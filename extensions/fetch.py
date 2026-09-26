from browser import window, aio
import json as py_json

class FetchError(RuntimeError):
    pass

class FetchResponse:
    def __init__(self, js_response, is_aio=False):
        self._js = js_response
        self._is_aio = is_aio
        try:
            self.ok = bool(js_response.ok) if not is_aio else True
        except:
            self.ok = True
        try:
            self.status = int(js_response.status) if hasattr(js_response, 'status') else 200
        except:
            self.status = 200
        try:
            self.statusText = str(js_response.statusText) if hasattr(js_response, 'statusText') else ""
        except:
            self.statusText = ""
    async def json(self):
        try:
            js_data = await self._js.json()
            return js_data
        except:
            txt = await self._js.text()
            return py_json.loads(txt)
    async def text(self):
        return await self._js.text()

async def fetch(url, method="GET", headers=None, body=None, mode="cors"):
    opts = {"method": method, "mode": mode}
    if headers:
        opts["headers"] = headers
    if body != None:
        opts["body"] = body
    try:
        js_resp = await window.fetch(url, opts)
        return FetchResponse(js_resp, is_aio=False)
    except Exception as e1:
        try:
            window.console.warn("[fetch] window.fetch failed, trying aio", str(e1)[:200])
        except:
            pass
        try:
            aio_resp = await aio.fetch(url, method=method)
            return FetchResponse(aio_resp, is_aio=True)
        except Exception as e2:
            raise FetchError(f"fetch failed {url}: {e1} / {e2}")

async def fetch_json(url):
    resp = await fetch(url)
    if not resp.ok:
        txt = await resp.text()
        raise FetchError(f"HTTP {resp.status} {txt[:200]}")
    js_data = await resp.json()
    try:
        return py_json.loads(window.JSON.stringify(js_data))
    except:
        return js_data

async def fetch_text(url):
    resp = await fetch(url)
    if not resp.ok:
        raise FetchError(f"HTTP {resp.status}")
    return await resp.text()
