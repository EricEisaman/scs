# Spatial audio - PATINA COPPER sphere humming on a big plane. NOT blue.
# The GOLD sphere is the SOUND SOURCE (440 Hz). Red/Yellow/Green balls are decoys (no sound).
# Target: patina copper, defect 0.80, corrosion 1.0, roughness 0.28, metalness 1.0.
# Light is a CLOUDY SKY (see scs_engine_webgl2.py cloudySky) - overcast, not gradient + softboxes.
# For kids learning on CMU CS Academy: this is plain CMU Graphics.
# All flat shapes use the cmu_graphics API. The ONLY extra thing is centerZ at the END.
# NO Canvas2D fallback. World shapes are REAL 3D (centerZ set), drawn by WebGL2 / WebGPU.
# We do NOT project them to shaded 2D circles. If the renderer is 2D, a world shape FAILS LOUD.
#   No centerZ  -> HUD overlay, on top, like a game HUD
#   centerZ set -> in the 3D world, with depth. centerZ=0 still counts as 3D.
# Nothing else is new. No renderer words, no engine words.
#
# Walk toward the sphere: louder. Walk past it: left -> right.
#   WASD move, Q down, Shift sprint, drag / arrows look
#   Space play, 1 / 2 / 3 move sphere, C centre, E envelope, P pipeline

from scs import *
from scs_spatial_audio import SpatialAudioEngine
from scs_3d import Camera3D
import math as _math

# --- Version logs: logs don't lie ---
APP_VERSION = '2026-11-14-spatial-audio-v3-3d-patinas'

def _log_versions(where):
    _ep_ver = 'unknown'
    try:
        import scs_entrypoint as _ep
        _ep_ver = getattr(_ep, '__version__', 'unknown')
    except Exception as _e_ep:
        _ep_ver = 'import-failed:%r' % (_e_ep,)
    _kind = 'unknown'
    _cap = {}
    _stats = {}
    try:
        _kind = getRendererKind()
    except Exception as _e_k:
        _kind = 'getRendererKind-failed:%r' % (_e_k,)
    try:
        _cap = getCapability()
    except Exception:
        _cap = {}
    try:
        _stats = getStats()
    except Exception:
        _stats = {}
    _msg = '[SCS versions] where=%s entrypoint=%s renderer_version=0.1 renderer_kind=%s renderer_cap=%s renderer_stats=%s app=%s' % (where, _ep_ver, _kind, _cap, _stats, APP_VERSION)
    # v33: log ONCE. print() already lands in DevTools in Brython, so
    # print + console.log duplicated every line (looked like double-run).
    try:
        from browser import window as _w
        if _w is not None and hasattr(_w, 'console'):
            _w.console.log(_msg)
        else:
            print(_msg)
    except Exception:
        try:
            print(_msg)
        except Exception:
            pass

_log_versions('import')

SPHERE_START = (0.0, 1.0, -2.0)
SPHERE_PRESETS = {
    '1': (0.0, 1.0, -2.0),
    '2': (-6.0, 1.0, -2.0),
    '3': (6.0, 1.0, -2.0),
}
ENVELOPES = ['pad', 'pluck', 'piano', 'bass']
PLANE_HALF = 20.0
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
        app.status = 'Audio unavailable'
        return
    if app.src.playing:
        app.src.stop()
        app.playing = False
        app.status = 'Stopped - press Space or PLAY to hear the sphere'
    else:
        ok = app.src.start()
        app.playing = bool(ok)
        if ok:
            app.status = 'Playing - walk with WASD, listen for left/right'
        else:
            app.status = 'Audio blocked - click PLAY again'


def _rebuild_source(app):
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


# NO Canvas2D fallback. All browsers have WebGL.
# World shapes use WORLD coords directly (centerX = world X, centerY = world Y,
# centerZ = world Z). The WebGL2 / WebGPU shader does the projection.
# _project is ONLY for math / tests, never for drawing shaded 2D circles.
def _project(app, world):
    return app.camera.project(world, 900.0, 560.0)


def onAppStart(app):
    _log_versions('onAppStart')
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
    app.status = 'Click PLAY (browser needs a click for audio)'
    app.speed = 0.14
    app.sprint = 0.34
    app.sprinting = False
    app.dragging = False
    app.lastMouse = None
    app.pulse = 0.0
    app.stepCount = 0
    app.balls = [
        {'x': -6.0, 'z': -3.0, 'r': 0.60, 'y': 3.0, 'vy': 0.0, 'color': '#B87333', 'defect': 0.72, 'corrosion': 0.0, 'name': 'Copper'},
        {'x': 0.0, 'z': 4.0, 'r': 0.50, 'y': 4.5, 'vy': 0.0, 'color': '#C9A227', 'defect': 0.68, 'corrosion': 0.0, 'name': 'Brass'},
        {'x': 6.0, 'z': -3.0, 'r': 0.70, 'y': 2.2, 'vy': 0.0, 'color': '#B87333', 'defect': 0.82, 'corrosion': 1.0, 'name': 'Copper-Patina'},
    ]
    # ---- HUD shapes: flat, overlay ----
    app.hudTop = Rect(0, 0, 900, 62, fill='black', align='left-top')
    app.hudTitle = Label('SPATIAL AUDIO -- GOLD sphere = sound source (440 Hz) on a 40 x 40 m plane',
                         20, 18, fill='#FFD700', size=18, bold=True,
                         align='left-top')
    app.hudHelp = Label('WASD move | Q down | Shift sprint | Drag / Arrows look | Space play | E envelope | P pipeline',
                        20, 42, fill='#a0a0c0', size=12, align='left-top')
    app.hudDist = Label('', 880, 42, fill='#ffd97a', size=12,
                        align='right-top')
    app.hudSourceLegend = Label('GOLD = SOUND SOURCE  |  Red/Yellow/Green = bouncing decoys (no sound)', 20, 64, fill='#FFD700', size=12, bold=True, align='left-top')
    app.statusBar = Rect(40, 430, 820, 32, fill='#26263a', roundness=6,
                         align='left-top')
    app.statusLabel = Label(app.status, 56, 446, fill='#ffd97a', size=13,
                            align='left-top')
    app.playBtn = Rect(PLAY_BTN[0], PLAY_BTN[1], PLAY_BTN[2], PLAY_BTN[3],
                       fill='#22aa66', roundness=8, align='left-top')
    app.playLabel = Label('PLAY', PLAY_BTN[0] + 80, PLAY_BTN[1] + 22,
                          fill='white', size=15, bold=True, align='center')
    app.stopBtn = Rect(STOP_BTN[0], STOP_BTN[1], STOP_BTN[2], STOP_BTN[3],
                       fill='#cc3344', roundness=8, align='left-top')
    app.stopLabel = Label('STOP', STOP_BTN[0] + 60, STOP_BTN[1] + 22,
                          fill='white', size=15, bold=True, align='center')
    app.centerBtn = Rect(CENTER_BTN[0], CENTER_BTN[1], CENTER_BTN[2], CENTER_BTN[3],
                         fill='#2e2e4a', roundness=8, align='left-top')
    app.centerLabel = Label('CENTRE SPHERE (C)', CENTER_BTN[0] + 100, CENTER_BTN[1] + 22,
                            fill='white', size=13, bold=True, align='center')
    app.modeBtn = Rect(MODE_BTN[0], MODE_BTN[1], MODE_BTN[2], MODE_BTN[3],
                       fill='#2e2e4a', roundness=8, align='left-top')
    app.modeLabel = Label('MODE: PIPELINE (P)', MODE_BTN[0] + 80, MODE_BTN[1] + 22,
                          fill='white', size=11, bold=True, align='center')
    app.miniMap = Rect(740, 70, 120, 120, fill='#111128', roundness=6,
                       align='left-top')
    app.miniMapTitle = Label('TOP-DOWN  40m', 800, 80, fill='#8888aa', size=10,
                             align='center')
    app.miniSphere = Circle(800, 120, 6, fill='#FFD700', border='white', borderWidth=1)  # GOLD = sound source, not blue
    app.miniCam = Circle(800, 120, 4, fill='white')
    app.miniArrow = Line(800, 120, 800, 106, fill='white', lineWidth=2)
    app.readout = Label('', 40, 530, fill='#a0a0c0', size=12,
                        align='left-top')
    # ---- World shapes: in the 3D world ----
    # World: centerZ set = 3D. HUD above has NO centerZ = HUD. That is the whole rule.
    app.sphereShadow = Oval(450, 280, 70, 14, fill='black', centerZ=0.02)
    # TARGET: patina copper, not flat blue/gold. Cloudy sky is the light (see CLOUDY engine).
    app.sphere = Circle(0, 1, 1.2, fill='#B87333', border='white', borderWidth=3, centerZ=-2.0)
    app.sphere.defectLevel = 0.80
    app.sphere.corrosionEnabled = 1.0
    app.sphere.metalness = 1.0
    app.sphere.roughness = 0.28
    app.sphereHighlight = Circle(435, 265, 12, fill='#88aaff', centerZ=-2.0)
    app.sphereLabel = Label('SOUND SOURCE - 440 Hz - DAMAGED COPPER', 450, 340, fill='#FFD700', size=11, bold=True,
                            align='center', centerZ=-2.0)
    app.ballBodies = []
    app.ballHighlights = []
    for b in app.balls:
        app.ballBodies.append(Oval(0, 1, b['r']*2, b['r']*2, fill=b['color'],
                                    border='white', borderWidth=1, centerZ=b['z']))
        app.ballHighlights.append(Circle(435, 265, 10, fill='white', centerZ=b['z']))
        app.ballBodies[-1].defectLevel = b.get('defect', 0.55)
        app.ballBodies[-1].corrosionEnabled = b.get('corrosion', 0.0)
        app.ballBodies[-1].metalness = 1.0
        app.ballBodies[-1].roughness = 0.32
    app.cubeShapes = []
    for _cz in (-8.0, 2.0):
        app.cubeShapes.append(Rect(450, 280, 40, 40, fill='#8a8f98',
                                   border='#222222', align='left-top', centerZ=_cz))
    for _c in app.cubeShapes:
        _c.defectLevel = 0.50
        _c.corrosionEnabled = 0.0
        _c.metalness = 1.0
        _c.roughness = 0.38
    app.planeLines = []
    for _ in range(26):
        app.planeLines.append(Line(0, 0, 0, 0, fill='#2a2a4a', lineWidth=1, centerZ=0.0))


def onStep(app):
    app.stepCount += 1
    if app.stepCount == 1:
        _log_versions('onStep-first-frame')
    if app.stepCount == 60:
        _log_versions('onStep-frame-60')
    if app.playing:
        app.pulse += 0.12
    for b in app.balls:
        b['vy'] -= 0.022
        b['y'] += b['vy']
        if b['y'] < b['r']:
            b['y'] = b['r']
            b['vy'] = -b['vy'] * 0.88
            if abs(b['vy']) < 0.08:
                b['vy'] = 0.28 + 0.12 * abs(b['x'])
    if app.spatial is not None:
        app.spatial.update(app.camera)


def onKeyHold(app, key):
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
        app.status = 'Sphere moved'
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
    if k == 'q':
        app.camera.move(up=-0.14)
        return
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
        app.camera.look(dx * 0.35, -dy * 0.35)
        app.lastMouse = (x, y)


def onMouseRelease(app, x, y):
    app.dragging = False
    app.lastMouse = None


def _update_world(app):
    # World shapes use WORLD coords. WebGL2 / WebGPU does the projection.
    # NO project-to-screen, NO shaded 2D circles, NO Canvas2D fallback.
    # All browsers have WebGL, so we just set world coords and let the GPU do it.
    H = PLANE_HALF
    li = 0
    z = -H
    while z <= H + 0.01:
        line = app.planeLines[li]
        li += 1
        line.visible = True
        # Line in 3D: x1,y1,centerZ1 -> x2,y2,centerZ2. Y=0 is the plane.
        line.x1, line.y1 = -H, 0.0
        line.x2, line.y2 = H, 0.0
        line.centerZ1 = z
        line.centerZ2 = z
        line.centerZ = z
        line.fill = '#2a2a4a'
        line.lineWidth = 1
        z += GRID_STEP
    x = -H
    while x <= H + 0.01:
        line = app.planeLines[li]
        li += 1
        line.visible = True
        line.x1, line.y1 = x, 0.0
        line.x2, line.y2 = x, 0.0
        line.centerZ1 = -H
        line.centerZ2 = H
        line.centerZ = 0.0
        line.fill = '#2a2a4a'
        line.lineWidth = 1
        x += GRID_STEP
    corners = [(-H, 0.0, -H), (H, 0.0, -H), (H, 0.0, H), (-H, 0.0, H)]
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        line = app.planeLines[li]
        li += 1
        line.visible = True
        line.x1, line.y1 = a[0], a[1]
        line.x2, line.y2 = b[0], b[1]
        line.centerZ1 = a[2]
        line.centerZ2 = b[2]
        line.centerZ = 0.0
        line.fill = '#555588'
        line.lineWidth = 2
    # Sphere - WORLD coords, WORLD radius. GPU projects.
    sx, sy, sz = app.sphere_pos
    app.sphereShadow.centerX = sx
    app.sphereShadow.centerY = 0.02
    app.sphereShadow.centerZ = sz
    app.sphereShadow.visible = True
    app.sphere.centerX = sx
    app.sphere.centerY = sy
    app.sphere.centerZ = sz
    app.sphereHighlight.centerX = sx - 0.3
    app.sphereHighlight.centerY = sy + 0.3
    app.sphereHighlight.centerZ = sz
    app.sphereLabel.centerX = sx
    app.sphereLabel.centerY = sy + 1.2
    app.sphereLabel.centerZ = sz
    app.sphere.visible = True
    app.sphereHighlight.visible = True
    app.sphereLabel.visible = True
    # Sphere radius in WORLD units, not screen pixels. Pulse scales world radius.
    _r = 1.0
    if app.playing:
        _r += 0.15 * _math.sin(app.pulse)
    app.sphere.radius = _r
    app.sphereHighlight.radius = _r * 0.25
    # Bouncing balls: Oval bodies, world coords, world size
    for i, b in enumerate(app.balls):
        body = app.ballBodies[i]
        hi = app.ballHighlights[i]
        body.centerX = b['x']
        body.centerY = b['y']
        body.centerZ = b['z']
        hi.centerX = b['x'] - b['r'] * 0.35
        hi.centerY = b['y'] + b['r'] * 0.35
        hi.centerZ = b['z']
        body.visible = True
        hi.visible = True
        squash = 0.82 if (b['y'] < b['r'] + 0.25 and b['vy'] < 0) else 1.0
        body.width = b['r'] * 2
        body.height = b['r'] * 2 * squash
        hi.radius = b['r'] * 0.28
    # Reference cubes - WORLD coords, WORLD size
    for i, (cx0, cz0) in enumerate(((-6.0, -8.0), (6.0, 2.0))):
        cube = app.cubeShapes[i]
        cube.centerX = cx0
        cube.centerY = 0.5
        cube.centerZ = cz0
        cube.visible = True
        cube.width = 1.0
        cube.height = 1.0


def redrawAll(app):
    _update_world(app)
    # HUD: just update text / fill on shapes we made in onAppStart
    if app.src is not None:
        dist = app.src.distance_to(app.camera.position)
        gain = app.src.gain_at(app.camera.position)
        pan = app.src.pan_at(app.camera)
        app.hudDist.text = 'dist %.2f m   gain %.2f   pan %+.2f  ( -1 left / +1 right )' % (dist, gain, pan)
        mx, my, mw, mh = 740, 70, 120, 120
        def _map(wx, wz):
            return (mx + (wx + 20.0) / 40.0 * mw,
                    my + 16 + (wz + 20.0) / 40.0 * (mh - 22))
        sx2, sy2 = _map(app.src.position[0], app.src.position[2])
        cx2, cy2 = _map(app.camera.position[0], app.camera.position[2])
        app.miniSphere.centerX = sx2
        app.miniSphere.centerY = sy2
        app.miniCam.centerX = cx2
        app.miniCam.centerY = cy2
        f = app.camera.forward()
        app.miniArrow.x1, app.miniArrow.y1 = cx2, cy2
        app.miniArrow.x2, app.miniArrow.y2 = cx2 + f[0] * 14, cy2 + f[2] * 14
    app.statusLabel.text = app.status
    app.playLabel.text = 'PLAY' if not app.playing else 'PAUSE'
    app.playBtn.fill = '#22aa66' if not app.playing else '#ccaa22'
    app.modeLabel.text = 'MODE: %s (P)' % ('PIPELINE' if app.use_pipeline else 'CLASSIC')
    p = app.camera.position
    app.readout.text = 'cam (%.1f, %.1f, %.1f)  yaw %.0f  pitch %.0f  |  sphere %s  |  envelope %s' % (
        p[0], p[1], p[2], app.camera.yaw, app.camera.pitch, app.sphere_pos, app.envelope)


def main():
    # Plain CMU: no renderer words, no engine words. Just run it.
    _log_versions('main-before-runApp')
    runApp(900, 560, renderer='webgl2')


main()
