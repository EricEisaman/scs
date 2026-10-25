/**
 * extensions/pyodide_worker.js — SCS Pyodide Web Worker
 * Serious implementation: isolates CPython WASM runtime off main thread,
 * keeps canvas at 60fps during heavy SciPy / combinatorics.
 *
 * Main -> Worker:
 * {id, type: 'init', config?: {indexURL, packageBaseUrl, packages}}
 * {id, type: 'loadPackage', packages: string[], options?: object}
 * {id, type: 'loadPackagesFromImports', code: string}
 * {id, type: 'run', code: string}
 * {id, type: 'runAsync', code: string}
 * {id, type: 'pyimport', name: string}
 * {id, type: 'getGlobal', name: string}
 * {id, type: 'setGlobal', name: string, value: any}
 * {id, type: 'fs_write', path: string, data: string|Uint8Array}
 * {id, type: 'fs_read', path: string}
 * {id, type: 'install', package: string} # via micropip
 *
 * Worker -> Main:
 * {type: 'ready', version: string}
 * {type: 'stdout', data: string}
 * {type: 'stderr', data: string}
 * {id, success: true, result: any, type: <original type>}
 * {id, success: false, error: string, stack: string}
 */
const DEFAULT_CDN = "https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js";
let pyodide = null;
let ready = false;
let initPromise = null;
function post(type, payload = {}) { self.postMessage({ type, ...payload }); }
function postResult(id, origType, success, data) {
  if (success) { self.postMessage({ id, type: origType, success: true, result: data }); }
  else { self.postMessage({ id, type: origType, success: false, error: data?.message || String(data), stack: data?.stack || "" }); }
}
async function loadPyodideRuntime(config = {}) {
  if (pyodide) return pyodide;
  if (initPromise) return initPromise;
  initPromise = (async () => {
    if (typeof loadPyodide === "undefined") {
      const cdn = config.indexURL ? config.indexURL.replace(/\/$/, "") + "/pyodide.js" : DEFAULT_CDN;
      try { importScripts(cdn); } catch (e) { throw new Error(`Failed to importScripts(${cdn}): ${e}`); }
    }
    const opts = { stdout: (msg) => post("stdout", { data: msg }), stderr: (msg) => post("stderr", { data: msg }), ...config };
    pyodide = await loadPyodide(opts);
    const preload = config.packages || ["numpy", "scipy"];
    if (preload && preload.length) { try { await pyodide.loadPackage(preload); } catch (e) { console.warn("[pyodide_worker] preload warning", e); } }
    try { await pyodide.loadPackage("micropip"); } catch (_) {}
    ready = true;
    post("ready", { version: pyodide.version || "unknown", loadedPackages: Object.keys(pyodide.loadedPackages || {}) });
    return pyodide;
  })();
  try { return await initPromise; } catch (e) { initPromise = null; throw e; }
}
loadPyodideRuntime().catch(e => { post("error", { error: e.toString(), stack: e.stack || "" }); });
self.onmessage = async (event) => {
  const msg = event.data || {}; const { id, type } = msg; if (!type) return;
  try {
    if (type === "init") { const py = await loadPyodideRuntime(msg.config || {}); if (id != null) postResult(id, type, true, { version: py.version }); return; }
    if (!pyodide) { await loadPyodideRuntime(msg.config || {}); }
    switch (type) {
      case "loadPackage": { const pkgs = msg.packages; if (!pkgs) throw new Error("loadPackage: missing packages"); const res = await pyodide.loadPackage(pkgs, msg.options || {}); if (id != null) postResult(id, type, true, res || true); break; }
      case "loadPackagesFromImports": { if (!msg.code) throw new Error("loadPackagesFromImports: missing code"); const res = await pyodide.loadPackagesFromImports(msg.code, msg.options || {}); if (id != null) postResult(id, type, true, res || true); break; }
      case "run": case "runPython": { if (!msg.code) throw new Error("run: missing code"); const res = pyodide.runPython(msg.code, msg.options || {}); if (id != null) { let out = res; try { if (out && typeof out.toJs === "function") out = out.toJs({ dict_converter: Object.fromEntries }); } catch (_) {} postResult(id, type, true, out); } break; }
      case "runAsync": case "runPythonAsync": { if (!msg.code) throw new Error("runAsync: missing code"); const res = await pyodide.runPythonAsync(msg.code, msg.options || {}); if (id != null) { let out = res; try { if (out && typeof out.toJs === "function") { out = out.toJs({ dict_converter: Object.fromEntries, create_proxies: false }); } } catch (_) {} postResult(id, type, true, out); } break; }
      case "pyimport": { if (!msg.name) throw new Error("pyimport: missing name"); const mod = pyodide.pyimport(msg.name); if (id != null) { let repr = ""; try { repr = pyodide.runPython(`repr(__import__('${msg.name}'))`); } catch { repr = `[module ${msg.name}]`; } postResult(id, type, true, { name: msg.name, repr }); } break; }
      case "getGlobal": { if (!msg.name) throw new Error("getGlobal: missing name"); const val = pyodide.globals.get(msg.name); let out = val; try { if (out && typeof out.toJs === "function") out = out.toJs({ dict_converter: Object.fromEntries, create_proxies: false }); } catch (_) {} if (id != null) postResult(id, type, true, out); break; }
      case "setGlobal": { if (!msg.name) throw new Error("setGlobal: missing name"); pyodide.globals.set(msg.name, msg.value); if (id != null) postResult(id, type, true, true); break; }
      case "fs_write": { if (!msg.path) throw new Error("fs_write: missing path"); const dir = msg.path.split("/").slice(0, -1).join("/") || "/"; try { pyodide.FS.mkdirTree(dir); } catch (_) {} pyodide.FS.writeFile(msg.path, msg.data); if (id != null) postResult(id, type, true, true); break; }
      case "fs_read": { if (!msg.path) throw new Error("fs_read: missing path"); const data = pyodide.FS.readFile(msg.path, { encoding: "utf8" }); if (id != null) postResult(id, type, true, data); break; }
      case "install": { if (!msg.package) throw new Error("install: missing package"); try { await pyodide.loadPackage("micropip"); } catch (_) {} const micropip = pyodide.pyimport("micropip"); await micropip.install(msg.package); if (id != null) postResult(id, type, true, true); break; }
      default: throw new Error(`Unknown message type: ${type}`);
    }
  } catch (err) { if (id != null) postResult(id, type || "unknown", false, err); else post("error", { error: err?.toString() || String(err), stack: err?.stack || "" }); }
};
