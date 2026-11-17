# Simple spatial audio test - uses the shared module, no copied fallback code.
from scs import *
try:
    from scs_fallback_audio import SpatialAudioEngine
except Exception:
    SpatialAudioEngine = None
from scs_3d import Camera3D
import math as _math

PLAY_BTN = (40, 470, 160, 44)
STOP_BTN = (212, 470, 120, 44)

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
        app.status = 'Stopped - press Space or PLAY'
    else:
        if app.spatial is not None:
            app.spatial.resume()
        app.src.start()
        app.playing = True
        app.status = 'Playing - walk with WASD, listen left/right'

def onAppStart(app):
    app.background = '#0e0e1a'
    app.camera = Camera3D(position=(0.0, 2.0, 6.0), yaw=0.0, pitch=-4.0)
    app.spatial = SpatialAudioEngine() if SpatialAudioEngine is not None else None
    app.sphere_pos = (0.0, 1.0, -2.0)
    app.src = None
    if app.spatial is not None:
        app.src = app.spatial.create_source(position=app.sphere_pos, freq=440.0, kind='sine', volume=0.5, loop=True)
    app.playing = False
    app.status = 'Click PLAY (browser needs a click for audio)'
    app.speed = 0.14
    app.sprinting = False
    # HUD
    app.hudTitle = Label('SIMPLE SPATIAL AUDIO - GOLD = sound source', 20, 18, fill='#FFD700', size=18, bold=True, align='left-top')
    app.hudHelp = Label('WASD move | Shift sprint | Drag look | Space play', 20, 42, fill='#a0a0c0', size=12, align='left-top')
    app.hudDist = Label('', 880, 42, fill='#ffd97a', size=12, align='right-top')
    app.statusBar = Rect(40, 430, 820, 32, fill='#26263a', roundness=6, align='left-top')
    app.statusLabel = Label(app.status, 56, 446, fill='#ffd97a', size=13, align='left-top')
    app.playBtn = Rect(PLAY_BTN[0], PLAY_BTN[1], PLAY_BTN[2], PLAY_BTN[3], fill='#22aa66', roundness=8, align='left-top')
    app.playLabel = Label('PLAY', PLAY_BTN[0] + 80, PLAY_BTN[1] + 22, fill='white', size=15, bold=True, align='center')
    app.stopBtn = Rect(STOP_BTN[0], STOP_BTN[1], STOP_BTN[2], STOP_BTN[3], fill='#cc3344', roundness=8, align='left-top')
    app.stopLabel = Label('STOP', STOP_BTN[0] + 60, STOP_BTN[1] + 22, fill='white', size=15, bold=True, align='center')
    app.miniMap = Rect(740, 70, 120, 120, fill='#111128', roundness=6, align='left-top')
    app.miniMapTitle = Label('TOP-DOWN  40m', 800, 80, fill='#8888aa', size=10, align='center')
    app.miniSphere = Circle(800, 120, 6, fill='#FFD700', border='white', borderWidth=1)
    app.miniCam = Circle(800, 120, 4, fill='white')
    app.miniArrow = Line(800, 120, 800, 106, fill='white', lineWidth=2)
    app.readout = Label('', 40, 530, fill='#a0a0c0', size=12, align='left-top')
    # World: sphere + shadow, centerZ = 3D
    app.sphereShadow = Oval(450, 280, 70, 14, fill='black', centerZ=0.02)
    app.sphere = Circle(0, 1, 1.2, fill='#FFD700', border='white', borderWidth=3, centerZ=-2.0)
    app.sphereLabel = Label('SOUND SOURCE - 440 Hz', 450, 340, fill='#FFD700', size=11, bold=True, align='center', centerZ=-2.0)

def onStep(app):
    if app.spatial is not None:
        app.spatial.update(app.camera)

def onKeyHold(app, key):
    k = str(key).lower()
    speed = 0.34 if app.sprinting else app.speed
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

def onMouseDrag(app, x, y):
    if app.lastMouse is not None:
        dx = x - app.lastMouse[0]
        dy = y - app.lastMouse[1]
        app.camera.look(dx * 0.3, -dy * 0.3)
    app.lastMouse = (x, y)

def onMouseRelease(app, x, y):
    app.lastMouse = None

def _update_world(app):
    sx, sy, sz = app.sphere_pos
    app.sphereShadow.centerX = sx
    app.sphereShadow.centerY = 0.02
    app.sphereShadow.centerZ = sz
    app.sphere.centerX = sx
    app.sphere.centerY = sy
    app.sphere.centerZ = sz
    app.sphereLabel.centerX = sx
    app.sphereLabel.centerY = sy + 1.2
    app.sphereLabel.centerZ = sz

def redrawAll(app):
    _update_world(app)
    if app.src is not None:
        dist = app.src.distance_to(app.camera.position)
        gain = app.src.gain_at(app.camera.position)
        pan = app.src.pan_at(app.camera)
        app.hudDist.text = 'dist %.2f m   gain %.2f   pan %+.2f' % (dist, gain, pan)
        mx, my, mw, mh = 740, 70, 120, 120
        def _map(wx, wz):
            return (mx + (wx + 20.0) / 40.0 * mw, my + 16 + (wz + 20.0) / 40.0 * (mh - 22))
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
    p = app.camera.position
    app.readout.text = 'cam (%.1f, %.1f, %.1f)  yaw %.0f  |  sphere %s' % (p[0], p[1], p[2], app.camera.yaw, app.sphere_pos)

def main():
    runApp(900, 560, renderer='webgl2', enableFullscreen=True)

main()
