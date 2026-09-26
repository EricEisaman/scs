# extensions.py - SCS Extensions System - v3.0.17 STABLE
# fetch + multiplayer ultra minimal (fix resolve_local), datastar proper spec
# fetch_demo safe, MUST USE MP EXTENSION, apps frozen

import sys
import types
from browser import window, aio
import json as py_json

try:
    import extensions as _ext_pkg
except:
    _ext_pkg = types.ModuleType('extensions')
    sys.modules['extensions'] = _ext_pkg

# --- fetch - ULTRA MINIMAL - fetch_demo safe ---
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
        return js_data
    async def text(self):
        return await self._js.text()

async def fetch(url, method="GET", headers=None, body=None, mode=None):
    opts = {"method": method}
    if headers:
        opts["headers"] = headers
    if body is not None:
        opts["body"] = body
    if mode:
        opts["mode"] = mode
    js_resp = await window.fetch(url, opts)
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

# --- multiplayer - ULTRA MINIMAL - COMMITTED API ---
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
        if not cid or not sid:
            raise RuntimeError("missing ids")
        self.client_id = str(cid)
        self.session_id = str(sid)
        self.is_synchronizer = bool(is_sync)
        try:
            stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
            es_obj = window.EventSource.new(stream_url)
            self._es = es_obj
            try:
                window._bgs_es = es_obj
            except:
                pass
        except:
            try:
                stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
                es_obj = window.EventSource(stream_url)
                self._es = es_obj
                try:
                    window._bgs_es = es_obj
                except:
                    pass
            except:
                pass
        env_name = self.environment_name
        try:
            env_name = js_data.environment_name
        except:
            try:
                env_name = js_data["environment_name"]
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

# --- datastar - PROPER SPEC - line-prefix parsing, Python-native, merge, null deletion, onlyIfMissing ---
if not hasattr(window, "_bgs_signals"):
    window._bgs_signals = {}
if not hasattr(window, "_bgs_es"):
    window._bgs_es = None
if not hasattr(window, "_bgs_last_patch_ms"):
    window._bgs_last_patch_ms = 0

_attached_es_ids = set()

def _extract_signals_json(raw):
    if not isinstance(raw, str):
        return None
    for line in raw.splitlines():
        if line.startswith("signals "):
            return line[len("signals "):]
    return None

def _parse_datastar_patch(raw):
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
    if only_if_missing:
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
    return window._bgs_signals.get(name, default)

def is_connected(max_silence_ms=10000):
    try:
        es = window._bgs_es
        if es is None or es.readyState != 1:
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
    if es is None:
        raise ValueError("attach_to_eventsource requires an EventSource")
    try:
        if getattr(es, "_bgs_listener_attached", False):
            window._bgs_es = es
            return
    except:
        pass
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
    window.console.log("[extensions.py] v3.0.17 PROPER DATASTAR SPEC + ULTRA MINIMAL MP/FETCH - apps frozen")
except:
    pass
