from scs import *
import math

def getTempAtAlt(km):
    if km <= 12: return 15 - 6.5*km
    elif km <= 50: return -56.5 + (km-12)*(57.5/38)
    elif km <= 85: return 1 - (km-50)*2.6
    else: return -90 + (km-85)*3.5

def getPressureAtAlt(km):
    return 1013.25 * math.exp(-km/7.64)

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 30
    app.probeAlt = 5.0
    # moved 25px right from 120 -> 145 to clear left clip
    app.towerX = 145
    app.towerW = 200
    app.layers = [
        (0, 12, "0-12km TROPOSPHERE", rgb(110,180,255)),
        (12, 50, "12-50km STRATOSPHERE", rgb(180,160,255)),
        (50, 85, "50-85km MESOSPHERE", rgb(140,140,190)),
        (85, 110, "85-110km THERMOSPHERE", rgb(60,60,80)),
    ]
    app.paused = False

def onMouseDrag(app, mx, my):
    if mx < 650:
        alt = (620 - my) / (620-60) * 110
        app.probeAlt = max(0, min(105, alt))

def onMousePress(app, mx, my): onMouseDrag(app,mx,my)
def onKeyPress(app, key):
    if key == 'space': app.paused = not app.paused
    if key == 'up': app.probeAlt = min(105, app.probeAlt+2)
    if key == 'down': app.probeAlt = max(0, app.probeAlt-2)

def onStep(app): pass

def redrawAll(app):
    drawRect(0,0,1050,700, fill=rgb(18,22,35))
    towerX, towerW = app.towerX, app.towerW
    drawRect(towerX, 50, towerW, 580, fill=rgb(30,35,55), border=rgb(80,90,120), borderWidth=2)
    
    for bottom, top, name, col in app.layers:
        yTop = 630 - (top/110)*580
        yBot = 630 - (bottom/110)*580
        drawRect(towerX, yTop, towerW, yBot-yTop, fill=col, opacity=65, border=None)
        # FIX: label INSIDE tower, left aligned, never off-screen
        drawLabel(name, towerX+8, (yTop+yBot)/2, size=11, fill=rgb(235,240,255), align='left', bold=True)

    # Temp profile - clamped left of right panels
    for km in range(0,111):
        t = getTempAtAlt(km)
        x = towerX + towerW + 10 + (t+90)/120*165
        y = 630 - (km/110)*580
        drawCircle(x, y, 2, fill=rgb(255,160,60), border=None)
    drawLabel("Temperature profile ->", towerX+towerW+75, 45, size=12, fill=rgb(255,160,60), bold=True)

    probeY = 630 - (app.probeAlt/110)*580
    drawLine(towerX-20, probeY, towerX+towerW+185, probeY, fill=rgb(255,255,100), lineWidth=1, dashes=(6,4))
    drawCircle(towerX+towerW//2, probeY, 11, fill=rgb(255,255,100), border=rgb(0,0,0), borderWidth=2)
    drawLabel(f"PROBE {app.probeAlt:.1f} km", towerX+towerW//2, probeY-18, size=14, bold=True, fill=rgb(255,255,150))

    p = getPressureAtAlt(app.probeAlt)
    t = getTempAtAlt(app.probeAlt)
    drawRect(550, 60, 470, 250, fill=rgb(26,30,45), border=rgb(70,80,110), borderWidth=2)
    drawLabel("SAMPLE TWO POINTS PER LAYER TO INFORM YOUR GRAPHS", 785, 82, size=14, bold=True, fill=rgb(255,230,100))
    drawLabel(f"Altitude: {app.probeAlt:.1f} km", 580, 118, size=22, bold=True, fill=rgb(255,255,255), align='left')
    drawLabel(f"Pressure: {p:.1f} hPa", 580, 153, size=22, bold=True, fill=rgb(140,200,255), align='left')
    drawLabel(f"Temp: {t:.1f} C", 580, 188, size=22, bold=True, fill=rgb(255,140,80), align='left')
    drawLabel(f"Density ~ {100*math.exp(-app.probeAlt/7.64):.1f}% of sea level", 580, 222, size=16, fill=rgb(180,190,210), align='left')
    drawLabel("Task: every 10km write Alt / Pressure / Temp", 580, 252, size=13, fill=rgb(170,180,200), align='left')
    drawLabel("Then plot Pressure vs Alt and Temp vs Alt", 580, 272, size=13, fill=rgb(170,180,200), align='left')

    drawRect(550, 330, 470, 350, fill=rgb(26,30,45), border=rgb(70,80,110), borderWidth=2)
    drawLabel("ATMOSPHERE COMPOSITION - Constant to ~80km", 785, 352, size=14, bold=True, fill=rgb(230,240,255))
    barX, barY, barW, barH = 580, 385, 410, 36
    drawRect(barX, barY, barW, barH, fill=rgb(40,45,65), border=rgb(90,100,130), borderWidth=1)
    o2W = int(barW*0.2095); arW = max(12, int(barW*0.0093)); co2W = max(8, int(barW*0.005)); n2W = barW - o2W - arW - co2W
    x=barX
    drawRect(x, barY, n2W, barH, fill=rgb(80,140,255), border=None); x+=n2W
    drawRect(x, barY, o2W, barH, fill=rgb(255,90,90), border=None); x+=o2W
    drawRect(x, barY, arW, barH, fill=rgb(120,255,120), border=None); x+=arW
    drawRect(x, barY, co2W, barH, fill=rgb(255,220,80), border=None)
    drawLabel(f"N2 78%", barX+8, barY+18, size=12, bold=True, fill=rgb(255,255,255), align='left')
    drawLabel(f"O2 21%", barX+n2W+6, barY+18, size=12, bold=True, fill=rgb(255,255,255), align='left')
    drawCircle(580, 445, 6, fill=rgb(80,140,255), border=None)
    drawLabel("Nitrogen N2 - 78.08% - inert filler", 595, 445, size=13, fill=rgb(220,230,255), align='left')
    drawCircle(580, 470, 6, fill=rgb(255,90,90), border=None)
    drawLabel("Oxygen O2 - 20.95% - for life", 595, 470, size=13, fill=rgb(220,230,255), align='left')
    drawCircle(580, 495, 6, fill=rgb(120,255,120), border=None)
    drawLabel("Argon Ar - 0.93% - inert", 595, 495, size=13, fill=rgb(220,230,255), align='left')
    drawCircle(580, 520, 6, fill=rgb(255,220,80), border=None)
    drawLabel("CO2 - 0.04% - greenhouse, variable", 595, 520, size=13, fill=rgb(255,230,100), align='left')
    drawLabel("Water vapor 0-4% HIGHLY VARIABLE", 580, 550, size=14, bold=True, fill=rgb(140,200,255), align='left')
    drawLabel("Paper Q: % constant but pressure drops?", 580, 575, size=13, fill=rgb(200,210,230), align='left')
    drawLabel("A: Fewer molecules per volume aloft", 580, 595, size=13, fill=rgb(200,210,230), align='left')

    drawRect(0,0,1050,40, fill=rgb(10,12,20), opacity=92)
    drawLabel("ATMOSPHERE TOWER:  Composition & Structure", 15, 20, size=16, bold=True, fill=rgb(255,255,255), align='left')

def main(): runApp(1050,700)
main()