# extensions/datastar.py
# SCS Extensions System - Datastar Integration (Model Layer)
# ==========================================================
# Strict MVC: Pure Model. No scs import, no drawing.
# Provides Brython helpers to integrate Datastar SSE signals with SCS canvas.
#
# Architecture:
#   Backend: datastar-py → SSE patch_signals({gameSnapshot, players, etc.})
#   Frontend JS: datastar.js → updates signals → window.Signals or window.__SCS_*
#   Brython: this module → reads window.Signals → feeds SCS model
#
# This is the "amazing" bridge: Datastar drives UI state, Brython drives canvas.
# No WebSockets - just SSE + HTTP actions (Datastar-native).

from browser import window, aio
import json as _pyjson

class DatastarError(Exception):
    pass

def _get_signals_object():
    """Try to get Signals object from various datastar setups"""
    # Try window.Signals (datastar-signals plugin)
    try:
        sig = getattr(window, 'Signals', None)
        if sig is not None:
            return sig
    except:
        pass
    # Try window.ds (some setups)
    try:
        ds = getattr(window, 'ds', None)
        if ds is not None:
            # ds.signal(name) returns signal object
            return ds
    except:
        pass
    return None

def get_signal(name: str, default=None):
    """
    Get a datastar signal value from JS.
    
    Supports:
    - window.Signals.<name> (datastar-signals plugin)
    - window.__SCS_GAME_STATE for gameSnapshot
    - window.<name> direct
    """
    # Special case for game snapshot stored via data-on-signal-patch
    if name == "gameSnapshot":
        try:
            if hasattr(window, '__SCS_GAME_STATE'):
                gs = getattr(window, '__SCS_GAME_STATE')
                # Could be JS object or JSON string
                return gs
        except:
            pass
        try:
            if hasattr(window, '__SCS_GAME_SNAPSHOT'):
                return getattr(window, '__SCS_GAME_SNAPSHOT')
        except:
            pass
    
    # Try Signals object
    try:
        sigs = _get_signals_object()
        if sigs is not None:
            # If it's ds object with signal() method
            if hasattr(sigs, 'signal'):
                try:
                    s = sigs.signal(name)
                    if hasattr(s, 'value'):
                        return s.value
                    return s
                except:
                    pass
            # Direct property
            if hasattr(sigs, name):
                return getattr(sigs, name)
    except Exception as e:
        pass
    
    # Try window directly
    try:
        if hasattr(window, name):
            return getattr(window, name)
    except:
        pass
    
    # Try localStorage fallback for persistence
    try:
        if hasattr(window, 'localStorage'):
            val = window.localStorage.getItem(f"scs_signal_{name}")
            if val:
                try:
                    return _pyjson.loads(val)
                except:
                    return val
    except:
        pass
    
    return default

def set_signal(name: str, value):
    """Set a datastar signal from Brython (triggers reactive update if plugin available)"""
    try:
        sigs = _get_signals_object()
        if sigs is not None and hasattr(sigs, name):
            setattr(sigs, name, value)
            return True
    except:
        pass
    try:
        # Set as window global and localStorage
        setattr(window, name, value)
        if hasattr(window, 'localStorage'):
            try:
                window.localStorage.setItem(f"scs_signal_{name}", _pyjson.dumps(value) if isinstance(value, (dict, list)) else str(value))
            except:
                pass
        return True
    except:
        pass
    return False

def get_game_snapshot():
    """
    Get the latest game snapshot from datastar.
    
    Server sends: patch_signals({"gameSnapshot": {"entities": [...], "platforms": [...], "coins": [...], "serverTick": N}})
    Client JS stores: window.__SCS_GAME_STATE = $gameSnapshot
    Brython reads: get_game_snapshot()
    """
    raw = get_signal("gameSnapshot") or get_signal("__SCS_GAME_STATE") or get_signal("__SCS_GAME_SNAPSHOT")
    if raw is None:
        return None
    
    # If it's a JS object, convert to Python dict via to_dict if available, else try json
    try:
        # Brython JS objects have special handling - try to convert
        if hasattr(raw, 'to_dict'):
            return raw.to_dict()
        # If it's already dict/list
        if isinstance(raw, (dict, list)):
            return raw
        # Try JSON parse if string
        if isinstance(raw, str):
            return _pyjson.loads(raw)
        # Try to iterate JS object properties via window.JSON.stringify then parse
        try:
            json_str = window.JSON.stringify(raw)
            return _pyjson.loads(json_str)
        except:
            pass
        # Last resort: return as is
        return raw
    except Exception as e:
        return None

def is_datastar_connected() -> bool:
    """Check if datastar is connected and streaming"""
    try:
        # Check for datastar connection indicator
        if hasattr(window, '__SCS_DATASTAR_CONNECTED'):
            return bool(getattr(window, '__SCS_DATASTAR_CONNECTED'))
        # Check if Signals object exists
        if _get_signals_object() is not None:
            return True
        # Check if game snapshot exists
        if get_game_snapshot() is not None:
            return True
    except:
        pass
    return False

async def send_input_action(base_url: str, room_id: str, player_id: str, move_x: int, jump: bool, seq: int):
    """
    Send player input to server via HTTP POST.
    This is the client->server path (Datastar actions are HTTP under the hood).
    
    Server endpoint: POST /api/v1/rooms/{room_id}/input
    Body: {playerId, moveX, jump, seq}
    """
    from .fetch import fetch_json
    url = f"{base_url.rstrip('/')}/api/v1/rooms/{room_id}/input"
    try:
        result = await fetch_json(url, method='POST', body={
            "playerId": player_id,
            "moveX": max(-1, min(1, move_x)),
            "jump": bool(jump),
            "seq": seq
        })
        return result
    except Exception as e:
        raise DatastarError(f"send_input failed: {e}")

async def join_room_action(base_url: str, room_id: str, player_name: str):
    """Join a room via HTTP"""
    from .fetch import fetch_json
    url = f"{base_url.rstrip('/')}/api/v1/rooms/{room_id}/join"
    try:
        result = await fetch_json(url, method='POST', body={"playerName": player_name})
        return result
    except Exception as e:
        raise DatastarError(f"join_room failed: {e}")

async def create_room_action(base_url: str):
    """Create a room via HTTP"""
    from .fetch import fetch_json
    url = f"{base_url.rstrip('/')}/api/v1/rooms"
    try:
        result = await fetch_json(url, method='POST', body={})
        return result
    except Exception as e:
        raise DatastarError(f"create_room failed: {e}")

# For apps that need to run async from sync onAppStart
def run(coro):
    return aio.run(coro)

__all__ = [
    'get_signal', 'set_signal', 'get_game_snapshot',
    'is_datastar_connected',
    'send_input_action', 'join_room_action', 'create_room_action',
    'DatastarError', 'run'
]
