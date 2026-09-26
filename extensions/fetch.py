from browser import window
import json as py_json

class FetchError(RuntimeError):
    pass

class FetchResponse:
    def __init__(self, js_response):
        self._js = js_response
        self.ok = bool(js_response.ok)
        self.status = int(js_response.status)
        try:
            self.statusText = str(js_response.statusText)
        except Exception:
            self.statusText = ""

    async def json(self):
        js_value = await self._js.json()
        try:
            # One-shot Python-native conversion at network boundary
            return py_json.loads(window.JSON.stringify(js_value))
        except Exception as exc:
            try:
                window.console.error("[fetch] response JSON conversion failed", exc)
            except Exception:
                pass
            return js_value

    async def text(self):
        return await self._js.text()

async def fetch(url, method="GET", headers=None, body=None):
    # Brython: Python dict passed to JS is auto-converted to JS object
    options = {"method": method}
    if headers is not None:
        options["headers"] = headers
    if body is not None:
        options["body"] = body
    js_response = await window.fetch(url, options)
    return FetchResponse(js_response)

async def fetch_json(url):
    response = await fetch(url)
    if not response.ok:
        raise FetchError("fetch_json HTTP " + str(response.status) + " " + response.statusText)
    return await response.json()

async def fetch_text(url):
    response = await fetch(url)
    if not response.ok:
        raise FetchError("fetch_text HTTP " + str(response.status) + " " + response.statusText)
    return await response.text()
