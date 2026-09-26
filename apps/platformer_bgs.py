# apps/platformer_bgs.py - v0.1.17 MUST USE MULTIPLAYER EXTENSION
# Version: 0.1.17 - MUST ALWAYS USE extensions.multiplayer - NO FALLBACK
# SCS purpose: enable cmu_graphics users to quickly add extension modules
# This app demonstrates proper use of extensions.multiplayer + extensions.datastar

from scs import *
from browser import window, aio

# MUST ALWAYS USE multiplayer extension - import from extensions system
# https://github.com/EricEisaman/scs/tree/main - extensions/
from extensions.multiplayer import MultiplayerClient
from extensions.datastar import get_signal, is_connected as is_datastar_connected, attach_to_eventsource
from extensions.fetch import fetch_json  # fetch_demo safe, keep import working

__version__ = "0.1.17"
__build__ = "2026-09-26-v0.1.17-must-use-mp-extension"

try:
    window.console.log("[BGS] platformer_bgs.py version " + __version__ + " build " + __build__ + " - MUST USE extensions.multiplayer")
except:
    print("[BGS] version " + __version__)

import math
import random

# NO FALLBACK ALLOWED - if import above fails, app will error, which is correct per spec
# The entire purpose of SCS system is to enable extension modules
MULTIPLAYER_ENABLED = True

class RemoteVisual:
    def __init__(self, clientId, color):
        self.clientId = clientId
        self.color = color
        self.trail = []
        self.facing = 1
        self.last_px = None
        self.last_py = None
        self.blink_phase = random.random()*6.28
        self.is_blinking = False
        self.last_seen = 0
        self.prev_pos = None
        self.target_pos = None
        self.interp_t = 0.0

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

class Platform:
    def __init__(self, x, y, w, h, typ="normal", color=None):
        self.x=float(x); self.y=float(y); self.w=float(w); self.h=float(h); self.type=typ; self.color=color or rgb(60,60,80)

class Player:
    def __init__(self, pid, name, x, y, color, keys):
        self.id=pid; self.name=name; self.x=float(x); self.y=float(y); self.vx=0.0; self.vy=0.0
        self.w=32; self.h=44; self.on_ground=False; self.facing=1; self.state="idle"
        self.color=color; self.keys=keys; self.score=0; self.jump_count=0; self.max_jumps=2
        self.coyote_timer=0; self.jump_buffer=0; self.spawn_x=float(x); self.spawn_y=float(y)
        self.trail=[]; self.coin_flash=0
        self.anim_phase=0.0
        self.last_trail_x=None; self.last_trail_y=None

class World:
    def __init__(self, width=2400, height=700):
        self.width=width; self.height=height; self.gravity=0.65; self.friction=0.82
        self.platforms=[]; self.coins=[]; self.players={}; self.tick=0; self.build_level()
    def build_level(self):
        self.platforms=[
            Platform(1200,680,2400,50,"normal",rgb(40,40,60)),
            Platform(250,580,180,18,"normal",rgb(80,80,110)),
            Platform(500,520,180,18,"normal",rgb(80,80,110)),
            Platform(750,460,200,18,"normal",rgb(80,80,110)),
            Platform(1050,400,220,18,"normal",rgb(80,80,110)),
            Platform(1350,360,200,18,"bouncy",rgb(100,200,100)),
            Platform(1650,420,180,18,"normal",rgb(80,80,110)),
            Platform(1900,500,200,18,"normal",rgb(80,80,110)),
            Platform(2100,350,160,18,"normal",rgb(80,80,110)),
            Platform(30,400,24,700,"wall",rgb(50,50,70)),
            Platform(2370,400,24,700,"wall",rgb(50,50,70)),
        ]
        self.coins=[]
        for plat in self.platforms:
            if plat.type=="wall" or plat.w>1000: continue
            self.coins.append({
                "id": "coin_" + str(len(self.coins)),
                "instanceId": "coin_" + str(len(self.coins)),
                "x":float(plat.x),"y":float(plat.y-50),
                "collected":False,"collectedBy":None,"val":10,"bob":random.random()*6.28,
                "pos": [float(plat.x), float(plat.y-50), 0.0],
                "rot": [0.0,0.0,0.0,1.0],
                "isCollected": False
            })
        extras=[(400,300),(900,300),(1200,250),(1800,280)]
        for ex,ey in extras:
            self.coins.append({
                "id": "coin_" + str(len(self.coins)),
                "instanceId": "coin_" + str(len(self.coins)),
                "x":float(ex),"y":float(ey),
                "collected":False,"collectedBy":None,"val":10,"bob":random.random()*6.28,
                "pos": [float(ex), float(ey), 0.0],
                "rot": [0.0,0.0,0.0,1.0],
                "isCollected": False
            })
    def add_player(self, pid, name, color, keys):
        p=Player(pid,name,150+len(self.players)*70,100,color,keys); self.players[pid]=p; return p
    def apply_input(self, pid, move_x, jump_pressed, jump_just_pressed=False):
        if pid not in self.players: return
        p=self.players[pid]
        if move_x!=0:
            p.vx=move_x*5.8; p.facing=move_x
            if p.on_ground: p.state="run"
            else: p.state="jump" if p.vy<0 else "fall"
        else:
            p.vx*=self.friction
            if abs(p.vx)<0.2: p.vx=0
            if p.on_ground: p.state="idle"
        if p.on_ground: p.coyote_timer=6
        else: p.coyote_timer=max(0, p.coyote_timer-1)
        if jump_just_pressed:
            p.jump_buffer=6
        else:
            p.jump_buffer=max(0, p.jump_buffer-1)
        if p.jump_buffer>0 and p.coyote_timer>0:
            p.vy=-13.2; p.on_ground=False; p.jump_count=1; p.state="jump"; p.jump_buffer=0; p.coyote_timer=0
        elif jump_just_pressed and p.jump_count<p.max_jumps and p.jump_count>0 and p.jump_buffer>0:
            p.vy=-11.0; p.jump_count+=1; p.state="jump"; p.jump_buffer=0
    def step(self, app_ref=None):
        self.tick+=1
        for p in list(self.players.values()):
            if not p.on_ground: p.vy+=self.gravity
            p.x+=p.vx; p.y+=p.vy; p.on_ground=False
            p.anim_phase = (p.anim_phase + 0.05) % 1.0
            px1,py1=p.x-p.w/2,p.y-p.h/2; px2,py2=p.x+p.w/2,p.y+p.h/2
            for plat in self.platforms:
                bx1,by1=plat.x-plat.w/2,plat.y-plat.h/2; bx2,by2=plat.x+plat.w/2,plat.y+plat.h/2
                if px2<bx1 or px1>bx2 or py2<by1 or py1>by2: continue
                ox=min(px2,bx2)-max(px1,bx1); oy=min(py2,by2)-max(py1,by1)
                if ox<oy:
                    p.x=bx1-p.w/2-0.5 if p.x<plat.x else bx2+p.w/2+0.5; p.vx=0
                else:
                    if p.y<plat.y:
                        p.y=by1-p.h/2-0.5; p.vy=0; p.on_ground=True; p.jump_count=0
                        if plat.type=="bouncy": p.vy=-16; p.on_ground=False; p.state="jump"
                    else: p.y=by2+p.h/2+0.5; p.vy=0
            if p.x<40: p.x=40
            if p.x>self.width-40: p.x=self.width-40
            if p.y>self.height+200: p.x,p.y,p.vx,p.vy=p.spawn_x,p.spawn_y,0,0
            try:
                facing = int(p.facing) if p.facing!=0 else 1
                trail_x = float(p.x) - float(facing) * (float(p.w) * 0.5)
                trail_y = float(p.y) + float(p.h) * 0.2
                is_moving = abs(float(p.vx)) > 0.5 or abs(float(p.vy)) > 0.5
                add = False
                if is_moving:
                    if p.last_trail_x is None:
                        add = True
                    else:
                        dx = trail_x - p.last_trail_x
                        dy = trail_y - p.last_trail_y
                        if math.hypot(dx, dy) >= 3.0:
                            add = True
                else:
                    if len(p.trail) > 0:
                        p.trail.pop(0)
                        if len(p.trail) > 0:
                            p.trail.pop(0)
                    add = False
                if add:
                    p.trail.append((trail_x, trail_y))
                    p.last_trail_x = trail_x
                    p.last_trail_y = trail_y
            except:
                if abs(float(p.vx)) > 0.5 or abs(float(p.vy)) > 0.5:
                    p.trail.append((float(p.x), float(p.y)))
            if len(p.trail)>18: p.trail.pop(0)
            if p.coin_flash>0: p.coin_flash-=1
            if app_ref:
                for coin in app_ref.world.coins:
                    if coin.get("collected") or coin.get("isCollected"): continue
                    try: dx=float(p.x)-float(coin["x"]); dy=float(p.y)-float(coin["y"])
                    except: continue
                    if abs(dx)<22 and abs(dy)<28:
                        coin["collected"]=True
                        coin["isCollected"]=True
                        coin["collectedBy"]=p.id
                        p.score+=coin.get("val",10)
                        p.coin_flash=10
                        if app_ref:
                            app_ref.local_collected_coins.add(coin["id"])
                            app_ref.coin_seq = getattr(app_ref, 'coin_seq', 0) + 1
        for coin in self.coins:
            if not isinstance(coin, dict): continue
            coin["bob"]+=0.08
            coin["pos"] = [float(coin["x"]), float(coin["y"]), 0.0]

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
    app.world=World(); app.camera_x=0.0; app.keys_held=set(); app.prev_keys_held=set(); app.show_help=True
    app.mode="bgs-multiplayer"; app.room_id="level1"; app.client_id=None; app.mp_client=None
    app.datastar_connected=False; app.remote_players={}; app.remote_visuals={}
    app.last_send_ms=0; app.enable_trails=True; app.trail_length=20
    app.local_collected_coins=set()
    app.is_host=False
    app.seq=0
    app.coin_seq=0
    app.last_fetch_inflight=False
    app.has_opacity=False
    app.authority={}
    try:
        drawCircle(0,0,1,fill=rgb(255,255,255), opacity=50)
        app.has_opacity=True
    except:
        app.has_opacity=False
    app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])
    # MUST USE extensions.multiplayer extension - NO FALLBACK
    base_url="https://scs-207.onrender.com"
    try:
        if hasattr(window, 'location') and 'localhost' in window.location.hostname:
            base_url="http://localhost:10000"
    except:
        pass
    app.mp_client=MultiplayerClient(base_url=base_url, environment_name="level1", character_name="Player")
    async def join_mp():
        try:
            res=await app.mp_client.join()
            cid=res.get("client_id")
            is_sync=res.get("is_synchronizer", False)
            app.client_id=cid
            app.is_host=is_sync
            try:
                window.console.log("[BGS] Joined " + str(app.client_id) + " host=" + str(app.is_host) + " via extensions.multiplayer - MUST USE MP")
            except:
                pass
            try:
                if hasattr(app.mp_client, '_es') and app.mp_client._es:
                    attach_to_eventsource(app.mp_client._es)
            except:
                pass
        except Exception as e:
            try:
                window.console.error("[BGS] Join failed - NO FALLBACK, MUST USE MP EXTENSION", e)
            except:
                print("[BGS] Join failed " + str(e))
    aio.run(join_mp())

def onKeyPress(app, key):
    if key=='r':
        app.world=World(); app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])
        app.remote_players.clear(); app.remote_visuals.clear(); app.local_collected_coins.clear()
        app.authority.clear()
        app.seq=0; app.coin_seq=0; app.camera_x=0.0
        try:
            window._bgs_signals.clear()
        except:
            pass
    if key=='p': app.paused=not getattr(app,'paused',False)
    if key=='h': app.show_help=not app.show_help
    if key=='g': app.enable_trails=not app.enable_trails
    if key=='1' and len(app.world.players)<4:
        idx=len(app.world.players)
        app.world.add_player("local_" + str(idx),"P" + str(idx+1),COLORS[idx%len(COLORS)],KEYSETS[idx%len(KEYSETS)])
    if key=='c':
        x = float(random.randint(100,2000))
        y = float(random.randint(100,400))
        new_id="coin_" + str(len(app.world.coins))
        app.world.coins.append({
            "id":new_id,"instanceId":new_id,
            "x":x,"y":y,
            "collected":False,"isCollected":False,"collectedBy":None,"val":10,"bob":random.random()*6.28,
            "pos":[x, y, 0.0],
            "rot":[0.0,0.0,0.0,1.0]
        })

def onKeyHold(app, keys):
    app.prev_keys_held = getattr(app, 'keys_held', set())
    app.keys_held=set(keys)
    for pid, p in app.world.players.items():
        km=p.keys; move_x=0
        if km["left"] in app.keys_held: move_x-=1
        if km["right"] in app.keys_held: move_x+=1
        jump_held=km["jump"] in app.keys_held
        jump_just_pressed = jump_held and (km["jump"] not in app.prev_keys_held)
        app.world.apply_input(pid, move_x, jump_held, jump_just_pressed)

def onStep(app):
    try:
        sig=get_signal("character-state-update")
        if sig and isinstance(sig, dict):
            updates = sig.get("updates", [])
            for u in updates:
                if not isinstance(u, dict): continue
                cid=u.get("clientId")
                if cid and cid != app.client_id:
                    now_tick = app.world.tick
                    if cid in app.remote_players:
                        old_seq = app.remote_players[cid].get("seq", -1)
                        new_seq = u.get("seq", 0)
                        if new_seq < old_seq:
                            continue
                    app.remote_players[cid]=u
                    if cid not in app.remote_visuals:
                        try:
                            h = sum(ord(c) for c in cid) % len(COLORS)
                            col = COLORS[h]
                        except:
                            col = rgb(120,180,255)
                        app.remote_visuals[cid]=RemoteVisual(clientId=cid, color=col)
                    vis = app.remote_visuals.get(cid)
                    if vis:
                        vis.last_seen = now_tick
                    remote_coins = u.get("collectedCoins", [])
                    if remote_coins:
                        for rc_id in remote_coins:
                            for coin in app.world.coins:
                                if (coin["id"]==rc_id or coin["instanceId"]==rc_id) and not coin.get("collected"):
                                    coin["collected"]=True
                                    coin["isCollected"]=True
                                    coin["collectedBy"]=cid
        app.datastar_connected=is_datastar_connected()
        try:
            now = app.world.tick
            to_remove = []
            for cid, vis in app.remote_visuals.items():
                if now - getattr(vis, 'last_seen', 0) > 300:
                    to_remove.append(cid)
            for cid in to_remove:
                if cid in app.remote_players:
                    del app.remote_players[cid]
                if cid in app.remote_visuals:
                    del app.remote_visuals[cid]
        except:
            pass
    except Exception as e:
        try:
            window.console.error("[BGS] onStep signal handling failed", e)
        except:
            pass
    app.world.step(app_ref=app)

    for cid, remote in list(app.remote_players.items()):
        vis = app.remote_visuals.get(cid)
        if not vis:
            try:
                h = sum(ord(c) for c in cid) % len(COLORS)
                col = COLORS[h]
            except:
                col = rgb(120,180,255)
            vis = RemoteVisual(clientId=cid, color=col)
            app.remote_visuals[cid]=vis
        pos = remote.get("position"); vel = remote.get("velocity", [0,0,0])
        rot = remote.get("rotation", [0,0,0])
        if not pos or len(pos)<2: continue
        try:
            px = float(pos[0]); py = float(pos[1])
            vx = float(vel[0]) if len(vel)>0 else 0.0
            yaw = float(rot[1]) if len(rot)>1 else 0.0
            if vis.target_pos is None:
                vis.target_pos = (px, py)
                vis.prev_pos = (px, py)
                vis.interp_t = 1.0
            else:
                if abs(px - vis.target_pos[0]) > 0.1 or abs(py - vis.target_pos[1]) > 0.1:
                    vis.prev_pos = vis.target_pos
                    vis.target_pos = (px, py)
                    vis.interp_t = 0.0
            vis.interp_t = min(1.0, vis.interp_t + 0.2)
            if vis.prev_pos and vis.target_pos:
                lerp_px = vis.prev_pos[0] + (vis.target_pos[0] - vis.prev_pos[0]) * vis.interp_t
                lerp_py = vis.prev_pos[1] + (vis.target_pos[1] - vis.prev_pos[1]) * vis.interp_t
                px, py = lerp_px, lerp_py
            if abs(vx) > 0.3:
                vis.facing = 1 if vx > 0 else -1
            else:
                vis.facing = 1 if abs(yaw) < 1.5 else -1
        except:
            continue
        try:
            facing = int(vis.facing) if vis.facing!=0 else 1
            trail_x = px - float(facing) * 15.0
            trail_y = py + 10.0
            try:
                vx = float(vel[0]) if 'vel' in locals() else 0
                vy = float(vel[1]) if 'vel' in locals() else 0
                is_moving = abs(vx) > 0.5 or abs(vy) > 0.5
            except:
                is_moving = True
            should_add = False
            if is_moving:
                if vis.last_px is None:
                    should_add = True
                else:
                    dist = math.hypot(trail_x - vis.last_px, trail_y - vis.last_py) if vis.last_px is not None else 999
                    if dist > 3.0:
                        should_add = True
            else:
                if len(vis.trail) > 0:
                    vis.trail.pop(0)
                    if len(vis.trail) > 0:
                        vis.trail.pop(0)
            if should_add:
                vis.trail.append((trail_x, trail_y))
                vis.last_px = trail_x
                vis.last_py = trail_y
        except:
            if len(vis.trail) < app.trail_length:
                vis.trail.append((px, py))
        if len(vis.trail) > app.trail_length: 
            vis.trail.pop(0)
        vis.blink_phase += 0.05
        try:
            stable_hash = sum(ord(c) for c in cid) % 60
            vis.is_blinking = (app.world.tick + stable_hash) % 120 == 0
        except:
            vis.is_blinking = False

    if "local_0" in app.world.players:
        try:
            target=float(app.world.players["local_0"].x)-float(app.width)//2
            app.camera_x=float(app.camera_x)*0.85+float(target)*0.15
            app.camera_x=clamp(app.camera_x,0,float(app.world.width-app.width))
        except:
            pass

    # 60Hz networking - MUST USE extensions.multiplayer extension
    if app.mp_client and app.client_id and "local_0" in app.world.players:
        now=0
        try: now=int(window.Date.now())
        except: now=app.world.tick*16
        if now - app.last_send_ms > 16 and not app.last_fetch_inflight:
            app.last_send_ms=now
            app.seq+=1
            lp=app.world.players["local_0"]
            try:
                payload = {
                    "updates":[{
                        "clientId": str(app.client_id),
                        "characterModelId": "platformer_default",
                        "position": [float(lp.x), float(lp.y), 0.0],
                        "velocity": [float(lp.vx), float(lp.vy), 0.0],
                        "animationState": str(lp.state),
                        "animationFrame": float(lp.anim_phase),
                        "isJumping": bool(not lp.on_ground),
                        "isBoosting": False,
                        "boostTimeRemaining": 0.0,
                        "timestamp": int(window.Date.now()) if hasattr(window, 'Date') else app.world.tick,
                        "collectedCoins": list(app.local_collected_coins),
                        "score": int(lp.score),
                        "seq": int(app.seq)
                    }],
                    "timestamp": int(window.Date.now()) if hasattr(window, 'Date') else app.world.tick
                }
                url = app.mp_client.base_url + "/api/multiplayer/character-state"
                body_str = window.JSON.stringify(payload)
                opts = {"method":"PATCH","headers":{"Content-Type":"application/json","X-Client-ID":str(app.client_id)},"body":body_str}
                try:
                    js_opts = window.JSON.parse(window.JSON.stringify(opts))
                except:
                    js_opts = opts
                app.last_fetch_inflight=True
                async def do_fetch():
                    try:
                        resp = await window.fetch(url, js_opts)
                    except:
                        pass
                    finally:
                        app.last_fetch_inflight=False
                aio.run(do_fetch())
            except:
                app.last_fetch_inflight=False

def drawTrail(trail, color, camera_x, is_local=False, facing=1, has_opacity=True):
    if not trail or len(trail)==0:
        return
    if len(trail) >= 2:
        try:
            total_dist = 0
            for j in range(len(trail)-1):
                total_dist += math.hypot(trail[j+1][0]-trail[j][0], trail[j+1][1]-trail[j][1])
            if total_dist < 3.0:
                return
        except:
            pass
    for i in range(len(trail)):
        try:
            tx = float(trail[i][0]); ty = float(trail[i][1])
            x = tx - float(camera_x); y = ty
        except: continue
        t = i / max(1, len(trail)-1)
        opacity = t * 75
        size = 1.5 + t * 3.5
        try:
            if has_opacity:
                if is_local:
                    drawCircle(x, y, size, fill=color, opacity=opacity)
                    if t > 0.6:
                        drawCircle(x, y, size*0.5, fill=rgb(255,255,180), opacity=opacity*0.9)
                else:
                    drawCircle(x, y, size, fill=color, opacity=opacity)
                    if t > 0.5:
                        drawCircle(x, y, size*0.35, fill=rgb(255,255,255), opacity=opacity*0.8)
            else:
                drawCircle(x, y, size, fill=color)
        except:
            try:
                drawCircle(x, y, size, fill=color)
            except:
                pass
    for i in range(len(trail)-1):
        try:
            tx1 = float(trail[i][0]); ty1 = float(trail[i][1])
            tx2 = float(trail[i+1][0]); ty2 = float(trail[i+1][1])
            x1 = tx1 - float(camera_x); y1 = ty1; x2 = tx2 - float(camera_x); y2 = ty2
        except: continue
        t = i / max(1, len(trail)-1)
        if math.hypot(x2-x1, y2-y1) < 0.1:
            continue
        width = 2 + t * 5
        line_opacity = 10 + t * 60
        try:
            if has_opacity:
                drawLine(x1, y1, x2, y2, fill=color, lineWidth=width, opacity=line_opacity)
            else:
                drawLine(x1, y1, x2, y2, fill=color, lineWidth=width)
        except:
            try:
                drawLine(x1, y1, x2, y2, fill=color, lineWidth=width)
            except: pass

def redrawAll(app):
    try: drawRect(0,0,app.width,app.height,fill=app.background)
    except: pass
    for i in range(40):
        try:
            sx=(i*137%app.world.width-float(app.camera_x)*0.2)%app.width
            sy=(i*237%app.height*0.8)%app.height
            drawCircle(sx,sy,(i%3)+1,fill=rgb(200,200,255))
        except: pass
    for plat in app.world.platforms:
        try:
            left = float(plat.x) - float(plat.w)/2; top = float(plat.y) - float(plat.h)/2
            x = left - float(app.camera_x); y = top
            if x+plat.w<-120 or x>app.width+120: continue
            if plat.type=="bouncy":
                drawRect(x,y+3,plat.w,plat.h,fill=rgb(20,50,20)); drawRect(x,y,plat.w,plat.h,fill=rgb(100,200,100))
            elif plat.type=="wall": drawRect(x,y,plat.w,plat.h,fill=plat.color)
            else: drawRect(x,y+3,plat.w,plat.h,fill=rgb(20,20,35)); drawRect(x,y,plat.w,plat.h,fill=plat.color)
        except: continue
    for c in app.world.coins:
        if c.get("collected") or c.get("isCollected"): continue
        try: cx=float(c["x"])-float(app.camera_x); cy=float(c["y"])+math.sin(float(c.get("bob",0)))*6
        except: continue
        if cx<-50 or cx>app.width+50: continue
        drawCircle(cx,cy,10,fill=rgb(255,235,100)); drawCircle(cx,cy-2,10,fill=rgb(255,250,180))
        drawLabel("$",cx,cy,size=12,fill=rgb(100,80,0))
    for pid, p in app.world.players.items():
        try: x=float(p.x)-float(app.camera_x); y=float(p.y)
        except: continue
        if x<-100 or x>app.width+100: continue
        if app.enable_trails and p.trail:
            drawTrail(p.trail, p.color, app.camera_x, is_local=True, facing=int(p.facing), has_opacity=app.has_opacity)
        col=p.color
        if p.coin_flash>0: col=rgb(255,255,255) if p.coin_flash%2==0 else p.color
        try:
            drawRect(x-p.w/2,y-p.h/2,p.w,p.h*0.9,fill=col)
            eye_x=x+int(p.facing)*6
            drawCircle(eye_x,y-6,5,fill=rgb(255,255,255))
            drawCircle(eye_x+int(p.facing)*2,y-6,2,fill=rgb(0,0,0))
            drawLabel(p.name,x,y-p.h*0.7-14,size=11,fill=rgb(255,255,255))
            if p.score>0: drawLabel(str(p.score),x,y-p.h*0.7-26,size=9,fill=rgb(255,235,100))
        except: pass
    for cid in list(app.remote_players.keys()):
        remote = app.remote_players.get(cid)
        if not remote: continue
        pos = remote.get("position")
        if not pos or len(pos) < 2: continue
        try: px = float(pos[0]); py = float(pos[1])
        except: continue
        try: x = px - float(app.camera_x); y = py
        except: continue
        if x < -400 or x > app.width + 400: continue
        vis = app.remote_visuals.get(cid)
        if not vis: continue
        if app.enable_trails and vis.trail and len(vis.trail)>0:
            drawTrail(vis.trail, vis.color, app.camera_x, is_local=False, facing=int(vis.facing), has_opacity=app.has_opacity)
        try:
            drawRect(x-15,y-20,30,40,fill=vis.color)
            drawRect(x-15,y+18,30,4,fill=rgb(30,30,30))
            facing = int(vis.facing)
            if vis.is_blinking:
                drawLine(x-12, y-6, x-2, y-6, fill=rgb(20,20,30), lineWidth=2)
                drawLine(x+2, y-6, x+12, y-6, fill=rgb(20,20,30), lineWidth=2)
            else:
                eye_x = x + facing*6
                drawCircle(eye_x, y-6, 5, fill=rgb(255,255,255))
                drawCircle(eye_x + facing*2, y-6, 2, fill=rgb(0,0,0))
            drawLabel(cid[:4],x,y-30,size=10,fill=rgb(200,220,255))
            st = remote.get("animationState","")
            if st: drawLabel(st, x, y+28, size=8, fill=rgb(180,180,255))
            r_score = remote.get("score", 0)
            if r_score>0: drawLabel(str(r_score), x, y-42, size=9, fill=rgb(255,235,100))
        except:
            continue
    drawRect(app.width//2,22,app.width,44,fill=rgb(0,0,0))
    status="BGS 60Hz MUST USE MP | LOCAL:" + str(len(app.world.players)) + " REMOTE:" + str(len(app.remote_players)) + " COINS:" + str(len([c for c in app.world.coins if not c.get('collected')])) + "/" + str(len(app.world.coins))
    if app.datastar_connected: status+=" | CONNECTED"
    else: status+=" | CONNECTING"
    if app.is_host: status+=" HOST"
    if app.has_opacity: status+=" OPACITY"
    drawLabel(status,app.width//2,14,size=10,fill=rgb(220,220,230))
    drawCircle(app.width-20,14,6,fill=rgb(100,255,100) if app.datastar_connected else rgb(255,200,100))
    y=50
    drawRect(90,y+20,160,20+len(app.world.players)*18,fill=rgb(0,0,0))
    drawLabel("LOCAL",90,y,size=12,fill=rgb(255,255,255)); y+=18
    for p in list(app.world.players.values())[:6]:
        drawLabel(p.name + ": " + str(p.score) + " trail:" + str(len(p.trail)),90,y,size=11,fill=p.color); y+=18
    if app.remote_players:
        y+=10
        drawRect(90,y+10,160,10+len(app.remote_players)*16,fill=rgb(0,0,0))
        drawLabel("REMOTE 60Hz (" + str(len(app.remote_players)) + ")",90,y,size=11,fill=rgb(180,200,255)); y+=14
        for cid, r in list(app.remote_players.items())[:6]:
            vis = app.remote_visuals.get(cid)
            trail_len = len(vis.trail) if vis and vis.trail else 0
            st=r.get("animationState","?"); sc=r.get("score",0)
            drawLabel(cid[:6] + " " + st + " $" + str(sc) + " trail:" + str(trail_len),90,y,size=10,fill=rgb(180,180,255)); y+=16
    if app.show_help:
        hx=app.width-160; hy=80
        drawRect(hx,hy+60,300,190,fill=rgb(0,0,0))
        drawLabel("BGS CONTROLS",hx,hy-20,size=12,fill=rgb(255,255,255))
        drawLabel("WASD move",hx,hy,size=10,fill=rgb(200,220,255))
        drawLabel("R reset G trails",hx,hy+16,size=10,fill=rgb(200,220,255))
        drawLabel("MUST USE MP EXT",hx,hy+32,size=10,fill=rgb(255,100,100))
        drawLabel("60Hz PATCH 16ms",hx,hy+48,size=8,fill=rgb(180,200,255))
        drawLabel("Coins:" + str(len(app.local_collected_coins)) + " seq:" + str(app.seq),hx,hy+60,size=10,fill=rgb(255,235,100))
        drawLabel("scs.py 3.0.17",hx,hy+72,size=8,fill=rgb(100,255,100))
    drawRect(app.width//2,app.height-18,app.width,36,fill=rgb(0,0,0))
    drawLabel("MUST USE: extensions.multiplayer + extensions.datastar + extensions.fetch - SCS EXTENSION SYSTEM",app.width//2,app.height-18,size=6,fill=rgb(100,255,100))

def run():
    try:
        runApp(1050, 700)
    except Exception as e:
        try:
            window.console.error("[BGS] runApp failed", e)
        except:
            print("[BGS] runApp failed " + str(e))

run()
