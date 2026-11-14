# SCS Integrations — five boundaries around the renderer

None of these live inside `render()`. Each is an adapter with the same
common contract:

> **Explicit ownership, asynchronous lifecycle, timestamped data where
> relevant, bounded work at the rendering boundary.**

| # | Area | Module | The boundary | What render() sees |
|---|------|--------|--------------|--------------------|
| 1 | Local storage | `scs_storage.py` | `AssetCache` (IndexedDB, async) + `PreferenceStore` (localStorage, prefs only) | Bytes via `get()` / `put()`; misses are normal |
| 2 | WASM | `scs_wasm.py` | `ArrayLayout` + `WasmMemoryView` + batch `write_batch()` | Typed-array ranges, refreshed after growth |
| 3 | Web Audio | `scs_audio.py` | `AudioEngine` + `ClockMapping` + `AudioWorklet` DSP | Audio-time scheduling, never frame time |
| 4 | Web media | `scs_media.py` | `MediaSourceAdapter` (element / VideoFrame / camera) | One `MediaFrame` per render frame, re-imported |
| 5 | Serial / USB | `scs_serial.py` | `SerialAdapter` / `USBAdapter` + `ProtocolParser` + `BoundedQueue` | `latest()` sample, `drain_commands()` |

## 1. Storage — async, versioned, never GPU handles

```python
from scs_storage import assets, prefs, cache_key
prefs.set('theme', 'dark')                    # localStorage: prefs only
assets.put('level-1', processed_bytes,        # IndexedDB: binary
           options={'quality': 2})             # fingerprint in key
cached = assets.get('level-1', {'quality': 2}) # Promise -> bytes | None
```

- Key = `name@v<schema>:<options-fingerprint>`. Bump the schema to
  invalidate everything; change options to get a different key.
- Cache the **source asset or processed CPU representation**, never a
  `GPUTexture` / `WebGLTexture` — `put()` raises `TypeError` on handles.
- Miss / invalidation / write failure are normal: `get()` resolves to
  `None`, `put()` resolves to `None` on failure. Rendering never
  depends on persistence.
- Population happens on load / in idle time, never in `begin_frame()`.

## 2. WASM — bulk ABI, explicit ownership

```python
from scs_wasm import ArrayLayout, WasmMemoryView, update_transforms
layout = ArrayLayout('transform', 'float32', N,
                     {'x': 0, 'y': 1, 'rotation': 2, 'scale': 3})
view = WasmMemoryView(wasm_memory.buffer, layout, owner='wasm')
update_transforms(view, [{'x': 10, 'y': 20, ...}, ...])  # ONE call
view.check_fresh(wasm_memory.buffer)  # after any grow: refresh or die
```

- Layout documents element type, alignment, stride, offsets, count.
- `owner='wasm' | 'js' | 'shared'` says who frees / grows.
- `copy_on_upload=True` (default): the upload copies immediately.
  `False`: the upload retains the view — caller must not mutate/free.
- A view is a **CPU-memory** view. It avoids a CPU copy; it is not
  "zero-copy GPU access". The GPU upload is a separate decision
  (`upload_view(..., copy=...)` makes it explicit).
- After `memory.grow()`, non-shared buffers detach: `check_fresh()`
  rebuilds the view. Shared memory does not detach, but the length
  check still applies.

## 3. Audio — separate clock, supplied context, worklet DSP

```python
from scs_audio import AudioEngine
engine = AudioEngine(context=app_audio_context)  # supplied: NOT owned
engine.resume()  # from a click handler ONLY (autoplay)
engine.schedule(node, engine.clock.now_audio() + 0.5)
engine.register_worklet('dsp', 'dsp-processor.js')  # audio thread
```

- Scheduling uses `AudioContext.currentTime`, never frame count.
- `ClockMapping` (`getOutputTimestamp()`) maps audio time ↔
  `performance.now()` for visuals that must sync to sound.
- DSP lives in an `AudioWorklet`, never in a render callback.
- `dispose()` never closes an app-supplied context. Only a context
  the engine itself created is closed.
- No implicit start: `resume()` is the explicit user-gesture path.

## 4. Media — a source, not a texture

```python
from scs_media import CameraAdapter
cam = CameraAdapter(video_element)          # buffering='latest' default
frame = cam.acquire(frame_id)               # current frame, this frame only
tex = cam.import_for_webgpu(device, frame)  # valid_for_frame_only: True
```

- The adapter is cached; the **imported texture is not**. Re-import
  every frame; `MediaFrame.is_valid_for(frame_id)` proves staleness.
- `VideoFrame` ownership: `owned=True` → adapter closes it;
  `owned=False` → caller closes it. Never double-close.
- Buffering: `latest` (camera: drop old, show newest), `queue_all`
  (offline: deliver every frame), `drop_oldest` / `drop_newest`.
  Queues are bounded (`max_queue`).
- Timestamps + colour policy (`color_space`, `color_conversion`)
  travel with the adapter, not per material.

## 5. Serial / USB — optional, timestamped, bounded

```python
from scs_serial import SerialAdapter, LineParser
dev = SerialAdapter(baud_rate=115200, parser=LineParser())
# from a click handler ONLY:
dev.request().then(lambda port: dev.connect(port))
# in onStep / redrawAll -- never in render():
value = dev.latest()           # sample latest sensor state
for cmd in dev.drain_commands(): send(cmd)
```

- `request()` / `requestDevice()` require transient user activation:
  call from a click, never from deferred init.
- Stages are separate: permission → connection → `ProtocolParser`
  (bytes → samples) → scene reads `latest()`.
- `BoundedQueue` with `drop_oldest` / `drop_newest` / `error`:
  device traffic cannot accumulate without bound.
- Rendering **samples** the latest state; commands are queued
  separately because every command must be delivered.
- Disconnect / reconnect are states (`lost`, `reconnecting`),
  not exceptions. `list_authorized()` enumerates prior grants
  without a prompt.
- `SerialAdapter` and `USBAdapter` are distinct classes. A USB
  device exposing a serial port still uses two different APIs.

## What the renderer guarantees to all five

- `render()` / `renderFrame()` never block on storage, audio, media,
  serial, or WASM. Each adapter is polled / scheduled at the
  boundary; the frame proceeds without it if it is absent.
- No adapter owns the renderer, and the renderer owns no adapter.
  Disposal is per-adapter and explicit.
