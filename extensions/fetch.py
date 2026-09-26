
from browser import window, aio
import json as py_json

class FetchError(RuntimeError):
    pass

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
        try:
            self.statusText = str(js_response.statusText)
        except:
            self.statusText = ""

    async def json(self):
        js_data = await self._js.json()
        return js_data

    async def text(self):
        return await self._js.text()

async def fetch(url, method="GET", headers=None, body=None, mode="cors", credentials=None, cache=None):
    opts = {"method": method, "mode": mode}
    if headers is not None:
        opts["headers"] = headers
    if body is not None:
        try:
            if isinstance(body, dict):
                import json as _j
                opts["body"] = _j.dumps(body)
            else:
                opts["body"] = body
        except:
            opts["body"] = body
    if credentials is not None:
        opts["credentials"] = credentials
    if cache is not None:
        opts["cache"] = cache

    try:
        # PRIMARY: window.fetch - this is what Sage-ec/scs uses and what you asked for
        js_resp = await window.fetch(url, opts)
        return FetchResponse(js_resp)
    except Exception as e1:
        try:
            window.console.warn("[extensions.fetch] window.fetch failed, trying aio.fetch", str(e1))
        except:
            pass
        try:
            js_resp = await aio.fetch(url, opts)
            return FetchResponse(js_resp)
        except Exception as e2:
            try:
                window.console.error("[extensions.fetch] both fetches failed", str(e1), str(e2))
            except:
                pass
            raise FetchError(f"fetch failed for {url}: {e1} / {e2}")

async def fetch_json(url, method="GET", headers=None, body=None, mode="cors"):
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
    if not resp.ok:
        try:
            txt = await resp.text()
        except:
            txt = ""
        raise FetchError(f"HTTP {resp.status} {txt[:200]}")
    js_data = await resp.json()
    try:
        # Original Sage-ec pattern: stringify then parse
        json_str = window.JSON.stringify(js_data)
        return py_json.loads(json_str)
    except Exception as conv_e:
        # Fallback for e-15 or JS objects that don't stringify cleanly
        try:
            window.console.warn("[fetch_json] conversion failed, returning raw", str(conv_e))
        except:
            pass
        return js_data

async def fetch_text(url, method="GET", headers=None, body=None, mode="cors"):
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
    if not resp.ok:
        raise FetchError(f"HTTP {resp.status}")
    return await resp.text()
