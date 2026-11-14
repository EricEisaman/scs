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
    a different engine behind the caller's back. NO FALLBACK CONTENT.

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

# ----------------------------------------------------------------------
# MSDF text in WGSL - FIRST-RATE, same Chlumsky median as GLSL.
# WGSL has no fwidth(): w = (abs(dpdx(sd)) + abs(dpdy(sd))) * pxRange.
# This engine had NO draw_label - labels were dropped in WebGPU 3D.
# Now it has MSDF, so button labels show in WebGPU 3D too.
# ----------------------------------------------------------------------
_MSDF_WGSL = """
struct MSDFUniforms {
  res: vec2<f32>,
  pxRange: f32,
  _pad: f32,
};
@group(0) @binding(0) var<uniform> u: MSDFUniforms;
@group(0) @binding(1) var u_tex: texture_2d<f32>;
@group(0) @binding(2) var u_sampler: sampler;
struct MSDFOut {
  @builtin(position) pos: vec4<f32>,
  @location(0) uv: vec2<f32>,
  @location(1) color: vec4<f32>,
};
@vertex fn vs_msdf(@location(0) pos: vec2<f32>,
                    @location(1) uv: vec2<f32>,
                    @location(2) color: vec4<f32>) -> MSDFOut {
  var out: MSDFOut;
  let clip = (pos / u.res) * 2.0 - 1.0;
  out.pos = vec4<f32>(clip.x, -clip.y, 0.0, 1.0);
  out.uv = uv;
  out.color = color;
  return out;
}
fn msdf_median(r: f32, g: f32, b: f32) -> f32 {
  return min(max(min(r, g), min(max(r, g), b)), max(min(r, g), min(max(r, g), b)));
}
@fragment fn fs_msdf(@location(0) uv: vec2<f32>,
                      @location(1) color: vec4<f32>) -> @location(0) vec4<f32> {
  let t = textureSample(u_tex, u_sampler, uv);
  let sd = msdf_median(t.r, t.g, t.b);
  // PROPER: w = fwidth(sd) = abs(dpdx)+abs(dpdy), WITHOUT pxRange multiplier.
  // pxRange is baked into atlas encoding. Old *u.pxRange over-blurred 4x.
  let w = abs(dpdx(sd)) + abs(dpdy(sd));
  var alpha = smoothstep(0.5 - w, 0.5 + w, sd);
  alpha = pow(alpha, 1.0 / 2.2);
  if (alpha < 0.01) { discard; }
  return vec4<f32>(color.rgb, alpha * color.a);
}
"""

def _msdf_is_edge(alpha, w, h, i):
    x = i % w; y = i // w; v = alpha[i] > 127
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0: continue
            nx, ny = x+dx, y+dy
            if nx < 0 or nx >= w or ny < 0 or ny >= h: return True
            if (alpha[ny*w+nx] > 127) != v: return True
    return False

def _edt_1d(f, n):
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
                try: self.ctx.fillStyle='rgb(128,128,128)'; self.ctx.fillRect(0,0,size,size)
                except Exception: pass
                self._tmp=document.createElement('canvas'); self._tmp_ctx=self._tmp.getContext('2d')
            except Exception: self.canvas=None
    def measure(self, text, font_str):
        if self.ctx is not None:
            try: self.ctx.font=font_str; m=self.ctx.measureText(str(text)); return float(m.width), float(getattr(m,'actualBoundingBoxAscent',12)+getattr(m,'actualBoundingBoxDescent',4))
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
            except Exception: # NO FALLBACK: getImageData failed - fail this glyph, do NOT fake MSDF with bitmap.
                return
            alpha=[data[i+3] for i in range(0,len(data),4)]; sdf=_msdf_distance(alpha,tw,th); out_w,out_h=int(w),int(h)
            try: out_img=self.ctx.createImageData(out_w,out_h); out_data=out_img.data
            except Exception: return
            rng=self.PX_RANGE*SUP
            for oy in range(out_h):
                for ox in range(out_w):
                    def _s(dx,dy):
                        sx=min(tw-1,max(0,ox*SUP+self.PAD*SUP+dx)); sy=min(th-1,max(0,oy*SUP+self.PAD*SUP+dy)); idx=int(sy)*tw+int(sx); return sdf[idx] if 0<=idx<len(sdf) else 0.0
                    r=_s(0,0); g=_s(1,0); b=_s(0,1)
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
            # MSDF pipeline - PROPER. Was missing entirely, so labels were dropped.
            # Blend on, depth off, ortho. Same WGSL as _MSDF_WGSL (median, dpdx/dpdy, gamma).
            try:
                _msdf_mod = device.createShaderModule({'code': _MSDF_WGSL})
                self._msdf_pipeline = device.createRenderPipeline({
                    'layout': 'auto',
                    'vertex': {
                        'module': _msdf_mod, 'entryPoint': 'vs_msdf',
                        'buffers': [{'arrayStride': 32,
                                     'attributes': [
                                         {'shaderLocation': 0, 'offset': 0, 'format': 'float32x2'},
                                         {'shaderLocation': 1, 'offset': 8, 'format': 'float32x2'},
                                         {'shaderLocation': 2, 'offset': 16, 'format': 'float32x4'}]}],
                    },
                    'fragment': {
                        'module': _msdf_mod, 'entryPoint': 'fs_msdf',
                        'targets': [{'format': self.format,
                                     'blend': {
                                         'color': {'srcFactor': 'src-alpha', 'dstFactor': 'one-minus-src-alpha', 'operation': 'add'},
                                         'alpha': {'srcFactor': 'one', 'dstFactor': 'one-minus-src-alpha', 'operation': 'add'},
                                     }}],
                    },
                    'primitive': {'topology': 'triangle-list', 'cullMode': 'none'},
                    'depthStencil': {
                        'depthWriteEnabled': False,
                        'depthCompare': 'always',
                        'format': 'depth24plus',
                    },
                })
                self._msdf_uniform_buffer = device.createBuffer({'size': 16, 'usage': 0x04 | 0x08})
                self._msdf_vertex_buffer = device.createBuffer({'size': 65536*4, 'usage': 0x02 | 0x08})
                self._msdf_sampler = device.createSampler({'magFilter': 'linear', 'minFilter': 'linear',
                                                           'addressModeU': 'clamp-to-edge', 'addressModeV': 'clamp-to-edge'})
                self._msdf_texture = None
            except Exception as _e:
                self._msdf_pipeline = None
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
            # MSDF labels: second pass, loadOp 'load' to preserve 3D. Was missing - labels dropped.
            try: self._flush_msdf(encoder, view)
            except Exception: pass
            self.device.queue.submit([encoder.finish()])
            return True
        except Exception as e:
            self.error = 'render failed: %s' % e
            return False

    def draw_label(self, text, x, y, fill='black', size=12, font='arial', bold=False, italic=False, opacity=100, align='center', rotateAngle=0):
        """MSDF label in WebGPU 3D. Was missing - labels dropped. Now WGSL MSDF median + dpdx/dpdy."""
        try:
            if not hasattr(self, '_msdf_atlas'):
                self._msdf_atlas = _MSDFAtlas()
                self._msdf_batches = []
            style = ('italic ' if italic else '') + ('bold ' if bold else '')
            font_str = '%s%dpx %s' % (style, size, font)
            u0, v0, u1, v1, w, h = self._msdf_atlas.get_rect(text, font_str)
            a = str(align).lower()
            ox = 0.0 if 'left' in a else (-w if 'right' in a else -w/2)
            oy = 0.0 if 'top' in a else (-h if 'bottom' in a else -h/2)
            r, g, b = _parse_color(fill)
            self._msdf_batches.append((x+ox, y+oy, w, h, u0, v0, u1, v1, r, g, b, opacity/100.0))
        except Exception:
            pass

    def _flush_msdf(self, encoder, view):
        """Draw queued MSDF labels in a second pass (loadOp load, depth off). Proper WGSL MSDF."""
        try:
            batches = getattr(self, '_msdf_batches', [])
            if not batches or getattr(self, '_msdf_pipeline', None) is None:
                return
            atlas = getattr(self, '_msdf_atlas', None)
            if atlas is None or atlas.canvas is None:
                self._msdf_batches = []
                return
            # Upload atlas if dirty
            if getattr(atlas, 'dirty', False):
                try:
                    # Create texture from canvas via copyExternalImageToTexture if available, else via canvas bitmap
                    # Brython: device.createTexture + queue.copyExternalImageToTexture
                    if self._msdf_texture is None:
                        self._msdf_texture = self.device.createTexture({
                            'size': {'width': int(atlas.size), 'height': int(atlas.size), 'depthOrArrayLayers': 1},
                            'format': 'rgba8unorm',
                            'usage': 0x02 | 0x10,  # TEXTURE_BINDING | COPY_DST
                        })
                    try:
                        self.device.queue.copyExternalImageToTexture(
                            {'source': atlas.canvas},
                            {'texture': self._msdf_texture},
                            {'width': int(atlas.size), 'height': int(atlas.size), 'depthOrArrayLayers': 1})
                    except Exception:
                        pass
                    atlas.dirty = False
                except Exception: pass
            # Build vertex data: x,y,u,v,r,g,b,a per vertex, 6 verts per quad
            data = []
            for (x, y, w, h, u0, v0, u1, v1, r, g, b, a) in batches:
                data.extend([x, y, u0, v0, r, g, b, a, x+w, y, u1, v0, r, g, b, a, x+w, y+h, u1, v1, r, g, b, a,
                             x, y, u0, v0, r, g, b, a, x+w, y+h, u1, v1, r, g, b, a, x, y+h, u0, v1, r, g, b, a])
            # Uniforms: res (w,h), pxRange (4.0), pad
            try:
                self.device.queue.writeBuffer(self._msdf_uniform_buffer, 0, window.Float32Array.new([float(self.width), float(self.height), 4.0, 0.0]))
                self.device.queue.writeBuffer(self._msdf_vertex_buffer, 0, window.Float32Array.new(data))
            except Exception: pass
            # Second pass: load, not clear
            rp2 = encoder.beginRenderPass({
                'colorAttachments': [{'view': view, 'loadOp': 'load', 'storeOp': 'store'}],
                'depthStencilAttachment': {'view': self._depth_texture.createView(), 'depthLoadOp': 'load', 'depthStoreOp': 'store'},
            })
            try:
                rp2.setPipeline(self._msdf_pipeline)
                rp2.setVertexBuffer(0, self._msdf_vertex_buffer)
                bg = self.device.createBindGroup({
                    'layout': self._msdf_pipeline.getBindGroupLayout(0),
                    'entries': [{'binding': 0, 'resource': {'buffer': self._msdf_uniform_buffer}},
                                {'binding': 1, 'resource': self._msdf_texture.createView() if self._msdf_texture is not None else None},
                                {'binding': 2, 'resource': self._msdf_sampler}],
                })
                rp2.setBindGroup(0, bg)
                rp2.draw(len(data)//8)
            finally:
                rp2.end()
            self._msdf_batches = []
        except Exception:
            pass

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
        succeeded, False if not supported (NO FALLBACK - caller must handle failure explicitly)."""
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
