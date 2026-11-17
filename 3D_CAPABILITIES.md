# SCS 3D Capabilities & follow_cam App

## Overview

The SCS framework now supports full 3D graphics capabilities through new shape primitives, camera control, and procedural terrain generation. The showcase demo is **`follow_cam.py`** — a post-apocalyptic exploration environment with:

- **Procedurally generated 100×100 terrain mesh** with layered Perlin-like noise
- **Smooth follow camera** that trails the player cube
- **Physics simulation** including gravity and terrain collision detection
- **HUD overlay** with real-time minimap and 3D coordinates
- **WASD + QE controls** for intuitive exploration

## New 3D Shape Primitives

### Mesh3D — Custom Vertex/Index Mesh

```python
terrain = Mesh3D(
    vertices=vertex_array,      # flat [x,y,z,nx,ny,nz, ...] 
    indices=index_array,        # flat [i0,i1,i2, ...]
    centerX=0, centerY=0, centerZ=0,
    fill='gray',
    stroke=None,
    strokeWidth=1,
)
```

**Features:**
- Arbitrary mesh topology
- Per-vertex smooth shading (normals)
- Positioned via `centerX`, `centerY`, `centerZ`
- Full opacity/visibility control

**Use cases:**
- Procedurally generated terrain
- Complex 3D models from external data
- Custom geometry

### Cube3D — Axis-Aligned Cube

```python
cube = Cube3D(
    centerX=0, centerY=0, centerZ=5,
    width=1, height=1, depth=1,
    fill='rust',
    stroke='orange',
    strokeWidth=2,
)
```

**Features:**
- Axis-aligned box geometry
- Configurable width, height, depth
- World-space positioning and color

**Use cases:**
- Player avatar / controlled object
- Simple obstacles and structures
- Placeholder geometry

### Sphere3D — Sphere Geometry

```python
sphere = Sphere3D(
    centerX=10, centerY=2, centerZ=0,
    radius=2.0,
    fill='chrome',
    stroke=None,
)
```

**Features:**
- Spherical geometry
- World-space positioning
- Configurable radius

**Use cases:**
- Collectibles / power-ups
- Planets / celestial objects
- Light sources / glowing objects

## Camera Control API

### Camera3D Class

```python
from scs import Camera3D

camera = Camera3D(
    position=(0, 2, 6),    # World position (x, y, z)
    yaw=0,                 # Horizontal rotation (degrees, 0 = -Z)
    pitch=-15,             # Vertical tilt (degrees, + = look up)
    fov=65,                # Field of view (degrees)
    near=0.1,              # Near plane distance
    far=1000,              # Far plane distance
)
```

**Methods:**

```python
# Movement (world-space)
camera.move(forward=0.5, right=0.3, up=0)

# Looking (relative to camera orientation)
camera.look(dyaw_deg=10, dpitch_deg=5)

# Query
camera.forward()           # Returns normalized forward vector
camera.right()             # Returns normalized right vector
camera.up()                # Returns normalized up vector
camera.view_matrix()       # Returns MVP view matrix
camera.proj_matrix(aspect) # Returns projection matrix
```

### setCamera() — Activate 3D Rendering

```python
def onAppStart(app):
    # REQUIRED: Request WebGL2 renderer for 3D
    app.renderer = 'webgl2'

def redrawAll(app):
    setCamera(app.camera)         # Enable 3D mode
    clearScreen('skyblue')         # Set clear color
    
    drawShape(app.terrain)         # Draw 3D shapes
    drawShape(app.cube)
    
    setCamera(None)                # Return to 2D/HUD mode
    drawLabel("HUD Text", 450, 20) # Draw 2D overlays
```

**IMPORTANT: Renderer Requirement**

Apps with 3D shapes MUST set `app.renderer = 'webgl2'` in `onAppStart()`. Without this, the system defaults to 2D canvas rendering and 3D shapes won't display.

```python
def onAppStart(app):
    app.renderer = 'webgl2'  # Enable 3D graphics pipeline
    app.my_cube = Cube3D(...)
    app.my_terrain = Mesh3D(...)
```

**Contract:**
- `setCamera(camera)` enables 3D rendering with the given camera
- `setCamera(None)` returns to 2D/HUD mode
- Must be called before drawing 3D shapes
- 2D drawing (HUD) requires `setCamera(None)` first

### clearScreen(fill) — Set Background Color

```python
clearScreen('white')           # Named color
clearScreen('#1a1a1a')         # Hex color
clearScreen((0.5, 0.5, 0.5))   # RGB tuple [0, 1]
```

## follow_cam.py Demo Application

### Features

#### Terrain Generation
- **100×100 mesh subdivisions** with 2×2 meter world-space cells
- **Procedural height map**: 3-layer Perlin-like noise composition
- **Smooth shading**: Per-vertex normal computation for realistic lighting
- **Collision detection**: Bilinear height sampling for accurate cube positioning
- **Post-apocalyptic aesthetic**: Weathered concrete, rust, oxidized metal

#### Controls
| Key | Action |
|-----|--------|
| **W** | Move forward (cube-relative) |
| **S** | Move backward (cube-relative) |
| **Q** | Strafe left (perpendicular to facing) |
| **E** | Strafe right (perpendicular to facing) |
| **A** | Rotate left |
| **D** | Rotate right |
| **Space** | Jump (if on ground) |

#### Camera System
- **Smooth follow**: 8% lerp per frame toward target position
- **Chase distance**: 5 units behind cube
- **Height offset**: 2 units above cube
- **Look-ahead**: Camera maintains cube's yaw + slight downward pitch

#### HUD Overlay
- **Minimap** (100×100 px): Shows player position in real-time
  - White circle: terrain bounds
  - Orange dot: player position
  - Origin-relative coordinates
- **Position display**: Real-time X/Y/Z coordinates of cube
- **Control hints**: On-screen key bindings

### Physics Implementation

**Gravity Simulation:**
```python
# Applied each frame (dt ≈ 16ms)
velocity_y += gravity * dt           # Accelerate downward
position_y += velocity_y * dt        # Apply velocity

# Ground collision (cube radius ≈ 0.5)
terrain_y = sample_terrain_height(x, z)
if position_y - 0.5 < terrain_y:
    position_y = terrain_y + 0.5     # Place on surface
    velocity_y = 0                   # Stop falling
```

**Terrain Sampling:**
```python
# Bilinear interpolation for smooth height at any XZ position
def sample_terrain_height(x, z):
    # Find grid cell
    gx_int, gz_int = int(gx), int(gz)
    gx_frac, gz_frac = gx - gx_int, gz - gz_int
    
    # Sample 4 corner heights
    h00, h10, h01, h11 = ...
    
    # Interpolate
    h = lerp(lerp(h00, h10, gx_frac),
             lerp(h01, h11, gx_frac), 
             gz_frac)
    return h
```

## Color Palette

The follow_cam app uses a **post-apocalyptic realism** aesthetic:

```python
COLORS = {
    'rust':       (0.6, 0.3, 0.1),   # Rusty brown
    'concrete':   (0.4, 0.4, 0.4),   # Weathered concrete
    'moss':       (0.2, 0.4, 0.15),  # Moss/algae green
    'oxide':      (0.3, 0.5, 0.4),   # Oxidized copper
    'ash':        (0.25, 0.25, 0.28),# Ashy grey
    'warnings':   (1.0, 0.65, 0.0),  # Warning orange
    'danger':     (0.8, 0.1, 0.1),   # Rusted danger red
}
```

## Renderer Support

### WebGL2 Backend (Primary)

The WebGL2 renderer (`scs_engine_webgl2.py`) implements the full 3D pipeline:

```python
# Draw 3D cube
renderer.draw_cube3d(x, y, z, width, height, depth, 
                     fill='gray', stroke=None, strokeWidth=1)

# Draw 3D sphere
renderer.draw_sphere3d(x, y, z, radius,
                       fill='blue', stroke=None, strokeWidth=1)

# Draw custom mesh
renderer.draw_mesh3d(vertices, indices,
                     centerX=0, centerY=0, centerZ=0,
                     fill='gray', stroke=None, strokeWidth=1)

# Camera control
renderer.set_camera(camera)
renderer.clear_screen('white')
```

### 2D Canvas Backend (Fallback)

The 2D renderer (`scs_2d.py`) provides placeholder implementations:
- `Cube3D` → `Rect` (depth projected to screen space)
- `Sphere3D` → `Circle` (radius in screen space)
- `Mesh3D` → no-op (canvas2d not suitable for complex geometry)

**Note:** 2D rendering is a compatibility fallback. For true 3D, use WebGL2 or WebGPU.

## Technical Architecture

### Coordinate System

**Right-handed, Y-up:**
- **X**: right
- **Y**: up
- **Z**: forward (into screen)
- **Camera yaw=0**: looking down -Z axis
- **Pitch**: positive = looking up

### Pipeline

1. **Python app** (follow_cam.py)
   - Defines 3D shapes with `Mesh3D`, `Cube3D`, `Sphere3D`
   - Calls `setCamera(camera)` to activate 3D rendering
   - Calls `drawShape(shape)` to render each 3D object
   - Calls `setCamera(None)` to return to 2D for HUD

2. **Shape draw() method**
   - Calls renderer's `draw_cube3d()`, `draw_sphere3d()`, or `draw_mesh3d()`
   - Passes geometry, material, and transformation parameters

3. **WebGL2 Renderer**
   - Adds shape to scene array: `{kind, pos, scale, color, ...}`
   - Next frame's `render(camera)` processes all scene items
   - Computes MVP matrix, issues WebGL draw calls

4. **GPU Shader** (DAMAGED METAL PBR)
   - Vertex shader: transforms to world-space, computes normals
   - Fragment shader: Cook-Torrance BRDF, IBL, PBR materials

### Memory Model

**Shapes are persistent objects:**
- Created once in `onAppStart()`
- Modified in-place each frame (e.g., `cube.centerX = new_x`)
- Not recreated or destroyed
- Renderer caches geometry (VBOs/IBOs)

**HUD and 3D are separate rendering paths:**
- 3D: MVP matrix, depth test, perspective correct
- HUD: orthographic, pixel-perfect, no depth test, texture blend

## Extending the System

### Adding Custom 3D Primitives

```python
class Tetrahedron3D(_BaseShape):
    def __init__(self, centerX=0, centerY=0, centerZ=0, size=1, **kwargs):
        super().__init__(align='center', hud='3d', centerZ=centerZ, **kwargs)
        self._centerX = float(centerX)
        self._centerY = float(centerY)
        self._centerZ = float(centerZ)
        self._size = float(size)
        _shapes.append(self)

    @property
    def centerX(self):
        return self._centerX

    @centerX.setter
    def centerX(self, v):
        self._centerX = float(v)

    def draw(self, renderer):
        if not self.visible:
            return
        draw_fn = getattr(renderer, 'draw_tetrahedron3d', None)
        if draw_fn is not None:
            draw_fn(self._centerX, self._centerY, self._centerZ,
                   self._size, fill=self.fill, stroke=self.stroke)
```

Then add to `__all__` in `scs_entrypoint.py`:
```python
__all__ = [..., 'Tetrahedron3D', ...]
```

Implement in WebGL2 (`scs_engine_webgl2.py`):
```python
def draw_tetrahedron3d(self, cx, cy, cz, size, fill='gray', stroke=None, ...):
    self.add_box(cx, cy, cz, size, size, size, color=fill, ...)
```

## Known Limitations

1. **Mesh3D vertex count**: Large meshes (>100k vertices) may hit performance limits on low-end devices
2. **Procedural terrain generation**: Runs synchronously on main thread; large grids may stall first frame
3. **Collision detection**: Simple AABB (axis-aligned bounding box) for terrain; no per-triangle collisions
4. **2D canvas fallback**: Only provides placeholder circles/rects; no true 3D projection
5. **Material properties**: WebGL2 uses DAMAGED METAL PBR; custom shaders not yet exposed

## Future Enhancements

- [ ] Mesh LOD (level-of-detail) system for large terrains
- [ ] Per-mesh custom shader support
- [ ] Instanced rendering for repeated objects
- [ ] Skeletal animation support
- [ ] Physics integration (rigid body dynamics)
- [ ] Particle systems
- [ ] Shadow mapping
- [ ] Normal maps and displacement

## See Also

- [REPOSITORY_OVERVIEW.md](REPOSITORY_OVERVIEW.md) — Full system architecture
- [scs_3d.py](scs_3d.py) — Math utilities (vectors, matrices, Camera3D)
- [scs_engine_webgl2.py](scs_engine_webgl2.py) — GPU rendering pipeline
- [apps/follow_cam.py](apps/follow_cam.py) — Complete example implementation
- [scs_spatial_audio.py](scs_spatial_audio.py) — Another 3D demo (spatial audio environment)
