from browser import window
import json as py_json

class FetchError(RuntimeError):
    pass

def _is_null_js(js_obj):
    try:
        if js_obj is None:
            return True
    except:
        pass
    try:
        return bool(window.JSON.stringify(js_obj) == "null")
    except:
        return False

def _js_to_py(js_obj):
    try:
        if _is_null_js(js_obj):
            return None
        try:
            type_str = window.typeof(js_obj)
        except:
            type_str = ""
        if type_str == "number":
            return float(str(js_obj))
        if type_str == "string":
            return str(js_obj)
        if type_str == "boolean":
            return bool(js_obj)
        try:
            json_str = window.JSON.stringify(js_obj)
            return py_json.loads(json_str)
        except Exception:
            try:
                if hasattr(js_obj, 'length'):
                    length = int(js_obj.length)
                    result = []
                    for i in range(length):
                        try:
                            result.append(_js_to_py(js_obj[i]))
                        except:
                            result.append(None)
                    return result
                keys = window.Object.keys(js_obj)
                result = {}
                for idx in range(int(keys.length)):
                    try:
                        k = keys[idx]
                        result[str(k)] = _js_to_py(js_obj[k])
                    except:
                        continue
                return result
            except:
                pass
        return js_obj
    except Exception:
        return None

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
