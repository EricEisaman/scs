# extensions/datastar.py - Model-only, Brython + Datastar v1 best practice
from browser import window
import json

_signals = {}
_es = None
_connected = False

def _parse_signals_data(raw: str):
    # Datastar sends: "signals {\"key\": value}"
    raw = raw.strip()
    if raw.startswith("signals "):
        raw = raw[8:]
    return json.loads(raw)

def _on_patch_signals(evt):
    global _signals
    try:
        data = _parse_signals_data(evt.data)
        # data is { "character-state-update": {...}, "client-joined": {...} }
        _signals.update(data)
    except Exception as e:
        print(f"[datastar] parse error {e}: {evt.data[:200]}")

def _on_open(evt):
    global _connected
    _connected = True
    print("[datastar] SSE OPEN")

def _on_error(evt):
    global _connected
    _connected = False
    print("[datastar] SSE ERROR - will auto-reconnect")

def connect_sse(url: str):
    global _es, _connected
    if _es:
        try: _es.close()
        except: pass
    print(f"[datastar] connecting {url}")
    _es = window.EventSource.new(url)
    _es.addEventListener("datastar-patch-signals", _on_patch_signals)
    # optional: ignore element patches for this game
    _es.onopen = _on_open
    _es.onerror = _on_error
    # keep alive reference - Brython GC kills unreferenced ES
    window._scs_datastar_es = _es
    return _es

def get_signal(name, default=None):
    return _signals.get(name, default)

def is_datastar_connected():
    global _es, _connected
    if not _es:
        return False
    # 0=CONNECTING, 1=OPEN, 2=CLOSED
    return _es.readyState == 1 and _connected

def disconnect():
    global _es, _connected
    if _es:
        _es.close()
        _es = None
    _connected = False