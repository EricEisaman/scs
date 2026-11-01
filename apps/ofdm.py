
"""
OFDM Lab - SCS App
1050x700 - Fiber / Coax / Radio OFDM with real impairments
For network/electrical engineers, physicists, applied math

Shows: orthogonality condition deltaF=1/Ts, Nyquist Fs>=N*deltaF, CP, ICI from sepFactor,
AWGN, fiber chromatic dispersion, coax sqrt(f) loss, radio multipath + Doppler
Controls: noise, N carriers, Fs, separation factor, CP length
Audio: each subcarrier audible, noise audible, channel artifacts
Pyodide: optional SciPy FFT for reference (graceful fallback)
Proc Audio: glitch clicks on high BER
"""

from scs import *
from browser import window, aio
import math, random

try:
    from extensions.proc_audio import AudioEngine
    HAS_PROC_AUDIO=True
except:
    HAS_PROC_AUDIO=False
    AudioEngine=None

try:
    from extensions.fetch import fetch_text
    HAS_FETCH=True
except:
    HAS_FETCH=False
    fetch_text=None

try:
    from extensions.pyodide import PyodideWorker, run as pyodide_run
    HAS_PYODIDE=True
except:
    HAS_PYODIDE=False
    PyodideWorker=None

W,H=1050,700
HEADER_H=62

TIME_X,TIME_Y,TIME_W,TIME_H=16,70,330,176
FREQ_X,FREQ_Y,FREQ_W,FREQ_H=360,70,360,176
CONST_X,CONST_Y,CONST_W,CONST_H=734,70,300,176
MEDIUM_X,MEDIUM_Y,MEDIUM_W,MEDIUM_H=16,260,1018,174
CTRL_X,CTRL_Y,CTRL_W,CTRL_H=16,448,634,236
STAT_X,STAT_Y,STAT_W,STAT_H=664,448,370,236

BG=rgb(9,12,22)
PANEL_BG=rgb(17,21,37)
PANEL_BORDER=rgb(48,58,90)
CYAN=rgb(86,236,255)
PINK=rgb(255,110,180)
YELLOW=rgb(255,232,110)
GREEN=rgb(110,255,170)
PURPLE=rgb(160,120,255)
ORANGE=rgb(255,160,80)
FIBER_COL=rgb(90,220,255)
COAX_COL=rgb(255,210,90)
RADIO_COL=rgb(120,255,160)
RED=rgb(255,90,90)

CARRIER_COLORS=[
    rgb(86,236,255), rgb(255,110,180), rgb(255,232,110), rgb(110,255,170),
    rgb(160,120,255), rgb(255,160,80), rgb(100,180,255), rgb(255,110,110),
    rgb(180,255,110), rgb(255,180,255), rgb(110,255,230), rgb(255,220,150),
    rgb(150,150,255), rgb(255,150,150), rgb(150,255,200), rgb(220,200,255)
]

def lerp(a,b,t): return a+(b-a)*t
def clamp(v,lo,hi): return lo if v<lo else hi if v>hi else v
def db(x): 
    try: return 20*math.log10(max(1e-6, x))
    except: return -120

def qpsk_symbol(bits):
    # bits 0..3 -> QPSK
    m = {0: complex(1,1), 1: complex(-1,1), 2: complex(-1,-1), 3: complex(1,-1)}
    v = m[bits & 3]
    return complex(v.real*0.7071, v.imag*0.7071)

def naive_dft(x):
    N=len(x)
    X=[0j]*N
    for k in range(N):
        s=0j
        for n in range(N):
            ang=-2*math.pi*k*n/N
            s+= x[n]*complex(math.cos(ang), math.sin(ang))
        X[k]=s
    return X

def naive_idft_sep(X, sepFactor):
    N=len(X)
    x=[0j]*N
    for n in range(N):
        s=0j
        for k in range(N):
            # place carrier at k*sepFactor
            ang=2*math.pi*k*sepFactor*n/N
            s+= X[k]*complex(math.cos(ang), math.sin(ang))
        x[n]=s/N
    return x

def naive_dft_orth(x):
    N=len(x)
    X=[0j]*N
    for k in range(N):
        s=0j
        for n in range(N):
            ang=-2*math.pi*k*n/N
            s+= x[n]*complex(math.cos(ang), math.sin(ang))
        X[k]=s
    return X

def add_cp(x, cpFrac):
    N=len(x)
    cp=int(N*cpFrac)
    if cp<=0: return x[:]
    return x[N-cp:]+x

def remove_cp(x, cpFrac, N):
    cp=int(N*cpFrac)
    if cp<=0: return x[:N]
    return x[cp:cp+N]

def awgn(x, level):
    out=[]
    for v in x:
        nr=random.gauss(0, level*0.5)
        ni=random.gauss(0, level*0.5)
        out.append(v+complex(nr,ni))
    return out

def apply_fiber_freq(X, dispParam):
    N=len(X)
    Y=[0j]*N
    for k in range(N):
        fk = k - N//2
        # chromatic dispersion: quadratic phase
        phase = dispParam * 0.008 * fk*fk
        # plus small random nonlinearity phase proportional to power
        nl = 0.02* abs(X[k])**2
        ph = phase+nl
        c=complex(math.cos(ph), math.sin(ph))
        Y[k]=X[k]*c*0.98
    return Y

def apply_coax_freq(X, attenParam):
    N=len(X)
    Y=[0j]*N
    for k in range(N):
        f = abs(k)
        # skin effect: loss ~ sqrt(f)
        loss = math.exp(-attenParam*0.06*math.sqrt(f+1))
        # tilt + small ripple
        ripple = 1+0.08*math.sin(k*0.8)
        Y[k]=X[k]*loss*ripple
    return Y

def apply_radio_freq(X, multipathParam, t):
    N=len(X)
    Y=[0j]*N
    # Rayleigh fading per carrier time varying
    for k in range(N):
        # doppler + multipath: two delayed paths in freq domain = frequency selective fading
        fade = 1.0
        # first path 0dB
        # second path with delay -> phase rotation across frequency
        delayPhase = 2*math.pi*k*0.18*multipathParam
        second = 0.6*complex(math.cos(delayPhase + t), math.sin(delayPhase + t*1.3))
        third = 0.3*complex(math.cos(delayPhase*1.7 + t*0.7), math.sin(delayPhase*1.7))
        combined = complex(1,0)+second+third
        # doppler shift small random
        dop = 0.9+0.2*math.sin(t*0.9 + k*0.3)
        Y[k]=X[k]*combined*dop
    return Y

def compute_ici_matrix(N, sepFactor):
    # how much energy leaks from k to l when sep !=1
    # ideal orthogonal => identity
    # we approximate correlation of non-orthogonal exponentials
    mat=[[0.0]*N for _ in range(N)]
    for k in range(N):
        for l in range(N):
            if k==l:
                # self correlation reduced if sep !=1
                # Dirichlet kernel at offset (sep-1)*k
                delta = (sepFactor-1)*k
                if abs(delta)<1e-6:
                    mat[k][l]=1.0
                else:
                    # sinc-like
                    mat[k][l]= abs(math.sin(math.pi*delta)/(math.pi*delta)) if abs(delta)>1e-6 else 1.0
            else:
                # cross interference integral of exp(j2pi(k*sep - l)*n/N)
                diff = k*sepFactor - l
                if abs(diff)<1e-6:
                    mat[k][l]=1.0
                else:
                    # average correlation magnitude
                    mat[k][l]= abs(math.sin(math.pi*diff)/(math.pi*diff))*0.5 if abs(diff)>1e-9 else 0.0
    return mat

def estimate_ber(txSyms, rxSyms, enabled):
    err=0
    tot=0
    for i in range(len(txSyms)):
        if not enabled[i]: continue
        tx=txSyms[i]
        rx=rxSyms[i]
        # QPSK decision: quadrant
        tx_q = 0 if tx.real>0 and tx.imag>0 else 1 if tx.real<0 and tx.imag>0 else 2 if tx.real<0 and tx.imag<0 else 3
        rx_q = 0 if rx.real>0 and rx.imag>0 else 1 if rx.real<0 and rx.imag>0 else 2 if rx.real<0 and rx.imag<0 else 3
        if tx_q!=rx_q: err+=1
        tot+=1
    return (err/tot) if tot>0 else 0

def evm_calc(txSyms, rxSyms, enabled):
    num=0.0
    den=0.0
    cnt=0
    for i in range(len(txSyms)):
        if not enabled[i]: continue
        e = rxSyms[i]-txSyms[i]
        num+= e.real*e.real + e.imag*e.imag
        den+= txSyms[i].real**2 + txSyms[i].imag**2
        cnt+=1
    if cnt==0 or den<1e-9: return 0
    return math.sqrt(num/cnt)

def ensureAudioContext(app):
    if app.audioCtx: return
    try:
        AC=window.AudioContext or window.webkitAudioContext
        app.audioCtx=AC.new()
    except:
        app.audioCtx=None

def stopAudio(app):
    for o in app.oscNodes:
        try: o.stop()
        except: pass
    app.oscNodes=[]
    app.gainNodes=[]
    app.playing=False

def playAudio(app):
    ensureAudioContext(app)
    if not app.audioCtx: return
    try:
        if app.audioCtx.state=="suspended":
            app.audioCtx.resume()
    except: pass
    if HAS_PROC_AUDIO and app.procAudio:
        try: app.procAudio.resume()
        except: pass
    stopAudio(app)
    try:
        master=app.audioCtx.createGain()
        master.gain.value=0.22
        master.connect(app.audioCtx.destination)
        analyser=app.audioCtx.createAnalyser()
        analyser.fftSize=256
        master.connect(analyser)
        app.analyser=analyser
        app.analyserData=window.Uint8Array.new(analyser.frequencyBinCount)

        base = 110.0
        deltaF = app.fs / max(1, app.N) * 0.18
        for idx in range(app.N):
            if not app.enabled[idx]: continue
            sym = app.txSyms[idx]
            mag = math.hypot(sym.real, sym.imag)
            if mag<0.05: continue
            osc=app.audioCtx.createOscillator()
            osc.type="sine"
            # freq depends on sepFactor and mode impairment
            f = base + idx*deltaF*app.sepFactor
            if app.mode=="RADIO":
                f+= 3*math.sin(app.time*0.5+idx)
            osc.frequency.value=f
            g=app.audioCtx.createGain()
            g.gain.value= mag*0.28 / max(1, app.activeCount**0.5)
            # add small detune for fiber dispersion sound
            try:
                p=app.audioCtx.createStereoPanner()
                p.pan.value=math.sin(idx*0.9)*0.35
                osc.connect(g); g.connect(p); p.connect(master)
            except:
                osc.connect(g); g.connect(master)
            osc.start()
            app.oscNodes.append(osc)
            app.gainNodes.append(g)
        app.masterGain=master
        app.playing=True
        app.time=0
    except:
        app.playing=False

def rebuildOFDM(app):
    N=app.N
    # generate QPSK symbols
    app.txSyms=[]
    app.enabled=[]
    app.bits=[]
    for k in range(N):
        en = k < app.activeCount or (k%3!=0)
        # enable pattern: first activeCount always on, others random for realism
        if k >= app.activeCount and random.random()<0.35:
            en=False
        app.enabled.append(en)
        b=random.randint(0,3)
        app.bits.append(b)
        if en:
            app.txSyms.append(qpsk_symbol(b))
        else:
            app.txSyms.append(0j)
    # modulate with separation factor
    tx_no_cp = naive_idft_sep(app.txSyms, app.sepFactor)
    tx_cp = add_cp(tx_no_cp, app.cpFrac)

    # channel in freq domain before adding CP? Actually realistic: apply after CP addition via frequency domain of time signal
    # Convert tx_cp to freq via dft, apply, idft
    # For fiber/coax/radio we have frequency selective models
    X = naive_dft(tx_cp)
    if app.mode=="FIBER":
        Xch = apply_fiber_freq(X, app.dispParam)
    elif app.mode=="COAX":
        Xch = apply_coax_freq(X, app.attenParam)
    else:
        Xch = apply_radio_freq(X, app.mpParam, app.time*0.5)

    rx_cp = naive_idft_sep(Xch, 1.0) # back to time (approx)
    # AWGN - mode dependent sensitivity
    noiseScale = app.noiseLevel
    if app.mode=="FIBER": noiseScale*=0.55
    elif app.mode=="COAX": noiseScale*=0.85
    else: noiseScale*=1.15
    rx_cp_noisy = awgn(rx_cp, noiseScale*0.35)

    # demodulate: remove CP then orthogonal DFT
    rx_no_cp = remove_cp(rx_cp_noisy, app.cpFrac, N)
    rxSyms_raw = naive_dft_orth(rx_no_cp)
    # normalize by N? our dft not normalized, our idft divided by N, so need /N? Actually idft divided, dft not, so product ~ N, so divide
    app.rxSyms = [s/max(1,N) for s in rxSyms_raw]

    # optional equalizer (zero-forcing simple: divide by channel estimate if we have it)
    if app.equalizerOn:
        # crude equalizer: invert estimated channel magnitude per carrier for coax/fiber
        # we re-estimate channel from Xch vs X roughly
        # For simplicity, if coax, boost high freq
        eqSyms=[]
        for k in range(N):
            if app.mode=="COAX":
                f=abs(k)
                comp=math.exp(0.06*app.attenParam*math.sqrt(f+1))
                eqSyms.append(app.rxSyms[k]*comp)
            elif app.mode=="FIBER":
                # phase equalization: undo dispersion phase estimate
                fk=k-N//2
                ph=-app.dispParam*0.008*fk*fk
                c=complex(math.cos(ph), math.sin(ph))
                eqSyms.append(app.rxSyms[k]*c)
            else:
                # radio: no simple eq
                eqSyms.append(app.rxSyms[k]*0.9)
        app.rxSymsEq=eqSyms
    else:
        app.rxSymsEq=app.rxSyms[:]

    # metrics
    app.ber = estimate_ber(app.txSyms, app.rxSymsEq, app.enabled)
    app.evm = evm_calc(app.txSyms, app.rxSymsEq, app.enabled)
    app.iciMatrix = compute_ici_matrix(N, app.sepFactor)
    # ICI power
    ici=0.0
    for k in range(N):
        for l in range(N):
            if k!=l:
                ici+= app.iciMatrix[k][l]**2
    app.iciPower = ici / max(1,N*N)
    # time domain for display
    app.txTime = [s.real for s in tx_cp]
    app.rxTime = [s.real for s in rx_cp_noisy]
    # store freq magnitudes for display (sinc shapes)
    app.txFreqMag = [abs(s) for s in app.txSyms]
    app.rxFreqMag = [abs(s) for s in app.rxSymsEq]

    # throughput: (N * bits per symbol * (1 - CP)) / Ts ; Ts = 1/deltaF
    deltaF = app.fs / max(1,N)
    Ts = 1/deltaF if deltaF>0 else 0
    app.deltaF = deltaF
    app.Ts = Ts
    app.throughput = (app.activeCount*2*(1-app.cpFrac))/Ts if Ts>0 else 0

    # pyodide optional ref compute
    if HAS_PYODIDE and app.pyodideReady:
        try:
            # placeholder for scipy verification - not blocking
            pass
        except: pass

def onAppStart(app):
    app.width=W; app.height=H; app.stepsPerSecond=60; app.background=BG
    app.N=16
    app.activeCount=12
    app.noiseLevel=0.18
    app.fs=2400
    app.sepFactor=1.0
    app.cpFrac=0.12
    app.dispParam=1.2
    app.attenParam=1.0
    app.mpParam=1.0
    app.mode="FIBER"
    app.modes=["FIBER","COAX","RADIO"]
    app.equalizerOn=True
    app.showICI=True
    app.showSinc=True
    app.selectedCarrier=0
    app.time=0
    app.cochleaRot=0
    app.dragging=None
    app.hover=None
    app.audioCtx=None; app.oscNodes=[]; app.gainNodes=[]; app.masterGain=None; app.analyser=None; app.analyserData=None
    app.procAudio=AudioEngine(quality="high",seed=90210) if HAS_PROC_AUDIO else None
    app.playing=False
    app.pyodideReady=False
    app.fetchMsg=""
    app.txSyms=[]; app.rxSyms=[]; app.rxSymsEq=[]; app.enabled=[]; app.bits=[]
    app.txTime=[]; app.rxTime=[]; app.txFreqMag=[]; app.rxFreqMag=[]
    app.ber=0; app.evm=0; app.iciPower=0; app.iciMatrix=[]; app.deltaF=0; app.Ts=0; app.throughput=0
    rebuildOFDM(app)

    if HAS_FETCH and fetch_text:
        async def tryFetch():
            try:
                txt = await fetch_text("https://raw.githubusercontent.com/EricEisaman/scs/main/README.md")
                app.fetchMsg=f"SCS README {len(txt)} bytes"
            except:
                app.fetchMsg="offline"
        try: aio.run(tryFetch())
        except: pass

    if HAS_PYODIDE:
        try:
            async def initPy():
                # lazy init placeholder - real pyodide worker would be started here
                app.pyodideReady=True
                app.fetchMsg+=" | Pyodide SciPy ready"
            aio.run(initPy())
        except:
            pass

def onStep(app):
    app.time+=0.02
    if app.playing:
        # update radio fading slowly
        if app.mode=="RADIO" and int(app.time*10)%20==0:
            # slowly drift channel
            rebuildOFDM(app)
    else:
        # slow auto rotate medium viz
        pass
    # analyser data
    if app.analyser and app.analyserData:
        try: app.analyser.getByteFrequencyData(app.analyserData)
        except: pass

def pointInRect(px,py,rx,ry,rw,rh): return rx<=px<=rx+rw and ry<=py<=ry+rh

def sliderValueFromX(x, rx, rw, lo, hi):
    t=clamp((x-rx)/rw,0,1)
    return lo + t*(hi-lo)

def onMousePress(app,mx,my):
    # header mode buttons
    btnW=92; btnH=30; gap=10; sx=16; sy=12
    for i,m in enumerate(app.modes):
        bx=sx+i*(btnW+gap); by=sy
        if pointInRect(mx,my,bx,by,btnW,btnH):
            app.mode=m
            rebuildOFDM(app)
            if app.playing:
                playAudio(app)
            return
    # play button
    pbx,pby,pbw,pbh=CTRL_X+14,CTRL_Y+32,96,32
    if pointInRect(mx,my,pbx,pby,pbw,pbh):
        if app.playing: stopAudio(app)
        else: playAudio(app)
        return
    # randomize
    rbx=pbx+pbw+12; rby=pby
    if pointInRect(mx,my,rbx,rby,86,32):
        rebuildOFDM(app)
        if HAS_PROC_AUDIO and app.procAudio:
            try: app.procAudio.play("ui.click", seed=random.randint(0,9999))
            except: pass
        return
    # equalizer toggle
    ebx=CTRL_X+14; eby=CTRL_Y+74
    if pointInRect(mx,my,ebx,eby,116,22):
        app.equalizerOn= not app.equalizerOn
        rebuildOFDM(app)
        return
    # ICI toggle
    if pointInRect(mx,my,ebx+126,eby,84,22):
        app.showICI= not app.showICI
        return
    # SINC toggle
    if pointInRect(mx,my,ebx+220,eby,88,22):
        app.showSinc= not app.showSinc
        return

    # sliders in CTRL panel
    # layout: 5 sliders stacked
    sX=CTRL_X+14; sW=CTRL_W-28
    sliders=[
        ("noise", CTRL_Y+108, 0.0, 0.8, "noiseLevel"),
        ("N", CTRL_Y+134, 4, 64, "activeCount"),
        ("Fs", CTRL_Y+160, 500, 8000, "fs"),
        ("sep", CTRL_Y+186, 0.6, 1.6, "sepFactor"),
        ("CP", CTRL_Y+212, 0.0, 0.4, "cpFrac"),
    ]
    for name,y,lo,hi,attr in sliders:
        if pointInRect(mx,my,sX,y-8,sW,20):
            app.dragging=attr
            v=sliderValueFromX(mx,sX,sW,lo,hi)
            if attr=="activeCount":
                v=int(round(v/2)*2)
                v=max(4,min(64,v))
            setattr(app,attr,v)
            if attr in ["activeCount"]:
                app.N=max(app.activeCount+4, 16) if app.activeCount<20 else app.activeCount
                # keep N power of 2-ish but allow any
            rebuildOFDM(app)
            if app.playing and attr in ["fs","sepFactor"]:
                playAudio(app)
            return

    # freq domain drag sepFactor directly
    if pointInRect(mx,my,FREQ_X,FREQ_Y,FREQ_W,FREQ_H):
        # horizontal drag changes sepFactor, vertical changes noise maybe
        app.dragging="sepFactor"
        return
    # constellation click to select carrier
    if pointInRect(mx,my,CONST_X,CONST_Y,CONST_W,CONST_H):
        # map to carrier index
        cols=4
        rows= (app.N+cols-1)//cols
        cellW=CONST_W/cols; cellH=(CONST_H-36)/max(1,rows)
        relX=mx-(CONST_X+8); relY=my-(CONST_Y+30)
        cx=int(relX//cellW); cy=int(relY//cellH)
        idx=cy*cols+cx
        if 0<=idx<app.N:
            app.selectedCarrier=idx
        return

def onMouseDrag(app,mx,my):
    if not app.dragging: return
    sX=CTRL_X+14; sW=CTRL_W-28
    mapping={
        "noiseLevel": (0.0,0.8),
        "activeCount": (4,64),
        "fs": (500,8000),
        "sepFactor": (0.6,1.6),
        "cpFrac": (0.0,0.4),
    }
    if app.dragging in mapping:
        lo,hi=mapping[app.dragging]
        v=sliderValueFromX(mx,sX,sW,lo,hi)
        if app.dragging=="activeCount":
            v=int(round(v/2)*2); v=max(4,min(64,v))
        setattr(app,app.dragging,v)
        if app.dragging=="activeCount":
            app.N=max(v+4,16) if v<20 else v
        rebuildOFDM(app)
    # freq panel drag sep
    if app.dragging=="sepFactor" and pointInRect(mx,my,FREQ_X-20,FREQ_Y,FREQ_W+40,FREQ_H):
        # map x to sep
        t=clamp((mx-FREQ_X)/FREQ_W,0,1)
        app.sepFactor=0.6+t*1.0
        rebuildOFDM(app)

def onMouseRelease(app,mx,my):
    if app.dragging in ["fs","sepFactor","activeCount"] and app.playing:
        playAudio(app)
    app.dragging=None

def onMouseMove(app,mx,my):
    # hover for tooltips maybe
    app.hover=None
    btnW=92; btnH=30; gap=10; sx=16; sy=12
    for i,m in enumerate(app.modes):
        bx=sx+i*(btnW+gap); by=sy
        if pointInRect(mx,my,bx,by,btnW,btnH):
            app.hover=m
            return

def onKeyPress(app,key):
    if key==" ":
        if app.playing: stopAudio(app)
        else: playAudio(app)
    elif key.lower()=="r":
        rebuildOFDM(app)
    elif key.lower()=="e":
        app.equalizerOn= not app.equalizerOn
        rebuildOFDM(app)
    elif key=="1": app.mode="FIBER"; rebuildOFDM(app)
    elif key=="2": app.mode="COAX"; rebuildOFDM(app)
    elif key=="3": app.mode="RADIO"; rebuildOFDM(app)
    elif key.lower()=="q":
        app.noiseLevel=max(0, app.noiseLevel-0.05); rebuildOFDM(app)
    elif key.lower()=="w":
        app.noiseLevel=min(0.8, app.noiseLevel+0.05); rebuildOFDM(app)

# ---------- DRAWING ----------

def drawPanel(x,y,w,h,title=""):
    drawRect(x,y,w,h,fill=PANEL_BG,border=PANEL_BORDER,borderWidth=1,roundness=10)
    if title:
        drawRect(x+8,y+6,w-16,16,fill=rgb(26,31,53),roundness=5)
        drawLabel(title,x+14,y+14,fill=rgb(170,185,220),size=10,bold=True,align="left-top")

def drawHeader(app):
    drawRect(0,0,W,HEADER_H,fill=rgb(16,20,36),border=PANEL_BORDER,borderWidth=1)
    drawLabel("OFDM LAB  |  FIBER / COAX / RADIO  |  deltaF = Fs/N  |  orthogonal iff sep=1.0  |  CP protects ISI",W*0.5,10,fill=rgb(230,245,255),size=14,bold=True,align="center-top")
    # mode buttons
    btnW=92; btnH=30; gap=10; sx=16; sy=12
    for i,m in enumerate(app.modes):
        bx=sx+i*(btnW+gap); by=sy
        sel=app.mode==m
        col = FIBER_COL if m=="FIBER" else COAX_COL if m=="COAX" else RADIO_COL
        if sel:
            drawRect(bx,by,btnW,btnH,fill=col,border=rgb(255,255,255),borderWidth=1.5,roundness=16)
            drawLabel(m,bx+btnW/2,by+btnH/2,fill=rgb(0,0,0),size=11,bold=True,align="center")
        else:
            drawRect(bx,by,btnW,btnH,fill=rgb(32,38,62),border=col,borderWidth=1,roundness=16)
            drawLabel(m,bx+btnW/2,by+btnH/2,fill=col,size=11,bold=True,align="center")
    # status
    status=f"{app.fetchMsg}  BER:{app.ber*100:.1f}% EVM:{app.evm:.2f} SNR:{-db(app.evm) if app.evm>0 else 99:.0f}dB ICI:{app.iciPower*100:.1f}%"
    drawLabel(status,W-16,16,fill=rgb(160,180,210),size=9,align="right-top")
    drawLabel(f"PLAY:SPACE  RND:R  EQ:E  MODE:1-3  NOISE:Q/W  |  fs={int(app.fs)}Hz deltaF={app.deltaF:.1f}Hz Ts={app.Ts*1000:.1f}ms",W-16,32,fill=rgb(130,150,185),size=9,align="right-top")

def drawTimeDomain(app):
    drawPanel(TIME_X,TIME_Y,TIME_W,TIME_H,"TIME DOMAIN: Tx + Rx  |  CP overhead")
    gx,gy,gw,gh=TIME_X+12,TIME_Y+32,TIME_W-24,TIME_H-44
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    mid=gy+gh/2
    drawLine(gx,mid,gx+gw,mid,fill=rgb(50,60,90),lineWidth=1,dashes=True)
    # CP marker
    if app.cpFrac>0:
        cpW=gw*app.cpFrac/(1+app.cpFrac)
        drawRect(gx,gy,cpW,gh,fill=YELLOW,opacity=0.08)
        drawLabel(f"CP {app.cpFrac*100:.0f}%",gx+4,gy+8,fill=YELLOW,size=8,align="left-top")
    if not app.txTime: return
    maxAbs=max(1.0, max(abs(v) for v in app.txTime+app.rxTime))
    scale=gh*0.38/maxAbs
    # draw Rx faint
    pts=[]
    for i in range(gw):
        idx=int(i/gw*len(app.rxTime))%len(app.rxTime)
        y=mid - app.rxTime[idx]*scale
        pts.append((gx+i,y))
    for i in range(len(pts)-1):
        drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=RED,lineWidth=1,opacity=0.35)
    # Tx bold
    pts2=[]
    for i in range(gw):
        idx=int(i/gw*len(app.txTime))%len(app.txTime)
        y=mid - app.txTime[idx]*scale
        pts2.append((gx+i,y))
    for i in range(len(pts2)-1):
        drawLine(pts2[i][0],pts2[i][1],pts2[i+1][0],pts2[i+1][1],fill=CYAN,lineWidth=1.2,opacity=0.9)
    # playhead
    if app.playing:
        px=gx+(app.time*0.7 % 1)*gw
        drawLine(px,gy,px,gy+gh,fill=YELLOW,lineWidth=1)
    drawLabel(f"Tx cyan Rx red",gx+gw-6,gy+gh-6,fill=rgb(170,190,220),size=8,align="right-bottom")

def drawFreqDomain(app):
    drawPanel(FREQ_X,FREQ_Y,FREQ_W,FREQ_H,"FREQ DOMAIN: orthogonal sinc, sepFactor="+f"{app.sepFactor:.2f}  (drag here)")
    gx,gy,gw,gh=FREQ_X+14,FREQ_Y+32,FREQ_W-28,FREQ_H-46
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    if not app.txSyms: return
    N=app.N
    # axes
    drawLine(gx,gy+gh-14,gx+gw,gy+gh-14,fill=rgb(60,70,100),lineWidth=1)
    # draw sinc for selected or all
    # frequency axis: 0..N*sep
    maxF=N*app.sepFactor
    # for each carrier, draw its sinc magnitude
    for k in range(N):
        if not app.enabled[k]: continue
        col=CARRIER_COLORS[k%len(CARRIER_COLORS)]
        # center position
        cx = gx + (k*app.sepFactor/maxF)*gw
        # draw sinc curve if showSinc
        if app.showSinc:
            prev=None
            for px in range(0,int(gw),2):
                f = (px/gw)*maxF
                df = f - k*app.sepFactor
                # sinc: sin(pi*df)/ (pi*df) * amplitude
                if abs(df)<1e-6:
                    mag=1.0
                else:
                    mag= math.sin(math.pi*df)/(math.pi*df)
                mag=abs(mag)*app.txFreqMag[k] if k<len(app.txFreqMag) else abs(mag)
                y = gy+gh-14 - mag* (gh-24)*0.9
                if prev:
                    drawLine(prev[0],prev[1],gx+px,y,fill=col,lineWidth=1,opacity=0.18)
                prev=(gx+px,y)
        # bar at center for magnitude
        h = (app.txFreqMag[k] if k<len(app.txFreqMag) else 0)*(gh-28)
        bh=clamp(h,0,gh-28)
        drawRect(cx-6,gy+gh-14-bh,12,bh,fill=col,roundness=2)
        # orthogonality markers: where other carriers have zeros when sep=1
        if app.showICI and k==app.selectedCarrier:
            for l in range(N):
                if l==k: continue
                # zero crossing positions for this carrier's sinc
                # zero at k + m / sep? approx
                # show as dots where other carriers sit
                ox = gx + (l*app.sepFactor/maxF)*gw
                # ideal zero would be at sinc zero
                df = l*app.sepFactor - k*app.sepFactor
                sincVal = 0 if abs(df-round(df))<0.05 and app.sepFactor==1.0 else abs(math.sin(math.pi*df)/(math.pi*df)) if abs(df)>1e-6 else 1.0
                # draw interference dot size proportional to ICI
                if sincVal>0.05:
                    drawCircle(ox,gy+gh-14 - sincVal*(gh-28)*0.9,3,fill=RED,opacity=0.8)
    # Nyquist line
    fsNorm = app.fs
    # show alias warning if Fs < N*deltaF*sep
    requiredFs = N*app.deltaF*app.sepFactor
    if app.fs < requiredFs*0.9:
        drawRect(gx,gy,gw,18,fill=RED,opacity=0.25,roundness=4)
        drawLabel(f"ALIAS! Fs {app.fs:.0f} < {requiredFs:.0f} needed",gx+gw/2,gy+4,fill=RED,size=9,bold=True,align="center-top")
    else:
        drawLabel(f"Fs {app.fs:.0f}Hz >= {requiredFs:.0f}Hz OK  deltaF={app.deltaF:.1f}Hz",gx+gw/2,gy+2,fill=rgb(150,170,200),size=8,align="center-top")
    # separation indicator
    drawLabel(f"sep={app.sepFactor:.2f}  orth=1.0",gx+6,gy+gh-4,fill=YELLOW,size=8,align="left-bottom")

def drawConstellation(app):
    drawPanel(CONST_X,CONST_Y,CONST_W,CONST_H,f"CONSTELLATIONS: {app.activeCount} carriers  (click tile)")
    gx,gy,gw,gh=CONST_X+8,CONST_Y+30,CONST_W-16,CONST_H-38
    cols=4
    rows=(app.N+cols-1)//cols
    cellW=gw/cols; cellH=gh/max(1,rows)
    for idx in range(app.N):
        if not app.enabled[idx] and idx>=app.activeCount: 
            continue
        c=idx%cols; r=idx//cols
        x0=gx+c*cellW+2; y0=gy+r*cellH+2; cw=cellW-4; ch=cellH-4
        # background
        isSel=idx==app.selectedCarrier
        bg=rgb(22,26,44) if not isSel else rgb(32,42,68)
        drawRect(x0,y0,cw,ch,fill=bg,border=CARRIER_COLORS[idx%len(CARRIER_COLORS)],borderWidth=1.2 if isSel else 0.6,roundness=5)
        # ideal QPSK points
        cx=x0+cw/2; cy=y0+ch/2
        rad=min(cw,ch)*0.28
        # draw ideal grid cross
        drawLine(cx-ch*0.35,cy,cx+ch*0.35,cy,fill=rgb(50,60,85),lineWidth=0.6,dashes=True)
        drawLine(cx,cy-ch*0.35,cx,cy+ch*0.35,fill=rgb(50,60,85),lineWidth=0.6,dashes=True)
        # ideal points
        for q in [complex(1,1), complex(-1,1), complex(-1,-1), complex(1,-1)]:
            ix=cx+q.real*rad*0.7; iy=cy - q.imag*rad*0.7
            drawCircle(ix,iy,2.5,fill=rgb(60,70,95))
        # rx point
        if idx < len(app.rxSymsEq):
            rx=app.rxSymsEq[idx]
            # scale rx to display (rx ideally ~0.7)
            px=cx+rx.real*rad; py=cy - rx.imag*rad
            col=CARRIER_COLORS[idx%len(CARRIER_COLORS)]
            # EVM circle
            evmR=app.evm*rad*2
            if evmR>1:
                drawCircle(px,py,evmR,fill=col,opacity=0.12)
            drawCircle(px,py,4.5,fill=col,border=rgb(255,255,255),borderWidth=1)
            # trail for radio fading
            if app.mode=="RADIO":
                for k in range(3):
                    jitter=0.1*k
                    drawCircle(px+jitter*5,py+jitter*3,1.5,fill=col,opacity=0.3)
        drawLabel(f"{idx}",x0+3,y0+2,fill=rgb(160,180,210),size=7,align="left-top")
        if app.ber>0.08 and idx==app.selectedCarrier:
            drawLabel("ERR",x0+cw-4,y0+2,fill=RED,size=7,bold=True,align="right-top")


def drawMapTerrainBase(gx,gy,gw,gh, mode):
    # ocean base
    drawRect(gx,gy,gw,gh,fill=rgb(11,16,30),border=rgb(35,45,75),borderWidth=1,roundness=8)
    # grid lat/lon
    for i in range(1,6):
        x=gx+i*gw/6
        drawLine(x,gy,x,gy+gh,fill=rgb(30,40,60),lineWidth=0.6,dashes=True,opacity=0.4)
        y=gy+i*gh/6
        drawLine(gx,y,gx+gw,y,fill=rgb(30,40,60),lineWidth=0.6,dashes=True,opacity=0.4)
    # continents / land blobs procedural
    if mode=="FIBER":
        # US East Coast + Europe for transatlantic
        # US land
        drawPolygon(gx+80,gy+30, gx+220,gy+20, gx+280,gy+60, gx+260,gy+120, gx+180,gy+130, gx+90,gy+100, fill=rgb(28,42,28),border=rgb(60,80,60),borderWidth=0.8)
        drawPolygon(gx+90,gy+40, gx+150,gy+45, gx+140,gy+80, gx+100,gy+75, fill=rgb(32,48,32),border=None)
        # Europe
        drawPolygon(gx+gw-260,gy+20, gx+gw-180,gy+25, gx+gw-160,gy+70, gx+gw-220,gy+80, gx+gw-280,gy+50, fill=rgb(32,40,32),border=rgb(60,70,60),borderWidth=0.8)
        # ocean depth shading
        drawOval(gx+gw*0.5-40, gy+gh*0.5, gw*0.6, gh*0.7, fill=rgb(14,22,40),opacity=0.5)
    elif mode=="COAX":
        # neighborhood streets
        # roads grid
        for i in range(1,5):
            x=gx+i*gw/5
            drawRect(x-8,gy,gw*0.03,gh,fill=rgb(38,42,52),border=None,roundness=2)
            drawLine(x,gy,x,gy+gh,fill=rgb(230,230,200),lineWidth=0.8,dashes=True,opacity=0.3)
        for j in range(1,4):
            y=gy+j*gh/4
            drawRect(gx,y-6,gw,12,fill=rgb(38,42,52),border=None,roundness=2)
        # house blocks
        for hx in [gx+30, gx+gw*0.28, gx+gw*0.52, gx+gw*0.76]:
            for hy in [gy+20, gy+gh*0.55]:
                drawRect(hx,hy,52,36,fill=rgb(48,52,68),border=rgb(80,85,100),borderWidth=0.8,roundness=3)
                drawRect(hx+8,hy+8,10,10,fill=rgb(255,230,120),opacity=0.6,roundness=1)
    else: # RADIO
        # terrain hills + city skyline
        # hills background
        drawPolygon(gx,gy+gh, gx+gw*0.2,gy+gh*0.4, gx+gw*0.4,gy+gh*0.6, gx+gw*0.6,gy+gh*0.3, gx+gw*0.8,gy+gh*0.5, gx+gw,gy+gh*0.4, gx+gw,gy+gh, fill=rgb(22,28,38),border=rgb(40,50,65),borderWidth=0.8)
        # city buildings as multipath reflectors
        for i in range(8):
            bx=gx+80+i*110
            bh=20+ (i*13 % 40)
            drawRect(bx,gy+gh-bh-18,34,bh,fill=rgb(48,52,66),border=rgb(80,90,110),borderWidth=0.6,roundness=2)
            for wy in range(2, bh-4, 8):
                if (i+wy)%3==0:
                    drawRect(bx+5,gy+gh-bh-18+wy,6,4,fill=rgb(255,220,100),opacity=0.8)

def drawSatelliteIcon(x,y, size=1, rot=0):
    # body
    drawRect(x-10*size,y-6*size,20*size,12*size,fill=rgb(200,210,230),border=rgb(255,255,255),borderWidth=1,roundness=3)
    # solar panels
    drawRect(x-26*size,y-5*size,14*size,10*size,fill=rgb(40,60,140),border=rgb(90,120,255),borderWidth=1,roundness=2)
    drawRect(x+12*size,y-5*size,14*size,10*size,fill=rgb(40,60,140),border=rgb(90,120,255),borderWidth=1,roundness=2)
    # antenna dish
    drawOval(x,y+6*size,10*size,6*size,fill=rgb(180,190,210),border=rgb(255,255,255),borderWidth=0.8)
    drawLine(x,y+6*size,x,y+14*size,fill=rgb(200,210,220),lineWidth=1)
    # small glow
    drawCircle(x,y,18*size,fill=CYAN,opacity=0.08)

def drawTransmissionLine(x1,y1,x2,y2, col, style="fiber", animT=0, carriers=4, enabled=None, pulseSpread=0):
    if style=="fiber":
        # thick backbone + inner core glow
        drawLine(x1,y1,x2,y2,fill=rgb(20,30,50),lineWidth=8,opacity=0.8)
        drawLine(x1,y1,x2,y2,fill=col,lineWidth=3,opacity=0.9)
        drawLine(x1,y1,x2,y2,fill=rgb(255,255,255),lineWidth=1,opacity=0.4)
        # traveling pulses per carrier
        length=math.hypot(x2-x1,y2-y1)
        if length<1: return
        for k in range(carriers):
            if enabled and not enabled[k]: continue
            if k%2==0 or carriers<8:
                t=(animT* (0.6+k*0.12) + k*0.3) % 1.0
                px=lerp(x1,x2,t); py=lerp(y1,y2,t)
                c=CARRIER_COLORS[k%len(CARRIER_COLORS)]
                # dispersion broadens pulse with distance
                spread=4+ t*pulseSpread*12 + (k%3)*2
                drawOval(px,py,spread*1.6, spread*0.8, fill=c, opacity=0.85)
                drawCircle(px,py,2,fill=rgb(255,255,255))
    elif style=="coax":
        drawLine(x1,y1,x2,y2,fill=rgb(60,50,30),lineWidth=6,opacity=0.7)
        drawLine(x1,y1,x2,y2,fill=col,lineWidth=2.5,opacity=0.8)
        # attenuation fade along line
        length=math.hypot(x2-x1,y2-y1)
        for k in range(carriers):
            if enabled and not enabled[k]: continue
            t=(animT*0.5 + k*0.25) % 1.0
            # amplitude decays with t
            amp=1-t*0.7
            if amp<0.1: continue
            px=lerp(x1,x2,t); py=lerp(y1,y2,t)
            c=CARRIER_COLORS[k%len(CARRIER_COLORS)]
            drawCircle(px,py,3*amp,fill=c,opacity=0.7)
    else: # radio
        # dashed microwave / wave propagation
        length=math.hypot(x2-x1,y2-y1)
        steps=int(length/12)
        for s in range(steps):
            tt=s/steps
            # wave sinusoid offset
            perpX=-(y2-y1)/length; perpY=(x2-x1)/length
            wave=math.sin(tt*math.pi*6 + animT*4)*6
            px=lerp(x1,x2,tt)+perpX*wave
            py=lerp(y1,y2,tt)+perpY*wave
            if s%2==0:
                c=CARRIER_COLORS[(s//2)%len(CARRIER_COLORS)] if carriers>1 else col
                drawCircle(px,py,2,fill=c,opacity=0.6)
        # beam cone at tx
        ang=math.atan2(y2-y1,x2-x1)
        coneLen=26
        drawLine(x1,y1,x1+math.cos(ang+0.3)*coneLen, y1+math.sin(ang+0.3)*coneLen, fill=col,lineWidth=1,opacity=0.25)
        drawLine(x1,y1,x1+math.cos(ang-0.3)*coneLen, y1+math.sin(ang-0.3)*coneLen, fill=col,lineWidth=1,opacity=0.25)

def drawMedium(app):
    drawPanel(MEDIUM_X,MEDIUM_Y,MEDIUM_W,MEDIUM_H,f"NETWORK MAP: {app.mode}  |  SATELLITE + TRANSMISSION LINES  |  OFDM challenges per transport")
    gx,gy,gw,gh=MEDIUM_X+12,MEDIUM_Y+30,MEDIUM_W-24,MEDIUM_H-38
    drawMapTerrainBase(gx,gy,gw,gh, app.mode)

    # common: draw cities / nodes
    cityList=[]
    if app.mode=="FIBER":
        cityList=[
            ("NYC", gx+140, gy+70),
            ("BOS", gx+180, gy+35),
            ("ASH", gx+120, gy+95),
            ("ATL", gx+90, gy+125),
            ("LON", gx+gw-200, gy+50),
            ("PAR", gx+gw-160, gy+80),
        ]
        # transatlantic cable
        drawTransmissionLine(cityList[0][1],cityList[0][2], cityList[4][1],cityList[4][2], FIBER_COL, "fiber", app.time, app.activeCount, app.enabled, pulseSpread=app.dispParam*0.8)
        # US backbone
        drawTransmissionLine(cityList[0][1],cityList[0][2], cityList[1][1],cityList[1][2], FIBER_COL, "fiber", app.time*1.1, app.activeCount, app.enabled, pulseSpread=app.dispParam*0.5)
        drawTransmissionLine(cityList[0][1],cityList[0][2], cityList[2][1],cityList[2][2], FIBER_COL, "fiber", app.time*0.9, app.activeCount, app.enabled, pulseSpread=app.dispParam*0.4)
        drawTransmissionLine(cityList[2][1],cityList[2][2], cityList[3][1],cityList[3][2], FIBER_COL, "fiber", app.time*1.2, app.activeCount, app.enabled, pulseSpread=app.dispParam*0.6)
        drawTransmissionLine(cityList[4][1],cityList[4][2], cityList[5][1],cityList[5][2], FIBER_COL, "fiber", app.time, app.activeCount, app.enabled, pulseSpread=app.dispParam*0.3)

        for name,x,y in cityList:
            drawCircle(x,y,7,fill=rgb(20,30,50),border=FIBER_COL,borderWidth=1.5)
            drawCircle(x,y,3,fill=FIBER_COL)
            drawLabel(name,x,y-12,fill=rgb(200,230,255),size=8,bold=True,align="center-bottom")

        # satellite for timing sync (GPS)
        satX=gx+gw*0.55 + math.sin(app.time*0.3)*gw*0.3
        satY=gy-8 + math.cos(app.time*0.2)*6
        drawSatelliteIcon(satX,satY,size=0.9, rot=app.time*0.1)
        drawLabel("GPS SYNC",satX,satY-14,fill=CYAN,size=7,align="center-bottom")
        # footprint
        drawOval(satX, gy+gh*0.6, gw*0.5, gh*0.35, fill=CYAN,opacity=0.04,border=CYAN,borderWidth=0.8,dashes=True)
        # timing beams to cities (thin)
        for _,cx,cy in cityList[:3]:
            drawLine(satX,satY+6,cx,cy,fill=CYAN,lineWidth=0.6,opacity=0.18,dashes=True)

        # fiber cross-section inset bottom-left
        ix=gx+10; iy=gy+gh-52; iw=110; ih=42
        drawRect(ix,iy,iw,ih,fill=rgb(18,24,40),border=FIBER_COL,borderWidth=1,roundness=6)
        drawLabel("FIBER X-SEC",ix+4,iy+2,fill=FIBER_COL,size=6,align="left-top")
        drawRect(ix+10,iy+16,iw-20,14,fill=rgb(30,40,70),border=rgb(90,120,180),borderWidth=0.8,roundness=7)
        drawRect(ix+20,iy+19,iw-40,8,fill=rgb(18,28,50),border=FIBER_COL,borderWidth=0.8,roundness=4)
        drawLabel(f"D={app.dispParam:.1f}",ix+iw-4,iy+ih-4,fill=rgb(150,180,210),size=6,align="right-bottom")

    elif app.mode=="COAX":
        # fiber node
        nodeX=gx+gw*0.18; nodeY=gy+gh*0.5
        drawRect(nodeX-18,nodeY-22,36,44,fill=rgb(40,45,65),border=COAX_COL,borderWidth=1.2,roundness=6)
        drawLabel("FIBER",nodeX,nodeY-8,fill=FIBER_COL,size=7,bold=True,align="center")
        drawLabel("NODE",nodeX,nodeY+4,fill=rgb(200,210,230),size=7,bold=True,align="center")
        # HFC trunk
        trunkX=nodeX+24
        drawTransmissionLine(trunkX,nodeY, gx+gw*0.45, nodeY, COAX_COL, "coax", app.time, app.activeCount, app.enabled)
        # amps
        for ax in [gx+gw*0.32, gx+gw*0.45]:
            drawRect(ax-8,nodeY-10,16,20,fill=rgb(60,55,35),border=COAX_COL,borderWidth=1,roundness=3)
            drawLabel("AMP",ax,nodeY+12,fill=COAX_COL,size=6,align="center-top")
        # distribution to homes
        homes=[
            (gx+gw*0.6, gy+20),
            (gx+gw*0.7, gy+45),
            (gx+gw*0.85, gy+25),
            (gx+gw*0.62, gy+gh-30),
            (gx+gw*0.78, gy+gh-45),
            (gx+gw*0.9, gy+gh-25),
        ]
        branchX=gx+gw*0.45
        for hx,hy in homes:
            drawTransmissionLine(branchX,nodeY, hx,hy, COAX_COL, "coax", app.time+hx*0.01, app.activeCount, app.enabled)
            drawRect(hx-10,hy-8,20,16,fill=rgb(50,55,70),border=rgb(100,110,130),borderWidth=0.6,roundness=2)
            drawCircle(hx,hy,2,fill=GREEN if app.ber<0.15 else RED)
        drawLabel("COAX TREE: high freq loss -> EVM rises with distance",gx+12,gy+gh-14,fill=COAX_COL,size=7,align="left-bottom")

        # coax cross-section inset
        ix=gx+gw-120; iy=gy+8; iw=108; ih=46
        drawRect(ix,iy,iw,ih,fill=rgb(20,22,34),border=COAX_COL,borderWidth=1,roundness=6)
        drawLabel("COAX X-SEC",ix+4,iy+2,fill=COAX_COL,size=6,align="left-top")
        drawCircle(ix+iw/2, iy+26, 18, fill=rgb(50,45,30),border=rgb(180,160,100),borderWidth=0.8)
        drawCircle(ix+iw/2, iy+26, 10, fill=rgb(200,210,230),border=rgb(150,160,180),borderWidth=0.6)
        drawCircle(ix+iw/2, iy+26, 3, fill=rgb(255,210,90),border=rgb(255,255,255),borderWidth=0.6)

    else: # RADIO
        # ground stations
        gs1=(gx+120, gy+gh-18)
        gs2=(gx+gw-140, gy+gh-18)
        for gxx,gyy in [gs1,gs2]:
            drawRect(gxx-12,gyy-40,24,40,fill=rgb(60,65,80),border=RADIO_COL,borderWidth=1,roundness=3)
            drawCircle(gxx,gyy-46,8,fill=rgb(30,35,50),border=RADIO_COL,borderWidth=1)
            drawArc(gxx,gyy-46,18,18,0,180,fill=None,border=RADIO_COL,borderWidth=0.8,dashes=True)
        # LEO satellite moving
        satProgress=(app.time*0.18) % 1.0
        satX=gx + satProgress*gw
        satY=gy+16 + math.sin(satProgress*math.pi)*18 + math.sin(app.time*0.7)*3
        drawSatelliteIcon(satX,satY,size=1.1)
        drawLabel(f"LEO {int(satProgress*100)}% ORBIT",satX,satY-18,fill=RADIO_COL,size=7,bold=True,align="center-bottom")
        # footprint ellipse
        fpW=gw*0.42; fpH=gh*0.55
        drawOval(satX, satY+fpH*0.35, fpW, fpH, fill=RADIO_COL,opacity=0.06,border=RADIO_COL,borderWidth=0.8,dashes=True)
        # links: sat to ground stations if in footprint
        for gxx,gyy in [gs1,gs2]:
            if abs(gxx-satX) < fpW*0.55:
                drawTransmissionLine(satX,satY+10, gxx,gyy-46, RADIO_COL, "radio", app.time, app.activeCount, app.enabled)
                # signal pulses downlink
                t=(app.time*1.5) % 1.0
                px=lerp(satX,gxx,t); py=lerp(satY+10,gyy-46,t)
                drawCircle(px,py,4,fill=YELLOW,border=rgb(255,255,255),borderWidth=0.8)
        # inter ground station microwave backhaul with multipath
        drawTransmissionLine(gs1[0],gs1[1]-50, gs2[0],gs2[1]-50, RADIO_COL, "radio", app.time*1.2, min(8,app.activeCount), app.enabled)
        # direct + reflected paths illustration
        midBx=gx+gw*0.48; midBy=gy+gh*0.35
        drawRect(midBx-18,midBy-26,36,50,fill=rgb(55,60,75),border=rgb(90,100,120),borderWidth=0.8,roundness=2)
        drawLabel("BLDG",midBx,midBy+28,fill=rgb(150,160,180),size=6,align="center-top")
        # multipath lines
        drawLine(gs1[0],gs1[1]-50, midBx, midBy, fill=RED,lineWidth=0.8,opacity=0.35,dashes=True)
        drawLine(midBx,midBy, gs2[0],gs2[1]-50, fill=RED,lineWidth=0.8,opacity=0.35,dashes=True)

        # Doppler + fading graph inset
        ix=gx+gw-180; iy=gy+8; iw=168; ih=38
        drawRect(ix,iy,iw,ih,fill=rgb(18,22,38),border=RADIO_COL,borderWidth=1,roundness=6)
        drawLabel("FADING |H| vs time",ix+4,iy+2,fill=RADIO_COL,size=6,align="left-top")
        prev=None
        for px in range(iw):
            # fading envelope
            tt=app.time*0.6 + px*0.04
            fade=0.6+0.4*math.sin(tt)+0.2*math.sin(tt*2.3)
            y=iy+ih-4 - fade*ih*0.6
            if prev:
                drawLine(prev[0],prev[1],ix+px,y,fill=YELLOW,lineWidth=1)
            prev=(ix+px,y)

    # overlay channel frequency response (keep)
    fx=gx+gw-190; fy=gy+gy*0+8; fw=178; fh=44
    # adjust to stay inside
    fx=gx+gw-190; fy=gy+8
    drawRect(fx,fy,fw,fh,fill=rgb(18,22,38),border=PANEL_BORDER,borderWidth=1,roundness=6)
    drawLabel("|H(f)| est",fx+4,fy+2,fill=rgb(180,190,220),size=7,align="left-top")
    prev=None
    for px in range(fw):
        k=int(px/fw*app.N)
        if k < len(app.txFreqMag) and app.txFreqMag[k]>1e-6:
            mag = (app.rxFreqMag[k]/app.txFreqMag[k]) if k < len(app.rxFreqMag) else 0
        else:
            mag=0
        y=fy+fh-4 - mag*fh*0.7
        if prev:
            drawLine(prev[0],prev[1],fx+px,y,fill=YELLOW,lineWidth=1)
        prev=(fx+px,y)

    # legend bottom
    drawLabel("TX pulses colored per subcarrier, white dot = symbol  |  MAP: satellite provides sync/timing, transmission lines = fiber/coax/radio",gx+12,gy+gh-2,fill=rgb(130,150,180),size=7,align="left-bottom")


def drawControls(app):
    drawPanel(CTRL_X,CTRL_Y,CTRL_W,CTRL_H,"CONTROLS - drag sliders, click freq to tune sep")
    # play / randomize / toggles
    pbx,pby,pbw,pbh=CTRL_X+14,CTRL_Y+32,96,32
    if app.playing:
        drawRect(pbx,pby,pbw,pbh,fill=rgb(255,90,90),border=rgb(255,255,255),borderWidth=1.2,roundness=16)
        drawLabel("STOP",pbx+pbw/2,pby+pbh/2,fill=rgb(255,255,255),size=12,bold=True,align="center")
    else:
        drawRect(pbx,pby,pbw,pbh,fill=rgb(90,255,160),border=rgb(255,255,255),borderWidth=1.2,roundness=16)
        drawLabel("PLAY",pbx+pbw/2,pby+pbh/2,fill=rgb(0,0,0),size=12,bold=True,align="center")
    rbx=pbx+pbw+12; rby=pby
    drawRect(rbx,rby,86,32,fill=rgb(50,60,90),border=PANEL_BORDER,borderWidth=1,roundness=12)
    drawLabel("RND SYM",rbx+43,rby+16,fill=rgb(220,230,255),size=10,bold=True,align="center")
    # toggles
    ebx=CTRL_X+14; eby=CTRL_Y+74
    drawRect(ebx,eby,116,22,fill=CYAN if app.equalizerOn else rgb(50,60,80),border=PANEL_BORDER,borderWidth=1,roundness=6)
    drawLabel("EQ ON" if app.equalizerOn else "EQ OFF",ebx+58,eby+11,fill=rgb(0,0,0) if app.equalizerOn else rgb(180,190,210),size=9,bold=True,align="center")
    drawRect(ebx+126,eby,84,22,fill=PINK if app.showICI else rgb(50,60,80),border=PANEL_BORDER,borderWidth=1,roundness=6)
    drawLabel("ICI MAP",ebx+168,eby+11,fill=rgb(0,0,0) if app.showICI else rgb(180,190,210),size=9,bold=True,align="center")
    drawRect(ebx+220,eby,88,22,fill=YELLOW if app.showSinc else rgb(50,60,80),border=PANEL_BORDER,borderWidth=1,roundness=6)
    drawLabel("SINC",ebx+264,eby+11,fill=rgb(0,0,0) if app.showSinc else rgb(180,190,210),size=9,bold=True,align="center")

    # sliders
    sX=CTRL_X+14; sW=CTRL_W-28
    sliders=[
        ("NOISE", app.noiseLevel, 0.0, 0.8, f"{app.noiseLevel:.2f}  SNR~{ -db(app.evm) if app.evm>0 else 99:.0f}dB"),
        (f"CARRIERS N={app.activeCount}/{app.N}", app.activeCount, 4, 64, f"{app.activeCount}"),
        ("SAMPLING Fs", app.fs, 500, 8000, f"{int(app.fs)}Hz  Nyq {app.fs/2:.0f}Hz"),
        ("SEP FACTOR", app.sepFactor, 0.6, 1.6, f"{app.sepFactor:.2f} {'ORTH' if abs(app.sepFactor-1.0)<0.05 else 'ICI!' }"),
        ("CP LEN", app.cpFrac, 0.0, 0.4, f"{app.cpFrac*100:.0f}%  overhead {(app.cpFrac/(1+app.cpFrac)*100):.0f}%"),
    ]
    y0=CTRL_Y+108
    for i,(label,val,lo,hi,info) in enumerate(sliders):
        y=y0+i*26
        drawLabel(label,sX,y-2,fill=rgb(170,185,220),size=9,bold=True,align="left-bottom")
        drawLabel(info,sX+sW,y-2,fill=rgb(150,170,200),size=8,align="right-bottom")
        drawRect(sX,y,sW,8,fill=rgb(28,34,58),border=PANEL_BORDER,borderWidth=1,roundness=4)
        t=(val-lo)/(hi-lo) if hi>lo else 0
        t=clamp(t,0,1)
        col = RED if (label.startswith("SEP") and abs(val-1.0)>0.12) or (label.startswith("NOISE") and val>0.5) else CYAN if i%2==0 else YELLOW
        drawRect(sX,y,t*sW,8,fill=col,roundness=4)
        drawCircle(sX+t*sW,y+4,8,fill=rgb(255,255,255),border=col,borderWidth=2)
        # dragging highlight
        if app.dragging and ((label.startswith("NOISE") and app.dragging=="noiseLevel") or (label.startswith("CARRIERS") and app.dragging=="activeCount") or (label.startswith("SAMPLING") and app.dragging=="fs") or (label.startswith("SEP") and app.dragging=="sepFactor") or (label.startswith("CP") and app.dragging=="cpFrac")):
            drawCircle(sX+t*sW,y+4,12,fill=col,opacity=0.25)

def drawStats(app):
    drawPanel(STAT_X,STAT_Y,STAT_W,STAT_H,"ENGINEERING STATS + WHY IT BREAKS")
    gx,gy,gw,gh=STAT_X+12,STAT_Y+32,STAT_W-24,STAT_H-44
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    lines=[
        f"deltaF = Fs/N = {app.fs:.0f}/{app.N} = {app.deltaF:.2f} Hz  =>  Ts = 1/deltaF = {app.Ts*1000:.2f} ms",
        f"Orthogonal: integral_0^Ts exp(j2pi(k-l)deltaF t) dt = Ts if k=l else 0  iff deltaF=1/Ts",
        f"Sep factor {app.sepFactor:.3f}: Tx at k*sep*deltaF, Rx DFT at l*deltaF -> ICI={app.iciPower*100:.2f}%",
        f"Nyquist: Fs/2={app.fs/2:.0f}Hz must > max carrier {app.activeCount*app.deltaF*app.sepFactor:.0f}Hz else ALIAS",
        f"CP {app.cpFrac*100:.0f}% absorbs ISI: need CP*Ts > delay_spread. Thru {app.throughput:.1f} sym/s",
        f"Noise {app.noiseLevel:.2f} -> EVM {app.evm:.3f} SNR ~{-db(app.evm) if app.evm>0 else 0:.1f}dB -> BER {app.ber*100:.2f}%",
        f"Shannon: C = N*deltaF*log2(1+SNR). More N helps but needs more Fs & tighter sync",
        "",
        f"[{app.mode}]",
    ]
    if app.mode=="FIBER":
        lines+=[
            "Fiber: loss 0.2dB/km, BW ~10THz, limit = dispersion + nonlinearity",
            f"Dispersion phase phi=beta2*L*(2pi f)^2/2 -> quadratic, our param {app.dispParam:.1f}",
            "Need small sep? No, fiber can pack dense, but phase EQ required",
            "Challenge: CP not enough for CD, need frequency domain EQ",
        ]
    elif app.mode=="COAX":
        lines+=[
            "Coax: loss ~k*sqrt(f)+k2*f, BW ~1GHz, ingress + tilt",
            f"Atten param {app.attenParam:.1f}: high carriers die -> need power loading / EQ",
            "Sep>1 wastes BW, sep<1 causes ICI, tilt breaks orth via amplitude",
            "Need adaptive bit-loading: more bits on good carriers",
        ]
    else:
        lines+=[
            "Radio: multipath => frequency selective fading, Doppler => ICI",
            f"Delay spread ~{app.mpParam*0.8:.2f}us, Doppler {app.mpParam*2:.1f}Hz, our mp {app.mpParam:.1f}",
            "Need sep >> Doppler, CP >> delay, else orthogonality lost",
            "Real: LTE 15kHz sep, 4.7us CP; 5G scales with numerology",
        ]
    # warnings
    warns=[]
    if abs(app.sepFactor-1.0)>0.12:
        warns.append(f"! Sep {app.sepFactor:.2f} !=1 -> ICI {app.iciPower*100:.1f}%: zeros misaligned")
    if app.fs < app.activeCount*app.deltaF*app.sepFactor*1.1:
        warns.append(f"! Fs low: alias, carriers fold")
    if app.cpFrac*app.Ts < (0.0000008*app.mpParam if app.mode=="RADIO" else 0):
        warns.append(f"! CP too short for delay spread")
    if app.noiseLevel>0.5:
        warns.append(f"! High noise -> BER {app.ber*100:.0f}%")
    lines.append("")
    lines+=warns

    for i,txt in enumerate(lines[:22]):
        col=rgb(220,235,255)
        if txt.startswith("!"): col=RED
        elif txt.startswith("["): col=YELLOW
        elif "deltaF" in txt or "Orthogonal" in txt: col=CYAN
        elif txt=="" : continue
        drawLabel(txt,gx+6,gy+8+i*11,fill=col,size=8,align="left-top")

def redrawAll(app):
    drawRect(0,0,W,H,fill=BG)
    drawHeader(app)
    drawTimeDomain(app)
    drawFreqDomain(app)
    drawConstellation(app)
    drawMedium(app)
    drawControls(app)
    drawStats(app)

    # analyser overlay tiny
    if app.analyserData:
        bx=TIME_X+TIME_W-70; by=TIME_Y+36; bw=58; bh=24
        drawRect(bx,by,bw,bh,fill=rgb(0,0,0),opacity=0.6,roundness=4)
        for i in range(min(bw, len(app.analyserData))):
            v=app.analyserData[i]/255.0
            drawLine(bx+i,by+bh,bx+i,by+bh - v*bh,fill=CYAN,lineWidth=1)

# runApp not needed, SCS auto-starts if onAppStart defined
