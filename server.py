import os
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
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
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With')
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
        
        if path == '/healthz':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')
            return
        
        if path.startswith('/api/'):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            resp = {
                "peer_id": f"peer_{os.urandom(4).hex()}",
                "room": "default",
                "status": "ok"
            }
            self.wfile.write(json.dumps(resp).encode())
            return
        
        # Favicon handling - serve from root regardless of /scs/ prefix or .ico/.png
        if 'favicon' in path_lower:
            # Try root favicon.png, favicon.ico, scs.jpg, etc.
            for candidate in ['favicon.png', 'favicon.ico', 'scs.jpg', 'scs.png']:
                if Path(candidate).exists():
                    self.path = f'/{candidate}'
                    break
            # Also handle /scs/favicon.png -> /favicon.png
            if path_lower in ('/scs/favicon.png', '/scs/favicon.ico', '/favicon.png', '/favicon.ico'):
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
        
        if path.startswith('/api/'):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length else b''
            
            self.send_response(200)
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
        
        self.send_response(404)
        self.end_headers()

print(f'Serving ALL static + favicon + API + /healthz on {PORT}')
HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
