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


class FetchResponse:
    """
    Wrapper around browser's Response object.
    Mirrors the Fetch API: https://developer.mozilla.org/en-US/docs/Web/API/Response
    """
    def __init__(self, js_response):
        # js_response is the JS Response from window.fetch or aio.fetch
        self._js = js_response
        # Standard Fetch API attributes
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
        # For aio.fetch compatibility, data may be in .data
        self._aio_data = getattr(js_response, 'data', None)

    async def json(self):
        """
        Async parse as JSON. Mirrors Response.json()
        Returns Python dict/list.
        """
        # If this came from aio.fetch and already has data, try that
        if self._aio_data is not None:
            # aio.fetch may already have parsed data
            if isinstance(self._aio_data, (dict, list)):
                return self._aio_data
            try:
                return _pyjson.loads(self._aio_data)
            except:
                pass

        # Standard browser fetch path: await self._js.json()
        try:
            # In Brython, await js_response.json() returns Python object
            result = await self._js.json()
            return result
        except Exception as e:
            # Fallback: try text then parse
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
            # aio.fetch may have data as text
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

    Args:
        url (str): URL to fetch
        method (str): HTTP method, default 'GET'
        headers (dict): Optional headers dict, e.g. {'Content-Type': 'application/json'}
        body (str|dict): Optional body. If dict, will be JSON-stringified.
        mode (str): CORS mode, default 'cors' - 'cors', 'no-cors', 'same-origin'
        credentials (str): Optional 'omit', 'same-origin', 'include'
        cache (str): Optional cache mode

    Returns:
        FetchResponse: Response wrapper with .ok, .status, .json(), .text()

    Browser alignment:
        Mirrors window.fetch(url, {method, headers, body, mode, credentials, cache})

    Brython agreement:
        Uses window.fetch (JS Promise) which Brython can await, with fallback to aio.fetch
    """
    # Prepare init dict for window.fetch
    init = {}
    init['method'] = method
    if headers is not None:
        init['headers'] = headers
    if body is not None:
        # If body is dict/list, JSON stringify for browser fetch
        if isinstance(body, (dict, list)):
            try:
                init['body'] = _pyjson.dumps(body)
                # Ensure content-type if not set
                if headers is None or 'Content-Type' not in headers and 'content-type' not in str(headers).lower():
                    if 'headers' not in init:
                        init['headers'] = {}
                    # Don't mutate if headers is JS object
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

    # Primary path: window.fetch for strict browser alignment
    try:
        # window.fetch returns a Promise that Brython can await
        js_response = await window.fetch(url, init)
    except Exception as e1:
        # Fallback: aio.fetch - Brython's own async fetch, more forgiving with Python dicts
        try:
            # aio.fetch signature: aio.fetch(url, method, headers, data)
            # data is body
            data = body
            if isinstance(body, (dict, list)):
                data = _pyjson.dumps(body)
            js_response = await aio.fetch(url, method=method, headers=headers, data=data)
        except Exception as e2:
            # Both failed, raise network error
            raise FetchError(f"Fetch failed for {url}: {e1} / fallback {e2}", response=None)

    return FetchResponse(js_response)


async def fetch_json(url, method='GET', headers=None, body=None, mode='cors', check_ok=True):
    """
    Convenience: fetch and parse as JSON in one await.

    Args:
        url: URL to fetch
        method, headers, body, mode: passed to fetch()
        check_ok: if True, raises FetchError if response.ok is False

    Returns:
        dict|list: Parsed JSON

    Example:
        poem = await fetch_json('https://poetrydb.org/random')
    """
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
    if check_ok and not resp.ok:
        raise FetchError(f"HTTP {resp.status} {resp.statusText} for {url}", status=resp.status, response=resp)
    return await resp.json()


async def fetch_text(url, method='GET', headers=None, body=None, mode='cors', check_ok=True):
    """
    Convenience: fetch and parse as text in one await.

    Args:
        url: URL to fetch
        method, headers, body, mode: passed to fetch()
        check_ok: if True, raises FetchError if response.ok is False

    Returns:
        str: Response text
    """
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
    if check_ok and not resp.ok:
        raise FetchError(f"HTTP {resp.status} {resp.statusText} for {url}", status=resp.status, response=resp)
    return await resp.text()


# For apps that need to run async from sync onAppStart, re-export aio.run helper
def run(coro):
    """
    Helper to run an async coroutine from sync context.
    Wraps browser.aio.run.

    Example:
        from extensions.fetch import run
        run(load_poem(app))
    """
    return aio.run(coro)


__all__ = ['fetch', 'fetch_json', 'fetch_text', 'FetchResponse', 'FetchError', 'run']
