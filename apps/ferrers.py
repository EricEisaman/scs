
from scs import *
import re, math
try:
    from browser import aio
    HAS_AIO = True
except:
    HAS_AIO = False
    aio = None

PYODIDE_AVAILABLE = False
pyodide_run = None
pyodide_load = None

try:
    import extensions.pyodide as pyodide_mod
    PYODIDE_AVAILABLE = True
    for cand in ['run','run_python','run_code','exec','execute','eval']:
        if hasattr(pyodide_mod, cand):
            pyodide_run = getattr(pyodide_mod, cand)
            break
    for cand in ['load','load_pyodide','ensure_pyodide','init','start']:
        if hasattr(pyodide_mod, cand):
            pyodide_load = getattr(pyodide_mod, cand)
            break
except:
    try:
        from extensions.pyodide import run as pyodide_run
        from extensions.pyodide import load as pyodide_load
        PYODIDE_AVAILABLE = True
    except:
        try:
            from extensions.pyodide import run_python as pyodide_run
            PYODIDE_AVAILABLE = True
        except:
            PYODIDE_AVAILABLE = False

def partition_number_pure(n):
    if n < 0: return 0
    if n == 0: return 1
    p = [0]*(n+1)
    p[0] = 1
    for k in range(1, n+1):
        tot = 0
        j = 1
        while True:
            pent1 = j*(3*j-1)//2
            if pent1 > k: break
            s = 1 if j % 2 == 1 else -1
            tot += s * p[k-pent1]
            pent2 = j*(3*j+1)//2
            if pent2 <= k:
                tot += s * p[k-pent2]
            j += 1
        p[k] = tot
    return p[n]

def parse_partition(text):
    if not text: return None
    s = text.strip().replace('$','')
    parts = re.split(r'=|⊢|\\vdash', s)
    cand = s
    best = -1
    for seg in parts:
        score = seg.count('+')*2 + seg.count(',') + seg.count('(')
        if len(re.findall(r'\d+', seg)) >= 2:
            score += len(re.findall(r'\d+', seg))
        if score > best:
            best = score
            cand = seg
    cand = cand.replace('(',' ').replace(')',' ').replace('[',' ').replace(']',' ').replace('{',' ').replace('}',' ')
    if '+' in cand:
        toks = cand.split('+')
    elif ',' in cand:
        toks = cand.split(',')
    else:
        toks = re.split(r'\s+', cand)
    nums = []
    for t in toks:
        m = re.search(r'\d+', t)
        if m:
            v = int(m.group(0))
            if v>0: nums.append(v)
    if not nums:
        all_nums = [int(x) for x in re.findall(r'\d+', s)]
        if len(all_nums)>=2 and all_nums[0]==sum(all_nums[1:]):
            nums = all_nums[1:]
        elif all_nums:
            nums = all_nums
    if not nums: return None
    nums = sorted([x for x in nums if x>0], reverse=True)
    if len(nums)>30: nums = nums[:30]
    nums = [min(x,50) for x in nums]
    return nums or None

def conjugate_partition(part):
    if not part: return []
    return [sum(1 for r in part if r>i) for i in range(max(part)) if sum(1 for r in part if r>i)>0]

def durfee_square(part):
    k=0
    for i, rl in enumerate(part):
        if rl>=i+1: k=i+1
        else: break
    return k

def is_self_conjugate(part):
    return part==conjugate_partition(part)

def hook_lengths(part):
    conj = conjugate_partition(part)
    hooks=[]
    for i, rl in enumerate(part):
        row=[]
        for j in range(rl):
            right=rl-(j+1)
            down=conj[j]-(i+1) if j<len(conj) else 0
            row.append(right+down+1)
        hooks.append(row)
    return hooks

def latex_format(part):
    if not part: return "∅"
    n=sum(part)
    inner=",".join(map(str,part))
    plus="+".join(map(str,part))
    return f"λ=({inner})={plus}⊢{n}"

EXAMPLES=[
    {"label":"1. Classic 17 — 6+4+4+2+1","value":"6+4+4+2+1","latex":"$\\lambda=(6,4,4,2,1)\\vdash17$","desc":"MathWorld classic. Durfee 3, conj (5,4,3,3,1,1)"},
    {"label":"2. Staircase 15 — 5+4+3+2+1 self-conj","value":"5+4+3+2+1","latex":"$\\lambda=(5,4,3,2,1)\\vdash15$ self-conj","desc":"Staircase, λ=λ'. Hook formula demo"},
    {"label":"3. Square 16 — 4+4+4+4","value":"4+4+4+4","latex":"$\\lambda=(4^4)\\vdash16$ in 4x4 box","desc":"1 of C(8,4)=70 diagrams in 4x4 box"},
    {"label":"4. Hook 12 — 7+1+1+1+1+1","value":"7+1+1+1+1+1","latex":"$\\lambda=(7,1^5)\\vdash12$ hook","desc":"Hook shape, Durfee 1, Sn irrep"},
    {"label":"5. Irregular 21 — 8+5+3+2+2+1","value":"8+5+3+2+2+1","latex":"$\\lambda=(8,5,3,2,2,1)\\vdash21$","desc":"Conj (6,5,3,2,2,1,1,1), Durfee 3"},
]

def get_cell_pos(app,r,c):
    max_len=max(app.partition) if app.partition else 1
    cell=app.cellSize; gap=app.cellGap
    tw=max_len*(cell+gap)-gap
    th=len(app.partition)*(cell+gap)-gap
    sx=app.diagramCenterX - tw//2
    sy=app.diagramCenterY - th//2
    return (sx + c*(cell+gap), sy + r*(cell+gap))

def hit_test(app,mx,my):
    if not app.partition: return None
    for r,rl in enumerate(app.partition):
        for c in range(rl):
            x,y=get_cell_pos(app,r,c)
            if x<=mx<=x+app.cellSize and y<=my<=y+app.cellSize:
                return (r,c,'cell')
        x,y=get_cell_pos(app,r,rl)
        if x<=mx<=x+app.cellSize and y<=my<=y+app.cellSize and rl<50:
            return (r,rl,'add_right')
    max_len=max(app.partition) if app.partition else 1
    cell=app.cellSize; gap=app.cellGap
    tw=max_len*(cell+gap)-gap
    th=len(app.partition)*(cell+gap)-gap
    sx=app.diagramCenterX - tw//2
    sy=app.diagramCenterY - th//2
    ny=sy+len(app.partition)*(cell+gap)
    if sx<=mx<=sx+cell and ny<=my<=ny+cell and len(app.partition)<30:
        return (len(app.partition),0,'add_new_row')
    return None

def in_rect(px,py,rx,ry,rw,rh):
    return rx<=px<=rx+rw and ry<=py<=ry+rh

async def ensure_pyodide_loaded(app):
    if not PYODIDE_AVAILABLE or pyodide_load is None:
        return False
    try:
        app.pyodideStatus="Loading Pyodide worker (like linear_solver.py)..."
        await pyodide_load()
        app.pyodideReady=True
        app.pyodideStatus="Pyodide ready"
        return True
    except Exception as e:
        app.pyodideStatus=f"Pyodide load fallback: {e}"
        app.pyodideReady=True
        return True

async def pyodide_compute_all(app, partition):
    if not PYODIDE_AVAILABLE or pyodide_run is None:
        app.pyodideStatus="Pyodide not available, fallback"
        app.partitionNumber=partition_number_pure(app.n)
        app.partitionNumberN=app.n
        return
    if not app.pyodideReady:
        await ensure_pyodide_loaded(app)
    n=sum(partition)
    app.pyodideComputing=True
    app.pyodideStatus=f"Pyodide computing p({n}) in worker..."
    # code executed inside pyodide worker
    py_code = (
        f"part = {partition}\n"
        f"n = {n}\n"
        "max_len = max(part) if part else 0\n"
        "conj = [sum(1 for r in part if r>i) for i in range(max_len)]\n"
        "conj = [c for c in conj if c>0]\n"
        "d=0\n"
        "for i, rl in enumerate(part):\n"
        "    if rl>=i+1: d=i+1\n"
        "    else: break\n"
        "hooks=[]\n"
        "for i, rl in enumerate(part):\n"
        "    row=[]\n"
        "    for j in range(rl):\n"
        "        right=rl-(j+1)\n"
        "        down=conj[j]-(i+1) if j < len(conj) else 0\n"
        "        row.append(right+down+1)\n"
        "    hooks.append(row)\n"
        "def p_num(k):\n"
        "    if k<0: return 0\n"
        "    if k==0: return 1\n"
        "    p=[0]*(k+1); p[0]=1\n"
        "    for kk in range(1,k+1):\n"
        "        tot=0; j=1\n"
        "        while True:\n"
        "            pent1=j*(3*j-1)//2\n"
        "            if pent1>kk: break\n"
        "            s=1 if j%2==1 else -1\n"
        "            tot+=s*p[kk-pent1]\n"
        "            pent2=j*(3*j+1)//2\n"
        "            if pent2<=kk: tot+=s*p[kk-pent2]\n"
        "            j+=1\n"
        "        p[kk]=tot\n"
        "    return p[k]\n"
        "pn = p_num(n)\n"
        "try:\n"
        "    import math; prod=1\n"
        "    for row in hooks:\n"
        "        for h in row: prod*=h\n"
        "    f_lambda = math.factorial(n)//prod if prod!=0 else 0\n"
        "except: f_lambda = 0\n"
        "{\"conj\": conj, \"durfee\": d, \"hooks\": hooks, \"p_n\": pn, \"f_lambda\": f_lambda, \"n\": n}\n"
    )
    try:
        try:
            result = await pyodide_run(py_code)
        except TypeError:
            result = await pyodide_run(py_code, {})
        if isinstance(result, dict):
            app.conjugate = result.get("conj", conjugate_partition(partition))
            app.durfee = result.get("durfee", durfee_square(partition))
            app.hooks = result.get("hooks", hook_lengths(partition))
            app.partitionNumber = result.get("p_n", partition_number_pure(n))
            app.partitionNumberN = n
            app.f_lambda = result.get("f_lambda", 0)
            app.pyodideStatus = f"Pyodide done: p({n})={app.partitionNumber}, f^λ={app.f_lambda}"
        else:
            app.partitionNumber = int(result) if result is not None else partition_number_pure(n)
            app.partitionNumberN = n
            app.pyodideStatus = f"Pyodide returned {app.partitionNumber}"
    except Exception as e:
        app.pyodideStatus = f"Pyodide error {e}, fallback"
        app.partitionNumber = partition_number_pure(n)
        app.partitionNumberN = n
    app.pyodideComputing=False

def onAppStart(app):
    app.width=1050
    app.height=700
    app.stepsPerSecond=60
    try:
        app.background=gradient(rgb(12,14,22), rgb(22,26,42), rgb(18,22,36), start='top')
    except:
        app.background=rgb(16,18,28)
    app.inputText="6+4+4+2+1"
    app.partition=parse_partition(app.inputText) or [6,4,4,2,1]
    app.conjugate=conjugate_partition(app.partition)
    app.durfee=durfee_square(app.partition)
    app.hooks=hook_lengths(app.partition)
    app.selfConj=is_self_conjugate(app.partition)
    app.n=sum(app.partition)
    app.cellSize=40
    app.cellGap=7
    app.diagramCenterX=app.width//2 - 10
    app.diagramCenterY=app.height//2 + 40
    app.modeBoxes=True
    app.showConjugate=False
    app.showDurfee=True
    app.showHooks=False
    app.showInfo=False
    app.animT=0
    app.hover=None
    app.cursorBlink=0
    app.inputError=""
    app.dropdownOpen=False
    app.dropdownSelected=0
    app.dropdownRect=(20, 118, 320, 34)
    app.pyodideReady=False
    app.pyodideComputing=False
    app.pyodideStatus="Pyodide: initializing (see linear_solver pattern)"
    app.partitionNumber=None
    app.partitionNumberN=None
    app.f_lambda=0
    if HAS_AIO and PYODIDE_AVAILABLE:
        async def _init(app):
            await ensure_pyodide_loaded(app)
            await pyodide_compute_all(app, app.partition)
        try:
            aio.run(_init(app))
        except Exception as e:
            app.pyodideStatus=f"aio.run failed {e}"
    else:
        app.partitionNumber=partition_number_pure(app.n)
        app.partitionNumberN=app.n
        app.pyodideStatus="Pyodide extension not found — fallback"

def recompute(app):
    app.n=sum(app.partition)
    app.selfConj=is_self_conjugate(app.partition)
    app.animT=0
    if HAS_AIO and PYODIDE_AVAILABLE and pyodide_run is not None:
        try:
            async def _re(app):
                await pyodide_compute_all(app, app.partition)
            aio.run(_re(app))
        except:
            app.conjugate=conjugate_partition(app.partition)
            app.durfee=durfee_square(app.partition)
            app.hooks=hook_lengths(app.partition)
            app.partitionNumber=partition_number_pure(app.n)
            app.partitionNumberN=app.n
    else:
        app.conjugate=conjugate_partition(app.partition)
        app.durfee=durfee_square(app.partition)
        app.hooks=hook_lengths(app.partition)
        app.partitionNumber=partition_number_pure(app.n)
        app.partitionNumberN=app.n

def onStep(app):
    if app.animT<1.0:
        app.animT=min(1.0, app.animT+0.09)
    app.cursorBlink=(app.cursorBlink+1)%60
    if app.partition:
        max_len=max(app.partition)
        rows=len(app.partition)
        scale=min(1.0, 480/max(1,max_len*50), 360/max(1,rows*50))
        target=max(18, min(44, int(40*scale)))
        app.cellSize=int(app.cellSize*0.9 + target*0.1)

def onMouseMove(app,mx,my):
    app.hover=hit_test(app,mx,my)

def onMousePress(app,mx,my):
    if app.showInfo:
        if in_rect(mx,my,app.width-60,20,40,40):
            app.showInfo=False
            return
    dx,dy,dw,dh=app.dropdownRect
    if app.dropdownOpen:
        if in_rect(mx,my,dx,dy,dw,dh):
            app.dropdownOpen=False
            return
        for i in range(len(EXAMPLES)):
            if in_rect(mx,my,dx,dy+dh+i*34,dw,32):
                app.dropdownSelected=i
                ex=EXAMPLES[i]
                app.inputText=ex["value"]
                app.partition=parse_partition(ex["value"])
                app.inputError=""
                recompute(app)
                app.dropdownOpen=False
                return
        if not in_rect(mx,my,dx,dy+dh,dw,len(EXAMPLES)*34):
            app.dropdownOpen=False
    else:
        if in_rect(mx,my,dx,dy,dw,dh):
            app.dropdownOpen=True
            return
    if in_rect(mx,my,20,20,560,50):
        return
    btns=[(400,78,70,30,'parse'),(480,78,70,30,'boxes'),(560,78,90,30,'conj'),(660,78,70,30,'durfee'),(740,78,60,30,'hooks'),(810,78,60,30,'info')]
    for bx,by,bw,bh,act in btns:
        if in_rect(mx,my,bx,by,bw,bh):
            if act=='parse':
                np=parse_partition(app.inputText)
                if np:
                    app.partition=np
                    app.inputError=""
                    recompute(app)
                else:
                    app.inputError="Try 6+4+4+2+1 or dropdown"
            elif act=='boxes':
                app.modeBoxes=not app.modeBoxes
            elif act=='conj':
                app.showConjugate=not app.showConjugate
            elif act=='durfee':
                app.showDurfee=not app.showDurfee
            elif act=='hooks':
                app.showHooks=not app.showHooks
            elif act=='info':
                app.showInfo=not app.showInfo
            return
    hit=hit_test(app,mx,my)
    if hit:
        r,c,typ=hit
        if typ=='cell' and c==app.partition[r]-1:
            app.partition[r]-=1
            if app.partition[r]==0:
                app.partition.pop(r)
            app.partition=[x for x in app.partition if x>0]
            app.partition=sorted(app.partition, reverse=True) or [1]
            recompute(app)
        elif typ=='add_right':
            app.partition[r]+=1
            if r>0 and app.partition[r]>app.partition[r-1]:
                app.partition[r]=app.partition[r-1]
            for j in range(r+1,len(app.partition)):
                if app.partition[j]>app.partition[r]:
                    app.partition[j]=app.partition[r]
            recompute(app)
        elif typ=='add_new_row':
            app.partition.append(1)
            recompute(app)

def onKeyPress(app,key):
    if key.lower()=='i':
        app.showInfo=not app.showInfo
        return
    if key.lower()=='h':
        app.showHooks=not app.showHooks
        return
    if key.lower()=='c':
        app.showConjugate=not app.showConjugate
        return
    if key.lower()=='b':
        app.modeBoxes=not app.modeBoxes
        return
    if key.lower()=='d':
        app.showDurfee=not app.showDurfee
        return
    if key=='Escape':
        if app.dropdownOpen:
            app.dropdownOpen=False
        else:
            app.showInfo=False
        return
    if key=='Enter':
        np=parse_partition(app.inputText)
        if np:
            app.partition=np
            app.inputError=""
            recompute(app)
        return
    if key=='Backspace':
        if app.inputText:
            app.inputText=app.inputText[:-1]
        return
    if key==' ':
        app.dropdownSelected=(app.dropdownSelected+1)%len(EXAMPLES)
        ex=EXAMPLES[app.dropdownSelected]
        app.inputText=ex["value"]
        app.partition=parse_partition(ex["value"])
        recompute(app)
        return
    if len(key)==1 and len(app.inputText)<60:
        if key in "0123456789+-,()[]{}=\\$ " or key.isalpha():
            app.inputText+=key

def draw_rounded_rect(x,y,w,h,r, fill=None, border=None, borderWidth=1, opacity=100):
    try:
        drawRect(x,y,w,h, fill=fill, border=border, borderWidth=borderWidth, roundness=r, opacity=opacity)
    except:
        drawRect(x,y,w,h, fill=fill, border=border, borderWidth=borderWidth, opacity=opacity)

def draw_cell_box(app,x,y,size,r,c,is_hover,is_durfee,is_ghost=False):
    if not is_ghost:
        draw_rounded_rect(x+3,y+3,size,size,9, fill=rgb(0,0,0), opacity=16)
    if is_ghost:
        draw_rounded_rect(x,y,size,size,10, fill=gradient(rgb(120,140,200), rgb(90,110,170), start='top-left'), opacity=28, border=rgb(140,160,220), borderWidth=1)
        return
    if is_durfee and app.showDurfee:
        fa=rgb(255,210,90)
        fb=rgb(255,160,40)
    else:
        pals=[(rgb(110,180,255), rgb(60,120,220)), (rgb(120,220,180), rgb(70,170,130)), (rgb(255,180,120), rgb(230,120,70)), (rgb(200,150,255), rgb(150,90,220)), (rgb(255,130,180), rgb(220,80,130))]
        fa,fb=pals[r%len(pals)]
    if is_hover:
        draw_rounded_rect(x,y,size,size,11, fill=rgb(255,255,220), opacity=90, border=rgb(255,255,255), borderWidth=2)
        draw_rounded_rect(x+1,y+1,size-2,size-2,10, fill=gradient(fa,fb, start='top'), opacity=95)
    else:
        draw_rounded_rect(x,y,size,size,10, fill=gradient(fa,fb, start='top-left'), opacity=92, border=rgb(255,255,255), borderWidth=1)
        draw_rounded_rect(x+4,y+4,size*0.35,size*0.22,4, fill=rgb(255,255,255), opacity=30)

def draw_cell_dot(app,x,y,size,r,c,is_hover,is_durfee):
    cx=x+size//2
    cy=y+size//2
    rr=size//2-2
    drawCircle(cx+2,cy+3,rr, fill=rgb(0,0,0), opacity=14)
    cols=[rgb(120,190,255), rgb(140,230,190), rgb(255,190,130), rgb(210,160,255), rgb(255,140,190)]
    c1=rgb(255,220,100) if (is_durfee and app.showDurfee) else cols[r%len(cols)]
    drawCircle(cx,cy,rr, fill=c1, border=rgb(255,255,255), borderWidth=1, opacity=90)
    drawCircle(cx-rr*0.25, cy-rr*0.25, rr*0.35, fill=rgb(255,255,255), opacity=40)
    if is_hover:
        drawCircle(cx,cy,rr+4, fill=None, border=rgb(255,255,150), borderWidth=2, opacity=70)

def draw_dropdown(app):
    dx,dy,dw,dh=app.dropdownRect
    draw_rounded_rect(dx,dy,dw,dh,10, fill=gradient(rgb(38,44,72), rgb(28,34,58), start='top'), border=rgb(90,100,140), borderWidth=1, opacity=96)
    sel=EXAMPLES[app.dropdownSelected]
    drawLabel(sel["label"], dx+12, dy+dh//2, size=12, fill=rgb(235,240,255), align='left', bold=True)
    drawLabel("▼" if not app.dropdownOpen else "▲", dx+dw-16, dy+dh//2, size=12, fill=rgb(160,170,200), align='center')
    if app.dropdownOpen:
        draw_rounded_rect(dx, dy+dh+2, dw, len(EXAMPLES)*34+4, 10, fill=rgb(0,0,0), opacity=28)
        draw_rounded_rect(dx, dy+dh, dw, len(EXAMPLES)*34, 10, fill=gradient(rgb(32,38,64), rgb(22,28,50), start='top'), border=rgb(90,100,140), borderWidth=1, opacity=98)
        for i, ex in enumerate(EXAMPLES):
            oy=dy+dh+i*34
            is_sel=(i==app.dropdownSelected)
            if is_sel:
                draw_rounded_rect(dx+2, oy+2, dw-4, 30, 8, fill=rgb(70,90,150), opacity=90)
            drawLabel(ex["label"], dx+10, oy+16, size=11, fill=rgb(255,240,180) if is_sel else rgb(200,210,230), align='left', bold=is_sel)

def draw_info_overlay(app):
    drawRect(0,0,app.width,app.height, fill=rgb(8,10,18), opacity=86)
    px=40; py=20; pw=app.width-80; ph=app.height-40
    draw_rounded_rect(px,py,pw,ph,18, fill=gradient(rgb(20,24,38), rgb(28,32,52), start='top'), opacity=98, border=rgb(80,90,130), borderWidth=1)
    draw_rounded_rect(app.width-60,20,40,40,12, fill=rgb(60,70,100), border=rgb(120,130,170), borderWidth=1)
    drawLabel("✕", app.width-40,40, size=22, fill=rgb(220,230,255), bold=True)
    drawLabel("Ferrers — Pyodide leveraged like linear_solver.py", px+pw//2, py+38, size=22, fill=rgb(235,240,255), bold=True)
    lines=[
        "PYODIDE EXTENSION — REAL USAGE:",
        "from browser import aio",
        "from extensions.pyodide import run, load",
        "async def pyodide_compute_all(app, partition):",
        "    await load()",
        "    py_code = ''' part=[6,4,4,2,1]; ... p(n) Euler ... '''",
        "    result = await run(py_code)  # Web Worker, UI 60fps",
        "    app.partitionNumber = result['p_n']",
        "def onAppStart(app): aio.run(pyodide_compute_all(app, app.partition))",
        "",
        "Computes inside worker: p(n), conj, Durfee, hooks, f^λ=n!/∏h",
    ]
    y=py+90
    for line in lines:
        drawLabel(line, px+28, y, size=11, fill=rgb(120,200,255) if "PYODIDE" in line or "from" in line or "await" in line else rgb(210,220,240), align='left-top')
        y+=16

def redrawAll(app):
    for i in range(70):
        sx=(i*137)%app.width
        sy=(i*211)%app.height
        if sy<110: continue
        alpha=(math.sin(i*0.7+app.animT*0.1)*0.3+0.7)*35
        drawCircle(sx,sy,1, fill=rgb(200,210,255), opacity=int(alpha))
    draw_rounded_rect(18,18,560,50,14, fill=gradient(rgb(30,34,50), rgb(24,28,44), start='top'), border=rgb(70,80,110), borderWidth=1, opacity=96)
    drawLabel("LaTeX:", 40,28, size=11, fill=rgb(130,140,170), align='left-top', bold=True)
    cursor="|" if app.cursorBlink<30 else ""
    dt=app.inputText+cursor
    if len(dt)>48:
        dt=dt[-48:]
    drawLabel(dt, 40,46, size=16, fill=rgb(240,245,255), align='left-top')
    if app.inputError:
        drawLabel(app.inputError, 280,28, size=11, fill=rgb(255,180,120), align='left-top')
    btns=[(400,78,70,30,"Parse"),(480,78,70,30,"Boxes" if app.modeBoxes else "Dots"),(560,78,90,30,"Conj ON" if app.showConjugate else "Conj OFF"),(660,78,70,30,"Durfee"),(740,78,60,30,"Hooks"),(810,78,60,30,"Info")]
    for bx,by,bw,bh,txt in btns:
        fill_c=rgb(70,90,150) if "ON" in txt or txt in ["Parse","Info","Durfee","Hooks"] else rgb(45,55,85)
        draw_rounded_rect(bx,by,bw,bh,9, fill=fill_c, border=rgb(70,80,110), borderWidth=1, opacity=92)
        drawLabel(txt, bx+bw//2, by+bh//2, size=11, fill=rgb(230,240,255), bold=True)
    drawLabel("EXAMPLES ▼ 5 curated:", 20, 108, size=11, fill=rgb(140,150,190), align='left-top', bold=True)
    draw_dropdown(app)
    sel=EXAMPLES[app.dropdownSelected]
    drawLabel(sel["latex"], 360, 126, size=11, fill=rgb(255,230,150), align='left-top')
    drawLabel(sel["desc"], 360, 142, size=10, fill=rgb(160,170,200), align='left-top')
    if app.partition:
        drawLabel(latex_format(app.partition), app.diagramCenterX, 172, size=17, fill=rgb(240,240,255), bold=True)
        drawLabel(f"n={app.n} k={len(app.partition)} d={app.durfee} self={app.selfConj}  {app.pyodideStatus[:70]}", app.diagramCenterX, 190, size=10, fill=rgb(160,170,200))
    if app.showConjugate and app.conjugate:
        max_c=max(app.conjugate) if app.conjugate else 0
        cell=app.cellSize; gap=app.cellGap
        twc=max_c*(cell+gap)-gap
        thc=len(app.conjugate)*(cell+gap)-gap
        sxc=app.diagramCenterX - twc//2
        syc=app.diagramCenterY - thc//2
        for r,rl in enumerate(app.conjugate):
            for c in range(rl):
                x=sxc + c*(cell+gap)
                y=syc + r*(cell+gap)
                draw_cell_box(app,x,y,cell,r,c,False,False,is_ghost=True)
    if app.partition:
        for r,rl in enumerate(app.partition):
            for c in range(rl):
                x,y=get_cell_pos(app,r,c)
                prog=app.animT
                delay=(r*0.05 + c*0.02)
                local=max(0, min(1, (prog-delay)*3))
                if local<=0:
                    continue
                sz=int(app.cellSize*(0.2+0.8*local))
                ox=x+(app.cellSize-sz)//2
                oy=y+(app.cellSize-sz)//2
                is_h=(app.hover and app.hover[0]==r and app.hover[1]==c and app.hover[2]=='cell')
                is_d=(r<app.durfee and c<app.durfee)
                if app.modeBoxes:
                    draw_cell_box(app,ox,oy,sz,r,c,is_h,is_d)
                    if app.showHooks:
                        h=app.hooks[r][c] if r<len(app.hooks) and c<len(app.hooks[r]) else 0
                        drawLabel(str(h), x+app.cellSize//2, y+app.cellSize//2, size=11, fill=rgb(20,20,30), bold=True)
                else:
                    draw_cell_dot(app,ox,oy,sz,r,c,is_h,is_d)
                    if app.showHooks:
                        h=app.hooks[r][c] if r<len(app.hooks) and c<len(app.hooks[r]) else 0
                        drawLabel(str(h), x+app.cellSize//2, y+app.cellSize//2-10, size=9, fill=rgb(240,240,255), bold=True)
                if app.hover and app.hover[2]=='add_right' and app.hover[0]==r:
                    ax,ay=get_cell_pos(app,r,rl)
                    draw_rounded_rect(ax,ay,app.cellSize,app.cellSize,10, fill=rgb(100,255,150), opacity=25, border=rgb(100,255,150), borderWidth=2)
                    drawLabel("+", ax+app.cellSize//2, ay+app.cellSize//2, size=18, fill=rgb(100,255,150), bold=True)
        if app.hover and app.hover[2]=='add_new_row':
            max_len=max(app.partition) if app.partition else 1
            cell=app.cellSize; gap=app.cellGap
            tw=max_len*(cell+gap)-gap
            th=len(app.partition)*(cell+gap)-gap
            sx=app.diagramCenterX - tw//2
            sy=app.diagramCenterY - th//2
            ny=sy+len(app.partition)*(cell+gap)
            draw_rounded_rect(sx,ny,cell,cell,10, fill=rgb(100,200,255), opacity=28, border=rgb(100,200,255), borderWidth=2)
            drawLabel("+", sx+cell//2, ny+cell//2, size=18, fill=rgb(100,200,255), bold=True)
    rx=app.width-220; ry=170; rw=200; rh=380
    draw_rounded_rect(rx,ry,rw,rh,12, fill=gradient(rgb(28,32,52), rgb(22,26,42), start='top'), border=rgb(70,80,110), borderWidth=1, opacity=94)
    drawLabel("Partition Data", rx+rw//2, ry+16, size=13, fill=rgb(220,230,255), bold=True)
    y=ry+34
    def sl(lab,val):
        nonlocal y
        drawLabel(f"{lab}:", rx+12, y, size=11, fill=rgb(150,160,190), align='left-top')
        drawLabel(str(val), rx+rw-12, y, size=11, fill=rgb(235,245,255), align='right-top', bold=True)
        y+=18
    if app.partition:
        sl("λ", f"({','.join(map(str,app.partition))})")
        sl("n", app.n)
        sl("k", len(app.partition))
        sl("λ'", f"({','.join(map(str,app.conjugate))})")
        sl("Durfee", app.durfee)
        sl("Self", "Yes" if app.selfConj else "No")
        y+=4
        drawLabel("Hooks:", rx+12, y, size=10, fill=rgb(130,140,170), align='left-top')
        y+=12
        for r,row in enumerate(app.hooks[:5]):
            txt=" ".join(f"{h:2d}" for h in row[:8])
            drawLabel(f"r{r+1}:{txt}", rx+12, y, size=9, fill=rgb(200,210,230), align='left-top')
            y+=11
        y+=6
        drawLabel("Pyodide • p(n) in worker", rx+12, y, size=10, fill=rgb(120,180,255), bold=True, align='left-top')
        y+=12
        if app.pyodideComputing:
            drawLabel("Computing...", rx+12, y, size=10, fill=rgb(255,220,120), align='left-top')
        else:
            if app.partitionNumber is not None:
                vs=str(app.partitionNumber)
                if len(vs)>16:
                    vs=vs[:6]+"..."+vs[-4:]+f" ({len(str(app.partitionNumber))}d)"
                drawLabel(f"p({app.n})={vs}", rx+12, y, size=10, fill=rgb(200,230,255), align='left-top')
                y+=11
                if app.f_lambda:
                    drawLabel(f"f^λ={app.f_lambda} SYT", rx+12, y, size=9, fill=rgb(160,200,255), align='left-top')
    drawLabel("Click end add/remove • Dropdown 5 examples • b/c/d/h/i toggle • Enter parse", app.width//2, app.height-10, size=10, fill=rgb(120,130,160), align='center')
    if app.showInfo:
        draw_info_overlay(app)
    draw_rounded_rect(app.width-280, 18, 180, 26, 8, fill=rgb(30,50,90) if app.pyodideReady else rgb(60,30,30), border=rgb(80,120,200), borderWidth=1, opacity=88)
    drawLabel(app.pyodideStatus[:36], app.width-190, 31, size=10, fill=rgb(170,200,255), align='center')
