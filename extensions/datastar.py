from browser import window
import json

# Shared state - Python-native dict
if not hasattr(window, "_bgs_signals"):
    window._bgs_signals = {}
if not hasattr(window, "_bgs_es"):
    window._bgs_es = None
if not hasattr(window, "_bgs_last_patch_ms"):
    window._bgs_last_patch_ms = 0

# Python-side guard for duplicate listeners (in case JS property on ES proxy fails)
_attached_es_ids = set()

def _extract_signals_json(raw):
    """Extract signals JSON by Datastar spec: line starting with 'signals '"""
    if not isinstance(raw, str):
        return None
    for line in raw.splitlines():
        if line.startswith("signals "):
            return line[len("signals "):]
    return None

def _parse_datastar_patch(raw):
    """Parse Datastar patch lines per spec: signals + onlyIfMissing"""
    signals_json = None
    only_if_missing = False
    if not isinstance(raw, str):
        return None, False
    for line in raw.splitlines():
        if line.startswith("signals "):
            signals_json = line[len("signals "):]
        elif line.startswith("onlyIfMissing "):
            only_if_missing = line[len("onlyIfMissing "):].strip().lower() == "true"
    return signals_json, only_if_missing

def _merge_patch(target, patch):
    """JSON Merge Patch-like semantics with null = deletion"""
    for key, value in patch.items():
        if value is None:
            # Datastar: null/undefined = remove signal
            target.pop(key, None)
        elif isinstance(value, dict):
            existing = target.get(key)
            if not isinstance(existing, dict):
                existing = {}
                target[key] = existing
            _merge_patch(existing, value)
        else:
            target[key] = value

def _on_datastar_patch(evt):
    raw = getattr(evt, "data", None)
    if not raw:
        return
    signals_json, only_if_missing = _parse_datastar_patch(raw)
    if signals_json is None:
        # Not a signals patch, ignore
        return
    try:
        patch = json.loads(signals_json)
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
    # Handle onlyIfMissing semantics
    if only_if_missing:
        # Only keep keys that don't exist in current store
        filtered = {}
        for k, v in patch.items():
            if k not in window._bgs_signals:
                filtered[k] = v
        if not filtered:
            return
        patch = filtered
    _merge_patch(window._bgs_signals, patch)
    try:
        window._bgs_last_patch_ms = int(window.Date.now())
    except:
        pass

def get_signal(name, default=None):
    """Returns Python-native values (dict/list/str/int/bool/None)"""
    return window._bgs_signals.get(name, default)

def is_connected(max_silence_ms=10000):
    """True if EventSource OPEN and recent data (or just OPEN if no data yet)"""
    try:
        es = window._bgs_es
        if es is None or es.readyState != 1:
            return False
        last = getattr(window, "_bgs_last_patch_ms", 0)
        if last == 0:
            # Connected but no patch yet - still considered connected for backward compat
            return True
        try:
            now = int(window.Date.now())
            return (now - last) <= max_silence_ms
        except:
            return True
    except Exception:
        return False

def attach_to_eventsource(es):
    """Attach once, guard against duplicates"""
    if es is None:
        raise ValueError("attach_to_eventsource requires an EventSource")
    # JS property guard
    try:
        if getattr(es, "_bgs_listener_attached", False):
            window._bgs_es = es
            return
    except:
        pass
    # Python-side guard using id
    try:
        es_id = id(es)
        if es_id in _attached_es_ids and window._bgs_es is es:
            return
    except:
        pass
    try:
        es.addEventListener("datastar-patch-signals", _on_datastar_patch)
        try:
            es._bgs_listener_attached = True
        except:
            pass
        try:
            _attached_es_ids.add(id(es))
        except:
            pass
        window._bgs_es = es
    except Exception as exc:
        try:
            window.console.error("[BGS] Failed to attach datastar listener:", exc)
        except:
            pass
        raise
