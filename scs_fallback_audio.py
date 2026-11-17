# scs_fallback_audio.py - Shared fallback spatial audio for all SCS apps.
# Self-contained: only uses browser AudioContext, no scs_web_audio import.
# Any app can do: from scs_fallback_audio import SpatialAudioEngine

class _FallbackSpatialSource:
    def __init__(self, engine, position, freq=440.0, kind='sine', volume=0.5, loop=True):
        self.engine = engine
        self.position = tuple(position)
        self.freq = float(freq)
        self.kind = str(kind)
        self.volume = float(volume)
        self.loop = bool(loop)
        self.playing = False
        self._osc = None
        self._gain = None
        self._panner = None

    def _sync_panner(self):
        try:
            if self._panner is not None:
                self._panner.positionX.value = float(self.position[0])
                self._panner.positionY.value = float(self.position[1])
                self._panner.positionZ.value = float(self.position[2])
        except Exception:
            pass

    def start(self):
        try:
            if self.playing:
                return
            ctx = None
            try:
                ctx = self.engine._ctx
            except Exception:
                ctx = None
            if ctx is None:
                from browser import window as _w
                AC = getattr(_w, 'AudioContext', None) or getattr(_w, 'webkitAudioContext', None)
                ctx = AC.new()
                self.engine._ctx = ctx
            try:
                ctx.resume()
            except Exception:
                pass
            self._osc = ctx.createOscillator()
            self._osc.type = self.kind
            self._osc.frequency.value = self.freq
            self._gain = ctx.createGain()
            self._gain.gain.value = self.volume
            try:
                self._panner = ctx.createPanner()
                self._panner.panningModel = 'HRTF'
                self._panner.distanceModel = 'inverse'
            except Exception:
                self._panner = ctx.createStereoPanner()
            self._sync_panner()
            self._osc.connect(self._gain)
            self._gain.connect(self._panner)
            self._panner.connect(ctx.destination)
            self._osc.start()
            self.playing = True
        except Exception:
            pass

    def stop(self):
        try:
            if self._osc is not None:
                self._osc.stop()
        except Exception:
            pass
        try:
            if self._osc is not None:
                self._osc.disconnect()
        except Exception:
            pass
        try:
            if self._gain is not None:
                self._gain.disconnect()
        except Exception:
            pass
        try:
            if self._panner is not None:
                self._panner.disconnect()
        except Exception:
            pass
        self._osc = None
        self._gain = None
        self._panner = None
        self.playing = False

    def set_position(self, pos):
        self.position = tuple(pos)
        self._sync_panner()

    def distance_to(self, cam_pos):
        try:
            dx = float(self.position[0]) - float(cam_pos[0])
            dy = float(self.position[1]) - float(cam_pos[1])
            dz = float(self.position[2]) - float(cam_pos[2])
            return (dx * dx + dy * dy + dz * dz) ** 0.5
        except Exception:
            return 0.0

    def gain_at(self, cam_pos):
        try:
            d = self.distance_to(cam_pos)
            return 1.0 / (1.0 + d * 0.3)
        except Exception:
            return 0.5

    def pan_at(self, camera):
        try:
            r = camera.right()
            dx = float(self.position[0]) - float(camera.position[0])
            dz = float(self.position[2]) - float(camera.position[2])
            pan = dx * float(r[0]) + dz * float(r[2])
            if pan > 1.0:
                pan = 1.0
            if pan < -1.0:
                pan = -1.0
            return pan
        except Exception:
            return 0.0

class _FallbackSpatialEngine:
    def __init__(self, context=None):
        self._ctx = context
        self._sources = []

    def _ensure_ctx(self):
        if self._ctx is not None:
            return self._ctx
        try:
            from browser import window as _w
            AC = getattr(_w, 'AudioContext', None) or getattr(_w, 'webkitAudioContext', None)
            self._ctx = AC.new()
        except Exception:
            self._ctx = None
        return self._ctx

    def create_source(self, position=(0.0, 1.5, 0.0), freq=440.0, kind='sine', volume=0.5, loop=True, name=None, envelope=None, pipeline=None):
        src = _FallbackSpatialSource(self, position, freq=freq, kind=kind, volume=volume, loop=loop)
        self._sources.append(src)
        return src

    def create_spatial_source(self, position=(0.0, 1.5, 0.0), freq=440.0, kind='sine', volume=0.5, loop=True, name=None, envelope=None, pipeline=None):
        return self.create_source(position, freq=freq, kind=kind, volume=volume, loop=loop, name=name, envelope=envelope, pipeline=pipeline)

    def resume(self):
        try:
            ctx = self._ensure_ctx()
            if ctx is not None:
                ctx.resume()
        except Exception:
            pass

    def update(self, camera):
        try:
            ctx = self._ctx
            if ctx is None:
                return
            try:
                listener = ctx.listener
                if listener is not None:
                    listener.positionX.value = float(camera.position[0])
                    listener.positionY.value = float(camera.position[1])
                    listener.positionZ.value = float(camera.position[2])
                    f = camera.forward()
                    listener.forwardX.value = float(f[0])
                    listener.forwardY.value = float(f[1])
                    listener.forwardZ.value = float(f[2])
                    listener.upX.value = 0.0
                    listener.upY.value = 1.0
                    listener.upZ.value = 0.0
            except Exception:
                pass
            for src in self._sources:
                src._sync_panner()
        except Exception:
            pass

SpatialAudioEngine = _FallbackSpatialEngine
