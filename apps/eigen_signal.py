"""
eigen_signal.py
SCS Eigen Signal Lab — Finding Invariant Truth in Noise
Run: ?app=eigen_signal

Fixed version based on transcript:

Transcript core ideas:
- Biological populations → mean differences & SD → univariate effect size (Cohen's d)
- Complex research measures multiple correlated outcomes (BP, cholesterol, HR, weight)
- Multivariate effect size = Mahalanobis D = D² = (μ1-μ2)ᵀ Σ⁻¹ (μ1-μ2)
- Σ = covariance matrix = grid of how variables co-move
- To understand Σ, you decompose it into eigenvalues/eigenvectors
- Geometric view: applying M shears/stretches space, almost every vector spins off path
- Eigenvectors = invariant directions: they scale by λ but don't change direction
- Hunting for true effect in noisy correlated data = hunting for eigenvector in transform
- In eigenvalue.py: drag test vector, it spins wildly; when mouse hits true eigen span, dash lines LOCK

Required interactions (now actually working):
- 1/2/3/4: stretch / shear / rotation 90° / reflection
- Drag/click: move test vector (blue). Red = M·v transformed
- Mouse near eigenvector → SNAP + SIGNAL LOCKED (vector stops spinning, lines go solid gold)
- C: toggle covariance ellipse (blood pressure vs cholesterol)
- B: toggle blur = add variance → ellipse grows → Cohen's d shrinks
- S: toggle Sobel-like edge mode → highlight max difference (statistical Sobel = effect size)
- R: reset

Visual mapping:
- Covariance ellipse = Mahalanobis geometry. Eigenvectors = principal axes.
- Gaussian blur = convolution with bell curve = weighted average = increases SD / variance
- Sobel = Gx,Gy gradient = finds max difference = same logic as d = (μ_exp-μ_ctrl)/SD_pooled
"""

from scs import *
import math
import random

def matVecMul(M, v):
    return [M[0][0]*v[0] + M[0][1]*v[1], M[1][0]*v[0] + M[1][1]*v[1]]

def dot(a,b):
    return a[0]*b[0] + a[1]*b[1]

def cross(a,b):
    # 2D cross product magnitude
    return a[0]*b[1] - a[1]*b[0]

def norm(v):
    return math.hypot(v[0], v[1])

def normalize(v):
    m = math.hypot(v[0], v[1])
    if m < 1e-9:
        return [1,0]
    return [v[0]/m, v[1]/m]

def eigen2x2(M):
    a,b = M[0][0], M[0][1]
    c,d = M[1][0], M[1][1]
    tr = a+d
    det = a*d - b*c
    disc = tr*tr - 4*det
    if disc < -1e-9:
        return None  # complex = rotation, no real eigenvectors = pure noise
    disc = max(0.0, disc)
    sqrtD = math.sqrt(disc)
    l1 = (tr + sqrtD)/2
    l2 = (tr - sqrtD)/2
    def vecFor(l):
        # solve (M - lI) v = 0
        if abs(b) > 1e-6:
            return [b, l - a]
        elif abs(c) > 1e-6:
            return [l - d, c]
        else:
            # diagonal
            if abs(a-l) < abs(d-l):
                return [1,0]
            else:
                return [0,1]
    v1 = normalize(vecFor(l1))
    v2 = normalize(vecFor(l2))
    return [(l1, v1), (l2, v2)]

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 30
    app.background = gradient(rgb(15,17,21), rgb(26,29,36), start='top')

    app.centerX = 380
    app.centerY = 360
    app.scale = 110
    app.testMag = 1.5

    app.transIndex = 0
    app.transformations = [
        {'name': 'Stretch (positive λ)', 'M': [[1.8, 0.2],[0.2, 0.7]], 'key':'1', 'desc': '2 real eigen dirs, both scale >0'},
        {'name': 'Shear (defective)', 'M': [[1, 0.9],[0, 1]], 'key':'2', 'desc': 'repeated λ=1, only 1 true invariant line'},
        {'name': 'Rotation 90° (no real eigen)', 'M': [[0, -1],[1, 0]], 'key':'3', 'desc': 'spins EVERY vector = pure noise, no invariant'},
        {'name': 'Reflection (neg λ)', 'M': [[1.2, 0.3],[0.3, -0.8]], 'key':'4', 'desc': 'one axis flips direction (λ<0)'},
    ]

    app.testVec = [1, 0.5]
    app.testVec = normalize(app.testVec)
    app.testVec = [app.testVec[0]*app.testMag, app.testVec[1]*app.testMag]

    app.showEllipse = True
    app.blurAmount = 0  # 0-3
    app.sobelMode = False

    app.snapThreshold = 0.14  # sin(theta) ~ 8 degrees
    app.locked = False
    app.lockedEigenIndex = None
    app.lockedLambda = None
    app.lockedVec = None  # the eigen vec we locked to
    app.dragging = False

    # covariance for Mahalanobis demo: corr between BP and cholesterol
    app.cov = [[1.0, 0.7],[0.7, 1.0]]
    app.rho = 0.7

    # generate fake correlated data cloud (BP vs cholesterol)
    app.dataPoints = []
    random.seed(7)
    for _ in range(90):
        # Box-Muller for Gaussian
        # use random.gauss if available
        try:
            z1 = random.gauss(0,1)
            z2 = random.gauss(0,1)
        except:
            # fallback
            u1 = random.random()
            u2 = random.random()
            r = math.sqrt(-2*math.log(max(1e-9, u1)))
            th = 2*math.pi*u2
            z1 = r*math.cos(th)
            z2 = r*math.sin(th)
        # correlate
        x = z1
        y = app.rho*z1 + math.sqrt(max(0, 1-app.rho*app.rho))*z2
        # scale down to fit
        app.dataPoints.append([x*0.55, y*0.55])

    # for visual spin feedback
    app.lastAngleDiff = 0

def getCurrentM(app):
    return app.transformations[app.transIndex]['M']

def getCurrentEig(app):
    return eigen2x2(getCurrentM(app))

def screenToMath(app, mx, my):
    dx = (mx - app.centerX)/app.scale
    dy = (app.centerY - my)/app.scale
    return [dx, dy]

def mathToScreen(app, v):
    return (app.centerX + v[0]*app.scale, app.centerY - v[1]*app.scale)

def findClosestEigen(app, testVec):
    eig = getCurrentEig(app)
    if not eig:
        return None, None, 999
    tvNorm = normalize(testVec)
    best = None
    bestIdx = None
    bestCross = 999
    bestDot = 0
    for idx, (lam, ev) in enumerate(eig):
        # we consider both ev and -ev same span, so use abs cross and abs dot
        cr = abs(cross(tvNorm, ev))  # |sin theta|
        d = dot(tvNorm, ev)
        # prefer smallest sin
        if cr < bestCross:
            bestCross = cr
            best = (lam, ev)
            bestIdx = idx
            bestDot = d
    return best, bestIdx, bestCross, bestDot

def updateTestVecFromMouse(app, mx, my):
    mVec = screenToMath(app, mx, my)
    mag = norm(mVec)
    if mag < 0.12:
        return
    # normalize to testMag
    mVec = normalize(mVec)
    mVec = [mVec[0]*app.testMag, mVec[1]*app.testMag]

    eig = getCurrentEig(app)
    if eig:
        # check proximity to any eigen span
        closest, cIdx, cCross, cDot = findClosestEigen(app, mVec)
        if closest and cCross < app.snapThreshold:
            lam, ev = closest
            # SNAP: lock to eigenvector, preserve side (sign)
            sign = 1 if cDot >= 0 else -1
            snapped = [ev[0]*sign*app.testMag, ev[1]*sign*app.testMag]
            app.testVec = snapped
            app.locked = True
            app.lockedEigenIndex = cIdx
            app.lockedLambda = lam
            app.lockedVec = [ev[0]*sign, ev[1]*sign]
            return

    # not near eigen → free
    app.testVec = mVec
    app.locked = False
    app.lockedEigenIndex = None
    app.lockedLambda = None
    app.lockedVec = None

def onMousePress(app, mx, my):
    app.dragging = True
    updateTestVecFromMouse(app, mx, my)

def onMouseDrag(app, mx, my):
    app.dragging = True
    updateTestVecFromMouse(app, mx, my)

def onMouseMove(app, mx, my):
    # allow hover hunt even without press, as transcript says drag around
    if app.dragging:
        updateTestVecFromMouse(app, mx, my)
    else:
        # still update for hover detection, but don't require drag for snap demo
        # Comment out if you want drag-only
        updateTestVecFromMouse(app, mx, my)

def onMouseRelease(app, mx, my):
    app.dragging = False

def onKeyPress(app, key):
    if key in ('1','2','3','4'):
        app.transIndex = int(key)-1
        # re-evaluate lock for new M
        mVec = app.testVec
        eig = getCurrentEig(app)
        if eig:
            closest, cIdx, cCross, cDot = findClosestEigen(app, mVec)
            if closest and cCross < app.snapThreshold:
                lam, ev = closest
                sign = 1 if cDot >= 0 else -1
                app.testVec = [ev[0]*sign*app.testMag, ev[1]*sign*app.testMag]
                app.locked = True
                app.lockedEigenIndex = cIdx
                app.lockedLambda = lam
                app.lockedVec = [ev[0]*sign, ev[1]*sign]
            else:
                app.locked = False
                app.lockedEigenIndex = None
                app.lockedLambda = None
        else:
            app.locked = False
    elif key == 'c' or key == 'C':
        app.showEllipse = not app.showEllipse
    elif key == 'b' or key == 'B':
        app.blurAmount = (app.blurAmount + 1) % 4  # 0-3 → variance multiplier
        # blur also breaks lock visually because ellipse grows, but keep eigen lock for transform
    elif key == 's' or key == 'S':
        app.sobelMode = not app.sobelMode
    elif key == 'r' or key == 'R':
        app.testVec = [1,0.5]
        app.testVec = normalize(app.testVec)
        app.testVec = [app.testVec[0]*app.testMag, app.testVec[1]*app.testMag]
        app.blurAmount = 0
        app.sobelMode = False
        app.transIndex = 0
        app.locked = False
        app.lockedEigenIndex = None
        app.lockedLambda = None
        app.lockedVec = None

def redrawAll(app):
    M = getCurrentM(app)
    eig = getCurrentEig(app)
    tv = app.testVec
    transVec = matVecMul(M, tv)

    # ---- title bar ----
    drawLabel("Eigen Signal Lab — Invariant Truth in Multivariate Noise", 520, 28, size=24, bold=True, fill=rgb(230,230,240))
    tInfo = app.transformations[app.transIndex]
    drawLabel(f"{tInfo['key']}: {tInfo['name']} — {tInfo['desc']} | 1-4 switch | C ellipse | B blur | S Sobel | R reset | Drag to hunt eigen", 520, 55, size=15, fill=rgb(160,160,170))

    # ---- grid ----
    drawLine(50, app.centerY, 720, app.centerY, fill=rgb(60,60,70), lineWidth=1)
    drawLine(app.centerX, 90, app.centerX, 620, fill=rgb(60,60,70), lineWidth=1)
    for i in range(-3,4):
        if i==0: continue
        x = app.centerX + i*app.scale
        drawLine(x, 90, x, 620, fill=rgb(40,40,50), lineWidth=1, dashes=True, opacity=40)
        y = app.centerY + i*app.scale
        drawLine(50, y, 720, y, fill=rgb(40,40,50), lineWidth=1, dashes=True, opacity=40)
    drawLabel("0", app.centerX+6, app.centerY+14, size=15, fill=rgb(90,90,90))

    # ---- covariance ellipse (Mahalanobis) ----
    blurScale = 1 + app.blurAmount*0.45
    covEig = eigen2x2(app.cov)

    if app.showEllipse and covEig:
        # data points cloud (BP vs cholesterol correlation)
        for pt in app.dataPoints:
            # scale point by blur
            px = pt[0]*blurScale
            py = pt[1]*blurScale
            sx, sy = mathToScreen(app, [px, py])
            # color fades with blur
            alpha = 70 if app.blurAmount==0 else 55
            drawCircle(sx, sy, 3, fill=rgb(100,220,140), opacity=alpha)

        # ellipse axes = eigenvectors of covariance
        for idx, (lam, vec) in enumerate(covEig):
            scale = math.sqrt(max(0.1, lam)) * blurScale * app.scale * 1.25
            x2 = app.centerX + vec[0]*scale
            y2 = app.centerY - vec[1]*scale
            col = rgb(80,200,120) if idx==0 else rgb(80,160,200)
            drawLine(app.centerX, app.centerY, x2, y2, fill=col, lineWidth=3, opacity=75)
            drawLabel(f"cov λ={lam:.2f}", x2+10, y2, size=16, fill=col, bold=True)

        # ellipse outline polygon (Mahalanobis distance = 1.5 SD)
        pts = []
        for deg in range(0, 360, 5):
            rad = math.radians(deg)
            c, s = math.cos(rad), math.sin(rad)
            lam1, v1 = covEig[0]
            lam2, v2 = covEig[1]
            # sqrt covariance transform
            px = (math.sqrt(lam1)*c*v1[0] + math.sqrt(lam2)*s*v2[0]) * blurScale * 1.5
            py = (math.sqrt(lam1)*c*v1[1] + math.sqrt(lam2)*s*v2[1]) * blurScale * 1.5
            sx = app.centerX + px*app.scale
            sy = app.centerY - py*app.scale
            pts.append((sx, sy))
        for i in range(len(pts)):
            x1,y1 = pts[i]
            x2,y2 = pts[(i+1)%len(pts)]
            drawLine(x1,y1,x2,y2, fill=rgb(100,220,140), lineWidth=2, opacity=70)

        # label
        drawLabel(f"Mahalanobis ellipse (corr={app.rho}) — blur ×{blurScale:.2f} = ↑variance", app.centerX, 95, size=15, fill=rgb(100,220,140))

    # ---- eigenvector spans (invariant directions) ----
    if eig:
        for idx, (lam, vec) in enumerate(eig):
            x1 = app.centerX + vec[0]*340
            y1 = app.centerY - vec[1]*340
            x2 = app.centerX - vec[0]*340
            y2 = app.centerY + vec[1]*340
            isLockedSpan = app.locked and app.lockedEigenIndex == idx
            if isLockedSpan:
                # LOCKED: solid gold, thick, glowing
                drawLine(x1,y1,x2,y2, fill=rgb(255,230,120), lineWidth=5, opacity=100)
                drawLine(x1,y1,x2,y2, fill=rgb(255,220,80), lineWidth=2, dashes=False, opacity=90)
                drawLabel(f"λ={lam:.2f} ← LOCKED INVARIANT", x1+8, y1-6, size=16, fill=rgb(255,230,120), bold=True)
            else:
                drawLine(x1,y1,x2,y2, fill=rgb(255,220,80), lineWidth=2, dashes=True, opacity=55)
                # small label near edge
                if idx==0:
                    drawLabel(f"λ={lam:.2f} eigen span (invisible until hit)", x1-10, y1-10, size=15, fill=rgb(255,220,80, ), bold=False)
    else:
        drawLabel("No real eigenvectors — rotation spins EVERY vector (pure noise, no invariant signal)", app.centerX+20, 125, size=17, bold=True, fill=rgb(255,120,120))
        drawLabel("Like trying to find effect when variance = infinite", app.centerX+20, 142, size=15, fill=rgb(255,100,100))

    # ---- test vector (blue) and transformed (red/white) ----
    tvScreen = mathToScreen(app, tv)
    trScreen = mathToScreen(app, transVec)

    # angle between v and Mv → shows spin
    tvN = normalize(tv)
    trN = normalize(transVec)
    cosAng = max(-1, min(1, dot(tvN, trN)))
    ang = math.degrees(math.acos(cosAng))
    # cross sign for direction
    cr = cross(tv, transVec)
    if app.locked:
        ang = 0.0 if dot(tv, transVec) >=0 else 180.0

    # draw transformed first (under)
    colTrans = rgb(255,80,80)
    if app.sobelMode:
        colTrans = rgb(255,255,255)  # Sobel highlights edge in white
    drawLine(app.centerX, app.centerY, trScreen[0], trScreen[1], fill=colTrans, lineWidth=5, arrowEnd=True)
    drawLabel(f"M·v (λ·v when locked) | angle diff {ang:.1f}°", trScreen[0]+12, trScreen[1]+14, size=15, bold=True, fill=colTrans)

    # test vector on top
    drawLine(app.centerX, app.centerY, tvScreen[0], tvScreen[1], fill=rgb(100,160,255), lineWidth=5, arrowEnd=True)
    drawLabel("test v (you drag)", tvScreen[0]+10, tvScreen[1]-18, size=15, bold=True, fill=rgb(120,180,255))

    # lock halos
    if app.locked:
        drawCircle(tvScreen[0], tvScreen[1], 16, fill=None, border=rgb(255,220,80), borderWidth=3)
        drawCircle(trScreen[0], trScreen[1], 16, fill=None, border=rgb(255,220,80), borderWidth=3)
        drawCircle(tvScreen[0], tvScreen[1], 28, fill=None, border=rgb(255,220,80), borderWidth=1, opacity=40)
        drawCircle(trScreen[0], trScreen[1], 28, fill=None, border=rgb(255,220,80), borderWidth=1, opacity=40)

    # ---- top center status ----
    if app.locked:
        drawRect(180, 70, 400, 36, fill=rgb(40,35,10), border=rgb(255,220,80), borderWidth=2, roundness=8)
        drawLabel(f"SIGNAL LOCKED — direction preserved! λ={app.lockedLambda:.2f} | v ∥ Mv", 380, 84, size=18, bold=True, fill=rgb(255,230,100))
        drawLabel("Eigenvector = unshakable truth, like true effect inside noisy correlated data", 380, 100, size=15, fill=rgb(220,220,160))
    else:
        if eig:
            drawRect(180, 70, 400, 28, fill=rgb(30,32,40), border=rgb(60,60,70), borderWidth=1, roundness=8)
            drawLabel("Drag mouse — hunt for direction that doesn't spin (cross product → 0)", 380, 86, size=15, fill=rgb(180,180,190))

    # ---- right panel — transcript to math mapping ----
    rx = 750
    drawRect(rx, 90, 280, 600, fill=rgb(30,32,40), border=rgb(60,60,70), borderWidth=1, roundness=10)

    drawLabel("Mahalanobis D", rx+140, 110, size=20, bold=True, fill=rgb(230,230,240))
    drawLabel("Multivariate effect size:", rx+12, 126, size=15, fill=rgb(180,180,190), align='left')
    drawLabel("D² = (μ1-μ2)ᵀ Σ⁻¹ (μ1-μ2)", rx+12, 140, size=16, fill=rgb(150,220,180), align='left', bold=True)
    drawLabel("Σ = covariance matrix", rx+12, 154, size=15, fill=rgb(160,160,160), align='left')
    drawLabel("corr(BP, chol)=0.7 → ellipse", rx+12, 166, size=15, fill=rgb(160,160,160), align='left')
    drawLabel("Eigen Σ = principal axes", rx+12, 178, size=15, fill=rgb(160,160,160), align='left')

    # Gaussian Blur = Variance
    drawLabel("Gaussian Blur = Variance", rx+12, 200, size=15, bold=True, fill=rgb(180,180,255), align='left')
    drawLabel(f"Blur level {app.blurAmount} → SD ×{blurScale:.1f}", rx+12, 216, size=15, fill=rgb(160,160,180), align='left')
    drawLabel("Blur = weighted avg with", rx+12, 228, size=15, fill=rgb(160,160,180), align='left')
    drawLabel("Gaussian kernel (bell curve)", rx+12, 240, size=15, fill=rgb(160,160,180), align='left')
    # Cohen's d demo
    baseD = 1.2
    curD = baseD / blurScale
    drawLabel(f"More blur = bigger denom", rx+12, 254, size=15, fill=rgb(160,160,180), align='left')
    drawLabel(f"= smaller Cohen's d: {curD:.2f}", rx+12, 266, size=15, bold=True, fill=rgb(180,180,255), align='left')
    drawRect(rx+12, 270, 80, 10, fill=rgb(50,50,70), border=None, roundness=3)
    drawRect(rx+12, 270, int(80*curD/baseD), 10, fill=rgb(120,140,255), border=None, roundness=3)

    # Sobel Edge = Effect Size
    drawLabel("Sobel Edge = Effect Size", rx+12, 295, size=15, bold=True, fill=rgb(255,180,180), align='left')
    drawLabel("Sobel finds max difference", rx+12, 311, size=15, fill=rgb(220,180,180), align='left')
    drawLabel("between pixels: Gx, Gy grad", rx+12, 323, size=15, fill=rgb(220,180,180), align='left')
    drawLabel("d = (μ_exp-μ_ctrl)/SD", rx+12, 335, size=15, fill=rgb(255,200,200), align='left')
    drawLabel("is a statistical Sobel filter", rx+12, 347, size=15, fill=rgb(220,180,180), align='left')
    drawLabel("— cuts blur to find edge", rx+12, 359, size=15, fill=rgb(220,180,180), align='left')
    # show current edge magnitude
    edgeMag = norm([transVec[0]-tv[0], transVec[1]-tv[1]])
    drawLabel(f"Current |Mv - v| = {edgeMag:.2f}", rx+12, 375, size=15, fill=rgb(220,180,180), align='left')
    if app.sobelMode:
        drawRect(rx+8, 388, 170, 20, fill=rgb(60,20,20), border=rgb(255,200,200), borderWidth=1, roundness=5)
        drawLabel("SOBEL ON: white = edge", rx+12, 400, size=15, bold=True, fill=rgb(255,255,255), align='left')

    # Why eigenvectors matter
    drawLabel("Why eigenvectors matter:", rx+12, 425, size=15, bold=True, fill=rgb(255,220,80), align='left')
    drawLabel("Σ = U Λ Uᵀ eigen-decomp", rx+12, 441, size=15, fill=rgb(200,200,160), align='left')
    drawLabel("eigenvectors = axes of", rx+12, 453, size=15, fill=rgb(200,200,160), align='left')
    drawLabel("data cloud (ellipse)", rx+12, 465, size=15, fill=rgb(200,200,160), align='left')
    drawLabel("Finding true effect in", rx+12, 479, size=15, fill=rgb(200,200,160), align='left')
    drawLabel("noise = finding direction", rx+12, 491, size=15, fill=rgb(200,200,160), align='left')
    drawLabel("that doesn't spin under M", rx+12, 503, size=15, fill=rgb(200,200,160), align='left')

    drawLabel("Current M:", rx+12, 525, size=15, bold=True, fill=rgb(180,180,190), align='left')
    drawLabel(f"[{M[0][0]:.1f}  {M[0][1]:.1f}]", rx+12, 541, size=15, fill=rgb(200,200,200), align='left')
    drawLabel(f"[{M[1][0]:.1f}  {M[1][1]:.1f}]", rx+12, 555, size=15, fill=rgb(200,200,200), align='left')

    # bottom controls
    drawLabel("DRAG to hunt invariant dir", rx+140, 585, size=15, bold=True, fill=rgb(150,200,255))
    drawLabel("Near eigen → auto SNAP", rx+140, 600, size=15, fill=rgb(255,220,80))
    drawLabel("1=stretch 2=shear 3=rot 4=refl", rx+140, 615, size=15, fill=rgb(140,140,150))
    drawLabel("C=ellipse B=blur S=Sobel R=reset", rx+140, 630, size=15, fill=rgb(140,140,150))
    drawLabel("Mahalanobis = ellipse axes", rx+140, 645, size=15, fill=rgb(100,220,140))
    drawLabel("Blur = variance ↑ → d ↓", rx+140, 658, size=15, fill=rgb(120,140,255))
    drawLabel("Sobel = |diff| edge detector", rx+140, 671, size=15, fill=rgb(255,180,180))
