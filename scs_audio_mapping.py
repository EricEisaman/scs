
"""
scs_audio_mapping.py -- EFFECT + AUDIO VOLUME mapping.

Two mapping problems, one module:

  1. VOLUME mapping: a control (knob 0..1, MIDI velocity 0..127,
     MIDI CC, a Timeline automation value) is NOT a gain. Gain is
     linear amplitude; ears hear logarithmically. Mapping converts
     control -> gain / dB correctly, so "half volume" sounds like
     half volume, and velocity 64 does not sound like silence.

  2. EFFECT mapping: a control (knob, LFO, envelope, Timeline event)
     maps to an effect param (filter cutoff 20..20000 Hz, delay time,
     reverb wet, distortion amount). The mapping is range + curve:
     cutoff wants exponential (ears hear pitch log), wet wants linear,
     distortion wants a shaping curve. One mapping object per
     (control -> param) pair; a MappingChain maps one control to many
     params at once (a "macro" knob).

All mappings are pure functions + small objects. They work in CPython
(tests) and in the browser (they just compute numbers that are then
set on real AudioParams). No mapping ever touches the audio thread
directly -- it computes the value, the caller sets it.

Volume curves:
  linear      gain = x
  perceptual  gain = x^2  (equal-loudness-ish, the common choice)
  perceptual3 gain = x^3
  exponential gain = (exp(k*x)-1)/(exp(k)-1)
  db          gain = 10^(db/20), db in [-60, 0] mapped from x in [0,1]
  s_curve     gain = smoothstep(x)  (gentle at both ends)

Effect curves (same shaping fns, different ranges):
  linear, exponential (for Hz), logarithmic, cosine, smoothstep,
  ease_in, ease_out, step.

Equal-power crossfade for wet/dry:
  wet_gain = sin(wet * pi/2), dry_gain = cos(wet * pi/2)
  -- constant total power as you crossfade, no dip in the middle.
"""

import math


# [STRIPPED 70 bytes]
# Shaping functions: 0..1 -> 0..1
# [STRIPPED 70 bytes]

def _clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def _shape_linear(x):
    return _clamp01(x)


def _shape_exponential(x, k=4.0):
    # (exp(k*x)-1)/(exp(k)-1): 0->0, 1->1, concave.
    x = _clamp01(x)
    return (math.exp(k * x) - 1.0) / (math.exp(k) - 1.0)


def _shape_logarithmic(x, k=4.0):
    # log(1+k*x)/log(1+k): fast start, gentle end.
    x = _clamp01(x)
    return math.log(1.0 + k * x) / math.log(1.0 + k)


def _shape_cosine(x):
    x = _clamp01(x)
    return 0.5 - 0.5 * math.cos(math.pi * x)


def _shape_smoothstep(x):
    x = _clamp01(x)
    return x * x * (3.0 - 2.0 * x)


def _shape_ease_in(x):
    x = _clamp01(x)
    return x * x


def _shape_ease_out(x):
    x = _clamp01(x)
    return 1.0 - (1.0 - x) * (1.0 - x)


def _shape_step(x):
    return 0.0 if _clamp01(x) < 0.5 else 1.0


_SHAPES = {
    'linear': _shape_linear,
    'exponential': _shape_exponential,
    'exp': _shape_exponential,
    'logarithmic': _shape_logarithmic,
    'log': _shape_logarithmic,
    'cosine': _shape_cosine,
    'cos': _shape_cosine,
    'smoothstep': _shape_smoothstep,
    'smooth': _shape_smoothstep,
    's_curve': _shape_smoothstep,
    'ease_in': _shape_ease_in,
    'ease_out': _shape_ease_out,
    'step': _shape_step,
}

SHAPE_NAMES = tuple(_SHAPES.keys())


def shape_value(shape, x, k=4.0):
    """Shape a 0..1 value with a named curve."""
    fn = _SHAPES.get(str(shape or 'linear'), _shape_linear)
    try:
        return fn(float(x), k) if shape in ('exponential', 'exp', 'logarithmic', 'log') else fn(float(x))
    except Exception:
        return _clamp01(x)


def map_range(x, in_min, in_max, out_min, out_max, shape='linear', k=4.0):
    """Map x from [in_min, in_max] to [out_min, out_max] with shaping.

    The shaping happens in NORMALISED space (0..1), then the result
    is scaled to the output range. For exponential output ranges
    (e.g. filter Hz 20..20000), use shape='exponential' -- or better,
    use map_range_log() which interpolates in log space.
    """
    if in_max == in_min:
        return float(out_min)
    norm = _clamp01((float(x) - float(in_min)) / (float(in_max) - float(in_min)))
    shaped = shape_value(shape, norm, k=k)
    return float(out_min) + shaped * (float(out_max) - float(out_min))


def map_range_log(x, in_min, in_max, out_min, out_max, shape='linear'):
    """Map x to an output range in LOG space. For Hz, pitch, etc.

    out_min and out_max must be > 0. The result is geometric
    interpolation: halfway in -> sqrt(out_min * out_max), which is
    what ears hear as halfway for frequency.
    """
    if out_min <= 0 or out_max <= 0:
        return map_range(x, in_min, in_max, out_min, out_max, shape)
    if in_max == in_min:
        return float(out_min)
    norm = _clamp01((float(x) - float(in_min)) / (float(in_max) - float(in_min)))
    shaped = shape_value(shape, norm)
    lo, hi = math.log(float(out_min)), math.log(float(out_max))
    return math.exp(lo + shaped * (hi - lo))


# [STRIPPED 70 bytes]
# Volume: gain <-> dB <-> control
# [STRIPPED 70 bytes]

def db_to_gain(db):
    """dB -> linear gain. 0 dB -> 1.0, -6 dB -> 0.5, -inf -> 0."""
    try:
        if float(db) <= -120.0:
            return 0.0
        return 10.0 ** (float(db) / 20.0)
    except Exception:
        return 0.0


def gain_to_db(gain):
    """Linear gain -> dB. 0 -> -inf (returned as -120)."""
    g = float(gain)
    if g <= 0:
        return -120.0
    return 20.0 * math.log10(g)


def control_to_gain(x, curve='perceptual'):
    """Control 0..1 -> gain. 'perceptual' (x^2) is the default:
    knob at 0.5 sounds like half volume, not quarter."""
    x = _clamp01(x)
    if curve in ('perceptual', 'perceptual2'):
        return x * x
    if curve == 'perceptual3':
        return x * x * x
    if curve == 'linear':
        return x
    if curve in ('db', 'decibel'):
        # Control 0..1 -> dB -60..0 -> gain.
        return db_to_gain(-60.0 + 60.0 * x)
    return shape_value(curve, x)


def gain_to_control(gain, curve='perceptual'):
    """Gain -> control 0..1 (inverse of control_to_gain)."""
    g = max(0.0, min(1.0, float(gain)))
    if curve in ('perceptual', 'perceptual2'):
        return math.sqrt(g)
    if curve == 'perceptual3':
        return g ** (1.0 / 3.0)
    if curve == 'linear':
        return g
    if curve in ('db', 'decibel'):
        db = gain_to_db(g)
        return _clamp01((db + 60.0) / 60.0)
    return g


def velocity_to_gain(velocity, curve='perceptual'):
    """MIDI velocity 0..127 -> gain."""
    return control_to_gain(float(velocity) / 127.0, curve=curve)


def midi_cc_to_gain(cc, curve='perceptual'):
    """MIDI CC 0..127 -> gain (same as velocity)."""
    return velocity_to_gain(cc, curve=curve)


def equal_power_wet_dry(wet):
    """Wet/dry -> (wet_gain, dry_gain) with constant total power.

    wet=0 -> (0, 1), wet=0.5 -> (0.707, 0.707), wet=1 -> (1, 0).
    No volume dip in the middle, unlike linear crossfade.
    """
    w = _clamp01(wet)
    return (math.sin(w * math.pi / 2.0), math.cos(w * math.pi / 2.0))


# [STRIPPED 70 bytes]
# VolumeMapper: one control -> gain, with curve + range + dB readout
# [STRIPPED 70 bytes]

class VolumeMapper:
    """Maps a control to a gain. Holds curve + range + mute.

    ``vm = VolumeMapper(curve='perceptual', max_db=0.0)``
    ``vm.map(0.5)`` -> 0.25 gain, ``vm.map_db(0.5)`` -> -12.04 dB
    ``vm.set_on(gain_param, 0.5)`` sets a real/fake AudioParam.
    """

    def __init__(self, curve='perceptual', min_gain=0.0, max_gain=1.0,
                 min_db=-60.0, max_db=0.0, name='volume'):
        self.curve = str(curve or 'perceptual')
        self.min_gain = float(min_gain)
        self.max_gain = float(max_gain)
        self.min_db = float(min_db)
        self.max_db = float(max_db)
        self.name = str(name)
        self.muted = False

    def map(self, control):
        """Control 0..1 (or 0..127 if >1) -> gain."""
        x = float(control)
        if x > 1.0:  # MIDI 0..127
            x = x / 127.0
        x = _clamp01(x)
        if self.muted:
            return 0.0
        base = control_to_gain(x, self.curve)
        return self.min_gain + base * (self.max_gain - self.min_gain)

    def map_db(self, control):
        """Control -> dB."""
        return gain_to_db(self.map(control))

    def inverse(self, gain):
        """Gain -> control."""
        g = max(0.0, float(gain))
        if self.max_gain == self.min_gain:
            return 0.0
        base = _clamp01((g - self.min_gain) / (self.max_gain - self.min_gain))
        return gain_to_control(base, self.curve)

    def set_on(self, param, control, when=None):
        """Set an AudioParam to the mapped gain. Returns the gain."""
        gain = self.map(control)
        if param is None:
            return gain
        try:
            if when is not None:
                param.setValueAtTime(float(gain), float(when))
            else:
                param.value = float(gain)
        except Exception:
            pass
        return gain

    def mute(self):
        self.muted = True
        return 0.0

    def unmute(self):
        self.muted = False
        return True

    def describe(self):
        return {'name': self.name, 'curve': self.curve,
                'min_gain': self.min_gain, 'max_gain': self.max_gain,
                'min_db': self.min_db, 'max_db': self.max_db,
                'muted': self.muted}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        vm = cls(curve=d.get('curve', 'perceptual'),
                 min_gain=d.get('min_gain', 0.0), max_gain=d.get('max_gain', 1.0),
                 min_db=d.get('min_db', -60.0), max_db=d.get('max_db', 0.0),
                 name=d.get('name', 'volume'))
        vm.muted = bool(d.get('muted', False))
        return vm


# [STRIPPED 70 bytes]
# EffectParamMapping: control -> one effect param
# [STRIPPED 70 bytes]

class EffectParamMapping:
    """Maps a control to ONE effect param.

    ``EffectParamMapping('cutoff', 'filter', 'frequency',
    ...                 out_min=20, out_max=20000, log=True)``
    ``mapping.map(0.5)`` -> 632 Hz (geometric halfway, what ears hear).
    ``mapping.apply_to(effect, 0.5)`` sets it on an AudioEffect.
    ``mapping.apply_to_param(audio_param, 0.5)`` sets a real AudioParam.
    """

    def __init__(self, control, effect, param, out_min=0.0, out_max=1.0,
                 in_min=0.0, in_max=1.0, shape='linear', log=False,
                 name=None, k=4.0):
        self.control = str(control)      # e.g. 'cutoff', 'velocity', 'lfo'
        self.effect = str(effect)        # effect kind / chain / patch node
        self.param = str(param)          # param name on that effect
        self.out_min = float(out_min)
        self.out_max = float(out_max)
        self.in_min = float(in_min)
        self.in_max = float(in_max)
        self.shape = str(shape or 'linear')
        self.log = bool(log)
        self.name = str(name or ('%s->%s.%s' % (self.control, self.effect, self.param)))
        self.k = float(k)

    def map(self, control_value):
        """Control value -> effect param value."""
        if self.log:
            return map_range_log(control_value, self.in_min, self.in_max,
                                 self.out_min, self.out_max, shape=self.shape)
        return map_range(control_value, self.in_min, self.in_max,
                         self.out_min, self.out_max, shape=self.shape, k=self.k)

    def inverse(self, param_value):
        """Effect param value -> control value (approx, for linear/log)."""
        if self.out_max == self.out_min:
            return self.in_min
        if self.log and self.out_min > 0 and self.out_max > 0 and float(param_value) > 0:
            norm = (math.log(float(param_value)) - math.log(self.out_min)) / \
                   (math.log(self.out_max) - math.log(self.out_min))
            return self.in_min + _clamp01(norm) * (self.in_max - self.in_min)
        norm = _clamp01((float(param_value) - self.out_min) / (self.out_max - self.out_min))
        return self.in_min + norm * (self.in_max - self.in_min)

    def apply_to(self, effect, control_value):
        """Set the param on an AudioEffect (or any object with set_param)."""
        value = self.map(control_value)
        if effect is None:
            return value
        try:
            if hasattr(effect, 'set_param'):
                effect.set_param(self.param, value)
            elif isinstance(getattr(effect, 'params', None), dict):
                effect.params[self.param] = value
        except Exception:
            pass
        return value

    def apply_to_param(self, param, control_value, when=None):
        """Set a real/fake AudioParam."""
        value = self.map(control_value)
        if param is None:
            return value
        try:
            if when is not None:
                param.setValueAtTime(float(value), float(when))
            else:
                param.value = float(value)
        except Exception:
            pass
        return value

    def describe(self):
        return {'name': self.name, 'control': self.control,
                'effect': self.effect, 'param': self.param,
                'in_min': self.in_min, 'in_max': self.in_max,
                'out_min': self.out_min, 'out_max': self.out_max,
                'shape': self.shape, 'log': self.log}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        return cls(d['control'], d['effect'], d['param'],
                   out_min=d.get('out_min', 0.0), out_max=d.get('out_max', 1.0),
                   in_min=d.get('in_min', 0.0), in_max=d.get('in_max', 1.0),
                   shape=d.get('shape', 'linear'), log=d.get('log', False),
                   name=d.get('name'))


# [STRIPPED 70 bytes]
# MappingChain: one control -> many params (a macro knob)
# [STRIPPED 70 bytes]

class MappingChain:
    """One control drives many effect/volume params at once.

    ``chain = MappingChain('macro')``
    ``chain.add(EffectParamMapping('macro', 'filter', 'frequency', 20, 20000, log=True))``
    ``chain.add(EffectParamMapping('macro', 'reverb', 'wet', 0, 0.8))``
    ``chain.apply(engine, 0.7)`` sets every mapped param from one value.
    """

    def __init__(self, control, name=None):
        self.control = str(control)
        self.name = str(name or ('macro:' + self.control))
        self.mappings = []  # list[EffectParamMapping]
        self.volume = None  # optional VolumeMapper for this control

    def add(self, mapping):
        if isinstance(mapping, EffectParamMapping):
            self.mappings.append(mapping)
        else:
            raise ValueError('MappingChain.add needs an EffectParamMapping')
        return self

    def add_param(self, effect, param, out_min, out_max, **kwargs):
        """Shorthand: add_param('filter', 'frequency', 20, 20000, log=True)."""
        m = EffectParamMapping(self.control, effect, param,
                               out_min=out_min, out_max=out_max, **kwargs)
        self.mappings.append(m)
        return m

    def set_volume_mapper(self, mapper):
        self.volume = mapper
        return self

    def map_all(self, control_value):
        """Control -> {effect.param: value} + optional {'volume': gain}."""
        out = {}
        for m in self.mappings:
            out['%s.%s' % (m.effect, m.param)] = m.map(control_value)
        if self.volume is not None:
            out['volume'] = self.volume.map(control_value)
        return out

    def apply(self, engine, control_value, effects=None):
        """Set every mapped param. `effects` is an optional
        {effect_name: AudioEffect} lookup; without it, the engine's
        registered effects are used (engine.get_effect / get_effect_chain)."""
        values = self.map_all(control_value)
        for m in self.mappings:
            target = None
            if effects is not None:
                target = effects.get(m.effect)
            if target is None and engine is not None:
                try:
                    target = engine.get_effect(m.effect) or engine.get_effect_chain(m.effect)
                except Exception:
                    target = None
            if target is not None:
                try:
                    if hasattr(target, 'set_param'):
                        target.set_param(m.param, m.map(control_value))
                    elif hasattr(target, 'set_effect_param'):
                        target.set_effect_param(m.effect, m.param, m.map(control_value))
                except Exception:
                    pass
        if self.volume is not None and engine is not None:
            try:
                engine.set_master_volume(self.volume.map(control_value))
            except Exception:
                pass
        return values

    def describe(self):
        return {'name': self.name, 'control': self.control,
                'mappings': [m.describe() for m in self.mappings],
                'volume': self.volume.describe() if self.volume else None}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        c = cls(d.get('control', 'macro'), name=d.get('name'))
        for md in d.get('mappings', []):
            c.add(EffectParamMapping.from_dict(md))
        if d.get('volume'):
            c.set_volume_mapper(VolumeMapper.from_dict(d['volume']))
        return c


# [STRIPPED 70 bytes]
# Preset mappings: the ones every synth / effect needs
# [STRIPPED 70 bytes]

def preset_mapping(name):
    """Named mapping presets."""
    presets = {
        'cutoff': EffectParamMapping('cutoff', 'filter', 'frequency',
                                     out_min=20, out_max=20000, log=True, shape='linear'),
        'resonance': EffectParamMapping('resonance', 'filter', 'Q',
                                        out_min=0.5, out_max=20, log=True),
        'delay_time': EffectParamMapping('delay_time', 'delay', 'delayTime',
                                         out_min=0.01, out_max=1.0, log=True),
        'delay_feedback': EffectParamMapping('feedback', 'delay', 'feedback',
                                             out_min=0.0, out_max=0.9, shape='linear'),
        'reverb_wet': EffectParamMapping('reverb', 'reverb', 'wet',
                                         out_min=0.0, out_max=1.0, shape='linear'),
        'reverb_decay': EffectParamMapping('decay', 'reverb', 'decay',
                                           out_min=0.1, out_max=8.0, log=True),
        'distortion': EffectParamMapping('drive', 'distortion', 'amount',
                                         out_min=1.0, out_max=300.0, log=True),
        'chorus_depth': EffectParamMapping('depth', 'chorus', 'depth',
                                           out_min=0.0, out_max=0.01, shape='linear'),
        'volume': EffectParamMapping('volume', 'master', 'gain',
                                     out_min=0.0, out_max=1.0, shape='linear'),
        'pan': EffectParamMapping('pan', 'panner', 'pan',
                                  out_min=-1.0, out_max=1.0, shape='linear'),
    }
    if name not in presets:
        raise KeyError('unknown mapping preset %r' % name)
    return presets[name]


__all__ = [
    'SHAPE_NAMES', 'shape_value', 'map_range', 'map_range_log',
    'db_to_gain', 'gain_to_db', 'control_to_gain', 'gain_to_control',
    'velocity_to_gain', 'midi_cc_to_gain', 'equal_power_wet_dry',
    'VolumeMapper', 'EffectParamMapping', 'MappingChain', 'preset_mapping',
]
