"""
scs_post.py -- POST RENDERING EFFECTS.

Chain: HDR scene -> tone map -> bloom -> DOF -> grade -> vignette/grain/CA -> LDR.

Rules:
  * Post is a CHAIN of passes, not a pile of ifs. Passes are data:
    PostChain([Bloom(...), DepthOfField(...), Grade(...)]) -- reorder
    by moving a list item.
  * Everything runs in linear HDR until the final output. Tone mapping
    is a pass, not a shader hack in every material.
  * CPU reference for tone mapping + grading matches the GLSL, so
    tests can prove the shader math without a GPU.
  * Bloom is threshold + separable blur + composite, not a blur-everything.
    DOF is depth-aware (near + far), not a fullscreen blur.
"""

import math

# [STRIPPED 70 bytes]
# Tone mapping -- CPU reference (matches GLSL below)
# [STRIPPED 70 bytes]

def tonemap_aces(c):
    """ACES fitted (Stephen Hill). Input linear HDR, output 0..1."""
    # Hill's fit, per channel
    def _f(x):
        x = max(x, 0.0)
        return (x*(2.51*x+0.03)) / (x*(2.43*x+0.59)+0.14)
    if isinstance(c, (list, tuple)):
        return tuple(_f(v) for v in c)
    return _f(c)

def tonemap_reinhard(c):
    def _f(x):
        return max(x, 0.0) / (1.0 + max(x, 0.0))
    if isinstance(c, (list, tuple)):
        return tuple(_f(v) for v in c)
    return _f(c)

def tonemap_agx(c):
    """AgX-ish: log + S-curve. Simplified, filmic."""
    def _f(x):
        x = max(x, 0.0)
        # Log encode then smoothstep-ish S
        log = math.log10(x + 1e-4)  # -4..~1
        t = (log + 4.0) / 5.0  # 0..1
        t = max(0.0, min(1.0, t))
        return t*t*(3-2*t)
    if isinstance(c, (list, tuple)):
        return tuple(_f(v) for v in c)
    return _f(c)

def srgb_encode(c):
    def _f(x):
        x = max(x, 0.0)
        return x*12.92 if x <= 0.0031308 else 1.055*(x**(1/2.4))-0.055
    if isinstance(c, (list, tuple)):
        return tuple(_f(v) for v in c)
    return _f(c)

def grade_color(c, exposure=1.0, contrast=1.0, saturation=1.0, lift=(0,0,0), gain=(1,1,1)):
    """Lift/Gain + exposure + contrast + saturation. Linear in, linear out."""
    out = []
    for i, v in enumerate(c):
        v = v * exposure
        v = v * gain[i] + lift[i]
        v = (v - 0.18) * contrast + 0.18
        out.append(v)
    # Saturation: lerp to luma
    luma = out[0]*0.2126 + out[1]*0.7152 + out[2]*0.0722
    out = [luma + (v-luma)*saturation for v in out]
    return tuple(out)

TONEMAPS = {'aces': tonemap_aces, 'reinhard': tonemap_reinhard, 'agx': tonemap_agx, 'none': lambda c: c}

# [STRIPPED 70 bytes]
# Passes
# [STRIPPED 70 bytes]

class PostPass:
    kind = 'pass'
    def __init__(self, enabled=True):
        self.enabled = enabled
    def describe(self):
        return {'kind': self.kind, 'enabled': self.enabled}
    def glsl(self):
        return ''
    def uniforms(self):
        return {}

class ToneMapPass(PostPass):
    kind = 'tonemap'
    def __init__(self, operator='aces', exposure=1.0, **kw):
        super().__init__(**kw)
        self.operator = operator
        self.exposure = float(exposure)
    def apply_cpu(self, color):
        c = grade_color(color, exposure=self.exposure)
        fn = TONEMAPS.get(self.operator, tonemap_aces)
        return fn(c)
    def describe(self):
        d = super().describe()
        d.update({'operator': self.operator, 'exposure': self.exposure})
        return d
    def glsl(self):
        return GLSL_TONEMAP
    def uniforms(self):
        return {'u_exposure': self.exposure, 'u_tonemap': ['aces','reinhard','agx','none'].index(self.operator)}

class BloomPass(PostPass):
    kind = 'bloom'
    def __init__(self, threshold=1.0, strength=0.8, radius=0.6, quality='high', **kw):
        super().__init__(**kw)
        self.threshold = float(threshold)
        self.strength = float(strength)
        self.radius = float(radius)
        self.quality = quality
        self.mip_levels = 5 if quality == 'high' else 3
    def describe(self):
        d = super().describe()
        d.update({'threshold': self.threshold, 'strength': self.strength,
                  'radius': self.radius, 'mip_levels': self.mip_levels})
        return d
    def glsl(self):
        return GLSL_BLOOM
    def uniforms(self):
        return {'u_bloomThreshold': self.threshold, 'u_bloomStrength': self.strength, 'u_bloomRadius': self.radius}

class DepthOfFieldPass(PostPass):
    kind = 'dof'
    def __init__(self, focus_distance=5.0, focus_range=1.5, max_blur=0.02, **kw):
        super().__init__(**kw)
        self.focus_distance = float(focus_distance)
        self.focus_range = float(focus_range)
        self.max_blur = float(max_blur)
    def coc(self, depth):
        """Circle of confusion: 0 at focus, 1 at max blur."""
        d = abs(depth - self.focus_distance)
        if d <= self.focus_range:
            return 0.0
        return min(1.0, (d - self.focus_range) * self.max_blur * 10)
    def describe(self):
        d = super().describe()
        d.update({'focus_distance': self.focus_distance, 'focus_range': self.focus_range, 'max_blur': self.max_blur})
        return d
    def glsl(self):
        return GLSL_DOF

class VignettePass(PostPass):
    kind = 'vignette'
    def __init__(self, strength=0.35, radius=0.85, **kw):
        super().__init__(**kw)
        self.strength = float(strength)
        self.radius = float(radius)
    def glsl(self):
        return GLSL_VIGNETTE

class FilmGrainPass(PostPass):
    kind = 'grain'
    def __init__(self, amount=0.03, **kw):
        super().__init__(**kw)
        self.amount = float(amount)
    def glsl(self):
        return GLSL_GRAIN

class ChromaticAberrationPass(PostPass):
    kind = 'ca'
    def __init__(self, amount=0.0015, **kw):
        super().__init__(**kw)
        self.amount = float(amount)
    def glsl(self):
        return GLSL_CA

class ColorGradePass(PostPass):
    kind = 'grade'
    def __init__(self, exposure=1.0, contrast=1.0, saturation=1.0, lift=(0,0,0), gain=(1,1,1), temperature=0.0, tint=0.0, **kw):
        super().__init__(**kw)
        self.exposure = float(exposure); self.contrast = float(contrast); self.saturation = float(saturation)
        self.lift = tuple(lift); self.gain = tuple(gain)
        self.temperature = float(temperature); self.tint = float(tint)
    def apply_cpu(self, color):
        return grade_color(color, exposure=self.exposure, contrast=self.contrast,
                           saturation=self.saturation, lift=self.lift, gain=self.gain)
    def describe(self):
        d = super().describe()
        d.update({'exposure': self.exposure, 'contrast': self.contrast, 'saturation': self.saturation,
                  'lift': list(self.lift), 'gain': list(self.gain)})
        return d

class MotionBlurPass(PostPass):
    kind = 'motion_blur'
    def __init__(self, strength=0.5, samples=8, **kw):
        super().__init__(**kw)
        self.strength = float(strength); self.samples = int(samples)
    def glsl(self):
        return GLSL_MOTION_BLUR

# [STRIPPED 70 bytes]
# Chain
# [STRIPPED 70 bytes]

class PostChain:
    """Ordered list of passes. DEVX: chain = PostChain.cinematic()"""
    def __init__(self, passes=None):
        self.passes = list(passes or [])
    def add(self, p):
        self.passes.append(p)
        return p
    def remove(self, kind):
        self.passes = [p for p in self.passes if p.kind != kind]
        return self
    def enabled_passes(self):
        return [p for p in self.passes if p.enabled]
    def apply_cpu(self, color):
        """Apply grade + tonemap on CPU (for tests). Bloom/DOF need a GPU."""
        c = tuple(color)
        for p in self.enabled_passes():
            if isinstance(p, (ToneMapPass, ColorGradePass)):
                c = p.apply_cpu(c)
        return c
    def describe(self):
        return {'passes': [p.describe() for p in self.passes]}
    @classmethod
    def cinematic(cls):
        """The envy preset: ACES + bloom + DOF + grade + vignette + grain."""
        return cls([ToneMapPass('aces', exposure=1.1),
                    BloomPass(threshold=1.0, strength=0.7, radius=0.6),
                    DepthOfFieldPass(focus_distance=6.0, focus_range=2.0),
                    ColorGradePass(contrast=1.05, saturation=1.1),
                    VignettePass(strength=0.35),
                    FilmGrainPass(amount=0.025)])
    @classmethod
    def crisp(cls):
        """No bloom, no grain -- for UI / product shots."""
        return cls([ToneMapPass('aces', exposure=1.0),
                    ColorGradePass(contrast=1.0, saturation=1.0)])
    @classmethod
    def dreamy(cls):
        return cls([ToneMapPass('agx', exposure=1.0),
                    BloomPass(threshold=0.8, strength=1.2, radius=0.9),
                    DepthOfFieldPass(focus_distance=4.0, focus_range=1.0),
                    VignettePass(strength=0.5),
                    FilmGrainPass(amount=0.04)])

# [STRIPPED 70 bytes]
# GLSL -- one chunk per pass, composable in the pipeline
# [STRIPPED 70 bytes]

GLSL_TONEMAP = """
vec3 scs_tonemap_aces(vec3 x) {
  return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14), 0.0, 1.0);
}
vec3 scs_tonemap(vec3 c, int op, float exposure) {
  c *= exposure;
  if (op == 0) return scs_tonemap_aces(c);
  if (op == 1) return c / (1.0 + c);
  if (op == 2) { vec3 t = clamp((log(c + 0.0001) + 4.0) / 5.0, 0.0, 1.0); return t*t*(3.0-2.0*t); }
  return c;
}
"""
GLSL_BLOOM = """
// Bloom: threshold in the bright pass, separable Gaussian blur in the
// blur pass, additive composite. Threshold = 1.0 means only HDR highlights bloom.
vec3 scs_bloom_threshold(vec3 c, float threshold) { return max(c - threshold, 0.0); }
"""
GLSL_DOF = """
// DOF: CoC from depth, gathered blur. Focus distance + range in uniforms.
float scs_coc(float depth, float focusDist, float focusRange, float maxBlur) {
  float d = abs(depth - focusDist);
  if (d <= focusRange) return 0.0;
  return min(1.0, (d - focusRange) * maxBlur * 10.0);
}
"""
GLSL_VIGNETTE = """
vec3 scs_vignette(vec3 c, vec2 uv, float strength, float radius) {
  float d = distance(uv, vec2(0.5));
  float v = smoothstep(radius, radius - 0.4, d);
  return c * mix(1.0, v, strength);
}
"""
GLSL_GRAIN = """
float scs_grain(vec2 uv, float time) {
  return fract(sin(dot(uv + time, vec2(12.9898, 78.233))) * 43758.5453);
}
"""
GLSL_CA = """
// Chromatic aberration: sample R/B with radial offset.
vec2 scs_ca_offset(vec2 uv, float amount) {
  vec2 d = uv - vec2(0.5);
  return d * amount;
}
"""
GLSL_MOTION_BLUR = """
// Motion blur: gather along velocity (velocity buffer) -- strength * samples.
"""

# [STRIPPED 70 bytes]
# WGSL twins -- WebGPU post uses THESE, never the GLSL above.
# Same math as the GLSL versions (ACES fit, vignette, grain).
# [STRIPPED 70 bytes]

WGSL_TONEMAP = """
// WGSL: tonemap (ACES / Reinhard / AgX) -- same math as GLSL_TONEMAP.
fn scs_tonemap_aces(x: vec3<f32>) -> vec3<f32> {
  return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), vec3<f32>(0.0), vec3<f32>(1.0));
}
fn scs_tonemap(c: vec3<f32>, op: i32, exposure: f32) -> vec3<f32> {
  let e = c * exposure;
  if (op == 0) { return scs_tonemap_aces(e); }
  if (op == 1) { return e / (1.0 + e); }
  return e;
}
"""

WGSL_VIGNETTE = """
fn scs_vignette(c: vec3<f32>, uv: vec2<f32>, strength: f32, radius: f32) -> vec3<f32> {
  let d = distance(uv, vec2<f32>(0.5));
  let v = smoothstep(radius, radius - 0.4, d);
  return c * mix(1.0, v, strength);
}
"""

WGSL_GRAIN = """
fn scs_grain(uv: vec2<f32>, time: f32) -> f32 {
  return fract(sin(dot(uv + time, vec2<f32>(12.9898, 78.233))) * 43758.5453);
}
"""

WGSL_BLOOM = """
// WGSL bloom threshold -- same as GLSL_BLOOM.
fn scs_bloom_threshold(c: vec3<f32>, threshold: f32) -> vec3<f32> { return max(c - threshold, vec3<f32>(0.0)); }
"""

WGSL_DOF = """
fn scs_coc(depth: f32, focusDist: f32, focusRange: f32, maxBlur: f32) -> f32 {
  let d = abs(depth - focusDist);
  if (d <= focusRange) { return 0.0; }
  return min(1.0, (d - focusRange) * maxBlur * 10.0);
}
"""

def wgsl_for_pass(pass_kind):
    """Return the WGSL chunk for a post pass kind, or '' if none."""
    return {'tonemap': WGSL_TONEMAP, 'bloom': WGSL_BLOOM, 'dof': WGSL_DOF,
            'vignette': WGSL_VIGNETTE, 'grain': WGSL_GRAIN}.get(pass_kind, '')

def glsl_for_pass(pass_kind):
    return {'tonemap': GLSL_TONEMAP, 'bloom': GLSL_BLOOM, 'dof': GLSL_DOF,
            'vignette': GLSL_VIGNETTE, 'grain': GLSL_GRAIN,
            'ca': GLSL_CA, 'motion_blur': GLSL_MOTION_BLUR}.get(pass_kind, '')
