
from browser import window

class FetchError(RuntimeError):
    pass

def _js_to_py_simple(js_obj):
    # Avoid window.typeof - use Python isinstance and JS Array check only
    try:
        if js_obj is None:
            return None
    except:
        pass
    try:
        # JS null check
        if window.JSON.stringify(js_obj) == "null":
            return None
    except:
        pass
    # Python primitives already converted by Brython
    if isinstance(js_obj, (str, int, float, bool)):
        return js_obj
    # JS primitives that are still JS objects - convert via str
    try:
        # If it's a JS string, Array.isArray false and not object with keys? 
        # Try to detect number via converting to float
        # Use JS to check: if it's array
        is_arr = False
        try:
            is_arr = bool(window.Array.isArray(js_obj))
        except:
            is_arr = False
        if is_arr:
            res = []
            ln = int(js_obj.length)
            for i in range(ln):
                try:
                    res.append(_js_to_py_simple(js_obj[i]))
                except:
                    res.append(None)
            return res
        # If object, try Object.keys
        try:
            keys = window.Object.keys(js_obj)
            kl = int(keys.length)
            res = {}
            for idx in range(kl):
                k = keys[idx]
                try:
                    res[str(k)] = _js_to_py_simple(js_obj[k])
                except:
                    continue
            return res
        except:
            pass
    except Exception as e:
        try:
            window.console.log("[_js_to_py_simple] error", str(e))
        except:
            pass
    # Fallback: try str conversion for numbers
    try:
        # If it's JS number, str() will give scientific notation which Python float can parse
        s = str(js_obj)
        # Try float
        if s.replace(".","",1).replace("-","",1).replace("e","",1).replace("E","",1).replace("+","",1).isdigit() or "e" in s.lower():
            try:
                return float(s)
            except:
                pass
        return s
    except:
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
