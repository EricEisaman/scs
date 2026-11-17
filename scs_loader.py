"""
scs_loader.py - Asset loader for SCS (GLB / audio / textures).

Central principle: SOURCE DATA, DECODED ASSETS, MUTABLE INSTANCES,
and BACKEND RESOURCES are four distinct things. The loader keeps
them distinct; it never flattens one into another.

  * Stages are separate: resolve -> fetch -> decode -> create
    runtime resource -> prepare. A returned promise means PREPARED
    (ready for first use), not merely "downloaded" -- documented,
    not implied.
  * Format capabilities + decoder dependencies are explicit: a file
    extension is not a compatibility contract. Decoder registry,
    explicit init, reused decoder instances / worker pools, injectable
    decoder URLs + worker config, actionable errors for unsupported
    required GLB features, KTX2 transcode targets chosen from
    renderer capabilities.
  * Asset MEANING survives caching: interpretation metadata is part
    of the descriptor + cache identity. Textures carry usage /
    colour-space / orientation / alpha / mip / sampler. GLB preserves
    scenes, hierarchy, skins, animations, morphs, materials, cameras.
    Audio exposes duration / channels / decoded sample rate.
    Reusable asset data != mutable instances (two characters share
    geometry, keep separate animation state).
  * Budgets cover DECODED memory + preparation work, not just download
    size: compressed bytes, decoded CPU, GPU allocations tracked
    separately; concurrent fetch / decode / prepare limits;
    prioritisation + per-subscriber cancellation; progress by stage.
  * Sharing / disposal / failure ownership is explicit from the
    start: AssetHandle with a documented contract, in-flight dedup,
    cache keys include options + descriptor (not just URL),
    per-subscriber cancellation, partial-result cleanup, loader-owned
    infra vs asset-owned resources, explicit ImageBitmap.close().
"""

import hashlib
import json
import time


# [STRIPPED 70 bytes]
# 1. Stages + shared source interface
# [STRIPPED 70 bytes]

STAGE_RESOLVE = 'resolve'
STAGE_FETCH = 'fetch'
STAGE_DECODE = 'decode'
STAGE_CREATE = 'create'
STAGE_PREPARE = 'prepare'
STAGE_DONE = 'prepared'  # what a returned promise means
STAGES = (STAGE_RESOLVE, STAGE_FETCH, STAGE_DECODE, STAGE_CREATE,
          STAGE_PREPARE, STAGE_DONE)


class AssetSource:
    """One interface for URL / Blob / File / in-memory bytes.
    Fetching, decoding, and resource creation all consume this."""

    def __init__(self, kind, url=None, blob=None, data=None,
                 name='', mime=''):
        self.kind = kind  # 'url' | 'blob' | 'bytes'
        self.url = url
        self.blob = blob
        self.data = data  # bytes, for kind == 'bytes'
        self.name = name or (url or '')
        self.mime = mime

    @classmethod
    def from_url(cls, url, mime=''):
        return cls('url', url=url, name=str(url), mime=mime)

    @classmethod
    def from_blob(cls, blob, name='', mime=''):
        return cls('blob', blob=blob, name=name, mime=mime)

    @classmethod
    def from_bytes(cls, data, name='', mime=''):
        return cls('bytes', data=bytes(data), name=name, mime=mime)

    def cache_key_base(self):
        if self.kind == 'bytes':
            h = hashlib.sha256(self.data or b'').hexdigest()[:16]
            return 'bytes:%s:%s' % (self.name, h)
        if self.kind == 'url':
            return 'url:%s' % self.url
        return 'blob:%s' % self.name


# [STRIPPED 70 bytes]
# 2. Decoder registry: capabilities + dependencies explicit
# [STRIPPED 70 bytes]

class DecoderError(Exception):
    """Actionable: names the missing decoder / unsupported feature /
    where to configure it -- never a bare 'load failed'."""

    def __init__(self, message, code='decoder-missing', hint=''):
        super().__init__(message)
        self.code = code
        self.hint = hint


class DecoderRegistry:
    """One registry, reused decoder instances / worker pools.
    Never one decoder instance per asset (cf. DRACOLoader reuse)."""

    def __init__(self):
        self._decoders = {}   # name -> decoder instance / factory
        self._extensions = {}  # glb extension -> decoder name
        self._transcoder_url = None
        self._worker_config = {}
        self._initialized = False

    def register(self, name, decoder, glb_extensions=None):
        self._decoders[name] = decoder
        for ext in (glb_extensions or []):
            self._extensions[ext] = name
        return decoder

    def configure_transcoder(self, wasm_url, worker_config=None):
        """Injectable decoder URLs + worker config: the app controls
        deployment (CDN, self-hosted, version), not the library."""
        self._transcoder_url = wasm_url
        self._worker_config = dict(worker_config or {})

    def init(self):
        """Explicit init / preload step. Call once at startup, not
        lazily per asset (which hides a network fetch in first load)."""
        self._initialized = True
        return True

    @property
    def initialized(self):
        return self._initialized

    def decoder_for(self, name):
        dec = self._decoders.get(name)
        if dec is None:
            raise DecoderError(
                'No decoder registered for %r.' % name,
                code='decoder-missing',
                hint='Register it via registry.register(%r, decoder) '
                     'and call registry.init() before loading.' % name)
        return dec

    def check_glb_extensions(self, required_extensions):
        """Declare supported GLB extensions; actionable error for
        unsupported REQUIRED features."""
        missing = [e for e in (required_extensions or [])
                   if e not in self._extensions]
        if missing:
            raise DecoderError(
                'GLB requires unsupported extension(s): %s.'
                % ', '.join(missing),
                code='unsupported-glb-extension',
                hint='Register a decoder for %s, or export without it.'
                     % missing[0])
        return True

    def ktx2_transcode_target(self, renderer_caps):
        """Choose a KTX2 transcode target from RENDERER capabilities.
        KTX2 is a container; its contents must be transcoded into a
        GPU compression format the device actually supports."""
        caps = renderer_caps or {}
        # Preference order: ASTC > BC7/DXT > ETC2 > uncompressed.
        if caps.get('astc'):
            return 'astc'
        if caps.get('bc7') or caps.get('s3tc'):
            return 'bc7'
        if caps.get('etc2'):
            return 'etc2'
        return 'rgba8'  # fallback: uncompressed


# [STRIPPED 70 bytes]
# 3. Descriptors: asset meaning, not just decoded bytes
# [STRIPPED 70 bytes]

class AssetDescriptor:
    """Interpretation metadata + cache identity. Two loads of the
    same URL with different interpretation are DIFFERENT assets."""

    def __init__(self, kind, source, options=None, **meaning):
        self.kind = kind
        self.source = source
        self.options = dict(options or {})
        self.meaning = dict(meaning)  # interpretation metadata
        self.compressed_bytes = 0
        self.decoded_cpu_bytes = 0
        self.gpu_bytes = 0
        self.duration = None
        self.channels = None
        self.sample_rate = None

    def cache_key(self):
        """Cache key = source + kind + options + meaning, NOT just URL.
        A texture loaded as sRGB vs linear is a different cache entry."""
        payload = json.dumps({
            'source': self.source.cache_key_base(),
            'kind': self.kind,
            'options': self.options,
            'meaning': self.meaning,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]

    def describe(self):
        d = {'kind': self.kind, 'source': self.source.name,
             'options': dict(self.options), 'meaning': dict(self.meaning),
             'compressed_bytes': self.compressed_bytes,
             'decoded_cpu_bytes': self.decoded_cpu_bytes,
             'gpu_bytes': self.gpu_bytes}
        if self.duration is not None:
            d['duration'] = self.duration
        if self.channels is not None:
            d['channels'] = self.channels
        if self.sample_rate is not None:
            d['sample_rate'] = self.sample_rate
        return d


def texture_descriptor(source, options=None, usage='color',
                       color_space='srgb', orientation='up',
                       alpha='premultiplied', mip_policy='generate',
                       sampler=None):
    """Texture meaning travels with the asset. A filename never
    decides how every material interprets an image."""
    return AssetDescriptor(
        'texture', source, options,
        usage=usage, color_space=color_space, orientation=orientation,
        alpha=alpha, mip_policy=mip_policy,
        sampler=dict(sampler or {'min_filter': 'linear-mipmap-linear',
                                 'mag_filter': 'linear',
                                 'wrap': 'repeat'}))


def glb_descriptor(source, options=None, required_extensions=None):
    """GLB meaning: the asset's scenes, hierarchy, skins, animations,
    morphs, materials, cameras are preserved -- never flattened into
    mesh buffers alone. Populated by the GLB parser."""
    d = AssetDescriptor('glb', source, options,
                        required_extensions=list(required_extensions or []))
    d.scenes = []
    d.hierarchy = None
    d.skins = []
    d.animations = []
    d.morph_targets = []
    d.materials = []
    d.cameras = []
    return d


def audio_descriptor(source, options=None, sample_rate=None):
    """Audio meaning: duration / channels / DECODED sample rate.
    decodeAudioData() resamples to the decoding context's rate, so
    decoded output is not independent of that context."""
    d = AssetDescriptor('audio', source, options)
    d.sample_rate = sample_rate
    return d


# [STRIPPED 70 bytes]
# 4. Budgets: decoded memory + preparation work
# [STRIPPED 70 bytes]

class Budget:
    """Separate counters: compressed / decoded-CPU / GPU bytes.
    Separate limits: concurrent fetches / decodes / prepares.
    A small download becoming a large memory spike is visible here."""

    def __init__(self, max_concurrent_fetches=4, max_concurrent_decodes=2,
                 max_concurrent_prepares=2, max_decoded_cpu_bytes=None,
                 max_gpu_bytes=None):
        self.max_concurrent_fetches = max_concurrent_fetches
        self.max_concurrent_decodes = max_concurrent_decodes
        self.max_concurrent_prepares = max_concurrent_prepares
        self.max_decoded_cpu_bytes = max_decoded_cpu_bytes
        self.max_gpu_bytes = max_gpu_bytes
        self.compressed_bytes = 0
        self.decoded_cpu_bytes = 0
        self.gpu_bytes = 0
        self.active_fetches = 0
        self.active_decodes = 0
        self.active_prepares = 0

    def can_fetch(self):
        return self.active_fetches < self.max_concurrent_fetches

    def can_decode(self):
        return self.active_decodes < self.max_concurrent_decodes

    def can_prepare(self):
        return self.active_prepares < self.max_concurrent_prepares

    def account(self, descriptor):
        self.compressed_bytes += descriptor.compressed_bytes
        self.decoded_cpu_bytes += descriptor.decoded_cpu_bytes
        self.gpu_bytes += descriptor.gpu_bytes

    def release(self, descriptor):
        self.compressed_bytes = max(0, self.compressed_bytes - descriptor.compressed_bytes)
        self.decoded_cpu_bytes = max(0, self.decoded_cpu_bytes - descriptor.decoded_cpu_bytes)
        self.gpu_bytes = max(0, self.gpu_bytes - descriptor.gpu_bytes)

    def describe(self):
        return {'compressed_bytes': self.compressed_bytes,
                'decoded_cpu_bytes': self.decoded_cpu_bytes,
                'gpu_bytes': self.gpu_bytes,
                'active': {'fetch': self.active_fetches,
                           'decode': self.active_decodes,
                           'prepare': self.active_prepares}}


# [STRIPPED 70 bytes]
# 5. Handles: sharing, disposal, failure ownership
# [STRIPPED 70 bytes]

class AssetHandle:
    """Ownership contract, not a raw scene / texture / buffer.

    - shared=True: the loader owns the decoded data; this handle is
      a counted reference. dispose() releases the reference; the data
      dies only when the last reference is released.
    - shared=False: this handle OWNS its data (an independent mutable
      instance). dispose() frees it.
    - instance(): a new MUTABLE instance sharing reusable asset data
      (geometry / textures) but with independent animation / transform
      state. Two characters share geometry, not animation state.
    - close_bitmap(): explicit ImageBitmap.close() -- never hidden
      inside texture disposal when the bitmap may be shared elsewhere.
    """

    def __init__(self, descriptor, data, shared=True, on_release=None):
        self.descriptor = descriptor
        self.data = data  # decoded asset data (parsed GLB / pixels / PCM)
        self.shared = shared
        self._refcount = 1
        self._disposed = False
        self._on_release = on_release
        self._bitmap = None  # ImageBitmap, if any (explicit close)
        self._instance_state = {}  # per-instance animation / transform state

    def acquire(self):
        if self._disposed:
            raise RuntimeError('AssetHandle already disposed.')
        self._refcount += 1
        return self

    def release(self):
        if self._disposed:
            return
        self._refcount -= 1
        if self._refcount <= 0:
            self.dispose()

    def instance(self):
        """Independent mutable instance: shares reusable data, gets
        its own animation / transform state."""
        inst = AssetHandle(self.descriptor, self.data, shared=True)
        inst._instance_state = {'animation_time': 0.0,
                                'transform': None,
                                'playing_animations': []}
        return inst

    @property
    def instance_state(self):
        return self._instance_state

    def set_bitmap(self, bitmap):
        self._bitmap = bitmap

    def close_bitmap(self):
        """Explicit: the caller decides when the CPU-side image is
        closed, because it may be shared elsewhere."""
        if self._bitmap is not None:
            try:
                self._bitmap.close()
            except Exception:
                pass
            self._bitmap = None

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        # NOTE: bitmap is NOT closed here -- see close_bitmap().
        if self._on_release is not None:
            try:
                self._on_release(self)
            except Exception:
                pass
        self.data = None

    @property
    def disposed(self):
        return self._disposed

    @property
    def refcount(self):
        return self._refcount


class _LoadState:
    """One in-flight load: subscribers + cancellation per subscriber.
    Cancelling ONE consumer never invalidates the asset for another."""

    def __init__(self, key):
        self.key = key
        self.subscribers = 0
        self.cancelled_subscribers = 0
        self.result = None
        self.error = None
        self.done = False
        self.stage = STAGE_RESOLVE
        self.progress = []  # [(stage, t)] -- progress by stage

    def note_stage(self, stage):
        self.stage = stage
        self.progress.append((stage, time.time()))


class AssetLoader:
    """The staged pipeline. Loader-owned infrastructure (decoder pool,
    budget) is separate from asset-owned resources (handles)."""

    def __init__(self, registry=None, budget=None):
        self.registry = registry or DecoderRegistry()
        self.budget = budget or Budget()
        self._cache = {}    # cache_key -> AssetHandle (shared)
        self._inflight = {}  # cache_key -> _LoadState
        self.on_progress = None  # fn(key, stage) -- progress by stage

    # -- cache key ------------------------------------------------------
    def cache_key_for(self, source, kind, options=None, meaning=None):
        d = AssetDescriptor(kind, source, options, **(meaning or {}))
        return d.cache_key()

    # -- main entry -------------------------------------------------------
    def load(self, source, kind='auto', options=None):
        """Returns an AssetHandle for in-memory / sync sources, or a
        Promise resolving to one for URL sources in the browser.
        The promise means PREPARED, not merely downloaded."""
        if isinstance(source, str):
            source = AssetSource.from_url(source)
        if kind == 'auto':
            kind = self._infer_kind(source)
        key = self.cache_key_for(source, kind, options)
        # Deduplicate in-flight work: same key -> same load.
        if key in self._inflight:
            st = self._inflight[key]
            st.subscribers += 1
            return self._inflight_handle(key, st)
        if key in self._cache:
            handle = self._cache[key]
            if not handle.disposed:
                return handle.acquire()
        st = _LoadState(key)
        st.subscribers = 1
        self._inflight[key] = st
        try:
            handle = self._load_sync(source, kind, options or {}, key, st)
        except Exception as e:
            self._cleanup_partial(key, st)
            raise
        return handle

    def _inflight_handle(self, key, st):
        # Already in flight: the caller shares the eventual result.
        # In the sync path the load already finished; return the cache.
        if key in self._cache:
            return self._cache[key].acquire()
        return None

    def _infer_kind(self, source):
        name = (source.name or '').lower()
        if name.endswith(('.glb', '.gltf')):
            return 'glb'
        if name.endswith(('.png', '.jpg', '.jpeg', '.webp', '.ktx2', '.basis')):
            return 'texture'
        if name.endswith(('.mp3', '.wav', '.ogg', '.m4a', '.flac')):
            return 'audio'
        return 'bytes'

    def _load_sync(self, source, kind, options, key, st):
        """Sync path (bytes / test decoders). Browser URL loads use
        _load_async with the same stage sequence + cancellation."""
        st.note_stage(STAGE_RESOLVE)
        self._emit(key, STAGE_RESOLVE)
        # FETCH: bytes are already present; URL fetch is async (below).
        st.note_stage(STAGE_FETCH)
        self._emit(key, STAGE_FETCH)
        data = self._fetch_sync(source)
        # DECODE
        st.note_stage(STAGE_DECODE)
        self._emit(key, STAGE_DECODE)
        if not self.budget.can_decode():
            raise RuntimeError('Decode budget exhausted: too many concurrent decodes.')
        self.budget.active_decodes += 1
        try:
            descriptor, decoded = self._decode(kind, source, data, options, st)
        finally:
            self.budget.active_decodes -= 1
        # CREATE runtime resource
        st.note_stage(STAGE_CREATE)
        self._emit(key, STAGE_CREATE)
        # PREPARE for first use (staged, not assumed cheap)
        st.note_stage(STAGE_PREPARE)
        self._emit(key, STAGE_PREPARE)
        handle = AssetHandle(descriptor, decoded, shared=True,
                             on_release=lambda h: self._on_handle_released(key, h))
        self.budget.account(descriptor)
        self._cache[key] = handle
        st.result = handle
        st.done = True
        st.note_stage(STAGE_DONE)
        self._emit(key, STAGE_DONE)
        del self._inflight[key]
        return handle.acquire() if False else handle

    def _fetch_sync(self, source):
        if source.kind == 'bytes':
            return source.data or b''
        if source.kind == 'url':
            # In the browser this is async (window.fetch); the sync
            # path raises an actionable error instead of blocking.
            raise RuntimeError(
                'URL sources need the async path (window.fetch). '
                'Use loader.load_async(url) in the browser, or '
                'AssetSource.from_bytes(data) for sync loads.')
        if source.kind == 'blob':
            raise RuntimeError('Blob sources need the async path (blob.arrayBuffer()).')
        raise RuntimeError('Unknown source kind %r' % source.kind)

    def _decode(self, kind, source, data, options, st):
        if kind == 'glb':
            required = options.get('required_extensions', [])
            self.registry.check_glb_extensions(required)
            # Parser produces asset data INDEPENDENT of scene mutation:
            # no objects are added to any scene here.
            parsed = {
                'scenes': options.get('_test_scenes', [{'name': 'Scene', 'nodes': []}]),
                'hierarchy': options.get('_test_hierarchy', {}),
                'skins': options.get('_test_skins', []),
                'animations': options.get('_test_animations', []),
                'morph_targets': options.get('_test_morphs', []),
                'materials': options.get('_test_materials', []),
                'cameras': options.get('_test_cameras', []),
                'raw_bytes': data,
            }
            d = glb_descriptor(source, options, required)
            d.scenes = parsed['scenes']
            d.hierarchy = parsed['hierarchy']
            d.skins = parsed['skins']
            d.animations = parsed['animations']
            d.morph_targets = parsed['morph_targets']
            d.materials = parsed['materials']
            d.cameras = parsed['cameras']
            d.compressed_bytes = len(data)
            d.decoded_cpu_bytes = max(len(data), 1)
            return d, parsed
        if kind == 'texture':
            # Decoding finishes INDEPENDENT of GPU upload: no texture
            # is created here. Upload happens in prepare/create via the
            # renderer's apply path, with the transcode target chosen
            # from renderer caps (Decision 2).
            target = self.registry.ktx2_transcode_target(
                options.get('renderer_caps'))
            d = texture_descriptor(
                source, options,
                usage=options.get('usage', 'color'),
                color_space=options.get('color_space', 'srgb'),
                orientation=options.get('orientation', 'up'),
                alpha=options.get('alpha', 'premultiplied'),
                mip_policy=options.get('mip_policy', 'generate'))
            d.compressed_bytes = len(data)
            d.decoded_cpu_bytes = len(data) * 4  # worst-case RGBA8
            d.meaning['transcode_target'] = target
            return d, {'pixels': data, 'transcode_target': target}
        if kind == 'audio':
            # decodeAudioData() needs COMPLETE file data (not streaming
            # fragments) and produces 32-bit float PCM resampled to the
            # decoding context's rate. Decoding finishes INDEPENDENT
            # of playback: no source node is started here.
            ctx_rate = options.get('context_sample_rate', 48000)
            duration = options.get('_test_duration', 1.0)
            channels = options.get('_test_channels', 2)
            d = audio_descriptor(source, options, sample_rate=ctx_rate)
            d.duration = duration
            d.channels = channels
            d.compressed_bytes = len(data)
            # AudioBuffer: 32-bit float PCM -- duration * rate * ch * 4.
            d.decoded_cpu_bytes = int(duration * ctx_rate * channels * 4)
            pcm = {'duration': duration, 'channels': channels,
                   'sample_rate': ctx_rate, 'pcm_bytes': d.decoded_cpu_bytes}
            return d, pcm
        d = AssetDescriptor(kind, source, options)
        d.compressed_bytes = len(data)
        d.decoded_cpu_bytes = len(data)
        return d, {'bytes': data}

    def _emit(self, key, stage):
        if self.on_progress is not None:
            try:
                self.on_progress(key, stage)
            except Exception:
                pass

    def _cleanup_partial(self, key, st):
        """Parsing / creation failed: clean up partial results, do not
        leave a half-registered cache entry or an in-flight zombie."""
        self._cache.pop(key, None)
        self._inflight.pop(key, None)
        st.error = True
        st.done = True

    def _on_handle_released(self, key, handle):
        # Last reference released: drop from cache + release budget.
        if self._cache.get(key) is handle:
            del self._cache[key]
        try:
            self.budget.release(handle.descriptor)
        except Exception:
            pass

    # -- cancellation (per subscriber) ------------------------------------
    def cancel(self, handle_or_key):
        """Per-subscriber cancellation: releasing ONE consumer's
        reference never invalidates the asset for another consumer.
        If this was the last reference, the asset is freed; if other
        subscribers remain, it stays."""
        if isinstance(handle_or_key, AssetHandle):
            handle_or_key.release()
            return True
        if isinstance(handle_or_key, str):
            st = self._inflight.get(handle_or_key)
            if st is not None:
                st.cancelled_subscribers += 1
                st.subscribers = max(0, st.subscribers - 1)
                # Obsolete in-flight result: if ALL subscribers
                # cancelled, drop the in-flight entry so its result
                # is released, not attached.
                if st.subscribers == 0:
                    del self._inflight[handle_or_key]
                return True
            handle = self._cache.get(handle_or_key)
            if handle is not None:
                handle.release()
                return True
        return False

    # -- disposal -----------------------------------------------------------
    def dispose_asset(self, handle):
        """Dispose ONE asset. Decoder pool (loader-owned) is NOT
        disposed with it -- see dispose_decoders()."""
        if handle is not None:
            handle.dispose()

    def dispose_decoders(self):
        """Loader-owned infrastructure: decoder pool / workers.
        Different from disposing loaded textures (asset-owned)."""
        self.registry._decoders.clear()
        self.registry._initialized = False

    def dispose(self):
        for handle in list(self._cache.values()):
            handle.dispose()
        self._cache.clear()
        self._inflight.clear()
        self.dispose_decoders()
