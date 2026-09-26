# Dockerfile for scs-datastar-extension
# Serves datastar backend with /healthz AND static files
# Fixed: uses server.py instead of invalid multi-line CMD python -c
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

# Serve all static files + /healthz - uses server.py (valid Dockerfile syntax)
CMD ["python", "server.py"]
