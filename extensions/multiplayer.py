from browser import window, aio
import json

# Pre-import datastar at module load, not inside async func (Brython import inside async crashes)
try:
    import extensions.datastar as _ds_mod
    _has_ds = True
except:
    _ds_mod = None
    _has_ds = False

class CharacterState:
    pass  # for import compatibility - wire shape is dict per MULTIPLAYER_SYNCH.md §5.1.1

class MultiplayerError(Exception):
    pass

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
                # SSE - use pre-imported datastar module, not import inside async (Brython crash)
                stream_url = f"{self.base_url}/api/multiplayer/stream?sid={self.session_id}"
                connected = False
                if _has_ds and _ds_mod and hasattr(_ds_mod, 'connect_sse'):
                    try:
                        _ds_mod.connect_sse(stream_url)
                        connected = True
                        print(f"[mp] datastar.connect_sse OK {stream_url}")
                    except Exception as ex:
                        print(f"[mp] datastar.connect_sse failed {ex}, using direct EventSource")
                if not connected:
                    try:
                        self._es = window.EventSource.new(stream_url)
                        window._scs_es = self._es
                        def _on_sig(evt):
                            raw = evt.data if isinstance(evt.data, str) else ""
                            if raw.startswith("signals "):
                                raw = raw[8:]
                            try:
                                d = json.loads(raw)
                                # Update signals dict directly without import
                                if _has_ds and _ds_mod and hasattr(_ds_mod, '_signals'):
                                    try:
                                        _ds_mod._signals.update(d)
                                    except:
                                        pass
                                # Also update window._bgs_signals for BGS
                                try:
                                    if isinstance(d, dict):
                                        for k,v in d.items():
                                            window._bgs_signals[k] = v
                                except:
                                    pass
                            except Exception as pe:
                                print(f"[mp] signal parse fail {pe}")
                        self._es.addEventListener("datastar-patch-signals", _on_sig)
                        self._es.onopen = lambda e: print("[mp] SSE OPEN")
                        self._es.onerror = lambda e: print(f"[mp] SSE ERROR {e}")
                    except Exception as sse_e:
                        print(f"[mp] SSE direct failed {sse_e}")
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
            pos = [position[0], position[1], 0] if len(position)==2 else list(position)
            vel = [velocity[0], velocity[1], 0] if len(velocity)==2 else list(velocity)
            char = {
                "clientId": self.client_id,
                "characterModelId": "platformer_default",
                "position": pos,
                "rotation": [0,0,0],
                "velocity": vel,
                "animationState": animationState,
                "animationFrame": kw.get("animationFrame", 0),
                "isJumping": not onGround,
                "isBoosting": kw.get("isBoosting", False),
                "boostTimeRemaining": kw.get("boostTimeRemaining", 0),
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
