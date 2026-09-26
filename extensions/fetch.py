
from browser import window

class FetchError(RuntimeError):
    pass

def _js_to_py_simple(js_obj):
    try:
        if js_obj is None:
            return None
    except:
        pass
    try:
        if window.JSON.stringify(js_obj) == "null":
            return None
    except:
        pass
    try:
        t = window.typeof(js_obj)
        if t == "number":
            return float(str(js_obj))
        if t == "string":
            return str(js_obj)
        if t == "boolean":
            return bool(js_obj)
    except:
        pass
    try:
        if bool(window.Array.isArray(js_obj)):
            res = []
            for i in range(int(js_obj.length)):
                res.append(_js_to_py_simple(js_obj[i]))
            return res
        if window.typeof(js_obj) == "object":
            keys = window.Object.keys(js_obj)
            res = {}
            for idx in range(int(keys.length)):
                k = keys[idx]
                res[str(k)] = _js_to_py_simple(js_obj[k])
            return res
    except:
        pass
    return js_obj

class FetchResponse:
    def __init__(self, js_response):
        self._js = js_response
        try:
            self.ok = bool(js_response.ok)
        except:
            self.ok = True
        try:
            self.status = int(js_response.status)
        except:
            self.status = 200
    async def json(self):
        js_data = await self._js.json()
        return js_data
    async def text(self):
        return await self._js.text()

async def fetch(url, method="GET", headers=None, body=None):
    opts = {"method": method, "mode": "cors"}
    if headers:
        opts["headers"] = headers
    if body is not None:
        opts["body"] = body
    js_resp = await window.fetch(url, opts)
    return FetchResponse(js_resp)

async def fetch_json(url):
    resp = await fetch(url)
    if not resp.ok:
        txt = await resp.text()
        raise FetchError(f"HTTP {resp.status} {txt[:200]}")
    js_data = await resp.json()
    return _js_to_py_simple(js_data)

async def fetch_text(url):
    resp = await fetch(url)
    if not resp.ok:
        raise FetchError(f"HTTP {resp.status}")
    return await resp.text()
