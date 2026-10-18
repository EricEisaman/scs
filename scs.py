"""
scs.py - Sigma Computer Science - CMU Graphics API shim for Brython
Version: 3.1.0 - CMU-compatible + SCS mutable-align extension

Fixes the ?app= vs sandbox offset bug:

Root cause in the screenshots:
  Rect(0,0,W,H, align='left-top') was created, but old/new align handling
  fell back to 'center'. Centered at (0,0) only the bottom-right quadrant
  (W/2 x H/2) is visible at top-left. That's exactly the white half-grid
  and black panels offset into the graph in ?app=graphing_lines.

Changes:
  - Single canonical _VALID_ALIGNS + _ALIGN_ALIASES (no duplicates)
  - _normalize_align handles 'left-top', 'left_top', 'leftTop', 'top-left', etc.
  - _resolve_bbox is pure (no console.log spam)
  - _BaseShape: x,y now mean "reference point per align" like CMU
    left = x - ox(align,W), top = y - oy(align,H)
  - align is now a mutable property (SCS extension) that preserves the
    reference point: changing align moves left/top so that x,y stays put.
    This keeps CMU creation-time behavior but doesn't break apps that do
    shape.align = '...' after creation.
  - Rect default align='left-top', Oval/Circle/Star/etc default 'center'
    per https://academy.cs.cmu.edu/docs/ and CMU desktop implementation
  - Group: computes bbox from children, removes children from global _shapes
    to avoid double-draw, moves children when group moves, supports align
    mutation.
  - Canvas auto-resizes to App width/height.
  - _clear_shapes called on App init.
"""

from browser import window, document
import math

# ======================================================================
# ALIGN LOGIC - CMU spec + aliases
# ======================================================================

_VALID_ALIGNS = {
    'left-top', 'top', 'right-top',
    'left', 'center', 'right',
    'left-bottom', 'bottom', 'right-bottom'
}

_ALIGN_ALIASES = {
    # hyphenless / camelCase / reversed
    'lefttop': 'left-top',
    'topleft': 'left-top',
    'top-left': 'left-top',
    'righttop': 'right-top',
    'topright': 'right-top',
    'top-right': 'right-top',
    'leftbottom': 'left-bottom',
    'bottomleft': 'left-bottom',
    'bottom-left': 'left-bottom',
    'rightbottom': 'right-bottom',
    'bottomright': 'right-bottom',
    'bottom-right': 'right-bottom',
    # center variants
    'topcenter': 'top',
    'centertop': 'top',
    'top-center': 'top',
    'center-top': 'top',
    'bottomcenter': 'bottom',
    'centerbottom': 'bottom',
    'bottom-center': 'bottom',
    'center-bottom': 'bottom',
    'leftcenter': 'left',
    'centerleft': 'left',
    'left-center': 'left',
    'center-left': 'left',
    'rightcenter': 'right',
    'centerright': 'right',
    'right-center': 'right',
    'center-right': 'right',
    'centercenter': 'center',
    'centre': 'center',
    'middle': 'center',
}

def _normalize_align(align):
    if not align:
        return 'center'
    s = str(align).strip()
    if not s:
        return 'center'
    lower = s.lower()
    # replace _ and spaces with -
    norm_dash = lower.replace('_', '-').replace(' ', '-')
    nospace = norm_dash.replace('-', '')
    # 1) direct alias lookup on nospace (handles leftTop, LeftTop, etc.)
    if nospace in _ALIGN_ALIASES:
        return _ALIGN_ALIASES[nospace]
    # 2) direct alias with dashes
    if norm_dash in _ALIGN_ALIASES:
        return _ALIGN_ALIASES[norm_dash]
    # 3) canonical
    if norm_dash in _VALID_ALIGNS:
        return norm_dash
    if nospace in _VALID_ALIGNS:
        return nospace  # shouldn't happen but safe
    # 4) substring fallback like CMU desktop does
    has_left = 'left' in lower
    has_right = 'right' in lower
    has_top = 'top' in lower
    has_bottom = 'bottom' in lower
    has_center = 'center' in lower or 'middle' in lower or 'centre' in lower
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
    if has_center:
        return 'center'
    return 'center'

def _get_align_offsets(align, width, height):
    a = _normalize_align(align)
    # horizontal
    if a in ('left-top', 'left', 'left-bottom'):
        ox = 0
    elif a in ('right-top', 'right', 'right-bottom'):
        ox = width
    else:  # top, bottom, center
        ox = width / 2
    # vertical
    if a in ('left-top', 'top', 'right-top'):
        oy = 0
    elif a in ('left-bottom', 'bottom', 'right-bottom'):
        oy = height
    else:  # left, right, center
        oy = height / 2
    return ox, oy

def _resolve_bbox(x, y, width, height, align):
    """CMU: given reference (x,y), size, align -> (left,top)"""
    ox, oy = _get_align_offsets(align, width, height)
    return x - ox, y - oy

# ======================================================================
# CANVAS
# ======================================================================
_canvas = None
_ctx = None
_app = None
_shapes = []
_image_cache = {}

def _ensure_canvas():
    global _canvas, _ctx
    if _canvas is None:
        _canvas = document.getElementById('canvas')
        if not _canvas:
            _canvas = document.createElement('canvas')
            _canvas.id = 'canvas'
            _canvas.width = 800
            _canvas.height = 600
            _canvas.style.border = '1px solid #ccc'
            document.body.appendChild(_canvas)
        _ctx = _canvas.getContext('2d')
    # sync with app size if app exists
    if _app is not None:
        try:
            if _canvas.width != int(_app.width) or _canvas.height != int(_app.height):
                _canvas.width = int(_app.width)
                _canvas.height = int(_app.height)
        except:
            pass

def _clear_shapes():
    global _shapes
    _shapes = []

# ======================================================================
# BASE SHAPE - now with mutable align + x,y reference point
# ======================================================================
class _BaseShape:
    """
    Stores bbox as _left,_top,_width,_height.
    x,y are reference point per current align:
      x = left + ox(align,W)
      y = top + oy(align,H)
    Changing align preserves x,y (SCS mutable extension).
    Changing x,y moves left/top.
    """
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

    # ---- align mutable ----
    @property
    def align(self):
        return self._align

    @align.setter
    def align(self, new_align):
        new_align = _normalize_align(new_align)
        if new_align == self._align:
            return
        # preserve reference point
        ox_old, oy_old = _get_align_offsets(self._align, self._width, self._height)
        ref_x = self._left + ox_old
        ref_y = self._top + oy_old
        ox_new, oy_new = _get_align_offsets(new_align, self._width, self._height)
        self._left = ref_x - ox_new
        self._top = ref_y - oy_new
        self._align = new_align

    # ---- reference point x,y ----
    @property
    def x(self):
        ox, _ = _get_align_offsets(self._align, self._width, self._height)
        return self._left + ox

    @x.setter
    def x(self, v):
        ox, _ = _get_align_offsets(self._align, self._width, self._height)
        self._left = float(v) - ox

    @property
    def y(self):
        _, oy = _get_align_offsets(self._align, self._width, self._height)
        return self._top + oy

    @y.setter
    def y(self, v):
        _, oy = _get_align_offsets(self._align, self._width, self._height)
        self._top = float(v) - oy

    # ---- bbox properties ----
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
        # SCS extension: keep center (CMU keeps center for width/height)
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
        global _shapes
        if self in _shapes:
            _shapes.remove(self)
            _shapes.append(self)

    def toBack(self):
        global _shapes
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
        except:
            return False

# ======================================================================
# RECT - default left-top per CMU
# ======================================================================
class Rect(_BaseShape):
    def __init__(self, x, y, width, height, **kwargs):
        align = kwargs.pop('align', 'left-top')
        base_kwargs = {k: v for k, v in kwargs.items() if k != 'align'}
        super().__init__(align=align, **base_kwargs)
        self._width = float(width)
        self._height = float(height)
        l, t = _resolve_bbox(float(x), float(y), float(width), float(height), align)
        self._left = l
        self._top = t
        self.roundness = kwargs.get('roundness', 0)
        # if part of a group, don't double-add (Group will handle)
        _shapes.append(self)

# ======================================================================
# OVAL - default center
# ======================================================================
class Oval(_BaseShape):
    def __init__(self, x, y, width, height, **kwargs):
        align = kwargs.pop('align', 'center')
        base_kwargs = {k: v for k, v in kwargs.items() if k != 'align'}
        super().__init__(align=align, **base_kwargs)
        self._width = float(width)
        self._height = float(height)
        l, t = _resolve_bbox(float(x), float(y), float(width), float(height), align)
        self._left = l
        self._top = t
        _shapes.append(self)

# ======================================================================
# CIRCLE - default center
# ======================================================================
class Circle(_BaseShape):
    def __init__(self, x, y, radius, **kwargs):
        align = kwargs.pop('align', 'center')
        base_kwargs = {k: v for k, v in kwargs.items() if k != 'align'}
        super().__init__(align=align, **base_kwargs)
        self._radius = float(radius)
        w = h = float(radius) * 2
        self._width = w
        self._height = h
        l, t = _resolve_bbox(float(x), float(y), w, h, align)
        self._left = l
        self._top = t
        _shapes.append(self)

    @property
    def radius(self):
        return self._radius
    @radius.setter
    def radius(self, v):
        cx = self.centerX
        cy = self.centerY
        self._radius = float(v)
        self._width = self._height = float(v) * 2
        self.centerX = cx
        self.centerY = cy

# ======================================================================
# REGULAR POLYGON - default center
# ======================================================================
class RegularPolygon(_BaseShape):
    def __init__(self, x, y, radius, points, **kwargs):
        align = kwargs.pop('align', 'center')
        base_kwargs = {k: v for k, v in kwargs.items() if k != 'align'}
        super().__init__(align=align, **base_kwargs)
        self._radius = float(radius)
        self.points = int(points)
        w = h = float(radius) * 2
        self._width = w
        self._height = h
        l, t = _resolve_bbox(float(x), float(y), w, h, align)
        self._left = l
        self._top = t
        _shapes.append(self)

    @property
    def radius(self):
        return self._radius
    @radius.setter
    def radius(self, v):
        cx = self.centerX
        cy = self.centerY
        self._radius = float(v)
        self._width = self._height = float(v) * 2
        self.centerX = cx
        self.centerY = cy

class Star(RegularPolygon):
    def __init__(self, x, y, radius, points, **kwargs):
        self.ratio = kwargs.get('ratio', 0.5)
        super().__init__(x, y, radius, points, **kwargs)

# ======================================================================
# LINE
# ======================================================================
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
        self._group = None
        _shapes.append(self)

    @property
    def left(self): return min(self.x1, self.x2)
    @property
    def right(self): return max(self.x1, self.x2)
    @property
    def top(self): return min(self.y1, self.y2)
    @property
    def bottom(self): return max(self.y1, self.y2)
    @property
    def centerX(self): return (self.x1 + self.x2) / 2
    @centerX.setter
    def centerX(self, v):
        dx = float(v) - self.centerX
        self.x1 += dx
        self.x2 += dx
    @property
    def centerY(self): return (self.y1 + self.y2) / 2
    @centerY.setter
    def centerY(self, v):
        dy = float(v) - self.centerY
        self.y1 += dy
        self.y2 += dy
    def toFront(self):
        global _shapes
        if self in _shapes:
            _shapes.remove(self)
            _shapes.append(self)
    def toBack(self):
        global _shapes
        if self in _shapes:
            _shapes.remove(self)
            _shapes.insert(0, self)

# ======================================================================
# POLYGON
# ======================================================================
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
        self._group = None
        xs = self.points[0::2]
        ys = self.points[1::2]
        self._left = min(xs) if xs else 0
        self._top = min(ys) if ys else 0
        self._width = (max(xs) - min(xs)) if xs else 0
        self._height = (max(ys) - min(ys)) if ys else 0
        _shapes.append(self)
    @property
    def left(self): return self._left
    @property
    def right(self): return self._left + self._width
    @property
    def top(self): return self._top
    @property
    def bottom(self): return self._top + self._height
    @property
    def centerX(self): return self._left + self._width / 2
    @centerX.setter
    def centerX(self, v):
        dx = float(v) - self.centerX
        self._left += dx
        self.points = [p + dx if i % 2 == 0 else p for i, p in enumerate(self.points)]
    @property
    def centerY(self): return self._top + self._height / 2
    @centerY.setter
    def centerY(self, v):
        dy = float(v) - self.centerY
        self._top += dy
        self.points = [p + dy if i % 2 == 1 else p for i, p in enumerate(self.points)]

# ======================================================================
# ARC
# ======================================================================
class Arc(_BaseShape):
    def __init__(self, x, y, width, height, startAngle, sweepAngle, **kwargs):
        align = kwargs.pop('align', 'center')
        base_kwargs = {k: v for k, v in kwargs.items() if k != 'align'}
        super().__init__(align=align, **base_kwargs)
        self._width = float(width)
        self._height = float(height)
        l, t = _resolve_bbox(float(x), float(y), float(width), float(height), align)
        self._left = l
        self._top = t
        self.startAngle = float(startAngle)
        self.sweepAngle = float(sweepAngle)
        _shapes.append(self)

# ======================================================================
# LABEL - uses text alignment for drawing, but bbox for hits
# ======================================================================
class Label(_BaseShape):
    def __init__(self, text, x, y, **kwargs):
        align = kwargs.pop('align', 'center')
        # Label stores reference point as _x,_y for canvas textAlign
        super().__init__(align=align, **kwargs)
        self.text = str(text)
        self.size = kwargs.get('size', 12)
        self.font = kwargs.get('font', 'arial')
        self.bold = kwargs.get('bold', False)
        self.italic = kwargs.get('italic', False)
        # approximate metrics
        self._width = len(self.text) * self.size * 0.6
        self._height = float(self.size)
        l, t = _resolve_bbox(float(x), float(y), self._width, self._height, align)
        self._left = l
        self._top = t
        # also keep ref for drawLabel
        self._ref_x = float(x)
        self._ref_y = float(y)
        _shapes.append(self)

    # x,y for Label should track ref, not left
    @property
    def x(self):
        return self._ref_x
    @x.setter
    def x(self, v):
        dx = float(v) - self._ref_x
        self._ref_x = float(v)
        self._left += dx

    @property
    def y(self):
        return self._ref_y
    @y.setter
    def y(self, v):
        dy = float(v) - self._ref_y
        self._ref_y = float(v)
        self._top += dy

# ======================================================================
# IMAGE
# ======================================================================
class Image(_BaseShape):
    def __init__(self, path, x, y, **kwargs):
        align = kwargs.pop('align', 'center')
        base_kwargs = {k: v for k, v in kwargs.items() if k != 'align'}
        super().__init__(align=align, **base_kwargs)
        self.path = path
        self._width = float(kwargs.get('width', 100))
        self._height = float(kwargs.get('height', 100))
        l, t = _resolve_bbox(float(x), float(y), self._width, self._height, align)
        self._left = l
        self._top = t
        self._img = None
        try:
            img = window.Image.new()
            img.src = path
            self._img = img
            _image_cache[path] = img
        except:
            pass
        _shapes.append(self)

# ======================================================================
# GROUP - fixed to avoid double-draw offset
# ======================================================================
class Group(_BaseShape):
    def __init__(self, *shapes, **kwargs):
        align = kwargs.pop('align', 'left-top')
        super().__init__(align=align, **kwargs)
        # remove children from global list so they only draw via group
        global _shapes
        self.shapes = []
        for s in shapes:
            if s in _shapes:
                _shapes.remove(s)
            self.shapes.append(s)
            try:
                s._group = self
            except:
                pass
        self._recalc_bbox()
        _shapes.append(self)

    def _recalc_bbox(self):
        if not self.shapes:
            self._left = 0
            self._top = 0
            self._width = 0
            self._height = 0
            return
        try:
            lefts = [s.left for s in self.shapes if hasattr(s, 'left')]
            tops = [s.top for s in self.shapes if hasattr(s, 'top')]
            rights = [s.right for s in self.shapes if hasattr(s, 'right')]
            bottoms = [s.bottom for s in self.shapes if hasattr(s, 'bottom')]
            if lefts and rights and tops and bottoms:
                self._left = min(lefts)
                self._top = min(tops)
                self._width = max(rights) - self._left
                self._height = max(bottoms) - self._top
        except:
            pass

    # moving group moves children
    @property
    def left(self):
        return self._left
    @left.setter
    def left(self, v):
        dx = float(v) - self._left
        self._left = float(v)
        for s in self.shapes:
            if hasattr(s, 'left'):
                s.left += dx

    @property
    def top(self):
        return self._top
    @top.setter
    def top(self, v):
        dy = float(v) - self._top
        self._top = float(v)
        for s in self.shapes:
            if hasattr(s, 'top'):
                s.top += dy

    @property
    def centerX(self):
        self._recalc_bbox()
        return self._left + self._width / 2
    @centerX.setter
    def centerX(self, v):
        dx = float(v) - self.centerX
        self.left = self._left + dx

    @property
    def centerY(self):
        self._recalc_bbox()
        return self._top + self._height / 2
    @centerY.setter
    def centerY(self, v):
        dy = float(v) - self.centerY
        self.top = self._top + dy

    def add(self, shape):
        global _shapes
        if shape in _shapes:
            _shapes.remove(shape)
        self.shapes.append(shape)
        try:
            shape._group = self
        except:
            pass
        self._recalc_bbox()

    def remove(self, shape):
        if shape in self.shapes:
            self.shapes.remove(shape)
            _shapes.append(shape)
            try:
                shape._group = None
            except:
                pass
            self._recalc_bbox()

    # align mutation for group preserves ref point too
    @property
    def align(self):
        return self._align
    @align.setter
    def align(self, new_align):
        new_align = _normalize_align(new_align)
        if new_align == self._align:
            return
        ox_old, oy_old = _get_align_offsets(self._align, self._width, self._height)
        ref_x = self._left + ox_old
        ref_y = self._top + oy_old
        ox_new, oy_new = _get_align_offsets(new_align, self._width, self._height)
        dx = (ref_x - ox_new) - self._left
        dy = (ref_y - oy_new) - self._top
        self._left = ref_x - ox_new
        self._top = ref_y - oy_new
        for s in self.shapes:
            if hasattr(s, 'left'):
                s.left += dx
            if hasattr(s, 'top'):
                s.top += dy
        self._align = new_align

# ======================================================================
# DRAW FUNCTIONS
# ======================================================================
def drawRect(x, y, width, height, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='left-top', visible=True, roundness=0):
    _ensure_canvas()
    if not visible:
        return
    left, top = _resolve_bbox(float(x), float(y), float(width), float(height), _normalize_align(align))
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        if rotateAngle != 0:
            cx = left + width / 2
            cy = top + height / 2
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-cx, -cy)
        if roundness > 0:
            r = min(roundness, min(width, height) / 2)
            ctx.beginPath()
            ctx.moveTo(left + r, top)
            ctx.arcTo(left + width, top, left + width, top + height, r)
            ctx.arcTo(left + width, top + height, left, top + height, r)
            ctx.arcTo(left, top + height, left, top, r)
            ctx.arcTo(left, top, left + width, top, r)
            ctx.closePath()
            if fill is not None:
                ctx.fillStyle = fill if isinstance(fill, str) else str(fill)
                ctx.fill()
            if border is not None:
                ctx.strokeStyle = border if isinstance(border, str) else str(border)
                ctx.lineWidth = borderWidth
                if dashes:
                    ctx.setLineDash([6, 3])
                ctx.stroke()
        else:
            if fill is not None:
                ctx.fillStyle = fill if isinstance(fill, str) else str(fill)
                ctx.fillRect(left, top, width, height)
            if border is not None:
                ctx.strokeStyle = border if isinstance(border, str) else str(border)
                ctx.lineWidth = borderWidth
                if dashes:
                    ctx.setLineDash([6, 3])
                ctx.strokeRect(left, top, width, height)
    finally:
        ctx.restore()

def drawCircle(x, y, radius, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible:
        return
    w = h = float(radius) * 2
    left, top = _resolve_bbox(float(x), float(y), w, h, align)
    cx = left + radius
    cy = top + radius
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        if rotateAngle != 0:
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-cx, -cy)
        ctx.beginPath()
        ctx.arc(cx, cy, radius, 0, 2 * math.pi)
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill, str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border, str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawOval(x, y, width, height, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible:
        return
    left, top = _resolve_bbox(float(x), float(y), float(width), float(height), align)
    cx = left + width / 2
    cy = top + height / 2
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        if rotateAngle != 0:
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-cx, -cy)
        ctx.beginPath()
        ctx.ellipse(cx, cy, width / 2, height / 2, 0, 0, 2 * math.pi)
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill, str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border, str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawRegularPolygon(x, y, radius, points, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible:
        return
    w = h = float(radius) * 2
    left, top = _resolve_bbox(float(x), float(y), w, h, align)
    cx = left + radius
    cy = top + radius
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        if rotateAngle != 0:
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-cx, -cy)
        ctx.beginPath()
        for i in range(int(points)):
            ang = 2 * math.pi * i / points - math.pi / 2
            px = cx + radius * math.cos(ang)
            py = cy + radius * math.sin(ang)
            if i == 0:
                ctx.moveTo(px, py)
            else:
                ctx.lineTo(px, py)
        ctx.closePath()
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill, str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border, str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawStar(x, y, radius, points, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True, ratio=0.5):
    _ensure_canvas()
    if not visible:
        return
    w = h = float(radius) * 2
    left, top = _resolve_bbox(float(x), float(y), w, h, align)
    cx = left + radius
    cy = top + radius
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        if rotateAngle != 0:
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-cx, -cy)
        ctx.beginPath()
        for i in range(int(points) * 2):
            r = radius if i % 2 == 0 else radius * ratio
            ang = math.pi * i / points - math.pi / 2
            px = cx + r * math.cos(ang)
            py = cy + r * math.sin(ang)
            if i == 0:
                ctx.moveTo(px, py)
            else:
                ctx.lineTo(px, py)
        ctx.closePath()
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill, str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border, str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawLabel(text, x, y, fill='black', size=12, font='arial', bold=False, italic=False, opacity=100, align='center', visible=True, rotateAngle=0):
    _ensure_canvas()
    if not visible:
        return
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        ctx.fillStyle = fill if fill else 'black'
        style = ''
        if italic:
            style += 'italic '
        if bold:
            style += 'bold '
        ctx.font = f"{style}{size}px {font}"
        a = _normalize_align(align)
        if 'left' in a:
            ctx.textAlign = 'left'
        elif 'right' in a:
            ctx.textAlign = 'right'
        else:
            ctx.textAlign = 'center'
        if 'top' in a:
            ctx.textBaseline = 'top'
        elif 'bottom' in a:
            ctx.textBaseline = 'bottom'
        else:
            ctx.textBaseline = 'middle'
        if rotateAngle != 0:
            ctx.translate(x, y)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-x, -y)
        ctx.fillText(str(text), x, y)
    finally:
        ctx.restore()

def drawLine(x1, y1, x2, y2, fill='black', lineWidth=2, opacity=100, dashes=False, visible=True):
    _ensure_canvas()
    if not visible:
        return
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        ctx.strokeStyle = fill if fill else 'black'
        ctx.lineWidth = lineWidth
        if dashes:
            ctx.setLineDash([6, 3])
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
    finally:
        ctx.restore()

def drawPolygon(*points, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, visible=True):
    _ensure_canvas()
    if not visible or len(points) < 4:
        return
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        ctx.beginPath()
        ctx.moveTo(points[0], points[1])
        for i in range(2, len(points), 2):
            ctx.lineTo(points[i], points[i+1])
        ctx.closePath()
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill, str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border, str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawArc(x, y, width, height, startAngle, sweepAngle, fill=None, border=None, borderWidth=2, opacity=100, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible:
        return
    left, top = _resolve_bbox(float(x), float(y), float(width), float(height), align)
    cx = left + width / 2
    cy = top + height / 2
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        ctx.beginPath()
        start = math.radians(startAngle)
        end = math.radians(startAngle + sweepAngle)
        ctx.ellipse(cx, cy, width / 2, height / 2, 0, start, end)
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill, str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border, str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawImage(path, x, y, width=None, height=None, opacity=100, rotateAngle=0, align='center', visible=True):
    _ensure_canvas()
    if not visible:
        return
    ctx = _ctx
    img = _image_cache.get(path)
    if not img:
        try:
            img = window.Image.new()
            img.src = path
            _image_cache[path] = img
        except:
            return
    w = width if width is not None else (img.width if hasattr(img, 'width') else 100)
    h = height if height is not None else (img.height if hasattr(img, 'height') else 100)
    left, top = _resolve_bbox(float(x), float(y), float(w), float(h), align)
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        if rotateAngle != 0:
            cx = left + w / 2
            cy = top + h / 2
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-cx, -cy)
        try:
            ctx.drawImage(img, left, top, w, h)
        except:
            pass
    finally:
        ctx.restore()

# ---------- Utilities ----------
def rgb(r, g, b):
    return f"rgb({int(r)},{int(g)},{int(b)})"

def gradient(*colors, start='left-top'):
    return colors[0] if colors else 'black'

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
    import random
    return random.randrange(a) if b is None else random.randrange(a, b)

def randint(a, b):
    import random
    return random.randint(a, b)

def random(a=None, b=None):
    import random
    if a is None:
        return random.random()
    if b is None:
        return random.random() * a
    return random.uniform(a, b)

class Sound:
    def __init__(self, path):
        self.path = path
        self._audio = None
        try:
            self._audio = window.Audio.new(path)
        except:
            pass
    def play(self, loop=False, restart=False):
        try:
            if self._audio:
                self._audio.loop = loop
                if restart:
                    self._audio.currentTime = 0
                self._audio.play()
        except:
            pass
    def pause(self):
        try:
            if self._audio:
                self._audio.pause()
        except:
            pass

class App:
    def __init__(self, width=400, height=400):
        global _app
        self.width = width
        self.height = height
        self.background = 'white'
        self.stepsPerSecond = 30
        self.paused = False
        _app = self
        _clear_shapes()
        _ensure_canvas()

def runApp(width=400, height=400):
    pass

def cmu_graphics_run(app=None, width=400, height=400):
    runApp(width, height)

# Aliases
Rect = Rect
Oval = Oval
Circle = Circle
RegularPolygon = RegularPolygon
Star = Star
Line = Line
Polygon = Polygon
Label = Label
Arc = Arc
Group = Group
Image = Image
