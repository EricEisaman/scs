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
        runApp(..., renderer='webgpu')   # WebGPU (async init, auto fallback)
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
    'runApp', 'run', 'loop', 'run_app', 'stop', 'boot', 'main',
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
]

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
    try:
        if hasattr(window, 'console'):
            window.console.log(msg)
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


def _size_canvas(width, height):
    """Backing store = width*dpr, CSS size = width px. User coords stay
    in CSS pixels on every renderer."""
    global _canvas_width, _canvas_height
    _canvas_width, _canvas_height = int(width), int(height)
    canvas = _find_canvas()
    if canvas is None:
        return
    dpr = _dpr()
    try:
        canvas.width = int(width * dpr)
        canvas.height = int(height * dpr)
        canvas.style.width = '%dpx' % int(width)
        canvas.style.height = '%dpx' % int(height)
        try:
            canvas.setAttribute('width', str(int(width * dpr)))
            canvas.setAttribute('height', str(int(height * dpr)))
        except Exception:
            pass
    except Exception:
        pass


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
    """window.SCS_CONFIG set by the JS / CDN loader (see src/scs-loader.js).
    Returns a dict-like or None."""
    try:
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


def create_renderer(kind, canvas, width, height):
    """Instantiate a renderer. 'webgpu' is async -- the returned object
    has .ready == False until on_ready fires; the entrypoint falls back
    on on_error. Raises on sync failure (2D / WebGL2)."""
    kind = (kind or '2d').lower()
    if kind in ('2d', 'canvas', 'canvas2d'):
        from scs_2d import Renderer2D
        return Renderer2D(canvas, width, height)
    if kind in ('webgl', 'webgl2', 'webgl-2'):
        from scs_webgl import RendererWebGL2
        return RendererWebGL2(canvas, width, height)
    if kind in ('webgpu', 'gpu'):
        from scs_webgpu import RendererWebGPU
        return RendererWebGPU(canvas, width, height)
    raise ValueError('Unknown renderer %r (expected 2d, webgl2, webgpu, auto)' % kind)


def _resolve_renderer_kind(requested):
    """Precedence: explicit arg > ?renderer= > SCS_CONFIG.renderer >
    SCS_CONFIG default > '2d'. 'auto' stays 'auto'."""
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
    if kind == '2d' and renderer is not None:
        _ctx = getattr(renderer, 'ctx', None)
    else:
        _ctx = None


def _ensure_canvas():
    global _canvas
    canvas = _find_canvas()
    if canvas is None:
        return None
    if _renderer is None:
        _size_canvas(_canvas_width, _canvas_height)
        try:
            r = create_renderer('2d', canvas, _canvas_width, _canvas_height)
            _activate_renderer(r, '2d')
        except Exception:
            pass
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
    def __init__(self, **kwargs):
        self._align = _normalize_align(kwargs.get('align', 'center'))
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
    def __init__(self, x, y, width, height, **kwargs):
        align = kwargs.pop('align', 'left-top')
        super().__init__(align=align,
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
    def __init__(self, x, y, width, height, **kwargs):
        align = kwargs.pop('align', 'center')
        super().__init__(align=align,
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
    def __init__(self, x, y, radius, **kwargs):
        align = kwargs.pop('align', 'center')
        super().__init__(align=align,
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
    def __init__(self, x, y, radius, points, **kwargs):
        align = kwargs.pop('align', 'center')
        super().__init__(align=align,
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
    def __init__(self, x, y, radius, points, **kwargs):
        super().__init__(x, y, radius, points, **kwargs)
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
    def __init__(self, x1, y1, x2, y2, **kwargs):
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
    def __init__(self, *points, **kwargs):
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
    def __init__(self, x, y, width, height, startAngle, sweepAngle, **kwargs):
        align = kwargs.pop('align', 'center')
        super().__init__(align=align,
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
    def __init__(self, text, x, y, **kwargs):
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
    def __init__(self, path, x, y, **kwargs):
        align = kwargs.pop('align', 'center')
        super().__init__(align=align,
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
    def __init__(self, *shapes):
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
    if _renderer is None:
        _ensure_canvas()
    return _renderer


def drawRect(x, y, width, height, fill='black', border=None, borderWidth=2,
             opacity=100, rotateAngle=0, dashes=False, align='left-top',
             visible=True, roundness=0):
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
               opacity=100, rotateAngle=0, dashes=False, align='center', visible=True):
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
             opacity=100, rotateAngle=0, dashes=False, align='center', visible=True):
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
                       align='center', visible=True):
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
             visible=True, ratio=0.5):
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
              rotateAngle=0):
    if not visible:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    r.draw_label(str(text), float(x), float(y), fill=fill, size=size, font=font,
                 bold=bold, italic=italic, opacity=opacity, align=align,
                 rotateAngle=rotateAngle)


def drawLine(x1, y1, x2, y2, fill='black', lineWidth=2, opacity=100,
             dashes=False, visible=True):
    if not visible:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    r.draw_line(float(x1), float(y1), float(x2), float(y2), fill=fill,
                lineWidth=lineWidth, opacity=opacity, dashes=dashes)


def drawPolygon(*points, fill='black', border=None, borderWidth=2, opacity=100,
                rotateAngle=0, dashes=False, visible=True):
    if not visible or len(points) < 4:
        return
    r = _renderer_or_2d()
    if r is None:
        return
    r.draw_polygon([float(p) for p in points], fill=fill, border=border,
                   borderWidth=borderWidth, opacity=opacity,
                   rotateAngle=rotateAngle, dashes=dashes)


def drawArc(x, y, width, height, startAngle, sweepAngle, fill=None, border=None,
            borderWidth=2, opacity=100, dashes=False, align='center', visible=True):
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
              align='center', visible=True):
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
    def __init__(self, width=400, height=400, renderer=None, **kwargs):
        global _app
        self.width = width
        self.height = height
        self.background = 'white'
        self.stepsPerSecond = kwargs.get('stepsPerSecond', 30)
        self.paused = False
        self.renderer = renderer  # per-app renderer request (runApp wins)
        self._onAppStart = None
        self._onStep = None
        self._redrawAll = None
        _app = self
        _clear_shapes()


def runApp(width=400, height=400, stepsPerSecond=30, renderer=None,
         canvas=None, **kwargs):
    """Kept for `App(...)` + `runApp()` CMU shape. Full alias of run_app().

    Must keep the full run_app() signature: user code does
    `from scs import *`, which overwrites the entrypoint's
    `_user_ns['runApp']` (= run_app) with this module-level name.
    A narrow (width, height)-only wrapper here is what caused
    `runApp() got an unexpected keyword argument 'stepsPerSecond'`.
    """
    return run_app(width=width, height=height,
                   stepsPerSecond=stepsPerSecond, renderer=renderer,
                   canvas=canvas, **kwargs)


def cmu_graphics_run(app=None, width=400, height=400, stepsPerSecond=30,
                      renderer=None, canvas=None, **kwargs):
    if app is not None:
        try:
            width = getattr(app, 'width', width)
            height = getattr(app, 'height', height)
            stepsPerSecond = getattr(app, 'stepsPerSecond', stepsPerSecond)
            renderer = getattr(app, 'renderer', renderer)
        except Exception:
            pass
    return run_app(width=width, height=height,
                   stepsPerSecond=stepsPerSecond, renderer=renderer,
                   canvas=canvas, **kwargs)


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


def _pos(ev):
    canvas = _find_canvas()
    try:
        r = canvas.getBoundingClientRect()
        sx = canvas.width / r.width if r.width else 1
        sy = canvas.height / r.height if r.height else 1
        # Backing store is width*dpr; user coords are CSS pixels, so
        # divide by dpr to map backing-store scale back to CSS pixels.
        return ((ev.clientX - r.left) * sx / _dpr(),
                (ev.clientY - r.top) * sy / _dpr())
    except Exception:
        return (0, 0)


def _mp(ev):
    global _is_dragging
    _is_dragging = True
    try:
        _find_canvas().focus()
    except Exception:
        pass
    if _app is not None:
        _call('onMousePress', _app, *_pos(ev))


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
        for s in list(_shapes):
            try:
                draw_fn = getattr(s, 'draw', None)
                if draw_fn is not None:
                    draw_fn(r)
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
        _step()
        _render()
    except Exception:
        stop()


def _start_loop():
    global _app_timer
    stop()
    _frame()
    iv = int(1000 / _steps_per_second) if _steps_per_second > 0 else 33
    try:
        _app_timer = timer.set_interval(_frame, iv)
    except Exception:
        pass


def run_app(width=400, height=400, stepsPerSecond=30, renderer=None,
            canvas=None, **kwargs):
    """The initialiser. renderer: '2d' (default, backwards compat),
    'webgl2', 'webgpu', or 'auto' (WebGPU -> WebGL2 -> 2D).

    Also honours (in order): explicit arg > _pending_renderer from
    setRenderer() > ?renderer= URL param > SCS_CONFIG.renderer.
    """
    global _app, _canvas, _steps_per_second, _pending_renderer
    _refresh_user_funcs()
    _bind_events()
    stop()
    if canvas is not None:
        _canvas = canvas
    _steps_per_second = stepsPerSecond
    _size_canvas(width, height)
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

    kind = _resolve_renderer_kind(
        renderer or _pending_renderer or getattr(app, 'renderer', None))
    _pending_renderer = None

    def _fallback(exc_kind, err):
        # WebGPU/WebGL2 failed: walk down the chain, then start anyway.
        nxt = {'webgpu': 'webgl2', 'webgl2': '2d'}.get(exc_kind)
        if nxt is None:
            _debug_log('SCS renderer failed (%s): %s' % (exc_kind, err))
            return
        try:
            r = create_renderer(nxt, _find_canvas(), width, height)
            _activate_renderer(r, nxt)
            _start_loop()
        except Exception as e2:
            _fallback(nxt, e2)

    if kind == 'auto':
        # Try WebGPU async; on failure fall through to WebGL2 -> 2D.
        try:
            r = create_renderer('webgpu', _find_canvas(), width, height)
        except Exception:
            r = None
        if r is not None and getattr(r, '_init_error', None) is None:
            def _auto_ready():
                _activate_renderer(r, 'webgpu')
                _start_loop()

            def _auto_fail(err):
                _fallback('webgpu', err)

            r.on_ready = _auto_ready
            r.on_error = _auto_fail
            return  # loop starts from _auto_ready
        _fallback('webgpu', getattr(r, '_init_error', 'no WebGPU') if r else 'no WebGPU')
        return

    if kind == 'webgpu':
        try:
            r = create_renderer('webgpu', _find_canvas(), width, height)
        except Exception as e:
            _fallback('webgpu', e)
            return
        if getattr(r, '_init_error', None) is not None:
            _fallback('webgpu', r._init_error)
            return

        def _gpu_ready():
            _activate_renderer(r, 'webgpu')
            _start_loop()

        def _gpu_fail(err):
            _fallback('webgpu', err)

        r.on_ready = _gpu_ready
        r.on_error = _gpu_fail
        return  # loop starts from _gpu_ready

    try:
        r = create_renderer(kind, _find_canvas(), width, height)
    except Exception as e:
        _fallback(kind, e)
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
    global _presentation, _presentation_coordinator
    try:
        from scs_presentation import PresentationController, ResizeCoordinator
        container = canvas
        try:
            parent = getattr(canvas, 'parentElement', None)
            if parent is not None:
                container = parent
        except Exception:
            pass
        _presentation = PresentationController(canvas=canvas, container=container)
        def _apply(metrics):
            r = _renderer
            if r is not None and hasattr(r, 'apply_size'):
                try:
                    r.apply_size(metrics)
                except Exception:
                    pass
        _presentation_coordinator = ResizeCoordinator(_apply)
        try:
            _presentation.observe_resize(_presentation_coordinator)
        except Exception:
            pass
    except Exception:
        _presentation = None
        _presentation_coordinator = None


def _teardown_presentation():
    global _presentation, _presentation_coordinator
    try:
        if _presentation is not None:
            _presentation.dispose()
    except Exception:
        pass
    _presentation = None
    _presentation_coordinator = None


# [STRIPPED 70 bytes]
# Controller / Gamepad (scs_controller.py)
# [STRIPPED 70 bytes]

def getControllerManager():
    global _controller_manager
    if _controller_manager is None:
        try:
            from scs_controller import ControllerManager
            _controller_manager = ControllerManager()
        except Exception:
            _controller_manager = None
    return _controller_manager


def getGamepads():
    try:
        from browser import window
        gps = window.navigator.getGamepads()
        return list(gps) if gps is not None else []
    except Exception:
        mgr = getControllerManager()
        if mgr is not None:
            try:
                mgr.mark_blocked()
            except Exception:
                pass
        return []


def controllerFeedback(player, kind, intensity=1.0, duration_ms=100):
    try:
        mgr = getControllerManager()
        if mgr is None:
            return False
        ctrl = mgr.player_controller(player)
        if ctrl is None:
            return False
        return ctrl.feedback(kind, intensity, duration_ms)
    except Exception:
        return False


# [STRIPPED 70 bytes]
# Loader (scs_loader.py) -- see below for getAssetLoader etc.
# [STRIPPED 70 bytes]

def getAssetLoader():
    """Singleton AssetLoader (scs_loader). Stages are separate:
    fetch -> decode -> create runtime resource -> prepare."""
    global _asset_loader
    if _asset_loader is None:
        try:
            from scs_loader import AssetLoader
            _asset_loader = AssetLoader()
        except Exception:
            _asset_loader = None
    return _asset_loader


def loadAsset(source, kind='auto', options=None):
    """Load one asset through the staged pipeline. Returns an
    AssetHandle with a documented ownership contract, not a raw
    scene/texture/buffer. Promise stage is PREPARED (see scs_loader)."""
    loader = getAssetLoader()
    if loader is None:
        raise RuntimeError('Asset loader unavailable')
    return loader.load(source, kind=kind, options=options)


def loadGLB(source, options=None):
    return loadAsset(source, kind='glb', options=options)


def loadTexture(source, options=None):
    return loadAsset(source, kind='texture', options=options)


def loadAudio(source, options=None):
    return loadAsset(source, kind='audio', options=options)


# [STRIPPED 70 bytes]
# Splats (scs_splats.py) -- first-class primitive
# [STRIPPED 70 bytes]

def getSplatRenderer(backend='webgl2'):
    """Singleton splat renderer extension. WebGL raster + WebGPU
    compute behind the same boundary. Custom passes, shared camera /
    depth, explicit ordering."""
    global _splat_renderer
    if _splat_renderer is None:
        try:
            from scs_splats import WebGLSplatRenderer, WebGPUSplatRenderer
            _splat_renderer = WebGPUSplatRenderer() if backend == 'webgpu' \
                else WebGLSplatRenderer()
        except Exception:
            _splat_renderer = None
    return _splat_renderer


def createSplatSchema(sh_degree=0, relightable=False):
    """Versioned logical schema. Backends pack it; the schema is
    the contract, not any packed layout."""
    from scs_splats import SplatSchema
    s = SplatSchema(version=1, sh_degree=sh_degree)
    if relightable:
        s.add_relightable()
    s.validate()
    return s


def createSplatAsset(schema=None, name='splats'):
    """A splat asset: schema + chunks + hierarchy + appearance +
    proxies. Scene membership here; residency in ResidencyManager."""
    from scs_splats import SplatAsset
    return SplatAsset(schema or createSplatSchema(), name=name)


def loadSplatManifest(asset_id, schema, chunk_ids, coarse_chunk_id=None):
    """Chunked asset manifest + coarse representation before the
    whole asset is available."""
    from scs_splats import SplatAssetLoader
    return SplatAssetLoader().manifest(asset_id, schema, chunk_ids,
                                       coarse_chunk_id)


# Aliases the user namespace expects.
run = run_app
loop = run_app


# ----------------------------------------------------------------------
# App loading (was in index.html)
# ----------------------------------------------------------------------

def app_file():
    d = 'apps/app.py'
    try:
        v = _url_param('app')
        if not v:
            cfg_app = _config_value('app')
            if cfg_app:
                v = str(cfg_app)
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
    _user_ns['runApp'] = run_app
    _user_ns['run'] = run_app
    _user_ns['loop'] = run_app
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


def load():
    # JS loader may inject code directly (SCS.create({code: '...'})).
    code = _config_value('code')
    if code:
        exec_code(str(code), '<SCS.create code>')
        return
    t = app_file()
    url = _app_url(t)

    def ok(txt):
        if txt:
            exec_code(txt, t)

    def fail(e):
        _debug_log('SCS could not load %s: %s' % (url, e))

    try:
        window.fetch(url).then(lambda r: r.text().then(ok)).catch(fail)
    except Exception:
        pass


def boot():
    """Called from index.html / the JS loader. Binds events, loads the
    app (?app= / SCS_CONFIG), and starts it."""
    _bind_events()
    load()


main = boot
