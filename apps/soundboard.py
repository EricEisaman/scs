"""
apps/soundboard.py - QBasic Gorillas 8-Bit Soundboard - HIGH QUALITY TETR-LEVEL
EVENT-DRIVEN ONLY - No timeouts, only Web Audio events
1050x700 SCS app that imports extensions/8bit and demonstrates sounds in nice soundboard.
May import from ui.py and canvas_ui.py.

Fixed for SCS sandbox: no setMaxShapeCount, frame safe
All visuals event-driven: banana x=x0+vx*t, explosion radius=elapsed*90
"""

from scs import *
import importlib
import math
import random

try:
    eightbit = importlib.import_module('extensions.8bit')
    QBasicMMLParser = eightbit.QBasicMMLParser
    EightBitAudioEngine = eightbit.EightBitAudioEngine
    GORILLAS_MML = eightbit.GORILLAS_MML
    GORILLA_SOUNDS = eightbit.GORILLA_SOUNDS
    GORILLA_DESCRIPTIONS = eightbit.GORILLA_DESCRIPTIONS
    HAS_8BIT = True
except Exception as e:
    print(f"8bit load failed: {e}")
    HAS_8BIT = False
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
    GORILLA_DESCRIPTIONS = {
        "title": "Title 1812 Overture T160 O1 L8/L4",
        "throw": "Throw A- L32 C L64 B L16 A+ L64",
        "building_explosion": "Building O0 L32 E F G E F D C fast",
        "gorilla_explosion": "Gorilla O0 L16 E F G E F D C slow",
        "victory_single": "Victory single O0 L32",
        "victory_dance": "Victory 8x chest beating",
        "intro_part1": "Intro P1 O1 bass",
        "intro_part2": "Intro P2 O2 Eb/D-",
        "intro_part3": "Intro P3 O2 G-/E",
        "intro_part4": "Intro P4 B/A/G- + O1",
        "intro_melody": "Full intro melody P1-4",
        "intro_fanfare_8x": "Fanfare 8x T160",
        "full_intro": "Full intro sequence as in GorillaIntro()",
    }
    QBasicMMLParser = None
    EightBitAudioEngine = None

SOUND_KEYS = [
    ("title", "TITLE 1812"),
    ("throw", "THROW"),
    ("building_explosion", "BLDG BOOM"),
    ("gorilla_explosion", "GORILLA BOOM"),
    ("victory_single", "VICTORY NOTE"),
    ("victory_dance", "VICTORY DANCE"),
    ("intro_part1", "INTRO P1 Bass"),
    ("intro_part2", "INTRO P2 Eb/D-"),
    ("intro_part3", "INTRO P3 G-/E"),
    ("intro_part4", "INTRO P4 B/A/G-"),
    ("intro_melody", "INTRO MELODY"),
    ("intro_fanfare_8x", "FANFARE 8X"),
    ("full_intro", "FULL INTRO"),
]

def make_city_buildings_original(width):
    """Faithful to GORILLA.BAS MakeCityScape - slope logic 1-6"""
    buildings = []
    x = 0
    slope = random.randint(1,6)
    new_height = 15 if slope==1 else 130 if slope==2 else 50
    height_inc = 8 if slope==1 else -8 if slope==2 else 0
    while x < width - 40 and len(buildings) < 22:
        bw = random.randint(42, 68)
        if slope in (1,2):
            new_height += height_inc
        elif slope in (3,4,5):
            new_height += -5 if x > width//2 else 5
        new_height = max(25, min(210, new_height + random.randint(-18,18)))
        bh = new_height
        base = random.choice([(40,40,85),(50,65,110),(55,50,85),(35,55,95),(60,60,80)])
        wins = []
        for wx in range(6, bw-10, 13):
            for wy in range(12, int(bh)-14, 17):
                if random.random() > 0.3:
                    wins.append((wx, wy, random.random() > 0.5))
        buildings.append({'x':x,'w':bw,'h':bh,'base':base,'wins':wins})
        x += bw + 5
    return buildings

def now_audio_time(app):
    try:
        if hasattr(app, 'player') and app.player and hasattr(app.player, 'ctx') and app.player.ctx:
            return app.player.ctx.currentTime
    except:
        pass
    try:
        return app.frame * 0.016
    except:
        return 0

def dispatch_event(app, name, payload=None):
    h = getattr(app, f'on_{name}', None)
    if h:
        try:
            h(payload)
        except Exception as e:
            print(f"event {name} {e}")

def onAppStart(app):
    # Critical attrs FIRST - prevents white screen if later code fails
    app.width = 1050
    app.height = 700
    app.frame = 0
    app.show_help = True
    app.last_error = ""
    app.gorilla_left_x = 95
    app.gorilla_right_x = 890
    app.gorilla_anim = 0
    app.playing_name = None
    app.playing_events = []
    app.playing_start_time = None
    app.playing_duration = 0
    app.banana_event = None
    app.explosion_event = None
    app.explosion_particles = []
    app.victory_event = None
    app.sun_x = 860
    app.sun_y = 95
    app.wind = random.randint(-18,18)
    app.buildings = make_city_buildings_original(1050)

    try:
        if hasattr(app, 'setMaxShapeCount'):
            app.setMaxShapeCount(12000)
    except:
        pass

    if HAS_8BIT and EightBitAudioEngine:
        try:
            app.engine = EightBitAudioEngine(quality="high")
            app.parser = QBasicMMLParser()
            app.player = app.engine.player
        except Exception as e:
            app.last_error = f"Audio {e}"
            app.engine = None
            app.parser = None
            app.player = None
    else:
        app.engine = None
        app.parser = None
        app.player = None

    app.buttons = []
    cols = 4
    btn_w = 232
    btn_h = 56
    start_x = 28
    start_y = 106
    gap_x = 14
    gap_y = 10
    for idx, (key,label) in enumerate(SOUND_KEYS):
        r = idx // cols
        c = idx % cols
        x = start_x + c*(btn_w+gap_x)
        y = start_y + r*(btn_h+gap_y)
        mml = GORILLA_SOUNDS.get(key, [""])[0]
        if len(GORILLA_SOUNDS.get(key,[])) > 1:
            mml = f"{len(GORILLA_SOUNDS.get(key,[]))} phrases"
        app.buttons.append({'key':key,'label':label,'x':x,'y':y,'w':btn_w,'h':btn_h,'hover':False,'mml':mml,'idx':idx})

    app.detail_x = 28
    app.detail_y = 106 + 4*(btn_h+gap_y) + 16
    app.detail_w = 4*(btn_w+gap_x) - gap_x
    app.detail_h = 148
    app.vis_x = start_x + 4*(btn_w+gap_x) + 18
    app.vis_y = 106
    app.vis_w = 1050 - app.vis_x - 28
    app.vis_h = 398

    def on_audio_ended(evt):
        app.playing_name = None
        app.playing_events = []
        app.playing_start_time = None
        app.victory_event = None
        app.explosion_particles = []

    def on_throw_launched(p):
        app.banana_event = {'x0':p['x0'],'y0':p['y0'],'vx':9+random.uniform(-1,1),'vy':-13,'startTime':now_audio_time(app)}
        app.explosion_event = None
        app.explosion_particles = []

    def on_impact(p):
        app.banana_event = None
        app.explosion_event = {'x':p['x'],'y':p['y'],'startTime':now_audio_time(app)}
        parts = []
        for _ in range(24):
            ang = random.uniform(0, 2*math.pi)
            spd = random.uniform(2, 8)
            parts.append({
                'x0':p['x'],'y0':p['y'],
                'vx': math.cos(ang)*spd,
                'vy': math.sin(ang)*spd - random.uniform(1,3),
                'startTime': now_audio_time(app),
                'life': random.uniform(0.6,1.2),
                'color': random.choice([(255,200,60),(255,140,30),(255,80,20),(255,240,180)])
            })
        app.explosion_particles = parts

    def on_victory_started(p):
        app.victory_event = {'startTime': now_audio_time(app)}

    app.on_audio_ended = on_audio_ended
    app.on_throw_launched = on_throw_launched
    app.on_impact = on_impact
    app.on_victory_started = on_victory_started

def onMouseMove(app, mx, my):
    try:
        for b in app.buttons:
            b['hover'] = (b['x'] <= mx <= b['x']+b['w'] and b['y'] <= my <= b['y']+b['h'])
    except:
        pass

def trigger_sound(app, key):
    try:
        if hasattr(app, 'engine') and app.engine:
            app.engine.resume()
            if hasattr(app, 'player') and app.player:
                app.player.resume()
    except Exception as e:
        try:
            app.last_error = f"resume {e}"
        except:
            pass
    try:
        app.show_help = False
    except:
        pass
    mml_list = GORILLA_SOUNDS.get(key, [])
    events = []
    if hasattr(app, 'parser') and app.parser:
        try:
            app.parser.reset()
            for mml in mml_list:
                events.extend(app.parser.parse(mml, carry_state=True))
        except Exception as e:
            try:
                app.last_error = f"parse {e}"
            except:
                pass
    try:
        app.playing_name = key
        app.playing_events = events
        app.playing_start_time = now_audio_time(app)
        app.playing_duration = sum(e['total_duration'] for e in events)/1000.0 if events else 1.0
    except:
        pass
    def done(evt):
        dispatch_event(app, 'audio_ended', evt)
    try:
        if hasattr(app, 'engine') and app.engine:
            app.engine.play(key, on_complete=done)
    except Exception as e:
        try:
            app.last_error = f"play {e}"
        except:
            pass
    if key == "throw":
        dispatch_event(app, 'throw_launched', {'x0': app.gorilla_left_x+32, 'y0': app.height-190})
    elif "explosion" in key:
        tx = app.gorilla_right_x+20
        ty = app.height-165
        if key == "building_explosion":
            tx = random.randint(320, 760)
            ty = random.randint(app.height-310, app.height-130)
        dispatch_event(app, 'impact', {'x':tx,'y':ty})
    elif "victory" in key:
        dispatch_event(app, 'victory_started', {})

def onMousePress(app, mx, my):
    try:
        if hasattr(app, 'engine') and app.engine:
            app.engine.resume()
            if hasattr(app, 'player') and app.player:
                app.player.resume()
    except:
        pass
    try:
        app.show_help = False
    except:
        pass
    try:
        for b in app.buttons:
            if b['x'] <= mx <= b['x']+b['w'] and b['y'] <= my <= b['y']+b['h']:
                trigger_sound(app, b['key'])
                return
        if app.vis_x <= mx <= app.vis_x+app.vis_w and app.vis_y <= my <= app.vis_y+app.vis_h:
            dispatch_event(app, 'impact', {'x':mx,'y':my})
            try:
                if hasattr(app, 'engine') and app.engine:
                    app.engine.play('building_explosion', on_complete=lambda e: dispatch_event(app,'audio_ended',e))
            except:
                pass
    except Exception as e:
        try:
            app.last_error = f"mouse {e}"
        except:
            pass

def onKeyPress(app, key):
    mp = {'1':'title','2':'throw','3':'building_explosion','4':'gorilla_explosion','5':'victory_dance','6':'intro_melody','7':'full_intro','t':'throw','b':'building_explosion','g':'gorilla_explosion','v':'victory_dance','f':'full_intro',' ':'throw'}
    try:
        k = key.lower() if len(key)==1 else key
        if k in mp:
            trigger_sound(app, mp[k])
        if k == 'r':
            app.show_help = not app.show_help
        if k == 'c':
            app.buildings = make_city_buildings_original(1050)
    except:
        pass

def onStep(app):
    try:
        app.frame += 1
    except:
        try:
            app.frame = 1
        except:
            pass
    try:
        cur = now_audio_time(app)
        if hasattr(app, 'banana_event') and app.banana_event:
            el = cur - app.banana_event['startTime']
            tf = el * 60.0
            x = app.banana_event['x0'] + app.banana_event['vx']*tf
            y = app.banana_event['y0'] + app.banana_event['vy']*tf + 0.5*0.6*tf*tf
            app.banana_event['x'] = x
            app.banana_event['y'] = y
            if y > app.height - 105 or x < -20 or x > app.width+20:
                dispatch_event(app, 'impact', {'x':x,'y':min(y, app.height-105)})
        if hasattr(app, 'victory_event') and app.victory_event and hasattr(app, 'playing_name') and app.playing_name and 'victory' in app.playing_name:
            el = cur - app.victory_event['startTime']
            app.gorilla_anim = 1 if int(el/0.18) % 2 == 0 else 2
        else:
            try:
                app.gorilla_anim = 0
            except:
                pass
        if hasattr(app, 'explosion_event') and app.explosion_event:
            el = cur - app.explosion_event['startTime']
            if el > 1.3:
                app.explosion_event = None
                app.explosion_particles = []
        if hasattr(app, 'explosion_particles') and app.explosion_particles:
            cur = now_audio_time(app)
            alive = []
            for p in app.explosion_particles:
                if cur - p['startTime'] < p['life']:
                    alive.append(p)
            app.explosion_particles = alive
    except Exception as e:
        try:
            app.last_error = f"step {e}"
        except:
            pass

def draw_gorilla_ega(app, x, y, anim, scale=1.0):
    try:
        drawRect(x, y, int(28*scale), int(22*scale), fill=rgb(90,60,20), border=rgb(40,25,8), borderWidth=1)
        drawRect(x+int(5*scale), y+int(5*scale), int(6*scale), int(4*scale), fill=rgb(0,0,0))
        drawRect(x+int(17*scale), y+int(5*scale), int(6*scale), int(4*scale), fill=rgb(0,0,0))
        drawRect(x+int(6*scale), y+int(6*scale), int(2*scale), int(2*scale), fill=rgb(255,255,255))
        drawRect(x+int(18*scale), y+int(6*scale), int(2*scale), int(2*scale), fill=rgb(255,255,255))
        drawRect(x-int(6*scale), y+int(22*scale), int(40*scale), int(32*scale), fill=rgb(100,68,28), border=rgb(40,25,8), borderWidth=1)
        drawCircle(x+int(6*scale), y+int(32*scale), int(9*scale), fill=rgb(120,85,45))
        drawCircle(x+int(22*scale), y+int(32*scale), int(9*scale), fill=rgb(120,85,45))
        drawRect(x-int(2*scale), y+int(54*scale), int(14*scale), int(20*scale), fill=rgb(80,50,15))
        drawRect(x+int(16*scale), y+int(54*scale), int(14*scale), int(20*scale), fill=rgb(80,50,15))
        if anim == 0:
            drawRect(x-int(16*scale), y+int(26*scale), int(13*scale), int(30*scale), fill=rgb(90,60,20), border=rgb(40,25,8), borderWidth=1)
            drawRect(x+int(31*scale), y+int(26*scale), int(13*scale), int(30*scale), fill=rgb(90,60,20), border=rgb(40,25,8), borderWidth=1)
        elif anim == 1:
            drawRect(x-int(16*scale), y+int(10*scale), int(13*scale), int(30*scale), fill=rgb(110,75,30), border=rgb(40,25,8), borderWidth=1)
            drawRect(x+int(31*scale), y+int(26*scale), int(13*scale), int(30*scale), fill=rgb(90,60,20), border=rgb(40,25,8), borderWidth=1)
        else:
            drawRect(x-int(16*scale), y+int(26*scale), int(13*scale), int(30*scale), fill=rgb(90,60,20), border=rgb(40,25,8), borderWidth=1)
            drawRect(x+int(31*scale), y+int(10*scale), int(13*scale), int(30*scale), fill=rgb(110,75,30), border=rgb(40,25,8), borderWidth=1)
    except:
        pass

def draw_beveled_button(app, b, is_playing, is_hover):
    try:
        x,y,w,h = b['x'],b['y'],b['w'],b['h']
        idx = b['idx']
        ega_palette = [
            rgb(255,220,100), rgb(120,220,255), rgb(255,160,100), rgb(255,95,95),
            rgb(150,255,150), rgb(100,255,190), rgb(180,180,255), rgb(210,170,255),
            rgb(255,170,230), rgb(255,210,130), rgb(140,240,255), rgb(255,255,160), rgb(230,230,230)
        ]
        base = ega_palette[idx % len(ega_palette)]
        drawRect(x+3, y+3, w, h, fill=rgb(0,0,0))
        if is_playing:
            drawRect(x-2, y-2, w+4, h+4, fill=rgb(255,255,255))
            drawRect(x, y, w, h, fill=rgb(255,255,80), border=rgb(0,0,0), borderWidth=2)
        elif is_hover:
            drawRect(x, y, w, h, fill=rgb(255,255,255), border=rgb(0,0,0), borderWidth=2)
            drawRect(x+2, y+2, w-4, h-4, fill=base, border=rgb(0,0,0), borderWidth=1)
        else:
            drawRect(x, y, w, h, fill=base, border=rgb(0,0,0), borderWidth=2)
            drawLine(x, y, x+w, y, fill=rgb(255,255,255), lineWidth=2)
            drawLine(x, y, x, y+h, fill=rgb(255,255,255), lineWidth=1)
        drawLabel(b['label'], x+w//2, y+18, size=12, bold=True, fill=rgb(0,0,0))
        mml = b['mml']
        if len(mml) > 28:
            mml = mml[:26]+".."
        drawLabel(mml, x+w//2, y+38, size=8, fill=rgb(30,30,30))
    except Exception as e:
        try:
            drawRect(b['x'], b['y'], b['w'], b['h'], fill=rgb(200,200,200))
            drawLabel(b['label'], b['x']+b['w']//2, b['y']+b['h']//2, size=10, fill=rgb(0,0,0))
        except:
            pass

def redrawAll(app):
    try:
        drawRect(0,0,app.width,app.height, fill=rgb(8,12,38))
        for i in range(0, 200, 8):
            shade = 8 + i//3
            drawRect(0, i, app.width, 8, fill=rgb(shade, shade+2, 38+shade//2))
        for _ in range(30):
            try:
                sx = (app.frame*2 + _*137) % app.width
                sy = (_*59) % 180
                if sy < 160:
                    drawCircle(sx, sy, 1, fill=rgb(180,200,255))
            except:
                pass
        try:
            drawCircle(app.sun_x, app.sun_y, 28, fill=rgb(255,240,120), border=rgb(255,200,60), borderWidth=2)
            for ang in range(0,360,45):
                rad = math.radians(ang + app.frame)
                x1 = app.sun_x + math.cos(rad)*32
                y1 = app.sun_y + math.sin(rad)*32
                x2 = app.sun_x + math.cos(rad)*44
                y2 = app.sun_y + math.sin(rad)*44
                drawLine(x1, y1, x2, y2, fill=rgb(255,220,100), lineWidth=2)
        except:
            pass
        for sy in range(0, app.height, 6):
            try:
                drawLine(0, sy, app.width, sy, fill=rgb(0,30,50), lineWidth=1)
            except:
                pass
        ground_y = app.height - 90
        try:
            for b in app.buildings:
                base = b['base']
                drawRect(b['x'], ground_y - b['h'], b['w'], b['h'], fill=rgb(base[0],base[1],base[2]), border=rgb(10,10,20), borderWidth=2)
                for (wx, wy, flick) in b['wins']:
                    try:
                        on = True
                        if flick:
                            on = (app.frame + wx) % 180 > 5
                        if on:
                            drawRect(b['x']+wx, ground_y - b['h'] + wy, 6, 7, fill=rgb(255,235,120), border=rgb(60,50,20), borderWidth=1)
                        else:
                            drawRect(b['x']+wx, ground_y - b['h'] + wy, 6, 7, fill=rgb(25,25,45))
                    except:
                        pass
            drawRect(0, ground_y, app.width, 90, fill=rgb(22,22,32), border=rgb(40,40,50), borderWidth=1)
            wx = app.width//2
            drawLine(wx-45, ground_y+42, wx+45, ground_y+42, fill=rgb(255,80,80), lineWidth=3)
            try:
                wind_x = wx + app.wind*2
                drawLine(wx, ground_y+42, wind_x, ground_y+42, fill=rgb(255,255,100), lineWidth=2)
                drawLine(wind_x, ground_y+42, wind_x-8, ground_y+34, fill=rgb(255,255,100), lineWidth=2)
                drawLine(wind_x, ground_y+42, wind_x-8, ground_y+50, fill=rgb(255,255,100), lineWidth=2)
                drawLabel(f"WIND {app.wind}", wx, ground_y+68, size=10, bold=True, fill=rgb(255,120,120))
            except:
                pass
        except Exception as e:
            try:
                app.last_error = f"buildings {e}"
            except:
                pass
        try:
            def gnd_x(gx):
                for b in app.buildings:
                    if b['x'] <= gx <= b['x']+b['w']:
                        return ground_y - b['h']
                return ground_y - 50
            gl_ground = gnd_x(app.gorilla_left_x)
            gr_ground = gnd_x(app.gorilla_right_x)
            draw_gorilla_ega(app, app.gorilla_left_x, gl_ground - 74, app.gorilla_anim if app.playing_name and 'victory' in app.playing_name else 0)
            draw_gorilla_ega(app, app.gorilla_right_x, gr_ground - 74, 0 if not (app.playing_name and 'victory' in app.playing_name) else (2 if app.gorilla_anim==1 else 1))
        except:
            pass
        try:
            if hasattr(app, 'banana_event') and app.banana_event and 'x' in app.banana_event:
                cur = now_audio_time(app)
                el = cur - app.banana_event['startTime']
                for dt in [0.12, 0.08, 0.04]:
                    if el - dt > 0:
                        tf = (el - dt)*60.0
                        tx = app.banana_event['x0'] + app.banana_event['vx']*tf
                        ty = app.banana_event['y0'] + app.banana_event['vy']*tf + 0.5*0.6*tf*tf
                        sz = int(6 - dt*20)
                        if sz > 1:
                            drawCircle(int(tx), int(ty), sz, fill=rgb(255,230,80))
                drawRect(int(app.banana_event['x']), int(app.banana_event['y']), 16, 9, fill=rgb(255,235,50), border=rgb(0,0,0), borderWidth=2)
        except:
            pass
        try:
            if hasattr(app, 'explosion_event') and app.explosion_event:
                cur = now_audio_time(app)
                el = cur - app.explosion_event['startTime']
                radius = el * 95
                ex = int(app.explosion_event['x'])
                ey = int(app.explosion_event['y'])
                for r in range(0, int(radius), 10):
                    c = 255 - r*2
                    if c < 20:
                        c = 20
                    drawCircle(ex, ey, r, fill=None, border=rgb(255, c, 20), borderWidth=3)
                drawCircle(ex, ey, int(radius*0.55), fill=rgb(255,185,65))
                drawCircle(ex, ey, int(radius*0.32), fill=rgb(255,255,210))
            if hasattr(app, 'explosion_particles') and app.explosion_particles:
                for p in app.explosion_particles:
                    cur = now_audio_time(app)
                    el = cur - p['startTime']
                    tf = el * 60.0
                    x = p['x0'] + p['vx']*tf
                    y = p['y0'] + p['vy']*tf + 0.5*0.35*tf*tf
                    life_ratio = 1.0 - el / p['life']
                    if life_ratio > 0:
                        sz = int(4 * life_ratio + 2)
                        col = p['color']
                        drawCircle(int(x), int(y), sz, fill=rgb(col[0],col[1],col[2]), border=rgb(0,0,0), borderWidth=1)
        except:
            pass
        try:
            drawRect(0,0,app.width,80, fill=rgb(0,0,0), border=rgb(40,40,60), borderWidth=2)
            drawLabel("QBasic GORILLAS.BAS - 8-BIT SOUNDBOARD", app.width//2, 24, size=22, bold=True, fill=rgb(0,255,255))
            drawLabel("Event-driven: currentTime + onended | No timeouts | Tetr-quality", app.width//2, 48, size=11, fill=rgb(180,220,255))
            drawLabel("CLICK BUTTON OR PRESS 1-7 T/B/G/V/F SPACE C=new city", app.width//2, 66, size=10, fill=rgb(255,255,150))
        except:
            pass
        try:
            for b in app.buttons:
                is_playing = (b['key'] == app.playing_name)
                draw_beveled_button(app, b, is_playing, b['hover'])
        except Exception as e:
            try:
                app.last_error = f"buttons {e}"
            except:
                pass
        try:
            drawRect(app.detail_x, app.detail_y, app.detail_w, app.detail_h, fill=rgb(0,0,0), border=rgb(0,255,255), borderWidth=2)
            drawCircle(app.detail_x+app.detail_w-18, app.detail_y+14, 7, fill=rgb(0,255,80) if app.playing_name else rgb(60,60,60), border=rgb(0,0,0), borderWidth=1)
            if app.playing_name:
                desc = GORILLA_DESCRIPTIONS.get(app.playing_name, "")
                drawLabel(f"> {app.playing_name.upper()} : {desc}", app.detail_x+12, app.detail_y+14, size=11, bold=True, fill=rgb(0,255,255), align='left-top')
                mml_list = GORILLA_SOUNDS.get(app.playing_name, [])
                mml_str = " | ".join(mml_list)
                if len(mml_str) > 85:
                    mml_str = mml_str[:83]+".."
                drawLabel(f"MML: {mml_str}", app.detail_x+12, app.detail_y+34, size=9, fill=rgb(255,255,150), align='left-top')
                if app.playing_events:
                    elapsed = 0
                    if app.playing_start_time is not None:
                        elapsed = now_audio_time(app) - app.playing_start_time
                    prog = min(1.0, elapsed / max(0.001, app.playing_duration))
                    drawRect(app.detail_x+12, app.detail_y+54, app.detail_w-24, 12, fill=rgb(30,30,50), border=rgb(0,0,0), borderWidth=1)
                    drawRect(app.detail_x+12, app.detail_y+54, int((app.detail_w-24)*prog), 12, fill=rgb(0,255,180), border=rgb(0,0,0), borderWidth=1)
            else:
                drawLabel("SELECT A SOUND - Event driven", app.detail_x+12, app.detail_y+14, size=10, bold=True, fill=rgb(100,200,255), align='left-top')
                drawLabel("Keys: 1-7 T/B/G/V/F SPACE C=new city R=help", app.detail_x+12, app.detail_y+36, size=9, fill=rgb(200,200,200), align='left-top')
                if hasattr(app, 'last_error') and app.last_error:
                    drawLabel(f"Err: {app.last_error}", app.detail_x+12, app.detail_y+60, size=9, fill=rgb(255,80,80), align='left-top')
        except:
            pass
        try:
            drawRect(app.vis_x, app.vis_y, app.vis_w, app.vis_h, fill=rgb(5,5,12), border=rgb(255,0,255), borderWidth=2)
            drawLabel("SQUARE WAVE VISUALIZER - 50% duty PC Speaker", app.vis_x+12, app.vis_y+14, size=10, bold=True, fill=rgb(255,0,255), align='left-top')
            if hasattr(app, 'playing_events') and app.playing_events and hasattr(app, 'playing_start_time') and app.playing_start_time is not None:
                cur = now_audio_time(app)
                elapsed = cur - app.playing_start_time
                accum = 0
                cur_ev = None
                for ev in app.playing_events:
                    if accum <= elapsed <= accum + ev['total_duration']/1000.0:
                        cur_ev = ev
                        break
                    accum += ev['total_duration']/1000.0
                if cur_ev and cur_ev['freq'] > 0:
                    drawLabel(f"FREQ {cur_ev['freq']:.1f}Hz NOTE {cur_ev.get('raw','')} t={elapsed:.2f}s", app.vis_x+12, app.vis_y+36, size=10, fill=rgb(0,255,255), align='left-top')
                    wave_y = app.vis_y + 70
                    wave_h = 55
                    wave_w = app.vis_w - 24
                    cycles = 5
                    period_px = wave_w / cycles
                    for cx in range(cycles):
                        x = app.vis_x + 12 + cx*period_px
                        drawLine(x, wave_y, x+period_px/2, wave_y, fill=rgb(0,255,180), lineWidth=3)
                        drawLine(x+period_px/2, wave_y+wave_h, x+period_px, wave_y+wave_h, fill=rgb(0,255,180), lineWidth=3)
                        drawLine(x+period_px/2, wave_y, x+period_px/2, wave_y+wave_h, fill=rgb(0,255,180), lineWidth=2)
        except:
            pass
        try:
            drawRect(0, app.height-22, app.width, 22, fill=rgb(0,0,0), border=rgb(30,30,40), borderWidth=1)
            drawLabel("Original GORILLA.BAS 1990 Microsoft | QBasic PLAY MML | EVENT-DRIVEN", app.width//2, app.height-11, size=9, fill=rgb(120,180,200), align='center')
        except:
            pass
        try:
            if hasattr(app, 'show_help') and app.show_help:
                drawRect(app.width//2-230, app.height//2-70, 460, 150, fill=rgb(0,0,0), border=rgb(0,255,255), borderWidth=2)
                drawLabel("CLICK ANYWHERE TO ENABLE AUDIO", app.width//2, app.height//2-42, size=15, bold=True, fill=rgb(0,255,255))
                drawLabel("AudioContext needs gesture, then onended drives everything", app.width//2, app.height//2-20, size=10, fill=rgb(200,200,200))
                drawLabel("Keys: 1-7 T/B/G/V/F SPACE | C=new city R=help", app.width//2, app.height//2+2, size=10, fill=rgb(255,255,150))
                drawLabel("TETR QUALITY | No timeouts, only events", app.width//2, app.height//2+24, size=9, fill=rgb(150,150,150))
        except:
            pass
    except Exception as e:
        try:
            drawRect(0,0,app.width,app.height, fill=rgb(40,0,0))
            drawLabel(f"DRAW ERROR: {e}", app.width//2, app.height//2-20, size=14, bold=True, fill=rgb(255,100,100))
            import traceback
            tb = traceback.format_exc()
            drawLabel(tb[:220], app.width//2, app.height//2+20, size=8, fill=rgb(255,200,200))
        except:
            pass

def main():
    runApp(1050, 700)

main()
