"""
extensions/pyodide.py — SCS Pyodide Extension
Serious wrapper around Pyodide WASM runtime.

Exposes a reasonable subset of the official Pyodide JS/Python API:
https://pyodide.org/en/stable/usage/api/js-api.html
https://pyodide.org/en/stable/usage/api/python-api.html

- Lifecycle: ensure(), get_version(), is_ready()
- Packages: load_package(), load_packages_from_imports(), install() via micropip
- Execution: run_python(), run_python_async(), run_python_sync()
- Imports: pyimport()
- Globals: get_global(), set_global(), get_global_async(), set_global_async()
- Conversion: to_py(), from_js() helpers
- JS modules: register_js_module(), unregister_js_module()
- I/O: set_stdout(), set_stderr(), set_stdin()
- FS: fs_write_file(), fs_read_file(), fs_mkdir()

Plus SCS domain helpers:
- root() — nonlinear system solver via scipy.optimize.root
- partition_stats() — partition conjugate, Durfee, hooks, p(n), f^lambda

All heavy work runs in Pyodide (WASM CPython) without blocking UI.
Optionally can delegate to extensions/pyodide_worker.js via Worker API.

Backwards compatible: existing community apps using root(), partition_stats(),
run_python(), run() continue to work unchanged.
"""

from browser import window, document, aio
import json

_pyodide = None
_loading = False
_ready = False
_load_error = None

_worker = None
_worker_ready = False
_worker_pending = {}
_worker_id = 1

PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js"
PYODIDE_WORKER_URL = "extensions/pyodide_worker.js"


# ----------------------------------------------------------------------
# Internal: script loader
# ----------------------------------------------------------------------
async def _load_script(src):
    """Inject <script src> and wait for window.loadPyodide."""
    for _ in range(3):
        scripts = document.head.getElementsByTagName("script")
        for i in range(len(scripts)):
            try:
                if scripts[i].src and src in scripts[i].src:
                    for _ in range(100):
                        if hasattr(window, "loadPyodide"):
                            return True
                        await aio.sleep(0.1)
            except:
                pass
        break

    script = document.createElement("script")
    script.src = src
    script.async = False
    document.head.appendChild(script)

    for _ in range(200):
        if hasattr(window, "loadPyodide"):
            return True
        await aio.sleep(0.1)
    return False


async def _ensure_pyodide(config=None):
    """Lazy singleton — loads Pyodide + preloads numpy/scipy."""
    global _pyodide, _loading, _ready, _load_error

    if _ready and _pyodide is not None:
        return _pyodide

    if _loading:
        for _ in range(300):
            if not _loading:
                break
            await aio.sleep(0.1)
        if _ready and _pyodide is not None:
            return _pyodide
        if _load_error:
            raise _load_error

    _loading = True
    _load_error = None
    try:
        if not hasattr(window, "loadPyodide"):
            ok = await _load_script(PYODIDE_CDN)
            if not ok:
                raise RuntimeError(f"Failed to load {PYODIDE_CDN}")

        # Allow custom config (indexURL, packageBaseUrl, etc.)
        cfg = config or {}
        if cfg:
            _pyodide = await window.loadPyodide(cfg)
        else:
            _pyodide = await window.loadPyodide()

        try:
            await _pyodide.loadPackage(["numpy", "scipy"])
        except Exception as e:
            print(f"pyodide preload warning: {e}")

        _ready = True
        return _pyodide
    except Exception as e:
        _load_error = e
        _pyodide = None
        _ready = False
        raise
    finally:
        _loading = False


def _convert_proxy(obj):
    """Best-effort conversion of PyProxy -> JS/Python native."""
    if obj is None:
        return None
    try:
        if hasattr(obj, "toJs"):
            # Avoid creating proxies for speed unless needed
            try:
                return obj.toJs({"dict_converter": Object.fromEntries, "create_proxies": False})
            except:
                try:
                    return obj.toJs()
                except:
                    return obj
    except:
        pass
    return obj


def is_ready():
    return _ready and _pyodide is not None


# ----------------------------------------------------------------------
# Public API — subset of https://pyodide.org/en/stable/usage/api/js-api.html
# ----------------------------------------------------------------------
async def ensure(config=None):
    """Ensure Pyodide is loaded, return instance."""
    return await _ensure_pyodide(config)


async def get_version():
    py = await _ensure_pyodide()
    try:
        return py.version
    except:
        return "unknown"


async def load_package(names, options=None):
    """
    Load packages from Pyodide distribution.
    names: str | list[str] e.g. 'numpy' or ['numpy','scipy']
    Mirrors pyodide.loadPackage
    """
    py = await _ensure_pyodide()
    if isinstance(names, str):
        names = [names]
    await py.loadPackage(names, options or {})
    return True


async def load_packages_from_imports(code, options=None):
    """
    Inspect Python code and auto-install imports.
    Mirrors pyodide.loadPackagesFromImports
    """
    py = await _ensure_pyodide()
    await py.loadPackagesFromImports(code, options or {})
    return True


async def run_python_sync(code, options=None):
    """Synchronous execution, no top-level await. Mirrors pyodide.runPython"""
    py = await _ensure_pyodide()
    res = py.runPython(code, options or {})
    return _convert_proxy(res)


async def run_python_async(code, options=None):
    """Async execution with top-level await support. Mirrors pyodide.runPythonAsync"""
    py = await _ensure_pyodide()
    res = await py.runPythonAsync(code, options or {})
    return _convert_proxy(res)


async def run_python(code: str, options=None):
    """
    Low-level runner — returns result of last expression.
    Backwards compatible: old signature returned string/result.
    Now uses runPythonAsync for full support.
    """
    return await run_python_async(code, options)


async def run(code: str, options=None):
    """Alias for run_python for backwards compatibility."""
    return await run_python(code, options)


async def pyimport(name):
    """Import Python module and return it. Mirrors pyodide.pyimport"""
    py = await _ensure_pyodide()
    mod = py.pyimport(name)
    return mod


async def to_py(js_obj, options=None):
    """Convert JS object to Python. Mirrors pyodide.toPy"""
    py = await _ensure_pyodide()
    return py.toPy(js_obj, options or {})


async def install(package, extras=""):
    """
    Install package via micropip (PyPI). Handles pure Python wheels.
    package: e.g. 'snowballstemmer' or 'numpy==1.26'
    Mirrors typical pattern: await loadPackage('micropip'); micropip.install()
    """
    py = await _ensure_pyodide()
    try:
        await py.loadPackage("micropip")
    except:
        pass
    # Use Python-level micropip with await
    pkg_repr = repr(package)
    code = f"""
import micropip
await micropip.install({pkg_repr})
"""
    await py.runPythonAsync(code)
    return True


async def register_js_module(name, module):
    """Register JS module for Python import. Mirrors pyodide.registerJsModule"""
    py = await _ensure_pyodide()
    py.registerJsModule(name, module)
    return True


async def unregister_js_module(name):
    py = await _ensure_pyodide()
    py.unregisterJsModule(name)
    return True


def set_stdout(handler):
    """Set stdout handler. handler: dict with batched() or callable"""
    if _pyodide and hasattr(_pyodide, "setStdout"):
        _pyodide.setStdout(handler)
        return True
    return False


def set_stderr(handler):
    if _pyodide and hasattr(_pyodide, "setStderr"):
        _pyodide.setStderr(handler)
        return True
    return False


def set_stdin(handler):
    if _pyodide and hasattr(_pyodide, "setStdin"):
        _pyodide.setStdin(handler)
        return True
    return False


# Globals access — mirrors pyodide.globals
def get_global(name):
    if _pyodide and hasattr(_pyodide, "globals"):
        try:
            v = _pyodide.globals.get(name)
            return _convert_proxy(v)
        except:
            pass
    return None


def set_global(name, value):
    if _pyodide and hasattr(_pyodide, "globals"):
        try:
            _pyodide.globals.set(name, value)
            return True
        except:
            pass
    return False


async def get_global_async(name):
    py = await _ensure_pyodide()
    v = py.globals.get(name)
    return _convert_proxy(v)


async def set_global_async(name, value):
    py = await _ensure_pyodide()
    py.globals.set(name, value)
    return True


# FS helpers — mirrors pyodide.FS
async def fs_mkdir(path):
    py = await _ensure_pyodide()
    try:
        py.FS.mkdirTree(path)
        return True
    except Exception as e:
        print(f"fs_mkdir warning: {e}")
        return False


async def fs_write_file(path, data, encoding="utf8"):
    py = await _ensure_pyodide()
    try:
        # Ensure parent dir
        parent = "/".join(path.split("/")[:-1])
        if parent:
            try:
                py.FS.mkdirTree(parent)
            except:
                pass
        if isinstance(data, str):
            py.FS.writeFile(path, data)
        else:
            py.FS.writeFile(path, data)
        return True
    except Exception:
        # Fallback via Python open
        esc = data if isinstance(data, str) else str(data)
        code = f"open({repr(path)}, 'w', encoding={repr(encoding)}).write({repr(esc)})"
        try:
            await py.runPythonAsync(code)
            return True
        except Exception as e:
            print(f"fs_write_file error: {e}")
            return False


async def fs_read_file(path, encoding="utf8"):
    py = await _ensure_pyodide()
    try:
        return py.FS.readFile(path, {"encoding": encoding})
    except Exception:
        code = f"open({repr(path)}, 'r', encoding={repr(encoding)}).read()"
        try:
            return await py.runPythonAsync(code)
        except Exception as e:
            print(f"fs_read_file error: {e}")
            return None


# ----------------------------------------------------------------------
# Worker support (optional, non-breaking)
# ----------------------------------------------------------------------
async def _ensure_worker(config=None):
    """Spawn pyodide_worker.js if not already."""
    global _worker, _worker_ready, _worker_id
    if _worker and _worker_ready:
        return _worker

    try:
        Worker = window.Worker
    except:
        raise RuntimeError("Worker not supported in this environment")

    if not _worker:
        _worker = Worker.new(PYODIDE_WORKER_URL)

        def on_msg(event):
            data = event.data
            if not data:
                return
            t = data.get("type") if hasattr(data, "get") else getattr(data, "type", None)
            if t == "ready":
                global _worker_ready
                _worker_ready = True
            # Resolve pending promises
            id_ = data.get("id") if hasattr(data, "get") else getattr(data, "id", None)
            if id_ is not None and id_ in _worker_pending:
                fut = _worker_pending.pop(id_)
                try:
                    if data.get("success"):
                        fut["resolve"](data.get("result"))
                    else:
                        fut["reject"](Exception(data.get("error") or "worker error"))
                except:
                    pass

        _worker.addEventListener("message", on_msg)

    # Init
    cfg = config or {}
    await _worker_call({"type": "init", "config": cfg})
    return _worker


def _worker_call(msg):
    """Send message to worker and await response via Promise bridge."""
    global _worker_id
    import asyncio as _asyncio  # Brython's asyncio via aio

    cur_id = _worker_id
    _worker_id += 1
    msg["id"] = cur_id

    # We need to bridge JS Promise to Brython Future
    # Use aio-style manual future via dict
    future = {"resolved": False, "value": None, "error": None}

    def resolve(v):
        future["resolved"] = True
        future["value"] = v

    def reject(e):
        future["resolved"] = True
        future["error"] = e

    _worker_pending[cur_id] = {"resolve": resolve, "reject": reject}
    _worker.postMessage(msg)

    async def waiter():
        for _ in range(500):  # 50s timeout
            if future["resolved"]:
                if future["error"]:
                    raise future["error"]
                return future["value"]
            await aio.sleep(0.1)
        raise TimeoutError("worker call timeout")

    return waiter()


async def run_via_worker(code, action="runAsync"):
    """Run code inside worker, keep main thread free."""
    await _ensure_worker()
    return await _worker_call({"type": action, "code": code})


# ----------------------------------------------------------------------
# Domain helpers (kept for backwards compatibility, no app references)
# ----------------------------------------------------------------------
async def root(residual_expressions, initial_values, variables=None):
    """
    Solve nonlinear system via scipy.optimize.root inside Pyodide.
    Args:
        residual_expressions: list[str] — expressions evaluated with variables
        initial_values: list[float]
        variables: list[str] — variable names
    Returns dict: {x, fun, success, status, message, nfev, initialResidualNorm, residualNorm}
    """
    py = await _ensure_pyodide()
    variables = variables or []

    try:
        py.globals.set("residual_exprs_py", residual_expressions)
        py.globals.set("initial_vals_py", initial_values)
        py.globals.set("variable_names_py", variables)
    except:
        pass

    code = """
import json, math, numpy as np
from scipy.optimize import root as scipy_root

try:
    exprs = list(residual_exprs_py)
except:
    exprs = []
try:
    x0_list = list(initial_vals_py)
except:
    x0_list = []
try:
    var_names = list(variable_names_py)
except:
    var_names = []

x0 = np.array(x0_list, dtype=float)

SAFE_FUNCS = {
    'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
    'asin': math.asin, 'acos': math.acos, 'atan': math.atan,
    'sinh': math.sinh, 'cosh': math.cosh, 'tanh': math.tanh,
    'exp': math.exp, 'log': math.log, 'ln': math.log,
    'sqrt': math.sqrt, 'pi': math.pi, 'e': math.e,
    'fabs': math.fabs, 'pow': math.pow,
}

def eval_residuals(vars_arr):
    local = {}
    for name, val in zip(var_names, vars_arr):
        local[name] = float(val)
    local.update(SAFE_FUNCS)
    out = []
    for expr in exprs:
        try:
            out.append(float(eval(expr, {"__builtins__": {}}, local)))
        except Exception:
            out.append(float('nan'))
    return out

def residual_np(vars_arr):
    return np.array(eval_residuals(vars_arr), dtype=float)

try:
    init_res = residual_np(x0)
    initial_norm = float(np.linalg.norm(init_res))
except Exception:
    initial_norm = float('nan')

try:
    sol = scipy_root(residual_np, x0, method='hybr')
    x_list = sol.x.tolist() if hasattr(sol, 'x') and sol.x is not None else []
    fun_list = sol.fun.tolist() if hasattr(sol, 'fun') and sol.fun is not None else []
    success = bool(getattr(sol, 'success', False))
    status = int(getattr(sol, 'status', -1))
    message = str(getattr(sol, 'message', ''))
    nfev = int(getattr(sol, 'nfev', 0))
    try:
        final_norm = float(np.linalg.norm(sol.fun)) if hasattr(sol, 'fun') else float('nan')
    except:
        final_norm = float('nan')
except Exception as e:
    x_list = []
    fun_list = []
    success = False
    status = -1
    message = f"Solver exception: {e}"
    nfev = 0
    final_norm = float('nan')

result = {
    'x': x_list,
    'fun': fun_list,
    'success': success,
    'status': status,
    'message': message,
    'nfev': nfev,
    'initialResidualNorm': initial_norm,
    'residualNorm': final_norm
}
json.dumps(result)
"""

    json_str = await py.runPythonAsync(code)
    try:
        return json.loads(json_str)
    except:
        if isinstance(json_str, dict):
            return json_str
        try:
            return json.loads(str(json_str))
        except:
            raise RuntimeError(f"Failed to parse root result: {json_str}")


async def partition_stats(part_list):
    """
    Compute partition invariants inside Pyodide.
    Args:
        part_list: list[int] e.g. [6,4,4,2,1]
    Returns dict:
        {conj, durfee, hooks, p_n, f_lambda, n, prod_hooks, part}
    """
    py = await _ensure_pyodide()

    try:
        py.globals.set("part_input_py", part_list)
    except:
        pass

    code = """
import json, math

try:
    part = list(part_input_py)
except:
    part = []

part = [int(x) for x in part if int(x) > 0]
part = sorted(part, reverse=True)

n = sum(part)
max_len = max(part) if part else 0

conj = [sum(1 for r in part if r > i) for i in range(max_len)]
conj = [c for c in conj if c > 0]

d = 0
for i, rl in enumerate(part):
    if rl >= i+1:
        d = i+1
    else:
        break

hooks = []
for i, rl in enumerate(part):
    row = []
    for j in range(rl):
        right = rl - (j+1)
        down = conj[j] - (i+1) if j < len(conj) else 0
        row.append(right + down + 1)
    hooks.append(row)

def p_number(k):
    if k < 0:
        return 0
    if k == 0:
        return 1
    p = [0]*(k+1)
    p[0] = 1
    for kk in range(1, k+1):
        total = 0
        j = 1
        while True:
            pent1 = j*(3*j-1)//2
            if pent1 > kk:
                break
            sign = 1 if (j % 2 == 1) else -1
            total += sign * p[kk - pent1]
            pent2 = j*(3*j+1)//2
            if pent2 <= kk:
                total += sign * p[kk - pent2]
            j += 1
        p[kk] = total
    return p[k]

pn = p_number(n)

prod_hooks = 1
for row in hooks:
    for h in row:
        prod_hooks *= h

try:
    f_lambda = math.factorial(n) // prod_hooks if prod_hooks != 0 else 0
except:
    f_lambda = 0

result = {
    'conj': conj,
    'durfee': d,
    'hooks': hooks,
    'p_n': pn,
    'f_lambda': f_lambda,
    'n': n,
    'prod_hooks': prod_hooks,
    'part': part
}
json.dumps(result)
"""
    json_str = await py.runPythonAsync(code)
    try:
        return json.loads(json_str)
    except:
        if isinstance(json_str, dict):
            return json_str
        return json.loads(str(json_str))
