# extensions.py - Root shim for Brython GitHub Pages
# Fixes 404 for ./extensions.py - Brython tries this before ./extensions/__init__.py
import sys, types
try:
    __path__ = ['extensions']
except: pass
# Only pre-create placeholders for original extensions - NOT proc_audio
# Pre-creating placeholder for proc_audio blocks real file from loading
for _n in ['fetch','datastar','multiplayer']:
    _f = f'extensions.{_n}'
    if _f not in sys.modules:
        try:
            sys.modules[_f] = types.ModuleType(_f)
        except: pass
try:
    from extensions.fetch import fetch, fetch_json, fetch_text, FetchError, FetchResponse
    sys.modules['extensions.fetch'].fetch = fetch
    sys.modules['extensions.fetch'].fetch_json = fetch_json
    sys.modules['extensions.fetch'].fetch_text = fetch_text
    sys.modules['extensions.fetch'].FetchError = FetchError
    sys.modules['extensions.fetch'].FetchResponse = FetchResponse
except: pass
try:
    from extensions.datastar import get_signal, set_signal, get_game_snapshot, is_datastar_connected
    sys.modules['extensions.datastar'].get_signal = get_signal
    sys.modules['extensions.datastar'].set_signal = set_signal
    sys.modules['extensions.datastar'].get_game_snapshot = get_game_snapshot
    sys.modules['extensions.datastar'].is_datastar_connected = is_datastar_connected
except: pass
try:
    from extensions.multiplayer import MultiplayerClient, CharacterState, MultiplayerError
    sys.modules['extensions.multiplayer'].MultiplayerClient = MultiplayerClient
    sys.modules['extensions.multiplayer'].CharacterState = CharacterState
    sys.modules['extensions.multiplayer'].MultiplayerError = MultiplayerError
except: pass
# proc_audio - import WITHOUT pre-created placeholder so real file loads
try:
    import extensions.proc_audio as _real_pa
    sys.modules['extensions.proc_audio'] = _real_pa
except: pass
