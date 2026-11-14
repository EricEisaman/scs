"""
scs_webgl.py - SCS WebGL2 renderer + shared GPU geometry compiler.

Architecture (from the reference survey in README.md):

  * Two.js / PixiJS / melonJS  -> renderer-agnostic scene graph, one API,
    AUTO fallback WebGPU -> WebGL2 -> Canvas2D.
  * Canvas2DtoWebGL (Javi Agenjo) / expo-2d-context -> emulate Canvas2D on
    WebGL by tessellating fills into triangles, expanding strokes into
    triangle strips, and rasterising text on an offscreen 2D canvas into
    a texture atlas. Never reimplement a font rasteriser.
  * Mapbox earcut / Lyon / Pathfinder / Vello -> fill = triangulation,
    stroke = stroke-to-fill. WebGPU differs from WebGL2 only in *submission*
    (WGSL pipelines vs GL calls), not in geometry.

So this module owns the geometry compiler used by BOTH GPU backends:

    parse_color / flatten_* / ear-clip triangulate / stroke_to_fill
    / expand_dashes / TextAtlas / gradient sampling

scs_webgpu.py imports the compiler from here and only replaces the
submission layer (WGSL pipelines, GPUBuffers, GPUTextures). scs_2d.py does
not use this module at all -- it is the reference Canvas2D backend.

Coordinate system (all renderers): CSS pixels, origin top-left, y down.
WebGL2 flips y in the vertex shader (clip.y = -clip.y).
"""

import math

try:
    from browser import document, window
except ImportError:  # CPython tests: stubbed by tests/
    document = None
    window = None


# ----------------------------------------------------------------------
# Colours
# ----------------------------------------------------------------------

_NAMED = {
    'black': (0, 0, 0), 'white': (255, 255, 255),
    'red': (255, 0, 0), 'green': (0, 128, 0), 'blue': (0, 0, 255),
    'yellow': (255, 255, 0), 'cyan': (0, 255, 255), 'magenta': (255, 0, 255),
    'orange': (255, 165, 0), 'purple': (128, 0, 128), 'pink': (255, 192, 203),
    'brown': (165, 42, 42), 'gray': (128, 128, 128), 'grey': (128, 128, 128),
    'lime': (0, 255, 0), 'navy': (0, 0, 128), 'teal': (0, 128, 128),
    'gold': (255, 215, 0), 'silver': (192, 192, 192),
    'lightgray': (211, 211, 211), 'lightgrey': (211, 211, 211),
    'darkgray': (169, 169, 169), 'darkgrey': (169, 169, 169),
    'lightblue': (173, 216, 230), 'lightgreen': (144, 238, 144),
    'darkred': (139, 0, 0), 'darkgreen': (0, 100, 0), 'darkblue': (0, 0, 139),
    'crimson': (220, 20, 60), 'coral': (255, 127, 80), 'salmon': (250, 128, 114),
    'khaki': (240, 230, 140), 'beige': (245, 245, 220), 'ivory': (255, 255, 240),
    'lavender': (230, 230, 250), 'violet': (238, 130, 238),
    'indigo': (75, 0, 130), 'maroon': (128, 0, 0), 'olive': (128, 128, 0),
    'aqua': (0, 255, 255), 'fuchsia': (255, 0, 255), 'limegreen': (50, 205, 50),
    'skyblue': (135, 206, 235), 'steelblue': (70, 130, 180),
    'transparent': (0, 0, 0),
}


def parse_color(c):
    """Return (r, g, b, a) with rgb in 0..1, a in 0..1. Gradient dicts fall
    back to their first stop (callers that support gradients use
    gradient_color_at() instead)."""
    if c is None:
        return (0.0, 0.0, 0.0, 0.0)
    if isinstance(c, dict):
        if c.get('_is_grad'):
            cols = c.get('colors') or ['black']
            return parse_color(cols[0])
        return (0.0, 0.0, 0.0, 1.0)
    if isinstance(c, (list, tuple)):
        if len(c) == 3:
            r, g, b = c
            return (r / 255.0 if r > 1 else float(r),
                    g / 255.0 if g > 1 else float(g),
                    b / 255.0 if b > 1 else float(b), 1.0)
        if len(c) == 4:
            r, g, b, a = c
            return (r / 255.0 if r > 1 else float(r),
                    g / 255.0 if g > 1 else float(g),
                    b / 255.0 if b > 1 else float(b),
                    a / 100.0 if a > 1 else float(a))
        return (0.0, 0.0, 0.0, 1.0)
    s = str(c).strip().lower()
    if s in _NAMED:
        r, g, b = _NAMED[s]
        return (r / 255.0, g / 255.0, b / 255.0, 0.0 if s == 'transparent' else 1.0)
    if s.startswith('#'):
        h = s[1:]
        if len(h) == 3:
            h = ''.join(ch * 2 for ch in h)
        if len(h) == 6:
            return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0,
                    int(h[4:6], 16) / 255.0, 1.0)
        if len(h) == 8:
            return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0,
                    int(h[4:6], 16) / 255.0, int(h[6:8], 16) / 255.0)
    if s.startswith('rgba'):
        inner = s[5:-1].split(',')
        r, g, b, a = (float(v) for v in inner)
        return (r / 255.0, g / 255.0, b / 255.0, a)
    if s.startswith('rgb'):
        inner = s[4:-1].split(',')
        r, g, b = (float(v) for v in inner)
        return (r / 255.0, g / 255.0, b / 255.0, 1.0)
    return (0.0, 0.0, 0.0, 1.0)


def _gradient_axis(start, left, top, w, h):
    """Map SCS gradient start=... to (x0, y0, x1, y1) in bbox coords."""
    cx, cy = left + w / 2, top + h / 2
    table = {
        'top': (cx, top, cx, top + h),
        'bottom': (cx, top + h, cx, top),
        'left': (left, cy, left + w, cy),
        'right': (left + w, cy, left, cy),
        'left-top': (left, top, left + w, top + h),
        'top-left': (left, top, left + w, top + h),
        'right-top': (left + w, top, left, top + h),
        'top-right': (left + w, top, left, top + h),
        'left-bottom': (left, top + h, left + w, top),
        'bottom-left': (left, top + h, left + w, top),
        'right-bottom': (left + w, top + h, left, top),
        'bottom-right': (left + w, top + h, left, top),
        'center': (cx, cy, cx + w, cy),
    }
    return table.get(str(start).strip().lower(), (cx, top, cx, top + h))


def gradient_color_at(x, y, fill, bbox):
    """Per-vertex colour for a fill that may be a gradient dict.
    bbox = (left, top, w, h). Solid fills return parse_color(fill)."""
    if not isinstance(fill, dict) or not fill.get('_is_grad'):
        return parse_color(fill)
    colors = fill.get('colors') or ['black']
    if len(colors) == 1:
        return parse_color(colors[0])
    left, top, w, h = bbox
    x0, y0, x1, y1 = _gradient_axis(fill.get('start', 'top'), left, top, w, h)
    dx, dy = x1 - x0, y1 - y0
    denom = dx * dx + dy * dy
    t = 0.0 if denom == 0 else ((x - x0) * dx + (y - y0) * dy) / denom
    t = max(0.0, min(1.0, t))
    seg = t * (len(colors) - 1)
    i = min(int(seg), len(colors) - 2)
    f = seg - i
    c0 = parse_color(colors[i])
    c1 = parse_color(colors[i + 1])
    return tuple(c0[k] + (c1[k] - c0[k]) * f for k in range(4))


# ----------------------------------------------------------------------
# Path flattening: curves -> polylines (GPU has no curves)
# ----------------------------------------------------------------------

def flatten_arc(cx, cy, rx, ry, start_deg, sweep_deg, rotation_deg=0):
    n = max(8, int(abs(sweep_deg) / 360.0 * 64))
    rot = math.radians(rotation_deg)
    cr, sr = math.cos(rot), math.sin(rot)
    pts = []
    for i in range(n + 1):
        a = math.radians(start_deg + sweep_deg * i / n)
        x, y = cx + rx * math.cos(a), cy + ry * math.sin(a)
        if rotation_deg:
            x, y = cx + (x - cx) * cr - (y - cy) * sr, cy + (x - cx) * sr + (y - cy) * cr
        pts.append((x, y))
    return pts


def flatten_ellipse(cx, cy, rx, ry, rotation_deg=0):
    return flatten_arc(cx, cy, rx, ry, 0, 360, rotation_deg)[:-1]


def flatten_rounded_rect(left, top, w, h, r):
    r = max(0.0, min(r, min(w, h) / 2))
    if r == 0:
        return [(left, top), (left + w, top), (left + w, top + h), (left, top + h)]
    pts = []
    corners = [
        (left + w - r, top + r, 270, 360),
        (left + w - r, top + h - r, 0, 90),
        (left + r, top + h - r, 90, 180),
        (left + r, top + r, 180, 270),
    ]
    for cx, cy, a0, a1 in corners:
        for i in range(9):
            a = math.radians(a0 + (a1 - a0) * i / 8)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def rotate_points(pts, cx, cy, angle_deg):
    if not angle_deg:
        return list(pts)
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa,
             cy + (x - cx) * sa + (y - cy) * ca) for (x, y) in pts]


# ----------------------------------------------------------------------
# Triangulation: ear clipping (Mapbox earcut idea, O(n^2) -- fine for
# SCS polygons, which are small). Falls back to a fan on degenerate input.
# ----------------------------------------------------------------------

def _signed_area(pts):
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] -
                      pts[(i + 1) % len(pts)][0] * pts[i][1]
                      for i in range(len(pts)))


def _point_in_triangle(px, py, ax, ay, bx, by, cx, cy):
    def sign(x1, y1, x2, y2, x3, y3):
        return (x1 - x3) * (y2 - y3) - (x2 - x3) * (y1 - y3)
    d1 = sign(px, py, ax, ay, bx, by)
    d2 = sign(px, py, bx, by, cx, cy)
    d3 = sign(px, py, cx, cy, ax, ay)
    neg = (d1 < -1e-9) or (d2 < -1e-9) or (d3 < -1e-9)
    pos = (d1 > 1e-9) or (d2 > 1e-9) or (d3 > 1e-9)
    return not (neg and pos)


def triangulate_polygon(pts):
    """pts: [(x, y), ...] (open ring, no duplicated last point).
    Returns flat [(x, y), ...] triangle vertices (3 per triangle)."""
    pts = [(float(x), float(y)) for (x, y) in pts]
    if len(pts) < 3:
        return []
    if len(pts) == 3:
        return list(pts)
    # Drop a duplicated closing point if present.
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if _signed_area(pts) < 0:
        pts = list(reversed(pts))
    idx = list(range(len(pts)))
    out = []

    def is_convex(i0, i1, i2):
        ax, ay = pts[i0]
        bx, by = pts[i1]
        cx, cy = pts[i2]
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) > 1e-9

    guard = 0
    while len(idx) > 3 and guard < len(pts) * 4:
        guard += 1
        clipped = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if not is_convex(i0, i1, i2):
                continue
            ax, ay = pts[i0]
            bx, by = pts[i1]
            cx, cy = pts[i2]
            if any(_point_in_triangle(pts[j][0], pts[j][1], ax, ay, bx, by, cx, cy)
                   for j in idx if j not in (i0, i1, i2)):
                continue
            out.extend([pts[i0], pts[i1], pts[i2]])
            idx.pop(k)
            clipped = True
            break
        if not clipped:
            break
    if len(idx) == 3:
        out.extend([pts[idx[0]], pts[idx[1]], pts[idx[2]]])
    elif len(idx) > 3:
        # Degenerate / self-intersecting input: fan fallback (matches what
        # a naive triangulator would do; 2D backend stays authoritative).
        for i in range(1, len(idx) - 1):
            out.extend([pts[idx[0]], pts[idx[i]], pts[idx[i + 1]]])
    return out


# ----------------------------------------------------------------------
# Stroke -> fill (Lyon / Pathfinder stroke-to-fill, centred stroke like
# Canvas2D: half the width inside, half outside).
# ----------------------------------------------------------------------

def _normal(x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1.0
    return (-dy / L, dx / L)


def stroke_to_fill(pts, width, closed=False):
    """pts: polyline [(x,y)...]. Returns flat triangle vertices."""
    if len(pts) < 2 or width <= 0:
        return []
    hw = width / 2.0
    n = len(pts)
    # Offset points per vertex: average of adjacent segment normals.
    left, right = [], []
    for i in range(n):
        if closed:
            p_prev, p_next = pts[i - 1], pts[(i + 1) % n]
        elif i == 0:
            p_prev, p_next = pts[0], pts[1]
        elif i == n - 1:
            p_prev, p_next = pts[-2], pts[-1]
        else:
            p_prev, p_next = pts[i - 1], pts[i + 1]
        n1 = _normal(p_prev[0], p_prev[1], pts[i][0], pts[i][1])
        n2 = _normal(pts[i][0], pts[i][1], p_next[0], p_next[1])
        nx, ny = n1[0] + n2[0], n1[1] + n2[1]
        L = math.hypot(nx, ny) or 1.0
        nx, ny = nx / L, ny / L
        # Miter length compensation: 1 / cos(half-angle).
        dot = max(-1.0, min(1.0, (n1[0] * n2[0] + n1[1] * n2[1]) / 2.0 + 0.5))
        miter = 1.0 / max(0.25, math.sqrt(max(0.0, dot)))
        miter = min(miter, 4.0)
        x, y = pts[i]
        left.append((x + nx * hw * miter, y + ny * hw * miter))
        right.append((x - nx * hw * miter, y - ny * hw * miter))
    segs = [(i, (i + 1) % n) for i in range(n)] if closed else \
        [(i, i + 1) for i in range(n - 1)]
    out = []
    for a, b in segs:
        out.extend([left[a], right[a], left[b],
                    right[a], right[b], left[b]])
    return out


def expand_dashes(pts, dash=(6, 3), closed=False):
    """Split a polyline into the 'on' sub-polylines of a dash pattern.
    Returns a list of polylines. Canvas2D setLineDash([6,3]) equivalent."""
    if not dash:
        return [list(pts)]
    pattern = list(dash)
    out, cur = [], []
    pat_i, pat_left, on = 0, float(pattern[0]), True
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    if closed and len(pts) > 2:
        segs.append((pts[-1], pts[0]))
    for (x1, y1), (x2, y2) in segs:
        seg_len = math.hypot(x2 - x1, y2 - y1)
        t = 0.0
        while t < seg_len:
            step = min(pat_left, seg_len - t)
            if on:
                f0, f1 = t / seg_len, (t + step) / seg_len
                p0 = (x1 + (x2 - x1) * f0, y1 + (y2 - y1) * f0)
                p1 = (x1 + (x2 - x1) * f1, y1 + (y2 - y1) * f1)
                if not cur:
                    cur.append(p0)
                cur.append(p1)
            else:
                if cur:
                    out.append(cur)
                    cur = []
            t += step
            pat_left -= step
            if pat_left <= 1e-9:
                pat_i = (pat_i + 1) % len(pattern)
                pat_left = float(pattern[pat_i])
                on = not on
    if cur:
        out.append(cur)
    return out


# ----------------------------------------------------------------------
# Text atlas: rasterise glyphs once on an offscreen 2D canvas, then draw
# textured quads on the GPU (PixiJS / Canvas2DtoWebGL / expo approach).
# ----------------------------------------------------------------------

class TextAtlas:
    def __init__(self, size=2048):
        self.size = size
        self.canvas = None
        self.ctx = None
        self.cache = {}
        self.cursor_x = 4
        self.cursor_y = 4
        self.row_h = 0
        self.dirty = True
        if document is not None:
            try:
                self.canvas = document.createElement('canvas')
                self.canvas.width = size
                self.canvas.height = size
                self.ctx = self.canvas.getContext('2d')
            except Exception:
                self.canvas = None

    def measure(self, text, font_str):
        if self.ctx is not None:
            try:
                self.ctx.font = font_str
                m = self.ctx.measureText(str(text))
                return float(m.width), float(getattr(m, 'actualBoundingBoxAscent', 12) +
                                             getattr(m, 'actualBoundingBoxDescent', 4))
            except Exception:
                pass
        return len(str(text)) * 7.0, 14.0

    def get_rect(self, text, font_str):
        """Return (u0, v0, u1, v1, w, h) in atlas UV space. Draws into the
        atlas on first use. White glyphs: tint is applied in the shader."""
        key = (str(text), font_str)
        if key in self.cache:
            return self.cache[key]
        w, h = self.measure(text, font_str)
        w, h = int(math.ceil(w)) + 2, int(math.ceil(h)) + 2
        if self.cursor_x + w > self.size - 4:
            self.cursor_x = 4
            self.cursor_y += self.row_h + 4
            self.row_h = 0
        if self.cursor_y + h > self.size - 4:
            # Atlas full: clear and restart. Geometry built earlier in this
            # frame keeps stale UVs for one frame (documented); SCS apps
            # rarely exceed a 2048px atlas of distinct labels.
            self.cache.clear()
            self.cursor_x, self.cursor_y, self.row_h = 4, 4, 0
        x, y = self.cursor_x, self.cursor_y
        if self.ctx is not None:
            try:
                self.ctx.font = font_str
                self.ctx.fillStyle = 'white'
                self.ctx.textBaseline = 'top'
                self.ctx.fillText(str(text), x + 1, y + 1)
            except Exception:
                pass
        self.cursor_x += w + 2
        self.row_h = max(self.row_h, h)
        self.dirty = True
        rect = (x / self.size, y / self.size,
                (x + w) / self.size, (y + h) / self.size, float(w), float(h))
        self.cache[key] = rect
        return rect


# ----------------------------------------------------------------------
# Affine transform stack (CPU-side; GPU shaders stay projection-only)
# ----------------------------------------------------------------------

_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def compose(m1, m2):
    """m1 * m2 for (a, b, c, d, tx, ty) with x' = a*x + c*y + tx."""
    a1, b1, c1, d1, t1x, t1y = m1
    a2, b2, c2, d2, t2x, t2y = m2
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * t2x + c1 * t2y + t1x, b1 * t2x + d1 * t2y + t1y)


def rotation_matrix(cx, cy, angle_deg):
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    # T(cx,cy) * R * T(-cx,-cy)
    return (ca, sa, -sa, ca,
            cx - ca * cx + sa * cy, cy - sa * cx - ca * cy)


class TransformStack:
    def __init__(self):
        self.stack = [(_IDENTITY, 1.0)]

    def push(self, cx, cy, angle_deg, alpha_mult):
        m, al = self.stack[-1]
        m2 = compose(m, rotation_matrix(cx, cy, angle_deg)) if angle_deg else m
        self.stack.append((m2, al * alpha_mult))

    def pop(self):
        if len(self.stack) > 1:
            self.stack.pop()

    @property
    def matrix(self):
        return self.stack[-1][0]

    @property
    def alpha(self):
        return self.stack[-1][1]

    def apply(self, pts):
        a, b, c, d, tx, ty = self.matrix
        return [(a * x + c * y + tx, b * x + d * y + ty) for (x, y) in pts]


# ----------------------------------------------------------------------
# Batched geometry sink shared by the two GPU renderers.
# Each renderer subclasses _GPURendererBase and implements _submit().
# ----------------------------------------------------------------------

class _GPURendererBase:
    kind = 'gpu'

    def __init__(self, canvas, width, height):
        self.canvas = canvas
        self.width = width
        self.height = height
        self.dpr = 1.0
        try:
            self.dpr = float(window.devicePixelRatio or 1.0)
        except Exception:
            pass
        self.transforms = TransformStack()
        self.atlas = TextAtlas()
        self._solid = []       # flat [x, y, r, g, b, a, ...]
        self._tex_batches = {}  # texture_key -> flat [x, y, u, v, r, g, b, a, ...]
        self._images = {}      # path -> HTMLImageElement
        self._bg = (1.0, 1.0, 1.0, 1.0)

    # -- frame ------------------------------------------------------
    def resize(self, width, height):
        self.width, self.height = width, height

    def begin_frame(self, background):
        self._bg = parse_color(background) if background is not None else (1, 1, 1, 1)
        self._solid = []
        self._tex_batches = {}
        self.transforms = TransformStack()

    def end_frame(self):
        self._submit()
        self._solid = []
        self._tex_batches = {}

    def push_transform(self, cx, cy, angle_deg, alpha_mult):
        self.transforms.push(cx, cy, angle_deg, alpha_mult)

    def pop_transform(self):
        self.transforms.pop()

    # -- emit helpers ----------------------------------------------
    def _emit_fill(self, pts, fill, bbox, opacity):
        tris = triangulate_polygon(pts)
        if not tris:
            return
        tris = self.transforms.apply(tris)
        alpha = opacity * self.transforms.alpha
        if isinstance(fill, dict) and fill.get('_is_grad'):
            for (x, y) in tris:
                r, g, b, a = gradient_color_at(x, y, fill, bbox)
                self._solid.extend([x, y, r, g, b, a * alpha])
        else:
            r, g, b, a = parse_color(fill)
            a *= alpha
            for (x, y) in tris:
                self._solid.extend([x, y, r, g, b, a])

    def _emit_stroke(self, pts, color, width, opacity, dashes, closed):
        if width <= 0 or color is None:
            return
        r, g, b, a = parse_color(color)
        a *= opacity * self.transforms.alpha
        lines = expand_dashes(pts, (6, 3) if dashes else None, closed) if dashes else [list(pts)]
        for line in lines:
            if len(line) < 2:
                continue
            tris = stroke_to_fill(line, width, closed)
            tris = self.transforms.apply(tris)
            for (x, y) in tris:
                self._solid.extend([x, y, r, g, b, a])

    def _emit_textured_quad(self, key, x, y, w, h, u0, v0, u1, v1, tint, opacity):
        quad = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        quad = self.transforms.apply(quad)
        r, g, b, a = parse_color(tint)
        a *= opacity * self.transforms.alpha
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad
        buf = self._tex_batches.setdefault(key, [])
        buf.extend([x0, y0, u0, v0, r, g, b, a,
                    x1, y1, u1, v0, r, g, b, a,
                    x2, y2, u1, v1, r, g, b, a,
                    x0, y0, u0, v0, r, g, b, a,
                    x2, y2, u1, v1, r, g, b, a,
                    x3, y3, u0, v1, r, g, b, a])

    # -- SCS draw API (identical signature on all three renderers) --
    def draw_rect(self, left, top, w, h, fill='black', border=None,
                  borderWidth=2, opacity=100, rotateAngle=0, dashes=False,
                  roundness=0):
        op = opacity / 100.0
        pts = flatten_rounded_rect(left, top, w, h, roundness) if roundness else \
            [(left, top), (left + w, top), (left + w, top + h), (left, top + h)]
        pts = rotate_points(pts, left + w / 2, top + h / 2, rotateAngle)
        if fill is not None:
            self._emit_fill(pts, fill, (left, top, w, h), op)
        if border is not None:
            self._emit_stroke(pts + [pts[0]], border, borderWidth, op, dashes, True)

    def draw_oval(self, cx, cy, w, h, fill='black', border=None,
                  borderWidth=2, opacity=100, rotateAngle=0, dashes=False):
        op = opacity / 100.0
        pts = flatten_ellipse(cx, cy, w / 2, h / 2, rotateAngle)
        if fill is not None:
            self._emit_fill(pts, fill, (cx - w / 2, cy - h / 2, w, h), op)
        if border is not None:
            self._emit_stroke(pts + [pts[0]], border, borderWidth, op, dashes, True)

    draw_circle = None  # replaced below (needs radius signature)

    def draw_circle_impl(self, cx, cy, radius, fill='black', border=None,
                         borderWidth=2, opacity=100, rotateAngle=0, dashes=False):
        self.draw_oval(cx, cy, radius * 2, radius * 2, fill, border,
                        borderWidth, opacity, rotateAngle, dashes)

    def draw_regular_polygon(self, cx, cy, radius, points, fill='black',
                             border=None, borderWidth=2, opacity=100,
                             rotateAngle=0, dashes=False):
        op = opacity / 100.0
        pts = []
        for i in range(int(points)):
            a = 2 * math.pi * i / points - math.pi / 2 + math.radians(rotateAngle)
            pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
        if fill is not None:
            self._emit_fill(pts, fill, (cx - radius, cy - radius, radius * 2, radius * 2), op)
        if border is not None:
            self._emit_stroke(pts + [pts[0]], border, borderWidth, op, dashes, True)

    def draw_star(self, cx, cy, radius, points, fill='black', border=None,
                  borderWidth=2, opacity=100, rotateAngle=0, dashes=False, ratio=0.5):
        op = opacity / 100.0
        pts = []
        for i in range(int(points) * 2):
            r = radius if i % 2 == 0 else radius * ratio
            a = math.pi * i / points - math.pi / 2 + math.radians(rotateAngle)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        if fill is not None:
            self._emit_fill(pts, fill, (cx - radius, cy - radius, radius * 2, radius * 2), op)
        if border is not None:
            self._emit_stroke(pts + [pts[0]], border, borderWidth, op, dashes, True)

    def draw_arc(self, cx, cy, w, h, startAngle, sweepAngle, fill=None,
                 border=None, borderWidth=2, opacity=100, dashes=False):
        op = opacity / 100.0
        pts = flatten_arc(cx, cy, w / 2, h / 2, startAngle, sweepAngle)
        if fill is not None:
            fan = [(cx, cy)] + pts
            self._emit_fill(fan, fill, (cx - w / 2, cy - h / 2, w, h), op)
        if border is not None:
            self._emit_stroke(pts, border, borderWidth, op, dashes, False)

    def draw_polygon(self, points, fill='black', border=None, borderWidth=2,
                     opacity=100, rotateAngle=0, dashes=False):
        op = opacity / 100.0
        pts = [(float(points[i]), float(points[i + 1]))
               for i in range(0, len(points) - 1, 2)]
        if not pts:
            return
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        pts = rotate_points(pts, cx, cy, rotateAngle)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bbox = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        if fill is not None:
            self._emit_fill(pts, fill, bbox, op)
        if border is not None:
            self._emit_stroke(pts + [pts[0]], border, borderWidth, op, dashes, True)

    def draw_line(self, x1, y1, x2, y2, fill='black', lineWidth=2,
                  opacity=100, dashes=False):
        self._emit_stroke([(x1, y1), (x2, y2)], fill, lineWidth,
                          opacity / 100.0, dashes, False)

    def draw_label(self, text, x, y, fill='black', size=12, font='arial',
                   bold=False, italic=False, opacity=100, align='center',
                   rotateAngle=0):
        style = ('italic ' if italic else '') + ('bold ' if bold else '')
        font_str = '%s%dpx %s' % (style, size, font)
        u0, v0, u1, v1, w, h = self.atlas.get_rect(text, font_str)
        # CMU align: (x, y) is the anchor; canvas textAlign/textBaseline
        # equivalents for the GPU quads.
        a = str(align).lower()
        if 'left' in a:
            ox = 0.0
        elif 'right' in a:
            ox = -w
        else:
            ox = -w / 2
        if 'top' in a:
            oy = 0.0
        elif 'bottom' in a:
            oy = -h
        else:
            oy = -h / 2
        quad_pts = [(x + ox, y + oy), (x + ox + w, y + oy),
                    (x + ox + w, y + oy + h), (x + ox, y + oy + h)]
        quad_pts = rotate_points(quad_pts, x, y, rotateAngle)
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = \
            self.transforms.apply(quad_pts)
        r, g, b, al = parse_color(fill)
        al *= (opacity / 100.0) * self.transforms.alpha
        buf = self._tex_batches.setdefault(('atlas',), [])
        buf.extend([x0, y0, u0, v0, r, g, b, al,
                    x1, y1, u1, v0, r, g, b, al,
                    x2, y2, u1, v1, r, g, b, al,
                    x0, y0, u0, v0, r, g, b, al,
                    x2, y2, u1, v1, r, g, b, al,
                    x3, y3, u0, v1, r, g, b, al])

    def draw_image(self, path, left, top, w, h, opacity=100, rotateAngle=0):
        img = self._images.get(path)
        if img is None:
            try:
                img = window.Image.new()
                img.src = path
                self._images[path] = img
            except Exception:
                return
        try:
            complete = bool(getattr(img, 'complete', False))
        except Exception:
            complete = False
        if not complete:
            return
        iw = float(getattr(img, 'naturalWidth', 0) or getattr(img, 'width', 0) or w)
        ih = float(getattr(img, 'naturalHeight', 0) or getattr(img, 'height', 0) or h)
        if iw == 0 or ih == 0:
            return
        self._emit_textured_quad(('image', path), left, top, w, h,
                                 0.0, 0.0, 1.0, 1.0, 'white', opacity / 100.0)
        # NOTE: rotateAngle for images is applied by _emit_textured_quad
        # through the transform stack only for Groups; a rotated standalone
        # image rotates around its centre via push/pop in the entrypoint
        # shape draw path. See scs_entrypoint.Image.draw.

    # -- sprites: SAME signature as 2D / WebGPU / WGPU-3D / XR --------
    # WebGL-2D + WebGPU-2D (both inherit this base) emit a textured quad
    # immediately. billboard + z are accepted and ignored (no camera).
    def draw_image_uv(self, path, u0, v0, u1, v1, left, top, w, h,
                      opacity=100, rotateAngle=0, flip_x=False, flip_y=False,
                      billboard='none', z=0, tint='white'):
        img = self._images.get(path)
        if img is None:
            try:
                img = window.Image.new()
                img.src = path
                self._images[path] = img
            except Exception:
                return
        try:
            complete = bool(getattr(img, 'complete', False))
        except Exception:
            complete = False
        if not complete:
            return
        if flip_x:
            u0, u1 = u1, u0
        if flip_y:
            v0, v1 = v1, v0
        if rotateAngle:
            cx, cy = float(left) + float(w) / 2, float(top) + float(h) / 2
            self.push_transform(cx, cy, rotateAngle, 1.0)
            try:
                self._emit_textured_quad(('image', path), left, top, w, h,
                                         float(u0), float(v0), float(u1), float(v1),
                                         tint or 'white', opacity / 100.0)
            finally:
                self.pop_transform()
        else:
            self._emit_textured_quad(('image', path), left, top, w, h,
                                     float(u0), float(v0), float(u1), float(v1),
                                     tint or 'white', opacity / 100.0)

    def draw_sprite(self, image, u0, v0, u1, v1, x, y, w, h,
                    opacity=100, rotateAngle=0, flip_x=False, flip_y=False,
                    billboard='none', z=0, tint='white'):
        left = float(x) - float(w) / 2
        top = float(y) - float(h) / 2
        return self.draw_image_uv(image, u0, v0, u1, v1, left, top, w, h,
                                  opacity=opacity, rotateAngle=rotateAngle,
                                  flip_x=flip_x, flip_y=flip_y, tint=tint)

    def draw_sprite_sheet(self, sheet, frame, x, y, w=None, h=None,
                          opacity=100, rotateAngle=0, flip_x=False, flip_y=False,
                          billboard='none', z=0, tint='white'):
        fr = sheet.frame(frame)
        ww = float(w) if w is not None else float(fr.w)
        hh = float(h) if h is not None else float(fr.h)
        u0, v0, u1, v1 = fr.uv
        return self.draw_sprite(sheet.image, u0, v0, u1, v1, x, y, ww, hh,
                                opacity=opacity, rotateAngle=rotateAngle,
                                flip_x=flip_x, flip_y=flip_y, billboard=billboard, z=z, tint=tint)

    def _submit(self):
        raise NotImplementedError


# Fix draw_circle name (kept separate for its radius signature).
_GPURendererBase.draw_circle = _GPURendererBase.draw_circle_impl
del _GPURendererBase.draw_circle_impl


# ----------------------------------------------------------------------
# WebGL2 renderer
# ----------------------------------------------------------------------

_SOLID_VS = """
attribute vec2 a_pos;
attribute vec4 a_color;
uniform vec2 u_res;
varying vec4 v_color;
void main() {
  vec2 clip = (a_pos / u_res) * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  v_color = a_color;
}
"""
_SOLID_FS = """
precision mediump float;
varying vec4 v_color;
void main() { gl_FragColor = v_color; }
"""
_TEX_VS = """
attribute vec2 a_pos;
attribute vec2 a_uv;
attribute vec4 a_color;
uniform vec2 u_res;
varying vec2 v_uv;
varying vec4 v_color;
void main() {
  vec2 clip = (a_pos / u_res) * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  v_uv = a_uv;
  v_color = a_color;
}
"""
_TEX_FS = """
precision mediump float;
uniform sampler2D u_tex;
uniform float u_mask;
varying vec2 v_uv;
varying vec4 v_color;
void main() {
  vec4 t = texture2D(u_tex, v_uv);
  if (u_mask > 0.5) {
    gl_FragColor = vec4(v_color.rgb, t.a * v_color.a);
  } else {
    gl_FragColor = vec4(t.rgb, t.a * v_color.a);
  }
}
"""


class RendererWebGL2(_GPURendererBase):
    kind = 'webgl2'

    def __init__(self, canvas, width, height):
        super().__init__(canvas, width, height)
        self.gl = None
        try:
            self.gl = canvas.getContext('webgl2')
        except Exception:
            self.gl = None
        if self.gl is None:
            raise RuntimeError('WebGL2 not available in this browser')
        gl = self.gl
        self._prog_solid = self._compile(_SOLID_VS, _SOLID_FS)
        self._prog_tex = self._compile(_TEX_VS, _TEX_FS)
        self._buf_solid = gl.createBuffer()
        self._buf_tex = gl.createBuffer()
        self._gl_textures = {}  # key -> WebGLTexture
        self._atlas_tex = None
        try:
            gl.enable(gl.BLEND)
            gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
            gl.disable(gl.DEPTH_TEST)
        except Exception:
            pass

    def _compile(self, vs_src, fs_src):
        gl = self.gl
        vs = gl.createShader(gl.VERTEX_SHADER)
        gl.shaderSource(vs, vs_src)
        gl.compileShader(vs)
        fs = gl.createShader(gl.FRAGMENT_SHADER)
        gl.shaderSource(fs, fs_src)
        gl.compileShader(fs)
        prog = gl.createProgram()
        gl.attachShader(prog, vs)
        gl.attachShader(prog, fs)
        gl.linkProgram(prog)
        return prog

    def _upload_texture(self, key, source, is_atlas=False):
        gl = self.gl
        tex = self._gl_textures.get(key)
        if tex is None:
            tex = gl.createTexture()
            self._gl_textures[key] = tex
        gl.bindTexture(gl.TEXTURE_2D, tex)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
        try:
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA,
                          gl.UNSIGNED_BYTE, source)
        except Exception:
            pass
        return tex

    def _draw_buffer(self, prog, buf, data, stride, with_uv):
        if not data:
            return
        gl = self.gl
        gl.useProgram(prog)
        gl.bindBuffer(gl.ARRAY_BUFFER, buf)
        try:
            gl.bufferData(gl.ARRAY_BUFFER, window.Float32Array.new(data),
                          gl.DYNAMIC_DRAW)
        except Exception:
            return
        loc_res = gl.getUniformLocation(prog, 'u_res')
        gl.uniform2f(loc_res, float(self.width), float(self.height))
        a_pos = gl.getAttribLocation(prog, 'a_pos')
        gl.enableVertexAttribArray(a_pos)
        gl.vertexAttribPointer(a_pos, 2, gl.FLOAT, False, stride * 4, 0)
        if with_uv:
            a_uv = gl.getAttribLocation(prog, 'a_uv')
            gl.enableVertexAttribArray(a_uv)
            gl.vertexAttribPointer(a_uv, 2, gl.FLOAT, False, stride * 4, 2 * 4)
            a_col = gl.getAttribLocation(prog, 'a_color')
            gl.enableVertexAttribArray(a_col)
            gl.vertexAttribPointer(a_col, 4, gl.FLOAT, False, stride * 4, 4 * 4)
        else:
            a_col = gl.getAttribLocation(prog, 'a_color')
            gl.enableVertexAttribArray(a_col)
            gl.vertexAttribPointer(a_col, 4, gl.FLOAT, False, stride * 4, 2 * 4)
        gl.drawArrays(gl.TRIANGLES, 0, len(data) // stride)

    def _submit(self):
        gl = self.gl
        try:
            gl.viewport(0, 0, int(self.width * self.dpr), int(self.height * self.dpr))
            r, g, b, a = self._bg
            gl.clearColor(r, g, b, a)
            gl.clear(gl.COLOR_BUFFER_BIT)
        except Exception:
            return
        self._draw_buffer(self._prog_solid, self._buf_solid, self._solid, 6, False)
        # Textured batches: atlas (mask) + one batch per image (RGBA).
        for key, data in list(self._tex_batches.items()):
            if not data:
                continue
            if key == ('atlas',):
                if self.atlas.canvas is None:
                    continue
                if self.atlas.dirty:
                    self._upload_texture(key, self.atlas.canvas)
                    self.atlas.dirty = False
                else:
                    gl.bindTexture(gl.TEXTURE_2D, self._gl_textures.get(key))
                gl.useProgram(self._prog_tex)
                gl.uniform1f(gl.getUniformLocation(self._prog_tex, 'u_mask'), 1.0)
                gl.activeTexture(gl.TEXTURE0)
                gl.bindTexture(gl.TEXTURE_2D, self._gl_textures.get(key))
                gl.uniform1i(gl.getUniformLocation(self._prog_tex, 'u_tex'), 0)
            else:
                img = self._images.get(key[1])
                if img is None:
                    continue
                self._upload_texture(key, img)
                gl.useProgram(self._prog_tex)
                gl.uniform1f(gl.getUniformLocation(self._prog_tex, 'u_mask'), 0.0)
                gl.activeTexture(gl.TEXTURE0)
                gl.bindTexture(gl.TEXTURE_2D, self._gl_textures.get(key))
                gl.uniform1i(gl.getUniformLocation(self._prog_tex, 'u_tex'), 0)
            self._draw_buffer(self._prog_tex, self._buf_tex, data, 8, True)

    def destroy(self):
        self.gl = None
