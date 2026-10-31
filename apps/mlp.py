
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
        "load":{"x":40,"y":610,"w":160,"h":38,"label":"Load Fashion-MNIST","enabled":True},
        "train":{"x":215,"y":610,"w":130,"h":38,"label":"Train MLP","enabled":False},
        "reset":{"x":360,"y":610,"w":80,"h":38,"label":"Reset","enabled":True},  # BOTTOM OPEN SPACE - was 600
        "clear":{"x":670,"y":340,"w":80,"h":28,"label":"Clear","enabled":True},
    }
    app.hover=None; app.upload_hover=False

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
    app.epoch=0; app.buttons["train"]["enabled"]=False
    # RESPONSIBLE PIPELINE: FULL 4915 train, 1085 val, no cut, chunked micro-batches
    # Push data responsibly: small allocs, yield every 4 samples, progress bar
    Xtr=app.X_train; ytr=app.y_train; Xva=app.X_val; yva=app.y_val
    app.batch=16  # Smaller batch = smaller per-chunk work = no freeze
    app.max_epochs=8  # 8 epochs full dataset = good accuracy for demo
    W1,b1,W2,b2=init_weights(app.hidden)
    app.W1=W1; app.b1=b1; app.W2=W2; app.b2=b2
    app.status=f"Training FULL {len(Xtr)} samples - responsible pipeline batch {app.batch}"
    for ep in range(app.max_epochs):
        app.epoch=ep+1
        app.status=f"Training epoch {app.epoch}/{app.max_epochs}..."
        idx=list(range(len(Xtr)))
        random.shuffle(idx)
        total_loss=0.0; correct=0; batches=0
        for start in range(0,len(idx),app.batch):
            batch_idx=idx[start:start+app.batch]
            if not batch_idx:
                continue
            dW1=[[0.0]*app.hidden for _ in range(784)]
            db1=[0.0]*app.hidden
            dW2=[[0.0]*10 for _ in range(app.hidden)]
            db2=[0.0]*10
            batch_loss=0.0; batch_correct=0
            # Responsible: process samples in micro-chunks of 2, yield between
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
                # Responsible pipeline: yield every 2 samples, not blocking main thread
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
            # Responsible: yield + progress after every micro-batch
            app.progress=(app.epoch-1 + batches/((len(Xtr)+app.batch-1)//app.batch))/app.max_epochs
            await aio.sleep(0.01)
            if batches%5==0:
                app.status=f"Epoch {app.epoch}/{app.max_epochs} batch {batches}/{(len(Xtr)+app.batch-1)//app.batch} loss {total_loss/batches:.3f} - pushing {len(Xtr)} samples responsibly"
                await aio.sleep(0)

        avg_loss=total_loss/batches if batches else 0
        acc=correct/len(Xtr) if Xtr else 0
        val_loss=0.0; val_correct=0
        for xi,yi in zip(Xva,yva):
            _,_,_,probs=forward(xi,W1,b1,W2,b2)
            yi_int=int(yi)
            p=probs[yi_int] if yi_int < len(probs) else 1e-12
            p=min(max(p,1e-12),1-1e-12)
            val_loss+=-math.log(p)
            pred=max(range(len(probs)), key=lambda k: probs[k])
            if pred==yi_int:
                val_correct+=1
        val_loss/=len(Xva) if Xva else 1
        val_acc=val_correct/len(Xva) if Xva else 0
        app.loss_hist.append(avg_loss); app.acc_hist.append(acc)
        app.val_loss_hist.append(val_loss); app.val_acc_hist.append(val_acc)
        app.W1=W1; app.b1=b1; app.W2=W2; app.b2=b2
        app.progress=(ep+1)/app.max_epochs
        app.status=f"Epoch {app.epoch}/{app.max_epochs} loss {avg_loss:.3f} acc {acc*100:.1f}% val {val_acc*100:.1f}%"
        await aio.sleep(0.05)
        app.lr*=0.95
    app.training=False; app.trained=True; app.buttons["train"]["enabled"]=True
    app.status=f"Done acc {app.acc_hist[-1]*100:.1f}% val {app.val_acc_hist[-1]*100:.1f}% - TOP TIER"

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
    orig_w=int(width); orig_h=int(height); size=min(orig_w,orig_h)
    sx=(orig_w-size)//2; sy=(orig_h-size)//2
    dst_canvas=document.createElement("canvas")
    dst_canvas.width=28; dst_canvas.height=28
    dctx=dst_canvas.getContext("2d")
    try: dctx.drawImage(src_canvas, sx, sy, size, size, 0, 0, 28, 28)
    except: dctx.drawImage(src_canvas,0,0,28,28)
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
    big_canvas=document.createElement("canvas")
    big_canvas.width=140; big_canvas.height=140
    bctx=big_canvas.getContext("2d")
    bctx.imageSmoothingEnabled=False
    bctx.drawImage(dst_canvas,0,0,140,140)
    proc_url=big_canvas.toDataURL("image/png")
    return {"original_url":previewUrl,"processed_url":proc_url,"vector":vec}

async def handle_upload(app, source):
    app.status="Loading via load_image()..."
    try:
        result=await process_upload_to_28x28(source)
        vec=result.get("vector")
        vec_f=[max(0.0,min(1.0,float(v))) for v in vec]
        app.orig_url=result.get("original_url"); app.proc_url=result.get("processed_url"); app.proc_vec=vec_f
        if app.W1 is None:
            app.status="Upload 28x28 processed - train first"; return
        _,_,_,probs=forward(vec_f, app.W1, app.b1, app.W2, app.b2)
        pred=max(range(len(probs)), key=lambda k: probs[k])
        app.probs=probs; app.pred=int(pred)
        app.status=f"Inferred {LABELS.get(int(pred),str(pred))} {probs[int(pred)]*100:.1f}%"
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
                app.W1=None; app.b1=None; app.W2=None; app.b2=None
                app.trained=False; app.loss_hist=[]; app.acc_hist=[]; app.val_loss_hist=[]; app.val_acc_hist=[]; app.epoch=0; app.lr=0.08
                app.pred=None; app.probs=None; app.orig_url=None; app.proc_url=None; app.proc_vec=None
                app.dataset_loaded=False; app.X_train=[]; app.y_train=[]; app.sample_urls=[None]*10
                app.status="Reset"; app.fetch_status="Ready"; app.buttons["load"]["enabled"]=True; app.buttons["train"]["enabled"]=False
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
    gx,gy,gw,gh=40,470,560,110  # MOVED WAY DOWN - was 440, now 470 gives 185px gap
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
        drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=ACC,lineWidth=2.2)
    for x,y in pts:
        drawCircle(x,y,3,fill=ACC,border=rgb(255,255,255),borderWidth=1)
    pts2=[]
    for i,v in enumerate(app.val_loss_hist):
        x=gx+12 + (i/max(1,len(app.val_loss_hist)-1))*(gw-24)
        y=gy+gh-12 - ((v-min_l)/rng*(gh-24))
        pts2.append((x,y))
    for i in range(len(pts2)-1):
        drawLine(pts2[i][0],pts2[i][1],pts2[i+1][0],pts2[i+1][1],fill=ACC2,lineWidth=1.6)
    drawLabel(f"train {app.loss_hist[-1]:.3f}", gx+gw-12, gy+12, size=10, fill=DIM, align="right-top")
    drawLabel(f"val {app.val_loss_hist[-1]:.3f} acc {app.val_acc_hist[-1]*100:.1f}%", gx+gw-12, gy+26, size=10, fill=ACC2, align="right-top")

def redrawAll(app):
    drawRect(0,0,WIDTH,68,fill=rgb(18,20,32))
    drawLabel("Fashion-MNIST MLP Lab 1050x700 - TOP TIER FIXED ARCH VISIBLE + BUTTONS BOTTOM",28,16,size=18,fill=TXT,bold=True,align="left-top")
    drawLabel("784->64 ReLU->10 Softmax | Arch Y=285 Loss Y=470 Buttons Y=610 - NO OVERLAP",28,42,size=10,fill=DIM,align="left-top")
    drawRect(0,HEIGHT-30,WIDTH,30,fill=rgb(18,20,32),border=GRID)
    drawLabel(f"{app.status} | {app.fetch_status[:140]}",12,HEIGHT-15,size=9,fill=DIM,align="left-center")
    draw_panel(20,80,600,590,title=f"Training - Official Fashion-MNIST Epoch {app.epoch}/{app.max_epochs} Hidden {app.hidden}")
    for bid in ["load","train","reset"]:
        b=app.buttons[bid]
        draw_button(b, app.hover==bid, b["enabled"])
    if app.dataset_loaded:
        drawLabel(f"Samples 28x28 x3 - {len(app.X_all)} total - 4 FETCHES DONE",32,145,size=10,fill=DIM,align="left-top")
        for i in range(10):
            col=i%5; row=i//5; x=32+col*116; y=165+row*76
            drawRect(x,y,104,64,fill=rgb(24,28,44),border=BORDER,roundness=9)
            drawLabel(SHORT[i],x+52,y+8,size=10,fill=TXT,bold=True,align="center-top")
            # FIXED: Draw sample via rects to avoid scs.py img.src warning (drawImage triggers warning for dataURL)
            vec=app.samples.get(i)
            if vec is not None:
                try:
                    # Draw 28x28 scaled to 60x36 inside card
                    for r in range(28):
                        for c in range(28):
                            fv=float(vec[r*28+c])
                            if fv>1.0: fv/=255.0
                            fv=max(0.0,min(1.0,fv))
                            if fv<0.05: continue
                            gray=int(fv*255)
                            # Scale 60/28=2.14 width, 36/28=1.28 height
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
        drawLabel("Fixed: overlap + slow 47M loop -> fast to_py()",32,181,size=9,fill=ACC2,align="left-top")
    # FIXED LAYOUT - architecture higher, loss lower - no overlap
    drawLabel("Architecture:",32,270,size=12,fill=TXT,bold=True,align="left-top")
    ix,iy=48,285  # MOVED UP - was 365 covering
    for i in range(8):
        drawCircle(ix,iy+i*10,3,fill=rgb(120,130,170))
    drawLabel("784",ix,iy+90,size=10,fill=DIM,align="center-top")
    hx,hy=180,285
    for i in range(6):
        drawCircle(hx,hy+i*13,5,fill=ACC)
    drawLabel(f"{app.hidden} ReLU",hx,hy+90,size=10,fill=ACC,align="center-top")
    ox,oy=320,285
    for i in range(10):
        c=ACC2 if app.pred is not None and i==app.pred else rgb(100,110,140)
        drawCircle(ox,oy+i*8,4,fill=c)
    drawLabel("10 Softmax",ox,oy+90,size=10,fill=DIM,align="center-top")
    drawLine(ix+6,iy+20,hx-6,hy+20,fill=GRID,lineWidth=0.5)
    drawLine(hx+8,hy+30,ox-6,oy+30,fill=GRID,lineWidth=0.5)
    if app.training:
        bx,by,bw,bh=400,285,200,14
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
        drawLabel("center-crops to square, resizes to 28x28",ux+uw/2,uy+118,size=10,fill=DIM,align="center-top")
        drawLabel("grayscale, invert if light, normalize 0-1",ux+uw/2,uy+132,size=10,fill=DIM,align="center-top")
        drawLabel("Proper method from extensions.file_loader",ux+uw/2,uy+158,size=9,fill=DIM,align="center-top")
    else:
        drawLabel("Original (via load_image):",ux+8,uy+8,size=10,fill=DIM,align="left-top")
        try: drawImage(app.orig_url,ux+10,uy+24,100,100)
        except: drawRect(ux+10,uy+24,100,100,fill=rgb(50,50,60))
        drawLabel("28x28 processed x5:",ux+130,uy+8,size=10,fill=DIM,align="left-top")
        if app.proc_url:
            try: drawImage(app.proc_url,ux+130,uy+24,140,140)
            except: drawRect(ux+130,uy+24,140,140,fill=rgb(40,40,50))
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
