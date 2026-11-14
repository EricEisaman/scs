# SCS WebXR Architecture — the 10 decisions

XR is a **mode transition**, not a second renderer and not a rewrite.
The scene API (`Rect`, `Label`, `Group`, `drawRect`, `onStep`,
`redrawAll`) does not change. What changes is who owns the loop,
the camera, and the target.

```
Desktop:  SCS owns loop + camera + canvas target
XR:       runtime owns loop + views + compositor targets
          SCS owns scene + simulation + per-view rendering
```

## The boundary: FrameContext

`scs_xr.FrameContext` is the one object that crosses the boundary:

```python
FrameContext(
    views=[View(...), View(...)],   # supplied by the runtime
    timestamp=...,                   # XR frame time
    reference_space=Space(...),      # 'local' / 'local-floor' / ...
    input_sources=[XRInputSource(...)],
    session=...,
)
```

`renderFrame(frame_ctx)` renders current app state for those views.
It never calls `onStep`. That is the whole scheduling contract.

## Decision map

| # | Decision | SCS answer | Where |
|---|----------|------------|-------|
| 1 | Externally-driven loop | `renderFrame(FrameContext)`; `_step()` split from `_render()`; XR uses `XRSession.requestAnimationFrame`, desktop loop stops on enter | `scs_entrypoint.renderFrame`, `_step`, `_render`, `startXR` |
| 2 | Frame = collection of views | `View` per runtime view; projection/view matrices passed through verbatim, never derived from SCS camera FOV, never assumed symmetric; AR = 1 view | `scs_xr.View`, `FrameContext.from_xr_frame` |
| 3 | Explicit coordinate spaces | `Space` (AppWorld / ReferenceSpace / TrackedSpace) + `Locomotion` as the ONE world-placement transform; `world = Reference * Locomotion * Tracked` | `scs_xr.Space`, `Locomotion`, `mat4_*` |
| 4 | Borrowed, frame-scoped targets | `BorrowedTarget.dispose()` is a no-op; backends bind borrowed framebuffer / texture view, never resize/destroy | `scs_xr.BorrowedTarget`, `scs_webgl._submit`, `scs_webgpu._submit` |
| 5 | XR behind capability interface | `XRCapability` + `probe_xr_capability()`; WebGPU-XR tested separately from WebGPU; `WebGLXRPresentation` (`XRWebGLLayer`) vs `WebGPUXRPresentation` (`XRGPUBinding`); unsupported combos fail in `enter()` | `scs_xr.XRCapability`, `XRPresentation`, `XRSessionManager.enter` |
| 6 | Multi-view ≠ multiview GPU | Sequential rendering is the baseline (`render_views_sequentially`); multiview is a capability-gated optimisation (`render_views_multiview`); per-view camera data distinct from per-object/material | `scs_xr.render_views_*`, `scs_entrypoint._render_one_view` |
| 7 | Post-processing explicit | `PostPassDescriptor` carries view viewport, texture view, array slice, formats, depth availability; `needs_intermediate` → own intermediate, never resize borrowed target | `scs_xr.PostPassDescriptor` |
| 8 | Compositor layers | `CompositorLayer` (quad/cylinder/equirect/projection), capability-gated, fallback = scene geometry | `scs_xr.CompositorLayer` |
| 9 | Input = sources + actions | `XRInputSource`: `targetRaySpace != gripSpace`, grip may be `None`; `select` / `squeeze` semantic actions; `raycast()` (scene) vs `hit_test()` (real world) never conflated; app callbacks `onXRSelect` / `onXRSqueeze` / `onXRInput` | `scs_xr.XRInputSource`, `scs_entrypoint.startXR` |
| 10 | XR lifecycle = ordinary states | `XRSessionManager`: `not-started → requesting → running → tracking-lost → ended / failed`; async setup, symmetric teardown restores desktop loop; `getViewerPose() == null` → empty views → skip drawing, keep loop | `scs_xr.XRSessionManager`, `scs_entrypoint.stopXR` |

## What SCS deliberately does NOT do

- **No XR camera overrides.** There is no `app.xrCamera`. Views arrive
  with their matrices; the scene never rewrites them.
- **No FOV-derived projections.** SCS never computes a projection matrix
  from a field of view. If a view has no projection, it is identity —
  the runtime is the authority.
- **No owned XR targets.** SCS never calls `resize()` or `destroy()`
  on a `BorrowedTarget`. The 2D backend rejects borrowed targets
  predictably (`UnsupportedError`) instead of faking XR.
- **No simulation in rendering.** `renderFrame()` with 2 views calls
  `onStep` zero times. The desktop `_frame()` calls it exactly once.
- **No multiview requirement.** A backend without multiview still
  renders XR correctly, sequentially. Multiview is performance, not
  correctness.

## Per-view rendering flow

```
XRSession.requestAnimationFrame(frame)
  -> XRSessionManager._on_xr_frame
    -> FrameContext.from_xr_frame()   # [] if pose is null
    -> Presentation.acquire()         # borrowed targets + viewports
    -> on_frame(frame_ctx)
      -> renderFrame(frame_ctx)
        -> for each view:
             renderer.begin_frame(bg, target=view.target,
                                  viewport=view.viewport)
             renderer.push_view(view)  # camera only
             redrawAll(app) + display list
             renderer.pop_view()
             renderer.end_frame()      # submits to THAT view's target
```

Shared scene preparation (`redrawAll`, shape list) runs per view, but
geometry is collected per view into that view's target — uploads are
per view because targets differ, simulation is not repeated.

## Testing without a headset

`FrameContext.desktop(w, h)` and `scs_xr.View` with hand-made matrices
let every path above run on desktop: two views with different
viewports / cameras render the same scene twice, proving the loop,
target, and camera separation without XR hardware. See
`apps/xr_demo.py`.
