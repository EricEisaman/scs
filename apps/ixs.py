from scs import *
from browser import document, window
import math, random

BG = rgb(9, 14, 18)
PANEL_BG = rgb(18, 26, 30)
GRID = rgb(32, 44, 49)
INK = rgb(230, 242, 238)
MUTED = rgb(128, 148, 142)
MINT = rgb(102, 224, 177)
GOLD = rgb(244, 190, 92)
RED = rgb(255, 105, 125)
BLUE = rgb(110, 160, 255)
CYAN = rgb(80, 220, 255)
ORANGE = rgb(255, 166, 77)
PURPLE = rgb(180, 130, 255)

_PANEL_ID = 'phonon-controls'

# Physical constants
HC = 12398e3  # meV * Angstrom  (12.398 keV*A = 12,398,000 meV*A)
HBAR = 1.0545718e-34
AMU = 1.6605390666e-27
MEV_TO_J = 1.60218e-22
# masses
M_SI_AMU = 28.085
M_N_AMU = 14.007
M_SI = M_SI_AMU * AMU
M_N = M_N_AMU * AMU
SQRT_M1M2 = math.sqrt(M_SI * M_N)

# lattice
A_LATT = 7.6  # Angstrom, beta-Si3N4 a
# honeycomb delta vectors (nearest neighbor) ~ a / sqrt(3)
D0 = A_LATT / math.sqrt(3.0)
DELTAS = [
    (D0 * 1.0, D0 * 0.0),
    (D0 * -0.5, D0 * math.sqrt(3)/2),
    (D0 * -0.5, D0 * -math.sqrt(3)/2),
]
# direct lattice vectors
A1 = (A_LATT, 0.0)
A2 = (A_LATT*0.5, A_LATT*math.sqrt(3)/2)
# basis
BASIS_SI = (0.0, 0.0)
BASIS_N = (A1[0]/3 + A2[0]*2/3 - A1[0]*0.5, A1[1]/3 + A2[1]*2/3 - A2[1]*0.5)  # centered approx
BASIS_N = (A_LATT*0.5, A_LATT*math.sqrt(3)/6)

# force constants -> gives 10-80 meV
K_L = 78.0  # N/m longitudinal
K_T = 32.0  # N/m transverse

def _dot(ax,ay,bx,by): return ax*bx + ay*by

def _compute_S(qx, qy):
    sc = 0.0
    ss = 0.0
    for dx, dy in DELTAS:
        ph = qx*dx + qy*dy
        sc += math.cos(ph)
        ss += math.sin(ph)
    mag = math.sqrt(sc*sc + ss*ss)
    return sc, ss, mag

def _dynamical_matrix(qx, qy):
    """Return 4 branches: each dict with w2, w_meV, e1,e2, pol, label"""
    sc, ss, smag = _compute_S(qx, qy)
    branches = []
    # two polarizations
    for Kp, pol, label_prefix in [(K_L, 'L', ''), (K_T, 'T', '')]:
        A = 3*Kp / M_SI
        B = 3*Kp / M_N
        C = -Kp * smag / SQRT_M1M2
        # 2x2 matrix [[A, C],[C, B]]
        trace = A + B
        det = A*B - C*C
        disc = (A - B)*(A - B) + 4*C*C
        disc = max(disc, 0.0)
        sqrt_disc = math.sqrt(disc)
        w2_1 = (trace - sqrt_disc)*0.5
        w2_2 = (trace + sqrt_disc)*0.5
        # eigenvectors: for each w2, [C, w2-A]
        for w2, typ in [(w2_1, 'AC'), (w2_2, 'OP')]:
            if abs(w2) < 1e-12:
                # zero mode: e = [sqrt(M_N), sqrt(M_SI)]? acoustic both move together
                e1 = math.sqrt(M_N)
                e2 = math.sqrt(M_SI)
            else:
                e1 = C
                e2 = w2 - A
                # if both zero, set
                if abs(e1) < 1e-12 and abs(e2) < 1e-12:
                    e1, e2 = 1.0, 1.0
            norm = math.sqrt(e1*e1 + e2*e2)
            if norm < 1e-12:
                norm = 1.0
            e1 /= norm
            e2 /= norm
            # physical displacements u = e / sqrt(m)
            u1 = e1 / math.sqrt(M_SI)
            u2 = e2 / math.sqrt(M_N)
            # normalize max to 1
            max_u = max(abs(u1), abs(u2), 1e-12)
            u1 /= max_u
            u2 /= max_u
            # frequency to meV
            if w2 < 0:
                w_meV = - math.sqrt(-w2) * HBAR / MEV_TO_J * 1000.0  # negative indicates instability
                # Actually HBAR * sqrt(|w2|) / meV
                # correction: sqrt(|w2|) is rad/s
                # compute: hbar * sqrt
                # w_meV negative
                w_meV = - HBAR * math.sqrt(-w2) / MEV_TO_J * 1000.0
            else:
                w_meV = HBAR * math.sqrt(w2) / MEV_TO_J * 1000.0
            branches.append({
                'w2': w2,
                'w_meV': w_meV,
                'e1': e1, 'e2': e2,
                'u1': u1, 'u2': u2,
                'pol': pol,
                'type': typ,
                'label': f"{typ}-{pol}",
                'S': smag,
                'sc': sc, 'ss': ss
            })
    # sort by w_meV (acoustic first)
    branches.sort(key=lambda b: b['w_meV'])
    return branches

def _k_from_E(E_meV):
    # k = 2pi * E / hc
    return 2*math.pi*E_meV / HC

def _bose_factor(w_meV, T):
    # n = 1/(exp(hw/kT)-1), kT in meV: kB=0.08617 meV/K
    if w_meV <= 0.1:
        return 1.0
    kT = 0.08617 * T
    if kT < 1e-6:
        return 1.0
    x = w_meV / kT
    if x > 20:
        return 1.0
    try:
        return 1.0/(math.exp(x)-1) + 1
    except:
        return 1.0

def _install_controls(app):
    existing = document.getElementById(_PANEL_ID)
    if existing:
        existing.parentNode.removeChild(existing)
    panel = document.createElement('section')
    panel.id = _PANEL_ID
    panel.style.cssText = 'box-sizing:border-box;width:1050px;max-width:95vw;padding:16px 20px;margin:0 0 10px;background:#121a1e;border:1px solid #2a3a3f;color:#e6f2ee;font:12px/1.4 ui-monospace;display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px'
    panel.innerHTML = f'''
      <div style="grid-column:1/-1;display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px;align-items:baseline;margin-bottom:2px">
        <strong style="font-size:16px;color:#66e0b1;letter-spacing:0.5px">Hexagonal Si₃N₄ Thin Film · Phonon IXS</strong>
        <span style="color:#80948e">D(q) e = ω² e · 15-25 keV → meV loss</span>
      </div>
      <label style="display:grid;gap:4px;color:#b6c6bf">E_in (keV) <span id="val-Ein" style="color:#f4be5c"></span>
        <input id="sl-Ein" type="range" min="15000" max="25000" step="100" value="{int(app.Ein)}" style="width:100%">
      </label>
      <label style="display:grid;gap:4px;color:#b6c6bf">Resolution ΔE (meV) <span id="val-dE" style="color:#66e0b1"></span>
        <input id="sl-dE" type="range" min="0.5" max="5" step="0.1" value="{app.dE}" style="width:100%">
      </label>
      <label style="display:grid;gap:4px;color:#b6c6bf">Scattering 2θ (°) <span id="val-theta"></span>
        <input id="sl-theta" type="range" min="5" max="85" step="1" value="{app.theta_deg}" style="width:100%">
      </label>
      <label style="display:grid;gap:4px;color:#b6c6bf">Azimuth φ (°) <span id="val-phi"></span>
        <input id="sl-phi" type="range" min="0" max="360" step="2" value="{app.phi_deg}" style="width:100%">
      </label>
      <label style="display:grid;gap:4px;color:#b6c6bf">Phonon branch
        <select id="sl-branch" style="background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:6px">
          <option value="0">0: LA (lowest)</option>
          <option value="1">1: TA</option>
          <option value="2">2: LO</option>
          <option value="3" selected>3: TO (highest)</option>
        </select>
      </label>
      <label style="display:grid;gap:4px;color:#b6c6bf">Temperature (K) <span id="val-T"></span>
        <input id="sl-T" type="range" min="10" max="600" step="10" value="{app.T}" style="width:100%">
      </label>
      <div style="display:flex;gap:8px;align-items:end">
        <button id="btn-play" style="padding:8px 14px;background:#66e0b1;color:#10201a;border:0;font-weight:bold;cursor:pointer">⏸ Pause</button>
        <button id="btn-scan" style="padding:8px 14px;background:#1e2a2e;color:#a0b8b1;border:1px solid #344a4f;cursor:pointer">Scan q</button>
        <button id="btn-inst" style="padding:8px 10px;background:#1e2a2e;color:#ff6b7a;border:1px solid #4a3440;cursor:pointer">Instability</button>
      </div>
      <div id="phonon-info" style="grid-column:1/-1;color:#80948e;font-size:11px;line-height:1.5;border-top:1px solid #223035;padding-top:8px"></div>
    '''
    document.getElementById('canvas-container').parentNode.insertBefore(panel, document.getElementById('canvas-container'))

    def upd():
        app.Ein = float(document['sl-Ein'].value)
        app.dE = float(document['sl-dE'].value)
        app.theta_deg = float(document['sl-theta'].value)
        app.phi_deg = float(document['sl-phi'].value)
        app.T = float(document['sl-T'].value)
        app.branch_idx = int(document['sl-branch'].value)
        document['val-Ein'].textContent = f"{app.Ein/1000:.1f} keV"
        document['val-dE'].textContent = f"{app.dE:.1f} meV"
        document['val-theta'].textContent = f"{app.theta_deg:.0f}°"
        document['val-phi'].textContent = f"{app.phi_deg:.0f}°"
        document['val-T'].textContent = f"{int(app.T)} K"
        # recompute q
        k = _k_from_E(app.Ein)
        # q magnitude = 2k sin(theta/2)
        th = math.radians(app.theta_deg)
        qmag = 2*k*math.sin(th/2)
        ph = math.radians(app.phi_deg)
        app.qx = qmag * math.cos(ph)
        app.qy = qmag * math.sin(ph)
        app.branches = _dynamical_matrix(app.qx, app.qy)

    for sid in ['sl-Ein','sl-dE','sl-theta','sl-phi','sl-T','sl-branch']:
        document[sid].bind('input', lambda e: upd())
    def toggle_play(e):
        app.playing = not app.playing
        document['btn-play'].textContent = '▶ Play' if not app.playing else '⏸ Pause'
    def toggle_scan(e):
        app.auto_scan = not app.auto_scan
        document['btn-scan'].style.background = '#66e0b1' if app.auto_scan else '#1e2a2e'
        document['btn-scan'].style.color = '#10201a' if app.auto_scan else '#a0b8b1'
    def toggle_inst(e):
        app.show_instability = not app.show_instability
        # make K negative to induce instability at zone boundary
        global K_L, K_T
        if app.show_instability:
            K_L = -10.0
            K_T = -5.0
        else:
            K_L = 78.0
            K_T = 32.0
        document['btn-inst'].style.background = '#ff6b7a' if app.show_instability else '#1e2a2e'
        document['btn-inst'].style.color = '#fff' if app.show_instability else '#ff6b7a'
        upd()
    document['btn-play'].bind('click', toggle_play)
    document['btn-scan'].bind('click', toggle_scan)
    document['btn-inst'].bind('click', toggle_inst)
    upd()

def _gen_lattice(nx, ny):
    pts = []
    for i in range(-nx//2, nx//2+1):
        for j in range(-ny//2, ny//2+1):
            # base cell origin
            ox = i*A1[0] + j*A2[0]
            oy = i*A1[1] + j*A2[1]
            # Si
            pts.append((ox+BASIS_SI[0], oy+BASIS_SI[1], 0, 'Si'))
            # N
            pts.append((ox+BASIS_N[0], oy+BASIS_N[1], 1, 'N'))
    return pts

def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=30; app.background=BG
    app.Ein=20000.0  # meV
    app.dE=1.8
    app.theta_deg=35.0
    app.phi_deg=20.0
    app.T=300.0
    app.branch_idx=3
    app.playing=True
    app.auto_scan=False
    app.show_instability=False
    app.time=0.0
    app.amplitude=8.0
    app.lattice=_gen_lattice(8,6)
    app.qx=0.5; app.qy=0.3
    k=_k_from_E(app.Ein)
    th=math.radians(app.theta_deg)
    qmag=2*k*math.sin(th/2)
    ph=math.radians(app.phi_deg)
    app.qx=qmag*math.cos(ph); app.qy=qmag*math.sin(ph)
    app.branches=_dynamical_matrix(app.qx, app.qy)
    # precompute dispersion path Gamma-M-K-Gamma
    app.path_pts=[]
    # define high sym points in reciprocal (units A^-1)
    # Gamma (0,0), M (pi/a, pi/(sqrt3 a)), K (4pi/3a,0)
    Gamma=(0,0)
    M=(math.pi/A_LATT, math.pi/(math.sqrt(3)*A_LATT))
    K=(4*math.pi/(3*A_LATT), 0)
    def lerp(a,b,t): return (a[0]*(1-t)+b[0]*t, a[1]*(1-t)+b[1]*t)
    for seg in [(Gamma,M),(M,K),(K,Gamma)]:
        for s in range(25):
            t=s/24
            app.path_pts.append(lerp(seg[0],seg[1],t))
    # compute dispersion along path
    app.dispersion=[]
    for q in app.path_pts:
        br=_dynamical_matrix(q[0],q[1])
        app.dispersion.append([b['w_meV'] for b in br])
    _install_controls(app)

def onStep(app):
    if not app.playing:
        return
    dt=0.03
    app.time+=dt
    if app.auto_scan:
        # rotate q slowly
        app.phi_deg = (app.phi_deg + 0.6) % 360
        ph=math.radians(app.phi_deg)
        # also modulate theta
        app.theta_deg = 30 + 15*math.sin(app.time*0.3)
        k=_k_from_E(app.Ein)
        qmag=2*k*math.sin(math.radians(app.theta_deg)/2)
        app.qx=qmag*math.cos(ph)
        app.qy=qmag*math.sin(ph)
        app.branches=_dynamical_matrix(app.qx, app.qy)
        # update sliders display (optional)
        try:
            document['sl-phi'].value=str(app.phi_deg)
            document['sl-theta'].value=str(app.theta_deg)
            document['val-phi'].textContent=f"{app.phi_deg:.0f}°"
            document['val-theta'].textContent=f"{app.theta_deg:.0f}°"
        except:
            pass

def _draw_lattice(app, x0,y0,w,h):
    drawRect(x0,y0,w,h, fill=rgb(14,22,26), border=rgb(42,58,63), borderWidth=1)
    # thin film border glow
    drawRect(x0-2,y0-2,w+4,h+4, fill=None, border=rgb(60,80,85), borderWidth=1)
    drawLabel('REAL SPACE · Hexagonal Si₃N₄ Thin Film · phonon displacement', x0+10, y0+14, size=11, fill=MUTED, align='left')
    # center of lattice in panel
    cx=x0+w*0.5; cy=y0+h*0.55
    scale=14.0  # pixels per Angstrom
    # selected branch
    if app.branch_idx>=len(app.branches): app.branch_idx=0
    br=app.branches[app.branch_idx]
    qx,qy=app.qx,app.qy
    qnorm=math.sqrt(qx*qx+qy*qy)+1e-9
    qhatx=qx/qnorm; qhaty=qy/qnorm
    # polarization direction
    if br['pol']=='L':
        px,py=qhatx,qhaty
    else:
        px,py=-qhaty,qhatx
    w_meV=br['w_meV']
    # frequency for animation: use absolute meV to rad/s scaling for visible speed
    # animate with frequency proportional to meV, but scaled for 30fps
    omega_anim = max(0.5, min(6.0, abs(w_meV)*0.15))  # rad/frame factor
    # draw bonds first
    # for each Si, find nearest N neighbors
    # quick neighbor search: for each point, look for close N within 2.5A
    pts=app.lattice
    # draw bonds
    for i,(x,y,typ,_) in enumerate(pts):
        if typ!=0: continue
        # Si at (x,y)
        for j,(x2,y2,typ2,_) in enumerate(pts):
            if typ2!=1: continue
            dx=x2-x; dy=y2-y
            dist=math.sqrt(dx*dx+dy*dy)
            if dist< D0*1.3 and dist>0.1:
                # compute displacement for bond stretch visualization
                # world positions
                X1=cx + x*scale
                Y1=cy + y*scale
                X2=cx + x2*scale
                Y2=cy + y2*scale
                # animate displacements
                phase1 = qx*x + qy*y - app.time*omega_anim*8
                phase2 = qx*x2 + qy*y2 - app.time*omega_anim*8
                # u1, u2 from branch
                disp1 = br['u1'] * math.cos(phase1) * app.amplitude
                disp2 = br['u2'] * math.cos(phase2) * app.amplitude
                X1d = X1 + disp1*px*2.0
                Y1d = Y1 + disp1*py*2.0
                X2d = X2 + disp2*px*2.0
                Y2d = Y2 + disp2*py*2.0
                # bond color based on stretch
                stretch = abs(disp1-disp2)
                # lerp color
                col = rgb(60+int(80*stretch/10), 70, 80) if stretch<10 else rgb(120,90,90)
                drawLine(X1d,Y1d,X2d,Y2d, fill=col, lineWidth=1)
    # draw atoms with glow
    for x,y,typ,_ in pts:
        X=cx + x*scale
        Y=cy + y*scale
        phase = qx*x + qy*y - app.time*omega_anim*8
        amp = (br['u1'] if typ==0 else br['u2']) * math.cos(phase) * app.amplitude
        Xd = X + amp*px*2.0
        Yd = Y + amp*py*2.0
        if typ==0: # Si larger blue
            # glow
            drawCircle(Xd,Yd, 10, fill=rgb(30,65,110))
            drawCircle(Xd,Yd, 6, fill=BLUE, border=rgb(180,210,255), borderWidth=1)
            drawCircle(Xd,Yd, 2, fill=rgb(210,230,255))
        else: # N smaller
            drawCircle(Xd,Yd, 8, fill=rgb(110,65,30))
            drawCircle(Xd,Yd, 4.5, fill=GOLD, border=rgb(255,230,160), borderWidth=1)
    # show q arrow in corner
    drawLabel(f"q = {qnorm:.2f} Å⁻¹  ω={w_meV:.1f} meV  {br['label']}  {'UNSTABLE' if w_meV<0 else ''}", x0+10, y0+h-14, size=11, fill= MINT if w_meV>=0 else RED, align='left')

def _draw_brillouin(app, x0,y0,w,h):
    drawRect(x0,y0,w,h, fill=rgb(14,22,26), border=rgb(42,58,63), borderWidth=1)
    drawLabel('RECIPROCAL SPACE · Brillouin Zone', x0+10, y0+14, size=11, fill=MUTED, align='left')
    cx=x0+w*0.5; cy=y0+h*0.55; R= min(w,h)*0.38
    # hexagon points
    hex_pts=[]
    for i in range(6):
        ang=math.radians(30+i*60)
        hex_pts.append((cx+R*math.cos(ang), cy+R*math.sin(ang)))
    # draw hex
    for i in range(6):
        x1,y1=hex_pts[i]; x2,y2=hex_pts[(i+1)%6]
        drawLine(x1,y1,x2,y2, fill=rgb(70,90,95), lineWidth=2)
    # Gamma
    drawCircle(cx,cy,3, fill=INK)
    drawLabel('Γ', cx+6, cy-8, size=11, fill=INK, align='left')
    # M and K labels
    drawLabel('M', hex_pts[0][0]+6, hex_pts[0][1], size=10, fill=MUTED, align='left')
    drawLabel('K', hex_pts[1][0]+4, hex_pts[1][1]-10, size=10, fill=MUTED, align='left')
    # draw path Gamma-M-K-Gamma faint
    # draw q vector
    # map q to screen: q up to ~3 Å^-1 corresponds to R
    # scale: BZ boundary ~ 2π/a * 0.66 ≈ 0.55 Å^-1? Actually our hex R corresponds to ~1.0 Å^-1
    q_scale = R / 1.2  # 1.2 A^-1 maps to edge
    qx, qy = app.qx, app.qy
    # wrap to first BZ for display? show as is but clamp
    qx_s = cx + qx*q_scale
    qy_s = cy - qy*q_scale  # y flipped
    # draw from Gamma
    drawLine(cx,cy,qx_s,qy_s, fill=CYAN, lineWidth=2)
    drawCircle(qx_s,qy_s,5, fill=CYAN, border=INK, borderWidth=1)
    # draw small arrow head
    ang=math.atan2(cy-qy_s, qx_s-cx)
    # simple
    drawLabel(f"q", qx_s+8, qy_s-8, size=11, fill=CYAN, align='left')
    # show G vectors?
    # draw reciprocal lattice points faint
    for i in range(-1,2):
        for j in range(-1,2):
            if i==0 and j==0: continue
            # b1,b2 approx
            b1x= 2*math.pi/A_LATT *1.0
            b1y= 2*math.pi/A_LATT *(-1/math.sqrt(3))
            b2x=0
            b2y= 2*math.pi/A_LATT *2/math.sqrt(3)
            rx=i*b1x+j*b2x
            ry=i*b1y+j*b2y
            sx=cx+rx*q_scale
            sy=cy-ry*q_scale
            if x0< sx < x0+w and y0< sy < y0+h:
                drawCircle(sx,sy,2, fill=rgb(60,70,75))

def _draw_dispersion(app, x0,y0,w,h):
    drawRect(x0,y0,w,h, fill=rgb(14,22,26), border=rgb(42,58,63), borderWidth=1)
    drawLabel('PHONON DISPERSION ω(q) · D(q)e=ω²e', x0+10, y0+14, size=11, fill=MUTED, align='left')
    # axes
    pad_l=38; pad_r=10; pad_t=28; pad_b=22
    ax=x0+pad_l; ay=y0+pad_t; aw=w-pad_l-pad_r; ah=h-pad_t-pad_b
    drawRect(ax,ay,aw,ah, fill=rgb(10,18,22), border=rgb(40,55,60), borderWidth=1)
    # find min max w
    all_w=[]
    for row in app.dispersion:
        for v in row: all_w.append(v)
    w_min=min(all_w)-2; w_max=max(all_w)+5
    if w_min>0: w_min=-5
    # path x: 0.. len(path)
    n=len(app.path_pts)
    # draw branches
    cols=[rgb(102,224,177), rgb(80,220,255), rgb(244,190,92), rgb(180,130,255)]
    for b_idx in range(4):
        for i in range(n-1):
            x1=ax + (i/(n-1))*aw
            x2=ax + ((i+1)/(n-1))*aw
            y1v=app.dispersion[i][b_idx]
            y2v=app.dispersion[i+1][b_idx]
            # map y
            y1 = ay+ah - (y1v - w_min)/(w_max - w_min)*ah
            y2 = ay+ah - (y2v - w_min)/(w_max - w_min)*ah
            # clip negative?
            if y1v<0 or y2v<0:
                col=RED
            else:
                col=cols[b_idx]
            lw=3 if b_idx==app.branch_idx else 1.5
            drawLine(x1,y1,x2,y2, fill=col, lineWidth=lw)
    # high sym markers
    for frac,label in [(0,'Γ'), (0.33,'M'), (0.66,'K'), (1.0,'Γ')]:
        x=ax+frac*aw
        drawLine(x,ay,x,ay+ah, fill=rgb(50,65,70), lineWidth=1, dashes=[3,3])
        drawLabel(label, x, ay+ah+12, size=10, fill=MUTED, align='center')
    # current q projection: find closest path point to current q
    # compute distance in q space
    best_i=0; best_d=1e9
    for i,q in enumerate(app.path_pts):
        d=(q[0]-app.qx)**2 + (q[1]-app.qy)**2
        if d<best_d: best_d=d; best_i=i
    xq=ax + (best_i/(n-1))*aw
    drawLine(xq,ay,xq,ay+ah, fill=CYAN, lineWidth=1)
    drawCircle(xq, ay+ah - (app.branches[app.branch_idx]['w_meV']-w_min)/(w_max-w_min)*ah, 4, fill=CYAN, border=INK)
    drawLabel(f"{w_min:.0f} meV", ax-4, ay+ah, size=9, fill=MUTED, align='right')
    drawLabel(f"{w_max:.0f} meV", ax-4, ay+6, size=9, fill=MUTED, align='right')
    # negative region shading for instability
    if w_min<0:
        y0_line = ay+ah - (0 - w_min)/(w_max - w_min)*ah
        drawRect(ax,y0_line,aw,ay+ah-y0_line, fill=rgb(80,30,35))
        drawLabel('ω²<0 unstable', ax+aw-2, y0_line+12, size=9, fill=RED, align='right')

def _draw_ixs(app, x0,y0,w,h):
    drawRect(x0,y0,w,h, fill=rgb(14,22,26), border=rgb(42,58,63), borderWidth=1)
    drawLabel('IXS SPECTRUM · E_in vs ħω loss', x0+10, y0+14, size=11, fill=MUTED, align='left')
    # three energies visualization
    # top bar: E_in huge
    # show E_in as large bar, and zoom inset for meV
    pad=10
    # E_in bar
    Ein=app.Ein
    # bar from 15k to 25k meV, show current
    bar_x=x0+12; bar_y=y0+32; bar_w=w-24; bar_h=14
    drawRect(bar_x,bar_y,bar_w,bar_h, fill=rgb(30,40,45), border=rgb(60,75,80), borderWidth=1)
    # fill proportional
    frac = (Ein-15000)/(10000)
    drawRect(bar_x,bar_y,bar_w*frac,bar_h, fill=BLUE)
    drawLabel(f"E_in = {Ein/1000:.1f} keV ({Ein/1000*1e3:.0f} eV)", bar_x+4, bar_y+9, size=10, fill=INK, align='left')
    # scale comparison: show 100 meV vs 20 keV = 1:200,000
    drawLabel(f"scale 1 meV = {Ein/1000/0.001:.0f} × smaller than E_in", bar_x, bar_y+bar_h+12, size=9, fill=rgb(90,110,115), align='left')
    # spectrum axes
    ax=x0+12; ay=y0+70; aw=w-24; ah=h-90
    drawRect(ax,ay,aw,ah, fill=rgb(10,18,22), border=rgb(40,55,60), borderWidth=1)
    # x: energy loss 0-110 meV, y: intensity
    # compute intensities for each branch
    branches=app.branches
    # Q magnitude for intensity
    qnorm=math.sqrt(app.qx*app.qx+app.qy*app.qy)+1e-9
    qhatx=app.qx/qnorm; qhaty=app.qy/qnorm
    intensities=[]
    for br in branches:
        # Q·e factor: for L, ~1, for T small depending on q direction
        # we have polarization: L dot Q = 1, T dot Q = 0 if perfect
        # add some misalignment
        if br['pol']=='L':
            q_dot_e = 0.9 + 0.1*math.cos(math.radians(app.phi_deg))
        else:
            q_dot_e = 0.2 + 0.2*abs(math.sin(math.radians(app.phi_deg)))
        # include eigenvector mass factor and 1/omega
        omega = abs(br['w_meV'])+1.0
        I = (q_dot_e*q_dot_e) * _bose_factor(abs(br['w_meV']), app.T) / omega
        # highlight selected branch
        if branches.index(br)==app.branch_idx:
            I*=1.6
        intensities.append(I)
    max_I = max(intensities) if intensities else 1.0
    max_I = max(max_I, 1.0)
    # draw elastic peak at 0
    # Gaussian broadening
    def gauss(x, x0, sigma, amp):
        return amp*math.exp(-0.5*((x-x0)/sigma)**2)
    # x scale: 0-110 meV
    x_min=0; x_max=110
    # draw grid
    for meV in [0,20,40,60,80,100]:
        xx=ax + (meV-x_min)/(x_max-x_min)*aw
        drawLine(xx,ay,xx,ay+ah, fill=rgb(35,45,50), lineWidth=1, dashes=[2,4])
        drawLabel(f"{meV}", xx, ay+ah+10, size=9, fill=MUTED, align='center')
    # draw elastic
    # elastic huge
    for i in range(int(aw)):
        x_meV = x_min + (i/aw)*(x_max-x_min)
        y_val = gauss(x_meV, 0, app.dE*0.4, max_I*1.2)
        # convert to screen y
        # accumulate? just draw line for elastic separately as tall
        pass
    # draw spectrum as stacked Gaussians
    # for each x pixel, sum contributions
    prev_y=None; prev_x=None
    for px_i in range(int(aw)):
        x_meV = x_min + (px_i/aw)*(x_max-x_min)
        y_sum=0.0
        # elastic
        y_sum+= gauss(x_meV, 0, max(0.3, app.dE*0.5), max_I*1.0)
        for br_idx, br in enumerate(branches):
            w = abs(br['w_meV'])
            if w<0.5: continue
            sigma = max(0.4, app.dE)
            amp = intensities[br_idx]
            y_sum += gauss(x_meV, w, sigma, amp)
            # also Stokes/anti-Stokes negative? show small anti-Stokes at -w (not in range)
        # map y to screen
        y_screen = ay+ah - (y_sum/max_I/1.5)*ah*0.85
        y_screen = max(ay+2, min(ay+ah-2, y_screen))
        x_screen = ax + px_i
        if prev_x is not None:
            col = CYAN if True else MINT
            drawLine(prev_x, prev_y, x_screen, y_screen, fill=MINT, lineWidth=2)
        prev_x, prev_y = x_screen, y_screen
    # draw peaks markers
    for br_idx, br in enumerate(branches):
        w=abs(br['w_meV'])
        if w<0.5 or w> x_max: continue
        xx=ax + (w-x_min)/(x_max-x_min)*aw
        yy= ay+ah - (intensities[br_idx]/max_I/1.5)*ah*0.85
        col = [MINT, CYAN, GOLD, PURPLE][br_idx%4]
        if br_idx==app.branch_idx:
            drawCircle(xx,yy,5, fill=col, border=INK, borderWidth=1)
            drawLabel(f"{br['label']} {br['w_meV']:.1f} meV", xx+6, yy-10, size=10, fill=col, align='left')
        else:
            drawCircle(xx,yy,3, fill=col)
    # draw resolution annotation
    drawLabel(f"ΔE={app.dE:.1f} meV blurs peaks · I ∝ |Q·e|²/ω", ax, ay-8, size=9, fill=rgb(120,140,145), align='left')
    # draw E_out = E_in - hw
    hw = abs(app.branches[app.branch_idx]['w_meV']) if app.branches else 0
    Eout = app.Ein - hw
    drawLabel(f"E_out = E_in - ħω = {Eout/1000:.6f} keV  loss={hw:.1f} meV", x0+10, y0+h-8, size=10, fill=GOLD, align='left')

def _draw_geometry(app, x0,y0,w,h):
    # tiny top strip showing k_in, k_out, q geometry exaggerated
    drawRect(x0,y0,w,h, fill=rgb(14,22,26), border=rgb(42,58,63), borderWidth=1)
    drawLabel('SCATTERING GEOMETRY · k_in - k_out = Q ≈ q', x0+8, y0+12, size=10, fill=MUTED, align='left')
    cx=x0+w*0.5; cy=y0+h*0.5+6
    k_len= w*0.38
    # k_in direction: -phi ?
    ang_in= math.radians(app.phi_deg - app.theta_deg/2)
    ang_out= math.radians(app.phi_deg + app.theta_deg/2)
    # draw k_in
    x_in = cx - k_len*math.cos(ang_in)*0.5
    y_in = cy - k_len*math.sin(ang_in)*0.5
    x_tip = cx + k_len*math.cos(ang_in)*0.5
    y_tip = cy + k_len*math.sin(ang_in)*0.5
    drawLine(x_in,y_in,x_tip,y_tip, fill=BLUE, lineWidth=2)
    drawCircle(x_tip,y_tip,4, fill=BLUE)
    drawLabel('k_in', x_in-12, y_in-8, size=10, fill=BLUE, align='right')
    # k_out slightly shorter (energy loss)
    loss_frac = abs(app.branches[app.branch_idx]['w_meV'])/app.Ein if app.branches else 0
    k_out_len = k_len*(1 - loss_frac*2)  # exaggerate *2 for visibility (still tiny)
    x_out = cx + k_out_len*math.cos(ang_out)*0.5
    y_out = cy + k_out_len*math.sin(ang_out)*0.5
    x_out_base = cx - k_out_len*math.cos(ang_out)*0.5
    y_out_base = cy - k_out_len*math.sin(ang_out)*0.5
    drawLine(x_out_base,y_out_base,x_out,y_out, fill=GOLD, lineWidth=2)
    drawCircle(x_out,y_out,4, fill=GOLD)
    drawLabel('k_out', x_out+6, y_out-6, size=10, fill=GOLD, align='left')
    # q vector difference
    drawLine(x_tip,y_tip,x_out,y_out, fill=CYAN, lineWidth=2, dashes=[4,4])
    drawLabel('Q', (x_tip+x_out)/2+6, (y_tip+y_out)/2-8, size=10, fill=CYAN, align='left')
    drawLabel(f"|k|={_k_from_E(app.Ein):.1f} Å⁻¹  |Q|={math.sqrt(app.qx**2+app.qy**2):.2f} Å⁻¹", x0+8, y0+h-6, size=9, fill=rgb(100,115,120), align='left')

def redrawAll(app):
    drawRect(0,0,app.width,app.height, fill=BG)
    # title bar
    drawLabel('PHONON INTERACTION · IXS', 24, 24, size=20, fill=INK, bold=True, align='left')
    drawLabel(f"E_in {app.Ein/1000:.1f} keV · ΔE {app.dE:.1f} meV · ħω up to 100 meV · Si₃N₄ film", 24, 42, size=11, fill=MUTED, align='left')
    # layouts: top geometry strip, then lattice + BZ + dispersion + IXS
    # geometry
    _draw_geometry(app, 24, 54, 350, 78)
    # info about three energies
    drawRect(390,54, 636,78, fill=rgb(18,28,32), border=rgb(42,58,63), borderWidth=1)
    drawLabel('THREE ENERGIES IN ONE IXS EVENT:', 400, 66, size=10, fill=GOLD, bold=True, align='left')
    drawLabel(f"1) E_in ~ {app.Ein/1e6:.1f}×10⁷ meV (15-25 keV) wavelength ~ {HC/app.Ein:.2f} Å", 400, 80, size=10, fill=INK, align='left')
    hw = abs(app.branches[app.branch_idx]['w_meV']) if app.branches else 0
    drawLabel(f"2) ħω = {hw:.1f} meV lost to lattice · E_out = {app.Ein-hw:.0f} meV", 400, 92, size=10, fill=MINT, align='left')
    drawLabel(f"3) ΔE = {app.dE:.1f} meV resolution · detects 1 part in {app.Ein/app.dE:.0f} million", 400, 104, size=10, fill=CYAN, align='left')
    drawLabel(f"E_out 23,724,000→23,723,900 example 100 meV loss", 400, 116, size=9, fill=rgb(120,135,140), align='left')

    # main panels
    _draw_lattice(app, 24, 142, 500, 320)
    _draw_brillouin(app, 540, 142, 230, 155)
    _draw_dispersion(app, 785, 142, 241, 155)
    _draw_ixs(app, 540, 310, 486, 152)
    # film thickness indicator
    drawRect(24, 472, 1026, 54, fill=rgb(18,26,30), border=rgb(42,58,63), borderWidth=1)
    drawLabel('THIN FILM: 3 layers · c-axis out-of-plane · substrate below · vacuum above', 32, 484, size=10, fill=MUTED, align='left')
    drawRect(32, 494, 1010, 8, fill=rgb(30,40,45), border=rgb(60,70,75), borderWidth=1)
    drawRect(32, 494, 1010*0.7, 8, fill=BLUE)
    drawRect(32, 502, 1010*0.3, 4, fill=GOLD)
    drawLabel('Si₃N₄ 12 nm', 32, 514, size=9, fill=BLUE, align='left')
    drawLabel('Instability when ω²<0 → imaginary phonon', 540, 514, size=9, fill=RED if app.show_instability else MUTED, align='left')

    # info panel text
    try:
        info = document.getElementById('phonon-info')
        if info:
            br = app.branches[app.branch_idx] if app.branches else None
            if br:
                qnorm=math.sqrt(app.qx*app.qx+app.qy*app.qy)
                info.innerHTML = f"D(q) eigenvalues: " + ", ".join([f"{b['label']}={b['w_meV']:.1f} meV (w²={b['w2']:.2e})" for b in app.branches]) + f" | q=({app.qx:.2f},{app.qy:.2f}) Å⁻¹ | |q|={qnorm:.2f} | k={_k_from_E(app.Ein):.2f} Å⁻¹ | selected {br['label']} e=[{br['e1']:.2f},{br['e2']:.2f}] u=[{br['u1']:.2f},{br['u2']:.2f}]"
    except:
        pass

def onKeyPress(app, key):
    if key==' ':
        app.playing=not app.playing
    elif key.lower()=='r':
        app.time=0
