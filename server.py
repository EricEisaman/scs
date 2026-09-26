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

_lock = threading.Lock()
_sessions = {}
_char_states = {}
_client_env = {}
_last_cleanup = 0

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
        
        if path.startswith('/api/multiplayer/stream'):
            sid = query.get('sid', ['unknown'])[0]
            with _lock:
                sess = _sessions.get(sid)
                my_cid = sess.get('client_id') if sess else None
                my_env = sess.get('env', 'level1') if sess else 'level1'
            
            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            self.wfile.write(b': connected\n\n')
            self.wfile.flush()
            
            try:
                global _last_cleanup
                # 300Hz = 0.00333s, but Python http.server can't do 300Hz without burning CPU
                # Use 100Hz (0.01s) - blazing but not CPU melt, your FastAPI does 300Hz with asyncio
                # This fallback only used if FastAPI down, so 100Hz is fine
                for _ in range(72000):  # 100Hz * 60 * 12min
                    with _lock:
                        now = time.time()
                        if now - _last_cleanup > 30:  # cleanup every 30s, not every tick
                            _last_cleanup = now
                            for old_sid in list(_sessions.keys()):
                                if now - _sessions[old_sid].get('last_seen', now) > 120:
                                    old_cid = _sessions[old_sid].get('client_id')
                                    _sessions.pop(old_sid, None)
                                    _char_states.pop(old_cid, None)
                                    _client_env.pop(old_cid, None)
                        if my_cid:
                            peers = [c for cid, c in _char_states.items() if cid != my_cid and _client_env.get(cid, 'level1') == my_env]
                        else:
                            peers = list(_char_states.values())
                        count = len(_sessions)
                    
                    # Outside lock - json + I/O
                    payload = {"character-state-update": {"updates": peers, "timestamp": int(now*1000)}, "peer-count": count}
                    sse_msg = f"event: datastar-patch-signals\ndata: signals {json.dumps(payload)}\n\n"
                    self.wfile.write(sse_msg.encode())
                    self.wfile.flush()
                    time.sleep(0.01)  # 100Hz BLAZING - your FastAPI does 300Hz with asyncio, this is fallback
            except:
                pass
            return
        
        if path.startswith('/api/multiplayer/join'):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            cid = f"client_{os.urandom(4).hex()}"
            sid = f"sess_{os.urandom(4).hex()}"
            with _lock:
                _sessions[sid] = {"client_id": cid, "env": "level1", "last_seen": time.time()}
                _client_env[cid] = "level1"
            resp = {"client_id": cid, "session_id": sid, "peer_id": cid, "clientId": cid, "sessionId": sid, "room": "level1", "status": "ok", "peer_count": len(_sessions)}
            self.wfile.write(json.dumps(resp).encode())
            return
        
        if path.startswith('/api/'):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "sessions": len(_sessions), "peers": len(_char_states)}).encode())
            return
        
        if 'favicon' in path_lower:
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
            
            with _lock:
                _sessions[sid] = {"client_id": cid, "env": env, "character_name": char_name, "last_seen": time.time()}
                _client_env[cid] = env
            
            resp = {"client_id": cid, "session_id": sid, "peer_id": cid, "clientId": cid, "sessionId": sid, "room": env, "environment": env, "status": "ok", "is_synchronizer": len(_sessions) == 1, "peer_count": len(_sessions)}
            self.wfile.write(json.dumps(resp).encode())
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
            updates = data.get('updates', [])
            if not updates and isinstance(data, dict) and 'position' in data:
                updates = [data]
            
            with _lock:
                for char in updates:
                    cid = char.get('clientId') or char.get('client_id') or client_id
                    if not cid:
                        continue
                    _char_states[cid] = char
                    sess = next((s for s in _sessions.values() if s.get('client_id') == cid), None)
                    if sess:
                        sess['last_seen'] = time.time()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
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

print(f'BLAZING 100Hz fallback + /healthz on {PORT} - FastAPI main.py does 300Hz')
HTTPServerClass = ThreadingHTTPServer
HTTPServerClass(('0.0.0.0', PORT), Handler).serve_forever()
