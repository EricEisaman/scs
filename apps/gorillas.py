from scs import *
import math
import random
import importlib

WIDTH = 1050
HEIGHT = 700
BOTTOM_LINE = 685
SUN_X = WIDTH // 2
SUN_Y = int(25 * (HEIGHT / 350.0))

BACK_COLOR = rgb(0, 0, 170)
BLACK_BG = rgb(0,0,0)
BUILDING_COLORS = [rgb(170,0,0), rgb(128,128,128), rgb(170,85,0), rgb(0,128,128)]
WINDOW_ON = rgb(255,255,85)
WINDOW_OFF = rgb(64,64,74)
GORILLA_COLOR = rgb(255,165,90)
SUN_COLOR = rgb(255,255,0)

GRAVITY = 0.185
BLAST_R = 36

# ---- 8bit audio integration - built ON TOP of proc_audio.py ----
try:
    eightbit = importlib.import_module('extensions.8bit')
    EightBitAudioEngine = eightbit.EightBitAudioEngine
    HAS_8BIT = True
except Exception as e:
    print(f"8bit load failed: {e}")
    HAS_8BIT = False
    EightBitAudioEngine = None
    eightbit = None

def play_sound(app, name, on_complete=None):
    """Event-driven sound - currentTime scheduling + onended, no timeouts"""
    if not hasattr(app, 'engine') or app.engine is None:
        return
    try:
        app.engine.resume()
    except:
        pass
    try:
        # resume player ctx if present
        if hasattr(app, 'player') and app.player:
            try:
                app.player.resume()
            except:
                pass
    except:
        pass
    try:
        app.engine.play(name, on_complete=on_complete)
    except Exception as e:
        print(f"play {name} failed {e}")

def Scl(n):
    return n * (HEIGHT / 350.0)

class Hole:
    def __init__(self,x,y,r): self.x=x; self.y=y; self.r=r
class Frag:
    def __init__(self,x,y,w,h,vx,vy,col):
        self.x=x; self.y=y; self.w=w; self.h=h; self.vx=vx; self.vy=vy
        self.rot=random.uniform(0,360); self.rSpeed=random.uniform(-8,8); self.col=col

class Building:
    def __init__(self,x,y,w,h,col):
        self.x=x; self.y=y; self.w=w; self.h=h; self.col=col
        self.windows=[]; self.holes=[]; self.frags=[]; self.static=True
        self._genWindows()
    def _genWindows(self):
        self.windows=[]
        ww=int(5*(WIDTH/640.0))
        wh=int(7*(HEIGHT/350.0))
        x_step=int(10*(WIDTH/640.0))+ww+2
        y_step=int(15*(HEIGHT/350.0))+2
        cx=self.x+ int(5*(WIDTH/640.0))
        while cx+ww < self.x+self.w-4:
            cy=self.y+ int(8*(HEIGHT/350.0))
            while cy+wh < self.y+self.h-8:
                self.windows.append((cx,cy,ww,wh, random.random()>0.32))
                cy+=y_step
            cx+=x_step
    def solidAt(self,px,py):
        if px < self.x or px > self.x+self.w or py < self.y or py > self.y+self.h:
            return False
        for hh in self.holes:
            if (px-hh.x)**2 + (py-hh.y)**2 <= hh.r*hh.r:
                return False
        return True
    def damage(self,hx,hy,r=BLAST_R):
        self.static=False
        self.holes.append(Hole(hx,hy,r))
        for _ in range(18):
            ang=random.uniform(0, 2*math.pi)
            dist=random.uniform(0, r*0.95)
            fx=hx+math.cos(ang)*dist
            fy=hy+math.sin(ang)*dist
            if fx < self.x-8 or fx > self.x+self.w+8 or fy < self.y-8 or fy > self.y+self.h+8:
                continue
            fw=random.randint(4,9); fh=random.randint(4,9)
            vx=math.cos(ang)*random.uniform(1.2,4.5)
            vy=math.sin(ang)*random.uniform(1.2,4.5)-random.uniform(0.5,2.5)
            self.frags.append(Frag(fx,fy,fw,fh,vx,vy,self.col))
        if len(self.holes)>12:
            self.holes=self.holes[-10:]
    def updateFrags(self):
        alive=[]
        for f in self.frags:
            f.vy+=GRAVITY*0.6; f.x+=f.vx; f.y+=f.vy; f.vx*=0.99; f.rot+=f.rSpeed
            if f.y+f.h>=BOTTOM_LINE: f.y=BOTTOM_LINE-f.h; f.vy*=-0.28; f.vx*=0.72
            if -60<f.x<WIDTH+60 and f.y<HEIGHT+60: alive.append(f)
        self.frags=alive
    def draw(self):
        drawRect(self.x, self.y, self.w, self.h, fill=self.col)
        for hh in self.holes:
            drawCircle(hh.x, hh.y, hh.r, fill=BACK_COLOR, border=BACK_COLOR)
        for wx,wy,ww,wh,on in self.windows:
            cx=wx+ww/2; cy=wy+wh/2
            if cx < self.x or cx > self.x+self.w or cy < self.y or cy > self.y+self.h:
                continue
            inside=False
            for hh in self.holes:
                if (cx-hh.x)**2 + (cy-hh.y)**2 < (hh.r+2)**2:
                    inside=True; break
            if inside: continue
            drawRect(wx,wy,ww,wh,fill=WINDOW_ON if on else WINDOW_OFF)
        for f in self.frags:
            drawRect(f.x+f.w/2, f.y+f.h/2, f.w, f.h, fill=f.col, align='center', rotateAngle=f.rot)

def generateCity():
    buildings=[]; x=2; slope=random.randint(1,6)
    if slope==1: newHt=80
    elif slope==2: newHt=200
    elif slope in (3,4,5): newHt=80
    else: newHt=200
    HtInc = int(12 * (HEIGHT/350.0))
    DefBWidth = int(37 * (WIDTH/640.0))
    RandomHeight = int(100 * (HEIGHT/350.0))
    GHeight = int(25 * (HEIGHT/350.0))
    SunHt = int(39 * (HEIGHT/350.0))
    cur=0
    while x < WIDTH - HtInc and cur<16:
        if slope==1: newHt+=HtInc
        elif slope==2: newHt-=HtInc
        elif slope in (3,4,5):
            if x > WIDTH//2: newHt-=2*HtInc
            else: newHt+=2*HtInc
        else:
            if x > WIDTH//2: newHt+=2*HtInc
            else: newHt-=2*HtInc
        if newHt < HtInc: newHt = HtInc
        BWidth = random.randint(1, DefBWidth) + DefBWidth
        if x + BWidth > WIDTH: BWidth = WIDTH - x - 2
        if BWidth < 22: break
        BHeight = random.randint(1, RandomHeight) + newHt
        if BHeight < HtInc: BHeight = HtInc
        if BOTTOM_LINE - BHeight <= SunHt + GHeight + 10:
            BHeight = BOTTOM_LINE - (SunHt + GHeight + 10)
        by = BOTTOM_LINE - BHeight
        buildings.append(Building(x, by, BWidth, BHeight, random.choice(BUILDING_COLORS)))
        x += BWidth + int(2 * (WIDTH/640.0))
        cur+=1
    if buildings:
        center_idx = min(range(len(buildings)), key=lambda i: abs(buildings[i].x + buildings[i].w/2 - WIDTH//2))
        target_top = SUN_Y + Scl(32)
        target_h = BOTTOM_LINE - target_top
        b = buildings[center_idx]
        buildings[center_idx] = Building(b.x, target_top, b.w, target_h, b.col)
        for di in (-2,-1,1,2):
            idx = center_idx+di
            if 0 <= idx < len(buildings):
                min_h = int(target_h * (0.72 if abs(di)==1 else 0.60))
                if buildings[idx].h < min_h:
                    bb = buildings[idx]
                    buildings[idx] = Building(bb.x, BOTTOM_LINE-min_h, bb.w, min_h, bb.col)
    return buildings

def placeGorillas(buildings):
    if len(buildings)<4: left=buildings[0]; right=buildings[-1]
    else: left=buildings[random.randint(1,2)]; right=buildings[len(buildings)-1-random.randint(1,2)]
    return (left.x+left.w//2 - Scl(14), left.y - Scl(30), left), (right.x+right.w//2 - Scl(14), right.y - Scl(30), right)

def drawGorilla(x,y,arm='down',facing=1):
    drawRect(x - Scl(4), y, Scl(6.9), Scl(6), fill=GORILLA_COLOR)
    drawRect(x - Scl(5), y + Scl(2), Scl(9), Scl(2), fill=GORILLA_COLOR)
    drawLine(x - Scl(3), y + Scl(2), x + Scl(2), y + Scl(2), fill=rgb(0,0,0), lineWidth=max(1,int(Scl(1))))
    drawCircle(x - Scl(1.5), y + Scl(4), Scl(0.6), fill=rgb(0,0,0))
    drawCircle(x + Scl(1.5), y + Scl(4), Scl(0.6), fill=rgb(0,0,0))
    drawLine(x - Scl(3), y + Scl(7), x + Scl(2), y + Scl(7), fill=GORILLA_COLOR, lineWidth=max(1,int(Scl(1))))
    drawRect(x - Scl(8), y + Scl(8), Scl(14.9), Scl(6), fill=GORILLA_COLOR)
    drawRect(x - Scl(6), y + Scl(15), Scl(10.9), Scl(5), fill=GORILLA_COLOR)
    for i in range(5):
        drawArc(x + Scl(i), y + Scl(25), Scl(20), Scl(20), 135, 67, fill=None, border=GORILLA_COLOR, borderWidth=int(Scl(1.8)))
        drawArc(x + Scl(-6) + Scl(i-0.1), y + Scl(25), Scl(20), Scl(20), 337, 68, fill=None, border=GORILLA_COLOR, borderWidth=int(Scl(1.8)))
    drawArc(x - Scl(4.9), y + Scl(10), Scl(9.8), Scl(9.8), 270, 90, fill=None, border=rgb(0,0,0), borderWidth=1)
    drawArc(x + Scl(4.9), y + Scl(10), Scl(9.8), Scl(9.8), 180, 90, fill=None, border=rgb(0,0,0), borderWidth=1)
    if arm=='down':
        for i in range(-5,0):
            drawArc(x + Scl(i-0.1), y + Scl(14), Scl(18), Scl(18), 135, 90, fill=None, border=GORILLA_COLOR, borderWidth=int(Scl(2)))
            drawArc(x + Scl(4.9)+ Scl(i), y + Scl(14), Scl(18), Scl(18), 315, 90, fill=None, border=GORILLA_COLOR, borderWidth=int(Scl(2)))
    elif arm=='rightUp':
        for i in range(-5,0):
            drawArc(x + Scl(i-0.1), y + Scl(14), Scl(18), Scl(18), 135, 90, fill=None, border=GORILLA_COLOR, borderWidth=int(Scl(2)))
            drawArc(x + Scl(4.9)+ Scl(i), y + Scl(4), Scl(18), Scl(18), 315, 90, fill=None, border=GORILLA_COLOR, borderWidth=int(Scl(2)))
    elif arm=='leftUp':
        for i in range(-5,0):
            drawArc(x + Scl(i-0.1), y + Scl(4), Scl(18), Scl(18), 135, 90, fill=None, border=GORILLA_COLOR, borderWidth=int(Scl(2)))
            drawArc(x + Scl(4.9)+ Scl(i), y + Scl(14), Scl(18), Scl(18), 315, 90, fill=None, border=GORILLA_COLOR, borderWidth=int(Scl(2)))
    elif arm=='victory':
        for i in range(-5,0):
            drawArc(x + Scl(i-0.1), y + Scl(4), Scl(18), Scl(18), 135, 90, fill=None, border=GORILLA_COLOR, borderWidth=int(Scl(2)))
            drawArc(x + Scl(4.9)+ Scl(i), y + Scl(4), Scl(18), Scl(18), 315, 90, fill=None, border=GORILLA_COLOR, borderWidth=int(Scl(2)))

def drawBanana(x,y,rot):
    w=Scl(6); h=Scl(3)
    if rot%2==0: drawRect(x, y, w, h, fill=rgb(255,255,0), border=rgb(0,0,0), borderWidth=1, roundness=1)
    else: drawRect(x, y, h, w, fill=rgb(255,255,0), border=rgb(0,0,0), borderWidth=1, roundness=1)

def drawSun(x,y,shocked=False):
    drawCircle(x, y, Scl(12), fill=SUN_COLOR, border=SUN_COLOR)
    drawLine(x - Scl(20), y, x + Scl(20), y, fill=SUN_COLOR, lineWidth=1)
    drawLine(x, y - Scl(15), x, y + Scl(15), fill=SUN_COLOR, lineWidth=1)
    drawLine(x - Scl(15), y - Scl(10), x + Scl(15), y + Scl(10), fill=SUN_COLOR, lineWidth=1)
    drawLine(x - Scl(15), y + Scl(10), x + Scl(15), y - Scl(10), fill=SUN_COLOR, lineWidth=1)
    drawLine(x - Scl(8), y - Scl(13), x + Scl(8), y + Scl(13), fill=SUN_COLOR, lineWidth=1)
    drawLine(x - Scl(8), y + Scl(13), x + Scl(8), y - Scl(13), fill=SUN_COLOR, lineWidth=1)
    drawLine(x - Scl(18), y - Scl(5), x + Scl(18), y + Scl(5), fill=SUN_COLOR, lineWidth=1)
    drawLine(x - Scl(18), y + Scl(5), x + Scl(18), y - Scl(5), fill=SUN_COLOR, lineWidth=1)
    if shocked:
        drawCircle(x, y + Scl(5), Scl(2.9), fill=rgb(0,0,0), border=rgb(0,0,0))
        drawCircle(x, y + Scl(5), Scl(1.2), fill=BACK_COLOR, border=BACK_COLOR)
    else:
        drawArc(x, y, Scl(16), Scl(16), 20, 140, fill=None, border=rgb(0,0,0), borderWidth=1)
    drawCircle(x - Scl(3), y - Scl(2), Scl(1), fill=rgb(0,0,0), border=rgb(0,0,0))
    drawCircle(x + Scl(3), y - Scl(2), Scl(1), fill=rgb(0,0,0), border=rgb(0,0,0))

def isReturnKey(key):
    if key is None: return False
    k=str(key).lower()
    return k in ('enter','return','\r','\n','\x0d') or key in (chr(13),chr(10))

def onAppStart(app):
    app.width=WIDTH; app.height=HEIGHT; app.stepsPerSecond=60
    app.buildings=[]; app.gorillaPos=[]; app.scores=[0,0]; app.totalWins=[0,0,0]
    app.banana=None; app.explosion=None; app.particles=[]
    app.sunShocked=False; app.sunTimer=0; app.blink=True; app.blinkTimer=0; app.sparkle=1
    app.background=BLACK_BG
    app.shiftDown=False; app.capsOn=False
    app.state='intro'
    app.inputText=""; app.inputStage=0
    app.playerNames=["Player 1","Player 2"]
    app.numGames=3; app.gravity=GRAVITY
    app.J=1; app.currentPlayer=0
    app.angle=[45,135]; app.power=[18,18]
    app.awaiting='angle'; app.victoryTimer=0; app.winner=None

    # --- Audio engine init (does not touch graphics) ---
    app.engine = None
    app.player = None
    if HAS_8BIT and EightBitAudioEngine:
        try:
            app.engine = EightBitAudioEngine(quality="high")
            app.player = app.engine.player
            print("[gorillas] 8bit engine ready")
        except Exception as e:
            print(f"[gorillas] audio init {e}")

def startNewRound(app):
    app.buildings=generateCity()
    g1,g2=placeGorillas(app.buildings)
    app.gorillaPos=[g1,g2]
    app.banana=None; app.explosion=None; app.particles=[]
    app.sunShocked=False; app.sunTimer=0; app.victoryTimer=0; app.winner=None
    app.J = 1 - app.J; app.currentPlayer=app.J
    app.angle=[45,135]; app.awaiting='angle'; app.inputText=""; app.state='aiming'
    app.background=BACK_COLOR

def fireBanana(app):
    if app.state!='aiming': return
    idx=app.currentPlayer; gx,gy,bld=app.gorillaPos[idx]
    if idx==0:
        sx=gx+Scl(28)
        sy=gy - Scl(6)
    else:
        sx=gx - Scl(10)
        sy=gy - Scl(6)
    ang=math.radians(app.angle[idx]); p=app.power[idx]
    vx=math.cos(ang)*p*0.38; vy=-math.sin(ang)*p*0.38
    app.banana={'x':sx,'y':sy,'vx':vx,'vy':vy,'rot':0,'trail':[],'age':0}
    app.state='flying'
    # SOUND: throw MBo0L32A-L64CL16BL64A+ - ascending throw
    play_sound(app, 'throw')

def createExplosion(app,x,y,gorilla=False):
    maxR=BLAST_R + (14 if gorilla else 0)
    app.explosion={'x':x,'y':y,'r':5,'maxR':maxR,'growing':True}
    for _ in range(30 if gorilla else 18):
        ang=random.uniform(0,2*math.pi); sp=random.uniform(1.5,6.5)
        app.particles.append({'x':x,'y':y,'vx':math.cos(ang)*sp,'vy':math.sin(ang)*sp-1,'r':random.uniform(2,4.5),'life':1.0,'col':random.choice([rgb(255,120,20),rgb(255,210,60),rgb(255,80,20)])})
    # SOUND: explosion differs for building vs gorilla
    if gorilla:
        play_sound(app, 'gorilla_explosion')
    else:
        play_sound(app, 'building_explosion')

def checkGorillaHit(app,bx,by):
    for i,(gx,gy,bld) in enumerate(app.gorillaPos):
        if gx- Scl(5) <= bx <= gx+Scl(25) and gy- Scl(5) <= by <= gy+Scl(30): return i
    return -1

def onStep(app):
    if not hasattr(app,'buildings'): return
    app.blinkTimer+=1
    if app.blinkTimer>16: app.blink=not app.blink; app.blinkTimer=0
    if app.state=='intro':
        app.sparkle = (app.sparkle % 5)+1
        return
    for b in app.buildings:
        if not b.static and len(b.frags)>0: b.updateFrags()
    if app.sunTimer>0:
        app.sunTimer-=1
        if app.sunTimer==0: app.sunShocked=False
    if app.state=='flying' and app.banana:
        b=app.banana; b['vy']+=GRAVITY; b['x']+=b['vx']; b['y']+=b['vy']; b['rot']+=18; b['age']=b.get('age',0)+1; b['trail'].append((b['x'],b['y']))
        if len(b['trail'])>16: b['trail'].pop(0)
        x,y=b['x'],b['y']
        if x<-30 or x>WIDTH+30 or y>BOTTOM_LINE+30:
            app.banana=None; app.state='aiming'; app.J=1-app.J; app.currentPlayer=app.J; app.sunShocked=False; app.awaiting='angle'; app.inputText=""; return
        if (x-SUN_X)**2 + (y-SUN_Y)**2 < (Scl(12)+9)**2 and y < SUN_Y+Scl(12)+18:
            if not app.sunShocked: app.sunShocked=True; app.sunTimer=90
        hg=checkGorillaHit(app,x,y)
        if hg!=-1 and hg==app.currentPlayer and b.get('age',0) < 10:
            hg=-1
        if hg!=-1:
            app.winner=1-app.currentPlayer if hg==app.currentPlayer else app.currentPlayer
            app.scores[app.winner]+=1; app.totalWins[app.winner+1]+=1
            createExplosion(app,x,y,gorilla=True); app.banana=None; app.state='exploding'; return
        for building in app.buildings:
            if building.solidAt(x,y):
                building.damage(x,y,BLAST_R); createExplosion(app,x,y); app.banana=None; app.state='exploding'; app.winner=None; return
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
                        app.state='dancing'; app.victoryTimer=100
                        # SOUND: victory dance MFO0L32EFGEFDC x8
                        play_sound(app, 'victory_dance')
                    else: app.state='aiming'; app.J=1-app.J; app.currentPlayer=app.J; app.sunShocked=False; app.awaiting='angle'; app.inputText=""
        np=[]
        for p in app.particles:
            p['x']+=p['vx']; p['y']+=p['vy']; p['vy']+=0.18; p['vx']*=0.99; p['life']-=0.028
            if p['life']>0: np.append(p)
        app.particles=np
    elif app.state=='dancing':
        app.victoryTimer-=1
        if app.victoryTimer<=0:
            if max(app.scores)>=app.numGames: app.state='gameOver'; app.background=BLACK_BG
            else: startNewRound(app)

def onKeyPress(app, key):
    # Resume audio on any key (gesture)
    try:
        if hasattr(app, 'engine') and app.engine:
            app.engine.resume()
    except:
        pass
    if key is None: return
    low=str(key).lower()
    if 'shift' in low:
        app.shiftDown=True
        return
    if low in ('capslock','caps_lock','caps'):
        app.capsOn=not app.capsOn
        return
    ret=isReturnKey(key)
    if app.state=='intro':
        # SOUND: title 1812 MBT160O1L8CDEDCDL4ECC on intro -> game start
        play_sound(app, 'title')
        app.state='getInputs'; app.inputStage=0; app.inputText=""; app.background=BLACK_BG
        return
    if app.state=='getInputs':
        if ret:
            if app.inputStage==0:
                app.playerNames[0]=app.inputText.strip()[:10] if app.inputText.strip()!="" else "Player 1"
                app.inputStage=1; app.inputText=""
            elif app.inputStage==1:
                app.playerNames[1]=app.inputText.strip()[:10] if app.inputText.strip()!="" else "Player 2"
                app.inputStage=2; app.inputText=""
            elif app.inputStage==2:
                try: v=int(app.inputText.strip()); app.numGames=v if 0<v<20 else 3
                except: app.numGames=3
                app.inputStage=3; app.inputText=""
            elif app.inputStage==3:
                try: g=float(app.inputText.strip()); app.gravity=g*0.018 if g>0 else GRAVITY
                except: app.gravity=GRAVITY
                app.scores=[0,0]; app.totalWins=[0,0,0]; app.J=1; startNewRound(app)
                # SOUND: intro fanfare after setup
                play_sound(app, 'intro_fanfare_8x')
            return
        if key=='Backspace': app.inputText=app.inputText[:-1]; return
        if key=='Escape': app.inputText=""; return
        if key==' ' or low=='space':
            if app.inputStage in (0,1) and len(app.inputText)<10: app.inputText+=' '
            return
        if len(key)==1:
            ch=key
            if ch.isalpha():
                upper = app.shiftDown ^ app.capsOn
                if ch.islower() and upper: ch=ch.upper()
            if app.inputStage in (0,1):
                if len(app.inputText)<10: app.inputText+=ch
            else:
                if len(app.inputText)<6 and ch in "0123456789.":
                    if ch=="." and "." in app.inputText: pass
                    else: app.inputText+=ch
        return
    if app.state=='gameOver':
        if low=='y' or ret:
            app.state='getInputs'; app.inputStage=0; app.inputText=""; app.background=BLACK_BG
            play_sound(app, 'title')
        elif low=='n':
            app.state='intro'; app.background=BLACK_BG
        return
    if app.state=='aiming':
        if ret:
            txt=app.inputText.strip()
            if txt=="": return
            try: val=float(txt)
            except: app.inputText=""; return
            if app.awaiting=='angle':
                if val>360: app.inputText=""; return
                app.angle[app.currentPlayer]=val; app.inputText=""; app.awaiting='velocity'
            else:
                app.power[app.currentPlayer]=max(3,min(32,val))
                fireBanana(app); app.inputText=""; app.awaiting='angle'
            return
        if key=='Backspace': app.inputText=app.inputText[:-1]; return
        if len(key)==1 and key in "0123456789.":
            if len(app.inputText)<7:
                if key=="." and "." in app.inputText: pass
                else: app.inputText+=key
            return

def onKeyRelease(app, key):
    if key and 'shift' in str(key).lower(): app.shiftDown=False

def onMousePress(app,mx,my):
    try:
        if hasattr(app, 'engine') and app.engine:
            app.engine.resume()
    except:
        pass
    if app.state=='intro':
        play_sound(app, 'title')
        app.state='getInputs'; app.inputStage=0; app.inputText=""; app.background=BLACK_BG
    elif app.state=='gameOver':
        app.state='getInputs'; app.inputStage=0; app.inputText=""; app.background=BLACK_BG

def redrawAll(app):
    if not hasattr(app,'state'): return
    if app.state=='intro':
        drawRect(0,0,WIDTH,HEIGHT,fill=BLACK_BG)
        a=app.sparkle
        starLine="*    *    *    *    *    *    *    *    *    *    *    *    *    *    *    *    *    *    *    *    *    *    *    *    *    *"
        drawLabel(starLine[a-1:a+105], WIDTH//2, 10, fill=rgb(255,255,0), size=13, align='center')
        drawLabel(starLine[5-a:5-a+105], WIDTH//2, HEIGHT-10, fill=rgb(255,255,0), size=13, align='center')
        for b in range(2,24):
            c=(a+b)%5
            if c==1:
                drawLabel("*", 12, b*28, fill=rgb(255,255,0), size=13)
                drawLabel("*", WIDTH-12, (25-b)*28, fill=rgb(255,255,0), size=13)
        drawLabel("Q B a s i c    G O R I L L A S", WIDTH//2, 90, fill=rgb(255,255,255), size=20, bold=True, align='center')
        drawLabel("Copyright (C) IBM Corporation 1991", WIDTH//2, 130, fill=rgb(200,200,200), size=15, align='center')
        drawLabel("Your mission is to hit your opponent with the exploding", WIDTH//2, 180, fill=rgb(200,200,200), size=14, align='center')
        drawLabel("banana by varying the angle and power of your throw, taking", WIDTH//2, 205, fill=rgb(200,200,200), size=14, align='center')
        drawLabel("into account wind speed, gravity, and the city skyline.", WIDTH//2, 230, fill=rgb(200,200,200), size=14, align='center')
        drawLabel("The wind speed is shown by a directional arrow at the bottom", WIDTH//2, 255, fill=rgb(200,200,200), size=14, align='center')
        drawLabel("of the playing field, its length relative to its strength.", WIDTH//2, 280, fill=rgb(200,200,200), size=14, align='center')
        drawLabel("Press any key to continue", WIDTH//2, HEIGHT-50, fill=rgb(255,255,255), size=15, align='center')
        return
    if app.state=='getInputs':
        drawRect(0,0,WIDTH,HEIGHT,fill=BLACK_BG)
        y0=HEIGHT//2-100
        blink="_" if app.blink else ""
        if app.inputStage==0:
            drawLabel("Name of Player 1 (Default = 'Player 1'): " + app.inputText + blink, 80, y0, fill=rgb(255,255,255), size=30, align='left')
        elif app.inputStage==1:
            drawLabel(f"Name of Player 1: {app.playerNames[0]}", 80, y0-60, fill=rgb(180,180,180), size=30, align='left')
            drawLabel("Name of Player 2 (Default = 'Player 2'): " + app.inputText + blink, 80, y0, fill=rgb(255,255,255), size=30, align='left')
        elif app.inputStage==2:
            drawLabel("Play to how many total points (Default = 3): " + app.inputText + blink, 60, y0, fill=rgb(255,255,255), size=30, align='left')
        elif app.inputStage==3:
            drawLabel("Gravity in Meters/Sec (Earth = 9.8): " + app.inputText + blink, 80, y0, fill=rgb(255,255,255), size=28, align='left')
        return
    drawRect(0,0,WIDTH,HEIGHT,fill=BACK_COLOR)
    for b in app.buildings: b.draw()
    drawSun(SUN_X,SUN_Y,shocked=app.sunShocked)
    for i,(gx,gy,bld) in enumerate(app.gorillaPos):
        arm='down'
        if app.state=='flying' and app.banana and i==app.currentPlayer: arm='rightUp' if i==0 else 'leftUp'
        elif app.state=='dancing' and app.winner==i: arm='victory' if (app.victoryTimer//10)%2==0 else 'rightUp'
        drawGorilla(gx,gy,arm=arm,facing=1 if i==0 else -1)
    if app.banana:
        for j,(tx,ty) in enumerate(app.banana['trail']): drawCircle(tx,ty,2.5,fill=rgb(255,230,30),opacity=40+j*3)
        drawBanana(app.banana['x'],app.banana['y'],app.banana['rot'])
    if app.explosion:
        e=app.explosion; drawCircle(e['x'],e['y'],e['r'],fill=rgb(255,120,20)); drawCircle(e['x'],e['y'],e['r']*0.6,fill=rgb(255,220,100))
    for p in app.particles: drawCircle(p['x'],p['y'],p['r']*p['life'],fill=p['col'])
    # HUD - fixed layout: names at top, angle/velocity BELOW names to avoid overlap
    if app.state in ('aiming','flying','exploding','dancing'):
        try:
            drawLabel(app.playerNames[0], 24, 20, fill=rgb(255,255,255), size=24, align='left', bold=True, font='Orbitron')
            drawLabel(app.playerNames[1], WIDTH-24, 20, fill=rgb(255,255,255), size=24, align='right', bold=True, font='Orbitron')
        except:
            drawLabel(app.playerNames[0], 24, 20, fill=rgb(255,255,255), size=24, align='left', bold=True)
            drawLabel(app.playerNames[1], WIDTH-24, 20, fill=rgb(255,255,255), size=24, align='right', bold=True)
        if app.currentPlayer==0:
            ax=24; ay=60
        else:
            ax=WIDTH-260; ay=60
        if app.awaiting=='angle':
            drawLabel(f"Angle: {app.inputText}" + ("_" if app.blink else ""), ax, ay, fill=rgb(255,255,255), size=22, align='left', bold=True)
        else:
            drawLabel(f"Angle: {app.angle[app.currentPlayer]:.0f}", ax, ay, fill=rgb(220,220,220), size=20, align='left')
            drawLabel(f"Velocity: {app.inputText}" + ("_" if app.blink else ""), ax, ay+30, fill=rgb(255,255,255), size=22, align='left', bold=True)
    drawLabel(f"{app.totalWins[1]}>Score<{app.totalWins[2]}", WIDTH//2, HEIGHT-28, fill=rgb(255,255,255), size=32, align='center', bold=True)
    if app.state=='gameOver':
        drawRect(0,0,WIDTH,HEIGHT,fill=BLACK_BG)
        drawLabel("GAME OVER!", WIDTH//2, HEIGHT//2-60, fill=rgb(255,255,255), size=22, bold=True, align='center')
        drawLabel(f"{app.playerNames[0]}  {app.totalWins[1]}", WIDTH//2-100, HEIGHT//2+10, fill=rgb(255,255,255), size=15, align='left')
        drawLabel(f"{app.playerNames[1]}  {app.totalWins[2]}", WIDTH//2+100, HEIGHT//2+10, fill=rgb(255,255,255), size=15, align='right')
        drawLabel("Would you like to play again? (y/n)", WIDTH//2, HEIGHT//2+60, fill=rgb(255,85,255), size=15, align='center')

def main():
    runApp(1050,700)

main()
