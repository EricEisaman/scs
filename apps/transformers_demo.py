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
from browser import aio, document, window
from extensions.transformers import pipeline, clear_cache, get_download_progress, ORIGINAL_TO_XENOVA
from extensions.ui import Button, ImageInput, TextArea

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
        return ["No result yet. Select a model and press Generate."]
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

def _input_field_key(task_def):
    task = task_def['task']
    if task == 'question-answering':
        return 'question'
    if task == 'automatic-speech-recognition':
        return 'audio_url'
    if task in ('image-to-text', 'image-classification', 'zero-shot-image-classification', 'object-detection'):
        return 'image_url'
    return 'example_input'

def _viewport_canvas_width():
    try:
        viewport_width = int(window.innerWidth)
    except Exception:
        viewport_width = 1132
    return max(320, min(1100, viewport_width - 32))

def _task_grid_rows(app):
    return (len(app.tasks) + app.buttonsPerRow - 1) // app.buttonsPerRow

def _layout_dom_controls(app):
    canvas = document['cmu-canvas']
    container = document['canvas-container']
    canvas.width = app.width
    canvas.height = app.height
    canvas.style.width = f'{app.width}px'
    canvas.style.height = f'{app.height}px'
    container.style.width = f'{app.width}px'
    container.style.height = f'{app.height}px'
    app.generateButtonX = app.width - 18 - app.generateButtonW
    app.generateControl.set_bounds(app.generateButtonX, app.generateButtonY, app.generateButtonW, app.generateButtonH)
    _sync_input_editor(app)
    try:
        print(f"[transformers demo] canvas layout: app={app.width}x{app.height} canvas={canvas.width}x{canvas.height} container={container.getBoundingClientRect().width:.1f}px")
    except Exception as error:
        print(f"[transformers demo] canvas layout measurement failed: {error}")

def _sync_input_editor(app):
    task_def = app.tasks[app.selectedIdx]
    field = _input_field_key(task_def)
    editor_value = task_def.get(field, '')
    is_image = field == 'image_url'
    if is_image and task_def.get('image_file_name'):
        editor_value = task_def['image_file_name']
    app.inputEditor.value = editor_value
    if is_image:
        app.imageInput.show()
        app.imageInput.set_source(task_def.get(field, ''))
    else:
        app.imageInput.hide()
    left_y = app.buttonStartY + _task_grid_rows(app) * (app.buttonH + app.buttonGap) + 6 + 52
    left_w = (app.width - 56) // 2
    app.imageInput.set_bounds(30, left_y + 151, left_w - 24, 180)
    if task_def['task'] == 'question-answering':
        context_lines = len(wrap_text(task_def['context'], 60))
        top = left_y + 67 + 14 * context_lines
        height = 48
        placeholder = 'Type a question'
    elif task_def['task'] == 'zero-shot-classification':
        top, height = left_y + 48, 100
        placeholder = 'Enter text to classify'
    elif task_def['task'] in ('image-to-text', 'image-classification', 'zero-shot-image-classification', 'object-detection'):
        top, height = left_y + 48, 46
        placeholder = 'Paste an image URL'
    elif task_def['task'] == 'automatic-speech-recognition':
        top, height = left_y + 48, 46
        placeholder = 'Paste an audio URL'
    else:
        top, height = left_y + 48, 350
        placeholder = 'Type or paste input text'
    app.inputEditor.placeholder = placeholder
    app.inputEditor.set_bounds(30, top + 45, left_w - 24, height)

def _store_input_editor(app, event=None):
    task_def = app.tasks[app.selectedIdx]
    field = _input_field_key(task_def)
    task_def[field] = app.inputEditor.value
    if field == 'image_url':
        task_def.pop('image_file_name', None)
        app.imageInput.set_source(task_def[field])

def _store_selected_image(app, source, file_name):
    task_def = app.tasks[app.selectedIdx]
    task_def['image_url'] = source
    task_def['image_file_name'] = file_name
    app.inputEditor.value = file_name

# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
async def load_and_run(app):
    task_def = TASKS[app.selectedIdx]
    pipe_key = f"{task_def['task']}::{task_def['model']}"
    print(f"[transformers demo] controller entered: task={task_def['task']} model={task_def['model']}")

    if pipe_key not in app.pipeCache:
        app.loading = True
        app.loadingStage = 'model'
        app.loadingPercent = 0
        app.loadingMsg = f"Loading {task_def['label']}..."
        app.loadingDetail = f"Preparing {task_def['model']}"
        try:
            print(f"[transformers demo] calling pipeline(): task={task_def['task']} model={task_def['model']} dtype=q8")
            pipe = await pipeline(task_def['task'], task_def['model'], dtype='q8')
            app.pipeCache[pipe_key] = pipe
            print(f"[transformers demo] pipeline ready: {pipe_key}")
        except Exception as e:
            print(f"[transformers demo] model load failed: {type(e).__name__}: {e}")
            app.resultError = f"Load failed: {e}"
            app.loading = False
            app.loadingStage = 'idle'
            return
        app.loading = False

    pipe = app.pipeCache[pipe_key]
    app.loading = True
    app.loadingStage = 'inference'
    app.loadingMsg = f"Running {task_def['label']}..."
    app.loadingDetail = "Inference via ONNX Runtime WASM"
    app.result = None
    app.resultError = None
    try:
        if task_def['task'] == 'question-answering':
            res = await pipe({'question': task_def['question'], 'context': task_def['context']})
        elif task_def['task'] in ('zero-shot-classification','zero-shot-image-classification'):
            inp = task_def['example_input'] if task_def['task']=='zero-shot-classification' else task_def.get('image_url', DEMO_IMAGES[app.imageIdx])
            res = await pipe(inp, candidate_labels=task_def['candidate_labels'])
        elif task_def['task'] in ('image-classification','object-detection','image-to-text'):
            img = task_def.get('image_url') or DEMO_IMAGES[app.imageIdx]
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
        app.generatePending = False
        print(f"[transformers demo] inference complete: task={task_def['task']}")
    except Exception as e:
        print(f"[transformers demo] inference failed: {type(e).__name__}: {e}")
        app.resultError = str(e)[:400]
        app.resultLines = [f"Error: {e}"]
    finally:
        app.loading = False
        app.loadingStage = 'idle'

def start_generate(app):
    if app.loading:
        print("[transformers demo] Generate ignored: another run is already active")
        return
    task_def = TASKS[app.selectedIdx]
    pipe_key = f"{task_def['task']}::{task_def['model']}"
    print(f"[transformers demo] Generate requested: task={task_def['task']} model={task_def['model']}")
    app.loading = True
    app.loadingStage = 'inference' if pipe_key in app.pipeCache else 'model'
    app.loadingPercent = 0
    app.generatePending = True
    app.loadingMsg = f"Loading {task_def['label']}..." if app.loadingStage == 'model' else f"Running {task_def['label']}..."
    app.loadingDetail = f"Preparing {task_def['model']}" if app.loadingStage == 'model' else "Starting inference..."
    app.resultError = None
    try:
        aio.run(load_and_run(app))
        print("[transformers demo] aio.run accepted controller coroutine")
    except Exception as e:
        print(f"[transformers demo] aio.run failed: {type(e).__name__}: {e}")
        app.loading = False
        app.loadingStage = 'idle'
        app.resultError = f"Could not start generation: {e}"

# ---------------------------------------------------------------------------
# SCS App
# ---------------------------------------------------------------------------
def onAppStart(app):
    app.width = _viewport_canvas_width()
    app.height = 780
    app.background = gradient(rgb(15, 17, 21), rgb(26, 29, 36), start='top')
    app.stepsPerSecond = 30

    app.tasks = TASKS
    app.selectedIdx = 0
    app.pipeCache = {}
    app.loading = False
    app.loadingMsg = "Ready"
    app.loadingDetail = "Select a model, then press Generate"
    app.loadingStage = 'idle'
    app.loadingPercent = 0
    app.result = None
    app.generatePending = False
    app.resultLines = ["Select a model, then press Generate", "First run downloads from HF Hub", "Model is cached for later runs"]
    app.resultError = None
    app.imageIdx = 0
    app.showHelp = False

    app.buttonW = 152
    app.buttonH = 26
    app.buttonGap = 5
    app.buttonsPerRow = 4
    app.buttonStartX = 18
    app.buttonStartY = 56
    app.buttonsPerRow = max(1, min(4, (app.width - 31) // (app.buttonW + app.buttonGap)))
    app.generateButtonW = 130
    app.generateButtonH = 34
    app.generateButtonX = app.width - 18 - app.generateButtonW
    app.generateButtonY = 5
    app.generatePending = False

    container = document['canvas-container']
    container.style.position = 'relative'
    app.inputEditor = TextArea(container, 'transformers-demo-input', aria_label='Model input')
    app.inputEditor.bind('input', lambda event: _store_input_editor(app, event))
    app.imageInput = ImageInput(
        container,
        'transformers-demo-image-input',
        on_change=lambda source, file_name: _store_selected_image(app, source, file_name),
    )
    _sync_input_editor(app)

    app.generateControl = Button(container, 'transformers-demo-generate', 'Generate', aria_label='Generate with selected model')
    _layout_dom_controls(app)
    app.generateControl.bind('click', lambda event: start_generate(app))

    def resize_to_viewport(event):
        width = _viewport_canvas_width()
        if width == app.width:
            return
        app.width = width
        app.buttonsPerRow = max(1, min(4, (app.width - 31) // (app.buttonW + app.buttonGap)))
        _layout_dom_controls(app)
    window.bind('resize', resize_to_viewport)

def onKeyPress(app, key):
    try:
        if document.activeElement.id == app.inputEditor.element.id:
            return
    except Exception:
        pass
    if key.lower() == 'enter':
        start_generate(app)
    elif key.lower() == 'r':
        start_generate(app)
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
        _sync_input_editor(app)
        app.result = None
        app.generatePending = False
        app.resultLines = [f"Selected: {app.tasks[app.selectedIdx]['display']}", "Press Generate"]
    elif key == 'Left' or key == 'a':
        app.selectedIdx = (app.selectedIdx - 1) % len(app.tasks)
        _sync_input_editor(app)
        app.result = None
        app.generatePending = False
        app.resultLines = [f"Selected: {app.tasks[app.selectedIdx]['display']}", "Press Generate"]
    elif key in '123456789':
        idx = int(key)-1
        if idx < len(app.tasks):
            app.selectedIdx = idx
            _sync_input_editor(app)
            app.result = None
            app.generatePending = False
            app.resultLines = [f"Selected: {app.tasks[app.selectedIdx]['display']}", "Press Generate"]
    elif key == '0':
        idx = 9
        app.selectedIdx = idx
        _sync_input_editor(app)
        app.result = None
        app.generatePending = False
        app.resultLines = [f"Selected: {app.tasks[idx]['display']}", "Press Generate"]
    elif key.lower() == 'i':
        app.imageIdx = (app.imageIdx + 1) % len(DEMO_IMAGES)
        for td in app.tasks:
            if 'image_url' in td:
                td['image_url'] = DEMO_IMAGES[app.imageIdx]
        _sync_input_editor(app)

def onMousePress(app, mx, my):
    for i, task_def in enumerate(app.tasks):
        row = i // app.buttonsPerRow
        col = i % app.buttonsPerRow
        bx = app.buttonStartX + col * (app.buttonW + app.buttonGap)
        by = app.buttonStartY + row * (app.buttonH + app.buttonGap)
        if bx <= mx <= bx + app.buttonW and by <= my <= by + app.buttonH:
            app.selectedIdx = i
            _sync_input_editor(app)
            app.result = None
            app.generatePending = False
            app.resultLines = [f"Selected: {task_def['display']}", "Press Generate"]
            return
    if app.tasks[app.selectedIdx]['task'] in ('image-classification','object-detection','image-to-text','zero-shot-image-classification'):
        if 30 <= mx <= 540 and 300 <= my <= 600:
            app.imageIdx = (app.imageIdx + 1) % len(DEMO_IMAGES)
            for td in app.tasks:
                if 'image_url' in td:
                    td['image_url'] = DEMO_IMAGES[app.imageIdx]
            _sync_input_editor(app)

def onStep(app):
    if app.loading and app.loadingStage == 'model':
        progress = get_download_progress()
        loaded = float(progress.get('loaded', 0) or 0)
        total = float(progress.get('total', 0) or 0)
        percent = float(progress.get('progress', 0) or 0)
        if percent == 0 and total > 0:
            percent = loaded / total * 100
        app.loadingPercent = max(0, min(100, percent))
        filename = str(progress.get('file') or progress.get('name') or app.tasks[app.selectedIdx]['model'])
        filename = filename.rsplit('/', 1)[-1]
        if total > 0:
            app.loadingDetail = f"{filename}  {loaded / 1048576:.1f} / {total / 1048576:.1f} MB"
        else:
            app.loadingDetail = filename

def redrawAll(app):
    drawRect(0, 0, app.width, 44, fill=rgb(21, 23, 30))
    drawLabel("SCS x Transformers.js - 14 Models Exact from Screenshot - ONNX WASM in Browser",
              18, 15, fill=rgb(220, 220, 230), size=15, bold=True, align='left')
    drawLabel("Click Generate to run | Select task (14) | LEFT/RIGHT | C=Clear | I=Cycle images | H=Help",
              18, 31, fill=rgb(150, 150, 165), size=11, align='left')

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
    infoY = app.buttonStartY + _task_grid_rows(app) * (app.buttonH + app.buttonGap) + 6
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
    drawLabel(f"Cache {len(app.pipeCache)}/14", rightX+88, leftY+14, fill=rgb(100,100,120), size=10, align='left')

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
        drawLabel("Question (editable):", tx, ty, fill=rgb(160,220,255), size=12, align='left', bold=True)
    elif sel['task'] in ('image-classification','object-detection','image-to-text','zero-shot-image-classification'):
        image_url = sel.get('image_url') or DEMO_IMAGES[app.imageIdx]
        imgBoxY = leftY + 151
        imgBoxH = 180
        ty = imgBoxY + imgBoxH + 12
        if 'candidate_labels' in sel:
            drawLabel("Candidate labels:", tx, ty, fill=rgb(180,180,200), size=11, align='left', bold=True)
            ty += 14
            for lbl in sel['candidate_labels']:
                drawLabel(f" - {lbl}", tx, ty, fill=rgb(200,200,220), size=11, align='left')
                ty += 13
    elif sel['task'] == 'zero-shot-classification':
        ty = leftY + 48 + 153
        drawLabel("Labels:", tx, ty, fill=rgb(180,180,200), size=11, align='left', bold=True)
        ty += 14
        for lbl in sel['candidate_labels']:
            drawLabel(f" - {lbl}", tx, ty, fill=rgb(200,200,220), size=11, align='left')
            ty += 13
    elif sel['task'] == 'automatic-speech-recognition':
        ty = leftY + 201
        drawLabel("JFK - 'Ask not what your country can do for you'", tx, ty, fill=rgb(200,200,210), size=11, align='left')
        ty += 14
        drawLabel("Whisper tiny.en 41 MB", tx, ty, fill=rgb(130,130,150), size=10, align='left')
    else:
        pass

    otx = rightX + 12
    oty = leftY + 32
    if app.loading:
        drawLabel(app.loadingMsg, otx+ leftW//2 -12, oty+100, fill=rgb(255,220,100), size=15, bold=True, align='center')
        drawLabel(app.loadingDetail, otx+ leftW//2 -12, oty+122, fill=rgb(180,180,190), size=11, align='center')
        if app.loadingStage == 'model':
            progressX = otx + 18
            progressY = oty + 148
            progressW = leftW - 60
            drawRect(progressX, progressY, progressW, 12, fill=rgb(45,48,60), roundness=5)
            if app.loadingPercent > 0:
                drawRect(progressX, progressY, progressW * app.loadingPercent / 100, 12, fill=rgb(0,184,148), roundness=5)
            drawLabel(f"{app.loadingPercent:.0f}%", progressX+progressW//2, progressY+28, fill=rgb(200,220,220), size=10)
        else:
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

    button_color = 'rgb(130,150,176)' if app.generatePending else 'rgb(44,130,242)'
    button_text = "Generating..." if app.loading else "Generate"
    if app.generateControl.color != button_color:
        app.generateControl.color = button_color
    if app.generateControl.text != button_text:
        app.generateControl.text = button_text

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
            "Generate runs selected model; C clear, I cycle images, H close",
        ]
        hy = app.height//2 -130
        for line in helpLines:
            drawLabel(line, app.width//2, hy, fill=rgb(200,200,210), size=10, align='center')
            hy += 15

runApp(width=1100, height=780)
