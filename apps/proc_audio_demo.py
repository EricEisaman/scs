"""
proc_audio_demo.py - Demo for procedural audio extension
SCS app: ?app=proc_audio_demo
"""
from scs import *
import math
import random
import json as py_json

try:
    import extensions.proc_audio as pa
    AudioEngine = pa.AudioEngine
    Patch = pa.Patch
    sfx = pa.sfx
    Bus = pa.Bus
    SeededRandom = pa.SeededRandom
    OfflineRenderer = pa.OfflineRenderer
    Recorder = pa.Recorder
    BUILTIN_PRESETS = pa.BUILTIN_PRESETS
    QUALITY_PROFILES = pa.QUALITY_PROFILES
    HAS_PROC_AUDIO = True
except Exception as e:
    print(f"proc_audio import failed: {e}")
    HAS_PROC_AUDIO = False
    AudioEngine = None
    Patch = None
    sfx = None
    Bus = None
    SeededRandom = None
    OfflineRenderer = None
    Recorder = None
    BUILTIN_PRESETS = {}
    QUALITY_PROFILES = {}

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.background = rgb(15,15,25)

    # Audio engine
    if HAS_PROC_AUDIO:
        app.audio = AudioEngine(quality="high", seed=90210, master_db=-4, category_levels={"music": -10, "sfx": -3, "ui": -6, "voice": -2, "ambience": -12})
        app.recorder = Recorder(app.audio)
        app.offline = OfflineRenderer()
        app.sfx = sfx
        app.sfx.init(quality="high", seed=90210, master_db=-4)
    else:
        app.audio = None

    app.unlocked = False
    app.last_seed = 42
    app.play_log = []
    app.selected_preset = "character.jump"
    app.presets_list = list(BUILTIN_PRESETS.keys()) if HAS_PROC_AUDIO else []
    app.macro_brightness = 0.7
    app.macro_pitch = 1.0
    app.macro_energy = 0.8
    app.spatial_x = app.width//2
    app.ducking = False
    app.meter_data = []

    # Demo particles for burst protection visual
    app.particles = []

    # Custom patch example - laser with builder API
    if HAS_PROC_AUDIO:
        app.custom_laser = (
            Patch(id="custom.laser_demo", category="sfx", duration=0.25, polyphony=6)
            .oscillator("sawtooth", frequency=880)
            .pitch_envelope(start=2400, end=160, duration=0.18, curve="exp")
            .filter("lowpass", frequency=3200, q=3)
            .envelope(attack=0.002, decay=0.12, sustain=0, release=0.04)
            .distortion(amount=18)
        )
        app.custom_laser.tags = ["custom","weapon","demo"]
        # Second patch - jump with macro controls
        app.custom_jump = (
            Patch(id="custom.jump_macro", category="sfx", duration=0.35)
            .oscillator("sine", frequency=220)
            .filter("lowpass", frequency=2000, q=0.8)
            .envelope(attack=0.005, decay=0.15, sustain=0, release=0.1)
        )
        app.custom_jump.macro("weight", default=0.5, min=0, max=1, maps_to="filter.frequency")
        app.custom_jump.macro("brightness", default=0.7, min=0, max=1, maps_to="osc.frequency")

    app.stepsPerSecond = 30
    app.tick = 0

def onStep(app):
    app.tick += 1
    # update particles
    for p in app.particles[:]:
        p["x"] += p["vx"]
        p["y"] += p["vy"]
        p["life"] -= 1
        if p["life"] <= 0:
            app.particles.remove(p)

    # analysis meter
    if HAS_PROC_AUDIO and app.audio and app.unlocked and app.tick % 5 == 0:
        try:
            analysis = app.audio.get_analysis("sfx", fft_size=512)
            app.meter_data = analysis.get("spectrum", [])[:32]
        except:
            pass

def redrawAll(app):
    drawRect(0,0,app.width,app.height, fill=app.background)

    # Title
    drawLabel("PROC_AUDIO - Declarative Procedural SFX Extension", app.width//2, 28, size=18, fill=rgb(200,220,255), bold=True)
    drawLabel("High-level: sfx.play('jump', pitch=1.2)  |  Low-level: Patch().oscillator().filter().envelope()", app.width//2, 52, size=11, fill=rgb(150,170,200))

    # Unlock banner
    if not app.unlocked:
        drawRect(app.width//2, app.height//2, 420, 120, fill=rgb(40,40,80), border=rgb(100,120,255), borderWidth=2, align='center')
        drawLabel("CLICK TO UNLOCK AUDIO", app.width//2, app.height//2 - 20, size=20, fill=rgb(255,255,255), bold=True)
        drawLabel("Browsers require user gesture to start AudioContext", app.width//2, app.height//2 + 10, size=11, fill=rgb(180,180,220))
        drawLabel("Then use QWERTY keys to play presets", app.width//2, app.height//2 + 30, size=11, fill=rgb(180,180,220))
        return

    # Left panel - preset browser
    drawRect(10,80, 260, 540, fill=rgb(25,25,40), border=rgb(60,60,90), borderWidth=1)
    drawLabel("PRESET BROWSER", 140, 95, size=12, fill=rgb(180,200,255), bold=True)
    y = 115
    for i, pid in enumerate(app.presets_list[:18]):
        is_sel = (pid == app.selected_preset)
        col = rgb(80,80,180) if is_sel else rgb(35,35,55)
        bcol = rgb(120,140,255) if is_sel else rgb(50,50,70)
        drawRect(20, y, 240, 22, fill=col, border=bcol, borderWidth=1 if is_sel else 0)
        drawLabel(pid, 30, y+11, size=10, fill=rgb(220,220,255) if is_sel else rgb(160,160,180), align="left-top")
        y += 26
        if y > 600:
            break

    # Center panel - patch graph visual
    drawRect(280,80, 500, 320, fill=rgb(20,20,35), border=rgb(70,70,100), borderWidth=1)
    drawLabel(f"PATCH: {app.selected_preset}", 530, 95, size=13, fill=rgb(220,230,255), bold=True)
    if HAS_PROC_AUDIO:
        patch = BUILTIN_PRESETS.get(app.selected_preset)
        if patch:
            # draw graph nodes
            nodes = patch.graph
            nx = 300
            for node in nodes:
                nid = node.get("id","?")
                ntype = node.get("type","?")
                drawRect(nx, 130, 90, 50, fill=rgb(50,50,90), border=rgb(100,100,150), borderWidth=1)
                drawLabel(nid, nx+45, 145, size=9, fill=rgb(200,220,255), bold=True)
                drawLabel(ntype, nx+45, 162, size=8, fill=rgb(150,170,200))
                # arrow
                if nx < 700:
                    drawLine(nx+90, 155, nx+110, 155, fill=rgb(100,100,150), lineWidth=2)
                nx += 110
            # routing
            drawLabel(f"Duration: {patch.duration}s | Poly: {patch.polyphony} | Cat: {patch.category}", 530, 210, size=10, fill=rgb(150,170,190))
            tags = ",".join(patch.tags[:4])
            drawLabel(f"Tags: {tags}", 530, 230, size=10, fill=rgb(130,150,180))
            # randomization
            if patch.randomization:
                rnd_str = ", ".join([f"{k}:{v}" for k,v in list(patch.randomization.items())[:2]])
                drawLabel(f"Variation: {rnd_str}", 530, 250, size=9, fill=rgb(180,200,120))

            # macro controls
            drawLabel("MACRO CONTROLS:", 300, 285, size=11, fill=rgb(200,220,255), bold=True, align="left-top")
            # brightness slider
            drawRect(300, 305, 200, 12, fill=rgb(40,40,60), border=rgb(80,80,100), borderWidth=1)
            drawRect(300, 305, int(200*app.macro_brightness), 12, fill=rgb(100,180,255))
            drawLabel(f"brightness {app.macro_brightness:.2f}", 510, 311, size=10, fill=rgb(200,220,255), align="left-top")
            # pitch
            drawRect(300, 325, 200, 12, fill=rgb(40,40,60), border=rgb(80,80,100), borderWidth=1)
            drawRect(300, 325, int(200*min(1,app.macro_pitch/2)), 12, fill=rgb(255,180,100))
            drawLabel(f"pitch {app.macro_pitch:.2f}", 510, 331, size=10, fill=rgb(200,220,255), align="left-top")
            # energy
            drawRect(300, 345, 200, 12, fill=rgb(40,40,60), border=rgb(80,80,100), borderWidth=1)
            drawRect(300, 345, int(200*app.macro_energy), 12, fill=rgb(255,100,100))
            drawLabel(f"energy {app.macro_energy:.2f}", 510, 351, size=10, fill=rgb(200,220,255), align="left-top")

    # Right panel - mixer buses
    drawRect(790,80, 250, 320, fill=rgb(25,25,40), border=rgb(60,60,90), borderWidth=1)
    drawLabel("MIXER BUSES", 915, 95, size=12, fill=rgb(180,200,255), bold=True)
    buses = ["master","music","sfx","ui","voice","ambience"]
    by = 115
    for bus in buses:
        db = app.audio.category_levels.get(bus, -3) if app.audio else -3
        if bus == "master":
            db = app.audio.master_db if app.audio else -4
        lin = max(0, min(1, (db + 60)/60))
        drawRect(800, by, 230, 28, fill=rgb(35,35,55), border=rgb(60,60,80), borderWidth=1)
        drawRect(800, by, int(230*lin), 28, fill=rgb(100,200,120) if bus!="master" else rgb(200,200,100))
        drawLabel(f"{bus} {db}dB", 810, by+14, size=10, fill=rgb(220,220,255), align="left-top")
        by += 34

    # Spectrum meter
    drawRect(280,410, 500, 80, fill=rgb(15,15,25), border=rgb(50,50,70), borderWidth=1)
    drawLabel("ANALYSER - FFT / RMS", 300, 420, size=10, fill=rgb(150,170,190), align="left-top")
    if app.meter_data:
        for i, val in enumerate(app.meter_data[:32]):
            h = (val/255)*60
            drawRect(290 + i*15, 470 - h, 10, h, fill=rgb(100, 150+val//2, 255))

    # Play log
    drawRect(790,410, 250, 210, fill=rgb(20,20,30), border=rgb(50,50,70), borderWidth=1)
    drawLabel("PLAY LOG (deterministic seeds)", 915, 420, size=10, fill=rgb(150,170,190), bold=True)
    ly = 435
    for entry in app.play_log[-12:]:
        drawLabel(entry, 800, ly, size=9, fill=rgb(180,200,180), align="left-top")
        ly += 14

    # Controls help
    drawRect(10,625, 1030, 65, fill=rgb(20,25,40), border=rgb(60,70,90), borderWidth=1)
    drawLabel("Q:jump  W:laser  E:explosion  R:coin  T:hover  Y:engine  A:spatial  S:duck  D:burst(20x)  Space:random  M:mute music  C:custom patch  B:bake WAV  P:particles", 20, 635, size=10, fill=rgb(180,200,255), align="left-top")
    drawLabel("Mouse X = pan  |  Drag brightness/pitch/energy sliders  |  Click preset to select  |  High-level API: sfx.play('jump', pitch=1.2, seed=42)", 20, 655, size=9, fill=rgb(130,150,180), align="left-top")

    # particles for burst test
    for p in app.particles:
        drawCircle(p["x"], p["y"], 4, fill=rgb(255,200,100), opacity=p["life"]/20)

def onMousePress(app, mouseX, mouseY):
    if not app.unlocked:
        if HAS_PROC_AUDIO and app.audio:
            app.audio.resume()
            app.sfx.resume()
        app.unlocked = True
        if HAS_PROC_AUDIO:
            # play unlock sound
            try:
                app.audio.play("ui.coin_pickup", seed=1)
            except:
                pass
        return

    # check preset click
    if 20 <= mouseX <= 260 and 115 <= mouseY <= 600:
        idx = int((mouseY - 115)//26)
        if 0 <= idx < len(app.presets_list):
            app.selected_preset = app.presets_list[idx]
            if HAS_PROC_AUDIO:
                try:
                    h = app.audio.play(app.selected_preset, seed=app.last_seed)
                    app.play_log.append(f"{app.selected_preset} seed={app.last_seed}")
                    app.last_seed += 1
                except:
                    pass

    # check macro sliders
    if 300 <= mouseX <= 500:
        if 305 <= mouseY <= 317:
            app.macro_brightness = max(0, min(1, (mouseX-300)/200))
        elif 325 <= mouseY <= 337:
            app.macro_pitch = max(0.2, min(2.5, (mouseX-300)/200 * 2.5))
        elif 345 <= mouseY <= 357:
            app.macro_energy = max(0, min(1.5, (mouseX-300)/200 * 1.5))

    app.spatial_x = mouseX

def onMouseDrag(app, mouseX, mouseY):
    onMousePress(app, mouseX, mouseY)

def onKeyPress(app, key):
    if not app.unlocked:
        if HAS_PROC_AUDIO and app.audio:
            app.audio.resume()
        app.unlocked = True
        return

    if not HAS_PROC_AUDIO:
        return

    k = key.lower()
    try:
        if k == 'q':
            h = app.audio.play("character.jump", params={"pitch":app.macro_pitch,"brightness":app.macro_brightness,"energy":app.macro_energy}, seed=app.last_seed)
            app.play_log.append(f"jump pitch={app.macro_pitch:.2f} seed={app.last_seed}")
        elif k == 'w':
            h = app.audio.play("weapon.laser_01", params={"pitch":app.macro_pitch,"brightness":app.macro_brightness}, seed=app.last_seed, position=(app.spatial_x,0,0), spatial=True)
            app.play_log.append(f"laser pan={((app.spatial_x/app.width)*2-1):.2f} seed={app.last_seed}")
        elif k == 'e':
            h = app.audio.play("weapon.explosion_large", params={"energy":app.macro_energy}, seed=app.last_seed, position=(app.spatial_x,0,0), spatial=True)
            app.play_log.append(f"explosion energy={app.macro_energy:.2f} seed={app.last_seed}")
        elif k == 'r':
            h = app.audio.play("ui.coin_pickup", seed=app.last_seed)
            app.play_log.append(f"coin seed={app.last_seed}")
        elif k == 't':
            h = app.audio.play("ui.hover", seed=app.last_seed)
            app.play_log.append(f"hover seed={app.last_seed}")
        elif k == 'y':
            h = app.audio.play("vehicle.engine_idle", seed=app.last_seed)
            app.play_log.append(f"engine_idle seed={app.last_seed}")
        elif k == 'a':
            # spatial test - move sound left to right
            h = app.audio.play("weapon.plasma_bolt", position=(app.spatial_x,0,-5), spatial=True, min_distance=1, max_distance=100, occlusion=0.3, seed=app.last_seed)
            app.play_log.append(f"spatial x={app.spatial_x} seed={app.last_seed}")
        elif k == 's':
            # ducking test - voice ducks music
            if not app.ducking:
                app.audio.duck(target_bus="music", trigger_bus="voice", amount_db=-12, attack=0.03, release=0.35)
                app.ducking = True
            h1 = app.audio.play("character.jump", category="music", seed=app.last_seed)  # music bus
            h2 = app.audio.play("ui.coin_pickup", category="voice", seed=app.last_seed+1)  # voice triggers duck
            app.play_log.append(f"duck music->voice seed={app.last_seed}")
        elif k == 'd':
            # burst protection - 20 simultaneous impacts should become 1 foreground + aggregated
            for i in range(20):
                app.audio.play("weapon.laser_01", seed=app.last_seed+i, params={"pan": random.uniform(-0.5,0.5)})
                app.particles.append({"x":random.randint(300,700),"y":random.randint(400,500),"vx":random.uniform(-3,3),"vy":random.uniform(-4,-1),"life":20})
            app.play_log.append(f"burst 20x protected seed={app.last_seed}")
        elif k == ' ':
            # random variation - same preset, different seed = reproducible variation
            app.last_seed = random.randint(0,100000)
            h = app.audio.play(app.selected_preset, seed=app.last_seed, params={"pitch":random.uniform(0.8,1.3),"brightness":random.uniform(0.3,1.0),"energy":random.uniform(0.5,1.2)}, position=(random.randint(0,app.width),0,0), spatial=True)
            app.play_log.append(f"{app.selected_preset} var seed={app.last_seed}")
        elif k == 'm':
            # mute music
            app.audio.mute_bus("music", mute=True)
            app.play_log.append("mute music")
            # unmute after 2 sec via JS timeout
            from browser import window
            window.setTimeout(lambda: app.audio.mute_bus("music", mute=False), 2000)
        elif k == 'c':
            # custom patch builder API
            h = app.audio.play(app.custom_laser, seed=app.last_seed, params={"pitch":app.macro_pitch,"energy":app.macro_energy})
            app.play_log.append(f"custom.laser builder seed={app.last_seed}")
        elif k == 'b':
            # bake WAV via offline
            result = app.audio.render_to_wav(app.selected_preset, duration=1.0, seed=app.last_seed)
            app.play_log.append(f"bake WAV {app.selected_preset} -> {result}")
        elif k == 'p':
            # particles - test polyphony limit
            for i in range(8):
                app.audio.play("character.footstep_grass", seed=app.last_seed+i)
            app.play_log.append(f"poly 8 footsteps seed={app.last_seed}")
        elif k == 'l':
            # linter
            app.play_log.append(f"linter: voices={len(app.audio._active_voices)}/{app.audio.max_voices} state={app.audio._state}")

        app.last_seed += 1
        if len(app.play_log) > 50:
            app.play_log = app.play_log[-50:]

    except Exception as e:
        app.play_log.append(f"ERR {e}")

def onKeyHold(app, keys):
    # hold space for continuous random
    if ' ' in keys and app.tick % 6 == 0 and app.unlocked and HAS_PROC_AUDIO:
        try:
            app.audio.play(app.selected_preset, seed=app.last_seed, params={"pitch":random.uniform(0.9,1.2)})
            app.last_seed += 1
        except:
            pass
