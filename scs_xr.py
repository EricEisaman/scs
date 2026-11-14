"""
scs_xr.py - WebXR integration for SCS (clean integration, not a rewrite).

The key shift (see ARCHITECTURE_XR.md): XR supplies frame timing,
tracked views, and presentation targets. SCS must NOT assume it owns
any of them.

    Desktop loop (owned by SCS):
        requestAnimationFrame -> _step() -> _render(one camera, canvas)

    XR loop (owned by the runtime):
        XRSession.requestAnimationFrame(frame)
            -> renderFrame(FrameContext)   # NO onStep here
            -> per view: prepare once, render to borrowed target

Architecture:

    scs_entrypoint  -- scene API, simulation (onStep), renderFrame()
    scs_xr          -- THIS FILE: FrameContext, View, Space, Session,
                       InputSource, Presentation, Layers  (XR concepts)
    scs_core        -- Pass / Pipeline / Texture / Capability (shared)
    backends        -- 2D / WebGL2 / WebGPU: render a View into a
                       borrowed target. They never own XR state.

Rules enforced here:
  1. renderFrame() never advances simulation (no onStep per view).
  2. A frame is a collection of Views, never 1 camera or exactly 2 eyes.
     Projection matrices are SUPPLIED by the runtime, never derived
     from an SCS camera FOV, never assumed symmetric.
  3. Coordinate spaces are explicit: AppWorld != ReferenceSpace !=
     TrackedSpace. Locomotion composes in one place.
  4. Render targets can be BORROWED: never resized / destroyed by SCS.
  5. XR presentation is behind a capability interface; WebGPU-XR is
     NOT implied by WebGPU support (capability-tested separately).
  6. Sequential multi-view rendering is the baseline; multiview is an
     optimisation gated on capability, not a redesign.
  7. Post-processing knows its view's viewport / slice / formats /
     depth availability; no full-canvas assumption.
  8. Compositor layers are optional, capability-gated, with a
     scene-geometry fallback.
  9. Input = tracked sources + semantic actions (select/squeeze),
     targetRaySpace != gripSpace, grip may be absent. Raycast != hit-test.
 10. XR entry/exit/unavailable-tracking are ordinary lifecycle states.
     getViewerPose() returning None never throws.
"""

import math

try:
    from browser import window
except ImportError:
    window = None


# ----------------------------------------------------------------------
# Coordinate spaces (Decision 3)
# ----------------------------------------------------------------------
# AppWorld: where SCS shapes live (the 2D scene, in CSS pixels).
# ReferenceSpace: the XR space the app chose ('local', 'local-floor',
#   'bounded-floor', 'unbounded'). Poses are resolved RELATIVE to it.
# TrackedSpace: raw device / controller tracking.
# Composition (one place, never scattered into scene objects):
#   world = ReferenceSpace * Locomotion * Tracked
# Locomotion (teleport / joystick move) moves the WORLD, never the
# tracked head pose. That is the whole point of keeping them distinct.

_IDENTITY_4 = (1.0, 0.0, 0.0, 0.0,
              0.0, 1.0, 0.0, 0.0,
              0.0, 0.0, 1.0, 0.0,
              0.0, 0.0, 0.0, 1.0)


def mat4_translation(x, y, z=0.0):
    return (1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            float(x), float(y), float(z), 1.0)


def mat4_multiply(a, b):
    """Column-major 4x4 multiply (WebXR / WebGL convention)."""
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            out[col * 4 + row] = sum(
                a[k * 4 + row] * b[col * 4 + k] for k in range(4))
    return tuple(out)


def mat4_for_2d_camera(offset_x, offset_y, scale=1.0, rotation_deg=0.0):
    """2D camera as a 4x4: scale -> rotate -> translate. SCS shapes are
    2D; the XR view's 3D projection (below) is applied by the runtime /
    compositor, NOT derived here from FOV."""
    a = math.radians(rotation_deg)
    ca, sa = math.cos(a) * scale, math.sin(a) * scale
    return (ca, sa, 0.0, 0.0,
            -sa, ca, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            float(offset_x), float(offset_y), 0.0, 1.0)


class Space:
    """A named coordinate space with a matrix relative to its parent.
    `reference` is the XRReferenceSpace type when this IS that space."""

    def __init__(self, name, matrix=None, reference=None):
        self.name = name
        self.matrix = tuple(matrix) if matrix is not None else _IDENTITY_4
        self.reference = reference  # e.g. 'local-floor' or None

    def compose(self, other):
        """self * other: apply other first, then self."""
        return Space(self.name + '*' + other.name,
                     mat4_multiply(self.matrix, other.matrix))

    def __repr__(self):
        return 'Space(%s, ref=%s)' % (self.name, self.reference)


class Locomotion:
    """The ONE place world-placement lives. Moving the world = updating
    this transform. Tracked poses are never rewritten."""

    def __init__(self):
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.offset_z = 0.0
        self.rotation_deg = 0.0
        self.scale = 1.0

    def move(self, dx, dy, dz=0.0):
        self.offset_x += dx
        self.offset_y += dy
        self.offset_z += dz

    def teleport_to(self, x, y, z=0.0):
        self.offset_x, self.offset_y, self.offset_z = float(x), float(y), float(z)

    def as_space(self):
        return Space('locomotion',
                     mat4_multiply(
                         mat4_translation(self.offset_x, self.offset_y, self.offset_z),
                         mat4_for_2d_camera(0, 0, self.scale, self.rotation_deg)))


# ----------------------------------------------------------------------
# Views + FrameContext (Decisions 1, 2, 6, 7)
# ----------------------------------------------------------------------

class View:
    """ONE view supplied by the runtime. Never constructed from an SCS
    camera: projection_matrix is the runtime's matrix (possibly
    asymmetric), viewport is the runtime's viewport, target is the
    runtime's (borrowed) attachment for this view."""

    def __init__(self, eye=None, projection_matrix=None,
                 view_matrix=None, viewport=None, target=None,
                 texture_view=None, array_slice=0, depth_available=None):
        self.eye = eye  # 'left' | 'right' | None (AR: one view, eye=None)
        # Opaque 4x4s, supplied by the runtime. SCS never derives them.
        self.projection_matrix = tuple(projection_matrix) if projection_matrix \
            else _IDENTITY_4
        self.view_matrix = tuple(view_matrix) if view_matrix else _IDENTITY_4
        # Viewport: (x, y, width, height) in the target's pixels.
        # NEVER assumed to be (0, 0, canvasW, canvasH).
        self.viewport = tuple(viewport) if viewport else (0, 0, 0, 0)
        # Borrowed presentation attachment for this view (Decision 4).
        self.target = target
        self.texture_view = texture_view
        self.array_slice = int(array_slice)
        self.depth_available = depth_available
        # 2D camera for SCS scene content inside this view: offset/scale
        # resolved from view_matrix + locomotion by the caller, kept
        # SEPARATE from per-object / per-material data (Decision 6).
        self.camera_2d = {'offset_x': 0.0, 'offset_y': 0.0,
                          'scale': 1.0, 'rotation_deg': 0.0}

    def camera_matrix(self):
        c = self.camera_2d
        return mat4_for_2d_camera(c['offset_x'], c['offset_y'],
                                  c['scale'], c['rotation_deg'])


class FrameContext:
    """The architectural boundary (Decision: 'most useful boundary').
    Everything a frame needs, nothing it must own:
      views, borrowed targets, tracking/input resolved FOR THIS FRAME."""

    def __init__(self, views=None, timestamp=0.0, predicted_display_time=None,
                 reference_space=None, input_sources=None, session=None):
        self.views = list(views) if views else []
        self.timestamp = timestamp
        self.predicted_display_time = predicted_display_time
        self.reference_space = reference_space  # Space, may be None
        self.input_sources = list(input_sources) if input_sources else []
        self.session = session
        # None pose == tracking unavailable: renderFrame() skips drawing
        # and keeps the loop alive (Decision 10). Views == [] encodes it.
        self.viewer_pose_available = len(self.views) > 0

    @classmethod
    def from_xr_frame(cls, xr_frame, reference_space, session=None):
        """Build from a real XRFrame. getViewerPose() may return null --
        that is a normal state, not an exception."""
        try:
            pose = xr_frame.getViewerPose(reference_space._xr_space)
        except Exception:
            pose = None
        if pose is None:
            return cls(views=[], reference_space=reference_space,
                       session=session)
        views = []
        try:
            xr_views = pose.views
        except Exception:
            xr_views = []
        for v in xr_views:
            # Projection / view matrices come from the runtime verbatim.
            views.append(View(
                eye=getattr(v, 'eye', None),
                projection_matrix=list(getattr(v, 'projectionMatrix', _IDENTITY_4)),
                view_matrix=list(getattr(v, 'transform', {}).matrix) if hasattr(getattr(v, 'transform', None), 'matrix') else None,
                viewport=(0, 0, 0, 0),  # filled by the presentation layer
                target=None,            # filled by the presentation layer
            ))
        return cls(views=views, reference_space=reference_space,
                   session=session)

    @classmethod
    def desktop(cls, width, height, camera_2d=None):
        """A single-view FrameContext for non-XR rendering. Lets desktop
        and XR share renderFrame(): desktop is just a 1-view frame."""
        v = View(eye=None, viewport=(0, 0, int(width), int(height)))
        if camera_2d:
            v.camera_2d.update(camera_2d)
        return cls(views=[v])


# ----------------------------------------------------------------------
# Presentation: borrowed targets behind a capability interface (Dec 4, 5)
# ----------------------------------------------------------------------

class BorrowedTarget:
    """A compositor-owned attachment. SCS may draw into it, never resize
    or destroy it. dispose() is a deliberate no-op -- ownership stays
    with the compositor (Decision 4)."""

    def __init__(self, label, framebuffer=None, texture=None,
                 texture_view=None, viewport=None, borrowed=True):
        self.label = label
        self.framebuffer = framebuffer  # WebGL: XRWebGLLayer framebuffer
        self.texture = texture          # WebGPU: compositor texture
        self.texture_view = texture_view
        self.viewport = viewport
        self.borrowed = borrowed

    def dispose(self):
        # Borrowed: nothing to free. This no-op is the ownership contract.
        return None


class XRPresentation:
    """Backend capability interface (Decision 5): 'render views' is
    separate from 'acquire + present XR attachments'."""

    backend = 'base'

    def acquire(self, frame_ctx, xr_frame, layer):
        """Return {view_index: BorrowedTarget} for this XRFrame."""
        raise NotImplementedError

    def present(self, xr_frame):
        return None


class WebGLXRPresentation(XRPresentation):
    backend = 'webgl2'

    def __init__(self, gl, xr_layer):
        self.gl = gl
        self.layer = xr_layer  # XRWebGLLayer, created during session setup

    def acquire(self, frame_ctx, xr_frame, layer=None):
        # WebGL exposes ONE opaque XR framebuffer for the whole frame;
        # per-view viewports come from XRWebGLLayer.getViewport(view).
        targets = {}
        try:
            fb = self.layer.framebuffer
            for i, view in enumerate(frame_ctx.views):
                try:
                    vp = self.layer.getViewport(view._xr_view)
                    viewport = (vp.x, vp.y, vp.width, vp.height)
                except Exception:
                    viewport = view.viewport
                targets[i] = BorrowedTarget(
                    'xr-webgl-view-%d' % i, framebuffer=fb, viewport=viewport)
        except Exception:
            pass
        return targets


class WebGPUXRPresentation(XRPresentation):
    backend = 'webgpu'

    def __init__(self, device, xr_binding):
        self.device = device
        self.binding = xr_binding  # XRGPUBinding

    def acquire(self, frame_ctx, xr_frame, layer=None):
        # WebGPU supplies compositor textures + per-view subimages:
        # texture view + viewport + array slice per view (Decision 4, 7).
        targets = {}
        try:
            for i, view in enumerate(frame_ctx.views):
                sub = self.binding.getViewSubImage(layer, view._xr_view)
                targets[i] = BorrowedTarget(
                    'xr-webgpu-view-%d' % i,
                    texture=sub.colorTexture,
                    texture_view=sub.colorTexture.createView(),
                    viewport=(sub.viewport.x, sub.viewport.y,
                              sub.viewport.width, sub.viewport.height))
        except Exception:
            pass
        return targets


# ----------------------------------------------------------------------
# Capability: XR is NOT implied by WebGPU/WebGL support (Decision 5)
# ----------------------------------------------------------------------

class XRCapability:
    def __init__(self, **kw):
        self.xr_available = kw.get('xr_available', False)
        self.supports_webgl_xr = kw.get('supports_webgl_xr', False)
        self.supports_webgpu_xr = kw.get('supports_webgpu_xr', False)
        self.supports_multiview = kw.get('supports_multiview', False)
        self.supports_layers = kw.get('supports_layers', False)
        self.supports_depth = kw.get('supports_depth', False)
        self.supports_hit_test = kw.get('supports_hit_test', False)
        self.session_modes = kw.get('session_modes', [])

    def require(self, what):
        ok = {
            'webgl_xr': self.supports_webgl_xr,
            'webgpu_xr': self.supports_webgpu_xr,
            'multiview': self.supports_multiview,
            'layers': self.supports_layers,
            'depth': self.supports_depth,
            'hit_test': self.supports_hit_test,
        }.get(what, False)
        if not ok:
            raise RuntimeError(
                'WebXR capability %r is not available on this backend/runtime. '
                'Check XRCapability before entering XR -- unsupported '
                'combinations fail at init, not mid-frame.' % what)

    def to_dict(self):
        return {
            'xr_available': self.xr_available,
            'supports_webgl_xr': self.supports_webgl_xr,
            'supports_webgpu_xr': self.supports_webgpu_xr,
            'supports_multiview': self.supports_multiview,
            'supports_layers': self.supports_layers,
            'supports_depth': self.supports_depth,
            'supports_hit_test': self.supports_hit_test,
            'session_modes': self.session_modes,
        }


def probe_xr_capability():
    """Capability-test the available path (Decision 5). No assumption
    that ordinary WebGPU support implies WebGPU-XR support."""
    cap = XRCapability()
    try:
        nav = window.navigator if window is not None else None
        if nav is None or getattr(nav, 'xr', None) is None:
            return cap
        cap.xr_available = True
        # WebGL-XR: XRWebGLLayer exists; WebGPU-XR: XRGPUBinding exists
        # AND navigator.gpu exists. Each tested independently.
        try:
            cap.supports_webgl_xr = getattr(window, 'XRWebGLLayer', None) is not None
        except Exception:
            pass
        try:
            cap.supports_webgpu_xr = (
                getattr(window, 'XRGPUBinding', None) is not None and
                getattr(nav, 'gpu', None) is not None)
        except Exception:
            pass
        # Layers / multiview / depth / hit-test are runtime features;
        # they are probed per-session, defaults are conservative False.
        cap.session_modes = ['inline', 'immersive-vr', 'immersive-ar']
    except Exception:
        pass
    return cap


# ----------------------------------------------------------------------
# Post-processing: explicit per-view attachments (Decision 7)
# ----------------------------------------------------------------------

class PostPassDescriptor:
    """Every screen-space pass knows its view's viewport, texture view /
    array slice, attachment formats, and depth availability. If it
    cannot run directly on an XR attachment, it uses an intermediate
    target (Decision 7) -- never the wrong eye / region."""

    def __init__(self, view, color_format='rgba8unorm',
                 depth_available=False, needs_intermediate=False):
        self.view = view
        self.viewport = view.viewport
        self.texture_view = view.texture_view
        self.array_slice = view.array_slice
        self.color_format = color_format
        self.depth_available = depth_available
        self.needs_intermediate = needs_intermediate
        # XR attachments are borrowed: a pass that needs to write to a
        # DIFFERENT target must allocate its own intermediate, never
        # resize the borrowed one.
        self.intermediate = None

    def require_intermediate(self, label='scs-post-intermediate'):
        if self.intermediate is None:
            self.intermediate = {'label': label, 'owned': True,
                                 'viewport': self.viewport}
        return self.intermediate


# ----------------------------------------------------------------------
# Compositor layers (Decision 8)
# ----------------------------------------------------------------------

class CompositorLayer:
    """A panel / video / HUD presented by the compositor, NOT rendered
    into the scene projection image. Capability-gated; fallback is
    scene geometry (a quad in the scene) when layers are unavailable."""

    def __init__(self, kind, label, capability):
        self.kind = kind  # 'quad' | 'cylinder' | 'equirect' | 'projection'
        self.label = label
        self.capability = capability
        self.fallback_to_scene_geometry = False
        try:
            capability.require('layers')
        except Exception:
            # Fallback, not failure: render as scene geometry.
            self.fallback_to_scene_geometry = True

    def describe(self):
        if self.fallback_to_scene_geometry:
            return {'kind': self.kind, 'presented_as': 'scene-geometry-fallback'}
        return {'kind': self.kind, 'presented_as': 'compositor-layer'}


# ----------------------------------------------------------------------
# Input: tracked sources + semantic actions (Decision 9)
# ----------------------------------------------------------------------

class XRInputSource:
    """One tracked source. targetRaySpace (pointing) != gripSpace
    (held object). grip may be None. Selection / squeeze are semantic
    actions, independent of button layout."""

    def __init__(self, handedness='none', target_ray_space=None,
                 grip_space=None, profiles=None):
        self.handedness = handedness
        self.target_ray_space = target_ray_space
        self.grip_space = grip_space  # may be None -- callers must check
        self.profiles = list(profiles) if profiles else []
        self.select_pressed = False
        self.squeeze_pressed = False

    @classmethod
    def from_xr(cls, xr_source):
        try:
            grip = getattr(xr_source, 'gripSpace', None)
        except Exception:
            grip = None
        return cls(
            handedness=getattr(xr_source, 'handedness', 'none'),
            target_ray_space=getattr(xr_source, 'targetRaySpace', None),
            grip_space=grip,
            profiles=list(getattr(xr_source, 'profiles', []) or []))

    def has_grip(self):
        return self.grip_space is not None

    def raycast(self, scene_raycast_fn, origin, direction):
        """Scene-object raycasting (against SCS shapes / scene)."""
        return scene_raycast_fn(origin, direction)

    def hit_test(self, hit_test_fn, ray):
        """WebXR hit testing (against REAL-WORLD geometry). A different
        kind of intersection from raycast() -- never conflated."""
        return hit_test_fn(ray)


# ----------------------------------------------------------------------
# Lifecycle: entry / exit / unavailable tracking (Decision 10)
# ----------------------------------------------------------------------

XR_NOT_STARTED = 'not-started'
XR_REQUESTING = 'requesting'
XR_RUNNING = 'running'
XR_TRACKING_LOST = 'tracking-lost'
XR_ENDED = 'ended'
XR_FAILED = 'failed'


class XRSessionManager:
    """Async setup, symmetric teardown, ordinary lifecycle states.

    enter(): compatibility -> reference space -> layers -> transfer
        frame scheduling to XRSession.requestAnimationFrame.
    exit():  release session state, restore non-XR rendering.
    """

    def __init__(self, on_frame=None, on_exit=None):
        self.state = XR_NOT_STARTED
        self.session = None
        self.reference_space = None
        self.reference_space_type = 'local'
        self.presentation = None
        self.capability = probe_xr_capability()
        self.on_frame = on_frame  # fn(frame_ctx, xr_frame)
        self.on_exit = on_exit
        self.error = None
        self._xr_raf_id = None

    def enter(self, mode='immersive-vr', reference_space_type='local',
              backend='webgl2'):
        """Async: returns a Promise. Unsupported combos fail HERE,
        during init, not halfway through rendering."""
        self.state = XR_REQUESTING
        self.reference_space_type = reference_space_type
        cap = self.capability
        try:
            if backend == 'webgl2':
                cap.require('webgl_xr')
            elif backend == 'webgpu':
                cap.require('webgpu_xr')
            else:
                raise RuntimeError('Unknown XR backend %r' % backend)
        except Exception as e:
            self.state = XR_FAILED
            self.error = str(e)
            raise

        def _setup(session):
            self.session = session
            try:
                session.addEventListener('end', self._on_session_end)
            except Exception:
                pass

            def _got_space(space):
                self.reference_space = Space(
                    'reference-' + reference_space_type,
                    reference=reference_space_type)
                self.reference_space._xr_space = space
                self.state = XR_RUNNING
                # Transfer frame scheduling to the session.
                try:
                    self._xr_raf_id = session.requestAnimationFrame(self._on_xr_frame)
                except Exception as e:
                    self.state = XR_FAILED
                    self.error = str(e)

            try:
                session.requestReferenceSpace(reference_space_type).then(_got_space)
            except Exception as e:
                self.state = XR_FAILED
                self.error = str(e)

        try:
            nav_xr = window.navigator.xr
            nav_xr.requestSession(mode).then(_setup)
        except Exception as e:
            self.state = XR_FAILED
            self.error = str(e)

    def _on_xr_frame(self, xr_time, xr_frame):
        if self.state != XR_RUNNING or self.session is None:
            return
        # Schedule the NEXT frame first (XR pattern), then render this one.
        try:
            self.session.requestAnimationFrame(self._on_xr_frame)
        except Exception:
            pass
        if self.on_frame is not None:
            try:
                frame_ctx = FrameContext.from_xr_frame(
                    xr_frame, self.reference_space, session=self.session)
                # Presentation layer fills per-view targets/viewports.
                if self.presentation is not None:
                    targets = self.presentation.acquire(frame_ctx, xr_frame, None)
                    for i, view in enumerate(frame_ctx.views):
                        t = targets.get(i)
                        if t is not None:
                            view.target = t
                            view.viewport = t.viewport or view.viewport
                if not frame_ctx.viewer_pose_available:
                    self.state = XR_TRACKING_LOST
                else:
                    self.state = XR_RUNNING
                self.on_frame(frame_ctx, xr_frame)
            except Exception:
                # A bad XR frame never kills the session.
                pass

    def _on_session_end(self, _ev=None):
        self.exit()

    def exit(self):
        """Symmetric teardown: release session state, restore non-XR."""
        self.state = XR_ENDED
        sess = self.session
        self.session = None
        self.reference_space = None
        self.presentation = None
        if self.on_exit is not None:
            try:
                self.on_exit()
            except Exception:
                pass
        if sess is not None:
            try:
                sess.end()
            except Exception:
                pass

    def is_running(self):
        return self.state == XR_RUNNING


# ----------------------------------------------------------------------
# Multi-view rendering: sequential baseline, multiview as optimisation
# ----------------------------------------------------------------------

def render_views_sequentially(frame_ctx, render_one_view):
    """Baseline (Decision 6): render each supplied view in turn.
    Shared scene preparation happens ONCE in the caller, before this;
    per-view work is only camera + viewport + target. Simulation is
    NEVER advanced here -- the caller already stepped it."""
    results = []
    for i, view in enumerate(frame_ctx.views):
        results.append(render_one_view(view, i))
    return results


def render_views_multiview(frame_ctx, render_multiview, capability):
    """Optimised path: ONE multiview operation for all views. Gated on
    capability; falls back to sequential -- never a redesign."""
    try:
        capability.require('multiview')
    except Exception:
        return render_views_sequentially(
            frame_ctx, lambda v, i: render_multiview([v], i))
    return render_multiview(frame_ctx.views, 0)
