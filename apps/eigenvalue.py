from scs import *
import math


WIDTH = 1050
HEIGHT = 700
PLANE_LEFT = 45
PLANE_TOP = 140
PLANE_WIDTH = 610
PLANE_HEIGHT = 520
ORIGIN_X = 350
ORIGIN_Y = 398
SCALE = 65
BUTTONS = [
    (54, 78, 140, 36),
    (204, 78, 140, 36),
    (354, 78, 140, 36),
    (504, 78, 140, 36)
]

BG = rgb(15, 20, 23)
PLANE = rgb(18, 25, 28)
INK = rgb(229, 238, 232)
MUTED = rgb(137, 157, 151)
GRID = rgb(54, 69, 66)
MINT = rgb(102, 224, 177)
CYAN = rgb(95, 194, 226)
AMBER = rgb(244, 190, 92)
RED = rgb(244, 111, 104)

PRESETS = [
    {
        'name': 'STRETCH',
        'matrix': ((2.0, 0.0), (0.0, 0.5)),
        'eigenlines': [
            (1.0, 0.0, 2.0, 'x-axis  lambda=2'),
            (0.0, 1.0, 0.5, 'y-axis  lambda=0.5')
        ],
        'description': 'Horizontal stretch, vertical compression.'
    },
    {
        'name': 'SHEAR',
        'matrix': ((1.0, 1.0), (0.0, 1.0)),
        'eigenlines': [(1.0, 0.0, 1.0, 'x-axis  lambda=1')],
        'description': 'Horizontal shear; only the x-axis stays fixed.'
    },
    {
        'name': 'ROTATE 90',
        'matrix': ((0.0, -1.0), (1.0, 0.0)),
        'eigenlines': [],
        'description': 'A quarter-turn has no real eigenvector directions.'
    },
    {
        'name': 'REFLECT',
        'matrix': ((-1.0, 0.0), (0.0, 1.0)),
        'eigenlines': [
            (1.0, 0.0, -1.0, 'x-axis  lambda=-1'),
            (0.0, 1.0, 1.0, 'y-axis  lambda=1')
        ],
        'description': 'The x-axis reverses; the y-axis stays fixed.'
    }
]


def _transform(matrix, x, y):
    return (
        matrix[0][0] * x + matrix[0][1] * y,
        matrix[1][0] * x + matrix[1][1] * y
    )


def _to_screen(x, y):
    return ORIGIN_X + SCALE * x, ORIGIN_Y - SCALE * y


def _from_screen(x, y):
    world_x = (x - ORIGIN_X) / SCALE
    world_y = (ORIGIN_Y - y) / SCALE
    return max(-2.2, min(2.2, world_x)), max(-2.2, min(2.2, world_y))


def _vector_image(app):
    matrix = PRESETS[app.preset]['matrix']
    return _transform(matrix, app.vectorX, app.vectorY)


def _vector_is_eigen(app):
    image_x, image_y = _vector_image(app)
    vector_length_sq = app.vectorX ** 2 + app.vectorY ** 2
    image_length_sq = image_x ** 2 + image_y ** 2
    if vector_length_sq < 1e-8 or image_length_sq < 1e-8:
        return False, 0.0
    cross = app.vectorX * image_y - app.vectorY * image_x
    tolerance = 0.025 * math.sqrt(vector_length_sq * image_length_sq)
    eigenvalue = (app.vectorX * image_x + app.vectorY * image_y) / vector_length_sq
    return abs(cross) <= tolerance, eigenvalue


def _draw_button(index, selected):
    x, y, width, height = BUTTONS[index]
    fill = rgb(42, 59, 55) if selected else rgb(25, 33, 37)
    border = MINT if selected else rgb(59, 75, 70)
    drawRect(x, y, width, height, fill=fill, border=border, borderWidth=1)
    drawLabel(PRESETS[index]['name'], x + width / 2, y + height / 2,
              size=12, fill=MINT if selected else INK, bold=selected)


def _draw_plane(app):
    preset = PRESETS[app.preset]
    matrix = preset['matrix']
    drawRect(PLANE_LEFT, PLANE_TOP, PLANE_WIDTH, PLANE_HEIGHT,
             fill=PLANE, border=rgb(54, 69, 66), borderWidth=1)

    for value in range(-3, 4):
        drawLine(*_to_screen(value, -4), *_to_screen(value, 4),
                 fill=GRID, lineWidth=1, opacity=55)
        drawLine(*_to_screen(-5, value), *_to_screen(5, value),
                 fill=GRID, lineWidth=1, opacity=55)

        start = _transform(matrix, value, -4)
        end = _transform(matrix, value, 4)
        drawLine(*_to_screen(*start), *_to_screen(*end),
                 fill=CYAN, lineWidth=1, opacity=36)
        start = _transform(matrix, -5, value)
        end = _transform(matrix, 5, value)
        drawLine(*_to_screen(*start), *_to_screen(*end),
                 fill=CYAN, lineWidth=1, opacity=36)

    drawLine(PLANE_LEFT, ORIGIN_Y, PLANE_LEFT + PLANE_WIDTH, ORIGIN_Y,
             fill=rgb(117, 138, 132), lineWidth=1.5)
    drawLine(ORIGIN_X, PLANE_TOP, ORIGIN_X, PLANE_TOP + PLANE_HEIGHT,
             fill=rgb(117, 138, 132), lineWidth=1.5)
    for value in range(-3, 4):
        if value == 0:
            continue
        x, y = _to_screen(value, 0)
        drawLabel(str(value), x, ORIGIN_Y + 13, size=9, fill=MUTED)
        x, y = _to_screen(0, value)
        drawLabel(str(value), ORIGIN_X - 12, y, size=9, fill=MUTED, align='right')

    for direction_x, direction_y, eigenvalue, label in preset['eigenlines']:
        start = _to_screen(-4.8 * direction_x, -4.8 * direction_y)
        end = _to_screen(4.8 * direction_x, 4.8 * direction_y)
        drawLine(*start, *end, fill=MINT, lineWidth=2, dashes=True, opacity=85)
        label_x, label_y = _to_screen(3.65 * direction_x, 3.65 * direction_y)
        if direction_y:
            label_x += 30
        else:
            label_y -= 16
        drawLabel(label, label_x, label_y, size=10, fill=MINT, bold=True)

    image_x, image_y = _vector_image(app)
    vector_tip = _to_screen(app.vectorX, app.vectorY)
    image_tip = _to_screen(image_x, image_y)
    drawLine(ORIGIN_X, ORIGIN_Y, vector_tip[0], vector_tip[1],
             fill=CYAN, lineWidth=4, arrowEnd=True)
    drawLine(ORIGIN_X, ORIGIN_Y, image_tip[0], image_tip[1],
             fill=AMBER, lineWidth=4, arrowEnd=True)
    drawCircle(vector_tip[0], vector_tip[1], 6, fill=CYAN)
    drawCircle(image_tip[0], image_tip[1], 6, fill=AMBER)
    drawLabel('v', vector_tip[0] + 13, vector_tip[1] - 11,
              size=15, fill=CYAN, bold=True)
    drawLabel('Av', image_tip[0] + 14, image_tip[1] + 12,
              size=15, fill=AMBER, bold=True)
    drawCircle(ORIGIN_X, ORIGIN_Y, 3, fill=INK)


def _draw_sidebar(app):
    preset = PRESETS[app.preset]
    matrix = preset['matrix']
    image_x, image_y = _vector_image(app)
    is_eigen, eigenvalue = _vector_is_eigen(app)
    vector_length = math.sqrt(app.vectorX ** 2 + app.vectorY ** 2)
    image_length = math.sqrt(image_x ** 2 + image_y ** 2)
    scale_factor = image_length / vector_length if vector_length else 0

    drawLabel('TRANSFORMATION', 700, 155, size=11, fill=MUTED, align='left')
    drawLabel('A = [[{:.2g}, {:.2g}],'.format(matrix[0][0], matrix[0][1]),
              700, 184, size=14, fill=INK, align='left')
    drawLabel('     [{:.2g}, {:.2g}]]'.format(matrix[1][0], matrix[1][1]),
              700, 207, size=14, fill=INK, align='left')
    drawLabel(preset['description'], 700, 246, size=11, fill=MUTED, align='left')

    drawLine(700, 275, 1007, 275, fill=rgb(55, 69, 64), lineWidth=1)
    drawLabel('VECTOR COMPARISON', 700, 300, size=11, fill=MUTED, align='left')
    drawLabel('v  = ({:.2f}, {:.2f})'.format(app.vectorX, app.vectorY),
              700, 331, size=14, fill=CYAN, align='left')
    drawLabel('Av = ({:.2f}, {:.2f})'.format(image_x, image_y),
              700, 359, size=14, fill=AMBER, align='left')
    drawLabel('Length scale = {:.2f}'.format(scale_factor),
              700, 389, size=12, fill=INK, align='left')

    drawLine(700, 421, 1007, 421, fill=rgb(55, 69, 64), lineWidth=1)
    if PRESETS[app.preset]['eigenlines']:
        if is_eigen:
            message = 'EIGENVECTOR: span unchanged'
            detail = 'Av = lambda v,  lambda = {:.3g}'.format(eigenvalue)
            color = MINT
            direction = 'Direction reverses' if eigenvalue < 0 else 'Direction is preserved'
        else:
            message = 'Not an eigenvector'
            detail = 'v and Av lie on different lines'
            color = AMBER
            direction = 'Try dragging v onto a dashed line'
    else:
        message = 'No real eigenvector lines'
        detail = 'Every nonzero direction turns 90 degrees'
        color = RED
        direction = 'The zero vector is excluded'
    drawLabel(message, 700, 451, size=14, fill=color, bold=True, align='left')
    drawLabel(detail, 700, 478, size=11, fill=INK, align='left')
    drawLabel(direction, 700, 502, size=11, fill=MUTED, align='left')

    drawRect(690, 545, 324, 92, fill=rgb(25, 33, 37), border=rgb(55, 69, 64), borderWidth=1)
    drawLabel('KEY IDEA', 706, 565, size=10, fill=MINT, bold=True, align='left')
    drawLabel('An eigenvector keeps its span (line).', 706, 590,
              size=11, fill=INK, align='left')
    drawLabel('The eigenvalue tells how that line scales.', 706, 613,
              size=11, fill=INK, align='left')


def onAppStart(app):
    app.width = WIDTH
    app.height = HEIGHT
    app.stepsPerSecond = 30
    app.preset = 0
    app.vectorX = 1.35
    app.vectorY = 0.8
    app.draggingVector = False


def onMousePress(app, mouseX, mouseY):
    app.draggingVector = False
    for index, (x, y, width, height) in enumerate(BUTTONS):
        if x <= mouseX <= x + width and y <= mouseY <= y + height:
            app.preset = index
            return

    if (PLANE_LEFT <= mouseX <= PLANE_LEFT + PLANE_WIDTH
            and PLANE_TOP <= mouseY <= PLANE_TOP + PLANE_HEIGHT):
        tip_x, tip_y = _to_screen(app.vectorX, app.vectorY)
        if math.hypot(mouseX - tip_x, mouseY - tip_y) <= 20:
            app.draggingVector = True
        else:
            app.vectorX, app.vectorY = _from_screen(mouseX, mouseY)
            app.draggingVector = True


def onMouseDrag(app, mouseX, mouseY):
    if app.draggingVector:
        app.vectorX, app.vectorY = _from_screen(mouseX, mouseY)


def onMouseRelease(app, mouseX, mouseY):
    app.draggingVector = False


def onKeyPress(app, key):
    if key in ('1', '2', '3', '4'):
        app.preset = int(key) - 1


def redrawAll(app):
    drawRect(0, 0, app.width, app.height, fill=BG)
    drawLabel('EIGENVECTORS / GEOMETRIC TRANSFORMATIONS', 54, 35,
              size=21, fill=INK, bold=True, align='left')
    drawLabel('Compare a vector v with its image Av under the same plane map.',
              54, 57, size=12, fill=MUTED, align='left')
    for index in range(len(PRESETS)):
        _draw_button(index, index == app.preset)

    drawLabel('ORIGINAL GRID', 60, 126, size=9, fill=MUTED, align='left')
    drawLabel('TRANSFORMED GRID', 190, 126, size=9, fill=CYAN, align='left')
    drawLabel('Click the plane to place v, or drag its tip.', 423, 126,
              size=10, fill=MUTED, align='right')
    _draw_plane(app)
    _draw_sidebar(app)
