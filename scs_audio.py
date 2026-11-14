"""
scs_audio.py - Web Audio integration for SCS (Integration 3).

Contract: the AUDIO clock is separate from the RENDER clock.

  * Audio is scheduled against audio time (AudioContext.currentTime),
    never against "when the renderer drew a frame".
  * An application may SUPPLY its AudioContext. Ownership is explicit:
    disposing the renderer never closes an app-owned graph.
  * Clock mapping is explicit: getOutputTimestamp() relates audio
    time to the performance.now() time domain. Visuals that must
    sync to audio use that mapping, not frame count.
  * Custom real-time DSP goes in an AudioWorklet (separate audio
    thread), never in a rendering callback.
  * Autoplay: starting / resuming audio requires a user gesture.
    resume() must be called from a click / key handler; it is not
    called implicitly at renderer construction.
"""

import time


class ClockMapping:
    """performance.now() <-> AudioContext.currentTime mapping.
    Refreshed from getOutputTimestamp() when available; falls back
    to a one-time offset measured at construction."""

    def __init__(self, context=None):
        self.context = context
        self._offset = None  # audio_time - performance_time
        self.refresh()

    def refresh(self):
        try:
            if self.context is not None and hasattr(self.context, 'getOutputTimestamp'):
                ts = self.context.getOutputTimestamp()
                # ts has contextTime + performanceTime (ms).
                perf_s = float(ts.performanceTime) / 1000.0
                self._offset = float(ts.contextTime) - perf_s
                return self._offset
        except Exception:
            pass
        try:
            now_perf = time.time()
            ctx_t = float(self.context.currentTime) if self.context else 0.0
            self._offset = ctx_t - now_perf
        except Exception:
            self._offset = 0.0
        return self._offset

    def audio_to_performance(self, audio_time):
        return (audio_time - (self._offset or 0.0))

    def performance_to_audio(self, perf_time):
        return perf_time + (self._offset or 0.0)

    def now_audio(self):
        try:
            return float(self.context.currentTime)
        except Exception:
            return time.time() + (self._offset or 0.0)


class AudioEvent:
    """A timestamped audio-side event (note, cue, beat). Visuals that
    react to it use its audio timestamp + the ClockMapping, not the
    frame it happened to be observed in."""

    def __init__(self, audio_time, kind, data=None):
        self.audio_time = float(audio_time)
        self.kind = kind
        self.data = data or {}


class AudioEngine:
    """Owns (optionally) an AudioContext and the scheduling API.
    If `context` is supplied, this engine does NOT own it: dispose()
    leaves it open. If omitted, the engine creates one lazily on
    resume() -- never at construction (autoplay policy)."""

    def __init__(self, context=None):
        self.context = context
        self.owns_context = context is None
        self.clock = ClockMapping(context)
        self._worklets = {}
        self._started = False

    # -- lifecycle / autoplay ------------------------------------
    def resume(self):
        """Call from a USER GESTURE (click / key). Returns a Promise
        in the browser, None in tests. This is the explicit path
        autoplay policies require -- no implicit start."""
        if self.context is None:
            try:
                from browser import window
                AC = getattr(window, 'AudioContext', None) or \
                    getattr(window, 'webkitAudioContext', None)
                if AC is not None:
                    self.context = AC.new()
                    self.clock.context = self.context
                    self.clock.refresh()
            except Exception:
                pass
        if self.context is None:
            return None
        try:
            p = self.context.resume()
            self._started = True
            return p
        except Exception:
            self._started = True
            return None

    def suspend(self):
        if self.context is not None and self.owns_context:
            try:
                return self.context.suspend()
            except Exception:
                pass
        return None

    def dispose(self):
        """Disposing the RENDERER / engine never closes an
        application-owned context. Only a context this engine created
        is closed, and only if the app asks for it."""
        if self.context is not None and self.owns_context:
            try:
                self.context.close()
            except Exception:
                pass
        self.context = None
        self._worklets.clear()

    # -- scheduling (audio time, never frame time) ----------------
    def schedule(self, node, at_audio_time, param=None):
        """Schedule `node.start(at_audio_time)`. Callers pass audio
        time (from clock.now_audio() or an AudioEvent)."""
        try:
            node.start(float(at_audio_time))
        except Exception:
            try:
                node.start()
            except Exception:
                pass
        return float(at_audio_time)

    def schedule_at_performance_time(self, node, perf_time):
        """Schedule a node at a performance.now() instant, mapped
        through the clock -- the sync primitive for visuals."""
        return self.schedule(node, self.clock.performance_to_audio(perf_time))

    def schedule_in(self, node, delay_seconds):
        """Schedule `delay_seconds` from now, in audio time."""
        return self.schedule(node, self.clock.now_audio() + float(delay_seconds))

    # -- DSP in a worklet, never in a render callback --------------
    def register_worklet(self, name, module_url):
        """Load an AudioWorklet module. Returns a Promise in the browser.
        DSP runs on the audio thread; rendering callbacks never do DSP."""
        if self.context is None:
            raise RuntimeError('Call resume() (from a user gesture) before registering a worklet.')
        try:
            p = self.context.audioWorklet.addModule(module_url)
            self._worklets[name] = module_url
            return p
        except Exception as e:
            raise RuntimeError('AudioWorklet load failed: %s' % e)

    def create_worklet_node(self, name, **params):
        if self.context is None:
            raise RuntimeError('No AudioContext: call resume() first.')
        try:
            from browser import window
            Node = getattr(window, 'AudioWorkletNode', None)
            if Node is None:
                raise RuntimeError('AudioWorkletNode unavailable')
            return Node.new(self.context, name, params)
        except Exception as e:
            raise RuntimeError('Worklet node creation failed: %s' % e)


# A shared engine for simple SCS Sound use; apps with their own
# context should construct AudioEngine(context=their_context).
_shared_engine = None


def shared_engine():
    global _shared_engine
    if _shared_engine is None:
        _shared_engine = AudioEngine()
    return _shared_engine
