
from scs import *
from browser import window, aio
from extensions.proc_audio import AudioEngine
from extensions.fetch import fetch_json, fetch_text, fetch
from extensions.pyodide import run_python
import math
import random

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
YELLOW = rgb(255,230,110)
GREEN = rgb(110,255,170)
ORANGE = rgb(255,160,80)
RED = rgb(255,90,90)
BLUE = rgb(110,180,255)
PINK = rgb(255,110,180)
PURPLE = rgb(160,120,255)

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

PYODIDE_CODE = '''
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
{'declination':decl.tolist(),'intensity':F.tolist(),'power_spectrum':power.tolist()}
'''

async def load_live_geomag(app):
    try:
        kp_data=await fetch_json('https://services.swpc.noaa.gov/json/planetary_k_index_1m.json')
        latest=kp_data[-1]; app.kp_live=float(latest.get('Kp',3)); app.kp_history=[float(d.get('Kp',0)) for d in kp_data[-60:]]
        app.log_fetch=f"Kp OK {app.kp_live:.1f}"
    except Exception as e:
        app.log_fetch=f"fetch_json Kp failed: {e}"; print(f"fetch_json Kp failed: {e}")
    try:
        txt=await fetch_text('https://www.intermagnet.org/data_download.html')
        app.log_fetch2=f"INTERMAGNET OK {len(txt)}"
    except Exception as e:
        app.log_fetch2=f"fetch_text INTERMAGNET failed: {e}"; print(f"fetch_text INTERMAGNET failed: {e}")
    try:
        meta=await fetch_json('https://catalog.data.gov/api/3/action/package_show?id=data-on-the-earths-magnetic-field-and-its-secular-change-since-1800')
        app.log_fetch3=f"Data.gov OK {meta.get('title','')[:30]}"
    except Exception as e:
        app.log_fetch3=f"fetch_json Data.gov failed: {e}"; print(f"fetch_json Data.gov failed: {e}")
    try:
        resp=await fetch('https://www.ncei.noaa.gov/products/geomagnetic-data',method='GET',mode='cors')
        t=await resp.text(); app.log_fetch4=f"fetch NCEI OK {len(t)}"
    except Exception as e:
        app.log_fetch4=f"fetch NCEI failed: {e}"; print(f"fetch NCEI failed: {e}")
    aio.run(compute_with_pyodide(app))

async def compute_with_pyodide(app):
    try:
        code=f"year={app.year}\nmoment={app.dipole_moment}\npole_lat={app.pole_lat}\npole_lon={app.pole_lon}\n"+PYODIDE_CODE
        result=await run_python(code)
        app.decl_grid=result.get('declination'); app.power_spec=result.get('power_spectrum')
        app.log_pyodide=f"pyodide OK {len(app.decl_grid)}x{len(app.decl_grid[0])}"
    except Exception as e:
        app.log_pyodide=f"run_python failed: {e}"; print(f"run_python failed: {e}")

def play_kp_sonification(app):
    try:
        app.audio_engine.resume()
        base=55+app.kp_live*18+app.kp_slider*10
        app.audio_engine.play("magnetosphere.ambient",seed=int(base),spatial=False)
        app.audio_engine.play("magnetosphere.pulse",seed=int(app.solar_wind_speed+app.kp_slider*10))
        app.audio_engine.play("ui.sweep",seed=int(app.kp_live*20+app.year%100))
        app.is_playing=True; app.log_audio=f"AudioEngine play OK Kp {app.kp_slider:.1f}"
    except Exception as e:
        app.log_audio=f"AudioEngine failed: {e}"; print(f"AudioEngine failed: {e}")

def stop_sonification(app):
    try:
        app.audio_engine.stop(); app.is_playing=False; app.log_audio="AudioEngine stop OK"
    except Exception as e:
        app.log_audio=f"AudioEngine stop failed: {e}"; print(f"AudioEngine stop failed: {e}")

def onAppStart(app):
    app.width=W; app.height=H; app.stepsPerSecond=60; app.background=BG
    app.year=2025; app.dipole_tilt=10.5; app.dipole_moment=interp_moment(2025); app.pole_lat,app.pole_lon=interp_pole(2025)
    app.kp_live=3.2; app.kp_slider=3.0; app.solar_wind_speed=420; app.imf_bz=-2.0
    app.log_fetch="Idle"; app.log_fetch2=""; app.log_fetch3=""; app.log_fetch4=""; app.log_pyodide="Initializing"; app.log_audio="Idle"
    app.decl_grid=None; app.power_spec=[1,0.7,0.5,0.35,0.22,0.15,0.1,0.06]; app.kp_history=[random.uniform(0,4) for _ in range(60)]
    app.dragging_year=False; app.dragging_kp=False; app.dragging_sw=False; app.hover_panel=None; app.show_globe=False; app.globe_rot=0; app.is_playing=False
    app.insight="Drag YEAR 1800-2025. Kp drives magnetosphere + aurora. SAA grows as dipole weakens."
    app.audio_engine=AudioEngine(quality="high",seed=90210)
    app.observatories=[(65.1,-19.6,"LRV"),(60.4,5.3,"DOB"),(58.7,-3.7,"LER"),(55.3,-3.2,"ESK"),(50.3,4.6,"DOU"),(52.0,-4.5,"ABK"),(40.3,-4.3,"SPT"),(36.9,-2.0,"SFS"),(28.0,-16.5,"GUI"),(64.7,-147.8,"CMO"),(47.6,-122.3,"NEW"),(38.2,-122.3,"FRN"),(-33.3,26.5,"HER"),(-23.2,-45.0,"VSS"),(-31.4,115.9,"GNG"),(35.6,140.2,"KAK"),(-43.7,172.3,"EYR")]
    aio.run(load_live_geomag(app)); aio.run(compute_with_pyodide(app)); app.time=0

def onStep(app):
    app.time+=0.02; app.globe_rot+=0.008
    if app.is_playing and int(app.time*10)%50==0:
        try:
            app.audio_engine.play("magnetosphere.pulse",seed=int(app.solar_wind_speed+app.kp_slider*10))
        except Exception as e:
            print(f"onStep AudioEngine failed: {e}")

def pointInRect(px,py,rx,ry,rw,rh): return rx<=px<=rx+rw and ry<=py<=ry+rh

def onMousePress(app,mx,my):
    if pointInRect(mx,my,W-280,8,110,34): app.show_globe=not app.show_globe; return
    if pointInRect(mx,my,W-156,8,70,34):
        if app.is_playing: stop_sonification(app)
        else: play_kp_sonification(app)
        return
    if pointInRect(mx,my,W-74,8,58,34): aio.run(load_live_geomag(app)); return
    if app.show_globe:
        if pointInRect(mx,my,W-60,HEADER_H+8,36,26): app.show_globe=False
        return
    if pointInRect(mx,my,DRIFT_X+14,DRIFT_Y+DRIFT_H-22,DRIFT_W-28,24): app.dragging_year=True; update_year_from_x(app,mx); return
    if pointInRect(mx,my,MAG_X+14,MAG_Y+MAG_H-52,MAG_W-28,24): app.dragging_kp=True; update_kp_from_x(app,mx); return
    if pointInRect(mx,my,MAG_X+14,MAG_Y+MAG_H-22,MAG_W-28,24): app.dragging_sw=True; update_sw_from_x(app,mx); return
    if pointInRect(mx,my,DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H):
        app.dipole_tilt=11+3*math.sin(app.time*2); app.insight=f"Dynamo tilt {app.dipole_tilt:.1f} deg. Secular variation driven by non-dipole."; aio.run(compute_with_pyodide(app))
    if pointInRect(mx,my,MAG_X,MAG_Y,MAG_W,MAG_H): app.imf_bz=-app.imf_bz; app.insight=f"Bz {app.imf_bz:+.1f}nT {'southward reconnection' if app.imf_bz<0 else 'northward quiet'}"

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
    elif key.lower()=='r': aio.run(load_live_geomag(app))
    elif key.lower()=='t': app.year=clamp(app.year+1,1800,2025); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year); aio.run(compute_with_pyodide(app))
    elif key.lower()=='e': app.year=clamp(app.year-1,1800,2025); app.pole_lat,app.pole_lon=interp_pole(app.year); app.dipole_moment=interp_moment(app.year); aio.run(compute_with_pyodide(app))

def drawPanel(x,y,w,h,title="",highlight=False):
    fill=PANEL_BG if not highlight else rgb(26,30,52)
    drawRect(x,y,w,h,fill=fill,border=PANEL_BORDER,borderWidth=1,roundness=10)
    if title:
        drawRect(x+8,y+6,w-16,16,fill=rgb(28,32,52),roundness=5)
        drawLabel(title,x+14,y+14,fill=rgb(180,190,220),size=11,bold=True,align="left-top")
def drawHeader(app):
    drawRect(0,0,W,HEADER_H,fill=rgb(18,22,38))
    drawLabel("EMF LAB — Dynamo, Drift & Impact",W*0.38,10,fill=rgb(240,250,255),size=15,bold=True,align="center-top")
    drawLabel(f"{app.year} M {app.dipole_moment:.2f}e22 Pole {app.pole_lat:.1f}N {app.pole_lon:.1f}E Tilt {app.dipole_tilt:.1f}deg Kp {app.kp_live:.1f}/{app.kp_slider:.1f} SW {int(app.solar_wind_speed)}",W*0.38,30,fill=rgb(160,180,210),size=10,align="center-top")
    drawRect(12,46,W-340,16,fill=rgb(35,60,85),border=CYAN,borderWidth=1,roundness=6,opacity=0.9)
    drawLabel(app.insight,W*0.5-160,54,fill=rgb(200,240,255),size=9.5,bold=True,align="center")
    bx,by,bw,bh=W-280,8,110,34; fillCol=rgb(88,240,255) if not app.show_globe else rgb(255,180,120)
    drawRect(bx,by,bw,bh,fill=fillCol,border=rgb(255,255,255),borderWidth=1.2,roundness=18)
    drawLabel("GLOBE VIEW",bx+bw/2,by+bh/2,fill=rgb(0,0,0),size=11,bold=True,align="center")
    px,py,pw,ph=W-156,8,70,34; pfill=rgb(90,255,160) if not app.is_playing else rgb(255,90,90)
    drawRect(px,py,pw,ph,fill=pfill,border=rgb(255,255,255),borderWidth=1.2,roundness=18)
    drawLabel("STOP" if app.is_playing else "PLAY",px+pw/2,py+ph/2,fill=rgb(0,0,0) if not app.is_playing else rgb(255,255,255),size=11,bold=True,align="center")
    lx,ly,lw,lh=W-74,8,58,34; drawRect(lx,ly,lw,lh,fill=rgb(45,55,85),border=PANEL_BORDER,borderWidth=1,roundness=18); drawLabel("LIVE",lx+lw/2,ly+lh/2,fill=rgb(200,220,255),size=10,bold=True,align="center")
def drawDynamo(app):
    hl=app.hover_panel=="dynamo"; drawPanel(DYNAMO_X,DYNAMO_Y,DYNAMO_W,DYNAMO_H,f"DYNAMO tilt {app.dipole_tilt:.1f}deg",highlight=hl)
    gx,gy,gw,gh=DYNAMO_X+14,DYNAMO_Y+30,DYNAMO_W-28,DYNAMO_H-48; drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=8)
    cx=gx+gw*0.38; cy=gy+gh*0.52; earth_r=92
    drawCircle(cx,cy,earth_r,fill=rgb(45,35,25),border=rgb(80,60,40),borderWidth=1)
    outer_r=earth_r*0.55; drawCircle(cx,cy,outer_r,fill=rgb(200,90,20),border=rgb(255,160,80),borderWidth=1.2)
    for k in range(6):
        ang=k*60+app.time*18; rad=outer_r*0.62; x=cx+rad*math.cos(math.radians(ang)); y=cy+rad*math.sin(math.radians(ang))*0.75
        ax=math.cos(math.radians(ang+90))*10; ay=math.sin(math.radians(ang+90))*7
        drawLine(x,y,x+ax,y+ay,fill=ORANGE,lineWidth=1.5,arrowEnd=True)
    tilt=math.radians(app.dipole_tilt)
    for L in [1.4,1.8,2.3,3.0]:
        pts=[]; line=dipole_field_line(L,90)
        for r,theta in line:
            th=theta-tilt; px=cx+r*earth_r*0.85*math.sin(th); py=cy-r*earth_r*0.85*math.cos(th)*0.9
            if math.hypot(px-cx,py-cy)>earth_r*0.98 or abs(theta-math.pi/2)>0.6: pts.append((px,py))
        for i in range(len(pts)-1): drawLine(pts[i][0],pts[i][1],pts[i+1][0],pts[i+1][1],fill=CYAN,lineWidth=1.6,opacity=0.7)
def drawDrift(app):
    hl=app.hover_panel=="drift"; drawPanel(DRIFT_X,DRIFT_Y,DRIFT_W,DRIFT_H,"SECULAR 1800-2025",highlight=hl)
    gx,gy,gw,gh=DRIFT_X+14,DRIFT_Y+30,DRIFT_W-28,DRIFT_H-68; drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=8)
    pcx=gx+gw*0.34; pcy=gy+gh*0.48; pr=78; drawCircle(pcx,pcy,pr,fill=rgb(16,20,36),border=rgb(50,60,90),borderWidth=0.8)
    prev=None
    for y,lat,lon in N_POLE_HISTORY:
        r=(90-lat)/20*pr; th=math.radians(lon+90); x=pcx+r*math.cos(th); y_=pcy+r*math.sin(th)
        t=(y-1800)/225; col=rgb(int(lerp(80,255,t)),int(lerp(180,90,t)),int(lerp(255,80,t)))
        if prev: drawLine(prev[0],prev[1],x,y_,fill=col,lineWidth=2.2,opacity=0.85)
        drawCircle(x,y_,3.5,fill=col,border=rgb(0,0,0),borderWidth=0.8); prev=(x,y_)
    sx=DRIFT_X+14; sy=DRIFT_Y+DRIFT_H-22; sw=DRIFT_W-28; drawRect(sx,sy,sw,8,fill=rgb(30,35,55),border=PANEL_BORDER,borderWidth=1,roundness=4)
    t=(app.year-1800)/225; drawRect(sx,sy,t*sw,8,fill=ORANGE,roundness=4); drawCircle(sx+t*sw,sy+4,8,fill=rgb(255,255,255),border=ORANGE,borderWidth=2)
    drawLabel(f"{app.log_fetch} | {app.log_pyodide}",gx+8,gy+gh-8,fill=rgb(160,180,210),size=7,align="left-bottom")
def drawMag(app):
    hl=app.hover_panel=="mag"; drawPanel(MAG_X,MAG_Y,MAG_W,MAG_H,f"MAGNETOSPHERE Kp {app.kp_slider:.1f}",highlight=hl)
    gx,gy,gw,gh=MAG_X+14,MAG_Y+30,MAG_W-28,MAG_H-72; drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=8)
    sun_x=gx+28; sun_y=gy+gh*0.5; drawCircle(sun_x,sun_y,18,fill=rgb(255,220,80),border=rgb(255,180,40),borderWidth=1.5)
    ex=gx+gw*0.45; ey=gy+gh*0.5; drawCircle(ex,ey,18,fill=rgb(80,140,255),border=rgb(255,255,255),borderWidth=1)
    rmp=10*(400/app.solar_wind_speed)**0.33*(1-app.kp_slider*0.03); rmp_px=rmp*9
    drawArc(ex,ey,rmp_px,rmp_px*1.1,200,160,fill=None,border=CYAN,borderWidth=1.8,opacity=0.9)
    tail_len=120+app.solar_wind_speed*0.12; drawRect(ex+8,ey-32,tail_len,64,fill=rgb(20,30,60),border=PANEL_BORDER,borderWidth=1,roundness=0,opacity=0.5)
    ksx=MAG_X+14; ksy=MAG_Y+MAG_H-52; ksw=MAG_W-28; drawRect(ksx,ksy,ksw,8,fill=rgb(30,35,55),border=PANEL_BORDER,borderWidth=1,roundness=4)
    tk=app.kp_slider/9; colk=GREEN if tk<0.44 else YELLOW if tk<0.66 else RED
    drawRect(ksx,ksy,tk*ksw,8,fill=colk,roundness=4); drawCircle(ksx+tk*ksw,ksy+4,8,fill=rgb(255,255,255),border=colk,borderWidth=2)
def drawImpact(app):
    hl=app.hover_panel=="impact"; drawPanel(IMPACT_X,IMPACT_Y,IMPACT_W,IMPACT_H,"IMPACT SAA",highlight=hl)
    gx,gy,gw,gh=IMPACT_X+14,IMPACT_Y+30,IMPACT_W-28,IMPACT_H-48; drawRect(gx,gy,gw,gh,fill=rgb(12,16,30),border=rgb(35,45,75),borderWidth=1,roundness=8)
    mx=gx+6; my=gy+8; mw=gw*0.58; mh=gh-16; drawRect(mx,my,mw,mh,fill=rgb(16,24,42),border=rgb(35,45,75),borderWidth=1,roundness=6)
    saa_x=mx+(-50+180)/360*mw; saa_y=my+(80-(-26))/160*mh; saa_r=28+(8.6-app.dipole_moment)*12
    drawOval(saa_x,saa_y,saa_r*2.2,saa_r*1.4,fill=RED,opacity=0.18); drawOval(saa_x,saa_y,saa_r*1.6,saa_r,fill=RED,border=RED,borderWidth=1.2,opacity=0.7)
    drawLabel("SAA",saa_x,saa_y-2,fill=RED,size=9,bold=True,align="center")
    drawLabel(f"{app.log_fetch2} {app.log_fetch3} {app.log_fetch4} | {app.log_audio}",gx+8,gy+gh-8,fill=rgb(130,150,180),size=7,align="left-bottom")
def drawGlobeOverlay(app):
    drawRect(0,0,W,H,fill=BG); drawRect(0,0,W,HEADER_H,fill=rgb(18,22,38))
    drawLabel("GLOBE VIEW — Compass Needles (SOS)",W*0.5,12,fill=rgb(240,250,255),size=16,bold=True,align="center-top")
    bx,by,bw,bh=W-280,8,110,34; drawRect(bx,by,bw,bh,fill=rgb(255,180,120),border=rgb(255,255,255),borderWidth=1.2,roundness=18); drawLabel("GLOBE VIEW",bx+bw/2,by+bh/2,fill=rgb(0,0,0),size=11,bold=True,align="center")
    closeBx,closeBy,closeBw,closeBh=W-60,HEADER_H+8,36,26; drawRect(closeBx,closeBy,closeBw,closeBh,fill=rgb(60,70,90),border=rgb(200,210,230),borderWidth=1,roundness=7); drawLabel("X",closeBx+closeBw/2,closeBy+closeBh/2,fill=rgb(230,240,255),size=13,bold=True,align="center")
    gx,gy,gw,gh=16,HEADER_H+12,680,600; drawRect(gx,gy,gw,gh,fill=rgb(18,22,38),border=PANEL_BORDER,borderWidth=1,roundness=12)
    cx=gx+gw*0.48; cy=gy+gh*0.5; R=210; drawCircle(cx,cy,R,fill=rgb(20,35,60),border=rgb(60,80,110),borderWidth=1.5)
    tilt=math.radians(app.dipole_tilt)
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

def redrawAll(app):
    drawRect(0,0,W,H,fill=BG); drawHeader(app)
    if app.show_globe: drawGlobeOverlay(app); return
    drawDynamo(app); drawDrift(app); drawMag(app); drawImpact(app)
