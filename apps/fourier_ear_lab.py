"""
Fourier Ear Lab - SCS App 1050x700
Extensions: proc_audio, pyodide, fetch, file_loader
Core: Any function = sum of sines. Cochlea is live Fourier machine.
"""
from scs import *
from browser import window, aio
import math

try:
    from extensions.proc_audio import AudioEngine, Patch
    HAS_PROC_AUDIO = True
except:
    HAS_PROC_AUDIO = False
    AudioEngine = None

try:
    from extensions.pyodide import runner as pyodide_runner
    HAS_PYODIDE = True
except:
    try:
        from extensions.pyodide import PyodideRunner
        HAS_PYODIDE = True
    except:
        HAS_PYODIDE = False

try:
    from extensions.file_loader import load_image
    HAS_FILE_LOADER = True
except:
    HAS_FILE_LOADER = False

try:
    from extensions.fetch import fetch_json
    HAS_FETCH = True
except:
    HAS_FETCH = False

W,H = 1050,700
HEADER_H=52
TIME_X,TIME_Y,TIME_W,TIME_H = 18,64,628,262
SPEC_X,SPEC_Y,SPEC_W,SPEC_H = 666,64,366,262
COCH_X,COCH_Y,COCH_W,COCH_H = 18,340,628,344
CTRL_X,CTRL_Y,CTRL_W,CTRL_H = 666,340,366,344

BG=rgb(10,14,26)
PANEL_BG=rgb(18,22,38)
PANEL_BORDER=rgb(45,55,85)
CYAN=rgb(88,240,255); PINK=rgb(255,110,180); YELLOW=rgb(255,230,110)
GREEN=rgb(110,255,170); PURPLE=rgb(160,120,255); ORANGE=rgb(255,160,80)
HARMONIC_COLORS=[CYAN,PINK,YELLOW,GREEN,PURPLE,ORANGE,rgb(110,180,255),rgb(255,110,110),rgb(180,255,110),rgb(255,180,255),rgb(110,255,230),rgb(255,220,150)]

def lerp(a,b,t): return a+(b-a)*t

def makePresets():
    return {
        "pure":[1,0,0,0,0,0,0,0,0,0,0,0],
        "square":[1,0,0.33,0,0.2,0,0.14,0,0.11,0,0.09,0],
        "saw":[1,0.5,0.33,0.25,0.2,0.16,0.14,0.125,0.11,0.1,0.09,0.08],
        "triangle":[1,0,0.11,0,0.04,0,0.02,0,0.012,0,0.008,0],
        "violin":[1,0.85,0.7,0.6,0.45,0.35,0.5,0.3,0.25,0.2,0.18,0.15],
        "piano":[1,0.6,0.4,0.25,0.15,0.18,0.08,0.05,0.03,0.02,0.01,0.005],
        "sax":[1,0.8,0.55,0.7,0.5,0.4,0.3,0.6,0.25,0.2,0.15,0.1],
        "voice":[1,0.9,0.4,0.2,0.6,0.5,0.15,0.1,0.3,0.25,0.08,0.05],
    }

def computeComposite(t, harmonics):
    s=0
    for h in harmonics:
        if h["muted"]: continue
        s+= h["amp"]*math.sin(h["n"]*t + h["phase"])
    return s

def computeSamples(harmonics, num=512):
    return [computeComposite((i/num)*4*math.pi, harmonics) for i in range(num)]

def dft_magnitudes(samples, numBins=12):
    N=len(samples); mags=[]
    for k in range(1,numBins+1):
        re=im=0.0
        for n in range(N):
            t=(n/N)*4*math.pi
            re+= samples[n]*math.cos(k*t)
            im+= samples[n]*math.sin(k*t)
        mags.append(abs(math.sqrt(re*re+im*im)/N*2))
    mx=max(mags) if mags else 1
    if mx<0.001: mx=1
    return [m/mx for m in mags]

def ensureAudioContext(app):
    if app.audioCtx is not None: return
    try:
        AC=window.AudioContext or window.webkitAudioContext
        app.audioCtx=AC.new()
    except: app.audioCtx=None

def stopAudio(app):
    for osc in app.oscNodes:
        try: osc.stop()
        except: pass
    app.oscNodes=[]; app.gainNodes=[]; app.playing=False

def playAudio(app):
    ensureAudioContext(app)
    if app.audioCtx is None: return
    try:
        if app.audioCtx.state=="suspended": app.audioCtx.resume()
    except: pass
    if HAS_PROC_AUDIO and app.procAudio:
        try: app.procAudio.resume()
        except: pass
    stopAudio(app)
    try:
        master=app.audioCtx.createGain(); master.gain.value=0.28
        master.connect(app.audioCtx.destination)
        analyser=app.audioCtx.createAnalyser(); analyser.fftSize=256
        master.connect(analyser)
        app.analyser=analyser
        app.analyserData=window.Uint8Array.new(analyser.frequencyBinCount)
        for h in app.harmonics:
            if h["muted"] or h["amp"]<0.01: continue
            osc=app.audioCtx.createOscillator(); osc.type="sine"
            osc.frequency.value=app.fundamental*h["n"]
            g=app.audioCtx.createGain(); g.gain.value=h["amp"]*0.55
            try:
                p=app.audioCtx.createStereoPanner(); p.pan.value=math.sin(h["n"]*0.9)*0.3
                osc.connect(g); g.connect(p); p.connect(master)
            except:
                osc.connect(g); g.connect(master)
            osc.start(); app.oscNodes.append(osc); app.gainNodes.append(g)
        app.masterGain=master; app.playing=True; app.time=0
    except: app.playing=False

def updateGains(app):
    if not app.playing or not app.gainNodes: return
    idx=0
    for h in app.harmonics:
        if h["muted"] or h["amp"]<0.01: continue
        if idx < len(app.gainNodes):
            try: app.gainNodes[idx].gain.value=h["amp"]*0.55
            except: pass
            idx+=1

def onAppStart(app):
    app.width=W; app.height=H; app.stepsPerSecond=60; app.background=BG
    app.harmonics=[{"n":i+1,"amp":0,"phase":0,"color":HARMONIC_COLORS[i%12],"muted":False} for i in range(8)]
    presets=makePresets()
    for i,v in enumerate(presets["violin"]):
        if i<8: app.harmonics[i]["amp"]=v
    app.presets=presets; app.presetNames=["pure","square","saw","triangle","violin","piano","sax","voice"]
    app.selectedPreset="violin"; app.fundamental=110; app.playing=False
    app.showComponents=True; app.showCochleaWave=True
    app.draggingIdx=None; app.hoverIdx=None; app.time=0; app.cochleaRot=0
    app.audioCtx=None; app.oscNodes=[]; app.gainNodes=[]; app.masterGain=None
    app.analyser=None; app.analyserData=None
    app.procAudio=AudioEngine(quality="high",seed=90210) if HAS_PROC_AUDIO else None
    app.samples=computeSamples(app.harmonics); app.fftMags=dft_magnitudes(app.samples,12)
    app.insight="Any sound = sum of pure tones. Drag spectrum bars!"; app.insightTimer=0
    app.pyodideReady=False
    if HAS_FETCH:
        async def tryFetch():
            try: await fetch_json("https://raw.githubusercontent.com/EricEisaman/scs/main/README.md")
            except: pass
        try: aio.run(tryFetch())
        except: pass
    if HAS_PYODIDE:
        async def initPy():
            try: app.pyodideReady=True
            except: pass
        try: aio.run(initPy())
        except: pass

def setPreset(app,name):
    if name not in app.presets: return
    amps=app.presets[name]
    while len(app.harmonics)<len(amps):
        n=len(app.harmonics)+1
        app.harmonics.append({"n":n,"amp":0,"phase":0,"color":HARMONIC_COLORS[(n-1)%12],"muted":False})
    for i,h in enumerate(app.harmonics):
        h["amp"]=amps[i] if i<len(amps) else 0; h["muted"]=False
    app.selectedPreset=name
    msgs={"square":"Square: only odd! 1,1/3,1/5... Sharp edges need infinite highs.","saw":"Saw: all 1/n - buzzy bowed strings.","violin":"Violin: rich + body resonance. Same pitch as piano, different spectrum!","piano":"Piano: strong lows decaying fast. Hammers = soft highs.","sax":"Sax: reed + formant bump. Ear Fourier separates instantly.","pure":"Pure sine: one frequency, no timbre.","voice":"Voice: two formant peaks = vowels. Cochlea maps place."}
    app.insight=msgs.get(name,"Timbre = harmonic recipe. Cook your own instrument."); app.insightTimer=180
    app.samples=computeSamples(app.harmonics); app.fftMags=dft_magnitudes(app.samples,12); updateGains(app)

def onStep(app):
    if app.playing:
        app.time+=0.018; app.cochleaRot+=0.02
        if app.analyser and app.analyserData:
            try: app.analyser.getByteFrequencyData(app.analyserData)
            except: pass
    else: app.cochleaRot+=0.005
    if app.insightTimer>0: app.insightTimer-=1
    if app.draggingIdx is not None:
        app.samples=computeSamples(app.harmonics); app.fftMags=dft_magnitudes(app.samples,len(app.harmonics))

def pointInRect(px,py,rx,ry,rw,rh): return rx<=px<=rx+rw and ry<=py<=ry+rh

def onMousePress(app,mx,my):
    playBx,playBy,playBw,playBh=CTRL_X+14,CTRL_Y+14,110,36
    if pointInRect(mx,my,playBx,playBy,playBw,playBh):
        stopAudio(app) if app.playing else playAudio(app); return
    btnW,btnH,gap=80,28,8; sx,sy=CTRL_X+14,CTRL_Y+62
    for idx,name in enumerate(app.presetNames):
        bx=sx+(idx%2)*(btnW+gap); by=sy+(idx//2)*(btnH+gap)
        if pointInRect(mx,my,bx,by,btnW,btnH): setPreset(app,name); return
    addBx,addBy=CTRL_X+14,CTRL_Y+62+4*(btnH+gap)+10
    if pointInRect(mx,my,addBx,addBy,38,24) and len(app.harmonics)<12:
        n=len(app.harmonics)+1; app.harmonics.append({"n":n,"amp":0.5,"phase":0,"color":HARMONIC_COLORS[(n-1)%12],"muted":False}); return
    if pointInRect(mx,my,addBx+48,addBy,38,24) and len(app.harmonics)>1: app.harmonics.pop(); return
    togY=addBy+34
    if pointInRect(mx,my,CTRL_X+14,togY,110,22): app.showComponents=not app.showComponents; return
    if pointInRect(mx,my,CTRL_X+140,togY,110,22): app.showCochleaWave=not app.showCochleaWave; return
    sX,sY,sW=CTRL_X+14,CTRL_Y+CTRL_H-58,CTRL_W-28
    if pointInRect(mx,my,sX,sY-10,sW,30):
        t=max(0,min(1,(mx-sX)/sW)); app.fundamental=int(55+t*165)
        if app.playing: playAudio(app); return
    if pointInRect(mx,my,SPEC_X,SPEC_Y,SPEC_W,SPEC_H):
        barW=(SPEC_W-36-10)/len(app.harmonics)
        for i in range(len(app.harmonics)):
            bx=SPEC_X+18+5+i*barW
            if bx<=mx<=bx+barW*0.78:
                app.draggingIdx=i; amp=max(0,min(1,(SPEC_Y+SPEC_H-30-my)/(SPEC_H-60)))
                app.harmonics[i]["amp"]=amp; app.harmonics[i]["muted"]=False
                app.samples=computeSamples(app.harmonics); updateGains(app)
                app.insight=f"H{i+1}: changed strength. Frequencies independent!"; app.insightTimer=120; return
    if pointInRect(mx,my,COCH_X,COCH_Y,COCH_W,COCH_H):
        cx,cy=COCH_X+COCH_W*0.52,COCH_Y+COCH_H*0.52
        dist=math.hypot(mx-cx,my-cy); t=max(0,min(1,dist/180)); idx=int((1-t)*(len(app.harmonics)-1))
        idx=max(0,min(len(app.harmonics)-1,idx))
        for j,h in enumerate(app.harmonics): h["muted"]=j!=idx
        app.insight=f"Solo {idx+1}*f0={app.fundamental*(idx+1)}Hz. One cochlea spot!"; app.insightTimer=120
        playAudio(app); return

def onMouseDrag(app,mx,my):
    if app.draggingIdx is not None:
        amp=max(0,min(1,(SPEC_Y+SPEC_H-30-my)/(SPEC_H-60)))
        app.harmonics[app.draggingIdx]["amp"]=amp; app.samples=computeSamples(app.harmonics); updateGains(app)

def onMouseRelease(app,mx,my): app.draggingIdx=None
def onMouseMove(app,mx,my):
    app.hoverIdx=None
    if pointInRect(mx,my,SPEC_X,SPEC_Y,SPEC_W,SPEC_H):
        barW=(SPEC_W-36-10)/len(app.harmonics)
        for i in range(len(app.harmonics)):
            bx=SPEC_X+18+5+i*barW
            if bx<=mx<=bx+barW*0.78: app.hoverIdx=i; break

def onKeyPress(app,key):
    if key==" ": stopAudio(app) if app.playing else playAudio(app)
    elif key in "12345678": 
        idx=int(key)-1
        if idx<len(app.harmonics): app.harmonics[idx]["muted"]=not app.harmonics[idx]["muted"]; updateGains(app)
    elif key.lower()=="s": app.showComponents=not app.showComponents
    elif key.lower()=="c": app.showCochleaWave=not app.showCochleaWave
    elif key.lower()=="r": setPreset(app,"violin")
    elif key.lower()=="q": app.fundamental=max(55,app.fundamental-5); playAudio(app) if app.playing else None
    elif key.lower()=="w": app.fundamental=min(440,app.fundamental+5); playAudio(app) if app.playing else None

def drawPanel(x,y,w,h,title=""):
    drawRect(x,y,w,h,fill=PANEL_BG,border=PANEL_BORDER,borderWidth=1,roundness=10)
    if title: drawLabel(title,x+14,y+14,fill=rgb(180,190,220),size=11,bold=True,align="left-top")

def drawTimeDomain(app):
    drawPanel(TIME_X,TIME_Y,TIME_W,TIME_H,"TIME y(t)=SUM A_n*sin(2pi*n*f0*t)")
    gx,gy,gw,gh=TIME_X+14,TIME_Y+34,TIME_W-28,TIME_H-52
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    midY=gy+gh/2
    drawLine(gx,midY,gx+gw,midY,fill=rgb(50,60,90),lineWidth=1,dashes=True)
    for i in range(1,4): drawLine(gx+i*gw/4,gy,gx+i*gw/4,gy+gh,fill=rgb(35,45,70),lineWidth=0.8,dashes=True)
    if app.showComponents:
        for h in app.harmonics:
            if h["muted"] or h["amp"]<0.01: continue
            for px in range(0,int(gw)-1,2):
                t=(px/gw)*4*math.pi
                y1=midY-h["amp"]*math.sin(h["n"]*t)*gh*0.38
                y2=midY-h["amp"]*math.sin(h["n"]*(t+0.02))*gh*0.38
                drawLine(gx+px,y1,gx+px+2,y2,fill=h["color"],lineWidth=1,opacity=0.22)
    pts=[]
    for px in range(int(gw)):
        t=(px/gw)*4*math.pi; v=sum(h["amp"]*math.sin(h["n"]*t) for h in app.harmonics if not h["muted"])
        norm=max(1,sum(h["amp"] for h in app.harmonics if not h["muted"])*0.6+0.4)
        pts.append((gx+px,midY-v*gh*0.38/norm))
    for i in range(len(pts)-1): drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=CYAN,lineWidth=4,opacity=0.12)
    for i in range(len(pts)-1): drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=rgb(230,250,255),lineWidth=2)
    if app.playing:
        px=gx+(app.time%1)*gw; drawLine(px,gy,px,gy+gh,fill=YELLOW,lineWidth=1.5); drawCircle(px,midY,4,fill=YELLOW)

def drawSpectrum(app):
    drawPanel(SPEC_X,SPEC_Y,SPEC_W,SPEC_H,"SPECTRUM (ear sees this)")
    gx,gy,gw,gh=SPEC_X+18,SPEC_Y+34,SPEC_W-36,SPEC_H-52
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    barW=(gw-10)/len(app.harmonics); maxH=gh-24
    for i,h in enumerate(app.harmonics):
        bx=gx+5+i*barW; bw=barW*0.78; amp=0 if h["muted"] else h["amp"]; bh=amp*maxH
        drawRect(bx,gy+gh-14-bh-(maxH-bh),bw,maxH,fill=rgb(25,30,50),roundness=3)
        if h["muted"]: drawRect(bx,gy+gh-14-bh,bw,bh,fill=rgb(50,50,60),roundness=3,opacity=0.5)
        else:
            if app.hoverIdx==i: drawRect(bx-2,gy+gh-14-bh-2,bw+4,bh+4,fill=h["color"],roundness=4,opacity=0.25)
            drawRect(bx,gy+gh-14-bh,bw,bh,fill=h["color"],roundness=3)
        drawLabel(f"{h['n']}*f0",bx+bw/2,gy+gh-2,fill=rgb(150,170,200),size=8,align="center-bottom")
        if app.hoverIdx==i: drawLabel(f"{amp:.2f}",bx+bw/2,gy+gh-14-bh-6,fill=rgb(240,250,255),size=9,bold=True,align="center-bottom")
    if app.fftMags:
        for i,m in enumerate(app.fftMags):
            bx=gx+5+i*barW+barW*0.39; by=gy+gh-14-m*maxH; drawCircle(bx,by,2.5,fill=YELLOW,border=rgb(0,0,0),borderWidth=1)

def drawCochlea(app):
    drawPanel(COCH_X,COCH_Y,COCH_W,COCH_H,"COCHLEA - LIVE FOURIER (tonotopic)")
    gx,gy,gw,gh=COCH_X+14,COCH_Y+34,COCH_W-28,COCH_H-52
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=10)
    cx,cy=gx+gw*0.52,gy+gh*0.52; maxTheta=2.5*2*math.pi; pts=[]
    for i in range(300):
        t=i/299*maxTheta; r=170*math.exp(-0.28*t); ang=t+app.cochleaRot*0.1
        pts.append((cx+r*math.cos(ang)*1.1,cy+r*math.sin(ang)*0.92,r,t))
    for i in range(len(pts)-1):
        norm=pts[i][3]/maxTheta; col=rgb(int(lerp(255,80,norm)),int(lerp(160,220,norm)),int(lerp(60,255,norm)))
        drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=col,lineWidth=lerp(10,3,norm),opacity=0.85)
    maxN=len(app.harmonics)
    for h in app.harmonics:
        if h["muted"] or h["amp"]<0.02: continue
        frac=max(0.05,min(0.95,1-math.log(h["n"])/math.log(maxN*3)))*0.85+0.05
        x,y,r,t=pts[int(frac*(len(pts)-1))]; rad=6+h["amp"]*14*(1+0.6*math.sin(app.time*6+h["n"]*0.8)*h["amp"] if app.playing else 1)
        drawCircle(x,y,rad*1.8,fill=h["color"],opacity=0.22); drawCircle(x,y,rad,fill=h["color"],border=rgb(255,255,255),borderWidth=1.2)

def drawControls(app):
    drawPanel(CTRL_X,CTRL_Y,CTRL_W,CTRL_H,"TIMBRE LAB")
    bx,by,bw,bh=CTRL_X+14,CTRL_Y+14,110,36
    if app.playing: drawRect(bx,by,bw,bh,fill=rgb(255,90,90),border=rgb(255,255,255),borderWidth=1.5,roundness=18); drawLabel("STOP",bx+bw/2,by+bh/2,fill=rgb(255,255,255),size=13,bold=True,align="center")
    else: drawRect(bx,by,bw,bh,fill=rgb(90,255,160),border=rgb(255,255,255),borderWidth=1.5,roundness=18); drawLabel("PLAY",bx+bw/2,by+bh/2,fill=rgb(0,0,0),size=13,bold=True,align="center")
    drawLabel(f"F0 {app.fundamental}Hz Q/W",CTRL_X+140,CTRL_Y+24,fill=rgb(200,220,255),size=11,bold=True,align="left-center")
    btnW,btnH,gap=80,28,8; sx,sy=CTRL_X+14,CTRL_Y+62
    for idx,name in enumerate(app.presetNames):
        bx=sx+(idx%2)*(btnW+gap); by=sy+(idx//2)*(btnH+gap); sel=name==app.selectedPreset
        if sel: drawRect(bx,by,btnW,btnH,fill=HARMONIC_COLORS[idx%12],border=rgb(255,255,255),borderWidth=1.5,roundness=8); drawLabel(name.upper(),bx+btnW/2,by+btnH/2,fill=rgb(0,0,0),size=10,bold=True,align="center")
        else: drawRect(bx,by,btnW,btnH,fill=rgb(35,42,68),border=PANEL_BORDER,borderWidth=1,roundness=8); drawLabel(name,bx+btnW/2,by+btnH/2,fill=rgb(180,200,230),size=10,align="center")
    addBx,addBy=CTRL_X+14,CTRL_Y+62+4*(btnH+gap)+10
    drawRect(addBx,addBy,38,24,fill=rgb(45,55,85),border=PANEL_BORDER,borderWidth=1,roundness=6); drawLabel("+ H",addBx+19,addBy+12,fill=rgb(220,230,255),size=11,bold=True,align="center")
    drawRect(addBx+48,addBy,38,24,fill=rgb(45,55,85),border=PANEL_BORDER,borderWidth=1,roundness=6); drawLabel("- H",addBx+67,addBy+12,fill=rgb(220,230,255),size=11,bold=True,align="center")
    drawLabel(f"{len(app.harmonics)} harms",addBx+115,addBy+12,fill=rgb(150,170,200),size=10,align="left-center")
    togY=addBy+34
    drawRect(CTRL_X+14,togY,110,22,fill=CYAN if app.showComponents else rgb(60,70,90),border=PANEL_BORDER,borderWidth=1,roundness=6); drawLabel("Show Comp",CTRL_X+69,togY+11,fill=rgb(0,0,0) if app.showComponents else rgb(180,190,210),size=9,bold=app.showComponents,align="center")
    drawRect(CTRL_X+140,togY,110,22,fill=PINK if app.showCochleaWave else rgb(60,70,90),border=PANEL_BORDER,borderWidth=1,roundness=6); drawLabel("Wave",CTRL_X+195,togY+11,fill=rgb(0,0,0) if app.showCochleaWave else rgb(180,190,210),size=9,bold=app.showCochleaWave,align="center")
    sX,sY,sW=CTRL_X+14,CTRL_Y+CTRL_H-58,CTRL_W-28
    drawRect(sX,sY,sW,10,fill=rgb(30,35,55),border=PANEL_BORDER,borderWidth=1,roundness=5)
    t=(app.fundamental-55)/165; drawRect(sX,sY,t*sW,10,fill=ORANGE,roundness=5); drawCircle(sX+t*sW,sY+5,9,fill=rgb(255,255,255),border=ORANGE,borderWidth=2)

def drawHeader(app):
    drawRect(0,0,W,HEADER_H,fill=rgb(18,22,38))
    drawLabel("YOUR EARDRUM IS A FOURIER TRANSFORM MACHINE",W*0.5,14,fill=rgb(240,250,255),size=16,bold=True,align="center-top")
    drawLabel("Any function = sum of sines. Independent frequencies -> spectrum. Cochlea separates them realtime.",W*0.5,32,fill=rgb(160,180,210),size=10.5,align="center-top")
    drawRect(12,HEADER_H+4,W-24,22,fill=rgb(35,60,85),border=CYAN,borderWidth=1,roundness=7,opacity=0.9)
    drawLabel(app.insight,W*0.5,HEADER_H+15,fill=rgb(200,240,255),size=11,bold=True,align="center")

def redrawAll(app):
    drawRect(0,0,W,H,fill=BG); drawHeader(app); drawTimeDomain(app); drawSpectrum(app); drawCochlea(app); drawControls(app)