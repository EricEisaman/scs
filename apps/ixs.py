from scs import *
from browser import document
import math

BG = rgb(9, 14, 18)
INK = rgb(230, 242, 238)
MUTED = rgb(128, 148, 142)
MINT = rgb(102, 224, 177)
GOLD = rgb(244, 190, 92)
RED = rgb(255, 105, 125)
BLUE = rgb(110, 160, 255)
CYAN = rgb(80, 220, 255)
PURPLE = rgb(180, 130, 255)

_PANEL_ID = 'ixs-controls'

HC = 12398e3
HBAR = 1.0545718e-34
AMU = 1.6605390666e-27
MEV_TO_J = 1.60218e-22

M_SI = 28.085 * AMU
M_N = 14.007 * AMU
SQRT_M1M2 = math.sqrt(M_SI * M_N)

A_LATT = 7.6
D0 = A_LATT / math.sqrt(3.0)
DELTAS = [(D0,0.0),(D0*-0.5,D0*math.sqrt(3)/2),(D0*-0.5,D0*-math.sqrt(3)/2)]
A1 = (A_LATT, 0.0)
A2 = (A_LATT*0.5, A_LATT*math.sqrt(3)/2)
BASIS_N = (A_LATT*0.5, A_LATT*math.sqrt(3)/6)

K_L = 78.0
K_T = 32.0

def _compute_S(qx,qy):
    sc=0.0; ss=0.0
    for dx,dy in DELTAS:
        ph=qx*dx+qy*dy
        sc+=math.cos(ph); ss+=math.sin(ph)
    return sc, ss, math.sqrt(sc*sc+ss*ss)

def _dynamical_matrix(qx,qy,kL=K_L,kT=K_T):
    sc,ss,smag=_compute_S(qx,qy)
    branches=[]
    for Kp,pol in [(kL,'L'),(kT,'T')]:
        A=3*Kp/M_SI; B=3*Kp/M_N; C=-Kp*smag/SQRT_M1M2
        trace=A+B; disc=(A-B)*(A-B)+4*C*C
        sd=math.sqrt(max(disc,0.0))
        for w2,typ in [((trace-sd)*0.5,'AC'),((trace+sd)*0.5,'OP')]:
            if abs(w2)<1e-12:
                e1=math.sqrt(M_N); e2=math.sqrt(M_SI)
            else:
                e1=C; e2=w2-A
                if abs(e1)<1e-12 and abs(e2)<1e-12: e1,e2=1.0,1.0
            norm=math.hypot(e1,e2) or 1.0
            e1/=norm; e2/=norm
            u1=e1/math.sqrt(M_SI); u2=e2/math.sqrt(M_N)
            max_u=max(abs(u1),abs(u2),1e-12)
            u1/=max_u; u2/=max_u
            if w2<0: w_meV=-HBAR*math.sqrt(-w2)/MEV_TO_J
            else: w_meV=HBAR*math.sqrt(w2)/MEV_TO_J
            branches.append({'w2':w2,'w_meV':w_meV,'e1':e1,'e2':e2,'u1':u1,'u2':u2,'pol':pol,'type':typ,'label':f"{typ}-{pol}"})
    branches.sort(key=lambda b: b['w_meV'])
    return branches

def _k_from_E(E_meV): return 2*math.pi*E_meV/HC
def _bose(w,T):
    if w<=0.1: return 1.0
    kT=0.08617*T
    if kT<1e-9: return 1.0
    x=w/kT
    if x>20: return 1.0
    try: return 1.0/(math.exp(x)-1)+1
    except: return 1.0

def _gen_lattice(nx=6,ny=4):
    pts=[]
    for i in range(-nx//2,nx//2+1):
        for j in range(-ny//2,ny//2+1):
            ox=i*A1[0]+j*A2[0]; oy=i*A1[1]+j*A2[1]
            pts.append((ox,oy,0)); pts.append((ox+BASIS_N[0],oy+BASIS_N[1],1))
    return pts

def _install_controls(app):
    old=document.getElementById(_PANEL_ID)
    if old: old.parentNode.removeChild(old)
    panel=document.createElement('section')
    panel.id=_PANEL_ID
    panel.style.cssText='box-sizing:border-box;width:1050px;max-width:95vw;padding:14px 18px;margin:0 0 10px;background:#121a1e;border:1px solid #2a3a3f;color:#e6f2ee;font:11px/1.4 ui-monospace;display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px'
    html=''
    html+='<div style="grid-column:1/-1;display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px">'
    html+='<strong style="font-size:15px;color:#66e0b1">Hexagonal Si3N4 Thin Film - IXS</strong>'
    html+='<span style="color:#80948e">D(q)e=w2e - 15-25 keV to meV loss</span></div>'
    html+=f'<label>E_in keV <b id="vEin" style="color:#f4be5c"></b><input id="sEin" type="range" min="15000000" max="25000000" step="100000" value="{int(app.Ein)}" style="width:100%"></label>'
    html+=f'<label>Resolution dE meV <b id="vdE" style="color:#66e0b1"></b><input id="sdE" type="range" min="0.5" max="5" step="0.1" value="{app.dE}" style="width:100%"></label>'
    html+=f'<label>Scattering 2theta <b id="vTh"></b><input id="sTh" type="range" min="5" max="85" step="1" value="{app.theta_deg}" style="width:100%"></label>'
    html+=f'<label>Azimuth phi <b id="vPh"></b><input id="sPh" type="range" min="0" max="360" step="2" value="{app.phi_deg}" style="width:100%"></label>'
    html+='<label>Branch<select id="sBr" style="background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:5px"><option value="0">0 LA acoustic</option><option value="1">1 TA acoustic</option><option value="2">2 LO optical</option><option value="3" selected>3 TO optical</option></select></label>'
    html+=f'<label>Temp K <b id="vT"></b><input id="sT" type="range" min="10" max="600" step="10" value="{app.T}" style="width:100%"></label>'
    html+='<div style="display:flex;gap:6px;align-items:end"><button id="bPlay" style="padding:7px 12px;background:#66e0b1;color:#10201a;border:0;font-weight:bold;cursor:pointer">Pause</button><button id="bScan" style="padding:7px 10px;background:#1e2a2e;color:#a0b8b1;border:1px solid #344a4f;cursor:pointer">Scan q</button><button id="bInst" style="padding:7px 10px;background:#1e2a2e;color:#ff6b7a;border:1px solid #4a3440;cursor:pointer">Instability</button></div>'
    html+='<div id="ixs-info" style="grid-column:1/-1;color:#7a9590;font-size:10px;border-top:1px solid #223035;padding-top:6px"></div>'
    panel.innerHTML=html
    document.getElementById('canvas-container').parentNode.insertBefore(panel, document.getElementById('canvas-container'))
    def upd():
        app.Ein=float(document['sEin'].value); app.dE=float(document['sdE'].value)
        app.theta_deg=float(document['sTh'].value); app.phi_deg=float(document['sPh'].value)
        app.T=float(document['sT'].value); app.branch_idx=int(document['sBr'].value)
        document['vEin'].textContent=f"{app.Ein/1e6:.1f} keV"
        document['vdE'].textContent=f"{app.dE:.1f}"; document['vTh'].textContent=f"{app.theta_deg:.0f}°"
        document['vPh'].textContent=f"{app.phi_deg:.0f}°"; document['vT'].textContent=f"{int(app.T)}K"
        k=_k_from_E(app.Ein); qmag=2*k*math.sin(math.radians(app.theta_deg)/2)
        ph=math.radians(app.phi_deg); app.qx=qmag*math.cos(ph); app.qy=qmag*math.sin(ph)
        app.branches=_dynamical_matrix(app.qx,app.qy,kL=app.cur_KL,kT=app.cur_KT)
    for sid in ['sEin','sdE','sTh','sPh','sT','sBr']:
        document[sid].bind('input', lambda e: upd())
    def tPlay(e):
        app.playing=not app.playing; document['bPlay'].textContent='Pause' if app.playing else 'Play'
    def tScan(e):
        app.auto_scan=not app.auto_scan
        document['bScan'].style.background='#66e0b1' if app.auto_scan else '#1e2a2e'
        document['bScan'].style.color='#10201a' if app.auto_scan else '#a0b8b1'
    def tInst(e):
        app.show_instability=not app.show_instability
        if app.show_instability: app.cur_KL=-12.0; app.cur_KT=-6.0
        else: app.cur_KL=K_L; app.cur_KT=K_T
        document['bInst'].style.background='#ff6b7a' if app.show_instability else '#1e2a2e'
        document['bInst'].style.color='#fff' if app.show_instability else '#ff6b7a'
        app.dispersion=[]
        for q in app.path_pts:
            br=_dynamical_matrix(q[0],q[1],kL=app.cur_KL,kT=app.cur_KT)
            app.dispersion.append([b['w_meV'] for b in br])
        upd()
    document['bPlay'].bind('click', tPlay); document['bScan'].bind('click', tScan); document['bInst'].bind('click', tInst)
    upd()

def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=30; app.background=BG
    app.Ein=20000000.0; app.dE=1.8; app.theta_deg=35.0; app.phi_deg=20.0; app.T=300.0
    app.branch_idx=3; app.playing=True; app.auto_scan=False; app.show_instability=False
    app.time=0.0; app.amplitude=6.0; app.cur_KL=K_L; app.cur_KT=K_T
    app.lattice=_gen_lattice(6,4)
    k=_k_from_E(app.Ein); qmag=2*k*math.sin(math.radians(app.theta_deg)/2)
    ph=math.radians(app.phi_deg); app.qx=qmag*math.cos(ph); app.qy=qmag*math.sin(ph)
    app.branches=_dynamical_matrix(app.qx,app.qy,kL=app.cur_KL,kT=app.cur_KT)
    Gamma=(0,0); M=(math.pi/A_LATT, math.pi/(math.sqrt(3)*A_LATT)); Kpt=(4*math.pi/(3*A_LATT),0)
    def lerp(a,b,t): return (a[0]*(1-t)+b[0]*t, a[1]*(1-t)+b[1]*t)
    app.path_pts=[]
    for seg in [(Gamma,M),(M,Kpt),(Kpt,Gamma)]:
        for s in range(30): app.path_pts.append(lerp(seg[0],seg[1],s/29))
    app.dispersion=[]
    for q in app.path_pts:
        br=_dynamical_matrix(q[0],q[1],kL=app.cur_KL,kT=app.cur_KT)
        app.dispersion.append([b['w_meV'] for b in br])
    _install_controls(app)

def onStep(app):
    if not app.playing: return
    app.time+=0.04
    if app.auto_scan:
        app.phi_deg=(app.phi_deg+0.7)%360; app.theta_deg=30+15*math.sin(app.time*0.25)
        k=_k_from_E(app.Ein); qmag=2*k*math.sin(math.radians(app.theta_deg)/2)
        ph=math.radians(app.phi_deg); app.qx=qmag*math.cos(ph); app.qy=qmag*math.sin(ph)
        app.branches=_dynamical_matrix(app.qx,app.qy,kL=app.cur_KL,kT=app.cur_KT)
        try:
            document['sPh'].value=str(app.phi_deg); document['sTh'].value=str(app.theta_deg)
            document['vPh'].textContent=f"{app.phi_deg:.0f}°"; document['vTh'].textContent=f"{app.theta_deg:.0f}°"
        except: pass

def _clip(x,y,x0,y0,w,h): return x0+4 <= x <= x0+w-4 and y0+4 <= y <= y0+h-4

def _draw_lattice(app,x0,y0,w,h):
    drawRect(x0,y0,w,h, fill=rgb(13,20,24), border=rgb(42,58,63), borderWidth=1)
    drawLabel('REAL SPACE - Hexagonal Si3N4 phonon (clipped)', x0+8, y0+12, size=10, fill=MUTED, align='left')
    cx=x0+w*0.5; cy=y0+h*0.55; scale=13.0
    br=app.branches[app.branch_idx] if app.branch_idx < len(app.branches) else app.branches[0]
    qx,qy=app.qx,app.qy; qn=math.hypot(qx,qy)+1e-9; qhx=qx/qn; qhy=qy/qn
    px,py=(qhx,qhy) if br['pol']=='L' else (-qhy,qhx)
    omega_anim=max(0.6, min(5.0, abs(br['w_meV'])*0.12))
    for (x,y,typ) in app.lattice:
        if typ!=0: continue
        for (x2,y2,typ2) in app.lattice:
            if typ2!=1: continue
            if math.hypot(x2-x,y2-y) > D0*1.35 or math.hypot(x2-x,y2-y)<0.1: continue
            X1=cx+x*scale; Y1=cy+y*scale; X2=cx+x2*scale; Y2=cy+y2*scale
            if not (_clip(X1,Y1,x0,y0,w,h) and _clip(X2,Y2,x0,y0,w,h)): continue
            ph1=qx*x+qy*y - app.time*omega_anim*6; ph2=qx*x2+qy*y2 - app.time*omega_anim*6
            d1=br['u1']*math.cos(ph1)*app.amplitude; d2=br['u2']*math.cos(ph2)*app.amplitude
            X1d=X1+d1*px*1.8; Y1d=Y1+d1*py*1.8; X2d=X2+d2*px*1.8; Y2d=Y2+d2*py*1.8
            if not (_clip(X1d,Y1d,x0,y0,w,h) and _clip(X2d,Y2d,x0,y0,w,h)): continue
            drawLine(X1d,Y1d,X2d,Y2d, fill=rgb(55,65,70), lineWidth=1)
    for (x,y,typ) in app.lattice:
        X=cx+x*scale; Y=cy+y*scale
        if not _clip(X,Y,x0,y0,w,h): continue
        ph=qx*x+qy*y - app.time*omega_anim*6
        amp=(br['u1'] if typ==0 else br['u2'])*math.cos(ph)*app.amplitude
        Xd=X+amp*px*1.8; Yd=Y+amp*py*1.8
        if not _clip(Xd,Yd,x0,y0,w,h): continue
        if typ==0: drawCircle(Xd,Yd,6, fill=BLUE, border=rgb(180,210,255), borderWidth=1)
        else: drawCircle(Xd,Yd,4.5, fill=GOLD, border=rgb(255,230,160), borderWidth=1)
    col=MINT if br['w_meV']>=0 else RED
    drawLabel(f"q={qn:.2f} A-1  w={br['w_meV']:.1f} meV {br['label']} {'UNSTABLE' if br['w_meV']<0 else ''}", x0+8, y0+h-10, size=10, fill=col, align='left')

def _draw_brillouin(app,x0,y0,w,h):
    drawRect(x0,y0,w,h, fill=rgb(13,20,24), border=rgb(42,58,63), borderWidth=1)
    drawLabel('BRILLOUIN ZONE - static (q marker moves)', x0+8, y0+12, size=9, fill=MUTED, align='left')
    cx=x0+w*0.5; cy=y0+h*0.55; R=min(w,h)*0.34
    hex_pts=[]
    for i in range(6):
        ang=math.radians(30+i*60); hex_pts.append((cx+R*math.cos(ang), cy+R*math.sin(ang)))
    for i in range(6):
        x1,y1=hex_pts[i]; x2,y2=hex_pts[(i+1)%6]; drawLine(x1,y1,x2,y2, fill=rgb(70,90,95), lineWidth=2)
    drawCircle(cx,cy,3, fill=INK); drawLabel('G', cx+6, cy-8, size=10, fill=INK, align='left')
    q_scale=R/1.2; qx_s=cx+app.qx*q_scale; qy_s=cy-app.qy*q_scale
    drawLine(cx,cy,qx_s,qy_s, fill=CYAN, lineWidth=2); drawCircle(qx_s,qy_s,5, fill=CYAN, border=INK, borderWidth=1)
    drawLabel('q', qx_s+7, qy_s-7, size=10, fill=CYAN, align='left')

def _draw_dispersion(app,x0,y0,w,h):
    drawRect(x0,y0,w,h, fill=rgb(13,20,24), border=rgb(42,58,63), borderWidth=1)
    drawLabel('DISPERSION w(q) - static bands, marker dynamic', x0+8, y0+12, size=9, fill=MUTED, align='left')
    pad_l=36; pad_r=8; pad_t=22; pad_b=18
    ax=x0+pad_l; ay=y0+pad_t; aw=w-pad_l-pad_r; ah=h-pad_t-pad_b
    drawRect(ax,ay,aw,ah, fill=rgb(10,18,22), border=rgb(40,55,60), borderWidth=1)
    all_w=[]
    for row in app.dispersion:
        for v in row: all_w.append(v)
    w_min=min(all_w)-3; w_max=max(all_w)+5
    if w_min>0: w_min=-5
    n=len(app.path_pts); cols=[MINT,CYAN,GOLD,PURPLE]
    for b_idx in range(4):
        for i in range(n-1):
            x1=ax+(i/(n-1))*aw; x2=ax+((i+1)/(n-1))*aw
            y1v=app.dispersion[i][b_idx]; y2v=app.dispersion[i+1][b_idx]
            y1=ay+ah-(y1v-w_min)/(w_max-w_min)*ah; y2=ay+ah-(y2v-w_min)/(w_max-w_min)*ah
            col=RED if y1v<0 or y2v<0 else cols[b_idx]; lw=3 if b_idx==app.branch_idx else 1.2
            drawLine(x1,y1,x2,y2, fill=col, lineWidth=lw)
    for frac,label in [(0,'G'),(0.33,'M'),(0.66,'K'),(1.0,'G')]:
        x=ax+frac*aw; drawLine(x,ay,x,ay+ah, fill=rgb(50,65,70), lineWidth=1, dashes=[3,3]); drawLabel(label,x,ay+ah+10,size=9,fill=MUTED,align='center')
    best_i=0; best_d=1e9
    for i,q in enumerate(app.path_pts):
        d=(q[0]-app.qx)**2+(q[1]-app.qy)**2
        if d<best_d: best_d=d; best_i=i
    xq=ax+(best_i/(n-1))*aw; drawLine(xq,ay,xq,ay+ah, fill=CYAN, lineWidth=1)
    br=app.branches[app.branch_idx]; yq=ay+ah-(br['w_meV']-w_min)/(w_max-w_min)*ah
    drawCircle(xq, max(ay+2,min(ay+ah-2,yq)), 4, fill=CYAN, border=INK)
    drawLabel(f"{w_min:.0f}", ax-4, ay+ah, size=8, fill=MUTED, align='right')
    drawLabel(f"{w_max:.0f} meV", ax-4, ay+4, size=8, fill=MUTED, align='right')
    if w_min<0:
        y0_line=ay+ah-(0-w_min)/(w_max-w_min)*ah
        drawRect(ax,y0_line,aw,ay+ah-y0_line, fill=rgb(60,25,30)); drawLabel('w2<0', ax+aw-2, y0_line+10, size=8, fill=RED, align='right')

def _draw_ixs(app,x0,y0,w,h):
    drawRect(x0,y0,w,h, fill=rgb(13,20,24), border=rgb(42,58,63), borderWidth=1)
    drawLabel('IXS SPECTRUM - dynamic: I~|Q·e|2/w', x0+8, y0+12, size=9, fill=MUTED, align='left')
    bar_x=x0+8; bar_y=y0+24; bar_w=w-16; bar_h=10
    drawRect(bar_x,bar_y,bar_w,bar_h, fill=rgb(30,40,45), border=rgb(60,75,80), borderWidth=1)
    frac=(app.Ein-15000000)/10000000; drawRect(bar_x,bar_y,bar_w*max(0,min(1,frac)),bar_h, fill=BLUE)
    drawLabel(f"E_in={app.Ein/1e6:.1f}keV lam={HC/app.Ein:.3f}A", bar_x+4, bar_y+7, size=8, fill=INK, align='left')
    ax=x0+8; ay=y0+44; aw=w-16; ah=h-62
    drawRect(ax,ay,aw,ah, fill=rgb(10,18,22), border=rgb(40,55,60), borderWidth=1)
    x_min=0; x_max=110
    for meV in [0,20,40,60,80,100]:
        xx=ax+(meV-x_min)/(x_max-x_min)*aw; drawLine(xx,ay,xx,ay+ah, fill=rgb(35,45,50), lineWidth=1, dashes=[2,4]); drawLabel(f"{meV}",xx,ay+ah+9,size=8,fill=MUTED,align='center')
    intens=[]
    for br in app.branches:
        qdot=0.9 if br['pol']=='L' else 0.25
        intens.append(qdot*qdot*_bose(abs(br['w_meV']),app.T)/(abs(br['w_meV'])+1.5))
    max_I=max(intens) if intens else 1.0; max_I=max(max_I,0.5)
    def gauss(x,x0,s,a): return a*math.exp(-0.5*((x-x0)/s)**2) if s>1e-9 else 0
    prev=None
    for px_i in range(int(aw)):
        x_meV=x_min+(px_i/aw)*(x_max-x_min)
        y_sum=gauss(x_meV,0,max(0.3,app.dE*0.45),max_I*1.0)
        for idx,br in enumerate(app.branches):
            w=abs(br['w_meV'])
            if w<0.5 or w>x_max or w<0: continue
            y_sum+=gauss(x_meV,w,max(0.4,app.dE),intens[idx])
        y_s=ay+ah-(y_sum/max_I/1.6)*ah*0.85; y_s=max(ay+2,min(ay+ah-2,y_s)); x_s=ax+px_i
        if prev: drawLine(prev[0],prev[1],x_s,y_s, fill=MINT, lineWidth=2)
        prev=(x_s,y_s)
    cols=[MINT,CYAN,GOLD,PURPLE]
    for idx,br in enumerate(app.branches):
        w=abs(br['w_meV'])
        if w<0.5 or w>x_max: continue
        xx=ax+(w-x_min)/(x_max-x_min)*aw; yy=ay+ah-(intens[idx]/max_I/1.6)*ah*0.85
        col=cols[idx%4]
        if idx==app.branch_idx:
            drawCircle(xx,yy,5, fill=col, border=INK, borderWidth=1)
            drawLabel(f"{br['label']} {br['w_meV']:.1f}meV", xx+6, yy-10, size=8, fill=col, align='left')
        else: drawCircle(xx,yy,3, fill=col)
    hw=abs(app.branches[app.branch_idx]['w_meV']) if app.branches else 0
    drawLabel(f"E_out={(app.Ein-hw)/1e6:.6f}keV loss={hw:.1f}meV dE={app.dE:.1f}meV 1:{app.Ein/app.dE:.0f}M", x0+8, y0+h-7, size=8, fill=GOLD, align='left')

def _draw_geometry(app,x0,y0,w,h):
    drawRect(x0,y0,w,h, fill=rgb(13,20,24), border=rgb(42,58,63), borderWidth=1)
    drawLabel('GEOMETRY k_in - k_out = Q', x0+6, y0+10, size=8, fill=MUTED, align='left')
    cx=x0+w*0.5; cy=y0+h*0.5+4; k_len=w*0.36
    ang_in=math.radians(app.phi_deg-app.theta_deg/2); ang_out=math.radians(app.phi_deg+app.theta_deg/2)
    x_in=cx-k_len*math.cos(ang_in)*0.5; y_in=cy-k_len*math.sin(ang_in)*0.5
    x_tip=cx+k_len*math.cos(ang_in)*0.5; y_tip=cy+k_len*math.sin(ang_in)*0.5
    drawLine(x_in,y_in,x_tip,y_tip, fill=BLUE, lineWidth=2); drawCircle(x_tip,y_tip,3, fill=BLUE)
    k_out_len=k_len*(1-abs(app.branches[app.branch_idx]['w_meV'])/app.Ein*3)
    x_out_base=cx-k_out_len*math.cos(ang_out)*0.5; y_out_base=cy-k_out_len*math.sin(ang_out)*0.5
    x_out=cx+k_out_len*math.cos(ang_out)*0.5; y_out=cy+k_out_len*math.sin(ang_out)*0.5
    drawLine(x_out_base,y_out_base,x_out,y_out, fill=GOLD, lineWidth=2); drawCircle(x_out,y_out,3, fill=GOLD)
    drawLine(x_tip,y_tip,x_out,y_out, fill=CYAN, lineWidth=1, dashes=[4,4])
    drawLabel(f"|k|={_k_from_E(app.Ein):.1f} A-1 |Q|={math.hypot(app.qx,app.qy):.2f}", x0+6, y0+h-6, size=8, fill=rgb(100,115,120), align='left')

def redrawAll(app):
    drawRect(0,0,app.width,app.height, fill=BG)
    drawLabel('IXS - Phonon Interaction', 20, 22, size=18, fill=INK, bold=True, align='left')
    drawLabel(f"E_in {app.Ein/1e6:.1f}keV dE {app.dE:.1f}meV hw 1-100meV Si3N4 12nm", 20, 38, size=10, fill=MUTED, align='left')
    _draw_geometry(app, 20, 50, 310, 72)
    drawRect(345,50,685,72, fill=rgb(18,28,32), border=rgb(42,58,63), borderWidth=1)
    drawLabel('THREE ENERGIES IN ONE IXS EVENT:', 355, 58, size=9, fill=GOLD, bold=True, align='left')
    hw=abs(app.branches[app.branch_idx]['w_meV']) if app.branches else 0
    drawLabel(f"1) E_in = {app.Ein:.0f} meV = {app.Ein/1e6:.1f} keV lam={HC/app.Ein:.3f}A", 355, 70, size=9, fill=INK, align='left')
    drawLabel(f"2) hw = {hw:.1f} meV lost E_out={app.Ein-hw:.0f} meV", 355, 82, size=9, fill=MINT, align='left')
    drawLabel(f"3) dE = {app.dE:.1f} meV resolution 1 in {app.Ein/app.dE:.0f}M ex 23,724,000->23,723,900", 355, 94, size=9, fill=CYAN, align='left')
    _draw_lattice(app,20,130,500,330)
    _draw_brillouin(app,535,130,235,155)
    _draw_dispersion(app,785,130,245,155)
    _draw_ixs(app,535,295,495,165)
    drawRect(20,470,1010,38, fill=rgb(18,26,30), border=rgb(42,58,63), borderWidth=1)
    drawLabel('THIN FILM: 3 layers c-axis out-of-plane', 28, 478, size=9, fill=MUTED, align='left')
    drawRect(28,490,994,6, fill=rgb(30,40,45), border=rgb(60,70,75), borderWidth=1)
    drawRect(28,490,994*0.7,6, fill=BLUE)
    drawLabel('Si3N4 12nm - instability when w2<0', 400, 498, size=8, fill=RED if app.show_instability else MUTED, align='left')
    try:
        info=document.getElementById('ixs-info')
        if info:
            br=app.branches[app.branch_idx]; qn=math.hypot(app.qx,app.qy)
            info.innerHTML=f"D(q) diag: " + ", ".join([f"{b['label']}={b['w_meV']:.1f}meV" for b in app.branches]) + f" | q=({app.qx:.2f},{app.qy:.2f}) |q|={qn:.2f} k={_k_from_E(app.Ein):.2f} | e=[{br['e1']:.2f},{br['e2']:.2f}]"
    except: pass

def onKeyPress(app,key):
    if key==' ': app.playing=not app.playing
    elif key.lower()=='r': app.time=0
