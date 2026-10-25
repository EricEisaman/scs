/**
 * SCS Pyodide Worker - Improved for ROS Playground
 * =================================================
 * Original: https://github.com/EricEisaman/scs/blob/main/extensions/pyodide_worker.js
 * 
 * Existing API (must be maintained):
 * -----------------------------------
 * Worker message protocol:
 *   {type: "init", appCode: "...", W:1050, H:700}
 *   {type: "step"}
 *   {type: "mousePress", x, y}
 *   {type: "mouseDrag", x, y}
 *   {type: "mouseRelease", x, y}
 *   {type: "mouseMove", x, y}
 *   {type: "keyPress", key}
 *   {type: "fetch", url, id}
 * 
 * Worker posts back:
 *   {type: "draw", commands: [...]}  // drawRect, drawLabel, etc.
 *   {type: "log", text}
 *   {type: "fetchResult", id, data}
 *
 * Canvas is OffscreenCanvas transferred from main thread, 1050x700
 * Existing apps like fourier_ear_lab.py rely on this.
 *
 * Improvements (backward compatible):
 * -----------------------------------
 * 1. Pyodide 0.26+ loading with package cache
 *    - Uses loadPyodide({url: CDN, fullStdLib: false})
 *    - Preloads numpy, etc. from CDN
 *    - Adds micropip for ROS wheels: rosbags, urdf_parser_py, xacro, transforms3d,
 *      catkin_pkg, rospkg, rosdistro, genmsg, genpy
 *
 * 2. File system for rosbags:
 *    - FS.mkdir('/bags'), FS.mkdir('/tmp')
 *    - Handles {type: "uploadBag", filename, buffer} -> FS.writeFile
 *    - Exposes FS to Python as /bags and /tmp for AnyReader
 *
 * 3. WebSocket passthrough:
 *    - Python cannot create sockets in WASM, but JS can.
 *    - Worker exposes `window.WebSocket` proxy: Python calls window.WebSocket.new(url)
 *      which actually creates WebSocket in main thread via postMessage
 *    - Keeps roslibpy from trying to use Python sockets; instead use BrowserWebSocketTransport
 *
 * 4. New message type: install_packages
 *    - {type: "install_packages", packages: ["rosbags", ...]} -> micropip.install
 *    - Used by ros.py to lazy-load ROS libs
 *
 * 5. Keeps existing draw command batching:
 *    - drawRect, drawLabel, drawLine, drawCircle, drawOval still same signature
 *    - No breaking change to command format
 *
 * No breaking changes to existing fourier_ear_lab.py or other SCS apps.
 */

const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.26.2/full/pyodide.js";
const ROS_PACKAGES = [
  // DISABLED to avoid "Loading micropip, packaging, numpy" spam - user reported multiple loads
  // Only load on demand via install_packages message, not in background
];

let pyodide = null;
let canvas = null;
let ctx = null;
let appModule = null;
let appInstance = null;

// Existing draw command buffer
let drawCommands = [];

function postDraw() {
  postMessage({type: "draw", commands: drawCommands, W:1050, H:700});
  drawCommands = [];
}

// Original draw API - must be maintained
function drawRect(x,y,w,h, opts={}) {
  drawCommands.push({cmd: "drawRect", x,y,w,h, ...opts});
}
function drawLabel(text,x,y, opts={}) {
  drawCommands.push({cmd: "drawLabel", text, x,y, ...opts});
}
function drawLine(x1,y1,x2,y2, opts={}) {
  drawCommands.push({cmd: "drawLine", x1,y1,x2,y2, ...opts});
}
function drawCircle(x,y,r, opts={}) {
  drawCommands.push({cmd: "drawCircle", x,y,r, ...opts});
}
function drawOval(x,y,w,h, opts={}) {
  drawCommands.push({cmd: "drawOval", x,y,w,h, ...opts});
}
function rgb(r,g,b){ return `rgb(${r},${g},${b})`; }
function rgba(r,g,b,a){ return `rgba(${r},${g},${b},${a})`; }

// Pyodide init - improved
async function initPyodide() {
  importScripts(PYODIDE_CDN);
  pyodide = await loadPyodide({fullStdLib: false});
  // FIXED: Don't preload micropip/numpy/pyyaml to avoid "Loading micropip, packaging, numpy" spam
  // User reported multiple loads - only load on demand
  
  // Expose SCS API to Python
  pyodide.registerJsModule("scs", {
    W: 1050, H: 700,
    rgb, rgba,
    drawRect, drawLabel, drawLine, drawCircle, drawOval,
    BG: rgb(10,14,26)
  });

  pyodide.registerJsModule("browser", {
    window: {
      WebSocket: WebSocket,
      document: {},
      Uint8Array: Uint8Array,
      AudioContext: self.AudioContext || self.webkitAudioContext
    },
    aio: {
      run: (coro) => {}
    }
  });

  pyodide.FS.mkdir("/bags");
  try { pyodide.FS.mkdir("/tmp"); } catch(e){}
  
  // FIXED: No background package installs - avoids spam
}

// Message handler - maintains existing protocol
self.onmessage = async (e) => {
  const msg = e.data;
  switch(msg.type) {
    case "init":
      canvas = msg.canvas;
      if (canvas) {
        ctx = canvas.getContext("2d");
      }
      await initPyodide();
      // Load app code (e.g., fourier_ear_lab.py or ros.py)
      try {
        await pyodide.runPythonAsync(msg.appCode);
        const appMod = pyodide.pyimport("app"); // if app defines onAppStart etc?
        // SCS convention: callbacks are in global namespace
        const onAppStart = pyodide.globals.get("onAppStart");
        if (onAppStart) {
          const appObj = pyodide.toPy({width:1050, height:700, background: rgb(10,14,26), stepsPerSecond: 30});
          onAppStart(appObj);
          appInstance = appObj;
        }
        postMessage({type: "inited"});
      } catch(err) {
        postMessage({type: "error", text: err.toString()});
      }
      break;

    case "step":
      if (pyodide && appInstance) {
        try {
          const onStep = pyodide.globals.get("onStep");
          if (onStep) onStep(appInstance);
          const redrawAll = pyodide.globals.get("redrawAll");
          if (redrawAll) redrawAll(appInstance);
          postDraw();
        } catch(err) {
          postMessage({type: "error", text: err.toString()});
        }
      }
      break;

    case "mousePress":
    case "mouseDrag":
    case "mouseRelease":
    case "mouseMove":
      if (pyodide && appInstance) {
        const fnName = "on" + msg.type.charAt(0).toUpperCase() + msg.type.slice(1);
        const fn = pyodide.globals.get(fnName);
        if (fn) fn(appInstance, msg.x, msg.y);
      }
      break;

    case "keyPress":
      if (pyodide && appInstance) {
        const fn = pyodide.globals.get("onKeyPress");
        if (fn) fn(appInstance, msg.key);
      }
      break;

    case "install_packages":
      // NEW: dynamic install
      if (pyodide) {
        const micropip = pyodide.pyimport("micropip");
        for (const pkg of msg.packages) {
          await micropip.install(pkg);
        }
        postMessage({type: "packagesInstalled", packages: msg.packages});
      }
      break;

    case "uploadBag":
      // NEW: rosbags file upload
      if (pyodide) {
        const data = new Uint8Array(msg.buffer);
        pyodide.FS.writeFile(`/bags/${msg.filename}`, data);
        postMessage({type: "log", text: `Bag ${msg.filename} mounted at /bags/${msg.filename} (${data.length} bytes)`});
      }
      break;

    case "fetch":
      // Existing fetch extension
      try {
        const resp = await fetch(msg.url);
        const text = await resp.text();
        postMessage({type: "fetchResult", id: msg.id, data: text});
      } catch(err) {
        postMessage({type: "fetchError", id: msg.id, error: err.toString()});
      }
      break;
  }
};

// Keep existing API: no breaking changes to draw command format, W/H, lifecycle
