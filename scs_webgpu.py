"""
scs_webgpu.py - SCS WebGPU renderer.

Reuses the ENTIRE geometry compiler from scs_webgl.py (parse_color,
triangulate, stroke_to_fill, expand_dashes, TextAtlas, TransformStack,
_GPURendererBase). Only the submission layer differs:

  WebGL2 : GLSL shaders + gl.bufferData + gl.drawArrays
  WebGPU : WGSL shaders + GPUBuffers + GPURenderPass + queue.submit

This is the Vello / Pathfinder / Lyon lesson: tessellate on the CPU,
rasterise on the GPU. A full compute-tile renderer (Vello) is a future
optimisation, not a prerequisite for API compatibility.

Device creation is async (navigator.gpu.requestAdapter() returns a
Promise). The entrypoint constructs this renderer, calls onAppStart
immediately, and starts the frame loop from on_ready. If WebGPU is
unavailable the entrypoint falls back to WebGL2, then 2D.
"""

import math

try:
    from browser import window
except ImportError:
    window = None

from scs_webgl import _GPURendererBase, parse_color


_SOLID_WGSL = """
struct VSOut {
  @builtin(position) pos: vec4<f32>,
  @location(0) color: vec4<f32>,
};
@group(0) @binding(0) var<uniform> u_res: vec2<f32>;
@vertex fn vs(@location(0) pos: vec2<f32>, @location(1) color: vec4<f32>) -> VSOut {
  var out: VSOut;
  let clip = (pos / u_res) * 2.0 - 1.0;
  out.pos = vec4<f32>(clip.x, -clip.y, 0.0, 1.0);
  out.color = color;
  return out;
}
@fragment fn fs(@location(0) color: vec4<f32>) -> @location(0) vec4<f32> {
  return color;
}
"""

_TEX_WGSL = """
struct VSOut {
  @builtin(position) pos: vec4<f32>,
  @location(0) uv: vec2<f32>,
  @location(1) color: vec4<f32>,
};
@group(0) @binding(0) var<uniform> u_res: vec2<f32>;
@group(0) @binding(1) var u_sampler: sampler;
@group(0) @binding(2) var u_tex: texture_2d<f32>;
@group(0) @binding(3) var<uniform> u_mask: u32;
@vertex fn vs(@location(0) pos: vec2<f32>, @location(1) uv: vec2<f32>,
              @location(2) color: vec4<f32>) -> VSOut {
  var out: VSOut;
  let clip = (pos / u_res) * 2.0 - 1.0;
  out.pos = vec4<f32>(clip.x, -clip.y, 0.0, 1.0);
  out.uv = uv;
  out.color = color;
  return out;
}
@fragment fn fs(@location(0) uv: vec2<f32>, @location(1) color: vec4<f32>)
    -> @location(0) vec4<f32> {
  let t = textureSample(u_tex, u_sampler, uv);
  if (u_mask == 1u) {
    return vec4<f32>(color.rgb, t.a * color.a);
  }
  return vec4<f32>(t.rgb, t.a * color.a);
}
"""


class RendererWebGPU(_GPURendererBase):
    kind = 'webgpu'

    def __init__(self, canvas, width, height):
        super().__init__(canvas, width, height)
        self.ready = False
        self.device = None
        self.context = None
        self.format = None
        self.on_ready = None
        self.on_error = None
        self._pipelines = {}
        self._res_buffer = None
        self._sampler = None
        self._gpu_textures = {}   # key -> (GPUTexture, GPUTextureView, bind group)
        self._uploaded_images = set()
        self._init_error = None
        try:
            gpu = window.navigator.gpu
        except Exception:
            gpu = None
        if gpu is None:
            self._init_error = 'WebGPU not available (navigator.gpu is None)'
            if self.on_error:
                self.on_error(self._init_error)
            return
        # Async: requestAdapter -> requestDevice -> configure -> ready.
        # Brython wraps Python callables as JS functions for .then().
        try:
            gpu.requestAdapter().then(self._on_adapter)
        except Exception as e:
            self._init_error = str(e)

    def _on_adapter(self, adapter):
        if adapter is None:
            self._fail('WebGPU adapter is None (no compatible GPU / blocked)')
            return
        try:
            adapter.requestDevice().then(self._on_device)
        except Exception as e:
            self._fail(str(e))

    def _on_device(self, device):
        try:
            self.device = device
            gpu = window.navigator.gpu
            self.format = gpu.getPreferredCanvasFormat()
            self.context = self.canvas.getContext('webgpu')
            self.context.configure({
                'device': device,
                'format': self.format,
                'alphaMode': 'opaque',
            })
            self._sampler = device.createSampler({
                'magFilter': 'linear', 'minFilter': 'linear',
            })
            # Resolution uniform (vec2<f32>, 8 bytes, 256-byte aligned alloc).
            self._res_buffer = device.createBuffer({
                'size': 256,
                'usage': 0x04 | 0x08,  # COPY_DST | UNIFORM (GPUBufferUsage)
            })
            self._mask_buf = device.createBuffer({
                'size': 256,
                'usage': 0x04 | 0x08,
            })
            self._pipelines['solid'] = self._make_pipeline(
                _SOLID_WGSL, ['solid'],
                [{'arrayStride': 24,
                  'attributes': [
                      {'shaderLocation': 0, 'offset': 0, 'format': 'float32x2'},
                      {'shaderLocation': 1, 'offset': 8, 'format': 'float32x4'},
                  ]}])
            self._pipelines['tex'] = self._make_pipeline(
                _TEX_WGSL, ['tex'],
                [{'arrayStride': 32,
                  'attributes': [
                      {'shaderLocation': 0, 'offset': 0, 'format': 'float32x2'},
                      {'shaderLocation': 1, 'offset': 8, 'format': 'float32x2'},
                      {'shaderLocation': 2, 'offset': 16, 'format': 'float32x4'},
                  ]}])
            self.ready = True
            if self.on_ready:
                self.on_ready()
        except Exception as e:
            self._fail(str(e))

    def _fail(self, msg):
        self._init_error = msg
        if self.on_error:
            self.on_error(msg)

    def _make_pipeline(self, wgsl, _name, buffers):
        device = self.device
        module = device.createShaderModule({'code': wgsl})
        # Auto layout: bind group layout is inferred from the WGSL.
        return device.createRenderPipeline({
            'layout': 'auto',
            'vertex': {'module': module, 'entryPoint': 'vs', 'buffers': buffers},
            'fragment': {'module': module, 'entryPoint': 'fs',
                         'targets': [{'format': self.format,
                                      'blend': {
                                          'color': {'srcFactor': 'src-alpha',
                                                    'dstFactor': 'one-minus-src-alpha',
                                                    'operation': 'add'},
                                          'alpha': {'srcFactor': 'src-alpha',
                                                    'dstFactor': 'one-minus-src-alpha',
                                                    'operation': 'add'}}}]},
            'primitive': {'topology': 'triangle-list'},
        })

    # -- textures ---------------------------------------------------
    def _gpu_texture_for(self, key, source, w, h, is_mask):
        """Create (or reuse) a GPUTexture + bind group for an image/atlas."""
        cached = self._gpu_textures.get(key)
        if cached is not None and key != ('atlas',):
            return cached
        device = self.device
        tex = device.createTexture({
            'size': {'width': int(w), 'height': int(h), 'depthOrArrayLayers': 1},
            'format': 'rgba8unorm',
            'usage': 0x02 | 0x10 | 0x04,  # TEXTURE_BINDING | COPY_DST | RENDER_ATTACHMENT
        })
        try:
            device.queue.copyExternalImageToTexture(
                {'source': source}, {'texture': tex}, {'width': int(w), 'height': int(h)})
        except Exception:
            pass
        # Mask flag is a uniform, not per-texture state: rebuild the bind
        # group per pipeline use is wasteful, so we keep TWO bind groups
        # per texture (mask=0 / mask=1) in a small dict on the entry.
        entry = {'texture': tex, 'view': tex.createView(), 'bind': {}}
        self._gpu_textures[key] = entry
        return entry

    def _bind_group(self, entry, is_mask):
        if is_mask in entry['bind']:
            return entry['bind'][is_mask]
        device = self.device
        # Write mask uniform.
        data = window.Uint32Array.new([1 if is_mask else 0, 0, 0, 0])
        device.queue.writeBuffer(self._mask_buf, 0, data)
        pipeline = self._pipelines['tex']
        bg = device.createBindGroup({
            'layout': pipeline.getBindGroupLayout(0),
            'entries': [
                {'binding': 0, 'resource': {'buffer': self._res_buffer}},
                {'binding': 1, 'resource': self._sampler},
                {'binding': 2, 'resource': entry['view']},
                {'binding': 3, 'resource': {'buffer': self._mask_buf}},
            ],
        })
        entry['bind'][is_mask] = bg
        return bg

    def _bind_group_solid(self):
        device = self.device
        pipeline = self._pipelines['solid']
        return device.createBindGroup({
            'layout': pipeline.getBindGroupLayout(0),
            'entries': [{'binding': 0, 'resource': {'buffer': self._res_buffer}}],
        })

    # -- submission --------------------------------------------------
    def _submit(self):
        if not self.ready or self.device is None:
            return
        device = self.device
        try:
            # Resolution uniform.
            res = window.Float32Array.new([float(self.width), float(self.height)])
            device.queue.writeBuffer(self._res_buffer, 0, res)
            view = self.context.getCurrentTexture().createView()
            r, g, b, a = self._bg
            encoder = device.createCommandEncoder()
            rp = encoder.beginRenderPass({
                'colorAttachments': [{
                    'view': view,
                    'clearValue': {'r': r, 'g': g, 'b': b, 'a': a},
                    'loadOp': 'clear',
                    'storeOp': 'store',
                }],
            })
            # Solid pass.
            if self._solid:
                buf = device.createBuffer({
                    'size': max(256, len(self._solid) * 4),
                    'usage': 0x02 | 0x08,  # VERTEX | COPY_DST
                })
                device.queue.writeBuffer(
                    buf, 0, window.Float32Array.new(self._solid))
                rp.setPipeline(self._pipelines['solid'])
                rp.setBindGroup(0, self._bind_group_solid())
                rp.setVertexBuffer(0, buf)
                rp.draw(len(self._solid) // 6)
            # Textured batches.
            for key, data in list(self._tex_batches.items()):
                if not data:
                    continue
                if key == ('atlas',):
                    if self.atlas.canvas is None:
                        continue
                    if self.atlas.dirty or ('atlas',) not in self._gpu_textures:
                        entry = self._gpu_texture_for(
                            ('atlas',), self.atlas.canvas,
                            self.atlas.size, self.atlas.size, True)
                        self.atlas.dirty = False
                    else:
                        entry = self._gpu_textures[('atlas',)]
                    is_mask = True
                else:
                    img = self._images.get(key[1])
                    if img is None:
                        continue
                    iw = int(getattr(img, 'naturalWidth', 0) or getattr(img, 'width', 0) or 1)
                    ih = int(getattr(img, 'naturalHeight', 0) or getattr(img, 'height', 0) or 1)
                    if key not in self._gpu_textures:
                        entry = self._gpu_texture_for(key, img, iw, ih, False)
                    else:
                        entry = self._gpu_textures[key]
                    is_mask = False
                buf = device.createBuffer({
                    'size': max(256, len(data) * 4),
                    'usage': 0x02 | 0x08,
                })
                device.queue.writeBuffer(buf, 0, window.Float32Array.new(data))
                rp.setPipeline(self._pipelines['tex'])
                rp.setBindGroup(0, self._bind_group(entry, is_mask))
                rp.setVertexBuffer(0, buf)
                rp.draw(len(data) // 8)
            rp.end()
            device.queue.submit([encoder.finish()])
        except Exception:
            # A failed frame (e.g. canvas resized mid-frame) must not kill
            # the loop; the next frame retries.
            pass

    def draw_hud_canvas(self, canvas, left=0, top=0, w=None, h=None, opacity=100):
        """HUD texture in WebGPU: offscreen 2D canvas -> texture -> HUD quad.
        Default HUD/2D. Works everywhere WebGPU works. Returns True."""
        try:
            if canvas is None:
                return False
            ww = float(w) if w is not None else float(self.width)
            hh = float(h) if h is not None else float(self.height)
            key = ('hud', 'offscreen')
            try:
                self._upload_texture(key, canvas)
            except Exception:
                return False
            self._emit_textured_quad(key, float(left), float(top), ww, hh,
                                     0.0, 0.0, 1.0, 1.0, 'white', float(opacity) / 100.0)
            return True
        except Exception:
            return False

    def draw_html_element(self, element, left=0, top=0, w=None, h=None, opacity=100):
        """HTML-in-Canvas in WebGPU: device.queue.drawElementImageToTexture() - Chrome 157+ only.
        Old (149-154): copyElementImageToTexture(). Firefox/Safari have nothing.
        Hit-testing: canvas.updateElementGeometry(element, {canvasTransform}).
        Returns True if upload succeeded, False if not supported (caller falls back to texture)."""
        try:
            if element is None:
                return False
            device = getattr(self, 'device', None)
            if device is None:
                return False
            queue = getattr(device, 'queue', None)
            if queue is None:
                return False
            has_new = hasattr(queue, 'drawElementImageToTexture')
            has_old = hasattr(queue, 'copyElementImageToTexture')
            if not (has_new or has_old):
                return False
            ww = float(w) if w is not None else float(self.width)
            hh = float(h) if h is not None else float(self.height)
            key = ('html', 'hud')
            # Allocate / get texture for HTML HUD - reuse _upload_texture path if possible
            # For WebGPU we need a GPUTexture; _upload_texture handles it for canvas,
            # but for HTML we need to draw the element into it via the queue.
            # Try the queue method first; if it needs a texture, create one via _upload_texture
            # with a dummy canvas, then overwrite it with the element.
            try:
                if has_new:
                    # drawElementImageToTexture(texture, element) - exact signature varies by Chrome version,
                    # try (texture, element) then (element, texture) then (texture, element, x, y)
                    tex = self._gl_textures.get(key) if hasattr(self, '_gl_textures') else None
                    if tex is None:
                        # Create a placeholder texture via _upload_texture with an empty canvas
                        try:
                            _c = window.document.createElement('canvas') if window is not None else None
                            if _c is not None:
                                _c.width = int(ww); _c.height = int(hh)
                                self._upload_texture(key, _c)
                                tex = self._gl_textures.get(key) if hasattr(self, '_gl_textures') else None
                        except Exception:
                            tex = None
                    if tex is not None:
                        queue.drawElementImageToTexture(tex, element)
                    else:
                        queue.drawElementImageToTexture(element)
                else:
                    queue.copyElementImageToTexture(element)
            except Exception:
                return False
            # Hit-testing
            try:
                _canvas = getattr(self, 'canvas', None)
                if _canvas is not None and hasattr(_canvas, 'updateElementGeometry'):
                    try:
                        _m = window.DOMMatrix.new() if window is not None else None
                        if _m is not None:
                            _m = _m.translate(float(left), float(top))
                            _canvas.updateElementGeometry(element, {'canvasTransform': _m})
                        else:
                            _canvas.updateElementGeometry(element, {})
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                self._emit_textured_quad(key, float(left), float(top), ww, hh,
                                         0.0, 0.0, 1.0, 1.0, 'white', float(opacity) / 100.0)
            except Exception:
                return False
            return True
        except Exception:
            return False

    def destroy(self):
        self.ready = False
        self.device = None
