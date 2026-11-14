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
    no silent downgrade, no projected-circle pretending to be 3D.

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
            return True
        except Exception as e:
            self.error = 'render failed: %s' % e
            return False

    def describe(self):
        return {'kind': self.kind, 'width': self.width,
                'height': self.height, 'scene_items': len(self.scene),
                'has_context': self.gl is not None, 'error': self.error}
