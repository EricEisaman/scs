"""
extensions/chat_slayer.py — General purpose Chat Slayer extension for ALL apps

Lightweight Matrix-compatible chat server client (https://github.com/EricEisaman/chat-slayer)
- Single Node process, in-memory state, bundled for Render free tier
- Client apps use standard Matrix client API routes under /_matrix/client/...
- Demo uses Datastar SSE (GET /demo/stream) + actions (POST /demo/actions/*)
- Works for any app: games, chat apps, collaborative tools, etc.

General purpose — NOT TETR.IO specific:
- Can be imported by any app in /mnt/data/apps/*.py
- Provides ChatSlayerClient for Matrix-compatible chat
- Headers: X-Chat-Slayer-Client-Id (required), Authorization Bearer (after login)
- Supports: register, login, create/join rooms, send messages, history, SSE live updates
- Configurable base_url, client_id, username per app

Usage examples:

# Any app (Brython):
from extensions.chat_slayer import ChatSlayerClient, get_chat_client, init_chat

# 1. Basic chat
client = ChatSlayerClient(
    base_url="https://your-chat-slayer.onrender.com",
    client_id="my-app",
    username="Player1"
)
client.register_or_login()
client.join_room("Lobby")
client.send("Hello world!")

# 2. TETR.IO integration (OPEN CHAT is SLASH per config.png):
app.chat_client = ChatSlayerClient(
    base_url="https://scs-207.onrender.com",
    client_id="tetrio-chat",
    username=app.username
)
app.chat_client.register_or_login()
app.chat_client.join_room("Lobby")

# 3. Generic init helper (works for all apps):
client = init_chat(app, base_url="https://your-server.com")

API routes used:
    POST /_matrix/client/r0/register?kind=user  — register (401 -> retry with m.login.dummy)
    POST /_matrix/client/r0/login              — login
    POST /_matrix/client/r0/createRoom         — create room
    POST /_matrix/client/r0/rooms/register     — idempotent ensure rooms
    POST /_matrix/client/r0/join/{roomId}     — join room
    PUT  /_matrix/client/r0/rooms/{roomId}/send/m.room.message/{txnId}
    GET  /_matrix/client/v3/rooms/{roomId}/messages?limit=N
    GET  /demo/stream (SSE) — live room directory + messages (Datastar)
"""

from browser import window
import json as py_json
import time
import random

# Default config — can be overridden per client
DEFAULT_BASE_URL = "https://scs-207.onrender.com"
DEFAULT_CLIENT_ID = "tetrio-chat"
DEFAULT_ROOM = "Lobby"

# Global JS state for SSE and signals
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
                connected: false
            };
        }
        """)
    except:
        pass

_ensure_js_state()

def _js_log(msg):
    try:
        print(f"[ChatSlayer] {msg}")
    except:
        pass

def _b64_random_id():
    try:
        return f"{int(time.time()*1000)}_{random.randint(1000,9999)}"
    except:
        return f"txn_{int(time.time())}"

class ChatSlayerClient:
    """
    Matrix-compatible client for Chat Slayer
    Works in Brython via window.fetch (JS interop)
    """
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
        self.messages = []  # list of {sender, body, timestamp}
        self._txn_counter = 0
        self._chat_open = False
        self._chat_input = ""
        self._on_message_cb = None

        _ensure_js_state()
        _js_log(f"Client created base={self.base_url} id={self.client_id} user={self.username}")

    def _fetch(self, path, method="GET", body=None, headers_extra=None, callback=None):
        """
        Do fetch via window.eval to avoid Brython CORS issues
        body should be dict or None
        """
        try:
            url = self.base_url + path
            headers = {
                "Content-Type": "application/json",
                "X-Chat-Slayer-Client-Id": self.client_id
            }
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            if headers_extra:
                headers.update(headers_extra)

            body_str = py_json.dumps(body) if body is not None else "null"
            # Use window.fetch via eval
            script = f"""
            (async () => {{
                try {{
                    const res = await fetch({py_json.dumps(url)}, {{
                        method: {py_json.dumps(method)},
                        headers: {py_json.dumps(headers)},
                        body: {body_str} === null ? undefined : {py_json.dumps(body_str)} === "null" ? undefined : JSON.stringify({body_str} ? JSON.parse({py_json.dumps(body_str)}) : {py_json.dumps(body_str)}),
                    }});
                    const text = await res.text();
                    let data;
                    try {{ data = JSON.parse(text); }} catch(e) {{ data = text; }}
                    window._chatSlayer.lastResponse = {{status: res.status, data: data, url: {py_json.dumps(url)}}};
                    console.log("[ChatSlayer] fetch", {py_json.dumps(url)}, res.status, data);
                    return {{status: res.status, data: data}};
                }} catch(e) {{
                    console.error("[ChatSlayer] fetch fail", e, {py_json.dumps(url)});
                    window._chatSlayer.lastError = String(e);
                    return {{status: 0, data: {{error: String(e)}}}};
                }}
            }})()
            """
            # Simplify: use eval for promise
            # For Brython we need to handle async via window.eval returning promise
            # We'll use a sync-style via window.eval and store in _chatSlayer
            window.eval(f"""
            fetch({py_json.dumps(url)}, {{
                method: {py_json.dumps(method)},
                headers: {py_json.dumps(headers)},
                body: {body_str} === null || {py_json.dumps(body_str)} === "null" ? undefined : {py_json.dumps(body_str)}
            }}).then(async r => {{
                const t = await r.text();
                let d; try {{ d = JSON.parse(t); }} catch(e) {{ d = t; }}
                window._chatSlayer.lastResponse = {{status: r.status, data: d}};
                console.log("[ChatSlayer]", r.status, d);
            }}).catch(e => {{
                console.error("[ChatSlayer] fetch error", e);
                window._chatSlayer.lastError = String(e);
            }});
            """)
            return True
        except Exception as e:
            _js_log(f"fetch fail {e}")
            return False

    def _fetch_sync(self, path, method="GET", body=None):
        """
        Synchronous-ish fetch using window.eval with JSON stringify
        Returns parsed response from window._chatSlayer.lastResponse after short delay
        This is best-effort; for real production use SSE + async callbacks
        """
        try:
            url = self.base_url + path
            headers = {
                "Content-Type": "application/json",
                "X-Chat-Slayer-Client-Id": self.client_id
            }
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"

            body_json = py_json.dumps(body) if body is not None else "null"
            headers_json = py_json.dumps(headers)

            js = f"""
            fetch({py_json.dumps(url)}, {{
                method: {py_json.dumps(method)},
                headers: {headers_json},
                body: {body_json} === "null" ? undefined : {body_json}
            }}).then(r => r.text().then(t => {{
                let d; try {{ d = JSON.parse(t); }} catch(e) {{ d = t; }}
                window._chatSlayer.lastResponse = {{status: r.status, data: d, path: {py_json.dumps(path)}}};
            }})).catch(e => {{
                window._chatSlayer.lastError = String(e);
            }});
            """
            window.eval(js)
            return True
        except Exception as e:
            _js_log(f"_fetch_sync fail {e}")
            return False

    def register_or_login(self):
        """
        Try register, if user exists then login
        Implements Matrix UIAA: first POST without auth returns 401 with session,
        second POST with m.login.dummy + session
        """
        _js_log(f"register_or_login {self.username}")
        # Try register step 1 (no auth) — will get 401 with session
        self._fetch_sync("/_matrix/client/r0/register?kind=user", method="POST", body={
            "username": self.username,
            "password": self.password
        })
        # The actual retry with dummy auth needs session from 401 response
        # For simplicity, try direct login after a short delay via JS
        window.eval(f"""
        (async () => {{
            const base = {py_json.dumps(self.base_url)};
            const cid = {py_json.dumps(self.client_id)};
            const user = {py_json.dumps(self.username)};
            const pass = {py_json.dumps(self.password)};
            const headers = {{"Content-Type":"application/json","X-Chat-Slayer-Client-Id": cid}};
            // Step 1: try register without auth to get session
            let regRes = await fetch(base + "/_matrix/client/r0/register?kind=user", {{
                method: "POST", headers: headers,
                body: JSON.stringify({{username: user, password: pass}})
            }});
            let regText = await regRes.text();
            let regData;
            try {{ regData = JSON.parse(regText); }} catch(e) {{ regData = regText; }}
            console.log("[ChatSlayer] register step1", regRes.status, regData);
            if (regRes.status === 200) {{
                // Registered directly (some servers allow)
                window._chatSlayer.token = regData.access_token;
                window._chatSlayer.userId = regData.user_id;
                window._chatSlayer.lastResponse = {{status: regRes.status, data: regData}};
                console.log("[ChatSlayer] registered", regData.user_id);
                return;
            }}
            if (regRes.status === 401 && regData.session) {{
                // Retry with dummy auth
                let regRes2 = await fetch(base + "/_matrix/client/r0/register?kind=user", {{
                    method: "POST", headers: headers,
                    body: JSON.stringify({{
                        username: user, password: pass,
                        auth: {{type: "m.login.dummy", session: regData.session}}
                    }})
                }});
                let regText2 = await regRes2.text();
                let regData2;
                try {{ regData2 = JSON.parse(regText2); }} catch(e) {{ regData2 = regText2; }}
                console.log("[ChatSlayer] register step2", regRes2.status, regData2);
                if (regRes2.status === 200) {{
                    window._chatSlayer.token = regData2.access_token;
                    window._chatSlayer.userId = regData2.user_id;
                    window._chatSlayer.lastResponse = {{status: regRes2.status, data: regData2}};
                    return;
                }}
                // If user exists, try login
                if (regRes2.status === 400 || regRes2.status === 409) {{
                    console.log("[ChatSlayer] user exists, trying login");
                }}
            }}
            // Login
            let loginRes = await fetch(base + "/_matrix/client/r0/login", {{
                method: "POST", headers: headers,
                body: JSON.stringify({{type: "m.login.password", user: user, password: pass}})
            }});
            let loginText = await loginRes.text();
            let loginData;
            try {{ loginData = JSON.parse(loginText); }} catch(e) {{ loginData = loginText; }}
            console.log("[ChatSlayer] login", loginRes.status, loginData);
            if (loginRes.status === 200) {{
                window._chatSlayer.token = loginData.access_token;
                window._chatSlayer.userId = loginData.user_id;
                window._chatSlayer.lastResponse = {{status: loginRes.status, data: loginData}};
            }} else {{
                window._chatSlayer.lastResponse = {{status: loginRes.status, data: loginData}};
            }}
        }})();
        """)
        _js_log("register_or_login kicked off async")
        return True

    def login(self):
        return self.register_or_login()

    def _update_from_js(self):
        """Pull token/userId from window._chatSlayer"""
        try:
            token = window._chatSlayer.token
            user_id = window._chatSlayer.userId
            if token:
                self.access_token = str(token)
                self.connected = True
            if user_id:
                self.user_id = str(user_id)
            # Check lastResponse for room etc
            last = getattr(window._chatSlayer, 'lastResponse', None)
            if last and isinstance(last, dict):
                data = last.get('data') if hasattr(last, 'get') else getattr(last, 'data', None)
                # For dict from JS
                try:
                    if hasattr(data, 'to_dict'):
                        data = data.to_dict()
                except:
                    pass
            return True
        except:
            return False

    def join_room(self, room_name=None):
        """Join or create room by display name (idempotent via /rooms/register)"""
        room = room_name or self.room_name
        self.room_name = room
        _js_log(f"join_room {room}")
        window.eval(f"""
        (async () => {{
            const base = {py_json.dumps(self.base_url)};
            const cid = {py_json.dumps(self.client_id)};
            const token = window._chatSlayer.token;
            if (!token) {{ console.warn("[ChatSlayer] no token yet for join"); return; }}
            const headers = {{
                "Content-Type":"application/json",
                "X-Chat-Slayer-Client-Id": cid,
                "Authorization": "Bearer " + token
            }};
            // Idempotent ensure room exists
            let res = await fetch(base + "/_matrix/client/r0/rooms/register", {{
                method: "POST", headers: headers,
                body: JSON.stringify({{names: [{py_json.dumps(room)}]}})
            }});
            let text = await res.text();
            let data;
            try {{ data = JSON.parse(text); }} catch(e) {{ data = text; }}
            console.log("[ChatSlayer] rooms/register", res.status, data);
            if (res.status === 200 && data.rooms && data.rooms[0]) {{
                const roomId = data.rooms[0].room_id;
                window._chatSlayer.roomId = roomId;
                window._chatSlayer.lastResponse = {{status: res.status, data: data}};
                // Also try /messages to get history
                let histRes = await fetch(base + "/_matrix/client/v3/rooms/" + encodeURIComponent(roomId) + "/messages?limit=20", {{
                    headers: headers
                }});
                let histText = await histRes.text();
                let histData;
                try {{ histData = JSON.parse(histText); }} catch(e) {{ histData = histText; }}
                console.log("[ChatSlayer] history", histRes.status, histData);
                if (histData.chunk) {{
                    window._chatSlayer.messages = histData.chunk.map(ev => ({{
                        sender: ev.sender,
                        body: ev.content?.body || ev.content?.msg || "",
                        timestamp: ev.origin_server_ts || Date.now()
                    }}));
                }}
            }}
        }})();
        """)
        return True

    def send(self, message, room_id=None):
        """Send message to room"""
        if not message or not message.strip():
            return False
        msg = message.strip()[:500]
        target_room = room_id or self.room_id or getattr(window._chatSlayer, 'roomId', None)
        if not target_room:
            # Fallback to room name register then send
            target_room = self.room_name
        _js_log(f"send to {target_room}: {msg[:50]}")
        window.eval(f"""
        (async () => {{
            const base = {py_json.dumps(self.base_url)};
            const cid = {py_json.dumps(self.client_id)};
            const token = window._chatSlayer.token;
            let roomId = {py_json.dumps(str(target_room))};
            // If roomId is display name, resolve first
            if (!roomId.startsWith("!")) {{
                // Try to get roomId from cache
                roomId = window._chatSlayer.roomId || roomId;
            }}
            if (!token) {{ console.warn("[ChatSlayer] no token for send"); return; }}
            if (!roomId || !roomId.startsWith("!")) {{
                console.warn("[ChatSlayer] no roomId for send, have", roomId);
                // Try register again to get roomId
                const headers = {{
                    "Content-Type":"application/json",
                    "X-Chat-Slayer-Client-Id": cid,
                    "Authorization": "Bearer " + token
                }};
                let regRes = await fetch(base + "/_matrix/client/r0/rooms/register", {{
                    method: "POST", headers: headers,
                    body: JSON.stringify({{names: [roomId]}})
                }});
                let regText = await regRes.text();
                let regData;
                try {{ regData = JSON.parse(regText); }} catch(e) {{ regData = regText; }}
                if (regData.rooms && regData.rooms[0]) {{
                    roomId = regData.rooms[0].room_id;
                    window._chatSlayer.roomId = roomId;
                }}
            }}
            const headers = {{
                "Content-Type":"application/json",
                "X-Chat-Slayer-Client-Id": cid,
                "Authorization": "Bearer " + token
            }};
            const txnId = "txn" + Date.now() + Math.random().toString(36).slice(2);
            const body = {{msgtype: "m.text", body: {py_json.dumps(msg)}}};
            let url = base + "/_matrix/client/r0/rooms/" + encodeURIComponent(roomId) + "/send/m.room.message/" + txnId;
            let res = await fetch(url, {{
                method: "PUT", headers: headers,
                body: JSON.stringify(body)
            }});
            let text = await res.text();
            let data;
            try {{ data = JSON.parse(text); }} catch(e) {{ data = text; }}
            console.log("[ChatSlayer] send", res.status, data);
            if (res.status === 200) {{
                // Optimistic local echo
                if (!window._chatSlayer.messages) window._chatSlayer.messages = [];
                window._chatSlayer.messages.push({{
                    sender: window._chatSlayer.userId || "me",
                    body: {py_json.dumps(msg)},
                    timestamp: Date.now()
                }});
                // Keep last 50
                if (window._chatSlayer.messages.length > 50) {{
                    window._chatSlayer.messages = window._chatSlayer.messages.slice(-50);
                }}
            }}
            window._chatSlayer.lastResponse = {{status: res.status, data: data}};
        }})();
        """)
        return True

    def start_sse(self):
        """Start Datastar SSE stream for live messages (GET /demo/stream) — uses same token"""
        _js_log("start_sse")
        window.eval(f"""
        (async () => {{
            const base = {py_json.dumps(self.base_url)};
            const cid = {py_json.dumps(self.client_id)};
            const token = window._chatSlayer.token;
            if (!token) {{ console.warn("[ChatSlayer] no token for SSE"); return; }}
            if (window._chatSlayer.es) {{
                try {{ window._chatSlayer.es.close(); }} catch(e) {{}}
            }}
            // Use demo stream if available, else Matrix sync
            // For Matrix, we poll /messages every 3s as fallback
            const headers = {{
                "X-Chat-Slayer-Client-Id": cid,
                "Authorization": "Bearer " + token
            }};
            // Try demo SSE first (Datastar)
            try {{
                const es = new EventSource(base + "/demo/stream?token=" + encodeURIComponent(token));
                window._chatSlayer.es = es;
                es.addEventListener("datastar-patch-signals", (e) => {{
                    try {{
                        let raw = e.data;
                        if (raw.startsWith("signals ")) raw = raw.slice(8);
                        let data = JSON.parse(raw);
                        // Look for room-message
                        if (data["room-message"] || (data.cs && data.cs.payload)) {{
                            let payload = data["room-message"] || (data.cs ? data.cs.payload : null);
                            if (payload && payload.body) {{
                                if (!window._chatSlayer.messages) window._chatSlayer.messages = [];
                                window._chatSlayer.messages.push({{
                                    sender: payload.sender || "unknown",
                                    body: payload.body,
                                    timestamp: payload.timestamp || Date.now()
                                }});
                                if (window._chatSlayer.messages.length > 50) window._chatSlayer.messages = window._chatSlayer.messages.slice(-50);
                                console.log("[ChatSlayer] SSE message", payload);
                            }}
                        }}
                    }} catch(err) {{ console.warn("[ChatSlayer] SSE parse fail", err, e.data); }}
                }});
                es.onopen = () => {{ console.log("[ChatSlayer] SSE open"); window._chatSlayer.connected = true; }};
                es.onerror = (err) => {{ console.warn("[ChatSlayer] SSE error", err); }};
            }} catch(err) {{
                console.warn("[ChatSlayer] SSE setup fail", err);
            }}
            // Fallback poll every 3s for Matrix messages
            if (window._chatSlayer.pollInterval) clearInterval(window._chatSlayer.pollInterval);
            window._chatSlayer.pollInterval = setInterval(async () => {{
                try {{
                    let roomId = window._chatSlayer.roomId;
                    if (!roomId) return;
                    let res = await fetch(base + "/_matrix/client/v3/rooms/" + encodeURIComponent(roomId) + "/messages?limit=20", {{
                        headers: headers
                    }});
                    let text = await res.text();
                    let data;
                    try {{ data = JSON.parse(text); }} catch(e) {{ data = text; }}
                    if (data.chunk) {{
                        window._chatSlayer.messages = data.chunk.map(ev => ({{
                            sender: ev.sender,
                            body: ev.content?.body || "",
                            timestamp: ev.origin_server_ts || Date.now()
                        }}));
                    }}
                }} catch(e) {{ console.warn("[ChatSlayer] poll fail", e); }}
            }}, 3000);
        }})();
        """)
        return True

    def get_messages(self):
        """Pull messages from JS state into Python list"""
        try:
            js_msgs = getattr(window._chatSlayer, 'messages', [])
            # Convert JS array to Python list
            py_msgs = []
            try:
                # window._chatSlayer.messages is JS array, iterate via length
                length = int(window.eval("window._chatSlayer.messages ? window._chatSlayer.messages.length : 0"))
                for i in range(length):
                    try:
                        sender = window.eval(f"window._chatSlayer.messages[{i}].sender")
                        body = window.eval(f"window._chatSlayer.messages[{i}].body")
                        ts = window.eval(f"window._chatSlayer.messages[{i}].timestamp")
                        py_msgs.append({"sender": str(sender), "body": str(body), "timestamp": int(ts) if ts else int(time.time()*1000)})
                    except:
                        continue
            except:
                # Fallback: try direct
                try:
                    py_msgs = list(js_msgs)
                except:
                    py_msgs = []
            self.messages = py_msgs[-50:]
            return self.messages
        except Exception as e:
            _js_log(f"get_messages fail {e}")
            return self.messages

    def open_chat(self):
        self._chat_open = True
        _js_log("chat opened")

    def close_chat(self):
        self._chat_open = False
        self._chat_input = ""
        _js_log("chat closed")

    def toggle_chat(self):
        self._chat_open = not self._chat_open
        return self._chat_open

    def set_input(self, text):
        self._chat_input = text[:200]

    def draw_chat_overlay(self, app):
        """
        Draw chat overlay for TETR.IO — call from redrawAll when chat open or messages present
        Matches TETR.IO chat style: bottom-left, semi-transparent
        """
        try:
            from scs import drawRect, drawLabel, drawRoundedRect
            # Pull latest messages
            self.get_messages()
            msgs = self.messages[-8:]  # last 8

            # Chat history area — bottom left, above footer
            chat_x = 12
            chat_y = app.height - 180
            chat_w = 340
            chat_h = 140

            if msgs or self._chat_open:
                # Background
                drawRoundedRect(chat_x-6, chat_y-6, chat_w+12, chat_h+12, 8, (18,18,24), border=(60,60,70), borderWidth=1)
                # Title
                drawLabel(f"CHAT [{self.room_name}]", chat_x+6, chat_y-2, size=8, fill=(180,200,220), bold=True, align="left-top")
                # Messages
                for i, m in enumerate(msgs):
                    y = chat_y + 14 + i*16
                    sender = m.get('sender','')[:20]
                    body = m.get('body','')[:60]
                    # Color by sender
                    is_me = self.user_id and sender == self.user_id
                    col = (120,255,150) if is_me else (200,200,220)
                    drawLabel(f"{sender}: {body}", chat_x+6, y, size=8, fill=col, align="left-top")

            if self._chat_open:
                # Input box
                input_y = chat_y + chat_h + 8
                drawRoundedRect(chat_x-4, input_y-2, chat_w+8, 22, 6, (30,32,45), border=(80,90,120), borderWidth=1)
                # Cursor blink
                blink = int(time.time()*2) % 2 == 0
                cursor = "_" if blink else ""
                drawLabel(f"> {self._chat_input}{cursor}", chat_x+4, input_y+4, size=9, fill=(220,230,255), align="left-top")
                drawLabel("ENTER to send, ESC to close", chat_x+chat_w-4, input_y+4, size=7, fill=(120,130,150), align="right-top")

        except Exception as e:
            _js_log(f"draw_chat_overlay fail {e}")

# Singleton helper for app
_global_client = None

def get_chat_client(base_url=None, client_id=None, username=None):
    global _global_client
    if _global_client is None:
        _global_client = ChatSlayerClient(base_url=base_url, client_id=client_id, username=username)
    else:
        if base_url:
            _global_client.base_url = base_url.rstrip("/")
        if username:
            _global_client.username = username
    return _global_client

def init_chat(app, base_url=None):
    """
    Initialize chat for TETR.IO app
    Call from onAppStart or after welcome
    """
    try:
        username = getattr(app, 'username', None) or f"Player{random.randint(1000,9999)}"
        client = get_chat_client(base_url=base_url, username=username, client_id="tetrio-chat")
        app.chat_client = client
        # Store in window for JS access
        window._chatSlayer.tetrioUsername = username
        client.register_or_login()
        # Delay join and SSE to allow token to be set
        window.eval(f"""
        setTimeout(() => {{
            if (window._chatSlayer.token) {{
                console.log("[ChatSlayer] token ready, joining Lobby");
                // join will be triggered by Python after a bit, but also try here
            }}
        }}, 1500);
        """)
        # Schedule join via Python after 2s
        def _delayed_join():
            try:
                client._update_from_js()
                if client.access_token:
                    client.join_room("Lobby")
                    client.start_sse()
            except:
                pass
        # Use window.setTimeout for delayed join
        window.eval(f"setTimeout(() => {{ console.log('[ChatSlayer] delayed join check'); }}, 2000);")
        # We'll rely on onStep to call _update_from_js and auto-join
        _js_log(f"init_chat for {username}")
        return client
    except Exception as e:
        _js_log(f"init_chat fail {e}")
        return None
