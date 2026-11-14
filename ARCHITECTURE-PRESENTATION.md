# SCS Fullscreen / Presentation — the 5 decisions

Fullscreen is an **async presentation mode**, not a canvas resize.
The unit is the **presentation container** (canvas + DOM UI), not the
canvas alone. CSS size, physical pixels, and rendering resolution are
three separate numbers.

## Decision map

| # | Decision | SCS answer | Where |
|---|----------|------------|-------|
| 1 | Async presentation mode, not resize | `enterFullscreen(element) -> Promise`, `exitFullscreen()`; state derived from `document.fullscreenElement` + `fullscreenchange`, never an optimistic Boolean; rejected requests report + preserve embedded mode; request made directly from a user gesture, never deferred behind asset loading | `scs_presentation.PresentationController`, `scs_entrypoint.enterFullscreen` |
| 2 | Fullscreen a container, not the canvas | Container = canvas's parent when present, so DOM UI siblings accompany the canvas; overlay slot for menus / captions / loading / exit button as semantic DOM buttons, not canvas-redrawn controls; keyboard nav + focus restoration in the contract; browser exit preserved; pointer/keyboard capture separate, opt-in | `PresentationController`, `make_exit_button`, `add_to_overlay` |
| 3 | CSS / physical / render resolution separate | `DisplayMetrics`: CSS size, `dpr`, `render_scale`, `effective_dpr`, backing size; `devicePixelContentBoxSize` preferred, CSS×DPR fallback; `render_scale` + `pixel_ratio_cap` + `pixel_budget` published to effects + input; DPR 3 = 9× pixels of DPR 1 at same CSS area | `scs_presentation.DisplayMetrics`, `scs_core.DisplayConfig` |
| 4 | Coordinated resize | ONE `apply_size(metrics)` per renderer updates drawing buffer + aspect + viewport + depth/MSAA + post + picking together; `ResizeCoordinator` coalesces notifications, applies newest at a frame boundary, reallocates only on change; zero-sized containers skip rendering without allocating; pointer conversion uses current bounds + buffer scale, never screen dims | `scs_presentation.ResizeCoordinator`, `client_to_drawing_buffer`, renderer `apply_size` |
| 5 | Mobile / embedding / cleanup explicit | Feature-detect fullscreen + CSS viewport-filling fallback; host owns `<meta viewport>` — SCS never disables zoom; `visualViewport` keyboard shrink is NOT a layout resize; listeners scoped to presentation surface; `dispose()` removes observers/listeners, restores styles/focus/capture | `PresentationController.dispose`, `_listen_visual_viewport` |

## Modes (separate, sharing sizing)

- `embedded` — fills its container.
- `viewport` — fills the browser viewport via CSS (fallback when the
  Fullscreen API is unavailable).
- `fullscreen` — browser Fullscreen API on the container.

## Sizing example

```python
# 800×600 CSS, DPR 3, render_scale 0.5, cap 2.0, budget 4M:
# effective DPR = min(3*0.5, 2.0) = 1.5 -> backing 1200×900
# Without the cap, DPR 3 alone would be 2400×1800 = 4.32M px.
metrics = getDisplayMetrics()
# {'display': {'css_width': 800, ...},
#  'drawing_buffer': {'width': 1200, 'height': 900, ...}}
```

## What SCS deliberately does NOT do

- Never treats fullscreen as "render at max DPR".
- Never derives state from an optimistic flag — `is_fullscreen()`
  reads `document.fullscreenElement`.
- Never disables user zoom or writes page viewport config.
- Never treats an on-screen keyboard shrinking the *visual* viewport
  as a layout resize.
- Never leaves observers / listeners / styles / focus behind on exit.
