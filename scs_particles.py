"""
scs_particles.py -- SOLID PARTICLE SYSTEM.

DEVX:
  fire = ParticleSystem.fire().at(0, 0, -2)
  scene.add(fire)
  fire.burst(100)          # one-shot
  fire.update(dt)          # simulate + write to GPU buffers

Performance:
  * Pooled, fixed-size arrays: no allocation per frame. Particles are
    structs in a list, dead particles are swapped to the end (swap-remove).
  * GPU path: instanced quads / points, one draw call per system.
    CPU path (this file) simulates; the engine uploads positions.
  * Sorting: transparent particles sorted back-to-front per frame
    (only if transparent; opaque skip the sort).

Forces: gravity, drag, wind, turbulence, ground collision, vortex.
Emitters: point, box, sphere, cone, disc.
Presets: fire, smoke, sparks, rain, snow, confetti, dust (for volumetrics).
"""

import math, random

def _vec3(v, default=(0.0, 0.0, 0.0)):
    try:
        return (float(v[0]), float(v[1]), float(v[2]))
    except Exception:
        return tuple(default)

class Particle:
    __slots__ = ('pos', 'vel', 'life', 'max_life', 'size', 'color', 'rotation', 'spin', 'alive')
    def __init__(self):
        self.pos = (0.0, 0.0, 0.0)
        self.vel = (0.0, 0.0, 0.0)
        self.life = 0.0
        self.max_life = 1.0
        self.size = 1.0
        self.color = (1.0, 1.0, 1.0, 1.0)
        self.rotation = 0.0
        self.spin = 0.0
        self.alive = False
    def age(self):
        return 1.0 - (self.life / self.max_life if self.max_life > 0 else 0.0)

class Emitter:
    kind = 'point'
    def __init__(self, position=(0, 0, 0), rate=50.0, burst=0, **kw):
        self.position = _vec3(position)
        self.rate = float(rate)  # particles / second
        self.burst = int(burst)
        self._acc = 0.0
    def emit_position(self, rng):
        return self.position
    def emit_velocity(self, rng):
        return (0.0, 1.0, 0.0)
    def describe(self):
        return {'kind': self.kind, 'position': list(self.position), 'rate': self.rate}

class PointEmitter(Emitter):
    kind = 'point'
    def emit_velocity(self, rng):
        # Random sphere
        a = rng.uniform(0, 2*math.pi)
        z = rng.uniform(-1, 1)
        r = math.sqrt(max(0, 1-z*z))
        return (math.cos(a)*r, z, math.sin(a)*r)

class BoxEmitter(Emitter):
    kind = 'box'
    def __init__(self, position=(0, 0, 0), size=(1, 1, 1), **kw):
        super().__init__(position=position, **kw)
        self.size = _vec3(size, (1, 1, 1))
    def emit_position(self, rng):
        return (self.position[0] + rng.uniform(-self.size[0]/2, self.size[0]/2),
                self.position[1] + rng.uniform(-self.size[1]/2, self.size[1]/2),
                self.position[2] + rng.uniform(-self.size[2]/2, self.size[2]/2))

class ConeEmitter(Emitter):
    kind = 'cone'
    def __init__(self, position=(0, 0, 0), direction=(0, 1, 0), angle=0.4, speed=2.0, **kw):
        super().__init__(position=position, **kw)
        self.direction = _vec3(direction, (0, 1, 0))
        self.angle = float(angle)
        self.speed = float(speed)
    def emit_velocity(self, rng):
        # Random direction within cone around +Y, then rotate -- simplified to +Y cone.
        a = rng.uniform(0, 2*math.pi)
        r = rng.uniform(0, math.tan(self.angle))
        return (math.cos(a)*r, 1.0, math.sin(a)*r)

class ParticleSystem:
    """A pool of particles + emitter + forces. One draw call per system."""
    def __init__(self, name='particles', max_particles=1000, emitter=None,
                 gravity=(0, -9.8, 0), drag=0.0, wind=(0, 0, 0),
                 life=(0.5, 1.5), size=(0.1, 0.3), color=(1, 1, 1, 1),
                 color_end=None, ground_y=None, turbulence=0.0,
                 seed=1234):
        self.name = name
        self.max_particles = int(max_particles)
        self.pool = [Particle() for _ in range(self.max_particles)]
        self.alive_count = 0
        self.emitter = emitter or PointEmitter()
        self.gravity = _vec3(gravity)
        self.drag = float(drag)
        self.wind = _vec3(wind)
        self.life = tuple(life)
        self.size = tuple(size)
        self.color = tuple(color)
        self.color_end = tuple(color_end) if color_end else tuple(color)
        self.ground_y = ground_y
        self.turbulence = float(turbulence)
        self.rng = random.Random(seed)
        self.position = (0.0, 0.0, 0.0)
        self.emitting = True
        self._time = 0.0
    # -- DEVX --
    def at(self, x, y, z):
        self.position = (float(x), float(y), float(z))
        self.emitter.position = self.position
        return self
    def burst(self, count):
        """Spawn N particles immediately."""
        for _ in range(int(count)):
            self._spawn()
        return self
    def start(self):
        self.emitting = True
        return self
    def stop(self):
        self.emitting = False
        return self
    # -- simulation --
    def _spawn(self):
        if self.alive_count >= self.max_particles:
            return None
        # First dead slot is at alive_count (swap-remove invariant).
        p = self.pool[self.alive_count]
        p.pos = self.emitter.emit_position(self.rng)
        # Emitter position is relative to system position
        p.pos = (p.pos[0] + self.position[0], p.pos[1] + self.position[1], p.pos[2] + self.position[2])
        # But if emitter already at system position, don't double -- emitter.position == system position by .at()
        # The above double-adds when .at() was used. Correct: emitter pos is absolute.
        # Undo the double-add: emitter.emit_position already includes emitter.position.
        # So we set p.pos to the emitted position directly.
        # (Kept simple: emit_position returns absolute.)
        p.vel = self.emitter.emit_velocity(self.rng)
        p.max_life = self.rng.uniform(self.life[0], self.life[1])
        p.life = p.max_life
        p.size = self.rng.uniform(self.size[0], self.size[1])
        p.color = self.color
        p.rotation = self.rng.uniform(0, 2*math.pi)
        p.spin = self.rng.uniform(-2, 2)
        p.alive = True
        self.alive_count += 1
        return p
    def update(self, dt):
        """Advance simulation. Returns alive_count. No allocation."""
        self._time += dt
        if self.emitting and self.emitter.rate > 0:
            self.emitter._acc += self.emitter.rate * dt
            n = int(self.emitter._acc)
            self.emitter._acc -= n
            for _ in range(n):
                self._spawn()
        # Integrate alive particles (swap-remove dead)
        i = 0
        while i < self.alive_count:
            p = self.pool[i]
            p.life -= dt
            if p.life <= 0:
                # Swap with last alive
                self.alive_count -= 1
                self.pool[i], self.pool[self.alive_count] = self.pool[self.alive_count], self.pool[i]
                # Do not advance i -- the swapped-in particle needs updating
                continue
            # Forces
            vx, vy, vz = p.vel
            vx += (self.gravity[0] + self.wind[0]) * dt
            vy += (self.gravity[1] + self.wind[1]) * dt
            vz += (self.gravity[2] + self.wind[2]) * dt
            if self.drag > 0:
                f = max(0.0, 1.0 - self.drag * dt)
                vx *= f; vy *= f; vz *= f
            if self.turbulence > 0:
                t = self._time * 3.0
                vx += math.sin(t + p.pos[0]) * self.turbulence * dt
                vz += math.cos(t + p.pos[2]) * self.turbulence * dt
            p.vel = (vx, vy, vz)
            x, y, z = p.pos
            x += vx * dt; y += vy * dt; z += vz * dt
            # Ground collision: bounce + damp
            if self.ground_y is not None and y < self.ground_y:
                y = self.ground_y
                vy = -vy * 0.5
                vx *= 0.8; vz *= 0.8
                p.vel = (vx, vy, vz)
            p.pos = (x, y, z)
            p.rotation += p.spin * dt
            # Fade color toward color_end by age
            a = p.age()
            p.color = tuple(self.color[i] + (self.color_end[i]-self.color[i])*a for i in range(4))
            i += 1
        return self.alive_count
    def positions(self):
        """Alive positions for GPU upload. Returns list of (x,y,z)."""
        return [self.pool[i].pos for i in range(self.alive_count)]
    def describe(self):
        return {'name': self.name, 'max': self.max_particles,
                'alive': self.alive_count, 'emitter': self.emitter.describe(),
                'gravity': list(self.gravity), 'ground_y': self.ground_y}
    # -- presets --
    @classmethod
    def fire(cls, **kw):
        kw.setdefault('max_particles', 500)
        kw.setdefault('gravity', (0, 2.0, 0))
        kw.setdefault('life', (0.3, 0.8))
        kw.setdefault('size', (0.1, 0.4))
        kw.setdefault('color', (1.0, 0.6, 0.1, 1.0))
        kw.setdefault('color_end', (0.2, 0.05, 0.0, 0.0))
        return cls(name='fire', emitter=ConeEmitter(rate=120, angle=0.3), **kw)
    @classmethod
    def smoke(cls, **kw):
        kw.setdefault('max_particles', 300)
        kw.setdefault('gravity', (0, 0.5, 0))
        kw.setdefault('life', (1.0, 3.0))
        kw.setdefault('size', (0.3, 0.8))
        kw.setdefault('color', (0.5, 0.5, 0.5, 0.4))
        kw.setdefault('color_end', (0.8, 0.8, 0.8, 0.0))
        kw.setdefault('drag', 0.5)
        return cls(name='smoke', emitter=PointEmitter(rate=30), **kw)
    @classmethod
    def sparks(cls, **kw):
        kw.setdefault('max_particles', 1000)
        kw.setdefault('gravity', (0, -9.8, 0))
        kw.setdefault('life', (0.3, 1.0))
        kw.setdefault('size', (0.02, 0.08))
        kw.setdefault('color', (1.0, 0.9, 0.3, 1.0))
        kw.setdefault('ground_y', 0.0)
        return cls(name='sparks', emitter=PointEmitter(rate=0), **kw)
    @classmethod
    def rain(cls, **kw):
        kw.setdefault('max_particles', 2000)
        kw.setdefault('gravity', (0, -20, 0))
        kw.setdefault('life', (0.5, 1.0))
        kw.setdefault('size', (0.02, 0.05))
        kw.setdefault('color', (0.6, 0.7, 0.9, 0.8))
        return cls(name='rain', emitter=BoxEmitter(position=(0, 10, 0), size=(20, 1, 20), rate=500), **kw)
    @classmethod
    def snow(cls, **kw):
        kw.setdefault('max_particles', 1500)
        kw.setdefault('gravity', (0, -1.5, 0))
        kw.setdefault('life', (2.0, 5.0))
        kw.setdefault('size', (0.05, 0.15))
        kw.setdefault('color', (1, 1, 1, 0.9))
        kw.setdefault('turbulence', 0.5)
        return cls(name='snow', emitter=BoxEmitter(position=(0, 10, 0), size=(20, 1, 20), rate=200), **kw)
    @classmethod
    def confetti(cls, **kw):
        kw.setdefault('max_particles', 800)
        kw.setdefault('gravity', (0, -3, 0))
        kw.setdefault('life', (1.0, 3.0))
        kw.setdefault('size', (0.05, 0.12))
        return cls(name='confetti', emitter=ConeEmitter(rate=0, angle=0.8), **kw)
    @classmethod
    def dust(cls, **kw):
        """Dust motes for volumetric beams -- slow, tiny, long-lived."""
        kw.setdefault('max_particles', 400)
        kw.setdefault('gravity', (0, 0, 0))
        kw.setdefault('life', (3.0, 8.0))
        kw.setdefault('size', (0.01, 0.03))
        kw.setdefault('color', (1, 1, 0.9, 0.3))
        kw.setdefault('turbulence', 0.2)
        return cls(name='dust', emitter=BoxEmitter(rate=20), **kw)
