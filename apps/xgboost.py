
from scs import *
from browser import aio, window
import math, random, json, traceback

# REAL ONLY - 10-way MNIST - FLAT DATA {"data":[0,0,0,0.149,0.871,...]} chunk 784
# Fix: resp.text()+json.loads() not resp.json() (JS proxy breaks isinstance)

try:
    import extensions.pyodide as _py_ext
    PYODIDE_EXT_OK = True
    _py_candidates = ['run_python_async','run_python','run','exec','evaluate','run_code','execute','runPythonAsync']
except Exception:
    PYODIDE_EXT_OK = False
    _py_ext = None
    _py_candidates = []

def softmax(logits):
    m=max(logits)
    exps=[math.exp(l-m) for l in logits]
    s=sum(exps)+1e-12
    return [e/s for e in exps]

def cross_entropy_loss(y_true, probs):
    total=0.0; eps=1e-12
    for yt,pr in zip(y_true, probs):
        p=pr[yt] if yt < len(pr) else eps
        p=min(max(p,eps),1-eps)
        total+=-math.log(p)
    return total/len(y_true) if y_true else 0.0

def accuracy_multiclass(y_true, probs):
    c=0
    for yt,pr in zip(y_true, probs):
        pred=max(range(len(pr)), key=lambda k: pr[k])
        if pred==yt: c+=1
    return c/len(y_true) if y_true else 0.0

def find_best_stump_fast(X, target, n_feat_sample=16, min_leaf=8):
    n=len(X)
    if n==0: return 0,0.5,0.0,0.0,0.0
    d=len(X[0])
    feat_pool=random.sample(range(d), min(n_feat_sample,d))
    best_gain=-1e100; best_f=feat_pool[0]; best_thr=0.5; best_left=0.0; best_right=0.0
    for f in feat_pool:
        vals=[X[i][f] for i in range(n)]
        svals=sorted(vals)
        thr_candidates=[svals[n//4], svals[n//2], svals[3*n//4]]
        for thr in thr_candidates:
            ls=0.0; lc=0; rs=0.0; rc=0
            for i in range(n):
                if vals[i]<thr:
                    ls+=target[i]; lc+=1
                else:
                    rs+=target[i]; rc+=1
            if lc<min_leaf or rc<min_leaf: continue
            lm=ls/lc if lc else 0.0; rm=rs/rc if rc else 0.0
            gain=lc*lm*lm + rc*rm*rm
            if gain>best_gain:
                best_gain=gain; best_f=f; best_thr=thr; best_left=lm; best_right=rm
    return best_f,best_thr,best_left,best_right,best_gain

def train_val_split_10way(X,y,ratio=0.78):
    # Stratified split - ENSURE non-empty even with small data
    by_class={}
    for xi,yi in zip(X,y):
        by_class.setdefault(yi, []).append((xi,yi))
    Xtr=[]; ytr=[]; Xva=[]; yva=[]
    for c in range(10):
        lst=by_class.get(c, [])
        if not lst: continue
        random.shuffle(lst)
        n=len(lst)
        n_tr = max(1, int(n*ratio)) if n>1 else 1
        if n_tr>=n: n_tr=n-1 if n>1 else 1
        for xi,yi in lst[:n_tr]:
            Xtr.append(xi); ytr.append(yi)
        for xi,yi in lst[n_tr:]:
            Xva.append(xi); yva.append(yi)
    # Fallback if val empty
    if not Xva and Xtr:
        # move 22% to val
        cut=int(len(Xtr)*0.78)
        Xva=Xtr[cut:]; yva=ytr[cut:]
        Xtr=Xtr[:cut]; ytr=ytr[:cut]
    # Shuffle
    if Xtr:
        combined=list(zip(Xtr,ytr)); random.shuffle(combined)
        Xtr,ytr=zip(*combined); Xtr,ytr=list(Xtr),list(ytr)
    if Xva:
        combined=list(zip(Xva,yva)); random.shuffle(combined)
        Xva,yva=zip(*combined); Xva,yva=list(Xva),list(yva)
    return list(Xtr),list(ytr),list(Xva),list(yva)

async def resilient_pyodide_run(code_str):
    async def unwrap(res, max_depth=12):
        for _ in range(max_depth):
            if res is None: break
            if hasattr(res,'to_py'):
                try:
                    tmp=res.to_py()
                    if tmp is not None: res=tmp
                except Exception: pass
            try:
                if hasattr(res,'__await__'):
                    res=await res; continue
                if hasattr(res,'then') and callable(getattr(res,'then')):
                    res=await res; continue
                s=str(res)
                if '<coroutine' in s.lower():
                    if isinstance(res,str): return None
                    return None
            except Exception: pass
            break
        return res
    if PYODIDE_EXT_OK and _py_ext is not None:
        for name in _py_candidates:
            try:
                fn=getattr(_py_ext, name, None)
                if fn is None: continue
                raw=fn(code_str)
                res=await unwrap(raw)
                if res is None: continue
                if isinstance(res,str) and '<coroutine' in res.lower(): continue
                return res
            except Exception: continue
    try:
        if hasattr(window,'pyodide') and window.pyodide is not None:
            raw=await window.pyodide.runPythonAsync(code_str)
            res=await unwrap(raw)
            return res
    except Exception: pass
    return None

async def fetch_mnist_via_jsdelivr_REAL(app):
    base_url = "https://cdn.jsdelivr.net/npm/mnist@1.1.0/src/digits/{}.json"
    all_samples=[]
    for d in range(10):
        url = base_url.format(d)
        try:
            app.fetch_status=f"REAL {d}/9 fetching total {len(all_samples)}"
            resp = await window.fetch(url)
            if not resp.ok:
                raise Exception(f"HTTP {resp.status}")
            txt = await resp.text()
            if hasattr(txt,'to_py'):
                try: txt=txt.to_py()
                except Exception: pass
            txt=str(txt)
            parsed=json.loads(txt)
            raw=parsed
            if isinstance(raw, dict) and 'data' in raw:
                raw=raw['data']
            cnt=0
            if isinstance(raw, list) and len(raw)>0 and isinstance(raw[0], (int,float)):
                total=len(raw)
                n_images=total//784
                n_take=min(n_images, 120)
                for i in range(n_take):
                    chunk=raw[i*784:(i+1)*784]
                    if len(chunk)<784: break
                    pix=[]
                    for v in chunk:
                        try:
                            fv=float(v)
                            if fv>1.0: fv/=255.0
                            pix.append(max(0.0,min(1.0,fv)))
                        except Exception:
                            pix.append(0.0)
                    if len(pix)==784:
                        all_samples.append((pix,d))
                        cnt+=1
            elif isinstance(raw, list) and len(raw)>0 and isinstance(raw[0], dict):
                for item in raw[:120]:
                    try:
                        inp=item.get('input')
                        if inp is None: continue
                        flat=list(inp) if isinstance(inp,(list,tuple)) else []
                        if len(flat)<784: continue
                        pix=[max(0.0,min(1.0,float(v) if float(v)<=1.0 else float(v)/255.0)) for v in flat[:784]]
                        all_samples.append((pix,d)); cnt+=1
                    except Exception: continue
            app.fetch_status=f"Digit {d}: +{cnt} total {len(all_samples)}"
        except Exception as e:
            tb=traceback.format_exc()[:120]
            app.fetch_status=f"Digit {d} FAIL {str(e)[:40]} {tb} total {len(all_samples)}"
            continue
    if len(all_samples)<20:
        raise Exception(f"Only {len(all_samples)} samples")
    return all_samples

async def fetch_mnist_samples(app):
    app.fetch_status="Fetching REAL 10-way..."
    app.mnist_loaded=False
    try:
        samples = await fetch_mnist_via_jsdelivr_REAL(app)
        app.all_samples=samples
        # Build balanced sets
        by_class={i:[] for i in range(10)}
        for pix,lab in samples:
            if len(by_class[lab])<200:
                by_class[lab].append((pix,lab))
        balanced=[]
        for c in range(10):
            balanced.extend(by_class[c])
        random.shuffle(balanced)
        if not balanced:
            raise Exception("balanced empty")
        Xb=[p for p,_ in balanced]
        yb=[l for _,l in balanced]
        app.X_train_full, app.y_train_full = Xb, yb
        app.fetch_status=f"REAL {len(samples)} raw | {len(Xb)} balanced"
        X,y=Xb,yb
        if len(X)>1200:
            X=X[:1200]; y=y[:1200]
        Xtr,ytr,Xva,yva=train_val_split_10way(X,y,0.78)
        # CRITICAL: Ensure non-empty
        if not Xtr:
            raise Exception(f"Xtr empty after split X={len(X)}")
        app.X_train, app.y_train = Xtr, ytr
        app.X_val, app.y_val = Xva, yva
        app.F_train=[[0.0]*10 for _ in range(len(Xtr))]
        app.F_val=[[0.0]*10 for _ in range(len(Xva))]
        app.mnist_loaded=True
        app.fetch_status=f"REAL {len(samples)} | Train {len(Xtr)} Val {len(Xva)} | READY - Press Play"
        return
    except Exception as e:
        tb=traceback.format_exc()
        app.fetch_status=f"REAL FAILED: {str(e)[:80]} | {tb[:200]}"
        app.mnist_loaded=False
        app.all_samples=[]; app.X_train=[]; app.y_train=[]; app.X_val=[]; app.y_val=[]
        return

async def pyodide_train_reference(app):
    app.pyodide_status="Pyodide: disabled for REAL only"
    app.pyodide_ready=False

def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=20
    app.background=gradient(rgb(14,16,22), rgb(24,27,35), start='top')
    app.eta=0.12; app.max_trees=330; app.current_m=0
    app.trees=[]; app.loss_history=[]; app.val_loss_history=[]; app.acc_history=[]; app.train_acc_history=[]
    app.feature_importance=[0.0]*784; app.is_playing=False
    app.mnist_loaded=False; app.all_samples=[]; app.X_train=[]; app.y_train=[]
    app.X_val=[]; app.y_val=[]; app.F_train=[]; app.F_val=[]
    app.fetch_status="Fetching REAL 10-way..."; app.pyodide_status="REAL only"
    app.pyodide_ready=False; app.pyodide_reference=None
    app.ref_train_losses=[]; app.ref_val_losses=[]
    app.drawing=[0.0]*784; app.is_drawing=False
    app.prediction=None; app.prediction_probs=None
    app.show_rf=False; app.show_overfit=True
    app.selected_sample_idx=0; app.hover_feat=None; app.t=0
    aio.run(fetch_mnist_samples(app))

def onStep(app):
    app.t+=1
    try:
        if app.is_playing:
            if not app.mnist_loaded or not app.X_train:
                # Do not overwrite useful status, just pause
                app.is_playing=False
                if not app.fetch_status.startswith("REAL"):
                    app.fetch_status=f"Waiting REAL - {app.fetch_status[:40]}"
            else:
                if app.current_m < app.max_trees:
                    step_one_tree(app)
                else:
                    app.is_playing=False
    except Exception as e:
        app.fetch_status=f"Step err {e} {traceback.format_exc()[:60]}"
        app.is_playing=False

def step_one_tree(app):
    try:
        if not app.X_train: return
        probs_train=[softmax(f) for f in app.F_train]
        trees_this_iter=[]
        for c in range(10):
            target=[]
            for i in range(len(app.X_train)):
                y_onehot=1.0 if app.y_train[i]==c else 0.0
                target.append(y_onehot - probs_train[i][c])
            f_idx,thr,left_val,right_val,gain=find_best_stump_fast(app.X_train, target, n_feat_sample=16, min_leaf=8)
            for i,x in enumerate(app.X_train):
                app.F_train[i][c]+=app.eta*(left_val if x[f_idx]<thr else right_val)
            for i,x in enumerate(app.X_val):
                app.F_val[i][c]+=app.eta*(left_val if x[f_idx]<thr else right_val)
            app.feature_importance[f_idx]+=max(0.0,gain)
            trees_this_iter.append({"class":c,"feature":f_idx,"threshold":thr,"left":left_val,"right":right_val,"gain":gain})
        app.trees.append(trees_this_iter)
        probs_train_new=[softmax(f) for f in app.F_train]
        probs_val_new=[softmax(f) for f in app.F_val]
        app.loss_history.append(cross_entropy_loss(app.y_train, probs_train_new))
        app.val_loss_history.append(cross_entropy_loss(app.y_val, probs_val_new))
        app.acc_history.append(accuracy_multiclass(app.y_val, probs_val_new))
        app.train_acc_history.append(accuracy_multiclass(app.y_train, probs_train_new))
        app.current_m+=1
        if any(v>0.05 for v in app.drawing):
            predict_drawing(app)
    except Exception as e:
        app.fetch_status=f"train err {e} {traceback.format_exc()[:80]}"
        app.is_playing=False

def predict_drawing(app):
    if not app.trees: app.prediction=None; return
    f=[0.0]*10
    for trees_iter in app.trees:
        for stump in trees_iter:
            c=stump["class"]
            if app.drawing[stump["feature"]] < stump["threshold"]:
                f[c]+=app.eta*stump["left"]
            else:
                f[c]+=app.eta*stump["right"]
    probs=softmax(f)
    pred=max(range(10), key=lambda c: probs[c])
    app.prediction=pred; app.prediction_probs=probs

def reset_ensemble(app):
    app.trees=[]; app.loss_history=[]; app.val_loss_history=[]; app.acc_history=[]; app.train_acc_history=[]
    if app.X_train:
        app.F_train=[[0.0]*10 for _ in range(len(app.X_train))]
        app.F_val=[[0.0]*10 for _ in range(len(app.X_val))]
    else:
        app.F_train=[]; app.F_val=[]
    app.current_m=0; app.feature_importance=[0.0]*784; app.is_playing=False; app.prediction=None

def recompute_F(app):
    if not app.X_train: return
    app.F_train=[[0.0]*10 for _ in range(len(app.X_train))]
    app.F_val=[[0.0]*10 for _ in range(len(app.X_val))]
    app.feature_importance=[0.0]*784
    for trees_iter in app.trees:
        for stump in trees_iter:
            f_idx=stump["feature"]; thr=stump["threshold"]; lv=stump["left"]; rv=stump["right"]; c=stump["class"]
            app.feature_importance[f_idx]+=max(0.0,stump["gain"])
            for i,x in enumerate(app.X_train):
                app.F_train[i][c]+=app.eta*(lv if x[f_idx]<thr else rv)
            for i,x in enumerate(app.X_val):
                app.F_val[i][c]+=app.eta*(lv if x[f_idx]<thr else rv)
    if any(v>0.05 for v in app.drawing):
        predict_drawing(app)

def paint_at(app,mx,my):
    gx=int((mx-30)//8); gy=int((my-110)//8)
    for dy in range(-1,2):
        for dx in range(-1,2):
            ny=gy+dy; nx=gx+dx
            if 0<=ny<28 and 0<=nx<28:
                dist=math.hypot(dx,dy)
                if dist>1.2: continue
                intensity=0.95 if dist<0.5 else 0.25
                idx=ny*28+nx
                app.drawing[idx]=min(1.0, app.drawing[idx]+intensity)

def onMousePress(app,mx,my):
    if 360<=mx<=430 and 12<=my<=36:
        app.is_playing=not app.is_playing
        return
    if 440<=mx<=485 and 12<=my<=36:
        step_one_tree(app); return
    if 495<=mx<=555 and 12<=my<=36:
        reset_ensemble(app); return
    if 570<=mx<=590 and 12<=my<=22:
        app.eta=min(0.5,app.eta+0.02); return
    if 570<=mx<=590 and 26<=my<=36:
        app.eta=max(0.01,app.eta-0.02); return
    if 860<=mx<=1020 and 12<=my<=36:
        app.show_rf=not app.show_rf; return
    if 30<=mx<=120 and 338<=my<=358:
        app.drawing=[0.0]*784; app.prediction=None; return
    if 30<=mx<=254 and 110<=my<=334:
        app.is_drawing=True; paint_at(app,mx,my); return
    if 20<=mx<=280 and 440<=my<=560:
        if app.all_samples:
            idx_x=int((mx-20)//50); idx_y=int((my-440)//50)
            idx_x=max(0,min(idx_x,4)); idx_y=max(0,min(idx_y,1))
            idx=idx_y*5+idx_x
            shown=[]; seen=set()
            for pix,lab in app.all_samples:
                if lab not in seen and len(shown)<10:
                    shown.append((pix,lab)); seen.add(lab)
            if len(shown)<10: shown=app.all_samples[:10]
            if idx < len(shown):
                pix,lab=shown[idx]
                app.selected_sample_idx=idx
                app.drawing=pix[:]; predict_drawing(app)
        return
    if 720<=mx<=944 and 120<=my<=344:
        col=int((mx-720)//8); row=int((my-120)//8)
        if 0<=row<28 and 0<=col<28:
            app.hover_feat=row*28+col
        return

def onMouseDrag(app,mx,my):
    if app.is_drawing and 30<=mx<=254 and 110<=my<=334:
        paint_at(app,mx,my)

def onMouseRelease(app,mx,my):
    app.is_drawing=False
    if any(v>0.05 for v in app.drawing):
        predict_drawing(app)

def onKeyPress(app,key):
    if key=='space':
        app.is_playing=not app.is_playing
    elif key.lower()=='r': reset_ensemble(app)
    elif key=='Right': step_one_tree(app)
    elif key=='Left':
        if app.trees:
            app.trees.pop(); app.loss_history.pop(); app.val_loss_history.pop(); app.acc_history.pop(); app.train_acc_history.pop()
            app.current_m-=1; recompute_F(app)
    elif key.lower()=='c': app.drawing=[0.0]*784; app.prediction=None
    elif key=='+' or key=='=': app.eta=min(0.5,app.eta+0.02)
    elif key=='-' or key=='_': app.eta=max(0.01,app.eta-0.02)
    elif key.lower()=='o': app.show_overfit=not app.show_overfit
    elif key.lower()=='f': app.show_rf=not app.show_rf

def redrawAll(app):
    drawRect(0,0,app.width,app.height, fill=gradient(rgb(14,16,22), rgb(24,27,35), start='top'))
    drawRect(0,0,app.width,50, fill=rgb(18,20,28), border=rgb(40,45,60), borderWidth=1)
    drawLabel("XGBoost Lab - REAL MNIST ONLY - FLAT FIX v3 FINAL", 14, 14, size=14, bold=True, fill=rgb(220,230,255), align='left-top')
    drawLabel("F_m=F_{m-1}+eta*h_m | REAL 10-way flat chunk 784 | resp.text()+json.loads", 14, 32, size=8, fill=rgb(130,255,130), align='left-top')
    play_col=rgb(0,212,255) if app.is_playing else rgb(55,65,85)
    drawRect(360,12,70,26, fill=play_col, border=rgb(90,110,140), borderWidth=1, roundness=7)
    drawLabel("Pause" if app.is_playing else "Play", 395, 25, size=11, bold=True, fill=rgb(10,15,25) if app.is_playing else rgb(200,220,255))
    drawRect(440,12,45,26, fill=rgb(40,45,60), border=rgb(70,80,100), borderWidth=1, roundness=7)
    drawLabel("Step", 462, 25, size=11, fill=rgb(200,220,255))
    drawRect(495,12,60,26, fill=rgb(40,45,60), border=rgb(70,80,100), borderWidth=1, roundness=7)
    drawLabel("Reset", 525, 25, size=11, fill=rgb(200,220,255))
    drawLabel(f"eta={app.eta:.2f}", 600, 15, size=11, bold=True, fill=rgb(180,200,220), align='left-top')
    drawRect(570,12,18,10, fill=rgb(50,60,80), border=rgb(80,90,110), borderWidth=1, roundness=3)
    drawLabel("+", 579, 17, size=9, fill=rgb(200,220,255))
    drawRect(570,26,18,10, fill=rgb(50,60,80), border=rgb(80,90,110), borderWidth=1, roundness=3)
    drawLabel("-", 579, 31, size=9, fill=rgb(200,220,255))
    drawLabel("learn rate", 625, 20, size=9, fill=rgb(110,125,145), align='left-top')
    rf_fill=rgb(255,0,110) if app.show_rf else rgb(45,50,65)
    drawRect(860,12,160,26, fill=rf_fill, border=rgb(90,60,80), borderWidth=1, roundness=7)
    drawLabel("RF vs Boosting", 940, 25, size=11, bold=True, fill=rgb(255,220,230) if app.show_rf else rgb(180,190,210))
    drawRect(12,60,276,620, fill=rgb(20,23,31), border=rgb(35,40,55), borderWidth=1, roundness=12)
    drawLabel("INPUT: Draw 0-9 - REAL MNIST 28x28", 24, 72, size=11, bold=True, fill=rgb(180,200,230), align='left-top')
    drawLabel("Each pixel = feature (784-d) REAL", 24, 88, size=9, fill=rgb(110,255,110), align='left-top')
    drawRect(28,100,228,228, fill=rgb(8,10,15), border=rgb(60,70,90), borderWidth=1, roundness=8)
    for r in range(28):
        for c in range(28):
            v=app.drawing[r*28+c]
            if v>0.01:
                gray=int(20+v*235)
                drawRect(30+c*8, 102+r*8, 8, 8, fill=rgb(gray,gray,gray))
    for i in range(0,29,7):
        drawLine(30+i*8,102,30+i*8,330, lineWidth=0.4, fill=rgb(30,35,50))
        drawLine(30,102+i*8,254,102+i*8, lineWidth=0.4, fill=rgb(30,35,50))
    drawRect(30,338,90,20, fill=rgb(45,50,65), border=rgb(70,80,100), borderWidth=1, roundness=6)
    drawLabel("Clear C", 75, 348, size=10, bold=True, fill=rgb(200,220,255))
    drawLabel("10-way REAL", 140, 348, size=9, bold=True, fill=rgb(130,255,130), align='left-top')
    if app.prediction is not None and app.prediction_probs is not None:
        col=rgb(0,212,255)
        prob=app.prediction_probs[app.prediction]
        drawRect(30,364,224,36, fill=rgb(30,35,50), border=col, borderWidth=1, roundness=8)
        drawLabel(f"Pred: {app.prediction}  {prob*100:.1f}%", 142, 376, size=14, bold=True, fill=col)
        drawLabel("softmax REAL", 142, 390, size=8, fill=rgb(120,135,155))
        for c in range(10):
            p=app.prediction_probs[c] if c < len(app.prediction_probs) else 0
            x0=30 + c*22; y0=406; h=p*36
            bar_col=rgb(0,212,255) if c==app.prediction else rgb(60,70,90)
            drawRect(x0, y0+36-h, 18, h, fill=bar_col, border=rgb(80,90,110), borderWidth=0.5, roundness=2)
            drawLabel(str(c), x0+9, y0+46, size=8, bold=True, fill=rgb(180,190,210))
    else:
        drawRect(30,364,224,60, fill=rgb(20,23,31), border=rgb(35,40,55), borderWidth=1, roundness=6)
        drawLabel("Draw any digit 0-9", 142, 384, size=11, fill=rgb(100,115,135))
        drawLabel("REAL 10-way softmax", 142, 400, size=9, fill=rgb(90,255,90))
    drawLabel("Samples REAL - click:", 24, 432, size=9, fill=rgb(120,255,120), align='left-top')
    if app.all_samples:
        shown=[]; seen=set()
        for pix,lab in app.all_samples:
            if lab not in seen and len(shown)<10:
                shown.append((pix,lab)); seen.add(lab)
        if len(shown)<10: shown=app.all_samples[:10]
        for i,(pix,lab) in enumerate(shown[:10]):
            x0=20 + (i%5)*50; y0=446 + (i//5)*50
            for r in range(28):
                for c in range(28):
                    v=pix[r*28+c]
                    if v>0.15:
                        gray=int(v*200+40)
                        drawRect(x0 + c*0.85, y0 + r*0.85, 0.9, 0.9, fill=rgb(gray,gray,gray))
            if i==app.selected_sample_idx % 10:
                drawRect(x0-1,y0-1,25,25, fill=None, border=rgb(0,212,255), borderWidth=1.2, roundness=2)
            drawLabel(str(lab), x0+12, y0+28, size=8, bold=True, fill=rgb(160,175,190))
    drawLabel(app.fetch_status[:70], 24, 556, size=7, fill=rgb(110,255,110), align='left-top')
    drawRect(300,60,388,620, fill=rgb(22,25,34), border=rgb(35,40,55), borderWidth=1, roundness=12)
    drawLabel("BOOSTING: Multinomial 10-way REAL", 312, 72, size=12, bold=True, fill=rgb(200,220,255), align='left-top')
    drawLabel(f"Trees {app.current_m}/{app.max_trees} (x10) eta={app.eta:.2f} REAL", 312, 88, size=8, fill=rgb(130,145,165), align='left-top')
    if app.show_rf:
        drawRect(312,108,180,90, fill=rgb(30,20,30), border=rgb(80,40,60), borderWidth=1, roundness=8)
        drawLabel("Random Forest (parallel)", 320,116, size=9, bold=True, fill=rgb(255,150,180), align='left-top')
        for i in range(5):
            x=322+i*32; y=132
            drawRect(x,y,24,32, fill=rgb(60,40,55), border=rgb(120,70,90), borderWidth=1, roundness=4)
            drawLabel(f"T{i+1}", x+12,y+16, size=8, fill=rgb(220,180,200))
        drawRect(504,108,172,90, fill=rgb(20,30,40), border=rgb(40,80,100), borderWidth=1, roundness=8)
        drawLabel("Boosting (sequential)", 512,116, size=9, bold=True, fill=rgb(120,220,255), align='left-top')
        for i in range(5):
            x=512+i*30; y=132
            col=rgb(0,212,255) if i<app.current_m else rgb(40,60,75)
            drawRect(x,y,24,32, fill=col, border=rgb(0,180,220), borderWidth=1, roundness=4)
            if i>0: drawLine(x-6,y+16,x,y+16, lineWidth=1.2, fill=rgb(0,212,255))
            drawLabel(f"h{i+1}", x+12,y+16, size=7, bold=True, fill=rgb(10,20,30) if i<app.current_m else rgb(120,140,160))
    else:
        if app.trees:
            last_iter=app.trees[-1]
            txt=", ".join([f"{s['class']}:({s['feature']%28},{s['feature']//28})" for s in last_iter[:3]])
            drawLabel(f"Weak learners h_{app.current_m} x10: {txt}...", 312,114, size=8, bold=True, fill=rgb(180,220,255), align='left-top')
            drawLabel(f"Each stump fits y_c - softmax(F)_c", 312,128, size=8, fill=rgb(130,150,175), align='left-top')
            drawRect(312,142,56,56, fill=rgb(10,15,25), border=rgb(0,212,255), borderWidth=1, roundness=6)
            best_stump=max(last_iter, key=lambda s: s['gain'])
            fr=best_stump['feature']//28; fc=best_stump['feature']%28
            for r in range(28):
                for c in range(28):
                    if r==fr and c==fc:
                        drawRect(312+c*2,142+r*2,2.5,2.5, fill=rgb(255,183,3))
            drawLabel(f"Best pixel ({fc},{fr}) cls {best_stump['class']} thr {best_stump['threshold']:.2f}", 380,148, size=7, fill=rgb(140,160,185), align='left-top')
            drawLabel("Val samples - residuals drives next:", 380,162, size=7, fill=rgb(140,160,185), align='left-top')
            for i in range(min(5, len(app.X_val))):
                x=380+i*52; y=174
                pix=app.X_val[i]
                for r in range(28):
                    for c in range(28):
                        v=pix[r*28+c]
                        if v>0.1:
                            gray=int(30+v*180)
                            drawRect(x + c*1.2, y + r*1.2, 1.3,1.3, fill=rgb(gray,gray,gray))
                drawLabel(str(app.y_val[i]), x+17, y+40, size=9, bold=True, fill=rgb(0,212,255))
        else:
            drawLabel(f"No trees yet - X={len(app.X_train)} REAL={app.mnist_loaded}", 312,120, size=10, fill=rgb(120,255,120), align='left-top')
            drawLabel("Press Play - REAL DATA ONLY - FINAL", 312,138, size=9, fill=rgb(100,255,100), align='left-top')
    drawRect(312,220,368,130, fill=rgb(14,18,26), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("Loss vs #trees - cyan train / gold val", 320,228, size=9, bold=True, fill=rgb(180,200,220), align='left-top')
    drawLine(338,246,338,332, lineWidth=1, fill=rgb(60,70,90))
    drawLine(338,332,662,332, lineWidth=1, fill=rgb(60,70,90))
    drawLabel("0", 328,334, size=8, fill=rgb(100,115,135))
    drawLabel(f"{app.max_trees}", 650,334, size=8, fill=rgb(100,115,135))
    if app.loss_history:
        max_loss=max(max(app.loss_history), max(app.val_loss_history) if app.val_loss_history else 0, 0.7)
        min_loss=min(min(app.loss_history), min(app.val_loss_history) if app.val_loss_history else 0, 0.1)
        rng=max_loss-min_loss if max_loss-min_loss>0.1 else 0.1
        prev_x=None; prev_y=None
        for i,loss in enumerate(app.loss_history):
            x=338 + (i/app.max_trees)*324; y=332 - ((loss-min_loss)/rng)*80
            if prev_x is not None: drawLine(prev_x,prev_y,x,y, lineWidth=1.3, fill=rgb(0,212,255))
            prev_x,prev_y=x,y
        prev_x=None; prev_y=None
        for i,loss in enumerate(app.val_loss_history):
            x=338 + (i/app.max_trees)*324; y=332 - ((loss-min_loss)/rng)*80
            if prev_x is not None: drawLine(prev_x,prev_y,x,y, lineWidth=1.3, fill=rgb(255,183,3))
            prev_x,prev_y=x,y
        if app.current_m>0:
            x_cur=338 + (app.current_m/app.max_trees)*324
            drawLine(x_cur,246,x_cur,332, lineWidth=1, fill=rgb(200,220,255), dashes=(2,2))
    if app.acc_history:
        acc=app.acc_history[-1]
        drawLabel(f"Val Acc {acc*100:.1f}% REAL", 320,320, size=9, bold=True, fill=rgb(180,220,255), align='left-top')
    drawRect(312,358,368,50, fill=rgb(18,22,32), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("F_m = F_{m-1} + eta*h_m  h_m approx y - softmax(F)", 320,366, size=9, fill=rgb(200,220,255), align='left-top')
    drawLabel("10 stumps per round, one per class", 320,382, size=8, fill=rgb(120,140,165), align='left-top')
    drawLabel(f"Ensemble timeline - {app.current_m*10} stumps:", 312,418, size=9, bold=True, fill=rgb(180,200,220), align='left-top')
    for i in range(min(app.current_m, 80)):
        trees_iter=app.trees[i] if i < len(app.trees) else []
        max_gain=max([s['gain'] for s in trees_iter]) if trees_iter else 0
        x=312 + (i%40)*9; y=430 + (i//40)*14
        col_int=int(60 + (max_gain/5)*195) if max_gain>0 else 60
        col_int=min(255,col_int)
        drawRect(x,y,7,8, fill=rgb(col_int,col_int//2,30), border=rgb(80,60,30), borderWidth=0.4, roundness=1)
    drawRect(700,60,338,620, fill=rgb(20,23,31), border=rgb(35,40,55), borderWidth=1, roundness=12)
    drawLabel("RESEARCH VIEW - REAL ONLY", 712,72, size=11, bold=True, fill=rgb(220,255,130), align='left-top')
    drawLabel("No synthetic, no CSV", 712,88, size=9, fill=rgb(130,255,130), align='left-top')
    drawRect(718,100,228,228, fill=rgb(10,12,18), border=rgb(50,60,80), borderWidth=1, roundness=8)
    max_imp=max(app.feature_importance) if max(app.feature_importance)>0 else 1
    for r in range(28):
        for c in range(28):
            imp=app.feature_importance[r*28+c]
            if imp>0.01*max_imp:
                norm=imp/max_imp
                if norm<0.5:
                    t=norm*2
                    col=rgb(int(10+t*0), int(15+t*80), int(20+t*180))
                else:
                    t=(norm-0.5)*2
                    col=rgb(int(t*255), int(80+t*103), int(180*(1-t)))
                drawRect(720+c*8,102+r*8,8,8, fill=col)
    if app.hover_feat is not None:
        hr=app.hover_feat//28; hc=app.hover_feat%28
        drawRect(720+hc*8,102+hr*8,8,8, fill=None, border=rgb(255,255,255), borderWidth=1.5)
        drawLabel(f"pixel ({hc},{hr}) imp {app.feature_importance[app.hover_feat]:.1f}", 720,332, size=8, fill=rgb(200,220,255), align='left-top')
    drawLabel("Feature importance: 10-way REAL", 712,340, size=9, fill=rgb(140,255,140), align='left-top')
    drawRect(712,352,316,86, fill=rgb(16,20,28), border=rgb(40,50,70), borderWidth=1, roundness=8)
    drawLabel("Softmax cross-entropy REAL:", 720,360, size=9, bold=True, fill=rgb(180,200,220), align='left-top')
    drawLabel("L = -sum_i sum_c p_{i,c} log q_{i,c}", 720,374, size=9, fill=rgb(200,220,255), align='left-top')
    drawLabel("q = softmax(F) = exp(F_c)/sum_k exp(F_k)", 720,386, size=8, fill=rgb(150,170,200), align='left-top')
    drawLabel("grad = q - p -> h_m ~ p - q", 720,400, size=9, bold=True, fill=rgb(0,212,255), align='left-top')
    drawLabel("F_m = F_{m-1}+eta*h_m  10 logits REAL", 720,412, size=8, fill=rgb(160,180,210), align='left-top')
    drawLabel("330 trees x10 = 3300 stumps REAL", 720,424, size=8, fill=rgb(130,255,130), align='left-top')
    drawRect(712,444,316,84, fill=rgb(18,22,32), border=rgb(35,45,65), borderWidth=1, roundness=8)
    drawLabel("Pyodide worker:", 720,452, size=9, bold=True, fill=rgb(180,200,220), align='left-top')
    status=app.pyodide_status
    drawLabel(status[:58], 720,466, size=8, fill=rgb(120,200,150) if app.pyodide_ready else rgb(200,150,120), align='left-top')
    if len(status)>58:
        drawLabel(status[58:116], 720,478, size=8, fill=rgb(120,200,150) if app.pyodide_ready else rgb(200,150,120), align='left-top')
    if app.pyodide_ready and app.pyodide_reference:
        acc=app.pyodide_reference.get("accuracy",0)
        drawLabel(f"sklearn GBM 330: {acc*100:.1f}% REAL", 720,492, size=8, fill=rgb(160,200,180), align='left-top')
    else:
        drawLabel("Brython GBM - REAL only - fixed", 720,492, size=8, fill=rgb(140,255,140), align='left-top')
    drawRect(712,534,316,110, fill=rgb(14,18,26), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("Research insights REAL:", 720,542, size=9, bold=True, fill=rgb(220,255,130), align='left-top')
    notes=["* 10 logits, softmax REAL","* stumps depth1 high bias low var","* boosting reduces bias seq","* eta 0.01-0.3 improves gen","* 330 trees high cap","* MNIST 784-d, 10 classes REAL"]
    for i,line in enumerate(notes):
        drawLabel(line, 720,556+i*12, size=8, fill=rgb(130,255,130), align='left-top')
    drawLabel(f"REAL ONLY - {app.fetch_status[:60]}", 14, 686, size=8, fill=rgb(80,255,80), align='left-top')
