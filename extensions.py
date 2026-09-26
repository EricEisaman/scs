# extensions.py - v3.0.25 - FIX module callable + e-15 SAFE
import sys, types
from browser import window

try:
    import extensions as _ext_pkg
except:
    _ext_pkg = types.ModuleType('extensions')
    sys.modules['extensions'] = _ext_pkg

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
    if isinstance(js_obj, (str, int, float, bool)):
        return js_obj
    try:
        is_arr = False
        try:
            is_arr = bool(window.Array.isArray(js_obj))
        except:
            is_arr = False
        if is_arr:
            result = []
            ln = int(js_obj.length)
            for i in range(ln):
                try:
                    result.append(_js_to_py_safe(js_obj[i]))
                except:
                    result.append(None)
            return result
        try:
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
        except:
            pass
    except Exception as e:
        try:
            window.console.log("[_js_to_py_safe] error", str(e))
        except:
            pass
    try:
        s = str(js_obj)
        if "e" in s.lower() or s.replace(".","",1).replace("-","",1).isdigit():
            try:
                return float(s)
            except:
                pass
        return s
    except:
        return None

def _js_to_py_simple(js_obj):
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
    if isinstance(js_obj, (str, int, float, bool)):
        return js_obj
    try:
        is_arr = False
        try:
            is_arr = bool(window.Array.isArray(js_obj))
        except:
            is_arr = False
        if is_arr:
            res = []
            for i in range(int(js_obj.length)):
                res.append(_js_to_py_simple(js_obj[i]))
            return res
        try:
            keys = window.Object.keys(js_obj)
            res = {}
            for idx in range(int(keys.length)):
                k = keys[idx]
                res[str(k)] = _js_to_py_simple(js_obj[k])
            return res
        except:
            pass
    except:
        pass
    try:
        s = str(js_obj)
        if "e" in s.lower() or s.replace(".","",1).replace("-","",1).isdigit():
            try:
                return float(s)
            except:
                pass
        return s
    except:
        return js_obj

def _parse_join_data(js_data):
    cid = None
    sid = None
    is_sync = False
    env_name = "level1"
    try:
        cid = js_data.client_id
    except:
        try:
            cid = js_data["client_id"]
        except:
            cid = None
    try:
        sid = js_data.session_id
    except:
        try:
            sid = js_data["session_id"]
        except:
            sid = None
    try:
        is_sync = js_data.is_synchronizer
    except:
        try:
            is_sync = js_data["is_synchronizer"]
        except:
            is_sync = False
    try:
        env_name = js_data.environment_name
    except:
        try:
            env_name = js_data["environment_name"]
        except:
            pass
    return cid, sid, is_sync, env_name

class FetchError(RuntimeError):
    pass

class FetchResponse:
    def __init__(self, js_response):
        self._js = js_response
        try:
            self.ok = bool(js_response.ok)
        except:
            self.ok = True
        try:
            self.status = int(js_response.status)
        except:
            self.status = 200
    async def json(self):
        js_data = await self._js.json()
        return js_data
    async def text(self):
        return await self._js.text()

async def fetch(url, method="GET", headers=None, body=None):
    opts = {"method": method, "mode": "cors"}
    if headers:
        opts["headers"] = headers
    if body is not None:
        opts["body"] = body
    js_resp = await window.fetch(url, opts)
    return FetchResponse(js_resp)

async def fetch_json(url):
    resp = await fetch(url)
    if not resp.ok:
        txt = await resp.text()
        raise FetchError(f"HTTP {resp.status} {txt[:200]}")
    js_data = await resp.json()
    return _js_to_py_simple(js_data)

async def fetch_text(url):
    resp = await fetch(url)
    if not resp.ok:
        raise FetchError(f"HTTP {resp.status}")
    return await resp.text()

_mod_ft = types.ModuleType('extensions.fetch')
_mod_ft.fetch = fetch
_mod_ft.fetch_json = fetch_json
_mod_ft.fetch_text = fetch_text
_mod_ft.FetchResponse = FetchResponse
_mod_ft.FetchError = FetchError
sys.modules['extensions.fetch'] = _mod_ft
try:
    _ext_pkg.fetch = _mod_ft
except:
    pass

BASE_URL_DEFAULT = "https://scs-207.onrender.com"

class MultiplayerClient:
    def __init__(self, base_url=BASE_URL_DEFAULT, environment="level1", environment_name=None, character_name="Player", **kw):
        self.base_url = base_url.rstrip("/")
        self.environment_name = environment_name or environment or "level1"
        self.character_name = kw.get("character_name", character_name) or "Player"
        self.client_id = None
        self.session_id = None
        self.is_synchronizer = False
        self._es = None
    async def join(self):
        base_url = self.base_url
        url = base_url + "/api/multiplayer/join"
        payload = {"environment_name": self.environment_name, "character_name": self.character_name}
        resp = await window.fetch(url, {"method": "POST", "headers": {"Content-Type": "application/json"}, "body": window.JSON.stringify(payload)})
        if not resp.ok:
            raise RuntimeError("join HTTP " + str(resp.status))
        js_data = await resp.json()
        cid, sid, is_sync, env_name = _parse_join_data(js_data)
        if not cid or not sid:
            raise RuntimeError("missing ids")
        self.client_id = str(cid)
        self.session_id = str(sid)
        self.is_synchronizer = bool(is_sync)
        try:
            stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
            es_obj = window.EventSource.new(stream_url)
            self._es = es_obj
            window._bgs_es = es_obj
        except Exception:
            try:
                es_obj = window.EventSource(stream_url)
                self._es = es_obj
                window._bgs_es = es_obj
            except Exception:
                pass
        return {"client_id": str(cid), "session_id": str(sid), "is_synchronizer": bool(is_sync), "environment_name": env_name}

_mod_mp = types.ModuleType('extensions.multiplayer')
_mod_mp.MultiplayerClient = MultiplayerClient
_mod_mp.BASE_URL_DEFAULT = BASE_URL_DEFAULT
sys.modules['extensions.multiplayer'] = _mod_mp
try:
    _ext_pkg.multiplayer = _mod_mp
except:
    pass

_signals_store = {}
_attached_es = None

if not hasattr(window, "_bgs_es"):
    window._bgs_es = None
if not hasattr(window, "_bgs_last_patch_ms"):
    window._bgs_last_patch_ms = 0
if not hasattr(window, "_bgs_signals_json"):
    window._bgs_signals_json = "{}"

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

_mod_ds = types.ModuleType('extensions.datastar')
_mod_ds.get_signal = get_signal
_mod_ds.is_connected = is_connected
_mod_ds.attach_to_eventsource = attach_to_eventsource
_mod_ds._on_datastar_patch = _on_datastar_patch
sys.modules['extensions.datastar'] = _mod_ds
try:
    _ext_pkg.datastar = _mod_ds
except:
    pass

try:
    window.console.log("[extensions.py] v3.0.25 FIX module callable + e-15 SAFE")
except:
    pass
