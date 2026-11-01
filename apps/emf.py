
"""
EMF Lab - Earth's Magnetic Field Dynamics v7 - Fourier Ear Lab parity
Layout: 1050x700, header 70, 4 panels like Ear Lab, 60fps, cached geometry, min font 12
Audio: window.AudioContext + AudioEngine dual, like Ear Lab
Fetch: window.fetch multi-source with to_py, like Ear Lab
Pyodide: loadPackage numpy directly, no micropip - fixed lame shit
"""
from scs import *
from browser import window, aio, document
import math, random, traceback

try:
    from extensions.proc_audio import AudioEngine
    HAS_PROC_AUDIO=True
except:
    HAS_PROC_AUDIO=False
    AudioEngine=None
try:
    from extensions.fetch import fetch_json, fetch_text, fetch
    HAS_FETCH=True
except:
    HAS_FETCH=False
    fetch_json=None; fetch_text=None; fetch=None
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
PANEL_BORDER=rgb(45,55,85)
CYAN=rgb(88,240,255)
PINK=rgb(255,110,180)
YELLOW=rgb(255,230,110)
GREEN=rgb(110,255,170)
PURPLE=rgb(160,120,255)
ORANGE=rgb(255,160,80)
RED=rgb(255,90,90)
BLUE=rgb(110,180,255)
TXT=rgb(236,240,255)
DIM=rgb(150,160,188)
GRID=rgb(44,50,76)
PANEL=rgb(28,31,48)
PANEL2=rgb(22,26,42)
BORDER=rgb(58,64,94)
ACC=rgb(99,102,241)
ACC_H=rgb(129,133,255)
ACC2=rgb(16,185,129)

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

# SCS pattern: SOURCES multi-mirror, but only CORS-enabled endpoints to avoid console spam
# Direct SWPC works (CORS *), others use allorigins/get which itself has CORS * and proxy.cors.sh which has CORS *
SOURCES={
    "kp":[
        "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json",
    ],
    "intermagnet":[
        "https://api.allorigins.win/get?url=https://www.intermagnet.org/data_download.html",
        "https://proxy.cors.sh/https://www.intermagnet.org/data_download.html",
    ],
    "datagov":[
        "https://api.allorigins.win/get?url=https://catalog.data.gov/api/3/action/package_show?id=data-on-the-earths-magnetic-field-and-its-secular-change-since-1800",
        "https://proxy.cors.sh/https://catalog.data.gov/api/3/action/package_show?id=data-on-the-earths-magnetic-field-and-its-secular-change-since-1800",
    ],
    "ncei":[
        "https://api.allorigins.win/get?url=https://www.ncei.noaa.gov/products/geomagnetic-data",
        "https://proxy.cors.sh/https://www.ncei.noaa.gov/products/geomagnetic-data",
    ],
}

def _decode_allorigins_response(resp_json):
    # allorigins/get returns {contents: "<html>...", status: {...}}
    # contents may be JSON string or HTML
    try:
        r=_to_py(resp_json)
        if isinstance(r, dict):
            c=r.get('contents','')
            if c:
                return c
            # sometimes nested?
            return str(r)[:2000]
        return str(r)
    except Exception as e:
        print(f"_decode_allorigins {e}")
        return ""

async def fetch_text_via_allorigins_or_proxy(url):
    # url is already allorigins/get?url=... or proxy.cors.sh/...
    # For allorigins/get we need to parse JSON then contents
    try:
        if "api.allorigins.win/get" in url:
            # Use extensions.fetch for JSON
            if HAS_FETCH and fetch_json:
                try:
                    j=await fetch_json(url)
                    txt=_decode_allorigins_response(j)
                    if txt and len(txt)>=10:
                        print(f"fetch_text allorigins/get OK {url[:80]} len {len(txt)}")
                        return txt
                except Exception as e:
                    print(f"allorigins/get fetch_json failed {e}")
            # window.fetch fallback
            r=await window.fetch(url)
            if not r.ok: raise Exception(f"allorigins status {r.status}")
            j=await r.json()
            txt=_decode_allorigins_response(j)
            if txt and len(txt)>=10:
                print(f"fetch_text allorigins/get via window.fetch OK len {len(txt)}")
                return txt
            raise Exception("empty allorigins contents")
        else:
            # proxy.cors.sh returns raw text directly
            if HAS_FETCH and fetch_text:
                try:
                    txt=await fetch_text(url)
                    if txt and len(str(txt))>=10:
                        print(f"fetch_text proxy.cors.sh OK via extensions.fetch {url[:80]}")
                        return str(txt)
                except Exception as e:
                    print(f"proxy.cors.sh fetch_text failed {e}")
            r=await window.fetch(url)
            if not r.ok: raise Exception(f"proxy status {r.status}")
            txt=await r.text()
            if txt and len(str(txt))>=10:
                print(f"fetch_text proxy.cors.sh via window.fetch OK len {len(str(txt))}")
                return str(txt)
            raise Exception("empty proxy contents")
    except Exception as e:
        print(f"fetch_text_via_allorigins_or_proxy {url[:80]} failed {e}")
        raise


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

async def fetch_json_popular(urls,label):
    # Kp only - direct SWPC has CORS *, no proxy needed
    last=None
    if HAS_FETCH and fetch_json:
        for url in urls:
            # Skip allorigins wrapper for Kp - direct fetch
            if "planetary_k_index" in url:
                try:
                    data=await fetch_json(url)
                    data=_to_py(data)
                    if data:
                        print(f"fetch_json {label} OK via extensions.fetch {url[:60]}")
                        return data
                except Exception as e:
                    last=e
                    print(f"extensions.fetch_json {label} failed {e}")
                    continue
    # For Kp, also try window.fetch direct
    for url in urls:
        if "planetary_k_index" in url:
            try:
                resp=await window.fetch(url)
                if not resp.ok: raise Exception(f"HTTP {resp.status}")
                data=await resp.json()
                print(f"fetch_json {label} OK via window.fetch")
                return _to_py(data)
            except Exception as e:
                last=e
                print(f"window.fetch_json {label} failed {e}")
                continue
    raise Exception(f"All failed {label}: {last}")

async def fetch_text_popular(urls,label):
    # For intermagnet/datagov/ncei - only try ONE proxy that has CORS * to avoid console spam
    # Use allorigins/get helper
    last=None
    for url in urls:
        try:
            txt=await fetch_text_via_allorigins_or_proxy(url)
            if txt and len(str(txt))>=10:
                return str(txt)
        except Exception as e:
            last=e
            continue
    raise Exception(f"All failed {label}: {last}")

async def fetch_json_via_allorigins(url):
    # url is direct data.gov url, we wrap it in allorigins/get and parse contents as JSON
    api=f"https://api.allorigins.win/get?url={window.encodeURIComponent(url)}"
    try:
        if HAS_FETCH and fetch_json:
            try:
                j=await fetch_json(api)
                c=_decode_allorigins_response(j)
                if c:
                    import json as _jsjson
                    try:
                        return _jsjson.loads(c)
                    except:
                        # c may already be dict?
                        return _to_py(c)
            except Exception as e:
                print(f"fetch_json_via_allorigins extensions.fetch failed {e}")
        r=await window.fetch(api)
        if not r.ok: raise Exception(f"allorigins status {r.status}")
        j=await r.json()
        c=_decode_allorigins_response(j)
        import json as _jsjson
        return _jsjson.loads(c)
    except Exception as e:
        print(f"fetch_json_via_allorigins {url[:60]} failed {e}")
        raise


async def fetch_text_popular(urls,label):
    last=None
    for url in urls:
        try:
            resp=await window.fetch(url)
            if not resp.ok: raise Exception(f"HTTP {resp.status}")
            txt=await resp.text()
            txt=str(txt)
            if len(txt)<10: raise Exception("short")
            return txt
        except Exception as e:
            last=e
            print(f"fetch_text_popular {label} {url} {e}")
            continue
    raise Exception(f"All failed {label}: {last}")

# Fixed pyodide - no micropip import at top level, load numpy via loadPackage
PYODIDE_CODE = """
# Fourier Ear Lab parity: no micropip crash, use loadPackage numpy directly
try:
    import pyodide
    await pyodide.loadPackage("numpy")
except Exception as e:
    print(f"pyodide load numpy failed {e}")
    try:
        import pyodide_js
        await pyodide_js.loadPackage("numpy")
    except Exception as e2:
        print(f"pyodide_js load numpy failed {e2}")

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
        app.pyodide_status="pyodide not available - Fourier Ear pattern no pyodide"; app.log_pyodide=app.pyodide_status; return
    try:
        app.pyodide_status="Pyodide computing..."
        code=f"year={app.year}\nmoment={app.dipole_moment}\npole_lat={app.pole_lat}\npole_lon={app.pole_lon}\n"+PYODIDE_CODE
        res=await run_python(code)
        res=_to_py(res)
        if isinstance(res,dict):
            app.decl_grid=res.get('declination')
            app.power_spec=res.get('power_spectrum',[1,0.7,0.5,0.35,0.22,0.15,0.1,0.06])
            app.pyodide_status=f"pyodide OK {len(app.decl_grid)}x{len(app.decl_grid[0])} via loadPackage - fixed"
            app.log_pyodide=app.pyodide_status
            app.buttons["cache"]["enabled"]=True
        else:
            app.pyodide_status=f"pyodide not dict {type(res)}"; app.log_pyodide=app.pyodide_status
    except Exception as e:
        app.pyodide_status=f"run_python failed: {e}"; app.log_pyodide=app.pyodide_status
        print(f"run_python failed: {e}\n{traceback.format_exc()}")

async def load_live_geomag(app):
    # Kp - direct, CORS *, should always work like Fourier Ear fetch_text from raw github
    try:
        app.fetch_status="Fetching Kp..."
        data=await fetch_json_popular(SOURCES["kp"],"kp")
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
            app.log_fetch=f"Kp OK {app.kp_live:.1f} via extensions.fetch - like Ear Lab"; app.fetch_status=app.log_fetch
            print(app.log_fetch)
        else:
            raise Exception("Kp not list")
    except Exception as e:
        app.log_fetch=f"Kp fetch failed: {e}"; app.fetch_status=app.log_fetch; print(app.log_fetch)

    # INTERMAGNET - has no CORS, use allorigins/get which HAS CORS *, avoid direct fetch to intermagnet.org (would cause browser CORS error)
    try:
        txt=await fetch_text_popular(SOURCES["intermagnet"],"intermagnet")
        app.log_fetch2=f"INTERMAGNET OK {len(txt)} via allorigins/get - no CORS spam"; app.fetch_status2=app.log_fetch2
        print(app.log_fetch2)
    except Exception as e:
        app.log_fetch2=f"INTERMAGNET CORS blocked, static data used - {e}"; app.fetch_status2=app.log_fetch2; print(app.log_fetch2)

    # Data.gov - same, use allorigins/get
    try:
        # Try via allorigins/get helper that parses contents
        direct_url="https://catalog.data.gov/api/3/action/package_show?id=data-on-the-earths-magnetic-field-and-its-secular-change-since-1800"
        meta=await fetch_json_via_allorigins(direct_url)
        meta=_to_py(meta); title=""
        if isinstance(meta,dict):
            if "result" in meta: title=_js_get(_to_py(meta.get("result",{})),'title','')
            else: title=_js_get(meta,'title','')
        app.log_fetch3=f"Data.gov OK {str(title)[:24]} via allorigins/get"; app.fetch_status3=app.log_fetch3
        print(app.log_fetch3)
    except Exception as e:
        # Fallback try text popular (proxy.cors.sh)
        try:
            txt=await fetch_text_popular(SOURCES["datagov"],"datagov")
            app.log_fetch3=f"Data.gov OK {len(txt)} via proxy.cors.sh"; app.fetch_status3=app.log_fetch3
            print(app.log_fetch3)
        except Exception as e2:
            app.log_fetch3=f"Data.gov CORS blocked, static - {e2}"; app.fetch_status3=app.log_fetch3; print(app.log_fetch3)

    try:
        t=await fetch_text_popular(SOURCES["ncei"],"ncei")
        app.log_fetch4=f"NCEI OK {len(t)} via allorigins/get"; app.fetch_status4=app.log_fetch4
        print(app.log_fetch4)
    except Exception as e:
        app.log_fetch4=f"NCEI CORS blocked, static - {e}"; app.fetch_status4=app.log_fetch4; print(app.log_fetch4)

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
                app.procAudio.play("magnetosphere.pulse",seed=int(app.solar_wind_speed+app.kp_slider*10))
            except Exception as e: print(f"procAudio play {e}")
        app.is_playing=True
        app.log_audio=f"Audio OK Kp {app.kp_slider:.1f} base {int(55+app.kp_slider*10)}Hz - Ear parity"
    except Exception as e:
        app.log_audio=f"Audio failed {e}"; print(f"Audio failed {e}\n{traceback.format_exc()}")

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

CACHE_KEY="emf_sigma_v7_ear_parity"

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
    app.width=W; app.height=H; app.stepsPerSecond=60; app.background=BG
    app.year=2025; app.dipole_tilt=10.5; app.dipole_moment=interp_moment(2025); app.pole_lat,app.pole_lon=interp_pole(2025)
    app.kp_live=3.2; app.kp_slider=3.0; app.solar_wind_speed=420; app.imf_bz=-2.0
    app.log_fetch="Idle"; app.log_fetch2=""; app.log_fetch3=""; app.log_fetch4=""; app.log_pyodide="Init loadPackage numpy - no micropip"; app.log_audio="Idle"
    app.fetch_status="Ready - LIVE (Ear pattern)"; app.fetch_status2=""; app.fetch_status3=""; app.fetch_status4=""; app.pyodide_status="Init"
    app.decl_grid=None; app.power_spec=[1,0.7,0.5,0.35,0.22,0.15,0.1,0.06]; app.kp_history=[random.uniform(0,4) for _ in range(60)]
    app.dragging_year=False; app.dragging_kp=False; app.dragging_sw=False; app.hover_panel=None; app.show_globe=False; app.globe_rot=0; app.is_playing=False; app.time=0
    app.insight="SIGMA LAB - 60fps parity with Fourier Ear - cached field lines, min 12pt"
    app.audioCtx=None; app.oscNodes=[]; app.gainNodes=[]; app.masterGain=None; app.analyser=None
    app.procAudio=AudioEngine(quality="high",seed=90210) if HAS_PROC_AUDIO else None
    # cached geometry like Ear Lab caches samples
    app.field_lines=[dipole_field_line(L,72) for L in [1.4,1.8,2.3,3.0]]
    app.observatories=[(65.1,-19.6,"LRV"),(60.4,5.3,"DOB"),(58.7,-3.7,"LER"),(55.3,-3.2,"ESK"),(50.3,4.6,"DOU"),(52.0,-4.5,"ABK"),(40.3,-4.3,"SPT"),(36.9,-2.0,"SFS"),(28.0,-16.5,"GUI"),(64.7,-147.8,"CMO"),(47.6,-122.3,"NEW"),(38.2,-122.3,"FRN"),(-33.3,26.5,"HER"),(-23.2,-45.0,"VSS"),(-31.4,115.9,"GNG"),(35.6,140.2,"KAK"),(-43.7,172.3,"EYR")]
    app.buttons={
        "live":{"x":30,"y":610,"w":90,"h":38,"label":"LIVE","enabled":True},
        "globe":{"x":130,"y":610,"w":110,"h":38,"label":"GLOBE VIEW","enabled":True},
        "play":{"x":250,"y":610,"w":80,"h":38,"label":"PLAY","enabled":True},
        "cache":{"x":340,"y":610,"w":110,"h":38,"label":"CACHE","enabled":False},
        "clear":{"x":460,"y":610,"w":100,"h":38,"label":"CLEAR CACHE","enabled":True},
    }
    app.hover=None
    try_load_cached(app)
    aio.run(load_live_geomag(app))
    aio.run(compute_with_pyodide(app))

def onStep(app):
    app.time+=0.02; app.globe_rot+=0.008
    if app.is_playing and int(app.time*20)%80==0 and HAS_PROC_AUDIO and getattr(app,'procAudio',None):
        try: app.procAudio.play("magnetosphere.pulse",seed=int(app.solar_wind_speed+app.kp_slider*10))
        except Exception as e: print(f"onStep pulse {e}")

def pointInRect(px,py,rx,ry,rw,rh): return rx<=px<=rx+rw and ry<=py<=ry+rh

def onMousePress(app,mx,my):
    earBx,earBy,earBw,earBh=W-132,10,118,36
    if pointInRect(mx,my,earBx,earBy,earBw,earBh):
        app.show_globe=not app.show_globe
        return
    if app.show_globe:
        closeBx,closeBy,closeBw,closeBh=W-52,HEADER_H+8,36,26
        if pointInRect(mx,my,closeBx,closeBy,closeBw,closeBh):
            app.show_globe=False
            return
        return
    for bid,b in app.buttons.items():
        if b["x"]<=mx<=b["x"]+b["w"] and b["y"]<=my<=b["y"]+b["h"] and b["enabled"]:
            if bid=="live": aio.run(load_live_geomag(app))
            elif bid=="globe": app.show_globe=not app.show_globe
            elif bid=="play":
                if app.is_playing: stop_sonification(app)
                else: play_kp_sonification(app)
                b["label"]="STOP" if app.is_playing else "PLAY"
            elif bid=="cache": cache_now(app)
            elif bid=="clear": clear_cache(app)
            return
    if pointInRect(mx,my,DRIFT_X+14,DRIFT_Y+DRIFT_H-22,DRIFT_W-28,24):
        app.dragging_year=True; update_year_from_x(app,mx); return
    if pointInRect(mx,my,MAG_X+14,MAG_Y+MAG_H-52,MAG_W-28,24):
        app.dragging_kp=True; update_kp_from_x(app,mx); return
    if pointInRect(mx,my,MAG_X+14,MAG_Y+MAG_H-22,MAG_W-28,24):
        app.dragging_sw=True; update_sw_from_x(app,mx); return
    if pointInRect(mx,my,DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H):
        app.dipole_tilt=11+3*math.sin(app.time*2); app.insight=f"Dynamo tilt {app.dipole_tilt:.1f}deg - cached"; aio.run(compute_with_pyodide(app))
    if pointInRect(mx,my,MAG_X,MAG_Y,MAG_W,MAG_H):
        app.imf_bz=-app.imf_bz; app.insight=f"Bz {app.imf_bz:+.1f}nT {'southward reconnection' if app.imf_bz<0 else 'northward quiet'}"

def update_year_from_x(app,mx):
    t=clamp((mx-(DRIFT_X+14))/(DRIFT_W-28),0,1); app.year=int(1800+t*225); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year); app.dipole_tilt=11.5-(app.year-1800)*0.003; aio.run(compute_with_pyodide(app))
def update_kp_from_x(app,mx):
    t=clamp((mx-(MAG_X+14))/(MAG_W-28),0,1); app.kp_slider=t*9
    if app.is_playing: play_kp_sonification(app)
def update_sw_from_x(app,mx):
    t=clamp((mx-(MAG_X+14))/(MAG_W-28),0,1); app.solar_wind_speed=300+t*500

def onMouseDrag(app,mx,my):
    if app.dragging_year: update_year_from_x(app,mx)
    if app.dragging_kp: update_kp_from_x(app,mx)
    if app.dragging_sw: update_sw_from_x(app,mx)
def onMouseRelease(app,mx,my): app.dragging_year=False; app.dragging_kp=False; app.dragging_sw=False
def onMouseMove(app,mx,my):
    app.hover=None
    for bid,b in app.buttons.items():
        if b["x"]<=mx<=b["x"]+b["w"] and b["y"]<=my<=b["y"]+b["h"]: app.hover=bid
    if pointInRect(mx,my,DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H): app.hover_panel="dynamo"
    elif pointInRect(mx,my,DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H): app.hover_panel="drift"
    elif pointInRect(mx,my,MAG_X,MAG_Y,MAG_W,MAG_H): app.hover_panel="mag"
    elif pointInRect(mx,my,IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H): app.hover_panel="impact"
    else: app.hover_panel=None
    app.hoverEar=pointInRect(mx,my,W-132,10,118,36)
def onKeyPress(app,key):
    if key.lower()=='g': app.show_globe=not app.show_globe
    elif key==' ':
        if app.is_playing: stop_sonification(app)
        else: play_kp_sonification(app)
        app.buttons["play"]["label"]="STOP" if app.is_playing else "PLAY"
    elif key.lower()=='r': aio.run(load_live_geomag(app))
    elif key.lower()=='t': app.year=clamp(app.year+1,1800,2025); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year); aio.run(compute_with_pyodide(app))
    elif key.lower()=='e': app.year=clamp(app.year-1,1800,2025); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year); aio.run(compute_with_pyodide(app))

def drawPanel(x,y,w,h,title=""):
    drawRect(x,y,w,h,fill=PANEL_BG,border=PANEL_BORDER,borderWidth=1,roundness=10)
    if title:
        drawRect(x+8,y+6,w-16,16,fill=rgb(28,32,52),roundness=5)
        drawLabel(title,x+14,y+14,fill=rgb(180,190,220),size=12,bold=True,align="left-top")
def draw_button(b,hover,enabled):
    x,y,w,h=b["x"],b["y"],b["w"],b["h"]
    if not enabled: fill=rgb(48,52,72); bc=rgb(68,74,102); tc=DIM
    else: fill=ACC_H if hover else ACC; bc=rgb(130,134,255) if hover else ACC; tc=rgb(255,255,255)
    drawRect(x,y,w,h,fill=fill,border=bc,borderWidth=1,roundness=9)
    drawLabel(b["label"],x+w/2,y+h/2,size=12,fill=tc,bold=True)

def drawHeader(app):
    drawRect(0,0,W,HEADER_H,fill=rgb(18,22,38))
    drawLabel("EMF LAB — Dynamo, Drift & Impact — SIGMA 60FPS",W*0.5,12,fill=TXT,size=14,bold=True,align="center-top")
    drawLabel(f"{app.year} M {app.dipole_moment:.2f}e22 Pole {app.pole_lat:.1f}N {app.pole_lon:.1f}E Tilt {app.dipole_tilt:.1f}deg Kp {app.kp_live:.1f}/{app.kp_slider:.1f} SW {int(app.solar_wind_speed)}",W*0.5,32,fill=DIM,size=12,align="center-top")
    drawRect(12,50,W-140,16,fill=rgb(35,60,85),border=CYAN,borderWidth=1,roundness=6,opacity=0.9)
    drawLabel(app.insight,W*0.5-60,58,fill=rgb(200,240,255),size=12,bold=True,align="center")
    bx,by,bw,bh=W-132,10,118,36
    hover=getattr(app,'hoverEar',False)
    fillCol=rgb(160,120,255) if not hover else rgb(190,150,255)
    if getattr(app,'show_globe',False): fillCol=rgb(255,180,120)
    drawRect(bx,by,bw,bh,fill=fillCol,border=rgb(255,255,255),borderWidth=1.5,roundness=18)
    drawLabel("GLOBE VIEW",bx+bw/2,by+bh/2,fill=rgb(0,0,0),size=12,bold=True,align="center")

def drawDynamo(app):
    drawPanel(DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H,"DYNAMO CORE - cached field lines")
    gx,gy,gw,gh=DYNAMO_X+14,DYNAMO_Y+34,DYNAMO_W-28,DYNAMO_H-52
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    cx=gx+gw*0.38; cy=gy+gh*0.52; earth_r=92
    drawCircle(cx,cy,earth_r,fill=rgb(45,35,25),border=rgb(80,60,40),borderWidth=1)
    outer_r=earth_r*0.55; drawCircle(cx,cy,outer_r,fill=rgb(200,90,20),border=rgb(255,160,80),borderWidth=1.2)
    for k in range(6):
        ang=k*60+app.time*18; rad=outer_r*0.62; x=cx+rad*math.cos(math.radians(ang)); y=cy+rad*math.sin(math.radians(ang))*0.75
        ax=math.cos(math.radians(ang+90))*10; ay=math.sin(math.radians(ang+90))*7
        drawLine(x,y,x+ax,y+ay,fill=ORANGE,lineWidth=1.5,arrowEnd=True)
        drawCircle(x,y,3,fill=YELLOW,opacity=0.7)
    tilt=math.radians(app.dipole_tilt)
    for line in getattr(app,'field_lines',[]):
        pts=[]
        for r,theta in line:
            th=theta-tilt; px=cx+r*earth_r*0.85*math.sin(th); py=cy-r*earth_r*0.85*math.cos(th)*0.9
            if math.hypot(px-cx,py-cy)>earth_r*0.98 or abs(theta-math.pi/2)>0.6: pts.append((px,py))
        for i in range(len(pts)-1): drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=CYAN,lineWidth=1.6,opacity=0.7)
    drawLabel(f"alpha-omega {app.dipole_tilt:.1f}deg",gx+8,gy+gh-8,fill=DIM,size=12,align="left-bottom")

def drawDrift(app):
    drawPanel(DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H,"SECULAR 1800-2025 Pole Wander")
    gx,gy,gw,gh=DRIFT_X+14,DRIFT_Y+34,DRIFT_W-28,DRIFT_H-78
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    pcx=gx+gw*0.34; pcy=gy+gh*0.48; pr=78
    drawCircle(pcx,pcy,pr,fill=rgb(16,20,36),border=rgb(50,60,90),borderWidth=0.8)
    for r in [pr*0.33,pr*0.66]: drawCircle(pcx,pcy,r,fill=None,border=rgb(40,50,80),borderWidth=0.6,dashes=True)
    drawLine(pcx-pr,pcy,pcx+pr,pcy,fill=rgb(40,50,80),lineWidth=0.6,dashes=True)
    drawLine(pcx,pcy-pr,pcx,pcy+pr,fill=rgb(40,50,80),lineWidth=0.6,dashes=True)
    prev=None
    for y,lat,lon in N_POLE_HISTORY:
        r=(90-lat)/20*pr; th=math.radians(lon+90); x=pcx+r*math.cos(th); y_=pcy+r*math.sin(th)
        t=(y-1800)/225; col=rgb(int(lerp(80,255,t)),int(lerp(180,90,t)),int(lerp(255,80,t)))
        if prev: drawLine(prev[0],prev[1],x,y_,fill=col,lineWidth=2.2,opacity=0.85)
        drawCircle(x,y_,3.5,fill=col,border=rgb(0,0,0),borderWidth=0.8); prev=(x,y_)
        if y==app.year: drawCircle(x,y_,9,fill=col,opacity=0.25); drawCircle(x,y_,5.5,fill=YELLOW,border=rgb(255,255,255),borderWidth=1.2)
    sx=DRIFT_X+14; sy=DRIFT_Y+DRIFT_H-22; sw=DRIFT_W-28
    drawRect(sx,sy,sw,8,fill=rgb(30,35,55),border=BORDER,borderWidth=1,roundness=4)
    t=(app.year-1800)/225; drawRect(sx,sy,t*sw,8,fill=ORANGE,roundness=4); drawCircle(sx+t*sw,sy+4,8,fill=rgb(255,255,255),border=ORANGE,borderWidth=2)
    drawLabel(f"{app.log_fetch} | {app.log_pyodide}",gx+8,gy+gh-8,fill=DIM,size=12,align="left-bottom")

def drawMag(app):
    drawPanel(MAG_X,MAG_Y,MAG_W,MAG_H,f"MAGNETOSPHERE Kp {app.kp_slider:.1f} SW {int(app.solar_wind_speed)} Bz {app.imf_bz:+.1f}")
    gx,gy,gw,gh=MAG_X+14,MAG_Y+34,MAG_W-28,MAG_H-82
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    sun_x=gx+28; sun_y=gy+gh*0.5; drawCircle(sun_x,sun_y,18,fill=rgb(255,220,80),border=rgb(255,180,40),borderWidth=1.5)
    for i in range(6):
        ay=gy+20+i*(gh-40)/5+math.sin(app.time*2+i)*4; ax0=sun_x+22; ax1=gx+gw*0.28+(app.solar_wind_speed-300)/500*20
        drawLine(ax0,ay,ax1,ay,fill=rgb(200,200,180),lineWidth=1.2,arrowEnd=True,opacity=0.6)
    ex=gx+gw*0.45; ey=gy+gh*0.5; drawCircle(ex,ey,18,fill=rgb(80,140,255),border=rgb(255,255,255),borderWidth=1); drawCircle(ex,ey,6,fill=GREEN)
    tilt=math.radians(app.dipole_tilt); drawLine(ex,ey,ex+14*math.sin(tilt),ey-14*math.cos(tilt),fill=CYAN,lineWidth=1.5,arrowEnd=True)
    rmp=10*(400/app.solar_wind_speed)**0.33*(1-app.kp_slider*0.03); rmp_px=rmp*9
    drawArc(ex,ey,rmp_px,rmp_px*1.1,200,160,fill=None,border=CYAN,borderWidth=1.8,opacity=0.9)
    drawLabel(f"MP {rmp:.1f} Re",ex-rmp_px*0.7,ey-22,fill=CYAN,size=12,align="center-bottom")
    bs=rmp_px*1.35; drawArc(ex,ey,bs,bs*1.15,200,160,fill=None,border=rgb(180,180,200),borderWidth=1,dashes=True,opacity=0.6)
    tail_len=120+app.solar_wind_speed*0.12; drawRect(ex+8,ey-32,tail_len,64,fill=rgb(20,30,60),border=BORDER,borderWidth=1,roundness=0,opacity=0.5)
    for i in range(0,int(tail_len),18):
        x=ex+12+i+math.sin(app.time*3+i*0.2)*3; drawLine(x,ey,x+8,ey,fill=YELLOW,lineWidth=1,opacity=0.5)
    drawOval(ex,ey,38,26,fill=None,border=PINK,borderWidth=1.2,opacity=0.7); drawOval(ex,ey,56,38,fill=None,border=PURPLE,borderWidth=1.2,opacity=0.5)
    oval_colat=18+app.kp_slider*1.8+(-app.imf_bz if app.imf_bz<0 else 0)*0.8
    for side in [-1,1]:
        oy=ey+side*(22+oval_colat*0.6); ow=36-side*oval_colat*0.2
        drawArc(ex,oy,ow,10,0,360,fill=rgb(110,255,170),border=None,opacity=0.18+app.kp_slider*0.04)
        drawArc(ex,oy,ow,10,0,360,fill=None,border=GREEN,borderWidth=1,opacity=0.7)
    ksx=MAG_X+14; ksy=MAG_Y+MAG_H-52; ksw=MAG_W-28
    drawRect(ksx,ksy,ksw,8,fill=rgb(30,35,55),border=BORDER,borderWidth=1,roundness=4)
    tk=app.kp_slider/9; colk=GREEN if tk<0.44 else YELLOW if tk<0.66 else RED; drawRect(ksx,ksy,tk*ksw,8,fill=colk,roundness=4); drawCircle(ksx+tk*ksw,ksy+4,8,fill=rgb(255,255,255),border=colk,borderWidth=2)
    ssx=MAG_X+14; ssy=MAG_Y+MAG_H-22; ssw=MAG_W-28
    drawRect(ssx,ssy,ssw,8,fill=rgb(30,35,55),border=BORDER,borderWidth=1,roundness=4)
    tsw=(app.solar_wind_speed-300)/500; drawRect(ssx,ssy,tsw*ssw,8,fill=BLUE,roundness=4); drawCircle(ssx+tsw*ssw,ssy+4,8,fill=rgb(255,255,255),border=BLUE,borderWidth=2)

def drawImpact(app):
    drawPanel(IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H,"IMPACT — SAA, Navigation, Systems")
    gx,gy,gw,gh=IMPACT_X+14,IMPACT_Y+34,IMPACT_W-28,IMPACT_H-58
    drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=6)
    mx=gx+6; my=gy+8; mw=gw*0.58; mh=gh-16; drawRect(mx,my,mw,mh,fill=rgb(16,24,42),border=rgb(35,45,75),borderWidth=1,roundness=6)
    for lat in [-60,-30,0,30,60]:
        y=my+(80-lat)/160*mh; drawLine(mx,y,mx+mw,y,fill=rgb(35,45,75),lineWidth=0.5,dashes=True)
    for lon in [-120,-60,0,60,120]:
        x=mx+(lon+180)/360*mw; drawLine(x,my,x,my+mh,fill=rgb(35,45,75),lineWidth=0.5,dashes=True)
    saa_x=mx+(-50+180)/360*mw; saa_y=my+(80-(-26))/160*mh; saa_r=28+(8.6-app.dipole_moment)*12
    drawOval(saa_x,saa_y,saa_r*2.2,saa_r*1.4,fill=RED,opacity=0.18); drawOval(saa_x,saa_y,saa_r*1.6,saa_r,fill=RED,border=RED,borderWidth=1.2,opacity=0.7)
    drawLabel("SAA",saa_x,saa_y-2,fill=RED,size=12,bold=True,align="center")
    if app.decl_grid:
        for i in range(len(app.decl_grid)-1):
            for j in range(len(app.decl_grid[0])-1):
                if abs(app.decl_grid[i][j])<8:
                    x=mx+(j/36)*mw; y=my+(i/18)*mh; drawCircle(x,y,1.2,fill=YELLOW,opacity=0.7)
    for lat,lon,code in app.observatories:
        x=mx+(lon+180)/360*mw; y=my+(80-lat)/160*mh; drawCircle(x,y,2.2,fill=CYAN,border=rgb(0,0,0),borderWidth=0.6)
    px=gx+gw*0.62+8; py=gy+8; pw=gw*0.36-8; ph=mh*0.48; drawRect(px,py,pw,ph,fill=rgb(16,20,36),border=rgb(35,45,75),borderWidth=1,roundness=6)
    drawLabel("Power n",px+4,py+4,fill=DIM,size=12,align="left-top")
    maxp=max(app.power_spec) if max(app.power_spec)>0 else 1
    for i,p in enumerate(app.power_spec[:8]):
        bx=px+8+i*(pw-16)/8; bw=(pw-20)/8*0.7; bh=(p/maxp)*(ph-22); drawRect(bx,py+ph-8-bh,bw,bh,fill=PURPLE if i>0 else YELLOW,roundness=3); drawLabel(str(i+1),bx+bw/2,py+ph-2,fill=DIM,size=12,align="center-bottom")
    ix=gx+gw*0.62+8; iy=gy+ph+18; iw=gw*0.36-8; ih=mh-ph-18; drawRect(ix,iy,iw,ih,fill=rgb(16,20,36),border=rgb(35,45,75),borderWidth=1,roundness=6)
    impacts=[f"WMM err {app.year-2020}*0.2deg",f"True=Mag {app.decl_grid[9][18] if app.decl_grid else 5:+.1f}deg",f"SAA upset x{1.2+(8.6-app.dipole_moment):.1f}","GIC Kp>6","Aviation runway","Animals magnetoreception","Met: true north not mag"]
    for k,txt in enumerate(impacts):
        y=iy+8+k*13
        if y<iy+ih-4: drawLabel(txt,ix+6,y,fill=YELLOW if k==0 else DIM,size=12,align="left-top")
    drawLabel(f"{app.log_fetch2} {app.log_fetch3} | {app.log_audio}",gx+8,gy+gh-8,fill=rgb(130,150,180),size=12,align="left-bottom")

def drawGlobeOverlay(app):
    drawRect(0,0,W,H,fill=BG); drawRect(0,0,W,HEADER_H,fill=rgb(18,22,38))
    drawLabel("GLOBE VIEW — Compass Needles & Field — 60FPS",W*0.5,12,fill=TXT,size=14,bold=True,align="center-top")
    drawLabel("Dipole + IGRF non-dipole. Needles = declination. SAA = weak spot.",W*0.5,32,fill=DIM,size=12,align="center-top")
    bx,by,bw,bh=W-280,8,110,34; drawRect(bx,by,bw,bh,fill=rgb(255,180,120),border=rgb(255,255,255),borderWidth=1.2,roundness=18); drawLabel("GLOBE VIEW",bx+bw/2,by+bh/2,fill=rgb(0,0,0),size=12,bold=True,align="center")
    closeBx,closeBy,closeBw,closeBh=W-60,HEADER_H+8,36,26; drawRect(closeBx,closeBy,closeBw,closeBh,fill=rgb(60,70,90),border=rgb(200,210,230),borderWidth=1,roundness=7); drawLabel("X",closeBx+closeBw/2,closeBy+closeBh/2,fill=rgb(230,240,255),size=12,bold=True,align="center")
    gx,gy,gw,gh=16,HEADER_H+12,680,600; drawRect(gx,gy,gw,gh,fill=PANEL,border=BORDER,borderWidth=1,roundness=14)
    cx=gx+gw*0.48; cy=gy+gh*0.5; R=210; drawCircle(cx,cy,R,fill=rgb(20,35,60),border=rgb(60,80,110),borderWidth=1.5)
    for lat in [-60,-30,0,30,60]:
        ry=R*math.cos(math.radians(lat))*0.42; y=cy+R*math.sin(math.radians(lat))*0.42; drawOval(cx,y,R*1.8,ry*2,fill=None,border=rgb(50,70,100),borderWidth=0.6,dashes=True)
    tilt=math.radians(app.dipole_tilt+5*math.sin(app.time*0.5))
    for L in [1.6,2.0,2.5,3.2,4.0]:
        pts=[]
        for th_deg in range(12,168,4):
            th=math.radians(th_deg); r=L*(math.sin(th)**2)
            if r<1.05 or r>5: continue
            th2=th-tilt; x=cx+r*R*0.92*math.sin(th2); y=cy-r*R*0.92*math.cos(th2)*0.42
            if math.hypot(x-cx,(y-cy)/0.42)>R*1.02: pts.append((x,y))
        for i in range(len(pts)-1): drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=CYAN,lineWidth=1.4,opacity=0.65)
    if app.decl_grid:
        for i in range(0,18,3):
            for j in range(0,36,6):
                lat=80-i/18*160; lon=-180+j/36*360+app.globe_rot*20; th=math.radians(lon)
                if math.cos(th)<0: continue
                x=cx+R*math.cos(math.radians(lat))*math.sin(th)*0.9*0.85; y=cy+R*math.sin(math.radians(lat))*0.42*0.85
                decl=app.decl_grid[i][j]; ang=math.radians(decl)
                drawLine(x,y,x+8*math.sin(ang),y-8*math.cos(ang)*0.42,fill=RED,lineWidth=1.2,arrowEnd=True)
                drawLine(x,y,x-6*math.sin(ang),y+6*math.cos(ang)*0.42,fill=BLUE,lineWidth=1)
    saa_lat,saa_lon=-26,-50; th=math.radians(saa_lon+app.globe_rot*20); sx=cx+R*math.cos(math.radians(saa_lat))*math.sin(th)*0.9; sy=cy+R*math.sin(math.radians(saa_lat))*0.42
    if math.cos(th)>0: drawCircle(sx,sy,18,fill=RED,opacity=0.22); drawCircle(sx,sy,10,fill=RED,border=rgb(255,255,255),borderWidth=1,opacity=0.8); drawLabel("SAA low F",sx+14,sy,fill=RED,size=12,bold=True,align="left-center")
    for side in [1,-1]:
        oval_lat=75-app.kp_slider*1.2; ry=R*math.cos(math.radians(oval_lat))*0.42*0.3; y=cy+side*R*math.sin(math.radians(oval_lat))*0.42*0.92
        drawOval(cx,y,R*1.6,ry*2,fill=None,border=GREEN,borderWidth=1.5,opacity=0.6+app.kp_slider*0.05)
    plat,plon=app.pole_lat,app.pole_lon+app.globe_rot*20; th=math.radians(plon); px=cx+R*math.cos(math.radians(plat))*math.sin(th)*0.9; py=cy+R*math.sin(math.radians(plat))*0.42
    if math.cos(th)>-0.2: drawCircle(px,py,6,fill=YELLOW,border=rgb(255,255,255),borderWidth=1.5); drawLabel(f"NMP {app.year}",px+8,py,fill=YELLOW,size=12,bold=True,align="left-center")
    ix,iy,iw,ih=710,HEADER_H+12,324,180; drawRect(ix,iy,iw,ih,fill=PANEL,border=BORDER,borderWidth=1,roundness=10); drawLabel("DYNAMO THEORY",ix+12,iy+10,fill=TXT,size=12,bold=True,align="left-top")
    lines=["Outer core Fe ~4mm/s","Coriolis alpha-effect","Differential omega","Dipole 80% surface","West drift 0.2deg/yr","Reversals ~200kyr","Laschamp 42kya 5%","Decay 5%/century"]
    for k,l in enumerate(lines): drawLabel(l,ix+12,iy+28+k*16,fill=DIM,size=12,align="left-top")
    ex,ey,ew,eh=710,HEADER_H+204,324,180; drawRect(ex,ey,ew,eh,fill=PANEL,border=BORDER,borderWidth=1,roundness=10); drawLabel("EDUCATORS - SIGMA",ex+12,ey+10,fill=TXT,size=12,bold=True,align="left-top")
    edu=["True vs Mag 0-30deg","WMM2025 airports","Phones WMM+gyro","GPS not mag","Mag != weather","GIC affects sensors","Aurora Kp+Bz south","Field protects atmo"]
    for k,l in enumerate(edu): drawLabel(l,ex+12,ey+28+k*16,fill=DIM,size=12,align="left-top")
    dx,dy,dw,dh=710,HEADER_H+396,324,208; drawRect(dx,dy,dw,dh,fill=PANEL,border=BORDER,borderWidth=1,roundness=10); drawLabel("LIVE DATA SIGMA LOG",dx+12,dy+10,fill=TXT,size=12,bold=True,align="left-top")
    src=[f"Kp {app.kp_live:.1f} {app.log_fetch}",f"INTERMAG {app.log_fetch2[:32]}",f"Data.gov {app.log_fetch3[:30]}",f"Pyodide {app.log_pyodide[:32]}",f"NCEI {app.log_fetch4[:30]}",f"Audio {app.log_audio[:30]}","WMM2025 IGRF-14","Kp sonified"]
    for k,l in enumerate(src): drawLabel(l,dx+12,dy+28+k*18,fill=DIM,size=12,align="left-top")

def redrawAll(app):
    drawRect(0,0,W,H,fill=BG)
    drawHeader(app)
    if app.show_globe:
        drawGlobeOverlay(app)
    else:
        drawDynamo(app); drawDrift(app); drawMag(app); drawImpact(app)
    for bid in app.buttons:
        b=app.buttons[bid]
        draw_button(b, app.hover==bid, b["enabled"])
    drawRect(0,H-30,W,30,fill=rgb(18,20,32),border=GRID)
    drawLabel(f"{app.fetch_status} | {app.fetch_status2[:40]} | {app.pyodide_status[:40]} | {app.log_audio[:30]}",12,H-15,size=12,fill=DIM,align="left-center")
