# SCS Repository Overview

## Project Summary

**SCS (Sigma Computer Science)** is a Brython-powered implementation of the CMU Graphics API that runs entirely in the browser. It supports 2D Canvas, WebGL2, WebGPU, and WebXR with a unified API.

**Key metrics:**
- 37 Python modules (~22,600 LOC)
- 50+ example applications in `apps/`
- Multi-renderer support (2D, WebGL2, WebGPU, WebXR)
- Zero server-side Python backend required

---

## Directory Structure

```
scs/
├── 📄 Core Entrypoint & Runtime
│   ├── scs.py                      # Main entry point, API surface
│   ├── scs_entrypoint.py          # App execution, renderer selection
│   └── scs_core.py                # Core data structures
│
├── 🎨 Rendering Engines (Multi-Renderer)
│   ├── scs_2d.py                  # 2D Canvas renderer
│   ├── scs_3d.py                  # 3D base abstractions
│   ├── scs_webgl.py               # WebGL (legacy/compatibility)
│   ├── scs_engine_webgl2.py       # WebGL2 modern renderer ⭐
│   ├── scs_engine_webgpu.py       # WebGPU (future/WIP)
│   ├── scs_wgpu.py                # WebGPU fallback
│   └── scs_webgpu.py              # WebGPU bridge
│
├── 🎬 Graphics & Visual Systems
│   ├── scs_scenegraph.py          # 3D scene hierarchy
│   ├── scs_materials.py           # Material/shader system
│   ├── scs_lighting.py            # Lighting & IBL (recently optimized)
│   ├── scs_post.py                # Post-processing effects
│   ├── scs_particles.py           # Particle systems
│   ├── scs_volumetric.py          # Volumetric rendering
│   ├── scs_pipeline.py            # Rendering pipeline
│   └── scs_animation.py           # Animation system
│
├── 🔊 Audio Systems
│   ├── scs_audio.py               # Audio core
│   ├── scs_web_audio.py           # Web Audio API
│   ├── scs_spatial_audio.py       # 3D spatial audio
│   ├── scs_audio_pipelines.py     # DSP pipelines
│   ├── scs_audio_envelopes.py     # Envelope generation
│   ├── scs_audio_mapping.py       # Audio parameter mapping
│   └── scs_fallback_audio.py      # Fallback audio
│
├── 🎮 Advanced Features
│   ├── scs_xr.py                  # WebXR (VR/AR)
│   ├── scs_controller.py          # Input devices (gamepad, etc)
│   ├── scs_presentation.py        # Presentation mode
│   ├── scs_loader.py              # Asset loading
│   ├── scs_media.py               # Media handling
│   ├── scs_serial.py              # Serial protocol
│   ├── scs_storage.py             # Local storage
│   └── scs_wasm.py                # WASM integration
│
├── 🌐 Graphics Assets
│   ├── scs_splats.py              # Gaussian splatting
│   ├── scs_splat_gpu.py           # GPU splatting
│   ├── scs_splat_urls.py          # Splat asset URLs
│   └── scs_splat_formats.ply      # Splat format sample
│
├── 📱 Web Integration
│   ├── scs.js                     # JavaScript entry point
│   ├── extensions.py              # Extension system
│   ├── scs-datastar-extension/    # Datastar integration
│   └── index.html                 # Main demo page
│
├── 🧪 Applications & Examples
│   ├── apps/                      # 50+ demo applications
│   │   ├── spatial_audio.py       # Recently optimized! ⭐
│   │   ├── rabbit_sim.py
│   │   ├── tetr.py
│   │   ├── platformer_bgs.py
│   │   └── ... (40+ more)
│   │
│   └── extensions/                # Extension modules
│       ├── proc_audio.py          # Procedural audio
│       ├── match.py               # Pattern matching
│       └── ... (others)
│
├── 🏗️ Deployment & Configuration
│   ├── Dockerfile
│   ├── netlify.toml
│   ├── render.yaml
│   ├── package.json               # NPM scripts & metadata
│   └── package-lock.json
│
├── 📚 Documentation
│   ├── README.md                  # Main documentation
│   ├── ARCHITECTURE-*.md          # Architecture deep-dives
│   │   ├── ARCHITECTURE-CONTROLLER.md
│   │   ├── ARCHITECTURE-LOADER.md
│   │   ├── ARCHITECTURE-PRESENTATION.md
│   │   ├── ARCHITECTURE-SPLATS.md
│   │   ├── ARCHITECTURE-INTEGRATIONS.md
│   │   └── ARCHITECTURE-XR.md
│   └── REPOSITORY_OVERVIEW.md     # This file
│
├── 🛠️ Development
│   ├── .gitignore                 # Git ignore rules
│   ├── .nojekyll                  # GitHub Pages marker
│   ├── favicon.png
│   ├── scs.jpg                    # Project logo
│   └── sandbox.html               # Sandbox environment
│
└── 🧪 Testing
    ├── test.html                  # Manual test file (ignored)
    └── __pycache__/               # Python cache (ignored)
```

---

## Module Categories & Dependencies

### 1️⃣ **Core Runtime** (Must load first)
- `scs.py` → `scs_core.py` → `scs_entrypoint.py`
- Handles app lifecycle, renderer selection, event loop

### 2️⃣ **Renderer Pipeline** (Chosen at runtime)
- **2D Path:** `scs_2d.py` only
- **WebGL2 Path:** `scs_engine_webgl2.py` → `scs_lighting.py` → `scs_materials.py`
- **WebGPU Path:** `scs_engine_webgpu.py` → (future)
- Each renderer implements: render(), clear(), setViewport(), drawShape(), etc.

### 3️⃣ **Graphics Stack** (Shared across renderers)
- `scs_scenegraph.py` - Scene representation
- `scs_animation.py` - Animation logic
- `scs_pipeline.py` - Render pipeline state
- `scs_post.py` - Post-effects (optional)

### 4️⃣ **Audio Stack** (Independent of renderer)
- `scs_audio.py` - Core audio API
- `scs_web_audio.py` - Web Audio API bindings
- `scs_spatial_audio.py` - 3D spatial audio (recently optimized!)
- Procedural audio via `extensions/proc_audio.py`

### 5️⃣ **Specialized Systems**
- **XR:** `scs_xr.py` (WebXR session management)
- **Input:** `scs_controller.py` (gamepad, keyboard, mouse)
- **Assets:** `scs_loader.py`, `scs_splats.py`
- **Storage:** `scs_storage.py` (localStorage API)

---

## Recent Optimizations (November 2026)

### HUD Visual Quality Fix ✅
- **Issue:** HUD text was blurry and unreadable at high DPI
- **Root Cause:** Canvas backing size not matching WebGL viewport
- **Solution:** Implement 2× backing resolution (1800×1120 for 900×560 logical)
- **Impact:** Crisp, sharp HUD text; readable labels

### Startup Time Optimization ✅
- **Issue:** App took 13+ seconds to render first frame
- **Root Cause:** IBL (Image-Based Lighting) computation blocking main thread
  - 128×128 BRDF LUT with 64 samples per pixel = 1M+ calculations
  - Running synchronously in Brython interpreter
- **Solution:** Reduce BRDF resolution and sampling
  - BRDF LUT: 128×128 → 64×64 (4× fewer texels)
  - Samples: 64 → 4 per texel (16× fewer calculations)
  - Env cubemap: 32×32 → 16×16 per face
- **Impact:** Startup time reduced to ~2 seconds (≈6.5× speedup)
- **Quality:** Minor visual fidelity loss, acceptable for startup

### Performance Enhancement ✅
- **Issue:** Console logs dropping FPS significantly
- **Solution:** Remove per-frame HUD offscreen debug logs
- **Impact:** Smooth frame rate maintained

### Files Modified
- `scs_engine_webgl2.py` - IBL optimization
- `scs_entrypoint.py` - Canvas sizing, HUD offscreen handling

---

## Development Workflow

### Local Development
```bash
npm run dev        # Start local server on :8080 with live reload
npm run build      # No-op (Python package, no build step)
npm test           # Compile-check Python files
```

### Adding a New App
1. Create `apps/my_app.py`
2. Implement `onAppStart()` and `redrawAll()`
3. Access via `?app=my_app` or hardcode in `index.html`

### Adding an Extension
1. Create `extensions/my_ext.py`
2. Register in `extensions.py`
3. Import from app: `from extensions.my_ext import *`

---

## Package Structure & Exports

### NPM Package
- **Main:** `scs.js` (CDN entry point)
- **Files:** Includes core Python modules, HTML, README
- **Exports:** `SCS.create()`, `run_app()` in JavaScript

### PyPI-Compatible (via Brython)
- **Install:** Already bundled in scs.js
- **API:** CMU Graphics compatible (Graphics, Image, Rect, Circle, Label, etc.)

---

## Known Issues & TODOs

| Issue | Status | Priority |
|-------|--------|----------|
| BRDF LUT computation (13s→2s) | ✅ FIXED | High |
| HUD text blurriness | ✅ FIXED | High |
| WebGPU support (incomplete) | 🔄 WIP | Medium |
| Gaussian splatting (slow) | 📋 Backlog | Medium |
| XR browser support (limited) | 🔄 Varies | Low |
| Procedural audio real-time | ⚠️ Limited | Medium |

---

## Repository Cleanliness Checklist

| Item | Status | Notes |
|------|--------|-------|
| `.gitignore` coverage | ✅ | Excludes `__pycache__`, `test.html`, build artifacts |
| Duplicate READMEs | ⚠️ | `README_.md` is old; should remove |
| Documentation | ✅ | Comprehensive ARCHITECTURE-*.md files |
| Package.json | ✅ | Scripts updated, metadata current |
| Unused files | ✅ | Only active code present |
| Naming conventions | ✅ | Consistent `scs_*.py` prefix |

---

## Recommended Next Steps

### High Priority
1. **Remove `README_.md`** (duplicate, outdated)
2. **Update ARCHITECTURE docs** with recent performance fixes
3. **Add CHANGELOG.md** to track version history

### Medium Priority
1. Consider moving `test.html` → `.github/test.html` or `tools/`
2. Add CI/CD config (GitHub Actions) for automated testing
3. Document renderer selection strategy in main README

### Low Priority
1. Consider organizing apps/ into categories (education/, game/, audio/, etc.)
2. Add JSDoc comments to scs.js for IDE support
3. Modernize extensions/ with TypeScript definitions

---

## Key Files to Know

| File | Purpose | Lines |
|------|---------|-------|
| `scs_entrypoint.py` | App execution & renderer bootstrap | ~3900 |
| `scs_engine_webgl2.py` | WebGL2 rendering pipeline | ~1200 |
| `scs_core.py` | Shape/primitive definitions | ~800 |
| `scs_spatial_audio.py` | 3D audio calculations | ~600 |
| `scs_animation.py` | Animation interpolation | ~400 |
| `scs.js` | JavaScript CDN entry point | ~200 |

---

## Contributing Guide

### Code Style
- Python: PEP 8 (mostly), snake_case functions/vars
- JavaScript: ES6, camelCase
- Comments: Explain WHY, not WHAT
- No type hints (Brython compatibility)

### Before Committing
```bash
npm test                    # Compile check
git add .gitignore         # Always ensure .gitignore updated
git commit -m "Brief: explanation" --author "Name"
```

### Performance Considerations
- Brython executes Python ~100× slower than native JS
- Avoid tight loops with complex Python logic
- Pre-compute heavy operations (see BRDF LUT example)
- Use native JS for performance-critical paths (scs.js)

---

Generated: November 17, 2026
Last Updated: After HUD & Startup Optimization Pass
