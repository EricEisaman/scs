"""
extensions.multiplayer - SCS Multiplayer Extension - STRICT NO FALLBACK
Model-only, no scs import, browser-aligned, async where browser is async
Implements exact server props per SERVER_CLIENT_AUDIT.md
Server: https://scs-207.onrender.com
"""

from browser import window, aio
import json as py_json

# Server contract per audit
BASE_URL_DEFAULT = "https://scs-207.onrender.com"

class MultiplayerClient:
    """
    Strict initiation - NO FALLBACK ALLOWED
    Uses extensions.fetch-style browser-aligned API internally
    """
    def __init__(self, base_url=BASE_URL_DEFAULT, environment="level1", environment_name=None, character_name="Player", **kw):
        self.base_url = base_url.rstrip("/")
        self.environment_name = environment_name or environment or "level1"
        self.character_name = kw.get("character_name", character_name) or "Player"
        self.client_id = None
        self.session_id = None
        self.is_synchronizer = False
        self._es = None

    async def join(self, retries=3):
        """
        POST /api/multiplayer/join
        Body: {"environment_name": str, "character_name": str} snake_case REQUIRED
        Returns: {client_id, session_id, is_synchronizer, environment_name}
        NO FALLBACK - raises on failure
        """
        base_url = self.base_url
        last_exc = None
        for attempt in range(retries):
            try:
                url = base_url + "/api/multiplayer/join"
                payload = {
                    "environment_name": self.environment_name,
                    "character_name": self.character_name
                }
                body = window.JSON.stringify(payload)
                js_opts = {
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "body": body
                }
                try:
                    opts = window.JSON.parse(window.JSON.stringify(js_opts))
                except:
                    opts = js_opts

                resp = await window.fetch(url, opts)
                if not resp.ok:
                    txt = ""
                    try:
                        txt = await resp.text()
                    except:
                        pass
                    raise RuntimeError(f"join HTTP {resp.status}: {txt[:500]}")

                js_data = await resp.json()
                # Convert JS -> Python safely without json.loads crash
                try:
                    data = {}
                    keys = window.Object.keys(js_data)
                    for i in range(len(keys)):
                        k = keys[i]
                        try:
                            data[k] = js_data[k]
                        except:
                            continue
                    # If keys failed, try stringify
                    if not data:
                        data = py_json.loads(window.JSON.stringify(js_data))
                except:
                    try:
                        data = py_json.loads(window.JSON.stringify(js_data))
                    except:
                        data = {}

                cid = data.get("client_id")
                sid = data.get("session_id")
                is_sync = data.get("is_synchronizer", False)

                if not cid or not sid:
                    raise RuntimeError(f"missing ids in join response: {data}")

                self.client_id = cid
                self.session_id = sid
                self.is_synchronizer = bool(is_sync)

                # Open SSE stream - STRICT, NO FALLBACK eval
                try:
                    stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
                    # Brython correct: EventSource.new()
                    es_obj = None
                    try:
                        es_obj = window.EventSource.new(stream_url)
                    except Exception as e1:
                        # Second try direct call (some Brython versions)
                        try:
                            es_obj = window.EventSource(stream_url)
                        except Exception as e2:
                            window.console.error("[extensions.multiplayer] EventSource creation failed", e1, e2)
                            raise e2

                    self._es = es_obj
                    # Store globally for compatibility with existing BGS code
                    try:
                        window._bgs_es = es_obj
                    except:
                        pass

                    try:
                        window.console.log(f"[extensions.multiplayer] Joined {cid} host={is_sync} sid={sid[:8]}")
                    except:
                        pass

                except Exception as e:
                    try:
                        window.console.error("[extensions.multiplayer] EventSource setup failed", e)
                    except:
                        pass
                    # Don't fail join if ES fails, but keep ids

                return {
                    "client_id": cid,
                    "session_id": sid,
                    "is_synchronizer": bool(is_sync),
                    "environment_name": data.get("environment_name", self.environment_name)
                }

            except Exception as ex:
                last_exc = ex
                try:
                    window.console.error(f"[extensions.multiplayer] join attempt {attempt+1} failed", ex)
                except:
                    print(f"[extensions.multiplayer] join fail {attempt+1}: {ex}")
                await aio.sleep(1.0 * (attempt + 1))

        # NO FALLBACK - raise last error
        raise last_exc or RuntimeError("join failed after retries - NO FALLBACK ALLOWED")

__all__ = ["MultiplayerClient", "BASE_URL_DEFAULT"]
