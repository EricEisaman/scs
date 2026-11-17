"""
scs_serial.py - Web Serial / USB integration for SCS (Integration 5).

Contract: devices are OPTIONAL producers/consumers of TIMESTAMPED
application data -- never dependencies of render().

  * Permission lives in an explicit UI-facing API: requestPort() /
    requestDevice() require transient user activation, so they are
    NEVER called from a deferred init task. Call them from a click.
  * Permission, connection, protocol parsing, and scene updates are
    SEPARATE stages. A parser never touches the scene; the scene
    never touches a port.
  * Bounded queues + explicit overflow: device traffic cannot
    accumulate unlimited pending work.
  * Rendering SAMPLES the latest sensor state; commands are queued
    separately when each command must be delivered.
  * Disconnect / reconnect are lifecycle states, not exceptions.
    Web Serial can enumerate previously authorised ports.
  * Serial and USB are DISTINCT adapters. A USB device that exposes
    a serial port is still two APIs -- they are not interchangeable.
"""

import time
from collections import deque


# Lifecycle states (shared vocabulary for both adapters).
STATE_DISCONNECTED = 'disconnected'
STATE_REQUESTING = 'requesting'   # permission prompt is open
STATE_CONNECTED = 'connected'
STATE_LOST = 'lost'               # disconnected unexpectedly
STATE_RECONNECTING = 'reconnecting'


class TimestampedSample:
    def __init__(self, data, timestamp=None):
        self.data = data
        self.timestamp = timestamp if timestamp is not None else time.time()

    def age(self, now=None):
        return (now if now is not None else time.time()) - self.timestamp


class BoundedQueue:
    """Bounded queue with an explicit overflow policy. Unbounded
    accumulation of device traffic is a bug, not a feature."""

    def __init__(self, max_items=256, overflow='drop_oldest'):
        self.max_items = int(max_items)
        self.overflow = overflow  # 'drop_oldest' | 'drop_newest' | 'error'
        self._q = deque()

    def push(self, item):
        if len(self._q) >= self.max_items:
            if self.overflow == 'drop_oldest':
                self._q.popleft()
            elif self.overflow == 'drop_newest':
                return False
            elif self.overflow == 'error':
                raise OverflowError('BoundedQueue full (%d)' % self.max_items)
        self._q.append(item)
        return True

    def pop(self):
        return self._q.popleft() if self._q else None

    def drain(self):
        out = list(self._q)
        self._q.clear()
        return out

    def latest(self):
        return self._q[-1] if self._q else None

    def __len__(self):
        return len(self._q)


class ProtocolParser:
    """Stage 3: bytes -> TimestampedSample. Pure function of bytes,
    no port, no scene. Subclass and override parse()."""

    def parse(self, chunk):
        """Return a list of TimestampedSample (possibly empty)."""
        return []


class LineParser(ProtocolParser):
    """Newline-delimited text protocol: 'x,y\\n' -> sample."""

    def __init__(self):
        self._buf = ''

    def parse(self, chunk):
        try:
            self._buf += chunk.decode('utf-8', errors='replace') \
                if isinstance(chunk, (bytes, bytearray)) else str(chunk)
        except Exception:
            return []
        out = []
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            line = line.strip()
            if line:
                out.append(TimestampedSample(line))
        return out


class DeviceAdapter:
    """Shared skeleton: lifecycle + bounded queues + sampling.
    Subclasses implement the transport (Serial vs USB)."""

    kind = 'base'

    def __init__(self, parser=None, max_samples=256, max_commands=64):
        self.state = STATE_DISCONNECTED
        self.parser = parser or LineParser()
        self.samples = BoundedQueue(max_samples, 'drop_oldest')
        self.commands = BoundedQueue(max_commands, 'drop_oldest')
        self.on_disconnect = None
        self.on_reconnect = None
        self.error = None
        self._port = None

    # -- permission: UI-facing, user activation required ------------
    def request(self):
        """MUST be called from a user gesture (click). Returns a
        Promise in the browser. Never called from deferred init."""
        raise NotImplementedError

    # -- connection --------------------------------------------------
    def connect(self, port=None):
        raise NotImplementedError

    def disconnect(self):
        self.state = STATE_DISCONNECTED
        self._port = None

    def _on_unexpected_disconnect(self):
        self.state = STATE_LOST
        if self.on_disconnect:
            try:
                self.on_disconnect(self)
            except Exception:
                pass

    # -- data path ---------------------------------------------------
    def _on_bytes(self, chunk):
        """Stage 3 -> stage 4: parse, then queue samples. The scene
        is never touched here."""
        try:
            for sample in self.parser.parse(chunk):
                self.samples.push(sample)
        except Exception:
            pass

    def latest(self):
        """Rendering SAMPLES the latest state: one value, no queue
        drain, no backlog. This is what onStep / redrawAll read."""
        s = self.samples.latest()
        return s.data if s is not None else None

    def latest_sample(self):
        return self.samples.latest()

    def queue_command(self, data):
        """Commands are queued SEPARATELY from samples: every command
        must be delivered, in order. Samples may be dropped; commands
        are not (until the bounded queue overflows by policy)."""
        self.commands.push(TimestampedSample(data))

    def drain_commands(self):
        return self.commands.drain()


class SerialAdapter(DeviceAdapter):
    """Web Serial (navigator.serial). Distinct from USB."""

    kind = 'serial'

    def __init__(self, baud_rate=9600, **kw):
        super().__init__(**kw)
        self.baud_rate = baud_rate

    def request(self):
        """navigator.serial.requestPort() -- user gesture required."""
        self.state = STATE_REQUESTING
        try:
            from browser import window
            return window.navigator.serial.requestPort()
        except Exception as e:
            self.state = STATE_DISCONNECTED
            self.error = str(e)
            raise

    def list_authorized(self):
        """Previously authorised ports, no prompt (getPorts())."""
        try:
            from browser import window
            return window.navigator.serial.getPorts()
        except Exception:
            return []

    def connect(self, port=None):
        self.state = STATE_CONNECTED
        self._port = port
        try:
            if port is not None and hasattr(port, 'open'):
                port.open({'baudRate': self.baud_rate})
        except Exception as e:
            self.state = STATE_DISCONNECTED
            self.error = str(e)
            raise
        return self._port


class USBAdapter(DeviceAdapter):
    """WebUSB (navigator.usb). Distinct from Serial -- even when the
    USB device exposes a serial port, these are different APIs."""

    kind = 'usb'

    def __init__(self, filters=None, **kw):
        super().__init__(**kw)
        self.filters = filters or []

    def request(self, filters=None):
        """navigator.usb.requestDevice() -- user gesture required."""
        self.state = STATE_REQUESTING
        try:
            from browser import window
            return window.navigator.usb.requestDevice(
                {'filters': filters or self.filters})
        except Exception as e:
            self.state = STATE_DISCONNECTED
            self.error = str(e)
            raise

    def list_authorized(self):
        """Previously authorised devices, no prompt (getDevices())."""
        try:
            from browser import window
            return window.navigator.usb.getDevices()
        except Exception:
            return []

    def connect(self, device=None):
        self.state = STATE_CONNECTED
        self._port = device
        try:
            if device is not None and hasattr(device, 'open'):
                device.open()
        except Exception as e:
            self.state = STATE_DISCONNECTED
            self.error = str(e)
            raise
        return self._port
