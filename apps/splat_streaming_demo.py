# Splat Streaming Demo -- REAL skatepark, no toy garden, no fake splats.
# Run: ?app=splat_streaming_demo
# Streams the REAL PlayCanvas Streamed SOG scene:
#   https://code.playcanvas.com/examples_data/example_skatepark_02/lod-meta.json
# 1. fetch_lod_meta_from_url() -- GET real lod-meta.json (window.fetch)
# 2. parse_lod_meta() -- lodLevels, filenames, tree, environment
# 3. SplatURLStreamer.plan(camera) -- per leaf LOD by distance, chunk URLs via filenames[]
# 4. fetch_chunk_meta_from_url() -- GET each chunk meta.json, real count + textures
# 5. Draw each leaf REAL bound from lod-meta.json tree as a rect. No garden. No fake dots.
# If fetch fails, demo says so. It does NOT silently fall back to a fake garden.
# Utils showcased: fetch_lod_meta_from_url, resolve_chunk_url, join_url,
# select_lod_for_distance, SplatURLStreamer.plan, fetch_chunk_meta_from_url
# Controls: U reload | C camera CLOSE (LOD 0) | F camera FAR (LOD 3) | Click reload

from scs_splat_formats import parse_lod_meta
from scs_splat_urls import (
    SKATEPARK_LOD_META, SplatURLStreamer, fetch_lod_meta_from_url,
    fetch_chunk_meta_from_url, resolve_chunk_url, select_lod_for_distance,
    leaf_distance_to_camera,
)

def _project(app, x, z):
    mn, mx = app.root_min, app.root_max
    sx = 40 + (x - mn[0]) / (mx[0] - mn[0] + 0.0001) * 970
    sy = 300 + (z - mn[2]) / (mx[2] - mn[2] + 0.0001) * 300
    return (sx, sy)

def _on_lod_meta(app, meta):
    app.meta = meta
    app.streamer.meta = meta
    app.streamer.manifest_loaded = True
    app.streamer.lod_meta_url = SKATEPARK_LOD_META
    app.status.text = 'lod-meta.json loaded -- ' + str(meta.leaf_count()) + ' leaves, ' + str(meta.lod_levels) + ' LODs, ' + str(len(meta.filenames)) + ' chunk files'
    app.stats.text = 'LOD totals: ' + str([meta.total_for_lod(l) for l in range(meta.lod_levels)]) + '  |  env: ' + str(meta.environment)
    app.root_min, app.root_max = meta.root_bound()
    app.plan = app.streamer.plan(camera=app.camera)
    app.chunk_urls = app.streamer.chunk_urls_for_plan(app.plan)
    app.plan_label.text = 'Plan: ' + str(len(app.plan)) + ' leaves, ' + str(len(app.chunk_urls)) + ' unique chunk URLs, coarsest first'
    if app.chunk_urls:
        app.chunk_label.text = 'Next chunk: ' + app.chunk_urls[0]
    for r in app.leaf_rects:
        r.visible = False
    app.leaf_rects = []
    for leaf in meta.leaves():
        x0, y0 = _project(app, leaf.bound_min[0], leaf.bound_min[2])
        x1, y1 = _project(app, leaf.bound_max[0], leaf.bound_max[2])
        w = max(2, abs(x1 - x0))
        h = max(2, abs(y1 - y0))
        d = leaf_distance_to_camera(leaf, app.camera)
        lod = select_lod_for_distance(d)
        col = ['red', 'orange', 'gold', 'dodgerblue'][min(3, lod)]
        rect = Rect(x0, y0, w, h, fill=None, border=col, borderWidth=1)
        rect.visible = True
        app.leaf_rects.append(rect)
    app.chunk_idx = 0
    app.splats_loaded = 0
    app.chunks_loaded = 0
    app.progress_label.text = 'Streaming chunks... 0 / ' + str(len(app.chunk_urls))
    app.fetching = True

def _on_chunk_meta(app, chunk_meta):
    app.chunks_loaded += 1
    app.splats_loaded += int(chunk_meta.count or 0)
    app.progress_label.text = 'Chunks: ' + str(app.chunks_loaded) + ' / ' + str(len(app.chunk_urls)) + '  |  Splats (from chunk metas): ' + str(app.splats_loaded)
    app.chunk_label.text = 'Loaded: ' + str(chunk_meta.count) + ' splats, textures: ' + str(chunk_meta.texture_files()[:3])
    if app.chunks_loaded >= len(app.chunk_urls):
        app.status.text = 'Streaming complete -- ' + str(app.chunks_loaded) + ' chunks, ' + str(app.splats_loaded) + ' splats (chunk metas). Press U to reload.'
        app.fetching = False

def _on_fail(app, err):
    app.status.text = 'Fetch FAILED: ' + str(err) + ' -- no fake fallback. Check network / CORS.'
    app.fetching = False

def _start_load(app):
    app.status.text = 'Fetching lod-meta.json from PlayCanvas...'
    app.stats.text = ''
    app.plan_label.text = ''
    app.chunk_label.text = ''
    app.progress_label.text = ''
    app.fetching = True
    app.meta = None
    for r in app.leaf_rects:
        r.visible = False
    app.leaf_rects = []
    fetch_lod_meta_from_url(SKATEPARK_LOD_META, lambda meta: _on_lod_meta(app, meta), lambda e: _on_fail(app, e))

def onAppStart(app):
    app.background = '#0b0e14'
    app.camera = (0.0, 0.0, 0.0)
    app.streamer = SplatURLStreamer(SKATEPARK_LOD_META)
    app.meta = None
    app.plan = []
    app.chunk_urls = []
    app.chunk_idx = 0
    app.splats_loaded = 0
    app.chunks_loaded = 0
    app.fetching = False
    app.leaf_rects = []
    app.root_min = (-150.0, -115.0, -5.0)
    app.root_max = (115.0, 122.0, 34.0)
    app.title = Label('Splat Streaming -- REAL skatepark, Streamed SOG', 20, 18, size=17, fill='white', align='left-top', bold=True)
    app.url_label = Label('URL: ' + SKATEPARK_LOD_META, 20, 46, size=11, fill='#8b93a5', align='left-top')
    app.utils_label = Label('Utils: fetch_lod_meta_from_url() + resolve_chunk_url() + SplatURLStreamer.plan() + fetch_chunk_meta_from_url()', 20, 68, size=12, fill='#ffd166', align='left-top')
    app.status = Label('Starting...', 20, 94, size=13, fill='lightgray', align='left-top')
    app.stats = Label('', 20, 118, size=12, fill='white', align='left-top')
    app.plan_label = Label('', 20, 142, size=12, fill='white', align='left-top')
    app.chunk_label = Label('', 20, 166, size=12, fill='#8b93a5', align='left-top')
    app.progress_label = Label('', 20, 190, size=13, fill='white', align='left-top')
    app.legend = Label('Rects = REAL leaf bounds from lod-meta.json. Red=LOD0 finest, Blue=LOD3 coarsest. No fake garden.', 20, 214, size=12, fill='#8b93a5', align='left-top')
    app.hint = Label('U reload  |  C camera CLOSE (LOD 0)  |  F camera FAR (LOD 3)  |  Click reload', 20, 238, size=12, fill='#8b93a5', align='left-top')
    _start_load(app)

def onStep(app):
    if not app.fetching:
        return
    if app.meta is None:
        return
    if app.chunk_idx < len(app.chunk_urls):
        if not getattr(app, '_waiting', False):
            app._waiting = True
            url = app.chunk_urls[app.chunk_idx]
            cur_idx = app.chunk_idx
            app.chunk_idx += 1
            def _ok(cm, _idx=cur_idx):
                app._waiting = False
                _on_chunk_meta(app, cm)
            def _fail(e):
                app._waiting = False
                app.progress_label.text = 'Chunk failed: ' + str(e) + ' -- continuing'
            fetch_chunk_meta_from_url(url, _ok, _fail)

def onKeyPress(app, key):
    k = str(key).lower()
    if k == 'u':
        _start_load(app)
    elif k == 'c':
        app.camera = (-100.0, -50.0, 10.0)
        if app.meta is not None:
            _on_lod_meta(app, app.meta)
    elif k == 'f':
        app.camera = (0.0, 0.0, 0.0)
        if app.meta is not None:
            _on_lod_meta(app, app.meta)

def onMousePress(app, mouseX, mouseY):
    _start_load(app)
