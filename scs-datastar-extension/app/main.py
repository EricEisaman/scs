"""
SCS Datastar Platformer Backend - BGS-MP-SYNC Python Implementation
Normative spec: https://github.com/EricEisaman/babylon-game-starter/blob/main/MULTIPLAYER_SYNCH.md
Short name: SCS-MP-SYNC
Transport: HTTPS + SSE (Datastar)
Encoding: JSON UTF-8

Implements:
- Session lifecycle: join, leave, stream (SSE)
- State messages: character-state, item-state, item-authority-claim/release
- Authority: itemOwners + envArrivalOrder + envAuthority (per §4.7, §4.8)
- Signals: character-state-update, item-state-update, client-joined, client-left,
           synchronizer-changed, item-authority-changed, env-item-authority-changed
- Dirty filter + freshness matrix (simplified for platformer)
"""

from fastapi import FastAPI, Request, APIRouter, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import pathlib as _path
import json
import asyncio
import uuid
import time

from .api.health import router as health_router
from .settings import settings
from .multiplayer.protocol import (
    JoinRequest, JoinResponse, 
    ClientJoinedSignal, ClientLeftSignal, SynchronizerChangedSignal,
    CharacterState, CharacterStateUpdate,
    ItemInstanceState, ItemCollectionEvent, ItemStateUpdate,
    ItemAuthorityClaim, ItemAuthorityClaimResponse,
    ItemAuthorityRelease,
    ItemAuthorityChangedSignal, EnvItemAuthorityChangedSignal,
    Capabilities
)
from .multiplayer.authority import AuthorityManager
from .multiplayer.dirty import DirtyFilter, FreshnessMatrix

from datastar_py.fastapi import DatastarResponse
from datastar_py import ServerSentEventGenerator as SSE

# ---------- Core Session & Room ----------

class ClientSession:
    def __init__(self, client_id: str, session_id: str, environment: str, character_name: str, is_synchronizer: bool):
        self.client_id = client_id
        self.session_id = session_id
        self.environment = environment
        self.character_name = character_name
        self.is_synchronizer = is_synchronizer
        self.created_at = time.time()
        self.last_seen = time.time()
        self.sse_queue: Optional[asyncio.Queue] = None  # for SSE push

class MultiplayerRegistry:
    def __init__(self):
        self.clients: Dict[str, ClientSession] = {}  # client_id -> session
        self.sessions: Dict[str, str] = {}  # session_id -> client_id
        self.authority = AuthorityManager()
        self.dirty_filter = DirtyFilter()
        self.freshness = FreshnessMatrix()
        self.base_synchronizer: Optional[str] = None
        self.character_cache: Dict[str, CharacterState] = {}  # client_id -> last CharacterState
        self.item_cache: Dict[str, ItemInstanceState] = {}  # instanceId -> last state
        self._lock = asyncio.Lock()
        self._tick_task: Optional[asyncio.Task] = None
        self.running = True

    async def start(self):
        self._tick_task = asyncio.create_task(self._tick_loop())
        print("[SCS-MP-SYNC] Registry started")

    async def stop(self):
        self.running = False
        if self._tick_task:
            self._tick_task.cancel()
            try: await self._tick_task
            except asyncio.CancelledError: pass
        print("[SCS-MP-SYNC] Registry stopped")

    async def _tick_loop(self):
        while self.running:
            await asyncio.sleep(1/20)  # 20Hz tick, broadcast if dirty

    async def join(self, req: JoinRequest) -> JoinResponse:
        async with self._lock:
            client_id = uuid.uuid4().hex[:8]
            session_id = uuid.uuid4().hex[:16]
            existing = sum(session.environment == req.environment_name for session in self.clients.values())
            is_sync = self.base_synchronizer is None

            session = ClientSession(
                client_id=client_id,
                session_id=session_id,
                environment=req.environment_name,
                character_name=req.character_name,
                is_synchronizer=is_sync
            )
            self.clients[client_id] = session
            self.sessions[session_id] = client_id

            if is_sync:
                self.base_synchronizer = client_id

            # Authority: arrival
            auth_event = self.authority.client_arrives(client_id, req.environment_name)

            # Freshness: mark all items as stale for this client (bootstrap)
            all_iids = list(self.item_cache.keys())
            self.freshness.client_enters(req.environment_name, client_id, all_iids)

            # Broadcast client-joined + env-authority-changed if needed
            await self._broadcast_signal("client-joined", {
                "eventType": "joined",
                "clientId": client_id,
                "environment": req.environment_name,
                "character": req.character_name,
                "totalClients": existing + 1,
                "timestamp": int(time.time()*1000)
            }, environment=req.environment_name)

            if auth_event.get("became_authority"):
                await self._broadcast_signal("env-item-authority-changed", {
                    "environmentName": req.environment_name,
                    "previousAuthorityId": None,
                    "newAuthorityId": client_id,
                    "reason": "arrival",
                    "timestamp": int(time.time()*1000)
                }, environment=req.environment_name)

            # Bootstrap: send existing authorities to new client via its queue (handled in stream)

            return JoinResponse(
                client_id=client_id,
                session_id=session_id,
                is_synchronizer=is_sync,
                existing_clients=existing
            )

    async def leave(self, client_id: str):
        async with self._lock:
            session = self.clients.pop(client_id, None)
            if not session:
                return
            self.sessions.pop(session.session_id, None)
            if session.sse_queue:
                self._enqueue_signal(session.sse_queue, "__close__", {})
                session.sse_queue = None
            if self.base_synchronizer == client_id:
                # Promote earliest remaining
                if self.clients:
                    new_sync = next(iter(self.clients))
                    self.base_synchronizer = new_sync
                    await self._broadcast_signal("synchronizer-changed", {
                        "newSynchronizerId": new_sync,
                        "reason": "disconnection",
                        "timestamp": int(time.time()*1000)
                    })
                else:
                    self.base_synchronizer = None

            # Authority failover
            events = self.authority.client_leaves(client_id)
            for ev in events:
                if ev["type"] == "env-authority-changed":
                    await self._broadcast_signal("env-item-authority-changed", ev, environment=ev.get("environmentName", session.environment))
                elif ev["type"] == "item-authority-changed":
                    await self._broadcast_signal("item-authority-changed", ev, environment=session.environment)

            self.freshness.client_leaves(session.environment, client_id)

            await self._broadcast_signal("client-left", {
                "eventType": "left",
                "clientId": client_id,
                "totalClients": sum(s.environment == session.environment for s in self.clients.values()),
                "timestamp": int(time.time()*1000)
            }, environment=session.environment)

    async def get_client_by_session(self, session_id: str) -> Optional[ClientSession]:
        client_id = self.sessions.get(session_id)
        if not client_id:
            return None
        return self.clients.get(client_id)

    @staticmethod
    def _enqueue_signal(queue: asyncio.Queue, signal_name: str, payload: Dict[str, Any]):
        try:
            queue.put_nowait((signal_name, payload))
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
                queue.put_nowait((signal_name, payload))
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

    async def subscribe_sse(self, client_id: str):
        """Atomically attach a live queue and capture the matching environment snapshot."""
        async with self._lock:
            client = self.clients.get(client_id)
            if not client:
                raise HTTPException(401, "Unknown client_id")
            if client.sse_queue:
                self._enqueue_signal(client.sse_queue, "__close__", {})
            queue = asyncio.Queue(maxsize=64)
            client.sse_queue = queue
            env_name = client.environment
            now = int(time.time()*1000)
            bootstrap = [("connectionState", {
                "connectionState": "connected",
                "clientId": client.client_id,
                "sessionId": client.session_id,
                "isSynchronizer": client.is_synchronizer,
                "environment": env_name,
                "serverTick": 0,
                "datastarConnected": True,
            })]
            for existing in self.clients.values():
                if existing.environment == env_name and existing.client_id != client_id:
                    bootstrap.append(("client-joined", {
                        "eventType": "joined",
                        "clientId": existing.client_id,
                        "environment": env_name,
                        "character": existing.character_name,
                        "totalClients": sum(s.environment == env_name for s in self.clients.values()),
                        "timestamp": now,
                    }))
            env_authority = self.authority.envAuthority.get(env_name)
            if env_authority:
                bootstrap.append(("envAuthority", {
                    "environmentName": env_name,
                    "previousAuthorityId": None,
                    "newAuthorityId": env_authority,
                    "reason": "arrival",
                    "timestamp": now,
                }))
            for instance_id, owner in self.authority.itemOwners.items():
                if self._item_belongs_to_environment(instance_id, env_name):
                    bootstrap.append(("itemAuthority", {
                        "instanceId": instance_id,
                        "previousOwnerId": None,
                        "newOwnerId": owner["ownerClientId"],
                        "reason": "claim",
                        "timestamp": now,
                    }))
            characters = [state.to_dict() for owner_id, state in self.character_cache.items()
                          if owner_id in self.clients and self.clients[owner_id].environment == env_name]
            if characters:
                bootstrap.append(("character-state-update", {"updates": characters, "timestamp": now}))
            items = [row for instance_id, row in self.item_cache.items()
                     if self._item_belongs_to_environment(instance_id, env_name)]
            if items:
                bootstrap.append(("item-state-update", {"updates": items, "collections": [], "timestamp": now}))
            return queue, bootstrap

    @staticmethod
    def _item_belongs_to_environment(instance_id: str, environment: str) -> bool:
        return str(instance_id).startswith(environment + ":")

    async def unsubscribe_sse(self, client_id: str, queue: asyncio.Queue):
        async with self._lock:
            client = self.clients.get(client_id)
            if client and client.sse_queue is queue:
                client.sse_queue = None

    async def _broadcast_signal(self, signal_name: str, payload: Dict[str, Any], environment: Optional[str] = None):
        for client in list(self.clients.values()):
            if environment is not None and client.environment != environment:
                continue
            if client.sse_queue:
                self._enqueue_signal(client.sse_queue, signal_name, payload)

    async def handle_character_state(self, client_id: str, updates: List[Dict]):
        async with self._lock:
            if client_id not in self.clients:
                raise HTTPException(403, "Unknown client")
            session = self.clients[client_id]
            # Authorization: each update.clientId must == X-Client-ID
            parsed_updates = []
            for update in updates:
                try:
                    state = CharacterState.from_payload(update)
                except (TypeError, ValueError) as ex:
                    raise HTTPException(422, str(ex))
                if state.clientId != client_id:
                    raise HTTPException(403, f"clientId mismatch: {state.clientId} != {client_id}")
                parsed_updates.append(state)
            for state in parsed_updates:
                self.character_cache[client_id] = state

            await self._broadcast_signal("character-state-update", {
                "updates": [state.to_dict() for state in parsed_updates],
                "timestamp": int(time.time()*1000)
            }, environment=session.environment)

    async def handle_item_state(self, client_id: str, updates: List[Dict], collections: List[Dict]):
        async with self._lock:
            session = self.clients.get(client_id)
            if not session:
                raise HTTPException(403, "Unknown client")

            env_name = session.environment
            accepted_updates = []
            accepted_collections = []

            # Per-row authorization (Tier 1 explicit, Tier 2 env-authority)
            for row in updates:
                iid = row.get("instanceId")
                if not iid:
                    continue
                resolved = self.authority.get_resolved_owner(iid, env_name)
                if resolved != client_id:
                    # Silently drop per §7.5
                    continue
                # Dirty filter
                if self.dirty_filter.is_dirty(iid, row):
                    accepted_updates.append(row)
                    self.item_cache[iid] = row
                    # Freshness: mark stale for others, fresh for owner
                    all_clients_in_env = [cid for cid, s in self.clients.items() if s.environment == env_name]
                    self.freshness.mark_dirty(env_name, iid, client_id, all_clients_in_env)
                    # Refresh activity if explicit
                    if iid in self.authority.itemOwners:
                        self.authority.refresh(iid, client_id)
                else:
                    # Still refresh activity even if clean
                    if iid in self.authority.itemOwners:
                        self.authority.refresh(iid, client_id)

            # Collections: first-write-wins
            for coll in collections:
                iid = coll.get("instanceId")
                if not iid:
                    continue
                cached = self.item_cache.get(iid)
                if cached and cached.get("isCollected"):
                    continue
                if coll.get("collectedByClientId") != client_id:
                    continue
                # Accept
                accepted_collections.append(coll)
                # Mark collected in cache
                if iid in self.item_cache:
                    self.item_cache[iid]["isCollected"] = True
                    self.item_cache[iid]["collectedByClientId"] = client_id
                else:
                    self.item_cache[iid] = {"instanceId": iid, "isCollected": True, "collectedByClientId": client_id}

            if accepted_updates or accepted_collections:
                await self._broadcast_signal("item-state-update", {
                    "updates": accepted_updates,
                    "collections": accepted_collections,
                    "timestamp": int(time.time()*1000)
                }, environment=env_name)

    async def handle_item_claim(self, client_id: str, claim: Dict) -> Dict:
        async with self._lock:
            session = self.clients.get(client_id)
            if not session:
                raise HTTPException(403, "Unknown client")
            iid = claim.get("instanceId")
            if not iid:
                raise HTTPException(400, "Missing instanceId")
            result = self.authority.claim(iid, client_id, idle_timeout_ms=10000)
            if result["accepted"]:
                if not result.get("already_owned"):
                    await self._broadcast_signal("item-authority-changed", {
                        "instanceId": iid,
                        "previousOwnerId": result.get("previous"),
                        "newOwnerId": result.get("new"),
                        "reason": result.get("reason", "claim"),
                        "timestamp": int(time.time()*1000)
                    }, environment=session.environment)
                return {
                    "ok": True,
                    "accepted": True,
                    "instanceId": iid,
                    "ownerClientId": result.get("new"),
                    "serverTimestamp": int(time.time()*1000)
                }
            else:
                return {
                    "ok": True,
                    "accepted": False,
                    "instanceId": iid,
                    "currentOwnerId": result.get("currentOwnerId"),
                    "serverTimestamp": int(time.time()*1000)
                }

    async def handle_item_release(self, client_id: str, release: Dict) -> Dict:
        async with self._lock:
            session = self.clients.get(client_id)
            if not session:
                raise HTTPException(403, "Unknown client")
            iid = release.get("instanceId")
            if not iid:
                raise HTTPException(400, "Missing instanceId")
            result = self.authority.release(iid, client_id)
            if result.get("released"):
                await self._broadcast_signal("item-authority-changed", {
                    "instanceId": iid,
                    "previousOwnerId": result.get("previous"),
                    "newOwnerId": None,
                    "reason": "release",
                    "timestamp": int(time.time()*1000)
                }, environment=session.environment)
                return {"ok": True, "released": True, "instanceId": iid, "serverTimestamp": int(time.time()*1000)}
            else:
                return {"ok": True, "released": False, "instanceId": iid, "serverTimestamp": int(time.time()*1000)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mp = MultiplayerRegistry()
    await app.state.mp.start()
    yield
    await app.state.mp.stop()


app = FastAPI(
    title="SCS Multiplayer - BGS-MP-SYNC Python",
    version="0.1.0",
    description="Python implementation of Babylon Game Starter Multiplayer Sync - SCS-MP-SYNC",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins_list() or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)

# ---------- BGS Routes ----------

bgs_router = APIRouter(prefix="/api/multiplayer")

class JoinBody(BaseModel):
    environment_name: str
    character_name: str

@bgs_router.post("/join")
async def join(request: Request, body: JoinBody):
    registry: MultiplayerRegistry = request.app.state.mp
    res = await registry.join(JoinRequest(environment_name=body.environment_name, character_name=body.character_name))
    return {
        "client_id": res.client_id,
        "session_id": res.session_id,
        "is_synchronizer": res.is_synchronizer,
        "existing_clients": res.existing_clients
    }

@bgs_router.post("/leave")
async def leave(request: Request, x_client_id: Optional[str] = Header(None, alias="X-Client-ID"), client_id: Optional[str] = None):
    cid = x_client_id or client_id or request.query_params.get("client_id")
    if not cid:
        raise HTTPException(400, "Missing client_id")
    registry: MultiplayerRegistry = request.app.state.mp
    await registry.leave(cid)
    return {"ok": True}

@bgs_router.get("/stream")
async def stream(request: Request, sid: Optional[str] = None, x_session_id: Optional[str] = Header(None, alias="X-Session-ID")):
    session_id = sid or x_session_id or request.query_params.get("session_id")
    if not session_id:
        raise HTTPException(400, "Missing session_id")
    registry: MultiplayerRegistry = request.app.state.mp
    client = await registry.get_client_by_session(session_id)
    if not client:
        raise HTTPException(401, "Unknown session_id")
    if sum(bool(session.sse_queue) for session in registry.clients.values()) >= 64:
        raise HTTPException(503, "Too many clients")

    async def event_generator():
        queue, bootstrap = await registry.subscribe_sse(client.client_id)
        try:
            for signal_name, payload in bootstrap:
                yield SSE.patch_signals({signal_name: payload})
                if signal_name == "character-state-update":
                    yield SSE.patch_signals({"gameSnapshot": payload})
            while True:
                signal_name, payload = await queue.get()
                if signal_name == "__close__":
                    break
                # Map signal_name to Datastar signal patch
                # BGS signals are delivered as patch_signals({signal_name: payload})
                yield SSE.patch_signals({signal_name: payload})

                # Also patch window globals for Brython compatibility
                if signal_name == "character-state-update":
                    yield SSE.patch_signals({"gameSnapshot": payload})
        except asyncio.CancelledError:
            pass
        finally:
            await registry.unsubscribe_sse(client.client_id, queue)

    return DatastarResponse(event_generator())

class CharacterStateBody(BaseModel):
    updates: List[Dict[str, Any]]
    timestamp: int

@bgs_router.patch("/character-state")
async def character_state(request: Request, body: CharacterStateBody, x_client_id: Optional[str] = Header(None, alias="X-Client-ID")):
    cid = x_client_id or request.headers.get("X-Client-ID")
    if not cid:
        raise HTTPException(400, "Missing X-Client-ID")
    registry: MultiplayerRegistry = request.app.state.mp
    await registry.handle_character_state(cid, body.updates)
    return {"ok": True}

class ItemStateBody(BaseModel):
    updates: List[Dict[str, Any]] = []
    collections: List[Dict[str, Any]] = []
    timestamp: int

@bgs_router.patch("/item-state")
async def item_state(request: Request, body: ItemStateBody, x_client_id: Optional[str] = Header(None, alias="X-Client-ID")):
    cid = x_client_id or request.headers.get("X-Client-ID")
    if not cid:
        raise HTTPException(400, "Missing X-Client-ID")
    registry: MultiplayerRegistry = request.app.state.mp
    await registry.handle_item_state(cid, body.updates, body.collections)
    return {"ok": True}

class ClaimBody(BaseModel):
    instanceId: str
    clientPosition: Optional[Dict[str, float]] = None
    reason: Optional[str] = None
    timestamp: int

@bgs_router.patch("/item-authority-claim")
async def item_claim(request: Request, body: ClaimBody, x_client_id: Optional[str] = Header(None, alias="X-Client-ID")):
    cid = x_client_id or request.headers.get("X-Client-ID")
    if not cid:
        raise HTTPException(400, "Missing X-Client-ID")
    registry: MultiplayerRegistry = request.app.state.mp
    result = await registry.handle_item_claim(cid, body.dict())
    return result

class ReleaseBody(BaseModel):
    instanceId: str
    reason: Optional[str] = None
    timestamp: int

@bgs_router.patch("/item-authority-release")
async def item_release(request: Request, body: ReleaseBody, x_client_id: Optional[str] = Header(None, alias="X-Client-ID")):
    cid = x_client_id or request.headers.get("X-Client-ID")
    if not cid:
        raise HTTPException(400, "Missing X-Client-ID")
    registry: MultiplayerRegistry = request.app.state.mp
    result = await registry.handle_item_release(cid, body.dict())
    return result

# Effects, lights, sky (base synchronizer only) - simplified
class EffectsBody(BaseModel):
    particle_effects: Optional[List[Dict]] = None
    environment_particles: Optional[List[Dict]] = None
    timestamp: int

@bgs_router.patch("/effects-state")
async def effects_state(request: Request, body: EffectsBody, x_client_id: Optional[str] = Header(None, alias="X-Client-ID")):
    cid = x_client_id or request.headers.get("X-Client-ID")
    registry: MultiplayerRegistry = request.app.state.mp
    if registry.base_synchronizer != cid:
        raise HTTPException(403, "Not base synchronizer")
    session = registry.clients.get(cid)
    if not session:
        raise HTTPException(403, "Unknown client")
    await registry._broadcast_signal("effects-state-update", body.dict(), environment=session.environment)
    return {"ok": True}

app.include_router(bgs_router)

@app.get("/api/v1/capabilities")
async def capabilities():
    return Capabilities().__dict__

@app.get("/extension/manifest.json")
async def manifest():
    mp = _path.Path(__file__).parent.parent / "extension" / "manifest.json"
    if mp.exists():
        return JSONResponse(json.loads(mp.read_text()))
    return JSONResponse({"id": "scs.bgs.platformer", "version": "0.1.0"})

@app.get("/")
async def root():
    return {
        "service": "SCS Multiplayer - SCS-MP-SYNC (BGS Python)",
        "version": "0.1.0",
        "spec": "https://github.com/EricEisaman/babylon-game-starter/blob/main/MULTIPLAYER_SYNCH.md",
        "transport": "HTTPS + SSE (Datastar)",
        "endpoints": {
            "join": "POST /api/multiplayer/join {environment_name, character_name}",
            "leave": "POST /api/multiplayer/leave X-Client-ID",
            "stream": "GET /api/multiplayer/stream?sid=session_id",
            "character-state": "PATCH /api/multiplayer/character-state X-Client-ID {updates, timestamp}",
            "item-state": "PATCH /api/multiplayer/item-state X-Client-ID {updates, collections, timestamp}",
            "item-claim": "PATCH /api/multiplayer/item-authority-claim X-Client-ID {instanceId, reason, timestamp}",
            "item-release": "PATCH /api/multiplayer/item-authority-release X-Client-ID {instanceId, reason, timestamp}",
        },
        "signals": ["character-state-update", "item-state-update", "client-joined", "client-left", "synchronizer-changed", "item-authority-changed", "env-item-authority-changed"],
        "python_api": "extensions.multiplayer.MultiplayerClient"
    }