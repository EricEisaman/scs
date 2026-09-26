from browser import window
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
            window._bgs_es = es_obj
        except:
            try:
                stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
                es_obj = window.EventSource(stream_url)
                self._es = es_obj
                window._bgs_es = es_obj
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
