# extensions.py - v3.0.32 FIX module not callable - use aio.get/post, NO w_fetch, NO aio.fetch
import sys, types
from browser import window

try:
    import extensions as _ext_pkg
except:
    _ext_pkg = types.ModuleType('extensions')
    sys.modules['extensions'] = _ext_pkg

from browser import aio
import json as py_json

class FetchError(RuntimeError):
    pass

class FetchResponse:
    def __init__(self, aio_response):
        self._resp = aio_response
        try:
            self.status = int(aio_response.status)
        except:
            self.status = 200
        try:
            self.ok = 200 <= self.status < 300
        except:
            self.ok = True
        try:
            self.statusText = ""
        except:
            self.statusText = ""
        self._data = getattr(aio_response, 'data', None)
        self._text = getattr(aio_response, 'text', None)

    async def json(self):
        d = self._data
        if d is None:
            d = self._text
        if isinstance(d, dict):
            return d
        if isinstance(d, str):
            try:
                return py_json.loads(d)
            except:
                return d
        try:
            return await self._resp.json()
        except:
            return d

    async def text(self):
        d = self._data
        if d is None:
            d = self._text
        if isinstance(d, str):
            return d
        if isinstance(d, dict):
            try:
                return py_json.dumps(d)
            except:
                return str(d)
        try:
            return await self._resp.text()
        except:
            return str(d) if d is not None else ""

async def fetch(url, method="GET", headers=None, body=None, data=None, mode="cors", credentials=None, cache=None):
    b = body if body is not None else data
    if isinstance(b, dict):
        b = py_json.dumps(b)
    opts_headers = headers or {}
    try:
        m = method.upper() if method else "GET"
        if m == "GET":
            resp = await aio.get(url, headers=opts_headers)
        elif m == "POST":
            resp = await aio.post(url, headers=opts_headers, data=b)
        elif m == "PATCH":
            if hasattr(aio, 'ajax'):
                resp = await aio.ajax("PATCH", url, headers=opts_headers, data=b)
            else:
                resp = await aio.post(url, headers=opts_headers, data=b)
        else:
            if hasattr(aio, 'ajax'):
                resp = await aio.ajax(m, url, headers=opts_headers, data=b)
            else:
                resp = await aio.get(url, headers=opts_headers)
        return FetchResponse(resp)
    except Exception as e:
        raise FetchError(f"aio {m} failed for {url}: {e}")

async def fetch_json(url, method="GET", headers=None, body=None, mode="cors"):
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
    if not resp.ok:
        try:
            txt = await resp.text()
        except:
            txt = ""
        raise FetchError(f"HTTP {resp.status} {txt[:200]}")
    return await resp.json()

async def fetch_text(url, method="GET", headers=None, body=None, mode="cors"):
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
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

# Multiplayer
from browser import window, aio
import json as py_json

BASE_URL_DEFAULT = "https://scs-207.onrender.com"

def _parse_join_data(js_data):
    if isinstance(js_data, dict):
        cid = js_data.get("client_id")
        sid = js_data.get("session_id")
        is_sync = js_data.get("is_synchronizer", False)
        env_name = js_data.get("environment_name", "level1")
        return cid, sid, is_sync, env_name
    return None, None, False, "level1"

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
        data_str = py_json.dumps(payload)
        try:
            # Use aio.post - NOT aio.fetch (module not callable)
            resp = await aio.post(url, headers={"Content-Type": "application/json"}, data=data_str)
        except Exception as e:
            raise RuntimeError(f"join aio.post failed {e}")
        try:
            status = int(resp.status)
            ok = 200 <= status < 300
        except:
            try:
                ok = bool(resp.ok)
            except:
                ok = True
            status = getattr(resp, 'status', 200)
        if not ok:
            raise RuntimeError(f"join HTTP {status}")
        try:
            # aio response: data may be dict or string
            raw = getattr(resp, 'data', None)
            if raw is None:
                raw = getattr(resp, 'text', None)
            if isinstance(raw, dict):
                js_data = raw
            elif isinstance(raw, str):
                js_data = py_json.loads(raw)
            else:
                # try json method
                try:
                    js_data = await resp.json()
                except:
                    txt = await resp.text() if hasattr(resp, 'text') else str(raw)
                    js_data = py_json.loads(txt)
        except Exception as e:
            try:
                txt = await resp.text()
            except:
                txt = str(getattr(resp, 'data', ''))
            try:
                js_data = py_json.loads(txt)
            except:
                raise RuntimeError(f"join parse failed {e} data={txt[:200]}")
        cid, sid, is_sync, env_name = _parse_join_data(js_data)
        if not cid or not sid:
            raise RuntimeError(f"missing ids in join response: {js_data}")
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

    async def send_character_state(self, client_id, state_payload):
        base_url = self.base_url
        url = base_url + "/api/multiplayer/character-state"
        try:
            body_str = py_json.dumps(state_payload)
        except:
            body_str = str(state_payload)
        try:
            # PATCH via aio.ajax if available, else POST fallback
            if hasattr(aio, 'ajax'):
                resp = await aio.ajax("PATCH", url, headers={"Content-Type": "application/json", "X-Client-ID": str(client_id)}, data=body_str)
            else:
                resp = await aio.post(url, headers={"Content-Type": "application/json", "X-Client-ID": str(client_id), "X-HTTP-Method-Override": "PATCH"}, data=body_str)
            try:
                return 200 <= int(resp.status) < 300
            except:
                try:
                    return bool(resp.ok)
                except:
                    return True
        except Exception:
            return False


BASE_URL_DEFAULT = "https://scs-207.onrender.com"

_mod_mp = types.ModuleType('extensions.multiplayer')
_mod_mp.MultiplayerClient = MultiplayerClient
_mod_mp.BASE_URL_DEFAULT = BASE_URL_DEFAULT
sys.modules['extensions.multiplayer'] = _mod_mp
try:
    _ext_pkg.multiplayer = _mod_mp
except:
    pass

# Datastar
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
    if isinstance(js_obj, str):
        return js_obj
    if isinstance(js_obj, bool):
        return bool(js_obj)
    if isinstance(js_obj, int):
        return int(js_obj)
    if isinstance(js_obj, float):
        return float(js_obj)
    if isinstance(js_obj, dict):
        return {str(k): _js_to_py_safe(v) for k, v in js_obj.items()}
    if isinstance(js_obj, list):
        return [_js_to_py_safe(x) for x in js_obj]
    try:
        if window.Array.isArray(js_obj):
            out = []
            ln = int(js_obj.length)
            for i in range(ln):
                out.append(_js_to_py_safe(js_obj[i]))
            return out
    except:
        pass
    try:
        keys = window.Object.keys(js_obj)
        kl = int(keys.length)
        out = {}
        for idx in range(kl):
            k = keys[idx]
            out[str(k)] = _js_to_py_safe(js_obj[k])
        return out
    except:
        pass
    try:
        s = str(js_obj)
        try:
            return float(s)
        except:
            return s
    except:
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
