# follow_cam.py - Follow Camera + Procedural Terrain Demo
# Features:
# - 100x100 procedurally-generated terrain with smooth shading
# - Cube controlled via WASD + QE for strafing
# - Follow camera that smoothly trails the cube
# - Post-apocalyptic realism aesthetic
# - HUD: minimap + 3D position coordinates

from scs import *
import math
import random

# Import 3D utilities
try:
    from scs_3d import v3, v3_add, v3_sub, v3_scale, v3_normalize, v3_length
except ImportError:
    # Fallback definitions if scs_3d unavailable
    def v3(x=0, y=0, z=0): return (float(x), float(y), float(z))
    def v3_add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
    def v3_sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
    def v3_scale(a, s): return (a[0] * s, a[1] * s, a[2] * s)
    def v3_length(a): return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    def v3_normalize(a):
        l = v3_length(a)
        return (a[0] / l, a[1] / l, a[2] / l) if l > 0 else (0, 0, 0)


# Post-apocalyptic color palette
COLORS = {
    'rust': (0.6, 0.3, 0.1),           # Rusty brown
    'concrete': (0.4, 0.4, 0.4),       # Weathered concrete
    'moss': (0.2, 0.4, 0.15),          # Moss/algae green
    'oxide': (0.3, 0.5, 0.4),          # Oxidized copper
    'ash': (0.25, 0.25, 0.28),         # Ashy grey
    'warnings': (1.0, 0.65, 0.0),      # Warning orange
    'danger': (0.8, 0.1, 0.1),         # Rusted danger red
}


def perlin_noise_2d(x, y, seed=42):
    """Simple procedural noise using sine waves (pseudo-Perlin)."""
    random.seed(int(seed * 10000) + int(x * 1000) + int(y * 1000))
    n1 = math.sin(x * 0.1 + y * 0.07 + seed) * 0.5 + 0.5
    n2 = math.sin(x * 0.05 + y * 0.1 + seed * 2) * 0.5 + 0.5
    n3 = math.sin(x * 0.02 + y * 0.03 + seed * 3) * 0.5 + 0.5
    return (n1 * 0.5 + n2 * 0.3 + n3 * 0.2)


def generate_terrain_mesh(grid_size=100, cell_size=2.0, height_scale=5.0):
    """
    Generate a 100x100 terrain mesh with procedural height map.
    
    Args:
        grid_size: Number of subdivisions per side (100x100 = 10,000 verts)
        cell_size: World-space size of each cell (2m)
        height_scale: Vertical scaling factor
    
    Returns:
        (vertices, indices) for terrain mesh
    """
    vertices = []
    indices = []
    
    # Generate heightmap
    half_size = grid_size * cell_size / 2.0
    
    for y in range(grid_size + 1):
        for x in range(grid_size + 1):
            # World position
            world_x = x * cell_size - half_size
            world_z = y * cell_size - half_size
            
            # Procedural height with layered noise
            height = perlin_noise_2d(world_x, world_z, seed=1) * height_scale
            height += perlin_noise_2d(world_x * 2, world_z * 2, seed=2) * height_scale * 0.5
            height += perlin_noise_2d(world_x * 0.5, world_z * 0.5, seed=3) * height_scale * 0.3
            height -= height_scale * 1.5  # Offset so terrain is roughly centered
            
            # Vertex position + placeholder for normal (computed later)
            vertices.extend([world_x, height, world_z, 0.0, 1.0, 0.0])
    
    # Generate indices for smooth-shaded triangles
    for y in range(grid_size):
        for x in range(grid_size):
            v0 = y * (grid_size + 1) + x
            v1 = v0 + 1
            v2 = v0 + (grid_size + 1)
            v3 = v2 + 1
            
            indices.extend([v0, v2, v1])
            indices.extend([v1, v2, v3])
    
    # Compute vertex normals (smooth shading)
    normals = [[0.0, 0.0, 0.0] for _ in range((grid_size + 1) * (grid_size + 1))]
    
    for i in range(0, len(indices), 3):
        i0, i1, i2 = indices[i], indices[i+1], indices[i+2]
        
        # Get positions
        p0 = (vertices[i0*6], vertices[i0*6+1], vertices[i0*6+2])
        p1 = (vertices[i1*6], vertices[i1*6+1], vertices[i1*6+2])
        p2 = (vertices[i2*6], vertices[i2*6+1], vertices[i2*6+2])
        
        # Compute face normal
        e1 = v3_sub(p1, p0)
        e2 = v3_sub(p2, p0)
        face_normal = v3_normalize((
            e1[1] * e2[2] - e1[2] * e2[1],
            e1[2] * e2[0] - e1[0] * e2[2],
            e1[0] * e2[1] - e1[1] * e2[0]
        ))
        
        # Accumulate to vertex normals
        for idx in [i0, i1, i2]:
            normals[idx][0] += face_normal[0]
            normals[idx][1] += face_normal[1]
            normals[idx][2] += face_normal[2]
    
    # Normalize and write back
    for i in range(len(normals)):
        n = normals[i]
        length = math.sqrt(n[0]*n[0] + n[1]*n[1] + n[2]*n[2])
        if length > 0:
            n[0] /= length
            n[1] /= length
            n[2] /= length
        vertices[i*6+3] = n[0]
        vertices[i*6+4] = n[1]
        vertices[i*6+5] = n[2]
    
    return (vertices, indices)


def sample_terrain_height(vertices, grid_size, cell_size, world_x, world_z):
    """
    Sample terrain height at a world position using bilinear interpolation.
    """
    half_size = grid_size * cell_size / 2.0
    
    # Clamp to terrain bounds
    world_x = max(-half_size, min(half_size, world_x))
    world_z = max(-half_size, min(half_size, world_z))
    
    # Grid coordinates
    gx = (world_x + half_size) / cell_size
    gz = (world_z + half_size) / cell_size
    
    gx_int = int(gx)
    gz_int = int(gz)
    gx_frac = gx - gx_int
    gz_frac = gz - gz_int
    
    # Clamp grid indices
    gx_int = max(0, min(grid_size - 1, gx_int))
    gz_int = max(0, min(grid_size - 1, gz_int))
    gx_int_next = min(gx_int + 1, grid_size)
    gz_int_next = min(gz_int + 1, grid_size)
    
    # Sample 4 heights
    idx00 = (gz_int * (grid_size + 1) + gx_int) * 6 + 1
    idx10 = (gz_int * (grid_size + 1) + gx_int_next) * 6 + 1
    idx01 = (gz_int_next * (grid_size + 1) + gx_int) * 6 + 1
    idx11 = (gz_int_next * (grid_size + 1) + gx_int_next) * 6 + 1
    
    h00 = vertices[idx00]
    h10 = vertices[idx10]
    h01 = vertices[idx01]
    h11 = vertices[idx11]
    
    # Bilinear interpolation
    h0 = h00 * (1 - gx_frac) + h10 * gx_frac
    h1 = h01 * (1 - gx_frac) + h11 * gx_frac
    h = h0 * (1 - gz_frac) + h1 * gz_frac
    
    return h


def onAppStart(app):
    """Initialize terrain, cube, camera, and HUD."""
    
    # Terrain parameters
    app.grid_size = 100
    app.cell_size = 2.0
    app.height_scale = 5.0
    
    # Generate terrain mesh
    app.terrain_vertices, app.terrain_indices = generate_terrain_mesh(
        app.grid_size, app.cell_size, app.height_scale
    )
    
    # Terrain shape (3D mesh)
    app.terrain = Mesh3D(
        vertices=app.terrain_vertices,
        indices=app.terrain_indices,
        centerX=0, centerY=0, centerZ=0,
        fill=COLORS['concrete'],
        stroke=None,
    )
    
    # Cube shape
    app.cube_pos = (0.0, 2.0, 0.0)
    app.cube = Cube3D(
        centerX=app.cube_pos[0],
        centerY=app.cube_pos[1],
        centerZ=app.cube_pos[2],
        width=1.0, height=1.0, depth=1.0,
        fill=COLORS['rust'],
        stroke=COLORS['warnings'],
        strokeWidth=2,
    )
    
    # Main camera (follows the cube)
    app.main_camera = Camera3D(
        position=(0.0, 3.0, 5.0),
        yaw=0.0, pitch=-15.0,
        fov=65.0, near=0.1, far=1000.0
    )
    
    # Follow camera smoothing parameters
    app.camera_distance = 5.0
    app.camera_height_offset = 2.0
    app.camera_smooth_factor = 0.08
    
    # Cube movement
    app.cube_speed = 0.3
    app.cube_rotation_speed = 2.0
    app.cube_velocity = [0.0, 0.0, 0.0]
    app.cube_yaw = 0.0
    
    # Gravity
    app.gravity = -0.5
    app.cube_velocity_y = 0.0
    
    # Keyboard state
    app.keys_pressed = {}
    
    # HUD minimap
    app.minimap_x = 50
    app.minimap_y = 50
    app.minimap_size = 100
    app.minimap_range = app.grid_size * app.cell_size
    
    # Position label
    app.pos_label = Label(
        "X: 0.0  Y: 0.0  Z: 0.0",
        50, 100,
        fontSize=16,
        fill='white',
        hud=True,
    )
    
    # Minimap background
    app.minimap_bg = Rect(
        app.minimap_x, app.minimap_y,
        app.minimap_size, app.minimap_size,
        fill=COLORS['ash'],
        stroke='white',
        strokeWidth=2,
        hud=True,
    )
    
    # Minimap player indicator
    app.minimap_player = Circle(
        app.minimap_x + app.minimap_size / 2,
        app.minimap_y + app.minimap_size / 2,
        4,
        fill=COLORS['warnings'],
        hud=True,
    )
    
    # Minimap terrain indicator (static border)
    app.minimap_terrain_circle = Circle(
        app.minimap_x + app.minimap_size / 2,
        app.minimap_y + app.minimap_size / 2,
        app.minimap_size / 2 - 2,
        fill=None,
        stroke=COLORS['oxide'],
        strokeWidth=1,
        hud=True,
    )


def update_camera(app):
    """
    Smoothly follow the cube with the camera.
    Camera maintains a distance and height offset behind the cube's yaw direction.
    """
    cube_x, cube_y, cube_z = app.cube_pos
    
    # Desired camera position: behind cube at distance, with height offset
    yaw_rad = math.radians(app.cube_yaw)
    cam_offset_x = -math.sin(yaw_rad) * app.camera_distance
    cam_offset_z = -math.cos(yaw_rad) * app.camera_distance
    
    target_pos = (
        cube_x + cam_offset_x,
        cube_y + app.camera_height_offset,
        cube_z + cam_offset_z
    )
    
    # Smooth lerp to target position
    current = app.main_camera.position
    factor = app.camera_smooth_factor
    new_pos = (
        current[0] + (target_pos[0] - current[0]) * factor,
        current[1] + (target_pos[1] - current[1]) * factor,
        current[2] + (target_pos[2] - current[2]) * factor,
    )
    
    app.main_camera.position = new_pos
    
    # Look at cube with slight height adjustment
    app.main_camera.yaw = app.cube_yaw
    app.main_camera.pitch = -20.0


def update_cube(app):
    """
    Update cube position based on movement and gravity.
    Slide along terrain to maintain height above ground.
    """
    # Accumulate movement
    cube_x, cube_y, cube_z = app.cube_pos
    
    # Gravity
    app.cube_velocity_y += app.gravity * 0.016
    
    # Apply velocity
    cube_x += app.cube_velocity[0] * 0.016
    cube_y += app.cube_velocity_y * 0.016
    cube_z += app.cube_velocity[2] * 0.016
    
    # Sample terrain height at cube position
    terrain_y = sample_terrain_height(
        app.terrain_vertices,
        app.grid_size,
        app.cell_size,
        cube_x, cube_z
    )
    
    # Cube collision with terrain (cube radius ~0.5)
    cube_radius = 0.5
    if cube_y - cube_radius < terrain_y:
        cube_y = terrain_y + cube_radius
        app.cube_velocity_y = 0.0
    
    app.cube_pos = (cube_x, cube_y, cube_z)
    app.cube.centerX = cube_x
    app.cube.centerY = cube_y
    app.cube.centerZ = cube_z


def onKeyHold(app, key):
    """Handle continuous key input for cube movement."""
    k = str(key).lower()
    app.keys_pressed[k] = True
    
    # Forward/backward (W/S)
    if k == 'w':
        yaw_rad = math.radians(app.cube_yaw)
        app.cube_velocity[0] = -math.sin(yaw_rad) * app.cube_speed
        app.cube_velocity[2] = -math.cos(yaw_rad) * app.cube_speed
    elif k == 's':
        yaw_rad = math.radians(app.cube_yaw)
        app.cube_velocity[0] = math.sin(yaw_rad) * app.cube_speed
        app.cube_velocity[2] = math.cos(yaw_rad) * app.cube_speed
    
    # Strafe left/right (A/D for rotation, Q/E for strafe)
    elif k == 'q':
        yaw_rad = math.radians(app.cube_yaw)
        app.cube_velocity[0] = -math.cos(yaw_rad) * app.cube_speed
        app.cube_velocity[2] = math.sin(yaw_rad) * app.cube_speed
    elif k == 'e':
        yaw_rad = math.radians(app.cube_yaw)
        app.cube_velocity[0] = math.cos(yaw_rad) * app.cube_speed
        app.cube_velocity[2] = -math.sin(yaw_rad) * app.cube_speed
    
    # Rotation (A/D)
    elif k == 'a':
        app.cube_yaw += app.cube_rotation_speed
    elif k == 'd':
        app.cube_yaw -= app.cube_rotation_speed
    
    # Jump (Space)
    elif k == ' ':
        if app.cube_velocity_y == 0.0:
            app.cube_velocity_y = 0.8


def onKeyRelease(app, key):
    """Stop movement on key release."""
    k = str(key).lower()
    if k in app.keys_pressed:
        del app.keys_pressed[k]
    
    # Decelerate if no key pressed
    if 'w' not in app.keys_pressed and 's' not in app.keys_pressed:
        if 'q' not in app.keys_pressed and 'e' not in app.keys_pressed:
            app.cube_velocity[0] *= 0.9
            app.cube_velocity[2] *= 0.9


def redrawAll(app):
    """Render terrain, cube, camera, and HUD."""
    
    # Update cube position and gravity
    update_cube(app)
    
    # Update follow camera
    update_camera(app)
    
    # Clear and set camera
    setCamera(app.main_camera)
    clearScreen(COLORS['ash'])
    
    # Draw terrain
    drawShape(app.terrain)
    
    # Draw cube
    drawShape(app.cube)
    
    # Reset to HUD mode for drawing 2D elements
    setCamera(None)
    
    # Update position label
    app.pos_label.text = (
        f"X: {app.cube_pos[0]:6.1f}  "
        f"Y: {app.cube_pos[1]:6.1f}  "
        f"Z: {app.cube_pos[2]:6.1f}"
    )
    
    # Draw HUD minimap background
    drawShape(app.minimap_bg)
    drawShape(app.minimap_terrain_circle)
    
    # Draw minimap player position
    minimap_center_x = app.minimap_x + app.minimap_size / 2
    minimap_center_y = app.minimap_y + app.minimap_size / 2
    
    # Normalize cube position to minimap
    half_range = app.minimap_range / 2
    map_x = (app.cube_pos[0] / half_range) * (app.minimap_size / 2 - 4)
    map_z = (app.cube_pos[2] / half_range) * (app.minimap_size / 2 - 4)
    
    app.minimap_player.centerX = minimap_center_x + map_x
    app.minimap_player.centerY = minimap_center_y + map_z
    drawShape(app.minimap_player)
    
    # Draw position coordinates
    drawShape(app.pos_label)
    
    # Draw instructions
    info_text = "WASD: Move  Q/E: Strafe  A/D: Rotate  Space: Jump"
    drawLabel(info_text, 450, 20, fontSize=14, fill='white')


runApp(width=900, height=560, enableFullscreen=True)
