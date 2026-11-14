// scs.js - SCS from npm / CDN. Thin JS only.
// No loop, no events, no renderer, no shape drawing here.
// All of that is baked into the Python package (scs_entrypoint.py).
// Users just import from npm or load from CDN:
//
//   <script src="https://cdn.jsdelivr.net/npm/scs-graphics@3.0.0/scs.js"></script>
//   <canvas id="canvas" data-app="apps/app.py"></canvas>
//   <script>SCS.create({ canvas: '#canvas' })</script>
//
// Or top level: point to a valid app:
//   SCS.create({ app: 'myapp.py' })
//   SCS.create({ code: 'from scs import *\n...\nrunApp()' })
//
// Or sandbox: just enter app code:
//   SCS.create({ sandbox: '#code-input' })

(function (global) {
  if (global.SCS && global.SCS.__scs_js) return;
  var BRYTHON_JS = 'https://cdn.jsdelivr.net/npm/brython@3.11.3/brython.min.js';
  var BRYTHON_STDLIB = 'https://cdn.jsdelivr.net/npm/brython@3.11.3/brython_stdlib.js';

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error('Failed to load ' + src)); };
      document.head.appendChild(s);
    });
  }

  function ensureBrython() {
    if (global.brython) return Promise.resolve();
    return loadScript(BRYTHON_JS).then(function () { return loadScript(BRYTHON_STDLIB); });
  }

  function create(opts) {
    opts = opts || {};
    // Top level: point to a valid app. One pointer, no config suffering.
    // opts.app: 'myapp.py' | 'apps/myapp.py' | 'https://.../myapp.py'
    // opts.code: raw CMU-style Python code (sandbox: just enter app code)
    // opts.canvas: selector or element, default '#canvas'
    // opts.hud: 'texture' | 'html' | 'auto' | false, default 'texture' (HUD/2D)
    // opts.renderer: 'auto' | '2d' | 'webgl2' | 'webgpu'
    global.SCS_CONFIG = global.SCS_CONFIG || {};
    if (opts.app) global.SCS_CONFIG.app = opts.app;
    if (opts.code) global.SCS_CONFIG.code = opts.code;
    if (opts.renderer) global.SCS_CONFIG.renderer = opts.renderer;
    if (opts.hud !== undefined) global.SCS_CONFIG.hud = opts.hud;
    if (opts.appBase) global.SCS_CONFIG.appBase = opts.appBase;

    var canvasEl = null;
    if (opts.canvas) {
      canvasEl = typeof opts.canvas === 'string' ? document.querySelector(opts.canvas) : opts.canvas;
    } else {
      canvasEl = document.querySelector('#canvas') || document.querySelector('#cmu-canvas') || document.querySelector('canvas');
    }
    if (canvasEl && opts.app && !canvasEl.getAttribute('data-app')) {
      canvasEl.setAttribute('data-app', opts.app);
    }

    return ensureBrython().then(function () {
      // Boot the Python package. Loop / events / renderer / shape drawing all live there.
      var bootCode = opts.sandbox
        ? "import scs_entrypoint as ep\nep.boot_sandbox()"
        : "import scs_entrypoint as ep\nep.boot(" + (opts.app ? JSON.stringify(opts.app) : "") + ")";
      var script = document.createElement('script');
      script.type = 'text/python';
      script.text = bootCode;
      document.body.appendChild(script);
      // Brython: if already booted, run the new script; if not, boot with pythonpath.
      if (global.brython && global.__BRYTHON__ && global.__BRYTHON__.run_script) {
        try { global.__BRYTHON__.run_script(bootCode, 'scs-boot'); } catch (e) { /* brython() will run it */ }
      } else {
        try { global.brython({ debug: 1, pythonpath: ['.', 'scs', '..', '../scs'] }); } catch (e) { console.error('[SCS] brython() failed', e); }
      }
    });
  }

  global.SCS = {
    __scs_js: true,
    version: '3.0.0',
    create: create,
    // Thin aliases: point to a valid app, or just enter app code.
    boot: function (app) { return create({ app: app }); },
    sandbox: function (selector) { return create({ sandbox: selector || '#code-input' }); }
  };
})(typeof window !== 'undefined' ? window : this);
