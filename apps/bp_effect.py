
from scs import *
import math
def gaussian(x, mean, sd):
    if sd < 0.5: sd = 0.5
    return (1.0 / (sd * math.sqrt(2*math.pi))) * math.exp(-0.5 * ((x-mean)/sd)**2)
def onAppStart(app):
    app.width=1050; app.height=700; app.background=rgb(248,249,252)
    app.ctrlMean=130.0; app.rawDiff=22.4; app.sd=12.0; app.ctrlSD=12.0; app.n=120; app.useGlass=False
    app.gL=55; app.gR=995; app.gT=72; app.gB=410; app.xMin=82; app.xMax=178; app.dragging=False
def pX(app,v): return app.gL + (v-app.xMin)/(app.xMax-app.xMin)*(app.gR-app.gL)
def vX(app,px): return app.xMin + (px-app.gL)/(app.gR-app.gL)*(app.xMax-app.xMin)
def compute(app):
    expMean=app.ctrlMean-app.rawDiff
    d=app.rawDiff/app.sd if app.sd else 0
    df=2*app.n-2; J=1-3/(4*df-1) if df>1 else 1; g=d*J
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
        app.dragging=True; app.rawDiff=max(0.2,min(40,app.ctrlMean-vX(app,mx)))
def onMouseDrag(app,mx,my):
    if app.dragging: app.rawDiff=max(0.2,min(40,app.ctrlMean-vX(app,mx)))
def onMouseRelease(app,mx,my): app.dragging=False
def onKeyPress(app,key):
    if key in ('r','R'): app.rawDiff=1.0; app.n=50000; app.sd=12; app.ctrlSD=12; app.useGlass=False
    elif key=='up': app.rawDiff=min(40,app.rawDiff+0.6)
    elif key=='down': app.rawDiff=max(0.2,app.rawDiff-0.6)
    elif key=='right': app.sd=min(30,app.sd+1); app.ctrlSD=min(30,app.ctrlSD+1)
    elif key=='left': app.sd=max(3,app.sd-1); app.ctrlSD=max(3,app.ctrlSD-1)
    elif key in ('m','M'): app.n=min(50000,int(app.n*1.35+8))
    elif key in ('n','N'): app.n=max(10,int(app.n/1.35))
    elif key in ('g','G'): app.useGlass=not app.useGlass
def redrawAll(app):
    expMean,d,g,delta,J,t,p=compute(app)
    drawRect(0,0,1050,60,fill=rgb(18,20,28))
    drawLabel("Why P < 0.05 Means Nothing Without Effect Size",525,20,size=21,bold=True,fill=rgb(255,255,255))
    drawLabel("DRAG curves | UP/DOWN effect | LEFT/RIGHT noise | N/M sample size | G Glass Δ | R 1-pt trap",525,42,size=12,fill=rgb(180,180,190))
    drawRect(app.gL-2,app.gT-2,app.gR-app.gL+4,app.gB-app.gT+4,fill=rgb(255,255,255),border=rgb(190,200,210),borderWidth=1,roundness=12)
    for v in range(85,176,5):
        x=pX(app,v)
        if v%10==0:
            drawLine(x,app.gT,x,app.gB,fill=rgb(232,233,236),lineWidth=1)
            drawLine(x,app.gB,x,app.gB+6,fill=rgb(160,160,160))
            drawLabel(str(v),x,app.gB+16,size=13,bold=True,fill=rgb(80,80,80))
        else:
            drawLine(x,app.gT,x,app.gB,fill=rgb(242,243,245))
    drawLabel("Systolic BP (mmHg) — lower is better →",525,app.gB+36,size=14,bold=True,fill=rgb(60,60,70))
    maxG=max(1/(app.ctrlSD*2.5066),1/(app.sd*2.5066))
    hScale=260/maxG if maxG>0 else 200
    ptsC=[]; ptsE=[]
    for i in range(240):
        xv=app.xMin + (app.xMax-app.xMin)*i/239
        yc=gaussian(xv,app.ctrlMean,app.ctrlSD); ye=gaussian(xv,expMean,app.sd)
        xpix=pX(app,xv)
        ptsC.append((xpix,app.gB-yc*hScale)); ptsE.append((xpix,app.gB-ye*hScale))
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
    drawCircle(cx,app.gT+16,10,fill=rgb(45,90,210),border=rgb(255,255,255),borderWidth=3)
    drawCircle(ex,app.gT+16,10,fill=rgb(200,35,35),border=rgb(255,255,255),borderWidth=3)
    drawLabel(f"CONTROL {app.ctrlMean:.0f} σ={app.ctrlSD:.0f}",cx,app.gT-6,size=14,bold=True,fill=rgb(45,90,210))
    drawLabel(f"DRUG {expMean:.1f} σ={app.sd:.0f}",ex,app.gT-6,size=14,bold=True,fill=rgb(200,35,35))
    drawLine(ex,app.gB-34,cx,app.gB-34,fill=rgb(20,20,20),lineWidth=3,arrowStart=True,arrowEnd=True)
    drawLabel(f"RAW DIFFERENCE = {app.rawDiff:.1f} mmHg",(ex+cx)/2,app.gB-56,size=15,bold=True,fill=rgb(20,20,20))
    cardY=462; cardH=226
    drawRect(18,cardY,322,cardH,fill=rgb(255,255,255),border=rgb(190,200,215),borderWidth=1,roundness=12)
    drawLabel("Effect Size (the real question)",32,cardY+18,size=13,bold=True,fill=rgb(20,20,30),align='left')
    drawLabel(f"d = {app.rawDiff:.1f}/{app.sd:.1f} = {d:.3f}",32,cardY+42,size=20,bold=True,align='left')
    interp="negligible" if abs(d)<0.2 else "small" if abs(d)<0.5 else "medium" if abs(d)<0.8 else "LARGE"
    drawLabel(f"{interp} (0.2/0.5/0.8 ≠ law)",32,cardY+68,size=13,fill=rgb(60,60,70),align='left')
    drawLabel(f"Hedges g={g:.3f} J={J:.4f}",32,cardY+94,size=12,bold=True,fill=rgb(70,50,100),align='left')
    drawLabel(f"Glass Δ={delta:.3f} {'[ON]' if app.useGlass else '[OFF G]'}",32,cardY+114,size=12,bold=True,fill=rgb(120,70,15),align='left')
    drawLabel("Use Δ when treatment explodes variance",32,cardY+132,size=11,fill=rgb(100,80,50),align='left')
    drawLabel("Cohen warned: benchmarks ≠ law!",32,cardY+152,size=11,bold=True,align='left')
    drawLabel("Context decides if effect matters.",32,cardY+170,size=11,align='left')
    drawRect(364,cardY,322,cardH,fill=rgb(255,245,248),border=rgb(230,170,185),borderWidth=1,roundness=12)
    drawLabel("P-VALUE ILLUSION",378,cardY+18,size=13,bold=True,fill=rgb(150,25,55),align='left')
    drawLabel(f"n = {app.n:,} per group",378,cardY+42,size=14,bold=True,align='left')
    drawLabel(f"t ≈ d·√(n/2) = {t:.2f}",378,cardY+66,size=14,align='left')
    pCol=rgb(0,140,0) if p<0.05 else rgb(180,30,30)
    drawLabel(f"p ≈ {p}",378,cardY+94,size=28,bold=True,fill=pCol,align='left')
    drawLabel(f"{'→ SIGNIFICANT!' if p<0.05 else '→ NOT significant'}",378,cardY+122,size=14,bold=True,fill=pCol,align='left')
    drawLabel("With n=50k, d=0.08 → p<0.05",378,cardY+148,size=12,fill=rgb(120,40,50),align='left')
    drawLabel("P = engine on? d = >5 mph?",378,cardY+168,size=12,bold=True,align='left')
    drawRect(710,cardY,322,cardH,fill=rgb(242,252,242),border=rgb(160,200,160),borderWidth=1,roundness=12)
    drawLabel("CLINICAL CONTEXT",724,cardY+18,size=13,bold=True,fill=rgb(25,90,25),align='left')
    if app.rawDiff <= 1.5:
        drawLabel(f"d={d:.2f} → 1 mmHg drop",724,cardY+44,size=13,align='left')
        drawLabel("Saves ~0 lives.",724,cardY+64,size=14,bold=True,fill=rgb(180,30,30),align='left')
        drawLabel("Math sig, clinically USELESS.",724,cardY+106,size=13,bold=True,fill=rgb(180,30,30),align='left')
    elif app.rawDiff < 6:
        drawLabel(f"d={d:.2f} small, millions→matters",724,cardY+44,size=13,align='left')
        drawLabel("0.2 mortality = thousands saved",724,cardY+90,size=12,bold=True,align='left')
    else:
        drawLabel(f"d={d:.2f} MEDIUM/LARGE",724,cardY+44,size=14,bold=True,align='left')
        drawLabel(f"{app.rawDiff:.0f} mmHg prevents strokes",724,cardY+68,size=13,align='left')
        drawLabel("Context > benchmarks!",724,cardY+92,size=12,bold=True,align='left')
    drawLabel("Fun video d=0.8 = trivial.",724,cardY+148,size=11,fill=rgb(80,80,80),align='left')
    drawLabel("Mortality d=0.2 = massive.",724,cardY+164,size=11,bold=True,fill=rgb(80,80,80),align='left')
