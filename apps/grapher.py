from scs import *
import math

REG_TYPES = ["Linear", "Quadratic", "Exponential", "Logarithmic", "Power", "Cubic"]

def solveLinearSystem(A, b):
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        max_row = i
        max_val = abs(M[i][i])
        for k in range(i+1, n):
            if abs(M[k][i]) > max_val:
                max_val = abs(M[k][i])
                max_row = k
        if max_val < 1e-12:
            return None
        if max_row != i:
            M[i], M[max_row] = M[max_row], M[i]
        for k in range(i+1, n):
            factor = M[k][i] / M[i][i]
            for j in range(i, n+1):
                M[k][j] -= factor * M[i][j]
    x = [0]*n
    for i in range(n-1, -1, -1):
        s = M[i][n]
        for j in range(i+1, n):
            s -= M[i][j]*x[j]
        if abs(M[i][i]) < 1e-12:
            return None
        x[i] = s / M[i][i]
    return x

def linearReg(x, y):
    n = len(x)
    if n < 2:
        return None
    sx = sum(x); sy = sum(y)
    sxx = sum(v*v for v in x)
    sxy = sum(x[i]*y[i] for i in range(n))
    denom = n*sxx - sx*sx
    if abs(denom) < 1e-12:
        return None
    m = (n*sxy - sx*sy)/denom
    b = (sy - m*sx)/n
    ymean = sy/n
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res = sum((y[i] - (m*x[i]+b))**2 for i in range(n))
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 else 0
    return {"m":m, "b":b, "r2":r2, "fn": lambda xv: m*xv+b, "eq": f"y = {m:.3g}x + {b:.3g}"}

def quadraticReg(x, y):
    n = len(x)
    if n < 3:
        return linearReg(x,y)
    sx = sum(x); sx2 = sum(v*v for v in x); sx3 = sum(v**3 for v in x); sx4 = sum(v**4 for v in x)
    sy = sum(y); sxy = sum(x[i]*y[i] for i in range(n)); sx2y = sum((x[i]**2)*y[i] for i in range(n))
    A = [[sx4, sx3, sx2],[sx3, sx2, sx],[sx2, sx, n]]
    B = [sx2y, sxy, sy]
    sol = solveLinearSystem(A,B)
    if sol is None:
        return linearReg(x,y)
    a,b,c = sol
    fn = lambda xv: a*xv*xv + b*xv + c
    ymean = sy/n
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res = sum((y[i] - fn(x[i]))**2 for i in range(n))
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 else 0
    return {"a":a,"b":b,"c":c,"r2":r2,"fn":fn,"eq": f"y = {a:.3g}x² + {b:.3g}x + {c:.3g}"}

def cubicReg(x,y):
    n = len(x)
    if n < 4:
        return quadraticReg(x,y)
    sx = sum(x); sx2 = sum(v*v for v in x); sx3 = sum(v**3 for v in x)
    sx4 = sum(v**4 for v in x); sx5 = sum(v**5 for v in x); sx6 = sum(v**6 for v in x)
    sy = sum(y); sxy = sum(x[i]*y[i] for i in range(n)); sx2y = sum((x[i]**2)*y[i] for i in range(n)); sx3y = sum((x[i]**3)*y[i] for i in range(n))
    A = [[sx6,sx5,sx4,sx3],[sx5,sx4,sx3,sx2],[sx4,sx3,sx2,sx],[sx3,sx2,sx,n]]
    B = [sx3y, sx2y, sxy, sy]
    sol = solveLinearSystem(A,B)
    if sol is None:
        return quadraticReg(x,y)
    a,b,c,d = sol
    fn = lambda xv: a*xv**3 + b*xv*xv + c*xv + d
    ymean = sy/n
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res = sum((y[i] - fn(x[i]))**2 for i in range(n))
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 else 0
    return {"a":a,"b":b,"c":c,"d":d,"r2":r2,"fn":fn,"eq": f"y = {a:.3g}x³ + {b:.3g}x² + {c:.3g}x + {d:.3g}"}

def expReg(x,y):
    fx=[]; fy=[]
    for i in range(len(x)):
        if y[i]>0:
            fx.append(x[i]); fy.append(math.log(y[i]))
    if len(fx)<2:
        return None
    lin = linearReg(fx,fy)
    if lin is None:
        return None
    b = lin["m"]; ln_a = lin["b"]; a = math.exp(ln_a)
    fn = lambda xv: a*math.exp(b*xv)
    ymean = sum(y)/len(y)
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res = sum((y[i] - fn(x[i]))**2 for i in range(len(x)))
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 else 0
    return {"a":a,"b":b,"r2":r2,"fn":fn,"eq": f"y = {a:.3g}·e^({b:.3g}x)"}

def logReg(x,y):
    fx=[]; fy=[]
    for i in range(len(x)):
        if x[i]>0:
            fx.append(math.log(x[i])); fy.append(y[i])
    if len(fx)<2:
        return None
    lin = linearReg(fx,fy)
    if lin is None:
        return None
    a = lin["m"]; b = lin["b"]
    fn = lambda xv: a*math.log(xv)+b if xv>0 else None
    ymean = sum(y)/len(y)
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res = 0
    cnt=0
    for i in range(len(x)):
        if x[i]>0:
            ss_res += (y[i] - fn(x[i]))**2
            cnt+=1
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 and cnt>0 else 0
    return {"a":a,"b":b,"r2":r2,"fn":fn,"eq": f"y = {a:.3g}·ln(x) + {b:.3g}"}

def powerReg(x,y):
    fx=[]; fy=[]
    for i in range(len(x)):
        if x[i]>0 and y[i]>0:
            fx.append(math.log(x[i])); fy.append(math.log(y[i]))
    if len(fx)<2:
        return None
    lin = linearReg(fx,fy)
    if lin is None:
        return None
    b = lin["m"]; ln_a = lin["b"]; a = math.exp(ln_a)
    fn = lambda xv: a*(xv**b) if xv>0 else None
    ymean = sum(y)/len(y)
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res=0
    for i in range(len(x)):
        if x[i]>0:
            pred = fn(x[i])
            if pred is not None:
                ss_res += (y[i]-pred)**2
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 else 0
    return {"a":a,"b":b,"r2":r2,"fn":fn,"eq": f"y = {a:.3g}·x^{b:.3g}"}

def computeReg(x,y, typ):
    if len(x)<2:
        return None
    if typ=="Linear":
        return linearReg(x,y)
    if typ=="Quadratic":
        return quadraticReg(x,y)
    if typ=="Exponential":
        return expReg(x,y)
    if typ=="Logarithmic":
        return logReg(x,y)
    if typ=="Power":
        return powerReg(x,y)
    if typ=="Cubic":
        return cubicReg(x,y)
    return linearReg(x,y)

def niceStep(v):
    if v<=0:
        return 1
    exp = math.floor(math.log10(v))
    f = v / (10**exp)
    if f <= 1.5:
        nf=1
    elif f <= 3:
        nf=2
    elif f <= 7:
        nf=5
    else:
        nf=10
    return nf * (10**exp)

def getTicks(mn,mx, maxTicks=6):
    if mn==mx:
        mn-=1; mx+=1
    rng = mx-mn
    step = niceStep(rng / maxTicks)
    start = math.floor(mn/step)*step
    end = math.ceil(mx/step)*step
    ticks=[]
    v=start
    while v <= end+1e-9:
        ticks.append(v)
        v+=step
    return ticks, step

def tryFloat(s):
    try:
        return float(str(s).strip())
    except:
        return None

def onAppStart(app):
    app.width=1050
    app.height=700
    app.stepsPerSecond=20
    app.mode='table'
    app.columns=["CO2 ppm","Temp C","Escape %","Notes"]
    app.data=[
        ["280","14.8","55","preindustrial"],
        ["400","15.5","48",""],
        ["500","16.5","38",""],
        ["600","17.8","28",""],
        ["750","19.0","18",""],
        ["900","20.5","12",""],
        ["1000","21.2","9",""],
        ["","","",""],
    ]
    app.selRow=0
    app.selCol=0
    app.editing=False
    app.editText=""
    app.scrollRow=0
    app.scrollCol=0
    app.graphXCol=0
    app.graphYCol=1
    app.showReg=True
    app.regType=0
    app.openDropdown=None

def getVisibleCounts(app):
    topBar=48
    headerH=36
    availH = app.height - topBar - headerH - 20
    nRows = len(app.data)
    if nRows <= 10:
        rowH = max(32, availH // max(1,nRows))
    else:
        rowH = 36
    maxRows = max(1, availH // rowH)
    nCols = len(app.columns)
    availW = app.width - 10
    if nCols <= 6:
        colW = availW // max(1,nCols)
    else:
        colW = 150
    maxCols = max(1, availW // colW)
    return rowH, maxRows, colW, maxCols

def getCellRect(app, r, c, rowH, colW):
    topBar=48
    headerH=36
    x = 5 + (c - app.scrollCol)*colW
    y = topBar + headerH + (r - app.scrollRow)*rowH
    return x,y,colW,rowH

def getHeaderRect(app, c, colW):
    topBar=48
    x = 5 + (c - app.scrollCol)*colW
    y = topBar
    return x,y,colW,36

def getGraphData(app):
    xVals=[]; yVals=[]
    if app.graphXCol >= len(app.columns) or app.graphYCol >= len(app.columns):
        return [],[]
    for row in app.data:
        if app.graphXCol < len(row) and app.graphYCol < len(row):
            xv = tryFloat(row[app.graphXCol])
            yv = tryFloat(row[app.graphYCol])
            if xv is not None and yv is not None:
                if math.isfinite(xv) and math.isfinite(yv):
                    xVals.append(xv); yVals.append(yv)
    return xVals, yVals

def onMousePress(app,mx,my):
    topBar=48
    if 10 <= mx <= 110 and 8 <= my <= 40:
        app.mode='table'
        app.openDropdown=None
        return
    if 120 <= mx <= 220 and 8 <= my <= 40:
        app.mode='graph'
        app.openDropdown=None
        return
    if app.mode=='table':
        if 260 <= mx <= 340 and 8 <= my <= 40:
            app.data.append(["" for _ in range(len(app.columns))])
            return
        if 350 <= mx <= 440 and 8 <= my <= 40:
            app.columns.append(f"Col {len(app.columns)+1}")
            for row in app.data:
                row.append("")
            return
        if 450 <= mx <= 530 and 8 <= my <= 40:
            if len(app.data)>1 and 0 <= app.selRow < len(app.data):
                app.data.pop(app.selRow)
                app.selRow = max(0, min(app.selRow, len(app.data)-1))
            return
        if 540 <= mx <= 630 and 8 <= my <= 40:
            if len(app.columns)>1 and 0 <= app.selCol < len(app.columns):
                idx=app.selCol
                app.columns.pop(idx)
                for row in app.data:
                    if idx < len(row):
                        row.pop(idx)
                app.selCol = max(0, min(app.selCol, len(app.columns)-1))
                app.graphXCol = min(app.graphXCol, len(app.columns)-1)
                app.graphYCol = min(app.graphYCol, len(app.columns)-1)
            return
        if 640 <= mx <= 700 and 8 <= my <= 40:
            for r in range(len(app.data)):
                for c in range(len(app.columns)):
                    if c < len(app.data[r]):
                        app.data[r][c]=""
            return
        if 710 <= mx <= 830 and 8 <= my <= 40:
            app.columns=["CO2 ppm","Temp C","Escape %","Notes"]
            app.data=[
                ["280","14.8","55","preindustrial"],
                ["400","15.5","48",""],
                ["500","16.5","38",""],
                ["600","17.8","28",""],
                ["750","19.0","18",""],
                ["900","20.5","12",""],
                ["1000","21.2","9",""],
                ["","","",""],
            ]
            return
        rowH, maxRows, colW, maxCols = getVisibleCounts(app)
        headerH=36
        if topBar <= my <= topBar+headerH:
            for c in range(app.scrollCol, min(len(app.columns), app.scrollCol+maxCols)):
                x,y,w,h = getHeaderRect(app,c,colW)
                if x <= mx <= x+w:
                    if app.selRow==-1 and app.selCol==c and app.editing:
                        pass
                    else:
                        if app.selRow==-1 and app.selCol==c:
                            app.editing=True
                            app.editText=str(app.columns[c])
                        else:
                            app.selRow=-1
                            app.selCol=c
                            app.editing=False
                    return
        if my > topBar+headerH:
            for r in range(app.scrollRow, min(len(app.data), app.scrollRow+maxRows)):
                for c in range(app.scrollCol, min(len(app.columns), app.scrollCol+maxCols)):
                    x,y,w,h = getCellRect(app,r,c,rowH,colW)
                    if x <= mx <= x+w and y <= my <= y+h:
                        if app.selRow==r and app.selCol==c and not app.editing:
                            app.editing=True
                            app.editText=str(app.data[r][c] if c < len(app.data[r]) else "")
                        else:
                            app.selRow=r
                            app.selCol=c
                            app.editing=False
                        return
            app.editing=False
    else:
        if 20 <= mx <= 250 and 120 <= my <= 152:
            app.openDropdown='xcol' if app.openDropdown!='xcol' else None
            return
        if 20 <= mx <= 250 and 190 <= my <= 222:
            app.openDropdown='ycol' if app.openDropdown!='ycol' else None
            return
        if 20 <= mx <= 250 and 310 <= my <= 342 and app.showReg:
            app.openDropdown='reg' if app.openDropdown!='reg' else None
            return
        if 20 <= mx <= 40 and 260 <= my <= 280:
            app.showReg = not app.showReg
            return
        if app.openDropdown=='xcol':
            for i, colName in enumerate(app.columns):
                iy = 152 + (i+1)*30
                if 20 <= mx <= 250 and iy <= my <= iy+28:
                    app.graphXCol=i
                    app.openDropdown=None
                    return
            app.openDropdown=None
            return
        if app.openDropdown=='ycol':
            for i, colName in enumerate(app.columns):
                iy = 222 + (i+1)*30
                if 20 <= mx <= 250 and iy <= my <= iy+28:
                    app.graphYCol=i
                    app.openDropdown=None
                    return
            app.openDropdown=None
            return
        if app.openDropdown=='reg':
            for i, rt in enumerate(REG_TYPES):
                iy = 342 + (i+1)*30
                if 20 <= mx <= 250 and iy <= my <= iy+28:
                    app.regType=i
                    app.openDropdown=None
                    return
            app.openDropdown=None
            return

def onKeyPress(app,key):
    if app.editing:
        if key=='enter' or key=='tab':
            if app.selRow==-1:
                if 0 <= app.selCol < len(app.columns):
                    app.columns[app.selCol]=app.editText.strip() or f"Col {app.selCol+1}"
            else:
                if 0 <= app.selRow < len(app.data) and 0 <= app.selCol < len(app.columns):
                    while len(app.data[app.selRow]) <= app.selCol:
                        app.data[app.selRow].append("")
                    app.data[app.selRow][app.selCol]=app.editText
            app.editing=False
            app.editText=""
            if key=='tab':
                app.selCol+=1
                if app.selCol >= len(app.columns):
                    app.selCol=0
                    app.selRow+=1
                    if app.selRow >= len(app.data):
                        app.data.append(["" for _ in range(len(app.columns))])
        elif key=='escape':
            app.editing=False
            app.editText=""
        elif key=='backspace':
            app.editText = app.editText[:-1]
        elif len(key)==1:
            if len(app.editText)<40:
                app.editText+=key
        return
    else:
        if app.mode=='table':
            if key=='up':
                app.selRow = max(0, app.selRow-1)
                if app.selRow < app.scrollRow:
                    app.scrollRow = app.selRow
            elif key=='down':
                app.selRow = min(len(app.data)-1, app.selRow+1)
                rowH, maxRows, _, _ = getVisibleCounts(app)
                if app.selRow >= app.scrollRow+maxRows:
                    app.scrollRow = app.selRow - maxRows +1
            elif key=='left':
                app.selCol = max(0, app.selCol-1)
                if app.selCol < app.scrollCol:
                    app.scrollCol = app.selCol
            elif key=='right':
                app.selCol = min(len(app.columns)-1, app.selCol+1)
                _, _, _, maxCols = getVisibleCounts(app)
                if app.selCol >= app.scrollCol+maxCols:
                    app.scrollCol = app.selCol - maxCols +1
            elif key=='enter':
                app.editing=True
                if app.selRow==-1:
                    app.editText=str(app.columns[app.selCol])
                else:
                    app.editText=str(app.data[app.selRow][app.selCol] if app.selCol < len(app.data[app.selRow]) else "")
            elif key=='backspace' or key=='delete':
                if app.selRow>=0:
                    if app.selCol < len(app.data[app.selRow]):
                        app.data[app.selRow][app.selCol]=""
            elif key=='tab':
                app.selCol+=1
                if app.selCol >= len(app.columns):
                    app.selCol=0
                    app.selRow+=1
                    if app.selRow >= len(app.data):
                        app.data.append(["" for _ in range(len(app.columns))])

def redrawAll(app):
    drawRect(0,0,app.width,app.height, fill=rgb(245,247,251))
    drawRect(0,0,app.width,48, fill=rgb(22,28,45))
    def drawTopBtn(x,label,active):
        fill = rgb(65,85,135) if active else rgb(42,48,68)
        border = rgb(110,140,220) if active else rgb(60,65,85)
        drawRect(x,8,100,32, fill=fill, border=border, borderWidth=1.5)
        drawLabel(label, x+50, 24, size=12, bold=True, fill=rgb(255,255,255))
    drawTopBtn(10,"TABLE", app.mode=='table')
    drawTopBtn(120,"GRAPH", app.mode=='graph')
    
    if app.mode=='table':
        def smallBtn(x,lab):
            drawRect(x,8,80,32, fill=rgb(38,44,64), border=rgb(70,80,110), borderWidth=1)
            drawLabel(lab, x+40, 24, size=11, bold=False, fill=rgb(210,220,240))
        smallBtn(260,"+ Row")
        smallBtn(350,"+ Col")
        smallBtn(450,"- Row")
        smallBtn(540,"- Col")
        drawRect(640,8,60,32, fill=rgb(38,44,64), border=rgb(70,80,110), borderWidth=1)
        drawLabel("Clear", 670,24, size=11, fill=rgb(210,220,240))
        drawRect(710,8,120,32, fill=rgb(90,70,40), border=rgb(180,150,90), borderWidth=1)
        drawLabel("Load Example", 770,24, size=11, bold=True, fill=rgb(255,235,150))

        rowH, maxRows, colW, maxCols = getVisibleCounts(app)
        topBar=48
        headerH=36
        drawRect(0,topBar,app.width,headerH, fill=rgb(235,238,245), border=rgb(200,205,220), borderWidth=1)
        for c in range(app.scrollCol, min(len(app.columns), app.scrollCol+maxCols)):
            x,y,w,h = getHeaderRect(app,c,colW)
            isSel = (app.selCol==c and app.selRow==-1)
            fill = rgb(200,215,250) if isSel else rgb(235,238,245)
            drawRect(x,y,w,h, fill=fill, border=rgb(180,185,200), borderWidth=1)
            fSize = max(10, min(13, int(colW/10)))
            txt = app.columns[c]
            if len(txt)*fSize*0.6 > w-10:
                txt = txt[:int((w-10)/(fSize*0.6))]+"…"
            drawLabel(txt, x+w/2, y+h/2, size=fSize, bold=True, fill=rgb(30,35,55))
            if isSel and app.editing:
                drawRect(x+3,y+3,w-6,h-6, fill=rgb(255,255,255), border=rgb(80,120,220), borderWidth=2)
                drawLabel(app.editText+"|", x+8, y+h/2, size=fSize, fill=rgb(20,20,20), align='left')

        for r in range(app.scrollRow, min(len(app.data), app.scrollRow+maxRows)):
            for c in range(app.scrollCol, min(len(app.columns), app.scrollCol+maxCols)):
                x,y,w,h = getCellRect(app,r,c,rowH,colW)
                base = rgb(255,255,255) if r%2==0 else rgb(248,249,253)
                if r==app.selRow and c==app.selCol:
                    base = rgb(220,232,255)
                drawRect(x,y,w,h, fill=base, border=rgb(210,215,230), borderWidth=1)
                val = app.data[r][c] if c < len(app.data[r]) else ""
                if not (app.editing and r==app.selRow and c==app.selCol):
                    fSize = max(10, min(13, int(colW/12), int(rowH/2.5)))
                    s = str(val)
                    if len(s)*fSize*0.6 > w-12:
                        s = s[:int((w-12)/(fSize*0.6))]+"…"
                    col = rgb(30,30,35)
                    if tryFloat(val) is not None:
                        col = rgb(15,60,130)
                    drawLabel(s, x+8, y+h/2, size=fSize, fill=col, align='left')
                else:
                    fSize = max(10, min(13, int(colW/12)))
                    drawRect(x+2,y+2,w-4,h-4, fill=rgb(255,255,255), border=rgb(80,120,220), borderWidth=2)
                    drawLabel(app.editText+"|", x+8, y+h/2, size=fSize, fill=rgb(20,20,20), align='left')

        if app.scrollRow>0:
            drawLabel(f"↑ {app.scrollRow} rows above", 10, topBar+headerH+10, size=10, fill=rgb(100,110,130), align='left')
        if app.scrollCol>0:
            drawLabel(f"← {app.scrollCol} cols left", app.width-120, topBar+10, size=10, fill=rgb(100,110,130), align='left')
        drawLabel("Click cell to select, click again to edit. Enter/Tab to save. Arrows to move.", app.width/2, app.height-10, size=10, fill=rgb(100,110,130))

    else:
        drawRect(0,48,270,app.height-48, fill=rgb(238,241,248), border=rgb(200,210,230), borderWidth=1)
        drawLabel("GRAPH SETTINGS", 135, 70, size=13, bold=True, fill=rgb(30,35,55))
        drawLabel("X Column", 20, 105, size=11, bold=True, fill=rgb(60,65,85), align='left')
        drawRect(20,120,230,32, fill=rgb(255,255,255), border=rgb(160,170,200), borderWidth=1.5)
        xName = app.columns[app.graphXCol] if app.graphXCol < len(app.columns) else "Select"
        drawLabel(xName, 30, 136, size=12, fill=rgb(20,25,40), align='left')
        drawLabel("▼", 235, 136, size=10, fill=rgb(80,90,110))

        drawLabel("Y Column", 20, 175, size=11, bold=True, fill=rgb(60,65,85), align='left')
        drawRect(20,190,230,32, fill=rgb(255,255,255), border=rgb(160,170,200), borderWidth=1.5)
        yName = app.columns[app.graphYCol] if app.graphYCol < len(app.columns) else "Select"
        drawLabel(yName, 30, 206, size=12, fill=rgb(20,25,40), align='left')
        drawLabel("▼", 235, 206, size=10, fill=rgb(80,90,110))

        drawRect(20,260,20,20, fill=rgb(255,255,255), border=rgb(120,130,160), borderWidth=1.5)
        if app.showReg:
            drawRect(24,264,12,12, fill=rgb(70,110,200))
        drawLabel("Show regression line", 50, 270, size=11, fill=rgb(30,35,55), align='left')

        if app.showReg:
            drawLabel("Regression Type", 20, 295, size=11, bold=True, fill=rgb(60,65,85), align='left')
            drawRect(20,310,230,32, fill=rgb(255,255,255), border=rgb(160,170,200), borderWidth=1.5)
            drawLabel(REG_TYPES[app.regType], 30, 326, size=12, fill=rgb(20,25,40), align='left')
            drawLabel("▼", 235, 326, size=10, fill=rgb(80,90,110))

        xVals, yVals = getGraphData(app)
        drawRect(20,360,230,200, fill=rgb(255,255,255), border=rgb(210,215,230), borderWidth=1)
        drawLabel(f"Points: {len(xVals)}", 30, 375, size=11, fill=rgb(50,55,75), align='left')
        if len(xVals)>=2:
            drawLabel(f"X: {min(xVals):.2g} to {max(xVals):.2g}", 30, 395, size=10, fill=rgb(80,90,110), align='left')
            drawLabel(f"Y: {min(yVals):.2g} to {max(yVals):.2g}", 30, 415, size=10, fill=rgb(80,90,110), align='left')
        if len(xVals)>=2 and app.showReg:
            reg = computeReg(xVals, yVals, REG_TYPES[app.regType])
            if reg:
                drawLabel(reg["eq"], 30, 440, size=10, bold=True, fill=rgb(30,70,150), align='left')
                drawLabel(f"R² = {reg['r2']:.4f}", 30, 460, size=11, bold=True, fill=rgb(30,35,55), align='left')
                interp="Strong fit" if reg["r2"]>0.9 else "Moderate fit" if reg["r2"]>0.7 else "Weak fit"
                drawLabel(interp, 30, 480, size=10, fill=rgb(80,90,110), align='left')
        else:
            drawLabel("Need ≥2 numeric points", 30, 440, size=10, fill=rgb(150,80,80), align='left')

        drawLabel("TABLE: add cols/rows,", 135, 580, size=9, fill=rgb(100,110,130))
        drawLabel("enter numbers to plot", 135, 592, size=9, fill=rgb(100,110,130))

        gx=300; gy=70; gw=700; gh=580
        drawRect(gx,gy,gw,gh, fill=rgb(255,255,255), border=rgb(200,210,230), borderWidth=1.5)
        if len(xVals)<2:
            drawLabel("Add numeric data in TABLE mode and select X/Y columns", gx+gw/2, gy+gh/2, size=14, fill=rgb(130,140,160))
        else:
            xmin=min(xVals); xmax=max(xVals); ymin=min(yVals); ymax=max(yVals)
            if xmin==xmax:
                xmin-=1; xmax+=1
            if ymin==ymax:
                ymin-=1; ymax+=1
            xpad=(xmax-xmin)*0.12; ypad=(ymax-ymin)*0.12
            xmin-=xpad; xmax+=xpad; ymin-=ypad; ymax+=ypad
            xticks, _ = getTicks(xmin,xmax,6)
            yticks, _ = getTicks(ymin,ymax,6)

            for xt in xticks:
                if xmin <= xt <= xmax:
                    px = gx + (xt - xmin)/(xmax - xmin)*gw
                    drawLine(px, gy, px, gy+gh, fill=rgb(230,233,240), lineWidth=1)
                    drawLabel(f"{xt:.2g}", px, gy+gh+8, size=9, fill=rgb(80,85,95))
            for yt in yticks:
                if ymin <= yt <= ymax:
                    py = gy+gh - (yt - ymin)/(ymax - ymin)*gh
                    drawLine(gx, py, gx+gw, py, fill=rgb(230,233,240), lineWidth=1)
                    drawLabel(f"{yt:.2g}", gx-8, py, size=9, fill=rgb(80,85,95), align='right')

            if xmin <= 0 <= xmax:
                px0 = gx + (0 - xmin)/(xmax - xmin)*gw
                drawLine(px0, gy, px0, gy+gh, fill=rgb(100,110,130), lineWidth=1.5)
            if ymin <= 0 <= ymax:
                py0 = gy+gh - (0 - ymin)/(ymax - ymin)*gh
                drawLine(gx, py0, gx+gw, py0, fill=rgb(100,110,130), lineWidth=1.5)

            for i in range(len(xVals)):
                px = gx + (xVals[i] - xmin)/(xmax - xmin)*gw
                py = gy+gh - (yVals[i] - ymin)/(ymax - ymin)*gh
                drawCircle(px,py,5, fill=rgb(70,110,220), border=rgb(255,255,255), borderWidth=1.5)

            if app.showReg:
                reg = computeReg(xVals, yVals, REG_TYPES[app.regType])
                if reg and reg["fn"]:
                    prev=None
                    for j in range(100):
                        xv = xmin + (xmax-xmin)*j/99
                        try:
                            yv = reg["fn"](xv)
                            if yv is None or not math.isfinite(yv):
                                prev=None
                                continue
                            px = gx + (xv - xmin)/(xmax - xmin)*gw
                            py = gy+gh - (yv - ymin)/(ymax - ymin)*gh
                            if prev:
                                drawLine(prev[0],prev[1],px,py, fill=rgb(220,60,60), lineWidth=2.5)
                            prev=(px,py)
                        except:
                            prev=None
                            continue

            fSize = max(11, min(14, int(gw/50)))
            drawLabel(xName, gx+gw/2, gy+gh+28, size=fSize, bold=True, fill=rgb(30,35,55))
            drawLabel(yName, gx-45, gy+gh/2, size=fSize, bold=True, fill=rgb(30,35,55), rotateAngle=-90)

        if app.openDropdown=='xcol':
            for i, colName in enumerate(app.columns):
                iy = 152 + (i+1)*30
                drawRect(20,iy,230,28, fill=rgb(245,247,255), border=rgb(180,190,210), borderWidth=1)
                drawLabel(colName, 30, iy+14, size=11, fill=rgb(20,25,40), align='left')
        if app.openDropdown=='ycol':
            for i, colName in enumerate(app.columns):
                iy = 222 + (i+1)*30
                drawRect(20,iy,230,28, fill=rgb(245,247,255), border=rgb(180,190,210), borderWidth=1)
                drawLabel(colName, 30, iy+14, size=11, fill=rgb(20,25,40), align='left')
        if app.openDropdown=='reg':
            for i, rt in enumerate(REG_TYPES):
                iy = 342 + (i+1)*30
                drawRect(20,iy,230,28, fill=rgb(255,245,240) if i==app.regType else rgb(245,247,255), border=rgb(180,190,210), borderWidth=1)
                drawLabel(rt, 30, iy+14, size=11, fill=rgb(20,25,40), align='left')

def main():
    runApp(1050,700)

main()
