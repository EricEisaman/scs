"""
scs_3d.py - REAL 3D math + mesh generation for SCS.

This is what scs_webgl.py was missing: no depth, no MVP, no mesh,
no perspective, no lookAt. This module is pure Python (no GL calls),
so it is testable without a browser and usable by every backend:

  * WebGL2: scs_webgl.RendererWebGL2 consumes the matrices + mesh
    and draws them with a real 3D shader + depth test.
  * Canvas2D fallback: Camera3D.project() gives screen coords, so
    the same scene still renders as shaded 2D circles.

Coordinate system: right-handed, Y up, -Z forward (OpenGL convention).
Camera yaw=0 looks down -Z. WASD moves in the camera's XZ plane.
"""

import math


# ----------------------------------------------------------------------
# Vec3 (plain tuples, no numpy -- Brython-safe)
# ----------------------------------------------------------------------

def v3(x=0.0, y=0.0, z=0.0):
    return (float(x), float(y), float(z))


def v3_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v3_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v3_scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def v3_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v3_cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def v3_length(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def v3_normalize(a):
    l = v3_length(a)
    if l == 0:
        return (0.0, 0.0, 0.0)
    return (a[0] / l, a[1] / l, a[2] / l)


def v3_distance(a, b):
    return v3_length(v3_sub(a, b))


# ----------------------------------------------------------------------
# Mat4 -- column-major, OpenGL layout, flat list of 16 floats.
# mat4_mul(a, b) returns a * b (b applied first, then a).
# ----------------------------------------------------------------------

def mat4_identity():
    return [1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0]


def mat4_mul(a, b):
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            s = 0.0
            for k in range(4):
                s += a[k * 4 + row] * b[col * 4 + k]
            out[col * 4 + row] = s
    return out


def mat4_translate(x, y, z):
    m = mat4_identity()
    m[12] = float(x)
    m[13] = float(y)
    m[14] = float(z)
    return m


def mat4_scale(sx, sy, sz):
    m = mat4_identity()
    m[0] = float(sx)
    m[5] = float(sy)
    m[10] = float(sz)
    return m


def mat4_perspective(fov_deg, aspect, near, far):
    """Perspective projection. fov is vertical, in degrees."""
    f = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    m = [0.0] * 16
    m[0] = f / aspect
    m[5] = f
    m[10] = (far + near) / (near - far)
    m[11] = -1.0
    m[14] = (2.0 * far * near) / (near - far)
    return m


def mat4_look_at(eye, target, up=(0.0, 1.0, 0.0)):
    """View matrix: camera at eye, looking at target."""
    f = v3_normalize(v3_sub(target, eye))
    s = v3_normalize(v3_cross(f, up))
    # If forward is parallel to up, pick a different up.
    if v3_length(s) == 0:
        s = v3_normalize(v3_cross(f, (1.0, 0.0, 0.0)))
    u = v3_cross(s, f)
    m = mat4_identity()
    m[0] = s[0]
    m[4] = s[1]
    m[8] = s[2]
    m[1] = u[0]
    m[5] = u[1]
    m[9] = u[2]
    m[2] = -f[0]
    m[6] = -f[1]
    m[10] = -f[2]
    m[12] = -v3_dot(s, eye)
    m[13] = -v3_dot(u, eye)
    m[14] = v3_dot(f, eye)
    return m


def mat4_transform_point(m, p):
    """Transform a 3D point by a Mat4, with perspective divide."""
    x, y, z = p
    cx = m[0] * x + m[4] * y + m[8] * z + m[12]
    cy = m[1] * x + m[5] * y + m[9] * z + m[13]
    cz = m[2] * x + m[6] * y + m[10] * z + m[14]
    cw = m[3] * x + m[7] * y + m[11] * z + m[15]
    if cw != 0:
        return (cx / cw, cy / cw, cz / cw, cw)
    return (cx, cy, cz, cw)


# ----------------------------------------------------------------------
# Camera3D -- the WASD camera. One object owns position + yaw/pitch.
# The SAME camera drives the GL view matrix AND the Web Audio
# listener (scs_spatial_audio), so what you see is what you hear.
# ----------------------------------------------------------------------

class Camera3D:
    def __init__(self, position=(0.0, 2.0, 6.0), yaw=0.0, pitch=0.0,
                 fov=60.0, near=0.1, far=100.0):
        self.position = v3(*position)
        self.yaw = float(yaw)      # degrees, 0 = looking down -Z
        self.pitch = float(pitch)  # degrees, + = looking up
        self.fov = float(fov)
        self.near = float(near)
        self.far = float(far)

    def forward(self):
        yaw = math.radians(self.yaw)
        pitch = math.radians(self.pitch)
        return v3_normalize((
            -math.sin(yaw) * math.cos(pitch),
            math.sin(pitch),
            -math.cos(yaw) * math.cos(pitch),
        ))

    def right(self):
        # Right = forward x world-up, normalized. Yaw-only (no roll).
        f = self.forward()
        r = v3_cross(f, (0.0, 1.0, 0.0))
        return v3_normalize(r)

    def up(self):
        r = self.right()
        f = self.forward()
        return v3_cross(r, f)

    def look(self, dyaw_deg, dpitch_deg):
        """Mouse drag: dyaw + = turn right, dpitch + = look up."""
        self.yaw += float(dyaw_deg)
        self.pitch = max(-89.0, min(89.0, self.pitch + float(dpitch_deg)))

    def move_forward(self, dist):
        # WASD moves in the XZ plane (no flying when looking up).
        yaw = math.radians(self.yaw)
        dx = -math.sin(yaw) * dist
        dz = -math.cos(yaw) * dist
        self.position = v3_add(self.position, (dx, 0.0, dz))

    def move_right(self, dist):
        yaw = math.radians(self.yaw)
        dx = math.cos(yaw) * dist
        dz = -math.sin(yaw) * dist
        self.position = v3_add(self.position, (dx, 0.0, dz))

    def move_up(self, dist):
        self.position = v3_add(self.position, (0.0, dist, 0.0))

    def move(self, forward=0.0, right=0.0, up=0.0):
        """Combined WASD step. Called from onKeyHold every step."""
        if forward:
            self.move_forward(forward)
        if right:
            self.move_right(right)
        if up:
            self.move_up(up)

    def view_matrix(self):
        target = v3_add(self.position, self.forward())
        return mat4_look_at(self.position, target, (0.0, 1.0, 0.0))

    def proj_matrix(self, aspect):
        return mat4_perspective(self.fov, aspect, self.near, self.far)

    def project(self, world, viewport_w, viewport_h):
        """World -> (screen_x, screen_y, depth, behind).

        screen origin is top-left, like SCS. behind=True means the
        point is behind the camera and must not be drawn.
        """
        view = self.view_matrix()
        proj = self.proj_matrix(viewport_w / float(viewport_h))
        mvp = mat4_mul(proj, view)
        nx, ny, nz, w = mat4_transform_point(mvp, world)
        if w <= 0:
            return (0.0, 0.0, 0.0, True)
        sx = (nx + 1.0) * 0.5 * viewport_w
        sy = (1.0 - (ny + 1.0) * 0.5) * viewport_h
        return (sx, sy, nz, False)

    def describe(self):
        return {'position': self.position, 'yaw': self.yaw,
                'pitch': self.pitch, 'fov': self.fov}


# ----------------------------------------------------------------------
# Meshes -- generated in Python, uploaded once by the GL renderer.
# ----------------------------------------------------------------------

def make_sphere_mesh(lat_segments=24, lon_segments=32):
    """UV sphere, radius 1, centred at origin.

    Returns (vertices, indices) where vertices is flat
    [x, y, z, nx, ny, nz, ...] and indices is flat [i0, i1, i2, ...].
    """
    verts = []
    for lat in range(lat_segments + 1):
        theta = math.pi * lat / lat_segments  # 0 = north pole
        sin_t, cos_t = math.sin(theta), math.cos(theta)
        for lon in range(lon_segments + 1):
            phi = 2.0 * math.pi * lon / lon_segments
            sin_p, cos_p = math.sin(phi), math.cos(phi)
            x = sin_t * cos_p
            y = cos_t
            z = sin_t * sin_p
            verts.extend([x, y, z, x, y, z])  # pos == normal on unit sphere
    idx = []
    row = lon_segments + 1
    for lat in range(lat_segments):
        for lon in range(lon_segments):
            a = lat * row + lon
            b = a + row
            idx.extend([a, b, a + 1, b, b + 1, a + 1])
    return (verts, idx)


def make_cube_mesh():
    """Unit cube centred at origin, 36 indices, per-face normals."""
    # 6 faces x 4 verts, non-indexed normals via explicit verts.
    faces = [
        # (normal, 4 corners)
        ((0, 0, 1), [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),
        ((0, 0, -1), [(1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1)]),
        ((1, 0, 0), [(1, -1, 1), (1, -1, -1), (1, 1, -1), (1, 1, 1)]),
        ((-1, 0, 0), [(-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1)]),
        ((0, 1, 0), [(-1, 1, 1), (1, 1, 1), (1, 1, -1), (-1, 1, -1)]),
        ((0, -1, 0), [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)]),
    ]
    verts = []
    idx = []
    base = 0
    for (nx, ny, nz), corners in faces:
        for (x, y, z) in corners:
            verts.extend([x * 0.5, y * 0.5, z * 0.5, nx, ny, nz])
        idx.extend([base, base + 1, base + 2,
                    base, base + 2, base + 3])
        base += 4
    return (verts, idx)


def make_floor_grid(size=20, step=1):
    """Grid lines on the XZ plane (y=0). Returns flat [x,y,z, ...] pairs."""
    pts = []
    h = size / 2.0
    n = int(size / step)
    for i in range(-n, n + 1):
        c = i * step
        pts.extend([-h, 0.0, c, h, 0.0, c])   # line parallel to X
        pts.extend([c, 0.0, -h, c, 0.0, h])   # line parallel to Z
    return pts
