# follow_cam.py - Follow Camera + Procedural Terrain Demo
# Features:
# - Single 100x100 procedurally-generated terrain MESH (no individual cubes)
# - Cube controlled via WASD + QE
# - Follow camera that smoothly trails the cube
# - Mouse drag to reposition camera
# - HUD minimap with position coordinates

from scs import *
import math

COLORS = {
    'rust': (0.6, 0.3, 0.1),
    'concrete': (0.4, 0.4, 0.4),
    'moss': (0.2, 0.4, 0.15),
    'oxide': (0.3, 0.5, 0.4),
    'ash': (0.25, 0.25, 0.28),
    'warnings': (1.0, 0.65, 0.0),
    'danger': (0.8, 0.1, 0.1),
}


def perlin_noise_2d(x, y, seed=42):
    """Simple procedural noise using sine waves."""
    n1 = math.sin(x * 0.03 + y * 0.025 + seed * 0.1) * 0.5 + 0.5
    n2 = math.sin(x * 0.1 + y * 0.08 + seed * 0.2) * 0.5 + 0.5
    n3 = math.sin(x * 0.2 + y * 0.15 + seed * 0.3) * 0.5 + 0.5
    n4 = math.sin(x * 0.4 + y * 0.3 + seed * 0.4) * 0.5 + 0.5
    return (n1 * 0.4 + n2 * 0.35 + n3 * 0.2 + n4 * 0.05)


def sample_terrain_height(world_x, world_z):
    """Sample terrain height at any world position."""
    return perlin_noise_2d(world_x, world_z) * 18.0


def generate_terrain_mesh(grid_size=100, cell_size=1.0):
    """Generate terrain mesh with vertices [x,y,z,nx,ny,nz,...] and indices."""
    vertices_flat = []
    indices = []
    
    # Build vertex grid
    vertices_grid = []
    for z in range(grid_size + 1):
        for x in range(grid_size + 1):
            world_x = x * cell_size - (grid_size * cell_size) / 2
            world_z = z * cell_size - (grid_size * cell_size) / 2
            height = sample_terrain_height(world_x, world_z)
            vertices_grid.append((world_x, height, world_z))
    
    # Compute vertex normals
    vertex_normals = [(0.0, 0.0, 0.0) for _ in range(len(vertices_grid))]
    
    for z in range(grid_size):
        for x in range(grid_size):
            v0_idx = z * (grid_size + 1) + x
            v1_idx = z * (grid_size + 1) + (x + 1)
            v2_idx = (z + 1) * (grid_size + 1) + x
            v3_idx = (z + 1) * (grid_size + 1) + (x + 1)
            
            v0 = vertices_grid[v0_idx]
            v1 = vertices_grid[v1_idx]
            v2 = vertices_grid[v2_idx]
            v3 = vertices_grid[v3_idx]
            
            # First triangle
            e1 = (v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2])
            e2 = (v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2])
            n = (
                e1[1] * e2[2] - e1[2] * e2[1],
                e1[2] * e2[0] - e1[0] * e2[2],
                e1[0] * e2[1] - e1[1] * e2[0]
            )
            for i in range(3):
                vertex_normals[v0_idx] = tuple(vertex_normals[v0_idx][j] + n[j] for j in range(3))
            for i in range(3):
                vertex_normals[v1_idx] = tuple(vertex_normals[v1_idx][j] + n[j] for j in range(3))
            for i in range(3):
                vertex_normals[v2_idx] = tuple(vertex_normals[v2_idx][j] + n[j] for j in range(3))
            
            # Second triangle
            e1 = (v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2])
            e2 = (v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2])
            n = (
                e1[1] * e2[2] - e1[2] * e2[1],
                e1[2] * e2[0] - e1[0] * e2[2],
                e1[0] * e2[1] - e1[1] * e2[0]
            )
            for i in range(3):
                vertex_normals[v1_idx] = tuple(vertex_normals[v1_idx][j] + n[j] for j in range(3))
            for i in range(3):
                vertex_normals[v3_idx] = tuple(vertex_normals[v3_idx][j] + n[j] for j in range(3))
            for i in range(3):
                vertex_normals[v2_idx] = tuple(vertex_normals[v2_idx][j] + n[j] for j in range(3))
    
    # Normalize normals
    for i in range(len(vertex_normals)):
        nx, ny, nz = vertex_normals[i]
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        if length > 0.001:
            vertex_normals[i] = (nx / length, ny / length, nz / length)
        else:
            vertex_normals[i] = (0.0, 1.0, 0.0)
    
    # Flatten vertices
    for i, (x, y, z) in enumerate(vertices_grid):
        nx, ny, nz = vertex_normals[i]
        vertices_flat.extend([x, y, z, nx, ny, nz])
    
    # Build indices
    for z in range(grid_size):
        for x in range(grid_size):
            v0_idx = z * (grid_size + 1) + x
            v1_idx = z * (grid_size + 1) + (x + 1)
            v2_idx = (z + 1) * (grid_size + 1) + x
            v3_idx = (z + 1) * (grid_size + 1) + (x + 1)
            
            indices.extend([v0_idx, v1_idx, v2_idx])
            indices.extend([v1_idx, v3_idx, v2_idx])
    
    return vertices_flat, indices


def onAppStart(app):
    """Initialize terrain mesh, cube, camera, and HUD."""
    app.renderer = 'webgl2'
    
    # Generate terrain mesh once
    vertices, indices = generate_terrain_mesh(grid_size=100, cell_size=1.0)
    app.terrain_mesh = Mesh3D(
        vertices=vertices,
        indices=indices,
        centerX=0.0,
        centerY=0.0,
        centerZ=0.0,
        fill=COLORS['concrete'],
        stroke=None,
    )
    
    # Player cube
    app.cube_pos = [0.0, 10.0, 0.0]
    app.cube_vel = [0.0, 0.0, 0.0]
    app.cube_yaw = 0.0
    app.cube_vel_y = 0.0
    
    app.cube = Cube3D(
        centerX=app.cube_pos[0],
        centerY=app.cube_pos[1],
        centerZ=app.cube_pos[2],
        width=2.0, height=2.0, depth=2.0,
        fill=COLORS['rust'],
        stroke=COLORS['warnings'],
        strokeWidth=2,
    )
    
    # Camera - positioned behind and above cube, looking toward it
    app.main_camera = Camera3D(
        position=(15.0, 15.0, 15.0),
        yaw=0.0, pitch=-30.0,
        fov=65.0, near=0.1, far=1000.0
    )
    app.camera_smooth_factor = 0.08
    app.mouse_last_x = 0
    app.mouse_last_y = 0
    app.camera_yaw_offset = 0.0
    app.camera_pitch_offset = -30.0
    
    # Physics
    app.gravity = -0.5
    app.on_ground = False
    
    # Input
    app.keys = {}
    app.shift_pressed = False
    app.mouse_last_x = 0
    app.mouse_last_y = 0
    app.camera_yaw_offset = 0.0  # Relative to player
    app.camera_pitch_offset = -30.0
    
    # HUD
    app.pos_label = Label(
        "X: 0.0  Y: 0.0  Z: 0.0",
        450, 50,
        size=16,
        fill='white',
        hud=True,
    )
    
    app.quat_label = Label(
        "Q: [0.000, 0.000, 0.000, 1.000]",
        450, 70,
        size=14,
        fill='white',
        hud=True,
    )
    
    app.minimap_bg = Circle(
        450, 150,
        50,
        fill=None,
        stroke='white',
        strokeWidth=2,
        hud=True,
    )
    
    app.minimap_player = Circle(
        450, 150, 4,
        fill=COLORS['warnings'],
        hud=True,
    )


def update_cube(app):
    """Update cube position, velocity, and collision."""
    speed = 0.3
    if app.shift_pressed:
        speed *= 3.0
    
    if 'w' in app.keys:
        app.cube_vel[0] += math.cos(app.cube_yaw) * speed
        app.cube_vel[2] += math.sin(app.cube_yaw) * speed
    if 's' in app.keys:
        app.cube_vel[0] -= math.cos(app.cube_yaw) * speed
        app.cube_vel[2] -= math.sin(app.cube_yaw) * speed
    if 'a' in app.keys:
        app.cube_yaw -= 0.1
    if 'd' in app.keys:
        app.cube_yaw += 0.1
    if 'q' in app.keys:
        app.cube_vel[0] += math.cos(app.cube_yaw + math.pi/2) * speed
        app.cube_vel[2] += math.sin(app.cube_yaw + math.pi/2) * speed
    if 'e' in app.keys:
        app.cube_vel[0] -= math.cos(app.cube_yaw + math.pi/2) * speed
        app.cube_vel[2] -= math.sin(app.cube_yaw + math.pi/2) * speed
    if ' ' in app.keys and app.on_ground:
        app.cube_vel_y = 0.5
        app.on_ground = False
    
    # Friction
    app.cube_vel[0] *= 0.95
    app.cube_vel[2] *= 0.95
    
    # Gravity
    app.cube_vel_y += app.gravity
    app.cube_vel_y *= 0.98
    
    # Update position
    app.cube_pos[0] += app.cube_vel[0]
    app.cube_pos[1] += app.cube_vel_y
    app.cube_pos[2] += app.cube_vel[2]
    
    # Collision with terrain
    terrain_height = sample_terrain_height(app.cube_pos[0], app.cube_pos[2])
    if app.cube_pos[1] < terrain_height + 0.5:
        app.cube_pos[1] = terrain_height + 0.5
        app.cube_vel_y = 0.0
        app.on_ground = True
    else:
        app.on_ground = False
    
    # Update cube shape
    app.cube.centerX = app.cube_pos[0]
    app.cube.centerY = app.cube_pos[1]
    app.cube.centerZ = app.cube_pos[2]


def update_camera(app):
    """Update follow camera that trails behind player."""
    cam_distance = 8.0
    cam_height = 5.0
    
    # Orbit around player based on cube yaw + mouse offset
    orbit_yaw = app.cube_yaw + app.camera_yaw_offset
    orbit_pitch = math.radians(app.camera_pitch_offset)
    
    # Spherical coordinates around player
    cam_x = app.cube_pos[0] - math.cos(orbit_yaw) * cam_distance * math.cos(orbit_pitch)
    cam_z = app.cube_pos[2] - math.sin(orbit_yaw) * cam_distance * math.cos(orbit_pitch)
    cam_y = app.cube_pos[1] + cam_height + cam_distance * math.sin(orbit_pitch)
    
    # Smooth follow
    pos = app.main_camera.position
    new_x = pos[0] + (cam_x - pos[0]) * app.camera_smooth_factor
    new_y = pos[1] + (cam_y - pos[1]) * app.camera_smooth_factor
    new_z = pos[2] + (cam_z - pos[2]) * app.camera_smooth_factor
    
    # Update camera position directly
    app.main_camera.position = (new_x, new_y, new_z)
    
    # Always look at player
    dx = app.cube_pos[0] - new_x
    dz = app.cube_pos[2] - new_z
    dy = app.cube_pos[1] - new_y
    
    dist_xz = (dx * dx + dz * dz) ** 0.5
    if dist_xz > 0.1:
        app.main_camera.yaw = math.atan2(dz, dx)
        app.main_camera.pitch = math.degrees(math.atan2(dy, dist_xz))


def onKeyHold(app, key):
    """Track key presses."""
    app.keys[key.lower()] = True
    if key == 'Shift':
        app.shift_pressed = True


def onKeyRelease(app, key):
    """Track key releases."""
    if key.lower() in app.keys:
        del app.keys[key.lower()]
    if key == 'Shift':
        app.shift_pressed = False


def onMouseDrag(app, x, y):
    """Reposition camera via mouse drag."""
    if not hasattr(app, '_drag_start'):
        app._drag_start = True
        app._last_drag_x = x
        app._last_drag_y = y
        return
    
    dx = x - app._last_drag_x
    dy = y - app._last_drag_y
    
    app.camera_yaw_offset += dx * 0.01
    app.camera_pitch_offset -= dy * 0.01
    app.camera_pitch_offset = max(-85, min(85, app.camera_pitch_offset))
    
    app._last_drag_x = x
    app._last_drag_y = y


def redrawAll(app):
    """Render everything."""
    update_cube(app)
    update_camera(app)
    
    # Render 3D scene
    setCamera(app.main_camera)
    clearScreen(COLORS['ash'])
    
    # Draw terrain mesh
    drawShape(app.terrain_mesh)
    
    # Draw player cube
    drawShape(app.cube)
    
    # Reset to HUD
    setCamera(None)
    
    # Update HUD
    app.pos_label.text = f"X: {app.cube_pos[0]:6.1f}  Y: {app.cube_pos[1]:6.1f}  Z: {app.cube_pos[2]:6.1f}"
    
    # Calculate quaternion from yaw rotation (Y-axis)
    half_yaw = app.cube_yaw / 2.0
    qx = 0.0
    qy = math.sin(half_yaw)
    qz = 0.0
    qw = math.cos(half_yaw)
    app.quat_label.text = f"Q: [{qx:7.4f}, {qy:7.4f}, {qz:7.4f}, {qw:7.4f}]"
    
    drawShape(app.pos_label)
    drawShape(app.quat_label)
    
    drawShape(app.minimap_bg)
    drawShape(app.minimap_player)
    
    drawLabel("WASD: Move  Q/E: Strafe  A/D: Rotate  Space: Jump  Shift: 3x Speed", 450, 500, size=12, fill='white')


runApp(width=900, height=560, enableFullscreen=True)
