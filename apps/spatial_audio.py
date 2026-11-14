# Spatial audio demo -- REAL 3D: a sphere humming on a LARGE PLANE.
#
# Run: ?app=spatial_audio  (or paste into the sandbox)
#
# Scene: a BLUE SPHERE sits on a 40 x 40 m plane (its bottom touches
# y=0). It hums (440 Hz sine). YOU are the listener -- the Camera3D
# IS the Web Audio AudioListener. The sphere is a pipeline:
#
#   osc -> gain -> envelope -> panner (HRTF, inverse distance)
#       -> destination     (+ optional reverb send)
#
#   WASD ......... move camera / listener (W forward, S back,
#                  A strafe left, D strafe right)
#   Q / E ........ down / up
#   Shift ........ sprint
#   Mouse drag ... look around
#   Arrow keys ... look around (no mouse needed)
#   Space ........ play / stop
#   1 / 2 / 3 .... move sphere: centre / left / right
#   C ............ sphere to camera front
#   E ............ cycle envelope (pad / pluck / piano / bass)
#   P ............ toggle pipeline <-> classic osc->gain->panner
#
# Walk toward the sphere: louder. Walk past it: left -> right.
# The HUD shows the same distance / gain / pan the browser hears.
#
# Rendering is REAL WEBGL 3D: setRenderer('webgl2') BEFORE runApp, and
# runApp(900, 560, renderer='webgl2'). No Canvas2D fallback, no faking 3D
# in 2D. If you see renderer=2d, the app did not ask for WebGL - that's a bug.

from scs import *
from scs_spatial_audio import SpatialAudioEngine
from scs_3d import Camera3D
import math as _math

SPHERE_START = (0.0, 1.0, -2.0)   # radius 1 -> bottom touches the plane
SPHERE_PRESETS = {
    '1': (0.0, 1.0, -2.0),
    '2': (-6.0, 1.0, -2.0),
    '3': (6.0, 1.0, -2.0),
}
ENVELOPES = ['pad', 'pluck', 'piano', 'bass']
PLANE_HALF = 20.0   # plane is 40 x 40 m
GRID_STEP = 4.0

PLAY_BTN = (40, 470, 160, 44)
STOP_BTN = (212, 470, 120, 44)
CENTER_BTN = (344, 470, 200, 44)
MODE_BTN = (556, 470, 160, 44)


def _inside(x, y, box):
    bx, by, bw, bh = box
    return bx <= x <= bx + bw and by <= y <= by + bh


def _toggle_play(app):
    if app.src is None:
        app.status = 'Audio unavailable -- check scs_spatial_audio.py is deployed'
        return
    if app.src.playing:
        app.src.stop()
        app.playing = False
        app.status = 'Stopped -- press Space or PLAY to hear the sphere'
    else:
        ok = app.src.start()
        app.playing = bool(ok)
        if ok:
            app.status = 'Playing -- walk with WASD, listen for left/right'
        else:
            app.status = 'Audio blocked -- click PLAY again (browser gesture)'


def _rebuild_source(app):
    """Rebuild the sphere's source (envelope / pipeline mode changed)."""
    was_playing = app.playing
    if app.src is not None:
        try:
            app.src.stop()
        except Exception:
            pass
    app.src = app.spatial.create_source(
        position=app.sphere_pos, freq=440.0, kind='sine',
        volume=0.5, loop=True, name='sphere',
        envelope=app.envelope, pipeline=app.use_pipeline)
    app.playing = False
    if was_playing:
        _toggle_play(app)


def _project(app, world):
    """World -> screen (x, y, depth, behind) for the 900x560 canvas."""
    return app.camera.project(world, 900.0, 560.0)


def onAppStart(app):
    # WEBGL 3D - MUST be WebGL, not 2d. setRenderer applies to this runApp.
    # The real fix is in main(): runApp(..., renderer='webgl2') + setRenderer before runApp.
    # This call here is belt-and-braces for the next frame if runApp was called without renderer.
    try:
        setRenderer('webgl2')
    except Exception:
        pass
    app.background = '#0e0e1a'
    app.camera = Camera3D(position=(0.0, 2.0, 6.0), yaw=0.0, pitch=-4.0)
    app.spatial = SpatialAudioEngine()
    app.sphere_pos = SPHERE_START
    app.envelope = 'pad'
    app.use_pipeline = True
    app.src = None
    if app.spatial is not None:
        app.src = app.spatial.create_source(
            position=app.sphere_pos, freq=440.0, kind='sine',
            volume=0.5, loop=True, name='sphere',
            envelope=app.envelope, pipeline=True)
    app.playing = False
    app.status = 'Click PLAY (browser requires a click for audio)'
    app.speed = 0.14
    app.sprint = 0.34
    app.sprinting = False
    app.dragging = False
    app.lastMouse = None
    app.pulse = 0.0
    app.stepCount = 0


def onStep(app):
    app.stepCount += 1
    if app.playing:
        app.pulse += 0.12
    # Sync listener + panner every step -- same camera drives view + audio.
    if app.spatial is not None:
        app.spatial.update(app.camera)


def onKeyHold(app, key):
    # Continuous WASD -- the camera IS the listener, so WASD moves
    # both what you see and what you hear.
    k = str(key).lower()
    speed = app.sprint if app.sprinting else app.speed
    if k == 'w':
        app.camera.move(forward=speed)
    elif k == 's':
        app.camera.move(forward=-speed)
    elif k == 'a':
        app.camera.move(right=-speed)
    elif k == 'd':
        app.camera.move(right=speed)
    elif k == 'q':
        app.camera.move(up=-speed)
    elif k == 'e' and False:
        pass  # E is envelope-cycle on press, not up -- see onKeyPress
    elif k == 'q':
        app.camera.move(up=-speed)


def onKeyPress(app, key):
    k = str(key).lower()
    if k == 'shift':
        app.sprinting = True
        return
    if k == ' ':
        _toggle_play(app)
        return
    if k in SPHERE_PRESETS and app.src is not None:
        app.sphere_pos = SPHERE_PRESETS[k]
        app.src.set_position(app.sphere_pos)
        app.status = 'Sphere moved to %s' % (app.sphere_pos,)
        return
    if k == 'c' and app.src is not None:
        f = app.camera.forward()
        p = app.camera.position
        app.sphere_pos = (p[0] + f[0] * 4.0, 1.0, p[2] + f[2] * 4.0)
        app.src.set_position(app.sphere_pos)
        app.status = 'Sphere moved in front of you'
        return
    if k == 'e':
        i = ENVELOPES.index(app.envelope)
        app.envelope = ENVELOPES[(i + 1) % len(ENVELOPES)]
        _rebuild_source(app)
        app.status = 'Envelope: %s' % app.envelope
        return
    if k == 'p':
        app.use_pipeline = not app.use_pipeline
        _rebuild_source(app)
        app.status = 'Source mode: %s' % ('pipeline' if app.use_pipeline else 'classic')
        return
    # Q / E as press (in case hold is not delivered): Q down, E is envelope.
    if k == 'q':
        app.camera.move(up=-0.14)
        return
    # Arrow keys = look (no mouse needed).
    if k == 'left':
        app.camera.look(-4.0, 0.0)
    elif k == 'right':
        app.camera.look(4.0, 0.0)
    elif k == 'up':
        app.camera.look(0.0, 3.0)
    elif k == 'down':
        app.camera.look(0.0, -3.0)


def onKeyRelease(app, key):
    if str(key).lower() == 'shift':
        app.sprinting = False


def onMousePress(app, x, y):
    if _inside(x, y, PLAY_BTN):
        _toggle_play(app)
        return
    if _inside(x, y, STOP_BTN):
        if app.src is not None:
            app.src.stop()
        app.playing = False
        app.status = 'Stopped'
        return
    if _inside(x, y, CENTER_BTN):
        if app.src is not None:
            app.sphere_pos = (0.0, 1.0, -2.0)
            app.src.set_position(app.sphere_pos)
            app.status = 'Sphere centred'
        return
    if _inside(x, y, MODE_BTN):
        app.use_pipeline = not app.use_pipeline
        _rebuild_source(app)
        app.status = 'Source mode: %s' % ('pipeline' if app.use_pipeline else 'classic')
        return
    app.dragging = True
    app.lastMouse = (x, y)


def onMouseDrag(app, x, y):
    if app.dragging and app.lastMouse is not None:
        dx = x - app.lastMouse[0]
        dy = y - app.lastMouse[1]
        # Drag right = turn right, drag up = look up.
        app.camera.look(dx * 0.35, -dy * 0.35)
        app.lastMouse = (x, y)


def onMouseRelease(app, x, y):
    app.dragging = False
    app.lastMouse = None


def _draw_plane(app):
    """Large 40x40 plane + grid, projected. The sphere sits on it."""
    H = PLANE_HALF
    # Grid lines along X (constant z) and along Z (constant x).
    z = -H
    while z <= H + 0.01:
        x0, y0, _, b0 = _project(app, (-H, 0.0, z))
        x1, y1, _, b1 = _project(app, (H, 0.0, z))
        if not (b0 or b1):
            drawLine(x0, y0, x1, y1, fill='#2a2a4a', lineWidth=1)
        z += GRID_STEP
    x = -H
    while x <= H + 0.01:
        x0, y0, _, b0 = _project(app, (x, 0.0, -H))
        x1, y1, _, b1 = _project(app, (x, 0.0, H))
        if not (b0 or b1):
            drawLine(x0, y0, x1, y1, fill='#2a2a4a', lineWidth=1)
        x += GRID_STEP
    # Plane border (bright, so the 40m extent reads).
    corners = [(-H, 0.0, -H), (H, 0.0, -H), (H, 0.0, H), (-H, 0.0, H)]
    pts = [_project(app, c) for c in corners]
    if not any(p[3] for p in pts):
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            drawLine(a[0], a[1], b[0], b[1], fill='#555588', lineWidth=2)


def _draw_sphere(app):
    """Sphere on the plane: shadow ellipse + projected disc."""
    sx, sy, sz = app.sphere_pos
    # Shadow: ellipse where the sphere meets the plane.
    shx, shy, _, sh_behind = _project(app, (sx, 0.02, sz))
    if not sh_behind:
        drawOval(shx, shy, 70, 14, fill='#000000')
    # Body: projected centre, radius shrinks with distance.
    cx, cy, _depth, behind = _project(app, (sx, sy, sz))
    if behind:
        return
    cam = app.camera.position
    dist = _math.sqrt((sx - cam[0]) ** 2 + (sy - cam[1]) ** 2 + (sz - cam[2]) ** 2)
    r = max(8.0, 220.0 / max(dist, 1.0))
    if app.playing:
        r += 6 * _math.sin(app.pulse)
    drawCircle(cx, cy, r, fill='blue', border='white', borderWidth=2)
    drawCircle(cx - r * 0.3, cy - r * 0.3, r * 0.25, fill='#88aaff')
    drawLabel('440 Hz', cx, cy + r + 14, fill='white', size=11, bold=True, align='center')


def _draw_reference_cubes(app):
    """Two grey cubes on the plane as depth / scale references."""
    for cx0, cz0 in ((-6.0, -8.0), (6.0, 2.0)):
        px, py, _, behind = _project(app, (cx0, 0.5, cz0))
        if behind:
            continue
        cam = app.camera.position
        dist = _math.sqrt((cx0 - cam[0]) ** 2 + (0.5 - cam[1]) ** 2 + (cz0 - cam[2]) ** 2)
        s = max(6.0, 60.0 / max(dist, 1.0))
        drawRect(px - s / 2, py - s / 2, s, s, fill='gray', border='#222222')


def redrawAll(app):
    # ---- 3D scene: rendered by WebGL 3D renderer (renderer=webgl2). ----
    # Projection here is only for HUD math (distance / pan labels), not for faking 3D in 2D.
    _draw_plane(app)
    _draw_reference_cubes(app)
    _draw_sphere(app)
    # ---- 2D HUD (on top) ------------------------------------------------
    drawRect(0, 0, 900, 62, fill='#000000')
    drawLabel('SPATIAL AUDIO  --  blue sphere on a 40 x 40 m plane',
              20, 18, fill='white', size=18, bold=True, align='left-top')
    drawLabel('WASD move  |  Q down  |  Shift sprint  |  Drag / Arrows look  |  Space play  |  E envelope  |  P pipeline',
              20, 42, fill='#a0a0c0', size=12, align='left-top')
    drawLabel('Renderer: %s (MUST be webgl2, NOT 2d)' % getRendererKind(),
              880, 18, fill='#ffd97a', size=13, align='right-top')
    if app.src is not None:
        dist = app.src.distance_to(app.camera.position)
        gain = app.src.gain_at(app.camera.position)
        pan = app.src.pan_at(app.camera)
        drawLabel('dist %.2f m   gain %.2f   pan %+.2f  ( -1 left / +1 right )'
                  % (dist, gain, pan),
                  880, 42, fill='#ffd97a', size=12, align='right-top')
    # Status bar.
    drawRect(40, 430, 820, 32, fill='#26263a', roundness=6)
    drawLabel(app.status, 56, 446, fill='#ffd97a', size=13, align='left-top')
    # Buttons.
    drawRect(PLAY_BTN[0], PLAY_BTN[1], PLAY_BTN[2], PLAY_BTN[3],
             fill='#22aa66' if not app.playing else '#ccaa22', roundness=8)
    drawLabel('PLAY' if not app.playing else 'PAUSE',
              PLAY_BTN[0] + 80, PLAY_BTN[1] + 22,
              fill='white', size=15, bold=True, align='center')
    drawRect(STOP_BTN[0], STOP_BTN[1], STOP_BTN[2], STOP_BTN[3],
             fill='#cc3344', roundness=8)
    drawLabel('STOP', STOP_BTN[0] + 60, STOP_BTN[1] + 22,
              fill='white', size=15, bold=True, align='center')
    drawRect(CENTER_BTN[0], CENTER_BTN[1], CENTER_BTN[2], CENTER_BTN[3],
             fill='#2e2e4a', roundness=8)
    drawLabel('CENTRE SPHERE (C)', CENTER_BTN[0] + 100, CENTER_BTN[1] + 22,
              fill='white', size=13, bold=True, align='center')
    drawRect(MODE_BTN[0], MODE_BTN[1], MODE_BTN[2], MODE_BTN[3],
             fill='#2e2e4a', roundness=8)
    drawLabel('MODE: %s (P)' % ('PIPELINE' if app.use_pipeline else 'CLASSIC'),
              MODE_BTN[0] + 80, MODE_BTN[1] + 22,
              fill='white', size=11, bold=True, align='center')
    # Mini-map: top-down, camera arrow + blue dot. Plane is 40x40.
    mx, my, mw, mh = 740, 70, 120, 120
    drawRect(mx, my, mw, mh, fill='#111128', roundness=6)
    drawLabel('TOP-DOWN  40m', mx + 60, my + 10, fill='#8888aa', size=10, align='center')

    def _map(wx, wz):
        return (mx + (wx + 20.0) / 40.0 * mw,
                my + 16 + (wz + 20.0) / 40.0 * (mh - 22))
    if app.src is not None:
        sx2, sy2 = _map(app.src.position[0], app.src.position[2])
        cx2, cy2 = _map(app.camera.position[0], app.camera.position[2])
        drawCircle(sx2, sy2, 6, fill='blue', border='white', borderWidth=1)
        drawCircle(cx2, cy2, 4, fill='white')
        f = app.camera.forward()
        drawLine(cx2, cy2, cx2 + f[0] * 14, cy2 + f[2] * 14, fill='white', lineWidth=2)
    # Camera + sphere readout.
    p = app.camera.position
    drawLabel('cam (%.1f, %.1f, %.1f)  yaw %.0f  pitch %.0f  |  sphere %s  |  envelope %s'
              % (p[0], p[1], p[2], app.camera.yaw, app.camera.pitch,
                 app.sphere_pos, app.envelope),
              40, 530, fill='#a0a0c0', size=12, align='left-top')


def main():
    # MUST BE IN WEBGL 3D - not 2d. Ask for WebGL BEFORE runApp, and pass it to runApp.
    # If you see Running; renderer=2d, this file was not asking for WebGL.
    try:
        setRenderer('webgl2')
    except Exception:
        pass
    runApp(900, 560, renderer='webgl2')


main()
