# SCS Controller Integration — the 5 decisions

Gameplay depends on **buttons, axes, and capabilities** — never on
USB vs Bluetooth transport.

## Decision map

| # | Decision | SCS answer | Where |
|---|----------|------------|-------|
| 1 | Abstract the controller, not the transport | Gamepad API is the normal path; pair Bluetooth in **system settings**, then detect browser exposure; Web Bluetooth is **not** the default workflow (BLE peripherals ≠ game-controller interface); custom BLE lives in `BLEControllerAdapter` producing the **same** actions | `scs_controller.ControllerManager`, `BLEControllerAdapter` |
| 2 | Physical ≠ semantic | Action layer: `move / look / confirm / cancel / grab / …`; standard layout used **only** when `mapping === 'standard'`; unknown mapping (`''`) → no assumed layout, rebinding required; rebinding, stick inversion, sensitivity, dead zones; dead zone **before** action evaluation; smoothing optional, never imposed; glyphs / physical names kept in UI, never in actions | `scs_controller.Binding`, `standard_bindings`, `apply_dead_zone`, `Controller.rebind` |
| 3 | One snapshot per step | Poll `getGamepads()` **once** per simulation step at one input boundary; convert to library-owned `ControllerSnapshot` (reused buffers, no per-sample object graph); `pressed / held / released` derived from successive snapshots; `consume_transitions()` so one press never re-fires across catch-up steps; `Gamepad.timestamp` is diagnostic, **not** Bluetooth latency | `Controller.poll`, `ControllerSnapshot`, `ControllerManager.poll_all` |
| 4 | Discovery / assignment / reconnect separate | States: `waiting-for-interaction / available / assigned / disconnected / blocked`; "press a button to join" (a pre-load connection may not fire its event until interaction); `gamepad.index` is **not** identity (indices reused) — opaque `device_id`; on disconnect, held actions cleared (no stuck movement); reconnect policy explicit: `restore` vs `confirm` (default); Permissions Policy blocking reported as `blocked`, not "no controller found" | `ControllerManager`, `STATE_*` |
| 5 | Haptics optional, bounded | `feedback(controller, kind, intensity)` — gameplay never touches an actuator; availability detected; unsupported / rejected → `False`, gameplay continues; intensity + duration capped; repeats coalesced; `cancel()` on pause / disconnect / dispose; user vibration setting respected; non-haptic feedback preserved | `scs_controller.Haptics`, `Controller.feedback` |

## The input boundary

```
per simulation step (ONCE, not per camera / XR view):
  gamepads = navigator.getGamepads()   # one poll
  manager.poll_all(gamepads, frame)    # snapshots + transitions + assignment
  gameplay reads actions via manager.player_controller(0).action_*
  manager.consume_all_transitions()   # one press = one fire, even in catch-up
```

Rendering multiple cameras or XR views reuses the same snapshot —
no duplicate polling.

## Bluetooth, honestly

- A Bluetooth controller paired in system settings may or may not be
  exposed by a given browser/OS. SCS **detects** exposure; it cannot
  **guarantee** it. Verify per controller / OS / browser.
- Wireless operation may not preserve every capability of a wired
  path (e.g. haptics exposed over USB but not over Bluetooth).
  `Haptics.feedback()` returning `False` is a normal outcome, not
  an error.
- Web Bluetooth (`navigator.bluetooth`) accesses BLE peripherals.
  It is not a gamepad API. Use it only for a custom BLE peripheral,
  via `BLEControllerAdapter`, which feeds the same snapshot pipeline.

## What gameplay code never does

- Never reads `gamepad.buttons[0]` directly — use `action_pressed('confirm')`.
- Never uses `gamepad.index` as identity — use `controller.device_id`.
- Never assumes a layout when `mapping == ''` — require rebinding.
- Never calls `vibrationActuator.playEffect()` directly — use `feedback()`.
- Never treats `Gamepad.timestamp` as transport latency.
