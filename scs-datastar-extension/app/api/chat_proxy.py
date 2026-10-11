"""
app/api/chat_proxy.py — CANONICAL LOCATION (see screenshot 2026-10-10)
tetr-21 branch: Dockerfile reference - must be FastAPI pattern

PURPOSE:
  Additive proxy for chat-slayer: /chat-api/{path} -> https://chat-slayer.onrender.com/{path}
  This is the ONLY new file required for chat integration.

FASTAPI PATTERN (no httpx):
    - Uses only fastapi + stdlib (urllib, http.client) — matches health.py pattern
    - APIRouter with @router.api_route("/chat-api/{path:path}")
    - No external deps — works even if httpx not installed (fixes ModuleNotFoundError on Render)
    - Same pattern as health: from fastapi import APIRouter; router = APIRouter()

DO NOT CREATE:
  app/chat_proxy.py (flat) — WRONG LOCATION
  app/chat_proxy_1.py — WRONG

CORRECT USAGE IN main.py (2 lines only):
  from.api.chat_proxy import router as chat_proxy_router
  app.include_router(chat_proxy_router)

Implements:
    - Per babylon-game-starter CHAT.md: serviceUrl "/chat-api" same-origin
    - Uses web-demo clientId which allows https://ericeisaman.github.io origin
    - Headers preserved: X-Chat-Slayer-Client-Id (required), Authorization Bearer,
    X-Demo-Room-Id, X-Demo-Room-Name, X-Demo-Room-Names, X-Demo-Message
    - SSE: /chat-api/demo/stream streamed via http.client (X-Accel-Buffering: no)

LESSON LEARNED:
  Previous version used httpx -> ModuleNotFoundError on Render tetr-21 branch.
  FastAPI pattern = no httpx, pure stdlib proxy.
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
import os
from urllib.parse import urlparse
import urllib.request
import urllib.error
import http.client

router = APIRouter()

CHAT_UPSTREAM_URL = os.getenv("CHAT_UPSTREAM_URL", "https://chat-slayer.onrender.com")
CHAT_CLIENT_ID_DEFAULT = os.getenv("CHAT_CLIENT_ID", "web-demo")

# Headers we forward (case-insensitive check, preserve original case for upstream)
FORWARD_HEADER_NAMES = [
    "x-chat-slayer-client-id",
    "authorization",
    "x-demo-room-id",
    "x-demo-room-name",
    "x-demo-room-names",
    "x-demo-message",
    "content-type",
    "accept",
    "origin",
]

HOP_BY_HOP = {"content-encoding", "transfer-encoding", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "upgrade"}

@router.api_route("/chat-api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def chat_api_proxy(path: str, request: Request):
    # Build upstream URL with query string preserved
    base = CHAT_UPSTREAM_URL.rstrip("/")
    upstream = f"{base}/{path}"
    if request.url.query:
        upstream += f"?{request.url.query}"

    # Collect headers to forward
    headers = {}
    for name in FORWARD_HEADER_NAMES:
        # FastAPI headers are case-insensitive, try lower and original
        v = request.headers.get(name) or request.headers.get(name.title()) or request.headers.get(name.upper())
        if v:
            # Use canonical header name expected upstream (preserve original casing for X- headers)
            if name == "x-chat-slayer-client-id":
                headers["X-Chat-Slayer-Client-Id"] = v
            elif name == "authorization":
                headers["Authorization"] = v
            elif name == "x-demo-room-id":
                headers["X-Demo-Room-Id"] = v
            elif name == "x-demo-room-name":
                headers["X-Demo-Room-Name"] = v
            elif name == "x-demo-room-names":
                headers["X-Demo-Room-Names"] = v
            elif name == "x-demo-message":
                headers["X-Demo-Message"] = v
            elif name == "origin":
                headers["Origin"] = v
            else:
                headers[name] = v

    # Default clientId to web-demo which allows https://ericeisaman.github.io per CLIENT_GUIDE.md
    lowered = {k.lower() for k in headers.keys()}
    if "x-chat-slayer-client-id" not in lowered:
        headers["X-Chat-Slayer-Client-Id"] = CHAT_CLIENT_ID_DEFAULT
    if "origin" not in lowered:
        headers["Origin"] = request.headers.get("origin") or request.headers.get("Origin") or "https://ericeisaman.github.io"

    body = await request.body()
    # urllib requires None for no body, not empty bytes for GET
    body_to_send = body if body else None
    is_stream = "demo/stream" in path

    if is_stream:
        # SSE streaming via http.client — no httpx
        def stream_gen():
            parsed = urlparse(upstream)
            scheme = parsed.scheme
            host = parsed.hostname
            port = parsed.port or (443 if scheme == "https" else 80)
            conn_cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
            conn = conn_cls(host, port, timeout=65)
            try:
                path_qs = parsed.path or "/"
                if parsed.query:
                    path_qs += f"?{parsed.query}"
                # http.client needs headers as dict
                conn.request(request.method, path_qs, body=body_to_send, headers=headers)
                resp = conn.getresponse()
                # Stream chunks
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    yield chunk
            except Exception as e:
                # Yield error as SSE comment to avoid silent close
                yield f": proxy error {e}\n\n".encode()
            finally:
                try:
                    conn.close()
                except:
                    pass

        return StreamingResponse(
            stream_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Methods": "*",
            },
        )

    # Non-streaming proxy via urllib — no httpx
    try:
        # urllib.request.Request will handle method
        req = urllib.request.Request(upstream, data=body_to_send, headers=headers, method=request.method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            status = resp.status
            # Filter hop-by-hop headers
            resp_headers = {}
            for k, v in resp.headers.items():
                if k.lower() not in HOP_BY_HOP:
                    resp_headers[k] = v
            # Ensure CORS
            if "Access-Control-Allow-Origin" not in resp_headers:
                resp_headers["Access-Control-Allow-Origin"] = request.headers.get("origin", "*")
            media_type = resp.headers.get_content_type()
            return Response(
                content=content,
                status_code=status,
                headers=resp_headers,
                media_type=media_type,
            )
    except urllib.error.HTTPError as e:
        # Upstream returned error status — forward body/status
        try:
            err_content = e.read()
        except:
            err_content = b""
        err_headers = {}
        try:
            for k, v in e.headers.items():
                if k.lower() not in HOP_BY_HOP:
                    err_headers[k] = v
        except:
            pass
        return Response(
            content=err_content,
            status_code=e.code,
            headers=err_headers,
            media_type=e.headers.get_content_type() if hasattr(e.headers, 'get_content_type') else None,
        )
    except Exception as e:
        return JSONResponse({"error": f"chat proxy failed: {e}", "upstream": upstream}, status_code=502)