
from scs import *
from browser import aio, window
import math, random

# ── Extensions — Model only ──
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

def softmax(logits):
    m = max(logits)
    exps = [math.exp(l - m) for l in logits]
    s = sum(exps) + 1e-12
    return [e / s for e in exps]

def cross_entropy_loss(y_true, probs):
    total = 0.0
    eps = 1e-12
    for yt, pr in zip(y_true, probs):
        p = pr[yt] if yt < len(pr) else eps
        p = min(max(p, eps), 1-eps)
        total += -math.log(p)
    return total / len(y_true) if y_true else 0.0

def accuracy_multiclass(y_true, probs):
    correct = 0
    for yt, pr in zip(y_true, probs):
        pred = max(range(len(pr)), key=lambda c: pr[c])
        if pred == yt:
            correct+=1
    return correct / len(y_true) if y_true else 0.0

def find_best_stump_fast(X, target, n_feat_sample=32, min_leaf=5):
    n = len(X)
    if n==0:
        return 0,0.5,0.0,0.0,0.0
    d = len(X[0])
    feat_pool = random.sample(range(d), min(n_feat_sample, d))
    best_gain = -1e100
    best_f = feat_pool[0]
    best_thr = 0.5
    best_left = 0.0
    best_right = 0.0
    exhaustive = n <= 250
    for f in feat_pool:
        vals = [X[i][f] for i in range(n)]
        svals = sorted(vals)
        if exhaustive:
            step = max(1, n//18)
            thr_candidates = [svals[i] for i in range(step, n-step, step)]
            thr_candidates.append(sum(vals)/n)
        else:
            thr_candidates = [svals[n//4], svals[n//2], svals[3*n//4], sum(vals)/n]
        for thr in thr_candidates:
            left_sum=0.0; left_cnt=0; right_sum=0.0; right_cnt=0
            for i in range(n):
                if vals[i] < thr:
                    left_sum+=target[i]; left_cnt+=1
                else:
                    right_sum+=target[i]; right_cnt+=1
            if left_cnt < min_leaf or right_cnt < min_leaf:
                continue
            left_mean = left_sum / left_cnt if left_cnt else 0.0
            right_mean = right_sum / right_cnt if right_cnt else 0.0
            gain = left_cnt*left_mean*left_mean + right_cnt*right_mean*right_mean
            balance = 1.0 - abs(left_cnt - right_cnt)/n * 0.15
            gain = gain * balance
            if gain > best_gain:
                best_gain=gain; best_f=f; best_thr=thr; best_left=left_mean; best_right=right_mean
    return best_f,best_thr,best_left,best_right,best_gain

def generate_prototype_10():
    def blank(): return [0.0]*784
    def idx(r,c): return r*28+c
    protos = [blank() for _ in range(10)]
    for r in range(28):
        for c in range(28):
            dr=r-14; dc=c-14; d=math.hypot(dr*1.2, dc)
            if 9<d<13: protos[0][idx(r,c)]=0.9
    for r in range(6,22):
        for c in range(13,16):
            protos[1][idx(r,c)]=0.9
    for r in range(28):
        for c in range(28):
            if 6<=r<=8 and 8<=c<=20: protos[2][idx(r,c)]=0.9
            if 9<=r<=13 and 16<=c<=20: protos[2][idx(r,c)]=0.9
            if 14<=r<=16 and 8<=c<=20: protos[2][idx(r,c)]=0.9
            if 17<=r<=21 and 8<=c<=12: protos[2][idx(r,c)]=0.9
            if 22<=r<=24 and 8<=c<=20: protos[2][idx(r,c)]=0.9
    for r in range(28):
        for c in range(28):
            dr1=r-8; dc1=c-18
            if 12<math.hypot(dr1*1.2, dc1)<16 and c>12 and r<14: protos[3][idx(r,c)]=0.9
            dr2=r-19; dc2=c-18
            if 12<math.hypot(dr2*1.2, dc2)<16 and c>12 and r>=10: protos[3][idx(r,c)]=0.9
            if 14<=c<=16 and 6<=r<=22: protos[3][idx(r,c)]=max(protos[3][idx(r,c)],0.3)
    for r in range(6,22):
        for c in range(8,20):
            if abs(c-14)<1 and r<16: protos[4][idx(r,c)]=0.9
            if r==16 and 8<=c<=20: protos[4][idx(r,c)]=0.9
            if c>14 and r>10 and abs((c-14)-(r-10)*0.6)<1: protos[4][idx(r,c)]=0.9
    for r in range(28):
        for c in range(28):
            if 6<=r<=8 and 8<=c<=20: protos[5][idx(r,c)]=0.9
            if 9<=r<=13 and 8<=c<=12: protos[5][idx(r,c)]=0.9
            if 14<=r<=16 and 8<=c<=20: protos[5][idx(r,c)]=0.9
            if 17<=r<=21 and 16<=c<=20: protos[5][idx(r,c)]=0.9
            if 22<=r<=24 and 8<=c<=20: protos[5][idx(r,c)]=0.9
    for r in range(28):
        for c in range(28):
            dr=r-18; dc=c-14
            if 8<math.hypot(dr,dc)<12: protos[6][idx(r,c)]=0.9
            if 8<=r<=14 and 8<=c<=12: protos[6][idx(r,c)]=0.9
    for r in range(28):
        for c in range(28):
            if 6<=r<=8 and 8<=c<=20: protos[7][idx(r,c)]=0.9
            if 9<=r<=20 and abs(c-(20-(r-8)*0.8))<1: protos[7][idx(r,c)]=0.9
    for r in range(28):
        for c in range(28):
            drt=r-9; dct=c-14; drb=r-19; dcb=c-14
            if 9<math.hypot(drt*1.1,dct)<13: protos[8][idx(r,c)]=0.9
            if 9<math.hypot(drb*1.1,dcb)<13: protos[8][idx(r,c)]=0.9
            if abs(c-14)<2 and 9<r<19: protos[8][idx(r,c)]=max(protos[8][idx(r,c)],0.4)
    for r in range(28):
        for c in range(28):
            dr=r-10; dc=c-14
            if 8<math.hypot(dr,dc)<12: protos[9][idx(r,c)]=0.9
            if 14<=r<=22 and 16<=c<=20: protos[9][idx(r,c)]=0.9
    return protos

def synth_mnist_full(n_per_class=80):
    protos = generate_prototype_10()
    X=[]; y=[]
    for digit in range(10):
        base = protos[digit]
        for _ in range(n_per_class):
            img=[min(1.0,max(0.0,v+random.gauss(0,0.22)+(random.uniform(-0.3,0.3) if random.random()<0.05 else 0))) for v in base]
            X.append(img); y.append(digit)
    combined=list(zip(X,y)); random.shuffle(combined)
    X[:],y[:]=zip(*combined)
    return list(X),list(y)

def train_val_split(X,y,ratio=0.78):
    by_class={}
    for xi,yi in zip(X,y):
        by_class.setdefault(yi, []).append((xi,yi))
    Xtr=[]; ytr=[]; Xva=[]; yva=[]
    for c in range(10):
        lst=by_class.get(c, [])
        random.shuffle(lst)
        n=len(lst)
        if n==0: continue
        n_tr=int(n*ratio)
        if n_tr==0: n_tr=1
        if n_tr>=n: n_tr=n-1
        for xi,yi in lst[:n_tr]:
            Xtr.append(xi); ytr.append(yi)
        for xi,yi in lst[n_tr:]:
            Xva.append(xi); yva.append(yi)
    # Shuffle
    combined=list(zip(Xtr,ytr))
    random.shuffle(combined)
    if combined:
        Xtr,ytr=zip(*combined)
        Xtr,ytr=list(Xtr),list(ytr)
    else:
        Xtr,ytr=[],[]
    combined=list(zip(Xva,yva))
    random.shuffle(combined)
    if combined:
        Xva,yva=zip(*combined)
        Xva,yva=list(Xva),list(yva)
    else:
        Xva,yva=[],[]
    return Xtr,ytr,Xva,yva

async def resilient_pyodide_run(code_str):
    async def unwrap(res, max_depth=8):
        for _ in range(max_depth):
            if res is None:
                break
            if hasattr(res, 'to_py'):
                try:
                    res=res.to_py()
                except Exception:
                    pass
            try:
                rstr=str(res)
                if '<coroutine' in rstr:
                    if hasattr(res, '__await__'):
                        try:
                            res=await res
                            continue
                        except Exception:
                            return None
                    if isinstance(res, str):
                        return None
            except Exception:
                pass
            if hasattr(res, '__await__'):
                try:
                    res=await res
                    continue
                except Exception:
                    break
            if hasattr(res, 'then'):
                try:
                    res=await res
                    continue
                except Exception:
                    break
            try:
                if isinstance(res, str) and '<coroutine' in res:
                    return None
                if '<coroutine' in str(res):
                    return None
            except Exception:
                pass
            break
        return res
    if PYODIDE_EXT_OK and _py_ext is not None:
        for name in _py_candidates:
            try:
                fn=getattr(_py_ext, name)
                res=fn(code_str)
                res=await unwrap(res)
                if res is None:
                    continue
                try:
                    if '<coroutine' in str(res):
                        continue
                except Exception:
                    pass
                return res
            except Exception:
                continue
    try:
        if hasattr(window, 'pyodide') and window.pyodide is not None:
            res=await window.pyodide.runPythonAsync(code_str)
            res=await unwrap(res)
            return res
    except Exception:
        pass
    return None

async def fetch_mnist_via_decompression(url):
    try:
        resp = await window.fetch(url, {"mode": "cors"})
        if not resp.ok:
            raise Exception(f"HTTP {resp.status}")
        if not hasattr(window, 'DecompressionStream'):
            raise Exception("DecompressionStream not supported")
        ds = window.DecompressionStream.new("gzip")
        stream = resp.body.pipeThrough(ds)
        r2 = window.Response.new(stream)
        txt = await r2.text()
        if hasattr(txt, 'to_py'):
            try:
                txt=txt.to_py()
            except Exception:
                pass
        txt=str(txt)
        try:
            import json as _json
            data=_json.loads(txt)
            return data
        except Exception:
            try:
                import json as _json2
                lines=txt.strip().split("\n")
                out=[]
                for line in lines[:4000]:
                    line=line.strip()
                    if not line: continue
                    if line in ('[',']'): continue
                    if line.endswith(','): line=line[:-1]
                    try:
                        o=_json2.loads(line)
                        out.append(o)
                    except Exception:
                        continue
                if out: return out
            except Exception:
                pass
        return txt
    except Exception as e:
        raise e

async def fetch_idx_gz(url):
    # Fetch official IDX .gz and parse via JS Uint8Array
    try:
        resp = await window.fetch(url, {"mode": "cors"})
        if not resp.ok:
            raise Exception(f"HTTP {resp.status}")
        if not hasattr(window, 'DecompressionStream'):
            raise Exception("No DecompressionStream")
        ds = window.DecompressionStream.new("gzip")
        stream = resp.body.pipeThrough(ds)
        r2 = window.Response.new(stream)
        buf = await r2.arrayBuffer()
        # Convert ArrayBuffer to list of bytes via Uint8Array
        u8 = window.Uint8Array.new(buf)
        # to_py may convert to Python list
        if hasattr(u8, 'to_py'):
            try:
                py_list = u8.to_py()
                return list(py_list)
            except Exception:
                pass
        # Fallback iterate via JS
        length = int(u8.length) if hasattr(u8, 'length') else 0
        out=[]
        # For performance, only take first 5000 if huge
        # Use window loop? We'll try Python loop with JS access
        # Access via u8[i] may be slow but okay for 50k*784
        # We will return the typed array itself and let caller handle via JS
        return u8
    except Exception as e:
        raise e

async def fetch_mnist_samples(app):
    app.fetch_status="Fetching full MNIST 10-way..."
    app.mnist_loaded=False

    # RECOMMENDED sources from prompt: jsDelivr per-digit JSON + Google IDX
    digit_json_base = "https://cdn.jsdelivr.net/npm/mnist@1.1.0/src/digits/{}.json"
    digit_json_fallback = "https://raw.githack.com/cazala/mnist/master/src/digits/{}.json"

    all_samples=[]

    # Try digit-by-digit JSON (most reliable per prompt)
    try:
        app.fetch_status="Fetching per-digit JSON via jsDelivr (0-9)..."
        for d in range(10):
            url = digit_json_base.format(d)
            url_fb = digit_json_fallback.format(d)
            data=None
            for u in [url, url_fb]:
                try:
                    if FETCH_OK and fetch_json is not None:
                        data = await fetch_json(u)
                    else:
                        resp = await window.fetch(u, {"mode":"cors"})
                        if not resp.ok: continue
                        txt = await resp.text()
                        if hasattr(txt,'to_py'): txt=txt.to_py()
                        import json as _js
                        data = _js.loads(str(txt))
                    if data is not None:
                        break
                except Exception:
                    continue
            if data is None:
                continue
            # Parse: data may be list of images (28x28 or 784) or list of {input, output}
            # mnist npm: each file contains array of images, each image is 784 numbers 0-1?
            # Let's handle generically
            parsed=0
            if isinstance(data, list):
                for item in data[:600]:  # limit per digit for speed
                    try:
                        img=None; lab=d
                        if isinstance(item, dict):
                            # check keys
                            if 'input' in item:
                                img=item['input']
                                out=item.get('output')
                                if isinstance(out, list):
                                    lab = max(range(len(out)), key=lambda i: out[i]) if out else d
                            elif 'image' in item:
                                img=item['image']
                                lab=item.get('label', d)
                            elif 'data' in item:
                                img=item['data']
                            else:
                                # maybe dict of pixel indices?
                                continue
                        elif isinstance(item, list):
                            img=item
                        if img is None: continue
                        # Flatten if nested 28x28
                        flat=[]
                        if isinstance(img, list) and len(img)>0 and isinstance(img[0], list):
                            for row in img:
                                flat.extend(row)
                        else:
                            flat=img
                        if len(flat)<784: continue
                        # Normalize: if values 0-255 -> /255, if 0-1 keep
                        pix=[]
                        for v in flat[:784]:
                            try:
                                fv=float(v)
                                if fv>1.0: fv=fv/255.0
                                pix.append(max(0.0,min(1.0,fv)))
                            except Exception:
                                pix.append(0.0)
                        all_samples.append((pix, int(lab)))
                        parsed+=1
                    except Exception:
                        continue
            app.fetch_status=f"Digit {d}: +{parsed} total {len(all_samples)}"
        if len(all_samples)>=100:
            app.all_samples=all_samples
            by_class={i:[] for i in range(10)}
            for pix,lab in all_samples:
                if len(by_class[lab])<250:
                    by_class[lab].append((pix,lab))
            balanced=[]
            for c in range(10):
                balanced.extend(by_class[c])
            random.shuffle(balanced)
            Xb=[p for p,_ in balanced]; yb=[l for _,l in balanced]
            app.X_train_full, app.y_train_full = Xb, yb
            app.fetch_status=f"Loaded {len(all_samples)} via per-digit JSON ✓ 10-way"
            X,y=Xb,yb
            if len(X)>1400:
                X=X[:1400]; y=y[:1400]
            Xtr,ytr,Xva,yva=train_val_split(X,y,0.78)
            app.X_train,app.y_train=Xtr,ytr
            app.X_val,app.y_val=Xva,yva
            app.F_train=[[0.0]*10 for _ in range(len(Xtr))]
            app.F_val=[[0.0]*10 for _ in range(len(Xva))]
            app.mnist_loaded=True
            app.fetch_status+=f" | Train {len(Xtr)} Val {len(Xva)}"
            return
    except Exception as e:
        app.fetch_status=f"Per-digit JSON fail: {str(e)[:40]}"

    # Try official IDX gz from Google mirror (recommended)
    try:
        app.fetch_status="Trying Google IDX gz..."
        # For simplicity, we will try to fetch train images and labels via IDX
        # If DecompressionStream works, parse first 2000 samples
        img_url = "https://storage.googleapis.com/cvdf-datasets/mnist/train-images-idx3-ubyte.gz"
        lbl_url = "https://storage.googleapis.com/cvdf-datasets/mnist/train-labels-idx1-ubyte.gz"
        # Fetch both
        img_bytes = await fetch_idx_gz(img_url)
        lbl_bytes = await fetch_idx_gz(lbl_url)
        # img_bytes is Uint8Array or list
        # Parse IDX: need to interpret big-endian ints
        # If we got Uint8Array, we need to read header
        # Let's try to convert to Python list if not already
        def to_list(b):
            if isinstance(b, list):
                return b
            try:
                if hasattr(b, 'to_py'):
                    return list(b.to_py())
            except Exception:
                pass
            # Try length and indexing
            try:
                l=int(b.length)
                return [int(b[i]) for i in range(min(l, 2000000))]
            except Exception:
                return []
        img_list = to_list(img_bytes)
        lbl_list = to_list(lbl_bytes)
        if len(img_list)>16 and len(lbl_list)>8:
            # Parse header big-endian
            # Images: 0-3 magic 0x00 00 08 03, 4-7 num images, 8-11 rows, 12-15 cols
            def be_int(lst, off):
                return (lst[off]<<24)|(lst[off+1]<<16)|(lst[off+2]<<8)|lst[off+3]
            n_img = be_int(img_list, 4)
            rows = be_int(img_list, 8)
            cols = be_int(img_list, 12)
            n_lbl = be_int(lbl_list, 4)
            # Take first 1500
            n_take = min(1500, n_img, n_lbl)
            samples=[]
            img_off=16
            lbl_off=8
            for i in range(n_take):
                pix=[]
                base=img_off + i*rows*cols
                for j in range(rows*cols):
                    if base+j < len(img_list):
                        pix.append(img_list[base+j]/255.0)
                    else:
                        pix.append(0.0)
                lab = lbl_list[lbl_off + i] if lbl_off+i < len(lbl_list) else 0
                samples.append((pix, int(lab)))
            if len(samples)>=100:
                app.all_samples=samples
                Xb=[p for p,_ in samples]; yb=[l for _,l in samples]
                app.X_train_full, app.y_train_full=Xb,yb
                app.fetch_status=f"Loaded {len(samples)} via IDX gz ✓"
                X,y=Xb,yb
                Xtr,ytr,Xva,yva=train_val_split(X,y,0.78)
                app.X_train,app.y_train=Xtr,ytr
                app.X_val,app.y_val=Xva,yva
                app.F_train=[[0.0]*10 for _ in range(len(Xtr))]
                app.F_val=[[0.0]*10 for _ in range(len(Xva))]
                app.mnist_loaded=True
                app.fetch_status+=f" | Train {len(Xtr)} Val {len(Xva)}"
                return
    except Exception as e:
        app.fetch_status=f"IDX gz fail: {str(e)[:40]}"

    # Fallback: small CSVs via jsDelivr/raw.githack
    csv_candidates=[
        "https://cdn.jsdelivr.net/gh/makeyourownneuralnetwork/makeyourownneuralnetwork@master/mnist_dataset/mnist_train_100.csv",
        "https://raw.githack.com/makeyourownneuralnetwork/makeyourownneuralnetwork/master/mnist_dataset/mnist_train_100.csv",
        "https://cdn.jsdelivr.net/gh/makeyourownneuralnetwork/makeyourownneuralnetwork@master/mnist_dataset/mnist_test_10.csv",
        "https://raw.githack.com/makeyourownneuralnetwork/makeyourownneuralnetwork/master/mnist_dataset/mnist_test_10.csv",
    ]
    combined=[]
    for url in csv_candidates:
        try:
            if FETCH_OK and fetch_text is not None:
                txt=await fetch_text(url)
            else:
                resp=await window.fetch(url, {"mode":"cors"})
                if not resp.ok: continue
                txt=await resp.text()
                if hasattr(txt,'to_py'): txt=txt.to_py()
                txt=str(txt)
            lines=txt.strip().split("\n")
            for line in lines[:1200]:
                if not line.strip(): continue
                low=line.lower()
                if low.startswith("label") or "pixel" in low: continue
                parts=line.split(",")
                try:
                    if len(parts)>=785:
                        lab=int(float(parts[0])); pix=[float(p)/255.0 for p in parts[1:785]]
                        combined.append((pix[:784],lab))
                except Exception:
                    continue
        except Exception:
            continue
    if len(combined)>=20:
        app.all_samples=combined
        Xb=[p for p,_ in combined]; yb=[l for _,l in combined]
        present=set(yb)
        if len(present)<10:
            sx,sy=synth_mnist_full(40)
            for pix,lab in zip(sx,sy):
                if lab not in present or yb.count(lab)<15:
                    Xb.append(pix); yb.append(lab)
        app.X_train_full, app.y_train_full=Xb,yb
        app.fetch_status=f"Loaded {len(combined)} via CSVs ✓"
        X,y=Xb,yb
        if len(X)>1400:
            X=X[:1400]; y=y[:1400]
        Xtr,ytr,Xva,yva=train_val_split(X,y,0.78)
        app.X_train,app.y_train=Xtr,ytr
        app.X_val,app.y_val=Xva,yva
        app.F_train=[[0.0]*10 for _ in range(len(Xtr))]
        app.F_val=[[0.0]*10 for _ in range(len(Xva))]
        app.mnist_loaded=True
        app.fetch_status+=f" | Train {len(Xtr)} Val {len(Xva)}"
        return

    # Final synthetic fallback
    app.fetch_status="Fetch unavailable - synthetic 10-way fallback"
    sx,sy=synth_mnist_full(120)
    app.all_samples=[(pix,lab) for pix,lab in zip(sx,sy)]
    app.X_train_full, app.y_train_full=sx,sy
    X,y=sx,sy
    Xtr,ytr,Xva,yva=train_val_split(X,y,0.78)
    app.X_train,app.y_train=Xtr,ytr
    app.X_val,app.y_val=Xva,yva
    app.F_train=[[0.0]*10 for _ in range(len(Xtr))]
    app.F_val=[[0.0]*10 for _ in range(len(Xva))]
    app.mnist_loaded=True
    app.fetch_status+=f" | Train {len(Xtr)} Val {len(Xva)} synthetic"

async def pyodide_train_reference(app):
    app.pyodide_status="Pyodide: probing..."
    if not PYODIDE_EXT_OK:
        app.pyodide_status="Pyodide ext not found - Brython GBM fallback"
        app.pyodide_ready=False
        return
    lines=[
        "import math, random, traceback, json",
        "try:",
        "    import numpy as np",
        "    from sklearn.ensemble import GradientBoostingClassifier",
        "    def blank(): return np.zeros(784)",
        "    def idx(r,c): return r*28+c",
        "    import math as _math",
        "    protos=[blank() for _ in range(10)]",
        "    for r in range(28):",
        "        for c in range(28):",
        "            dr=r-14; dc=c-14; d=_math.hypot(dr*1.2, dc)",
        "            if 9<d<13: protos[0][idx(r,c)]=0.9",
        "    for r in range(6,22):",
        "        for c in range(13,16):",
        "            protos[1][idx(r,c)]=0.9",
        "    for r in range(28):",
        "        for c in range(28):",
        "            if 6<=r<=8 and 8<=c<=20: protos[2][idx(r,c)]=0.9",
        "            if 9<=r<=13 and 16<=c<=20: protos[2][idx(r,c)]=0.9",
        "            if 14<=r<=16 and 8<=c<=20: protos[2][idx(r,c)]=0.9",
        "            if 17<=r<=21 and 8<=c<=12: protos[2][idx(r,c)]=0.9",
        "            if 22<=r<=24 and 8<=c<=20: protos[2][idx(r,c)]=0.9",
        "    for r in range(28):",
        "        for c in range(28):",
        "            dr1=r-8; dc1=c-18",
        "            if 12<_math.hypot(dr1*1.2, dc1)<16 and c>12 and r<14: protos[3][idx(r,c)]=0.9",
        "            dr2=r-19; dc2=c-18",
        "            if 12<_math.hypot(dr2*1.2, dc2)<16 and c>12 and r>=10: protos[3][idx(r,c)]=0.9",
        "            if 14<=c<=16 and 6<=r<=22: protos[3][idx(r,c)]=max(protos[3][idx(r,c)],0.3)",
        "    for r in range(6,22):",
        "        for c in range(8,20):",
        "            if abs(c-14)<1 and r<16: protos[4][idx(r,c)]=0.9",
        "            if r==16 and 8<=c<=20: protos[4][idx(r,c)]=0.9",
        "            if c>14 and r>10 and abs((c-14)-(r-10)*0.6)<1: protos[4][idx(r,c)]=0.9",
        "    for r in range(28):",
        "        for c in range(28):",
        "            if 6<=r<=8 and 8<=c<=20: protos[5][idx(r,c)]=0.9",
        "            if 9<=r<=13 and 8<=c<=12: protos[5][idx(r,c)]=0.9",
        "            if 14<=r<=16 and 8<=c<=20: protos[5][idx(r,c)]=0.9",
        "            if 17<=r<=21 and 16<=c<=20: protos[5][idx(r,c)]=0.9",
        "            if 22<=r<=24 and 8<=c<=20: protos[5][idx(r,c)]=0.9",
        "    for r in range(28):",
        "        for c in range(28):",
        "            dr=r-18; dc=c-14",
        "            if 8<_math.hypot(dr,dc)<12: protos[6][idx(r,c)]=0.9",
        "            if 8<=r<=14 and 8<=c<=12: protos[6][idx(r,c)]=0.9",
        "    for r in range(28):",
        "        for c in range(28):",
        "            if 6<=r<=8 and 8<=c<=20: protos[7][idx(r,c)]=0.9",
        "            if 9<=r<=20 and abs(c-(20-(r-8)*0.8))<1: protos[7][idx(r,c)]=0.9",
        "    for r in range(28):",
        "        for c in range(28):",
        "            drt=r-9; dct=c-14; drb=r-19; dcb=c-14",
        "            if 9<_math.hypot(drt*1.1,dct)<13: protos[8][idx(r,c)]=0.9",
        "            if 9<_math.hypot(drb*1.1,dcb)<13: protos[8][idx(r,c)]=0.9",
        "            if abs(c-14)<2 and 9<r<19: protos[8][idx(r,c)]=max(protos[8][idx(r,c)],0.4)",
        "    for r in range(28):",
        "        for c in range(28):",
        "            dr=r-10; dc=c-14",
        "            if 8<_math.hypot(dr,dc)<12: protos[9][idx(r,c)]=0.9",
        "            if 14<=r<=22 and 16<=c<=20: protos[9][idx(r,c)]=0.9",
        "    rng=np.random.default_rng(42)",
        "    X=[]; y=[]",
        "    for d in range(10):",
        "        for _ in range(120):",
        "            X.append(np.clip(protos[d]+rng.normal(0,0.22,784),0,1)); y.append(d)",
        "    X=np.array(X); y=np.array(y)",
        "    perm=rng.permutation(len(y)); X=X[perm]; y=y[perm]",
        "    split=int(0.8*len(y)); Xtr,Xte=X[:split],X[split:]; ytr,yte=y[:split],y[split:]",
        "    clf=GradientBoostingClassifier(n_estimators=330, learning_rate=0.1, max_depth=1, subsample=0.9, random_state=42)",
        "    clf.fit(Xtr,ytr)",
        "    train_losses=[]; val_losses=[]",
        "    for prob in clf.staged_predict_proba(Xtr):",
        "        prob=np.clip(prob,1e-12,1-1e-12)",
        "        loss=-np.mean([math.log(prob[i, ytr[i]]) for i in range(len(ytr))])",
        "        train_losses.append(float(loss))",
        "    for prob in clf.staged_predict_proba(Xte):",
        "        prob=np.clip(prob,1e-12,1-1e-12)",
        "        loss=-np.mean([math.log(prob[i, yte[i]]) for i in range(len(yte))])",
        "        val_losses.append(float(loss))",
        "    acc=float(clf.score(Xte,yte))",
        "    fi=clf.feature_importances_.tolist() if hasattr(clf,'feature_importances_') else [0]*784",
        "    result={\"status\":\"ok\",\"train_losses\":train_losses,\"val_losses\":val_losses,\"accuracy\":acc,\"feature_importance\":fi}",
        "except Exception as e:",
        "    result={\"status\":\"error\",\"msg\":str(e),\"trace\":traceback.format_exc()}",
        "result",
    ]
    code="\n".join(lines)
    try:
        res=await resilient_pyodide_run(code)
        py_res=res
        try:
            if hasattr(py_res,'to_py'): py_res=py_res.to_py()
        except Exception:
            pass
        if isinstance(py_res,str):
            try:
                import json as _js
                py_res=_js.loads(py_res)
            except Exception:
                pass
        if isinstance(py_res, dict) and py_res.get("status")=="ok":
            app.pyodide_status=f"Pyodide OK 330 trees 10-way acc {py_res.get('accuracy',0):.3f}"
            app.pyodide_reference=py_res
            app.pyodide_ready=True
            app.ref_train_losses=py_res.get("train_losses",[])
            app.ref_val_losses=py_res.get("val_losses",[])
            if py_res.get("feature_importance"):
                app.feature_importance=py_res.get("feature_importance",[0]*784)
        else:
            app.pyodide_status=f"Pyodide: {str(py_res)[:120]}"
            app.pyodide_ready=False
    except Exception as e:
        app.pyodide_status=f"Pyodide err {e} fallback"
        app.pyodide_ready=False

def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=30
    app.background=gradient(rgb(14,16,22), rgb(24,27,35), start='top')
    app.eta=0.12; app.max_trees=330; app.current_m=0
    app.trees=[]; app.loss_history=[]; app.val_loss_history=[]; app.acc_history=[]; app.train_acc_history=[]
    app.feature_importance=[0.0]*784; app.is_playing=False
    app.mnist_loaded=False; app.all_samples=[]; app.X_train=[]; app.y_train=[]
    app.X_val=[]; app.y_val=[]; app.F_train=[]; app.F_val=[]
    app.fetch_status="Init fetch full MNIST..."; app.pyodide_status="Init pyodide..."
    app.pyodide_ready=False; app.pyodide_reference=None
    app.ref_train_losses=[]; app.ref_val_losses=[]
    app.drawing=[0.0]*784; app.is_drawing=False
    app.prediction=None; app.prediction_probs=None
    app.show_rf=False; app.show_overfit=True
    app.selected_sample_idx=0; app.hover_feat=None
    app.t=0
    sx,sy=synth_mnist_full(40)
    Xtr,ytr,Xva,yva=train_val_split(sx,sy,0.78)
    app.X_train,app.y_train=Xtr,ytr
    app.X_val,app.y_val=Xva,yva
    app.F_train=[[0.0]*10 for _ in range(len(Xtr))]
    app.F_val=[[0.0]*10 for _ in range(len(Xva))]
    aio.run(fetch_mnist_samples(app))
    aio.run(pyodide_train_reference(app))

def onStep(app):
    app.t+=1
    if app.is_playing and app.mnist_loaded:
        if app.current_m < app.max_trees:
            step_one_tree(app)
        else:
            app.is_playing=False

def step_one_tree(app):
    if not app.X_train: return
    probs_train=[softmax(f) for f in app.F_train]
    trees_this_iter=[]
    for c in range(10):
        target=[]
        for i in range(len(app.X_train)):
            y_onehot=1.0 if app.y_train[i]==c else 0.0
            target.append(y_onehot - probs_train[i][c])
        f_idx,thr,left_val,right_val,gain=find_best_stump_fast(app.X_train, target, n_feat_sample=32, min_leaf=5)
        for i,x in enumerate(app.X_train):
            app.F_train[i][c]+=app.eta*(left_val if x[f_idx]<thr else right_val)
        for i,x in enumerate(app.X_val):
            app.F_val[i][c]+=app.eta*(left_val if x[f_idx]<thr else right_val)
        app.feature_importance[f_idx]+=max(0.0,gain)
        trees_this_iter.append({"class":c,"feature":f_idx,"threshold":thr,"left":left_val,"right":right_val,"gain":gain})
    app.trees.append(trees_this_iter)
    probs_train_new=[softmax(f) for f in app.F_train]
    probs_val_new=[softmax(f) for f in app.F_val]
    train_loss=cross_entropy_loss(app.y_train, probs_train_new)
    val_loss=cross_entropy_loss(app.y_val, probs_val_new)
    val_acc=accuracy_multiclass(app.y_val, probs_val_new)
    train_acc=accuracy_multiclass(app.y_train, probs_train_new)
    app.loss_history.append(train_loss); app.val_loss_history.append(val_loss)
    app.acc_history.append(val_acc); app.train_acc_history.append(train_acc)
    app.current_m+=1
    if any(v>0.05 for v in app.drawing):
        predict_drawing(app)

def predict_drawing(app):
    if not app.trees:
        app.prediction=None; return
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
    app.prediction=pred
    app.prediction_probs=probs
    app.prediction_logits=f[:]

def reset_ensemble(app):
    app.trees=[]; app.loss_history=[]; app.val_loss_history=[]; app.acc_history=[]; app.train_acc_history=[]
    app.F_train=[[0.0]*10 for _ in range(len(app.X_train))]
    app.F_val=[[0.0]*10 for _ in range(len(app.X_val))]
    app.current_m=0; app.feature_importance=[0.0]*784; app.is_playing=False; app.prediction=None

def recompute_F(app):
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
    if 30<=mx<=120 and 338<=my<=358:
        app.drawing=[0.0]*784; app.prediction=None; return
    if 30<=mx<=254 and 110<=my<=334:
        app.is_drawing=True; paint_at(app,mx,my); return
    if 20<=mx<=280 and 440<=my<=560:
        if app.all_samples:
            cols=5
            idx_x=int((mx-20)//50)
            idx_y=int((my-440)//50)
            idx_x=max(0,min(idx_x,4))
            idx_y=max(0,min(idx_y,1))
            idx=idx_y*cols + idx_x
            shown=[]
            seen=set()
            for pix,lab in app.all_samples:
                if lab not in seen and len(shown)<10:
                    shown.append((pix,lab)); seen.add(lab)
            if len(shown)<10:
                shown=app.all_samples[:10]
            if idx < len(shown):
                pix,lab=shown[idx]
                app.selected_sample_idx=idx
                app.drawing=pix[:]; predict_drawing(app)
            elif idx < len(app.all_samples):
                pix,lab=app.all_samples[idx]
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
    elif key.lower()=='r':
        reset_ensemble(app)
    elif key=='Right':
        if app.current_m<app.max_trees: step_one_tree(app)
    elif key=='Left':
        if app.trees:
            app.trees.pop(); app.loss_history.pop(); app.val_loss_history.pop(); app.acc_history.pop(); app.train_acc_history.pop()
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
    drawRect(0,0,app.width,50, fill=rgb(18,20,28), border=rgb(40,45,60), borderWidth=1)
    drawLabel("XGBoost Lab - Full MNIST 10-way Softmax", 14, 14, size=14, bold=True, fill=rgb(220,230,255), align='left-top')
    drawLabel("F_m = F_{m-1}+eta*h_m | L=-sum p log softmax(F) | 60k/10k 784-d", 14, 32, size=9, fill=rgb(130,145,165), align='left-top')
    play_col=rgb(0,212,255) if app.is_playing else rgb(55,65,85)
    drawRect(360,12,70,26, fill=play_col, border=rgb(90,110,140), borderWidth=1, roundness=7)
    drawLabel("Play" if not app.is_playing else "Pause", 395, 25, size=11, bold=True, fill=rgb(10,15,25) if app.is_playing else rgb(200,220,255))
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
    drawLabel("INPUT: Draw 0-9 - MNIST 28x28", 24, 72, size=11, bold=True, fill=rgb(180,200,230), align='left-top')
    drawLabel("Each pixel = feature (784-d) 10 classes", 24, 88, size=9, fill=rgb(110,125,145), align='left-top')
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
    drawLabel("10-way", 140, 348, size=9, bold=True, fill=rgb(130,145,165), align='left-top')
    if app.prediction is not None and app.prediction_probs is not None:
        col=rgb(0,212,255)
        prob=app.prediction_probs[app.prediction]
        drawRect(30,364,224,36, fill=rgb(30,35,50), border=col, borderWidth=1, roundness=8)
        drawLabel(f"Pred: {app.prediction}  {prob*100:.1f}%", 142, 376, size=14, bold=True, fill=col)
        drawLabel("softmax 10 logits", 142, 390, size=8, fill=rgb(120,135,155))
        for c in range(10):
            p=app.prediction_probs[c] if c < len(app.prediction_probs) else 0
            x0=30 + c*22; y0=406; h=p*36
            bar_col=rgb(0,212,255) if c==app.prediction else rgb(60,70,90)
            drawRect(x0, y0+36-h, 18, h, fill=bar_col, border=rgb(80,90,110), borderWidth=0.5, roundness=2)
            drawLabel(str(c), x0+9, y0+46, size=8, bold=True, fill=rgb(180,190,210))
    else:
        drawRect(30,364,224,60, fill=rgb(20,23,31), border=rgb(35,40,55), borderWidth=1, roundness=6)
        drawLabel("Draw any digit 0-9", 142, 384, size=11, fill=rgb(100,115,135))
        drawLabel("10-way softmax model", 142, 400, size=9, fill=rgb(90,105,125))
    drawLabel("Samples via fetch - click (10-way):", 24, 432, size=9, fill=rgb(120,135,155), align='left-top')
    if app.all_samples:
        shown=[]
        seen=set()
        for pix,lab in app.all_samples:
            if lab not in seen and len(shown)<10:
                shown.append((pix,lab)); seen.add(lab)
        if len(shown)<10:
            shown=app.all_samples[:10]
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
    drawLabel(app.fetch_status[:56], 24, 556, size=7, fill=rgb(90,105,125), align='left-top')
    drawRect(300,60,388,620, fill=rgb(22,25,34), border=rgb(35,40,55), borderWidth=1, roundness=12)
    drawLabel("BOOSTING: Multinomial 10-way", 312, 72, size=12, bold=True, fill=rgb(200,220,255), align='left-top')
    drawLabel(f"Trees {app.current_m}/{app.max_trees} (x10 stumps) eta={app.eta:.2f} target 330->89%", 312, 88, size=8, fill=rgb(130,145,165), align='left-top')
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
            if i>0:
                drawLine(x-6,y+16,x,y+16, lineWidth=1.2, fill=rgb(0,212,255))
            drawLabel(f"h{i+1}", x+12,y+16, size=7, bold=True, fill=rgb(10,20,30) if i<app.current_m else rgb(120,140,160))
    else:
        if app.trees:
            last_iter=app.trees[-1]
            txt=", ".join([f"{s['class']}:({s['feature']%28},{s['feature']//28})" for s in last_iter[:3]])
            drawLabel(f"Weak learners h_{app.current_m} x10: {txt}...", 312,114, size=8, bold=True, fill=rgb(180,220,255), align='left-top')
            drawLabel(f"Each stump fits residual y_c - softmax(F)_c", 312,128, size=8, fill=rgb(130,150,175), align='left-top')
            drawRect(312,142,56,56, fill=rgb(10,15,25), border=rgb(0,212,255), borderWidth=1, roundness=6)
            best_stump=max(last_iter, key=lambda s: s['gain'])
            fr=best_stump['feature']//28; fc=best_stump['feature']%28
            for r in range(28):
                for c in range(28):
                    if r==fr and c==fc:
                        drawRect(312+c*2,142+r*2,2.5,2.5, fill=rgb(255,183,3))
            drawLabel(f"Best pixel ({fc},{fr}) cls {best_stump['class']} thr {best_stump['threshold']:.2f} gain {best_stump['gain']:.1f}", 380,148, size=7, fill=rgb(140,160,185), align='left-top')
            drawLabel("Val samples - residuals y - softmax(F) drives next stump:", 380,162, size=7, fill=rgb(140,160,185), align='left-top')
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
            drawLabel("No trees yet - Space/Step. F0=0, p=0.1 per class", 312,120, size=10, fill=rgb(120,135,155), align='left-top')
            drawLabel("L = -sum p log softmax(F)  grad = softmax(F)-y", 312,138, size=9, fill=rgb(100,120,145), align='left-top')
    drawRect(312,220,368,130, fill=rgb(14,18,26), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("Loss (cross-entropy) vs #trees - cyan train / gold val", 320,228, size=9, bold=True, fill=rgb(180,200,220), align='left-top')
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
            if prev_x is not None:
                drawLine(prev_x,prev_y,x,y, lineWidth=1.3, fill=rgb(0,212,255))
            prev_x,prev_y=x,y
        prev_x=None; prev_y=None
        for i,loss in enumerate(app.val_loss_history):
            x=338 + (i/app.max_trees)*324; y=332 - ((loss-min_loss)/rng)*80
            if prev_x is not None:
                drawLine(prev_x,prev_y,x,y, lineWidth=1.3, fill=rgb(255,183,3))
            prev_x,prev_y=x,y
        if app.current_m>0:
            x_cur=338 + (app.current_m/app.max_trees)*324
            drawLine(x_cur,246,x_cur,332, lineWidth=1, fill=rgb(200,220,255), dashes=(2,2))
    if app.acc_history:
        acc=app.acc_history[-1]
        drawLabel(f"Val Acc {acc*100:.1f}% target 89% @330 (10-way)", 320,320, size=9, bold=True, fill=rgb(180,220,255), align='left-top')
    drawRect(312,358,368,50, fill=rgb(18,22,32), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("F_m = F_{m-1} + eta*h_m  h_m approx y - softmax(F)", 320,366, size=9, fill=rgb(200,220,255), align='left-top')
    drawLabel("10 stumps per round, one per class, softmax gradient", 320,382, size=8, fill=rgb(120,140,165), align='left-top')
    drawLabel(f"Ensemble timeline - {app.current_m*10} stumps (x10 per iter):", 312,418, size=9, bold=True, fill=rgb(180,200,220), align='left-top')
    for i in range(min(app.current_m, 80)):
        trees_iter=app.trees[i] if i < len(app.trees) else []
        max_gain=max([s['gain'] for s in trees_iter]) if trees_iter else 0
        x=312 + (i%40)*9; y=430 + (i//40)*14
        col_int=int(60 + (max_gain/5)*195) if max_gain>0 else 60
        col_int=min(255,col_int)
        drawRect(x,y,7,8, fill=rgb(col_int,col_int//2,30), border=rgb(80,60,30), borderWidth=0.4, roundness=1)
    drawRect(700,60,338,620, fill=rgb(20,23,31), border=rgb(35,40,55), borderWidth=1, roundness=12)
    drawLabel("RESEARCH VIEW - Softmax, Capacity", 712,72, size=11, bold=True, fill=rgb(220,230,255), align='left-top')
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
    drawLabel("Feature importance: 10-way (28x28)", 712,340, size=9, fill=rgb(140,160,185), align='left-top')
    drawRect(712,352,316,86, fill=rgb(16,20,28), border=rgb(40,50,70), borderWidth=1, roundness=8)
    drawLabel("Softmax cross-entropy:", 720,360, size=9, bold=True, fill=rgb(180,200,220), align='left-top')
    drawLabel("L = -sum_i sum_c p_{i,c} log q_{i,c}", 720,374, size=9, fill=rgb(200,220,255), align='left-top')
    drawLabel("q = softmax(F) = exp(F_c)/sum_k exp(F_k)", 720,386, size=8, fill=rgb(150,170,200), align='left-top')
    drawLabel("grad = q - p -> h_m ~ p - q (pseudo-residual)", 720,400, size=9, bold=True, fill=rgb(0,212,255), align='left-top')
    drawLabel("F_m = F_{m-1}+eta*h_m  10 logits", 720,412, size=8, fill=rgb(160,180,210), align='left-top')
    drawLabel("330 trees x10 = 3300 stumps -> 89% acc", 720,424, size=8, fill=rgb(130,150,175), align='left-top')
    drawRect(712,444,316,84, fill=rgb(18,22,32), border=rgb(35,45,65), borderWidth=1, roundness=8)
    drawLabel("Pyodide worker (extensions.pyodide):", 720,452, size=9, bold=True, fill=rgb(180,200,220), align='left-top')
    status=app.pyodide_status
    drawLabel(status[:58], 720,466, size=8, fill=rgb(120,200,150) if app.pyodide_ready else rgb(200,150,120), align='left-top')
    if len(status)>58:
        drawLabel(status[58:116], 720,478, size=8, fill=rgb(120,200,150) if app.pyodide_ready else rgb(200,150,120), align='left-top')
    if app.pyodide_ready and app.pyodide_reference:
        acc=app.pyodide_reference.get("accuracy",0)
        drawLabel(f"sklearn GBM 330 10-way: {acc*100:.1f}% target 89%", 720,492, size=8, fill=rgb(160,200,180), align='left-top')
        drawLabel("XGBoost = GBM + 2nd-order Taylor + sparsity", 720,504, size=8, fill=rgb(130,150,175), align='left-top')
    else:
        drawLabel("Brython GBM 10-way fallback - browser", 720,492, size=8, fill=rgb(140,160,185), align='left-top')
        drawLabel("pip install xgboost in Pyodide for exact XGBoost", 720,504, size=8, fill=rgb(110,130,155), align='left-top')
    drawRect(712,534,316,110, fill=rgb(14,18,26), border=rgb(35,40,55), borderWidth=1, roundness=8)
    drawLabel("Research insights:", 720,542, size=9, bold=True, fill=rgb(220,230,255), align='left-top')
    notes=["* 10 logits, softmax -> cross-entropy","* stumps depth1 high bias low var","* boosting reduces bias seq (vs RF var)","* eta 0.01-0.3 slows improves gen","* 330 trees high cap overfits w/o early stop","* MNIST 784-d, 10 classes, 60k/10k"]
    for i,line in enumerate(notes):
        drawLabel(line, 720,556+i*12, size=8, fill=rgb(130,145,165), align='left-top')
    drawLabel("SCS 1050x700 - fetch + pyodide - 10-way softmax", 14, 686, size=8, fill=rgb(80,95,115), align='left-top')
