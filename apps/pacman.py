# pacman.py - Pac-Man clone for SCS, 1050x700
# Place this file as apps/pacman.py in the SCS repo.
# Run: python -m http.server 8000, then open ?app=pacman
# Controls: C / 5 = insert coin (credit, short waka), SPACE / ENTER / 1 = start
#   when CREDIT > 0, Arrow keys to move, P to pause, R to attract screen.
# Flow: attract (CHARACTER / NICKNAME, CREDIT 0) -> C -> pregame
#   (PUSH START BUTTON, CREDIT 1) -> C again -> pregame CREDIT 2 ->
#   SPACE -> intro (READY! + Start Music, no motion) -> play.
# Audio: uses extensions/pacman_audio.py if present, else silent.
# Credit is one short waka burst, not a jingle. Start Music is the jingle.
# Model, Controller, View are kept separate. onStep and key handlers
# change state, redrawAll only draws.
from scs import *
import random

# Audio: Pac-Man extension on top of proc_audio, guarded so game runs silent if missing.
try:
    from extensions.pacman_audio import PacManAudioEngine as _PacAudio
    HAS_PAC_AUDIO = True
except Exception:
    _PacAudio = None
    HAS_PAC_AUDIO = False

try:
    from browser import window as _window
    HAS_WINDOW = True
except Exception:
    _window = None
    HAS_WINDOW = False


_audio = None
try:
    if HAS_PAC_AUDIO and _PacAudio is not None:
        _audio = _PacAudio(quality="medium", seed=1)
except Exception:
    _audio = None

def _play(name):
    try:
        if _audio is not None:
            # Waka is defined in pacman_audio.py as one WSG voice, not here.
            _audio.play(name)
    except Exception:
        pass

def _resumeAudio():
    try:
        if _audio is not None:
            _audio.resume()
    except Exception:
        pass

def _stopAudio():
    try:
        if _audio is not None and getattr(_audio, 'player', None) is not None:
            _audio.player.stop_all()
    except Exception:
        pass

def _loadHigh():
    try:
        if HAS_WINDOW and _window is not None:
            v = _window.localStorage.getItem("pacman_high")
            if v is not None:
                return int(v)
    except Exception:
        pass
    return 0

def _saveHigh(v):
    try:
        if HAS_WINDOW and _window is not None:
            _window.localStorage.setItem("pacman_high", str(v))
    except Exception:
        pass

def _loadLeaderboard():
    try:
        if HAS_WINDOW and _window is not None:
            raw = _window.localStorage.getItem("pacman_leaderboard")
            if raw is not None:
                import json as _json
                data = _json.loads(raw)
                if isinstance(data, list):
                    return data[:3]
    except Exception:
        pass
    return []

def _saveLeaderboard(scores):
    try:
        if HAS_WINDOW and _window is not None:
            import json as _json
            _window.localStorage.setItem("pacman_leaderboard", _json.dumps(scores[:3]))
    except Exception:
        pass

def _dist(x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    return (dx * dx + dy * dy) ** 0.5

def _normKey(key):
    if key is None:
        return ''
    k = str(key)
    low = k.lower()
    if low in ('left', 'arrowleft', 'a'):
        return 'left'
    if low in ('right', 'arrowright', 'd'):
        return 'right'
    if low in ('up', 'arrowup', 'w'):
        return 'up'
    if low in ('down', 'arrowdown', 's'):
        return 'down'
    if low in (' ', 'space', 'spacebar'):
        return 'space'
    if low == 'p':
        return 'p'
    if low == 'r':
        return 'r'
    return low

# 1050 x 700 : T 30, COLS 35, ROWS 21, maze 1050 x 630, HUD 70
T = 30
COLS = 35
ROWS = 21
MAZE_W = 1050
MAZE_H = 630
HUD_H = 70
APP_W = 1050
APP_H = 700
TUNNEL_ROW = 10
DOOR_C = 17
DOOR_R = 8
FRUIT_POS = (17, 13)
PAC_START = (17, 15)
BLINKY_START = (17, 7)

MAZE = [
"###################################",
"#o...............................o#",
"#.####..####...#####...####..####.#",
"#.####..####...#####...####..####.#",
"#.#########..##.....##..#########.#",
"#o#########..##.....##..#########o#",
"#.####..##..##.......##..##..####.#",
"#.................................#",
"#.####..##....###D###....##..####.#",
"#.......##...#       #...##.......#",
"      ..##...# G G G #...##..      ",
"#............#       #............#",
"#.##..####..###########..####..##.#",
"#.##..####...............####..##.#",
"#.####..####...#####...####..####.#",
"#................P................#",
"#.####..####...#####...####..####.#",
"#.####..####...........####..####.#",
"#.####..#####..#####..#####..####.#",
"#o...............................o#",
"###################################",
]

DIRS = {'left': (-1, 0), 'right': (1, 0), 'up': (0, -1), 'down': (0, 1)}
DIR_LIST = [(-1, 0), (1, 0), (0, -1), (0, 1)]

# Scatter / chase phases in seconds: 7 scatter, 20 chase, 7, 20, 5, 20, 5, then chase forever.
PHASES = [(7, 'scatter'), (20, 'chase'), (7, 'scatter'), (20, 'chase'), (5, 'scatter'), (20, 'chase'), (5, 'scatter'), (100000, 'chase')]
FRUIT_POINTS = {'cherry': 100, 'strawberry': 300, 'orange': 500, 'apple': 700, 'melon': 1000}
FRUIT_BY_LEVEL = ['cherry', 'strawberry', 'orange', 'apple', 'melon', 'melon', 'melon']

# Arcade death, 60 steps/sec: freeze 60, anim 90, hold 60, total 210.
# Sound starts at tick 60, not at collision. Ghosts visible in freeze, gone in anim.
DEATH_FREEZE_TICKS = 60
DEATH_ANIM_TICKS = 90
DEATH_HOLD_TICKS = 60
DEATH_TOTAL_TICKS = 210
DEATH_READY_TICKS = 120
# Pregame / intro: Start Music is the opening jingle, Credit is one short waka.
# INTRO_TICKS covers the Start Music + READY! hold before any motion.
# FIX: 110 BPM, user's two-part text in music.txt. Treble as written = 41 16ths = 5.59 s = 335 ticks, bass = 32 16ths = 262 ticks. Use longer so intro does not cut off.
INTRO_TICKS = 262
DEAD_HOLD_TICKS = 180
WON_HOLD_TICKS = 120
CREDIT_MAX = 2
# 11 frames, mouth half-angle, facing up. Sweep = 360 - 2 * openAmt.
DEATH_OPEN = [20, 40, 60, 80, 100, 120, 140, 155, 165, 172, 178]
# Eating mouth: FIX - includes 0 so mouth fully closes.
# FIX - mouth only advances when Pac-Man actually moves, frozen when stopped.
# Full circle (openAmt 0) is only for intro / READY! plus the 0 frame in cycle.
PAC_MOUTH_CYCLE = [0, 10, 22, 32, 22, 10]

# Model helpers
def isWall(app, c, r, forGhost=False, allowDoor=False):
    if r < 0 or r >= ROWS:
        return True
    if c < 0 or c >= COLS:
        if r == TUNNEL_ROW:
            return False
        return True
    ch = MAZE[r][c]
    if ch == '#':
        return True
    if ch == 'D':
        return not allowDoor
    return False

def tileOf(e):
    cx = e['x'] + T / 2
    cy = e['y'] + T / 2
    return int(cx // T), int(cy // T)

def isNearCentre(e, tol):
    mx = e['x'] % T
    my = e['y'] % T
    dx = mx if mx < T / 2 else T - mx
    dy = my if my < T / 2 else T - my
    return dx < tol and dy < tol

def snapToTile(e):
    e['x'] = int(round(e['x'] / T)) * T
    e['y'] = int(round(e['y'] / T)) * T

def snapPerp(e, newDir):
    if newDir[0] != 0:
        e['y'] = int(round(e['y'] / T)) * T
    if newDir[1] != 0:
        e['x'] = int(round(e['x'] / T)) * T

def wrap(app, e):
    if e['x'] < -T:
        e['x'] = COLS * T
    if e['x'] > COLS * T:
        e['x'] = -T

def newEntity(c, r, color):
    return {'x': float(c * T), 'y': float(r * T), 'dx': 0, 'dy': 0, 'color': color, 'home': (c, r), 'fright': False, 'state': 'active', 'releaseDots': 0, 'bob': 0}

def resetPositions(app):
    app.pac = newEntity(PAC_START[0], PAC_START[1], 'yellow')
    app.pac['dx'] = -1
    app.pac['dy'] = 0
    app.pac['decideTile'] = None
    app.nextDir = (-1, 0)
    cols = ['red', 'pink', 'cyan', 'orange']
    names = ['blinky', 'pinky', 'inky', 'clyde']
    starts = [(BLINKY_START[0], BLINKY_START[1]), (17, 10), (15, 10), (19, 10)]
    states = ['active', 'house', 'house', 'house']
    release = [0, 0, 30, 60]
    releaseAfter = [0, 0, 240, 480]
    app.ghosts = []
    for i in range(4):
        c, r = starts[i]
        g = newEntity(c, r, cols[i])
        g['name'] = names[i]
        g['state'] = states[i]
        g['releaseDots'] = release[i]
        g['releaseAfter'] = releaseAfter[i]
        g['decideTile'] = None
        g['dx'] = -1 if i % 2 == 0 else 1
        g['dy'] = 0
        if states[i] == 'house':
            g['dx'] = 0
            g['dy'] = 0
        app.ghosts.append(g)
    app.dotsSinceDeath = 0
    app.frightTimer = 0
    app.ghostCombo = 0
    app.mouth = 0

def loadLevel(app):
    app.pellets = set()
    app.power = set()
    for r in range(ROWS):
        for c in range(COLS):
            if MAZE[r][c] == '.':
                app.pellets.add((c, r))
            if MAZE[r][c] == 'o':
                app.power.add((c, r))
    app.walls = []
    for r in range(ROWS):
        for c in range(COLS):
            if MAZE[r][c] == '#':
                app.walls.append((c, r))
    app.totalPellets = len(app.pellets) + len(app.power)
    app.pelletsEaten = 0
    app.fruit = None
    app.fruitTimer = 0
    app.fruitSpawned70 = False
    app.fruitSpawned170 = False
    app.modeTimer = 0
    app.lastMode = 'scatter'
    app.modeChanged = False
    resetPositions(app)

def currentMode(app):
    scale = 1.0
    if app.level == 2:
        scale = 0.85
    if app.level == 3:
        scale = 0.7
    if app.level >= 4:
        scale = 0.5
    t = app.modeTimer / 60.0
    acc = 0
    for dur, mode in PHASES:
        acc = acc + dur * scale
        if t < acc:
            return mode
    return 'chase'

def getPacSpeed(app):
    base = 2.0 + 0.08 * (app.level - 1)
    if base > 2.6:
        base = 2.6
    c, r = tileOf(app.pac)
    if r == TUNNEL_ROW and (c < 5 or c > 29):
        return 1.2
    if app.frightTimer > 0:
        return base + 0.15
    return base

def getGhostSpeed(app, i, g):
    if g['state'] == 'eyes':
        return 4.0
    if g['state'] == 'house':
        return 0.5
    if g['state'] == 'leaving' or g['state'] == 'entering':
        return 2.0
    c, r = tileOf(g)
    if r == TUNNEL_ROW and (c < 5 or c > 29):
        return 1.0
    if g['fright']:
        return 1.1
    base = 1.85 + 0.07 * (app.level - 1)
    if base > 2.4:
        base = 2.4
    # Elroy: Blinky speeds up when few pellets remain
    if i == 0:
        left = len(app.pellets) + len(app.power)
        if left < 10:
            base = base + 0.5
        elif left < 20:
            base = base + 0.3
    return base

def ghostTarget(app, i, g, scatter):
    p = app.pac
    pc, pr = tileOf(p)
    corners = [(33, 1), (1, 1), (33, 19), (1, 19)]
    if scatter:
        return corners[i]
    if i == 0:
        return (pc, pr)
    if i == 1:
        # Pinky: 4 ahead, with original up bug: 4 up and 4 left when moving up
        if p['dy'] == -1:
            return (pc - 4, pr - 4)
        return (pc + 4 * p['dx'], pr + 4 * p['dy'])
    if i == 2:
        b = app.ghosts[0]
        bc, br = tileOf(b)
        if p['dy'] == -1:
            ax, ay = pc - 2, pr - 2
        else:
            ax, ay = pc + 2 * p['dx'], pr + 2 * p['dy']
        return (2 * ax - bc, 2 * ay - br)
    # Clyde
    d = _dist(g['x'], g['y'], p['x'], p['y'])
    if d > 8 * T:
        return (pc, pr)
    return (1, 19)

def spawnFruit(app):
    kind = FRUIT_BY_LEVEL[app.level - 1] if app.level - 1 < len(FRUIT_BY_LEVEL) else 'melon'
    app.fruit = {'pos': FRUIT_POS, 'kind': kind, 'timer': 540}
    _play('fruit')

def addScore(app, pts):
    app.score = app.score + pts
    if app.score > app.high:
        app.high = app.score
        _saveHigh(app.high)
        try:
            board = list(app.leaderboard) if isinstance(app.leaderboard, list) else []
            board.append(app.high)
            board.sort(reverse=True)
            app.leaderboard = board[:3]
            _saveLeaderboard(app.leaderboard)
        except Exception:
            pass
    if app.score >= app.nextExtraLife:
        app.lives = app.lives + 1
        app.nextExtraLife = app.nextExtraLife + 10000
        _play('extra_life')

# Controller
def movePac(app):
    p = app.pac
    speed = getPacSpeed(app)
    # Eat on the tile Pac is actually in, every step. Cornering turns
    # early, so eating only near centre misses pellets in the turned-from tile.
    c0, r0 = tileOf(p)
    if (c0, r0) in app.pellets:
        app.pellets.remove((c0, r0))
        addScore(app, 10)
        app.pelletsEaten = app.pelletsEaten + 1
        app.dotsSinceDeath = app.dotsSinceDeath + 1
        _play('waka')
        if app.pelletsEaten == 70 and not app.fruitSpawned70:
            app.fruitSpawned70 = True
            spawnFruit(app)
        if app.pelletsEaten == 170 and not app.fruitSpawned170:
            app.fruitSpawned170 = True
            spawnFruit(app)
    if (c0, r0) in app.power:
        app.power.remove((c0, r0))
        addScore(app, 50)
        app.pelletsEaten = app.pelletsEaten + 1
        app.dotsSinceDeath = app.dotsSinceDeath + 1
        dur = 360 - app.level * 30
        if dur < 60:
            dur = 60
        if dur > 360:
            dur = 360
        app.frightTimer = dur
        app.ghostCombo = 0
        for g in app.ghosts:
            if g['state'] == 'active':
                g['fright'] = True
                g['dx'] = -g['dx']
                g['dy'] = -g['dy']
        _play('power')
    if app.fruit is not None and (c0, r0) == app.fruit['pos']:
        pts = FRUIT_POINTS[app.fruit['kind']]
        addScore(app, pts)
        app.fruit = None
        app.fruitTimer = 0
        _play('fruit_eaten')
    # Instant reverse, no snap needed.
    if app.nextDir[0] == -p['dx'] and app.nextDir[1] == -p['dy'] and app.nextDir != (0, 0):
        p['dx'], p['dy'] = app.nextDir
    if isNearCentre(p, speed + 1.5):
        c, r = tileOf(p)
        nx, ny = app.nextDir
        cur = (p['dx'], p['dy'])
        # Turning: snap both axes to centre only when actually turning.
        if (nx, ny) != (0, 0) and (nx, ny) != cur and not isWall(app, c + nx, r + ny):
            snapToTile(p)
            p['dx'], p['dy'] = nx, ny
        # Stopping: snap to centre only when wall ahead and we stop.
        elif isWall(app, c + p['dx'], r + p['dy']) and (p['dx'], p['dy']) != (0, 0):
            snapToTile(p)
            p['dx'] = 0
            p['dy'] = 0
        # Moving straight: no snap, keep momentum.
    else:
        # Cornering: within 4 px of centre on the perpendicular axis,
        # snap only the perpendicular axis and turn early.
        mx = p['x'] % T
        my = p['y'] % T
        dxc = mx if mx < T / 2 else T - mx
        dyc = my if my < T / 2 else T - my
        if p['dx'] != 0 and app.nextDir[1] != 0 and dyc < 4:
            c, r = tileOf(p)
            if not isWall(app, c + app.nextDir[0], r + app.nextDir[1]):
                snapPerp(p, app.nextDir)
                p['dx'], p['dy'] = app.nextDir
        if p['dy'] != 0 and app.nextDir[0] != 0 and dxc < 4:
            c, r = tileOf(p)
            if not isWall(app, c + app.nextDir[0], r + app.nextDir[1]):
                snapPerp(p, app.nextDir)
                p['dx'], p['dy'] = app.nextDir
    p['x'] = p['x'] + p['dx'] * speed
    p['y'] = p['y'] + p['dy'] * speed
    wrap(app, p)

def moveGhost(app, i, g):
    if g['state'] == 'house':
        g['bob'] = g['bob'] + 1
        if (g['bob'] // 20) % 2 == 0:
            g['y'] = g['y'] - 0.4
        else:
            g['y'] = g['y'] + 0.4
        if g['y'] < g['home'][1] * T - 4:
            g['y'] = g['home'][1] * T - 4
        if g['y'] > g['home'][1] * T + 4:
            g['y'] = g['home'][1] * T + 4
        # Staggered release: dots OR per-ghost timer, and only one ghost
        # leaves at a time, so leaving ghosts never stack on the door.
        leaving = False
        for other in app.ghosts:
            if other is not g and other['state'] in ('leaving', 'entering'):
                leaving = True
        dotsReady = app.dotsSinceDeath >= g['releaseDots']
        timeReady = app.timer - app.lastDeathTimer > g.get('releaseAfter', 0)
        if (dotsReady or timeReady) and not leaving:
            g['state'] = 'leaving'
            g['dx'] = 0
            g['dy'] = 0
        return
    if g['state'] == 'leaving':
        targetX = DOOR_C * T
        if abs(g['x'] - targetX) > 1.5:
            if g['x'] < targetX:
                g['x'] = g['x'] + 2
            else:
                g['x'] = g['x'] - 2
            return
        g['x'] = targetX
        if g['y'] > DOOR_R * T - T:
            g['y'] = g['y'] - 2
            return
        g['y'] = float(DOOR_R * T - T)
        g['state'] = 'active'
        g['dx'] = -1
        g['dy'] = 0
        g['decideTile'] = None
        return
    if g['state'] == 'eyes':
        speed = 4.0
        c, r = tileOf(g)
        if isNearCentre(g, speed + 1.5) and g.get('decideTile') != (c, r):
            if c == DOOR_C and r == DOOR_R:
                g['state'] = 'entering'
                g['decideTile'] = (c, r)
                return
            opts = []
            for dx, dy in DIR_LIST:
                if (dx, dy) == (-g['dx'], -g['dy']):
                    continue
                if not isWall(app, c + dx, r + dy, forGhost=True, allowDoor=True):
                    opts.append((dx, dy))
            if not opts:
                opts = [(-g['dx'], -g['dy'])]
            opts.sort(key=lambda d: (c + d[0] - DOOR_C) ** 2 + (r + d[1] - DOOR_R) ** 2)
            nxt = opts[0]
            if nxt != (g['dx'], g['dy']):
                snapToTile(g)
            g['dx'], g['dy'] = nxt
            g['decideTile'] = (c, r)
        g['x'] = g['x'] + g['dx'] * speed
        g['y'] = g['y'] + g['dy'] * speed
        wrap(app, g)
        return
    if g['state'] == 'entering':
        if g['y'] < 10 * T:
            g['y'] = g['y'] + 2
            return
        g['y'] = float(10 * T)
        g['x'] = float(g['home'][0] * T)
        g['state'] = 'house'
        g['fright'] = False
        g['bob'] = 0
        g['decideTile'] = None
        g['releaseDots'] = app.dotsSinceDeath + 2
        g['releaseAfter'] = 120
        _play('ghost_revive')
        return
    # Active
    mode = currentMode(app)
    scatter = mode == 'scatter'
    speed = getGhostSpeed(app, i, g)
    c0, r0 = tileOf(g)
    inTunnel = r0 == TUNNEL_ROW and (c0 < 5 or c0 > 29)
    if isNearCentre(g, speed + 1.5) and not inTunnel and g.get('decideTile') != (c0, r0):
        c, r = c0, r0
        opts = []
        for dx, dy in DIR_LIST:
            if (dx, dy) == (-g['dx'], -g['dy']):
                continue
            if not isWall(app, c + dx, r + dy, forGhost=True, allowDoor=False):
                opts.append((dx, dy))
        if not opts:
            opts = [(-g['dx'], -g['dy'])]
        if g['fright']:
            nxt = random.choice(opts)
        else:
            tc, tr = ghostTarget(app, i, g, scatter)
            opts.sort(key=lambda d: (c + d[0] - tc) ** 2 + (r + d[1] - tr) ** 2)
            nxt = opts[0]
        if nxt != (g['dx'], g['dy']):
            snapToTile(g)
        g['dx'], g['dy'] = nxt
        g['decideTile'] = (c, r)
    g['x'] = g['x'] + g['dx'] * speed
    g['y'] = g['y'] + g['dy'] * speed
    wrap(app, g)

def checkCollisions(app):
    p = app.pac
    for g in app.ghosts:
        if g['state'] == 'house' or g['state'] == 'leaving' or g['state'] == 'entering':
            continue
        if _dist(p['x'], p['y'], g['x'], g['y']) < T * 0.6:
            if g['fright'] and g['state'] == 'active':
                app.ghostCombo = app.ghostCombo + 1
                pts = 200 * (2 ** (app.ghostCombo - 1))
                addScore(app, pts)
                g['fright'] = False
                g['state'] = 'eyes'
                g['dx'] = 0
                g['dy'] = -1
                _play('ghost_eaten')
            elif g['state'] == 'active' and not g['fright']:
                app.lives = app.lives - 1
                app.frightTimer = 0
                app.fruit = None
                for _g in app.ghosts:
                    _g['fright'] = False
                _stopAudio()
                app.state = 'dying'
                app.deathTimer = 0
                app.pac['dx'] = 0
                app.pac['dy'] = 0
                app.nextDir = (0, 0)
                return

def _addCredit(app):
    if app.credits < CREDIT_MAX:
        app.credits = app.credits + 1
    _play('credit')
    if app.state == 'attract':
        app.state = 'pregame'
        app.timer = 0
    elif app.state == 'pregame':
        app.timer = 0

def _startFromPregame(app):
    if app.credits <= 0:
        return False
    app.credits = app.credits - 1
    app.score = 0
    app.lives = 3
    app.level = 1
    app.nextExtraLife = 10000
    loadLevel(app)
    app.timer = 0
    app.lastDeathTimer = 0
    app.modeTimer = 0
    app.deathTimer = 0
    app.nextDir = (-1, 0)
    app.state = 'intro'
    app.paused = False
    _play('intro')
    return True

def onAppStart(app):
    app.width = APP_W
    app.height = APP_H
    app.stepsPerSecond = 60
    app.background = 'black'
    app.score = 0
    app.high = _loadHigh()
    app.nextExtraLife = 10000
    app.lives = 3
    app.level = 1
    app.credits = 0
    app.state = 'attract'
    app.paused = False
    app.timer = 0
    app.lastDeathTimer = 0
    app.frightTimer = 0
    app.ghostCombo = 0
    app.mouth = 0
    app.deathTimer = 0
    app.leaderboard = _loadLeaderboard()
    loadLevel(app)

def onKeyPress(app, key):
    k = _normKey(key)
    # Coin: works in attract, pregame, and during play / intro / dying
    # for the next game. One short waka, never a jingle.
    if k in ('c', '5'):
        _resumeAudio()
        _addCredit(app)
        return
    if app.state in ('dying', 'ready_wait'):
        return
    if app.state == 'attract':
        if k in ('space', 'enter', 'return', '1'):
            if app.credits > 0:
                _resumeAudio()
                _startFromPregame(app)
        return
    if app.state == 'pregame':
        if k in ('space', 'enter', 'return', '1'):
            _resumeAudio()
            _startFromPregame(app)
        return
    if app.state == 'intro':
        if k in DIRS:
            app.nextDir = DIRS[k]
        return
    if app.state in ('dead', 'won'):
        if k == 'r':
            app.score = 0
            app.lives = 3
            app.level = 1
            app.nextExtraLife = 10000
            app.credits = 0
            loadLevel(app)
            app.state = 'attract'
            app.timer = 0
            app.deathTimer = 0
        return
    if k in DIRS:
        pressed = DIRS[k]
        app.nextDir = pressed
        return
    if k == 'p' and app.state == 'play':
        app.paused = not app.paused
        return
    if k == 'r':
        app.score = 0
        app.lives = 3
        app.level = 1
        app.nextExtraLife = 10000
        app.credits = 0
        loadLevel(app)
        app.state = 'attract'
        app.timer = 0
        app.deathTimer = 0
        return
    if k == 'space' and app.state == 'play':
        return
def _tickHouse(app):
    for g in app.ghosts:
        if g['state'] != 'house':
            continue
        g['bob'] = g['bob'] + 1
        if (g['bob'] // 20) % 2 == 0:
            g['y'] = g['y'] - 0.4
        else:
            g['y'] = g['y'] + 0.4
        if g['y'] < g['home'][1] * T - 4:
            g['y'] = g['home'][1] * T - 4
        if g['y'] > g['home'][1] * T + 4:
            g['y'] = g['home'][1] * T + 4

def onStep(app):
    if app.state == 'dying':
        app.deathTimer = app.deathTimer + 1
        if app.deathTimer == DEATH_FREEZE_TICKS:
            _play('death')
        if app.deathTimer >= DEATH_TOTAL_TICKS:
            app.deathTimer = 0
            if app.lives <= 0:
                app.state = 'dead'
                app.timer = 0
            else:
                resetPositions(app)
                app.timer = 0
                app.lastDeathTimer = 0
                app.modeTimer = 0
                app.frightTimer = 0
                app.fruit = None
                app.state = 'ready_wait'
        return
    if app.state == 'ready_wait':
        app.timer = app.timer + 1
        _tickHouse(app)
        if app.timer >= DEATH_READY_TICKS:
            app.timer = 0
            app.modeTimer = 0
            app.state = 'play'
            app.paused = False
        return
    if app.state in ('attract', 'pregame'):
        app.timer = app.timer + 1
        return
    if app.state == 'intro':
        app.timer = app.timer + 1
        _tickHouse(app)
        if app.timer >= INTRO_TICKS:
            app.timer = 0
            app.modeTimer = 0
            app.state = 'play'
            app.paused = False
        return
    if app.state == 'dead':
        app.timer = app.timer + 1
        if app.timer >= DEAD_HOLD_TICKS:
            app.timer = 0
            app.score = 0
            app.lives = 3
            app.level = 1
            app.nextExtraLife = 10000
            loadLevel(app)
            if app.credits > 0:
                app.state = 'pregame'
            else:
                app.state = 'attract'
        return
    if app.state == 'won':
        app.timer = app.timer + 1
        if app.timer >= WON_HOLD_TICKS:
            app.timer = 0
            app.lastDeathTimer = 0
            app.modeTimer = 0
            app.deathTimer = 0
            loadLevel(app)
            resetPositions(app)
            app.state = 'intro'
            app.paused = False
            _play('intro')
        return
    if app.state != 'play':
        return
    if app.paused:
        return
    app.timer = app.timer + 1
    app.modeTimer = app.modeTimer + 1
    # FIX: mouth only advances when Pac-Man actually moves, frozen when stopped against a wall.
    if (app.pac['dx'], app.pac['dy']) != (0, 0):
        app.mouth = (app.mouth + 1) % 20
    # Mode change: reverse ghosts on scatter to chase flip
    m = currentMode(app)
    if m != app.lastMode:
        app.lastMode = m
        for g in app.ghosts:
            if g['state'] == 'active' and not g['fright']:
                c, r = tileOf(g)
                if not isWall(app, c - g['dx'], r - g['dy'], forGhost=True, allowDoor=False):
                    g['dx'] = -g['dx']
                    g['dy'] = -g['dy']
    if app.frightTimer > 0:
        app.frightTimer = app.frightTimer - 1
        if app.frightTimer == 0:
            for g in app.ghosts:
                g['fright'] = False
    if app.fruit is not None:
        app.fruitTimer = app.fruitTimer + 1
        app.fruit['timer'] = app.fruit['timer'] - 1
        if app.fruit['timer'] <= 0:
            app.fruit = None
    movePac(app)
    for i, g in enumerate(app.ghosts):
        moveGhost(app, i, g)
    checkCollisions(app)
    if app.state != 'play':
        return
    if not app.pellets and not app.power:
        app.level = app.level + 1
        loadLevel(app)
        app.state = 'won'
        _play('level_clear')

# View: only draws, never changes state.
# redrawAll only calls draw helpers, like the drone example:
# drawMaze, drawPellets, drawFruit, drawPac, drawGhosts, drawHUD.
# Controllers (onKeyPress, onStep) never draw. Draw helpers never
# change app state, never play sound, never print keys or state.
def drawMaze(app):
    for (c, r) in app.walls:
        drawRect(c * T + 2, r * T + 2, T - 4, T - 4, fill=None, border='royalBlue', borderWidth=2)
    drawRect(DOOR_C * T + 4, DOOR_R * T + 12, T - 8, 6, fill='pink', border=None)

def drawPellets(app):
    for (c, r) in app.pellets:
        drawCircle(c * T + T / 2, r * T + T / 2, 3, fill='white')
    pulse = 8
    if (app.timer // 12) % 2 == 0:
        pulse = 6
    for (c, r) in app.power:
        drawCircle(c * T + T / 2, r * T + T / 2, pulse, fill='white')

def drawFruit(app):
    if app.fruit is None:
        return
    fc, fr = app.fruit['pos']
    fx = fc * T + T / 2
    fy = fr * T + T / 2
    kind = app.fruit['kind']
    if kind == 'cherry':
        drawCircle(fx - 5, fy + 4, 7, fill='red')
        drawCircle(fx + 5, fy + 4, 7, fill='red')
        drawLine(fx - 5, fy - 2, fx + 2, fy - 10, fill='#D89055', lineWidth=2)
        drawLine(fx + 5, fy - 2, fx + 2, fy - 10, fill='#D89055', lineWidth=2)
        drawRect(fx - 9, fy + 5, 4, 4, fill='white')
        drawRect(fx + 1, fy + 5, 4, 4, fill='white')
    elif kind == 'strawberry':
        drawCircle(fx, fy + 2, 10, fill='red')
        drawRect(fx - 6, fy - 10, 12, 4, fill='green')
    elif kind == 'orange':
        drawCircle(fx, fy, 11, fill='orange')
        drawRect(fx - 2, fy - 13, 4, 4, fill='brown')
    elif kind == 'apple':
        drawCircle(fx, fy, 11, fill='red')
        drawRect(fx - 2, fy - 13, 4, 4, fill='brown')
    else:
        drawCircle(fx, fy, 11, fill='darkGreen')
        drawRect(fx - 8, fy - 2, 16, 3, fill='lightGreen')

def drawPac(app):
    p = app.pac
    if app.state in ('attract', 'pregame'):
        return
    if app.state == 'dead':
        return
    if app.state in ('intro', 'ready_wait'):
        drawArc(p['x'] + T / 2, p['y'] + T / 2, T - 6, T - 6, 0, 360, fill='yellow', border=None)
        return
    if app.state == 'dying':
        if app.deathTimer < DEATH_FREEZE_TICKS:
            openAmt = 20
            angMap = {(1, 0): 0, (-1, 0): 180, (0, 1): 90, (0, -1): 270, (0, 0): 0}
            ang = angMap[(p['dx'], p['dy'])]
            drawArc(p['x'] + T / 2, p['y'] + T / 2, T - 6, T - 6, ang + openAmt, 360 - 2 * openAmt, fill='yellow', border=None)
            return
        anim = app.deathTimer - DEATH_FREEZE_TICKS
        if anim >= DEATH_ANIM_TICKS:
            return
        frame = (anim * 11) // DEATH_ANIM_TICKS
        if frame > 10:
            frame = 10
        openAmt = DEATH_OPEN[frame]
        drawArc(p['x'] + T / 2, p['y'] + T / 2, T - 6, T - 6, 270 + openAmt, 360 - 2 * openAmt, fill='yellow', border=None)
        if anim >= 80:
            cx = p['x'] + T / 2
            cy = p['y'] + T / 2
            drawLine(cx - 9, cy, cx + 9, cy, fill='yellow', lineWidth=2)
            drawLine(cx, cy - 9, cx, cy + 9, fill='yellow', lineWidth=2)
            drawLine(cx - 6, cy - 6, cx + 6, cy + 6, fill='yellow', lineWidth=2)
            drawLine(cx - 6, cy + 6, cx + 6, cy - 6, fill='yellow', lineWidth=2)
            drawCircle(cx, cy, 2, fill='yellow')
        return
    # drawArc(centerX, centerY, width, height, startAngle, sweepAngle,
    #         fill, border). Angles: 0 = east, 90 = south, 180 = west,
    # 270 = north (canvas clockwise). Mouth is the missing wedge:
    # start = facing + openAmt, sweep = 360 - 2 * openAmt.
    # FIX: cycle now includes 0, so mouth fully closes. Frozen when stopped (see onStep).
    openAmt = PAC_MOUTH_CYCLE[(app.mouth // 2) % len(PAC_MOUTH_CYCLE)]
    angMap = {(1, 0): 0, (-1, 0): 180, (0, 1): 90, (0, -1): 270, (0, 0): 0}
    ang = angMap[(p['dx'], p['dy'])]
    drawArc(p['x'] + T / 2, p['y'] + T / 2, T - 6, T - 6, ang + openAmt, 360 - 2 * openAmt, fill='yellow', border=None)

def drawGhosts(app):
    if app.state in ('attract', 'pregame'):
        return
    if app.state == 'dead':
        return
    if app.state == 'dying' and app.deathTimer >= DEATH_FREEZE_TICKS:
        return
    for g in app.ghosts:
        cx = g['x'] + T / 2
        cy = g['y'] + T / 2
        if g['state'] == 'eyes':
            drawCircle(cx - 5, cy - 3, 4, fill='white')
            drawCircle(cx + 5, cy - 3, 4, fill='white')
            drawCircle(cx - 5 + g['dx'] * 2, cy - 3 + g['dy'] * 2, 2, fill='blue')
            drawCircle(cx + 5 + g['dx'] * 2, cy - 3 + g['dy'] * 2, 2, fill='blue')
        else:
            if g['fright']:
                col = 'blue'
                if app.frightTimer < 90 and (app.frightTimer // 10) % 2 == 1:
                    col = 'white'
            else:
                col = g['color']
            drawCircle(cx, cy - 2, 12, fill=col)
            drawRect(cx - 12, cy - 2, 24, 14, fill=col)
            for k in range(3):
                drawCircle(cx - 8 + k * 8, cy + 12, 4, fill=col)
            if g['fright']:
                drawCircle(cx - 5, cy - 2, 2, fill='white')
                drawCircle(cx + 5, cy - 2, 2, fill='white')
                drawLine(cx - 6, cy + 5, cx + 6, cy + 5, fill='white', lineWidth=1)
            else:
                drawCircle(cx - 5, cy - 3, 3, fill='white')
                drawCircle(cx + 5, cy - 3, 3, fill='white')
                drawCircle(cx - 5 + g['dx'] * 2, cy - 3 + g['dy'] * 2, 1.5, fill='black')
                drawCircle(cx + 5 + g['dx'] * 2, cy - 3 + g['dy'] * 2, 1.5, fill='black')

def _drawGhostIcon(cx, cy, col):
    drawCircle(cx, cy - 2, 12, fill=col)
    drawRect(cx - 12, cy - 2, 24, 14, fill=col)
    for k in range(3):
        drawCircle(cx - 8 + k * 8, cy + 12, 4, fill=col)
    drawCircle(cx - 5, cy - 3, 3, fill='white')
    drawCircle(cx + 5, cy - 3, 3, fill='white')
    drawCircle(cx - 5, cy - 3, 1.5, fill='black')
    drawCircle(cx + 5, cy - 3, 1.5, fill='black')

def _drawScoreHeader(app):
    drawLabel('1UP', 210, 22, fill='white', size=16)
    drawLabel(str(app.score).zfill(2) if app.state in ('attract', 'pregame') else str(app.score), 210, 44, fill='white', size=16)
    drawLabel('HIGH SCORE', 525, 22, fill='white', size=16)
    drawLabel(str(app.high), 525, 44, fill='white', size=16)
    drawLabel('2UP', 840, 22, fill='white', size=16)
    if app.credits >= 2:
        drawLabel('00', 840, 44, fill='white', size=16)

def drawAttract(app):
    _drawScoreHeader(app)
    drawLabel('CHARACTER / NICKNAME', 525, 120, fill='white', size=18)
    rows = [
        ('red', 'OIKAKE - - - "AKABEI"', 'red', 185),
        ('pink', 'MACHIBUSE - - "PINKY"', 'pink', 255),
        ('cyan', 'KIMAGURE - - "AOSUKE"', 'cyan', 325),
        ('orange', 'OTOBOKE - - - "GUZUTA"', 'orange', 395),
    ]
    for col, txt, fill, y in rows:
        _drawGhostIcon(210, y, col)
        drawLabel(txt, 560, y, fill=fill, size=16)
    drawCircle(210, 485, 4, fill='white')
    drawArc(500, 485, 26, 26, 32, 296, fill='yellow', border=None)
    _drawGhostIcon(580, 485, 'red')
    _drawGhostIcon(660, 485, 'pink')
    _drawGhostIcon(740, 485, 'cyan')
    _drawGhostIcon(820, 485, 'orange')
    drawCircle(210, 545, 3, fill='white')
    drawLabel('.  10  PTS', 420, 545, fill='white', size=16)
    drawCircle(210, 590, 8, fill='white')
    drawLabel('50  PTS', 420, 590, fill='white', size=16)
    drawLabel('namco', 525, 640, fill='pink', size=16)
    drawLabel('CREDIT  ' + str(app.credits), 525, 680, fill='white', size=16)
    drawLabel('C = COIN   SPACE = START', 525, 662, fill='gray', size=11)

def drawPregame(app):
    _drawScoreHeader(app)
    if (app.timer // 30) % 2 == 0:
        drawLabel('PUSH START BUTTON', 525, 300, fill='orange', size=24)
    drawLabel('1 PLAYER ONLY', 525, 400, fill='cyan', size=20)
    drawLabel('BONUS PAC-MAN FOR 10000 PTS', 525, 480, fill='pink', size=18)
    drawLabel('© 1980 MIDWAY MFG. CO.', 525, 560, fill='pink', size=16)
    drawLabel('CREDIT  ' + str(app.credits), 525, 680, fill='white', size=16)
    if app.credits >= 2:
        drawLabel('2 CREDITS', 525, 620, fill='white', size=14)
    else:
        drawLabel('C = ANOTHER CREDIT', 525, 620, fill='gray', size=12)

def drawHUD(app):
    y = ROWS * T + 22
    drawLabel('1UP  ' + str(app.score), 150, y, fill='white', size=16)
    drawLabel('HIGH SCORE  ' + str(app.high), 525, y, fill='white', size=16)
    drawLabel('CREDIT  ' + str(app.credits), 880, y, fill='white', size=16)
    for k in range(app.lives):
        lx = 60 + k * 30
        ly = ROWS * T + 48
        drawArc(lx, ly, 20, 20, 32, 296, fill='yellow', border=None)
    kind = FRUIT_BY_LEVEL[app.level - 1] if app.level - 1 < len(FRUIT_BY_LEVEL) else 'melon'
    fx = 980
    fy = ROWS * T + 48
    if kind == 'cherry':
        drawCircle(fx - 5, fy + 4, 7, fill='red')
        drawCircle(fx + 5, fy + 4, 7, fill='red')
        drawLine(fx - 5, fy - 2, fx + 2, fy - 10, fill='#D89055', lineWidth=2)
        drawLine(fx + 5, fy - 2, fx + 2, fy - 10, fill='#D89055', lineWidth=2)
        drawRect(fx - 9, fy + 5, 4, 4, fill='white')
        drawRect(fx + 1, fy + 5, 4, 4, fill='white')
    elif kind == 'strawberry':
        drawCircle(fx, fy + 2, 10, fill='red')
    elif kind == 'orange':
        drawCircle(fx, fy, 11, fill='orange')
    elif kind == 'apple':
        drawCircle(fx, fy, 11, fill='red')
    else:
        drawCircle(fx, fy, 11, fill='darkGreen')

def redrawAll(app):
    if app.state == 'attract':
        drawAttract(app)
        return
    if app.state == 'pregame':
        drawPregame(app)
        return
    drawMaze(app)
    drawPellets(app)
    drawFruit(app)
    drawPac(app)
    drawGhosts(app)
    drawHUD(app)
    if app.state in ('intro', 'ready_wait'):
        drawLabel('READY!', 525, 380, fill='yellow', size=24)
    if app.state == 'dead':
        drawLabel('GAME OVER', 525, 380, fill='red', size=24)
    if app.state == 'won':
        drawLabel('LEVEL CLEAR', 525, 380, fill='yellow', size=24)
    if app.state == 'play' and app.paused:
        drawLabel('PAUSED', 525, 380, fill='white', size=24)

def main():
    runApp(1050, 700, stepsPerSecond=60)

main()
