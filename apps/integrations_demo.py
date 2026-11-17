# Integrations demo -- every adapter, no hardware required.
#
# Run: ?app=integrations_demo
# All five adapters work in-memory / with stubs on desktop, so the
# demo shows the CONTRACT (keys, layouts, clocks, buffering, sampling)
# without needing IndexedDB, WASM, a mic, a camera, or a serial device.
#
# 1. Storage: versioned cache key + prefs (no GPU handles).
# 2. WASM: one batch transform update, layout-documented.
# 3. Audio: schedule against audio time, resume() from a click.
# 4. Media: camera adapter with 'latest' buffering, one-frame validity.
# 5. Serial: LineParser + latest() sampling, bounded queues.

from scs_storage import assets, prefs, cache_key
from scs_wasm import ArrayLayout, WasmMemoryView, update_transforms
from scs_audio import AudioEngine
from scs_media import CameraAdapter
from scs_serial import SerialAdapter, LineParser

# --- 1. Storage -------------------------------------------------------
prefs.set('theme', 'dark')  # localStorage: small prefs only
# Cache PROCESSED CPU bytes, never a GPU handle:
assets.put_sync('level-1', b'\x00\x01\x02', options={'quality': 2})
assert assets.get_sync('level-1', {'quality': 2}) == b'\x00\x01\x02'
# Different options = different key (no stale hit):
assert assets.get_sync('level-1', {'quality': 1}) is None

# --- 2. WASM ----------------------------------------------------------
layout = ArrayLayout('transform', 'float32', 2,
                     {'x': 0, 'y': 1, 'rotation': 2, 'scale': 3})
# In a real app this buffer IS the WASM linear memory (wasm_memory.buffer).
fake_memory = bytearray(layout.total_bytes)
view = WasmMemoryView(fake_memory, layout, owner='wasm', copy_on_upload=True)
update_transforms(view, [{'x': 100, 'y': 200, 'rotation': 0, 'scale': 1},
                         {'x': 300, 'y': 200, 'rotation': 45, 'scale': 2}])

# --- 3. Audio ---------------------------------------------------------
# App-supplied context: engine does NOT own it, dispose() won't close it.
audio = AudioEngine(context=None)  # creates lazily on resume()

# --- 4. Media ---------------------------------------------------------
# Camera: 'latest' buffering -- interactive effects show the newest frame.
camera = CameraAdapter(None, buffering='latest', max_queue=1)

# --- 5. Serial --------------------------------------------------------
serial = SerialAdapter(baud_rate=115200, parser=LineParser())
serial._on_bytes(b'42,7\n')  # parser stage: bytes -> sample
serial._on_bytes(b'43,8\n')
# Rendering samples the LATEST state; it never drains the queue.
latest_sensor = serial.latest()  # '43,8'


def onAppStart(app):
    app.background = 'black'
    Label('Integrations: storage / WASM / audio / media / serial',
          20, 20, size=16, fill='white', align='left-top')
    Label('prefs theme: ' + str(prefs.get('theme')),
          20, 50, size=14, fill='lightgray', align='left-top')
    Label('cached level-1: ' + str(assets.get_sync('level-1', {'quality': 2}) is not None),
          20, 75, size=14, fill='lightgray', align='left-top')
    Label('latest serial sample: ' + str(latest_sensor),
          20, 100, size=14, fill='lightgray', align='left-top')
    Label('WASM transform[0]: ' + str(view.read_record(0)),
          20, 125, size=14, fill='lightgray', align='left-top')
    Label('Click to resume audio (user gesture required).',
          20, 155, size=14, fill='gold', align='left-top')
    Rect(20, 180, 300, 40, fill='dodgerblue')
    Label('camera adapter: ' + str(camera.describe()),
          20, 235, size=12, fill='lightgray', align='left-top')


def onMousePress(app, x, y):
    # Audio: the EXPLICIT user-gesture path. Never auto-started.
    audio.resume()
    # Serial: permission is also a user-gesture path (no device here,
    # so this is a no-op in the demo -- the call shape is the point):
    # serial.request().then(lambda port: serial.connect(port))
