# SCS Datastar Platformer - BGS-MP-SYNC Python

Fullstack extension: FastAPI + datastar-py + Brython 2D platformer with Babylon Game Starter multiplayer sync pattern.

## Render Deployment

Render expects:
- `render.yaml` in repo root (this file)
- `Dockerfile` in repo root (this file)

This repo has backend code in `scs-datastar-extension/` but Dockerfile copies from there.

### Deploy Steps
1. Push to GitHub
2. Render -> New Web Service -> Connect repo
3. Render auto-detects `render.yaml`
4. Runtime: Docker, Dockerfile Path: `./Dockerfile`
5. Health check: `/healthz`
6. Port: 10000 (env PORT)

### Local Dev
```bash
cd scs-datastar-extension
pip install -e .
uvicorn app.main:app --reload --port 10000
# http://localhost:10000/
# http://localhost:10000/docs
# http://localhost:10000/api/multiplayer/join
```

### SCS Apps (Playable Now)
- `?app=platformer_bgs` - Uses new BGS-MP-SYNC Python API (`extensions.multiplayer.MultiplayerClient`)
- `?app=platformer_multiplayer` - Local 2-4 player + datastar ghost mode

### Python API (Well-designed, BGS pattern)

```python
from extensions.multiplayer import MultiplayerClient

client = MultiplayerClient(
    base_url="https://scs-datastar-extension.onrender.com",
    environment="level1",
    character_name="Player1"
)

# Join (POST /api/multiplayer/join)
await client.join()  # -> client_id, session_id, is_synchronizer

# Send inputs (PATCH /api/multiplayer/character-state)
await client.send_character_state(
    position=[x, y],
    velocity=[vx, vy],
    animationState="run"
)

# Claim item authority (PATCH /api/multiplayer/item-authority-claim)
await client.claim_item_authority("level1::coin::0", reason="proximity-enter")

# SSE stream (GET /api/multiplayer/stream?sid=session_id)
# Datastar: patch_signals({"character-state-update": {...}})
# Brython reads via window.__SCS_GAME_STATE
```

### Protocol: SCS-MP-SYNC

Adapted from BGS-MP-SYNC: https://github.com/EricEisaman/babylon-game-starter/blob/main/MULTIPLAYER_SYNCH.md

- Session: join, leave, stream (SSE)
- Character state: per-client ownership, server validates X-Client-ID
- Item state: resolved owner (explicit claim > env-authority), dirty filter, freshness matrix
- Authority: itemOwners + envArrivalOrder + envAuthority
- Signals: character-state-update, item-state-update, client-joined, synchronizer-changed, etc.
- Transport: HTTPS + SSE (Datastar), no websockets

### Files Fixed
- `index.html` title: SCS Datastar Platformer - BGS Multiplayer (was Building-CMU-CPCS-sandbox)
- `sandbox.html` title: SCS Datastar Platformer - Sandbox
- `Dockerfile` in root for Render
- `render.yaml` in root for Render
