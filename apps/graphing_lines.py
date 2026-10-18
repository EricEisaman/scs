from scs import *
import random

C_BG=rgb(11,14,20); C_PANEL=rgb(22,26,36); C_PANEL2=rgb(32,38,52)
C_GRID=rgb(48,54,70); C_AXES=rgb(180,190,210)
C_BLUE=rgb(90,160,255); C_ORANGE=rgb(255,140,60)
C_TEXT=rgb(230,235,245); C_TEXT_DIM=rgb(145,155,175)
C_GOOD=rgb(0,220,120)

def drawRoundedRect(x, y, width, height, radius, fill, align='center'):
    if align == 'center':
        x = x - width/2
        y = y - height/2
    r = max(0, min(radius, width/2, height/2))
    if r == 0:
        drawRect(x, y, width, height, fill=fill)
        return
    if width > 2 * r:
        drawRect(x + r, y, width - 2 * r, height, fill=fill)
    if height > 2 * r:
        drawRect(x, y + r, width, height - 2 * r, fill=fill)
    for cx in (x + r, x + width - r):
        for cy in (y + r, y + height - r):
            drawCircle(cx, cy, r, fill=fill)

def onAppStart(app):
    app.xMin,app.xMax=-10,10; app.yMin,app.yMax=-10,10
    app.gLeft,app.gTop,app.gW,app.gH=30,30,640,640
    app.snap=True; app.mode='build'
    app.dragging=None; app.selectedField='m'
    app.attemptM=0; app.attemptB=0; app.attemptX1=0; app.attemptY1=0
    app.buildCorrect=False; app.formulaCorrect=False
    app.feedback=''; app.feedbackColor=C_TEXT
    # generate both targets but end with feedback for current mode
    generateFormulaTarget(app)
    generateBuildTarget(app)
    checkBuild(app)

def generateBuildTarget(app):
    app.buildForm = random.choice(['slope','point'])
    if app.buildForm == 'point':
        for _ in range(100):
            app.buildM = random.choice([-2,-1,1,2])
            app.buildX1 = random.randint(-8,8)
            app.buildY1 = random.randint(-8,8)
            app.buildB = app.buildY1 - app.buildM*app.buildX1
            if -10 <= app.buildB <= 10:
                break
    else:
        app.buildM = random.choice([-2,-1.5,-1,-0.5,0.5,1,1.5,2])
        app.buildB = random.randint(-6,6)
        for _ in range(100):
            app.buildX1 = random.randint(-8,8)
            app.buildY1 = app.buildM*app.buildX1 + app.buildB
            if -10 <= app.buildY1 <= 10:
                break
    app.userP1=[-4,1]; app.userP2=[4,3]
    app.buildCorrect=False
    # only set this message when we are actually in build mode
    if app.mode=='build':
        app.feedback='Drag P1 & P2 to match the equation'
        app.feedbackColor=C_TEXT

def generateFormulaTarget(app):
    app.fM = random.choice([-3,-2,-1,1,2,3])
    app.fB = random.randint(-5,5)
    for _ in range(100):
        x1 = random.randint(-8,2)
        x2 = random.randint(2,8)
        y1 = app.fM*x1 + app.fB
        y2 = app.fM*x2 + app.fB
        if -10 <= x1 <= 10 and -10 <= y1 <= 10 and -10 <= y2 <= 10:
            break
    app.fP1=[x1,y1]; app.fP2=[x2,y2]
    app.attemptM=0; app.attemptB=0; app.attemptX1=x1; app.attemptY1=y1
    app.formulaCorrect=False
    if app.mode=='formula':
        app.feedback='Find m, b and a point on this line'
        app.feedbackColor=C_TEXT

def mathToPixel(app,mx,my):
    px=app.gLeft+(mx-app.xMin)/(app.xMax-app.xMin)*app.gW
    py=app.gTop+app.gH-(my-app.yMin)/(app.yMax-app.yMin)*app.gH
    return px,py
def pixelToMath(app,px,py):
    mx=app.xMin+(px-app.gLeft)/app.gW*(app.xMax-app.xMin)
    my=app.yMin+(app.gTop+app.gH-py)/app.gH*(app.yMax-app.yMin)
    if app.snap: mx=round(mx); my=round(my)
    return mx,my
def getMB(p1,p2):
    dx=p2[0]-p1[0]
    if abs(dx)<0.001: return None,None
    m=(p2[1]-p1[1])/dx; b=p1[1]-m*p1[0]; return m,b
def dist(x1,y1,x2,y2): return ((x1-x2)**2 + (y1-y2)**2)**0.5

def checkBuild(app):
    um,ub=getMB(app.userP1,app.userP2)
    if um is None:
        app.buildCorrect=False
        return False
    ok = abs(um-app.buildM)<0.2 and abs(ub-app.buildB)<0.5
    app.buildCorrect = ok
    if app.mode=='build':
        if ok:
            app.feedback='✓ Perfect! New equation?'
            app.feedbackColor=C_GOOD
        else:
            app.feedback='Drag P1 & P2 to match the equation'
            app.feedbackColor=C_TEXT
    return ok

def drawGrid(app):
    for i in range(app.xMin, app.xMax+1):
        x,_=mathToPixel(app,i,0)
        drawLine(x,app.gTop,x,app.gTop+app.gH, fill=C_GRID)
        drawLabel(str(i), x, app.gTop+app.gH+14, fill=C_TEXT_DIM, size=12)
    for j in range(app.yMin, app.yMax+1):
        _,y=mathToPixel(app,0,j)
        drawLine(app.gLeft,y,app.gLeft+app.gW,y, fill=C_GRID)
        if j!=0: drawLabel(str(j), app.gLeft-16, y, fill=C_TEXT_DIM, size=12)
    ox,_=mathToPixel(app,0,0); _,oy=mathToPixel(app,0,0)
    drawLine(app.gLeft,oy,app.gLeft+app.gW,oy, fill=C_AXES, lineWidth=2)
    drawLine(ox,app.gTop,ox,app.gTop+app.gH, fill=C_AXES, lineWidth=2)

def drawLineMath(app,m,b,color,w=3,dashes=False, opacity=100):
    if m is None: return
    prev=None
    for xi in range(app.xMin*30, app.xMax*30+1):
        x=xi/30; y=m*x+b
        if app.yMin-1<=y<=app.yMax+1:
            px,py=mathToPixel(app,x,y)
            if prev: drawLine(prev[0],prev[1],px,py, fill=color, lineWidth=w, dashes=dashes, opacity=opacity)
            prev=(px,py)
        else: prev=None

def redrawAll(app):
    drawRect(1050/2,700/2,1050,700,fill=C_BG,align='center')
    drawRect(875,350,350,700,fill=C_PANEL,align='center')
    drawGrid(app)

    um,ub=getMB(app.userP1,app.userP2)
    buildIsCorrect = False
    if app.mode=='build' and um is not None:
        buildIsCorrect = abs(um-app.buildM)<0.2 and abs(ub-app.buildB)<0.5

    if (app.mode=='build' and (buildIsCorrect or app.buildCorrect)) or (app.mode=='formula' and app.formulaCorrect):
        drawRect(350,350,660,660,fill=C_GOOD, opacity=10, align='center')
        drawRect(350,350,674,674,fill=None, border=C_GOOD, borderWidth=5, align='center')

    if app.mode=='build':
        if um is not None:
            drawLineMath(app,um,ub,C_BLUE,4)
        for p,c in [(app.userP1,C_ORANGE),(app.userP2,C_BLUE)]:
            px,py=mathToPixel(app,p[0],p[1])
            drawCircle(px,py,12, fill=C_PANEL, border=c, borderWidth=3)
            drawCircle(px,py,5, fill=c)

        if app.buildForm=='slope':
            drawLabel(f'TARGET (slope-intercept):', 350,20, fill=C_ORANGE, size=15, bold=True)
            drawLabel(f'y = {app.buildM} x + {app.buildB}', 350,48, fill=C_ORANGE, size=22, bold=True)
        else:
            drawLabel(f'TARGET (point-slope):', 350,20, fill=C_ORANGE, size=15, bold=True)
            drawLabel(f'y - {app.buildY1} = {app.buildM}(x - {app.buildX1})', 350,48, fill=C_ORANGE, size=20, bold=True)

        if buildIsCorrect or app.buildCorrect:
            drawLabel('✓ CORRECT!', app.gLeft+20, app.gTop+app.gH-20, fill=C_GOOD, size=20, bold=True, align='left')

    else:
        drawLineMath(app,app.fM,app.fB,C_BLUE,5)
        drawLabel('Write the equation for this line', 350,22, fill=C_BLUE, size=16, bold=True)
        drawLabel(f'y = {app.attemptM} x + {app.attemptB}', 875,268, fill=C_BLUE, size=18, bold=True)
        drawLabel(f'y - {app.attemptY1} = {app.attemptM}(x - {app.attemptX1})', 875,295, fill=C_ORANGE, size=15, bold=True)
        if app.formulaCorrect:
            drawLabel('✓ CORRECT!', app.gLeft+20, app.gTop+app.gH-20, fill=C_GOOD, size=20, bold=True, align='left')

    drawRect(875,102,320,48,fill=rgb(32,38,52), align='center')
    drawLabel('SNAP TO INTEGER', 735,102, fill=C_TEXT_DIM, size=14, align='left')
    drawLabel('ON' if app.snap else 'OFF', 880,103, fill=C_ORANGE if app.snap else C_TEXT_DIM, size=13, bold=True)
    drawRoundedRect(960,103,56,24,12, C_BLUE if app.snap else C_GRID, align='center')
    drawCircle(932+ (44 if app.snap else 12),103,9, fill='white')

    drawRect(875,165,320,58,fill=rgb(32,38,52), align='center')
    drawRoundedRect(800,165,142,38,7, C_BLUE if app.mode=='build' else C_PANEL, align='center')
    drawRoundedRect(950,165,142,38,7, C_BLUE if app.mode=='formula' else C_PANEL, align='center')
    drawLabel('BUILD GRAPH', 800,165, fill=C_TEXT, size=13, bold=True)
    drawLabel('WRITE FORMULA', 950,165, fill=C_TEXT, size=13, bold=True)

    if app.mode=='build':
        drawLabel('Mode 1: Equation -> Graph',875,222, fill=C_ORANGE, size=15, bold=True)
        drawLabel(app.feedback,875,305, fill=app.feedbackColor, size=16, bold=True)
        drawRoundedRect(875,350,240,42,9, C_ORANGE, align='center')
        drawLabel('NEW EQUATION [N]',875,350, fill='black', size=14, bold=True)
    else:
        drawLabel('Mode 2: Graph -> Equation',875,222, fill=C_BLUE, size=15, bold=True)
        y0=320
        for i,key in enumerate(['m','b','x1','y1']):
            val = {'m':app.attemptM,'b':app.attemptB,'x1':app.attemptX1,'y1':app.attemptY1}[key]
            sel = app.selectedField==key
            drawRoundedRect(810,y0+i*50,160,38,7, rgb(45,60,90) if sel else C_BG, align='center')
            drawLabel(f'{key} = {val}', 735, y0+i*50, fill=C_ORANGE if sel else C_TEXT, size=15, align='left', bold=sel)
            drawRect(905,y0+i*50-10,32,18,fill=rgb(32,38,52), align='center')
            drawRect(905,y0+i*50+10,32,18,fill=rgb(32,38,52), align='center')
            drawLabel('^',905,y0+i*50-10, fill=C_TEXT_DIM, size=12)
            drawLabel('v',905,y0+i*50+10, fill=C_TEXT_DIM, size=12)
        drawRoundedRect(875,545,240,44,9, C_BLUE, align='center')
        drawLabel('CHECK [C]',875,545, fill='white', size=15, bold=True)
        drawLabel(app.feedback,875,580, fill=app.feedbackColor, size=14)
        if app.formulaCorrect:
            drawRoundedRect(875,620,240,40,9, C_GOOD, align='center')
            drawLabel('NEW GRAPH [N]',875,620, fill='black', size=14, bold=True)
        else:
            drawRoundedRect(875,620,240,40,9, C_PANEL2, align='center')
            drawLabel('NEW GRAPH [N]',875,620, fill=C_TEXT, size=14, bold=True)

def onMousePress(app,mx,my):
    if 932<=mx<=988 and 92<=my<=114: app.snap=not app.snap; return
    if 730<=mx<=872 and 145<=my<=185:
        app.mode='build'
        checkBuild(app)
        return
    if 878<=mx<=1022 and 145<=my<=185:
        app.mode='formula'
        app.feedback='Find m, b and a point on this line'
        app.feedbackColor=C_TEXT
        app.formulaCorrect=False
        return
    if app.mode=='build' and 755<=mx<=995 and 329<=my<=371: generateBuildTarget(app); return
    if app.mode=='formula' and 755<=mx<=995 and 523<=my<=567:
        mOk = abs(app.attemptM-app.fM)<0.01
        bOk = abs(app.attemptB-app.fB)<0.01
        pointOnLine = abs(app.attemptY1 - (app.fM*app.attemptX1 + app.fB))<0.01
        pointMatchesOwn = abs(app.attemptY1 - (app.attemptM*app.attemptX1 + app.attemptB))<0.01
        if mOk and bOk and pointOnLine and pointMatchesOwn:
            app.formulaCorrect=True
            app.feedback='✓ Both forms correct!'; app.feedbackColor=C_GOOD
        else:
            app.formulaCorrect=False
            if not mOk:
                app.feedback='Slope m is off'; app.feedbackColor=rgb(255,120,120)
            elif not bOk:
                app.feedback='Intercept b is off'; app.feedbackColor=rgb(255,120,120)
            elif not pointOnLine:
                app.feedback='Point (x1,y1) not on line'; app.feedbackColor=rgb(255,120,120)
            else:
                app.feedback='Point does not match your m & b'; app.feedbackColor=rgb(255,120,120)
        return
    if app.mode=='formula' and 755<=mx<=995 and 600<=my<=640:
        generateFormulaTarget(app); return
    if app.mode=='build':
        for i,p in enumerate([app.userP1,app.userP2]):
            px,py=mathToPixel(app,p[0],p[1])
            if dist(mx,my,px,py)<22: app.dragging=i; return
    if app.mode=='formula':
        y0=320
        for i,key in enumerate(['m','b','x1','y1']):
            if 730<=mx<=890 and y0+i*50-19<=my<=y0+i*50+19: app.selectedField=key; return
            if 889<=mx<=921:
                if y0+i*50-19<=my<=y0+i*50-1:
                    if key=='m': app.attemptM+=1
                    elif key=='b': app.attemptB+=1
                    elif key=='x1': app.attemptX1+=1
                    else: app.attemptY1+=1
                    return
                if y0+i*50+1<=my<=y0+i*50+19:
                    if key=='m': app.attemptM-=1
                    elif key=='b': app.attemptB-=1
                    elif key=='x1': app.attemptX1-=1
                    else: app.attemptY1-=1
                    return

def onMouseDrag(app,mx,my):
    if app.dragging is not None and app.mode=='build':
        nmx,nmy=pixelToMath(app,mx,my)
        if app.dragging==0: app.userP1=[nmx,nmy]
        else: app.userP2=[nmx,nmy]
        checkBuild(app)

def onMouseRelease(app,mx,my):
    app.dragging=None
    if app.mode=='build': checkBuild(app)

def onKeyPress(app,key):
    if key=='n' and app.mode=='build': generateBuildTarget(app)
    if key=='n' and app.mode=='formula': generateFormulaTarget(app)
    if key=='c' and app.mode=='formula': onMousePress(app,875,545)
    if app.mode=='formula' and app.selectedField:
        if key=='up':
            if app.selectedField=='m': app.attemptM+=1
            elif app.selectedField=='b': app.attemptB+=1
            elif app.selectedField=='x1': app.attemptX1+=1
            else: app.attemptY1+=1
        if key=='down':
            if app.selectedField=='m': app.attemptM-=1
            elif app.selectedField=='b': app.attemptB-=1
            elif app.selectedField=='x1': app.attemptX1-=1
            else: app.attemptY1-=1

def main():
    runApp(1050,700)
    
main()
