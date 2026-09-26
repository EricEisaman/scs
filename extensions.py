
import sys
import types
from browser import window, aio
import json as py_json

# Clear IDB caches that cause old shim to stick - do it here early
try:
    for _n in ["brython", "scs", "SCS", "scs-cache", "brython-cache", "__brython_transpile__"]:
        try:
            window.indexedDB.deleteDatabase(_n)
        except:
            pass
except:
    pass

try:
    import extensions as _ext_pkg
except:
    _ext_pkg = types.ModuleType('extensions')
    sys.modules['extensions'] = _ext_pkg

# fetch - must work for fetch_demo
class FetchResponse:
    def __init__(self, js_resp):
        self._js = js_resp
        self.ok = bool(js_resp.ok)
        self.status = int(js_resp.status)
        try:
            self.statusText = str(js_resp.statusText)
        except:
            self.statusText = ""
        self.headers = {}
    async def json(self):
        js_data = await self._js.json()
        try:
            keys = window.Object.keys(js_data)
            result = {}
            for i in range(len(keys)):
                k = keys[i]
                try:
                    result[k] = js_data[k]
                except:
                    continue
            return result
        except:
            try:
                return py_json.loads(window.JSON.stringify(js_data))
            except:
                return js_data
    async def text(self):
        return await self._js.text()

async def fetch(url, method="GET", headers=None, body=None, mode=None):
    opts = {"method": method}
    if headers:
        opts["headers"] = headers
    if body is not None:
        if isinstance(body, (dict, list)):
            opts["body"] = window.JSON.stringify(body)
        else:
            opts["body"] = body
    if mode:
        opts["mode"] = mode
    try:
        js_opts = window.JSON.parse(window.JSON.stringify(opts))
    except:
        js_opts = opts
    js_resp = await window.fetch(url, js_opts)
    return FetchResponse(js_resp)

async def fetch_json(url, **kw):
    resp = await fetch(url, **kw)
    if not resp.ok:
        raise RuntimeError("fetch_json HTTP " + str(resp.status))
    return await resp.json()

async def fetch_text(url, **kw):
    resp = await fetch(url, **kw)
    if not resp.ok:
        raise RuntimeError("fetch_text HTTP " + str(resp.status))
    return await resp.text()

class FetchError(RuntimeError):
    pass

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

# multiplayer - STRICT NO FALLBACK
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
    async def join(self, retries=3):
        base_url = self.base_url
        last_exc = None
        for attempt in range(retries):
            try:
                url = base_url + "/api/multiplayer/join"
                payload = {"environment_name": self.environment_name, "character_name": self.character_name}
                body = window.JSON.stringify(payload)
                js_opts = {"method": "POST", "headers": {"Content-Type": "application/json"}, "body": body}
                try:
                    opts = window.JSON.parse(window.JSON.stringify(js_opts))
                except:
                    opts = js_opts
                resp = await window.fetch(url, opts)
                if not resp.ok:
                    txt = ""
                    try:
                        txt = await resp.text()
                    except:
                        pass
                    raise RuntimeError("join HTTP " + str(resp.status))
                js_data = await resp.json()
                try:
                    data = {}
                    keys = window.Object.keys(js_data)
                    for i in range(len(keys)):
                        k = keys[i]
                        try:
                            data[k] = js_data[k]
                        except:
                            continue
                    if not data:
                        data = py_json.loads(window.JSON.stringify(js_data))
                except:
                    try:
                        data = py_json.loads(window.JSON.stringify(js_data))
                    except:
                        data = {}
                cid = data.get("client_id")
                sid = data.get("session_id")
                is_sync = data.get("is_synchronizer", False)
                if not cid or not sid:
                    raise RuntimeError("missing ids")
                self.client_id = cid
                self.session_id = sid
                self.is_synchronizer = bool(is_sync)
                try:
                    stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
                    es_obj = None
                    try:
                        es_obj = window.EventSource.new(stream_url)
                    except:
                        es_obj = window.EventSource(stream_url)
                    self._es = es_obj
                    try:
                        window._bgs_es = es_obj
                    except:
                        pass
                except:
                    pass
                return {"client_id": cid, "session_id": sid, "is_synchronizer": bool(is_sync), "environment_name": data.get("environment_name", self.environment_name)}
            except Exception as ex:
                last_exc = ex
                await aio.sleep(1.0 * (attempt + 1))
        raise last_exc or RuntimeError("join failed - NO FALLBACK")

_mod_mp = types.ModuleType('extensions.multiplayer')
_mod_mp.MultiplayerClient = MultiplayerClient
_mod_mp.BASE_URL_DEFAULT = BASE_URL_DEFAULT
sys.modules['extensions.multiplayer'] = _mod_mp
try:
    _ext_pkg.multiplayer = _mod_mp
except:
    pass

# datastar
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
    window.console.log("[extensions.py] loaded - NO FALLBACK MP fixed, fetch_demo safe v3.0.16")
except:
    pass
