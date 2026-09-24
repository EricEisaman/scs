from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import math

@dataclass
class Platform:
    x: float
    y: float
    w: float
    h: float
    type: str = "normal"

@dataclass
class PlayerState:
    id: str
    name: str
    x: float
    y: float
    vx: float = 0
    vy: float = 0
    w: float = 32
    h: float = 44
    on_ground: bool = False
    facing: int = 1
    state: str = "idle"
    color: str = "#ff6b6b"
    score: int = 0
    jump_count: int = 0
    max_jumps: int = 2
    last_input_seq: int = 0

class World:
    def __init__(self, width: int = 2400, height: int = 700):
        self.width = width
        self.height = height
        self.gravity = 0.65
        self.friction = 0.82
        self.players: Dict[str, PlayerState] = {}
        self.platforms: List[Platform] = []
        self.coins: List[Dict] = []
        self.tick = 0
        self._build_level()

    def _build_level(self):
        self.platforms = [
            Platform(1200, 680, 2400, 50, "normal"),
            Platform(250, 580, 180, 18),
            Platform(500, 520, 180, 18),
            Platform(750, 460, 200, 18),
            Platform(1050, 400, 220, 18),
            Platform(1350, 360, 200, 18, "bouncy"),
            Platform(1650, 420, 180, 18),
            Platform(1900, 500, 200, 18),
            Platform(600, 300, 120, 16),
            Platform(1100, 200, 160, 16),
            Platform(30, 400, 24, 700),
            Platform(2370, 400, 24, 700),
        ]
        self.coins = [{"id": f"coin_{i}", "x": 250 + i*140, "y": 400 - (i%3)*100, "collected": False} for i in range(12)]

    def add_player(self, player_id: str, name: str, color: str = "#ff6b6b") -> PlayerState:
        spawn_x = 150 + len(self.players)*70
        p = PlayerState(id=player_id, name=name[:20], x=spawn_x, y=100, color=color)
        self.players[player_id] = p
        return p

    def remove_player(self, player_id: str):
        self.players.pop(player_id, None)

    def apply_input(self, player_id: str, move_x: int, jump: bool, seq: int):
        p = self.players.get(player_id)
        if not p:
            return
        p.last_input_seq = seq
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
        if jump:
            if p.on_ground:
                p.vy = -13.2
                p.on_ground = False
                p.jump_count = 1
                p.state = "jump"
            elif p.jump_count < p.max_jumps:
                p.vy = -11.0
                p.jump_count += 1

    def _aabb(self, ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
        return not (ax2 < bx1 or ax1 > bx2 or ay2 < by1 or ay1 > by2)

    def step(self):
        self.tick += 1
        for p in list(self.players.values()):
            if not p.on_ground:
                p.vy += self.gravity
                if p.vy > 14:
                    p.vy = 14
            p.x += p.vx
            p.y += p.vy

            # collisions
            p.on_ground = False
            px1, py1 = p.x - p.w/2, p.y - p.h/2
            px2, py2 = p.x + p.w/2, p.y + p.h/2
            for plat in self.platforms:
                bx1, by1 = plat.x - plat.w/2, plat.y - plat.h/2
                bx2, by2 = plat.x + plat.w/2, plat.y + plat.h/2
                if not self._aabb(px1, py1, px2, py2, bx1, by1, bx2, by2):
                    continue
                ox = min(px2, bx2) - max(px1, bx1)
                oy = min(py2, by2) - max(py1, by1)
                if ox < oy:
                    p.x = bx1 - p.w/2 - 0.5 if p.x < plat.x else bx2 + p.w/2 + 0.5
                    p.vx = 0
                else:
                    if p.y < plat.y:
                        p.y = by1 - p.h/2 - 0.5
                        p.vy = 0
                        p.on_ground = True
                        p.jump_count = 0
                        if plat.type == "bouncy":
                            p.vy = -16
                            p.on_ground = False
                    else:
                        p.y = by2 + p.h/2 + 0.5
                        p.vy = 0

            if p.x < 40: p.x = 40
            if p.x > self.width - 40: p.x = self.width - 40
            if p.y > self.height + 200:
                p.x, p.y, p.vx, p.vy = p.x, 100, 0, 0
                p.score = max(0, p.score - 10)

    def get_snapshot(self):
        return {
            "entities": [
                {"id": p.id, "x": p.x, "y": p.y, "vx": p.vx, "vy": p.vy,
                 "state": p.state, "color": p.color, "name": p.name,
                 "score": p.score, "onGround": p.on_ground, "facing": p.facing}
                for p in self.players.values()
            ],
            "platforms": [{"x": pl.x, "y": pl.y, "w": pl.w, "h": pl.h, "type": pl.type} for pl in self.platforms],
            "coins": [c for c in self.coins if not c.get("collected")],
            "serverTick": self.tick
        }