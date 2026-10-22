
"""
eigen_signal.py
SCS Eigen Signal Lab — Finding Invariant Truth in Noise
Run: ?app=eigen_signal

Fixed for Brython: mutate list in-place with slice assignment app.testVec[:] = [...]
"""
from scs import *
import math

def matVecMul(M, v):
    return [M[0][0]*v[0] + M[0][1]*v[1], M[1][0]*v[0] + M[1][1]*v[1]]

def dot(a,b):
    return a[0]*b[0] + a[1]*b[1]

def cross(a,b):
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
        return None
    disc = max(0.0, disc)
    sqrtD = math.sqrt(disc)
    l1 = (tr + sqrtD)/2
    l2 = (tr - sqrtD)/2
    def vecFor(l):
        if abs(b) > 1e-6:
            return [b, l - a]
        elif abs(c) > 1e-6:
            return [l - d, c]
        else:
            return [1,0] if abs(a-l) < abs(d-l) else [0,1]
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
        {'name': 'Stretch (positive lambda)', 'M': [[1.8, 0.2],[0.2, 0.7]], 'key':'1', 'desc': '2 real dirs scale >0'},
        {'name': 'Shear (defective)', 'M': [[1, 0.9],[0, 1]], 'key':'2', 'desc': 'repeated lambda=1, 1 invariant'},
        {'name': 'Rotation 90 deg (no real)', 'M': [[0, -1],[1, 0]], 'key':'3', 'desc': 'spins EVERY vec = pure noise'},
        {'name': 'Reflection (neg lambda)', 'M': [[1.2, 0.3],[0.3, -0.8]], 'key':'4', 'desc': 'one axis flips (lambda<0)'},
    ]
    # Important: create list once, then mutate in-place with [:] later
    app.testVec = [1.5, 0]
    app.showEllipse = True
    app.blurAmount = 0
    app.sobelMode = False
    app.snapThreshold = 0.14
    app.locked = False
    app.lockedEigenIndex = None
    app.lockedLambda = None
    app.cov = [[1.0, 0.7],[0.7, 1.0]]
    app.rho = 0.7
    app.dragCount = 0
    app.moveCount = 0
    app.lastEvent = "none"
    app.dataPoints = []
    for i in range(90):
        a = math.sin(i*12.9898)*43758.5453
        a = a - math.floor(a)
        b = math.sin(i*78.233)*23421.5453
        b = b - math.floor(b)
        u1 = max(0.0001, min(0.9999, a))
        u2 = max(0.0001, min(0.9999, b))
        r = math.sqrt(-2*math.log(u1))
        th = 2*math.pi*u2
        z1 = r*math.cos(th)
        z2 = r*math.sin(th)
        x = max(-2.5, min(2.5, z1))
        y = max(-2.5, min(2.5, z2))
        yy = app.rho*x + math.sqrt(max(0, 1-app.rho*app.rho))*y
        app.dataPoints.append([x*0.55, yy*0.55])

def getCurrentM(app):
    return app.transformations[app.transIndex]['M']

def getCurrentEig(app):
    return eigen2x2(getCurrentM(app))

def screenToMath(app, mx, my):
    return [(mx - app.centerX)/app.scale, (app.centerY - my)/app.scale]

def mathToScreen(app, v):
    return (app.centerX + v[0]*app.scale, app.centerY - v[1]*app.scale)

def findClosestEigen(app, testVec):
    eig = getCurrentEig(app)
    if not eig:
        return None, None, 999, 0
    tvNorm = normalize(testVec)
    best = None
    bestIdx = None
    bestCross = 999
    bestDot = 0
    for idx, (lam, ev) in enumerate(eig):
        cr = abs(cross(tvNorm, ev))
        d = dot(tvNorm, ev)
        if cr < bestCross:
            bestCross = cr
            best = (lam, ev)
            bestIdx = idx
            bestDot = d
    return best, bestIdx, bestCross, bestDot

def updateTestVecFromMouse(app, mx, my):
    dx, dy = screenToMath(app, mx, my)
    mag = math.hypot(dx, dy)
    if mag < 0.12:
        return
    nx = dx/mag*app.testMag
    ny = dy/mag*app.testMag
    # Check snap to eigen span
    eig = getCurrentEig(app)
    if eig is not None:
        # Use temporary vec for check
        tmp = [nx, ny]
        closest, cIdx, cCross, cDot = findClosestEigen(app, tmp)
        if closest is not None and cCross < app.snapThreshold:
            lam, ev = closest
            sign = 1 if cDot >= 0 else -1
            # MUTATE IN-PLACE for Brython
            app.testVec[:] = [ev[0]*sign*app.testMag, ev[1]*sign*app.testMag]
            app.locked = True
            app.lockedEigenIndex = cIdx
            app.lockedLambda = lam
            return
    # No snap - mutate in-place
    app.testVec[:] = [nx, ny]
    app.locked = False
    app.lockedEigenIndex = None
    app.lockedLambda = None

def onMousePress(app, mx, my):
    app.lastEvent = f"PRESS {mx:.0f},{my:.0f}"
    app.dragCount += 1
    updateTestVecFromMouse(app, mx, my)

def onMouseDrag(app, mx, my):
    app.lastEvent = f"DRAG {mx:.0f},{my:.0f}"
    app.dragCount += 1
    updateTestVecFromMouse(app, mx, my)

def onMouseMove(app, mx, my):
    app.lastEvent = f"MOVE {mx:.0f},{my:.0f}"
    app.moveCount += 1
    updateTestVecFromMouse(app, mx, my)

def onKeyPress(app, key):
    if key in ('1','2','3','4'):
        app.transIndex = int(key)-1
    elif key in ('c','C'):
        app.showEllipse = not app.showEllipse
    elif key in ('b','B'):
        app.blurAmount = (app.blurAmount + 1) % 4
    elif key in ('s','S'):
        app.sobelMode = not app.sobelMode
    elif key in ('r','R'):
        app.testVec[:] = [1.5, 0]
        app.blurAmount = 0
        app.sobelMode = False
        app.transIndex = 0
        app.locked = False

def redrawAll(app):
    # TEMP DEBUG - remove after fix
    try:
        drawRect(10, 70, 260, 110, fill=rgb(0,0,0), border=rgb(255,255,0), borderWidth=2, roundness=6, opacity=90)
        drawLabel(f"last {app.lastEvent}", 15, 90, size=15, fill=rgb(255,255,0), align='left')
        drawLabel(f"drag# {app.dragCount} move# {app.moveCount}", 15, 110, size=15, fill=rgb(255,255,0), align='left')
        drawLabel(f"vec {app.testVec[0]:.2f} {app.testVec[1]:.2f}", 15, 130, size=15, fill=rgb(200,255,200), align='left')
        drawLabel(f"mag {math.hypot(app.testVec[0], app.testVec[1]):.2f}", 15, 150, size=15, fill=rgb(200,255,200), align='left')
    except:
        pass
    M = getCurrentM(app)
    eig = getCurrentEig(app)
    tv = app.testVec
    tr = matVecMul(M, tv)

    drawLabel("Eigen Signal Lab - Invariant Truth in Multivariate Noise", 520, 28, size=24, bold=True, fill=rgb(230,230,240))
    tInfo = app.transformations[app.transIndex]
    drawLabel(f"{tInfo['key']}: {tInfo['name']} - {tInfo['desc']} | 1-4 C ellipse B blur S Sobel R reset Drag to hunt", 520, 55, size=15, fill=rgb(160,160,170))

    drawLine(50, app.centerY, 720, app.centerY, fill=rgb(60,60,70), lineWidth=1)
    drawLine(app.centerX, 90, app.centerX, 620, fill=rgb(60,60,70), lineWidth=1)
    for i in range(-3,4):
        if i==0:
            continue
        x = app.centerX + i*app.scale
        drawLine(x, 90, x, 620, fill=rgb(40,40,50), lineWidth=1, dashes=True, opacity=40)
        y = app.centerY + i*app.scale
        drawLine(50, y, 720, y, fill=rgb(40,40,50), lineWidth=1, dashes=True, opacity=40)
    drawLabel("0", app.centerX+6, app.centerY+15, size=15, fill=rgb(90,90,90))

    blurScale = 1 + app.blurAmount*0.45
    covEig = eigen2x2(app.cov)

    if app.showEllipse and covEig is not None:
        for pt in app.dataPoints:
            px = pt[0]*blurScale
            py = pt[1]*blurScale
            sx = app.centerX + px*app.scale
            sy = app.centerY - py*app.scale
            drawCircle(sx, sy, 3, fill=rgb(100,220,140), opacity=60)
        for idx, (lam, vec) in enumerate(covEig):
            scale = math.sqrt(max(0.1, lam)) * blurScale * app.scale * 1.25
            x2 = app.centerX + vec[0]*scale
            y2 = app.centerY - vec[1]*scale
            col = rgb(80,200,120) if idx==0 else rgb(80,160,200)
            drawLine(app.centerX, app.centerY, x2, y2, fill=col, lineWidth=3, opacity=75)
            drawLabel(f"cov lambda={lam:.2f}", x2+10, y2, size=15, fill=col, bold=True)
        pts = []
        for deg in range(0, 360, 5):
            rad = math.radians(deg)
            c = math.cos(rad)
            s = math.sin(rad)
            lam1, v1 = covEig[0]
            lam2, v2 = covEig[1]
            px = (math.sqrt(lam1)*c*v1[0] + math.sqrt(lam2)*s*v2[0]) * blurScale * 1.5
            py = (math.sqrt(lam1)*c*v1[1] + math.sqrt(lam2)*s*v2[1]) * blurScale * 1.5
            sx = app.centerX + px*app.scale
            sy = app.centerY - py*app.scale
            pts.append((sx, sy))
        for i in range(len(pts)):
            x1,y1 = pts[i]
            x2,y2 = pts[(i+1)%len(pts)]
            drawLine(x1,y1,x2,y2, fill=rgb(100,220,140), lineWidth=2, opacity=70)
        drawLabel(f"Mahalanobis ellipse corr={app.rho} blur x{blurScale:.2f}=variance up", app.centerX, 95, size=15, fill=rgb(100,220,140))

    if eig is not None:
        for idx, (lam, vec) in enumerate(eig):
            x1 = app.centerX + vec[0]*340
            y1 = app.centerY - vec[1]*340
            x2 = app.centerX - vec[0]*340
            y2 = app.centerY + vec[1]*340
            isLocked = app.locked and app.lockedEigenIndex == idx
            if isLocked:
                drawLine(x1,y1,x2,y2, fill=rgb(255,230,120), lineWidth=5, opacity=100)
                drawLine(x1,y1,x2,y2, fill=rgb(255,220,80), lineWidth=2, dashes=False, opacity=90)
                drawLabel(f"lambda={lam:.2f} LOCKED INVARIANT", x1+8, y1-6, size=15, fill=rgb(255,230,120), bold=True)
            else:
                drawLine(x1,y1,x2,y2, fill=rgb(255,220,80), lineWidth=2, dashes=True, opacity=55)
                if idx==0:
                    drawLabel(f"lambda={lam:.2f} eigen span invisible until hit", x1-10, y1-10, size=15, fill=rgb(255,220,80))

    tvS = mathToScreen(app, tv)
    trS = mathToScreen(app, tr)
    tvN = normalize(tv)
    trN = normalize(tr)
    cosAng = max(-1, min(1, dot(tvN, trN)))
    ang = math.degrees(math.acos(cosAng))
    if app.locked:
        ang = 0.0 if dot(tv, tr) >=0 else 180.0

    colTrans = rgb(255,80,80)
    if app.sobelMode:
        colTrans = rgb(255,255,255)
    drawLine(app.centerX, app.centerY, trS[0], trS[1], fill=colTrans, lineWidth=5, arrowEnd=True)
    drawLabel(f"M dot v lambda dot v when locked angle {ang:.1f} deg", trS[0]+15, trS[1]+15, size=15, bold=True, fill=colTrans)

    drawLine(app.centerX, app.centerY, tvS[0], tvS[1], fill=rgb(100,160,255), lineWidth=5, arrowEnd=True)
    drawLabel("test v you drag", tvS[0]+10, tvS[1]-18, size=15, bold=True, fill=rgb(120,180,255))

    if app.locked:
        drawCircle(tvS[0], tvS[1], 16, fill=None, border=rgb(255,220,80), borderWidth=3)
        drawCircle(trS[0], trS[1], 16, fill=None, border=rgb(255,220,80), borderWidth=3)
        drawRect(180, 70, 400, 36, fill=rgb(40,35,10), border=rgb(255,220,80), borderWidth=2, roundness=8)
        drawLabel(f"SIGNAL LOCKED lambda={app.lockedLambda:.2f} v parallel Mv", 380, 84, size=18, bold=True, fill=rgb(255,230,100))
        drawLabel("Eigenvector = unshakable truth like true effect inside noise", 380, 100, size=15, fill=rgb(220,220,160))
    else:
        if eig is not None:
            drawRect(180, 70, 400, 28, fill=rgb(30,32,40), border=rgb(60,60,70), borderWidth=1, roundness=8)
            drawLabel("Drag mouse hunt for direction that does not spin cross product to 0", 380, 86, size=15, fill=rgb(180,180,190))

    rx = 750
    drawRect(rx, 90, 280, 600, fill=rgb(30,32,40), border=rgb(60,60,70), borderWidth=1, roundness=10)
    drawLabel("Mahalanobis D", rx+140, 110, size=20, bold=True, fill=rgb(230,230,240))
    drawLabel("Multivariate effect size:", rx+15, 126, size=15, fill=rgb(180,180,190), align='left')
    drawLabel("D2 = (mu1-mu2)T Sigma-1 (mu1-mu2)", rx+15, 140, size=15, fill=rgb(150,220,180), align='left', bold=True)
    drawLabel("Sigma = covariance matrix", rx+15, 154, size=15, fill=rgb(160,160,160), align='left')
    drawLabel("corr BP chol 0.7 ellipse", rx+15, 166, size=15, fill=rgb(160,160,160), align='left')
    drawLabel("Eigen Sigma = principal axes", rx+15, 178, size=15, fill=rgb(160,160,160), align='left')
    drawLabel("Gaussian Blur = Variance", rx+15, 200, size=15, bold=True, fill=rgb(180,180,255), align='left')
    drawLabel(f"Blur level {app.blurAmount} SD x{blurScale:.1f}", rx+15, 216, size=15, fill=rgb(160,160,180), align='left')
    drawLabel("Blur = weighted avg with", rx+15, 228, size=15, fill=rgb(160,160,180), align='left')
    drawLabel("Gaussian kernel bell curve", rx+15, 240, size=15, fill=rgb(160,160,180), align='left')
    baseD = 1.2
    curD = baseD / blurScale
    drawLabel(f"More blur bigger denom", rx+15, 254, size=15, fill=rgb(160,160,180), align='left')
    drawLabel(f"smaller Cohen d: {curD:.2f}", rx+15, 266, size=15, bold=True, fill=rgb(180,180,255), align='left')
    drawRect(rx+15, 270, 80, 10, fill=rgb(50,50,70), border=None, roundness=3)
    drawRect(rx+15, 270, int(80*curD/baseD), 10, fill=rgb(120,140,255), border=None, roundness=3)
    drawLabel("Sobel Edge = Effect Size", rx+15, 295, size=15, bold=True, fill=rgb(255,180,180), align='left')
    drawLabel("Sobel finds max difference", rx+15, 311, size=15, fill=rgb(220,180,180), align='left')
    drawLabel("between pixels Gx Gy grad", rx+15, 323, size=15, fill=rgb(220,180,180), align='left')
    drawLabel("d = (mu exp-mu ctrl)/SD", rx+15, 335, size=15, fill=rgb(255,200,200), align='left')
    drawLabel("is a statistical Sobel filter", rx+15, 347, size=15, fill=rgb(220,180,180), align='left')
    drawLabel("cuts blur to find edge", rx+15, 359, size=15, fill=rgb(220,180,180), align='left')
    edgeMag = norm([tr[0]-tv[0], tr[1]-tv[1]])
    drawLabel(f"Current |Mv - v| = {edgeMag:.2f}", rx+15, 375, size=15, fill=rgb(220,180,180), align='left')
    if app.sobelMode:
        drawRect(rx+8, 388, 170, 20, fill=rgb(60,20,20), border=rgb(255,200,200), borderWidth=1, roundness=5)
        drawLabel("SOBEL ON white = edge", rx+15, 400, size=15, bold=True, fill=rgb(255,255,255), align='left')
    drawLabel("Why eigenvectors matter:", rx+15, 425, size=15, bold=True, fill=rgb(255,220,80), align='left')
    drawLabel("Sigma = U Lambda UT decomp", rx+15, 441, size=15, fill=rgb(200,200,160), align='left')
    drawLabel("eigenvectors = axes of", rx+15, 453, size=15, fill=rgb(200,200,160), align='left')
    drawLabel("data cloud ellipse", rx+15, 465, size=15, fill=rgb(200,200,160), align='left')
    drawLabel("Finding true effect in", rx+15, 479, size=15, fill=rgb(200,200,160), align='left')
    drawLabel("noise = finding direction", rx+15, 491, size=15, fill=rgb(200,200,160), align='left')
    drawLabel("that does not spin under M", rx+15, 503, size=15, fill=rgb(200,200,160), align='left')
    drawLabel("Current M:", rx+15, 525, size=15, bold=True, fill=rgb(180,180,190), align='left')
    drawLabel(f"[{M[0][0]:.1f}  {M[0][1]:.1f}]", rx+15, 541, size=15, fill=rgb(200,200,200), align='left')
    drawLabel(f"[{M[1][0]:.1f}  {M[1][1]:.1f}]", rx+15, 555, size=15, fill=rgb(200,200,200), align='left')
    drawLabel("DRAG to hunt invariant dir", rx+140, 585, size=15, bold=True, fill=rgb(150,200,255))
    drawLabel("Near eigen auto SNAP", rx+140, 600, size=15, fill=rgb(255,220,80))
    drawLabel("1=stretch 2=shear 3=rot 4=refl", rx+140, 615, size=15, fill=rgb(140,140,150))
    drawLabel("C=ellipse B=blur S=Sobel R=reset", rx+140, 630, size=15, fill=rgb(140,140,150))
    drawLabel("Mahalanobis = ellipse axes", rx+140, 645, size=15, fill=rgb(100,220,140))
    drawLabel("Blur = variance up d down", rx+140, 658, size=15, fill=rgb(120,140,255))
    drawLabel("Sobel = |diff| edge detector", rx+140, 671, size=15, fill=rgb(255,180,180))
