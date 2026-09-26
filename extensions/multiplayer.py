from browser import window, aio
import json

class CharacterState:
    pass  # for import compatibility - wire shape is dict per MULTIPLAYER_SYNCH.md §5.1.1

class MultiplayerClient:
    def __init__(self, base_url="https://scs-207.onrender.com", environment="level1", environment_name=None, character_name="Player", **kw):
        self.base_url = base_url.rstrip("/")
        self.environment_name = environment_name or environment or kw.get("environment") or "level1"
        self.character_name = kw.get("character_name", character_name) or character_name or "Player"
        self.client_id = None
        self.session_id = None
        self.is_synchronizer = False
        # callbacks - BGS pattern
        self.on_character_state = None
        self.on_item_authority_changed = None
        self._es = None

    async def join(self, retries=3):
        # Render free tier cold start = 30-60s
        for attempt in range(retries):
            try:
                url = f"{self.base_url}/api/multiplayer/join"
                payload = {"environment_name": self.environment_name, "character_name": self.character_name}
                body = window.JSON.stringify(payload)
                print(f"[mp] join {url} env={self.environment_name} attempt={attempt+1}")
                resp = await window.fetch(url, {
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "body": body,
                    "mode": "cors"
                })
                if not resp.ok:
                    txt = ""
                    try:
                        txt = await resp.text()
                    except:
                        pass
                    raise Exception(f"HTTP {resp.status} {txt}")
                js_data = await resp.json()
                data = json.loads(window.JSON.stringify(js_data))
                self.client_id = data.get("client_id")
                self.session_id = data.get("session_id")
                self.is_synchronizer = data.get("is_synchronizer", False)
                # SSE - Datastar best practice: ONE EventSource via extensions.datastar
                stream_url = f"{self.base_url}/api/multiplayer/stream?sid={self.session_id}"
                try:
                    import extensions.datastar as ds
                    ds.connect_sse(stream_url)
                except Exception as ex:
                    print(f"[mp] datastar.connect_sse failed {ex}, using direct EventSource")
                    self._es = window.EventSource.new(stream_url)
                    window._scs_es = self._es
                    def _on_sig(evt):
                        raw = evt.data if isinstance(evt.data, str) else ""
                        if raw.startswith("signals "):
                            raw = raw[8:]
                        try:
                            d = json.loads(raw)
                            try:
                                import extensions.datastar as ds2
                                ds2._signals.update(d)
                            except:
                                pass
                            # callbacks
                            if "character-state-update" in d and self.on_character_state:
                                self.on_character_state(d.get("character-state-update", {}).get("updates", []) or d.get("updates", []))
                        except Exception as pe:
                            print(f"[mp] signal parse fail {pe}")
                    self._es.addEventListener("datastar-patch-signals", _on_sig)
                    self._es.onopen = lambda e: print("[mp] SSE OPEN")
                    self._es.onerror = lambda e: print(f"[mp] SSE ERROR {e}")
                print(f"[mp] Joined client_id={self.client_id} sid={self.session_id} sync={self.is_synchronizer}")
                return data
            except Exception as e:
                import traceback
                print(f"[mp] join attempt {attempt+1} failed: {e}")
                traceback.print_exc()
                await aio.sleep(2*(attempt+1))
        raise Exception("join failed after retries")

    async def send_character_state(self, position, velocity, animationState="idle", onGround=True, **kw):
        if not self.client_id:
            return
        try:
            pos = [float(position[0]), float(position[1])]
            vel = [float(velocity[0]), float(velocity[1])]
            char = {
                "clientId": self.client_id,
                "characterModelId": "platformer-default",
                "position": pos,
                "velocity": vel,
                "animationState": animationState,
                "animationFrame": kw.get("animationFrame", 0),
                "isJumping": not onGround,
                "facing": int(kw.get("facing", 1)),
                "score": int(kw.get("score", 0)),
                "onGround": bool(onGround),
                "timestamp": int(window.Date.now())
            }
            url = f"{self.base_url}/api/multiplayer/character-state"
            body = window.JSON.stringify({"updates": [char], "timestamp": char["timestamp"]})
            await window.fetch(url, {
                "method": "PATCH",
                "headers": {"Content-Type": "application/json", "X-Client-ID": self.client_id},
                "body": body,
                "mode": "cors"
            })
        except Exception as e:
            print(f"[mp] send_character_state failed {e}")
