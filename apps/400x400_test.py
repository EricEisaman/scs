from scs import *

#MODEL - initialize state for 2 shapes stored in variables
def onAppStart(app):
    app.rectX = 400/2
    app.rectY = 400/2
    app.rectW = 300
    app.rectH = 100
    app.rectFill = 'red'
    app.angle = 0
    
    app.circleX = 400/2
    app.circleY = 400/2
    app.circleR = 10

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
    runApp(400,400)
main()
