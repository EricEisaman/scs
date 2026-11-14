# SCS Loader — the 5 decisions

Central principle: **source data, decoded assets, mutable instances,
and backend resources are four distinct things.**

## Decision map

| # | Decision | SCS answer | Where |
|---|----------|------------|-------|
| 1 | Separate fetch / decode / create / prepare | `resolve → fetch → decode → create → prepare`; shared `AssetSource` for URL / Blob / File / bytes; GLB parsing produces asset data **without** adding objects to a scene; texture decoding finishes **without** GPU upload; audio decoding finishes **without** playback; a returned promise means **PREPARED** (ready for first use), not "downloaded" | `scs_loader.AssetSource`, `AssetLoader.load`, `STAGE_*` |
| 2 | Capabilities + decoder deps explicit | `DecoderRegistry`: explicit `init()`/preload, **reused** decoder instances / worker pools (never one per asset), injectable transcoder URLs + worker config, declared GLB extensions + **actionable** error for unsupported required features, KTX2 transcode target chosen from **renderer caps** (`astc > bc7 > etc2 > rgba8`) | `DecoderRegistry`, `DecoderError`, `ktx2_transcode_target` |
| 3 | Preserve meaning, not just bytes | Interpretation metadata is part of the descriptor + cache identity: textures carry usage / colour-space / orientation / alpha / mip / sampler; GLB preserves scenes, hierarchy, skins, animations, morphs, materials, cameras; audio exposes duration / channels / **decoded** sample rate (resampled to the decoding context's rate); reusable asset data ≠ mutable instances (`handle.instance()` shares geometry, keeps separate animation state) | `AssetDescriptor`, `texture_descriptor`, `glb_descriptor`, `audio_descriptor`, `AssetHandle.instance` |
| 4 | Budget decoded memory + prep work | Separate counters: compressed / decoded-CPU / GPU bytes; separate limits: concurrent fetches / decodes / prepares; large prep staged; GPU-compressed texture paths (Basis/KTX2 → transcoded compressed format); short SFX vs long-form audio distinguished (AudioBuffer = 32-bit float PCM, `decodeAudioData` needs **complete** file data, not streaming fragments); prioritisation + per-subscriber cancellation; obsolete decode results released, not attached; **progress by stage**, not downloaded-bytes-as-readiness | `Budget`, `AssetLoader._load_sync`, `_LoadState.progress` |
| 5 | Sharing / disposal / failure ownership | `AssetHandle` with a documented contract (shared refcount vs owned); in-flight dedup; cache keys include **options + meaning**, not just URL; per-subscriber cancellation (one cancelled consumer never invalidates another's asset); partial-result cleanup on failure; loader-owned infra (decoder pool) ≠ asset-owned resources (`dispose_decoders()` vs `dispose_asset()`); `ImageBitmap.close()` explicit via `handle.close_bitmap()`, never hidden in texture disposal | `AssetHandle`, `AssetLoader.cancel`, `_cleanup_partial`, `dispose_*` |

## What a returned promise means

**PREPARED** — fetched, decoded, runtime resource created, prepared
for first use. Not "downloaded". Code that only needs the download
(e.g. a progress bar) reads stage progress, not the promise.

## Cache identity

```
key = hash(source + kind + options + meaning)
```

Same URL as sRGB vs linear, or with different sampler settings, is a
**different** cache entry. Same URL + same options + same meaning is
**one** shared handle (refcounted).

## Failure example

```python
loader.registry.register('draco', draco_decoder,
                         glb_extensions=['KHR_draco_mesh_compression'])
loader.registry.init()
try:
    handle = loadGLB(AssetSource.from_bytes(glb_bytes),
                     options={'required_extensions': ['KHR_draco_mesh_compression']})
except DecoderError as e:
    # e.code == 'unsupported-glb-extension', e.hint tells you what to register
    ...
```

## What the loader never does

- Never adds parsed GLB objects to a scene (parsing ≠ scene mutation).
- Never uploads a texture as a side effect of decoding it.
- Never starts audio playback as a side effect of decoding it.
- Never creates one decoder instance per asset.
- Never closes a shared `ImageBitmap` inside texture disposal.
- Never lets one cancelled subscriber kill another's asset.
- Never presents "downloaded bytes" as overall readiness.
