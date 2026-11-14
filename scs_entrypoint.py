"""
scs_entrypoint.py - SCS entrypoint: API, App, events, loop, app loading.

This file replaces ALL of the Python that used to live in index.html.
index.html is now ~20 lines: load Brython, load this module, call boot().

    import scs_entrypoint
    scs_entrypoint.boot()

What lives here:
  * Align logic (exact CMU semantics, creation-time only)
  * Shape classes (Rect, Oval, Circle, RegularPolygon, Star, Line,
    Polygon, Arc, Label, Image, Group) -- each with draw(renderer)
  * Immediate-mode draw* functions -- thin forwards to the renderer
  * App + runApp/run/loop -- renderer selection happens HERE:
        runApp(width, height, renderer='2d' | 'webgl2' | 'webgpu' | 'auto')
        runApp(..., renderer='webgpu')   # WebGPU (async init, NO FALLBACK)
        runApp(..., renderer='auto')     # WebGPU -> WebGL2 -> 2D
        ?app=rabbit_sim&renderer=webgpu  # URL param, same selection
        SCS.create({renderer: 'webgpu'}) # JS / CDN loader, same selection
  * Events: mouse, drag, keyboard (press/release/hold), resize, touch
  * Main loop: onStep + redrawAll + shape display list, stepsPerSecond
  * App loading: ?app= sanitised fetch, exec into a user namespace,
    auto-start when callbacks are defined (CMU-style, no runApp needed)

Renderer contract: every renderer in scs_2d / scs_webgl / scs_webgpu
implements the same draw_* methods. Shapes and draw* functions never
touch a canvas context directly -- they only call the renderer.
That is what makes the API identical on all three backends.

Backwards compat: `import scs` still works -- scs.py aliases this module
(see scs.py). Old globals _canvas, _ctx, _shapes, _app are kept live:
_ctx is the 2D context when the 2D renderer is active, else None.
"""

import math
import random as _random

try:
    from browser import document, window, timer
except ImportError:  # CPython tests
    document = None
    window = None
    timer = None

__all__ = [
    'Rect', 'Oval', 'Circle', 'RegularPolygon', 'Star', 'Line', 'Polygon',
    'Arc', 'Label', 'Image', 'Group', 'Sound', 'App',
    'drawRect', 'drawOval', 'drawCircle', 'drawRegularPolygon', 'drawStar',
    'drawLine', 'drawPolygon', 'drawArc', 'drawLabel', 'drawImage',
    'runApp', 'run', 'loop', 'run_app', 'cmu_graphics_run', 'stop', 'boot', 'main',
    'rgb', 'gradient', 'distance', 'angleTo', 'getPointInDir', 'rounded',
    'makeList', 'randrange', 'randint', 'random',
    'getRendererKind', 'create_renderer', 'setRenderer',
    'getCapability', 'getStats', 'disposeRenderer', 'requestReadback',
    'getDisplayConfig',
    # WebXR (scs_xr.py): externally-driven loop, FrameContext, lifecycle.
    'renderFrame', 'startXR', 'stopXR', 'getXRState', 'getXRCapability',
    # Integrations (scs_storage / scs_wasm / scs_audio / scs_media / scs_serial):
    # adapters around the renderer, never inside render().
    'getAssetCache', 'getPrefs', 'getAudioEngine', 'getMediaAdapter',
    'getSerialAdapter', 'getUSBAdapter',
    # Spatial audio + 3D math + separate 3D engines.
    'getSpatialAudioEngine', 'Camera3D',
    'getWebGL2Engine', 'getWebGPUEngine',
    'getSplatRenderer', 'createSplatSchema', 'loadSplatManifest',
    'getPipelineManager', 'getMaterialLibrary', 'getPBRMaterial',
]

__version__ = '2026-11-14-FIXED-v38-no-responsive-only-fullscreen-resizes'

# v32: ONE window property only: window.scs.
# Corporate host pages do not want SCS scattering __SCS_* / SCS_CONFIG etc
# across window. All SCS runtime state lives nested under window.scs.
# We never create any other window.* property. We never overwrite an
# existing window.scs - we reuse it and only add our own keys.
def _scs_ns():
    try:
        _ns = getattr(window, 'scs', None)
        if _ns is None:
            _ns = {}
            try:
                window.scs = _ns
            except Exception:
                pass
            return _ns
        return _ns
    except Exception:
        return {}

def _scs_get(_k, _default=None):
    try:
        _ns = _scs_ns()
        try:
            if isinstance(_ns, dict):
                return _ns.get(_k, _default)
        except Exception:
            pass
        return getattr(_ns, _k, _default)
    except Exception:
        return _default

def _scs_set(_k, _v):
    try:
        _ns = _scs_ns()
        try:
            if isinstance(_ns, dict):
                _ns[_k] = _v
                return
        except Exception:
            pass
        try:
            setattr(_ns, _k, _v)
        except Exception:
            pass
    except Exception:
        pass

def _scs_cleanup_legacy():
    # v31 wrote window.__SCS_* - remove them on first v32 load so the host
    # window is left clean. Migrate any values into window.scs first.
    try:
        for _old, _new in (('__SCS_VERSION_PRINTED__', 'versionPrinted'),
                           ('__SCS_EVENTS_BOUND__', 'eventsBound'),
                           ('__SCS_BOOTED__', 'booted'),
                           ('__SCS_LAST_RUNAPP__', 'lastRunApp')):
            try:
                _v = getattr(window, _old, None)
            except Exception:
                _v = None
            if _v is not None:
                try:
                    if _scs_get(_new, None) is None:
                        _scs_set(_new, _v)
                except Exception:
                    pass
                try:
                    delattr(window, _old)
                except Exception:
                    pass
    except Exception:
        pass
try:
    _scs_cleanup_legacy()
except Exception:
    pass

# Console proof: log version the moment this file is imported by Brython.
# If the live console does NOT show this line, the browser is NOT running this file.
# v31 single-run: window-level guard. Two module instances (scs_entrypoint
# vs scs.scs_entrypoint) have separate Python globals, so a Python-only
# _booted flag does NOT stop the second instance. window is shared, so it
# is the only place an "already ran" flag works across instances.
try:
    _ver_msg = '[SCS entrypoint] version=' + __version__
    _already_printed = False
    try:
        from browser import window as _w
        _already_printed = bool(_scs_get('versionPrinted', False))
    except Exception:
        _w = None
    if not _already_printed:
        try:
            _scs_set('versionPrinted', True)
        except Exception:
            pass
        _debug_log(_ver_msg)
except Exception:
    pass

# ----------------------------------------------------------------------
# Align -- exact CMU semantics
# ----------------------------------------------------------------------

_VALID_ALIGNS = {
    'left-top', 'top', 'right-top',
    'left', 'center', 'right',
    'left-bottom', 'bottom', 'right-bottom',
}

_ALIGN_ALIASES = {
    'lefttop': 'left-top', 'topleft': 'left-top',
    'righttop': 'right-top', 'topright': 'right-top',
    'leftbottom': 'left-bottom', 'bottomleft': 'left-bottom',
    'rightbottom': 'right-bottom', 'bottomright': 'right-bottom',
    'topcenter': 'top', 'centertop': 'top',
    'bottomcenter': 'bottom', 'centerbottom': 'bottom',
    'leftcenter': 'left', 'centerleft': 'left',
    'rightcenter': 'right', 'centerright': 'right',
    'centre': 'center', 'middle': 'center', 'centercenter': 'center',
}


def _normalize_align(align):
    if not align:
        return 'center'
    a = str(align).strip().lower().replace('_', '-').replace(' ', '-')
    a_nospace = a.replace('-', '')
    if a_nospace in _ALIGN_ALIASES:
        return _ALIGN_ALIASES[a_nospace]
    if a in _ALIGN_ALIASES:
        return _ALIGN_ALIASES[a]
    if a in _VALID_ALIGNS:
        return a
    has_left = 'left' in a
    has_right = 'right' in a
    has_top = 'top' in a
    has_bottom = 'bottom' in a
    if has_left and has_top:
        return 'left-top'
    if has_right and has_top:
        return 'right-top'
    if has_left and has_bottom:
        return 'left-bottom'
    if has_right and has_bottom:
        return 'right-bottom'
    if has_left:
        return 'left'
    if has_right:
        return 'right'
    if has_top:
        return 'top'
    if has_bottom:
        return 'bottom'
    return 'center'

def _normalize_hud(hud=None, mode=None):
    """Per-shape HUD-or-3D flag. Default to HUD/2D.
    hud: 'hud' | '2d' | 'texture' | 'html' | True | None -> 'hud' (HUD/2D, default)
         '3d' | 'world' | False -> '3d' (3D world, depth on, not HUD)
         'auto' -> 'auto' (inherit from app's global HUD mode)
    mode: alias for hud - mode='hud'/'2d' -> 'hud', mode='3d'/'world' -> '3d'
    Returns 'hud' | '3d' | 'texture' | 'html' | 'auto'. Default is '3d' (hud=False, 3D mode)."""
    # mode alias takes precedence if hud is default/None
    if mode is not None and hud is None:
        hud = mode
    elif mode is not None and (hud is False or hud == 'hud'):
        # If both given, mode overrides only if it explicitly says 3d
        _m = str(mode).strip().lower().replace('-', '_')
        if _m in ('3d', 'world', '3d_world'):
            hud = '3d'
        elif _m in ('hud', '2d', 'texture', 'html', 'auto'):
            hud = _m if _m != '2d' else 'hud'
    if hud is None:
        return '3d'  # default False = 3D mode
    if hud is True:
        return 'hud'  # hud=True = overlay
    if hud is False:
        return '3d'  # hud=False (default) = 3D mode
    s = str(hud).strip().lower().replace('-', '_')
    if s in ('', 'hud', '2d', '2_d', 'hud_2d', '2d_hud', 'true', 'yes', 'on', '1'):
        return 'hud'
    if s in ('texture', 'tex', 'hud_texture'):
        return 'texture'
    if s in ('html', 'html_in_canvas', 'html_canvas', 'dom', 'live'):
        return 'html'
    if s in ('auto', 'automatic', 'inherit'):
        return 'auto'
    if s in ('3d', 'world', '3d_world', 'world_3d', 'false', 'no', 'off', '0'):
        return '3d'
    return 'hud'


def _is_3d_shape(shape):
    """CMU rule: centerZ set = 3D, no centerZ = HUD. centerZ at END.
    centerZ wins over hud. hud=False / hud='3d' also counts as 3D for backwards compat.
    """
    try:
        z = getattr(shape, 'centerZ', getattr(shape, 'z', getattr(shape, '_centerZ', getattr(shape, '_z', None))))
        if z is not None:
            return True
        z1 = getattr(shape, 'centerZ1', getattr(shape, 'z1', None))
        z2 = getattr(shape, 'centerZ2', getattr(shape, 'z2', None))
        if z1 is not None or z2 is not None:
            return True
        h = getattr(shape, 'hud', None)
        if h == '3d':
            return True
        return False
    except Exception:
        return False

def _get_shape_z(shape):
    try:
        return getattr(shape, 'centerZ', getattr(shape, 'z', getattr(shape, '_centerZ', None)))
    except Exception:
        return None



def _get_align_offsets(align, width, height):
    a = _normalize_align(align)
    if a in ('left-top', 'left', 'left-bottom'):
        ox = 0
    elif a in ('right-top', 'right', 'right-bottom'):
        ox = width
    else:
        ox = width / 2
    if a in ('left-top', 'top', 'right-top'):
        oy = 0
    elif a in ('left-bottom', 'bottom', 'right-bottom'):
        oy = height
    else:
        oy = height / 2
    return ox, oy


def _resolve_bbox(x, y, width, height, align):
    ox, oy = _get_align_offsets(align, width, height)
    return x - ox, y - oy


# ----------------------------------------------------------------------
# Global state (kept live for backwards compat)
# ----------------------------------------------------------------------

_canvas = None
_ctx = None            # 2D context when renderer is 2D, else None
_renderer = None       # current renderer object
_renderer_kind = '2d'
# HUD mode: any existing 2D app can just change runApp() to get it in 3D.
# runApp(..., renderer='webgl2' / 'webgpu' / '3d', hud=True, mode='hud'/'3d')
# The 2D app draws unchanged to an offscreen 2D canvas. That canvas is
# composited every frame as a fullscreen HUD quad (depth off, ortho) in the
# 3D scene. The 2D app never knows it is in 3D. No rewrite, one-line change.
_hud_mode = False
# --- Fullscreen button (enableFullscreen=True) ---
# Minimal HUD button, bottom-right, 36x36, 16px margin. Same HUD system as
# PLAY/STOP: centerZ is None -> drawn via HUD texture, hit-tested via
# _hud_shape_at in the SAME logical space as _pos (v27). Position is derived
# from _canvas_width/_canvas_height on every resize, so it stays bottom-right
# in windowed AND fullscreen. Logical size tracks CSS size on fullscreenchange,
# so picking stays correct without a second coordinate system.
_fullscreen_enabled = False
_fullscreen_btn = None
_fullscreen_btn_label = None
_fullscreen_orig_w = None
_fullscreen_orig_h = None
_fullscreen_orig_style_w = None
_fullscreen_orig_style_h = None
_hud_offscreen = None   # offscreen 2D canvas where the 2D app draws in HUD mode
_hud_2d_renderer = None  # 2D renderer for the offscreen canvas
_hud_3d_kind = None     # 'webgl2' or 'webgpu' when in HUD mode
# Both, with a flag: HUD texture (default, works everywhere) vs HTML-in-Canvas
# (Chrome 157+ only, live DOM). _hud_kind: 'texture' | 'html' | 'auto'.
#   hud='texture'  -> offscreen 2D canvas -> WebGL texture (works everywhere)
#   hud='html'     -> live DOM element -> WebGL texture via texElementSubImage2D
#                      (Chrome 157+ only, NO FALLBACK to texture)
#   hud='auto'     -> try HTML-in-Canvas if supported, else texture
#   hud=True       -> 'texture' (backwards compat, default)
#   mode='hud'/'3d' -> 'texture', mode='html' -> 'html', mode='auto' -> 'auto'
_hud_kind = 'texture'
_hud_html_element = None  # DOM element to render in HTML-in-Canvas mode (or None = default HUD div)
_hud_html_supported = None  # cached: does this browser support HTML-in-Canvas?
_app = None
_shapes = []           # display list, z-order = list order
_all_shapes = _shapes  # alias -- _clear_shapes mutates, never rebinds
_image_cache = {}

_user_funcs = {}
_user_ns = {}
_app_timer = None
_is_dragging = False
_pressed_keys = set()
_canvas_width = 400
_canvas_height = 400
_steps_per_second = 30
_pending_renderer = None
_xr_manager = None
_xr_active = False
_presentation = None
_presentation_coordinator = None
_render_scale = 1.0
_pixel_ratio_cap = None
_pixel_budget = None
_controller_manager = None
_asset_loader = None
_splat_renderer = None

_CALLBACK_NAMES = (
    'onAppStart', 'appStarted', 'redrawAll', 'onStep',
    'onMousePress', 'onMouseRelease', 'onMouseMove', 'onMouseDrag',
    'onKeyPress', 'onKeyRelease', 'onKeyHold', 'onResize',
    # WebXR semantic actions (scs_xr): select / squeeze, not mouse.
    'onXRSelect', 'onXRSqueeze', 'onXRInput',
)


def _clear_shapes():
    del _shapes[:]


_clear_all_shapes = _clear_shapes


def _debug_log(msg):
    # v33: log ONCE. Brython print() already goes to DevTools, so doing
    # console.log AND print duplicated every line (looked like double-run).
    # Prefer console.log in browser, print only as fallback (CPython tests).
    try:
        if window is not None and hasattr(window, 'console'):
            window.console.log(msg)
            return
    except Exception:
        pass
    try:
        print(msg)
    except Exception:
        pass


# ----------------------------------------------------------------------
# Canvas + renderer selection
# ----------------------------------------------------------------------

def _find_canvas():
    global _canvas
    if _canvas is not None:
        return _canvas
    for getter in ('cmu-canvas', 'canvas', 'scs-canvas'):
        try:
            c = document.getElementById(getter)
        except Exception:
            c = None
        if c is not None:
            _canvas = c
            return c
    try:
        c = document.getElementById('canvas')
    except Exception:
        c = None
    if c is None:
        try:
            c = document.createElement('canvas')
            c.id = 'canvas'
            document.body.appendChild(c)
        except Exception:
            c = None
    _canvas = c
    return c


def _dpr():
    try:
        return float(window.devicePixelRatio or 1.0)
    except Exception:
        return 1.0

def _budgeted_ratio():
    # v38: NO RESPONSIVE. No DPR scaling, no pixel budget.
    # runApp(900,560) => CSS 900x560, backing 900x560, always.
    # Only fullscreen may change it (see _on_fullscreen_change).
    return 1.0

# --- Resize pipeline (v29): CSS drives layout, ResizeObserver drives buffer ---
# CSS size (content box) is the source of truth. canvas.width/height (backing)
# are derived, never the other way round, so a buffer change cannot feed back
# into layout. Notifications coalesce into one pending update, applied before
# the next frame draw, not once per burst event.
_resize_pending = None  # (cssW, cssH, backingW, backingH)
_resize_observer = None
_resize_last_dpr = None
_resize_wrapper_css_injected = False

def _get_hud_offscreen(width, height):
    """Offscreen 2D canvas for HUD mode. The 2D app draws here, unchanged.
    Returns the canvas. Created once per size, reused every frame."""
    global _hud_offscreen
    try:
        w, h = int(width), int(height)
    except Exception:
        w, h = 400, 400
    # v34: offscreen size is CSS size * DPR at creation. Do NOT recreate
    # just because the budgeted DPR wobbled (1.0 -> 0.5) - that was recreating
    # the canvas every few frames and desyncing the HUD renderer.
    # Only recreate if CSS size changed.
    if _hud_offscreen is not None:
        try:
            # Compare against stored CSS size, not budgeted size.
            _ow = getattr(_hud_offscreen, '_scs_css_w', None)
            _oh = getattr(_hud_offscreen, '_scs_css_h', None)
            if _ow == w and _oh == h:
                return _hud_offscreen
        except Exception:
            pass
    _br = _budgeted_ratio()
    try:
        c = document.createElement('canvas')
        c.width = int(w * _br)
        c.height = int(h * _br)
        try:
            c._scs_css_w = w
            c._scs_css_h = h
        except Exception:
            pass
        try:
            c.style.width = '%dpx' % w
            c.style.height = '%dpx' % h
        except Exception:
            pass
        _hud_offscreen = c
        return c
    except Exception:
        return None

def getHudOffscreenCanvas():
    """For scs.py: in HUD mode, scs.py's _ensure_canvas() must return this
    offscreen canvas, NOT the visible WebGL canvas (getContext('2d') on a
    WebGL canvas returns null). This is what makes an existing scs.py app
    work in 3D with only a runApp() change."""
    return _hud_offscreen

def isHudMode():
    return bool(_hud_mode)

def getHudKind():
    """'texture' | 'html' | 'auto' - which HUD implementation is active."""
    return _hud_kind

def isHtmlInCanvasSupported():
    """Chrome 157+ only. Firefox/Safari have shipped nothing. Cache the result.
    Checks: gl.texElementSubImage2D (Chrome 157+) or gl.texElementImage2D (149-154),
    plus canvas.updateElementGeometry for hit-testing."""
    global _hud_html_supported
    if _hud_html_supported is not None:
        return _hud_html_supported
    try:
        c = _find_canvas()
        if c is None:
            _hud_html_supported = False
            return False
        # 2D: drawElementImage() - Chrome 157+
        try:
            ctx2d = c.getContext('2d')
            if ctx2d is not None and hasattr(ctx2d, 'drawElementImage'):
                _hud_html_supported = True
                return True
        except Exception:
            pass
        # WebGL: texElementSubImage2D (157+) or texElementImage2D (149-154)
        try:
            gl = c.getContext('webgl2') or c.getContext('webgl')
            if gl is not None and (hasattr(gl, 'texElementSubImage2D') or hasattr(gl, 'texElementImage2D')):
                _hud_html_supported = True
                return True
        except Exception:
            pass
        # Hit-testing helper alone is not enough, but if the canvas has it
        # and we are in Chrome, we are likely on 157+.
        try:
            if hasattr(c, 'updateElementGeometry'):
                # Only trust it if we also saw a texElement method above;
                # otherwise it may be a stub. Fall through to False.
                pass
        except Exception:
            pass
        _hud_html_supported = False
        return False
    except Exception:
        _hud_html_supported = False
        return False

def getHtmlHudElement():
    """DOM element to render in HTML-in-Canvas mode. If the user passed
    html_element=... to runApp(), use that. Otherwise create/use the default
    HUD div #scs-html-hud. The app can fill it with buttons, inputs, etc.,
    and it will be live (typeable, clickable) inside the 3D scene on Chrome 157+."""
    global _hud_html_element
    if _hud_html_element is not None:
        return _hud_html_element
    try:
        el = document.getElementById('scs-html-hud')
        if el is None:
            el = document.createElement('div')
            el.id = 'scs-html-hud'
            try:
                el.setAttribute('content', 'drawable')
            except Exception:
                pass
            try:
                el.style.position = 'absolute'
                el.style.left = '0px'
                el.style.top = '0px'
                el.style.pointerEvents = 'auto'
            except Exception:
                pass
            try:
                document.body.appendChild(el)
            except Exception:
                pass
        _hud_html_element = el
        return el
    except Exception:
        return None

def setHtmlHudElement(el):
    """Set the DOM element for HTML-in-Canvas HUD. Accepts an element,
    a selector string ('#my-hud', '.hud'), or an id."""
    global _hud_html_element
    try:
        if isinstance(el, str):
            try:
                if el.startswith('#'):
                    _hud_html_element = document.getElementById(el[1:])
                elif el.startswith('.'):
                    _hud_html_element = document.querySelector(el)
                else:
                    _hud_html_element = document.getElementById(el) or document.querySelector(el)
            except Exception:
                _hud_html_element = None
        else:
            _hud_html_element = el
    except Exception:
        _hud_html_element = None
    return _hud_html_element


def _replace_canvas_for_context(kind):
    # v35: One canvas = one context type per page load (browser rule).
    # WebGL -> 2D (spatial_audio -> fetch_demo) or 2D -> WebGL on the SAME
    # canvas makes getContext() return null and run_app fails with no loop.
    # Fix: if the requested kind differs from the canvas's existing context
    # kind, replace the <canvas> element with a fresh one (same id, same
    # attributes). Fresh element has no context, so getContext() succeeds.
    try:
        _prev = _scs_get('canvasContextKind', None)
        if _prev is None or str(_prev).lower() == str(kind).lower():
            return
        _c = _find_canvas()
        if _c is None:
            return
        _parent = getattr(_c, 'parentNode', None)
        if _parent is None:
            return
        _new = document.createElement('canvas')
        try:
            _new.id = _c.id
        except Exception:
            pass
        for _attr in ('data-app', 'tabindex'):  # v38: NEVER copy width/height attrs (1050x700 in index.html)
            try:
                _v = _c.getAttribute(_attr)
                if _v is not None:
                    _new.setAttribute(_attr, _v)
            except Exception:
                pass
        try:
            _new.style.cssText = _c.style.cssText
        except Exception:
            pass
        # v38: new canvas gets runApp size, not index.html attrs.
        try:
            _new.width = int(_canvas_width); _new.height = int(_canvas_height)
            _new.style.width = '%dpx' % int(_canvas_width); _new.style.height = '%dpx' % int(_canvas_height)
        except Exception:
            pass
        _parent.replaceChild(_new, _c)
        global _canvas
        _canvas = _new
        _scs_set('canvasContextKind', str(kind).lower())
        _debug_log('SCS canvas: replaced canvas to switch context %s -> %s' % (_prev, kind))
    except Exception:
        pass

def _size_canvas(width, height):
    """v29: CSS controls displayed size, buffer is derived.
    Initial CSS = width x height px (the layout). Backing = CSS * budgeted ratio.
    After this, CSS is NOT rewritten from the buffer - ResizeObserver measures
    the content box and queues a buffer update. No layout feedback loop."""
    global _canvas_width, _canvas_height, _resize_last_dpr
    _canvas_width, _canvas_height = int(width), int(height)
    canvas = _find_canvas()
    if canvas is None:
        return
    _br = _budgeted_ratio()
    _resize_last_dpr = _br
    try:
        # v36: APP SIZE WINS. runApp(900,560) means 900x560, period.
        # v30 "host owns CSS" left the canvas at index.html's 1050x700 while
        # the app drew at 900x560 - then ResizeObserver measured 1050x700
        # (or DevTools 9990x7593) and overwrote the app size every frame.
        # That is the tiny flashing HUD tile at the bottom. Always set CSS
        # to the app size. Host pages that want responsive must opt in via
        # fullscreen / responsive mode, not by having a different CSS size.
        try:
            canvas.style.width = '%dpx' % int(width)
            canvas.style.height = '%dpx' % int(height)
        except Exception:
            pass
        # Buffer: assign only if actually changed (avoids needless reset).
        _bw, _bh = int(width), int(height)  # v38: backing == CSS == runApp, no DPR multiply
        if int(canvas.width) != _bw:
            canvas.width = _bw
        if int(canvas.height) != _bh:
            canvas.height = _bh
    except Exception:
        pass
    try:
        _ensure_resize_observer()
    except Exception:
        pass

def _measure_canvas_css():
    # CSS content-box size in CSS px, rounded. Used as fallback when
    # devicePixelContentBoxSize is unavailable.
    try:
        _c = _find_canvas()
        if _c is None:
            return (float(_canvas_width), float(_canvas_height))
        _r = _c.getBoundingClientRect()
        return (float(_r.width), float(_r.height))
    except Exception:
        return (float(_canvas_width), float(_canvas_height))

def _queue_resize(cssW, cssH, backingW=None, backingH=None):
    # v37: NO RESIZING EVER. Fixed-size app: runApp(900,560) is 900x560.
    # There was never supposed to be a resize pipeline. RO / DPR / presentation
    # resizing is what blew the canvas up to viewport size and made the
    # poem text huge and clipped. This is a no-op by design.
    return
    global _resize_pending
    try:
        _cssW, _cssH = float(cssW), float(cssH)
        if _cssW <= 0 or _cssH <= 0:
            return
        _br = _budgeted_ratio()
        if backingW is None or backingH is None:
            backingW, backingH = int(round(_cssW * _br)), int(round(_cssH * _br))
        else:
            backingW, backingH = int(backingW), int(backingH)
        _resize_pending = (_cssW, _cssH, backingW, backingH)
    except Exception:
        pass

def _apply_pending_resize():
    # v37: NO RESIZING EVER. See _queue_resize.
    return
    # Called at the START of _frame, before any draw. Applies one coalesced
    # update: buffer only if changed, HUD offscreen + renderer sizes in step,
    # fullscreen button repositioned. Post-resize, the next draw restores
    # 2D context config (begin_frame sets absolute transform) and redraws the
    # scene from scratch - never stretches an old frame.
    global _resize_pending, _canvas_width, _canvas_height, _hud_offscreen, _hud_2d_renderer
    if _resize_pending is None:
        return
    _cssW, _cssH, _bw, _bh = _resize_pending
    _resize_pending = None
    # v36: FIXED-SIZE APPS IGNORE ResizeObserver. If the pending size does not
    # match the app's current size, it is the PAGE / DevTools viewport size
    # (1050x700, 9990x7593), not the app size. Applying it overwrites
    # runApp(900,560) and makes the app draw as a tiny flashing tile.
    # Only responsive/fullscreen apps opt into RO-driven size.
    try:
        _is_resp = bool(_responsive) if '_responsive' in globals() else False
    except Exception:
        _is_resp = False
    if not _is_resp:
        try:
            if int(round(_cssW)) != int(_canvas_width) or int(round(_cssH)) != int(_canvas_height):
                return
        except Exception:
            pass
    # v36: no-op if backing already matches - assigning canvas.width clears
    # the canvas and resets the 2D context, which is the per-frame flash.
    try:
        _c0 = _find_canvas()
        if _c0 is not None and int(_c0.width) == int(_bw) and int(_c0.height) == int(_bh):
            return
    except Exception:
        pass
    try:
        _c = _find_canvas()
        if _c is not None:
            # Buffer: only when changed.
            if int(_c.width) != int(_bw):
                _c.width = int(_bw)
            if int(_c.height) != int(_bh):
                _c.height = int(_bh)
        _canvas_width, _canvas_height = int(round(_cssW)), int(round(_cssH))
        # HUD offscreen (size-dependent target) resized consistently.
        try:
            _hud_offscreen = None
            _hud_2d_renderer = None
            if _hud_offscreen is None:
                _get_hud_offscreen(_canvas_width, _canvas_height)
            if _hud_offscreen is not None:
                try:
                    _hud_2d_renderer = create_renderer('2d', _hud_offscreen, _canvas_width, _canvas_height)
                    # 2D renderer must use the same budgeted ratio for its absolute transform.
                    try:
                        _hud_2d_renderer.dpr = _budgeted_ratio()
                    except Exception:
                        pass
                except Exception:
                    _hud_2d_renderer = None
        except Exception:
            pass
        # Main renderer: logical size for HUD/mouse + viewport for 3D.
        try:
            _r = _renderer
            if _r is not None:
                _r.width = int(_canvas_width)
                _r.height = int(_canvas_height)
                try:
                    _r.dpr = _budgeted_ratio()
                except Exception:
                    pass
        except Exception:
            pass
        _reposition_fullscreen_button()
    except Exception:
        pass

def _check_pixel_ratio_change():
    # v37: NO RESIZING EVER. DPR wobble must not resize the canvas.
    return
    # Zoom / display-density change with unchanged CSS size: device-pixel
    # observation would catch it, but not all browsers support it. Check DPR
    # every frame in the resize pipeline and queue a buffer-only update.
    global _resize_last_dpr
    try:
        _br = _budgeted_ratio()
        if _resize_last_dpr is None:
            _resize_last_dpr = _br
            return
        if abs(_br - _resize_last_dpr) > 0.001:
            _resize_last_dpr = _br
            _cssW, _cssH = _measure_canvas_css()
            _queue_resize(_cssW, _cssH)
    except Exception:
        pass

def _on_resize_observer(entries, observer=None):
    # v37: NO RESIZING EVER.
    return
    # ResizeObserver: prefer devicePixelContentBoxSize (exact backing size),
    # fallback to contentBoxSize * budgeted ratio, then bounding rect * ratio.
    try:
        for _e in entries:
            _bw = _bh = None
            try:
                _dpc = getattr(_e, 'devicePixelContentBoxSize', None)
                if _dpc is not None and len(_dpc) > 0:
                    _bw = int(_dpc[0].inlineSize)
                    _bh = int(_dpc[0].blockSize)
            except Exception:
                pass
            try:
                _cb = getattr(_e, 'contentBoxSize', None)
                if _cb is not None and len(_cb) > 0:
                    _cssW = float(_cb[0].inlineSize)
                    _cssH = float(_cb[0].blockSize)
                else:
                    _cssW, _cssH = _measure_canvas_css()
            except Exception:
                _cssW, _cssH = _measure_canvas_css()
            if _bw is None or _bh is None:
                _br = _budgeted_ratio()
                _bw, _bh = int(round(_cssW * _br)), int(round(_cssH * _br))
            # v36: fixed-size app - RO is advisory only. If CSS box != app
            # size, it is the host page / DevTools, not the app. Ignore it.
            try:
                _is_resp2 = bool(_responsive) if '_responsive' in globals() else False
            except Exception:
                _is_resp2 = False
            if not _is_resp2:
                try:
                    if int(round(_cssW)) != int(_canvas_width) or int(round(_cssH)) != int(_canvas_height):
                        continue
                except Exception:
                    pass
            _queue_resize(_cssW, _cssH, _bw, _bh)
    except Exception:
        pass

def _ensure_resize_observer():
    # v37: NO RESIZING EVER. Do not create a ResizeObserver at all.
    # Creating it was enough: it fired on load and overwrote the app size.
    return
    global _resize_observer
    if _resize_observer is not None:
        return
    try:
        _c = _find_canvas()
        if _c is None:
            return
        _RO = getattr(window, 'ResizeObserver', None)
        if _RO is None:
            # No RO: window.resize fallback + DPR check in _frame still works.
            try:
                window.addEventListener('resize', lambda *_a: _queue_resize(*_measure_canvas_css()))
            except Exception:
                pass
            return
        try:
            # Prefer device-pixel box - exact backing size, catches zoom/DPR.
            _resize_observer = _RO.new(_on_resize_observer, {'box': 'device-pixel-content-box'})
        except Exception:
            try:
                _resize_observer = _RO.new(_on_resize_observer)
            except Exception:
                return
        try:
            _resize_observer.observe(_c)
        except Exception:
            pass
    except Exception:
        pass

def _ensure_app_wrapper():
    # v30: NON-INVASIVE for apps already in the wild in standard web pages.
    # Do NOT create a div, do NOT move the canvas, do NOT inject CSS.
    # Moving the canvas or injecting !important fullscreen CSS breaks the
    # host page's own layout (flex/grid, responsive rules, other content).
    # HUD controls are drawn INSIDE the canvas, so fullscreening the canvas
    # itself keeps them visible. Use the existing parent ONLY if it holds
    # just the canvas (a dedicated container); otherwise use the canvas.
    try:
        _c = _find_canvas()
        if _c is None:
            return None
        _p = _c.parentElement
        if _p is not None:
            try:
                # Dedicated container = only the canvas inside (ignore text nodes).
                _kids = [ _n for _n in list(_p.childNodes) if getattr(_n, 'nodeType', 3) == 1 ]
                if len(_kids) == 1 and _kids[0] is _c:
                    return _p
            except Exception:
                pass
        return _c
    except Exception:
        return None


def _url_param(name):
    try:
        s = window.location.search
        if not s:
            return None
        p = window.URLSearchParams.new(s)
        v = p.get(name)
        return v if v else None
    except Exception:
        return None


def _js_config():
    """v32: config lives under window.scs.config. Legacy window.SCS_CONFIG
    (set by the JS / CDN loader) is still read for backwards compat with
    pages already in the wild, but we never create it."""
    try:
        cfg = _scs_get('config', None)
        if cfg is not None:
            return cfg
        cfg = getattr(window, 'SCS_CONFIG', None)
        if cfg is None:
            return None
        return cfg
    except Exception:
        return None


def _config_value(name):
    cfg = _js_config()
    if cfg is not None:
        try:
            v = getattr(cfg, name, None)
            if v is not None:
                return v
        except Exception:
            pass
        try:
            v = cfg[name]
            if v is not None:
                return v
        except Exception:
            pass
    return None


def getRendererKind():
    return _renderer_kind


def getCapability():
    """Negotiated capability set for the active renderer (Decision 2).
    Returns {} before the first run_app()."""
    if _renderer is not None and hasattr(_renderer, 'capability'):
        return _renderer.capability.to_dict()
    return {}


def getStats():
    """Observability (Decision 20): draws, uploads, pipelines, memory."""
    if _renderer is not None and hasattr(_renderer, 'get_stats'):
        return _renderer.get_stats()
    try:
        from scs_core import STATS
        return STATS.to_dict()
    except Exception:
        return {}


def getDisplayConfig():
    """CSS size vs backing size vs DPR vs render scale (Decision 17)."""
    try:
        from scs_core import DisplayConfig
        return DisplayConfig(_canvas_width, _canvas_height, dpr=_dpr())
    except Exception:
        return None


def disposeRenderer():
    """Explicit disposal (Decision 18): release the current renderer
    and all tracked resources. The next run_app() recreates it."""
    global _renderer, _ctx
    if _renderer is not None:
        try:
            _renderer.destroy()
        except Exception:
            pass
    _renderer = None
    _ctx = None


def requestReadback(x, y, w, h):
    """Async readback (Decision 11): returns a Promise, never blocks.
    Use for screenshots / picking. WebGPU rejects predictably (see
    scs_webgpu._readback_promise)."""
    if _renderer is None or not hasattr(_renderer, '_readback_promise'):
        raise RuntimeError('No renderer with readback support is active')
    return _renderer._readback_promise(x, y, w, h)


def _import_renderer_module(name):
    """Import scs_2d / scs_webgl / scs_webgpu, trying both layouts.

    Deployments exist in two shapes: modules at the site root (pythonpath
    '.') and modules under scs/ (pythonpath 'scs'). Brython's ImportError
    str() is just the module name ('scs_2d'), which is why the sandbox
    showed the cryptic `SCS renderer failed (2d): scs_2d`. This helper
    tries both layouts and raises a RuntimeError that names the file
    that must be deployed alongside scs_entrypoint.py.
    """
    try:
        if name == 'scs_2d':
            from scs_2d import Renderer2D
            return Renderer2D
        if name == 'scs_webgl':
            from scs_webgl import RendererWebGL2
            return RendererWebGL2
        if name == 'scs_webgpu':
            from scs_webgpu import RendererWebGPU
            return RendererWebGPU
    except Exception as _e1:
        try:
            if name == 'scs_2d':
                from scs.scs_2d import Renderer2D
                return Renderer2D
            if name == 'scs_webgl':
                from scs.scs_webgl import RendererWebGL2
                return RendererWebGL2
            if name == 'scs_webgpu':
                from scs.scs_webgpu import RendererWebGPU
                return RendererWebGPU
        except Exception as _e2:
            raise RuntimeError(
                '%s.py not importable (tried %s and scs/%s.py). '
                'Deploy %s.py next to scs_entrypoint.py (or under scs/) '
                'and hard-refresh. First error: %r; second: %r'
                % (name, name, name, name, _e1, _e2))
    raise ValueError('Unknown renderer module %r' % name)


def create_renderer(kind, canvas, width, height):
    """Instantiate a renderer. 'webgpu' is async -- the returned object
    has .ready == False until on_ready fires; the entrypoint falls back
    on on_error. Raises on sync failure (2D / WebGL2)."""
    kind = (kind or '2d').lower()
    if kind in ('2d', 'canvas', 'canvas2d'):
        return _import_renderer_module('scs_2d')(canvas, width, height)
    if kind in ('webgl', 'webgl2', 'webgl-2'):
        # FIX v25: 'webgl2' means the 3D engine (kind webgl2-3d), NOT the 2D
        # tessellator in scs_webgl.py. The 3D path in _render_one_view only
        # runs when kind == 'webgl2-3d'. Try the engine first; if its
        # getContext(webgl2) fails (e.g. canvas already has 2d), fall back
        # to the 2D tessellator so 2D apps still work.
        try:
            from scs_engine_webgl2 import WebGL2Engine
            _eng = WebGL2Engine(canvas=canvas, width=width, height=height)
            if getattr(_eng, 'error', None) is None and getattr(_eng, 'gl', None) is not None:
                return _eng
            # Engine failed - fall through to tessellator
            _debug_log('SCS renderer webgl2 engine failed (%s) - using 2D tessellator' % (getattr(_eng, 'error', 'unknown'),))
        except Exception as _e_eng:
            _debug_log('SCS renderer webgl2 engine import failed (%r) - using 2D tessellator' % (_e_eng,))
        return _import_renderer_module('scs_webgl')(canvas, width, height)
    if kind in ('webgpu', 'gpu'):
        return _import_renderer_module('scs_webgpu')(canvas, width, height)
    raise ValueError('Unknown renderer %r (expected 2d, webgl2, webgpu, auto)' % kind)


def _resolve_renderer_kind(requested):
    """Precedence: explicit arg > ?renderer= > SCS_CONFIG.renderer > '2d'.
    'auto' = default (2D). No fallback chain."""
    if requested:
        return str(requested).lower()
    url = _url_param('renderer')
    if url:
        return str(url).lower()
    cfg = _config_value('renderer')
    if cfg:
        return str(cfg).lower()
    return '2d'


def _activate_renderer(renderer, kind):
    global _renderer, _renderer_kind, _ctx
    _renderer = renderer
    _renderer_kind = kind
    # FIX v25: log the real kind. Old code never logged here, so the only
    # 'SCS renderer version=0.1 mode=...' line came from a cached old file.
    try:
        _debug_log('SCS renderer version=0.1 mode=%s' % (kind,))
    except Exception:
        pass
    if kind == '2d' and renderer is not None:
        _ctx = getattr(renderer, 'ctx', None)
    else:
        _ctx = None


def _ensure_canvas():
    # FIX v25: do NOT create a 2d renderer here. getContext('2d') on the visible
    # canvas permanently blocks getContext('webgl2') on the same canvas (browser
    # rule: one canvas = one context type). The old code created 2d first, so
    # every later webgl2 request got null and fell back to 2d. Just return canvas.
    global _canvas
    canvas = _find_canvas()
    if canvas is None:
        return None
    return canvas


def setRenderer(kind):
    """Switch renderer for the NEXT runApp() call (or immediately if an
    app is already running -- the next frame uses it)."""
    global _pending_renderer
    _pending_renderer = _resolve_renderer_kind(kind)
    return _pending_renderer


# ----------------------------------------------------------------------
# Shapes
# ----------------------------------------------------------------------

class _BaseShape:
    def __init__(self, hud=None, centerZ=None, **kwargs):
        self._align = _normalize_align(kwargs.get('align', 'center'))
        # Per-shape: centerZ at END wins. No centerZ + no hud = HUD (new rule).
        # centerZ set = 3D, even centerZ=0. hud=False / hud='3d' still = 3D for backwards compat.
        _cz = centerZ
        if _cz is None:
            _cz = kwargs.get('centerZ', kwargs.get('z', None))
        self._centerZ = None if _cz is None else float(_cz)
        self._z = self._centerZ
        if self._centerZ is not None:
            self.hud = '3d'
        elif hud is not None or 'hud' in kwargs or 'mode' in kwargs:
            self.hud = _normalize_hud(hud if hud is not None else kwargs.get('hud', None), kwargs.get('mode', None))
        else:
            self.hud = 'hud'
        self.fill = kwargs.get('fill', 'black')
        self.border = kwargs.get('border', None)
        self.borderWidth = kwargs.get('borderWidth', 2)
        self.opacity = kwargs.get('opacity', 100)
        self.rotateAngle = kwargs.get('rotateAngle', 0)
        self.dashes = kwargs.get('dashes', False)
        self.visible = kwargs.get('visible', True)
        self._left = 0
        self._top = 0
        self._width = 0
        self._height = 0
        self._group = None

    @property
    def align(self):
        return self._align

    @align.setter
    def align(self, _v):
        raise AttributeError('align is creation-time only in CMU Graphics')

    @property
    def z(self):
        return getattr(self, '_z', None)

    @z.setter
    def z(self, v):
        self._z = None if v is None else float(v)
        self._centerZ = self._z
        if self._z is not None:
            self.hud = '3d'

    @property
    def centerZ(self):
        return getattr(self, '_z', None)

    @centerZ.setter
    def centerZ(self, v):
        self._z = None if v is None else float(v)
        self._centerZ = self._z
        if self._z is not None:
            self.hud = '3d'

    @property
    def left(self):
        return self._left

    @left.setter
    def left(self, v):
        self._left = float(v)

    @property
    def top(self):
        return self._top

    @top.setter
    def top(self, v):
        self._top = float(v)

    @property
    def right(self):
        return self._left + self._width

    @right.setter
    def right(self, v):
        self._left = float(v) - self._width

    @property
    def bottom(self):
        return self._top + self._height

    @bottom.setter
    def bottom(self, v):
        self._top = float(v) - self._height

    @property
    def centerX(self):
        return self._left + self._width / 2

    @centerX.setter
    def centerX(self, v):
        self._left = float(v) - self._width / 2

    @property
    def centerY(self):
        return self._top + self._height / 2

    @centerY.setter
    def centerY(self, v):
        self._top = float(v) - self._height / 2

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, v):
        cx = self.centerX
        self._width = float(v)
        self.centerX = cx

    @property
    def height(self):
        return self._height

    @height.setter
    def height(self, v):
        cy = self.centerY
        self._height = float(v)
        self.centerY = cy

    def toFront(self):
        if self in _shapes:
            _shapes.remove(self)
            _shapes.append(self)

    def toBack(self):
        if self in _shapes:
            _shapes.remove(self)
            _shapes.insert(0, self)

    def contains(self, x, y):
        return (self._left <= x <= self._left + self._width and
                self._top <= y <= self._top + self._height)

    def hits(self, x, y):
        return self.contains(x, y)

    def hitsShape(self, other):
        try:
            return not (self.right < other.left or self.left > other.right or
                        self.bottom < other.top or self.top > other.bottom)
        except Exception:
            return False


class Rect(_BaseShape):
    def __init__(self, x, y, width, height, hud=None, centerZ=None, **kwargs):
        self.hud = _normalize_hud(hud, kwargs.get('mode', None))
        align = kwargs.pop('align', 'left-top')
        super().__init__(align=align, hud=hud, centerZ=centerZ,
                         **{k: v for k, v in kwargs.items() if k != 'align'})
        self._width = float(width)
        self._height = float(height)
        l, t = _resolve_bbox(float(x), float(y), float(width), float(height), align)
        self._left, self._top = l, t
        self.roundness = kwargs.get('roundness', 0)
        _shapes.append(self)

    def draw(self, renderer):
        if not self.visible:
            return
        renderer.draw_rect(self._left, self._top, self._width, self._height,
                           fill=self.fill, border=self.border,
                           borderWidth=self.borderWidth, opacity=self.opacity,
                           rotateAngle=self.rotateAngle, dashes=self.dashes,
                           roundness=self.roundness)


class Oval(_BaseShape):
    def __init__(self, x, y, width, height, hud=None, centerZ=None, **kwargs):
        self.hud = _normalize_hud(hud, kwargs.get('mode', None))
        align = kwargs.pop('align', 'center')
        super().__init__(align=align, hud=hud, centerZ=centerZ,
                         **{k: v for k, v in kwargs.items() if k != 'align'})
        self._width = float(width)
        self._height = float(height)
        l, t = _resolve_bbox(float(x), float(y), float(width), float(height), align)
        self._left, self._top = l, t
        _shapes.append(self)

    def draw(self, renderer):
        if not self.visible:
            return
        renderer.draw_oval(self.centerX, self.centerY, self._width, self._height,
                           fill=self.fill, border=self.border,
                           borderWidth=self.borderWidth, opacity=self.opacity,
                           rotateAngle=self.rotateAngle, dashes=self.dashes)


class Circle(_BaseShape):
    def __init__(self, x, y, radius, hud=None, centerZ=None, **kwargs):
        self.hud = _normalize_hud(hud, kwargs.get('mode', None))
        align = kwargs.pop('align', 'center')
        super().__init__(align=align, hud=hud, centerZ=centerZ,
                         **{k: v for k, v in kwargs.items() if k != 'align'})
        self._radius = float(radius)
        w = h = float(radius) * 2
        self._width, self._height = w, h
        l, t = _resolve_bbox(float(x), float(y), w, h, align)
        self._left, self._top = l, t
        _shapes.append(self)

    @property
    def radius(self):
        return self._radius

    @radius.setter
    def radius(self, v):
        self._radius = float(v)
        self._width = self._height = float(v) * 2

    @property
    def centerX(self):
        return self._left + self._radius

    @centerX.setter
    def centerX(self, v):
        self._left = float(v) - self._radius

    @property
    def centerY(self):
        return self._top + self._radius

    @centerY.setter
    def centerY(self, v):
        self._top = float(v) - self._radius

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, v):
        self.radius = float(v) / 2

    @property
    def height(self):
        return self._height

    @height.setter
    def height(self, v):
        self.radius = float(v) / 2

    def draw(self, renderer):
        if not self.visible:
            return
        renderer.draw_circle(self.centerX, self.centerY, self._radius,
                             fill=self.fill, border=self.border,
                             borderWidth=self.borderWidth, opacity=self.opacity,
                             rotateAngle=self.rotateAngle, dashes=self.dashes)


class RegularPolygon(_BaseShape):
    def __init__(self, x, y, radius, points, hud=None, centerZ=None, **kwargs):
        self.hud = _normalize_hud(hud, kwargs.get('mode', None))
        align = kwargs.pop('align', 'center')
        super().__init__(align=align, hud=hud, centerZ=centerZ,
                         **{k: v for k, v in kwargs.items() if k != 'align'})
        self._radius = float(radius)
        self.points = int(points)
        w = h = float(radius) * 2
        self._width, self._height = w, h
        l, t = _resolve_bbox(float(x), float(y), w, h, align)
        self._left, self._top = l, t
        _shapes.append(self)

    @property
    def radius(self):
        return self._radius

    @radius.setter
    def radius(self, v):
        self._radius = float(v)
        self._width = self._height = float(v) * 2

    @property
    def centerX(self):
        return self._left + self._radius

    @centerX.setter
    def centerX(self, v):
        self._left = float(v) - self._radius

    @property
    def centerY(self):
        return self._top + self._radius

    @centerY.setter
    def centerY(self, v):
        self._top = float(v) - self._radius

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, v):
        self.radius = float(v) / 2

    @property
    def height(self):
        return self._height

    @height.setter
    def height(self, v):
        self.radius = float(v) / 2

    def draw(self, renderer):
        if not self.visible:
            return
        renderer.draw_regular_polygon(
            self.centerX, self.centerY, self._radius, self.points,
            fill=self.fill, border=self.border, borderWidth=self.borderWidth,
            opacity=self.opacity, rotateAngle=self.rotateAngle,
            dashes=self.dashes)


class Star(RegularPolygon):
    def __init__(self, x, y, radius, points, hud=None, centerZ=None, **kwargs):
        super().__init__(x, y, radius, points, hud=hud, **kwargs)
        self.ratio = kwargs.get('ratio', 0.5)

    def draw(self, renderer):
        if not self.visible:
            return
        renderer.draw_star(self.centerX, self.centerY, self._radius,
                           self.points, fill=self.fill, border=self.border,
                           borderWidth=self.borderWidth, opacity=self.opacity,
                           rotateAngle=self.rotateAngle, dashes=self.dashes,
                           ratio=self.ratio)


class Line:
    def __init__(self, x1, y1, x2, y2, hud=None, centerZ=None, centerZ1=None, centerZ2=None, **kwargs):
        self.hud = _normalize_hud(hud, kwargs.get('mode', None))
        _cz2 = centerZ if centerZ is not None else kwargs.get('centerZ', kwargs.get('z', None))
        self._centerZ = None if _cz2 is None else float(_cz2)
        self._z = self._centerZ
        _z1 = centerZ1 if centerZ1 is not None else kwargs.get('centerZ1', kwargs.get('z1', _cz2))
        _z2 = centerZ2 if centerZ2 is not None else kwargs.get('centerZ2', kwargs.get('z2', _cz2))
        self.centerZ1 = None if _z1 is None else float(_z1)
        self.centerZ2 = None if _z2 is None else float(_z2)
        if self._centerZ is not None:
            self.hud = '3d'
        self.x1 = float(x1)
        self.y1 = float(y1)
        self.x2 = float(x2)
        self.y2 = float(y2)
        self.fill = kwargs.get('fill', 'black')
        self.lineWidth = kwargs.get('lineWidth', kwargs.get('borderWidth', 2))
        self.opacity = kwargs.get('opacity', 100)
        self.visible = kwargs.get('visible', True)
        self.dashes = kwargs.get('dashes', False)
        self.rotateAngle = kwargs.get('rotateAngle', 0)
        _shapes.append(self)

    @property
    def left(self):
        return min(self.x1, self.x2)

    @property
    def right(self):
        return max(self.x1, self.x2)

    @property
    def top(self):
        return min(self.y1, self.y2)

    @property
    def bottom(self):
        return max(self.y1, self.y2)

    @property
    def width(self):
        return abs(self.x2 - self.x1)

    @property
    def height(self):
        return abs(self.y2 - self.y1)

    @property
    def centerX(self):
        return (self.x1 + self.x2) / 2

    @centerX.setter
    def centerX(self, v):
        dx = float(v) - self.centerX
        self.x1 += dx
        self.x2 += dx

    @property
    def centerY(self):
        return (self.y1 + self.y2) / 2

    @centerY.setter
    def centerY(self, v):
        dy = float(v) - self.centerY
        self.y1 += dy
        self.y2 += dy

    def toFront(self):
        if self in _shapes:
            _shapes.remove(self)
            _shapes.append(self)

    def toBack(self):
        if self in _shapes:
            _shapes.remove(self)
            _shapes.insert(0, self)

    def contains(self, x, y):
        # Distance from point to segment < lineWidth/2 + 1.
        dx, dy = self.x2 - self.x1, self.y2 - self.y1
        L2 = dx * dx + dy * dy
        if L2 == 0:
            return math.hypot(x - self.x1, y - self.y1) <= self.lineWidth / 2 + 1
        t = max(0.0, min(1.0, ((x - self.x1) * dx + (y - self.y1) * dy) / L2))
        return math.hypot(x - (self.x1 + t * dx), y - (self.y1 + t * dy)) <= self.lineWidth / 2 + 1

    def hits(self, x, y):
        return self.contains(x, y)

    def draw(self, renderer):
        if not self.visible:
            return
        renderer.draw_line(self.x1, self.y1, self.x2, self.y2,
                           fill=self.fill, lineWidth=self.lineWidth,
                           opacity=self.opacity, dashes=self.dashes)


class Polygon:
    def __init__(self, *points, hud=None, centerZ=None, **kwargs):
        self.hud = _normalize_hud(hud, kwargs.get('mode', None))
        self.points = [float(p) for p in points]
        self.fill = kwargs.get('fill', 'black')
        self.border = kwargs.get('border', None)
        self.borderWidth = kwargs.get('borderWidth', 2)
        self.opacity = kwargs.get('opacity', 100)
        self.visible = kwargs.get('visible', True)
        self.dashes = kwargs.get('dashes', False)
        self.rotateAngle = kwargs.get('rotateAngle', 0)
        _shapes.append(self)

    def _xs(self):
        return self.points[0::2]

    def _ys(self):
        return self.points[1::2]

    @property
    def left(self):
        return min(self._xs()) if self._xs() else 0

    @property
    def right(self):
        return max(self._xs()) if self._xs() else 0

    @property
    def top(self):
        return min(self._ys()) if self._ys() else 0

    @property
    def bottom(self):
        return max(self._ys()) if self._ys() else 0

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top

    @property
    def centerX(self):
        return (self.left + self.right) / 2

    @centerX.setter
    def centerX(self, v):
        dx = float(v) - self.centerX
        for i in range(0, len(self.points), 2):
            self.points[i] += dx

    @property
    def centerY(self):
        return (self.top + self.bottom) / 2

    @centerY.setter
    def centerY(self, v):
        dy = float(v) - self.centerY
        for i in range(1, len(self.points), 2):
            self.points[i] += dy

    def toFront(self):
        if self in _shapes:
            _shapes.remove(self)
            _shapes.append(self)

    def toBack(self):
        if self in _shapes:
            _shapes.remove(self)
            _shapes.insert(0, self)

    def draw(self, renderer):
        if not self.visible:
            return
        renderer.draw_polygon(list(self.points), fill=self.fill,
                              border=self.border, borderWidth=self.borderWidth,
                              opacity=self.opacity, rotateAngle=self.rotateAngle,
                              dashes=self.dashes)


class Arc(_BaseShape):
    def __init__(self, x, y, width, height, startAngle, sweepAngle, hud=None, centerZ=None, **kwargs):
        self.hud = _normalize_hud(hud, kwargs.get('mode', None))
        align = kwargs.pop('align', 'center')
        super().__init__(align=align, hud=hud, centerZ=centerZ,
                         **{k: v for k, v in kwargs.items() if k != 'align'})
        self._width = float(width)
        self._height = float(height)
        l, t = _resolve_bbox(float(x), float(y), float(width), float(height), align)
        self._left, self._top = l, t
        self.startAngle = float(startAngle)
        self.sweepAngle = float(sweepAngle)
        _shapes.append(self)

    def draw(self, renderer):
        if not self.visible:
            return
        renderer.draw_arc(self.centerX, self.centerY, self._width, self._height,
                          self.startAngle, self.sweepAngle, fill=self.fill,
                          border=self.border, borderWidth=self.borderWidth,
                          opacity=self.opacity, dashes=self.dashes)


class Label:
    def __init__(self, text, x, y, hud=None, centerZ=None, **kwargs):
        self.hud = _normalize_hud(hud, kwargs.get('mode', None))
        _cz2 = centerZ if centerZ is not None else kwargs.get('centerZ', kwargs.get('z', None))
        self._centerZ = None if _cz2 is None else float(_cz2)
        self._z = self._centerZ
        if self._centerZ is not None:
            self.hud = '3d'
        self.text = str(text)
        self.size = kwargs.get('size', 12)
        self.font = kwargs.get('font', 'arial')
        self.bold = kwargs.get('bold', False)
        self.italic = kwargs.get('italic', False)
        self.fill = kwargs.get('fill', 'black')
        self.opacity = kwargs.get('opacity', 100)
        self.visible = kwargs.get('visible', True)
        self.rotateAngle = kwargs.get('rotateAngle', 0)
        self._align = _normalize_align(kwargs.get('align', 'center'))
        self._x = float(x)
        self._y = float(y)
        _shapes.append(self)

    @property
    def align(self):
        return self._align

    @align.setter
    def align(self, _v):
        raise AttributeError('align is creation-time only in CMU Graphics')

    @property
    def centerX(self):
        return self._x

    @centerX.setter
    def centerX(self, v):
        self._x = float(v)

    @property
    def centerY(self):
        return self._y

    @centerY.setter
    def centerY(self, v):
        self._y = float(v)

    @property
    def left(self):
        return self._x - self.width / 2

    @property
    def top(self):
        return self._y - self.height / 2

    @property
    def right(self):
        return self._x + self.width / 2

    @property
    def bottom(self):
        return self._y + self.height / 2

    @property
    def width(self):
        return len(self.text) * self.size * 0.6

    @property
    def height(self):
        return float(self.size)

    def draw(self, renderer):
        if not self.visible:
            return
        renderer.draw_label(self.text, self._x, self._y, fill=self.fill,
                            size=self.size, font=self.font, bold=self.bold,
                            italic=self.italic, opacity=self.opacity,
                            align=self._align, rotateAngle=self.rotateAngle)


class Image(_BaseShape):
    def __init__(self, path, x, y, hud=None, centerZ=None, **kwargs):
        self.hud = _normalize_hud(hud, kwargs.get('mode', None))
        align = kwargs.pop('align', 'center')
        super().__init__(align=align, hud=hud, centerZ=centerZ,
                         **{k: v for k, v in kwargs.items() if k != 'align'})
        self.path = path
        self._width = float(kwargs.get('width', 100))
        self._height = float(kwargs.get('height', 100))
        l, t = _resolve_bbox(float(x), float(y), self._width, self._height, align)
        self._left, self._top = l, t
        _shapes.append(self)

    @property
    def centerX(self):
        return self._left + self._width / 2

    @centerX.setter
    def centerX(self, v):
        self._left = float(v) - self._width / 2

    @property
    def centerY(self):
        return self._top + self._height / 2

    @centerY.setter
    def centerY(self, v):
        self._top = float(v) - self._height / 2

    def draw(self, renderer):
        if not self.visible:
            return
        renderer.draw_image(self.path, self._left, self._top,
                            self._width, self._height,
                            opacity=self.opacity, rotateAngle=self.rotateAngle)


class Group:
    def __init__(self, *shapes, hud=None, centerZ=None, **kwargs):
        self.hud = _normalize_hud(hud, kwargs.get('mode', None))
        self.shapes = list(shapes)
        self.visible = True
        self.opacity = 100
        self.rotateAngle = 0
        _shapes.append(self)

    def add(self, *shapes):
        self.shapes.extend(shapes)

    def remove(self, shape):
        if shape in self.shapes:
            self.shapes.remove(shape)

    @property
    def left(self):
        vals = [s.left for s in self.shapes if hasattr(s, 'left')]
        return min(vals) if vals else 0

    @property
    def top(self):
        vals = [s.top for s in self.shapes if hasattr(s, 'top')]
        return min(vals) if vals else 0

    @property
    def right(self):
        vals = [s.right for s in self.shapes if hasattr(s, 'right')]
        return max(vals) if vals else 0

    @property
    def bottom(self):
        vals = [s.bottom for s in self.shapes if hasattr(s, 'bottom')]
        return max(vals) if vals else 0

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top

    @property
    def centerX(self):
        if not self.shapes:
            return 0
        return sum(s.centerX for s in self.shapes if hasattr(s, 'centerX')) / len(self.shapes)

    @centerX.setter
    def centerX(self, v):
        dx = float(v) - self.centerX
        for s in self.shapes:
            if hasattr(s, 'centerX'):
                s.centerX += dx

    @property
    def centerY(self):
        if not self.shapes:
            return 0
        return sum(s.centerY for s in self.shapes if hasattr(s, 'centerY')) / len(self.shapes)

    @centerY.setter
    def centerY(self, v):
        dy = float(v) - self.centerY
        for s in self.shapes:
            if hasattr(s, 'centerY'):
                s.centerY += dy

    def toFront(self):
        if self in _shapes:
            _shapes.remove(self)
            _shapes.append(self)

    def toBack(self):
        if self in _shapes:
            _shapes.remove(self)
            _shapes.insert(0, self)

    def draw(self, renderer):
        if not self.visible:
            return
        renderer.push_transform(self.centerX, self.centerY,
                                self.rotateAngle, self.opacity / 100.0)
        try:
            for s in list(self.shapes):
                try:
                    draw_fn = getattr(s, 'draw', None)
                    if draw_fn is not None:
                        draw_fn(renderer)
                except Exception:
                    pass
        finally:
            renderer.pop_transform()


# ----------------------------------------------------------------------
# Immediate-mode draw* functions -- forward to the current renderer.
# (In old scs.py these touched _ctx directly; that is what locked SCS
# to Canvas2D. They now work on every backend.)
# ----------------------------------------------------------------------

def _renderer_or_2d():
    # FIX v25: do NOT auto-create a 2d renderer here. _ensure_canvas used to
    # create 2d and steal the canvas. Now it just returns the canvas, so
    # returning _renderer (possibly None) is correct - run_app creates it.
    if _renderer is None:
        _ensure_canvas()
    return _renderer


def drawRect(x, y, width, height, fill='black', border=None, borderWidth=2,
             opacity=100, rotateAngle=0, dashes=False, align='left-top',
             visible=True, roundness=0, hud=False, centerZ=None):
    if not visible:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    left, top = _resolve_bbox(float(x), float(y), float(width), float(height),
                              _normalize_align(align))
    r.draw_rect(left, top, float(width), float(height), fill=fill, border=border,
                borderWidth=borderWidth, opacity=opacity, rotateAngle=rotateAngle,
                dashes=dashes, roundness=roundness)


def drawCircle(x, y, radius, fill='black', border=None, borderWidth=2,
               opacity=100, rotateAngle=0, dashes=False, align='center', visible=True, hud=False, centerZ=None):
    if not visible:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    w = h = float(radius) * 2
    left, top = _resolve_bbox(float(x), float(y), w, h, align)
    r.draw_circle(left + radius, top + radius, float(radius), fill=fill,
                  border=border, borderWidth=borderWidth, opacity=opacity,
                  rotateAngle=rotateAngle, dashes=dashes)


def drawOval(x, y, width, height, fill='black', border=None, borderWidth=2,
             opacity=100, rotateAngle=0, dashes=False, align='center', visible=True, hud=False, centerZ=None):
    if not visible:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    left, top = _resolve_bbox(float(x), float(y), float(width), float(height), align)
    r.draw_oval(left + float(width) / 2, top + float(height) / 2,
                float(width), float(height), fill=fill, border=border,
                borderWidth=borderWidth, opacity=opacity, rotateAngle=rotateAngle,
                dashes=dashes)


def drawRegularPolygon(x, y, radius, points, fill='black', border=None,
                       borderWidth=2, opacity=100, rotateAngle=0, dashes=False,
                       align='center', visible=True, hud=False, centerZ=None):
    if not visible:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    w = h = float(radius) * 2
    left, top = _resolve_bbox(float(x), float(y), w, h, align)
    r.draw_regular_polygon(left + radius, top + radius, float(radius), points,
                           fill=fill, border=border, borderWidth=borderWidth,
                           opacity=opacity, rotateAngle=rotateAngle, dashes=dashes)


def drawStar(x, y, radius, points, fill='black', border=None, borderWidth=2,
             opacity=100, rotateAngle=0, dashes=False, align='center',
             visible=True, ratio=0.5, hud=False, centerZ=None):
    if not visible:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    w = h = float(radius) * 2
    left, top = _resolve_bbox(float(x), float(y), w, h, align)
    r.draw_star(left + radius, top + radius, float(radius), points, fill=fill,
                border=border, borderWidth=borderWidth, opacity=opacity,
                rotateAngle=rotateAngle, dashes=dashes, ratio=ratio)


def drawLabel(text, x, y, fill='black', size=12, font='arial', bold=False,
              italic=False, opacity=100, align='center', visible=True,
              rotateAngle=0, hud=False, centerZ=None):
    if not visible:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    r.draw_label(str(text), float(x), float(y), fill=fill, size=size, font=font,
                 bold=bold, italic=italic, opacity=opacity, align=align,
                 rotateAngle=rotateAngle)


def drawLine(x1, y1, x2, y2, fill='black', lineWidth=2, opacity=100,
             dashes=False, visible=True, hud=False, centerZ=None):
    if not visible:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    r.draw_line(float(x1), float(y1), float(x2), float(y2), fill=fill,
                lineWidth=lineWidth, opacity=opacity, dashes=dashes)


def drawPolygon(*points, fill='black', border=None, borderWidth=2, opacity=100,
                rotateAngle=0, dashes=False, visible=True, hud=False, centerZ=None):
    if not visible or len(points) < 4:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    r.draw_polygon([float(p) for p in points], fill=fill, border=border,
                   borderWidth=borderWidth, opacity=opacity,
                   rotateAngle=rotateAngle, dashes=dashes)


def drawArc(x, y, width, height, startAngle, sweepAngle, fill=None, border=None,
            borderWidth=2, opacity=100, dashes=False, align='center', visible=True, hud=False, centerZ=None):
    if not visible:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    left, top = _resolve_bbox(float(x), float(y), float(width), float(height), align)
    r.draw_arc(left + float(width) / 2, top + float(height) / 2,
               float(width), float(height), float(startAngle), float(sweepAngle),
               fill=fill, border=border, borderWidth=borderWidth,
               opacity=opacity, dashes=dashes)


def drawImage(path, x, y, width=None, height=None, opacity=100, rotateAngle=0,
              align='center', visible=True, hud=False, centerZ=None):
    if not visible:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    w = float(width) if width is not None else 100.0
    h = float(height) if height is not None else 100.0
    left, top = _resolve_bbox(float(x), float(y), w, h, align)
    r.draw_image(path, left, top, w, h, opacity=opacity, rotateAngle=rotateAngle)


# ----------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------

def rgb(r, g, b):
    return 'rgb(%d,%d,%d)' % (int(r), int(g), int(b))


def gradient(*colors, start='top'):
    """Return a gradient dict. All three renderers understand it:
    2D builds a CanvasGradient, GPU backends sample it per-vertex.
    (Old scs.py returned only colors[0] -- a gradient that was not
    a gradient. This is the one intentional behaviour fix.)"""
    return {'_is_grad': True, 'colors': list(colors), 'start': start}


def distance(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)


def angleTo(x1, y1, x2, y2):
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def getPointInDir(x, y, angle, length):
    rad = math.radians(angle)
    return x + length * math.cos(rad), y + length * math.sin(rad)


def rounded(n):
    return round(n)


def makeList(n, v=None):
    return [v] * n if v is not None else [None] * n


def randrange(a, b=None):
    return _random.randrange(a) if b is None else _random.randrange(a, b)


def randint(a, b):
    return _random.randint(a, b)


def random(a=None, b=None):
    if a is None:
        return _random.random()
    if b is None:
        return _random.random() * a
    return _random.uniform(a, b)


# ----------------------------------------------------------------------
# Sound
# ----------------------------------------------------------------------

class Sound:
    def __init__(self, path):
        self.path = path
        self._audio = None
        try:
            self._audio = window.Audio.new(path)
        except Exception:
            pass

    def play(self, loop=False, restart=False):
        try:
            if self._audio:
                self._audio.loop = loop
                if restart:
                    self._audio.currentTime = 0
                self._audio.play()
        except Exception:
            pass

    def pause(self):
        try:
            if self._audio:
                self._audio.pause()
        except Exception:
            pass


# ----------------------------------------------------------------------
# App
# ----------------------------------------------------------------------

class App:
    def __init__(self, width=400, height=400, renderer=None, hud=False, **kwargs):
        global _app
        if isinstance(width, App):
            _src = width
            width = getattr(_src, 'width', 400)
            height = getattr(_src, 'height', 400)
            if renderer is None:
                renderer = getattr(_src, 'renderer', None)
            for _k in ('stepsPerSecond', 'background', 'paused'):
                if _k not in kwargs and hasattr(_src, _k):
                    kwargs[_k] = getattr(_src, _k)
        self.width = width
        self.height = height
        self.background = kwargs.get('background', 'white')
        self.stepsPerSecond = kwargs.get(
            'stepsPerSecond',
            kwargs.get('steps_per_second', kwargs.get('fps', 30)))
        self.paused = kwargs.get('paused', False)
        self.renderer = renderer  # per-app renderer request (runApp wins)
        self._onAppStart = None
        self._onStep = None
        self._redrawAll = None
        _app = self
        _clear_shapes()

    def runApp(self, *args, **kwargs):
        return runApp(self, *args, **kwargs)

    def run(self, *args, **kwargs):
        return runApp(self, *args, **kwargs)

    def loop(self, *args, **kwargs):
        return runApp(self, *args, **kwargs)


def _parse_run_args(args, kwargs):
    """Parse every runApp calling convention in the wild. Precedence:
    defaults < global _app from prior App(...) < App passed to runApp
    < explicit kwargs < explicit positionals. Unknown kwargs dropped,
    never TypeError."""
    kwargs = dict(kwargs) if kwargs else {}
    width, height, steps, renderer, canvas = 400, 400, 30, None, None
    try:
        if _app is not None:
            width = getattr(_app, 'width', width)
            height = getattr(_app, 'height', height)
            steps = getattr(_app, 'stepsPerSecond', steps)
            renderer = getattr(_app, 'renderer', renderer)
    except Exception:
        pass
    app_obj = None
    if args and isinstance(args[0], App):
        app_obj = args[0]
        args = args[1:]
    if app_obj is None and 'app' in kwargs and isinstance(kwargs.get('app'), App):
        app_obj = kwargs.pop('app')
    if app_obj is not None:
        try:
            width = getattr(app_obj, 'width', width)
            height = getattr(app_obj, 'height', height)
            steps = getattr(app_obj, 'stepsPerSecond', steps)
            renderer = getattr(app_obj, 'renderer', renderer)
        except Exception:
            pass
    if 'width' in kwargs:
        width = kwargs.pop('width')
    if 'height' in kwargs:
        height = kwargs.pop('height')
    for _k in ('stepsPerSecond', 'steps_per_second', 'fps', 'frameRate'):
        if _k in kwargs:
            steps = kwargs.pop(_k)
            break
    if 'renderer' in kwargs:
        renderer = kwargs.pop('renderer')
    if 'canvas' in kwargs:
        canvas = kwargs.pop('canvas')
    # HUD / 3D mode: MUST NOT be dropped. Any existing app must be able to
    # just change the runApp call: runApp(1050, 700, stepsPerSecond=60, renderer='webgl2')
    # or runApp(..., renderer='3d') or runApp(..., hud=True) or runApp(..., mode='hud').
    # These are parsed here and forwarded to run_app(), not dropped.
    hud = kwargs.pop('hud', None)
    mode = kwargs.pop('mode', None)
    # HTML-in-Canvas element: which DOM element to render in hud='html' mode.
    # Accepts element, '#id', '.class', or 'id'. None = default #scs-html-hud div.
    html_element = kwargs.pop('html_element', None)
    if html_element is None:
        html_element = kwargs.pop('html', None)
    if html_element is None:
        html_element = kwargs.pop('html_hud', None)
    # Both, with a flag: hud can be True/False OR a string:
    #   hud='texture' -> offscreen 2D canvas -> WebGL texture (works everywhere, default)
    #   hud='html'    -> live DOM -> WebGL texture via texElementSubImage2D (Chrome 157+ only, NO FALLBACK to texture)
    #   hud='auto'    -> try HTML if supported, else texture
    #   hud=True      -> 'texture' (backwards compat)
    #   hud='html-in-canvas' / 'html_in_canvas' / 'canvas' -> 'html'
    if isinstance(hud, str):
        _hud_str = hud.strip().lower().replace('-', '_')
        if _hud_str in ('html', 'html_in_canvas', 'html_canvas', 'canvas', 'dom', 'live'):
            hud = 'html'
        elif _hud_str in ('texture', 'tex', 'hud', '3d', 'hud_3d', '3d_hud'):
            hud = 'texture'
        elif _hud_str in ('auto', 'automatic'):
            hud = 'auto'
        elif _hud_str in ('1', 'true', 'yes', 'on'):
            hud = True
        elif _hud_str in ('0', 'false', 'no', 'off', 'none'):
            hud = False
    # Aliases: mode='3d' / mode='hud' / renderer='3d' / renderer='hud' all mean HUD texture.
    # mode='html' / mode='html-in-canvas' means HTML-in-Canvas.
    if mode is not None:
        mode = str(mode).lower().replace('-', '_')
        if mode in ('html', 'html_in_canvas', 'html_canvas', 'canvas', 'dom', 'live'):
            mode = 'html'
            hud = 'html'
        elif mode in ('auto', 'automatic'):
            mode = 'auto'
            hud = 'auto'
    if renderer is not None and str(renderer).lower() in ('3d', 'hud', 'hud-3d', '3d-hud'):
        mode = 'hud'
        renderer = 'webgl2'
        if hud is None:
            hud = 'texture'
    if mode in ('3d', 'hud', 'hud-3d', '3d-hud'):
        if hud is None:
            hud = 'texture'
        if renderer is None or str(renderer).lower() in ('3d', 'hud'):
            renderer = 'webgl2'
    # Normalize hud=True -> 'texture', hud='html' stays, hud='auto' stays
    if hud is True:
        hud = 'texture'
    # If mode is 'html' but hud was not set, hud='html' (already handled above)
    if mode == 'html' and hud is None:
        hud = 'html'
    # Extra kwargs are still dropped (never TypeError), but hud/mode are kept.
    # Return them via globals so runApp() can forward them.
    if len(args) >= 1:
        width = args[0]
    if len(args) >= 2:
        height = args[1]
    if len(args) >= 3:
        steps = args[2]
    if len(args) >= 4:
        renderer = args[3]
    if len(args) >= 5:
        canvas = args[4]
    # Attach hud/mode to the return via a tuple - callers unpack 7 values.
    return width, height, steps, renderer, canvas, hud, mode, html_element


def runApp(*args, **kwargs):
    """Full alias of run_app(). NEVER raises 'unexpected keyword argument'.
    Any existing app can just change this call to get it in 3D:
      runApp(1050, 700, stepsPerSecond=60)  -> 2D (default, backwards compat)
      runApp(1050, 700, stepsPerSecond=60, renderer='webgl2')  -> 2D app in 3D HUD
      runApp(1050, 700, stepsPerSecond=60, renderer='3d')  -> same, HUD
      runApp(1050, 700, stepsPerSecond=60, hud=True)  -> HUD
      runApp(1050, 700, stepsPerSecond=60, mode='hud')  -> HUD
    """
    width, height, steps, renderer, canvas, hud, mode, html_element = _parse_run_args(args, kwargs)
    return run_app(width=width, height=height,
                   stepsPerSecond=steps, renderer=renderer, canvas=canvas,
                   hud=hud, mode=mode, html_element=html_element)


def cmu_graphics_run(*args, **kwargs):
    """CMU alias. Same bulletproof parsing as runApp()."""
    width, height, steps, renderer, canvas, hud, mode, html_element = _parse_run_args(args, kwargs)
    return run_app(width=width, height=height,
                   stepsPerSecond=steps, renderer=renderer, canvas=canvas,
                   hud=hud, mode=mode, html_element=html_element)


# ----------------------------------------------------------------------
# Events (moved verbatim from index.html, plus touch + resize)
# ----------------------------------------------------------------------

def _call(name, *args):
    cb = _user_funcs.get(name)
    if cb is None:
        return
    try:
        cb(*args)
    except Exception:
        pass


def _fullscreen_btn_rect(w, h):
    # Minimal: 36x36, 16px margin from bottom-right in logical space.
    _m, _s = 16.0, 36.0
    return (float(w) - _m - _s, float(h) - _m - _s, _s, _s)

def _create_fullscreen_button(w, h):
    global _fullscreen_btn, _fullscreen_btn_label
    try:
        _l, _t, _s, _h = _fullscreen_btn_rect(w, h)
        # Rect() appends to _shapes - created AFTER onAppStart so it is topmost
        # (reversed _hud_shape_at checks it first) and draws on top of other HUD.
        _btn = Rect(_l, _t, _s, _h, fill='#1a1a2a', border='#555566', borderWidth=1, roundness=8, align='left-top')
        _btn._is_fullscreen_btn = True
        _lab = Label('\u26f6', _l + _s/2, _t + _s/2, fill='#e6e6e6', size=18, bold=True, align='center')
        _lab._is_fullscreen_btn = True
        _fullscreen_btn = _btn
        _fullscreen_btn_label = _lab
        return _btn
    except Exception:
        return None

def _reposition_fullscreen_button():
    try:
        if _fullscreen_btn is None:
            return
        _l, _t, _s, _h = _fullscreen_btn_rect(_canvas_width, _canvas_height)
        _fullscreen_btn._left = _l
        _fullscreen_btn._top = _t
        if _fullscreen_btn_label is not None:
            try:
                _fullscreen_btn_label.centerX = _l + _s/2
                _fullscreen_btn_label.centerY = _t + _s/2
            except Exception:
                pass
    except Exception:
        pass

def _toggle_fullscreen():
    # v29: request on the WRAPPER (canvas + controls stay visible), from a
    # user gesture, handle rejected promise. Do NOT assume success - the
    # fullscreenchange handler + ResizeObserver will measure the actual layout.
    try:
        try:
            _fs = document.fullscreenElement
        except Exception:
            _fs = None
        if _fs is not None:
            try:
                _p = document.exitFullscreen()
                # exitFullscreen also returns a promise in modern browsers - swallow rejection.
                try:
                    if _p is not None and hasattr(_p, 'catch'):
                        _p.catch(lambda _e: None)
                except Exception:
                    pass
            except Exception:
                pass
            return
        _w = _ensure_app_wrapper()
        _target = _w if _w is not None else _find_canvas()
        if _target is None:
            return
        try:
            _p = _target.requestFullscreen()
            try:
                if _p is not None and hasattr(_p, 'catch'):
                    _p.catch(lambda _e: None)
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        pass

def _on_fullscreen_change(ev=None):
    # v38: THE ONLY RESIZE ALLOWED. No RO, no DPR, no presentation.
    # Enter fullscreen -> canvas = screen size. Exit -> canvas = runApp size exactly.
    # _fullscreen_orig_w/h are set in run_app() from runApp() args and never change.
    try:
        try:
            _is_fs = document.fullscreenElement is not None
        except Exception:
            _is_fs = False
        _c = _find_canvas()
        if _c is None:
            return
        if _is_fs:
            try:
                _w, _h = int(window.innerWidth), int(window.innerHeight)
                _c.style.width = '%dpx' % _w; _c.style.height = '%dpx' % _h
                _c.width = _w; _c.height = _h
                globals()['__dict__']['_canvas_width'] = _w; globals()['__dict__']['_canvas_height'] = _h
            except Exception:
                pass
        else:
            try:
                _w = int(_fullscreen_orig_w) if _fullscreen_orig_w else 900
                _h = int(_fullscreen_orig_h) if _fullscreen_orig_h else 560
                _c.style.width = '%dpx' % _w; _c.style.height = '%dpx' % _h
                _c.width = _w; _c.height = _h
                globals()['__dict__']['_canvas_width'] = _w; globals()['__dict__']['_canvas_height'] = _h
            except Exception:
                pass
    except Exception:
        pass


def _pos(ev):
    # FIX v27 HUD events: map CSS rect -> logical app size (_canvas_width x
    # _canvas_height), NOT via backing-store canvas.width / DPR. Old code did
    # (clientX-left)*canvas.width/r.width/dpr. canvas.width = _canvas_width*dpr
    # at _size_canvas time, so if DPR changes after sizing (DevTools emulation,
    # zoom, display move), the division is wrong and clicks drift off the HUD
    # buttons. Logical size is the same space HUD Rects are drawn in (Rect(40,470,160,44)
    # means app x=40..200, y=470..514), so this is the space onMousePress expects.
    # Y is top-down in both: CSS y=0 is top, app y=0 is top, HUD texture V=0 is top
    # (see engine draw_hud_canvas: top vertex has V=0). No Y flip.
    canvas = _find_canvas()
    try:
        r = canvas.getBoundingClientRect()
        if not r.width or not r.height:
            return (0, 0)
        # Prefer logical size (set by _size_canvas). Fall back to 900x560 if not yet set.
        _lw = float(_canvas_width) if _canvas_width else 900.0
        _lh = float(_canvas_height) if _canvas_height else 560.0
        return ((ev.clientX - r.left) * _lw / float(r.width),
                (ev.clientY - r.top) * _lh / float(r.height))
    except Exception:
        return (0, 0)

def _hud_shape_at(x, y):
    # HUD hit-test in the SAME logical space as _pos and as HUD Rects are drawn.
    # Returns the topmost HUD shape (centerZ is None) whose bbox contains (x,y),
    # or None. Used to stop camera-drag from starting when a HUD button is clicked.
    try:
        for s in reversed(list(_shapes)):
            if getattr(s, 'centerZ', None) is not None:
                continue
            if not getattr(s, 'visible', True):
                continue
            # Rect: _left/_top/_width/_height. Circle/Oval/Label: use _left/_top + size.
            try:
                _l = float(getattr(s, '_left', 0) or 0)
                _t = float(getattr(s, '_top', 0) or 0)
                _w = float(getattr(s, '_width', 0) or 0)
                _h = float(getattr(s, '_height', 0) or 0)
                # Label has no _width/_height in some builds - use a small hit box around center
                if _w == 0 and _h == 0:
                    _cx = float(getattr(s, 'centerX', _l) or _l)
                    _cy = float(getattr(s, 'centerY', _t) or _t)
                    _l, _t, _w, _h = _cx - 20, _cy - 10, 40, 20
                if _l <= x <= _l + _w and _t <= y <= _t + _h:
                    return s
            except Exception:
                continue
    except Exception:
        pass
    return None


def _mp(ev):
    global _is_dragging
    # FIX v27 HUD events: HUD buttons are UI, not camera drag. If the press lands
    # on a HUD shape (centerZ is None), do NOT start dragging - the app's
    # onMousePress will handle the button (PLAY/STOP/CENTRE/MODE). Otherwise,
    # dragging starts for camera look.
    _x, _y = _pos(ev)
    _hit = _hud_shape_at(_x, _y)
    # Fullscreen button (enableFullscreen=True) is owned by the entrypoint, NOT
    # the app. It is a HUD Rect + Label, both tagged _is_fullscreen_btn.
    # If either is hit, toggle fullscreen, do NOT start drag, do NOT call
    # the app's onMousePress (the app did not create this button).
    if _hit is not None and getattr(_hit, '_is_fullscreen_btn', False):
        _is_dragging = False
        try:
            _find_canvas().focus()
        except Exception:
            pass
        _toggle_fullscreen()
        return
    # Only Rect buttons block drag - Labels are text, they should not block look.
    # If the hit is a Rect (button background), it is a UI element.
    if _hit is not None and type(_hit).__name__ in ('Rect',):
        _is_dragging = False
    else:
        _is_dragging = True
    try:
        _find_canvas().focus()
    except Exception:
        pass
    if _app is not None:
        _call('onMousePress', _app, _x, _y)


def _mr(ev):
    global _is_dragging
    if _app is not None:
        _call('onMouseRelease', _app, *_pos(ev))
    _is_dragging = False


def _mm(ev):
    if _app is None:
        return
    x, y = _pos(ev)
    if _is_dragging:
        _call('onMouseDrag', _app, x, y)
    _call('onMouseMove', _app, x, y)


def _norm_key(raw):
    if raw == ' ':
        return 'space'
    if len(raw) == 1:
        return raw
    low = raw.lower()
    return {'arrowleft': 'left', 'arrowright': 'right',
            'arrowup': 'up', 'arrowdown': 'down'}.get(low, low)


def _kp(ev):
    if _app is None:
        return
    try:
        ae = document.activeElement
        if ae is not None and ae.tagName in ('INPUT', 'TEXTAREA', 'SELECT'):
            return
    except Exception:
        pass
    k = _norm_key(ev.key)
    if k not in _pressed_keys:
        _pressed_keys.add(k)
        _call('onKeyPress', _app, k)


def _kr(ev):
    if _app is None:
        return
    k = _norm_key(ev.key)
    if k in _pressed_keys:
        _pressed_keys.discard(k)
    _call('onKeyRelease', _app, k)


def _kh():
    if _app is None:
        return
    for k in list(_pressed_keys):
        _call('onKeyHold', _app, k)


def _on_resize(ev=None):
    if _app is None:
        return
    _call('onResize', _app, _canvas_width, _canvas_height)


def _touch(ev, kind):
    try:
        t = ev.touches[0] if ev.touches and len(ev.touches) else None
        if t is None:
            return
        fake = type('E', (), {})()
        fake.clientX, fake.clientY = t.clientX, t.clientY
        if kind == 'start':
            _mp(fake)
        elif kind == 'end':
            _mr(fake)
        else:
            _mm(fake)
        try:
            ev.preventDefault()
        except Exception:
            pass
    except Exception:
        pass


_events_bound = False


def _bind_events():
    global _events_bound
    if _events_bound:
        return
    # v32: window.scs.eventsBound - one window property, nested.
    try:
        if bool(_scs_get('eventsBound', False)):
            _events_bound = True
            return
        _scs_set('eventsBound', True)
    except Exception:
        pass
    _events_bound = True
    canvas = _find_canvas()
    if canvas is None:
        return
    try:
        canvas.bind('mousedown', _mp)
        canvas.bind('mouseup', _mr)
        canvas.bind('mousemove', _mm)
        document.bind('keydown', _kp)
        document.bind('keyup', _kr)
        window.bind('resize', _on_resize)
        canvas.bind('touchstart', lambda ev: _touch(ev, 'start'))
        canvas.bind('touchmove', lambda ev: _touch(ev, 'move'))
        canvas.bind('touchend', lambda ev: _touch(ev, 'end'))
    except Exception:
        pass


# ----------------------------------------------------------------------
# Main loop + run_app (renderer selection happens here)
# ----------------------------------------------------------------------

def stop():
    global _app_timer
    if _app_timer is not None:
        try:
            timer.clear_interval(_app_timer)
        except Exception:
            pass
        _app_timer = None


def _refresh_user_funcs():
    global _user_funcs
    _user_funcs = {n: _user_ns[n] for n in _CALLBACK_NAMES
                   if callable(_user_ns.get(n))}


def _step():
    # Simulation ONLY. Separated from rendering so XR can render N
    # views without advancing the simulation N times (XR Decision 1).
    try:
        _kh()
        if _app is not None and 'onStep' in _user_funcs and not _app.paused:
            _call('onStep', _app)
    except Exception:
        pass


def _render_one_view(view, renderer=None):
    # Scene preparation (redrawAll + display list) happens ONCE per
    # view, with that view's borrowed target + viewport + camera.
    # Shared uploads / scene prep are NOT duplicated per view beyond
    # what the view actually needs (XR Decision 6: per-view camera data
    # is distinct from per-object / per-material data).
    r = renderer if renderer is not None else _renderer
    if r is None or _app is None:
        return
    # ENGINE PATH: 3D engine (webgl2-3d) - translate CMU shapes to engine scene.
    # FIX: Oval has no radius - use width/2, NOT 1.0. Old code made all balls radius 1.0 -> red/green clipped.
    if getattr(r, 'kind', '') == 'webgl2-3d':
        try:
            # FIX v26 HUD: engine path MUST call redrawAll first. Old code
            # never did, so _update_world never ran, sphere positions never
            # updated, and HUD labels never updated. Non-engine path calls
            # redrawAll - engine path must too.
            try:
                _call('redrawAll', _app)
            except Exception:
                pass
            r.clear_scene()
            r.add_floor(40, '#22223a')
            for s in list(_shapes):
                try:
                    if not getattr(s, 'visible', True):
                        continue
                    _cz = getattr(s, 'centerZ', None)
                    if _cz is None:
                        continue
                    _cx = float(getattr(s, 'centerX', 0) or 0)
                    _cy = float(getattr(s, 'centerY', 0) or 0)
                    _fill = getattr(s, 'fill', 'blue') or 'blue'
                    _cls = type(s).__name__
                    if _cls in ('Rect',):
                        r.add_box(_cx, _cy, float(_cz), float(getattr(s, 'width', 1) or 1), float(getattr(s, 'height', 1) or 1), 1.0, _fill, metalness=float(getattr(s, 'metalness', 1.0) or 1.0), roughness=float(getattr(s, 'roughness', 0.38) or 0.38), defectLevel=float(getattr(s, 'defectLevel', 0.5) or 0.5))
                    else:
                        # Circle: radius attr. Oval: width/2 (NOT 1.0). Ball highlights: radius attr.
                        if _cls in ('Oval',):
                            _rad = float(getattr(s, 'width', 1.0) or 1.0) / 2.0
                        else:
                            _rad = float(getattr(s, 'radius', getattr(s, '_radius', 1.0)) or 1.0)
                        # DAMAGED METAL: per-sphere defect + corrosion, stored on shape by app (v5).
                        # Default: metallic=1.0 (metal, not plastic), roughness from shape or 0.32, defect 0.45.
                        _def = float(getattr(s, 'defectLevel', 0.45) or 0.45)
                        _corr = float(getattr(s, 'corrosionEnabled', 0.0) or 0.0)
                        _met = float(getattr(s, 'metalness', 1.0) if getattr(s, 'metalness', None) is not None else 1.0)
                        _rou = float(getattr(s, 'roughness', 0.32) if getattr(s, 'roughness', None) is not None else 0.32)
                        # Copper-patina green is corrosion, not base colour - engine handles it via corrosionColor.
                        # For patina ball, base is copper, corrosion colour is patina green.
                        _corrCol = '#3affa8' if _corr > 0.5 else '#3a1a08'
                        try:
                            r.add_sphere(_cx, _cy, float(_cz), _rad, _fill, metalness=_met, roughness=_rou, defectLevel=_def, corrosionEnabled=_corr, corrosionColor=_corrCol)
                        except TypeError:
                            r.add_sphere(_cx, _cy, float(_cz), _rad, _fill)
                except Exception:
                    pass
            _cam = getattr(_app, 'camera', None)
            if _cam is None:
                # v33: correct camera primitive. Never pass None to engine -
                # engine returns False on None and you get black screen.
                # Default matches spatial_audio: pos (0,2,6), yaw 0, pitch -4, fov 60.
                try:
                    from scs_3d import Camera3D as _C3D
                    _cam = _C3D(position=(0.0, 2.0, 6.0), yaw=0.0, pitch=-4.0, fov=60.0)
                    _app.camera = _cam
                except Exception:
                    _cam = None
            if _cam is not None:
                r.render(_cam)
            # FIX v26 HUD: ALWAYS draw HUD shapes (centerZ is None) in 3D mode,
            # not only if _hud_mode is True. Old code required _hud_mode, but
            # _hud_mode is only True when _is_3d_app is True, and _is_3d_app is
            # only True when the app defines onRender3D etc. Spatial audio has
            # NO such callback - it uses centerZ shapes + redrawAll - so
            # _hud_mode stayed False and HUD was never drawn. Now: if there is
            # ANY HUD shape, lazily create the offscreen + 2d renderer and draw it.
            try:
                _has_hud = False
                for _hs in list(_shapes):
                    if getattr(_hs, 'centerZ', None) is None and getattr(_hs, 'visible', True):
                        _has_hud = True
                        break
                if _has_hud:
                    global _hud_offscreen, _hud_2d_renderer
                    # v34: HUD offscreen / renderer MUST stay in sync.
                    # _get_hud_offscreen recreates the canvas when CSS size or
                    # budgeted DPR changes. Old code kept the old 2D renderer,
                    # which still drew to the OLD (detached) offscreen - HUD
                    # briefly showed, then went into the off-canvas behind.
                    # Fix: if the offscreen changed, recreate the renderer.
                    _prev_off = _hud_offscreen
                    try:
                        _get_hud_offscreen(_canvas_width, _canvas_height)
                    except Exception:
                        pass
                    if _hud_offscreen is not None and _hud_offscreen is not _prev_off:
                        _hud_2d_renderer = None
                    if _hud_2d_renderer is None and _hud_offscreen is not None:
                        try:
                            _hud_2d_renderer = create_renderer('2d', _hud_offscreen, _canvas_width, _canvas_height)
                        except Exception:
                            _hud_2d_renderer = None
                    # Safety: renderer must draw to the CURRENT offscreen,
                    # not a stale one. If it does not, recreate it.
                    try:
                        _rc = getattr(_hud_2d_renderer, 'canvas', None) if _hud_2d_renderer is not None else None
                        if _rc is None:
                            _rc = getattr(_hud_2d_renderer, '_canvas', None) if _hud_2d_renderer is not None else None
                        if _rc is not None and _hud_offscreen is not None and _rc is not _hud_offscreen:
                            _hud_2d_renderer = create_renderer('2d', _hud_offscreen, _canvas_width, _canvas_height)
                    except Exception:
                        pass
                    if _hud_2d_renderer is not None:
                        _hud_2d_renderer.begin_frame('rgba(0,0,0,0)')
                        for s in list(_shapes):
                            try:
                                if getattr(s, 'centerZ', None) is None and getattr(s, 'visible', True):
                                    getattr(s, 'draw', lambda _r: None)(_hud_2d_renderer)
                            except Exception:
                                pass
                        _hud_2d_renderer.end_frame()
                        if _hud_offscreen is not None and hasattr(r, 'draw_hud_canvas'):
                            r.draw_hud_canvas(_hud_offscreen, 0, 0, _canvas_width, _canvas_height)
            except Exception:
                pass
        except Exception:
            pass
        return
    target = getattr(view, 'target', None) if view is not None else None
    viewport = getattr(view, 'viewport', None) if view is not None else None
    try:
        r.begin_frame(_app.background, target=target, viewport=viewport)
    except TypeError:
        r.begin_frame(_app.background)
    if view is not None and hasattr(r, 'push_view'):
        try:
            r.push_view(view)
        except Exception:
            pass
    try:
        _call('redrawAll', _app)
        # PER-SHAPE HUD vs 3D: 3D apps have flat shapes that can be HUD mode OR 3D mode.
        # hud=False/'texture'/True -> screen-space HUD (draw to _hud_2d_renderer / offscreen)
        # hud='3d'/'world'/False -> world-space 3D (draw to 3D renderer r, depth on)
        # 2D apps: no 3D, all shapes draw to r (2D renderer) - no routing needed.
        _is_3d = bool(getattr(_app, '_is_3d_app', False)) if _app is not None else False
        # _is_3d_app is computed in run_app from _user_funcs - use that if available
        try:
            _is_3d = any(k in _user_funcs for k in ('onRender3D', 'onDraw3D', 'draw3D', 'onRender', 'render3D'))
        except Exception:
            pass
        _hud_shapes_drawn = False
        for s in list(_shapes):
            try:
                # NO Canvas2D fallback for 3D: a shape with centerZ set
                # must NOT be drawn as a shaded 2D circle on a 2D renderer.
                # Fail loud, do not downgrade.
                try:
                    _rk = getattr(r, 'kind', getattr(r, 'name', ''))
                    if _is_3d_shape(s) and str(_rk).lower() in ('2d', 'canvas2d'):
                        raise RuntimeError('3D shape (centerZ set) requires WebGL2 / WebGPU, got 2D renderer. NO Canvas2D fallback.')
                except RuntimeError:
                    raise
                except Exception:
                    pass
                draw_fn = getattr(s, 'draw', None)
                if draw_fn is None:
                    continue
                # Route per shape in 3D apps only
                if _is_3d and _hud_mode:
                    _sh = getattr(s, 'hud', False)
                    # FINAL: hud=False (default) = 3D mode, hud=True = overlay. _normalize_hud maps
                    # True->'hud', False->'3d'. Handle raw bools: True => overlay, False => 3D.
                    if _sh is True:
                        _sh_str = 'hud'
                    elif _sh is False or _sh is None:
                        _sh_str = '3d'
                    else:
                        _sh_str = str(_sh).lower() if _sh is not None else '3d'
                    if _sh_str in ('hud', 'texture', 'html', 'true', '1', ''):
                        # Overlay flat shape (hud=True): draw to HUD 2D renderer (offscreen), NOT to 3D renderer
                        _hr = _hud_2d_renderer
                        if _hr is not None:
                            draw_fn(_hr)
                            _hud_shapes_drawn = True
                            continue
                        # No HUD 2D renderer (should not happen in 3D HUD mode) - fall through to 3D
                        # No fallback content: draw to 3D renderer as HUD quad via r.draw_label etc.
                        # For now, draw to r (it will handle HUD quads in 3D engine's MSDF path)
                        draw_fn(r)
                    else:
                        # 3D flat shape: world-space, depth on, draw to 3D renderer
                        draw_fn(r)
                else:
                    draw_fn(r)
            except Exception:
                pass
        # HUD mode: composite as a fullscreen HUD quad in the 3D scene.
        # Both, with a flag:
        #   hud='texture' -> offscreen 2D canvas (where scs.py's 2D app drew,
        #     unchanged) -> WebGL texture. Works everywhere.
        #   hud='html' -> live DOM element -> WebGL texture via
        #     texElementSubImage2D (Chrome 157+ only). Live, typeable,
        #     accessible. NO FALLBACK to texture if not supported.
        #   hud='auto' -> already resolved to 'html' or 'texture' in run_app().
        # This is the one-line-change contract: the 2D app never knows it is in 3D.
        # Only composite HUD if HUD shapes were actually drawn this frame.
        # 3D app with only 3D flat shapes (hud='3d') has no HUD to composite.
        if _hud_mode and _hud_shapes_drawn:
            try:
                _hud_done = False
                # Only composite HUD texture if HUD shapes were drawn (or app explicitly asked for HUD).
                # NO FALLBACK: hud='html' failing does NOT fall back to texture. Proper HTML or fail.
                if _hud_kind == 'html':
                    try:
                        _el = getHtmlHudElement()
                        if _el is not None and hasattr(r, 'draw_html_element'):
                            _hud_done = bool(r.draw_html_element(_el, 0, 0, _canvas_width, _canvas_height))
                    except Exception:
                        _hud_done = False
                    # No fallback to texture - if HTML fails, it fails. No fallback content.
                    if not _hud_done:
                        _debug_log('SCS HUD: hud="html" failed - NO FALLBACK to texture. Failing HUD composite.')
                elif _hud_offscreen is not None:
                    if hasattr(r, 'draw_hud_canvas'):
                        r.draw_hud_canvas(_hud_offscreen, 0, 0, _canvas_width, _canvas_height)
                    elif hasattr(r, 'draw_image'):
                        try:
                            r.draw_image(_hud_offscreen, 0, 0, _canvas_width, _canvas_height)
                        except Exception:
                            pass
            except Exception:
                pass
    finally:
        if view is not None and hasattr(r, 'pop_view'):
            try:
                r.pop_view()
            except Exception:
                pass
    try:
        r.end_frame()
    except Exception:
        pass


def _render(frame_ctx=None):
    # Desktop: a 1-view FrameContext. XR: the supplied FrameContext.
    # Either way the same code path renders the views.
    if frame_ctx is None:
        try:
            from scs_xr import FrameContext
            frame_ctx = FrameContext.desktop(_canvas_width, _canvas_height)
        except Exception:
            frame_ctx = None
    if frame_ctx is None or not getattr(frame_ctx, 'views', None):
        # No views == tracking unavailable (or no app): skip drawing,
        # keep the loop alive, never throw (XR Decision 10).
        return
    for view in frame_ctx.views:
        _render_one_view(view)


def renderFrame(frame_ctx):
    """Externally-driven rendering (XR Decision 1).

    renderFrame(frameContext) renders the CURRENT app state for the
    supplied views. It NEVER calls onStep: the caller (desktop loop or
    XRSession.requestAnimationFrame) already stepped the simulation
    once. Rendering 2 views must not advance the simulation twice.
    A FrameContext with no views (getViewerPose() == null) renders
    nothing and does not throw.
    """
    try:
        _render(frame_ctx)
    except Exception:
        pass


def _frame():
    # Internally-owned desktop loop: step once, then render once.
    # In XR this loop is STOPPED and the session owns scheduling.
    # Zero-sized container: skip normal rendering (Presentation D4).
    try:
        if _presentation_coordinator is not None:
            cur = _presentation_coordinator.current()
            if cur is not None and getattr(cur, 'is_zero_sized', False):
                return
        # v29 resize pipeline: apply coalesced resize + DPR change BEFORE draw.
        try:
            _check_pixel_ratio_change()
        except Exception:
            pass
        try:
            _apply_pending_resize()
        except Exception:
            pass
        _step()
        _render()
    except Exception:
        stop()


def _start_loop():
    global _app_timer
    # v31: stop() clears THIS instance's timer, but not another instance's.
    # The window flag + runApp 500ms guard above are the real dedup; here we
    # just ensure we don't start a second interval from THIS instance.
    stop()
    _frame()
    iv = int(1000 / _steps_per_second) if _steps_per_second > 0 else 33
    try:
        _app_timer = timer.set_interval(_frame, iv)
    except Exception:
        pass


def run_app(width=400, height=400, stepsPerSecond=30, renderer=None,
            canvas=None, hud=None, mode=None, html_element=None, enableFullscreen=False, **kwargs):
    """The initialiser. renderer: '2d', 'webgl2', or 'webgpu'. NO FALLBACK.
    NO WebGPU -> WebGL2 -> 2D fallback chain. 'auto' = default (2D, or HUD texture if 3D renderer). If you ask for 'webgl2' and
    WebGL2 fails, it FAILS. If you ask for 'webgpu' and WebGPU fails, it FAILS.
    Proper WebGL, proper WebGPU. No silent downgrade, no fallback content.

    Also honours (in order): explicit arg > _pending_renderer from
    setRenderer() > ?renderer= URL param > SCS_CONFIG.renderer.
    """
    global _app, _canvas, _steps_per_second, _pending_renderer
    # v33: NO 500ms guard. It black-screened: second exec_code stops loop #1,
    # then this guard rejected runApp #2, leaving NO loop running.
    # Single-run is enforced by boot() via window.scs.booted, not here.
    # runApp ALWAYS starts a loop after stop().
    if isinstance(width, App):
        _a = width
        try:
            width = getattr(_a, 'width', 400)
            height = getattr(_a, 'height', height)
            stepsPerSecond = getattr(_a, 'stepsPerSecond', stepsPerSecond)
            if renderer is None:
                renderer = getattr(_a, 'renderer', None)
        except Exception:
            pass
    if 'steps_per_second' in kwargs and stepsPerSecond == 30:
        stepsPerSecond = kwargs.get('steps_per_second')
    if 'fps' in kwargs and stepsPerSecond == 30:
        stepsPerSecond = kwargs.get('fps')
    _refresh_user_funcs()
    _bind_events()
    stop()
    if canvas is not None:
        _canvas = canvas
    _steps_per_second = stepsPerSecond
    # HUD resolution: explicit hud/mode > renderer='3d'/'hud' > 2D app + 3D renderer.
    # Any existing 2D app: runApp(..., renderer='webgl2') or renderer='3d' or hud=True
    # or mode='hud'/'3d' -> HUD mode. A 3D-native app (uses 3D callbacks) is NOT
    # forced into HUD; it runs natively. We detect 2D apps by: no 3D callbacks
    # defined (no onRender3D / onDraw3D / draw3D in _user_funcs).
    global _hud_mode, _hud_2d_renderer, _hud_3d_kind, _hud_kind, _hud_html_element
    global _fullscreen_enabled, _fullscreen_btn, _fullscreen_btn_label, _fullscreen_orig_w, _fullscreen_orig_h, _fullscreen_orig_style_w, _fullscreen_orig_style_h
    # enableFullscreen: explicit arg > kwargs (enableFullscreen / enable_fullscreen / fullscreenButton)
    _ef = enableFullscreen
    if not _ef:
        for _k in ('enableFullscreen', 'enable_fullscreen', 'fullscreenButton', 'fullscreen_button'):
            if _k in kwargs and kwargs.get(_k):
                _ef = True
                break
    _fullscreen_enabled = bool(_ef)
    _fullscreen_btn = None
    _fullscreen_btn_label = None
    _fullscreen_orig_w = int(width)
    _fullscreen_orig_h = int(height)
    _fullscreen_orig_style_w = None
    _fullscreen_orig_style_h = None
    _hud_mode = False
    _hud_2d_renderer = None
    _hud_3d_kind = None
    _hud_kind = 'texture'
    _hud_html_element = None
    _hud_requested = False
    # Both, with a flag: hud='texture' (default) vs hud='html' vs hud='auto'
    # Normalize hud: True -> 'texture', 'html'/'texture'/'auto' stay as-is
    _hud_flag = hud
    if _hud_flag is True:
        _hud_flag = 'texture'
    if isinstance(_hud_flag, str):
        _hf = _hud_flag.strip().lower().replace('-', '_')
        if _hf in ('html', 'html_in_canvas', 'html_canvas', 'canvas', 'dom', 'live'):
            _hud_flag = 'html'
        elif _hf in ('texture', 'tex', 'hud', '3d', 'hud_3d', '3d_hud'):
            _hud_flag = 'texture'
        elif _hf in ('auto', 'automatic'):
            _hud_flag = 'auto'
        elif _hf in ('1', 'true', 'yes', 'on'):
            _hud_flag = 'texture'
        elif _hf in ('0', 'false', 'no', 'off', 'none'):
            _hud_flag = False
    if _hud_flag in ('texture', 'html', 'auto'):
        _hud_requested = True
        _hud_kind = _hud_flag
    if mode is not None and str(mode).lower().replace('-', '_') in ('hud', '3d', 'hud_3d', '3d_hud'):
        _hud_requested = True
        if _hud_kind not in ('html', 'auto'):
            _hud_kind = 'texture'
    if mode is not None and str(mode).lower().replace('-', '_') in ('html', 'html_in_canvas', 'html_canvas', 'canvas', 'dom', 'live'):
        _hud_requested = True
        _hud_kind = 'html'
    if mode is not None and str(mode).lower().replace('-', '_') in ('auto', 'automatic'):
        _hud_requested = True
        _hud_kind = 'texture'  # auto = automatic texture, no explicit mode required
    if renderer is not None and str(renderer).lower() in ('3d', 'hud', 'hud-3d', '3d-hud'):
        _hud_requested = True
        renderer = 'webgl2'
        if _hud_kind not in ('html', 'auto'):
            _hud_kind = 'texture'
    # HUD ONLY MAKES SENSE IN 3D APPS. Was inverted before - that was the fuckup.
    # Old (wrong): 2D app + webgl2 => HUD. That forced every 2D app into an empty
    # 3D scene just to HUD over it. Nonsense.
    # Correct: 2D app + webgl2/webgpu => just 2D via WebGL, NO HUD, NO offscreen canvas.
    # 3D app (has onRender3D / onDraw3D / draw3D) + webgl2/webgpu => HUD is the 2D
    # overlay (labels, buttons) on top of the 3D scene. THAT is when HUD makes sense.
    _is_3d_app = any(k in _user_funcs for k in ('onRender3D', 'onDraw3D', 'draw3D', 'onRender', 'render3D'))
    # _renderer_req must include setRenderer() / _pending_renderer / App.renderer,
    # not just the runApp() arg.
    _renderer_req = str(renderer or _pending_renderer or getattr(_app, 'renderer', None) or '').lower() or None  # FIX: _app, not app - app is defined at line 2394, using app here = UnboundLocalError
    if not _is_3d_app and _hud_requested:
        # Explicit hud=True / mode='hud' on a 2D app - HUD makes no sense, ignore it.
        # Don't force a 2D app into HUD. Just render 2D.
        _debug_log('SCS HUD: hud requested on a 2D app (no 3D callbacks) - HUD only makes sense in 3D apps. Ignoring HUD, rendering 2D directly.')
        _hud_requested = False
        _hud_kind = 'texture'
    if _renderer_req in ('webgl2', 'webgl', 'webgpu', 'gpu', 'auto') and _is_3d_app:
        # Implicit HUD: 3D app + 3D renderer => HUD overlay automatically, no explicit mode needed.
        _hud_requested = True
        if _hud_kind not in ('html', 'texture'):
            _hud_kind = 'texture'
    if _hud_requested:
        _hud_mode = True
        # HUD is AUTOMATIC - no explicit mode required. Native cmu_graphics has NO hud param.
        # runApp(900,560, renderer='webgl2') with a 3D app => HUD texture, automatically.
        # 2D app + webgl2 => NO HUD, just 2D via WebGL (see above).
        # hud='auto' = "figure it out" = texture. NOT a fallback chain, NOT an error.
        # Only hud='html' is explicit: if Chrome 157+ is missing, it FAILS (no fallback to texture).
        if _hud_kind == 'auto':
            _hud_kind = 'texture'
        if _hud_kind == 'html':
            try:
                if not isHtmlInCanvasSupported():
                    _debug_log('SCS HUD: hud="html" requested but HTML-in-Canvas not supported in this browser (Chrome 157+ only). NO FALLBACK to texture. Failing.')
                    return
            except Exception:
                _debug_log('SCS HUD: hud="html" check failed. NO FALLBACK. Failing.')
                return
        # Store the HTML element for HTML mode (None = default #scs-html-hud div)
        if html_element is not None:
            try:
                setHtmlHudElement(html_element)
            except Exception:
                pass
        # Also honour html=... / html_hud=... passed via **kwargs (for runApp via scs.py)
        for _hk in ('html', 'html_hud', 'htmlElement'):
            if _hk in kwargs and kwargs.get(_hk) is not None:
                try:
                    setHtmlHudElement(kwargs.get(_hk))
                except Exception:
                    pass
        # 3D kind for HUD: explicit webgpu => webgpu, else webgl2.
        # 'auto' = default to webgl2 for HUD - NOT a fallback chain, NOT an error.
        # Native cmu_graphics has no renderer param, so auto must just work.
        if _renderer_req in ('webgpu', 'gpu'):
            _hud_3d_kind = 'webgpu'
        else:
            _hud_3d_kind = 'webgl2'
        # Offscreen 2D canvas is created AFTER _size_canvas (needs width/height)
        # but BEFORE the 3D renderer is created, so scs.py can find it.
    _size_canvas(width, height)
    # HUD: create the offscreen 2D canvas NOW, before any 2D drawing happens.
    # scs.py's _ensure_canvas() will return this canvas in HUD mode, so the
    # existing 2D app draws here, unchanged. The 3D renderer composites it.
    if _hud_mode:
        try:
            _get_hud_offscreen(width, height)
            try:
                _hud_2d_renderer = create_renderer('2d', _hud_offscreen, width, height)
            except Exception:
                _hud_2d_renderer = None
            # Force the visible canvas to the 3D kind - the 2D app is NOT on it.
            if renderer is None or str(renderer).lower() in ('2d', 'canvas', 'canvas2d'):
                renderer = _hud_3d_kind or 'webgl2'
        except Exception:
            pass
    _setup_presentation(_find_canvas())
    # App object: reuse the one user code already made if it matches,
    # else create it (this also clears the display list).
    app = _app
    if app is None or app.width != width or app.height != height:
        app = App(width, height)
    app.stepsPerSecond = stepsPerSecond
    _app = app
    _clear_shapes()
    _call('onAppStart', app)
    if 'appStarted' in _user_funcs and 'onAppStart' not in _user_funcs:
        _call('appStarted', app)
    # Fullscreen button: created AFTER onAppStart so it is topmost in _shapes
    # (drawn last, hit-tested first). Position derived from runApp width/height.
    if _fullscreen_enabled:
        try:
            _c0 = _find_canvas()
            if _c0 is not None:
                try:
                    _fullscreen_orig_style_w = _c0.style.width
                    _fullscreen_orig_style_h = _c0.style.height
                except Exception:
                    pass
            _create_fullscreen_button(width, height)
            # Bind once: fullscreenchange -> _on_fullscreen_change (resizing + reposition)
            try:
                document.addEventListener('fullscreenchange', _on_fullscreen_change)
            except Exception:
                pass
        except Exception:
            pass

    kind = _resolve_renderer_kind(
        renderer or _pending_renderer or getattr(app, 'renderer', None))
    _pending_renderer = None
    if _hud_mode:
        # In HUD mode the visible canvas is always 3D. If the resolved kind
        # is still '2d' (e.g. no renderer was passed, only hud=True), use _hud_3d_kind.
        # 'auto' = default to HUD 3D kind (webgl2) - automatic, no explicit mode required.
        if kind in ('2d', 'canvas', 'canvas2d', 'auto'):
            kind = _hud_3d_kind or 'webgl2'

    # NO FALLBACK. Proper WebGL / WebGPU. If the requested renderer fails, FAIL.
    # _fallback() is deleted - no WebGPU -> WebGL2 -> 2D chain, no silent downgrade.
    # BUT: 'auto' is NOT an error. Native cmu_graphics has NO renderer param -
    # runApp() with no renderer must just work and default to 2D. So 'auto' = '2d'.
    # No fallback chain, just the native default.
    if kind == 'auto':
        kind = '2d'

    if kind == 'webgpu':
        try:
            r = create_renderer('webgpu', _find_canvas(), width, height)
        except Exception as e:
            try:
                import traceback as _tb
                _detail = _tb.format_exc()
            except Exception:
                _detail = ''
            _debug_log('SCS renderer failed (webgpu): %s: %r\n%s - NO FALLBACK. Failing.' % (type(e).__name__, e, _detail))
            return
        if getattr(r, '_init_error', None) is not None:
            _debug_log('SCS renderer failed (webgpu): %s - NO FALLBACK. Failing.' % (r._init_error,))
            return

        def _gpu_ready():
            try:
                _scs_set('canvasContextKind', 'webgpu')
            except Exception:
                pass
            _activate_renderer(r, 'webgpu')
            _start_loop()

        def _gpu_fail(err):
            _debug_log('SCS renderer failed (webgpu): %s - NO FALLBACK. Failing.' % (err,))
            return

        r.on_ready = _gpu_ready
        r.on_error = _gpu_fail
        return  # loop starts from _gpu_ready

    # v35: switch canvas if context kind changed (WebGL -> 2D for fetch_demo).
    try:
        _replace_canvas_for_context(kind)
    except Exception:
        pass
    # webgl2 / 2d: explicit, no fallback. If create fails, FAIL.
    try:
        r = create_renderer(kind, _find_canvas(), width, height)
        try:
            _scs_set('canvasContextKind', str(kind).lower())
        except Exception:
            pass
    except Exception as e:
        try:
            import traceback as _tb
            _detail = _tb.format_exc()
        except Exception:
            _detail = ''
        _debug_log('SCS renderer failed (%s): %s: %r\n%s - NO FALLBACK. Failing.' % (kind, type(e).__name__, e, _detail))
        return
    _activate_renderer(r, kind)
    _start_loop()


# ----------------------------------------------------------------------
# WebXR: entry / exit / capability (scs_xr.py owns the concepts;
# this file owns the loop transfer + app-state wiring)
# ----------------------------------------------------------------------

def getXRCapability():
    try:
        from scs_xr import probe_xr_capability
        return probe_xr_capability().to_dict()
    except Exception:
        return {}


def getXRState():
    if _xr_manager is None:
        return 'not-started'
    return _xr_manager.state


def startXR(mode='immersive-vr', reference_space_type='local',
            backend=None):
    """Enter XR. Async setup: compatibility -> reference space ->
    layers -> transfer frame scheduling to XRSession.requestAnimationFrame.
    Unsupported combos fail HERE (init), not mid-frame (XR Decision 5/10).
    Returns the session manager; its .state tracks the lifecycle.
    """
    global _xr_manager, _xr_active
    try:
        from scs_xr import XRSessionManager
    except Exception as e:
        raise RuntimeError('WebXR module unavailable: %s' % e)
    backend = backend or ('webgpu' if _renderer_kind == 'webgpu' else 'webgl2')
    # Presentation for the active backend (capability-tested in enter()).
    presentation = None
    try:
        from scs_xr import WebGLXRPresentation, WebGPUXRPresentation
        if backend == 'webgpu':
            presentation = None  # XRGPUBinding is created per-session
        else:
            presentation = None  # XRWebGLLayer is created per-session
    except Exception:
        pass

    def _on_xr_frame(frame_ctx, xr_frame):
        # XR owns timing: NO onStep here. The desktop loop already
        # stepped once per desktop frame; XR frames render only.
        # Input: semantic actions from tracked sources (XR Decision 9).
        try:
            for src in getattr(frame_ctx, 'input_sources', []) or []:
                if getattr(src, 'select_pressed', False):
                    _call('onXRSelect', _app, src)
                if getattr(src, 'squeeze_pressed', False):
                    _call('onXRSqueeze', _app, src)
                _call('onXRInput', _app, src)
        except Exception:
            pass
        renderFrame(frame_ctx)

    def _on_xr_exit():
        global _xr_active
        _xr_active = False
        # Symmetric teardown: restore non-XR rendering (XR Decision 10).
        try:
            _start_loop()
        except Exception:
            pass

    _xr_manager = XRSessionManager(on_frame=_on_xr_frame, on_exit=_on_xr_exit)
    # Stop the internally-owned loop BEFORE transferring scheduling.
    stop()
    _xr_active = True
    _xr_manager.enter(mode=mode, reference_space_type=reference_space_type,
                      backend=backend)
    return _xr_manager


def stopXR():
    """Exit XR and restore non-XR rendering."""
    global _xr_active
    if _xr_manager is not None:
        try:
            _xr_manager.exit()
        except Exception:
            pass
    _xr_active = False


# ----------------------------------------------------------------------
# Integrations: adapters around the renderer (common contract:
# explicit ownership, async lifecycle, timestamped data, bounded work)
# ----------------------------------------------------------------------

def getAssetCache():
    """Async asset cache (IndexedDB): versioned binary data, never GPU handles."""
    try:
        from scs_storage import assets
        return assets
    except Exception:
        return None


def getPrefs():
    """Small preferences only (localStorage, string-only)."""
    try:
        from scs_storage import prefs
        return prefs
    except Exception:
        return None


def getAudioEngine(context=None):
    """AudioEngine with a separate clock. If `context` is supplied,
    the engine does NOT own it (dispose never closes it). Call
    engine.resume() from a user gesture (autoplay policy)."""
    try:
        from scs_audio import AudioEngine
        return AudioEngine(context=context)
    except Exception:
        return None


def getMediaAdapter(kind='camera', source=None, **kw):
    """Media-source adapter: 'camera' (latest buffering), 'video'
    (element), or 'frames' (VideoFrame producer). The adapter is
    cached; imported external textures are one-frame-valid."""
    try:
        from scs_media import CameraAdapter, VideoElementAdapter, VideoFrameAdapter
        if kind == 'camera':
            return CameraAdapter(source, **kw)
        if kind == 'frames':
            return VideoFrameAdapter(**kw)
        return VideoElementAdapter(source, **kw)
    except Exception:
        return None


def getSerialAdapter(**kw):
    """Web Serial adapter. Call adapter.request() from a click
    (user activation required), never from deferred init."""
    try:
        from scs_serial import SerialAdapter
        return SerialAdapter(**kw)
    except Exception:
        return None


def getUSBAdapter(**kw):
    """WebUSB adapter -- DISTINCT from Serial, even for a USB device
    that exposes a serial port."""
    try:
        from scs_serial import USBAdapter
        return USBAdapter(**kw)
    except Exception:
        return None


# [STRIPPED 70 bytes]
# Presentation / fullscreen (scs_presentation.py)
# [STRIPPED 70 bytes]

def getPresentationController():
    return _presentation


def getDisplayMetrics():
    try:
        from scs_core import DisplayConfig
        if _presentation_coordinator is not None:
            cur = _presentation_coordinator.current()
            if cur is not None:
                return cur.to_dict()
        return DisplayConfig(_canvas_width, _canvas_height,
                             dpr=_dpr(), render_scale=_render_scale,
                             pixel_ratio_cap=_pixel_ratio_cap,
                             pixel_budget=_pixel_budget).to_dict()
    except Exception:
        return {}


def setRenderScale(scale):
    global _render_scale
    _render_scale = float(scale)
    try:
        if _presentation_coordinator is not None:
            cur = _presentation_coordinator.current()
            if cur is not None:
                from scs_presentation import DisplayMetrics
                _presentation_coordinator.force_apply(DisplayMetrics(
                    cur.css_width, cur.css_height, cur.dpr,
                    render_scale=_render_scale,
                    pixel_ratio_cap=_pixel_ratio_cap,
                    pixel_budget=_pixel_budget))
    except Exception:
        pass
    return _render_scale


def setPixelBudget(budget=None, pixel_ratio_cap=None):
    global _pixel_budget, _pixel_ratio_cap
    if budget is not None:
        _pixel_budget = int(budget)
    if pixel_ratio_cap is not None:
        _pixel_ratio_cap = float(pixel_ratio_cap)
    return {'pixel_budget': _pixel_budget, 'pixel_ratio_cap': _pixel_ratio_cap}


def enterFullscreen(element=None):
    """Async presentation mode. MUST be called directly from a user
    gesture -- never deferred behind asset loading. Fullscreens the
    presentation CONTAINER, not necessarily the canvas."""
    if _presentation is None:
        raise RuntimeError('No presentation controller: call run_app() first.')
    return _presentation.enter_fullscreen(element)


def exitFullscreen():
    if _presentation is None:
        return None
    return _presentation.exit_fullscreen()


def getFullscreenState():
    if _presentation is None:
        return {'mode': 'embedded', 'is_fullscreen': False,
                'supports_fullscreen': False}
    return {'mode': _presentation.current_mode(),
            'is_fullscreen': _presentation.is_fullscreen(),
            'supports_fullscreen': _presentation.supports_fullscreen()}


def _setup_presentation(canvas):
    # v38: NO RESPONSIVE. No PresentationController, no ResizeCoordinator, no 100vw/100vh.
    return

# ----------------------------------------------------------------------
# App loading (was in index.html)
# ----------------------------------------------------------------------

def app_file(app=None):
    """Top level: user simply points to a valid app.
    Precedence (first wins):
      1. explicit boot(app) / load(app) arg - boot("myapp.py")
      2. ?app=myapp - URL param, user pointing at top level. MUST win over data-app.
         BUG FIX: data-app="apps/app.py" in index.html used to win over ?app=fetch_demo,
         so ?app=fetch_demo showed app.py. ?app= is explicit, data-app is the HTML default.
      3. window.SCS_CONFIG.app - npm / CDN config
      4. <canvas data-app="apps/myapp.py"> - fallback in HTML, only if no URL / config
      5. default apps/app.py
    A valid app is any .py file with CMU-style onAppStart/redrawAll/runApp.
    No suffering: no registry, no manifest, no build step."""
    d = 'apps/app.py'
    try:
        v = None
        if app is not None:
            v = str(app)
        if not v:
            # ?app= FIRST - user pointing at top level in URL. Must win over data-app.
            v = _url_param('app')
        if not v:
            cfg_app = _config_value('app')
            if cfg_app:
                v = str(cfg_app)
        if not v:
            # <canvas data-app="..."> - HTML default only, if no URL / config / explicit arg.
            try:
                from browser import document as _doc
                for _cid in ('canvas', 'cmu-canvas'):
                    try:
                        _cv = _doc[_cid]
                        if _cv is not None:
                            _dv = None
                            try:
                                _dv = _cv.getAttribute('data-app')
                            except Exception:
                                try:
                                    _dv = getattr(_cv, 'dataset', None)
                                    if _dv is not None:
                                        _dv = getattr(_dv, 'app', None)
                                except Exception:
                                    _dv = None
                            if _dv:
                                v = str(_dv)
                                break
                    except Exception:
                        pass
            except Exception:
                pass
        if not v:
            return d
        try:
            v = window.decodeURIComponent(v)
        except Exception:
            pass
        v = v.strip()
        if not v or '..' in v or v.startswith('/') or '\\' in v:
            return d
        if v.endswith('.py'):
            v = v[:-3]
        if v.startswith('apps/'):
            b = v[5:].split('/')[-1]
            return 'apps/' + b + '.py'
        b = v.split('/')[-1]
        b = ''.join(c for c in b if c.isalnum() or c in '_-')
        return 'apps/' + b + '.py' if b else d
    except Exception:
        return d


def _app_url(name):
    base = _config_value('appBase')
    if base:
        return str(base).rstrip('/') + '/' + name
    return name


def exec_code(code, fn):
    global _user_ns, _user_funcs
    stop()
    _clear_shapes()
    _user_ns = {'__builtins__': __builtins__}
    for name in __all__:
        if name in globals():
            _user_ns[name] = globals()[name]
    _user_ns['sin'] = math.sin
    _user_ns['cos'] = math.cos
    _user_ns['atan2'] = math.atan2
    _user_ns['sqrt'] = math.sqrt
    _user_ns['pi'] = math.pi
    _user_ns['runApp'] = runApp
    _user_ns['run'] = runApp
    _user_ns['loop'] = runApp
    _user_ns['cmu_graphics_run'] = cmu_graphics_run
    _user_ns['App'] = App
    _user_ns['getAssetCache'] = getAssetCache
    _user_ns['getPrefs'] = getPrefs
    _user_ns['getAudioEngine'] = getAudioEngine
    _user_ns['getMediaAdapter'] = getMediaAdapter
    _user_ns['getSerialAdapter'] = getSerialAdapter
    _user_ns['getUSBAdapter'] = getUSBAdapter
    _user_ns['renderFrame'] = renderFrame
    _user_ns['startXR'] = startXR
    _user_ns['stopXR'] = stopXR
    _user_ns['getXRState'] = getXRState
    _user_ns['getXRCapability'] = getXRCapability
    # JS / CDN bridge: SCS.create({callbacks: {onAppStart, ...}}) passes
    # JS functions; Brython can call them directly.
    try:
        cfg = _js_config()
        if cfg is not None:
            cbs = getattr(cfg, 'callbacks', None)
            if cbs is not None:
                for n in _CALLBACK_NAMES:
                    try:
                        fn_cb = getattr(cbs, n, None)
                        if callable(fn_cb):
                            _user_ns[n] = fn_cb
                    except Exception:
                        pass
    except Exception:
        pass
    # CRITICAL: Brython ignores sys.modules['scs'] = _ep in scs.py.
    # `import scs` loads a SEPARATE scs module (old runApp(width=400, height=400)),
    # and app.py's `from scs import *` overwrites _user_ns['runApp'] with that old one.
    # Patch the LOADED scs module object in memory BEFORE exec, so the star
    # import inside app.py gets the fixed runApp.
    try:
        import scs as _scs_patch
        _scs_patch.runApp = runApp
        _scs_patch.run = runApp
        _scs_patch.loop = runApp
        _scs_patch.cmu_graphics_run = cmu_graphics_run
        _scs_patch.run_app = run_app
    except Exception:
        pass
    try:
        import sys as _sys2
        try:
            _sys2.modules['scs'] = _sys2.modules['scs_entrypoint']
        except Exception:
            pass
    except Exception:
        pass
    try:
        exec(code, _user_ns)
        _refresh_user_funcs()
        if _user_funcs:
            # CMU-style app: callbacks defined, no explicit runApp() call
            # (or runApp() already started the loop -- starting again is
            # a no-op because run_app stops the old timer first).
            w = _config_value('width') or 1050
            h = _config_value('height') or 700
            try:
                w = int(w)
                h = int(h)
            except Exception:
                w, h = 1050, 700
            # Only auto-start if the loop is not already running.
            if _app_timer is None:
                run_app(width=w, height=h)
    except Exception as e:
        _debug_log('SCS exec error in %s: %s' % (fn, e))
        # Prove WHICH runApp app.py actually called: _user_ns['runApp'] may have
        # been overwritten by `from scs import *` inside app.py with a DIFFERENT
        # runApp (e.g. from scs.py or cmu_graphics.py) that still has the old
        # def runApp(width=400, height=400) signature. Log it.
        try:
            import inspect as _insp2
            _ns_run = _user_ns.get('runApp', None)
            try:
                _ns_sig = str(_insp2.signature(_ns_run)) if _ns_run is not None else 'None'
            except Exception:
                _ns_sig = 'signature-unavailable'
            _ns_msg = '[SCS] exec failed: _user_ns runApp' + _ns_sig + ' ep.runApp' + str(_insp2.signature(runApp))
            print(_ns_msg)
            try:
                from browser import window as _w3
                _w3.console.log(_ns_msg)
            except Exception:
                pass
            # What does `import scs` give RIGHT NOW?
            try:
                import scs as _scs_now
                _scs_sig = str(_insp2.signature(_scs_now.runApp))
                _scs_msg = '[SCS] import scs runApp' + _scs_sig + ' scs module=' + str(getattr(_scs_now, '__name__', '?')) + ' is_ep=' + str(_scs_now is globals().get('_ep', None) or _scs_now is __import__('scs_entrypoint'))
                print(_scs_msg)
                try:
                    _w3.console.log(_scs_msg)
                except Exception:
                    pass
            except Exception as _e_scs:
                print('[SCS] import scs failed: ' + str(_e_scs))
            # SCS uses the cmu_graphics API, NOT the actual cmu_graphics module.
            # Never `import cmu_graphics` - there is no cmu_graphics.py on the server,
            # and trying to fetch it is what caused the 404s. SCS *is* the API.
            # App code uses `from scs import *`, never `from cmu_graphics import *`.
            # First line of app code - what does it import?
            try:
                _first = str(code)[:300].replace(chr(10), ' | ')
                _first_msg = '[SCS] app code head: ' + _first
                print(_first_msg)
                try:
                    _w3.console.log(_first_msg)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass


def load(app=None):
    # JS loader may inject code directly (SCS.create({code: '...'})).
    code = _config_value('code')
    if code:
        exec_code(str(code), '<SCS.create code>')
        return
    # Top level: point to a valid app. load(app) / boot(app) wins, else data-app / ?app= / SCS_CONFIG.app / default.
    t = app_file(app)
    url = _app_url(t)

    def ok(txt):
        if txt:
            # Never exec HTML as Python: 404 / Netlify fallback returns HTML, not .py.
            _s = str(txt).lstrip()[:200].lower()
            if _s.startswith('<!doctype html') or _s.startswith('<html'):
                _debug_log('SCS could not load %s: got HTML (404), not Python. File missing?' % url)
                return
            exec_code(txt, t)

    def fail(e):
        _debug_log('SCS could not load %s: %s' % (url, e))

    def _on_resp(r):
        # Check ok / status BEFORE reading body. 404 must not be exec'd.
        try:
            _ok = getattr(r, 'ok', True)
            _status = getattr(r, 'status', 200)
        except Exception:
            _ok, _status = True, 200
        if not _ok:
            _debug_log('SCS could not load %s: HTTP %s (file missing?)' % (url, _status))
            return
        try:
            r.text().then(ok)
        except Exception as e:
            fail(e)

    try:
        window.fetch(url).then(_on_resp).catch(fail)
    except Exception:
        pass


def boot(app=None):
    """Top level: user simply points to a valid app.
    boot() - data-app / ?app= / SCS_CONFIG.app / default apps/app.py
    boot("myapp.py") - point to a valid app, no config, no suffering
    boot("apps/myapp.py") - same, explicit path
    Binds events, loads the app, and starts it. Loop / events / renderer
    all live in the package, not in HTML."""
    # Console proof at boot(): which runApp is actually in globals() RIGHT NOW.
    try:
        import inspect as _insp
        try:
            _sig = str(_insp.signature(runApp))
        except Exception:
            _sig = 'signature-unavailable'
        _boot_msg = '[SCS entrypoint] boot() version=' + __version__ + ' runApp' + _sig
        _debug_log(_boot_msg)
    except Exception:
        pass
    # v31 single-run: second boot() on the same page is a duplicate (e.g.
    # index.html + loader both calling boot, or Brython executing the
    # <script> twice). Ignore it - do NOT fetch/exec the app a second time.
    try:
        if bool(_scs_get('booted', False)):
            try:
                print('[SCS entrypoint] boot() already ran - ignoring duplicate boot()')
            except Exception:
                pass
            return
        _scs_set('booted', True)
    except Exception:
        pass
    _bind_events()
    load(app)


def boot_sandbox():
    """Sandbox boot - baked into the package, not in HTML.
    Thin shell (sandbox.html) has only <canvas> + <textarea id=\"code-input\">.
    No loop, no events, no renderer, no shape drawing in HTML.
    This function owns all of it: default example (CMU-style, no suffering),
    Run/Stop + log UI created here if missing, event binding, exec, loop.
    Users just import from npm or load from CDN and it works."""
    try:
        from browser import document, window
    except Exception:
        return
    try:
        # Default CMU example - lives in the package, not in HTML, so the shell stays thin.
        # Same API students already know: from scs import *, onAppStart, redrawAll, onMousePress, runApp.
        _default = (
            "from scs import *\n\n"
            "def onAppStart(app):\n"
            "    app.dots = []\n"
            "    app.color = 'blue'\n\n"
            "def redrawAll(app):\n"
            "    for cx, cy in app.dots:\n"
            "        drawCircle(cx, cy, 20, fill=app.color)\n\n"
            "def onMousePress(app, mouseX, mouseY):\n"
            "    app.dots.append((mouseX, mouseY))\n\n"
            "def onKeyPress(app, key):\n"
            "    if key == 'r':\n"
            "        app.color = 'red'\n"
            "    elif key == 'b':\n"
            "        app.color = 'blue'\n\n"
            "def main():\n"
            "    runApp()\n\n"
            "main()\n"
        )
        try:
            _ta = document['code-input']
            if not _ta.value:
                _ta.value = _default
        except Exception:
            pass
        # Log + Run/Stop UI - created here in the package, not in HTML.
        # If the shell already has them (old shells), reuse them. If not, create them.
        try:
            _log = None
            try:
                _log = document['log']
            except Exception:
                pass
            if _log is None:
                try:
                    _log = document.createElement('div')
                    _log.id = 'log'
                    try:
                        _log.style.cssText = 'margin-top:10px;background:#1a1d24;border:1px solid #3a3f4b;border-radius:6px;padding:10px;min-height:80px;white-space:pre-wrap;font-size:11px;max-height:300px;overflow:auto;color:#e6e6e6;'
                    except Exception:
                        pass
                    document.body.appendChild(_log)
                except Exception:
                    _log = None
            def _log_msg(msg):
                try:
                    if _log is not None:
                        _log.text += str(msg) + '\n'
                except Exception:
                    pass
            # Wire _debug_log to the sandbox log, so package errors show up here, not just console.
            try:
                _orig = _debug_log
                def _sb_log(m):
                    try:
                        _log_msg(m)
                    except Exception:
                        pass
                    try:
                        _orig(m)
                    except Exception:
                        pass
                globals()['_debug_log'] = _sb_log
            except Exception:
                pass
            # Run / Stop buttons - created in the package if missing.
            try:
                _run_btn = None
                try:
                    _run_btn = document['run-btn']
                except Exception:
                    pass
                if _run_btn is None:
                    _run_btn = document.createElement('button')
                    _run_btn.id = 'run-btn'
                    _run_btn.text = 'Run'
                    try:
                        _run_btn.style.cssText = 'background:#4c6ef5;color:white;border:0;padding:10px 18px;border-radius:6px;cursor:pointer;font-weight:600;margin-right:8px;'
                    except Exception:
                        pass
                    document.body.appendChild(_run_btn)
                _stop_btn = None
                try:
                    _stop_btn = document['stop-btn']
                except Exception:
                    pass
                if _stop_btn is None:
                    _stop_btn = document.createElement('button')
                    _stop_btn.id = 'stop-btn'
                    _stop_btn.text = 'Stop'
                    try:
                        _stop_btn.style.cssText = 'background:#4c6ef5;color:white;border:0;padding:10px 18px;border-radius:6px;cursor:pointer;font-weight:600;margin-right:8px;'
                    except Exception:
                        pass
                    document.body.appendChild(_stop_btn)
            except Exception:
                _run_btn = _stop_btn = None
            def _run(ev=None):
                try:
                    _ta2 = document['code-input']
                    exec_code(_ta2.value, '<sandbox>')
                    _log_msg('Running; renderer=' + str(getRendererKind()))
                except Exception:
                    import traceback
                    _log_msg('Error:\n' + traceback.format_exc())
            def _stop(ev=None):
                try:
                    stop()
                    _log_msg('Stopped.')
                except Exception:
                    pass
            try:
                if _run_btn is not None:
                    _run_btn.bind('click', _run)
                if _stop_btn is not None:
                    _stop_btn.bind('click', _stop)
            except Exception:
                pass
            # Sandbox: just enter app code. Paste / type in the textarea and it runs.
            # No Run click required: auto-run on input (debounced) - all in the package, not HTML.
            try:
                _ta3 = document['code-input']
                _timer = {'id': None}
                def _on_input(ev=None):
                    try:
                        from browser import timer as _tm
                        try:
                            if _timer['id'] is not None:
                                _tm.clear_timeout(_timer['id'])
                        except Exception:
                            pass
                        def _do():
                            try:
                                _run()
                            except Exception:
                                pass
                        try:
                            _timer['id'] = _tm.set_timeout(_do, 600)
                        except Exception:
                            _do()
                    except Exception:
                        pass
                try:
                    _ta3.bind('input', _on_input)
                except Exception:
                    pass
            except Exception:
                pass
            _bind_events()
            # Auto-run once, so the student sees something immediately - no suffering.
            try:
                _run()
            except Exception:
                pass
            _log_msg('Sandbox ready. API from package (scs_entrypoint.py via scs.py).')
        except Exception:
            pass
    except Exception:
        pass


main = boot
