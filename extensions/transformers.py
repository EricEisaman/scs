"""
extensions.transformers - SCS Extension wrapping transformers.js
=================================================================
Proper SCS extension (Model-only, browser-aligned, async)

Based on examination of existing SCS extensions:
- extensions/fetch.py: uses window.fetch, returns FetchResponse with async .json()/.text()/.blob()/.arrayBuffer(),
  handles JS objects vs Python dicts transparently via JSON serialization and dual backend (window.fetch primary, aio.fetch fallback)
- extensions/file_loader.py: loads images via Image() with crossOrigin='anonymous', draws to canvas,
  extracts RGBA via getImageData, converts Uint8ClampedArray -> Python list via Array.from, handles CORS
- extensions/pyodide.py: lazy Pyodide worker, serializes SciPy ops via postMessage, uses JSON for args/results,
  truncates large arrays for Brython safety

This extension follows same patterns:
- JS bootstrap via window.eval, defines window._scs* helpers (like fetch.py dual backend)
- JSON for Py<->JS bridge (like fetch and pyodide)
- TypedArray handling via Array.from (like file_loader)
- Tensor truncation to 50 elements (like pyodide worker result decoding)
- Pipeline cache in JS (window._scsTransformersCache) to avoid re-downloading
- Quantized q8 default for WASM performance

Install:
  extensions/transformers.py
  extensions.py shim must inject sys.modules['extensions.transformers']

Usage:
  from browser import aio
  from extensions.transformers import pipeline

  async def run(app):
      pipe = await pipeline('text-classification', 'Xenova/distilbert-base-uncased-finetuned-sst-2-english')
      app.result = await pipe('I love SCS!')

  def onAppStart(app):
      aio.run(run(app))
"""

from browser import window
import json

# ---------------------------------------------------------------------------
# JS bootstrap - Brython-safe (no \n escapes, real newlines)
# ---------------------------------------------------------------------------
_JS_BOOTSTRAP = """
(function(){
  if (window._scsTransformersSetup) return;
  window._scsTransformersSetup = true;
  window._scsTransformersCache = {};
  window._scsTransformersModule = null;
  window._scsTransformersProgress = {status: 'idle', file: '', loaded: 0, total: 0, progress: 0};

  window._scsEnsureTransformers = async () => {
    if (window._scsTransformersModule) return window._scsTransformersModule;
    try {
      console.info('[scs transformers] importing @huggingface/transformers@3.8.1');
      const mod = await import('https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1');
      mod.env.allowLocalModels = false;
      mod.env.allowRemoteModels = true;
      // WASM assets via CDN (mirrors fetch.py dual backend pattern)
      mod.env.backends.onnx.wasm.wasmPaths = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/dist/';
      window._scsTransformersModule = mod;
      console.info('[scs transformers] JS module imported; remote models enabled');
      return mod;
    } catch(e) {
      console.error('[scs transformers] JS module import failed', e);
      throw e;
    }
  };

  window._scsGetPipeline = async (task, modelId, optsJson) => {
    let opts = {};
    if (optsJson) {
      try { opts = JSON.parse(optsJson); } catch(e) { opts = {}; }
    }
    // Default to quantized q8 for browser (like pyodide default optimization)
    if (opts.dtype === undefined) {
      opts.dtype = 'q8';
    }
    const key = task + '::' + (modelId || 'default') + '::' + JSON.stringify(opts);
    if (window._scsTransformersCache[key]) {
      console.info('[scs transformers] using cached pipeline', {task, modelId});
      window._scsTransformersProgress = {status: 'cached', file: '', loaded: 0, total: 0, progress: 100};
      return window._scsTransformersCache[key];
    }
    console.info('[scs transformers] pipeline requested', {task, modelId, dtype: opts.dtype});
    window._scsTransformersProgress = {status: 'loading', file: '', loaded: 0, total: 0, progress: 0};
    let lastProgressKey = '';
    let lastProgressBucket = -1;
    opts.progress_callback = (event) => {
      const update = event || {};
      const status = String(update.status || 'loading');
      const file = String(update.file || update.name || '');
      const progress = Number(update.progress) || 0;
      window._scsTransformersProgress = {
        status,
        file,
        loaded: Number(update.loaded) || 0,
        total: Number(update.total) || 0,
        progress
      };
      const bucket = Math.floor(progress / 25);
      if (file !== lastProgressKey || bucket !== lastProgressBucket || status !== 'progress') {
        console.info('[scs transformers] model progress', {status, file, progress});
        lastProgressKey = file;
        lastProgressBucket = bucket;
      }
    };
    try {
      const mod = await window._scsEnsureTransformers();
      console.info('[scs transformers] calling Transformers.js pipeline; model fetch should begin', {task, modelId});
      const pipe = await mod.pipeline(task, modelId || undefined, opts);
      window._scsTransformersCache[key] = pipe;
      console.info('[scs transformers] pipeline loaded', {task, modelId});
      return pipe;
    } catch(e) {
      window._scsTransformersProgress.status = 'error';
      console.error('[scs transformers] pipeline load failed', {task, modelId, error: e});
      throw e;
    }
  };

  // Handles file_loader-style encoding: supports (input), (input, labels), (input, options), (input, labels, options)
  window._scsRunPipe = async (pipe, inputJson, secondJson, thirdJson) => {
    let input;
    try { input = JSON.parse(inputJson); } catch(e) { input = inputJson; }

    let second;
    try { second = secondJson ? JSON.parse(secondJson) : undefined; } catch(e) { second = secondJson; }

    let third;
    try { third = thirdJson ? JSON.parse(thirdJson) : undefined; } catch(e) { third = thirdJson; }

    let result;
    // Dispatch based on presence of labels (array) vs options (object)
    if (second !== undefined && third !== undefined) {
      result = await pipe(input, second, third);
    } else if (second !== undefined) {
      // second could be labels array or options object - pipeline handles both
      result = await pipe(input, second);
    } else {
      result = await pipe(input);
    }

    // JSON serialization with TypedArray / Tensor handling (like file_loader + pyodide)
    const replacer = (k, v) => {
      if (v && typeof v === 'object') {
        if (v.data && v.dims && v.data.length !== undefined) {
          const arr = Array.from(v.data);
          const truncated = arr.length > 50;
          return { dims: v.dims, data: truncated ? arr.slice(0,50) : arr, truncated: truncated, type: 'tensor' };
        }
        if (v instanceof Float32Array || v instanceof Uint8Array || v instanceof Uint8ClampedArray || v instanceof Int32Array) {
          const arr = Array.from(v);
          return arr.length > 100 ? arr.slice(0,100) : arr;
        }
      }
      return v;
    };
    try {
      return JSON.stringify(result, replacer);
    } catch(e) {
      return JSON.stringify({ error: String(e), raw: String(result).slice(0,500) });
    }
  };

  window._scsClearCache = () => {
    window._scsTransformersCache = {};
  };

  window._scsListPipelines = () => {
    return JSON.stringify(Object.keys(window._scsTransformersCache));
  };

  window._scsGetProgress = () => JSON.stringify(window._scsTransformersProgress);
})();
"""

_initialized = False

def _ensure_js():
    global _initialized
    if _initialized:
        return
    if getattr(window, '_scsTransformersSetup', None):
        _initialized = True
        return
    window.eval(_JS_BOOTSTRAP)
    _initialized = True

# ---------------------------------------------------------------------------
# Model ID normalization - maps original HF names (from screenshot) to Xenova ONNX
# ---------------------------------------------------------------------------
ORIGINAL_TO_XENOVA = {
    "t5-small": "Xenova/t5-small",
    "distilgpt2": "Xenova/distilgpt2",
    "bert-base-cased": "Xenova/bert-base-cased",
    "bert-base-multilingual-uncased-sentiment": "Xenova/bert-base-multilingual-uncased-sentiment",
    "Davlan/bert-base-multilingual-cased-ner-hrl": "Xenova/bert-base-multilingual-cased-ner-hrl",
    "typeform/distilbert-base-uncased-mnli": "Xenova/distilbert-base-uncased-mnli",
    "distilbert-base-cased-distilled-squad": "Xenova/distilbert-base-cased-distilled-squad",
    "distilbart-cnn-6-6": "Xenova/distilbart-cnn-6-6",
    "Salesforce/codegen-350M-mono": "Xenova/codegen-350M-mono",
    "whisper-tiny.en": "Xenova/whisper-tiny.en",
    "vit-gpt2-image-captioning": "Xenova/vit-gpt2-image-captioning",
    "google/vit-base-patch16-224": "Xenova/vit-base-patch16-224",
    "openai/clip-vit-base-patch16": "Xenova/clip-vit-base-patch16",
    "facebook/detr-resnet-50": "Xenova/detr-resnet-50",
    # also support explicit Xenova names already
}

def _normalize_model_id(model_id):
    if not model_id:
        return None
    # If already Xenova, keep
    if model_id.startswith("Xenova/"):
        return model_id
    # Direct mapping
    if model_id in ORIGINAL_TO_XENOVA:
        return ORIGINAL_TO_XENOVA[model_id]
    # If model contains slash, try Xenova + last part
    if "/" in model_id:
        last = model_id.split("/")[-1]
        # Heuristic: Xenova/{last}
        candidate = f"Xenova/{last}"
        return candidate
    # Bare name like t5-small etc already handled, fallback to Xenova/{id}
    return f"Xenova/{model_id}"

# All 14 tasks from screenshot - exact order
SCREENSHOT_TASKS = [
    "translation",
    "text-generation",
    "fill-mask",
    "text-classification",
    "token-classification",
    "zero-shot-classification",
    "question-answering",
    "summarization",
    "text-generation",  # code completion uses text-generation pipeline with codegen model
    "automatic-speech-recognition",
    "image-to-text",
    "image-classification",
    "zero-shot-image-classification",
    "object-detection",
]

DEFAULT_MODELS = {
    'translation': 'Xenova/t5-small',
    'text-generation': 'Xenova/distilgpt2',
    'fill-mask': 'Xenova/bert-base-cased',
    'text-classification': 'Xenova/bert-base-multilingual-uncased-sentiment',
    'token-classification': 'Xenova/bert-base-multilingual-cased-ner-hrl',
    'zero-shot-classification': 'Xenova/distilbert-base-uncased-mnli',
    'question-answering': 'Xenova/distilbert-base-cased-distilled-squad',
    'summarization': 'Xenova/distilbart-cnn-6-6',
    'code-completion': 'Xenova/codegen-350M-mono',
    'automatic-speech-recognition': 'Xenova/whisper-tiny.en',
    'image-to-text': 'Xenova/vit-gpt2-image-captioning',
    'image-classification': 'Xenova/vit-base-patch16-224',
    'zero-shot-image-classification': 'Xenova/clip-vit-base-patch16',
    'object-detection': 'Xenova/detr-resnet-50',
}

# For backward compat
ALL_TASKS = list(set(SCREENSHOT_TASKS + list(DEFAULT_MODELS.keys())))

class TransformersPipeline:
    """
    Wraps JS transformers.js pipeline.
    Handles data encoding/decoding like other SCS extensions:
    - Inputs: Python str/dict/list -> JSON.stringify in JS (file_loader pattern)
    - Outputs: JS object -> JSON.stringify with TypedArray handling -> json.loads in Python (pyodide pattern)
    - Candidate labels for zero-shot passed as second arg (separate JSON)
    """
    def __init__(self, js_pipe, task, model_id=None, options=None):
        self._js_pipe = js_pipe
        self.task = task
        self.model_id = model_id
        self.options = options or {}

    async def __call__(self, inputs, candidate_labels=None, **run_options):
        # Support candidate_labels as kwarg (fetch.py transparent handling)
        if candidate_labels is None and 'candidate_labels' in run_options:
            candidate_labels = run_options.pop('candidate_labels')

        input_json = json.dumps(inputs)

        # second arg is labels if provided
        second_json = json.dumps(candidate_labels) if candidate_labels is not None else None

        # third arg is options if any
        opts_json = json.dumps(run_options) if run_options else None

        # If only options and no labels, put options as second
        if second_json is None and opts_json is not None:
            result_json_str = await window._scsRunPipe(self._js_pipe, input_json, opts_json, None)
        else:
            result_json_str = await window._scsRunPipe(self._js_pipe, input_json, second_json, opts_json)

        result_json_str = str(result_json_str)
        try:
            return json.loads(result_json_str)
        except Exception:
            return result_json_str

    def __repr__(self):
        return f"TransformersPipeline(task={self.task!r}, model={self.model_id!r})"

async def ensure_transformers():
    _ensure_js()
    mod = await window._scsEnsureTransformers()
    return mod

async def pipeline(task, model=None, **options):
    """
    Create pipeline, normalizing model ID to Xenova ONNX version.
    Mirrors transformers.js pipeline(task, model, options) but async and cached.

    Encoding:
      - model ID normalized via ORIGINAL_TO_XENOVA (like file_loader normalizes URLs)
      - options JSON-serialized (like fetch.py handles headers/body)
    Decoding:
      - result JSON-serialized in JS with Array.from for TypedArrays (file_loader)
      - truncated tensors (pyodide)
      - parsed via json.loads in Python
    """
    _ensure_js()
    if task == 'sentiment-analysis':
        task = 'text-classification'
    if task == 'ner':
        task = 'token-classification'
    if task == 'code-completion':
        task = 'text-generation'

    normalized_model = _normalize_model_id(model) if model else None

    opts_json = json.dumps(options) if options else None
    js_pipe = await window._scsGetPipeline(task, normalized_model, opts_json)
    return TransformersPipeline(js_pipe, task, normalized_model, options)

async def clear_cache():
    _ensure_js()
    window.eval('window._scsClearCache && window._scsClearCache()')

async def list_cached_pipelines():
    _ensure_js()
    try:
        js_str = window._scsListPipelines()
        return json.loads(str(js_str))
    except:
        return []

def get_download_progress():
    _ensure_js()
    try:
        return json.loads(str(window._scsGetProgress()))
    except Exception:
        return {}

async def configure_env(**kwargs):
    _ensure_js()
    mod = await window._scsEnsureTransformers()
    for k, v in kwargs.items():
        js_code = f"window._scsTransformersModule.env.{k} = {json.dumps(v)}"
        window.eval(js_code)
    return mod.env if hasattr(mod, 'env') else None

__all__ = [
    'pipeline',
    'TransformersPipeline',
    'ensure_transformers',
    'clear_cache',
    'list_cached_pipelines',
    'get_download_progress',
    'configure_env',
    'DEFAULT_MODELS',
    'ORIGINAL_TO_XENOVA',
    'SCREENSHOT_TASKS',
    'ALL_TASKS',
]
