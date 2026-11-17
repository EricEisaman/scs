# Navigation System Verification

## System Architecture Review

### 1. Ray Casting & Terrain Sampling

**Location**: `apps/follow_cam.py` lines 174-241

#### Height Sampling (`sample_terrain_height`)
- **Method**: Bilinear interpolation across 4 grid cell corners
- **Accuracy**: Sub-cell precision at any XZ position
- **Grid Resolution**: 100×100 mesh with 2m cells = 200m × 200m terrain
- **Clamping**: Bounds-checked to prevent out-of-bounds access
- **Formula**:
  ```
  gx = (world_x + half_size) / cell_size
  gz = (world_z + half_size) / cell_size
  h = bilinear_interpolate(h00, h10, h01, h11, gx_frac, gz_frac)
  ```

#### Normal Sampling (`sample_terrain_normal`)
- **Method**: Bilinear interpolation of pre-computed vertex normals
- **Normal Data**: Stored in vertex format (x, y, z) at indices [3, 4, 5]
- **Smooth Shading**: Per-vertex normals computed from face normals
- **Upward Guarantee**: Normals flipped to ensure positive Y component
- **Formula**:
  ```
  normal = bilinear_interpolate(n00, n10, n01, n11, gx_frac, gz_frac)
  if normal.y < 0: normal = -normal
  ```

### 2. Shader Logic (WebGL2)

**Location**: `scs_engine_webgl2.py` lines 1-150+ (_VS and _FS)

#### Vertex Shader
- **Input**: Object-space positions, normals, UVs
- **Transform**: 
  - Position: `gl_Position = u_mvp * vec4(a_pos, 1.0)`
  - Normals: `v_worldNormal = u_normal * a_normal` (inverse-transpose matrix)
- **Output**: World-space position, normal, object-space position for defects
- **Coordinate System**: Right-handed, Y-up, -Z forward (OpenGL)

#### Fragment Shader - Cook-Torrance PBR
- **Normal Transformation**: Input world-space normals are normalized per-fragment
- **Material Pipeline**:
  1. Base color (RGB) from mesh material
  2. Metallic = 0.0 (non-metallic for terrain)
  3. Roughness = 0.85 (weathered concrete/rust)
  4. Fresnel F0 = mix(0.04, baseColor, metallic)
  5. Diffuse kD = (1 - Fresnel) × (1 - metallic) = fully diffuse for terrain

- **Lighting Equation** (Cook-Torrance BRDF):
  ```
  Lo = integral over hemisphere of:
       (kD * albedo/π + kS * DFG/(4(N·V)(N·L))) * L * (N·L)
  
  where:
  - D = GGX distribution with roughness
  - F = Schlick Fresnel approximation
  - G = Smith geometry shadowing
  - kS = Fresnel (F)
  - kD = 1 - kS (1 - metallic)
  ```

- **Defect System** (Damaged Metal):
  - Scratches: Elongated metallic defects with procedural direction
  - Pits: Cellular metallic defects
  - Roughness variation: High-frequency detail filtering with fwidth()
  - Corrosion: Optional dielectric overlay (reduces metallic appearance)
  - Level: Controlled by `uDefectLevel` [0, 1]

- **IBL (Image-Based Lighting)**:
  - Diffuse: Pre-integrated hemisphere sampling
  - Specular: Specular BRDF LUT + pre-filtered mip chain
  - Kulla-Conty multi-scatter correction for energy conservation

#### Coordinate Convention Verification
- **Terrain Mesh**: Generated with Y-up, Z=depth
- **Camera**: Yaw=0 looks down -Z axis (standard OpenGL)
- **Lighting**: All calculations in world-space
- **Normal Mapping**: Correctly transforms from object to world space via u_normal matrix

### 3. Collision Detection & Navigation

**Location**: `apps/follow_cam.py` lines 414-497

#### Update Cycle
1. **Predict Next Position**:
   - `next_pos = current_pos + velocity * dt`
   - Applied with dt = 0.016 seconds (~60 FPS)

2. **Raycast Downward**:
   - Query terrain height at XZ position: `sample_terrain_height(next_x, next_z)`
   - Returns interpolated Y value at ground level

3. **Collision Response**:
   - If `next_y - cube_radius < terrain_height`:
     - Place cube: `next_y = terrain_height + cube_radius`
     - Stop falling: `velocity_y = 0`
   - Else: Continue falling (gravity active)

4. **Terrain-Aligned Rotation** (Quaternion SLERP):
   - **Sample Normal**: `sample_terrain_normal(next_x, next_z)`
   - **Compute Target Rotation**:
     - Rotation axis: `cross((0,1,0), terrain_normal)`
     - Rotation angle: `acos(dot((0,1,0), terrain_normal))`
     - Target quat: `quat_from_axis_angle(axis, angle)`
   - **Interpolate**: `quat_slerp(current_rotation, target_rotation, lerp_factor)`
   - **Result**: Cube smoothly aligns its +Y axis with terrain normal

5. **Rotation Behavior**:
   - On ground: Aggressive LERP (factor = 0.1) → fast terrain alignment
   - In air: Gentle LERP (factor = 0.05) → slow upright orientation recovery

#### Mathematical Correctness

**Quaternion Representation**:
```
q = (w, x, y, z)  where w is scalar, (x,y,z) is vector part
q_identity = (1, 0, 0, 0)  (no rotation)
q * v * q^-1 rotates vector v
SLERP(q1, q2, t) smoothly interpolates rotation
```

**Normal Alignment**:
```
Given: up_world = (0, 1, 0), terrain_normal = sampled from mesh
Find: quaternion q such that q * up_world = terrain_normal

If significant rotation:
  axis = normalize(cross(up_world, terrain_normal))
  angle = acos(dot(up_world, terrain_normal))
  q = from_axis_angle(axis, angle)

If already aligned (axis_len < 0.001):
  q = identity
```

### 4. Movement System

**Location**: `apps/follow_cam.py` lines 522-563

#### Controls
| Key | Action | Base Speed | With Shift |
|-----|--------|-----------|-----------|
| **W** | Forward (cube-relative) | 0.3 m/s | 0.9 m/s |
| **S** | Backward | 0.3 m/s | 0.9 m/s |
| **Q** | Strafe Left (perpendicular) | 0.3 m/s | 0.9 m/s |
| **E** | Strafe Right | 0.3 m/s | 0.9 m/s |
| **A** | Rotate Left | 2.0°/frame | 2.0°/frame |
| **D** | Rotate Right | 2.0°/frame | 2.0°/frame |
| **Space** | Jump (if grounded) | 0.8 m/s up | 0.8 m/s up |
| **Shift** | Speed Boost | - | 3× speed mult |

#### Yaw-Relative Movement
```
yaw_rad = radians(cube_yaw)

Forward:
  vx = -sin(yaw_rad) * speed
  vz = -cos(yaw_rad) * speed

Strafe Left (perpendicular to facing):
  vx = -cos(yaw_rad) * speed
  vz = sin(yaw_rad) * speed

Strafe Right:
  vx = cos(yaw_rad) * speed
  vz = -sin(yaw_rad) * speed

Rotation:
  cube_yaw ± rotation_speed per frame
```

#### Deceleration
- Friction applied when no movement keys pressed
- Decel factor: 0.9× per frame (smooth sliding stop)
- Applies to X and Z velocity only (Y is gravity-driven)

### 5. Camera System (Follow Camera)

**Location**: `apps/follow_cam.py` lines 377-408

#### Smooth Following
1. **Desired Position**:
   - Behind cube at distance: 5 units
   - Height offset: 2 units above cube
   - Maintains cube's current yaw
   
   ```
   yaw_rad = radians(cube_yaw)
   cam_offset_x = -sin(yaw_rad) * distance
   cam_offset_z = -cos(yaw_rad) * distance
   target_pos = (cube_x + cam_offset_x, cube_y + 2, cube_z + cam_offset_z)
   ```

2. **Smooth Interpolation**:
   - LERP factor: 0.08 per frame
   - Current ← Current + (Target - Current) × 0.08
   - Result: Camera lags naturally, not rigid

3. **Camera Orientation**:
   - Yaw: Matches cube yaw
   - Pitch: -20° (slight downward look)
   - FOV: 65° (comfortable exploration view)

## Verification Checklist

### Ray Casting ✓
- [x] Bilinear height interpolation implemented correctly
- [x] Bounds checking prevents out-of-bounds vertex access
- [x] Normal sampling uses same interpolation method
- [x] Normals always point upward (Y > 0)
- [x] Sub-cell precision for smooth terrain

### Shader Logic ✓
- [x] Vertex normals transformed correctly (inverse-transpose)
- [x] World-space lighting calculations
- [x] Cook-Torrance BRDF with GGX + Smith + Schlick
- [x] Proper Fresnel F0 computation (metallic: 0.0 for terrain)
- [x] Energy-conserving (Kulla-Conty multi-scatter)
- [x] Coordinate system consistent (Y-up, -Z forward)

### Navigation System ✓
- [x] Gravity simulation with velocity accumulation
- [x] Collision detection: sphere vs. height field
- [x] Terrain-aligned rotation via quaternion SLERP
- [x] Normal sampling integrated into collision
- [x] Smooth orientation recovery when falling
- [x] Deceleration friction when keys released
- [x] Yaw-relative movement (W/S/Q/E)
- [x] Rotation controls (A/D)
- [x] Jump mechanic with grounding check
- [x] Shift key 3× speed multiplier

### Camera ✓
- [x] Smooth follow with configurable LERP
- [x] Maintains offset behind cube
- [x] Height offset above cube
- [x] Yaw-locked camera orientation
- [x] Slight downward pitch for better visibility

## Known Limitations

1. **Terrain Resolution**: 100×100 grid with 2m cells provides ~11m radius exploration
   - Maximum terrain height variation: ±9m from center
   - Total playable area: 200×200 meters

2. **Collision**: Sphere vs. height field (no per-triangle raycasts)
   - Acceptable for smooth procedural terrain
   - Cube radius fixed at 0.5 units

3. **Normal Precision**: Bilinear interpolation (not full Phong or tessellation)
   - Adequate for 2m grid resolution
   - Fine detail filtering with shader fwidth()

4. **Rotation Speed**: Quaternion LERP is not adaptive
   - Fixed factor 0.1 on ground, 0.05 in air
   - Could be enhanced with terrain slope-based scaling

## Performance Notes

- Mesh: 101×101 = 10,201 vertices, ~20,000 indices
- Normals: Pre-computed per-vertex (not per-frame)
- Sampling: O(1) bilinear lookup, no search/grid iteration
- Rotation: O(1) quaternion SLERP, 4×4 matrix multiply
- Frame time: Dominated by shader execution, not collision/navigation

## Testing Recommendations

1. **Terrain Alignment**:
   - Walk onto slopes and verify cube rotates to match
   - Jump and verify cube returns to upright orientation

2. **Height Accuracy**:
   - Verify no cube clipping through terrain
   - Check smooth height transitions on slopes

3. **Camera Tracking**:
   - Rotate camera follows cube instantly
   - Position smoothly lags behind

4. **Movement Response**:
   - Shift key noticeably speeds up movement
   - Deceleration feels responsive (not sticky)
   - Jump responds to gravity consistently

5. **Edge Cases**:
   - Extreme slopes (should handle gracefully)
   - Terrain peaks and valleys
   - Fast movement over hills
