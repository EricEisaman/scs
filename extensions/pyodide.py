"""
extensions/pyodide.py — Top-tier Pyodide API wrapper for SCS

Follows SCS top-tier extension pattern:
- Lazy singleton, cached WASM runtime
- CDN loader with de-duplication
- Full subset of official Pyodide JS API mirrored in Pythonic form
- Robust across Pyodide 0.23-0.26 (globals is dict in 0.25+)
- Optional Worker offload, non-breaking
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


async def _load_script(src):
    for _ in range(3):
        try:
            scripts = document.head.getElementsByTagName("script")
            for i in range(len(scripts)):
                s = scripts[i]
                try:
                    if s.getAttribute("src") and src in s.getAttribute("src"):
                        for _ in range(100):
                            if hasattr(window, "loadPyodide"):
                                return True
                            await aio.sleep(0.1)
                except:
                    pass
        except:
            break

    script = document.createElement("script")
    script.setAttribute("src", src)
    script.setAttribute("async", "false")
    document.head.appendChild(script)

    for _ in range(200):
        if hasattr(window, "loadPyodide"):
            return True
        await aio.sleep(0.1)
    return False


async def _ensure_pyodide(config=None):
    global _pyodide, _loading, _ready, _load_error
    # Top-tier: check module cache first
    if _ready and _pyodide is not None:
        return _pyodide
    # Top-tier: check window cache to survive Brython re-imports / SCS hot-reload
    try:
        if hasattr(window, "_scs_pyodide") and window._scs_pyodide:
            _pyodide = window._scs_pyodide
            _ready = True
            return _pyodide
    except:
        pass
    if _loading:
        for _ in range(300):
            if not _loading:
                break
            await aio.sleep(0.1)
        if _ready and _pyodide is not None:
            return _pyodide
        # Also re-check window cache while waiting
        try:
            if hasattr(window, "_scs_pyodide") and window._scs_pyodide:
                _pyodide = window._scs_pyodide
                _ready = True
                return _pyodide
        except:
            pass
        if _load_error:
            raise _load_error

    _loading = True
    _load_error = None
    try:
        if not hasattr(window, "loadPyodide"):
            ok = await _load_script(PYODIDE_CDN)
            if not ok:
                raise RuntimeError("Failed to load Pyodide CDN: " + PYODIDE_CDN)

        cfg = config or {}
        if cfg:
            _pyodide = await window.loadPyodide(cfg)
        else:
            _pyodide = await window.loadPyodide()

        # Top-tier: DO NOT preload heavy packages here.
        # Packages are lazy-loaded on demand (root() needs scipy, partition_stats needs none).
        # This eliminates the "Loading numpy, scipy, openblas" log for apps like Ferrers.

        _ready = True
        try:
            window._scs_pyodide = _pyodide
        except:
            pass
        return _pyodide
    except Exception as e:
        _load_error = e
        _pyodide = None
        _ready = False
        raise
    finally:
        _loading = False


def _convert_proxy(obj):
    if obj is None:
        return None
    try:
        if hasattr(obj, "toJs"):
            return obj.toJs()
    except:
        pass
    return obj


def is_ready():
    return _ready and _pyodide is not None


async def ensure(config=None):
    return await _ensure_pyodide(config)


async def get_version():
    py = await _ensure_pyodide()
    try:
        return py.version
    except:
        return "unknown"


async def load_package(names, options=None):
    py = await _ensure_pyodide()
    if isinstance(names, str):
        names = [names]
    await py.loadPackage(names, options or {})
    return True


async def load_packages_from_imports(code, options=None):
    py = await _ensure_pyodide()
    await py.loadPackagesFromImports(code, options or {})
    return True


async def run_python_sync(code, options=None):
    py = await _ensure_pyodide()
    res = py.runPython(code, options or {})
    return _convert_proxy(res)


async def run_python_async(code, options=None):
    py = await _ensure_pyodide()
    res = await py.runPythonAsync(code, options or {})
    return _convert_proxy(res)


async def run_python(code, options=None):
    return await run_python_async(code, options)


async def run(code, options=None):
    return await run_python(code, options)


async def pyimport(name):
    py = await _ensure_pyodide()
    return py.pyimport(name)


async def to_py(js_obj, options=None):
    py = await _ensure_pyodide()
    return py.toPy(js_obj, options or {})


async def install(package):
    py = await _ensure_pyodide()
    try:
        await py.loadPackage("micropip")
    except:
        pass
    code = "import micropip\nawait micropip.install(" + repr(package) + ")"
    await py.runPythonAsync(code)
    return True


async def register_js_module(name, module):
    py = await _ensure_pyodide()
    py.registerJsModule(name, module)
    return True


async def unregister_js_module(name):
    py = await _ensure_pyodide()
    py.unregisterJsModule(name)
    return True


def set_stdout(handler):
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


def get_global(name):
    if _pyodide and hasattr(_pyodide, "globals"):
        try:
            g = _pyodide.globals
            v = g.get(name) if hasattr(g, "get") else g[name]
            return _convert_proxy(v)
        except:
            pass
    return None


def set_global(name, value):
    if _pyodide and hasattr(_pyodide, "globals"):
        try:
            g = _pyodide.globals
            if hasattr(g, "set"):
                g.set(name, value)
            else:
                g[name] = value
            return True
        except:
            try:
                _pyodide.globals[name] = value
                return True
            except:
                pass
    return False


async def get_global_async(name):
    py = await _ensure_pyodide()
    try:
        g = py.globals
        v = g.get(name) if hasattr(g, "get") else g[name]
    except:
        v = None
    return _convert_proxy(v)


async def set_global_async(name, value):
    py = await _ensure_pyodide()
    try:
        g = py.globals
        if hasattr(g, "set"):
            g.set(name, value)
        else:
            g[name] = value
    except:
        try:
            py.globals[name] = value
        except:
            await py.runPythonAsync(name + " = " + json.dumps(value))
    return True


async def fs_mkdir(path):
    py = await _ensure_pyodide()
    try:
        py.FS.mkdirTree(path)
        return True
    except Exception as e:
        print("fs_mkdir warning: " + str(e))
        return False


async def fs_write_file(path, data, encoding="utf8"):
    py = await _ensure_pyodide()
    try:
        parent = "/".join(path.split("/")[:-1])
        if parent:
            try:
                py.FS.mkdirTree(parent)
            except:
                pass
        py.FS.writeFile(path, data)
        return True
    except Exception:
        try:
            code = "open(" + repr(path) + ", 'w', encoding=" + repr(encoding) + ").write(" + repr(data if isinstance(data, str) else str(data)) + ")"
            await py.runPythonAsync(code)
            return True
        except Exception as e:
            print("fs_write_file error: " + str(e))
            return False


async def fs_read_file(path, encoding="utf8"):
    py = await _ensure_pyodide()
    try:
        return py.FS.readFile(path, {"encoding": encoding})
    except Exception:
        try:
            code = "open(" + repr(path) + ", 'r', encoding=" + repr(encoding) + ").read()"
            return await py.runPythonAsync(code)
        except Exception as e:
            print("fs_read_file error: " + str(e))
            return None


async def _ensure_worker(config=None):
    global _worker, _worker_ready
    if _worker and _worker_ready:
        return _worker
    try:
        WorkerCtor = window.Worker
    except:
        raise RuntimeError("Worker not supported")
    if not _worker:
        try:
            _worker = WorkerCtor.new(PYODIDE_WORKER_URL)
        except:
            _worker = window.Worker.new(PYODIDE_WORKER_URL)

        def on_msg(event):
            data = event.data
            if not data:
                return
            try:
                t = data.type if hasattr(data, "type") else data.get("type")
            except:
                try:
                    t = data["type"]
                except:
                    t = None
            if t == "ready":
                global _worker_ready
                _worker_ready = True
            try:
                id_ = data.id if hasattr(data, "id") else data.get("id")
            except:
                try:
                    id_ = data["id"]
                except:
                    id_ = None
            if id_ is not None and id_ in _worker_pending:
                fut = _worker_pending.pop(id_)
                try:
                    success = data.get("success") if hasattr(data, "get") else getattr(data, "success", False)
                    if success:
                        res = data.get("result") if hasattr(data, "get") else getattr(data, "result", None)
                        fut["resolve"](res)
                    else:
                        err = data.get("error") if hasattr(data, "get") else getattr(data, "error", "worker error")
                        fut["reject"](Exception(err))
                except:
                    pass

        _worker.addEventListener("message", on_msg)

    cfg = config or {}
    await _worker_call({"type": "init", "config": cfg})
    return _worker


def _worker_call(msg):
    global _worker_id
    cur_id = _worker_id
    _worker_id += 1
    msg["id"] = cur_id
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
        for _ in range(500):
            if future["resolved"]:
                if future["error"]:
                    raise future["error"]
                return future["value"]
            await aio.sleep(0.1)
        raise TimeoutError("worker call timeout")
    return waiter()


async def run_via_worker(code, action="runAsync"):
    await _ensure_worker()
    return await _worker_call({"type": action, "code": code})


async def root(residual_expressions, initial_values, variables=None):
    py = await _ensure_pyodide()
    # Lazy-load scipy only when root() is actually used (top-tier pattern)
    try:
        await py.loadPackage(["numpy", "scipy"])
    except Exception as e:
        print("root: loadPackage warning " + str(e))
    variables = variables or []
    exprs_json = json.dumps(residual_expressions)
    x0_json = json.dumps(initial_values)
    var_json = json.dumps(variables)

    code = (
        "import json, math, numpy as np\n"
        "from scipy.optimize import root as scipy_root\n"
        "exprs = " + exprs_json + "\n"
        "x0_list = " + x0_json + "\n"
        "var_names = " + var_json + "\n"
        "x0 = np.array(x0_list, dtype=float)\n"
        "SAFE_FUNCS = {\n"
        "    'sin': math.sin, 'cos': math.cos, 'tan': math.tan,\n"
        "    'asin': math.asin, 'acos': math.acos, 'atan': math.atan,\n"
        "    'sinh': math.sinh, 'cosh': math.cosh, 'tanh': math.tanh,\n"
        "    'exp': math.exp, 'log': math.log, 'ln': math.log,\n"
        "    'sqrt': math.sqrt, 'pi': math.pi, 'e': math.e,\n"
        "    'fabs': math.fabs, 'pow': math.pow,\n"
        "}\n"
        "def eval_residuals(vars_arr):\n"
        "    local = {}\n"
        "    for name, val in zip(var_names, vars_arr):\n"
        "        local[name] = float(val)\n"
        "    local.update(SAFE_FUNCS)\n"
        "    out = []\n"
        "    for expr in exprs:\n"
        "        try:\n"
        "            out.append(float(eval(expr, {'__builtins__': {}}, local)))\n"
        "        except Exception:\n"
        "            out.append(float('nan'))\n"
        "    return out\n"
        "def residual_np(vars_arr):\n"
        "    return np.array(eval_residuals(vars_arr), dtype=float)\n"
        "try:\n"
        "    init_res = residual_np(x0)\n"
        "    initial_norm = float(np.linalg.norm(init_res))\n"
        "except Exception:\n"
        "    initial_norm = float('nan')\n"
        "try:\n"
        "    sol = scipy_root(residual_np, x0, method='hybr')\n"
        "    x_list = sol.x.tolist() if hasattr(sol, 'x') and sol.x is not None else []\n"
        "    fun_list = sol.fun.tolist() if hasattr(sol, 'fun') and sol.fun is not None else []\n"
        "    success = bool(getattr(sol, 'success', False))\n"
        "    status = int(getattr(sol, 'status', -1))\n"
        "    message = str(getattr(sol, 'message', ''))\n"
        "    nfev = int(getattr(sol, 'nfev', 0))\n"
        "    try:\n"
        "        final_norm = float(np.linalg.norm(sol.fun)) if hasattr(sol, 'fun') else float('nan')\n"
        "    except:\n"
        "        final_norm = float('nan')\n"
        "except Exception as e:\n"
        "    x_list = []\n"
        "    fun_list = []\n"
        "    success = False\n"
        "    status = -1\n"
        "    message = 'Solver exception: %s' % e\n"
        "    nfev = 0\n"
        "    final_norm = float('nan')\n"
        "result = {\n"
        "    'x': x_list,\n"
        "    'fun': fun_list,\n"
        "    'success': success,\n"
        "    'status': status,\n"
        "    'message': message,\n"
        "    'nfev': nfev,\n"
        "    'initialResidualNorm': initial_norm,\n"
        "    'residualNorm': final_norm\n"
        "}\n"
        "json.dumps(result)\n"
    )

    json_str = await py.runPythonAsync(code)
    try:
        return json.loads(json_str)
    except:
        if isinstance(json_str, dict):
            return json_str
        return json.loads(str(json_str))


async def partition_stats(part_list):
    py = await _ensure_pyodide()
    part_json = json.dumps(part_list)

    code = (
        "import json, math\n"
        "part = " + part_json + "\n"
        "part = [int(x) for x in part if int(x) > 0]\n"
        "part = sorted(part, reverse=True)\n"
        "n = sum(part)\n"
        "max_len = max(part) if part else 0\n"
        "conj = [sum(1 for r in part if r > i) for i in range(max_len)]\n"
        "conj = [c for c in conj if c > 0]\n"
        "d = 0\n"
        "for i, rl in enumerate(part):\n"
        "    if rl >= i+1:\n"
        "        d = i+1\n"
        "    else:\n"
        "        break\n"
        "hooks = []\n"
        "for i, rl in enumerate(part):\n"
        "    row = []\n"
        "    for j in range(rl):\n"
        "        right = rl - (j+1)\n"
        "        down = conj[j] - (i+1) if j < len(conj) else 0\n"
        "        row.append(right + down + 1)\n"
        "    hooks.append(row)\n"
        "def p_number(k):\n"
        "    if k < 0:\n"
        "        return 0\n"
        "    if k == 0:\n"
        "        return 1\n"
        "    p = [0]*(k+1)\n"
        "    p[0] = 1\n"
        "    for kk in range(1, k+1):\n"
        "        total = 0\n"
        "        j = 1\n"
        "        while True:\n"
        "            pent1 = j*(3*j-1)//2\n"
        "            if pent1 > kk:\n"
        "                break\n"
        "            sign = 1 if (j % 2 == 1) else -1\n"
        "            total += sign * p[kk - pent1]\n"
        "            pent2 = j*(3*j+1)//2\n"
        "            if pent2 <= kk:\n"
        "                total += sign * p[kk - pent2]\n"
        "            j += 1\n"
        "        p[kk] = total\n"
        "    return p[k]\n"
        "pn = p_number(n)\n"
        "prod_hooks = 1\n"
        "for row in hooks:\n"
        "    for h in row:\n"
        "        prod_hooks *= h\n"
        "try:\n"
        "    f_lambda = math.factorial(n) // prod_hooks if prod_hooks != 0 else 0\n"
        "except:\n"
        "    f_lambda = 0\n"
        "result = {\n"
        "    'conj': conj,\n"
        "    'durfee': d,\n"
        "    'hooks': hooks,\n"
        "    'p_n': pn,\n"
        "    'f_lambda': f_lambda,\n"
        "    'n': n,\n"
        "    'prod_hooks': prod_hooks,\n"
        "    'part': part\n"
        "}\n"
        "json.dumps(result)\n"
    )

    json_str = await py.runPythonAsync(code)
    try:
        return json.loads(json_str)
    except:
        if isinstance(json_str, dict):
            return json_str
        return json.loads(str(json_str))
