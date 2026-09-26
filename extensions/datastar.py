from browser import window
import json as py_json

if not hasattr(window, "_bgs_signals"):
    window._bgs_signals = {}
if not hasattr(window, "_bgs_es"):
    window._bgs_es = None

def _merge_patch(target, patch):
    if patch is None:
        return None
    if not isinstance(patch, dict):
        return patch
    if not isinstance(target, dict):
        target = {}
    for k in patch:
        v = patch[k]
        if v is None:
            if k in target:
                del target[k]
        else:
            tv = target.get(k)
            if isinstance(v, dict) and isinstance(tv, dict):
                target[k] = _merge_patch(tv, v)
            else:
                target[k] = v
    return target

def _on_datastar_patch(evt):
    try:
        raw = evt.data
        if not raw:
            return
        lines = raw.split("\n")
        # Handle both \n joined and actual newlines
        tmp = []
        for l in lines:
            tmp.extend(l.splitlines())
        lines = tmp
        signal_line = None
        only_if_missing = False
        for line in lines:
            if not isinstance(line, str):
                continue
            s = line.strip()
            if s.startswith("signals "):
                signal_line = s[8:].strip()
            elif s.startswith("signals"):
                idx = s.find("{")
                if idx != -1:
                    signal_line = s[idx:].strip()
            if "onlyIfMissing" in s and "true" in s.lower():
                only_if_missing = True
        if not signal_line:
            for l in lines:
                if "{" in l:
                    idx = l.find("{")
                    signal_line = l[idx:].strip()
                    break
        if not signal_line:
            return
        try:
            js_parsed = window.JSON.parse(signal_line)
            data = py_json.loads(window.JSON.stringify(js_parsed))
        except:
            return
        for k in data:
            try:
                v = data[k]
                if v is None:
                    try:
                        if k in window._bgs_signals:
                            del window._bgs_signals[k]
                    except:
                        pass
                    continue
                if only_if_missing and k in window._bgs_signals:
                    continue
                existing = window._bgs_signals.get(k)
                if isinstance(existing, dict) and isinstance(v, dict):
                    window._bgs_signals[k] = _merge_patch(existing, v)
                else:
                    window._bgs_signals[k] = v
            except:
                continue
    except:
        pass

def get_signal(name, default=None):
    try:
        return window._bgs_signals.get(name, default)
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
        es.addEventListener("multiplayer-snapshot", _on_datastar_patch)
        window._bgs_es = es
    except:
        pass
