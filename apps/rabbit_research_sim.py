
from scs import *
import math, random

def gaussian(mean, sd):
    # Box-Muller
    u1 = random.random()
    u2 = random.random()
    if u1 < 1e-6: u1 = 1e-6
    z = math.sqrt(-2*math.log(u1)) * math.cos(2*math.pi*u2)
    return mean + z*sd

def gaussian_pdf(x, mean, sd):
    if sd < 0.05: sd = 0.05
    return (1.0/(sd*math.sqrt(2*math.pi))) * math.exp(-0.5*((x-mean)/sd)**2)

def onAppStart(app):
    app.width=1050
    app.height=700
    app.stepsPerSecond=30
    app.background=rgb(242, 247, 238)

    # RESEARCH PARAMS - based on transcript effect size discussion
    app.ctrlMean=2.5  # kg rabbit weight
    app.rawDiff=0.6   # treatment adds 0.6kg
    app.sd=0.45
    app.ctrlSD=0.45
    app.n=24
    app.habitat=32  # base K
    app.food=1.0    # 0.4 - 1.8 multiplier
    app.predation=0.06
    app.growthR=0.18

    # LAYOUT FULL 1050x700
    app.meadowTop=66
    app.meadowBot=382
    app.ctrlL=14; app.ctrlR=516
    app.expL=534; app.expR=1036
    app.graphL=14; app.graphR=700
    app.graphTop=400; app.graphBot=620
    app.xMin=1.0; app.xMax=4.8

    app.time=0
    app.showBells=True
    app.useGlass=False

    app.ctrlRabbits=[]
    app.expRabbits=[]
    app.foxes=[{'x': 300, 'dir':1}, {'x': 800, 'dir':-1}]

    generateRabbits(app)

def generateRabbits(app):
    app.ctrlRabbits=[]
    app.expRabbits=[]
    expMean = app.ctrlMean + app.rawDiff
    for i in range(app.n):
        # control
        x = random.uniform(app.ctrlL+20, app.ctrlR-20)
        y = random.uniform(app.meadowTop+40, app.meadowBot-18)
        w = gaussian(app.ctrlMean, app.ctrlSD)
        w = max(0.8, min(5.0, w))
        app.ctrlRabbits.append({'x':x,'y':y,'w':w,'hop':random.random()*6.28,'id':i})
        # experimental
        x2 = random.uniform(app.expL+20, app.expR-20)
        y2 = random.uniform(app.meadowTop+40, app.meadowBot-18)
        w2 = gaussian(expMean, app.sd)
        w2 = max(0.8, min(5.0, w2))
        app.expRabbits.append({'x':x2,'y':y2,'w':w2,'hop':random.random()*6.28,'id':i+100})

def computeStats(app):
    if not app.ctrlRabbits or not app.expRabbits:
        return None
    ctrlWs = [r['w'] for r in app.ctrlRabbits]
    expWs = [r['w'] for r in app.expRabbits]
    def mean(arr): return sum(arr)/len(arr) if arr else 0
    def sd(arr, m):
        if len(arr)<2: return 0.4
        return math.sqrt(sum((x-m)**2 for x in arr)/(len(arr)-1))
    mC=mean(ctrlWs); mE=mean(expWs)
    sC=sd(ctrlWs,mC); sE=sd(expWs,mE)
    raw = mE - mC
    pooledVar = ((len(ctrlWs)-1)*sC*sC + (len(expWs)-1)*sE*sE) / (len(ctrlWs)+len(expWs)-2) if len(ctrlWs)+len(expWs)>2 else sC*sC
    pooledSD = math.sqrt(pooledVar) if pooledVar>0 else 0.4
    d = raw/pooledSD if pooledSD>0 else 0
    df = len(ctrlWs)+len(expWs)-2
    J = 1 - 3/(4*df-1) if df>1 else 1
    g = d*J
    delta = raw/sC if sC>0 else 0
    K = app.habitat * app.food
    return {'mC':mC,'mE':mE,'sC':sC,'sE':sE,'raw':raw,'pooled':pooledSD,'d':d,'g':g,'delta':delta,'J':J,'K':K,'nC':len(ctrlWs),'nE':len(expWs)}

def pX(app, v):
    return app.graphL + (v-app.xMin)/(app.xMax-app.xMin)*(app.graphR-app.graphL)
def vX(app, px):
    return app.xMin + (px-app.graphL)/(app.graphR-app.graphL)*(app.xMax-app.xMin)

def onStep(app):
    app.time+=1
    stats = computeStats(app)
    if not stats: return
    K = stats['K']
    # logistic + predation for each meadow
    for group in [app.ctrlRabbits, app.expRabbits]:
        N = len(group)
        # birth chance increases when below K
        if N < K and N>0 and random.random() < app.growthR * (1 - N/K + 0.2):
            # new rabbit near random existing
            parent = random.choice(group)
            x = parent['x'] + random.uniform(-18,18)
            # clamp to meadow bounds
            if group is app.ctrlRabbits:
                x = max(app.ctrlL+18, min(app.ctrlR-18, x))
                y = max(app.meadowTop+40, min(app.meadowBot-18, parent['y']+random.uniform(-10,10)))
                w = gaussian(app.ctrlMean, app.ctrlSD)
            else:
                x = max(app.expL+18, min(app.expR-18, x))
                y = max(app.meadowTop+40, min(app.meadowBot-18, parent['y']+random.uniform(-10,10)))
                w = gaussian(app.ctrlMean+app.rawDiff, app.sd)
            w = max(0.8, min(5.0, w))
            group.append({'x':x,'y':y,'w':w,'hop':random.random()*6.28,'id':random.randint(0,10000)})
        # predation - remove
        if N>3 and random.random() < app.predation:
            # remove smallest / random to simulate predation pressure
            idx = random.randrange(len(group))
            group.pop(idx)
        # movement + hop animation
        for r in group:
            r['x'] += random.uniform(-0.9,0.9)
            r['hop'] += 0.22
            if group is app.ctrlRabbits:
                r['x'] = max(app.ctrlL+14, min(app.ctrlR-14, r['x']))
            else:
                r['x'] = max(app.expL+14, min(app.expR-14, r['x']))

    # fox movement
    for fox in app.foxes:
        fox['x'] += fox['dir']*1.1
        if fox['x']<50 or fox['x']>1000:
            fox['dir']*=-1

def drawRabbit(x, y, w, isCtrl, hopPhase, time):
    # w = weight trait influences size
    size = 0.8 + (w-1.0)*0.35
    size = max(0.7, min(1.6, size))
    hop = math.sin(hopPhase + time*0.12)*4*size
    y2 = y + hop
    # shadow
    drawOval(x, y+10*size, 18*size, 6*size, fill=rgb(0,0,0), opacity=18)
    # body
    bodyCol = rgb(120,160,255) if isCtrl else rgb(255,110,110) if w>2.8 else rgb(255,160,120)
    # make heavier rabbits slightly larger/darker
    if not isCtrl:
        # experimental gets golden tint if heavy
        if w > 3.0:
            bodyCol = rgb(255,190,80)
    drawOval(x, y2, 22*size, 14*size, fill=bodyCol, border=rgb(30,30,30), borderWidth=1)
    # head
    drawCircle(x+8*size, y2-6*size, 8*size, fill=bodyCol, border=rgb(30,30,30), borderWidth=1)
    # ears
    drawOval(x+10*size, y2-16*size, 5*size, 12*size, fill=bodyCol, border=rgb(30,30,30), borderWidth=1)
    drawOval(x+15*size, y2-15*size, 4*size, 10*size, fill=rgb(255,200,200), border=None)
    # eye
    drawCircle(x+12*size, y2-7*size, 1.8*size, fill=rgb(20,20,20))
    # weight label tiny
    # drawLabel(f"{w:.1f}", x, y2+14*size, size=15, fill=rgb(50,50,50))

def drawMeadow(app, L, R, Top, Bot, rabbits, isCtrl, label):
    # background
    drawRect(L, Top, R-L, Bot-Top, fill=rgb(180,220,140) if isCtrl else rgb(190,230,150), border=rgb(120,170,90), borderWidth=1, roundness=12)
    # grass texture - many small blades
    for i in range(80):
        gx = L + (i*37 % (R-L-10)) + random.uniform(-2,2)
        gy = Bot - random.uniform(2,22)
        drawLine(gx, gy, gx+random.uniform(-2,2), gy- random.uniform(4,9), fill=rgb(100,150,60), lineWidth=1, opacity=70)
    # flowers
    for i in range(8):
        fx = L + 20 + i* (R-L)//9
        fy = Top + 18 + (i%3)*8
        col = rgb(255,220,80) if i%2==0 else rgb(255,180,200)
        drawCircle(fx, fy, 3, fill=col, border=rgb(100,120,60), borderWidth=1)
    # rabbits
    for r in rabbits:
        drawRabbit(r['x'], r['y'], r['w'], isCtrl, r['hop'], app.time)
    # meadow label - BIG FONT +8 style
    drawRect(L+8, Top+6, 220, 28, fill=rgb(255,255,255), opacity=85, border=None, roundness=8)
    drawLabel(label, L+118, Top+20, size=18, bold=True, fill=rgb(30,60,20))
    # N/K bar
    stats = computeStats(app)
    if stats:
        K = stats['K']
        N = len(rabbits)
        frac = min(1, N/K) if K>0 else 0
        barL = L+12; barW = 180
        drawRect(barL, Bot-14, barW, 8, fill=rgb(255,255,255), border=rgb(80,80,80), borderWidth=1, roundness=4)
        drawRect(barL, Bot-14, barW*frac, 8, fill=rgb(60,140,40) if frac<0.9 else rgb(200,60,30), border=None, roundness=4)
        drawLabel(f"N={N} K={K:.0f} {frac*100:.0f}%", L+118, Bot-6, size=15, bold=True, fill=rgb(40,40,40))

def handleKeys(app, key):
    k = key.lower() if isinstance(key,str) else key
    if k=='r':
        app.ctrlMean=2.5; app.rawDiff=0.6; app.sd=0.45; app.ctrlSD=0.45; app.n=24
        app.habitat=32; app.food=1.0; app.predation=0.06; app.growthR=0.18
        app.useGlass=False; generateRabbits(app); return True
    elif k==' ' or k=='space':
        generateRabbits(app); return True
    elif k=='up':
        app.rawDiff=min(2.0, app.rawDiff+0.08); generateRabbits(app); return True
    elif k=='down':
        app.rawDiff=max(0.05, app.rawDiff-0.08); generateRabbits(app); return True
    elif k=='right':
        app.sd=min(1.2, app.sd+0.05); app.ctrlSD=min(1.2, app.ctrlSD+0.05); generateRabbits(app); return True
    elif k=='left':
        app.sd=max(0.15, app.sd-0.05); app.ctrlSD=max(0.15, app.ctrlSD-0.05); generateRabbits(app); return True
    elif k=='m':
        app.n=min(80, app.n+4); generateRabbits(app); return True
    elif k=='n':
        app.n=max(6, app.n-4); generateRabbits(app); return True
    elif k=='g':
        app.useGlass=not app.useGlass; return True
    elif k=='f':
        app.food=min(1.8, app.food+0.1); return True
    elif k=='v': # less food (v for minus food)
        app.food=max(0.4, app.food-0.1); return True
    elif k=='h':
        app.habitat=min(70, app.habitat+3); return True
    elif k=='j':
        app.habitat=max(10, app.habitat-3); return True
    elif k=='p':
        app.predation=min(0.25, app.predation+0.015); return True
    elif k=='o':
        app.predation=max(0.0, app.predation-0.015); return True
    elif k=='b':
        app.showBells=not app.showBells; return True
    return False

def onKeyPress(app,key):
    handleKeys(app,key)

def onKeyHold(app,keys):
    if isinstance(keys, dict):
        for k in ['up','down','left','right','n','m','g','r','f','v','h','j','p','o','b',' ']:
            if keys.get(k):
                handleKeys(app,k)
    elif isinstance(keys,(list,tuple,set)):
        for k in keys:
            handleKeys(app,k)

def onMousePress(app,mx,my):
    # click in graph to set raw diff
    if app.graphL <= mx <= app.graphR and app.graphTop <= my <= app.graphBot:
        # map x to weight diff
        val = app.xMin + (mx-app.graphL)/(app.graphR-app.graphL)*(app.xMax-app.xMin)
        # raw diff approx = val - ctrlMean? Actually exp mean = ctrl + raw
        # set raw diff = val - ctrlMean if clicking near exp side
        if val > app.ctrlMean:
            app.rawDiff = max(0.05, min(2.0, val - app.ctrlMean))
            generateRabbits(app)

def redrawAll(app):
    stats = computeStats(app)
    if not stats:
        return

    # HEADER - NO FILENAME
    drawRect(0,0,1050,60,fill=rgb(22,26,18))
    drawLabel("Rabbit Research Lab — Population Dynamics Meets Effect Size",525,20,size=20,bold=True,fill=rgb(255,255,255))
    drawLabel("UP/DOWN effect | LEFT/RIGHT noise | N/M rabbits | F/V food | H/J habitat | P/O predation | G Glass | B bells | SPACE new | R reset",525,42,size=15,fill=rgb(180,200,160))

    # MEADOWS - FULL WIDTH
    drawMeadow(app, app.ctrlL, app.ctrlR, app.meadowTop, app.meadowBot, app.ctrlRabbits, True, f"CONTROL n={stats['nC']}")
    drawMeadow(app, app.expL, app.expR, app.meadowTop, app.meadowBot, app.expRabbits, False, f"ENRICHED n={stats['nE']} +{app.rawDiff:.2f}kg")

    # FOXES - little predator indicator
    for fox in app.foxes:
        drawOval(fox['x'], app.meadowBot+8, 18, 8, fill=rgb(180,80,30), border=rgb(50,20,10), borderWidth=1)
        drawCircle(fox['x']+6, app.meadowBot+4, 6, fill=rgb(200,90,30), border=rgb(50,20,10), borderWidth=1)

    # GRAPH AREA - BELL CURVES - uses 55-995 full width style but now left panel
    drawRect(app.graphL-2, app.graphTop-2, app.graphR-app.graphL+4, app.graphBot-app.graphTop+4, fill=rgb(255,255,255), border=rgb(190,200,170), borderWidth=1, roundness=12)

    # x grid + big fonts +8
    for v in [1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5]:
        x = pX(app,v)
        drawLine(x, app.graphTop, x, app.graphBot, fill=rgb(230,235,220), lineWidth=1)
        drawLine(x, app.graphBot, x, app.graphBot+6, fill=rgb(120,120,100))
        drawLabel(f"{v:.1f}", x, app.graphBot+16, size=20, bold=True, fill=rgb(70,70,60))
    drawLabel("Rabbit weight (kg) — heavier = better nutrition →", 357, app.graphBot+38, size=20, bold=True, fill=rgb(60,60,50))

    # bells
    maxG = max(1/(stats['sC']*2.5066) if stats['sC']>0 else 1, 1/(stats['sE']*2.5066) if stats['sE']>0 else 1)
    hScale = 160 / maxG if maxG>0 else 120
    ptsC=[]; ptsE=[]
    for i in range(200):
        xv = app.xMin + (app.xMax-app.xMin)*i/199
        yc = gaussian_pdf(xv, stats['mC'], stats['sC'])
        ye = gaussian_pdf(xv, stats['mE'], stats['sE'])
        xpix = pX(app,xv)
        ptsC.append((xpix, app.graphBot - yc*hScale))
        ptsE.append((xpix, app.graphBot - ye*hScale))
    # fills
    for i in range(len(ptsC)):
        x,y=ptsC[i]; drawLine(x,y,x,app.graphBot,fill=rgb(100,150,255),lineWidth=1,opacity=14)
    for i in range(len(ptsE)):
        x,y=ptsE[i]; drawLine(x,y,x,app.graphBot,fill=rgb(255,100,100),lineWidth=1,opacity=14)
    for i in range(len(ptsC)-1):
        drawLine(ptsC[i][0],ptsC[i][1],ptsC[i+1][0],ptsC[i+1][1],fill=rgb(60,110,200),lineWidth=4)
        drawLine(ptsE[i][0],ptsE[i][1],ptsE[i+1][0],ptsE[i+1][1],fill=rgb(200,40,40),lineWidth=4)

    # mean lines with BIG fonts +8
    cx = pX(app, stats['mC']); ex = pX(app, stats['mE'])
    drawLine(cx, app.graphTop+8, cx, app.graphBot, fill=rgb(60,110,200), lineWidth=2, dashes=True, opacity=80)
    drawLine(ex, app.graphTop+8, ex, app.graphBot, fill=rgb(200,40,40), lineWidth=2, dashes=True, opacity=80)
    drawCircle(cx, app.graphTop+16, 10, fill=rgb(60,110,200), border=rgb(255,255,255), borderWidth=3)
    drawCircle(ex, app.graphTop+16, 10, fill=rgb(200,40,40), border=rgb(255,255,255), borderWidth=3)
    drawLabel(f"CTRL {stats['mC']:.2f}kg σ={stats['sC']:.2f}", cx, app.graphTop-2, size=20, bold=True, fill=rgb(40,80,180))
    drawLabel(f"ENRICHED    {stats['mE']:.2f}kg σ={stats['sE']:.2f}", ex, app.graphTop+18, size=20, bold=True, fill=rgb(180,30,30))

    # raw diff arrow big
    drawLine(ex, app.graphBot-30, cx, app.graphBot-30, fill=rgb(20,20,20), lineWidth=3, arrowStart=True, arrowEnd=True)
    drawLabel(f"DIFF = {stats['raw']:.2f}kg", (ex+cx)/2, app.graphBot-52, size=20, bold=True, fill=rgb(20,20,20))

    # RIGHT STATS PANEL - FULL HEIGHT RIGHT
    rx=714; rw=322
    cardY=400
    # pop dynamics card
    drawRect(rx, cardY, rw, 84, fill=rgb(255,255,255), border=rgb(190,200,170), borderWidth=1, roundness=12)
    drawLabel("Population Dynamics", rx+12, cardY+14, size=15, bold=True, fill=rgb(30,60,20), align='left')
    drawLabel(f"K = habitat×food = {app.habitat}×{app.food:.1f} = {stats['K']:.0f}", rx+12, cardY+32, size=15, align='left')
    drawLabel(f"Growth r={app.growthR:.2f} Pred={app.predation:.2f} H/J habitat F/V food P/O pred", rx+12, cardY+48, size=15, align='left', fill=rgb(80,80,80))
    drawLabel(f"Control {stats['nC']} vs Enriched {stats['nE']} rabbits alive", rx+12, cardY+64, size=15, bold=True, align='left')

    # effect size card
    cardY2=492
    drawRect(rx, cardY2, rw, 118, fill=rgb(255,255,255), border=rgb(190,200,215), borderWidth=1, roundness=12)
    drawLabel("Effect Size Lab", rx+12, cardY2+14, size=15, bold=True, fill=rgb(20,20,40), align='left')
    drawLabel(f"d = {stats['raw']:.2f}/{stats['pooled']:.2f} = {stats['d']:.3f}", rx+12, cardY2+32, size=18, bold=True, align='left')
    interp="negligible" if abs(stats['d'])<0.2 else "small" if abs(stats['d'])<0.5 else "medium" if abs(stats['d'])<0.8 else "LARGE"
    drawLabel(f"{interp} (0.2 small 0.5 med 0.8 large ≠ law)", rx+12, cardY2+52, size=15, fill=rgb(70,70,80), align='left')
    drawLabel(f"Hedges g={stats['g']:.3f} J={stats['J']:.3f}", rx+12, cardY2+70, size=15, bold=True, fill=rgb(70,50,100), align='left')
    glassBg = rgb(255,235,160) if app.useGlass else rgb(245,245,245)
    drawRect(rx+8, cardY2+84, rw-16, 24, fill=glassBg, border=rgb(200,170,90) if app.useGlass else rgb(210,210,210), borderWidth=1, roundness=6)
    drawLabel(f"Glass Δ={stats['delta']:.3f} {'[ON]' if app.useGlass else '[OFF G]'}", rx+12, cardY2+98, size=15, bold=True, fill=rgb(120,70,15), align='left')

    # p-value illusion card
    cardY3=618
    # t approx
    t = stats['d']*math.sqrt(stats['nC']/2) if stats['nC']>0 else 0
    if abs(t)>3.5: p=0.0004
    elif abs(t)>2.8: p=0.005
    elif abs(t)>2.0: p=0.04
    elif abs(t)>1.3: p=0.18
    else: p=0.42
    drawRect(rx, cardY3, rw, 72, fill=rgb(255,245,248), border=rgb(230,170,185), borderWidth=1, roundness=12)
    drawLabel("P-Value Trap", rx+12, cardY3+14, size=15, bold=True, fill=rgb(150,25,55), align='left')
    drawLabel(f"n={stats['nC']}+{stats['nE']} t={t:.2f} p≈{p}", rx+12, cardY3+32, size=15, bold=True, align='left')
    pCol = rgb(0,140,0) if p<0.05 else rgb(180,30,30)
    drawLabel(f"{'SIGNIFICANT' if p<0.05 else 'not sig'} but d={stats['d']:.2f} {interp}", rx+12, cardY3+50, size=15, bold=True, fill=pCol, align='left')
    drawLabel("Large n makes tiny diff p<0.05", rx+12, cardY3+64, size=15, fill=rgb(120,40,50), align='left')
