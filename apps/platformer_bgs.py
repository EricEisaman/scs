# apps/platformer_bgs.py
# SCS Platformer using BGS-MP-SYNC Python API
# Well-designed Python API following Babylon Game Starter pattern

from scs import *
from browser import window, aio
import math
import random

try:
    from extensions.multiplayer import MultiplayerClient, CharacterState
    from extensions.fetch import fetch_json
    from extensions.datastar import get_signal, is_datastar_connected
    HAS_MP = True
except:
    HAS_MP = False
    def get_signal(n,d=None): return d
    def is_datastar_connected(): return False

# ---------- Physics ----------
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

class Platform:
    def __init__(self, x, y, w, h, typ="normal", color=None):
        self.x=x; self.y=y; self.w=w; self.h=h; self.type=typ; self.color=color or rgb(60,60,80)

class Player:
    def __init__(self, pid, name, x, y, color, keys):
        self.id=pid; self.name=name; self.x=x; self.y=y; self.vx=0; self.vy=0
        self.w=32; self.h=44; self.on_ground=False; self.facing=1; self.state="idle"
        self.color=color; self.keys=keys; self.score=0; self.jump_count=0; self.max_jumps=2
        self.coyote_timer=0; self.jump_buffer=0; self.alive=True; self.spawn_x=x; self.spawn_y=y; self.trail=[]

class World:
    def __init__(self, width=2400, height=700):
        self.width=width; self.height=height; self.gravity=0.65; self.friction=0.82
        self.platforms=[]; self.coins=[]; self.players={}; self.tick=0; self.build_level()
    def build_level(self):
        self.platforms=[
            Platform(1200,680,2400,50,"normal",rgb(40,40,60)),
            Platform(250,580,180,18,"normal"), Platform(500,520,180,18),
            Platform(750,460,200,18), Platform(1050,400,220,18),
            Platform(1350,360,200,18,"bouncy",rgb(100,200,100)),
            Platform(1650,420,180,18), Platform(1900,500,200,18),
            Platform(30,400,24,700), Platform(2370,400,24,700),
        ]
        self.coins=[{"x":250+i*140,"y":400-(i%3)*100,"collected":False,"val":10} for i in range(10)]
    def add_player(self, pid, name, color, keys):
        p=Player(pid,name,150+len(self.players)*70,100,color,keys)
        self.players[pid]=p; return p
    def apply_input(self, pid, move_x, jump):
        if pid not in self.players: return
        p=self.players[pid]
        if move_x!=0:
            p.vx=move_x*5.8; p.facing=move_x
            if p.on_ground: p.state="run"
        else:
            p.vx*=self.friction
            if abs(p.vx)<0.2: p.vx=0
        if jump and p.on_ground:
            p.vy=-13.2; p.on_ground=False; p.jump_count=1; p.state="jump"
        elif jump and p.jump_count<p.max_jumps:
            p.vy=-11.0; p.jump_count+=1
    def step(self):
        self.tick+=1
        for p in list(self.players.values()):
            if not p.on_ground:
                p.vy+=self.gravity
            p.x+=p.vx; p.y+=p.vy
            p.on_ground=False
            px1,py1=p.x-p.w/2,p.y-p.h/2
            px2,py2=p.x+p.w/2,p.y+p.h/2
            for plat in self.platforms:
                bx1,by1=plat.x-plat.w/2,plat.y-plat.h/2
                bx2,by2=plat.x+plat.w/2,plat.y+plat.h/2
                if px2<bx1 or px1>bx2 or py2<by1 or py1>by2: continue
                ox=min(px2,bx2)-max(px1,bx1)
                oy=min(py2,by2)-max(py1,by1)
                if ox<oy:
                    p.x=bx1-p.w/2-0.5 if p.x<plat.x else bx2+p.w/2+0.5
                    p.vx=0
                else:
                    if p.y<plat.y:
                        p.y=by1-p.h/2-0.5; p.vy=0; p.on_ground=True; p.jump_count=0
                        if plat.type=="bouncy": p.vy=-16; p.on_ground=False
                    else:
                        p.y=by2+p.h/2+0.5; p.vy=0
            if p.x<40: p.x=40
            if p.x>self.width-40: p.x=self.width-40
            if p.y>self.height+200:
                p.x,p.y,p.vx,p.vy=150,100,0,0
            # trail
            p.trail.append((p.x,p.y))
            if len(p.trail)>6: p.trail.pop(0)

# ---------- App State ----------
# Keymaps
KEYSETS=[
    {"left":"a","right":"d","jump":"w","down":"s"},
    {"left":"arrowleft","right":"arrowright","jump":"arrowup","down":"arrowdown"},
    {"left":"j","right":"l","jump":"i","down":"k"},
    {"left":"4","right":"6","jump":"8","down":"5"},
]
COLORS=[rgb(255,107,107),rgb(78,205,196),rgb(69,183,209),rgb(249,202,36),rgb(108,92,231),rgb(253,121,168)]

def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=60
    app.background=rgb(15,15,30)
    app.world=World()
    app.camera_x=0
    app.keys_held=set()
    app.show_help=True
    app.mode="bgs-multiplayer"
    app.room_id="level1"
    app.client_id=None
    app.mp_client=None
    app.datastar_connected=False
    app.remote_players={}  # clientId -> CharacterState dict
    app.authority={}  # instanceId -> ownerId

    # Add local players
    app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])

    # Setup BGS multiplayer if available
    if HAS_MP:
        # Use local backend or production
        base_url = "http://localhost:10000"
        try:
            if hasattr(window, 'location') and 'github.io' in window.location.hostname:
                base_url = "https://scs-207.onrender.com"
        except:
            pass
        app.mp_client = MultiplayerClient(base_url=base_url, environment="level1", character_name="Player")
        # Callbacks following BGS pattern
        def on_char_state(updates):
            # updates: list of CharacterState dicts
            for u in updates:
                cid = u.get("clientId")
                if cid and cid != app.client_id:
                    app.remote_players[cid] = u
        def on_item_auth(instanceId, prev, new, reason):
            app.authority[instanceId] = new
        if hasattr(app.mp_client, 'on_character_state'):
            app.mp_client.on_character_state = on_char_state
            app.mp_client.on_item_authority_changed = on_item_auth

        async def join_mp():
            try:
                res = await app.mp_client.join()
                app.client_id = res.get("client_id")
                app.room_id = "level1"
                print(f"[BGS] Joined {app.client_id} sync={res.get('is_synchronizer')}")
            except Exception as e:
                print(f"[BGS] Join failed {e}")
        aio.run(join_mp())

def onKeyPress(app, key):
    if key=='r':
        app.world=World()
        app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])
    if key=='p': app.paused=not getattr(app,'paused',False)
    if key=='h': app.show_help=not app.show_help
    if key=='1' and len(app.world.players)<8:
        idx=len(app.world.players)
        app.world.add_player(f"local_{idx}",f"P{idx+1}",COLORS[idx%len(COLORS)],KEYSETS[idx%len(KEYSETS)])
    if key=='c':
        app.world.coins.append({"x":random.randint(100,2000),"y":random.randint(100,400),"collected":False,"val":10})

def onKeyHold(app, keys):
    app.keys_held=set(keys)
    # Local input -> world
    for pid, p in app.world.players.items():
        km=p.keys
        move_x=0
        if km["left"] in app.keys_held: move_x-=1
        if km["right"] in app.keys_held: move_x+=1
        jump=km["jump"] in app.keys_held
        app.world.apply_input(pid, move_x, jump)

    # BGS: send character-state
    if app.mp_client and app.client_id and "local_0" in app.world.players:
        lp=app.world.players["local_0"]
        async def send():
            try:
                await app.mp_client.send_character_state(
                    position=[lp.x, lp.y],
                    velocity=[lp.vx, lp.vy],
                    animationState=lp.state,
                    facing=lp.facing,
                    onGround=lp.on_ground,
                    score=lp.score
                )
            except Exception as e:
                print(f"send char error {e}")
        aio.run(send())

def onStep(app):
    # Check datastar signals for remote players
    if HAS_MP:
        try:
            sig = get_signal("character-state-update")
            if sig and isinstance(sig, dict):
                updates=sig.get("updates",[])
                for u in updates:
                    cid=u.get("clientId")
                    if cid and cid!=app.client_id:
                        app.remote_players[cid]=u
            # Also check env authority
            app.datastar_connected=is_datastar_connected()
        except:
            pass

    app.world.step()
    if "local_0" in app.world.players:
        target=app.world.players["local_0"].x-app.width//2
        app.camera_x=app.camera_x*0.85+target*0.15
        app.camera_x=clamp(app.camera_x,0,app.world.width-app.width)
    for coin in app.world.coins:
        if not isinstance(coin, dict): continue
        # simple bob

def redrawAll(app):
    drawRect(0,0,app.width,app.height,fill=app.background)
    # stars
    for i in range(30):
        sx=(i*137%app.world.width-app.camera_x*0.2)%app.width
        sy=(i*237%app.height*0.8)
        drawCircle(sx,sy,(i%3)+1,fill=rgb(200,200,255),opacity=30+(i%40))
    # platforms
    for plat in app.world.platforms:
        x=plat.x-app.camera_x; y=plat.y
        if x+plat.w/2<-100 or x-plat.w/2>app.width+100: continue
        if plat.type=="bouncy":
            drawRect(x,y,plat.w,plat.h,fill=rgb(100,200,100),roundness=6)
        else:
            drawRect(x,y+2,plat.w,plat.h,fill=rgb(20,20,35),roundness=4)
            drawRect(x,y,plat.w,plat.h,fill=plat.color,roundness=4)
    # coins
    for c in app.world.coins:
        if c.get("collected"): continue
        cx=c["x"]-app.camera_x; cy=c["y"]
        drawCircle(cx,cy,10,fill=rgb(255,235,100))
        drawLabel("$",cx,cy,size=12,fill=rgb(100,80,0),bold=True)
    # local players
    for pid, p in app.world.players.items():
        x=p.x-app.camera_x; y=p.y
        for i,(tx,ty) in enumerate(p.trail):
            drawCircle(tx-app.camera_x,ty,3+i*0.5,fill=p.color,opacity=(i+1)/len(p.trail)*30)
        drawRect(x,y,p.w,p.h*0.9,fill=p.color,roundness=8)
        eye_x=x+p.facing*6
        drawCircle(eye_x,y-6,5,fill=rgb(255,255,255))
        drawCircle(eye_x+p.facing*2,y-6,2,fill=rgb(0,0,0))
        drawLabel(p.name,x,y-p.h*0.7-12,size=11,fill=rgb(255,255,255),bold=True)
    # remote players (BGS character-state)
    for cid, remote in app.remote_players.items():
        pos=remote.get("position",[0,0])
        x=pos[0]-app.camera_x; y=pos[1] if len(pos)>1 else 0
        if x<-100 or x>app.width+100: continue
        state=remote.get("animationState","idle")
        drawRect(x,y,32,44,fill=rgb(180,180,255),opacity=80,roundness=8)
        drawLabel(f"{cid[:4]} {state}",x,y-40,size=9,fill=rgb(200,200,255))
        drawCircle(x,y-6,4,fill=rgb(255,255,255))

    # UI - BGS status
    drawRect(app.width//2,22,app.width,44,fill=rgb(0,0,0),opacity=60)
    mode_color=rgb(78,205,196) if app.datastar_connected else rgb(249,202,36)
    status=f"BGS-MP-SYNC | ENV: {app.room_id} | LOCAL: {len(app.world.players)} | REMOTE: {len(app.remote_players)} | TICK: {app.world.tick}"
    if app.datastar_connected: status+=" | DATASTAR: CONNECTED"
    else: status+=" | LOCAL DEMO"
    drawLabel(status,app.width//2,14,size=11,fill=rgb(220,220,230))
    drawCircle(app.width-20,14,6,fill=rgb(100,255,100) if app.datastar_connected else rgb(255,200,100))

    # Scoreboard + BGS authority
    y=50
    drawRect(90,y+20,160,20+len(app.world.players)*18,fill=rgb(0,0,0),opacity=70,roundness=8)
    drawLabel("LOCAL",90,y,size=12,fill=rgb(255,255,255),bold=True)
    y+=18
    for p in list(app.world.players.values())[:6]:
        drawLabel(f"{p.name}: {p.score}",90,y,size=11,fill=p.color,bold=True); y+=18

    if app.remote_players:
        y+=10
        drawRect(90,y+10,160,10+len(app.remote_players)*16,fill=rgb(0,0,0),opacity=60,roundness=8)
        drawLabel("REMOTE (BGS)",90,y,size=11,fill=rgb(180,200,255),bold=True); y+=14
        for cid, r in list(app.remote_players.items())[:6]:
            drawLabel(f"{cid[:6]}",90,y,size=10,fill=rgb(180,180,255)); y+=16

    if app.show_help:
        hx=app.width-160; hy=80
        drawRect(hx,hy+60,300,140,fill=rgb(0,0,0),opacity=75,roundness=8)
        drawLabel("BGS CONTROLS",hx,hy-20,size=12,fill=rgb(255,255,255),bold=True)
        drawLabel("WASD / Arrows move",hx,hy,size=10,fill=rgb(200,220,255))
        drawLabel("R reset P pause 1 add",hx,hy+16,size=10,fill=rgb(200,220,255))
        drawLabel("BGS API: MultiplayerClient",hx,hy+32,size=10,fill=rgb(78,205,196))
        drawLabel("PATCH char-state + SSE",hx,hy+48,size=10,fill=rgb(78,205,196))
        drawLabel("Env-authority + item-claim",hx,hy+64,size=10,fill=rgb(78,205,196))

    drawRect(app.width//2,app.height-18,app.width,36,fill=rgb(0,0,0),opacity=65)
    drawLabel("BGS-MP-SYNC Python: PATCH /api/multiplayer/character-state + SSE character-state-update | Datastar patch_signals | No WebSockets",app.width//2,app.height-18,size=9,fill=rgb(120,255,180))