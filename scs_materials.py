"""
scs_materials.py -- PBR MATERIALS, second to none.

A material is DATA, not a shader. The GLB loader produces materials
from glTF JSON (including every KHR extension below). The pipelines
(scs_pipeline.py) turn a material into shader uniforms / bind groups.
The engines never invent material semantics inline.

PBR model: Cook-Torrance, GGX NDF, Smith geometry, Schlick Fresnel,
plus IBL (irradiance + prefiltered env + BRDF LUT). See
scs_pipeline.py for the GLSL/WGSL that evaluates it, and
pbr_brdf() in this file for the CPU reference the shaders must match.

KHR extensions supported (all of them, not just baseColor):
  KHR_materials_clearcoat, KHR_materials_sheen, KHR_materials_transmission,
  KHR_materials_volume, KHR_materials_ior, KHR_materials_specular,
  KHR_materials_iridescence, KHR_materials_anisotropy, KHR_materials_dispersion,
  KHR_materials_emissive_strength, KHR_materials_unlit,
  KHR_texture_transform, KHR_materials_variants (variant selection).

Splat materials are separate: captured-radiance (SH is radiance, NOT
albedo) vs relightable (base_color + normal + roughness + PRT).

No GL / WebGPU calls here. Pure data + CPU BRDF reference.
"""

import math

# ----------------------------------------------------------------------
# CPU BRDF reference -- shaders must match this. Used by tests.
# ----------------------------------------------------------------------

def _clamp01(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except Exception:
        return 0.0

def _vec3(v, default=(1.0, 1.0, 1.0)):
    try:
        if v is None:
            return tuple(default)
        return (float(v[0]), float(v[1]), float(v[2]))
    except Exception:
        return tuple(default)

def _vec4(v, default=(1.0, 1.0, 1.0, 1.0)):
    try:
        if v is None:
            return tuple(default)
        return (float(v[0]), float(v[1]), float(v[2]),
                float(v[3]) if len(v) > 3 else 1.0)
    except Exception:
        return tuple(default)

def ggx_ndf(n_dot_h, roughness):
    """GGX / Trowbridge-Reitz NDF. roughness in [0,1], a = roughness^2."""
    a = max(float(roughness), 0.001) ** 2
    a2 = a * a
    d = n_dot_h * n_dot_h * (a2 - 1.0) + 1.0
    return a2 / (math.pi * d * d)

def schlick_geometry(n_dot_v, roughness):
    """Schlick-GGX geometry (single direction)."""
    k = (float(roughness) + 1.0) ** 2 / 8.0
    return n_dot_v / (n_dot_v * (1.0 - k) + k)

def smith_geometry(n_dot_v, n_dot_l, roughness):
    return schlick_geometry(n_dot_v, roughness) * schlick_geometry(n_dot_l, roughness)

def fresnel_schlick(cos_theta, f0):
    """f0 as (r,g,b) tuple. Returns (r,g,b)."""
    m = max(1.0 - float(cos_theta), 0.0) ** 5
    return tuple(f + (1.0 - f) * m for f in f0)

def fresnel_schlick_roughness(cos_theta, f0, roughness):
    """Schlick with roughness -- used for IBL specular."""
    m = max(1.0 - float(cos_theta), 0.0) ** 5
    fmax = max(1.0 - float(roughness), f0[0]), max(1.0 - float(roughness), f0[1]), max(1.0 - float(roughness), f0[2])
    # per-channel: f0 + (max(1-rough, f0) - f0) * m
    return tuple(f + (fm - f) * m for f, fm in zip(f0, fmax))

def pbr_brdf(n_dot_l, n_dot_v, n_dot_h, v_dot_h, base_color, metallic, roughness):
    """Cook-Torrance BRDF (specular) + Lambert diffuse, scalar N/V/L/H.
    Returns (diffuse_rgb, specular_rgb) for a white light of intensity 1.
    This is the reference the GLSL/WGSL must match."""
    ndl = max(float(n_dot_l), 0.0)
    ndv = max(float(n_dot_v), 0.0)
    ndh = max(float(n_dot_h), 0.0)
    vdh = max(float(v_dot_h), 0.0)
    if ndl <= 0.0 or ndv <= 0.0:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    # F0: dielectric 0.04, metal = baseColor
    f0 = tuple(c * metallic + 0.04 * (1.0 - metallic) for c in base_color)
    D = ggx_ndf(ndh, roughness)
    G = smith_geometry(ndv, ndl, roughness)
    F = fresnel_schlick(vdh, f0)
    spec = tuple(D * G * f / (4.0 * ndv * ndl + 0.001) for f in F)
    # Energy conservation: diffuse = (1 - F) * (1 - metallic) * albedo / pi
    # Use average Fresnel for the diffuse term (matches shader).
    f_avg = sum(F) / 3.0
    kd = (1.0 - f_avg) * (1.0 - metallic)
    diff = tuple(kd * c / math.pi for c in base_color)
    return diff, spec

# ----------------------------------------------------------------------
# Texture transform (KHR_texture_transform)
# ----------------------------------------------------------------------

class TextureTransform:
    def __init__(self, offset=(0.0, 0.0), rotation=0.0, scale=(1.0, 1.0), tex_coord=0):
        self.offset = (float(offset[0]), float(offset[1])) if offset else (0.0, 0.0)
        self.rotation = float(rotation)
        self.scale = (float(scale[0]), float(scale[1])) if scale else (1.0, 1.0)
        self.tex_coord = int(tex_coord)
    def apply(self, uv):
        # glTF: uv' = R * (S * uv) + offset, rotation about origin per spec
        # (with KHR_texture_transform, rotation is counter-clockwise).
        c, s = math.cos(self.rotation), math.sin(self.rotation)
        x = uv[0] * self.scale[0]
        y = uv[1] * self.scale[1]
        rx = x * c - y * s
        ry = x * s + y * c
        return (rx + self.offset[0], ry + self.offset[1])
    def describe(self):
        return {'offset': list(self.offset), 'rotation': self.rotation,
                'scale': list(self.scale), 'texCoord': self.tex_coord}

class TextureInfo:
    """One texture slot: index + transform + texCoord. Not the pixels."""
    def __init__(self, index=None, tex_coord=0, transform=None, strength=None, scale=None):
        self.index = index
        self.tex_coord = int(tex_coord)
        self.transform = transform  # TextureTransform or None
        self.strength = strength    # occlusionStrength
        self.scale = scale          # normalScale
    def describe(self):
        d = {'index': self.index, 'texCoord': self.tex_coord}
        if self.transform is not None:
            d['transform'] = self.transform.describe()
        if self.strength is not None:
            d['strength'] = self.strength
        if self.scale is not None:
            d['scale'] = self.scale
        return d

def _tex_info(j):
    if not isinstance(j, dict):
        return None
    tr = None
    ext = j.get('extensions') or {}
    ktx = ext.get('KHR_texture_transform') or {}
    if ktx:
        tr = TextureTransform(offset=ktx.get('offset', (0.0, 0.0)),
                              rotation=ktx.get('rotation', 0.0),
                              scale=ktx.get('scale', (1.0, 1.0)),
                              tex_coord=ktx.get('texCoord', j.get('texCoord', 0)))
    return TextureInfo(index=j.get('index'), tex_coord=j.get('texCoord', 0),
                       transform=tr)

# ----------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------

class Material:
    def __init__(self, name='', base_color=(1.0, 1.0, 1.0), alpha=1.0,
                 double_sided=False, alpha_mode='OPAQUE', alpha_cutoff=0.5,
                 emissive=(0.0, 0.0, 0.0), emissive_factor=1.0, emissive_strength=1.0,
                 normal_scale=1.0):
        self.name = str(name or '')
        self.base_color = _vec3(base_color)
        self.alpha = _clamp01(alpha)
        self.double_sided = bool(double_sided)
        self.alpha_mode = str(alpha_mode or 'OPAQUE').upper()
        self.alpha_cutoff = float(alpha_cutoff)
        self.emissive = _vec3(emissive, (0.0, 0.0, 0.0))
        self.emissive_factor = float(emissive_factor)
        self.emissive_strength = float(emissive_strength)
        self.normal_scale = float(normal_scale)
        self.base_color_texture = None  # TextureInfo
        self.normal_texture = None
        self.metallic_roughness_texture = None
        self.occlusion_texture = None
        self.emissive_texture = None
        self.kind = 'material'
        self.unlit = False
        self.variants = {}  # variant name -> material override (KHR_materials_variants)

    def to_uniforms(self):
        return {
            'u_baseColor': (self.base_color[0], self.base_color[1], self.base_color[2], self.alpha),
            'u_emissive': (self.emissive[0] * self.emissive_factor * self.emissive_strength,
                           self.emissive[1] * self.emissive_factor * self.emissive_strength,
                           self.emissive[2] * self.emissive_factor * self.emissive_strength, 1.0),
            'u_alphaCutoff': self.alpha_cutoff,
            'u_doubleSided': 1.0 if self.double_sided else 0.0,
            'u_hasBaseColorTexture': 1.0 if self.base_color_texture is not None else 0.0,
            'u_hasNormalTexture': 1.0 if self.normal_texture is not None else 0.0,
            'u_hasEmissiveTexture': 1.0 if self.emissive_texture is not None else 0.0,
            'u_normalScale': self.normal_scale,
            'u_unlit': 1.0 if self.unlit else 0.0,
        }

    def describe(self):
        return {'kind': self.kind, 'name': self.name, 'base_color': list(self.base_color),
                'alpha': self.alpha, 'double_sided': self.double_sided,
                'alpha_mode': self.alpha_mode, 'emissive': list(self.emissive),
                'emissive_strength': self.emissive_strength, 'unlit': self.unlit}

class PBRMaterial(Material):
    """Full PBR: metallic-roughness + every KHR extension."""
    def __init__(self, name='', base_color=(1.0, 1.0, 1.0), metallic=1.0, roughness=1.0,
                 ior=1.5, specular_factor=1.0, specular_color=(1.0, 1.0, 1.0),
                 clearcoat=0.0, clearcoat_roughness=0.0,
                 sheen_color=(0.0, 0.0, 0.0), sheen_roughness=0.5,
                 transmission=0.0, thickness=0.0,
                 attenuation_color=(1.0, 1.0, 1.0), attenuation_distance=float('inf'),
                 iridescence=0.0, iridescence_ior=1.3, iridescence_thickness_min=100.0,
                 iridescence_thickness_max=400.0,
                 anisotropy_strength=0.0, anisotropy_rotation=0.0,
                 dispersion=0.0, **kw):
        super().__init__(name=name, base_color=base_color, **kw)
        self.kind = 'pbr'
        self.metallic = _clamp01(metallic)
        self.roughness = _clamp01(roughness)
        self.ior = float(ior)
        self.specular_factor = float(specular_factor)
        self.specular_color = _vec3(specular_color)
        self.occlusion_strength = 1.0
        # Clearcoat (KHR_materials_clearcoat)
        self.clearcoat = _clamp01(clearcoat)
        self.clearcoat_roughness = _clamp01(clearcoat_roughness)
        self.clearcoat_normal_texture = None
        # Sheen (KHR_materials_sheen)
        self.sheen_color = _vec3(sheen_color, (0.0, 0.0, 0.0))
        self.sheen_roughness = _clamp01(sheen_roughness)
        self.sheen_color_texture = None
        self.sheen_roughness_texture = None
        # Transmission + Volume (KHR_materials_transmission / volume)
        self.transmission = _clamp01(transmission)
        self.thickness = float(thickness)
        self.attenuation_color = _vec3(attenuation_color)
        try:
            self.attenuation_distance = float(attenuation_distance)
        except Exception:
            self.attenuation_distance = float('inf')
        self.transmission_texture = None
        self.thickness_texture = None
        self.attenuation_texture = None
        # Iridescence (KHR_materials_iridescence)
        self.iridescence = _clamp01(iridescence)
        self.iridescence_ior = float(iridescence_ior)
        self.iridescence_thickness_min = float(iridescence_thickness_min)
        self.iridescence_thickness_max = float(iridescence_thickness_max)
        self.iridescence_texture = None
        self.iridescence_thickness_texture = None
        # Anisotropy (KHR_materials_anisotropy)
        self.anisotropy_strength = _clamp01(anisotropy_strength)
        self.anisotropy_rotation = float(anisotropy_rotation)
        self.anisotropy_texture = None
        # Dispersion (KHR_materials_dispersion)
        self.dispersion = float(dispersion)

    def f0(self):
        """Dielectric F0 from IOR, mixed with specularColor, then metal."""
        f0_diel = ((self.ior - 1.0) / (self.ior + 1.0)) ** 2
        # specularColor * specularFactor * f0_diel for dielectric
        f0 = tuple(sc * self.specular_factor * f0_diel for sc in self.specular_color)
        return tuple(c * self.metallic + f * (1.0 - self.metallic) for c, f in zip(self.base_color, f0))

    def to_uniforms(self):
        u = super().to_uniforms()
        u.update({
            'u_metallic': self.metallic, 'u_roughness': self.roughness,
            'u_ior': self.ior,
            'u_specularFactor': self.specular_factor,
            'u_specularColor': (self.specular_color[0], self.specular_color[1], self.specular_color[2], 1.0),
            'u_occlusionStrength': self.occlusion_strength,
            'u_clearcoat': self.clearcoat, 'u_clearcoatRoughness': self.clearcoat_roughness,
            'u_sheenColor': (self.sheen_color[0], self.sheen_color[1], self.sheen_color[2], 1.0),
            'u_sheenRoughness': self.sheen_roughness,
            'u_transmission': self.transmission, 'u_thickness': self.thickness,
            'u_attenuationColor': (self.attenuation_color[0], self.attenuation_color[1], self.attenuation_color[2], 1.0),
            'u_attenuationDistance': self.attenuation_distance if self.attenuation_distance == self.attenuation_distance and abs(self.attenuation_distance) != float('inf') else 1e9,
            'u_iridescence': self.iridescence, 'u_iridescenceIor': self.iridescence_ior,
            'u_iridescenceThicknessMin': self.iridescence_thickness_min,
            'u_iridescenceThicknessMax': self.iridescence_thickness_max,
            'u_anisotropyStrength': self.anisotropy_strength,
            'u_anisotropyRotation': self.anisotropy_rotation,
            'u_dispersion': self.dispersion,
        })
        return u

    def describe(self):
        d = super().describe()
        d.update({'metallic': self.metallic, 'roughness': self.roughness, 'ior': self.ior,
                  'specular_factor': self.specular_factor, 'specular_color': list(self.specular_color),
                  'clearcoat': self.clearcoat, 'clearcoat_roughness': self.clearcoat_roughness,
                  'sheen_color': list(self.sheen_color), 'sheen_roughness': self.sheen_roughness,
                  'transmission': self.transmission, 'thickness': self.thickness,
                  'attenuation_color': list(self.attenuation_color),
                  'attenuation_distance': self.attenuation_distance,
                  'iridescence': self.iridescence, 'iridescence_ior': self.iridescence_ior,
                  'anisotropy_strength': self.anisotropy_strength, 'dispersion': self.dispersion})
        return d

class UnlitMaterial(Material):
    def __init__(self, name='', base_color=(1.0, 1.0, 1.0), **kw):
        super().__init__(name=name, base_color=base_color, **kw)
        self.kind = 'unlit'
        self.unlit = True

class SplatMaterial(Material):
    MODE_CAPTURED = 'captured-radiance'
    MODE_RELIGHTABLE = 'relightable-material'
    MODE_ARTISTIC = 'artistic-adjustment'
    def __init__(self, name='', mode='captured-radiance', sh_degree=0, lighting=None, **kw):
        super().__init__(name=name, **kw)
        self.kind = 'splat'
        self.mode = str(mode)
        self.sh_degree = int(sh_degree)
        self.lighting = lighting or ('pbr+prt' if 'relightable' in self.mode else 'captured')
    def to_uniforms(self):
        u = super().to_uniforms()
        u.update({'u_splatMode': 1.0 if 'relightable' in self.mode else 0.0})
        return u

def material_from_color(color, name=''):
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        vals = [float(c) for c in color[:3]]
        if max(vals) > 1.0:
            vals = [v / 255.0 for v in vals]
        return UnlitMaterial(name=name, base_color=tuple(vals))
    s = str(color or '').strip().lower()
    _named = {'black': (0,0,0), 'white': (1,1,1), 'red': (1,0,0), 'green': (0,0.5,0),
              'blue': (0,0,1), 'yellow': (1,1,0), 'cyan': (0,1,1), 'magenta': (1,0,1),
              'orange': (1,0.65,0), 'gray': (0.5,0.5,0.5), 'grey': (0.5,0.5,0.5),
              'gold': (1,0.84,0), 'dodgerblue': (0.12,0.56,1.0)}
    if s in _named:
        return UnlitMaterial(name=name or s, base_color=_named[s])
    if s.startswith('#') and len(s) in (4, 7):
        h = s[1:]
        if len(h) == 3:
            h = ''.join(c*2 for c in h)
        return UnlitMaterial(name=name or s, base_color=(int(h[0:2],16)/255.0, int(h[2:4],16)/255.0, int(h[4:6],16)/255.0))
    return UnlitMaterial(name=name, base_color=(0.0,0.0,1.0))

def material_from_gltf(jmat, name='', textures=None):
    """glTF material JSON -> PBRMaterial, every KHR extension."""
    jmat = jmat or {}
    pbr = jmat.get('pbrMetallicRoughness') or {}
    base = _vec4(pbr.get('baseColorFactor'), (1.0,1.0,1.0,1.0))
    ext = jmat.get('extensions') or {}
    # IOR / specular / etc. are in extensions
    ior = 1.5
    if isinstance(ext.get('KHR_materials_ior'), dict):
        ior = float(ext['KHR_materials_ior'].get('ior', 1.5))
    spec_f, spec_c = 1.0, (1.0,1.0,1.0)
    if isinstance(ext.get('KHR_materials_specular'), dict):
        se = ext['KHR_materials_specular']
        spec_f = float(se.get('specularFactor', 1.0))
        spec_c = _vec3(se.get('specularColorFactor'), (1.0,1.0,1.0))
    mat = PBRMaterial(
        name=jmat.get('name') or name,
        base_color=base[:3], alpha=base[3],
        metallic=float(pbr.get('metallicFactor', 1.0)),
        roughness=float(pbr.get('roughnessFactor', 1.0)),
        double_sided=bool(jmat.get('doubleSided', False)),
        alpha_mode=jmat.get('alphaMode', 'OPAQUE'),
        alpha_cutoff=float(jmat.get('alphaCutoff', 0.5)),
        emissive=_vec3(jmat.get('emissiveFactor'), (0.0,0.0,0.0)),
        ior=ior, specular_factor=spec_f, specular_color=spec_c,
    )
    # emissiveStrength
    if isinstance(ext.get('KHR_materials_emissive_strength'), dict):
        mat.emissive_strength = float(ext['KHR_materials_emissive_strength'].get('emissiveStrength', 1.0))
    # unlit
    if 'KHR_materials_unlit' in ext:
        mat.unlit = True
        mat.kind = 'unlit'
    # clearcoat
    if isinstance(ext.get('KHR_materials_clearcoat'), dict):
        cc = ext['KHR_materials_clearcoat']
        mat.clearcoat = float(cc.get('clearcoatFactor', 0.0))
        mat.clearcoat_roughness = float(cc.get('clearcoatRoughnessFactor', 0.0))
        if isinstance(cc.get('clearcoatNormalTexture'), dict):
            mat.clearcoat_normal_texture = _tex_info(cc['clearcoatNormalTexture'])
    # sheen
    if isinstance(ext.get('KHR_materials_sheen'), dict):
        sh = ext['KHR_materials_sheen']
        mat.sheen_color = _vec3(sh.get('sheenColorFactor'), (0.0,0.0,0.0))
        mat.sheen_roughness = float(sh.get('sheenRoughnessFactor', 0.5))
        if isinstance(sh.get('sheenColorTexture'), dict):
            mat.sheen_color_texture = _tex_info(sh['sheenColorTexture'])
        if isinstance(sh.get('sheenRoughnessTexture'), dict):
            mat.sheen_roughness_texture = _tex_info(sh['sheenRoughnessTexture'])
    # transmission + volume
    if isinstance(ext.get('KHR_materials_transmission'), dict):
        tr = ext['KHR_materials_transmission']
        mat.transmission = float(tr.get('transmissionFactor', 0.0))
        if isinstance(tr.get('transmissionTexture'), dict):
            mat.transmission_texture = _tex_info(tr['transmissionTexture'])
    if isinstance(ext.get('KHR_materials_volume'), dict):
        vo = ext['KHR_materials_volume']
        mat.thickness = float(vo.get('thicknessFactor', 0.0))
        mat.attenuation_color = _vec3(vo.get('attenuationColor'), (1.0,1.0,1.0))
        mat.attenuation_distance = float(vo.get('attenuationDistance', float('inf')))
        if isinstance(vo.get('thicknessTexture'), dict):
            mat.thickness_texture = _tex_info(vo['thicknessTexture'])
    # iridescence
    if isinstance(ext.get('KHR_materials_iridescence'), dict):
        ir = ext['KHR_materials_iridescence']
        mat.iridescence = float(ir.get('iridescenceFactor', 0.0))
        mat.iridescence_ior = float(ir.get('iridescenceIor', 1.3))
        mat.iridescence_thickness_min = float(ir.get('iridescenceThicknessMinimum', 100.0))
        mat.iridescence_thickness_max = float(ir.get('iridescenceThicknessMaximum', 400.0))
    # anisotropy
    if isinstance(ext.get('KHR_materials_anisotropy'), dict):
        an = ext['KHR_materials_anisotropy']
        mat.anisotropy_strength = float(an.get('anisotropyStrength', 0.0))
        mat.anisotropy_rotation = float(an.get('anisotropyRotation', 0.0))
    # dispersion
    if isinstance(ext.get('KHR_materials_dispersion'), dict):
        mat.dispersion = float(ext['KHR_materials_dispersion'].get('dispersion', 0.0))
    # base textures
    if isinstance(pbr.get('baseColorTexture'), dict):
        mat.base_color_texture = _tex_info(pbr['baseColorTexture'])
    if isinstance(pbr.get('metallicRoughnessTexture'), dict):
        mat.metallic_roughness_texture = _tex_info(pbr['metallicRoughnessTexture'])
    if isinstance(jmat.get('normalTexture'), dict):
        mat.normal_texture = _tex_info(jmat['normalTexture'])
        mat.normal_scale = float(jmat['normalTexture'].get('scale', 1.0))
    if isinstance(jmat.get('occlusionTexture'), dict):
        mat.occlusion_texture = _tex_info(jmat['occlusionTexture'])
        mat.occlusion_strength = float(jmat['occlusionTexture'].get('strength', 1.0))
    if isinstance(jmat.get('emissiveTexture'), dict):
        mat.emissive_texture = _tex_info(jmat['emissiveTexture'])
    # variants
    if isinstance(ext.get('KHR_materials_variants'), dict):
        for v in ext['KHR_materials_variants'].get('variants', []):
            if isinstance(v, dict) and 'name' in v:
                mat.variants[v['name']] = v
    return mat

class MaterialLibrary:
    def __init__(self):
        self._by_name = {}
        self._list = []
    def add(self, mat):
        if mat.name and mat.name in self._by_name:
            return self._by_name[mat.name]
        self._by_name[mat.name] = mat
        self._list.append(mat)
        return mat
    def get(self, name, default=None):
        return self._by_name.get(name, default)
    def from_gltf_materials(self, jmaterials):
        out = []
        for i, jm in enumerate(jmaterials or []):
            out.append(self.add(material_from_gltf(jm, name='mat%d' % i)))
        return out
    def describe(self):
        return [m.describe() for m in self._list]
    def __len__(self):
        return len(self._list)
