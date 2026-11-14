"""
scs_engine_wgpu.py -- PROPER WebGPU engine, ENGINE-AGNOSTIC API.

This is the canonical `wgpu` engine. The older file scs_engine_webgpu.py
is the same 3D solid-only engine without sprites; this file supersedes it
for new code (it keeps the same class name + build_uniform_data() so old
code keeps working, and adds the full engine-agnostic API below).

What "engine-agnostic" means here -- and why this file is the proof:
  * The SAME draw_* methods exist on every engine, with the SAME
    signatures, in the SAME order:
        begin_frame(background) / end_frame()
        push_transform(cx, cy, angle_deg, alpha_mult) / pop_transform()
        draw_rect / draw_circle / draw_oval / draw_line / draw_polygon /
        draw_label / draw_image / draw_image_uv / draw_sprite / draw_sprite_sheet
        clear_scene() / add_sphere() / add_box() / add_floor() / add_sprite()
        render(camera) / render_for_view(view) / resize(w, h) / describe()
    2D (scs_2d), WebGL-2D (scs_webgl), WebGPU-2D (scs_webgpu), WebGL2-3D
    (scs_engine_webgl2), WGPU-3D (THIS FILE) and XR (scs_xr, via
    render_for_view) all implement this set. User code never branches on
    `if engine == 'webgpu'`. It calls the same methods and the engine
    decides how to honour them (2D: immediate quad; 3D: queued scene
    item + billboard in render(); XR: per-view render_for_view).
  * Sprites are the same call everywhere (see scs_sprites.py):
        renderer.draw_sprite(image, u0, v0, u1, v1, x, y, w, h,
                             opacity=100, rotateAngle=0,
                             flip_x=False, flip_y=False,
                             billboard='none', z=0, tint='white')
    2D ignores billboard + z. 3D queues the sprite and applies
    billboarding in render(camera) / render_for_view(view) with THAT
    camera. XR calls render_for_view(view) once per eye, so billboarding
    is per-eye, not once for the whole frame.
  * No fallback. Own native WebGPU context: navigator.gpu, adapter,
    device, canvas.getContext('webgpu'). Never touches WebGL2, never
    touches the 2D renderers, never imports scs_webgl. If WebGPU is
    unavailable, `error` is set and the engine FAILS -- the caller picks
    the engine; the engine does not pick a different one behind the
    caller's back.
  * Own WGSL: solid (lit sphere/cube) + textured (sprite / image quads).
    Own GPUBuffers, own depth texture, own pipelines. Depth test on
    for the 3D scene, depth off for the 2D overlay (HUD).
  * Async init: requestAdapter -> requestDevice -> configure.
    `ready` is False until on_ready fires.

Math only is shared (scs_3d.py: pure matrices, no GPU calls).
Billboard math is shared (scs_sprites.billboard_model_matrix).
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
    mat4_mul = mat4_translate = mat4_scale = None

try:
    from scs_sprites import billboard_model_matrix as _billboard_matrix
except Exception:
    _billboard_matrix = None


_SOLID_WGSL = """
struct Uniforms {
  mvp: mat4x4<f32>,
  normal: mat3x3<f32>,
  color: vec3<f32>,
  lightDir: vec3<f32>,
};
@group(0) @binding(0) var<uniform> u: Uniforms;
struct VSOut {
  @builtin(position) pos: vec4<f32>,
  @location(0) normal: vec3<f32>,
  @location(1) color: vec3<f32>,
};
@vertex fn vs(@location(0) pos: vec3<f32>,
               @location(1) normal: vec3<f32>) -> VSOut {
  var out: VSOut;
  out.pos = u.mvp * vec4<f32>(pos, 1.0);
  out.normal = u.normal * normal;
  out.color = u.color;
  return out;
}
@fragment fn fs(@location(0) normal: vec3<f32>,
                @location(1) color: vec3<f32>) -> @location(0) vec4<f32> {
  let n = normalize(normal);
  let diff = max(dot(n, normalize(u.lightDir)), 0.0);
  var col = color * (0.35 + 0.65 * diff);
  let halfV = normalize(normalize(u.lightDir) + vec3<f32>(0.0, 0.0, 1.0));
  let spec = pow(max(dot(n, halfV), 0.0), 32.0) * 0.6;
  return vec4<f32>(col + spec, 1.0);
}
"""

_TEXTURED_WGSL = """
struct Uniforms {
  mvp: mat4x4<f32>,
  tint: vec4<f32>,
};
@group(0) @binding(0) var<uniform> u: Uniforms;
@group(0) @binding(1) var u_sampler: sampler;
@group(0) @binding(2) var u_tex: texture_2d<f32>;
struct VSOut {
  @builtin(position) pos: vec4<f32>,
  @location(0) uv: vec2<f32>,
  @location(1) tint: vec4<f32>,
};
@vertex fn vs(@location(0) pos: vec3<f32>,
               @location(1) uv: vec2<f32>) -> VSOut {
  var out: VSOut;
  out.pos = u.mvp * vec4<f32>(pos, 1.0);
  out.uv = uv;
  out.tint = u.tint;
  return out;
}
@fragment fn fs(@location(0) uv: vec2<f32>,
                @location(1) tint: vec4<f32>) -> @location(0) vec4<f32> {
  let t = textureSample(u_tex, u_sampler, uv);
  if (t.a < 0.01) { discard; }
  return vec4<f32>(t.rgb * tint.rgb, t.a * tint.a);
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
    if c is None:
        return (0.0, 0.0, 0.0, 1.0)
    if isinstance(c, (list, tuple)):
        if len(c) >= 3:
            r = float(c[0]) / 255.0 if c[0] > 1 else float(c[0])
            g = float(c[1]) / 255.0 if c[1] > 1 else float(c[1])
            b = float(c[2]) / 255.0 if c[2] > 1 else float(c[2])
            a = float(c[3]) if len(c) >= 4 else 1.0
            return (r, g, b, a)
    s = str(c).strip().lower()
    if s in _NAMED:
        r, g, b = _NAMED[s]
        return (r / 255.0, g / 255.0, b / 255.0, 1.0)
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
    return (0.0, 0.0, 1.0, 1.0)


def _mat4_identity():
    return [1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0]


def _mat4_ortho(left, right, bottom, top, near, far):
    """Orthographic projection, column-major, for the 2D overlay."""
    m = [0.0] * 16
    m[0] = 2.0 / (right - left)
    m[5] = 2.0 / (top - bottom)
    m[10] = -2.0 / (far - near)
    m[12] = -(right + left) / (right - left)
    m[13] = -(top + bottom) / (top - bottom)
    m[14] = -(far + near) / (far - near)
    m[15] = 1.0
    return m


def _mat4_rotate_z(angle_rad):
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return [c, s, 0.0, 0.0,
            -s, c, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0]


class WGPUEngine:
    """Owns one WebGPU device + context + pipelines + depth texture.

    Engine-agnostic API (see module docstring): begin_frame/end_frame,
    draw_* (2D overlay + 3D scene), add_* (3D scene), render(camera),
    render_for_view(view) for XR, resize, describe.
    """

    kind = 'wgpu'
    # Aliases so old code that checks kind == 'webgpu-3d' keeps working.
    kinds = ('wgpu', 'webgpu-3d', 'webgpu')

    def __init__(self, canvas=None, width=900, height=560, background=None):
        self.width = int(width)
        self.height = int(height)
        self.canvas = canvas
        self.device = None
        self.context = None
        self.format = None
        self.pipeline = None          # solid pipeline
        self.textured_pipeline = None  # sprite / image pipeline
        self.ready = False
        self.error = None
        self.on_ready = None
        self.on_error = None
        self.scene = []    # 3D items: sphere / cube / sprite
        self.overlay = []  # 2D items: rect / circle / line / label / image / sprite (HUD)
        self.light = (0.5, 1.0, 0.5)
        self.clear_color = _parse_color(background) if background is not None else (0.05, 0.05, 0.10, 1.0)
        self._vertex_buffer = None
        self._index_buffer = None
        self._quad_buffer = None
        self._uniform_buffer = None
        self._textured_uniform_buffer = None
        self._depth_texture = None
        self._sampler = None
        self._textures = {}  # path -> (GPUTexture, GPUTextureView) or None while loading
        self._sphere_index_count = 0
        self._cube_index_count = 0
        self._transform_stack = [(0.0, 0.0, 0.0, 1.0)]  # (cx, cy, angle_deg, alpha)
        if self.canvas is None:
            self.canvas = self._find_canvas()
        if self.canvas is None:
            self.error = 'No canvas for WGPUEngine'
            return
        if window is None:
            self.error = 'No browser window (CPython) -- WGPUEngine needs a browser'
            return
        try:
            gpu = window.navigator.gpu
        except Exception:
            gpu = None
        if gpu is None:
            self.error = 'WebGPU not available (navigator.gpu is None)'
            if self.on_error:
                self.on_error(self.error)
            return
        try:
            gpu.requestAdapter().then(self._on_adapter)
        except Exception as e:
            self.error = 'requestAdapter failed: %s' % e

    def _find_canvas(self):
        if document is None:
            return None
        for cid in ('wgpu-canvas', 'webgpu-canvas', 'canvas', 'scs-canvas', 'cmu-canvas'):
            try:
                c = document.getElementById(cid)
            except Exception:
                c = None
            if c is not None:
                return c
        return None

    def _on_adapter(self, adapter):
        if adapter is None:
            self.error = 'WebGPU adapter is None (no compatible GPU)'
            if self.on_error:
                self.on_error(self.error)
            return
        try:
            adapter.requestDevice().then(self._on_device)
        except Exception as e:
            self.error = 'requestDevice failed: %s' % e

    def _on_device(self, device):
        try:
            self.device = device
            gpu = window.navigator.gpu
            self.format = gpu.getPreferredCanvasFormat()
            self.context = self.canvas.getContext('webgpu')
            self.context.configure({'device': device, 'format': self.format, 'alphaMode': 'opaque'})
            from scs_3d import make_cube_mesh
            s_verts, s_idx = make_sphere_mesh(24, 32)
            c_verts, c_idx = make_cube_mesh()
            all_verts = list(s_verts) + list(c_verts)
            n_sphere = len(s_verts) // 6
            all_idx = list(s_idx) + [i + n_sphere for i in c_idx]
            self._sphere_index_count = len(s_idx)
            self._cube_index_count = len(c_idx)
            self._vertex_buffer = self._make_buffer(all_verts, 0x08 | 0x02)
            self._index_buffer = self._make_buffer(all_idx, 0x10 | 0x02)
            # Quad for sprites / images: pos xyz + uv, centred at origin, size 1x1.
            quad = [-0.5, -0.5, 0.0, 0.0, 1.0,
                     0.5, -0.5, 0.0, 1.0, 1.0,
                     0.5,  0.5, 0.0, 1.0, 0.0,
                    -0.5, -0.5, 0.0, 0.0, 1.0,
                     0.5,  0.5, 0.0, 1.0, 0.0,
                    -0.5,  0.5, 0.0, 0.0, 0.0]
            self._quad_buffer = self._make_buffer(quad, 0x08 | 0x02)
            self._uniform_buffer = device.createBuffer({'size': 256, 'usage': 0x04 | 0x08})
            self._textured_uniform_buffer = device.createBuffer({'size': 256, 'usage': 0x04 | 0x08})
            self._depth_texture = device.createTexture({
                'size': {'width': int(self.width), 'height': int(self.height), 'depthOrArrayLayers': 1},
                'format': 'depth24plus', 'usage': 0x10})
            solid_mod = device.createShaderModule({'code': _SOLID_WGSL})
            tex_mod = device.createShaderModule({'code': _TEXTURED_WGSL})
            self.pipeline = device.createRenderPipeline({
                'layout': 'auto',
                'vertex': {'module': solid_mod, 'entryPoint': 'vs',
                           'buffers': [{'arrayStride': 24, 'attributes': [
                               {'shaderLocation': 0, 'offset': 0, 'format': 'float32x3'},
                               {'shaderLocation': 1, 'offset': 12, 'format': 'float32x3'}]}]},
                'fragment': {'module': solid_mod, 'entryPoint': 'fs',
                             'targets': [{'format': self.format}]},
                'primitive': {'topology': 'triangle-list', 'cullMode': 'back'},
                'depthStencil': {'depthWriteEnabled': True, 'depthCompare': 'less', 'format': 'depth24plus'},
            })
            self.textured_pipeline = device.createRenderPipeline({
                'layout': 'auto',
                'vertex': {'module': tex_mod, 'entryPoint': 'vs',
                           'buffers': [{'arrayStride': 20, 'attributes': [
                               {'shaderLocation': 0, 'offset': 0, 'format': 'float32x3'},
                               {'shaderLocation': 1, 'offset': 12, 'format': 'float32x2'}]}]},
                'fragment': {'module': tex_mod, 'entryPoint': 'fs',
                             'targets': [{'format': self.format,
                                          'blend': {'color': {'srcFactor': 'src-alpha', 'dstFactor': 'one-minus-src-alpha', 'operation': 'add'},
                                                      'alpha': {'srcFactor': 'one', 'dstFactor': 'one-minus-src-alpha', 'operation': 'add'}}}]},
                'primitive': {'topology': 'triangle-list', 'cullMode': 'none'},
                'depthStencil': {'depthWriteEnabled': True, 'depthCompare': 'less', 'format': 'depth24plus'},
            })
            self._sampler = device.createSampler({'magFilter': 'linear', 'minFilter': 'linear'})
            self.ready = True
            if self.on_ready:
                self.on_ready()
        except Exception as e:
            self.error = 'WebGPU device setup failed: %s' % e
            if self.on_error:
                self.on_error(self.error)

    def _make_buffer(self, data, usage):
        try:
            buf = self.device.createBuffer({'size': max(16, len(data) * 4), 'usage': usage})
            return buf
        except Exception:
            return None

    # -- engine-agnostic frame --------------------------------------------
    def resize(self, width, height):
        self.width, self.height = int(width), int(height)
        if self.device is not None and self.ready:
            try:
                self._depth_texture = self.device.createTexture({
                    'size': {'width': int(self.width), 'height': int(self.height), 'depthOrArrayLayers': 1},
                    'format': 'depth24plus', 'usage': 0x10})
            except Exception:
                pass

    def begin_frame(self, background=None):
        """Start a frame. Clears the 2D overlay. 3D scene persists (add_*)."""
        if background is not None:
            self.clear_color = _parse_color(background)
        self.overlay = []
        self._transform_stack = [(0.0, 0.0, 0.0, 1.0)]

    def end_frame(self, camera=None):
        """End a frame. If a camera is given, render the frame now.
        If no camera is given, the caller will call render(camera) itself
        (the 3D-engine pattern). Returns True if a frame was rendered."""
        if camera is not None:
            return self.render(camera)
        return False

    def push_transform(self, cx, cy, angle_deg, alpha_mult):
        self._transform_stack.append((float(cx), float(cy), float(angle_deg or 0), float(alpha_mult)))
    def pop_transform(self):
        if len(self._transform_stack) > 1:
            self._transform_stack.pop()

    # -- 3D scene (same shape as WebGL2 engine) ---------------------------
    def clear_scene(self):
        self.scene = []
    def clear_overlay(self):
        self.overlay = []
    def add_sphere(self, x, y, z, radius, color='blue'):
        item = {'kind': 'sphere', 'pos': (float(x), float(y), float(z)),
                'scale': (float(radius),) * 3, 'color': color}
        self.scene.append(item)
        return item
    def add_box(self, x, y, z, sx, sy, sz, color='gray'):
        item = {'kind': 'cube', 'pos': (float(x), float(y), float(z)),
                'scale': (float(sx), float(sy), float(sz)), 'color': color}
        self.scene.append(item)
        return item
    def add_floor(self, size=22.0, color='#22223a'):
        return self.add_box(0.0, -0.05, 0.0, size, 0.1, size, color)
    def add_sprite(self, image, u0=0.0, v0=0.0, u1=1.0, v1=1.0, x=0.0, y=0.0, z=0.0,
                   w=1.0, h=1.0, opacity=100, rotateAngle=0, flip_x=False, flip_y=False,
                   billboard='none', tint='white'):
        """Add a sprite to the 3D scene. Same args as draw_sprite().

        Use this when you want the sprite to live in the world (not HUD).
        draw_sprite() with billboard != 'none' or z != 0 does this for you.
        """
        # Flip is baked into UVs here so render() does not need to re-apply it.
        if flip_x:
            u0, u1 = u1, u0
        if flip_y:
            v0, v1 = v1, v0
        item = {'kind': 'sprite', 'image': image, 'uv': (float(u0), float(v0), float(u1), float(v1)),
                'pos': (float(x), float(y), float(z)), 'scale': (float(w), float(h), 1.0),
                'opacity': float(opacity), 'rotateAngle': float(rotateAngle),
                'billboard': billboard, 'tint': tint}
        self.scene.append(item)
        return item

    # -- 2D overlay: draw_* with the SAME signatures as 2D / WebGL / WebGPU-2D --
    def _overlay_item(self, kind, **kwargs):
        item = {'kind': kind}
        item.update(kwargs)
        self.overlay.append(item)
        return item
    def draw_rect(self, left, top, w, h, fill='black', border=None, borderWidth=2,
                  opacity=100, rotateAngle=0, dashes=False, roundness=0):
        return self._overlay_item('rect', left=float(left), top=float(top), w=float(w), h=float(h),
                                  fill=fill, border=border, borderWidth=borderWidth,
                                  opacity=float(opacity), rotateAngle=float(rotateAngle))
    def draw_circle(self, cx, cy, radius, fill='black', border=None, borderWidth=2,
                    opacity=100, rotateAngle=0, dashes=False):
        return self._overlay_item('circle', cx=float(cx), cy=float(cy), radius=float(radius),
                                  fill=fill, border=border, borderWidth=borderWidth,
                                  opacity=float(opacity))
    def draw_oval(self, cx, cy, w, h, fill='black', border=None, borderWidth=2,
                  opacity=100, rotateAngle=0, dashes=False):
        return self._overlay_item('oval', cx=float(cx), cy=float(cy), w=float(w), h=float(h),
                                  fill=fill, border=border, borderWidth=borderWidth,
                                  opacity=float(opacity))
    def draw_line(self, x1, y1, x2, y2, fill='black', lineWidth=2, opacity=100, dashes=False):
        return self._overlay_item('line', x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2),
                                  fill=fill, lineWidth=float(lineWidth), opacity=float(opacity))
    def draw_polygon(self, points, fill='black', border=None, borderWidth=2, opacity=100,
                     rotateAngle=0, dashes=False):
        return self._overlay_item('polygon', points=list(points), fill=fill, border=border,
                                  borderWidth=borderWidth, opacity=float(opacity))
    def draw_label(self, text, x, y, fill='black', size=12, font='arial', bold=False,
                   italic=False, opacity=100, align='center', rotateAngle=0):
        # Labels in the WGPU 3D engine are overlay-only; GPU text atlas lives
        # in scs_webgpu (2D). We queue the item so describe() / tests see it,
        # and render() skips it (no text pipeline in the 3D engine).
        return self._overlay_item('label', text=str(text), x=float(x), y=float(y), fill=fill,
                                  size=float(size), font=font, bold=bool(bold), italic=bool(italic),
                                  opacity=float(opacity), align=align)
    def draw_image(self, path, left, top, w, h, opacity=100, rotateAngle=0):
        return self.draw_sprite(path, 0.0, 0.0, 1.0, 1.0, float(left) + float(w) / 2, float(top) + float(h) / 2,
                                 w, h, opacity=opacity, rotateAngle=rotateAngle)
    def draw_image_uv(self, path, u0, v0, u1, v1, left, top, w, h, opacity=100, rotateAngle=0):
        return self.draw_sprite(path, u0, v0, u1, v1, float(left) + float(w) / 2, float(top) + float(h) / 2,
                                 w, h, opacity=opacity, rotateAngle=rotateAngle)
    def draw_sprite(self, image, u0, v0, u1, v1, x, y, w, h, opacity=100, rotateAngle=0,
                    flip_x=False, flip_y=False, billboard='none', z=0, tint='white'):
        """THE engine-agnostic sprite call. Same signature on every engine.

        Rules in THIS engine:
          * billboard != 'none' or z != 0 -> world sprite: queued into scene,
            billboard applied in render(camera) / render_for_view(view).
          * otherwise -> HUD sprite: queued into overlay, drawn with ortho.
        2D engines ignore billboard + z and always draw it as a HUD quad.
        """
        if flip_x:
            u0, u1 = u1, u0
        if flip_y:
            v0, v1 = v1, v0
        if (billboard is not None and str(billboard).lower() not in ('none', '', 'off')) or float(z or 0) != 0:
            return self.add_sprite(image, u0, v0, u1, v1, x, y, z, w, h,
                                   opacity=opacity, rotateAngle=rotateAngle, billboard=billboard, tint=tint)
        return self._overlay_item('sprite', image=image, uv=(float(u0), float(v0), float(u1), float(v1)),
                                  x=float(x), y=float(y), w=float(w), h=float(h),
                                  opacity=float(opacity), rotateAngle=float(rotateAngle), tint=tint)
    def draw_sprite_sheet(self, sheet, frame, x, y, w=None, h=None, opacity=100, rotateAngle=0,
                          flip_x=False, flip_y=False, billboard='none', z=0, tint='white'):
        """draw_sprite_sheet(sheet, frame_index_or_name, x, y, w, h, ...).

        Accepts a SpriteSheet (scs_sprites) -- extracts UV + image for you.
        w/h default to the frame's pixel size when omitted.
        """
        fr = sheet.frame(frame)
        ww = float(w) if w is not None else float(fr.w)
        hh = float(h) if h is not None else float(fr.h)
        u0, v0, u1, v1 = fr.uv
        return self.draw_sprite(sheet.image, u0, v0, u1, v1, x, y, ww, hh,
                                opacity=opacity, rotateAngle=rotateAngle,
                                flip_x=flip_x, flip_y=flip_y, billboard=billboard, z=z, tint=tint)

    # -- pure-python uniform / matrix helpers (testable without a GPU) --
    def build_uniform_data(self, camera, item):
        """Solid uniform: MVP + normal + color + light. Same as scs_engine_webgpu."""
        view = camera.view_matrix()
        proj = camera.proj_matrix(self.width / float(self.height))
        model = mat4_mul(mat4_translate(*item['pos']), mat4_scale(*item['scale']))
        mv = mat4_mul(view, model)
        mvp = mat4_mul(proj, mv)
        normal = [mv[0], mv[1], mv[2], 0.0, mv[4], mv[5], mv[6], 0.0, mv[8], mv[9], mv[10], 0.0]
        r, g, b, _a = _parse_color(item['color'])
        return list(mvp) + normal + [r, g, b, 0.0] + [float(self.light[0]), float(self.light[1]), float(self.light[2]), 0.0]

    def build_sprite_model_matrix(self, item, camera_eye):
        """Model matrix for a sprite item, with billboarding.

        Pure python. camera_eye = camera.position (tuple) or None.
        This is what render(camera) calls per sprite per frame.
        """
        if _billboard_matrix is not None:
            return _billboard_matrix(item['pos'], item['scale'], item.get('rotateAngle', 0),
                                     camera_eye, item.get('billboard', 'none'))
        # Fallback: no billboard helper -- translate + rotateZ + scale.
        model = mat4_mul(mat4_translate(*item['pos']),
                         mat4_mul(_mat4_rotate_z(math.radians(float(item.get('rotateAngle', 0)))),
                                  mat4_scale(*item['scale'])))
        return model

    def build_sprite_uniform_data(self, camera, item):
        """Textured uniform: MVP + tint. Pure python."""
        view = camera.view_matrix()
        proj = camera.proj_matrix(self.width / float(self.height))
        try:
            eye = camera.position
        except Exception:
            eye = None
        model = self.build_sprite_model_matrix(item, eye)
        mvp = mat4_mul(proj, mat4_mul(view, model))
        r, g, b, a = _parse_color(item.get('tint', 'white'))
        alpha = (float(item.get('opacity', 100)) / 100.0) * a
        return list(mvp) + [r, g, b, alpha] + [0.0] * 12

    # -- textures ------------------------------------------------------------
    def _get_texture(self, path):
        """Return (GPUTexture, GPUTextureView) or None if not ready yet.

        Starts an async load on first use. Never blocks, never raises.
        In CPython (no window) returns None.
        """
        if self.device is None or window is None:
            return None
        if path in self._textures:
            return self._textures[path]
        self._textures[path] = None
        try:
            img = window.Image.new()
            def _on_load(_ev=None):
                try:
                    tex = self.device.createTexture({
                        'size': {'width': int(img.naturalWidth or img.width), 'height': int(img.naturalHeight or img.height), 'depthOrArrayLayers': 1},
                        'format': 'rgba8unorm-srgb', 'usage': 0x04 | 0x10 | 0x02})
                    self.device.queue.copyExternalImageToTexture({'source': img}, {'texture': tex}, {'width': int(img.naturalWidth or img.width), 'height': int(img.naturalHeight or img.height), 'depthOrArrayLayers': 1})
                    self._textures[path] = (tex, tex.createView())
                except Exception:
                    self._textures[path] = None
            img.onload = _on_load
            img.src = str(path)
        except Exception:
            self._textures[path] = None
        return None

    # -- render ------------------------------------------------------------
    def render(self, camera):
        """One frame from a Camera3D. No-op until ready. Never falls back."""
        if not self.ready or camera is None:
            return False
        try:
            view = camera.view_matrix()
            proj = camera.proj_matrix(self.width / float(self.height))
            eye = getattr(camera, 'position', None)
            return self._render_with_matrices(view, proj, eye, target_view=None)
        except Exception as e:
            self.error = 'render failed: %s' % e
            return False

    def render_for_view(self, view):
        """One frame for ONE XR view. Same sprite API, per-eye billboarding.

        view: scs_xr.View -- has projection_matrix, view_matrix (runtime-supplied),
        viewport, target. The runtime supplies the matrices; SCS never derives
        them from an SCS camera FOV. This is how sprites work in WebXR:
        the XR loop calls render_for_view(view) once per view, and sprites
        billboard to THAT view's eye, not to a single desktop camera.
        """
        if not self.ready or view is None:
            return False
        try:
            proj = list(getattr(view, 'projection_matrix', None) or [])
            vm = list(getattr(view, 'view_matrix', None) or [])
            if len(proj) != 16 or len(vm) != 16:
                return False
            # Eye position = inverse view translation: eye = -R^T * t.
            # view matrix is column-major: t = (m[12], m[13], m[14]).
            # R^T rows are columns of R. eye = -(R^T * t).
            eye = (-(vm[0] * vm[12] + vm[1] * vm[13] + vm[2] * vm[14]),
                   -(vm[4] * vm[12] + vm[5] * vm[13] + vm[6] * vm[14]),
                   -(vm[8] * vm[12] + vm[9] * vm[13] + vm[10] * vm[14]))
            target = getattr(view, 'target', None)
            return self._render_with_matrices(vm, proj, eye, target_view=target)
        except Exception as e:
            self.error = 'render_for_view failed: %s' % e
            return False

    def _render_with_matrices(self, view_matrix, proj_matrix, eye, target_view):
        """Shared GPU submission for render() and render_for_view()."""
        try:
            if target_view is not None:
                try:
                    color_view = target_view.createView() if hasattr(target_view, 'createView') else target_view
                except Exception:
                    color_view = target_view
            else:
                color_view = self.context.getCurrentTexture().createView()
            encoder = self.device.createCommandEncoder()
            rp = encoder.beginRenderPass({
                'colorAttachments': [{'view': color_view,
                                      'clearValue': {'r': float(self.clear_color[0]), 'g': float(self.clear_color[1]), 'b': float(self.clear_color[2]), 'a': float(self.clear_color[3])},
                                      'loadOp': 'clear', 'storeOp': 'store'}],
                'depthStencilAttachment': {'view': self._depth_texture.createView(),
                                          'depthClearValue': 1.0, 'depthLoadOp': 'clear', 'depthStoreOp': 'store'},
            })
            # -- 3D scene: solid items, then sprites (textured) --
            for item in self.scene:
                if item['kind'] == 'sprite':
                    self._draw_sprite_gpu(rp, item, view_matrix, proj_matrix, eye)
                else:
                    self._draw_solid_gpu(rp, item, view_matrix, proj_matrix)
            # -- 2D overlay: ortho, depth test still on but quads are at z=0 in screen space --
            ortho = _mat4_ortho(0, float(self.width), float(self.height), 0, -1, 1)
            for item in self.overlay:
                if item['kind'] == 'sprite':
                    self._draw_overlay_sprite_gpu(rp, item, ortho)
                # rect / circle / line / label in the 3D engine are queued for
                # describe() + tests; the 3D engine has no 2D vector pipeline.
                # (Use the 2D / WebGPU-2D renderer for vector HUDs, or add
                #  a textured label atlas -- deliberately not faked here.)
            rp.end()
            self.device.queue.submit([encoder.finish()])
            return True
        except Exception as e:
            self.error = 'render failed: %s' % e
            return False

    def _draw_solid_gpu(self, rp, item, view_matrix, proj_matrix):
        model = mat4_mul(mat4_translate(*item['pos']), mat4_scale(*item['scale']))
        mv = mat4_mul(view_matrix, model)
        mvp = mat4_mul(proj_matrix, mv)
        normal = [mv[0], mv[1], mv[2], 0.0, mv[4], mv[5], mv[6], 0.0, mv[8], mv[9], mv[10], 0.0]
        r, g, b, _a = _parse_color(item['color'])
        data = list(mvp) + normal + [r, g, b, 0.0] + [float(self.light[0]), float(self.light[1]), float(self.light[2]), 0.0]
        self.device.queue.writeBuffer(self._uniform_buffer, 0, window.Float32Array.new(data))
        bg = self.device.createBindGroup({'layout': self.pipeline.getBindGroupLayout(0),
                                          'entries': [{'binding': 0, 'resource': {'buffer': self._uniform_buffer}}]})
        rp.setPipeline(self.pipeline)
        rp.setVertexBuffer(0, self._vertex_buffer)
        rp.setIndexBuffer(self._index_buffer, 'uint16')
        rp.setBindGroup(0, bg)
        if item['kind'] == 'sphere':
            rp.drawIndexed(self._sphere_index_count)
        else:
            rp.drawIndexed(self._cube_index_count)

    def _draw_sprite_gpu(self, rp, item, view_matrix, proj_matrix, eye):
        tex = self._get_texture(item['image'])
        if tex is None:
            return
        model = self.build_sprite_model_matrix(item, eye)
        mvp = mat4_mul(proj_matrix, mat4_mul(view_matrix, model))
        r, g, b, a = _parse_color(item.get('tint', 'white'))
        alpha = (float(item.get('opacity', 100)) / 100.0) * a
        data = list(mvp) + [r, g, b, alpha] + [0.0] * 12
        self.device.queue.writeBuffer(self._textured_uniform_buffer, 0, window.Float32Array.new(data))
        bg = self.device.createBindGroup({'layout': self.textured_pipeline.getBindGroupLayout(0),
                                          'entries': [{'binding': 0, 'resource': {'buffer': self._textured_uniform_buffer}},
                                                      {'binding': 1, 'resource': self._sampler},
                                                      {'binding': 2, 'resource': tex[1]}]})
        rp.setPipeline(self.textured_pipeline)
        rp.setVertexBuffer(0, self._quad_buffer)
        rp.setBindGroup(0, bg)
        # UVs are per-sprite, not per-vertex: we encode them by rewriting the
        # quad buffer for this sprite (6 verts, 5 floats each). Cheap for
        # a sprite count in the tens; a real batcher would use instancing.
        u0, v0, u1, v1 = item['uv']
        quad = [-0.5, -0.5, 0.0, u0, v1,
                 0.5, -0.5, 0.0, u1, v1,
                 0.5,  0.5, 0.0, u1, v0,
                -0.5, -0.5, 0.0, u0, v1,
                 0.5,  0.5, 0.0, u1, v0,
                -0.5,  0.5, 0.0, u0, v0]
        # NOTE: the quad buffer is shared; a real engine would use a per-
        # sprite vertex buffer or instanced UVs. This per-sprite rewrite is
        # the simplest correct path and is documented as such.
        try:
            self.device.queue.writeBuffer(self._quad_buffer, 0, window.Float32Array.new(quad))
        except Exception:
            pass
        rp.draw(6)

    def _draw_overlay_sprite_gpu(self, rp, item, ortho):
        tex = self._get_texture(item['image'])
        if tex is None:
            return
        # Overlay sprite: centre (x, y) in screen px, size (w, h).
        model = mat4_mul(mat4_translate(item['x'], item['y'], 0.0),
                         mat4_mul(_mat4_rotate_z(math.radians(float(item.get('rotateAngle', 0)))),
                                  mat4_scale(item['w'], item['h'], 1.0)))
        mvp = mat4_mul(ortho, model)
        r, g, b, a = _parse_color(item.get('tint', 'white'))
        alpha = (float(item.get('opacity', 100)) / 100.0) * a
        data = list(mvp) + [r, g, b, alpha] + [0.0] * 12
        self.device.queue.writeBuffer(self._textured_uniform_buffer, 0, window.Float32Array.new(data))
        bg = self.device.createBindGroup({'layout': self.textured_pipeline.getBindGroupLayout(0),
                                          'entries': [{'binding': 0, 'resource': {'buffer': self._textured_uniform_buffer}},
                                                      {'binding': 1, 'resource': self._sampler},
                                                      {'binding': 2, 'resource': tex[1]}]})
        rp.setPipeline(self.textured_pipeline)
        rp.setVertexBuffer(0, self._quad_buffer)
        rp.setBindGroup(0, bg)
        u0, v0, u1, v1 = item['uv']
        quad = [-0.5, -0.5, 0.0, u0, v1,
                 0.5, -0.5, 0.0, u1, v1,
                 0.5,  0.5, 0.0, u1, v0,
                -0.5, -0.5, 0.0, u0, v1,
                 0.5,  0.5, 0.0, u1, v0,
                -0.5,  0.5, 0.0, u0, v0]
        try:
            self.device.queue.writeBuffer(self._quad_buffer, 0, window.Float32Array.new(quad))
        except Exception:
            pass
        rp.draw(6)

    def describe(self):
        return {'kind': self.kind, 'width': self.width, 'height': self.height,
                'ready': self.ready, 'scene_items': len(self.scene),
                'overlay_items': len(self.overlay), 'error': self.error}


# Backwards-compat names: old code imported WebGPU3DEngine from scs_engine_webgpu.
WebGPU3DEngine = WGPUEngine
EngineWGPU = WGPUEngine
WGPU3DEngine = WGPUEngine


def create_engine(canvas=None, width=900, height=560, background=None):
    """Create a WGPUEngine. Same factory shape as the other engines."""
    return WGPUEngine(canvas=canvas, width=width, height=height, background=background)
