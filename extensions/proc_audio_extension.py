"""
proc_audio_extension.py - SCS Extension wrapper for procedural audio

This file is the official SCS extension entry point.
It re-exports proc_audio library and provides integration helpers for games.

Usage in any SCS app:

from proc_audio_extension import audio, sfx, Patch, Bus

# in onAppStart:
audio.resume()  # call on first user interaction

# in onKeyPress etc:
sfx.play("jump", pitch=1.2, seed=event_id)
audio.play("weapon.laser_01", position=(x,y,z), spatial=True)

# custom patch:
laser = Patch().oscillator("sawtooth", 880).pitch_envelope(2400,160,0.18).filter("lowpass",3200).envelope(0.002,0.12,0,0.04)
audio.play(laser, seed=42)

Features included:
- High-level sfx.play API
- Low-level Patch graph builder
- JSON serialization, determinism, variation
- Buses, ducking, spatial, occlusion, polyphony, burst protection
- Offline WAV baking, recording, analysis
- Quality profiles, capability detection, autoplay handling
"""

try:
    from proc_audio import (
        AudioEngine,
        Patch,
        Bus,
        SoundHandle,
        SeededRandom,
        SpatialSource,
        OfflineRenderer,
        Recorder,
        sfx,
        BUILTIN_PRESETS,
        QUALITY_PROFILES,
        WORKLET_JS,
        MANIFEST_EXAMPLE
    )
    HAS_LIB = True
except Exception as e:
    try:
        import proc_audio as _pa
        AudioEngine = _pa.AudioEngine
        Patch = _pa.Patch
        Bus = _pa.Bus
        SoundHandle = _pa.SoundHandle
        SeededRandom = _pa.SeededRandom
        SpatialSource = _pa.SpatialSource
        OfflineRenderer = _pa.OfflineRenderer
        Recorder = _pa.Recorder
        sfx = _pa.sfx
        BUILTIN_PRESETS = _pa.BUILTIN_PRESETS
        QUALITY_PROFILES = _pa.QUALITY_PROFILES
        WORKLET_JS = _pa.WORKLET_JS
        MANIFEST_EXAMPLE = _pa.MANIFEST_EXAMPLE
        HAS_LIB = True
    except Exception as e2:
        HAS_LIB = False
        AudioEngine = None
        Patch = None

# Singleton engine for easy use
_audio_engine = None

def get_audio_engine(quality="high", seed=None, **kw):
    global _audio_engine
    if _audio_engine is None and HAS_LIB:
        _audio_engine = AudioEngine(quality=quality, seed=seed, **kw)
    return _audio_engine

# Default engine instance - lazy
audio = get_audio_engine() if HAS_LIB else None

# Re-export sfx singleton
# sfx already imported

# Helper: unlock audio from any SCS event
def unlock_audio(event=None):
    if audio:
        return audio.resume()
    if sfx:
        return sfx.resume()
    return False

# Helper: play with deterministic seed from event id
def play_event(event_id, preset_name, **kw):
    seed = hash(event_id) & 0x7FFFFFFF if isinstance(event_id, str) else int(event_id)
    if sfx:
        return sfx.play(preset_name, seed=seed, **kw)
    if audio:
        return audio.play(preset_name, seed=seed, **kw)
    return None

# Export list
__all__ = [
    "AudioEngine",
    "Patch",
    "Bus",
    "SoundHandle",
    "SeededRandom",
    "SpatialSource",
    "OfflineRenderer",
    "Recorder",
    "sfx",
    "audio",
    "get_audio_engine",
    "unlock_audio",
    "play_event",
    "BUILTIN_PRESETS",
    "QUALITY_PROFILES"
]
