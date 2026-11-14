"""
scs_media.py - Web media integration for SCS (Integration 4).

Contract: a MEDIA SOURCE is not a permanent texture.

  * A media-source adapter acquires the CURRENT usable media resource
    at rendering time -- video frames change every frame, a static
    image loader is the wrong path.
  * WebGPU: importExternalTexture() accepts HTMLVideoElement /
    VideoFrame. WebGL: texImage2D from the element / frame.
  * VideoFrame ownership is explicit: borrowed frames are closed by
    the adapter, owned frames by the caller. Nobody closes twice.
  * Buffering policy is explicit: 'latest' (interactive camera:
    drop old, show newest) vs 'queue_all' (offline: deliver every
    frame) vs 'drop_oldest' / 'drop_newest' queue behaviour.
  * Timestamps + colour-conversion policy travel with the adapter,
    so sync and colour are not guessed per material.
  * An imported external texture is VALID FOR ONE FRAME ONLY. It is
    never put into an indefinitely reusable material-resource cache.
    Re-import every frame; cache the ADAPTER, not the texture.
"""

import time
from collections import deque


BUFFER_LATEST = 'latest'        # keep newest, drop everything older
BUFFER_QUEUE_ALL = 'queue_all'  # deliver every frame, bounded queue
BUFFER_DROP_OLDEST = 'drop_oldest'
BUFFER_DROP_NEWEST = 'drop_newest'


class MediaFrame:
    """One acquired media frame: the resource + its timestamp +
    who owns it. `valid_for_frame` is the render-frame id it was
    acquired for; an external texture from an older frame is stale."""

    def __init__(self, resource, timestamp=None, owned=False, frame_id=None,
                 color_space='srgb'):
        self.resource = resource  # VideoFrame / HTMLVideoElement
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.owned = owned  # True: caller must close(); False: adapter closes
        self.frame_id = frame_id
        self.color_space = color_space
        self.closed = False

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if hasattr(self.resource, 'close'):
                self.resource.close()
        except Exception:
            pass

    def is_valid_for(self, frame_id):
        """External textures are one-frame-valid. Anything older is stale."""
        return self.frame_id == frame_id and not self.closed


class MediaSourceAdapter:
    """Base adapter: acquire the current frame, honour the buffering
    policy, track timestamps + colour policy. Subclasses provide the
    source (element / VideoFrame producer / camera)."""

    def __init__(self, source=None, buffering=BUFFER_LATEST,
                 max_queue=4, color_space='srgb',
                 color_conversion='bt709'):
        self.source = source
        self.buffering = buffering
        self.max_queue = int(max_queue)
        self.color_space = color_space
        self.color_conversion = color_conversion  # 'bt709' | 'bt601' | 'srgb'
        self._queue = deque(maxlen=self.max_queue if buffering != BUFFER_QUEUE_ALL else self.max_queue)
        self._frame_id = 0
        self._last_frame = None

    # -- acquisition (called at rendering time) -------------------
    def acquire(self, frame_id=None):
        """Return the CURRENT usable MediaFrame for this render frame.
        'latest' drops everything but the newest; 'queue_all' delivers
        in order. The returned frame is valid for THIS frame only."""
        if frame_id is None:
            self._frame_id += 1
            frame_id = self._frame_id
        frame = self._produce(frame_id)
        if frame is None:
            return self._last_frame  # no new frame: reuse last, don't stall
        if self.buffering == BUFFER_LATEST:
            # Drop everything older: interactive camera must not lag.
            if self._last_frame is not None and not self._last_frame.owned:
                self._last_frame.close()
            self._last_frame = frame
            return frame
        # Queue policies: bounded, explicit overflow.
        if len(self._queue) >= self.max_queue:
            if self.buffering == BUFFER_DROP_OLDEST:
                old = self._queue.popleft()
                if not old.owned:
                    old.close()
            elif self.buffering == BUFFER_DROP_NEWEST:
                if not frame.owned:
                    frame.close()
                return self._queue[-1] if self._queue else None
        self._queue.append(frame)
        self._last_frame = frame
        return frame

    def _produce(self, frame_id):
        """Subclass hook: produce ONE new MediaFrame, or None."""
        if self.source is None:
            return None
        ts = None
        try:
            ts = getattr(self.source, 'currentTime', None)
        except Exception:
            pass
        return MediaFrame(self.source, timestamp=ts, owned=False,
                          frame_id=frame_id, color_space=self.color_space)

    def drain(self):
        """Offline path: take every queued frame in order."""
        out = list(self._queue)
        self._queue.clear()
        return out

    # -- backend import (never cached across frames) ---------------
    def import_for_webgpu(self, device, frame):
        """WebGPU: importExternalTexture(). The result is valid for
        THIS frame only -- callers must NOT put it in a texture cache."""
        if frame is None or frame.closed:
            raise RuntimeError('Cannot import a closed / missing media frame.')
        try:
            tex = device.importExternalTexture({'source': frame.resource})
        except Exception as e:
            raise RuntimeError('importExternalTexture failed: %s' % e)
        return {'texture': tex, 'frame_id': frame.frame_id,
                'timestamp': frame.timestamp,
                'color_space': frame.color_space,
                'valid_for_frame_only': True}

    def upload_for_webgl(self, gl, texture, frame):
        """WebGL: texImage2D from the current element / frame."""
        if frame is None or frame.closed:
            raise RuntimeError('Cannot upload a closed / missing media frame.')
        try:
            gl.bindTexture(gl.TEXTURE_2D, texture)
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA,
                           gl.UNSIGNED_BYTE, frame.resource)
        except Exception as e:
            raise RuntimeError('WebGL video upload failed: %s' % e)
        return {'frame_id': frame.frame_id, 'timestamp': frame.timestamp}

    def describe(self):
        return {
            'buffering': self.buffering, 'max_queue': self.max_queue,
            'color_space': self.color_space,
            'color_conversion': self.color_conversion,
            'queued': len(self._queue),
        }


class VideoElementAdapter(MediaSourceAdapter):
    """Adapter for an <video> element (borrowed resource: the element
    owns the frames, the adapter never closes them)."""

    def __init__(self, video_element, **kw):
        super().__init__(source=video_element, **kw)


class VideoFrameAdapter(MediaSourceAdapter):
    """Adapter for a VideoFrame producer (e.g. WebCodecs).
    Frames arrive via push(frame, owned=...): owned=True means the
    CALLER transfers ownership to the adapter (adapter closes);
    owned=False means the caller retains it (adapter never closes)."""

    def __init__(self, **kw):
        super().__init__(source=None, **kw)
        self._pending = deque()

    def push(self, video_frame, owned=True, timestamp=None):
        self._frame_id += 1
        self._pending.append(MediaFrame(
            video_frame, timestamp=timestamp, owned=owned,
            frame_id=self._frame_id, color_space=self.color_space))
        if len(self._pending) > self.max_queue:
            old = self._pending.popleft()
            if old.owned:
                old.close()

    def _produce(self, frame_id):
        if not self._pending:
            return None
        f = self._pending.popleft()
        f.frame_id = frame_id
        return f


class CameraAdapter(VideoElementAdapter):
    """Camera: interactive, so the default policy is 'latest' --
    a camera effect must show the newest frame, never a queue
    of stale ones."""
    def __init__(self, video_element, **kw):
        kw.setdefault('buffering', BUFFER_LATEST)
        kw.setdefault('max_queue', 1)
        super().__init__(video_element, **kw)
