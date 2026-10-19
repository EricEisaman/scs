from scs import *
import math

def calcBudget(albedo, gh):
    solarIn=340.0
    reflected=solarIn*albedo
    absorbed=solarIn-reflected
    sigma=5.67e-8
    Te=(absorbed/sigma)**0.25
    Ts=Te/((1-gh/2)**0.25) if gh<0.99 else Te*1.6
    atmAbs=absorbed*(0.20+gh*0.50)
    surfAbs=absorbed-atmAbs
    atmEm=atmAbs+surfAbs*gh
    surfEm=sigma*Ts**4
    return {'in':solarIn,'ref':reflected,'abs':absorbed,'atmAbs':atmAbs,'surfAbs':surfAbs,'Te':Te,'Ts':Ts,'surfEm':surfEm,'atmEm':atmEm}

def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=30
    app.albedo=0.30; app.gh=0.39; app.dragging=None
    app.budget=calcBudget(app.albedo,app.gh)

def onMousePress(app,mx,my):
    if 30 <= mx <= 360 and 618 <= my <= 642: app.dragging='albedo'
    elif 400 <= mx <= 730 and 618 <= my <= 642: app.dragging='gh'
    # presets - now at y=302 and 335, clearly below data panel which ends at 282
    if 792 <= mx <= 892 and 302 <= my <= 327: app.albedo,app.gh=0.30,0.40
    elif 902 <= mx <= 1028 and 302 <= my <= 327: app.albedo,app.gh=0.50,0.35
    elif 792 <= mx <= 892 and 335 <= my <= 360: app.albedo,app.gh=0.30,0.70
    elif 902 <= mx <= 1028 and 335 <= my <= 360: app.albedo,app.gh=0.10,0.10
    onMouseDrag(app,mx,my)

def onMouseDrag(app,mx,my):
    if app.dragging=='albedo': app.albedo=max(0.05,min(0.65,(mx-30)/330))
    if app.dragging=='gh': app.gh=max(0.0,min(0.95,(mx-400)/330))
    app.budget=calcBudget(app.albedo,app.gh)
def onMouseRelease(app,mx,my): app.dragging=None
def onKeyPress(app,k):
    if k=='up': app.albedo=min(0.65,app.albedo+0.02)
    if k=='down': app.albedo=max(0.05,app.albedo-0.02)
    if k=='right': app.gh=min(0.95,app.gh+0.02)
    if k=='left': app.gh=max(0.0,app.gh-0.02)
    app.budget=calcBudget(app.albedo,app.gh)

def redrawAll(app):
    drawRect(0,0,1050,700, fill=rgb(13,18,33))
    b=app.budget
    drawRect(0,0,1050,38, fill=rgb(10,12,20), opacity=92)
    drawLabel("APP 3: RADIATION BUDGET BOARD - In = Out at equilibrium", 15, 20, size=17, bold=True, fill=rgb(255,255,255), align='left')

    # LEFT FLOW - uses full width to 770
    drawCircle(70, 90, 30, fill=rgb(255,222,85), border=None)
    drawLabel("SUN", 70, 92, size=14, bold=True, fill=rgb(50,30,0))

    drawRect(115, 82, 195, 20, fill=rgb(255,222,85), border=None)
    drawLabel(f"{b['in']:.0f} W/m2 INCOMING", 232, 62, size=16, bold=True, fill=rgb(255,222,85))

    # reflected - label completely clear of line
    refW=max(3,b['ref']/340*26)
    drawLine(205, 92, 80, 48, fill=rgb(160,200,255), lineWidth=refW)
    drawLabel(f"Reflected {b['ref']:.0f} W/m2", 10, 38, size=15, bold=True, fill=rgb(160,200,255), align='left')

    # atmosphere - larger, centered
    drawRect(325, 58, 235, 115, fill=rgb(50,70,125), border=rgb(130,160,230), borderWidth=2)
    drawLabel("ATMOSPHERE", 442, 80, size=17, bold=True, fill=rgb(255,255,255))
    drawLabel(f"Absorbs {b['atmAbs']:.0f} W/m2", 442, 104, size=15, fill=rgb(190,210,255))
    drawLabel(f"Emits {b['atmEm']:.0f} W/m2 up & down", 442, 126, size=13, fill=rgb(255,150,150))
    drawLabel(f"Greenhouse g={app.gh:.2f}", 442, 146, size=13, fill=rgb(255,180,180))

    # to space
    drawRect(560, 82, 195, 20, fill=rgb(255,95,95), border=None)
    drawLabel(f"To space {b['abs']:.0f} = IN", 657, 62, size=15, bold=True, fill=rgb(255,95,95))

    # absorbed vertical - uses middle empty space now
    absW=max(5,b['abs']/340*32)
    drawRect(430, 173, absW, 252, fill=rgb(255,175,60), border=None)
    drawLabel(f"Absorbed {b['abs']:.0f} total", 470+absW, 295, size=16, bold=True, fill=rgb(255,175,60), align='left')

    # surface - wide, lower to fill space
    drawRect(130, 425, 540, 150, fill=rgb(95,75,45), border=rgb(210,180,120), borderWidth=2)
    drawLabel("SURFACE", 400, 452, size=18, bold=True, fill=rgb(255,255,255))
    drawLabel(f"Absorbs {b['surfAbs']:.0f} W/m2 solar + IR", 400, 480, size=15, fill=rgb(255,230,150))
    drawLabel(f"Emits {b['surfEm']:.0f} W/m2 IR upward", 400, 504, size=15, fill=rgb(255,120,120))
    drawLabel(f"Albedo {app.albedo:.2f} controls reflection", 400, 534, size=14, fill=rgb(200,210,230))

    # thermometer - enlarged, gap from right panel
    drawRect(700, 425, 76, 150, fill=rgb(35,38,55), border=rgb(110,115,140), borderWidth=2)
    TsC=b['Ts']-273.15
    frac=max(0,min(1,(TsC+20)/60))
    drawRect(702, 575-frac*148, 72, frac*148, fill=rgb(255,70,70), border=None)
    drawLabel(f"{TsC:.1f} C", 738, 402, size=20, bold=True, fill=rgb(255,70,70))
    drawLabel(f"Te {b['Te']-273.15:.1f}C w/o GH", 738, 590, size=13, fill=rgb(160,175,200))

    # RIGHT COLUMN - 790-1030, data ends at 282, presets start at 302 = no overlap
    drawRect(790, 52, 248, 230, fill=rgb(26,31,50), border=rgb(75,85,115), borderWidth=2)
    drawLabel("COPY TO PAPER", 914, 72, size=16, bold=True, fill=rgb(255,230,100))
    drawLabel(f"In: {b['in']:.0f} W/m2", 805, 98, size=18, fill=rgb(255,222,85), align='left')
    drawLabel(f"Ref: {b['ref']:.0f} W/m2", 805, 124, size=18, fill=rgb(160,200,255), align='left')
    drawLabel(f"Abs: {b['abs']:.0f} W/m2", 805, 150, size=18, bold=True, fill=rgb(255,175,60), align='left')
    drawLabel(f"Atm Abs {b['atmAbs']:.0f}", 805, 176, size=15, fill=rgb(190,210,255), align='left')
    drawLabel(f"Surf Abs {b['surfAbs']:.0f}", 805, 197, size=15, fill=rgb(255,230,150), align='left')
    drawLabel(f"Ts {b['Ts']:.0f}K {TsC:.1f}C", 805, 224, size=16, bold=True, fill=rgb(255,95,95), align='left')
    drawLabel("In = Ref + Abs | Abs = Out", 805, 252, size=13, fill=rgb(150,220,150), align='left')

    # preset buttons - separate block, 12px gap
    drawRect(792, 302, 100, 28, fill=rgb(55,65,95), border=rgb(120,135,175), borderWidth=1.5)
    drawLabel("Modern", 842, 317, size=15, fill=rgb(255,255,255))
    drawRect(902, 302, 126, 28, fill=rgb(75,85,105), border=rgb(120,135,175), borderWidth=1.5)
    drawLabel("Ice Age", 965, 317, size=15, fill=rgb(255,255,255))
    drawRect(792, 335, 100, 28, fill=rgb(95,65,55), border=rgb(175,135,125), borderWidth=1.5)
    drawLabel("High CO2", 842, 350, size=15, fill=rgb(255,255,255))
    drawRect(902, 335, 126, 28, fill=rgb(45,45,65), border=rgb(120,135,175), borderWidth=1.5)
    drawLabel("No GH", 965, 350, size=15, fill=rgb(255,255,255))

    # sliders - own band at bottom, not overlapping thermometer
    drawLabel(f"Albedo {app.albedo:.2f} - ice/clouds", 30, 598, size=16, bold=True, fill=rgb(160,200,255), align='left')
    drawRect(30, 618, 330, 24, fill=rgb(40,50,75), border=rgb(110,130,170), borderWidth=1.5)
    drawCircle(30+app.albedo/0.65*330, 630, 13, fill=rgb(160,200,255), border=rgb(0,0,0), borderWidth=2)

    drawLabel(f"Greenhouse {app.gh:.2f} - CO2/CH4", 400, 598, size=16, bold=True, fill=rgb(255,150,150), align='left')
    drawRect(400, 618, 330, 24, fill=rgb(70,45,60), border=rgb(170,110,120), borderWidth=1.5)
    drawCircle(400+app.gh/0.95*330, 630, 13, fill=rgb(255,120,120), border=rgb(0,0,0), borderWidth=2)

    drawLabel("DRAG SLIDERS - Paper: Sankey for 3 presets, graph Ts vs Albedo and Ts vs GH", 390, 668, size=15, bold=True, fill=rgb(230,240,255))

def main(): runApp(1050,700, stepsPerSecond=30)
main()