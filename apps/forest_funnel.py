"""
forest_funnel.py
SCS Meta-Analysis Lab — Forest Plot, Funnel Plot, File Drawer
Run: ?app=forest_funnel

Covers transcript: Gene Glass meta-analysis, fixed vs random (REML intuition),
Q / I² / tau², funnel plot asymmetry, trim-and-fill, publication bias,
Hasselblad-Hedges OR→d bridge

Controls:
- F: toggle Fixed vs Random effects model
- B: toggle publication bias (hide small negative studies)
- T: toggle trim-and-fill imputation
- SPACE: regenerate 20 studies
- UP/DOWN: increase/decrease true tau (heterogeneity)
- Mouse: hover near studies for details
"""
from scs import *
import math
import random

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 10
    app.background = rgb(248, 249, 251)

    app.k = 20
    app.trueMean = 0.4   # true d
    app.trueTau = 0.25   # between-study SD
    app.showFixed = False  # False = random, True = fixed
    app.biasOn = False
    app.trimFillOn = False
    app.hoverIndex = -1

    app.forestLeft = 20
    app.forestRight = 520
    app.funnelLeft = 560
    app.funnelRight = 1030

    generateStudies(app)

def generateStudies(app):
    # generate k studies: each with n, SE, observed d
    app.studies = []  # dict: n, se, d, true
    for i in range(app.k):
        n = random.randint(20, 200)
        # SE approx for Cohen d: sqrt(1/n1 + 1/n2 + d^2/(2*(n1+n2))) simplified
        # use n per group = n
        true_i = random.gauss(app.trueMean, app.trueTau)
        se = math.sqrt(2.0/n + (true_i*true_i)/(4*n)) + random.random()*0.05
        obs = random.gauss(true_i, se)
        app.studies.append({'n': n, 'se': se, 'd': obs, 'true': true_i, 'hidden': False})
    computeMeta(app)

def computeMeta(app):
    studies = [s for s in app.studies if not s['hidden']]
    if len(studies)==0:
        studies = app.studies
    # fixed weights
    w_fixed = []
    for s in studies:
        w = 1.0/(s['se']*s['se']) if s['se']>0 else 0
        w_fixed.append(w)
    sum_w = sum(w_fixed)
    pooled_fixed = sum(w*d['d'] for w,d in zip(w_fixed, studies))/sum_w if sum_w>0 else 0

    # Q statistic
    Q = sum(w * (s['d'] - pooled_fixed)**2 for w,s in zip(w_fixed, studies))
    df = len(studies)-1
    # tau^2 DerSimonian-Laird
    sum_w2 = sum(w*w for w in w_fixed)
    denom = sum_w - sum_w2/sum_w if sum_w!=0 else 1
    tau2 = max(0, (Q - df)/denom) if denom>0 else 0
    tau = math.sqrt(tau2)

    # random weights
    w_rand = []
    for s in studies:
        v = s['se']*s['se'] + tau2
        w = 1.0/v if v>0 else 0
        w_rand.append(w)
    sum_wr = sum(w_rand)
    pooled_random = sum(w*s['d'] for w,s in zip(w_rand, studies))/sum_wr if sum_wr>0 else 0
    se_random = math.sqrt(1.0/sum_wr) if sum_wr>0 else 1

    # I^2
    I2 = max(0, (Q - df)/Q * 100) if Q>0 else 0

    app.meta = {
        'pooled_fixed': pooled_fixed,
        'pooled_random': pooled_random,
        'se_random': se_random,
        'Q': Q,
        'df': df,
        'tau2': tau2,
        'tau': tau,
        'I2': I2,
        'w_fixed': w_fixed,
        'w_rand': w_rand,
        'studies_vis': studies
    }

    # funnel trim-fill simple: mirror positive outliers if bias
    # find studies to impute: reflect studies with d > pooled_random
    if app.biasOn or True:
        # for display, generate imputed
        imputed = []
        for s in studies:
            if s['d'] > pooled_random + 0.1:
                # mirror
                mirror_d = pooled_random - (s['d'] - pooled_random)
                imputed.append({'n': s['n'], 'se': s['se'], 'd': mirror_d, 'true': mirror_d, 'imputed': True})
        app.meta['imputed'] = imputed
    else:
        app.meta['imputed'] = []

def applyBias(app):
    # hide studies: if small n and negative effect, hide (file drawer)
    for s in app.studies:
        if s['n'] < 60 and s['d'] < app.trueMean - 0.2:
            s['hidden'] = app.biasOn and random.random() < 0.75
        else:
            s['hidden'] = False
    computeMeta(app)

def onKeyPress(app, key):
    if key == 'f' or key == 'F':
        app.showFixed = not app.showFixed
    elif key == 'b' or key == 'B':
        app.biasOn = not app.biasOn
        applyBias(app)
    elif key == 't' or key == 'T':
        app.trimFillOn = not app.trimFillOn
    elif key == ' ':
        generateStudies(app)
        if app.biasOn:
            applyBias(app)
    elif key == 'up':
        app.trueTau = min(0.6, app.trueTau + 0.05)
        generateStudies(app)
        if app.biasOn: applyBias(app)
    elif key == 'down':
        app.trueTau = max(0.0, app.trueTau - 0.05)
        generateStudies(app)
        if app.biasOn: applyBias(app)
    elif key == 'r' or key == 'R':
        app.trueMean = 0.4
        app.trueTau = 0.25
        app.biasOn = False
        app.trimFillOn = False
        app.showFixed = False
        generateStudies(app)

def onMouseMove(app, mx, my):
    # find hovered study in forest plot
    # forest plot y positions
    top = 110
    step = 22
    app.hoverIndex = -1
    for i, s in enumerate(app.meta.get('studies_vis', [])):
        y = top + i*step
        if abs(my - y) < 10 and app.forestLeft <= mx <= app.forestRight:
            app.hoverIndex = i
            break

def redrawAll(app):
    drawLabel("Forest + Funnel — The Engine of Meta-Analysis", app.width//2, 24, size=18, bold=True)
    drawLabel("F=fixed/random  B=file-drawer bias  T=trim+fill  SPACE=new studies  UP/DOWN=heterogeneity  R=reset", app.width//2, 44, size=11, fill=rgb(90,90,90))

    # left: forest plot
    drawRect(app.forestLeft, 60, app.forestRight-app.forestLeft, 620, fill=rgb(255,255,255), border=rgb(210,210,215), borderWidth=1, roundness=8)
    drawLabel("Forest Plot — 20 studies + diamond = pooled truth", (app.forestLeft+app.forestRight)//2, 75, size=13, bold=True)

    # zero line
    # map d to x: d range -1 to 1.5
    dMin, dMax = -1.0, 1.5
    def xFromD(d):
        frac = (d - dMin)/(dMax - dMin)
        return app.forestLeft + 90 + frac * (app.forestRight - app.forestLeft - 110)
    zeroX = xFromD(0)
    drawLine(zeroX, 95, zeroX, 95+app.k*22+40, fill=rgb(200,200,200), lineWidth=1, dashes=True)
    drawLabel("0 = no effect", zeroX, 98, size=10, fill=rgb(130,130,130))

    # x axis labels
    for d in [-1, -0.5, 0, 0.5, 1.0, 1.5]:
        drawLabel(f"{d}", xFromD(d), 95+app.k*22+28, size=10, fill=rgb(100,100,100))

    top = 110
    step = 22
    for i, s in enumerate(app.meta.get('studies_vis', [])):
        y = top + i*step
        w = app.meta['w_rand'] if not app.showFixed else app.meta['w_fixed']
        # weight determines square size
        wi = w[i] if i < len(w) else 0
        maxW = max(w) if w else 1
        sq = 4 + 10 * (wi / maxW) if maxW>0 else 4

        # CI: d ± 1.96*se
        ciLow = s['d'] - 1.96*s['se']
        ciHigh = s['d'] + 1.96*s['se']
        xLow = xFromD(ciLow)
        xHigh = xFromD(ciHigh)
        xMid = xFromD(s['d'])

        isHover = (i == app.hoverIndex)
        col = rgb(30,120,255) if not isHover else rgb(255,50,50)
        drawLine(xLow, y, xHigh, y, fill=col, lineWidth=2 if not isHover else 3)
        drawRect(xMid - sq//2, y - sq//2, sq, sq, fill=col, border=rgb(255,255,255), borderWidth=1)

        drawLabel(f"S{i+1} n={s['n']}", app.forestLeft+8, y, size=9, align='left', fill=rgb(80,80,80))
        if isHover:
            drawLabel(f"d={s['d']:.2f} se={s['se']:.2f}", app.forestLeft+88, y-12, size=10, bold=True, fill=rgb(200,30,30), align='left')

    # pooled diamond
    pooled = app.meta['pooled_fixed'] if app.showFixed else app.meta['pooled_random']
    se_p = math.sqrt(1/sum(app.meta['w_fixed'])) if app.showFixed else app.meta['se_random']
    ciL = pooled - 1.96*se_p
    ciR = pooled + 1.96*se_p
    yDiamond = top + app.k*step + 18
    xC = xFromD(pooled)
    xL = xFromD(ciL)
    xR = xFromD(ciR)
    # diamond polygon
    drawPolygon(xC, yDiamond-10, xR, yDiamond, xC, yDiamond+10, xL, yDiamond, fill=rgb(20,20,20), border=rgb(0,0,0), borderWidth=1)
    drawLabel(f"Pooled {'FIXED' if app.showFixed else 'RANDOM'} d={pooled:.3f} [{ciL:.2f}, {ciR:.2f}]", xC, yDiamond+24, size=11, bold=True, fill=rgb(20,20,20))

    # stats box
    drawRect(app.forestLeft+8, yDiamond+36, 490, 72, fill=rgb(248,245,255), border=rgb(190,170,210), borderWidth=1, roundness=6)
    drawLabel(f"Q={app.meta['Q']:.1f}  df={app.meta['df']}  tau²={app.meta['tau2']:.3f}  tau={app.meta['tau']:.3f}", app.forestLeft+18, yDiamond+46, size=10, align='left', bold=True)
    drawLabel(f"I²={app.meta['I2']:.0f}% → { '0% = all noise, 75% = real differences' if app.meta['I2']>0 else 'no heterogeneity'}", app.forestLeft+18, yDiamond+62, size=10, align='left')
    modelDesc = "Fixed: one true effect, variance = sampling only" if app.showFixed else "Random: distribution of true effects, REML/tau² (Borenstein: choose by theory!)"
    drawLabel(modelDesc, app.forestLeft+18, yDiamond+78, size=9, align='left', fill=rgb(80,60,100))
    drawLabel(f"True tau setting={app.trueTau:.2f} (UP/DOWN)", app.forestLeft+18, yDiamond+92, size=9, align='left', fill=rgb(100,100,100))

    # right: funnel plot
    drawRect(app.funnelLeft, 60, app.funnelRight-app.funnelLeft, 620, fill=rgb(255,255,255), border=rgb(210,210,215), borderWidth=1, roundness=8)
    drawLabel("Funnel Plot — Detecting the File Drawer", (app.funnelLeft+app.funnelRight)//2, 75, size=13, bold=True)
    # funnel axes: x = effect, y = precision (1/se) or se inverted. Use y = se, top = small se (precise)
    fTop = 105
    fBottom = 95+app.k*22+70
    fLeft = app.funnelLeft + 60
    fRight = app.funnelRight - 20
    def fx(d): 
        return fLeft + (d - dMin)/(dMax-dMin)*(fRight-fLeft)
    def fy(se):
        # se 0.05 to 0.6 -> y
        seMin, seMax = 0.02, 0.6
        frac = (se - seMin)/(seMax - seMin)
        return fTop + frac*(fBottom - fTop)

    # draw funnel contours (triangle)
    pooledX = fx(pooled)
    drawLine(pooledX, fy(0.02), fx(dMin), fy(0.6), fill=rgb(220,220,220), lineWidth=1, dashes=True)
    drawLine(pooledX, fy(0.02), fx(dMax), fy(0.6), fill=rgb(220,220,220), lineWidth=1, dashes=True)
    drawLine(fx(0), fTop, fx(0), fBottom, fill=rgb(200,200,200), dashes=True)

    drawLabel("effect d →", (fLeft+fRight)//2, fBottom+14, size=10, fill=rgb(100,100,100))
    drawLabel("precision ↑", fLeft-22, (fTop+fBottom)//2, size=10, fill=rgb(100,100,100), rotateAngle=-90)

    # plot studies
    for s in app.meta['studies_vis']:
        x = fx(s['d'])
        y = fy(s['se'])
        drawCircle(x, y, 6, fill=rgb(30,120,255), border=rgb(255,255,255), borderWidth=1, opacity=85)

    # imputed studies if trim-fill on
    if app.trimFillOn:
        for s in app.meta.get('imputed', [])[:6]:
            x = fx(s['d'])
            y = fy(s['se'])
            drawCircle(x, y, 6, fill=rgb(255,100,100), border=rgb(255,255,255), borderWidth=1, opacity=60)
            drawLine(x, y, fx(pooled + (pooled - s['d'])), fy(s['se']), fill=rgb(255,100,100), lineWidth=1, dashes=True, opacity=50)
        drawLabel("Trim-Fill: red = imputed file-drawer studies", (fLeft+fRight)//2, fTop+12, size=10, fill=rgb(200,30,30), bold=True)

    if app.biasOn:
        drawLabel("BIAS ON: small negative studies hidden → asymmetry", (fLeft+fRight)//2, fTop-2, size=11, bold=True, fill=rgb(200,30,30))
        # highlight empty corner
        drawRect(fLeft, fy(0.3), fx(pooled)-fLeft, fy(0.6)-fy(0.3), fill=rgb(255,200,200), opacity=20, border=None)
        drawLabel("missing corner = file drawer", fLeft+10, fy(0.45), size=10, fill=rgb(180,50,50), align='left')
    else:
        drawLabel("Symmetrical = no bias (random scatter)", (fLeft+fRight)//2, fTop-2, size=11, fill=rgb(60,120,60))

    # bottom explanation
    drawRect(20, 610, 1010, 80, fill=rgb(255,255,255), border=rgb(210,210,215), borderWidth=1, roundness=8)
    drawLabel("What you see: Squares sized by weight (1/SE²). Diamond = pooled truth. I² = % variance due to real differences, not chance. Q = chi-squared heterogeneity test.", 30, 625, size=10, align='left', fill=rgb(60,60,60))
    drawLabel("File drawer: journals publish positive. Funnel becomes asymmetric. Trim-and-fill mirrors positive studies to left to estimate bias-corrected effect.", 30, 640, size=10, align='left', fill=rgb(60,60,60))
    drawLabel("Bridge: OR → d via Hasselblad-Hedges: d = log(OR) × √3 / π  (log centers at 0, π/√3 = SD of logistic)", 30, 655, size=10, align='left', fill=rgb(80,60,100), bold=True)
    drawLabel("For scholars: fixed = Platonic one true d. Random = family of true ds (age, dose). Choose by theory, not by Q p-value! — Borenstein 2009", 30, 670, size=10, align='left', fill=rgb(90,90,90))
