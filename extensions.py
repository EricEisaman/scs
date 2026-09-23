# extensions.py - Root shim for Brython compatibility
# This file exists to make `import extensions` succeed when Brython
# tries ./extensions.py before ./extensions/__init__.py
# It implements the full fetch API (Model-only, strict MVC) and
# injects `extensions.fetch` into sys.modules so that
# `from extensions.fetch import fetch_json` works even if the
# package folder fails to load.
#
# Strict MVC: No scs import, no drawing, pure data layer.
# Browser Fetch alignment: mirrors window.fetch
# Brython agreement: uses window.fetch + aio.fetch, async/await

from browser import window, aio
import json as _pyjson
import sys
import types

class FetchError(Exception):
    def __init__(self, message, status=None, response=None):
        super().__init__(message)
        self.status = status
        self.response = response

class FetchResponse:
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
        if self._aio_data is not None:
            if isinstance(self._aio_data, (dict, list)):
                return self._aio_data
            try:
                return _pyjson.loads(self._aio_data)
            except:
                pass
        try:
            result = await self._js.json()
            return result
        except Exception as e:
            try:
                txt = await self._js.text()
                return _pyjson.loads(txt)
            except Exception:
                raise FetchError(f"Failed to parse JSON: {e}", status=self.status, response=self)

    async def text(self):
        if self._aio_data is not None and isinstance(self._aio_data, str):
            return self._aio_data
        try:
            return await self._js.text()
        except Exception as e:
            if self._aio_data is not None:
                return str(self._aio_data)
            raise FetchError(f"Failed to read text: {e}", status=self.status, response=self)

    async def blob(self):
        try:
            if hasattr(self._js, 'blob'):
                return await self._js.blob()
        except:
            pass
        return await self.text()

    async def arrayBuffer(self):
        try:
            if hasattr(self._js, 'arrayBuffer'):
                return await self._js.arrayBuffer()
        except:
            pass
        return await self.text()

async def fetch(url, method='GET', headers=None, body=None, mode='cors', credentials=None, cache=None):
    init = {}
    init['method'] = method
    if headers is not None:
        init['headers'] = headers
    if body is not None:
        if isinstance(body, (dict, list)):
            try:
                init['body'] = _pyjson.dumps(body)
                if headers is None or 'Content-Type' not in str(headers):
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
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
    if check_ok and not resp.ok:
        raise FetchError(f"HTTP {resp.status} {resp.statusText} for {url}", status=resp.status, response=resp)
    return await resp.json()

async def fetch_text(url, method='GET', headers=None, body=None, mode='cors', check_ok=True):
    resp = await fetch(url, method=method, headers=headers, body=body, mode=mode)
    if check_ok and not resp.ok:
        raise FetchError(f"HTTP {resp.status} {resp.statusText} for {url}", status=resp.status, response=resp)
    return await resp.text()

def run(coro):
    return aio.run(coro)

__all__ = ['fetch', 'fetch_json', 'fetch_text', 'FetchResponse', 'FetchError', 'run']

# --- Make `extensions.fetch` importable even when only this file exists ---
# Create a submodule object for extensions.fetch that points to this module's exports
try:
    # Create module object for extensions.fetch
    fetch_submod = types.ModuleType('extensions.fetch')
    fetch_submod.fetch = fetch
    fetch_submod.fetch_json = fetch_json
    fetch_submod.fetch_text = fetch_text
    fetch_submod.FetchResponse = FetchResponse
    fetch_submod.FetchError = FetchError
    fetch_submod.run = run
    fetch_submod.__all__ = __all__
    # Register it so `from extensions.fetch import ...` finds it without needing extensions/fetch.py
    sys.modules['extensions.fetch'] = fetch_submod
    # Also ensure `extensions` package points to this file's path for submodule search
    try:
        __path__ = ['extensions']
    except:
        pass
except Exception as e:
    # If types.ModuleType not available in Brython, fallback
    pass
