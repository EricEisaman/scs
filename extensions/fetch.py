from browser import window, aio
import json as py_json

class FetchError(RuntimeError):
    pass

def _convert_js(js_data):
    try:
        json_str = window.JSON.stringify(js_data)
        try:
            js_obj = window.JSON.parse(json_str)
            return py_json.loads(window.JSON.stringify(js_obj))
        except:
            return py_json.loads(json_str)
    except Exception:
        return js_data

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
    async def json(self):
        js_data = await self._js.json()
        return js_data
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
        # Fallback to aio.fetch
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
    return _convert_js(js_data)

async def fetch_text(url):
    resp = await fetch(url)
    if not resp.ok:
        raise FetchError(f"HTTP {resp.status}")
    return await resp.text()
