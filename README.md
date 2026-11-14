[SCS : Scientific Computing System](scs.jpg)

# SCS : Scientific Computing System

> A fast, faithful, Brython-powered implementation of the **CMU Graphics** API that runs in the browser. No server-side Python backend is required; scientific-computing labs load Pyodide and SciPy in a Web Worker when needed.

[[Brython](https://img.shields.io/badge/Brython-3.11.3-blue)](https://brython.info/)
[[CMU Graphics](https://img.shields.io/badge/API-CMU%20Graphics-red)](https://academy.cs.cmu.edu/)
[[License](https://img.shields.io/badge/license-MIT-black)](LICENSE)
[[Apps](https://img.shields.io/badge/apps-19-green)](#apps-included)

Live demo:
<a href="https://ericeisaman.github.io/scs/" target="_blank" rel="noopener noreferrer">
  https://ericeisaman.github.io/scs/
</a>
- loads <code>apps/app.py</code>

<br>

Try: <code>?app=rabbit_sim</code> →
<a href="https://ericeisaman.github.io/scs/?app=rabbit_sim" target="_blank" rel="noopener noreferrer">
  https://ericeisaman.github.io/scs/?app=rabbit_sim
</a>

<br>

Sandbox: <code>/sandbox/</code> →
<a href="https://ericeisaman.github.io/scs/sandbox/" target="_blank" rel="noopener noreferrer">
  https://ericeisaman.github.io/scs/sandbox/
</a>

---

## Multi-Renderer: 2D Canvas, WebGL2, WebGPU, and WebXR

SCS is now SCS API-compatible across renderers. The same CMU Graphics app code runs on a 2D canvas context, WebGL2, or WebGPU, depending on initialization. `scs_entrypoint.py` handles all user choices.

```python
run_app(renderer='2d')      # 2D canvas context
run_app(renderer='webgl2')  # WebGL2
run_app(renderer='webgpu')  # WebGPU (async init, auto fallback)
run_app(renderer='auto')    # WebGPU -> WebGL2 -> 2D
```

Other ways to choose:

```
?app=rabbit_sim&renderer=webgpu   # URL param
SCS.create({renderer: 'webgpu'})  # JS / CDN loader
setRenderer('webgl2')             # switch at runtime where supported
```

| Choice | Renderer | Notes |
| --- | --- | --- |
| `2d` | 2D canvas context | Original path, `_ctx` is the 2D context |
| `webgl2` | WebGL2 | Same API, GPU raster path |
| `webgpu` | WebGPU | Same API, async init, falls back on failure |
| `auto` | Best available | WebGPU → WebGL2 → 2D |

WebXR is handled separately, not as a fourth renderer:

```python
startXR(mode='immersive-vr')  # enter XR
renderFrame(frameContext)     # externally-driven XR loop
stopXR()                      # exit XR
getXRState() / getXRCapability()
```

See `docs/ARCHITECTURE_XR.md` for the XR loop, `FrameContext`, lifecycle, and semantic actions (`select` / `squeeze`, not mouse).

---

## New Interactive Labs

SCS now pairs its CMU Graphics runtime with focused visual and scientific-computing experiences:

| Lab | Explore |
| --- | --- |
| [Nonlinear Solver](https://ericeisaman.github.io/scs/?app=linear_solver) | Solve nonlinear equation systems with SciPy's `optimize.root`. |
| [ODE Solver](https://ericeisaman.github.io/scs/?app=ode) | Integrate and animate six physics, mechanics, and chemistry ODE presets with SciPy. |
| [Eigenvectors](https://ericeisaman.github.io/scs/?app=eigenvalue) | See how stretch, shear, rotation, and reflection transform vectors and eigenvector spans. |
| [Image Processing](https://ericeisaman.github.io/scs/?app=image_processing) | Apply Gaussian filtering, Sobel edges, and binary morphology to an image. |

Brython remains the rendering runtime. SciPy computations run in an optional Pyodide worker; the ODE lab animates successfully returned samples locally in Brython. The reusable `extensions.file_loader` handles local image files and image URLs.

### What is this?

SCS is a drop-in browser runtime for CMU Graphics / `cmu_graphics` coursework. You write the same `onAppStart`, `onStep`, `redrawAll`, `onMousePress` code you would in CMU Academy, and it runs on an HTML canvas via Brython.

This repo includes:

- **`scs.py`**: the full API shim (`Rect`, `Oval`, `Circle`, `Label`, `Line`, `Polygon`, `Group`, `Image`, `Sound`, `draw*`, `rgb()`, `gradient()`, `distance()`, `angleTo()`, etc.) with **align as a true general property**
- **`scs_entrypoint.py`**: multi-renderer entrypoint — 2D / WebGL2 / WebGPU selection, auto fallback, event handlers, and boilerplate from `index.html`
- **`scs/`**: renderer and subsystem modules — see [SCS modules](#scs-modules) below
- **`index.html`**: production viewer. Loads apps from `apps/` via URL param `?app=`, with auto-start and a `window.fetch` loader
- **`sandbox.html`**: live editor. Edit code in a textarea and hit Run. It also auto-starts
- **`extensions/`**: **NEW: SCS Extensions System**, pure Model-layer libraries that bring the browser to your CMU app
- **`apps/`**: all runnable apps. No root duplication.

---

## SCS Modules

All new modules live under `scs/` in the repository. Docs live under `docs/`.

| Module | What it is | Doc |
| --- | --- | --- |
| `scs/scs_presentation.py` | Fullscreen / presentation as an async presentation mode, not a canvas resize | `docs/ARCHITECTURE_PRESENTATION.md` |
| `scs/scs_controller.py` | Gamepad / controller — gameplay depends on buttons, axes, capabilities, never on USB vs Bluetooth transport | `docs/ARCHITECTURE_CONTROLLER.md` |
| `scs/scs_loader.py` | Asset loader (GLB / audio / textures) — source data, decoded assets, mutable instances, and backend resources are four distinct things | `docs/ARCHITECTURE_LOADER.md` |
| `scs/scs_splats.py` | 3D Gaussian splats as a first-class rendering primitive, not a mesh-loader special case | `docs/ARCHITECTURE_SPLATS.md` |
| `scs/scs_storage.py` | Storage / persistence layer | `docs/ARCHITECTURE_INTEGRATIONS.md` |
| `scs/scs_wasm.py` | WASM interop layer | `docs/ARCHITECTURE_INTEGRATIONS.md` |
| `scs/scs_audio.py` | Audio subsystem | `docs/ARCHITECTURE_INTEGRATIONS.md` |
| `scs/scs_media.py` | Media subsystem | `docs/ARCHITECTURE_INTEGRATIONS.md` |
| `scs/scs_serial.py` | Serial subsystem | `docs/ARCHITECTURE_INTEGRATIONS.md` |
| `scs/scs_xr.py` | WebXR — externally-driven loop, `FrameContext`, lifecycle | `docs/ARCHITECTURE_XR.md` |

Entrypoint surface (all in `scs_entrypoint.py`):

```python
# Renderers
run_app(renderer='2d' | 'webgl2' | 'webgpu' | 'auto')
setRenderer('webgpu')
# XR
startXR(), stopXR(), renderFrame(frameContext), getXRState(), getXRCapability()
# Presentation / controller / loader / splats
enterFullscreen(), getControllerManager(), getAssetLoader(), loadAsset()
getSplatRenderer(), createSplatSchema(), createSplatAsset(), loadSplatManifest()
```

### Splats: first-class primitive

Splats get their own projection + ordering pipeline, schema, chunk / LOD / residency machinery, and appearance model — behind the same boundary for WebGL (raster) and WebGPU (compute-assisted):

- **Custom passes**, not just mesh draw calls — shared cameras, transforms, lighting inputs, and opaque-scene depth.
- **Versioned logical schema** ≠ packed GPU layout — position, scale/rotation or covariance, opacity, variable-degree SH, optional normals / material / lighting-transfer / custom attributes, chunk-local quantization metadata. No JS object per Gaussian.
- **Sorting / transparency as an explicit service** — replaceable ordering stage, across interacting splat objects, with validity info. Static attribute buffers are separate from the visible/sorted index list.
- **Multi-view preparation** — scene-wide work once, view-dependent work per view. One eye's ordering is never assumed sufficient for the other.
- **Chunked assets** — manifest + coarse chunk first, fetch by id / byte range, decode independently, cancel / reprioritize, partial readiness, monolithic fallback.
- **Hierarchical LOD as representation** — bounds, parent/child, approximation error, payload refs. Coarse parents stand in while children load. Never "first N splats".
- **Residency ≠ scene membership** — separate accounting/budgets for downloaded / decoded / GPU / sorting / pending work. Stable chunk handles with generation checks, never raw GPU offsets.
- **Captured radiance ≠ intrinsic material** — modes: `captured-radiance`, `artistic-adjustment`, `relightable-material`, `precomputed-lighting-variant`. SH coefficients are never labeled "albedo".
- **Aligned proxy geometry** — per-role proxies (`relighting` / `collision` / `shadow` / `occlusion` / `picking` / `radiance-transfer`) in the same coordinate system. A collision proxy is not automatically an adequate relighting proxy.
- **Appearance updates independent of geometry/LOD** — replace appearance without rebuilding positions, covariance, hierarchy, or bounds. Only appearance buffers are invalidated.

Demo: `?app=splats_demo`

### Presentation, Controller, Loader

- **Presentation** (`apps/presentation_demo.py`): fullscreen is an async presentation mode. Capability-tested entry, presentation state, and exit paths are explicit.
- **Controller** (`apps/controller_demo.py`): button / axis / capability model with deadzones, mapping, and disconnect/reconnect handling. Game code never branches on transport.
- **Loader** (`apps/loader_demo.py`): `getAssetLoader()` / `loadAsset()` / `loadGLB()` / `loadTexture()` / `loadAudio()`. Source bytes, decoded data, instances, and GPU resources stay distinct, so the same asset can be reused across backends without re-decoding.

### Integrations: Storage, WASM, Audio, Media, Serial

`apps/integrations_demo.py` exercises the integration layer: storage, WASM, audio, media, and serial behind explicit boundaries — resource creation, updates, command recording, and submission stay separate, with explicit ownership, async lifecycle, timestamped data where relevant, and bounded work at the rendering boundary. Mutable WebGL global state is never the shared abstraction; each backend defines its portable baseline, capability checks, and backend-specific extensions.

---

## 🌟 NEW: The SCS Extensions System. The Browser Is Now Your Model

We asked: what if CMU Graphics apps could talk to the real web without breaking MVC? What if you could `await fetch_json()` in `onAppStart` and still keep `redrawAll` pure?

**The SCS Extensions System** is the answer. It's awesome because it stays out of your way.

### Why it's awesome

**1. Strict MVC, zero cheating**
Extensions are **Model-only**. They never import `scs`, never touch canvas, never draw. They fetch data. Your Controller (`onAppStart`, `onMousePress`) stores it in `app.*`. Your View (`redrawAll`) reads `app.*` and renders. CPCS-approved separation.

```
Model:      extensions.fetch → data
Controller: onAppStart → app.poem = await fetch_json(...)
View:       redrawAll → drawLabel(app.poem.title)
```

**2. Browser Fetch API aligned**
We mirror `window.fetch` exactly. If you know MDN, you know SCS:

```python
# Browser: fetch(url, {method, headers, body, mode})
# SCS:     await fetch(url, method='POST', headers={}, body={}, mode='cors')
```

Returns `FetchResponse` with `.ok`, `.status`, `.statusText`, `.headers`, and async `.json()`, `.text()`, `.blob()`, `.arrayBuffer()`.

**3. Brython async that just works**
All public APIs are `async def`. Use `browser.aio`:

```python
from browser import aio
from extensions.fetch import fetch_json

async def load_poem(app):
    app.poem = await fetch_json('https://poetrydb.org/random')

def onAppStart(app):
    aio.run(load_poem(app))
```

No callbacks. No promises. Just `await`.

**4. Bulletproof Brython loader**
Brython tries `./extensions.py` before `./extensions/__init__.py` — classic footgun. We ship **both**:

- `extensions.py`: root shim implementing full API and injecting `sys.modules['extensions.fetch']`
- `extensions/__init__.py` + `extensions/fetch.py`: real package

Result: `from extensions.fetch import fetch_json` **always** works, in `index.html` and `sandbox.html`.

**5. Auto-start loader (finally!)**
Both viewers now detect CMU-style apps that define `onAppStart`/`redrawAll` without calling `runApp()` — and auto-start them. Fixed the `aio.run()` false-positive that was blocking it.

### 📦 Extensions Included

#### `extensions.fetch` — Async Fetch (Model Layer)

The flagship. Full browser fetch in Python.

```python
from extensions.fetch import fetch, fetch_json, fetch_text, FetchError

# Simple JSON
poem = await fetch_json('https://poetrydb.org/random')

# Full control
resp = await fetch('https://api.example.com/data',
                   method='POST',
                   headers={'Content-Type': 'application/json'},
                   body={'key': 'value'},
                   mode='cors')

if resp.ok:
    data = await resp.json()

# Text
html = await fetch_text('https://example.com')
```

**Features:**
- `fetch(url, method, headers, body, mode, credentials, cache)` → `FetchResponse`
- `fetch_json(url, ...)` → `dict|list`
- `fetch_text(url, ...)` → `str`
- `FetchError` with `.status` + `.response`
- Dual backend: `window.fetch` primary, `aio.fetch` fallback
- Handles JS objects vs Python dicts transparently

### 🧪 The Proof: `fetch_demo`

`apps/fetch_demo.py` — PoetryDB Live Demo

```
?app=fetch_demo → https://ericeisaman.github.io/scs/?app=fetch_demo
```

MVC-perfect:

```python
from scs import *
from extensions.fetch import fetch_json
from browser import aio

def parse_poem(raw): # Model helper — pure
    data = raw[0] if isinstance(raw, list) else raw
    return {'title': data['title'], 'author': data['author'], 'lines': data['lines']}

async def load_poem(app): # Controller
    app.loading = True
    data = await fetch_json('https://poetrydb.org/random')
    app.poem = parse_poem(data)
    app.loading = False

def onAppStart(app):
    app.background = gradient(rgb(15,17,21), rgb(26,29,36), start='top')
    aio.run(load_poem(app))

def onMousePress(app, x, y): # Click for new poem
    aio.run(load_poem(app))

def redrawAll(app): # View — pure rendering
    if app.loading:
        drawLabel("Loading poem...", app.width//2, app.height//2, size=20)
    else:
        drawLabel(app.poem['title'], app.width//2, 110, size=24, bold=True)
```

Controls: `SPACE / R / Click` → new poem.

---

## Multiplayer Platformer Sync

`apps/platformer_multiplayer.py` is a playable 2D platformer that runs with the same game code in local mode or against the Datastar backend. It supports two to four local players, player movement and jumping, coins, platform collisions, and procedural game sounds.

The optional backend in `scs-datastar-extension/` implements SCS-MP-SYNC over HTTPS, JSON, and Server-Sent Events (SSE). Clients join an environment, receive a session ID, subscribe to a live stream, and publish state through HTTP actions:

- `POST /api/multiplayer/join` creates a client session and assigns the initial synchronizer.
- `GET /api/multiplayer/stream?sid=<session_id>` sends the bootstrap snapshot and live Datastar signals.
- `PATCH /api/multiplayer/character-state` publishes validated 2D character state.
- `PATCH /api/multiplayer/item-state` publishes shared item poses and collection events.
- `PATCH /api/multiplayer/item-authority-claim` and `item-authority-release` manage item ownership.
- `POST /api/multiplayer/leave` closes a client session.

The registry keeps updates isolated by environment, provides a 20 Hz server tick, validates finite 2D vectors, bootstraps new subscribers without an event gap, and handles synchronizer and item-authority failover. Signals include character and item updates, client join and leave events, synchronizer changes, and authority changes. See [the synchronization protocol](https://github.com/EricEisaman/babylon-game-starter/blob/main/MULTIPLAYER_SYNCH.md) and [the multiplayer tests](scs-datastar-extension/tests/test_multiplayer_sync.py).

## Procedural Sound System

The procedural audio extension in `extensions/proc_audio.py` builds deterministic sound effects in the browser with the Web Audio API. The live [PROCAUDIO demo](https://ericeisaman.github.io/scs/PROCAUDIO.html) provides the quickest way to hear and inspect the system.

Use the high-level API for preset playback:

```python
from extensions.proc_audio import AudioEngine

audio = AudioEngine(quality="high", seed=90210)
audio.resume()  # call after a user gesture
audio.play("character.jump", seed=42, spatial=True, position={"x": 0, "y": 0})
```

For custom sounds, `Patch` provides a declarative graph and chainable builder for oscillators, pitch envelopes, filters, ADSR envelopes, distortion, macros, routing, tags, and JSON serialization. Seeded randomization keeps variations reproducible. The engine also includes master and category buses, polyphony limits with voice stealing, burst protection, stereo or full spatial profiles, reverb and convolution, analyser data, AudioWorklet DSP, `OfflineAudioContext` baking, and recording.

Quality profiles are `low`, `medium`, `high`, and `cinematic`. Presets and routing metadata are published in [the procedural audio manifest](extensions/proc_audio_manifest.json), while the demo app is available at `?app=proc_audio_demo`.

### ✨ Catalog Your Creations in the apps Directory

Default: `apps/app.py`

**Safe loader**
- Blocks `..` and absolute paths
- Sanitizes to `[a-zA-Z0-9_-]`
- Graceful fallback to `apps/app.py`
- Now uses `window.fetch` — reliable in Brython 3.11.3

---

### 🚀 Quick Start

#### 1. Clone and serve
```bash
git clone https://github.com/ericeisaman/scs
cd scs
python -m http.server 8000
# open http://localhost:8000/
```

> Chrome blocks `file://` fetch. You must use a local server.

#### 2. Open an app
```
http://localhost:8000/                     → Joukowski Wind Tunnel
http://localhost:8000/?app=rabbit_sim      → Rabbit Population Lab
http://localhost:8000/?app=fetch_demo      → Extensions.fetch Demo (NEW!)
http://localhost:8000/sandbox.html         → Live editor
```

Pick a renderer:

```
http://localhost:8000/?app=rabbit_sim&renderer=webgpu  → WebGPU
http://localhost:8000/?app=rabbit_sim&renderer=webgl2  → WebGL2
http://localhost:8000/?app=rabbit_sim&renderer=2d      → 2D canvas
http://localhost:8000/?app=rabbit_sim&renderer=auto    → best available
```

#### 3. Try Extensions in sandbox

Paste this into `sandbox.html`:

```python
from scs import *
from extensions.fetch import fetch_json
from browser import aio

async def load(app):
    app.joke = await fetch_json('https://official-joke-api.appspot.com/random_joke')

def onAppStart(app):
    app.joke = None
    aio.run(load(app))

def onMousePress(app, x, y):
    aio.run(load(app))

def redrawAll(app):
    if app.joke is None:
        drawLabel("Loading...", 200, 200, fill='white', size=20)
    else:
        drawLabel(app.joke['setup'], 200, 180, fill='white', size=14)
        drawLabel(app.joke['punchline'], 200, 210, fill='cyan', size=14, bold=True)
```

Click for new joke. No backend.

### 📁 Project Structure

```
/
├── index.html          # Viewer: loads apps via ?app=, auto-start, window.fetch
├── sandbox.html        # Editor: edit + Run, auto-start, pythonpath=['.']
├── scs.py              # CMU Graphics API (Brython)
├── scs_entrypoint.py   # Multi-renderer entrypoint: 2D / WebGL2 / WebGPU / WebXR
├── app.py              # DEPRECATED placeholder (see apps/app.py)
├── extensions.py        # Root shim: makes `import extensions` work in Brython
├── extensions/         # SCS Extensions System
│   ├── __init__.py     # Package marker
│   ├── fetch.py        # Async Fetch: browser-aligned, Model-only
│   ├── file_loader.py  # Browser image loading and RGBA extraction, Model-only
│   ├── pyodide.py      # Lazy SciPy API: Pyodide Web Worker, Model-only
│   └── pyodide_worker.js # Worker runtime and serialized SciPy operations
├── scs/                # Renderer + subsystem modules (new)
│   ├── scs_presentation.py
│   ├── scs_controller.py
│   ├── scs_loader.py
│   ├── scs_splats.py
│   ├── scs_storage.py
│   ├── scs_wasm.py
│   ├── scs_audio.py
│   ├── scs_media.py
│   ├── scs_serial.py
│   └── scs_xr.py
├── docs/               # Architecture docs (new)
│   ├── ARCHITECTURE_PRESENTATION.md
│   ├── ARCHITECTURE_CONTROLLER.md
│   ├── ARCHITECTURE_LOADER.md
│   ├── ARCHITECTURE_SPLATS.md
│   ├── ARCHITECTURE_INTEGRATIONS.md
│   └── ARCHITECTURE_XR.md
└── apps/
    ├── acceleration_academy.py
    ├── app.py              → Joukowski Aerofoil Wind Tunnel (default)
    ├── drone_control_theory.py
    ├── eigenvalue.py       → Visual eigenvectors and plane transformations
    ├── fetch_demo.py       → Extensions.fetch: PoetryDB live
    ├── image_processing.py → scipy.ndimage image filtering and morphology
    ├── linear_solver.py    → SciPy nonlinear root finder: Pyodide worker
    ├── ode.py              → SciPy ODE solver with animated preset systems
    ├── Motorsliver.py
    ├── momentum_mayhem.py
    ├── platformer_bgs.py
    ├── proc_audio_demo.py  → Procedural audio workbench
    ├── rabbit_sim.py       → Rabbit Meadow Population Dynamics
    ├── swila.py
    ├── presentation_demo.py → Fullscreen / presentation (new)
    ├── controller_demo.py   → Gamepad / controller (new)
    ├── loader_demo.py       → Asset loader (new)
    ├── splats_demo.py       → Gaussian splats, first-class primitive (new)
    ├── integrations_demo.py → Storage / WASM / audio / media / serial (new)
    └── xr_demo.py           → WebXR (new)
```

No root `app.py` duplication. Real apps are **only** in `apps/`.

### 🧪 Apps Included

#### `apps/app.py` — Joukowski Conformal-Mapping Wind Tunnel
Exact-method aerofoil design. 1050×700. Drag the gold handle to change camber, W/S for circulation, A/D for angle of attack.

- Cached source & mapped geometry (built only on input change)
- Streamlines with circulation asymmetry
- Leading/trailing edge detection, quarter-chord pivot rotation
- Wind stays horizontal — aerofoil rotates

Controls: `W/S` circulation, `A/D` angle, `Q/E` radius, `1/2/3` presets, `Space` pause, `R` reset, `H` help

#### `apps/rabbit_sim.py` — Rabbit Population Dynamics Lab
CMU CS Academy style ecology sim. Logistic growth + predation + carrying capacity.

```
carryingCapacity = habitatCapacity * foodAvailability
rabbitGrowth = r * N * (1 - N / K)
predation = foxes * predationRate * N / (N + halfSaturation)
```

Features: cloud parallax, day/night sky, animated rabbits/foxes, flowers, grass patches, capacity history graph.

#### `apps/fetch_demo.py` — Extensions.fetch Live Demo (NEW!)
Proof that Extensions work. Fetches random poem from PoetryDB.org.

- Uses `extensions.fetch` + `browser.aio`
- Handles JS-object vs Python-dict edge cases
- MVC strict: no drawing in fetch, no fetching in redrawAll
- 1050×700, gradient background, click/space for new poem

#### `apps/linear_solver.py` — Nonlinear Root Finder
Enter one LaTeX-style equation per line, name the variables, and provide an initial guess. SciPy's `optimize.root` runs in a lazily started Pyodide Web Worker; Brython remains responsible for the controls and CMU canvas.

- Supports powers, fractions, square roots, and common trigonometric/log functions
- Displays the solution, residuals, evaluation count, and before/after residual norm
- Open with `/?app=linear_solver`; the first solve downloads Pyodide and SciPy

#### `apps/ode.py` — Animated ODE Solver
Integrate a selected initial-value system with SciPy's `solve_ivp` in the Pyodide worker. Brython animates the returned samples locally, without making a worker request on each frame. The six presets cover a nonlinear pendulum, Lorenz attractor, mass-spring-damper, Duffing oscillator, consecutive A→B→C reactions, and the Brusselator.

- Choose a preset or edit the initial state, time span, and integration method, then select **Integrate**
- Playback advances through the computed samples; press `Space` to pause/resume and `R` to restart
- Open with `/?app=ode`; the first solve downloads Pyodide and SciPy
- Known limitation: Lorenz and consecutive-reaction results currently fail during result decoding in Brython 3.11.3; the other four presets have been verified

#### `apps/eigenvalue.py` — Eigenvectors as Geometric Directions
Compare a vector with its image under stretch, shear, 90-degree rotation, and reflection. Drag or click in the plane to move the test vector; dashed lines mark eigenvector spans and the sidebar reports whether the direction is preserved.

- Includes positive, negative, and repeated eigenvalue examples, plus a rotation with no real eigenvectors
- Select transformations with the on-screen buttons or keys `1`-`4`
- Open with `/?app=eigenvalue`

#### `apps/image_processing.py` — Image Processing Lab
Load the bundled `scs.jpg`, choose a local image, or enter a CORS-enabled image URL. Compare the source and result for Gaussian blur, Sobel edge magnitude, or binary opening with foreground-area measurement. Image loading is provided by `extensions.file_loader`; SciPy processing runs in the optional Pyodide worker.

- Resizes input to a maximum 384-pixel edge before processing
- Open with `/?app=image_processing`

#### New subsystem demos

- `apps/presentation_demo.py` — Fullscreen / presentation (`?app=presentation_demo`)
- `apps/controller_demo.py` — Gamepad / controller (`?app=controller_demo`)
- `apps/loader_demo.py` — Asset loader, GLB / audio / textures (`?app=loader_demo`)
- `apps/splats_demo.py` — Gaussian splats as a first-class primitive (`?app=splats_demo`)
- `apps/integrations_demo.py` — Storage / WASM / audio / media / serial (`?app=integrations_demo`)
- `apps/xr_demo.py` — WebXR (`?app=xr_demo`)

### 🛠 Creating a New App

1. Create `apps/my_app.py`:

```python
from scs import *

def onAppStart(app):
    app.stepsPerSecond = 30
    app.x = 200

def onStep(app):
    app.x = (app.x + 2) % app.width

def redrawAll(app):
    drawCircle(app.x, 200, 20, fill='cyan')
```

2. Run:

```
http://localhost:8000/?app=my_app
```

That's it. No registration needed.

### 🔌 Creating a New Extension

Want `extensions.storage`, `extensions.geolocation`, `extensions.sound`?

**Rules (strict MVC):**
1. **Model-only** — no `import scs`, no `draw*`, no `app.*`
2. **Browser-aligned** — mirror the Web API (MDN)
3. **Async where browser is async** — `async def` + `await window.xxx`
4. **Provide both shim and package** — `extensions.py` root + `extensions/your_ext.py`

Template:

```python
# extensions/my_ext.py
from browser import window, aio

async def do_thing(url):
    return await window.myAPI(url)

__all__ = ['do_thing']
```

Add to `extensions.py` shim:

```python
import types, sys
mod = types.ModuleType('extensions.my_ext')
mod.do_thing = do_thing
sys.modules['extensions.my_ext'] = my_mod
```

Use:

```python
from extensions.my_ext import do_thing
```

### 📖 API Notes

SCS implements the CMU Graphics exact API plus fixes:

| Area | Details |
|------|---------|
| Shapes | `Rect`, `Oval`, `Circle`, `Line`, `Polygon`, `RegularPolygon`, `Star`, `Label`, `Arc`, `Group`, `Image` |
| Draw | `drawRect`, `drawOval`, `drawCircle`, `drawLine`, `drawPolygon`, `drawLabel`, `drawArc`, `drawImage` — all accept `align`, `opacity`, `rotateAngle`, `visible`, `dashes` |
| Props | `fill`, `border`, `borderWidth`, `opacity`, `rotateAngle`, `align` (`center`, `left`, `right`, `top`, `bottom`, `leftTop`, etc.), `roundness`, `dashes` are general |
| App | `App(width, height)`, `app.width`, `app.height`, `app.background`, `stepsPerSecond`, `paused` |
| Events | `onAppStart`, `onStep`, `redrawAll`, `onMousePress/Release/Drag/Move`, `onKeyPress/Release/Hold`, `onResize` |
| Utils | `rgb(r,g,b)`, `gradient(*colors, start=)`, `distance()`, `angleTo()`, `getPointInDir()`, `rounded()`, `makeList()` |
| Extensions | `extensions.fetch` — `fetch()`, `fetch_json()`, `fetch_text()`, `FetchResponse`, `FetchError` |
| Renderers | `run_app(renderer='2d' | 'webgl2' | 'webgpu' | 'auto')`, `setRenderer()`, `?renderer=` |
| XR | `startXR()`, `stopXR()`, `renderFrame()`, `getXRState()`, `getXRCapability()` |
| Splats | `getSplatRenderer()`, `createSplatSchema()`, `createSplatAsset()`, `loadSplatManifest()` |

**Brython-safe logging:** Uses `chr(10)` not `\n` inside string literals to avoid Brython parse errors.

### 🧠 Architecture

```
index.html / sandbox.html
  ├── brython({pythonpath:['.']})  → finds extensions.py + extensions/
  ├── <script id="scs">  → scs.py — App, _start_app, loop()
  └── <script id="main">  → loader
        ├── get_requested_app_filename()  → ?app= → apps/*.py
        ├── window.fetch(apps/<name>.py) → text
        └── exec_user_code() → custom runApp → auto-start → _start_app → loop()

scs.py loop:
  onKeyHold → onStep → clear → background → redrawAll → _draw_all_shapes()
  interval = 1000 / stepsPerSecond

extensions.fetch:
  window.fetch (Promise) → await → FetchResponse
      ↘ fallback aio.fetch
  FetchResponse.json() → Python dict/list

scs_entrypoint.py:
  run_app(renderer=...) → 2D / WebGL2 / WebGPU, auto fallback
  startXR() → XR loop → renderFrame(frameContext)
```

### 🔒 Security

- URL param is sanitized: only `a-zA-Z0-9_-` kept
- `..`, `/`, `\` blocked
- All loads constrained to `apps/` folder
- Extensions enforce CORS via `mode='cors'`

### 🤝 Contributing

1. Add your app to `apps/your_name.py`
2. Test via `?app=your_name`
3. Add extension to `extensions/` if you need browser APIs
4. PR with a screenshot/GIF

Keep apps valid CMU Graphics — don't touch the loader to fix an app. If something doesn't animate, fix `scs.py`.

Extensions must be Model-only. No drawing in `extensions/`.

### License

MIT — use it for teaching, demos, student work.

---

Built for CMU CS Academy style code, running at 60fps in the browser. No build step. No bundler. Just Python.

Now with Extensions — because your CMU app deserves the real web.
