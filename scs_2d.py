"""
scs_2d.py - SCS Canvas2D renderer (the reference backend).

Implements exactly the same draw_* method signatures as the GPU
renderers in scs_webgl.py / scs_webgpu.py, on top of
CanvasRenderingContext2D. This is the behavioural ground truth:
where a GPU backend and this file disagree, this file wins and the
GPU backend is the bug (see RENDERER_SUPPORT.md).

DPR: the entrypoint sizes the canvas backing store to width*dpr and
sets style width to width px. This renderer sets ctx.setTransform(dpr,...)
each frame so user coordinates stay in CSS pixels.
"""

import math

try:
    from browser import window
except ImportError:
    window = None


class Renderer2D:
    kind = '2d'

    def __init__(self, canvas, width, height):
        self.canvas = canvas
        self.width = width
        self.height = height
        self.dpr = 1.0
        try:
            self.dpr = float(window.devicePixelRatio or 1.0)
        except Exception:
            pass
        self.ctx = None
        try:
            self.ctx = canvas.getContext('2d')
        except Exception:
            self.ctx = None
        if self.ctx is None:
            raise RuntimeError('Canvas 2D context not available')
        self._alpha_stack = [1.0]
        self._image_cache = {}

    # -- frame ------------------------------------------------------
    def resize(self, width, height):
        self.width, self.height = width, height

    def begin_frame(self, background):
        ctx = self.ctx
        ctx.setTransform(self.dpr, 0, 0, self.dpr, 0, 0)
        ctx.clearRect(0, 0, self.width, self.height)
        if background is not None:
            if isinstance(background, dict) and background.get('_is_grad'):
                grad = self._make_gradient(background, 0, 0, self.width, self.height)
                ctx.fillStyle = grad if grad is not None else background['colors'][0]
            else:
                ctx.fillStyle = background if isinstance(background, str) else str(background)
            ctx.fillRect(0, 0, self.width, self.height)
        self._alpha_stack = [1.0]

    def end_frame(self):
        pass

    def push_transform(self, cx, cy, angle_deg, alpha_mult):
        ctx = self.ctx
        ctx.save()
        if angle_deg:
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(angle_deg))
            ctx.translate(-cx, -cy)
        self._alpha_stack.append(self._alpha_stack[-1] * alpha_mult)

    def pop_transform(self):
        self.ctx.restore()
        if len(self._alpha_stack) > 1:
            self._alpha_stack.pop()

    @property
    def _alpha(self):
        return self._alpha_stack[-1]

    # -- helpers ----------------------------------------------------
    def _make_gradient(self, grad, left, top, w, h):
        """CanvasGradient for an SCS gradient dict over a bbox."""
        try:
            colors = grad.get('colors') or ['black']
            start = str(grad.get('start', 'top')).lower()
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
            x0, y0, x1, y1 = table.get(start, (cx, top, cx, top + h))
            g = self.ctx.createLinearGradient(x0, y0, x1, y1)
            for i, c in enumerate(colors):
                g.addColorStop(i / max(1, len(colors) - 1),
                               c if isinstance(c, str) else str(c))
            return g
        except Exception:
            return None

    def _apply_fill(self, fill, bbox):
        if isinstance(fill, dict) and fill.get('_is_grad'):
            g = self._make_gradient(fill, *bbox)
            self.ctx.fillStyle = g if g is not None else fill['colors'][0]
        elif fill is not None:
            self.ctx.fillStyle = fill if isinstance(fill, str) else str(fill)

    def _apply_stroke(self, border, borderWidth, dashes):
        self.ctx.strokeStyle = border if isinstance(border, str) else str(border)
        self.ctx.lineWidth = borderWidth
        try:
            self.ctx.setLineDash([6, 3] if dashes else [])
        except Exception:
            pass

    def _rotated(self, cx, cy, angle_deg):
        """Context manager-ish: caller must restore. Returns True."""
        if angle_deg:
            self.ctx.save()
            self.ctx.translate(cx, cy)
            self.ctx.rotate(math.radians(angle_deg))
            self.ctx.translate(-cx, -cy)
            return True
        return False

    # -- SCS draw API (identical signature on all three renderers) --
    def draw_rect(self, left, top, w, h, fill='black', border=None,
                  borderWidth=2, opacity=100, rotateAngle=0, dashes=False,
                  roundness=0):
        ctx = self.ctx
        ctx.save()
        try:
            ctx.globalAlpha = (opacity / 100.0) * self._alpha
            saved = self._rotated(left + w / 2, top + h / 2, rotateAngle)
            try:
                if roundness and roundness > 0:
                    r = min(roundness, min(w, h) / 2)
                    ctx.beginPath()
                    ctx.moveTo(left + r, top)
                    ctx.arcTo(left + w, top, left + w, top + h, r)
                    ctx.arcTo(left + w, top + h, left, top + h, r)
                    ctx.arcTo(left, top + h, left, top, r)
                    ctx.arcTo(left, top, left + w, top, r)
                    ctx.closePath()
                    if fill is not None:
                        self._apply_fill(fill, (left, top, w, h))
                        ctx.fill()
                    if border is not None:
                        self._apply_stroke(border, borderWidth, dashes)
                        ctx.stroke()
                else:
                    if fill is not None:
                        self._apply_fill(fill, (left, top, w, h))
                        ctx.fillRect(left, top, w, h)
                    if border is not None:
                        self._apply_stroke(border, borderWidth, dashes)
                        ctx.strokeRect(left, top, w, h)
            finally:
                if saved:
                    ctx.restore()
        finally:
            ctx.restore()

    def draw_oval(self, cx, cy, w, h, fill='black', border=None,
                  borderWidth=2, opacity=100, rotateAngle=0, dashes=False):
        ctx = self.ctx
        ctx.save()
        try:
            ctx.globalAlpha = (opacity / 100.0) * self._alpha
            saved = self._rotated(cx, cy, rotateAngle)
            try:
                ctx.beginPath()
                ctx.ellipse(cx, cy, w / 2, h / 2, 0, 0, 2 * math.pi)
                if fill is not None:
                    self._apply_fill(fill, (cx - w / 2, cy - h / 2, w, h))
                    ctx.fill()
                if border is not None:
                    self._apply_stroke(border, borderWidth, dashes)
                    ctx.stroke()
            finally:
                if saved:
                    ctx.restore()
        finally:
            ctx.restore()

    def draw_circle(self, cx, cy, radius, fill='black', border=None,
                    borderWidth=2, opacity=100, rotateAngle=0, dashes=False):
        ctx = self.ctx
        ctx.save()
        try:
            ctx.globalAlpha = (opacity / 100.0) * self._alpha
            saved = self._rotated(cx, cy, rotateAngle)
            try:
                ctx.beginPath()
                ctx.arc(cx, cy, radius, 0, 2 * math.pi)
                if fill is not None:
                    self._apply_fill(fill, (cx - radius, cy - radius, radius * 2, radius * 2))
                    ctx.fill()
                if border is not None:
                    self._apply_stroke(border, borderWidth, dashes)
                    ctx.stroke()
            finally:
                if saved:
                    ctx.restore()
        finally:
            ctx.restore()

    def draw_regular_polygon(self, cx, cy, radius, points, fill='black',
                             border=None, borderWidth=2, opacity=100,
                             rotateAngle=0, dashes=False):
        ctx = self.ctx
        ctx.save()
        try:
            ctx.globalAlpha = (opacity / 100.0) * self._alpha
            saved = self._rotated(cx, cy, rotateAngle)
            try:
                ctx.beginPath()
                for i in range(int(points)):
                    a = 2 * math.pi * i / points - math.pi / 2
                    px, py = cx + radius * math.cos(a), cy + radius * math.sin(a)
                    if i == 0:
                        ctx.moveTo(px, py)
                    else:
                        ctx.lineTo(px, py)
                ctx.closePath()
                if fill is not None:
                    self._apply_fill(fill, (cx - radius, cy - radius, radius * 2, radius * 2))
                    ctx.fill()
                if border is not None:
                    self._apply_stroke(border, borderWidth, dashes)
                    ctx.stroke()
            finally:
                if saved:
                    ctx.restore()
        finally:
            ctx.restore()

    def draw_star(self, cx, cy, radius, points, fill='black', border=None,
                  borderWidth=2, opacity=100, rotateAngle=0, dashes=False, ratio=0.5):
        ctx = self.ctx
        ctx.save()
        try:
            ctx.globalAlpha = (opacity / 100.0) * self._alpha
            saved = self._rotated(cx, cy, rotateAngle)
            try:
                ctx.beginPath()
                for i in range(int(points) * 2):
                    r = radius if i % 2 == 0 else radius * ratio
                    a = math.pi * i / points - math.pi / 2
                    px, py = cx + r * math.cos(a), cy + r * math.sin(a)
                    if i == 0:
                        ctx.moveTo(px, py)
                    else:
                        ctx.lineTo(px, py)
                ctx.closePath()
                if fill is not None:
                    self._apply_fill(fill, (cx - radius, cy - radius, radius * 2, radius * 2))
                    ctx.fill()
                if border is not None:
                    self._apply_stroke(border, borderWidth, dashes)
                    ctx.stroke()
            finally:
                if saved:
                    ctx.restore()
        finally:
            ctx.restore()

    def draw_arc(self, cx, cy, w, h, startAngle, sweepAngle, fill=None,
                 border=None, borderWidth=2, opacity=100, dashes=False):
        ctx = self.ctx
        ctx.save()
        try:
            ctx.globalAlpha = (opacity / 100.0) * self._alpha
            ctx.beginPath()
            start = math.radians(startAngle)
            end = math.radians(startAngle + sweepAngle)
            ctx.ellipse(cx, cy, w / 2, h / 2, 0, start, end)
            if fill is not None:
                self._apply_fill(fill, (cx - w / 2, cy - h / 2, w, h))
                ctx.fill()
            if border is not None:
                self._apply_stroke(border, borderWidth, dashes)
                ctx.stroke()
        finally:
            ctx.restore()

    def draw_polygon(self, points, fill='black', border=None, borderWidth=2,
                     opacity=100, rotateAngle=0, dashes=False):
        if len(points) < 4:
            return
        ctx = self.ctx
        ctx.save()
        try:
            ctx.globalAlpha = (opacity / 100.0) * self._alpha
            cx = sum(points[0::2]) / (len(points) // 2)
            cy = sum(points[1::2]) / (len(points) // 2)
            saved = self._rotated(cx, cy, rotateAngle)
            try:
                ctx.beginPath()
                ctx.moveTo(points[0], points[1])
                for i in range(2, len(points), 2):
                    ctx.lineTo(points[i], points[i + 1])
                ctx.closePath()
                if fill is not None:
                    xs, ys = points[0::2], points[1::2]
                    self._apply_fill(fill, (min(xs), min(ys),
                                            max(xs) - min(xs), max(ys) - min(ys)))
                    ctx.fill()
                if border is not None:
                    self._apply_stroke(border, borderWidth, dashes)
                    ctx.stroke()
            finally:
                if saved:
                    ctx.restore()
        finally:
            ctx.restore()

    def draw_line(self, x1, y1, x2, y2, fill='black', lineWidth=2,
                  opacity=100, dashes=False):
        ctx = self.ctx
        ctx.save()
        try:
            ctx.globalAlpha = (opacity / 100.0) * self._alpha
            ctx.strokeStyle = fill if fill else 'black'
            ctx.lineWidth = lineWidth
            try:
                ctx.setLineDash([6, 3] if dashes else [])
            except Exception:
                pass
            ctx.beginPath()
            ctx.moveTo(x1, y1)
            ctx.lineTo(x2, y2)
            ctx.stroke()
        finally:
            ctx.restore()

    def draw_label(self, text, x, y, fill='black', size=12, font='arial',
                   bold=False, italic=False, opacity=100, align='center',
                   rotateAngle=0):
        ctx = self.ctx
        ctx.save()
        try:
            ctx.globalAlpha = (opacity / 100.0) * self._alpha
            ctx.fillStyle = fill if fill else 'black'
            style = ('italic ' if italic else '') + ('bold ' if bold else '')
            ctx.font = '%s%dpx %s' % (style, size, font)
            a = str(align).lower()
            ctx.textAlign = 'left' if 'left' in a else ('right' if 'right' in a else 'center')
            ctx.textBaseline = 'top' if 'top' in a else ('bottom' if 'bottom' in a else 'middle')
            saved = self._rotated(x, y, rotateAngle)
            try:
                ctx.fillText(str(text), x, y)
            finally:
                if saved:
                    ctx.restore()
        finally:
            ctx.restore()

    def draw_image(self, path, left, top, w, h, opacity=100, rotateAngle=0):
        ctx = self.ctx
        img = self._image_cache.get(path)
        if img is None:
            try:
                img = window.Image.new()
                img.src = path
                self._image_cache[path] = img
            except Exception:
                return
        ctx.save()
        try:
            ctx.globalAlpha = (opacity / 100.0) * self._alpha
            saved = self._rotated(left + w / 2, top + h / 2, rotateAngle)
            try:
                try:
                    ctx.drawImage(img, left, top, w, h)
                except Exception:
                    pass
            finally:
                if saved:
                    ctx.restore()
        finally:
            ctx.restore()

    def destroy(self):
        self.ctx = None
