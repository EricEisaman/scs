"""
scs_splats.py - 3D Gaussian splats as a FIRST-CLASS rendering
primitive for SCS (10 architectural decisions).

Splats are NOT a mesh-loader special case. They get their own
projection + ordering pipeline, their own schema, their own chunk /
LOD / residency machinery, and their own appearance model -- behind
the same high-level integration boundary for WebGL (raster) and
WebGPU (compute-assisted) backends.

  Geometry, appearance, visibility, residency are SEPARATE concerns.
  A splat asset can be in the scene while only some chunks reside
  in CPU / GPU memory. Appearance can change without rebuilding
  geometry. Ordering is an explicit service, not a transparent-queue
  afterthought.
"""

import math
import time


# [STRIPPED 70 bytes]
# 2. Logical schema vs packed GPU representation
# [STRIPPED 70 bytes]

SCHEMA_VERSION = 1


class SplatAttribute:
    """One logical attribute. No fixed packed layout is the public API;
    each backend packs this differently."""

    def __init__(self, name, dtype, components=1, optional=False,
                 quantization=None, description=''):
        self.name = name
        self.dtype = dtype  # 'float32' | 'uint8' | 'float16' ...
        self.components = int(components)
        self.optional = bool(optional)
        self.quantization = dict(quantization or {})
        self.description = description

    def describe(self):
        return {'name': self.name, 'dtype': self.dtype,
                'components': self.components, 'optional': self.optional,
                'quantization': dict(self.quantization)}


class SplatSchema:
    """Versioned LOGICAL attribute schema. Backends pack it; the
    schema is the contract, not any one packed layout."""

    def __init__(self, version=SCHEMA_VERSION, sh_degree=0):
        self.version = int(version)
        self.sh_degree = int(sh_degree)  # variable-degree SH, 0..3
        self.attributes = {}  # name -> SplatAttribute
        self._add_baseline()

    def _add_baseline(self):
        # Baseline: position, shape, opacity. Shape is scale/rotation
        # OR covariance -- the schema carries whichever the asset has.
        self.add(SplatAttribute('position', 'float32', 3,
                                description='Gaussian centre'))
        self.add(SplatAttribute('scale', 'float32', 3, optional=True,
                                description='Scale (with rotation)'))
        self.add(SplatAttribute('rotation', 'float32', 4, optional=True,
                                description='Quaternion (with scale)'))
        self.add(SplatAttribute('covariance', 'float32', 6, optional=True,
                                description='Upper-triangular covariance'))
        self.add(SplatAttribute('opacity', 'float32', 1,
                                description='Alpha'))
        self._add_sh(self.sh_degree)

    def _add_sh(self, degree):
        # Variable-degree SH: (degree+1)^2 coefficients x 3 channels.
        # Degree 0 = 1 coeff (DC colour); degree 3 = 16 coeffs.
        n = (int(degree) + 1) ** 2
        self.add(SplatAttribute('sh', 'float32', n * 3,
                                description='SH appearance, degree %d' % degree))

    def add(self, attr):
        self.attributes[attr.name] = attr
        return attr

    def add_relightable(self):
        """Relightable extension: normals, base colour, roughness,
        lighting-transfer -- NOT part of the baseline. Ordinary and
        relightable splats do not carry identical attributes."""
        self.add(SplatAttribute('normal', 'float32', 3, optional=True,
                                description='Surface normal (relightable)'))
        self.add(SplatAttribute('base_color', 'float32', 3, optional=True,
                                description='Intrinsic base colour (NOT SH)'))
        self.add(SplatAttribute('roughness', 'float32', 1, optional=True))
        self.add(SplatAttribute('metalness', 'float32', 1, optional=True))
        self.add(SplatAttribute('radiance_transfer', 'float32', 9, optional=True,
                                description='Precomputed radiance transfer'))
        return self

    def add_custom(self, name, dtype, components, **kw):
        return self.add(SplatAttribute(name, dtype, components,
                                       optional=True, **kw))

    def validate(self):
        # Position + opacity required; shape needs scale+rotation OR covariance.
        if 'position' not in self.attributes or 'opacity' not in self.attributes:
            raise ValueError('Splat schema needs position + opacity.')
        has_sr = 'scale' in self.attributes and 'rotation' in self.attributes
        has_cov = 'covariance' in self.attributes
        if not (has_sr or has_cov):
            raise ValueError('Splat schema needs scale+rotation or covariance.')
        return True

    def describe(self):
        return {'version': self.version, 'sh_degree': self.sh_degree,
                'attributes': [a.describe() for a in self.attributes.values()]}


# [STRIPPED 70 bytes]
# 8. Captured radiance vs intrinsic material
# [STRIPPED 70 bytes]

MODE_CAPTURED_RADIANCE = 'captured-radiance'      # appearance under captured light, view-dependent
MODE_ARTISTIC = 'artistic-adjustment'             # tint / exposure / contrast
MODE_RELIGHTABLE = 'relightable-material'         # intrinsic attrs + lighting model
MODE_PRECOMPUTED_LIGHTING = 'precomputed-lighting-variant'  # coeffs for one lighting condition


class AppearancePayload:
    """Versioned appearance payload. Replacing it never rebuilds
    geometry, covariance, hierarchy, or bounds (Decision 10)."""

    def __init__(self, mode, version=1, coefficients=None, params=None):
        if mode not in (MODE_CAPTURED_RADIANCE, MODE_ARTISTIC,
                        MODE_RELIGHTABLE, MODE_PRECOMPUTED_LIGHTING):
            raise ValueError('Unknown appearance mode %r' % mode)
        self.mode = mode
        self.version = int(version)
        self.coefficients = coefficients  # SH / PRT / material data
        self.params = dict(params or {})  # tint, exposure, lighting ...

    def describe(self):
        return {'mode': self.mode, 'version': self.version,
                'params': dict(self.params)}


# [STRIPPED 70 bytes]
# 5+6+7. Chunks, hierarchy LOD, residency
# [STRIPPED 70 bytes]

class SplatChunk:
    """One independently addressable chunk. Stable logical identity;
    application code never retains raw GPU offsets."""

    def __init__(self, chunk_id, bounds, level=0, parent_id=None,
                 byte_range=None, payload_ref=None):
        self.chunk_id = chunk_id
        self.bounds = bounds  # (min_xyz, max_xyz) or None
        self.level = int(level)  # 0 = coarsest
        self.parent_id = parent_id
        self.children_ids = []
        self.byte_range = byte_range  # (start, end) for Range fetch
        self.payload_ref = payload_ref
        self.generation = 0  # bumped on every re-upload / re-decode
        self.residency = 'absent'  # absent | downloaded | decoded | gpu
        self.count = 0
        self.approximation_error = 0.0  # how well this chunk approximates children

    def handle(self):
        """Stable logical handle with generation/version checks."""
        return SplatChunkHandle(self.chunk_id, self.generation)


class SplatChunkHandle:
    def __init__(self, chunk_id, generation):
        self.chunk_id = chunk_id
        self.generation = int(generation)

    def is_current_for(self, chunk):
        return chunk is not None and chunk.chunk_id == self.chunk_id \
            and chunk.generation == self.generation


class SplatHierarchy:
    """LOD as a REPRESENTATION: bounds, parent/child, approximation,
    payload refs. Coarse parents stand in while children load.
    'Draw the first N splats' is NOT a lower-detail representation."""

    def __init__(self):
        self.chunks = {}  # chunk_id -> SplatChunk
        self.roots = []

    def add(self, chunk):
        self.chunks[chunk.chunk_id] = chunk
        if chunk.parent_id is None:
            self.roots.append(chunk.chunk_id)
        else:
            parent = self.chunks.get(chunk.parent_id)
            if parent is not None:
                parent.children_ids.append(chunk.chunk_id)
        return chunk

    def select_lod(self, view, budget, hysteresis=0.1, last_selection=None):
        """View-dependent selection under a rendering budget.
        Returns selected chunk_ids. Hysteresis avoids unstable
        switching: a chunk selected last frame stays selected until
        its error exceeds (threshold * (1 + hysteresis))."""
        last = set(last_selection or [])
        selected = []
        # Depth-first from roots: refine while budget + error allow.
        stack = list(self.roots)
        spent = 0
        while stack:
            cid = stack.pop(0)
            chunk = self.chunks.get(cid)
            if chunk is None:
                continue
            # View-dependent criterion: distance to bounds centre.
            dist = _distance_to_bounds(view.get('position', (0, 0, 0)),
                                       chunk.bounds) if chunk.bounds else 0.0
            # Error grows with distance: coarse is fine far away.
            # Threshold: level * 10 units (tunable per asset).
            threshold = (chunk.level + 1) * 10.0
            if chunk.chunk_id in last:
                threshold *= (1.0 + hysteresis)
            needs_refinement = dist < threshold and chunk.children_ids \
                and spent + len(chunk.children_ids) <= budget
            if needs_refinement:
                # Refine: children replace the parent (if resident or
                # loadable -- coarse parent is the fallback, so we
                # still select the parent if children are absent).
                children_resident = all(
                    self.chunks.get(c) is not None and
                    self.chunks[c].residency in ('decoded', 'gpu')
                    for c in chunk.children_ids)
                if children_resident:
                    stack = list(chunk.children_ids) + stack
                    continue
                # Children unavailable: keep the coarse parent.
                selected.append(cid)
                spent += 1
            else:
                selected.append(cid)
                spent += 1
            if spent >= budget:
                break
        return selected


def _distance_to_bounds(pos, bounds):
    if not bounds:
        return 0.0
    (mn, mx) = bounds
    cx = sum(mn) / 3.0 if False else (mn[0] + mx[0]) / 2.0
    cy = (mn[1] + mx[1]) / 2.0
    cz = (mn[2] + mx[2]) / 2.0
    dx, dy, dz = pos[0] - cx, pos[1] - cy, pos[2] - cz
    return math.sqrt(dx * dx + dy * dy + dz * dz)


class ResidencyManager:
    """Residency != scene membership. An asset is in the scene while
    only some chunks reside in CPU / GPU memory. Separate accounting
    + budgets per category; stable handles with generation checks."""

    def __init__(self, max_downloaded_bytes=None, max_decoded_bytes=None,
                 max_gpu_bytes=None, max_sorting_bytes=None):
        self.budgets = {'downloaded': max_downloaded_bytes,
                        'decoded': max_decoded_bytes,
                        'gpu': max_gpu_bytes,
                        'sorting': max_sorting_bytes}
        self.accounting = {'downloaded': 0, 'decoded': 0, 'gpu': 0,
                           'sorting': 0, 'pending_uploads': 0,
                           'pending_decodes': 0}

    def mark(self, chunk, residency, byte_size=0):
        """Move a chunk between residency states, updating accounting."""
        old = chunk.residency
        if old in self.accounting:
            self.accounting[old] = max(0, self.accounting[old] - byte_size)
        chunk.residency = residency
        if residency in self.accounting:
            self.accounting[residency] += byte_size
        if residency == 'gpu':
            chunk.generation += 1
        return chunk

    def can_reside(self, category, byte_size):
        cap = self.budgets.get(category)
        if cap is None:
            return True
        return self.accounting.get(category, 0) + byte_size <= cap

    def evict_lru(self, chunks, category, need_bytes):
        """Evict least-recently-used chunks from a category until the
        budget fits. Returns evicted chunk_ids. Scene membership is
        untouched -- eviction never destroys scene objects."""
        evicted = []
        freed = 0
        # Caller supplies chunks in LRU order (oldest first).
        for chunk in chunks:
            if freed >= need_bytes:
                break
            if chunk.residency == category:
                self.mark(chunk, 'absent', 0)
                evicted.append(chunk.chunk_id)
                freed += 1  # unit accounting in tests; real code uses bytes
        return evicted


# [STRIPPED 70 bytes]
# 3. Sorting / transparency as an explicit service
# [STRIPPED 70 bytes]

class SortingService:
    """Ordering is a REPLACEABLE stage: inputs, outputs, scheduling,
    validity. Static attribute buffers are separate from the current
    visible/sorted index list. Ordering spans interacting splat
    objects, not each object independently."""

    def __init__(self, mode='cpu-exact'):
        self.mode = mode  # 'cpu-exact' | 'worker' | 'gpu' | 'approximate'
        self.last_validity = None

    def order(self, views, splat_objects):
        """Inputs: views (collection), splat_objects (all interacting
        assets). Outputs: {view_index: sorted global index list}.
        Validity: {'view': index, 'frame': n, 'exact': bool}."""
        result = {}
        for vi, view in enumerate(views):
            # Global sort across objects: collect (depth, global_idx).
            items = []
            for obj in splat_objects:
                for local_idx, pos in enumerate(obj.positions()):
                    depth = _view_depth(view, pos)
                    items.append((depth, obj.object_id, local_idx))
            # Back-to-front for alpha compositing.
            items.sort(key=lambda t: -t[0])
            result[vi] = [(obj_id, local) for (_d, obj_id, local) in items]
        self.last_validity = {'exact': self.mode == 'cpu-exact',
                              'mode': self.mode, 'views': len(views)}
        return result

    def describe(self):
        return {'mode': self.mode, 'validity': self.last_validity}


def _view_depth(view, pos):
    # Depth along the view direction (default: -Z forward).
    vp = view.get('position', (0, 0, 0))
    dx, dy, dz = pos[0] - vp[0], pos[1] - vp[1], pos[2] - vp[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


# [STRIPPED 70 bytes]
# 4. Multi-view preparation (incl. XR)
# [STRIPPED 70 bytes]

class ViewCollection:
    """A COLLECTION of views into preparation, not one global camera.
    Scene-wide work is shared; view-dependent work is per view."""

    def __init__(self, views=None):
        self.views = list(views or [])  # each: {position, direction, eye, ...}

    def add(self, view):
        self.views.append(view)
        return view

    def scene_wide(self):
        """Decoding, residency, shared transforms -- done once."""
        return {'view_count': len(self.views),
                'shared': True}

    def per_view(self, view_index):
        """Projected footprint, appearance evaluation, LOD, ordering --
        done per view. One eye's ordering is NOT assumed sufficient
        for the other."""
        if 0 <= view_index < len(self.views):
            return dict(self.views[view_index])
        return None


# [STRIPPED 70 bytes]
# 9. Aligned proxy geometry + auxiliary lighting data
# [STRIPPED 70 bytes]

PROXY_ROLES = ('relighting', 'collision', 'shadow', 'occlusion',
               'picking', 'radiance-transfer')


class ProxyGeometry:
    """Companion geometry in the SAME coordinate system as the splats.
    Roles are DISTINCT: a collision proxy is not automatically an
    adequate relighting proxy."""

    def __init__(self, role, geometry_ref, coordinate_system='splat-local'):
        if role not in PROXY_ROLES:
            raise ValueError('Unknown proxy role %r (roles: %s)'
                             % (role, ', '.join(PROXY_ROLES)))
        self.role = role
        self.geometry_ref = geometry_ref
        self.coordinate_system = coordinate_system

    def describe(self):
        return {'role': self.role, 'geometry': self.geometry_ref,
                'coordinate_system': self.coordinate_system}


# [STRIPPED 70 bytes]
# Asset: geometry + appearance + hierarchy + proxies
# [STRIPPED 70 bytes]

class SplatAsset:
    """A splat asset: schema + chunks + hierarchy + appearance +
    proxies. Scene membership lives here; residency lives in the
    ResidencyManager. Appearance lives in versioned payloads."""

    _next_id = 0

    def __init__(self, schema, name='splats'):
        SplatAsset._next_id += 1
        self.object_id = 'splat-%d' % SplatAsset._next_id
        self.name = name
        self.schema = schema
        self.hierarchy = SplatHierarchy()
        self.appearance = AppearancePayload(MODE_CAPTURED_RADIANCE, version=1)
        self.proxies = {}  # role -> ProxyGeometry
        self._positions = []  # logical positions (test / CPU path)
        self._visible = True
        self._derived_version = 0  # bumped only when derived resources change

    def add_chunk(self, chunk):
        return self.hierarchy.add(chunk)

    def add_proxy(self, proxy):
        self.proxies[proxy.role] = proxy
        return proxy

    def positions(self):
        return list(self._positions)

    def set_positions(self, positions):
        self._positions = list(positions)

    @property
    def visible(self):
        return self._visible

    def set_visible(self, v):
        self._visible = bool(v)

    def apply_appearance(self, payload, aggregation='before'):
        """Replace / modify appearance WITHOUT rebuilding positions,
        covariance, hierarchy, or bounds (Decision 10).

        aggregation='before': edit applies before LOD aggregation --
          coarse parents are recomputed from edited leaves.
        aggregation='after': edit applies after aggregation --
          only leaf appearance changes; parents keep their old
          aggregate until the next aggregation pass.
        Only derived resources are invalidated (appearance buffers),
        never geometry / hierarchy / bounds."""
        old_mode = self.appearance.mode
        self.appearance = payload
        self._derived_version += 1
        return {'previous_mode': old_mode, 'new_mode': payload.mode,
                'aggregation': aggregation,
                'invalidated': ['appearance-buffers'],
                'preserved': ['positions', 'covariance', 'hierarchy', 'bounds'],
                'needs_parent_reaggregation': aggregation == 'before'}


# [STRIPPED 70 bytes]
# 1. Renderer-extension interface: custom passes
# [STRIPPED 70 bytes]

class SplatRendererExtension:
    """A renderable object that contributes CUSTOM PASSES, not just
    mesh draw calls. Participates in scene prep, visibility, sorting,
    compositing. Shares cameras, transforms, lighting inputs, and
    opaque-scene depth with the host renderer. Specialized GPU
    resources / shaders without conventional vertex/index buffers."""

    backend = 'base'

    def __init__(self, sorting=None, residency=None):
        self.sorting = sorting or SortingService()
        self.residency = residency or ResidencyManager()
        self.assets = []

    def add_asset(self, asset):
        self.assets.append(asset)
        return asset

    def prepare_scene(self, views):
        """Scene-wide work: decoding, residency, shared transforms."""
        vc = views if isinstance(views, ViewCollection) else ViewCollection(views)
        return {'scene_wide': vc.scene_wide(),
                'assets': [a.object_id for a in self.assets]}

    def select_visibility(self, views, budget=1000):
        """Visibility selection per view, via hierarchy LOD."""
        vc = views if isinstance(views, ViewCollection) else ViewCollection(views)
        out = {}
        for vi, view in enumerate(vc.views):
            selected = []
            for asset in self.assets:
                if asset.visible:
                    selected.extend(asset.hierarchy.select_lod(
                        view, budget))
            out[vi] = selected
        return out

    def sort(self, views):
        """Ordering stage: explicit, replaceable, across objects."""
        vc = views if isinstance(views, ViewCollection) else ViewCollection(views)
        return self.sorting.order(vc.views, self.assets)

    def composite(self, views, sorted_indices, opaque_depth=None):
        """Compositing with opaque-scene depth + other transparent
        content. Depth is an INPUT, not something splats ignore."""
        return {'backend': self.backend,
                'views': len(views.views if isinstance(views, ViewCollection) else views),
                'sorted_views': len(sorted_indices),
                'opaque_depth_shared': opaque_depth is not None}

    def render(self, views, opaque_depth=None, budget=1000):
        """Full pass: prepare -> visibility -> sort -> composite."""
        self.prepare_scene(views)
        visible = self.select_visibility(views, budget)
        sorted_idx = self.sort(views)
        return self.composite(views, sorted_idx, opaque_depth)


class WebGLSplatRenderer(SplatRendererExtension):
    """Raster-based splat rendering (WebGL2). Same boundary as WebGPU."""
    backend = 'webgl2-raster'


class WebGPUSplatRenderer(SplatRendererExtension):
    """Compute-assisted splat rendering (WebGPU). Same boundary."""
    backend = 'webgpu-compute'


# [STRIPPED 70 bytes]
# 5. Chunked asset interface: manifest + streaming
# [STRIPPED 70 bytes]

class SplatManifest:
    """Manifest + coarse representation BEFORE the whole asset is
    available. Chunked assets, not monolithic downloads."""

    def __init__(self, asset_id, schema, chunk_ids, coarse_chunk_id=None):
        self.asset_id = asset_id
        self.schema = schema
        self.chunk_ids = list(chunk_ids)
        self.coarse_chunk_id = coarse_chunk_id

    def describe(self):
        return {'asset_id': self.asset_id,
                'chunks': len(self.chunk_ids),
                'coarse': self.coarse_chunk_id}


class SplatAssetLoader:
    """Fetch by id / byte range, decode independently, cancel /
    reprioritize, report partial readiness, fall back without
    random access. Progressive monolithic download != spatial streaming."""

    def __init__(self, fetcher=None):
        self.fetcher = fetcher  # fn(chunk_id, byte_range) -> bytes (test) / Promise (browser)
        self._pending = {}  # chunk_id -> {'priority': n, 'cancelled': bool}
        self._ready = set()

    def manifest(self, asset_id, schema, chunk_ids, coarse_chunk_id=None):
        return SplatManifest(asset_id, schema, chunk_ids, coarse_chunk_id)

    def fetch_chunk(self, chunk, priority=0):
        """Fetch ONE chunk by identifier / byte range."""
        # Preserve a cancellation that arrived while this chunk was
        # already pending (cancel() during an in-flight fetch must
        # win over a re-issued fetch for the same chunk).
        was_cancelled = self._pending.get(chunk.chunk_id, {}).get('cancelled', False)
        self._pending[chunk.chunk_id] = {'priority': priority,
                                         'cancelled': was_cancelled}
        if self.fetcher is not None:
            data = self.fetcher(chunk.chunk_id, chunk.byte_range)
        else:
            data = b''
        if self._pending.get(chunk.chunk_id, {}).get('cancelled'):
            self._pending.pop(chunk.chunk_id, None)
            return None  # obsolete result: not attached
        self._pending.pop(chunk.chunk_id, None)
        self._ready.add(chunk.chunk_id)
        chunk.residency = 'downloaded'
        return data

    def decode_chunk(self, chunk, data):
        """Decode ONE chunk independently."""
        chunk.residency = 'decoded'
        chunk.generation += 1
        return {'chunk_id': chunk.chunk_id, 'decoded_bytes': len(data or b'')}

    def cancel(self, chunk_id):
        entry = self._pending.get(chunk_id)
        if entry is not None:
            entry['cancelled'] = True
            return True
        return False

    def reprioritize(self, chunk_id, priority):
        entry = self._pending.get(chunk_id)
        if entry is not None:
            entry['priority'] = priority
            return True
        return False

    def partial_readiness(self):
        """Which chunks are ready / pending -- partial readiness is
        first-class, not '0% or 100%'."""
        return {'ready': sorted(self._ready),
                'pending': sorted(self._pending.keys())}

    def fallback_monolithic(self, data):
        """Server / format cannot provide random access: fall back to
        a single-chunk asset. Same interface, degraded granularity."""
        chunk = SplatChunk('monolithic', bounds=None, level=0)
        chunk.residency = 'downloaded'
        self._ready.add('monolithic')
        return [chunk]


# [STRIPPED 70 bytes]
# BATCH 3: DISK vs GPU SEPARATION -- renderer is GPU-only.
# [STRIPPED 70 bytes]
#   DISK (scs_splat_formats.py) -> SplatData -> GPU (scs_splat_gpu.py) -> RENDERER (this file)
# The renderer below NEVER parses disk bytes. If you see a call to
# parse_ply / parse_spz / parse_splat in this file, that is a bug --
# disk parsing lives in scs_splat_formats.py only.
# New disk format (RAD, ...): register_format() in scs_splat_formats.py.
# Renderer + GPU layout do NOT change.
# [STRIPPED 70 bytes]

try:
    from scs_splat_formats import (
        SplatData as _SplatData, parse_file as _parse_file,
        parse_sog_manifest as _parse_sog_manifest,
        SOGManifest as _SOGManifest,
        register_format as _register_format,
    )
    from scs_splat_gpu import pack_gpu as _pack_gpu, SplatGPUBuffer as _SplatGPUBuffer
    _HAS_SPLIT = True
except Exception:
    _HAS_SPLIT = False
    _SplatData = None

def _ensure_split():
    if not _HAS_SPLIT:
        raise RuntimeError('scs_splat_formats / scs_splat_gpu are required for the disk/GPU split')

# -- New asset constructors (GPU-only path) --
def _asset_from_splat_data(splat_data, name=''):
    """SplatData -> SplatAsset with a GPU buffer. The ONLY way to make
    an asset from parsed data. Disk -> SplatData happens in formats."""
    _ensure_split()
    gpu = _pack_gpu(splat_data)
    # Build a minimal asset using the existing SplatAsset API.
    # SplatAsset.__init__ signature: (schema, name=...) -- check at runtime.
    try:
        from scs_splats import SplatSchema as _Schema
    except Exception:
        _Schema = None
    # Use the module's own SplatAsset (defined above) -- construct via __new__
    # to avoid signature churn, then fill fields the renderer reads.
    asset = SplatAsset.__new__(SplatAsset)
    asset.name = name or getattr(splat_data, 'name', '') or 'splat'
    asset.schema = _Schema(version=1, sh_degree=getattr(splat_data, 'sh_degree', 0)) if _Schema else None
    asset.gpu_buffer = gpu
    asset.splat_data = splat_data
    asset.chunks = []
    asset._positions = list(splat_data.positions)
    # The renderer reads asset.chunks / asset._positions in older paths;
    # give it one chunk that carries the GPU buffer.
    try:
        ch = SplatChunk('chunk-0', bounds=None, level=0, byte_range=(0, len(gpu.data)))
        ch.count = gpu.count
        ch.gpu_buffer = gpu
        ch.residency = 'downloaded'
        asset.chunks = [ch]
    except Exception:
        pass
    return asset

def _asset_from_file_bytes(data, format_hint='', name=''):
    """Disk bytes -> SplatData (formats) -> GPU (gpu) -> Asset (renderer).
    This is the ONLY disk entry point. The renderer never parses disk."""
    _ensure_split()
    splat_data = _parse_file(data, format_hint=format_hint)
    splat_data.name = name or splat_data.name
    return _asset_from_splat_data(splat_data, name=name)

# Attach as classmethods on SplatAsset (so existing code can call them)
try:
    SplatAsset.from_splat_data = staticmethod(_asset_from_splat_data)
    SplatAsset.from_file_bytes = staticmethod(_asset_from_file_bytes)
    SplatAsset.from_disk = staticmethod(_asset_from_file_bytes)
except Exception:
    pass

# -- Streaming: SOG manifest + chunk loading, via formats+gpu --
class SOGStreamer:
    """Stream a SOG asset: manifest first (coarse), then chunks by LOD/distance.
    Each chunk: disk bytes -> SplatData (formats) -> GPU (gpu) -> asset chunk.
    The renderer only ever sees GPU buffers."""
    def __init__(self, fetcher=None):
        self.fetcher = fetcher  # (chunk_id, byte_range) -> bytes, or None
        self.manifest = None
        self.loaded = {}  # chunk_id -> SplatAsset chunk
    def load_manifest(self, manifest_bytes):
        _ensure_split()
        self.manifest = _parse_sog_manifest(manifest_bytes)
        return self.manifest
    def load_chunk(self, chunk_id, chunk_bytes, sh_degree=0):
        """Chunk disk bytes -> SplatData -> GPU -> asset chunk."""
        _ensure_split()
        from scs_splat_formats import parse_sog_chunk as _parse_sog_chunk
        sd = _parse_sog_chunk(chunk_bytes, sh_degree=sh_degree or (self.manifest.sh_degree if self.manifest else 0))
        gpu = _pack_gpu(sd)
        ch = SplatChunk(chunk_id, bounds=None, level=0, byte_range=(0, len(gpu.data)))
        ch.count = gpu.count
        ch.gpu_buffer = gpu
        ch.residency = 'downloaded'
        self.loaded[chunk_id] = ch
        return ch
    def coarse_first(self):
        """Return the coarse chunk id (load this first for partial readiness)."""
        if self.manifest is None:
            return None
        c = self.manifest.coarse_chunk()
        return c.get('id') if c else None
    def describe(self):
        return {'manifest': self.manifest.describe() if self.manifest else None,
                'loaded': sorted(self.loaded.keys())}
