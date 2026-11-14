
"""
scs_audio_pipelines.py -- NODE-BASED audio SOURCE pipelines.

A pipeline is an explicit node graph, not an ad-hoc pile of calls:

    src -> stage1 -> stage2 -> ... -> effects -> destination
                    \-> send -> reverb -> destination (parallel)

    pipe = AudioSrcPipeline('lead', src='oscillator', freq=440)
    pipe.add_filter('lowpass', frequency=1200)   # stage
    pipe.add_envelope('pluck')                   # stage (gain + envelope)
    pipe.add_effect('reverb', decay=2.0)         # stage (effect)
    pipe.add_send('delay-send', 'delay', wet=0.3)  # parallel send
    pipe.set_volume(0.7)                          # VolumeMapper
    pipe.build(engine)                            # real/fake nodes, wired
    pipe.start()                                  # note_on
    pipe.stop()                                   # note_off -> release

Sources (AudioSrc):
  oscillator -- osc(freq, type)            buffer -- audio buffer / URL
  noise      -- white noise                file -- URL / path (fetch+decode)
  mic        -- getUserMedia               worklet -- AudioWorkletNode
  patch      -- an AudioPatch as a source  input -- an existing node

Stages (PipelineStage):
  gain / filter / delay / compressor / panner / convolver / waveshaper
  envelope -- a CurveEnvelope driving a gain stage
  effect   -- an AudioEffect (or EffectChain) as a stage
  mapping  -- an EffectParamMapping / VolumeMapper driving a stage

The pipeline OWNS the wiring. build() creates every node (real in the
browser, fake in CPython), connects them in order, applies envelopes
and mappings, and returns the built node dict. start()/stop() handle
note_on / note_off through the envelope stages. to_dict()/from_dict()
save the pipeline (envelopes as points, effects as params) so a
pipeline can be rebuilt on any engine.

Pipelines compose: AudioPipelineMixer mixes N pipelines into one
master gain + master EffectChain (the "mixer" / "bus").
"""

import math

try:
    from scs_audio_envelopes import CurveEnvelope, ADSREnvelope, adsr_envelope, envelope_preset
except Exception:
    from scs_audio_envelopes import CurveEnvelope, ADSREnvelope, adsr_envelope, envelope_preset

try:
    from scs_audio_mapping import VolumeMapper, EffectParamMapping, MappingChain, equal_power_wet_dry
except Exception:
    from scs_audio_mapping import VolumeMapper, EffectParamMapping, MappingChain, equal_power_wet_dry


# [STRIPPED 70 bytes]
# Sources
# [STRIPPED 70 bytes]

_SRC_KINDS = ('oscillator', 'buffer', 'noise', 'file', 'mic', 'worklet',
              'patch', 'input', 'gain')


class AudioSrc:
    """One audio source: what starts the pipeline.

    ``AudioSrc('oscillator', freq=440, type='sawtooth')``
    ``AudioSrc('noise')`` / ``AudioSrc('file', url='kick.wav')``
    ``AudioSrc('mic')`` / ``AudioSrc('worklet', worklet_name='my-dsp')``
    """

    def __init__(self, kind, **params):
        kind = str(kind)
        if kind not in _SRC_KINDS:
            raise ValueError('unknown audio src kind %r' % kind)
        self.kind = kind
        self.params = dict(params)
        self._node = None

    @classmethod
    def oscillator(cls, freq=440.0, type='sine', detune=0.0):
        return cls('oscillator', freq=float(freq), type=type, detune=float(detune))

    @classmethod
    def noise(cls, gain=0.5):
        return cls('noise', gain=float(gain))

    @classmethod
    def file(cls, url, loop=False):
        return cls('file', url=str(url), loop=bool(loop))

    @classmethod
    def buffer(cls, buffer=None, url=None, loop=False):
        return cls('buffer', buffer=buffer, url=url, loop=bool(loop))

    @classmethod
    def mic(cls):
        return cls('mic')

    @classmethod
    def worklet(cls, worklet_name, **params):
        p = dict(params)
        p['worklet_name'] = worklet_name
        return cls('worklet', **p)

    def create_node(self, engine):
        """Create the source node. Returns (node, kind)."""
        if engine is None:
            raise ValueError('AudioSrc needs an engine to create nodes')
        ctx = None
        try:
            ctx = engine.context
        except Exception:
            ctx = None
        if ctx is None:
            try:
                engine.resume()
                ctx = engine.context
            except Exception:
                pass
        if ctx is None:
            raise RuntimeError('No AudioContext: call engine.resume() first')
        kind = self.kind
        if kind == 'oscillator':
            node = ctx.createOscillator()
            try:
                node.frequency.value = float(self.params.get('freq', 440.0))
            except Exception:
                try:
                    node.frequency.setValueAtTime(float(self.params.get('freq', 440.0)), float(ctx.currentTime))
                except Exception:
                    pass
            try:
                node.type = self.params.get('type', 'sine')
            except Exception:
                pass
            self._node = node
            return node
        if kind == 'noise':
            # Noise = buffer source with a noise buffer.
            node = ctx.createBufferSource() if hasattr(ctx, 'createBufferSource') else engine.create_node('buffersource')
            try:
                sr = 44100
                buf = ctx.createBuffer(1, sr, sr)
                try:
                    data = buf.getChannelData(0)
                    for i in range(len(data)):
                        data[i] = 2.0 * ((i * 2654435761 % 1000) / 1000.0) - 1.0
                except Exception:
                    pass
                node.buffer = buf
                node.loop = True
            except Exception:
                pass
            self._node = node
            return node
        if kind in ('file', 'buffer'):
            node = ctx.createBufferSource() if hasattr(ctx, 'createBufferSource') else engine.create_node('buffersource')
            try:
                node.loop = bool(self.params.get('loop', False))
            except Exception:
                pass
            # The buffer itself is loaded by the app (fetch+decode) and
            # set via pipe.set_source_buffer(buf). Until then the node
            # exists but is silent -- build() never crashes on it.
            if self.params.get('buffer') is not None:
                try:
                    node.buffer = self.params['buffer']
                except Exception:
                    pass
            self._node = node
            return node
        if kind == 'mic':
            # Mic needs getUserMedia (async, gesture). The engine
            # supplies it via engine.create_mic_source() when available;
            # here we return a gain placeholder so build() still works.
            node = engine.create_node('gain', gain=1.0)
            node._is_mic_placeholder = True
            self._node = node
            return node
        if kind == 'worklet':
            try:
                node = engine.create_worklet_node(self.params.get('worklet_name', 'worklet'), **{k: v for k, v in self.params.items() if k != 'worklet_name'})
            except Exception:
                node = engine.create_node('gain', gain=1.0)
            self._node = node
            return node
        if kind == 'patch':
            # A patch as a source: build it via the engine.
            patch = self.params.get('patch')
            if patch is not None:
                built = engine.play_patch(patch, freq=self.params.get('freq'),
                                          duration=self.params.get('duration', 1.0))
                # play_patch returns the built node dict; use its output.
                if isinstance(built, dict):
                    node = built.get('amp') or built.get('osc') or next(iter(built.values()), None)
                    self._node = node
                    return node
            node = engine.create_node('gain', gain=1.0)
            self._node = node
            return node
        # 'gain' / 'input': passthrough gain.
        node = engine.create_node('gain', gain=float(self.params.get('gain', 1.0)))
        self._node = node
        return node

    def describe(self):
        return {'kind': self.kind, 'params': dict(self.params)}

    def to_dict(self):
        d = self.describe()
        # Buffers are not JSON-safe; drop them, keep the URL.
        d['params'].pop('buffer', None)
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(d['kind'], **d.get('params', {}))


# [STRIPPED 70 bytes]
# Stages
# [STRIPPED 70 bytes]

_STAGE_KINDS = ('gain', 'filter', 'delay', 'compressor', 'panner',
                'stereopanner', 'convolver', 'waveshaper', 'analyser',
                'envelope', 'effect', 'mapping', 'volume')


class PipelineStage:
    """One stage in a pipeline: a node + optional envelope / mapping.

    ``PipelineStage('filter', type='lowpass', frequency=1200)``
    ``PipelineStage('envelope', envelope=adsr_envelope(...))``
    ``PipelineStage('effect', effect=AudioEffect('reverb', ...))``
    """

    def __init__(self, kind, name=None, **params):
        kind = str(kind)
        if kind not in _STAGE_KINDS:
            raise ValueError('unknown pipeline stage kind %r' % kind)
        self.kind = kind
        self.name = str(name or kind)
        self.params = dict(params)
        self.envelope = params.get('envelope')  # CurveEnvelope or None
        self.mapping = params.get('mapping')    # EffectParamMapping or None
        self._node = None

    def create_node(self, engine):
        """Create this stage's node (or effect node)."""
        if self.kind == 'envelope':
            # Envelope stage = a gain node the envelope drives.
            node = engine.create_node('gain', gain=1.0)
            self._node = node
            return node
        if self.kind == 'effect':
            eff = self.params.get('effect')
            if eff is None:
                # params ARE the effect: PipelineStage('effect', kind='reverb', decay=2)
                from scs_web_audio import AudioEffect as _AE
                eff = _AE(self.params.get('effect_kind', self.params.get('kind', 'gain')),
                          **{k: v for k, v in self.params.items() if k not in ('effect', 'effect_kind', 'kind', 'envelope', 'mapping')})
                self.params['effect'] = eff
            try:
                node = eff.create_node(engine)
            except Exception:
                node = engine.create_node('gain', gain=1.0)
            self._node = node
            return node
        if self.kind == 'volume':
            node = engine.create_node('gain', gain=1.0)
            self._node = node
            return node
        if self.kind == 'mapping':
            # Mapping stage has no node of its own; it drives the
            # previous stage. build() handles it.
            self._node = None
            return None
        # Plain node kinds.
        node_kind = self.kind
        try:
            node = engine.create_node(node_kind, **{k: v for k, v in self.params.items() if k not in ('envelope', 'mapping')})
        except Exception:
            node = engine.create_node('gain', gain=1.0)
        # Apply params onto AudioParams.
        for pname, value in self.params.items():
            if pname in ('envelope', 'mapping'):
                continue
            try:
                p = getattr(node, pname, None)
                if p is not None and hasattr(p, 'value'):
                    p.value = float(value)
                elif hasattr(node, 'params') and isinstance(node.params, dict):
                    node.params[pname] = value
            except Exception:
                pass
        self._node = node
        return node

    def apply_envelope(self, start_time=0.0, peak=1.0):
        """Apply this stage's envelope to its node."""
        if self.envelope is None or self._node is None:
            return 0
        try:
            return self.envelope.apply_to_gain(self._node, start_time, peak=peak)
        except Exception:
            try:
                return self.envelope.apply(getattr(self._node, 'gain', None), start_time, peak=peak)
            except Exception:
                return 0

    def describe(self):
        d = {'kind': self.kind, 'name': self.name,
             'params': {k: v for k, v in self.params.items() if k not in ('envelope', 'mapping', 'effect')}}
        if self.envelope is not None:
            try:
                d['envelope'] = self.envelope.to_dict()
            except Exception:
                d['envelope'] = {'name': getattr(self.envelope, 'name', 'envelope')}
        if self.mapping is not None:
            try:
                d['mapping'] = self.mapping.to_dict()
            except Exception:
                pass
        if self.params.get('effect') is not None:
            try:
                d['effect'] = self.params['effect'].to_dict()
            except Exception:
                pass
        return d

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        params = dict(d.get('params', {}))
        if d.get('envelope'):
            try:
                from scs_audio_envelopes import CurveEnvelope as _CE
                # ADSR dicts have type='adsr'
                if d['envelope'].get('type') == 'adsr':
                    from scs_audio_envelopes import ADSREnvelope as _ADSR
                    params['envelope'] = _ADSR.from_dict(d['envelope'])
                else:
                    params['envelope'] = _CE.from_dict(d['envelope'])
            except Exception:
                pass
        if d.get('effect'):
            try:
                from scs_web_audio import AudioEffect as _AE
                params['effect'] = _AE.from_dict(d['effect'])
            except Exception:
                pass
        return cls(d['kind'], name=d.get('name'), **params)


# [STRIPPED 70 bytes]
# AudioSrcPipeline
# [STRIPPED 70 bytes]

class AudioSrcPipeline:
    """A node-based source pipeline: src -> stages -> destination.

    Example (see module docstring)::

        pipe = AudioSrcPipeline('lead', src='oscillator', freq=440)
        pipe.add_filter('lowpass', frequency=1200)
        pipe.add_envelope('pluck')
        pipe.add_effect('reverb', decay=2.0)
        pipe.build(engine)
        pipe.start()
    """

    def __init__(self, name, src=None, **src_params):
        self.name = str(name)
        if isinstance(src, AudioSrc):
            self.src = src
        elif isinstance(src, str):
            self.src = AudioSrc(src, **src_params)
        elif src is None:
            self.src = AudioSrc('oscillator', **src_params)
        else:
            self.src = AudioSrc('oscillator', **src_params)
        self.stages = []  # list[PipelineStage]
        self.sends = []   # list[(send_name, EffectChain/AudioEffect, amount)]
        self.volume_mapper = VolumeMapper(curve='perceptual', name=name + ':volume')
        self._volume = 1.0
        self._built = None  # {'src': node, 'stages': [...], 'output': node}
        self._engine = None
        self._started = False
        self._start_time = None
        self._note_off = None
        self._source_buffer = None

    # -- building ---------------------------------------------------------
    def add_stage(self, kind, name=None, **params):
        stage = PipelineStage(kind, name=name, **params)
        self.stages.append(stage)
        return stage

    def add_gain(self, gain=1.0, name=None):
        return self.add_stage('gain', name=name or 'gain', gain=float(gain))

    def add_filter(self, type='lowpass', frequency=1000.0, Q=1.0, gain=0.0, name=None):
        return self.add_stage('filter', name=name or 'filter', type=type,
                              frequency=float(frequency), Q=float(Q), gain=float(gain))

    def add_delay(self, delayTime=0.3, feedback=0.3, name=None):
        return self.add_stage('delay', name=name or 'delay',
                              delayTime=float(delayTime), feedback=float(feedback))

    def add_compressor(self, name=None, **params):
        d = {'threshold': -24.0, 'knee': 30.0, 'ratio': 12.0, 'attack': 0.003, 'release': 0.25}
        d.update(params)
        return self.add_stage('compressor', name=name or 'compressor', **d)

    def add_panner(self, pan=0.0, name=None):
        return self.add_stage('stereopanner', name=name or 'panner', pan=float(pan))

    def add_envelope(self, envelope_or_preset, name=None, **kwargs):
        """add_envelope('pluck') / add_envelope(adsr_envelope(...)) /
        add_envelope(CurveEnvelope(...)). Adds a gain stage driven by
        the envelope."""
        if isinstance(envelope_or_preset, str):
            env = envelope_preset(envelope_or_preset, **kwargs)
        elif isinstance(envelope_or_preset, (CurveEnvelope, ADSREnvelope)):
            env = envelope_or_preset
        else:
            env = adsr_envelope(**kwargs)
        return self.add_stage('envelope', name=name or ('env:' + getattr(env, 'name', 'envelope')),
                              envelope=env)

    def add_effect(self, effect_or_kind, name=None, **params):
        """add_effect('reverb', decay=2.0) / add_effect(AudioEffect(...))."""
        if isinstance(effect_or_kind, str):
            from scs_web_audio import AudioEffect as _AE
            # Preset or kind?
            try:
                eff = _AE.preset(effect_or_kind, **params)
            except Exception:
                eff = _AE(effect_or_kind, **params)
        else:
            eff = effect_or_kind
        return self.add_stage('effect', name=name or ('fx:' + getattr(eff, 'kind', 'effect')),
                              effect=eff)

    def add_mapping(self, mapping, name=None):
        """add_mapping(EffectParamMapping(...)) -- drives the previous stage."""
        return self.add_stage('mapping', name=name or 'mapping', mapping=mapping)

    def add_send(self, send_name, effect_or_kind, amount=0.3, **params):
        """Parallel send: src output also goes to this effect -> destination.
        Does not affect the main chain."""
        if isinstance(effect_or_kind, str):
            from scs_web_audio import AudioEffect as _AE
            try:
                eff = _AE.preset(effect_or_kind, **params)
            except Exception:
                eff = _AE(effect_or_kind, **params)
        else:
            eff = effect_or_kind
        self.sends.append((str(send_name), eff, float(amount)))
        return self.sends[-1]

    # -- volume -------------------------------------------------------------
    def set_volume(self, control, curve=None):
        """Set volume via the VolumeMapper (control 0..1 or MIDI 0..127)."""
        if curve is not None:
            self.volume_mapper.curve = str(curve)
        self._volume = float(self.volume_mapper.map(control))
        if self._built is not None and self._built.get('output') is not None:
            # Output is the last stage or the master gain; set it if gain.
            try:
                param = getattr(self._built['output'], 'gain', None)
                if param is not None:
                    param.value = self._volume
            except Exception:
                pass
        return self._volume

    @property
    def volume(self):
        return self._volume

    def set_source_buffer(self, buf):
        """Set the decoded AudioBuffer for file/buffer sources."""
        self._source_buffer = buf
        if self._built is not None and self._built.get('src') is not None:
            try:
                self._built['src'].buffer = buf
            except Exception:
                pass
        return True

    # -- build / start / stop ------------------------------------------------
    def build(self, engine, destination=None):
        """Create every node and wire src -> stages -> destination.
        Returns {'src': node, 'stages': [nodes], 'output': node}."""
        self._engine = engine
        try:
            engine.resume()
        except Exception:
            pass
        ctx = getattr(engine, 'context', None)
        if ctx is None:
            # Fake-context path: engine._ensure_context() in CPython.
            try:
                ctx = engine._ensure_context()
            except Exception:
                ctx = None
        dest = destination
        if dest is None and ctx is not None:
            dest = getattr(ctx, 'destination', None)
        # Source.
        src_node = self.src.create_node(engine)
        # Stages in order.
        stage_nodes = []
        current = src_node
        for stage in self.stages:
            if stage.kind == 'mapping':
                # Mapping drives the PREVIOUS stage's node.
                m = stage.mapping
                if m is not None and stage_nodes:
                    prev = stage_nodes[-1]
                    try:
                        param = getattr(prev, m.param, None)
                        if param is not None:
                            m.apply_to_param(param, 1.0)
                    except Exception:
                        pass
                continue
            node = stage.create_node(engine)
            if node is None:
                continue
            try:
                current.connect(node)
            except Exception:
                pass
            stage_nodes.append(node)
            current = node
        # Output gain (volume) at the end of the chain.
        out_gain = engine.create_node('gain', gain=self._volume)
        try:
            current.connect(out_gain)
        except Exception:
            pass
        if dest is not None:
            try:
                out_gain.connect(dest)
            except Exception:
                pass
        # Parallel sends: src -> effect -> destination.
        send_nodes = []
        for (send_name, eff, amount) in self.sends:
            try:
                node = eff.create_node(engine)
                # Send amount = gain before the effect.
                send_gain = engine.create_node('gain', gain=float(amount))
                src_node.connect(send_gain)
                send_gain.connect(node)
                if dest is not None:
                    node.connect(dest)
                send_nodes.append((send_name, node, send_gain))
            except Exception:
                pass
        self._built = {'src': src_node, 'stages': stage_nodes,
                       'output': out_gain, 'sends': send_nodes,
                       'destination': dest}
        return self._built

    def start(self, when=None, freq=None, note=None):
        """Note_on: start the source, apply envelopes. Returns True."""
        if self._engine is None:
            raise RuntimeError('Call build(engine) before start()')
        if self._started:
            return True
        engine = self._engine
        ctx = getattr(engine, 'context', None)
        try:
            now = float(when) if when is not None else float(ctx.currentTime)
        except Exception:
            now = 0.0
        # Retune oscillator sources.
        target = None
        if freq is not None:
            target = float(freq)
        elif note is not None:
            try:
                from scs_web_audio import note_to_freq as _ntf
                target = _ntf(note)
            except Exception:
                target = None
        if target is not None and self.src.kind == 'oscillator':
            try:
                self._built['src'].frequency.value = target
            except Exception:
                pass
        # Envelopes: attack+decay+sustain-start.
        for stage in self.stages:
            if stage.kind == 'envelope' and stage.envelope is not None:
                try:
                    stage.apply_envelope(now, peak=1.0)
                except Exception:
                    pass
        # Start the source node.
        try:
            self._built['src'].start(now)
        except Exception:
            try:
                self._built['src'].start()
            except Exception:
                pass
        self._started = True
        self._start_time = now
        self._note_off = None
        return True

    def stop(self, when=None):
        """Note_off: run release envelopes, then stop the source."""
        if not self._started or self._built is None:
            return True
        engine = self._engine
        ctx = getattr(engine, 'context', None)
        try:
            now = float(when) if when is not None else float(ctx.currentTime)
        except Exception:
            now = 0.0
        # Release envelopes.
        for stage in self.stages:
            if stage.kind == 'envelope' and stage.envelope is not None:
                env = stage.envelope
                try:
                    if hasattr(env, 'apply_release'):
                        env.apply_release(getattr(stage._node, 'gain', None), now)
                    else:
                        # Generic curve envelope: ramp to 0 over 0.2s.
                        try:
                            stage._node.gain.linearRampToValueAtTime(0.0, now + 0.2)
                        except Exception:
                            pass
                except Exception:
                    pass
        # Stop the source after the longest release.
        max_release = 0.0
        for stage in self.stages:
            if stage.kind == 'envelope' and stage.envelope is not None:
                try:
                    max_release = max(max_release, float(getattr(stage.envelope, 'release', 0.0) or 0.0))
                except Exception:
                    pass
        try:
            self._built['src'].stop(now + max_release)
        except Exception:
            try:
                self._built['src'].stop()
            except Exception:
                pass
        self._started = False
        self._note_off = now
        return True

    def note_on(self, *args, **kwargs):
        return self.start(*args, **kwargs)

    def note_off(self, *args, **kwargs):
        return self.stop(*args, **kwargs)

    def set_param(self, stage_name, param, value):
        """Set a param on a stage by name."""
        for stage in self.stages:
            if stage.name == str(stage_name):
                stage.params[str(param)] = value
                if stage._node is not None:
                    try:
                        p = getattr(stage._node, str(param), None)
                        if p is not None and hasattr(p, 'value'):
                            p.value = float(value)
                        elif hasattr(stage._node, 'params'):
                            stage._node.params[str(param)] = value
                    except Exception:
                        pass
                return True
        return False

    def get_stage(self, name):
        for stage in self.stages:
            if stage.name == str(name):
                return stage
        return None

    # -- serialise ----------------------------------------------------------
    def describe(self):
        return {'name': self.name, 'src': self.src.describe(),
                'stages': [s.describe() for s in self.stages],
                'sends': [{'name': n, 'effect': e.to_dict(), 'amount': a}
                          for (n, e, a) in self.sends],
                'volume': self._volume, 'started': self._started}

    def to_dict(self):
        return self.describe()

    @classmethod
    def from_dict(cls, d):
        pipe = cls(d.get('name', 'pipeline'), src=AudioSrc.from_dict(d['src']))
        for sd in d.get('stages', []):
            pipe.stages.append(PipelineStage.from_dict(sd))
        for s in d.get('sends', []):
            try:
                from scs_web_audio import AudioEffect as _AE
                pipe.sends.append((s['name'], _AE.from_dict(s['effect']), float(s.get('amount', 0.3))))
            except Exception:
                pass
        pipe._volume = float(d.get('volume', 1.0))
        return pipe


# [STRIPPED 70 bytes]
# Mixer: N pipelines -> master
# [STRIPPED 70 bytes]

class AudioPipelineMixer:
    """Mix N pipelines into one master gain + master EffectChain.

    ``mixer = AudioPipelineMixer('mix')``
    ``mixer.add(pipe1).add(pipe2)``
    ``mixer.build(engine)`` builds every pipeline into the master bus.
    ``mixer.set_master_volume(0.8)`` / ``mixer.add_master_effect('hall')``
    """

    def __init__(self, name='mix', master_volume=0.8):
        self.name = str(name)
        self.pipelines = []  # list[AudioSrcPipeline]
        self.master_volume = float(master_volume)
        self.master_effects = []  # list[AudioEffect]
        self._master_gain = None
        self._engine = None

    def add(self, pipeline):
        self.pipelines.append(pipeline)
        return self

    def remove(self, name):
        self.pipelines = [p for p in self.pipelines if p.name != str(name)]
        return self

    def add_master_effect(self, effect_or_kind, **params):
        if isinstance(effect_or_kind, str):
            from scs_web_audio import AudioEffect as _AE
            try:
                eff = _AE.preset(effect_or_kind, **params)
            except Exception:
                eff = _AE(effect_or_kind, **params)
        else:
            eff = effect_or_kind
        self.master_effects.append(eff)
        return eff

    def set_master_volume(self, control):
        vm = VolumeMapper(curve='perceptual', name=self.name + ':master')
        self.master_volume = float(vm.map(control))
        if self._master_gain is not None:
            try:
                self._master_gain.gain.value = self.master_volume
            except Exception:
                pass
        return self.master_volume

    def build(self, engine):
        """Build every pipeline into the master bus."""
        self._engine = engine
        try:
            engine.resume()
        except Exception:
            pass
        ctx = getattr(engine, 'context', None)
        dest = getattr(ctx, 'destination', None) if ctx is not None else None
        # Master chain: master gain -> master effects -> destination.
        master = engine.create_node('gain', gain=self.master_volume)
        self._master_gain = master
        current = master
        for eff in self.master_effects:
            try:
                node = eff.create_node(engine)
                current.connect(node)
                current = node
            except Exception:
                pass
        if dest is not None:
            try:
                current.connect(dest)
            except Exception:
                pass
        # Each pipeline builds into the master gain (not destination).
        for pipe in self.pipelines:
            pipe.build(engine, destination=master)
        return {'master': master, 'pipelines': [p._built for p in self.pipelines]}

    def start_all(self, **kwargs):
        return [p.start(**kwargs) for p in self.pipelines]

    def stop_all(self, **kwargs):
        return [p.stop(**kwargs) for p in self.pipelines]

    def describe(self):
        return {'name': self.name, 'master_volume': self.master_volume,
                'pipelines': [p.describe() for p in self.pipelines],
                'master_effects': [e.to_dict() for e in self.master_effects]}


__all__ = [
    'AudioSrc', 'PipelineStage', 'AudioSrcPipeline', 'AudioPipelineMixer',
]
