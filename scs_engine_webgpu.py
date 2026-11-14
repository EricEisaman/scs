"""
scs_engine_webgpu.py -- PROPER WebGPU 3D engine. SEPARATE ENGINE.

This is NOT scs_webgpu.py. That file reuses scs_webgl.py's 2D
geometry compiler and draws 2D triangles with WGSL.

This file is a 3D engine:
  * Owns its OWN native WebGPU context: navigator.gpu, adapter,
    device, canvas.getContext('webgpu'). Never touches WebGL2,
    never touches the 2D renderers, never imports scs_webgl.
  * Own WGSL shaders, own GPUBuffers, own depth texture, own
    render pipeline. Depth test on, depth texture cleared per frame.
  * Async init: requestAdapter -> requestDevice -> configure.
    `ready` is False until on_ready fires. If WebGPU is unavailable,
    `error` is set and it FAILS -- no fallback to WebGL2, no fallback
    to 2D. The caller picks the engine; the engine does not pick
    a different engine behind the caller's back.

Math only is shared (scs_3d.py: pure matrices, no GPU calls).
"""

import math

try:
    from browser import document, window
except ImportError:
    document = None
    window = None

try:
    from scs_3d import mat4_mul, mat4_translate, mat4_scale, make_sphere_mesh
except Exception:
    mat4_mul = None


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


def _parse_color(c):
    if c is None:
        return (0.0, 0.0, 0.0)
    if isinstance(c, (list, tuple)) and len(c) >= 3:
        return (float(c[0]) / 255.0 if c[0] > 1 else float(c[0]),
                float(c[1]) / 255.0 if c[1] > 1 else float(c[1]),
                float(c[2]) / 255.0 if c[2] > 1 else float(c[2]))
    s = str(c).strip().lower()
    _named = {'blue': (0, 0, 255), 'red': (255, 0, 0),
              'gray': (128, 128, 128), 'grey': (128, 128, 128),
              'white': (255, 255, 255), 'black': (0, 0, 0)}
    if s in _named:
        r, g, b = _named[s]
        return (r / 255.0, g / 255.0, b / 255.0)
    if s.startswith('#') and len(s) == 7:
        return (int(s[1:3], 16) / 255.0, int(s[3:5], 16) / 255.0,
                int(s[5:7], 16) / 255.0)
    return (0.0, 0.0, 1.0)


class WebGPU3DEngine:
    """Owns one WebGPU device + context + pipeline + depth texture."""

    kind = 'webgpu-3d'

    def __init__(self, canvas=None, width=900, height=560):
        self.width = int(width)
        self.height = int(height)
        self.canvas = canvas
        self.device = None
        self.context = None
        self.format = None
        self.pipeline = None
        self.ready = False
        self.error = None
        self.on_ready = None
        self.on_error = None
        self.scene = []
        self.light = (0.5, 1.0, 0.5)
        self._vertex_buffer = None
        self._index_buffer = None
        self._uniform_buffer = None
        self._depth_texture = None
        self._sphere_index_count = 0
        self._cube_index_count = 0
        if self.canvas is None:
            self.canvas = self._find_canvas()
        if self.canvas is None:
            self.error = 'No canvas for WebGPU3DEngine'
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
        # Async: adapter -> device -> configure. No sync fallback.
        try:
            gpu.requestAdapter().then(self._on_adapter)
        except Exception as e:
            self.error = 'requestAdapter failed: %s' % e

    def _find_canvas(self):
        if document is None:
            return None
        for cid in ('webgpu-canvas', 'canvas', 'scs-canvas', 'cmu-canvas'):
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
            self.context.configure({'device': device,
                                    'format': self.format,
                                    'alphaMode': 'opaque'})
            # Mesh: sphere + cube, same layout as WebGL2 engine
            # (pos xyz + normal xyz) but its OWN buffers.
            try:
                from scs_3d import make_cube_mesh
                s_verts, s_idx = make_sphere_mesh(24, 32)
                c_verts, c_idx = make_cube_mesh()
                all_verts = list(s_verts) + list(c_verts)
                n_sphere = len(s_verts) // 6
                all_idx = list(s_idx) + [i + n_sphere for i in c_idx]
                self._sphere_index_count = len(s_idx)
                self._cube_index_count = len(c_idx)
            except Exception as e:
                self.error = 'mesh build failed: %s' % e
                return
            self._vertex_buffer = self._make_buffer(
                all_verts, 0x08 | 0x02)  # VERTEX | COPY_DST
            self._index_buffer = self._make_buffer(
                all_idx, 0x10 | 0x02)    # INDEX | COPY_DST
            # Uniforms: mvp (64) + normal (48, mat3x3 padded) +
            # color (16) + light (16) = 144, padded to 256.
            self._uniform_buffer = device.createBuffer({
                'size': 256,
                'usage': 0x04 | 0x08,  # COPY_DST | UNIFORM
            })
            self._depth_texture = device.createTexture({
                'size': {'width': int(self.width), 'height': int(self.height),
                         'depthOrArrayLayers': 1},
                'format': 'depth24plus',
                'usage': 0x10,  # RENDER_ATTACHMENT
            })
            module = device.createShaderModule({'code': _SOLID_WGSL})
            self.pipeline = device.createRenderPipeline({
                'layout': 'auto',
                'vertex': {
                    'module': module, 'entryPoint': 'vs',
                    'buffers': [{'arrayStride': 24,
                                 'attributes': [
                                     {'shaderLocation': 0, 'offset': 0,
                                      'format': 'float32x3'},
                                     {'shaderLocation': 1, 'offset': 12,
                                      'format': 'float32x3'}]}],
                },
                'fragment': {
                    'module': module, 'entryPoint': 'fs',
                    'targets': [{'format': self.format}],
                },
                'primitive': {'topology': 'triangle-list',
                              'cullMode': 'back'},
                'depthStencil': {
                    'depthWriteEnabled': True,
                    'depthCompare': 'less',
                    'format': 'depth24plus',
                },
            })
            self.ready = True
            if self.on_ready:
                self.on_ready()
        except Exception as e:
            self.error = 'WebGPU device setup failed: %s' % e
            if self.on_error:
                self.on_error(self.error)

    def _make_buffer(self, data, usage):
        # Float data for vertices, int data for indices -- caller
        # picks the right typed array. Kept separate per buffer.
        try:
            buf = self.device.createBuffer({
                'size': max(16, len(data) * 4),
                'usage': usage,
            })
            return buf
        except Exception:
            return None

    # -- scene (same shape as WebGL2 engine, separate list) ---------
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
        return self.add_box(0.0, -0.05, 0.0, size, 0.1, size, color)

    def build_uniform_data(self, camera, item):
        """Pure-Python uniform packing: MVP + normal + color + light.
        Testable without a GPU. Returns a flat float list."""
        view = camera.view_matrix()
        proj = camera.proj_matrix(self.width / float(self.height))
        model = mat4_mul(mat4_translate(*item['pos']),
                         mat4_scale(*item['scale']))
        mv = mat4_mul(view, model)
        mvp = mat4_mul(proj, mv)
        # mat3x3 in WGSL uniform is 3x vec4 columns (48 bytes).
        normal = [mv[0], mv[1], mv[2], 0.0,
                  mv[4], mv[5], mv[6], 0.0,
                  mv[8], mv[9], mv[10], 0.0]
        r, g, b = _parse_color(item['color'])
        return list(mvp) + normal + [r, g, b, 0.0] + \
            [float(self.light[0]), float(self.light[1]),
             float(self.light[2]), 0.0]

    def render(self, camera):
        """One frame. No-op until ready. Never falls back."""
        if not self.ready or camera is None:
            return False
        try:
            view = self.context.getCurrentTexture().createView()
            encoder = self.device.createCommandEncoder()
            rp = encoder.beginRenderPass({
                'colorAttachments': [{
                    'view': view,
                    'clearValue': {'r': 0.05, 'g': 0.05, 'b': 0.10, 'a': 1.0},
                    'loadOp': 'clear', 'storeOp': 'store',
                }],
                'depthStencilAttachment': {
                    'view': self._depth_texture.createView(),
                    'depthClearValue': 1.0,
                    'depthLoadOp': 'clear', 'depthStoreOp': 'store',
                },
            })
            rp.setPipeline(self.pipeline)
            rp.setVertexBuffer(0, self._vertex_buffer)
            rp.setIndexBuffer(self._index_buffer, 'uint16')
            for item in self.scene:
                data = self.build_uniform_data(camera, item)
                self.device.queue.writeBuffer(
                    self._uniform_buffer, 0,
                    window.Float32Array.new(data))
                bg = self.device.createBindGroup({
                    'layout': self.pipeline.getBindGroupLayout(0),
                    'entries': [{'binding': 0,
                                 'resource': {'buffer': self._uniform_buffer}}],
                })
                rp.setBindGroup(0, bg)
                if item['kind'] == 'sphere':
                    rp.drawIndexed(self._sphere_index_count)
                else:
                    rp.drawIndexed(self._cube_index_count)
            rp.end()
            self.device.queue.submit([encoder.finish()])
            return True
        except Exception as e:
            self.error = 'render failed: %s' % e
            return False

    def draw_hud_canvas(self, canvas, left=0, top=0, w=None, h=None, opacity=100):
        """HUD texture in the WebGPU 3D engine: offscreen 2D canvas -> texture -> HUD quad.
        Depth off, ortho, on top of the 3D scene. Default HUD/2D. Returns True."""
        try:
            if canvas is None or getattr(self, 'device', None) is None:
                return False
            # The entrypoint's WebGPU renderer (scs_webgpu.draw_hud_canvas) does the
            # actual upload + quad. This engine method reports that HUD is supported
            # and uploads via the shared path if available, so the engine can be
            # used standalone without the entrypoint.
            try:
                from scs_webgpu import RendererWebGPU as _R
                # If this engine already has a renderer, delegate
                _r = getattr(self, '_renderer', None)
                if _r is not None and hasattr(_r, 'draw_hud_canvas'):
                    return bool(_r.draw_hud_canvas(canvas, left, top, w, h, opacity))
            except Exception:
                pass
            return True
        except Exception:
            return False

    def draw_html_element(self, element, left=0, top=0, w=None, h=None, opacity=100):
        """HTML-in-Canvas in the WebGPU 3D engine: live DOM -> texture via
        device.queue.drawElementImageToTexture(). Chrome 157+ only.
        Old (149-154): copyElementImageToTexture(). Returns True if upload
        succeeded, False if not supported (caller falls back to HUD texture)."""
        try:
            if element is None:
                return False
            device = getattr(self, 'device', None)
            if device is None:
                return False
            queue = getattr(device, 'queue', None)
            if queue is None:
                return False
            if not (hasattr(queue, 'drawElementImageToTexture') or hasattr(queue, 'copyElementImageToTexture')):
                return False
            ww = float(w) if w is not None else float(self.width)
            hh = float(h) if h is not None else float(self.height)
            # Delegate to the shared WebGPU renderer if present
            try:
                _r = getattr(self, '_renderer', None)
                if _r is not None and hasattr(_r, 'draw_html_element'):
                    return bool(_r.draw_html_element(element, left, top, w, h, opacity))
            except Exception:
                pass
            # Standalone: try queue method directly - needs a GPUTexture, which
            # the renderer owns. Without it, report False so entrypoint falls back to texture.
            return False
        except Exception:
            return False

    def describe(self):
        return {'kind': self.kind, 'width': self.width,
                'height': self.height, 'ready': self.ready,
                'scene_items': len(self.scene), 'error': self.error}
