from scs import *
import math

def gaussian(x, mean, sd):
    if sd < 0.5: sd = 0.5
    return (1.0 / (sd * math.sqrt(2*math.pi))) * math.exp(-0.5 * ((x-mean)/sd)**2)

def onAppStart(app):
    app.width=1050
    app.height=700
    app.stepsPerSecond=30
    app.background=rgb(248,249,252)
    app.ctrlMean=130.0
    app.rawDiff=22.4
    app.sd=12.0
    app.ctrlSD=12.0
    app.n=120
    app.useGlass=False
    # MOVED DOWN 50px: was 72/410, now 122/460
    app.gL=55
    app.gR=995
    app.gT=122
    app.gB=460
    app.xMin=82
    app.xMax=178
    app.dragging=False

def pX(app,v):
    return app.gL + (v-app.xMin)/(app.xMax-app.xMin)*(app.gR-app.gL)

def vX(app,px):
    return app.xMin + (px-app.gL)/(app.gR-app.gL)*(app.xMax-app.xMin)

def compute(app):
    expMean=app.ctrlMean-app.rawDiff
    d=app.rawDiff/app.sd if app.sd else 0
    df=2*app.n-2
    J=1-3/(4*df-1) if df>1 else 1
    g=d*J
    delta=app.rawDiff/app.ctrlSD if app.ctrlSD else 0
    t=d*math.sqrt(app.n/2)
    if abs(t)>3.5: p=0.0004
    elif abs(t)>2.8: p=0.005
    elif abs(t)>2.0: p=0.04
    elif abs(t)>1.3: p=0.18
    else: p=0.42
    return expMean,d,g,delta,J,t,p

def onMousePress(app,mx,my):
    if app.gL<=mx<=app.gR and app.gT<=my<=app.gB:
        app.dragging=True
        app.rawDiff=max(0.2,min(40,app.ctrlMean-vX(app,mx)))

def onMouseDrag(app,mx,my):
    if app.dragging:
        app.rawDiff=max(0.2,min(40,app.ctrlMean-vX(app,mx)))

def onMouseRelease(app,mx,my):
    app.dragging=False

def handleKeys(app,key):
    # robust lowercasing
    k = key.lower() if isinstance(key,str) else key
    changed=False
    if k=='r':
        app.rawDiff=1.0; app.n=50000; app.sd=12; app.ctrlSD=12; app.useGlass=False; changed=True
    elif k=='up':
        app.rawDiff=min(40,app.rawDiff+0.6); changed=True
    elif k=='down':
        app.rawDiff=max(0.2,app.rawDiff-0.6); changed=True
    elif k=='right':
        app.sd=min(30,app.sd+1); app.ctrlSD=min(30,app.ctrlSD+1); changed=True
    elif k=='left':
        app.sd=max(3,app.sd-1); app.ctrlSD=max(3,app.ctrlSD-1); changed=True
    elif k=='m':  # M = more sample
        app.n=min(50000,int(app.n*1.45+10)); changed=True
    elif k=='n':  # N = fewer
        app.n=max(10,int(app.n/1.45)); changed=True
    elif k=='g':  # G = Glass delta toggle
        app.useGlass=not app.useGlass; changed=True
    return changed

def onKeyPress(app,key):
    handleKeys(app,key)

def onKeyHold(app,keys):
    # SCS sometimes sends keys as dict/list for hold
    # support both forms
    if isinstance(keys, dict):
        for k in ['up','down','left','right','n','m','g','r']:
            if keys.get(k):
                handleKeys(app,k)
    elif isinstance(keys, (list,tuple,set)):
        for k in keys:
            handleKeys(app,k)

def redrawAll(app):
    expMean,d,g,delta,J,t,p=compute(app)

    # HEADER - no filename
    drawRect(0,0,1050,60,fill=rgb(18,20,28))
    drawLabel("Why P < 0.05 Means Nothing Without Effect Size",525,20,size=21,bold=True,fill=rgb(255,255,255))
    drawLabel("DRAG curves | UP/DOWN effect | LEFT/RIGHT noise | N/M sample size | G Glass Δ | R 1-pt trap",525,42,size=12,fill=rgb(180,180,190))

    # GRAPH - moved down 50px
    drawRect(app.gL-2,app.gT-2,app.gR-app.gL+4,app.gB-app.gT+4,fill=rgb(255,255,255),border=rgb(190,200,210),borderWidth=1,roundness=12)

    # x grid + labels - FONT +8: was 13 -> 21
    for v in range(85,176,5):
        x=pX(app,v)
        if v%10==0:
            drawLine(x,app.gT,x,app.gB,fill=rgb(232,233,236),lineWidth=1)
            drawLine(x,app.gB,x,app.gB+6,fill=rgb(160,160,160))
            drawLabel(str(v),x,app.gB+18,size=21,bold=True,fill=rgb(80,80,80))
        else:
            drawLine(x,app.gT,x,app.gB,fill=rgb(242,243,245))

    # x title - FONT +8: was 14 -> 22
    drawLabel("Systolic BP (mmHg) — lower is better →",525,app.gB+44,size=22,bold=True,fill=rgb(60,60,70))

    maxG=max(1/(app.ctrlSD*2.5066),1/(app.sd*2.5066))
    hScale=260/maxG if maxG>0 else 200
    ptsC=[]; ptsE=[]
    for i in range(240):
        xv=app.xMin + (app.xMax-app.xMin)*i/239
        yc=gaussian(xv,app.ctrlMean,app.ctrlSD)
        ye=gaussian(xv,expMean,app.sd)
        xpix=pX(app,xv)
        ptsC.append((xpix,app.gB-yc*hScale))
        ptsE.append((xpix,app.gB-ye*hScale))

    for i in range(len(ptsC)):
        x,y=ptsC[i]; drawLine(x,y,x,app.gB,fill=rgb(60,110,230),lineWidth=1,opacity=16)
    for i in range(len(ptsE)):
        x,y=ptsE[i]; drawLine(x,y,x,app.gB,fill=rgb(220,50,50),lineWidth=1,opacity=16)
    for i in range(len(ptsC)-1):
        drawLine(ptsC[i][0],ptsC[i][1],ptsC[i+1][0],ptsC[i+1][1],fill=rgb(45,90,210),lineWidth=4)
        drawLine(ptsE[i][0],ptsE[i][1],ptsE[i+1][0],ptsE[i+1][1],fill=rgb(200,35,35),lineWidth=4)

    cx=pX(app,app.ctrlMean); ex=pX(app,expMean)
    drawLine(cx,app.gT+8,cx,app.gB,fill=rgb(45,90,210),lineWidth=2,dashes=True,opacity=80)
    drawLine(ex,app.gT+8,ex,app.gB,fill=rgb(200,35,35),lineWidth=2,dashes=True,opacity=80)
    drawCircle(cx,app.gT+18,12,fill=rgb(45,90,210),border=rgb(255,255,255),borderWidth=3)
    drawCircle(ex,app.gT+18,12,fill=rgb(200,35,35),border=rgb(255,255,255),borderWidth=3)

    # GRAPH LABELS - FONT +8: was 14 -> 22
    drawLabel(f"CONTROL {app.ctrlMean:.0f} σ={app.ctrlSD:.0f}",cx,app.gT-8,size=22,bold=True,fill=rgb(45,90,210))
    drawLabel(f"DRUG {expMean:.1f} σ={app.sd:.0f}",ex,app.gT-8,size=22,bold=True,fill=rgb(200,35,35))

    # RAW DIFF - FONT +8: was 15 -> 23
    drawLine(ex,app.gB-36,cx,app.gB-36,fill=rgb(20,20,20),lineWidth=3,arrowStart=True,arrowEnd=True)
    drawLabel(f"RAW DIFFERENCE = {app.rawDiff:.1f} mmHg",(ex+cx)/2,app.gB-62,size=23,bold=True,fill=rgb(20,20,20))

    # BOTTOM CARDS - shifted down to fit after graph move
    cardY=532
    cardH=158
    # card 1
    drawRect(18,cardY,322,cardH,fill=rgb(255,255,255),border=rgb(190,200,215),borderWidth=1,roundness=12)
    drawLabel("Effect Size (the real question)",32,cardY+16,size=12,bold=True,fill=rgb(20,20,30),align='left')
    drawLabel(f"d = {app.rawDiff:.1f}/{app.sd:.1f} = {d:.3f}",32,cardY+38,size=18,bold=True,align='left')
    interp="negligible" if abs(d)<0.2 else "small" if abs(d)<0.5 else "medium" if abs(d)<0.8 else "LARGE"
    drawLabel(f"{interp} (0.2/0.5/0.8 ≠ law)",32,cardY+58,size=11,fill=rgb(60,60,70),align='left')
    drawLabel(f"Hedges g={g:.3f} J={J:.4f}",32,cardY+76,size=11,bold=True,fill=rgb(70,50,100),align='left')
    # Glass highlight
    glassBg = rgb(255,235,180) if app.useGlass else rgb(255,255,255)
    drawRect(30,cardY+92,300,26,fill=glassBg,border=rgb(200,170,100) if app.useGlass else rgb(220,220,220),borderWidth=1 if app.useGlass else 0,roundness=6)
    drawLabel(f"Glass Δ={delta:.3f} {'[ON - using ctrl SD]' if app.useGlass else '[OFF - press G]'}",32,cardY+106,size=12,bold=True,fill=rgb(120,70,15),align='left')
    drawLabel("Use Δ when treatment explodes variance",32,cardY+130,size=10,fill=rgb(100,80,50),align='left')

    # card 2
    drawRect(364,cardY,322,cardH,fill=rgb(255,245,248),border=rgb(230,170,185),borderWidth=1,roundness=12)
    drawLabel("P-VALUE ILLUSION",378,cardY+16,size=12,bold=True,fill=rgb(150,25,55),align='left')
    drawLabel(f"n = {app.n:,} per group {'[M=more N=fewer]' if app.n<1000 else ''}",378,cardY+36,size=12,bold=True,align='left')
    drawLabel(f"t ≈ d·√(n/2) = {t:.2f}",378,cardY+54,size=12,align='left')
    pCol=rgb(0,140,0) if p<0.05 else rgb(180,30,30)
    drawLabel(f"p ≈ {p}",378,cardY+76,size=24,bold=True,fill=pCol,align='left')
    drawLabel(f"{'→ SIGNIFICANT!' if p<0.05 else '→ NOT significant'}",378,cardY+98,size=12,bold=True,fill=pCol,align='left')
    drawLabel("With n=50k, d=0.08 → p<0.05",378,cardY+116,size=10,fill=rgb(120,40,50),align='left')
    drawLabel("P = engine on? d = >5 mph?",378,cardY+132,size=11,bold=True,align='left')

    # card 3
    drawRect(710,cardY,322,cardH,fill=rgb(242,252,242),border=rgb(160,200,160),borderWidth=1,roundness=12)
    drawLabel("CLINICAL CONTEXT",724,cardY+16,size=12,bold=True,fill=rgb(25,90,25),align='left')
    if app.rawDiff <= 1.5:
        drawLabel(f"d={d:.2f} → 1 mmHg drop",724,cardY+38,size=12,align='left')
        drawLabel("Saves ~0 lives.",724,cardY+56,size=13,bold=True,fill=rgb(180,30,30),align='left')
        drawLabel("Math sig, clinically USELESS.",724,cardY+74,size=11,bold=True,fill=rgb(180,30,30),align='left')
    elif app.rawDiff < 6:
        drawLabel(f"d={d:.2f} small, millions→matters",724,cardY+38,size=11,align='left')
        drawLabel("0.2 mortality = thousands saved",724,cardY+56,size=11,bold=True,align='left')
    else:
        drawLabel(f"d={d:.2f} MEDIUM/LARGE",724,cardY+38,size=13,bold=True,align='left')
        drawLabel(f"{app.rawDiff:.0f} mmHg prevents strokes",724,cardY+56,size=11,align='left')
    drawLabel("Fun rating d=0.8 = trivial.",724,cardY+92,size=10,fill=rgb(80,80,80),align='left')
    drawLabel("Mortality d=0.2 = massive.",724,cardY+106,size=10,bold=True,fill=rgb(80,80,80),align='left')
    drawLabel(f"Glass: {delta:.2f} vs Cohen d: {d:.2f}",724,cardY+124,size=10,fill=rgb(100,70,20),align='left')
