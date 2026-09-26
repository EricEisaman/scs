from browser import window
import json as py_json

class FetchError(RuntimeError):
    pass

def _js_to_py(js_obj):
    # Convert JS object to Python without using json.loads to avoid e-15 bug
    try:
        # Try to use JS JSON roundtrip but with manual handling
        # If js_obj is primitive, return directly
        if js_obj == None:
            return None
        t = window.Object.prototype.toString.call(js_obj)
        s = str(t)
        if s == "[object Array]":
            result = []
            length = js_obj.length
            for i in range(length):
                try:
                    result.append(_js_to_py(js_obj[i]))
                except:
                    result.append(None)
            return result
        if s == "[object Object]":
            result = {}
            keys = window.Object.keys(js_obj)
            # keys is JS array
            for k in keys:
                try:
                    # k is JS string, convert to Python str
                    py_k = str(k)
                    py_v = _js_to_py(js_obj[k])
                    result[py_k] = py_v
                except Exception:
                    continue
            return result
        # Primitive
        try:
            # Numbers - handle scientific notation by converting via float(str())
            if isinstance(js_obj, float) or isinstance(js_obj, int):
                return js_obj
            # JS number
            if window.typeof(js_obj) == "number":
                return float(str(js_obj))
            if window.typeof(js_obj) == "string":
                return str(js_obj)
            if window.typeof(js_obj) == "boolean":
                return bool(js_obj)
        except:
            pass
        return js_obj
    except Exception:
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
    if body != None:
        opts["body"] = body
    js_resp = await window.fetch(url, opts)
    return FetchResponse(js_resp)

async def fetch_json(url):
    resp = await fetch(url)
    if not resp.ok:
        txt = await resp.text()
        raise FetchError(f"HTTP {resp.status} {txt[:200]}")
    js_data = await resp.json()
    return _js_to_py(js_data)

async def fetch_text(url):
    resp = await fetch(url)
    if not resp.ok:
        raise FetchError(f"HTTP {resp.status}")
    return await resp.text()
