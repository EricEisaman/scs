
from scs import *
from browser import aio, window, document
from extensions.file_loader import load_image, FileLoaderError
from extensions.pyodide import run_python
from extensions.proc_audio import AudioEngine
from extensions.fetch import fetch, fetch_json, fetch_text
import math, random, traceback

WIDTH=1050
HEIGHT=700
HEADER_H=64
DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H = 16,78,500,252
DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H = 534,78,500,252
MAG_X,MAG_Y,MAG_W,MAG_H = 16,350,500,336
IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H = 534,350,500,336

BG=rgb(10,14,26)
PANEL=rgb(28,31,48)
PANEL2=rgb(22,26,42)
BORDER=rgb(58,64,94)
ACC=rgb(99,102,241)
ACC_H=rgb(129,133,255)
ACC2=rgb(16,185,129)
TXT=rgb(236,240,255)
DIM=rgb(150,160,188)
GRID=rgb(44,50,76)
CYAN=rgb(88,240,255)
YELLOW=rgb(255,230,110)
GREEN=rgb(110,255,170)
ORANGE=rgb(255,160,80)
RED=rgb(255,90,90)
BLUE=rgb(110,180,255)
PINK=rgb(255,110,180)
PURPLE=rgb(160,120,255)

N_POLE_HISTORY = [(1800,70.2,-96.5),(1850,70.8,-96.0),(1900,71.0,-97.0),(1920,72.5,-98.0),(1940,74.0,-100.0),(1960,75.5,-100.5),(1970,76.5,-101.0),(1980,77.8,-102.5),(1990,79.0,-104.0),(2000,81.3,-110.5),(2005,83.2,-118.0),(2010,85.0,-132.8),(2015,86.3,160.0),(2020,86.4,164.0),(2025,86.1,150.0)]
MOMENT_HISTORY = [(1800,8.55),(1850,8.40),(1900,8.25),(1950,8.00),(1980,7.90),(2000,7.80),(2010,7.75),(2020,7.71),(2025,7.68)]

def lerp(a,b,t): return a+(b-a)*t
def clamp(v,lo,hi): return lo if v<lo else hi if v>hi else v
def interp_pole(year):
    for i in range(len(N_POLE_HISTORY)-1):
        y0,lat0,lon0 = N_POLE_HISTORY[i]
        y1,lat1,lon1 = N_POLE_HISTORY[i+1]
        if y0 <= year <= y1:
            t=(year-y0)/(y1-y0) if y1!=y0 else 0
            dlon=((lon1-lon0+540)%360)-180
            return lerp(lat0,lat1,t), lon0+dlon*t
    return N_POLE_HISTORY[-1][1], N_POLE_HISTORY[-1][2]
def interp_moment(year):
    for i in range(len(MOMENT_HISTORY)-1):
        y0,m0 = MOMENT_HISTORY[i]
        y1,m1 = MOMENT_HISTORY[i+1]
        if y0 <= year <= y1:
            return lerp(m0,m1,(year-y0)/(y1-y0))
    return MOMENT_HISTORY[-1][1]
def dipole_field_line(L,n=80):
    pts=[]
    for i in range(n):
        theta=math.pi*0.08+(math.pi*0.84)*i/(n-1)
        r=L*(math.sin(theta)**2)
        if r>0.2 and r<2.2: pts.append((r,theta))
    return pts

# --- SIGMA SOURCES: multi-URL like mlp.py, no fallback data, just log ---
SOURCES={
    "kp":[
        "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json",
        "https://api.allorigins.win/raw?url=https://services.swpc.noaa.gov/json/planetary_k_index_1m.json",
    ],
    "intermagnet":[
        "https://api.allorigins.win/raw?url=https://www.intermagnet.org/data_download.html",
        "https://corsproxy.io/?https://www.intermagnet.org/data_download.html",
        "https://www.intermagnet.org/data_download.html",
    ],
    "datagov":[
        "https://api.allorigins.win/raw?url=https://catalog.data.gov/api/3/action/package_show?id=data-on-the-earths-magnetic-field-and-its-secular-change-since-1800",
        "https://catalog.data.gov/api/3/action/package_show?id=data-on-the-earths-magnetic-field-and-its-secular-change-since-1800",
    ],
    "ncei":[
        "https://www.ncei.noaa.gov/products/geomagnetic-data",
        "https://api.allorigins.win/raw?url=https://www.ncei.noaa.gov/products/geomagnetic-data",
    ],
    "wmm":[
        "https://www.ngdc.noaa.gov/geomag/WMM/data/WMM2025/WMM2025.csv",
        "https://api.allorigins.win/raw?url=https://www.ngdc.noaa.gov/geomag/WMM/data/WMM2025/WMM2025.csv",
    ]
}

def _to_py(obj):
    try:
        if hasattr(obj, "to_py"):
            return obj.to_py()
    except:
        pass
    return obj

def _js_get(obj, key, default=None):
    try:
        if obj is None: return default
        obj = _to_py(obj)
        if isinstance(obj, dict):
            return obj.get(key, default)
        try:
            g=getattr(obj, 'get', None)
            if callable(g):
                return g(key, default)
        except: pass
        try:
            return obj[key]
        except: pass
        try:
            return getattr(obj, key)
        except: pass
        return default
    except Exception as e:
        print(f"_js_get {key} failed {e}")
        return default

async def fetch_json_popular(urls, label):
    last_err=None
    for url in urls:
        try:
            resp=await window.fetch(url)
            if not resp.ok:
                raise Exception(f"HTTP {resp.status} {url}")
            data=await resp.json()
            data=_to_py(data)
            # handle nested result wrappers (data.gov)
            if isinstance(data, dict) and "result" in data and label=="datagov":
                # keep wrapper, caller will unwrap
                pass
            return data
        except Exception as e:
            last_err=e
            print(f"fetch_json_popular {label} {url} failed {e}")
            continue
    raise Exception(f"All sources failed for {label}: {last_err}")

async def fetch_text_popular(urls, label):
    last_err=None
    for url in urls:
        try:
            resp=await window.fetch(url)
            if not resp.ok:
                raise Exception(f"HTTP {resp.status} {url}")
            txt=await resp.text()
            txt=str(txt)
            if len(txt)<10:
                raise Exception("Too short")
            return txt
        except Exception as e:
            last_err=e
            print(f"fetch_text_popular {label} {url} failed {e}")
            continue
    raise Exception(f"All sources failed for {label}: {last_err}")

# --- Pyodide: must use extensions.pyodide, install numpy via micropip ---
PYODIDE_CODE = """
import micropip
await micropip.install("numpy")
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
    try:
        app.pyodide_status="Pyodide computing..."
        code=f"year={app.year}\nmoment={app.dipole_moment}\npole_lat={app.pole_lat}\npole_lon={app.pole_lon}\n"+PYODIDE_CODE
        result=await run_python(code)
        result=_to_py(result)
        app.decl_grid=result.get('declination') if isinstance(result, dict) else None
        app.power_spec=result.get('power_spectrum') if isinstance(result, dict) else [1,0.7,0.5,0.35,0.22,0.15,0.1,0.06]
        if app.decl_grid:
            app.pyodide_status=f"pyodide OK {len(app.decl_grid)}x{len(app.decl_grid[0])} - micropip numpy"
            app.log_pyodide=app.pyodide_status
        else:
            app.pyodide_status="pyodide empty result"
            app.log_pyodide=app.pyodide_status
    except Exception as e:
        app.pyodide_status=f"run_python failed: {e}"
        app.log_pyodide=app.pyodide_status
        print(f"run_python failed: {e}\n{traceback.format_exc()}")

async def load_live_geomag(app):
    # Direct use of extensions.fetch + window.fetch multi-source - log only, no fallbacks
    # 1. Kp - uses window.fetch via fetch_json_popular (like mlp.py fetch_bytes_popular)
    try:
        app.fetch_status="Fetching SWPC Kp..."
        kp_data=await fetch_json_popular(SOURCES["kp"], "kp")
        kp_data=_to_py(kp_data)
        if isinstance(kp_data, list) and len(kp_data)>0:
            latest=kp_data[-1]
            kp_raw=_js_get(latest,'Kp',3)
            # Kp can be "3o", "2+", extract number
            try:
                s=str(kp_raw)
                num=''.join([c for c in s if c.isdigit() or c=='.'])
                app.kp_live=float(num) if num else 3.0
            except:
                app.kp_live=3.0
            # history last 60
            hist=[]
            try:
                n=len(kp_data)
                for i in range(max(0,n-60), n):
                    it=kp_data[i]
                    v=_js_get(it,'Kp',0)
                    s=str(v)
                    num=''.join([c for c in s if c.isdigit() or c=='.'])
                    hist.append(float(num) if num else 0.0)
                if hist:
                    app.kp_history=hist
            except Exception as e2:
                print(f"Kp hist parse {e2}")
            app.log_fetch=f"Kp OK {app.kp_live:.1f} via window.fetch"
            app.fetch_status=app.log_fetch
        else:
            raise Exception("Kp not list")
    except Exception as e:
        app.log_fetch=f"fetch_json Kp failed: {e}"
        app.fetch_status=app.log_fetch
        print(f"fetch_json Kp failed: {e}")

    # 2. INTERMAGNET
    try:
        txt=await fetch_text_popular(SOURCES["intermagnet"], "intermagnet")
        app.log_fetch2=f"INTERMAGNET OK {len(txt)} via allorigins"
        app.fetch_status2=app.log_fetch2
    except Exception as e:
        app.log_fetch2=f"fetch_text INTERMAGNET failed: {e}"
        app.fetch_status2=app.log_fetch2
        print(f"fetch_text INTERMAGNET failed: {e}")

    # 3. Data.gov
    try:
        meta=await fetch_json_popular(SOURCES["datagov"], "datagov")
        meta=_to_py(meta)
        title=""
        if isinstance(meta, dict):
            if "title" in meta:
                title=meta.get("title","")
            elif "result" in meta:
                res=_to_py(meta.get("result",{}))
                title=_js_get(res,'title','') if isinstance(res, dict) else ""
        app.log_fetch3=f"Data.gov OK {str(title)[:30]}"
        app.fetch_status3=app.log_fetch3
    except Exception as e:
        app.log_fetch3=f"fetch_json Data.gov failed: {e}"
        app.fetch_status3=app.log_fetch3
        print(f"fetch_json Data.gov failed: {e}")

    # 4. NCEI
    try:
        t=await fetch_text_popular(SOURCES["ncei"], "ncei")
        app.log_fetch4=f"fetch NCEI OK {len(t)}"
        app.fetch_status4=app.log_fetch4
    except Exception as e:
        app.log_fetch4=f"fetch NCEI failed: {e}"
        app.fetch_status4=app.log_fetch4
        print(f"fetch NCEI failed: {e}")

    aio.run(compute_with_pyodide(app))

def play_kp_sonification(app):
    try:
        try:
            if hasattr(app.audio_engine,'resume'):
                app.audio_engine.resume()
        except Exception as e:
            print(f"AudioEngine resume failed: {e}")
        base=55+app.kp_live*18+app.kp_slider*10
        # Sigma sonification: Kp 0-9 -> 55-220Hz drone + pulse = whistler
        app.audio_engine.play("magnetosphere.ambient",seed=int(base),spatial=False)
        app.audio_engine.play("magnetosphere.pulse",seed=int(app.solar_wind_speed+app.kp_slider*10))
        app.audio_engine.play("ui.sweep",seed=int(app.kp_live*20+app.year%100))
        app.is_playing=True
        app.log_audio=f"AudioEngine play OK Kp {app.kp_slider:.1f} seed {int(base)}"
    except Exception as e:
        app.log_audio=f"AudioEngine failed: {e}"
        print(f"AudioEngine failed: {e}\n{traceback.format_exc()}")

def stop_sonification(app):
    try:
        if hasattr(app.audio_engine,'stop'):
            app.audio_engine.stop()
        elif hasattr(app.audio_engine,'stop_all'):
            app.audio_engine.stop_all()
        elif hasattr(app.audio_engine,'pause'):
            app.audio_engine.pause()
        else:
            print("AudioEngine no stop method - flag only")
        app.is_playing=False
        app.log_audio="AudioEngine stop OK - sigma stop"
    except Exception as e:
        app.log_audio=f"AudioEngine stop failed: {e}"
        print(f"AudioEngine stop failed: {e}")

CACHE_KEY="emf_sigma_cache_v2"

def try_load_cached(app):
    try:
        raw=window.localStorage.getItem(CACHE_KEY)
        if raw is None: return False
        data=window.JSON.parse(raw)
        data=_to_py(data)
        if not isinstance(data, dict): return False
        app.decl_grid=data.get("decl_grid")
        app.power_spec=data.get("power_spec",[1,0.7,0.5,0.35,0.22,0.15,0.1,0.06])
        app.year=int(data.get("year",2025))
        app.pole_lat,app.pole_lon=interp_pole(app.year)
        app.dipole_moment=interp_moment(app.year)
        app.log_pyodide=f"Cache hit {app.year}"
        return True
    except Exception as e:
        print(f"Cache load failed {e}")
        return False

def cache_now(app):
    try:
        if app.decl_grid is None: return False
        payload={"decl_grid":app.decl_grid,"power_spec":app.power_spec,"year":app.year}
        jstr=window.JSON.stringify(payload)
        window.localStorage.setItem(CACHE_KEY, jstr)
        app.fetch_status=f"Cached {len(jstr)//1024}KB"
        return True
    except Exception as e:
        print(f"Cache failed {e}")
        return False

def clear_cache(app):
    try:
        window.localStorage.removeItem(CACHE_KEY)
        app.decl_grid=None
        app.fetch_status="Cache cleared - sigma reset"
        return True
    except Exception as e:
        print(f"Clear cache failed {e}")
        return False

def onAppStart(app):
    app.width=WIDTH; app.height=HEIGHT; app.stepsPerSecond=20
    app.background=gradient(rgb(10,12,20), rgb(26,30,50), start="top")
    app.year=2025; app.dipole_tilt=10.5; app.dipole_moment=interp_moment(2025); app.pole_lat,app.pole_lon=interp_pole(2025)
    app.kp_live=3.2; app.kp_slider=3.0; app.solar_wind_speed=420; app.imf_bz=-2.0
    app.log_fetch="Idle"; app.log_fetch2=""; app.log_fetch3=""; app.log_fetch4=""; app.log_pyodide="Initializing micropip numpy"; app.log_audio="Idle"
    app.fetch_status="Ready - Click LIVE (4 fetches - FAST)"; app.fetch_status2=""; app.fetch_status3=""; app.fetch_status4=""; app.pyodide_status="Initializing"
    app.decl_grid=None; app.power_spec=[1,0.7,0.5,0.35,0.22,0.15,0.1,0.06]; app.kp_history=[random.uniform(0,4) for _ in range(60)]
    app.dragging_year=False; app.dragging_kp=False; app.dragging_sw=False; app.hover_panel=None; app.show_globe=False; app.globe_rot=0; app.is_playing=False; app.time=0
    app.insight="SIGMA LAB - Drag YEAR 1800-2025. Kp drives magnetosphere. SAA grows as dipole weakens."
    app.audio_engine=AudioEngine(quality="high",seed=90210)
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
    if app.is_playing and int(app.time*10)%50==0:
        try:
            app.audio_engine.play("magnetosphere.pulse",seed=int(app.solar_wind_speed+app.kp_slider*10))
        except Exception as e:
            print(f"onStep AudioEngine failed: {e}")

def pointInRect(px,py,rx,ry,rw,rh): return rx<=px<=rx+rw and ry<=py<=ry+rh

def onMousePress(app,mx,my):
    for bid,b in app.buttons.items():
        if b["x"]<=mx<=b["x"]+b["w"] and b["y"]<=my<=b["y"]+b["h"] and b["enabled"]:
            if bid=="live":
                aio.run(load_live_geomag(app))
            elif bid=="globe":
                app.show_globe=not app.show_globe
            elif bid=="play":
                if app.is_playing: stop_sonification(app)
                else: play_kp_sonification(app)
                b["label"]="STOP" if app.is_playing else "PLAY"
            elif bid=="cache":
                cache_now(app)
            elif bid=="clear":
                clear_cache(app)
            return
    if app.show_globe:
        if pointInRect(mx,my,WIDTH-60,HEADER_H+8,36,26):
            app.show_globe=False
        return
    if pointInRect(mx,my,DRIFT_X+14,DRIFT_Y+DRIFT_H-22,DRIFT_W-28,24):
        app.dragging_year=True; update_year_from_x(app,mx); return
    if pointInRect(mx,my,MAG_X+14,MAG_Y+MAG_H-52,MAG_W-28,24):
        app.dragging_kp=True; update_kp_from_x(app,mx); return
    if pointInRect(mx,my,MAG_X+14,MAG_Y+MAG_H-22,MAG_W-28,24):
        app.dragging_sw=True; update_sw_from_x(app,mx); return
    if pointInRect(mx,my,DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H):
        app.dipole_tilt=11+3*math.sin(app.time*2); app.insight=f"Dynamo tilt {app.dipole_tilt:.1f} deg - sigma alpha-omega"; aio.run(compute_with_pyodide(app))
    if pointInRect(mx,my,MAG_X,MAG_Y,MAG_W,MAG_H):
        app.imf_bz=-app.imf_bz; app.insight=f"Bz {app.imf_bz:+.1f}nT {'southward reconnection sigma' if app.imf_bz<0 else 'northward quiet'}"

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
        if b["x"]<=mx<=b["x"]+b["w"] and b["y"]<=my<=b["y"]+b["h"]:
            app.hover=bid
    if pointInRect(mx,my,DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H): app.hover_panel="dynamo"
    elif pointInRect(mx,my,DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H): app.hover_panel="drift"
    elif pointInRect(mx,my,MAG_X,MAG_Y,MAG_W,MAG_H): app.hover_panel="mag"
    elif pointInRect(mx,my,IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H): app.hover_panel="impact"
    else: app.hover_panel=None
def onKeyPress(app,key):
    if key.lower()=='g': app.show_globe=not app.show_globe
    elif key==' ':
        if app.is_playing: stop_sonification(app)
        else: play_kp_sonification(app)
        app.buttons["play"]["label"]="STOP" if app.is_playing else "PLAY"
    elif key.lower()=='r': aio.run(load_live_geomag(app))
    elif key.lower()=='t': app.year=clamp(app.year+1,1800,2025); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year); aio.run(compute_with_pyodide(app))
    elif key.lower()=='e': app.year=clamp(app.year-1,1800,2025); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year); aio.run(compute_with_pyodide(app))

def draw_panel(x,y,w,h,title=""):
    drawRect(x,y,w,h,fill=PANEL,border=BORDER,borderWidth=1,roundness=14,opacity=98)
    drawRect(x,y,w,34,fill=rgb(38,42,66),roundness=14)
    drawRect(x,y+17,w,17,fill=rgb(38,42,66))
    if title:
        drawLabel(title,x+16,y+17,size=13,fill=TXT,bold=True,align="left-center")
def draw_button(b,hover,enabled):
    x,y,w,h=b["x"],b["y"],b["w"],b["h"]
    if not enabled:
        fill=rgb(48,52,72); bc=rgb(68,74,102); tc=DIM
    else:
        fill=ACC_H if hover else ACC; bc=rgb(130,134,255) if hover else ACC; tc=rgb(255,255,255)
    drawRect(x,y,w,h,fill=fill,border=bc,borderWidth=1,roundness=9)
    drawLabel(b["label"],x+w/2,y+h/2,size=12,fill=tc,bold=True)

def drawHeader(app):
    drawRect(0,0,WIDTH,HEADER_H,fill=rgb(18,20,32))
    drawLabel("EMF LAB — Dynamo, Drift & Impact — SIGMA SCHOLAR",WIDTH*0.38,10,fill=TXT,size=15,bold=True,align="center-top")
    drawLabel(f"{app.year} M {app.dipole_moment:.2f}e22 Pole {app.pole_lat:.1f}N {app.pole_lon:.1f}E Tilt {app.dipole_tilt:.1f}deg Kp {app.kp_live:.1f}/{app.kp_slider:.1f} SW {int(app.solar_wind_speed)}",WIDTH*0.38,30,fill=DIM,size=10,align="center-top")
    drawRect(12,46,WIDTH-340,16,fill=rgb(35,60,85),border=CYAN,borderWidth=1,roundness=6,opacity=0.9)
    drawLabel(app.insight,WIDTH*0.5-160,54,fill=rgb(200,240,255),size=9.5,bold=True,align="center")

def drawDynamo(app):
    hl=app.hover_panel=="dynamo"
    draw_panel(DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H,title=f"DYNAMO CORE tilt {app.dipole_tilt:.1f} deg" + (" - HOVER" if hl else ""))
    gx,gy,gw,gh=DYNAMO_X+14,DYNAMO_Y+40,DYNAMO_W-28,DYNAMO_H-58
    drawRect(gx,gy,gw,gh,fill=PANEL2,border=BORDER,borderWidth=1,roundness=10)
    cx=gx+gw*0.38; cy=gy+gh*0.52; earth_r=92
    drawCircle(cx,cy,earth_r,fill=rgb(45,35,25),border=rgb(80,60,40),borderWidth=1)
    outer_r=earth_r*0.55; drawCircle(cx,cy,outer_r,fill=rgb(200,90,20),border=rgb(255,160,80),borderWidth=1.2)
    for k in range(6):
        ang=k*60+app.time*18; rad=outer_r*0.62; x=cx+rad*math.cos(math.radians(ang)); y=cy+rad*math.sin(math.radians(ang))*0.75
        ax=math.cos(math.radians(ang+90))*10; ay=math.sin(math.radians(ang+90))*7
        drawLine(x,y,x+ax,y+ay,fill=ORANGE,lineWidth=1.5,arrowEnd=True)
        drawCircle(x,y,3,fill=YELLOW,opacity=0.7)
    tilt=math.radians(app.dipole_tilt)
    for L in [1.4,1.8,2.3,3.0]:
        pts=[]; line=dipole_field_line(L,90)
        for r,theta in line:
            th=theta-tilt; px=cx+r*earth_r*0.85*math.sin(th); py=cy-r*earth_r*0.85*math.cos(th)*0.9
            if math.hypot(px-cx,py-cy)>earth_r*0.98 or abs(theta-math.pi/2)>0.6: pts.append((px,py))
        for i in range(len(pts)-1): drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=CYAN,lineWidth=1.6,opacity=0.7)

def drawDrift(app):
    hl=app.hover_panel=="drift"
    draw_panel(DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H,title="SECULAR 1800-2025 Pole Wander" + (" - SIGMA" if hl else ""))
    gx,gy,gw,gh=DRIFT_X+14,DRIFT_Y+40,DRIFT_W-28,DRIFT_H-78
    drawRect(gx,gy,gw,gh,fill=PANEL2,border=BORDER,borderWidth=1,roundness=10)
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
    drawLabel(f"{app.log_fetch} | {app.log_pyodide}",gx+8,gy+gh-8,fill=DIM,size=7,align="left-bottom")

def drawMag(app):
    hl=app.hover_panel=="mag"
    draw_panel(MAG_X,MAG_Y,MAG_W,MAG_H,title=f"MAGNETOSPHERE Kp {app.kp_slider:.1f} SW {int(app.solar_wind_speed)} Bz {app.imf_bz:+.1f}" + (" - SIGMA" if hl else ""))
    gx,gy,gw,gh=MAG_X+14,MAG_Y+40,MAG_W-28,MAG_H-82
    drawRect(gx,gy,gw,gh,fill=PANEL2,border=BORDER,borderWidth=1,roundness=10)
    sun_x=gx+28; sun_y=gy+gh*0.5; drawCircle(sun_x,sun_y,18,fill=rgb(255,220,80),border=rgb(255,180,40),borderWidth=1.5)
    for i in range(6):
        ay=gy+20+i*(gh-40)/5+math.sin(app.time*2+i)*4; ax0=sun_x+22; ax1=gx+gw*0.28+(app.solar_wind_speed-300)/500*20
        drawLine(ax0,ay,ax1,ay,fill=rgb(200,200,180),lineWidth=1.2,arrowEnd=True,opacity=0.6)
    ex=gx+gw*0.45; ey=gy+gh*0.5; drawCircle(ex,ey,18,fill=rgb(80,140,255),border=rgb(255,255,255),borderWidth=1); drawCircle(ex,ey,6,fill=GREEN)
    tilt=math.radians(app.dipole_tilt); drawLine(ex,ey,ex+14*math.sin(tilt),ey-14*math.cos(tilt),fill=CYAN,lineWidth=1.5,arrowEnd=True)
    rmp=10*(400/app.solar_wind_speed)**0.33*(1-app.kp_slider*0.03); rmp_px=rmp*9
    drawArc(ex,ey,rmp_px,rmp_px*1.1,200,160,fill=None,border=CYAN,borderWidth=1.8,opacity=0.9)
    drawLabel(f"MP {rmp:.1f} Re",ex-rmp_px*0.7,ey-22,fill=CYAN,size=8,align="center-bottom")
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
    hl=app.hover_panel=="impact"
    draw_panel(IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H,title="IMPACT — SAA, Navigation, Systems" + (" - SIGMA" if hl else ""))
    gx,gy,gw,gh=IMPACT_X+14,IMPACT_Y+40,IMPACT_W-28,IMPACT_H-58
    drawRect(gx,gy,gw,gh,fill=PANEL2,border=BORDER,borderWidth=1,roundness=10)
    mx=gx+6; my=gy+8; mw=gw*0.58; mh=gh-16; drawRect(mx,my,mw,mh,fill=rgb(16,24,42),border=rgb(35,45,75),borderWidth=1,roundness=6)
    for lat in [-60,-30,0,30,60]:
        y=my+(80-lat)/160*mh; drawLine(mx,y,mx+mw,y,fill=rgb(35,45,75),lineWidth=0.5,dashes=True)
    for lon in [-120,-60,0,60,120]:
        x=mx+(lon+180)/360*mw; drawLine(x,my,x,my+mh,fill=rgb(35,45,75),lineWidth=0.5,dashes=True)
    saa_x=mx+(-50+180)/360*mw; saa_y=my+(80-(-26))/160*mh; saa_r=28+(8.6-app.dipole_moment)*12
    drawOval(saa_x,saa_y,saa_r*2.2,saa_r*1.4,fill=RED,opacity=0.18); drawOval(saa_x,saa_y,saa_r*1.6,saa_r,fill=RED,border=RED,borderWidth=1.2,opacity=0.7)
    drawLabel("SAA",saa_x,saa_y-2,fill=RED,size=9,bold=True,align="center")
    if app.decl_grid:
        for i in range(len(app.decl_grid)-1):
            for j in range(len(app.decl_grid[0])-1):
                if abs(app.decl_grid[i][j])<8:
                    x=mx+(j/36)*mw; y=my+(i/18)*mh; drawCircle(x,y,1.2,fill=YELLOW,opacity=0.7)
    for lat,lon,code in app.observatories:
        x=mx+(lon+180)/360*mw; y=my+(80-lat)/160*mh; drawCircle(x,y,2.2,fill=CYAN,border=rgb(0,0,0),borderWidth=0.6)
    px=gx+gw*0.62+8; py=gy+8; pw=gw*0.36-8; ph=mh*0.48; drawRect(px,py,pw,ph,fill=rgb(16,20,36),border=rgb(35,45,75),borderWidth=1,roundness=6)
    drawLabel("Power n",px+4,py+4,fill=DIM,size=8,align="left-top")
    maxp=max(app.power_spec) if max(app.power_spec)>0 else 1
    for i,p in enumerate(app.power_spec[:8]):
        bx=px+8+i*(pw-16)/8; bw=(pw-20)/8*0.7; bh=(p/maxp)*(ph-22); drawRect(bx,py+ph-8-bh,bw,bh,fill=PURPLE if i>0 else YELLOW,roundness=3); drawLabel(str(i+1),bx+bw/2,py+ph-2,fill=DIM,size=7,align="center-bottom")
    ix=gx+gw*0.62+8; iy=gy+ph+18; iw=gw*0.36-8; ih=mh-ph-18; drawRect(ix,iy,iw,ih,fill=rgb(16,20,36),border=rgb(35,45,75),borderWidth=1,roundness=6)
    impacts=[f"WMM err {app.year-2020}*0.2deg",f"True=Mag {app.decl_grid[9][18] if app.decl_grid else 5:+.1f}deg",f"SAA upset x{1.2+(8.6-app.dipole_moment):.1f}","GIC Kp>6","Aviation runway","Animals magnetoreception","Met: true north not mag"]
    for k,txt in enumerate(impacts):
        y=iy+8+k*13
        if y<iy+ih-4: drawLabel(txt,ix+6,y,fill=YELLOW if k==0 else DIM,size=7.5,align="left-top")
    drawLabel(f"{app.log_fetch2} {app.log_fetch3} {app.log_fetch4} | {app.log_audio}",gx+8,gy+gh-8,fill=rgb(130,150,180),size=7,align="left-bottom")

def drawGlobeOverlay(app):
    drawRect(0,0,WIDTH,HEIGHT,fill=BG); drawRect(0,0,WIDTH,HEADER_H,fill=rgb(18,20,32))
    drawLabel("GLOBE VIEW — Compass Needles & Field — SIGMA SCHOLAR",WIDTH*0.5,12,fill=TXT,size=16,bold=True,align="center-top")
    drawLabel("Dipole + IGRF non-dipole. Needles = local declination. SAA = weak spot. Sigma not skibidi.",WIDTH*0.5,32,fill=DIM,size=11,align="center-top")
    bx,by,bw,bh=WIDTH-280,8,110,34
    drawRect(bx,by,bw,bh,fill=rgb(255,180,120),border=rgb(255,255,255),borderWidth=1.2,roundness=18); drawLabel("GLOBE VIEW",bx+bw/2,by+bh/2,fill=rgb(0,0,0),size=11,bold=True,align="center")
    closeBx,closeBy,closeBw,closeBh=WIDTH-60,HEADER_H+8,36,26; drawRect(closeBx,closeBy,closeBw,closeBh,fill=rgb(60,70,90),border=rgb(200,210,230),borderWidth=1,roundness=7); drawLabel("X",closeBx+closeBw/2,closeBy+closeBh/2,fill=rgb(230,240,255),size=13,bold=True,align="center")
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
    if math.cos(th)>0: drawCircle(sx,sy,18,fill=RED,opacity=0.22); drawCircle(sx,sy,10,fill=RED,border=rgb(255,255,255),borderWidth=1,opacity=0.8); drawLabel("SAA low F",sx+14,sy,fill=RED,size=9,bold=True,align="left-center")
    for side in [1,-1]:
        oval_lat=75-app.kp_slider*1.2; ry=R*math.cos(math.radians(oval_lat))*0.42*0.3; y=cy+side*R*math.sin(math.radians(oval_lat))*0.42*0.92
        drawOval(cx,y,R*1.6,ry*2,fill=None,border=GREEN,borderWidth=1.5,opacity=0.6+app.kp_slider*0.05)
    plat,plon=app.pole_lat,app.pole_lon+app.globe_rot*20; th=math.radians(plon); px=cx+R*math.cos(math.radians(plat))*math.sin(th)*0.9; py=cy+R*math.sin(math.radians(plat))*0.42
    if math.cos(th)>-0.2: drawCircle(px,py,6,fill=YELLOW,border=rgb(255,255,255),borderWidth=1.5); drawLabel(f"NMP {app.year}",px+8,py,fill=YELLOW,size=9,bold=True,align="left-center")
    ix,iy,iw,ih=710,HEADER_H+12,324,180; drawRect(ix,iy,iw,ih,fill=PANEL,border=BORDER,borderWidth=1,roundness=10); drawLabel("DYNAMO THEORY - SIGMA",ix+12,iy+10,fill=TXT,size=10,bold=True,align="left-top")
    lines=["Outer core liquid Fe convects ~4mm/s","Coriolis → helicity, alpha-effect","Differential rotation → omega-effect","Dipole ~80% surface, 20% non-dipole","Westward drift 0.2°/yr - sigma grind","Reversals every ~200kyr, last 780kya","Excursions: Laschamp 42kya field 5%","Current decay 5%/century sigma decay"]
    for k,l in enumerate(lines): drawLabel(l,ix+12,iy+28+k*16,fill=DIM,size=9,align="left-top")
    ex,ey,ew,eh=710,HEADER_H+204,324,180; drawRect(ex,ey,ew,eh,fill=PANEL,border=BORDER,borderWidth=1,roundness=10); drawLabel("FOR EDUCATORS - SIGMA NOT SKIBIDI",ex+12,ey+10,fill=TXT,size=10,bold=True,align="left-top")
    edu=["True vs Magnetic: 0-30° error","WMM2025 vs WMM2020: airports renumber","Phones use WMM + gyro - sigma compass","Weather balloons: GPS not mag","Magnetosphere ≠ troposphere","But GIC affects met sensors, power","Aurora = Kp + Bz south - sigma lights","Teach: field protects atmosphere"]
    for k,l in enumerate(edu): drawLabel(l,ex+12,ey+28+k*16,fill=DIM,size=9,align="left-top")
    dx,dy,dw,dh=710,HEADER_H+396,324,208; drawRect(dx,dy,dw,dh,fill=PANEL,border=BORDER,borderWidth=1,roundness=10); drawLabel("LIVE DATA & SOURCES - SIGMA LOG ONLY",dx+12,dy+10,fill=TXT,size=10,bold=True,align="left-top")
    src=[f"SWPC Kp {app.kp_live:.1f} {app.log_fetch}",f"INTERMAGNET {app.log_fetch2[:32]}",f"Data.gov {app.log_fetch3[:30]}",f"Pyodide {app.log_pyodide[:32]}",f"NCEI {app.log_fetch4[:30]}",f"Audio {app.log_audio[:30]}","WMM2025, IGRF-14, gufm1 1800-","Procaudio: Kp sonified sigma drone"]
    for k,l in enumerate(src): drawLabel(l,dx+12,dy+28+k*18,fill=DIM,size=8.5,align="left-top")

def redrawAll(app):
    drawRect(0,0,WIDTH,HEIGHT,fill=BG)
    drawHeader(app)
    if app.show_globe:
        drawGlobeOverlay(app)
    else:
        drawDynamo(app); drawDrift(app); drawMag(app); drawImpact(app)
    for bid in app.buttons:
        b=app.buttons[bid]
        draw_button(b, app.hover==bid, b["enabled"])
    drawRect(0,HEIGHT-30,WIDTH,30,fill=rgb(18,20,32),border=GRID)
    drawLabel(f"{app.fetch_status} | {app.fetch_status2[:40]} | {app.pyodide_status[:40]} | {app.log_audio[:30]}",12,HEIGHT-15,size=9,fill=DIM,align="left-center")
