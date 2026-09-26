
from browser import window

_signals_store = {}
_attached_es = None

if not hasattr(window, "_bgs_es"):
    window._bgs_es = None
if not hasattr(window, "_bgs_last_patch_ms"):
    window._bgs_last_patch_ms = 0
if not hasattr(window, "_bgs_signals_json"):
    window._bgs_signals_json = "{}"

def _js_to_py_safe(js_obj):
    try:
        if js_obj is None:
            return None
    except:
        pass
    try:
        if window.JSON.stringify(js_obj) == "null":
            return None
    except:
        pass
    try:
        t = window.typeof(js_obj)
    except:
        t = ""
    if t == "number":
        try:
            return float(str(js_obj))
        except:
            return 0.0
    if t == "string":
        return str(js_obj)
    if t == "boolean":
        return bool(js_obj)
    if t == "object":
        try:
            if bool(window.Array.isArray(js_obj)):
                result = []
                ln = int(js_obj.length)
                for i in range(ln):
                    try:
                        result.append(_js_to_py_safe(js_obj[i]))
                    except:
                        result.append(None)
                return result
            keys = window.Object.keys(js_obj)
            result = {}
            kl = int(keys.length)
            for idx in range(kl):
                try:
                    k = keys[idx]
                    result[str(k)] = _js_to_py_safe(js_obj[k])
                except:
                    continue
            return result
        except Exception as e:
            try:
                window.console.log("[_js_to_py_safe] error", str(e))
            except:
                pass
    return None

def _sync_debug_signals():
    try:
        import json as _j
        window._bgs_signals_json = _j.dumps(_signals_store)
    except:
        window._bgs_signals_json = "{}"
    try:
        window._bgs_signals_debug = window.JSON.parse(window._bgs_signals_json)
    except:
        pass

def _parse_datastar_patch(raw):
    if raw is None:
        return None, False
    try:
        raw = str(raw)
    except:
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
        js_patch = window.JSON.parse(signals_json)
        patch = _js_to_py_safe(js_patch)
    except Exception as exc:
        try:
            window.console.error("[BGS] Invalid Datastar signal JSON:", exc, signals_json[:500])
        except:
            pass
        return
    if not isinstance(patch, dict):
        return
    if only_if_missing:
        filtered = {}
        for k, v in patch.items():
            if v is not None:
                filtered[k] = v
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
    return _signals_store.get(name, default)

def is_connected(max_silence_ms=10000):
    try:
        es = window._bgs_es
        if not es:
            return False
        try:
            rs = getattr(es, "readyState", 0)
            if rs != 1:
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
        if _attached_es and es == _attached_es:
            return
    except:
        try:
            if _attached_es == es:
                return
        except:
            pass
    if _attached_es:
        try:
            _attached_es.removeEventListener("datastar-patch-signals", _on_datastar_patch)
        except:
            pass
    try:
        es.addEventListener("datastar-patch-signals", _on_datastar_patch)
    except Exception as exc:
        try:
            window.console.error("[BGS] Failed to attach", exc)
        except:
            pass
        raise
    _attached_es = es
    window._bgs_es = es
