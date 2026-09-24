"""
extensions.multiplayer - Well-designed Python API following BGS-MP-SYNC
For SCS / Brython apps.

Usage:
    from extensions.multiplayer import MultiplayerClient

    client = MultiplayerClient(
        base_url="https://your-backend.onrender.com",
        environment="level1",
        character_name="Player1"
    )

    async def on_character_update(updates):
        for char in updates:
            # char.position, char.velocity, etc.
            pass

    client.on_character_state = on_character_update
    client.on_item_state = lambda updates, collections: ...
    client.on_client_joined = lambda clientId, env, char, total: ...
    client.on_item_authority_changed = lambda instanceId, prev, new, reason: ...

    await client.join()
    # In onStep:
    await client.send_character_state(position=[x,y], velocity=[vx,vy], animationState="run")
"""

from browser import window, aio
import json as _json
import time

class MultiplayerError(Exception):
    pass

class CharacterState:
    def __init__(self, clientId, position=None, velocity=None, animationState="idle", **kwargs):
        self.clientId = clientId
        self.characterModelId = kwargs.get("characterModelId", "platformer-default")
        self.position = position or [0,0]
        self.velocity = velocity or [0,0]
        self.animationState = animationState
        self.animationFrame = kwargs.get("animationFrame", 0.0)
        self.isJumping = kwargs.get("isJumping", False)
        self.facing = kwargs.get("facing", 1)
        self.score = kwargs.get("score", 0)
        self.onGround = kwargs.get("onGround", False)
        self.timestamp = int(time.time()*1000)

    def to_dict(self):
        return {
            "clientId": self.clientId,
            "characterModelId": self.characterModelId,
            "position": self.position,
            "velocity": self.velocity,
            "animationState": self.animationState,
            "animationFrame": self.animationFrame,
            "isJumping": self.isJumping,
            "facing": self.facing,
            "score": self.score,
            "onGround": self.onGround,
            "timestamp": self.timestamp
        }

class ItemInstanceState:
    def __init__(self, instanceId, pos=None, **kwargs):
        self.instanceId = instanceId
        self.itemName = kwargs.get("itemName", "")
        self.pos = pos or [0,0]
        self.rot = kwargs.get("rot", [0,0,0,1])
        self.isCollected = kwargs.get("isCollected", False)
        self.collectedByClientId = kwargs.get("collectedByClientId")
        self.ownerClientId = kwargs.get("ownerClientId")
        self.timestamp = int(time.time()*1000)

class MultiplayerClient:
    """
    High-level client following BGS-MP-SYNC lifecycle:
    1. join() -> POST /api/multiplayer/join
    2. open stream -> GET /api/multiplayer/stream?sid=session_id (SSE via Datastar)
    3. send character-state -> PATCH /api/multiplayer/character-state
    4. claim/release item authority -> PATCH /api/multiplayer/item-authority-claim
    5. send item-state -> PATCH /api/multiplayer/item-state (if resolved owner)
    """

    def __init__(self, base_url: str, environment: str = "level1", character_name: str = "Player", character_model_id: str = "platformer-default"):
        self.base_url = base_url.rstrip("/")
        self.environment = environment
        self.character_name = character_name
        self.character_model_id = character_model_id

        self.client_id: str = None
        self.session_id: str = None
        self.is_synchronizer: bool = False
        self.connected: bool = False

        # Callbacks
        self.on_character_state = None
        self.on_item_state = None
        self.on_client_joined = None
        self.on_client_left = None
        self.on_synchronizer_changed = None
        self.on_item_authority_changed = None
        self.on_env_authority_changed = None

    async def join(self):
        from .fetch import fetch_json
        url = f"{self.base_url}/api/multiplayer/join"
        try:
            res = await fetch_json(url, method="POST", body={
                "environment_name": self.environment,
                "character_name": self.character_name
            })
            self.client_id = res.get("client_id")
            self.session_id = res.get("session_id")
            self.is_synchronizer = res.get("is_synchronizer", False)
            self.connected = True
            # Store for SSE
            window.__SCS_MP_CLIENT_ID = self.client_id
            window.__SCS_MP_SESSION_ID = self.session_id
            window.__SCS_MP_BASE_URL = self.base_url
            return res
        except Exception as e:
            raise MultiplayerError(f"join failed: {e}")

    async def leave(self):
        from .fetch import fetch_json
        if not self.client_id:
            return
        url = f"{self.base_url}/api/multiplayer/leave"
        try:
            await fetch_json(url, method="POST", headers={"X-Client-ID": self.client_id})
            self.connected = False
        except Exception as e:
            print(f"leave error: {e}")

    async def send_character_state(self, position, velocity=None, animationState="idle", **kwargs):
        from .fetch import fetch_json
        if not self.client_id:
            raise MultiplayerError("Not joined")
        url = f"{self.base_url}/api/multiplayer/character-state"
        state = CharacterState(
            clientId=self.client_id,
            position=position,
            velocity=velocity or [0,0],
            animationState=animationState,
            characterModelId=self.character_model_id,
            **kwargs
        )
        try:
            return await fetch_json(url, method="PATCH", headers={"X-Client-ID": self.client_id}, body={
                "updates": [state.to_dict()],
                "timestamp": int(time.time()*1000)
            })
        except Exception as e:
            print(f"send_character_state error: {e}")

    async def send_item_state(self, instanceId, pos, **kwargs):
        from .fetch import fetch_json
        if not self.client_id:
            raise MultiplayerError("Not joined")
        url = f"{self.base_url}/api/multiplayer/item-state"
        try:
            return await fetch_json(url, method="PATCH", headers={"X-Client-ID": self.client_id}, body={
                "updates": [{
                    "instanceId": instanceId,
                    "pos": pos,
                    "rot": kwargs.get("rot", [0,0,0,1]),
                    "isCollected": kwargs.get("isCollected", False),
                    "timestamp": int(time.time()*1000)
                }],
                "timestamp": int(time.time()*1000)
            })
        except Exception as e:
            print(f"send_item_state error: {e}")

    async def claim_item_authority(self, instanceId, reason="proximity-enter"):
        from .fetch import fetch_json
        if not self.client_id:
            raise MultiplayerError("Not joined")
        url = f"{self.base_url}/api/multiplayer/item-authority-claim"
        try:
            return await fetch_json(url, method="PATCH", headers={"X-Client-ID": self.client_id}, body={
                "instanceId": instanceId,
                "reason": reason,
                "timestamp": int(time.time()*1000)
            })
        except Exception as e:
            print(f"claim error: {e}")

    async def release_item_authority(self, instanceId, reason="grace-expired"):
        from .fetch import fetch_json
        if not self.client_id:
            raise MultiplayerError("Not joined")
        url = f"{self.base_url}/api/multiplayer/item-authority-release"
        try:
            return await fetch_json(url, method="PATCH", headers={"X-Client-ID": self.client_id}, body={
                "instanceId": instanceId,
                "reason": reason,
                "timestamp": int(time.time()*1000)
            })
        except Exception as e:
            print(f"release error: {e}")

    def is_datastar_connected(self):
        try:
            return bool(window.__SCS_DATASTAR_CONNECTED)
        except:
            return False

    def get_latest_signals(self):
        """Read latest Datastar signals (for canvas rendering)"""
        try:
            from .datastar import get_signal, get_game_snapshot
            # Try BGS signals
            chars = get_signal("characterState") or get_signal("character-state-update")
            items = get_signal("itemState") or get_signal("item-state-update") or get_game_snapshot()
            return {"characters": chars, "items": items}
        except:
            return {}

__all__ = ["MultiplayerClient", "CharacterState", "ItemInstanceState", "MultiplayerError"]