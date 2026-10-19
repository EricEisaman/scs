from scs import *
import math

def calcBudget(albedo, greenHouse):
    solarIn = 340.0
    reflected = solarIn * albedo
    absorbed = solarIn - reflected
    # effective emission temp
    # absorbed = sigma*T_e^4  -> T_e
    sigma = 5.67e-8
    Te = (absorbed / sigma) ** 0.25
    # surface temp higher due to greenhouse: Ts = Te / (1-g/2)^0.25
    Ts = Te / ((1 - greenHouse/2) ** 0.25) if greenHouse<1.9 else Te*1.8
    # split
    atmAbsorbed = absorbed * (0.2 + greenHouse*0.5)
    surfAbsorbed = absorbed - atmAbsorbed
    # emission
    atmEmission = atmAbsorbed + surfAbsorbed*greenHouse
    surfEmission = 5.67e-8 * Ts**4
    spaceEmission = absorbed  # at equilibrium must equal absorbed
    return {
        'in': solarIn, 'ref': reflected, 'abs': absorbed,
        'atmAbs': atmAbsorbed, 'surfAbs': surfAbsorbed,
        'Te': Te, 'Ts': Ts, 'surfEm': surfEmission, 'atmEm': atmEmission
    }

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 30
    app.albedo = 0.30
    app.gh = 0.40
    app.dragging = None # 'albedo' or 'gh'
    app.budget = calcBudget(app.albedo, app.gh)

def onMousePress(app, mx, my):
    # sliders bottom
    if 50 <= mx <= 450 and 610 <= my <= 630:
        app.dragging = 'albedo'
    elif 550 <= mx <= 950 and 610 <= my <= 630:
        app.dragging = 'gh'
    onMouseDrag(app, mx, my)
    # preset buttons
    if 720 <= mx <= 820 and 120 <= my <= 145:
        app.albedo, app.gh = 0.30, 0.40 # modern
    if 830 <= mx <= 930 and 120 <= my <= 145:
        app.albedo, app.gh = 0.50, 0.35 # ice age
    if 720 <= mx <= 820 and 150 <= my <= 175:
        app.albedo, app.gh = 0.30, 0.70 # high CO2
    if 830 <= mx <= 930 and 150 <= my <= 175:
        app.albedo, app.gh = 0.10, 0.10 # no GH

def onMouseDrag(app, mx, my):
    if app.dragging == 'albedo':
        frac = (mx-50)/400
        app.albedo = max(0.05, min(0.65, frac))
    elif app.dragging == 'gh':
        frac = (mx-550)/400
        app.gh = max(0.0, min(0.95, frac))
    app.budget = calcBudget(app.albedo, app.gh)

def onMouseRelease(app, mx, my):
    app.dragging = None

def onKeyPress(app, key):
    if key == 'up': app.albedo = min(0.65, app.albedo+0.02)
    if key == 'down': app.albedo = max(0.05, app.albedo-0.02)
    if key == 'right': app.gh = min(0.95, app.gh+0.02)
    if key == 'left': app.gh = max(0, app.gh-0.02)
    app.budget = calcBudget(app.albedo, app.gh)

def redrawAll(app):
    drawRect(0,0,1050,700, fill=rgb(15,20,35))
    b = app.budget

    # Header
    drawRect(0,0,1050,38, fill=rgb(10,12,20), opacity=90)
    drawLabel("APP 3: RADIATION BUDGET BOARD - In = Out at equilibrium", 15, 20, size=13, bold=True, fill=rgb(255,255,255), align='left')

    # Visual budget - left sun
    drawCircle(90, 130, 35, fill=rgb(255,220,80), border=None)
    drawLabel("SUN", 90, 132, size=12, bold=True, fill=rgb(40,20,0))
    # incoming arrow width = 340
    drawLine(130, 130, 320, 130, fill=rgb(255,220,80), lineWidth=10)
    drawLabel(f"{b['in']:.0f} W/m2 IN", 225, 110, size=12, bold=True, fill=rgb(255,220,80))

    # reflected arrow
    refW = max(2, b['ref']/340*40)
    drawLine(250, 130, 90, 70, fill=rgb(180,200,255), lineWidth=refW)
    drawLabel(f"Reflected {b['ref']:.0f}", 120, 60, size=11, fill=rgb(180,200,255), bold=True)

    # atmosphere box
    drawRect(320, 90, 160, 80, fill=rgb(70,90,140), opacity=70, border=rgb(120,150,220), borderWidth=2)
    drawLabel("ATMOSPHERE", 400, 105, size=11, bold=True, fill=rgb(255,255,255))
    drawLabel(f"Abs {b['atmAbs']:.0f}", 400, 125, size=11, fill=rgb(200,220,255))
    drawLabel(f"Emits {b['atmEm']:.0f} up/down", 400, 145, size=10, fill=rgb(255,160,160))

    # surface
    drawRect(200, 380, 400, 100, fill=rgb(90,70,40), border=rgb(200,170,110), borderWidth=2)
    drawLabel("SURFACE", 400, 395, size=12, bold=True, fill=rgb(255,255,255))
    drawLabel(f"Absorbs {b['surfAbs']:.0f} W/m2", 400, 415, size=11, fill=rgb(255,230,150))
    drawLabel(f"Emits {b['surfEm']:.0f} W/m2 (IR)", 400, 435, size=10, fill=rgb(255,100,100))
    
    # surface temp thermometer
    TsC = b['Ts'] - 273.15
    drawRect(620, 380, 60, 100, fill=rgb(40,40,50), border=rgb(100,100,120))
    # fill height based on -20 to +40 C
    frac = (TsC + 20)/60
    frac = max(0, min(1, frac))
    drawRect(622, 480-frac*96, 56, frac*96, fill=rgb(255,80,80), border=None)
    drawLabel(f"{TsC:.1f} C", 650, 365, size=16, bold=True, fill=rgb(255,80,80))
    drawLabel(f"{b['Te']-273.15:.1f}C no GH", 650, 500, size=10, fill=rgb(150,170,200))

    # arrows down
    absW = max(2, b['abs']/340*35)
    drawLine(400, 170, 400, 380, fill=rgb(255,180,60), lineWidth=absW)
    drawLabel(f"Absorbed {b['abs']:.0f}", 460, 260, size=11, fill=rgb(255,180,60))

    # emission to space
    drawLine(480, 130, 700, 130, fill=rgb(255,100,100), lineWidth=absW)
    drawLabel(f"To space {b['abs']:.0f} = IN", 600, 110, size=11, fill=rgb(255,100,100), bold=True)

    # Data panel for copying
    drawRect(710, 40, 320, fill=rgb(25,30,48), border=rgb(70,80,110), borderWidth=2)
    drawLabel("COPY TO PAPER - BUDGET TABLE", 870, 60, size=12, bold=True, fill=rgb(255,230,100))
    drawLabel(f"Incoming: {b['in']:.0f} W/m2", 730, 90, size=14, fill=rgb(255,220,80), align='left')
    drawLabel(f"Albedo: {app.albedo:.2f} -> Ref: {b['ref']:.1f}", 730, 115, size=14, fill=rgb(140,200,255), align='left')
    drawLabel(f"Absorbed by system: {b['abs']:.1f}", 730, 140, size=14, bold=True, fill=rgb(255,180,60), align='left')
    drawLabel(f"  - Atm absorbs: {b['atmAbs']:.1f}", 730, 165, size=12, fill=rgb(180,200,255), align='left')
    drawLabel(f"  - Surf absorbs: {b['surfAbs']:.1f}", 730, 185, size=12, fill=rgb(255,230,150), align='left')
    drawLabel(f"Effective T (no GH): {b['Te']:.0f}K {b['Te']-273.15:.1f}C", 730, 215, size=12, fill=rgb(180,190,210), align='left')
    drawLabel(f"Surface T (with GH): {b['Ts']:.0f}K {b['Ts']-273.15:.1f}C", 730, 235, size=13, bold=True, fill=rgb(255,100,100), align='left')
    drawLabel(f"GH opacity: {app.gh:.2f}", 730, 255, size=12, fill=rgb(255,160,160), align='left')
    drawLabel("Check: In ({:.0f}) = Ref ({:.0f}) + Abs ({:.0f})".format(b['in'], b['ref'], b['abs']), 730, 285, size=10, fill=rgb(150,200,150), align='left')
    drawLabel("At equilibrium Abs = Out to space", 730, 305, size=10, fill=rgb(150,200,150), align='left')

    # presets
    drawRect(720,120,100,25, fill=rgb(50,60,90), border=rgb(120,130,170))
    drawLabel("Modern", 770, 133, size=11, fill=rgb(255,255,255))
    drawRect(830,120,100,25, fill=rgb(70,80,100), border=rgb(120,130,170))
    drawLabel("Ice Age", 880, 133, size=11, fill=rgb(255,255,255))
    drawRect(720,150,100,25, fill=rgb(90,60,50), border=rgb(170,130,120))
    drawLabel("High CO2", 770, 163, size=11, fill=rgb(255,255,255))
    drawRect(830,150,100,25, fill=rgb(40,40,60), border=rgb(120,130,170))
    drawLabel("No GH", 880, 163, size=11, fill=rgb(255,255,255))

    # sliders
    drawLabel(f"Albedo (ice/cloud reflect) = {app.albedo:.2f}  <- drag ->", 50, 590, size=13, bold=True, fill=rgb(180,200,255), align='left')
    drawRect(50, 610, 400, 18, fill=rgb(40,50,75), border=rgb(100,120,160))
    drawCircle(50+app.albedo/0.65*400, 619, 11, fill=rgb(180,200,255), border=rgb(0,0,0), borderWidth=2)

    drawLabel(f"Greenhouse opacity = {app.gh:.2f}  <- drag ->", 550, 590, size=13, bold=True, fill=rgb(255,160,160), align='left')
    drawRect(550, 610, 400, 18, fill=rgb(70,45), border=rgb(160,100))
    drawCircle(550+app.gh/0.95*400, 619, 11, fill=rgb(255,120,120), border=rgb(0,0,0), borderWidth=2)

    drawLabel("LEFT/RIGHT=GH  UP/DOWN=Albedo | Paper: Draw Sankey for 3 presets, then graph Ts vs Albedo and Ts vs GH", 525, 655, size=11, bold=True, fill=rgb(230,240,255))

def main():
    runApp(1050,700, stepsPerSecond=30)
main()