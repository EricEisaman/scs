from browser import window
import json

_signals = {}
_es = None

def _on_signals(evt):
    raw = evt.data.strip() if isinstance(evt.data, str) else ""
    if raw.startswith("signals "):
        raw = raw[8:]
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            _signals.update(data)
            # Also update BGS signals
            try:
                for k,v in data.items():
                    window._bgs_signals[k] = v
            except:
                pass
    except Exception as e:
        pass

def connect_sse(url):
    global _es
    if _es:
        try:
            _es.close()
        except:
            pass
    _es = window.EventSource.new(url)
    _es.addEventListener("datastar-patch-signals", _on_signals)
    window._scs_es = _es  # prevent Brython GC
    window._bgs_es = _es
    print(f"[datastar] SSE {url}")
    return _es

def get_signal(name, default=None):
    return _signals.get(name, default)

def set_signal(name, value):
    _signals[name] = value
    try:
        window._bgs_signals[name] = value
    except:
        pass

def get_game_snapshot():
    return dict(_signals)

def is_datastar_connected():
    try:
        return _es is not None and _es.readyState == 1
    except:
        return False
