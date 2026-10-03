from scs import *
import math
import random

# ------------------------------------------------------------
# MOMENTUM MAYHEM: Storm Chaser
# CMU CS Academy CPCS Mode
# 1050 x 700
# ------------------------------------------------------------

PURPLE = rgb(130, 70, 215)
DARK_PURPLE = rgb(71, 35, 122)
LAVENDER = rgb(220, 195, 255)
INK = rgb(25, 30, 50)
PANEL = rgb(245, 247, 255)
CYAN = rgb(70, 225, 245)
GOLD = rgb(255, 205, 70)
GREEN = rgb(75, 205, 125)
RED = rgb(245, 92, 105)
ORANGE = rgb(255, 143, 71)
SKY = rgb(74, 130, 211)

# ------------------------------------------------------------
# App setup
# ------------------------------------------------------------

def onAppStart(app):
    app.stepsPerSecond = 30
    resetGame(app)

def resetGame(app):
    app.screen = 'home'
    app.questionIndex = 0
    app.score = 0
    app.streak = 0
    app.feedback = ''
    app.feedbackColor = INK
    app.selectedAnswer = None
    app.graphReturnQuestion = 0
    app.time = 0

    app.rain = []
    app.sparkles = []
    app.clouds = [
        [130, 105, 1.0],
        [430, 150, 0.8],
        [800, 95, 1.2],
        [990, 175, 0.7]
    ]

    random.seed(8)

    for i in range(90):
        app.rain.append([
            random.randint(0, 1050),
            random.randint(0, 700),
            random.randint(7, 18)
        ])

    for i in range(24):
        app.sparkles.append([
            random.randint(20, 1030),
            random.randint(25, 675),
            random.randint(0, 359)
        ])

    app.questions = [
        {
            'title': 'Checkpoint 1: Hurricane Intel',
            'category': 'VELOCITY',
            'prompt': (
                'A hurricane is 500 km east of town and moves at 20 km/h. '
                'Which extra detail is needed to know whether it is heading '
                'toward town?'
            ),
            'choices': [
                'The hurricane direction of motion',
                'The hurricane cloud color',
                'The town population',
                'The hurricane age'
            ],
            'correct': 0,
            'explanation': (
                'Correct! Speed says how fast the storm moves. Velocity '
                'requires both speed and direction.'
            ),
            'graph': False
        },
        {
            'title': 'Checkpoint 2: Curveball Circuit',
            'category': 'SPEED VS VELOCITY',
            'prompt': (
                'A race car travels around a curved track at a constant '
                'speed of 30 m/s. What happens to its velocity?'
            ),
            'choices': [
                'It stays constant because speed stays constant',
                'It changes because the car changes direction',
                'It becomes zero at every turn',
                'It doubles at every turn'
            ],
            'correct': 1,
            'explanation': (
                'Correct! Velocity includes direction. Turning changes '
                'direction, so velocity changes even at constant speed.'
            ),
            'graph': False
        },
        {
            'title': 'Checkpoint 3: Motion Scanner',
            'category': 'GRAPH EVIDENCE',
            'prompt': (
                'Use the position-time graph. During which interval is the '
                'rover moving with the greatest positive velocity?'
            ),
            'choices': [
                '0 to 2 seconds',
                '2 to 4 seconds',
                '4 to 6 seconds',
                '6 to 8 seconds'
            ],
            'correct': 2,
            'explanation': (
                'Correct! On a position-time graph, velocity is represented '
                'by slope. The 4 to 6 second segment has the steepest '
                'upward slope.'
            ),
            'graph': True
        },
        {
            'title': 'Checkpoint 4: Reference Point Remix',
            'category': 'RELATIVE MOTION',
            'prompt': (
                'A car moves west at 10 km/h. A hurricane moves west at '
                '20 km/h. From the car frame of reference, how does the '
                'hurricane appear to move?'
            ),
            'choices': [
                'Toward the car at 10 km/h',
                'Away from the car at 30 km/h',
                'It is motionless',
                'Toward the car at 20 km/h'
            ],
            'correct': 0,
            'explanation': (
                'Correct! Both move west, but the hurricane moves west '
                '10 km/h faster than the car. It approaches the car at '
                '10 km/h.'
            ),
            'graph': False
        },
        {
            'title': 'Checkpoint 5: Momentum Launch',
            'category': 'MOMENTUM',
            'prompt': (
                'An 80 kg sprinter runs east at 10 m/s. What is the '
                'sprinter momentum?'
            ),
            'choices': [
                '8 kg m/s east',
                '70 kg m/s east',
                '800 kg m/s east',
                '800 kg m/s west'
            ],
            'correct': 2,
            'explanation': (
                'Correct! Momentum is p = mv. So p = 80 kg times 10 m/s, '
                'which is 800 kg m/s east.'
            ),
            'graph': False
        },
        {
            'title': 'Final Boss: Cargo Clash',
            'category': 'COMPARE MOMENTUM',
            'prompt': (
                'A car and a delivery truck travel west at the same '
                'velocity. The truck has more mass. Which statement is true?'
            ),
            'choices': [
                'The car has more momentum because it is smaller',
                'They have equal momentum because velocity matches',
                'The truck has more momentum because its mass is greater',
                'Neither object has momentum while moving west'
            ],
            'correct': 2,
            'explanation': (
                'Correct! Since p = mv, objects with the same velocity have '
                'more momentum when they have more mass.'
            ),
            'graph': False
        }
    ]

# ------------------------------------------------------------
# Animation
# ------------------------------------------------------------

def onStep(app):
    app.time += 1

    for drop in app.rain:
        drop[1] += drop[2]
        drop[0] -= 2

        if drop[1] > 700 or drop[0] < -10:
            drop[0] = random.randint(0, 1050)
            drop[1] = random.randint(-200, 0)

    for cloud in app.clouds:
        cloud[0] -= cloud[2]

        if cloud[0] < -180:
            cloud[0] = 1200

# ------------------------------------------------------------
# Input events
# ------------------------------------------------------------

def onMousePress(app, mouseX, mouseY):
    if app.screen == 'home':
        if pointInRect(mouseX, mouseY, 380, 545, 290, 78):
            app.screen = 'question'
            app.questionIndex = 0
            app.score = 0
            app.streak = 0
            app.feedback = ''
            app.selectedAnswer = None

    elif app.screen == 'question':
        handleQuestionClick(app, mouseX, mouseY)

    elif app.screen == 'graph':
        if pointInRect(mouseX, mouseY, 785, 24, 235, 54):
            app.screen = 'question'

    elif app.screen == 'finish':
        if pointInRect(mouseX, mouseY, 365, 545, 320, 70):
            resetGame(app)

def onKeyPress(app, key):
    if app.screen == 'graph':
        if key.lower() == 'g':
            app.screen = 'question'

    elif app.screen == 'question':
        currentQuestion = app.questions[app.questionIndex]

        if key.lower() == 'g' and currentQuestion['graph']:
            app.graphReturnQuestion = app.questionIndex
            app.screen = 'graph'

        elif key.lower() == 'r':
            resetGame(app)

    elif app.screen == 'finish':
        if key.lower() == 'r':
            resetGame(app)

def handleQuestionClick(app, mouseX, mouseY):
    question = app.questions[app.questionIndex]

    # Graph workflow button.
    if question['graph']:
        if pointInRect(mouseX, mouseY, 770, 129, 220, 52):
            app.graphReturnQuestion = app.questionIndex
            app.screen = 'graph'
            return

    # Answer choices.
    for i in range(4):
        y = 365 + i * 70

        if pointInRect(mouseX, mouseY, 130, y, 790, 54):
            chooseAnswer(app, i)
            return

    # Continue button.
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
# Main redraw function
# ------------------------------------------------------------

def redrawAll(app):
    if app.screen == 'home':
        drawHomeScreen(app)

    elif app.screen == 'question':
        drawQuestionScreen(app)

    elif app.screen == 'graph':
        drawGraphScreen(app)

    elif app.screen == 'finish':
        drawFinishScreen(app)

# ------------------------------------------------------------
# General helper functions
# ------------------------------------------------------------

def pointInRect(x, y, left, top, width, height):
    return (left <= x <= left + width and
            top <= y <= top + height)

def drawButton(x, y, width, height, text, fillColor,
               textColor, borderColor, size):
    drawRect(x, y, width, height,
             fill=fillColor,
             border=borderColor,
             borderWidth=2)

    drawLabel(text, x + width / 2, y + height / 2,
              size=size,
              bold=True,
              fill=textColor)

def drawWrappedText(text, x, y, maxChars,
                    lineHeight=22, size=16,
                    fill=INK, bold=False, align='left'):
    words = text.split(' ')
    line = ''
    lines = []

    for word in words:
        if line == '':
            testLine = word
        else:
            testLine = line + ' ' + word

        if len(testLine) <= maxChars:
            line = testLine
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
# Background and shared graphics
# ------------------------------------------------------------

def drawStormBackground(app):
    drawRect(0, 0, 1050, 700, fill=SKY)

    drawRect(0, 0, 1050, 250,
             fill=gradient(rgb(50, 72, 130),
                           rgb(97, 125, 188),
                           start='top'))

    drawRect(0, 250, 1050, 450,
             fill=gradient(rgb(65, 108, 161),
                           rgb(132, 183, 203),
                           start='top'))

    for cloud in app.clouds:
        drawCloud(cloud[0], cloud[1], cloud[2])

    for drop in app.rain:
        drawLine(drop[0], drop[1],
                 drop[0] - 5, drop[1] + drop[2],
                 fill=rgb(190, 225, 255),
                 opacity=38,
                 lineWidth=2)

    drawPolygon(
        0, 540,
        130, 450,
        250, 535,
        400, 430,
        565, 540,
        720, 410,
        880, 535,
        1050, 445,
        1050, 700,
        0, 700,
        fill=rgb(34, 86, 87)
    )

    drawRect(0, 590, 1050, 110, fill=rgb(26, 65, 66))

    drawPolygon(
        0, 660,
        1050, 535,
        1050, 700,
        0, 700,
        fill=rgb(45, 48, 58)
    )

    for x in range(-30, 1120, 120):
        drawPolygon(
            x, 676,
            x + 70, 667,
            x + 70, 676,
            x, 685,
            fill=GOLD,
            opacity=80
        )

def drawCloud(x, y, scale):
    cloudColor = rgb(65, 79, 118)

    drawOval(x, y,
             95 * scale, 45 * scale,
             fill=cloudColor)

    drawOval(x + 35 * scale, y - 17 * scale,
             85 * scale, 65 * scale,
             fill=cloudColor)

    drawOval(x + 85 * scale, y,
             120 * scale, 52 * scale,
             fill=cloudColor)

    drawOval(x + 140 * scale, y - 10 * scale,
             75 * scale, 52 * scale,
             fill=cloudColor)

def drawTopBar(app, label):
    drawRect(0, 0, 1050, 76,
             fill=rgb(23, 27, 52),
             opacity=92)

    drawLabel('MOMENTUM MAYHEM',
              35, 29,
              size=23,
              bold=True,
              fill='white',
              align='left')

    drawLabel(label,
              36, 55,
              size=12,
              bold=True,
              fill=LAVENDER,
              align='left')

    drawRect(760, 15, 120, 46,
             fill=rgb(43, 49, 83),
             border=LAVENDER,
             borderWidth=1,
             opacity=95)

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
             fill=rgb(43, 49, 83),
             border=LAVENDER,
             borderWidth=1,
             opacity=95)

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
    drawStormBackground(app)

    drawHurricane(825, 270, 1.35, app.time)

    drawRect(70, 135, 590, 355,
             fill=rgb(16, 22, 46),
             opacity=87,
             border=LAVENDER,
             borderWidth=2)

    drawLabel('MOMENTUM',
              110, 205,
              size=48,
              bold=True,
              fill='white',
              align='left')

    drawLabel('MAYHEM',
              110, 258,
              size=48,
              bold=True,
              fill=CYAN,
              align='left')

    drawLabel('Storm Chaser Physics Quest',
              113, 305,
              size=21,
              bold=True,
              fill=LAVENDER,
              align='left')

    drawWrappedText(
        'Pilot your science rover through six fast checkpoints. Decode '
        'velocity, reference frames, motion graphs, and momentum before '
        'the storm reaches the town!',
        113, 350, 51,
        lineHeight=24,
        size=16,
        fill='white'
    )

    drawLabel('Mission tools:',
              113, 432,
              size=14,
              bold=True,
              fill=GOLD,
              align='left')

    drawLabel('Direction radar',
              235, 432,
              size=14,
              fill='white',
              align='left')

    drawLabel('Graph scanner',
              400, 432,
              size=14,
              fill='white',
              align='left')

    drawLabel('p = mv engine',
              535, 432,
              size=14,
              fill='white',
              align='left')

    drawButton(380, 545, 290, 78,
               'START THE MISSION',
               PURPLE,
               'white',
               LAVENDER,
               20)

    drawLabel('Click choices to answer. Graph checkpoints include a full-screen graph viewer.',
              525, 662,
              size=13,
              fill='white')

    drawRover(850, 587, 1.05, 'east')

# ------------------------------------------------------------
# Question screen
# ------------------------------------------------------------

def drawQuestionScreen(app):
    drawStormBackground(app)

    question = app.questions[app.questionIndex]

    drawTopBar(app, 'SCIENCE MISSION')

    drawLabel('CHECKPOINT ' + str(app.questionIndex + 1) +
              ' / ' + str(len(app.questions)),
              47, 103,
              size=16,
              bold=True,
              fill='white',
              align='left')

    # Progress bar outline.
    drawRect(47, 116, 530, 13,
             fill=rgb(31, 43, 78),
             border='white',
             borderWidth=1)

    # FIX:
    # CPCS requires positive rectangle widths.
    # At checkpoint 1, completedWidth is 0, so do not draw a fill bar.
    completedWidth = 530 * app.questionIndex / len(app.questions)

    if completedWidth > 0:
        drawRect(47, 116, completedWidth, 13, fill=CYAN)

    for i in range(len(app.questions)):
        x = 47 + (i + 0.5) * 530 / len(app.questions)

        if i < app.questionIndex:
            circleColor = GOLD
        elif i == app.questionIndex:
            circleColor = CYAN
        else:
            circleColor = LAVENDER

        drawCircle(x, 122.5, 8,
                   fill=circleColor,
                   border='white',
                   borderWidth=1)

    drawRect(60, 148, 930, 500,
             fill=PANEL,
             border=LAVENDER,
             borderWidth=3,
             opacity=97)

    drawRect(90, 175, 260, 35, fill=DARK_PURPLE)

    drawLabel(question['category'],
              220, 192,
              size=14,
              bold=True,
              fill='white')

    drawLabel(question['title'],
              90, 238,
              size=24,
              bold=True,
              fill=INK,
              align='left')

    # Required purple graph button.
    if question['graph']:
        drawButton(770, 129, 220, 52,
                   'VIEW GRAPH',
                   PURPLE,
                   'white',
                   LAVENDER,
                   16)

        drawLabel('Open evidence view',
                  880, 190,
                  size=11,
                  fill='white')

    drawWrappedText(question['prompt'],
                    92, 280, 90,
                    lineHeight=23,
                    size=17,
                    fill=INK)

    choiceLetters = ['A', 'B', 'C', 'D']

    for i in range(4):
        y = 365 + i * 70

        choiceFill = 'white'
        choiceBorder = rgb(177, 186, 217)
        letterFill = DARK_PURPLE

        if app.selectedAnswer != None:
            if i == question['correct']:
                choiceFill = rgb(214, 250, 224)
                choiceBorder = GREEN
                letterFill = GREEN

            elif i == app.selectedAnswer:
                choiceFill = rgb(255, 224, 228)
                choiceBorder = RED
                letterFill = RED

        drawRect(130, y, 790, 54,
                 fill=choiceFill,
                 border=choiceBorder,
                 borderWidth=2)

        drawCircle(163, y + 27, 17, fill=letterFill)

        drawLabel(choiceLetters[i],
                  163, y + 27,
                  size=15,
                  bold=True,
                  fill='white')

        drawLabel(question['choices'][i],
                  198, y + 27,
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
        drawLabel('Choose the best answer to charge the rover.',
                  90, 657,
                  size=14,
                  italic=True,
                  fill=rgb(73, 85, 120),
                  align='left')

    drawRover(965, 106, 0.48, 'west')

# ------------------------------------------------------------
# Full-screen graph screen
# ------------------------------------------------------------

def drawGraphScreen(app):
    drawRect(0, 0, 1050, 700, fill=rgb(246, 248, 255))

    drawRect(0, 0, 1050, 88, fill=rgb(26, 31, 61))

    drawLabel('ROVER MOTION GRAPH: POSITION VS TIME',
              42, 43,
              size=24,
              bold=True,
              fill='white',
              align='left')

    drawLabel('Use slope to compare velocity.',
              43, 68,
              size=14,
              fill=LAVENDER,
              align='left')

    # Required top-right graph toggle.
    drawButton(785, 24, 235, 54,
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

    drawLabel('A steeper upward line means a greater positive velocity.',
              525, 148,
              size=15,
              fill=rgb(73, 84, 118))

    drawRect(75, 180, 670, 430,
             fill='white',
             border=rgb(165, 177, 216),
             borderWidth=2)

    left = 145
    bottom = 545
    graphWidth = 535
    graphHeight = 300

    # Vertical gridlines and time labels.
    for i in range(9):
        x = left + i * graphWidth / 8

        drawLine(x, bottom - graphHeight,
                 x, bottom,
                 fill=rgb(222, 228, 244))

        drawLabel(str(i),
                  x, bottom + 25,
                  size=13,
                  fill=INK)

    # Horizontal gridlines and position labels.
    for i in range(7):
        y = bottom - i * graphHeight / 6

        drawLine(left, y,
                 left + graphWidth, y,
                 fill=rgb(222, 228, 244))

        drawLabel(str(i * 10),
                  left - 25, y,
                  size=12,
                  fill=INK)

    # Axes.
    drawLine(left, bottom,
             left + graphWidth + 15, bottom,
             fill=INK,
             lineWidth=3)

    drawLine(left, bottom + 10,
             left, bottom - graphHeight - 15,
             fill=INK,
             lineWidth=3)

    # Arrowheads.
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

    drawLabel('Position in meters',
              103, 345,
              size=15,
              bold=True,
              fill=INK,
              rotateAngle=270)

    # Position-time data.
    points = [
        (0, 0),
        (2, 10),
        (4, 10),
        (6, 50),
        (8, 60)
    ]

    screenPoints = []

    for point in points:
        timeValue = point[0]
        positionValue = point[1]

        x = left + timeValue * graphWidth / 8
        y = bottom - positionValue * graphHeight / 60

        screenPoints.append((x, y))

    segmentColors = [
        ORANGE,
        rgb(115, 125, 160),
        GREEN,
        CYAN
    ]

    intervalLabels = [
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
                 fill=segmentColors[i],
                 lineWidth=7)

        drawLabel(intervalLabels[i],
                  (x1 + x2) / 2,
                  min(y1, y2) - 21,
                  size=13,
                  bold=True,
                  fill=segmentColors[i])

    for point in screenPoints:
        drawCircle(point[0], point[1], 7,
                   fill='white',
                   border=INK,
                   borderWidth=2)

    # Explanation panel.
    drawRect(775, 180, 230, 430,
             fill=rgb(233, 239, 255),
             border=LAVENDER,
             borderWidth=2)

    drawLabel('READ THE GRAPH',
              890, 214,
              size=17,
              bold=True,
              fill=DARK_PURPLE)

    drawWrappedText('On a position-time graph:',
                    795, 254, 26,
                    lineHeight=20,
                    size=14,
                    fill=INK,
                    bold=True)

    drawCircle(802, 307, 7, fill=GREEN)

    drawWrappedText('Upward slope means positive velocity',
                    818, 300, 21,
                    lineHeight=18,
                    size=13,
                    fill=INK)

    drawCircle(802, 365, 7, fill=rgb(115, 125, 160))

    drawWrappedText('A flat line means zero velocity',
                    818, 358, 21,
                    lineHeight=18,
                    size=13,
                    fill=INK)

    drawCircle(802, 423, 7, fill=ORANGE)

    drawWrappedText('A steeper slope means greater speed',
                    818, 416, 21,
                    lineHeight=18,
                    size=13,
                    fill=INK)

    drawRect(795, 490, 190, 75,
             fill='white',
             border=PURPLE,
             borderWidth=2)

    drawLabel('MISSION HINT',
              890, 510,
              size=13,
              bold=True,
              fill=PURPLE)

    drawWrappedText('Compare the slopes, not just final positions.',
                    890, 532, 26,
                    lineHeight=16,
                    size=12,
                    fill=INK,
                    align='center')

    drawLabel('Click BACK TO QUESTION (G) when you are ready to answer.',
              525, 654,
              size=15,
              bold=True,
              fill=DARK_PURPLE)

# ------------------------------------------------------------
# Finish screen
# ------------------------------------------------------------

def drawFinishScreen(app):
    drawStormBackground(app)

    drawRect(160, 104, 730, 480,
             fill=rgb(20, 25, 50),
             opacity=91,
             border=LAVENDER,
             borderWidth=3)

    for sparkle in app.sparkles:
        x = sparkle[0]
        y = sparkle[1]
        angle = sparkle[2]

        radius = 4 + 2 * math.sin(math.radians(app.time * 5 + angle))

        drawStar(x, y, radius, 4,
                 fill=GOLD,
                 opacity=65)

    drawLabel('MISSION COMPLETE!',
              525, 180,
              size=39,
              bold=True,
              fill='white')

    drawLabel('The town is safe. Your physics instincts are online.',
              525, 225,
              size=18,
              fill=LAVENDER)

    drawHurricane(250, 380, 0.72, app.time)
    drawRover(785, 438, 1.15, 'east')

    drawRect(350, 285, 350, 165,
             fill=rgb(46, 54, 97),
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

    drawLabel('Momentum mastery unlocked',
              525, 416,
              size=15,
              fill='white')

    drawLabel('Key takeaway: velocity has speed and direction. Momentum is p = mv.',
              525, 498,
              size=15,
              bold=True,
              fill='white')

    drawButton(365, 545, 320, 70,
               'PLAY AGAIN',
               PURPLE,
               'white',
               LAVENDER,
               19)

    drawLabel('Press R at any time to restart.',
              525, 650,
              size=13,
              fill='white')

# ------------------------------------------------------------
# Rover drawing
# ------------------------------------------------------------

def drawRover(x, y, scale, direction):
    directionMultiplier = 1

    if direction == 'west':
        directionMultiplier = -1

    drawOval(x, y + 30 * scale,
             175 * scale, 28 * scale,
             fill='black',
             opacity=28)

    drawCircle(x - 47 * scale, y + 20 * scale,
               18 * scale,
               fill=rgb(18, 22, 31),
               border='white',
               borderWidth=1)

    drawCircle(x + 47 * scale, y + 20 * scale,
               18 * scale,
               fill=rgb(18, 22, 31),
               border='white',
               borderWidth=1)

    drawCircle(x - 47 * scale, y + 20 * scale,
               7 * scale,
               fill=CYAN)

    drawCircle(x + 47 * scale, y + 20 * scale,
               7 * scale,
               fill=CYAN)

    drawRect(x - 72 * scale, y - 21 * scale,
             144 * scale, 40 * scale,
             fill=rgb(55, 72, 120),
             border=CYAN,
             borderWidth=2)

    drawPolygon(
        x - 43 * scale, y - 21 * scale,
        x - 18 * scale, y - 53 * scale,
        x + 35 * scale, y - 53 * scale,
        x + 58 * scale, y - 21 * scale,
        fill=rgb(91, 124, 180),
        border=CYAN
    )

    drawRect(x - 10 * scale, y - 46 * scale,
             24 * scale, 17 * scale,
             fill=rgb(189, 240, 255),
             border='white',
             borderWidth=1)

    arrowX = x + directionMultiplier * 93 * scale

    drawLine(x + directionMultiplier * 62 * scale, y - 2 * scale,
             arrowX, y - 2 * scale,
             fill=GOLD,
             lineWidth=4)

    if directionMultiplier == 1:
        drawPolygon(
            arrowX + 8 * scale, y - 2 * scale,
            arrowX - 5 * scale, y - 10 * scale,
            arrowX - 5 * scale, y + 6 * scale,
            fill=GOLD
        )

    else:
        drawPolygon(
            arrowX - 8 * scale, y - 2 * scale,
            arrowX + 5 * scale, y - 10 * scale,
            arrowX + 5 * scale, y + 6 * scale,
            fill=GOLD
        )

# ------------------------------------------------------------
# Hurricane drawing
# ------------------------------------------------------------

def drawHurricane(x, y, scale, time):
    drawOval(x, y,
             210 * scale, 210 * scale,
             fill=rgb(214, 224, 243),
             opacity=28)

    wobble = 5 * math.sin(math.radians(time * 5))

    for i in range(5):
        size = (175 - i * 28) * scale
        angle = (time * 5 + i * 68) % 360

        # CPCS drawArc uses centerX and centerY,
        # not a top-left rectangle position.
        drawArc(x, y,
                size, size,
                angle, 225,
                fill=None,
                border=rgb(230, 240, 255),
                borderWidth=max(1, int(7 * scale)),
                opacity=84)

    drawCircle(x + wobble, y,
               18 * scale,
               fill=rgb(31, 44, 81))

    drawLabel('STORM',
              x, y + 135 * scale,
              size=max(10, int(15 * scale)),
              bold=True,
              fill='white')

# ------------------------------------------------------------
# Start app
# ------------------------------------------------------------

def main():
    runApp(width=1050, height=700)

main()