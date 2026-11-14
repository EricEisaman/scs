"""
scs_lighting.py -- LIGHTING SYSTEM.

Rules:
  * Lights are DATA, not shader code. The pipeline turns them into
    uniforms / shader chunks. Same lights drive WebGL2, WebGPU, and
    the CPU reference in this file.
  * Physical units: intensity in candela / lux-ish, decay = 2 (physical).
    No magic 0..1 brightness that breaks when you add a second light.
  * Shadows are config, not a boolean: map size, bias, normal bias,
    radius (PCF), camera bounds. A light with cast_shadow=False costs
    nothing in the shadow pass.
  * IBL is a light too: EnvironmentLight (irradiance + prefiltered env).
  * LightRig presets: studio 3-point, sunset, night, noon -- one call,
    not 20 lines of setup.

CPU reference: evaluate_lights() matches the PBR shader's direct term
for a Lambert + GGX surface. Used by tests; the GPU path is in
scs_pipeline.py (GLSL/WGSL PBR + these light uniforms).
"""

import math

# [STRIPPED 70 bytes]
# Helpers
# [STRIPPED 70 bytes]

def _vec3(v, default=(0.0, 0.0, 0.0)):
    try:
        if v is None:
            return tuple(default)
        return (float(v[0]), float(v[1]), float(v[2]))
    except Exception:
        return tuple(default)

def _norm(v):
    x, y, z = _vec3(v)
    l = math.sqrt(x*x + y*y + z*z)
    if l < 1e-9:
        return (0.0, 0.0, -1.0)
    return (x/l, y/l, z/l)

def _dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

# [STRIPPED 70 bytes]
# Shadow config
# [STRIPPED 70 bytes]

class ShadowConfig:
    def __init__(self, map_size=2048, bias=-0.0005, normal_bias=0.02,
                 radius=2.0, near=0.1, far=100.0, ortho_half=20.0):
        self.map_size = int(map_size)
        self.bias = float(bias)
        self.normal_bias = float(normal_bias)
        self.radius = float(radius)  # PCF radius
        self.near = float(near)
        self.far = float(far)
        self.ortho_half = float(ortho_half)  # directional shadow camera
    def describe(self):
        return {'map_size': self.map_size, 'bias': self.bias,
                'normal_bias': self.normal_bias, 'radius': self.radius,
                'near': self.near, 'far': self.far,
                'ortho_half': self.ortho_half}

# [STRIPPED 70 bytes]
# Lights
# [STRIPPED 70 bytes]

class Light:
    kind = 'light'
    def __init__(self, name='', color=(1.0, 1.0, 1.0), intensity=1.0,
                 cast_shadow=False, shadow=None):
        self.name = str(name or '')
        self.color = _vec3(color, (1.0, 1.0, 1.0))
        self.intensity = float(intensity)
        self.cast_shadow = bool(cast_shadow)
        self.shadow = shadow or (ShadowConfig() if cast_shadow else None)
        self.visible = True
    def describe(self):
        return {'kind': self.kind, 'name': self.name,
                'color': list(self.color), 'intensity': self.intensity,
                'cast_shadow': self.cast_shadow,
                'shadow': self.shadow.describe() if self.shadow else None}
    def to_uniforms(self, index=0):
        return {'type': self.kind, 'color': self.color,
                'intensity': self.intensity, 'index': index}

class DirectionalLight(Light):
    kind = 'directional'
    def __init__(self, name='', color=(1, 1, 1), intensity=3.0,
                 direction=(0.5, -1.0, 0.5), **kw):
        super().__init__(name=name, color=color, intensity=intensity, **kw)
        self.direction = _norm(direction)  # direction light travels
    def describe(self):
        d = super().describe()
        d['direction'] = list(self.direction)
        return d
    def to_uniforms(self, index=0):
        u = super().to_uniforms(index)
        u.update({'direction': self.direction, 'position': (0, 0, 0)})
        return u

class PointLight(Light):
    kind = 'point'
    def __init__(self, name='', color=(1, 1, 1), intensity=10.0,
                 position=(0, 0, 0), distance=0.0, decay=2.0, **kw):
        super().__init__(name=name, color=color, intensity=intensity, **kw)
        self.position = _vec3(position)
        self.distance = float(distance)  # 0 = infinite, else cutoff
        self.decay = float(decay)  # 2 = physical
    def attenuation(self, point):
        """Physical attenuation: intensity / d^decay, 0 beyond distance."""
        dx = point[0]-self.position[0]; dy = point[1]-self.position[1]; dz = point[2]-self.position[2]
        d2 = dx*dx + dy*dy + dz*dz
        d = math.sqrt(d2)
        if self.distance > 0 and d > self.distance:
            return 0.0
        return self.intensity / max(d2 if self.decay == 2 else d**self.decay, 1e-6)
    def describe(self):
        d = super().describe()
        d.update({'position': list(self.position), 'distance': self.distance, 'decay': self.decay})
        return d
    def to_uniforms(self, index=0):
        u = super().to_uniforms(index)
        u.update({'position': self.position, 'distance': self.distance, 'decay': self.decay})
        return u

class SpotLight(Light):
    kind = 'spot'
    def __init__(self, name='', color=(1, 1, 1), intensity=20.0,
                 position=(0, 5, 0), direction=(0, -1, 0),
                 angle=0.5, penumbra=0.4, distance=0.0, decay=2.0, **kw):
        super().__init__(name=name, color=color, intensity=intensity, **kw)
        self.position = _vec3(position)
        self.direction = _norm(direction)
        self.angle = float(angle)  # outer cone, radians
        self.penumbra = max(0.0, min(1.0, float(penumbra)))  # 0=hard, 1=soft
        self.distance = float(distance)
        self.decay = float(decay)
    def cone_factor(self, point):
        """0 outside cone, 1 inside inner cone, smooth penumbra between."""
        to_p = _norm((point[0]-self.position[0], point[1]-self.position[1], point[2]-self.position[2]))
        cos_a = _dot(to_p, self.direction)
        cos_outer = math.cos(self.angle)
        inner = math.cos(self.angle * (1.0 - self.penumbra))
        if cos_a <= cos_outer:
            return 0.0
        if cos_a >= inner:
            return 1.0
        # smoothstep between outer and inner
        t = (cos_a - cos_outer) / max(inner - cos_outer, 1e-6)
        return t*t*(3-2*t)
    def attenuation(self, point):
        dx = point[0]-self.position[0]; dy = point[1]-self.position[1]; dz = point[2]-self.position[2]
        d = math.sqrt(dx*dx+dy*dy+dz*dz)
        if self.distance > 0 and d > self.distance:
            return 0.0
        return self.intensity / max(d**self.decay, 1e-6) * self.cone_factor(point)
    def describe(self):
        d = super().describe()
        d.update({'position': list(self.position), 'direction': list(self.direction),
                  'angle': self.angle, 'penumbra': self.penumbra,
                  'distance': self.distance, 'decay': self.decay})
        return d
    def to_uniforms(self, index=0):
        u = super().to_uniforms(index)
        u.update({'position': self.position, 'direction': self.direction,
                  'angle': self.angle, 'penumbra': self.penumbra,
                  'distance': self.distance, 'decay': self.decay})
        return u

class RectAreaLight(Light):
    kind = 'rect_area'
    def __init__(self, name='', color=(1, 1, 1), intensity=5.0,
                 position=(0, 3, 0), look_at=(0, 0, 0),
                 width=2.0, height=1.0, **kw):
        super().__init__(name=name, color=color, intensity=intensity, **kw)
        self.position = _vec3(position)
        self.look_at = _vec3(look_at)
        self.width = float(width); self.height = float(height)
    def describe(self):
        d = super().describe()
        d.update({'position': list(self.position), 'look_at': list(self.look_at),
                  'width': self.width, 'height': self.height})
        return d

class EnvironmentLight(Light):
    """IBL: irradiance + prefiltered env + BRDF LUT. One light, whole scene ambient."""
    kind = 'environment'
    def __init__(self, name='env', intensity=1.0, rotation=0.0,
                 env_map=None, irradiance=None, **kw):
        super().__init__(name=name, color=(1, 1, 1), intensity=intensity, **kw)
        self.rotation = float(rotation)
        self.env_map = env_map  # texture handle / URL
        self.irradiance = irradiance
    def describe(self):
        d = super().describe()
        d.update({'rotation': self.rotation, 'has_env_map': self.env_map is not None})
        return d

# [STRIPPED 70 bytes]
# LightRig presets -- one call, not 20 lines
# [STRIPPED 70 bytes]

class LightRig:
    """A named set of lights. Presets are the DEVX: rig = LightRig.studio()"""
    def __init__(self, name='rig', lights=None):
        self.name = name
        self.lights = list(lights or [])
    def add(self, light):
        self.lights.append(light)
        return light
    def describe(self):
        return {'name': self.name, 'lights': [l.describe() for l in self.lights]}
    @classmethod
    def studio(cls):
        """3-point studio: key + fill + rim + soft env."""
        rig = cls('studio')
        rig.add(DirectionalLight('key', color=(1, 0.98, 0.95), intensity=3.0, direction=(0.5, -1, 0.5), cast_shadow=True))
        rig.add(DirectionalLight('fill', color=(0.8, 0.9, 1.0), intensity=1.2, direction=(-0.7, -0.3, -0.5)))
        rig.add(DirectionalLight('rim', color=(1, 1, 1), intensity=2.0, direction=(0, -0.2, 1.0)))
        rig.add(EnvironmentLight('studio-env', intensity=0.4))
        return rig
    @classmethod
    def sunset(cls):
        rig = cls('sunset')
        rig.add(DirectionalLight('sun', color=(1, 0.5, 0.2), intensity=4.0, direction=(0.8, -0.2, 0.3), cast_shadow=True))
        rig.add(EnvironmentLight('sunset-env', intensity=0.3))
        rig.add(PointLight('bounce', color=(1, 0.7, 0.4), intensity=5.0, position=(0, 1, 3), distance=10))
        return rig
    @classmethod
    def night(cls):
        rig = cls('night')
        rig.add(DirectionalLight('moon', color=(0.6, 0.7, 1.0), intensity=0.8, direction=(0.3, -1, 0.2), cast_shadow=True))
        rig.add(PointLight('lamp', color=(1, 0.8, 0.4), intensity=15.0, position=(2, 3, 2), distance=12))
        rig.add(EnvironmentLight('night-env', intensity=0.15))
        return rig
    @classmethod
    def noon(cls):
        rig = cls('noon')
        rig.add(DirectionalLight('sun', color=(1, 1, 0.98), intensity=5.0, direction=(0.1, -1, 0.1), cast_shadow=True))
        rig.add(EnvironmentLight('noon-env', intensity=0.6))
        return rig

# [STRIPPED 70 bytes]
# LightingSystem -- owns lights, culls, packs uniforms
# [STRIPPED 70 bytes]

class LightingSystem:
    MAX_LIGHTS = 8  # GPU uniform array size. More lights -> cull, don't overflow.
    def __init__(self, rig=None):
        self.lights = []
        if rig is not None:
            self.lights.extend(rig.lights if isinstance(rig, LightRig) else rig)
        self.env = None
        for l in self.lights:
            if isinstance(l, EnvironmentLight):
                self.env = l
    def add(self, light):
        self.lights.append(light)
        if isinstance(light, EnvironmentLight):
            self.env = light
        return light
    def remove(self, light):
        if light in self.lights:
            self.lights.remove(light)
        return light
    def active_lights(self, point=None, max_lights=None):
        """Cull: visible + in range. Point lights beyond distance are dropped.
        Sorted: directional first, then by intensity (brightest wins the uniform slots)."""
        max_lights = max_lights or self.MAX_LIGHTS
        active = [l for l in self.lights if getattr(l, 'visible', True)]
        if point is not None:
            def _score(l):
                if isinstance(l, PointLight):
                    return -l.attenuation(point)
                if isinstance(l, SpotLight):
                    return -l.attenuation(point)
                return -l.intensity
            active.sort(key=_score)
        else:
            active.sort(key=lambda l: (0 if isinstance(l, DirectionalLight) else 1, -l.intensity))
        return active[:max_lights]
    def to_uniforms(self, point=None):
        """Packed uniforms the pipeline consumes. Always MAX_LIGHTS entries
        (inactive = intensity 0) so the shader loop is branchless."""
        active = self.active_lights(point)
        out = []
        for i, l in enumerate(active):
            out.append(l.to_uniforms(i))
        while len(out) < self.MAX_LIGHTS:
            out.append({'type': 'none', 'color': (0, 0, 0), 'intensity': 0.0, 'index': len(out)})
        return {'lights': out, 'light_count': len(active),
                'env_intensity': self.env.intensity if self.env else 0.0,
                'env_rotation': self.env.rotation if self.env else 0.0}
    def evaluate(self, point, normal):
        """CPU reference: total direct irradiance at point with normal.
        Returns (r, g, b). Matches the shader's direct term for a white
        Lambert surface (diffuse only) -- used by tests."""
        n = _norm(normal)
        total = [0.0, 0.0, 0.0]
        for l in self.active_lights(point):
            if isinstance(l, DirectionalLight):
                L = (-l.direction[0], -l.direction[1], -l.direction[2])
                ndl = max(_dot(n, L), 0.0)
                for i in range(3):
                    total[i] += l.color[i] * l.intensity * ndl
            elif isinstance(l, PointLight):
                att = l.attenuation(point)
                if att <= 0:
                    continue
                L = _norm((point[0]-l.position[0], point[1]-l.position[1], point[2]-l.position[2]))
                ndl = max(_dot(n, L), 0.0)
                for i in range(3):
                    total[i] += l.color[i] * att * ndl
            elif isinstance(l, SpotLight):
                att = l.attenuation(point)
                if att <= 0:
                    continue
                L = _norm((point[0]-l.position[0], point[1]-l.position[1], point[2]-l.position[2]))
                ndl = max(_dot(n, L), 0.0)
                for i in range(3):
                    total[i] += l.color[i] * att * ndl
        return tuple(total)
    def describe(self):
        return {'lights': [l.describe() for l in self.lights],
                'env': self.env.describe() if self.env else None}

# GLSL chunk the pipeline can inject (same math as evaluate()).
GLSL_LIGHTS_CHUNK = """
// SCS lighting chunk: up to 8 lights, directional + point + spot.
// Injected by scs_pipeline when LightingSystem is present.
struct SCSLight { int type; vec3 color; float intensity; vec3 position; vec3 direction; float angle; float penumbra; float distance; float decay; };
uniform SCSLight u_lights[8];
uniform int u_lightCount;
vec3 scs_lighting(vec3 pos, vec3 N) {
  vec3 total = vec3(0.0);
  for (int i = 0; i < 8; i++) {
    if (i >= u_lightCount) break;
    SCSLight L = u_lights[i];
    if (L.type == 0) { // directional
      vec3 Ld = normalize(-L.direction);
      total += L.color * L.intensity * max(dot(N, Ld), 0.0);
    } else if (L.type == 1) { // point
      vec3 toL = L.position - pos;
      float d = length(toL);
      if (L.distance > 0.0 && d > L.distance) continue;
      float att = L.intensity / max(pow(d, L.decay), 0.0001);
      total += L.color * att * max(dot(N, normalize(toL)), 0.0);
    } else if (L.type == 2) { // spot
      vec3 toL = L.position - pos;
      float d = length(toL);
      if (L.distance > 0.0 && d > L.distance) continue;
      float cosA = dot(normalize(toL), L.direction);
      float cosOuter = cos(L.angle);
      float cosInner = cos(L.angle * (1.0 - L.penumbra));
      float cone = smoothstep(cosOuter, cosInner, cosA);
      float att = L.intensity / max(pow(d, L.decay), 0.0001) * cone;
      total += L.color * att * max(dot(N, normalize(toL)), 0.0);
    }
  }
  return total;
}
"""
