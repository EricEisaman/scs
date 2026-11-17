# Presentation demo -- fullscreen is a mode, not a resize.
#
# Run: ?app=presentation_demo
# Click the canvas to enter fullscreen (user gesture REQUIRED --
# the request is made directly from the click, never deferred behind
# asset loading). Press Esc or the DOM exit button to leave; the
# controller derives state from document.fullscreenElement, so a
# browser/user exit outside the API still restores embedded mode.
#
# The overlay slot holds DOM controls (semantic <button>, not
# canvas-redrawn controls). The canvas itself only draws the scene.

def onAppStart(app):
    app.background = 'black'
    # Sizing: fullscreen never means "max DPR". Cap the ratio and
    # the pixel budget so a DPR-3 phone does not pay 9x pixels.
    setPixelBudget(budget=4000000, pixel_ratio_cap=2.0)
    setRenderScale(1.0)
    Label('Presentation demo -- click to enter fullscreen',
          20, 20, size=16, fill='white', align='left-top')
    Label('Overlay controls are DOM, not canvas-drawn.',
          20, 50, size=14, fill='lightgray', align='left-top')
    Label('Esc / exit button restores embedded mode.',
          20, 75, size=14, fill='lightgray', align='left-top')
    Star(200, 200, 80, 5, fill='gold')
    Circle(320, 200, 40, fill='dodgerblue')
    # Metrics are published for effects + input code:
    # getDisplayMetrics() -> display (CSS) + drawing_buffer (backing)


def onMousePress(app, x, y):
    # Directly from the gesture: enterFullscreen() returns a Promise.
    # A rejection preserves embedded mode and reports -- it does not
    # leave an optimistic "fullscreen" flag behind.
    try:
        enterFullscreen()
    except Exception:
        pass


def onKeyPress(app, key):
    if key == 'Escape':
        exitFullscreen()
