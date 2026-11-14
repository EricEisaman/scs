# Spatial audio demo -- THREE modes, ONE rule:
#
#   NO ENGINE SPECIFIED  ->  OLD 2D ENGINE (SCS runApp, no renderer arg).
#                             This is the compat default. Nothing upgrades
#                             you silently. The 2D engine draws the scene
#                             with its own 2D primitives (projected circle
#                             + grid lines) and says so in the HUD.
#   ?engine=webgl2     ->  SEPARATE WebGL2 3D engine (scs_engine_webgl2.py).
#                             Own native WebGL2 context, own loop, NO runApp.
#   ?engine=webgpu     ->  SEPARATE WebGPU 3D engine (scs_engine_webgpu.py).
#                             Own native WebGPU context/device, own loop,
#                             NO runApp.
#
# (?renderer=webgl2 / webgpu is also honoured as an engine request
# for this demo, so ?app=spatial_audio_demo&renderer=webgl2 works.)
#
# Scene in all three modes: a BLUE SPHERE is the sound source
# (440 Hz sine). You are the listener -- Camera3D drives BOTH the
# view (GL or 2D projection) AND the Web Audio listener, so what
# you see is what you hear.
#   WASD ....... move   Q/E down/up   Shift sprint
#   Mouse drag . look   Arrows ...... look
#   Space / PLAY play/stop   1/2/3 move source   C centre front
#
# Walk toward the sphere: louder. Walk past it: left -> right.

try:
    from browser import document, window
except ImportError:
    document = None
    window = None

import math


def _engine_requested():
    try:
        search = str(window.location.search or '').lower()
    except Exception:
        search = ''
    if 'engine=webgpu' in search or 'renderer=webgpu' in search:
        return 'webgpu'
    if 'engine=webgl2' in search or 'renderer=webgl2' in search:
        return 'webgl2'
    # DEFAULT: old 2D engine. Preserve compatibility.
    return '2d'


ENGINE = _engine_requested()

PRESETS = {
    '1': (0.0, 1.5, -2.0),
    '2': (-4.0, 1.5, -2.0),
    '3': (4.0, 1.5, -2.0),
}


# ======================================================================
# SEPARATE ENGINES: WebGL2 / WebGPU. No runApp, no SCS 2D loop.
# The engine owns the canvas + context. If it fails, it fails --
# it does NOT fall back to 2D.
# ======================================================================
if ENGINE in ('webgl2', 'webgpu'):

    from scs_3d import Camera3D
    from scs_spatial_audio import SpatialAudioEngine
    from scs_engine_webgl2 import WebGL2Engine
    from scs_engine_webgpu import WebGPU3DEngine

    class Demo:
        def __init__(self):
            self.camera = Camera3D(position=(0.0, 2.0, 6.0), yaw=0.0,
                                   pitch=-4.0)
            self.spatial = SpatialAudioEngine()
            self.src = self.spatial.create_source(
                position=(0.0, 1.5, -2.0), freq=440.0, kind='sine',
                volume=0.5, loop=True, name='blue sphere')
            self.playing = False
            self.status = 'Click PLAY -- browser needs a click for audio'
            self.held = set()
            self.sprinting = False
            self.dragging = False
            self.last_mouse = None
            self.pulse = 0.0
            self.engine = None
            self.hud_status = None
            self.hud_stats = None
            self._pick_engine()

        def _pick_engine(self):
            canvas = None
            try:
                canvas = document.getElementById('canvas')
            except Exception:
                canvas = None
            if ENGINE == 'webgpu':
                self.engine = WebGPU3DEngine(canvas=canvas, width=900,
                                             height=560)
                self.engine.on_ready = self._start_loop
                self.engine.on_error = self._engine_failed
                if self.engine.error:
                    self._engine_failed(self.engine.error)
            else:
                self.engine = WebGL2Engine(canvas=canvas, width=900,
                                           height=560)
                if self.engine.error:
                    self._engine_failed(self.engine.error)
                else:
                    self._start_loop()

        def _engine_failed(self, err):
            self.status = ('ENGINE FAILED (%s): %s -- not falling back '
                           'to 2D. Reload with no ?engine= for 2D.' %
                           (ENGINE, err))
            self._build_hud()
            if self.hud_status is not None:
                self.hud_status.textContent = self.status

        def _build_hud(self):
            if document is None:
                return
            try:
                body = document.body
                wrap = document.createElement('div')
                wrap.setAttribute('style',
                    'font-family:sans-serif;color:#fff;max-width:900px;'
                    'margin:8px auto;')
                title = document.createElement('div')
                title.textContent = ('SPATIAL AUDIO -- blue sphere = sound '
                                     '(engine: %s, separate context)' % ENGINE)
                title.setAttribute('style',
                                   'font-size:18px;font-weight:bold;')
                sub = document.createElement('div')
                sub.textContent = ('WASD move | Q/E down/up | Shift sprint | '
                                   'Drag / Arrows look | Space play | '
                                   '1/2/3 move source | C centre front')
                sub.setAttribute('style', 'color:#a0a0c0;font-size:13px;')
                self.hud_status = document.createElement('div')
                self.hud_status.textContent = self.status
                self.hud_status.setAttribute(
                    'style', 'background:#26263a;padding:8px;margin:8px 0;'
                             'color:#ffd97a;')
                self.hud_stats = document.createElement('div')
                self.hud_stats.setAttribute(
                    'style', 'color:#ffd97a;font-size:13px;')
                btn = document.createElement('button')
                btn.textContent = 'PLAY'
                btn.setAttribute('style',
                                 'padding:8px 20px;margin-right:8px;')
                btn.addEventListener('click', self._on_play_click)
                wrap.appendChild(title)
                wrap.appendChild(sub)
                wrap.appendChild(self.hud_status)
                wrap.appendChild(self.hud_stats)
                wrap.appendChild(btn)
                body.insertBefore(wrap, body.firstChild)
            except Exception:
                pass

        def _on_play_click(self, _ev=None):
            self.toggle_play()

        def toggle_play(self):
            if self.src.playing:
                self.src.stop()
                self.playing = False
                self.status = 'Stopped -- press Space or PLAY'
            else:
                ok = self.src.start()
                self.playing = bool(ok)
                self.status = ('Playing -- walk with WASD, listen left/right'
                               if ok else 'Audio blocked -- click PLAY again')
            if self.hud_status is not None:
                self.hud_status.textContent = self.status

        def _bind_input(self):
            if window is None:
                return
            try:
                window.addEventListener('keydown', self._on_key_down)
                window.addEventListener('keyup', self._on_key_up)
                c = self.engine.canvas if self.engine else None
                if c is not None:
                    c.addEventListener('mousedown', self._on_mouse_down)
                    window.addEventListener('mousemove', self._on_mouse_move)
                    window.addEventListener('mouseup', self._on_mouse_up)
            except Exception:
                pass

        def _on_key_down(self, ev):
            k = str(getattr(ev, 'key', '') or '').lower()
            if k == ' ':
                self.toggle_play()
                return
            if k in PRESETS:
                self.src.set_position(PRESETS[k])
                self.status = 'Source moved to %s' % (PRESETS[k],)
                return
            if k == 'c':
                f = self.camera.forward()
                p = self.camera.position
                self.src.set_position((p[0] + f[0] * 4.0, 1.5,
                                       p[2] + f[2] * 4.0))
                self.status = 'Source moved in front of you'
                return
            if k == 'shift':
                self.sprinting = True
                return
            if k == 'arrowleft':
                self.camera.look(-4.0, 0.0)
            elif k == 'arrowright':
                self.camera.look(4.0, 0.0)
            elif k == 'arrowup':
                self.camera.look(0.0, 3.0)
            elif k == 'arrowdown':
                self.camera.look(0.0, -3.0)
            else:
                self.held.add(k)

        def _on_key_up(self, ev):
            k = str(getattr(ev, 'key', '') or '').lower()
            if k == 'shift':
                self.sprinting = False
            self.held.discard(k)

        def _on_mouse_down(self, ev):
            self.dragging = True
            self.last_mouse = (ev.clientX, ev.clientY)

        def _on_mouse_move(self, ev):
            if self.dragging and self.last_mouse is not None:
                dx = ev.clientX - self.last_mouse[0]
                dy = ev.clientY - self.last_mouse[1]
                self.camera.look(dx * 0.35, -dy * 0.35)
                self.last_mouse = (ev.clientX, ev.clientY)

        def _on_mouse_up(self, _ev):
            self.dragging = False
            self.last_mouse = None

        def _start_loop(self):
            self._build_hud()
            self._bind_input()
            if window is not None:
                window.requestAnimationFrame(self._frame)

        def _frame(self, _t=None):
            speed = 0.30 if self.sprinting else 0.12
            if 'w' in self.held:
                self.camera.move(forward=speed)
            if 's' in self.held:
                self.camera.move(forward=-speed)
            if 'a' in self.held:
                self.camera.move(right=-speed)
            if 'd' in self.held:
                self.camera.move(right=speed)
            if 'q' in self.held:
                self.camera.move(up=-speed)
            if 'e' in self.held:
                self.camera.move(up=speed)
            if self.playing:
                self.pulse += 0.12
            self.spatial.update(self.camera)
            self.engine.clear_scene()
            self.engine.add_floor(22.0, '#22223a')
            pulse_r = 0.9 + (0.15 * math.sin(self.pulse)
                             if self.playing else 0.0)
            sx, sy, sz = self.src.position
            self.engine.add_metal_sphere(sx, sy, sz, pulse_r, color='#a8c4ff', roughness=0.12)
            self.engine.add_box(-3.0, 0.5, -4.0, 1.0, 1.0, 1.0, 'gray')
            self.engine.add_box(3.0, 0.5, -1.0, 1.0, 1.0, 1.0, 'gray')
            self.engine.render(self.camera)
            if self.hud_stats is not None:
                dist = self.src.distance_to(self.camera.position)
                gain = self.src.gain_at(self.camera.position)
                pan = self.src.pan_at(self.camera)
                p = self.camera.position
                self.hud_stats.textContent = (
                    'dist %.2f m  gain %.2f  pan %+.2f  |  '
                    'cam (%.1f, %.1f, %.1f) yaw %.0f pitch %.0f' %
                    (dist, gain, pan, p[0], p[1], p[2],
                     self.camera.yaw, self.camera.pitch))
            if self.hud_status is not None:
                self.hud_status.textContent = self.status
            if window is not None:
                window.requestAnimationFrame(self._frame)

    Demo()


# ======================================================================
# DEFAULT: OLD 2D ENGINE. No ?engine= -> runApp() with NO renderer arg,
# so _resolve_renderer_kind() falls through to '2d'. This is the
# compat path. The scene is drawn with the 2D engine's own primitives.
# It does NOT pretend to be 3D -- HUD says "2D compat".
# ======================================================================
else:
    from scs import *

    PLAY_BTN = (40, 470, 160, 44)
    STOP_BTN = (212, 470, 120, 44)
    CENTER_BTN = (344, 470, 200, 44)

    def _inside(x, y, box):
        bx, by, bw, bh = box
        return bx <= x <= bx + bw and by <= y <= by + bh

    def _toggle_play_2d(app):
        if app.src is None:
            app.status = 'Audio unavailable'
            return
        if app.src.playing:
            app.src.stop()
            app.playing = False
            app.status = 'Stopped -- press Space or PLAY'
        else:
            ok = app.src.start()
            app.playing = bool(ok)
            app.status = ('Playing -- walk with WASD, listen left/right'
                          if ok else
                          'Audio blocked -- click PLAY again')

    def onAppStart(app):
        app.background = '#0e0e1a'
        # NO setRenderer() here. No renderer arg in runApp() below.
        # No engine specified -> old 2D engine. That is the default.
        app.camera = Camera3D(position=(0.0, 2.0, 6.0), yaw=0.0,
                              pitch=-4.0)
        app.spatial = getSpatialAudioEngine()
        app.src = None
        if app.spatial is not None:
            app.src = app.spatial.create_source(
                position=(0.0, 1.5, -2.0), freq=440.0, kind='sine',
                volume=0.5, loop=True, name='blue sphere')
        app.playing = False
        app.status = 'Click PLAY (browser needs a click for audio)'
        app.speed = 0.12
        app.sprint = 0.30
        app.sprinting = False
        app.dragging = False
        app.lastMouse = None
        app.pulse = 0.0

    def onStep(app):
        if app.playing:
            app.pulse += 0.12
        if app.spatial is not None:
            app.spatial.update(app.camera)

    def onKeyHold(app, key):
        k = str(key).lower()
        speed = app.sprint if getattr(app, 'sprinting', False) else app.speed
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
        elif k == 'e':
            app.camera.move(up=speed)

    def onKeyPress(app, key):
        k = str(key).lower()
        if k == 'shift':
            app.sprinting = True
            return
        if k == ' ':
            _toggle_play_2d(app)
            return
        if k in PRESETS and app.src is not None:
            app.src.set_position(PRESETS[k])
            app.status = 'Source moved to %s' % (PRESETS[k],)
            return
        if k == 'c' and app.src is not None:
            f = app.camera.forward()
            p = app.camera.position
            app.src.set_position((p[0] + f[0] * 4.0, 1.5,
                                  p[2] + f[2] * 4.0))
            app.status = 'Source moved in front of you'
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
            _toggle_play_2d(app)
            return
        if _inside(x, y, STOP_BTN):
            if app.src is not None:
                app.src.stop()
            app.playing = False
            app.status = 'Stopped'
            return
        if _inside(x, y, CENTER_BTN):
            if app.src is not None:
                app.src.set_position((0.0, 1.5, -2.0))
                app.status = 'Source centred'
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

    def redrawAll(app):
        # 2D compat rendering: floor grid as projected 2D lines,
        # sphere as a projected 2D circle sized by distance.
        # This IS the old 2D engine doing its job -- not 3D.
        cam = app.camera
        W, H = 900, 560
        # Floor grid
        for i in range(-10, 11, 2):
            for (x1, z1, x2, z2) in ((-10, i, 10, i), (i, -10, i, 10)):
                p1 = cam.project((x1, 0.0, z1), W, H)
                p2 = cam.project((x2, 0.0, z2), W, H)
                if not p1[3] and not p2[3]:
                    drawLine(p1[0], p1[1], p2[0], p2[1],
                             fill='#3a3a5a', lineWidth=1)
        # Depth-reference boxes as projected squares
        for (bx, bz) in ((-3.0, -4.0), (3.0, -1.0)):
            p = cam.project((bx, 0.5, bz), W, H)
            if not p[3]:
                drawRect(p[0] - 18, p[1] - 18, 36, 36, fill='gray')
        # Sphere as projected circle
        if app.src is not None:
            sx, sy, sz = app.src.position
        else:
            sx, sy, sz = (0.0, 1.5, -2.0)
        p = cam.project((sx, sy, sz), W, H)
        if not p[3]:
            dist = max(0.1, math.sqrt(
                (sx - cam.position[0]) ** 2 +
                (sy - cam.position[1]) ** 2 +
                (sz - cam.position[2]) ** 2))
            pr = 0.9 * (H / 2.0) / dist
            if app.playing:
                pr *= (1.0 + 0.15 * math.sin(app.pulse))
            drawCircle(p[0], p[1], max(4.0, pr), fill='blue',
                       border='black', borderWidth=1)
            drawCircle(p[0] - pr * 0.3, p[1] - pr * 0.35,
                       max(1.0, pr * 0.18), fill='white')
        # HUD
        drawRect(0, 0, 900, 62, fill='#000000')
        drawLabel('SPATIAL AUDIO -- 2D COMPAT (no ?engine=, old 2D engine)',
                  20, 18, fill='white', size=18, bold=True, align='left-top')
        drawLabel('WASD move | Q/E down/up | Shift sprint | Drag / Arrows look | Space play',
                  20, 42, fill='#a0a0c0', size=12, align='left-top')
        drawLabel('Renderer: %s' % getRendererKind(),
                  880, 18, fill='#ffd97a', size=13, align='right-top')
        if app.src is not None:
            dist = app.src.distance_to(app.camera.position)
            gain = app.src.gain_at(app.camera.position)
            pan = app.src.pan_at(app.camera)
            drawLabel('dist %.2f m  gain %.2f  pan %+.2f' % (dist, gain, pan),
                      880, 42, fill='#ffd97a', size=12, align='right-top')
        drawRect(40, 430, 820, 32, fill='#26263a', roundness=6)
        drawLabel(app.status, 56, 446, fill='#ffd97a', size=13,
                  align='left-top')
        drawRect(PLAY_BTN[0], PLAY_BTN[1], PLAY_BTN[2], PLAY_BTN[3],
                 fill='#22aa66' if not app.playing else '#ccaa22',
                 roundness=8)
        drawLabel('PLAY' if not app.playing else 'PAUSE',
                  PLAY_BTN[0] + 80, PLAY_BTN[1] + 22,
                  fill='white', size=15, bold=True, align='center')
        drawRect(STOP_BTN[0], STOP_BTN[1], STOP_BTN[2], STOP_BTN[3],
                 fill='#cc3344', roundness=8)
        drawLabel('STOP', STOP_BTN[0] + 60, STOP_BTN[1] + 22,
                  fill='white', size=15, bold=True, align='center')
        drawRect(CENTER_BTN[0], CENTER_BTN[1], CENTER_BTN[2], CENTER_BTN[3],
                 fill='#2e2e4a', roundness=8)
        drawLabel('CENTRE SOURCE (C)', CENTER_BTN[0] + 100,
                  CENTER_BTN[1] + 22, fill='white', size=13, bold=True,
                  align='center')
        p = app.camera.position
        drawLabel('cam (%.1f, %.1f, %.1f)  yaw %.0f  pitch %.0f'
                  % (p[0], p[1], p[2], app.camera.yaw, app.camera.pitch),
                  40, 530, fill='#a0a0c0', size=12, align='left-top')
        drawLabel('For real 3D: reload with ?engine=webgl2 or ?engine=webgpu',
                  40, 548, fill='#8888aa', size=11, align='left-top')

    # NO renderer arg here. _resolve_renderer_kind() -> '2d' by default.
    # That is the compat rule: no engine specified = old 2D engine.
    runApp(900, 560)
