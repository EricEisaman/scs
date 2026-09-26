from browser import aio
import json as py_json

class FetchError(RuntimeError):
    pass

class FetchResponse:
    def __init__(self, aio_response):
        self._resp = aio_response
        try:
            self.ok = bool(aio_response.ok)
        except:
            try:
                self.ok = 200 <= int(aio_response.status) < 300
            except:
                self.ok = True
        try:
            self.status = int(aio_response.status)
        except:
            self.status = 200
        try:
            self.statusText = str(aio_response.statusText)
        except:
            self.statusText = ""

    async def json(self):
        try:
            return await self._resp.json()
        except:
            txt = await self._resp.text()
            try:
                return py_json.loads(txt)
            except:
                return txt

    async def text(self):
        return await self._resp.text()

async def fetch(url, method="GET", headers=None, body=None, mode="cors", credentials=None, cache=None):
    opts = {}
    if method is not None:
        opts["method"] = method
    if headers is not None:
        opts["headers"] = headers
    if body is not None:
        if isinstance(body, dict):
            opts["data"] = py_json.dumps(body)
        else:
            opts["data"] = body
    try:
        resp = await aio.fetch(url, **opts)
        return FetchResponse(resp)
    except Exception as e:
        raise FetchError(f"aio.fetch failed for {url}: {e}")

async def fetch_json(url, method="GET", headers=None, body=None, mode="cors"):
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
    if not resp.ok:
        try:
            txt = await resp.text()
        except:
            txt = ""
        raise FetchError(f"HTTP {resp.status} {txt[:200]}")
    data = await resp.json()
    return data

async def fetch_text(url, method="GET", headers=None, body=None, mode="cors"):
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
    if not resp.ok:
        raise FetchError(f"HTTP {resp.status}")
    return await resp.text()
