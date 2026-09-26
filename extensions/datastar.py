from browser import window
import json as py_json

# === Ownership ===
# Python state: source of truth for Brython gameplay
_signals_store = {}
# Browser state: EventSource object
_attached_es = None

if not hasattr(window, "_bgs_es"):
    window._bgs_es = None
if not hasattr(window, "_bgs_last_patch_ms"):
    window._bgs_last_patch_ms = 0
# Debug snapshots only - never read for game logic
if not hasattr(window, "_bgs_signals_json"):
    window._bgs_signals_json = "{}"

def _sync_debug_signals():
    try:
        window._bgs_signals_json = py_json.dumps(_signals_store)
    except Exception:
        try:
            window._bgs_signals_json = "{}"
        except:
            pass
    # Optional JS object mirror for console inspection - clearly named debug only
    try:
        window._bgs_signals_debug = window.JSON.parse(window._bgs_signals_json)
    except:
        pass

def _parse_datastar_patch(raw):
    # raw may be JS string wrapper - coerce to Python str
    if raw is None:
        return None, False
    try:
        raw = str(raw)
    except Exception:
        return None, False
    signals_json = None
    only_if_missing = False
    for line in raw.splitlines():
        if line.startswith("signals "):
            signals_json = line[len("signals "):]
        elif line.startswith("onlyIfMissing "):
            only_if_missing = line[len("onlyIfMissing "):].strip().lower() == "true"
    return signals_json, only_if_missing

def _merge_patch(target, patch):
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict):
            existing = target.get(key)
            if not isinstance(existing, dict):
                existing = {}
                target[key] = existing
            _merge_patch(existing, value)
        else:
            target[key] = value

def _merge_if_missing(target, patch):
    for key, value in patch.items():
        if key not in target:
            target[key] = value
            continue
        current = target[key]
        if isinstance(current, dict) and isinstance(value, dict):
            _merge_if_missing(current, value)

def _on_datastar_patch(evt):
    raw = getattr(evt, "data", None)
    if not raw:
        return
    signals_json, only_if_missing = _parse_datastar_patch(raw)
    if signals_json is None:
        return
    try:
        patch = py_json.loads(signals_json)
    except Exception as exc:
        try:
            window.console.error("[BGS] Invalid Datastar signal JSON:", exc, signals_json[:500])
        except:
            pass
        return
    if not isinstance(patch, dict):
        try:
            window.console.warn("[BGS] Signal patch was not an object:", patch)
        except:
            pass
        return
    # Respect Datastar semantics: onlyIfMissing true = init defaults only, no deletes
    if only_if_missing:
        # If patch contains null with onlyIfMissing, ignore deletes per sister's contract advice
        # Filter nulls out for onlyIfMissing case
        filtered = {k: v for k, v in patch.items() if v is not None}
        if not filtered:
            return
        _merge_if_missing(_signals_store, filtered)
    else:
        _merge_patch(_signals_store, patch)
    try:
        window._bgs_last_patch_ms = int(window.Date.now())
    except:
        pass
    _sync_debug_signals()

def get_signal(name, default=None):
    # Always read from Python-owned store - never from window
    return _signals_store.get(name, default)

def is_connected(max_silence_ms=10000):
    try:
        es = window._bgs_es
        if not es:
            return False
        try:
            if es.readyState != 1:
                return False
        except:
            return False
        last = getattr(window, "_bgs_last_patch_ms", 0)
        if last == 0:
            return True
        try:
            now = int(window.Date.now())
            return (now - last) <= max_silence_ms
        except:
            return True
    except:
        return False

def attach_to_eventsource(es):
    global _attached_es
    if not es:
        raise ValueError("attach_to_eventsource requires an EventSource")
    try:
        if _attached_es is not None and es == _attached_es:
            return
    except:
        if _attached_es == es:
            return
    if _attached_es:
        try:
            _attached_es.removeEventListener("datastar-patch-signals", _on_datastar_patch)
        except Exception:
            pass
    try:
        es.addEventListener("datastar-patch-signals", _on_datastar_patch)
    except Exception as exc:
        try:
            window.console.error("[BGS] Failed to attach datastar listener:", exc)
        except:
            pass
        raise
    _attached_es = es
    window._bgs_es = es
