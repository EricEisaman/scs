"""
scs_controller.py - Gamepad / controller integration for SCS (5 decisions).

Contract: gameplay depends on BUTTONS, AXES, and CAPABILITIES -- never
on USB vs Bluetooth transport.

  * The Gamepad API is the NORMAL interface for OS/browser-exposed
    controllers. Pair Bluetooth controllers in SYSTEM SETTINGS, then
    detect whether the browser exposes them. "Connect via Web Bluetooth"
    is NOT the default workflow: Web Bluetooth is BLE peripherals, not
    a universal game-controller interface. Custom BLE support lives in
    a SEPARATE adapter producing the SAME application-level actions.
  * Physical controls != semantic actions: move / look / confirm /
    cancel / grab live in an action layer above raw indices.
  * Sample ONCE per simulation step into a library-owned snapshot.
    Transitions (pressed / held / released) derive from successive
    snapshots. One physical press never fires repeatedly across
    catch-up steps.
  * Discovery, player assignment, and reconnect are SEPARATE
    lifecycle concepts. gamepad.index is NOT permanent identity.
  * Haptics are OPTIONAL, BOUNDED output: feedback(player, kind,
    intensity) with availability detection, coalescing, caps, and
    cancellation -- never a per-frame device-command stream.
"""

import time


# [STRIPPED 70 bytes]
# 2. Physical controls vs semantic actions
# [STRIPPED 70 bytes]

# Standard layout (gamepad.mapping === 'standard') only. Unknown
# mapping (mapping == '') means: NO assumed layout, rebinding required.
STANDARD_MAPPING = 'standard'

# Standard button indices (only valid when mapping == 'standard').
STD_BUTTONS = {
    'confirm': 0,      # bottom face button (A / Cross)
    'cancel': 1,       # right face button (B / Circle)
    'grab': 2,         # left face button (X / Square)
    'alt': 3,          # top face button (Y / Triangle)
    'shoulder_l': 4, 'shoulder_r': 5,
    'trigger_l': 6, 'trigger_r': 7,
    'select': 8, 'start': 9,
    'stick_l': 10, 'stick_r': 11,
    'dpad_up': 12, 'dpad_down': 13, 'dpad_left': 14, 'dpad_right': 15,
}
# Standard axes: 0/1 left stick, 2/3 right stick.
STD_AXES = {'move_x': 0, 'move_y': 1, 'look_x': 2, 'look_y': 3}

# Semantic actions gameplay code uses. Glyphs / physical names live
# in the UI layer, never here: 'confirm' has no manufacturer's label.
ACTIONS = ('move', 'look', 'confirm', 'cancel', 'grab', 'alt',
           'shoulder_l', 'shoulder_r', 'trigger_l', 'trigger_r',
           'select', 'start', 'pause')


class Binding:
    """One action -> physical control mapping. Rebindable at runtime.
    A Binding never assumes a manufacturer's label or position name."""

    def __init__(self, action, kind, index, invert=False,
                 sensitivity=1.0, dead_zone=0.15):
        self.action = action      # semantic action name
        self.kind = kind          # 'button' | 'axis' | 'axis_button'
        self.index = int(index)   # raw button / axis index
        self.invert = bool(invert)
        self.sensitivity = float(sensitivity)
        self.dead_zone = float(dead_zone)

    def describe(self):
        return {'action': self.action, 'kind': self.kind,
                'index': self.index, 'invert': self.invert,
                'sensitivity': self.sensitivity, 'dead_zone': self.dead_zone}


def standard_bindings(dead_zone=0.15):
    """Default bindings for the STANDARD layout only. Callers must
    check mapping == 'standard' before using these."""
    out = []
    for action, idx in STD_BUTTONS.items():
        out.append(Binding(action, 'button', idx, dead_zone=dead_zone))
    out.append(Binding('move', 'axis', STD_AXES['move_x'], dead_zone=dead_zone))
    out.append(Binding('move', 'axis', STD_AXES['move_y'], dead_zone=dead_zone))
    out.append(Binding('look', 'axis', STD_AXES['look_x'], dead_zone=dead_zone))
    out.append(Binding('look', 'axis', STD_AXES['look_y'], dead_zone=dead_zone))
    return out


def apply_dead_zone(value, dead_zone):
    """Dead zone BEFORE action evaluation. Returns 0 inside the zone,
    rescaled to [0, 1] outside it. Smoothing is OPTIONAL and lives
    in the caller, never imposed here."""
    v = float(value)
    dz = float(dead_zone)
    if abs(v) <= dz:
        return 0.0
    # Rescale so the edge of the zone is 0 and full deflection is 1.
    out = (abs(v) - dz) / (1.0 - dz)
    return out if v >= 0 else -out


# [STRIPPED 70 bytes]
# 3. One snapshot per simulation step, stable, reusable buffers
# [STRIPPED 70 bytes]

class ControllerSnapshot:
    """Library-owned snapshot for ONE simulation step. Reused buffers:
    buttons/axes are written in place, no object graph per sample."""

    def __init__(self, max_buttons=32, max_axes=8):
        self.buttons = [0.0] * max_buttons   # analog values 0..1
        self.button_pressed = [False] * max_buttons
        self.axes = [0.0] * max_axes
        self.timestamp = 0.0  # Gamepad.timestamp: diagnostic only, NOT latency
        self.mapping = ''
        self.connected = False
        self.frame = 0

    def copy_from(self, other):
        self.buttons[:] = other.buttons[:len(self.buttons)]
        self.button_pressed[:] = other.button_pressed[:len(self.button_pressed)]
        self.axes[:] = other.axes[:len(self.axes)]
        self.timestamp = other.timestamp
        self.mapping = other.mapping
        self.connected = other.connected


class Controller:
    """One controller: snapshot + transitions + bindings + haptics.

    Transitions derive from SUCCESSIVE snapshots: pressed = now and
    not before, released = before and not now, held = both. A fixed
    step consumes each transition ONCE: after the step reads it, the
    transition is cleared until the next poll."""

    def __init__(self, device_id, player=None, bindings=None):
        self.device_id = device_id  # opaque identity, NOT gamepad.index
        self.player = player         # None = unassigned
        self.bindings = list(bindings) if bindings is not None else []
        self.prev = ControllerSnapshot()
        self.curr = ControllerSnapshot()
        self._transitions_consumed = True
        self._haptics = Haptics()
        self.vibration_enabled = True

    # -- polling (one boundary per step) ------------------------------
    def poll(self, gamepad, frame=0):
        """Sample navigator.getGamepads()[i] ONCE for this step.
        `gamepad` is the raw Gamepad object (or None if disconnected).
        Reuses buffers; derives transitions; marks them unconsumed."""
        prev_pressed = list(self.curr.button_pressed)
        prev_values = list(self.curr.buttons)
        if gamepad is None:
            self.curr.connected = False
            self.curr.button_pressed = [False] * len(self.curr.button_pressed)
            self.curr.buttons = [0.0] * len(self.curr.buttons)
            self.curr.axes = [0.0] * len(self.curr.axes)
        else:
            self.curr.connected = True
            try:
                self.curr.mapping = getattr(gamepad, 'mapping', '') or ''
            except Exception:
                self.curr.mapping = ''
            try:
                self.curr.timestamp = float(getattr(gamepad, 'timestamp', 0.0) or 0.0)
            except Exception:
                self.curr.timestamp = 0.0
            try:
                raw_buttons = list(getattr(gamepad, 'buttons', []) or [])
                for i in range(min(len(raw_buttons), len(self.curr.buttons))):
                    b = raw_buttons[i]
                    try:
                        self.curr.buttons[i] = float(getattr(b, 'value', 0.0))
                        self.curr.button_pressed[i] = bool(getattr(b, 'pressed', False))
                    except Exception:
                        try:
                            self.curr.buttons[i] = float(b)
                            self.curr.button_pressed[i] = float(b) > 0.5
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                raw_axes = list(getattr(gamepad, 'axes', []) or [])
                for i in range(min(len(raw_axes), len(self.curr.axes))):
                    try:
                        self.curr.axes[i] = float(raw_axes[i])
                    except Exception:
                        pass
            except Exception:
                pass
        self.curr.frame = frame
        # Transitions from successive snapshots.
        self._pressed = [c and not p for c, p in
                         zip(self.curr.button_pressed, prev_pressed)]
        self._released = [p and not c for c, p in
                          zip(self.curr.button_pressed, prev_pressed)]
        self._held = [c and p for c, p in
                      zip(self.curr.button_pressed, prev_pressed)]
        self.prev.copy_from(self.curr)
        self._transitions_consumed = False
        return self.curr

    def consume_transitions(self):
        """Mark this step's transitions consumed: a catch-up step
        re-polling the same physical state does NOT re-fire a press.
        Call once per simulation step after gameplay reads input."""
        self._transitions_consumed = True

    # -- semantic actions (Decision 2) --------------------------------
    def _binding_value(self, binding):
        if binding.kind == 'button':
            if 0 <= binding.index < len(self.curr.buttons):
                return self.curr.buttons[binding.index]
            return 0.0
        if binding.kind == 'axis':
            if 0 <= binding.index < len(self.curr.axes):
                v = self.curr.axes[binding.index]
                if binding.invert:
                    v = -v
                return apply_dead_zone(v * binding.sensitivity, binding.dead_zone)
            return 0.0
        return 0.0

    def action_value(self, action):
        """Current value of a semantic action (0..1, or -1..1 for axes).
        Dead zone applied before evaluation; no imposed smoothing."""
        best = 0.0
        for b in self.bindings:
            if b.action != action:
                continue
            v = self._binding_value(b)
            if abs(v) > abs(best):
                best = v
        return best

    def action_pressed(self, action):
        """True if ANY binding for this action transitioned pressed
        in the current step AND transitions have not been consumed."""
        if self._transitions_consumed:
            return False
        for b in self.bindings:
            if b.action != action or b.kind != 'button':
                continue
            if 0 <= b.index < len(self._pressed) and self._pressed[b.index]:
                return True
        return False

    def action_released(self, action):
        if self._transitions_consumed:
            return False
        for b in self.bindings:
            if b.action != action or b.kind != 'button':
                continue
            if 0 <= b.index < len(self._released) and self._released[b.index]:
                return True
        return False

    def action_held(self, action):
        for b in self.bindings:
            if b.action != action or b.kind != 'button':
                continue
            if 0 <= b.index < len(self.curr.button_pressed) and \
                    self.curr.button_pressed[b.index]:
                return True
        return False

    def rebind(self, action, binding):
        """Replace the binding for an action (accessibility / prefs)."""
        self.bindings = [b for b in self.bindings if b.action != action]
        self.bindings.append(binding)

    # -- haptics (Decision 5, via Haptics below) -----------------------
    def feedback(self, kind, intensity=1.0, duration_ms=100):
        return self._haptics.feedback(self, kind, intensity, duration_ms)

    def cancel_feedback(self):
        return self._haptics.cancel(self)


# [STRIPPED 70 bytes]
# 4. Discovery / assignment / reconnect: separate lifecycles
# [STRIPPED 70 bytes]

STATE_WAITING = 'waiting-for-interaction'
STATE_AVAILABLE = 'available'
STATE_ASSIGNED = 'assigned'
STATE_DISCONNECTED = 'disconnected'
STATE_BLOCKED = 'blocked'  # Permissions Policy blocked getGamepads()


class ControllerManager:
    """Owns discovery, player assignment, reconnect policy.

    - gamepad.index is NOT identity: indices are reused after
      disconnect. Identity is an opaque device_id derived from
      gamepad.id + a per-connection counter.
    - 'Press a button to join': a controller connected before page
      load may not fire its connection event until the user interacts
      while the page is focused -- so assignment is by first PRESS,
      not by connection alone.
    - On disconnect, held actions are cleared (no stuck movement).
    - Reconnect policy is explicit: 'restore' (same player) or
      'confirm' (press to re-join). Default: 'confirm'.
    """

    def __init__(self, max_players=4, reconnect_policy='confirm'):
        self.max_players = int(max_players)
        self.reconnect_policy = reconnect_policy
        self.controllers = {}  # device_id -> Controller
        self._index_to_device = {}  # gamepad.index -> device_id
        self._counter = 0
        self._blocked = False
        self.on_assigned = None
        self.on_disconnected = None

    def _new_device_id(self, gamepad):
        self._counter += 1
        try:
            gid = str(getattr(gamepad, 'id', 'gamepad'))
        except Exception:
            gid = 'gamepad'
        return '%s#%d' % (gid, self._counter)

    def poll_all(self, gamepads, frame=0):
        """The ONE input boundary per step: poll getGamepads() once,
        update every controller, assign on first press. `gamepads`
        is the list from navigator.getGamepads()."""
        seen = set()
        for idx, gp in enumerate(gamepads or []):
            if gp is None:
                continue
            device_id = self._index_to_device.get(idx)
            if device_id is None or device_id not in self.controllers:
                device_id = self._new_device_id(gp)
                self._index_to_device[idx] = device_id
                mapping = ''
                try:
                    mapping = getattr(gp, 'mapping', '') or ''
                except Exception:
                    pass
                bindings = standard_bindings() if mapping == STANDARD_MAPPING else []
                self.controllers[device_id] = Controller(
                    device_id, bindings=bindings)
            seen.add(device_id)
            ctrl = self.controllers[device_id]
            ctrl.poll(gp, frame=frame)
            # Assignment by first PRESS, not by connection alone.
            if ctrl.player is None and any(ctrl._pressed):
                self.assign(ctrl)
        # Disconnects: indices that vanished.
        for idx, device_id in list(self._index_to_device.items()):
            if device_id not in seen:
                self._on_disconnect(device_id)
                del self._index_to_device[idx]
        return self.controllers

    def assign(self, controller, player=None):
        """Assign the lowest free player slot, or the requested one."""
        if player is None:
            used = {c.player for c in self.controllers.values()
                    if c.player is not None}
            for p in range(self.max_players):
                if p not in used:
                    player = p
                    break
            if player is None:
                return None
        controller.player = player
        if self.on_assigned is not None:
            try:
                self.on_assigned(controller, player)
            except Exception:
                pass
        return player

    def _on_disconnect(self, device_id):
        ctrl = self.controllers.get(device_id)
        if ctrl is None:
            return
        # Clear held actions: no stuck movement / firing.
        ctrl.curr.button_pressed = [False] * len(ctrl.curr.button_pressed)
        ctrl.curr.buttons = [0.0] * len(ctrl.curr.buttons)
        ctrl.curr.axes = [0.0] * len(ctrl.curr.axes)
        ctrl.curr.connected = False
        ctrl.cancel_feedback()
        old_player = ctrl.player
        if self.reconnect_policy == 'confirm':
            ctrl.player = None  # press to re-join
        # 'restore' keeps ctrl.player; a reconnecting device with the
        # same id reuses it (see poll_all: new device_id, but the app
        # can re-assign by id prefix if it chooses).
        if self.on_disconnected is not None:
            try:
                self.on_disconnected(ctrl, old_player)
            except Exception:
                pass

    def mark_blocked(self):
        """Permissions Policy blocked getGamepads() / connection events
        in an embedded document. Distinct from 'no controller found'."""
        self._blocked = True

    def state(self):
        if self._blocked:
            return STATE_BLOCKED
        if not self.controllers:
            return STATE_WAITING
        if any(c.player is not None for c in self.controllers.values()):
            return STATE_ASSIGNED
        return STATE_AVAILABLE

    def player_controller(self, player):
        for c in self.controllers.values():
            if c.player == player:
                return c
        return None

    def consume_all_transitions(self):
        for c in self.controllers.values():
            c.consume_transitions()


# [STRIPPED 70 bytes]
# 5. Haptics: optional, bounded output
# [STRIPPED 70 bytes]

class Haptics:
    """Application-level feedback: feedback(controller, kind, intensity).
    Gameplay never touches an actuator directly."""

    def __init__(self, max_duration_ms=500, max_intensity=1.0,
                 coalesce_window_ms=50):
        self.max_duration_ms = int(max_duration_ms)
        self.max_intensity = float(max_intensity)
        self.coalesce_window_ms = float(coalesce_window_ms)
        self._last = {}  # device_id -> (kind, time_ms, intensity)

    def _actuator(self, controller):
        """Detect availability. A controller can HAVE vibration
        hardware while the platform/browser does not EXPOSE it --
        physical support alone is insufficient."""
        try:
            gp = getattr(controller, '_raw_gamepad', None)
            if gp is not None:
                vib = getattr(gp, 'vibrationActuator', None)
                if vib is not None:
                    return vib
        except Exception:
            pass
        return None

    def feedback(self, controller, kind, intensity=1.0, duration_ms=100):
        """Bounded: intensity capped, duration capped, repeats
        coalesced. Unsupported effects / rejections never interrupt
        gameplay -- they return False. Respects the user's vibration
        setting (controller.vibration_enabled)."""
        if controller is None or not getattr(controller, 'vibration_enabled', True):
            return False
        intensity = max(0.0, min(float(intensity), self.max_intensity))
        duration = max(0, min(int(duration_ms), self.max_duration_ms))
        if intensity <= 0 or duration <= 0:
            return False
        # Coalesce: same kind within the window -> skip the duplicate.
        now = time.time() * 1000.0
        last = self._last.get(controller.device_id)
        if last is not None and last[0] == kind and \
                (now - last[1]) < self.coalesce_window_ms:
            return False
        self._last[controller.device_id] = (kind, now, intensity)
        actuator = self._actuator(controller)
        if actuator is None:
            # No exposed actuator: non-haptic feedback still applies
            # (the caller shows a visual/audio cue). Not an error.
            return False
        try:
            effect = {'duration': duration, 'weakMagnitude': intensity,
                      'strongMagnitude': intensity}
            res = actuator.playEffect('dual-rumble', effect)
            # playEffect returns a Promise in browsers; a rejection
            # must not interrupt gameplay. Fire-and-forget with a
            # swallowed rejection in real code; here return True.
            return True
        except Exception:
            return False

    def cancel(self, controller):
        """Cancel on pause / disconnect / dispose, where supported."""
        if controller is None:
            return False
        self._last.pop(controller.device_id, None)
        actuator = self._actuator(controller)
        if actuator is None:
            return False
        try:
            actuator.reset()
            return True
        except Exception:
            try:
                actuator.playEffect('dual-rumble', {'duration': 0,
                    'weakMagnitude': 0, 'strongMagnitude': 0})
                return True
            except Exception:
                return False


# [STRIPPED 70 bytes]
# BLE adapter (Decision 1): separate, same actions
# [STRIPPED 70 bytes]

class BLEControllerAdapter:
    """Custom BLE-device support, SEPARATE from the Gamepad path.
    A BLE peripheral produces the SAME ControllerSnapshot / actions
    as a Gamepad controller -- gameplay code cannot tell the difference.
    This is NOT the default workflow: Web Bluetooth is BLE
    peripherals, not a universal game-controller interface."""

    def __init__(self, device_name='BLE Controller'):
        self.device_name = device_name
        self.controller = Controller('ble:' + device_name,
                                     bindings=standard_bindings())
        self.connected = False

    def on_ble_state(self, buttons, axes, frame=0):
        """Feed a BLE notification into the same snapshot pipeline.
        `buttons`: list of (value, pressed); `axes`: list of floats."""
        class _FakeGamepad:
            pass
        gp = _FakeGamepad()
        gp.mapping = STANDARD_MAPPING
        gp.timestamp = time.time() * 1000.0
        gp.buttons = [type('B', (), {'value': v, 'pressed': p})()
                       for (v, p) in buttons]
        gp.axes = list(axes)
        return self.controller.poll(gp, frame=frame)

    def disconnect(self):
        self.connected = False
        self.controller.cancel_feedback()
