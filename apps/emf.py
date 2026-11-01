
"""
EMF Lab v21 - BLANK PAGE FIX - safe SCS primitives only
- No drawOval/drawArc unless fallback
- No opacity on drawLine (some builds choke)
- No dashes param if unsafe -> use fallback
- No bottom log footer
- No top-right SIGMA box
- No orange duplicate GLOBE VIEW
- Purple globe button toggles BACK TO LAB / GLOBE VIEW
- Panels original: 82/350
"""
from scs import *
from browser import window, aio
import math, random, traceback, json

try:
    from extensions.proc_audio import AudioEngine
    HAS_PROC_AUDIO=True
except:
    HAS_PROC_AUDIO=False
    AudioEngine=None
try:
    from extensions.fetch import fetch_json
    HAS_FETCH=True
except:
    HAS_FETCH=False
    fetch_json=None
try:
    from extensions.pyodide import run_python
    HAS_PYODIDE=True
except:
    HAS_PYODIDE=False
    run_python=None

W,H=1050,700
HEADER_H=70
DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H=16,82,500,252
DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H=534,82,500,252
MAG_X,MAG_Y,MAG_W,MAG_H=16,350,500,336
IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H=534,350,500,336

BG=rgb(10,14,26)
PANEL_BG=rgb(18,22,38)
TXT=rgb(236,240,255)
DIM=rgb(150,160,188)
CYAN=rgb(88,240,255)
YELLOW=rgb(255,230,110)
ORANGE=rgb(255,160,80)
RED=rgb(255,90,90)
BLUE=rgb(110,180,255)
GREEN=rgb(110,255,170)
PURPLE=rgb(160,120,255)
PINK=rgb(255,110,180)
BORDER=rgb(58,64,94)
ACC=rgb(99,102,241)
ACC_H=rgb(129,133,255)

# ---- SAFE DRAW WRAPPERS - prevent blank page ----
def sRect(x,y,w,h,fill=None,border=None,borderWidth=1,roundness=0):
    try:
        if roundness: drawRect(x,y,w,h,fill=fill,border=border,borderWidth=borderWidth,roundness=roundness)
        else: drawRect(x,y,w,h,fill=fill,border=border,borderWidth=borderWidth)
    except Exception as e:
        try: drawRect(x,y,w,h,fill=fill or BG)
        except: pass
def sCircle(x,y,r,fill=None,border=None,borderWidth=1):
    try: drawCircle(x,y,r,fill=fill,border=border,borderWidth=borderWidth)
    except:
        try: drawCircle(x,y,r,fill=fill)
        except: pass
def sLine(x1,y1,x2,y2,fill=None,lineWidth=1):
    try: drawLine(x1,y1,x2,y2,fill=fill,lineWidth=lineWidth)
    except:
        try: drawLine(x1,y1,x2,y2,fill=fill)
        except: pass
def sLabel(txt,x,y,fill=None,size=12,bold=False,align="left"):
    try: drawLabel(txt,x,y,fill=fill,size=size,bold=bold,align=align)
    except:
        try: drawLabel(txt,x,y,fill=fill,size=size,bold=bold)
        except: pass

# Fallback oval as circle
def sOval(cx,cy,w,h,fill=None,border=None,borderWidth=1):
    try:
        # try real drawOval if exists
        drawOval(cx,cy,w,h,fill=fill,border=border,borderWidth=borderWidth)
    except:
        try: drawOval(cx,cy,w,h,fill=fill,border=border,borderWidth=borderWidth)
        except: sCircle(cx,cy,min(w,h)/2,fill=fill,border=border,borderWidth=borderWidth)

N_POLE_HISTORY = [(1800,70.2,-96.5),(1850,70.8,-96.0),(1900,71.0,-97.0),(1920,72.5,-98.0),(1940,74.0,-100.0),(1960,75.5,-100.5),(1970,76.5,-101.0),(1980,77.8,-102.5),(1990,79.0,-104.0),(2000,81.3,-110.5),(2005,83.2,-118.0),(2010,85.0,-132.8),(2015,86.3,160.0),(2020,86.4,164.0),(2025,86.1,150.0)]
MOMENT_HISTORY = [(1800,8.55),(1850,8.40),(1900,8.25),(1950,8.00),(1980,7.90),(2000,7.80),(2010,7.75),(2020,7.71),(2025,7.68)]

def lerp(a,b,t): return a+(b-a)*t
def clamp(v,lo,hi): return lo if v<lo else hi if v>hi else v
def interp_pole(year):
    for i in range(len(N_POLE_HISTORY)-1):
        y0,lat0,lon0=N_POLE_HISTORY[i]; y1,lat1,lon1=N_POLE_HISTORY[i+1]
        if y0<=year<=y1:
            t=(year-y0)/(y1-y0) if y1!=y0 else 0
            dlon=((lon1-lon0+540)%360)-180
            return lerp(lat0,lat1,t), lon0+dlon*t
    return N_POLE_HISTORY[-1][1], N_POLE_HISTORY[-1][2]
def interp_moment(year):
    for i in range(len(MOMENT_HISTORY)-1):
        y0,m0=MOMENT_HISTORY[i]; y1,m1=MOMENT_HISTORY[i+1]
        if y0<=year<=y1: return lerp(m0,m1,(year-y0)/(y1-y0))
    return MOMENT_HISTORY[-1][1]
def dipole_field_line(L,n=72):
    pts=[]
    for i in range(n):
        theta=math.pi*0.09+(math.pi*0.82)*i/(n-1)
        r=L*(math.sin(theta)**2)
        if 0.25<r<2.1: pts.append((r,theta))
    return pts

def _to_py(o):
    try:
        if hasattr(o,"to_py"): return o.to_py()
    except: pass
    return o
def _js_get(o,k,d=None):
    try:
        o=_to_py(o)
        if isinstance(o,dict): return o.get(k,d)
        try:
            g=getattr(o,'get',None)
            if callable(g): return g(k,d)
        except: pass
        try: return o[k]
        except: pass
        try: return getattr(o,k)
        except: pass
        return d
    except: return d

async def fetch_json_cors(url):
    try:
        if HAS_FETCH and fetch_json:
            try:
                data=await fetch_json(url)
                print(f"fetch_json_cors OK {url[:80]}")
                return _to_py(data)
            except Exception as e:
                print(f"extensions.fetch failed {e}")
        r=await window.fetch(url)
        if not r.ok: raise Exception(f"HTTP {r.status}")
        data=await r.json()
        print(f"fetch_json_cors OK window.fetch {url[:60]}")
        return _to_py(data)
    except Exception as e:
        print(f"fetch_json_cors {url[:60]} failed {e}")
        raise

async def fetch_json_popular(urls,label):
    last=None
    for url in urls:
        try:
            data=await fetch_json_cors(url)
            if data: return data
        except Exception as e:
            last=e; print(f"fetch_json_popular {label} {url[:60]} failed {e}"); continue
    raise Exception(f"All failed {label}: {last}")

PYODIDE_CODE = """
try:
    import pyodide_js
    await pyodide_js.loadPackage("numpy")
    print("pyodide_js loadPackage numpy OK")
except Exception as e:
    print(f"pyodide_js load failed {e}")
    try:
        import js
        await js.pyodide.loadPackage("numpy")
        print("js.pyodide OK")
    except Exception as e2:
        print(f"js.pyodide failed {e2}")

import numpy as np
year=globals().get('year',2025); moment=globals().get('moment',7.7)
pole_lat=np.deg2rad(globals().get('pole_lat',86.1)); pole_lon=np.deg2rad(globals().get('pole_lon',150.0))
lats=np.linspace(-80,80,18); lons=np.linspace(-180,180,36)
decl=np.zeros((len(lats),len(lons))); drift=(year-1800)*0.2
for i in range(len(lats)):
 for j in range(len(lons)):
  latr=np.deg2rad(lats[i]); lonr=np.deg2rad(lons[j])
  d=np.rad2deg(np.arctan2(np.sin(lonr-pole_lon)*np.cos(pole_lat), np.cos(latr)*np.sin(pole_lat)-np.sin(latr)*np.cos(pole_lat)*np.cos(lonr-pole_lon)))
  d+=8*np.sin(2*lonr+np.deg2rad(drift))*np.cos(latr); d+=(7.7-moment)*3; decl[i,j]=((d+540)%360)-180
F=30+25*np.abs(np.sin(lats)[:,None]); degrees=np.arange(1,9); power=moment**2*(0.9**degrees)/degrees
{'declination':decl.tolist(),'intensity':F.tolist(),'power_spectrum':power.tolist(),'lats':lats.tolist(),'lons':lons.tolist()}
"""

async def compute_with_pyodide(app):
    if not HAS_PYODIDE:
        app.pyodide_status="pyodide not available"; app.log_pyodide=app.pyodide_status; return
    try:
        app.pyodide_status="Pyodide computing..."
        code=f"year={app.year}\nmoment={app.dipole_moment}\npole_lat={app.pole_lat}\npole_lon={app.pole_lon}\n"+PYODIDE_CODE
        res=await run_python(code)
        res=_to_py(res)
        if isinstance(res,dict):
            app.decl_grid=res.get('declination')
            app.power_spec=res.get('power_spectrum',[1,0.7,0.5,0.35,0.22,0.15,0.1,0.06])
            app.pyodide_status=f"pyodide OK {len(app.decl_grid) if app.decl_grid else 0}"
        else:
            try:
                if hasattr(res,'get'):
                    app.decl_grid=res.get('declination')
                    app.power_spec=res.get('power_spectrum',[1,0.7,0.5,0.35,0.22,0.15,0.1,0.06])
                    app.pyodide_status="pyodide OK via get"
                else:
                    app.pyodide_status=f"pyodide {type(res)}"
            except Exception as e2:
                app.pyodide_status=f"pyodide parse {e2}"
        app.log_pyodide=app.pyodide_status
        app.buttons["cache"]["enabled"]=True
        print(app.pyodide_status)
    except Exception as e:
        app.pyodide_status=f"run_python failed: {e}"; app.log_pyodide=app.pyodide_status
        print(f"run_python failed: {e}\n{traceback.format_exc()}")

async def load_live_geomag(app):
    try:
        app.fetch_status="Fetching Kp..."
        data=await fetch_json_popular(["https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"],"kp")
        data=_to_py(data)
        if isinstance(data,list) and len(data)>0:
            latest=data[-1]
            raw=_js_get(latest,'Kp',3)
            try:
                s=str(raw); num=''.join([c for c in s if c.isdigit() or c=='.'])
                app.kp_live=float(num) if num else 3.0
            except: app.kp_live=3.0
            hist=[]
            try:
                n=len(data)
                for i in range(max(0,n-60),n):
                    v=_js_get(data[i],'Kp',0); s=str(v); num=''.join([c for c in s if c.isdigit() or c=='.']); hist.append(float(num) if num else 0.0)
                if hist: app.kp_history=hist
            except Exception as e2: print(f"hist parse {e2}")
            app.log_fetch=f"Kp OK {app.kp_live:.1f}"; app.fetch_status=app.log_fetch
            print(app.log_fetch)
    except Exception as e:
        app.log_fetch=f"Kp failed: {e}"; app.fetch_status=app.log_fetch; print(app.log_fetch)
    try:
        obs=await fetch_json_popular(["https://geomag.usgs.gov/ws/observatories/?format=json"],"usgs_obs")
        obs=_to_py(obs)
        count=len(obs) if isinstance(obs, (list, dict)) else 0
        if isinstance(obs, dict) and "observatories" in obs: count=len(obs["observatories"])
        app.log_fetch2=f"USGS OBS OK {count}"; app.fetch_status2=app.log_fetch2; print(app.log_fetch2)
        try:
            if isinstance(obs, list) and len(obs)>0:
                new_obs=[]
                for entry in obs[:20]:
                    entry=_to_py(entry)
                    if isinstance(entry, dict):
                        code_=_js_get(entry,'code',None) or _js_get(entry,'id',None)
                        lat=_js_get(entry,'latitude',None); lon=_js_get(entry,'longitude',None)
                        if code_ and lat is not None and lon is not None:
                            try: new_obs.append((float(lat), float(lon), str(code_)))
                            except: pass
                if len(new_obs)>=2: app.observatories=new_obs
        except Exception as e: print(f"USGS obs parse {e}")
    except Exception as e:
        app.log_fetch2=f"USGS OBS {e}"; app.fetch_status2=app.log_fetch2; print(app.log_fetch2)
    app.log_fetch3="USGS DATA disabled"; app.fetch_status3=app.log_fetch3
    app.log_fetch4="BGS GIN disabled"; app.fetch_status4=app.log_fetch4
    aio.run(compute_with_pyodide(app))

def ensureAudioContext(app):
    if getattr(app,'audioCtx',None): return
    try:
        AC=window.AudioContext or window.webkitAudioContext
        app.audioCtx=AC.new()
    except Exception as e:
        print(f"ensureAudioContext failed {e}"); app.audioCtx=None

def stopAudioNodes(app):
    for o in getattr(app,'oscNodes',[]):
        try: o.stop()
        except: pass
    app.oscNodes=[]; app.gainNodes=[]

def play_kp_sonification(app):
    try:
        ensureAudioContext(app)
        if HAS_PROC_AUDIO and getattr(app,'procAudio',None):
            try: app.procAudio.resume()
            except Exception as e: print(f"procAudio resume {e}")
        if getattr(app,'audioCtx',None):
            try:
                if app.audioCtx.state=="suspended": app.audioCtx.resume()
            except: pass
            try:
                stopAudioNodes(app)
                master=app.audioCtx.createGain(); master.gain.value=0.28; master.connect(app.audioCtx.destination)
                base=55+app.kp_live*18+app.kp_slider*10
                osc=app.audioCtx.createOscillator(); osc.type="sine"; osc.frequency.value=base
                g=app.audioCtx.createGain(); g.gain.value=0.45
                osc.connect(g); g.connect(master); osc.start()
                app.oscNodes=[osc]; app.gainNodes=[g]; app.masterGain=master
            except Exception as e: print(f"Web Audio osc {e}")
        if HAS_PROC_AUDIO and getattr(app,'procAudio',None):
            try:
                base=55+app.kp_live*18+app.kp_slider*10
                app.procAudio.play("magnetosphere.ambient",seed=int(base),spatial=False)
            except Exception as e: print(f"procAudio play {e}")
        app.is_playing=True; app.log_audio=f"Audio OK Kp {app.kp_slider:.1f}"
    except Exception as e:
        app.log_audio=f"Audio failed {e}"; print(f"Audio failed {e}")

def stop_sonification(app):
    try:
        stopAudioNodes(app)
        if HAS_PROC_AUDIO and getattr(app,'procAudio',None):
            try:
                if hasattr(app.procAudio,'stop'): app.procAudio.stop()
                elif hasattr(app.procAudio,'stop_all'): app.procAudio.stop_all()
                elif hasattr(app.procAudio,'pause'): app.procAudio.pause()
            except Exception as e: print(f"procAudio stop {e}")
        app.is_playing=False; app.log_audio="Audio stop OK"
    except Exception as e:
        app.log_audio=f"Audio stop failed {e}"; print(f"stop failed {e}")

CACHE_KEY="emf_sigma_v21_blankfix"

def try_load_cached(app):
    try:
        raw=window.localStorage.getItem(CACHE_KEY)
        if raw is None: return False
        data=window.JSON.parse(raw); data=_to_py(data)
        if not isinstance(data,dict): return False
        app.decl_grid=data.get("decl_grid"); app.power_spec=data.get("power_spec",[1,0.7,0.5,0.35,0.22,0.15,0.1,0.06])
        app.year=int(data.get("year",2025)); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year)
        app.log_pyodide=f"Cache hit {app.year}"; return True
    except Exception as e: print(f"Cache load {e}"); return False

def cache_now(app):
    try:
        if app.decl_grid is None: return False
        payload={"decl_grid":app.decl_grid,"power_spec":app.power_spec,"year":app.year}
        jstr=window.JSON.stringify(payload); window.localStorage.setItem(CACHE_KEY,jstr); app.fetch_status=f"Cached {len(jstr)//1024}KB"; return True
    except Exception as e: print(f"Cache {e}"); return False

def clear_cache(app):
    try: window.localStorage.removeItem(CACHE_KEY); app.decl_grid=None; app.fetch_status="Cache cleared"; return True
    except Exception as e: print(f"Clear {e}"); return False

def onAppStart(app):
    try:
        app.width=W; app.height=H; app.stepsPerSecond=60; app.background=BG
        app.year=2025; app.dipole_tilt=10.5; app.dipole_moment=interp_moment(2025); app.pole_lat,app.pole_lon=interp_pole(2025)
        app.kp_live=3.2; app.kp_slider=3.0; app.solar_wind_speed=420; app.imf_bz=-2.0
        app.log_fetch="Idle"; app.log_fetch2=""; app.log_fetch3=""; app.log_fetch4=""; app.log_pyodide="Init"; app.log_audio="Idle"
        app.fetch_status="Ready"; app.fetch_status2=""; app.fetch_status3=""; app.fetch_status4=""; app.pyodide_status="Init"
        app.decl_grid=None; app.power_spec=[1,0.7,0.5,0.35,0.22,0.15,0.1,0.06]; app.kp_history=[random.uniform(0,4) for _ in range(60)]
        app.dragging_year=False; app.dragging_kp=False; app.dragging_sw=False; app.hover_panel=None; app.show_globe=False; app.globe_rot=0; app.is_playing=False; app.time=0
        app.insight="SIGMA 60FPS"
        app.audioCtx=None; app.oscNodes=[]; app.gainNodes=[]; app.masterGain=None
        try: app.procAudio=AudioEngine(quality="high",seed=90210) if HAS_PROC_AUDIO else None
        except Exception as e: print(f"AudioEngine init failed {e}"); app.procAudio=None
        app.field_lines=[dipole_field_line(L,72) for L in [1.4,1.8,2.3,3.0]]
        app.observatories=[(65.1,-19.6,"LRV"),(60.4,5.3,"DOB"),(58.7,-3.7,"LER"),(55.3,-3.2,"ESK"),(50.3,4.6,"DOU"),(52.0,-4.5,"ABK"),(40.3,-4.3,"SPT"),(36.9,-2.0,"SFS"),(28.0,-16.5,"GUI"),(64.7,-147.8,"CMO"),(47.6,-122.3,"NEW"),(38.2,-122.3,"FRN"),(-33.3,26.5,"HER"),(-23.2,-45.0,"VSS"),(-31.4,115.9,"GNG"),(35.6,140.2,"KAK"),(-43.7,172.3,"EYR")]
        app.buttons={
            "live":{"x":12,"y":44,"w":72,"h":22,"label":"LIVE","enabled":True},
            "globe":{"x":92,"y":44,"w":92,"h":22,"label":"GLOBE VIEW","enabled":True},
            "play":{"x":192,"y":44,"w":60,"h":22,"label":"PLAY","enabled":True},
            "cache":{"x":260,"y":44,"w":70,"h":22,"label":"CACHE","enabled":False},
            "clear":{"x":338,"y":44,"w":90,"h":22,"label":"CLEAR CACHE","enabled":True},
        }
        app.hover=None
        try: try_load_cached(app)
        except Exception as e: print(f"cache load failed {e}")
        try: aio.run(load_live_geomag(app))
        except Exception as e: print(f"load_live_geomag failed {e}")
        try: aio.run(compute_with_pyodide(app))
        except Exception as e: print(f"compute_with_pyodide failed {e}")
        print("onAppStart OK v21 blankfix")
    except Exception as e:
        print(f"onAppStart FATAL {e}\n{traceback.format_exc()}")
        # minimal fallback so app still shows
        try:
            app.width=W; app.height=H; app.show_globe=False; app.buttons={}; app.time=0
        except: pass

def onStep(app):
    try:
        app.time+=0.02; app.globe_rot+=0.008
        if app.is_playing and int(app.time*20)%80==0 and HAS_PROC_AUDIO and getattr(app,'procAudio',None):
            try: app.procAudio.play("magnetosphere.pulse",seed=int(app.solar_wind_speed+app.kp_slider*10))
            except Exception as e: print(f"onStep pulse {e}")
    except Exception as e:
        print(f"onStep failed {e}")

def pointInRect(px,py,rx,ry,rw,rh): return rx<=px<=rx+rw and ry<=py<=ry+rh

def onMousePress(app,mx,my):
    try:
        for bid,b in app.buttons.items():
            if b["x"]<=mx<=b["x"]+b["w"] and b["y"]<=my<=b["y"]+b["h"] and b["enabled"]:
                if bid=="live": aio.run(load_live_geomag(app))
                elif bid=="globe": 
                    app.show_globe=not app.show_globe
                    b["label"]="BACK TO LAB" if app.show_globe else "GLOBE VIEW"
                elif bid=="play":
                    if app.is_playing: stop_sonification(app)
                    else: play_kp_sonification(app)
                    b["label"]="STOP" if app.is_playing else "PLAY"
                elif bid=="cache": cache_now(app)
                elif bid=="clear": clear_cache(app)
                return
        if app.show_globe:
            closeBx,closeBy,closeBw,closeBh=W-60,82,36,22
            if pointInRect(mx,my,closeBx,closeBy,closeBw,closeBh):
                app.show_globe=False
                app.buttons["globe"]["label"]="GLOBE VIEW"
                return
            return
        if pointInRect(mx,my,DRIFT_X+14,DRIFT_Y+DRIFT_H-22,DRIFT_W-28,24):
            app.dragging_year=True; update_year_from_x(app,mx); return
        if pointInRect(mx,my,MAG_X+14,MAG_Y+MAG_H-52,MAG_W-28,24):
            app.dragging_kp=True; update_kp_from_x(app,mx); return
        if pointInRect(mx,my,MAG_X+14,MAG_Y+MAG_H-22,MAG_W-28,24):
            app.dragging_sw=True; update_sw_from_x(app,mx); return
        if pointInRect(mx,my,DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H):
            app.dipole_tilt=11+3*math.sin(app.time*2); aio.run(compute_with_pyodide(app))
        if pointInRect(mx,my,MAG_X,MAG_Y,MAG_W,MAG_H):
            app.imf_bz=-app.imf_bz
    except Exception as e:
        print(f"onMousePress failed {e}")

def update_year_from_x(app,mx):
    t=clamp((mx-(DRIFT_X+14))/(DRIFT_W-28),0,1); app.year=int(1800+t*225); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year); app.dipole_tilt=11.5-(app.year-1800)*0.003; aio.run(compute_with_pyodide(app))
def update_kp_from_x(app,mx):
    t=clamp((mx-(MAG_X+14))/(MAG_W-28),0,1); app.kp_slider=t*9
    if app.is_playing: play_kp_sonification(app)
def update_sw_from_x(app,mx):
    t=clamp((mx-(MAG_X+14))/(MAG_W-28),0,1); app.solar_wind_speed=300+t*500

def onMouseDrag(app,mx,my):
    try:
        if app.dragging_year: update_year_from_x(app,mx)
        if app.dragging_kp: update_kp_from_x(app,mx)
        if app.dragging_sw: update_sw_from_x(app,mx)
    except Exception as e:
        print(f"onMouseDrag {e}")
def onMouseRelease(app,mx,my):
    app.dragging_year=False; app.dragging_kp=False; app.dragging_sw=False
def onMouseMove(app,mx,my):
    try:
        app.hover=None
        for bid,b in app.buttons.items():
            if b["x"]<=mx<=b["x"]+b["w"] and b["y"]<=my<=b["y"]+b["h"]: app.hover=bid
        if pointInRect(mx,my,DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H): app.hover_panel="dynamo"
        elif pointInRect(mx,my,DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H): app.hover_panel="drift"
        elif pointInRect(mx,my,MAG_X,MAG_Y,MAG_W,MAG_H): app.hover_panel="mag"
        elif pointInRect(mx,my,IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H): app.hover_panel="impact"
        else: app.hover_panel=None
    except Exception as e:
        print(f"onMouseMove {e}")
def onKeyPress(app,key):
    try:
        if key.lower()=='g': 
            app.show_globe=not app.show_globe
            app.buttons["globe"]["label"]="BACK TO LAB" if app.show_globe else "GLOBE VIEW"
        elif key==' ':
            if app.is_playing: stop_sonification(app)
            else: play_kp_sonification(app)
            app.buttons["play"]["label"]="STOP" if app.is_playing else "PLAY"
        elif key.lower()=='r': aio.run(load_live_geomag(app))
        elif key.lower()=='t': app.year=clamp(app.year+1,1800,2025); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year); aio.run(compute_with_pyodide(app))
        elif key.lower()=='e': app.year=clamp(app.year-1,1800,2025); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year); aio.run(compute_with_pyodide(app))
    except Exception as e:
        print(f"onKeyPress {e}")

def drawPanel(x,y,w,h,title=""):
    sRect(x,y,w,h,fill=PANEL_BG,border=BORDER,borderWidth=1,roundness=10)
    if title:
        sRect(x+8,y+6,w-16,16,fill=rgb(28,32,52),roundness=5)
        sLabel(title,x+14,y+14,fill=rgb(180,190,220),size=12,bold=True,align="left-top")
def draw_button(b,hover,enabled):
    x,y,w,h=b["x"],b["y"],b["w"],b["h"]
    if not enabled: fill=rgb(48,52,72); bc=rgb(68,74,102); tc=DIM
    else: fill=ACC_H if hover else ACC; bc=rgb(130,134,255) if hover else ACC; tc=rgb(255,255,255)
    sRect(x,y,w,h,fill=fill,border=bc,borderWidth=1,roundness=9)
    sLabel(b["label"],x+w/2,y+h/2,size=12,fill=tc,bold=True,align="center")

def drawHeader(app):
    sRect(0,0,W,HEADER_H,fill=rgb(18,22,38))
    sLabel("EMF LAB — Dynamo, Drift & Impact",W*0.5,8,fill=TXT,size=14,bold=True,align="center-top")
    sLabel(f"{app.year}  M {app.dipole_moment:.2f}e22  Pole {app.pole_lat:.1f}N {app.pole_lon:.1f}E  Kp {app.kp_live:.1f}",W*0.5,26,fill=DIM,size=11,align="center-top")

def drawDynamo(app):
    drawPanel(DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H,"DYNAMO CORE - cached")
    gx,gy,gw,gh=DYNAMO_X+14,DYNAMO_Y+34,DYNAMO_W-28,DYNAMO_H-52
    sRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    cx=gx+gw*0.38; cy=gy+gh*0.52; earth_r=92
    sCircle(cx,cy,earth_r,fill=rgb(45,35,25),border=rgb(80,60,40),borderWidth=1)
    outer_r=earth_r*0.55; sCircle(cx,cy,outer_r,fill=rgb(200,90,20),border=rgb(255,160,80),borderWidth=1)
    for k in range(6):
        ang=k*60+app.time*18; rad=outer_r*0.62; x=cx+rad*math.cos(math.radians(ang)); y=cy+rad*math.sin(math.radians(ang))*0.75
        ax=math.cos(math.radians(ang+90))*10; ay=math.sin(math.radians(ang+90))*7
        sLine(x,y,x+ax,y+ay,fill=ORANGE,lineWidth=1.5)
        sCircle(x,y,3,fill=YELLOW)
    tilt=math.radians(app.dipole_tilt)
    for line in getattr(app,'field_lines',[]):
        pts=[]
        for r,theta in line:
            th=theta-tilt; px=cx+r*earth_r*0.85*math.sin(th); py=cy-r*earth_r*0.85*math.cos(th)*0.9
            if math.hypot(px-cx,py-cy)>earth_r*0.98 or abs(theta-math.pi/2)>0.6: pts.append((px,py))
        for i in range(len(pts)-1): sLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=CYAN,lineWidth=1)
    sLabel(f"alpha-omega {app.dipole_tilt:.1f}deg",gx+8,gy+gh-8,fill=DIM,size=12,align="left-bottom")

def drawDrift(app):
    drawPanel(DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H,"SECULAR 1800-2025 Pole Wander")
    gx,gy,gw,gh=DRIFT_X+14,DRIFT_Y+34,DRIFT_W-28,DRIFT_H-78
    sRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    pcx=gx+gw*0.34; pcy=gy+gh*0.48; pr=78
    sCircle(pcx,pcy,pr,fill=rgb(16,20,36),border=rgb(50,60,90),borderWidth=1)
    sCircle(pcx,pcy,pr*0.33,fill=None,border=rgb(40,50,80),borderWidth=1)
    sCircle(pcx,pcy,pr*0.66,fill=None,border=rgb(40,50,80),borderWidth=1)
    sLine(pcx-pr,pcy,pcx+pr,pcy,fill=rgb(40,50,80),lineWidth=1)
    sLine(pcx,pcy-pr,pcx,pcy+pr,fill=rgb(40,50,80),lineWidth=1)
    prev=None
    for y,lat,lon in N_POLE_HISTORY:
        r=(90-lat)/20*pr; th=math.radians(lon+90); x=pcx+r*math.cos(th); y_=pcy+r*math.sin(th)
        t=(y-1800)/225; col=rgb(int(lerp(80,255,t)),int(lerp(180,90,t)),int(lerp(255,80,t)))
        if prev: sLine(prev[0],prev[1],x,y_,fill=col,lineWidth=2)
        sCircle(x,y_,3.5,fill=col,border=rgb(0,0,0),borderWidth=1); prev=(x,y_)
        if y==app.year:
            sCircle(x,y_,9,fill=col); sCircle(x,y_,5.5,fill=YELLOW,border=rgb(255,255,255),borderWidth=1)
    sx=DRIFT_X+14; sy=DRIFT_Y+DRIFT_H-22; sw=DRIFT_W-28
    sRect(sx,sy,sw,8,fill=rgb(30,35,55),border=BORDER,borderWidth=1,roundness=4)
    t=(app.year-1800)/225; sRect(sx,sy,t*sw,8,fill=ORANGE,roundness=4); sCircle(sx+t*sw,sy+4,8,fill=rgb(255,255,255),border=ORANGE,borderWidth=2)

def drawMag(app):
    drawPanel(MAG_X,MAG_Y,MAG_W,MAG_H,f"MAGNETOSPHERE Kp {app.kp_slider:.1f} SW {int(app.solar_wind_speed)} Bz {app.imf_bz:+.1f}")
    gx,gy,gw,gh=MAG_X+14,MAG_Y+34,MAG_W-28,MAG_H-82
    sRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    sun_x=gx+28; sun_y=gy+gh*0.5; sCircle(sun_x,sun_y,18,fill=rgb(255,220,80),border=rgb(255,180,40),borderWidth=1)
    ex=gx+gw*0.45; ey=gy+gh*0.5; sCircle(ex,ey,18,fill=rgb(80,140,255),border=rgb(255,255,255),borderWidth=1); sCircle(ex,ey,6,fill=GREEN)
    rmp=10*(400/app.solar_wind_speed)**0.33*(1-app.kp_slider*0.03); rmp_px=rmp*9
    sCircle(ex,ey,rmp_px,fill=None,border=CYAN,borderWidth=2)
    sLabel(f"MP {rmp:.1f} Re",ex-rmp_px*0.7,ey-22,fill=CYAN,size=12,align="center-bottom")
    sCircle(ex,ey,rmp_px*1.35,fill=None,border=rgb(180,180,200),borderWidth=1)
    ksx=MAG_X+14; ksy=MAG_Y+MAG_H-52; ksw=MAG_W-28
    sRect(ksx,ksy,ksw,8,fill=rgb(30,35,55),border=BORDER,borderWidth=1,roundness=4)
    tk=app.kp_slider/9; colk=GREEN if tk<0.44 else YELLOW if tk<0.66 else RED; sRect(ksx,ksy,tk*ksw,8,fill=colk,roundness=4); sCircle(ksx+tk*ksw,ksy+4,8,fill=rgb(255,255,255),border=colk,borderWidth=2)
    ssx=MAG_X+14; ssy=MAG_Y+MAG_H-22; ssw=MAG_W-28
    sRect(ssx,ssy,ssw,8,fill=rgb(30,35,55),border=BORDER,borderWidth=1,roundness=4)
    tsw=(app.solar_wind_speed-300)/500; sRect(ssx,ssy,tsw*ssw,8,fill=BLUE,roundness=4); sCircle(ssx+tsw*ssw,ssy+4,8,fill=rgb(255,255,255),border=BLUE,borderWidth=2)

def drawImpact(app):
    drawPanel(IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H,"IMPACT — SAA, Navigation, Systems")
    gx,gy,gw,gh=IMPACT_X+14,IMPACT_Y+34,IMPACT_W-28,IMPACT_H-58
    sRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    mx=gx+6; my=gy+8; mw=gw*0.58; mh=gh-16; sRect(mx,my,mw,mh,fill=rgb(16,24,42),border=rgb(35,45,75),borderWidth=1,roundness=6)
    for lat in [-60,-30,0,30,60]:
        y=my+(80-lat)/160*mh; sLine(mx,y,mx+mw,y,fill=rgb(35,45,75),lineWidth=1)
    for lon in [-120,-60,0,60,120]:
        x=mx+(lon+180)/360*mw; sLine(x,my,x,my+mh,fill=rgb(35,45,75),lineWidth=1)
    saa_x=mx+(-50+180)/360*mw; saa_y=my+(80-(-26))/160*mh; saa_r=28+(8.6-app.dipole_moment)*12
    sCircle(saa_x,saa_y,saa_r*2,fill=RED); sLabel("SAA",saa_x,saa_y-2,fill=RED,size=12,bold=True,align="center")
    for lat,lon,code in app.observatories:
        x=mx+(lon+180)/360*mw; y=my+(80-lat)/160*mh; sCircle(x,y,2.2,fill=CYAN,border=rgb(0,0,0),borderWidth=1)
    px=gx+gw*0.62+8; py=gy+8; pw=gw*0.36-8; ph=mh*0.48; sRect(px,py,pw,ph,fill=rgb(16,20,36),border=rgb(35,45,75),borderWidth=1,roundness=6)
    sLabel("Power n",px+4,py+4,fill=DIM,size=12,align="left-top")
    maxp=max(app.power_spec) if max(app.power_spec)>0 else 1
    for i,p in enumerate(app.power_spec[:8]):
        bx=px+8+i*(pw-16)/8; bw=(pw-20)/8*0.7; bh=(p/maxp)*(ph-22); sRect(bx,py+ph-8-bh,bw,bh,fill=PURPLE if i>0 else YELLOW,roundness=3); sLabel(str(i+1),bx+bw/2,py+ph-2,fill=DIM,size=12,align="center-bottom")
    ix=gx+gw*0.62+8; iy=gy+ph+18; iw=gw*0.36-8; ih=mh-ph-18; sRect(ix,iy,iw,ih,fill=rgb(16,20,36),border=rgb(35,45,75),borderWidth=1,roundness=6)
    impacts=[f"WMM err {app.year-2020}*0.2deg",f"True=Mag {app.decl_grid[9][18] if app.decl_grid else 5:+.1f}deg",f"SAA x{1.2+(8.6-app.dipole_moment):.1f}","GIC Kp>6","Aviation","Animals mag","Met: true north"]
    for k,txt in enumerate(impacts):
        y=iy+8+k*13
        if y<iy+ih-4: sLabel(txt,ix+6,y,fill=YELLOW if k==0 else DIM,size=12,align="left-top")

def drawGlobeOverlay(app):
    sRect(0,0,W,H,fill=BG); sRect(0,0,W,HEADER_H,fill=rgb(18,22,38))
    sLabel("GLOBE VIEW — Compass Needles & Field",W*0.5,8,fill=TXT,size=14,bold=True,align="center-top")
    sLabel("Dipole + IGRF non-dipole. Needles = declination.",W*0.5,26,fill=DIM,size=11,align="center-top")
    gx,gy,gw,gh=16,HEADER_H+12,680,600; sRect(gx,gy,gw,gh,fill=PANEL,border=BORDER,borderWidth=1,roundness=14)
    cx=gx+gw*0.48; cy=gy+gh*0.5; R=210; sCircle(cx,cy,R,fill=rgb(20,35,60),border=rgb(60,80,110),borderWidth=1)
    tilt=math.radians(app.dipole_tilt+5*math.sin(app.time*0.5))
    for L in [1.6,2.0,2.5,3.2,4.0]:
        pts=[]
        for th_deg in range(12,168,4):
            th=math.radians(th_deg); r=L*(math.sin(th)**2)
            if r<1.05 or r>5: continue
            th2=th-tilt; x=cx+r*R*0.92*math.sin(th2); y=cy-r*R*0.92*math.cos(th2)*0.42
            if math.hypot(x-cx,(y-cy)/0.42)>R*1.02: pts.append((x,y))
        for i in range(len(pts)-1): sLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=CYAN,lineWidth=1)
    if app.decl_grid:
        for i in range(0,18,3):
            for j in range(0,36,6):
                lat=80-i/18*160; lon=-180+j/36*360+app.globe_rot*20; th=math.radians(lon)
                if math.cos(th)<0: continue
                x=cx+R*math.cos(math.radians(lat))*math.sin(th)*0.9*0.85; y=cy+R*math.sin(math.radians(lat))*0.42*0.85
                decl=app.decl_grid[i][j]; ang=math.radians(decl)
                sLine(x,y,x+8*math.sin(ang),y-8*math.cos(ang)*0.42,fill=RED,lineWidth=1)
                sLine(x,y,x-6*math.sin(ang),y+6*math.cos(ang)*0.42,fill=BLUE,lineWidth=1)
    saa_lat,saa_lon=-26,-50; th=math.radians(saa_lon+app.globe_rot*20); sx=cx+R*math.cos(math.radians(saa_lat))*math.sin(th)*0.9; sy=cy+R*math.sin(math.radians(saa_lat))*0.42
    if math.cos(th)>0:
        sCircle(sx,sy,18,fill=RED); sCircle(sx,sy,10,fill=RED,border=rgb(255,255,255),borderWidth=1); sLabel("SAA low F",sx+14,sy,fill=RED,size=12,bold=True,align="left-center")
    plat,plon=app.pole_lat,app.pole_lon+app.globe_rot*20; th=math.radians(plon); px=cx+R*math.cos(math.radians(plat))*math.sin(th)*0.9; py=cy+R*math.sin(math.radians(plat))*0.42
    if math.cos(th)>-0.2: sCircle(px,py,6,fill=YELLOW,border=rgb(255,255,255),borderWidth=1); sLabel(f"NMP {app.year}",px+8,py,fill=YELLOW,size=12,bold=True,align="left-center")
    ix,iy,iw,ih=710,82,324,180; sRect(ix,iy,iw,ih,fill=PANEL,border=BORDER,borderWidth=1,roundness=10); sLabel("DYNAMO THEORY",ix+12,iy+10,fill=TXT,size=12,bold=True,align="left-top")
    lines=["Outer core Fe ~4mm/s","Coriolis alpha-effect","Differential omega","Dipole 80% surface","West drift 0.2deg/yr","Reversals ~200kyr","Laschamp 42kya 5%","Decay 5%/century"]
    for k,l in enumerate(lines): sLabel(l,ix+12,iy+28+k*16,fill=DIM,size=12,align="left-top")
    ex,ey,ew,eh=710,274,324,180; sRect(ex,ey,ew,eh,fill=PANEL,border=BORDER,borderWidth=1,roundness=10); sLabel("EDUCATORS - SIGMA",ex+12,ey+10,fill=TXT,size=12,bold=True,align="left-top")
    edu=["True vs Mag 0-30deg","WMM2025 airports","Phones WMM+gyro","GPS not mag","Mag != weather","GIC affects sensors","Aurora Kp+Bz south","Field protects atmo"]
    for k,l in enumerate(edu): sLabel(l,ex+12,ey+28+k*16,fill=DIM,size=12,align="left-top")
    dx,dy,dw,dh=710,466,324,150; sRect(dx,dy,dw,dh,fill=PANEL,border=BORDER,borderWidth=1,roundness=10); sLabel("LIVE DATA",dx+12,dy+10,fill=TXT,size=12,bold=True,align="left-top")
    src=[f"Kp {app.kp_live:.1f} live",f"USGS OBS {app.log_fetch2[:30]}",f"Pyodide {app.log_pyodide[:28]}",f"Audio {app.log_audio[:24]}","WMM2025 IGRF-14"]
    for k,l in enumerate(src): sLabel(l,dx+12,dy+28+k*18,fill=DIM,size=12,align="left-top")
    closeBx,closeBy,closeBw,closeBh=W-60,82,36,22
    sRect(closeBx,closeBy,closeBw,closeBh,fill=rgb(60,70,90),border=rgb(200,210,230),borderWidth=1,roundness=7); sLabel("X",closeBx+closeBw/2,closeBy+closeBh/2,fill=rgb(230,240,255),size=12,bold=True,align="center")

def redrawAll(app):
    try:
        sRect(0,0,W,H,fill=BG)
        drawHeader(app)
        if app.show_globe:
            drawGlobeOverlay(app)
        else:
            drawDynamo(app); drawDrift(app); drawMag(app); drawImpact(app)
        for bid in app.buttons:
            b=app.buttons[bid]
            if bid=="globe":
                b["label"]="BACK TO LAB" if app.show_globe else "GLOBE VIEW"
            draw_button(b, app.hover==bid, b["enabled"])
    except Exception as e:
        print(f"redrawAll failed {e}\n{traceback.format_exc()}")
        try:
            sRect(0,0,W,H,fill=BG)
            sLabel(f"Redraw error: {e}", 20, 20, fill=RED, size=14, align="left-top")
            sLabel(traceback.format_exc()[:600], 20, 50, fill=DIM, size=11, align="left-top")
        except:
            print("redrawAll even fallback failed")
