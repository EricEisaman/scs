importScripts('https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js');

let runtimePromise;
let requestQueue = Promise.resolve();

function getRuntime() {
  if (!runtimePromise) {
    runtimePromise = loadPyodide({
      indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/'
    }).then(async (pyodide) => {
      await pyodide.loadPackage('scipy');
      return pyodide;
    });
  }
  return runtimePromise;
}

function encodePayload(payload) {
  return JSON.stringify(JSON.stringify(payload));
}

async function solveRoot(pyodide, payload) {
  const code = `
import ast, json, numpy as np
from scipy.optimize import root as _scipy_root
_payload = json.loads(${encodePayload(payload)})
_names, _equations = _payload['variables'], _payload['equations']
_allowed_nodes = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub,
    ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.USub, ast.UAdd, ast.Constant,
    ast.Name, ast.Call, ast.Load)
_functions = {
    'abs': np.abs, 'sqrt': np.sqrt, 'sin': np.sin, 'cos': np.cos,
  'tan': np.tan, 'sec': lambda x: 1 / np.cos(x),
  'csc': lambda x: 1 / np.sin(x), 'cot': lambda x: np.cos(x) / np.sin(x),
  'asin': np.arcsin, 'acos': np.arccos, 'atan': np.arctan,
  'exp': np.exp, 'log': lambda x, base=10: np.log(x) / np.log(base),
  'ln': np.log, 'log10': np.log10,
    'sinh': np.sinh, 'cosh': np.cosh, 'tanh': np.tanh,
    'pi': np.pi, 'e': np.e
}
_trees = [ast.parse(eq, mode='eval') for eq in _equations]
for _tree in _trees:
    for _node in ast.walk(_tree):
        if not isinstance(_node, _allowed_nodes):
            raise ValueError('Unsupported expression syntax')
        if isinstance(_node, ast.Name) and _node.id not in _names and _node.id not in _functions:
            raise ValueError('Unknown symbol: ' + _node.id)
        if isinstance(_node, ast.Call) and (not isinstance(_node.func, ast.Name) or _node.func.id not in _functions):
            raise ValueError('Unsupported function call')
def _system(_x):
    _environment = dict(_functions)
    _environment.update({name: _x[i] for i, name in enumerate(_names)})
    return [eval(compile(tree, '<equation>', 'eval'), {'__builtins__': {}}, _environment) for tree in _trees]
_initial = _system(np.asarray(_payload['x0'], dtype=float))
_result = _scipy_root(_system, _payload['x0'])
json.dumps({
    'x': _result.x.tolist(),
    'fun': np.asarray(_result.fun).tolist(),
    'initialResidualNorm': float(np.linalg.norm(_initial)),
    'residualNorm': float(np.linalg.norm(_result.fun)),
    'success': bool(_result.success),
    'message': str(_result.message),
    'nfev': int(_result.nfev)
})
`;
  return JSON.parse(await pyodide.runPythonAsync(code));
}

async function solveLinearProgram(pyodide, payload) {
  const code = `
import json
from scipy.optimize import linprog as _scipy_linprog
_payload = json.loads(${encodePayload(payload)})
_result = _scipy_linprog(
    _payload['c'], A_ub=_payload.get('A_ub'), b_ub=_payload.get('b_ub'),
    A_eq=_payload.get('A_eq'), b_eq=_payload.get('b_eq'),
    bounds=_payload.get('bounds'), method=_payload.get('method', 'highs'))
json.dumps({
    'x': None if _result.x is None else _result.x.tolist(),
    'fun': None if _result.fun is None else float(_result.fun),
    'success': bool(_result.success),
    'message': str(_result.message),
    'status': int(_result.status),
    'nit': int(_result.nit)
})
`;
  return JSON.parse(await pyodide.runPythonAsync(code));
}

async function solveNdimage(pyodide, payload) {
  const pixelProxy = pyodide.toPy(payload.pixels);
  pyodide.globals.set('_scs_rgba_buffer', pixelProxy);
  try {
    const code = `
import base64, json, numpy as np
from scipy import ndimage as ndi
_width, _height = ${Number(payload.width)}, ${Number(payload.height)}
_operation = ${JSON.stringify(payload.operation)}
_rgba = np.frombuffer(_scs_rgba_buffer, dtype=np.uint8).reshape((_height, _width, 4))
_rgb = _rgba[:, :, :3].astype(np.float32)
_gray = np.dot(_rgb, np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))
if _operation == 'gaussian':
    _output_rgb = np.stack([
        ndi.gaussian_filter(_rgb[:, :, channel], sigma=1.6, mode='reflect')
        for channel in range(3)
    ], axis=2)
    _measurement = 1.6
elif _operation == 'sobel':
    _gx = ndi.sobel(_gray, axis=1, mode='reflect')
    _gy = ndi.sobel(_gray, axis=0, mode='reflect')
    _magnitude = np.hypot(_gx, _gy)
    _peak = float(_magnitude.max())
    _output_gray = (_magnitude * (255.0 / _peak)) if _peak > 0 else _magnitude
    _output_rgb = np.repeat(_output_gray[:, :, None], 3, axis=2)
    _measurement = float(np.count_nonzero(_magnitude > _peak * 0.15) * 100.0 / _magnitude.size) if _peak > 0 else 0.0
elif _operation == 'opening':
    _threshold = float(np.percentile(_gray, 60))
    _mask = _gray >= _threshold
    _opened = ndi.binary_opening(_mask, structure=np.ones((3, 3), dtype=bool))
    _output_gray = _opened.astype(np.uint8) * 255
    _output_rgb = np.repeat(_output_gray[:, :, None], 3, axis=2)
    _measurement = float(np.count_nonzero(_opened) * 100.0 / _opened.size)
else:
    raise ValueError('Unsupported image operation')
_output = np.empty((_height, _width, 4), dtype=np.uint8)
_output[:, :, :3] = np.clip(_output_rgb, 0, 255).astype(np.uint8)
_output[:, :, 3] = 255
json.dumps({
    'rgba': base64.b64encode(_output.tobytes()).decode('ascii'),
    'measurement': _measurement
})
`;
    const encoded = JSON.parse(await pyodide.runPythonAsync(code));
    const binary = atob(encoded.rgba);
    const pixels = new Uint8ClampedArray(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      pixels[index] = binary.charCodeAt(index);
    }
    return {
      kind: 'ndimage',
      pixels,
      width: payload.width,
      height: payload.height,
      measurement: encoded.measurement
    };
  } finally {
    pyodide.globals.delete('_scs_rgba_buffer');
    pixelProxy.destroy();
  }
}

async function handleRequest({ id, operation, payload }) {
  const pyodide = await getRuntime();
  if (operation === 'root') return solveRoot(pyodide, payload);
  if (operation === 'linprog') return solveLinearProgram(pyodide, payload);
  if (operation === 'ndimage') return solveNdimage(pyodide, payload);
  throw new Error('Unsupported Pyodide operation');
}

self.onmessage = ({ data }) => {
  requestQueue = requestQueue
    .then(() => handleRequest(data))
    .then((result) => {
      if (result && result.pixels instanceof Uint8ClampedArray) {
        self.postMessage({ id: data.id, result }, [result.pixels.buffer]);
      } else {
        self.postMessage({ id: data.id, result });
      }
    })
    .catch((error) => self.postMessage({
      id: data.id,
      error: String(error && error.message || error)
    }));
};
