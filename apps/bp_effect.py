"""
bp_effect.py
SCS App 1: The 1-Point Drug — P-value vs Effect Size
Run: ?app=app1_blood_pressure_effect

Covers transcript Section 1-2: P-value illusion, Cohen's d, clinical significance

Story: Pharma claims "significant" 1-point BP drop with n=50,000. Is it useful?
You control n and true effect. Watch p-value swing wildly while d stays stable.

Controls:
- UP/DOWN: change raw mean difference (drug effect in mmHg)
- LEFT/RIGHT: change pooled SD (noisiness of population)
- N/M: decrease/increase total n (10 to 50,000)
- G: toggle Glass's Delta (control SD only) vs pooled
- R: reset to classic 1-point trap
"""
from scs import *
import math

def gaussian(x, mean, sd):
    if sd < 0.5: sd = 0.5
    return (1.0 / (sd * math.sqrt(2*math.pi))) * math.exp(-0.5 * ((x-mean)/sd)**2)

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 30
    app.background = rgb(250, 250, 252)

    # classic example values
    app.ctrlMean = 130.0  # systolic
    app.rawDiff = 1.0     # drug lowers by 1
    app.sd = 12.0
    app.ctrlSD = 12.0
    app.n = 50000
    app.useGlass = False

    app.graphLeft = 80
    app.graphRight = 650
    app.graphTop = 110
    app.graphBottom = 380
    app.xMin = 90
    app.xMax = 170

    app.dragging = False

def posX(app, v):
    frac = (v - app.xMin) / (app.xMax - app.xMin)
    return app.graphLeft + frac * (app.graphRight - app.graphLeft)

def valX(app, px):
    frac = (px - app.graphLeft) / (app.graphRight - app.graphLeft)
    return app.xMin + frac * (app.xMax - app.xMin)

def compute(app):
    expMean = app.ctrlMean - app.rawDiff  # drug lowers
    sd_pooled = app.sd
    # Cohen's d
    d = app.rawDiff / sd_pooled if sd_pooled != 0 else 0
    # Hedges g correction
    df = 2*app.n - 2 if app.n>1 else 1
    J = 1 - 3.0/(4*df - 1) if df>1 else 1
    g = d * J
    # Glass delta using ctrl SD
    delta = app.rawDiff / app.ctrlSD if app.ctrlSD!=0 else 0
    # approx t = d * sqrt(n/2) for two groups equal n
    t = d * math.sqrt(app.n/2) if app.n>1 else 0
    # super rough p-value bucket
    if abs(t) > 3.5: p = 0.0004
    elif abs(t) > 2.8: p = 0.005
    elif abs(t) > 2.0: p = 0.04
    elif abs(t) > 1.3: p = 0.18
    else: p = 0.45
    return expMean, d, g, delta, J, t, p

def onMousePress(app, mx, my):
    if app.graphLeft <= mx <= app.graphRight and app.graphTop <= my <= app.graphBottom:
        app.dragging = True

def onMouseDrag(app, mx, my):
    if app.dragging:
        app.rawDiff = max(0, min(30, app.ctrlMean - valX(app, mx)))
        # clamp
        if app.rawDiff < 0.1: app.rawDiff = 0.1

def onMouseRelease(app, mx, my):
    app.dragging = False

def onKeyPress(app, key):
    if key == 'r' or key == 'R':
        app.rawDiff = 1.0
        app.n = 50000
        app.sd = 12.0
        app.ctrlSD = 12.0
    elif key == 'up':
        app.rawDiff = min(30, app.rawDiff + 0.5)
    elif key == 'down':
        app.rawDiff = max(0.1, app.rawDiff - 0.5)
    elif key == 'right':
        app.sd = min(30, app.sd + 1)
        app.ctrlSD = min(30, app.ctrlSD + 1)
    elif key == 'left':
        app.sd = max(2, app.sd - 1)
        app.ctrlSD = max(2, app.ctrlSD - 1)
    elif key == 'm' or key == 'M':
        app.n = min(50000, int(app.n * 1.4 + 5))
    elif key == 'n' or key == 'N':
        app.n = max(10, int(app.n / 1.4))
    elif key == 'g' or key == 'G':
        app.useGlass = not app.useGlass

def redrawAll(app):
    expMean, d, g, delta, J, t, p = compute(app)

    drawLabel("APP 1: The 1-Point Blood Pressure Trap — P-value vs Effect Size", app.width//2, 26, size=18, bold=True, fill=rgb(20,20,30))
    drawLabel("Drag in graph to change drug effect. UP/DOWN effect, LEFT/RIGHT noise, N/M sample size, G Glass Δ, R reset", app.width//2, 48, size=11, fill=rgb(90,90,90))

    # graph bg
    drawRect(app.graphLeft, app.graphTop, app.graphRight-app.graphLeft, app.graphBottom-app.graphTop, fill=rgb(255,255,255), border=rgb(210,210,215), borderWidth=1)
    # x axis
    for v in range(90, 171, 10):
        x = posX(app, v)
        drawLine(x, app.graphBottom, x, app.graphBottom+4, fill=rgb(200,200,200))
        drawLabel(str(v), x, app.graphBottom+12, size=10, fill=rgb(120,120,120))
    drawLabel("Systolic BP (mmHg) — lower is better", (app.graphLeft+app.graphRight)//2, app.graphBottom+26, size=11, fill=rgb(100,100,100))

    # draw two bells
    # control
    ptsC = []
    for i in range(160):
        xv = app.xMin + (app.xMax-app.xMin)*i/159
        yv = gaussian(xv, app.ctrlMean, app.ctrlSD)
        xp = posX(app, xv)
        yp = app.graphBottom - yv * (app.ctrlSD*22) * 12  # scale fudge
        ptsC.append((xp, yp))
    for i in range(len(ptsC)-1):
        drawLine(ptsC[i][0], ptsC[i][1], ptsC[i+1][0], ptsC[i+1][1], fill=rgb(80,130,255), lineWidth=3, opacity=85)
    # exp
    ptsE = []
    for i in range(160):
        xv = app.xMin + (app.xMax-app.xMin)*i/159
        yv = gaussian(xv, expMean, app.sd)
        xp = posX(app, xv)
        yp = app.graphBottom - yv * (app.sd*22) * 12
        ptsE.append((xp, yp))
    for i in range(len(ptsE)-1):
        drawLine(ptsE[i][0], ptsE[i][1], ptsE[i+1][0], ptsE[i+1][1], fill=rgb(255,80,80), lineWidth=3, opacity=85)

    # mean lines
    drawLine(posX(app, app.ctrlMean), app.graphTop, posX(app, app.ctrlMean), app.graphBottom, fill=rgb(80,130,255), lineWidth=2, dashes=True)
    drawLine(posX(app, expMean), app.graphTop, posX(app, expMean), app.graphBottom, fill=rgb(255,80,80), lineWidth=2, dashes=True)
    drawLabel(f"CTRL {app.ctrlMean:.0f}", posX(app, app.ctrlMean), app.graphTop+12, size=11, bold=True, fill=rgb(60,100,200))
    drawLabel(f"DRUG {expMean:.1f}", posX(app, expMean), app.graphTop+28, size=11, bold=True, fill=rgb(200,40,40))

    # raw diff arrow
    drawLine(posX(app, expMean), app.graphBottom-20, posX(app, app.ctrlMean), app.graphBottom-20, fill=rgb(30,30,30), lineWidth=2, arrowEnd=True, arrowStart=True)
    drawLabel(f"raw diff = {app.rawDiff:.1f} mmHg", (posX(app, expMean)+posX(app, app.ctrlMean))/2, app.graphBottom-36, size=12, bold=True)

    # right panel
    px = 690
    drawRect(px, 90, 340, 580, fill=rgb(255,255,255), border=rgb(220,220,225), borderWidth=1, roundness=10)

    drawLabel(f"n per group = {app.n}", px+170, 115, size=16, bold=True)
    drawLabel(f"SD pooled = {app.sd:.1f}  |  SD ctrl = {app.ctrlSD:.1f}", px+170, 135, size=11, fill=rgb(90,90,90))

    # big stats
    drawLabel(f"Cohen's d = diff / SD_pooled", px+20, 165, size=12, bold=True, align='left')
    drawLabel(f"{app.rawDiff:.2f} / {app.sd:.2f} = {d:.3f}", px+20, 185, size=22, bold=True, fill=rgb(20,20,20), align='left')
    interp = "negligible" if abs(d)<0.2 else "small" if abs(d)<0.5 else "medium" if abs(d)<0.8 else "large"
    drawLabel(f"Interpretation: {interp} (0.2 small, 0.5 med, 0.8 large — but context matters!)", px+20, 210, size=11, fill=rgb(80,80,80), align='left')

    drawLabel(f"Hedges' g = d × J  J={J:.4f}", px+20, 240, size=11, bold=True, align='left', fill=rgb(70,70,120))
    drawLabel(f"g = {g:.3f}  (penalizes n<20)", px+20, 258, size=11, align='left', fill=rgb(70,70,120))

    drawLabel(f"Glass's Δ = diff / SD_ctrl = {delta:.3f}", px+20, 280, size=11, bold=True, align='left', fill=rgb(120,80,20))
    drawLabel(f"{'ON — treatment exploded variance, use ctrl as anchor' if app.useGlass else 'OFF — pooling (press G)'}", px+20, 296, size=10, align='left', fill=rgb(120,80,20))

    # p-value illusion
    drawRect(px+15, 320, 310, 110, fill=rgb(250,240,255), border=rgb(190,160,220), borderWidth=1, roundness=8)
    drawLabel("P-value illusion:", px+25, 332, size=12, bold=True, fill=rgb(90,30,130), align='left')
    drawLabel(f"t ≈ d×√(n/2) = {t:.2f}", px+25, 350, size=12, align='left')
    pColor = rgb(0,150,0) if p<0.05 else rgb(180,40,40)
    drawLabel(f"p ≈ {p}  {'→ SIGNIFICANT!' if p<0.05 else '→ not significant'}", px+25, 370, size=14, bold=True, fill=pColor, align='left')
    drawLabel(f"With n=50k, even d=0.08 is p<0.05", px+25, 390, size=11, align='left', fill=rgb(100,40,40))
    drawLabel(f"P says 'not zero'. d says 'how much'.", px+25, 410, size=11, bold=True, align='left')

    # clinical context
    drawRect(px+15, 445, 310, 100, fill=rgb(240,250,240), border=rgb(160,200,160), borderWidth=1, roundness=8)
    drawLabel("Clinical context:", px+25, 457, size=12, bold=True, fill=rgb(30,100,30), align='left')
    if app.rawDiff <= 1.5:
        drawLabel(f"d={d:.2f} small: 1 mmHg saves ~0 lives.", px+25, 475, size=11, align='left')
        drawLabel(f"Mathematically sig, clinically useless.", px+25, 493, size=11, bold=True, align='left', fill=rgb(180,30,30))
    elif app.rawDiff < 5:
        drawLabel(f"d={d:.2f} small but maybe real.", px+25, 475, size=11, align='left')
        drawLabel(f"At population scale, could matter.", px+25, 493, size=11, align='left')
    else:
        drawLabel(f"d={d:.2f} medium/large!", px+25, 475, size=11, align='left')
        drawLabel(f"10 mmHg drop prevents strokes.", px+25, 493, size=11, bold=True, align='left', fill=rgb(30,100,30))
    drawLabel(f"Cohen warned: don't use 0.2/0.5/0.8", px+25, 515, size=10, align='left', fill=rgb(80,80,80))
    drawLabel(f"blindly — domain expertise required.", px+25, 528, size=10, align='left', fill=rgb(80,80,80))

    # mechanic analogy
    drawLabel("Mechanic: P = 'engine turns on'. Effect size = 'goes >5 mph?'", px+170, 610, size=11, fill=rgb(80,80,90), bold=True)
    drawLabel("Try: set diff=1, n=50000 → p<0.05 but useless. Then diff=10, n=30 → bigger d.", px+170, 630, size=10, fill=rgb(90,90,90))
