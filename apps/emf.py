"""
EMF Lab - RESTORED WORKING GRAPHS - 4 panels bulletproof
Matches working-past-state.png graphs exactly
Only 2 CORS * fetches, no bottom log spam, 3 buttons purple toggle
"""

from scs import *
from browser import window, aio
from extensions.proc_audio import AudioEngine
from extensions.fetch import fetch_json, fetch_text, fetch
from extensions.pyodide import run_python
import math, random

W,H = 1050,700
HEADER_H = 64
DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H = 16,78,500,252
DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H = 534,78,500,252
MAG_X,MAG_Y,MAG_W,MAG_H = 16,350,500,336
IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H = 534,350,500,336

BG = rgb(10,14,26)
PANEL_BG = rgb(18,22,38)
PANEL_BORDER = rgb(45,55,85)
CYAN = rgb(88,240,255)
PINK = rgb(255,110,180)
YELLOW = rgb(255,230,110)
GREEN = rgb(110,255,170)
PURPLE = rgb(160,120,255)
ORANGE = rgb(255,160,80)
RED = rgb(255,90,90)
BLUE = rgb(110,180,255)

N_POLE_HISTORY = [(1800,70.2,-96.5),(1850,70.8,-96.0),(1900,71.0,-97.0),(1920,72.5,-98.0),(1940,74.0,-100.0),(1960,75.5,-100.5),(1970,76.5,-101.0),(1980,77.8,-102.5),(1990,79.0,-104.0),(2000,81.3,-110.5),(2005,83.2,-118.0),(2010,85.0,-132.8),(2015,86.3,160.0),(2020,86.4,164.0),(2025,86.1,150.0)]
MOMENT_HISTORY = [(1800,8.55),(1850,8.40),(1900,8.25),(1950,8.00),(1980,7.90),(2000,7.80),(2010,7.75),(2020,7.71),(2025,7.68)]

def lerp(a,b,t): return a+(b-a)*t
def clamp(v,lo,hi): return lo if v<lo else hi if v>hi else v

def interp_pole(year):
    for i in range(len(N_POLE_HISTORY)-1):
        y0,lat0,lon0 = N_POLE_HISTORY[i]
        y1,lat1,lon1 = N_POLE_HISTORY[i+1]
        if y0 <= year <= y1:
            t = (year-y0)/(y1-y0) if y1!=y0 else 0
            dlon = ((lon1-lon0+540)%360)-180
            return lerp(lat0,lat1,t), lon0 + dlon*t
    return N_POLE_HISTORY[-1][1], N_POLE_HISTORY[-1][2]

def interp_moment(year):
    for i in range(len(MOMENT_HISTORY)-1):
        y0,m0 = MOMENT_HISTORY[i]
        y1,m1 = MOMENT_HISTORY[i+1]
        if y0 <= year <= y1:
            return lerp(m0,m1,(year-y0)/(y1-y0))
    return MOMENT_HISTORY[-1][1]

def dipole_field_line(L, n=80):
    pts=[]
    for i in range(n):
        theta = 3.14159*0.08 + (3.14159*0.84)*i/(n-1)
        r = L * (math.sin(theta)**2)
        if r>0.2 and r<2.2:
            pts.append((r,theta))
    return pts

def to_py_safe(x):
    # Convert JsProxy to python recursively
    try:
        if hasattr(x, 'to_py'):
            x = x.to_py()
    except:
        pass
    if isinstance(x, list):
        out=[]
        for v in x:
            try:
                if hasattr(v, 'to_py'): v = v.to_py()
            except: pass
            out.append(v)
        return out
    return x

PYODIDE_PRELOAD = """
try:
    import numpy
except:
    try:
        import pyodide_js
        await pyodide_js.loadPackage("numpy")
    except:
        pass
import numpy as np
"numpy ready"
"""

PYODIDE_CODE = """
import numpy as np
year = globals().get('year', 2025)
tilt = np.deg2rad(globals().get('tilt_deg', 11.0))
moment = globals().get('moment', 7.7)
lats = np.linspace(-80,80,18)
lons = np.linspace(-180,180,36)
decl = np.zeros((len(lats), len(lons)))
pole_lat = np.deg2rad(globals().get('pole_lat', 86.1))
pole_lon = np.deg2rad(globals().get('pole_lon', 150.0))
drift = (year-1800)*0.2
for i, lat in enumerate(lats):
    latr = np.deg2rad(lat)
    for j, lon in enumerate(lons):
        lonr = np.deg2rad(lon)
        d = np.rad2deg(np.arctan2(np.sin(lonr-pole_lon)*np.cos(pole_lat), np.cos(latr)*np.sin(pole_lat) - np.sin(latr)*np.cos(pole_lat)*np.cos(lonr-pole_lon)))
        d += 8*np.sin(2*lonr + np.deg2rad(drift))*np.cos(latr)
        d += (7.7-moment)*3
        decl[i,j] = ((d+540)%360)-180
F = 30 + 25*np.abs(np.sin(lats)[:,None])
degrees = np.arange(1,9)
power = moment**2 * (0.9**degrees) / degrees
{'declination': decl.tolist(), 'intensity': F.tolist(), 'power_spectrum': power.tolist()}
"""

async def load_live_geomag(app):
    app.fetch_status = "Kp..."
    try:
        kp_data = await fetch_json('https://services.swpc.noaa.gov/json/planetary_k_index_1m.json')
        kp_data = to_py_safe(kp_data)
        if isinstance(kp_data, list) and len(kp_data)>0:
            latest = to_py_safe(kp_data[-1])
            raw = latest.get('Kp',3) if isinstance(latest, dict) else 3
            if isinstance(raw, str):
                try: raw = float(raw.strip().replace('o','').replace('+','').replace('-',''))
                except: raw = 3.0
            app.kp_live = float(raw)
            hist=[]
            for d in kp_data[-60:]:
                d = to_py_safe(d)
                if isinstance(d, dict):
                    try:
                        v = d.get('Kp',0)
                        if isinstance(v,str): v = float(v.strip().replace('o','').replace('+','').replace('-',''))
                        hist.append(float(v))
                    except: pass
            if len(hist)>5: app.kp_history = hist
            app.fetch_status = f"Kp OK {app.kp_live:.1f}"
    except Exception as e:
        app.fetch_status = f"Kp err {str(e)[:20]}"
        app.kp_live = 3.0

    app.fetch_status2 = "USGS..."
    try:
        obs = await fetch_json('https://geomag.usgs.gov/ws/observatories/?format=json')
        obs = to_py_safe(obs)
        if isinstance(obs, list):
            parsed=[]
            for o in obs[:20]:
                o = to_py_safe(o)
                if isinstance(o, dict):
                    try:
                        lat = float(o.get('lat',0) or o.get('latitude',0))
                        lon = float(o.get('lon',0) or o.get('longitude',0))
                        code = o.get('id','') or o.get('code','')
                        if lat and lon: parsed.append((lat,lon,code[:4]))
                    except: pass
            if parsed: app.observatories = parsed
            app.fetch_status2 = f"USGS OBS OK {len(app.observatories)}"
    except Exception as e:
        app.fetch_status2 = f"USGS {str(e)[:20]}"

    app.fetch_status3 = "USGS DATA disabled"
    aio.run(compute_with_pyodide(app))

async def compute_with_pyodide(app):
    app.pyodide_status = "Pyodide..."
    try:
        r = await run_python(PYODIDE_PRELOAD)
        r = to_py_safe(r)
        app.pyodide_status = f"preload {r}"
    except Exception as e:
        app.pyodide_status = f"preload err {str(e)[:20]}"
    code = f"year={app.year}\ntilt_deg={app.dipole_tilt}\nmoment={app.dipole_moment}\npole_lat={app.pole_lat}\npole_lon={app.pole_lon}\n" + PYODIDE_CODE
    try:
        result = await run_python(code)
        result = to_py_safe(result)
        if isinstance(result, dict):
            dg = to_py_safe(result.get('declination'))
            if isinstance(dg, list) and len(dg)>0:
                app.decl_grid = dg
                app.intensity_grid = to_py_safe(result.get('intensity'))
                app.power_spec = to_py_safe(result.get('power_spectrum', [1,0.8,0.6]))
                app.pyodide_status = f"Pyodide OK {len(app.decl_grid)}x{len(app.decl_grid[0])}"
    except Exception as e:
        app.pyodide_status = f"Pyodide {str(e)[:30]}"
        # keep fallback grid

def onAppStart(app):
    app.width=W; app.height=H; app.stepsPerSecond=30; app.background=BG
    app.year=2025; app.dipole_tilt=10.5; app.dipole_moment=interp_moment(2025); app.pole_lat,app.pole_lon=interp_pole(2025)
    app.kp_live=3.0; app.kp_slider=3.0; app.solar_wind_speed=420; app.imf_bz=-2.0
    app.fetch_status="Idle"; app.fetch_status2=""; app.fetch_status3=""; app.pyodide_status="Init..."
    # FALLBACK GRID - ensures graphs never blank even if pyodide fails
    app.decl_grid=[[(j-18)*2 + 5*math.sin(i*0.5+j*0.2) for j in range(36)] for i in range(18)]
    app.intensity_grid=[[30+abs(i-9)*2 for j in range(36)] for i in range(18)]
    app.power_spec=[1,0.7,0.5,0.35,0.22,0.15,0.1,0.06]
    app.kp_history=[random.uniform(0,4) for _ in range(60)]
    app.dragging_year=False; app.dragging_kp=False; app.dragging_sw=False; app.hover_panel=None; app.show_globe=False; app.globe_rot=0; app.is_playing=False; app.time=0
    app.insight="Drag YEAR 1800-2025. Kp drives MP. Click MAG to flip Bz."
    try:
        app.audio_engine=AudioEngine(quality="high", seed=90210)
    except:
        app.audio_engine=None
    app.observatories=[(65.1,-19.6,"LRV"),(60.4,5.3,"DOB"),(58.7,-3.7,"LER"),(55.3,-3.2,"ESK"),(50.3,4.6,"DOU"),(52.0,-4.5,"ABK"),(40.3,-4.3,"SPT"),(36.9,-2.0,"SFS"),(28.0,-16.5,"GUI"),(64.7,-147.8,"CMO"),(47.6,-122.3,"NEW"),(38.2,-122.3,"FRN"),(-33.3,26.5,"HER"),(-23.2,-45.0,"VSS"),(-31.4,115.9,"GNG"),(35.6,140.2,"KAK"),(-43.7,172.3,"EYR")]
    aio.run(load_live_geomag(app))
    aio.run(compute_with_pyodide(app))

def onStep(app):
    app.time+=0.02; app.globe_rot+=0.008

def pointInRect(px,py,rx,ry,rw,rh): return rx<=px<=rx+rw and ry<=py<=ry+rh

def onMousePress(app,mx,my):
    if pointInRect(mx,my,W-280,8,110,34):
        app.show_globe=not app.show_globe; app.globe_rot=0; return
    if pointInRect(mx,my,W-156,8,70,34):
        if app.is_playing:
            try: app.audio_engine.stop()
            except: pass
            app.is_playing=False
        else:
            try:
                app.audio_engine.resume()
                base=55+app.kp_live*18+app.kp_slider*10
                app.audio_engine.play("magnetosphere.ambient", seed=int(base), spatial=False)
                app.is_playing=True
            except:
                try:
                    app.audio_engine.play("ambient.drone", seed=int(base))
                    app.is_playing=True
                except: pass
        return
    if pointInRect(mx,my,W-74,8,58,34):
        aio.run(load_live_geomag(app)); return
    if app.show_globe:
        if pointInRect(mx,my,W-60,HEADER_H+8,36,26): app.show_globe=False; return
        return
    if pointInRect(mx,my,DRIFT_X+14,DRIFT_Y+DRIFT_H-32,DRIFT_W-28,24):
        app.dragging_year=True; update_year_from_x(app,mx); return
    if pointInRect(mx,my,MAG_X+14,MAG_Y+MAG_H-62,MAG_W-28,24):
        app.dragging_kp=True; update_kp_from_x(app,mx); return
    if pointInRect(mx,my,MAG_X+14,MAG_Y+MAG_H-32,MAG_W-28,24):
        app.dragging_sw=True; update_sw_from_x(app,mx); return
    if pointInRect(mx,my,DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H):
        app.dipole_tilt=11+3*math.sin(app.time*2); aio.run(compute_with_pyodide(app))
    if pointInRect(mx,my,MAG_X,MAG_Y,MAG_W,MAG_H): app.imf_bz=-app.imf_bz

def update_year_from_x(app,mx):
    sx=DRIFT_X+14; sw=DRIFT_W-28; t=clamp((mx-sx)/sw,0,1)
    app.year=int(1800+t*225); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year); app.dipole_tilt=11.5-(app.year-1800)*0.003
    aio.run(compute_with_pyodide(app))

def update_kp_from_x(app,mx):
    ksx=MAG_X+14; ksw=MAG_W-28; t=clamp((mx-ksx)/ksw,0,1); app.kp_slider=t*9
    if app.is_playing:
        try:
            base=55+app.kp_live*18+app.kp_slider*10
            app.audio_engine.play("magnetosphere.ambient", seed=int(base), spatial=False)
        except: pass

def update_sw_from_x(app,mx):
    ssx=MAG_X+14; ssw=MAG_W-28; t=clamp((mx-ssx)/ssw,0,1); app.solar_wind_speed=300+t*500

def onMouseDrag(app,mx,my):
    if app.dragging_year: update_year_from_x(app,mx)
    if app.dragging_kp: update_kp_from_x(app,mx)
    if app.dragging_sw: update_sw_from_x(app,mx)

def onMouseRelease(app,mx,my):
    app.dragging_year=False; app.dragging_kp=False; app.dragging_sw=False

def onMouseMove(app,mx,my):
    if pointInRect(mx,my,DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H): app.hover_panel="dynamo"
    elif pointInRect(mx,my,DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H): app.hover_panel="drift"
    elif pointInRect(mx,my,MAG_X,MAG_Y,MAG_W,MAG_H): app.hover_panel="mag"
    elif pointInRect(mx,my,IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H): app.hover_panel="impact"
    else: app.hover_panel=None

def onKeyPress(app,key):
    if key.lower()=='g': app.show_globe=not app.show_globe
    elif key==' ':
        if app.is_playing:
            try: app.audio_engine.stop()
            except: pass
            app.is_playing=False
        else:
            try:
                app.audio_engine.resume()
                base=55+app.kp_live*18+app.kp_slider*10
                app.audio_engine.play("magnetosphere.ambient", seed=int(base), spatial=False)
                app.is_playing=True
            except: pass
    elif key.lower()=='r': aio.run(load_live_geomag(app))

def drawPanel(x,y,w,h,title="", highlight=False):
    try:
        fill=PANEL_BG if not highlight else rgb(26,30,52)
        drawRect(x,y,w,h,fill=fill,border=PANEL_BORDER,borderWidth=1, roundness=10)
        if title:
            drawRect(x+8,y+6,w-16,16,fill=rgb(28,32,52),roundness=5)
            drawLabel(title, x+14, y+14, fill=rgb(180,190,220), size=11, bold=True, align="left-top")
    except: pass

def drawHeader(app):
    try:
        drawRect(0,0,W,HEADER_H, fill=rgb(18,22,38))
        drawLabel("EMF LAB — Dynamo, Drift & Impact", W*0.38, 10, fill=rgb(240,250,255), size=15, bold=True, align="center-top")
        drawLabel(f"{app.year} M {app.dipole_moment:.2f} Pole {app.pole_lat:.1f}N {app.pole_lon:.1f}E Tilt {app.dipole_tilt:.1f}° Kp {app.kp_live:.1f}/{app.kp_slider:.1f} SW {int(app.solar_wind_speed)} Bz {app.imf_bz:+.1f}", W*0.38, 30, fill=rgb(160,180,210), size=10, align="center-top")
        drawRect(12,46,W-340,16, fill=rgb(35,60,85), border=CYAN, borderWidth=1, roundness=6, opacity=0.9)
        drawLabel(app.insight, W*0.5-160, 54, fill=rgb(200,240,255), size=9.5, bold=True, align="center")
        is_globe=getattr(app,'show_globe',False)
        col=PURPLE if not is_globe else rgb(255,180,120)
        label="BACK TO LAB" if is_globe else "GLOBE VIEW"
        drawRect(W-280,8,110,34, fill=col, border=rgb(255,255,255), borderWidth=1.2, roundness=18)
        drawLabel(label, W-280+55, 8+17, fill=rgb(255,255,255) if is_globe else rgb(0,0,0), size=11, bold=True, align="center")
        drawRect(W-156,8,70,34, fill=rgb(90,255,160) if not getattr(app,'is_playing',False) else rgb(255,90,90), border=rgb(255,255,255), borderWidth=1.2, roundness=18)
        drawLabel("STOP" if getattr(app,'is_playing',False) else "PLAY", W-156+35, 8+17, fill=rgb(0,0,0), size=11, bold=True, align="center")
        drawRect(W-74,8,58,34, fill=rgb(45,55,85), border=PANEL_BORDER, borderWidth=1, roundness=18)
        drawLabel("LIVE", W-74+29, 8+17, fill=rgb(200,220,255), size=10, bold=True, align="center")
    except: pass

def drawMpArc(cx,cy,rx,ry, deg1, deg2, col, w=1.8):
    try:
        pts=[]
        for d in range(deg1, deg2+1, 3):
            th=math.radians(d)
            pts.append((cx+rx*math.cos(th), cy+ry*math.sin(th)*0.9))
        for i in range(len(pts)-1):
            drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1], fill=col, lineWidth=w)
    except: pass

def drawDynamo(app):
    try:
        hl=app.hover_panel=="dynamo"
        drawPanel(DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H, f"DYNAMO CORE — tilt {app.dipole_tilt:.1f}°", highlight=hl)
        gx,gy,gw,gh=DYNAMO_X+14,DYNAMO_Y+30,DYNAMO_W-28,DYNAMO_H-48
        drawRect(gx,gy,gw,gh, fill=rgb(12,16,30), border=rgb(35,45,75), borderWidth=1, roundness=8)
        cx=gx+gw*0.38; cy=gy+gh*0.52; earth_r=92
        drawCircle(cx,cy,earth_r, fill=rgb(45,35,25), border=rgb(80,60,40), borderWidth=1)
        drawCircle(cx,cy,earth_r*0.88, fill=rgb(60,45,30), border=None)
        drawCircle(cx,cy,earth_r*0.55, fill=rgb(200,90,20), border=rgb(255,160,80), borderWidth=1.2)
        for k in range(6):
            ang=k*60+app.time*18; rad=earth_r*0.55*0.62
            x=cx+rad*math.cos(math.radians(ang)); y=cy+rad*math.sin(math.radians(ang))*0.75
            try: drawLine(x,y,x+math.cos(math.radians(ang+90))*10,y+math.sin(math.radians(ang+90))*7, fill=ORANGE, lineWidth=1.5, arrowEnd=True)
            except: pass
        drawCircle(cx,cy,earth_r*0.20, fill=rgb(220,220,210), border=rgb(255,255,255), borderWidth=1)
        tilt=math.radians(app.dipole_tilt)
        for L in [1.4,1.8,2.3,3.0]:
            pts=[]
            for r,th in dipole_field_line(L, n=90):
                th2=th-tilt; px=cx+r*earth_r*0.85*math.sin(th2); py=cy-r*earth_r*0.85*math.cos(th2)*0.9
                if math.hypot(px-cx, py-cy)>earth_r*0.98 or abs(th-math.pi/2)>0.6: pts.append((px,py))
            for i in range(len(pts)-1):
                try: drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1], fill=CYAN, lineWidth=1.6, opacity=0.8)
                except: pass
        nx=gx+gw-88; ny=gy+26
        drawRect(nx,ny,76,52, fill=rgb(18,22,38), border=PANEL_BORDER, borderWidth=1, roundness=6)
        try:
            decl=app.decl_grid[9][18] if app.decl_grid and len(app.decl_grid)>9 and len(app.decl_grid[0])>18 else 0
            ang=math.radians(decl + app.time*5)
            drawLine(nx+38, ny+28, nx+38+18*math.sin(ang), ny+28-18*math.cos(ang), fill=RED, lineWidth=2, arrowEnd=True)
            drawLine(nx+38, ny+28, nx+38-14*math.sin(ang), ny+28+14*math.cos(ang), fill=BLUE, lineWidth=2)
            drawCircle(nx+38, ny+28, 3, fill=rgb(255,255,255))
            drawLabel(f"{decl:+.1f}°", nx+38, ny+48, fill=YELLOW, size=8, align="center-bottom")
        except: pass
    except: pass

def drawDrift(app):
    try:
        hl=app.hover_panel=="drift"
        drawPanel(DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H, f"SECULAR 1800-2025 Pole Wander", highlight=hl)
        gx,gy,gw,gh=DRIFT_X+14,DRIFT_Y+30,DRIFT_W-28,DRIFT_H-68
        drawRect(gx,gy,gw,gh, fill=rgb(12,16,30), border=rgb(35,45,75), borderWidth=1, roundness=8)
        pcx=gx+gw*0.34; pcy=gy+gh*0.48; pr=78
        drawCircle(pcx,pcy,pr, fill=rgb(16,20,36), border=rgb(50,60,90), borderWidth=0.8)
        for r in [pr*0.33, pr*0.66]: drawCircle(pcx,pcy,r, fill=None, border=rgb(40,50,80), borderWidth=0.6)
        prev=None
        for y,lat,lon in N_POLE_HISTORY:
            r=(90-lat)/20*pr; th=math.radians(lon+90); x=pcx+r*math.cos(th); y_=pcy+r*math.sin(th); t=(y-1800)/225; col=rgb(int(lerp(80,255,t)), int(lerp(180,90,t)), int(lerp(255,80,t)))
            if prev:
                try: drawLine(prev[0],prev[1],x,y_, fill=col, lineWidth=2.2)
                except: pass
            try: drawCircle(x,y_, 3.5, fill=col, border=rgb(0,0,0), borderWidth=0.8)
            except: pass
            prev=(x,y_)
        sx=DRIFT_X+14; sy=DRIFT_Y+DRIFT_H-22; sw=DRIFT_W-28
        drawRect(sx,sy,sw,8, fill=rgb(30,35,55), border=PANEL_BORDER, borderWidth=1, roundness=4)
        t=(app.year-1800)/225; drawRect(sx,sy,t*sw,8, fill=ORANGE, roundness=4); drawCircle(sx+t*sw, sy+4, 8, fill=rgb(255,255,255), border=ORANGE, borderWidth=2)
        drawLabel(f"Year {app.year} {app.fetch_status} {app.pyodide_status[:24]}", gx+8, gy+gh-8, fill=rgb(160,180,210), size=8, align="left-bottom")
    except Exception as e:
        drawLabel(f"drift err {e}"[:40], DRIFT_X+20, DRIFT_Y+40, fill=RED, size=8, align="left-top")

def drawMag(app):
    try:
        hl=app.hover_panel=="mag"
        drawPanel(MAG_X,MAG_Y,MAG_W,MAG_H, f"MAGNETOSPHERE Kp {app.kp_slider:.1f} SW {int(app.solar_wind_speed)} Bz {app.imf_bz:+.1f}", highlight=hl)
        gx,gy,gw,gh=MAG_X+14,MAG_Y+30,MAG_W-28,MAG_H-72
        drawRect(gx,gy,gw,gh, fill=rgb(12,16,30), border=rgb(35,45,75), borderWidth=1, roundness=8)
        sun_x=gx+28; sun_y=gy+gh*0.5; drawCircle(sun_x, sun_y, 18, fill=rgb(255,220,80), border=rgb(255,180,40), borderWidth=1.5)
        drawLabel("Sun", sun_x, sun_y-26, fill=YELLOW, size=9, bold=True, align="center-bottom")
        ex=gx+gw*0.45; ey=gy+gh*0.5; drawCircle(ex,ey,18, fill=rgb(80,140,255), border=rgb(255,255,255), borderWidth=1)
        rmp=10 * (400/app.solar_wind_speed)**0.33 * (1 - app.kp_slider*0.03); rmp_px=rmp*9
        drawMpArc(ex, ey, rmp_px, rmp_px*1.1, 110, 250, CYAN, 1.8); drawMpArc(ex, ey, rmp_px*1.35, rmp_px*1.35*1.15, 110, 250, rgb(180,180,200), 1)
        drawLabel(f"MP {rmp:.1f} Re", ex-rmp_px*0.7, ey-22, fill=CYAN, size=8, align="center-bottom")
        tail_len=120 + app.solar_wind_speed*0.12; drawRect(ex+8, ey-32, tail_len, 64, fill=rgb(20,30,60), border=PANEL_BORDER, borderWidth=1, opacity=0.5)
        drawOval(ex, ey, 38, 26, fill=None, border=PINK, borderWidth=1.2, opacity=0.7); drawOval(ex, ey, 56, 38, fill=None, border=PURPLE, borderWidth=1.2, opacity=0.5)
        ksx=MAG_X+14; ksy=MAG_Y+MAG_H-52; ksw=MAG_W-28; drawRect(ksx,ksy,ksw,8, fill=rgb(30,35,55), border=PANEL_BORDER, borderWidth=1, roundness=4); tk=app.kp_slider/9; colk=GREEN if tk<0.44 else YELLOW if tk<0.66 else RED; drawRect(ksx,ksy,tk*ksw,8, fill=colk, roundness=4); drawCircle(ksx+tk*ksw, ksy+4, 8, fill=rgb(255,255,255), border=colk, borderWidth=2)
        ssx=MAG_X+14; ssy=MAG_Y+MAG_H-22; ssw=MAG_W-28; drawRect(ssx,ssy,ssw,8, fill=rgb(30,35,55), border=PANEL_BORDER, borderWidth=1, roundness=4); tsw=(app.solar_wind_speed-300)/500; drawRect(ssx,ssy,tsw*ssw,8, fill=BLUE, roundness=4); drawCircle(ssx+tsw*ssw, ssy+4, 8, fill=rgb(255,255,255), border=BLUE, borderWidth=2)
    except Exception as e:
        drawLabel(f"mag err {e}"[:40], MAG_X+20, MAG_Y+40, fill=RED, size=8, align="left-top")

def drawImpact(app):
    try:
        hl=app.hover_panel=="impact"
        drawPanel(IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H, "IMPACT — SAA, Navigation, Systems", highlight=hl)
        gx,gy,gw,gh=IMPACT_X+14,IMPACT_Y+30,IMPACT_W-28,IMPACT_H-48
        drawRect(gx,gy,gw,gh, fill=rgb(12,16,30), border=rgb(35,45,75), borderWidth=1, roundness=8)
        mx=gx+6; my=gy+8; mw=gw*0.58; mh=gh-16; drawRect(mx,my,mw,mh, fill=rgb(16,24,42), border=rgb(35,45,75), borderWidth=1, roundness=6)
        saa_x=mx + (-50+180)/360*mw; saa_y=my + (80-(-26))/160*mh; saa_r=28 + (8.6-app.dipole_moment)*12
        drawOval(saa_x, saa_y, saa_r*2.2, saa_r*1.4, fill=RED, opacity=0.18); drawOval(saa_x, saa_y, saa_r*1.6, saa_r, fill=None, border=RED, borderWidth=1.2, opacity=0.7); drawLabel("SAA", saa_x, saa_y-2, fill=RED, size=9, bold=True, align="center")
        if app.decl_grid:
            try:
                for i in range(len(app.decl_grid)):
                    for j in range(len(app.decl_grid[0])):
                        if abs(app.decl_grid[i][j])<8: drawCircle(mx + (j/36)*mw, my + (i/18)*mh, 1.2, fill=YELLOW, opacity=0.7)
            except: pass
        try:
            for lat,lon,code in app.observatories[:12]: drawCircle(mx + (lon+180)/360*mw, my + (80-lat)/160*mh, 2.2, fill=CYAN, border=rgb(0,0,0), borderWidth=0.6)
        except: pass
        px=gx+gw*0.62+8; py=gy+8; pw=gw*0.36-8; ph=mh*0.48; drawRect(px,py,pw,ph, fill=rgb(16,20,36), border=rgb(35,45,75), borderWidth=1, roundness=6); drawLabel("Power n", px+4, py+4, fill=rgb(150,170,200), size=8, align="left-top")
        if app.power_spec:
            try:
                maxp=max(app.power_spec) if max(app.power_spec)>0 else 1
                for i,p in enumerate(app.power_spec[:8]):
                    bx=px+8 + i*(pw-16)/8; bw=(pw-20)/8*0.7; bh=(p/maxp)*(ph-22); drawRect(bx, py+ph-8-bh, bw, bh, fill=PURPLE if i>0 else YELLOW, roundness=3)
            except: pass
        drawLabel(f"{app.fetch_status2} {app.fetch_status3}", gx+8, gy+gh-8, fill=rgb(130,150,180), size=7.5, align="left-bottom")
    except Exception as e:
        drawLabel(f"impact err {e}"[:40], IMPACT_X+20, IMPACT_Y+40, fill=RED, size=8, align="left-top")

def drawGlobeOverlay(app):
    try:
        drawRect(0,0,W,H, fill=BG); drawRect(0,0,W,HEADER_H, fill=rgb(18,22,38))
        drawLabel("GLOBE VIEW — Compass Needles & Field (SOS)", W*0.5, 12, fill=rgb(240,250,255), size=16, bold=True, align="center-top")
        drawRect(W-280,8,110,34, fill=PURPLE, border=rgb(255,255,255), borderWidth=1.2, roundness=18); drawLabel("BACK TO LAB", W-280+55, 8+17, fill=rgb(255,255,255), size=11, bold=True, align="center")
        drawRect(W-60, HEADER_H+8, 36,26, fill=rgb(60,70,90), border=rgb(200,210,230), borderWidth=1, roundness=7); drawLabel("X", W-60+18, HEADER_H+8+13, fill=rgb(230,240,255), size=13, bold=True, align="center")
        gx,gy,gw,gh=16, HEADER_H+12, 680, 600; drawRect(gx,gy,gw,gh, fill=rgb(18,22,38), border=PANEL_BORDER, borderWidth=1, roundness=12)
        cx=gx+gw*0.48; cy=gy+gh*0.5; R=210; drawCircle(cx,cy,R, fill=rgb(20,35,60), border=rgb(60,80,110), borderWidth=1.5)
        tilt=math.radians(app.dipole_tilt + 5*math.sin(app.time*0.5))
        for L in [1.6,2.0,2.5,3.2,4.0]:
            pts=[]
            for th_deg in range(12,168,4):
                th=math.radians(th_deg); r=L * (math.sin(th)**2)
                if r<1.05 or r>5: continue
                th2=th-tilt; x=cx + r*R*0.92*math.sin(th2); y=cy - r*R*0.92*math.cos(th2)*0.42
                if math.hypot(x-cx, (y-cy)/0.42) > R*1.02: pts.append((x,y))
            for i in range(len(pts)-1):
                try: drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1], fill=CYAN, lineWidth=1.4, opacity=0.65)
                except: pass
        if app.decl_grid:
            for i in range(0,18,3):
                for j in range(0,36,6):
                    try:
                        lat=80 - i/18*160; lon=-180 + j/36*360 + app.globe_rot*20; th=math.radians(lon)
                        if math.cos(th) < 0: continue
                        x=cx + R*math.cos(math.radians(lat))*math.sin(th)*0.9*0.85; y=cy + R*math.sin(math.radians(lat))*0.42*0.85; decl=app.decl_grid[i][j]; ang=math.radians(decl)
                        drawLine(x,y, x+8*math.sin(ang), y-8*math.cos(ang)*0.42, fill=RED, lineWidth=1.2, arrowEnd=True)
                    except: pass
    except: pass

def redrawAll(app):
    drawRect(0,0,W,H, fill=BG)
    drawHeader(app)
    if app.show_globe:
        drawGlobeOverlay(app)
        return
    # BULLETPROOF - each panel isolated, one crash doesn't kill others
    drawDynamo(app)
    drawDrift(app)
    drawMag(app)
    drawImpact(app)

def onDraw(app):
    redrawAll(app)
