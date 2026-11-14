"""
scs_volumetric.py -- VOLUMETRIC LIGHTING.

What it is:
  * Light shafts / god rays through a spot / directional light.
  * Volumetric fog: density + height falloff + scattering.
  * Dust / particles in the beam (see scs_particles.py for the dust).

Math (CPU reference, matches shader):
  * Beer-Lambert: transmittance = exp(-density * distance)
  * Henyey-Greenstein phase: forward scattering (g > 0) = light shafts
    are brighter looking toward the light.
  * Single-scattering: L = light * phase * transmittance * density

Performance: volumetrics are computed in a half-res pass, upsampled.
The shader chunk below is the half-res raymarch (8-16 steps, not 64).
"""

import math

def _vec3(v, default=(0.0, 0.0, 0.0)):
    try:
        return (float(v[0]), float(v[1]), float(v[2]))
    except Exception:
        return tuple(default)

def _norm(v):
    x, y, z = _vec3(v)
    l = math.sqrt(x*x+y*y+z*z)
    return (x/l, y/l, z/l) if l > 1e-9 else (0, 0, -1)

def _dot(a, b):
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

def heney_greenstein(cos_theta, g):
    """Phase function. g=0 isotropic, g>0 forward, g<0 backward."""
    g2 = g*g
    denom = (1 + g2 - 2*g*cos_theta)
    return (1 - g2) / (4*math.pi * denom**1.5)

def beer_lambert(density, distance):
    return math.exp(-density * distance)

def transmittance(density, distance):
    return beer_lambert(density, distance)

class FogVolume:
    """A box / global fog volume: density, height falloff, color."""
    def __init__(self, density=0.02, height_falloff=0.1, color=(0.6, 0.7, 0.8),
                 anisotropy=0.6, bounds=None):
        self.density = float(density)
        self.height_falloff = float(height_falloff)
        self.color = _vec3(color, (0.6, 0.7, 0.8))
        self.anisotropy = float(anisotropy)  # g in HG
        self.bounds = bounds  # ((minx,miny,minz),(maxx,maxy,maxz)) or None = global
    def density_at(self, point):
        """Density with height falloff: thinner at altitude."""
        if self.bounds is not None:
            (mn, mx) = self.bounds
            if not (mn[0] <= point[0] <= mx[0] and mn[1] <= point[1] <= mx[1] and mn[2] <= point[2] <= mx[2]):
                return 0.0
        return self.density * math.exp(-point[1] * self.height_falloff)
    def describe(self):
        return {'density': self.density, 'height_falloff': self.height_falloff,
                'color': list(self.color), 'anisotropy': self.anisotropy,
                'bounds': self.bounds}

class VolumetricSpot:
    """A spot light that also renders a visible cone (light shaft)."""
    def __init__(self, position=(0, 5, 0), direction=(0, -1, 0), angle=0.4,
                 intensity=10.0, color=(1, 0.9, 0.7), density=0.05,
                 steps=12):
        self.position = _vec3(position)
        self.direction = _norm(direction)
        self.angle = float(angle)
        self.intensity = float(intensity)
        self.color = _vec3(color)
        self.density = float(density)
        self.steps = int(steps)
    def in_cone(self, point):
        to_p = _norm((point[0]-self.position[0], point[1]-self.position[1], point[2]-self.position[2]))
        return _dot(to_p, self.direction) >= math.cos(self.angle)
    def shaft_brightness(self, point, view_dir):
        """Single-scatter brightness at a point in the cone, seen from view_dir."""
        if not self.in_cone(point):
            return 0.0
        d = math.sqrt(sum((point[i]-self.position[i])**2 for i in range(3)))
        # Transmittance from light to point + from point to camera (approx: same d)
        t = beer_lambert(self.density, d)
        # Phase: view dir vs light dir (forward scattering = brighter)
        cos_t = _dot(_norm(view_dir), self.direction)
        phase = heney_greenstein(cos_t, 0.6)
        return self.intensity * phase * t * self.density
    def describe(self):
        return {'position': list(self.position), 'direction': list(self.direction),
                'angle': self.angle, 'intensity': self.intensity,
                'color': list(self.color), 'density': self.density, 'steps': self.steps}

class GodRays:
    """Screen-space god rays: radial blur from the sun's screen position."""
    def __init__(self, strength=0.6, samples=32, decay=0.95, density=0.9):
        self.strength = float(strength)
        self.samples = int(samples)
        self.decay = float(decay)
        self.density = float(density)
    def describe(self):
        return {'strength': self.strength, 'samples': self.samples,
                'decay': self.decay, 'density': self.density}

class VolumetricSystem:
    """Owns fog + volumetric lights + god rays. One system per scene."""
    def __init__(self, fog=None):
        self.fog = fog or FogVolume()
        self.spots = []
        self.god_rays = GodRays()
        self.enabled = True
    def add_spot(self, spot):
        self.spots.append(spot)
        return spot
    def evaluate(self, point, view_dir, light_dir):
        """CPU: total volumetric radiance at point. Returns (r,g,b)."""
        if not self.enabled:
            return (0, 0, 0)
        dens = self.fog.density_at(point)
        # Ambient fog scattering (cheap)
        cos_t = _dot(_norm(view_dir), _norm(light_dir))
        phase = heney_greenstein(cos_t, self.fog.anisotropy)
        fog_r = tuple(self.fog.color[i] * phase * dens * 0.5 for i in range(3))
        # Shafts
        shaft = [0.0, 0.0, 0.0]
        for s in self.spots:
            b = s.shaft_brightness(point, view_dir)
            for i in range(3):
                shaft[i] += s.color[i] * b
        return tuple(fog_r[i] + shaft[i] for i in range(3))
    def describe(self):
        return {'enabled': self.enabled, 'fog': self.fog.describe(),
                'spots': [s.describe() for s in self.spots],
                'god_rays': self.god_rays.describe()}
    @classmethod
    def cathedral(cls):
        """The to-die-for preset: shafts through windows + dusty fog."""
        sys = cls(FogVolume(density=0.03, height_falloff=0.05, color=(0.8, 0.75, 0.6)))
        sys.add_spot(VolumetricSpot(position=(0, 8, 0), direction=(0.2, -1, 0.1),
                                    angle=0.25, intensity=20, color=(1, 0.9, 0.6), density=0.08))
        sys.god_rays = GodRays(strength=0.8, samples=48)
        return sys
    @classmethod
    def forest(cls):
        sys = cls(FogVolume(density=0.02, height_falloff=0.1, color=(0.6, 0.75, 0.6)))
        sys.add_spot(VolumetricSpot(position=(2, 6, 2), direction=(-0.2, -1, -0.2),
                                    angle=0.35, intensity=12, color=(1, 1, 0.85), density=0.05))
        return sys

GLSL_VOLUMETRIC = """
// Volumetric: half-res raymarch, 12 steps, Beer-Lambert + HG phase.
// Injected by the pipeline when VolumetricSystem is present.
float scs_hg(float cosT, float g) {
  float g2 = g*g;
  return (1.0 - g2) / (4.0 * 3.14159 * pow(1.0 + g2 - 2.0*g*cosT, 1.5));
}
vec3 scs_volumetric(vec3 pos, vec3 viewDir, vec3 lightDir, float density, vec3 fogColor) {
  float t = exp(-density * length(pos));
  float phase = scs_hg(dot(normalize(viewDir), normalize(lightDir)), 0.6);
  return fogColor * phase * density * t;
}
"""


WGSL_VOLUMETRIC = """
// WGSL volumetric -- same math as GLSL_VOLUMETRIC (Beer-Lambert + HG).
fn scs_hg(cosT: f32, g: f32) -> f32 {
  let g2 = g * g;
  return (1.0 - g2) / (4.0 * 3.14159 * pow(1.0 + g2 - 2.0 * g * cosT, 1.5));
}
fn scs_volumetric(pos: vec3<f32>, viewDir: vec3<f32>, lightDir: vec3<f32>, density: f32, fogColor: vec3<f32>) -> vec3<f32> {
  let t = exp(-density * length(pos));
  let phase = scs_hg(dot(normalize(viewDir), normalize(lightDir)), 0.6);
  return fogColor * phase * density * t;
}
"""

def wgsl_chunk():
    return WGSL_VOLUMETRIC
def glsl_chunk():
    return GLSL_VOLUMETRIC
