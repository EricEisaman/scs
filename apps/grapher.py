
from scs import *
import math

# ================= CONFIG - EDIT HERE =================
CONFIG = {
    "baseFontSize": 14,      # <-- CHANGE THIS to scale all fonts. Try 12, 14, 16, 18
    "headerBonus": 2,         # header = base + headerBonus
    "cellBonus": 1,           # cell = base + cellBonus
    "smallBonus": -2,         # tick labels, hints = base + smallBonus
    "titleBonus": 3,          # graph axis titles = base + titleBonus
    "topButtonSize": 14,
    "dropdownSize": 14,
    "rowHeight": 44,
    "headerHeight": 42,
    "dropdownItemHeight": 34,
}
# ======================================================

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
    if n < 2: return None
    sx = sum(x); sy = sum(y)
    sxx = sum(v*v for v in x)
    sxy = sum(x[i]*y[i] for i in range(n))
    denom = n*sxx - sx*sx
    if abs(denom) < 1e-12: return None
    m = (n*sxy - sx*sy)/denom
    b = (sy - m*sx)/n
    ymean = sy/n
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res = sum((y[i] - (m*x[i]+b))**2 for i in range(n))
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 else 0
    return {"m":m, "b":b, "r2":r2, "fn": lambda xv: m*xv+b, "eq": f"y = {m:.3g}x + {b:.3g}"}

def quadraticReg(x, y):
    n = len(x)
    if n < 3: return linearReg(x,y)
    sx = sum(x); sx2 = sum(v*v for v in x); sx3 = sum(v**3 for v in x); sx4 = sum(v**4 for v in x)
    sy = sum(y); sxy = sum(x[i]*y[i] for i in range(n)); sx2y = sum((x[i]**2)*y[i] for i in range(n))
    A = [[sx4, sx3, sx2],[sx3, sx2, sx],[sx2, sx, n]]
    B = [sx2y, sxy, sy]
    sol = solveLinearSystem(A,B)
    if sol is None: return linearReg(x,y)
    a,b,c = sol
    fn = lambda xv: a*xv*xv + b*xv + c
    ymean = sy/n
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res = sum((y[i] - fn(x[i]))**2 for i in range(n))
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 else 0
    return {"a":a,"b":b,"c":c,"r2":r2,"fn":fn,"eq": f"y = {a:.3g}x^2 + {b:.3g}x + {c:.3g}"}

def cubicReg(x,y):
    n = len(x)
    if n < 4: return quadraticReg(x,y)
    sx = sum(x); sx2 = sum(v*v for v in x); sx3 = sum(v**3 for v in x)
    sx4 = sum(v**4 for v in x); sx5 = sum(v**5 for v in x); sx6 = sum(v**6 for v in x)
    sy = sum(y); sxy = sum(x[i]*y[i] for i in range(n)); sx2y = sum((x[i]**2)*y[i] for i in range(n)); sx3y = sum((x[i]**3)*y[i] for i in range(n))
    A = [[sx6,sx5,sx4,sx3],[sx5,sx4,sx3,sx2],[sx4,sx3,sx2,sx],[sx3,sx2,sx,n]]
    B = [sx3y, sx2y, sxy, sy]
    sol = solveLinearSystem(A,B)
    if sol is None: return quadraticReg(x,y)
    a,b,c,d = sol
    fn = lambda xv: a*xv**3 + b*xv*xv + c*xv + d
    ymean = sy/n
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res = sum((y[i] - fn(x[i]))**2 for i in range(n))
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 else 0
    return {"a":a,"b":b,"c":c,"d":d,"r2":r2,"fn":fn,"eq": f"y = {a:.3g}x^3 + {b:.3g}x^2 + {c:.3g}x + {d:.3g}"}

def expReg(x,y):
    fx=[]; fy=[]
    for i in range(len(x)):
        if y[i]>0: fx.append(x[i]); fy.append(math.log(y[i]))
    if len(fx)<2: return None
    lin = linearReg(fx,fy)
    if lin is None: return None
    b = lin["m"]; ln_a = lin["b"]; a = math.exp(ln_a)
    fn = lambda xv: a*math.exp(b*xv)
    ymean = sum(y)/len(y)
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res = sum((y[i] - fn(x[i]))**2 for i in range(len(x)))
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 else 0
    return {"a":a,"b":b,"r2":r2,"fn":fn,"eq": f"y = {a:.3g}*e^({b:.3g}x)"}

def logReg(x,y):
    fx=[]; fy=[]
    for i in range(len(x)):
        if x[i]>0: fx.append(math.log(x[i])); fy.append(y[i])
    if len(fx)<2: return None
    lin = linearReg(fx,fy)
    if lin is None: return None
    a = lin["m"]; b = lin["b"]
    fn = lambda xv: a*math.log(xv)+b if xv>0 else None
    ymean = sum(y)/len(y)
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res = sum((y[i] - fn(x[i]))**2 for i in range(len(x)) if x[i]>0)
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 else 0
    return {"a":a,"b":b,"r2":r2,"fn":fn,"eq": f"y = {a:.3g}*ln(x) + {b:.3g}"}

def powerReg(x,y):
    fx=[]; fy=[]
    for i in range(len(x)):
        if x[i]>0 and y[i]>0: fx.append(math.log(x[i])); fy.append(math.log(y[i]))
    if len(fx)<2: return None
    lin = linearReg(fx,fy)
    if lin is None: return None
    b = lin["m"]; ln_a = lin["b"]; a = math.exp(ln_a)
    fn = lambda xv: a*(xv**b) if xv>0 else None
    ymean = sum(y)/len(y)
    ss_tot = sum((yi - ymean)**2 for yi in y)
    ss_res=0
    for i in range(len(x)):
        if x[i]>0:
            p = fn(x[i])
            if p is not None: ss_res += (y[i]-p)**2
    r2 = 1 - ss_res/ss_tot if ss_tot>1e-12 else 0
    return {"a":a,"b":b,"r2":r2,"fn":fn,"eq": f"y = {a:.3g}*x^{b:.3g}"}

def computeReg(x,y, typ):
    if len(x)<2: return None
    if typ=="Linear": return linearReg(x,y)
    if typ=="Quadratic": return quadraticReg(x,y)
    if typ=="Exponential": return expReg(x,y)
    if typ=="Logarithmic": return logReg(x,y)
    if typ=="Power": return powerReg(x,y)
    if typ=="Cubic": return cubicReg(x,y)
    return linearReg(x,y)

def niceStep(v):
    if v<=0: return 1
    exp = math.floor(math.log10(v))
    f = v / (10**exp)
    if f <= 1.5: nf=1
    elif f <= 3: nf=2
    elif f <= 7: nf=5
    else: nf=10
    return nf * (10**exp)

def getTicks(mn,mx, maxTicks=6):
    if mn==mx: mn-=1; mx+=1
    rng = mx-mn
    step = niceStep(rng / maxTicks)
    start = math.floor(mn/step)*step
    end = math.ceil(mx/step)*step
    ticks=[]; v=start
    while v <= end+1e-9:
        ticks.append(v); v+=step
    return ticks, step

def tryFloat(s):
    try: return float(str(s).strip())
    except: return None

# Font helpers that all reference CONFIG
def font_base(): return CONFIG["baseFontSize"]
def font_header(): return CONFIG["baseFontSize"] + CONFIG["headerBonus"]
def font_cell(): return CONFIG["baseFontSize"] + CONFIG["cellBonus"]
def font_small(): return CONFIG["baseFontSize"] + CONFIG["smallBonus"]
def font_title(): return CONFIG["baseFontSize"] + CONFIG["titleBonus"]
def font_top(): return CONFIG["topButtonSize"]
def font_dropdown(): return CONFIG["dropdownSize"]

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
    app.selRow=0; app.selCol=0
    app.editing=False; app.editText=""
    app.scrollRow=0; app.scrollCol=0
    app.graphXCol=0; app.graphYCol=1
    app.showReg=True; app.regType=0
    app.openDropdown=None
    app.shiftDown=False
    app.capsLock=False

def getVisibleCounts(app):
    topBar=48
    headerH=CONFIG["headerHeight"]
    availH = app.height - topBar - headerH - 24
    nRows = len(app.data)
    rowH = max(CONFIG["rowHeight"], availH // max(1,nRows)) if nRows <= 8 else CONFIG["rowHeight"]
    maxRows = max(1, availH // rowH)
    nCols = len(app.columns)
    availW = app.width - 12
    colW = availW // max(1,nCols) if nCols <= 6 else 180
    maxCols = max(1, availW // colW)
    return rowH, maxRows, colW, maxCols

def getCellRect(app, r, c, rowH, colW):
    topBar=48; headerH=CONFIG["headerHeight"]
    x = 6 + (c - app.scrollCol)*colW
    y = topBar + headerH + (r - app.scrollRow)*rowH
    return x,y,colW,rowH

def getHeaderRect(app, c, colW):
    x = 6 + (c - app.scrollCol)*colW
    y = 48
    return x,y,colW,CONFIG["headerHeight"]

def getGraphData(app):
    xVals=[]; yVals=[]
    if app.graphXCol >= len(app.columns) or app.graphYCol >= len(app.columns): return [],[]
    for row in app.data:
        if app.graphXCol < len(row) and app.graphYCol < len(row):
            xv = tryFloat(row[app.graphXCol])
            yv = tryFloat(row[app.graphYCol])
            if xv is not None and yv is not None and math.isfinite(xv) and math.isfinite(yv):
                xVals.append(xv); yVals.append(yv)
    return xVals, yVals

def onMousePress(app,mx,my):
    if 10 <= mx <= 110 and 8 <= my <= 40:
        app.mode='table'; app.openDropdown=None; return
    if 120 <= mx <= 220 and 8 <= my <= 40:
        app.mode='graph'; app.openDropdown=None; return
    if app.mode=='table':
        if 260 <= mx <= 340 and 8 <= my <= 40:
            app.data.append(["" for _ in range(len(app.columns))]); return
        if 350 <= mx <= 440 and 8 <= my <= 40:
            app.columns.append(f"Col {len(app.columns)+1}")
            for row in app.data: row.append("")
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
                    if idx < len(row): row.pop(idx)
                app.selCol = max(0, min(app.selCol, len(app.columns)-1))
                app.graphXCol = min(app.graphXCol, len(app.columns)-1)
                app.graphYCol = min(app.graphYCol, len(app.columns)-1)
            return
        if 640 <= mx <= 700 and 8 <= my <= 40:
            for r in range(len(app.data)):
                for c in range(len(app.columns)):
                    if c < len(app.data[r]): app.data[r][c]=""
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
        headerH=CONFIG["headerHeight"]; topBar=48
        if topBar <= my <= topBar+headerH:
            for c in range(app.scrollCol, min(len(app.columns), app.scrollCol+maxCols)):
                x,y,w,h = getHeaderRect(app,c,colW)
                if x <= mx <= x+w:
                    if app.selRow==-1 and app.selCol==c:
                        app.editing=True; app.editText=str(app.columns[c])
                    else:
                        app.selRow=-1; app.selCol=c; app.editing=False
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
                            app.selRow=r; app.selCol=c; app.editing=False
                        return
            app.editing=False
    else:
        # GRAPH - open dropdown gets priority
        if app.openDropdown is not None:
            if app.openDropdown=='xcol':
                for i in range(len(app.columns)):
                    iy = 156 + i*CONFIG["dropdownItemHeight"]
                    if 20 <= mx <= 260 and iy <= my <= iy+CONFIG["dropdownItemHeight"]-2:
                        app.graphXCol=i; app.openDropdown=None; return
                if 20 <= mx <= 260 and 120 <= my <= 156:
                    app.openDropdown=None; return
                app.openDropdown=None
            elif app.openDropdown=='ycol':
                for i in range(len(app.columns)):
                    iy = 226 + i*CONFIG["dropdownItemHeight"]
                    if 20 <= mx <= 260 and iy <= my <= iy+CONFIG["dropdownItemHeight"]-2:
                        app.graphYCol=i; app.openDropdown=None; return
                if 20 <= mx <= 260 and 190 <= my <= 226:
                    app.openDropdown=None; return
                app.openDropdown=None
            elif app.openDropdown=='reg':
                for i in range(len(REG_TYPES)):
                    iy = 356 + i*CONFIG["dropdownItemHeight"]
                    if 20 <= mx <= 260 and iy <= my <= iy+CONFIG["dropdownItemHeight"]-2:
                        app.regType=i; app.openDropdown=None; return
                if 20 <= mx <= 260 and 320 <= my <= 356:
                    app.openDropdown=None; return
                app.openDropdown=None
        if 20 <= mx <= 260 and 120 <= my <= 156:
            app.openDropdown='xcol'; return
        if 20 <= mx <= 260 and 190 <= my <= 226:
            app.openDropdown='ycol'; return
        if 20 <= mx <= 260 and 320 <= my <= 356 and app.showReg:
            app.openDropdown='reg'; return
        if 20 <= mx <= 42 and 262 <= my <= 284:
            app.showReg = not app.showReg; return

def onKeyPress(app,key):
    # Track shift / caps for CAPS fix
    low = key.lower()
    if 'shift' in low:
        app.shiftDown = True
        return
    if 'caps' in low or 'capslock' in low:
        app.capsLock = not app.capsLock
        return

    if app.editing:
        if key=='enter' or key=='tab':
            if app.selRow==-1:
                if 0 <= app.selCol < len(app.columns):
                    newName = app.editText.strip() or f"Col {app.selCol+1}"
                    app.columns[app.selCol]=newName
            else:
                if 0 <= app.selRow < len(app.data) and 0 <= app.selCol < len(app.columns):
                    while len(app.data[app.selRow]) <= app.selCol:
                        app.data[app.selRow].append("")
                    app.data[app.selRow][app.selCol]=app.editText
            app.editing=False; app.editText=""
            if key=='tab':
                app.selCol+=1
                if app.selCol >= len(app.columns):
                    app.selCol=0; app.selRow+=1
                    if app.selRow >= len(app.data):
                        app.data.append(["" for _ in range(len(app.columns))])
        elif key=='escape':
            app.editing=False; app.editText=""
        elif key=='backspace' or key=='delete':
            app.editText = app.editText[:-1]
        elif key=='space' or key==' ':
            if len(app.editText)<60: app.editText+=' '
        else:
            # FIX FOR CAPS: handle letters with shift/caps
            if len(key)==1:
                ch = key
                # If SCS sends lowercase even when shift held, we uppercase manually
                if ch.isalpha():
                    # xor: shift or caps => uppercase
                    shouldUpper = app.shiftDown ^ app.capsLock
                    # Also respect if key is already uppercase
                    if shouldUpper:
                        ch = ch.upper()
                    else:
                        ch = ch.lower()
                    # If original key was uppercase, keep it uppercase regardless
                    if key.isupper():
                        ch = key  # trust original uppercase
                if len(app.editText)<60:
                    app.editText+=ch
            elif key=='period' or key=='.':
                app.editText+='.'
            elif key=='comma' or key==',':
                app.editText+=','
            elif key=='minus' or key=='dash' or key=='-':
                app.editText+='-'
            elif key=='slash' or key=='/':
                app.editText+='/'
            elif key=='percent' or key=='%':
                app.editText+='%'
        return
    else:
        if app.mode=='table':
            if key=='up':
                app.selRow = max(0, app.selRow-1)
                if app.selRow < app.scrollRow: app.scrollRow = app.selRow
            elif key=='down':
                app.selRow = min(len(app.data)-1, app.selRow+1)
                rowH, maxRows, _, _ = getVisibleCounts(app)
                if app.selRow >= app.scrollRow+maxRows: app.scrollRow = app.selRow - maxRows +1
            elif key=='left':
                app.selCol = max(0, app.selCol-1)
                if app.selCol < app.scrollCol: app.scrollCol = app.selCol
            elif key=='right':
                app.selCol = min(len(app.columns)-1, app.selCol+1)
                _, _, _, maxCols = getVisibleCounts(app)
                if app.selCol >= app.scrollCol+maxCols: app.scrollCol = app.selCol - maxCols +1
            elif key=='enter':
                app.editing=True
                app.editText=str(app.columns[app.selCol]) if app.selRow==-1 else str(app.data[app.selRow][app.selCol] if app.selCol < len(app.data[app.selRow]) else "")
            elif key=='backspace' or key=='delete':
                if app.selRow>=0 and app.selCol < len(app.data[app.selRow]):
                    app.data[app.selRow][app.selCol]=""
            elif key=='tab':
                app.selCol+=1
                if app.selCol >= len(app.columns):
                    app.selCol=0; app.selRow+=1
                    if app.selRow >= len(app.data):
                        app.data.append(["" for _ in range(len(app.columns))])

def onKeyRelease(app,key):
    low = key.lower()
    if 'shift' in low:
        app.shiftDown = False

def redrawAll(app):
    drawRect(0,0,app.width,app.height, fill=rgb(245,247,251))
    drawRect(0,0,app.width,48, fill=rgb(22,28,45))
    def drawTopBtn(x,label,active):
        fill = rgb(65,85,135) if active else rgb(42,48,68)
        border = rgb(110,140,220) if active else rgb(60,65,85)
        drawRect(x,8,100,32, fill=fill, border=border, borderWidth=1.5)
        drawLabel(label, x+50, 24, size=font_top(), bold=True, fill=rgb(255,255,255))
    drawTopBtn(10,"TABLE", app.mode=='table')
    drawTopBtn(120,"GRAPH", app.mode=='graph')
    if app.mode=='table':
        def smallBtn(x,lab):
            drawRect(x,8,80,32, fill=rgb(38,44,64), border=rgb(70,80,110), borderWidth=1)
            drawLabel(lab, x+40, 24, size=font_base(), bold=False, fill=rgb(210,220,240))
        smallBtn(260,"+ Row"); smallBtn(350,"+ Col"); smallBtn(450,"- Row"); smallBtn(540,"- Col")
        drawRect(640,8,60,32, fill=rgb(38,44,64), border=rgb(70,80,110), borderWidth=1)
        drawLabel("Clear", 670,24, size=font_base(), fill=rgb(210,220,240))
        drawRect(710,8,120,32, fill=rgb(90,70,40), border=rgb(180,150,90), borderWidth=1)
        drawLabel("Load Example", 770,24, size=font_base(), bold=True, fill=rgb(255,235,150))
        rowH, maxRows, colW, maxCols = getVisibleCounts(app)
        topBar=48; headerH=CONFIG["headerHeight"]
        drawRect(0,topBar,app.width,headerH, fill=rgb(235,238,245), border=rgb(200,205,220), borderWidth=1)
        for c in range(app.scrollCol, min(len(app.columns), app.scrollCol+maxCols)):
            x,y,w,h = getHeaderRect(app,c,colW)
            isSel = (app.selCol==c and app.selRow==-1)
            fill = rgb(200,215,250) if isSel else rgb(235,238,245)
            drawRect(x,y,w,h, fill=fill, border=rgb(180,185,200), borderWidth=1)
            fSize = font_header()
            txt = app.columns[c]
            if len(txt)*fSize*0.6 > w-12: txt = txt[:max(1,int((w-12)/(fSize*0.6)))]+"…"
            drawLabel(txt, x+w/2, y+h/2, size=fSize, bold=True, fill=rgb(30,35,55))
            if isSel and app.editing:
                drawRect(x+4,y+4,w-8,h-8, fill=rgb(255,255,255), border=rgb(80,120,220), borderWidth=2.5)
                drawLabel(app.editText+"|", x+10, y+h/2, size=fSize, fill=rgb(20,20,20), align='left')
        for r in range(app.scrollRow, min(len(app.data), app.scrollRow+maxRows)):
            for c in range(app.scrollCol, min(len(app.columns), app.scrollCol+maxCols)):
                x,y,w,h = getCellRect(app,r,c,rowH,colW)
                base = rgb(255,255,255) if r%2==0 else rgb(248,249,253)
                if r==app.selRow and c==app.selCol: base = rgb(220,232,255)
                drawRect(x,y,w,h, fill=base, border=rgb(210,215,230), borderWidth=1)
                val = app.data[r][c] if c < len(app.data[r]) else ""
                if not (app.editing and r==app.selRow and c==app.selCol):
                    fSize = font_cell()
                    s = str(val)
                    if len(s)*fSize*0.6 > w-16: s = s[:max(1,int((w-16)/(fSize*0.6)))]+"…"
                    col = rgb(30,30,35) if tryFloat(val) is None else rgb(15,60,130)
                    drawLabel(s, x+12, y+h/2, size=fSize, fill=col, align='left')
                else:
                    fSize = font_cell()
                    drawRect(x+3,y+3,w-6,h-6, fill=rgb(255,255,255), border=rgb(80,120,220), borderWidth=2.5)
                    drawLabel(app.editText+"|", x+12, y+h/2, size=fSize, fill=rgb(20,20,20), align='left')
        drawLabel(f"baseFontSize={CONFIG['baseFontSize']} (edit CONFIG top of file) | CAPS: {'ON' if app.capsLock else 'off'} SHIFT:{'down' if app.shiftDown else 'up'} | Click to select, again to edit.", app.width/2, app.height-10, size=font_small(), bold=True, fill=rgb(80,90,120))
    else:
        drawRect(0,48,280,app.height-48, fill=rgb(238,241,248), border=rgb(200,210,230), borderWidth=1)
        drawLabel("GRAPH SETTINGS", 140, 72, size=font_base()+1, bold=True, fill=rgb(30,35,55))
        drawLabel("X Column", 22, 102, size=font_small()+1, bold=True, fill=rgb(60,65,85), align='left')
        drawRect(20,120,240,36, fill=rgb(255,255,255), border=rgb(160,170,200), borderWidth=1.8)
        xName = app.columns[app.graphXCol] if app.graphXCol < len(app.columns) else "Select"
        drawLabel(xName, 32, 138, size=font_dropdown(), bold=True, fill=rgb(20,25,40), align='left')
        drawLabel("v", 238, 138, size=font_small(), fill=rgb(80,90,110))
        drawLabel("Y Column", 22, 172, size=font_small()+1, bold=True, fill=rgb(60,65,85), align='left')
        drawRect(20,190,240,36, fill=rgb(255,255,255), border=rgb(160,170,200), borderWidth=1.8)
        yName = app.columns[app.graphYCol] if app.graphYCol < len(app.columns) else "Select"
        drawLabel(yName, 32, 208, size=font_dropdown(), bold=True, fill=rgb(20,25,40), align='left')
        drawLabel("v", 238, 208, size=font_small(), fill=rgb(80,90,110))
        drawRect(20,262,22,22, fill=rgb(255,255,255), border=rgb(120,130,160), borderWidth=1.8)
        if app.showReg: drawRect(24,266,14,14, fill=rgb(70,110,200))
        drawLabel("Show regression line", 52, 273, size=font_base()-1, fill=rgb(30,35,55), align='left')
        if app.showReg:
            drawLabel("Regression Type", 22, 302, size=font_small()+1, bold=True, fill=rgb(60,65,85), align='left')
            drawRect(20,320,240,36, fill=rgb(255,255,255), border=rgb(160,170,200), borderWidth=1.8)
            drawLabel(REG_TYPES[app.regType], 32, 338, size=font_dropdown(), bold=True, fill=rgb(20,25,40), align='left')
            drawLabel("v", 238, 338, size=font_small(), fill=rgb(80,90,110))
        xVals, yVals = getGraphData(app)
        drawRect(20,370,240,220, fill=rgb(255,255,255), border=rgb(210,215,230), borderWidth=1.2)
        drawLabel(f"Points: {len(xVals)}", 32, 388, size=font_base()-1, bold=True, fill=rgb(50,55,75), align='left')
        if len(xVals)>=2:
            drawLabel(f"X: {min(xVals):.2g} to {max(xVals):.2g}", 32, 410, size=font_small(), fill=rgb(80,90,110), align='left')
            drawLabel(f"Y: {min(yVals):.2g} to {max(yVals):.2g}", 32, 430, size=font_small(), fill=rgb(80,90,110), align='left')
        if len(xVals)>=2 and app.showReg:
            reg = computeReg(xVals, yVals, REG_TYPES[app.regType])
            if reg:
                drawLabel(reg["eq"], 32, 455, size=font_small(), bold=True, fill=rgb(30,70,150), align='left')
                drawLabel(f"R2 = {reg['r2']:.4f}", 32, 478, size=font_base()-1, bold=True, fill=rgb(30,35,55), align='left')
                interp="Strong fit" if reg["r2"]>0.9 else "Moderate fit" if reg["r2"]>0.7 else "Weak fit"
                drawLabel(interp, 32, 500, size=font_small(), fill=rgb(80,90,110), align='left')
        else:
            drawLabel("Need >=2 numeric points", 32, 455, size=font_small(), bold=True, fill=rgb(150,80,80), align='left')
        gx=310; gy=70; gw=700; gh=590
        drawRect(gx,gy,gw,gh, fill=rgb(255,255,255), border=rgb(200,210,230), borderWidth=1.8)
        if len(xVals)<2:
            drawLabel("Add numeric data in TABLE mode", gx+gw/2, gy+gh/2-15, size=font_title(), bold=True, fill=rgb(130,140,160))
            drawLabel("and select X/Y columns", gx+gw/2, gy+gh/2+15, size=font_base(), fill=rgb(130,140,160))
        else:
            xmin=min(xVals); xmax=max(xVals); ymin=min(yVals); ymax=max(yVals)
            if xmin==xmax: xmin-=1; xmax+=1
            if ymin==ymax: ymin-=1; ymax+=1
            xpad=(xmax-xmin)*0.12; ypad=(ymax-ymin)*0.12
            xmin-=xpad; xmax+=xpad; ymin-=ypad; ymax+=ypad
            xticks, _ = getTicks(xmin,xmax,6)
            yticks, _ = getTicks(ymin,ymax,6)
            for xt in xticks:
                if xmin <= xt <= xmax:
                    px = gx + (xt - xmin)/(xmax - xmin)*gw
                    drawLine(px, gy, px, gy+gh, fill=rgb(230,233,240), lineWidth=1)
                    drawLabel(f"{xt:.2g}", px, gy+gh+10, size=font_small(), fill=rgb(60,70,85))
            for yt in yticks:
                if ymin <= yt <= ymax:
                    py = gy+gh - (yt - ymin)/(ymax - ymin)*gh
                    drawLine(gx, py, gx+gw, py, fill=rgb(230,233,240), lineWidth=1)
                    drawLabel(f"{yt:.2g}", gx-10, py, size=font_small(), fill=rgb(60,70,85), align='right')
            if xmin <= 0 <= xmax:
                px0 = gx + (0 - xmin)/(xmax - xmin)*gw
                drawLine(px0, gy, px0, gy+gh, fill=rgb(100,110,130), lineWidth=1.5)
            if ymin <= 0 <= ymax:
                py0 = gy+gh - (0 - ymin)/(ymax - ymin)*gh
                drawLine(gx, py0, gx+gw, py0, fill=rgb(100,110,130), lineWidth=1.5)
            for i in range(len(xVals)):
                px = gx + (xVals[i] - xmin)/(xmax - xmin)*gw
                py = gy+gh - (yVals[i] - ymin)/(ymax - ymin)*gh
                drawCircle(px,py,6, fill=rgb(70,110,220), border=rgb(255,255,255), borderWidth=2)
            if app.showReg:
                reg = computeReg(xVals, yVals, REG_TYPES[app.regType])
                if reg and reg["fn"]:
                    prev=None
                    for j in range(100):
                        xv = xmin + (xmax-xmin)*j/99
                        try:
                            yv = reg["fn"](xv)
                            if yv is None or not math.isfinite(yv): prev=None; continue
                            px = gx + (xv - xmin)/(xmax - xmin)*gw
                            py = gy+gh - (yv - ymin)/(ymax - ymin)*gh
                            if prev: drawLine(prev[0],prev[1],px,py, fill=rgb(220,60,60), lineWidth=3)
                            prev=(px,py)
                        except: prev=None; continue
            fSize = font_title()
            drawLabel(xName, gx+gw/2, gy+gh+32, size=fSize, bold=True, fill=rgb(30,35,55))
            drawLabel(yName, gx-50, gy+gh/2, size=fSize, bold=True, fill=rgb(30,35,55), rotateAngle=-90)
        if app.openDropdown=='xcol':
            for i, colName in enumerate(app.columns):
                iy = 156 + i*CONFIG["dropdownItemHeight"]
                drawRect(20,iy,240,CONFIG["dropdownItemHeight"]-2, fill=rgb(245,247,255), border=rgb(160,180,210), borderWidth=1.2)
                drawLabel(colName, 32, iy+CONFIG["dropdownItemHeight"]//2, size=font_base()-1, bold=True, fill=rgb(20,25,40), align='left')
        if app.openDropdown=='ycol':
            for i, colName in enumerate(app.columns):
                iy = 226 + i*CONFIG["dropdownItemHeight"]
                drawRect(20,iy,240,CONFIG["dropdownItemHeight"]-2, fill=rgb(245,247,255), border=rgb(160,180,210), borderWidth=1.2)
                drawLabel(colName, 32, iy+CONFIG["dropdownItemHeight"]//2, size=font_base()-1, bold=True, fill=rgb(20,25,40), align='left')
        if app.openDropdown=='reg':
            for i, rt in enumerate(REG_TYPES):
                iy = 356 + i*CONFIG["dropdownItemHeight"]
                fill = rgb(255,240,230) if i==app.regType else rgb(245,247,255)
                drawRect(20,iy,240,CONFIG["dropdownItemHeight"]-2, fill=fill, border=rgb(160,180,210), borderWidth=1.2)
                drawLabel(rt, 32, iy+CONFIG["dropdownItemHeight"]//2, size=font_base()-1, bold=True, fill=rgb(20,25,40), align='left')

def main():
    runApp(1050,700)

main()
