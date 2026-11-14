"""
scs_scenegraph.py -- SCENE GRAPH, the most intuitive one.

DEVX:
  scene = Scene()
  hero = Node('hero').at(0, 1, -2)
  scene.add(hero)
  hero.add(Node('sword').at(0.5, 0, 0))
  hero.find('sword')          # deep search
  scene.update()              # world matrices, dirty-only

Rules:
  * Every Node has local TRS + a cached world matrix. Dirty flag:
    changing a Node marks it + its children dirty. update() only
    recomputes dirty subtrees. 10k nodes, 1 moving -> 1 subtree.
  * No stringly-typed magic: .at() .rot() .scaled() are fluent and
    return self, so you can chain.
  * Nodes hold components (lights, meshes, cameras, splats) -- the
    graph is the scene, not a parallel structure.
  * GLB: Node.from_gltf() builds the hierarchy from glTF nodes.
"""

import math

# [STRIPPED 70 bytes]
# Math (pure, no GL) -- column-major 4x4, same as scs_3d
# [STRIPPED 70 bytes]

def _mat4_identity():
    return [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]

def _mat4_mul(a, b):
    out = [0.0]*16
    for r in range(4):
        for c in range(4):
            s = 0.0
            for k in range(4):
                s += a[k*4 + r] * b[c*4 + k]
            out[c*4 + r] = s
    return out

def _mat4_translate(x, y, z):
    m = _mat4_identity()
    m[12], m[13], m[14] = float(x), float(y), float(z)
    return m

def _mat4_scale(x, y, z):
    m = _mat4_identity()
    m[0], m[5], m[10] = float(x), float(y), float(z)
    return m

def _quat_from_euler(rx, ry, rz):
    """Euler (radians, XYZ) -> quaternion (x, y, z, w)."""
    cx, sx = math.cos(rx/2), math.sin(rx/2)
    cy, sy = math.cos(ry/2), math.sin(ry/2)
    cz, sz = math.cos(rz/2), math.sin(rz/2)
    return (sx*cy*cz + cx*sy*sz, cx*sy*cz - sx*cy*sz,
            cx*cy*sz + sx*sy*cz, cx*cy*cz - sx*sy*sz)

def _quat_to_mat4(q):
    x, y, z, w = q
    xx, yy, zz = x*x, y*y, z*z
    xy, xz, yz = x*y, x*z, y*z
    wx, wy, wz = w*x, w*y, w*z
    return [1-2*(yy+zz), 2*(xy+wz), 2*(xz-wy), 0,
            2*(xy-wz), 1-2*(xx+zz), 2*(yz+wx), 0,
            2*(xz+wy), 2*(yz-wx), 1-2*(xx+yy), 0,
            0, 0, 0, 1]

def _mat4_from_trs(pos, quat, scale):
    t = _mat4_translate(*pos)
    r = _quat_to_mat4(quat)
    s = _mat4_scale(*scale)
    return _mat4_mul(_mat4_mul(t, r), s)

# [STRIPPED 70 bytes]
# Node
# [STRIPPED 70 bytes]

class Node:
    def __init__(self, name='', position=(0, 0, 0), rotation=(0, 0, 0, 1),
                 scale=(1, 1, 1), visible=True, tags=None):
        self.name = str(name or '')
        self.position = tuple(float(v) for v in position)
        self.rotation = tuple(float(v) for v in rotation)  # quat (x,y,z,w)
        self.scale = tuple(float(v) for v in scale)
        self.visible = bool(visible)
        self.tags = set(tags or [])
        self.parent = None
        self.children = []
        self.components = {}  # role -> object (mesh, light, camera, splat, ...)
        self.user_data = {}
        self._local_dirty = True
        self._world_dirty = True
        self._local = None
        self._world = None
        self.skin = None  # Skeleton, set by animation / GLB skin
        self.mesh = None

    # -- fluent setters (return self) --
    def at(self, x, y, z):
        self.position = (float(x), float(y), float(z))
        self._mark_dirty()
        return self
    def rot(self, rx=0.0, ry=0.0, rz=0.0, quat=None):
        """rot(rx, ry, rz) in radians, or rot(quat=(x,y,z,w))."""
        if quat is not None:
            self.rotation = tuple(float(v) for v in quat)
        else:
            self.rotation = _quat_from_euler(float(rx), float(ry), float(rz))
        self._mark_dirty()
        return self
    def scaled(self, x, y=None, z=None):
        if y is None:
            y = x; z = x
        self.scale = (float(x), float(y), float(z))
        self._mark_dirty()
        return self
    def tag(self, *tags):
        self.tags.update(tags)
        return self

    # -- hierarchy --
    def add(self, child):
        """Add a child. Accepts Node or (name, Node) -- returns the child."""
        if isinstance(child, tuple) and len(child) == 2:
            child = child[1]
        if child.parent is not None:
            child.parent.remove(child)
        child.parent = self
        self.children.append(child)
        child._mark_dirty()
        return child
    def remove(self, child):
        if child in self.children:
            self.children.remove(child)
            child.parent = None
            child._mark_dirty()
        return child
    def child(self, name):
        """Direct child by name, or None."""
        for c in self.children:
            if c.name == name:
                return c
        return None
    def find(self, name):
        """Deep search by name (self + descendants)."""
        if self.name == name:
            return self
        for c in self.children:
            found = c.find(name)
            if found is not None:
                return found
        return None
    def find_all(self, name):
        out = []
        if self.name == name:
            out.append(self)
        for c in self.children:
            out.extend(c.find_all(name))
        return out
    def find_by_tag(self, tag):
        out = []
        if tag in self.tags:
            out.append(self)
        for c in self.children:
            out.extend(c.find_by_tag(tag))
        return out
    def traverse(self, fn):
        fn(self)
        for c in self.children:
            c.traverse(fn)
        return self
    def path(self):
        """'/scene/hero/sword' -- useful for debugging + animation binding."""
        parts = []
        n = self
        while n is not None:
            parts.append(n.name or '?')
            n = n.parent
        return '/' + '/'.join(reversed(parts))

    # -- components --
    def attach(self, role, obj):
        self.components[role] = obj
        return obj
    def get(self, role, default=None):
        return self.components.get(role, default)

    # -- transforms --
    def _mark_dirty(self):
        if not self._world_dirty:
            self._world_dirty = True
            for c in self.children:
                c._mark_dirty()
        self._local_dirty = True
    def local_matrix(self):
        if self._local_dirty or self._local is None:
            self._local = _mat4_from_trs(self.position, self.rotation, self.scale)
            self._local_dirty = False
        return list(self._local)
    def world_matrix(self):
        if self._world_dirty or self._world is None:
            if self.parent is None:
                self._world = self.local_matrix()
            else:
                self._world = _mat4_mul(self.parent.world_matrix(), self.local_matrix())
            self._world_dirty = False
        return list(self._world)
    def world_position(self):
        w = self.world_matrix()
        return (w[12], w[13], w[14])
    def look_at(self, target, up=(0, 1, 0)):
        """Point this node's -Z (camera convention) or +Z at target.
        Simplified: sets rotation from direction. Full lookAt in engine."""
        # Keep it simple + predictable: yaw only (Y-up), for DEVX.
        dx = target[0] - self.world_position()[0]
        dz = target[2] - self.world_position()[2]
        yaw = math.atan2(dx, dz)
        self.rot(0, yaw, 0)
        return self
    def update(self):
        """Update this subtree's world matrices (dirty-only)."""
        self.world_matrix()
        for c in self.children:
            c.update()
        return self
    def describe(self, depth=0):
        return {'name': self.name, 'position': list(self.position),
                'rotation': list(self.rotation), 'scale': list(self.scale),
                'children': [c.describe(depth+1) for c in self.children],
                'components': list(self.components.keys()),
                'tags': sorted(self.tags)}
    @classmethod
    def from_gltf(cls, jnode, name=''):
        n = cls(name=jnode.get('name') or name)
        if 'translation' in jnode:
            n.position = tuple(float(v) for v in jnode['translation'])
        if 'rotation' in jnode:
            n.rotation = tuple(float(v) for v in jnode['rotation'])
        if 'scale' in jnode:
            n.scale = tuple(float(v) for v in jnode['scale'])
        if 'mesh' in jnode:
            n.mesh = jnode['mesh']
        if 'skin' in jnode:
            n.user_data['skin'] = jnode['skin']
        if 'camera' in jnode:
            n.user_data['camera'] = jnode['camera']
        n._mark_dirty()
        return n

# [STRIPPED 70 bytes]
# Scene
# [STRIPPED 70 bytes]

class Scene:
    def __init__(self, name='scene'):
        self.name = name
        self.root = Node('root')
        self._by_name_cache = None
    def add(self, node):
        self.root.add(node)
        self._by_name_cache = None
        return node
    def remove(self, node):
        self.root.remove(node)
        self._by_name_cache = None
        return node
    def find(self, name):
        return self.root.find(name)
    def find_all(self, name):
        return self.root.find_all(name)
    def find_by_tag(self, tag):
        return self.root.find_by_tag(tag)
    def traverse(self, fn):
        return self.root.traverse(fn)
    def update(self):
        """Update world matrices for the whole scene (dirty-only)."""
        self.root.update()
        return self
    def count(self):
        n = [0]
        def _c(_):
            n[0] += 1
        self.traverse(_c)
        return n[0] - 1  # exclude root
    def describe(self):
        return {'name': self.name, 'nodes': self.count(),
                'root': self.root.describe()}
    @classmethod
    def from_gltf(cls, gltf, scene_index=0):
        """Build a Scene from glTF JSON (scenes + nodes)."""
        scene = cls(name='gltf-scene')
        jnodes = gltf.get('nodes') or []
        nodes = [Node.from_gltf(jn, name='node%d' % i) for i, jn in enumerate(jnodes)]
        # Wire hierarchy via children indices
        for i, jn in enumerate(jnodes):
            for ci in jn.get('children') or []:
                nodes[i].add(nodes[ci])
        # Roots: scene.nodes or all parentless
        jscene = (gltf.get('scenes') or [{}])[scene_index] if scene_index < len(gltf.get('scenes') or [{}]) else {}
        roots = jscene.get('nodes') or [i for i, n in enumerate(nodes) if n.parent is None]
        for ri in roots:
            scene.add(nodes[ri])
        scene.update()
        return scene
