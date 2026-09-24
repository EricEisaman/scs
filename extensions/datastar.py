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
    except Exception as e:
        # print(f"[datastar] parse fail {e} raw={raw[:100]}")
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
    print(f"[datastar] SSE {url}")
    return _es

def get_signal(name, default=None):
    return _signals.get(name, default)

def is_datastar_connected():
    try:
        return _es is not None and _es.readyState == 1
    except:
        return False
