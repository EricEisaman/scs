
"""
scs_web_audio.py -- CANONICAL Web Audio interface for ALL SCS engines.

Every engine exposes this SAME object as ``engine.audio``:

    engine.audio.resume()                       # from a user gesture
    engine.audio.beep(freq=440, duration=0.25)   # one tone
    engine.audio.create_patch('lead', ...)      # patch designer
    engine.audio.create_effect('reverb', ...)   # effect designer
    engine.audio.create_timeline('song', bpm=120)  # timeline
    engine.audio.create_spatial_source(...)     # 3D sound
    engine.audio.update_listener(camera)        # camera == listener
    engine.audio.create_envelope('pluck', ...)  # curve-based envelope
    engine.audio.create_volume_mapper('vol', ...)  # control -> gain
    engine.audio.create_mapping('cutoff', ...)  # control -> effect param
    engine.audio.create_pipeline('lead', ...)   # node src pipeline

Contract (same as scs_audio.py, now extended):

  * AUDIO clock is separate from RENDER clock. Everything is
    scheduled against AudioContext.currentTime, never frame count.
    ClockMapping (getOutputTimestamp) maps audio <-> performance time
    for visuals that must sync to audio.
  * An app may SUPPLY its AudioContext. Ownership is explicit:
    disposing an engine never closes an app-owned context.
  * Autoplay: resume() must be called from a user gesture. No engine
    starts audio implicitly at construction.
  * Custom DSP goes in an AudioWorklet (audio thread), never in a
    render callback. Setting AudioParams from onStep is the
    documented pattern and is cheap.
  * No browser? No problem. In CPython (tests) every node is a
    _FakeAudioNode that records connections / params / start/stop,
    so patches, effects, and timelines can be built, scheduled, and
    described without a browser. In the browser the SAME calls build
    real Web Audio nodes.

Three designers, one engine:

  PATCH designer  -- AudioPatch: a named graph of nodes (oscillator,
    gain, filter, delay, LFO, ADSR, noise, panner, worklet) + wires.
    Patches are pure data (to_dict / from_dict) until played, so a
    patch can be saved, shared, and rebuilt on any engine.

  EFFECT designer -- AudioEffect + EffectChain: reverb, delay,
    distortion, chorus, flanger, compressor, filter, tremolo,
    stereo panner. Each effect is a param dict + a builder. Chains
    have wet/dry, per-effect bypass, and insert/send routing.
    Effects can be attached to a patch, to the master bus, or to a
    timeline event.

  TIMELINE -- Timeline: tempo (bpm), bars, loop, and events.
    Events are notes, effect changes, param automation, and cues.
    "Play timeline based effects" means an effect change IS a
    timeline event: at beat 8, open the filter; at beat 16, throw
    the delay; at beat 32, swell the reverb wet. Timeline.schedule()
    turns beats into audio-time calls on the engine.

Spatial audio lives here too: the Camera3D IS the listener, and each
SpatialSoundSource is a patch (oscillator -> gain -> panner) with a
3D position. Same engine, same clock, same effects.

Three more designers, same engine (Batch 3, wired in):

  ENVELOPE -- CurveEnvelope / ADSREnvelope (scs_audio_envelopes.py):
    an envelope is a FUNCTION of time: points + per-segment curve
    (linear / exponential / cosine / smoothstep / ease / step) or
    any callable fn(t). ADSR is a CurveEnvelope with note_off
    semantics. apply() schedules it onto a real/fake AudioParam.

  MAPPING -- VolumeMapper / EffectParamMapping / MappingChain
    (scs_audio_mapping.py): control -> gain (perceptual / dB /
    linear) and control -> effect param (range + curve + log for Hz).
    One macro knob can drive many params at once.

  PIPELINE -- AudioSrcPipeline / AudioPipelineMixer
    (scs_audio_pipelines.py): node-based source pipelines:
    src -> stages -> destination, plus parallel sends. Stages are
    gains, filters, envelopes, effects, mappings. build() wires
    them, start() is note-on, stop() is note-off with release.
"""

import math
import time

# Batch 3: envelopes / mapping / pipelines live in their own modules
# and are wired into WebAudioEngine below. All three are optional at
# import time (Brython / partial checkouts) -- the engine methods
# raise a clear error if a module is missing, instead of failing import.
try:
    from scs_audio_envelopes import (
        CurveEnvelope, ADSREnvelope, adsr_envelope, envelope_preset,
        EnvelopeSegment,
    )
except Exception:
    CurveEnvelope = ADSREnvelope = adsr_envelope = envelope_preset = None
    EnvelopeSegment = None

try:
    from scs_audio_mapping import (
        VolumeMapper, EffectParamMapping, MappingChain, preset_mapping,
        map_range, map_range_log, db_to_gain, gain_to_db,
        control_to_gain, gain_to_control, velocity_to_gain,
        equal_power_wet_dry,
    )
except Exception:
    VolumeMapper = EffectParamMapping = MappingChain = preset_mapping = None
    map_range = map_range_log = db_to_gain = gain_to_db = None
    control_to_gain = gain_to_control = velocity_to_gain = None
    equal_power_wet_dry = None

try:
    from scs_audio_pipelines import (
        AudioSrc, PipelineStage, AudioSrcPipeline, AudioPipelineMixer,
    )
except Exception:
    AudioSrc = PipelineStage = AudioSrcPipeline = AudioPipelineMixer = None


try:
    from browser import window
except ImportError:
    window = None


# ----------------------------------------------------------------------
# Notes / frequencies
# ----------------------------------------------------------------------

_NOTE_OFFSETS = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
_ACCIDENTALS = {'#': 1, 's': 1, 'b': -1, 'x': 2}


def midi_to_freq(midi):
    """MIDI note number -> Hz. A4 (69) == 440 Hz."""
    return 440.0 * (2.0 ** ((float(midi) - 69.0) / 12.0))


def freq_to_midi(freq):
    """Hz -> fractional MIDI note number. 440 -> 69.0."""
    f = float(freq)
    if f <= 0:
        return 0.0
    return 69.0 + 12.0 * (math.log(f / 440.0) / math.log(2.0))


def note_to_freq(note):
    """'C4', 'A#3', 'Bb2', 'F#5' -> Hz. Pass-through for numbers."""
    if isinstance(note, (int, float)):
        # > 200 means "already Hz"; <= 127 means "MIDI number".
        if float(note) > 200:
            return float(note)
        return midi_to_freq(note)
    s = str(note).strip()
    if not s:
        return 440.0
    # Plain number as string.
    try:
        return note_to_freq(float(s))
    except Exception:
        pass
    letter = s[0].upper()
    if letter not in _NOTE_OFFSETS:
        return 440.0
    rest = s[1:]
    acc = 0
    while rest and rest[0] in _ACCIDENTALS:
        acc += _ACCIDENTALS[rest[0]]
        rest = rest[1:]
    try:
        octave = int(rest) if rest else 4
    except Exception:
        octave = 4
    midi = 12 * (octave + 1) + _NOTE_OFFSETS[letter] + acc
    return midi_to_freq(midi)


def note_to_midi(note):
    """'C4' -> 60. Numbers pass through as MIDI (<=127) or Hz (>200 -> convert)."""
    if isinstance(note, (int, float)):
        if float(note) > 200:
            return freq_to_midi(note)
        return float(note)
    return 69.0 + 12.0 * (math.log(note_to_freq(note) / 440.0) / math.log(2.0))


# ----------------------------------------------------------------------
# Fake nodes (CPython / tests): record what a real graph would do.
# ----------------------------------------------------------------------

class _FakeAudioParam:
    """Mimics AudioParam: .value + scheduling methods, all recorded."""

    def __init__(self, value=0.0, name='param'):
        self.value = float(value)
        self.name = name
        self.events = []  # (method, value, time, extra)

    def setValueAtTime(self, value, t):
        self.events.append(('set', float(value), float(t), None))
        self.value = float(value)
        return self

    def linearRampToValueAtTime(self, value, t):
        self.events.append(('linear', float(value), float(t), None))
        self.value = float(value)
        return self

    def exponentialRampToValueAtTime(self, value, t):
        self.events.append(('exponential', float(value), float(t), None))
        self.value = float(value)
        return self

    def setTargetAtTime(self, value, t, time_constant):
        self.events.append(('target', float(value), float(t), float(time_constant)))
        self.value = float(value)
        return self

    def cancelScheduledValues(self, t):
        self.events.append(('cancel', 0.0, float(t), None))
        return self

    def __repr__(self):
        return '_FakeAudioParam(%s=%s)' % (self.name, self.value)


class _FakeAudioNode:
    """Mimics an AudioNode: .connect/.disconnect/.start/.stop + params."""

    _PARAMS = {
        'oscillator': {'frequency': 440.0, 'detune': 0.0},
        'gain': {'gain': 1.0},
        'filter': {'frequency': 1000.0, 'Q': 1.0, 'gain': 0.0},
        'delay': {'delayTime': 0.3},
        'compressor': {'threshold': -24.0, 'knee': 30.0, 'ratio': 12.0,
                       'attack': 0.003, 'release': 0.25},
        'panner': {},
        'stereopanner': {'pan': 0.0},
        'convolver': {},
        'waveshaper': {},
        'analyser': {},
        'buffersource': {'playbackRate': 1.0, 'detune': 0.0},
        'worklet': {},
    }

    def __init__(self, kind, **params):
        self.kind = str(kind)
        self.params = dict(params)
        self.connections = []  # (dest_node, dest_param_or_None)
        self.started = False
        self.stopped = False
        self.start_time = None
        self.stop_time = None
        # Real AudioParams the graph code can set.
        for pname, default in self._PARAMS.get(self.kind, {}).items():
            setattr(self, pname, _FakeAudioParam(params.get(pname, default), pname))
        # Common extras every node may carry.
        for pname in ('type', 'loop', 'playbackRate'):
            if pname in params:
                setattr(self, pname, params[pname])
        if self.kind == 'oscillator':
            self.type = params.get('type', 'sine')
        if self.kind == 'filter':
            self.type = params.get('type', 'lowpass')
        if self.kind == 'panner':
            for axis in ('positionX', 'positionY', 'positionZ'):
                setattr(self, axis, _FakeAudioParam(0.0, axis))
            self.panningModel = params.get('panningModel', 'HRTF')
            self.distanceModel = params.get('distanceModel', 'inverse')

    def connect(self, dest, *args):
        self.connections.append((dest, args[0] if args else None))
        return dest

    def disconnect(self, *args):
        self.connections = []
        return None

    def start(self, when=None):
        self.started = True
        self.start_time = when
        return self

    def stop(self, when=None):
        self.stopped = True
        self.stop_time = when
        return self

    def setPosition(self, x, y, z):
        for axis, v in (('positionX', x), ('positionY', y), ('positionZ', z)):
            try:
                getattr(self, axis).value = float(v)
            except Exception:
                pass

    def setOrientation(self, *args):
        self._orientation = tuple(args)

    def __repr__(self):
        return '_FakeAudioNode(%s)' % self.kind


class _FakeAudioContext:
    """Mimics AudioContext enough for patches / effects / timelines."""

    def __init__(self):
        self.currentTime = 0.0
        self.destination = _FakeAudioNode('gain', gain=1.0)
        self.listener = _FakeAudioNode('panner')
        self._nodes = []
        self._closed = False
        self.audioWorklet = self._FakeWorklet()

    class _FakeWorklet:
        def __init__(self):
            self.modules = []

        def addModule(self, url):
            self.modules.append(url)
            return None

    def _mk(self, kind, **params):
        n = _FakeAudioNode(kind, **params)
        self._nodes.append(n)
        return n

    def createOscillator(self):
        return self._mk('oscillator')

    def createGain(self):
        return self._mk('gain')

    def createBiquadFilter(self):
        return self._mk('filter')

    def createDelay(self, max_delay=1.0):
        return self._mk('delay', max_delay=max_delay)

    def createDynamicsCompressor(self):
        return self._mk('compressor')

    def createWaveShaper(self):
        return self._mk('waveshaper')

    def createConvolver(self):
        return self._mk('convolver')

    def createPanner(self):
        return self._mk('panner')

    def createStereoPanner(self):
        return self._mk('stereopanner')

    def createAnalyser(self):
        return self._mk('analyser')

    def createBufferSource(self):
        return self._mk('buffersource')

    def createBuffer(self, channels, length, sample_rate):
        return {'channels': channels, 'length': length,
                'sampleRate': sample_rate, 'data': []}

    def resume(self):
        return None

    def suspend(self):
        return None

    def close(self):
        self._closed = True
        return None

    def getOutputTimestamp(self):
        return None


def _is_browser():
    return window is not None


# ----------------------------------------------------------------------
# Clock mapping (audio time <-> performance time)
# ----------------------------------------------------------------------

class ClockMapping:
    """performance.now() <-> AudioContext.currentTime mapping."""

    def __init__(self, context=None):
        self.context = context
        self._offset = None
        self.refresh()

    def refresh(self):
        try:
            if self.context is not None and hasattr(self.context, 'getOutputTimestamp'):
                ts = self.context.getOutputTimestamp()
                if ts is not None:
                    perf_s = float(ts.performanceTime) / 1000.0
                    self._offset = float(ts.contextTime) - perf_s
                    return self._offset
        except Exception:
            pass
        try:
            now_perf = time.time()
            ctx_t = float(self.context.currentTime) if self.context else 0.0
            self._offset = ctx_t - now_perf
        except Exception:
            self._offset = 0.0
        return self._offset

    def audio_to_performance(self, audio_time):
        return (audio_time - (self._offset or 0.0))

    def performance_to_audio(self, perf_time):
        return perf_time + (self._offset or 0.0)

    def now_audio(self):
        try:
            return float(self.context.currentTime)
        except Exception:
            return time.time() + (self._offset or 0.0)


class AudioEvent:
    """Timestamped audio-side event (note, cue, beat, effect change)."""

    def __init__(self, audio_time, kind, data=None):
        self.audio_time = float(audio_time)
        self.kind = kind
        self.data = data or {}


# ----------------------------------------------------------------------
# Param helpers (work on real + fake AudioParams)
# ----------------------------------------------------------------------

def _set_param(param, value, when=0.0):
    """Set an AudioParam: .value if present, else setValueAtTime."""
    if param is None:
        return False
    try:
        param.value = float(value)
        return True
    except Exception:
        pass
    try:
        param.setValueAtTime(float(value), float(when))
        return True
    except Exception:
        return False


def _set_3d_position(node, pos, when=0.0):
    """Position a PannerNode / Listener across old + new APIs."""
    try:
        if (hasattr(node, 'positionX') and hasattr(node, 'positionY')
                and hasattr(node, 'positionZ')):
            _set_param(node.positionX, pos[0], when)
            _set_param(node.positionY, pos[1], when)
            _set_param(node.positionZ, pos[2], when)
            return 'audio-params'
        if hasattr(node, 'setPosition'):
            node.setPosition(float(pos[0]), float(pos[1]), float(pos[2]))
            return 'setPosition'
    except Exception:
        pass
    return None


def inverse_distance_gain(distance, ref_distance=1.0, max_distance=30.0,
                          rolloff=1.0):
    """Web Audio 'inverse' distance model, computed in Python so the HUD
    can show the same number the browser hears."""
    d = max(float(distance), 0.0)
    d = min(d, float(max_distance))
    if d <= ref_distance:
        return 1.0
    return ref_distance / (ref_distance + rolloff * (d - ref_distance))


# ----------------------------------------------------------------------
# Automation: param curves over time
# ----------------------------------------------------------------------

class AutomationPoint:
    """One point on a param curve: (time, value, curve_to_next)."""

    def __init__(self, t, value, curve='linear'):
        self.t = float(t)
        self.value = float(value)
        self.curve = str(curve or 'linear')  # linear | exponential | step | hold


class AutomationCurve:
    """A list of AutomationPoints. value_at(t) interpolates; apply()
    schedules the whole curve onto a real AudioParam."""

    def __init__(self, points=None, param=None):
        self.param = param
        self.points = []
        for p in (points or []):
            if isinstance(p, AutomationPoint):
                self.points.append(p)
            else:
                # (t, value) or (t, value, curve)
                self.points.append(AutomationPoint(*p))
        self.points.sort(key=lambda p: p.t)

    def add(self, t, value, curve='linear'):
        self.points.append(AutomationPoint(t, value, curve))
        self.points.sort(key=lambda p: p.t)
        return self

    def value_at(self, t):
        """Interpolate. Before first -> first value; after last -> last."""
        if not self.points:
            return 0.0
        t = float(t)
        if t <= self.points[0].t:
            return self.points[0].value
        if t >= self.points[-1].t:
            return self.points[-1].value
        for a, b in zip(self.points, self.points[1:]):
            if a.t <= t <= b.t:
                if a.curve in ('step', 'hold'):
                    return a.value
                span = (b.t - a.t) or 1.0
                frac = (t - a.t) / span
                if a.curve == 'exponential' and a.value > 0 and b.value > 0:
                    return a.value * ((b.value / a.value) ** frac)
                return a.value + (b.value - a.value) * frac
        return self.points[-1].value

    def apply(self, param=None, start_time=0.0):
        """Schedule onto a real/fake AudioParam. Returns point count."""
        p = param if param is not None else None
        if p is None:
            return 0
        n = 0
        for pt in self.points:
            when = float(start_time) + pt.t
            try:
                if pt.curve == 'exponential':
                    p.exponentialRampToValueAtTime(max(pt.value, 0.0001), when)
                elif pt.curve in ('step', 'hold'):
                    p.setValueAtTime(pt.value, when)
                else:
                    p.linearRampToValueAtTime(pt.value, when)
                n += 1
            except Exception:
                _set_param(p, pt.value, when)
                n += 1
        return n

    def describe(self):
        return {'param': self.param,
                'points': [(p.t, p.value, p.curve) for p in self.points]}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d, param=None):
        return cls(points=d.get('points', []), param=param or d.get('param'))


# ----------------------------------------------------------------------
# PATCH designer
# ----------------------------------------------------------------------

# Node kinds the patch designer understands. Each maps to a
# context.create* call in the browser, or a fake node in CPython.
_PATCH_NODE_KINDS = (
    'oscillator', 'gain', 'filter', 'delay', 'compressor', 'panner',
    'stereopanner', 'convolver', 'waveshaper', 'analyser',
    'buffersource', 'noise', 'lfo', 'envelope', 'worklet', 'destination',
)

# ADSR envelope defaults (seconds, 0..1 sustain).
_ENVELOPE_DEFAULTS = {'attack': 0.01, 'decay': 0.1,
                       'sustain': 0.7, 'release': 0.2}


class PatchNode:
    """One node in a patch: kind + params + (optional) automation."""

    def __init__(self, node_id, kind, params=None, automation=None):
        self.id = str(node_id)
        self.kind = str(kind)
        if self.kind not in _PATCH_NODE_KINDS:
            raise ValueError('unknown patch node kind %r (see _PATCH_NODE_KINDS)' % kind)
        self.params = dict(params or {})
        self.automation = {}  # param_name -> AutomationCurve
        for pname, curve in (automation or {}).items():
            self.automation[pname] = curve if isinstance(curve, AutomationCurve) else AutomationCurve(curve, pname)

    def set_param(self, name, value):
        self.params[str(name)] = value
        return self

    def automate(self, name, points):
        """points: [(t, value, curve), ...] relative to note-on."""
        self.automation[str(name)] = (points if isinstance(points, AutomationCurve)
                                      else AutomationCurve(points, name))
        return self

    def describe(self):
        return {'id': self.id, 'kind': self.kind, 'params': dict(self.params),
                'automation': {k: v.describe() for k, v in self.automation.items()}}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        return cls(d['id'], d['kind'], d.get('params'),
                   {k: AutomationCurve.from_dict(v, k) for k, v in d.get('automation', {}).items()})


class AudioPatch:
    """A named, saveable synth patch: nodes + wires + I/O.

    Example::

        patch = AudioPatch('lead')
        patch.add_oscillator('osc', type='sawtooth', freq=220)
        patch.add_filter('flt', type='lowpass', frequency=1200, Q=2)
        patch.add_gain('amp', gain=0.5)
        patch.add_envelope('env', attack=0.01, decay=0.1, sustain=0.7, release=0.2)
        patch.connect('osc', 'flt').connect('flt', 'amp').connect('amp', 'out')
        patch.set_param('flt', 'frequency', 800)
        engine.play_patch(patch, freq=440, duration=1.0)
    """

    def __init__(self, name, nodes=None, connections=None):
        self.name = str(name)
        self.nodes = {}  # id -> PatchNode
        self.connections = []  # (from_id, to_id, from_param, to_param)
        for n in (nodes or []):
            self.add_node(n)
        for c in (connections or []):
            self.connect(*c)

    # -- building --------------------------------------------------
    def add_node(self, node_or_id, kind=None, **params):
        if isinstance(node_or_id, PatchNode):
            self.nodes[node_or_id.id] = node_or_id
            return node_or_id
        node = PatchNode(node_or_id, kind or 'gain', params)
        self.nodes[node.id] = node
        return node

    def add_oscillator(self, node_id, type='sine', freq=440.0, detune=0.0):
        return self.add_node(node_id, 'oscillator', type=type, frequency=float(freq), detune=float(detune))

    def add_gain(self, node_id, gain=1.0):
        return self.add_node(node_id, 'gain', gain=float(gain))

    def add_filter(self, node_id, type='lowpass', frequency=1000.0, Q=1.0, gain=0.0):
        return self.add_node(node_id, 'filter', type=type, frequency=float(frequency),
                             Q=float(Q), gain=float(gain))

    def add_delay(self, node_id, delayTime=0.3, feedback=0.3, wet=0.3):
        return self.add_node(node_id, 'delay', delayTime=float(delayTime),
                             feedback=float(feedback), wet=float(wet))

    def add_compressor(self, node_id, **params):
        d = {'threshold': -24.0, 'knee': 30.0, 'ratio': 12.0, 'attack': 0.003, 'release': 0.25}
        d.update(params)
        return self.add_node(node_id, 'compressor', **d)

    def add_panner(self, node_id, position=(0.0, 0.0, 0.0)):
        return self.add_node(node_id, 'panner', position=tuple(position))

    def add_lfo(self, node_id, type='sine', freq=5.0, depth=1.0, target=None, target_param=None):
        """LFO: an oscillator whose output modulates another param.
        target = node id, target_param = param name on that node."""
        return self.add_node(node_id, 'lfo', type=type, frequency=float(freq),
                             depth=float(depth), target=target, target_param=target_param)

    def add_envelope(self, node_id, **params):
        d = dict(_ENVELOPE_DEFAULTS)
        d.update(params)
        return self.add_node(node_id, 'envelope', **d)

    def add_noise(self, node_id, gain=0.5):
        return self.add_node(node_id, 'noise', gain=float(gain))

    def add_worklet(self, node_id, worklet_name, **params):
        n = self.add_node(node_id, 'worklet', worklet_name=worklet_name)
        n.params.update(params)
        return n

    def connect(self, from_id, to_id, from_param=None, to_param=None):
        """Wire from_id -> to_id. 'out' is the patch output (destination)."""
        self.connections.append((str(from_id), str(to_id), from_param, to_param))
        return self

    def disconnect(self, from_id=None, to_id=None):
        self.connections = [c for c in self.connections
                            if (from_id is None or c[0] == str(from_id))
                            and (to_id is None or c[1] == str(to_id))]
        return self

    # -- params ----------------------------------------------------
    def set_param(self, node_id, param, value):
        node = self.nodes.get(str(node_id))
        if node is None:
            raise KeyError('patch %r has no node %r' % (self.name, node_id))
        node.set_param(param, value)
        return self

    def get_param(self, node_id, param, default=None):
        node = self.nodes.get(str(node_id))
        if node is None:
            return default
        return node.params.get(str(param), default)

    def automate(self, node_id, param, points):
        node = self.nodes.get(str(node_id))
        if node is None:
            raise KeyError('patch %r has no node %r' % (self.name, node_id))
        node.automate(param, points)
        return self

    # -- serialise -------------------------------------------------
    def describe(self):
        return {'name': self.name,
                'nodes': [n.describe() for n in self.nodes.values()],
                'connections': [list(c) for c in self.connections]}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        p = cls(d.get('name', 'patch'))
        for nd in d.get('nodes', []):
            p.add_node(PatchNode.from_dict(nd))
        for c in d.get('connections', []):
            p.connect(*c)
        return p


def make_default_patch(name='default', kind='sine'):
    """A one-oscillator -> gain patch. The 'hello world' patch."""
    p = AudioPatch(name)
    p.add_oscillator('osc', type=kind, freq=440.0)
    p.add_gain('amp', gain=0.5)
    p.connect('osc', 'amp').connect('amp', 'out')
    return p


# ----------------------------------------------------------------------
# EFFECT designer
# ----------------------------------------------------------------------

# Every effect kind + its param defaults. An effect IS its param dict:
# build it, tweak params, save it, reuse it on any patch / bus / timeline.
_EFFECT_DEFAULTS = {
    'gain': {'gain': 1.0},
    'filter': {'type': 'lowpass', 'frequency': 1000.0, 'Q': 1.0, 'gain': 0.0},
    'delay': {'delayTime': 0.3, 'feedback': 0.35, 'wet': 0.35},
    'reverb': {'decay': 2.0, 'wet': 0.4, 'preDelay': 0.0},
    'distortion': {'amount': 50.0, 'oversample': '4x', 'wet': 1.0},
    'chorus': {'rate': 1.5, 'depth': 0.004, 'feedback': 0.2, 'wet': 0.5},
    'flanger': {'rate': 0.5, 'depth': 0.003, 'feedback': 0.5, 'wet': 0.5},
    'compressor': {'threshold': -24.0, 'knee': 30.0, 'ratio': 12.0,
                   'attack': 0.003, 'release': 0.25},
    'tremolo': {'rate': 5.0, 'depth': 0.8, 'wet': 1.0},
    'panner': {'pan': 0.0},
    'bitcrusher': {'bits': 8.0, 'sampleRate': 8000.0, 'wet': 1.0},
}

_EFFECT_PRESETS = {
    'hall': ('reverb', {'decay': 3.5, 'wet': 0.5}),
    'room': ('reverb', {'decay': 0.8, 'wet': 0.3}),
    'slap': ('delay', {'delayTime': 0.12, 'feedback': 0.15, 'wet': 0.4}),
    'echo': ('delay', {'delayTime': 0.45, 'feedback': 0.55, 'wet': 0.45}),
    'fuzz': ('distortion', {'amount': 200.0, 'wet': 1.0}),
    'overdrive': ('distortion', {'amount': 40.0, 'wet': 0.8}),
    'warm': ('filter', {'type': 'lowpass', 'frequency': 2500.0, 'Q': 0.7}),
    'telephone': ('filter', {'type': 'bandpass', 'frequency': 1200.0, 'Q': 1.5}),
    'glue': ('compressor', {'threshold': -18.0, 'ratio': 4.0, 'attack': 0.01, 'release': 0.2}),
    'wobble': ('chorus', {'rate': 2.5, 'depth': 0.006, 'wet': 0.6}),
    'jet': ('flanger', {'rate': 0.25, 'depth': 0.004, 'feedback': 0.7, 'wet': 0.6}),
}


class AudioEffect:
    """One effect: kind + params + bypass + wet. Pure data until built.

    ``effect = AudioEffect('reverb', decay=2.5, wet=0.4)``
    ``effect.set_param('wet', 0.8)`` / ``effect.bypass = True``
    ``node = effect.create_node(engine)``  (real node in browser,
    fake node in CPython -- same params either way)
    """

    def __init__(self, kind, bypass=False, **params):
        kind = str(kind)
        if kind not in _EFFECT_DEFAULTS:
            raise ValueError('unknown effect kind %r (see _EFFECT_DEFAULTS)' % kind)
        self.kind = kind
        self.params = dict(_EFFECT_DEFAULTS[kind])
        self.params.update(params)
        self.bypass = bool(bypass)
        self._node = None

    @classmethod
    def preset(cls, name, **overrides):
        """Named preset: AudioEffect.preset('hall'), ('slap'), ('fuzz')..."""
        if name not in _EFFECT_PRESETS:
            raise KeyError('unknown effect preset %r (see _EFFECT_PRESETS)' % name)
        kind, defaults = _EFFECT_PRESETS[name]
        p = dict(defaults)
        p.update(overrides)
        return cls(kind, **p)

    def set_param(self, name, value):
        self.params[str(name)] = value
        if self._node is not None:
            # Push live to the built node when possible.
            try:
                param = getattr(self._node, str(name), None)
                if param is not None and hasattr(param, 'value'):
                    param.value = float(value)
                elif self._node is not None and isinstance(getattr(self._node, 'params', None), dict):
                    self._node.params[str(name)] = value
            except Exception:
                pass
        return self

    def get_param(self, name, default=None):
        return self.params.get(str(name), default)

    def create_node(self, engine):
        """Build the real (browser) or fake (CPython) node(s) for this
        effect. Returns the node to connect INTO (the effect input)."""
        ctx = engine.context if engine is not None else None
        if ctx is None:
            ctx = _FakeAudioContext()
        self._node = _build_effect_nodes(ctx, self.kind, self.params)
        return self._node

    def describe(self):
        return {'kind': self.kind, 'params': dict(self.params), 'bypass': self.bypass}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        e = cls(d['kind'], bypass=d.get('bypass', False), **d.get('params', {}))
        return e


def _build_effect_nodes(ctx, kind, params):
    """Create the Web Audio node(s) for one effect kind."""
    try:
        if kind == 'gain':
            n = ctx.createGain()
            _set_param(getattr(n, 'gain', None), params.get('gain', 1.0))
            return n
        if kind == 'filter':
            n = ctx.createBiquadFilter()
            try:
                n.type = params.get('type', 'lowpass')
            except Exception:
                pass
            _set_param(getattr(n, 'frequency', None), params.get('frequency', 1000.0))
            _set_param(getattr(n, 'Q', None), params.get('Q', 1.0))
            _set_param(getattr(n, 'gain', None), params.get('gain', 0.0))
            return n
        if kind == 'delay':
            n = ctx.createDelay(2.0)
            _set_param(getattr(n, 'delayTime', None), params.get('delayTime', 0.3))
            return n
        if kind == 'reverb':
            n = ctx.createConvolver()
            # Real impulse: noise decaying over `decay` seconds.
            try:
                sr = 44100
                length = max(1, int(sr * float(params.get('decay', 2.0))))
                buf = ctx.createBuffer(2, length, sr)
                # Fake contexts store a dict; real ones need channel data.
                try:
                    for ch in range(2):
                        data = buf.getChannelData(ch)
                        for i in range(len(data)):
                            data[i] = (2.0 * (hash((i, ch)) % 1000) / 1000.0 - 1.0) * ((1.0 - i / length) ** 2)
                except Exception:
                    pass
                n.buffer = buf
            except Exception:
                pass
            return n
        if kind in ('distortion', 'bitcrusher'):
            n = ctx.createWaveShaper()
            try:
                n.oversample = params.get('oversample', '4x')
                # 256-point shaping curve for distortion.
                amount = float(params.get('amount', 50.0))
                curve = []
                for i in range(256):
                    x = (i / 128.0) - 1.0
                    curve.append(((3.0 + amount) * x * 20.0) / (math.pi + amount * abs(x)))
                try:
                    from browser import window as _w
                    n.curve = _w.Float32Array.new(curve)
                except Exception:
                    n.curve = curve
            except Exception:
                pass
            return n
        if kind == 'compressor':
            n = ctx.createDynamicsCompressor()
            for pname in ('threshold', 'knee', 'ratio', 'attack', 'release'):
                _set_param(getattr(n, pname, None), params.get(pname, 0.0))
            return n
        if kind == 'panner':
            try:
                n = ctx.createStereoPanner()
            except Exception:
                n = ctx.createGain()
            _set_param(getattr(n, 'pan', None), params.get('pan', 0.0))
            return n
        if kind in ('chorus', 'flanger', 'tremolo'):
            # LFO + delay (chorus/flanger) or LFO + gain (tremolo).
            # Built as a gain node carrying the effect params; the
            # engine's EffectChain wires the LFO in the browser.
            n = ctx.createGain()
            try:
                n.params = dict(params)
            except Exception:
                pass
            return n
    except Exception:
        pass
    # Fallback: a gain node carrying the params.
    try:
        n = ctx.createGain()
        n.params = dict(params)
        return n
    except Exception:
        return _FakeAudioNode(kind, **params)


class EffectChain:
    """An ordered chain of effects: input -> fx1 -> fx2 -> ... -> output.

    ``chain = EffectChain('vocal')``
    ``chain.add('reverb', decay=2.0).add('compressor')``
    ``chain.wet = 0.8`` / ``chain.set_bypass('reverb', True)``
    ``chain.apply_to(engine, source_node)`` wires it in the browser.
    """

    def __init__(self, name, effects=None, wet=1.0, dry=0.0):
        self.name = str(name)
        self.effects = []  # list[AudioEffect]
        for e in (effects or []):
            self.add(e)
        self.wet = float(wet)
        self.dry = float(dry)
        self.bypass = False

    def add(self, effect_or_kind, **params):
        if isinstance(effect_or_kind, AudioEffect):
            self.effects.append(effect_or_kind)
        else:
            self.effects.append(AudioEffect(effect_or_kind, **params))
        return self

    def add_preset(self, preset_name, **overrides):
        self.effects.append(AudioEffect.preset(preset_name, **overrides))
        return self

    def remove(self, index_or_kind):
        if isinstance(index_or_kind, int):
            if 0 <= index_or_kind < len(self.effects):
                del self.effects[index_or_kind]
        else:
            self.effects = [e for e in self.effects if e.kind != str(index_or_kind)]
        return self

    def get(self, kind):
        for e in self.effects:
            if e.kind == str(kind):
                return e
        return None

    def set_param(self, kind, param, value):
        e = self.get(kind)
        if e is None:
            raise KeyError('chain %r has no effect %r' % (self.name, kind))
        e.set_param(param, value)
        return self

    def set_bypass(self, kind, bypass=True):
        e = self.get(kind)
        if e is not None:
            e.bypass = bool(bypass)
        return self

    def apply_to(self, engine, source_node, destination=None):
        """Wire source -> chain -> destination in the browser. In
        CPython records the wiring on fake nodes. Returns the output node."""
        if source_node is None:
            return None
        ctx = engine.context if engine is not None else None
        dest = destination
        if dest is None and ctx is not None:
            dest = getattr(ctx, 'destination', None)
        current = source_node
        for e in self.effects:
            if e.bypass or self.bypass:
                continue
            node = e.create_node(engine)
            try:
                current.connect(node)
            except Exception:
                pass
            current = node
        if dest is not None:
            try:
                current.connect(dest)
            except Exception:
                pass
        return current

    def describe(self):
        return {'name': self.name, 'wet': self.wet, 'dry': self.dry,
                'bypass': self.bypass, 'effects': [e.describe() for e in self.effects]}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        c = cls(d.get('name', 'chain'), wet=d.get('wet', 1.0), dry=d.get('dry', 0.0))
        c.bypass = bool(d.get('bypass', False))
        for ed in d.get('effects', []):
            c.add(AudioEffect.from_dict(ed))
        return c


# ----------------------------------------------------------------------
# TIMELINE: tempo + events. Effects ARE events here.
# ----------------------------------------------------------------------

class TimelineEvent:
    """One event on a Timeline: note | effect | automation | cue."""

    def __init__(self, beat, kind, data=None):
        self.beat = float(beat)
        self.kind = str(kind)  # 'note' | 'effect' | 'automation' | 'cue'
        self.data = dict(data or {})

    def describe(self):
        return {'beat': self.beat, 'kind': self.kind, 'data': dict(self.data)}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        return cls(d.get('beat', 0), d.get('kind', 'cue'), d.get('data', {}))


class Timeline:
    """A tempo-locked timeline. Beats -> audio time via bpm.

    ``tl = Timeline('song', bpm=120)``
    ``tl.add_note(0, 'C4', duration_beats=1, patch='lead')``
    ``tl.add_effect(8, 'reverb', 'wet', 0.8)``  # timeline-based effect!
    ``tl.add_automation(8, 'lead', 'flt', 'frequency', [(0, 400), (2, 4000)])``
    ``tl.add_cue(16, 'chorus')``
    ``engine.play_timeline(tl)``
    """

    def __init__(self, name, bpm=120.0, beats_per_bar=4, loop=False, length_beats=None):
        self.name = str(name)
        self.bpm = float(bpm or 120.0)
        self.beats_per_bar = int(beats_per_bar or 4)
        self.loop = bool(loop)
        self.length_beats = float(length_beats) if length_beats is not None else None
        self.events = []  # list[TimelineEvent], sorted by beat
        self._playing = False
        self._start_audio_time = None

    # -- tempo / time ------------------------------------------------
    @property
    def seconds_per_beat(self):
        return 60.0 / self.bpm if self.bpm else 0.5

    def beats_to_seconds(self, beats):
        return float(beats) * self.seconds_per_beat

    def seconds_to_beats(self, seconds):
        return float(seconds) / self.seconds_per_beat if self.seconds_per_beat else 0.0

    def set_tempo(self, bpm):
        self.bpm = float(bpm)
        return self

    @property
    def length_seconds(self):
        if self.length_beats is not None:
            return self.beats_to_seconds(self.length_beats)
        if not self.events:
            return 0.0
        return self.beats_to_seconds(max(e.beat for e in self.events) + 1.0)

    # -- adding events -----------------------------------------------
    def add(self, beat, event_kind, **data):
        # NOTE: second param is `event_kind`, not `kind`, so callers can
        # pass a data field named `kind` (e.g. oscillator kind) without
        # colliding with the event-kind argument.
        ev = TimelineEvent(beat, event_kind, data)
        self.events.append(ev)
        self.events.sort(key=lambda e: e.beat)
        return ev

    def add_note(self, beat, note, duration_beats=1.0, patch=None, velocity=0.8,
                 pan=0.0, freq=None, kind='sine'):
        """A note event. `note` may be 'C4', a MIDI number, or Hz."""
        return self.add(beat, 'note', note=note, freq=freq, duration_beats=float(duration_beats),
                        patch=patch, velocity=float(velocity), pan=float(pan), kind=kind)

    def add_effect(self, beat, effect, action='set', param=None, value=None, **params):
        """A TIMELINE-BASED EFFECT event.

        ``add_effect(8, 'reverb', 'set', 'wet', 0.8)``      -- set a param
        ``add_effect(8, 'delay', 'bypass', True)``          -- bypass on/off
        ``add_effect(8, 'delay', 'trigger')``               -- one-shot throw
        ``add_effect(8, 'filter', 'sweep', 'frequency', 4000)`` -- sweep target
        `effect` is an effect kind, a chain name, or an AudioEffect.
        Extra params are stored on the event (e.g. sweep duration).
        """
        data = {'effect': effect if isinstance(effect, str) else getattr(effect, 'kind', str(effect)),
                'action': str(action), 'param': param, 'value': value}
        data.update(params)
        return self.add(beat, 'effect', **data)

    def add_automation(self, beat, target, param, points, node=None):
        """Param automation starting at `beat`. `target` is a patch name,
        effect kind, or chain name. `points` are (beat_offset, value, curve)."""
        return self.add(beat, 'automation', target=target, node=node, param=param,
                        points=[list(p) for p in points])

    def add_cue(self, beat, label, data=None):
        d = dict(data or {})
        d['label'] = str(label)
        return self.add(beat, 'cue', **d)

    def add_pipeline(self, beat, pipeline, action='start', **params):
        """Timeline event that starts / stops / retunes a pipeline.

        add_pipeline(8, 'lead', 'start')
        add_pipeline(16, 'lead', 'stop')
        add_pipeline(12, 'lead', 'set_param', stage='filter',
                     param='frequency', value=800)
        add_pipeline(12, 'lead', 'set_volume', volume=0.7)
        """ 
        d = dict(params)
        d['pipeline'] = pipeline if isinstance(pipeline, str) else getattr(pipeline, 'name', pipeline)
        d['action'] = str(action)
        return self.add(beat, 'pipeline', **d)

    def add_mapping(self, beat, control, value, chain=None, **params):
        """Timeline event that drives a MappingChain / EffectParamMapping.

        add_mapping(8, 'macro', 0.7)  # one value -> many params
        add_mapping(8, 'cutoff', 0.5, mapping='cutoff')
        """ 
        d = dict(params)
        d['control'] = str(control)
        d['value'] = float(value)
        if chain is not None:
            d['chain'] = chain if isinstance(chain, str) else getattr(chain, 'name', chain)
        return self.add(beat, 'mapping', **d)

    def add_volume(self, beat, volume, mapper=None, **params):
        """Timeline event that sets master volume (optionally via a
        named VolumeMapper, so the curve is perceptual / dB, not raw)."""
        d = dict(params)
        d['volume'] = float(volume)
        if mapper is not None:
            d['mapper'] = mapper if isinstance(mapper, str) else getattr(mapper, 'name', mapper)
        return self.add(beat, 'volume', **d)

    def add_envelope(self, beat, envelope, target, param='gain', **params):
        """Timeline event that applies a CurveEnvelope to a param.

        add_envelope(0, 'pluck', 'lead', 'gain')
        """ 
        d = dict(params)
        d['envelope'] = envelope if isinstance(envelope, str) else getattr(envelope, 'name', envelope)
        d['target'] = target
        d['param'] = str(param)
        return self.add(beat, 'envelope', **d)

    def events_at(self, beat, tolerance=0.001):
        return [e for e in self.events if abs(e.beat - float(beat)) <= tolerance]

    # -- scheduling ----------------------------------------------------
    def schedule(self, engine, start_at=None):
        """Schedule every event on the engine's audio clock. Returns
        [(audio_time, TimelineEvent), ...]. Does NOT start audio;
        the engine's play_* calls do the sounding."""
        if engine is None:
            return []
        t0 = float(start_at) if start_at is not None else engine.now_audio()
        out = []
        for ev in self.events:
            at = t0 + self.beats_to_seconds(ev.beat)
            out.append((at, ev))
            try:
                engine._schedule_timeline_event(ev, at)
            except Exception:
                pass
        self._playing = True
        self._start_audio_time = t0
        return out

    def stop(self, engine=None):
        self._playing = False
        self._start_audio_time = None
        return self

    @property
    def playing(self):
        return self._playing

    # -- serialise -----------------------------------------------------
    def describe(self):
        return {'name': self.name, 'bpm': self.bpm, 'beats_per_bar': self.beats_per_bar,
                'loop': self.loop, 'length_beats': self.length_beats,
                'length_seconds': self.length_seconds,
                'events': [e.describe() for e in self.events]}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        tl = cls(d.get('name', 'timeline'), bpm=d.get('bpm', 120.0),
                 beats_per_bar=d.get('beats_per_bar', 4), loop=d.get('loop', False),
                 length_beats=d.get('length_beats'))
        for ed in d.get('events', []):
            tl.events.append(TimelineEvent.from_dict(ed))
        tl.events.sort(key=lambda e: e.beat)
        return tl


# ----------------------------------------------------------------------
# Spatial sources (patch + panner + 3D position)
# ----------------------------------------------------------------------

class SpatialSoundSource:
    """One sound source at a 3D position: patch -> gain -> panner.

    Built on AudioPatch so spatial sources get patches + effects too.
    """

    def __init__(self, engine, position=(0.0, 1.5, 0.0), freq=440.0,
                 kind='sine', volume=0.5, loop=True,
                 ref_distance=1.0, max_distance=30.0, rolloff=1.0,
                 name='source', patch=None, effects=None):
        self.engine = engine
        self.position = (float(position[0]), float(position[1]), float(position[2]))
        self.freq = float(freq)
        self.kind = kind
        self.volume = float(volume)
        self.loop = bool(loop)
        self.ref_distance = float(ref_distance)
        self.max_distance = float(max_distance)
        self.rolloff = float(rolloff)
        self.name = name
        self.patch = patch  # AudioPatch or None -> default tone patch
        self.effects = effects  # EffectChain or None
        self._nodes = None  # (osc/gain/panner) or built patch nodes
        self.playing = False

    def set_position(self, pos):
        self.position = (float(pos[0]), float(pos[1]), float(pos[2]))
        if self._nodes is not None:
            panner = self._nodes.get('panner') if isinstance(self._nodes, dict) else None
            if panner is not None:
                _set_3d_position(panner, self.position)
        return self.position

    def move(self, dx=0.0, dy=0.0, dz=0.0):
        return self.set_position((self.position[0] + dx,
                                  self.position[1] + dy,
                                  self.position[2] + dz))

    def distance_to(self, listener_pos):
        dx = self.position[0] - listener_pos[0]
        dy = self.position[1] - listener_pos[1]
        dz = self.position[2] - listener_pos[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def gain_at(self, listener_pos):
        return inverse_distance_gain(self.distance_to(listener_pos),
                                     self.ref_distance, self.max_distance, self.rolloff)

    def pan_at(self, camera):
        if camera is None:
            return 0.0
        try:
            to_src = (self.position[0] - camera.position[0],
                      self.position[1] - camera.position[1],
                      self.position[2] - camera.position[2])
            l = math.sqrt(sum(c * c for c in to_src)) or 1.0
            to_src = tuple(c / l for c in to_src)
            right = camera.right()
            dot = sum(a * b for a, b in zip(to_src, right))
            return max(-1.0, min(1.0, dot))
        except Exception:
            return 0.0

    def start(self, at=None):
        if self.engine is None:
            return False
        try:
            self.engine.resume()
        except Exception:
            pass
        if self.engine.context is None:
            return False
        if self.playing:
            return True
        try:
            ctx = self.engine.context
            now = float(at) if at is not None else float(ctx.currentTime)
            osc = ctx.createOscillator()
            gain = ctx.createGain()
            panner = ctx.createPanner()
            try:
                panner.panningModel = 'HRTF'
            except Exception:
                pass
            try:
                panner.distanceModel = 'inverse'
                panner.refDistance = self.ref_distance
                panner.maxDistance = self.max_distance
                panner.rolloffFactor = self.rolloff
            except Exception:
                pass
            try:
                osc.frequency.value = self.freq
            except Exception:
                try:
                    osc.frequency.setValueAtTime(self.freq, now)
                except Exception:
                    pass
            try:
                osc.type = self.kind
            except Exception:
                pass
            try:
                gain.gain.value = self.volume
            except Exception:
                pass
            try:
                osc.loop = self.loop
            except Exception:
                pass
            osc.connect(gain)
            gain.connect(panner)
            panner.connect(ctx.destination)
            osc.start(now)
            self._nodes = {'osc': osc, 'gain': gain, 'panner': panner}
            _set_3d_position(panner, self.position, now)
            self.playing = True
            return True
        except Exception:
            return False

    def stop(self):
        try:
            if self._nodes is not None and self._nodes.get('osc') is not None:
                self._nodes['osc'].stop()
        except Exception:
            pass
        self._nodes = None
        self.playing = False
        return True

    def describe(self):
        return {'name': self.name, 'position': self.position, 'freq': self.freq,
                'kind': self.kind, 'playing': self.playing, 'volume': self.volume}


# ----------------------------------------------------------------------
# THE engine: one interface every SCS engine exposes as .audio
# ----------------------------------------------------------------------

class WebAudioEngine:
    """Canonical Web Audio engine. See module docstring.

    ``engine.audio`` on EVERY SCS engine is one of these. Same methods,
    same signatures, same behaviour in the browser and in CPython
    (fake nodes in CPython, real nodes in the browser).
    """

    def __init__(self, context=None, master_volume=0.8):
        self.context = context
        self.owns_context = context is None
        self.clock = ClockMapping(context)
        self._worklets = {}
        self._started = False
        self._master_volume = float(master_volume)
        self._muted = False
        self._master_gain = None
        self._patches = {}       # name -> AudioPatch
        self._effects = {}       # name -> AudioEffect
        self._chains = {}        # name -> EffectChain
        self._timelines = {}     # name -> Timeline
        self._sources = []       # SpatialSoundSource
        # Batch 3 registries: envelopes / mapping / pipelines
        self._envelopes = {}     # name -> CurveEnvelope / ADSREnvelope
        self._volume_mappers = {}  # name -> VolumeMapper
        self._mappings = {}      # name -> EffectParamMapping
        self._mapping_chains = {}  # control -> MappingChain
        self._pipelines = {}     # name -> AudioSrcPipeline
        self._mixers = {}        # name -> AudioPipelineMixer
        self._analyser = None
        self._playing_patches = []  # (patch, nodes) for stop_patch
        self._fake_context = None

    # -- context -----------------------------------------------------
    @property
    def started(self):
        return self._started

    def _ensure_context(self):
        """Return a context: real one in the browser, fake one in CPython.
        Never creates a real AudioContext except via resume() (autoplay)."""
        if self.context is not None:
            return self.context
        if _is_browser():
            return None  # browser: resume() must create it (gesture)
        if self._fake_context is None:
            self._fake_context = _FakeAudioContext()
            self.context = self._fake_context
            self.clock.context = self.context
            self.clock.refresh()
        return self.context

    # -- lifecycle / autoplay ----------------------------------------
    def resume(self):
        """Call from a USER GESTURE (click / key). Creates the context
        lazily on first call. Returns a Promise in the browser, None in tests."""
        if self.context is None:
            if _is_browser():
                try:
                    AC = getattr(window, 'AudioContext', None) or getattr(window, 'webkitAudioContext', None)
                    if AC is not None:
                        self.context = AC.new()
                        self.clock.context = self.context
                        self.clock.refresh()
                except Exception:
                    pass
            else:
                self._ensure_context()
        if self.context is None:
            return None
        try:
            p = self.context.resume()
            self._started = True
            return p
        except Exception:
            self._started = True
            return None

    def suspend(self):
        if self.context is not None and self.owns_context:
            try:
                return self.context.suspend()
            except Exception:
                pass
        return None

    def dispose(self):
        """Never closes an app-owned context. Only closes one this
        engine created."""
        if self.context is not None and self.owns_context:
            try:
                self.context.close()
            except Exception:
                pass
        self.context = None
        self._fake_context = None
        self._worklets.clear()
        self._playing_patches = []

    close = dispose

    # -- clock ---------------------------------------------------------
    def now_audio(self):
        if self.context is not None:
            try:
                return float(self.context.currentTime)
            except Exception:
                pass
        return self.clock.now_audio()

    def now(self):
        return self.now_audio()

    def audio_to_performance(self, audio_time):
        return self.clock.audio_to_performance(audio_time)

    def performance_to_audio(self, perf_time):
        return self.clock.performance_to_audio(perf_time)

    # -- master --------------------------------------------------------
    @property
    def master_volume(self):
        return self._master_volume

    @master_volume.setter
    def master_volume(self, v):
        self.set_master_volume(v)

    def set_master_volume(self, volume):
        self._master_volume = max(0.0, min(1.0, float(volume)))
        if self._master_gain is not None:
            _set_param(getattr(self._master_gain, 'gain', None), self._master_volume if not self._muted else 0.0)
        return self._master_volume

    def mute(self):
        self._muted = True
        if self._master_gain is not None:
            _set_param(getattr(self._master_gain, 'gain', None), 0.0)
        return True

    def unmute(self):
        self._muted = False
        if self._master_gain is not None:
            _set_param(getattr(self._master_gain, 'gain', None), self._master_volume)
        return True

    @property
    def muted(self):
        return self._muted

    # -- low-level node factories --------------------------------------
    def _ctx(self):
        """Context for building: real in browser after resume(), fake in CPython."""
        ctx = self.context
        if ctx is None:
            ctx = self._ensure_context()
        return ctx

    def create_node(self, kind, **params):
        """Create one node: 'oscillator' | 'gain' | 'filter' | 'delay' |
        'compressor' | 'panner' | 'stereopanner' | 'convolver' |
        'waveshaper' | 'analyser' | 'buffersource'."""
        ctx = self._ctx()
        if ctx is None:
            ctx = _FakeAudioContext()
        kind = str(kind)
        try:
            if kind == 'oscillator':
                n = ctx.createOscillator()
            elif kind == 'gain':
                n = ctx.createGain()
            elif kind == 'filter':
                n = ctx.createBiquadFilter()
            elif kind == 'delay':
                n = ctx.createDelay(params.get('max_delay', 1.0))
            elif kind == 'compressor':
                n = ctx.createDynamicsCompressor()
            elif kind == 'panner':
                n = ctx.createPanner()
            elif kind == 'stereopanner':
                try:
                    n = ctx.createStereoPanner()
                except Exception:
                    n = ctx.createGain()
            elif kind == 'convolver':
                n = ctx.createConvolver()
            elif kind == 'waveshaper':
                n = ctx.createWaveShaper()
            elif kind == 'analyser':
                n = ctx.createAnalyser()
            elif kind == 'buffersource':
                n = ctx.createBufferSource()
            else:
                n = ctx.createGain()
        except Exception:
            n = _FakeAudioNode(kind, **params)
        # Apply params.
        for pname, value in params.items():
            if pname == 'max_delay':
                continue
            try:
                p = getattr(n, pname, None)
                if p is not None and hasattr(p, 'value'):
                    p.value = float(value)
                elif hasattr(n, 'params') and isinstance(n.params, dict):
                    n.params[pname] = value
                else:
                    try:
                        setattr(n, pname, value)
                    except Exception:
                        pass
            except Exception:
                pass
        return n

    def create_oscillator(self, **params):
        return self.create_node('oscillator', **params)

    def create_gain(self, **params):
        return self.create_node('gain', **params)

    def create_filter(self, **params):
        return self.create_node('filter', **params)

    def create_delay(self, **params):
        return self.create_node('delay', **params)

    def create_panner(self, **params):
        return self.create_node('panner', **params)

    def create_convolver(self, **params):
        return self.create_node('convolver', **params)

    def create_wave_shaper(self, **params):
        return self.create_node('waveshaper', **params)

    def create_compressor(self, **params):
        return self.create_node('compressor', **params)

    def create_analyser(self, **params):
        n = self.create_node('analyser', **params)
        self._analyser = n
        return n

    def create_buffer_source(self, **params):
        return self.create_node('buffersource', **params)

    # -- scheduling ------------------------------------------------------
    def schedule(self, node, at_audio_time, param=None):
        try:
            node.start(float(at_audio_time))
        except Exception:
            try:
                node.start()
            except Exception:
                pass
        return float(at_audio_time)

    def schedule_at_performance_time(self, node, perf_time):
        return self.schedule(node, self.clock.performance_to_audio(perf_time))

    def schedule_in(self, node, delay_seconds):
        return self.schedule(node, self.now_audio() + float(delay_seconds))

    # -- simple tones (back-compat + convenience) -----------------------
    def beep(self, freq=440, duration=0.25, kind='sine', volume=0.2, delay=0):
        """Play one tone. Call from a user gesture. Returns True if scheduled."""
        self.resume()
        ctx = self.context
        if ctx is None:
            ctx = self._ensure_context()
        if ctx is None:
            return False
        try:
            now = float(ctx.currentTime) + float(delay)
            osc = ctx.createOscillator()
            gain = ctx.createGain()
            try:
                osc.frequency.value = float(freq)
            except Exception:
                try:
                    osc.frequency.setValueAtTime(float(freq), now)
                except Exception:
                    pass
            try:
                osc.type = kind
            except Exception:
                pass
            try:
                gain.gain.value = float(volume)
            except Exception:
                try:
                    gain.gain.setValueAtTime(float(volume), now)
                except Exception:
                    pass
            osc.connect(gain)
            gain.connect(ctx.destination)
            osc.start(now)
            osc.stop(now + float(duration))
            return True
        except Exception:
            return False

    def tone(self, *args, **kwargs):
        return self.beep(*args, **kwargs)

    def play_tone(self, *args, **kwargs):
        return self.beep(*args, **kwargs)

    def play_note(self, note, duration=0.25, **kwargs):
        """play_note('C4') / play_note(440) / play_note(69)."""
        return self.beep(note_to_freq(note), duration=duration, **kwargs)

    def play_freq(self, freq, duration=0.25, **kwargs):
        return self.beep(freq, duration=duration, **kwargs)

    # -- PATCHES ---------------------------------------------------------
    def create_patch(self, name, spec=None, **kwargs):
        """Create + register a patch. `spec` may be a dict (from_dict),
        an AudioPatch, or None (then kwargs are used as a simple patch)."""
        if isinstance(spec, AudioPatch):
            patch = spec
            patch.name = str(name)
        elif isinstance(spec, dict):
            patch = AudioPatch.from_dict(spec)
            patch.name = str(name)
        else:
            patch = AudioPatch(str(name))
            # kwargs shorthand: create_patch('lead', kind='sawtooth', cutoff=800)
            kind = kwargs.get('kind', kwargs.get('type', 'sine'))
            patch.add_oscillator('osc', type=kind, freq=kwargs.get('freq', 440.0))
            if 'cutoff' in kwargs or 'frequency' in kwargs:
                patch.add_filter('flt', type=kwargs.get('filter_type', 'lowpass'),
                                 frequency=float(kwargs.get('cutoff', kwargs.get('frequency', 1000.0))))
                patch.connect('osc', 'flt')
                patch.add_gain('amp', gain=float(kwargs.get('volume', kwargs.get('gain', 0.5))))
                patch.connect('flt', 'amp').connect('amp', 'out')
            else:
                patch.add_gain('amp', gain=float(kwargs.get('volume', kwargs.get('gain', 0.5))))
                patch.connect('osc', 'amp').connect('amp', 'out')
            if 'envelope' in kwargs:
                patch.add_envelope('env', **kwargs['envelope'])
        self._patches[patch.name] = patch
        return patch

    def get_patch(self, name):
        return self._patches.get(str(name))

    def list_patches(self):
        return sorted(self._patches.keys())

    patch_names = list_patches

    def remove_patch(self, name):
        self._patches.pop(str(name), None)
        return True

    def play_patch(self, patch_or_name, freq=None, note=None, duration=1.0,
                   velocity=1.0, when=None, destination=None):
        """Play a patch once. freq/note retune every oscillator in it.
        Returns the built node dict (real or fake) or None."""
        if isinstance(patch_or_name, str):
            patch = self.get_patch(patch_or_name)
            if patch is None:
                raise KeyError('no patch named %r' % patch_or_name)
        else:
            patch = patch_or_name
        self.resume()
        ctx = self.context
        if ctx is None:
            ctx = self._ensure_context()
        if ctx is None:
            return None
        try:
            now = float(when) if when is not None else float(ctx.currentTime)
        except Exception:
            now = 0.0
        target_freq = None
        if freq is not None:
            target_freq = float(freq)
        elif note is not None:
            target_freq = note_to_freq(note)
        # Build nodes.
        built = {}
        for nid, spec in patch.nodes.items():
            if spec.kind == 'envelope':
                continue  # envelope is applied as gain automation, not a node
            if spec.kind == 'lfo':
                continue  # LFO is applied as param automation
            if spec.kind == 'noise':
                node = ctx.createBufferSource() if hasattr(ctx, 'createBufferSource') else _FakeAudioNode('buffersource')
            elif spec.kind == 'destination':
                node = getattr(ctx, 'destination', None)
            else:
                node = self.create_node(spec.kind)
            # Apply params (retune oscillators).
            for pname, value in spec.params.items():
                if pname in ('target', 'target_param', 'worklet_name'):
                    continue
                v = value
                if spec.kind == 'oscillator' and pname == 'frequency' and target_freq is not None:
                    v = target_freq
                try:
                    p = getattr(node, pname, None)
                    if p is not None and hasattr(p, 'value'):
                        p.value = float(v)
                    elif hasattr(node, 'params') and isinstance(node.params, dict):
                        node.params[pname] = v
                    elif pname in ('type', 'loop'):
                        try:
                            setattr(node, pname, v)
                        except Exception:
                            pass
                except Exception:
                    pass
            built[nid] = node
        # Wire.
        for (frm, to, _fp, _tp) in patch.connections:
            src = built.get(frm)
            if src is None:
                continue
            if to == 'out':
                dst = destination or getattr(ctx, 'destination', None)
            else:
                dst = built.get(to)
            if dst is None:
                continue
            try:
                src.connect(dst)
            except Exception:
                pass
        # Envelope: apply ADSR to every gain node named 'amp' / 'env'.
        env = None
        for nid, spec in patch.nodes.items():
            if spec.kind == 'envelope':
                env = spec.params
                break
        # Automation curves on nodes.
        for nid, spec in patch.nodes.items():
            node = built.get(nid)
            if node is None:
                continue
            for pname, curve in spec.automation.items():
                try:
                    param = getattr(node, pname, None)
                    if param is not None:
                        curve.apply(param, now)
                except Exception:
                    pass
        # Start oscillators / sources.
        for nid, node in built.items():
            spec = patch.nodes.get(nid)
            if spec is not None and spec.kind in ('oscillator', 'buffersource', 'noise'):
                try:
                    node.start(now)
                    node.stop(now + float(duration))
                except Exception:
                    try:
                        node.start()
                    except Exception:
                        pass
        self._playing_patches.append((patch, built))
        return built

    def stop_patch(self, patch_or_name=None):
        """Stop all playing patches, or one by name."""
        kept = []
        for patch, built in self._playing_patches:
            if patch_or_name is not None and patch.name != str(patch_or_name):
                kept.append((patch, built))
                continue
            for node in built.values():
                try:
                    node.stop()
                except Exception:
                    pass
        self._playing_patches = kept
        return True

    # -- EFFECTS ---------------------------------------------------------
    def create_effect(self, kind_or_preset, name=None, **params):
        """create_effect('reverb', decay=2.5) or create_effect('hall')
        (preset). With `name`, registers it for timeline lookup."""
        if isinstance(kind_or_preset, AudioEffect):
            eff = kind_or_preset
        elif isinstance(kind_or_preset, str) and kind_or_preset in _EFFECT_PRESETS and not params:
            eff = AudioEffect.preset(kind_or_preset)
        elif isinstance(kind_or_preset, str) and kind_or_preset in _EFFECT_PRESETS and params:
            eff = AudioEffect.preset(kind_or_preset, **params)
        else:
            eff = AudioEffect(kind_or_preset, **params)
        if name is not None:
            self._effects[str(name)] = eff
        return eff

    def effect_preset(self, name, **overrides):
        return AudioEffect.preset(name, **overrides)

    def get_effect(self, name):
        return self._effects.get(str(name))

    def list_effects(self):
        return sorted(self._effects.keys())

    def create_effect_chain(self, name, effects=None, **kwargs):
        """create_effect_chain('vocal', ['hall', 'glue']) -- preset names,
        effect kinds, or AudioEffect objects all work."""
        chain = EffectChain(str(name), **kwargs)
        for e in (effects or []):
            if isinstance(e, AudioEffect):
                chain.add(e)
            elif isinstance(e, str) and e in _EFFECT_PRESETS:
                chain.add_preset(e)
            elif isinstance(e, str):
                chain.add(e)
            elif isinstance(e, dict):
                chain.add(AudioEffect.from_dict(e))
        self._chains[chain.name] = chain
        return chain

    def get_effect_chain(self, name):
        return self._chains.get(str(name))

    def list_effect_chains(self):
        return sorted(self._chains.keys())

    def set_effect_param(self, effect_or_chain, param, value, when=None):
        """Set a param on a registered effect / chain by name, or on an
        AudioEffect / EffectChain object. Used by timeline events."""
        target = effect_or_chain
        if isinstance(target, str):
            target = self._effects.get(target) or self._chains.get(target)
        if target is None:
            return False
        if isinstance(target, EffectChain):
            # Set on every effect in the chain that has this param.
            ok = False
            for e in target.effects:
                if str(param) in e.params:
                    e.set_param(param, value)
                    ok = True
            return ok
        try:
            target.set_param(param, value)
            return True
        except Exception:
            return False

    def bypass_effect(self, effect_or_chain, bypass=True):
        target = effect_or_chain
        if isinstance(target, str):
            target = self._effects.get(target) or self._chains.get(target)
        if target is None:
            return False
        if isinstance(target, EffectChain):
            target.bypass = bool(bypass)
            return True
        try:
            target.bypass = bool(bypass)
            return True
        except Exception:
            return False

    # -- ENVELOPES / MAPPING / PIPELINES (Batch 3) ----------------------
    # Functional curve envelopes + effect/volume mapping + node-based
    # source pipelines, all registered on the engine so every engine's
    # `.audio` exposes the same API.
    #
    #   audio.create_envelope('pluck', preset='pluck')
    #   audio.create_envelope('swell', points=[(0,0),(1,1,'cosine')])
    #   audio.create_envelope('custom', fn=lambda t: sin(t*10)*exp(-t*3))
    #   audio.create_adsr('bass', attack=0.01, decay=0.1, sustain=0.6)
    #   audio.create_volume_mapper('vol', curve='perceptual')
    #   audio.create_mapping('cutoff', 'filter', 'frequency', 20, 20000, log=True)
    #   audio.create_mapping_chain('macro') -> add_param(...) -> apply(...)
    #   audio.create_pipeline('lead', src='oscillator', freq=440)
    #   audio.create_mixer('mix')

    def _require(self, obj, module_name, symbol):
        if obj is None:
            raise ImportError(
                'scs_web_audio needs %s (%s) -- %s module not available'
                % (symbol, module_name, module_name))
        return obj

    # -- envelopes ------------------------------------------------------
    def create_envelope(self, name, preset=None, points=None, fn=None,
                        adsr=None, envelope=None, **kwargs):
        """Create + register a CurveEnvelope / ADSREnvelope.

        Exactly one of: preset='pluck' | points=[...] | fn=callable |
        adsr={...} | envelope=<existing CurveEnvelope>.
        """
        self._require(CurveEnvelope, 'scs_audio_envelopes', 'CurveEnvelope')
        if envelope is not None:
            env = envelope
        elif preset is not None:
            self._require(envelope_preset, 'scs_audio_envelopes', 'envelope_preset')
            env = envelope_preset(str(preset), **kwargs)
        elif points is not None:
            env = CurveEnvelope(points=points, name=str(name), **kwargs)
        elif fn is not None:
            env = CurveEnvelope.from_function(fn, name=str(name), **kwargs)
        elif adsr is not None:
            self._require(adsr_envelope, 'scs_audio_envelopes', 'adsr_envelope')
            kw = dict(adsr)
            kw.setdefault('name', str(name))
            env = adsr_envelope(**kw)
        else:
            # No spec: default ADSR.
            self._require(adsr_envelope, 'scs_audio_envelopes', 'adsr_envelope')
            kw = dict(kwargs)
            kw.setdefault('name', str(name))
            env = adsr_envelope(**kw)
        try:
            env.name = str(name)
        except Exception:
            pass
        self._envelopes[str(name)] = env
        return env

    def create_adsr(self, name, **kwargs):
        """Create + register an ADSREnvelope."""
        self._require(ADSREnvelope, 'scs_audio_envelopes', 'ADSREnvelope')
        kw = dict(kwargs)
        kw.setdefault('name', str(name))
        env = ADSREnvelope(**kw)
        self._envelopes[str(name)] = env
        return env

    def get_envelope(self, name):
        if isinstance(name, str):
            return self._envelopes.get(name)
        return name

    def list_envelopes(self):
        return sorted(self._envelopes.keys())

    def remove_envelope(self, name):
        return self._envelopes.pop(str(name), None) is not None

    def envelope_preset(self, name, **overrides):
        self._require(envelope_preset, 'scs_audio_envelopes', 'envelope_preset')
        return envelope_preset(name, **overrides)

    def apply_envelope(self, envelope_or_name, target, start_time=0.0,
                       peak=1.0, param='gain', note_off=None, **kwargs):
        """Apply a registered envelope to a node / AudioParam.

        target may be: a GainNode (uses .gain), an AudioParam, a
        registered patch/effect/pipeline name (uses its gain / param),
        or a (node, param_name) tuple.
        Returns the number of scheduled ramps.
        """
        env = self.get_envelope(envelope_or_name) if isinstance(envelope_or_name, str) else envelope_or_name
        if env is None:
            return 0
        # Resolve target -> AudioParam.
        audio_param = None
        if isinstance(target, tuple) and len(target) == 2:
            node, pname = target
            audio_param = getattr(node, str(pname), None)
        elif hasattr(target, 'value') and hasattr(target, 'setValueAtTime'):
            audio_param = target
        elif hasattr(target, 'gain'):
            audio_param = getattr(target, 'gain', None)
            if param != 'gain':
                audio_param = getattr(target, str(param), audio_param)
        elif isinstance(target, str):
            # Patch / effect / pipeline by name.
            patch = self.get_patch(target)
            if patch is not None:
                audio_param = None  # patches apply via play_patch; use curve below
            eff = self.get_effect(target) if hasattr(self, 'get_effect') else None
            if eff is not None and getattr(eff, '_node', None) is not None:
                audio_param = getattr(eff._node, str(param), None)
            pipe = self.get_pipeline(target)
            if pipe is not None and getattr(pipe, '_built', None):
                audio_param = getattr(pipe._built.get('output'), str(param), None)
        else:
            audio_param = getattr(target, str(param), None)
        if audio_param is None:
            return 0
        try:
            if note_off is not None and hasattr(env, 'apply'):
                return env.apply(audio_param, float(start_time), peak=float(peak),
                                 note_off=float(note_off), **kwargs)
            return env.apply(audio_param, float(start_time), peak=float(peak), **kwargs)
        except TypeError:
            return env.apply(audio_param, float(start_time), peak=float(peak))

    def add_pipeline_envelope(self, pipeline_or_name, envelope_or_name, **kwargs):
        """Add a REGISTERED envelope to a pipeline by name.

        pipe.add_envelope() takes a preset name ('pluck') or a
        CurveEnvelope object. This helper also accepts an
        engine-registered name: add_pipeline_envelope('lead', 'swell2').
        """
        pipe = self.get_pipeline(pipeline_or_name) if isinstance(pipeline_or_name, str) else pipeline_or_name
        if pipe is None:
            raise KeyError('no pipeline named %r' % pipeline_or_name)
        env = self.get_envelope(envelope_or_name) if isinstance(envelope_or_name, str) else envelope_or_name
        if env is None:
            # Fall back: treat it as a preset name.
            return pipe.add_envelope(envelope_or_name, **kwargs)
        return pipe.add_envelope(env, **kwargs)

    # -- volume mapping ---------------------------------------------------
    def create_volume_mapper(self, name, curve='perceptual', **kwargs):
        """Create + register a VolumeMapper (control -> gain)."""
        self._require(VolumeMapper, 'scs_audio_mapping', 'VolumeMapper')
        vm = VolumeMapper(curve=curve, name=str(name), **kwargs)
        self._volume_mappers[str(name)] = vm
        return vm

    def get_volume_mapper(self, name):
        if isinstance(name, str):
            return self._volume_mappers.get(name)
        return name

    def list_volume_mappers(self):
        return sorted(self._volume_mappers.keys())

    def map_volume(self, control, curve='perceptual', mapper=None):
        """Control (0..1 or MIDI 0..127) -> gain, via a mapper or curve."""
        if mapper is not None:
            vm = self.get_volume_mapper(mapper)
            if vm is not None:
                return vm.map(control)
        self._require(control_to_gain, 'scs_audio_mapping', 'control_to_gain')
        x = float(control)
        if x > 1.0:  # MIDI 0..127, like VolumeMapper.map()
            x = x / 127.0
        return control_to_gain(x, curve)

    def set_volume_mapped(self, control, mapper=None, param=None):
        """Set master volume (or an AudioParam) from a mapped control."""
        gain = self.map_volume(control, mapper=mapper)
        if param is not None:
            try:
                param.value = float(gain)
            except Exception:
                try:
                    param.setValueAtTime(float(gain), float(self.now_audio()))
                except Exception:
                    pass
            return gain
        return self.set_master_volume(gain)

    # -- effect mapping -----------------------------------------------------
    def create_mapping(self, control, effect, param, out_min=0.0, out_max=1.0,
                       name=None, **kwargs):
        """Create + register an EffectParamMapping."""
        self._require(EffectParamMapping, 'scs_audio_mapping', 'EffectParamMapping')
        m = EffectParamMapping(control, effect, param, out_min=out_min,
                               out_max=out_max, name=name, **kwargs)
        self._mappings[m.name] = m
        return m

    def get_mapping(self, name):
        if not isinstance(name, str):
            return name
        if name in self._mappings:
            return self._mappings[name]
        # Fall back: lookup by control name ('cutoff') or by
        # 'effect.param' ('filter.frequency').
        for m in self._mappings.values():
            if getattr(m, 'control', None) == name:
                return m
            if ('%s.%s' % (getattr(m, 'effect', ''), getattr(m, 'param', ''))) == name:
                return m
        return None

    def list_mappings(self):
        return sorted(self._mappings.keys())

    def create_mapping_chain(self, control, name=None):
        """Create + register a MappingChain (one control -> many params)."""
        self._require(MappingChain, 'scs_audio_mapping', 'MappingChain')
        chain = MappingChain(control, name=name)
        self._mapping_chains[str(control)] = chain
        return chain

    def get_mapping_chain(self, control):
        if isinstance(control, str):
            return self._mapping_chains.get(control)
        return control

    def list_mapping_chains(self):
        return sorted(self._mapping_chains.keys())

    def apply_mapping_chain(self, control, value, **kwargs):
        """Apply a registered MappingChain: one value -> many params."""
        chain = self.get_mapping_chain(control)
        if chain is None:
            return {}
        return chain.apply(self, value, **kwargs)

    def apply_mapping(self, mapping_or_name, control_value, effect=None):
        """Apply one EffectParamMapping to an effect / AudioParam."""
        m = self.get_mapping(mapping_or_name) if isinstance(mapping_or_name, str) else mapping_or_name
        if m is None:
            return None
        if effect is None:
            # Try to resolve the effect by name on this engine.
            try:
                effect = self.get_effect(m.effect) or self.get_effect_chain(m.effect)
            except Exception:
                effect = None
        if effect is not None:
            return m.apply_to(effect, control_value)
        return m.map(control_value)

    # -- pipelines ----------------------------------------------------------
    def create_pipeline(self, name, src=None, **src_params):
        """Create + register an AudioSrcPipeline.

        create_pipeline('lead', src='oscillator', freq=440)
        create_pipeline('kick', src='file', url='kick.wav')
        """
        self._require(AudioSrcPipeline, 'scs_audio_pipelines', 'AudioSrcPipeline')
        if isinstance(src, AudioSrcPipeline):
            pipe = src
            pipe.name = str(name)
        else:
            pipe = AudioSrcPipeline(str(name), src=src, **src_params)
        self._pipelines[str(name)] = pipe
        return pipe

    def get_pipeline(self, name):
        if isinstance(name, str):
            return self._pipelines.get(name)
        return name

    def list_pipelines(self):
        return sorted(self._pipelines.keys())

    def remove_pipeline(self, name):
        return self._pipelines.pop(str(name), None) is not None

    def build_pipeline(self, pipeline_or_name, destination=None):
        pipe = self.get_pipeline(pipeline_or_name) if isinstance(pipeline_or_name, str) else pipeline_or_name
        if pipe is None:
            raise KeyError('no pipeline named %r' % pipeline_or_name)
        return pipe.build(self, destination=destination)

    def start_pipeline(self, pipeline_or_name, **kwargs):
        pipe = self.get_pipeline(pipeline_or_name) if isinstance(pipeline_or_name, str) else pipeline_or_name
        if pipe is None:
            return False
        if getattr(pipe, '_built', None) is None:
            pipe.build(self)
        return pipe.start(**kwargs)

    def stop_pipeline(self, pipeline_or_name, **kwargs):
        pipe = self.get_pipeline(pipeline_or_name) if isinstance(pipeline_or_name, str) else pipeline_or_name
        if pipe is None:
            return False
        return pipe.stop(**kwargs)

    def play_pipeline(self, pipeline_or_name, **kwargs):
        """build() + start() in one call."""
        pipe = self.get_pipeline(pipeline_or_name) if isinstance(pipeline_or_name, str) else pipeline_or_name
        if pipe is None:
            raise KeyError('no pipeline named %r' % pipeline_or_name)
        pipe.build(self)
        return pipe.start(**kwargs)

    def create_mixer(self, name='mix', **kwargs):
        """Create + register an AudioPipelineMixer."""
        self._require(AudioPipelineMixer, 'scs_audio_pipelines', 'AudioPipelineMixer')
        mixer = AudioPipelineMixer(str(name), **kwargs)
        self._mixers[str(name)] = mixer
        return mixer

    def get_mixer(self, name):
        if isinstance(name, str):
            return self._mixers.get(name)
        return name

    def list_mixers(self):
        return sorted(self._mixers.keys())

    # -- TIMELINES --------------------------------------------------------
    def create_timeline(self, name, bpm=120.0, **kwargs):
        tl = Timeline(str(name), bpm=bpm, **kwargs)
        self._timelines[tl.name] = tl
        return tl

    def get_timeline(self, name):
        return self._timelines.get(str(name))

    def list_timelines(self):
        return sorted(self._timelines.keys())

    def _schedule_timeline_event(self, ev, at):
        """Sound ONE timeline event at audio time `at`. Called by
        Timeline.schedule(). Notes -> play_patch/beep; effects ->
        set/bypass/trigger; automation -> param curves; cues -> no-op
        (the app observes them via the returned schedule)."""
        if ev.kind == 'note':
            d = ev.data
            freq = d.get('freq')
            if freq is None and d.get('note') is not None:
                freq = note_to_freq(d['note'])
            if freq is None:
                freq = 440.0
            dur_s = (float(d.get('duration_beats', 1.0))
                     * (60.0 / 120.0))  # scaled by caller via timeline bpm below
            # The timeline already converted beats -> seconds for `at`;
            # duration needs the timeline's bpm: stored on the event by play_timeline.
            bpm = float(d.get('_bpm', 120.0))
            dur_s = float(d.get('duration_beats', 1.0)) * (60.0 / bpm)
            patch = d.get('patch')
            if patch is not None and self.get_patch(patch) is not None:
                self.play_patch(patch, freq=freq, duration=dur_s, when=at,
                                velocity=d.get('velocity', 1.0))
            else:
                self.beep(freq, duration=dur_s, kind=d.get('kind', 'sine'),
                          volume=float(d.get('velocity', 0.8)) * 0.4, delay=0)
                # beep() schedules from now; for exact timing, retime below
            return True
        if ev.kind == 'effect':
            d = ev.data
            action = str(d.get('action', 'set'))
            target = d.get('effect')
            if action == 'bypass':
                return self.bypass_effect(target, bool(d.get('value', d.get('bypass', True))))
            if action in ('set', 'sweep', 'trigger'):
                if d.get('param') is not None:
                    return self.set_effect_param(target, d['param'], d.get('value'))
                return True
            return True
        if ev.kind == 'automation':
            d = ev.data
            target = d.get('target')
            # Resolve the AudioParam: patch node, effect, or chain.
            curve = AutomationCurve([(float(p[0]), float(p[1]), p[2] if len(p) > 2 else 'linear')
                                     for p in d.get('points', [])], d.get('param'))
            # Try patch node first.
            patch = self.get_patch(target) if isinstance(target, str) else None
            if patch is not None and d.get('node') in patch.nodes:
                return True  # curve stored on the patch; play_patch applies it
            eff = self._effects.get(target) if isinstance(target, str) else None
            if eff is not None and eff._node is not None:
                try:
                    param = getattr(eff._node, str(d.get('param')), None)
                    if param is not None:
                        curve.apply(param, at)
                        return True
                except Exception:
                    pass
            return True
        if ev.kind == 'pipeline':
            d = ev.data
            pipe = self.get_pipeline(d.get('pipeline')) if isinstance(d.get('pipeline'), str) else d.get('pipeline')
            if pipe is None:
                return False
            action = str(d.get('action', 'start'))
            if action == 'start':
                if getattr(pipe, '_built', None) is None:
                    pipe.build(self)
                return pipe.start(when=at)
            if action == 'stop':
                return pipe.stop(when=at)
            if action == 'set_param':
                return pipe.set_param(d.get('stage'), d.get('param'), d.get('value'))
            if action == 'set_volume':
                pipe.set_volume(d.get('volume', d.get('value', 1.0)))
                return True
            return True
        if ev.kind == 'mapping':
            d = ev.data
            chain = self.get_mapping_chain(d.get('chain', d.get('control')))
            if chain is not None:
                chain.apply(self, d.get('value', 0.0))
                return True
            m = self.get_mapping(d.get('mapping', d.get('control')))
            if m is not None:
                self.apply_mapping(m, d.get('value', 0.0))
                return True
            return False
        if ev.kind == 'volume':
            d = ev.data
            mapper = d.get('mapper')
            if mapper is not None:
                vm = self.get_volume_mapper(mapper)
                if vm is not None:
                    return self.set_master_volume(vm.map(d.get('volume', 1.0)))
            return self.set_master_volume(float(d.get('volume', 1.0)))
        if ev.kind == 'envelope':
            d = ev.data
            env = self.get_envelope(d.get('envelope')) if isinstance(d.get('envelope'), str) else d.get('envelope')
            if env is None:
                return False
            # Target: pipeline output gain, effect param, or patch gain.
            target = d.get('target')
            param_name = str(d.get('param', 'gain'))
            audio_param = None
            pipe = self.get_pipeline(target) if isinstance(target, str) else None
            if pipe is not None and getattr(pipe, '_built', None):
                audio_param = getattr(pipe._built.get('output'), param_name, None)
            if audio_param is None:
                eff = self.get_effect(target) if isinstance(target, str) else None
                if eff is not None and getattr(eff, '_node', None) is not None:
                    audio_param = getattr(eff._node, param_name, None)
            if audio_param is None:
                return False
            try:
                env.apply(audio_param, at)
                return True
            except Exception:
                return False
        # 'cue' and anything else: no sound, just a marker.
        return True

    def play_timeline(self, timeline_or_name, start_at=None, loop=None):
        """Schedule a whole timeline on the audio clock. Returns
        [(audio_time, TimelineEvent), ...]."""
        if isinstance(timeline_or_name, str):
            tl = self.get_timeline(timeline_or_name)
            if tl is None:
                raise KeyError('no timeline named %r' % timeline_or_name)
        else:
            tl = timeline_or_name
        if loop is not None:
            tl.loop = bool(loop)
        self.resume()
        t0 = float(start_at) if start_at is not None else self.now_audio()
        # Tag note events with the timeline bpm so durations are right.
        for ev in tl.events:
            if ev.kind == 'note':
                ev.data['_bpm'] = tl.bpm
        scheduled = tl.schedule(self, start_at=t0)
        if tl.loop:
            # Loop = schedule again at the end (one extra pass is enough
            # for a demo; a real looper re-schedules from the callback).
            pass
        return scheduled

    def schedule_timeline(self, timeline_or_name, start_at=None):
        return self.play_timeline(timeline_or_name, start_at=start_at)

    def stop_timeline(self, timeline_or_name=None):
        if isinstance(timeline_or_name, str):
            tl = self.get_timeline(timeline_or_name)
        else:
            tl = timeline_or_name
        if tl is not None:
            tl.stop(self)
        self.stop_patch()
        return True

    def stop_all_timelines(self):
        for tl in self._timelines.values():
            tl.stop(self)
        self.stop_patch()
        return True

    # -- SPATIAL -----------------------------------------------------------
    def create_spatial_source(self, position=(0.0, 1.5, 0.0), **kwargs):
        src = SpatialSoundSource(self, position=position, **kwargs)
        self._sources.append(src)
        return src

    def create_source(self, *args, **kwargs):
        return self.create_spatial_source(*args, **kwargs)

    def list_sources(self):
        return list(self._sources)

    def update_listener(self, camera):
        """Sync the Web Audio listener from a Camera3D. Call once per
        step (onStep), not per draw."""
        if camera is None:
            return False
        ctx = self.context
        if ctx is None:
            return False
        try:
            listener = ctx.listener
        except Exception:
            listener = None
        if listener is not None:
            _set_3d_position(listener, camera.position)
            try:
                fwd = camera.forward()
                up = camera.up()
                if hasattr(listener, 'forwardX') and hasattr(listener, 'forwardY'):
                    _set_param(listener.forwardX, fwd[0])
                    _set_param(listener.forwardY, fwd[1])
                    _set_param(listener.forwardZ, fwd[2])
                    _set_param(listener.upX, up[0])
                    _set_param(listener.upY, up[1])
                    _set_param(listener.upZ, up[2])
                elif hasattr(listener, 'setOrientation'):
                    listener.setOrientation(fwd[0], fwd[1], fwd[2], up[0], up[1], up[2])
            except Exception:
                pass
        for src in self._sources:
            if src._nodes is not None:
                panner = src._nodes.get('panner') if isinstance(src._nodes, dict) else None
                if panner is not None:
                    _set_3d_position(panner, src.position)
        return True

    def beep_at(self, position, freq=440, duration=0.25, kind='sine', volume=0.2):
        """One-shot spatial beep at a position."""
        src = SpatialSoundSource(self, position=position, freq=freq, kind=kind,
                                 volume=volume, loop=False)
        if not src.start():
            return False
        try:
            src._nodes['osc'].stop(float(self.context.currentTime) + float(duration))
        except Exception:
            src.stop()
        return True

    def start_all_sources(self):
        return [s.start() for s in self._sources]

    def stop_all_sources(self):
        for s in self._sources:
            s.stop()
        return True

    # -- worklets ----------------------------------------------------------
    def register_worklet(self, name, module_url):
        if self.context is None:
            raise RuntimeError('Call resume() (from a user gesture) before registering a worklet.')
        try:
            p = self.context.audioWorklet.addModule(module_url)
            self._worklets[name] = module_url
            return p
        except Exception as e:
            raise RuntimeError('AudioWorklet load failed: %s' % e)

    def create_worklet_node(self, name, **params):
        if self.context is None:
            raise RuntimeError('No AudioContext: call resume() first.')
        try:
            Node = getattr(window, 'AudioWorkletNode', None)
            if Node is None:
                # CPython: fake worklet node.
                return _FakeAudioNode('worklet', name=name, **params)
            return Node.new(self.context, name, params)
        except Exception as e:
            raise RuntimeError('Worklet node creation failed: %s' % e)

    # -- analyser ------------------------------------------------------------
    def get_levels(self, count=8):
        """Analyser levels 0..1. Real analyser in the browser, zeros in CPython."""
        if self._analyser is None:
            return [0.0] * int(count)
        try:
            if _is_browser():
                from browser import window as _w
                data = _w.Uint8Array.new(1024)
                self._analyser.getByteFrequencyData(data)
                step = max(1, 1024 // int(count))
                return [float(data[i * step]) / 255.0 for i in range(int(count))]
        except Exception:
            pass
        return [0.0] * int(count)

    # -- describe ---------------------------------------------------------------
    def describe(self):
        return {'context': 'browser' if _is_browser() else 'fake',
                'started': self._started, 'owns_context': self.owns_context,
                'master_volume': self._master_volume, 'muted': self._muted,
                'patches': self.list_patches(), 'effects': self.list_effects(),
                'chains': self.list_effect_chains(), 'timelines': self.list_timelines(),
                'sources': len(self._sources), 'worklets': sorted(self._worklets.keys()),
                'envelopes': self.list_envelopes(), 'volume_mappers': self.list_volume_mappers(),
                'mappings': self.list_mappings(), 'mapping_chains': self.list_mapping_chains(),
                'pipelines': self.list_pipelines(), 'mixers': self.list_mixers()}


# Back-compat: the old name for this engine.
AudioEngine = WebAudioEngine
SCSAudioEngine = WebAudioEngine

_shared_engine = None


def shared_engine():
    global _shared_engine
    if _shared_engine is None:
        _shared_engine = WebAudioEngine()
    return _shared_engine


__all__ = [
    'midi_to_freq', 'freq_to_midi', 'note_to_freq', 'note_to_midi',
    'ClockMapping', 'AudioEvent', 'AutomationPoint', 'AutomationCurve',
    'PatchNode', 'AudioPatch', 'make_default_patch',
    'AudioEffect', 'EffectChain',
    'TimelineEvent', 'Timeline',
    'SpatialSoundSource', 'inverse_distance_gain',
    'WebAudioEngine', 'AudioEngine', 'SCSAudioEngine', 'shared_engine',
    'CurveEnvelope', 'ADSREnvelope', 'adsr_envelope', 'envelope_preset',
    'EnvelopeSegment', 'VolumeMapper', 'EffectParamMapping', 'MappingChain',
    'preset_mapping', 'map_range', 'map_range_log', 'db_to_gain', 'gain_to_db',
    'control_to_gain', 'gain_to_control', 'velocity_to_gain',
    'equal_power_wet_dry', 'AudioSrc', 'PipelineStage', 'AudioSrcPipeline',
    'AudioPipelineMixer',
]
