# extensions.py - v3.0.18 FINAL - NO $B.$is - per sister expert
import sys, types
from browser import window, aio
import json as py_json

try:
    import extensions as _ext_pkg
except:
    _ext_pkg = types.ModuleType('extensions')
    sys.modules['extensions'] = _ext_pkg

# --- fetch ---
class FetchError(RuntimeError):
    pass

class FetchResponse:
    def __init__(self, js_response):
        self._js = js_response
        self.ok = bool(js_response.ok)
        self.status = int(js_response.status)
        try:
            self.statusText = str(js_response.statusText)
        except:
            self.statusText = ""
    async def json(self):
        js_value = await self._js.json()
        json_text = window.JSON.stringify(js_value)
        try:
            return py_json.loads(json_text)
        except Exception as exc:
            try:
                window.console.error("[fetch] JSON conversion failed", exc, json_text[:500])
            except:
                pass
            raise
    async def text(self):
        return await self._js.text()

async def fetch(url, method="GET", headers=None, body=None):
    options = {"method": method}
    if headers != None:
        options["headers"] = headers
    if body != None:
        options["body"] = body
    js_response = await window.fetch(url, options)
    return FetchResponse(js_response)

async def fetch_json(url):
    response = await fetch(url)
    if not response.ok:
        raise FetchError("fetch_json HTTP " + str(response.status) + " " + response.statusText)
    return await response.json()

async def fetch_text(url):
    response = await fetch(url)
    if not response.ok:
        raise FetchError("fetch_text HTTP " + str(response.status) + " " + response.statusText)
    return await response.text()

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

# --- multiplayer ---
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
        resp = await window.fetch(url, {
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": window.JSON.stringify(payload)
        })
        if not resp.ok:
            raise RuntimeError("join HTTP " + str(resp.status))
        js_data = await resp.json()
        try:
            data = py_json.loads(window.JSON.stringify(js_data))
        except:
            data = {}
        cid = data.get("client_id")
        sid = data.get("session_id")
        is_sync = bool(data.get("is_synchronizer", False))
        env_name = data.get("environment_name", self.environment_name)
        if not cid or not sid:
            raise RuntimeError("missing ids")
        self.client_id = str(cid)
        self.session_id = str(sid)
        self.is_synchronizer = is_sync
        try:
            stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
            es_obj = window.EventSource.new(stream_url)
            self._es = es_obj
            window._bgs_es = es_obj
        except:
            try:
                stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
                es_obj = window.EventSource(stream_url)
                self._es = es_obj
                window._bgs_es = es_obj
            except:
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

# --- datastar ---
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
        window._bgs_signals_json = py_json.dumps(_signals_store)
    except:
        window._bgs_signals_json = "{}"
    try:
        window._bgs_signals_debug = window.JSON.parse(window._bgs_signals_json)
    except:
        pass

def _parse_datastar_patch(raw):
    if raw == None:
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
        if value == None:
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
    if signals_json == None:
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
        return
    if only_if_missing:
        filtered = {k: v for k, v in patch.items() if v != None}
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
    window.console.log("[extensions.py] v3.0.18 FINAL - NO $B.$is - sister expert - apps frozen")
except:
    pass
