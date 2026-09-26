from browser import aio
import json as py_json

class FetchError(RuntimeError):
    pass

class FetchResponse:
    def __init__(self, aio_response):
        self._resp = aio_response
        # aio response has .status and .data
        try:
            self.status = int(aio_response.status)
        except:
            self.status = 200
        try:
            self.ok = 200 <= self.status < 300
        except:
            self.ok = True
        try:
            self.statusText = str(aio_response.statusText) if hasattr(aio_response, 'statusText') else ""
        except:
            self.statusText = ""
        # data may be string or dict
        self._data = getattr(aio_response, 'data', None)
        self._text = getattr(aio_response, 'text', None)

    async def json(self):
        # aio response data may already be parsed or string
        d = self._data
        if d is None:
            d = self._text
        if isinstance(d, dict):
            return d
        if isinstance(d, str):
            try:
                return py_json.loads(d)
            except:
                return d
        # If response itself has json method (fallback)
        try:
            return await self._resp.json()
        except:
            pass
        return d

    async def text(self):
        d = self._data
        if d is None:
            d = self._text
        if isinstance(d, str):
            return d
        if isinstance(d, dict):
            try:
                return py_json.dumps(d)
            except:
                return str(d)
        try:
            t = await self._resp.text()
            return t
        except:
            return str(d) if d is not None else ""

async def fetch(url, method="GET", headers=None, body=None, data=None, mode="cors", credentials=None, cache=None):
    # Use aio.get / post / ajax - aio.fetch is module not callable, causes "module object not callable"
    b = body if body is not None else data
    # Normalize body to string if dict
    if isinstance(b, dict):
        b = py_json.dumps(b)
    opts_headers = headers or {}
    try:
        m = method.upper() if method else "GET"
        if m == "GET":
            resp = await aio.get(url, headers=opts_headers)
        elif m == "POST":
            resp = await aio.post(url, headers=opts_headers, data=b)
        elif m == "PATCH":
            # aio has no patch, use ajax
            try:
                resp = await aio.ajax("PATCH", url, headers=opts_headers, data=b)
            except AttributeError:
                # fallback: use aio.post with method override via ajax
                from browser import ajax
                # create future manually? For now try aio.get with custom
                # Use ajax object wrapped
                import asyncio as _asyncio
                # Simple fallback using aio.post and hope server handles X-HTTP-Method-Override
                resp = await aio.post(url, headers=opts_headers, data=b)
        elif m == "PUT":
            resp = await aio.ajax("PUT", url, headers=opts_headers, data=b) if hasattr(aio, 'ajax') else await aio.post(url, headers=opts_headers, data=b)
        elif m == "DELETE":
            resp = await aio.ajax("DELETE", url, headers=opts_headers) if hasattr(aio, 'ajax') else await aio.get(url, headers=opts_headers)
        else:
            # generic ajax
            if hasattr(aio, 'ajax'):
                resp = await aio.ajax(m, url, headers=opts_headers, data=b)
            else:
                resp = await aio.get(url, headers=opts_headers)
        return FetchResponse(resp)
    except Exception as e:
        raise FetchError(f"aio {m} failed for {url}: {e}")

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
