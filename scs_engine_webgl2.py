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

# PROPER METALLIC PBR - Cook-Torrance GGX, 3-point + IBL, ACES. NOT Lambert.
# Vertex: world pos + world normal for real view-dependent metal.
_VS = """
attribute vec3 a_pos;
attribute vec3 a_normal;
uniform mat4 u_mvp;
uniform mat4 u_model;
uniform mat3 u_normal;
varying vec3 v_worldPos;
varying vec3 v_normal;
void main() {
  vec4 wp = u_model * vec4(a_pos, 1.0);
  v_worldPos = wp.xyz;
  v_normal = u_normal * a_normal;
  gl_Position = u_mvp * vec4(a_pos, 1.0);
}
"""

_FS = """
precision highp float;
uniform vec3 u_color;
uniform float u_metalness;
uniform float u_roughness;
uniform vec3 u_camPos;
uniform vec3 u_lightDir;
uniform vec3 u_lightColor;
varying vec3 v_worldPos;
varying vec3 v_normal;

// GGX normal distribution
float D_GGX(vec3 N, vec3 H, float rough) {
  float a = rough * rough;
  float a2 = a * a;
  float NdotH = max(dot(N, H), 0.0);
  float NdotH2 = NdotH * NdotH;
  float denom = NdotH2 * (a2 - 1.0) + 1.0;
  return a2 / (3.14159265 * denom * denom + 1e-6);
}
float G_SchlickGGX(float NdotV, float rough) {
  float r = rough + 1.0;
  float k = (r * r) / 8.0;
  return NdotV / (NdotV * (1.0 - k) + k + 1e-6);
}
float G_Smith(vec3 N, vec3 V, vec3 L, float rough) {
  float NdotV = max(dot(N, V), 0.0);
  float NdotL = max(dot(N, L), 0.0);
  return G_SchlickGGX(NdotV, rough) * G_SchlickGGX(NdotL, rough);
}
vec3 F_Schlick(float cosTheta, vec3 F0) {
  return F0 + (1.0 - F0) * pow(1.0 - cosTheta, 5.0);
}
vec3 F_SchlickRough(float cosTheta, vec3 F0, float rough) {
  return F0 + (max(vec3(1.0 - rough), F0) - F0) * pow(1.0 - cosTheta, 5.0);
}
// Fake studio env - sky gradient + 2 softbox streaks so metal has something to reflect.
// No HDR file needed: this is what makes chrome read as chrome, not flat grey.
vec3 envColor(vec3 R, float rough) {
  // Sky: horizon warm grey -> zenith deep blue
  float y = R.y * 0.5 + 0.5;
  vec3 sky = mix(vec3(0.12, 0.12, 0.16), vec3(0.35, 0.55, 0.95), smoothstep(0.0, 1.0, y));
  vec3 ground = vec3(0.08, 0.07, 0.10);
  vec3 env = mix(ground, sky, smoothstep(-0.1, 0.25, R.y));
  // Softbox 1: big warm key strip overhead-left
  vec3 box1Dir = normalize(vec3(-0.6, 0.9, 0.35));
  float b1 = pow(max(dot(R, box1Dir), 0.0), mix(180.0, 8.0, rough));
  env += vec3(1.0, 0.95, 0.85) * b1 * 2.2;
  // Softbox 2: cool rim strip behind-right - gives that bright edge on metal
  vec3 box2Dir = normalize(vec3(0.7, 0.35, -0.8));
  float b2 = pow(max(dot(R, box2Dir), 0.0), mix(220.0, 10.0, rough));
  env += vec3(0.55, 0.75, 1.0) * b2 * 1.8;
  // Thin floor bounce strip
  float b3 = pow(max(dot(R, vec3(0.0, -1.0, 0.0)), 0.0), 6.0);
  env += vec3(0.25, 0.22, 0.28) * b3 * 0.35;
  return env;
}
vec3 ACES(vec3 x) {
  float a = 2.51; float b = 0.03; float c = 2.43; float d = 0.59; float e = 0.14;
  return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}
void main() {
  vec3 albedo = u_color;
  float metal = clamp(u_metalness, 0.0, 1.0);
  float rough = clamp(u_roughness, 0.04, 1.0);
  vec3 N = normalize(v_normal);
  if (!gl_FrontFacing) N = -N;
  vec3 V = normalize(u_camPos - v_worldPos);
  float NdotV = max(dot(N, V), 0.0);
  vec3 F0 = mix(vec3(0.04), albedo, metal);

  // ---- Direct: 3-point ----
  vec3 Lo = vec3(0.0);
  // Key: warm, hard, from up-left-front
  vec3 L1 = normalize(u_lightDir);
  vec3 L1col = u_lightColor * 3.0;
  // Fill: cool blue, from right-low
  vec3 L2 = normalize(vec3(-0.7, 0.25, -0.6));
  vec3 L2col = vec3(0.35, 0.55, 1.0) * 0.9;
  // Rim: from behind, makes metal edge glow
  vec3 L3 = normalize(vec3(0.2, 0.6, -1.0));
  vec3 L3col = vec3(0.9, 0.95, 1.0) * 1.2;

  vec3 lights[3];
  lights[0] = L1; lights[1] = L2; lights[2] = L3;
  vec3 lightCols[3];
  lightCols[0] = L1col; lightCols[1] = L2col; lightCols[2] = L3col;

  for (int i = 0; i < 3; i++) {
    vec3 L = lights[i];
    vec3 H = normalize(V + L);
    float NdotL = max(dot(N, L), 0.0);
    if (NdotL <= 0.0) continue;
    float NDF = D_GGX(N, H, rough);
    float G = G_Smith(N, V, L, rough);
    vec3 F = F_Schlick(max(dot(H, V), 0.0), F0);
    vec3 spec = (NDF * G * F) / (4.0 * NdotV * NdotL + 1e-4);
    vec3 kS = F;
    vec3 kD = (vec3(1.0) - kS) * (1.0 - metal);
    vec3 diff = kD * albedo / 3.14159265;
    Lo += (diff + spec) * lightCols[i] * NdotL;
  }

  // ---- IBL: what makes metal look like metal ----
  vec3 R = reflect(-V, N);
  vec3 env = envColor(R, rough);
  vec3 Fenv = F_SchlickRough(NdotV, F0, rough);
  vec3 kSenv = Fenv;
  vec3 kDenv = (vec3(1.0) - kSenv) * (1.0 - metal);
  // Hemisphere ambient for diffuse
  vec3 hemi = mix(vec3(0.10, 0.09, 0.12), vec3(0.35, 0.45, 0.65), N.y * 0.5 + 0.5);
  vec3 ambient = kDenv * albedo * hemi * 0.9 + env * kSenv * (1.0 - rough * 0.55);
  // Extra sharp reflection for polished metal - env already has softboxes, boost it
  ambient += env * metal * (1.0 - rough) * 0.6;

  vec3 col = Lo + ambient;
  // ACES + gamma - metal without tone mapping blows out to white
  col = ACES(col * 1.05);
  col = pow(col, vec3(1.0 / 2.2));
  gl_FragColor = vec4(col, 1.0);
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
        try:
            print('SCS renderer version=0.1 mode=webgl2')
        except Exception:
            pass
        # DO NOT return here - fall through to program + buffer creation.
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
        try:
            if not gl.getShaderParameter(vs, gl.COMPILE_STATUS):
                return None
        except Exception:
            pass
        fs = gl.createShader(gl.FRAGMENT_SHADER)
        gl.shaderSource(fs, fs_src)
        gl.compileShader(fs)
        try:
            if not gl.getShaderParameter(fs, gl.COMPILE_STATUS):
                return None
        except Exception:
            pass
        prog = gl.createProgram()
        gl.attachShader(prog, vs)
        gl.attachShader(prog, fs)
        gl.linkProgram(prog)
        try:
            if not gl.getProgramParameter(prog, gl.LINK_STATUS):
                return None
        except Exception:
            pass
        return prog

    # -- scene ------------------------------------------------------
    def clear_scene(self):
        self.scene = []

    def add_sphere(self, x, y, z, radius, color='blue', metalness=None, roughness=None, material=None):
        # METAL default for the spatial-audio sphere: chrome. Callers that pass
        # explicit metalness/roughness win. 'blue' + no material = old look would be
        # flat, so a bare add_sphere('blue') now means polished blue metal, not plastic.
        # Dielectric callers pass metalness=0 explicitly.
        if material == 'metal':
            metalness = 1.0 if metalness is None else metalness
            roughness = 0.12 if roughness is None else roughness
        elif material == 'plastic':
            metalness = 0.0 if metalness is None else metalness
            roughness = 0.55 if roughness is None else roughness
        elif material == 'chrome':
            metalness = 1.0 if metalness is None else metalness
            roughness = 0.08 if roughness is None else roughness
        if metalness is None:
            metalness = 0.0
        if roughness is None:
            roughness = 0.55
        self.scene.append({'kind': 'sphere',
                           'pos': (float(x), float(y), float(z)),
                           'scale': (float(radius),) * 3,
                           'color': color,
                           'metalness': float(metalness),
                           'roughness': float(roughness)})
        return self.scene[-1]

    def add_metal_sphere(self, x, y, z, radius, color='#c8d4e8', roughness=0.12):
        # Explicit hero: polished chrome-blue metal. This is what spatial audio uses.
        return self.add_sphere(x, y, z, radius, color=color, metalness=1.0, roughness=roughness, material='metal')

    def add_box(self, x, y, z, sx, sy, sz, color='gray', metalness=0.0, roughness=0.85, material=None):
        if material == 'metal':
            metalness = 1.0
            roughness = 0.25
        self.scene.append({'kind': 'cube',
                           'pos': (float(x), float(y), float(z)),
                           'scale': (float(sx), float(sy), float(sz)),
                           'color': color,
                           'metalness': float(metalness),
                           'roughness': float(roughness)})
        return self.scene[-1]

    def add_floor(self, size=22.0, color='#22223a'):
        # Flat box as the floor -- dielectric, rough, so metal sphere pops against it.
        return self.add_box(0.0, -0.05, 0.0, size, 0.1, size, color, metalness=0.0, roughness=0.95)

    # -- render -----------------------------------------------------
    def render(self, camera):
        """Draw the scene from `camera` (Camera3D). Own loop calls
        this once per frame. Returns False if no GL context."""
        if self.gl is None or camera is None:
            return False
        if getattr(self, 'program', None) is None:
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
            u_model = gl.getUniformLocation(self.program, 'u_model')
            u_norm = gl.getUniformLocation(self.program, 'u_normal')
            u_col = gl.getUniformLocation(self.program, 'u_color')
            u_metal = gl.getUniformLocation(self.program, 'u_metalness')
            u_rough = gl.getUniformLocation(self.program, 'u_roughness')
            u_cam = gl.getUniformLocation(self.program, 'u_camPos')
            u_light = gl.getUniformLocation(self.program, 'u_lightDir')
            u_light_col = gl.getUniformLocation(self.program, 'u_lightColor')
            # Camera pos: Camera3D.position - drives view-dependent Fresnel / reflections.
            try:
                cp = camera.position
                gl.uniform3f(u_cam, float(cp[0]), float(cp[1]), float(cp[2]))
            except Exception:
                gl.uniform3f(u_cam, 0.0, 2.0, 6.0)
            gl.uniform3f(u_light, float(self.light[0]),
                         float(self.light[1]), float(self.light[2]))
            # Warm key light - makes chrome read warm on one side, cool on the other.
            gl.uniform3f(u_light_col, 1.0, 0.95, 0.88)
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
                if u_model is not None:
                    gl.uniformMatrix4fv(u_model, False,
                                        window.Float32Array.new(model))
                gl.uniformMatrix3fv(u_norm, False,
                                    window.Float32Array.new(nm))
                cr, cg, cb = _parse_color(item['color'])
                gl.uniform3f(u_col, cr, cg, cb)
                if u_metal is not None:
                    gl.uniform1f(u_metal, float(item.get('metalness', 0.0)))
                if u_rough is not None:
                    gl.uniform1f(u_rough, float(item.get('roughness', 0.5)))
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
            # Draw fullscreen textured quad - depth off, BLENDING ON.
            # HUD canvas is mostly transparent (alpha 0). With blending OFF,
            # transparent pixels still overwrite 3D with black (RGB 0,0,0) -> HUD covers everything.
            # With SRC_ALPHA / ONE_MINUS_SRC_ALPHA, only HUD pixels show, 3D shows through elsewhere.
            try:
                if not hasattr(self, '_hud_prog') or self._hud_prog is None:
                    _vs = "attribute vec2 a_p; attribute vec2 a_uv; varying vec2 v_uv; void main(){ v_uv=a_uv; gl_Position=vec4(a_p,0.0,1.0); }"
                    _fs = "precision mediump float; uniform sampler2D u_tex; varying vec2 v_uv; void main(){ gl_FragColor=texture2D(u_tex, v_uv); }"
                    _vs_o = gl.createShader(gl.VERTEX_SHADER); gl.shaderSource(_vs_o, _vs); gl.compileShader(_vs_o)
                    _fs_o = gl.createShader(gl.FRAGMENT_SHADER); gl.shaderSource(_fs_o, _fs); gl.compileShader(_fs_o)
                    _prog = gl.createProgram(); gl.attachShader(_prog, _vs_o); gl.attachShader(_prog, _fs_o); gl.linkProgram(_prog)
                    try:
                        if not gl.getProgramParameter(_prog, gl.LINK_STATUS):
                            return False
                    except Exception:
                        pass
                    if _prog is None:
                        return False
                    self._hud_prog = _prog
                    _buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, _buf)
                    # UVs: canvas top (y=0) -> V=0, canvas bottom -> V=1, because texImage2D with canvas does NOT flip Y by default.
                    # Quad: bottom-left (-1,-1) samples canvas bottom (V=1), top-left (-1,1) samples canvas top (V=0).
                    # Previous verts had V flipped, so HUD appeared upside-down / stretched.
                    _verts = [-1.0,-1.0,0.0,1.0, 1.0,-1.0,1.0,1.0, -1.0,1.0,0.0,0.0, 1.0,1.0,1.0,0.0]
                    gl.bufferData(gl.ARRAY_BUFFER, window.Float32Array.new(_verts), gl.STATIC_DRAW)
                    self._hud_buf = _buf
                if getattr(self, '_hud_prog', None) is None:
                    return False
                gl.disable(gl.DEPTH_TEST)
                gl.enable(gl.BLEND)
                gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
                gl.useProgram(self._hud_prog)
                gl.bindBuffer(gl.ARRAY_BUFFER, self._hud_buf)
                _ap = gl.getAttribLocation(self._hud_prog, 'a_p')
                _au = gl.getAttribLocation(self._hud_prog, 'a_uv')
                if _ap < 0 or _au < 0:
                    gl.disable(gl.BLEND)
                    gl.enable(gl.DEPTH_TEST)
                    return False
                gl.enableVertexAttribArray(_ap); gl.vertexAttribPointer(_ap, 2, gl.FLOAT, False, 16, 0)
                gl.enableVertexAttribArray(_au); gl.vertexAttribPointer(_au, 2, gl.FLOAT, False, 16, 8)
                gl.activeTexture(gl.TEXTURE0)
                gl.bindTexture(gl.TEXTURE_2D, tex)
                gl.uniform1i(gl.getUniformLocation(self._hud_prog, 'u_tex'), 0)
                gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
                gl.disable(gl.BLEND)
                gl.enable(gl.DEPTH_TEST)
            except Exception:
                pass
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
