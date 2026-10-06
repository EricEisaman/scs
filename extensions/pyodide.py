"""extensions/pyodide.py - Proper aio bridge + direct JsProxy -> Python conversion
No JSON stringify/parse for large arrays - avoids Brython json.loads Array(2) bug
"""

import json
import math
from browser import window, aio

_WORKER_PATH = './extensions/pyodide_worker.js'
_worker = None
_pending = {}  # id -> {done, result, error}
_next_id = 0

class PyodideError(Exception):
    pass

def _on_message(event):
    data = event.data
    rid = getattr(data, 'id', None)
    try:
        rid = int(rid)
    except Exception:
        return
    entry = _pending.pop(rid, None)
    if entry is None:
        return
    window.clearTimeout(entry['timer'])
    err = getattr(data, 'error', None)
    if 'callback' in entry:
        if err:
            entry['callback'](None, PyodideError(str(err)))
        else:
            try:
                result = _decode_result(getattr(data, 'result', None))
            except Exception as error:
                entry['callback'](None, PyodideError(f'Decode failed: {error}'))
                return
            entry['callback'](result, None)
        return
    if err:
        entry['future'].set_exception(PyodideError(str(err)))
    else:
        entry['future'].set_result(getattr(data, 'result', None))

def _on_timeout(rid):
    entry = _pending.pop(rid, None)
    if entry is not None:
        error = PyodideError('Pyodide worker timeout')
        if 'callback' in entry:
            entry['callback'](None, error)
        else:
            entry['future'].set_exception(error)

def _on_error(event):
    global _worker
    msg = str(getattr(event, 'message', 'Pyodide worker failed'))
    pending = list(_pending.values())
    _pending.clear()
    for entry in pending:
        window.clearTimeout(entry['timer'])
    if _worker is not None:
        try:
            _worker.terminate()
        except Exception:
            pass
        _worker = None
    for entry in pending:
        error = PyodideError(msg)
        if 'callback' in entry:
            entry['callback'](None, error)
        else:
            entry['future'].set_exception(error)

def _get_worker():
    global _worker
    if _worker is None:
        _worker = window.Worker.new(_WORKER_PATH)
        _worker.onmessage = _on_message
        _worker.onerror = _on_error
    return _worker

def _post_callback_request(op, payload, callback):
    global _next_id
    _next_id += 1
    rid = _next_id
    timer_id = window.setTimeout(lambda: _on_timeout(rid), 60000)
    _pending[rid] = {'callback': callback, 'timer': timer_id}
    try:
        _get_worker().postMessage({'id': rid, 'operation': op, 'payload': payload})
    except Exception as error:
        entry = _pending.pop(rid, None)
        if entry is not None:
            window.clearTimeout(entry['timer'])
        callback(None, PyodideError(f'postMessage failed: {error}'))

async def _request(op, payload):
    global _next_id
    _next_id += 1
    rid = _next_id
    future = aio.Future()
    timer_id = window.setTimeout(lambda: _on_timeout(rid), 60000)
    entry = {'future': future, 'timer': timer_id}
    _pending[rid] = entry
    try:
        _get_worker().postMessage({'id': rid, 'operation': op, 'payload': payload})
    except Exception as error:
        _pending.pop(rid, None)
        window.clearTimeout(timer_id)
        raise PyodideError(f'postMessage failed: {error}')

    js_res = await future

    return _decode_result(js_res)

def _decode_result(js_res):
    try:
        kind = getattr(js_res, 'kind', None)
    except Exception:
        kind = None
    if kind == 'ndimage':
        return {
            'pixels': js_res.pixels,
            'width': int(js_res.width),
            'height': int(js_res.height),
            'measurement': float(js_res.measurement)
        }
    if kind == 'ode':
        try:
            packed = json.loads(str(window.JSON.stringify(js_res)))

            def unpack_series(value):
                return [float(item) for item in value.split(',') if item]

            packed['t'] = unpack_series(packed['t'])
            packed['y'] = [unpack_series(row) for row in packed['y']]
            return packed
        except Exception as error:
            raise PyodideError(f'Decode failed: {error}')

    try:
        result = json.loads(str(window.JSON.stringify(js_res)))
    except Exception as e:
        raise PyodideError(f'Decode failed: {e}')
    if not isinstance(result, dict):
        raise PyodideError('Worker returned an invalid result object')
    return result

# --- validators ---

def _vf(vals, name, mn=1, mx=8):
    if not isinstance(vals, (list, tuple)):
        raise ValueError(f'{name} list required')
    if not (mn <= len(vals) <= mx):
        raise ValueError(f'{name} {mn}-{mx}')
    out=[]
    for v in vals:
        try: out.append(float(v))
        except: raise ValueError(f'{name} numbers')
    return out

def _vs(exprs, name, mn=1, mx=8):
    if not isinstance(exprs, (list, tuple)):
        raise ValueError(f'{name} list required')
    if not (mn <= len(exprs) <= mx):
        raise ValueError(f'{name} {mn}-{mx}')
    out=[]
    for e in exprs:
        s=str(e).strip()
        if not s or len(s)>512: raise ValueError(f'{name} 1-512')
        out.append(s)
    return out

async def root(equations, x0, variables=None):
    equations=_vs(equations,'equations')
    x0=_vf(x0,'x0',len(equations),len(equations))
    if variables is None:
        variables=[f'x{i}' for i in range(len(x0))]
    else:
        variables=[str(n).strip() for n in variables]
        if len(variables)!=len(x0) or len(set(variables))!=len(variables) or any(not n.isidentifier() for n in variables):
            raise ValueError('variables identifiers')
    return await _request('root',{'equations':equations,'x0':x0,'variables':variables})

async def linprog(c, A_ub=None, b_ub=None, A_eq=None, b_eq=None, bounds=None, method='highs'):
    c=_vf(c,'c',1,64)
    return await _request('linprog',{'c':c,'A_ub':A_ub,'b_ub':b_ub,'A_eq':A_eq,'b_eq':b_eq,'bounds':bounds,'method':method})

async def solve_ivp(odes, y0, t_span, params=None, method='RK45', t_eval=None, var_names=None):
    payload = _solve_ivp_payload(odes, y0, t_span, params, method, t_eval, var_names)
    return await _request('solve_ivp', payload)

def solve_ivp_callback(odes, y0, t_span, callback, params=None, method='RK45', t_eval=None, var_names=None):
    payload = _solve_ivp_payload(odes, y0, t_span, params, method, t_eval, var_names)
    _post_callback_request('solve_ivp', payload, callback)

def _solve_ivp_payload(odes, y0, t_span, params, method, t_eval, var_names):
    odes=_vs(odes,'odes')
    y0=_vf(y0,'y0',len(odes),len(odes))
    if not isinstance(t_span,(list,tuple)) or len(t_span)!=2: raise ValueError('t_span 2 numbers')
    t_span=[float(t_span[0]),float(t_span[1])]
    if t_span[0]==t_span[1]: raise ValueError('t_span distinct')
    p={}
    for k,v in (params or {}).items():
        if not str(k).isidentifier(): raise ValueError('param key id')
        p[str(k)]=float(v)
    if method not in {'RK45','RK23','DOP853','BDF','Radau','LSODA'}: raise ValueError('method')
    if t_eval is None: te=500
    elif isinstance(t_eval,int):
        if not (10<=t_eval<=2000): raise ValueError('t_eval 10-2000')
        te=int(t_eval)
    else: te=_vf(t_eval,'t_eval',2,2000)
    if var_names is None: var_names=[f'y{i}' for i in range(len(y0))]
    return {'odes':odes,'y0':y0,'t_span':t_span,'params':p,'method':method,'t_eval':te,'var_names':var_names}

async def odeint(odes, y0, t, params=None, var_names=None):
    odes=_vs(odes,'odes')
    y0=_vf(y0,'y0',len(odes),len(odes))
    t_pts=_vf(t,'t',2,2000)
    p={}
    for k,v in (params or {}).items(): p[str(k)]=float(v)
    if var_names is None: var_names=[f'y{i}' for i in range(len(y0))]
    return await _request('odeint',{'odes':odes,'y0':y0,'t':t_pts,'params':p,'var_names':var_names})

async def ndimage(pixels, width, height, operation):
    width=int(width); height=int(height)
    if not (1<=width<=384 and 1<=height<=384): raise ValueError('1-384')
    if len(pixels)!=width*height*4: raise ValueError('RGBA')
    if operation not in ('gaussian','sobel','opening'): raise ValueError('op')
    return await _request('ndimage',{'pixels':pixels,'width':width,'height':height,'operation':operation})

__all__=['root','linprog','solve_ivp','solve_ivp_callback','odeint','ndimage','PyodideError']
