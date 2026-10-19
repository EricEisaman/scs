from scs import *
import math

def calcBudget(albedo, greenHouse):
    solarIn = 340.0
    reflected = solarIn * albedo
    absorbed = solarIn - reflected
    sigma = 5.67e-8
    Te = (absorbed / sigma) ** 0.25
    Ts = Te / ((1 - greenHouse/2) ** 0.25) if greenHouse < 0.99 else Te*1.6
    atmAbsorbed = absorbed * (0.20 + greenHouse*0.50)
    surfAbsorbed = absorbed - atmAbsorbed
    atmEmission = atmAbsorbed + surfAbsorbed*greenHouse
    surfEmission = 5.67e-8 * Ts**4
    return {'in':solarIn,'ref':reflected,'abs':absorbed,'atmAbs':atmAbsorbed,'surfAbs':surfAbsorbed,'Te':Te,'Ts':Ts,'surfEm':surfEmission,'atmEm':atmEmission}

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 30
    app.albedo = 0.30
    app.gh = 0.40
    app.dragging = None
    app.budget = calcBudget(app.albedo, app.gh)

def onMousePress(app, mx, my):
    if 50 <= mx <= 450 and 620 <= my <= 640:
        app.dragging = 'albedo'
    elif 500 <= mx <= 750 and 620 <= my <= 640:
        app.dragging = 'gh'
    onMouseDrag(app,mx,my)
    if 820 <= mx <= 920 and 135 <= my <= 160: app.albedo, app.gh = 0.30, 0.40
    if 930 <= mx <= 1020 and 135 <= my <= 160: app.albedo, app.gh = 0.50, 0.35
    if 820 <= mx <= 920 and 165 <= my <= 190: app.albedo, app.gh = 0.30, 0.70
    if 930 <= mx <= 1020 and 165 <= my <= 190: app.albedo, app.gh = 0.10, 0.10
    app.budget = calcBudget(app.albedo, app.gh)

def onMouseDrag(app, mx, my):
    if app.dragging == 'albedo':
        app.albedo = max(0.05, min(0.65, (mx-50)/400))
    elif app.dragging == 'gh':
        app.gh = max(0.0, min(0.95, (mx-500)/250))
    app.budget = calcBudget(app.albedo, app.gh)

def onMouseRelease(app,mx,my):
    app.dragging = None

def onKeyPress(app,key):
    if key=='up': app.albedo = min(0.65, app.albedo+0.02)
    if key=='down': app.albedo = max(0.05, app.albedo-0.02)
    if key=='right': app.gh = min(0.95, app.gh+0.02)
    if key=='left': app.gh = max(0.0, app.gh-0.02)
    app.budget = calcBudget(app.albedo, app.gh)

def redrawAll(app):
    drawRect(0,0,1050,700, fill=rgb(14,19,34))
    b = app.budget
    drawRect(0,0,1050,38, fill=rgb(10,12,20), opacity=92)
    drawLabel("APP 3: RADIATION BUDGET BOARD - In = Out at equilibrium", 15, 20, size=15, bold=True, fill=rgb(255,255,255), align='left')

    # SUN
    drawCircle(80, 115, 32, fill=rgb(255,222,85), border=None)
    drawLabel("SUN", 80, 116, size=14, bold=True, fill=rgb(50,30,0))

    # IN arrow - yellow
    drawRect(125, 105, 190, 20, fill=rgb(255,222,85), border=None)
    drawLabel(f"{b['in']:.0f} W/m2 INCOMING", 220, 86, size=14, bold=True, fill=rgb(255,222,85))

    # REFLECTED - separate diagonal, label OFF line
    refW = max(3, b['ref']/340*28)
    drawLine(210, 115, 75, 55, fill=rgb(160,200,255), lineWidth=refW)
    drawLabel(f"Reflected {b['ref']:.0f} W/m2", 30, 38, size=13, bold=True, fill=rgb(160,200,255), align='left')

    # ATMOSPHERE box - centered top, larger
    drawRect(330, 80, 220, 110, fill=rgb(50,70,125), opacity=95, border=rgb(130,160,230), borderWidth=2)
    drawLabel("ATMOSPHERE", 440, 100, size=15, bold=True, fill=rgb(255,255,255))
    drawLabel(f"Absorbs {b['atmAbs']:.0f} W/m2", 440, 124, size=13, fill=rgb(190,210,255))
    drawLabel(f"Emits {b['atmEm']:.0f} W/m2 up & down", 440, 144, size=12, fill=rgb(255,150,150))
    drawLabel(f"Greenhouse g={app.gh:.2f}", 440, 164, size=12, fill=rgb(255,180,180))

    # ABSORBED vertical - orange, label to right of line
    absW = max(4, b['abs']/340*32)
    drawRect(430, 190, absW, 235, fill=rgb(255,175,60), border=None)
    drawLabel(f"Absorbed {b['abs']:.0f} total", 455+absW, 300, size=14, bold=True, fill=rgb(255,175,60), align='left')

    # TO SPACE - red, label above
    drawRect(550, 105, 200, 20, fill=rgb(255,95,95), border=None)
    drawLabel(f"To space {b['abs']:.0f} W/m2 = IN", 650, 84, size=13, bold=True, fill=rgb(255,95,95))

    # SURFACE box - LOWERED to use space, much larger
    drawRect(150, 425, 500, 145, fill=rgb(95,75,45), border=rgb(210,180,120), borderWidth=2)
    drawLabel("SURFACE", 400, 450, size=16, bold=True, fill=rgb(255,255,255))
    drawLabel(f"Absorbs {b['surfAbs']:.0f} W/m2 solar + IR", 400, 475, size=13, fill=rgb(255,230,150))
    drawLabel(f"Emits {b['surfEm']:.0f} W/m2 IR upward", 400, 498, size=13, fill=rgb(255,120,120))
    drawLabel(f"Albedo {app.albedo:.2f} controls reflection", 400, 525, size=12, fill=rgb(200,210,230))

    # THERMOMETER - enlarged, right of surface
    drawRect(680, 425, 80, 145, fill=rgb(35,38,55), border=rgb(110,115,140), borderWidth=2)
    TsC = b['Ts']-273.15
    frac = (TsC+20)/60
    frac = max(0,min(1,frac))
    drawRect(682, 570-frac*143, 76, frac*143, fill=rgb(255,70,70), border=None)
    drawLabel(f"{TsC:.1f} C", 720, 400, size=18, bold=True, fill=rgb(255,70,70))
    drawLabel(f"Te={b['Te']-273.15:.1f}C w/o GH", 720, 585, size=11, fill=rgb(160,175,200))
    drawLabel("SURFACE TEMP", 720, 610, size=12, bold=True, fill=rgb(230,240,255))

    # DATA PANEL - fully on right, no overlap
    drawRect(800, 40, 235, 290, fill=rgb(26,31,50), border=rgb(75,85,115), borderWidth=2)
    drawLabel("COPY TO PAPER", 917, 60, size=14, bold=True, fill=rgb(255,230,100))
    drawLabel(f"In: {b['in']:.0f} W/m2", 815, 85, size=16, fill=rgb(255,222,85), align='left')
    drawLabel(f"Ref: {b['ref']:.0f} W/m2", 815, 110, size=16, fill=rgb(160,200,255), align='left')
    drawLabel(f"Abs: {b['abs']:.0f} W/m2", 815, 135, size=16, bold=True, fill=rgb(255,175,60), align='left')
    drawLabel(f"Atm Abs {b['atmAbs']:.0f}", 815, 160, size=14, fill=rgb(190,210,255), align='left')
    drawLabel(f"Surf Abs {b['surfAbs']:.0f}", 815, 182, size=14, fill=rgb(255,230,150), align='left')
    drawLabel(f"Te {b['Te']:.0f}K", 815, 210, size=14, fill=rgb(180,190,210), align='left')
    drawLabel(f"Ts {b['Ts']:.0f}K {TsC:.1f}C", 815, 232, size=15, bold=True, fill=rgb(255,95,95), align='left')
    drawLabel("In = Ref + Abs", 815, 260, size=12, fill=rgb(150,220,150), align='left')
    drawLabel("Abs = Out (equil.)", 815, 278, size=12, fill=rgb(150,220,150), align='left')

    # presets
    drawRect(820,135,100,25, fill=rgb(55,65,95), border=rgb(120,135,175))
    drawLabel("Modern", 870, 148, size=13, fill=rgb(255,255,255))
    drawRect(930,135,90,25, fill=rgb(75,85,105), border=rgb(120,135,175))
    drawLabel("Ice Age", 975, 148, size=13, fill=rgb(255,255,255))
    drawRect(820,165,100,25, fill=rgb(95,65,55), border=rgb(175,135,125))
    drawLabel("High CO2", 870, 178, size=13, fill=rgb(255,255,255))
    drawRect(930,165,90,25, fill=rgb(45,45,65), border=rgb(120,135,175))
    drawLabel("No GH", 975, 178, size=13, fill=rgb(255,255,255))

    # sliders - bottom, full width use
    drawLabel(f"Albedo (reflect) {app.albedo:.2f} - ice/clouds", 50, 602, size=15, bold=True, fill=rgb(160,200,255), align='left')
    drawRect(50, 620, 400, 20, fill=rgb(40,50,75), border=rgb(110,130,170))
    drawCircle(50+app.albedo/0.65*400, 630, 13, fill=rgb(160,200,255), border=rgb(0,0,0), borderWidth=2)

    drawLabel(f"Greenhouse {app.gh:.2f} - CO2/CH4", 500, 602, size=15, bold=True, fill=rgb(255,150,150), align='left')
    drawRect(500, 620, 250, 20, fill=rgb(70,45,60), border=rgb(170,110,120))
    drawCircle(500+app.gh/0.95*250, 630, 13, fill=rgb(255,120,120), border=rgb(0,0,0), borderWidth=2)

    drawLabel("DRAG SLIDERS - Paper: Sankey for 3 presets, graph Ts vs Albedo and Ts vs GH", 525, 665, size=13, bold=True, fill=rgb(230,240,255))

def main():
    runApp(1050,700, stepsPerSecond=30)
main()