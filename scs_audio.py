
"""
scs_audio.py -- Web Audio integration for SCS (Integration 3).

Thin compatibility layer over the CANONICAL interface in
scs_web_audio.py. Every engine exposes the SAME object as
``engine.audio`` (a WebAudioEngine), and this module re-exports it
under the old names so existing code keeps working:

    from scs_audio import AudioEngine, ClockMapping, AudioEvent
    from scs_audio import AudioPatch, AudioEffect, EffectChain, Timeline

Contract, still true:
  * AUDIO clock is separate from RENDER clock. Schedule against
    AudioContext.currentTime, never frame count.
  * An app may SUPPLY its AudioContext. Disposing never closes an
    app-owned context.
  * resume() must be called from a user gesture (autoplay policy).
  * Custom DSP goes in an AudioWorklet, never in a render callback.

Batch 3 (wired into WebAudioEngine, re-exported here):
  * ENVELOPES: CurveEnvelope / ADSREnvelope / adsr_envelope /
    envelope_preset -- functional, curve-based envelopes.
    engine.audio.create_envelope('pluck', preset='pluck')
  * MAPPING: VolumeMapper / EffectParamMapping / MappingChain /
    preset_mapping / map_range / map_range_log / db_to_gain /
    gain_to_db / control_to_gain / velocity_to_gain /
    equal_power_wet_dry -- effect + volume mapping.
    engine.audio.create_volume_mapper('vol', curve='perceptual')
    engine.audio.create_mapping('cutoff', 'filter', 'frequency', 20, 20000, log=True)
  * PIPELINES: AudioSrc / PipelineStage / AudioSrcPipeline /
    AudioPipelineMixer -- node-based source pipelines.
    engine.audio.create_pipeline('lead', src='oscillator', freq=440)
"""

from scs_web_audio import (
    midi_to_freq, freq_to_midi, note_to_freq, note_to_midi,
    ClockMapping, AudioEvent,
    AutomationPoint, AutomationCurve,
    PatchNode, AudioPatch, make_default_patch,
    AudioEffect, EffectChain,
    TimelineEvent, Timeline,
    SpatialSoundSource, inverse_distance_gain,
    WebAudioEngine, SCSAudioEngine, shared_engine,
    # Batch 3: envelopes / mapping / pipelines
    CurveEnvelope, ADSREnvelope, adsr_envelope, envelope_preset,
    EnvelopeSegment,
    VolumeMapper, EffectParamMapping, MappingChain, preset_mapping,
    map_range, map_range_log, db_to_gain, gain_to_db,
    control_to_gain, gain_to_control, velocity_to_gain,
    equal_power_wet_dry,
    AudioSrc, PipelineStage, AudioSrcPipeline, AudioPipelineMixer,
)

# Old name for the engine.
AudioEngine = WebAudioEngine

__all__ = [
    'midi_to_freq', 'freq_to_midi', 'note_to_freq', 'note_to_midi',
    'ClockMapping', 'AudioEvent',
    'AutomationPoint', 'AutomationCurve',
    'PatchNode', 'AudioPatch', 'make_default_patch',
    'AudioEffect', 'EffectChain',
    'TimelineEvent', 'Timeline',
    'SpatialSoundSource', 'inverse_distance_gain',
    'WebAudioEngine', 'AudioEngine', 'SCSAudioEngine', 'shared_engine',
    # Envelopes
    'CurveEnvelope', 'ADSREnvelope', 'adsr_envelope', 'envelope_preset',
    'EnvelopeSegment',
    # Mapping
    'VolumeMapper', 'EffectParamMapping', 'MappingChain', 'preset_mapping',
    'map_range', 'map_range_log', 'db_to_gain', 'gain_to_db',
    'control_to_gain', 'gain_to_control', 'velocity_to_gain',
    'equal_power_wet_dry',
    # Pipelines
    'AudioSrc', 'PipelineStage', 'AudioSrcPipeline', 'AudioPipelineMixer',
]
