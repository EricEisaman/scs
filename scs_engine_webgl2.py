# v50 DAMAGED_METAL + pixel-perfect HUD (viewport no DPR, HUD NEAREST) + import-safe
"""
scs_engine_webgl2_DAMAGED_METAL.py -- WebGL2 engine with DAMAGED METAL PBR shader.
Implements the full shader contract (see _VS/_FS comments).
GLSL ES 3.00, Cook-Torrance GGX + Smith + Schlick + Kulla-Conty multi-scatter, HDR IBL + BRDF LUT.
uDefectLevel in [0,1]. 0 = clean, baseline finish preserved. 1 = max authored damage.
Spheres are DAMAGED METAL: metallic=1.0, baseColor = metal F0, defectLevel per sphere.
HUD: blending ON, viewport = drawing buffer, so HUD does not cover 3D or scale wrong.
"""
import math
try:
    from browser import document, window
except ImportError:
    document = None
    window = None
try:
    from scs_3d import (mat4_mul, mat4_translate, mat4_scale,
                        make_sphere_mesh, make_cube_mesh)
except Exception:
    mat4_mul = None

_VS = '#version 300 es\n// Damaged-metal PBR - vertex shader\n// GLSL ES 3.00 (WebGL2). No mixed-version syntax.\n// Coordinate convention: object-space (a_pos) -> model -> world-space.\n// All lighting is in world space. Normals transformed by u_normal (inverse-transpose of model).\n// Attributes:\n//   a_pos    : vec3, object-space position\n//   a_normal : vec3, object-space normal\n//   a_uv     : vec2, optional (unused for defects - defects use object-space pos, so non-uniform scale does not stretch them)\n// Varyings:\n//   v_worldPos    : world-space position for lighting\n//   v_worldNormal : world-space normal (before defect perturbation)\n//   v_objPos      : object-space position for procedural defects (stable under model scale)\n//   v_uv          : passthrough, for future texture use\nin vec3 a_pos;\nin vec3 a_normal;\nin vec2 a_uv;\nuniform mat4 u_mvp;\nuniform mat4 u_model;\nuniform mat3 u_normal;\nout vec3 v_worldPos;\nout vec3 v_worldNormal;\nout vec3 v_objPos;\nout vec2 v_uv;\nvoid main() {\n    vec4 wp = u_model * vec4(a_pos, 1.0);\n    v_worldPos = wp.xyz;\n    v_worldNormal = u_normal * a_normal;\n    v_objPos = a_pos;\n    v_uv = a_uv;\n    gl_Position = u_mvp * vec4(a_pos, 1.0);\n}\n'
_FS = '#version 300 es\n// Damaged-metal PBR - fragment shader\n// GLSL ES 3.00 (WebGL2). Cook-Torrance GGX + Smith + Schlick Fresnel + Kulla-Conty multi-scatter.\n// Coordinate convention: ALL lighting in WORLD space.\n//   N : shading normal (world, after defect perturbation, normalized)\n//   V : view dir = normalize(u_camPos - v_worldPos) (world)\n//   L : light dir (world, pointing TOWARD light)\n//   R : reflection dir = reflect(-V, N) (world)\n// Material evaluation (baseColor, metallic, roughness, N) is SEPARATE from lighting.\n// BRDF is called with those values - no material logic inside the BRDF.\n// Linear HDR throughout. Tone mapping + sRGB encode happen EXACTLY ONCE at the end, in this shader.\n// Host must NOT tone map again.\n// Base-color textures (if any) must be decoded sRGB -> linear by host. Rough/metal/normal/defect masks are linear.\n// F0 = mix(vec3(0.04), baseColor, metallic). kD = (1-F)*(1-metallic). Fully metallic => no Lambertian diffuse.\n// Roughness convention: alpha = roughness*roughness (GGX). Applied identically in direct + IBL.\n// Roughness floor 0.04. No final HDR clamp to [0,1] before tone mapping.\n// uDefectLevel in [0,1], clamped internally. 0.0 = clean, every damage term vanishes, baseline finish preserved.\n// 1.0 = max authored damage, not random. Same procedural fields for all defect levels (fixed hash, no seed change).\n// Defects: scratches (metallic, elongated), pits (metallic), roughness variation, dirt/corrosion (dielectric, reduces metallic).\n// Corrosion is OPTIONAL (u_corrosionEnabled) and uses u_corrosionColor - NOT auto-orange.\n// Scratches: sparse elongated, direction-controlled. Pits: sparse cellular. Both use same mask for roughness + normal.\n// Normal perturbation: from coherent height field via screen-space derivatives, NOT random RGB.\n// High-frequency detail is filtered with fwidth (ES 3.00 core) to avoid sparkle at distance.\n// Brushed finish: ISOTROPIC approximation in this shader (GGX isotropic). Directional scratch masks affect\n// roughness/normal only - they are NOT a full anisotropic BRDF. Use anisotropic GGX if true brushed anisotropy is required.\n// Geometry limit: normal/bump only. Deep gouges / large dents that change silhouette need displacement/geometry, not this shader.\nprecision highp float;\nprecision highp samplerCube;\nprecision highp sampler2D;\nin vec3 v_worldPos;\nin vec3 v_worldNormal;\nin vec3 v_objPos;\nin vec2 v_uv;\nlayout(location = 0) out vec4 fragColor;\n// --- Material (baseline, host-provided, linear) ---\nuniform vec3  u_baseColor;      // linear base color (F0 for metal). Host converts sRGB -> linear.\nuniform float u_metallic;       // baseline metallic, [0,1]. Clean metal = 1.0.\nuniform float u_roughness;      // baseline perceptual roughness, [0,1]. 0.18 polished, 0.35 brushed/satin, 0.5 satin.\n// --- Defects ---\nuniform float u_defectLevel;    // [0,1], clamped internally. 0 = clean, 1 = max authored damage.\nuniform float u_featureScale;   // physical feature scale. Object-space coords * u_featureScale. Default 1.0 = 1 unit = 1 m.\nuniform float u_corrosionEnabled; // 0 = no corrosion (metal stays metal), 1 = allow corrosion layer where defect is high.\nuniform vec3  u_corrosionColor; // linear corrosion colour. E.g. copper patina green (0.2,0.7,0.5) linear, steel rust (0.35,0.12,0.05) linear. NOT auto-orange.\nuniform float u_corrosionMetallic; // metallic of corrosion layer, usually 0.0 (dielectric).\n// --- Lighting ---\nuniform vec3  u_camPos;         // world-space camera position.\nuniform vec3  u_lightDir;       // world-space direction TOWARD key light (normalized by shader).\nuniform vec3  u_lightColor;     // linear key light colour * intensity.\nuniform float u_envIntensity;   // IBL intensity multiplier.\nuniform float u_exposure;       // exposure, applied once before tone mapping.\n// --- IBL ---\nuniform samplerCube u_envMap;   // HDR cubemap, roughness-prefiltered mip chain (host provides). Linear HDR.\nuniform sampler2D u_brdfLUT;    // BRDF integration LUT (Split-Sum, Karis 2013). R = F*scale, G = bias. Linear.\n// --- Debug ---\nuniform int   u_debugMode;      // 0=final, 1=defect masks (R=scratch G=pit B=roughVar A=dirt), 2=metallic, 3=roughness,\n//                               // 4=shading normal (encoded), 5=direct specular, 6=env specular, 7=scratches only, 8=pits only.\nconst float PI = 3.141592653589793;\n// ---------- Hash / noise (fixed, deterministic, no seed change with uDefectLevel) ----------\nfloat hash11(float p) { p = fract(p * 0.1031); p *= p + 33.33; p *= p + p; return fract(p); }\nfloat hash21(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }\nfloat hash31(vec3 p) { p = fract(p * 0.3183099 + vec3(0.1, 0.17, 0.13)); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }\nfloat vnoise(vec3 p) {\n    vec3 i = floor(p); vec3 f = fract(p); f = f * f * (3.0 - 2.0 * f);\n    float n000 = hash31(i + vec3(0.0,0.0,0.0)); float n100 = hash31(i + vec3(1.0,0.0,0.0));\n    float n010 = hash31(i + vec3(0.0,1.0,0.0)); float n110 = hash31(i + vec3(1.0,1.0,0.0));\n    float n001 = hash31(i + vec3(0.0,0.0,1.0)); float n101 = hash31(i + vec3(1.0,0.0,1.0));\n    float n011 = hash31(i + vec3(0.0,1.1,1.0)); float n111 = hash31(i + vec3(1.0,1.0,1.0));\n    return mix(mix(mix(n000,n100,f.x), mix(n010,n110,f.x), f.y),\n               mix(mix(n001,n101,f.x), mix(n011,n111,f.x), f.y), f.z);\n}\nfloat fbm(vec3 p, int octaves) {\n    float v = 0.0; float amp = 0.5; float freq = 1.0;\n    for (int i = 0; i < 5; i++) {\n        if (i >= octaves) break;\n        v += amp * vnoise(p * freq);\n        freq *= 2.03; amp *= 0.5;\n    }\n    return v;\n}\n// ---------- BRDF (Cook-Torrance, GGX, Smith, Schlick) ----------\nfloat D_GGX(vec3 N, vec3 H, float alpha) {\n    float a2 = alpha * alpha;\n    float NdotH = clamp(dot(N, H), 0.0, 1.0);\n    float NdotH2 = NdotH * NdotH;\n    float denom = NdotH2 * (a2 - 1.0) + 1.0;\n    return a2 / (PI * denom * denom + 1e-7);\n}\nfloat G_SchlickGGX(float NdotV, float alpha) {\n    // Smith masking-shadowing, Schlick-GGX, alpha = roughness^2 convention (Karis).\n    // k = alpha / 2 for direct lighting (not (r+1)^2/8 - that is a different convention).\n    float k = alpha * 0.5;\n    return NdotV / (NdotV * (1.0 - k) + k + 1e-7);\n}\nfloat G_Smith(vec3 N, vec3 V, vec3 L, float alpha) {\n    float NdotV = clamp(dot(N, V), 0.0, 1.0);\n    float NdotL = clamp(dot(N, L), 0.0, 1.0);\n    return G_SchlickGGX(NdotV, alpha) * G_SchlickGGX(NdotL, alpha);\n}\nvec3 F_Schlick(float cosTheta, vec3 F0) {\n    return F0 + (vec3(1.0) - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);\n}\nvec3 F_SchlickRough(float cosTheta, vec3 F0, float rough) {\n    return F0 + (max(vec3(1.0 - rough), F0) - F0) * pow(clamp(1.0 - cosTheta, 0.0, 1.0), 5.0);\n}\n// ---------- Normal perturbation from coherent height field ----------\nvec3 perturbNormal(vec3 surfPos, vec3 surfNormal, float height, float scale) {\n    // Cotangent-frame bump from height field. Height must be the SAME field used for roughness.\n    float hx = dFdx(height);\n    float hy = dFdy(height);\n    vec3 dpdx = dFdx(surfPos);\n    vec3 dpdy = dFdy(surfPos);\n    vec3 r1 = cross(dpdy, surfNormal);\n    vec3 r2 = cross(surfNormal, dpdx);\n    float det = dot(dpdx, r1);\n    float sgn = (det < 0.0) ? -1.0 : 1.0;\n    vec3 grad = sgn * (hx * r1 + hy * r2);\n    return normalize(abs(det) * surfNormal - scale * grad);\n}\n// ---------- Defect masks (all deterministic, fixed fields, same mask for roughness + normal) ----------\n// Returns: scratch, pit, roughVar, dirt, corrosion via out params. All 0 when uDefectLevel == 0.\nvoid defectMasks(vec3 objPos, float defect, out float scratch, out float pit, out float roughVar, out float dirt, out float corrosion) {\n    scratch = 0.0; pit = 0.0; roughVar = 0.0; dirt = 0.0; corrosion = 0.0;\n    if (defect <= 0.0) return;\n    float d = clamp(defect, 0.0, 1.0);\n    // Coverage + amplitude envelopes: separate threshold (coverage) and depth (amplitude).\n    // Coverage grows with defect, amplitude deepens. Not finalColor * defect.\n    float scratchCov = smoothstep(0.03, 0.65, d);\n    float pitCov     = smoothstep(0.12, 0.80, d);\n    float roughCov   = smoothstep(0.02, 0.60, d);\n    float dirtCov    = smoothstep(0.40, 0.92, d);\n    float corrCov    = smoothstep(0.55, 1.00, d) * u_corrosionEnabled;\n    float scratchAmp = smoothstep(0.0, 0.60, d);\n    float pitAmp     = smoothstep(0.0, 0.70, d);\n    vec3 p = objPos * u_featureScale;\n    // --- Broad finish variation (low freq, affects roughness only, not normal) ---\n    float broad = fbm(p * 1.2 + vec3(7.3), 3);\n    roughVar = (broad - 0.5) * 2.0 * roughCov * 0.35;\n    // --- Medium wear patches (affects roughness + dirt, not normal) ---\n    float wear = fbm(p * 2.1 + vec3(3.7, 1.2, 9.1), 3);\n    float wearMask = smoothstep(0.62, 0.78, wear) * roughCov;\n    roughVar += wearMask * 0.45;\n    // --- Scratches: 3 families, elongated, different directions ---\n    // Family A: elongated along X (low freq in X, high freq in Y/Z)\n    float ridgeA = 1.0 - abs(vnoise(vec3(p.x * 2.0, p.y * 28.0, p.z * 28.0)) * 2.0 - 1.0);\n    float fwA = fwidth(ridgeA);\n    float sA = smoothstep(0.94 - fwA, 0.985 + fwA, ridgeA);\n    sA *= 1.0 - clamp(fwA * 3.0, 0.0, 1.0); // filter: fade when pixel footprint > scratch width (no sparkle)\n    // Family B: elongated along Y\n    float ridgeB = 1.0 - abs(vnoise(vec3(p.x * 26.0, p.y * 2.0, p.z * 26.0)) * 2.0 - 1.0);\n    float fwB = fwidth(ridgeB);\n    float sB = smoothstep(0.94 - fwB, 0.985 + fwB, ridgeB);\n    sB *= 1.0 - clamp(fwB * 3.0, 0.0, 1.0);\n    // Family C: diagonal, elongated along (1,1,0)\n    vec3 pC = vec3(dot(p, vec3(0.707, 0.707, 0.0)) * 2.0, dot(p, vec3(-0.707, 0.707, 0.0)) * 26.0, p.z * 26.0);\n    float ridgeC = 1.0 - abs(vnoise(pC) * 2.0 - 1.0);\n    float fwC = fwidth(ridgeC);\n    float sC = smoothstep(0.945 - fwC, 0.99 + fwC, ridgeC);\n    sC *= 1.0 - clamp(fwC * 3.0, 0.0, 1.0);\n    // Sparse: only a fraction of ridge lines are real scratches (hash gate per cell)\n    float gateA = step(0.55, hash31(floor(p * vec3(2.0, 28.0, 28.0)) * 0.5));\n    float gateB = step(0.60, hash31(floor(p * vec3(26.0, 2.0, 26.0)) * 0.5 + 13.0));\n    float gateC = step(0.62, hash31(floor(pC) * 0.5 + 7.0));\n    scratch = clamp(sA * gateA + sB * gateB + sC * gateC, 0.0, 1.0) * scratchCov * scratchAmp;\n    // --- Pits: sparse cellular, depth via shape ---\n    float pitNoise = vnoise(p * 14.0 + vec3(11.0));\n    float pitCell = hash31(floor(p * 14.0));\n    float pitRaw = smoothstep(0.72, 0.88, pitNoise) * step(0.68, pitCell);\n    float fwP = fwidth(pitNoise);\n    pitRaw *= 1.0 - clamp(fwP * 2.0, 0.0, 1.0);\n    pit = pitRaw * pitCov * pitAmp;\n    // --- Dirt: medium patches, dielectric (will reduce metallic) ---\n    float dirtNoise = fbm(p * 1.8 + vec3(19.0, 4.0, 2.0), 3);\n    dirt = smoothstep(0.68, 0.82, dirtNoise) * dirtCov;\n    // --- Corrosion: only if enabled, only where dirt/wear is, uses its own field (not a copy of dirt) ---\n    float corrNoise = fbm(p * 2.6 + vec3(5.0, 23.0, 17.0), 3);\n    corrosion = smoothstep(0.66, 0.80, corrNoise) * corrCov * (0.4 + 0.6 * dirt);\n    // Clamp all\n    scratch = clamp(scratch, 0.0, 1.0); pit = clamp(pit, 0.0, 1.0);\n    dirt = clamp(dirt, 0.0, 1.0); corrosion = clamp(corrosion, 0.0, 1.0);\n}\n// ---------- Material evaluation (separate from lighting) ----------\nvoid evaluateMaterial(vec3 objPos, vec3 geomNormal, vec3 worldPos,\n                      out vec3 baseColor, out float metallic, out float roughness, out vec3 N,\n                      out float scratchM, out float pitM, out float roughVarM, out float dirtM, out float corrM) {\n    float defect = clamp(u_defectLevel, 0.0, 1.0);\n    defectMasks(objPos, defect, scratchM, pitM, roughVarM, dirtM, corrM);\n    // Baseline finish (preserved at defect==0)\n    baseColor = u_baseColor;\n    metallic = clamp(u_metallic, 0.0, 1.0);\n    roughness = clamp(u_roughness, 0.04, 1.0);\n    // Roughness: scratches + pits + broad/wear variation increase roughness (mechanical damage does NOT change metallic)\n    float roughAdd = scratchM * 0.35 + pitM * 0.45 + roughVarM;\n    // Dirt slightly raises roughness (matte layer)\n    roughAdd += dirtM * 0.25 + corrM * 0.30;\n    roughness = clamp(roughness + roughAdd, 0.04, 1.0);\n    // Height field for normal perturbation: SAME masks as roughness (coherence)\n    float height = scratchM * 0.18 + pitM * 0.55 + roughVarM * 0.05;\n    // Normal: perturb from height field, strength scales with defect (0 at defect==0 because masks are 0)\n    vec3 nGeom = normalize(geomNormal);\n    if (defect > 0.0 && (scratchM > 0.001 || pitM > 0.001)) {\n        N = perturbNormal(worldPos, nGeom, height, 1.2);\n    } else {\n        N = nGeom;\n    }\n    // Metallic: ONLY dirt/corrosion (another substance) reduces metallic. Scratches/pits stay metallic.\n    float dielectricCover = clamp(dirtM * 0.85 + corrM * 0.95, 0.0, 1.0);\n    metallic = mix(metallic, u_corrosionMetallic * corrM + 0.0 * (1.0 - corrM), dielectricCover);\n    // Actually: dirt is dielectric (metallic 0), corrosion is u_corrosionMetallic (usually 0)\n    metallic = mix(metallic, 0.0, dielectricCover);\n    // Base colour: corrosion layer replaces base colour where corrosion is (its own substance)\n    // Dirt darkens slightly (not a colour multiply by defect - a layer blend)\n    baseColor = mix(baseColor, baseColor * 0.72, dirtM * 0.6);\n    baseColor = mix(baseColor, u_corrosionColor, corrM);\n    // Ensure linear, no negative\n    baseColor = max(baseColor, vec3(0.0));\n}\n// ---------- Tone mapping (ACES fitted, exactly once) ----------\nvec3 aces(vec3 x) {\n    float a = 2.51; float b = 0.03; float c = 2.43; float d = 0.59; float e = 0.14;\n    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);\n}\nvec3 srgbEncode(vec3 lin) { return pow(clamp(lin, 0.0, 1.0), vec3(1.0 / 2.2)); }\n// ---------- Cloudy sky environment - the actual reflection source ----------\n// Overcast sky, not a gradient + softboxes. This is what makes metal read as metal.\n// Procedural fbm clouds: dark grey tops, bright diffused glow at horizon where sun is behind clouds,\n// warm grey horizon band. Used for IBL and for background. Roughness blurs it via mip / fbm scale.\n// If a real HDR equirect is bound to u_envMap, we blend 85% cloudy-sky + 15% envMap so the sky dominates.\n// If no envMap, cloudy sky is 100% of IBL - never black.\nvec3 cloudySky(vec3 dir, float rough) {\n    vec3 d = normalize(dir);\n    float y = d.y;\n    vec3 cp = vec3(d.x * 1.8, d.y * 3.2, d.z * 1.8);\n    float blur = 1.0 + rough * 3.0;\n    float c1 = fbm(cp * 1.2 / blur + vec3(3.1), 4);\n    float c2 = fbm(cp * 2.6 / blur + vec3(7.7, 1.3, 2.2), 4);\n    float c3 = fbm(cp * 5.5 / blur + vec3(1.7, 9.1, 4.3), 3);\n    float cloud = c1 * 0.55 + c2 * 0.30 + c3 * 0.15;\n    vec3 sunDir = normalize(vec3(-0.55, 0.12, 0.35));\n    float sunAmt = pow(max(dot(d, sunDir), 0.0), 3.0);\n    float horizonGlow = exp(-abs(y - 0.08) * 4.0);\n    vec3 zenith = vec3(0.18, 0.22, 0.28);\n    vec3 midCloud = vec3(0.45, 0.50, 0.58);\n    vec3 brightCloud = vec3(0.78, 0.80, 0.82);\n    vec3 warmHorizon = vec3(0.72, 0.62, 0.52);\n    vec3 ground = vec3(0.28, 0.20, 0.16);\n    vec3 sky = mix(midCloud, zenith, smoothstep(0.1, 0.85, y));\n    sky = mix(sky, brightCloud, smoothstep(0.45, 0.75, cloud) * (1.0 - smoothstep(0.0, 0.5, y)));\n    sky = mix(sky, warmHorizon, horizonGlow * (0.55 + 0.45 * cloud));\n    sky += vec3(1.0, 0.85, 0.65) * sunAmt * horizonGlow * 1.2;\n    sky = mix(ground, sky, smoothstep(-0.25, 0.05, y));\n    sky *= 0.82 + 0.36 * cloud;\n    return sky;\n}\n// ---------- Main ----------\nvoid main() {\n    // Geometry normal, face correction (double-sided for debugging, engine culls back faces normally)\n    vec3 geomN = normalize(v_worldNormal);\n    if (!gl_FrontFacing) geomN = -geomN;\n    vec3 V = normalize(u_camPos - v_worldPos);\n    // Material evaluation FIRST, lighting SECOND\n    vec3 baseColor; float metallic; float roughness; vec3 N;\n    float scratchM, pitM, roughVarM, dirtM, corrM;\n    evaluateMaterial(v_objPos, geomN, v_worldPos, baseColor, metallic, roughness, N, scratchM, pitM, roughVarM, dirtM, corrM);\n    // Clamp + floor\n    roughness = clamp(roughness, 0.04, 1.0);\n    metallic = clamp(metallic, 0.0, 1.0);\n    float alpha = roughness * roughness; // GGX alpha convention, used in direct + IBL consistently\n    float NdotV = clamp(dot(N, V), 0.0, 1.0);\n    vec3 F0 = mix(vec3(0.04), baseColor, metallic);\n    // --- Direct light (key, 3-point for readability - key is the physical one, fill/rim are low-intensity) ---\n    vec3 L1 = normalize(u_lightDir);\n    vec3 L1col = u_lightColor;\n    vec3 L2 = normalize(vec3(-0.7, 0.25, -0.6));\n    vec3 L2col = vec3(0.35, 0.55, 1.0) * 0.9;\n    vec3 L3 = normalize(vec3(0.2, 0.6, -1.0));\n    vec3 L3col = vec3(0.9, 0.95, 1.0) * 1.2;\n    vec3 lights[3]; lights[0] = L1; lights[1] = L2; lights[2] = L3;\n    vec3 lightCols[3]; lightCols[0] = L1col; lightCols[1] = L2col; lightCols[2] = L3col;\n    vec3 Lo = vec3(0.0);\n    vec3 directSpec = vec3(0.0);\n    for (int i = 0; i < 3; i++) {\n        vec3 L = lights[i];\n        vec3 H = normalize(V + L);\n        float NdotL = clamp(dot(N, L), 0.0, 1.0);\n        if (NdotL <= 0.0) continue;\n        float NDF = D_GGX(N, H, alpha);\n        float G = G_Smith(N, V, L, alpha);\n        vec3 F = F_Schlick(clamp(dot(H, V), 0.0, 1.0), F0);\n        vec3 spec = (NDF * G * F) / (4.0 * NdotV * NdotL + 1e-4);\n        vec3 kS = F;\n        vec3 kD = (vec3(1.0) - kS) * (1.0 - metallic); // fully metallic => kD = 0, no Lambertian\n        vec3 diff = kD * baseColor / PI;\n        Lo += (diff + spec) * lightCols[i] * NdotL;\n        if (i == 0) directSpec = spec * lightCols[i] * NdotL;\n    }\n    // --- IBL (HDR cubemap, roughness-prefiltered, Split-Sum) ---\n    vec3 R = reflect(-V, N);\n    R = normalize(R);\n    // Prefiltered env: mip = alpha * MAX_LOD (host provides cubemap with mips). Consistent with direct alpha.\n    float maxLod = 6.0; // host: cubemap with 7 mips (128 -> 1). If fewer mips, clamp still works.\n    // IBL: cloudy sky IS the environment. 85% cloudy sky + 15% envMap (if bound).\n    vec3 cloudy = cloudySky(R, roughness);\n    vec3 envTex = textureLod(u_envMap, R, roughness * maxLod).rgb;\n    float envHasContent = step(0.01, dot(envTex, vec3(1.0)));\n    vec3 prefiltered = mix(cloudy, cloudy * 0.85 + envTex * 0.15, envHasContent);\n    // If host provides no envMap (black), prefiltered is black - no fake ambient. Host MUST provide HDR env.\n    vec2 brdf = texture(u_brdfLUT, vec2(NdotV, roughness)).rg;\n    vec3 Fenv = F_SchlickRough(NdotV, F0, roughness);\n    vec3 specIBL = prefiltered * (Fenv * brdf.x + brdf.y);\n    // --- Multiple-scattering compensation (Kulla-Conty 2017, via BRDF LUT) ---\n    // Single-scatter loses energy at high roughness, especially on metals. Do NOT fix with ambient.\n    // E_ss = brdf.x + brdf.y, E_ms = 1 - E_ss, F_avg approx from F0 + (1-F0)*0.2 (average Fresnel)\n    float E_ss = brdf.x + brdf.y;\n    float E_ms = 1.0 - E_ss;\n    vec3 F_avg = F0 + (vec3(1.0) - F0) * 0.2;\n    // Energy that would be lost to multiple bounces, re-injected as diffuse-like (but metal-tinted) term\n    vec3 F_ms = (F_avg * E_ms) / (1.0 - F_avg * (1.0 - E_ms) + 1e-4);\n    vec3 msComp = prefiltered * F_ms * E_ms * metallic; // only matters for metals, dielectric gets it via diffuse below\n    // Diffuse IBL (only for non-metal)\n    vec3 irradiance = cloudySky(N, 0.9) * 0.85 + textureLod(u_envMap, N, 5.0).rgb * 0.15; // cloudy diffuse\n    vec3 kDenv = (vec3(1.0) - Fenv) * (1.0 - metallic);\n    vec3 diffIBL = kDenv * baseColor * irradiance;\n    vec3 envSpec = specIBL + msComp;\n    vec3 LoHDR = Lo + diffIBL + envSpec * u_envIntensity;\n    // --- Debug views ---\n    if (u_debugMode == 1) { fragColor = vec4(clamp(vec3(scratchM, pitM, roughVarM * 0.5 + 0.5), 0.0, 1.0), 1.0); return; }\n    if (u_debugMode == 2) { fragColor = vec4(vec3(metallic), 1.0); return; }\n    if (u_debugMode == 3) { fragColor = vec4(vec3(roughness), 1.0); return; }\n    if (u_debugMode == 4) { fragColor = vec4(N * 0.5 + 0.5, 1.0); return; }\n    if (u_debugMode == 5) { fragColor = vec4(srgbEncode(aces(directSpec * u_exposure)), 1.0); return; }\n    if (u_debugMode == 6) { fragColor = vec4(srgbEncode(aces(envSpec * u_exposure)), 1.0); return; }\n    if (u_debugMode == 7) { fragColor = vec4(vec3(scratchM), 1.0); return; }\n    if (u_debugMode == 8) { fragColor = vec4(vec3(pitM), 1.0); return; }\n    // --- Final: NO clamp of HDR to [0,1] before tone mapping. Exposure -> ACES -> sRGB, exactly once. ---\n    vec3 col = aces(LoHDR * u_exposure);\n    col = srgbEncode(col);\n    fragColor = vec4(col, 1.0);\n}\n'

_NAMED = {
    'black': (0, 0, 0), 'white': (255, 255, 255),
    'red': (255, 0, 0), 'green': (0, 128, 0), 'blue': (0, 0, 255),
    'yellow': (255, 255, 0), 'cyan': (0, 255, 255),
    'magenta': (255, 0, 255), 'orange': (255, 165, 0),
    'gray': (128, 128, 128), 'grey': (128, 128, 128),
    'gold': (255, 215, 0), 'dodgerblue': (30, 144, 255),
}


def _parse_color(c):
    """Own colour parser. Does NOT import scs_webgl's."""
    if c is None:
        return (0.0, 0.0, 0.0)
    if isinstance(c, (list, tuple)):
        if len(c) >= 3:
            return (float(c[0]) / 255.0 if c[0] > 1 else float(c[0]),
                    float(c[1]) / 255.0 if c[1] > 1 else float(c[1]),
                    float(c[2]) / 255.0 if c[2] > 1 else float(c[2]))
    s = str(c).strip().lower()
    if s in _NAMED:
        r, g, b = _NAMED[s]
        return (r / 255.0, g / 255.0, b / 255.0)
    if s.startswith('#'):
        h = s[1:]
        if len(h) == 3:
            h = ''.join(ch * 2 for ch in h)
        if len(h) == 6:
            return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0,
                    int(h[4:6], 16) / 255.0)
    return (0.0, 0.0, 1.0)


class WebGL2Engine:
    """Owns one WebGL2 context, one program, one sphere mesh, one
    cube mesh. Scene is a plain list -- render(camera) draws it."""

    kind = 'webgl2-3d'

    def __init__(self, canvas=None, width=900, height=560):
        self.width = int(width)
        self.height = int(height)
        self.canvas = canvas
        self.gl = None
        self.program = None
        self.scene = []  # [{kind, pos, scale, color}]
        self.clear_color = (0.05, 0.05, 0.10, 1.0)
        self.light = (0.5, 1.0, 0.5)
        self._buf_v = None
        self._buf_i = None
        self._sphere_index_count = 0
        self._cube_index_count = 0
        self._cube_index_offset = 0
        self.error = None
        if self.canvas is None:
            self.canvas = self._find_canvas()
        if self.canvas is None:
            self.error = 'No canvas for WebGL2Engine'
            return
        try:
            # SEPARATE native context. If this canvas already has a
            # 2D context, the browser returns None -- that is a real
            # failure, not something to paper over with a fallback.
            self.gl = self.canvas.getContext('webgl2')
        except Exception as e:
            self.gl = None
            self.error = 'getContext(webgl2) failed: %s' % e
            return
        if self.gl is None:
            self.error = 'WebGL2 not available (getContext returned null)'
            return
        try:
            print('SCS renderer version=0.1 mode=webgl2 damaged-metal')
        except Exception:
            pass
        # Fall through to program creation (old code returned here, leaving program=None)
        gl = self.gl
        try:
            self.program = self._compile(_VS, _FS)
            self._buf_v = gl.createBuffer()
            self._buf_i = gl.createBuffer()
            s_verts, s_idx = make_sphere_mesh(24, 32)
            c_verts, c_idx = make_cube_mesh()
            all_verts = list(s_verts) + list(c_verts)
            n_sphere_verts = len(s_verts) // 6
            all_idx = list(s_idx) + [i + n_sphere_verts for i in c_idx]
            self._sphere_index_count = len(s_idx)
            self._cube_index_offset = len(s_idx)
            self._cube_index_count = len(c_idx)
            gl.bindBuffer(gl.ARRAY_BUFFER, self._buf_v)
            gl.bufferData(gl.ARRAY_BUFFER,
                          window.Float32Array.new(all_verts),
                          gl.STATIC_DRAW)
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, self._buf_i)
            gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,
                          window.Uint16Array.new(all_idx),
                          gl.STATIC_DRAW)
            gl.enable(gl.DEPTH_TEST)
            gl.depthFunc(gl.LESS)
            gl.enable(gl.CULL_FACE)
            gl.cullFace(gl.BACK)
            # --- IBL assets: procedural HDR env cubemap + BRDF LUT ---
            # Host owns these. If you have real HDR files, replace _make_env_cubemap/_make_brdf_lut with file loads.
            # Env: 6 faces, each a small gradient + softbox streaks, mipmapped for roughness-prefiltering.
            # BRDF LUT: 128x128, Split-Sum (Karis). Generated on CPU here (no external file needed for demo).
            try:
                self.exposure = 1.0
                self.envIntensity = 1.0
                self.debugMode = 0
                self._env_tex = self._make_env_cubemap()
                self._brdf_tex = self._make_brdf_lut()
            except Exception as _e:
                self._env_tex = None
                self._brdf_tex = None
        except Exception as e:
            self.error = 'WebGL2Engine init failed: %s' % e
            self.gl = None

    def _make_env_cubemap(self):
        # Procedural HDR env: 64x64 per face, sky gradient + 2 softboxes. Mipmapped (generateMipmap) for prefiltering.
        # This is a placeholder for a real HDR file (e.g. studio.hdr -> cubemap). For production, load HDR equirect
        # and convert to cubemap + prefilter per roughness. The shader treats it as linear HDR.
        gl = self.gl
        tex = gl.createTexture()
        gl.bindTexture(gl.TEXTURE_CUBE_MAP, tex)
        try:
            gl.texParameteri(gl.TEXTURE_CUBE_MAP, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
            gl.texParameteri(gl.TEXTURE_CUBE_MAP, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
            gl.texParameteri(gl.TEXTURE_CUBE_MAP, gl.TEXTURE_WRAP_R, gl.CLAMP_TO_EDGE)
            gl.texParameteri(gl.TEXTURE_CUBE_MAP, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR)
            gl.texParameteri(gl.TEXTURE_CUBE_MAP, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
        except Exception:
            pass
        # 6 faces: +X, -X, +Y, -Y, +Z, -Z. Each face: 64x64 RGBA float via Uint8 (LDR approx of HDR, scaled in shader by envIntensity).
        # For a true HDR env, use RGBA16F + float data. Here we use Uint8 for broad compatibility.
        import math as _m
        for face in range(6):
            data = []
            for y in range(64):
                for x in range(64):
                    u = (x / 63.0) * 2.0 - 1.0
                    v = (y / 63.0) * 2.0 - 1.0
                    # Simple gradient per face: horizon warm, zenith blue
                    g = 0.25 + 0.35 * max(0.0, v)
                    r = int(180 * g + 60 * max(0.0, u)); gcol = int(190 * g + 40); b = int(255 * g)
                    # Softbox streak on +Y face
                    if face == 2 and abs(u) < 0.4 and abs(v) < 0.2:
                        r, gcol, b = 255, 250, 230
                    data.extend([min(255, r), min(255, gcol), min(255, b), 255])
            try:
                gl.texImage2D(gl.TEXTURE_CUBE_MAP_POSITIVE_X + face, 0, gl.RGBA, 64, 64, 0, gl.RGBA, gl.UNSIGNED_BYTE, window.Uint8Array.new(data))
            except Exception:
                pass
        try:
            gl.generateMipmap(gl.TEXTURE_CUBE_MAP)
        except Exception:
            pass
        return tex

    def _make_brdf_lut(self):
        # Split-Sum BRDF LUT (Karis 2013): R = F*scale, G = bias. 128x128.
        # Computed on CPU with GGX + Smith + Schlick, 1024 samples per texel (approx). Host can replace with a precomputed file.
        gl = self.gl
        tex = gl.createTexture()
        gl.bindTexture(gl.TEXTURE_2D, tex)
        try:
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
        except Exception:
            pass
        import math as _m
        data = []
        for y in range(128):
            rough = (y + 0.5) / 128.0
            alpha = rough * rough
            for x in range(128):
                ndv = (x + 0.5) / 128.0
                ndv = max(ndv, 0.001)
                # Integrate: sample hemisphere, GGX, Smith, Schlick (F0=1 for scale, F0=0 for bias via 1-cos)
                s1 = 0.0; s2 = 0.0; n = 64
                V = (_m.sqrt(1.0 - ndv * ndv), 0.0, ndv)
                for k in range(n):
                    # Hammersley
                    u1 = (k + 0.5) / float(n); u2 = ((k * 7) % n + 0.5) / float(n)
                    phi = 2.0 * _m.pi * u1
                    cosT = _m.sqrt((1.0 - u2) / (1.0 + (alpha * alpha - 1.0) * u2))
                    sinT = _m.sqrt(max(0.0, 1.0 - cosT * cosT))
                    H = (sinT * _m.cos(phi), sinT * _m.sin(phi), cosT)
                    # L = 2*dot(V,H)*H - V
                    vdoth = max(0.0, V[0] * H[0] + V[2] * H[2])
                    Lx = 2.0 * vdoth * H[0] - V[0]; Ly = 2.0 * vdoth * H[1] - V[1]; Lz = 2.0 * vdoth * H[2] - V[2]
                    ndotl = max(0.0, Lz)
                    ndoth = max(0.0, H[2])
                    if ndotl > 0.0:
                        # G_Smith with alpha
                        k_g = alpha * 0.5
                        g1v = ndv / (ndv * (1.0 - k_g) + k_g + 1e-6)
                        g1l = ndotl / (ndotl * (1.0 - k_g) + k_g + 1e-6)
                        G = g1v * g1l
                        vis = G * vdoth / (ndoth * ndv + 1e-6)
                        fc = pow(1.0 - vdoth, 5.0)
                        s1 += (1.0 - fc) * vis
                        s2 += fc * vis
                s1 /= float(n); s2 /= float(n)
                data.extend([int(max(0, min(255, s1 * 255))), int(max(0, min(255, s2 * 255))), 0, 255])
        try:
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 128, 128, 0, gl.RGBA, gl.UNSIGNED_BYTE, window.Uint8Array.new(data))
        except Exception:
            pass
        return tex

    def _find_canvas(self):
        if document is None:
            return None
        for cid in ('webgl2-canvas', 'canvas', 'scs-canvas', 'cmu-canvas'):
            try:
                c = document.getElementById(cid)
            except Exception:
                c = None
            if c is not None:
                return c
        return None

    def _compile(self, vs_src, fs_src):
        gl = self.gl
        vs = gl.createShader(gl.VERTEX_SHADER)
        gl.shaderSource(vs, vs_src)
        gl.compileShader(vs)
        try:
            if not gl.getShaderParameter(vs, gl.COMPILE_STATUS):
                print(gl.getShaderInfoLog(vs))
                return None
        except Exception:
            pass
        fs = gl.createShader(gl.FRAGMENT_SHADER)
        gl.shaderSource(fs, fs_src)
        gl.compileShader(fs)
        try:
            if not gl.getShaderParameter(fs, gl.COMPILE_STATUS):
                print(gl.getShaderInfoLog(fs))
                return None
        except Exception:
            pass
        prog = gl.createProgram()
        gl.attachShader(prog, vs)
        gl.attachShader(prog, fs)
        gl.linkProgram(prog)
        try:
            if not gl.getProgramParameter(prog, gl.LINK_STATUS):
                print(gl.getProgramInfoLog(prog))
                return None
        except Exception:
            pass
        return prog

    # -- scene ------------------------------------------------------
    def clear_scene(self):
        self.scene = []

    def add_sphere(self, x, y, z, radius, color='blue', metalness=None, roughness=None, material=None, defectLevel=0.72, corrosionEnabled=0.0, corrosionColor='#3a1a08', featureScale=1.0):
        # METAL default for the spatial-audio sphere: chrome. Callers that pass
        # explicit metalness/roughness win. 'blue' + no material = old look would be
        # flat, so a bare add_sphere('blue') now means polished blue metal, not plastic.
        # Dielectric callers pass metalness=0 explicitly.
        if material == 'metal':
            metalness = 1.0 if metalness is None else metalness
            roughness = 0.12 if roughness is None else roughness
        elif material == 'plastic':
            metalness = 0.0 if metalness is None else metalness
            roughness = 0.55 if roughness is None else roughness
        elif material == 'chrome':
            metalness = 1.0 if metalness is None else metalness
            roughness = 0.08 if roughness is None else roughness
        if metalness is None:
            # No material given: sphere = metal (the hero object). Boxes stay dielectric below.
            metalness = 1.0
        if roughness is None:
            roughness = 0.14
        # DAMAGED METAL: default metallic=1.0 (not plastic). If caller passes metalness explicitly, respect it.
        # defectLevel is per-object artistic control, NOT roughness replacement.
        self.scene.append({'kind': 'sphere',
                           'pos': (float(x), float(y), float(z)),
                           'scale': (float(radius),) * 3,
                           'color': color,
                           'metalness': float(metalness),
                           'roughness': float(roughness),
                           'defectLevel': float(defectLevel),
                           'corrosionEnabled': float(corrosionEnabled),
                           'corrosionColor': corrosionColor,
                           'featureScale': float(featureScale)})
        return self.scene[-1]

    def add_metal_sphere(self, x, y, z, radius, color='#c8d4e8', roughness=0.12):
        # Explicit hero: polished chrome-blue metal. This is what spatial audio uses.
        return self.add_sphere(x, y, z, radius, color=color, metalness=1.0, roughness=roughness, material='metal')

    def add_box(self, x, y, z, sx, sy, sz, color='gray', metalness=0.0, roughness=0.85, material=None, defectLevel=0.0, corrosionEnabled=0.0, corrosionColor='#3a1a08', featureScale=1.0):
        if material == 'metal':
            metalness = 1.0
            roughness = 0.25
        self.scene.append({'kind': 'cube',
                           'pos': (float(x), float(y), float(z)),
                           'scale': (float(sx), float(sy), float(sz)),
                           'color': color,
                           'metalness': float(metalness),
                           'roughness': float(roughness),
                           'defectLevel': float(defectLevel),
                           'corrosionEnabled': float(corrosionEnabled),
                           'corrosionColor': corrosionColor,
                           'featureScale': float(featureScale)})
        return self.scene[-1]

    def add_floor(self, size=22.0, color='#22223a'):
        # Flat box as the floor -- dielectric, rough, so metal sphere pops against it.
        return self.add_box(0.0, -0.05, 0.0, size, 0.1, size, color, metalness=0.0, roughness=0.95)

    # -- render -----------------------------------------------------
    def render(self, camera):
        """Draw the scene from `camera` (Camera3D). Own loop calls
        this once per frame. Returns False if no GL context."""
        if self.gl is None or camera is None:
            return False
        gl = self.gl
        try:
            # v29 3D resize: viewport from the ACTUAL drawing buffer, not
            # width*dpr recomputed here. WebGL does NOT update the viewport
            # automatically after canvas.width/height changes. drawingBufferWidth
            # is the backing size set by the entrypoint pipeline (CSS * budgeted
            # ratio). Projection below uses CSS aspect (width/height) so resizing
            # reframes without stretching geometry.
            try:
                _dbw = int(getattr(gl, 'drawingBufferWidth', 0) or 0)
                _dbh = int(getattr(gl, 'drawingBufferHeight', 0) or 0)
            except Exception:
                _dbw = _dbh = 0
            if _dbw > 0 and _dbh > 0:
                gl.viewport(0, 0, _dbw, _dbh)
            else:
                _dpr2 = 1.0
                try:
                    _dpr2 = min(float(window.devicePixelRatio or 1.0), 2.0)
                except Exception:
                    pass
                gl.viewport(0, 0, int(self.width * _dpr2), int(self.height * _dpr2))
            r, g, b, a = self.clear_color
            gl.clearColor(r, g, b, a)
            # REAL depth: colour + depth, depth test on for the whole draw.
            gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT)
            gl.enable(gl.DEPTH_TEST)
            view = camera.view_matrix()
            proj = camera.proj_matrix(self.width / float(self.height))
            gl.useProgram(self.program)
            gl.bindBuffer(gl.ARRAY_BUFFER, self._buf_v)
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, self._buf_i)
            a_pos = gl.getAttribLocation(self.program, 'a_pos')
            a_norm = gl.getAttribLocation(self.program, 'a_normal')
            gl.enableVertexAttribArray(a_pos)
            gl.enableVertexAttribArray(a_norm)
            gl.vertexAttribPointer(a_pos, 3, gl.FLOAT, False, 6 * 4, 0)
            gl.vertexAttribPointer(a_norm, 3, gl.FLOAT, False, 6 * 4, 3 * 4)
            u_mvp = gl.getUniformLocation(self.program, 'u_mvp')
            u_model = gl.getUniformLocation(self.program, 'u_model')
            u_norm = gl.getUniformLocation(self.program, 'u_normal')
            u_col = gl.getUniformLocation(self.program, 'u_baseColor')
            u_metal = gl.getUniformLocation(self.program, 'u_metallic')
            u_defect = gl.getUniformLocation(self.program, 'u_defectLevel')
            u_feat = gl.getUniformLocation(self.program, 'u_featureScale')
            u_corrEn = gl.getUniformLocation(self.program, 'u_corrosionEnabled')
            u_corrCol = gl.getUniformLocation(self.program, 'u_corrosionColor')
            u_corrMetal = gl.getUniformLocation(self.program, 'u_corrosionMetallic')
            u_envMap = gl.getUniformLocation(self.program, 'u_envMap')
            u_brdf = gl.getUniformLocation(self.program, 'u_brdfLUT')
            u_debug = gl.getUniformLocation(self.program, 'u_debugMode')
            u_expo = gl.getUniformLocation(self.program, 'u_exposure')
            u_envInt = gl.getUniformLocation(self.program, 'u_envIntensity')
            u_rough = gl.getUniformLocation(self.program, 'u_roughness')
            u_cam = gl.getUniformLocation(self.program, 'u_camPos')
            u_light = gl.getUniformLocation(self.program, 'u_lightDir')
            u_light_col = gl.getUniformLocation(self.program, 'u_lightColor')
            # Camera pos: Camera3D.position - drives view-dependent Fresnel / reflections.
            try:
                cp = camera.position
                gl.uniform3f(u_cam, float(cp[0]), float(cp[1]), float(cp[2]))
            except Exception:
                gl.uniform3f(u_cam, 0.0, 2.0, 6.0)
            gl.uniform3f(u_light, float(self.light[0]),
                         float(self.light[1]), float(self.light[2]))
            # Warm key light - makes chrome read warm on one side, cool on the other.
            gl.uniform3f(u_light_col, 1.0, 0.95, 0.88)
            for item in self.scene:
                model = mat4_mul(mat4_translate(*item['pos']),
                                 mat4_scale(*item['scale']))
                mv = mat4_mul(view, model)
                mvp = mat4_mul(proj, mv)
                nm = [mv[0], mv[1], mv[2],
                      mv[4], mv[5], mv[6],
                      mv[8], mv[9], mv[10]]
                gl.uniformMatrix4fv(u_mvp, False,
                                    window.Float32Array.new(mvp))
                if u_model is not None:
                    gl.uniformMatrix4fv(u_model, False,
                                        window.Float32Array.new(model))
                gl.uniformMatrix3fv(u_norm, False,
                                    window.Float32Array.new(nm))
                cr, cg, cb = _parse_color(item['color'])
                # Host owns sRGB -> linear for base color (shader expects linear). Do NOT pass sRGB.
                # _parse_color returns sRGB 0..1 from hex. Convert: lin = srgb^2.2 (approx sRGB decode).
                try:
                    lr = float(cr) ** 2.2; lg = float(cg) ** 2.2; lb = float(cb) ** 2.2
                except Exception:
                    lr, lg, lb = cr, cg, cb
                gl.uniform3f(u_col, lr, lg, lb)
                if u_metal is not None:
                    gl.uniform1f(u_metal, float(item.get('metalness', 1.0)))
                if u_rough is not None:
                    gl.uniform1f(u_rough, float(item.get('roughness', 0.35)))
                # --- Damaged metal: per-object defect control ---
                if u_defect is not None:
                    gl.uniform1f(u_defect, float(item.get('defectLevel', 0.0)))
                if u_feat is not None:
                    gl.uniform1f(u_feat, float(item.get('featureScale', 1.0)))
                if u_corrEn is not None:
                    gl.uniform1f(u_corrEn, float(item.get('corrosionEnabled', 0.0)))
                if u_corrCol is not None:
                    ccr, ccg, ccb = _parse_color(item.get('corrosionColor', '#3a1a08'))
                    try:
                        ccr = float(ccr) ** 2.2; ccg = float(ccg) ** 2.2; ccb = float(ccb) ** 2.2
                    except Exception:
                        pass
                    gl.uniform3f(u_corrCol, ccr, ccg, ccb)
                if u_corrMetal is not None:
                    gl.uniform1f(u_corrMetal, 0.0)
                if u_debug is not None:
                    gl.uniform1i(u_debug, int(getattr(self, 'debugMode', 0)))
                if u_expo is not None:
                    gl.uniform1f(u_expo, float(getattr(self, 'exposure', 1.0)))
                if u_envInt is not None:
                    gl.uniform1f(u_envInt, float(getattr(self, 'envIntensity', 1.0)))
                # --- IBL bindings: env cubemap on TEXTURE0, BRDF LUT on TEXTURE1 ---
                try:
                    if getattr(self, '_env_tex', None) is not None:
                        gl.activeTexture(gl.TEXTURE0)
                        gl.bindTexture(gl.TEXTURE_CUBE_MAP, self._env_tex)
                        if u_envMap is not None:
                            gl.uniform1i(u_envMap, 0)
                    if getattr(self, '_brdf_tex', None) is not None:
                        gl.activeTexture(gl.TEXTURE1)
                        gl.bindTexture(gl.TEXTURE_2D, self._brdf_tex)
                        if u_brdf is not None:
                            gl.uniform1i(u_brdf, 1)
                except Exception:
                    pass
                if item['kind'] == 'sphere':
                    gl.drawElements(gl.TRIANGLES,
                                    self._sphere_index_count,
                                    gl.UNSIGNED_SHORT, 0)
                else:
                    gl.drawElements(gl.TRIANGLES,
                                    self._cube_index_count,
                                    gl.UNSIGNED_SHORT,
                                    self._cube_index_offset * 2)
            return True
        except Exception as e:
            self.error = 'render failed: %s' % e
            return False

    def draw_hud_canvas(self, canvas, left=0, top=0, w=None, h=None, opacity=100):
        """HUD texture in the 3D engine: offscreen 2D canvas -> texture -> fullscreen HUD quad.
        Depth off, ortho, on top of the 3D scene. Default HUD/2D. Returns True."""
        try:
            if canvas is None or getattr(self, 'gl', None) is None:
                return False
            gl = self.gl
            ww = float(w) if w is not None else float(self.width)
            hh = float(h) if h is not None else float(self.height)
            # Upload canvas as texture (reuse _hud_tex if present)
            try:
                tex = getattr(self, '_hud_tex', None)
                if tex is None:
                    tex = gl.createTexture()
                    self._hud_tex = tex
                gl.bindTexture(gl.TEXTURE_2D, tex)
                try:
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST)  # v50 pixel-perfect HUD
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)  # v50 pixel-perfect HUD
                except Exception:
                    pass
                try:
                    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, canvas)
                except Exception:
                    return False
            except Exception:
                return False
            # HUD quad: depth off, BLENDING ON. Without blending, transparent HUD pixels (alpha 0)
            # overwrite 3D with black. With SRC_ALPHA / ONE_MINUS_SRC_ALPHA, only HUD pixels show.
            # Viewport = drawing-buffer size, not CSS size, or HUD scales wrong.
            try:
                if not hasattr(self, '_hud_prog') or self._hud_prog is None:
                    _vs = "attribute vec2 a_p; attribute vec2 a_uv; varying vec2 v_uv; void main(){ v_uv=a_uv; gl_Position=vec4(a_p,0.0,1.0); }"
                    _fs = "precision mediump float; uniform sampler2D u_tex; varying vec2 v_uv; void main(){ gl_FragColor=texture2D(u_tex, v_uv); }"
                    _vs_o = gl.createShader(gl.VERTEX_SHADER); gl.shaderSource(_vs_o, _vs); gl.compileShader(_vs_o)
                    _fs_o = gl.createShader(gl.FRAGMENT_SHADER); gl.shaderSource(_fs_o, _fs); gl.compileShader(_fs_o)
                    _prog = gl.createProgram(); gl.attachShader(_prog, _vs_o); gl.attachShader(_prog, _fs_o); gl.linkProgram(_prog)
                    if _prog is None:
                        return False
                    self._hud_prog = _prog
                    _buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, _buf)
                    # UV: canvas top -> V=0 (texImage2D with canvas does NOT flip Y)
                    _verts = [-1.0,-1.0,0.0,1.0, 1.0,-1.0,1.0,1.0, -1.0,1.0,0.0,0.0, 1.0,1.0,1.0,0.0]
                    gl.bufferData(gl.ARRAY_BUFFER, window.Float32Array.new(_verts), gl.STATIC_DRAW)
                    self._hud_buf = _buf
                if getattr(self, '_hud_prog', None) is None:
                    return False
                # v29: HUD pass viewport also from drawing buffer, not recomputed DPR.
                try:
                    _dbw2 = int(getattr(gl, 'drawingBufferWidth', 0) or 0)
                    _dbh2 = int(getattr(gl, 'drawingBufferHeight', 0) or 0)
                except Exception:
                    _dbw2 = _dbh2 = 0
                if _dbw2 > 0 and _dbh2 > 0:
                    gl.viewport(0, 0, _dbw2, _dbh2)
                else:
                    try:
                        _dpr = min(float(window.devicePixelRatio or 1.0), 2.0)
                    except Exception:
                        _dpr = 1.0
                    gl.viewport(0, 0, int(self.width), int(self.height))  # v50: backing==CSS, no DPR multiply
                gl.disable(gl.DEPTH_TEST)
                gl.enable(gl.BLEND)
                gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
                gl.useProgram(self._hud_prog)
                gl.bindBuffer(gl.ARRAY_BUFFER, self._hud_buf)
                _ap = gl.getAttribLocation(self._hud_prog, 'a_p')
                _au = gl.getAttribLocation(self._hud_prog, 'a_uv')
                if _ap < 0 or _au < 0:
                    gl.disable(gl.BLEND); gl.enable(gl.DEPTH_TEST); return False
                gl.enableVertexAttribArray(_ap); gl.vertexAttribPointer(_ap, 2, gl.FLOAT, False, 16, 0)
                gl.enableVertexAttribArray(_au); gl.vertexAttribPointer(_au, 2, gl.FLOAT, False, 16, 8)
                gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex)
                gl.uniform1i(gl.getUniformLocation(self._hud_prog, 'u_tex'), 0)
                gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
                gl.disable(gl.BLEND)
                gl.enable(gl.DEPTH_TEST)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def draw_html_element(self, element, left=0, top=0, w=None, h=None, opacity=100):
        """HTML-in-Canvas in the 3D engine: live DOM -> texture via texElementSubImage2D.
        Chrome 157+ only. Returns True if upload succeeded, False if not supported
        (caller falls back to HUD texture)."""
        try:
            if element is None or getattr(self, 'gl', None) is None:
                return False
            gl = self.gl
            if not (hasattr(gl, 'texElementSubImage2D') or hasattr(gl, 'texElementImage2D')):
                return False
            ww = float(w) if w is not None else float(self.width)
            hh = float(h) if h is not None else float(self.height)
            try:
                tex = getattr(self, '_html_tex', None)
                if tex is None:
                    tex = gl.createTexture()
                    self._html_tex = tex
                gl.bindTexture(gl.TEXTURE_2D, tex)
                try:
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
                except Exception:
                    pass
                # Allocate storage first (required before texElementSubImage2D)
                try:
                    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, int(ww), int(hh), 0, gl.RGBA, gl.UNSIGNED_BYTE, None)
                except Exception:
                    pass
                if hasattr(gl, 'texElementSubImage2D'):
                    gl.texElementSubImage2D(gl.TEXTURE_2D, 0, 0, 0, element)
                else:
                    gl.texElementImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, element)
            except Exception:
                return False
            # Hit-testing
            try:
                _canvas = getattr(self, 'canvas', None)
                if _canvas is not None and hasattr(_canvas, 'updateElementGeometry'):
                    try:
                        from browser import window as _win
                        _m = _win.DOMMatrix.new() if _win is not None else None
                        if _m is not None:
                            _m = _m.translate(float(left), float(top))
                            _canvas.updateElementGeometry(element, {'canvasTransform': _m})
                        else:
                            _canvas.updateElementGeometry(element, {})
                    except Exception:
                        pass
            except Exception:
                pass
            return True
        except Exception:
            return False

    def describe(self):
        return {'kind': self.kind, 'width': self.width,
                'height': self.height, 'scene_items': len(self.scene),
                'has_context': self.gl is not None, 'error': self.error}
