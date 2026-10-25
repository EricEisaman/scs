
"""
Fourier Ear Lab - SCS App v4 - slider fixed, fetch fixed
"""
from scs import *
from browser import window, aio
import math

try:
    from extensions.proc_audio import AudioEngine
    HAS_PROC_AUDIO=True
except:
    HAS_PROC_AUDIO=False
    AudioEngine=None
try:
    from extensions.fetch import fetch_json, fetch_text
    HAS_FETCH=True
except:
    HAS_FETCH=False
    fetch_text=None
    fetch_json=None

W,H=1050,700
HEADER_H=70
TIME_X,TIME_Y,TIME_W,TIME_H=16,82,620,252
SPEC_X,SPEC_Y,SPEC_W,SPEC_H=652,82,382,252
COCH_X,COCH_Y,COCH_W,COCH_H=16,350,620,336
CTRL_X,CTRL_Y,CTRL_W,CTRL_H=652,350,382,336

BG=rgb(10,14,26)
PANEL_BG=rgb(18,22,38)
PANEL_BORDER=rgb(45,55,85)
CYAN=rgb(88,240,255); PINK=rgb(255,110,180); YELLOW=rgb(255,230,110)
GREEN=rgb(110,255,170); PURPLE=rgb(160,120,255); ORANGE=rgb(255,160,80)
HARMONIC_COLORS=[CYAN,PINK,YELLOW,GREEN,PURPLE,ORANGE,rgb(110,180,255),rgb(255,110,110),rgb(180,255,110),rgb(255,180,255),rgb(110,255,230),rgb(255,220,150)]

def lerp(a,b,t): return a+(b-a)*t

def preset_amp_phase(preset,n):
    if preset=="pure": return (1.0 if n==1 else 0.0,0)
    if preset=="square": return (1.0/n if n%2==1 else 0.0,0)
    if preset=="saw": return (1.0/n,0)
    if preset=="triangle":
        if n%2==0: return (0.0,0)
        amp=1.0/(n*n); ph=0 if ((n-1)//2)%2==0 else math.pi
        return (amp,ph)
    table={"violin":[1,0.85,0.7,0.6,0.45,0.35,0.5,0.3,0.25,0.2,0.18,0.15],"piano":[1,0.6,0.4,0.25,0.15,0.18,0.08,0.05,0.03,0.02,0.01,0.005],"sax":[1,0.8,0.55,0.7,0.5,0.4,0.3,0.6,0.25,0.2,0.15,0.1],"voice":[1,0.9,0.4,0.2,0.6,0.5,0.15,0.1,0.3,0.25,0.08,0.05]}
    arr=table.get(preset,[])
    if n<=len(arr): return (arr[n-1],0)
    return (0.08/n,0)

def computeComposite(t, harmonics):
    s=0.0
    for h in harmonics:
        if h["muted"]: continue
        s+=h["amp"]*math.sin(h["n"]*t + h["phase"])
    return s

def computeSamples(harmonics,num=1024):
    return [computeComposite((i/num)*4*math.pi, harmonics) for i in range(num)]

def dft_magnitudes(samples,numBins):
    N=len(samples); mags=[]
    for k in range(1,numBins+1):
        re=im=0.0
        for n in range(N):
            t=(n/N)*4*math.pi
            re+=samples[n]*math.cos(k*t)
            im+=samples[n]*math.sin(k*t)
        mags.append(math.hypot(re,im)/N*2)
    mx=max(mags) if mags else 1
    if mx<0.001: mx=1
    return [m/mx for m in mags]

def ensureAudioContext(app):
    if app.audioCtx: return
    try:
        AC=window.AudioContext or window.webkitAudioContext
        app.audioCtx=AC.new()
    except: app.audioCtx=None

def stopAudio(app):
    for o in app.oscNodes:
        try: o.stop()
        except: pass
    app.oscNodes=[]; app.gainNodes=[]; app.playing=False

def rebuildAudio(app):
    if not app.playing: return
    stopAudio(app)
    playAudio(app)

def playAudio(app):
    ensureAudioContext(app)
    if not app.audioCtx: return
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
            if h["muted"] or h["amp"]<0.005: continue
            osc=app.audioCtx.createOscillator(); osc.type="sine"
            osc.frequency.value=app.fundamental*h["n"]
            g=app.audioCtx.createGain(); g.gain.value=h["amp"]*0.55
            try:
                p=app.audioCtx.createStereoPanner(); p.pan.value=math.sin(h["n"]*0.9)*0.25
                osc.connect(g); g.connect(p); p.connect(master)
            except:
                osc.connect(g); g.connect(master)
            osc.start()
            app.oscNodes.append(osc); app.gainNodes.append(g)
        app.masterGain=master; app.playing=True; app.time=0
    except: app.playing=False

def updateGains(app):
    if not app.playing or not app.gainNodes: return
    active=[h for h in app.harmonics if not h["muted"] and h["amp"]>=0.005]
    if len(active)!=len(app.gainNodes):
        rebuildAudio(app); return
    idx=0
    for h in app.harmonics:
        if h["muted"] or h["amp"]<0.005: continue
        if idx < len(app.gainNodes):
            try: app.gainNodes[idx].gain.value=h["amp"]*0.55
            except: pass
            idx+=1

def onAppStart(app):
    app.width=W; app.height=H; app.stepsPerSecond=60; app.background=BG
    app.harmonics=[{"n":i+1,"amp":0,"phase":0,"color":HARMONIC_COLORS[i%12],"muted":False} for i in range(8)]
    for h in app.harmonics:
        amp,ph=preset_amp_phase("violin",h["n"]); h["amp"]=amp; h["phase"]=ph
    app.presetNames=["pure","square","saw","triangle","violin","piano","sax","voice"]
    app.selectedPreset="violin"; app.fundamental=110; app.playing=False
    app.showComponents=True; app.showCochleaWave=True
    app.draggingIdx=None; app.draggingSlider=False; app.hoverIdx=None; app.time=0; app.cochleaRot=0
    app.audioCtx=None; app.oscNodes=[]; app.gainNodes=[]; app.masterGain=None; app.analyser=None
    app.procAudio=AudioEngine(quality="high",seed=90210) if HAS_PROC_AUDIO else None
    app.samples=computeSamples(app.harmonics); app.fftMags=dft_magnitudes(app.samples,len(app.harmonics))
    app.insight="Drag spectrum bars -> waveform + cochlea update. Frequencies independent!"; app.insightTimer=0
    # FIXED: use fetch_text for markdown, not fetch_json
    if HAS_FETCH and fetch_text:
        async def tryFetch():
            try:
                txt = await fetch_text("https://raw.githubusercontent.com/EricEisaman/scs/main/README.md")
                app.fetchedLen = len(txt)
            except Exception as e:
                app.fetchedLen = 0
        try: aio.run(tryFetch())
        except: pass

def setPreset(app,name):
    if name not in app.presetNames: return
    for h in app.harmonics:
        amp,ph=preset_amp_phase(name,h["n"]); h["amp"]=amp; h["phase"]=ph; h["muted"]=False
    app.selectedPreset=name
    msgs={"square":"Square: ONLY odd 1/n. Sharp edges need infinite highs!","triangle":"Triangle: odd 1/n^2 alternating. Soft pointy.","saw":"Saw: all 1/n - bright buzzy.","pure":"Pure sine: 1 freq, no timbre.","violin":"Violin: rich + bump at 7th. Same pitch, different spectrum!","piano":"Piano: strong lows, fast decay.","sax":"Sax: reed + formant at 8th.","voice":"Voice: formants = vowels."}
    app.insight=msgs.get(name,"Timbre = recipe."); app.insightTimer=200
    app.samples=computeSamples(app.harmonics); app.fftMags=dft_magnitudes(app.samples,len(app.harmonics))
    if app.playing: rebuildAudio(app)

def onStep(app):
    if app.playing:
        app.time+=0.02; app.cochleaRot+=0.02
        if app.analyser and app.analyserData:
            try: app.analyser.getByteFrequencyData(app.analyserData)
            except: pass
    else: app.cochleaRot+=0.004
    if app.insightTimer>0: app.insightTimer-=1

def pointInRect(px,py,rx,ry,rw,rh): return rx<=px<=rx+rw and ry<=py<=ry+rh

def updateFundamentalFromX(app,mx):
    sX=CTRL_X+14; sW=CTRL_W-28
    t=max(0,min(1,(mx-sX)/sW)); app.fundamental=int(55+t*165)
    if app.playing: rebuildAudio(app)

def onMousePress(app,mx,my):
    playBx,playBy,playBw,playBh=CTRL_X+14,CTRL_Y+32,110,36
    if pointInRect(mx,my,playBx,playBy,playBw,playBh):
        if app.playing: stopAudio(app)
        else: playAudio(app)
        return
    btnW,btnH,gap=80,28,8; sx,sy=CTRL_X+14,CTRL_Y+78
    for idx,name in enumerate(app.presetNames):
        bx=sx+(idx%2)*(btnW+gap); by=sy+(idx//2)*(btnH+gap)
        if pointInRect(mx,my,bx,by,btnW,btnH): setPreset(app,name); return
    addBx,addBy=CTRL_X+14,CTRL_Y+78+4*(btnH+gap)+14
    if pointInRect(mx,my,addBx,addBy,38,24):
        if len(app.harmonics)<12:
            n=len(app.harmonics)+1; amp,ph=preset_amp_phase(app.selectedPreset,n)
            if amp==0: amp=0.4/n
            app.harmonics.append({"n":n,"amp":amp,"phase":ph,"color":HARMONIC_COLORS[(n-1)%12],"muted":False})
            app.samples=computeSamples(app.harmonics); app.fftMags=dft_magnitudes(app.samples,len(app.harmonics))
            if app.playing: rebuildAudio(app)
        return
    if pointInRect(mx,my,addBx+48,addBy,38,24):
        if len(app.harmonics)>1:
            app.harmonics.pop()
            app.samples=computeSamples(app.harmonics); app.fftMags=dft_magnitudes(app.samples,len(app.harmonics))
            if app.playing: rebuildAudio(app)
        return
    togY=addBy+34
    if pointInRect(mx,my,CTRL_X+14,togY,110,22): app.showComponents=not app.showComponents; return
    if pointInRect(mx,my,CTRL_X+140,togY,110,22): app.showCochleaWave=not app.showCochleaWave; return
    # slider - moved down to y=308
    sX,sY,sW=CTRL_X+14,CTRL_Y+308,CTRL_W-28
    if pointInRect(mx,my,sX,sY-12,sW,32):
        app.draggingSlider=True
        updateFundamentalFromX(app,mx)
        return
    if pointInRect(mx,my,SPEC_X,SPEC_Y,SPEC_W,SPEC_H):
        n=len(app.harmonics); maxBarW=42; barW=min(maxBarW,(SPEC_W-40)/n); totalW=barW*n; offsetX=SPEC_X+18+(SPEC_W-36-totalW)/2
        for i in range(n):
            bx=offsetX+i*barW
            if bx<=mx<=bx+barW*0.85:
                app.draggingIdx=i
                rel=(SPEC_Y+SPEC_H-30-my)/(SPEC_H-60)
                app.harmonics[i]["amp"]=max(0,min(1,rel)); app.harmonics[i]["muted"]=False
                app.samples=computeSamples(app.harmonics); app.fftMags=dft_magnitudes(app.samples,len(app.harmonics))
                updateGains(app)
                if app.playing and len([h for h in app.harmonics if not h["muted"] and h["amp"]>=0.005])!=len(app.gainNodes):
                    rebuildAudio(app)
                app.insight=f"H{i+1} changed -> others stay. Independent!"; app.insightTimer=120
                return
    if pointInRect(mx,my,COCH_X,COCH_Y,COCH_W,COCH_H):
        cx,cy=COCH_X+COCH_W*0.52,COCH_Y+COCH_H*0.52
        dist=math.hypot(mx-cx,my-cy); t=max(0,min(1,dist/185)); idx=int((1-t)*(len(app.harmonics)-1))
        idx=max(0,min(len(app.harmonics)-1,idx))
        for j,h in enumerate(app.harmonics): h["muted"]=j!=idx
        app.insight=f"Solo {idx+1}*f0={app.fundamental*(idx+1)}Hz - one spot!"; app.insightTimer=120
        rebuildAudio(app); return

def onMouseDrag(app,mx,my):
    if app.draggingSlider:
        updateFundamentalFromX(app,mx)
        return
    if app.draggingIdx is not None:
        rel=(SPEC_Y+SPEC_H-30-my)/(SPEC_H-60)
        app.harmonics[app.draggingIdx]["amp"]=max(0,min(1,rel))
        app.samples=computeSamples(app.harmonics); updateGains(app)
        if app.playing:
            if len([h for h in app.harmonics if not h["muted"] and h["amp"]>=0.005])!=len(app.gainNodes):
                rebuildAudio(app)

def onMouseRelease(app,mx,my):
    app.draggingIdx=None
    app.draggingSlider=False

def onMouseMove(app,mx,my):
    app.hoverIdx=None
    if pointInRect(mx,my,SPEC_X,SPEC_Y,SPEC_W,SPEC_H):
        n=len(app.harmonics); maxBarW=42; barW=min(maxBarW,(SPEC_W-40)/n); totalW=barW*n; offsetX=SPEC_X+18+(SPEC_W-36-totalW)/2
        for i in range(n):
            bx=offsetX+i*barW
            if bx<=mx<=bx+barW*0.85: app.hoverIdx=i; break

def onKeyPress(app,key):
    if key==" ":
        if app.playing: stopAudio(app)
        else: playAudio(app)
    elif key in "123456789":
        idx=int(key)-1
        if idx<len(app.harmonics):
            app.harmonics[idx]["muted"]=not app.harmonics[idx]["muted"]
            if app.playing: rebuildAudio(app)
    elif key.lower()=="s": app.showComponents=not app.showComponents
    elif key.lower()=="c": app.showCochleaWave=not app.showCochleaWave
    elif key.lower()=="r": setPreset(app,"violin")
    elif key.lower()=="q": app.fundamental=max(55,app.fundamental-5); rebuildAudio(app) if app.playing else None
    elif key.lower()=="w": app.fundamental=min(440,app.fundamental+5); rebuildAudio(app) if app.playing else None

def drawPanel(x,y,w,h,title=""):
    drawRect(x,y,w,h,fill=PANEL_BG,border=PANEL_BORDER,borderWidth=1,roundness=10)
    if title:
        drawRect(x+8,y+6,w-16,16,fill=rgb(28,32,52),roundness=5)
        drawLabel(title,x+14,y+14,fill=rgb(180,190,220),size=11,bold=True,align="left-top")

def drawTimeDomain(app):
    drawPanel(TIME_X,TIME_Y,TIME_W,TIME_H,"TIME y(t)=SUM A_n*sin(2pi*n*f0*t + phase)")
    gx,gy,gw,gh=TIME_X+14,TIME_Y+34,TIME_W-28,TIME_H-52
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    midY=gy+gh/2
    drawLine(gx,midY,gx+gw,midY,fill=rgb(50,60,90),lineWidth=1,dashes=True)
    for i in range(1,4): drawLine(gx+i*gw/4,gy,gx+i*gw/4,gy+gh,fill=rgb(35,45,70),lineWidth=0.8,dashes=True)
    samples=app.samples; maxAbs=max(1.0, max(abs(v) for v in samples)) if samples else 1.0
    scale=(gh*0.38)/maxAbs
    if app.showComponents:
        for h in app.harmonics:
            if h["muted"] or h["amp"]<0.005: continue
            for px in range(0,int(gw)-1,3):
                t=(px/gw)*4*math.pi
                y1=midY - h["amp"]*math.sin(h["n"]*t + h["phase"])*scale
                y2=midY - h["amp"]*math.sin(h["n"]*(t+0.04) + h["phase"])*scale
                drawLine(gx+px,y1,gx+px+3,y2,fill=h["color"],lineWidth=1,opacity=0.16)
    pts=[]
    for px in range(int(gw)):
        idx=int(px/gw*len(samples))%len(samples)
        pts.append((gx+px, midY - samples[idx]*scale))
    for i in range(len(pts)-1): drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=CYAN,lineWidth=4,opacity=0.12)
    for i in range(len(pts)-1): drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=rgb(230,250,255),lineWidth=2)
    if app.playing:
        px=gx+(app.time%1)*gw; drawLine(px,gy,px,gy+gh,fill=YELLOW,lineWidth=1.5); drawCircle(px,midY,4,fill=YELLOW)
    drawLabel(f"f0={app.fundamental}Hz max={maxAbs:.2f}",gx+gw-8,gy+gh-8,fill=rgb(160,180,210),size=10,align="right-bottom")

def drawSpectrum(app):
    drawPanel(SPEC_X,SPEC_Y,SPEC_W,SPEC_H,"SPECTRUM (ear sees this) - drag bars")
    gx,gy,gw,gh=SPEC_X+18,SPEC_Y+34,SPEC_W-36,SPEC_H-52
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    n=len(app.harmonics); maxBarW=42; barW=min(maxBarW,(gw-10)/n); totalW=barW*n
    offsetX=gx+5+(gw-10-totalW)/2; maxH=gh-26
    for i,h in enumerate(app.harmonics):
        bx=offsetX+i*barW; bw=barW*0.82; amp=0 if h["muted"] else h["amp"]; bh=amp*maxH
        drawRect(bx,gy+gh-14-maxH,bw,maxH,fill=rgb(25,30,50),roundness=3)
        if h["muted"]: drawRect(bx,gy+gh-14-bh,bw,bh,fill=rgb(50,50,60),roundness=3,opacity=0.5)
        else:
            if app.hoverIdx==i: drawRect(bx-2,gy+gh-14-bh-2,bw+4,bh+4,fill=h["color"],roundness=4,opacity=0.25)
            drawRect(bx,gy+gh-14-bh,bw,bh,fill=h["color"],roundness=3)
        drawLabel(f"{h['n']}*f0",bx+bw/2,gy+gh-2,fill=rgb(150,170,200),size=8,align="center-bottom")
        if app.hoverIdx==i: drawLabel(f"{amp:.2f}",bx+bw/2,gy+gh-16-bh,fill=rgb(240,250,255),size=9,bold=True,align="center-bottom")
    if app.fftMags:
        for i,m in enumerate(app.fftMags[:n]):
            bx=offsetX+i*barW+barW*0.41; by=gy+gh-14-m*maxH
            drawCircle(bx,by,3,fill=YELLOW,border=rgb(0,0,0),borderWidth=1)

def drawCochlea(app):
    drawPanel(COCH_X,COCH_Y,COCH_W,COCH_H,"COCHLEA - LIVE FOURIER (tonotopic map)")
    gx,gy,gw,gh=COCH_X+14,COCH_Y+34,COCH_W-28,COCH_H-52
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=10)
    cx,cy=gx+gw*0.52,gy+gh*0.52; maxTheta=2.5*2*math.pi; pts=[]
    for i in range(320):
        t=i/319*maxTheta; r=175*math.exp(-0.29*t); ang=t+app.cochleaRot*0.08
        pts.append((cx+r*math.cos(ang)*1.08,cy+r*math.sin(ang)*0.9,r,t))
    for i in range(len(pts)-1):
        norm=pts[i][3]/maxTheta; col=rgb(int(lerp(255,80,norm)),int(lerp(160,220,norm)),int(lerp(60,255,norm)))
        drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=col,lineWidth=lerp(11,3.5,norm),opacity=0.88)
    for i in range(0,len(pts)-1,4):
        drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=rgb(255,255,255),lineWidth=1,opacity=0.08)
    markers=[(0.02,"20kHz BASE"),(0.38,"1kHz"),(0.68,"250Hz"),(0.90,"20Hz APEX")]
    for frac,lbl in markers:
        idx=int(frac*(len(pts)-1)); x,y,r,t=pts[idx]
        drawCircle(x,y,5,fill=rgb(255,255,255),border=PANEL_BORDER,borderWidth=1)
        ang=t+app.cochleaRot*0.08; ox=math.cos(ang)*22; oy=math.sin(ang)*22
        lx=x+ox; ly=y+oy
        drawRect(lx-2,ly-12, len(lbl)*5.5+6,14, fill=rgb(18,22,38), border=rgb(80,90,120), borderWidth=0.8, roundness=4, opacity=0.9)
        drawLabel(lbl,lx+2,ly-2,fill=rgb(200,210,230),size=8,align="left-top")
        drawLine(x,y,lx,ly,fill=rgb(120,130,160),lineWidth=0.8,opacity=0.6)
    maxN=len(app.harmonics)
    for h in app.harmonics:
        if h["muted"] or h["amp"]<0.008: continue
        if maxN>1: frac=0.92 - (h["n"]-1)/(maxN-1)*0.84
        else: frac=0.92
        frac=max(0.05,min(0.95,frac))
        x,y,r,t=pts[int(frac*(len(pts)-1))]
        pulse=1+0.5*math.sin(app.time*5+h["n"])*h["amp"] if app.playing else 1
        rad=6+h["amp"]*14*pulse
        drawCircle(x,y,rad*1.6,fill=h["color"],opacity=0.20)
        drawCircle(x,y,rad,fill=h["color"],border=rgb(255,255,255),borderWidth=1.1)
    drawLabel("Base=high -> Apex=low. 3500 hair cells. Click map to solo.",gx+8,gy+gh-8,fill=rgb(130,150,180),size=9,align="left-bottom")

def drawControls(app):
    drawPanel(CTRL_X,CTRL_Y,CTRL_W,CTRL_H,"TIMBRE LAB - click preset")
    bx,by,bw,bh=CTRL_X+14,CTRL_Y+32,110,36
    if app.playing: drawRect(bx,by,bw,bh,fill=rgb(255,90,90),border=rgb(255,255,255),borderWidth=1.5,roundness=18); drawLabel("STOP",bx+bw/2,by+bh/2,fill=rgb(255,255,255),size=13,bold=True,align="center")
    else: drawRect(bx,by,bw,bh,fill=rgb(90,255,160),border=rgb(255,255,255),borderWidth=1.5,roundness=18); drawLabel("PLAY",bx+bw/2,by+bh/2,fill=rgb(0,0,0),size=13,bold=True,align="center")
    drawLabel(f"F0 {app.fundamental}Hz Q/W",CTRL_X+140,CTRL_Y+42,fill=rgb(200,220,255),size=11,bold=True,align="left-center")
    btnW,btnH,gap=80,28,8; sx,sy=CTRL_X+14,CTRL_Y+78
    for idx,name in enumerate(app.presetNames):
        bx=sx+(idx%2)*(btnW+gap); by=sy+(idx//2)*(btnH+gap); sel=name==app.selectedPreset
        if sel: drawRect(bx,by,btnW,btnH,fill=HARMONIC_COLORS[idx%12],border=rgb(255,255,255),borderWidth=1.5,roundness=8); drawLabel(name.upper(),bx+btnW/2,by+btnH/2,fill=rgb(0,0,0),size=10,bold=True,align="center")
        else: drawRect(bx,by,btnW,btnH,fill=rgb(35,42,68),border=PANEL_BORDER,borderWidth=1,roundness=8); drawLabel(name,bx+btnW/2,by+btnH/2,fill=rgb(180,200,230),size=10,align="center")
    addBx,addBy=CTRL_X+14,CTRL_Y+78+4*(btnH+gap)+14
    drawRect(addBx,addBy,38,24,fill=rgb(45,55,85),border=PANEL_BORDER,borderWidth=1,roundness=6); drawLabel("+ H",addBx+19,addBy+12,fill=rgb(220,230,255),size=11,bold=True,align="center")
    drawRect(addBx+48,addBy,38,24,fill=rgb(45,55,85),border=PANEL_BORDER,borderWidth=1,roundness=6); drawLabel("- H",addBx+67,addBy+12,fill=rgb(220,230,255),size=11,bold=True,align="center")
    drawLabel(f"{len(app.harmonics)} harms",addBx+115,addBy+12,fill=rgb(150,170,200),size=10,align="left-center")
    togY=addBy+34
    drawRect(CTRL_X+14,togY,110,22,fill=CYAN if app.showComponents else rgb(60,70,90),border=PANEL_BORDER,borderWidth=1,roundness=6); drawLabel("Show Comp",CTRL_X+69,togY+11,fill=rgb(0,0,0) if app.showComponents else rgb(180,190,210),size=9,bold=app.showComponents,align="center")
    drawRect(CTRL_X+140,togY,110,22,fill=PINK if app.showCochleaWave else rgb(60,70,90),border=PANEL_BORDER,borderWidth=1,roundness=6); drawLabel("Wave",CTRL_X+195,togY+11,fill=rgb(0,0,0) if app.showCochleaWave else rgb(180,190,210),size=9,bold=app.showCochleaWave,align="center")
    # slider moved down to 308
    sX,sY,sW=CTRL_X+14,CTRL_Y+308,CTRL_W-28
    drawRect(sX,sY,sW,10,fill=rgb(30,35,55),border=PANEL_BORDER,borderWidth=1,roundness=5)
    t=(app.fundamental-55)/165; drawRect(sX,sY,t*sW,10,fill=ORANGE,roundness=5); drawCircle(sX+t*sW,sY+5,10,fill=rgb(255,255,255),border=ORANGE,borderWidth=2)
    drawLabel("55Hz",sX,sY+14,fill=rgb(130,140,170),size=8,align="left-top")
    drawLabel("220Hz",sX+sW,sY+14,fill=rgb(130,140,170),size=8,align="right-top")

def drawHeader(app):
    drawRect(0,0,W,HEADER_H,fill=rgb(18,22,38))
    drawLabel("YOUR EARDRUM IS A FOURIER TRANSFORM MACHINE",W*0.5,12,fill=rgb(240,250,255),size=16,bold=True,align="center-top")
    drawLabel("Any function = sum of sines. Independent frequencies -> spectrum. Cochlea separates them realtime.",W*0.5,30,fill=rgb(160,180,210),size=10.5,align="center-top")
    drawRect(12,50,W-24,16,fill=rgb(35,60,85),border=CYAN,borderWidth=1,roundness=6,opacity=0.9)
    drawLabel(app.insight,W*0.5,58,fill=rgb(200,240,255),size=10,bold=True,align="center")

def redrawAll(app):
    drawRect(0,0,W,H,fill=BG); drawHeader(app); drawTimeDomain(app); drawSpectrum(app); drawCochlea(app); drawControls(app)
