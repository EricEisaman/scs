# extensions.py - Root shim for Brython GitHub Pages
# Fixes 404 for ./extensions.py - Brython tries this before ./extensions/__init__.py
# V25 FIX: Do NOT pre-create empty placeholders - they cache without MultiplayerClient
import sys

try:
    __path__ = ['extensions']
except:
    pass

# IMPORTANT: Do NOT pre-create sys.modules['extensions.multiplayer'] etc.
# Old code did: sys.modules[f] = ModuleType(f) which cached empty module
# causing "[BGS] MP import failed (cached mp_ext has no MultiplayerClient)"
# Let real files load naturally

# Try to import real implementations and expose them on sys.modules
# This ensures even if Brython's IndexedDB has empty cached version, we overwrite

def _ensure_module(name, attrs):
    """Ensure sys.modules[name] has attrs from real module"""
    try:
        # Import real file
        __import__(name)
        mod = sys.modules.get(name)
        if mod:
            for attr_name, attr_val in attrs.items():
                setattr(mod, attr_name, attr_val)
            return True
    except Exception as e:
        pass
    return False

# fetch
try:
    from extensions.fetch import fetch, fetch_json, fetch_text, FetchError, FetchResponse
    if 'extensions.fetch' in sys.modules:
        m = sys.modules['extensions.fetch']
        m.fetch = fetch
        m.fetch_json = fetch_json
        m.fetch_text = fetch_text
        m.FetchError = FetchError
        m.FetchResponse = FetchResponse
    else:
        import types
        m = types.ModuleType('extensions.fetch')
        m.fetch = fetch
        m.fetch_json = fetch_json
        m.fetch_text = fetch_text
        m.FetchError = FetchError
        m.FetchResponse = FetchResponse
        sys.modules['extensions.fetch'] = m
except Exception:
    pass

# datastar
try:
    from extensions.datastar import get_signal, set_signal, get_game_snapshot, is_datastar_connected, connect_sse
    if 'extensions.datastar' in sys.modules:
        m = sys.modules['extensions.datastar']
        m.get_signal = get_signal
        m.set_signal = set_signal
        m.get_game_snapshot = get_game_snapshot
        m.is_datastar_connected = is_datastar_connected
        try:
            m.connect_sse = connect_sse
        except:
            pass
    else:
        import types
        m = types.ModuleType('extensions.datastar')
        m.get_signal = get_signal
        m.set_signal = set_signal
        m.get_game_snapshot = get_game_snapshot
        m.is_datastar_connected = is_datastar_connected
        try:
            m.connect_sse = connect_sse
        except:
            pass
        sys.modules['extensions.datastar'] = m
except Exception:
    pass

# multiplayer - CRITICAL FIX for cached empty module
try:
    # Force re-import real file, not cached empty placeholder
    if 'extensions.multiplayer' in sys.modules:
        # Delete cached empty version so real file loads
        del sys.modules['extensions.multiplayer']
    from extensions.multiplayer import MultiplayerClient, CharacterState, MultiplayerError
    import types
    m = types.ModuleType('extensions.multiplayer')
    m.MultiplayerClient = MultiplayerClient
    m.CharacterState = CharacterState
    m.MultiplayerError = MultiplayerError
    sys.modules['extensions.multiplayer'] = m
    # Also ensure extensions.multiplayer is importable
    try:
        import extensions.multiplayer as _mp_real
        _mp_real.MultiplayerClient = MultiplayerClient
        _mp_real.CharacterState = CharacterState
        _mp_real.MultiplayerError = MultiplayerError
    except:
        pass
except Exception as e:
    # If real import fails, try to at least keep whatever was there
    try:
        from extensions.multiplayer import MultiplayerClient, CharacterState, MultiplayerError
        if 'extensions.multiplayer' not in sys.modules:
            import types
            m = types.ModuleType('extensions.multiplayer')
            sys.modules['extensions.multiplayer'] = m
        sys.modules['extensions.multiplayer'].MultiplayerClient = MultiplayerClient
        sys.modules['extensions.multiplayer'].CharacterState = CharacterState
        sys.modules['extensions.multiplayer'].MultiplayerError = MultiplayerError
    except:
        pass

# proc_audio - import WITHOUT pre-created placeholder so real file loads
try:
    import extensions.proc_audio as _real_pa
    sys.modules['extensions.proc_audio'] = _real_pa
except:
    pass
