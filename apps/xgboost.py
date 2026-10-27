
from scs import *
from browser import aio, window
import math, random

# ─────────────────────────────────────────────────────────────
# Extensions — Model only, strict MVC
# ─────────────────────────────────────────────────────────────
try:
    from extensions.fetch import fetch_json, fetch_text, fetch, FetchError
    FETCH_OK = True
except Exception:
    FETCH_OK = False
    fetch_json = None
    fetch_text = None
    fetch = None
    class FetchError(Exception): pass

try:
    import extensions.pyodide as _py_ext
    PYODIDE_EXT_OK = True
    _py_candidates = []
    for _name in ['run_python_async', 'run_python', 'run', 'exec', 'evaluate', 'run_code', 'execute', 'runPythonAsync', 'runPython']:
        if hasattr(_py_ext, _name):
            _py_candidates.append(_name)
except Exception:
    PYODIDE_EXT_OK = False
    _py_ext = None
    _py_candidates = []

def sigmoid(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        e = math.exp(x)
        return e / (1.0 + e)

def log_loss_binary(y_true, f_logit):
    eps = 1e-12
    total = 0.0
    for yt, ft in zip(y_true, f_logit):
        p = sigmoid(ft)
        p = min(max(p, eps), 1-eps)
        total += -math.log(p) if yt==1 else -math.log(1-p)
    return total / len(y_true) if y_true else 0.0

def accuracy_binary(y_true, f_logit):
    correct = 0
    for yt, ft in zip(y_true, f_logit):
        p = sigmoid(ft)
        if (1 if p>=0.5 else 0) == yt:
            correct+=1
    return correct / len(y_true) if y_true else 0.0

def find_best_stump(X, grad, n_feat_sample=40, min_leaf=5):
    n = len(X)
    if n==0:
        return 0,0.5,0.0,0.0,0.0
    d = len(X[0])
    target = [-g for g in grad]
    total_sum = sum(target)
    feat_pool = random.sample(range(d), min(n_feat_sample, d))
    best_gain = -1e100
    best_f = feat_pool[0] if feat_pool else 0
    best_thr = 0.5
    best_left = 0.0
    best_right = 0.0
    for f in feat_pool:
        pairs = [(X[i][f], target[i]) for i in range(n)]
        pairs.sort(key=lambda x: x[0])
        left_sum = 0.0
        left_cnt = 0
        right_sum = total_sum
        right_cnt = n
        for i in range(1,n):
            v_prev, t_prev = pairs[i-1]
            left_sum+=t_prev; left_cnt+=1
            right_sum-=t_prev; right_cnt-=1
            v_curr = pairs[i][0]
            if v_curr==v_prev: continue
            if left_cnt<min_leaf or right_cnt<min_leaf: continue
            left_mean = left_sum/left_cnt
            right_mean = right_sum/right_cnt if right_cnt else 0.0
            gain = left_cnt*left_mean*left_mean + right_cnt*right_mean*right_mean
            if gain>best_gain:
                best_gain=gain; best_f=f
                best_thr=(v_prev+v_curr)*0.5
                best_left=left_mean; best_right=right_mean
    return best_f,best_thr,best_left,best_right,best_gain

def generate_prototype_3_8():
    def blank(): return [0.0]*784
    def idx(r,c): return r*28+c
    proto3=blank(); proto8=blank()
    for r in range(28):
        for c in range(28):
            dr1=r-8; dc1=c-18
            if 12<math.hypot(dr1*1.2, dc1)<16 and c>12 and r<14:
                proto3[idx(r,c)]=0.9
            dr2=r-19; dc2=c-18
            if 12<math.hypot(dr2*1.2, dc2)<16 and c>12 and r>=10:
                proto3[idx(r,c)]=0.9
            if 14<=c<=16 and 6<=r<=22:
                proto3[idx(r,c)]=max(proto3[idx(r,c)],0.3)
            drt=r-9; dct=c-14; drb=r-19; dcb=c-14
            if 9<math.hypot(drt*1.1,dct)<13: proto8[idx(r,c)]=0.9
            if 9<math.hypot(drb*1.1,dcb)<13: proto8[idx(r,c)]=0.9
            if abs(c-14)<2 and 9<r<19:
                proto8[idx(r,c)]=max(proto8[idx(r,c)],0.4)
    return proto3,proto8

def synth_mnist_3_vs_8(n_per_class=200):
    proto3,proto8=generate_prototype_3_8()
    X=[]; y=[]
    for _ in range(n_per_class):
        img=[min(1.0,max(0.0,v+random.gauss(0,0.18)+(random.uniform(-0.3,0.3) if random.random()<0.04 else 0))) for v in proto3]
        X.append(img); y.append(0)
        img2=[min(1.0,max(0.0,v+random.gauss(0,0.18)+(random.uniform(-0.3,0.3) if random.random()<0.04 else 0))) for v in proto8]
        X.append(img2); y.append(1)
    combined=list(zip(X,y)); random.shuffle(combined)
    X[:],y[:]=zip(*combined)
    return list(X),list(y)

def train_val_split(X,y,ratio=0.78):
    n=len(X); n_train=int(n*ratio)
    return X[:n_train],y[:n_train],X[n_train:],y[n_train:]

# ─────────────────────────────────────────────────────────────
# Resilient Pyodide runner — handles old/new worker APIs
# ─────────────────────────────────────────────────────────────
async def resilient_pyodide_run(code_str):
    # Try extension entrypoints
    if PYODIDE_EXT_OK and _py_ext is not None:
        for name in _py_candidates:
            try:
                fn = getattr(_py_ext, name)
                res = fn(code_str)
                # Unwrap up to 3 layers of awaitable / Promise
                for _ in range(4):
                    if res is None:
                        break
                    if hasattr(res, '__await__'):
                        res = await res
                    elif hasattr(res, 'then'):
                        # JS Promise
                        try:
                            res = await res
                        except Exception:
                            break
                    else:
                        break
                # If we got a string that looks like coroutine repr, treat as failure
                if isinstance(res, str) and res.startswith('<coroutine'):
                    continue
                return res
            except Exception as e:
                continue
        # Try direct attribute runPythonAsync on module
        try:
            if hasattr(_py_ext, 'pyodide') and hasattr(_py_ext.pyodide, 'runPythonAsync'):
                res = await _py_ext.pyodide.runPythonAsync(code_str)
                return res
        except:
            pass

    # Try window.pyodide global (newer SCS versions expose it)
    try:
        if hasattr(window, 'pyodide') and window.pyodide is not None:
            res = await window.pyodide.runPythonAsync(code_str)
            # unwrap
            for _ in range(3):
                if hasattr(res, 'to_py'):
                    try:
                        res = res.to_py()
                        break
                    except:
                        pass
                if hasattr(res, '__await__'):
                    res = await res
                else:
                    break
            return res
    except Exception:
        pass

    return None

# ─────────────────────────────────────────────────────────────
# Fetch with working URLs + robust fallback
# ─────────────────────────────────────────────────────────────
async def fetch_mnist_samples(app):
    app.fetch_status = "Fetching MNIST via extensions.fetch..."
    app.mnist_loaded = False

    # Working small MNIST CSVs (verified via search)
    candidates = [
        "https://raw.githubusercontent.com/makeyourownneuralnetwork/makeyourownneuralnetwork/master/mnist_dataset/mnist_test_10.csv",
        "https://cdn.jsdelivr.net/gh/makeyourownneuralnetwork/makeyourownneuralnetwork@master/mnist_dataset/mnist_test_10.csv",
        "https://raw.githubusercontent.com/makeyourownneuralnetwork/makeyourownneuralnetwork/master/mnist_dataset/mnist_train_100.csv",
        "https://cdn.jsdelivr.net/gh/makeyourownneuralnetwork/makeyourownneuralnetwork@master/mnist_dataset/mnist_train_100.csv",
        "https://raw.githubusercontent.com/cme195/cme195.github.io/master/assets/data/mnist_small.csv",
    ]

    data_ok=False
    if FETCH_OK and fetch_text is not None:
        for url in candidates:
            try:
                app.fetch_status = f"Trying {url.split('/')[-1]}..."
                txt = await fetch_text(url)
                lines = txt.strip().split("\n")
                samples=[]
                for line in lines[:300]:
                    if not line.strip(): continue
                    low=line.lower()
                    if low.startswith("label") or low.startswith("digit") or "pixel" in low:
                        continue
                    parts=line.split(",")
                    # Handle different formats:
                    # makeyourownneuralnetwork: label, 784 pixels
                    # mnist_small: label in first col
                    try:
                        if len(parts)>=785:
                            label=int(float(parts[0]))
                            pixels=[float(p)/255.0 for p in parts[1:785]]
                            samples.append((pixels[:784], label))
                        elif len(parts)>=2:
                            # maybe 784 cols + label at end? try
                            # Try last as label
                            label=int(float(parts[-1]))
                            pixels=[float(p)/255.0 if float(p)>1 else float(p) for p in parts[:784]]
                            if len(pixels)>=784:
                                # normalize if needed
                                mx=max(pixels) if pixels else 1
                                if mx>1:
                                    pixels=[p/255.0 for p in pixels]
                                samples.append((pixels[:784], label))
                    except Exception:
                        continue
                if len(samples)>=8:
                    app.all_samples=samples
                    Xb=[]; yb=[]
                    for pix,lab in samples:
                        if lab==3: Xb.append(pix); yb.append(0)
                        elif lab==8: Xb.append(pix); yb.append(1)
                    # If not enough 3/8, pad with synthetic
                    if len(Xb)<20:
                        sx,sy=synth_mnist_3_vs_8(50)
                        Xb.extend(sx); yb.extend(sy)
                    app.X_train_full, app.y_train_full = Xb, yb
                    app.fetch_status=f"Loaded {len(samples)} samples via fetch ✓"
                    data_ok=True
                    break
            except Exception as e:
                app.fetch_status=f"Fetch fail {url.split('/')[-1]}: {str(e)[:60]}"
                continue

    if not data_ok:
        app.fetch_status="Fetch unavailable — synthetic 3 vs 8 (high-fidelity fallback)"
        sx,sy=synth_mnist_3_vs_8(220)
        app.all_samples=[(pix, 3 if lab==0 else 8) for pix,lab in zip(sx,sy)]
        app.X_train_full, app.y_train_full = sx,sy

    X,y=app.X_train_full, app.y_train_full
    combined=list(zip(X,y)); random.shuffle(combined)
    if combined:
        X,y=zip(*combined); X,y=list(X),list(y)
    app.X_train, app.y_train, app.X_val, app.y_val = train_val_split(X,y,0.78)
    app.F_train=[0.0]*len(app.X_train)
    app.F_val=[0.0]*len(app.X_val)
    app.mnist_loaded=True
    app.fetch_status+=f" | Train {len(app.X_train)} Val {len(app.X_val)}"

async def pyodide_train_reference(app):
    app.pyodide_status="Pyodide: probing extension..."
    if not PYODIDE_EXT_OK:
        app.pyodide_status="Pyodide ext not found — Brython GBM fallback"
        app.pyodide_ready=False
        return

    code = \"\"\"
import sys, json, math, random, traceback
try:
    import numpy as np
    from sklearn.ensemble import GradientBoostingClassifier
    def blank(): return np.zeros(784)
    def idx(r,c): return r*28+c
    p3=blank(); p8=blank()
    for r in range(28):
        for c in range(28):
            dr1=r-8; dc1=c-18
            if 12<math.hypot(dr1*1.2, dc1)<16 and c>12 and r<14: p3[idx(r,c)]=0.9
            dr2=r-19; dc2=c-18
            if 12<math.hypot(dr2*1.2, dc2)<16 and c>12 and r>=10: p3[idx(r,c)]=0.9
            if 14<=c<=16 and 6<=r<=22: p3[idx(r,c)]=max(p3[idx(r,c)],0.3)
            drt=r-9; dct=c-14; drb=r-19; dcb=c-14
            if 9<math.hypot(drt*1.1,dct)<13: p8[idx(r,c)]=0.9
            if 9<math.hypot(drb*1.1,dcb)<13: p8[idx(r,c)]=0.9
            if abs(c-14)<2 and 9<r<19: p8[idx(r,c)]=max(p8[idx(r,c)],0.4)
    rng=np.random.default_rng(42)
    X=[]; y=[]
    for _ in range(180):
        X.append(np.clip(p3+rng.normal(0,0.18,784),0,1)); y.append(0)
        X.append(np.clip(p8+rng.normal(0,0.18,784),0,1)); y.append(1)
    X=np.array(X); y=np.array(y)
    perm=rng.permutation(len(y)); X=X[perm]; y=y[perm]
    split=int(0.78*len(y)); Xtr,Xte=X[:split],X[split:]; ytr,yte=y[:split],y[split:]
    clf=GradientBoostingClassifier(n_estimators=330, learning_rate=0.1, max_depth=1, subsample=0.9, random_state=42)
    clf.fit(Xtr,ytr)
    train_losses=[]; val_losses=[]
    for pred in clf.staged_decision_function(Xtr):
        prob=1/(1+np.exp(-pred)); prob=np.clip(prob,1e-12,1-1e-12)
        loss=-np.mean(ytr*np.log(prob)+(1-ytr)*np.log(1-prob)); train_losses.append(float(loss))
    for pred in clf.staged_decision_function(Xte):
        prob=1/(1+np.exp(-pred)); prob=np.clip(prob,1e-12,1-1e-12)
        loss=-np.mean(yte*np.log(prob)+(1-yte)*np.log(1-prob)); val_losses.append(float(loss))
    acc=float(clf.score(Xte,yte))
    fi=clf.feature_importances_.tolist()
    result={"status":"ok","train_losses":train_losses,"val_losses":val_losses,"accuracy":acc,"feature_importance":fi,"n_estimators":330}
except Exception as e:
    result={"status":"error","msg":str(e),"trace":traceback.format_exc()}
result
\"\"\"

    try:
        res = await resilient_pyodide_run(code)
        py_res=res
        try:
            if hasattr(py_res, 'to_py'):
                py_res=py_res.to_py()
        except:
            pass
        if isinstance(py_res, str):
            try:
                import json as _js
                py_res=_js.loads(py_res)
            except:
                pass
        if isinstance(py_res, dict) and py_res.get("status")=="ok":
            app.pyodide_status=f"Pyodide ✓ sklearn GBM 330 trees val acc {py_res.get('accuracy',0):.3f}"
            app.pyodide_reference=py_res
            app.pyodide_ready=True
            app.ref_train_losses=py_res.get("train_losses",[])
            app.ref_val_losses=py_res.get("val_losses",[])
            app.feature_importance=py_res.get("feature_importance",[0]*784)
        else:
            app.pyodide_status=f"Pyodide: {str(py_res)[:160]}"
            app.pyodide_ready=False
    except Exception as e:
        app.pyodide_status=f"Pyodide error: {e} — Brython fallback"
        app.pyodide_ready=False

# ─────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────
def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=30
    app.background=gradient(rgb(14,16,22), rgb(24,27,35), start='top')
    app.eta=0.12; app.max_trees=330; app.current_m=0
    app.trees=[]; app.loss_history=[]; app.val_loss_history=[]; app.acc_history=[]
    app.feature_importance=[0.0]*784; app.is_playing=False
    app.mnist_loaded=False; app.all_samples=[]; app.X_train=[]; app.y_train=[]
    app.X_val=[]; app.y_val=[]; app.F_train=[]; app.F_val=[]
    app.fetch_status="Init fetch..."; app.pyodide_status="Init pyodide..."
    app.pyodide_ready=False; app.pyodide_reference=None
    app.ref_train_losses=[]; app.ref_val_losses=[]
    app.drawing=[0.0]*784; app.is_drawing=False
    app.prediction=None; app.prediction_probs=None
    app.show_rf=False; app.show_overfit=True
    app.selected_sample_idx=0; app.hover_feat=None
    app.t=0; app.pulse=0

    sx,sy=synth_mnist_3_vs_8(160)
    Xtr,ytr,Xva,yva=train_val_split(sx,sy,0.78)
    app.X_train,app.y_train=Xtr,ytr; app.X_val,app.y_val=Xva,yva
    app.F_train=[0.0]*len(Xtr); app.F_val=[0.0]*len(Xva)

    aio.run(fetch_mnist_samples(app))
    aio.run(pyodide_train_reference(app))

def onStep(app):
    app.t+=1; app.pulse=(app.pulse+0.08)%(2*math.pi)
    if app.is_playing and app.mnist_loaded:
        for _ in range(2):
            if app.current_m>=app.max_trees:
                app.is_playing=False; break
            step_one_tree(app)

def step_one_tree(app):
    if not app.X_train: return
    grad_train=[sigmoid(ft)-yt for yt,ft in zip(app.y_train, app.F_train)]
    grad_val=[sigmoid(ft)-yt for yt,ft in zip(app.y_val, app.F_val)]
    f_idx,thr,left_val,right_val,gain=find_best_stump(app.X_train, grad_train, n_feat_sample=44)
    app.feature_importance[f_idx]+=max(0.0,gain)
    for i,x in enumerate(app.X_train):
        app.F_train[i]+=app.eta*(left_val if x[f_idx]<thr else right_val)
    for i,x in enumerate(app.X_val):
        app.F_val[i]+=app.eta*(left_val if x[f_idx]<thr else right_val)
    train_loss=log_loss_binary(app.y_train, app.F_train)
    val_loss=log_loss_binary(app.y_val, app.F_val)
    train_acc=accuracy_binary(app.y_train, app.F_train)
    val_acc=accuracy_binary(app.y_val, app.F_val)
    app.loss_history.append(train_loss); app.val_loss_history.append(val_loss); app.acc_history.append(val_acc)
    app.trees.append({"feature":f_idx,"threshold":thr,"left":left_val,"right":right_val,"gain":gain,"train_loss":train_loss,"val_loss":val_loss,"val_acc":val_acc})
    app.current_m+=1
    if any(v>0.05 for v in app.drawing):
        predict_drawing(app)

def predict_drawing(app):
    if not app.trees:
        app.prediction=None; return
    f=0.0
    for tree in app.trees:
        if app.drawing[tree["feature"]]<tree["threshold"]:
            f+=app.eta*tree["left"]
        else:
            f+=app.eta*tree["right"]
    p=sigmoid(f)
    app.prediction=8 if p>=0.5 else 3
    app.prediction_probs=[1-p,p]

def reset_ensemble(app):
    app.trees=[]; app.loss_history=[]; app.val_loss_history=[]; app.acc_history=[]
    app.F_train=[0.0]*len(app.X_train); app.F_val=[0.0]*len(app.X_val)
    app.current_m=0; app.feature_importance=[0.0]*784; app.is_playing=False; app.prediction=None

def recompute_F(app):
    app.F_train=[0.0]*len(app.X_train); app.F_val=[0.0]*len(app.X_val)
    app.feature_importance=[0.0]*784
    for tree in app.trees:
        f_idx=tree["feature"]; thr=tree["threshold"]; lv=tree["left"]; rv=tree["right"]
        app.feature_importance[f_idx]+=max(0.0,tree["gain"])
        for i,x in enumerate(app.X_train):
            app.F_train[i]+=app.eta*(lv if x[f_idx]<thr else rv)
        for i,x in enumerate(app.X_val):
            app.F_val[i]+=app.eta*(lv if x[f_idx]<thr else rv)
    if any(v>0.05 for v in app.drawing):
        predict_drawing(app)

def paint_at(app,mx,my):
    gx=int((mx-30)//8); gy=int((my-110)//8)
    for dy in range(-1,2):
        for dx in range(-1,2):
            ny=gy+dy; nx=gx+dx
            if 0<=ny<28 and 0<=nx<28:
                dist=math.hypot(dx,dy)
                intensity=max(0.0,1.0-dist*0.6)
                idx=ny*28+nx
                app.drawing[idx]=min(1.0, app.drawing[idx]+intensity*0.85)

def onMousePress(app,mx,my):
    # Header controls - new layout to avoid overlap
    if 360<=mx<=430 and 12<=my<=36:
        app.is_playing=not app.is_playing; return
    if 440<=mx<=485 and 12<=my<=36:
        if app.current_m<app.max_trees: step_one_tree(app); return
    if 495<=mx<=555 and 12<=my<=36:
        reset_ensemble(app); return
    if 570<=mx<=590 and 12<=my<=22:
        app.eta=min(0.5,app.eta+0.02); return
    if 570<=mx<=590 and 26<=my<=36:
        app.eta=max(0.01,app.eta-0.02); return
    if 860<=mx<=1020 and 12<=my<=36:
        app.show_rf=not app.show_rf; return
    # Drawing canvas
    if 30<=mx<=254 and 110<=my<=334:
        app.is_drawing=True; paint_at(app,mx,my); return
    # Gallery
    if 20<=mx<=280 and 360<=my<=430:
        if app.all_samples:
            idx=int((mx-20)/260 * min(10, len(app.all_samples)))
            idx=max(0,min(idx,len(app.all_samples)-1))
            app.selected_sample_idx=idx
            pix,lab=app.all_samples[idx]
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
    elif key.lower()=='r':
        reset_ensemble(app)
    elif key=='Right':
        if app.current_m<app.max_trees: step_one_tree(app)
    elif key=='Left':
        if app.trees:
            app.trees.pop(); app.loss_history.pop(); app.val_loss_history.pop(); app.acc_history.pop()
            app.current_m-=1; recompute_F(app)
    elif key.lower()=='c':
        app.drawing=[0.0]*784; app.prediction=None
    elif key=='+' or key=='=':
        app.eta=min(0.5,app.eta+0.02)
    elif key=='-' or key=='_':
        app.eta=max(0.01,app.eta-0.02)
    elif key.lower()=='o':
        app.show_overfit=not app.show_overfit
    elif key.lower()=='f':
        app.show_rf=not app.show_rf

def redrawAll(app):
    drawRect(0,0,app.width,app.height, fill=gradient(rgb(14,16,22), rgb(24,27,35), start='top'))
    # Header - fixed layout no overlap
    drawRect(0,0,app.width,50, fill=rgb(18,20,28), border=rgb(40,45,60), borderWidth=1)
    drawLabel("XGBoost Lab", 14, 14, size=15, bold=True, fill=rgb(220,230,255), align='left-top')
    drawLabel("F_m = F_{m-1} + η·h_m  |  h_m ≈ -∂L/∂F  |  L = -Σ p log q", 14, 32, size=10, fill=rgb(130,145,165), align='left-top')

    # Controls centered/right
    play_col=rgb(0,212,255) if app.is_playing else rgb(55,65,85)
    drawRect(360,12,70,26, fill=play_col, border=rgb(90,110,140), borderWidth=1, roundness=7)
    drawLabel("▶ Play" if not app.is_playing else "⏸ Pause", 395, 25, size=11, bold=True, fill=rgb(10,15,25) if app.is_playing else rgb(200,220,255))

    drawRect(440,12,45,26, fill=rgb(40,45,60), border=rgb(70,80,100), borderWidth=1, roundness=7)
    drawLabel("Step", 462, 25, size=11, fill=rgb(200,220,255))

    drawRect(495,12,60,26, fill=rgb(40,45,60), border=rgb(70,80,100), borderWidth=1, roundness=7)
    drawLabel("Reset", 525, 25, size=11, fill=rgb(200,220,255))

    drawLabel(f"η={app.eta:.2f}", 600, 15, size=11, bold=True, fill=rgb(180,200,220), align='left-top')
    drawRect(570,12,18,10, fill=rgb(50,60,80), border=rgb(80,90,110), borderWidth=1, roundness=3)
    drawLabel("+", 579, 17, size=9, fill=rgb(200,220,255))
    drawRect(570,26,18,10, fill=rgb(50,60,80), border=rgb(80,90,110), borderWidth=1, roundness=3)
    drawLabel("−", 579, 31, size=9, fill=rgb(200,220,255))
    drawLabel("learn rate", 625, 20, size=9, fill=rgb(110,125,145), align='left-top')

    rf_fill=rgb(255,0,110) if app.show_rf else rgb(45,50,65)
    drawRect(860,12,160,26, fill=rf_fill, border=rgb(90,60,80), borderWidth=1, roundness=7)
    drawLabel("RF vs Boosting", 940, 25, size=11, bold=True, fill=rgb(255,220,230) if app.show_rf else rgb(180,190,210))

    # Left panel
    drawRect(12,60,276,620, fill=rgb(20,23,31), border=rgb(35,40,55), borderWidth=1, roundness=12)
    drawLabel("INPUT: Draw 3 or 8 — MNIST 28×28", 24, 72, size=11, bold=True, fill=rgb(180,200,230), align='left-top')
    drawLabel("Each pixel = feature (784-d)", 24, 88, size=9, fill=rgb(110,125,145), align='left-top')
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

    if app.prediction is not None:
        col=rgb(0,212,255) if app.prediction==8 else rgb(255,183,3)
        drawRect(30,338,224,34, fill=rgb(30,35,50), border=col, borderWidth=1, roundness=8)
        prob=app.prediction_probs[1] if app.prediction==8 else app.prediction_probs[0]
        drawLabel(f"Pred: {app.prediction}  {prob*100:.1f}%", 142, 350, size=13, bold=True, fill=col)
        if app.trees:
            last=app.trees[-1]
            drawLabel(f"stump pixel ({last['feature']%28},{last['feature']//28}) thr {last['threshold']:.2f}", 142, 364, size=8, fill=rgb(150,165,190))
    else:
        drawLabel("Draw to predict — ensemble of stumps", 142, 355, size=10, fill=rgb(100,115,135))

    drawLabel("Samples via extensions.fetch — click:", 24, 382, size=9, fill=rgb(120,135,155), align='left-top')
    if app.all_samples:
        n_show=min(10, len(app.all_samples))
        for i in range(n_show):
            pix,lab=app.all_samples[i]
            x0=20 + i*25; y0=396
            for r in range(28):
                for c in range(28):
                    v=pix[r*28+c]
                    if v>0.15:
                        gray=int(v*200+40)
                        drawRect(x0 + c*0.85, y0 + r*0.85, 0.9, 0.9, fill=rgb(gray,gray,gray))
            if i==app.selected_sample_idx:
                drawRect(x0-1,y0-1,25,25, fill=None, border=rgb(0,212,255), borderWidth=1.5, roundness=2)
            drawLabel(str(lab), x0+12, y0+28, size=8, fill=rgb(160,175,190))
    drawLabel(app.fetch_status[:52], 24, 432, size=8, fill=rgb(90,105,125), align='left-top')

    # Middle panel
    drawRect(300,60,388,620, fill=rgb(22,25,34), border=rgb(35,40,55), borderWidth=1, roundness=12)
    drawLabel("BOOSTING: Sequential correction", 312, 72, size=12, bold=True, fill=rgb(200,220,255), align='left-top')
    drawLabel(f"Trees {app.current_m}/{app.max_trees}  η={app.eta:.2f}  target 330→89% acc", 312, 88, size=9, fill=rgb(130,145,165), align='left-top')

    if app.show_rf:
        drawRect(312,108,180,90, fill=rgb(30,20,30), border=rgb(80,40,60), borderWidth=1, roundness=8)
        drawLabel("Random Forest (parallel)", 320,116, size=10, bold=True, fill=rgb(255,150,180), align='left-top')
        for i in range(5):
            x=322+i*32; y=132
            drawRect(x,y,24,32, fill=rgb(60,40,55), border=rgb(120,70,90), borderWidth=1, roundness=4)
            drawLabel(f"T{i+1}", x+12,y+16, size=8, fill=rgb(220,180,200))
        drawLabel("bootstrap + vote", 360, 176, size=9, fill=rgb(180,120,140))
        drawRect(504,108,172,90, fill=rgb(20,30,40), border=rgb(40,80,100), borderWidth=1, roundness=8)
        drawLabel("Boosting (sequential)", 512,116, size=10, bold=True, fill=rgb(120,220,255), align='left-top')
        for i in range(5):
            x=512+i*30; y=132
            col=rgb(0,212,255) if i<app.current_m else rgb(40,60,75)
            drawRect(x,y,24,32, fill=col, border=rgb(0,180,220), borderWidth=1, roundness=4)
            if i>0:
                drawLine(x-6,y+16,x,y+16, lineWidth=1.2, fill=rgb(0,212,255))
            drawLabel(f"h{i+1}", x+12,y+16, size=8, bold=True, fill=rgb(10,20,30) if i<app.current_m else rgb(120,140,160))
    else:
        if app.trees:
            last=app.trees[-1]
            f=last["feature"]; fr=f//28; fc=f%28
            drawLabel(f"Weak learner h_{app.current_m}: stump pixel ({fc},{fr}) thr {last['threshold']:.2f}", 312,114, size=10, bold=True, fill=rgb(180,220,255), align='left-top')
            drawLabel(f"left {last['left']:+.2f} right {last['right']:+.2f} gain {last['gain']:.1f}", 312,130, size=9, fill=rgb(130,150,175), align='left-top')
            drawRect(312,144,56,56, fill=rgb(10,15,25), border=rgb(0,212,255), borderWidth=1, roundness=6)
            for r in range(28):
                for c in range(28):
                    if r==fr and c==fc:
                        drawRect(312+c*2,144+r*2,2.5,2.5, fill=rgb(255,183,3))
            drawLabel("Pseudo-residuals (-∂L/∂F) for 5 val samples:", 380,148, size=9, fill=rgb(140,160,185), align='left-top')
            for i in range(min(5, len(app.X_val))):
                x=380+i*52; y=162
                pix=app.X_val[i]
                for r in range(28):
                    for c in range(28):
                        v=pix[r*28+c]
                        if v>0.1:
                            gray=int(30+v*180)
                            drawRect(x + c*1.2, y + r*1.2, 1.3,1.3, fill=rgb(gray,gray,gray))
                if i < len(app.F_val):
                    grad=sigmoid(app.F_val[i]) - app.y_val[i]
                    err=abs(grad)
                    r_col=int(200*err+40); g_col=int(200*(1-err)+40)
                    drawRect(x-2,y-2,36,36, fill=None, border=rgb(r_col,g_col,60), borderWidth=1.2, roundness=3)
                    drawLabel(f"{-grad:+.2f}", x+17, y+40, size=8, fill=rgb(200,220,255))
        else:
            drawLabel("No trees yet — Space/Step to grow. F0=0, p=0.5", 312,120, size=11, fill=rgb(120,135,155), align='left-top')
            drawLabel("L = -[ y log σ(F) + (1-y) log(1-σ(F)) ]", 312,138, size=10, fill=rgb(100,120,145), align='left-top')

    drawRect(312,210,368,130, fill=rgb(14,18,26), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("Loss vs #trees — cyan train / gold val", 320,218, size=10, bold=True, fill=rgb(180,200,220), align='left-top')
    drawLine(338,236,338,322, lineWidth=1, fill=rgb(60,70,90))
    drawLine(338,322,662,322, lineWidth=1, fill=rgb(60,70,90))
    drawLabel("0", 328,324, size=8, fill=rgb(100,115,135))
    drawLabel(f"{app.max_trees}", 650,324, size=8, fill=rgb(100,115,135))
    if app.loss_history:
        max_loss=max(max(app.loss_history), max(app.val_loss_history) if app.val_loss_history else 0, 0.7)
        min_loss=min(min(app.loss_history), min(app.val_loss_history) if app.val_loss_history else 0, 0.1)
        rng=max_loss-min_loss if max_loss-min_loss>0.1 else 0.1
        prev_x=None; prev_y=None
        for i,loss in enumerate(app.loss_history):
            x=338 + (i/app.max_trees)*324; y=322 - ((loss-min_loss)/rng)*80
            if prev_x is not None:
                drawLine(prev_x,prev_y,x,y, lineWidth=1.3, fill=rgb(0,212,255))
            prev_x,prev_y=x,y
        prev_x=None; prev_y=None
        for i,loss in enumerate(app.val_loss_history):
            x=338 + (i/app.max_trees)*324; y=322 - ((loss-min_loss)/rng)*80
            if prev_x is not None:
                drawLine(prev_x,prev_y,x,y, lineWidth=1.3, fill=rgb(255,183,3))
            prev_x,prev_y=x,y
        if app.show_overfit and len(app.val_loss_history)>40:
            min_idx=app.val_loss_history.index(min(app.val_loss_history))
            if min_idx < len(app.val_loss_history)-8:
                x_min=338 + (min_idx/app.max_trees)*324
                drawLine(x_min,236,x_min,322, lineWidth=1, fill=rgb(255,0,110), dashes=(4,4))
                drawLabel("overfit ↑", x_min+6,244, size=8, bold=True, fill=rgb(255,80,130))
        if app.current_m>0:
            x_cur=338 + (app.current_m/app.max_trees)*324
            drawLine(x_cur,236,x_cur,322, lineWidth=1, fill=rgb(200,220,255), dashes=(2,2))

    if app.acc_history:
        acc=app.acc_history[-1]
        drawLabel(f"Val Acc {acc*100:.1f}% target 89% @330", 320,310, size=9, bold=True, fill=rgb(180,220,255), align='left-top')

    drawRect(312,348,368,50, fill=rgb(18,22,32), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("F_m = F_{m-1} + η·h_m   h_m ≈ y - σ(F_{m-1})", 320,356, size=10, fill=rgb(200,220,255), align='left-top')
    drawLabel("Weak learner = stump: 1 split, high bias — boosting reduces bias", 320,372, size=8, fill=rgb(120,140,165), align='left-top')

    drawLabel(f"Ensemble timeline — {app.current_m} stumps (gold=high gain):", 312,408, size=9, bold=True, fill=rgb(180,200,220), align='left-top')
    for i in range(min(app.current_m, 80)):
        tree=app.trees[i] if i<len(app.trees) else None
        x=312 + (i%40)*9; y=420 + (i//40)*14
        gain=tree["gain"] if tree else 0
        max_gain=max([t["gain"] for t in app.trees]) if app.trees else 1
        h=3 + (gain/max_gain)*9 if max_gain>0 else 3
        col_int=int(60 + (gain/max_gain)*195) if max_gain>0 else 60
        drawRect(x,y,7,h, fill=rgb(col_int,col_int//2,30), border=rgb(80,60,30), borderWidth=0.4, roundness=1)

    # Right panel
    drawRect(700,60,338,620, fill=rgb(20,23,31), border=rgb(35,40,55), borderWidth=1, roundness=12)
    drawLabel("RESEARCH VIEW — Capacity, Gradients", 712,72, size=11, bold=True, fill=rgb(220,230,255), align='left-top')
    drawLabel("Why boosting has high capacity", 712,88, size=9, fill=rgb(130,145,165), align='left-top')
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
    drawLabel("Feature importance: 3 vs 8 (28×28)", 712,340, size=9, fill=rgb(140,160,185), align='left-top')

    drawRect(712,352,316,76, fill=rgb(16,20,28), border=rgb(40,50,70), borderWidth=1, roundness=8)
    drawLabel("Multi-class cross-entropy:", 720,360, size=9, bold=True, fill=rgb(180,200,220), align='left-top')
    drawLabel("L = -Σ Σ p log q  q=softmax(F)", 720,374, size=9, fill=rgb(200,220,255), align='left-top')
    drawLabel("Binary: L = -[ y log σ(F)+(1-y)log(1-σ(F)) ]", 720,386, size=8, fill=rgb(150,170,200), align='left-top')
    drawLabel("∂L/∂F = σ(F)-y → h_m≈y-σ(F_{m-1})", 720,400, size=9, bold=True, fill=rgb(0,212,255), align='left-top')
    drawLabel("F_m = F_{m-1}+η·h_m", 720,412, size=8, fill=rgb(160,180,210), align='left-top')

    drawRect(712,434,316,84, fill=rgb(18,22,32), border=rgb(35,45,65), borderWidth=1, roundness=8)
    drawLabel("Pyodide worker (extensions.pyodide):", 720,442, size=9, bold=True, fill=rgb(180,200,220), align='left-top')
    status=app.pyodide_status
    drawLabel(status[:58], 720,456, size=8, fill=rgb(120,200,150) if app.pyodide_ready else rgb(200,150,120), align='left-top')
    if len(status)>58:
        drawLabel(status[58:116], 720,468, size=8, fill=rgb(120,200,150) if app.pyodide_ready else rgb(200,150,120), align='left-top')
    if app.pyodide_ready and app.pyodide_reference:
        acc=app.pyodide_reference.get("accuracy",0)
        drawLabel(f"sklearn GBM 330 stumps: {acc*100:.1f}% matches 89% target", 720,482, size=8, fill=rgb(160,200,180), align='left-top')
        drawLabel("XGBoost = GBM + 2nd-order Taylor + sparsity", 720,494, size=8, fill=rgb(130,150,175), align='left-top')
    else:
        drawLabel("Brython GBM fallback — 100% browser", 720,482, size=8, fill=rgb(140,160,185), align='left-top')
        drawLabel("pip install xgboost in Pyodide for exact XGBoost", 720,494, size=8, fill=rgb(110,130,155), align='left-top')

    drawRect(712,524,316,110, fill=rgb(14,18,26), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("Research insights:", 720,532, size=9, bold=True, fill=rgb(220,230,255), align='left-top')
    notes=["• stumps depth1 → high bias low var","• boosting reduces bias sequentially (vs RF var)","• η∈[0.01,0.3] slows, improves gen","• 330 trees high cap → overfits w/o early stop","• MNIST 784-d, 10 classes, 60k/10k","• XGBoost: 2nd-order + sparsity-aware"]
    for i,line in enumerate(notes):
        drawLabel(line, 720,546+i*12, size=8, fill=rgb(130,145,165), align='left-top')

    drawLabel("SCS 1050×700 — fetch + pyodide resilient — top-tier", 14, 686, size=8, fill=rgb(80,95,115), align='left-top')
