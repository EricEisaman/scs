"""
eigen_signal.py
SCS Eigen Signal Lab — Finding Invariant Truth in Noise
Run: ?app=eigen_signal

Covers transcript: eigenvalue.py, Mahalanobis D, covariance matrices, Sobel as effect size,
Gaussian blur = variance

Idea: Multivariate effect size = Mahalanobis D = distance accounting for correlation.
Its geometry is an ellipse (covariance). Eigenvectors = axes of ellipse = directions that don't spin when you transform space.
Dragging test vector = hunting for signal. When you hit eigenvector, it locks — like finding true effect in noise.

Controls:
- 1/2/3/4: stretch / shear / rotation 90° / reflection
- Drag mouse: move test vector (blue). Red = transformed vector
- Mouse near eigenvector → SNAP + "SIGNAL LOCKED"
- C: toggle covariance ellipse (blood pressure vs cholesterol)
- B: toggle blur (add variance) — see ellipse grow
- S: toggle Sobel-like edge mode (highlight max difference)
- R: reset
"""
from scs import *
import math

def matVecMul(M, v):
    return [M[0][0]*v[0] + M[0][1]*v[1], M[1][0]*v[0] + M[1][1]*v[1]]

def eigen2x2(M):
    # eigenvalues of 2x2: lambda = (trace ± sqrt(trace^2 -4 det))/2
    a,b = M[0][0], M[0][1]
    c,d = M[1][0], M[1][1]
    tr = a+d
    det = a*d - b*c
    disc = tr*tr - 4*det
    if disc < 0:
        return None  # complex = rotation, no real eigenvectors
    sqrtD = math.sqrt(disc)
    l1 = (tr + sqrtD)/2
    l2 = (tr - sqrtD)/2
    # eigenvectors: solve (M - lambda I) v =0 => (a-l)x + b y =0
    def vecFor(l):
        if abs(b) > 1e-6:
            return [b, l - a]  # up to scale, or alternative
        elif abs(c) > 1e-6:
            return [l - d, c]
        else:
            return [1,0] if abs(a-l) < abs(d-l) else [0,1]
    v1 = vecFor(l1)
    v2 = vecFor(l2)
    # normalize
    def norm(v):
        m = math.hypot(v[0], v[1])
        return [v[0]/m, v[1]/m] if m>0 else [1,0]
    return [(l1, norm(v1)), (l2, norm(v2))]

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 30
    app.background = gradient(rgb(15,17,21), rgb(26,29,36), start='top')

    app.centerX = 380
    app.centerY = 360
    app.scale = 110

    app.transIndex = 0
    app.transformations = [
        {'name': 'Stretch (positive eigenvalues)', 'M': [[1.8, 0.2],[0.2, 0.7]], 'key':'1'},
        {'name': 'Shear (repeated eigen)', 'M': [[1, 0.9],[0, 1]], 'key':'2'},
        {'name': 'Rotation 90° (no real eigen = pure noise)', 'M': [[0, -1],[1, 0]], 'key':'3'},
        {'name': 'Reflection (negative eigen)', 'M': [[1.2, 0.3],[0.3, -0.8]], 'key':'4'},
    ]

    app.testVec = [1, 0.5]  # in math coords
    app.showEllipse = True
    app.blurAmount = 0
    app.sobelMode = False

    # covariance for Mahalanobis demo: corr between BP and cholesterol
    app.cov = [[1.0, 0.7],[0.7, 1.0]]  # correlation 0.7

def getCurrentM(app):
    return app.transformations[app.transIndex]['M']

def onMouseMove(app, mx, my):
    # convert screen to math vec from center
    dx = (mx - app.centerX)/app.scale
    dy = (app.centerY - my)/app.scale  # flip y
    if math.hypot(dx,dy) < 0.1:
        return
    # normalize to unit-ish
    mag = math.hypot(dx,dy)
    app.testVec = [dx/mag*1.5, dy/mag*1.5]

def onMouseDrag(app, mx, my):
    onMouseMove(app, mx, my)

def onKeyPress(app, key):
    if key in ('1','2','3','4'):
        app.transIndex = int(key)-1
    elif key == 'c' or key == 'C':
        app.showEllipse = not app.showEllipse
    elif key == 'b' or key == 'B':
        app.blurAmount = (app.blurAmount + 1) % 4  # 0-3
    elif key == 's' or key == 'S':
        app.sobelMode = not app.sobelMode
    elif key == 'r' or key == 'R':
        app.testVec = [1,0.5]
        app.blurAmount = 0
        app.sobelMode = False
        app.transIndex = 0

def redrawAll(app):
    M = getCurrentM(app)
    eig = eigen2x2(M)

    # title
    drawLabel("Eigen Signal Lab — Invariant Truth in Multivariate Noise", 520, 30, size=25, bold=True, fill=rgb(230,230,240))
    drawLabel(f"{app.transIndex+1}: {app.transformations[app.transIndex]['name']} — press 1-4 to switch, C ellipse, B blur (variance), S Sobel (edge), R reset", 520, 60, size=19, fill=rgb(160,160,170))

    # grid
    # draw axes
    drawLine(50, app.centerY, 720, app.centerY, fill=rgb(60,60,70), lineWidth=1)
    drawLine(app.centerX, 90, app.centerX, 620, fill=rgb(60,60,70), lineWidth=1)
    # grid lines
    for i in range(-3,4):
        if i==0: continue
        x = app.centerX + i*app.scale
        drawLine(x, 90, x, 620, fill=rgb(40,40,50), lineWidth=1, dashes=True, opacity=40)
        y = app.centerY + i*app.scale
        drawLine(50, y, 720, y, fill=rgb(40,40,50), lineWidth=1, dashes=True, opacity=40)

    # covariance ellipse (Mahalanobis)
    if app.showEllipse:
        # ellipse axes from cov eigenvectors
        covEig = eigen2x2(app.cov)
        if covEig:
            for idx, (lam, vec) in enumerate(covEig):
                # scale by sqrt(lam) * blur
                scale = math.sqrt(max(0.1, lam)) * (1 + app.blurAmount*0.4) * app.scale * 1.2
                x2 = app.centerX + vec[0]*scale
                y2 = app.centerY - vec[1]*scale
                col = rgb(80,200,120) if idx==0 else rgb(80,160,200)
                drawLine(app.centerX, app.centerY, x2, y2, fill=col, lineWidth=3, opacity=70)
                drawLabel(f"cov eigen {lam:.2f}", x2+8, y2, size=18, fill=col, bold=True)
            # draw ellipse approx via polygon
            pts = []
            for theta in range(0, 360, 6):
                rad = math.radians(theta)
                # point on unit circle transformed by cov sqrt
                # simple: use eigen decomposition to generate ellipse
                # p = sum sqrt(lam_i) * cos/sin * vec_i
                c, s = math.cos(rad), math.sin(rad)
                # combine
                # approximate ellipse via mixing eigenvectors
                if covEig and len(covEig)>=2:
                    lam1, v1 = covEig[0]
                    lam2, v2 = covEig[1]
                    px = app.centerX + (math.sqrt(lam1)*c*v1[0] + math.sqrt(lam2)*s*v2[0]) * app.scale * (1+app.blurAmount*0.4)*1.2
                    py = app.centerY - (math.sqrt(lam1)*c*v1[1] + math.sqrt(lam2)*s*v2[1]) * app.scale * (1+app.blurAmount*0.4)*1.2
                    pts.append((px,py))
            for i in range(len(pts)):
                x1,y1 = pts[i]
                x2,y2 = pts[(i+1)%len(pts)]
                drawLine(x1,y1,x2,y2, fill=rgb(100,220,140), lineWidth=2, opacity=60)

    # eigenvector spans (dashed) — the invariant directions
    if eig:
        for lam, vec in eig:
            # extend both directions
            x1 = app.centerX + vec[0]*300
            y1 = app.centerY - vec[1]*300
            x2 = app.centerX - vec[0]*300
            y2 = app.centerY + vec[1]*300
            drawLine(x1,y1,x2,y2, fill=rgb(255,220,80), lineWidth=2, dashes=True, opacity=70)
            drawLabel(f"λ={lam:.2f} eigen direction", x1, y1, size=18, fill=rgb(255,220,80), bold=True)
    else:
        drawLabel("No real eigenvectors — rotation spins every vector (pure noise, no invariant signal)", app.centerX + 20, 145, size=20, bold=True, fill=rgb(255,100,100))

    # test vector (blue) and transformed (red)
    tv = app.testVec
    tvScreen = (app.centerX + tv[0]*app.scale, app.centerY - tv[1]*app.scale)
    drawLine(app.centerX, app.centerY, tvScreen[0], tvScreen[1], fill=rgb(100,160,255), lineWidth=4, arrowEnd=True)
    drawLabel("test v (you)", tvScreen[0]+10, tvScreen[1]-10, size=19, bold=True, fill=rgb(120,180,255))

    transVec = matVecMul(M, tv)
    trScreen = (app.centerX + transVec[0]*app.scale, app.centerY - transVec[1]*app.scale)
    colTrans = rgb(255,80,80) if not app.sobelMode else rgb(255,255,255)
    drawLine(app.centerX, app.centerY, trScreen[0], trScreen[1], fill=colTrans, lineWidth=4, arrowEnd=True)
    drawLabel("M·v (transformed)", trScreen[0]+10, trScreen[1]+10, size=19, bold=True, fill=colTrans)

    # check if near eigenvector (signal lock)
    locked = False
    lockInfo = ""
    if eig:
        for lam, ev in eig:
            # cross product near 0 means parallel
            cross = abs(tv[0]*ev[1] - tv[1]*ev[0])
            dot = tv[0]*ev[0] + tv[1]*ev[1]
            # parallel if cross small and dot not near 0
            if cross < 0.15:
                locked = True
                lockInfo = f"λ={lam:.2f}"
                # draw lock effect
                drawCircle(tvScreen[0], tvScreen[1], 14, fill=None, border=rgb(255,220,80), borderWidth=3)
                drawCircle(trScreen[0], trScreen[1], 14, fill=None, border=rgb(255,220,80), borderWidth=3)
                break

    if locked:
        drawLabel(f"SIGNAL LOCKED — direction preserved! {lockInfo}", 380, 85, size=22, bold=True, fill=rgb(255,220,80))
        drawLabel("Eigenvector = invariant truth, like true effect inside noise", 380, 102, size=19, fill=rgb(220,220,180))
    else:
        if eig:
            drawLabel("Drag mouse — hunt for direction that doesn't spin", 380, 85, size=20, fill=rgb(180,180,190))

    # right panel — explanation linking to transcript
    rx = 750
    drawRect(rx, 90, 280, 600, fill=rgb(30,32,40), border=rgb(60,60,70), borderWidth=1, roundness=10)

    drawLabel("Mahalanobis D", rx+140, 110, size=22, bold=True, fill=rgb(230,230,240))
    drawLabel("Multivariate effect size:", rx+12, 128, size=18, fill=rgb(180,180,190), align='left')
    drawLabel("D² = (μ1-μ2)ᵀ Σ⁻¹ (μ1-μ2)", rx+12, 142, size=19, fill=rgb(150,220,180), align='left', bold=True)
    drawLabel("Σ = covariance matrix", rx+12, 158, size=18, fill=rgb(160,160,160), align='left')
    drawLabel("Accounts for correlation", rx+12, 172, size=18, fill=rgb(160,160,160), align='left')
    drawLabel("between BP & cholesterol", rx+12, 186, size=18, fill=rgb(160,160,160), align='left')

    drawLabel("Gaussian Blur = Variance", rx+12, 215, size=19, bold=True, fill=rgb(180,180,255), align='left')
    drawLabel(f"Blur level {app.blurAmount} → SD ×{1+app.blurAmount*0.4:.1f}", rx+12, 232, size=18, fill=rgb(160,160,180), align='left')
    drawLabel("Blur = weighted avg with", rx+12, 246, size=18, fill=rgb(160,160,180), align='left')
    drawLabel("Gaussian kernel (bell curve)", rx+12, 260, size=18, fill=rgb(160,160,180), align='left')
    drawLabel("More blur = bigger denominator", rx+12, 274, size=18, fill=rgb(160,160,180), align='left')
    drawLabel("= smaller Cohen's d", rx+12, 288, size=18, fill=rgb(160,160,180), align='left')

    drawLabel("Sobel Edge = Effect Size", rx+12, 315, size=19, bold=True, fill=rgb(255,180,180), align='left')
    drawLabel("Sobel finds max difference", rx+12, 332, size=18, fill=rgb(220,180,180), align='left')
    drawLabel("between pixels: Gx, Gy gradient", rx+12, 346, size=18, fill=rgb(220,180,180), align='left')
    drawLabel("d = (μ_exp-μ_ctrl)/SD_pooled", rx+12, 360, size=18, fill=rgb(255,200,200), align='left')
    drawLabel("is a statistical Sobel filter —", rx+12, 374, size=18, fill=rgb(220,180,180), align='left')
    drawLabel("cuts blur to find edge", rx+12, 388, size=18, fill=rgb(220,180,180), align='left')
    if app.sobelMode:
        drawLabel("SOBEL MODE ON: white = edge", rx+12, 404, size=18, bold=True, fill=rgb(255,255,255), align='left')

    drawLabel("Why eigenvectors matter:", rx+12, 435, size=19, bold=True, fill=rgb(255,220,80), align='left')
    drawLabel("Covariance Σ decomposed via", rx+12, 452, size=18, fill=rgb(200,200,160), align='left')
    drawLabel("eigenvalues/vectors = principal", rx+12, 466, size=18, fill=rgb(200,200,160), align='left')
    drawLabel("axes of data cloud.", rx+12, 480, size=18, fill=rgb(200,200,160), align='left')
    drawLabel("Finding true effect in noise", rx+12, 494, size=18, fill=rgb(200,200,160), align='left')
    drawLabel("= finding direction that", rx+12, 508, size=18, fill=rgb(200,200,160), align='left')
    drawLabel("doesn't spin under transform.", rx+12, 522, size=18, fill=rgb(200,200,160), align='left')

    drawLabel("Current M:", rx+12, 550, size=18, bold=True, fill=rgb(180,180,190), align='left')
    drawLabel(f"[{M[0][0]:.1f}  {M[0][1]:.1f}]", rx+12, 566, size=19, fill=rgb(200,200,200), align='left')
    drawLabel(f"[{M[1][0]:.1f}  {M[1][1]:.1f}]", rx+12, 582, size=19, fill=rgb(200,200,200), align='left')

    drawLabel("1=stretch 2=shear 3=rot 4=refl", rx+140, 615, size=18, fill=rgb(140,140,150))
    drawLabel("C=ellipse B=blur S=Sobel", rx+140, 630, size=18, fill=rgb(140,140,150))
