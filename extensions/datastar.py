from browser import window

if not hasattr(window, "_bgs_signals"):
    window._bgs_signals = {}
if not hasattr(window, "_bgs_es"):
    window._bgs_es = None

def _js_to_py(js_val, depth=0):
    if depth > 20:
        return None
    try:
        if js_val is None:
            return None
        if isinstance(js_val, (str, int, float, bool)):
            return js_val
        if isinstance(js_val, dict):
            return {k: _js_to_py(v, depth+1) for k, v in js_val.items()}
        if isinstance(js_val, (list, tuple)):
            return [_js_to_py(x, depth+1) for x in js_val]
        try:
            if window.Array.isArray(js_val):
                return [_js_to_py(js_val[i], depth+1) for i in range(int(js_val.length))]
        except:
            pass
        try:
            keys = window.Object.keys(js_val)
            result = {}
            for i in range(len(keys)):
                k = keys[i]
                try:
                    result[k] = _js_to_py(js_val[k], depth+1)
                except:
                    continue
            return result
        except:
            return js_val
    except:
        return None

def _merge_patch(target, patch):
    if patch is None:
        return None
    if not isinstance(patch, dict):
        return patch
    if not isinstance(target, dict):
        target = {}
    for k, v in patch.items():
        if v is None:
            if k in target:
                del target[k]
        else:
            if isinstance(v, dict) and isinstance(target.get(k), dict):
                target[k] = _merge_patch(target.get(k, {}), v)
            else:
                target[k] = v
    return target

def _on_datastar_patch(evt):
    try:
        raw = evt.data
        if not raw:
            return
        try:
            lines = raw.splitlines()
            if len(lines) == 0:
                lines = [raw]
        except:
            lines = [raw]
        signal_line = None
        only_if_missing = False
        for line in lines:
            if not isinstance(line, str):
                continue
            stripped = line.strip()
            if stripped.startswith("signals "):
                signal_line = stripped[8:].strip()
            elif stripped.startswith("signals"):
                idx = stripped.find("{")
                if idx != -1:
                    signal_line = stripped[idx:].strip()
            elif "onlyIfMissing" in stripped and "true" in stripped.lower():
                only_if_missing = True
        if not signal_line:
            try:
                for l in lines:
                    if "{" in l:
                        start = l.find("{")
                        signal_line = l[start:].strip()
                        if "onlyIfMissing" in signal_line:
                            signal_line = signal_line[:signal_line.find("onlyIfMissing")].strip()
                        break
            except:
                pass
        if not signal_line:
            return
        try:
            js_parsed = window.JSON.parse(signal_line)
        except:
            return
        try:
            keys = window.Object.keys(js_parsed)
            for i in range(len(keys)):
                k = keys[i]
                try:
                    v = js_parsed[k]
                    if v is None:
                        try:
                            if k in window._bgs_signals:
                                del window._bgs_signals[k]
                        except:
                            window._bgs_signals[k] = None
                        continue
                    if only_if_missing and k in window._bgs_signals:
                        continue
                    py_v = _js_to_py(v)
                    if py_v is None:
                        continue
                    existing = window._bgs_signals.get(k)
                    if isinstance(existing, dict) and isinstance(py_v, dict):
                        window._bgs_signals[k] = _merge_patch(existing, py_v)
                    else:
                        window._bgs_signals[k] = py_v
                except:
                    continue
        except:
            pass
    except:
        pass

def get_signal(name, default=None):
    try:
        return window._bgs_signals.get(name, default)
    except:
        try:
            return window._bgs_signals[name]
        except:
            return default

def is_connected():
    try:
        es = window._bgs_es
        if not es:
            return False
        return es.readyState == 1
    except:
        return False

def attach_to_eventsource(es):
    try:
        es.addEventListener("datastar-patch-signals", _on_datastar_patch)
        window._bgs_es = es
    except:
        pass
