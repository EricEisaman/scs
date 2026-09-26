
from browser import window, aio
import json as py_json

BASE_URL_DEFAULT = "https://scs-207.onrender.com"

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
        # Use window.fetch directly - as you demanded
        try:
            resp = await window.fetch(url, {"method": "POST", "headers": {"Content-Type": "application/json"}, "body": window.JSON.stringify(payload)})
        except Exception as e:
            try:
                window.console.warn("[MultiplayerClient] window.fetch join failed, trying aio", str(e))
                resp = await aio.fetch(url, {"method": "POST", "headers": {"Content-Type": "application/json"}, "body": py_json.dumps(payload)})
            except Exception as e2:
                raise RuntimeError(f"join fetch failed {e} / {e2}")
        if not resp.ok:
            raise RuntimeError("join HTTP " + str(resp.status))
        js_data = await resp.json()
        cid, sid, is_sync, env_name = _parse_join_data(js_data)
        if not cid or not sid:
            raise RuntimeError("missing ids")
        self.client_id = str(cid)
        self.session_id = str(sid)
        self.is_synchronizer = bool(is_sync)
        # Attach EventSource for datastar
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
        # Helper for 60Hz updates - accommodates full multiplayer system
        # state_payload is dict with updates list
        base_url = self.base_url
        url = base_url + "/api/multiplayer/character-state"
        try:
            body_str = window.JSON.stringify(state_payload)
        except:
            body_str = py_json.dumps(state_payload)
        opts = {"method": "PATCH", "headers": {"Content-Type": "application/json", "X-Client-ID": str(client_id)}, "body": body_str}
        try:
            js_opts = window.JSON.parse(window.JSON.stringify(opts))
        except:
            js_opts = opts
        try:
            resp = await window.fetch(url, js_opts)
            return resp.ok
        except Exception as e:
            try:
                window.console.error("[MultiplayerClient] send_character_state failed", str(e))
            except:
                pass
            return False
