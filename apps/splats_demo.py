# Splats demo -- first-class primitive, not a mesh-loader special case.
#
# Run: ?app=splats_demo
# The demo shows the CONTRACT (schema, chunks, LOD, sorting,
# appearance modes, proxies) with a small synthetic asset -- no
# .PLY / .RAD file needed. A real loader feeds the same classes.
#
# - Schema is versioned + logical; backends pack it differently.
# - Appearance mode is explicit: SH here is CAPTURED RADIANCE, not albedo.
# - Appearance updates never rebuild geometry.
# - LOD parents stand in while children load.

from scs_splats import (
    SplatSchema, SplatAsset, SplatChunk, SplatRendererExtension,
    WebGLSplatRenderer, AppearancePayload, ProxyGeometry,
    MODE_CAPTURED_RADIANCE, MODE_RELIGHTABLE,
    ViewCollection, SplatAssetLoader,
)

# 2: versioned logical schema, SH degree 2, relightable extension reserved.
schema = SplatSchema(version=1, sh_degree=2)
schema.add_relightable()
schema.validate()

# 5+6: chunked asset with a coarse parent + two children.
asset = SplatAsset(schema, name='garden')
coarse = SplatChunk('coarse', bounds=((0, 0, 0), (10, 10, 10)), level=0,
                    byte_range=(0, 4096))
child_a = SplatChunk('a', bounds=((0, 0, 0), (5, 10, 10)), level=1,
                     parent_id='coarse', byte_range=(4096, 8192))
child_b = SplatChunk('b', bounds=((5, 0, 0), (10, 10, 10)), level=1,
                     parent_id='coarse', byte_range=(8192, 12288))
asset.add_chunk(coarse)
asset.add_chunk(child_a)
asset.add_chunk(child_b)
asset.set_positions([(2, 5, 2), (7, 5, 7), (5, 5, 5)])

# 9: proxies are role-distinct, same coordinate system.
asset.add_proxy(ProxyGeometry('relighting', 'mesh:relight-proxy'))
asset.add_proxy(ProxyGeometry('collision', 'mesh:collision-proxy'))

# 1+3+4: renderer extension, multi-view, explicit ordering.
renderer = WebGLSplatRenderer()
renderer.add_asset(asset)
views = ViewCollection([{'position': (0, 5, -10), 'eye': 'left'},
                        {'position': (0.5, 5, -10), 'eye': 'right'}])
result = renderer.render(views, opaque_depth={'depth': 'shared'})
# 10: appearance update -- geometry untouched, only appearance invalidated.
asset.apply_appearance(
    AppearancePayload(MODE_RELIGHTABLE, version=2,
                      params={'lighting': 'pbr+prt'}),
    aggregation='before')

# 5: chunked loader -- manifest + coarse first, partial readiness.
loader = SplatAssetLoader(fetcher=lambda cid, rng: b'chunk:' + cid.encode())
manifest = loader.manifest('garden', schema, ['coarse', 'a', 'b'],
                           coarse_chunk_id='coarse')
loader.fetch_chunk(coarse)


def onAppStart(app):
    app.background = 'black'
    Label('Splats demo -- first-class primitive, not a mesh special case',
          20, 20, size=16, fill='white', align='left-top')
    Label('schema v1, SH degree 2, relightable attrs reserved',
          20, 50, size=14, fill='lightgray', align='left-top')
    Label('appearance: ' + asset.appearance.mode + ' (SH is NOT albedo)',
          20, 75, size=14, fill='lightgray', align='left-top')
    Label('chunks ready: ' + str(loader.partial_readiness()['ready']),
          20, 100, size=14, fill='lightgray', align='left-top')
    Label('render backend: ' + result['backend'],
          20, 125, size=14, fill='lightgray', align='left-top')
    Label('proxies: relighting + collision (distinct roles)',
          20, 150, size=14, fill='lightgray', align='left-top')
    Star(200, 300, 80, 5, fill='gold')
    Circle(320, 300, 40, fill='dodgerblue')
