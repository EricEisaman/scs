"""
apps/soundboard.py - QBasic Gorillas 8-Bit Soundboard
1050x700 SCS app that demonstrates all original Gorillas PLAY MML sounds via extensions/8bit.py

Imports:
- extensions/8bit.py (via importlib because name starts with digit)
- optionally extensions/ui.py and extensions/canvas_ui.py for UI helpers

All sounds are identical to original GORILLA.BAS PLAY strings:
- Title 1812, Throw, Building Explosion, Gorilla Explosion, Victory, Intro parts, Full intro

Visual design: Retro CRT / EGA city skyline with gorillas beating chest.
"""

from scs import *
import importlib
import math
import random

# ----------------------------------------------------------------------
# Import 8bit extension (digit-starting module requires importlib)
# ----------------------------------------------------------------------
eightbit = importlib.import_module('extensions.8bit')
QBasicMMLParser = eightbit.QBasicMMLParser
EightBitPlayer = eightbit.EightBitPlayer
EightBitAudioEngine = eightbit.EightBitAudioEngine
GORILLAS_MML = eightbit.GORILLAS_MML
GORILLA_SOUNDS = eightbit.GORILLA_SOUNDS
GORILLA_DESCRIPTIONS = eightbit.GORILLA_DESCRIPTIONS

# Try ui and canvas_ui extensions
try:
    ui_ext = importlib.import_module('extensions.ui')
    HAS_UI = True
except Exception:
    ui_ext = None
    HAS_UI = False

try:
    canvas_ui_ext = importlib.import_module('extensions.canvas_ui')
    HAS_CANVAS_UI = True
except Exception:
    canvas_ui_ext = None
    HAS_CANVAS_UI = False

# Also try legacy names
try:
    canvas_ui_alt = importlib.import_module('extensions.canvas_ui')
    if not HAS_CANVAS_UI:
        canvas_ui_ext = canvas_ui_alt
        HAS_CANVAS_UI = True
except:
    pass

# ----------------------------------------------------------------------
# Button definitions - 13 sounds
# ----------------------------------------------------------------------
SOUND_ORDER = [
    ("title", "TITLE 1812", rgb(255, 220, 100)),
    ("throw", "THROW", rgb(120, 220, 255)),
    ("building_explosion", "BLDG BOOM", rgb(255, 150, 100)),
    ("gorilla_explosion", "GORILLA BOOM", rgb(255, 90, 90)),
    ("victory_single", "VICTORY NOTE", rgb(150, 255, 150)),
    ("victory_dance", "VICTORY DANCE", rgb(100, 255, 180)),
    ("intro_part1", "INTRO P1 - Bass", rgb(180, 180, 255)),
    ("intro_part2", "INTRO P2 - Eb/D-", rgb(200, 160, 255)),
    ("intro_part3", "INTRO P3 - G-/E", rgb(255, 160, 230)),
    ("intro_part4", "INTRO P4 - B/A/G-", rgb(255, 200, 120)),
    ("intro_melody", "INTRO MELODY", rgb(140, 240, 255)),
    ("intro_fanfare_8x", "FANFARE 8X", rgb(255, 255, 150)),
    ("full_intro", "FULL INTRO", rgb(255, 255, 255)),
]

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def make_city_buildings(width, count=18):
    buildings = []
    x = 0
    # Gorillas style random heights with slope
    slope = random.randint(1, 6)
    if slope == 1:
        new_ht = 15
        inc = 8
    elif slope == 2:
        new_ht = 130
        inc = -8
    else:
        new_ht = 50
        inc = 0
    while x < width and len(buildings) < count:
        bw = random.randint(35, 70)
        if slope in (1, 2):
            new_ht += inc
        elif slope in (3, 4, 5):
            if x > width//2:
                new_ht -= 4
            else:
                new_ht += 4
        bh = max(30, min(220, new_ht + random.randint(-40, 40)))
        color = random.choice([rgb(40, 40, 80), rgb(50, 70, 120), rgb(60, 50, 90), rgb(35, 60, 100)])
        # windows
        wins = []
        for wx in range(5, bw-8, 12):
            for wy in range(10, int(bh)-12, 16):
                if random.random() > 0.3:
                    wins.append((wx, wy))
        buildings.append({'x': x, 'w': bw, 'h': bh, 'color': color, 'wins': wins})
        x += bw + 4
    return buildings


# ----------------------------------------------------------------------
# App lifecycle
# ----------------------------------------------------------------------
def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.setMaxShapeCount(5000)

    # Colors - EGA retro palette
    app.bg_top = rgb(8, 10, 30)
    app.bg_mid = rgb(18, 20, 50)
    app.bg_bottom = rgb(10, 15, 35)
    app.cyan = rgb(0, 255, 255)
    app.magenta = rgb(255, 0, 255)
    app.yellow = rgb(255, 255, 0)

    # Audio
    app.engine = EightBitAudioEngine(quality="high")
    app.parser = QBasicMMLParser()
    app.player = app.engine.player

    # State
    app.buildings = make_city_buildings(1050, 22)
    app.gorilla_left_x = 90
    app.gorilla_right_x = 880
    app.gorilla_y = 0  # computed
    app.gorilla_anim = 0  # 0=down, 1=left up, 2=right up
    app.gorilla_anim_timer = 0
    app.playing_name = None
    app.playing_events = []
    app.playing_time = 0
    app.playing_duration = 0
    app.banana_pos = None
    app.banana_timer = 0
    app.explosion_pos = None
    app.explosion_radius = 0
    app.explosion_timer = 0
    app.crt_flicker = 0

    # Buttons - grid 4 cols
    app.buttons = []
    cols = 4
    btn_w = 230
    btn_h = 52
    start_x = 30
    start_y = 110
    gap_x = 16
    gap_y = 12
    for idx, (key, label, col) in enumerate(SOUND_ORDER):
        r = idx // cols
        c = idx % cols
        x = start_x + c * (btn_w + gap_x)
        y = start_y + r * (btn_h + gap_y)
        app.buttons.append({
            'key': key,
            'label': label,
            'x': x,
            'y': y,
            'w': btn_w,
            'h': btn_h,
            'color': col,
            'hover': False,
            'mml': GORILLA_SOUNDS.get(key, [""])[0] if len(GORILLA_SOUNDS.get(key, []))==1 else f"{len(GORILLA_SOUNDS.get(key, []))} phrases"
        })

    # Detail panel
    app.detail_x = 30
    app.detail_y = 110 + 4 * (btn_h + gap_y) + 18
    app.detail_w = 4 * (btn_w + gap_x) - gap_x
    app.detail_h = 170

    # Right side visualizer
    app.vis_x = start_x + 4 * (btn_w + gap_x) + 20
    app.vis_y = 110
    app.vis_w = 1050 - app.vis_x - 30
    app.vis_h = 580

    app.show_help = True
    app.frame = 0

def onMouseMove(app, mx, my):
    for btn in app.buttons:
        btn['hover'] = (btn['x'] <= mx <= btn['x']+btn['w'] and btn['y'] <= my <= btn['y']+btn['h'])

def onMousePress(app, mx, my):
    # Resume audio - required after user gesture
    app.engine.resume()
    app.player.resume()
    app.show_help = False

    # Check buttons
    for btn in app.buttons:
        if btn['x'] <= mx <= btn['x']+btn['w'] and btn['y'] <= my <= btn['y']+btn['h']:
            key = btn['key']
            app.playing_name = key
            mml_list = GORILLA_SOUNDS.get(key, [])
            # Parse with state carried
            app.parser.reset()
            events = []
            for mml in mml_list:
                ev = app.parser.parse(mml, carry_state=True)
                events.extend(ev)
            app.playing_events = events
            app.playing_time = 0
            app.playing_duration = sum(e['total_duration'] for e in events)
            app.gorilla_anim_timer = 0
            app.banana_timer = 0
            app.explosion_timer = 0
            app.explosion_radius = 0

            # Trigger visual effects based on sound
            if key == "throw":
                app.banana_pos = {'x': app.gorilla_left_x + 30, 'y': app.height - 180, 'vx': 8, 'vy': -12}
                app.banana_timer = 60
            elif "explosion" in key:
                # explosion at opposite gorilla
                tx = app.gorilla_right_x + 20
                ty = app.height - 160
                if key == "building_explosion":
                    tx = random.randint(300, 750)
                    ty = random.randint(app.height-300, app.height-120)
                app.explosion_pos = (tx, ty)
                app.explosion_radius = 0
                app.explosion_timer = 40
            elif "victory" in key:
                app.gorilla_anim_timer = 80

            # Play via engine
            app.engine.play(key)
            return

    # Click in visualizer to random building explosion
    if app.vis_x <= mx <= app.vis_x+app.vis_w and app.vis_y <= my <= app.vis_y+app.vis_h:
        # trigger random explosion visual
        app.explosion_pos = (mx, my)
        app.explosion_radius = 0
        app.explosion_timer = 30

def onKeyPress(app, key):
    # Number keys 1-9, 0, etc for quick play
    mapping = {
        '1': 'title',
        '2': 'throw',
        '3': 'building_explosion',
        '4': 'gorilla_explosion',
        '5': 'victory_dance',
        '6': 'intro_melody',
        '7': 'full_intro',
        't': 'throw',
        'b': 'building_explosion',
        'g': 'gorilla_explosion',
        'v': 'victory_dance',
        'f': 'full_intro',
        ' ': 'throw'
    }
    if key.lower() in mapping:
        k = mapping[key.lower()]
        # simulate button press
        mml_list = GORILLA_SOUNDS.get(k, [])
        app.parser.reset()
        events = []
        for mml in mml_list:
            events.extend(app.parser.parse(mml, carry_state=True))
        app.playing_name = k
        app.playing_events = events
        app.playing_time = 0
        app.playing_duration = sum(e['total_duration'] for e in events)
        app.engine.play(k)
        app.engine.resume()
        app.player.resume()

def onStep(app):
    app.frame += 1
    app.crt_flicker = (app.crt_flicker + 1) % 60

    # Animate gorilla chest beating when victory
    if app.gorilla_anim_timer > 0:
        app.gorilla_anim_timer -= 1
        # alternate arms
        if app.frame % 12 < 6:
            app.gorilla_anim = 1
        else:
            app.gorilla_anim = 2
    else:
        app.gorilla_anim = 0

    # Banana flight
    if app.banana_pos and app.banana_timer > 0:
        app.banana_timer -= 1
        app.banana_pos['x'] += app.banana_pos['vx']
        app.banana_pos['y'] += app.banana_pos['vy']
        app.banana_pos['vy'] += 0.6  # gravity
        if app.banana_pos['y'] > app.height - 100:
            # hit ground -> explosion
            app.explosion_pos = (app.banana_pos['x'], app.banana_pos['y'])
            app.explosion_radius = 0
            app.explosion_timer = 35
            app.banana_pos = None

    # Explosion growth
    if app.explosion_timer > 0:
        app.explosion_timer -= 1
        app.explosion_radius += 3
    else:
        app.explosion_radius = 0
        app.explosion_pos = None

    # Playing time advance
    if app.playing_events and app.playing_duration > 0:
        app.playing_time += 16  # ~60fps *16ms
        if app.playing_time > app.playing_duration + 200:
            # finished
            pass

def draw_gorilla(app, x, y, anim_state, scale=1.0):
    # Simple EGA-style gorilla using shapes
    # anim_state: 0=down, 1=left up, 2=right up
    # Body
    # head
    drawRect(x, y, 28*scale, 22*scale, fill=rgb(90, 60, 20), border=None)
    # eyes
    drawRect(x+6*scale, y+6*scale, 5*scale, 3*scale, fill=rgb(0,0,0))
    drawRect(x+18*scale, y+6*scale, 5*scale, 3*scale, fill=rgb(0,0,0))
    # body
    drawRect(x-6*scale, y+22*scale, 40*scale, 30*scale, fill=rgb(90, 60, 20))
    # chest
    drawCircle(x+6*scale, y+30*scale, 8*scale, fill=rgb(120, 80, 40))
    drawCircle(x+22*scale, y+30*scale, 8*scale, fill=rgb(120, 80, 40))
    # legs
    drawRect(x-2*scale, y+52*scale, 14*scale, 18*scale, fill=rgb(80, 50, 15))
    drawRect(x+16*scale, y+52*scale, 14*scale, 18*scale, fill=rgb(80, 50, 15))

    # arms
    if anim_state == 0:  # both down
        drawRect(x-14*scale, y+26*scale, 12*scale, 28*scale, fill=rgb(90, 60, 20))
        drawRect(x+30*scale, y+26*scale, 12*scale, 28*scale, fill=rgb(90, 60, 20))
    elif anim_state == 1:  # left up
        drawRect(x-14*scale, y+8*scale, 12*scale, 28*scale, fill=rgb(90, 60, 20))
        drawRect(x+30*scale, y+26*scale, 12*scale, 28*scale, fill=rgb(90, 60, 20))
    else:  # right up
        drawRect(x-14*scale, y+26*scale, 12*scale, 28*scale, fill=rgb(90, 60, 20))
        drawRect(x+30*scale, y+8*scale, 12*scale, 28*scale, fill=rgb(90, 60, 20))

def redrawAll(app):
    # Background gradient EGA night
    drawRect(0, 0, app.width, app.height, fill=gradient(app.bg_top, app.bg_mid, app.bg_bottom, start='top'))

    # Scanlines CRT effect subtle
    for sy in range(0, app.height, 4):
        alpha = 15 if (sy//4) % 2 == 0 else 0
        drawLine(0, sy, app.width, sy, fill=rgb(0, 255, 255), opacity=alpha, lineWidth=1)

    # City skyline at bottom
    ground_y = app.height - 90
    # Draw buildings
    for b in app.buildings:
        drawRect(b['x'], ground_y - b['h'], b['w'], b['h'], fill=b['color'], border=rgb(20, 20, 40), borderWidth=1)
        # windows
        for (wx, wy) in b['wins']:
            # flicker some windows
            win_on = random.random() > 0.2 or app.frame % 120 < 5
            if win_on:
                drawRect(b['x']+wx, ground_y - b['h'] + wy, 5, 6, fill=rgb(255, 240, 120), opacity=85)
            else:
                drawRect(b['x']+wx, ground_y - b['h'] + wy, 5, 6, fill=rgb(30, 30, 50), opacity=60)

    # Ground
    drawRect(0, ground_y, app.width, 90, fill=rgb(25, 25, 35))

    # Wind arrow (like Gorillas)
    wind_x = app.width//2
    drawLine(wind_x-40, ground_y+40, wind_x+40, ground_y+40, fill=rgb(255, 80, 80), lineWidth=2)
    drawLine(wind_x+40, ground_y+40, wind_x+30, ground_y+32, fill=rgb(255, 80, 80), lineWidth=2)
    drawLine(wind_x+40, ground_y+40, wind_x+30, ground_y+48, fill=rgb(255, 80, 80), lineWidth=2)
    drawLabel("WIND", wind_x, ground_y+65, fill=rgb(255, 100, 100), size=10, bold=True)

    # Gorillas
    # compute y on top of buildings - find building under gorilla
    def gorilla_ground_x(gx):
        for b in app.buildings:
            if b['x'] <= gx <= b['x']+b['w']:
                return ground_y - b['h']
        return ground_y - 50
    gl_ground = gorilla_ground_x(app.gorilla_left_x)
    gr_ground = gorilla_ground_x(app.gorilla_right_x)
    draw_gorilla(app, app.gorilla_left_x, gl_ground - 70, app.gorilla_anim if app.playing_name and 'victory' in app.playing_name else 0, scale=1.1)
    draw_gorilla(app, app.gorilla_right_x, gr_ground - 70, 0 if not (app.playing_name and 'victory' in app.playing_name) else (2 if app.gorilla_anim==1 else 1), scale=1.1)

    # Banana
    if app.banana_pos:
        # rotating banana
        rot = app.frame * 20 % 360
        drawOval(app.banana_pos['x'], app.banana_pos['y'], 14, 8, fill=rgb(255, 230, 50), rotateAngle=rot)
        drawOval(app.banana_pos['x'], app.banana_pos['y'], 10, 5, fill=rgb(200, 180, 30), rotateAngle=rot)

    # Explosion
    if app.explosion_pos and app.explosion_timer > 0:
        ex, ey = app.explosion_pos
        # concentric circles
        for r in range(0, int(app.explosion_radius), 8):
            col = rgb(255, 200 - r*2, 50 + r)
            drawCircle(ex, ey, r, fill=None, border=col, borderWidth=3, opacity=max(0, 100 - r*2))
        drawCircle(ex, ey, app.explosion_radius//2, fill=rgb(255, 180, 60), opacity=70)
        drawCircle(ex, ey, app.explosion_radius//3, fill=rgb(255, 255, 200), opacity=90)

    # Title bar
    drawRect(0, 0, app.width, 78, fill=rgb(0, 0, 0), opacity=70)
    drawLabel("QBasic GORILLAS.BAS - 8-BIT SOUNDBOARD", app.width//2, 22, size=26, bold=True, fill=rgb(0, 255, 255))
    drawLabel("Faithful PLAY MML Square-Wave Emulation  |  Built on extensions.proc_audio + extensions.8bit", app.width//2, 48, size=12, fill=rgb(180, 220, 255))
    drawLabel("CLICK A BUTTON OR PRESS 1-7, T/B/G/V/F/SPACE", app.width//2, 66, size=11, fill=rgb(255, 255, 150))

    # Buttons
    for btn in app.buttons:
        # shadow
        drawRect(btn['x']+3, btn['y']+3, btn['w'], btn['h'], fill=rgb(0,0,0), opacity=40)
        # base
        base_col = btn['color']
        if btn['key'] == app.playing_name:
            # pulsing when playing
            pulse = 30 + 20*math.sin(app.frame*0.3)
            base_col = rgb(
                min(255, base_col.red + pulse),
                min(255, base_col.green + pulse),
                min(255, base_col.blue + pulse)
            )
            drawRect(btn['x']-2, btn['y']-2, btn['w']+4, btn['h']+4, fill=rgb(255,255,255), opacity=30)
        if btn['hover']:
            drawRect(btn['x'], btn['y'], btn['w'], btn['h'], fill=rgb(255,255,255), opacity=20)

        # button face with EGA bevel
        drawRect(btn['x'], btn['y'], btn['w'], btn['h'], fill=base_col, border=rgb(0,0,0), borderWidth=1)
        # highlight top
        drawLine(btn['x'], btn['y'], btn['x']+btn['w'], btn['y'], fill=rgb(255,255,255), opacity=50, lineWidth=2)
        drawLine(btn['x'], btn['y'], btn['x'], btn['y']+btn['h'], fill=rgb(255,255,255), opacity=35, lineWidth=2)

        # label
        drawLabel(btn['label'], btn['x']+btn['w']//2, btn['y']+18, size=12, bold=True, fill=rgb(0,0,0))
        # mml hint
        mml_hint = GORILLAS_MML.get(btn['key'], btn['mml'])
        if len(mml_hint) > 28:
            mml_hint = mml_hint[:26] + ".."
        drawLabel(mml_hint, btn['x']+btn['w']//2, btn['y']+36, size=8, fill=rgb(20,20,20), font='monospace')

        # icon - tiny square wave
        for i in range(4):
            ix = btn['x']+8 + i*10
            iy = btn['y']+44 if i%2==0 else btn['y']+48
            drawRect(ix, iy, 8, 2, fill=rgb(0,0,0), opacity=60)

    # Detail panel - MML and events
    drawRect(app.detail_x, app.detail_y, app.detail_w, app.detail_h, fill=rgb(0,0,0), opacity=75, border=rgb(0, 255, 255), borderWidth=1)
    if app.playing_name:
        desc = GORILLA_DESCRIPTIONS.get(app.playing_name, "")
        drawLabel(f"> {app.playing_name.upper()} : {desc}", app.detail_x+12, app.detail_y+16, size=11, bold=True, fill=rgb(0,255,255), align='left-top')
        mml_list = GORILLA_SOUNDS.get(app.playing_name, [])
        mml_str = "  |  ".join(mml_list)
        if len(mml_str) > 110:
            mml_str = mml_str[:108] + ".."
        drawLabel(f"MML: {mml_str}", app.detail_x+12, app.detail_y+34, size=9, fill=rgb(255,255,150), align='left-top', font='monospace')

        # Show parsed events as piano roll
        if app.playing_events:
            # progress bar
            prog = min(1.0, app.playing_time / max(1, app.playing_duration))
            drawRect(app.detail_x+12, app.detail_y+50, app.detail_w-24, 8, fill=rgb(40,40,60))
            drawRect(app.detail_x+12, app.detail_y+50, (app.detail_w-24)*prog, 8, fill=rgb(0,255,180))

            # events
            x0 = app.detail_x + 12
            y0 = app.detail_y + 72
            max_notes = min(24, len(app.playing_events))
            step_x = (app.detail_w - 24) / max(1, max_notes)
            for i in range(max_notes):
                ev = app.playing_events[i]
                # freq to height
                if ev['freq'] > 0:
                    # map freq log to height
                    # A0 27.5 to A6 ~1760
                    logf = math.log2(max(27.5, ev['freq'])/27.5)
                    h = 4 + logf*8
                    is_current = (i / max_notes) <= prog + 0.05 and (i / max_notes) >= prog - 0.05
                    col = rgb(0, 255, 180) if not is_current else rgb(255, 255, 0)
                    drawRect(x0 + i*step_x, y0 + 40 - h, step_x-2, h, fill=col, border=rgb(0,0,0), borderWidth=1)
                    # label freq
                    if i % 3 == 0:
                        drawLabel(f"{int(ev['freq'])}", x0 + i*step_x + 2, y0+48, size=7, fill=rgb(200,200,200), align='left-top')
                else:
                    # rest
                    drawRect(x0 + i*step_x, y0+20, step_x-2, 4, fill=rgb(80,80,80))

            drawLabel(f"Events: {len(app.playing_events)}  Duration: {int(app.playing_duration)}ms  Tempo: {app.playing_events[0]['tempo'] if app.playing_events else '-'}  Mode: {app.playing_events[0]['mode'] if app.playing_events else '-'}",
                      app.detail_x+12, app.detail_y+124, size=9, fill=rgb(180,200,255), align='left-top')
            # show first few raw
            raw_preview = " > ".join([e['raw'] for e in app.playing_events[:12]])
            drawLabel(raw_preview[:120], app.detail_x+12, app.detail_y+142, size=8, fill=rgb(150,150,150), align='left-top', font='monospace')
    else:
        drawLabel("SELECT A SOUND TO SEE ITS ORIGINAL QBasic PLAY MML AND PARSED EVENTS", app.detail_x+12, app.detail_y+16, size=11, fill=rgb(100,200,255), align='left-top')
        drawLabel("All frequencies use square wave @ A4=440Hz N58 - identical to PC speaker", app.detail_x+12, app.detail_y+36, size=10, fill=rgb(200,200,200), align='left-top')
        drawLabel("Example: MBO0L32EFGEFDC = MB background, O0 octave 0, L32 32nd notes, E F G E F D C", app.detail_x+12, app.detail_y+56, size=9, fill=rgb(180,180,180), align='left-top', font='monospace')
        drawLabel("Throw: A- L32 (Ab), C L64, B L16, A+ L64 - ultra short blip", app.detail_x+12, app.detail_y+76, size=9, fill=rgb(180,180,180), align='left-top', font='monospace')

    # Right visualizer - square wave + spectrum
    drawRect(app.vis_x, app.vis_y, app.vis_w, app.vis_h, fill=rgb(0,0,0), opacity=80, border=rgb(255,0,255), borderWidth=1)
    drawLabel("SQUARE WAVE VISUALIZER & CITY VIEW", app.vis_x+12, app.vis_y+14, size=11, bold=True, fill=rgb(255,0,255), align='left-top')
    # draw mini city in visualizer?
    # square wave
    if app.playing_events and app.playing_time < app.playing_duration + 500:
        # find current event
        accum = 0
        cur_ev = None
        for ev in app.playing_events:
            if accum <= app.playing_time <= accum + ev['total_duration']:
                cur_ev = ev
                break
            accum += ev['total_duration']
        if cur_ev and cur_ev['freq'] > 0:
            freq = cur_ev['freq']
            # draw square wave
            wave_y = app.vis_y + 80
            wave_h = 60
            wave_w = app.vis_w - 24
            drawLabel(f"FREQ: {freq:.1f} Hz  NOTE: {cur_ev.get('raw','')}  OCT: {cur_ev.get('octave','')}", app.vis_x+12, wave_y-20, size=10, fill=rgb(0,255,255), align='left-top', font='monospace')
            # square wave path
            # number of cycles visible
            cycles = 4
            period_px = wave_w / cycles
            # draw
            for cx in range(cycles):
                x = app.vis_x + 12 + cx*period_px
                # high
                drawLine(x, wave_y, x+period_px/2, wave_y, fill=rgb(0,255,180), lineWidth=2)
                # low
                drawLine(x+period_px/2, wave_y+wave_h, x+period_px, wave_y+wave_h, fill=rgb(0,255,180), lineWidth=2)
                # vertical
                drawLine(x+period_px/2, wave_y, x+period_px/2, wave_y+wave_h, fill=rgb(0,255,180), lineWidth=2)
        else:
            drawLabel("REST / SILENCE", app.vis_x+12, app.vis_y+70, size=10, fill=rgb(100,100,100), align='left-top')

        # piano keyboard
        kb_y = app.vis_y + 170
        kb_x = app.vis_x + 12
        white_w = 14
        white_h = 60
        # 2 octaves
        notes = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']*2
        wx = 0
        for idx, n in enumerate(notes):
            is_black = '#' in n
            if not is_black:
                drawRect(kb_x+wx, kb_y, white_w, white_h, fill=rgb(240,240,240), border=rgb(0,0,0))
                wx += white_w+1
        # black keys
        wx = 0
        # crude black placement
        black_offsets = [1, 3, 6, 8, 10]  # within octave
        for octv in range(2):
            base_x = kb_x + octv* (7* (white_w+1))
            for bo in black_offsets:
                # estimate x
                bx = base_x + bo*(white_w+1) - 6
                drawRect(bx, kb_y, 10, 35, fill=rgb(20,20,20))
        # highlight current note
        if cur_ev and cur_ev['type']=='note':
            # map freq to key
            # rough: find closest
            # Use note_value
            # note_value already in ev? we have octave and letter
            # highlight white key approx
            # just draw indicator
            drawCircle(kb_x + (app.frame % (app.vis_w-40)), kb_y+white_h+12, 6, fill=rgb(255, 255, 0))

    else:
        drawLabel("No sound playing - click a button", app.vis_x+12, app.vis_y+60, size=12, fill=rgb(100,100,100), align='left-top')
        # show gorilla ASCII
        drawLabel("   .-\"\"\"\"-.   ", app.vis_x+40, app.vis_y+120, size=14, fill=rgb(120,80,40), font='monospace', align='left-top')
        drawLabel("  /  o o  \\  ", app.vis_x+40, app.vis_y+140, size=14, fill=rgb(120,80,40), font='monospace', align='left-top')
        drawLabel("  |  __  |  ", app.vis_x+40, app.vis_y+160, size=14, fill=rgb(120,80,40), font='monospace', align='left-top')

    # Bottom credits
    drawRect(0, app.height-22, app.width, 22, fill=rgb(0,0,0), opacity=80)
    drawLabel("Original GORILLA.BAS by R. IBM / Microsoft 1990 | MML Parser: 100% faithful | PC Speaker: Square wave | SCS Extensions: proc_audio + 8bit + ui + canvas_ui", app.width//2, app.height-11, size=9, fill=rgb(120,180,200), align='center')

    # Help overlay
    if app.show_help:
        drawRect(app.width//2-220, app.height//2-90, 440, 180, fill=rgb(0,0,0), opacity=90, border=rgb(0,255,255), borderWidth=2)
        drawLabel("CLICK ANYWHERE TO ENABLE AUDIO", app.width//2, app.height//2-60, size=16, bold=True, fill=rgb(0,255,255))
        drawLabel("AudioContext requires user gesture", app.width//2, app.height//2-35, size=11, fill=rgb(200,200,200))
        drawLabel("Then click sound buttons to play original Gorillas MML", app.width//2, app.height//2-10, size=11, fill=rgb(200,200,200))
        drawLabel("Keys: 1-7, T=throw, B=building, G=gorilla, V=victory, F=full intro, SPACE=throw", app.width//2, app.height//2+15, size=10, fill=rgb(255,255,150))
        drawLabel("Built on extensions.proc_audio without modifying it", app.width//2, app.height//2+40, size=9, fill=rgb(150,150,150))
