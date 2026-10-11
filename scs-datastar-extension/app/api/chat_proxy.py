"""
app/chat_proxy.py — additive module for tetr-20/scs-datastar-extension
General server extension — does NOT overwrite existing multiplayer.py / main.py
Import via: from .chat_proxy import router as chat_proxy_router
           app.include_router(chat_proxy_router)

Implements /chat-api/{path} -> https://chat-slayer.onrender.com/{path}
Per babylon-game-starter CHAT.md: serviceUrl "/chat-api" same-origin on Render,
direct on github.io. Uses web-demo clientId which allows https://ericeisaman.github.io

Headers preserved: X-Chat-Slayer-Client-Id (required), Authorization Bearer,
X-Demo-Room-Id, X-Demo-Room-Name, X-Demo-Room-Names, X-Demo-Message
SSE: /chat-api/demo/stream streamed unbuffered (X-Accel-Buffering: no)
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
import os
import httpx

router = APIRouter()

CHAT_UPSTREAM_URL = os.getenv("CHAT_UPSTREAM_URL", "https://chat-slayer.onrender.com")
CHAT_CLIENT_ID_DEFAULT = os.getenv("CHAT_CLIENT_ID", "web-demo")

http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=60.0))

@router.api_route("/chat-api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def chat_api_proxy(path: str, request: Request):
    upstream = f"{CHAT_UPSTREAM_URL.rstrip('/')}/{path}"
    if request.url.query:
        upstream += f"?{request.url.query}"

    headers = {}
    for k in ["x-chat-slayer-client-id", "authorization", "x-demo-room-id", "x-demo-room-name", "x-demo-room-names", "x-demo-message", "content-type", "accept"]:
        v = request.headers.get(k) or request.headers.get(k.title())
        if v:
            headers[k] = v
    # Default to web-demo which allows https://ericeisaman.github.io per CLIENT_GUIDE.md
    if "x-chat-slayer-client-id" not in {kk.lower() for kk in headers}:
        headers["X-Chat-Slayer-Client-Id"] = CHAT_CLIENT_ID_DEFAULT

    body = await request.body()
    is_stream = "demo/stream" in path

    if is_stream:
        async def stream_gen():
            async with http_client.stream(request.method, upstream, headers=headers, content=body if body else None) as up:
                async for chunk in up.aiter_bytes():
                    yield chunk
        return StreamingResponse(stream_gen(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "*",
        })

    try:
        up_resp = await http_client.request(request.method, upstream, headers=headers, content=body if body else None)
        return Response(
            content=up_resp.content,
            status_code=up_resp.status_code,
            headers={k: v for k, v in up_resp.headers.items() if k.lower() not in ["content-encoding", "transfer-encoding", "connection"]},
            media_type=up_resp.headers.get("content-type"),
        )
    except Exception as e:
        return JSONResponse({"error": f"chat proxy failed: {e}", "upstream": upstream}, status_code=502)
