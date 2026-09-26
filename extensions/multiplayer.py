from browser import window, aio
import json as py_json

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
                    raise RuntimeError("join HTTP " + str(resp.status) + ": " + txt[:500])
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
