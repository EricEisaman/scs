from scs import *
import math
import random

# ---------- helpers (model only, no drawing) ----------
# local implementations to avoid NameError in sandbox where distance/angleTo may not be global
def distance(x1,y1,x2,y2):
    return math.hypot(x2-x1, y2-y1)
def angleTo(x1,y1,x2,y2):
    return math.degrees(math.atan2(y2-y1, x2-x1))
def getPointInDir(x,y, angleDeg, dist):
    rad = math.radians(angleDeg)
    return (x + dist*math.cos(rad), y + dist*math.sin(rad))
def makeList(rows, cols):
    return [[0]*cols for _ in range(rows)]
def rounded(n):
    return round(n)

def lerp(a,b,t): return a + (b-a)*t
def clamp(v, lo, hi): return max(lo, min(hi, v))
def rectsOverlap(ax,ay,aw,ah, bx,by,bw,bh):
    return (ax - aw/2 < bx + bw/2 and ax + aw/2 > bx - bw/2 and
            ay - ah/2 < by + bh/2 and ay + ah/2 > by - bh/2)

def spawnSawModel(app, x, y, targetX, targetY):
    ang = angleTo(x, y, targetX, targetY)
    speed = 6.5 if app.heli['phase']==1 else 7.5
    vx, vy = getPointInDir(0, 0, ang, speed)
    app.saws.append({
        'x': x, 'y': y, 'vx': vx, 'vy': vy, 'r': 18,
        'parryable': False, 'parryWindow': 0, 'parried': False,
        'life': 300, 'glow': 0, 'trail': []
    })

def spawnParticleModels(app, x, y, n, col, speed=6, ptype='spark'):
    for _ in range(n):
        a = random.uniform(0, 360)
        s = random.uniform(1, speed)
        vx, vy = getPointInDir(0, 0, a, s)
        app.particles.append({
            'x': x, 'y': y,
            'vx': vx + random.uniform(-1,1),
            'vy': vy - random.uniform(0,3),
            'life': random.randint(20,45), 'maxLife':45,
            'col': col, 'r': random.uniform(2,5), 'type': ptype,
        })

def onAppStart(app):
    app.stepsPerSecond = 60
    app.background = gradient(rgb(28,30,35), rgb(50,52,55), rgb(90,92,88), start='top')

    app.t = 0
    app.gameState = 'intro'
    app.message = "MOTORSLIVER // HELI-2 CARGO LIFTER - READY"
    app.messageTimer = 0
    app.screenShake = 0
    app.slowMo = 0
    app.victoryT = 0

    gh = 70
    app.platforms = [
        {'x': 525, 'y': 700 - gh/2, 'w': 1050, 'h': gh, 'type':'ground', 'yellow': True},
        {'x': 160, 'y': 560, 'w': 220, 'h': 18, 'type':'deck', 'yellow': True},
        {'x': 890, 'y': 560, 'w': 220, 'h': 18, 'type':'deck', 'yellow': True},
        {'x': 200, 'y': 430, 'w': 200, 'h': 16, 'type':'deck', 'yellow': True},
        {'x': 850, 'y': 430, 'w': 200, 'h': 16, 'type':'deck', 'yellow': False},
        {'x': 525, 'y': 330, 'w': 260, 'h': 12, 'type':'beam', 'yellow': True},
        {'x': 360, 'y': 485, 'w': 22, 'h': 260, 'type':'pillar', 'yellow': True},
        {'x': 690, 'y': 485, 'w': 22, 'h': 260, 'type':'pillar', 'yellow': True},
        {'x': 525, 'y': 600, 'w': 90, 'h': 10, 'type':'vault', 'yellow': False},
    ]
    app.demoGrid = makeList(2, 3)

    app.player = {
        'x': 525, 'y': 700 - gh - 40,
        'vx': 0, 'vy': 0, 'w': 22, 'h': 36,
        'onGround': False, 'onWall': False, 'wallSide': 0, 'wallSlideTimer':0, 'coyote':0,
        'facing': 1, 'hp': 3, 'invuln':0, 'parryTimer':0, 'isParrying':False,
        'isChainsawing':False, 'attached':False, 'attachOffsetX':0, 'sliceProgress':0.0,
    }
    app.heli = {
        'x': 525, 'y': 140, 'vx': 2.2, 'w': 260, 'h': 68,
        'state': 'patrol', 'stateTimer':0, 'phase':1,
        'segments': [False, False, False], 'curSeg':0,
        'stunTimer':0, 'flybyDir':1, 'rotor':0, 'wobble':0,
        'targetY':140, 'flash':0,
    }
    app.saws = []
    app.particles = []
    app.orbie = {'x': 480, 'y': 500, 'bob':0}
    app.keysHeld = set()

def onKeyPress(app, key):
    key = key.lower()
    if key == 'r':
        onAppStart(app)
        app.gameState = 'playing'
        return
    if app.gameState == 'intro':
        if key in ('1','2'):
            app.gameState = 'playing'
            app.message = "P: 'Let's sliver.' // PARRY [K]" if key=='1' else "Orbie: '...sawdust in lens.' // [K] PARRY"
            app.messageTimer = 200
        return
    if app.gameState in ('victory','defeat'):
        if key in (' ', 'space'):
            onAppStart(app)
            app.gameState = 'playing'
        return

    p = app.player
    if key in ('w',' ','up','space'):
        if p['onGround'] or p['coyote']>0 or p['attached']:
            p['vy'] = -13.5
            p['onGround'] = False
            p['coyote'] = 0
            p['attached'] = False
            p['sliceProgress'] = max(0, p['sliceProgress']-0.05)
            spawnParticleModels(app, p['x'], p['y']+p['h']/2, 6, rgb(175,172,165), 3, 'sand')
        elif p['onWall']:
            p['vy'] = -12
            p['vx'] = -p['wallSide'] * 8
            p['onWall'] = False
            p['facing'] = -p['wallSide']
            spawnParticleModels(app, p['x'], p['y'], 8, rgb(255,209,0), 4, 'spark')
        app.keysHeld.add('jump')

    if key == 'k':
        if not p['isParrying']:
            p['isParrying'] = True
            p['parryTimer'] = 18
            p['invuln'] = 6
            app.keysHeld.add('parry')
            for saw in app.saws:
                if not saw['parried'] and saw['parryable'] and distance(p['x'], p['y'], saw['x'], saw['y']) < 85:
                    saw['parried'] = True
                    saw['parryable'] = False
                    ang = angleTo(saw['x'], saw['y'], app.heli['x'], app.heli['y'])
                    vx, vy = getPointInDir(0,0,ang,12)
                    saw['vx'] = vx
                    saw['vy'] = vy
                    saw['glow'] = 30
                    p['vx'] += -vx*0.33
                    app.slowMo = 12
                    app.screenShake = 10
                    spawnParticleModels(app, saw['x'], saw['y'], 16, rgb(255,160,50), 8, 'spark')
                    app.message = "PARRY! SAW RETURNED - BOARD NOW!"
                    app.messageTimer = 90
                    break

    if key == 'j':
        app.keysHeld.add('chainsaw')
        p['isChainsawing'] = True

def onKeyRelease(app, key):
    key = key.lower()
    if key == 'j':
        app.keysHeld.discard('chainsaw')
        app.player['isChainsawing'] = False
    if key == 'k':
        app.keysHeld.discard('parry')
    if key in ('w',' ','up','space'):
        app.keysHeld.discard('jump')
        if app.player['vy'] < -6:
            app.player['vy'] = -6

def onKeyHold(app, keys):
    if app.gameState != 'playing': return
    p = app.player
    move = 0
    if 'a' in keys or 'left' in keys: move -= 1
    if 'd' in keys or 'right' in keys: move += 1
    if not p['attached']:
        targetVx = move * 5.2
        accel = 0.55 if p['onGround'] else 0.28
        p['vx'] = lerp(p['vx'], targetVx, accel)
        if move != 0:
            p['facing'] = 1 if move>0 else -1
    else:
        if move != 0:
            p['attachOffsetX'] += move * 2.8
            p['attachOffsetX'] = clamp(p['attachOffsetX'], -app.heli['w']/2 + 12, app.heli['w']/2 - 12)
            if p['isChainsawing']:
                p['sliceProgress'] += 0.008 * abs(move) + 0.006

def onMousePress(app, mx, my):
    if app.gameState == 'intro':
        app.gameState = 'playing'

def onStep(app):
    app.t += 1
    if app.gameState == 'intro':
        app.orbie['bob'] += 0.08
        app.orbie['x'] = lerp(app.orbie['x'], 525 + math.sin(app.t*0.03)*30, 0.05)
        app.orbie['y'] = lerp(app.orbie['y'], 380 + math.sin(app.orbie['bob'])*8, 0.05)
        return

    if app.gameState in ('victory','defeat'):
        app.victoryT += 1
        if app.gameState == 'victory':
            app.heli['y'] += 2
            app.heli['wobble'] += 0.2
            if app.victoryT % 3 == 0:
                spawnParticleModels(app, app.heli['x']+random.uniform(-130,130), app.heli['y'], 2, rgb(175,172,165), 5, 'sand')
        for part in app.particles[:]:
            part['x']+=part['vx']; part['y']+=part['vy']; part['vy']+=0.2 if part['type']=='sand' else 0.15
            part['vx']*=0.98; part['life']-=1
            if part['life']<=0: app.particles.remove(part)
        return

    if app.slowMo>0: app.slowMo-=1
    if app.screenShake>0: app.screenShake-=1
    if app.messageTimer>0: app.messageTimer-=1

    p = app.player
    h = app.heli

    if p['parryTimer']>0:
        p['parryTimer']-=1
        if p['parryTimer']==0: p['isParrying']=False
    if p['invuln']>0: p['invuln']-=1
    if h['flash']>0: h['flash']-=1

    h['rotor'] += 0.6
    h['stateTimer'] +=1

    if h['state']=='patrol':
        h['x']+=h['vx']
        if h['x']<180: h['x']=180; h['vx']=abs(h['vx'])
        if h['x']>870: h['x']=870; h['vx']=-abs(h['vx'])
        h['y']=lerp(h['y'], h['targetY']+math.sin(app.t*0.02)*8, 0.08)
        if h['stateTimer']>130:
            h['state']='telegraph'; h['stateTimer']=0; h['flash']=40
            app.message="HELI TELEGRAPH // ORANGE SAW INCOMING"; app.messageTimer=70

    elif h['state']=='telegraph':
        h['vx']*=0.85; h['wobble']=math.sin(app.t*0.5)*2
        if h['stateTimer']>40:
            spawnSawModel(app, h['x'], h['y']+20, p['x'], p['y'])
            h['state']='attack'; h['stateTimer']=0
            app.message="SAW LAUNCHED - [K] TO PARRY WHEN GLOWING!"; app.messageTimer=90

    elif h['state']=='attack':
        h['vx']*=0.9
        if h['stateTimer']>120 or len(app.saws)==0:
            h['state']='patrol'; h['stateTimer']=0; h['targetY']=random.uniform(120,180)
            h['vx']=random.choice([-2.2,2.2])

    elif h['state']=='stunned':
        h['targetY']=465
        h['y']=lerp(h['y'], h['targetY'], 0.12)
        h['vx']=lerp(h['vx'],0,0.12)
        h['wobble']=math.sin(app.t*0.3)*1.5
        h['stunTimer']-=1
        if h['stunTimer']<=0:
            if h['segments'][h['curSeg']]:
                h['curSeg']+=1
                if h['curSeg']>=3:
                    app.gameState='victory'
                    app.message="MOTORSLIVER // HELI-2 DESTROYED"; app.messageTimer=300
                    h['state']='crash'
                    spawnParticleModels(app, h['x'], h['y'], 60, rgb(255,122,0), 9, 'spark')
                    spawnParticleModels(app, h['x'], h['y'], 80, rgb(175,172,165), 8, 'sand')
                else:
                    h['phase']=2; h['state']='recover'; h['stateTimer']=0
                    app.message=f"SEGMENT {h['curSeg']} SLIVERED // FLYBY PHASE!"; app.messageTimer=150
            else:
                h['state']='recover'; h['stateTimer']=0
                app.message="STUN EXPIRED - READ FLIGHT PATH"; app.messageTimer=90

    elif h['state']=='flyby':
        h['x']+=9*h['flybyDir']
        if h['flybyDir']==1 and h['x']>1050+200:
            h['x']=-200; h['y']=random.uniform(240,360)
        elif h['flybyDir']==-1 and h['x']<-200:
            h['x']=1050+200; h['y']=random.uniform(240,360)
        h['y']+=math.sin(app.t*0.08)*1.2
        h['rotor']+=0.9
        if h['stateTimer']>240 and random.random()<0.02:
            h['flybyDir']*=-1; h['stateTimer']=0
        if h['stateTimer']%60<30: h['flash']=5

    elif h['state']=='boarded':
        h['x']+=h['flybyDir']*2.2
        h['y']=lerp(h['y'],300,0.04)
        h['wobble']=math.sin(app.t*0.4)*3
        h['stunTimer']-=1
        if h['stunTimer']<=0:
            if h['segments'][h['curSeg']]:
                h['curSeg']+=1
                if h['curSeg']>=3:
                    app.gameState='victory'; h['state']='crash'
                    app.message="FINAL SLIVER // CRASHING ON ROOFTOP"; app.messageTimer=300
                else:
                    h['state']='flyby'; h['stateTimer']=0; h['flybyDir']=-h['flybyDir']
                    app.message=f"SEGMENT {h['curSeg']} SLIVERED! ONE MORE!"; app.messageTimer=120
            else:
                h['state']='flyby'; h['stateTimer']=0; p['attached']=False; p['vy']=-5
                app.message="LOST GRIP! READ THE FLIGHT PATH AGAIN"; app.messageTimer=90
        if h['x']<150 or h['x']>900: h['flybyDir']*=-1

    elif h['state']=='recover':
        h['y']=lerp(h['y'],140,0.08)
        h['wobble']*=0.9
        if abs(h['y']-140)<5:
            if h['phase']==1:
                h['state']='patrol'; h['vx']=random.choice([-2.2,2.2])
            else:
                h['state']='flyby'; h['x']=-200 if h['flybyDir']==1 else 1050+200; h['y']=random.uniform(240,340)
            h['stateTimer']=0; p['attached']=False; p['sliceProgress']=0

    elif h['state']=='crash':
        h['y']+=3; h['rotor']+=1.5; h['wobble']+=0.3

    if not p['attached']:
        p['vy']+=0.72
        if p['vy']>12: p['vy']=12
        nextX = p['x']+p['vx']
        for plat in app.platforms:
            if plat['type'] in ('pillar','ground'):
                if rectsOverlap(nextX, p['y'], p['w'], p['h'], plat['x'], plat['y'], plat['w'], plat['h']):
                    if p['vx']>0: nextX=plat['x']-plat['w']/2-p['w']/2-0.1
                    else: nextX=plat['x']+plat['w']/2+p['w']/2+0.1
                    p['vx']=0
                    if plat['yellow'] and not p['onGround'] and p['vy']>0:
                        p['onWall']=True; p['wallSide']=1 if plat['x']<p['x'] else -1; p['wallSlideTimer']=12
        p['x']=nextX
        nextY=p['y']+p['vy']
        p['onGround']=False
        p['onWall']=False
        for plat in app.platforms:
            if rectsOverlap(p['x'], nextY, p['w'], p['h'], plat['x'], plat['y'], plat['w'], plat['h']):
                if p['vy']>0 and p['y']<plat['y']-plat['h']/2:
                    nextY=plat['y']-plat['h']/2-p['h']/2; p['vy']=0; p['onGround']=True; p['coyote']=8
                elif p['vy']<0 and p['y']>plat['y']+plat['h']/2:
                    nextY=plat['y']+plat['h']/2+p['h']/2; p['vy']=0
            if plat['type']=='pillar' and plat['yellow']:
                if abs(p['x']-plat['x'])<plat['w']/2+p['w']/2+6 and abs(p['y']-plat['y'])<plat['h']/2+p['h']/2:
                    if not p['onGround'] and p['vy']>0:
                        p['onWall']=True; p['wallSide']=1 if plat['x']<p['x'] else -1; p['vy']*=0.68; p['wallSlideTimer']=max(p['wallSlideTimer'],4)
        p['y']=nextY
        if p['onGround']:
            p['vx']*=0.82
            if abs(p['vx'])<0.1: p['vx']=0
        else:
            p['vx']*=0.98
            if p['coyote']>0: p['coyote']-=1
            if p['wallSlideTimer']>0: p['wallSlideTimer']-=1
        if p['x']<p['w']/2+12: p['x']=p['w']/2+12; p['vx']=0; p['onWall']=True; p['wallSide']=-1
        if p['x']>1050-p['w']/2-12: p['x']=1050-p['w']/2-12; p['vx']=0; p['onWall']=True; p['wallSide']=1
        if p['y']>700+100:
            p['hp']-=1; p['y']=700-200; p['x']=525; p['vy']=-10; p['vx']=0; p['invuln']=60; app.screenShake=8
            app.message="FELL INTO VOID // WATCH FOOTING"; app.messageTimer=90
            if p['hp']<=0: app.gameState='defeat'
        if h['state'] in ('stunned','flyby','boarded'):
            if distance(p['x'], p['y'], h['x'], h['y'])<170 and p['y']<h['y']+30:
                if p['isChainsawing'] or 'chainsaw' in app.keysHeld:
                    if h['state']=='flyby':
                        if p['vy']>0 and p['y']<h['y']:
                            p['attached']=True; p['attachOffsetX']=p['x']-h['x']
                            h['state']='boarded'; h['stunTimer']=420; h['flybyDir']=1 if h['x']<525 else -1
                            app.message="BOARDED DURING FLYBY! HOLD [J] + MOVE!"; app.messageTimer=120; app.screenShake=6
                            spawnParticleModels(app, p['x'], p['y'], 12, rgb(255,122,0), 5, 'spark')
                    else:
                        p['attached']=True; p['attachOffsetX']=p['x']-h['x']
                        app.message="ON HULL - HOLD [J] AND TRAVERSE ORANGE!"; app.messageTimer=100
    else:
        p['x']=h['x']+p['attachOffsetX']
        p['y']=h['y']-45
        p['vx']=h['vx'] if h['state']!='boarded' else h['flybyDir']*2.2
        p['vy']=0
        p['onGround']=True
        if 'jump' in app.keysHeld:
            p['attached']=False; p['vy']=-11; p['vx']+=random.uniform(-2,2); app.keysHeld.discard('jump')
        if p['isChainsawing'] or 'chainsaw' in app.keysHeld:
            p['sliceProgress']+=0.012
            if random.random()<0.5:
                spawnParticleModels(app, p['x']+random.uniform(-8,8), p['y']+10, 1, rgb(255,160,50), 4, 'spark')
            if p['sliceProgress']>=1.0:
                h['segments'][h['curSeg']]=True
                p['sliceProgress']=0; p['attached']=False; p['vy']=-8; p['vx']=random.uniform(-3,3)
                spawnParticleModels(app, h['x'], h['y'], 30, rgb(255,122,0), 9, 'spark')
                spawnParticleModels(app, h['x'], h['y'], 20, rgb(255,209,0), 7, 'spark')
                app.screenShake=12; app.slowMo=8
        else:
            p['sliceProgress']=max(0,p['sliceProgress']-0.004)
        if abs(p['x']-h['x'])>h['w']/2+30:
            p['attached']=False; p['vy']=-2

    for saw in app.saws[:]:
        saw['trail'].append((saw['x'], saw['y']))
        if len(saw['trail'])>8: saw['trail'].pop(0)
        saw['x']+=saw['vx']; saw['y']+=saw['vy']; saw['vy']+=0.08; saw['life']-=1
        d = distance(saw['x'], saw['y'], p['x'], p['y'])
        if not saw['parried'] and 20<d<110:
            saw['parryable']=True; saw['parryWindow']=min(20,saw['parryWindow']+1); saw['glow']=min(25,saw['glow']+2)
        else:
            if saw['parryWindow']>0: saw['parryWindow']-=1
            else: saw['parryable']=False
            saw['glow']=max(0,saw['glow']-1)
        if saw['parried'] and distance(saw['x'], saw['y'], h['x'], h['y'])<110:
            if h['state'] in ('patrol','telegraph','attack'):
                h['state']='stunned'; h['stunTimer']=480; h['stateTimer']=0; h['flash']=60
                app.screenShake=15; app.slowMo=15
                spawnParticleModels(app, h['x'], h['y'], 25, rgb(255,160,50), 8, 'spark')
                app.message="STUNNED! HELI FORCED DOWN - BOARD IT!"; app.messageTimer=120
            app.saws.remove(saw); continue
        if not saw['parried'] and p['invuln']==0 and not p['attached']:
            if distance(saw['x'], saw['y'], p['x'], p['y'])<saw['r']+p['w']/2:
                p['hp']-=1; p['invuln']=90; p['vx']=(p['x']-saw['x'])*0.3; p['vy']=-6
                app.screenShake=10; spawnParticleModels(app, p['x'], p['y'], 12, rgb(235,235,230), 5, 'sand')
                app.message=f"HIT! HP {p['hp']}/3 - TIMING MATTERS"; app.messageTimer=80
                app.saws.remove(saw)
                if p['hp']<=0: app.gameState='defeat'
                continue
        if saw['life']<=0 or saw['x']<-100 or saw['x']>1150 or saw['y']>800:
            if saw in app.saws: app.saws.remove(saw)

    for part in app.particles[:]:
        part['x']+=part['vx']; part['y']+=part['vy']; part['vy']+=0.2 if part['type']=='sand' else 0.15
        part['vx']*=0.98; part['life']-=1
        if part['life']<=0: app.particles.remove(part)

    app.orbie['bob']+=0.05
    targetOx = p['x'] + p['facing']*40 + math.sin(app.t*0.02)*10
    targetOy = p['y'] - 55 + math.sin(app.orbie['bob'])*6
    app.orbie['x'] = lerp(app.orbie['x'], targetOx, 0.09)
    app.orbie['y'] = lerp(app.orbie['y'], targetOy, 0.09)

def redrawAll(app):
    shakeX = random.uniform(-app.screenShake, app.screenShake) if app.screenShake>0 else 0
    shakeY = random.uniform(-app.screenShake, app.screenShake) if app.screenShake>0 else 0

    # obelisk - Polygon
    obX = 525 + shakeX
    obY = 85 + shakeY
    drawPolygon(obX, obY-65, obX-18, obY+85, obX-10, obY+90, obX+10, obY+90, obX+18, obY+85, fill=rgb(22,22,20), opacity=90)

    # Lumen lights - Oval
    drawOval(315+shakeX, 280+shakeY, 600, 600, fill=rgb(255,255,255), opacity=3)
    drawOval(735+shakeX, 245+shakeY, 520, 520, fill=rgb(255,250,230), opacity=4)

    # platforms - Rect + Line dashes
    for plat in app.platforms:
        px = plat['x']+shakeX
        py = plat['y']+shakeY
        drawRect(px+4, py+6, plat['w'], plat['h'], fill=rgb(40,40,38), opacity=30)
        fillCol = rgb(82,80,76) if plat['type']=='ground' else rgb(118,116,110) if plat['type'] in ('deck','pillar') else rgb(175,172,165) if plat['type']=='vault' else rgb(95,93,88)
        drawRect(px - plat['w']/2, py - plat['h']/2, plat['w'], plat['h'], fill=fillCol, border=rgb(82,80,76), borderWidth=1)
        if plat['yellow']:
            if plat['type'] in ('deck','ground'):
                for sx in range(int(-plat['w']/2)+6, int(plat['w']/2)-6, 18):
                    drawLine(px+sx, py - plat['h']/2, px+sx+10, py - plat['h']/2, fill=rgb(255,209,0), lineWidth=3, opacity=90)
            elif plat['type']=='pillar':
                for sy in range(int(-plat['h']/2)+8, int(plat['h']/2)-8, 20):
                    drawRect(px - plat['w']/2 -1, py+sy, 4, 12, fill=rgb(255,209,0), opacity=85)
            elif plat['type']=='beam':
                drawRect(px - plat['w']/2, py - plat['h']/2 -2, plat['w'], 4, fill=rgb(255,209,0), opacity=90)

    # Orbie
    ox = app.orbie['x']+shakeX
    oy = app.orbie['y']+shakeY
    drawCircle(ox, oy, 18, fill=rgb(90,180,255), opacity=12)
    drawCircle(ox, oy, 12, fill=rgb(245,245,250), border=rgb(200,200,210), borderWidth=1)
    ang = angleTo(ox, oy, app.heli['x']+shakeX, app.heli['y']+shakeY)
    ex, ey = getPointInDir(ox, oy, ang, 4)
    drawCircle(ex+2, ey-1, 4, fill=rgb(90,180,255), border=rgb(20,20,30), borderWidth=1)
    drawLine(ox, oy-12, ox+4, oy-20, fill=rgb(82,80,76), lineWidth=2)
    drawCircle(ox+4, oy-20, 2.5, fill=rgb(255,209,0))

    # Heli
    h = app.heli
    hx = h['x']+shakeX + math.sin(h['wobble']*0.3)*2
    hy = h['y']+shakeY + math.cos(h['wobble']*0.4)*1.5
    shadowY = 630
    dToGround = distance(hx, hy, hx, shadowY)
    shadowAlpha = clamp(60 - dToGround/6, 0, 50)
    drawOval(hx, shadowY, h['w']*1.2 * clamp(1 - dToGround/800, 0.4, 1), 18, fill=rgb(40,40,38), opacity=shadowAlpha)

    rotorLen = h['w']*0.75
    drawLine(hx - rotorLen, hy-28 + math.sin(h['rotor'])*1, hx + rotorLen, hy-28 - math.sin(h['rotor'])*1, fill=rgb(200,200,200), lineWidth=3, opacity=60, rotateAngle=h['rotor']*2)
    drawLine(hx - rotorLen*0.8, hy-26, hx + rotorLen*0.8, hy-26, fill=rgb(180,180,180), lineWidth=2, opacity=40, rotateAngle=-h['rotor']*3)

    bodyFill = rgb(82,80,76) if h['state']!='stunned' else rgb(70,68,64)
    if h['flash']>0:
        t = h['flash']/40
        bodyFill = rgb(int(lerp(82,255,t)), int(lerp(80,160,t)), int(lerp(76,50,t)))
    drawRect(hx - h['w']/2, hy - h['h']/2, h['w'], h['h'], fill=bodyFill, border=rgb(30,30,28), borderWidth=2)
    drawRect(hx - h['w']/2 + 12, hy - h['h']/2 + 8, 58, 22, fill=rgb(50,55,65), border=rgb(20,20,20), borderWidth=1)
    drawRect(hx - h['w']/2 + 16, hy - h['h']/2 + 11, 50, 10, fill=rgb(120,140,180), opacity=50)
    drawRect(hx + h['w']/2, hy - 6, 68, 14, fill=rgb(82,80,76), border=rgb(30,30,28), borderWidth=1)
    drawCircle(hx + h['w']/2 + 68, hy, 10, fill=rgb(82,80,76), border=rgb(30,30,28), borderWidth=1)
    drawLine(hx + h['w']/2 + 68, hy-14, hx + h['w']/2 + 68, hy+14, fill=rgb(180,180,180), lineWidth=2, opacity=70)
    drawLine(hx - h['w']/3, hy + h['h']/2, hx - h['w']/3, hy + h['h']/2 + 14, fill=rgb(140,138,132), lineWidth=4)
    drawLine(hx + h['w']/3, hy + h['h']/2, hx + h['w']/3, hy + h['h']/2 + 14, fill=rgb(140,138,132), lineWidth=4)
    drawRect(hx - h['w']/2 -6, hy + h['h']/2 + 14, h['w']+12, 5, fill=rgb(40,40,38))
    drawRegularPolygon(hx - h['w']/2 + 20, hy - h['h']/2 + 12, 4, 6, fill=rgb(30,30,28), opacity=80)
    drawRegularPolygon(hx + h['w']/2 - 20, hy - h['h']/2 + 12, 4, 6, fill=rgb(30,30,28), opacity=80)

    if h['curSeg'] < 3 and not h['segments'][h['curSeg']]:
        weakW = h['w'] - 28
        weakY = hy + 2
        pulse = 0.7 + 0.3*math.sin(app.t*0.12) if h['state'] not in ('stunned','boarded') else 1.0 + 0.4*math.sin(app.t*0.25)
        drawRect(hx - weakW/2, weakY - 7, weakW, 14, fill=rgb(180,80,0), opacity=int(90*pulse), border=rgb(255,122,0), borderWidth=2)
        drawLine(hx - weakW/2 + 6, weakY, hx + weakW/2 -6, weakY, fill=rgb(255,209,0), lineWidth=2, dashes=(8,6), opacity=90)
        for ax in range(int(-weakW/2)+20, int(weakW/2)-10, 36):
            drawPolygon(hx+ax, weakY, hx+ax+6, weakY-4, hx+ax+6, weakY+4, fill=rgb(255,209,0), opacity=80)
        if app.player['attached'] and h['state'] in ('stunned','boarded'):
            progW = weakW * app.player['sliceProgress']
            drawRect(hx - weakW/2, weakY -7, progW, 14, fill=rgb(255,209,0), opacity=85)
            drawCircle(hx - weakW/2 + progW, weakY, 6, fill=rgb(255,255,255), opacity=80)
            drawCircle(hx - weakW/2 + progW, weakY, 3, fill=rgb(255,160,50))
            drawLine(hx - weakW/2, weakY - 22, hx - weakW/2 + progW, weakY - 22, fill=rgb(255,209,0), lineWidth=2, arrowEnd=True)
        if h['state'] in ('stunned','boarded'):
            drawLabel("SLIVER HERE // HOLD [J] + MOVE", hx, weakY - 22, size=11, fill=rgb(255,209,0), bold=True)

    for i in range(3):
        if h['segments'][i]:
            segX = hx - h['w']/2 + 20 + i* (h['w']-40)/3
            drawLine(segX, hy - h['h']/2, segX+8, hy + h['h']/2, fill=rgb(40,40,38), lineWidth=3, opacity=70)
            drawLabel("X", segX+12, hy, size=14, fill=rgb(255,122,0), bold=True)

    if h['state']=='telegraph':
        drawLabel("! ! !", hx, hy - 52, size=22, fill=rgb(255,160,50), bold=True)
        drawOval(hx, hy - 30, 40+ h['stateTimer'], 40+ h['stateTimer'], fill=None, border=rgb(255,160,50), borderWidth=2, opacity= max(0, 80 - h['stateTimer']))
    if h['state']=='stunned':
        drawLabel(f"GROUNDED - {max(0,h['stunTimer']//60)}s", hx, hy - 52, size=14, fill=rgb(255,209,0), bold=True)

    for saw in app.saws:
        sx = saw['x']+shakeX
        sy = saw['y']+shakeY
        for j, (tx,ty) in enumerate(saw['trail']):
            alpha = (j+1)/len(saw['trail'])*30
            drawCircle(tx+shakeX, ty+shakeY, saw['r']*(j+1)/len(saw['trail'])*0.6, fill=rgb(180,80,0), opacity=alpha)
        isOrange = saw['parryable']
        fillCol = rgb(255,160,50) if isOrange else rgb(180,180,180)
        borderCol = rgb(255,209,0) if isOrange else rgb(40,40,40)
        drawCircle(sx, sy, saw['r'], fill=fillCol, border=borderCol, borderWidth=3 if isOrange else 2)
        drawCircle(sx, sy, saw['r']*0.5, fill=rgb(30,30,30))
        ang = app.t*0.5 + saw['x']*0.02
        for k in range(8):
            a = ang + k*math.pi/4
            x1, y1 = getPointInDir(sx, sy, math.degrees(a), saw['r']*0.7)
            x2, y2 = getPointInDir(sx, sy, math.degrees(a), saw['r']*1.15)
            drawLine(x1, y1, x2, y2, fill=rgb(20,20,20), lineWidth=2)
        if isOrange:
            drawCircle(sx, sy, saw['r']+8 + math.sin(app.t*0.3)*4, fill=None, border=rgb(255,209,0), borderWidth=2, opacity=70)
            drawLabel("PARRY [K]", sx, sy-32, size=11, fill=rgb(255,209,0), bold=True)

    for part in app.particles:
        px = part['x']+shakeX
        py = part['y']+shakeY
        lifeT = part['life']/part['maxLife']
        if part['type']=='spark':
            drawStar(px, py, part['r']*1.5, 5, fill=part['col'], opacity=int(90*lifeT), roundness=30)
        else:
            drawRect(px, py, part['r'], part['r'], fill=part['col'], opacity=int(60*lifeT), rotateAngle=part['x']*2)

    p = app.player
    px = p['x']+shakeX
    py = p['y']+shakeY
    if p['invuln']%6<3:
        drawOval(px, 638+shakeY, 24, 8, fill=rgb(40,40,38), opacity=30)
        drawRect(px-6, py+8, 6, 14, fill=rgb(50,50,55), border=rgb(30,30,30), borderWidth=1)
        drawRect(px+2, py+8, 6, 14, fill=rgb(50,50,55), border=rgb(30,30,30), borderWidth=1)
        drawRect(px - 9, py -10, 18, 20, fill=rgb(180,60,50), border=rgb(30,30,30), borderWidth=1)
        drawRect(px -9, py -4, 18, 6, fill=rgb(255,209,0), opacity=85)
        drawCircle(px, py-18, 9, fill=rgb(235,235,230), border=rgb(30,30,30), borderWidth=1)
        drawRect(px-10, py-24, 20, 6, fill=rgb(30,30,30))
        sawOffX = 14 * p['facing']
        sawY = py -2
        if p['isChainsawing']:
            drawRect(px + sawOffX -3, sawY-2, 22, 8, fill=rgb(230,230,220), border=rgb(20,20,20), borderWidth=1)
            drawRect(px + sawOffX + 10, sawY-1, 14, 4, fill=rgb(255,122,0), border=None)
        else:
            drawRect(px + sawOffX -3, sawY-2, 18, 6, fill=rgb(230,230,220), border=rgb(20,20,20), borderWidth=1)
        drawCircle(px + 4*p['facing'], py-18, 1.5, fill=rgb(20,20,20))
        if p['isParrying']:
            arcR = 28 + (18 - p['parryTimer'])
            drawArc(px + p['facing']*10, py-4, arcR*2, arcR*2, -50*p['facing'], 100, fill=None, border=rgb(255,160,50), borderWidth=4, opacity= max(0, 90 - p['parryTimer']*3))
            drawLabel("PARRY!", px, py-38, size=12, fill=rgb(255,160,50), bold=True)
        if p['onWall']:
            drawLabel("WALL-RUN", px, py-42, size=10, fill=rgb(255,209,0), bold=True)
            wx = px + p['wallSide']*14
            drawLine(wx, py-12, wx, py+12, fill=rgb(255,209,0), lineWidth=2, opacity=70)

    barW = 420
    barH = 18
    barX = 525 + shakeX
    barY = 36 + shakeY
    drawRect(barX - barW/2 -2, barY - barH/2 -2, barW+4, barH+4, fill=rgb(20,20,20), opacity=90)
    segW = barW/3
    for i in range(3):
        segFill = rgb(255,209,0) if app.heli['segments'][i] else (rgb(255,122,0) if i==app.heli['curSeg'] else rgb(60,60,60))
        x = barX - barW/2 + segW*i + segW/2
        pulse = rounded(15*math.sin(app.t*0.2)) if i==app.heli['curSeg'] and not app.heli['segments'][i] else 0
        drawRect(x - segW/2 +1, barY - barH/2, segW-2, barH, fill=segFill, opacity=95 if app.heli['segments'][i] else 80 + pulse)
        drawLine(x + segW/2, barY - barH/2, x + segW/2, barY + barH/2, fill=rgb(20,20,20), lineWidth=2)

    drawLabel(f"MOTORSLIVER // HELI-2 {app.heli['curSeg']+1}/3", barX, barY - 20, size=13, fill=rgb(220,220,220), bold=True)
    drawLabel("ORANGE = SLIVER PATH // YELLOW = PARKOUR", barX, barY + 18, size=10, fill=rgb(180,180,170))

    for i in range(3):
        hx_ = 22 + i*22 + shakeX
        hy_ = 22 + shakeY
        col = rgb(235,235,230) if i < p['hp'] else rgb(60,60,60)
        drawCircle(hx_, hy_, 8, fill=col, border=rgb(20,20,20), borderWidth=1)
        if i < p['hp']:
            drawLabel("♥", hx_, hy_+1, size=10, fill=rgb(180,40,40), bold=True)

    if app.messageTimer>0:
        alpha = 90 if app.messageTimer>20 else int(app.messageTimer*4.5)
        drawRect(235+shakeX, 650+shakeY, 580, 28, fill=rgb(20,20,18), opacity=alpha)
        drawLabel(app.message, 525+shakeX, 664+shakeY, size=12, fill=rgb(255,209,0), bold=True)

    drawLabel("[A/D] MOVE  [W/SPACE] JUMP  [J HOLD] SLIVER  [K] PARRY  [R] RESTART", 525+shakeX, 688+shakeY, size=9, fill=rgb(200,200,190), opacity=70)

    if app.gameState == 'intro':
        # fixed: was 525,350 which is left,top not center — caused bottom-right black box
        drawRect(0, 0, 1050, 700, fill=rgb(15,15,14), opacity=88)
        drawRect(165, 140, 720, 420, fill=rgb(32,32,30), border=rgb(140,138,132), borderWidth=2)
        drawLabel("MOTORSLIVER: HELI-2 // PARKOUR AS COMBAT", 525, 200, size=22, fill=rgb(235,235,230), bold=True)
        drawLabel("Boss as climbable moving level — sliver it apart", 525, 226, size=12, fill=rgb(180,180,170))
        drawCircle(345, 320, 24, fill=rgb(245,245,250), border=rgb(140,138,132), borderWidth=1)
        drawCircle(348, 318, 6, fill=rgb(90,180,255))
        drawRect(445, 280, 420, 88, fill=rgb(45,45,42), border=rgb(255,209,0), borderWidth=1)
        drawLabel("Orbie: 'Heli-2's buzzing the obelisk. Parry orange saw [K],'", 665, 292, size=11, fill=rgb(220,220,210))
        drawLabel("board it, then sliver orange paths [J]. After first sliver", 665, 308, size=11, fill=rgb(220,220,210))
        drawLabel("it stops throwing saws — use beams!'", 665, 324, size=11, fill=rgb(220,220,210))
        drawLabel("Orbie: 'Ready to sliver?'", 665, 344, size=11, fill=rgb(90,180,255), bold=True)
        c1Col = rgb(255,209,0) if app.t%40<20 else rgb(235,235,230)
        drawRect(445, 396, 200, 36, fill=rgb(60,60,56), border=c1Col, borderWidth=2)
        drawLabel("[1] Let's sliver.", 545, 414, size=12, fill=c1Col, bold=True)
        drawRect(685, 396, 200, 36, fill=rgb(60,60,56), border=rgb(175,172,165), borderWidth=1)
        drawLabel("[2] One more minute...", 785, 414, size=11, fill=rgb(180,180,170))
        drawLabel("YELLOW=go, ORANGE=sliver | Mirror's Edge + Colossus in 2D", 525, 452, size=10, fill=rgb(255,209,0), opacity=80)
        drawLabel("Press 1 or 2 to start Motorsliver", 525, 502, size=13, fill=rgb(235,235,230), bold=True)
        drawStar(825, 230, 8, 5, fill=rgb(255,209,0), opacity=60)

    elif app.gameState == 'defeat':
        # shake the world for juice, but keep instructions locked and readable
        drawRect(-20+shakeX, -20+shakeY, 1090, 740, fill=rgb(20,10,10), opacity=78)
        drawLabel("SLIVERED", 525, 320, size=44, fill=rgb(255,160,50), bold=True)
        drawLabel("High lethality - timing over trading.", 525, 358, size=13, fill=rgb(200,200,200))
        drawLabel(f"Segments: {sum(app.heli['segments'])}/3 // SPACE or R to retry", 525, 386, size=12, fill=rgb(255,209,0))

    elif app.gameState == 'victory':
        drawRect(-20+shakeX, -20+shakeY, 1090, 740, fill=rgb(40,38,30), opacity= 60 + min(30, app.victoryT))
        drawLabel("MOTORSLIVER // HELI-2 SLIVERED", 525, 310, size=32, fill=rgb(255,209,0), bold=True)
        drawLabel("Spatial route solved under pressure.", 525, 344, size=14, fill=rgb(235,235,230))
        drawLabel("Cargo lifter crumbles to sand.", 525, 368, size=12, fill=rgb(200,200,190))
        drawLabel("Press R to replay Motorsliver", 525, 404, size=11, fill=rgb(180,180,170))

def main():
    runApp(1050, 700)

main()
