from scs import *
from math import sin, cos, atan2, sqrt, pi


# ==============================================================
# THE EXACT METHOD OF AEROFOIL DESIGN
# JOUKOWSKI CONFORMAL-MAPPING WIND TUNNEL
#
# CMU CS Academy CPCS Mode
# Canvas: 1050 x 700
#
# VISUAL CONVENTION
# --------------------------------------------------------------
# The wind remains horizontal, moving left to right.
# The aerofoil and mapped flow geometry visibly rotate.
# The rotation angle is the displayed angle of attack alpha.
#
# CONTROLS
# --------------------------------------------------------------
# Drag gold handle : Move generating circle / change camber
# W / S            : Increase / decrease circulation
# A / D            : Rotate aerofoil down / up
# Q / E            : Make generating circle smaller / larger
# 1                : Symmetric preset
# 2                : Cambered preset
# 3                : High-lift preset
# SPACE            : Pause / resume tracer particles
# R                : Reset
# H                : Help
# ==============================================================


# --------------------------------------------------------------
# Utility functions
# --------------------------------------------------------------

def clamp(value, low, high):
    if value < low:
        return low
    elif value > high:
        return high
    return value


def distanceBetween(x1, y1, x2, y2):
    return sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def sourceToScreen(app, x, y):
    return (
        app.sourceCenterX + x * app.sourceScale,
        app.sourceCenterY - y * app.sourceScale
    )


def mappedToScreen(app, x, y):
    return (
        app.mappedCenterX + x * app.mappedScale,
        app.mappedCenterY - y * app.mappedScale
    )


def screenToSource(app, screenX, screenY):
    return (
        (screenX - app.sourceCenterX) / app.sourceScale,
        (app.sourceCenterY - screenY) / app.sourceScale
    )


def rotatePoint(x, y, pivotX, pivotY, angleRadians):
    dx = x - pivotX
    dy = y - pivotY

    rotatedX = pivotX + dx * cos(angleRadians) - dy * sin(angleRadians)
    rotatedY = pivotY + dx * sin(angleRadians) + dy * cos(angleRadians)

    return (rotatedX, rotatedY)


def joukowskiMap(x, y):
    # w = z + 1/z
    denominator = x * x + y * y

    if denominator < 0.0001:
        denominator = 0.0001

    return (
        x + x / denominator,
        y - y / denominator
    )


# --------------------------------------------------------------
# Fast cached source and mapped geometry
# --------------------------------------------------------------

def getBaseStreamlinePoint(app, level, theta):
    radius = app.circleRadius

    radialOffset = 0.22 + abs(level) * 0.46
    noseBend = 0.46 * (1 - cos(theta))
    sideBend = 0.16 * sin(theta) * sin(theta)

    radialDistance = radius + radialOffset + noseBend + sideBend

    x = app.circleX + radialDistance * cos(theta)
    y = app.circleY + radialDistance * sin(theta)

    # A qualitative circulation asymmetry.
    circulationShift = app.circulation * 0.13 * sin(theta)

    if level > 0:
        y += circulationShift
    else:
        y += circulationShift * 0.72

    return (x, y)


def buildOneStreamline(app, level):
    points = []

    if level > 0:
        startTheta = pi + 0.98
        endTheta = -0.98
    else:
        startTheta = pi - 0.98
        endTheta = 0.98

    startX = -3.45
    startY = level * 0.69 + app.circleY * 0.10
    points.append((startX, startY))

    steps = 50

    for step in range(steps + 1):
        fraction = step / steps
        theta = startTheta + (endTheta - startTheta) * fraction

        x, y = getBaseStreamlinePoint(app, level, theta)
        points.append((x, y))

    endX = 3.45
    endY = level * 0.69 + app.circleY * 0.10
    endY += app.circulation * 0.10
    points.append((endX, endY))

    return points


def rebuildCachedGeometry(app):
    # This runs only after an input change, never every onStep.

    app.sourceStreamlines = []
    app.mappedStreamlines = []

    levels = [
        -2.15, -1.72, -1.36, -1.04, -0.78, -0.54, -0.33,
         0.33,  0.54,  0.78,  1.04,  1.36,  1.72,  2.15
    ]

    for level in levels:
        sourceLine = buildOneStreamline(app, level)
        mappedLine = []

        for x, y in sourceLine:
            mappedX, mappedY = joukowskiMap(x, y)
            mappedLine.append((mappedX, mappedY))

        app.sourceStreamlines.append(sourceLine)
        app.mappedStreamlines.append(mappedLine)

    app.mappedAirfoilPoints = []

    pointCount = 180

    for index in range(pointCount + 1):
        theta = 2 * pi * index / pointCount

        sourceX = app.circleX + app.circleRadius * cos(theta)
        sourceY = app.circleY + app.circleRadius * sin(theta)

        mappedX, mappedY = joukowskiMap(sourceX, sourceY)
        app.mappedAirfoilPoints.append((mappedX, mappedY))

    # Cache leading and trailing edge coordinates in mapped world space.
    app.leadingEdge = app.mappedAirfoilPoints[0]
    app.trailingEdge = app.mappedAirfoilPoints[0]

    for point in app.mappedAirfoilPoints:
        if point[0] < app.leadingEdge[0]:
            app.leadingEdge = point

        if point[0] > app.trailingEdge[0]:
            app.trailingEdge = point

    # Rotation pivot: a point partway from leading to trailing edge.
    # Approximately a quarter-chord pivot works well visually.
    app.aerofoilPivotX = (
        app.leadingEdge[0] +
        0.28 * (app.trailingEdge[0] - app.leadingEdge[0])
    )

    app.aerofoilPivotY = (
        app.leadingEdge[1] +
        0.28 * (app.trailingEdge[1] - app.leadingEdge[1])
    )


# --------------------------------------------------------------
# Aerofoil display rotation
# --------------------------------------------------------------

def getRotatedMappedPoint(app, x, y):
    # In math coordinates, positive alpha should make the nose rise.
    # Screen y is inverted later by mappedToScreen, so use -alpha.
    angleRadians = -app.angleOfAttack * pi / 180

    return rotatePoint(
        x,
        y,
        app.aerofoilPivotX,
        app.aerofoilPivotY,
        angleRadians
    )


def getRotatedMappedScreenPoint(app, x, y):
    rotatedX, rotatedY = getRotatedMappedPoint(app, x, y)
    return mappedToScreen(app, rotatedX, rotatedY)


# --------------------------------------------------------------
# Statistics
# --------------------------------------------------------------

def getDesignStats(app):
    camber = app.circleY * 32
    thickness = max(1.5, (app.circleRadius - 0.87) * 58)

    liftIndex = (
        app.circulation * 0.62 +
        app.angleOfAttack * 0.065 +
        camber * 0.085
    )

    if liftIndex >= 1.85:
        rating = 'ELITE LIFT'
        ratingColor = 'springGreen'
    elif liftIndex >= 1.25:
        rating = 'MISSION READY'
        ratingColor = 'gold'
    elif liftIndex >= 0.45:
        rating = 'LIFTING'
        ratingColor = 'lightGreen'
    elif liftIndex >= -0.20:
        rating = 'NEAR NEUTRAL'
        ratingColor = 'lightSteelBlue'
    else:
        rating = 'DOWNFORCE'
        ratingColor = 'tomato'

    return (camber, thickness, liftIndex, rating, ratingColor)


def getKuttaStatus(app):
    targetX = 1.0 - app.circleRadius
    targetY = 0

    error = distanceBetween(
        app.circleX,
        app.circleY,
        targetX,
        targetY
    )

    if error < 0.12:
        return ('TRAILING EDGE ALIGNED', 'springGreen')
    elif error < 0.30:
        return ('NEAR EDGE SETUP', 'gold')
    else:
        return ('EXPERIMENTAL PROFILE', 'tomato')


# --------------------------------------------------------------
# Setup
# --------------------------------------------------------------

def resetApp(app):
    app.circleX = -0.10
    app.circleY = 0.13
    app.circleRadius = 1.10

    app.circulation = 0.55
    app.angleOfAttack = 0

    app.running = True
    app.showHelp = True
    app.draggingHandle = False

    app.particleOffset = 0

    app.message = 'Mission: rotate the aerofoil and study its mapped flow.'
    app.messageTimer = 180

    rebuildCachedGeometry(app)


def onAppStart(app):
    print("[DEBUG onAppStart] >>> ENTER")
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 30

    app.sourceCenterX = 265
    app.sourceCenterY = 365
    app.sourceScale = 97

    app.mappedCenterX = 786
    app.mappedCenterY = 365
    app.mappedScale = 130

    resetApp(app)


# --------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------

def drawPanel(x, y, width, height, fillColor, borderColor):
    drawRect(
        x, y, width, height,
        fill=fillColor,
        border=borderColor,
        borderWidth=2
    )


def drawArrow(x1, y1, x2, y2, color, opacity, lineWidth=2):
    drawLine(
        x1, y1, x2, y2,
        fill=color,
        lineWidth=lineWidth,
        opacity=opacity
    )

    angle = atan2(y2 - y1, x2 - x1)
    arrowSize = 7

    drawLine(
        x2, y2,
        x2 - arrowSize * cos(angle - 0.55),
        y2 - arrowSize * sin(angle - 0.55),
        fill=color,
        lineWidth=lineWidth,
        opacity=opacity
    )

    drawLine(
        x2, y2,
        x2 - arrowSize * cos(angle + 0.55),
        y2 - arrowSize * sin(angle + 0.55),
        fill=color,
        lineWidth=lineWidth,
        opacity=opacity
    )


def drawGrid(centerX, centerY, scale, width, height, color):
    for value in range(-3, 4):
        x = centerX + value * scale
        y = centerY - value * scale

        drawLine(
            x, centerY - height / 2,
            x, centerY + height / 2,
            fill=color,
            opacity=14
        )

        drawLine(
            centerX - width / 2, y,
            centerX + width / 2, y,
            fill=color,
            opacity=14
        )

    drawLine(
        centerX - width / 2, centerY,
        centerX + width / 2, centerY,
        fill='white',
        opacity=27
    )

    drawLine(
        centerX, centerY - height / 2,
        centerX, centerY + height / 2,
        fill='white',
        opacity=27
    )


def drawGlow(x, y, radius, color):
    drawCircle(x, y, radius + 12, fill=color, opacity=6)
    drawCircle(x, y, radius + 7, fill=color, opacity=10)
    drawCircle(x, y, radius + 3, fill=color, opacity=16)


def drawButton(x, y, width, height, text, fillColor):
    drawRect(
        x, y, width, height,
        fill=fillColor,
        border='white',
        borderWidth=1,
        opacity=95
    )

    drawLabel(
        text,
        x + width / 2,
        y + height / 2,
        fill='white',
        bold=True,
        size=10
    )


def drawProgressBar(x, y, width, height, ratio, fillColor):
    drawRect(
        x, y, width, height,
        fill='black',
        border='lightSteelBlue',
        borderWidth=1
    )

    fillWidth = clamp(ratio, 0, 1) * width

    if fillWidth > 0.5:
        drawRect(
            x, y, fillWidth, height,
            fill=fillColor
        )


# --------------------------------------------------------------
# Header and controls
# --------------------------------------------------------------

def drawHeader(app):
    drawRect(0, 0, app.width, app.height, fill='black')

    drawRect(0, 0, app.width, 87, fill='midnightBlue')
    drawRect(0, 87, app.width, 5, fill='slateBlue')
    drawRect(0, 92, app.width, 3, fill='gold', opacity=75)

    drawLabel(
        'THE EXACT METHOD OF AEROFOIL DESIGN',
        525, 26,
        fill='white',
        bold=True,
        size=23
    )

    drawLabel(
        'Joukowski Conformal-Mapping Wind Tunnel',
        525, 50,
        fill='lightSteelBlue',
        size=14
    )

    drawLabel(
        'Hold the wind fixed. Rotate the aerofoil. Transform the flow.',
        525, 71,
        fill='gold',
        bold=True,
        size=12
    )

    drawLabel(
        'w = z + 1/z',
        937, 47,
        fill='aqua',
        bold=True,
        size=15
    )


def drawControls(app):
    drawButton(24, 99, 55, 24, 'W +Γ', 'darkGreen')
    drawButton(84, 99, 55, 24, 'S -Γ', 'darkRed')

    drawButton(147, 99, 55, 24, 'A -α', 'darkSlateBlue')
    drawButton(207, 99, 55, 24, 'D +α', 'darkSlateBlue')

    drawButton(270, 99, 58, 24, 'Q thin', 'darkSlateGray')
    drawButton(333, 99, 62, 24, 'E thick', 'darkSlateGray')

    if app.running:
        flowText = 'PAUSE'
        flowColor = 'darkOrange'
    else:
        flowText = 'PLAY'
        flowColor = 'darkGreen'

    drawButton(404, 99, 68, 24, flowText, flowColor)

    drawButton(644, 99, 67, 24, '1 SYMM', 'darkSlateBlue')
    drawButton(717, 99, 70, 24, '2 CAMBER', 'darkSlateBlue')
    drawButton(793, 99, 65, 24, '3 LIFT', 'darkGreen')

    drawButton(880, 99, 62, 24, 'RESET', 'darkRed')
    drawButton(948, 99, 74, 24, 'HELP H', 'darkSlateBlue')


# --------------------------------------------------------------
# Source plane
# --------------------------------------------------------------

def drawSourceWindVectors():
    # Wind stays horizontal in both panes in this visual convention.
    for y in range(230, 514, 48):
        drawArrow(44, y, 85, y, 'aqua', 65)


def drawSourcePlane(app):
    drawPanel(22, 132, 470, 458, 'midnightBlue', 'slateBlue')

    drawLabel(
        '1. SOURCE PLANE: SOLVE THE CIRCLE',
        257, 158,
        fill='white',
        bold=True,
        size=15
    )

    drawLabel(
        'Circle flow is the mathematical starting point',
        257, 178,
        fill='lightSteelBlue',
        size=11
    )

    drawGrid(
        app.sourceCenterX,
        app.sourceCenterY,
        app.sourceScale,
        430,
        348,
        'lightCyan'
    )

    drawSourceWindVectors()

    for streamline in app.sourceStreamlines:
        previous = None

        for x, y in streamline:
            screenX, screenY = sourceToScreen(app, x, y)

            if previous != None:
                drawLine(
                    previous[0], previous[1],
                    screenX, screenY,
                    fill='aqua',
                    lineWidth=1.5,
                    opacity=67
                )

            previous = (screenX, screenY)

    circleX, circleY = sourceToScreen(
        app,
        app.circleX,
        app.circleY
    )

    circleRadius = app.circleRadius * app.sourceScale

    drawGlow(circleX, circleY, circleRadius, 'dodgerBlue')

    drawCircle(
        circleX, circleY, circleRadius,
        fill='dodgerBlue',
        opacity=63,
        border='white',
        borderWidth=2
    )

    drawGlow(circleX, circleY, 10, 'gold')

    drawCircle(
        circleX, circleY, 10,
        fill='gold',
        border='white',
        borderWidth=1
    )

    drawLine(
        circleX - 13, circleY,
        circleX + 13, circleY,
        fill='white',
        opacity=70
    )

    drawLine(
        circleX, circleY - 13,
        circleX, circleY + 13,
        fill='white',
        opacity=70
    )

    drawLabel(
        'DRAG',
        circleX,
        circleY - 22,
        fill='gold',
        bold=True,
        size=10
    )

    drawLabel(
        'z-plane',
        65, 564,
        fill='lightCyan',
        bold=True,
        size=12
    )

    drawLabel(
        'fixed generating geometry',
        257, 564,
        fill='lightCyan',
        size=11
    )


# --------------------------------------------------------------
# Mapped aerofoil plane
# --------------------------------------------------------------

def getFlowColor(index, total):
    middle = total / 2
    relativeDistance = abs(index - middle) / middle

    if relativeDistance < 0.22:
        return 'tomato'
    elif relativeDistance < 0.48:
        return 'gold'
    return 'springGreen'


def drawMappedStreamlines(app):
    lineCount = len(app.mappedStreamlines)

    for index in range(lineCount):
        streamline = app.mappedStreamlines[index]
        color = getFlowColor(index, lineCount)
        previous = None

        for x, y in streamline:
            screenX, screenY = getRotatedMappedScreenPoint(app, x, y)

            if previous != None:
                currentInside = (
                    514 <= screenX <= 1012 and
                    197 <= screenY <= 545
                )

                previousInside = (
                    514 <= previous[0] <= 1012 and
                    197 <= previous[1] <= 545
                )

                if currentInside and previousInside:
                    drawLine(
                        previous[0], previous[1],
                        screenX, screenY,
                        fill=color,
                        lineWidth=1.5,
                        opacity=68
                    )

            previous = (screenX, screenY)


def drawMappedAirfoil(app):
    screenPoints = []

    for x, y in app.mappedAirfoilPoints:
        screenX, screenY = getRotatedMappedScreenPoint(app, x, y)
        screenPoints.append((screenX, screenY))

    # Golden atmospheric glow.
    for index in range(len(screenPoints) - 1):
        x1, y1 = screenPoints[index]
        x2, y2 = screenPoints[index + 1]

        drawLine(
            x1, y1, x2, y2,
            fill='gold',
            lineWidth=8,
            opacity=13
        )

    # White aerofoil boundary.
    for index in range(len(screenPoints) - 1):
        x1, y1 = screenPoints[index]
        x2, y2 = screenPoints[index + 1]

        drawLine(
            x1, y1, x2, y2,
            fill='white',
            lineWidth=2
        )

    leadingX, leadingY = getRotatedMappedScreenPoint(
        app,
        app.leadingEdge[0],
        app.leadingEdge[1]
    )

    trailingX, trailingY = getRotatedMappedScreenPoint(
        app,
        app.trailingEdge[0],
        app.trailingEdge[1]
    )

    pivotX, pivotY = getRotatedMappedScreenPoint(
        app,
        app.aerofoilPivotX,
        app.aerofoilPivotY
    )

    drawGlow(pivotX, pivotY, 4, 'gold')

    drawCircle(
        pivotX, pivotY, 4,
        fill='gold',
        border='white',
        borderWidth=1
    )

    drawLabel(
        'PIVOT',
        pivotX,
        pivotY + 16,
        fill='gold',
        bold=True,
        size=8
    )

    drawCircle(leadingX, leadingY, 4, fill='orange')
    drawCircle(trailingX, trailingY, 4, fill='tomato')

    drawLabel(
        'LE',
        leadingX + 16,
        leadingY + 15,
        fill='orange',
        bold=True,
        size=10
    )

    drawLabel(
        'TE',
        trailingX - 16,
        trailingY - 17,
        fill='tomato',
        bold=True,
        size=10
    )


def drawFlowParticles(app):
    if not app.running:
        return

    particleLines = [1, 3, 5, 8, 10, 12]

    for lineIndex in particleLines:
        if lineIndex < len(app.mappedStreamlines):
            streamline = app.mappedStreamlines[lineIndex]

            if len(streamline) > 4:
                pointIndex = int(
                    (app.particleOffset + lineIndex * 11)
                    % len(streamline)
                )

                x, y = streamline[pointIndex]

                screenX, screenY = getRotatedMappedScreenPoint(
                    app,
                    x,
                    y
                )

                if (
                    514 <= screenX <= 1012 and
                    197 <= screenY <= 545
                ):
                    drawCircle(
                        screenX, screenY, 7,
                        fill='springGreen',
                        opacity=13
                    )

                    drawCircle(
                        screenX, screenY, 3,
                        fill='white',
                        border='springGreen',
                        borderWidth=1
                    )


def drawMappedWindVectors():
    # The wind is fixed and horizontal.
    for y in range(230, 514, 49):
        drawArrow(963, y, 1001, y, 'springGreen', 62)


def drawAngleIndicator(app):
    pivotX, pivotY = getRotatedMappedScreenPoint(
        app,
        app.aerofoilPivotX,
        app.aerofoilPivotY
    )

    # The dashed baseline represents alpha = 0.
    drawLine(
        pivotX - 48, pivotY,
        pivotX + 48, pivotY,
        fill='lightSteelBlue',
        lineWidth=1,
        opacity=60,
        dashes=True
    )

    # Direction of rotated aerofoil chord.
    angle = -app.angleOfAttack * pi / 180

    tipX = pivotX + 58 * cos(angle)
    tipY = pivotY + 58 * sin(angle)

    drawArrow(
        pivotX,
        pivotY,
        tipX,
        tipY,
        'gold',
        100,
        3
    )

    drawLabel(
        'α = ' + str(app.angleOfAttack) + '°',
        pivotX + 38,
        pivotY - 26,
        fill='gold',
        bold=True,
        size=11
    )


def drawMappedPlane(app):
    drawPanel(558, 132, 470, 458, 'darkSlateGray', 'seaGreen')

    drawLabel(
        '2. MAPPED PLANE: ROTATE THE AEROFOIL',
        793, 158,
        fill='white',
        bold=True,
        size=15
    )

    drawLabel(
        'Wind stays horizontal; A/D rotates wing and transformed flow',
        793, 178,
        fill='paleGreen',
        size=10
    )

    drawGrid(
        app.mappedCenterX,
        app.mappedCenterY,
        app.mappedScale,
        430,
        348,
        'paleGreen'
    )

    drawMappedWindVectors()
    drawMappedStreamlines(app)
    drawMappedAirfoil(app)
    drawAngleIndicator(app)
    drawFlowParticles(app)

    drawLabel(
        'w-plane',
        602, 564,
        fill='paleGreen',
        bold=True,
        size=12
    )

    drawLabel(
        'rotated aerofoil + transformed ideal flow',
        793, 564,
        fill='paleGreen',
        size=11
    )


# --------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------

def drawDashboard(app):
    drawPanel(22, 601, 1006, 84, 'midnightBlue', 'slateBlue')

    camber, thickness, liftIndex, rating, ratingColor = getDesignStats(app)
    kuttaText, kuttaColor = getKuttaStatus(app)

    drawLabel(
        'DESIGN TELEMETRY',
        100, 621,
        fill='gold',
        bold=True,
        size=13
    )

    drawLabel(
        'Camber',
        230, 620,
        fill='lightSteelBlue',
        size=10
    )

    drawLabel(
        str(round(camber, 1)) + '%',
        230, 646,
        fill='white',
        bold=True,
        size=17
    )

    drawLabel(
        'Thickness',
        355, 620,
        fill='lightSteelBlue',
        size=10
    )

    drawLabel(
        str(round(thickness, 1)) + '%',
        355, 646,
        fill='white',
        bold=True,
        size=17
    )

    drawLabel(
        'Aerofoil angle α',
        483, 620,
        fill='lightSteelBlue',
        size=10
    )

    drawLabel(
        str(app.angleOfAttack) + '°',
        483, 646,
        fill='gold',
        bold=True,
        size=17
    )

    drawLabel(
        'Circulation Γ',
        590, 620,
        fill='lightSteelBlue',
        size=10
    )

    drawLabel(
        str(round(app.circulation, 2)),
        590, 646,
        fill='white',
        bold=True,
        size=17
    )

    drawLabel(
        'Ideal lift index',
        710, 620,
        fill='lightSteelBlue',
        size=10
    )

    drawLabel(
        str(round(liftIndex, 2)),
        710, 646,
        fill=ratingColor,
        bold=True,
        size=17
    )

    drawLabel(
        rating,
        819, 620,
        fill=ratingColor,
        bold=True,
        size=11
    )

    drawLabel(
        kuttaText,
        908, 620,
        fill=kuttaColor,
        bold=True,
        size=9
    )

    drawLabel(
        'TARGET 1.25',
        819, 643,
        fill='lightSteelBlue',
        size=9
    )

    drawProgressBar(
        875, 638,
        128, 13,
        liftIndex / 1.25,
        ratingColor
    )

    drawLabel(
        'Wind fixed → wing rotates about quarter-chord pivot',
        257, 671,
        fill='gold',
        size=10
    )

    drawLabel(
        'Model: 2D, inviscid, ideal potential flow',
        740, 671,
        fill='lightSteelBlue',
        size=10
    )


# --------------------------------------------------------------
# Messages and help
# --------------------------------------------------------------

def drawMessage(app):
    if app.messageTimer > 0:
        drawRect(
            288, 133, 474, 29,
            fill='darkSlateBlue',
            border='gold',
            borderWidth=1,
            opacity=95
        )

        drawLabel(
            app.message,
            525, 147,
            fill='gold',
            bold=True,
            size=11
        )


def drawHelpOverlay(app):
    if not app.showHelp:
        return

    drawRect(
        0, 0, app.width, app.height,
        fill='black',
        opacity=72
    )

    drawPanel(
        212, 132, 626, 437,
        'midnightBlue',
        'gold'
    )

    drawLabel(
        'AEROFOIL DESIGN MISSION',
        525, 168,
        fill='gold',
        bold=True,
        size=21
    )

    drawLabel(
        'Turn a solved circle-flow problem into a rotating wing.',
        525, 198,
        fill='white',
        bold=True,
        size=13
    )

    instructions = [
        'The left panel starts with a solvable ideal-flow problem:',
        'flow around a generating circle in the z-plane.',
        '',
        'The Joukowski map w = z + 1/z transforms that circle',
        'and its flow curves into a wing-like aerofoil in the w-plane.',
        '',
        'Drag the gold circle handle to alter mapped camber.',
        'Use Q/E to alter thickness-like geometry.',
        'Use W/S to alter circulation and flow asymmetry.',
        '',
        'Use A/D to rotate the aerofoil about its quarter-chord pivot.',
        'The incoming wind remains horizontal, like a wind tunnel.',
        '',
        'Try preset 3, then press D repeatedly to visibly pitch the wing.'
    ]

    y = 229

    for line in instructions:
        drawLabel(
            line,
            525, y,
            fill='lightCyan',
            size=12
        )

        y += 20

    drawLabel(
        'CLICK ANYWHERE OR PRESS H TO START',
        525, 538,
        fill='springGreen',
        bold=True,
        size=13
    )


# --------------------------------------------------------------
# Main view
# --------------------------------------------------------------

def redrawAll(app):
    drawHeader(app)
    drawControls(app)
    drawSourcePlane(app)
    drawMappedPlane(app)
    drawDashboard(app)
    drawMessage(app)
    drawHelpOverlay(app)


# --------------------------------------------------------------
# Controller helpers
# --------------------------------------------------------------

def setMessage(app, text):
    app.message = text
    app.messageTimer = 100


def changeCirculation(app, amount):
    app.circulation = clamp(
        app.circulation + amount,
        -2.5,
        2.5
    )

    if amount > 0:
        setMessage(
            app,
            'Circulation increased: transformed flow becomes more asymmetric.'
        )
    else:
        setMessage(
            app,
            'Circulation decreased.'
        )

    rebuildCachedGeometry(app)


def changeAngle(app, amount):
    app.angleOfAttack = clamp(
        app.angleOfAttack + amount,
        -18,
        18
    )

    setMessage(
        app,
        'Aerofoil pitched to ' +
        str(app.angleOfAttack) +
        '°. Wind remains horizontal.'
    )


def changeRadius(app, amount):
    app.circleRadius = clamp(
        app.circleRadius + amount,
        0.94,
        1.30
    )

    if amount > 0:
        setMessage(
            app,
            'Generating circle enlarged: mapped profile becomes thicker.'
        )
    else:
        setMessage(
            app,
            'Generating circle reduced: mapped profile becomes thinner.'
        )

    rebuildCachedGeometry(app)


def toggleFlow(app):
    app.running = not app.running

    if app.running:
        setMessage(app, 'Tracer particles resumed.')
    else:
        setMessage(app, 'Tracer particles paused.')


def applyPreset(app, preset):
    if preset == 1:
        app.circleX = -0.10
        app.circleY = 0.00
        app.circleRadius = 1.10
        app.circulation = 0.00
        app.angleOfAttack = 0

        setMessage(
            app,
            'Preset 1: symmetric aerofoil, neutral angle, no circulation.'
        )

    elif preset == 2:
        app.circleX = -0.10
        app.circleY = 0.17
        app.circleRadius = 1.10
        app.circulation = 0.60
        app.angleOfAttack = 3

        setMessage(
            app,
            'Preset 2: cambered aerofoil at moderate positive angle.'
        )

    elif preset == 3:
        app.circleX = -0.12
        app.circleY = 0.24
        app.circleRadius = 1.14
        app.circulation = 1.20
        app.angleOfAttack = 7

        setMessage(
            app,
            'Preset 3: high-lift aerofoil. Press A/D to pitch the wing.'
        )

    rebuildCachedGeometry(app)


# --------------------------------------------------------------
# Events
# --------------------------------------------------------------

def onStep(app):
    # Geometry is cached. Animation only advances particle locations.
    if app.running:
        app.particleOffset += 0.45

    if app.messageTimer > 0:
        app.messageTimer -= 1


def onMousePress(app, mouseX, mouseY):
    if app.showHelp:
        app.showHelp = False
        return

    if 24 <= mouseX <= 79 and 99 <= mouseY <= 123:
        changeCirculation(app, 0.20)

    elif 84 <= mouseX <= 139 and 99 <= mouseY <= 123:
        changeCirculation(app, -0.20)

    elif 147 <= mouseX <= 202 and 99 <= mouseY <= 123:
        changeAngle(app, -1)

    elif 207 <= mouseX <= 262 and 99 <= mouseY <= 123:
        changeAngle(app, 1)

    elif 270 <= mouseX <= 328 and 99 <= mouseY <= 123:
        changeRadius(app, -0.04)

    elif 333 <= mouseX <= 395 and 99 <= mouseY <= 123:
        changeRadius(app, 0.04)

    elif 404 <= mouseX <= 472 and 99 <= mouseY <= 123:
        toggleFlow(app)

    elif 644 <= mouseX <= 711 and 99 <= mouseY <= 123:
        applyPreset(app, 1)

    elif 717 <= mouseX <= 787 and 99 <= mouseY <= 123:
        applyPreset(app, 2)

    elif 793 <= mouseX <= 858 and 99 <= mouseY <= 123:
        applyPreset(app, 3)

    elif 880 <= mouseX <= 942 and 99 <= mouseY <= 123:
        resetApp(app)

    elif 948 <= mouseX <= 1022 and 99 <= mouseY <= 123:
        app.showHelp = True

    else:
        handleX, handleY = sourceToScreen(
            app,
            app.circleX,
            app.circleY
        )

        if distanceBetween(mouseX, mouseY, handleX, handleY) <= 18:
            app.draggingHandle = True

            setMessage(
                app,
                'Handle engaged: drag to reshape the mapped aerofoil.'
            )


def onMouseDrag(app, mouseX, mouseY):
    if app.draggingHandle:
        sourceX, sourceY = screenToSource(app, mouseX, mouseY)

        app.circleX = clamp(sourceX, -0.38, 0.28)
        app.circleY = clamp(sourceY, -0.43, 0.43)

        rebuildCachedGeometry(app)


def onMouseRelease(app, mouseX, mouseY):
    app.draggingHandle = False


def onKeyPress(app, key):
    if key == 'h':
        app.showHelp = not app.showHelp

    elif key == 'r':
        resetApp(app)

    elif key == 'space':
        toggleFlow(app)

    elif key == 'w':
        changeCirculation(app, 0.20)

    elif key == 's':
        changeCirculation(app, -0.20)

    elif key == 'a':
        changeAngle(app, -1)

    elif key == 'd':
        changeAngle(app, 1)

    elif key == 'q':
        changeRadius(app, -0.04)

    elif key == 'e':
        changeRadius(app, 0.04)

    elif key == '1':
        applyPreset(app, 1)

    elif key == '2':
        applyPreset(app, 2)

    elif key == '3':
        applyPreset(app, 3)


def main():
    print("[DEBUG main] runApp 1050x700")
    runApp(width=1050, height=700)
    print("[DEBUG main] runApp done")

print("[DEBUG] calling main")
main()
print("[DEBUG] main done")

