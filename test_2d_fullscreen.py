# Minimal 2D app to test fullscreen mouse mapping
from scs import *

def onAppStart(app):
    app.click_positions = []

def onMousePress(app, x, y):
    # Record where the user clicked
    app.click_positions.append((x, y))
    if len(app.click_positions) > 100:
        app.click_positions.pop(0)
    print(f"Click at ({x:.1f}, {y:.1f})")

def redrawAll(app, canvas):
    # Draw background
    canvas.create_rectangle(0, 0, app.width, app.height, fill='black')
    
    # Draw grid for reference
    for x in range(0, app.width, 50):
        canvas.create_line(x, 0, x, app.height, fill='#333333')
    for y in range(0, app.height, 50):
        canvas.create_line(0, y, app.width, y, fill='#333333')
    
    # Draw numbers at grid intersections
    for x in range(0, app.width, 100):
        for y in range(0, app.height, 100):
            canvas.create_text(x+5, y+5, text=f'{x},{y}', fill='#666666', font='Arial 8')
    
    # Draw buttons
    canvas.create_rectangle(10, 10, 110, 60, fill='#0088ff')
    canvas.create_text(60, 35, text='Button 1', fill='white', font='Arial 14 bold')
    
    canvas.create_rectangle(app.width-110, app.height-60, app.width-10, app.height-10, fill='#ff8800')
    canvas.create_text(app.width-60, app.height-35, text='Button 2', fill='white', font='Arial 14 bold')
    
    # Draw crosshairs at recent click positions
    for i, (x, y) in enumerate(app.click_positions):
        # Fade out older clicks
        alpha = int(255 * (i / max(1, len(app.click_positions))))
        color = f'#{alpha:02x}{alpha:02x}{alpha:02x}'
        canvas.create_line(x-20, y, x+20, y, fill=color)
        canvas.create_line(x, y-20, x, y+20, fill=color)
        canvas.create_text(x+5, y-25, text=f'({x:.0f},{y:.0f})', fill=color, font='Arial 8')

# Run as 2D app with fullscreen button enabled
runApp(400, 400, enableFullscreen=True)
