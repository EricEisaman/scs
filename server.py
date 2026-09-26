import os
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

PORT = int(os.environ.get('PORT', '10000'))
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'https://ericeisaman.github.io,https://scs-207.onrender.com,http://localhost:8000,https://scs-2qah.onrender.com').split(',')
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]

class Handler(SimpleHTTPRequestHandler):
    def get_cors_origin(self):
        origin = self.headers.get('Origin', '')
        # Allow any origin in ALLOWED_ORIGINS or all if * logic
        if origin in ALLOWED_ORIGINS or '*' in ALLOWED_ORIGINS:
            return origin
        # For simplicity, allow ericeisaman.github.io always + localhost for dev
        if 'ericeisaman.github.io' in origin or 'localhost' in origin or 'onrender.com' in origin:
            return origin
        # Fallback: allow requesting origin (permissive for game)
        return origin if origin else '*'

    def send_cors_headers(self):
        origin = self.get_cors_origin()
        self.send_header('Access-Control-Allow-Origin', origin if origin else '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With')
        self.send_header('Access-Control-Allow-Credentials', 'true')
        self.send_header('Vary', 'Origin')

    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        path_lower = path.lower()
        
        # Health check
        if path == '/healthz':
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')
            return
        
        # API routes - handle multiplayer join with CORS
        if path.startswith('/api/'):
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            # Minimal multiplayer join response - returns peer id
            resp = {
                "peer_id": f"peer_{os.urandom(4).hex()}",
                "room": "default",
                "status": "ok",
                "message": "CORS fixed - multiplayer join stub"
            }
            self.wfile.write(json.dumps(resp).encode())
            return
        
        # Rewrites
        if path_lower in ('/sandbox', '/sandbox/'):
            self.path = '/sandbox.html'
        elif path_lower in ('/procaudio', '/procaudio/', '/proc-audio', '/proc-audio/'):
            self.path = '/PROCAUDIO.html'
        
        return super().do_GET()
    
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        # Handle multiplayer join POST with CORS
        if path.startswith('/api/'):
            # Read body if any
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length else b''
            
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            resp = {
                "peer_id": f"peer_{os.urandom(4).hex()}",
                "room": "default",
                "status": "ok",
                "received": len(body)
            }
            self.wfile.write(json.dumps(resp).encode())
            return
        
        # For other POSTs, fallback
        self.send_response(404)
        self.send_cors_headers()
        self.end_headers()

    def end_headers(self):
        # CORS for all responses
        self.send_cors_headers()
        if self.path.endswith('.py') or self.path.endswith('.html'):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

print(f'Serving ALL static + API + /healthz on {PORT}')
print(f'Allowed origins: {ALLOWED_ORIGINS}')
print(f'CORS fixed for /api/multiplayer/join from ericeisaman.github.io')
HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
