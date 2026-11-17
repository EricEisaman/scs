# Controller demo -- actions, not buttons; one snapshot per step.
#
# Run: ?app=controller_demo
# Connect a controller, then PRESS A BUTTON to join (a controller
# connected before page load may not fire its connection event until
# you interact with it while the page is focused -- assignment is by
# first PRESS, not by connection alone).
#
# Gameplay reads semantic actions, never raw indices:
#   confirm = action_pressed('confirm')   # not buttons[0]
#   move    = action_value('move')        # dead zone already applied
# Haptics go through feedback(): feedback(ctrl, 'impact', 0.8).
# Disconnect clears held actions -- movement cannot stay stuck.

player_x = 200
player_y = 200


def onAppStart(app):
    app.background = 'black'
    Label('Controller demo -- press a button to join',
          20, 20, size=16, fill='white', align='left-top')
    Label('confirm = jump  |  move stick = move  |  grab = haptic pulse',
          20, 50, size=14, fill='lightgray', align='left-top')
    Label('Gamepad API is the normal path. Pair Bluetooth in',
          20, 75, size=14, fill='lightgray', align='left-top')
    Label('system settings; Web Bluetooth is NOT the default workflow.',
          20, 100, size=14, fill='lightgray', align='left-top')
    Circle(200, 300, 30, fill='gold')


def onStep(app):
    global player_x, player_y
    # ONE poll per step, at the input boundary:
    mgr = getControllerManager()
    mgr.poll_all(getGamepads())
    ctrl = mgr.player_controller(0)
    if ctrl is None:
        mgr.consume_all_transitions()
        return
    # Semantic actions, dead zone already applied:
    mx = ctrl.action_value('move')  # left stick X (via bindings)
    # Move with the stick; confirm jumps; grab pulses haptics.
    player_x += mx * 4
    if ctrl.action_pressed('confirm'):
        player_y -= 40
    if ctrl.action_pressed('grab'):
        ctrl.feedback('impact', 0.8, 120)
    mgr.consume_all_transitions()  # one press = one fire, even in catch-up


def getGamepads():
    # In the browser: list(window.navigator.getGamepads())
    # Kept as a helper so the demo reads the same in tests.
    try:
        from browser import window
        return list(window.navigator.getGamepads())
    except Exception:
        return []
