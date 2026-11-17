"""
scs_splat_urls.py -- STREAMING SPLATS FROM URLs.

Utilities for the demo and for real apps. They handle the network;
parsing lives in scs_splat_formats.py, GPU packing in scs_splat_gpu.py.

  fetch_lod_meta_from_url(url)   -- GET lod-meta.json -> LodMeta
  resolve_chunk_url(base, file)  -- lod-meta dir + filenames[i] -> chunk meta.json URL
  fetch_chunk_meta(url)          -- GET chunk meta.json -> SogChunkMeta
  fetch_bytes(url)               -- GET any splat URL -> bytes (CPython sync / Brython async)
  load_splat_from_url(url)       -- detect by URL: lod-meta.json / .spz / .ply / .splat / meta.json
  SplatURLStreamer               -- manifest first, then chunks by LOD/distance, with progress

URL rules (PlayCanvas Streamed SOG):
  * lod-meta.json lives in a directory. All filenames[] are RELATIVE to
    that directory. Never guess "0_0/" from the pattern -- resolve via filenames[].
  * Chunk URL = join_url(lod_meta_url, filenames[file_index])
  * Chunk meta.json lives in its own directory. Its texture files are
    relative to THAT directory, not to lod-meta.json.
  * Environment URL = join_url(lod_meta_url, environment)

Browser (Brython): fetch is async (window.fetch -> Promise). The helpers
below use callbacks: fetch_json(url, on_ok, on_fail). They never block.
CPython (tests): fetch_bytes_sync(url) uses urllib.
"""

import json as _json

SKATEPARK_LOD_META = 'https://code.playcanvas.com/examples_data/example_skatepark_02/lod-meta.json'

def join_url(base_url, rel):
    rel = str(rel or '')
    if rel.startswith('http://') or rel.startswith('https://') or rel.startswith('blob:') or rel.startswith('data:'):
        return rel
    if not base_url:
        return rel
    base = str(base_url)
    if '?' in base:
        base = base.split('?', 1)[0]
    if '#' in base:
        base = base.split('#', 1)[0]
    if '/' in base:
        directory = base.rsplit('/', 1)[0] + '/'
    else:
        directory = ''
    parts = []
    for seg in (directory + rel).split('/'):
        if seg == '.' or seg == '':
            if seg == '' and not parts:
                parts.append(seg)
            continue
        if seg == '..':
            if len(parts) > 1:
                parts.pop()
            continue
        parts.append(seg)
    joined = '/'.join(parts)
    if joined.startswith('https:/') and not joined.startswith('https://'):
        joined = joined.replace('https:/', 'https://', 1)
    if joined.startswith('http:/') and not joined.startswith('http://'):
        joined = joined.replace('http:/', 'http://', 1)
    return joined

def dir_of(url):
    u = str(url or '')
    if '/' in u:
        return u.rsplit('/', 1)[0] + '/'
    return ''

def resolve_chunk_url(lod_meta_url, filenames, file_index):
    if file_index < 0 or file_index >= len(filenames):
        raise IndexError('chunk file index %d out of range (0..%d)' % (file_index, len(filenames)-1))
    return join_url(lod_meta_url, filenames[file_index])

def resolve_environment_url(lod_meta_url, environment):
    if not environment:
        return None
    return join_url(lod_meta_url, environment)

def detect_url_format(url):
    u = str(url or '').lower().split('?', 1)[0].split('#', 1)[0]
    if u.endswith('lod-meta.json'):
        return 'lod-meta'
    if u.endswith('meta.json'):
        return 'sog-chunk-meta'
    if u.endswith('.spz'):
        return 'spz'
    if u.endswith('.ply'):
        return 'ply'
    if u.endswith('.splat'):
        return 'splat'
    if u.endswith('.sog'):
        return 'sog'
    return 'unknown'

def fetch_bytes_sync(url, timeout=20):
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'SCS-splat-streamer/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

def fetch_json_sync(url, timeout=20):
    return _json.loads(fetch_bytes_sync(url, timeout=timeout).decode('utf-8'))

def fetch_json(url, on_ok, on_fail=None):
    try:
        from browser import window
    except ImportError:
        try:
            data = fetch_json_sync(url)
            on_ok(data)
        except Exception as e:
            if on_fail:
                on_fail(e)
        return None
    def _ok(resp):
        try:
            resp.text().then(lambda txt: on_ok(_json.loads(txt))).catch(lambda e: on_fail(e) if on_fail else None)
        except Exception as e:
            if on_fail:
                on_fail(e)
    def _fail(e):
        if on_fail:
            on_fail(e)
    try:
        window.fetch(url).then(_ok).catch(_fail)
    except Exception as e:
        if on_fail:
            on_fail(e)
    return None

def fetch_lod_meta_from_url(url, on_ok, on_fail=None):
    from scs_splat_formats import parse_lod_meta
    def _got(data):
        try:
            on_ok(parse_lod_meta(data))
        except Exception as e:
            if on_fail:
                on_fail(e)
    return fetch_json(url, _got, on_fail)

def fetch_chunk_meta_from_url(url, on_ok, on_fail=None):
    from scs_splat_formats import parse_sog_chunk_meta
    def _got(data):
        try:
            on_ok(parse_sog_chunk_meta(data))
        except Exception as e:
            if on_fail:
                on_fail(e)
    return fetch_json(url, _got, on_fail)

def select_lod_for_distance(distance, thresholds=(12.0, 35.0, 90.0)):
    if distance < thresholds[0]:
        return 0
    if distance < thresholds[1]:
        return 1
    if distance < thresholds[2]:
        return 2
    return 3

def leaf_distance_to_camera(leaf, camera):
    c = leaf.center()
    dx, dy, dz = c[0]-camera[0], c[1]-camera[1], c[2]-camera[2]
    return (dx*dx + dy*dy + dz*dz) ** 0.5

class SplatURLStreamer:
    def __init__(self, lod_meta_url=''):
        self.lod_meta_url = lod_meta_url
        self.meta = None
        self.manifest_loaded = False
        self.chunks_requested = []
        self.chunks_loaded = []
        self.chunk_metas = {}
        self.errors = []
        self.splats_loaded = 0
    def load_manifest(self, url, on_ok, on_fail=None):
        self.lod_meta_url = url
        def _ok(meta):
            self.meta = meta
            self.manifest_loaded = True
            on_ok(meta)
        def _fail(e):
            self.errors.append(str(e))
            if on_fail:
                on_fail(e)
        return fetch_lod_meta_from_url(url, _ok, _fail)
    def load_manifest_sync(self, url):
        from scs_splat_formats import parse_lod_meta
        data = fetch_json_sync(url)
        self.lod_meta_url = url
        self.meta = parse_lod_meta(data)
        self.manifest_loaded = True
        return self.meta
    def plan(self, camera=(0, 0, 0), lod_override=None):
        if self.meta is None:
            raise RuntimeError('load_manifest() first -- no LodMeta yet')
        plan = []
        for leaf in self.meta.leaves():
            d = leaf_distance_to_camera(leaf, camera)
            lod = lod_override if lod_override is not None else select_lod_for_distance(d)
            rng = leaf.range_for_lod(lod)
            # Fallback: try coarser LODs first, then finer -- a leaf may
            # not carry every LOD (missing key = no splats at that level).
            if rng is None:
                candidates = []
                for _lod in range(lod+1, self.meta.lod_levels):
                    candidates.append(_lod)
                for _lod in range(lod-1, -1, -1):
                    candidates.append(_lod)
                for _lod in candidates:
                    rng = leaf.range_for_lod(_lod)
                    if rng is not None:
                        lod = _lod
                        break
            if rng is None:
                continue
            chunk_url = resolve_chunk_url(self.lod_meta_url, self.meta.filenames, rng['file'])
            plan.append({'leaf': leaf, 'lod': lod, 'distance': d, 'file': rng['file'], 'offset': rng['offset'], 'count': rng['count'], 'chunk_url': chunk_url})
        plan.sort(key=lambda p: (-p['lod'], p['distance']))
        return plan
    def chunk_urls_for_plan(self, plan):
        seen = []
        for p in plan:
            if p['chunk_url'] not in seen:
                seen.append(p['chunk_url'])
        return seen
    def describe(self):
        return {'lod_meta_url': self.lod_meta_url, 'manifest_loaded': self.manifest_loaded, 'leaves': self.meta.leaf_count() if self.meta else 0, 'lod_levels': self.meta.lod_levels if self.meta else 0, 'chunks_requested': len(self.chunks_requested), 'chunks_loaded': len(self.chunks_loaded), 'splats_loaded': self.splats_loaded, 'errors': list(self.errors)}
