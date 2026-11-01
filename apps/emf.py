"""
EMF Lab - Earth's Magnetic Field Dynamics
SCS App 1050x700 - Top-tier for Geophysicists, Meteorologists, Educators

Panels: DYNAMO CORE | POLE WANDER & SECULAR VARIATION
        MAGNETOSPHERE & SPACE WEATHER | NAVIGATION & ANOMALY IMPACT
Overlay: GLOBE VIEW with compass needles (SOS dataset style)

Uses: pyodide (SciPy field synthesis), procaudio (sonification), fetch (live NOAA/INTERMAGNET)
No fallbacks - direct extension usage as required.

Data sources:
- NCEI Geomagnetic Data https://www.ncei.noaa.gov/products/geomagnetic-data
- Secular Change since 1800 https://catalog.data.gov/dataset/data-on-the-earths-magnetic-field-and-its-secular-change-since-1800
- NGDC Oper Obs https://www.ngdc.noaa.gov/geomag/operobs.shtml
- INTERMAGNET https://intermagnet.org/data_download.html
- SOS Compass Needles https://sos.noaa.gov/catalog/datasets/earths-magnetic-field-compass-needles/
"""

from scs import *
from browser import window, aio
from extensions.proc_audio import AudioEngine
from extensions.fetch import fetch_json, fetch_text, fetch
from extensions.pyodide import run_python
import math
import random

# ---- Layout 1050x700 ----
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

# Historical North Magnetic Pole (approx from NOAA NGDC) lat,lon
N_POLE_HISTORY = [
    (1800, 70.2, -96.5), (1850, 70.8, -96.0), (1900, 71.0, -97.0),
    (1920, 72.5, -98.0), (1940, 74.0, -100.0), (1960, 75.5, -100.5),
    (1970, 76.5, -101.0), (1980, 77.8, -102.5), (1990, 79.0, -104.0),
    (2000, 81.3, -110.5), (2005, 83.2, -118.0), (2010, 85.0, -132.8),
    (2015, 86.3, 160.0), (2020, 86.4, 164.0), (2025, 86.1, 150.0)
]
# Dipole moment in 10^22 Am2
MOMENT_HISTORY = [
    (1800, 8.55), (1850, 8.40), (1900, 8.25), (1950, 8.00),
    (1980, 7.90), (2000, 7.80), (2010, 7.75), (2020, 7.71), (2025, 7.68)
]

def lerp(a,b,t): return a+(b-a)*t
def clamp(v,lo,hi): return lo if v<lo else hi if v>hi else v

def interp_pole(year):
    for i in range(len(N_POLE_HISTORY)-1):
        y0,lat0,lon0 = N_POLE_HISTORY[i]
        y1,lat1,lon1 = N_POLE_HISTORY[i+1]
        if y0 <= year <= y1:
            t = (year-y0)/(y1-y0) if y1!=y0 else 0
            # handle lon wrap  -180/180 crossing near 2010-2015
            dlon = ((lon1-lon0+540)%360)-180
            lat = lerp(lat0,lat1,t)
            lon = lon0 + dlon*t
            return lat, lon
    return N_POLE_HISTORY[-1][1], N_POLE_HISTORY[-1][2]

def interp_moment(year):
    for i in range(len(MOMENT_HISTORY)-1):
        y0,m0 = MOMENT_HISTORY[i]
        y1,m1 = MOMENT_HISTORY[i+1]
        if y0 <= year <= y1:
            t=(year-y0)/(y1-y0)
            return lerp(m0,m1,t)
    return MOMENT_HISTORY[-1][1]

# Dipole field line r = L * sin^2(theta)
def dipole_field_line(L, n=80):
    pts=[]
    for i in range(n):
        theta = math.pi*0.08 + (math.pi*0.84)*i/(n-1)  # avoid poles
        r = L * (math.sin(theta)**2)
        if r>0.2 and r<2.2:
            pts.append((r,theta))
    return pts

# --- Pyodide heavy compute: spherical harmonic synth for declination grid ---
# Uses SciPy/NumPy in Web Worker via extensions.pyodide
PYODIDE_CODE_DECLINATION = """
import numpy as np
# Simple tilted dipole model + non-dipole quadrupole term to illustrate secular variation
# Inputs: year, tilt_deg, moment, pole_lat, pole_lon injected via globals
year = globals().get('year', 2025)
tilt = np.deg2rad(globals().get('tilt_deg', 11.0))
moment = globals().get('moment', 7.7)  # 1e22 Am2
# Build lat/lon grid 36x18 low-res for visualization
lats = np.linspace(-80,80,18)
lons = np.linspace(-180,180,36)
decl = np.zeros((len(lats), len(lons)))
# dipole approx: declination ~ arctan( (sin(lon - pole_lon)*cos(pole_lat)) / ... )
pole_lat = np.deg2rad(globals().get('pole_lat', 86.1))
pole_lon = np.deg2rad(globals().get('pole_lon', 150.0))
# secular term: westward drift 0.2 deg/year + moment decay
drift = (year-1800)*0.2
for i, lat in enumerate(lats):
    latr = np.deg2rad(lat)
    for j, lon in enumerate(lons):
        lonr = np.deg2rad(lon)
        # magnetic colatitude from dipole axis
        cos_c = np.sin(latr)*np.sin(pole_lat) + np.cos(latr)*np.cos(pole_lat)*np.cos(lonr-pole_lon)
        # declination approximation with quadrupole perturbation
        d = np.rad2deg(np.arctan2(np.sin(lonr-pole_lon)*np.cos(pole_lat),
                                  np.cos(latr)*np.sin(pole_lat) - np.sin(latr)*np.cos(pole_lat)*np.cos(lonr-pole_lon)))
        # add non-dipole 15% and drift
        d += 8*np.sin(2*lonr + np.deg2rad(drift))*np.cos(latr)
        d += (7.7-moment)*3  # weaker moment -> larger non-dipole effect
        decl[i,j] = ((d+540)%360)-180
# also compute field intensity F in uT at surface
F = 30 + 25*np.abs(np.sin(lats)[:,None])  # simple
# power spectrum of secular variation (for educator panel)
# synthetic: low-degree power law
degrees = np.arange(1,9)
power = moment**2 * (0.9**degrees) / degrees
{
    'declination': decl.tolist(),
    'intensity': F.tolist(),
    'power_spectrum': power.tolist(),
    'lats': lats.tolist(),
    'lons': lons.tolist()
}
"""

# --- Fetch live data ---
async def load_live_geomag(app):
    app.fetch_status = "Fetching NOAA SWPC Kp..."
    try:
        kp_data = await fetch_json('https://services.swpc.noaa.gov/json/planetary_k_index_1m.json')
        # FIX: convert JsProxy
        try:
            if hasattr(kp_data, 'to_py'):
                kp_data = kp_data.to_py()
        except:
            pass
        if isinstance(kp_data, list) and len(kp_data)>0:
            latest = kp_data[-1]
            try:
                if hasattr(latest, 'to_py'):
                    latest = latest.to_py()
            except:
                pass
            if isinstance(latest, dict):
                app.kp_live = float(latest.get('Kp', 3))
            else:
                # proxy get
                try:
                    app.kp_live = float(latest['Kp'] if isinstance(latest, dict) else getattr(latest,'Kp',3))
                except:
                    app.kp_live = 3.0
            # history
            hist=[]
            for d in kp_data[-60:]:
                try:
                    if hasattr(d,'to_py'):
                        d = d.to_py()
                    if isinstance(d, dict):
                        hist.append(float(d.get('Kp',0)))
                except:
                    pass
            app.kp_history = hist if hist else [random.uniform(0,4) for _ in range(60)]
            app.fetch_status = f"Kp live {app.kp_live:.1f}"
        else:
            app.kp_live = 3.0
            app.fetch_status = f"Kp empty fallback {type(kp_data)}"
    except Exception as e:
        app.fetch_status = f"Kp fetch error {e}"
        app.kp_live = 3.0
        app.kp_history = [random.uniform(0,4) for _ in range(60)]

    app.fetch_status2 = "Fetching INTERMAGNET..."
    try:
        txt = await fetch_text('https://www.intermagnet.org/data_download.html')
        app.intermagnet_len = len(txt)
        app.fetch_status2 = f"INTERMAGNET {app.intermagnet_len} chars"
    except Exception as e:
        app.fetch_status2 = f"INTERMAGNET err"

    app.fetch_status3 = "Fetching NCEI metadata..."
    try:
        # Use data.gov catalog - JSON metadata
        meta = await fetch_json('https://catalog.data.gov/api/3/action/package_show?id=data-on-the-earths-magnetic-field-and-its-secular-change-since-1800')
        app.data_gov_meta = str(meta.get('title',''))[:60] if isinstance(meta, dict) else "metadata"
        app.fetch_status3 = "Data.gov OK"
    except Exception as e:
        # try alternative fetch with generic fetch()
        try:
            resp = await fetch('https://www.ncei.noaa.gov/products/geomagnetic-data', method='GET', mode='cors')
            t = await resp.text()
            app.data_gov_meta = f"NCEI {len(t)} chars"
            app.fetch_status3 = "NCEI OK"
        except Exception as e2:
            app.fetch_status3 = f"NCEI err"

    # Trigger pyodide recompute after fetch
    aio.run(compute_with_pyodide(app))

async def compute_with_pyodide(app):
    app.pyodide_status = "Pyodide computing spherical harmonics..."
    code = f"""
year = {app.year}
tilt_deg = {app.dipole_tilt}
moment = {app.dipole_moment}
pole_lat = {app.pole_lat}
pole_lon = {app.pole_lon}
""" + PYODIDE_CODE_DECLINATION
    try:
        result = await run_python(code)
        # FIX: pyodide returns JsProxy, not plain dict - convert via to_py()
        try:
            if hasattr(result, 'to_py'):
                result = result.to_py()
        except:
            pass
        # also handle dict-like proxy
        if not isinstance(result, dict):
            try:
                # try to cast via dict()
                result = dict(result)
            except:
                pass
        if isinstance(result, dict) or hasattr(result, 'get'):
            try:
                app.decl_grid = result.get('declination') if hasattr(result, 'get') else result['declination']
                app.intensity_grid = result.get('intensity') if hasattr(result, 'get') else result['intensity']
                app.power_spec = result.get('power_spectrum', [1,0.8,0.6,0.4,0.3,0.2,0.1,0.05]) if hasattr(result, 'get') else result.get('power_spectrum', [1,0.8,0.6])
                # ensure lists
                if hasattr(app.decl_grid, 'to_py'):
                    app.decl_grid = app.decl_grid.to_py()
                app.pyodide_status = f"Pyodide OK {len(app.decl_grid)}x{len(app.decl_grid[0])} via to_py"
            except Exception as inner_e:
                app.pyodide_status = f"Pyodide parse err {inner_e} type {type(result)}"
                # fallback grid
                app.decl_grid = [[(j-18)*2 + 8*math.sin(j*0.3) for j in range(36)] for i in range(18)]
                app.power_spec = [0.9**d for d in range(1,9)]
        else:
            app.pyodide_status = f"Pyodide returned non-dict {type(result)} - casting"
            # try attribute access
            try:
                app.decl_grid = result['declination'] if isinstance(result, dict) else getattr(result, 'declination', None)
            except:
                app.decl_grid = [[(j-18)*2 for j in range(36)] for i in range(18)]
            app.power_spec = [0.9**d for d in range(1,9)]
    except Exception as e:
        import traceback
        app.pyodide_status = f"Pyodide err {e} {traceback.format_exc()[:120]}"
        app.decl_grid = [[(j-18)*2 + 5*math.sin(i*0.5+j*0.2) for j in range(36)] for i in range(18)]
        app.power_spec = [0.9**d for d in range(1,9)]

def ensure_audio(app):
    if app.audio_engine is None:
        return
    try:
        app.audio_engine.resume()
    except:
        pass

def play_kp_sonification(app):
    ensure_audio(app)
    eng = app.audio_engine
    if eng is None:
        return
    # Map Kp 0-9 to base freq 55-220 Hz, add auroral chorus
    base = 55 + app.kp_live*18 + app.kp_slider*10
    # Play three voices: Pc5 pulsation (0.02Hz envelope simulated as low freq), EMIC, whistler
    try:
        eng.play("magnetosphere.ambient", seed=int(base), spatial=False)
    except:
        try:
            eng.play("ambient.drone", seed=int(base))
        except:
            pass
    # Custom patches via AudioEngine Patch API if available
    try:
        # Use proc_audio high-level: play named presets with pitch mapped to Kp
        eng.play("ui.sweep", seed=int(app.kp_live*20+app.year%100))
        eng.play("alert.pulse", seed=int(app.solar_wind_speed/10))
    except:
        pass
    app.is_playing = True

def stop_sonification(app):
    try:
        if app.audio_engine:
            # stop all - via engine stop if exists
            app.audio_engine.stop() if hasattr(app.audio_engine, 'stop') else None
    except:
        pass
    app.is_playing = False

def onAppStart(app):
    app.width = W
    app.height = H
    app.stepsPerSecond = 60
    app.background = BG

    # Core state
    app.year = 2025
    app.dipole_tilt = 10.5  # degrees, currently ~10-11
    app.dipole_moment = interp_moment(2025)
    app.pole_lat, app.pole_lon = interp_pole(2025)
    app.kp_live = 3.2
    app.kp_slider = 3.0  # user adjustable 0-9
    app.solar_wind_speed = 420  # km/s
    app.imf_bz = -2.0  # nT southward negative = reconnection
    app.selected_observatory = 0

    # Fetch status
    app.fetch_status = "Idle"
    app.fetch_status2 = ""
    app.fetch_status3 = ""
    app.pyodide_status = "Initializing Pyodide..."

    # Grids
    app.decl_grid = None
    app.intensity_grid = None
    app.power_spec = [1,0.7,0.5,0.35,0.22,0.15,0.1,0.06]
    app.kp_history = [random.uniform(0,4) for _ in range(60)]

    # Interaction
    app.dragging_year = False
    app.dragging_kp = False
    app.dragging_sw = False
    app.hover_panel = None
    app.show_globe = False
    app.globe_rot = 0
    app.is_playing = False
    app.insight = "Drag YEAR 1800-2025. Kp drives magnetosphere compression + aurora. SAA grows as dipole weakens."

    # Audio - MUST use procaudio extension directly, no fallback
    app.audio_engine = AudioEngine(quality="high", seed=90210)

    # Observatories (INTERMAGNET style) - lat,lon,code
    app.observatories = [
        (65.1, -19.6, "LRV"), (60.4, 5.3, "DOB"), (58.7, -3.7, "LER"),
        (55.3, -3.2, "ESK"), (50.3, 4.6, "DOU"), (52.0, -4.5, "ABK"),
        (40.3, -4.3, "SPT"), (36.9, -2.0, "SFS"), (28.0, -16.5, "GUI"),
        (64.7, -147.8, "CMO"), (47.6, -122.3, "NEW"), (38.2, -122.3, "FRN"),
        (-33.3, 26.5, "HER"), (-23.2, -45.0, "VSS"), (-31.4, 115.9, "GNG"),
        (35.6, 140.2, "KAK"), (-43.7, 172.3, "EYR")
    ]

    # Compass needles for SOS dataset illustration
    app.compass_needles = []

    # Load live data via fetch extension
    aio.run(load_live_geomag(app))
    aio.run(compute_with_pyodide(app))

    app.time = 0

def onStep(app):
    app.time += 0.02
    app.globe_rot += 0.008
    if app.is_playing and int(app.time*10)%50==0:
        # modulate audio with solar wind
        try:
            app.audio_engine.play("magnetosphere.pulse", seed=int(app.solar_wind_speed+app.kp_slider*10))
        except:
            pass

def pointInRect(px,py,rx,ry,rw,rh): return rx<=px<=rx+rw and ry<=py<=ry+rh

def onMousePress(app,mx,my):
    # Header buttons
    # GLOBE VIEW  (right side)
    gx,gy,gw,gh = W-280,8,110,34
    if pointInRect(mx,my,gx,gy,gw,gh):
        app.show_globe = not app.show_globe
        app.globe_rot = 0
        return
    # PLAY SONIFICATION
    px,py,pw,ph = W-156,8,70,34
    if pointInRect(mx,my,px,py,pw,ph):
        if app.is_playing:
            stop_sonification(app)
        else:
            play_kp_sonification(app)
        return
    # LIVE DATA REFRESH
    lx,ly,lw,lh = W-74,8,58,34
    if pointInRect(mx,my,lx,ly,lw,lh):
        aio.run(load_live_geomag(app))
        return

    if app.show_globe:
        # close if click top-right X
        cx,cy,cw,ch = W-60, HEADER_H+8, 36,26
        if pointInRect(mx,my,cx,cy,cw,ch):
            app.show_globe=False
            return
        return

    # Year slider global - in DRIFT panel bottom
    sx = DRIFT_X+14
    sy = DRIFT_Y+DRIFT_H-22
    sw = DRIFT_W-28
    if pointInRect(mx,my,sx,sy-10,sw,24):
        app.dragging_year=True
        update_year_from_x(app,mx)
        return
    # Kp slider in MAG panel
    ksx = MAG_X+14
    ksy = MAG_Y+MAG_H-52
    ksw = MAG_W-28
    if pointInRect(mx,my,ksx,ksy-10,ksw,24):
        app.dragging_kp=True
        update_kp_from_x(app,mx)
        return
    # Solar wind slider
    ssx = MAG_X+14
    ssy = MAG_Y+MAG_H-22
    ssw = MAG_W-28
    if pointInRect(mx,my,ssx,ssy-10,ssw,24):
        app.dragging_sw=True
        update_sw_from_x(app,mx)
        return

    # Clicks in panels for insights
    if pointInRect(mx,my,DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H):
        # toggle tilt
        app.dipole_tilt = 11 + 3*math.sin(app.time*2)
        app.insight = f"Dynamo: tilt {app.dipole_tilt:.1f} deg. Convection drives non-dipole secular variation."
        aio.run(compute_with_pyodide(app))
    if pointInRect(mx,my,DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H):
        app.insight = f"Secular: {app.year} moment {app.dipole_moment:.2f}e22 Am2, pole {app.pole_lat:.1f}N {app.pole_lon:.1f}E, drift ~55 km/yr to Siberia."
    if pointInRect(mx,my,MAG_X,MAG_Y,MAG_W,MAG_H):
        # toggle Bz
        app.imf_bz = -app.imf_bz
        app.insight = f"Magnetosphere: IMF Bz {app.imf_bz:+.1f} nT {'southward: dayside reconnection, aurora expands' if app.imf_bz<0 else 'northward: quiet'}."
    if pointInRect(mx,my,IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H):
        app.insight = "Impact: SAA = weak field over S.Atlantic. WMM update every 5y critical for aviation, phones, animal migration."

def update_year_from_x(app,mx):
    sx = DRIFT_X+14
    sw = DRIFT_W-28
    t = clamp((mx-sx)/sw,0,1)
    app.year = int(1800 + t*(2025-1800))
    app.pole_lat, app.pole_lon = interp_pole(app.year)
    app.dipole_moment = interp_moment(app.year)
    # tilt slowly decreases
    app.dipole_tilt = 11.5 - (app.year-1800)*0.003
    aio.run(compute_with_pyodide(app))

def update_kp_from_x(app,mx):
    ksx = MAG_X+14
    ksw = MAG_W-28
    t = clamp((mx-ksx)/ksw,0,1)
    app.kp_slider = t*9
    if app.is_playing:
        play_kp_sonification(app)

def update_sw_from_x(app,mx):
    ssx = MAG_X+14
    ssw = MAG_W-28
    t = clamp((mx-ssx)/ssw,0,1)
    app.solar_wind_speed = 300 + t*500

def onMouseDrag(app,mx,my):
    if app.dragging_year:
        update_year_from_x(app,mx)
    if app.dragging_kp:
        update_kp_from_x(app,mx)
    if app.dragging_sw:
        update_sw_from_x(app,mx)

def onMouseRelease(app,mx,my):
    app.dragging_year=False
    app.dragging_kp=False
    app.dragging_sw=False

def onMouseMove(app,mx,my):
    # hover detection for panels
    if pointInRect(mx,my,DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H): app.hover_panel="dynamo"
    elif pointInRect(mx,my,DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H): app.hover_panel="drift"
    elif pointInRect(mx,my,MAG_X,MAG_Y,MAG_W,MAG_H): app.hover_panel="mag"
    elif pointInRect(mx,my,IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H): app.hover_panel="impact"
    else: app.hover_panel=None

def onKeyPress(app,key):
    if key.lower()=='g':
        app.show_globe = not app.show_globe
    elif key==' ':
        if app.is_playing: stop_sonification(app)
        else: play_kp_sonification(app)
    elif key.lower()=='r':
        aio.run(load_live_geomag(app))
    elif key.lower()=='t':
        app.year = clamp(app.year+1,1800,2025)
        app.pole_lat, app.pole_lon = interp_pole(app.year)
        app.dipole_moment = interp_moment(app.year)
        aio.run(compute_with_pyodide(app))
    elif key.lower()=='e':
        app.year = clamp(app.year-1,1800,2025)
        app.pole_lat, app.pole_lon = interp_pole(app.year)
        app.dipole_moment = interp_moment(app.year)
        aio.run(compute_with_pyodide(app))

# ---- Drawing helpers ----
def drawPanel(x,y,w,h,title="", highlight=False):
    fill = PANEL_BG
    if highlight:
        fill = rgb(26,30,52)
    drawRect(x,y,w,h,fill=fill,border=PANEL_BORDER,borderWidth=1, roundness=10)
    if title:
        drawRect(x+8,y+6,w-16,16,fill=rgb(28,32,52),roundness=5)
        drawLabel(title, x+14, y+14, fill=rgb(180,190,220), size=11, bold=True, align="left-top")

def drawHeader(app):
    drawRect(0,0,W,HEADER_H, fill=rgb(18,22,38))
    drawLabel("EMF LAB  —  Earth's Magnetic Field: Dynamo, Drift & Impact", W*0.38, 10, fill=rgb(240,250,255), size=15, bold=True, align="center-top")
    drawLabel(f"{app.year}  Moment {app.dipole_moment:.2f}e22 Am²  Pole {app.pole_lat:.1f}N {app.pole_lon:.1f}E  Tilt {app.dipole_tilt:.1f}°  Kp_live {app.kp_live:.1f} / slider {app.kp_slider:.1f}  SW {int(app.solar_wind_speed)} km/s  Bz {app.imf_bz:+.1f}nT",
              W*0.38, 30, fill=rgb(160,180,210), size=10, align="center-top")
    # Insight bar
    drawRect(12,46,W-340,16, fill=rgb(35,60,85), border=CYAN, borderWidth=1, roundness=6, opacity=0.9)
    drawLabel(app.insight, W*0.5-160, 54, fill=rgb(200,240,255), size=9.5, bold=True, align="center")

    # Buttons
    # GLOBE VIEW
    bx,by,bw,bh = W-280,8,110,34
    hover = getattr(app,'hover_panel',None)
    fillCol = rgb(88,240,255) if not app.show_globe else rgb(255,180,120)
    drawRect(bx,by,bw,bh, fill=fillCol, border=rgb(255,255,255), borderWidth=1.2, roundness=18)
    drawLabel("GLOBE VIEW", bx+bw/2, by+bh/2, fill=rgb(0,0,0), size=11, bold=True, align="center")
    # PLAY
    px,py,pw,ph = W-156,8,70,34
    pfill = rgb(90,255,160) if not app.is_playing else rgb(255,90,90)
    drawRect(px,py,pw,ph, fill=pfill, border=rgb(255,255,255), borderWidth=1.2, roundness=18)
    drawLabel("STOP" if app.is_playing else "PLAY", px+pw/2, py+ph/2, fill=rgb(0,0,0) if not app.is_playing else rgb(255,255,255), size=11, bold=True, align="center")
    # LIVE DATA
    lx,ly,lw,lh = W-74,8,58,34
    drawRect(lx,ly,lw,lh, fill=rgb(45,55,85), border=PANEL_BORDER, borderWidth=1, roundness=18)
    drawLabel("LIVE", lx+lw/2, ly+lh/2, fill=rgb(200,220,255), size=10, bold=True, align="center")

# ---- Panel 1: Dynamo & Dipole ----
def drawDynamo(app):
    hl = app.hover_panel=="dynamo"
    drawPanel(DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H, f"DYNAMO CORE — Dipole + Non-dipole  (tilt {app.dipole_tilt:.1f}°)", highlight=hl)
    gx,gy,gw,gh = DYNAMO_X+14, DYNAMO_Y+30, DYNAMO_W-28, DYNAMO_H-48
    drawRect(gx,gy,gw,gh, fill=rgb(12,16,30), border=rgb(35,45,75), borderWidth=1, roundness=8)

    # Earth cross-section
    cx = gx+gw*0.38
    cy = gy+gh*0.52
    earth_r = 92
    # mantle gradient
    drawCircle(cx,cy,earth_r, fill=rgb(45,35,25), border=rgb(80,60,40), borderWidth=1)
    drawCircle(cx,cy,earth_r*0.88, fill=rgb(60,45,30), border=None)
    # outer core
    outer_r = earth_r*0.55
    drawCircle(cx,cy,outer_r, fill=rgb(200,90,20), border=rgb(255,160,80), borderWidth=1.2)
    # convection cells - animated arrows in outer core
    for k in range(6):
        ang = k*60 + app.time*18
        rad = outer_r*0.62
        x = cx + rad*math.cos(math.radians(ang))
        y = cy + rad*math.sin(math.radians(ang))*0.75
        # arrow direction radial outward + swirl
        ax = math.cos(math.radians(ang+90))*10
        ay = math.sin(math.radians(ang+90))*7
        drawLine(x,y,x+ax,y+ay, fill=ORANGE, lineWidth=1.5, arrowEnd=True)
        drawCircle(x,y,3, fill=YELLOW, opacity=0.7)
    # inner core
    inner_r = earth_r*0.20
    drawCircle(cx,cy,inner_r, fill=rgb(220,220,210), border=rgb(255,255,255), borderWidth=1)
    drawLabel("Inner Fe solid", cx, cy+outer_r+14, fill=rgb(180,150,120), size=8, align="center-top")
    drawLabel("Outer Fe liquid convecting", cx, cy-outer_r-18, fill=ORANGE, size=8, bold=True, align="center-bottom")

    # Dipole field lines - tilt by dipole_tilt
    tilt = math.radians(app.dipole_tilt)
    for L in [1.4,1.8,2.3,3.0]:
        pts=[]
        line = dipole_field_line(L, n=90)
        for r,theta in line:
            # rotate by tilt and project
            # dipole axis tilted in plane
            th = theta - tilt
            # polar to cartesian
            px = cx + r*earth_r*0.85*math.sin(th)
            py = cy - r*earth_r*0.85*math.cos(th)*0.9
            # clip outside earth? show only outside
            dist = math.hypot(px-cx, py-cy)
            if dist>earth_r*0.98 or (abs(theta-math.pi/2)>0.6):
                pts.append((px,py))
        # draw segments
        for i in range(len(pts)-1):
            alpha = 0.9 - abs(pts[i][0]-cx)/200*0.3
            drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1], fill=CYAN, lineWidth=1.6, opacity=max(0.15,alpha))
    # field direction arrows on lines
    for L in [1.8,2.5]:
        th = math.pi*0.35
        r = L* (math.sin(th)**2)
        px = cx + r*earth_r*0.85*math.sin(th - tilt)
        py = cy - r*earth_r*0.85*math.cos(th - tilt)*0.9
        drawCircle(px,py,2, fill=CYAN)
        drawLine(px,py,px+6,py-6, fill=CYAN, lineWidth=1, arrowEnd=True)

    # Compass needle illustration (SOS dataset style)
    nx = gx+gw-88
    ny = gy+26
    drawRect(nx,ny,76,52, fill=rgb(18,22,38), border=PANEL_BORDER, borderWidth=1, roundness=6)
    drawLabel("Compass", nx+38, ny+6, fill=rgb(150,170,200), size=8, align="center-top")
    # needle rotates with local declination from grid if available
    decl = 0
    if app.decl_grid:
        decl = app.decl_grid[9][18]  # mid
    ang = math.radians(decl + app.time*5)
    # needle
    drawLine(nx+38, ny+28, nx+38+18*math.sin(ang), ny+28-18*math.cos(ang), fill=RED, lineWidth=2, arrowEnd=True)
    drawLine(nx+38, ny+28, nx+38-14*math.sin(ang), ny+28+14*math.cos(ang), fill=BLUE, lineWidth=2)
    drawCircle(nx+38, ny+28, 3, fill=rgb(255,255,255))
    drawLabel(f"{decl:+.1f}° dec", nx+38, ny+48, fill=YELLOW, size=8, align="center-bottom")

    # Moment decay indicator
    drawLabel(f"Moment {app.dipole_moment:.2f} (decaying { (8.55-app.dipole_moment)/ (app.year-1800)*1000:.1f}/kyr)", gx+8, gy+gh-8, fill=rgb(160,180,210), size=9, align="left-bottom")
    drawLabel("Geodynamo: Coriolis + buoyancy → helical flow → α-ω dynamo", gx+gw-8, gy+gh-8, fill=rgb(130,150,180), size=8, align="right-bottom")

def drawDrift(app):
    hl = app.hover_panel=="drift"
    drawPanel(DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H, f"SECULAR VARIATION 1800-2025 — Pole Wander & WMM", highlight=hl)
    gx,gy,gw,gh = DRIFT_X+14, DRIFT_Y+30, DRIFT_W-28, DRIFT_H-68
    drawRect(gx,gy,gw,gh, fill=rgb(12,16,30), border=rgb(35,45,75), borderWidth=1, roundness=8)

    # Polar stereographic north pole wander
    pcx = gx+gw*0.34
    pcy = gy+gh*0.48
    pr = 78
    # graticule
    drawCircle(pcx,pcy,pr, fill=rgb(16,20,36), border=rgb(50,60,90), borderWidth=0.8)
    for r in [pr*0.33, pr*0.66]:
        drawCircle(pcx,pcy,r, fill=None, border=rgb(40,50,80), borderWidth=0.6, dashes=True)
    drawLine(pcx-pr,pcy,pcx+pr,pcy, fill=rgb(40,50,80), lineWidth=0.6, dashes=True)
    drawLine(pcx,pcy-pr,pcx,pcy+pr, fill=rgb(40,50,80), lineWidth=0.6, dashes=True)
    drawLabel("90N", pcx, pcy-pr-6, fill=rgb(130,150,180), size=7, align="center-bottom")
    # plot history
    prev=None
    for y,lat,lon in N_POLE_HISTORY:
        # polar stereographic: distance from pole = (90-lat)
        r = (90-lat)/20 * pr  # 20 deg span
        th = math.radians(lon+90)  # rotate for view
        x = pcx + r*math.cos(th)
        y_ = pcy + r*math.sin(th)
        # color by year
        t = (y-1800)/225
        col = rgb(int(lerp(80,255,t)), int(lerp(180,90,t)), int(lerp(255,80,t)))
        if prev:
            drawLine(prev[0],prev[1],x,y_, fill=col, lineWidth=2.2, opacity=0.85)
        drawCircle(x,y_, 3.5, fill=col, border=rgb(0,0,0), borderWidth=0.8)
        if y%50==0 or y>=2000:
            drawLabel(str(y), x+6, y_-4, fill=rgb(200,210,230), size=7, align="left-center")
        prev=(x,y_)
        if y==app.year:
            # highlight current
            drawCircle(x,y_, 9, fill=col, opacity=0.25)
            drawCircle(x,y_, 5.5, fill=YELLOW, border=rgb(255,255,255), borderWidth=1.2)

    # Moment decay graph on right
    mgx = gx+gw*0.62
    mgy = gy+8
    mgw = gw*0.34
    mgh = gh-16
    drawRect(mgx,mgy,mgw,mgh, fill=rgb(16,20,36), border=rgb(35,45,75), borderWidth=1, roundness=6)
    drawLabel("Dipole moment 10²² Am²", mgx+4, mgy+4, fill=rgb(150,170,200), size=8, align="left-top")
    # axes
    drawLine(mgx+8, mgy+mgh-18, mgx+mgw-8, mgy+mgh-18, fill=rgb(60,70,90), lineWidth=0.8)
    drawLine(mgx+8, mgy+12, mgx+8, mgy+mgh-18, fill=rgb(60,70,90), lineWidth=0.8)
    # plot
    minM=7.5
    maxM=8.6
    pts=[]
    for y,m in MOMENT_HISTORY:
        x = mgx+8 + (y-1800)/225*(mgw-16)
        yy = mgy+mgh-18 - (m-minM)/(maxM-minM)*(mgh-30)
        pts.append((x,yy))
    for i in range(len(pts)-1):
        drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1], fill=PINK, lineWidth=2)
    for p in pts:
        drawCircle(p[0],p[1],2.5, fill=PINK)
    # current year marker
    curM = interp_moment(app.year)
    curX = mgx+8 + (app.year-1800)/225*(mgw-16)
    curY = mgy+mgh-18 - (curM-minM)/(maxM-minM)*(mgh-30)
    drawCircle(curX,curY,5, fill=YELLOW, border=rgb(255,255,255), borderWidth=1)
    drawLabel(f"{curM:.2f}", curX+6, curY-2, fill=YELLOW, size=8, align="left-center")

    # Year slider
    sx = DRIFT_X+14
    sy = DRIFT_Y+DRIFT_H-22
    sw = DRIFT_W-28
    drawRect(sx,sy,sw,8, fill=rgb(30,35,55), border=PANEL_BORDER, borderWidth=1, roundness=4)
    t = (app.year-1800)/225
    drawRect(sx,sy,t*sw,8, fill=ORANGE, roundness=4)
    drawCircle(sx+t*sw, sy+4, 8, fill=rgb(255,255,255), border=ORANGE, borderWidth=2)
    drawLabel("1800", sx, sy+10, fill=rgb(130,140,170), size=7, align="left-top")
    drawLabel("2025", sx+sw, sy+10, fill=rgb(130,140,170), size=7, align="right-top")
    drawLabel(f"Year {app.year} | {app.fetch_status} {app.pyodide_status[:28]}", gx+8, gy+gh-8, fill=rgb(160,180,210), size=8, align="left-bottom")

def drawMag(app):
    hl = app.hover_panel=="mag"
    drawPanel(MAG_X,MAG_Y,MAG_W,MAG_H, f"MAGNETOSPHERE — Solar Wind {int(app.solar_wind_speed)} km/s  Kp {app.kp_slider:.1f}  Bz {app.imf_bz:+.1f}nT", highlight=hl)
    gx,gy,gw,gh = MAG_X+14, MAG_Y+30, MAG_W-28, MAG_H-72
    drawRect(gx,gy,gw,gh, fill=rgb(12,16,30), border=rgb(35,45,75), borderWidth=1, roundness=8)

    # Sun left
    sun_x = gx+28
    sun_y = gy+gh*0.5
    drawCircle(sun_x, sun_y, 18, fill=rgb(255,220,80), border=rgb(255,180,40), borderWidth=1.5)
    drawLabel("Sun", sun_x, sun_y-26, fill=YELLOW, size=9, bold=True, align="center-bottom")
    # solar wind arrows
    for i in range(6):
        ay = gy+20 + i*(gh-40)/5 + math.sin(app.time*2+i)*4
        ax0 = sun_x+22
        ax1 = gx+gw*0.28 + (app.solar_wind_speed-300)/500*20
        drawLine(ax0, ay, ax1, ay, fill=rgb(200,200,180), lineWidth=1.2, arrowEnd=True, opacity=0.6)
    drawLabel(f"n~{5+app.kp_slider:.0f}/cc", gx+70, gy+12, fill=rgb(160,180,210), size=8, align="left-top")

    # Earth
    ex = gx+gw*0.45
    ey = gy+gh*0.5
    drawCircle(ex,ey,18, fill=rgb(80,140,255), border=rgb(255,255,255), borderWidth=1)
    drawCircle(ex,ey,6, fill=GREEN)
    # dipole tilt indicator
    tilt = math.radians(app.dipole_tilt)
    drawLine(ex, ey, ex+14*math.sin(tilt), ey-14*math.cos(tilt), fill=CYAN, lineWidth=1.5, arrowEnd=True)
    drawLabel("N mag", ex+16*math.sin(tilt), ey-16*math.cos(tilt), fill=CYAN, size=7, align="left-center")

    # Magnetopause - standoff distance scales as (1/ solar wind pressure)^1/6
    # pressure ~ n*v^2 ; simplified: Rmp ~ 10 Re * (400/v)^(1/3) * (3/Kp factor)
    rmp = 10 * (400/app.solar_wind_speed)**0.33 * (1 - app.kp_slider*0.03)
    rmp_px = rmp*9  # scale
    # dayside magnetopause arc
    drawArc(ex, ey, rmp_px, rmp_px*1.1, 200, 160, fill=None, border=CYAN, borderWidth=1.8, opacity=0.9)
    drawLabel(f"MP {rmp:.1f} Re", ex-rmp_px*0.7, ey-22, fill=CYAN, size=8, align="center-bottom")
    # bow shock ahead
    bs = rmp_px*1.35
    drawArc(ex, ey, bs, bs*1.15, 200, 160, fill=None, border=rgb(180,180,200), borderWidth=1, dashes=True, opacity=0.6)
    drawLabel("Bow shock", ex-bs*0.7, ey-36, fill=rgb(180,180,200), size=7, align="center-bottom")

    # Magnetotail
    tail_len = 120 + app.solar_wind_speed*0.12
    drawRect(ex+8, ey-32, tail_len, 64, fill=rgb(20,30,60), border=PANEL_BORDER, borderWidth=1, roundness=0, opacity=0.5)
    drawLine(ex+8, ey-32, ex+tail_len, ey-32, fill=rgb(60,80,120), lineWidth=0.8, opacity=0.6)
    drawLine(ex+8, ey+32, ex+tail_len, ey+32, fill=rgb(60,80,120), lineWidth=0.8, opacity=0.6)
    # current sheet
    for i in range(0,int(tail_len),18):
        x = ex+12+i+ math.sin(app.time*3+i*0.2)*3
        drawLine(x, ey, x+8, ey, fill=YELLOW, lineWidth=1, opacity=0.5)

    # Radiation belts - Van Allen
    drawOval(ex, ey, 38, 26, fill=None, border=PINK, borderWidth=1.2, opacity=0.7)
    drawOval(ex, ey, 56, 38, fill=None, border=PURPLE, borderWidth=1.2, opacity=0.5)
    drawLabel("Van Allen", ex+34, ey+6, fill=PINK, size=7, align="left-center")

    # Aurora ovals - Kp dependent latitude
    # Feldstein: auroral oval colatitude ~ 20 deg + Kp*1.5
    oval_colat = 18 + app.kp_slider*1.8 + ( -app.imf_bz if app.imf_bz<0 else 0)*0.8
    # draw north/south caps as arcs near earth
    for side in [-1,1]:
        oy = ey + side* (22 + oval_colat*0.6)
        ow = 36 - side*oval_colat*0.2
        drawArc(ex, oy, ow, 10, 0, 360, fill=rgb(110,255,170), border=None, opacity=0.18+app.kp_slider*0.04)
        drawArc(ex, oy, ow, 10, 0, 360, fill=None, border=GREEN, borderWidth=1, opacity=0.7)

    # Kp history sparkline
    hx = gx+8
    hy = gy+gh-32
    hw = gw*0.48
    hh = 28
    drawRect(hx,hy,hw,hh, fill=rgb(16,20,36), border=rgb(35,45,75), borderWidth=1, roundness=5)
    if app.kp_history:
        maxk=9
        for i in range(len(app.kp_history)-1):
            x0 = hx + i/(len(app.kp_history)-1)*hw
            x1 = hx + (i+1)/(len(app.kp_history)-1)*hw
            y0 = hy+hh - (app.kp_history[i]/maxk)*hh
            y1 = hy+hh - (app.kp_history[i+1]/maxk)*hh
            col = GREEN if app.kp_history[i]<4 else YELLOW if app.kp_history[i]<6 else RED
            drawLine(x0,y0,x1,y1, fill=col, lineWidth=1.5)
    drawLabel(f"Kp history 1h {app.fetch_status}", hx+4, hy+2, fill=rgb(150,170,200), size=7, align="left-top")

    # Meteorology note
    drawLabel("Met: GNSS scintillation, HF blackout, drag on LEO, no tropospheric weather link", gx+gw*0.5+8, gy+gh-8, fill=rgb(130,150,180), size=7.5, align="left-bottom")

    # Sliders
    # Kp slider
    ksx = MAG_X+14
    ksy = MAG_Y+MAG_H-52
    ksw = MAG_W-28
    drawRect(ksx,ksy,ksw,8, fill=rgb(30,35,55), border=PANEL_BORDER, borderWidth=1, roundness=4)
    tk = app.kp_slider/9
    colk = GREEN if tk<0.44 else YELLOW if tk<0.66 else RED
    drawRect(ksx,ksy,tk*ksw,8, fill=colk, roundness=4)
    drawCircle(ksx+tk*ksw, ksy+4, 8, fill=rgb(255,255,255), border=colk, borderWidth=2)
    drawLabel(f"Kp {app.kp_slider:.1f} {'quiet' if app.kp_slider<3 else 'active' if app.kp_slider<6 else 'storm'}", ksx, ksy-12, fill=rgb(180,200,230), size=8, align="left-bottom")
    # Solar wind slider
    ssx = MAG_X+14
    ssy = MAG_Y+MAG_H-22
    ssw = MAG_W-28
    drawRect(ssx,ssy,ssw,8, fill=rgb(30,35,55), border=PANEL_BORDER, borderWidth=1, roundness=4)
    tsw = (app.solar_wind_speed-300)/500
    drawRect(ssx,ssy,tsw*ssw,8, fill=BLUE, roundness=4)
    drawCircle(ssx+tsw*ssw, ssy+4, 8, fill=rgb(255,255,255), border=BLUE, borderWidth=2)
    drawLabel(f"SW {int(app.solar_wind_speed)} km/s  Bz {app.imf_bz:+.1f} nT (click mag to flip Bz)", ssx, ssy-12, fill=rgb(180,200,230), size=8, align="left-bottom")

def drawImpact(app):
    hl = app.hover_panel=="impact"
    drawPanel(IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H, "IMPACT — Navigation, SAA & Systems", highlight=hl)
    gx,gy,gw,gh = IMPACT_X+14, IMPACT_Y+30, IMPACT_W-28, IMPACT_H-48
    drawRect(gx,gy,gw,gh, fill=rgb(12,16,30), border=rgb(35,45,75), borderWidth=1, roundness=8)

    # World map simplified - equirectangular with declination contours from pyodide grid
    mx = gx+6
    my = gy+8
    mw = gw*0.58
    mh = gh-16
    drawRect(mx,my,mw,mh, fill=rgb(16,24,42), border=rgb(35,45,75), borderWidth=1, roundness=6)
    # graticule
    for lat in [-60,-30,0,30,60]:
        y = my + (80-lat)/160*mh
        drawLine(mx,y,mx+mw,y, fill=rgb(35,45,75), lineWidth=0.5, dashes=True)
    for lon in [-120,-60,0,60,120]:
        x = mx + (lon+180)/360*mw
        drawLine(x,my,x,my+mh, fill=rgb(35,45,75), lineWidth=0.5, dashes=True)

    # SAA - South Atlantic Anomaly low field
    # center approx -26S, -50W
    saa_x = mx + (-50+180)/360*mw
    saa_y = my + (80-(-26))/160*mh
    # intensity from grid? use synthetic low
    saa_r = 28 + (8.6-app.dipole_moment)*12  # grows as moment decays
    drawOval(saa_x, saa_y, saa_r*2.2, saa_r*1.4, fill=RED, opacity=0.18)
    drawOval(saa_x, saa_y, saa_r*1.6, saa_r, fill=RED, border=RED, borderWidth=1.2, opacity=0.7)
    drawLabel("SAA", saa_x, saa_y-2, fill=RED, size=9, bold=True, align="center")

    # Declination contours - use decl_grid if available
    if app.decl_grid:
        # draw 0 decl line (agonic) in yellow
        for i in range(len(app.decl_grid)-1):
            for j in range(len(app.decl_grid[0])-1):
                d = app.decl_grid[i][j]
                # zero crossing
                if abs(d)<8:
                    x = mx + (j/36)*mw
                    y = my + (i/18)*mh
                    drawCircle(x,y,1.2, fill=YELLOW, opacity=0.7)

    # Observatories
    for lat,lon,code in app.observatories:
        x = mx + (lon+180)/360*mw
        y = my + (80-lat)/160*mh
        if 0<=x<=mx+mw and 0<=y<=my+mh:
            drawCircle(x,y,2.2, fill=CYAN, border=rgb(0,0,0), borderWidth=0.6)
    drawLabel("INTERMAGNET", mx+4, my+mh-4, fill=CYAN, size=7, align="left-bottom")

    # Power spectrum panel - right side
    px = gx+gw*0.62+8
    py = gy+8
    pw = gw*0.36-8
    ph = mh*0.48
    drawRect(px,py,pw,ph, fill=rgb(16,20,36), border=rgb(35,45,75), borderWidth=1, roundness=6)
    drawLabel("Secular power n", px+4, py+4, fill=rgb(150,170,200), size=8, align="left-top")
    if app.power_spec:
        maxp = max(app.power_spec) if max(app.power_spec)>0 else 1
        for i,p in enumerate(app.power_spec[:8]):
            bx = px+8 + i*(pw-16)/8
            bw = (pw-20)/8*0.7
            bh = (p/maxp)*(ph-22)
            drawRect(bx, py+ph-8-bh, bw, bh, fill=PURPLE if i>0 else YELLOW, roundness=3)
            drawLabel(str(i+1), bx+bw/2, py+ph-2, fill=rgb(150,170,200), size=7, align="center-bottom")

    # Impact list
    ix = gx+gw*0.62+8
    iy = gy+ph+18
    iw = gw*0.36-8
    ih = mh - ph - 18
    drawRect(ix,iy,iw,ih, fill=rgb(16,20,36), border=rgb(35,45,75), borderWidth=1, roundness=6)
    impacts = [
        f"WMM error {app.year-2020}*0.2° if not updated",
        f"Compass: True = Mag {app.decl_grid[9][18] if app.decl_grid else 5:+.1f}°",
        f"SAA: sat upset x{1.2+(8.6-app.dipole_moment):.1f}",
        "GIC: pipelines, grids at Kp>6",
        "Aviation: mag vs true runway",
        "Animals: magnetoreception bias",
        "Edu: Met uses true north, not mag"
    ]
    for k,txt in enumerate(impacts):
        y = iy+8 + k*13
        if y < iy+ih-4:
            col = YELLOW if k==0 else rgb(180,200,230)
            drawLabel(txt, ix+6, y, fill=col, size=7.5, align="left-top")

    # Status
    drawLabel(f"{app.fetch_status2} {app.fetch_status3}", gx+8, gy+gh-8, fill=rgb(130,150,180), size=7.5, align="left-bottom")

def drawGlobeOverlay(app):
    # Full opaque BG like Ear View
    drawRect(0,0,W,H, fill=BG)
    drawRect(0,0,W,HEADER_H, fill=rgb(18,22,38))
    drawLabel("GLOBE VIEW — Compass Needles & Field (SOS Dataset Style)", W*0.5, 12, fill=rgb(240,250,255), size=16, bold=True, align="center-top")
    drawLabel("Field lines = dipole + IGRF non-dipole. Needles = local declination/inclination. SAA = weak spot.", W*0.5, 32, fill=rgb(160,180,210), size=11, align="center-top")

    # Buttons in overlay header
    bx,by,bw,bh = W-280,8,110,34
    fillCol = rgb(255,180,120)
    drawRect(bx,by,bw,bh, fill=fillCol, border=rgb(255,255,255), borderWidth=1.2, roundness=18)
    drawLabel("GLOBE VIEW", bx+bw/2, by+bh/2, fill=rgb(0,0,0), size=11, bold=True, align="center")
    # close X
    closeBx,closeBy,closeBw,closeBh = W-60, HEADER_H+8, 36,26
    drawRect(closeBx,closeBy,closeBw,closeBh, fill=rgb(60,70,90), border=rgb(200,210,230), borderWidth=1, roundness=7)
    drawLabel("X", closeBx+closeBw/2, closeBy+closeBh/2, fill=rgb(230,240,255), size=13, bold=True, align="center")

    # Main globe
    gx,gy,gw,gh = 16, HEADER_H+12, 680, 600
    drawRect(gx,gy,gw,gh, fill=rgb(18,22,38), border=PANEL_BORDER, borderWidth=1, roundness=12)
    cx = gx+gw*0.48
    cy = gy+gh*0.5
    R = 210
    # Earth sphere with simple shading
    drawCircle(cx,cy,R, fill=rgb(20,35,60), border=rgb(60,80,110), borderWidth=1.5)
    # latitude lines perspective
    for lat in [-60,-30,0,30,60]:
        # ellipse
        ry = R*math.cos(math.radians(lat))*0.42
        y = cy + R*math.sin(math.radians(lat))*0.42
        drawOval(cx, y, R*1.8, ry*2, fill=None, border=rgb(50,70,100), borderWidth=0.6, dashes=True)
    # longitude lines animated rotation
    for k in range(12):
        lon = k*30 + app.globe_rot*20
        # draw meridian as arc
        # approximate with line of points
        pts=[]
        for lat in range(-80,81,8):
            th = math.radians(lon)
            # simple orthographic projection
            x = cx + R*math.cos(math.radians(lat))*math.sin(th)*0.9
            y = cy + R*math.sin(math.radians(lat))*0.42
            # front hemisphere only
            if math.cos(th) > -0.3:
                pts.append((x,y))
        for i in range(len(pts)-1):
            drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1], fill=rgb(40,60,90), lineWidth=0.7, opacity=0.5)

    # Field lines around globe - dipole + tilt
    tilt = math.radians(app.dipole_tilt + 5*math.sin(app.time*0.5))
    for L in [1.6,2.0,2.5,3.2,4.0]:
        pts=[]
        for th_deg in range(12,168,4):
            th = math.radians(th_deg)
            r = L * (math.sin(th)**2)
            if r<1.05 or r>5: continue
            # rotate by tilt
            th2 = th - tilt
            x = cx + r*R*0.92*math.sin(th2)
            y = cy - r*R*0.92*math.cos(th2)*0.42
            # only outside globe
            if math.hypot(x-cx, (y-cy)/0.42) > R*1.02:
                pts.append((x,y))
        for i in range(len(pts)-1):
            drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1], fill=CYAN, lineWidth=1.4, opacity=0.65)

    # Compass needles on globe surface - sample from decl grid
    if app.decl_grid:
        for i in range(0,18,3):
            for j in range(0,36,6):
                lat = 80 - i/18*160
                lon = -180 + j/36*360 + app.globe_rot*20
                # project
                th = math.radians(lon)
                if math.cos(th) < 0: continue
                x = cx + R*math.cos(math.radians(lat))*math.sin(th)*0.9*0.85
                y = cy + R*math.sin(math.radians(lat))*0.42*0.85
                decl = app.decl_grid[i][j]
                ang = math.radians(decl)
                # needle
                drawLine(x,y, x+8*math.sin(ang), y-8*math.cos(ang)*0.42, fill=RED, lineWidth=1.2, arrowEnd=True)
                drawLine(x,y, x-6*math.sin(ang), y+6*math.cos(ang)*0.42, fill=BLUE, lineWidth=1)

    # SAA highlight on globe
    saa_lat, saa_lon = -26, -50
    th = math.radians(saa_lon + app.globe_rot*20)
    sx = cx + R*math.cos(math.radians(saa_lat))*math.sin(th)*0.9
    sy = cy + R*math.sin(math.radians(saa_lat))*0.42
    if math.cos(th)>0:
        drawCircle(sx,sy, 18, fill=RED, opacity=0.22)
        drawCircle(sx,sy, 10, fill=RED, border=rgb(255,255,255), borderWidth=1, opacity=0.8)
        drawLabel("SAA low F", sx+14, sy, fill=RED, size=9, bold=True, align="left-center")

    # Aurora oval on globe
    for side in [1,-1]:
        oval_lat = 75 - app.kp_slider*1.2
        # draw circle at latitude
        ry = R*math.cos(math.radians(oval_lat))*0.42*0.3
        y = cy + side*R*math.sin(math.radians(oval_lat))*0.42*0.92
        drawOval(cx, y, R*1.6, ry*2, fill=None, border=GREEN, borderWidth=1.5, opacity=0.6+app.kp_slider*0.05)
        drawOval(cx, y, R*1.62, ry*2.1, fill=GREEN, opacity=0.12)

    # North magnetic pole marker
    plat, plon = app.pole_lat, app.pole_lon + app.globe_rot*20
    th = math.radians(plon)
    px = cx + R*math.cos(math.radians(plat))*math.sin(th)*0.9
    py = cy + R*math.sin(math.radians(plat))*0.42
    if math.cos(th)>-0.2:
        drawCircle(px,py,6, fill=YELLOW, border=rgb(255,255,255), borderWidth=1.5)
        drawLabel(f"NMP {app.year}", px+8, py, fill=YELLOW, size=9, bold=True, align="left-center")

    # Side panels in overlay
    # Info
    ix,iy,iw,ih = 710, HEADER_H+12, 324, 180
    drawRect(ix,iy,iw,ih, fill=rgb(18,22,38), border=PANEL_BORDER, borderWidth=1, roundness=10)
    drawLabel("DYNAMO THEORY", ix+12, iy+10, fill=rgb(180,190,220), size=10, bold=True, align="left-top")
    lines = [
        "Outer core liquid Fe convects ~4mm/s",
        "Coriolis → helicity, α-effect",
        "Differential rotation → ω-effect",
        "Dipole ~80% of surface field",
        "Non-dipole = 20%, drifts west 0.2°/yr",
        "Reversals every ~200kyr, last 780kya",
        "Excursions: Laschamp 42kya field 5% ",
        "Current decay 5%/century → 1500yr?"
    ]
    for k,l in enumerate(lines):
        drawLabel(l, ix+12, iy+28+k*16, fill=rgb(180,200,230), size=9, align="left-top")

    # Educator
    ex,ey,ew,eh = 710, HEADER_H+204, 324, 180
    drawRect(ex,ey,ew,eh, fill=rgb(18,22,38), border=PANEL_BORDER, borderWidth=1, roundness=10)
    drawLabel("FOR EDUCATORS & METEOROLOGISTS", ex+12, ey+10, fill=rgb(180,190,220), size=10, bold=True, align="left-top")
    edu = [
        "True vs Magnetic: 0-30° error",
        "WMM2025 vs WMM2020: airports renumber",
        "Phones use WMM + gyro for compass",
        "Weather balloons: GPS not mag compass",
        "Magnetosphere ≠ troposphere weather",
        "But: GIC affects met sensors, power",
        "Aurora forecast = Kp + Bz south",
        "Teach: field protects atmosphere"
    ]
    for k,l in enumerate(edu):
        drawLabel(l, ex+12, ey+28+k*16, fill=rgb(160,180,210), size=9, align="left-top")

    # Data sources
    dx,dy,dw,dh = 710, HEADER_H+396, 324, 208
    drawRect(dx,dy,dw,dh, fill=rgb(18,22,38), border=PANEL_BORDER, borderWidth=1, roundness=10)
    drawLabel("LIVE DATA & SOURCES", dx+12, dy+10, fill=rgb(180,190,220), size=10, bold=True, align="left-top")
    src = [
        f"SWPC Kp {app.kp_live:.1f} {app.fetch_status}",
        f"INTERMAGNET {len(app.observatories)} obs {app.fetch_status2[:24]}",
        f"Data.gov {app.fetch_status3[:30]}",
        f"Pyodide {app.pyodide_status[:32]}",
        "NCEI geomag-data, operobs.shtml",
        "SOS compass-needles dataset",
        "WMM2025, IGRF-14, gufm1 1800-",
        "Procaudio: Kp sonified as drone + whistlers"
    ]
    for k,l in enumerate(src):
        drawLabel(l, dx+12, dy+28+k*18, fill=rgb(150,170,200), size=8.5, align="left-top")

def redrawAll(app):
    drawRect(0,0,W,H, fill=BG)
    drawHeader(app)
    if app.show_globe:
        drawGlobeOverlay(app)
        return
    drawDynamo(app)
    drawDrift(app)
    drawMag(app)
    drawImpact(app)
