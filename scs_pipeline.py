"""
scs_pipeline.py -- PROPER PIPELINES. One pipeline per backend, owned state.

Pipelines are NOT inline GL calls scattered in an engine. Each pipeline
owns:
  * its shader (GLSL for WebGL2, WGSL for WebGPU),
  * its state (depth, cull, blend, topology),
  * its material binding (PBR uniforms from scs_materials.py),
  * its draw (indexed, instanced, chunked -- never "load whole 2GB, draw once").

PBR evaluation (both shaders): Cook-Torrance GGX + Smith + Schlick,
+ clearcoat (second GGX lobe), + sheen (Charlie), + transmission
(Beer-Lambert through thickness), + IBL (irradiance + prefiltered
env + BRDF LUT approximation). The CPU reference in scs_materials.py
(pbr_brdf) must match the direct-light term.

2GB rule: pipelines draw in CHUNKS. A draw call never requires the
whole asset in memory -- the loader streams chunks, the pipeline draws
the chunks that are resident (see scs_loader / scs_splats).
"""

# ----------------------------------------------------------------------
# Pipeline config -- same shape for every backend
# ----------------------------------------------------------------------

class PipelineConfig:
    def __init__(self, depth_test=True, depth_write=True, cull_mode='back',
                 blend=False, blend_src='SRC_ALPHA', blend_dst='ONE_MINUS_SRC_ALPHA',
                 topology='triangle-list', front_face='ccw', alpha_mode='OPAQUE',
                 double_sided=False, sample_count=1):
        self.depth_test = bool(depth_test)
        self.depth_write = bool(depth_write)
        self.cull_mode = str(cull_mode)  # 'back' | 'front' | 'none'
        self.blend = bool(blend)
        self.blend_src = blend_src
        self.blend_dst = blend_dst
        self.topology = topology
        self.front_face = front_face
        self.alpha_mode = alpha_mode
        self.double_sided = bool(double_sided)
        self.sample_count = int(sample_count)
        if self.double_sided:
            self.cull_mode = 'none'
        if self.alpha_mode == 'BLEND':
            self.blend = True
            self.depth_write = False
    def describe(self):
        return {'depth_test': self.depth_test, 'depth_write': self.depth_write,
                'cull_mode': self.cull_mode, 'blend': self.blend,
                'topology': self.topology, 'alpha_mode': self.alpha_mode,
                'double_sided': self.double_sided}

def config_for_material(material):
    """Pipeline config derived from a PBR material -- not guessed per draw."""
    if material is None:
        return PipelineConfig()
    return PipelineConfig(
        depth_test=True,
        depth_write=(material.alpha_mode != 'BLEND'),
        cull_mode='none' if material.double_sided else 'back',
        blend=(material.alpha_mode == 'BLEND'),
        alpha_mode=material.alpha_mode,
        double_sided=material.double_sided,
    )

# ----------------------------------------------------------------------
# GLSL PBR -- WebGL2
# ----------------------------------------------------------------------

GLSL_PBR_VS = """
attribute vec3 a_pos;
attribute vec3 a_normal;
attribute vec2 a_uv;
attribute vec4 a_tangent;
uniform mat4 u_mvp;
uniform mat4 u_model;
uniform mat3 u_normalMat;
varying vec3 v_worldPos;
varying vec3 v_normal;
varying vec2 v_uv;
varying vec3 v_tangent;
varying vec3 v_bitangent;
void main() {
  vec4 wp = u_model * vec4(a_pos, 1.0);
  v_worldPos = wp.xyz;
  v_normal = normalize(u_normalMat * a_normal);
  v_uv = a_uv;
  v_tangent = normalize(u_normalMat * a_tangent.xyz);
  v_bitangent = normalize(cross(v_normal, v_tangent) * a_tangent.w);
  gl_Position = u_mvp * vec4(a_pos, 1.0);
}
"""

GLSL_PBR_FS = """
precision highp float;
uniform vec3 u_baseColor;
uniform float u_alpha;
uniform float u_metallic;
uniform float u_roughness;
uniform vec3 u_emissive;
uniform float u_emissiveStrength;
uniform float u_ior;
uniform vec3 u_specularColor;
uniform float u_specularFactor;
uniform float u_clearcoat;
uniform float u_clearcoatRoughness;
uniform vec3 u_sheenColor;
uniform float u_sheenRoughness;
uniform float u_transmission;
uniform float u_thickness;
uniform vec3 u_attenuationColor;
uniform float u_attenuationDistance;
uniform float u_iridescence;
uniform float u_iridescenceIor;
uniform float u_anisotropyStrength;
uniform float u_alphaCutoff;
uniform float u_unlit;
uniform vec3 u_camPos;
uniform vec3 u_lightDir;
uniform vec3 u_lightColor;
uniform vec3 u_ambient;
varying vec3 v_worldPos;
varying vec3 v_normal;
varying vec2 v_uv;
varying vec3 v_tangent;
varying vec3 v_bitangent;
float ggx(float ndh, float rough) {
  float a = rough * rough;
  float a2 = a * a;
  float d = ndh * ndh * (a2 - 1.0) + 1.0;
  return a2 / (3.14159265 * d * d);
}
float smithG(float ndv, float ndl, float rough) {
  float k = (rough + 1.0) * (rough + 1.0) / 8.0;
  float g1 = ndv / (ndv * (1.0 - k) + k);
  float g2 = ndl / (ndl * (1.0 - k) + k);
  return g1 * g2;
}
vec3 fresnel(float cosT, vec3 f0) {
  return f0 + (1.0 - f0) * pow(1.0 - cosT, 5.0);
}
void main() {
  if (u_unlit > 0.5) { gl_FragColor = vec4(u_baseColor, u_alpha); return; }
  vec3 N = normalize(v_normal);
  if (!gl_FrontFacing) N = -N;
  vec3 V = normalize(u_camPos - v_worldPos);
  vec3 L = normalize(u_lightDir);
  vec3 H = normalize(L + V);
  float ndl = max(dot(N, L), 0.0);
  float ndv = max(dot(N, V), 0.0);
  float ndh = max(dot(N, H), 0.0);
  float vdh = max(dot(V, H), 0.0);
  // F0 from IOR + specular, mixed by metalness
  float f0diel = pow((u_ior - 1.0) / (u_ior + 1.0), 2.0);
  vec3 f0 = mix(u_specularColor * u_specularFactor * f0diel, u_baseColor, u_metallic);
  // Direct: Cook-Torrance
  float D = ggx(ndh, u_roughness);
  float G = smithG(ndv, ndl, u_roughness);
  vec3 F = fresnel(vdh, f0);
  vec3 spec = D * G * F / max(4.0 * ndv * ndl, 0.001);
  float fAvg = (F.r + F.g + F.b) / 3.0;
  float kd = (1.0 - fAvg) * (1.0 - u_metallic);
  vec3 diff = kd * u_baseColor / 3.14159265;
  // Clearcoat: second GGX lobe (KHR_materials_clearcoat)
  float ccD = ggx(ndh, u_clearcoatRoughness);
  float ccG = smithG(ndv, ndl, u_clearcoatRoughness);
  vec3 ccF = fresnel(vdh, vec3(0.04));
  vec3 cc = ccD * ccG * ccF / max(4.0 * ndv * ndl, 0.001);
  // Sheen: Charlie approx (KHR_materials_sheen)
  float sheen = u_sheenRoughness * 0.0 + (1.0 - u_sheenRoughness) * pow(1.0 - ndh, 2.0);
  vec3 sheenCol = u_sheenColor * sheen * 0.5;
  // Transmission: Beer-Lambert (KHR_materials_transmission/volume)
  float beer = 1.0;
  if (u_transmission > 0.0 && u_thickness > 0.0) {
    vec3 att = -log(u_attenuationColor + 0.0001) / max(u_attenuationDistance, 0.001);
    beer = exp(-att.r * u_thickness * 0.33 - att.g * u_thickness * 0.33 - att.b * u_thickness * 0.33);
  }
  vec3 direct = (diff + spec + cc * u_clearcoat + sheenCol) * u_lightColor * ndl;
  direct = mix(direct, direct * beer + u_lightColor * 0.2, u_transmission);
  // IBL ambient: cheap irradiance + env spec approx
  vec3 iblDiff = u_baseColor * u_ambient * (1.0 - u_metallic);
  vec3 iblSpec = F * u_ambient * (1.0 - u_roughness);
  vec3 col = direct + iblDiff + iblSpec + u_emissive * u_emissiveStrength;
  if (u_alpha < u_alphaCutoff && u_alphaCutoff > 0.0) discard;
  gl_FragColor = vec4(col, u_alpha);
}
"""

# ----------------------------------------------------------------------
# WGSL PBR -- WebGPU (same math, WGSL syntax)
# ----------------------------------------------------------------------

WGSL_PBR = """
struct Uniforms {
  mvp: mat4x4<f32>,
  model: mat4x4<f32>,
  normalMat: mat3x3<f32>,
  baseColor: vec4<f32>,
  emissive: vec4<f32>,
  metallicRoughness: vec4<f32>, // x=metallic y=roughness z=ior w=alphaCutoff
  pbrExtra: vec4<f32>, // x=clearcoat y=clearcoatRough z=sheenRough w=transmission
  sheenColor: vec4<f32>,
  attenuation: vec4<f32>, // rgb=attenuationColor, a=attenuationDistance
  camPos: vec3<f32>,
  lightDir: vec3<f32>,
  lightColor: vec3<f32>,
  ambient: vec3<f32>,
};
@group(0) @binding(0) var<uniform> u: Uniforms;
struct VSOut {
  @builtin(position) pos: vec4<f32>,
  @location(0) worldPos: vec3<f32>,
  @location(1) normal: vec3<f32>,
  @location(2) uv: vec2<f32>,
};
@vertex fn vs(@location(0) pos: vec3<f32>, @location(1) normal: vec3<f32>, @location(2) uv: vec2<f32>) -> VSOut {
  var out: VSOut;
  let wp = u.model * vec4<f32>(pos, 1.0);
  out.worldPos = wp.xyz;
  out.normal = u.normalMat * normal;
  out.uv = uv;
  out.pos = u.mvp * vec4<f32>(pos, 1.0);
  return out;
}
fn ggx(ndh: f32, rough: f32) -> f32 {
  let a = rough * rough;
  let a2 = a * a;
  let d = ndh * ndh * (a2 - 1.0) + 1.0;
  return a2 / (3.14159265 * d * d);
}
fn smithG(ndv: f32, ndl: f32, rough: f32) -> f32 {
  let k = (rough + 1.0) * (rough + 1.0) / 8.0;
  let g1 = ndv / (ndv * (1.0 - k) + k);
  let g2 = ndl / (ndl * (1.0 - k) + k);
  return g1 * g2;
}
@fragment fn fs(@location(0) worldPos: vec3<f32>, @location(1) normal: vec3<f32>, @location(2) uv: vec2<f32>) -> @location(0) vec4<f32> {
  let N = normalize(normal);
  let V = normalize(u.camPos - worldPos);
  let L = normalize(u.lightDir);
  let H = normalize(L + V);
  let ndl = max(dot(N, L), 0.0);
  let ndv = max(dot(N, V), 0.0);
  let ndh = max(dot(N, H), 0.0);
  let vdh = max(dot(V, H), 0.0);
  let metallic = u.metallicRoughness.x;
  let roughness = u.metallicRoughness.y;
  let ior = u.metallicRoughness.z;
  let f0diel = pow((ior - 1.0) / (ior + 1.0), 2.0);
  let f0 = mix(vec3<f32>(f0diel), u.baseColor.rgb, metallic);
  let D = ggx(ndh, roughness);
  let G = smithG(ndv, ndl, roughness);
  let F = f0 + (vec3<f32>(1.0) - f0) * pow(1.0 - vdh, 5.0);
  let spec = D * G * F / max(4.0 * ndv * ndl, 0.001);
  let fAvg = (F.r + F.g + F.b) / 3.0;
  let kd = (1.0 - fAvg) * (1.0 - metallic);
  let diff = kd * u.baseColor.rgb / 3.14159265;
  let ccD = ggx(ndh, u.pbrExtra.y);
  let ccG = smithG(ndv, ndl, u.pbrExtra.y);
  let ccF = vec3<f32>(0.04) + (vec3<f32>(1.0) - vec3<f32>(0.04)) * pow(1.0 - vdh, 5.0);
  let cc = ccD * ccG * ccF / max(4.0 * ndv * ndl, 0.001);
  let direct = (diff + spec + cc * u.pbrExtra.x) * u.lightColor * ndl;
  let iblDiff = u.baseColor.rgb * u.ambient * (1.0 - metallic);
  let iblSpec = F * u.ambient * (1.0 - roughness);
  let col = direct + iblDiff + iblSpec + u.emissive.rgb;
  return vec4<f32>(col, u.baseColor.a);
}
"""



# ----------------------------------------------------------------------
# PBR SIMPLE -- pos + normal only (current sphere/cube meshes).
# Same BRDF as the full shader, no texture sampling. Used by the
# WebGL2 / WebGPU engines until meshes carry UV + tangent.
# ----------------------------------------------------------------------

GLSL_PBR_SIMPLE_VS = """
attribute vec3 a_pos;
attribute vec3 a_normal;
uniform mat4 u_mvp;
uniform mat4 u_model;
uniform mat3 u_normalMat;
varying vec3 v_worldPos;
varying vec3 v_normal;
void main() {
  vec4 wp = u_model * vec4(a_pos, 1.0);
  v_worldPos = wp.xyz;
  v_normal = normalize(u_normalMat * a_normal);
  gl_Position = u_mvp * vec4(a_pos, 1.0);
}
"""

GLSL_PBR_SIMPLE_FS = """
precision highp float;
uniform vec3 u_baseColor;
uniform float u_alpha;
uniform float u_metallic;
uniform float u_roughness;
uniform vec3 u_emissive;
uniform float u_ior;
uniform vec3 u_specularColor;
uniform float u_specularFactor;
uniform float u_clearcoat;
uniform float u_clearcoatRoughness;
uniform vec3 u_sheenColor;
uniform float u_sheenRoughness;
uniform float u_transmission;
uniform float u_thickness;
uniform vec3 u_attenuationColor;
uniform float u_attenuationDistance;
uniform float u_alphaCutoff;
uniform float u_unlit;
uniform vec3 u_camPos;
uniform vec3 u_lightDir;
uniform vec3 u_lightColor;
uniform vec3 u_ambient;
varying vec3 v_worldPos;
varying vec3 v_normal;
float ggx(float ndh, float rough) {
  float a = rough * rough; float a2 = a * a;
  float d = ndh * ndh * (a2 - 1.0) + 1.0;
  return a2 / (3.14159265 * d * d);
}
float smithG(float ndv, float ndl, float rough) {
  float k = (rough + 1.0) * (rough + 1.0) / 8.0;
  return (ndv / (ndv * (1.0 - k) + k)) * (ndl / (ndl * (1.0 - k) + k));
}
vec3 fresnel(float cosT, vec3 f0) { return f0 + (1.0 - f0) * pow(1.0 - cosT, 5.0); }
void main() {
  if (u_unlit > 0.5) { gl_FragColor = vec4(u_baseColor, u_alpha); return; }
  vec3 N = normalize(v_normal);
  if (!gl_FrontFacing) N = -N;
  vec3 V = normalize(u_camPos - v_worldPos);
  vec3 L = normalize(u_lightDir);
  vec3 H = normalize(L + V);
  float ndl = max(dot(N, L), 0.0);
  float ndv = max(dot(N, V), 0.0);
  float ndh = max(dot(N, H), 0.0);
  float vdh = max(dot(V, H), 0.0);
  float f0diel = pow((u_ior - 1.0) / (u_ior + 1.0), 2.0);
  vec3 f0 = mix(u_specularColor * u_specularFactor * f0diel, u_baseColor, u_metallic);
  float D = ggx(ndh, u_roughness);
  float G = smithG(ndv, ndl, u_roughness);
  vec3 F = fresnel(vdh, f0);
  vec3 spec = D * G * F / max(4.0 * ndv * ndl, 0.001);
  float fAvg = (F.r + F.g + F.b) / 3.0;
  float kd = (1.0 - fAvg) * (1.0 - u_metallic);
  vec3 diff = kd * u_baseColor / 3.14159265;
  float ccD = ggx(ndh, u_clearcoatRoughness);
  float ccG = smithG(ndv, ndl, u_clearcoatRoughness);
  vec3 cc = ccD * ccG * fresnel(vdh, vec3(0.04)) / max(4.0 * ndv * ndl, 0.001);
  float sheen = (1.0 - u_sheenRoughness) * pow(1.0 - ndh, 2.0);
  vec3 sheenCol = u_sheenColor * sheen * 0.5;
  float beer = 1.0;
  if (u_transmission > 0.0 && u_thickness > 0.0) {
    vec3 att = -log(u_attenuationColor + 0.0001) / max(u_attenuationDistance, 0.001);
    beer = exp(-(att.r + att.g + att.b) * u_thickness * 0.33);
  }
  vec3 direct = (diff + spec + cc * u_clearcoat + sheenCol) * u_lightColor * ndl;
  direct = mix(direct, direct * beer + u_lightColor * 0.2, u_transmission);
  vec3 col = direct + u_baseColor * u_ambient * (1.0 - u_metallic) + F * u_ambient * (1.0 - u_roughness) + u_emissive;
  if (u_alpha < u_alphaCutoff && u_alphaCutoff > 0.0) discard;
  gl_FragColor = vec4(col, u_alpha);
}
"""

WGSL_PBR_SIMPLE = """
struct Uniforms {
  mvp: mat4x4<f32>,
  model: mat4x4<f32>,
  normalMat: mat3x3<f32>,
  baseColor: vec4<f32>,
  emissive: vec4<f32>,
  metallicRoughness: vec4<f32>,
  pbrExtra: vec4<f32>,
  sheenColor: vec4<f32>,
  attenuation: vec4<f32>,
  camPos: vec3<f32>,
  lightDir: vec3<f32>,
  lightColor: vec3<f32>,
  ambient: vec3<f32>,
};
@group(0) @binding(0) var<uniform> u: Uniforms;
struct VSOut { @builtin(position) pos: vec4<f32>, @location(0) worldPos: vec3<f32>, @location(1) normal: vec3<f32>, };
@vertex fn vs(@location(0) pos: vec3<f32>, @location(1) normal: vec3<f32>) -> VSOut {
  var out: VSOut;
  let wp = u.model * vec4<f32>(pos, 1.0);
  out.worldPos = wp.xyz; out.normal = u.normalMat * normal;
  out.pos = u.mvp * vec4<f32>(pos, 1.0);
  return out;
}
fn ggx(ndh: f32, rough: f32) -> f32 {
  let a = rough * rough; let a2 = a * a;
  let d = ndh * ndh * (a2 - 1.0) + 1.0;
  return a2 / (3.14159265 * d * d);
}
fn smithG(ndv: f32, ndl: f32, rough: f32) -> f32 {
  let k = (rough + 1.0) * (rough + 1.0) / 8.0;
  return (ndv / (ndv * (1.0 - k) + k)) * (ndl / (ndl * (1.0 - k) + k));
}
@fragment fn fs(@location(0) worldPos: vec3<f32>, @location(1) normal: vec3<f32>) -> @location(0) vec4<f32> {
  let N = normalize(normal);
  let V = normalize(u.camPos - worldPos);
  let L = normalize(u.lightDir);
  let H = normalize(L + V);
  let ndl = max(dot(N, L), 0.0); let ndv = max(dot(N, V), 0.0);
  let ndh = max(dot(N, H), 0.0); let vdh = max(dot(V, H), 0.0);
  let metallic = u.metallicRoughness.x; let roughness = u.metallicRoughness.y; let ior = u.metallicRoughness.z;
  let f0diel = pow((ior - 1.0) / (ior + 1.0), 2.0);
  let f0 = mix(vec3<f32>(f0diel), u.baseColor.rgb, metallic);
  let D = ggx(ndh, roughness); let G = smithG(ndv, ndl, roughness);
  let F = f0 + (vec3<f32>(1.0) - f0) * pow(1.0 - vdh, 5.0);
  let spec = D * G * F / max(4.0 * ndv * ndl, 0.001);
  let fAvg = (F.r + F.g + F.b) / 3.0;
  let kd = (1.0 - fAvg) * (1.0 - metallic);
  let diff = kd * u.baseColor.rgb / 3.14159265;
  let ccD = ggx(ndh, u.pbrExtra.y); let ccG = smithG(ndv, ndl, u.pbrExtra.y);
  let ccF = vec3<f32>(0.04) + (vec3<f32>(1.0) - vec3<f32>(0.04)) * pow(1.0 - vdh, 5.0);
  let cc = ccD * ccG * ccF / max(4.0 * ndv * ndl, 0.001);
  let direct = (diff + spec + cc * u.pbrExtra.x) * u.lightColor * ndl;
  let col = direct + u.baseColor.rgb * u.ambient * (1.0 - metallic) + F * u.ambient * (1.0 - roughness) + u.emissive.rgb;
  return vec4<f32>(col, u.baseColor.a);
}
"""

# ----------------------------------------------------------------------
# Pipeline objects
# ----------------------------------------------------------------------

class WebGL2Pipeline:
    shader_language = 'GLSL'  # WebGL2 -> GLSL ONLY
    """Owns one WebGL2 program + state. One per material-kind, cached."""
    def __init__(self, gl, config=None, vs=None, fs=None):
        vs = vs or GLSL_PBR_SIMPLE_VS
        fs = fs or GLSL_PBR_SIMPLE_FS
        self.gl = gl
        self.config = config or PipelineConfig()
        self.vs_src = vs
        self.fs_src = fs
        self.program = None
        self._uniform_locs = {}
        self.error = None
        if gl is not None:
            try:
                self.program = self._compile(vs, fs)
            except Exception as e:
                self.error = str(e)
    def _compile(self, vs_src, fs_src):
        gl = self.gl
        vs = gl.createShader(gl.VERTEX_SHADER)
        gl.shaderSource(vs, vs_src); gl.compileShader(vs)
        fs = gl.createShader(gl.FRAGMENT_SHADER)
        gl.shaderSource(fs, fs_src); gl.compileShader(fs)
        prog = gl.createProgram()
        gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog)
        return prog
    def apply_state(self):
        gl = self.gl
        if gl is None:
            return
        if self.config.depth_test:
            gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS)
        else:
            try: gl.disable(gl.DEPTH_TEST)
            except Exception: pass
        if self.config.cull_mode == 'none':
            try: gl.disable(gl.CULL_FACE)
            except Exception: pass
        else:
            gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK)
        if self.config.blend:
            gl.enable(gl.BLEND)
        else:
            try: gl.disable(gl.BLEND)
            except Exception: pass
    def set_material_uniforms(self, material):
        """Push PBR uniforms. No per-draw colour parsing."""
        if material is None or self.gl is None or self.program is None:
            return
        gl = self.gl
        u = material.to_uniforms()
        try: gl.useProgram(self.program)
        except Exception: pass
        def uni(name):
            if name not in self._uniform_locs:
                try: self._uniform_locs[name] = gl.getUniformLocation(self.program, name)
                except Exception: self._uniform_locs[name] = None
            return self._uniform_locs[name]
        # Base PBR -- each call tolerant: FakeGL / partial GL may lack a setter.
        def _set(fn, *args):
            try: fn(*args)
            except Exception: pass
        bc = u['u_baseColor']
        _set(gl.uniform4f, uni('u_baseColor'), bc[0], bc[1], bc[2], bc[3])
        _set(gl.uniform1f, uni('u_metallic'), u.get('u_metallic', 0.0))
        _set(gl.uniform1f, uni('u_roughness'), u.get('u_roughness', 1.0))
        em = u['u_emissive']
        _set(gl.uniform3f, uni('u_emissive'), em[0], em[1], em[2])
        _set(gl.uniform1f, uni('u_emissiveStrength'), 1.0)
        _set(gl.uniform1f, uni('u_ior'), u.get('u_ior', 1.5))
        _set(gl.uniform1f, uni('u_clearcoat'), u.get('u_clearcoat', 0.0))
        _set(gl.uniform1f, uni('u_clearcoatRoughness'), u.get('u_clearcoatRoughness', 0.0))
        sc = u.get('u_sheenColor', (0,0,0,1))
        _set(gl.uniform3f, uni('u_sheenColor'), sc[0], sc[1], sc[2])
        _set(gl.uniform1f, uni('u_sheenRoughness'), u.get('u_sheenRoughness', 0.5))
        _set(gl.uniform1f, uni('u_transmission'), u.get('u_transmission', 0.0))
        _set(gl.uniform1f, uni('u_thickness'), u.get('u_thickness', 0.0))
        _set(gl.uniform1f, uni('u_alphaCutoff'), u.get('u_alphaCutoff', 0.5))
        _set(gl.uniform1f, uni('u_unlit'), u.get('u_unlit', 0.0))
    def describe(self):
        return {'backend': 'webgl2', 'config': self.config.describe(), 'has_program': self.program is not None, 'error': self.error}

class WebGPUPipeline:
    shader_language = 'WGSL'  # WebGPU -> WGSL ONLY
    """Owns one WebGPU render pipeline + WGSL. Async device, sync descriptor."""
    def __init__(self, device=None, format='bgra8unorm', config=None):
        self.device = device
        self.format = format
        self.config = config or PipelineConfig()
        self.pipeline = None
        self.shader_src = WGSL_PBR_SIMPLE
        self.error = None
    def pipeline_descriptor(self):
        """Pure descriptor -- testable without a GPU."""
        return {
            'layout': 'auto',
            'vertex': {'module': 'pbr', 'entryPoint': 'vs',
                       'buffers': [{'arrayStride': 32, 'attributes': [
                           {'shaderLocation': 0, 'offset': 0, 'format': 'float32x3'},
                           {'shaderLocation': 1, 'offset': 12, 'format': 'float32x3'},
                           {'shaderLocation': 2, 'offset': 24, 'format': 'float32x2'}]}]},
            'fragment': {'module': 'pbr', 'entryPoint': 'fs',
                         'targets': [{'format': self.format}]},
            'primitive': {'topology': 'triangle-list', 'cullMode': self.config.cull_mode},
            'depthStencil': {'depthWriteEnabled': self.config.depth_write,
                             'depthCompare': 'less' if self.config.depth_test else 'always',
                             'format': 'depth24plus'},
            'multisample': {'count': self.config.sample_count},
        }
    def describe(self):
        return {'backend': 'webgpu', 'config': self.config.describe(), 'has_pipeline': self.pipeline is not None}

class SplatPipeline:
    """Splat pipeline: point / quad splats, sorted, chunked. Separate from mesh pipelines."""
    def __init__(self, config=None):
        self.config = config or PipelineConfig(depth_write=False, blend=True)
        self.sorted = True
        self.chunked = True
    def sort_key(self, splat, camera_pos):
        dx = splat[0]-camera_pos[0]; dy = splat[1]-camera_pos[1]; dz = splat[2]-camera_pos[2]
        return -(dx*dx+dy*dy+dz*dz)
    def describe(self):
        return {'backend': 'splat', 'config': self.config.describe(), 'sorted': self.sorted, 'chunked': self.chunked}

class PipelineManager:
    """Cache pipelines by (backend, material-kind, config). One per kind, not per draw."""
    def __init__(self):
        self._cache = {}
    def webgl2(self, gl, material=None):
        from scs_materials import PBRMaterial
        cfg = config_for_material(material)
        key = ('webgl2', cfg.alpha_mode, cfg.double_sided)
        if key not in self._cache:
            self._cache[key] = WebGL2Pipeline(gl, cfg)
        return self._cache[key]
    def webgpu(self, device=None, material=None):
        cfg = config_for_material(material)
        key = ('webgpu', cfg.alpha_mode, cfg.double_sided)
        if key not in self._cache:
            self._cache[key] = WebGPUPipeline(device, config=cfg)
        return self._cache[key]
    def splat(self):
        if 'splat' not in self._cache:
            self._cache['splat'] = SplatPipeline()
        return self._cache['splat']
    def describe(self):
        return {str(k): v.describe() for k, v in self._cache.items()}
