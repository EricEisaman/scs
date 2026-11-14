# extensions/fetch.py
# SCS Extensions - Async Fetch (Model Layer)
# =========================================
# Strict MVC adherence:
#   - This module is PURE Model. It fetches data, never touches View.
#   - No import of scs, App, canvas, draw*, or any rendering code.
#   - No reference to redrawAll, onStep, or app.* state.
#   - Apps (Controller) call these functions and store results in app.*
#     View (redrawAll) then reads app.* and renders.
#
# Browser Fetch Alignment:
#   - API mirrors window.fetch(url, init) per https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API
#   - init supports: method, headers, body, mode, credentials, cache
#   - Returns FetchResponse with .ok, .status, .statusText, .headers
#   - And async methods .json(), .text(), .blob(), .arrayBuffer()
#
# Brython Async Agreement:
#   - All public functions are async def and must be awaited
#   - Uses browser.aio.fetch and window.fetch which return awaitable Promises
#   - Run via aio.run() or await inside another async def
#   - Example:
#       from browser import aio
#       from extensions.fetch import fetch_json
#       async def load(app):
#           app.poem = await fetch_json('https://poetrydb.org/random')
#       aio.run(load(app))

from browser import window, aio
import json as _pyjson

class FetchError(Exception):
    """Raised on network failure or non-ok response when check_ok=True"""
    def __init__(self, message, status=None, response=None):
        super().__init__(message)
        self.status = status
        self.response = response


def _js_to_py(obj):
    """JSObject / JS array -> real Python dict/list, RECURSIVELY.

    Live bug, even with the first fix:
      fetch_json returned type=<class 'list'>
      data preview=[<Javascript object: [object Object]>]
      data type=<class 'JSObject'>
    Brython converts the JS *array* to a Python list, but leaves its
    elements as JSObjects. The first fix did:
      if isinstance(obj, (dict, list, ...)): return obj
    so it returned the list untouched and the nested JSObject survived.

    Fix: ALWAYS recurse into lists/dicts, even when they are already
    Python. And re-recurse after to_py(), because to_py() can also
    return a list of JSObjects.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_js_to_py(x) for x in obj]
    if isinstance(obj, dict):
        return {_js_to_py(k): _js_to_py(v) for k, v in obj.items()}
    try:
        to_py = getattr(obj, 'to_py', None)
        if callable(to_py):
            converted = to_py()
            if converted is not obj:
                return _js_to_py(converted)
    except Exception:
        pass
    try:
        txt = window.JSON.stringify(obj)
        return _js_to_py(_pyjson.loads(str(txt)))
    except Exception:
        pass
    try:
        return _js_to_py(dict(obj))
    except Exception:
        pass
    try:
        return _js_to_py(list(obj))
    except Exception:
        pass
    return obj


class FetchResponse:
    """
    Wrapper around browser's Response object.
    Mirrors the Fetch API: https://developer.mozilla.org/en-US/docs/Web/API/Response
    """
    def __init__(self, js_response):
        self._js = js_response
        try:
            self.ok = bool(getattr(js_response, 'ok', True))
        except:
            self.ok = True
        try:
            self.status = int(getattr(js_response, 'status', 200))
        except:
            self.status = 200
        try:
            self.statusText = str(getattr(js_response, 'statusText', ''))
        except:
            self.statusText = ''
        try:
            self.headers = getattr(js_response, 'headers', {})
        except:
            self.headers = {}
        self._aio_data = getattr(js_response, 'data', None)

    async def json(self):
        """
        Async parse as JSON. Mirrors Response.json()
        Returns Python dict/list.
        """
        if self._aio_data is not None:
            if isinstance(self._aio_data, (dict, list)):
                return _js_to_py(self._aio_data)
            try:
                return _pyjson.loads(self._aio_data)
            except:
                pass
            return _js_to_py(self._aio_data)
        try:
            result = await self._js.json()
            return _js_to_py(result)
        except Exception as e:
            try:
                txt = await self._js.text()
                return _pyjson.loads(txt)
            except Exception:
                raise FetchError(f"Failed to parse JSON: {e}", status=self.status, response=self)

    async def text(self):
        """Async parse as text. Mirrors Response.text()"""
        if self._aio_data is not None and isinstance(self._aio_data, str):
            return self._aio_data
        try:
            return await self._js.text()
        except Exception as e:
            if self._aio_data is not None:
                return str(self._aio_data)
            raise FetchError(f"Failed to read text: {e}", status=self.status, response=self)

    async def blob(self):
        """Async parse as blob. Mirrors Response.blob()"""
        try:
            if hasattr(self._js, 'blob'):
                return await self._js.blob()
        except:
            pass
        return await self.text()

    async def arrayBuffer(self):
        """Async parse as arrayBuffer. Mirrors Response.arrayBuffer()"""
        try:
            if hasattr(self._js, 'arrayBuffer'):
                return await self._js.arrayBuffer()
        except:
            pass
        return await self.text()


async def fetch(url, method='GET', headers=None, body=None, mode='cors', credentials=None, cache=None):
    """
    Async fetch, aligned to browser fetch API.
    """
    init = {}
    init['method'] = method
    if headers is not None:
        init['headers'] = headers
    if body is not None:
        if isinstance(body, (dict, list)):
            try:
                init['body'] = _pyjson.dumps(body)
                if headers is None or 'Content-Type' not in headers and 'content-type' not in str(headers).lower():
                    if 'headers' not in init:
                        init['headers'] = {}
                    try:
                        init['headers']['Content-Type'] = 'application/json'
                    except:
                        pass
            except:
                init['body'] = body
        else:
            init['body'] = body
    if mode is not None:
        init['mode'] = mode
    if credentials is not None:
        init['credentials'] = credentials
    if cache is not None:
        init['cache'] = cache
    js_response = None
    try:
        js_response = await window.fetch(url, init)
    except Exception as e1:
        try:
            data = body
            if isinstance(body, (dict, list)):
                data = _pyjson.dumps(body)
            js_response = await aio.fetch(url, method=method, headers=headers, data=data)
        except Exception as e2:
            raise FetchError(f"Fetch failed for {url}: {e1} / fallback {e2}", response=None)
    return FetchResponse(js_response)


async def fetch_json(url, method='GET', headers=None, body=None, mode='cors', check_ok=True):
    """
    Convenience: fetch and parse as JSON in one await.
    Returns dict|list: Parsed JSON
    """
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
    if check_ok and not resp.ok:
        raise FetchError(f"HTTP {resp.status} {resp.statusText} for {url}", status=resp.status, response=resp)
    return await resp.json()


async def fetch_text(url, method='GET', headers=None, body=None, mode='cors', check_ok=True):
    """
    Convenience: fetch and parse as text in one await.
    Returns str: Response text
    """
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
    if check_ok and not resp.ok:
        raise FetchError(f"HTTP {resp.status} {resp.statusText} for {url}", status=resp.status, response=resp)
    return await resp.text()


def run(coro):
    """
    Helper to run an async coroutine from sync context.
    Wraps browser.aio.run.
    """
    return aio.run(coro)


__all__ = ['fetch', 'fetch_json', 'fetch_text', 'FetchResponse', 'FetchError', 'run']
