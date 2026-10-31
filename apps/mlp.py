from scs import *
from browser import document, window, aio
from extensions.file_loader import FileLoader
from extensions.pyodide import PyodideWorker
import math

WIDTH = 1050
HEIGHT = 700

LABELS = {
    0: "T-shirt/top",
    1: "Trouser",
    2: "Pullover",
    3: "Dress",
    4: "Coat",
    5: "Sandal",
    6: "Shirt",
    7: "Sneaker",
    8: "Bag",
    9: "Ankle boot"
}
SHORT = {
    0: "T-shirt",
    1: "Trouser",
    2: "Pullover",
    3: "Dress",
    4: "Coat",
    5: "Sandal",
    6: "Shirt",
    7: "Sneaker",
    8: "Bag",
    9: "Boot"
}

BG_TOP = rgb(11, 13, 22)
BG_BOT = rgb(27, 31, 50)
PANEL = rgb(30, 34, 52)
PANEL2 = rgb(22, 26, 40)
BORDER = rgb(56, 63, 92)
ACC = rgb(99, 102, 241)
ACC_H = rgb(129, 133, 255)
ACC2 = rgb(16, 185, 129)
TXT = rgb(235, 238, 250)
DIM = rgb(148, 158, 185)
GRID = rgb(45, 51, 78)

# Global extension instances - Model layer only, no drawing here
file_loader = FileLoader()
pyodide = PyodideWorker()

def onAppStart(app):
    app.width = WIDTH
    app.height = HEIGHT
    app.stepsPerSecond = 30
    app.background = gradient(BG_TOP, BG_BOT, start='top')

    app.file_ready = False
    app.pyodide_ready = False
    app.dataset_ready = False
    app.training = False
    app.trained = False

    app.X_train = None
    app.y_train = None
    app.X_test = None
    app.y_test = None

    app.W1 = None
    app.b1 = None
    app.W2 = None
    app.b2 = None

    app.epoch = 0
    app.max_epochs = 15
    app.lr = 0.08
    app.batch = 64
    app.hidden = 128

    app.loss_hist = []
    app.acc_hist = []
    app.progress = 0.0

    app.orig_url = None
    app.proc_url = None
    app.proc_vec = None
    app.pred = None
    app.probs = None

    app.buttons = {
        'load': {'x': 30, 'y': 92, 'w': 160, 'h': 38, 'label': 'Load Fashion-MNIST', 'enabled': False},
        'train': {'x': 205, 'y': 92, 'w': 130, 'h': 38, 'label': 'Train MLP', 'enabled': False},
        'reset': {'x': 350, 'y': 92, 'w': 80, 'h': 38, 'label': 'Reset', 'enabled': False},
        'clear': {'x': 670, 'y': 340, 'w': 80, 'h': 28, 'label': 'Clear', 'enabled': True},
    }
    app.hover = None
    app.upload_hover = False
    app.status = "Awaiting extension ready state..."

    app.sample_urls = [None]*10

    # hidden file input - used together with file_loader for picking
    inp = document.createElement('input')
    inp.type = 'file'
    inp.accept = 'image/*'
    inp.style.display = 'none'
    document.body.appendChild(inp)
    app.file_input = inp

    def on_change(evt):
        f = evt.target.files[0] if evt.target.files.length > 0 else None
        if f:
            aio.run(handle_upload(app, f))
        inp.value = ''

    inp.bind('change', on_change)

    # Await ready state for both extensions - no fallbacks
    aio.run(init_extensions(app))

async def init_extensions(app):
    app.status = "Initializing file_loader extension..."
    await file_loader.ready()
    app.file_ready = True
    app.status = "file_loader ready. Initializing pyodide extension..."

    await pyodide.ready()
    app.pyodide_ready = True
    app.status = "Pyodide ready. Loading NumPy, SciPy, scikit-learn..."

    # Init pyodide environment - Fashion-MNIST via sklearn
    await pyodide.run("""
import numpy as np
import micropip
await micropip.install('scikit-learn')
import sklearn
print('sklearn ready')
""")
    app.status = "Extensions ready. Click Load Fashion-MNIST."
    app.buttons['load']['enabled'] = True
    app.buttons['reset']['enabled'] = True

async def load_fashion_mnist(app):
    if not app.file_ready or not app.pyodide_ready:
        app.status = "Awaiting ready state..."
        return
    app.status = "Loading Fashion-MNIST (70k 28x28) via Pyodide + sklearn.datasets.fetch_openml..."
    app.buttons['load']['enabled'] = False

    code = """
from sklearn.datasets import fetch_openml
import numpy as np

X, y = fetch_openml('Fashion-MNIST', version=1, return_X_y=True, as_frame=False)
X = X.astype(np.float32) / 255.0
y = y.astype(np.int64)

# Use 6000 train, 1000 test for demo speed in browser
X_train = X[:6000]
y_train = y[:6000]
X_test = X[6000:7000]
y_test = y[6000:7000]

# Prepare sample preview URLs for each class - one image per class from test set
samples = {}
for i in range(len(X_test)):
    label = int(y_test[i])
    if label not in samples:
        samples[label] = X_test[i]
    if len(samples) == 10:
        break

(X_train.tolist(), y_train.tolist(), X_test.tolist(), y_test.tolist(), {k: v.tolist() for k,v in samples.items()})
"""

    result = await pyodide.run(code)
    # result is tuple: X_train, y_train, X_test, y_test, samples dict
    X_train, y_train, X_test, y_test, samples_dict = result

    app.X_train = X_train
    app.y_train = y_train
    app.X_test = X_test
    app.y_test = y_test
    app.dataset_ready = True

    # Build sample preview data URLs using file_loader to create image from rgba
    # file_loader provides utility to convert 28x28 grayscale to data URL
    for label in range(10):
        if str(label) in samples_dict:
            vec = samples_dict[str(label)]
        elif label in samples_dict:
            vec = samples_dict[label]
        else:
            continue
        # vec is list 784 float 0-1
        # Use file_loader to create data URL - auto scaled handling inside extension
        rgba = await file_loader.create_rgba_from_grayscale(vec, 28, 28)
        url = await file_loader.to_data_url(rgba, 28, 28, scale=2)
        app.sample_urls[label] = url

    app.status = f"Fashion-MNIST loaded: {len(y_train)} train, {len(y_test)} test. Ready to train MLP 784->{app.hidden}->10"
    app.buttons['train']['enabled'] = True

async def train_mlp(app):
    if not app.dataset_ready or app.training:
        return
    app.training = True
    app.trained = False
    app.loss_hist = []
    app.acc_hist = []
    app.epoch = 0
    app.buttons['train']['enabled'] = False
    app.status = f"Training MLP {app.hidden} hidden, ReLU, Softmax, lr={app.lr}"

    # Initialize weights in Pyodide
    await pyodide.run(f"""
import numpy as np
hidden = {app.hidden}
np.random.seed(0)
W1 = np.random.randn(784, hidden).astype(np.float32) * np.sqrt(2.0/784)
b1 = np.zeros(hidden, dtype=np.float32)
W2 = np.random.randn(hidden, 10).astype(np.float32) * np.sqrt(2.0/hidden)
b2 = np.zeros(10, dtype=np.float32)
print('weights init')
""")

    X_train = app.X_train
    y_train = app.y_train

    # Push training data into pyodide worker - zero-copy via file_loader helper
    await pyodide.set_var('X_train', X_train)
    await pyodide.set_var('y_train', y_train)
    await pyodide.set_var('lr', app.lr)
    await pyodide.set_var('batch_size', app.batch)

    for epoch in range(app.max_epochs):
        app.epoch = epoch + 1
        app.status = f"Epoch {app.epoch}/{app.max_epochs} training..."

        train_code = """
import numpy as np

n = X_train.shape[0] if hasattr(X_train, 'shape') else len(X_train)
# Convert lists to numpy if needed
if not isinstance(X_train, np.ndarray):
    X_tr = np.array(X_train, dtype=np.float32)
    y_tr = np.array(y_train, dtype=np.int64)
else:
    X_tr = X_train
    y_tr = y_train

# shuffle
idx = np.random.permutation(n)
X_shuf = X_tr[idx]
y_shuf = y_tr[idx]

total_loss = 0.0
correct = 0
batches = 0

for start in range(0, n, batch_size):
    end = min(start+batch_size, n)
    xb = X_shuf[start:end]
    yb = y_shuf[start:end]
    bsize = xb.shape[0]

    # forward
    z1 = xb @ W1 + b1
    a1 = np.maximum(0, z1)
    z2 = a1 @ W2 + b2
    # softmax
    z2_shift = z2 - np.max(z2, axis=1, keepdims=True)
    exp = np.exp(z2_shift)
    probs = exp / np.sum(exp, axis=1, keepdims=True)

    # loss
    # cross-entropy
    logp = -np.log(probs[np.arange(bsize), yb] + 1e-12)
    loss = np.mean(logp)
    total_loss += loss

    # accuracy
    pred = np.argmax(probs, axis=1)
    correct += np.sum(pred == yb)
    batches += 1

    # backward
    d_z2 = probs.copy()
    d_z2[np.arange(bsize), yb] -= 1
    d_z2 /= bsize

    d_W2 = a1.T @ d_z2
    d_b2 = np.sum(d_z2, axis=0)

    d_a1 = d_z2 @ W2.T
    d_z1 = d_a1 * (z1 > 0)

    d_W1 = xb.T @ d_z1
    d_b1 = np.sum(d_z1, axis=0)

    # sgd
    W1 -= lr * d_W1
    b1 -= lr * d_b1
    W2 -= lr * d_W2
    b2 -= lr * d_b2

avg_loss = total_loss / batches
acc = correct / n
(avg_loss, acc, W1.tolist(), b1.tolist(), W2.tolist(), b2.tolist())
"""

        avg_loss, acc, W1_list, b1_list, W2_list, b2_list = await pyodide.run(train_code)

        app.loss_hist.append(float(avg_loss))
        app.acc_hist.append(float(acc))
        app.W1 = W1_list
        app.b1 = b1_list
        app.W2 = W2_list
        app.b2 = b2_list
        app.progress = (epoch + 1) / app.max_epochs

        app.status = f"Epoch {app.epoch}/{app.max_epochs} - loss {avg_loss:.4f} - acc {acc*100:.2f}%"
        # allow UI to redraw
        await aio.sleep(0.05)

        # decay lr
        await pyodide.run("lr *= 0.95")

    app.training = False
    app.trained = True
    app.buttons['train']['enabled'] = True
    app.status = f"Training done! Final acc {app.acc_hist[-1]*100:.2f}%. Upload image to infer shirts, shoes, pants, etc."

async def handle_upload(app, file_obj):
    if not app.file_ready or not app.pyodide_ready:
        app.status = "Awaiting extension ready state..."
        return

    app.status = f"File loader: loading {file_obj.name}, auto scaling & center-cropping to 28x28..."

    # Use file_loader extension to load and auto scale/crop to proper dimensions
    # This is the required behavior: user uploads image, gets auto scaled and cropped
    result = await file_loader.load_image_auto_crop(
        file_obj,
        target_width=28,
        target_height=28,
        crop_mode='center',
        grayscale=True,
        invert_if_light=True,
        normalize=True
    )
    # result contains: original_url, processed_url, vector (784 float 0-1)

    app.orig_url = result['original_url']
    app.proc_url = result['processed_url']
    app.proc_vec = result['vector']

    # Inference via Pyodide MLP
    await pyodide.set_var('vec', app.proc_vec)
    await pyodide.set_var('W1_inf', app.W1)
    await pyodide.set_var('b1_inf', app.b1)
    await pyodide.set_var('W2_inf', app.W2)
    await pyodide.set_var('b2_inf', app.b2)

    infer_code = """
import numpy as np
x = np.array(vec, dtype=np.float32).reshape(1, -1)
W1 = np.array(W1_inf, dtype=np.float32)
b1 = np.array(b1_inf, dtype=np.float32)
W2 = np.array(W2_inf, dtype=np.float32)
b2 = np.array(b2_inf, dtype=np.float32)

z1 = x @ W1 + b1
a1 = np.maximum(0, z1)
z2 = a1 @ W2 + b2
# softmax
z2 = z2 - np.max(z2)
exp = np.exp(z2)
probs = exp / np.sum(exp)
pred = int(np.argmax(probs))
(probs[0].tolist(), pred)
"""
    probs_list, pred = await pyodide.run(infer_code)
    app.probs = probs_list
    app.pred = pred
    label = LABELS.get(pred, str(pred))
    app.status = f"Inferred {label} ({probs_list[pred]*100:.1f}%) via MLP - file_loader auto cropped & scaled to 28x28"

def onMousePress(app, mx, my):
    for bid, b in app.buttons.items():
        if b['x'] <= mx <= b['x']+b['w'] and b['y'] <= my <= b['y']+b['h'] and b['enabled']:
            if bid == 'load':
                aio.run(load_fashion_mnist(app))
            elif bid == 'train':
                aio.run(train_mlp(app))
            elif bid == 'reset':
                app.W1 = None
                app.b1 = None
                app.W2 = None
                app.b2 = None
                app.trained = False
                app.loss_hist = []
                app.acc_hist = []
                app.epoch = 0
                app.pred = None
                app.probs = None
                app.orig_url = None
                app.proc_url = None
                app.proc_vec = None
                app.status = "Reset. Load Fashion-MNIST again."
            elif bid == 'clear':
                app.orig_url = None
                app.proc_url = None
                app.proc_vec = None
                app.pred = None
                app.probs = None
                app.status = "Cleared. Upload new image."
            return
    if 670 <= mx <= 1000 and 120 <= my <= 320:
        # Trigger file_loader picker
        aio.run(trigger_file_picker(app))

async def trigger_file_picker(app):
    # Uses file_loader extension to open native file dialog
    file_obj = await file_loader.open_picker(accept='image/*')
    if file_obj:
        await handle_upload(app, file_obj)
    else:
        # fallback to hidden input click (still uses file_loader for processing)
        app.file_input.click()

def onMouseMove(app, mx, my):
    app.hover = None
    for bid, b in app.buttons.items():
        if b['x'] <= mx <= b['x']+b['w'] and b['y'] <= my <= b['y']+b['h']:
            app.hover = bid
    app.upload_hover = (670 <= mx <= 1000 and 120 <= my <= 320)

def onKeyPress(app, key):
    if key == 'l' or key == 'L':
        if app.buttons['load']['enabled']:
            aio.run(load_fashion_mnist(app))
    elif key == 't' or key == 'T':
        if app.buttons['train']['enabled']:
            aio.run(train_mlp(app))

def draw_panel(x, y, w, h, title):
    drawRect(x, y, w, h, fill=PANEL, border=BORDER, borderWidth=1, roundness=14, opacity=96)
    drawRect(x, y, w, 34, fill=rgb(38, 42, 66), roundness=14)
    drawRect(x, y+17, w, 17, fill=rgb(38, 42, 66))
    if title:
        drawLabel(title, x+16, y+17, size=14, fill=TXT, bold=True, align='left-center')

def draw_button(b, hover, enabled):
    x, y, w, h = b['x'], b['y'], b['w'], b['h']
    if not enabled:
        fill = rgb(48, 52, 72)
        bc = rgb(68, 74, 102)
        tc = DIM
    else:
        fill = ACC_H if hover else ACC
        bc = rgb(130, 134, 255) if hover else ACC
        tc = rgb(255, 255, 255)
    drawRect(x, y, w, h, fill=fill, border=bc, borderWidth=1, roundness=9)
    drawLabel(b['label'], x+w/2, y+h/2, size=12, fill=tc, bold=True)

def draw_loss_graph(app):
    gx, gy, gw, gh = 40, 340, 560, 160
    drawRect(gx, gy, gw, gh, fill=PANEL2, border=BORDER, roundness=10)
    for i in range(1, 4):
        yy = gy + i*gh//4
        drawLine(gx, yy, gx+gw, yy, fill=GRID, lineWidth=0.6, dashes=True)
    if len(app.loss_hist) < 2:
        drawLabel("Loss & accuracy will appear after training", gx+gw/2, gy+gh/2, size=11, fill=DIM, align='center-center')
        return
    # loss
    max_l = max(app.loss_hist)
    min_l = min(app.loss_hist)
    rng = max_l - min_l
    if rng < 0.05:
        rng = 0.5
    pts = []
    for i, v in enumerate(app.loss_hist):
        x = gx + 12 + (i / max(1, len(app.loss_hist)-1)) * (gw-24)
        y = gy + gh - 12 - ((v - min_l)/rng * (gh-24))
        pts.append((x, y))
    for i in range(len(pts)-1):
        drawLine(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1], fill=ACC, lineWidth=2.2)
    for x, y in pts:
        drawCircle(x, y, 3, fill=ACC, border=rgb(255,255,255), borderWidth=1)
    # accuracy
    pts2 = []
    for i, v in enumerate(app.acc_hist):
        x = gx + 12 + (i / max(1, len(app.acc_hist)-1)) * (gw-24)
        y = gy + gh - 12 - (v * (gh-24))
        pts2.append((x, y))
    for i in range(len(pts2)-1):
        drawLine(pts2[i][0], pts2[i][1], pts2[i+1][0], pts2[i+1][1], fill=ACC2, lineWidth=1.6)
    drawLabel(f"loss {app.loss_hist[-1]:.3f}", gx+gw-12, gy+12, size=10, fill=DIM, align='right-top')
    drawLabel(f"acc {app.acc_hist[-1]*100:.1f}%", gx+gw-12, gy+26, size=10, fill=ACC2, align='right-top')

def redrawAll(app):
    drawRect(0, 0, WIDTH, 68, fill=rgb(18, 20, 32))
    drawLabel("Fashion-MNIST MLP Lab  -  1050x700  -  Pyodide + FileLoader", 28, 16, size=24, fill=TXT, bold=True, align='left-top')
    drawLabel("MLP: 784 -> 128 ReLU -> 10 Softmax  |  Classes: T-shirt, Trouser, Pullover, Dress, Coat, Sandal, Shirt, Sneaker, Bag, Ankle boot", 28, 42, size=11, fill=DIM, align='left-top')

    drawRect(0, HEIGHT-30, WIDTH, 30, fill=rgb(18, 20, 32), border=GRID)
    drawLabel(f"{app.status}  |  file_loader ready={app.file_ready}  pyodide ready={app.pyodide_ready}  dataset={app.dataset_ready}  trained={app.trained}", 12, HEIGHT-15, size=10, fill=DIM, align='left-center')

    draw_panel(20, 80, 600, 590, title=f"Training - Fashion-MNIST via Pyodide  Epoch {app.epoch}/{app.max_epochs}  Hidden {app.hidden}")

    for bid in ['load', 'train', 'reset']:
        b = app.buttons[bid]
        draw_button(b, app.hover==bid, b['enabled'])

    if app.dataset_ready:
        drawLabel("Dataset samples (one per class, 28x28, rendered via file_loader.to_data_url):", 32, 145, size=11, fill=DIM, align='left-top')
        for i in range(10):
            col = i % 5
            row = i // 5
            x = 32 + col*116
            y = 165 + row*76
            drawRect(x, y, 104, 64, fill=rgb(24, 28, 44), border=BORDER, roundness=9)
            drawLabel(SHORT[i], x+52, y+8, size=10, fill=TXT, bold=True, align='center-top')
            url = app.sample_urls[i]
            if url:
                try:
                    drawImage(url, x+22, y+22, 60, 36)
                except:
                    drawRect(x+22, y+22, 60, 36, fill=rgb(70,70,80))
    else:
        drawLabel("Click Load Fashion-MNIST to fetch 70k images via Pyodide (sklearn.datasets.fetch_openml).", 32, 150, size=11, fill=DIM, align='left-top')
        drawLabel("No fallbacks - awaits file_loader.ready() and pyodide.ready().", 32, 168, size=10, fill=ACC, align='left-top')

    drawLabel("Architecture:", 32, 330, size=12, fill=TXT, bold=True, align='left-top')
    # arch viz
    ix, iy = 48, 352
    for i in range(8):
        drawCircle(ix, iy+i*12, 3, fill=rgb(120,130,170))
    drawLabel("784", ix, iy+100, size=10, fill=DIM, align='center-top')
    hx, hy = 180, 352
    for i in range(6):
        drawCircle(hx, hy+i*16, 5, fill=ACC)
    drawLabel(f"{app.hidden} ReLU", hx, hy+100, size=10, fill=ACC, align='center-top')
    ox, oy = 320, 352
    for i in range(10):
        c = ACC2 if app.pred is not None and i==app.pred else rgb(100,110,140)
        drawCircle(ox, oy+i*10, 4, fill=c)
    drawLabel("10 Softmax", ox, oy+110, size=10, fill=DIM, align='center-top')
    drawLine(ix+6, iy+20, hx-6, hy+20, fill=GRID, lineWidth=0.5)
    drawLine(hx+8, hy+30, ox-6, oy+30, fill=GRID, lineWidth=0.5)

    if app.training:
        bx, by, bw, bh = 400, 352, 200, 14
        drawRect(bx, by, bw, bh, fill=rgb(32,36,60), border=BORDER, roundness=6)
        drawRect(bx, by, bw*app.progress, bh, fill=ACC, roundness=6)
        drawLabel(f"Training...", bx+bw/2, by+bh/2, size=10, fill=rgb(255,255,255), bold=True)

    draw_loss_graph(app)

    # Inference panel
    draw_panel(640, 80, 390, 590, title="Inference - Upload Image Auto Scaled & Cropped to 28x28")

    ux, uy, uw, uh = 670, 120, 330, 200
    bc = ACC if app.upload_hover else BORDER
    fc = rgb(36, 41, 68) if app.upload_hover else rgb(28, 32, 52)
    drawRect(ux, uy, uw, uh, fill=fc, border=bc, borderWidth=2, roundness=12, dashes=True)

    if app.orig_url is None:
        drawLabel("DROP or CLICK to upload", ux+uw/2, uy+50, size=14, fill=TXT, bold=True, align='center-top')
        drawLabel("Photo of shirt, shoe, pant, skirt, dress, bag...", ux+uw/2, uy+76, size=11, fill=DIM, align='center-top')
        drawLabel("file_loader.load_image_auto_crop()", ux+uw/2, uy+102, size=10, fill=ACC, align='center-top')
        drawLabel("center-crops to square, resizes to 28x28", ux+uw/2, uy+118, size=10, fill=DIM, align='center-top')
        drawLabel("grayscale, inverts if light bg, normalizes", ux+uw/2, uy+132, size=10, fill=DIM, align='center-top')
        drawLabel("Uses: extensions.file_loader + pyodide", ux+uw/2, uy+158, size=9, fill=DIM, align='center-top')
    else:
        drawLabel("Original:", ux+8, uy+8, size=10, fill=DIM, align='left-top')
        try:
            drawImage(app.orig_url, ux+10, uy+24, 100, 100)
        except:
            drawRect(ux+10, uy+24, 100, 100, fill=rgb(50,50,60))
        drawLabel("28x28 processed (x5 enlarged):", ux+130, uy+8, size=10, fill=DIM, align='left-top')
        if app.proc_url:
            try:
                drawImage(app.proc_url, ux+130, uy+24, 140, 140)
            except:
                drawRect(ux+130, uy+24, 140, 140, fill=rgb(40,40,50))
        drawLabel("Vector 784 ready for MLP", ux+130, uy+172, size=9, fill=DIM, align='left-top')

    cb = app.buttons['clear']
    draw_button(cb, app.hover=='clear', cb['enabled'])

    py = 382
    drawRect(670, py, 330, 262, fill=PANEL2, border=GRID, roundness=10)
    if app.pred is None:
        drawLabel("No inference yet", 835, py+40, size=13, fill=DIM, align='center-top')
        drawLabel("Train MLP then upload clothing image", 835, py+62, size=11, fill=DIM, align='center-top')
        for i in range(10):
            drawLabel(f"{i}: {LABELS[i]}", 680, py+90 + i*15, size=10, fill=DIM, align='left-top')
    else:
        label = LABELS.get(app.pred, str(app.pred))
        conf = app.probs[app.pred]*100 if app.probs else 0
        drawLabel(f"Predicted: {label}", 835, py+12, size=16, fill=TXT, bold=True, align='center-top')
        drawLabel(f"{conf:.1f}% confident - {SHORT[app.pred]}", 835, py+34, size=13, fill=ACC2, bold=True, align='center-top')
        indexed = sorted(enumerate(app.probs), key=lambda x: x[1], reverse=True)
        for rank, (idx, p) in enumerate(indexed):
            bx = 680
            by = py+60 + rank*20
            bw = 190
            bh = 12
            drawRect(bx, by, bw, bh, fill=rgb(35,40,60), roundness=4)
            drawRect(bx, by, bw*p, bh, fill=ACC if idx==app.pred else rgb(80,90,130), roundness=4)
            drawLabel(f"{SHORT[idx]}", bx+bw+8, by+bh/2, size=10, fill=TXT, align='left-center')
            drawLabel(f"{p*100:.1f}%", bx+bw/2, by+bh/2, size=9, fill=rgb(255,255,255), align='center-center')

    drawLabel("Keys: L=Load  T=Train  R=Reset | Thanksgiving demo ready - audience can upload live photos", 32, HEIGHT-52, size=10, fill=DIM, align='left-top')
