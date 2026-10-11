"""
extensions/chat_slayer.py — per CLIENT_GUIDE.md + demo/ — NO EVAL
https://github.com/EricEisaman/chat-slayer/tree/main/demo
- X-Chat-Slayer-Client-Id on EVERY request = web-demo (must be in ALLOWED_CLIENTS)
- Unique browser ID stored separately as deviceId, NOT as clientId
- Register: POST no auth -> 401 {session} -> POST dummy auth -> 200 verification
- Login: POST /_matrix/client/r0/login m.login.password -> 200
- REST via scs-207 proxy on github.io to avoid CORS preflight, SSE direct to chat-slayer
- 429 backoff with Retry-After + 502/503 wake handling
- Username+password first screen
- Uses window.fetch directly, window.Object.new() for state — no window.eval
"""
from browser import window, aio
import json as py_json
import time, random

DEFAULT_PROXY_BASE = "https://scs-207.onrender.com/chat-api"
DEFAULT_DIRECT_BASE = "https://chat-slayer.onrender.com"
DEFAULT_CLIENT_ID = "web-demo"  # MUST be in ALLOWED_CLIENTS

def _get_unique_device_id():
    try:
        k = "tetr_device_id_v2"
        v = window.localStorage.getItem(k)
        if v:
            return v
        new_id = f"tetr_{int(time.time()*1000)}_{random.randint(1000,9999)}"
        window.localStorage.setItem(k, new_id)
        return new_id
    except:
        return f"tetr_{int(time.time()*1000)}_{random.randint(1000,9999)}"

def _ensure_js_state():
    try:
        _ = window._chatSlayer
        if _._is_none: raise AttributeError
        if not hasattr(_, "status"):
            _.status = "idle"
    except:
        try:
            o = window.Object.new()
            o.token = None; o.userId = None; o.deviceId = None
            o.roomId = None; o.messages = []; o.connected = False
            o.username = None; o.clientId = DEFAULT_CLIENT_ID
            o.deviceId = _get_unique_device_id()
            o.lastResp = None; o.lastError = None
            o.status = "idle"
            window._chatSlayer = o
        except:
            window._chatSlayer = {"token":None,"userId":None,"connected":False,"status":"idle","clientId":DEFAULT_CLIENT_ID,"deviceId":_get_unique_device_id()}

_ensure_js_state()

def _is_github_io():
    try:
        return "github.io" in window.location.hostname
    except:
        return False

def _get_rest_base(base_url=None):
    """REST (register/login) via scs-207 proxy on github.io to avoid CORS preflight failures"""
    raw = (base_url or DEFAULT_PROXY_BASE).rstrip("/")
    if "scs-207.onrender.com" in raw and "/chat-api" not in raw:
        raw += "/chat-api"
    if _is_github_io():
        return DEFAULT_PROXY_BASE
    # same-origin on Render
    try:
        if "scs-207" in window.location.hostname or "localhost" in window.location.hostname:
            return "/chat-api"
    except:
        pass
    return raw

def _get_stream_base():
    """SSE stream always direct on github.io - edge proxy breaks chunked SSE with ERR_HTTP2_PROTOCOL_ERROR"""
    return DEFAULT_DIRECT_BASE

class ChatSlayerClient:
    def __init__(self, base_url=None, client_id=None, username=None, password=None, status_cb=None):
        # Always use web-demo for gate, unique ID is deviceId
        self.base_url = _get_rest_base(base_url)
        self.stream_base = _get_stream_base()
        self.client_id = DEFAULT_CLIENT_ID  # FIX: must be in ALLOWED_CLIENTS
        self.device_id = _get_unique_device_id()
        self.username = username or f"Guest{random.randint(1000,9999)}"
        self.password = password or ""
        self.access_token = None
        self.user_id = None
        self.connected = False
        self.login_error = ""
        self._status_cb = status_cb

    def _set_status(self, msg):
        try:
            window._chatSlayer.status = msg
        except:
            pass
        if self._status_cb:
            try: self._status_cb(msg)
            except: pass

    def _parse_retry_after(self, resp):
        try:
            ra = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
            if ra:
                return int(str(ra).split()[0])
        except:
            pass
        return None

    async def _fetch_with_backoff(self, url, opts, retries=8, wake_mode=False):
        base = 2.0
        for attempt in range(retries + 1):
            try:
                resp = await window.fetch(url, opts)
                if resp.status not in (429, 502, 503, 504):
                    return resp
                ra = self._parse_retry_after(resp)
                if ra is not None:
                    wait = float(ra)
                else:
                    wait = (5 + attempt*2) if wake_mode or resp.status!= 429 else (base * (2 ** attempt))
                wait = min(wait, 20) + random.uniform(0, 1.5)
                if wake_mode or resp.status in (502,503,504):
                    self._set_status(f"Waking chat server... retry in {int(wait)}s ({attempt+1}/{retries+1})")
                else:
                    self._set_status(f"Rate limited, waiting {int(wait)}s...")
                await aio.sleep(wait)
                continue
            except Exception as e:
                wait = min(base * (2 ** attempt) + random.uniform(0,1), 20)
                self._set_status(f"Waking chat server... {e} - retry in {int(wait)}s ({attempt+1}/{retries+1})")
                await aio.sleep(wait)
        return await window.fetch(url, opts)

    async def wait_for_wake(self, max_attempts=12):
        self._set_status("Waking chat server (free tier, ~40s)...")
        headers = {"X-Chat-Slayer-Client-Id": self.client_id}
        for i in range(max_attempts):
            try:
                for path in ["/health", "/", "/_matrix/client/versions"]:
                    url = f"{self.base_url}{path}"
                    resp = await window.fetch(url, {"method":"GET","headers":headers})
                    if resp.status in (200, 401, 404):
                        self._set_status("Chat server awake")
                        return True
                    if resp.status in (502,503,504,429):
                        ra = self._parse_retry_after(resp)
                        wait = ra if ra is not None else min(4 + i*2, 15)
                        self._set_status(f"Waking chat server... {int(wait)}s (boot {i+1}/{max_attempts})")
                        await aio.sleep(wait + random.uniform(0,1))
                        break
                else:
                    await aio.sleep(2 + random.uniform(0,1))
            except Exception as e:
                await aio.sleep(3 + random.uniform(0,1))
        self._set_status("Chat offline - playing solo")
        return False

    async def register_or_login(self, username=None, password=None):
        if username: self.username = username
        if password: self.password = password
        if len(self.password) < 8:
            self.login_error = "Password min 8 chars"; return
        await self.wait_for_wake()

        base, cid, user, pwd = self.base_url, self.client_id, self.username, self.password
        headers = {"Content-Type":"application/json","X-Chat-Slayer-Client-Id":cid}
        self._set_status(f"Registering {user}...")

        opts1 = {"method":"POST","headers":headers,"body":py_json.dumps({"username":user,"password":pwd})}
        res1 = await self._fetch_with_backoff(base+"/_matrix/client/r0/register?kind=user", opts1, retries=5, wake_mode=True)
        t1 = await res1.text()
        try: d1 = py_json.loads(t1)
        except: d1 = {}

        if res1.status == 401 and d1.get("session"):
            body2 = {"username":user,"password":pwd,"auth":{"type":"m.login.dummy","session":d1["session"]}}
            opts2 = {"method":"POST","headers":headers,"body":py_json.dumps(body2)}
            res2 = await self._fetch_with_backoff(base+"/_matrix/client/r0/register?kind=user", opts2, retries=5, wake_mode=True)
            t2 = await res2.text()
            try: d2 = py_json.loads(t2)
            except: d2 = {}
            if res2.status == 200 and d2.get("access_token"):
                window._chatSlayer.token = d2["access_token"]
                window._chatSlayer.userId = d2["user_id"]
                window._chatSlayer.deviceId = d2.get("device_id") or self.device_id
                window._chatSlayer.username = user
                window._chatSlayer.connected = True
                window._chatSlayer.lastResp = {"status":200,"data":d2,"stage":"register_verified"}
                self.access_token = d2["access_token"]; self.user_id = d2["user_id"]; self.connected=True
                self._set_status(f"Connected as {user}")
                return d2

        if res1.status == 200 and d1.get("access_token"):
            window._chatSlayer.token = d1["access_token"]
            window._chatSlayer.userId = d1["user_id"]
            window._chatSlayer.username = user
            window._chatSlayer.connected = True
            window._chatSlayer.lastResp = {"status":200,"data":d1,"stage":"register_verified"}
            self.access_token = d1["access_token"]; self.connected=True
            self._set_status(f"Connected as {user}")
            return d1

        self._set_status(f"Logging in {user}...")
        bodyL = {"type":"m.login.password","identifier":{"type":"m.id.user","user":user},"password":pwd}
        optsL = {"method":"POST","headers":headers,"body":py_json.dumps(bodyL)}
        resL = await self._fetch_with_backoff(base+"/_matrix/client/r0/login", optsL, retries=5, wake_mode=True)
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
            self._set_status(f"Connected as {user}")
        else:
            window._chatSlayer.lastResp = {"status":resL.status,"data":dL,"stage":"login_failed"}
            window._chatSlayer.connected = False
            self._set_status(f"Login failed: {dL.get('error','unknown')} - {dL.get('errcode','')}")

    def get_stream_url(self):
        # Direct for SSE on github.io
        return f"{self.stream_base}/demo/stream"

_global=None
def get_chat_client(base_url=None, client_id=None, username=None, password=None, status_cb=None):
    global _global
    if _global is None:
        _global = ChatSlayerClient(base_url, client_id, username, password, status_cb=status_cb)
    else:
        if username: _global.username = username
        if password: _global.password = password
        if status_cb: _global._status_cb = status_cb
    return _global
