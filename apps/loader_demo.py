# Loader demo -- stages are separate, meaning survives caching.
#
# Run: ?app=loader_demo
# All loads here use in-memory bytes (sync path), so the demo shows
# the CONTRACT (stages, descriptors, cache identity, handles) without
# needing a network fetch. In the browser, URL loads use the same
# stage sequence via window.fetch.
#
# - A promise means PREPARED, not downloaded.
# - Same URL + different meaning = different cache entry.
# - handle.instance() shares geometry, keeps separate animation state.
# - One cancelled subscriber never invalidates another's asset.

from scs_loader import AssetSource, AssetLoader

loader = AssetLoader()
loader.registry.init()

# GLB: parsing produces asset data WITHOUT adding objects to a scene.
glb = loader.load(AssetSource.from_bytes(b'glTF-binary-stub', name='hero.glb'),
                  kind='glb',
                  options={'required_extensions': []})
# Texture: decoding finishes WITHOUT GPU upload; meaning travels along.
tex_srgb = loader.load(AssetSource.from_bytes(b'\x89PNG-stub', name='diffuse.png'),
                       kind='texture',
                       options={'color_space': 'srgb', 'usage': 'color'})
tex_linear = loader.load(AssetSource.from_bytes(b'\x89PNG-stub', name='diffuse.png'),
                         kind='texture',
                         options={'color_space': 'linear', 'usage': 'data'})
# Same bytes, different meaning -> different cache entries (not a stale hit).
assert tex_srgb is not tex_linear
# Audio: decoding finishes WITHOUT playback; duration / rate exposed.
sfx = loader.load(AssetSource.from_bytes(b'RIFF-stub', name='jump.wav'),
                  kind='audio',
                  options={'context_sample_rate': 48000,
                           '_test_duration': 0.3, '_test_channels': 1})
# Mutable instances: two characters share geometry, not animation state.
hero_a = glb.instance()
hero_b = glb.instance()
hero_a.instance_state['animation_time'] = 1.5
assert hero_b.instance_state['animation_time'] == 0.0


def onAppStart(app):
    app.background = 'black'
    Label('Loader demo -- stages separate, meaning survives caching',
          20, 20, size=16, fill='white', align='left-top')
    Label('GLB scenes: ' + str(len(glb.data['scenes'])) +
          ' | animations: ' + str(len(glb.data['animations'])),
          20, 50, size=14, fill='lightgray', align='left-top')
    Label('texture sRGB vs linear: different cache entries',
          20, 75, size=14, fill='lightgray', align='left-top')
    Label('audio: ' + str(sfx.descriptor.duration) + 's, ' +
          str(sfx.descriptor.channels) + 'ch, ' +
          str(sfx.descriptor.sample_rate) + ' Hz (decoded rate)',
          20, 100, size=14, fill='lightgray', align='left-top')
    Label('budget: ' + str(loader.budget.describe()),
          20, 125, size=12, fill='lightgray', align='left-top')
    Star(200, 250, 80, 5, fill='gold')
