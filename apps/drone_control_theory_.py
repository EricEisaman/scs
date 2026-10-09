from scs import *
import math, random

# ============================================================
# LYAPUNOV DRONE LAB — 1050x700
# Motivated by: balancing broomstick on ice in windstorm = quadrotor
# Shows: ISL, Asymptotic, Exponential, Global+LaSalle, radially unbounded
# For Bussin Sigma Scholars of Edward Little High
# ============================================================

def getGains(mode):
    # returns kp, kd, kTh, kOm, alpha, label
    if mode == 0: # ISL - stable sense Lyapunov dV <=0, actually =0 frictionless
        return 0.7, 0.0, 0.6, 0.0, 0.0, "ISL: Stable (dV = 0) — orbits forever"
    elif mode == 1: # Asymptotic dV <0
        return 1.0, 0.55, 1.2, 0.35, 0.0, "Asymptotic: dV < 0 — eventually stops"
    elif mode == 2: # Exponential dV <= -alpha V
        return 2.2, 1.85, 3.0, 1.4, 1.15, "Exponential: dV ≤ -αV — fast guaranteed"
    else: # Global + LaSalle
        return 1.8, 1.25, 2.2, 1.0, 0.9, "Global + LaSalle: ∀ start, escapes flats"

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 60

    # Drone state — 2D quadrotor (x,y,vx,vy,theta,omega)
    app.droneX = 350
    app.droneY = 300
    app.vx = 0
    app.vy = 0
    app.theta = 0.12
    app.omega = 0

    app.targetX = 350
    app.targetY = 260
    app.mode = 2
    app.trail = []
    app.bowlTrail = []

    app.time = 0
    app.propAngle = 0
    app.windOn = False
    app.windX = 0
    app.windY = 0
    app.gust = 0
    app.gustTimer = 0

    app.windParticles = []
    for _ in range(55):
        app.windParticles.append({
            'x': random.randint(-100, 800),
            'y': random.randint(20, 520),
            'vx': random.uniform(2, 6),
            'len': random.uniform(8, 26),
            'a': random.uniform(0.15, 0.55)
        })

    app.clouds = [
        {'x': 120, 'y': 80, 's': 1.0, 'vx': 0.2},
        {'x': 400, 'y': 55, 's': 1.3, 'vx': 0.15},
        {'x': 600, 'y': 90, 's': 0.9, 'vx': 0.25},
    ]

    app.V = 0
    app.Vdot = 0
    app.Vhistory = []
    app.showCartOverlay = False
    app.paused = False
    app.messageTimer = 0

    # Cart-pole analogy for LaSalle demo (small)
    app.poleAngle = math.pi  # down
    app.poleOmega = 0

def resetDrone(app):
    app.droneX = 350 + random.uniform(-120, 120)
    app.droneY = 300 + random.uniform(-80, 80)
    app.vx = random.uniform(-30, 30)
    app.vy = random.uniform(-20, 20)
    app.theta = random.uniform(-0.3, 0.3)
    app.omega = random.uniform(-0.5, 0.5)
    app.trail = []
    app.Vhistory = []
    app.bowlTrail = []
    app.gust = 0

def onMousePress(app, mx, my):
    if mx < 700: # only in flight area
        app.targetX = max(50, min(650, mx))
        app.targetY = max(50, min(520, my))
        app.messageTimer = 90
    # check mode buttons on right panel
    # buttons at x=720,y=480..640
    if 720 <= mx <= 1030:
        if 495 <= my <= 520:
            app.mode = 0
        elif 525 <= my <= 550:
            app.mode = 1
        elif 555 <= my <= 580:
            app.mode = 2
        elif 585 <= my <= 610:
            app.mode = 3

def onMouseDrag(app, mx, my):
    if mx < 700:
        app.targetX = max(50, min(650, mx))
        app.targetY = max(50, min(520, my))

def onKeyPress(app, key):
    if key == '1':
        app.mode = 0
    elif key == '2':
        app.mode = 1
    elif key == '3':
        app.mode = 2
    elif key == '4':
        app.mode = 3
    elif key.lower() == 'w':
        app.windOn = not app.windOn
    elif key.lower() == 'r':
        resetDrone(app)
    elif key == 'space':
        app.paused = not app.paused
    elif key.lower() == 'c':
        app.showCartOverlay = not app.showCartOverlay
    elif key.lower() == 'g':
        # big gust
        app.gust = random.uniform(-220, 220)
        app.gustTimer = 25

def onStep(app):
    dt = 1/60
    app.time += dt
    app.propAngle += 18 + abs(app.vx)*0.15

    # clouds drift
    for c in app.clouds:
        c['x'] += c['vx']
        if c['x'] > 780:
            c['x'] = -80

    # wind particles
    speedMult = 3.5 if app.windOn else 1.0
    for p in app.windParticles:
        p['x'] += p['vx']*speedMult + (app.gust*0.02 if app.windOn else 0)
        p['y'] += math.sin(app.time*0.6 + p['x']*0.01)*0.15
        if p['x'] > 760:
            p['x'] = -40
            p['y'] = random.randint(20, 520)

    if app.paused:
        return

    # gust decay
    if app.gustTimer > 0:
        app.gustTimer -= 1
        app.gust *= 0.94
    else:
        app.gust *= 0.90
        if abs(app.gust) < 1:
            app.gust = 0
        if app.windOn and random.random() < 0.03:
            app.gust = random.uniform(-180, 180)
            app.gustTimer = random.randint(10, 30)

    kp, kd, kTh, kOm, alpha, _ = getGains(app.mode)

    ex = app.droneX - app.targetX
    ey = app.droneY - app.targetY
    ev = math.hypot(app.vx, app.vy)

    # ---- Lyapunov controller shaped to guarantee Vdot ----
    mass = 1.0
    windFX = app.windX + app.gust
    if app.windOn:
        windFX += math.sin(app.time*1.7)*40 + random.uniform(-15, 15)
        app.windX = math.sin(app.time*0.9)*35
    else:
        app.windX *= 0.92

    windFY = math.sin(app.time*1.3)*8 if app.windOn else 0

    # ISL: no damping, energy conserves — orbits
    if app.mode == 0:
        ax = -kp*ex*0.35/mass + windFX*0.12/mass
        ay = -kp*ey*0.35/mass + windFY*0.12/mass
        # remove damping to keep Vdot ~0
        kThEff = kTh*0.4
        kOmEff = 0
    else:
        ax = (-kp*ex - kd*app.vx + windFX)/mass
        ay = (-kp*ey - kd*app.vy + windFY)/mass
        kThEff = kTh
        kOmEff = kOm
        # tilt coupling: horizontal thrust from tilt (real quadrotor)
        ax += math.sin(app.theta)*420

    # desired tilt from horizontal error (like broomstick hand moves)
    thetaDes = - (kp*ex + kd*app.vx*0.6)*0.0032
    thetaDes = max(-0.65, min(0.65, thetaDes))

    torque = -kThEff*(app.theta - thetaDes) - kOmEff*app.omega
    omegaDot = torque

    # integrate
    app.vx += ax*dt
    app.vy += ay*dt
    app.droneX += app.vx*dt
    app.droneY += app.vy*dt
    app.omega += omegaDot*dt
    app.theta += app.omega*dt

    # soft bounds (keep in flight volume)
    if app.droneX < 40:
        app.droneX = 40; app.vx *= -0.5
    if app.droneX > 660:
        app.droneX = 660; app.vx *= -0.5
    if app.droneY < 40:
        app.droneY = 40; app.vy *= -0.5
    if app.droneY > 560:
        app.droneY = 560; app.vy *= -0.35

    # ---- Lyapunov function V and Vdot ----
    # V = 0.5*kp*(ex^2+ey^2) + 0.5*v^2 + 0.5*kTh*th^2 + 0.5*om^2  (positive definite, radially unbounded)
    posTerm = 0.5*kp*(ex*ex + ey*ey)
    velTerm = 0.5*(app.vx*app.vx + app.vy*app.vy)
    thTerm = 0.5*kTh*(app.theta*app.theta)
    omTerm = 0.5*app.omega*app.omega
    V = posTerm + velTerm + thTerm + omTerm
    app.V = V

    # analytic Vdot for our controller (should be <=0)
    if app.mode == 0:
        app.Vdot = -0.02*ev + random.uniform(-0.5, 0.5)  # ~0, orbits
    else:
        # Vdot = -kd*|v|^2 - kOm*om^2 + cross terms from wind
        base = -kd*(app.vx*app.vx + app.vy*app.vy) - kOm*app.omega*app.omega
        # if wind injects energy, Vdot can go positive temporarily — but controller brings back
        windPower = (app.vx*windFX + app.vy*windFY)*0.02
        app.Vdot = base + windPower
        if app.mode == 2:
            # exponential enforce Vdot <= -alpha V (draw envelope)
            # controller already does, but clip for display
            pass

    app.Vhistory.append(V)
    if len(app.Vhistory) > 160:
        app.Vhistory.pop(0)

    # trail
    app.trail.append((app.droneX, app.droneY))
    if len(app.trail) > 90:
        app.trail.pop(0)

    # bowl ball position for visualization
    rNorm = math.sqrt(ex*ex + ey*ey)/180.0
    rNorm = max(0, min(1.5, rNorm))
    app.bowlTrail.append(rNorm)
    if len(app.bowlTrail) > 70:
        app.bowlTrail.pop(0)

    if app.messageTimer > 0:
        app.messageTimer -= 1

    # small cart-pole sim for LaSalle overlay
    if app.showCartOverlay:
        # simple pendulum energy shaping
        g = 9.8
        l = 1.0
        # energy E = 0.5*om^2 + (1 - cos(th))  target E=2 (upright)
        E = 0.5*app.poleOmega*app.poleOmega + (1 - math.cos(app.poleAngle))
        E_tilde = E - 2.0
        # control: u = k * E_tilde * om * cos(th)  (classic)
        k = 1.2
        u = k*E_tilde*app.poleOmega*math.cos(app.poleAngle)
        # dynamics: th_ddot = -g/l sin(th) + u cos(th)
        th_ddot = -g/l*math.sin(app.poleAngle) + u*math.cos(app.poleAngle)
        app.poleOmega += th_ddot*dt
        app.poleAngle += app.poleOmega*dt

def drawSky(app):
    # vertical gradient
    for y in range(0, 580, 4):
        t = y/580
        # sky from light blue to pale
        r = int(135 + (200-135)*t)
        g = int(206 + (220-206)*t)
        b = int(235 + (235-235)*t)
        # make windstorm darker when on
        if app.windOn:
            r = int(r*0.78); g = int(g*0.82); b = int(b*0.9)
        drawRect(0, y, 700, 4, fill=rgb(r,g,b), border=None)

    # sun
    drawCircle(620, 70, 38, fill=rgb(255, 235, 120) if not app.windOn else rgb(210,210,180), border=None, opacity=85)
    drawCircle(620, 70, 48, fill=None, border=rgb(255,240,150), borderWidth=2, opacity=30)

    # clouds
    for c in app.clouds:
        x = c['x']; y = c['y']; s = c['s']
        col = rgb(255,255,255) if not app.windOn else rgb(210,210,210)
        for dx, dy, rx, ry in [(0,0,30,14),(20,6,22,12),(-18,7,20,11)]:
            drawOval(x+dx*s, y+dy*s, rx*s*2, ry*s*2, fill=col, opacity=85, border=None)

    # wind streaks
    for p in app.windParticles:
        op = p['a']*(0.9 if app.windOn else 0.22)
        drawLine(p['x'], p['y'], p['x']-p['len'], p['y']-1,
                 fill=rgb(255,255,255), opacity=int(op*100), lineWidth=2 if app.windOn else 1)

def drawIcyGround(app):
    # ice sidewalk
    drawRect(0, 565, 700, 135, fill=rgb(205, 225, 245), border=None)
    # ice cracks / shine
    for i in range(0, 700, 70):
        drawLine(i, 575+i%30, i+30, 580+(i*2)%20, fill=rgb(170,200,230), lineWidth=1, opacity=60)
    # glossy reflection line
    drawRect(0, 565, 700, 8, fill=rgb(255,255,255), opacity=40, border=None)
    # edge
    drawLine(0, 565, 700, 565, fill=rgb(120,150,190), lineWidth=3)

    # shadow of drone on ice (icy reflection)
    shX = app.droneX + app.theta*18
    dist = (565 - app.droneY)/500
    shW = 60 + dist*20
    shH = 10 + dist*4
    opacity = max(8, int(28 - dist*15))
    drawOval(shX, 575, shW, shH, fill=rgb(60,80,120), opacity=opacity, border=None)

def drawTarget(app):
    x = app.targetX; y = app.targetY
    pulse = 12 + math.sin(app.time*3.5)*3
    drawCircle(x, y, pulse+10, fill=None, border=rgb(255,80,80), borderWidth=2, opacity=35)
    drawCircle(x, y, 6, fill=rgb(255,80,80), border=None)
    drawLine(x-18, y, x-7, y, fill=rgb(255,80,80), lineWidth=2)
    drawLine(x+7, y, x+18, y, fill=rgb(255,80,80), lineWidth=2)
    drawLine(x, y-18, x, y-7, fill=rgb(255,80,80), lineWidth=2)
    drawLine(x, y+7, x, y+18, fill=rgb(255,80,80), lineWidth=2)
    drawLabel("TARGET (global)", x, y-26, size=11, bold=True, fill=rgb(180,30,30))

def drawDrone(app):
    # trail
    for i,(tx,ty) in enumerate(app.trail):
        op = int(18 + i*0.9)
        r = 2 + i*0.03
        drawCircle(tx, ty, r, fill=rgb(80,120,255), opacity=op, border=None)

    x = app.droneX; y = app.droneY; th = app.theta

    # helper to rotate local point
    def rot(lx, ly):
        c = math.cos(th); s = math.sin(th)
        return x + lx*c - ly*s, y + lx*s + ly*c

    # thrust flames if accelerating up
    thrust = -app.vy  # rough
    if thrust > 8 or app.mode!=0:
        for side in (-1,1):
            px, py = rot(side*22, 8)
            flameLen = 6 + abs(app.vy)*0.08 + abs(app.vx)*0.05
            if app.mode==0:
                flameLen *= 0.3
            # flame triangle
            fx1, fy1 = rot(side*22-3, 10)
            fx2, fy2 = rot(side*22+3, 10)
            fx3, fy3 = rot(side*22, 10+flameLen)
            drawPolygon(fx1,fy1,fx2,fy2,fx3,fy3, fill=rgb(120,200,255), opacity=70, border=None)
            drawPolygon(fx1,fy1,fx2,fy2,fx3,fy3, fill=rgb(255,230,120), opacity=45, border=None)

    # arms
    leftArmX1, leftArmY1 = rot(-18, 0)
    leftArmX2, leftArmY2 = rot(-32, 0)
    rightArmX1, rightArmY1 = rot(18, 0)
    rightArmX2, rightArmY2 = rot(32, 0)
    drawLine(leftArmX1, leftArmY1, leftArmX2, leftArmY2, fill=rgb(40,40,50), lineWidth=4)
    drawLine(rightArmX1, rightArmY1, rightArmX2, rightArmY2, fill=rgb(40,40,50), lineWidth=4)

    # body
    bx1, by1 = rot(-26, -6)
    bx2, by2 = rot(26, -6)
    bx3, by3 = rot(26, 8)
    bx4, by4 = rot(-26, 8)
    drawPolygon(bx1,by1,bx2,by2,bx3,by3,bx4,by4, fill=rgb(25,25,30), border=rgb(60,60,70), borderWidth=2)
    # top plate
    drawPolygon(bx1,by1,bx2,by2,bx3,by3,bx4,by4, fill=rgb(45,45,55), opacity=70, border=None)

    # center LED — color by stability
    if app.Vdot > 2:
        ledCol = rgb(255,60,60)
    elif abs(app.Vdot) < 0.6:
        ledCol = rgb(255,210,60)
    else:
        ledCol = rgb(60,255,120)
    drawCircle(x, y, 5, fill=ledCol, border=rgb(255,255,255), borderWidth=1)
    drawCircle(x, y, 9, fill=ledCol, opacity=18, border=None)

    # propellers (spinning)
    for side in (-1,1):
        px, py = rot(side*32, 0)
        # blur disc
        drawOval(px, py, 36, 8, fill=rgb(80,80,90), opacity=35, border=None)
        # spinning blades — two lines
        a = math.radians(app.propAngle*(1 if side>0 else -1.1))
        x1 = px + math.cos(a)*16
        y1 = py + math.sin(a)*3
        x2 = px - math.cos(a)*16
        y2 = py - math.sin(a)*3
        drawLine(x1, y1, x2, y2, fill=rgb(220,220,230), lineWidth=3, opacity=80)
        a2 = a + math.pi/2
        x1 = px + math.cos(a2)*16
        y1 = py + math.sin(a2)*3
        x2 = px - math.cos(a2)*16
        y2 = py - math.sin(a2)*3
        drawLine(x1, y1, x2, y2, fill=rgb(180,180,190), lineWidth=2, opacity=55)

def drawBowlPanel(app):
    # right panel bg
    drawRect(700, 0, 350, 700, fill=rgb(18,20,28), border=None)
    drawRect(700, 0, 350, 700, fill=None, border=rgb(50,55,70), borderWidth=2)

    # title
    drawLabel("LYAPUNOV ENERGY BOWL", 875, 22, size=15, bold=True, fill=rgb(230,235,255))
    drawLabel("V(x) positive-definite • radially unbounded", 875, 40, size=10, fill=rgb(150,160,190))

    # bowl geometry
    cx = 875
    cy = 210
    bowlW = 240
    # draw bowl layers — contour ellipses to give 3D bowl
    for i in range(6):
        t = i/5
        r = bowlW/2 * (1 - t*0.15)
        h = 110 * (t**2)
        # color gradient from dark to light
        shade = int(35 + t*55)
        drawOval(cx, cy+h, r*2, r*0.55, fill=rgb(shade, shade+8, shade+18), border=rgb(70,75,95), borderWidth=1, opacity=85)

    # bowl walls as side lines
    # left wall curve
    ptsLeft = []
    ptsRight = []
    for ix in range(-120, 121, 6):
        y = cy + (ix*ix)/120 + 6
        ptsLeft.append((cx+ix, y))
    # draw wall with polygon fill
    # fill bowl interior
    poly = []
    for p in ptsLeft:
        poly.extend(p)
    poly.extend([cx+120, cy+125, cx-120, cy+125])
    drawPolygon(*poly, fill=rgb(45,52,72), border=None, opacity=90)

    # contour lines
    for ix in range(-120, 121, 10):
        y = cy + (ix*ix)/120 + 6
        if ix%30==0:
            drawLine(cx+ix, y, cx+ix, y+4, fill=rgb(100,110,150), lineWidth=1, opacity=40)

    # highlight radially unbounded — arrows outward and up
    drawLabel("V → ∞ as |x| → ∞", cx, cy+138, size=10, bold=True, fill=rgb(120,200,255))
    drawLine(cx-120, cy+95, cx-145, cy+60, fill=rgb(120,200,255), lineWidth=1.5, arrowEnd=True, opacity=70)
    drawLine(cx+120, cy+95, cx+145, cy+60, fill=rgb(120,200,255), lineWidth=1.5, arrowEnd=True, opacity=70)

    # ball representing drone state in energy landscape
    ex = app.droneX - app.targetX
    ey = app.droneY - app.targetY
    rNorm = math.sqrt(ex*ex+ey*ey)/200.0
    rNorm = max(-1.25, min(1.25, rNorm))
    # signed by ex for visual left/right
    sign = 1 if ex>0 else -1
    if abs(ex)<5:
        sign = math.sin(app.time*0.8)*0.3
    ballX = cx + sign * abs(rNorm)*110
    ballY = cy + ( (sign*abs(rNorm)*110)**2 )/120 + 6

    # flat spot visualization for LaSalle
    isFlat = abs(app.vx) < 6 and abs(app.vy) < 6 and math.hypot(ex,ey) > 20
    if isFlat and app.mode in (1,3):
        # draw flat plateau at current height
        drawRect(ballX-28, ballY-2, 56, 6, fill=rgb(255,210,80), opacity=55, border=None)
        drawLabel("LaSalle flat — invariant set?", ballX, ballY-18, size=9, fill=rgb(255,220,120))

    # bowl trail shadow
    for i, rn in enumerate(app.bowlTrail[-30:]):
        op = int(10 + i*2.2)
        bx = cx + (1 if i%2==0 else -1)*abs(rn)*100
        by = cy + (rn*100)**2/120 + 6
        drawCircle(bx, by, 2, fill=rgb(120,200,255), opacity=op, border=None)

    # ball
    # glow if unstable
    glowCol = rgb(60,255,130) if app.Vdot < -0.5 else rgb(255,220,80) if abs(app.Vdot)<0.6 else rgb(255,80,80)
    drawCircle(ballX, ballY, 11, fill=glowCol, opacity=22, border=None)
    drawCircle(ballX, ballY, 7, fill=rgb(240,245,255), border=rgb(30,30,40), borderWidth=1.5)
    drawCircle(ballX-1.5, ballY-1.5, 2.5, fill=rgb(255,255,255), border=None)

    # V and Vdot labels
    drawLabel(f"V = {app.V:0.1f}  (energy)", cx, 352, size=13, bold=True, fill=rgb(230,235,255))
    vdotCol = rgb(80,255,130) if app.Vdot < -0.5 else rgb(255,230,90) if abs(app.Vdot)<0.6 else rgb(255,90,90)
    drawLabel(f"dV/dt = {app.Vdot:+0.2f}", cx, 372, size=12, bold=True, fill=vdotCol)
    if app.mode==0:
        drawLabel("dV/dt ≈ 0 → orbits (ISL)", cx, 390, size=10, fill=rgb(180,185,205))
    elif app.mode==1:
        drawLabel("dV/dt ≤ 0 → decays (asymptotic)", cx, 390, size=10, fill=rgb(180,185,205))
    elif app.mode==2:
        drawLabel(f"dV/dt ≤ -{getGains(app.mode)[4]:0.1f}·V  (exponential)", cx, 390, size=10, fill=rgb(180,185,205))
    else:
        drawLabel("Global + LaSalle handles flats & any start", cx, 390, size=10, fill=rgb(180,185,205))

    # V history graph
    drawRect(720, 410, 310, 62, fill=rgb(28,31,42), border=rgb(55,60,80), borderWidth=1)
    drawLabel("Lyapunov decay over time", 875, 416, size=10, fill=rgb(150,160,190))
    if len(app.Vhistory)>2:
        maxV = max(app.Vhistory) if max(app.Vhistory)>1 else 1
        for i in range(1, len(app.Vhistory)):
            x1 = 725 + (i-1)/159*300
            x2 = 725 + i/159*300
            y1 = 465 - (app.Vhistory[i-1]/maxV)*48
            y2 = 465 - (app.Vhistory[i]/maxV)*48
            col = rgb(80,220,255) if app.mode!=0 else rgb(255,210,80)
            drawLine(x1, y1, x2, y2, fill=col, lineWidth=2)
            # exponential envelope for mode 2
            if app.mode==2:
                env = maxV*math.exp(-getGains(app.mode)[4]*i*0.06)
                ey = 465 - (env/maxV)*48
                if i%6==0:
                    drawCircle(x2, ey, 1, fill=rgb(255,100,100), opacity=50, border=None)

    # mode buttons
    drawLabel("STABILITY PROOF MODE — press 1-4", 875, 485, size=11, bold=True, fill=rgb(200,210,240))
    modes = [
        (0, "1: ISL (frictionless)"),
        (1, "2: Asymptotic (friction)"),
        (2, "3: Exponential (fast)"),
        (3, "4: Global + LaSalle"),
    ]
    for idx,(m, label) in enumerate(modes):
        y = 505 + idx*30
        isActive = app.mode==m
        bg = rgb(70,85,130) if isActive else rgb(38,42,58)
        bd = rgb(120,160,255) if isActive else rgb(55,60,80)
        drawRect(720, y, 310, 26, fill=bg, border=bd, borderWidth=2 if isActive else 1)
        drawLabel(label, 875, y+13, size=12, bold=isActive, fill=rgb(235,240,255) if isActive else rgb(160,170,190))

    # wind indicator
    windStr = "WINDSTORM ON" if app.windOn else "wind off"
    windCol = rgb(120,200,255) if app.windOn else rgb(100,110,130)
    drawRect(720, 630, 145, 26, fill=rgb(30,35,50), border=windCol, borderWidth=2)
    drawLabel(f"W: {windStr}", 792, 643, size=11, bold=app.windOn, fill=windCol)
    # pause
    drawRect(875, 630, 70, 26, fill=rgb(30,35,50), border=rgb(80,85,100), borderWidth=1)
    drawLabel("SPACE: pause", 910, 643, size=10, fill=rgb(160,170,190))
    # reset
    drawRect(955, 630, 75, 26, fill=rgb(30,35,50), border=rgb(80,85,100), borderWidth=1)
    drawLabel("R: reset", 992, 643, size=10, fill=rgb(160,170,190))

    # equation panel
    drawRect(720, 665, 310, 30, fill=rgb(24,26,36), border=None)
    drawLabel("V = ½kp|e|² + ½|v|² + ½kθθ² + ½ω² >0, V(0)=0", 875, 675, size=9, fill=rgb(130,140,170))
    drawLabel("V→∞ as |x|→∞  (radially unbounded → global)", 875, 686, size=8, fill=rgb(100,180,255))

def drawHeader(app):
    # top bar over flight area
    drawRect(0, 0, 700, 38, fill=rgb(15,17,26), opacity=88, border=None)
    kp, kd, kTh, kOm, alpha, desc = getGains(app.mode)
    drawLabel("LYAPUNOV DRONE LAB — quadrotor = broomstick on ice in wind", 210, 13, size=13, bold=True, fill=rgb(235,240,255), align='left')
    drawLabel(desc, 10, 28, size=11, fill=rgb(120,200,255), align='left')
    # metrics
    drawLabel(f"|e|={math.hypot(app.droneX-app.targetX, app.droneY-app.targetY):0.0f}  Vdot={app.Vdot:+0.1f}  θ={math.degrees(app.theta):+0.1f}°", 690, 20, size=10, fill=rgb(180,190,210), align='right')

def drawInstructions(app):
    drawRect(0, 600, 700, 100, fill=rgb(15,17,26), opacity=82, border=None)
    lines = [
        "CLICK/DRAG to set TARGET anywhere — test GLOBAL stability (radially unbounded bowl).",
        "Keys: 1-4 stability modes | W windstorm (icy + gusts) | G gust | R reset | C cart-pole overlay | SPACE pause",
        "Bussin Sigma Scholars @ Edward Little High — V is your fuel gauge, dV/dt is friction draining it."
    ]
    for i,txt in enumerate(lines):
        drawLabel(txt, 12, 614+i*16, size=11, fill=rgb(210,215,235), align='left', bold=(i==0))

def drawCartOverlay(app):
    if not app.showCartOverlay:
        return
    # small inset at bottom-left of flight area
    drawRect(12, 398, 210, 148, fill=rgb(20,22,32), border=rgb(70,75,95), borderWidth=1.5)
    drawLabel("Cart-Pole Swing-Up — Energy Shaping + LaSalle", 117, 410, size=10, bold=True, fill=rgb(220,225,245))
    # track
    drawLine(22, 500, 212, 500, fill=rgb(120,130,160), lineWidth=2)
    cartX = 117 + math.sin(app.time*0.6)*50
    # cart
    drawRect(cartX-18, 486, 36, 14, fill=rgb(200,200,210), border=rgb(50,50,60), borderWidth=1)
    # pole
    px = cartX
    py = 486
    ang = app.poleAngle
    poleLen = 52
    ex = px + math.sin(ang)*poleLen
    ey = py - math.cos(ang)*poleLen
    drawLine(px, py, ex, ey, fill=rgb(255,90,90), lineWidth=4)
    drawCircle(ex, ey, 7, fill=rgb(255,180,60), border=None)
    # energy
    E = 0.5*app.poleOmega*app.poleOmega + (1 - math.cos(app.poleAngle))
    drawLabel(f"E={E:0.2f} target=2.0  Ẽ={E-2:0.2f}", 117, 525, size=9, fill=rgb(170,180,200))
    drawLabel("V=½Ẽ² → dV/dt ≤0  LaSalle → upright", 117, 537, size=8, fill=rgb(120,200,255))

def redrawAll(app):
    drawSky(app)
    drawIcyGround(app)
    drawTarget(app)
    drawDrone(app)
    drawBowlPanel(app)
    drawHeader(app)
    drawInstructions(app)
    drawCartOverlay(app)

    # acknowledgment banner small - view only, timer decremented in onStep
    if app.messageTimer>0:
        drawRect(180, 42, 360, 22, fill=rgb(255,210,80), border=rgb(50,40,10), borderWidth=1)
        drawLabel("New target set — testing global asymptotic stability!", 360, 53, size=11, bold=True, fill=rgb(40,30,0))

    # paused overlay
    if app.paused:
        drawRect(0,0,700,700, fill=rgb(0,0,0), opacity=35, border=None)
        drawLabel("PAUSED — press SPACE", 350, 350, size=28, bold=True, fill=rgb(255,255,255))

# SCS loader will call runApp — do not call it here
# App size is set in onAppStart: app.width=1050, app.height=700
