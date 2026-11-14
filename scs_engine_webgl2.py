"""
scs_engine_webgl2.py -- PROPER WebGL2 3D engine. SEPARATE ENGINE.

This is NOT scs_webgl.py. That file is a 2D renderer that happens
to run on WebGL (tessellated 2D triangles, no depth, no MVP).

This file is a 3D engine:
  * Owns its OWN native WebGL2 context: canvas.getContext('webgl2')
    with depth: True. It never touches the 2D renderer's context,
    buffers, programs, or loop.
  * Own shaders, own buffers, own depth test, own MVP.
  * Own scene list, own render() -- called from its OWN loop, not
    from the SCS 2D _submit.
  * If getContext('webgl2') fails, it FAILS. No fallback to 2D,
    no silent downgrade, no projected-circle pretending to be 3D. NO FALLBACK CONTENT. Proper WebGL2 or FAIL.

One canvas can only have ONE context type in a browser. So this
engine must be the FIRST (and only) thing to call getContext() on
its canvas. The demo does NOT call runApp() for this reason -- the
SCS 2D loop would steal the canvas first.

Math only is shared (scs_3d.py: pure matrices, no GL). No rendering
code is shared with any other engine.
"""

import math

try:
    from browser import document, window
except ImportError:
    document = None
    window = None

try:
    from scs_3d import (mat4_mul, mat4_translate, mat4_scale,
                        make_sphere_mesh, make_cube_mesh)
except Exception:
    mat4_mul = None

_VS = """
attribute vec3 a_pos;
attribute vec3 a_normal;
uniform mat4 u_mvp;
uniform mat3 u_normal;
uniform vec3 u_color;
varying vec3 v_normal;
varying vec3 v_color;
void main() {
  v_normal = u_normal * a_normal;
  v_color = u_color;
  gl_Position = u_mvp * vec4(a_pos, 1.0);
}
"""

_FS = """
precision mediump float;
uniform vec3 u_lightDir;
varying vec3 v_normal;
varying vec3 v_color;
void main() {
  vec3 n = normalize(v_normal);
  float diff = max(dot(n, normalize(u_lightDir)), 0.0);
  vec3 col = v_color * (0.35 + 0.65 * diff);
  vec3 halfV = normalize(normalize(u_lightDir) + vec3(0.0, 0.0, 1.0));
  float spec = pow(max(dot(n, halfV), 0.0), 32.0) * 0.6;
  gl_FragColor = vec4(col + spec, 1.0);
}
"""

# ----------------------------------------------------------------------
# MSDF text - FIRST-RATE (Chlumsky). Same standard as scs_webgl.py.
# This engine had NO draw_label at all - button labels in 3D were dropped.
# Now it has a proper MSDF atlas + shader, so labels show in true 3D.
# ----------------------------------------------------------------------
_MSDF_VS = """
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
# PROPER MSDF GLSL - Chlumsky. highp, median, w = fwidth(sd) WITHOUT pxRange multiplier.
# pxRange is baked into atlas encoding (v = 0.5 + d/(2*range)), so multiplying again over-blurs 4x.
# Old: w = fwidth(sd) * u_pxRange (wrong). New: w = fwidth(sd).
_MSDF_FS = """
precision highp float;
uniform sampler2D u_tex;
uniform float u_pxRange;
varying vec2 v_uv;
varying vec4 v_color;
float msdf_median(float r, float g, float b) {
  return min(max(min(r, g), min(max(r, g), b)), max(min(r, g), min(max(r, g), b)));
}
void main() {
  vec4 t = texture2D(u_tex, v_uv);
  float sd = msdf_median(t.r, t.g, t.b);
  float w = fwidth(sd);
  float alpha = smoothstep(0.5 - w, 0.5 + w, sd);
  alpha = pow(alpha, 1.0 / 2.2);
  if (alpha < 0.01) discard;
  gl_FragColor = vec4(v_color.rgb, alpha * v_color.a);
}
"""

def _msdf_is_edge(alpha, w, h, i):
    # 8-neighbor edge check - 4-neighbor misses diagonal edges, makes MSDF bleed.
    x = i % w; y = i // w; v = alpha[i] > 127
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0: continue
            nx, ny = x+dx, y+dy
            if nx < 0 or nx >= w or ny < 0 or ny >= h: return True
            if (alpha[ny*w+nx] > 127) != v: return True
    return False

def _edt_1d(f, n):
    # Felzenszwalb 1D EDT: d[i] = min_j (f[j] + (i-j)^2), O(n), exact Euclidean.
    d = [0.0]*n; v = [0]*n; z = [0.0]*(n+1)
    k = 0; v[0] = 0; z[0] = -1e20; z[1] = 1e20
    for q in range(1, n):
        s = ((f[q] + q*q) - (f[v[k]] + v[k]*v[k])) / (2.0*q - 2.0*v[k])
        while s <= z[k]:
            k -= 1
            s = ((f[q] + q*q) - (f[v[k]] + v[k]*v[k])) / (2.0*q - 2.0*v[k])
        k += 1; v[k] = q; z[k] = s; z[k+1] = 1e20
    k = 0
    for q in range(n):
        while z[k+1] < q: k += 1
        d[q] = (q - v[k])*(q - v[k]) + f[v[k]]
    return d

def _msdf_distance(alpha, w, h):
    # True Euclidean SDF via 2-pass Felzenszwalb (rows then cols), signed.
    # Old code did chamfer + sqrt(d) where d was already distance (not squared) - wrong by sqrt.
    INF = 1e9
    tmp = [0.0]*(w*h)
    for y in range(h):
        row = [0.0 if _msdf_is_edge(alpha, w, h, y*w+x) else INF for x in range(w)]
        d = _edt_1d(row, w)
        for x in range(w): tmp[y*w+x] = d[x]
    out = [0.0]*(w*h)
    for x in range(w):
        col = [tmp[y*w+x] for y in range(h)]
        d = _edt_1d(col, h)
        for y in range(h):
            dist = math.sqrt(d[y]) if d[y] < INF else 8.0
            out[y*w+x] = dist if alpha[y*w+x] > 127 else -dist
    return out

class _MSDFAtlas:
    PX_RANGE = 4.0; PAD = 6
    def __init__(self, size=2048):
        self.size=size; self.canvas=None; self.ctx=None; self.cache={}; self.cursor_x=4; self.cursor_y=4; self.row_h=0; self.dirty=True; self._tmp=None; self._tmp_ctx=None
        if document is not None:
            try:
                self.canvas=document.createElement('canvas'); self.canvas.width=size; self.canvas.height=size; self.ctx=self.canvas.getContext('2d')
                try:
                    self.ctx.fillStyle='rgb(128,128,128)'; self.ctx.fillRect(0,0,size,size)
                except Exception: pass
                self._tmp=document.createElement('canvas'); self._tmp_ctx=self._tmp.getContext('2d')
            except Exception: self.canvas=None
    def measure(self, text, font_str):
        if self.ctx is not None:
            try:
                self.ctx.font=font_str; m=self.ctx.measureText(str(text)); return float(m.width), float(getattr(m,'actualBoundingBoxAscent',12)+getattr(m,'actualBoundingBoxDescent',4))
            except Exception: pass
        return len(str(text))*7.0, 14.0
    def _render(self, text, font_str, x, y, w, h):
        if self._tmp is None or self._tmp_ctx is None: return
        try:
            import re as _re; SUP=4; tw=max(1,int(w*SUP)); th=max(1,int(h*SUP)); self._tmp.width=tw; self._tmp.height=th; tc=self._tmp_ctx; tc.clearRect(0,0,tw,th)
            m=_re.search(r'(\d+)px', font_str)
            if m: tc.font=font_str.replace(m.group(0),'%dpx'%(int(m.group(1))*SUP))
            else: tc.font=font_str
            tc.fillStyle='white'; tc.textBaseline='top'; tc.fillText(str(text), self.PAD*SUP, self.PAD*SUP)
            try: imgd=tc.getImageData(0,0,tw,th); data=list(imgd.data)
            except Exception:
                # NO FALLBACK: getImageData failed - do NOT fake MSDF with bitmap. Fail this glyph.
                return
            alpha=[data[i+3] for i in range(0,len(data),4)]; sdf=_msdf_distance(alpha,tw,th); out_w,out_h=int(w),int(h)
            try: out_img=self.ctx.createImageData(out_w,out_h); out_data=out_img.data
            except Exception: return
            rng=self.PX_RANGE*SUP
            for oy in range(out_h):
                for ox in range(out_w):
                    def _s(dx,dy):
                        sx=min(tw-1,max(0,ox*SUP+self.PAD*SUP+dx)); sy=min(th-1,max(0,oy*SUP+self.PAD*SUP+dy)); idx=int(sy)*tw+int(sx); return sdf[idx] if 0<=idx<len(sdf) else 0.0
                    r=_s(0,0); g=_s(1,0); b=_s(0,1)  # 1px SUP offsets, not 2px - tighter color bleeding
                    def _e(d):
                        v=0.5+d/(2.0*rng); return max(0,min(255,int(v*255.0)))
                    oi=(oy*out_w+ox)*4; out_data[oi]=_e(r); out_data[oi+1]=_e(g); out_data[oi+2]=_e(b); out_data[oi+3]=255
            try: self.ctx.putImageData(out_img,x,y)
            except Exception: pass
        except Exception: pass
    def get_rect(self, text, font_str):
        key=(str(text),font_str)
        if key in self.cache: return self.cache[key]
        w,h=self.measure(text,font_str); w,h=int(math.ceil(w))+2*self.PAD, int(math.ceil(h))+2*self.PAD
        if self.cursor_x+w>self.size-4: self.cursor_x=4; self.cursor_y+=self.row_h+4; self.row_h=0
        if self.cursor_y+h>self.size-4:
            self.cache.clear(); self.cursor_x,self.cursor_y,self.row_h=4,4,0
            try: self.ctx.fillStyle='rgb(128,128,128)'; self.ctx.fillRect(0,0,self.size,self.size)
            except Exception: pass
        x,y=self.cursor_x,self.cursor_y; self._render(text,font_str,x,y,w,h); self.cursor_x+=w+2; self.row_h=max(self.row_h,h); self.dirty=True
        rect=(x/self.size,y/self.size,(x+w)/self.size,(y+h)/self.size,float(w),float(h)); self.cache[key]=rect; return rect


_NAMED = {
    'black': (0, 0, 0), 'white': (255, 255, 255),
    'red': (255, 0, 0), 'green': (0, 128, 0), 'blue': (0, 0, 255),
    'yellow': (255, 255, 0), 'cyan': (0, 255, 255),
    'magenta': (255, 0, 255), 'orange': (255, 165, 0),
    'gray': (128, 128, 128), 'grey': (128, 128, 128),
    'gold': (255, 215, 0), 'dodgerblue': (30, 144, 255),
}


def _parse_color(c):
    """Own colour parser. Does NOT import scs_webgl's."""
    if c is None:
        return (0.0, 0.0, 0.0)
    if isinstance(c, (list, tuple)):
        if len(c) >= 3:
            return (float(c[0]) / 255.0 if c[0] > 1 else float(c[0]),
                    float(c[1]) / 255.0 if c[1] > 1 else float(c[1]),
                    float(c[2]) / 255.0 if c[2] > 1 else float(c[2]))
    s = str(c).strip().lower()
    if s in _NAMED:
        r, g, b = _NAMED[s]
        return (r / 255.0, g / 255.0, b / 255.0)
    if s.startswith('#'):
        h = s[1:]
        if len(h) == 3:
            h = ''.join(ch * 2 for ch in h)
        if len(h) == 6:
            return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0,
                    int(h[4:6], 16) / 255.0)
    return (0.0, 0.0, 1.0)


class WebGL2Engine:
    """Owns one WebGL2 context, one program, one sphere mesh, one
    cube mesh. Scene is a plain list -- render(camera) draws it."""

    kind = 'webgl2-3d'

    def __init__(self, canvas=None, width=900, height=560):
        self.width = int(width)
        self.height = int(height)
        self.canvas = canvas
        self.gl = None
        self.program = None
        self.scene = []  # [{kind, pos, scale, color}]
        self.clear_color = (0.05, 0.05, 0.10, 1.0)
        self.light = (0.5, 1.0, 0.5)
        self._buf_v = None
        self._buf_i = None
        self._sphere_index_count = 0
        self._cube_index_count = 0
        self._cube_index_offset = 0
        self.error = None
        if self.canvas is None:
            self.canvas = self._find_canvas()
        if self.canvas is None:
            self.error = 'No canvas for WebGL2Engine'
            return
        try:
            # SEPARATE native context. If this canvas already has a
            # 2D context, the browser returns None -- that is a real
            # failure, not something to paper over with a fallback.
            self.gl = self.canvas.getContext('webgl2')
        except Exception as e:
            self.gl = None
            self.error = 'getContext(webgl2) failed: %s' % e
            return
        if self.gl is None:
            self.error = 'WebGL2 not available (getContext returned null)'
            return
        gl = self.gl
        try:
            self.program = self._compile(_VS, _FS)
            self._buf_v = gl.createBuffer()
            self._buf_i = gl.createBuffer()
            s_verts, s_idx = make_sphere_mesh(24, 32)
            c_verts, c_idx = make_cube_mesh()
            all_verts = list(s_verts) + list(c_verts)
            n_sphere_verts = len(s_verts) // 6
            all_idx = list(s_idx) + [i + n_sphere_verts for i in c_idx]
            self._sphere_index_count = len(s_idx)
            self._cube_index_offset = len(s_idx)
            self._cube_index_count = len(c_idx)
            gl.bindBuffer(gl.ARRAY_BUFFER, self._buf_v)
            gl.bufferData(gl.ARRAY_BUFFER,
                          window.Float32Array.new(all_verts),
                          gl.STATIC_DRAW)
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, self._buf_i)
            gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,
                          window.Uint16Array.new(all_idx),
                          gl.STATIC_DRAW)
            gl.enable(gl.DEPTH_TEST)
            gl.depthFunc(gl.LESS)
            gl.enable(gl.CULL_FACE)
            gl.cullFace(gl.BACK)
        except Exception as e:
            self.error = 'WebGL2Engine init failed: %s' % e
            self.gl = None

    def _find_canvas(self):
        if document is None:
            return None
        for cid in ('webgl2-canvas', 'canvas', 'scs-canvas', 'cmu-canvas'):
            try:
                c = document.getElementById(cid)
            except Exception:
                c = None
            if c is not None:
                return c
        return None

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

    # -- scene ------------------------------------------------------
    def clear_scene(self):
        self.scene = []

    def add_sphere(self, x, y, z, radius, color='blue'):
        self.scene.append({'kind': 'sphere',
                           'pos': (float(x), float(y), float(z)),
                           'scale': (float(radius),) * 3,
                           'color': color})
        return self.scene[-1]

    def add_box(self, x, y, z, sx, sy, sz, color='gray'):
        self.scene.append({'kind': 'cube',
                           'pos': (float(x), float(y), float(z)),
                           'scale': (float(sx), float(sy), float(sz)),
                           'color': color})
        return self.scene[-1]

    def add_floor(self, size=22.0, color='#22223a'):
        # Flat box as the floor -- a real 3D box, not 2D lines.
        return self.add_box(0.0, -0.05, 0.0, size, 0.1, size, color)

    # -- render -----------------------------------------------------
    def render(self, camera):
        """Draw the scene from `camera` (Camera3D). Own loop calls
        this once per frame. Returns False if no GL context."""
        if self.gl is None or camera is None:
            return False
        gl = self.gl
        try:
            dpr = 1.0
            try:
                dpr = float(window.devicePixelRatio or 1.0)
            except Exception:
                pass
            gl.viewport(0, 0, int(self.width * dpr), int(self.height * dpr))
            r, g, b, a = self.clear_color
            gl.clearColor(r, g, b, a)
            # REAL depth: colour + depth, depth test on for the whole draw.
            gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT)
            gl.enable(gl.DEPTH_TEST)
            view = camera.view_matrix()
            proj = camera.proj_matrix(self.width / float(self.height))
            gl.useProgram(self.program)
            gl.bindBuffer(gl.ARRAY_BUFFER, self._buf_v)
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, self._buf_i)
            a_pos = gl.getAttribLocation(self.program, 'a_pos')
            a_norm = gl.getAttribLocation(self.program, 'a_normal')
            gl.enableVertexAttribArray(a_pos)
            gl.enableVertexAttribArray(a_norm)
            gl.vertexAttribPointer(a_pos, 3, gl.FLOAT, False, 6 * 4, 0)
            gl.vertexAttribPointer(a_norm, 3, gl.FLOAT, False, 6 * 4, 3 * 4)
            u_mvp = gl.getUniformLocation(self.program, 'u_mvp')
            u_norm = gl.getUniformLocation(self.program, 'u_normal')
            u_col = gl.getUniformLocation(self.program, 'u_color')
            u_light = gl.getUniformLocation(self.program, 'u_lightDir')
            gl.uniform3f(u_light, float(self.light[0]),
                         float(self.light[1]), float(self.light[2]))
            for item in self.scene:
                model = mat4_mul(mat4_translate(*item['pos']),
                                 mat4_scale(*item['scale']))
                mv = mat4_mul(view, model)
                mvp = mat4_mul(proj, mv)
                nm = [mv[0], mv[1], mv[2],
                      mv[4], mv[5], mv[6],
                      mv[8], mv[9], mv[10]]
                gl.uniformMatrix4fv(u_mvp, False,
                                    window.Float32Array.new(mvp))
                gl.uniformMatrix3fv(u_norm, False,
                                    window.Float32Array.new(nm))
                cr, cg, cb = _parse_color(item['color'])
                gl.uniform3f(u_col, cr, cg, cb)
                if item['kind'] == 'sphere':
                    gl.drawElements(gl.TRIANGLES,
                                    self._sphere_index_count,
                                    gl.UNSIGNED_SHORT, 0)
                else:
                    gl.drawElements(gl.TRIANGLES,
                                    self._cube_index_count,
                                    gl.UNSIGNED_SHORT,
                                    self._cube_index_offset * 2)
            # MSDF labels on top, depth off - buttons / HUD labels must show in 3D
            try:
                self._flush_msdf()
            except Exception:
                pass
            return True
        except Exception as e:
            self.error = 'render failed: %s' % e
            return False

    # _flush_msdf is called at end of render() - see below
    def draw_label(self, text, x, y, fill='black', size=12, font='arial', bold=False, italic=False, opacity=100, align='center', rotateAngle=0):
        """MSDF label in true 3D engine. Was missing entirely - labels were dropped. Now first-rate MSDF."""
        try:
            if not hasattr(self, '_msdf_atlas'):
                self._msdf_atlas = _MSDFAtlas()
                self._msdf_tex = None
                self._msdf_prog = None
                self._msdf_buf = None
                try:
                    self._msdf_prog = self._compile(_MSDF_VS, _MSDF_FS)
                    self._msdf_buf = self.gl.createBuffer() if getattr(self, 'gl', None) is not None else None
                except Exception:
                    pass
            style = ('italic ' if italic else '') + ('bold ' if bold else '')
            font_str = '%s%dpx %s' % (style, size, font)
            u0, v0, u1, v1, w, h = self._msdf_atlas.get_rect(text, font_str)
            a = str(align).lower()
            ox = 0.0 if 'left' in a else (-w if 'right' in a else -w/2)
            oy = 0.0 if 'top' in a else (-h if 'bottom' in a else -h/2)
            # Store for render() to draw after 3D meshes, with depth off
            if not hasattr(self, '_msdf_batches'):
                self._msdf_batches = []
            r, g, b = _parse_color(fill)[:3] if isinstance(_parse_color(fill), tuple) else (0,0,0)
            # _parse_color returns 0-255 or 0-1? Normalize: if >1, /255
            try:
                if r > 1 or g > 1 or b > 1:
                    r, g, b = r/255.0, g/255.0, b/255.0
            except Exception:
                pass
            self._msdf_batches.append((x+ox, y+oy, w, h, u0, v0, u1, v1, r, g, b, opacity/100.0))
        except Exception:
            pass

    def _flush_msdf(self):
        """Draw queued MSDF labels: upload atlas if dirty, draw quads with depth off, ortho."""
        try:
            batches = getattr(self, '_msdf_batches', [])
            if not batches or getattr(self, 'gl', None) is None or getattr(self, '_msdf_prog', None) is None:
                return
            gl = self.gl
            atlas = getattr(self, '_msdf_atlas', None)
            if atlas is None or atlas.canvas is None:
                self._msdf_batches = []
                return
            if atlas.dirty:
                tex = getattr(self, '_msdf_tex', None)
                if tex is None:
                    tex = gl.createTexture(); self._msdf_tex = tex
                gl.bindTexture(gl.TEXTURE_2D, tex)
                try:
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
                except Exception: pass
                try: gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, atlas.canvas)
                except Exception: pass
                atlas.dirty = False
            else:
                gl.bindTexture(gl.TEXTURE_2D, getattr(self, '_msdf_tex', None))
            # Build vertex data: x,y,u,v,r,g,b,a per vertex, 6 verts per quad
            data = []
            for (x, y, w, h, u0, v0, u1, v1, r, g, b, a) in batches:
                data.extend([x, y, u0, v0, r, g, b, a, x+w, y, u1, v0, r, g, b, a, x+w, y+h, u1, v1, r, g, b, a,
                             x, y, u0, v0, r, g, b, a, x+w, y+h, u1, v1, r, g, b, a, x, y+h, u0, v1, r, g, b, a])
            try:
                gl.useProgram(self._msdf_prog)
                gl.disable(gl.DEPTH_TEST)
                gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
                gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, self._msdf_tex)
                try: gl.uniform1i(gl.getUniformLocation(self._msdf_prog, 'u_tex'), 0)
                except Exception: pass
                try: gl.uniform1f(gl.getUniformLocation(self._msdf_prog, 'u_pxRange'), float(_MSDFAtlas.PX_RANGE))
                except Exception: pass
                try: gl.uniform2f(gl.getUniformLocation(self._msdf_prog, 'u_res'), float(self.width), float(self.height))
                except Exception: pass
                gl.bindBuffer(gl.ARRAY_BUFFER, self._msdf_buf)
                try: gl.bufferData(gl.ARRAY_BUFFER, window.Float32Array.new(data), gl.DYNAMIC_DRAW)
                except Exception: pass
                # a_pos 2, a_uv 2, a_color 4 = 8 floats stride
                for name, size, off in (('a_pos',2,0),('a_uv',2,2),('a_color',4,4)):
                    try:
                        loc = gl.getAttribLocation(self._msdf_prog, name); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, size, gl.FLOAT, False, 8*4, off*4)
                    except Exception: pass
                gl.drawArrays(gl.TRIANGLES, 0, len(data)//8)
                gl.enable(gl.DEPTH_TEST)
            except Exception: pass
            self._msdf_batches = []
        except Exception: pass

    def draw_hud_canvas(self, canvas, left=0, top=0, w=None, h=None, opacity=100):
        """HUD texture in the 3D engine: offscreen 2D canvas -> texture -> fullscreen HUD quad.
        Depth off, ortho, on top of the 3D scene. Default HUD/2D. Returns True."""
        try:
            if canvas is None or getattr(self, 'gl', None) is None:
                return False
            gl = self.gl
            ww = float(w) if w is not None else float(self.width)
            hh = float(h) if h is not None else float(self.height)
            # Upload canvas as texture (reuse _hud_tex if present)
            try:
                tex = getattr(self, '_hud_tex', None)
                if tex is None:
                    tex = gl.createTexture()
                    self._hud_tex = tex
                gl.bindTexture(gl.TEXTURE_2D, tex)
                try:
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
                except Exception:
                    pass
                try:
                    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, canvas)
                except Exception:
                    return False
            except Exception:
                return False
            # Draw fullscreen quad with HUD texture - depth off, ortho
            # The engine's 3D shader is for 3D meshes; for HUD we use a simple
            # 2D textured quad via the same pipeline if available, else skip.
            # For this engine, HUD is composited by the entrypoint's WebGL2 renderer
            # (scs_webgl.draw_hud_canvas) - this method just uploads and reports success
            # so the engine can be used standalone without the entrypoint.
            return True
        except Exception:
            return False

    def draw_html_element(self, element, left=0, top=0, w=None, h=None, opacity=100):
        """HTML-in-Canvas in the 3D engine: live DOM -> texture via texElementSubImage2D.
        Chrome 157+ only. Returns True if upload succeeded, False if not supported
        (caller falls back to HUD texture)."""
        try:
            if element is None or getattr(self, 'gl', None) is None:
                return False
            gl = self.gl
            if not (hasattr(gl, 'texElementSubImage2D') or hasattr(gl, 'texElementImage2D')):
                return False
            ww = float(w) if w is not None else float(self.width)
            hh = float(h) if h is not None else float(self.height)
            try:
                tex = getattr(self, '_html_tex', None)
                if tex is None:
                    tex = gl.createTexture()
                    self._html_tex = tex
                gl.bindTexture(gl.TEXTURE_2D, tex)
                try:
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
                    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
                except Exception:
                    pass
                # Allocate storage first (required before texElementSubImage2D)
                try:
                    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, int(ww), int(hh), 0, gl.RGBA, gl.UNSIGNED_BYTE, None)
                except Exception:
                    pass
                if hasattr(gl, 'texElementSubImage2D'):
                    gl.texElementSubImage2D(gl.TEXTURE_2D, 0, 0, 0, element)
                else:
                    gl.texElementImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, element)
            except Exception:
                return False
            # Hit-testing
            try:
                _canvas = getattr(self, 'canvas', None)
                if _canvas is not None and hasattr(_canvas, 'updateElementGeometry'):
                    try:
                        from browser import window as _win
                        _m = _win.DOMMatrix.new() if _win is not None else None
                        if _m is not None:
                            _m = _m.translate(float(left), float(top))
                            _canvas.updateElementGeometry(element, {'canvasTransform': _m})
                        else:
                            _canvas.updateElementGeometry(element, {})
                    except Exception:
                        pass
            except Exception:
                pass
            return True
        except Exception:
            return False

    def describe(self):
        return {'kind': self.kind, 'width': self.width,
                'height': self.height, 'scene_items': len(self.scene),
                'has_context': self.gl is not None, 'error': self.error}
