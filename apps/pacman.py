# pacman.py - Pac-Man clone for SCS, 1050x700
# Place this file as apps/pacman.py in the SCS repo.
# Run: python -m http.server 8000, then open ?app=pacman
# Controls: Arrow keys to move, SPACE to start, P to pause, R to restart.
# Audio: uses extensions/pacman_audio.py if present, else silent.
# Model, Controller, View are kept separate. onStep and key handlers
# change state, redrawAll only draws.
# Entry point is main() with runApp, like gorillas.py. Without main() SCS
# only draws the first frame and never starts onStep or key handling.
from scs import *
import random
import importlib

# ---- pacman audio integration - built ON TOP of proc_audio.py, like gorillas 8bit ----
try:
    _pac_audio_mod = importlib.import_module('extensions.pacman_audio')
    PacManAudioEngine = _pac_audio_mod.PacManAudioEngine
    HAS_PAC_AUDIO = True
except Exception as e:
    print(f"pacman audio load failed: {e}")
    HAS_PAC_AUDIO = False
    PacManAudioEngine = None
    _pac_audio_mod = None

# ---- indexed_db integration - app-agnostic local high scores, local players only ----
try:
    _idb_mod = importlib.import_module('extensions.indexed_db')
    _get_store = _idb_mod.get_store
    HAS_INDEXED_DB = True
except Exception as e:
    print(f"indexed_db load failed: {e}")
    HAS_INDEXED_DB = False
    _get_store = None
    _idb_mod = None

try:
    from browser import window as _window
    HAS_WINDOW = True
except Exception:
    _window = None
    HAS_WINDOW = False

_APP_ID = "pacman"
_scores = None
try:
    if HAS_INDEXED_DB and _get_store is not None:
        _scores = _get_store()
except Exception as e:
    print(f"indexed_db store failed: {e}")
    _scores = None

def play_sound(app, name, on_complete=None):
    # Event-driven sound - currentTime scheduling + onended, no timeouts
    # Same pattern as gorillas.py play_sound, engine lives on app.
    if app is None:
        return
    if not hasattr(app, 'engine') or app.engine is None:
        try:
            if HAS_PAC_AUDIO and PacManAudioEngine is not None:
                app.engine = PacManAudioEngine(quality="medium", seed=1)
                app.player = app.engine.player
                print("[pacman] audio engine ready")
            else:
                return
        except Exception as e:
            print(f"[pacman] audio init {e}")
            return
    try:
        app.engine.resume()
    except Exception:
        pass
    try:
        if hasattr(app, 'player') and app.player:
            try:
                app.player.resume()
            except Exception:
                pass
    except Exception:
        pass
    try:
        app.engine.play(name, on_complete=on_complete)
    except Exception as e:
        print(f"play {name} failed {e}")

def _ensureAudio(app):
    if app is None:
        return None
    try:
        if not hasattr(app, 'engine') or app.engine is None:
            if HAS_PAC_AUDIO and PacManAudioEngine is not None:
                app.engine = PacManAudioEngine(quality="medium", seed=1)
                app.player = app.engine.player
                print("[pacman] audio engine ready")
    except Exception as e:
        print(f"[pacman] audio init {e}")
    try:
        if hasattr(app, 'engine') and app.engine:
            app.engine.resume()
    except Exception:
        pass
    try:
        if hasattr(app, 'engine') and app.engine:
            return app.engine
    except Exception:
        pass
    return None

def _play(app, name=None):
    # Compat wrapper: new code calls play_sound(app, name)
    if name is None:
        return
    play_sound(app, name)

def _resumeAudio(app=None):
    try:
        if app is not None and hasattr(app, 'engine') and app.engine:
            app.engine.resume()
    except Exception:
        pass

def _loadHigh():
    try:
        if _scores is not None:
            return int(_scores.best_score_sync(_APP_ID, player="local"))
    except Exception:
        pass
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
        if _scores is not None:
            _scores.add_score_sync(_APP_ID, "local", int(v))
    except Exception:
        pass
    try:
        if HAS_WINDOW and _window is not None:
            _window.localStorage.setItem("pacman_high", str(v))
    except Exception:
        pass

def _normKey(k):
    # SCS / browser can deliver many variants: space, ' ', Spacebar, ArrowLeft, etc.
    # Normalize all of them to CMU names: space, left, right, up, down, p, r.
    try:
        s = str(k)
    except Exception:
        return ""
    s = s.strip().lower()
    if s in (" ", "space", "spacebar", "space_bar", "space bar"):
        return "space"
    if s in ("arrowleft", "left", "a"):
        return "left"
    if s in ("arrowright", "right", "d"):
        return "right"
    if s in ("arrowup", "up", "w"):
        return "up"
    if s in ("arrowdown", "down", "s"):
        return "down"
    if s in ("enter", "return", "returnkey"):
        return "space"
    if s in ("p", "r", "escape", "esc"):
        return s
    return s

def isReturnKey(key):
    if key is None:
        return False
    k = str(key).lower()
    return k in ('enter', 'return') or key in (chr(13), chr(10))

def _startGame(app):
    # Shared start path for SPACE, Enter, arrows, WASD, and mouse click.
    _ensureAudio(app)
    try:
        _resumeAudio(app)
    except Exception:
        pass
    if app.state not in ("ready", "dead", "won"):
        return
    if app.state != "ready":
        app.score = 0
        app.lives = 3
        app.level = 1
        app.nextExtraLife = 10000
        loadLevel(app)
        app.timer = 0
    else:
        if app.timer == 0:
            play_sound(app, "intro")
    app.state = "play"
    app.paused = False

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
    app.nextDir = (-1, 0)
    cols = ['red', 'pink', 'cyan', 'orange']
    names = ['blinky', 'pinky', 'inky', 'clyde']
    starts = [(BLINKY_START[0], BLINKY_START[1]), (17, 10), (15, 10), (19, 10)]
    states = ['active', 'house', 'house', 'house']
    release = [0, 0, 30, 60]
    app.ghosts = []
    for i in range(4):
        c, r = starts[i]
        g = newEntity(c, r, cols[i])
        g['name'] = names[i]
        g['state'] = states[i]
        g['releaseDots'] = release[i]
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
    d = distance(g['x'], g['y'], p['x'], p['y'])
    if d > 8 * T:
        return (pc, pr)
    return (1, 19)

def spawnFruit(app):
    kind = FRUIT_BY_LEVEL[app.level - 1] if app.level - 1 < len(FRUIT_BY_LEVEL) else 'melon'
    app.fruit = {'pos': FRUIT_POS, 'kind': kind, 'timer': 540}
    play_sound(app, 'fruit')

def addScore(app, pts):
    app.score = app.score + pts
    if app.score > app.high:
        app.high = app.score
        _saveHigh(app.high)
        try:
            if _scores is not None:
                app.leaderboard = _scores.top_scores_sync(_APP_ID, limit=3)
        except Exception:
            pass
    if app.score >= app.nextExtraLife:
        app.lives = app.lives + 1
        app.nextExtraLife = app.nextExtraLife + 10000
        play_sound(app, 'extra_life')

# Controller
def movePac(app):
    p = app.pac
    speed = getPacSpeed(app)
    # Instant reverse
    if app.nextDir[0] == -p['dx'] and app.nextDir[1] == -p['dy'] and app.nextDir != (0, 0):
        p['dx'], p['dy'] = app.nextDir
    if isNearCentre(p, speed + 1.5):
        snapToTile(p)
        c, r = tileOf(p)
        if (c, r) in app.pellets:
            app.pellets.remove((c, r))
            addScore(app, 10)
            app.pelletsEaten = app.pelletsEaten + 1
            app.dotsSinceDeath = app.dotsSinceDeath + 1
            play_sound(app, 'waka')
            if app.pelletsEaten == 70 and not app.fruitSpawned70:
                app.fruitSpawned70 = True
                spawnFruit(app)
            if app.pelletsEaten == 170 and not app.fruitSpawned170:
                app.fruitSpawned170 = True
                spawnFruit(app)
        if (c, r) in app.power:
            app.power.remove((c, r))
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
            play_sound(app, 'power')
        if app.fruit is not None and (c, r) == app.fruit['pos']:
            pts = FRUIT_POINTS[app.fruit['kind']]
            addScore(app, pts)
            app.fruit = None
            app.fruitTimer = 0
            play_sound(app, 'fruit_eaten')
        nx, ny = app.nextDir
        if (nx, ny) != (0, 0) and not isWall(app, c + nx, r + ny):
            p['dx'], p['dy'] = nx, ny
        if isWall(app, c + p['dx'], r + p['dy']):
            p['dx'] = 0
            p['dy'] = 0
    else:
        # Cornering: within 4 px of centre on the perpendicular axis, snap and turn early
        mx = p['x'] % T
        my = p['y'] % T
        dxc = mx if mx < T / 2 else T - mx
        dyc = my if my < T / 2 else T - my
        if p['dx'] != 0 and app.nextDir[1] != 0 and dyc < 4:
            c, r = tileOf(p)
            if not isWall(app, c + app.nextDir[0], r + app.nextDir[1]):
                p['y'] = int(round(p['y'] / T)) * T
                p['dx'], p['dy'] = app.nextDir
        if p['dy'] != 0 and app.nextDir[0] != 0 and dxc < 4:
            c, r = tileOf(p)
            if not isWall(app, c + app.nextDir[0], r + app.nextDir[1]):
                p['x'] = int(round(p['x'] / T)) * T
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
        # Release by pellet counter, with timer fallback so game never stalls
        if app.dotsSinceDeath >= g['releaseDots'] or app.timer - app.lastDeathTimer > 480:
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
        return
    if g['state'] == 'eyes':
        speed = 4.0
        if isNearCentre(g, speed + 1.5):
            snapToTile(g)
            c, r = tileOf(g)
            if c == DOOR_C and r == DOOR_R:
                g['state'] = 'entering'
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
            g['dx'], g['dy'] = opts[0]
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
        g['releaseDots'] = app.dotsSinceDeath + 2
        play_sound(app, 'ghost_revive')
        return
    # Active
    mode = currentMode(app)
    scatter = mode == 'scatter'
    speed = getGhostSpeed(app, i, g)
    # Tunnel: keep straight, no decision
    c0, r0 = tileOf(g)
    inTunnel = r0 == TUNNEL_ROW and (c0 < 5 or c0 > 29)
    if isNearCentre(g, speed + 1.5) and not inTunnel:
        snapToTile(g)
        c, r = tileOf(g)
        opts = []
        for dx, dy in DIR_LIST:
            if (dx, dy) == (-g['dx'], -g['dy']):
                continue
            if not isWall(app, c + dx, r + dy, forGhost=True, allowDoor=False):
                opts.append((dx, dy))
        if not opts:
            opts = [(-g['dx'], -g['dy'])]
        if g['fright']:
            g['dx'], g['dy'] = random.choice(opts)
        else:
            tc, tr = ghostTarget(app, i, g, scatter)
            opts.sort(key=lambda d: (c + d[0] - tc) ** 2 + (r + d[1] - tr) ** 2)
            g['dx'], g['dy'] = opts[0]
    g['x'] = g['x'] + g['dx'] * speed
    g['y'] = g['y'] + g['dy'] * speed
    wrap(app, g)

def checkCollisions(app):
    p = app.pac
    for g in app.ghosts:
        if g['state'] == 'house' or g['state'] == 'leaving' or g['state'] == 'entering':
            continue
        if distance(p['x'], p['y'], g['x'], g['y']) < T * 0.6:
            if g['fright'] and g['state'] == 'active':
                app.ghostCombo = app.ghostCombo + 1
                pts = 200 * (2 ** (app.ghostCombo - 1))
                addScore(app, pts)
                g['fright'] = False
                g['state'] = 'eyes'
                g['dx'] = 0
                g['dy'] = -1
                play_sound(app, 'ghost_eaten')
            elif g['state'] == 'active' and not g['fright']:
                app.lives = app.lives - 1
                play_sound(app, 'death')
                if app.lives <= 0:
                    app.state = 'dead'
                    try:
                        saveLeaderboard(app)
                    except Exception:
                        pass
                else:
                    app.state = 'ready'
                resetPositions(app)
                app.timer = 0
                app.lastDeathTimer = 0
                app.modeTimer = 0
                return

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
    app.state = 'ready'
    app.paused = False
    app.timer = 0
    app.lastDeathTimer = 0
    app.frightTimer = 0
    app.ghostCombo = 0
    app.mouth = 0
    app.leaderboard = []
    app.leaderboardError = False
    app.lastKey = ""
    app.engine = None
    app.player = None
    # Audio engine init (does not touch graphics), like gorillas.py
    if HAS_PAC_AUDIO and PacManAudioEngine:
        try:
            app.engine = PacManAudioEngine(quality="medium", seed=1)
            app.player = app.engine.player
            print("[pacman] audio engine ready")
        except Exception as e:
            print(f"[pacman] audio init {e}")
    loadLevel(app)
    # Leaderboard: IndexedDB local only, sync mirror, never blocks, never fetches
    try:
        loadLeaderboard(app)
    except Exception:
        app.leaderboard = []

def loadLeaderboard(app):
    try:
        if _scores is not None:
            app.leaderboard = _scores.top_scores_sync(_APP_ID, limit=3)
            return
    except Exception:
        pass
    app.leaderboard = []
    app.leaderboardError = False

def saveLeaderboard(app):
    try:
        if _scores is not None and app.score > 0:
            _scores.add_score_sync(_APP_ID, "local", int(app.score), level=int(app.level))
            app.leaderboard = _scores.top_scores_sync(_APP_ID, limit=3)
    except Exception:
        pass

def onKeyPress(app, key):
    # Resume audio on any key (gesture), like gorillas.py
    try:
        if hasattr(app, 'engine') and app.engine:
            app.engine.resume()
    except Exception:
        pass
    if key is None:
        return
    try:
        app.lastKey = str(key)
    except Exception:
        app.lastKey = ""
    k = _normKey(key)
    if k in DIRS:
        app.nextDir = DIRS[k]
        # Arrows / WASD also start the game, so pressing a direction just works.
        if app.state in ("ready", "dead", "won"):
            _startGame(app)
        return
    if k == "p" and app.state == "play":
        app.paused = not app.paused
        return
    if k == "r":
        app.score = 0
        app.lives = 3
        app.level = 1
        app.nextExtraLife = 10000
        loadLevel(app)
        app.state = "ready"
        app.timer = 0
        return
    if k == "space" and app.state in ("ready", "dead", "won"):
        _startGame(app)
        return

def onKeyHold(app, keys):
    # keys can be a set/list of raw browser names: ArrowLeft, ' ', etc. Normalize each.
    try:
        if keys is None:
            return
        for raw in list(keys):
            k = _normKey(raw)
            if k in DIRS:
                app.nextDir = DIRS[k]
    except Exception:
        pass

def onKeyRelease(app, key):
    return

def onMousePress(app, mouseX, mouseY):
    # Click to start also resumes audio. Fixes focus: canvas click is a user gesture.
    try:
        if hasattr(app, 'engine') and app.engine:
            app.engine.resume()
    except Exception:
        pass
    try:
        app.lastKey = "click"
    except Exception:
        pass
    _ensureAudio(app)
    if app.state in ("ready", "dead", "won"):
        _startGame(app)

def onStep(app):
    if app.state != 'play':
        return
    if app.paused:
        return
    app.timer = app.timer + 1
    app.modeTimer = app.modeTimer + 1
    app.mouth = (app.mouth + 1) % 20
    # Mode change: reverse ghosts on scatter to chase flip
    m = currentMode(app)
    if m != app.lastMode:
        app.lastMode = m
        for g in app.ghosts:
            if g['state'] == 'active' and not g['fright']:
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
    if not app.pellets and not app.power:
        app.level = app.level + 1
        loadLevel(app)
        app.state = 'won'
        play_sound(app, 'level_clear')

# View: redrawAll only draws
def redrawAll(app):
    # Maze walls from cache
    for (c, r) in app.walls:
        drawRect(c * T + 2, r * T + 2, T - 4, T - 4, fill=None, border='royalBlue', borderWidth=2)
    # Door
    drawRect(DOOR_C * T + 4, DOOR_R * T + 12, T - 8, 6, fill='pink', border=None)
    for (c, r) in app.pellets:
        drawCircle(c * T + T / 2, r * T + T / 2, 3, fill='white')
    pulse = 8
    if (app.timer // 12) % 2 == 0:
        pulse = 6
    for (c, r) in app.power:
        drawCircle(c * T + T / 2, r * T + T / 2, pulse, fill='white')
    # Fruit
    if app.fruit is not None:
        fc, fr = app.fruit['pos']
        fx = fc * T + T / 2
        fy = fr * T + T / 2
        kind = app.fruit['kind']
        if kind == 'cherry':
            drawCircle(fx - 5, fy + 4, 7, fill='red')
            drawCircle(fx + 5, fy + 4, 7, fill='red')
            drawLine(fx - 5, fy - 2, fx + 2, fy - 10, fill='green', lineWidth=2)
            drawLine(fx + 5, fy - 2, fx + 2, fy - 10, fill='green', lineWidth=2)
        elif kind == 'strawberry':
            drawCircle(fx, fy + 2, 10, fill='red')
            drawRect(fx - 6, fy - 10, 12, 4, fill='green')
        elif kind == 'orange':
            drawCircle(fx, fy, 11, fill='orange')
            drawRect(fx - 2, fy - 13, 4, 4, fill='green')
        elif kind == 'apple':
            drawCircle(fx, fy, 11, fill='red')
            drawRect(fx - 2, fy - 13, 4, 4, fill='brown')
        else:
            drawCircle(fx, fy, 11, fill='darkGreen')
            drawRect(fx - 8, fy - 2, 16, 3, fill='lightGreen')
    # Pac-Man
    p = app.pac
    openAmt = 40 if app.mouth < 10 else 5
    if app.state != 'play':
        openAmt = 20
    angMap = {(1, 0): 0, (-1, 0): 180, (0, 1): 90, (0, -1): 270, (0, 0): 0}
    ang = angMap[(p['dx'], p['dy'])]
    drawArc(p['x'] + T / 2, p['y'] + T / 2, T - 6, T - 6, ang + openAmt, 360 - 2 * openAmt, fill='yellow')
    # Ghosts
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
            # Wavy feet
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
    # HUD: 1050 x 70 at bottom
    y = ROWS * T + 22
    drawLabel('Score ' + str(app.score), 80, y, fill='white', size=16)
    drawLabel('High ' + str(app.high), 260, y, fill='yellow', size=16)
    drawLabel('Level ' + str(app.level), 525, y, fill='white', size=16)
    drawLabel('Lives ' + str(app.lives), 700, y, fill='white', size=16)
    drawLabel('Mode ' + currentMode(app), 870, y, fill='cyan', size=16)
    # Lives icons
    for k in range(app.lives):
        lx = 60 + k * 30
        ly = ROWS * T + 48
        drawArc(lx, ly, 20, 20, 30, 300, fill='yellow')
    # Fruit indicator
    if app.fruit is not None:
        drawLabel('Fruit ' + app.fruit['kind'], 1020 - 80, ROWS * T + 48, fill='pink', size=14)
    # Debug: show last key + state so a dead keyboard is visible.
    try:
        lk = getattr(app, "lastKey", "")
        drawLabel("Key " + str(lk) + " State " + str(app.state), 525, 12, fill="lightGray", size=12)
    except Exception:
        pass
    # Leaderboard line, best effort
    if len(app.leaderboard) > 0:
        txt = 'Top: '
        for s in app.leaderboard:
            if isinstance(s, dict) and 'score' in s:
                txt = txt + str(s['score']) + ' '
            else:
                txt = txt + str(s) + ' '
        drawLabel(txt, 525, ROWS * T + 48, fill='lightGray', size=13)
    if app.state != 'play':
        if app.state == 'ready':
            msg = 'Press SPACE'
        elif app.state == 'dead':
            msg = 'GAME OVER - SPACE'
        elif app.state == 'won':
            msg = 'LEVEL CLEAR - SPACE'
        else:
            msg = 'Press SPACE'
        drawLabel(msg, app.width / 2, 7 * T + 16, fill='yellow', size=28, bold=True)
    if app.paused:
        drawLabel('PAUSED - P to resume', app.width / 2, 9 * T + 16, fill='white', size=20, bold=True)

def main():
    runApp(1050, 700)

main()
