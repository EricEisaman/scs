# extensions/multiplayer.py
from browser import window, aio
from extensions.fetch import fetch
import json

class CharacterState:
    pass # for import compatibility

class MultiplayerClient:
    def __init__(self, base_url="https://scs-207.onrender.com", environment="level1", environment_name=None, character_name="Player"):
        self.base_url = base_url.rstrip("/")
        self.environment_name = environment_name or environment or "level1"
        self.character_name = character_name
        self.client_id = None
        self.session_id = None
        self.is_synchronizer = False
        # callbacks (BGS pattern)
        self.on_character_state = None
        self.on_item_authority_changed = None

    async def join(self, retries=3):
        # Render free tier cold start = 30-60s
        for attempt in range(retries):
            try:
                resp = await fetch(
                    f"{self.base_url}/api/multiplayer/join",
                    method="POST",
                    headers={"Content-Type": "application/json"},
                    body=json.dumps({
                        "environment_name": self.environment_name,
                        "character_name": self.character_name
                    }),
                    mode="cors"
                )
                if not resp.ok:
                    raise Exception(f"join status {resp.status}")
                data = await resp.json()
                self.client_id = data.get("client_id") or data.get("clientId")
                self.session_id = data.get("session_id") or data.get("sessionId")
                self.is_synchronizer = data.get("is_synchronizer", False)

                # SINGLE SSE connection - use datastar extension
                from extensions.datastar import connect_sse
                connect_sse(f"{self.base_url}/api/multiplayer/stream?sid={self.session_id}")

                print(f"[BGS] joined {self.client_id} sync={self.is_synchronizer}")
                return data
            except Exception as e:
                print(f"[BGS] join attempt {attempt+1}/{retries} failed: {e}")
                if attempt < retries-1:
                    await aio.sleep(2 * (attempt+1))
        raise Exception("join failed after retries")

    async def send_character_state(self, position=None, velocity=None, animationState="idle", facing=1, onGround=True, score=0, **kwargs):
        # Accept your old signature but translate to spec §5.1.1
        if not self.client_id:
            return
        # normalize [x,y] -> [x,y,0]
        pos = position if isinstance(position, (list,tuple)) and len(position)==3 else [position[0], position[1], 0] if position else [0,0,0]
        vel = velocity if isinstance(velocity, (list,tuple)) and len(velocity)==3 else [velocity[0], velocity[1], 0] if velocity else [0,0,0]

        char = {
            "clientId": self.client_id,
            "characterModelId": kwargs.get("characterModelId", "platformer_default"),
            "position": pos,
            "rotation": [0,0,0],
            "velocity": vel,
            "animationState": animationState,
            "animationFrame": 0,
            "isJumping": not onGround,
            "isBoosting": False,
            "boostTimeRemaining": 0,
            "timestamp": int(window.Date.now())
        }
        try:
            await fetch(
                f"{self.base_url}/api/multiplayer/character-state",
                method="PATCH",
                headers={
                    "Content-Type": "application/json",
                    "X-Client-ID": self.client_id
                },
                body=json.dumps({
                    "updates": [char],
                    "timestamp": char["timestamp"]
                }),
                mode="cors"
            )
        except Exception as e:
            print(f"[BGS] char-state PATCH error {e}")

    async def leave(self):
        from extensions.datastar import disconnect
        disconnect()
        if self.client_id:
            try:
                await fetch(f"{self.base_url}/api/multiplayer/leave",
                    method="POST", headers={"X-Client-ID": self.client_id}, mode="cors")
            except: pass