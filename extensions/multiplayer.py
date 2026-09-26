from browser import window, aio
import json as py_json

BASE_URL_DEFAULT = "https://scs-207.onrender.com"

def _parse_join_data(js_data):
    cid = None
    sid = None
    is_sync = False
    env_name = "level1"
    if isinstance(js_data, dict):
        cid = js_data.get("client_id")
        sid = js_data.get("session_id")
        is_sync = js_data.get("is_synchronizer", False)
        env_name = js_data.get("environment_name", "level1")
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
        try:
            resp = await aio.fetch(url, method="POST", headers={"Content-Type": "application/json"}, data=py_json.dumps(payload))
        except Exception as e:
            raise RuntimeError(f"join aio.fetch failed {e}")
        try:
            ok = bool(resp.ok)
        except:
            try:
                ok = 200 <= int(resp.status) < 300
            except:
                ok = True
        if not ok:
            try:
                status = resp.status
            except:
                status = "unknown"
            raise RuntimeError(f"join HTTP {status}")
        try:
            js_data = await resp.json()
        except:
            txt = await resp.text()
            js_data = py_json.loads(txt)
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
            resp = await aio.fetch(url, method="PATCH", headers={"Content-Type": "application/json", "X-Client-ID": str(client_id)}, data=body_str)
            try:
                return bool(resp.ok)
            except:
                try:
                    return 200 <= int(resp.status) < 300
                except:
                    return True
        except Exception:
            return False
