from browser import window
import json as py_json

class FetchError(RuntimeError):
    pass

class FetchResponse:
    def __init__(self, js_response):
        self._js = js_response
        self.ok = bool(js_response.ok)
        self.status = int(js_response.status)
        try:
            self.statusText = str(js_response.statusText)
        except:
            self.statusText = ""
    async def json(self):
        # Old working: return JS data directly, no conversion - let app convert
        js_data = await self._js.json()
        return js_data
    async def text(self):
        return await self._js.text()

async def fetch(url, method="GET", headers=None, body=None):
    opts = {"method": method}
    if headers:
        opts["headers"] = headers
    if body != None:
        opts["body"] = body
    js_resp = await window.fetch(url, opts)
    return FetchResponse(js_resp)

async def fetch_json(url):
    resp = await fetch(url)
    if not resp.ok:
        raise FetchError(f"HTTP {resp.status}")
    js_data = await resp.json()
    # Convert here with one-shot
    try:
        return py_json.loads(window.JSON.stringify(js_data))
    except:
        # Fallback to js_data if conversion fails
        return js_data

async def fetch_text(url):
    resp = await fetch(url)
    if not resp.ok:
        raise FetchError(f"HTTP {resp.status}")
    return await resp.text()
