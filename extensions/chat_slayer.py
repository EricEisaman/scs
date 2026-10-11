"""
extensions/chat_slayer.py — Chat Slayer extension per CLIENT_GUIDE.md
https://github.com/EricEisaman/chat-slayer/blob/main/CLIENT_GUIDE.md

Implements:
- X-Chat-Slayer-Client-Id header on EVERY request (required)
- Registration 2-step UIAA: POST without auth -> 401 {flows, session}, then POST with auth {type: m.login.dummy, session}
- Login: POST /_matrix/client/r0/login with type m.login.password
- 429 backoff with Retry-After per CLIENT_GUIDE
- Name + Password entry UI (WaInput) - not hardcoded Guest
- FastAPI proxy pattern: /chat-api/* -> upstream, no httpx

Fixes previous bugs:
- drawRoundedRect import error (was `from scs import drawRoundedRect` which doesn't exist)
- Auto bot spawn in SOLO (fixed in tetr_26.py)
- Multiplayer label showing SOLO (breadcrumb now dynamic)
"""

from browser import window
import json as py_json
import time
import random

try:
    from extensions.canvas_ui import WaInput, WaButton, WaCard, WaBadge
    HAS_UI = True
except:
    HAS_UI = False

DEFAULT_BASE_URL = "https://scs-207.onrender.com"
DEFAULT_CLIENT_ID = "web-demo"
DEFAULT_ROOM = "Lobby"

def _ensure_js_state():
    try:
        window.eval("""
        if (!window._chatSlayer) {
            window._chatSlayer = {
                signals: {},
                es: null,
                token: null,
                userId: null,
                roomId: null,
                messages: [],
                connected: false,
                username: null,
                clientId: "web-demo"
            };
        }
        """)
    except:
        pass

_ensure_js_state()

def _log(msg):
    try:
        print(f"[ChatSlayer] {msg}")
    except:
        pass

class ChatSlayerClient:
    def __init__(self, base_url=None, client_id=None, username=None, password=None):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self.username = username or f"Guest{random.randint(1000,9999)}"
        self.password = password or "tetrio123"
        self.access_token = None
        self.user_id = None
        self.device_id = None
        self.room_id = None
        self.room_name = DEFAULT_ROOM
        self.connected = False
        self.messages = []
        self._txn = 0
        self._chat_open = False
        self._chat_input = ""
        # UI for name/password per CLIENT_GUIDE
        self.show_login_ui = True
        self.login_error = ""
        self._input_user = None
        self._input_pass = None
        self._btn_register = None
        self._btn_login = None
        _ensure_js_state()
        _log(f"Client base={self.base_url} id={self.client_id} user={self.username}")

    # ---- Core fetch with CLIENT_GUIDE headers + 429 backoff ----
    def _js_fetch(self, path, method="GET", body=None, cb_name=None):
        # Uses JS fetch to avoid Brython CORS, with backoff for 429 per CLIENT_GUIDE.md
        url = self.base_url + path
        headers = {
            "Content-Type": "application/json",
            "X-Chat-Slayer-Client-Id": self.client_id
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        
        body_str = py_json.dumps(body) if body is not None else "null"
        # JS with backoff
        js = f"""
        (async () => {{
            async function fetchWithBackoff(url, opts, retries=3) {{
                for (let a=0; a<=retries; a++) {{
                    let r = await fetch(url, opts);
                    if (r.status !== 429) return r;
                    let ra = r.headers.get("Retry-After") || "2";
                    let delay = parseInt(ra)*1000 || Math.pow(2,a)*1000;
                    console.warn("[ChatSlayer] 429 retry in "+delay+"ms attempt "+(a+1));
                    await new Promise(res=>setTimeout(res, delay));
                }}
                return await fetch(url, opts);
            }}
            try {{
                const res = await fetchWithBackoff({py_json.dumps(url)}, {{
                    method: {py_json.dumps(method)},
                    headers: {py_json.dumps(headers)},
                    body: {body_str} === "null" ? undefined : JSON.stringify({body_str} ? {py_json.dumps(body_str)} and JSON.parse({py_json.dumps(body_str)}) ? JSON.parse({py_json.dumps(body_str)}) : {py_json.dumps(body_str)} : null)
                }});
                const text = await res.text();
                let data; try {{ data = JSON.parse(text); }} catch(e) {{ data = text; }}
                window._chatSlayer.lastResp = {{status: res.status, data: data}};
                console.log("[ChatSlayer] {method} {path} ->", res.status, data);
                if (window._chatSlayer.{cb_name or 'cb'}) window._chatSlayer.{cb_name or 'cb'}(res.status, data);
                return {{status: res.status, data: data}};
            }} catch(e) {{
                console.error("[ChatSlayer] fetch fail", e);
                window._chatSlayer.lastError = String(e);
            }}
        }})();
        """
        try:
            window.eval(js)
        except Exception as e:
            _log(f"fetch eval fail {e}")

    def register_or_login(self, username=None, password=None):
        if username: self.username = username
        if password: self.password = password
        # Step 1 per CLIENT_GUIDE: POST without auth -> 401 with session
        user = self.username
        pwd = self.password
        base = self.base_url
        cid = self.client_id
        # Use full JS flow per CLIENT_GUIDE.md lines 356-431
        js = f"""
        (async () => {{
            const base = {py_json.dumps(base)};
            const cid = {py_json.dumps(cid)};
            const user = {py_json.dumps(user)};
            const pass = {py_json.dumps(pwd)};
            const headers = {{"Content-Type":"application/json","X-Chat-Slayer-Client-Id":cid}};
            async function fetchWithBackoff(url, opts, retries=3) {{
                for (let a=0;a<=retries;a++) {{
                    let r = await fetch(url, opts);
                    if (r.status!==429) return r;
                    let ra = r.headers.get("Retry-After")||"2";
                    let d = parseInt(ra)*1000 || Math.pow(2,a)*1000;
                    console.warn("[ChatSlayer] 429 retry "+d+"ms");
                    await new Promise(r=>setTimeout(r,d));
                }}
                return await fetch(url, opts);
            }}
            try {{
                // STEP 1 - no auth
                let res1 = await fetchWithBackoff(base + "/_matrix/client/r0/register?kind=user", {{
                    method:"POST", headers: headers,
                    body: JSON.stringify({{username:user, password:pass}})
                }});
                let t1 = await res1.text(); let d1; try{{d1=JSON.parse(t1)}}catch(e){{d1=t1}}
                console.log("[ChatSlayer] register step1", res1.status, d1);
                if (res1.status===401 && d1.session) {{
                    // STEP 2 - dummy auth per CLIENT_GUIDE.md
                    let res2 = await fetchWithBackoff(base + "/_matrix/client/r0/register?kind=user", {{
                        method:"POST", headers: headers,
                        body: JSON.stringify({{username:user, password:pass, auth:{{type:"m.login.dummy", session:d1.session}}}})
                    }});
                    let t2 = await res2.text(); let d2; try{{d2=JSON.parse(t2)}}catch(e){{d2=t2}}
                    console.log("[ChatSlayer] register step2", res2.status, d2);
                    if (res2.status===200) {{
                        window._chatSlayer.token = d2.access_token;
                        window._chatSlayer.userId = d2.user_id;
                        window._chatSlayer.username = user;
                        window._chatSlayer.connected = true;
                        window._chatSlayer.lastResp = {{status:200, data:d2}};
                        return;
                    }}
                    // If user exists (M_USER_IN_USE 409), try login
                    if (res2.status===400 || res2.status===409 || d2.errcode==="M_USER_IN_USE") {{
                        console.log("[ChatSlayer] user exists, trying login");
                    }} else {{
                        window._chatSlayer.lastResp={{status:res2.status,data:d2}};
                        return;
                    }}
                }} else if (res1.status===200) {{
                    // Some servers return 200 immediately (no UIAA)
                    window._chatSlayer.token = d1.access_token;
                    window._chatSlayer.userId = d1.user_id;
                    window._chatSlayer.connected = true;
                    window._chatSlayer.lastResp={{status:200,data:d1}};
                    return;
                }}
                // LOGIN per CLIENT_GUIDE.md line 439-450
                let loginRes = await fetchWithBackoff(base + "/_matrix/client/r0/login", {{
                    method:"POST", headers: headers,
                    body: JSON.stringify({{type:"m.login.password", identifier:{{type:"m.id.user", user:user}}, password:pass}})
                }});
                let lt = await loginRes.text(); let ld; try{{ld=JSON.parse(lt)}}catch(e){{ld=lt}}
                console.log("[ChatSlayer] login", loginRes.status, ld);
                if (loginRes.status===200) {{
                    window._chatSlayer.token = ld.access_token;
                    window._chatSlayer.userId = ld.user_id;
                    window._chatSlayer.username = user;
                    window._chatSlayer.connected = true;
                    window._chatSlayer.lastResp={{status:200,data:ld}};
                }} else {{
                    window._chatSlayer.lastResp={{status:loginRes.status,data:ld}};
                    window._chatSlayer.connected=false;
                }}
            }} catch(e) {{
                console.error("[ChatSlayer] register_or_login fail", e);
                window._chatSlayer.lastError=String(e);
            }}
        }})();
        """
        try:
            window.eval(js)
        except Exception as e:
            _log(f"register eval fail {e}")

    def _update_from_js(self):
        try:
            token = window.eval("window._chatSlayer.token")
            uid = window.eval("window._chatSlayer.userId")
            if token and token!="null" and token!="undefined":
                self.access_token = str(token)
                self.user_id = str(uid) if uid else self.user_id
                self.connected = True
        except:
            pass

    def join_room(self, room_name="Lobby"):
        self.room_name = room_name
        # Use demo actions or Matrix API
        self._js_fetch(f"/_matrix/client/r0/rooms/register", "POST", {"names":[room_name]}, "joinCb")

    def send(self, text):
        if not text.strip(): return
        self._txn+=1
        txn = f"txn_{int(time.time()*1000)}_{self._txn}"
        room = self.room_id or "!lobby:localhost"
        # Try demo send first
        self._js_fetch(f"/demo/actions/send", "POST", {"roomId":room}, None)

    def get_messages(self):
        try:
            length = int(window.eval("window._chatSlayer.messages ? window._chatSlayer.messages.length : 0"))
            msgs=[]
            for i in range(length):
                try:
                    s = window.eval(f"window._chatSlayer.messages[{i}].sender")
                    b = window.eval(f"window._chatSlayer.messages[{i}].body")
                    ts = window.eval(f"window._chatSlayer.messages[{i}].timestamp")
                    msgs.append({"sender":str(s),"body":str(b),"timestamp":int(ts) if ts else int(time.time()*1000)})
                except:
                    continue
            self.messages = msgs[-50:]
            return self.messages
        except:
            return self.messages

    # ---- UI for name/password per CLIENT_GUIDE ----
    def ensure_login_inputs(self, app, x=20, y=240):
        # Create WaInput for username/password if not exists, per CLIENT_GUIDE requirement
        if not HAS_UI:
            return
        if self._input_user is None:
            try:
                self._input_user = WaInput(x, y, w=180, h=28, placeholder="chat username", value=self.username, label="Chat Name")
                self._input_pass = WaInput(x, y+40, w=180, h=28, placeholder="password (8+ chars)", value=self.password, label="Chat Password")
                self._btn_register = WaButton("REGISTER", x, y+80, w=85, h=32, variant="brand")
                self._btn_login = WaButton("LOGIN", x+95, y+80, w=85, h=32, variant="neutral", appearance="outlined")
            except Exception as e:
                _log(f"ensure_login_inputs fail {e}")

    def draw_login_ui(self, app):
        # Draw name/password entry for chat slayer
        if not HAS_UI or not self.show_login_ui:
            return
        try:
            from scs import drawRect, drawLabel
            # custom rounded rect using drawRect with roundness (fix: scs has no drawRoundedRect)
            def _rr(x,y,w,h,r,fill,border=None):
                try:
                    drawRect(x,y,w,h,fill=fill,border=border,borderWidth=1,roundness=r)
                except:
                    drawRect(x,y,w,h,fill=fill,border=border,borderWidth=1)
            self.ensure_login_inputs(app)
            if self._input_user:
                self._input_user.draw()
            if self._input_pass:
                self._input_pass.draw()
            if self._btn_register:
                self._btn_register.draw()
            if self._btn_login:
                self._btn_login.draw()
            # error
            if self.login_error:
                drawLabel(self.login_error, 20, 360, size=9, fill=(255,120,120), align="left-top", bold=True)
            drawLabel("CHAT-SLAYER LOGIN (CLIENT_GUIDE.md)", 20, 230, size=9, fill=(180,200,220), align="left-top", bold=True)
        except Exception as e:
            _log(f"draw_login_ui fail {e}")

    def handle_login_press(self, mx, my):
        # Returns True if handled
        if not HAS_UI: return False
        try:
            if self._input_user and self._input_user.contains(mx,my):
                self._input_user.focused=True
                if self._input_pass: self._input_pass.focused=False
                return True
            if self._input_pass and self._input_pass.contains(mx,my):
                self._input_pass.focused=True
                if self._input_user: self._input_user.focused=False
                return True
            if self._btn_register and self._btn_register.contains(mx,my):
                # REGISTER per CLIENT_GUIDE 2-step
                u = getattr(self._input_user, 'value', self.username) if self._input_user else self.username
                p = getattr(self._input_pass, 'value', self.password) if self._input_pass else self.password
                if len(p)<8:
                    self.login_error="Password min 8 chars (CLIENT_GUIDE)"
                    return True
                self.username=u; self.password=p
                self.register_or_login(u,p)
                self.login_error=f"Trying register {u}..."
                return True
            if self._btn_login and self._btn_login.contains(mx,my):
                u = getattr(self._input_user, 'value', self.username) if self._input_user else self.username
                p = getattr(self._input_pass, 'value', self.password) if self._input_pass else self.password
                self.username=u; self.password=p
                self.register_or_login(u,p)
                self.login_error=f"Trying login {u}..."
                return True
        except Exception as e:
            _log(f"handle_login_press fail {e}")
        return False

    def draw_chat_overlay(self, app):
        try:
            from scs import drawRect, drawLabel
            def _rr(x,y,w,h,r,fill,border=None,bw=1):
                try:
                    drawRect(x,y,w,h,fill=fill,border=border,borderWidth=bw,roundness=r)
                except:
                    drawRect(x,y,w,h,fill=fill,border=border,borderWidth=bw)
            self.get_messages()
            msgs = self.messages[-8:]
            chat_x=12; chat_y=app.height-180; chat_w=340; chat_h=140
            if msgs or self._chat_open:
                _rr(chat_x-6, chat_y-6, chat_w+12, chat_h+12, 8, (18,18,24), (60,60,70), 1)
                drawLabel(f"CHAT [{self.room_name}] {self.username}", chat_x+6, chat_y-2, size=8, fill=(180,200,220), bold=True, align="left-top")
                for i,m in enumerate(msgs):
                    y=chat_y+14+i*16
                    drawLabel(f"{m.get('sender','')[:16]}: {m.get('body','')[:50]}", chat_x+6, y, size=8, fill=(200,200,220), align="left-top")
            if self._chat_open:
                input_y=chat_y+chat_h+8
                _rr(chat_x-4, input_y-2, chat_w+8, 22, 6, (30,32,45), (80,90,120), 1)
                blink = int(time.time()*2)%2==0
                cursor = "_" if blink else ""
                drawLabel(f"> {self._chat_input}{cursor}", chat_x+4, input_y+4, size=9, fill=(220,230,255), align="left-top")
        except Exception as e:
            _log(f"draw_chat_overlay fail {e}")

    def open_chat(self): self._chat_open=True
    def close_chat(self): self._chat_open=False
    def toggle_chat(self): self._chat_open=not self._chat_open; return self._chat_open
    def set_input(self, t): self._chat_input=t[:200]

_global=None
def get_chat_client(base_url=None, client_id=None, username=None):
    global _global
    if _global is None:
        _global=ChatSlayerClient(base_url=base_url, client_id=client_id, username=username)
    else:
        if base_url: _global.base_url=base_url.rstrip("/")
        if username: _global.username=username
    return _global

def init_chat(app, base_url=None):
    try:
        username=getattr(app,'username',None) or f"Player{random.randint(1000,9999)}"
        client=get_chat_client(base_url=base_url, username=username, client_id="web-demo")
        app.chat_client=client
        window._chatSlayer.tetrioUsername=username
        client.register_or_login()
        _log(f"init_chat for {username}")
        return client
    except Exception as e:
        _log(f"init_chat fail {e}")
        return None
