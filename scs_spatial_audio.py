
"""
scs_spatial_audio.py - 3D spatial audio for SCS, now as PIPELINES.

Rebuilt on the CANONICAL interface in scs_web_audio.py. The public API
is unchanged:

    from scs_spatial_audio import SpatialAudioEngine, SpatialSoundSource
    audio = SpatialAudioEngine()
    audio.resume()  # from a user gesture
    src = audio.create_source(position=(2, 1.5, 0), freq=440)
    src.start()
    audio.update(camera)  # Camera3D IS the listener

The listener IS the Camera3D from scs_3d.py. The same camera that
drives the GL view matrix drives the Web Audio listener, so what you
see is what you hear.

Batch 3: a spatial source IS a pipeline.

    src = audio.create_source(position=(2, 1.5, 0), freq=440,
                              envelope='pluck', pipeline=True)
    src.start()  # builds + starts its pipeline
    src.set_position((3, 1.5, 0))  # moves the pipeline's panner too

    pipe = audio.create_spatial_pipeline('lead', position=(2, 1.5, 0),
                                         freq=440, envelope='pad')
    pipe.add_filter('lowpass', frequency=1200)
    pipe.add_effect('reverb', decay=2.0)
    pipe.build(audio)
    pipe.start()

Pipeline shape for a spatial source:

    osc -> gain (volume, mapped) -> envelope (gain + CurveEnvelope)
         -> filter / effects -> panner (HRTF, inverse distance)
         -> destination

    + parallel sends (e.g. reverb send) -> destination

Moving the source updates the pipeline's panner node. The engine's
update(camera) updates the listener AND every spatial pipeline's
panner, so a moving source stays in the right place while the
camera moves.

Web Audio primitives used (all real, no fake):
  * PannerNode -- per-source position, HRTF, inverse distance model
  * AudioListener -- position + forward + up, from the camera
  * OscillatorNode / GainNode -- the sound itself
"""

from scs_web_audio import (
    SpatialSoundSource as _BaseSpatialSoundSource,
    WebAudioEngine,
    inverse_distance_gain,
    _set_param, _set_3d_position,
)

try:
    from scs_audio_envelopes import CurveEnvelope, ADSREnvelope, adsr_envelope, envelope_preset
except Exception:
    CurveEnvelope = ADSREnvelope = adsr_envelope = envelope_preset = None

try:
    from scs_audio_mapping import VolumeMapper
except Exception:
    VolumeMapper = None

try:
    from scs_audio_pipelines import AudioSrcPipeline, AudioSrc
except Exception:
    AudioSrcPipeline = AudioSrc = None


def _resolve_envelope(envelope, engine=None):
    """'pluck' | CurveEnvelope | None -> CurveEnvelope or None."""
    if envelope is None:
        return None
    if isinstance(envelope, str):
        # Registered on the engine? Else a preset.
        if engine is not None:
            try:
                env = engine.get_envelope(envelope)
                if env is not None:
                    return env
            except Exception:
                pass
        if envelope_preset is not None:
            try:
                return envelope_preset(envelope)
            except Exception:
                return None
        return None
    return envelope


class SpatialSoundSource(_BaseSpatialSoundSource):
    """A 3D source that can also be a node-based pipeline.

    Same API as scs_web_audio.SpatialSoundSource, plus:
      as_pipeline() / build_pipeline() -- src as AudioSrcPipeline
      set_volume_mapped(control) -- volume via VolumeMapper
    When a pipeline exists, start()/stop()/set_position() drive the
    pipeline; otherwise they use the original osc->gain->panner path.
    """

    def __init__(self, engine, position=(0.0, 1.5, 0.0), freq=440.0,
                 kind='sine', volume=0.5, loop=True,
                 ref_distance=1.0, max_distance=30.0, rolloff=1.0,
                 name='source', patch=None, effects=None,
                 envelope=None, pipeline=None, volume_mapper=None):
        super().__init__(engine, position=position, freq=freq, kind=kind,
                         volume=volume, loop=loop,
                         ref_distance=ref_distance, max_distance=max_distance,
                         rolloff=rolloff, name=name, patch=patch, effects=effects)
        self._envelope = _resolve_envelope(envelope, engine)
        self._pipeline = pipeline  # AudioSrcPipeline or None
        self._volume_mapper = volume_mapper  # VolumeMapper or None
        self._pipeline_built = False

    # -- pipeline ------------------------------------------------------
    def as_pipeline(self):
        """Build (or return) this source as an AudioSrcPipeline.

        Shape: osc -> gain(volume) -> envelope? -> effects? -> panner
        -> destination. The panner stage is named 'panner' so
        set_position() can find it.
        """
        if self._pipeline is not None:
            return self._pipeline
        if AudioSrcPipeline is None:
            raise ImportError('scs_audio_pipelines not available')
        pipe = AudioSrcPipeline(self.name, src='oscillator',
                                freq=self.freq, type=self.kind)
        # Volume as a gain stage (linear gain, like the original path).
        pipe.add_gain(self.volume, name='volume')
        if self._envelope is not None:
            pipe.add_envelope(self._envelope, name='envelope')
        # Effects: an EffectChain / AudioEffect / list of them.
        effs = self.effects
        if effs is not None:
            if isinstance(effs, (list, tuple)):
                for e in effs:
                    pipe.add_effect(e)
            else:
                try:
                    # EffectChain: add each effect in it.
                    for e in getattr(effs, 'effects', []):
                        pipe.add_effect(e)
                except Exception:
                    pipe.add_effect(effs)
        # Panner LAST before destination: HRTF + inverse distance.
        # PipelineStage('panner') creates a PannerNode via
        # engine.create_node('panner'); position is set after build().
        pipe.add_stage('panner', name='panner')
        self._pipeline = pipe
        # Keep the engine registry in sync when the engine has one.
        try:
            if self.engine is not None and hasattr(self.engine, '_pipelines'):
                self.engine._pipelines[pipe.name] = pipe
        except Exception:
            pass
        return pipe

    def build_pipeline(self, destination=None):
        """Build the pipeline and set the panner position."""
        pipe = self.as_pipeline()
        if self.engine is None:
            raise RuntimeError('Spatial source needs an engine to build')
        built = pipe.build(self.engine, destination=destination)
        self._pipeline_built = True
        self._sync_panner()
        return built

    def _sync_panner(self):
        """Push self.position onto the pipeline's panner node."""
        if self._pipeline is None or not self._pipeline_built:
            return False
        try:
            built = self._pipeline._built or {}
            stages = built.get('stages') or []
            # Panner is the last stage.
            panner = stages[-1] if stages else None
            if panner is not None:
                # PannerNode: set 3D position via _set_3d_position.
                try:
                    _set_3d_position(panner, self.position)
                except Exception:
                    pass
                # Also set distance-model params on the panner.
                for attr, val in (('refDistance', self.ref_distance),
                                  ('maxDistance', self.max_distance),
                                  ('rolloffFactor', self.rolloff)):
                    try:
                        setattr(panner, attr, float(val))
                    except Exception:
                        pass
                try:
                    panner.panningModel = 'HRTF'
                except Exception:
                    pass
                try:
                    panner.distanceModel = 'inverse'
                except Exception:
                    pass
                return True
        except Exception:
            pass
        return False

    def set_position(self, pos):
        super().set_position(pos)
        self._sync_panner()
        return self.position

    # -- volume mapping --------------------------------------------------
    def set_volume_mapped(self, control, mapper=None):
        """Set volume from a control (0..1 or MIDI 0..127) via a
        VolumeMapper. Returns the gain."""
        vm = mapper or self._volume_mapper
        if vm is None:
            if VolumeMapper is not None:
                vm = VolumeMapper(curve='perceptual', name=self.name + ':volume')
                self._volume_mapper = vm
            else:
                self.volume = float(control)
                return self.volume
        self.volume = float(vm.map(control))
        # Push onto live nodes (original path + pipeline path).
        if self._nodes is not None:
            try:
                self._nodes['gain'].gain.value = self.volume
            except Exception:
                pass
        if self._pipeline is not None and self._pipeline._built is not None:
            try:
                vol_stage = self._pipeline.get_stage('volume')
                if vol_stage is not None and vol_stage._node is not None:
                    vol_stage._node.gain.value = self.volume
            except Exception:
                pass
        return self.volume

    # -- start / stop: pipeline when present, else original path --------
    def start(self, at=None):
        if self._pipeline is not None or self._envelope is not None:
            # Pipeline path: build (if needed) + start.
            if self.engine is None:
                return False
            try:
                self.engine.resume()
            except Exception:
                pass
            if not self._pipeline_built:
                self.build_pipeline()
            pipe = self._pipeline
            # Retune.
            try:
                if pipe._built and pipe._built.get('src') is not None:
                    pipe._built['src'].frequency.value = self.freq
            except Exception:
                pass
            ok = pipe.start(when=at)
            self.playing = bool(ok)
            return ok
        return super().start(at=at)

    def stop(self):
        if self._pipeline is not None and self._pipeline_built:
            try:
                self._pipeline.stop()
            except Exception:
                pass
            self.playing = False
            return True
        return super().stop()

    def describe(self):
        d = super().describe()
        d.update({'envelope': getattr(self._envelope, 'name', None) if self._envelope else None,
                  'has_pipeline': self._pipeline is not None,
                  'pipeline_built': self._pipeline_built})
        return d


class SpatialAudioEngine(WebAudioEngine):
    """WebAudioEngine + listener + N spatial sources (as pipelines).

    Same interface as every other engine's ``.audio`` (it IS a
    WebAudioEngine), plus the spatial aliases old code uses:
    create_source() / update() / start_all() / stop_all().
    Batch 3: create_source(..., pipeline=True, envelope='pluck') and
    create_spatial_pipeline() return node-based pipelines.
    """

    def __init__(self, context=None, engine=None):
        if engine is not None:
            super().__init__(context=getattr(engine, 'context', context))
            # Adopt ALL registries, including Batch 3 ones.
            for attr in ('_patches', '_effects', '_chains', '_timelines',
                         '_sources', '_envelopes', '_volume_mappers',
                         '_mappings', '_mapping_chains', '_pipelines', '_mixers'):
                try:
                    setattr(self, attr, getattr(engine, attr, getattr(self, attr)))
                except Exception:
                    pass
            self.engine = engine
        else:
            super().__init__(context=context)
            self.engine = self

    # -- spatial sources (subclass, pipeline-aware) -----------------------
    def create_spatial_source(self, position=(0.0, 1.5, 0.0), **kwargs):
        # Pull pipeline-only kwargs out before constructing.
        envelope = kwargs.pop('envelope', None)
        pipeline = kwargs.pop('pipeline', None)
        volume_mapper = kwargs.pop('volume_mapper', None)
        use_pipeline = False
        if pipeline is True:
            use_pipeline = True
            pipeline = None
        src = SpatialSoundSource(self, position=position,
                                 envelope=envelope, pipeline=pipeline,
                                 volume_mapper=volume_mapper, **kwargs)
        self._sources.append(src)
        if use_pipeline:
            src.as_pipeline()
        return src

    def create_source(self, position=(0.0, 1.5, 0.0), **kwargs):
        return self.create_spatial_source(position=position, **kwargs)

    def create_spatial_pipeline(self, name, position=(0.0, 1.5, 0.0), **kwargs):
        """Create a spatial source AND its pipeline. Returns the pipeline.

        create_spatial_pipeline('lead', position=(2, 1.5, 0), freq=440,
                                envelope='pad')
        pipe.add_filter('lowpass', frequency=1200)
        pipe.build(engine)
        pipe.start()
        The pipeline is registered as engine.get_pipeline(name), and
        its SpatialSoundSource is pipe.spatial_source.
        """
        # Split pipeline-stage kwargs from source kwargs.
        freq = kwargs.pop('freq', 440.0)
        kind = kwargs.pop('kind', 'sine')
        volume = kwargs.pop('volume', 0.5)
        envelope = kwargs.pop('envelope', None)
        src = SpatialSoundSource(self, position=position, freq=freq,
                                 kind=kind, volume=volume,
                                 envelope=envelope, name=str(name), **kwargs)
        self._sources.append(src)
        pipe = src.as_pipeline()
        pipe.name = str(name)
        try:
            pipe.spatial_source = src
        except Exception:
            pass
        # Extra pipeline stages passed as kwargs? e.g. filter=True
        # is not supported -- use pipe.add_*() after creation.
        try:
            self._pipelines[str(name)] = pipe
        except Exception:
            pass
        return pipe

    def get_spatial_pipeline(self, name):
        pipe = self.get_pipeline(name) if hasattr(self, 'get_pipeline') else None
        return pipe

    # -- aliases old code uses -------------------------------------
    def update(self, camera):
        """Sync listener + panners from the camera. Call once per step."""
        ok = self.update_listener(camera)
        # Pipeline panners: update_listener only sees _nodes sources,
        # so push positions onto pipeline panners too.
        for src in list(self._sources):
            try:
                if isinstance(src, SpatialSoundSource):
                    src._sync_panner()
            except Exception:
                pass
        return ok

    def start_all(self):
        return self.start_all_sources()

    def stop_all(self):
        return self.stop_all_sources()

    @property
    def sources(self):
        return self._sources


_shared_spatial = None


def shared_spatial_engine():
    global _shared_spatial
    if _shared_spatial is None:
        _shared_spatial = SpatialAudioEngine()
    return _shared_spatial


__all__ = [
    'SpatialSoundSource', 'SpatialAudioEngine',
    'inverse_distance_gain', 'shared_spatial_engine',
    'CurveEnvelope', 'ADSREnvelope', 'adsr_envelope', 'envelope_preset',
    'VolumeMapper', 'AudioSrcPipeline', 'AudioSrc',
]
