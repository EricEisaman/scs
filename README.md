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

---

### What is this?

SCS is a drop-in browser runtime for CMU Graphics / `cmu_graphics` coursework. You write the same `onAppStart`, `onStep`, `redrawAll`, `onMousePress` code you would in CMU Academy, and it runs on an HTML canvas via Brython.

This repo includes:

- **`scs.py`** — the full API shim (`Rect`, `Oval`, `Circle`, `Label`, `Line`, `Polygon`, `Group`, `Image`, `Sound`, `draw*`, `rgb()`, `gradient()`, `distance()`, `angleTo()`, etc.) with **align as a true general property**
- **`index.html`** — production viewer. Loads apps from `apps/` via URL param `?app=`
- **`sandbox.html`** — live editor. Edit code in a textarea and hit Run
- **`apps/`** — all runnable apps. No root duplication.

### ✨ Catalog Your Creations in the apps Directory

Default: `apps/app.py`

**Safe loader**
- Blocks `..` and absolute paths
- Sanitizes to `[a-zA-Z0-9_-]`
- Graceful fallback to `apps/app.py`

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
http://localhost:8000/sandbox.html         → Live editor
```

### 📁 Project Structure

```
/
├── index.html          # Viewer — loads from apps/ via ?app=
├── sandbox.html        # Editor — edit + Run in browser
├── scs.py              # CMU Graphics API (Brython)
├── app.py              # DEPRECATED placeholder (see apps/app.py)
└── apps/
    ├── app.py              → Joukowski Aerofoil Wind Tunnel (default)
    ├── rabbit_sim.py       → Rabbit Meadow Population Dynamics
    ├── rabbit_valid_cmu.py → Original valid CMU version
    └── rabbit_fixed.py     → Fixed anim-every-frame version
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

### 🛠️ Creating a New App

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

**Brython-safe logging:** Uses `chr(10)` not `\n` inside string literals to avoid Brython parse errors.

### 🧠 Architecture

```
index.html
  ├── <script id="scs">  → scs.py inlined (or imported)
  └── <script id="main">  → loader
        ├── get_requested_app_filename()  → parses ?app= → apps/*.py
        ├── ajax GET apps/<name>.py
        └── exec_user_code() → custom runApp → _start_app → loop()
```

`scs.py` main loop:
```python
def loop():
    onKeyHold → onStep → clear → draw background → redrawAll → _draw_all_shapes()
    interval = 1000 / stepsPerSecond
```

### 🔒 Security

- URL param is sanitized: only `a-zA-Z0-9_-` kept
- `..`, `/`, `\` blocked
- All loads constrained to `apps/` folder

### 🤝 Contributing

1. Add your app to `apps/your_name.py`
2. Test via `?app=your_name`
3. PR with a screenshot/GIF

Keep apps valid CMU Graphics — don't touch the loader to fix an app. If something doesn't animate, fix `scs.py`.

### License

MIT — use it for teaching, demos, student work.

---

Built for CMU CS Academy style code, running at 60fps in the browser. No build step. No bundler. Just Python.
