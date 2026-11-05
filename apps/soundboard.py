
"""
apps/soundboard.py - QBasic Gorillas 8-Bit Soundboard
EVENT-DRIVEN ONLY - No timeouts, only onended events + currentTime
1050x700 SCS app - imports extensions/8bit.py
"""

from scs import *
import importlib
import math
import random

# Import 8bit extension - digit module requires importlib
try:
    eightbit = importlib.import_module('extensions.8bit')
    QBasicMMLParser = eightbit.QBasicMMLParser
    EightBitAudioEngine = eightbit.EightBitAudioEngine
    GORILLAS_MML = eightbit.GORILLAS_MML
    GORILLA_SOUNDS = eightbit.GORILLA_SOUNDS
    GORILLA_DESCRIPTIONS = eightbit.GORILLA_DESCRIPTIONS
    HAS_8BIT = True
except Exception as e:
    print(f"8bit extension failed: {e}")
    HAS_8BIT = False
    # Fallback MML so UI still works
    GORILLAS_MML = {
        "title_1812": "MBT160O1L8CDEDCDL4ECC",
        "throw": "MBo0L32A-L64CL16BL64A+",
        "building_explosion": "MBO0L32EFGEFDC",
        "gorilla_explosion": "MBO0L16EFGEFDC",
        "victory_single": "MFO0L32EFGEFDC",
        "intro_fanfare": "T160O0L32EFGEFDC",
        "intro_part1": "t120o1l16b9n0baan0bn0bn0baaan0b9n0baan0b",
        "intro_part2": "o2l16e-9n0e-d-d-n0e-n0e-n0e-d-d-d-n0e-9n0e-d-d-n0e-",
        "intro_part3": "o2l16g-9n0g-een0g-n0g-n0g-eeen0g-9n0g-een0g-",
        "intro_part4": "o2l16b9n0baan0g-n0g-n0g-eeen0o1b9n0baan0b",
    }
    GORILLA_SOUNDS = {
        "title": [GORILLAS_MML["title_1812"]],
        "throw": [GORILLAS_MML["throw"]],
        "building_explosion": [GORILLAS_MML["building_explosion"]],
        "gorilla_explosion": [GORILLAS_MML["gorilla_explosion"]],
        "victory_single": [GORILLAS_MML["victory_single"]],
        "victory_dance": [GORILLAS_MML["victory_single"]]*8,
        "intro_part1": [GORILLAS_MML["intro_part1"]],
        "intro_part2": [GORILLAS_MML["intro_part2"]],
        "intro_part3": [GORILLAS_MML["intro_part3"]],
        "intro_part4": [GORILLAS_MML["intro_part4"]],
        "intro_melody": [GORILLAS_MML["intro_part1"],GORILLAS_MML["intro_part2"],GORILLAS_MML["intro_part3"],GORILLAS_MML["intro_part4"]],
        "intro_fanfare_8x": [GORILLAS_MML["intro_fanfare"]]*8,
        "full_intro": [GORILLAS_MML["intro_part1"],GORILLAS_MML["intro_part2"],GORILLAS_MML["intro_part3"],GORILLAS_MML["intro_part4"]]+[GORILLAS_MML["intro_fanfare"]]*8,
    }
    GORILLA_DESCRIPTIONS = {k: k for k in GORILLA_SOUNDS}
    QBasicMMLParser = None
    EightBitAudioEngine = None

SOUND_KEYS = [
    ("title", "TITLE 1812"),
    ("throw", "THROW"),
    ("building_explosion", "BLDG BOOM"),
    ("gorilla_explosion", "GORILLA BOOM"),
    ("victory_single", "VICTORY NOTE"),
    ("victory_dance", "VICTORY DANCE"),
    ("intro_part1", "INTRO P1 - Bass"),
    ("intro_part2", "INTRO P2 - Eb/D-"),
    ("intro_part3", "INTRO P3 - G-/E"),
    ("intro_part4", "INTRO P4 - B/A/G-"),
    ("intro_melody", "INTRO MELODY"),
    ("intro_fanfare_8x", "FANFARE 8X"),
    ("full_intro", "FULL INTRO"),
]

def make_city_buildings(width, count=18):
    buildings = []
    x = 0
    slope = random.randint(1, 6)
    new_ht = 15 if slope==1 else 130 if slope==2 else 50
    inc = 8 if slope==1 else -8 if slope==2 else 0
    while x < width and len(buildings) < count:
        bw = random.randint(35, 70)
        if slope in (1,2):
            new_ht += inc
        elif slope in (3,4,5):
            new_ht += -4 if x > width//2 else 4
        bh = max(30, min(220, new_ht + random.randint(-40,40)))
        # color tuples, rgb made later in redraw to avoid white-screen at import
        base_col = random.choice([(40,40,80),(50,70,120),(60,50,90),(35,60,100)])
        wins = []
        for wx in range(5, bw-8, 12):
            for wy in range(10, int(bh)-12, 16):
                if random.random() > 0.3:
                    wins.append((wx, wy))
        buildings.append({'x':x,'w':bw,'h':bh,'base_color':base_col,'wins':wins})
        x += bw + 4
    return buildings

def now_audio_time(app):
    try:
        ctx = app.player.ctx
        if ctx:
            return ctx.currentTime
    except:
        pass
    return app.frame * 0.016

def dispatch_event(app, event_name, payload=None):
    handler = getattr(app, f'on_{event_name}', None)
    if handler:
        handler(payload)

def onAppStart(app):
    app.setMaxShapeCount(5000)
    app.buildings = make_city_buildings(1050, 22)
    app.gorilla_left_x = 90
    app.gorilla_right_x = 880
    app.gorilla_anim = 0
    app.playing_name = None
    app.playing_events = []
    app.playing_start_time = None
    app.playing_duration = 0

    app.banana_event = None
    app.explosion_event = None
    app.victory_event = None
    app.crt_flicker = 0
    app.frame = 0
    app.show_help = True

    # Audio
    if HAS_8BIT and EightBitAudioEngine:
        app.engine = EightBitAudioEngine(quality="high")
        app.parser = QBasicMMLParser()
        app.player = app.engine.player
    else:
        app.engine = None
        app.parser = None
        app.player = None

    # Buttons - colors created here with rgb() safe after app start
    palette = [
        rgb(255,220,100), rgb(120,220,255), rgb(255,150,100), rgb(255,90,90),
        rgb(150,255,150), rgb(100,255,180), rgb(180,180,255), rgb(200,160,255),
        rgb(255,160,230), rgb(255,200,120), rgb(140,240,255), rgb(255,255,150), rgb(255,255,255)
    ]
    app.buttons = []
    cols = 4
    btn_w = 230
    btn_h = 52
    start_x = 30
    start_y = 110
    gap_x = 16
    gap_y = 12
    for idx, (key,label) in enumerate(SOUND_KEYS):
        r = idx // cols
        c = idx % cols
        x = start_x + c*(btn_w+gap_x)
        y = start_y + r*(btn_h+gap_y)
        col = palette[idx % len(palette)]
        mml = GORILLA_SOUNDS.get(key, [""])[0] if len(GORILLA_SOUNDS.get(key,[]))==1 else f"{len(GORILLA_SOUNDS.get(key,[]))} phrases"
        app.buttons.append({'key':key,'label':label,'x':x,'y':y,'w':btn_w,'h':btn_h,'color':col,'hover':False,'mml':mml})

    app.detail_x = 30
    app.detail_y = 110 + 4*(btn_h+gap_y) + 18
    app.detail_w = 4*(btn_w+gap_x) - gap_x
    app.detail_h = 170

    app.vis_x = start_x + 4*(btn_w+gap_x) + 20
    app.vis_y = 110
    app.vis_w = 1050 - app.vis_x - 30
    app.vis_h = 580

    def on_audio_ended(event):
        app.playing_name = None
        app.playing_events = []
        app.playing_start_time = None
        app.victory_event = None

    def on_throw_launched(payload):
        app.banana_event = {
            'x0': payload['x0'], 'y0': payload['y0'],
            'vx': 8 + random.uniform(-1,1), 'vy': -12,
            'startTime': now_audio_time(app),
            'gravity': 0.6*60
        }

    def on_impact(payload):
        app.banana_event = None
        app.explosion_event = {'x':payload['x'],'y':payload['y'],'startTime':now_audio_time(app)}

    def on_victory_started(payload):
        app.victory_event = {'startTime': now_audio_time(app)}
        app.gorilla_anim = 1

    app.on_audio_ended = on_audio_ended
    app.on_throw_launched = on_throw_launched
    app.on_impact = on_impact
    app.on_victory_started = on_victory_started

def onMouseMove(app, mx, my):
    for btn in app.buttons:
        btn['hover'] = (btn['x'] <= mx <= btn['x']+btn['w'] and btn['y'] <= my <= btn['y']+btn['h'])

def trigger_sound(app, key):
    if app.engine:
        app.engine.resume()
        app.player.resume()
    app.show_help = False

    mml_list = GORILLA_SOUNDS.get(key, [])
    if app.parser:
        app.parser.reset()
        events = []
        for mml in mml_list:
            events.extend(app.parser.parse(mml, carry_state=True))
    else:
        events = []

    app.playing_name = key
    app.playing_events = events
    app.playing_start_time = now_audio_time(app)
    app.playing_duration = sum(e['total_duration'] for e in events)/1000.0 if events else 1.0

    def handle_audio_complete(evt):
        dispatch_event(app, 'audio_ended', evt)

    if app.engine:
        app.engine.play(key, on_complete=handle_audio_complete)
    else:
        # No audio engine, still trigger visual events
        pass

    if key == "throw":
        dispatch_event(app, 'throw_launched', {'x0': app.gorilla_left_x+30, 'y0': app.height-180})
    elif "explosion" in key:
        tx = app.gorilla_right_x+20
        ty = app.height-160
        if key == "building_explosion":
            tx = random.randint(300,750)
            ty = random.randint(app.height-300, app.height-120)
        dispatch_event(app, 'impact', {'x':tx,'y':ty})
    elif "victory" in key:
        dispatch_event(app, 'victory_started', {})

def onMousePress(app, mx, my):
    if app.engine:
        app.engine.resume()
        if app.player:
            app.player.resume()
    app.show_help = False
    for btn in app.buttons:
        if btn['x'] <= mx <= btn['x']+btn['w'] and btn['y'] <= my <= btn['y']+btn['h']:
            trigger_sound(app, btn['key'])
            return
    if app.vis_x <= mx <= app.vis_x+app.vis_w and app.vis_y <= my <= app.vis_y+app.vis_h:
        dispatch_event(app, 'impact', {'x':mx,'y':my})
        if app.engine:
            app.engine.play('building_explosion', on_complete=lambda e: dispatch_event(app,'audio_ended',e))

def onKeyPress(app, key):
    mapping = {
        '1':'title','2':'throw','3':'building_explosion','4':'gorilla_explosion',
        '5':'victory_dance','6':'intro_melody','7':'full_intro',
        't':'throw','b':'building_explosion','g':'gorilla_explosion',
        'v':'victory_dance','f':'full_intro',' ':'throw'
    }
    if key.lower() in mapping:
        trigger_sound(app, mapping[key.lower()])

def onStep(app):
    app.frame += 1
    app.crt_flicker = (app.crt_flicker + 1) % 60
    current = now_audio_time(app)

    if app.banana_event:
        elapsed = current - app.banana_event['startTime']
        t_frames = elapsed * 60.0
        x = app.banana_event['x0'] + app.banana_event['vx']*t_frames
        y = app.banana_event['y0'] + app.banana_event['vy']*t_frames + 0.5*0.6*t_frames*t_frames
        app.banana_event['x'] = x
        app.banana_event['y'] = y
        if y > app.height - 100 or x < 0 or x > app.width:
            dispatch_event(app, 'impact', {'x':x,'y':min(y, app.height-100)})

    if app.victory_event and app.playing_name and 'victory' in app.playing_name:
        elapsed = current - app.victory_event['startTime']
        app.gorilla_anim = 1 if (int(elapsed/0.2) % 2 == 0) else 2
    else:
        app.gorilla_anim = 0

    if app.explosion_event:
        elapsed = current - app.explosion_event['startTime']
        if elapsed > 1.2:
            app.explosion_event = None

def draw_gorilla(app, x, y, anim_state, scale=1.0):
    drawRect(x, y, 28*scale, 22*scale, fill=rgb(90,60,20))
    drawRect(x+6*scale, y+6*scale, 5*scale, 3*scale, fill=rgb(0,0,0))
    drawRect(x+18*scale, y+6*scale, 5*scale, 3*scale, fill=rgb(0,0,0))
    drawRect(x-6*scale, y+22*scale, 40*scale, 30*scale, fill=rgb(90,60,20))
    drawCircle(x+6*scale, y+30*scale, 8*scale, fill=rgb(120,80,40))
    drawCircle(x+22*scale, y+30*scale, 8*scale, fill=rgb(120,80,40))
    drawRect(x-2*scale, y+52*scale, 14*scale, 18*scale, fill=rgb(80,50,15))
    drawRect(x+16*scale, y+52*scale, 14*scale, 18*scale, fill=rgb(80,50,15))
    if anim_state == 0:
        drawRect(x-14*scale, y+26*scale, 12*scale, 28*scale, fill=rgb(90,60,20))
        drawRect(x+30*scale, y+26*scale, 12*scale, 28*scale, fill=rgb(90,60,20))
    elif anim_state == 1:
        drawRect(x-14*scale, y+8*scale, 12*scale, 28*scale, fill=rgb(90,60,20))
        drawRect(x+30*scale, y+26*scale, 12*scale, 28*scale, fill=rgb(90,60,20))
    else:
        drawRect(x-14*scale, y+26*scale, 12*scale, 28*scale, fill=rgb(90,60,20))
        drawRect(x+30*scale, y+8*scale, 12*scale, 28*scale, fill=rgb(90,60,20))

def redrawAll(app):
    # Background
    drawRect(0,0,app.width,app.height, fill=gradient(rgb(8,10,30), rgb(18,20,50), rgb(10,15,35), start='top'))
    for sy in range(0, app.height, 4):
        alpha = 15 if (sy//4) % 2 == 0 else 0
        drawLine(0, sy, app.width, sy, fill=rgb(0,255,255), opacity=alpha, lineWidth=1)

    ground_y = app.height - 90
    for b in app.buildings:
        col = rgb(b['base_color'][0], b['base_color'][1], b['base_color'][2])
        drawRect(b['x'], ground_y - b['h'], b['w'], b['h'], fill=col, border=rgb(20,20,40), borderWidth=1)
        for (wx, wy) in b['wins']:
            win_on = random.random() > 0.2 or app.frame % 120 < 5
            if win_on:
                drawRect(b['x']+wx, ground_y - b['h'] + wy, 5, 6, fill=rgb(255,240,120), opacity=85)
            else:
                drawRect(b['x']+wx, ground_y - b['h'] + wy, 5, 6, fill=rgb(30,30,50), opacity=60)

    drawRect(0, ground_y, app.width, 90, fill=rgb(25,25,35))

    # Gorillas
    def gorilla_ground_x(gx):
        for b in app.buildings:
            if b['x'] <= gx <= b['x']+b['w']:
                return ground_y - b['h']
        return ground_y - 50
    gl_ground = gorilla_ground_x(app.gorilla_left_x)
    gr_ground = gorilla_ground_x(app.gorilla_right_x)
    draw_gorilla(app, app.gorilla_left_x, gl_ground - 70, app.gorilla_anim if app.playing_name and 'victory' in app.playing_name else 0, scale=1.1)
    draw_gorilla(app, app.gorilla_right_x, gr_ground - 70, 0 if not (app.playing_name and 'victory' in app.playing_name) else (2 if app.gorilla_anim==1 else 1), scale=1.1)

    if app.banana_event and 'x' in app.banana_event:
        rot = app.frame * 20 % 360
        drawOval(app.banana_event['x'], app.banana_event['y'], 14, 8, fill=rgb(255,230,50), rotateAngle=rot)
        drawOval(app.banana_event['x'], app.banana_event['y'], 10, 5, fill=rgb(200,180,30), rotateAngle=rot)

    if app.explosion_event:
        elapsed = now_audio_time(app) - app.explosion_event['startTime']
        radius = elapsed * 90
        ex, ey = app.explosion_event['x'], app.explosion_event['y']
        for r in range(0, int(radius), 8):
            col = rgb(255, 200 - r*2, 50 + r)
            drawCircle(ex, ey, r, fill=None, border=col, borderWidth=3, opacity=max(0, 100 - r*2))
        drawCircle(ex, ey, radius//2, fill=rgb(255,180,60), opacity=70)
        drawCircle(ex, ey, radius//3, fill=rgb(255,255,200), opacity=90)

    # Header
    drawRect(0,0,app.width,78, fill=rgb(0,0,0), opacity=70)
    drawLabel("QBasic GORILLAS.BAS - 8-BIT SOUNDBOARD - EVENT DRIVEN", app.width//2, 22, size=22, bold=True, fill=rgb(0,255,255))
    drawLabel("Built on extensions.proc_audio + extensions.8bit | No timeouts, only onended + currentTime", app.width//2, 48, size=11, fill=rgb(180,220,255))
    drawLabel("CLICK A BUTTON OR PRESS 1-7, T/B/G/V/F/SPACE", app.width//2, 66, size=11, fill=rgb(255,255,150))

    # Buttons
    for btn in app.buttons:
        drawRect(btn['x']+3, btn['y']+3, btn['w'], btn['h'], fill=rgb(0,0,0), opacity=40)
        base_col = btn['color']
        if btn['key'] == app.playing_name:
            pulse = 30 + 20*math.sin(app.frame*0.3)
            base_col = rgb(min(255, base_col.red + pulse), min(255, base_col.green + pulse), min(255, base_col.blue + pulse))
            drawRect(btn['x']-2, btn['y']-2, btn['w']+4, btn['h']+4, fill=rgb(255,255,255), opacity=30)
        if btn['hover']:
            drawRect(btn['x'], btn['y'], btn['w'], btn['h'], fill=rgb(255,255,255), opacity=20)
        drawRect(btn['x'], btn['y'], btn['w'], btn['h'], fill=base_col, border=rgb(0,0,0), borderWidth=1)
        drawLine(btn['x'], btn['y'], btn['x']+btn['w'], btn['y'], fill=rgb(255,255,255), opacity=50, lineWidth=2)
        drawLine(btn['x'], btn['y'], btn['x'], btn['y']+btn['h'], fill=rgb(255,255,255), opacity=35, lineWidth=2)
        drawLabel(btn['label'], btn['x']+btn['w']//2, btn['y']+18, size=12, bold=True, fill=rgb(0,0,0))
        mml_hint = GORILLAS_MML.get(btn['key'], btn['mml'])
        if len(mml_hint) > 28:
            mml_hint = mml_hint[:26] + ".."
        drawLabel(mml_hint, btn['x']+btn['w']//2, btn['y']+36, size=8, fill=rgb(20,20,20), font='monospace')

    # Detail
    drawRect(app.detail_x, app.detail_y, app.detail_w, app.detail_h, fill=rgb(0,0,0), opacity=75, border=rgb(0,255,255), borderWidth=1)
    if app.playing_name:
        desc = GORILLA_DESCRIPTIONS.get(app.playing_name, "")
        drawLabel(f"> {app.playing_name.upper()} : {desc}", app.detail_x+12, app.detail_y+16, size=11, bold=True, fill=rgb(0,255,255), align='left-top')
        mml_list = GORILLA_SOUNDS.get(app.playing_name, [])
        mml_str = "  |  ".join(mml_list)
        if len(mml_str) > 110:
            mml_str = mml_str[:108] + ".."
        drawLabel(f"MML: {mml_str}", app.detail_x+12, app.detail_y+34, size=9, fill=rgb(255,255,150), align='left-top', font='monospace')
        if app.playing_events:
            elapsed = 0
            if app.playing_start_time is not None:
                elapsed = now_audio_time(app) - app.playing_start_time
            prog = min(1.0, elapsed / max(0.001, app.playing_duration))
            drawRect(app.detail_x+12, app.detail_y+50, app.detail_w-24, 8, fill=rgb(40,40,60))
            drawRect(app.detail_x+12, app.detail_y+50, (app.detail_w-24)*prog, 8, fill=rgb(0,255,180))
            x0 = app.detail_x + 12
            y0 = app.detail_y + 72
            max_notes = min(24, len(app.playing_events))
            step_x = (app.detail_w - 24) / max(1, max_notes)
            for i in range(max_notes):
                ev = app.playing_events[i]
                if ev['freq'] > 0:
                    logf = math.log2(max(27.5, ev['freq'])/27.5)
                    h = 4 + logf*8
                    is_current = (i / max_notes) <= prog + 0.05 and (i / max_notes) >= prog - 0.05
                    col = rgb(0,255,180) if not is_current else rgb(255,255,0)
                    drawRect(x0 + i*step_x, y0 + 40 - h, step_x-2, h, fill=col, border=rgb(0,0,0), borderWidth=1)
            drawLabel(f"Events: {len(app.playing_events)}  Duration: {int(app.playing_duration*1000)}ms", app.detail_x+12, app.detail_y+124, size=9, fill=rgb(180,200,255), align='left-top')
    else:
        drawLabel("SELECT A SOUND - All audio scheduled via currentTime + onended", app.detail_x+12, app.detail_y+16, size=10, fill=rgb(100,200,255), align='left-top')
        drawLabel("No timeouts - only events: throw -> impact -> explosion", app.detail_x+12, app.detail_y+36, size=10, fill=rgb(255,255,100), align='left-top')
        drawLabel("Example: MBO0L32EFGEFDC = MB background, O0 octave 0, L32 32nd notes", app.detail_x+12, app.detail_y+56, size=9, fill=rgb(180,180,180), align='left-top', font='monospace')

    # Visualizer
    drawRect(app.vis_x, app.vis_y, app.vis_w, app.vis_h, fill=rgb(0,0,0), opacity=80, border=rgb(255,0,255), borderWidth=1)
    drawLabel("SQUARE WAVE VISUALIZER", app.vis_x+12, app.vis_y+14, size=11, bold=True, fill=rgb(255,0,255), align='left-top')
    if app.playing_events and app.playing_start_time is not None:
        current = now_audio_time(app)
        elapsed = current - app.playing_start_time
        accum = 0
        cur_ev = None
        for ev in app.playing_events:
            if accum <= elapsed <= accum + ev['total_duration']/1000.0:
                cur_ev = ev
                break
            accum += ev['total_duration']/1000.0
        if cur_ev and cur_ev['freq'] > 0:
            freq = cur_ev['freq']
            wave_y = app.vis_y + 80
            wave_h = 60
            wave_w = app.vis_w - 24
            drawLabel(f"FREQ: {freq:.1f} Hz  NOTE: {cur_ev.get('raw','')}  t={elapsed:.2f}s", app.vis_x+12, wave_y-20, size=10, fill=rgb(0,255,255), align='left-top', font='monospace')
            cycles = 4
            period_px = wave_w / cycles
            for cx in range(cycles):
                x = app.vis_x + 12 + cx*period_px
                drawLine(x, wave_y, x+period_px/2, wave_y, fill=rgb(0,255,180), lineWidth=2)
                drawLine(x+period_px/2, wave_y+wave_h, x+period_px, wave_y+wave_h, fill=rgb(0,255,180), lineWidth=2)
                drawLine(x+period_px/2, wave_y, x+period_px/2, wave_y+wave_h, fill=rgb(0,255,180), lineWidth=2)

    drawRect(0, app.height-22, app.width, 22, fill=rgb(0,0,0), opacity=80)
    drawLabel("Original GORILLA.BAS 1990 | EVENT-DRIVEN: ctx.currentTime + onended | No setTimeout", app.width//2, app.height-11, size=9, fill=rgb(120,180,200), align='center')

    if app.show_help:
        drawRect(app.width//2-220, app.height//2-90, 440, 180, fill=rgb(0,0,0), opacity=90, border=rgb(0,255,255), borderWidth=2)
        drawLabel("CLICK ANYWHERE TO ENABLE AUDIO", app.width//2, app.height//2-60, size=16, bold=True, fill=rgb(0,255,255))
        drawLabel("AudioContext requires user gesture", app.width//2, app.height//2-35, size=11, fill=rgb(200,200,200))
        drawLabel("Keys: 1-7, T=throw, B=building, G=gorilla, V=victory, F=full intro", app.width//2, app.height//2-10, size=10, fill=rgb(255,255,150))

def main():
    runApp(1050, 700)

main()
