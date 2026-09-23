![SCS : Sigma Computer Science](scs.jpg)

# SCS : Sigma Computer Science

> A fast, faithful, Brython-powered implementation of the **CMU Graphics** API that runs natively in the browser. No install. No Python backend. Just open `index.html`.

[![Brython](https://img.shields.io/badge/Brython-3.11.3-blue)](https://brython.info/)
[![CMU Graphics](https://img.shields.io/badge/API-CMU%20Graphics-red)](https://academy.cs.cmu.edu/)
[![License](https://img.shields.io/badge/license-MIT-black)](LICENSE)
[![Apps](https://img.shields.io/badge/apps-4-green)](#apps-included)

Live demo:
<a href="https://ericeisaman.github.io/scs/" target="_blank" rel="noopener noreferrer">
  https://ericeisaman.github.io/scs/
</a>
— loads <code>apps/app.py</code>

<br>

Try: <code>?app=rabbit_sim</code> →
<a href="https://ericeisaman.github.io/scs/?app=rabbit_sim" target="_blank" rel="noopener noreferrer">
  https://ericeisaman.github.io/scs/?app=rabbit_sim
</a>

<br>

Sandbox: <code>/sandbox</code> →
<a href="https://ericeisaman.github.io/scs/sandbox" target="_blank" rel="noopener noreferrer">
  https://ericeisaman.github.io/scs/sandbox
</a>

---

### What is this?

SCS is a drop-in browser runtime for CMU Graphics / `cmu_graphics` coursework. You write the same `onAppStart`, `onStep`, `redrawAll`, `onMousePress` code you would in CMU Academy, and it runs on an HTML canvas via Brython.

This repo includes:

- **`scs.py`** — the full API shim (`Rect`, `Oval`, `Circle`, `Label`, `Line`, `Polygon`, `Group`, `Image`, `Sound`, `draw*`, `rgb()`, `gradient()`, `distance()`, `angleTo()`, etc.) with **align as a true general property**
- **`index.html`** — production viewer. Loads apps from `apps/` via URL param `?app=` — now with auto-start + `window.fetch` loader
- **`sandbox.html`** — live editor. Edit code in a textarea and hit Run — also auto-starts
- **`extensions/`** — **NEW: SCS Extensions System** — pure Model-layer libraries that bring the browser to your CMU app
- **`apps/`** — all runnable apps. No root duplication.

---

## 🌟 NEW: The SCS Extensions System — The Browser Is Now Your Model

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

- `extensions.py` — root shim implementing full API and injecting `sys.modules['extensions.fetch']`
- `extensions/__init__.py` + `extensions/fetch.py` — real package

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
├── index.html          # Viewer — loads from apps/ via ?app=, auto-start, window.fetch
├── sandbox.html        # Editor — edit + Run, auto-start, pythonpath=['.']
├── scs.py              # CMU Graphics API (Brython)
├── app.py              # DEPRECATED placeholder (see apps/app.py)
├── extensions.py        # Root shim — makes `import extensions` work in Brython
├── extensions/         # SCS Extensions System (NEW!)
│   ├── __init__.py     # Package marker
│   └── fetch.py        # Async Fetch — browser-aligned, Model-only
└── apps/
    ├── app.py              → Joukowski Aerofoil Wind Tunnel (default)
    ├── rabbit_sim.py       → Rabbit Meadow Population Dynamics
    ├── rabbit_valid_cmu.py → Original valid CMU version
    ├── rabbit_fixed.py     → Fixed anim-every-frame version
    └── fetch_demo.py       → Extensions.fetch — PoetryDB live (NEW!)
```

No root `app.py` duplication — real apps are **only** in `apps/`.

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
