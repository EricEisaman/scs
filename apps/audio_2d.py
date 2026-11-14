# 2D SPATIAL audio demo -- stereo sound on a flat playfield.
#
# This IS the 2D spatial audio demo (spatial_audio.py is the 3D one).
# Same idea as 3D spatial, flattened to a top-down plane: every source
# has a 2D position, the listener has a 2D position AND a facing
# direction. Pan and gain come from the source's angle + distance
# RELATIVE TO THE LISTENER, not from world X alone -- turn away from
# a source and it moves behind you.
#
# Run: ?app=audio_2d  (or paste into the sandbox)
#
# This is 2D audio, not 3D: no HRTF, no PannerNode. Each source is a
# node-based pipeline on engine.audio:
#
#   osc -> gain (volume) -> filter (cutoff) -> envelope -> StereoPanner
#       -> destination
#
# The LISTENER is the white arrow. Move it with WASD / arrows (or
# click the playfield), turn it with Q / E. Every step the demo
# recomputes, for each source, in LISTENER space:
#   rel  = atan2(dy, dx) - heading     (angle of source vs facing)
#   pan  = sin(rel)                     (-1 left, +1 right, 0 ahead/behind)
#   gain = inverse-distance * (0.75 + 0.25*cos(rel))  (behind is quieter)
# and pushes them onto the pipeline's panner + gain stages. What you
# hear is exactly what the HUD prints: walk left of a source and it
# moves right; turn 180 deg and it flips behind you and gets quieter.
#
# Controls:
#   WASD / Arrows ... move listener
#   Q / E ............ turn listener (facing -- pan is relative to this)
#   Click playfield ... move listener there
#   Click a source .... toggle that source on / off
#   1 / 2 / 3 ......... select BASS / LEAD / PAD
#   Space ............. play / stop selected source
#   E ................. cycle envelope (pluck / pad / piano) on selected
#   M ................. cycle macro: cutoff 0 / 0.5 / 1
#   Drag sliders ...... volume (perceptual) / macro (log cutoff)
#   P ................. toggle positional <-> fixed stereo
#
# Sound uses Batch 3: engine.audio.create_pipeline(),
# create_envelope(), create_volume_mapper(), create_mapping().

from scs import *
import math as _math

# Sources: (key, label, pos, freq, kind, colour)
SOURCES = [
    ('1', 'BASS', (200.0, 180.0), 110.0, 'sine', '#ff5566'),
    ('2', 'LEAD', (650.0, 180.0), 440.0, 'triangle', '#ffcc33'),
    ('3', 'PAD',  (450.0, 420.0), 220.0, 'sine', '#55aaff'),
]
ENVELOPES = ['pluck', 'pad', 'piano']
MACROS = [0.0, 0.5, 1.0]

HEAR_RANGE = 260.0   # px: at this 2D distance gain is ~0
REF_DIST = 60.0      # px: inside this, gain is full

PLAY_BTN = (40, 470, 160, 44)
STOP_BTN = (212, 470, 120, 44)
MODE_BTN = (344, 470, 220, 44)
VOL_Y = 412
VOL_X0 = 40
VOL_X1 = 460
MACRO_Y = 412
MACRO_X0 = 520
MACRO_X1 = 860


def _inside(x, y, box):
    bx, by, bw, bh = box
    return bx <= x <= bx + bw and by <= y <= by + bh


def _gain_2d(dist):
    """Inverse-distance falloff in 2D. Same shape as 3D gain_at()."""
    if dist <= REF_DIST:
        return 1.0
    return max(0.0, REF_DIST / max(dist, 1.0))


def _make_pipe(app, src):
    """Build (or rebuild) one source's pipeline with its envelope."""
    key, label, pos, freq, kind, colour = src
    name = 'src2d:' + key
    old = app.audio.get_pipeline(name) if app.audio is not None else None
    if old is not None:
        try:
            old.stop()
        except Exception:
            pass
        try:
            app.audio.remove_pipeline(name)
        except Exception:
            pass
    pipe = app.audio.create_pipeline(name, src='oscillator', freq=freq)
    pipe.add_gain(0.0, name='volume')          # set every step from geometry
    pipe.add_filter('lowpass', frequency=4000)  # macro moves this
    pipe.add_envelope(app.envelope)            # 'pluck' | 'pad' | 'piano'
    pipe.add_panner(0.0)                       # StereoPanner, named 'panner'
    pipe.build(app.audio)
    return pipe


def _retune(app):
    """Push listener geometry + sliders onto every pipeline.

    2D SPATIAL core: pan/gain are computed in listener space, so
    turning (Q/E) changes what you hear even standing still.
    """
    if app.audio is None:
        return
    lx, ly = app.listener
    heading = app.heading  # radians, 0 = facing +X (right), + = clockwise (screen y down)
    for key, label, pos, freq, kind, colour in SOURCES:
        st = app.states[key]
        pipe = st['pipe']
        if pipe is None:
            continue
        dx = pos[0] - lx
        dy = pos[1] - ly
        dist = _math.sqrt(dx * dx + dy * dy) or 1.0
        if app.positional:
            rel = _math.atan2(dy, dx) - heading
            rel = (rel + _math.pi) % (2 * _math.pi) - _math.pi  # -> -180..180
            pan = max(-1.0, min(1.0, _math.sin(rel)))
            # Behind you is quieter (simple head-shadow in 2D).
            geo = _gain_2d(dist) * (0.75 + 0.25 * _math.cos(rel))
            st['rel_deg'] = _math.degrees(rel)
        else:
            # Fixed stereo: BASS left, LEAD right, PAD centre.
            pan = {'1': -0.6, '2': 0.6, '3': 0.0}[key]
            geo = 0.8
            st['rel_deg'] = 0.0
        # Volume slider is perceptual (VolumeMapper), geometry is linear.
        master = app.vol_mapper.map(app.volume) if app.vol_mapper else app.volume
        gain = master * geo * (0.9 if st['playing'] else 0.0)
        try:
            pipe.set_param('panner', 'pan', pan)
        except Exception:
            pass
        try:
            pipe.set_param('volume', 'gain', gain)
        except Exception:
            pass
        # Macro -> cutoff in log space (20..20000 Hz), via the real
        # EffectParamMapping, not a hand-rolled formula.
        try:
            cutoff = app.cutoff_map.map(app.macro)
            pipe.set_param('filter', 'frequency', cutoff)
        except Exception:
            pass
        st['pan'] = pan
        st['gain'] = gain
        st['dist'] = dist


def _toggle_source(app, key):
    st = app.states[key]
    if st['playing']:
        try:
            st['pipe'].stop()
        except Exception:
            pass
        st['playing'] = False
        app.status = '%s stopped' % st['label']
    else:
        if st['pipe'] is None:
            src = [s for s in SOURCES if s[0] == key][0]
            st['pipe'] = _make_pipe(app, src)
        try:
            st['pipe'].start()
        except Exception:
            pass
        st['playing'] = True
        app.status = '%s playing -- move the white dot to hear pan/gain' % st['label']
    _retune(app)


def onAppStart(app):
    app.background = '#151522'
    app.audio = getAudioEngine()
    # Batch 3 objects, created once and reused.
    app.envelope = 'pluck'
    app.volume = 0.6
    app.macro = 0.5
    app.positional = True
    app.selected = '2'
    app.listener = (450.0, 300.0)
    app.heading = -_math.pi / 2  # facing up (north) at start
    app.held = set()
    app.status = 'Click PLAY or press Space -- first click enables audio'
    app.stepCount = 0
    app.pulse = 0.0
    if app.audio is not None:
        app.audio.resume()
        app.vol_mapper = app.audio.create_volume_mapper('vol2d', curve='perceptual')
        app.cutoff_map = app.audio.create_mapping('cutoff2d', 'filter', 'frequency',
                                                  20, 20000, log=True)
    else:
        app.vol_mapper = None
        app.cutoff_map = None
    app.states = {}
    for key, label, pos, freq, kind, colour in SOURCES:
        app.states[key] = {'label': label, 'pipe': None, 'playing': False,
                           'pan': 0.0, 'gain': 0.0, 'dist': 0.0, 'rel_deg': 0.0}


def onStep(app):
    app.stepCount += 1
    if any(s['playing'] for s in app.states.values()):
        app.pulse += 0.12
    # WASD / arrows held: move the listener.
    speed = 4.0
    dx = dy = 0.0
    if 'a' in app.held or 'left' in app.held:
        dx -= speed
    if 'd' in app.held or 'right' in app.held:
        dx += speed
    if 'w' in app.held or 'up' in app.held:
        dy -= speed
    if 's' in app.held or 'down' in app.held:
        dy += speed
    if dx != 0.0 or dy != 0.0:
        lx, ly = app.listener
        app.listener = (min(860.0, max(40.0, lx + dx)),
                        min(440.0, max(90.0, ly + dy)))
    _retune(app)


def onKeyHold(app, key):
    app.held.add(str(key).lower())


def onKeyRelease(app, key):
    app.held.discard(str(key).lower())


def onKeyPress(app, key):
    k = str(key).lower()
    if k == ' ':
        _toggle_source(app, app.selected)
        return
    if k in ('1', '2', '3'):
        app.selected = k
        app.status = 'Selected %s -- Space toggles it' % app.states[k]['label']
        return
    if k == 'e':
        i = ENVELOPES.index(app.envelope)
        app.envelope = ENVELOPES[(i + 1) % len(ENVELOPES)]
        # Rebuild the SELECTED source's pipeline with the new envelope.
        st = app.states[app.selected]
        if st['playing']:
            st['pipe'] = _make_pipe(app, [s for s in SOURCES if s[0] == app.selected][0])
            st['pipe'].start()
            _retune(app)
        app.status = 'Envelope: %s (on %s)' % (app.envelope, st['label'])
        return
    if k == 'm':
        i = MACROS.index(app.macro)
        app.macro = MACROS[(i + 1) % len(MACROS)]
        _retune(app)
        app.status = 'Macro: %.1f' % app.macro
        return
    if k == 'q':
        app.heading -= 0.25
        _retune(app)
        app.status = 'Facing %.0f deg' % _math.degrees(app.heading)
        return
    if k == 'p':
        app.positional = not app.positional
        _retune(app)
        app.status = 'Mode: %s' % ('positional (2D pan/gain)' if app.positional else 'fixed stereo')
        return


def onMousePress(app, x, y):
    if _inside(x, y, PLAY_BTN):
        _toggle_source(app, app.selected)
        return
    if _inside(x, y, STOP_BTN):
        for key in app.states:
            if app.states[key]['playing']:
                _toggle_source(app, key)
        app.status = 'All stopped'
        return
    if _inside(x, y, MODE_BTN):
        app.positional = not app.positional
        _retune(app)
        app.status = 'Mode: %s' % ('positional' if app.positional else 'fixed stereo')
        return
    # Volume slider.
    if VOL_X0 - 12 <= x <= VOL_X1 + 12 and VOL_Y - 16 <= y <= VOL_Y + 30:
        app.volume = max(0.0, min(1.0, (x - VOL_X0) / (VOL_X1 - VOL_X0)))
        app.dragging = 'vol'
        _retune(app)
        return
    # Macro slider.
    if MACRO_X0 - 12 <= x <= MACRO_X1 + 12 and MACRO_Y - 16 <= y <= MACRO_Y + 30:
        app.macro = max(0.0, min(1.0, (x - MACRO_X0) / (MACRO_X1 - MACRO_X0)))
        app.dragging = 'macro'
        _retune(app)
        return
    # Click a source: toggle it.
    for key, label, pos, freq, kind, colour in SOURCES:
        if (x - pos[0]) ** 2 + (y - pos[1]) ** 2 <= 34 ** 2:
            app.selected = key
            _toggle_source(app, key)
            return
    # Click the playfield: move the listener there.
    if 0 <= x <= 900 and 72 <= y <= 460:
        app.listener = (float(x), float(y))
        _retune(app)


def onMouseDrag(app, x, y):
    if getattr(app, 'dragging', None) == 'vol':
        app.volume = max(0.0, min(1.0, (x - VOL_X0) / (VOL_X1 - VOL_X0)))
        _retune(app)
    elif getattr(app, 'dragging', None) == 'macro':
        app.macro = max(0.0, min(1.0, (x - MACRO_X0) / (MACRO_X1 - MACRO_X0)))
        _retune(app)
    elif 0 <= x <= 900 and 72 <= y <= 460:
        app.listener = (float(x), float(y))
        _retune(app)


def onMouseRelease(app, x, y):
    app.dragging = None


def redrawAll(app):
    # ---- playfield ----------------------------------------------------
    drawRect(0, 72, 900, 388, fill='#22223a')
    for gx in range(0, 901, 40):
        drawLine(gx, 72, gx, 460, fill='#2e2e4a', lineWidth=1)
    for gy in range(72, 461, 40):
        drawLine(0, gy, 900, gy, fill='#2e2e4a', lineWidth=1)
    # Hear-range ring around the listener.
    lx, ly = app.listener
    drawCircle(lx, ly, HEAR_RANGE, fill=None, border='#3a3a5a', borderWidth=1)
    # Sources: coloured discs, ring pulses while playing.
    for key, label, pos, freq, kind, colour in SOURCES:
        st = app.states[key]
        r = 26 + (6 * _math.sin(app.pulse) if st['playing'] else 0)
        drawCircle(pos[0], pos[1], r, fill=colour, border='white' if app.selected == key else None,
                   borderWidth=2 if app.selected == key else 0)
        drawLabel(label, pos[0], pos[1] - 4, fill='black', size=12, bold=True, align='center')
        drawLabel('%.0f Hz' % freq, pos[0], pos[1] + 12, fill='black', size=10, align='center')
        if st['playing']:
            drawLabel('ON', pos[0], pos[1] + 40, fill='#7aff9a', size=11, bold=True, align='center')
    # Listener: white arrow pointing where you face. Pan is relative
    # to this arrow -- turn it and every source moves in your ears.
    hx = _math.cos(app.heading)
    hy = _math.sin(app.heading)
    drawCircle(lx, ly, 10, fill='white', border='#22aa66', borderWidth=3)
    drawLine(lx, ly, lx + hx * 22, ly + hy * 22, fill='#22aa66', lineWidth=3)
    drawLabel('YOU', lx, ly - 24, fill='white', size=11, bold=True, align='center')
    drawLabel('facing %.0f deg' % _math.degrees(app.heading),
              lx, ly + 24, fill='#7aff9a', size=10, align='center')
    # ---- HUD -----------------------------------------------------------
    drawRect(0, 0, 900, 72, fill='#000000')
    drawLabel('2D SPATIAL AUDIO  --  move + turn the white arrow, hear pan + gain',
              20, 14, fill='white', size=18, bold=True, align='left-top')
    drawLabel('WASD move  |  Q/E turn (facing)  |  Click = move  |  Click source = toggle  |  Space = selected  |  E envelope  |  P mode',
              20, 40, fill='#a0a0c0', size=12, align='left-top')
    # Per-source readout: the same numbers the ear hears.
    for i, (key, label, pos, freq, kind, colour) in enumerate(SOURCES):
        st = app.states[key]
        drawLabel('%s  dist %3.0fpx  rel %+4.0f deg  pan %+.2f  gain %.2f  %s'
                  % (label, st['dist'], st['rel_deg'], st['pan'], st['gain'],
                     'ON' if st['playing'] else 'off'),
                  880, 14 + i * 16, fill=colour, size=12, align='right-top')
    # Status bar.
    drawRect(40, 528, 820, 28, fill='#26263a', roundness=6)
    drawLabel(app.status, 56, 536, fill='#ffd97a', size=13, align='left-top')
    # Buttons.
    drawRect(PLAY_BTN[0], PLAY_BTN[1], PLAY_BTN[2], PLAY_BTN[3], fill='#22aa66', roundness=8)
    drawLabel('PLAY SEL', PLAY_BTN[0] + 80, PLAY_BTN[1] + 22, fill='white', size=14, bold=True, align='center')
    drawRect(STOP_BTN[0], STOP_BTN[1], STOP_BTN[2], STOP_BTN[3], fill='#cc3344', roundness=8)
    drawLabel('STOP ALL', STOP_BTN[0] + 60, STOP_BTN[1] + 22, fill='white', size=14, bold=True, align='center')
    drawRect(MODE_BTN[0], MODE_BTN[1], MODE_BTN[2], MODE_BTN[3], fill='#2e2e4a', roundness=8)
    drawLabel('MODE: %s (P)' % ('POSITIONAL' if app.positional else 'FIXED STEREO'),
              MODE_BTN[0] + 110, MODE_BTN[1] + 22, fill='white', size=12, bold=True, align='center')
    # Sliders.
    cutoff = app.cutoff_map.map(app.macro) if app.cutoff_map else 0.0
    vol_db = app.vol_mapper.map_db(app.volume) if app.vol_mapper else 0.0
    drawLabel('Volume  %.0f%%  (%.1f dB, perceptual)' % (app.volume * 100, vol_db),
              40, VOL_Y - 14, fill='white', size=12, align='left-top')
    drawRect(VOL_X0, VOL_Y, VOL_X1 - VOL_X0, 14, fill='#2e2e4a', roundness=7)
    drawRect(VOL_X0, VOL_Y, int((VOL_X1 - VOL_X0) * app.volume), 14, fill='#22aa66', roundness=7)
    drawCircle(VOL_X0 + (VOL_X1 - VOL_X0) * app.volume, VOL_Y + 7, 12, fill='white', border='#22aa66', borderWidth=3)
    drawLabel('Macro cutoff  %.0f Hz (log)' % cutoff, 520, MACRO_Y - 14, fill='white', size=12, align='left-top')
    drawRect(MACRO_X0, MACRO_Y, MACRO_X1 - MACRO_X0, 14, fill='#2e2e4a', roundness=7)
    drawRect(MACRO_X0, MACRO_Y, int((MACRO_X1 - MACRO_X0) * app.macro), 14, fill='#ffcc33', roundness=7)
    drawCircle(MACRO_X0 + (MACRO_X1 - MACRO_X0) * app.macro, MACRO_Y + 7, 12, fill='white', border='#ffcc33', borderWidth=3)
    drawLabel('envelope: %s (E)  |  selected: %s' % (app.envelope, app.states[app.selected]['label']),
              40, 496, fill='#a0a0c0', size=12, align='left-top')


def main():
    runApp(900, 560)


main()
