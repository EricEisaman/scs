from scs import *
from browser import aio, window, document
from extensions.file_loader import load_image, FileLoaderError
import math, random, traceback

WIDTH=1050
HEIGHT=700
LABELS={0:"T-shirt/top",1:"Trouser",2:"Pullover",3:"Dress",4:"Coat",5:"Sandal",6:"Shirt",7:"Sneaker",8:"Bag",9:"Ankle boot"}
SHORT={0:"T-shirt",1:"Trouser",2:"Pullover",3:"Dress",4:"Coat",5:"Sandal",6:"Shirt",7:"Sneaker",8:"Bag",9:"Boot"}
PANEL=rgb(28,31,48); PANEL2=rgb(22,26,42); BORDER=rgb(58,64,94)
ACC=rgb(99,102,241); ACC_H=rgb(129,133,255); ACC2=rgb(16,185,129)
TXT=rgb(236,240,255); DIM=rgb(150,160,188); GRID=rgb(44,50,76)

SOURCES={
    "train_images":[
        "https://raw.githubusercontent.com/zalandoresearch/fashion-mnist/master/data/fashion/train-images-idx3-ubyte.gz",
        "https://fashion-mnist.s3-website.eu-central-1.amazonaws.com/train-images-idx3-ubyte.gz",
    ],
    "train_labels":[
        "https://raw.githubusercontent.com/zalandoresearch/fashion-mnist/master/data/fashion/train-labels-idx1-ubyte.gz",
        "https://fashion-mnist.s3-website.eu-central-1.amazonaws.com/train-labels-idx1-ubyte.gz",
    ],
    "test_images":[
        "https://raw.githubusercontent.com/zalandoresearch/fashion-mnist/master/data/fashion/t10k-images-idx3-ubyte.gz",
        "https://fashion-mnist.s3-website.eu-central-1.amazonaws.com/t10k-images-idx3-ubyte.gz",
    ],
    "test_labels":[
        "https://raw.githubusercontent.com/zalandoresearch/fashion-mnist/master/data/fashion/t10k-labels-idx1-ubyte.gz",
        "https://fashion-mnist.s3-website.eu-central-1.amazonaws.com/t10k-labels-idx1-ubyte.gz",
    ]
}

async def fetch_bytes_popular(urls, label):
    last_err=None
    for url in urls:
        try:
            resp=await window.fetch(url)
            if not resp.ok:
                raise Exception(f"HTTP {resp.status} {url}")
            buf=None
            if url.endswith(".gz"):
                try:
                    DS = getattr(window, "DecompressionStream")
                    ds = DS.new("gzip")
                    stream = resp.body.pipeThrough(ds)
                    new_resp = window.Response.new(stream)
                    buf = await new_resp.arrayBuffer()
                except Exception as e:
                    buf = await resp.arrayBuffer()
            else:
                buf = await resp.arrayBuffer()
            u8 = window.Uint8Array.new(buf)
            # FAST: Use to_py() then getattr for Array.from to avoid keyword 'from' SyntaxError
            lst=None
            try:
                py_data = u8.to_py()
                if isinstance(py_data, (bytes, bytearray)):
                    lst = list(py_data)
                else:
                    # py_data is likely memoryview or list
                    lst = list(py_data)
            except:
                try:
                    # JS fast path: Array.from via getattr (avoids .from keyword)
                    from_fn = getattr(window.Array, "from")
                    js_arr = from_fn(u8)
                    if hasattr(js_arr, "to_py"):
                        js_arr = js_arr.to_py()
                    lst = list(js_arr)
                except:
                    # Slow fallback chunked
                    n = int(getattr(u8, "length", 0))
                    lst=[]
                    step=200000
                    for s in range(0,n,step):
                        e=min(s+step,n)
                        for i in range(s,e):
                            try: lst.append(int(u8[i]))
                            except: lst.append(0)
                        await aio.sleep(0)
            if lst is None or len(lst)<16:
                raise Exception(f"Too short")
            return lst
        except Exception as e:
            last_err=e
            continue
    raise Exception(f"All sources failed for {label}: {str(last_err)[:200]}")

def parse_idx_images(bl, max_images=6000):
    if len(bl)<16: raise Exception(f"short {len(bl)}")
    magic=(bl[0]<<24)|(bl[1]<<16)|(bl[2]<<8)|bl[3]
    if magic!=2051: raise Exception(f"magic {magic} !=2051")
    X=[]; off=16
    num=(bl[4]<<24)|(bl[5]<<16)|(bl[6]<<8)|bl[7]
    limit=min(num,max_images)
    for i in range(limit):
        base=off+i*784
        if base+784>len(bl): break
        vec=[bl[base+j]/255.0 for j in range(784)]
        X.append(vec)
    return X

def parse_idx_labels(bl, max_labels=6000):
    if len(bl)<8: raise Exception("short")
    magic=(bl[0]<<24)|(bl[1]<<16)|(bl[2]<<8)|bl[3]
    if magic!=2049: raise Exception(f"magic {magic} !=2049")
    num=(bl[4]<<24)|(bl[5]<<16)|(bl[6]<<8)|bl[7]
    limit=min(num,max_labels)
    y=[]
    for i in range(limit):
        if 8+i>=len(bl): break
        y.append(int(bl[8+i]))
    return y

def softmax(logits):
    m=max(logits)
    exps=[math.exp(l-m) for l in logits]
    s=sum(exps)+1e-12
    return [e/s for e in exps]

def forward(x,W1,b1,W2,b2):
    hidden=len(b1)
    z1=[0.0]*hidden
    for h in range(hidden):
        s=b1[h]
        for i in range(784):
            s+=x[i]*W1[i][h]
        z1[h]=s
    a1=[v if v>0 else 0.0 for v in z1]
    z2=[0.0]*10
    for o in range(10):
        s=b2[o]
        for h in range(hidden):
            s+=a1[h]*W2[h][o]
        z2[o]=s
    return z1,a1,z2,softmax(z2)

def init_weights(hidden=128):
    scale1=math.sqrt(2.0/784)
    scale2=math.sqrt(2.0/hidden)
    W1=[[random.gauss(0,scale1) for _ in range(hidden)] for _ in range(784)]
    b1=[0.0]*hidden
    W2=[[random.gauss(0,scale2) for _ in range(10)] for _ in range(hidden)]
    b2=[0.0]*10
    return W1,b1,W2,b2

def train_val_split(X,y,ratio=0.82):
    buckets=[[] for _ in range(10)]
    for xi,yi in zip(X,y):
        try:
            c=int(yi)
            if 0<=c<=9:
                buckets[c].append((xi,c))
        except:
            continue
    Xtr=[]; ytr=[]; Xva=[]; yva=[]
    for c in range(10):
        lst=buckets[c]
        if not lst:
            continue
        random.shuffle(lst)
        n=len(lst)
        n_tr=int(n*ratio)
        if n_tr<1:
            n_tr=1
        if n_tr>=n:
            n_tr=n-1 if n>1 else 1
        for k in range(n_tr):
            xi,yi=lst[k]
            Xtr.append(xi); ytr.append(yi)
        for k in range(n_tr,n):
            xi,yi=lst[k]
            Xva.append(xi); yva.append(yi)
    if Xtr:
        idx=list(range(len(Xtr)))
        random.shuffle(idx)
        Xtr=[Xtr[i] for i in idx]
        ytr=[ytr[i] for i in idx]
    if Xva:
        idx=list(range(len(Xva)))
        random.shuffle(idx)
        Xva=[Xva[i] for i in idx]
        yva=[yva[i] for i in idx]
    return Xtr,ytr,Xva,yva

def onAppStart(app):
    app.width=WIDTH; app.height=HEIGHT; app.stepsPerSecond=20
    app.background=gradient(rgb(10,12,20), rgb(26,30,50), start="top")
    app.dataset_loaded=False
    app.X_train=[]; app.y_train=[]; app.X_val=[]; app.y_val=[]; app.X_all=[]; app.y_all=[]
    app.samples={}; app.sample_urls=[None]*10
    app.W1=None; app.b1=None; app.W2=None; app.b2=None
    app.epoch=0; app.max_epochs=12; app.lr=0.08; app.batch=64; app.hidden=128
    app.loss_hist=[]; app.acc_hist=[]; app.val_loss_hist=[]; app.val_acc_hist=[]
    app.training=False; app.trained=False; app.progress=0.0
    app.orig_url=None; app.proc_url=None; app.proc_vec=None; app.pred=None; app.probs=None
    app.fetch_status="Ready - Click Load (4 fetches .gz - FAST)"
    app.status="TOP TIER FIXED - Array.from keyword bug + overlap + slow loop"
    app.buttons={
        "load":{"x":30,"y":610,"w":160,"h":38,"label":"Load Fashion-MNIST","enabled":True},
        "train":{"x":205,"y":610,"w":130,"h":38,"label":"Train MLP","enabled":False},
        "reset":{"x":350,"y":610,"w":80,"h":38,"label":"Reset","enabled":True},  # BOTTOM OPEN SPACE - was 600
        "clear":{"x":670,"y":340,"w":80,"h":28,"label":"Clear","enabled":True},
    }
    app.hover=None; app.upload_hover=False

# === TOP-TIER WEIGHT CACHING ===
CACHE_KEY="fashion_mnist_mlp_top_tier_weights_v1"

def try_load_cached_weights(app):
    try:
        raw = window.localStorage.getItem(CACHE_KEY)
        if raw is None:
            return False
        import json
        data = window.JSON.parse(raw)
        if hasattr(data, "to_py"):
            data = data.to_py()
        # data is dict with W1,b1,W2,b2,hidden,epoch,acc
        if not isinstance(data, dict):
            return False
        # Validate shapes
        W1 = data.get("W1")
        b1 = data.get("b1")
        W2 = data.get("W2")
        b2 = data.get("b2")
        hidden = data.get("hidden", 128)
        if hasattr(W1, "to_py"): W1 = W1.to_py()
        if hasattr(b1, "to_py"): b1 = b1.to_py()
        if hasattr(W2, "to_py"): W2 = W2.to_py()
        if hasattr(b2, "to_py"): b2 = b2.to_py()
        if W1 is None or b1 is None or W2 is None or b2 is None:
            return False
        # Convert to Python lists if needed
        app.W1 = W1
        app.b1 = b1
        app.W2 = W2
        app.b2 = b2
        app.hidden = int(hidden)
        app.trained = True
        app.epoch = int(data.get("epoch", 0))
        app.status = f"Loaded cached weights {app.hidden} hidden - ready for inference"
        if "cache" in app.buttons:
            app.buttons["cache"]["enabled"]=True  # enable if cache loaded
        app.fetch_status = f"Cache hit - {len(W1)}x{len(b1)} -> {len(W2[0])} - no training needed"
        app.buttons["train"]["enabled"] = True
        # Restore histories if available
        try:
            app.loss_hist = list(data.get("loss_hist", []))
            app.val_acc_hist = list(data.get("val_acc_hist", []))
        except:
            pass
        return True
    except Exception as e:
        print(f"Cache load failed: {e}")
        return False

def cache_weights_now(app):
    try:
        if app.W1 is None:
            app.status = "No weights to cache - train first"
            return False
        import json
        # Store compact - convert to list if needed
        payload = {
            "W1": app.W1,
            "b1": app.b1,
            "W2": app.W2,
            "b2": app.b2,
            "hidden": app.hidden,
            "epoch": app.epoch,
            "loss_hist": app.loss_hist[-20:] if len(app.loss_hist)>20 else app.loss_hist,
            "val_acc_hist": app.val_acc_hist[-20:] if len(app.val_acc_hist)>20 else app.val_acc_hist,
        }
        jstr = window.JSON.stringify(payload)
        window.localStorage.setItem(CACHE_KEY, jstr)
        app.status = f"Weights cached {len(jstr)//1024}KB to localStorage - will load by default next time"
        app.fetch_status = f"Cached hidden {app.hidden} epoch {app.epoch}"
        return True
    except Exception as e:
        app.status = f"Cache failed {str(e)[:80]}"
        print(f"Cache failed: {e}")
        return False

def clear_cached_weights(app):
    try:
        window.localStorage.removeItem(CACHE_KEY)
        app.W1=None; app.b1=None; app.W2=None; app.b2=None
        app.trained=False; app.loss_hist=[]; app.acc_hist=[]; app.val_loss_hist=[]; app.val_acc_hist=[]; app.epoch=0; app.lr=0.08
        app.pred=None; app.probs=None; app.orig_url=None; app.proc_url=None; app.proc_vec=None
        app.dataset_loaded=False; app.X_train=[]; app.y_train=[]; app.sample_urls=[None]*10
        app.status="Cache cleared - Reset"; app.fetch_status="Ready"; app.buttons["load"]["enabled"]=True; app.buttons["train"]["enabled"]=False
        return True
    except Exception as e:
        print(f"Clear cache failed {e}")
        return False

async def build_preview_urls(app):
    app.sample_urls=[None]*10
    for lbl in range(10):
        vec=app.samples.get(lbl)
        if vec is None:
            continue
        canvas=document.createElement("canvas")
        canvas.width=84; canvas.height=84
        ctx=canvas.getContext("2d")
        for r in range(28):
            for c in range(28):
                fv=float(vec[r*28+c])
                if fv>1.0:
                    fv/=255.0
                fv=max(0.0,min(1.0,fv))
                gray=int(fv*255)
                ctx.fillStyle=f"rgb({gray},{gray},{gray})"
                ctx.fillRect(c*3,r*3,3,3)
        app.sample_urls[lbl]=canvas.toDataURL("image/png")

async def load_fashion(app):
    if app.dataset_loaded:
        return
    app.buttons["load"]["enabled"]=False
    app.status="Fetching 4 IDX .gz - WATCH NETWORK TAB - FAST"
    try:
        app.fetch_status="Fetching train-images .gz..."
        img_bytes=await fetch_bytes_popular(SOURCES["train_images"], "train-images")
        X_train_all=parse_idx_images(img_bytes, 6000)
        await aio.sleep(0)
        app.fetch_status="Fetching train-labels .gz..."
        lbl_bytes=await fetch_bytes_popular(SOURCES["train_labels"], "train-labels")
        y_train_all=parse_idx_labels(lbl_bytes, 6000)
        await aio.sleep(0)
        app.fetch_status="Fetching t10k-images .gz..."
        t_img_bytes=await fetch_bytes_popular(SOURCES["test_images"], "test-images")
        X_test=parse_idx_images(t_img_bytes, 1000)
        await aio.sleep(0)
        app.fetch_status="Fetching t10k-labels .gz..."
        t_lbl_bytes=await fetch_bytes_popular(SOURCES["test_labels"], "test-labels")
        y_test=parse_idx_labels(t_lbl_bytes, 1000)
        X_all=X_train_all[:5000]+X_test[:1000]
        y_all=y_train_all[:5000]+y_test[:1000]
        samples={}
        for xi,yi in zip(X_test, y_test):
            c=int(yi)
            if c not in samples:
                samples[c]=xi
            if len(samples)==10:
                break
        Xtr,ytr,Xva,yva=train_val_split(X_all, y_all, 0.82)
        app.X_all=X_all; app.y_all=y_all
        app.X_train=Xtr; app.y_train=ytr; app.X_val=Xva; app.y_val=yva
        app.samples=samples
        await build_preview_urls(app)
        app.dataset_loaded=True
        app.fetch_status=f"Loaded {len(X_all)} | Train {len(Xtr)} Val {len(Xva)} - 4 FETCHES DONE"
        app.status=f"Fashion-MNIST loaded {len(X_all)} - TOP TIER"
        app.buttons["train"]["enabled"]=True
        app.buttons["load"]["enabled"]=False
    except Exception as e:
        import traceback
        tb=traceback.format_exc()
        app.fetch_status=f"Load failed {str(e)[:200]}"
        app.status=f"Failed {str(e)[:120]}"
        app.buttons["load"]["enabled"]=True
        print(tb)

async def train_mlp(app):
    if not app.dataset_loaded or app.training:
        return
    app.training=True; app.trained=False
    app.loss_hist=[]; app.acc_hist=[]; app.val_loss_hist=[]; app.val_acc_hist=[]
    app.live_train=[]; app.live_val=[]
    app.epoch=0; app.buttons["train"]["enabled"]=False
    # Disable cache button during training
    if "cache" in app.buttons:
        app.buttons["cache"]["enabled"]=False
    Xtr=app.X_train; ytr=app.y_train; Xva=app.X_val; yva=app.y_val
    app.batch=16
    app.max_epochs=8
    W1,b1,W2,b2=init_weights(app.hidden)
    app.W1=W1; app.b1=b1; app.W2=W2; app.b2=b2
    app.status=f"Training FULL {len(Xtr)} samples - smooth pipeline batch {app.batch} + live loss"
    for ep in range(app.max_epochs):
        app.epoch=ep+1
        app.status=f"Training epoch {app.epoch}/{app.max_epochs}..."
        idx=list(range(len(Xtr)))
        random.shuffle(idx)
        total_loss=0.0; correct=0; batches=0
        total_batches=(len(Xtr)+app.batch-1)//app.batch
        for start in range(0,len(idx),app.batch):
            batch_idx=idx[start:start+app.batch]
            if not batch_idx:
                continue
            dW1=[[0.0]*app.hidden for _ in range(784)]
            db1=[0.0]*app.hidden
            dW2=[[0.0]*10 for _ in range(app.hidden)]
            db2=[0.0]*10
            batch_loss=0.0; batch_correct=0
            for idx_b, bi in enumerate(batch_idx):
                x=Xtr[bi]; yi=int(ytr[bi])
                z1,a1,z2,probs=forward(x,W1,b1,W2,b2)
                eps=1e-12
                p=probs[yi] if yi < len(probs) else eps
                p=min(max(p,eps),1-eps)
                batch_loss+=-math.log(p)
                pred=max(range(len(probs)), key=lambda k: probs[k])
                if pred==yi:
                    batch_correct+=1
                dz2=probs[:]
                dz2[yi]-=1
                for o in range(10):
                    db2[o]+=dz2[o]/len(batch_idx)
                    for h in range(app.hidden):
                        dW2[h][o]+=a1[h]*dz2[o]/len(batch_idx)
                da1=[0.0]*app.hidden
                for h in range(app.hidden):
                    s=0.0
                    for o in range(10):
                        s+=dz2[o]*W2[h][o]
                    da1[h]=s
                dz1=[da1[h]*(1 if z1[h]>0 else 0) for h in range(app.hidden)]
                for h in range(app.hidden):
                    db1[h]+=dz1[h]/len(batch_idx)
                    for i in range(784):
                        dW1[i][h]+=x[i]*dz1[h]/len(batch_idx)
                if idx_b%2==0:
                    await aio.sleep(0)
            for i in range(784):
                for h in range(app.hidden):
                    W1[i][h]-=app.lr*dW1[i][h]
            for h in range(app.hidden):
                b1[h]-=app.lr*db1[h]
                for o in range(10):
                    W2[h][o]-=app.lr*dW2[h][o]
            for o in range(10):
                b2[o]-=app.lr*db2[o]
            total_loss+=batch_loss/len(batch_idx) if batch_idx else 0
            correct+=batch_correct; batches+=1
            app.progress=(app.epoch-1 + batches/total_batches)/app.max_epochs
            # FIXED: Live loss curve every 10 batches, safe val access
            if batches%10==0 or batches==1 or batches==total_batches:
                live_avg=total_loss/batches if batches else 0
                live_acc=correct/(batches*app.batch) if batches else 0
                app.live_train.append(live_avg)
                app.loss_hist.append(live_avg)
                app.acc_hist.append(live_acc)
                # FIXED: Always ensure val_loss_hist has at least one entry before reading [-1]
                if batches%30==0 or batches==total_batches:
                    v_loss=0.0; v_corr=0; v_n=min(200,len(Xva))
                    if v_n>0:
                        for vi in range(v_n):
                            xi=Xva[vi]; yi=int(yva[vi])
                            _,_,_,probs=forward(xi,W1,b1,W2,b2)
                            p=probs[yi] if yi < len(probs) else 1e-12
                            p=min(max(p,1e-12),1-1e-12)
                            v_loss+=-math.log(p)
                            if max(range(len(probs)), key=lambda k: probs[k])==yi:
                                v_corr+=1
                            if vi%40==0:
                                await aio.sleep(0)
                        v_loss/=v_n
                        v_acc=v_corr/v_n if v_n else 0
                    else:
                        v_loss=live_avg
                        v_acc=live_acc
                    app.live_val.append(v_loss)
                    app.val_loss_hist.append(v_loss)
                    app.val_acc_hist.append(v_acc)
                else:
                    if app.val_loss_hist:
                        app.val_loss_hist.append(app.val_loss_hist[-1])
                        app.val_acc_hist.append(app.val_acc_hist[-1])
                    else:
                        # First batches - initialize val with live train to avoid IndexError
                        app.val_loss_hist.append(live_avg)
                        app.val_acc_hist.append(live_acc)
                # SAFE status - val_loss_hist guaranteed non-empty now
                app.status=f"Epoch {app.epoch}/{app.max_epochs} batch {batches}/{total_batches} loss {live_avg:.3f} val {app.val_loss_hist[-1]:.3f}"
            await aio.sleep(0.01)
            if batches%15==0:
                await aio.sleep(0)
        avg_loss=total_loss/batches if batches else 0
        acc=correct/len(Xtr) if Xtr else 0
        val_loss=0.0; val_correct=0
        for vi,(xi,yi) in enumerate(zip(Xva,yva)):
            _,_,_,probs=forward(xi,W1,b1,W2,b2)
            yi_int=int(yi)
            p=probs[yi_int] if yi_int < len(probs) else 1e-12
            p=min(max(p,1e-12),1-1e-12)
            val_loss+=-math.log(p)
            pred=max(range(len(probs)), key=lambda k: probs[k])
            if pred==yi_int:
                val_correct+=1
            if vi%50==0:
                await aio.sleep(0)
        val_loss/=len(Xva) if Xva else 1
        val_acc=val_correct/len(Xva) if Xva else 0
        if app.loss_hist:
            app.loss_hist[-1]=avg_loss
            app.acc_hist[-1]=acc
        else:
            app.loss_hist.append(avg_loss); app.acc_hist.append(acc)
        if app.val_loss_hist:
            app.val_loss_hist[-1]=val_loss
            app.val_acc_hist[-1]=val_acc
        else:
            app.val_loss_hist.append(val_loss); app.val_acc_hist.append(val_acc)
        app.W1=W1; app.b1=b1; app.W2=W2; app.b2=b2
        app.progress=(ep+1)/app.max_epochs
        app.status=f"Epoch {app.epoch}/{app.max_epochs} loss {avg_loss:.3f} acc {acc*100:.1f}% val {val_acc*100:.1f}%"
        await aio.sleep(0.05)
        app.lr*=0.95
    app.training=False; app.trained=True; app.buttons["train"]["enabled"]=True
    if "cache" in app.buttons:
        app.buttons["cache"]["enabled"]=True
    app.status=f"Done acc {app.acc_hist[-1]*100:.1f}% val {app.val_acc_hist[-1]*100:.1f}%"
    cache_weights_now(app)

# === TOP-TIER IMAGE CROPPING & RESIZING ===
async def process_upload_to_28x28(source):
    result=await load_image(source, max_dimension=384)
    if hasattr(result,"to_py"):
        try: result=result.to_py()
        except: pass
    if not isinstance(result, dict):
        raise ValueError(f"load_image returned {type(result)}")
    width=result.get("width"); height=result.get("height"); pixels=result.get("pixels"); previewUrl=result.get("previewUrl") or result.get("preview_url")
    if width is None or height is None or pixels is None:
        raise ValueError("missing fields")
    if hasattr(pixels,"to_py"):
        try: pixels=pixels.to_py()
        except: pass
    src_canvas=document.createElement("canvas")
    src_canvas.width=int(width); src_canvas.height=int(height)
    ctx=src_canvas.getContext("2d")
    try:
        img_data=ctx.createImageData(int(width), int(height))
        data=img_data.data
        for i in range(min(len(pixels), len(data))):
            try: data[i]=int(pixels[i])
            except: pass
        ctx.putImageData(img_data,0,0)
    except Exception as e:
        img=window.Image.new()
        img.crossOrigin="anonymous"
        def exec_res(resolve,reject):
            img.onload=lambda ev: resolve(True)
            img.onerror=lambda ev: reject(e)
        img.src=previewUrl
        try:
            await window.Promise.new(exec_res)
            ctx.drawImage(img,0,0,int(width),int(height))
        except: pass
    try:
        full_data=ctx.getImageData(0,0,int(width),int(height))
        fd=full_data.data
        if hasattr(fd,"to_py"):
            fd=fd.to_py()
        min_x=int(width); max_x=0; min_y=int(height); max_y=0
        step_x=max(1,int(width)//200)
        step_y=max(1,int(height)//200)
        for y in range(0,int(height),step_y):
            for x in range(0,int(width),step_x):
                idx=(y*int(width)+x)*4
                if idx+2>=len(fd): continue
                try: r=int(fd[idx]); g=int(fd[idx+1]); b=int(fd[idx+2])
                except: continue
                brightness=(r+g+b)/3
                if brightness<220:
                    if x<min_x: min_x=x
                    if x>max_x: max_x=x
                    if y<min_y: min_y=y
                    if y>max_y: max_y=y
        if max_x<=min_x or max_y<=min_y:
            size=min(int(width),int(height))
            sx=(int(width)-size)//2
            sy=(int(height)-size)//2
            bbox_w=size; bbox_h=size
        else:
            pad_x=int((max_x-min_x)*0.15)
            pad_y=int((max_y-min_y)*0.15)
            min_x=max(0,min_x-pad_x); max_x=min(int(width)-1,max_x+pad_x)
            min_y=max(0,min_y-pad_y); max_y=min(int(height)-1,max_y+pad_y)
            bbox_w=max_x-min_x+1
            bbox_h=max_y-min_y+1
            sx=min_x; sy=min_y
            size=max(bbox_w,bbox_h)
            if bbox_w<bbox_h:
                sx=min_x - (size-bbox_w)//2
                sx=max(0,min(sx,int(width)-size))
            else:
                sy=min_y - (size-bbox_h)//2
                sy=max(0,min(sy,int(height)-size))
    except Exception as e:
        orig_w=int(width); orig_h=int(height); size=min(orig_w,orig_h)
        sx=(orig_w-size)//2; sy=(orig_h-size)//2
        bbox_w=size; bbox_h=size
    dst_canvas=document.createElement("canvas")
    dst_canvas.width=28; dst_canvas.height=28
    dctx=dst_canvas.getContext("2d")
    dctx.imageSmoothingEnabled=True
    dctx.imageSmoothingQuality="high"
    try:
        if size>112:
            tmp1=document.createElement("canvas")
            tmp1.width=112; tmp1.height=112
            t1ctx=tmp1.getContext("2d")
            t1ctx.imageSmoothingEnabled=True
            t1ctx.imageSmoothingQuality="high"
            t1ctx.drawImage(src_canvas, sx, sy, size, size, 0, 0, 112, 112)
            tmp2=document.createElement("canvas")
            tmp2.width=56; tmp2.height=56
            t2ctx=tmp2.getContext("2d")
            t2ctx.imageSmoothingEnabled=True
            t2ctx.imageSmoothingQuality="high"
            t2ctx.drawImage(tmp1, 0, 0, 112, 112, 0, 0, 56, 56)
            dctx.drawImage(tmp2, 0, 0, 56, 56, 0, 0, 28, 28)
        elif size>56:
            tmp=document.createElement("canvas")
            tmp.width=56; tmp.height=56
            tctx=tmp.getContext("2d")
            tctx.imageSmoothingEnabled=True
            tctx.imageSmoothingQuality="high"
            tctx.drawImage(src_canvas, sx, sy, size, size, 0, 0, 56, 56)
            dctx.drawImage(tmp, 0, 0, 56, 56, 0, 0, 28, 28)
        else:
            dctx.drawImage(src_canvas, sx, sy, size, size, 0, 0, 28, 28)
    except:
        dctx.drawImage(src_canvas, sx, sy, size, size, 0, 0, 28, 28)
    dst_data=dctx.getImageData(0,0,28,28); dst_pixels=dst_data.data
    if hasattr(dst_pixels,"to_py"):
        try: dst_pixels=dst_pixels.to_py()
        except: pass
    vec=[]
    for i in range(0, len(dst_pixels), 4):
        try: r=int(dst_pixels[i]); g=int(dst_pixels[i+1]); b=int(dst_pixels[i+2])
        except: r=g=b=0
        gray=(0.299*r+0.587*g+0.114*b)/255.0
        vec.append(gray)
    if len(vec)==784:
        avg=sum(vec)/len(vec)
        if avg>0.5:
            vec=[1.0-v for v in vec]
        mn=min(vec); mx=max(vec)
        if mx-mn>0.1:
            vec=[(v-mn)/(mx-mn) for v in vec]
        vec=[max(0.0,min(1.0,v)) for v in vec]
    big_canvas=document.createElement("canvas")
    big_canvas.width=140; big_canvas.height=140
    bctx=big_canvas.getContext("2d")
    bctx.imageSmoothingEnabled=False
    bctx.drawImage(dst_canvas,0,0,140,140)
    bctx.strokeStyle="rgba(99,102,241,0.3)"
    bctx.lineWidth=1
    bctx.strokeRect(0,0,140,140)
    proc_url=big_canvas.toDataURL("image/png")
    grid_canvas=document.createElement("canvas")
    grid_canvas.width=28; grid_canvas.height=28
    gctx=grid_canvas.getContext("2d")
    for r in range(28):
        for c in range(28):
            v=vec[r*28+c]
            gray=int(v*255)
            gctx.fillStyle=f"rgb({gray},{gray},{gray})"
            gctx.fillRect(c,r,1,1)
    grid_url=grid_canvas.toDataURL("image/png")
    return {"original_url":previewUrl,"processed_url":proc_url,"grid_url":grid_url,"vector":vec,"crop_info":{"sx":sx,"sy":sy,"size":size,"bbox_w":bbox_w,"bbox_h":bbox_h}}

async def handle_upload(app, source):
    app.status="Loading via load_image() - TOP-TIER crop..."
    try:
        result=await process_upload_to_28x28(source)
        vec=result.get("vector")
        vec_f=[max(0.0,min(1.0,float(v))) for v in vec]
        app.orig_url=result.get("original_url"); app.proc_url=result.get("processed_url"); app.grid_url=result.get("grid_url"); app.proc_vec=vec_f
        app.crop_info=result.get("crop_info",{})
        if app.W1 is None:
            if try_load_cached_weights(app):
                app.status="Upload processed + cached weights loaded - inferring"
            else:
                app.status="Upload 28x28 processed - train first or load cached"; return
        _,_,_,probs=forward(vec_f, app.W1, app.b1, app.W2, app.b2)
        pred=max(range(len(probs)), key=lambda k: probs[k])
        app.probs=probs; app.pred=int(pred)
        app.status=f"Inferred {LABELS.get(int(pred),str(pred))} {probs[int(pred)]*100:.1f}% - TOP-TIER crop"
    except Exception as e:
        import traceback
        tb=traceback.format_exc()
        app.status=f"Upload failed {str(e)[:100]}"
        print(tb)

def onMousePress(app, mx, my):
    for bid,b in app.buttons.items():
        if b["x"]<=mx<=b["x"]+b["w"] and b["y"]<=my<=b["y"]+b["h"] and b["enabled"]:
            if bid=="load":
                aio.run(load_fashion(app))
            elif bid=="train":
                aio.run(train_mlp(app))
            elif bid=="reset":
                clear_cached_weights(app)
            elif bid=="cache":
                cache_weights_now(app)
            elif bid=="clear":
                app.orig_url=None; app.proc_url=None; app.proc_vec=None; app.pred=None; app.probs=None; app.status="Cleared"
            return
    if 670<=mx<=1000 and 120<=my<=320:
        aio.run(trigger_picker(app))

async def trigger_picker(app):
    inp=document.createElement("input")
    inp.type="file"; inp.accept="image/*"; inp.style.display="none"
    document.body.appendChild(inp)
    fut=aio.Future()
    def on_change(evt):
        f=evt.target.files[0] if evt.target.files.length>0 else None
        fut.set_result(f)
        try: document.body.removeChild(inp)
        except: pass
    inp.bind("change", on_change)
    inp.click()
    file_obj=await fut
    if file_obj:
        await handle_upload(app, file_obj)

def onMouseMove(app, mx, my):
    app.hover=None
    for bid,b in app.buttons.items():
        if b["x"]<=mx<=b["x"]+b["w"] and b["y"]<=my<=b["y"]+b["h"]:
            app.hover=bid
    app.upload_hover=(670<=mx<=1000 and 120<=my<=320)

def onKeyPress(app, key):
    if key.lower()=="l" and app.buttons["load"]["enabled"]:
        aio.run(load_fashion(app))
    if key.lower()=="t" and app.buttons["train"]["enabled"]:
        aio.run(train_mlp(app))

def draw_panel(x,y,w,h,title):
    drawRect(x,y,w,h,fill=PANEL,border=BORDER,borderWidth=1,roundness=14,opacity=98)
    drawRect(x,y,w,34,fill=rgb(38,42,66),roundness=14)
    drawRect(x,y+17,w,17,fill=rgb(38,42,66))
    if title:
        drawLabel(title,x+16,y+17,size=13,fill=TXT,bold=True,align="left-center")

def draw_button(b,hover,enabled):
    x,y,w,h=b["x"],b["y"],b["w"],b["h"]
    if not enabled:
        fill=rgb(48,52,72); bc=rgb(68,74,102); tc=DIM
    else:
        fill=ACC_H if hover else ACC; bc=rgb(130,134,255) if hover else ACC; tc=rgb(255,255,255)
    drawRect(x,y,w,h,fill=fill,border=bc,borderWidth=1,roundness=9)
    drawLabel(b["label"],x+w/2,y+h/2,size=12,fill=tc,bold=True)

def draw_loss_graph(app):
    gx,gy,gw,gh=40,470,560,110
    drawRect(gx,gy,gw,gh,fill=PANEL2,border=BORDER,roundness=10)
    for i in range(1,4):
        yy=gy+i*gh//4
        drawLine(gx,yy,gx+gw,yy,fill=GRID,lineWidth=0.6,dashes=True)
    if len(app.loss_hist)<2:
        drawLabel(app.fetch_status[:78], gx+gw/2, gy+gh/2, size=9, fill=DIM, align="center-center")
        return
    max_l=max(max(app.loss_hist), max(app.val_loss_hist) if app.val_loss_hist else 0)
    min_l=min(min(app.loss_hist), min(app.val_loss_hist) if app.val_loss_hist else 0)
    rng=max_l-min_l if max_l-min_l>0.05 else 0.5
    pts=[]
    for i,v in enumerate(app.loss_hist):
        x=gx+12 + (i/max(1,len(app.loss_hist)-1))*(gw-24)
        y=gy+gh-12 - ((v-min_l)/rng*(gh-24))
        pts.append((x,y))
    for i in range(len(pts)-1):
        drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=ACC,lineWidth=1.8)
    step=max(1,len(pts)//16)
    for j in range(0,len(pts),step):
        x,y=pts[j]
        drawCircle(x,y,2.5,fill=ACC,border=rgb(255,255,255),borderWidth=0.8)
    pts2=[]
    for i,v in enumerate(app.val_loss_hist):
        x=gx+12 + (i/max(1,len(app.val_loss_hist)-1))*(gw-24)
        y=gy+gh-12 - ((v-min_l)/rng*(gh-24))
        pts2.append((x,y))
    for i in range(len(pts2)-1):
        drawLine(pts2[i][0],pts2[i][1],pts2[i+1][0],pts2[i+1][1],fill=ACC2,lineWidth=2.0)
    vstep=max(1,len(pts2)//12)
    for j in range(0,len(pts2),vstep):
        x,y=pts2[j]
        drawCircle(x,y,3,fill=ACC2,border=rgb(255,255,255),borderWidth=0.8)
    drawLabel(f"train {app.loss_hist[-1]:.3f} {len(app.loss_hist)}pts", gx+gw-12, gy+12, size=10, fill=DIM, align="right-top")
    if app.val_loss_hist:
        drawLabel(f"val {app.val_loss_hist[-1]:.3f} acc {app.val_acc_hist[-1]*100:.1f}%", gx+gw-12, gy+26, size=10, fill=ACC2, align="right-top")
    drawLabel("purple=train green=val", gx+12, gy+80, size=8, fill=DIM, align="left-top")

def redrawAll(app):
    drawRect(0,0,WIDTH,68,fill=rgb(18,20,32))
    drawLabel("Fashion-MNIST MLP Lab",28,16,size=22,fill=TXT,bold=True,align="left-top")
    drawLabel("Sigma Scholar Alliance",28,42,size=15,fill=DIM,align="left-top")
    drawRect(0,HEIGHT-30,WIDTH,30,fill=rgb(18,20,32),border=GRID)
    drawLabel(f"{app.status} | {app.fetch_status[:140]}",12,HEIGHT-15,size=9,fill=DIM,align="left-center")
    draw_panel(20,80,600,590,title=f"Training - Official Fashion-MNIST Epoch {app.epoch}/{app.max_epochs} Hidden {app.hidden}")
    for bid in ["load","train","reset","cache"]:
        if bid in app.buttons:
            b=app.buttons[bid]
            draw_button(b, app.hover==bid, b["enabled"])
    if app.dataset_loaded:
        drawLabel(f"Samples 28x28 x3 - {len(app.X_all)} total - 4 DATA FETCHES",32,145,size=10,fill=DIM,align="left-top")
        for i in range(10):
            col=i%5; row=i//5; x=32+col*116; y=165+row*76
            drawRect(x,y,104,64,fill=rgb(24,28,44),border=BORDER,roundness=9)
            drawLabel(SHORT[i],x+52,y+8,size=10,fill=TXT,bold=True,align="center-top")
            vec=app.samples.get(i)
            if vec is not None:
                try:
                    for r in range(28):
                        for c in range(28):
                            fv=float(vec[r*28+c])
                            if fv>1.0: fv/=255.0
                            fv=max(0.0,min(1.0,fv))
                            if fv<0.05: continue
                            gray=int(fv*255)
                            px=x+22 + int(c*60/28)
                            py=y+22 + int(r*36/28)
                            pw=max(1,int(60/28))
                            ph=max(1,int(36/28))
                            drawRect(px,py,pw,ph,fill=rgb(gray,gray,gray))
                except:
                    pass
    else:
        drawLabel("Click Load - WILL fire 4 fetches to raw GitHub .gz + S3 .gz - official",32,145,size=10,fill=DIM,align="left-top")
        drawLabel("Sources: raw.githubusercontent.com/.../ubyte.gz + S3 fashion-mnist + TF",32,163,size=9,fill=ACC,align="left-top")
        drawLabel("Fixed: overlap + slow 47M loop -> fast to_py() + CACHE",32,181,size=9,fill=ACC2,align="left-top")
    drawLabel("Architecture:",32,330,size=12,fill=TXT,bold=True,align="left-top")
    ix,iy=48,345
    for i in range(8):
        drawCircle(ix,iy+i*10,3,fill=rgb(120,130,170))
    drawLabel("784",ix,iy+90,size=10,fill=DIM,align="center-top")
    hx,hy=180,345
    for i in range(6):
        drawCircle(hx,hy+i*13,5,fill=ACC)
    drawLabel(f"{app.hidden} ReLU",hx,hy+90,size=10,fill=ACC,align="center-top")
    ox,oy=320,345
    for i in range(10):
        c=ACC2 if app.pred is not None and i==app.pred else rgb(100,110,140)
        drawCircle(ox,oy+i*8,4,fill=c)
    drawLabel("10 Softmax",ox,oy+90,size=10,fill=DIM,align="center-top")
    drawLine(ix+6,iy+20,hx-6,hy+20,fill=GRID,lineWidth=0.5)
    drawLine(hx+8,hy+30,ox-6,oy+30,fill=GRID,lineWidth=0.5)
    if app.training:
        bx,by,bw,bh=400,345,200,14
        drawRect(bx,by,bw,bh,fill=rgb(32,36,60),border=BORDER,roundness=6)
        drawRect(bx,by,bw*app.progress,bh,fill=ACC,roundness=6)
        drawLabel("Training...",bx+bw/2,by+bh/2,size=10,fill=rgb(255,255,255),bold=True)
    draw_loss_graph(app)
    draw_panel(640,80,390,590,title="Inference - Upload Auto Scaled & Cropped 28x28")
    ux,uy,uw,uh=670,120,330,200
    bc=ACC if app.upload_hover else BORDER
    fc=rgb(36,41,68) if app.upload_hover else rgb(28,32,52)
    drawRect(ux,uy,uw,uh,fill=fc,border=bc,borderWidth=2,roundness=12,dashes=True)
    if app.orig_url is None:
        drawLabel("DROP or CLICK to upload",ux+uw/2,uy+50,size=14,fill=TXT,bold=True,align="center-top")
        drawLabel("shirt, shoe, pant, skirt, dress, bag...",ux+uw/2,uy+76,size=11,fill=DIM,align="center-top")
        drawLabel("load_image(file, max_dimension=384)",ux+uw/2,uy+102,size=10,fill=ACC,align="center-top")
        drawLabel("TOP-TIER: bbox detect + multi-step resize",ux+uw/2,uy+118,size=10,fill=DIM,align="center-top")
        drawLabel("contrast stretch + proper 140x140 artifact",ux+uw/2,uy+132,size=10,fill=DIM,align="center-top")
        drawLabel("Cached weights auto-loaded if available",ux+uw/2,uy+158,size=9,fill=ACC2,align="center-top")
    else:
        drawLabel("Original (via load_image):",ux+8,uy+8,size=10,fill=DIM,align="left-top")
        try: drawImage(app.orig_url,ux+10,uy+24,100,100)
        except: drawRect(ux+10,uy+24,100,100,fill=rgb(50,50,60))
        drawLabel("28x28 x5 TOP-TIER:",ux+130,uy+8,size=10,fill=ACC,bold=True,align="left-top")
        if app.proc_url:
            try: 
                drawImage(app.proc_url,ux+130,uy+24,140,140)
            except: drawRect(ux+130,uy+24,140,140,fill=rgb(40,40,50))
        if hasattr(app,'crop_info') and app.crop_info:
            ci=app.crop_info
            drawLabel(f"crop {ci.get('bbox_w','?')}x{ci.get('bbox_h','?')}->{ci.get('size','?')} sq",ux+8,uy+134,size=8,fill=DIM,align="left-top")
    cb=app.buttons["clear"]
    draw_button(cb,app.hover=="clear",cb["enabled"])
    py=382
    drawRect(670,py,330,262,fill=PANEL2,border=GRID,roundness=10)
    if app.pred is None:
        drawLabel("No inference yet",835,py+40,size=13,fill=DIM,align="center-top")
        drawLabel("Train MLP then upload",835,py+62,size=11,fill=DIM,align="center-top")
        for i in range(10):
            drawLabel(f"{i}: {LABELS[i]}",680,py+90+i*15,size=10,fill=DIM,align="left-top")
    else:
        label=LABELS.get(app.pred,str(app.pred))
        conf=app.probs[app.pred]*100 if app.probs else 0
        drawLabel(f"Predicted: {label}",835,py+12,size=16,fill=TXT,bold=True,align="center-top")
        drawLabel(f"{conf:.1f}% {SHORT[app.pred]}",835,py+34,size=13,fill=ACC2,bold=True,align="center-top")
        indexed=sorted(enumerate(app.probs),key=lambda x:x[1],reverse=True)
        for rank,(idx,p) in enumerate(indexed):
            bx=680; by=py+60+rank*20; bw=190; bh=12
            drawRect(bx,by,bw,bh,fill=rgb(35,40,60),roundness=4)
            drawRect(bx,by,bw*p,bh,fill=ACC if idx==app.pred else rgb(80,90,130),roundness=4)
            drawLabel(f"{SHORT[idx]}",bx+bw+8,by+bh/2,size=10,fill=TXT,align="left-center")
            drawLabel(f"{p*100:.1f}%",bx+bw/2,by+bh/2,size=9,fill=rgb(255,255,255),align="center-center")

# === Override onAppStart to add CACHE button and auto-load cache ===
orig_onAppStart = onAppStart
def onAppStart(app):
    orig_onAppStart(app)
    app.buttons["reset"]["label"]="CLEAR CACHE"
    app.buttons["reset"]["x"]=350; app.buttons["reset"]["y"]=610; app.buttons["reset"]["w"]=110; app.buttons["reset"]["h"]=38
    app.buttons["cache"]={"x":475,"y":610,"w":135,"h":38,"label":"CACHE WEIGHTS","enabled":False}
    try:
        if try_load_cached_weights(app):
            app.buttons["load"]["enabled"]=False
            app.dataset_loaded=True
            app.fetch_status="Cache loaded - weights ready"
    except:
        pass
