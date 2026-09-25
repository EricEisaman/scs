"""
scs.py - Sigma Computer Science - CMU Graphics API shim for Brython
Version: 3.0.0 - EXACT CMU ALIGN LOGIC

Per https://academy.cs.cmu.edu/docs/ and
https://github.com/cmu-cs-academy/desktop-cmu-graphics/blob/main/cmu_graphics/shape_logic.py

CMU Spec:
  Rect(left, top, width, height, fill='black', border=None, borderWidth=2,
       opacity=100, rotateAngle=0, dashes=False, align='left-top', visible=True,
       roundness=0)
  Oval(centerX, centerY, width, height, align='center')
  Circle(centerX, centerY, radius, align='center')
  RegularPolygon(centerX, centerY, radius, points, align='center')
  Star(centerX, centerY, radius, points, ratio=0.5, align='center')
  Label(text, centerX, centerY, fill='black', size=12, font='arial',
        bold=False, italic=False, align='center')
  Line(x1,y1,x2,y2), Polygon(*points), Arc, Image, Group

Align: 9 positions, creation-time only (not mutable property)
  left-top    top    right-top
  left        center right
  left-bottom bottom right-bottom
Aliases: top-left=left-top, bottom-left=left-bottom, leftTop, rightBottom,
         center-left=left, top-center=top, etc.

CMU Implementation: x,y is interpreted according to align
  _resolve_bbox(x,y,w,h,align) -> left,top where:
    left = x - ox, top = y - oy
    ox = 0 for left, w/2 for center, w for right
    oy = 0 for top, h/2 for center, h for bottom
"""

from browser import window, document
import math

# ======================================================================
# ALIGN LOGIC - EXACT COPY FROM CMU desktop-cmu-graphics
# https://github.com/cmu-cs-academy/desktop-cmu-graphics/blob/main/cmu_graphics/shape_logic.py
# ======================================================================

# CMU's 9 aligns
_VALID_ALIGNS = {
    'left-top', 'top', 'right-top',
    'left', 'center', 'right',
    'left-bottom', 'bottom', 'right-bottom'
}

# Aliases map to canonical
_ALIGN_ALIASES = {
    'top-left': 'left-top',
    'top-right': 'right-top',
    'bottom-left': 'left-bottom',
    'bottom-right': 'right-bottom',
    'lefttop': 'left-top',
    'righttop': 'right-top',
    'leftbottom': 'left-bottom',
    'rightbottom': 'right-bottom',
    'topleft': 'left-top',
    'topright': 'right-top',
    'bottomleft': 'left-bottom',
    'bottomright': 'right-bottom',
    'centertop': 'top',
    'topcenter': 'top',
    'centerbottom': 'bottom',
    'bottomcenter': 'bottom',
    'centerleft': 'left',
    'leftcenter': 'left',
    'centerright': 'right',
    'rightcenter': 'right',
    'centercenter': 'center',
    'centre': 'center',
}

def _normalize_align(align):
    """
    Normalize align string to canonical 9 positions.
    CMU does: lower, strip, replace _ with -, handle aliases.
    """
    if not align:
        return 'center'
    a = str(align).strip().lower().replace('_', '-').replace(' ', '-')
    # Handle camelCase like leftTop -> left-top
    # Do simple replacement for known camelCases
    # Convert to lower kebab first
    # leftTop -> lefttop -> left-top via alias
    a_nospace = a.replace('-', '')
    if a_nospace in _ALIGN_ALIASES:
        return _ALIGN_ALIASES[a_nospace]
    if a in _ALIGN_ALIASES:
        return _ALIGN_ALIASES[a]
    if a in _VALID_ALIGNS:
        return a
    # Try to infer from substrings if still not valid
    # This handles weird inputs gracefully like CMU does
    has_left = 'left' in a
    has_right = 'right' in a
    has_top = 'top' in a
    has_bottom = 'bottom' in a
    has_center = 'center' in a or 'centre' in a
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
    # Default fallback per CMU: center for most shapes, left-top for Rect
    # Caller will provide appropriate default, so return center here
    return 'center'

def _get_align_offsets(align, width, height):
    """
    Given align and bbox width/height, return (ox, oy) offset of reference point
    inside bbox. This is the core of CMU's align logic.
    For Rect with align='left-top', ox=0, oy=0, so left=x, top=y
    For Rect with align='center', ox=w/2, oy=h/2, so left=x-w/2, top=y-h/2
    """
    a = _normalize_align(align)
    # Horizontal offset
    if a in ('left-top', 'left', 'left-bottom'):
        ox = 0
    elif a in ('right-top', 'right', 'right-bottom'):
        ox = width
    else:  # top, center, bottom
        ox = width / 2
    # Vertical offset
    if a in ('left-top', 'top', 'right-top'):
        oy = 0
    elif a in ('left-bottom', 'bottom', 'right-bottom'):
        oy = height
    else:  # left, center, right
        oy = height / 2
    return ox, oy

def _resolve_bbox(x, y, width, height, align):
    """
    Given reference point (x,y), bbox size (w,h), and align,
    return (left, top) of bbox. This is how CMU interprets x,y.
    left = x - ox
    top = y - oy
    where ox,oy from _get_align_offsets
    """
    ox, oy = _get_align_offsets(align, width, height)
    return x - ox, y - oy

# ======================================================================
# CANVAS SETUP - Brython specific
# ======================================================================
_canvas = None
_ctx = None
_app = None
_shapes = []  # list of all shapes for z-order
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

def _clear_shapes():
    global _shapes
    _shapes = []

# ======================================================================
# BASE SHAPE CLASS
# ======================================================================
class _BaseShape:
    """
    Base for all shapes. Stores _left,_top,_width,_height as actual bbox.
    align is stored as _align but is creation-time only, not mutable.
    Per CMU docs, you cannot set shape.align after creation.
    """
    def __init__(self, **kwargs):
        # align is creation-time only - store privately
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

    # left, top, right, bottom, centerX, centerY, width, height
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
        # Keep center
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
# RECT - default align left-top per CMU
# ======================================================================
class Rect(_BaseShape):
    """
    Rect(left, top, width, height, align='left-top')
    x,y is left,top when align='left-top' (default)
    x,y is center when align='center'
    """
    def __init__(self, x, y, width, height, **kwargs):
        # Extract align before passing to base - creation-time only
        align = kwargs.pop('align', 'left-top')
        # Remove align from kwargs for base so it doesn't get double-processed
        base_kwargs = {k: v for k, v in kwargs.items() if k != 'align'}
        super().__init__(align=align, **base_kwargs)
        self._width = float(width)
        self._height = float(height)
        # Resolve bbox: left,top from x,y,w,h,align
        l, t = _resolve_bbox(float(x), float(y), float(width), float(height), align)
        self._left = l
        self._top = t
        self.roundness = kwargs.get('roundness', 0)
        _shapes.append(self)

# ======================================================================
# OVAL - default center
# ======================================================================
class Oval(_BaseShape):
    """
    Oval(centerX, centerY, width, height, align='center')
    """
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
    """
    Circle(centerX, centerY, radius, align='center')
    """
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

# ======================================================================
# REGULAR POLYGON - default center
# ======================================================================
class RegularPolygon(_BaseShape):
    """
    RegularPolygon(centerX, centerY, radius, points, align='center')
    """
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
    def radius(self):
        return self._radius

    @radius.setter
    def radius(self, v):
        self._radius = float(v)
        self._width = self._height = float(v) * 2

# ======================================================================
# STAR
# ======================================================================
class Star(RegularPolygon):
    """
    Star(centerX, centerY, radius, points, ratio=0.5, align='center')
    """
    def __init__(self, x, y, radius, points, **kwargs):
        super().__init__(x, y, radius, points, **kwargs)
        self.ratio = kwargs.get('ratio', 0.5)

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
    @property
    def centerY(self): return self._top + self._height / 2

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
# LABEL
# ======================================================================
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
        self._x = float(x)
        self._y = float(y)
        self._width = len(self.text) * self.size * 0.6
        self._height = float(self.size)
        _shapes.append(self)

    @property
    def centerX(self): return self._x
    @centerX.setter
    def centerX(self, v): self._x = float(v)
    @property
    def centerY(self): return self._y
    @centerY.setter
    def centerY(self, v): self._y = float(v)
    @property
    def left(self): return self._x
    @property
    def top(self): return self._y

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

    @property
    def centerX(self): return self._left + self._width / 2
    @centerX.setter
    def centerX(self, v): self._left = float(v) - self._width / 2
    @property
    def centerY(self): return self._top + self._height / 2
    @centerY.setter
    def centerY(self, v): self._top = float(v) - self._height / 2

# ======================================================================
# GROUP
# ======================================================================
class Group:
    def __init__(self, *shapes):
        self.shapes = list(shapes)
        self.visible = True
        self.opacity = 100
        self.rotateAngle = 0
        self._left = 0
        self._top = 0
        if shapes:
            try:
                self._left = min([s.left for s in shapes if hasattr(s, 'left')])
                self._top = min([s.top for s in shapes if hasattr(s, 'top')])
            except:
                pass
        _shapes.append(self)

    @property
    def left(self): return self._left
    @property
    def top(self): return self._top
    @property
    def centerX(self):
        if not self.shapes: return 0
        return sum([s.centerX for s in self.shapes if hasattr(s, 'centerX')]) / len(self.shapes)
    @centerX.setter
    def centerX(self, v):
        dx = float(v) - self.centerX
        for s in self.shapes:
            if hasattr(s, 'centerX'): s.centerX += dx
    @property
    def centerY(self):
        if not self.shapes: return 0
        return sum([s.centerY for s in self.shapes if hasattr(s, 'centerY')]) / len(self.shapes)
    @centerY.setter
    def centerY(self, v):
        dy = float(v) - self.centerY
        for s in self.shapes:
            if hasattr(s, 'centerY'): s.centerY += dy

# ======================================================================
# DRAW FUNCTIONS - EXACT CMU LOGIC
# ======================================================================
def drawRect(x, y, width, height, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='left-top', visible=True, roundness=0):
    _ensure_canvas()
    if not visible: return
    left, top = _resolve_bbox(float(x), float(y), float(width), float(height), align)
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
                if dashes: ctx.setLineDash([6, 3])
                ctx.stroke()
        else:
            if fill is not None:
                ctx.fillStyle = fill if isinstance(fill, str) else str(fill)
                ctx.fillRect(left, top, width, height)
            if border is not None:
                ctx.strokeStyle = border if isinstance(border, str) else str(border)
                ctx.lineWidth = borderWidth
                if dashes: ctx.setLineDash([6, 3])
                ctx.strokeRect(left, top, width, height)
    finally:
        ctx.restore()

def drawCircle(x, y, radius, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible: return
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
            if dashes: ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawOval(x, y, width, height, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible: return
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
            if dashes: ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawRegularPolygon(x, y, radius, points, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible: return
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
            if dashes: ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawStar(x, y, radius, points, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True, ratio=0.5):
    _ensure_canvas()
    if not visible: return
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
            if dashes: ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawLabel(text, x, y, fill='black', size=12, font='arial', bold=False, italic=False, opacity=100, align='center', visible=True, rotateAngle=0):
    _ensure_canvas()
    if not visible: return
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        ctx.fillStyle = fill if fill else 'black'
        style = ''
        if italic: style += 'italic '
        if bold: style += 'bold '
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
    if not visible: return
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity / 100
        ctx.strokeStyle = fill if fill else 'black'
        ctx.lineWidth = lineWidth
        if dashes: ctx.setLineDash([6, 3])
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
    finally:
        ctx.restore()

def drawPolygon(*points, fill='black', border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, visible=True):
    _ensure_canvas()
    if not visible or len(points) < 4: return
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
            if dashes: ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawArc(x, y, width, height, startAngle, sweepAngle, fill=None, border=None, borderWidth=2, opacity=100, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible: return
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
            if dashes: ctx.setLineDash([6, 3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawImage(path, x, y, width=None, height=None, opacity=100, rotateAngle=0, align='center', visible=True):
    _ensure_canvas()
    if not visible: return
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

# ---------- Sound ----------
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

# ---------- App ----------
class App:
    def __init__(self, width=400, height=400):
        global _app
        self.width = width
        self.height = height
        self.background = 'white'
        self.stepsPerSecond = 30
        self.paused = False
        self._onAppStart = None
        self._onStep = None
        self._redrawAll = None
        _app = self
        _clear_shapes()

def runApp(width=400, height=400):
    pass

def cmu_graphics_run(app=None, width=400, height=400):
    runApp(width, height)

# Compatibility aliases
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
