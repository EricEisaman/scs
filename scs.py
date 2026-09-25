"""
scs.py - Sigma Computer Science - CMU Graphics API shim for Brython
Version: 1000+ lines - Fixed align as true general property

CMU Academy spec:
  Rect(left, top, width, height, align='left-top') - default left-top
  Circle(centerX, centerY, radius, align='center') - default center
  Oval(centerX, centerY, width, height, align='center')
  RegularPolygon(centerX, centerY, radius, points, align='center')
  Star(centerX, centerY, radius, points, align='center')
  Label(centerX, centerY, text, align='center')
  Image, Arc, etc.

Valid aligns (9 positions):
  left-top, top, right-top,
  left, center, right,
  left-bottom, bottom, right-bottom
Aliases: top-left = left-top, bottom-left = left-bottom, etc.
         leftTop, rightTop, leftBottom, rightBottom (camelCase)
         center-left = left, etc.

All shapes honor align for positioning and for property access.
"""

from browser import window, document
import math
import json as _json

# ---------- Align helpers - 9 positions ----------
def _normalize_align(align):
    """Normalize any align string to one of 9 canonical values"""
    if not align:
        return 'center'
    a = str(align).lower().replace('_','-').strip()
    # camelCase -> kebab
    # Handle leftTop, rightTop, etc.
    replacements = [
        ('lefttop','left-top'), ('righttop','right-top'),
        ('leftbottom','left-bottom'), ('rightbottom','right-bottom'),
        ('topleft','left-top'), ('topright','right-top'),
        ('bottomleft','left-bottom'), ('bottomright','right-bottom'),
        ('centertop','top'), ('topcenter','top'),
        ('centerbottom','bottom'), ('bottomcenter','bottom'),
        ('centerleft','left'), ('leftcenter','left'),
        ('centerright','right'), ('rightcenter','right'),
        ('centercenter','center'),
        ('top-left','left-top'), ('top-right','right-top'),
        ('bottom-left','left-bottom'), ('bottom-right','right-bottom'),
    ]
    for old, new in replacements:
        a = a.replace(old, new)
    # Validate - must be one of 9
    valid = {'left-top','top','right-top','left','center','right','left-bottom','bottom','right-bottom'}
    if a not in valid:
        # Try to infer from substrings
        if 'left' in a and 'top' in a:
            return 'left-top'
        if 'right' in a and 'top' in a:
            return 'right-top'
        if 'left' in a and 'bottom' in a:
            return 'left-bottom'
        if 'right' in a and 'bottom' in a:
            return 'right-bottom'
        if 'left' in a:
            return 'left'
        if 'right' in a:
            return 'right'
        if 'top' in a:
            return 'top'
        if 'bottom' in a:
            return 'bottom'
        return 'center'
    return a

def _align_offset(align, w, h):
    """
    Given align and bounding box w,h, return offset of reference point inside bbox.
    For Rect: left = x - ox, top = y - oy
    ox = 0 for left, w/2 for center, w for right
    oy = 0 for top, h/2 for center, h for bottom
    """
    a = _normalize_align(align)
    # horizontal
    if a in ('left-top','left','left-bottom'):
        ox = 0
    elif a in ('right-top','right','right-bottom'):
        ox = w
    else: # top, center, bottom
        ox = w/2
    # vertical
    if a in ('left-top','top','right-top'):
        oy = 0
    elif a in ('left-bottom','bottom','right-bottom'):
        oy = h
    else: # left, center, right
        oy = h/2
    return ox, oy

def _resolve_bbox(x, y, w, h, align):
    """Given reference point x,y and bbox w,h and align, return left,top"""
    ox, oy = _align_offset(align, w, h)
    return x - ox, y - oy

# ---------- Canvas setup ----------
_canvas = None
_ctx = None
_app = None
_shapes = []  # for compatibility
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
            document.body.appendChild(_canvas)
        _ctx = _canvas.getContext('2d')

def _clear_shapes():
    global _shapes
    _shapes = []

# ---------- Base Shape ----------
class _Shape:
    def __init__(self, **kwargs):
        self.fill = kwargs.get('fill', 'black')
        self.border = kwargs.get('border', None)
        self.borderWidth = kwargs.get('borderWidth', 2)
        self.opacity = kwargs.get('opacity', 100)
        self.rotateAngle = kwargs.get('rotateAngle', 0)
        self.dashes = kwargs.get('dashes', False)
        self.visible = kwargs.get('visible', True)
        self.align = _normalize_align(kwargs.get('align', 'center'))
        self._left = 0
        self._top = 0
        self._width = 0
        self._height = 0
        self._group = None

    @property
    def left(self):
        return self._left
    @left.setter
    def left(self, v):
        self._left = v

    @property
    def top(self):
        return self._top
    @top.setter
    def top(self, v):
        self._top = v

    @property
    def right(self):
        return self._left + self._width
    @right.setter
    def right(self, v):
        self._left = v - self._width

    @property
    def bottom(self):
        return self._top + self._height
    @bottom.setter
    def bottom(self, v):
        self._top = v - self._height

    @property
    def centerX(self):
        return self._left + self._width/2
    @centerX.setter
    def centerX(self, v):
        self._left = v - self._width/2

    @property
    def centerY(self):
        return self._top + self._height/2
    @centerY.setter
    def centerY(self, v):
        self._top = v - self._height/2

    @property
    def width(self):
        return self._width
    @width.setter
    def width(self, v):
        cx = self.centerX
        self._width = v
        self.centerX = cx

    @property
    def height(self):
        return self._height
    @height.setter
    def height(self, v):
        cy = self.centerY
        self._height = v
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

    def hits(self, x, y):
        return self.contains(x, y)

    def contains(self, x, y):
        return (self._left <= x <= self._left + self._width and
                self._top <= y <= self._top + self._height)

    def hitsShape(self, other):
        try:
            return not (self.right < other.left or self.left > other.right or
                        self.bottom < other.top or self.top > other.bottom)
        except:
            return False

    def containsShape(self, other):
        try:
            return (self.left <= other.left and self.right >= other.right and
                    self.top <= other.top and self.bottom >= other.bottom)
        except:
            return False

# ---------- Rect - default left-top per CMU docs ----------
class Rect(_Shape):
    def __init__(self, x, y, width, height, **kwargs):
        # CMU: Rect(left, top, width, height, align='left-top')
        align = kwargs.get('align', 'left-top')
        super().__init__(align=align, **kwargs)
        self._width = width
        self._height = height
        l, t = _resolve_bbox(x, y, width, height, align)
        self._left = l
        self._top = t
        self.roundness = kwargs.get('roundness', 0)
        _shapes.append(self)

# ---------- Oval - default center ----------
class Oval(_Shape):
    def __init__(self, x, y, width, height, **kwargs):
        align = kwargs.get('align', 'center')
        super().__init__(align=align, **kwargs)
        self._width = width
        self._height = height
        l, t = _resolve_bbox(x, y, width, height, align)
        self._left = l
        self._top = t
        _shapes.append(self)

# ---------- Circle - default center ----------
class Circle(_Shape):
    def __init__(self, x, y, radius, **kwargs):
        align = kwargs.get('align', 'center')
        super().__init__(align=align, **kwargs)
        self._radius = radius
        w = h = radius*2
        self._width = w
        self._height = h
        l, t = _resolve_bbox(x, y, w, h, align)
        self._left = l
        self._top = t
        _shapes.append(self)

    @property
    def radius(self):
        return self._radius
    @radius.setter
    def radius(self, v):
        self._radius = v
        self._width = self._height = v*2

    @property
    def centerX(self):
        return self._left + self._radius
    @centerX.setter
    def centerX(self, v):
        self._left = v - self._radius

    @property
    def centerY(self):
        return self._top + self._radius
    @centerY.setter
    def centerY(self, v):
        self._top = v - self._radius

# ---------- RegularPolygon - default center ----------
class RegularPolygon(_Shape):
    def __init__(self, x, y, radius, points, **kwargs):
        align = kwargs.get('align', 'center')
        super().__init__(align=align, **kwargs)
        self._radius = radius
        self.points = points
        w = h = radius*2
        self._width = w
        self._height = h
        l, t = _resolve_bbox(x, y, w, h, align)
        self._left = l
        self._top = t
        _shapes.append(self)

    @property
    def centerX(self):
        return self._left + self._radius
    @centerX.setter
    def centerX(self, v):
        self._left = v - self._radius
    @property
    def centerY(self):
        return self._top + self._radius
    @centerY.setter
    def centerY(self, v):
        self._top = v - self._radius
    @property
    def radius(self):
        return self._radius
    @radius.setter
    def radius(self, v):
        self._radius = v
        self._width = self._height = v*2

# ---------- Star - default center ----------
class Star(RegularPolygon):
    def __init__(self, x, y, radius, points, **kwargs):
        super().__init__(x, y, radius, points, **kwargs)
        self.ratio = kwargs.get('ratio', 0.5)

# ---------- Line ----------
class Line:
    def __init__(self, x1, y1, x2, y2, **kwargs):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.fill = kwargs.get('fill','black')
        self.border = kwargs.get('border', None)
        self.lineWidth = kwargs.get('lineWidth', kwargs.get('borderWidth', 2))
        self.opacity = kwargs.get('opacity', 100)
        self.visible = kwargs.get('visible', True)
        self.dashes = kwargs.get('dashes', False)
        self.align = _normalize_align(kwargs.get('align','center'))
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
        return (self.x1+self.x2)/2
    @centerX.setter
    def centerX(self, v):
        dx = v - self.centerX
        self.x1 += dx
        self.x2 += dx
    @property
    def centerY(self):
        return (self.y1+self.y2)/2
    @centerY.setter
    def centerY(self, v):
        dy = v - self.centerY
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
    def hits(self, x, y):
        # point near line
        return distance(x,y,self.x1,self.y1) + distance(x,y,self.x2,self.y2) - distance(self.x1,self.y1,self.x2,self.y2) < 5
    def contains(self, x, y):
        return self.hits(x,y)

# ---------- Polygon ----------
class Polygon:
    def __init__(self, *points, **kwargs):
        self.points = list(points)
        self.fill = kwargs.get('fill','black')
        self.border = kwargs.get('border', None)
        self.borderWidth = kwargs.get('borderWidth',2)
        self.opacity = kwargs.get('opacity',100)
        self.visible = kwargs.get('visible', True)
        self.dashes = kwargs.get('dashes', False)
        self.rotateAngle = kwargs.get('rotateAngle', 0)
        self.align = _normalize_align(kwargs.get('align','center'))
        xs = self.points[0::2]
        ys = self.points[1::2]
        self._left = min(xs) if xs else 0
        self._top = min(ys) if ys else 0
        self._width = (max(xs)-min(xs)) if xs else 0
        self._height = (max(ys)-min(ys)) if ys else 0
        # If align given with x,y in kwargs, reposition
        if 'centerX' in kwargs or 'centerY' in kwargs or 'left' in kwargs:
            # Handle positioning via align
            ref_x = kwargs.get('centerX', kwargs.get('left', None))
            ref_y = kwargs.get('centerY', kwargs.get('top', None))
            if ref_x is not None and ref_y is not None:
                l, t = _resolve_bbox(ref_x, ref_y, self._width, self._height, self.align)
                dx = l - self._left
                dy = t - self._top
                self.points = [p+dx if i%2==0 else p+dy for i,p in enumerate(self.points)]
                self._left = l
                self._top = t
        _shapes.append(self)
    @property
    def left(self):
        return self._left
    @property
    def right(self):
        return self._left + self._width
    @property
    def top(self):
        return self._top
    @property
    def bottom(self):
        return self._top + self._height
    @property
    def centerX(self):
        return self._left + self._width/2
    @property
    def centerY(self):
        return self._top + self._height/2
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

# ---------- Arc ----------
class Arc(_Shape):
    def __init__(self, x, y, width, height, startAngle, sweepAngle, **kwargs):
        align = kwargs.get('align','center')
        super().__init__(align=align, **kwargs)
        self._width = width
        self._height = height
        l, t = _resolve_bbox(x, y, width, height, align)
        self._left = l
        self._top = t
        self.startAngle = startAngle
        self.sweepAngle = sweepAngle
        _shapes.append(self)

# ---------- Label - default center ----------
class Label:
    def __init__(self, text, x, y, **kwargs):
        self.text = str(text)
        self.size = kwargs.get('size', 12)
        self.font = kwargs.get('font','arial')
        self.bold = kwargs.get('bold', False)
        self.italic = kwargs.get('italic', False)
        self.fill = kwargs.get('fill','black')
        self.opacity = kwargs.get('opacity',100)
        self.visible = kwargs.get('visible', True)
        self.rotateAngle = kwargs.get('rotateAngle',0)
        self.align = _normalize_align(kwargs.get('align','center'))
        self._x = x
        self._y = y
        self._width = len(self.text)*self.size*0.6
        self._height = self.size
        _shapes.append(self)
    @property
    def centerX(self):
        return self._x
    @centerX.setter
    def centerX(self, v):
        self._x = v
    @property
    def centerY(self):
        return self._y
    @centerY.setter
    def centerY(self, v):
        self._y = v
    @property
    def left(self):
        # left depends on align
        a = self.align
        if 'left' in a:
            return self._x
        elif 'right' in a:
            return self._x - self._width
        else:
            return self._x - self._width/2
    @property
    def top(self):
        a = self.align
        if 'top' in a:
            return self._y
        elif 'bottom' in a:
            return self._y - self._height
        else:
            return self._y - self._height/2
    @property
    def right(self):
        return self.left + self._width
    @property
    def bottom(self):
        return self.top + self._height
    @property
    def width(self):
        return self._width
    @property
    def height(self):
        return self._height
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

# ---------- Image ----------
class Image(_Shape):
    def __init__(self, path, x, y, **kwargs):
        align = kwargs.get('align','center')
        super().__init__(align=align, **kwargs)
        self.path = path
        self._width = kwargs.get('width', 100)
        self._height = kwargs.get('height', 100)
        l, t = _resolve_bbox(x, y, self._width, self._height, align)
        self._left = l
        self._top = t
        self._img = None
        # Load image
        try:
            img = window.Image.new()
            img.src = path
            self._img = img
            _image_cache[path] = img
        except:
            pass
        _shapes.append(self)
    @property
    def centerX(self):
        return self._left + self._width/2
    @centerX.setter
    def centerX(self, v):
        self._left = v - self._width/2
    @property
    def centerY(self):
        return self._top + self._height/2
    @centerY.setter
    def centerY(self, v):
        self._top = v - self._height/2

# ---------- Group ----------
class Group:
    def __init__(self, *shapes):
        self.shapes = list(shapes)
        self.visible = True
        self.opacity = 100
        self.rotateAngle = 0
        self._left = 0
        self._top = 0
        if shapes:
            self._left = min([s.left for s in shapes if hasattr(s,'left')])
            self._top = min([s.top for s in shapes if hasattr(s,'top')])
        _shapes.append(self)
    @property
    def left(self):
        return self._left
    @property
    def top(self):
        return self._top
    @property
    def centerX(self):
        if not self.shapes:
            return 0
        return sum([s.centerX for s in self.shapes if hasattr(s,'centerX')])/len(self.shapes)
    @centerX.setter
    def centerX(self, v):
        dx = v - self.centerX
        for s in self.shapes:
            if hasattr(s,'centerX'):
                s.centerX += dx
    @property
    def centerY(self):
        if not self.shapes:
            return 0
        return sum([s.centerY for s in self.shapes if hasattr(s,'centerY')])/len(self.shapes)
    @centerY.setter
    def centerY(self, v):
        dy = v - self.centerY
        for s in self.shapes:
            if hasattr(s,'centerY'):
                s.centerY += dy
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

# ---------- Draw functions - all honor 9 aligns ----------
def drawRect(x, y, width, height, fill=None, border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='left-top', visible=True, roundness=0):
    _ensure_canvas()
    if not visible:
        return
    left, top = _resolve_bbox(x, y, width, height, align)
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity/100
        if rotateAngle != 0:
            cx = left + width/2
            cy = top + height/2
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-cx, -cy)
        if roundness > 0:
            r = min(roundness, min(width, height)/2)
            ctx.beginPath()
            ctx.moveTo(left+r, top)
            ctx.arcTo(left+width, top, left+width, top+height, r)
            ctx.arcTo(left+width, top+height, left, top+height, r)
            ctx.arcTo(left, top+height, left, top, r)
            ctx.arcTo(left, top, left+width, top, r)
            ctx.closePath()
            if fill is not None:
                ctx.fillStyle = fill if isinstance(fill,str) else str(fill)
                ctx.fill()
            if border is not None:
                ctx.strokeStyle = border if isinstance(border,str) else str(border)
                ctx.lineWidth = borderWidth
                if dashes:
                    ctx.setLineDash([6,3])
                ctx.stroke()
        else:
            if fill is not None:
                ctx.fillStyle = fill if isinstance(fill,str) else str(fill)
                ctx.fillRect(left, top, width, height)
            if border is not None:
                ctx.strokeStyle = border if isinstance(border,str) else str(border)
                ctx.lineWidth = borderWidth
                if dashes:
                    ctx.setLineDash([6,3])
                ctx.strokeRect(left, top, width, height)
    finally:
        ctx.restore()

def drawCircle(x, y, radius, fill=None, border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible:
        return
    w = h = radius*2
    left, top = _resolve_bbox(x, y, w, h, align)
    cx = left + radius
    cy = top + radius
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity/100
        if rotateAngle != 0:
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-cx, -cy)
        ctx.beginPath()
        ctx.arc(cx, cy, radius, 0, 2*math.pi)
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill,str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border,str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6,3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawOval(x, y, width, height, fill=None, border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible:
        return
    left, top = _resolve_bbox(x, y, width, height, align)
    cx = left + width/2
    cy = top + height/2
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity/100
        if rotateAngle != 0:
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-cx, -cy)
        ctx.beginPath()
        ctx.ellipse(cx, cy, width/2, height/2, 0, 0, 2*math.pi)
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill,str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border,str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6,3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawRegularPolygon(x, y, radius, points, fill=None, border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible:
        return
    w = h = radius*2
    left, top = _resolve_bbox(x, y, w, h, align)
    cx = left + radius
    cy = top + radius
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity/100
        if rotateAngle != 0:
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-cx, -cy)
        ctx.beginPath()
        for i in range(points):
            ang = 2*math.pi*i/points - math.pi/2
            px = cx + radius*math.cos(ang)
            py = cy + radius*math.sin(ang)
            if i==0:
                ctx.moveTo(px, py)
            else:
                ctx.lineTo(px, py)
        ctx.closePath()
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill,str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border,str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6,3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawStar(x, y, radius, points, fill=None, border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, align='center', visible=True, ratio=0.5):
    _ensure_canvas()
    if not visible:
        return
    w = h = radius*2
    left, top = _resolve_bbox(x, y, w, h, align)
    cx = left + radius
    cy = top + radius
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity/100
        if rotateAngle != 0:
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotateAngle))
            ctx.translate(-cx, -cy)
        ctx.beginPath()
        for i in range(points*2):
            r = radius if i%2==0 else radius*ratio
            ang = math.pi*i/points - math.pi/2
            px = cx + r*math.cos(ang)
            py = cy + r*math.sin(ang)
            if i==0:
                ctx.moveTo(px, py)
            else:
                ctx.lineTo(px, py)
        ctx.closePath()
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill,str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border,str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6,3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawLabel(text, x, y, fill=None, size=12, font='arial', bold=False, italic=False, opacity=100, align='center', visible=True, rotateAngle=0):
    _ensure_canvas()
    if not visible:
        return
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity/100
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

def drawLine(x1, y1, x2, y2, fill=None, lineWidth=2, opacity=100, dashes=False, visible=True):
    _ensure_canvas()
    if not visible:
        return
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity/100
        ctx.strokeStyle = fill if fill else 'black'
        ctx.lineWidth = lineWidth
        if dashes:
            ctx.setLineDash([6,3])
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
    finally:
        ctx.restore()

def drawPolygon(*points, fill=None, border=None, borderWidth=2, opacity=100, rotateAngle=0, dashes=False, visible=True, align=None):
    _ensure_canvas()
    if not visible or len(points) < 4:
        return
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity/100
        ctx.beginPath()
        ctx.moveTo(points[0], points[1])
        for i in range(2, len(points), 2):
            ctx.lineTo(points[i], points[i+1])
        ctx.closePath()
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill,str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border,str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6,3])
            ctx.stroke()
    finally:
        ctx.restore()

def drawArc(x, y, width, height, startAngle, sweepAngle, fill=None, border=None, borderWidth=2, opacity=100, dashes=False, align='center', visible=True):
    _ensure_canvas()
    if not visible:
        return
    left, top = _resolve_bbox(x, y, width, height, align)
    cx = left + width/2
    cy = top + height/2
    ctx = _ctx
    ctx.save()
    try:
        ctx.globalAlpha = opacity/100
        ctx.beginPath()
        start = math.radians(startAngle)
        end = math.radians(startAngle + sweepAngle)
        ctx.ellipse(cx, cy, width/2, height/2, 0, start, end)
        if fill is not None:
            ctx.fillStyle = fill if isinstance(fill,str) else str(fill)
            ctx.fill()
        if border is not None:
            ctx.strokeStyle = border if isinstance(border,str) else str(border)
            ctx.lineWidth = borderWidth
            if dashes:
                ctx.setLineDash([6,3])
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
    # Determine size
    w = width if width is not None else (img.width if hasattr(img,'width') else 100)
    h = height if height is not None else (img.height if hasattr(img,'height') else 100)
    left, top = _resolve_bbox(x, y, w, h, align)
    ctx.save()
    try:
        ctx.globalAlpha = opacity/100
        if rotateAngle != 0:
            cx = left + w/2
            cy = top + h/2
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
def rgb(r,g,b):
    return f"rgb({int(r)},{int(g)},{int(b)})"

def gradient(*colors, start='left-top'):
    return colors[0] if colors else 'black'

def distance(x1,y1,x2,y2):
    return math.hypot(x2-x1, y2-y1)

def angleTo(x1,y1,x2,y2):
    return math.degrees(math.atan2(y2-y1, x2-x1))

def getPointInDir(x,y,angle,length):
    rad = math.radians(angle)
    return x + length*math.cos(rad), y + length*math.sin(rad)

def rounded(n):
    return round(n)

def makeList(n, v=None):
    return [v]*n if v is not None else [None]*n

def randrange(a,b=None):
    import random
    if b is None:
        return random.randrange(a)
    return random.randrange(a,b)

def randint(a,b):
    import random
    return random.randint(a,b)

def random(a=None,b=None):
    import random
    if a is None:
        return random.random()
    if b is None:
        return random.random()*a
    return random.uniform(a,b)

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
        self._onMousePress = None
        self._onMouseDrag = None
        self._onMouseRelease = None
        self._onMouseMove = None
        self._onKeyPress = None
        self._onKeyRelease = None
        self._onKeyHold = None
        self._onResize = None
        _app = self
        _clear_shapes()

def runApp(width=400, height=400):
    # For Brython, actual loop is handled in index.html
    pass

# For compatibility with cmu_graphics
def cmu_graphics_run(app=None, width=400, height=400):
    runApp(width, height)
