
"""
scs_audio_envelopes.py -- FUNCTIONAL, CURVE-BASED envelopes.

An envelope is a FUNCTION of time, not just four ADSR numbers.

    env = CurveEnvelope(points=[(0, 0), (0.01, 1), (0.1, 0.7), (0.5, 0.7)])
    env.value_at(0.05)   # -> 0.85 (interpolated, curve-aware)
    env.apply(gain_param, start_time=now)

Three ways to define one, all first-class:

  1. POINTS:  CurveEnvelope(points=[(t, value, curve), ...])
     curve per segment: 'linear' | 'exponential' | 'cosine' |
     'smoothstep' | 'step' | 'hold' | 'ease_in' | 'ease_out'.

  2. FUNCTION: CurveEnvelope.from_function(fn, duration=1.0)
     fn(t) -> value, t in seconds (or 0..1 if normalized=True).
     Any Python callable: a sine swell, a custom pluck, a random
     humanised curve. Functional envelopes are code, not data --
     they cannot be saved as JSON, only as points (see .sample()).

  3. ADSR:    adsr_envelope(attack, decay, sustain, release, ...)
     ADSR *is* a CurveEnvelope: 4 segments, with a note_off time.
     ADSR.value_at(t, note_off=None) holds sustain until note_off,
     then follows the release segment. This is the envelope that
     actually plays: note_on at t=0, note_off when the key lifts.

Applying is functional too: apply() schedules the curve onto a real
AudioParam (browser) or a fake param (CPython). Cosine / smoothstep /
ease segments are approximated with N linear ramps (default 16 per
segment) because Web Audio only has linear / exponential ramps
natively -- the approximation is what makes the curve audible as a
curve, not as a straight line.

Envelopes attach to: a gain (amplitude), a filter cutoff, an effect
param, a pipeline stage (see scs_audio_pipelines.py), a patch node
(see scs_web_audio.py AudioPatch.automate()).
"""

import math


# [STRIPPED 70 bytes]
# Segment curves: pure functions (t01, v0, v1) -> value
# [STRIPPED 70 bytes]

def _clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def _curve_linear(frac, v0, v1):
    return v0 + (v1 - v0) * frac


def _curve_exponential(frac, v0, v1):
    # Exponential needs positive values; clamp like Web Audio does.
    a = max(float(v0), 0.0001)
    b = max(float(v1), 0.0001)
    return a * ((b / a) ** frac)


def _curve_cosine(frac, v0, v1):
    # Cosine ease in-out: smooth start AND end.
    return v0 + (v1 - v0) * (0.5 - 0.5 * math.cos(math.pi * frac))


def _curve_smoothstep(frac, v0, v1):
    s = frac * frac * (3.0 - 2.0 * frac)
    return v0 + (v1 - v0) * s


def _curve_ease_in(frac, v0, v1):
    return v0 + (v1 - v0) * (frac * frac)


def _curve_ease_out(frac, v0, v1):
    return v0 + (v1 - v0) * (1.0 - (1.0 - frac) * (1.0 - frac))


def _curve_step(frac, v0, v1):
    return v0


_CURVE_FNS = {
    'linear': _curve_linear,
    'exponential': _curve_exponential,
    'exp': _curve_exponential,
    'cosine': _curve_cosine,
    'cos': _curve_cosine,
    'smoothstep': _curve_smoothstep,
    'smooth': _curve_smoothstep,
    'ease_in': _curve_ease_in,
    'ease_out': _curve_ease_out,
    'step': _curve_step,
    'hold': _curve_step,
}

CURVE_NAMES = tuple(_CURVE_FNS.keys())


def curve_value(curve, frac, v0, v1):
    """Evaluate one segment curve at frac (0..1) between v0 and v1."""
    fn = _CURVE_FNS.get(str(curve or 'linear'), _curve_linear)
    return fn(_clamp01(frac), float(v0), float(v1))


# [STRIPPED 70 bytes]
# One segment
# [STRIPPED 70 bytes]

class EnvelopeSegment:
    """One segment: from (t0, v0) to (t1, v1) along `curve`."""

    def __init__(self, t0, t1, v0, v1, curve='linear'):
        self.t0 = float(t0)
        self.t1 = float(t1)
        self.v0 = float(v0)
        self.v1 = float(v1)
        self.curve = str(curve or 'linear')
        if self.curve not in _CURVE_FNS:
            raise ValueError('unknown envelope curve %r (see CURVE_NAMES)' % curve)
        if self.t1 < self.t0:
            raise ValueError('envelope segment ends before it starts')

    @property
    def duration(self):
        return self.t1 - self.t0

    def value_at(self, t):
        if t <= self.t0:
            return self.v0
        if t >= self.t1:
            return self.v1
        if self.duration == 0:
            return self.v1
        frac = (float(t) - self.t0) / self.duration
        return curve_value(self.curve, frac, self.v0, self.v1)

    def describe(self):
        return {'t0': self.t0, 't1': self.t1, 'v0': self.v0,
                'v1': self.v1, 'curve': self.curve}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        return cls(d['t0'], d['t1'], d['v0'], d['v1'], d.get('curve', 'linear'))


# [STRIPPED 70 bytes]
# CurveEnvelope: points | function | ADSR
# [STRIPPED 70 bytes]

class CurveEnvelope:
    """A functional envelope: value_at(t) for any t.

    Construct from points, from a function, or from ADSR::

        CurveEnvelope(points=[(0, 0), (0.01, 1, 'cosine'), (0.3, 0.6)])
        CurveEnvelope.from_function(lambda t: math.sin(t * 10) * math.exp(-t * 3))
        adsr_envelope(attack=0.01, decay=0.1, sustain=0.7, release=0.25)
    """

    def __init__(self, points=None, fn=None, duration=None, loop=False,
                 normalized=False, name='envelope'):
        self.name = str(name)
        self.loop = bool(loop)
        self.normalized = bool(normalized)  # fn takes 0..1, not seconds
        self.duration = float(duration) if duration is not None else None
        self._fn = fn
        self.segments = []
        self._points = []
        if points:
            self._build_from_points(points)
        if self.duration is None:
            if self.segments:
                self.duration = self.segments[-1].t1
            elif self._fn is not None:
                self.duration = 1.0
            else:
                self.duration = 0.0

    # -- construction --------------------------------------------------
    def _build_from_points(self, points):
        # Normalise: (t, v) or (t, v, curve). Curve belongs to the
        # segment STARTING at that point (curve to the NEXT point).
        pts = []
        for p in points:
            if len(p) == 2:
                t, v = p
                c = 'linear'
            else:
                t, v, c = p[0], p[1], p[2]
            pts.append((float(t), float(v), str(c or 'linear')))
        pts.sort(key=lambda p: p[0])
        self._points = pts
        self.segments = []
        for (t0, v0, c), (t1, v1, _c2) in zip(pts, pts[1:]):
            self.segments.append(EnvelopeSegment(t0, t1, v0, v1, c))

    @classmethod
    def from_points(cls, points, **kwargs):
        return cls(points=points, **kwargs)

    @classmethod
    def from_function(cls, fn, duration=1.0, normalized=False, name='fn-envelope'):
        """fn(t) -> value. If normalized, fn takes 0..1 (phase)."""
        if not callable(fn):
            raise ValueError('from_function needs a callable fn(t)')
        return cls(fn=fn, duration=duration, normalized=normalized, name=name)

    @classmethod
    def from_adsr(cls, attack=0.01, decay=0.1, sustain=0.7, release=0.2,
                  peak=1.0, sustain_level=None, **kwargs):
        """ADSR as a CurveEnvelope (see adsr_envelope below)."""
        return adsr_envelope(attack, decay, sustain, release, peak,
                             sustain_level=sustain_level, **kwargs)

    # -- evaluation (the functional part) -------------------------------
    def value_at(self, t, note_off=None):
        """Value at time t (seconds since note_on).

        note_off: if given, sustain is held until note_off, then the
        release segment runs. Without note_off, ADSR envelopes hold
        their sustain value forever (a held key).
        """
        t = float(t)
        if self.loop and self.duration and self.duration > 0:
            t = t % self.duration
        if self._fn is not None:
            # Functional envelope: call the function.
            arg = (t / self.duration) if (self.normalized and self.duration) else t
            try:
                return float(self._fn(arg))
            except Exception:
                return 0.0
        if not self.segments:
            return 0.0
        # ADSR release: segments are [attack, decay, sustain-hold, release]
        # Detect ADSR shape: last segment is release and we hold sustain.
        # The ADSR subclass handles this; base class just interpolates.
        if t <= self.segments[0].t0:
            return self.segments[0].v0
        for seg in self.segments:
            if seg.t0 <= t <= seg.t1:
                return seg.value_at(t)
        return self.segments[-1].v1

    def sample(self, n=64, duration=None):
        """Sample the envelope into n values over `duration`.
        This is how a functional (code) envelope becomes saveable
        points: sample() -> from_points(samples)."""
        dur = float(duration) if duration is not None else float(self.duration or 1.0)
        if n <= 1:
            return [self.value_at(0.0)]
        return [self.value_at(dur * i / (n - 1)) for i in range(n)]

    def to_points(self, n=64):
        """Functional -> points: [(t, value), ...] for saving / JSON."""
        dur = float(self.duration or 1.0)
        if n <= 1:
            return [(0.0, self.value_at(0.0))]
        return [(dur * i / (n - 1), self.value_at(dur * i / (n - 1)))
                for i in range(n)]

    # -- applying to real / fake AudioParams ------------------------------
    def apply(self, param, start_time=0.0, peak=1.0, steps_per_segment=16):
        """Schedule this envelope onto an AudioParam.

        Returns the number of scheduled ramps. Linear / exponential
        segments use the native ramp; cosine / smoothstep / ease
        segments are subdivided into `steps_per_segment` linear ramps
        so the curve is actually heard as a curve.
        `peak` scales the envelope (envelope * peak).
        """
        if param is None:
            return 0
        t0 = float(start_time)
        n = 0
        if self._fn is not None:
            # Functional: sample into linear ramps.
            pts = self.to_points(steps_per_segment * 4)
            try:
                param.setValueAtTime(float(pts[0][1] * peak), t0)
                n += 1
            except Exception:
                pass
            for (t, v) in pts[1:]:
                try:
                    param.linearRampToValueAtTime(float(v * peak), t0 + t)
                    n += 1
                except Exception:
                    pass
            return n
        # Point-based: walk segments.
        try:
            param.setValueAtTime(float(self.segments[0].v0 * peak) if self.segments else 0.0, t0)
            n += 1
        except Exception:
            pass
        for seg in self.segments:
            n += self._apply_segment(param, seg, t0, peak, steps_per_segment)
        return n

    def _apply_segment(self, param, seg, t0, peak, steps):
        if seg.duration == 0:
            try:
                param.setValueAtTime(float(seg.v1 * peak), t0 + seg.t1)
                return 1
            except Exception:
                return 0
        if seg.curve == 'linear':
            try:
                param.linearRampToValueAtTime(float(seg.v1 * peak), t0 + seg.t1)
                return 1
            except Exception:
                return 0
        if seg.curve in ('exponential', 'exp'):
            try:
                param.exponentialRampToValueAtTime(max(float(seg.v1 * peak), 0.0001), t0 + seg.t1)
                return 1
            except Exception:
                return 0
        if seg.curve in ('step', 'hold'):
            try:
                param.setValueAtTime(float(seg.v1 * peak), t0 + seg.t1)
                return 1
            except Exception:
                return 0
        # Cosine / smoothstep / ease: subdivide into linear ramps.
        count = 0
        for i in range(1, int(steps) + 1):
            frac = i / float(steps)
            t = seg.t0 + seg.duration * frac
            v = curve_value(seg.curve, frac, seg.v0, seg.v1) * peak
            try:
                param.linearRampToValueAtTime(float(v), t0 + t)
                count += 1
            except Exception:
                pass
        return count

    def apply_to_gain(self, gain_node, start_time=0.0, peak=1.0, **kwargs):
        """Apply to a GainNode's .gain AudioParam."""
        if gain_node is None:
            return 0
        param = getattr(gain_node, 'gain', None)
        return self.apply(param, start_time, peak=peak, **kwargs)

    def apply_to_param(self, node, param_name, start_time=0.0, peak=1.0, **kwargs):
        """Apply to any named AudioParam on a node."""
        if node is None:
            return 0
        param = getattr(node, str(param_name), None)
        return self.apply(param, start_time, peak=peak, **kwargs)

    # -- serialise ----------------------------------------------------------
    def describe(self):
        return {'name': self.name, 'duration': self.duration, 'loop': self.loop,
                'normalized': self.normalized, 'functional': self._fn is not None,
                'points': list(self._points),
                'segments': [s.describe() for s in self.segments]}

    def to_dict(self):
        # Functional envelopes serialise as sampled points.
        if self._fn is not None:
            return {'name': self.name, 'duration': self.duration, 'loop': self.loop,
                    'points': self.to_points(64), 'functional': True}
        return {'name': self.name, 'duration': self.duration, 'loop': self.loop,
                'points': list(self._points), 'functional': False}

    @classmethod
    def from_dict(cls, d):
        env = cls(points=d.get('points', []), duration=d.get('duration'),
                  loop=d.get('loop', False), name=d.get('name', 'envelope'))
        return env


# [STRIPPED 70 bytes]
# ADSR: the playable envelope
# [STRIPPED 70 bytes]

class ADSREnvelope(CurveEnvelope):
    """ADSR with real note_on / note_off semantics.

    Segments: attack (0 -> peak), decay (peak -> sustain), sustain
    (hold), release (sustain -> 0). value_at(t, note_off=None) holds
    sustain until note_off, then runs release from the sustain value
    at note_off time.
    """

    def __init__(self, attack=0.01, decay=0.1, sustain=0.7, release=0.2,
                 peak=1.0, sustain_level=None, curve='linear',
                 release_curve='linear', name='adsr'):
        self.attack = float(attack)
        self.decay = float(decay)
        self.sustain = float(sustain) if sustain_level is None else float(sustain_level)
        self.release = float(release)
        self.peak = float(peak)
        self.curve = str(curve or 'linear')
        self.release_curve = str(release_curve or 'linear')
        # Points for the attack+decay part. Sustain is a hold, release
        # is handled in value_at() via note_off (it has no fixed time).
        points = [
            (0.0, 0.0, self.curve),
            (self.attack, self.peak, self.curve),
            (self.attack + self.decay, self.peak * self.sustain, self.curve),
        ]
        super().__init__(points=points, duration=self.attack + self.decay,
                         name=name)
        # Release segment template (starts at sustain, ends at 0).
        self._release_seg = EnvelopeSegment(0.0, self.release,
                                            self.peak * self.sustain, 0.0,
                                            self.release_curve)

    def value_at(self, t, note_off=None):
        t = float(t)
        if self.loop and self.duration and self.duration > 0:
            t = t % self.duration
        if note_off is None or t <= float(note_off):
            # Before note_off: attack/decay, then hold sustain.
            if t <= self.attack + self.decay:
                return super().value_at(t)
            return self.peak * self.sustain
        # After note_off: release from sustain value.
        rel_t = t - float(note_off)
        if rel_t >= self.release:
            return 0.0
        return self._release_seg.value_at(rel_t)

    def apply(self, param, start_time=0.0, peak=1.0, note_off=None,
              steps_per_segment=16):
        """Schedule attack+decay+sustain, then release at note_off.

        If note_off is None, only attack+decay+sustain-start is
        scheduled (a held key). The caller schedules release by
        calling apply_release() on key-up.
        """
        if param is None:
            return 0
        t0 = float(start_time)
        # Scale: envelope peak * caller peak.
        scale = float(peak)
        n = 0
        # Attack + decay via base apply (segments already in self).
        # Base apply schedules setValueAtTime(0) + attack + decay.
        # We call it with peak=scale.
        n += super().apply(param, t0, peak=scale,
                           steps_per_segment=steps_per_segment)
        if note_off is not None:
            n += self.apply_release(param, note_off, peak=scale,
                                    steps_per_segment=steps_per_segment)
        return n

    def apply_release(self, param, note_off, peak=1.0, steps_per_segment=16):
        """Schedule the release segment starting at absolute `note_off`."""
        if param is None:
            return 0
        seg = EnvelopeSegment(float(note_off), float(note_off) + self.release,
                              self.peak * self.sustain * float(peak), 0.0,
                              self.release_curve)
        return self._apply_segment(param, seg, 0.0, 1.0, steps_per_segment)

    def describe(self):
        d = super().describe()
        d.update({'attack': self.attack, 'decay': self.decay,
                  'sustain': self.sustain, 'release': self.release,
                  'peak': self.peak, 'curve': self.curve,
                  'release_curve': self.release_curve})
        return d

    def to_dict(self):
        return {'name': self.name, 'type': 'adsr', 'attack': self.attack,
                'decay': self.decay, 'sustain': self.sustain,
                'release': self.release, 'peak': self.peak,
                'curve': self.curve, 'release_curve': self.release_curve}

    @classmethod
    def from_dict(cls, d):
        return cls(attack=d.get('attack', 0.01), decay=d.get('decay', 0.1),
                   sustain=d.get('sustain', 0.7), release=d.get('release', 0.2),
                   peak=d.get('peak', 1.0), curve=d.get('curve', 'linear'),
                   release_curve=d.get('release_curve', 'linear'),
                   name=d.get('name', 'adsr'))


def adsr_envelope(attack=0.01, decay=0.1, sustain=0.7, release=0.2,
                  peak=1.0, sustain_level=None, **kwargs):
    """Factory: ADSR as a CurveEnvelope (ADSREnvelope)."""
    return ADSREnvelope(attack=attack, decay=decay, sustain=sustain,
                        release=release, peak=peak,
                        sustain_level=sustain_level, **kwargs)


# [STRIPPED 70 bytes]
# Presets: named envelopes, all CurveEnvelope
# [STRIPPED 70 bytes]

_ENVELOPE_PRESETS = {
    # name: (points or ADSR kwargs)
    'pluck': {'adsr': {'attack': 0.003, 'decay': 0.25, 'sustain': 0.0, 'release': 0.05}},
    'pad': {'adsr': {'attack': 0.8, 'decay': 0.4, 'sustain': 0.8, 'release': 1.2}},
    'piano': {'adsr': {'attack': 0.005, 'decay': 0.4, 'sustain': 0.3, 'release': 0.6}},
    'bass': {'adsr': {'attack': 0.01, 'decay': 0.15, 'sustain': 0.6, 'release': 0.15}},
    'swell': {'points': [(0, 0, 'cosine'), (0.8, 1, 'cosine'), (1.2, 0.6, 'cosine'), (2.0, 0, 'cosine')]},
    'tremolo': {'points': [(0, 1, 'cosine'), (0.1, 0.2, 'cosine'), (0.2, 1, 'cosine')], 'loop': True},
    'gate': {'points': [(0, 1, 'step'), (0.2, 1, 'step'), (0.2, 0, 'step'), (0.4, 0, 'step')], 'loop': True},
}


def envelope_preset(name, **overrides):
    """Named envelope preset: 'pluck', 'pad', 'piano', 'bass',
    'swell', 'tremolo', 'gate'."""
    if name not in _ENVELOPE_PRESETS:
        raise KeyError('unknown envelope preset %r' % name)
    spec = dict(_ENVELOPE_PRESETS[name])
    spec.update(overrides)
    if 'adsr' in spec:
        kw = dict(spec['adsr'])
        kw['name'] = name
        return adsr_envelope(**kw)
    pts = spec.get('points', [])
    return CurveEnvelope(points=pts, loop=spec.get('loop', False), name=name)


__all__ = [
    'CURVE_NAMES', 'curve_value',
    'EnvelopeSegment', 'CurveEnvelope', 'ADSREnvelope', 'adsr_envelope',
    'envelope_preset',
]
