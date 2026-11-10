from scs import *

#MODEL - initialize state for 2 shapes stored in variables
def onAppStart(app):
    app.rectX = 1050/2
    app.rectY = 700/2
    app.rectW = 500
    app.rectH = 200
    app.rectFill = 'red'
    app.angle = 0
    
    app.circleX = 1050/2
    app.circleY = 700/2
    app.circleR = 100

#CONTROLLER - automatic updates
def onStep(app):
    app.angle += 1

#CONTROLLER - interactive updates
def onMousePress(app, mouseX, mouseY):
    app.circleX = mouseX
    app.circleY = mouseY
    app.rectFill = 'orange' if app.rectFill == 'red' else 'red'

#VIEW - only drawing, no state changes
def redrawAll(app):
    drawRect(app.rectX, app.rectY, app.rectW, app.rectH,
             fill=app.rectFill, align='center', rotateAngle=app.angle)
    drawCircle(app.circleX, app.circleY, app.circleR, fill='blue')

def main():
    runApp(1050,700)
main()