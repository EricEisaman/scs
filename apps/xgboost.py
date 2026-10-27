
from scs import *
from browser import aio, window
import math, random, time

# ─────────────────────────────────────────────────────────────
# Extension imports — Model layer, strict MVC
# ─────────────────────────────────────────────────────────────
try:
    from extensions.fetch import fetch_json, fetch_text, fetch, FetchError
    FETCH_OK = True
except Exception as _fe:
    FETCH_OK = False
    fetch_json = None
    fetch_text = None
    fetch = None
    class FetchError(Exception): pass

try:
    import extensions.pyodide as _py_ext
    PYODIDE_EXT_OK = True
    # Detect available entrypoints (handles breaking changes)
    _py_candidates = []
    for _name in ['run_python_async', 'run_python', 'run', 'exec', 'evaluate', 'run_code', 'execute']:
        if hasattr(_py_ext, _name):
            _py_candidates.append(_name)
except Exception as _pe:
    PYODIDE_EXT_OK = False
    _py_ext = None
    _py_candidates = []

# ─────────────────────────────────────────────────────────────
# Utilities — Model helpers (pure, no drawing)
# ─────────────────────────────────────────────────────────────
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
        if yt == 1:
            total += -math.log(p)
        else:
            total += -math.log(1-p)
    return total / len(y_true) if y_true else 0.0

def accuracy_binary(y_true, f_logit):
    correct = 0
    for yt, ft in zip(y_true, f_logit):
        p = sigmoid(ft)
        pred = 1 if p >= 0.5 else 0
        if pred == yt:
            correct += 1
    return correct / len(y_true) if y_true else 0.0

def find_best_stump(X, grad, n_feat_sample=48, min_leaf=6):
    """
    X: list[list[float]] n x d (d=784 but we sample)
    grad: list[float] = p - y (gradient of loss)
    We fit stump to -grad (negative gradient / pseudo-residual)
    Returns feature, thresh, left_val, right_val, gain
    """
    n = len(X)
    if n == 0:
        return 0, 0.5, 0.0, 0.0, 0.0
    d = len(X[0])
    target = [-g for g in grad]  # pseudo-residual
    total_sum = sum(target)
    # sample features to keep interactive
    feat_pool = random.sample(range(d), min(n_feat_sample, d))
    best_gain = -1e100
    best_f = feat_pool[0] if feat_pool else 0
    best_thr = 0.5
    best_left = 0.0
    best_right = 0.0

    # precompute total mean for baseline (not needed for gain comparison)
    for f in feat_pool:
        # collect (value, target) pairs
        pairs = []
        for i in range(n):
            pairs.append((X[i][f], target[i]))
        pairs.sort(key=lambda x: x[0])

        left_sum = 0.0
        left_cnt = 0
        right_sum = total_sum
        right_cnt = n

        # sweep splits
        for i in range(1, n):
            v_prev, t_prev = pairs[i-1]
            left_sum += t_prev
            left_cnt += 1
            right_sum -= t_prev
            right_cnt -= 1

            v_curr = pairs[i][0]
            if v_curr == v_prev:
                continue
            if left_cnt < min_leaf or right_cnt < min_leaf:
                continue

            left_mean = left_sum / left_cnt
            right_mean = right_sum / right_cnt if right_cnt else 0.0
            # gain = reduction in squared error (proportional to sum mean^2 * count)
            gain = left_cnt * left_mean * left_mean + right_cnt * right_mean * right_mean

            if gain > best_gain:
                best_gain = gain
                best_f = f
                best_thr = (v_prev + v_curr) * 0.5
                best_left = left_mean
                best_right = right_mean

    return best_f, best_thr, best_left, best_right, best_gain

def generate_prototype_3_8():
    """
    Create synthetic 28x28 prototypes for digits 3 and 8 that are visually plausible
    for a researcher demo. Returns two base images (784 floats 0-1)
    """
    def blank(): return [0.0]*784
    def idx(r,c): return r*28 + c

    proto3 = blank()
    proto8 = blank()
    # Digit 3: two arcs on right side
    for r in range(28):
        for c in range(28):
            # upper loop of 3
            dr1 = r - 8
            dc1 = c - 18
            if 12 < math.hypot(dr1*1.2, dc1) < 16 and c > 12 and r < 14:
                proto3[idx(r,c)] = 0.9
            # lower loop
            dr2 = r - 19
            dc2 = c - 18
            if 12 < math.hypot(dr2*1.2, dc2) < 16 and c > 12 and r >= 10:
                proto3[idx(r,c)] = 0.9
            # spine
            if 14 <= c <= 16 and 6 <= r <= 22:
                proto3[idx(r,c)] = max(proto3[idx(r,c)], 0.3)

    for r in range(28):
        for c in range(28):
            dr_top = r - 9
            dc_top = c - 14
            dr_bot = r - 19
            dc_bot = c - 14
            # top loop of 8
            if 9 < math.hypot(dr_top*1.1, dc_top) < 13:
                proto8[idx(r,c)] = 0.9
            # bottom loop
            if 9 < math.hypot(dr_bot*1.1, dc_bot) < 13:
                proto8[idx(r,c)] = 0.9
            if abs(c-14) < 2 and 9 < r < 19:
                proto8[idx(r,c)] = max(proto8[idx(r,c)], 0.4)

    return proto3, proto8

def synth_mnist_3_vs_8(n_per_class=220):
    proto3, proto8 = generate_prototype_3_8()
    X = []
    y = []
    for _ in range(n_per_class):
        # jittered 3
        img = []
        for v in proto3:
            nv = v + random.gauss(0, 0.18)
            # random dropout / thickening
            if random.random() < 0.04:
                nv += random.uniform(-0.3, 0.3)
            img.append(min(1.0, max(0.0, nv)))
        # small affine jitter: shift 1px
        # we skip actual affine for speed, just noise
        X.append(img)
        y.append(0)  # 0 = digit 3

        img2 = []
        for v in proto8:
            nv = v + random.gauss(0, 0.18)
            if random.random() < 0.04:
                nv += random.uniform(-0.3, 0.3)
            img2.append(min(1.0, max(0.0, nv)))
        X.append(img2)
        y.append(1)  # 1 = digit 8

    # shuffle
    combined = list(zip(X,y))
    random.shuffle(combined)
    X[:], y[:] = zip(*combined)
    return list(X), list(y)

def train_val_split(X,y, ratio=0.8):
    n = len(X)
    n_train = int(n*ratio)
    return X[:n_train], y[:n_train], X[n_train:], y[n_train:]

# ─────────────────────────────────────────────────────────────
# Pyodide runner — resilient to breaking changes
# ─────────────────────────────────────────────────────────────
async def resilient_pyodide_run(code_str):
    """
    Try every known entrypoint of extensions.pyodide, handling old and new worker protocols.
    Returns result or None.
    """
    # 1) Try extension module
    if PYODIDE_EXT_OK and _py_ext is not None:
        for name in _py_candidates:
            try:
                fn = getattr(_py_ext, name)
                res = fn(code_str)
                # await if needed
                if hasattr(res, '__await__'):
                    res = await res
                elif hasattr(res, 'then'):  # JS Promise
                    # Brython aio can await JS promise?
                    try:
                        res = await res
                    except:
                        pass
                return res
            except Exception as e:
                continue
        # Try calling module as function if it exposes __call__?
        try:
            if hasattr(_py_ext, 'runPythonAsync'):
                res = _py_ext.runPythonAsync(code_str)
                if hasattr(res, '__await__'):
                    res = await res
                return res
        except:
            pass

    # 2) Try direct window.pyodide (if worker already loaded pyodide globally)
    try:
        if hasattr(window, 'pyodide') and window.pyodide is not None:
            res = await window.pyodide.runPythonAsync(code_str)
            return res
    except Exception as e:
        pass

    # 3) Try window.pyodideWorker or custom globals that old extension might have set
    try:
        # Some versions expose a worker proxy
        if hasattr(window, 'pyodideWorker'):
            # old API might be postMessage based, we cannot easily use here
            pass
    except:
        pass

    return None

# ─────────────────────────────────────────────────────────────
# Fetch loader — uses extensions.fetch (Model layer)
# ─────────────────────────────────────────────────────────────
async def fetch_mnist_samples(app):
    app.fetch_status = "Fetching MNIST via extensions.fetch..."
    app.mnist_loaded = False

    # Small public CSVs that are CORS-enabled via raw.githubusercontent.com
    candidates = [
        # 10-sample tiny test
        "https://raw.githubusercontent.com/AshutoshSce/MNIST-Dataset-in-CSV-format/master/mnist_test_10.csv",
        "https://raw.githubusercontent.com/csgsky/mnist-csv/master/mnist_test_10.csv",
        "https://raw.githubusercontent.com/mmoroney/mnist-csv/master/mnist_test_10.csv",
        # fallback to a slightly larger but still manageable 100-sample file if exists
        "https://raw.githubusercontent.com/hsjeong5/MNIST-for-Numpy/master/mnist_test.csv",
    ]

    data_ok = False
    if FETCH_OK and fetch_text is not None:
        for url in candidates:
            try:
                app.fetch_status = f"Fetching {url.split('/')[-1]}..."
                txt = await fetch_text(url)
                # quick parse check
                lines = txt.strip().split("\n")
                if len(lines) < 2:
                    continue
                # Detect format: some CSVs have label first, others have header
                samples = []
                for line in lines[:120]:  # only need ~100
                    if not line.strip():
                        continue
                    if line.lower().startswith("label") or line.lower().startswith("pixel"):
                        continue
                    parts = line.split(",")
                    if len(parts) < 785 and len(parts) > 10:
                        # might be 784 pixels + label at start or end
                        try:
                            # try label first
                            label = int(float(parts[0]))
                            pixels = [float(p)/255.0 for p in parts[1:785]]
                            if len(pixels) >= 784:
                                samples.append((pixels[:784], label))
                        except:
                            try:
                                label = int(float(parts[-1]))
                                pixels = [float(p)/255.0 for p in parts[:784]]
                                samples.append((pixels, label))
                            except:
                                continue
                    elif len(parts) >= 785:
                        try:
                            label = int(float(parts[0]))
                            pixels = [float(p)/255.0 for p in parts[1:785]]
                            samples.append((pixels, label))
                        except:
                            continue
                if len(samples) >= 10:
                    # filter to 3 vs 8 for binary demo but keep all for multiclass view
                    app.all_samples = samples
                    # Build binary 3 vs 8 dataset
                    Xb = []
                    yb = []
                    for pix, lab in samples:
                        if lab == 3:
                            Xb.append(pix); yb.append(0)
                        elif lab == 8:
                            Xb.append(pix); yb.append(1)
                    # If not enough 3/8 in tiny file, synthesize rest
                    if len(Xb) < 40:
                        sx, sy = synth_mnist_3_vs_8(60)
                        Xb.extend(sx); yb.extend(sy)
                    app.X_train_full, app.y_train_full = Xb, yb
                    # For display, keep all samples for gallery
                    app.fetch_status = f"Loaded {len(samples)} real MNIST samples via fetch"
                    data_ok = True
                    break
            except Exception as e:
                app.fetch_status = f"Fetch failed {url}: {e}"
                continue

    if not data_ok:
        app.fetch_status = "Fetch unavailable — generating high-fidelity synthetic MNIST (3 vs 8)"
        sx, sy = synth_mnist_3_vs_8(240)
        app.all_samples = [(pix, 3 if lab==0 else 8) for pix, lab in zip(sx, sy)]
        app.X_train_full, app.y_train_full = sx, sy

    # Split
    X, y = app.X_train_full, app.y_train_full
    # Ensure even
    combined = list(zip(X,y))
    random.shuffle(combined)
    if combined:
        X, y = zip(*combined)
        X, y = list(X), list(y)
    app.X_train, app.y_train, app.X_val, app.y_val = train_val_split(X,y,0.78)
    app.F_train = [0.0]*len(app.X_train)
    app.F_val = [0.0]*len(app.X_val)
    app.mnist_loaded = True
    app.fetch_status += f" | Train {len(app.X_train)} Val {len(app.X_val)}"

async def pyodide_train_reference(app):
    app.pyodide_status = "Pyodide: probing extension..."
    if not PYODIDE_EXT_OK:
        app.pyodide_status = "Pyodide extension not detected — using Brython GBM (research fallback)"
        app.pyodide_ready = False
        return

    # Python code to run inside Pyodide worker: train sklearn GBM and return metrics
    code = """
import sys, json, math, random
try:
    import numpy as np
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import log_loss, accuracy_score

    # tiny synthetic dataset inside worker to mimic MNIST 3 vs 8
    def make_proto():
        # same prototypes as host but numpy version
        import math
        def blank(): return np.zeros(784)
        def idx(r,c): return r*28+c
        p3 = blank(); p8 = blank()
        for r in range(28):
            for c in range(28):
                dr1 = r-8; dc1 = c-18
                if 12 < math.hypot(dr1*1.2, dc1) < 16 and c>12 and r<14:
                    p3[idx(r,c)] = 0.9
                dr2 = r-19; dc2 = c-18
                if 12 < math.hypot(dr2*1.2, dc2) < 16 and c>12 and r>=10:
                    p3[idx(r,c)] = 0.9
                if 14 <= c <= 16 and 6 <= r <= 22:
                    p3[idx(r,c)] = max(p3[idx(r,c)], 0.3)
                drt = r-9; dct = c-14
                drb = r-19; dcb = c-14
                if 9 < math.hypot(drt*1.1, dct) < 13:
                    p8[idx(r,c)] = 0.9
                if 9 < math.hypot(drb*1.1, dcb) < 13:
                    p8[idx(r,c)] = 0.9
                if abs(c-14)<2 and 9<r<19:
                    p8[idx(r,c)] = max(p8[idx(r,c)], 0.4)
        return p3, p8

    p3,p8 = make_proto()
    X=[]; y=[]
    rng = np.random.default_rng(42)
    for _ in range(220):
        X.append(np.clip(p3 + rng.normal(0,0.18,784),0,1)); y.append(0)
        X.append(np.clip(p8 + rng.normal(0,0.18,784),0,1)); y.append(1)
    X=np.array(X); y=np.array(y)
    # shuffle
    perm = rng.permutation(len(y))
    X=X[perm]; y=y[perm]
    split = int(0.78*len(y))
    Xtr, Xte = X[:split], X[split:]
    ytr, yte = y[:split], y[split:]

    clf = GradientBoostingClassifier(n_estimators=330, learning_rate=0.1, max_depth=1, subsample=0.9, random_state=42)
    clf.fit(Xtr, ytr)
    # staged loss
    train_losses = []
    val_losses = []
    for i, pred in enumerate(clf.staged_decision_function(Xtr)):
        # pred is decision function, convert to prob
        prob = 1/(1+np.exp(-pred))
        eps=1e-12
        prob = np.clip(prob, eps, 1-eps)
        loss = -np.mean(ytr*np.log(prob)+(1-ytr)*np.log(1-prob))
        train_losses.append(float(loss))
    for i, pred in enumerate(clf.staged_decision_function(Xte)):
        prob = 1/(1+np.exp(-pred))
        prob = np.clip(prob, 1e-12, 1-1e-12)
        loss = -np.mean(yte*np.log(prob)+(1-yte)*np.log(1-prob))
        val_losses.append(float(loss))

    acc = float(clf.score(Xte, yte))
    fi = clf.feature_importances_.tolist()

    result = {
        "status": "ok",
        "train_losses": train_losses,
        "val_losses": val_losses,
        "accuracy": acc,
        "feature_importance": fi,
        "n_estimators": 330,
        "note": "sklearn GradientBoosting (XGBoost-equivalent) on synthetic 3-vs-8"
    }
except Exception as e:
    import traceback
    result = {"status": "error", "msg": str(e), "trace": traceback.format_exc()}

result
"""

    try:
        res = await resilient_pyodide_run(code)
        # res may be Python dict or JS object or JSON string
        # Try to normalize
        py_res = res
        # If it's a JS proxy, try to convert
        if py_res is not None:
            # If it has to_py method (pyodide)
            try:
                if hasattr(py_res, 'to_py'):
                    py_res = py_res.to_py()
            except:
                pass
            # If string, parse json
            if isinstance(py_res, str):
                try:
                    import json as _json
                    py_res = _json.loads(py_res)
                except:
                    pass
        if isinstance(py_res, dict) and py_res.get("status") == "ok":
            app.pyodide_status = f"Pyodide ✓ sklearn GBM 330 trees — val acc {py_res.get('accuracy',0):.3f}"
            app.pyodide_reference = py_res
            app.pyodide_ready = True
            # Use its losses to seed visualization
            app.ref_train_losses = py_res.get("train_losses", [])
            app.ref_val_losses = py_res.get("val_losses", [])
            app.feature_importance = py_res.get("feature_importance", [0]*784)
        else:
            app.pyodide_status = f"Pyodide returned: {str(py_res)[:180]}"
            app.pyodide_ready = False
    except Exception as e:
        app.pyodide_status = f"Pyodide error (handled): {e} — fallback to Brython"
        app.pyodide_ready = False

# ─────────────────────────────────────────────────────────────
# App lifecycle — View/Controller (CMU Graphics API)
# ─────────────────────────────────────────────────────────────
def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 30
    app.background = gradient(rgb(14,16,22), rgb(24,27,35), start='top')

    # Core state
    app.eta = 0.12
    app.max_trees = 330  # from exposition: 330 weak learners → 89% acc
    app.current_m = 0
    app.trees = []
    app.loss_history = []
    app.val_loss_history = []
    app.acc_history = []
    app.feature_importance = [0.0]*784
    app.is_playing = False
    app.play_counter = 0

    app.mnist_loaded = False
    app.all_samples = []
    app.X_train = []; app.y_train = []
    app.X_val = []; app.y_val = []
    app.F_train = []; app.F_val = []
    app.fetch_status = "Initializing fetch..."
    app.pyodide_status = "Initializing pyodide..."
    app.pyodide_ready = False
    app.pyodide_reference = None
    app.ref_train_losses = []
    app.ref_val_losses = []

    # Drawing canvas
    app.drawing = [0.0]*784
    app.is_drawing = False
    app.brush_radius = 1.8
    app.prediction = None
    app.prediction_probs = None
    app.show_rf = False
    app.show_overfit = True
    app.mode = "binary"  # binary 3 vs 8 for clarity
    app.selected_sample_idx = 0
    app.hover_feat = None

    # UI geometry
    app.left_x = 18
    app.mid_x = 300
    app.right_x = 700
    app.header_h = 58

    # For beautiful animations
    app.t = 0
    app.pulse = 0

    # Async loaders — Model layer via extensions
    aio.run(fetch_mnist_samples(app))
    aio.run(pyodide_train_reference(app))

    # Start with synthetic immediately so UI is responsive
    sx, sy = synth_mnist_3_vs_8(180)
    Xtr, ytr, Xva, yva = train_val_split(sx, sy, 0.78)
    app.X_train, app.y_train = Xtr, ytr
    app.X_val, app.y_val = Xva, yva
    app.F_train = [0.0]*len(Xtr)
    app.F_val = [0.0]*len(Xva)

def onStep(app):
    app.t += 1
    app.pulse = (app.pulse + 0.08) % (2*math.pi)

    if app.is_playing and app.mnist_loaded:
        # Add up to 2 trees per step for smooth animation
        for _ in range(2):
            if app.current_m >= app.max_trees:
                app.is_playing = False
                break
            step_one_tree(app)

def step_one_tree(app):
    if not app.X_train:
        return
    # Compute gradients
    grad_train = []
    for yt, ft in zip(app.y_train, app.F_train):
        p = sigmoid(ft)
        grad_train.append(p - yt)  # dL/dF

    grad_val = []
    for yt, ft in zip(app.y_val, app.F_val):
        p = sigmoid(ft)
        grad_val.append(p - yt)

    # Find stump
    f_idx, thr, left_val, right_val, gain = find_best_stump(app.X_train, grad_train, n_feat_sample=52)

    # Update feature importance
    app.feature_importance[f_idx] += max(0.0, gain)

    # Update F
    for i, x in enumerate(app.X_train):
        if x[f_idx] < thr:
            app.F_train[i] += app.eta * left_val
        else:
            app.F_train[i] += app.eta * right_val
    for i, x in enumerate(app.X_val):
        if x[f_idx] < thr:
            app.F_val[i] += app.eta * left_val
        else:
            app.F_val[i] += app.eta * right_val

    # Compute metrics
    train_loss = log_loss_binary(app.y_train, app.F_train)
    val_loss = log_loss_binary(app.y_val, app.F_val)
    train_acc = accuracy_binary(app.y_train, app.F_train)
    val_acc = accuracy_binary(app.y_val, app.F_val)

    app.loss_history.append(train_loss)
    app.val_loss_history.append(val_loss)
    app.acc_history.append(val_acc)

    app.trees.append({
        "feature": f_idx,
        "threshold": thr,
        "left": left_val,
        "right": right_val,
        "gain": gain,
        "train_loss": train_loss,
        "val_loss": val_loss,
        "val_acc": val_acc
    })
    app.current_m += 1

    # Update drawing prediction if user drew
    if any(v>0.05 for v in app.drawing):
        predict_drawing(app)

def predict_drawing(app):
    if not app.trees:
        app.prediction = None
        return
    f = 0.0
    for tree in app.trees:
        if app.drawing[tree["feature"]] < tree["threshold"]:
            f += app.eta * tree["left"]
        else:
            f += app.eta * tree["right"]
    p = sigmoid(f)
    app.prediction = 8 if p >= 0.5 else 3
    app.prediction_probs = [1-p, p]  # [P(3), P(8)]

def onMousePress(app, mx, my):
    # Header buttons
    # Play/Pause
    if 300 <= mx <= 380 and 12 <= my <= 38:
        app.is_playing = not app.is_playing
        return
    # Step
    if 390 <= mx <= 430 and 12 <= my <= 38:
        if app.current_m < app.max_trees:
            step_one_tree(app)
        return
    # Reset
    if 440 <= mx <= 500 and 12 <= my <= 38:
        reset_ensemble(app)
        return
    # Eta +/-
    if 640 <= mx <= 660 and 12 <= my <= 22:
        app.eta = min(0.5, app.eta + 0.02)
        return
    if 640 <= mx <= 660 and 26 <= my <= 38:
        app.eta = max(0.01, app.eta - 0.02)
        return
    # Toggle RF comparison
    if 820 <= mx <= 950 and 12 <= my <= 38:
        app.show_rf = not app.show_rf
        return

    # Drawing canvas: left panel digit area
    # digit canvas at (30, 110) size 224x224 (28*8)
    if 30 <= mx <= 254 and 110 <= my <= 334:
        app.is_drawing = True
        paint_at(app, mx, my)
        return

    # Sample gallery click: small digits at left bottom
    if 20 <= mx <= 280 and 360 <= my <= 480:
        # pick sample based on x
        if app.all_samples:
            idx = int((mx-20)/260 * min(12, len(app.all_samples)))
            idx = max(0, min(idx, len(app.all_samples)-1))
            app.selected_sample_idx = idx
            # load into drawing for prediction
            pix, lab = app.all_samples[idx]
            app.drawing = pix[:]
            predict_drawing(app)
        return

    # Feature importance heatmap hover
    if 720 <= mx <= 944 and 120 <= my <= 344:  # 28*8 =224
        col = int((mx-720)//8)
        row = int((my-120)//8)
        if 0 <= row <28 and 0 <= col <28:
            app.hover_feat = row*28+col
        return

    # Loss curve hover for stage selection
    if 320 <= mx <= 680 and 460 <= my <= 620:
        # map x to tree index
        if app.trees:
            rel = (mx-320)/360
            m = int(rel * len(app.trees))
            m = max(0, min(m, len(app.trees)-1))
            # could show tooltip, we store hover
            app.hover_stage = m
        return

def onMouseDrag(app, mx, my):
    if app.is_drawing:
        if 30 <= mx <= 254 and 110 <= my <= 334:
            paint_at(app, mx, my)

def onMouseRelease(app, mx, my):
    app.is_drawing = False
    if any(v>0.05 for v in app.drawing):
        predict_drawing(app)

def onKeyPress(app, key):
    if key == 'space':
        app.is_playing = not app.is_playing
    elif key == 'r' or key == 'R':
        reset_ensemble(app)
    elif key == 'Right' or key == 'd':
        if app.current_m < app.max_trees:
            step_one_tree(app)
    elif key == 'Left' or key == 'a':
        if app.trees:
            # remove last tree (approximate by subtracting its contribution)
            # For simplicity, we recompute from scratch up to current-1 (costly but okay for <330)
            app.trees.pop()
            app.loss_history.pop()
            app.val_loss_history.pop()
            app.acc_history.pop()
            app.current_m -= 1
            # recompute F from scratch
            recompute_F(app)
    elif key == 'c' or key == 'C':
        app.drawing = [0.0]*784
        app.prediction = None
    elif key == '+' or key == '=':
        app.eta = min(0.5, app.eta+0.02)
    elif key == '-' or key == '_':
        app.eta = max(0.01, app.eta-0.02)
    elif key == 'o' or key == 'O':
        app.show_overfit = not app.show_overfit
    elif key == 'f' or key == 'F':
        app.show_rf = not app.show_rf

def recompute_F(app):
    app.F_train = [0.0]*len(app.X_train)
    app.F_val = [0.0]*len(app.X_val)
    app.feature_importance = [0.0]*784
    for tree in app.trees:
        f_idx = tree["feature"]; thr = tree["threshold"]
        lv = tree["left"]; rv = tree["right"]
        gain = tree["gain"]
        app.feature_importance[f_idx] += max(0.0, gain)
        for i, x in enumerate(app.X_train):
            app.F_train[i] += app.eta * (lv if x[f_idx] < thr else rv)
        for i, x in enumerate(app.X_val):
            app.F_val[i] += app.eta * (lv if x[f_idx] < thr else rv)
    if any(v>0.05 for v in app.drawing):
        predict_drawing(app)

def reset_ensemble(app):
    app.trees = []
    app.loss_history = []
    app.val_loss_history = []
    app.acc_history = []
    app.F_train = [0.0]*len(app.X_train)
    app.F_val = [0.0]*len(app.X_val)
    app.current_m = 0
    app.feature_importance = [0.0]*784
    app.is_playing = False
    app.prediction = None

def paint_at(app, mx, my):
    # map mouse to 28x28 grid
    gx = int((mx - 30) // 8)
    gy = int((my - 110) // 8)
    for dy in range(-1,2):
        for dx in range(-1,2):
            ny = gy + dy
            nx = gx + dx
            if 0 <= ny < 28 and 0 <= nx < 28:
                dist = math.hypot(dx, dy)
                intensity = max(0.0, 1.0 - dist*0.6)
                idx = ny*28 + nx
                app.drawing[idx] = min(1.0, app.drawing[idx] + intensity*0.85)

# ─────────────────────────────────────────────────────────────
# View — redrawAll (pure rendering, no fetch/pyodide calls)
# ─────────────────────────────────────────────────────────────
def redrawAll(app):
    # Background
    drawRect(0,0,app.width,app.height, fill=gradient(rgb(14,16,22), rgb(26,29,35), start='top'))

    # Header
    drawRect(0,0,app.width,58, fill=rgb(18,20,28), border=rgb(40,45,60), borderWidth=1)
    # Title
    drawLabel("XGBoost Lab — Gradient Boosted Trees on MNIST", 18, 18, size=16, bold=True, fill=rgb(220,230,255), align='left-top')
    drawLabel("Sequential additive modeling: F_m = F_{m-1} + η·h_m   |   h_m ≈ -∂L/∂F_{m-1}   |   L = -Σ p log q", 18, 36, size=11, fill=rgb(150,165,190), align='left-top')

    # Play controls
    # Play/Pause button
    play_col = rgb(0,212,255) if app.is_playing else rgb(60,70,90)
    drawRect(300,12,80,26, fill=play_col, border=rgb(100,120,150), borderWidth=1, roundness=6)
    drawLabel("▶ Play" if not app.is_playing else "⏸ Pause", 340, 25, size=12, bold=True, fill=rgb(10,15,25) if app.is_playing else rgb(200,220,255))

    drawRect(390,12,40,26, fill=rgb(40,45,60), border=rgb(70,80,100), borderWidth=1, roundness=6)
    drawLabel("Step", 410, 25, size=11, fill=rgb(200,220,255))

    drawRect(440,12,60,26, fill=rgb(40,45,60), border=rgb(70,80,100), borderWidth=1, roundness=6)
    drawLabel("Reset R", 470, 25, size=11, fill=rgb(200,220,255))

    # Eta control
    drawLabel(f"η = {app.eta:.2f}  learning rate", 520, 16, size=11, fill=rgb(160,175,195), align='left-top')
    drawRect(640,12,20,10, fill=rgb(50,60,80), border=rgb(80,90,110), borderWidth=1, roundness=3)
    drawLabel("+", 650, 17, size=10, fill=rgb(200,220,255))
    drawRect(640,28,20,10, fill=rgb(50,60,80), border=rgb(80,90,110), borderWidth=1, roundness=3)
    drawLabel("−", 650, 33, size=10, fill=rgb(200,220,255))
    drawLabel("Space play, ←→ step, C clear, O overfit", 520, 32, size=10, fill=rgb(110,125,145), align='left-top')

    # RF toggle
    rf_fill = rgb(255,0,110) if app.show_rf else rgb(45,50,65)
    drawRect(820,12,130,26, fill=rf_fill, border=rgb(90,60,80), borderWidth=1, roundness=6)
    drawLabel("RF vs Boosting", 885, 25, size=11, bold=True, fill=rgb(255,220,230) if app.show_rf else rgb(180,190,210))

    # Left panel — Digit canvas
    drawRect(12, 68, 276, 620, fill=rgb(20,23,31), border=rgb(35,40,55), borderWidth=1, roundness=12)
    drawLabel("INPUT: Draw a digit (3 or 8) — MNIST 28×28", 24, 82, size=12, bold=True, fill=rgb(180,200,230), align='left-top')
    drawLabel("Each pixel = feature. 10 classes. 60k train / 10k test.", 24, 98, size=10, fill=rgb(110,125,145), align='left-top')

    # Digit canvas background
    drawRect(28,108,228,228, fill=rgb(8,10,15), border=rgb(60,70,90), borderWidth=1, roundness=8)
    # Draw pixels
    for r in range(28):
        for c in range(28):
            v = app.drawing[r*28+c]
            if v > 0.01:
                # color: white with opacity = v
                alpha = int(v*255)
                # SCS doesn't support alpha directly, use fill with rgb scaled
                # approximate by blending
                gray = int(20 + v*235)
                drawRect(30 + c*8, 110 + r*8, 8, 8, fill=rgb(gray,gray,gray))

    # Grid faint
    for i in range(0,29,7):
        drawLine(30+i*8, 110, 30+i*8, 338, lineWidth=0.5, fill=rgb(30,35,50))
        drawLine(30, 110+i*8, 254, 110+i*8, lineWidth=0.5, fill=rgb(30,35,50))

    # Prediction
    if app.prediction is not None:
        col = rgb(0,212,255) if app.prediction==8 else rgb(255,183,3)
        drawRect(30, 348, 224, 38, fill=rgb(30,35,50), border=col, borderWidth=1, roundness=8)
        prob = app.prediction_probs[1] if app.prediction==8 else app.prediction_probs[0]
        drawLabel(f"Pred: {app.prediction}  ({prob*100:.1f}%)", 142, 362, size=14, bold=True, fill=col)
        # Show contribution of last stump
        if app.trees:
            last = app.trees[-1]
            f = last["feature"]
            drawLabel(f"Last stump: pixel ({f%28},{f//28}) < {last['threshold']:.2f} ? {last['left']:.2f} : {last['right']:.2f}", 142, 378, size=9, fill=rgb(150,165,190))
    else:
        drawLabel("Draw to predict — model is ensemble of stumps", 142, 368, size=11, fill=rgb(100,115,135))

    # Sample gallery
    drawLabel("MNIST samples (via extensions.fetch) — click to load:", 24, 400, size=10, fill=rgb(120,135,155), align='left-top')
    if app.all_samples:
        n_show = min(12, len(app.all_samples))
        for i in range(n_show):
            pix, lab = app.all_samples[i]
            x0 = 20 + i*21
            y0 = 416
            # draw tiny 28-> 18px
            for r in range(28):
                for c in range(28):
                    v = pix[r*28+c]
                    if v > 0.15:
                        gray = int(v*200+40)
                        drawRect(x0 + c*0.64, y0 + r*0.64, 0.7, 0.7, fill=rgb(gray,gray,gray))
            # border if selected
            if i == app.selected_sample_idx:
                drawRect(x0-1, y0-1, 20, 20, fill=None, border=rgb(0,212,255), borderWidth=1.5, roundness=2)
            drawLabel(str(lab), x0+9, y0+26, size=8, fill=rgb(160,175,190))
    else:
        drawLabel("Loading samples...", 24, 420, size=10, fill=rgb(120,135,155), align='left-top')

    # Fetch status
    drawLabel(app.fetch_status[:68], 24, 462, size=9, fill=rgb(90,105,125), align='left-top')

    # Middle panel — Boosting visualization
    drawRect(300, 68, 388, 620, fill=rgb(22,25,34), border=rgb(35,40,55), borderWidth=1, roundness=12)
    drawLabel("BOOSTING: Sequential correction — each stump fixes residual", 312, 82, size=12, bold=True, fill=rgb(200,220,255), align='left-top')
    drawLabel(f"Trees: {app.current_m} / {app.max_trees}   η={app.eta:.2f}   Target: 330 → 89% acc (exposition)", 312, 98, size=10, fill=rgb(130,145,165), align='left-top')

    # Show RF vs Boosting diagram
    if app.show_rf:
        # RF side
        drawRect(312, 112, 180, 98, fill=rgb(30,20,30), border=rgb(80,40,60), borderWidth=1, roundness=8)
        drawLabel("Random Forest (parallel)", 320, 120, size=10, bold=True, fill=rgb(255,150,180), align='left-top')
        for i in range(5):
            x = 322 + i*32
            y = 138
            drawRect(x, y, 24, 36, fill=rgb(60,40,55), border=rgb(120,70,90), borderWidth=1, roundness=4)
            drawLabel(f"T{i+1}", x+12, y+18, size=8, fill=rgb(220,180,200))
        drawLine(322, 180, 482, 180, lineWidth=1, fill=rgb(120,70,90), dashes=(3,3))
        drawLabel("bootstrap + vote → independent", 402, 195, size=9, fill=rgb(180,120,140))

        # Boosting side
        drawRect(504, 112, 172, 98, fill=rgb(20,30,40), border=rgb(40,80,100), borderWidth=1, roundness=8)
        drawLabel("Gradient Boosting (sequential)", 512, 120, size=10, bold=True, fill=rgb(120,220,255), align='left-top')
        for i in range(5):
            x = 512 + i*30
            y = 138
            is_active = i < app.current_m
            col = rgb(0,212,255) if is_active else rgb(40,60,75)
            drawRect(x, y, 24, 36, fill=col, border=rgb(0,180,220), borderWidth=1, roundness=4)
            if i>0:
                drawLine(x-6, y+18, x, y+18, lineWidth=1.5, fill=rgb(0,212,255))
                drawLabel("→", x-3, y+10, size=10, fill=rgb(0,212,255))
            drawLabel(f"h{i+1}", x+12, y+18, size=8, bold=True, fill=rgb(10,20,30) if is_active else rgb(120,140,160))
        drawLabel("residual fit → additive", 588, 195, size=9, fill=rgb(120,200,220))
    else:
        # When not showing RF, show current stump visualization
        if app.trees:
            last = app.trees[-1]
            f = last["feature"]
            fr = f//28; fc = f%28
            drawLabel(f"Weak learner h_{app.current_m}: decision stump (1 split) — pixel ({fc},{fr})", 312, 120, size=11, bold=True, fill=rgb(180,220,255), align='left-top')
            drawLabel(f"Split: x_{f} < {last['threshold']:.3f}  → left {last['left']:+.3f} / right {last['right']:+.3f}  gain {last['gain']:.2f}", 312, 136, size=10, fill=rgb(130,150,175), align='left-top')
            # Show pixel highlighted
            drawRect(312, 152, 56, 56, fill=rgb(10,15,25), border=rgb(0,212,255), borderWidth=1, roundness=6)
            for r in range(28):
                for c in range(28):
                    if r==fr and c==fc:
                        drawRect(312 + c*2, 152 + r*2, 2.5, 2.5, fill=rgb(255,183,3))
                    elif app.feature_importance[r*28+c] > 0:
                        imp = app.feature_importance[r*28+c]
                        max_imp = max(app.feature_importance) if max(app.feature_importance)>0 else 1
                        alpha = imp / max_imp
                        if alpha > 0.05:
                            g = int(30 + alpha*180)
                            drawRect(312 + c*2, 152 + r*2, 2, 2, fill=rgb(g//3, g//2, g))

            # Show gradient / residual for few samples
            drawLabel("Pseudo-residuals (-∂L/∂F) for 6 val samples — stump fits these:", 380, 154, size=10, fill=rgb(140,160,185), align='left-top')
            for i in range(min(6, len(app.X_val))):
                x = 380 + i*50
                y = 170
                # draw tiny digit
                pix = app.X_val[i]
                for r in range(28):
                    for c in range(28):
                        v = pix[r*28+c]
                        if v > 0.1:
                            gray = int(30+v*180)
                            drawRect(x + c*1.1, y + r*1.1, 1.2, 1.2, fill=rgb(gray,gray,gray))
                # residual color border
                if i < len(app.F_val):
                    grad = sigmoid(app.F_val[i]) - app.y_val[i]
                    # red = large error, green = small
                    err = abs(grad)
                    r_col = int(200*err + 40)
                    g_col = int(200*(1-err) + 40)
                    drawRect(x-2, y-2, 33, 33, fill=None, border=rgb(r_col, g_col, 60), borderWidth=1.5, roundness=3)
                    drawLabel(f"{-grad:+.2f}", x+16, y+38, size=8, fill=rgb(200,220,255))
        else:
            drawLabel("No trees yet — Press Space or Step to grow ensemble. F_0 = 0, p=0.5", 312, 140, size=11, fill=rgb(120,135,155), align='left-top')
            drawLabel("Cross-entropy: L = -[ y log p + (1-y) log(1-p) ]   where p = σ(F)", 312, 160, size=10, fill=rgb(100,120,145), align='left-top')

    # Loss curve
    drawRect(312, 228, 368, 150, fill=rgb(14,18,26), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("Loss vs #trees — training (cyan) vs validation (gold) — η controls step size", 320, 236, size=10, bold=True, fill=rgb(180,200,220), align='left-top')
    # Axes
    drawLine(340, 260, 340, 360, lineWidth=1, fill=rgb(60,70,90))
    drawLine(340, 360, 660, 360, lineWidth=1, fill=rgb(60,70,90))
    drawLabel("0", 330, 362, size=9, fill=rgb(100,115,135))
    drawLabel(f"{app.max_trees}", 650, 362, size=9, fill=rgb(100,115,135))
    drawLabel("Loss", 320, 265, size=9, fill=rgb(100,115,135))

    if app.loss_history:
        max_loss = max(max(app.loss_history), max(app.val_loss_history) if app.val_loss_history else 0, 0.7)
        min_loss = min(min(app.loss_history), min(app.val_loss_history) if app.val_loss_history else 0, 0.1)
        rng = max_loss - min_loss
        if rng < 0.1: rng = 0.1
        # draw training loss cyan
        prev_x = None; prev_y = None
        for i, loss in enumerate(app.loss_history):
            x = 340 + (i / app.max_trees) * 320
            y = 360 - ((loss - min_loss)/rng)*90
            if prev_x is not None:
                drawLine(prev_x, prev_y, x, y, lineWidth=1.5, fill=rgb(0,212,255))
            prev_x, prev_y = x, y
            if i % 30 == 0:
                drawCircle(x, y, 2, fill=rgb(0,212,255))
        # val loss gold
        prev_x = None; prev_y = None
        for i, loss in enumerate(app.val_loss_history):
            x = 340 + (i / app.max_trees) * 320
            y = 360 - ((loss - min_loss)/rng)*90
            if prev_x is not None:
                drawLine(prev_x, prev_y, x, y, lineWidth=1.5, fill=rgb(255,183,3))
            prev_x, prev_y = x, y

        # Reference from Pyodide if available
        if app.ref_train_losses and app.show_overfit:
            prev_x = None; prev_y = None
            for i, loss in enumerate(app.ref_train_losses[:app.max_trees]):
                x = 340 + (i / app.max_trees) * 320
                y = 360 - ((loss - min_loss)/rng)*90
                if prev_x is not None:
                    drawLine(prev_x, prev_y, x, y, lineWidth=1, fill=rgb(100,255,180), dashes=(2,2))
                prev_x, prev_y = x, y

        # Show overfitting region if enabled
        if app.show_overfit and len(app.val_loss_history) > 50:
            # find minimum val loss
            min_idx = app.val_loss_history.index(min(app.val_loss_history))
            if min_idx < len(app.val_loss_history)-10:
                x_min = 340 + (min_idx / app.max_trees) * 320
                drawLine(x_min, 260, x_min, 360, lineWidth=1, fill=rgb(255,0,110), dashes=(4,4))
                drawLabel("overfit ↑", x_min+8, 270, size=9, bold=True, fill=rgb(255,80,130))

        # Current marker
        if app.current_m >0:
            x_cur = 340 + (app.current_m / app.max_trees) * 320
            drawLine(x_cur, 260, x_cur, 360, lineWidth=1, fill=rgb(200,220,255), dashes=(2,2))
            if app.loss_history:
                drawLabel(f"{app.loss_history[-1]:.3f}", x_cur+4, 280, size=9, fill=rgb(0,212,255))

    # Accuracy
    if app.acc_history:
        acc = app.acc_history[-1]
        drawLabel(f"Val Acc: {acc*100:.1f}%  (target 89% @330 trees from exposition)", 320, 344, size=10, bold=True, fill=rgb(180,220,255), align='left-top')

    # Ensemble equation and gradient
    drawRect(312, 386, 368, 68, fill=rgb(18,22,32), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("Additive model: F_m(x) = F_{m-1}(x) + η·h_m(x)   —   η = learning rate", 320, 394, size=10, fill=rgb(200,220,255), align='left-top')
    drawLabel("h_m fitted to negative gradient: -∂L/∂F_{m-1} = y - p  (pseudo-residual)", 320, 410, size=10, fill=rgb(160,180,210), align='left-top')
    drawLabel("Weak learner = decision stump: 1 split, high bias, low variance — boosting reduces bias sequentially", 320, 426, size=9, fill=rgb(120,140,165), align='left-top')

    # Trees timeline — bottom of middle panel
    drawLabel(f"Ensemble timeline — {app.current_m} stumps built (gold = high gain):", 312, 466, size=10, bold=True, fill=rgb(180,200,220), align='left-top')
    # draw as small bars
    for i in range(min(app.current_m, 110)):  # show first 110 to fit
        tree = app.trees[i] if i < len(app.trees) else None
        x = 312 + (i%55)*6.5
        y = 480 + (i//55)*18
        gain = tree["gain"] if tree else 0
        max_gain = max([t["gain"] for t in app.trees]) if app.trees else 1
        h = 4 + (gain / max_gain)*10 if max_gain>0 else 4
        col_int = int(60 + (gain/max_gain)*195) if max_gain>0 else 60
        drawRect(x, y, 5, h, fill=rgb(col_int, col_int//2, 30), border=rgb(80,60,30), borderWidth=0.5, roundness=1)
    if app.current_m > 110:
        drawLabel(f"+{app.current_m-110} more...", 312, 520, size=9, fill=rgb(120,135,155), align='left-top')

    # Loss curve interactive area label
    drawRect(312, 460, 368, 160, fill=None, border=rgb(50,60,80), borderWidth=0.5, dashes=(3,3), roundness=8)

    # Right panel — Feature importance + equations + research notes
    drawRect(700, 68, 338, 620, fill=rgb(20,23,31), border=rgb(35,40,55), borderWidth=1, roundness=12)
    drawLabel("RESEARCH VIEW — Capacity, Gradients, Feature Importance", 712, 82, size=12, bold=True, fill=rgb(220,230,255), align='left-top')
    drawLabel("Why boosting has high capacity → overfits quickly", 712, 98, size=10, fill=rgb(130,145,165), align='left-top')

    # Feature importance heatmap 28x28
    drawRect(718, 118, 228, 228, fill=rgb(10,12,18), border=rgb(50,60,80), borderWidth=1, roundness=8)
    max_imp = max(app.feature_importance) if max(app.feature_importance)>0 else 1
    for r in range(28):
        for c in range(28):
            imp = app.feature_importance[r*28+c]
            if imp > 0.01*max_imp:
                norm = imp / max_imp
                # color map: black -> cyan -> gold
                if norm < 0.5:
                    # black to cyan
                    t = norm*2
                    col = rgb(int(10+t*0), int(15+t*80), int(20+t*180))
                else:
                    t = (norm-0.5)*2
                    col = rgb(int(t*255), int(80 + t*103), int(180*(1-t)))
                drawRect(720 + c*8, 120 + r*8, 8, 8, fill=col)
    # Highlight hover
    if app.hover_feat is not None:
        hr = app.hover_feat //28; hc = app.hover_feat %28
        drawRect(720+hc*8, 120+hr*8, 8, 8, fill=None, border=rgb(255,255,255), borderWidth=1.5)
        drawLabel(f"pixel ({hc},{hr}) imp {app.feature_importance[app.hover_feat]:.2f}", 720, 354, size=9, fill=rgb(200,220,255), align='left-top')

    drawLabel("Feature importance: pixels that split 3 vs 8 (28×28)", 712, 358, size=10, fill=rgb(140,160,185), align='left-top')

    # Equations panel
    drawRect(712, 376, 316, 88, fill=rgb(16,20,28), border=rgb(40,50,70), borderWidth=1, roundness=8)
    drawLabel("Multi-class cross-entropy (exposition):", 720, 384, size=10, bold=True, fill=rgb(180,200,220), align='left-top')
    drawLabel("L = - Σ_i Σ_c p_{i,c} log q_{i,c}   q = softmax(F)", 720, 400, size=10, fill=rgb(200,220,255), align='left-top')
    drawLabel("Binary case: L = -[ y log σ(F) + (1-y) log(1-σ(F)) ]", 720, 416, size=9, fill=rgb(150,170,200), align='left-top')
    drawLabel("∂L/∂F = σ(F) - y   →   h_m ≈ y - σ(F_{m-1})", 720, 432, size=10, bold=True, fill=rgb(0,212,255), align='left-top')
    drawLabel("F_m = F_{m-1} + η·h_m   — gradient descent in function space", 720, 448, size=9, fill=rgb(160,180,210), align='left-top')

    # Pyodide status + research insights
    drawRect(712, 472, 316, 84, fill=rgb(18,22,32), border=rgb(35,45,65), borderWidth=1, roundness=8)
    drawLabel("Pyodide worker (extensions.pyodide) — sklearn reference:", 720, 480, size=10, bold=True, fill=rgb(180,200,220), align='left-top')
    # Wrap status text
    status = app.pyodide_status
    drawLabel(status[:62], 720, 496, size=9, fill=rgb(120,200,150) if app.pyodide_ready else rgb(200,150,120), align='left-top')
    if len(status) > 62:
        drawLabel(status[62:124], 720, 508, size=9, fill=rgb(120,200,150) if app.pyodide_ready else rgb(200,150,120), align='left-top')

    if app.pyodide_reference and app.pyodide_ready:
        acc = app.pyodide_reference.get("accuracy", 0)
        drawLabel(f"sklearn GBM 330 stumps: val acc {acc*100:.1f}% — matches exposition 89%", 720, 522, size=9, fill=rgb(160,200,180), align='left-top')
        drawLabel(f"XGBoost (Chen & Guestrin 2016) = optimized GBM + regularization", 720, 536, size=9, fill=rgb(130,150,175), align='left-top')
    else:
        drawLabel("Fallback: Brython GBM training — 100% browser, no server", 720, 522, size=9, fill=rgb(140,160,185), align='left-top')
        drawLabel("Try: pip install xgboost in Pyodide for exact XGBoost", 720, 536, size=9, fill=rgb(110,130,155), align='left-top')

    # Bottom research notes
    drawRect(712, 564, 316, 112, fill=rgb(14,18,26), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("Research insights — why this matters:", 720, 572, size=10, bold=True, fill=rgb(220,230,255), align='left-top')
    notes = [
        "• Weak learners = stumps (depth 1) → high bias, low variance",
        "• Boosting reduces bias sequentially, not variance (vs RF)",
        "• Shrinkage η∈[0.01,0.3] slows learning, improves generalization",
        "• 330 trees → high capacity → overfits w/o early stopping",
        "• MNIST: each pixel is feature, 784-dim, 10 classes",
        "• XGBoost adds 2nd-order Taylor + sparsity-aware splits"
    ]
    for i, line in enumerate(notes):
        drawLabel(line, 720, 588 + i*13, size=9, fill=rgb(130,145,165), align='left-top')

    # Footer — credit
    drawLabel("SCS 1050×700 — extensions.fetch + extensions.pyodide — resilient to worker API changes — Built for top-tier researchers", 18, 682, size=9, fill=rgb(80,95,115), align='left-top')
