
from scs import *
import math
import random

# ============================================================
# GORILLAS - Top-Tier SCS Port of QBasic Gorillas
# 1050 x 700 - Lazy / Deferred Destructibility
# No wind - pure angle/power physics
# Minimum font size 13 enforced
# ============================================================

WIDTH = 1050
HEIGHT = 700
GROUND_HEIGHT = 650  # bottom of buildings
SKY_TOP = 0
SUN_X = WIDTH // 2
SUN_Y = 70
SUN_RADIUS = 28

GRAVITY = 0.18   # tuned for 60 FPS, power 5-32 range
BANANA_SCALE = 0.38
EXPLOSION_RADIUS = 36

# --- Building colors - high contrast city ---
BUILDING_PALETTE = [
    rgb(60, 65, 80),
    rgb(70, 75, 95),
    rgb(85, 90, 110),
    rgb(55, 60, 85),
    rgb(90, 85, 100),
    rgb(75, 80, 100),
]
WINDOW_ON = rgb(255, 230, 120)
WINDOW_OFF = rgb(30, 35, 50)

class DamageHole:
    __slots__ = ('x','y','r')
    def __init__(self, x, y, r):
        self.x = x
        self.y = y
        self.r = r

class Fragment:
    __slots__ = ('x','y','w','h','vx','vy','rot','rotSpeed','color','life','active')
    def __init__(self, x, y, w, h, vx, vy, color):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.vx = vx
        self.vy = vy
        self.rot = random.uniform(0, 360)
        self.rotSpeed = random.uniform(-12, 12)
        self.color = color
        self.life = 1.0
        self.active = True

class Building:
    __slots__ = ('x','y','w','h','color','windows','holes','fragments','isStatic','id')
    def __init__(self, x, y, w, h, color, bid):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.color = color
        self.windows = []  # list of (wx, wy, ww, wh, on)
        self.holes = []    # list of DamageHole - lazy carving
        self.fragments = []  # only populated near impact
        self.isStatic = True  # ultra cheap until hit
        self.id = bid
        self._genWindows()

    def _genWindows(self):
        # cheap window grid, only generated once
        wx_step = 14
        wy_step = 18
        ww, wh = 6, 9
        # inset
        start_x = self.x + 8
        end_x = self.x + self.w - 8 - ww
        start_y = self.y + 12
        end_y = self.y + self.h - 12
        y = start_y
        while y <= end_y:
            x = start_x
            while x <= end_x:
                on = random.random() > 0.35
                self.windows.append((x, y, ww, wh, on))
                x += wx_step
            y += wy_step

    def containsSolid(self, px, py):
        # ultra cheap AABB first
        if px < self.x or px > self.x + self.w or py < self.y or py > self.y + self.h:
            return False
        # check holes - if inside any hole, it's empty (not solid)
        for hole in self.holes:
            dx = px - hole.x
            dy = py - hole.y
            if dx*dx + dy*dy <= hole.r * hole.r:
                return False
        return True

    def addDamage(self, hx, hy, radius=EXPLOSION_RADIUS):
        # LAZY MATERIALIZATION: keep single collider until now
        # then carve locally and spawn only nearby fragments
        self.isStatic = False
        # clamp hole inside building bounds but allow slight overflow for nice crater
        self.holes.append(DamageHole(hx, hy, radius))
        # spawn localized fragments only near hit - not entire building
        fragCount = 14
        baseColor = self.color
        for _ in range(fragCount):
            # spawn within 1.5*radius of impact
            ang = random.uniform(0, 2*math.pi)
            dist = random.uniform(0, radius*1.1)
            fx = hx + math.cos(ang)*dist + random.uniform(-6,6)
            fy = hy + math.sin(ang)*dist + random.uniform(-6,6)
            # only if near building
            if fx < self.x - 10 or fx > self.x + self.w + 10:
                continue
            fw = random.randint(4, 10)
            fh = random.randint(4, 10)
            vx = math.cos(ang)*random.uniform(1.5, 5.5) + random.uniform(-1,1)
            vy = math.sin(ang)*random.uniform(1.5, 5.5) - random.uniform(1,3)  # pop upward
            # slightly darker fragment
            r = max(0, min(255, (baseColor.red if hasattr(baseColor,'red') else 70) + random.randint(-15,15)))
            # use base color with variation
            fragColor = rgb(
                max(30, min(255, 70 + random.randint(-20,20))),
                max(30, min(255, 75 + random.randint(-20,20))),
                max(30, min(255, 95 + random.randint(-20,20)))
            )
            self.fragments.append(Fragment(fx, fy, fw, fh, vx, vy, fragColor))
        # limit holes to avoid degenerate check - merge if too many
        if len(self.holes) > 12:
            self.holes = self.holes[-10:]

    def updateFragments(self):
        alive = []
        for f in self.fragments:
            if not f.active:
                continue
            f.vy += GRAVITY * 0.6
            f.x += f.vx
            f.y += f.vy
            f.vx *= 0.99
            f.rot += f.rotSpeed
            # ground collision
            if f.y + f.h >= GROUND_HEIGHT:
                f.y = GROUND_HEIGHT - f.h
                f.vy *= -0.25
                f.vx *= 0.7
                if abs(f.vy) < 0.6:
                    f.vy = 0
                    f.rotSpeed *= 0.8
            if f.y < HEIGHT + 50:
                alive.append(f)
        self.fragments = alive

    def draw(self, app):
        # single cheap rect if static and no holes
        if self.isStatic and len(self.holes)==0:
            drawRect(self.x, self.y, self.w, self.h, fill=self.color, border=None)
            # windows - ultra cheap batch
            for wx, wy, ww, wh, on in self.windows:
                if on:
                    drawRect(wx, wy, ww, wh, fill=WINDOW_ON, border=None)
                else:
                    drawRect(wx, wy, ww, wh, fill=WINDOW_OFF, border=None)
            return
        # damaged path - draw base then carve holes via background circles
        drawRect(self.x, self.y, self.w, self.h, fill=self.color, border=None)
        # windows with hole culling
        for wx, wy, ww, wh, on in self.windows:
            # center check against holes
            cx = wx + ww/2
            cy = wy + wh/2
            insideHole = False
            for hole in self.holes:
                if (cx-hole.x)**2 + (cy-hole.y)**2 < (hole.r-2)**2:
                    insideHole = True
                    break
            if insideHole:
                continue
            if on:
                drawRect(wx, wy, ww, wh, fill=WINDOW_ON, border=None)
            else:
                drawRect(wx, wy, ww, wh, fill=WINDOW_OFF, border=None)
        # carve holes - draw sky color circles (lazy damage visual)
        for hole in self.holes:
            # use app.sky gradient approximation: solid sky fill for performance
            drawCircle(hole.x, hole.y, hole.r, fill=app.skyColor, border=None)
            # inner darker rim for depth
            drawCircle(hole.x, hole.y, hole.r, fill=None, border=rgb(40,45,60), borderWidth=2)
        # draw active fragments on top
        for f in self.fragments:
            # simple rect with rotation via polygon
            cx = f.x + f.w/2
            cy = f.y + f.h/2
            drawRect(cx, cy, f.w, f.h, fill=f.color, border=None, align='center', rotateAngle=f.rot)

def generateCity(app):
    # Port of QBasic MakeCityScape slope logic
    buildings = []
    x = 2
    slope = random.randint(1,6)
    # slope types: 1 up, 2 down, 3-5 V, 6 inv V
    if slope == 1:
        newHt = 30
        htInc = 9
    elif slope == 2:
        newHt = 170
        htInc = -9
    else:
        newHt = 35
        htInc = 10

    randomHeight = 140
    defBWidth = 55
    cur = 0
    while x < WIDTH - 40:
        if slope == 1:
            newHt += htInc
        elif slope == 2:
            newHt += htInc
        elif slope in (3,4,5):
            if x > WIDTH//2:
                newHt -= 2*abs(htInc)*0.6
            else:
                newHt += 2*abs(htInc)*0.6
        else: # 6 inverted V
            if x > WIDTH//2:
                newHt += 2*abs(htInc)*0.6
            else:
                newHt -= 2*abs(htInc)*0.6

        bWidth = random.randint(defBWidth-12, defBWidth+18)
        if x + bWidth > WIDTH:
            bWidth = WIDTH - x - 2
        if bWidth < 30:
            bWidth = 30

        bHeight = int(random.randint(20, randomHeight) + newHt)
        bHeight = max(30, min(bHeight, GROUND_HEIGHT - 80 - 20))  # leave room for gorilla

        bottom = GROUND_HEIGHT
        top = bottom - bHeight
        # ensure not too tall to block sun
        if top < SUN_Y + SUN_RADIUS + 30 + 25:  # keep clear
            # adjust
            bHeight = bottom - (SUN_Y + SUN_RADIUS + 55)
            top = bottom - bHeight

        color = random.choice(BUILDING_PALETTE)
        b = Building(x, top, bWidth, bHeight, color, cur)
        buildings.append(b)
        x += bWidth + 6
        cur += 1
        if cur > 22:
            break

    return buildings

def placeGorillas(buildings):
    # place on 2nd or 3rd from edges - like QBasic
    if len(buildings) < 5:
        leftB = buildings[0]
        rightB = buildings[-1]
    else:
        leftIdx = random.randint(1,2)
        rightIdx = len(buildings) - random.randint(1,2) -1
        leftB = buildings[leftIdx]
        rightB = buildings[rightIdx]

    # gorilla size offsets
    gorillaW = 28
    gorillaH = 32
    g1x = leftB.x + leftB.w//2 - gorillaW//2
    g1y = leftB.y - gorillaH + 2
    g2x = rightB.x + rightB.w//2 - gorillaW//2
    g2y = rightB.y - gorillaH + 2

    return (g1x, g1y, leftB), (g2x, g2y, rightB)

def drawGorilla(x, y, armState='down', facing=1, isCurrent=False):
    # x,y top-left of gorilla base
    # facing 1 = right (player1), -1 = left (player2)
    # armState: down, leftUp, rightUp, bothUp, victory
    # Body parts - high quality but cheap
    # shadow
    drawOval(x+14, y+34, 30, 8, fill=rgb(0,0,0,0.22), border=None)

    # legs
    drawRect(x+4, y+22, 8, 12, fill=rgb(40,25,15), border=None, roundness=3)
    drawRect(x+16, y+22, 8, 12, fill=rgb(40,25,15), border=None, roundness=3)

    # body
    drawRect(x+2, y+10, 24, 16, fill=rgb(70,45,25), border=rgb(30,20,10), borderWidth=1, roundness=5)
    # chest highlight
    drawCircle(x+10, y+16, 7, fill=rgb(90,65,40), border=None)
    drawCircle(x+18, y+16, 7, fill=rgb(90,65,40), border=None)

    # head
    drawRect(x+5, y+0, 18, 14, fill=rgb(85,60,40), border=rgb(30,20,10), borderWidth=1, roundness=4)
    # eyes
    drawCircle(x+10, y+5, 2, fill=rgb(255,255,255), border=None)
    drawCircle(x+18, y+5, 2, fill=rgb(255,255,255), border=None)
    drawCircle(x+10, y+5.5, 1, fill=rgb(0,0,0), border=None)
    drawCircle(x+18, y+5.5, 1, fill=rgb(0,0,0), border=None)
    # brow
    drawLine(x+7, y+3, x+12, y+3, fill=rgb(0,0,0), lineWidth=1)
    drawLine(x+16, y+3, x+21, y+3, fill=rgb(0,0,0), lineWidth=1)
    # nose dots
    drawCircle(x+13, y+9, 0.8, fill=rgb(0,0,0), border=None)
    drawCircle(x+15, y+9, 0.8, fill=rgb(0,0,0), border=None)

    # arms - based on state
    # right arm from body's right, left arm from left
    if armState == 'down' or armState == 'bothDown':
        # both down
        drawLine(x+2, y+14, x-2, y+24, fill=rgb(70,45,25), lineWidth=6)
        drawLine(x+26, y+14, x+30, y+24, fill=rgb(70,45,25), lineWidth=6)
    elif armState == 'rightUp':  # throw arm up (player1 right, player2 left mirrored)
        if facing == 1:
            drawLine(x+2, y+14, x-2, y+24, fill=rgb(70,45,25), lineWidth=6)
            drawLine(x+26, y+14, x+34, y+2, fill=rgb(70,45,25), lineWidth=6)
            # hand
            drawCircle(x+35, y+1, 4, fill=rgb(85,60,40), border=None)
        else:
            drawLine(x+26, y+14, x+30, y+24, fill=rgb(70,45,25), lineWidth=6)
            drawLine(x+2, y+14, x-6, y+2, fill=rgb(70,45,25), lineWidth=6)
            drawCircle(x-7, y+1, 4, fill=rgb(85,60,40), border=None)
    elif armState == 'leftUp':
        if facing == 1:
            drawLine(x+26, y+14, x+30, y+24, fill=rgb(70,45,25), lineWidth=6)
            drawLine(x+2, y+14, x-6, y+2, fill=rgb(70,45,25), lineWidth=6)
            drawCircle(x-7, y+1, 4, fill=rgb(85,60,40), border=None)
        else:
            drawLine(x+2, y+14, x-2, y+24, fill=rgb(70,45,25), lineWidth=6)
            drawLine(x+26, y+14, x+34, y+2, fill=rgb(70,45,25), lineWidth=6)
            drawCircle(x+35, y+1, 4, fill=rgb(85,60,40), border=None)
    elif armState == 'victory':
        # both up waving
        drawLine(x+2, y+14, x-4, y+0, fill=rgb(70,45,25), lineWidth=6)
        drawLine(x+26, y+14, x+32, y+0, fill=rgb(70,45,25), lineWidth=6)
        drawCircle(x-5, y-1, 4, fill=rgb(85,60,40), border=None)
        drawCircle(x+33, y-1, 4, fill=rgb(85,60,40), border=None)

    if isCurrent:
        # highlight ring
        drawRect(x-3, y-3, 34, 40, fill=None, border=rgb(255,220,80), borderWidth=2, roundness=8, dashes=(4,4))

def drawBanana(x, y, rot, scale=1.0):
    # rot 0-3 or continuous - draw banana as curved polygon with peel
    # high quality: use polygon + arc
    # banana shape: crescent
    # We'll draw rotated banana using Group math manually: 4 orientations like original but smooth
    # For top-tier: draw as curved thick line with yellow fill and brown tips
    # rot in degrees
    # Convert to radians for shape
    r = math.radians(rot)
    # banana length
    length = 14*scale
    width = 6*scale
    # center line arc
    # approximate with 2 ovals
    # We'll draw banana as two overlapping circles subtraction visually via polygon
    # Simplest: draw thick arc
    # Use polygon for curved shape
    # Create banana points along curve
    points = []
    # banana curvature 60 degrees
    for i in range(7):
        t = i/6.0
        # along banana from -0.5 to 0.5 length
        along = (t-0.5)*length
        # curve offset
        curve = math.sin(t*math.pi)*width*0.8
        # rotate point
        px = along*math.cos(r) - curve*math.sin(r)
        py = along*math.sin(r) + curve*math.cos(r)
        points.append((x+px, y+py))
    # draw as thick line with yellow
    for i in range(len(points)-1):
        drawLine(points[i][0], points[i][1], points[i+1][0], points[i+1][1], fill=rgb(255,230,30), lineWidth=width)
    # brown tips
    drawCircle(points[0][0], points[0][1], 2.5*scale, fill=rgb(90,55,15), border=None)
    drawCircle(points[-1][0], points[-1][1], 2.5*scale, fill=rgb(90,55,15), border=None)
    # highlight
    drawCircle(x, y, 1.5*scale, fill=rgb(255,255,180), border=None)

def drawSun(x, y, state='happy', shockTimer=0):
    # body
    if state == 'shocked':
        col = rgb(255, 200, 80)
        # shocked rays wobble
        rayLen = 22 + math.sin(shockTimer*0.5)*3
    else:
        col = rgb(255, 220, 80)
        rayLen = 20

    # rays
    for ang in range(0, 360, 30):
        rad = math.radians(ang)
        x2 = x + math.cos(rad)*rayLen
        y2 = y + math.sin(rad)*rayLen
        drawLine(x, y, x2, y2, fill=rgb(255, 210, 60), lineWidth=3)

    drawCircle(x, y, SUN_RADIUS, fill=col, border=rgb(255,180,0), borderWidth=2)

    # eyes
    drawCircle(x-8, y-5, 4, fill=rgb(0,0,0), border=None)
    drawCircle(x+8, y-5, 4, fill=rgb(0,0,0), border=None)
    drawCircle(x-7, y-6, 1.5, fill=rgb(255,255,255), border=None)
    drawCircle(x+9, y-6, 1.5, fill=rgb(255,255,255), border=None)

    if state == 'shocked':
        drawCircle(x, y+8, 8, fill=rgb(0,0,0), border=None)
        drawCircle(x, y+8, 4, fill=rgb(255,150,150), border=None)
    else:
        # smile arc
        drawArc(x, y+2, 14, 10, 20, 160, fill=None, border=rgb(0,0,0), borderWidth=2)
        # rosy
        drawOval(x-14, y+6, 6, 3, fill=rgb(255,120,120,0.5), border=None)
        drawOval(x+14, y+6, 6, 3, fill=rgb(255,120,120,0.5), border=None)

def onAppStart(app):
    app.width = WIDTH
    app.height = HEIGHT
    app.stepsPerSecond = 60
    app.background = rgb(12, 14, 20)  # will override with custom sky draw
    app.skyColor = rgb(135, 206, 235)
    app.skyTop = rgb(100, 160, 220)
    app.skyBottom = rgb(185, 225, 250)

    app.buildings = []
    app.gorillaPos = []  # [(x,y, building), ...]
    app.scores = [0,0]
    app.playerNames = ["Player 1", "Player 2"]
    app.currentPlayer = 0  # 0 or 1
    app.angle = [45, 135]  # degrees, player2 90-180
    app.power = [18, 18]
    app.dragging = False
    app.dragStart = None
    app.dragCurrent = None
    app.banana = None  # dict x,y,vx,vy,rot
    app.trail = []  # list of (x,y)
    app.state = 'aiming'  # aiming, flying, exploding, dancing, gameOver
    app.explosion = None  # dict x,y,r, life
    app.particles = []  # explosion particles
    app.sunState = 'happy'
    app.sunShockTimer = 0
    app.victoryTimer = 0
    app.winner = None
    app.message = "Drag from gorilla to aim, release to throw!"
    app.messageTimer = 180
    app.gamesToWin = 3
    app.totalGames = 0
    app.gravity = GRAVITY
    app.showTrajectory = True
    app.aimLine = None

    startNewRound(app)

def startNewRound(app):
    app.buildings = generateCity(app)
    g1, g2 = placeGorillas(app.buildings)
    app.gorillaPos = [g1, g2]
    app.banana = None
    app.trail = []
    app.explosion = None
    app.particles = []
    app.state = 'aiming'
    app.sunState = 'happy'
    app.sunShockTimer = 0
    app.victoryTimer = 0
    app.winner = None
    app.dragging = False
    # keep scores, switch starting player every round?
    # reset angles to face opponent
    # Player1 should aim right, Player2 left
    app.angle = [45, 135]
    app.power = [18, 18]
    app.message = f"{app.playerNames[app.currentPlayer]}'s turn - drag to aim"
    app.messageTimer = 120

def fireBanana(app):
    if app.state != 'aiming':
        return
    idx = app.currentPlayer
    gx, gy, bld = app.gorillaPos[idx]
    # launch point near hand
    if idx == 0:
        sx = gx + 28
        sy = gy + 2
    else:
        sx = gx - 4
        sy = gy + 2

    ang = math.radians(app.angle[idx])
    p = app.power[idx]
    vx = math.cos(ang) * p * BANANA_SCALE
    vy = -math.sin(ang) * p * BANANA_SCALE

    app.banana = {
        'x': sx,
        'y': sy,
        'vx': vx,
        'vy': vy,
        'rot': 0,
        'trail': []
    }
    app.state = 'flying'
    app.trail = []
    app.message = ""
    # throw animation arm up briefly
    # handled in draw

def createExplosion(app, x, y, hitGorilla=False, hitSun=False):
    app.explosion = {'x': x, 'y': y, 'r': 6, 'maxR': EXPLOSION_RADIUS + (12 if hitGorilla else 0), 'growing': True}
    # particles
    for _ in range(32 if hitGorilla else 20):
        ang = random.uniform(0, 2*math.pi)
        speed = random.uniform(1.5, 7)
        app.particles.append({
            'x': x, 'y': y,
            'vx': math.cos(ang)*speed,
            'vy': math.sin(ang)*speed - 1,
            'r': random.uniform(2,5),
            'life': 1.0,
            'color': random.choice([rgb(255,120,20), rgb(255,200,50), rgb(255,80,20), rgb(200,200,200)])
        })
    if hitSun:
        app.sunState = 'shocked'
        app.sunShockTimer = 90

def checkGorillaHit(app, bx, by):
    for i, (gx, gy, bld) in enumerate(app.gorillaPos):
        # gorilla bounding box ~ 28x34
        if gx-4 <= bx <= gx+32 and gy-4 <= by <= gy+36:
            return i
    return -1

def onStep(app):
    # sun shock timer
    if app.sunShockTimer > 0:
        app.sunShockTimer -= 1
        if app.sunShockTimer == 0:
            app.sunState = 'happy'

    # update building fragments - only active fragments, ultra cheap when static
    for b in app.buildings:
        if not b.isStatic and len(b.fragments) > 0:
            b.updateFragments()

    if app.messageTimer > 0:
        app.messageTimer -= 1

    if app.state == 'flying' and app.banana:
        b = app.banana
        # physics
        b['vy'] += app.gravity
        b['x'] += b['vx']
        b['y'] += b['vy']
        b['rot'] += 18 + abs(b['vx'])*2
        b['trail'].append((b['x'], b['y']))
        if len(b['trail']) > 18:
            b['trail'].pop(0)

        x, y = b['x'], b['y']

        # off screen
        if x < -20 or x > WIDTH+20 or y > GROUND_HEIGHT+20:
            app.banana = None
            app.state = 'aiming'
            app.currentPlayer = 1 - app.currentPlayer
            app.message = f"{app.playerNames[app.currentPlayer]}'s turn"
            app.messageTimer = 90
            return

        # sun hit
        dxSun = x - SUN_X
        dySun = y - SUN_Y
        if dxSun*dxSun + dySun*dySun < (SUN_RADIUS+8)**2:
            createExplosion(app, x, y, hitSun=True)
            app.banana = None
            app.state = 'exploding'
            return

        # gorilla hit
        hitG = checkGorillaHit(app, x, y)
        if hitG != -1:
            # explosion on gorilla
            createExplosion(app, x, y, hitGorilla=True)
            app.banana = None
            app.state = 'exploding'
            app.winner = 1 - hitG  # other player wins round
            return

        # building hit - LAZY CHECK: first AABB cheap, then holes check only if needed
        for building in app.buildings:
            if building.containsSolid(x, y):
                # carve damage locally - materialize only near hit
                building.addDamage(x, y, EXPLOSION_RADIUS)
                createExplosion(app, x, y)
                app.banana = None
                app.state = 'exploding'
                return

    elif app.state == 'exploding':
        if app.explosion:
            exp = app.explosion
            if exp['growing']:
                exp['r'] += 3.2
                if exp['r'] >= exp['maxR']:
                    exp['growing'] = False
            else:
                exp['r'] -= 2.5
                if exp['r'] <= 0:
                    app.explosion = None
                    # if gorilla was hit, go to victory dance
                    if app.winner is not None:
                        app.state = 'dancing'
                        app.victoryTimer = 120
                        app.scores[app.winner] += 1
                        app.totalGames += 1
                        app.message = f"{app.playerNames[app.winner]} wins the round!"
                        app.messageTimer = 150
                    else:
                        # miss - next player
                        app.state = 'aiming'
                        app.currentPlayer = 1 - app.currentPlayer
                        app.message = f"{app.playerNames[app.currentPlayer]}'s turn"
                        app.messageTimer = 90
        # update explosion particles
        newParts = []
        for p in app.particles:
            p['x'] += p['vx']
            p['y'] += p['vy']
            p['vy'] += 0.18
            p['vx'] *= 0.99
            p['life'] -= 0.025
            if p['life'] > 0:
                newParts.append(p)
        app.particles = newParts
        if app.explosion is None and len(app.particles)==0 and app.winner is None:
            # ensure state returns
            if app.state == 'exploding':
                app.state = 'aiming'

    elif app.state == 'dancing':
        app.victoryTimer -= 1
        # dance animation timer
        if app.victoryTimer <= 0:
            # check game over
            if max(app.scores) >= app.gamesToWin:
                app.state = 'gameOver'
            else:
                # next round, switch starter
                app.currentPlayer = 1 - app.currentPlayer
                startNewRound(app)

    elif app.state == 'gameOver':
        pass

def onMousePress(app, mx, my):
    if app.state == 'gameOver':
        # restart
        app.scores = [0,0]
        app.totalGames = 0
        app.currentPlayer = 0
        startNewRound(app)
        return

    if app.state != 'aiming':
        return

    idx = app.currentPlayer
    gx, gy, bld = app.gorillaPos[idx]
    # check near gorilla to start drag
    gcx = gx + 14
    gcy = gy + 12
    if distance(gcx, gcy, mx, my) < 80:
        app.dragging = True
        app.dragStart = (gcx, gcy)
        app.dragCurrent = (mx, my)
        updateAimFromDrag(app, mx, my)

def onMouseDrag(app, mx, my):
    if not app.dragging or app.state != 'aiming':
        return
    app.dragCurrent = (mx, my)
    updateAimFromDrag(app, mx, my)

def onMouseRelease(app, mx, my):
    if not app.dragging:
        return
    app.dragging = False
    app.dragCurrent = (mx, my)
    updateAimFromDrag(app, mx, my)
    # if power reasonable, fire
    if app.power[app.currentPlayer] >= 4:
        fireBanana(app)

def updateAimFromDrag(app, mx, my):
    idx = app.currentPlayer
    gx, gy, bld = app.gorillaPos[idx]
    gcx = gx + 14
    gcy = gy + 16
    dx = mx - gcx
    dy = gcy - my  # invert y for angle
    # angle in degrees
    ang = math.degrees(math.atan2(dy, dx))
    if ang < 0:
        ang += 360
    # Clamp angle per player for intuitive play
    # Player 0 (left) wants 0-90, Player1 (right) wants 90-180
    # But allow full 0-180 for flexibility, just wrap
    if idx == 0:
        # left player: prefer 10-88 deg, but if dragging behind, clamp
        if ang > 180:
            # dragging backwards, reflect
            ang = 180 - (ang-180)
        ang = max(5, min(88, ang))
    else:
        # right player: 92-175
        if ang < 90:
            ang = 180 - ang
            if ang < 90:
                ang = 92
        ang = max(92, min(175, ang))

    dist = math.sqrt((mx-gcx)**2 + (my-gcy)**2)
    power = dist / 12.0
    power = max(3, min(32, power))

    app.angle[idx] = ang
    app.power[idx] = power

def onKeyPress(app, key):
    if app.state == 'gameOver':
        if key.lower() == 'r':
            app.scores = [0,0]
            app.totalGames = 0
            app.currentPlayer = 0
            startNewRound(app)
        return

    if app.state != 'aiming':
        if key.lower() == 'n':
            startNewRound(app)
        return

    idx = app.currentPlayer
    stepA = 2
    stepP = 0.8
    if key == 'left' or key.lower() == 'a':
        if idx == 0:
            app.angle[idx] = max(5, app.angle[idx]-stepA)
        else:
            app.angle[idx] = max(92, app.angle[idx]-stepA)
    elif key == 'right' or key.lower() == 'd':
        if idx == 0:
            app.angle[idx] = min(88, app.angle[idx]+stepA)
        else:
            app.angle[idx] = min(175, app.angle[idx]+stepA)
    elif key == 'up' or key.lower() == 'w':
        app.power[idx] = min(32, app.power[idx]+stepP)
    elif key == 'down' or key.lower() == 's':
        app.power[idx] = max(3, app.power[idx]-stepP)
    elif key == 'space':
        fireBanana(app)
    elif key.lower() == 'n':
        startNewRound(app)
    elif key.lower() == 't':
        app.showTrajectory = not app.showTrajectory
    elif key.lower() == 'r':
        startNewRound(app)

def drawTrajectory(app, idx):
    if app.state != 'aiming':
        return
    gx, gy, bld = app.gorillaPos[idx]
    if idx == 0:
        sx = gx + 28
        sy = gy + 2
    else:
        sx = gx - 4
        sy = gy + 2
    ang = math.radians(app.angle[idx])
    p = app.power[idx]
    vx = math.cos(ang) * p * BANANA_SCALE
    vy = -math.sin(ang) * p * BANANA_SCALE

    # simulate dots
    x, y = sx, sy
    simVx, simVy = vx, vy
    dots = []
    for i in range(80):
        x += simVx
        y += simVy
        simVy += app.gravity
        if i % 3 == 0:
            dots.append((x,y))
        # stop if would hit building or ground or out
        if y > GROUND_HEIGHT or x < 0 or x > WIDTH:
            break
        # building collision early break
        hitB = False
        for bld in app.buildings:
            if bld.containsSolid(x,y):
                hitB = True
                break
        if hitB:
            break
        # gorilla hit check (opponent)
        opp = 1-idx
        ogx, ogy, obld = app.gorillaPos[opp]
        if ogx-4 <= x <= ogx+32 and ogy-4 <= y <= ogy+36:
            break

    # draw dotted line
    for i, (dx, dy) in enumerate(dots):
        alpha = 1.0 - i/len(dots)*0.7
        size = 4 if i==0 else 3
        col = rgb(255, 255, 255, alpha*0.85) if i%2==0 else rgb(255, 230, 80, alpha*0.7)
        drawCircle(dx, dy, size, fill=col, border=None)

def redrawAll(app):
    # sky gradient - draw manually for hole carving color match
    # ultra cheap gradient via rects
    for i in range(0, HEIGHT, 4):
        t = i / GROUND_HEIGHT
        # lerp top to bottom
        r = int(100 + (185-100)*t)
        g = int(160 + (225-160)*t)
        b = int(220 + (250-220)*t)
        drawRect(0, i, WIDTH, 4, fill=rgb(r,g,b), border=None)

    # sun
    drawSun(SUN_X, SUN_Y, app.sunState, app.sunShockTimer)

    # buildings - LAZY: static buildings single rect, damaged only local work
    for bld in app.buildings:
        bld.draw(app)

    # ground
    drawRect(0, GROUND_HEIGHT, WIDTH, HEIGHT-GROUND_HEIGHT, fill=rgb(45,40,35), border=None)
    drawRect(0, GROUND_HEIGHT, WIDTH, 6, fill=rgb(70,70,70), border=None)

    # gorillas
    for i, (gx, gy, bld) in enumerate(app.gorillaPos):
        isCurrent = (i == app.currentPlayer and app.state == 'aiming')
        # determine arm state
        arm = 'down'
        if app.state == 'flying' and app.banana and i == app.currentPlayer:
            arm = 'rightUp' if i==0 else 'leftUp'
        elif app.state == 'dancing' and app.winner == i:
            # victory wave - alternate arms
            if (app.victoryTimer // 10) % 2 == 0:
                arm = 'leftUp'
            else:
                arm = 'rightUp'
        elif app.state == 'dancing' and app.winner is not None:
            arm = 'victory' if i==app.winner else 'down'
        drawGorilla(gx, gy, armState=arm, facing=1 if i==0 else -1, isCurrent=isCurrent)

    # trajectory preview
    if app.state == 'aiming' and app.showTrajectory:
        drawTrajectory(app, app.currentPlayer)

    # banana trail and banana
    if app.banana:
        # trail
        for j, (tx, ty) in enumerate(app.banana['trail']):
            alpha = (j+1)/len(app.banana['trail'])*0.6
            drawCircle(tx, ty, 2.5, fill=rgb(255,230,30,alpha), border=None)
        drawBanana(app.banana['x'], app.banana['y'], app.banana['rot'], scale=1.1)

    # explosion
    if app.explosion:
        exp = app.explosion
        # outer flash
        drawCircle(exp['x'], exp['y'], exp['r']+6, fill=rgb(255,200,30,0.35), border=None)
        drawCircle(exp['x'], exp['y'], exp['r'], fill=rgb(255,120,20), border=None)
        drawCircle(exp['x'], exp['y'], exp['r']*0.6, fill=rgb(255,220,100), border=None)
    # particles
    for p in app.particles:
        drawCircle(p['x'], p['y'], p['r']*p['life'], fill=p['color'], border=None)

    # HUD - top bar
    # semi-transparent header
    drawRect(0, 0, WIDTH, 92, fill=rgb(0,0,0,0.38), border=None)

    # player names and scores - font size >=13
    drawLabel(f"{app.playerNames[0]}: {app.scores[0]}", 18, 18, fill=rgb(255,255,255), size=18, bold=True, align='left')
    drawLabel(f"{app.playerNames[1]}: {app.scores[1]}", WIDTH-18, 18, fill=rgb(255,255,255), size=18, bold=True, align='right')

    # current turn indicator
    if app.state in ('aiming','flying','exploding','dancing'):
        turnText = f"TURN: {app.playerNames[app.currentPlayer].upper()}"
        drawLabel(turnText, WIDTH//2, 18, fill=rgb(255,220,80), size=20, bold=True, align='center')

    # angle/power for current player
    if app.state == 'aiming':
        idx = app.currentPlayer
        drawLabel(f"Angle: {app.angle[idx]:.1f}°", 18, 46, fill=rgb(200,230,255), size=15, align='left')
        drawLabel(f"Power: {app.power[idx]:.1f}", 18, 66, fill=rgb(200,230,255), size=15, align='left')
        # power bar
        barW = 160
        barH = 10
        pct = (app.power[idx]-3)/29.0
        drawRect(140, 62, barW, barH, fill=rgb(50,50,50), border=rgb(120,120,120), borderWidth=1, roundness=4)
        drawRect(140, 62, barW*pct, barH, fill=rgb(80,200,80), border=None, roundness=4)

        # controls help
        drawLabel("DRAG to aim, RELEASE to fire | A/D angle, W/S power, SPACE fire, T trajectory, N new city", WIDTH//2, 78, fill=rgb(180,190,200), size=13, align='center')

    # aim line when dragging
    if app.dragging and app.dragStart and app.dragCurrent:
        sx, sy = app.dragStart
        cx, cy = app.dragCurrent
        drawLine(sx, sy, cx, cy, fill=rgb(255,255,255,0.6), lineWidth=2, dashes=(6,4))
        drawCircle(cx, cy, 6, fill=rgb(255,255,255), border=rgb(0,0,0), borderWidth=1)

    # center message
    if app.message and app.messageTimer>0:
        # background pill
        tw = len(app.message)*8 + 24
        drawRect(WIDTH//2, HEIGHT//2 - 120, tw, 36, fill=rgb(0,0,0,0.55), border=None, roundness=18, align='center')
        drawLabel(app.message, WIDTH//2, HEIGHT//2 - 120, fill=rgb(255,255,200), size=16, bold=True, align='center')

    # game over overlay
    if app.state == 'gameOver':
        drawRect(0, 0, WIDTH, HEIGHT, fill=rgb(0,0,0,0.6), border=None)
        winnerIdx = 0 if app.scores[0] > app.scores[1] else 1
        drawLabel("GAME OVER", WIDTH//2, HEIGHT//2 - 80, fill=rgb(255,220,80), size=42, bold=True, align='center')
        drawLabel(f"{app.playerNames[winnerIdx]} WINS THE MATCH!", WIDTH//2, HEIGHT//2 - 20, fill=rgb(255,255,255), size=24, bold=True, align='center')
        drawLabel(f"Final Score {app.scores[0]} - {app.scores[1]}", WIDTH//2, HEIGHT//2 + 20, fill=rgb(200,200,200), size=18, align='center')
        drawLabel("Press R or Click to play again", WIDTH//2, HEIGHT//2 + 60, fill=rgb(150,200,255), size=16, align='center')
        # victory dance big gorilla
        drawGorilla(WIDTH//2-14, HEIGHT//2+90, armState='victory', facing=1)

    # performance debug - building stats (lazy system indicator)
    staticCount = sum(1 for b in app.buildings if b.isStatic)
    damagedCount = len(app.buildings) - staticCount
    drawLabel(f"Buildings: {len(app.buildings)} | Static: {staticCount} | Damaged: {damagedCount} | Fragments: {sum(len(b.fragments) for b in app.buildings)}", WIDTH//2, HEIGHT-12, fill=rgb(180,180,180), size=13, align='center')

# SCS auto-start handled by index.html loader - no runApp needed
