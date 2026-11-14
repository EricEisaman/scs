"""
scs_core.py - Resource-and-pass core for SCS.

This is the layer the 20 early decisions require, sitting BETWEEN the
SCS scene API (shapes in scs_entrypoint.py) and the three backends
(scs_2d / scs_webgl / scs_webgpu):

    SCS scene API (Rect, Label, Group, drawRect, ...)   <- optional scene layer
    scs_core: Pass, Pipeline, Texture, Buffer, Capability <- THIS FILE
    Backends: 2D / WebGL2 / WebGPU                           <- submission only

Why this boundary (Decision 1): a scene-graph-only core forces every
app to use the scene model; a GPU-resource-only core forces every app
to manage buffers. Resource-and-pass + optional scene gives both.

Why not WebGL-global-state as the abstraction (Decision 1, 4): WebGL's
mutable state is tracked by the backend, never by the app. WebGPU's
immutable pipelines are the model; WebGL emulates them via a cached
pipeline object (Decision 5).

Everything in here is backend-agnostic and Brython-safe (no dataclasses,
no typing, plain dicts/tuples). Backends import from here; the scene
layer never imports backend handles.
"""

import math
import time


# ----------------------------------------------------------------------
# 20. Observability (built first so every other decision can report)
# ----------------------------------------------------------------------

class Stats:
    """Counters for draws / uploads / pipeline creation / memory.
    Expensive validation lives behind `debug` and is OFF in hot paths."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.draws = 0
        self.triangles = 0
        self.upload_bytes = 0
        self.upload_calls = 0
        self.pipeline_creations = 0
        self.pipeline_cache_hits = 0
        self.texture_uploads = 0
        self.buffer_allocations = 0
        self.frames = 0
        self.cpu_ms = 0.0

    def to_dict(self):
        return {
            'draws': self.draws, 'triangles': self.triangles,
            'upload_bytes': self.upload_bytes, 'upload_calls': self.upload_calls,
            'pipeline_creations': self.pipeline_creations,
            'pipeline_cache_hits': self.pipeline_cache_hits,
            'texture_uploads': self.texture_uploads,
            'buffer_allocations': self.buffer_allocations,
            'frames': self.frames, 'cpu_ms': self.cpu_ms,
        }


STATS = Stats()


def _now_ms():
    try:
        return time.time() * 1000.0
    except Exception:
        return 0.0


# ----------------------------------------------------------------------
# 18. Ownership / disposal / memory budgets
# ----------------------------------------------------------------------

class Resource:
    """A GPU resource with an owner, a label (for GPU debuggers), and an
    explicit lifetime. GC is NOT the lifecycle: callers must dispose()."""

    def __init__(self, label, owner=None):
        self.label = label or 'unnamed'
        self.owner = owner
        self.disposed = False
        if owner is not None and hasattr(owner, '_track'):
            owner._track(self)

    def dispose(self):
        self.disposed = True

    def check_alive(self):
        if self.disposed:
            raise RuntimeError('Use of disposed resource: %s' % self.label)


class ResourceTracker:
    """Per-renderer registry. get_resource_stats() is the memory budget."""

    def __init__(self):
        self._resources = []

    def _track(self, res):
        self._resources.append(res)

    def dispose_all(self):
        for r in list(self._resources):
            try:
                r.dispose()
            except Exception:
                pass
        self._resources = []

    def live(self):
        return [r for r in self._resources if not r.disposed]

    def stats(self):
        by_kind = {}
        for r in self.live():
            k = type(r).__name__
            by_kind[k] = by_kind.get(k, 0) + 1
        return {'live_resources': len(self.live()), 'by_kind': by_kind}


# ----------------------------------------------------------------------
# 2. Capability contract -- portable baseline + explicit checks
# ----------------------------------------------------------------------

class UnsupportedError(RuntimeError):
    """Raised when an operation is outside the negotiated capability set.
    Callers (entrypoint) map this to a predictable fallback, never a
    silent wrong result."""


class Capability:
    """Negotiated at init. A common interface does NOT imply identical
    capabilities: WebGPU compute, for example, has no WebGL equivalent
    and is exposed here as supports_compute=False on WebGL2."""

    def __init__(self, backend, **kw):
        self.backend = backend  # '2d' | 'webgl2' | 'webgpu'
        self.max_texture_size = kw.get('max_texture_size', 2048)
        self.max_vertex_buffers = kw.get('max_vertex_buffers', 8)
        self.supports_compute = kw.get('supports_compute', False)
        self.supports_mipmaps = kw.get('supports_mipmaps', backend != 'webgpu')
        self.supports_msaa = kw.get('supports_msaa', True)
        self.supports_storage_buffers = kw.get(
            'supports_storage_buffers', backend == 'webgpu')
        self.supports_timestamp_query = kw.get('supports_timestamp_query', False)
        self.max_bind_groups = kw.get('max_bind_groups', 4 if backend == 'webgpu' else 0)
        # Portable baseline every backend guarantees (Decision 2).
        self.baseline = {
            'triangles', 'textured_quads', 'alpha_blend',
            'linear_gradients', 'dashed_strokes', 'text_atlas',
        }

    def require(self, feature):
        if feature == 'compute' and not self.supports_compute:
            raise UnsupportedError(
                'compute is not available on %s (WebGPU only)' % self.backend)
        if feature == 'storage_buffers' and not self.supports_storage_buffers:
            raise UnsupportedError(
                'storage buffers are not available on %s' % self.backend)
        if feature == 'mipmaps' and not self.supports_mipmaps:
            raise UnsupportedError(
                'generateMipmap is not available on %s; pre-generate mips' % self.backend)

    def to_dict(self):
        return {
            'backend': self.backend,
            'max_texture_size': self.max_texture_size,
            'supports_compute': self.supports_compute,
            'supports_mipmaps': self.supports_mipmaps,
            'supports_msaa': self.supports_msaa,
            'supports_storage_buffers': self.supports_storage_buffers,
            'max_bind_groups': self.max_bind_groups,
        }


def capability_for_webgl2(gl):
    max_tex = 2048
    try:
        max_tex = int(gl.getParameter(gl.MAX_TEXTURE_SIZE))
    except Exception:
        pass
    return Capability('webgl2', max_texture_size=max_tex,
                      supports_compute=False, supports_mipmaps=True)


def capability_for_webgpu(device=None):
    # WebGPU limits are queried from the adapter in the backend; the
    # portable baseline is the same, compute is the extension.
    return Capability('webgpu', max_texture_size=8192,
                      supports_compute=True, supports_mipmaps=False,
                      supports_storage_buffers=True)


# ----------------------------------------------------------------------
# 16. Colour + alpha conventions (decided once, enforced everywhere)
# ----------------------------------------------------------------------
# Inputs: sRGB 8-bit strings / rgb() / #hex (what CSS / CMU apps write).
# Internal: straight (non-premultiplied) alpha, floats 0..1.
# Blending: SRC_ALPHA / ONE_MINUS_SRC_ALPHA, canvas alphaMode 'opaque'.
# Textures: rgba8unorm (NOT rgba8unorm-srgb yet -- sRGB decode is a
# future, explicitly-versioned change; see ARCHITECTURE.md).
# Never guess per-material: every pipeline uses the same blend state.

BLEND_STRAIGHT_ALPHA = {
    'color': {'srcFactor': 'src-alpha', 'dstFactor': 'one-minus-src-alpha',
              'operation': 'add'},
    'alpha': {'srcFactor': 'src-alpha', 'dstFactor': 'one-minus-src-alpha',
              'operation': 'add'},
}


def to_linear(c):
    """sRGB 0..1 -> linear (for future sRGB texture path; not yet used
    in the blend path, but the conversion lives here, not per-material)."""
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def to_srgb(c):
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055


# ----------------------------------------------------------------------
# 17. Display size vs rendering resolution vs attachments
# ----------------------------------------------------------------------

class DisplayConfig:
    """CSS size, backing size, DPR policy, render scale, MSAA -- distinct
    settings (Decision 17). Resize recreates attachments coherently."""

    def __init__(self, css_width, css_height, dpr=1.0, render_scale=1.0,
                 sample_count=1, pixel_ratio_cap=None, pixel_budget=None):
        self.css_width = int(css_width)
        self.css_height = int(css_height)
        self.dpr = float(dpr or 1.0)
        self.render_scale = float(render_scale or 1.0)
        self.sample_count = int(sample_count or 1)
        # Decision 3: caps are part of the display config, not an
        # afterthought. Fullscreen never means "render at max DPR".
        self.pixel_ratio_cap = pixel_ratio_cap
        self.pixel_budget = pixel_budget

    @property
    def effective_dpr(self):
        d = self.dpr * self.render_scale
        if self.pixel_ratio_cap is not None:
            d = min(d, float(self.pixel_ratio_cap))
        return d

    @property
    def backing_width(self):
        if self.css_width <= 0:
            return 0
        w = int(self.css_width * self.effective_dpr)
        return self._apply_budget(w, int(self.css_height * self.effective_dpr))[0]

    @property
    def backing_height(self):
        if self.css_height <= 0:
            return 0
        h = int(self.css_height * self.effective_dpr)
        return self._apply_budget(int(self.css_width * self.effective_dpr), h)[1]

    def _apply_budget(self, w, h):
        if self.pixel_budget is None or w <= 0 or h <= 0:
            return (w, h)
        pixels = w * h
        if pixels <= self.pixel_budget:
            return (w, h)
        s = math.sqrt(self.pixel_budget / float(pixels))
        return (max(1, int(w * s)), max(1, int(h * s)))

    @property
    def is_zero_sized(self):
        return self.css_width <= 0 or self.css_height <= 0

    def to_dict(self):
        return {
            'display': {'css_width': self.css_width,
                        'css_height': self.css_height},
            'drawing_buffer': {'width': self.backing_width,
                               'height': self.backing_height,
                               'effective_dpr': self.effective_dpr},
            'caps': {'pixel_ratio_cap': self.pixel_ratio_cap,
                     'pixel_budget': self.pixel_budget},
            'is_zero_sized': self.is_zero_sized,
        }

    def resize(self, css_width, css_height, dpr=None, render_scale=None,
               sample_count=None, pixel_ratio_cap=None, pixel_budget=None):
        self.css_width = int(css_width)
        self.css_height = int(css_height)
        if dpr is not None:
            self.dpr = float(dpr)
        if render_scale is not None:
            self.render_scale = float(render_scale)
        if sample_count is not None:
            self.sample_count = int(sample_count)
        if pixel_ratio_cap is not None:
            self.pixel_ratio_cap = pixel_ratio_cap
        if pixel_budget is not None:
            self.pixel_budget = pixel_budget


# ----------------------------------------------------------------------
# 8. CPU-shader memory contract: ONE authoritative schema
# ----------------------------------------------------------------------
# Field offsets / alignment / strides live here. Writers and shader
# declarations are generated from the same schema -- never hand-maintained
# in two places (Decision 8). WebGPU binding-offset alignment (256B for
# uniform buffers) is enforced by uniform_buffer_size().

class Field:
    def __init__(self, name, kind, offset, fmt):
        self.name = name
        self.kind = kind  # 'float32x2' | 'float32x4' | 'float32' | 'uint32'
        self.offset = offset
        self.fmt = fmt  # WGSL type, e.g. 'vec2<f32>'


class VertexLayout:
    """A reusable geometry descriptor (Decision 13): format, stride,
    offsets, step mode. Backends derive VAOs / WGSL vertex buffers
    from this, they do not invent their own layout."""

    def __init__(self, name, fields, stride, step_mode='vertex'):
        self.name = name
        self.fields = fields
        self.stride = stride
        self.step_mode = step_mode

    def attributes(self):
        """[(shaderLocation, offset, format), ...] for WebGPU / WebGL."""
        return [(i, f.offset, f.kind) for i, f in enumerate(self.fields)]

    def wgsl_fields(self):
        return ', '.join('%s: %s' % (f.name, f.fmt) for f in self.fields)


SOLID_LAYOUT = VertexLayout('solid', [
    Field('pos', 'float32x2', 0, 'vec2<f32>'),
    Field('color', 'float32x4', 8, 'vec4<f32>'),
], stride=24)

TEX_LAYOUT = VertexLayout('tex', [
    Field('pos', 'float32x2', 0, 'vec2<f32>'),
    Field('uv', 'float32x2', 8, 'vec2<f32>'),
    Field('color', 'float32x4', 16, 'vec4<f32>'),
], stride=32)

# Per-instance data (Decision 12): same schema mechanism, step_mode
# 'instance'. SCS batches quads today; instancing is the next step and
# it reuses this layout instead of inventing a second one.
INSTANCE_LAYOUT = VertexLayout('instance', [
    Field('model', 'float32x4', 0, 'vec4<f32>'),  # placeholder: 4x4 in 4 rows
], stride=16, step_mode='instance')


def uniform_buffer_size(byte_size):
    """WebGPU uniform buffers must be 256-byte aligned."""
    return int(math.ceil(byte_size / 256.0) * 256)


def pack_solid_vertex(x, y, r, g, b, a):
    return (float(x), float(y), float(r), float(g), float(b), float(a))


def pack_tex_vertex(x, y, u, v, r, g, b, a):
    return (float(x), float(y), float(u), float(v),
            float(r), float(g), float(b), float(a))


# ----------------------------------------------------------------------
# 5. Pipeline identity + caching (first-class, not an optimisation)
# ----------------------------------------------------------------------

class PipelineDescriptor:
    """Canonical pipeline identity. Shaders, vertex layout, blend/depth,
    attachment format, sample count ALL participate (Decision 5).
    Material properties that change pipelines (e.g. mask vs RGBA) are
    part of the descriptor; ordinary values (colour, opacity) are NOT --
    they are uniforms / vertex data, so editing them never creates a
    new pipeline."""

    def __init__(self, shader_name, vertex_layout, blend=None,
                 depth_test=False, attachment_format='rgba8unorm',
                 sample_count=1, mask=False):
        self.shader_name = shader_name
        self.vertex_layout = vertex_layout
        self.blend = blend if blend is not None else BLEND_STRAIGHT_ALPHA
        self.depth_test = depth_test
        self.attachment_format = attachment_format
        self.sample_count = sample_count
        self.mask = mask  # text-atlas (alpha mask) vs RGBA image

    def key(self):
        layout = self.vertex_layout
        return (self.shader_name, layout.name, layout.stride,
                tuple((f.name, f.kind, f.offset) for f in layout.fields),
                str(self.blend), self.depth_test,
                self.attachment_format, self.sample_count, self.mask)


class PipelineCache:
    """One cache per renderer. get_or_create() is the ONLY way to make
    a pipeline; backends pass a factory that compiles for their API."""

    def __init__(self, stats=None):
        self._cache = {}
        self.stats = stats if stats is not None else STATS

    def get_or_create(self, descriptor, factory):
        k = descriptor.key()
        hit = self._cache.get(k)
        if hit is not None:
            self.stats.pipeline_cache_hits += 1
            return hit
        pipe = factory(descriptor)
        self._cache[k] = pipe
        self.stats.pipeline_creations += 1
        return pipe

    def clear(self):
        self._cache.clear()

    def __len__(self):
        return len(self._cache)


# ----------------------------------------------------------------------
# 6. Shaders: shared interface metadata + backend-native escape hatch
# ----------------------------------------------------------------------

class ShaderSet:
    """One shader, two spellings, one interface. GLSL and WGSL do NOT
    transfer (Decision 6): they are separate strings sharing the
    interface metadata below. `native` is the escape hatch: a caller
    may supply a backend-native shader that still declares this
    interface, and the backend validates it against the metadata."""

    def __init__(self, name, glsl_vs, glsl_fs, wgsl, attributes, uniforms):
        self.name = name
        self.glsl_vs = glsl_vs
        self.glsl_fs = glsl_fs
        self.wgsl = wgsl
        self.attributes = attributes  # [(name, VertexLayout field), ...]
        self.uniforms = uniforms      # [(name, kind), ...] e.g. ('u_res','vec2')
        self.native = {}              # {'webgl2': src, 'webgpu': src}


SHADERS = {}  # filled by backends at import (keeps this file backend-free)


def register_shader(shader_set):
    SHADERS[shader_set.name] = shader_set
    return shader_set


# ----------------------------------------------------------------------
# 7. Binding convention -- stable, explicit, shared layouts
# ----------------------------------------------------------------------
# WebGPU: group 0 = frame/view, group 1 = material, group 2 = object.
# WebGL:  texture unit 0 = material texture, unit 1 reserved for future.
# `layout: "auto"` is FORBIDDEN in SCS WebGPU code: explicit layouts let
# bind groups be reused across pipelines that share a group (Decision 7).
# Previous SCS code used one group for everything + auto layout; that is
# the bug this convention fixes.

BINDING = {
    'frame': 0,     # WebGPU group 0: resolution uniform
    'material': 1,  # WebGPU group 1: sampler + texture + mask uniform
    'object': 2,    # WebGPU group 2: per-object data (reserved)
}

BINDING_LAYOUTS = {
    # (group, binding) -> (kind, description)
    (0, 0): ('uniform', 'u_res vec2<f32>'),
    (1, 0): ('sampler', 'u_sampler'),
    (1, 1): ('texture', 'u_tex texture_2d<f32>'),
    (1, 2): ('uniform', 'u_mask u32'),
    (2, 0): ('uniform', 'u_object (reserved)'),
}


# ----------------------------------------------------------------------
# 3. Separate create / update / record / submit
# ----------------------------------------------------------------------

class PassDescriptor:
    """Explicit pass semantics (Decision 14): attachments, load/store,
    clear, whether the result must survive. Backends translate this to
    GPURenderPassDescriptor / gl.clear + viewport; they do not invent
    pass semantics per draw call."""

    def __init__(self, clear_color=(1.0, 1.0, 1.0, 1.0), load_op='clear',
                 store_op='store', preserve=False, label='scs-frame'):
        self.clear_color = clear_color
        self.load_op = load_op
        self.store_op = store_op
        self.preserve = preserve
        self.label = label


# ----------------------------------------------------------------------
# 9. Data by update frequency + dirty tracking
# ----------------------------------------------------------------------

class DirtySet:
    """STATIC / MATERIAL / FRAME / OBJECT buckets (Decision 9). Updating
    a transform must not rewrite material or geometry data."""

    def __init__(self):
        self.buckets = {'static': False, 'material': False,
                        'frame': False, 'object': False}

    def mark(self, bucket):
        self.buckets[bucket] = True

    def take(self, bucket):
        v = self.buckets[bucket]
        self.buckets[bucket] = False
        return v


# ----------------------------------------------------------------------
# 10. Allocation for many small records: suballocated arenas
# ----------------------------------------------------------------------

class Arena:
    """Suballocated arena (Decision 10): ONE buffer, many records.
    `alloc(size, alignment)` returns an offset; `write(offset, data)`
    stages CPU data; the backend uploads the arena in one call.
    This replaces 'one object == one buffer' and 'one batch == one
    buffer per frame' (which allocated every frame in old SCS WebGPU)."""

    def __init__(self, capacity=1 << 16, alignment=256):
        self.capacity = capacity
        self.alignment = alignment
        self.cursor = 0
        self.staged = {}  # offset -> list of floats

    def reset(self):
        self.cursor = 0
        self.staged.clear()

    def _align(self, n):
        return int(math.ceil(n / float(self.alignment)) * self.alignment)

    def alloc(self, byte_size):
        off = self._align(self.cursor)
        self.cursor = off + self._align(byte_size)
        if self.cursor > self.capacity:
            # Grow 2x (amortised); the backend recreates its GPU buffer.
            while self.capacity < self.cursor:
                self.capacity *= 2
        return off

    def write(self, offset, data):
        self.staged[offset] = list(data)

    def grows(self):
        return self.cursor > (self.capacity // 2)


class VertexArena(Arena):
    """Float32 vertex arena: alloc in floats, backend uploads once."""

    def alloc_floats(self, n_floats):
        return self.alloc(n_floats * 4) // 4

    def staged_floats(self):
        if not self.staged:
            return []
        out = []
        for off in sorted(self.staged):
            out.extend(self.staged[off])
        return out


# ----------------------------------------------------------------------
# 12. Batching / instancing: BatchKey + Batcher
# ----------------------------------------------------------------------

class BatchKey:
    """Batches stay splittable (Decision 12): same pipeline + texture +
    blend == one batch; different texture / mask / blend splits it.
    Logical objects keep their identity in the scene layer; the batcher
    only groups their triangles."""

    def __init__(self, pipeline_key, texture_key, blend_key):
        self.pipeline_key = pipeline_key
        self.texture_key = texture_key
        self.blend_key = blend_key

    def key(self):
        return (self.pipeline_key, self.texture_key, self.blend_key)

    def __hash__(self):
        return hash(self.key())

    def __eq__(self, other):
        return isinstance(other, BatchKey) and self.key() == other.key()


class Batcher:
    def __init__(self):
        self.batches = {}  # BatchKey -> list of floats

    def add(self, batch_key, floats):
        self.batches.setdefault(batch_key, []).extend(floats)

    def clear(self):
        self.batches.clear()

    def items(self):
        return list(self.batches.items())


# ----------------------------------------------------------------------
# 15. Texture creation: policy-rich descriptor, not just loadImage()
# ----------------------------------------------------------------------

class TextureDescriptor(Resource):
    """Format, size, mips, usage, compression, sampling -- all explicit
    (Decision 15). Loading is separate from allocation and upload."""

    def __init__(self, label, width, height, fmt='rgba8unorm',
                 mip_levels=1, usage=('texture_binding', 'copy_dst'),
                 sampler=None, compression=None, owner=None):
        super().__init__(label, owner)
        self.width = int(width)
        self.height = int(height)
        self.format = fmt
        self.mip_levels = int(mip_levels)
        self.usage = tuple(usage)
        self.compression = compression
        self.sampler = sampler or {
            'magFilter': 'linear', 'minFilter': 'linear',
            'wrapS': 'clamp-to-edge', 'wrapT': 'clamp-to-edge',
            'anisotropy': 1,
        }
        if compression is not None:
            raise UnsupportedError(
                'Compressed textures (%s) are not yet supported; '
                'pass compression=None' % compression)

    def validate(self, capability):
        if self.width > capability.max_texture_size or \
                self.height > capability.max_texture_size:
            raise UnsupportedError(
                'Texture %dx%d exceeds max %d on %s'
                % (self.width, self.height, capability.max_texture_size,
                   capability.backend))
        if self.mip_levels > 1:
            capability.require('mipmaps')

    def dispose(self):
        super().dispose()


# ----------------------------------------------------------------------
# 11. Async upload / readback: submission != completion != CPU access
# ----------------------------------------------------------------------
# API rule: NO synchronous getter that secretly waits for the GPU.
# readback() returns a Promise; on_readback(cb) fires when the GPU is
# done. Picking / screenshots / inspection tools use this, never a
# blocking read in the render loop (Decision 11).

class AsyncReadback:
    def __init__(self, backend):
        self.backend = backend
        self._pending = []

    def request(self, x, y, w, h):
        """Returns a JS Promise resolving to pixel data (RGBA bytes)."""
        p = self.backend._readback_promise(int(x), int(y), int(w), int(h))
        self._pending.append(p)
        return p

    def pending_count(self):
        return len(self._pending)


# ----------------------------------------------------------------------
# 19. Lifecycle: init states, capability negotiation, device recovery
# ----------------------------------------------------------------------

STATE_UNINITIALIZED = 'uninitialized'
STATE_INITIALIZING = 'initializing'
STATE_READY = 'ready'
STATE_LOST = 'lost'
STATE_FAILED = 'failed'


class Lifecycle:
    """Init is a state machine, not a constructor assumption (Decision 19).
    Resource DESCRIPTORS (PipelineDescriptor, TextureDescriptor) are
    retained so recovery can recreate backend handles after loss."""

    def __init__(self):
        self.state = STATE_UNINITIALIZED
        self.error = None
        self.descriptors = []  # retained for recovery
        self.on_lost = None
        self.on_recovered = None

    def retain(self, descriptor):
        self.descriptors.append(descriptor)

    def mark_lost(self, err):
        self.state = STATE_LOST
        self.error = err
        if self.on_lost:
            try:
                self.on_lost(err)
            except Exception:
                pass

    def mark_ready(self):
        self.state = STATE_READY
        self.error = None
        if self.on_recovered:
            try:
                self.on_recovered()
            except Exception:
                pass
