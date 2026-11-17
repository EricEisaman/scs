# SCS Splats — the 10 decisions

Splats are a **first-class rendering primitive**, not a mesh-loader
special case. Geometry, appearance, visibility, and residency are
separate concerns.

## Decision map

| # | Decision | SCS answer | Where |
|---|----------|------------|-------|
| 1 | Custom passes, not just mesh draw calls | `SplatRendererExtension` participates in scene prep, visibility, sorting, compositing; shares cameras, transforms, lighting, opaque depth; specialized GPU resources/shaders without vertex/index buffers; WebGL raster + WebGPU compute behind the same boundary | `SplatRendererExtension`, `WebGLSplatRenderer`, `WebGPUSplatRenderer` |
| 2 | Logical schema ≠ packed GPU layout | Versioned `SplatSchema`: position, scale/rotation **or** covariance, opacity, variable-degree SH, optional normals / material / lighting-transfer / custom attributes, chunk-local quantization metadata; no JS object per Gaussian; no fixed packed layout as public API | `SplatSchema`, `SplatAttribute` |
| 3 | Sorting / transparency as explicit service | `SortingService` is replaceable (cpu-exact / worker / gpu / approximate) with inputs, outputs, scheduling, validity; ordering spans interacting objects; static attribute buffers separate from visible/sorted index list; depth + other transparent content are inputs | `SortingService` |
| 4 | View-dependent work explicit, incl. XR | `ViewCollection`: scene-wide work once (decoding, residency, shared transforms), view-dependent work per view (footprint, appearance, LOD, ordering); one eye's ordering never assumed sufficient for the other | `ViewCollection`, `SplatRendererExtension.prepare_scene / sort` |
| 5 | Chunked assets | `SplatManifest` + coarse chunk before the whole asset; fetch by id / byte range; decode independently; cancel / reprioritize; partial readiness; monolithic fallback when no random access | `SplatAssetLoader`, `SplatManifest` |
| 6 | Hierarchical LOD as representation | `SplatHierarchy`: bounds, parent/child, approximation error, payload refs; coarse parent stands in while children load; view-dependent selection + budget + hysteresis; never "first N splats" | `SplatHierarchy.select_lod` |
| 7 | Residency ≠ scene membership | `ResidencyManager`: separate accounting/budgets for downloaded / decoded / GPU / sorting / pending uploads / decodes; stable `SplatChunkHandle` with generation checks, never raw GPU offsets; eviction never destroys scene objects | `ResidencyManager`, `SplatChunkHandle` |
| 8 | Captured radiance ≠ intrinsic material | Appearance modes: `captured-radiance`, `artistic-adjustment`, `relightable-material`, `precomputed-lighting-variant`. **Never label ordinary SH as "albedo"** — SH entangles material, illumination, view dependence; a shader hook cannot recover missing intrinsic info | `AppearancePayload`, `MODE_*` |
| 9 | Aligned proxy geometry + aux lighting | `ProxyGeometry` per role: `relighting / collision / shadow / occlusion / picking / radiance-transfer`, same coordinate system; roles distinct — a collision proxy is not automatically an adequate relighting proxy; PRT + PBR lighting transfer into per-Gaussian SH | `ProxyGeometry`, `PROXY_ROLES` |
| 10 | Appearance updates independent of geometry/LOD | `asset.apply_appearance(payload, aggregation='before'|'after')`: replaces appearance without rebuilding positions / covariance / hierarchy / bounds; GPU modifiers + custom shading stages; versioned payloads; `before` re-aggregates parents, `after` leaves parents until next pass; only appearance buffers invalidated | `SplatAsset.apply_appearance` |

## What to commit to now (extension points)

- Custom render passes with shared camera/depth access.
- Versioned typed attribute schemas.
- Chunked assets + replaceable residency management.
- Explicit multi-view preparation + ordering stages.
- Separate geometry, captured appearance, relighting data.

Together these preserve room for ordinary splats, streamed LOD worlds,
artistic effects, and genuinely relightable assets — without
pretending those are the same representation.

## What SCS deliberately does NOT do

- Never treats a Gaussian as an ordinary independently drawn mesh object.
- Never exposes one fixed packed layout as the public API.
- Never uses a conventional transparent-object queue as per-splat ordering.
- Never assumes one camera / one eye's ordering suffices for another.
- Never calls SH coefficients "albedo".
- Never uses a collision proxy as a relighting proxy without saying so.
- Never rebuilds geometry to change appearance.
