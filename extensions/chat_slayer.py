"""
extensions/chat_slayer.py — per CLIENT_GUIDE.md + demo/ — NO EVAL
https://github.com/EricEisaman/chat-slayer/tree/main/demo
- X-Chat-Slayer-Client-Id on EVERY request
- Register: POST no auth -> 401 {session} -> POST dummy auth -> 200 verification
- Login: POST /_matrix/client/r0/login m.login.password -> 200
- 429 backoff with Retry-After
- Username+password first screen
- Uses window.fetch directly, window.Object.new() for state — no window.eval
"""
from browser import window, aio
import json as py_json
import time, random

DEFAULT_BASE_URL = "https://scs-207.onrender.com/chat-api"
DEFAULT_CLIENT_ID = "web-demo"

def _ensure_js_state():
    try:
        _ = window._chatSlayer
        if _._is_none: raise AttributeError
    except:
        try:
            o = window.Object.new()
            o.token = None; o.userId = None; o.deviceId = None
            o.roomId = None; o.messages = []; o.connected = False
            o.username = None; o.clientId = DEFAULT_CLIENT_ID
            o.lastResp = None; o.lastError = None
            window._chatSlayer = o
        except:
            window._chatSlayer = {"token":None,"userId":None,"connected":False}

_ensure_js_state()

class ChatSlayerClient:
    def __init__(self, base_url=None, client_id=None, username=None, password=None):
        raw = (base_url or DEFAULT_BASE_URL).rstrip("/")
        if "scs-207.onrender.com" in raw and "/chat-api" not in raw:
            raw += "/chat-api"
        self.base_url = raw
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self.username = username or f"Guest{random.randint(1000,9999)}"
        self.password = password or ""
        self.access_token = None
        self.user_id = None
        self.connected = False
        self.login_error = ""

    async def _fetch_with_backoff(self, url, opts, retries=3):
        attempt = 0
        while attempt <= retries:
            resp = await window.fetch(url, opts)
            if resp.status != 429:
                return resp
            ra = resp.headers.get("Retry-After") or "2"
            try: delay = int(ra)*1000
            except: delay = (2 ** attempt) * 1000
            await aio.sleep(delay/1000)
            attempt += 1
        return resp

    async def register_or_login(self, username=None, password=None):
        if username: self.username = username
        if password: self.password = password
        if len(self.password) < 8:
            self.login_error = "Password min 8 chars"; return
        base, cid, user, pwd = self.base_url, self.client_id, self.username, self.password
        headers = {"Content-Type":"application/json","X-Chat-Slayer-Client-Id":cid}

        # STEP 1: no auth -> 401 with session
        opts1 = {"method":"POST","headers":headers,"body":py_json.dumps({"username":user,"password":pwd})}
        res1 = await self._fetch_with_backoff(base+"/_matrix/client/r0/register?kind=user", opts1)
        t1 = await res1.text()
        try: d1 = py_json.loads(t1)
        except: d1 = {}

        if res1.status == 401 and d1.get("session"):
            # STEP 2: dummy auth -> 200 verification
            body2 = {"username":user,"password":pwd,"auth":{"type":"m.login.dummy","session":d1["session"]}}
            opts2 = {"method":"POST","headers":headers,"body":py_json.dumps(body2)}
            res2 = await self._fetch_with_backoff(base+"/_matrix/client/r0/register?kind=user", opts2)
            t2 = await res2.text()
            try: d2 = py_json.loads(t2)
            except: d2 = {}
            if res2.status == 200 and d2.get("access_token"):
                window._chatSlayer.token = d2["access_token"]
                window._chatSlayer.userId = d2["user_id"]
                window._chatSlayer.deviceId = d2.get("device_id")
                window._chatSlayer.username = user
                window._chatSlayer.connected = True
                window._chatSlayer.lastResp = {"status":200,"data":d2,"stage":"register_verified"}
                self.access_token = d2["access_token"]; self.user_id = d2["user_id"]; self.connected=True
                return d2

        if res1.status == 200 and d1.get("access_token"):
            window._chatSlayer.token = d1["access_token"]
            window._chatSlayer.userId = d1["user_id"]
            window._chatSlayer.username = user
            window._chatSlayer.connected = True
            window._chatSlayer.lastResp = {"status":200,"data":d1,"stage":"register_verified"}
            self.access_token = d1["access_token"]; self.connected=True
            return d1

        # LOGIN fallback
        bodyL = {"type":"m.login.password","identifier":{"type":"m.id.user","user":user},"password":pwd}
        optsL = {"method":"POST","headers":headers,"body":py_json.dumps(bodyL)}
        resL = await self._fetch_with_backoff(base+"/_matrix/client/r0/login", optsL)
        tL = await resL.text()
        try: dL = py_json.loads(tL)
        except: dL = {}
        if resL.status == 200 and dL.get("access_token"):
            window._chatSlayer.token = dL["access_token"]
            window._chatSlayer.userId = dL["user_id"]
            window._chatSlayer.username = user
            window._chatSlayer.connected = True
            window._chatSlayer.lastResp = {"status":200,"data":dL,"stage":"login_verified"}
            self.access_token = dL["access_token"]; self.user_id = dL["user_id"]; self.connected=True
        else:
            window._chatSlayer.lastResp = {"status":resL.status,"data":dL,"stage":"login_failed"}
            window._chatSlayer.connected = False

_global=None
def get_chat_client(base_url=None, client_id=None, username=None, password=None):
    global _global
    if _global is None:
        _global = ChatSlayerClient(base_url, client_id, username, password)
    else:
        if username: _global.username = username
        if password: _global.password = password
    return _global