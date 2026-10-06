from scs import *
from browser import document
from extensions.pyodide import solve_ivp_callback
import math

BG = rgb(15, 20, 23)
INK = rgb(229, 238, 232)
MUTED = rgb(137, 157, 151)
MINT = rgb(102, 224, 177)
GOLD = rgb(244, 190, 92)
RED = rgb(244, 111, 104)
BLUE = rgb(114, 159, 255)
CYAN = rgb(86, 211, 255)
ORANGE = rgb(255, 166, 77)

_PANEL_ID = 'ode-solver-controls'

_EXAMPLES = {
    'pendulum': {
        'label': 'Physics: Nonlinear Pendulum',
        'desc': "theta'' + (g/L) sin(theta) + b theta' = 0",
        'var_names': ['theta', 'omega'],
        'odes': ['y[1]', '-(g/L)*sin(y[0]) - b*y[1]'],
        'y0': '1.0, 0.0',
        't_span': '0, 20',
        'params': {'g': 9.81, 'L': 1.0, 'b': 0.1},
        'method': 'RK45',
    },
    'lorenz': {
        'label': 'Physics: Lorenz Attractor',
        'desc': 'dx/dt=s(y-x), dy/dt=x(r-z)-y, dz/dt=xy - b z',
        'var_names': ['x', 'y', 'z'],
        'odes': ['sigma*(y[1]-y[0])', 'y[0]*(rho - y[2]) - y[1]', 'y[0]*y[1] - beta*y[2]'],
        'y0': '1, 0, 0',
        't_span': '0, 25',
        'params': {'sigma': 10.0, 'rho': 28.0, 'beta': 2.6666667},
        'method': 'RK45',
    },
    'msd': {
        'label': 'Mech: Mass-Spring-Damper',
        'desc': "m x'' + c x' + k x = 0",
        'var_names': ['x', 'v'],
        'odes': ['y[1]', '-(k/m)*y[0] - (c/m)*y[1]'],
        'y0': '1.0, 0.0',
        't_span': '0, 15',
        'params': {'m': 1.0, 'k': 4.0, 'c': 0.5},
        'method': 'RK45',
    },
    'duffing': {
        'label': 'Mech: Duffing Oscillator',
        'desc': "x''+ d x' + a x + b x^3 = g cos(w t)",
        'var_names': ['x', 'v'],
        'odes': ['y[1]', '-delta*y[1] - alpha*y[0] - beta*y[0]**3 + gamma*cos(omega*t)'],
        'y0': '0.5, 0.0',
        't_span': '0, 40',
        'params': {'delta': 0.2, 'alpha': -1.0, 'beta': 1.0, 'gamma': 0.3, 'omega': 1.2},
        'method': 'RK45',
    },
    'consecutive': {
        'label': 'Chem: Consecutive A->B->C',
        'desc': 'A --k1--> B --k2--> C',
        'var_names': ['A', 'B', 'C'],
        'odes': ['-k1*y[0]', 'k1*y[0] - k2*y[1]', 'k2*y[1]'],
        'y0': '1.0, 0.0, 0.0',
        't_span': '0, 50',
        'params': {'k1': 0.3, 'k2': 0.1},
        'method': 'BDF',
    },
    'brusselator': {
        'label': 'Chem: Brusselator',
        'desc': 'dx/dt=A-(B+1)x+x^2 y, dy/dt=Bx - x^2 y',
        'var_names': ['X', 'Y'],
        'odes': ['A - (B+1)*y[0] + y[0]**2*y[1]', 'B*y[0] - y[0]**2*y[1]'],
        'y0': '1.0, 1.0',
        't_span': '0, 30',
        'params': {'A': 1.0, 'B': 3.0},
        'method': 'RK45',
    }
}

COLORS = [MINT, GOLD, BLUE, RED, CYAN]

def _parse_csv(s):
    return [float(v.strip()) for v in s.split(',') if v.strip()!='']

def _safe_get(d, k, default=None):
    if d is None:
        return default
    try:
        if isinstance(d, dict):
            return d.get(k, default)
    except Exception:
        pass
    try:
        v = getattr(d, k, None)
        if v is not None:
            return v
    except Exception:
        pass
    try:
        return d[k]
    except Exception:
        return default

def _get_min_max(arr):
    try:
        clean = [float(x) for x in arr if x is not None]
        if not clean:
            return -1, 1
        lo = min(clean); hi = max(clean)
    except Exception:
        return -1, 1
    if abs(hi-lo) < 1e-12:
        return lo-1, hi+1
    pad = (hi-lo)*0.08
    return lo-pad, hi+pad

def _scale(v, s0, s1, d0, d1):
    try:
        if s1==s0:
            return (d0+d1)/2
        return d0 + (v-s0)/(s1-s0)*(d1-d0)
    except Exception:
        return (d0+d1)/2

def _install_controls(app):
    existing = document.getElementById(_PANEL_ID)
    if existing:
        existing.parentNode.removeChild(existing)
    panel = document.createElement('section')
    panel.id = _PANEL_ID
    panel.style.cssText = 'box-sizing:border-box;width:1050px;max-width:95vw;padding:20px 24px 18px;margin:0 0 12px;background:#191f22;border:1px solid #34413e;color:#e5eee8;font:13px/1.45 ui-monospace;'
    opts = ''.join(f'<option value="{k}"{" selected" if k==app.currentKey else ""}>{v["label"]}</option>' for k,v in _EXAMPLES.items())
    panel.innerHTML = f'''
      <div style="display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:14px">
        <strong style="font-size:18px;color:#66e0b1">ODE Solver</strong>
        <span style="color:#899d97">scipy · live simulation</span>
      </div>
      <form id="ode-form" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;align-items:end">
        <label style="display:grid;grid-column:1/-1;gap:6px;color:#b6c6bf">Example
          <select id="ode-example" style="width:100%;max-width:560px;background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:10px;font:13px ui-monospace">{opts}</select>
        </label>
        <label style="display:grid;gap:6px;color:#b6c6bf">Initial y0
          <input id="ode-y0" value="{app.y0_str}" style="background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:10px;font:13px ui-monospace">
        </label>
        <label style="display:grid;gap:6px;color:#b6c6bf">Time t0,tf
          <input id="ode-tspan" value="{app.t_span_str}" style="background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:10px;font:13px ui-monospace">
        </label>
        <label style="display:grid;gap:6px;color:#b6c6bf">Method
          <select id="ode-method" style="background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:10px;font:13px ui-monospace">
            <option>RK45</option><option>RK23</option><option>DOP853</option><option>BDF</option><option>Radau</option><option>LSODA</option>
          </select>
        </label>
        <button type="submit" style="height:39px;padding:0 16px;border:0;background:#66e0b1;color:#10201a;font-weight:bold;cursor:pointer">Integrate</button>
      </form>
      <div id="ode-desc" style="margin-top:10px;color:#899d97">{app.desc}</div>
      <div style="margin-top:6px;color:#5a6e69;font-size:11px">SPACE play/pause · R restart</div>
    '''
    document.getElementById('canvas-container').parentNode.insertBefore(panel, document.getElementById('canvas-container'))
    def submit(e):
        e.preventDefault()
        try:
            y0=_parse_csv(document['ode-y0'].value); t_span=_parse_csv(document['ode-tspan'].value)
            if len(t_span)!=2: raise ValueError('t_span 2')
        except Exception as err:
            app.error=str(err); app.status='Check inputs'; return
        app.y0=y0; app.y0_str=document['ode-y0'].value
        app.t_span=t_span; app.t_span_str=document['ode-tspan'].value
        app.method=document['ode-method'].value
        _start_solve(app)
    def load_ex(e):
        k=document['ode-example'].value; cfg=_EXAMPLES[k]
        app.currentKey=k; app.var_names=cfg['var_names']; app.odes=cfg['odes']; app.params=cfg['params']; app.desc=cfg['desc']
        app.y0_str=cfg['y0']; app.t_span_str=cfg['t_span']; app.method=cfg['method']
        document['ode-y0'].value=cfg['y0']; document['ode-tspan'].value=cfg['t_span']; document['ode-method'].value=cfg['method']
        document['ode-desc'].textContent=cfg['desc']
        app.y0=_parse_csv(cfg['y0']); app.t_span=_parse_csv(cfg['t_span'])
        _start_solve(app)
    document['ode-example'].bind('change', load_ex)
    document['ode-form'].bind('submit', submit)
    try:
        document['ode-method'].value = app.method
    except Exception:
        pass

def _start_solve(app):
    app.solve_id += 1
    app.result=None; app.error=None; app.playing=False
    app.status=f'Starting {app.method}...'; app.busy=True; app.t_idx=0
    solve_id = app.solve_id
    def completed(result, error):
        if solve_id != app.solve_id:
            return
        app.busy = False
        if error is not None:
            app.error = str(error)
            app.status = 'Solve failed'
            app.result = None
            return
        app.result = result
        msg = _safe_get(result, 'message', '')
        succ = _safe_get(result, 'success', False)
        sample_count = len(_safe_get(result, 't', []))
        summary = f'{sample_count} samples · playing'
        app.status = (str(msg) + ' · ' + summary) if msg else ('Success · ' + summary if succ else 'Failed · ' + summary)
        app.playing = True
        app.t_idx = 0
        app.error = None
    try:
        solve_ivp_callback(
            app.odes, app.y0, app.t_span, completed,
            params=app.params, method=app.method,
            var_names=app.var_names, t_eval=200
        )
    except Exception as e:
        if solve_id == app.solve_id:
            app.busy = False
            app.error = str(e)
            app.status = 'Solve failed'
            app.result = None

def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=30; app.background=BG
    app.currentKey='pendulum'; cfg=_EXAMPLES[app.currentKey]
    app.var_names=cfg['var_names']; app.odes=cfg['odes']; app.params=cfg['params']; app.desc=cfg['desc']
    app.y0_str=cfg['y0']; app.t_span_str=cfg['t_span']; app.method=cfg['method']
    app.y0=_parse_csv(cfg['y0']); app.t_span=_parse_csv(cfg['t_span'])
    app.status='Ready'; app.busy=False; app.error=None; app.result=None
    app.playing=False; app.t_idx=0; app.play_speed=2
    app.solve_id=0
    _install_controls(app)
    _start_solve(app)

def onStep(app):
    if app.result and app.playing:
        try:
            n = len(_safe_get(app.result, 't', []))
            if n>0:
                app.t_idx = (app.t_idx + app.play_speed) % n
        except Exception:
            pass

def onKeyPress(app, key):
    if key == 'space':
        if app.result:
            app.playing = not app.playing
    elif key.lower() == 'r':
        app.t_idx = 0
        app.playing = True

def _current_state(app):
    if not app.result:
        return app.t_span[0], app.y0
    try:
        t_arr = _safe_get(app.result, 't', [])
        y_arr = _safe_get(app.result, 'y', [])
        idx = int(app.t_idx) % len(t_arr) if t_arr else 0
        t = float(t_arr[idx]) if t_arr else 0.0
        y = [row[idx] for row in y_arr] if y_arr else app.y0
        return t, y
    except Exception:
        return app.t_span[0], app.y0

def _draw_simulation(app, sx, sy, sw, sh):
    drawRect(sx, sy, sw, sh, fill=rgb(22,30,33), border=rgb(52,65,62), borderWidth=1)
    key = app.currentKey
    t_cur, y_cur = _current_state(app)
    if not y_cur or len(y_cur)==0:
        y_cur = app.y0
    try:
        y_cur = [float(v) if v is not None else 0.0 for v in y_cur]
    except Exception:
        y_cur = app.y0
    if key == 'pendulum':
        drawLabel('PENDULUM', sx+12, sy+18, size=11, fill=MUTED, align='left')
        pivot_x = sx + sw*0.5; pivot_y = sy + 70; Lpix = 160
        theta = y_cur[0] if len(y_cur)>0 else 0
        bob_x = pivot_x + Lpix*math.sin(theta)
        bob_y = pivot_y + Lpix*math.cos(theta)
        drawLine(pivot_x, pivot_y, bob_x, bob_y, fill=rgb(90,110,105), lineWidth=2)
        drawCircle(pivot_x, pivot_y, 6, fill=GOLD)
        v = y_cur[1] if len(y_cur)>1 else 0
        col = MINT if abs(v)<2 else GOLD
        drawCircle(bob_x, bob_y, 18, fill=col, border=INK, borderWidth=2)
        drawLabel(f'theta={y_cur[0]:.2f} omega={y_cur[1]:.2f} t={t_cur:.1f}' if len(y_cur)>1 else f'theta={y_cur[0]:.2f}', sx+12, sy+sh-14, size=11, fill=INK, align='left')
    elif key == 'lorenz':
        drawLabel('LORENZ x-y', sx+12, sy+18, size=11, fill=MUTED, align='left')
        if not app.result:
            drawLabel('Integrate to see', sx+sw//2, sy+sh//2, size=13, fill=MUTED, align='center')
            return
        try:
            y_all = _safe_get(app.result,'y',[])
            if len(y_all) < 2:
                return
            xs = y_all[0]; ys = y_all[1]
            x_min,x_max = _get_min_max(xs); y_min,y_max = _get_min_max(ys)
            start = max(0, int(app.t_idx)-350)
            for j in range(start, int(app.t_idx)):
                if j+1 >= len(xs) or j+1 >= len(ys): break
                x1 = _scale(xs[j], x_min, x_max, sx+20, sx+sw-20)
                y1 = _scale(ys[j], y_min, y_max, sy+sh-20, sy+30)
                x2 = _scale(xs[j+1], x_min, x_max, sx+20, sx+sw-20)
                y2 = _scale(ys[j+1], y_min, y_max, sy+sh-20, sy+30)
                drawLine(x1,y1,x2,y2, fill=GOLD, lineWidth=1)
            if len(y_cur) >= 2:
                cx = _scale(y_cur[0], x_min, x_max, sx+20, sx+sw-20)
                cy = _scale(y_cur[1], y_min, y_max, sy+sh-20, sy+30)
                drawCircle(cx, cy, 6, fill=RED, border=INK)
        except Exception:
            pass
    elif key == 'msd':
        drawLabel('MASS-SPRING-DAMPER', sx+12, sy+18, size=11, fill=MUTED, align='left')
        wall_x = sx+20; base_y = sy+sh*0.5; scale=70
        x_phys = y_cur[0]; mass_w, mass_h = 60, 40
        mass_x = sx+sw*0.5 + x_phys*scale
        segs=10; dx=(mass_x-wall_x)/segs if segs else 0
        px=wall_x; py=base_y
        for i in range(segs):
            nx=px+dx; ny=base_y + (10 if i%2==0 else -10) if i < segs-1 else base_y
            drawLine(px, py, nx, ny, fill=MUTED, lineWidth=2)
            px, py = nx, ny
        drawRect(mass_x-mass_w//2, base_y-mass_h//2, mass_w, mass_h, fill=BLUE, border=INK, borderWidth=2)
    elif key == 'duffing':
        drawLabel('DUFFING', sx+12, sy+18, size=11, fill=MUTED, align='left')
        a = app.params.get('alpha', -1); b = app.params.get('beta', 1)
        prev=None
        for px in range(sx+20, sx+sw-20, 3):
            x_val=(px-(sx+sw*0.5))/60.0
            V=a*x_val*x_val*0.5 + b*x_val**4*0.25
            py=sy+sh*0.75 - V*35
            if prev: drawLine(prev[0], prev[1], px, py, fill=rgb(80,90,90), lineWidth=1)
            prev=(px,py)
        mx=sx+sw*0.5 + y_cur[0]*60
        my=sy+sh*0.75 - (a*y_cur[0]*y_cur[0]*0.5 + b*y_cur[0]**4*0.25)*35 - 12
        drawCircle(mx, my, 9, fill=ORANGE, border=INK, borderWidth=2)
    elif key == 'consecutive':
        drawLabel('A->B->C', sx+12, sy+18, size=11, fill=MUTED, align='left')
        beaker_w=80; beaker_h=170; gap=35
        start_x = sx + (sw - (3*beaker_w+2*gap))//2
        by=sy+60
        conc=y_cur if len(y_cur)>=3 else app.y0
        try:
            max_c=max(1.0, max([float(c) for c in conc if c is not None]))
        except Exception:
            max_c=1.0
        cols=[BLUE,GOLD,MINT]; labels=['A','B','C']
        for i in range(3):
            bx=start_x + i*(beaker_w+gap)
            drawRect(bx, by, beaker_w, beaker_h, fill=rgb(30,40,43), border=rgb(80,90,90), borderWidth=2)
            try:
                ci = float(conc[i]) if i < len(conc) else 0
            except Exception:
                ci=0
            h=(ci/max_c)*(beaker_h-6)
            drawRect(bx+3, by+beaker_h-3-h, beaker_w-6, h, fill=cols[i])
            drawLabel(f'{labels[i]}={ci:.2f}', bx+beaker_w//2, by+beaker_h+18, size=12, fill=INK, align='center')
    elif key == 'brusselator':
        drawLabel('BRUSSELATOR', sx+12, sy+18, size=11, fill=MUTED, align='left')
        bar_w=70; bar_h=150; bx1=sx+70; by=sy+70; bx2=sx+sw-70-bar_w; max_c=3.5
        try:
            h1=(float(y_cur[0])/max_c)*bar_h if len(y_cur)>0 else 0
            h2=(float(y_cur[1])/max_c)*bar_h if len(y_cur)>1 else 0
        except Exception:
            h1=h2=0
        drawRect(bx1, by, bar_w, bar_h, fill=rgb(30,40,43), border=MUTED)
        drawRect(bx1, by+bar_h-h1, bar_w, h1, fill=CYAN)
        drawRect(bx2, by, bar_w, bar_h, fill=rgb(30,40,43), border=MUTED)
        drawRect(bx2, by+bar_h-h2, bar_w, h2, fill=RED)

def _draw_plots(app, px, py, pw, ph):
    drawRect(px, py, pw, ph, fill=rgb(22,30,33), border=rgb(52,65,62), borderWidth=1)
    if not app.result:
        drawLabel('TIME SERIES', px+12, py+18, size=11, fill=MUTED, align='left')
        return
    try:
        t = _safe_get(app.result,'t',[]); y = _safe_get(app.result,'y',[])
        if not t or not y: return
        t_min,t_max = _get_min_max(t)
        all_y=[]
        for row in y:
            for v in row:
                try:
                    if v is not None:
                        all_y.append(float(v))
                except Exception:
                    pass
        y_min,y_max = _get_min_max(all_y)
        drawLabel(f't=[{t_min:.1f},{t_max:.1f}]', px+12, py+18, size=11, fill=MUTED, align='left')
        for idx in range(len(y)):
            col=COLORS[idx%len(COLORS)]
            try:
                drawRect(px+12+idx*70, py+ph-22, 10, 10, fill=col)
                drawLabel(app.var_names[idx], px+26+idx*70, py+ph-16, size=11, fill=INK, align='left')
                for j in range(len(t)-1):
                    try:
                        y1v = y[idx][j]; y2v = y[idx][j+1]
                        if y1v is None or y2v is None: continue
                        x1=_scale(t[j], t_min, t_max, px+10, px+pw-10)
                        x2=_scale(t[j+1], t_min, t_max, px+10, px+pw-10)
                        yy1=_scale(float(y1v), y_min, y_max, py+ph-35, py+35)
                        yy2=_scale(float(y2v), y_min, y_max, py+ph-35, py+35)
                        drawLine(x1,yy1,x2,yy2, fill=col, lineWidth=2)
                    except Exception:
                        continue
            except Exception:
                continue
        try:
            ct = t[int(app.t_idx)%len(t)] if t else 0
            cx=_scale(ct, t_min, t_max, px+10, px+pw-10)
            drawLine(cx, py+30, cx, py+ph-35, fill=rgb(90,110,105), lineWidth=1)
        except Exception:
            pass
    except Exception:
        pass

def redrawAll(app):
    drawRect(0,0,app.width,app.height, fill=BG)
    drawLabel('ORDINARY DIFFERENTIAL EQUATIONS', 54, 48, size=21, fill=INK, bold=True, align='left')
    drawLine(54, 78, 996, 78, fill=rgb(55,69,64), lineWidth=1)
    try:
        if app.busy: col=GOLD
        elif app.result and _safe_get(app.result,'success',False): col=MINT
        elif app.error: col=RED
        else: col=MUTED
    except Exception:
        col=MUTED
    drawLabel(app.status, 54, 104, size=12, fill=col, align='left')
    if app.error:
        drawLabel(str(app.error)[:110], 54, 124, size=11, fill=RED, align='left')
    sim_x, sim_y, sim_w, sim_h = 54, 140, 500, 390
    plot_x, plot_y, plot_w, plot_h = 580, 140, 416, 390
    _draw_simulation(app, sim_x, sim_y, sim_w, sim_h)
    _draw_plots(app, plot_x, plot_y, plot_w, plot_h)
