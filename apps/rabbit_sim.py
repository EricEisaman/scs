# The following code is valid cmu_graphics - rabbits and foxes animate
from scs import *
import math
import random

# ------------------------------------------------------------
# Rabbit Population Dynamics Lab
# CMU CS Academy CPCS / MVC-compatible simulation
#
# Ecological model, calculated once per simulated day:
#
# carryingCapacity = habitatCapacity * foodAvailability
# rabbitGrowth = r * rabbits * (1 - rabbits / carryingCapacity)
# predation = foxes * predationRate * rabbits / (rabbits + halfSaturation)
#
# nextRabbits = rabbits + rabbitGrowth - predation
# ------------------------------------------------------------

def onAppStart(app):
    app.stepsPerSecond = 20

    # Layout
    app.controlWidth = 290
    app.worldLeft = 290
    app.worldTop = 0
    app.worldWidth = app.width - app.worldLeft
    app.worldHeight = app.height

    # Slider definitions:
    # (name, minimum, maximum, currentValue, label, color)
    app.sliders = [
        ['rabbits', 2, 160, 28, 'Starting rabbits', 'white'],
        ['habitat', 1, 10, 6, 'Habitat area', 'mediumSeaGreen'],
        ['grass', 1, 10, 7, 'Orchard grass', 'lawnGreen'],
        ['foxes', 0, 18, 3, 'Foxes', 'tomato']
    ]

    app.activeSlider = None
    app.running = False
    app.speed = 1
    app.stepCounter = 0

    # Visual-state variables
    app.cloudOffset = 0
    app.sunAngle = 0
    app.pulse = 0
    app.message = 'Set conditions, then press RUN.'
    app.eventMessage = 'A meadow is waiting for its first ecological experiment.'
    app.day = 0

    # Physical / ecological parameters
    app.growthRate = 0.18
    app.baseHabitatCapacity = 58
    app.predationRate = 3.6
    app.halfSaturation = 24

    # Particle-like visual records
    app.rabbitsVisual = []
    app.foxesVisual = []
    app.stars = []
    app.flowers = []
    app.trees = []

    makeLandscape(app)
    resetSimulation(app)


# ------------------------------------------------------------
# MODEL HELPERS
# ------------------------------------------------------------

def getSliderValue(app, name):
    for slider in app.sliders:
        if slider[0] == name:
            return slider[3]
    return 0


def setSliderValue(app, name, value):
    for slider in app.sliders:
        if slider[0] == name:
            slider[3] = max(slider[1], min(slider[2], value))


def makeLandscape(app):
    for i in range(48):
        x = random.randint(app.worldLeft + 10, app.width - 10)
        y = random.randint(10, 145)
        r = random.choice([1, 1, 1, 2])
        app.stars.append([x, y, r])

    for i in range(45):
        x = random.randint(app.worldLeft + 12, app.width - 12)
        y = random.randint(355, app.height - 16)
        color = random.choice(['hotPink', 'gold', 'violet', 'white', 'orange'])
        app.flowers.append([x, y, color])

    for i in range(11):
        x = random.randint(app.worldLeft + 10, app.width - 24)
        y = random.randint(258, 338)
        scale = random.uniform(0.65, 1.15)
        app.trees.append([x, y, scale])


def resetSimulation(app):
    app.running = False
    app.day = 0
    app.stepCounter = 0

    app.rabbits = float(getSliderValue(app, 'rabbits'))
    app.foxes = float(getSliderValue(app, 'foxes'))
    app.habitat = getSliderValue(app, 'habitat')
    app.grass = getSliderValue(app, 'grass')

    app.capacity = calculateCapacity(app)
    app.lastGrowth = 0
    app.lastPredation = 0
    app.lastFoodPressure = 0

    app.history = [app.rabbits]
    app.capacityHistory = [app.capacity]
    app.foxHistory = [app.foxes]

    createAnimalVisuals(app)
    app.message = 'Ready: day 0. Press RUN to begin.'
    app.eventMessage = describeConditions(app)


def calculateCapacity(app):
    habitatCapacity = app.baseHabitatCapacity * app.habitat / 5
    foodMultiplier = 0.22 + 0.078 * app.grass
    return max(8, habitatCapacity * foodMultiplier)


def createAnimalVisuals(app):
    app.rabbitsVisual = []
    app.foxesVisual = []

    shownRabbits = min(42, max(2, int(app.rabbits)))
    shownFoxes = min(9, int(app.foxes))

    for i in range(shownRabbits):
        x = random.randint(app.worldLeft + 20, app.width - 22)
        y = random.randint(300, app.height - 28)
        app.rabbitsVisual.append([
            x, y,
            random.choice([-1, 1]),
            random.uniform(0.35, 0.95),
            random.randint(0, 50)
        ])

    for i in range(shownFoxes):
        x = random.randint(app.worldLeft + 28, app.width - 30)
        y = random.randint(300, app.height - 28)
        app.foxesVisual.append([
            x, y,
            random.choice([-1, 1]),
            random.uniform(0.45, 0.85),
            random.randint(0, 50)
        ])


def updateSimulation(app):
    app.habitat = getSliderValue(app, 'habitat')
    app.grass = getSliderValue(app, 'grass')

    if app.rabbits < 5 and app.foxes > 0:
        app.foxes = max(0, app.foxes - 0.15)
    elif app.rabbits > 55 and app.foxes < getSliderValue(app, 'foxes'):
        app.foxes += 0.04

    app.capacity = calculateCapacity(app)

    logisticGrowth = (
        app.growthRate * app.rabbits * (1 - app.rabbits / app.capacity)
    )

    predation = (
        app.foxes * app.predationRate *
        app.rabbits / (app.rabbits + app.halfSaturation)
    )

    crowding = max(0, app.rabbits - app.capacity) * 0.045

    app.lastGrowth = logisticGrowth
    app.lastPredation = predation
    app.lastFoodPressure = crowding

    app.rabbits = max(0, app.rabbits + logisticGrowth - predation - crowding)
    app.day += 1

    app.history.append(app.rabbits)
    app.capacityHistory.append(app.capacity)
    app.foxHistory.append(app.foxes)

    if len(app.history) > 90:
        app.history.pop(0)
        app.capacityHistory.pop(0)
        app.foxHistory.pop(0)

    updateAnimalVisuals(app)
    updateStatusMessage(app)


def updateAnimalVisuals(app):
    desiredRabbits = min(42, max(0, int(app.rabbits)))
    desiredFoxes = min(9, max(0, int(app.foxes)))

    while len(app.rabbitsVisual) < desiredRabbits:
        app.rabbitsVisual.append([
            random.randint(app.worldLeft + 20, app.width - 22),
            random.randint(300, app.height - 28),
            random.choice([-1, 1]),
            random.uniform(0.35, 0.95),
            random.randint(0, 50)
        ])

    while len(app.rabbitsVisual) > desiredRabbits:
        app.rabbitsVisual.pop()

    while len(app.foxesVisual) < desiredFoxes:
        app.foxesVisual.append([
            random.randint(app.worldLeft + 28, app.width - 30),
            random.randint(300, app.height - 28),
            random.choice([-1, 1]),
            random.uniform(0.45, 0.85),
            random.randint(0, 50)
        ])

    while len(app.foxesVisual) > desiredFoxes:
        app.foxesVisual.pop()

    for animal in app.rabbitsVisual:
        animal[0] += animal[2] * animal[3] * 2.2
        animal[4] += 1
        if animal[0] < app.worldLeft + 14 or animal[0] > app.width - 14:
            animal[2] *= -1
        animal[1] += math.sin(animal[4] / 7) * 0.4
        animal[1] = max(292, min(app.height - 28, animal[1]))

    for animal in app.foxesVisual:
        animal[0] += animal[2] * animal[3] * 2.8
        animal[4] += 1
        if animal[0] < app.worldLeft + 17 or animal[0] > app.width - 17:
            animal[2] *= -1
        animal[1] += math.sin(animal[4] / 9) * 0.35
        animal[1] = max(300, min(app.height - 30, animal[1]))


def updateStatusMessage(app):
    if app.rabbits < 1:
        app.message = 'Population collapse: the meadow has no rabbits left.'
        app.eventMessage = 'Predators and environmental limits overcame rabbit reproduction.'
    elif app.rabbits < 0.30 * app.capacity:
        app.message = 'Low population: recovery is possible if predation eases.'
        app.eventMessage = 'At low density, each predator has a large effect.'
    elif app.rabbits > 1.15 * app.capacity:
        app.message = "Overshoot! Rabbits exceed the meadow's current carrying capacity."
        app.eventMessage = 'Food competition and crowding now push population growth below zero.'
    elif app.lastGrowth > app.lastPredation:
        app.message = 'Population is growing: births exceed predator losses.'
        app.eventMessage = 'The logistic term is positive because rabbits are below carrying capacity.'
    else:
        app.message = 'Population is declining: predators or limited resources dominate.'
        app.eventMessage = 'Compare predation with growth in the statistics panel.'


def describeConditions(app):
    if app.foxes >= 10:
        predatorText = 'Strong fox pressure will challenge rabbit survival.'
    elif app.foxes == 0:
        predatorText = 'No foxes: watch environmental limits alone shape the population.'
    else:
        predatorText = 'Foxes create a realistic mortality pressure.'

    if app.grass <= 3:
        foodText = ' Food is scarce, so carrying capacity is low.'
    elif app.grass >= 8:
        foodText = ' Grass is abundant, supporting more rabbits.'
    else:
        foodText = ' Food is moderate.'

    return predatorText + foodText


# ------------------------------------------------------------
# CONTROLLER
# ------------------------------------------------------------

def onStep(app):
    app.cloudOffset = (app.cloudOffset + 0.7) % (app.worldWidth + 150)
    app.sunAngle += 0.018
    app.pulse += 0.12

    if app.running:
        app.stepCounter += 1

        # One ecological day every few visual frames.
        framesPerDay = max(1, 9 - 2 * app.speed)
        if app.stepCounter % framesPerDay == 0:
            updateSimulation(app)

        # Animals still move every frame.
        else:
            updateAnimalVisuals(app)


def onMousePress(app, mouseX, mouseY):
    if 18 <= mouseX <= 130 and 428 <= mouseY <= 466:
        app.running = not app.running
        if app.running:
            app.message = 'Simulation running: one day at a time.'
        else:
            app.message = 'Paused. Adjust conditions or continue.'
        return

    if 145 <= mouseX <= 270 and 428 <= mouseY <= 466:
        resetSimulation(app)
        return

    if 20 <= mouseX <= 82 and 485 <= mouseY <= 515:
        app.speed = max(1, app.speed - 1)
        return

    if 205 <= mouseX <= 268 and 485 <= mouseY <= 515:
        app.speed = min(4, app.speed + 1)
        return

    sliderTop = 108
    for i in range(len(app.sliders)):
        y = sliderTop + i * 68 + 29
        if 18 <= mouseX <= 268 and y - 15 <= mouseY <= y + 15:
            app.activeSlider = i
            updateActiveSlider(app, mouseX)
            return


def onMouseDrag(app, mouseX, mouseY):
    if app.activeSlider != None:
        updateActiveSlider(app, mouseX)


def onMouseRelease(app, mouseX, mouseY):
    app.activeSlider = None


def onKeyPress(app, key):
    if key == 'space':
        app.running = not app.running
        if app.running:
            app.message = 'Simulation running: one day at a time.'
        else:
            app.message = 'Paused. Press Space to continue.'
    elif key == 'r':
        resetSimulation(app)
    elif key == 'right':
        if not app.running:
            updateSimulation(app)
            # ensure visuals update after manual step
            updateAnimalVisuals(app)
    elif key == '1':
        app.speed = 1
    elif key == '2':
        app.speed = 2
    elif key == '3':
        app.speed = 3
    elif key == '4':
        app.speed = 4


def updateActiveSlider(app, mouseX):
    slider = app.sliders[app.activeSlider]
    left = 25
    right = 260
    ratio = max(0, min(1, (mouseX - left) / (right - left)))
    value = slider[1] + ratio * (slider[2] - slider[1])
    slider[3] = int(round(value))
    if slider[0] == 'rabbits':
        app.rabbits = float(slider[3])
    elif slider[0] == 'foxes':
        app.foxes = float(slider[3])
    app.habitat = getSliderValue(app, 'habitat')
    app.grass = getSliderValue(app, 'grass')
    app.capacity = calculateCapacity(app)
    app.message = 'Conditions changed. Press RESET, then RUN for a clean experiment.'
    app.eventMessage = describeConditions(app)


# ------------------------------------------------------------
# VIEW
# ------------------------------------------------------------

def redrawAll(app):
    drawControlPanel(app)
    drawMeadow(app)
    drawDataPanel(app)
    drawInstructions(app)


def drawControlPanel(app):
    drawRect(0, 0, app.controlWidth, app.height, fill='midnightBlue')
    drawRect(6, 7, app.controlWidth - 12, app.height - 14,
             fill='darkSlateBlue', border='cornflowerBlue', borderWidth=2)

    drawLabel('RABBIT MEADOW', 145, 31, fill='white',
              size=22, bold=True)
    drawLabel('Population Dynamics Lab', 145, 54, fill='lightCyan',
              size=12, bold=True)
    drawLine(18, 68, 270, 68, fill='cornflowerBlue', lineWidth=2)

    drawLabel('EXPERIMENT CONTROLS', 145, 87, fill='gold',
              size=13, bold=True)

    sliderTop = 108
    for i in range(len(app.sliders)):
        drawSlider(app, app.sliders[i], sliderTop + i * 68)

    runColor = 'crimson' if app.running else 'forestGreen'
    runText = 'PAUSE' if app.running else 'RUN'
    drawRect(18, 428, 112, 38,fill=runColor,
                    border='white', borderWidth=1)
    drawLabel(runText, 74, 447, fill='white', size=15, bold=True)

    drawRect(145, 428, 125, 38, fill='slateGray',
                    border='white', borderWidth=1)
    drawLabel('RESET', 207, 447, fill='white', size=15, bold=True)

    drawLabel('Simulation speed', 145, 482, fill='lightCyan',
              size=12, bold=True)
    drawRect(20, 486, 62, 29, fill='steelBlue',
                    border='white', borderWidth=1)
    drawLabel('-', 51, 500, fill='white', size=22, bold=True)

    drawLabel('x' + str(app.speed), 145, 501, fill='gold',
              size=18, bold=True)

    drawRect(205, 486, 63, 29,fill='steelBlue',
                    border='white', borderWidth=1)
    drawLabel('+', 236, 500, fill='white', size=20, bold=True)

    drawLine(18, 529, 270, 529, fill='cornflowerBlue', lineWidth=1)

    drawLabel('THE MODEL', 145, 548, fill='gold', size=13, bold=True)
    drawLabel('Growth = rN(1 - N / K)', 145, 571, fill='white',
              size=14, bold=True)
    drawLabel('K changes with habitat + grass', 145, 591,
              fill='lightCyan', size=11)
    drawLabel('Foxes remove rabbits each day', 145, 609,
              fill='lightCyan', size=11)

    drawRect(18, 623, 252, 46, fill='navy',
                    border='cornflowerBlue')
    drawLabel(app.message, 144, 640, fill='white', size=10, bold=True)
    drawLabel('Day ' + str(app.day), 144, 657, fill='gold',
              size=12, bold=True)


def drawSlider(app, slider, top):
    name, low, high, value, label, color = slider
    left = 25
    right = 260
    y = top + 29
    ratio = (value - low) / (high - low)

    drawLabel(label, 25, top + 4, align='left', fill='white',
              size=12, bold=True)
    drawLabel(str(value), 260, top + 4, align='right', fill='gold',
              size=14, bold=True)

    drawLine(left, y, right, y, fill='black', lineWidth=8)
    drawLine(left, y, left + ratio * (right - left), y,
             fill=color, lineWidth=8)

    knobX = left + ratio * (right - left)
    drawCircle(knobX, y, 10, fill='white', border=color, borderWidth=3)

    if name == 'habitat':
        unit = 'scale: land / shelter'
    elif name == 'grass':
        unit = 'scale: food supply'
    elif name == 'foxes':
        unit = 'predators'
    else:
        unit = 'animals at day 0'

    drawLabel(unit, 25, top + 50, align='left', fill='lightSteelBlue',
              size=9)


def drawMeadow(app):
    drawSky(app)
    drawHills(app)
    drawClouds(app)
    drawTrees(app)
    drawGrassField(app)
    drawFlowers(app)
    drawAnimals(app)
    drawWorldHeader(app)


def drawSky(app):
    daylight = (math.sin(app.sunAngle) + 1) / 2

    if daylight > 0.56:
        sky = 'skyBlue'
        horizon = 'lightCyan'
    elif daylight > 0.28:
        sky = 'mediumPurple'
        horizon = 'plum'
    else:
        sky = 'midnightBlue'
        horizon = 'darkSlateBlue'

    drawRect(app.worldLeft, 0, app.worldWidth, 300, fill=sky)
    drawRect(app.worldLeft, 190, app.worldWidth, 110, fill=horizon)

    sx = app.worldLeft + 55 + (app.worldWidth - 110) * daylight
    sy = 145 - 105 * math.sin(math.pi * daylight)

    if daylight > 0.36:
        drawCircle(sx, sy, 29, fill='gold', opacity=30)
        drawCircle(sx, sy, 20, fill='yellow')
        for angle in range(0, 360, 45):
            x2 = sx + 33 * math.cos(math.radians(angle))
            y2 = sy + 33 * math.sin(math.radians(angle))
            x3 = sx + 44 * math.cos(math.radians(angle))
            y3 = sy + 44 * math.sin(math.radians(angle))
            drawLine(x2, y2, x3, y3, fill='gold', lineWidth=2)
    else:
        for star in app.stars:
            drawCircle(star[0], star[1], star[2], fill='white', opacity=80)
        drawCircle(sx, sy, 22, fill='lightYellow')
        drawCircle(sx + 8, sy - 6, 21, fill=sky)


def drawHills(app):
    drawOval(app.worldLeft + 190, 440, 360, 175, fill='forestGreen')
    drawOval(app.worldLeft + 400, 360, 360, 155, fill='mediumSeaGreen')
    drawRect(app.worldLeft, 290, app.worldWidth, 90, fill='forestGreen')


def drawClouds(app):
    cloudX = app.worldLeft + 20 + app.cloudOffset
    positions = [
        (cloudX - 100, 65, 1.0),
        (cloudX + 190, 100, 0.75),
        (cloudX + 465, 48, 1.1)
    ]

    for x, y, scale in positions:
        wrappedX = app.worldLeft + ((x - app.worldLeft) % (app.worldWidth + 170)) + 70
        drawCloud(wrappedX, y, scale)


def drawCloud(x, y, scale):
    drawOval(x, y, 72 * scale, 28 * scale, fill='white', opacity=70)
    drawCircle(x + 18 * scale, y - 4 * scale, 17 * scale,
               fill='white', opacity=70)
    drawCircle(x + 39 * scale, y - 11 * scale, 22 * scale,
               fill='white', opacity=70)
    drawCircle(x + 59 * scale, y - 3 * scale, 16 * scale,
               fill='white', opacity=70)


def drawTrees(app):
    for tree in app.trees:
        x, y, scale = tree
        trunkW = 10 * scale
        trunkH = 32 * scale
        drawRect(x, y, trunkW, trunkH, fill='saddleBrown')
        drawCircle(x + 5 * scale, y - 8 * scale, 20 * scale,
                   fill='darkGreen')
        drawCircle(x - 6 * scale, y + 2 * scale, 14 * scale,
                   fill='forestGreen')
        drawCircle(x + 17 * scale, y + 2 * scale, 15 * scale,
                   fill='forestGreen')


def drawGrassField(app):
    grassLevel = getSliderValue(app, 'grass')
    fieldColor = 'yellowGreen' if grassLevel >= 6 else 'oliveDrab'
    drawRect(app.worldLeft, 337, app.worldWidth, app.height - 337,
             fill=fieldColor)

    patchCount = 5 + grassLevel * 3
    for i in range(patchCount):
        x = app.worldLeft + 14 + ((i * 67) % int(app.worldWidth - 30))
        y = 350 + ((i * 43) % int(app.height - 375))
        drawGrassPatch(x, y, grassLevel)


def drawGrassPatch(x, y, level):
    height = 5 + level
    drawLine(x, y, x - 3, y - height, fill='darkGreen', lineWidth=1)
    drawLine(x + 3, y, x + 4, y - height - 2, fill='green', lineWidth=1)
    drawLine(x + 6, y, x + 8, y - height + 1, fill='limeGreen', lineWidth=1)


def drawFlowers(app):
    for x, y, color in app.flowers:
        drawLine(x, y, x, y + 7, fill='darkGreen', lineWidth=1)
        drawCircle(x, y, 3, fill=color)
        drawCircle(x, y, 1, fill='gold')


def drawAnimals(app):
    for rabbit in app.rabbitsVisual:
        drawRabbit(rabbit[0], rabbit[1], rabbit[2], rabbit[4])

    for fox in app.foxesVisual:
        drawFox(fox[0], fox[1], fox[2], fox[4])

    if app.rabbits > 42:
        drawRect(app.worldLeft + 16, app.height - 42, 180, 25,
                        fill='white', opacity=75)
        drawLabel('+' + str(int(app.rabbits) - 42) +
                  ' rabbits beyond this view',
                  app.worldLeft + 106, app.height - 29,
                  fill='darkSlateGray', size=10, bold=True)


def drawRabbit(x, y, direction, tick):
    bodyColor = 'white'
    earTilt = math.sin(tick / 4) * 2

    drawOval(x - 9, y - 5, 18, 12, fill=bodyColor,
             border='lightGray', borderWidth=1)
    drawCircle(x + direction * 8, y - 8, 6, fill=bodyColor,
               border='lightGray', borderWidth=1)

    drawOval(x + direction * 5 - 2, y - 21 + earTilt, 4, 12,
             fill='white', border='lightGray')
    drawOval(x + direction * 10 - 2, y - 20 - earTilt, 4, 12,
             fill='white', border='lightGray')

    drawCircle(x + direction * 10, y - 9, 1.3, fill='black')
    drawCircle(x - direction * 10, y - 4, 3, fill='white',
               border='lightGray')


def drawFox(x, y, direction, tick):
    drawOval(x - 12, y - 7, 25, 13, fill='orangeRed',
             border='saddleBrown', borderWidth=1)
    drawPolygon(
        x + direction * 10, y - 13,
        x + direction * 18, y - 7,
        x + direction * 10, y - 2,
        fill='orangeRed', border='saddleBrown'
    )

    drawPolygon(
        x + direction * 9, y - 15,
        x + direction * 12, y - 23,
        x + direction * 15, y - 13,
        fill='saddleBrown'
    )

    drawPolygon(
        x - direction * 10, y - 3,
        x - direction * 23, y - 10,
        x - direction * 20, y + 3,
        fill='orangeRed', border='saddleBrown'
    )

    drawCircle(x + direction * 15, y - 8, 1.2, fill='black')
    drawLine(x - 2, y + 6, x + 2, y + 6, fill='saddleBrown', lineWidth=2)


def drawWorldHeader(app):
    drawRect(app.worldLeft + 14, 14, 265, 54,
                    fill='midnightBlue', opacity=78,
                    border='lightCyan', borderWidth=1)
    drawLabel('LIVE MEADOW • DAY ' + str(app.day),
              app.worldLeft + 147, 33,
              fill='white', size=14, bold=True)
    drawLabel('Rabbits, resources, and predators interact over time',
              app.worldLeft + 147, 51,
              fill='lightCyan', size=10)


def drawDataPanel(app):
    x = app.worldLeft + 14
    y = 68
    w = app.worldWidth - 25
    h = 215

    drawRect(x, y, w, h, fill='white', opacity=88,
                    border='darkSlateGray', borderWidth=2)

    cardY = y + 15
    cardW = (w - 40) / 4
    drawStatCard(x + 10, cardY, cardW, 'RABBITS',
                 str(round(app.rabbits, 1)), 'white', 'royalBlue')
    drawStatCard(x + 18 + cardW, cardY, cardW, 'CARRYING K',
                 str(round(app.capacity, 1)), 'paleGreen', 'forestGreen')
    drawStatCard(x + 26 + 2 * cardW, cardY, cardW, 'FOXES',
                 str(round(app.foxes, 1)), 'mistyRose', 'crimson')
    drawStatCard(x + 34 + 3 * cardW, cardY, cardW, 'GRASS',
                 str(getSliderValue(app, 'grass')) + ' / 10',
                 'lightYellow', 'oliveDrab')

    drawLabel(app.eventMessage, x + w / 2, y + 92,
              fill='darkSlateGray', size=11, bold=True)

    drawLine(x + 15, y + 108, x + w - 15, y + 108,
             fill='lightGray', lineWidth=1)

    growthText = formatSigned(app.lastGrowth)
    predationText = formatSigned(-app.lastPredation)
    crowdText = formatSigned(-app.lastFoodPressure)

    drawLabel('Daily balance:', x + 15, y + 129, align='left',
              fill='darkSlateGray', size=11, bold=True)
    drawLabel('logistic growth ' + growthText,
              x + 105, y + 129, align='left',
              fill='forestGreen', size=11, bold=True)
    drawLabel('fox effect ' + predationText,
              x + 245, y + 129, align='left',
              fill='crimson', size=11, bold=True)
    drawLabel('crowding ' + crowdText,
              x + 365, y + 129, align='left',
              fill='darkOrange', size=11, bold=True)

    drawGraph(app, x + 15, y + 143, w - 30, 64)


def drawStatCard(x, y, w, title, value, fillColor, borderColor):
    drawRect(x, y, w, 55, fill=fillColor,
                    border=borderColor, borderWidth=2)
    drawLabel(title, x + w / 2, y + 14, fill='darkSlateGray',
              size=9, bold=True)
    drawLabel(value, x + w / 2, y + 37, fill=borderColor,
              size=17, bold=True)


def drawGraph(app, x, y, w, h):
    drawRect(x, y, w, h, fill='aliceBlue', border='lightSlateGray')

    if len(app.history) < 2:
        drawLabel('Population history appears here as time passes.',
                  x + w / 2, y + h / 2, fill='slateGray', size=10)
        return

    maxValue = max(20, max(app.history), max(app.capacityHistory)) * 1.08
    count = len(app.history)
    dx = w / max(1, count - 1)

    previous = None
    for i in range(count):
        px = x + i * dx
        py = y + h - (app.capacityHistory[i] / maxValue) * h
        if previous != None and i % 2 == 0:
            drawLine(previous[0], previous[1], px, py,
                     fill='forestGreen', lineWidth=2)
        previous = (px, py)

    previous = None
    for i in range(count):
        px = x + i * dx
        py = y + h - (app.history[i] / maxValue) * h
        if previous != None:
            drawLine(previous[0], previous[1], px, py,
                     fill='royalBlue', lineWidth=2)
        previous = (px, py)

    drawLabel('blue: rabbits', x + 4, y + 5, align='left',
              fill='royalBlue', size=8, bold=True)
    drawLabel('green: capacity', x + 90, y + 5, align='left',
              fill='forestGreen', size=8, bold=True)


def formatSigned(value):
    rounded = round(value, 1)
    if rounded > 0:
        return '+' + str(rounded)
    return str(rounded)


def drawInstructions(app):
    x = app.worldLeft + 14
    y = app.height - 88
    w = app.worldWidth - 28

    drawRect(x, y, w, 72, fill='midnightBlue', opacity=83,
                    border='lightCyan', borderWidth=1)

    drawLabel('TRY THIS:', x + 12, y + 16, align='left',
              fill='gold', size=11, bold=True)
    drawLabel('1. Set foxes to 0 and observe logistic growth toward K.',
              x + 12, y + 33, align='left',
              fill='white', size=10)
    drawLabel('2. Lower grass or habitat to reduce K.  3. Add foxes and compare the curve.',
              x + 12, y + 49, align='left',
              fill='white', size=10)
    drawLabel('Keyboard: Space = run/pause   R = reset   Right Arrow = one day   1-4 = speed',
              x + 12, y + 64, align='left',
              fill='lightCyan', size=9)


def main():
    runApp(width=1050, height=700)


main()
