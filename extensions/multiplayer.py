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
