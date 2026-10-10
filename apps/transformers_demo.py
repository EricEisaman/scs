"""
apps/transformers_demo.py
--------------------------
SCS x Transformers.js - 14 Tasks Demo (Exact match for screenshot)

Required options from screenshot (14):
1. Translation w/ t5-small (78 MB)
2. Text generation w/ distilgpt2 (85 MB)
3. Masked language modelling w/ bert-base-cased (110 MB)
4. Text classification w/ bert-base-multilingual-uncased-sentiment (169 MB)
5. Token classification w/ Davlan/bert-base-multilingual-cased-ner-hrl (178 MB)
6. Zero-shot classification w/ typeform/distilbert-base-uncased-mnli (68 MB)
7. Question answering w/ distilbert-base-cased-distilled-squad (66 MB)
8. Summarization w/ distilbart-cnn-6-6 (284 MB)
9. Code completion w/ Salesforce/codegen-350M-mono (369 MB)
10. Speech to text w/ whisper-tiny.en (41 MB)
11. Image to text w/ vit-gpt2-image-captioning (246 MB)
12. Image classification w/ google/vit-base-patch16-224 (88 MB)
13. Zero-shot image classification w/ openai/clip-vit-base-patch16 (151 MB)
14. Object detection w/ facebook/detr-resnet-50 (43 MB)

Proper SCS MVC:
- Model helpers pure (format_result, wrap_text)
- Controller async via browser.aio.run + extensions.transformers
- View redrawAll pure

Data encoding/decoding confirmed from other extensions:
- fetch.py: window.fetch + JSON handling for JS objects vs Python dicts
- file_loader.py: Image() crossOrigin anonymous, canvas drawImage, getImageData, Array.from(Uint8ClampedArray)
- pyodide.py: postMessage JSON serialization, tensor truncation
Our extension uses same: JSON.stringify/parse bridge, Array.from for Float32Array, tensor truncation to 50 elements
"""

from scs import *
from browser import aio
from extensions.transformers import pipeline, clear_cache, ORIGINAL_TO_XENOVA

# ---------------------------------------------------------------------------
# Exact 14 tasks from screenshot - same order, same display names, same MB
# ---------------------------------------------------------------------------
TASKS = [
    {
        'display': 'Translation w/ t5-small (78 MB)',
        'id': 'translation',
        'label': 'Translation',
        'task': 'translation',
        'model_original': 't5-small',
        'model': 'Xenova/t5-small',
        'category': 'NLP',
        'color': rgb(0, 184, 148),
        'description': 'English to French translation',
        'example_input': 'translate English to French: Hello, how are you? I love machine learning.',
        'icon': '🌐'
    },
    {
        'display': 'Text generation w/ distilgpt2 (85 MB)',
        'id': 'textgen',
        'label': 'Text Gen',
        'task': 'text-generation',
        'model_original': 'distilgpt2',
        'model': 'Xenova/distilgpt2',
        'category': 'NLP',
        'color': rgb(253, 121, 168),
        'description': 'Continue text with distilgpt2',
        'example_input': 'Once upon a time, in a browser not so far away,',
        'icon': '✨'
    },
    {
        'display': 'Masked language modelling w/ bert-base-cased (110 MB)',
        'id': 'fillmask',
        'label': 'Masked LM',
        'task': 'fill-mask',
        'model_original': 'bert-base-cased',
        'model': 'Xenova/bert-base-cased',
        'category': 'NLP',
        'color': rgb(88, 101, 242),
        'description': 'Predict [MASK] token',
        'example_input': 'The goal of life is [MASK].',
        'icon': '🎭'
    },
    {
        'display': 'Text classification w/ bert-base-multilingual-uncased-sentiment (169 MB)',
        'id': 'sentiment',
        'label': 'Sentiment',
        'task': 'text-classification',
        'model_original': 'bert-base-multilingual-uncased-sentiment',
        'model': 'Xenova/bert-base-multilingual-uncased-sentiment',
        'category': 'NLP',
        'color': rgb(88, 101, 242),
        'description': 'Multilingual sentiment classification',
        'example_input': 'I love transformers.js! It runs AI directly in my browser, amazing!',
        'icon': '💬'
    },
    {
        'display': 'Token classification w/ Davlan/bert-base-multilingual-cased-ner-hrl (178 MB)',
        'id': 'ner',
        'label': 'NER',
        'task': 'token-classification',
        'model_original': 'Davlan/bert-base-multilingual-cased-ner-hrl',
        'model': 'Xenova/bert-base-multilingual-cased-ner-hrl',
        'category': 'NLP',
        'color': rgb(88, 101, 242),
        'description': 'NER - people, locations, orgs (hrl model)',
        'example_input': 'My name is Sarah and I live in London. I work at Hugging Face.',
        'icon': '🏷️'
    },
    {
        'display': 'Zero-shot classification w/ typeform/distilbert-base-uncased-mnli (68 MB)',
        'id': 'zero',
        'label': 'Zero-Shot',
        'task': 'zero-shot-classification',
        'model_original': 'typeform/distilbert-base-uncased-mnli',
        'model': 'Xenova/distilbert-base-uncased-mnli',
        'category': 'NLP',
        'color': rgb(253, 121, 168),
        'description': 'Classify without training',
        'example_input': 'I love building AI apps that run in the browser!',
        'candidate_labels': ['technology', 'sports', 'politics', 'art'],
        'icon': '🎯'
    },
    {
        'display': 'Question answering w/ distilbert-base-cased-distilled-squad (66 MB)',
        'id': 'qa',
        'label': 'Q&A',
        'task': 'question-answering',
        'model_original': 'distilbert-base-cased-distilled-squad',
        'model': 'Xenova/distilbert-base-cased-distilled-squad',
        'category': 'NLP',
        'color': rgb(88, 101, 242),
        'description': 'Answer from context',
        'context': 'Transformers.js is a JavaScript library that allows you to run Hugging Face Transformers directly in your browser. It uses ONNX Runtime to run models and supports tasks like text classification, translation, and image classification without needing a server.',
        'question': 'What does Transformers.js use to run models?',
        'example_input': 'Context + Question',
        'icon': '❓'
    },
    {
        'display': 'Summarization w/ distilbart-cnn-6-6 (284 MB)',
        'id': 'summ',
        'label': 'Summarize',
        'task': 'summarization',
        'model_original': 'distilbart-cnn-6-6',
        'model': 'Xenova/distilbart-cnn-6-6',
        'category': 'NLP',
        'color': rgb(88, 101, 242),
        'description': 'Summarize long text',
        'example_input': 'Transformers have revolutionized natural language processing. They were introduced in 2017 with the Attention Is All You Need paper. Since then, they have become the dominant architecture for NLP tasks. Models like BERT, GPT, and T5 have achieved state-of-the-art results on many benchmarks. Transformers.js brings this power to the browser, allowing developers to run these models client-side without server costs or privacy concerns.',
        'icon': '📝'
    },
    {
        'display': 'Code completion w/ Salesforce/codegen-350M-mono (369 MB)',
        'id': 'codegen',
        'label': 'CodeGen',
        'task': 'text-generation',
        'model_original': 'Salesforce/codegen-350M-mono',
        'model': 'Xenova/codegen-350M-mono',
        'category': 'Code',
        'color': rgb(162, 155, 254),
        'description': 'Code completion - Python',
        'example_input': 'def fibonacci(n):\n    if n <= 1:\n        return n\n    else:\n        return',
        'icon': '💻'
    },
    {
        'display': 'Speech to text w/ whisper-tiny.en (41 MB)',
        'id': 'asr',
        'label': 'ASR',
        'task': 'automatic-speech-recognition',
        'model_original': 'whisper-tiny.en',
        'model': 'Xenova/whisper-tiny.en',
        'category': 'Audio',
        'color': rgb(255, 118, 117),
        'description': 'Whisper tiny.en - JFK audio',
        'example_input': 'Audio: jfk.wav',
        'audio_url': 'https://huggingface.github.io/transformers.js/audio/jfk.wav',
        'icon': '🎙️'
    },
    {
        'display': 'Image to text w/ vit-gpt2-image-captioning (246 MB)',
        'id': 'caption',
        'label': 'Caption',
        'task': 'image-to-text',
        'model_original': 'vit-gpt2-image-captioning',
        'model': 'Xenova/vit-gpt2-image-captioning',
        'category': 'Vision',
        'color': rgb(255, 159, 67),
        'description': 'Caption image',
        'example_input': 'Image captioning',
        'image_url': 'https://huggingface.co/datasets/Xenova/transformers.js-docs/resolve/main/cats.jpg',
        'icon': '💭'
    },
    {
        'display': 'Image classification w/ google/vit-base-patch16-224 (88 MB)',
        'id': 'imgcls',
        'label': 'Img Classify',
        'task': 'image-classification',
        'model_original': 'google/vit-base-patch16-224',
        'model': 'Xenova/vit-base-patch16-224',
        'category': 'Vision',
        'color': rgb(255, 159, 67),
        'description': 'ImageNet classification',
        'example_input': 'Image classification',
        'image_url': 'https://huggingface.co/datasets/Xenova/transformers.js-docs/resolve/main/cats.jpg',
        'icon': '🖼️'
    },
    {
        'display': 'Zero-shot image classification w/ openai/clip-vit-base-patch16 (151 MB)',
        'id': 'zeroimg',
        'label': 'Zero-Shot Img',
        'task': 'zero-shot-image-classification',
        'model_original': 'openai/clip-vit-base-patch16',
        'model': 'Xenova/clip-vit-base-patch16',
        'category': 'Vision',
        'color': rgb(162, 155, 254),
        'description': 'CLIP zero-shot image classification',
        'example_input': 'Classify cat image',
        'image_url': 'https://huggingface.co/datasets/Xenova/transformers.js-docs/resolve/main/cats.jpg',
        'candidate_labels': ['a photo of cats', 'a photo of dogs', 'a photo of birds'],
        'icon': '🔍'
    },
    {
        'display': 'Object detection w/ facebook/detr-resnet-50 (43 MB)',
        'id': 'objdet',
        'label': 'Detection',
        'task': 'object-detection',
        'model_original': 'facebook/detr-resnet-50',
        'model': 'Xenova/detr-resnet-50',
        'category': 'Vision',
        'color': rgb(255, 159, 67),
        'description': 'Detect objects with boxes',
        'example_input': 'Object detection',
        'image_url': 'https://huggingface.co/datasets/Xenova/transformers.js-docs/resolve/main/cats.jpg',
        'icon': '📦'
    },
]

DEMO_IMAGES = [
    'https://huggingface.co/datasets/Xenova/transformers.js-docs/resolve/main/cats.jpg',
    'https://huggingface.co/datasets/Xenova/transformers.js-docs/resolve/main/tiger.jpg',
    'https://huggingface.co/datasets/Xenova/transformers.js-docs/resolve/main/coco.jpg',
]

# ---------------------------------------------------------------------------
# Model helpers - pure
# ---------------------------------------------------------------------------
def format_result(task_def, result):
    if result is None:
        return ["No result yet. Press SPACE to run."]
    t = task_def['task']
    lines = []
    try:
        if t == 'text-classification':
            if isinstance(result, list):
                for r in result[:4]:
                    label = r.get('label','?')
                    score = r.get('score',0)
                    lines.append(f"{label}: {score:.3f}")
        elif t == 'token-classification':
            if isinstance(result, list):
                for ent in result[:8]:
                    w = ent.get('word','')
                    e = ent.get('entity','') or ent.get('entity_group','')
                    s = ent.get('score',0)
                    lines.append(f"{w} -> {e} ({s:.2f})")
                if len(result) > 8:
                    lines.append(f"+ {len(result)-8} more...")
        elif t == 'question-answering':
            if isinstance(result, dict):
                lines.append(f"Answer: {result.get('answer','')}")
                lines.append(f"Score: {result.get('score',0):.3f}")
        elif t == 'fill-mask':
            if isinstance(result, list):
                for r in result[:5]:
                    seq = r.get('sequence','')
                    score = r.get('score',0)
                    if len(seq) > 75:
                        seq = seq[:72]+"..."
                    lines.append(f"{score:.3f} | {seq}")
        elif t in ('summarization','translation','image-to-text'):
            if isinstance(result, list) and result and isinstance(result[0], dict):
                d = result[0]
                text = d.get('summary_text') or d.get('translation_text') or d.get('generated_text') or str(d)
                for i in range(0, len(text), 68):
                    lines.append(text[i:i+68])
        elif t == 'text-generation':
            if isinstance(result, list) and result and isinstance(result[0], dict):
                text = result[0].get('generated_text','')
                for i in range(0, len(text), 68):
                    lines.append(text[i:i+68])
        elif t == 'zero-shot-classification':
            if isinstance(result, dict):
                labels = result.get('labels',[])
                scores = result.get('scores',[])
                for lb, sc in zip(labels[:5], scores[:5]):
                    lines.append(f"{lb}: {sc:.3f}")
        elif t == 'automatic-speech-recognition':
            if isinstance(result, dict):
                txt = result.get('text','')
                for i in range(0, len(txt), 68):
                    lines.append(txt[i:i+68])
            elif isinstance(result, list):
                lines.append(str(result[0].get('text','') if result else ''))
        elif t == 'image-classification':
            if isinstance(result, list):
                for r in result[:5]:
                    lines.append(f"{r.get('label','?')}: {r.get('score',0):.3f}")
        elif t == 'object-detection':
            if isinstance(result, list):
                for r in result[:6]:
                    lbl = r.get('label','obj')
                    sc = r.get('score',0)
                    lines.append(f"{lbl} {sc:.2f}")
                if len(result)==0:
                    lines.append("No objects detected")
        elif t == 'zero-shot-image-classification':
            if isinstance(result, list):
                for r in result[:5]:
                    lines.append(f"{r.get('label','?')}: {r.get('score',0):.3f}")
        else:
            txt = str(result)[:400]
            for i in range(0, len(txt), 68):
                lines.append(txt[i:i+68])
    except Exception as e:
        lines = [f"Format error: {e}", str(result)[:200]]
    return lines[:14]

def wrap_text(text, max_len=60):
    if not text:
        return []
    words = text.split(' ')
    lines = []
    cur = ""
    for w in words:
        if len(cur)+len(w)+1 <= max_len:
            cur = (cur+" "+w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
async def load_and_run(app):
    task_def = TASKS[app.selectedIdx]
    pipe_key = f"{task_def['task']}::{task_def['model']}"

    if pipe_key not in app.pipeCache:
        app.loading = True
        app.loadingMsg = f"Loading {task_def['label']}..."
        app.loadingDetail = f"{task_def['display']} - downloading..."
        try:
            pipe = await pipeline(task_def['task'], task_def['model'], dtype='q8')
            app.pipeCache[pipe_key] = pipe
        except Exception as e:
            app.resultError = f"Load failed: {e}"
            app.loading = False
            return
        app.loading = False

    pipe = app.pipeCache[pipe_key]
    app.loading = True
    app.loadingMsg = f"Running {task_def['label']}..."
    app.loadingDetail = "Inference via ONNX Runtime WASM"
    app.result = None
    app.resultError = None
    try:
        if task_def['task'] == 'question-answering':
            res = await pipe({'question': task_def['question'], 'context': task_def['context']})
        elif task_def['task'] in ('zero-shot-classification','zero-shot-image-classification'):
            inp = task_def['example_input'] if task_def['task']=='zero-shot-classification' else task_def.get('image_url', DEMO_IMAGES[app.imageIdx])
            if task_def['task']=='zero-shot-image-classification':
                inp = DEMO_IMAGES[app.imageIdx]
            res = await pipe(inp, candidate_labels=task_def['candidate_labels'])
        elif task_def['task'] in ('image-classification','object-detection','image-to-text'):
            img = DEMO_IMAGES[app.imageIdx]
            task_def['image_url'] = img
            res = await pipe(img)
        elif task_def['task'] == 'automatic-speech-recognition':
            res = await pipe(task_def['audio_url'])
        elif task_def['task'] == 'text-generation':
            if task_def['id'] == 'codegen':
                res = await pipe(task_def['example_input'], max_new_tokens=60, do_sample=False)
            else:
                res = await pipe(task_def['example_input'], max_new_tokens=40, do_sample=False)
        elif task_def['task'] == 'summarization':
            res = await pipe(task_def['example_input'], max_new_tokens=80, min_new_tokens=20)
        elif task_def['task'] == 'translation':
            res = await pipe(task_def['example_input'])
        else:
            res = await pipe(task_def['example_input'])
        app.result = res
        app.resultLines = format_result(task_def, res)
    except Exception as e:
        app.resultError = str(e)[:400]
        app.resultLines = [f"Error: {e}"]
    finally:
        app.loading = False

# ---------------------------------------------------------------------------
# SCS App
# ---------------------------------------------------------------------------
def onAppStart(app):
    app.width = 1120
    app.height = 780
    app.background = gradient(rgb(15, 17, 21), rgb(26, 29, 36), start='top')
    app.stepsPerSecond = 30

    app.tasks = TASKS
    app.selectedIdx = 0
    app.pipeCache = {}
    app.loading = False
    app.loadingMsg = "Ready"
    app.loadingDetail = "Press SPACE to run first model"
    app.result = None
    app.resultLines = ["Press SPACE to run model", "First run downloads from HF Hub (sizes in list)", "Cached afterwards via WASM"]
    app.resultError = None
    app.imageIdx = 0
    app.showHelp = False

    app.buttonW = 152
    app.buttonH = 26
    app.buttonGap = 5
    app.buttonsPerRow = 4
    app.buttonStartX = 18
    app.buttonStartY = 56

def onKeyPress(app, key):
    if key == ' ' or key == 'Enter':
        aio.run(load_and_run(app))
    elif key.lower() == 'r':
        aio.run(load_and_run(app))
    elif key.lower() == 'c':
        async def clear():
            await clear_cache()
            app.pipeCache = {}
            app.resultLines = ["Cache cleared"]
        aio.run(clear())
    elif key.lower() == 'h':
        app.showHelp = not app.showHelp
    elif key == 'Right' or key == 'd':
        app.selectedIdx = (app.selectedIdx + 1) % len(app.tasks)
        app.result = None
        app.resultLines = [f"Selected: {app.tasks[app.selectedIdx]['display']}", "Press SPACE"]
    elif key == 'Left' or key == 'a':
        app.selectedIdx = (app.selectedIdx - 1) % len(app.tasks)
        app.result = None
        app.resultLines = [f"Selected: {app.tasks[app.selectedIdx]['display']}", "Press SPACE"]
    elif key in '123456789':
        idx = int(key)-1
        if idx < len(app.tasks):
            app.selectedIdx = idx
            app.result = None
            app.resultLines = [f"Selected: {app.tasks[app.selectedIdx]['display']}", "Press SPACE"]
    elif key == '0':
        idx = 9
        app.selectedIdx = idx
    elif key.lower() == 'i':
        app.imageIdx = (app.imageIdx + 1) % len(DEMO_IMAGES)
        for td in app.tasks:
            if 'image_url' in td:
                td['image_url'] = DEMO_IMAGES[app.imageIdx]

def onMousePress(app, mx, my):
    for i, task_def in enumerate(app.tasks):
        row = i // app.buttonsPerRow
        col = i % app.buttonsPerRow
        bx = app.buttonStartX + col * (app.buttonW + app.buttonGap)
        by = app.buttonStartY + row * (app.buttonH + app.buttonGap)
        if bx <= mx <= bx + app.buttonW and by <= my <= by + app.buttonH:
            app.selectedIdx = i
            app.result = None
            app.resultLines = [f"Selected: {task_def['display']}", "Press SPACE to run"]
            return
    if 18 <= mx <= 138 and 710 <= my <= 745:
        aio.run(load_and_run(app))
        return
    if app.tasks[app.selectedIdx]['task'] in ('image-classification','object-detection','image-to-text','zero-shot-image-classification'):
        if 30 <= mx <= 540 and 300 <= my <= 600:
            app.imageIdx = (app.imageIdx + 1) % len(DEMO_IMAGES)
            for td in app.tasks:
                if 'image_url' in td:
                    td['image_url'] = DEMO_IMAGES[app.imageIdx]

def onStep(app):
    pass

def redrawAll(app):
    drawRect(0, 0, app.width, 44, fill=rgb(21, 23, 30))
    drawLabel("SCS x Transformers.js - 14 Models Exact from Screenshot - ONNX WASM in Browser",
              app.width//2, 15, fill=rgb(220, 220, 230), size=15, bold=True)
    drawLabel("SPACE=Run | Click task (14) | LEFT/RIGHT | C=Clear | I=Cycle images | H=Help",
              app.width//2, 31, fill=rgb(150, 150, 165), size=11)

    for i, td in enumerate(app.tasks):
        row = i // app.buttonsPerRow
        col = i % app.buttonsPerRow
        bx = app.buttonStartX + col * (app.buttonW + app.buttonGap)
        by = app.buttonStartY + row * (app.buttonH + app.buttonGap)
        isSel = (i == app.selectedIdx)
        if isSel:
            drawRect(bx, by, app.buttonW, app.buttonH, fill=td['color'], border=rgb(255,255,255), borderWidth=2, roundness=5)
            drawLabel(td['label'], bx+app.buttonW//2, by+app.buttonH//2, fill='white', size=10, bold=True)
        else:
            drawRect(bx, by, app.buttonW, app.buttonH, fill=rgb(45, 48, 60), border=td['color'], borderWidth=1, roundness=5)
            drawLabel(td['label'], bx+app.buttonW//2, by+app.buttonH//2, fill=rgb(210,210,220), size=9, bold=False)

    sel = app.tasks[app.selectedIdx]
    infoY = app.buttonStartY + 4* (app.buttonH + app.buttonGap) + 6
    drawRect(18, infoY, app.width-36, 38, fill=rgb(35, 38, 50), roundness=8, border=rgb(60,65,80), borderWidth=1)
    drawLabel(f"{sel['icon']}  {sel['display']}  |  {sel['description']}  |  Xenova: {sel['model']}",
              26, infoY+19, fill=rgb(200,200,210), size=11, align='left')

    leftX = 18
    leftY = infoY + 52
    leftW = (app.width - 56)//2
    rightX = leftX + leftW + 20
    panelH = 460

    drawRect(leftX, leftY, leftW, panelH, fill=rgb(28, 30, 40), border=rgb(60,65,80), borderWidth=1, roundness=10)
    drawLabel("INPUT", leftX+12, leftY+14, fill=rgb(130,130,150), size=11, align='left', bold=True)

    drawRect(rightX, leftY, leftW, panelH, fill=rgb(28, 30, 40), border=rgb(60,65,80), borderWidth=1, roundness=10)
    drawLabel("OUTPUT", rightX+12, leftY+14, fill=rgb(130,130,150), size=11, align='left', bold=True)
    drawLabel(f"Cache {len(app.pipeCache)}/14", rightX+leftW-12, leftY+14, fill=rgb(100,100,120), size=10, align='right')

    tx = leftX + 12
    ty = leftY + 32
    maxW = leftW - 24

    if sel['task'] == 'question-answering':
        drawLabel("Context:", tx, ty, fill=rgb(180,180,200), size=11, align='left', bold=True)
        ty += 14
        for line in wrap_text(sel['context'], 60):
            drawLabel(line, tx, ty, fill=rgb(220,220,230), size=11, align='left')
            ty += 14
            if ty > leftY+panelH-30: break
        ty += 8
        drawLabel(f"Q: {sel['question']}", tx, ty, fill=rgb(160,220,255), size=12, align='left', bold=True)
    elif sel['task'] in ('image-classification','object-detection','image-to-text','zero-shot-image-classification'):
        drawLabel(f"Image: {DEMO_IMAGES[app.imageIdx].split('/')[-1]} (click to cycle)", tx, ty, fill=rgb(150,150,170), size=10, align='left')
        ty += 14
        imgBoxY = ty
        imgBoxH = 240
        drawRect(tx, imgBoxY, maxW, imgBoxH, fill=rgb(20,20,25), border=rgb(80,80,100), borderWidth=1, roundness=6)
        drawLabel(f"{DEMO_IMAGES[app.imageIdx]}", tx+maxW//2, imgBoxY+imgBoxH//2-8, fill=rgb(100,100,120), size=9, align='center')
        drawLabel("Preview box - SCS Image() would load URL via file_loader", tx+maxW//2, imgBoxY+imgBoxH//2+10, fill=rgb(80,80,90), size=8, align='center')
        ty = imgBoxY + imgBoxH + 12
        if 'candidate_labels' in sel:
            drawLabel("Candidate labels:", tx, ty, fill=rgb(180,180,200), size=11, align='left', bold=True)
            ty += 14
            for lbl in sel['candidate_labels']:
                drawLabel(f" - {lbl}", tx, ty, fill=rgb(200,200,220), size=11, align='left')
                ty += 13
    elif sel['task'] == 'zero-shot-classification':
        drawLabel("Text:", tx, ty, fill=rgb(180,180,200), size=11, align='left', bold=True)
        ty += 14
        for line in wrap_text(sel['example_input'], 60):
            drawLabel(line, tx, ty, fill=rgb(220,220,230), size=11, align='left')
            ty += 14
        ty += 6
        drawLabel("Labels:", tx, ty, fill=rgb(180,180,200), size=11, align='left', bold=True)
        ty += 14
        for lbl in sel['candidate_labels']:
            drawLabel(f" - {lbl}", tx, ty, fill=rgb(200,200,220), size=11, align='left')
            ty += 13
    elif sel['task'] == 'automatic-speech-recognition':
        drawLabel(f"Audio: {sel['audio_url']}", tx, ty, fill=rgb(150,200,255), size=10, align='left')
        ty += 18
        drawLabel("JFK - 'Ask not what your country can do for you'", tx, ty, fill=rgb(200,200,210), size=11, align='left')
        ty += 14
        drawLabel("Whisper tiny.en 41 MB", tx, ty, fill=rgb(130,130,150), size=10, align='left')
    else:
        drawLabel("Text:", tx, ty, fill=rgb(180,180,200), size=11, align='left', bold=True)
        ty += 14
        for line in wrap_text(sel['example_input'], 60):
            if ty > leftY + panelH - 20: break
            drawLabel(line, tx, ty, fill=rgb(220,220,230), size=11, align='left')
            ty += 14

    otx = rightX + 12
    oty = leftY + 32
    if app.loading:
        drawLabel(app.loadingMsg, otx+ leftW//2 -12, oty+100, fill=rgb(255,220,100), size=15, bold=True, align='center')
        drawLabel(app.loadingDetail, otx+ leftW//2 -12, oty+122, fill=rgb(180,180,190), size=11, align='center')
        for i in range(3):
            drawCircle(otx + leftW//2 -20 + i*20, oty+150, 6, fill=rgb(100+i*30, 180, 255))
    else:
        if app.resultError:
            drawLabel("ERROR:", otx, oty, fill=rgb(255,100,100), size=12, bold=True, align='left')
            oty += 16
            for line in wrap_text(app.resultError, 60):
                drawLabel(line, otx, oty, fill=rgb(255,150,150), size=10, align='left')
                oty += 13
        else:
            if app.resultLines:
                for line in app.resultLines:
                    if oty > leftY + panelH - 20:
                        drawLabel("... truncated", otx, oty, fill=rgb(120,120,130), size=10, align='left')
                        break
                    drawLabel(line, otx, oty, fill=rgb(220,220,230), size=11, align='left')
                    oty += 15

    btnX, btnY, btnW, btnH = 18, 710, 130, 34
    drawRect(btnX, btnY, btnW, btnH, fill=rgb(88,101,242) if not app.loading else rgb(60,60,80), roundness=8, border=rgb(255,255,255), borderWidth=1)
    drawLabel("RUN (SPACE)" if not app.loading else "Loading...", btnX+btnW//2, btnY+btnH//2, fill='white', size=12, bold=True)

    drawRect(0, app.height-22, app.width, 22, fill=rgb(21,23,30))
    drawLabel(f"Task {app.selectedIdx+1}/14: {sel['display']} | Cache {len(app.pipeCache)} | Img {app.imageIdx+1}/{len(DEMO_IMAGES)}",
              12, app.height-11, fill=rgb(150,150,165), size=10, align='left')

    if app.showHelp:
        drawRect(app.width//2-260, app.height//2-190, 520, 380, fill=rgb(30,32,45), border=rgb(80,80,100), borderWidth=2, roundness=12)
        drawLabel("Help - Exact 14 Models from Screenshot", app.width//2, app.height//2-160, fill='white', size=14, bold=True)
        helpLines = [
            "All 14 options from screenshot included:",
            " Translation t5-small 78MB",
            " Text generation distilgpt2 85MB",
            " Masked LM bert-base-cased 110MB",
            " Text classification multilingual sentiment 169MB",
            " Token classification Davlan NER 178MB",
            " Zero-shot typeform mnli 68MB",
            " QA distilbert SQuAD 66MB",
            " Summarization distilbart 284MB",
            " Code completion codegen-350M 369MB",
            " ASR whisper-tiny.en 41MB",
            " Image to text vit-gpt2 246MB",
            " Image classification vit 88MB",
            " Zero-shot CLIP 151MB",
            " Object detection detr 43MB",
            "",
            "Encoding: JSON bridge, Array.from TypedArrays, tensor truncation",
            "Like file_loader (canvas+getImageData) and fetch (JSON handling)",
            "SPACE run, C clear, I cycle images, H close",
        ]
        hy = app.height//2 -130
        for line in helpLines:
            drawLabel(line, app.width//2, hy, fill=rgb(200,200,210), size=10, align='center')
            hy += 15
