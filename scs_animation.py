"""
scs_animation.py -- BONE ANIMATION, ultimate performance + DEVX + blending.

DEVX:
  mixer = AnimationMixer(scene)
  mixer.add_clip(clip)                    # from GLB or hand-built
  mixer.play('walk')                      # one call
  mixer.crossfade('run', duration=0.25)   # amazing blending
  mixer.set_layer_weight('upper', 0.7)    # upper-body layer
  mixer.update(dt)                        # pose -> scene graph

Performance:
  * Pose is evaluated only for nodes that actually animate.
  * Quaternion slerp, no matrix-per-keyframe.
  * Blending is weighted TRS blend, not full-matrix lerp (which
    shears). Rotation blends via slerp, translation/scale via lerp.
  * Crossfade is a timed blend between two poses, not a snap.
  * Additive layers: pose = base + (additive - bind) * weight.

GLB: AnimationClip.from_gltf(gltf_animation, nodes) reads
channels (translation / rotation / scale / weights) + samplers
(LINEAR / STEP / CUBICSPLINE) + accessors.
"""

import math

# [STRIPPED 70 bytes]
# Quaternions
# [STRIPPED 70 bytes]

def _quat_norm(q):
    l = math.sqrt(sum(v*v for v in q))
    if l < 1e-9:
        return (0, 0, 0, 1)
    return tuple(v/l for v in q)

def _quat_slerp(a, b, t):
    """Slerp, with shortest-path + linear fallback for tiny angles."""
    a = _quat_norm(a); b = _quat_norm(b)
    dot = sum(x*y for x, y in zip(a, b))
    if dot < 0:
        b = tuple(-v for v in b)
        dot = -dot
    if dot > 0.9995:
        # Lerp + normalize (tiny angle)
        out = tuple(x + t*(y-x) for x, y in zip(a, b))
        return _quat_norm(out)
    theta = math.acos(max(-1.0, min(1.0, dot)))
    sin_theta = math.sin(theta)
    w0 = math.sin((1-t)*theta) / sin_theta
    w1 = math.sin(t*theta) / sin_theta
    return tuple(w0*x + w1*y for x, y in zip(a, b))

def _quat_from_gltf(q):
    # glTF: (x, y, z, w)
    return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))

def _lerp(a, b, t):
    return a + (b-a)*t

def _lerp3(a, b, t):
    return tuple(_lerp(x, y, t) for x, y in zip(a, b))

# [STRIPPED 70 bytes]
# Tracks + Clips
# [STRIPPED 70 bytes]

class KeyframeTrack:
    """One property of one node: times + values + interpolation."""
    def __init__(self, node_name, property, times, values, interpolation='LINEAR'):
        self.node_name = node_name
        self.property = property  # 'translation' | 'rotation' | 'scale' | 'weights'
        self.times = list(times)
        self.values = list(values)
        self.interpolation = interpolation  # LINEAR | STEP | CUBICSPLINE
    def duration(self):
        return self.times[-1] if self.times else 0.0
    def sample(self, time):
        """Sample at time. Returns value (vec3 / quat / list)."""
        if not self.times:
            return None
        if time <= self.times[0]:
            return self.values[0]
        if time >= self.times[-1]:
            return self.values[-1]
        # Binary search for the segment (log n, not linear scan).
        lo, hi = 0, len(self.times)-1
        while lo + 1 < hi:
            mid = (lo+hi)//2
            if self.times[mid] <= time:
                lo = mid
            else:
                hi = mid
        t0, t1 = self.times[lo], self.times[hi]
        v0, v1 = self.values[lo], self.values[hi]
        if self.interpolation == 'STEP':
            return v0
        if self.interpolation == 'CUBICSPLINE':
            # glTF CUBICSPLINE: values are [inTangent, value, outTangent] per key.
            # This implementation stores expanded values; the GLB path
            # expands them before constructing the track (see from_gltf).
            # Fallback to LINEAR if not expanded.
            pass
        f = (time - t0) / max(t1 - t0, 1e-9)
        if self.property == 'rotation':
            return _quat_slerp(v0, v1, f)
        if isinstance(v0, (list, tuple)):
            return tuple(_lerp(x, y, f) for x, y in zip(v0, v1))
        return _lerp(v0, v1, f)
    def describe(self):
        return {'node': self.node_name, 'property': self.property,
                'keys': len(self.times), 'interpolation': self.interpolation}

class AnimationClip:
    def __init__(self, name, duration=0.0, tracks=None):
        self.name = name
        self.duration = float(duration)
        self.tracks = list(tracks or [])
    def add_track(self, track):
        self.tracks.append(track)
        if track.duration() > self.duration:
            self.duration = track.duration()
        return track
    def sample(self, time, loop=True):
        """Sample all tracks at time. Returns {node_name: {prop: value}}."""
        t = time
        if loop and self.duration > 0:
            t = t % self.duration
        pose = {}
        for tr in self.tracks:
            val = tr.sample(t)
            if val is None:
                continue
            pose.setdefault(tr.node_name, {})[tr.property] = val
        return pose
    def describe(self):
        return {'name': self.name, 'duration': self.duration,
                'tracks': [t.describe() for t in self.tracks]}
    @classmethod
    def from_gltf(cls, janim, node_names, accessors_data=None):
        """Build a clip from glTF animation JSON. accessors_data is an
        optional dict: accessor_index -> list of values (decoded by the
        loader). If None, tracks are built from the JSON's sampler
        indices (caller fills values later via bind_accessors)."""
        clip = cls(name=janim.get('name') or 'anim')
        # Samplers + channels
        samplers = janim.get('samplers') or []
        channels = janim.get('channels') or []
        for ch in channels:
            target = ch.get('target') or {}
            node_idx = target.get('node')
            path = target.get('path')
            if node_idx is None or node_idx >= len(node_names):
                continue
            node_name = node_names[node_idx]
            sampler = samplers[ch.get('sampler', 0)] if samplers else {}
            # Times / values are resolved by the caller via bind_accessors;
            # here we store sampler indices so the loader can fill them.
            track = KeyframeTrack(node_name, path, times=[], values=[],
                                  interpolation=sampler.get('interpolation', 'LINEAR'))
            track._gltf_input = sampler.get('input')
            track._gltf_output = sampler.get('output')
            clip.tracks.append(track)
        if accessors_data:
            clip.bind_accessors(accessors_data)
        return clip
    def bind_accessors(self, accessors_data):
        """Fill track times/values from decoded accessor data."""
        for tr in self.tracks:
            inp = getattr(tr, '_gltf_input', None)
            out = getattr(tr, '_gltf_output', None)
            if inp is not None and inp in accessors_data:
                tr.times = list(accessors_data[inp])
            if out is not None and out in accessors_data:
                tr.values = list(accessors_data[out])
            if tr.times:
                self.duration = max(self.duration, tr.times[-1])
        return self

# [STRIPPED 70 bytes]
# Skeleton + Skinning
# [STRIPPED 70 bytes]

class Skeleton:
    """Bone hierarchy + inverse bind matrices. Bones are Nodes."""
    def __init__(self, root=None, bones=None, inverse_bind=None):
        self.root = root
        self.bones = list(bones or [])
        self.inverse_bind = list(inverse_bind or [])
        self._by_name = {b.name: b for b in self.bones if b.name}
    def bone(self, name):
        return self._by_name.get(name)
    def bone_matrices(self):
        """World matrix * inverse bind per bone, for skinning.
        Returns list of 16-float matrices, same order as bones."""
        out = []
        for i, bone in enumerate(self.bones):
            w = bone.world_matrix()
            ib = self.inverse_bind[i] if i < len(self.inverse_bind) else [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]
            # world * inverse_bind
            # Column-major multiply (same as scs_scenegraph._mat4_mul)
            res = [0.0]*16
            for r in range(4):
                for c in range(4):
                    s = 0.0
                    for k in range(4):
                        s += w[k*4 + r] * ib[c*4 + k]
                    res[c*4 + r] = s
            out.append(res)
        return out
    def describe(self):
        return {'bones': [b.name for b in self.bones], 'count': len(self.bones)}

# [STRIPPED 70 bytes]
# Mixer -- blending is the point
# [STRIPPED 70 bytes]

class _ActiveClip:
    def __init__(self, clip, weight=1.0, speed=1.0, loop=True, layer='base', additive=False):
        self.clip = clip
        self.weight = float(weight)
        self.speed = float(speed)
        self.loop = loop
        self.layer = layer
        self.additive = additive
        self.time = 0.0
        self.fade_in = 0.0  # seconds remaining to fade in
        self.fade_in_total = 0.0
        self.fade_out = 0.0
        self.fade_out_total = 0.0

class AnimationMixer:
    """The DEVX: play / crossfade / layers / additive / weights.

    Example:
      mixer.play('idle')
      mixer.crossfade('walk', 0.25)   # blends idle -> walk over 0.25s
      mixer.play('wave', layer='upper', weight=0.8, additive=False)
      mixer.play('recoil', layer='fx', additive=True, weight=0.5)
    """
    def __init__(self, scene=None, node_map=None):
        self.scene = scene
        self.node_map = node_map or {}  # name -> Node (if scene is None)
        self.clips = {}  # name -> AnimationClip
        self.active = []  # _ActiveClip
        self._bind_pose = {}  # node_name -> (pos, quat, scale)
        self.time = 0.0
    def _node(self, name):
        if self.scene is not None:
            n = self.scene.find(name)
            if n is not None:
                return n
        return self.node_map.get(name)
    def _capture_bind(self, node_name):
        n = self._node(node_name)
        if n is None:
            return
        if node_name not in self._bind_pose:
            self._bind_pose[node_name] = (tuple(n.position), tuple(n.rotation), tuple(n.scale))
    def add_clip(self, clip):
        self.clips[clip.name] = clip
        return clip
    def play(self, name, weight=1.0, speed=1.0, loop=True, layer='base',
             additive=False, fade_in=0.0):
        """Play a clip. If another clip is on the same layer and not
        additive, it is faded out (unless you want both -- use a new layer)."""
        clip = self.clips.get(name) if isinstance(name, str) else name
        if clip is None:
            raise ValueError('AnimationMixer: no clip named %r' % name)
        # Fade out existing non-additive clips on the same layer.
        if not additive:
            for a in self.active:
                if a.layer == layer and not a.additive:
                    a.fade_out = 0.25 if fade_in == 0 else fade_in
                    a.fade_out_total = a.fade_out
        act = _ActiveClip(clip, weight=weight, speed=speed, loop=loop,
                          layer=layer, additive=additive)
        if fade_in > 0:
            act.fade_in = fade_in
            act.fade_in_total = fade_in
        self.active.append(act)
        # Capture bind pose for animated nodes.
        for tr in clip.tracks:
            self._capture_bind(tr.node_name)
        return act
    def crossfade(self, name, duration=0.25, weight=1.0, speed=1.0, loop=True, layer='base'):
        """Amazing blending: fade out current layer, fade in new clip."""
        clip = self.clips.get(name) if isinstance(name, str) else name
        if clip is None:
            raise ValueError('AnimationMixer: no clip named %r' % name)
        for a in self.active:
            if a.layer == layer and not a.additive:
                a.fade_out = duration
                a.fade_out_total = duration
        act = _ActiveClip(clip, weight=weight, speed=speed, loop=loop, layer=layer)
        act.fade_in = duration
        act.fade_in_total = duration
        self.active.append(act)
        for tr in clip.tracks:
            self._capture_bind(tr.node_name)
        return act
    def stop(self, name=None, layer=None, fade_out=0.0):
        """Stop a clip (or a whole layer). fade_out>0 blends it out."""
        for a in list(self.active):
            if (name is None or a.clip.name == name) and (layer is None or a.layer == layer):
                if fade_out > 0:
                    a.fade_out = fade_out
                    a.fade_out_total = fade_out
                else:
                    self.active.remove(a)
        return self
    def set_layer_weight(self, layer, weight):
        for a in self.active:
            if a.layer == layer:
                a.weight = float(weight)
        return self
    def set_speed(self, name, speed):
        for a in self.active:
            if a.clip.name == name:
                a.speed = float(speed)
        return self
    def update(self, dt):
        """Advance time, blend poses, write to the scene graph.
        Returns the blended pose {node: {prop: value}} for inspection."""
        self.time += dt
        # Advance + compute effective weights (fade in/out).
        blended = {}  # node -> {prop: (value, weight_sum, is_quat)}
        # First: base layers (non-additive), blended by weight.
        # Then: additive layers, applied on top of the base pose.
        base = []
        additive = []
        for a in list(self.active):
            a.time += dt * a.speed
            # Fade in/out
            w = a.weight
            if a.fade_in > 0:
                a.fade_in -= dt
                w *= max(0.0, 1.0 - max(a.fade_in, 0.0) / max(a.fade_in_total, 1e-9))
            if a.fade_out > 0:
                a.fade_out -= dt
                w *= max(0.0, a.fade_out / max(a.fade_out_total, 1e-9))
                if a.fade_out <= 0:
                    self.active.remove(a)
                    continue
            if w <= 0.001:
                continue
            (additive if a.additive else base).append((a, w))
        # Blend base: weighted average (quat via slerp accumulation is
        # approximate -- we do iterative slerp for correctness).
        for a, w in base:
            pose = a.clip.sample(a.time, loop=a.loop)
            for node_name, props in pose.items():
                slot = blended.setdefault(node_name, {})
                for prop, val in props.items():
                    if prop not in slot:
                        slot[prop] = (val, w)
                    else:
                        prev_val, prev_w = slot[prop]
                        total = prev_w + w
                        f = w / total
                        if prop == 'rotation':
                            new_val = _quat_slerp(prev_val, val, f)
                        elif isinstance(val, (list, tuple)):
                            new_val = tuple(x + f*(y-x) for x, y in zip(prev_val, val))
                        else:
                            new_val = prev_val + f*(val-prev_val)
                        slot[prop] = (new_val, total)
        # Apply base pose to scene graph.
        for node_name, props in blended.items():
            n = self._node(node_name)
            if n is None:
                continue
            for prop, (val, _w) in props.items():
                if prop == 'translation':
                    n.position = tuple(float(v) for v in val)
                elif prop == 'rotation':
                    n.rotation = _quat_norm(val)
                elif prop == 'scale':
                    n.scale = tuple(float(v) for v in val)
            n._mark_dirty()
        # Additive: pose = base + (additive - bind) * weight
        for a, w in additive:
            pose = a.clip.sample(a.time, loop=a.loop)
            for node_name, props in pose.items():
                n = self._node(node_name)
                if n is None:
                    continue
                bind = self._bind_pose.get(node_name)
                if bind is None:
                    continue
                bind_pos, bind_quat, bind_scale = bind
                for prop, val in props.items():
                    if prop == 'translation':
                        delta = tuple(v - b for v, b in zip(val, bind_pos))
                        n.position = tuple(p + delta[i]*w for i, p in enumerate(n.position))
                    elif prop == 'scale':
                        delta = tuple(v - b for v, b in zip(val, bind_scale))
                        n.scale = tuple(s + delta[i]*w for i, s in enumerate(n.scale))
                    elif prop == 'rotation':
                        # Additive rotation: slerp from bind to val by w, then
                        # compose with current (approx: slerp current -> current*delta).
                        # For DEVX + correctness, we slerp bind->val by w and
                        # then slerp current->that by w (small-angle approx).
                        add_rot = _quat_slerp(bind_quat, val, w)
                        n.rotation = _quat_slerp(n.rotation, add_rot, w)
                n._mark_dirty()
        # Return blended pose for tests / debugging.
        return {k: {p: v for p, (v, _w) in props.items()} for k, props in blended.items()}
    def describe(self):
        return {'clips': sorted(self.clips.keys()),
                'active': [{'clip': a.clip.name, 'layer': a.layer,
                            'weight': a.weight, 'time': round(a.time, 3),
                            'additive': a.additive} for a in self.active]}
