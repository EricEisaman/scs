from browser import window
import json as py_json

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
        try:
            keys = window.Object.keys(js_data)
            result = {}
            for i in range(len(keys)):
                k = keys[i]
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
