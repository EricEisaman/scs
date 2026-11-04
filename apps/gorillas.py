
from scs import *
import math
import random

# ============================================================
# GORILLAS - SCS 1050x700 - No Wind - Lazy Deferred Destruction
# Turn-based logic faithful to QBasic original
# MIN FONT 13
# ============================================================

WIDTH = 1050
HEIGHT = 700
GROUND_Y = 620
SUN_X = WIDTH // 2
SUN_Y = 70
SUN_R = 26

GRAVITY = 0.185
BANANA_SCALE = 0.38
BLAST_R = 34

BUILDING_COLORS = [
    rgb(62,68,86), rgb(72,76,92), rgb(80,86,105),
    rgb(58,64,84), rgb(85,82,98), rgb(70,72,90),
]
WIN_ON = rgb(255,232,130)
WIN_OFF = rgb(32,36,50)

class Hole:
    def __init__(self,x,y,r): self.x=x; self.y=y; self.r=r

class Frag:
    def __init__(self,x,y,w,h,vx,vy,col):
        self.x=x; self.y=y; self.w=w; self.h=h
        self.vx=vx; self.vy=vy
        self.rot=random.uniform(0,360)
        self.rSpeed=random.uniform(-10,10)
        self.col=col

class Building:
    def __init__(self,x,y,w,h,col,bid):
        self.x=x; self.y=y; self.w=w; self.h=h; self.col=col
        self.windows=[]; self.holes=[]; self.frags=[]
        self.static=True; self.id=bid
        self._makeWindows()
    def _makeWindows(self):
        sx=self.x+8; ex=self.x+self.w-10
        sy=self.y+12; ey=self.y+self.h-10
        y=sy
        while y < ey:
            x=sx
            while x < ex:
                self.windows.append((x,y,6,9, random.random()>0.32))
                x+=14
            y+=18
    def solidAt(self,px,py):
        if px<self.x or px>self.x+self.w or py<self.y or py>self.y+self.h:
            return False
        for h in self.holes:
            dx=px-h.x; dy=py-h.y
            if dx*dx+dy*dy <= h.r*h.r:
                return False
        return True
    def damage(self,hx,hy,r=BLAST_R):
        self.static=False
        self.holes.append(Hole(hx,hy,r))
        for _ in range(12):
            ang=random.uniform(0,2*math.pi)
            dist=random.uniform(2,r*0.95)
            fx=hx+math.cos(ang)*dist
            fy=hy+math.sin(ang)*dist
            if fx<self.x-8 or fx>self.x+self.w+8: continue
            if fy<self.y-8 or fy>self.y+self.h+8: continue
            fw=random.randint(4,9); fh=random.randint(4,9)
            vx=math.cos(ang)*random.uniform(1.2,4.5)
            vy=math.sin(ang)*random.uniform(1.2,4.5)-random.uniform(0.5,2.5)
            c=random.choice([rgb(70,72,85),rgb(85,86,95),rgb(95,92,105),rgb(60,62,75)])
            self.frags.append(Frag(fx,fy,fw,fh,vx,vy,c))
        if len(self.holes)>12:
            self.holes=self.holes[-10:]
    def updateFrags(self):
        alive=[]
        for f in self.frags:
            f.vy+=GRAVITY*0.6; f.x+=f.vx; f.y+=f.vy; f.vx*=0.99; f.rot+=f.rSpeed
            if f.y+f.h>=GROUND_Y:
                f.y=GROUND_Y-f.h; f.vy*=-0.28; f.vx*=0.72
                if abs(f.vy)<0.7: f.vy=0; f.rSpeed*=0.7
            if f.y<HEIGHT+60 and -60<f.x<WIDTH+60:
                alive.append(f)
        self.frags=alive
    def draw(self,app):
        drawRect(self.x,self.y,self.w,self.h,fill=self.col)
        for wx,wy,ww,wh,on in self.windows:
            cx=wx+ww/2; cy=wy+wh/2; inside=False
            for h in self.holes:
                if (cx-h.x)**2+(cy-h.y)**2 < (h.r-1)**2: inside=True; break
            if inside: continue
            drawRect(wx,wy,ww,wh,fill=WIN_ON if on else WIN_OFF)
        for h in self.holes:
            drawCircle(h.x,h.y,h.r,fill=app.skyMid)
            drawCircle(h.x,h.y,h.r,fill=None,border=rgb(38,42,56),borderWidth=2)
        for f in self.frags:
            drawRect(f.x+f.w/2,f.y+f.h/2,f.w,f.h,fill=f.col,align='center',rotateAngle=f.rot)

def makeCity(app):
    buildings=[]; x=2; slope=random.randint(1,6)
    if slope==1: newH=35; inc=10
    elif slope==2: newH=160; inc=-10
    else: newH=40; inc=11
    rndH=135; defW=54; bid=0
    while x<WIDTH-50 and bid<20:
        if slope==1: newH+=inc
        elif slope==2: newH+=inc
        elif slope in (3,4,5):
            newH+= 7 if x<=WIDTH//2 else -7
        else:
            newH+= -7 if x<=WIDTH//2 else 7
        bw=random.randint(defW-10,defW+20)
        if x+bw>WIDTH-2: bw=WIDTH-x-2
        if bw<28: break
        bh=int(newH+random.randint(20,rndH))
        bh=max(32,min(bh,GROUND_Y-(SUN_Y+SUN_R+60)))
        by=GROUND_Y-bh
        buildings.append(Building(x,by,bw,bh,random.choice(BUILDING_COLORS),bid))
        x+=bw+6; bid+=1
    if len(buildings)<8:
        while x<WIDTH-40 and len(buildings)<12:
            bw=60; bh=80+random.randint(0,90); by=GROUND_Y-bh
            buildings.append(Building(x,by,bw,bh,random.choice(BUILDING_COLORS),len(buildings)))
            x+=bw+6
    return buildings

def placeGorillas(buildings):
    if len(buildings)<4:
        left=buildings[0]; right=buildings[-1]
    else:
        left=buildings[random.randint(1,2)]
        right=buildings[len(buildings)-random.randint(2,3)]
    gW=28; gH=32
    g1x=left.x+left.w//2-gW//2; g1y=left.y-gH+2
    g2x=right.x+right.w//2-gW//2; g2y=right.y-gH+2
    return (g1x,g1y,left),(g2x,g2y,right)

def drawGorilla(x,y,arm='down',facing=1,highlight=False):
    if highlight:
        drawRect(x-4,y-4,36,42,fill=None,border=rgb(255,222,90),borderWidth=2,roundness=8,dashes=(5,4))
    drawOval(x+14,y+34,28,7,fill=rgb(20,20,20),opacity=35)
    drawRect(x+4,y+22,8,12,fill=rgb(42,26,16),roundness=3)
    drawRect(x+16,y+22,8,12,fill=rgb(42,26,16),roundness=3)
    drawRect(x+2,y+10,24,16,fill=rgb(72,48,28),border=rgb(32,20,12),borderWidth=1,roundness=5)
    drawCircle(x+10,y+16,6,fill=rgb(92,68,42)); drawCircle(x+18,y+16,6,fill=rgb(92,68,42))
    drawRect(x+5,y+0,18,13,fill=rgb(88,62,42),border=rgb(32,20,12),borderWidth=1,roundness=4)
    drawCircle(x+10,y+5,2,fill=rgb(255,255,255)); drawCircle(x+18,y+5,2,fill=rgb(255,255,255))
    drawCircle(x+10,y+5.5,1,fill=rgb(0,0,0)); drawCircle(x+18,y+5.5,1,fill=rgb(0,0,0))
    drawLine(x+7,y+3,x+12,y+3,fill=rgb(0,0,0),lineWidth=1)
    drawLine(x+16,y+3,x+21,y+3,fill=rgb(0,0,0),lineWidth=1)
    drawCircle(x+13,y+9,1,fill=rgb(0,0,0)); drawCircle(x+15,y+9,1,fill=rgb(0,0,0))
    if arm=='down':
        drawLine(x+2,y+14,x-2,y+24,fill=rgb(72,48,28),lineWidth=6)
        drawLine(x+26,y+14,x+30,y+24,fill=rgb(72,48,28),lineWidth=6)
    elif arm=='rightUp':
        if facing==1:
            drawLine(x+2,y+14,x-2,y+24,fill=rgb(72,48,28),lineWidth=6)
            drawLine(x+26,y+14,x+34,y+2,fill=rgb(72,48,28),lineWidth=6)
            drawCircle(x+35,y+1,4,fill=rgb(88,62,42))
        else:
            drawLine(x+26,y+14,x+30,y+24,fill=rgb(72,48,28),lineWidth=6)
            drawLine(x+2,y+14,x-6,y+2,fill=rgb(72,48,28),lineWidth=6)
            drawCircle(x-7,y+1,4,fill=rgb(88,62,42))
    elif arm=='leftUp':
        if facing==1:
            drawLine(x+26,y+14,x+30,y+24,fill=rgb(72,48,28),lineWidth=6)
            drawLine(x+2,y+14,x-6,y+2,fill=rgb(72,48,28),lineWidth=6)
            drawCircle(x-7,y+1,4,fill=rgb(88,62,42))
        else:
            drawLine(x+2,y+14,x-2,y+24,fill=rgb(72,48,28),lineWidth=6)
            drawLine(x+26,y+14,x+34,y+2,fill=rgb(72,48,28),lineWidth=6)
            drawCircle(x+35,y+1,4,fill=rgb(88,62,42))
    elif arm=='victory':
        drawLine(x+2,y+14,x-5,y+0,fill=rgb(72,48,28),lineWidth=6)
        drawLine(x+26,y+14,x+33,y+0,fill=rgb(72,48,28),lineWidth=6)
        drawCircle(x-6,y-1,4,fill=rgb(88,62,42)); drawCircle(x+34,y-1,4,fill=rgb(88,62,42))

def drawBanana(x,y,rot):
    r=math.radians(rot); L=14; W=6; pts=[]
    for i in range(7):
        t=i/6.0; along=(t-0.5)*L; curve=math.sin(t*math.pi)*W*0.75
        px=along*math.cos(r)-curve*math.sin(r)
        py=along*math.sin(r)+curve*math.cos(r)
        pts.append((x+px,y+py))
    for i in range(len(pts)-1):
        drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=rgb(255,230,30),lineWidth=W)
    drawCircle(pts[0][0],pts[0][1],2.5,fill=rgb(90,55,15))
    drawCircle(pts[-1][0],pts[-1][1],2.5,fill=rgb(90,55,15))
    drawCircle(x,y,1.5,fill=rgb(255,255,180))

def drawSun(x,y,state='happy',t=0):
    ray=21 if state!='shocked' else 24+math.sin(t*0.4)*3
    col=rgb(255,222,85) if state!='shocked' else rgb(255,205,85)
    for a in range(0,360,30):
        rad=math.radians(a)
        drawLine(x,y,x+math.cos(rad)*ray,y+math.sin(rad)*ray,fill=rgb(255,210,60),lineWidth=3)
    drawCircle(x,y,SUN_R,fill=col,border=rgb(255,180,0),borderWidth=2)
    drawCircle(x-8,y-4,4,fill=rgb(0,0,0)); drawCircle(x+8,y-4,4,fill=rgb(0,0,0))
    drawCircle(x-7,y-5,1.5,fill=rgb(255,255,255)); drawCircle(x+9,y-5,1.5,fill=rgb(255,255,255))
    if state=='shocked':
        drawCircle(x,y+8,7,fill=rgb(0,0,0)); drawCircle(x,y+8,3.5,fill=rgb(255,140,140))
    else:
        drawArc(x,y+3,14,9,20,140,fill=None,border=rgb(0,0,0),borderWidth=2)
        drawOval(x-13,y+6,6,3,fill=rgb(255,120,120),opacity=55)
        drawOval(x+13,y+6,6,3,fill=rgb(255,120,120),opacity=55)

# ===================== GAME LOGIC - TURN BASED =====================
# Faithful to QBasic:
# J = 1 before rounds, each shot J = 1-J, Tosser = J+1
# So starting player alternates each round.
# On hit: if self-hit, opponent gets point and does victory dance.
# On miss (building/ground/offscreen): turn switches.
# Sun hit: does NOT end turn, banana continues.

def onAppStart(app):
    app.width=WIDTH; app.height=HEIGHT; app.stepsPerSecond=60
    app.skyTop=rgb(98,162,220); app.skyMid=rgb(155,205,240); app.skyBottom=rgb(190,228,252)
    app.buildings=[]; app.gorillaPos=[]
    app.scores=[0,0]; app.playerNames=["Player 1","Player 2"]
    app.J=1  # QBasic J logic
    app.currentPlayer=0  # will be set by J logic
    app.angle=[45,135]; app.power=[18,18]
    app.dragging=False; app.dragStart=None; app.dragCurrent=None
    app.banana=None; app.state='aiming'
    app.explosion=None; app.particles=[]
    app.sunState='happy'; app.sunTimer=0
    app.victoryTimer=0; app.winner=None; app.roundLoser=None
    app.message=""; app.messageTimer=0
    app.gamesToWin=3; app.showTraj=True; app.gravity=GRAVITY
    app.sunHitThisShot=False
    startRound(app)

def startRound(app):
    # QBasic: MakeCityScape + PlaceGorillas + DoSun SUNHAPPY each round
    app.buildings=makeCity(app)
    g1,g2=placeGorillas(app.buildings)
    app.gorillaPos=[g1,g2]
    app.banana=None; app.explosion=None; app.particles=[]
    app.state='aiming'
    app.sunState='happy'; app.sunTimer=0; app.sunHitThisShot=False
    app.victoryTimer=0; app.winner=None; app.roundLoser=None
    app.dragging=False
    # QBasic turn logic: J = 1-J, Tosser = J+1
    app.J = 1 - app.J
    app.currentPlayer = app.J  # J=0 => player1, J=1 => player2 - matches Tosser=J+1
    # reset angles for new round but keep power
    app.angle=[45,135]
    app.message=f"Round {sum(app.scores)+1} - {app.playerNames[app.currentPlayer]} to throw"
    app.messageTimer=140

def fire(app):
    if app.state!='aiming': return
    idx=app.currentPlayer
    gx,gy,bld=app.gorillaPos[idx]
    sx=gx+28 if idx==0 else gx-4
    sy=gy+2
    ang=math.radians(app.angle[idx])
    p=app.power[idx]
    vx=math.cos(ang)*p*BANANA_SCALE
    vy=-math.sin(ang)*p*BANANA_SCALE
    app.banana={'x':sx,'y':sy,'vx':vx,'vy':vy,'rot':0,'trail':[]}
    app.state='flying'
    app.sunHitThisShot=False
    app.message=""

def makeExplosion(app,x,y,gorilla=False,sun=False):
    maxR=BLAST_R + (14 if gorilla else 0)
    app.explosion={'x':x,'y':y,'r':5,'maxR':maxR,'growing':True}
    cnt=30 if gorilla else 18
    for _ in range(cnt):
        ang=random.uniform(0,2*math.pi); sp=random.uniform(1.5,6.5)
        app.particles.append({'x':x,'y':y,'vx':math.cos(ang)*sp,'vy':math.sin(ang)*sp-1,'r':random.uniform(2,4.5),'life':1.0,'col':random.choice([rgb(255,120,20),rgb(255,210,60),rgb(255,80,20),rgb(210,210,210)])})
    if sun:
        app.sunState='shocked'; app.sunTimer=60

def gorillaHit(app,bx,by):
    for i,(gx,gy,bld) in enumerate(app.gorillaPos):
        if gx-5 <= bx <= gx+33 and gy-5 <= by <= gy+37:
            return i
    return -1

def onStep(app):
    if app.sunTimer>0:
        app.sunTimer-=1
        if app.sunTimer==0:
            app.sunState='happy'

    for b in app.buildings:
        if not b.static and len(b.frags)>0:
            b.updateFrags()

    if app.messageTimer>0: app.messageTimer-=1

    if app.state=='flying' and app.banana:
        b=app.banana
        b['vy']+=app.gravity; b['x']+=b['vx']; b['y']+=b['vy']
        b['rot']+=16+abs(b['vx'])*1.8
        b['trail'].append((b['x'],b['y']))
        if len(b['trail'])>16: b['trail'].pop(0)
        x,y=b['x'],b['y']

        # OFFSCREEN - QBasic: OnScreen=FALSE, miss, turn switches
        if x<-30 or x>WIDTH+30 or y>GROUND_Y+30:
            # miss
            app.banana=None
            app.state='aiming'
            # turn switch per QBasic: J=1-J done at top of loop, here we do it for next throw
            app.J = 1 - app.J
            app.currentPlayer = app.J
            if app.sunHitThisShot:
                # reset sun happy after shot as QBasic does: IF SunHit THEN DoSun SUNHAPPY
                app.sunState='happy'; app.sunTimer=0
                app.sunHitThisShot=False
            app.message=f"Miss! {app.playerNames[app.currentPlayer]}'s turn"
            app.messageTimer=100
            return

        # SUN - QBasic: pointval==SUNATTR and y<SunHt => SunHit=TRUE, ShotInSun=TRUE, Impact=FALSE
        # So banana passes through, only visual shock
        dx=x-SUN_X; dy=y-SUN_Y
        if dx*dx+dy*dy < (SUN_R+8)**2 and y < SUN_Y+SUN_R+18:
            if not app.sunHitThisShot:
                app.sunState='shocked'; app.sunTimer=90
                app.sunHitThisShot=True
                # small sparkle but don't explode
                for _ in range(6):
                    ang=random.uniform(0,2*math.pi)
                    app.particles.append({'x':x,'y':y,'vx':math.cos(ang)*2,'vy':math.sin(ang)*2,'r':2,'life':1.0,'col':rgb(255,220,90)})
            # DO NOT return - continue flight

        # GORILLA - direct hit
        hg=gorillaHit(app,x,y)
        if hg!=-1:
            # QBasic: ExplodeGorilla, returns PlayerHit (1 left side, 2 right side based on x)
            # But we use actual gorilla index hit
            # Determine self-hit
            isSelf = (hg == app.currentPlayer)
            if isSelf:
                # self-hit: opponent gets point, opponent dances (QBasic swaps PlayerNum for dance)
                app.winner = 1 - app.currentPlayer
                app.roundLoser = app.currentPlayer
                app.scores[app.winner]+=1
            else:
                app.winner = app.currentPlayer
                app.roundLoser = hg
                app.scores[app.winner]+=1

            makeExplosion(app,x,y,gorilla=True)
            app.banana=None
            app.state='exploding'
            # reset sun after shot if it was hit earlier in this shot
            # QBasic does IF SunHit THEN DoSun SUNHAPPY after each DoShot
            return

        # BUILDING - hit
        for building in app.buildings:
            if building.solidAt(x,y):
                building.damage(x,y,BLAST_R)
                makeExplosion(app,x,y)
                app.banana=None
                app.state='exploding'
                app.winner=None  # no winner, just miss
                return

    elif app.state=='exploding':
        if app.explosion:
            e=app.explosion
            if e['growing']:
                e['r']+=3.4
                if e['r']>=e['maxR']: e['growing']=False
            else:
                e['r']-=2.8
                if e['r']<=0:
                    app.explosion=None
                    if app.winner is not None:
                        # hit occurred - go to victory dance
                        app.state='dancing'
                        app.victoryTimer=100
                        # message already set via scores, add dance message
                        loserName = app.playerNames[app.roundLoser] if app.roundLoser is not None else ""
                        if app.roundLoser == app.currentPlayer:
                            app.message=f"{app.playerNames[app.roundLoser]} hit himself! {app.playerNames[app.winner]} wins round!"
                        else:
                            app.message=f"{app.playerNames[app.winner]} hits {app.playerNames[app.roundLoser]}!"
                        app.messageTimer=160
                        # sun reset after hit shot
                        if app.sunHitThisShot:
                            app.sunState='happy'; app.sunHitThisShot=False
                    else:
                        # building hit miss - turn switches
                        app.state='aiming'
                        app.J = 1 - app.J
                        app.currentPlayer = app.J
                        if app.sunHitThisShot:
                            app.sunState='happy'; app.sunHitThisShot=False
                        app.message=f"Hit building! {app.playerNames[app.currentPlayer]}'s turn"
                        app.messageTimer=100
        np=[]
        for p in app.particles:
            p['x']+=p['vx']; p['y']+=p['vy']; p['vy']+=0.18; p['vx']*=0.99; p['life']-=0.028
            if p['life']>0: np.append(p)
        app.particles=np
        if app.explosion is None and len(app.particles)==0 and app.state=='exploding' and app.winner is None:
            # safety fallback
            app.state='aiming'

    elif app.state=='dancing':
        app.victoryTimer-=1
        if app.victoryTimer<=0:
            if max(app.scores)>=app.gamesToWin:
                app.state='gameOver'
            else:
                # next round - QBasic J logic already handled? We already flipped J? No, for next round we need to flip again in startRound
                # Our startRound does J=1-J, so we should NOT flip here extra, just startRound
                # But currentPlayer is still the thrower who just won/lost, startRound will flip to next starter
                startRound(app)

def updateAim(app,mx,my):
    idx=app.currentPlayer
    gx,gy,bld=app.gorillaPos[idx]
    gcx=gx+14; gcy=gy+12
    dx=mx-gcx; dy=gcy-my
    ang=math.degrees(math.atan2(dy,dx))
    if ang<0: ang+=360
    if idx==0:
        if ang>180: ang=180-(ang-180)
        ang=max(5,min(88,ang))
    else:
        if ang<90: ang=180-ang
        ang=max(92,min(175,ang))
    dist=math.hypot(mx-gcx,my-gcy)
    power=max(3,min(32,dist/12.0))
    app.angle[idx]=ang; app.power[idx]=power

def onMousePress(app,mx,my):
    if app.state=='gameOver':
        app.scores=[0,0]; app.J=1; startRound(app); return
    if app.state!='aiming': return
    idx=app.currentPlayer; gx,gy,bld=app.gorillaPos[idx]
    if math.hypot(gx+14-mx,gy+12-my)<90:
        app.dragging=True; app.dragStart=(gx+14,gy+12); app.dragCurrent=(mx,my); updateAim(app,mx,my)

def onMouseDrag(app,mx,my):
    if not app.dragging or app.state!='aiming': return
    app.dragCurrent=(mx,my); updateAim(app,mx,my)

def onMouseRelease(app,mx,my):
    if not app.dragging: return
    app.dragging=False; app.dragCurrent=(mx,my); updateAim(app,mx,my)
    if app.power[app.currentPlayer]>=4: fire(app)

def onKeyPress(app,key):
    if app.state=='gameOver':
        if key.lower()=='r': app.scores=[0,0]; app.J=1; startRound(app)
        return
    if app.state!='aiming':
        if key.lower()=='n': startRound(app)
        return
    idx=app.currentPlayer
    if key=='left' or key.lower()=='a':
        app.angle[idx]=max(5 if idx==0 else 92, app.angle[idx]-2)
    elif key=='right' or key.lower()=='d':
        app.angle[idx]=min(88 if idx==0 else 175, app.angle[idx]+2)
    elif key=='up' or key.lower()=='w':
        app.power[idx]=min(32, app.power[idx]+0.8)
    elif key=='down' or key.lower()=='s':
        app.power[idx]=max(3, app.power[idx]-0.8)
    elif key=='space': fire(app)
    elif key.lower()=='n': startRound(app)
    elif key.lower()=='t': app.showTraj=not app.showTraj

def drawTraj(app,idx):
    if app.state!='aiming' or not app.showTraj: return
    gx,gy,bld=app.gorillaPos[idx]
    sx=gx+28 if idx==0 else gx-4; sy=gy+2
    ang=math.radians(app.angle[idx]); p=app.power[idx]
    vx=math.cos(ang)*p*BANANA_SCALE; vy=-math.sin(ang)*p*BANANA_SCALE
    x,y=sx,sy; sVx,sVy=vx,vy; dots=[]
    for i in range(90):
        x+=sVx; y+=sVy; sVy+=app.gravity
        if i%3==0: dots.append((x,y))
        if y>GROUND_Y or x<0 or x>WIDTH: break
        hit=False
        for bld in app.buildings:
            if bld.solidAt(x,y): hit=True; break
        if hit: break
        og=1-idx; ogx,ogy,ob=app.gorillaPos[og]
        if ogx-4<=x<=ogx+33 and ogy-4<=y<=ogy+37: break
    for i,(dx,dy) in enumerate(dots):
        c=rgb(255,255,255) if i%2==0 else rgb(255,230,70)
        drawCircle(dx,dy,3 if i==0 else 2,fill=c,opacity=70-i)

def redrawAll(app):
    for i in range(0,GROUND_Y,4):
        t=i/GROUND_Y; r=int(98+(190-98)*t); g=int(162+(228-162)*t); b=int(220+(252-220)*t)
        drawRect(0,i,WIDTH,4,fill=rgb(r,g,b))
    drawSun(SUN_X,SUN_Y,app.sunState,app.sunTimer)
    for b in app.buildings: b.draw(app)
    drawRect(0,GROUND_Y,WIDTH,HEIGHT-GROUND_Y,fill=rgb(46,41,36))
    drawRect(0,GROUND_Y,WIDTH,5,fill=rgb(72,72,72))
    for i,(gx,gy,bld) in enumerate(app.gorillaPos):
        isCur=(i==app.currentPlayer and app.state=='aiming')
        arm='down'
        if app.state=='flying' and app.banana and i==app.currentPlayer:
            arm='rightUp' if i==0 else 'leftUp'
        elif app.state=='dancing':
            if app.winner==i:
                arm='victory' if (app.victoryTimer//10)%2==0 else 'rightUp'
            else:
                arm='down'
        drawGorilla(gx,gy,arm=arm,facing=1 if i==0 else -1,highlight=isCur)
    if app.state=='aiming': drawTraj(app,app.currentPlayer)
    if app.banana:
        for j,(tx,ty) in enumerate(app.banana['trail']):
            drawCircle(tx,ty,2.5,fill=rgb(255,230,30),opacity=45+j*3)
        drawBanana(app.banana['x'],app.banana['y'],app.banana['rot'])
    if app.explosion:
        e=app.explosion
        drawCircle(e['x'],e['y'],e['r']+7,fill=rgb(255,200,30),opacity=35)
        drawCircle(e['x'],e['y'],e['r'],fill=rgb(255,120,20))
        drawCircle(e['x'],e['y'],e['r']*0.55,fill=rgb(255,220,90))
    for p in app.particles:
        drawCircle(p['x'],p['y'],p['r']*p['life'],fill=p['col'])

    drawRect(0,0,WIDTH,90,fill=rgb(0,0,0),opacity=38)
    drawLabel(f"{app.playerNames[0]}: {app.scores[0]}",18,18,fill=rgb(255,255,255),size=18,bold=True,align='left')
    drawLabel(f"{app.playerNames[1]}: {app.scores[1]}",WIDTH-18,18,fill=rgb(255,255,255),size=18,bold=True,align='right')
    if app.state in ('aiming','flying','exploding','dancing'):
        drawLabel(f"TURN: {app.playerNames[app.currentPlayer].upper()}",WIDTH//2,20,fill=rgb(255,222,90),size=20,bold=True,align='center')
    if app.state=='aiming':
        idx=app.currentPlayer
        drawLabel(f"Angle: {app.angle[idx]:.1f}°",18,46,fill=rgb(210,230,255),size=15,align='left')
        drawLabel(f"Power: {app.power[idx]:.1f}",18,66,fill=rgb(210,230,255),size=15,align='left')
        bw=150; bh=9; pct=(app.power[idx]-3)/29.0
        drawRect(130,62,bw,bh,fill=rgb(50,50,50),border=rgb(130,130,130),borderWidth=1,roundness=4)
        drawRect(130,62,bw*pct,bh,fill=rgb(90,210,90),roundness=4)
        drawLabel("DRAG to aim, RELEASE to fire | A/D angle W/S power SPACE fire T traj N new city",WIDTH//2,74,fill=rgb(185,195,205),size=13,align='center')
    if app.dragging and app.dragStart and app.dragCurrent:
        sx,sy=app.dragStart; cx,cy=app.dragCurrent
        drawLine(sx,sy,cx,cy,fill=rgb(255,255,255),lineWidth=2,dashes=(6,4),opacity=60)
        drawCircle(cx,cy,6,fill=rgb(255,255,255),border=rgb(0,0,0),borderWidth=1)
    if app.message and app.messageTimer>0:
        tw=len(app.message)*8+28
        drawRect(WIDTH//2,HEIGHT//2-115,tw,34,fill=rgb(0,0,0),opacity=55,roundness=17,align='center')
        drawLabel(app.message,WIDTH//2,HEIGHT//2-115,fill=rgb(255,255,200),size=16,bold=True,align='center')
    if app.state=='gameOver':
        drawRect(0,0,WIDTH,HEIGHT,fill=rgb(0,0,0),opacity=62)
        win=0 if app.scores[0]>app.scores[1] else 1
        drawLabel("GAME OVER",WIDTH//2,HEIGHT//2-80,fill=rgb(255,222,90),size=44,bold=True,align='center')
        drawLabel(f"{app.playerNames[win]} WINS THE MATCH!",WIDTH//2,HEIGHT//2-18,fill=rgb(255,255,255),size=24,bold=True,align='center')
        drawLabel(f"Final {app.scores[0]} - {app.scores[1]}",WIDTH//2,HEIGHT//2+22,fill=rgb(210,210,210),size=18,align='center')
        drawLabel("Press R or Click to play again",WIDTH//2,HEIGHT//2+62,fill=rgb(160,210,255),size=16,align='center')
        drawGorilla(WIDTH//2-14,HEIGHT//2+88,arm='victory',facing=1)
    staticC=sum(1 for b in app.buildings if b.static)
    damC=len(app.buildings)-staticC
    fragC=sum(len(b.frags) for b in app.buildings)
    drawLabel(f"Buildings {len(app.buildings)} | Static {staticC} | Damaged {damC} | Frags {fragC} | Turn logic: J={app.J} Tosser={app.currentPlayer+1} | No Wind",WIDTH//2,HEIGHT-12,fill=rgb(185,185,185),size=13,align='center')
