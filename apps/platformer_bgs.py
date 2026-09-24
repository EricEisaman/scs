# apps/platformer_bgs.py
from scs import *
from browser import window, aio
import math, random

try:
    from extensions.multiplayer import MultiplayerClient
    from extensions.datastar import get_signal, is_datastar_connected
    HAS_MP = True
except Exception as e:
    print(f"mp import fail {e}")
    HAS_MP = False
    def get_signal(n,d=None): return d
    def is_datastar_connected(): return False

def clamp(v, lo, hi):
    if v < lo: return lo
    if v > hi: return hi
    return v

class Platform:
    def __init__(self, x, y, w, h, typ="normal", color=None):
        self.x=x; self.y=y; self.w=w; self.h=h
        self.type=typ
        self.color=color or rgb(60,60,80)

class Player:
    def __init__(self, pid, name, x, y, color, keys):
        self.id=pid; self.name=name; self.x=x; self.y=y
        self.vx=0; self.vy=0; self.w=32; self.h=44
        self.on_ground=False; self.facing=1; self.state="idle"
        self.color=color; self.keys=keys; self.trail=[]

class World:
    def __init__(self, width=2400, height=700):
        self.width=width; self.height=height
        self.gravity=0.65; self.friction=0.82
        self.platforms=[]; self.coins=[]; self.players={}; self.tick=0
        self.build_level()
    def build_level(self):
        self.platforms=[
            Platform(1200,680,2400,50,"normal",rgb(40,40,60)),
            Platform(250,580,180,18), Platform(500,520,180,18),
            Platform(750,460,200,18), Platform(1050,400,220,18),
            Platform(1350,360,200,18,"bouncy",rgb(100,200,100)),
            Platform(1650,420,180,18), Platform(1900,500,200,18),
            Platform(30,400,24,700), Platform(2370,400,24,700),
        ]
        self.coins=[{"x":250+i*140,"y":400-(i%3)*100,"collected":False} for i in range(10)]
    def add_player(self, pid, name, color, keys):
        p=Player(pid,name,150+len(self.players)*70,100,color,keys)
        self.players[pid]=p
        return p
    def apply_input(self, pid, move_x, jump):