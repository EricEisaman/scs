# apps/platformer_multiplayer.py
# SCS Multiplayer Platformer Demo - Datastar + Brython Fullstack Showcase
# ========================================================================
# No WebSockets! Pure Datastar SSE + HTTP actions + Brython canvas.
# 
# This demo showcases the SCS Extensions System at its best:
# - extensions.fetch for HTTP
# - extensions.datastar for SSE signal integration
# - SCS canvas for 2D platformer rendering
# - MVC: Datastar = Model sync, Controller = input + fetch, View = canvas
#
# Playable offline (2-4 local players) + online (datastar-synced) with same code.
#
# Controls:
#   Player 1: A/D move, W/Space jump, S down
#   Player 2: Arrows move, Up/Space jump
#   Player 3: J/L move, I jump
#   Player 4: Numpad 4/6 move, Numpad 8 jump
#   Global: R reset, P pause, C add coin, M toggle multiplayer mode, 1-4 add players
#
# Datastar integration:
#   If running inside fullstack shell (window.__SCS_GAME_STATE exists),
#   game reads authoritative state from datastar signals.
#   Otherwise runs local simulation.

from scs import *
from browser import window, document, aio
import math
import random

# Try to import extensions (may not exist in some contexts)
try:
    from extensions.fetch import fetch_json
    HAS_FETCH = True
except:
    HAS_FETCH = False

try:
    from extensions.datastar import get_game_snapshot, get_signal, is_datastar_connected, set_signal
    HAS_DATASTAR = True
except:
    HAS_DATASTAR = False
    def get_game_snapshot(): return None
    def get_signal(name, default=None): return default
    def is_datastar_connected(): return False
    def set_signal(name, val): return False

# ==================== PLATFORMER PHYSICS ====================

def clamp(v, lo, hi):
    if v < lo: return lo
    if v > hi: return hi
    return v

def aabb_overlap(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
    return not (ax2 < bx1 or ax1 > bx2 or ay2 < by1 or ay1 > by2)

class Platform:
    def __init__(self, x, y, w, h, typ="normal", color=None):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.type = typ  # normal, bouncy, moving, lava
        self.color = color or rgb(60, 60, 80)
        self.orig_x = x
        self.orig_y = y
        self.phase = random.random() * 6.28

class Coin:
    def __init__(self, x, y, val=10):
        self.x = x
        self.y = y
        self.val = val
        self.collected = False
        self.bob = random.random() * 6.28
        self.spin = 0

class Player:
    def __init__(self, pid, name, x, y, color, keys):
        self.id = pid
        self.name = name
        self.x = x
        self.y = y
        self.vx = 0
        self.vy = 0
        self.w = 32
        self.h = 44
        self.on_ground = False
        self.facing = 1
        self.state = "idle"
        self.color = color
        self.keys = keys  # dict: left, right, jump, down
        self.score = 0
        self.jump_count = 0
        self.max_jumps = 2
        self.coyote_timer = 0
        self.jump_buffer = 0
        self.alive = True
        self.spawn_x = x
        self.spawn_y = y
        self.trail = []  # for juice

    def aabb(self):
        return (self.x - self.w/2, self.y - self.h/2, self.x + self.w/2, self.y + self.h/2)

    def reset(self):
        self.x = self.spawn_x
        self.y = self.spawn_y
        self.vx = 0
        self.vy = 0
        self.on_ground = False
        self.state = "idle"
        self.jump_count = 0
        self.alive = True

# ==================== WORLD ====================

class World:
    def __init__(self, width=2400, height=700):
        self.width = width
        self.height = height
        self.gravity = 0.65
        self.friction = 0.82
        self.platforms = []
        self.coins = []
        self.players = {}
        self.tick = 0
        self.build_level()
    
    def build_level(self):
        # Ground + aesthetic platforms
        self.platforms = [
            Platform(1200, 680, 2400, 50, "normal", rgb(40, 40, 60)),
            # Main path
            Platform(250, 580, 180, 18, "normal", rgb(80, 80, 110)),
            Platform(500, 520, 180, 18, "normal"),
            Platform(750, 460, 200, 18, "normal", rgb(90, 70, 110)),
            Platform(1050, 400, 220, 18, "normal"),
            Platform(1350, 360, 200, 18, "bouncy", rgb(100, 200, 100)),
            Platform(1650, 420, 180, 18, "normal"),
            Platform(1900, 500, 200, 18, "normal"),
            Platform(2100, 580, 180, 18, "normal"),
            # Upper secret
            Platform(600, 300, 120, 16, "normal", rgb(70, 70, 100)),
            Platform(800, 240, 140, 16, "normal"),
            Platform(1100, 200, 160, 16, "normal", rgb(200, 180, 80)),
            Platform(1400, 240, 140, 16, "normal"),
            Platform(1700, 300, 120, 16, "normal"),
            # Walls
            Platform(30, 400, 24, 700, "normal", rgb(30, 30, 50)),
            Platform(2370, 400, 24, 700, "normal", rgb(30, 30, 50)),
            # Lava pit for fun
            Platform(1200, 700, 300, 20, "lava", rgb(200, 50, 30)),
        ]
        self.coins = []
        positions = [
            (250, 530), (500, 470), (750, 410), (1050, 350), (1350, 310),
            (1650, 370), (1900, 450), (2100, 530),
            (600, 250), (800, 190), (1100, 150), (1400, 190), (1700, 250),
            (1050, 100), (1200, 100), (1350, 100),
            (400, 200), (1800, 200), (1200, 300)
        ]
        for i, (x, y) in enumerate(positions):
            self.coins.append(Coin(x, y, val=10 + (i%3)*5))

    def add_player(self, pid, name, color, keys):
        spawn_x = 150 + len(self.players)*60
        spawn_y = 100
        p = Player(pid, name, spawn_x, spawn_y, color, keys)
        self.players[pid] = p
        return p

    def apply_input(self, pid, move_x, jump, down=False):
        if pid not in self.players:
            return
        p = self.players[pid]
        if not p.alive:
            return
        
        # Horizontal
        if move_x != 0:
            p.vx = move_x * 5.8
            p.facing = move_x
            if p.on_ground:
                p.state = "run"
        else:
            p.vx *= self.friction
            if abs(p.vx) < 0.2:
                p.vx = 0
                if p.on_ground:
                    p.state = "idle"
        
        # Jump buffering
        if jump:
            p.jump_buffer = 6
        
        if p.jump_buffer > 0:
            if p.on_ground or p.coyote_timer > 0:
                p.vy = -13.2
                p.on_ground = False
                p.coyote_timer = 0
                p.jump_count = 1
                p.state = "jump"
                p.jump_buffer = 0
            elif p.jump_count < p.max_jumps:
                p.vy = -11.0
                p.jump_count += 1
                p.state = "jump"
                p.jump_buffer = 0

    def resolve_collisions(self, p):
        p.on_ground = False
        px1, py1, px2, py2 = p.aabb()
        
        for plat in self.platforms:
            bx1 = plat.x - plat.w/2
            by1 = plat.y - plat.h/2
            bx2 = plat.x + plat.w/2
            by2 = plat.y + plat.h/2
            
            if not aabb_overlap(px1, py1, px2, py2, bx1, by1, bx2, by2):
                continue
            
            if plat.type == "lava":
                # Die and respawn
                p.x = p.spawn_x
                p.y = p.spawn_y
                p.vx = 0
                p.vy = 0
                p.score = max(0, p.score - 20)
                continue
            
            overlap_x = min(px2, bx2) - max(px1, bx1)
            overlap_y = min(py2, by2) - max(py1, by1)
            
            if overlap_x < overlap_y:
                if p.x < plat.x:
                    p.x = bx1 - p.w/2 - 0.5
                else:
                    p.x = bx2 + p.w/2 + 0.5
                p.vx = 0
                if plat.type == "bouncy":
                    p.vx = -p.vx * 0.5
            else:
                if p.y < plat.y:
                    p.y = by1 - p.h/2 - 0.5
                    p.vy = 0
                    p.on_ground = True
                    p.coyote_timer = 6
                    p.jump_count = 0
                    if p.state in ("jump", "fall"):
                        p.state = "run" if abs(p.vx) > 0.5 else "idle"
                    if plat.type == "bouncy":
                        p.vy = -16
                        p.on_ground = False
                else:
                    p.y = by2 + p.h/2 + 0.5
                    p.vy = 0

    def step(self):
        self.tick += 1
        # Update platforms (moving)
        for plat in self.platforms:
            if plat.type == "moving":
                plat.x = plat.orig_x + math.sin(self.tick*0.02 + plat.phase) * 100
        
        for p in self.players.values():
            if not p.alive:
                continue
            
            # Timers
            if p.jump_buffer > 0:
                p.jump_buffer -= 1
            if p.coyote_timer > 0:
                p.coyote_timer -= 1
            
            # Gravity
            if not p.on_ground:
                p.vy += self.gravity
                if p.vy > 14:
                    p.vy = 14
                if p.vy > 1:
                    p.state = "fall"
            
            p.x += p.vx
            p.y += p.vy
            
            self.resolve_collisions(p)
            
            # Bounds
            if p.x < 40:
                p.x = 40
                p.vx = 0
            if p.x > self.width - 40:
                p.x = self.width - 40
                p.vx = 0
            if p.y > self.height + 200:
                p.x = p.spawn_x
                p.y = p.spawn_y
                p.vx = 0
                p.vy = 0
                p.score = max(0, p.score - 15)
            
            # Trail for juice
            p.trail.append((p.x, p.y))
            if len(p.trail) > 8:
                p.trail.pop(0)
            
            # Coins
            for coin in self.coins:
                if coin.collected:
                    continue
                if math.hypot(p.x - coin.x, p.y - coin.y) < 28:
                    coin.collected = True
                    p.score += coin.val

# ==================== SCS APP ====================

PLAYER_COLORS = [
    rgb(255, 107, 107), rgb(78, 205, 196), rgb(69, 183, 209),
    rgb(249, 202, 36), rgb(108, 92, 231), rgb(253, 121, 168),
    rgb(0, 184, 148), rgb(255, 159, 67)
]

KEYSETS = [
    {"left": "a", "right": "d", "jump": "w", "down": "s", "name": "WASD"},
    {"left": "arrowleft", "right": "arrowright", "jump": "arrowup", "down": "arrowdown", "name": "Arrows"},
    {"left": "j", "right": "l", "jump": "i", "down": "k", "name": "JIL"},
    {"left": "numpad4", "right": "numpad6", "jump": "numpad8", "down": "numpad5", "name": "Numpad"},
]

def onAppStart(app):
    print("platformer_multiplayer: onAppStart")
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 60
    
    app.world = World(width=2400, height=700)
    app.camera_x = 0
    app.camera_y = 0
    app.keys_held = set()
    app.paused = False
    app.show_help = True
    app.mode = "local"  # local or datastar
    app.datastar_url = "https://scs-datastar-extension.onrender.com"  # placeholder
    app.room_id = "DEMO"
    app.local_player_id = "player_0"
    app.input_seq = 0
    app.last_snapshot = None
    app.datastar_connected = False
    app.particles = []
    
    # Add initial players
    app.world.add_player("player_0", "You", PLAYER_COLORS[0], KEYSETS[0])
    app.world.add_player("player_1", "P2", PLAYER_COLORS[1], KEYSETS[1])
    
    app.background = gradient(rgb(15, 15, 30), rgb(30, 25, 50), start='top')
    
    # Try to detect datastar shell
    try:
        if hasattr(window, '__SCS_GAME_STATE'):
            app.mode = "datastar"
            app.datastar_connected = True
            print("Detected datastar shell, switching to datastar mode")
    except:
        pass
    
    # For online mode, try to fetch capabilities
    if HAS_FETCH:
        aio.run(try_connect_datastar(app))

async def try_connect_datastar(app):
    if not HAS_FETCH:
        return
    try:
        # This will fail if backend not deployed, that's fine - we stay local
        url = f"{app.datastar_url}/api/v1/capabilities"
        print(f"Trying datastar backend {url}")
        data = await fetch_json(url)
        print(f"Datastar backend capabilities: {data}")
        app.datastar_connected = True
        # If we have datastar.py extension, we can join room
        # For now just mark connected
    except Exception as e:
        print(f"Datastar backend not reachable (local mode): {e}")
        app.datastar_connected = False

def onKeyPress(app, key):
    key = key.lower()
    app.keys_held.add(key)
    
    if key == "r":
        for p in app.world.players.values():
            p.reset()
        for c in app.world.coins:
            c.collected = False
    elif key == "p":
        app.paused = not app.paused
    elif key == "h":
        app.show_help = not app.show_help
    elif key == "m":
        # Toggle mode
        app.mode = "datastar" if app.mode == "local" else "local"
    elif key == "c":
        # Spawn coin
        cx = random.randint(200, 2000)
        cy = random.randint(100, 500)
        app.world.coins.append(Coin(cx, cy))
    elif key in ("1", "2", "3", "4"):
        num = int(key)
        # Ensure that many players
        while len(app.world.players) < num:
            idx = len(app.world.players)
            if idx < len(PLAYER_COLORS):
                pid = f"player_{idx}"
                app.world.add_player(pid, f"P{idx+1}", PLAYER_COLORS[idx], KEYSETS[idx % len(KEYSETS)])
    elif key == "space":
        app.keys_held.add("space")

def onKeyRelease(app, key):
    key = key.lower()
    app.keys_held.discard(key)
    if key == " ":
        app.keys_held.discard("space")

def onStep(app):
    if app.paused:
        return
    
    app.input_seq += 1
    
    # Check for datastar snapshot (if in datastar shell)
    if app.mode == "datastar" and HAS_DATASTAR:
        snapshot = get_game_snapshot()
        if snapshot is not None:
            app.last_snapshot = snapshot
            app.datastar_connected = True
            # Apply snapshot to local rendering (interpolate)
            # Snapshot format: {entities: [{id, x, y, vx, vy, color, name, score, state}, ...], platforms, coins}
            try:
                # Update or create players from snapshot
                entities = snapshot.get("entities") if isinstance(snapshot, dict) else None
                if entities is None and hasattr(snapshot, 'get'):
                    entities = snapshot.get("entities")
                if entities:
                    for ent in entities:
                        eid = ent.get("id") if isinstance(ent, dict) else getattr(ent, 'id', None)
                        if eid not in app.world.players:
                            # Create ghost player
                            col = ent.get("color", "#ffffff") if isinstance(ent, dict) else getattr(ent, 'color', "#ffffff")
                            # Convert hex to rgb if needed
                            app.world.add_player(eid, ent.get("name", "Remote"), col, KEYSETS[0])
                        # Update position (lerp for smoothness)
                        if eid in app.world.players:
                            p = app.world.players[eid]
                            target_x = ent.get("x", p.x) if isinstance(ent, dict) else getattr(ent, 'x', p.x)
                            target_y = ent.get("y", p.y) if isinstance(ent, dict) else getattr(ent, 'y', p.y)
                            # Simple lerp
                            p.x = p.x * 0.6 + target_x * 0.4
                            p.y = p.y * 0.6 + target_y * 0.4
                            p.vx = ent.get("vx", 0) if isinstance(ent, dict) else getattr(ent, 'vx', 0)
                            p.vy = ent.get("vy", 0) if isinstance(ent, dict) else getattr(ent, 'vy', 0)
            except Exception as e:
                print(f"Snapshot apply error: {e}")
        # In datastar mode, we still handle local input and send via HTTP
        # For demo, we send input via extensions.datastar
        if HAS_FETCH and app.datastar_connected:
            # Find local player
            local = app.world.players.get(app.local_player_id)
            if local:
                move_x = 0
                if "a" in app.keys_held or "arrowleft" in app.keys_held:
                    move_x -= 1
                if "d" in app.keys_held or "arrowright" in app.keys_held:
                    move_x += 1
                jump = "w" in app.keys_held or "arrowup" in app.keys_held or " " in app.keys_held or "space" in app.keys_held
                # Apply locally immediately for responsiveness (client prediction)
                app.world.apply_input(app.local_player_id, move_x, jump)
                # Also send to server (fire and forget)
                # aio.run(send_input...) - we don't want to block onStep, so we use a trick: schedule via aio
                # For simplicity, we skip server send in this local demo version
                pass
        return
    
    # Local mode: direct input handling for all players
    for pid, player in app.world.players.items():
        keys = player.keys
        move_x = 0
        # Check both letter and arrow sets
        if keys["left"] in app.keys_held or (keys["left"] == "a" and "arrowleft" in app.keys_held):
            # Actually check more robustly
            pass
        # Simplified: player 0 uses WASD, player1 arrows, etc.
        if pid == "player_0":
            if "a" in app.keys_held:
                move_x -= 1
            if "d" in app.keys_held:
                move_x += 1
            jump = "w" in app.keys_held or " " in app.keys_held or "space" in app.keys_held
            down = "s" in app.keys_held
        elif pid == "player_1":
            if "arrowleft" in app.keys_held:
                move_x -= 1
            if "arrowright" in app.keys_held:
                move_x += 1
            jump = "arrowup" in app.keys_held or "arrowup" in app.keys_held
            down = "arrowdown" in app.keys_held
        elif pid == "player_2":
            if "j" in app.keys_held:
                move_x -= 1
            if "l" in app.keys_held:
                move_x += 1
            jump = "i" in app.keys_held
            down = "k" in app.keys_held
        elif pid == "player_3":
            if "numpad4" in app.keys_held:
                move_x -= 1
            if "numpad6" in app.keys_held:
                move_x += 1
            jump = "numpad8" in app.keys_held
            down = "numpad5" in app.keys_held
        else:
            # AI wander
            if app.world.tick % 120 == 0:
                move_x = random.choice([-1, 0, 1])
                jump = random.random() < 0.2
            else:
                move_x = 0
                jump = False
            down = False
        
        if pid in ("player_0", "player_1", "player_2", "player_3"):
            app.world.apply_input(pid, move_x, jump, app.input_seq)
    
    app.world.step()
    
    # Camera follows player 0
    if "player_0" in app.world.players:
        target_cam = app.world.players["player_0"].x - app.width//2
        app.camera_x = app.camera_x * 0.85 + target_cam * 0.15
        app.camera_x = clamp(app.camera_x, 0, app.world.width - app.width)
    
    # Update coins bob
    for coin in app.world.coins:
        coin.bob += 0.08
        coin.spin += 0.12

def draw_platform(app, plat, cam_x):
    x = plat.x - cam_x
    y = plat.y
    w = plat.w
    h = plat.h
    # Don't draw offscreen
    if x + w/2 < -100 or x - w/2 > app.width + 100:
        return
    
    if plat.type == "lava":
        fill = rgb(200, 50, 30)
        # Animated lava
        for i in range(3):
            drawRect(x, y + math.sin(app.world.tick*0.1 + i)*2, w, h//3, fill=fill, opacity=60 + i*15)
        drawRect(x, y, w, h, fill=fill, opacity=40)
    elif plat.type == "bouncy":
        drawRect(x, y, w, h, fill=rgb(100, 200, 100), roundness=6)
        drawLabel("BOUNCE", x, y, size=10, fill=rgb(20, 60, 20), bold=True)
    else:
        # Normal with shading
        drawRect(x, y+2, w, h, fill=rgb(20, 20, 35), roundness=4)
        drawRect(x, y, w, h, fill=plat.color, roundness=4)
        # Top highlight
        drawRect(x, y - h*0.3, w*0.9, h*0.2, fill=rgb(255,255,255), opacity=15, roundness=2)

def draw_player(app, player, cam_x):
    x = player.x - cam_x
    y = player.y
    
    if x < -100 or x > app.width + 100 or y < -100 or y > app.height + 100:
        return
    
    # Trail
    for i, (tx, ty) in enumerate(player.trail):
        tx_screen = tx - cam_x
        alpha = (i+1)/len(player.trail) * 30
        drawCircle(tx_screen, ty, 4 + i*0.5, fill=player.color, opacity=alpha)
    
    # Shadow
    drawOval(x, y+player.h*0.6, player.w*0.8, 8, fill=rgb(0,0,0), opacity=25)
    
    # Body
    body_w = player.w
    body_h = player.h
    
    # Squash/stretch based on state
    squash = 1.0
    if player.state == "jump":
        squash = 0.85
    elif player.state == "fall":
        squash = 1.15
    elif player.on_ground and abs(player.vx) > 1:
        squash = 0.9 + math.sin(app.world.tick*0.3)*0.05
    
    # Draw player rect
    drawRect(x, y, body_w, body_h*squash, fill=player.color, roundness=8)
    # Face direction indicator
    eye_x = x + player.facing*6
    drawCircle(eye_x, y-6, 5, fill=rgb(255,255,255))
    drawCircle(eye_x + player.facing*2, y-6, 2, fill=rgb(0,0,0))
    
    # Name
    drawLabel(player.name, x, y - body_h*0.7 - 12, size=11, fill=rgb(255,255,255), bold=True)
    # Score
    drawLabel(f"{player.score}", x, y - body_h*0.7 - 26, size=10, fill=rgb(200,200,255))

def redrawAll(app):
    # Background
    drawRect(0, 0, app.width, app.height, fill=app.background)
    
    # Parallax stars
    for i in range(40):
        sx = (i*137 % app.world.width - app.camera_x*0.2) % app.width
        sy = (i*237 % app.height*0.8)
        size = (i % 3) + 1
        opacity = 30 + (i % 40)
        drawCircle(sx, sy, size, fill=rgb(200, 200, 255), opacity=opacity)
    
    # Platforms
    for plat in app.world.platforms:
        draw_platform(app, plat, app.camera_x)
    
    # Coins
    for coin in app.world.coins:
        if coin.collected:
            continue
        cx = coin.x - app.camera_x
        cy = coin.y + math.sin(coin.bob)*6
        if cx < -50 or cx > app.width+50:
            continue
        # Coin glow
        drawCircle(cx, cy, 16, fill=rgb(255, 215, 0), opacity=30)
        drawCircle(cx, cy, 10, fill=rgb(255, 235, 100))
        drawLabel("$", cx, cy, size=12, fill=rgb(100, 80, 0), bold=True)
    
    # Players
    for pid, player in app.world.players.items():
        draw_player(app, player, app.camera_x)
    
    # UI - Top bar (Datastar island)
    drawRect(app.width//2, 22, app.width, 44, fill=rgb(0,0,0), opacity=60)
    
    mode_color = rgb(78, 205, 196) if app.mode == "datastar" else rgb(249, 202, 36)
    status_text = f"MODE: {app.mode.upper()} | ROOM: {app.room_id} | PLAYERS: {len(app.world.players)} | TICK: {app.world.tick}"
    if app.datastar_connected:
        status_text += " | DATASTAR: CONNECTED"
        conn_color = rgb(100, 255, 100)
    else:
        status_text += " | DATASTAR: LOCAL"
        conn_color = rgb(255, 200, 100)
    
    drawLabel(status_text, app.width//2, 14, size=11, fill=rgb(220, 220, 230))
    drawCircle(app.width - 20, 14, 6, fill=conn_color)
    
    # Scoreboard
    sorted_players = sorted(app.world.players.values(), key=lambda p: p.score, reverse=True)
    y = 50
    drawRect(90, y+20, 160, 20 + len(sorted_players)*18, fill=rgb(0,0,0), opacity=70, roundness=8)
    drawLabel("SCOREBOARD", 90, y, size=12, fill=rgb(255, 255, 255), bold=True)
    y += 18
    for p in sorted_players[:6]:
        drawLabel(f"{p.name}: {p.score}", 90, y, size=11, fill=p.color, bold=True)
        y += 18
    
    # Controls help
    if app.show_help:
        help_x = app.width - 160
        help_y = 80
        drawRect(help_x, help_y+60, 300, 140, fill=rgb(0,0,0), opacity=75, roundness=8)
        drawLabel("CONTROLS", help_x, help_y-20, size=12, fill=rgb(255,255,255), bold=True)
        drawLabel("P1 WASD + W/Space jump", help_x, help_y, size=10, fill=rgb(200,220,255))
        drawLabel("P2 Arrows + Up jump", help_x, help_y+16, size=10, fill=rgb(200,220,255))
        drawLabel("P3 J/L + I jump", help_x, help_y+32, size=10, fill=rgb(200,220,255))
        drawLabel("R reset  P pause  H help", help_x, help_y+48, size=10, fill=rgb(200,220,255))
        drawLabel("1-4 add players  C coin", help_x, help_y+64, size=10, fill=rgb(200,220,255))
        drawLabel("M toggle datastar/local", help_x, help_y+80, size=10, fill=rgb(180,200,255))
        drawLabel("Datastar: SSE patch_signals", help_x, help_y+96, size=9, fill=mode_color)
    
    # Datastar integration explanation
    drawRect(app.width//2, app.height-18, app.width, 36, fill=rgb(0,0,0), opacity=65)
    if app.mode == "datastar":
        drawLabel("Datastar: Server sends patch_signals({gameSnapshot}) via SSE | Brython reads window.__SCS_GAME_STATE | No WebSockets!", app.width//2, app.height-18, size=10, fill=rgb(120, 255, 180))
    else:
        drawLabel("Local Mode: Brython World.step() 60fps | Datastar would sync via SSE patch_signals | Press M to toggle | No WebSockets!", app.width//2, app.height-18, size=10, fill=rgb(255, 220, 120))
