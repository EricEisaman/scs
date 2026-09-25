"""SCS Extensions - Well-designed Python APIs"""
try:
    from . import fetch
    from .fetch import fetch as _fetch, fetch_json, fetch_text, FetchError, FetchResponse
except:
    pass
try:
    from . import datastar
    from .datastar import get_signal, set_signal, get_game_snapshot, is_datastar_connected
except:
    pass
try:
    from . import multiplayer
    from .multiplayer import MultiplayerClient, CharacterState, MultiplayerError
except:
    pass
try:
    from . import proc_audio
except:
    pass
