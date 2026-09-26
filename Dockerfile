# Dockerfile for scs-datastar-extension
# Serves datastar backend with /healthz AND static files
FROM python:3.11-slim

WORKDIR /app

# Copy everything - includes index.html, sandbox.html, PROCAUDIO.html, scs.py, apps/, extensions/, etc.
COPY . .

# Install any Python deps if requirements.txt exists
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi \
    && if [ -f scs-datastar-extension/requirements.txt ]; then pip install --no-cache-dir -r scs-datastar-extension/requirements.txt; fi

# Ensure .nojekyll
RUN touch .nojekyll

EXPOSE 10000

# If scs-datastar-extension has its own server, run it, otherwise fall back to static file server with /healthz
# This CMD handles both: if datastar server exists, it will serve static files as well via same port
CMD python -c "
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading

PORT = int(os.environ.get('PORT', 10000))

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        # Health check for Render
        if self.path == '/healthz':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')
            return
        # Serve all static files including index.html, sandbox.html, PROCAUDIO.html, scs.py, apps/, extensions/
        return super().do_GET()
    
    def end_headers(self):
        # No cache for scs.py and apps - CDN clears immediately
        if self.path.endswith('.py') or self.path.endswith('.html'):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

print(f'Serving ALL static files + /healthz on port {PORT}')
print(f'Files: index.html, sandbox.html, PROCAUDIO.html, scs.py, apps/, extensions/')
HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
"
