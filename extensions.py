# extensions.py - Root shim for Brython GitHub Pages
# Fixes 404 for ./extensions.py - Brython tries this before ./extensions/__init__.py
# V26 FIX: Do NOT pre-create empty placeholders - they cache without MultiplayerClient and never get overwritten
import sys

try:
    __path__ = ['extensions']
except:
    pass

# DELETE any cached empty placeholder before real import - this is the bug fix
# Old code: sys.modules[f] = ModuleType(f) creates empty module without MultiplayerClient
# Brython's IndexedDB then caches it forever
for _mod_name in ['extensions.multiplayer', 'extensions.datastar', 'extensions.fetch', 'extensions.proc_audio']:
    if _mod_name in sys.modules:
        try:
            # If module has no MultiplayerClient (empty placeholder), delete it so real file loads
            mod = sys.modules[_mod_name]
            if _mod_name == 'extensions.multiplayer' and not hasattr(mod, 'MultiplayerClient'):
                del sys.modules[_mod_name]
        except:
            pass

# Now import real implementations
try:
    from extensions.fetch import fetch, fetch_json, fetch_text, FetchError, FetchResponse
    import types
    if 'extensions.fetch' not in sys.modules or not hasattr(sys.modules['extensions.fetch'], 'fetch'):
        m = types.ModuleType('extensions.fetch')
        m.fetch = fetch
        m.fetch_json = fetch_json
        m.fetch_text = fetch_text
        m.FetchError = FetchError
        m.FetchResponse = FetchResponse
        sys.modules['extensions.fetch'] = m
    else:
        m = sys.modules['extensions.fetch']
        m.fetch = fetch
        m.fetch_json = fetch_json
        m.fetch_text = fetch_text
        m.FetchError = FetchError
        m.FetchResponse = FetchResponse
except:
    pass

try:
    from extensions.datastar import get_signal, set_signal, get_game_snapshot, is_datastar_connected, connect_sse
    import types
    if 'extensions.datastar' not in sys.modules or not hasattr(sys.modules['extensions.datastar'], 'get_signal'):
        m = types.ModuleType('extensions.datastar')
        sys.modules['extensions.datastar'] = m
    else:
        m = sys.modules['extensions.datastar']
    m.get_signal = get_signal
    m.set_signal = set_signal
    m.get_game_snapshot = get_game_snapshot
    m.is_datastar_connected = is_datastar_connected
    try:
        m.connect_sse = connect_sse
    except:
        pass
except:
    try:
        from extensions.datastar import get_signal, set_signal, get_game_snapshot, is_datastar_connected
        import types
        m = types.ModuleType('extensions.datastar')
        m.get_signal = get_signal
        m.set_signal = set_signal
        m.get_game_snapshot = get_game_snapshot
        m.is_datastar_connected = is_datastar_connected
        sys.modules['extensions.datastar'] = m
    except:
        pass

# multiplayer - CRITICAL: delete empty cached version first
try:
    if 'extensions.multiplayer' in sys.modules:
        del sys.modules['extensions.multiplayer']
except:
    pass

try:
    from extensions.multiplayer import MultiplayerClient, CharacterState, MultiplayerError
    import types
    m = types.ModuleType('extensions.multiplayer')
    m.MultiplayerClient = MultiplayerClient
    m.CharacterState = CharacterState
    m.MultiplayerError = MultiplayerError
    sys.modules['extensions.multiplayer'] = m
    # Also set on real module
    try:
        import extensions.multiplayer as _real_mp
        _real_mp.MultiplayerClient = MultiplayerClient
        _real_mp.CharacterState = CharacterState
        _real_mp.MultiplayerError = MultiplayerError
    except:
        pass
except Exception as e:
    print(f"[extensions.py] multiplayer import failed: {e}")
    pass

# proc_audio - import WITHOUT pre-created placeholder
try:
    import extensions.proc_audio as _real_pa
    sys.modules['extensions.proc_audio'] = _real_pa
except:
    pass
