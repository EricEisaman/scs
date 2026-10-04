"""
Edward Little High - Buss & Sigma Scholars
SWLA Deep Dive: Visualizing the Memory Crisis
1050x700 - CMU CPCS Sandbox (cmu_graphics)
FINAL FIXED - all crash guards + layout 10px adjustments
"""
from scs import *
import random

def fit_line(points):
    if len(points) < 2:
        return (0, points[0][1] if points else 0) if points else (0,0)
    n = len(points)
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    sum_xy = sum(p[0]*p[1] for p in points)
    sum_x2 = sum(p[0]*p[0] for p in points)
    denom = n*sum_x2 - sum_x*sum_x
    if abs(denom) < 1e-6:
        return (0, sum_y/n)
    m = (n*sum_xy - sum_x*sum_y) / denom
    b = (sum_y - m*sum_x)/n
    return (m,b)

def line_error(m,b, pt):
    return abs((m*pt[0]+b)-pt[1])

def generate_initial_clusters():
    pts=[]
    for _ in range(18):
        x=random.uniform(20,150); y=0.8*x+10+random.uniform(-12,12); pts.append((x,y,0))
    for _ in range(18):
        x=random.uniform(80,220); y=-0.6*x+220+random.uniform(-12,12); pts.append((x,y,1))
    for _ in range(18):
        x=random.uniform(30,230); y=0.15*x+130+random.uniform(-10,10); pts.append((x,y,2))
    random.shuffle(pts)
    return pts

def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=30
    app.L=32; app.H=32; app.D=128; app.J=4; app.bytesPer=2
    app.T=0; app.maxT=64; app.tokens=[]
    app.vocab=["hakuna","matata","the","context","is","long","remember","page","three","book","AI","memory","token"]
    app.cue="hakuna"; app.target="matata"
    app.memoryCapGB=32; app.linearGB=0.25; app.swlaGB=0.25+app.J*0.12
    app.focus=0; app.auto=True; app.stepCounter=0; app.oom=False; app.oomShake=0
    app.regPoints=generate_initial_clusters()
    app.singleLine=(0,0)
    app.expertLines=[(0.7,20),(-0.5,200),(0.1,120),(1.2,-20)]
    app.assignments=[]; app.activeExpert=0
    app.recallScores={"softmax":1.0,"linear":1.0,"swla":1.0}
    app.hudMessage="SPACE=token A=auto 1/2/3=focus C=clear Click plot"
    recomputeLines(app)
    app.softmaxGB_visual=0

def add_random_token(app):
    if app.oom: return
    tok=app.cue if (random.random()<0.3 and app.T%3==0 and len(app.tokens)%2==0) else random.choice(app.vocab)
    if random.random()<0.3 and app.T%3==1: tok=app.target
    app.tokens.append(tok); app.T+=1
    app.softmaxGB_visual=min(40, app.T*0.55)
    if app.softmaxGB_visual>=app.memoryCapGB:
        app.oom=True; app.oomShake=15
    app.recallScores["softmax"]=0.0 if app.oom else 1.0
    app.recallScores["linear"]=max(0.05, 1.0-(app.T*0.018)-(app.T**1.5)*0.0005)
    app.recallScores["swla"]=max(0.65, 1.0-(app.T*0.004))
    new_x=random.uniform(20,230)
    if tok in (app.cue,app.target):
        true_y=0.8*new_x+15+random.uniform(-8,8)
    else:
        c=random.randint(0,2)
        if c==0: true_y=0.8*new_x+10+random.uniform(-10,10)
        elif c==1: true_y=-0.6*new_x+220+random.uniform(-10,10)
        else: true_y=0.15*new_x+130+random.uniform(-10,10)
    app.regPoints.append((new_x,true_y,0))
    if len(app.regPoints)>90: app.regPoints.pop(0)
    recomputeLines(app)
    app.activeExpert=min(range(app.J), key=lambda j: line_error(app.expertLines[j][0],app.expertLines[j][1],(new_x,true_y)))

def onStep(app):
    app.stepCounter+=1
    if app.oomShake>0: app.oomShake-=1
    if app.auto and app.stepCounter%8==0 and not app.oom and app.T<app.maxT:
        add_random_token(app)

def redrawAll(app):
    drawRect(0,0,app.width,app.height, fill=rgb(14,14,20))
    drawRect(0,0,app.width,52, fill=rgb(22,22,30), border=rgb(40,40,55))
    drawLabel("The Memory Crisis: Softmax vs Linear vs SWLA (Stanford)",18,12,size=17,fill="white",bold=True,align="left-top")
    drawLabel(f"O(2·L·H·D_head·T) L={app.L} H={app.H} D={app.D} T={app.T}/{app.maxT} J={app.J} | {app.hudMessage}",18,30,size=11,fill=rgb(170,170,185),align="left-top")
    colW=340; gap=15; startX=10
    for i,(name,color) in enumerate([("SOFTMAX ATTENTION",rgb(255,90,90)),("LINEAR ATTENTION",rgb(90,200,255)),("SWLA - SWITCHING LINEAR",rgb(90,255,160))]):
        x=startX+i*(colW+gap)
        cardH=470
        drawRect(x,60,colW,cardH,fill=rgb(28,28,38),border=rgb(50,50,65),borderWidth=1)
        drawRect(x,60,colW,32,fill=color,opacity=22)
        drawLabel(name,x+12,68,size=12,bold=True,fill=color,align="left-top")
        memVal=app.softmaxGB_visual if i==0 else app.linearGB if i==1 else app.swlaGB
        memText=f"{memVal:.1f} / {app.memoryCapGB} GB" if i==0 and not app.oom else "OOM! CRASH" if i==0 else f"{memVal:.2f} GB O(1)" if i==1 else f"{memVal:.2f} GB O(J)"
        drawLabel(memText,x+colW-10,68,size=11,fill="white",align="right-top")
        barX,barY,barW,barH=x+12,100,colW-24,18
        drawRect(barX,barY,barW,barH,fill=rgb(18,18,26),border=rgb(60,60,75))
        fillW=min(barW,barW*(memVal/app.memoryCapGB))
        if fillW>0.5:
            drawRect(barX,barY,fillW,barH,fill=rgb(255,30,30) if i==0 and app.oom else color)
        if i==0 and app.oom:
            drawLabel("OUT OF MEMORY",barX+barW/2,barY+9,fill="white",size=11,bold=True)
        if i==0: drawSoftmaxCabinet(app,x,barY+30,colW)
        elif i==1: drawLinearWhiteboard(app,x,barY+30,colW)
        else: drawSWLAExperts(app,x,barY+30,colW)
        # FIX: recall boxes moved down 10px from -58 to -48
        meterY=60+cardH-48
        drawRect(x+12,meterY,colW-24,46,fill=rgb(22,22,32),border=rgb(50,50,65))
        score=list(app.recallScores.values())[i]
        drawLabel(f"Recall hakuna->matata: {score*100:.0f}%",x+16,meterY+6,size=10,fill=rgb(200,200,210),align="left-top")
        drawRect(x+16,meterY+22,colW-40,8,fill=rgb(35,35,45))
        recallW=(colW-40)*score
        if recallW>0.5:
            drawRect(x+16,meterY+22,recallW,8,fill=color)

    if app.oom:
        shakeX=random.uniform(-4,4) if app.oomShake>0 else 0
        drawRect(shakeX,0,app.width,app.height,fill=rgb(255,30,30),opacity=10)
        # FIX: OOM moved down 10px from 540 to 550
        drawLabel("OOM FAILURE: Filing cabinet burst through the walls! Batch size = 1, GPU melted.",app.width/2+shakeX,550,size=14,fill=rgb(255,100,100),bold=True)
    drawTokenStream(app)

def drawSoftmaxCabinet(app,x,y,w):
    drawLabel("Expanding Filing Cabinet",x+12,y+2,size=11,fill=rgb(255,180,180),bold=True,align="left-top")
    cabX=x+18; cabY=y+36; cabW=w-36
    drawRect(cabX,cabY,cabW,180,fill=rgb(45,30,30),border=rgb(80,50,50),borderWidth=1)
    for idx in range(min(app.T,18)):
        drawRect(cabX+6,cabY+6+idx*9,cabW-12,7,fill=rgb(90+idx*3,60+idx*2,60+idx*2),border=rgb(120,80,80))
    drawLabel(f"{app.T} x {app.T} = {app.T*app.T} pairwise",x+12,y+224,size=9,fill=rgb(255,140,140),align="left-top")
    gridX=x+16; gridY=y+240; n=min(12,max(2,app.T))
    if n>1:
        for r in range(n):
            for c in range(n):
                alpha=70 if r!=c else 100
                drawCircle(gridX+c*9+3,gridY+r*9+3,2.2,fill=rgb(255,90,90),opacity=alpha)

def drawLinearWhiteboard(app,x,y,w):
    drawLabel("Single Whiteboard O(1)",x+12,y+2,size=11,fill=rgb(140,200,255),bold=True,align="left-top")
    wbX=x+18; wbY=y+36; wbW=w-36; wbH=180
    drawRect(wbX,wbY,wbW,wbH,fill=rgb(235,235,228),border=rgb(60,60,70),borderWidth=2)
    noise=min(0.85,app.T*0.035)
    for r in range(6):
        for c in range(8):
            cx=wbX+10+c*(wbW-20)/8; cy=wbY+10+r*(wbH-20)/6
            gray=30+random.uniform(0,50)+noise*80
            drawRect(cx,cy,(wbW-20)/8-4,(wbH-20)/6-4,fill=rgb(gray+20,gray+20,gray+10),opacity=100-int(noise*60))
    drawLabel(f"Blur: {noise*100:.0f}%",x+12,y+224,size=9,fill=rgb(120,180,220),align="left-top")
    m,b=app.singleLine
    drawRect(x+16,y+240,w-32,50,fill=rgb(20,25,35),border=rgb(50,60,80))
    for px,py,_ in app.regPoints[-25:]:
        drawCircle(x+16+(px/250)*(w-32), y+240+50-(py/250)*50, 2, fill=rgb(90,200,255), opacity=50)
    drawLine(x+16, y+240+50-((m*0+b)/250)*50, x+16+w-32, y+240+50-((m*250+b)/250)*50, fill=rgb(90,200,255), lineWidth=2)

def drawSWLAExperts(app,x,y,w):
    drawLabel(f"J={app.J} Experts + Switching",x+12,y+2,size=11,fill=rgb(140,255,180),bold=True,align="left-top")
    wbW=(w-36-10)//2; wbH=84; startX=x+18; startY=y+36
    colors=[rgb(255,180,90),rgb(90,200,255),rgb(160,140,255),rgb(90,255,160)]
    for j in range(app.J):
        bx=startX+(j%2)*(wbW+10); by=startY+(j//2)*(wbH+8)
        isActive=j==app.activeExpert
        drawRect(bx,by,wbW,wbH,fill=rgb(245,245,238) if isActive else rgb(225,225,215),border=colors[j] if isActive else rgb(60,60,70),borderWidth=3 if isActive else 1)
        drawLabel(f"Expert {j+1}",bx+6,by+6,size=8,bold=True,fill=rgb(30,30,30),align="left-top")
        if isActive:
            drawCircle(bx+wbW-10,by+10,5,fill=colors[j])
            drawLabel("ACTIVE",bx+wbW-28,by+8,size=7,fill=colors[j],bold=True,align="left-top")
        m,b=app.expertLines[j]
        drawLine(bx+8,by+wbH-20-(m*0+b)/250*wbH*0.2,bx+wbW-8,by+wbH-20-(m*50+b)/250*wbH*0.2,fill=colors[j],lineWidth=2)
    plotX=x+18; plotY=y+36+2*(wbH+8)+10; plotW=w-36; plotH=80
    drawRect(plotX,plotY,plotW,plotH,fill=rgb(20,28,24),border=rgb(50,70,55))
    for idx,(px,py,_) in enumerate(app.regPoints[-40:]):
        assign=app.assignments[idx] if idx<len(app.assignments) else 0
        drawCircle(plotX+(px/250)*plotW,plotY+plotH-(py/250)*plotH,3.5,fill=colors[assign%4],opacity=85)
    for j,(m,b) in enumerate(app.expertLines):
        drawLine(plotX,plotY+plotH-((m*0+b)/250)*plotH,plotX+plotW,plotY+plotH-((m*250+b)/250)*plotH,fill=colors[j],lineWidth=2 if j==app.activeExpert else 1,opacity=90 if j==app.activeExpert else 45)

def drawTokenStream(app):
    y = app.height - 125
    drawRect(0, y, app.width, 62, fill=rgb(22,22,30), border=rgb(40,40,55))
    drawLabel(f"Sequence T={app.T}:",12,y+8,size=11,bold=True,fill=rgb(200,200,210),align="left-top")
    x=110
    for tok in app.tokens[-10:]:
        bg=rgb(90,200,255) if tok==app.cue else rgb(255,200,90) if tok==app.target else rgb(60,60,70)
        tw=len(tok)*7+16
        if x+tw>app.width-400: break
        drawRect(x,y+6,tw,22,fill=bg,border=rgb(90,90,100),borderWidth=1)
        drawLabel(tok,x+tw/2,y+17,size=10,fill="white",bold=tok in (app.cue,app.target))
        x+=tw+6
    drawLabel("SPACE=token A=auto R=reset 1/2/3=focus C=clear Click plot",app.width-12,y+8,size=9,fill=rgb(150,150,165),align="right-top")
    drawLabel("Edward Little High | Buss & Sigma Scholars",app.width-12,y+34,size=8,fill=rgb(120,120,135),align="right-top")

def recomputeLines(app):
    pts_xy=[(p[0],p[1]) for p in app.regPoints]
    app.singleLine=fit_line(pts_xy) if pts_xy else (0,0)
    for _ in range(3):
        assignments=[]
        for pt in app.regPoints:
            errs=[abs((m*pt[0]+b)-pt[1]) for m,b in app.expertLines]
            assignments.append(errs.index(min(errs)))
        newLines=[]
        for j in range(app.J):
            assigned=[(p[0],p[1]) for idx,p in enumerate(app.regPoints) if assignments[idx]==j]
            newLines.append(fit_line(assigned) if len(assigned)>=2 else app.expertLines[j])
        app.expertLines=newLines
    app.assignments=assignments

def onKeyPress(app,key):
    if key.lower()=='r':
        app.T=0; app.tokens=[]; app.softmaxGB_visual=0; app.oom=False; app.oomShake=0
        app.regPoints=generate_initial_clusters(); recomputeLines(app)
        for k in app.recallScores: app.recallScores[k]=1.0
    elif key==' ': add_random_token(app)
    elif key.lower()=='a': app.auto=not app.auto
    elif key in ('1','2','3','0'): app.focus=int(key) if int(key)!=app.focus else 0
    elif key.lower()=='c': app.regPoints=generate_initial_clusters(); recomputeLines(app)

def onMousePress(app,mx,my):
    colW=340; gap=15; startX=10
    x=startX+2*(colW+gap)+18; y=60+100+30+36+2*(84+8)+10; w=colW-36; h=80
    if x<=mx<=x+w and y<=my<=y+h:
        app.regPoints.append((((mx-x)/w)*250,(1-(my-y)/h)*250,0))
        recomputeLines(app)

runApp(width=1050, height=700)
