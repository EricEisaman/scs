from scs import *
import math
import random

# ------------------------------------------------------------
# ACCELERATION ACADEMY: Launch Lab
# CMU CS Academy CPCS Mode
# Canvas: 1050 x 700
#
# Projectile Lab improvements:
# - Launch angle is now adjustable.
# - Cannon barrel, initial velocity arrow, real projectile,
#   and predicted trajectory use the SAME launch angle.
# - Horizontal and vertical velocity components are calculated
#   from the selected launch speed and launch angle.
# ------------------------------------------------------------

PURPLE = rgb(131, 65, 220)
DARK_PURPLE = rgb(63, 31, 115)
LAVENDER = rgb(222, 197, 255)
INK = rgb(20, 28, 50)
PANEL = rgb(248, 249, 255)
CYAN = rgb(67, 226, 242)
GOLD = rgb(255, 205, 65)
GREEN = rgb(62, 205, 122)
RED = rgb(244, 88, 105)
ORANGE = rgb(255, 142, 65)
BLUE = rgb(47, 130, 225)
NAVY = rgb(24, 30, 65)
SKY_BLUE = rgb(110, 194, 255)
GRASS = rgb(51, 135, 93)
DARK_GRAY = rgb(48, 57, 82)
LIGHT_BLUE = rgb(224, 246, 255)

# ------------------------------------------------------------
# App initialization
# ------------------------------------------------------------

def onAppStart(app):
    app.stepsPerSecond = 30
    resetGame(app)

def resetGame(app):
    app.screen = 'home'
    app.questionIndex = 0
    app.score = 0
    app.streak = 0
    app.selectedAnswer = None
    app.feedback = ''
    app.feedbackColor = INK
    app.time = 0

    # Projectile Lab variables.
    #
    # launchSpeed is a visual simulation speed measured in m/s.
    # launchAngle is measured above the horizontal.
    app.launchSpeed = 42
    app.launchAngle = 35

    app.projectileRunning = False
    app.projectileLanded = False
    app.projectileTime = 0
    app.projectileX = 0
    app.projectileY = 0
    app.projectileTrail = []

    # Flight zone geometry.
    app.labLeft = 385
    app.labTop = 108
    app.labWidth = 625
    app.labHeight = 492
    app.groundY = 585

    # Cannon pivot and muzzle will be calculated from launchAngle.
    app.cannonPivotX = 500
    app.cannonPivotY = 532
    app.barrelLength = 94

    app.muzzleX = 0
    app.muzzleY = 0
    updateMuzzlePosition(app)

    # Visual scale: simulation meters to canvas pixels.
    app.velocityScale = 4.7
    app.gravity = 42

    # Animated sky data.
    app.clouds = [
        [120, 115, 0.7],
        [440, 92, 1.0],
        [810, 142, 0.82],
        [1030, 78, 0.63]
    ]

    app.stars = []
    random.seed(22)

    for i in range(35):
        app.stars.append([
            random.randint(15, 1035),
            random.randint(15, 300),
            random.randint(0, 359)
        ])

    app.questions = [
        {
            'title': 'Checkpoint 1: Green-Light Boost',
            'category': 'ACCELERATION BASICS',
            'prompt': (
                'A car starts at a red light. When the light turns green, '
                'the car moves faster and faster in a straight line. Why '
                'is the car accelerating?'
            ),
            'choices': [
                'Its velocity is changing because its speed increases',
                'It has stopped moving',
                'Its mass is increasing',
                'Its direction never changes'
            ],
            'correct': 0,
            'explanation': (
                'Correct! Acceleration is any change in velocity. The car '
                'is speeding up, so its velocity is changing.'
            ),
            'graph': False
        },
        {
            'title': 'Checkpoint 2: Brake Zone',
            'category': 'SLOWING DOWN',
            'prompt': (
                'A skateboarder moves west and slows to a stop. Which '
                'direction is the skateboarder acceleration?'
            ),
            'choices': [
                'West, the same direction as the velocity',
                'East, opposite the velocity',
                'Upward, because the skateboard slows down',
                'There is no acceleration while slowing down'
            ],
            'correct': 1,
            'explanation': (
                'Correct! When an object slows down, acceleration points '
                'opposite the direction of its velocity.'
            ),
            'graph': False
        },
        {
            'title': 'Checkpoint 3: Graph Garage',
            'category': 'GRAPH EVIDENCE',
            'prompt': (
                'Use the speed-time graph. During which interval does the '
                'race cart have zero acceleration?'
            ),
            'choices': [
                '0 to 2 seconds',
                '2 to 4 seconds',
                '4 to 6 seconds',
                '6 to 8 seconds'
            ],
            'correct': 1,
            'explanation': (
                'Correct! A horizontal line has a slope of zero. On a '
                'speed-time graph, slope represents acceleration, so the '
                'cart has zero acceleration from 2 to 4 seconds.'
            ),
            'graph': True
        },
        {
            'title': 'Checkpoint 4: Acceleration Engine',
            'category': 'CALCULATE a',
            'prompt': (
                'An airplane starts from rest and reaches 80 m/s north in '
                '20 seconds. What is its acceleration?'
            ),
            'choices': [
                '4 m/s squared north',
                '16 m/s squared north',
                '60 m/s squared north',
                '4 m/s squared south'
            ],
            'correct': 0,
            'explanation': (
                'Correct! a = (vf - vi) / t = (80 - 0) / 20 = 4 m/s '
                'squared north.'
            ),
            'graph': False
        },
        {
            'title': 'Checkpoint 5: Carousel Core',
            'category': 'CIRCULAR MOTION',
            'prompt': (
                'A carousel horse moves at constant speed in a circle. '
                'Why is the horse still accelerating?'
            ),
            'choices': [
                'Its direction changes continuously',
                'Its mass is decreasing',
                'It is not moving in a circle',
                'Constant speed always means zero acceleration'
            ],
            'correct': 0,
            'explanation': (
                'Correct! Velocity includes direction. In circular motion, '
                'the velocity direction changes constantly, so the horse '
                'accelerates toward the center.'
            ),
            'graph': False
        },
        {
            'title': 'Checkpoint 6: Projectile Proof',
            'category': 'PROJECTILE MOTION',
            'prompt': (
                'A ball is thrown horizontally while another ball is dropped '
                'from the same height at the same instant. Ignoring air '
                'resistance, which hits the ground first?'
            ),
            'choices': [
                'The dropped ball',
                'The thrown ball',
                'They hit the ground at the same time',
                'Neither ball reaches the ground'
            ],
            'correct': 2,
            'explanation': (
                'Correct! Both balls have the same vertical downward '
                'acceleration from gravity, so they fall for the same '
                'amount of time.'
            ),
            'graph': False
        }
    ]

# ------------------------------------------------------------
# Projectile physics helpers
# ------------------------------------------------------------

def updateMuzzlePosition(app):
    # In screen coordinates, positive y goes down.
    # A positive launchAngle should aim up and right,
    # so the y component is subtracted.
    angleRadians = math.radians(app.launchAngle)

    app.muzzleX = (
        app.cannonPivotX
        + app.barrelLength * math.cos(angleRadians)
    )

    app.muzzleY = (
        app.cannonPivotY
        - app.barrelLength * math.sin(angleRadians)
    )

def getVelocityComponents(app):
    angleRadians = math.radians(app.launchAngle)

    horizontalVelocity = app.launchSpeed * math.cos(angleRadians)
    verticalVelocity = app.launchSpeed * math.sin(angleRadians)

    return horizontalVelocity, verticalVelocity

def getProjectilePosition(app, timeValue):
    horizontalVelocity, verticalVelocity = getVelocityComponents(app)

    x = (
        app.muzzleX
        + horizontalVelocity * app.velocityScale * timeValue
    )

    y = (
        app.muzzleY
        - verticalVelocity * app.velocityScale * timeValue
        + 0.5 * app.gravity * timeValue * timeValue
    )

    return x, y

# ------------------------------------------------------------
# Animation
# ------------------------------------------------------------

def onStep(app):
    app.time += 1

    for cloud in app.clouds:
        cloud[0] -= cloud[2]

        if cloud[0] < -210:
            cloud[0] = 1230

    updateProjectile(app)

def updateProjectile(app):
    if app.projectileRunning == False:
        return

    app.projectileTime += 0.035

    newX, newY = getProjectilePosition(
        app,
        app.projectileTime
    )

    app.projectileX = newX
    app.projectileY = newY

    # Record the visible trajectory.
    if (app.projectileX < app.labLeft + app.labWidth - 10 and
            app.projectileY < app.groundY - 8 and
            app.projectileX > app.labLeft):

        app.projectileTrail.append([
            app.projectileX,
            app.projectileY
        ])

        if len(app.projectileTrail) > 180:
            app.projectileTrail.pop(0)

    # Landing and right-edge conditions.
    if (app.projectileY >= app.groundY - 12 or
            app.projectileX >= app.labLeft + app.labWidth - 14):

        app.projectileRunning = False
        app.projectileLanded = True

        if app.projectileY > app.groundY - 12:
            app.projectileY = app.groundY - 12

        if app.projectileX > app.labLeft + app.labWidth - 14:
            app.projectileX = app.labLeft + app.labWidth - 14

# ------------------------------------------------------------
# Input events
# ------------------------------------------------------------

def onMousePress(app, mouseX, mouseY):
    if app.screen == 'home':
        if pointInRect(mouseX, mouseY, 365, 540, 320, 76):
            app.screen = 'question'

        elif pointInRect(mouseX, mouseY, 760, 540, 220, 76):
            app.screen = 'lab'
            resetProjectile(app)

    elif app.screen == 'question':
        handleQuestionClick(app, mouseX, mouseY)

    elif app.screen == 'graph':
        if pointInRect(mouseX, mouseY, 775, 22, 245, 56):
            app.screen = 'question'

    elif app.screen == 'lab':
        handleLabClick(app, mouseX, mouseY)

    elif app.screen == 'finish':
        if pointInRect(mouseX, mouseY, 365, 540, 320, 70):
            resetGame(app)

def onKeyPress(app, key):
    if app.screen == 'question':
        currentQuestion = app.questions[app.questionIndex]

        if key.lower() == 'g' and currentQuestion['graph']:
            app.screen = 'graph'

        elif key.lower() == 'r':
            resetGame(app)

    elif app.screen == 'graph':
        if key.lower() == 'g':
            app.screen = 'question'

    elif app.screen == 'lab':
        if key.lower() == 'space':
            launchProjectile(app)

        elif key.lower() == 'r':
            resetProjectile(app)

        elif key.lower() == 'escape':
            app.screen = 'home'

    elif app.screen == 'finish':
        if key.lower() == 'r':
            resetGame(app)

# ------------------------------------------------------------
# Question interactions
# ------------------------------------------------------------

def handleQuestionClick(app, mouseX, mouseY):
    question = app.questions[app.questionIndex]

    if question['graph']:
        if pointInRect(mouseX, mouseY, 765, 128, 225, 52):
            app.screen = 'graph'
            return

    for i in range(4):
        y = 363 + i * 68

        if pointInRect(mouseX, mouseY, 130, y, 790, 53):
            chooseAnswer(app, i)
            return

    if app.selectedAnswer != None:
        if pointInRect(mouseX, mouseY, 770, 642, 200, 38):
            if app.questionIndex < len(app.questions) - 1:
                app.questionIndex += 1
                app.selectedAnswer = None
                app.feedback = ''
            else:
                app.screen = 'finish'

def chooseAnswer(app, answerIndex):
    if app.selectedAnswer != None:
        return

    app.selectedAnswer = answerIndex
    question = app.questions[app.questionIndex]

    if answerIndex == question['correct']:
        app.score += 100 + app.streak * 25
        app.streak += 1
        app.feedback = question['explanation']
        app.feedbackColor = GREEN

    else:
        app.streak = 0
        correctText = question['choices'][question['correct']]

        app.feedback = (
            "Not quite. The best answer is '" + correctText + "'. "
            + question['explanation']
        )

        app.feedbackColor = RED

# ------------------------------------------------------------
# Projectile Lab interactions
# ------------------------------------------------------------

def handleLabClick(app, mouseX, mouseY):
    if pointInRect(mouseX, mouseY, 30, 22, 155, 45):
        app.screen = 'home'
        return

    # Launch-speed decrease.
    if pointInRect(mouseX, mouseY, 80, 218, 52, 44):
        if app.launchSpeed > 24:
            app.launchSpeed -= 3
            resetProjectile(app)
        return

    # Launch-speed increase.
    if pointInRect(mouseX, mouseY, 278, 218, 52, 44):
        if app.launchSpeed < 60:
            app.launchSpeed += 3
            resetProjectile(app)
        return

    # Launch-angle decrease.
    if pointInRect(mouseX, mouseY, 80, 320, 52, 44):
        if app.launchAngle > 10:
            app.launchAngle -= 5
            updateMuzzlePosition(app)
            resetProjectile(app)
        return

    # Launch-angle increase.
    if pointInRect(mouseX, mouseY, 278, 320, 52, 44):
        if app.launchAngle < 70:
            app.launchAngle += 5
            updateMuzzlePosition(app)
            resetProjectile(app)
        return

    # Launch projectile button.
    if pointInRect(mouseX, mouseY, 82, 405, 246, 55):
        launchProjectile(app)
        return

    # Reset flight button.
    if pointInRect(mouseX, mouseY, 82, 475, 246, 44):
        resetProjectile(app)
        return

def launchProjectile(app):
    updateMuzzlePosition(app)

    app.projectileRunning = True
    app.projectileLanded = False
    app.projectileTime = 0
    app.projectileX = app.muzzleX
    app.projectileY = app.muzzleY
    app.projectileTrail = []

def resetProjectile(app):
    updateMuzzlePosition(app)

    app.projectileRunning = False
    app.projectileLanded = False
    app.projectileTime = 0
    app.projectileX = app.muzzleX
    app.projectileY = app.muzzleY
    app.projectileTrail = []

# ------------------------------------------------------------
# Main redraw
# ------------------------------------------------------------

def redrawAll(app):
    if app.screen == 'home':
        drawHomeScreen(app)

    elif app.screen == 'question':
        drawQuestionScreen(app)

    elif app.screen == 'graph':
        drawGraphScreen(app)

    elif app.screen == 'lab':
        drawProjectileLab(app)

    elif app.screen == 'finish':
        drawFinishScreen(app)

# ------------------------------------------------------------
# General drawing helpers
# ------------------------------------------------------------

def pointInRect(x, y, left, top, width, height):
    return (left <= x <= left + width and
            top <= y <= top + height)

def drawButton(x, y, width, height, text,
               fillColor=PURPLE,
               textColor='white',
               borderColor=LAVENDER,
               textSize=16):
    drawRect(x, y, width, height,
             fill=fillColor,
             border=borderColor,
             borderWidth=2)

    drawLabel(text,
              x + width / 2,
              y + height / 2,
              size=textSize,
              bold=True,
              fill=textColor)

def drawWrappedText(text, x, y, maxChars,
                    lineHeight=20, size=15,
                    fill=INK, bold=False,
                    align='left'):
    words = text.split(' ')
    lines = []
    line = ''

    for word in words:
        if line == '':
            possibleLine = word
        else:
            possibleLine = line + ' ' + word

        if len(possibleLine) <= maxChars:
            line = possibleLine
        else:
            lines.append(line)
            line = word

    if line != '':
        lines.append(line)

    for i in range(len(lines)):
        drawLabel(lines[i],
                  x,
                  y + i * lineHeight,
                  size=size,
                  fill=fill,
                  bold=bold,
                  align=align)

# ------------------------------------------------------------
# Shared background functions
# ------------------------------------------------------------

def drawSkyBackground(app):
    drawRect(0, 0, 1050, 700,
             fill=gradient(rgb(77, 140, 240),
                           rgb(160, 225, 255),
                           start='top'))

    drawRect(0, 455, 1050, 245, fill=GRASS)
    drawRect(0, 570, 1050, 130, fill=rgb(42, 65, 82))

    for x in range(-20, 1100, 115):
        drawRect(x, 630, 65, 10, fill=GOLD)

    for cloud in app.clouds:
        drawCloud(cloud[0], cloud[1], cloud[2])

    drawSun(934, 88)

def drawCloud(x, y, scale):
    cloudColor = rgb(246, 251, 255)

    drawOval(x, y,
             110 * scale, 44 * scale,
             fill=cloudColor,
             opacity=83)

    drawOval(x + 38 * scale, y - 20 * scale,
             80 * scale, 64 * scale,
             fill=cloudColor,
             opacity=83)

    drawOval(x + 88 * scale, y - 6 * scale,
             95 * scale, 57 * scale,
             fill=cloudColor,
             opacity=83)

def drawSun(x, y):
    drawCircle(x, y, 42,
               fill=GOLD,
               opacity=88)

    for angle in range(0, 360, 45):
        radians = math.radians(angle)

        x1 = x + math.cos(radians) * 55
        y1 = y + math.sin(radians) * 55
        x2 = x + math.cos(radians) * 69
        y2 = y + math.sin(radians) * 69

        drawLine(x1, y1, x2, y2,
                 fill=GOLD,
                 lineWidth=4)

def drawTopBar(app, subtitle):
    drawRect(0, 0, 1050, 76,
             fill=NAVY,
             opacity=94)

    drawLabel('ACCELERATION ACADEMY',
              34, 29,
              size=22,
              bold=True,
              fill='white',
              align='left')

    drawLabel(subtitle,
              35, 55,
              size=12,
              bold=True,
              fill=LAVENDER,
              align='left')

    drawRect(760, 15, 120, 46,
             fill=rgb(49, 57, 100),
             border=LAVENDER,
             borderWidth=1)

    drawLabel('SCORE',
              820, 28,
              size=11,
              bold=True,
              fill=LAVENDER)

    drawLabel(str(app.score),
              820, 47,
              size=19,
              bold=True,
              fill='white')

    drawRect(895, 15, 120, 46,
             fill=rgb(49, 57, 100),
             border=LAVENDER,
             borderWidth=1)

    drawLabel('STREAK',
              955, 28,
              size=11,
              bold=True,
              fill=LAVENDER)

    drawLabel('x ' + str(app.streak),
              955, 47,
              size=17,
              bold=True,
              fill=GOLD)

# ------------------------------------------------------------
# Home screen
# ------------------------------------------------------------

def drawHomeScreen(app):
    drawSkyBackground(app)
    drawRollerCoaster(app, 770, 400, 1.0)

    drawRect(65, 125, 610, 370,
             fill=NAVY,
             opacity=90,
             border=LAVENDER,
             borderWidth=3)

    drawLabel('ACCELERATION',
              105, 196,
              size=47,
              bold=True,
              fill='white',
              align='left')

    drawLabel('ACADEMY',
              105, 250,
              size=47,
              bold=True,
              fill=CYAN,
              align='left')

    drawLabel('Launch Lab Physics Mission',
              108, 296,
              size=21,
              bold=True,
              fill=LAVENDER,
              align='left')

    drawWrappedText(
        'Ride the Speedstorm Coaster, decode graph evidence, calculate '
        'acceleration, and launch a projectile to save the science fair!',
        108, 345, 53,
        lineHeight=24,
        size=16,
        fill='white'
    )

    drawLabel('Mission skills:',
              108, 435,
              size=14,
              bold=True,
              fill=GOLD,
              align='left')

    drawLabel('Speed up',
              235, 435,
              size=14,
              fill='white',
              align='left')

    drawLabel('Slow down',
              340, 435,
              size=14,
              fill='white',
              align='left')

    drawLabel('Turn',
              470, 435,
              size=14,
              fill='white',
              align='left')

    drawLabel('Launch',
              550, 435,
              size=14,
              fill='white',
              align='left')

    drawButton(365, 540, 320, 76,
               'START MISSION',
               PURPLE,
               'white',
               LAVENDER,
               20)

    drawButton(760, 540, 220, 76,
               'PROJECTILE LAB',
               DARK_PURPLE,
               'white',
               LAVENDER,
               16)

    drawLabel('Solve six checkpoints or experiment in the optional launch lab.',
              525, 665,
              size=13,
              fill='white')

# ------------------------------------------------------------
# Question screen
# ------------------------------------------------------------

def drawQuestionScreen(app):
    drawSkyBackground(app)

    question = app.questions[app.questionIndex]

    drawTopBar(app, 'SPEEDSTORM MISSION')

    drawLabel('CHECKPOINT ' + str(app.questionIndex + 1) +
              ' / ' + str(len(app.questions)),
              47, 103,
              size=16,
              bold=True,
              fill='white',
              align='left')

    drawRect(47, 116, 530, 13,
             fill=rgb(36, 65, 105),
             border='white',
             borderWidth=1)

    completedWidth = 530 * app.questionIndex / len(app.questions)

    # Do not draw a zero-width rectangle.
    if completedWidth > 0:
        drawRect(47, 116, completedWidth, 13, fill=CYAN)

    for i in range(len(app.questions)):
        x = 47 + (i + 0.5) * 530 / len(app.questions)

        if i < app.questionIndex:
            dotColor = GOLD
        elif i == app.questionIndex:
            dotColor = CYAN
        else:
            dotColor = LAVENDER

        drawCircle(x, 122.5, 8,
                   fill=dotColor,
                   border='white',
                   borderWidth=1)

    drawRect(60, 148, 930, 478,
             fill=PANEL,
             border=LAVENDER,
             borderWidth=3,
             opacity=97)

    drawRect(90, 175, 275, 35, fill=DARK_PURPLE)

    drawLabel(question['category'],
              227, 192,
              size=13,
              bold=True,
              fill='white')

    drawLabel(question['title'],
              90, 238,
              size=24,
              bold=True,
              fill=INK,
              align='left')

    if question['graph']:
        drawButton(765, 128, 225, 52,
                   'VIEW GRAPH',
                   PURPLE,
                   'white',
                   LAVENDER,
                   16)

        drawLabel('Open graph evidence',
                  878, 190,
                  size=11,
                  fill='white')

    drawWrappedText(question['prompt'],
                    92, 280, 90,
                    lineHeight=23,
                    size=17,
                    fill=INK)

    choiceLetters = ['A', 'B', 'C', 'D']

    for i in range(4):
        y = 363 + i * 68

        choiceFill = 'white'
        choiceBorder = rgb(174, 185, 217)
        letterFill = DARK_PURPLE

        if app.selectedAnswer != None:
            if i == question['correct']:
                choiceFill = rgb(215, 250, 226)
                choiceBorder = GREEN
                letterFill = GREEN

            elif i == app.selectedAnswer:
                choiceFill = rgb(255, 226, 230)
                choiceBorder = RED
                letterFill = RED

        drawRect(130, y, 790, 53,
                 fill=choiceFill,
                 border=choiceBorder,
                 borderWidth=2)

        drawCircle(163, y + 26.5, 17,
                   fill=letterFill)

        drawLabel(choiceLetters[i],
                  163, y + 26.5,
                  size=15,
                  bold=True,
                  fill='white')

        drawLabel(question['choices'][i],
                  198, y + 26.5,
                  size=15,
                  fill=INK,
                  align='left')

    if app.selectedAnswer != None:
        drawRect(90, 645, 640, 42,
                 fill=app.feedbackColor,
                 opacity=18,
                 border=app.feedbackColor,
                 borderWidth=1)

        drawWrappedText(app.feedback,
                        106, 658, 82,
                        lineHeight=15,
                        size=11,
                        fill=INK)

        drawButton(770, 642, 200, 38,
                   'CONTINUE',
                   DARK_PURPLE,
                   'white',
                   LAVENDER,
                   14)

    else:
        drawLabel('Choose the best answer to keep the coaster moving.',
                  90, 657,
                  size=14,
                  italic=True,
                  fill=rgb(70, 86, 122),
                  align='left')

    drawMiniCoaster(945, 107)

# ------------------------------------------------------------
# Full-screen graph evidence screen
# ------------------------------------------------------------

def drawGraphScreen(app):
    drawRect(0, 0, 1050, 700,
             fill=rgb(246, 248, 255))

    drawRect(0, 0, 1050, 88,
             fill=NAVY)

    drawLabel('RACE CART GRAPH: SPEED VS TIME',
              42, 42,
              size=24,
              bold=True,
              fill='white',
              align='left')

    drawLabel('On a speed-time graph, slope represents acceleration.',
              42, 67,
              size=14,
              fill=LAVENDER,
              align='left')

    drawButton(775, 22, 245, 56,
               'BACK TO QUESTION (G)',
               PURPLE,
               'white',
               LAVENDER,
               14)

    drawLabel('Evidence scanner',
              525, 122,
              size=20,
              bold=True,
              fill=INK)

    drawLabel('Find the interval with a horizontal line.',
              525, 148,
              size=15,
              fill=rgb(73, 84, 118))

    drawRect(70, 180, 680, 430,
             fill='white',
             border=rgb(165, 177, 216),
             borderWidth=2)

    left = 145
    bottom = 545
    graphWidth = 540
    graphHeight = 300

    for i in range(9):
        x = left + i * graphWidth / 8

        drawLine(x, bottom - graphHeight,
                 x, bottom,
                 fill=rgb(222, 228, 244))

        drawLabel(str(i),
                  x, bottom + 25,
                  size=13,
                  fill=INK)

    for i in range(7):
        y = bottom - i * graphHeight / 6

        drawLine(left, y,
                 left + graphWidth, y,
                 fill=rgb(222, 228, 244))

        drawLabel(str(i * 5),
                  left - 27, y,
                  size=12,
                  fill=INK)

    drawLine(left, bottom,
             left + graphWidth + 15, bottom,
             fill=INK,
             lineWidth=3)

    drawLine(left, bottom + 10,
             left, bottom - graphHeight - 15,
             fill=INK,
             lineWidth=3)

    drawPolygon(
        left + graphWidth + 18, bottom,
        left + graphWidth + 5, bottom - 7,
        left + graphWidth + 5, bottom + 7,
        fill=INK
    )

    drawPolygon(
        left, bottom - graphHeight - 18,
        left - 7, bottom - graphHeight - 5,
        left + 7, bottom - graphHeight - 5,
        fill=INK
    )

    drawLabel('Time in seconds',
              left + graphWidth / 2, 585,
              size=15,
              bold=True,
              fill=INK)

    drawLabel('Speed in m/s',
              101, 345,
              size=15,
              bold=True,
              fill=INK,
              rotateAngle=270)

    points = [
        (0, 0),
        (2, 15),
        (4, 15),
        (6, 5),
        (8, 20)
    ]

    screenPoints = []

    for point in points:
        timeValue = point[0]
        speedValue = point[1]

        x = left + timeValue * graphWidth / 8
        y = bottom - speedValue * graphHeight / 30

        screenPoints.append((x, y))

    colors = [
        ORANGE,
        GREEN,
        RED,
        CYAN
    ]

    labels = [
        '0 to 2 s',
        '2 to 4 s',
        '4 to 6 s',
        '6 to 8 s'
    ]

    for i in range(4):
        x1 = screenPoints[i][0]
        y1 = screenPoints[i][1]
        x2 = screenPoints[i + 1][0]
        y2 = screenPoints[i + 1][1]

        drawLine(x1, y1, x2, y2,
                 fill=colors[i],
                 lineWidth=7)

        drawLabel(labels[i],
                  (x1 + x2) / 2,
                  min(y1, y2) - 21,
                  size=13,
                  bold=True,
                  fill=colors[i])

    for point in screenPoints:
        drawCircle(point[0], point[1], 7,
                   fill='white',
                   border=INK,
                   borderWidth=2)

    drawRect(780, 180, 225, 430,
             fill=rgb(234, 240, 255),
             border=LAVENDER,
             borderWidth=2)

    drawLabel('GRAPH CLUES',
              892, 214,
              size=17,
              bold=True,
              fill=DARK_PURPLE)

    drawCircle(803, 275, 7, fill=ORANGE)

    drawWrappedText('Upward slope means positive acceleration.',
                    819, 268, 20,
                    lineHeight=18,
                    size=13,
                    fill=INK)

    drawCircle(803, 345, 7, fill=GREEN)

    drawWrappedText('Flat slope means zero acceleration.',
                    819, 338, 20,
                    lineHeight=18,
                    size=13,
                    fill=INK)

    drawCircle(803, 415, 7, fill=RED)

    drawWrappedText('Downward slope means negative acceleration.',
                    819, 408, 20,
                    lineHeight=18,
                    size=13,
                    fill=INK)

    drawRect(795, 495, 190, 74,
             fill='white',
             border=PURPLE,
             borderWidth=2)

    drawLabel('MISSION HINT',
              890, 516,
              size=13,
              bold=True,
              fill=PURPLE)

    drawWrappedText('Look for the segment with no rise and no fall.',
                    890, 538, 26,
                    lineHeight=16,
                    size=12,
                    fill=INK,
                    align='center')

    drawLabel('Click BACK TO QUESTION (G) when you are ready.',
              525, 654,
              size=15,
              bold=True,
              fill=DARK_PURPLE)

# ------------------------------------------------------------
# Projectile Lab
# ------------------------------------------------------------

def drawProjectileLab(app):
    drawSkyBackground(app)

    drawRect(0, 0, 1050, 86,
             fill=NAVY,
             opacity=96)

    drawButton(30, 22, 155, 45,
               'BACK TO HOME',
               PURPLE,
               'white',
               LAVENDER,
               13)

    drawLabel('PROJECTILE LAUNCH LAB',
              225, 35,
              size=24,
              bold=True,
              fill='white',
              align='left')

    drawLabel('The cannon, launch vector, predicted curve, and moving ball use one shared launch angle.',
              225, 61,
              size=13,
              fill=LAVENDER,
              align='left')

    drawLabControlPanel(app)
    drawFlightObservationZone(app)

def drawLabControlPanel(app):
    drawRect(45, 108, 320, 492,
             fill=rgb(247, 249, 255),
             border=LAVENDER,
             borderWidth=3)

    drawLabel('LAUNCH CONTROLS',
              205, 137,
              size=19,
              bold=True,
              fill=DARK_PURPLE)

    drawLine(76, 153, 334, 153,
             fill=LAVENDER,
             lineWidth=2)

    # Speed controls.
    drawLabel('INITIAL SPEED',
              205, 182,
              size=13,
              bold=True,
              fill=INK)

    drawLabel('Changes the size of the initial velocity.',
              205, 199,
              size=11,
              fill=rgb(83, 94, 126))

    drawButton(80, 218, 52, 44,
               '-',
               DARK_PURPLE,
               'white',
               LAVENDER,
               21)

    drawRect(141, 218, 128, 44,
             fill=rgb(231, 239, 255),
             border=PURPLE,
             borderWidth=2)

    drawLabel(str(app.launchSpeed) + ' m/s',
              205, 240,
              size=18,
              bold=True,
              fill=DARK_PURPLE)

    drawButton(278, 218, 52, 44,
               '+',
               DARK_PURPLE,
               'white',
               LAVENDER,
               21)

    # Angle controls.
    drawLabel('LAUNCH ANGLE',
              205, 285,
              size=13,
              bold=True,
              fill=INK)

    drawLabel('Controls the cannon direction and trajectory.',
              205, 302,
              size=11,
              fill=rgb(83, 94, 126))

    drawButton(80, 320, 52, 44,
               '-',
               DARK_PURPLE,
               'white',
               LAVENDER,
               21)

    drawRect(141, 320, 128, 44,
             fill=rgb(231, 239, 255),
             border=PURPLE,
             borderWidth=2)

    drawLabel(str(app.launchAngle) + ' degrees',
              205, 342,
              size=18,
              bold=True,
              fill=DARK_PURPLE)

    drawButton(278, 320, 52, 44,
               '+',
               DARK_PURPLE,
               'white',
               LAVENDER,
               21)

    drawButton(82, 405, 246, 55,
               'LAUNCH PROJECTILE',
               PURPLE,
               'white',
               LAVENDER,
               16)

    drawButton(82, 475, 246, 44,
               'RESET FLIGHT',
               rgb(70, 83, 130),
               'white',
               LAVENDER,
               14)

    drawRect(70, 535, 270, 46,
             fill=rgb(245, 255, 246),
             border=GREEN,
             borderWidth=2)

    drawLabel('SPACE launches. R resets. ESC returns home.',
              205, 558,
              size=11,
              bold=True,
              fill=GREEN)

def drawFlightObservationZone(app):
    drawRect(app.labLeft, app.labTop,
             app.labWidth, app.labHeight,
             fill=LIGHT_BLUE,
             border=CYAN,
             borderWidth=3)

    drawLabel('FLIGHT OBSERVATION ZONE',
              698, 137,
              size=18,
              bold=True,
              fill=DARK_PURPLE)

    drawLabel('The orange ball is the real launched projectile.',
              698, 160,
              size=12,
              fill=rgb(73, 85, 120))

    drawRect(app.labLeft + 3, 170,
             app.labWidth - 6, 95,
             fill=rgb(211, 239, 255),
             opacity=70)

    drawRect(app.labLeft + 3, 265,
             app.labWidth - 6, 100,
             fill=rgb(201, 234, 255),
             opacity=70)

    for x in range(430, 1000, 70):
        drawLine(x, 185, x, 570,
                 fill=rgb(180, 220, 240),
                 lineWidth=1,
                 dashes=True,
                 opacity=60)

    for y in range(205, 575, 55):
        drawLine(405, y, 990, y,
                 fill=rgb(180, 220, 240),
                 lineWidth=1,
                 dashes=True,
                 opacity=60)

    drawRect(app.labLeft + 3, app.groundY,
             app.labWidth - 6, 12,
             fill=rgb(48, 121, 74))

    drawCannon(app)
    drawInitialVelocityVector(app)
    drawNoGravityReference(app)
    drawPredictedTrajectory(app)
    drawProjectileTrail(app)
    drawGravityArrow(app)
    drawFlightStatus(app)

    # Draw last so the real ball always appears above all paths and scenery.
    drawLaunchedProjectile(app)

def drawCannon(app):
    angleRadians = math.radians(app.launchAngle)

    # The exact barrel end is the same point used as the launch point.
    barrelEndX = app.muzzleX
    barrelEndY = app.muzzleY

    # Wheel/base platform.
    drawRect(434, 532, 136, 53,
             fill=rgb(73, 84, 115),
             border=INK,
             borderWidth=2)

    drawCircle(462, 586, 12,
               fill=INK,
               border='white',
               borderWidth=1)

    drawCircle(542, 586, 12,
               fill=INK,
               border='white',
               borderWidth=1)

    drawCircle(462, 586, 4, fill=CYAN)
    drawCircle(542, 586, 4, fill=CYAN)

    # Cannon support.
    drawRegularPolygon(app.cannonPivotX,
                       app.cannonPivotY + 9,
                       38, 3,
                       fill=rgb(83, 66, 133),
                       border=DARK_PURPLE,
                       borderWidth=2,
                       rotateAngle=180)

    # CANNON BARREL:
    # Uses the same pivot and muzzle coordinates that drive the physics.
    drawLine(app.cannonPivotX, app.cannonPivotY,
             barrelEndX, barrelEndY,
             fill=DARK_GRAY,
             lineWidth=18)

    drawLine(app.cannonPivotX, app.cannonPivotY,
             barrelEndX, barrelEndY,
             fill=GOLD,
             lineWidth=10)

    # Barrel rim at the muzzle.
    drawCircle(barrelEndX, barrelEndY,
               11,
               fill=DARK_GRAY,
               border=GOLD,
               borderWidth=3)

    # Pivot.
    drawCircle(app.cannonPivotX, app.cannonPivotY,
               14,
               fill=ORANGE,
               border=DARK_PURPLE,
               borderWidth=2)

    drawLabel('ANGLE LOCKED',
              502, 568,
              size=10,
              bold=True,
              fill='white')

def drawInitialVelocityVector(app):
    angleRadians = math.radians(app.launchAngle)

    vectorLength = 75

    vectorEndX = (
        app.muzzleX
        + vectorLength * math.cos(angleRadians)
    )

    vectorEndY = (
        app.muzzleY
        - vectorLength * math.sin(angleRadians)
    )

    # Initial velocity vector has the exact same angle as the barrel
    # and the initial tangent of the projectile curve.
    drawLine(app.muzzleX, app.muzzleY,
             vectorEndX, vectorEndY,
             fill=ORANGE,
             lineWidth=4,
             arrowEnd=True)

    labelX = (
        app.muzzleX
        + (vectorLength + 26) * math.cos(angleRadians)
    )

    labelY = (
        app.muzzleY
        - (vectorLength + 26) * math.sin(angleRadians)
    )

    drawLabel('initial velocity',
              labelX,
              labelY,
              size=11,
              bold=True,
              fill=ORANGE)

def drawNoGravityReference(app):
    angleRadians = math.radians(app.launchAngle)

    referenceLength = 270

    referenceEndX = (
        app.muzzleX
        + referenceLength * math.cos(angleRadians)
    )

    referenceEndY = (
        app.muzzleY
        - referenceLength * math.sin(angleRadians)
    )

    # This straight dotted line follows the same initial angle.
    # It represents where the ball would go if gravity were absent.
    drawLine(app.muzzleX, app.muzzleY,
             referenceEndX, referenceEndY,
             fill=rgb(108, 126, 164),
             lineWidth=2,
             dashes=True)

    drawLabel('No gravity reference',
              referenceEndX + 20,
              referenceEndY - 4,
              size=11,
              fill=rgb(77, 91, 128))

def drawPredictedTrajectory(app):
    previousX = app.muzzleX
    previousY = app.muzzleY

    # Uses getProjectilePosition, exactly the same equation
    # as the animated, real launched projectile.
    for step in range(1, 220):
        timeValue = step * 0.016
        x, y = getProjectilePosition(app, timeValue)

        if x > app.labLeft + app.labWidth - 8:
            break

        if y > app.groundY - 8:
            break

        drawLine(previousX, previousY,
                 x, y,
                 fill=PURPLE,
                 lineWidth=2,
                 dashes=True,
                 opacity=60)

        previousX = x
        previousY = y

    drawLabel('Predicted trajectory',
              770, 255,
              size=11,
              fill=PURPLE)

def drawProjectileTrail(app):
    if len(app.projectileTrail) < 2:
        return

    for i in range(len(app.projectileTrail) - 1):
        x1 = app.projectileTrail[i][0]
        y1 = app.projectileTrail[i][1]
        x2 = app.projectileTrail[i + 1][0]
        y2 = app.projectileTrail[i + 1][1]

        drawLine(x1, y1, x2, y2,
                 fill=ORANGE,
                 lineWidth=3,
                 opacity=55)

def drawGravityArrow(app):
    drawLine(940, 245, 940, 365,
             fill=RED,
             lineWidth=5,
             arrowEnd=True)

    drawLabel('gravity',
              940, 222,
              size=14,
              bold=True,
              fill=RED)

    drawLabel('vertical acceleration',
              940, 385,
              size=11,
              fill=RED)

def drawLaunchedProjectile(app):
    if app.projectileRunning == False and app.projectileLanded == False:
        projectileX = app.muzzleX
        projectileY = app.muzzleY
    else:
        projectileX = app.projectileX
        projectileY = app.projectileY

    drawCircle(projectileX, projectileY,
               20,
               fill=None,
               border=GOLD,
               borderWidth=3,
               opacity=65)

    drawCircle(projectileX, projectileY,
               12,
               fill=ORANGE,
               border=DARK_PURPLE,
               borderWidth=2)

    drawCircle(projectileX - 4, projectileY - 4,
               3,
               fill='white',
               opacity=85)

    if app.projectileRunning:
        drawLabel('PROJECTILE',
                  projectileX,
                  projectileY - 26,
                  size=10,
                  bold=True,
                  fill=DARK_PURPLE)

def drawFlightStatus(app):
    drawRect(742, 526, 242, 45,
             fill='white',
             border=PURPLE,
             borderWidth=2,
             opacity=94)

    if app.projectileRunning:
        statusText = 'Flight active: trajectory in progress'
        statusColor = GREEN

    elif app.projectileLanded:
        statusText = 'Flight complete: reset or launch again'
        statusColor = ORANGE

    else:
        statusText = 'Ready: barrel and trajectory aligned'
        statusColor = DARK_PURPLE

    drawCircle(760, 548, 7, fill=statusColor)

    drawLabel(statusText,
              872, 548,
              size=11,
              bold=True,
              fill=INK)

    drawLabel('Initial speed: ' + str(app.launchSpeed) + ' m/s',
              680, 624,
              size=14,
              bold=True,
              fill=DARK_PURPLE)

    drawLabel('Launch angle: ' + str(app.launchAngle) + ' degrees',
              680, 648,
              size=14,
              bold=True,
              fill=DARK_PURPLE)

# ------------------------------------------------------------
# Finish screen
# ------------------------------------------------------------

def drawFinishScreen(app):
    drawSkyBackground(app)

    drawRect(160, 104, 730, 480,
             fill=NAVY,
             opacity=92,
             border=LAVENDER,
             borderWidth=3)

    for star in app.stars:
        x = star[0]
        y = star[1]
        angle = star[2]

        radius = 4 + 2 * math.sin(math.radians(app.time * 5 + angle))

        drawStar(x, y, radius, 4,
                 fill=GOLD,
                 opacity=72)

    drawLabel('MISSION COMPLETE!',
              525, 180,
              size=39,
              bold=True,
              fill='white')

    drawLabel('You stabilized the Speedstorm Coaster and saved the science fair.',
              525, 225,
              size=17,
              fill=LAVENDER)

    drawRollerCoaster(app, 270, 420, 0.62)
    drawProjectileCelebration(775, 405)

    drawRect(350, 285, 350, 165,
             fill=rgb(49, 59, 104),
             border=CYAN,
             borderWidth=2)

    drawLabel('FINAL SCORE',
              525, 320,
              size=15,
              bold=True,
              fill=LAVENDER)

    drawLabel(str(app.score),
              525, 370,
              size=50,
              bold=True,
              fill=GOLD)

    drawLabel('Acceleration expert unlocked',
              525, 416,
              size=15,
              fill='white')

    drawLabel('Acceleration means a change in speed, direction, or both.',
              525, 498,
              size=15,
              bold=True,
              fill='white')

    drawButton(365, 540, 320, 70,
               'PLAY AGAIN',
               PURPLE,
               'white',
               LAVENDER,
               19)

    drawLabel('Press R to restart from any mission screen.',
              525, 650,
              size=13,
              fill='white')

# ------------------------------------------------------------
# Decorative objects
# ------------------------------------------------------------

def drawRollerCoaster(app, centerX, centerY, scale):
    for xOffset in [-165, -65, 40, 150]:
        x = centerX + xOffset * scale

        drawLine(x, centerY + 110 * scale,
                 x, centerY + 205 * scale,
                 fill=rgb(70, 74, 95),
                 lineWidth=max(2, int(5 * scale)))

    drawArc(centerX - 85 * scale,
            centerY + 46 * scale,
            240 * scale,
            180 * scale,
            180, 180,
            fill=None,
            border=rgb(75, 64, 105),
            borderWidth=max(2, int(10 * scale)))

    drawArc(centerX + 95 * scale,
            centerY + 10 * scale,
            215 * scale,
            215 * scale,
            180, 180,
            fill=None,
            border=rgb(75, 64, 105),
            borderWidth=max(2, int(10 * scale)))

    drawLine(centerX - 205 * scale,
             centerY + 134 * scale,
             centerX - 85 * scale,
             centerY + 45 * scale,
             fill=rgb(75, 64, 105),
             lineWidth=max(2, int(10 * scale)))

    drawLine(centerX + 202 * scale,
             centerY + 118 * scale,
             centerX + 300 * scale,
             centerY + 172 * scale,
             fill=rgb(75, 64, 105),
             lineWidth=max(2, int(10 * scale)))

    cartX = centerX + math.sin(app.time / 18) * 115 * scale
    cartY = centerY + 72 * scale + math.cos(app.time / 18) * 22 * scale

    drawRect(cartX - 28 * scale,
             cartY - 14 * scale,
             56 * scale,
             24 * scale,
             fill=ORANGE,
             border=DARK_PURPLE,
             borderWidth=max(1, int(2 * scale)))

    drawCircle(cartX - 17 * scale,
               cartY + 15 * scale,
               7 * scale,
               fill=INK)

    drawCircle(cartX + 17 * scale,
               cartY + 15 * scale,
               7 * scale,
               fill=INK)

    drawLabel('SPEEDSTORM',
              centerX,
              centerY + 237 * scale,
              size=max(10, int(16 * scale)),
              bold=True,
              fill='white')

def drawMiniCoaster(x, y):
    drawArc(x, y + 12,
            70, 52,
            180, 180,
            fill=None,
            border=PURPLE,
            borderWidth=5)

    drawRect(x - 10, y + 5,
             20, 12,
             fill=ORANGE,
             border=DARK_PURPLE,
             borderWidth=1)

def drawProjectileCelebration(x, y):
    drawLine(x - 110, y + 55,
             x + 110, y + 55,
             fill=GREEN,
             lineWidth=7)

    for i in range(5):
        angle = 35 + i * 18
        radians = math.radians(angle)

        projectileX = x - 85 + math.cos(radians) * 150
        projectileY = y + 50 - math.sin(radians) * 105

        drawCircle(projectileX, projectileY,
                   8,
                   fill=ORANGE,
                   border=DARK_PURPLE,
                   borderWidth=1)

    drawLine(x - 85, y + 45,
             x + 95, y - 65,
             fill=PURPLE,
             lineWidth=4,
             dashes=True)

    drawLabel('PROJECTILE',
              x, y + 92,
              size=14,
              bold=True,
              fill='white')

# ------------------------------------------------------------
# Run app
# ------------------------------------------------------------

def main():
    runApp(width=1050, height=700)

main()