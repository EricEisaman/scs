import os
import json
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

PORT = int(os.environ.get('PORT', '10000'))
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'https://ericeisaman.github.io,https://scs-207.onrender.com,http://localhost:8000,https://scs-2qah.onrender.com').split(',')
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]

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
        
        # SSE stream - MUST be threaded or it blocks all other requests
        if path.startswith('/api/multiplayer/stream'):
            sid = query.get('sid', ['unknown'])[0]
            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            self.wfile.write(b': connected\n\n')
            self.wfile.flush()
            
            try:
                for i in range(120):  # 120 * 10s = 20 min
                    event_data = json.dumps({"updates": []})
                    sse_msg = f"event: datastar-patch-signals\ndata: signals {event_data}\n\n"
                    self.wfile.write(sse_msg.encode())
                    self.wfile.flush()
                    time.sleep(10)
            except:
                pass
            return
        
        if path.startswith('/api/multiplayer/join'):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            cid = f"client_{os.urandom(4).hex()}"
            sid = f"sess_{os.urandom(4).hex()}"
            resp = {
                "client_id": cid,
                "session_id": sid,
                "peer_id": cid,
                "clientId": cid,
                "sessionId": sid,
                "room": "level1",
                "status": "ok"
            }
            self.wfile.write(json.dumps(resp).encode())
            return
        
        if path.startswith('/api/'):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            resp = {"status": "ok"}
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
            resp = {
                "client_id": cid,
                "session_id": sid,
                "peer_id": cid,
                "clientId": cid,
                "sessionId": sid,
                "room": data.get("environment_name", "level1"),
                "status": "ok"
            }
            self.wfile.write(json.dumps(resp).encode())
            return
        
        if path.startswith('/api/'):
            content_length = int(self.headers.get('Content-Length', 0))
            self.rfile.read(content_length)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode()
            return
        
        self.send_response(404)
        self.end_headers()
    
    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path.startswith('/api/'):
            content_length = int(self.headers.get('Content-Length', 0))
            self.rfile.read(content_length)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode()
            return
        
        self.send_response(404)
        self.end_headers()

print(f'Serving ALL + SSE + API + /healthz on {PORT} with ThreadingHTTPServer (fixes blocking)')
HTTPServerClass = ThreadingHTTPServer
HTTPServerClass(('0.0.0.0', PORT), Handler).serve_forever()
