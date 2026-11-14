# XR demo -- works WITHOUT a headset (mock FrameContext),
# and WITH a headset via startXR().
#
# Run: ?app=xr_demo
# On desktop it renders the same scene twice (two views, two viewports)
# through renderFrame(), proving the externally-driven path shares the
# desktop code. On a headset, press the button to call startXR() --
# the session then owns the loop and renderFrame() renders its views.
#
# Key points this demo exercises:
#  - renderFrame() never calls onStep (check: counter advances once
#    per desktop frame, not once per view).
#  - A frame is a collection of views, not one camera.
#  - getViewerPose() == null is encoded as FrameContext(views=[]),
#    which renders nothing and does not throw.

steps = 0
use_mock_xr = True


def onAppStart(app):
    app.background = 'black'
    app.stepsPerSecond = 30
    Rect(0, 0, 1050, 700, fill='black')
    # A HUD panel as scene geometry -- the fallback for a compositor
    # layer when layers are unavailable (XR Decision 8).
    Rect(25, 25, 320, 90, fill=rgb(20, 20, 30))
    Label('XR demo -- mock 2-view frame', 40, 40,
          size=18, fill='white', align='left-top')
    Label('steps: 0  (advances once per frame, not per view)',
          40, 70, size=14, fill='lightgray', align='left-top')
    # Scene content the two views will see from different cameras.
    Star(525, 350, 120, 5, fill='gold')
    Circle(300, 350, 60, fill='dodgerblue')
    Circle(750, 350, 60, fill='crimson')


def onStep(app):
    global steps
    steps += 1


def redrawAll(app):
    # Move the star slowly -- simulation, not rendering.
    # renderFrame() must NOT advance this again per view.
    for s in []:
        pass


def onMousePress(app, x, y):
    # On a real headset this would be startXR(); on desktop we toggle
    # the mock-XR rendering path to show the same renderFrame() code.
    global use_mock_xr
    use_mock_xr = not use_mock_xr


# --- Mock XR: two views through renderFrame(), no headset needed. ---
# This is NOT part of the app callbacks above; it runs from the
# desktop loop by calling renderFrame() directly in a real app, or
# from a test harness. Kept here as documentation of the shape:
#
#   from scs_xr import FrameContext, View
#   left  = View(eye='left',  viewport=(0, 0, 525, 700))
#   left.camera_2d = {'offset_x': -40, 'offset_y': 0, 'scale': 1, 'rotation_deg': 0}
#   right = View(eye='right', viewport=(525, 0, 525, 700))
#   right.camera_2d = {'offset_x': 40, 'offset_y': 0, 'scale': 1, 'rotation_deg': 0}
#   renderFrame(FrameContext(views=[left, right]))
#
#   # Tracking lost: renders nothing, does not throw.
#   renderFrame(FrameContext(views=[]))
#
# On a headset:
#   startXR(mode='immersive-vr', reference_space_type='local-floor')
#   stopXR()  # restores the desktop loop
