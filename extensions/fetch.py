from browser import window
import json as py_json

def _js_to_py_recursive(js_val, depth=0):
    if depth > 25:
        return None
    try:
        if js_val is None:
            return None
        if isinstance(js_val, (str, int, float, bool)):
            return js_val
        # Check if JS array
        try:
            if window.Array.isArray(js_val):
                result = []
                for i in range(int(js_val.length)):
                    try:
                        result.append(_js_to_py_recursive(js_val[i], depth+1))
                    except:
                        continue
                return result
        except:
            pass
        # Check if dict-like
        try:
            keys = window.Object.keys(js_val)
            # If no keys, try stringify
            if len(keys) == 0:
                try:
                    # Try JSON stringify parse for primitives
                    return py_json.loads(window.JSON.stringify(js_val))
                except:
                    return js_val
            result = {}
            for i in range(len(keys)):
                k = keys[i]
                try:
                    result[k] = _js_to_py_recursive(js_val[k], depth+1)
                except:
                    continue
            return result
        except:
            try:
                return py_json.loads(window.JSON.stringify(js_val))
            except:
                return js_val
    except:
        return None

class FetchResponse:
    def __init__(self, js_resp):
        self._js = js_resp
        self.ok = bool(js_resp.ok)
        self.status = int(js_resp.status)
        try:
            self.statusText = str(js_resp.statusText)
        except:
            self.statusText = ""
        self.headers = {}
    async def json(self):
        js_data = await self._js.json()
        # Use recursive converter that handles arrays correctly
        try:
            result = _js_to_py_recursive(js_data)
            if result is not None:
                return result
        except:
            pass
        # Fallback: try direct Object.keys for dict
        try:
            keys = window.Object.keys(js_data)
            # If it's array-like with numeric keys, build list
            try:
                if window.Array.isArray(js_data):
                    lst = []
                    for i in range(int(js_data.length)):
                        try:
                            lst.append(_js_to_py_recursive(js_data[i], 1))
                        except:
                            lst.append(js_data[i])
                    return lst
            except:
                pass
            result = {}
            for i in range(len(keys)):
                k = keys[i]
                try:
                    result[k] = _js_to_py_recursive(js_data[k], 1)
                except:
                    try:
                        result[k] = js_data[k]
                    except:
                        continue
            return result
        except:
            try:
                return py_json.loads(window.JSON.stringify(js_data))
            except:
                return js_data
    async def text(self):
        return await self._js.text()

async def fetch(url, method="GET", headers=None, body=None, mode=None):
    opts = {"method": method}
    if headers:
        opts["headers"] = headers
    if body is not None:
        if isinstance(body, (dict, list)):
            opts["body"] = window.JSON.stringify(body)
        else:
            opts["body"] = body
    if mode:
        opts["mode"] = mode
    try:
        js_opts = window.JSON.parse(window.JSON.stringify(opts))
    except:
        js_opts = opts
    js_resp = await window.fetch(url, js_opts)
    return FetchResponse(js_resp)

async def fetch_json(url, **kw):
    resp = await fetch(url, **kw)
    if not resp.ok:
        raise RuntimeError("fetch_json HTTP " + str(resp.status))
    return await resp.json()

async def fetch_text(url, **kw):
    resp = await fetch(url, **kw)
    if not resp.ok:
        raise RuntimeError("fetch_text HTTP " + str(resp.status))
    return await resp.text()

class FetchError(RuntimeError):
    pass
