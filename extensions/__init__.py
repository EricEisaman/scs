"""SCS Extensions - Well-designed Python APIs"""
try:
    from .fetch import fetch, fetch_json, fetch_text, FetchError, FetchResponse
except: pass
try:
    from .datastar import get_signal, set_signal, get_game_snapshot, is_datastar_connected
except: pass
try:
    from .multiplayer import MultiplayerClient, CharacterState, MultiplayerError
except: pass
try:
    from .proc_audio import AudioEngine, Patch, Bus, SoundHandle, SeededRandom, SpatialSource, OfflineRenderer, Recorder, sfx, BUILTIN_PRESETS, QUALITY_PROFILES
except: pass
