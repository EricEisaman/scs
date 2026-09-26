import os
import json
import time
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

PORT = int(os.environ.get('PORT', '10000'))
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'https://ericeisaman.github.io,https://scs-207.onrender.com,http://localhost:8000,https://scs-2qah.onrender.com').split(',')
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]

# --- Multiplayer state (thread-safe) ---
_state_lock = threading.Lock()
# sid -> {client_id, env, character_name, last_seen}
_sessions = {}
# client_id -> latest character dict from PATCH
_character_states = {}
# client_id -> env
_client_env = {}

def _cleanup_old_sessions():
    now = time.time()
    with _state_lock:
        to_del = [sid for sid, s in _sessions.items() if now - s.get('last_seen', now) > 60]
        for sid in to_del:
            cid = _sessions[sid].get('client_id')
            _sessions.pop(sid, None)
            _character_states.pop(cid, None)
            _client_env.pop(cid, None)

class Handler(SimpleHTTPRequestHandler):
    def get_cors_origin(self):
        origin = self.headers.get('Origin', '')
        if not origin:
            return '*'
        if origin in ALLOWED_ORIGINS or 'ericeisaman.github.io' in origin or 'localhost' in origin or 'onrender.com' in origin:
            return origin
        return origin

    def end_headers(self):
        origin = self.get_cors_origin()
        self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE, PATCH')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, X-Client-ID')
        self.send_header('Access-Control-Allow-Credentials', 'true')
        self.send_header('Vary', 'Origin')
        if self.path.endswith('.py') or self.path.endswith('.html'):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        path_lower = path.lower()
        query = parse_qs(parsed.query)
        
        if path == '/healthz':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')
            return
        
        # SSE stream - real peer broadcasting
        if path.startswith('/api/multiplayer/stream'):
            sid = query.get('sid', ['unknown'])[0]
            # lookup client_id and env for this sid
            with _state_lock:
                sess = _sessions.get(sid)
                if sess:
                    my_client_id = sess.get('client_id')
                    my_env = sess.get('env', 'level1')
                else:
                    my_client_id = None
                    my_env = 'level1'
            
            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            self.wfile.write(b': connected\n\n')
            self.wfile.flush()
            
            try:
                # 20 min loop, 100ms tick = 12000 iterations, but we do 120 * 10s for compat, now faster
                last_sent = {}
                for _ in range(1200):  # 1200 * 0.5s = 10 min
                    with _state_lock:
                        # cleanup
                        # collect peers in same env, excluding self
                        peers = []
                        for cid, char in _character_states.items():
                            if cid == my_client_id:
                                continue
                            env = _client_env.get(cid, 'level1')
                            if env != my_env:
                                continue
                            # only send if changed
                            peers.append(char)
                        # also include session count for debug
                        session_count = len(_sessions)
                    
                    if peers:
                        # Datastar format: signals { "character-state-update": {"updates": [...]}, "peer-count": N }
                        event_data = json.dumps({
                            "character-state-update": {"updates": peers},
                            "peer-count": session_count
                        })
                    else:
                        event_data = json.dumps({"peer-count": session_count, "character-state-update": {"updates": []}})
                    
                    sse_msg = f"event: datastar-patch-signals\ndata: signals {event_data}\n\n"
                    self.wfile.write(sse_msg.encode())
                    self.wfile.flush()
                    time.sleep(0.5)
            except Exception as e:
                # print(f"SSE closed {sid}: {e}")
                pass
            # on disconnect, cleanup after delay? keep for 10s
            return
        
        if path.startswith('/api/multiplayer/join'):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            cid = f"client_{os.urandom(4).hex()}"
            sid = f"sess_{os.urandom(4).hex()}"
            with _state_lock:
                _sessions[sid] = {"client_id": cid, "env": "level1", "last_seen": time.time()}
                _client_env[cid] = "level1"
            resp = {
                "client_id": cid,
                "session_id": sid,
                "peer_id": cid,
                "clientId": cid,
                "sessionId": sid,
                "room": "level1",
                "status": "ok",
                "peer_count": len(_sessions)
            }
            self.wfile.write(json.dumps(resp).encode())
            return
        
        if path.startswith('/api/'):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            resp = {"status": "ok", "sessions": len(_sessions)}
            self.wfile.write(json.dumps(resp).encode())
            return
        
        if 'favicon' in path_lower:
            for candidate in ['favicon.png', 'favicon.ico']:
                if Path(candidate).exists():
                    self.path = f'/{candidate}'
                    break
            if path_lower in ('/scs/favicon.png', '/scs/favicon.ico'):
                for candidate in ['favicon.png', 'favicon.ico']:
                    if Path(candidate).exists():
                        self.path = f'/{candidate}'
                        break
            return super().do_GET()
        
        if path_lower in ('/sandbox', '/sandbox/'):
            self.path = '/sandbox.html'
        elif path_lower in ('/procaudio', '/procaudio/', '/proc-audio', '/proc-audio/'):
            self.path = '/PROCAUDIO.html'
        
        return super().do_GET()
    
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path.startswith('/api/multiplayer/join'):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length else b''
            try:
                data = json.loads(body) if body else {}
            except:
                data = {}
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            cid = f"client_{os.urandom(4).hex()}"
            sid = f"sess_{os.urandom(4).hex()}"
            env = data.get("environment_name") or data.get("environment") or "level1"
            char_name = data.get("character_name", "Player")
            
            with _state_lock:
                _sessions[sid] = {"client_id": cid, "env": env, "character_name": char_name, "last_seen": time.time()}
                _client_env[cid] = env
                # cleanup old
                now = time.time()
                for old_sid in list(_sessions.keys()):
                    if now - _sessions[old_sid].get('last_seen', now) > 120:
                        old_cid = _sessions[old_sid].get('client_id')
                        _sessions.pop(old_sid, None)
                        _character_states.pop(old_cid, None)
                        _client_env.pop(old_cid, None)
            
            resp = {
                "client_id": cid,
                "session_id": sid,
                "peer_id": cid,
                "clientId": cid,
                "sessionId": sid,
                "room": env,
                "environment": env,
                "status": "ok",
                "peer_count": len(_sessions)
            }
            self.wfile.write(json.dumps(resp).encode())
            print(f"[JOIN] {cid} {char_name} env={env} total={len(_sessions)}")
            return
        
        if path.startswith('/api/'):
            content_length = int(self.headers.get('Content-Length', 0))
            self.rfile.read(content_length)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            return
        
        self.send_response(404)
        self.end_headers()
    
    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path.startswith('/api/multiplayer/character-state'):
            content_length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(content_length) if content_length else b'{}'
            try:
                data = json.loads(raw)
            except:
                data = {}
            
            client_id = self.headers.get('X-Client-ID') or data.get('clientId')
            # updates can be in data['updates'] or data itself is char
            updates = data.get('updates', [])
            if not updates and isinstance(data, dict) and 'position' in data:
                updates = [data]
            
            with _state_lock:
                for char in updates:
                    cid = char.get('clientId') or char.get('client_id') or client_id
                    if not cid:
                        continue
                    _character_states[cid] = char
                    # update last_seen for session containing this cid
                    for sid, sess in _sessions.items():
                        if sess.get('client_id') == cid:
                            sess['last_seen'] = time.time()
                            break
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "peers": len(_character_states)}).encode())
            return
        
        if path.startswith('/api/'):
            content_length = int(self.headers.get('Content-Length', 0))
            self.rfile.read(content_length)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            return
        
        self.send_response(404)
        self.end_headers()

print(f'Serving REAL MULTIPLAYER + SSE + API + /healthz on {PORT} with ThreadingHTTPServer')
HTTPServerClass = ThreadingHTTPServer
HTTPServerClass(('0.0.0.0', PORT), Handler).serve_forever()
