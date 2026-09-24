"""
SCS-MP-SYNC - Python adaptation of BGS-MP-SYNC (Babylon Game Starter)
Normative: https://github.com/EricEisaman/babylon-game-starter/blob/main/MULTIPLAYER_SYNCH.md

Transport: HTTPS + SSE (Datastar)
Encoding: JSON UTF-8

This is the well-designed Python API that mirrors BGS patterns but for 2D platformer.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Literal
import time

# ---------- Session lifecycle ----------

@dataclass
class JoinRequest:
    environment_name: str
    character_name: str

@dataclass
class JoinResponse:
    client_id: str
    session_id: str
    is_synchronizer: bool
    existing_clients: int

@dataclass
class ClientJoinedSignal:
    eventType: Literal["joined"] = "joined"
    clientId: str = ""
    environment: str = ""
    character: str = ""
    totalClients: int = 0
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

@dataclass
class ClientLeftSignal:
    eventType: Literal["left"] = "left"
    clientId: str = ""
    totalClients: int = 0
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

@dataclass
class SynchronizerChangedSignal:
    newSynchronizerId: str
    reason: str  # "disconnection", etc.
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

# ---------- Character state (per-player) ----------

@dataclass
class CharacterState:
    """Authoritative per-player state, owned by client_id. Mirrors BGS CharacterState but 2D."""
    clientId: str
    characterModelId: str = "platformer-default"
    position: List[float] = field(default_factory=lambda: [0.0, 0.0])  # [x, y]
    velocity: List[float] = field(default_factory=lambda: [0.0, 0.0])   # [vx, vy]
    animationState: str = "idle"  # idle, run, jump, fall
    animationFrame: float = 0.0
    isJumping: bool = False
    facing: int = 1  # -1 left, 1 right
    score: int = 0
    onGround: bool = False
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

    def to_dict(self):
        return asdict(self)

@dataclass
class CharacterStateUpdate:
    updates: List[CharacterState]
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

# ---------- Item state (shared world) ----------

@dataclass
class ItemInstanceState:
    """Pose-only transport per BGS Invariant P. pos [x,y], rot quaternion [x,y,z,w]."""
    instanceId: str
    itemName: str = ""
    pos: List[float] = field(default_factory=lambda: [0.0, 0.0])  # world pos [x, y]
    rot: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])  # quaternion
    isCollected: bool = False
    collectedByClientId: Optional[str] = None
    ownerClientId: Optional[str] = None
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

@dataclass
class ItemCollectionEvent:
    instanceId: str
    collectedByClientId: str
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

@dataclass
class ItemStateUpdate:
    updates: List[ItemInstanceState] = field(default_factory=list)
    collections: List[ItemCollectionEvent] = field(default_factory=list)
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

# ---------- Authority ----------

@dataclass
class ItemAuthorityClaim:
    instanceId: str
    clientPosition: Optional[Dict[str, float]] = None  # {"x":.., "y":.., "z":..}
    reason: Optional[str] = None  # proximity-enter, refresh, etc.
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

@dataclass
class ItemAuthorityClaimResponse:
    ok: bool = True
    accepted: bool = False
    instanceId: str = ""
    ownerClientId: Optional[str] = None
    currentOwnerId: Optional[str] = None
    serverTimestamp: int = field(default_factory=lambda: int(time.time()*1000))

@dataclass
class ItemAuthorityRelease:
    instanceId: str
    reason: Optional[str] = None
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

@dataclass
class ItemAuthorityChangedSignal:
    instanceId: str
    previousOwnerId: Optional[str]
    newOwnerId: Optional[str]
    reason: Literal["claim", "release", "disconnect", "idle_timeout", "env_switch"]
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

@dataclass
class EnvItemAuthorityChangedSignal:
    environmentName: str
    previousAuthorityId: Optional[str]
    newAuthorityId: Optional[str]
    reason: Literal["arrival", "failover", "env_switch", "disconnect"]
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

# ---------- Global world state (base synchronizer only) ----------

@dataclass
class LightState:
    lightId: str
    isEnabled: bool = True
    intensity: float = 1.0
    timestamp: int = field(default_factory=lambda: int(time.time()*1000))

# ---------- Capabilities ----------
@dataclass
class Capabilities:
    protocolVersion: int = 1
    transport: str = "datastar-sse"
    features: Dict[str, bool] = field(default_factory=lambda: {
        "characterState": True,
        "itemState": True,
        "itemAuthority": True,
        "envAuthority": True,
        "baseSynchronizer": True,
        "websocket": False,
        "sse": True,
    })
    limits: Dict[str, int] = field(default_factory=lambda: {
        "maxClients": 16,
        "maxPlayersPerRoom": 8,
        "tickHz": 20,
        "snapshotHz": 15,
        "claimIdleTimeoutMs": 10000,
    })