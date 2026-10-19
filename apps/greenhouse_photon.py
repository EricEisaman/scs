from scs import *
import math, random

def calcSurfaceTemp(co2_ppm):
    # Fixed: baseline 0.77 at 280ppm = 14-15C, not -3C
    # 3C per doubling = epsilon increase ~0.06 per doubling
    epsilon = 0.77 + 0.06 * math.log(co2_ppm/280, 2)
    epsilon = max(0.65, min(0.92, epsilon))
    T = 255.0 / ((1 - epsilon/2) ** 0.25)
    return T, epsilon

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 40
    app.co2 = 420
    app.photons = []
    app.molecules = []
    for _ in range(40):
        app.molecules.append({'x': random.randint(80, 600), 'y': random.randint(120, 400), 'vib':0})
    app.time = 0
    app.sunCount = 0
    app.escaped = 0
    app.trapped = 0
    app.surfaceTempK, app.epsilon = calcSurfaceTemp(app.co2)
    app.paused = False

def onStep(app):
    if app.paused: return
    app.time += 1/40
    if random.random() < 0.22:
        app.photons.append({'x': random.randint(100, 580), 'y': 10, 'type':'sun', 'vy': 3.5, 'vx': random.uniform(-0.3,0.3)})
        app.sunCount += 1

    newPhotons = []
    for ph in app.photons:
        ph['x'] += ph['vx']
        ph['y'] += ph['vy']
        if ph['type']=='sun':
            if ph['y'] > 520:
                newPhotons.append({'x':ph['x'], 'y':520, 'type':'ir', 'vy':-2.8, 'vx': random.uniform(-1.2,1.2), 'age':0})
            else:
                newPhotons.append(ph)
        else: # IR
            ph['age']+=1
            willAbsorb = False
            # Only up-going IR in atmosphere can be absorbed, with Beer-Lambert small chance
            if 100 <= ph['y'] <= 500 and ph['vy'] < 0:
                # atmospheric window: 12% always passes
                if random.random() >= 0.12:
                    base = app.epsilon * 0.006 * (app.co2/400)  # 0.0032 at 280ppm, 0.013 at 990ppm per frame
                    if random.random() < base:
                        willAbsorb = True
                        # flash nearest molecule for visuals only
                        nearest = None
                        best = 9999
                        for m in app.molecules:
                            d = abs(ph['x']-m['x']) + abs(ph['y']-m['y'])
                            if d < best and d < 80:
                                best = d
                                nearest = m
                        if nearest:
                            nearest['vib'] = 20
                        else:
                            random.choice(app.molecules)['vib'] = 15

            if willAbsorb:
                if random.random() < 0.5:
                    # up - energy stays in atmosphere, will try to escape again
                    newPhotons.append({'x':ph['x'], 'y':ph['y'], 'type':'ir', 'vy':-2.8, 'vx': random.uniform(-1.2,1.2), 'age':0})
                else:
                    # down - returned to surface = trapped
                    newPhotons.append({'x':ph['x'], 'y':ph['y'], 'type':'ir', 'vy':2.8, 'vx': random.uniform(-1.2,1.2), 'age':0})
                    app.trapped += 1
            else:
                if ph['y'] < 20:
                    app.escaped += 1
                elif ph['y'] > 530:
                    # hit surface after being sent down - re-emit up, no extra count
                    newPhotons.append({'x':ph['x'], 'y':520, 'type':'ir', 'vy':-2.8, 'vx': random.uniform(-1.2,1.2), 'age':0})
                elif 0 <= ph['y'] <= 650:
                    newPhotons.append(ph)

    app.photons = newPhotons[-150:]
    for m in app.molecules:
        if m['vib']>0: m['vib']-=1
    if int(app.time*4)%4==0:
        app.surfaceTempK, app.epsilon = calcSurfaceTemp(app.co2)

def onMousePress(app, mx, my):
    if 750 <= mx <= 1020 and 380 <= my <= 600:
        frac = (my-380)/220
        frac = max(0, min(1, frac))
        app.co2 = 280 + frac*(1000-280)
        app.sunCount = 0
        app.escaped = 0
        app.trapped = 0

def onMouseDrag(app, mx, my):
    onMousePress(app,mx,my)

def onKeyPress(app, key):
    if key=='space': app.paused = not app.paused
    if key.lower()=='r':
        app.sunCount=0; app.escaped=0; app.trapped=0; app.photons=[]
    if key=='up': app.co2 = min(1000, app.co2+20)
    if key=='down': app.co2 = max(280, app.co2-20)

def redrawAll(app):
    drawRect(0,0,1050,700, fill=rgb(12,18,32))
    drawRect(0,0,700,100, fill=rgb(5,10,25))
    drawLabel("SUN", 350, 20, size=12, fill=rgb(255,240,100))
    drawRect(0,100,700,380, fill=rgb(30,45,85), opacity=50)
    drawLabel("ATMOSPHERE with CO2 molecules", 350, 110, size=11, fill=rgb(160,200,255))
    drawRect(0,520,700,180, fill=rgb(70,55,35))
    drawRect(0,520,700,8, fill=rgb(120,200,80))
    drawLabel("SURFACE absorbs sun, emits IR", 350, 545, size=11, fill=rgb(255,210,150))
    for m in app.molecules:
        vib = m['vib']/20
        r = 8 + vib*8
        col = rgb(255, 220+int(vib*30), 80) if vib>0 else rgb(100,200,255)
        drawCircle(m['x'], m['y'], r, fill=col, opacity=70+int(vib*30), border=rgb(255,255,255), borderWidth=1)
        if vib>0:
            drawLabel("vib!", m['x'], m['y']-14, size=8, fill=rgb(255,255,100))
    for ph in app.photons:
        if ph['type']=='sun':
            drawCircle(ph['x'], ph['y'], 4, fill=rgb(255,235,80), border=None)
        else:
            drawCircle(ph['x'], ph['y'], 4, fill=rgb(255,60,60), border=None)
            drawLine(ph['x'], ph['y'], ph['x']-ph['vx']*3, ph['y']-ph['vy']*3, fill=rgb(255,60,60), opacity=50, lineWidth=2)
    drawRect(710,0,340,700, fill=rgb(22,26,40), border=rgb(60,70,95), borderWidth=2)
    drawLabel("GREENHOUSE PHOTON LAB", 880, 22, size=15, bold=True, fill=rgb(255,255,255))
    drawLabel(f"CO2: {app.co2:.0f} ppm", 880, 50, size=22, bold=True, fill=rgb(255,230,100))
    tC = app.surfaceTempK - 273.15
    drawLabel(f"Surface: {tC:.1f} C / {app.surfaceTempK:.0f} K", 880, 80, size=16, bold=True, fill=rgb(255,120,80))
    drawLabel(f"Opacity ε={app.epsilon:.2f}", 880, 100, size=12, fill=rgb(180,190,210))
    drawRect(730, 125, 300, 190, fill=rgb(30,35,52), border=rgb(70,80,110), borderWidth=1)
    drawLabel("WRITE THIS ON PAPER - SPACE to pause", 880, 135, size=10, bold=True, fill=rgb(255,230,100))
    total = app.escaped+app.trapped
    escPct = 100*app.escaped/total if total>0 else 0
    drawLabel(f"Sun in: {app.sunCount}", 750, 165, size=14, fill=rgb(255,235,80), align='left')
    drawLabel(f"IR escaped to space: {app.escaped}", 750, 190, size=14, fill=rgb(140,200,255), align='left')
    drawLabel(f"IR trapped / returned: {app.trapped}", 750, 215, size=14, fill=rgb(255,100,100), align='left')
    drawLabel(f"Escape % = {escPct:.1f}%", 750, 240, size=16, bold=True, fill=rgb(255,255,255), align='left')
    drawLabel(f"Total IR = {total}", 750, 265, size=12, fill=rgb(170,180,200), align='left')
    drawLabel("Task: keep 20s, record, change CO2", 750, 290, size=10, fill=rgb(170,180,200), align='left')
    drawRect(750, 380, 30, 220, fill=rgb(50,55,75), border=rgb(100,110,140))
    sliderY = 380 + (app.co2-280)/(1000-280)*220
    drawCircle(765, sliderY, 12, fill=rgb(255,230,100), border=rgb(0,0,0), borderWidth=2)
    drawLabel("280 ppm", 800, 390, size=11, fill=rgb(200,210,230), align='left')
    drawLabel("1000 ppm", 800, 590, size=11, fill=rgb(200,210,230), align='left')
    drawLabel("DRAG SLIDER", 880, 360, size=11, bold=True, fill=rgb(255,230,100))
    drawLabel("UP/DOWN = CO2 | R=reset counts", 880, 625, size=10, fill=rgb(150,160,180))
    drawLabel("Yellow=sun, Red=IR. Molecule flashes=vibration", 880, 642, size=10, fill=rgb(150,160,180))
    drawLabel("Paper graph: X=CO2, Y1=Temp, Y2=Escape %", 880, 660, size=11, bold=True, fill=rgb(180,220,255))
    drawRect(0,0,1050,38, fill=rgb(10,12,20), opacity=88)
    drawLabel("GREENHOUSE BLANKET - More CO2 = fewer red dots escape", 15, 20, size=13, bold=True, fill=rgb(255,255,255), align='left')

def main():
    runApp(1050,700, stepsPerSecond=40)
main()