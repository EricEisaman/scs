"""Optional SciPy computation in a lazy Pyodide Web Worker.

This Model-only module has no SCS or canvas dependencies. Root expressions use
Python-style scalar syntax, for example ``x**2 + y - 4``.
"""

import json
from browser import window


_WORKER_PATH = './extensions/pyodide_worker.js'
_worker = None
_pending = {}
_next_request_id = 0


class PyodideError(Exception):
    """Raised when worker startup or a SciPy operation fails."""


def _handle_message(event):
    data = event.data
    callback = _pending.pop(data.id, None)
    if callback is None:
        return
    if getattr(data, 'error', None):
        callback[1](PyodideError(str(data.error)))
        return
    if getattr(data.result, 'kind', None) == 'ndimage':
        callback[0]({
            'pixels': data.result.pixels,
            'width': int(data.result.width),
            'height': int(data.result.height),
            'measurement': float(data.result.measurement)
        })
        return
    try:
        callback[0](json.loads(str(window.JSON.stringify(data.result))))
    except Exception as error:
        callback[1](PyodideError(str(error)))


def _handle_worker_error(event):
    global _worker
    message = str(getattr(event, 'message', 'Pyodide worker failed'))
    callbacks = list(_pending.values())
    _pending.clear()
    if _worker is not None:
        _worker.terminate()
        _worker = None
    for resolve, reject in callbacks:
        reject(PyodideError(message))


def _get_worker():
    global _worker
    if _worker is None:
        _worker = window.Worker.new(_WORKER_PATH)
        _worker.onmessage = _handle_message
        _worker.onerror = _handle_worker_error
    return _worker


async def _request(operation, payload):
    global _next_request_id
    _next_request_id += 1
    request_id = _next_request_id
    worker = _get_worker()

    def executor(resolve, reject):
        _pending[request_id] = (resolve, reject)
        worker.postMessage({
            'id': request_id,
            'operation': operation,
            'payload': payload
        })

    try:
        return await window.Promise.new(executor)
    except PyodideError:
        raise
    except Exception as error:
        _pending.pop(request_id, None)
        raise PyodideError(str(error))


async def root(equations, x0, variables=None):
    """Solve a nonlinear system with ``scipy.optimize.root``.

    Equations are residual expressions equal to zero. ``variables`` maps names
    to the ordered values in ``x0`` and defaults to ``x0``, ``x1``, etc.
    """
    equations = [str(equation).strip() for equation in equations]
    x0 = [float(value) for value in x0]
    if not equations or len(equations) != len(x0) or len(x0) > 8:
        raise ValueError('Provide 1-8 equations and the same number of initial values')
    if any(not equation or len(equation) > 512 for equation in equations):
        raise ValueError('Each residual must contain 1-512 characters')
    if variables is None:
        variables = ['x' + str(index) for index in range(len(x0))]
    else:
        variables = [str(name).strip() for name in variables]
    if (len(variables) != len(x0) or len(set(variables)) != len(variables)
            or any(not name.isidentifier() for name in variables)):
        raise ValueError('Variable names must be unique identifiers matching x0')
    return await _request('root', {
        'equations': equations,
        'x0': x0,
        'variables': variables
    })


async def linprog(c, A_ub=None, b_ub=None, A_eq=None, b_eq=None, bounds=None, method='highs'):
    """Minimize a linear objective using ``scipy.optimize.linprog``."""
    if not c:
        raise ValueError('The objective coefficients cannot be empty')
    return await _request('linprog', {
        'c': c,
        'A_ub': A_ub,
        'b_ub': b_ub,
        'A_eq': A_eq,
        'b_eq': b_eq,
        'bounds': bounds,
        'method': method
    })


async def ndimage(pixels, width, height, operation):
    """Apply a supported scipy.ndimage operation to an RGBA image buffer."""
    width = int(width)
    height = int(height)
    if width < 1 or height < 1 or width > 384 or height > 384:
        raise ValueError('Image dimensions must be between 1 and 384 pixels')
    if len(pixels) != width * height * 4:
        raise ValueError('RGBA buffer length does not match image dimensions')
    if operation not in ('gaussian', 'sobel', 'opening'):
        raise ValueError('Unsupported image operation')
    return await _request('ndimage', {
        'pixels': pixels,
        'width': width,
        'height': height,
        'operation': operation
    })


__all__ = ['root', 'linprog', 'ndimage', 'PyodideError']
