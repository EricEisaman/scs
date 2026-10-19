from scs import *
import math

def getTempAtAlt(km):
    # US Standard Atmosphere simplified, Celsius
    if km <= 12:  # troposphere
        return 15 - 6.5*km
    elif km <= 50:  # stratosphere
        return -56.5 + (km-12)*(57.5/38)  # -56.5 to +1 at 50km
    elif km <= 85:  # mesosphere
        return 1 - (km-50)*2.6
    else:
        return -90 + (km-85)*3.5

def getPressureAtAlt(km):
    # P = P0 * exp(-h/H) , H~7.64km
    return 1013.25 * math.exp(-km/7.64)

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 30
    app.probeAlt = 5.0
    app.layers = [
        (0, 12, "TROPOSPHERE - weather", rgb(110,180,255)),
        (12, 50, "STRATOSPHERE - ozone warms", rgb(180,160,255)),
        (50, 85, "MESOSPHERE - coldest", rgb(140,140,190)),
        (85, 110, "THERMOSPHERE - aurora", rgb(60,60,80)),
    ]
    app.showComposition = True
    app.paused = False

def onMouseDrag(app, mx, my):
    if mx < 650:
        # map y to alt: 620px = 0km, 60px = 110km
        alt = (620 - my) / (620-60) * 110
        app.probeAlt = max(0, min(105, alt))

def onMousePress(app, mx, my):
    onMouseDrag(app, mx, my)

def onKeyPress(app, key):
    if key == 'space': app.paused = not app.paused
    if key.lower() == 'c': app.showComposition = not app.showComposition
    if key == 'up': app.probeAlt = min(105, app.probeAlt+2)
    if key == 'down': app.probeAlt = max(0, app.probeAlt-2)

def onStep(app):
    if app.paused: return
    pass

def redrawAll(app):
    # Background
    drawRect(0,0,1050,700, fill=rgb(18,22,35))
    
    # Tower
    towerX, towerW = 120, 200
    drawRect(towerX, 50, towerW, 580, fill=rgb(30,35,55), border=rgb(80,90,120), borderWidth=2)
    
    # Layers
    for bottom, top, name, col in app.layers:
        yTop = 630 - (top/110)*(580)
        yBot = 630 - (bottom/110)*(580)
        drawRect(towerX, yTop, towerW, yBot-yTop, fill=col, opacity=60, border=None)
        drawLabel(f"{bottom}-{top}km", towerX-2, (yTop+yBot)/2, size=9, fill=rgb(200,210,230), align='right')
    
    # Temp profile line
    for km in range(0, 110):
        t = getTempAtAlt(km)
        # map -90..+30 C to x offset 0..180
        x = towerX + towerW + 10 + (t+90)/120*180
        y = 630 - (km/110)*580
        drawCircle(x, y, 1.5, fill=rgb(255,160,60), border=None)
    drawLabel("Temperature profile ->", towerX+towerW+90, 45, size=10, fill=rgb(255,160,60), bold=True)

    # Probe
    probeY = 630 - (app.probeAlt/110)*580
    drawLine(towerX-20, probeY, towerX+towerW+200, probeY, fill=rgb(255,255,100), lineWidth=1, dashes=(6,4))
    drawCircle(towerX+towerW//2, probeY, 9, fill=rgb(255,255,100), border=rgb(0,0,0), borderWidth=2)
    drawLabel(f"PROBE {app.probeAlt:.1f} km", towerX+towerW//2, probeY-16, size=12, bold=True, fill=rgb(255,255,150))

    # Readouts - BIG for copying
    p = getPressureAtAlt(app.probeAlt)
    t = getTempAtAlt(app.probeAlt)
    drawRect(550, 60, 470, 240, fill=rgb(26,30,45), border=rgb(70,80,110), borderWidth=2)
    drawLabel("COPY TO GRAPH PAPER - PAUSE WITH SPACE", 785, 80, size=12, bold=True, fill=rgb(255,230,100))
    drawLabel(f"Altitude: {app.probeAlt:.1f} km", 580, 115, size=20, bold=True, fill=rgb(255,255,255), align='left')
    drawLabel(f"Pressure: {p:.1f} hPa", 580, 150, size=20, bold=True, fill=rgb(140,200,255), align='left')
    drawLabel(f"Temp: {t:.1f} C", 580, 185, size=20, bold=True, fill=rgb(255,140,80), align='left')
    drawLabel(f"Density ~ {100*math.exp(-app.probeAlt/7.64):.1f}% of sea level", 580, 215, size=14, fill=rgb(180,190,210), align='left')
    drawLabel("Task: every 10km write Alt / Pressure / Temp in table", 580, 245, size=11, fill=rgb(170,180,200), align='left')
    drawLabel("Then plot Pressure vs Alt and Temp vs Alt", 580, 265, size=11, fill=rgb(170,180,200), align='left')

    # Composition pie
    if app.showComposition:
        drawRect(550, 320, 470, 280, fill=rgb(26,30,45), border=rgb(70,80,110), borderWidth=2)
        drawLabel("ATMOSPHERE COMPOSITION - Constant to ~80km", 785, 340, size=12, bold=True, fill=rgb(230,240,255))
        cx, cy, r = 680, 470, 80
        # N2 78%, O2 21%, Ar 0.93, CO2 0.04
        data = [(78.08, "N2 78%", rgb(80,140,255)), (20.95, "O2 21%", rgb(255,80,80)), (0.93, "Ar", rgb(120,255,120)), (0.04, "CO2", rgb(255,210,60))]
        start = -90
        for pct, label, col in data:
            ang = pct/100*360
            # wedge as polygon approx
            drawArc(cx, cy, r*2, r*2, start, start+ang, fill=col, border=None)
            drawLabel(label, cx+ (r+30)*math.cos(math.radians(start+ang/2)), cy+ (r+30)*math.sin(math.radians(start+ang/2)), size=11, bold=True, fill=rgb(255,255,255))
            start += ang
        drawLabel("Water vapor 0-4% VARIABLE", 850, 430, size=12, fill=rgb(140,200,255), align='left')
        drawLabel("Press C to hide. Drag probe on left.", 850, 455, size=11, fill=rgb(160,170,190), align='left')
        drawLabel("Paper Q: Why does % stay same but", 850, 485, size=11, fill=rgb(200,210,230), align='left')
        drawLabel("pressure drop? (molecules per volume)", 850, 502, size=11, fill=rgb(200,210,230), align='left')

    # Header / instructions
    drawRect(0,0,1050,38, fill=rgb(10,12,20), opacity=90)
    drawLabel("APP 1: ATMOSPHERE TOWER - Composition & Structure", 15, 20, size=14, bold=True, fill=rgb(255,255,255), align='left')
    drawLabel("UP/DOWN or DRAG | SPACE pause for copying | C composition", 1035, 20, size=11, fill=rgb(170,180,200), align='right')

def main():
    runApp(1050,700)
main()