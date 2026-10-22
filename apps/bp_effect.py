"""
bp_effect.py
SCS App 1 — 1050x700 — P-value vs Effect Size (Blood Pressure Trap)
Run: ?app=bp_effect

Uses full 1050x700: left 65% graph, right 35% stats
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
    app.background = rgb(248, 249, 252)

    app.ctrlMean = 130.0
    app.rawDiff = 1.0
    app.sd = 12.0
    app.ctrlSD = 12.0
    app.n = 50000
    app.useGlass = False

    # LAYOUT 1050x700
    app.gLeft = 70
    app.gRight = 680
    app.gTop = 80
    app.gBottom = 400
    app.pLeft = 700
    app.pRight = 1030
    app.pTop = 80

    app.xMin = 88
    app.xMax = 172
    app.dragging = False

def posX(app, v):
    frac = (v - app.xMin) / (app.xMax - app.xMin)
    return app.gLeft + frac * (app.gRight - app.gLeft)

def valX(app, px):
    frac = (px - app.gLeft) / (app.gRight - app.gLeft)
    return app.xMin + frac * (app.xMax - app.xMin)

def compute(app):
    expMean = app.ctrlMean - app.rawDiff
    d = app.rawDiff / app.sd if app.sd !=0 else 0
    df = 2*app.n -2 if app.n>1 else 1
    J = 1 - 3.0/(4*df -1) if df>1 else 1
    g = d * J
    delta = app.rawDiff / app.ctrlSD if app.ctrlSD!=0 else 0
    t = d * math.sqrt(app.n/2) if app.n>1 else 0
    if abs(t) > 3.5: p = 0.0004
    elif abs(t) > 2.8: p = 0.005
    elif abs(t) > 2.0: p = 0.04
    elif abs(t) > 1.3: p = 0.18
    else: p = 0.45
    return expMean, d, g, delta, J, t, p

def onMousePress(app, mx, my):
    if app.gLeft <= mx <= app.gRight and app.gTop <= my <= app.gBottom:
        app.dragging = True
        app.rawDiff = max(0.2, min(30, app.ctrlMean - valX(app, mx)))

def onMouseDrag(app, mx, my):
    if app.dragging:
        app.rawDiff = max(0.2, min(30, app.ctrlMean - valX(app, mx)))

def onMouseRelease(app, mx, my):
    app.dragging = False

def onKeyPress(app, key):
    if key == 'r' or key == 'R':
        app.rawDiff = 1.0; app.n = 50000; app.sd = 12.0; app.ctrlSD = 12.0; app.useGlass=False
    elif key == 'up': app.rawDiff = min(30, app.rawDiff + 0.5)
    elif key == 'down': app.rawDiff = max(0.2, app.rawDiff - 0.5)
    elif key == 'right': app.sd = min(30, app.sd + 1); app.ctrlSD = min(30, app.ctrlSD + 1)
    elif key == 'left': app.sd = max(3, app.sd - 1); app.ctrlSD = max(3, app.ctrlSD - 1)
    elif key == 'm' or key == 'M': app.n = min(50000, int(app.n*1.35+10))
    elif key == 'n' or key == 'N': app.n = max(10, int(app.n/1.35))
    elif key == 'g' or key == 'G': app.useGlass = not app.useGlass

def redrawAll(app):
    expMean, d, g, delta, J, t, p = compute(app)

    # HEADER — full width
    drawRect(0,0,1050,62, fill=rgb(20,22,30), border=None)
    drawLabel("BP_EFFECT.PY — Why P < 0.05 Means Nothing Without Effect Size", 525, 20, size=18, bold=True, fill=rgb(255,255,255))
    drawLabel("Drag graph to change drug effect | UP/DOWN effect | LEFT/RIGHT noise | N/M sample size | G Glass Δ | R reset", 525, 42, size=11, fill=rgb(180,180,190))

    # GRAPH BACKGROUND — uses left 65%
    drawRect(app.gLeft-1, app.gTop-1, app.gRight-app.gLeft+2, app.gBottom-app.gTop+2, fill=rgb(255,255,255), border=rgb(200,205,210), borderWidth=1, roundness=8)
    # grid
    for v in range(90, 171, 10):
        x = posX(app, v)
        drawLine(x, app.gTop, x, app.gBottom, fill=rgb(235,235,238), lineWidth=1)
        drawLine(x, app.gBottom, x, app.gBottom+5, fill=rgb(180,180,180))
        drawLabel(str(v), x, app.gBottom+14, size=11, fill=rgb(100,100,100))
    drawLabel("Systolic BP (mmHg) — lower = better", (app.gLeft+app.gRight)//2, app.gBottom+30, size=12, bold=True, fill=rgb(80,80,80))

    # compute scaled bells to fit height 220px
    maxGaussC = 1.0/(app.ctrlSD*2.5066)
    maxGaussE = 1.0/(app.sd*2.5066)
    maxG = max(maxGaussC, maxGaussE)
    hScale = 210 / maxG if maxG>0 else 200

    # draw fills under curves
    ptsC=[]; ptsE=[]
    for i in range(200):
        xv = app.xMin + (app.xMax-app.xMin)*i/199
        yc = gaussian(xv, app.ctrlMean, app.ctrlSD)
        ye = gaussian(xv, expMean, app.sd)
        xc = posX(app, xv)
        ycPix = app.gBottom - yc*hScale
        yePix = app.gBottom - ye*hScale
        ptsC.append((xc, ycPix, yc))
        ptsE.append((xc, yePix, ye))

    # overlap shading first
    for i in range(len(ptsC)-1):
        x1 = ptsC[i][0]
        # fill under with low alpha
        drawLine(x1, ptsC[i][1], x1, app.gBottom, fill=rgb(80,130,255), lineWidth=1, opacity=18)
        drawLine(x1, ptsE[i][1], x1, app.gBottom, fill=rgb(255,80,80), lineWidth=1, opacity=18)
    # lines
    for i in range(len(ptsC)-1):
        drawLine(ptsC[i][0], ptsC[i][1], ptsC[i+1][0], ptsC[i+1][1], fill=rgb(60,110,230), lineWidth=3, opacity=90)
        drawLine(ptsE[i][0], ptsE[i][1], ptsE[i+1][0], ptsE[i+1][1], fill=rgb(220,50,50), lineWidth=3, opacity=90)

    # mean dashed lines
    cx = posX(app, app.ctrlMean)
    ex = posX(app, expMean)
    drawLine(cx, app.gTop+10, cx, app.gBottom, fill=rgb(60,110,230), lineWidth=2, dashes=True, opacity=80)
    drawLine(ex, app.gTop+10, ex, app.gBottom, fill=rgb(220,50,50), lineWidth=2, dashes=True, opacity=80)
    drawCircle(cx, app.gTop+18, 7, fill=rgb(60,110,230), border=rgb(255,255,255), borderWidth=2)
    drawCircle(ex, app.gTop+18, 7, fill=rgb(220,50,50), border=rgb(255,255,255), borderWidth=2)
    drawLabel(f"CTRL {app.ctrlMean:.0f}  σ={app.ctrlSD:.0f}", cx, app.gTop+6, size=11, bold=True, fill=rgb(60,110,230))
    drawLabel(f"DRUG {expMean:.1f}  σ={app.sd:.0f}", ex, app.gTop+32, size=11, bold=True, fill=rgb(200,30,30))

    # raw diff double arrow bottom of graph
    drawLine(ex, app.gBottom-22, cx, app.gBottom-22, fill=rgb(30,30,30), lineWidth=2, arrowStart=True, arrowEnd=True)
    drawLabel(f"raw diff = {app.rawDiff:.1f} mmHg", (ex+cx)/2, app.gBottom-38, size=12, bold=True, fill=rgb(20,20,20))

    # RIGHT PANEL — full height usage
    drawRect(app.pLeft, app.pTop, app.pRight-app.pLeft, 610, fill=rgb(255,255,255), border=rgb(200,205,210), borderWidth=1, roundness=10)

    y = app.pTop + 18
    drawLabel(f"n per group = {app.n:,}", app.pLeft+165, y, size=16, bold=True); y+=22
    drawLabel(f"SD pooled={app.sd:.1f}  SD ctrl={app.ctrlSD:.1f}  J={J:.4f}", app.pLeft+165, y, size=11, fill=rgb(90,90,90)); y+=22

    drawRect(app.pLeft+12, y, 306, 62, fill=rgb(240,245,255), border=rgb(180,195,230), borderWidth=1, roundness=8)
    drawLabel("Cohen's d = diff / SD_pooled", app.pLeft+20, y+10, size=12, bold=True, align='left')
    drawLabel(f"{app.rawDiff:.2f} / {app.sd:.2f} = {d:.3f}", app.pLeft+20, y+30, size=22, bold=True, align='left')
    interp = "negligible" if abs(d)<0.2 else "small" if abs(d)<0.5 else "medium" if abs(d)<0.8 else "large"
    drawLabel(f"{interp}  (0.2/0.5/0.8 benchmarks ≠ law!)", app.pLeft+20, y+50, size=11, fill=rgb(70,70,90), align='left')
    y+=76

    drawRect(app.pLeft+12, y, 306, 56, fill=rgb(245,240,255), border=rgb(190,175,220), borderWidth=1, roundness=8)
    drawLabel(f"Hedges' g = d × J = {g:.3f}  (J penalizes n<20 by 5-10%)", app.pLeft+20, y+12, size=11, bold=True, fill=rgb(70,50,100), align='left')
    drawLabel(f"Glass Δ = diff / SD_ctrl = {delta:.3f} {'[ON]' if app.useGlass else '[OFF press G]'}", app.pLeft+20, y+30, size=11, bold=True, fill=rgb(110,70,20), align='left')
    drawLabel("Use Δ when treatment explodes variance", app.pLeft+20, y+44, size=10, fill=rgb(110,90,60), align='left')
    y+=70

    # P-VALUE ILLUSION — big, readable
    drawRect(app.pLeft+12, y, 306, 108, fill=rgb(255,240,245), border=rgb(230,160,180), borderWidth=1, roundness=8)
    drawLabel("P-VALUE ILLUSION", app.pLeft+20, y+12, size=12, bold=True, fill=rgb(150,30,60), align='left')
    drawLabel(f"t ≈ d·√(n/2) = {t:.2f}", app.pLeft+20, y+30, size=12, align='left')
    pCol = rgb(0,140,0) if p<0.05 else rgb(180,30,30)
    drawLabel(f"p ≈ {p}  {'→ SIGNIFICANT!' if p<0.05 else '→ not significant'}", app.pLeft+20, y+48, size=14, bold=True, fill=pCol, align='left')
    drawLabel("With n=50k, d=0.08 → p<0.05", app.pLeft+20, y+66, size=11, align='left', fill=rgb(120,40,50))
    drawLabel("P = engine on? d = goes >5 mph?", app.pLeft+20, y+82, size=11, bold=True, align='left')
    drawLabel("Same as transcript car analogy", app.pLeft+20, y+96, size=10, fill=rgb(100,80,80), align='left')
    y+=122

    drawRect(app.pLeft+12, y, 306, 108, fill=rgb(240,255,240), border=rgb(160,200,160), borderWidth=1, roundness=8)
    drawLabel("CLINICAL CONTEXT > BENCHMARKS", app.pLeft+20, y+12, size=11, bold=True, fill=rgb(30,90,30), align='left')
    if app.rawDiff <= 1.5:
        drawLabel("d≈0.08 small → 1 mmHg saves", app.pLeft+20, y+30, size=11, align='left')
        drawLabel("~0 lives. Math sig, clinically useless.", app.pLeft+20, y+46, size=11, bold=True, fill=rgb(180,30,30), align='left')
    elif app.rawDiff < 5:
        drawLabel(f"d={d:.2f} small, but at scale of", app.pLeft+20, y+30, size=11, align='left')
        drawLabel("millions, could matter.", app.pLeft+20, y+46, size=11, align='left')
    else:
        drawLabel(f"d={d:.2f} medium/large!", app.pLeft+20, y+30, size=11, align='left')
        drawLabel("10 mmHg prevents strokes.", app.pLeft+20, y+46, size=11, bold=True, fill=rgb(30,90,30), align='left')
    drawLabel("Cohen warned: don't use 0.2/0.5/0.8", app.pLeft+20, y+66, size=10, align='left', fill=rgb(80,80,80))
    drawLabel("blindly. Mortality 0.2 = thousands saved.", app.pLeft+20, y+80, size=10, align='left', fill=rgb(80,80,80))
    drawLabel("Fun rating 0.8 = trivial.", app.pLeft+20, y+94, size=10, align='left', fill=rgb(80,80,80))

    # footer bar
    drawRect(0, 655, 1050, 45, fill=rgb(20,22,30), border=None)
    drawLabel("Lesson: Effect size strips sample-size dependency. P tells you 'not zero', d tells you 'how much & does it matter?'", 525, 678, size=12, fill=rgb(220,220,230))
