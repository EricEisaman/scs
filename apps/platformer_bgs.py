# apps/platformer_bgs.py - V4.3 FINAL - server-safe
# Fixes: 
# 1. Loop error: unsupported operand type(s) for -: 'str' and 'int' - remote pos was string, now float()
# 2. Remote peers had no eyes / no trail
# 3. Accurate BGS data model declarations
# Verified compatible with scs-datastar-extension server:
#   POST /api/multiplayer/join {environment_name, character_name} -> {client_id, session_id}
#   GET  /api/multiplayer/stream?sid=... -> SSE datastar-patch-signals
#   PATCH /api/multiplayer/character-state + X-Client-ID header + {updates:[CharacterState], timestamp}

from scs import *
from browser import window, aio
import math
import random
import json as py_json

_bgs_signals_py = {}
window._bgs_signals = {}
window._bgs_es = None

def _bgs_on_datastar_patch(evt):
    try:
        raw = evt.data
        if isinstance(raw, str) and raw.startswith("signals "):
            raw = raw[8:]
        try:
            import json as _jj
            parsed = _jj.loads(raw)
        except:
            parsed = window.JSON.parse(raw)
        import json as _jj2
        parsed = _jj2.loads(window.JSON.stringify(parsed))
        if isinstance(parsed, dict):
            for kk, vv in parsed.items():
                _bgs_signals_py[kk] = vv
                try:
                    window._bgs_signals[kk] = vv
                except:
                    pass
    except:
        pass

def get_signal(n, d=None):
    try:
        if n in _bgs_signals_py:
            return _bgs_signals_py.get(n, d)
        return window._bgs_signals.get(n, d)
    except:
        try:
            return _bgs_signals_py.get(n, d)
        except:
            return d

def is_datastar_connected():
    try:
        es = window._bgs_es
        if not es:
            return False
        try:
            return es.readyState == 1
        except:
            return False
    except:
        return False

# --- ACCURATE SERVER DATA MODEL (from scs-datastar-extension) ---
# CharacterState: what server stores and broadcasts
# {
#   clientId: str,
#   characterModelId: str,  # "platformer_default"
#   position: [float, float, float],
#   velocity: [float, float, float],
#   animationState: str,  # idle/run/jump
#   animationFrame: int,
#   isJumping: bool,
#   isBoosting: bool,
#   boostTimeRemaining: float,
#   timestamp: int
# }
# Signal: character-state-update: {updates: CharacterState[], timestamp}

# Client-side visual only - NOT sent to server
class RemoteVisual:
    def __init__(self, clientId, color):
        self.clientId = clientId
        self.color = color
        self.trail = []  # List[Tuple[float,float]]
        self.facing = 1
        self.blink_phase = random.random()*6.28
        self.is_blinking = False

try:
    import extensions.multiplayer as mp_ext
    import extensions.datastar as ds_ext
    if not hasattr(mp_ext, 'MultiplayerClient'):
        raise AttributeError("no MultiplayerClient")
    MultiplayerClient = mp_ext.MultiplayerClient
    HAS_MP = True
except Exception as e:
    print(f"[BGS] MP import failed ({e}) - fallback")
    HAS_MP = True
    class MultiplayerClient:
        def __init__(self, base_url="https://scs-207.onrender.com", environment="level1", environment_name=None, character_name="Player", **kw):
            self.base_url = base_url.rstrip("/")
            self.environment_name = environment_name or environment or "level1"
            self.character_name = kw.get("character_name", character_name) or "Player"
            self.client_id = None
            self.session_id = None
        async def join(self, retries=3):
            base_url = self.base_url
            for attempt in range(retries):
                try:
                    url = base_url + "/api/multiplayer/join"
                    payload = {"environment_name": self.environment_name, "character_name": self.character_name}
                    body = window.JSON.stringify(payload)
                    resp = await window.fetch(url, window.JSON.parse(window.JSON.stringify({"method":"POST","headers":{"Content-Type":"application/json"},"body":body})))
                    js_data = await resp.json()
                    data = py_json.loads(window.JSON.stringify(js_data))
                    cid = data.get("client_id")
                    sid = data.get("session_id")
                    if not cid or not sid:
                        raise Exception("missing ids")
                    self.client_id = cid
                    self.session_id = sid
                    try:
                        stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
                        es_obj = window.eval("new EventSource('" + stream_url + "')")
                        window._bgs_es = es_obj
                        es_obj.addEventListener("datastar-patch-signals", _bgs_on_datastar_patch)
                    except Exception as sse_e:
                        print(f"[BGS] SSE fail {sse_e}")
                    return data
                except Exception as ex:
                    print(f"[BGS] join fail {attempt+1}: {ex}")
                    await aio.sleep(1.5)
            return {"client_id": None, "session_id": None, "local_demo": True}

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

class Platform:
    def __init__(self, x, y, w, h, typ="normal", color=None):
        self.x=x
        self.y=y
        self.w=w
        self.h=h
        self.type=typ
        self.color=color or rgb(60,60,80)

class Player:
    def __init__(self, pid, name, x, y, color, keys):
        self.id=pid
        self.name=name
        self.x=float(x)
        self.y=float(y)
        self.vx=0.0
        self.vy=0.0
        self.w=32
        self.h=44
        self.on_ground=False
        self.facing=1
        self.state="idle"
        self.color=color
        self.keys=keys
        self.score=0
        self.jump_count=0
        self.max_jumps=2
        self.coyote_timer=0
        self.jump_buffer=0
        self.spawn_x=float(x)
        self.spawn_y=float(y)
        self.trail=[]
        self.coin_flash=0

class World:
    def __init__(self, width=2400, height=700):
        self.width=width
        self.height=height
        self.gravity=0.65
        self.friction=0.82
        self.platforms=[]
        self.coins=[]
        self.players={}
        self.tick=0
        self.build_level()
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
            if plat.type=="wall" or plat.w>1000:
                continue
            self.coins.append({"x":float(plat.x),"y":float(plat.y-50),"collected":False,"val":10,"bob":random.random()*6.28})
        extras=[(400,300),(900,300),(1200,250),(1800,280)]
        for ex,ey in extras:
            self.coins.append({"x":float(ex),"y":float(ey),"collected":False,"val":10,"bob":random.random()*6.28})
    def add_player(self, pid, name, color, keys):
        p=Player(pid,name,150+len(self.players)*70,100,color,keys)
        self.players[pid]=p
        return p
    def apply_input(self, pid, move_x, jump):
        if pid not in self.players:
            return
        p=self.players[pid]
        if move_x!=0:
            p.vx=move_x*5.8
            p.facing=move_x
            if p.on_ground:
                p.state="run"
        else:
            p.vx*=self.friction
            if abs(p.vx)<0.2:
                p.vx=0
            if p.on_ground:
                p.state="idle"
        if p.on_ground:
            p.coyote_timer=6
        else:
            p.coyote_timer=max(0, p.coyote_timer-1)
        if jump:
            p.jump_buffer=6
        else:
            p.jump_buffer=max(0, p.jump_buffer-1)
        if p.jump_buffer>0 and p.coyote_timer>0:
            p.vy=-13.2
            p.on_ground=False
            p.jump_count=1
            p.state="jump"
            p.jump_buffer=0
            p.coyote_timer=0
        elif jump and p.jump_count<p.max_jumps and p.jump_count>0:
            if p.jump_buffer>0:
                p.vy=-11.0
                p.jump_count+=1
                p.state="jump"
                p.jump_buffer=0
    def step(self):
        self.tick+=1
        for p in list(self.players.values()):
            if not p.on_ground:
                p.vy+=self.gravity
            p.x+=p.vx
            p.y+=p.vy
            p.on_ground=False
            px1,py1=p.x-p.w/2,p.y-p.h/2
            px2,py2=p.x+p.w/2,p.y+p.h/2
            for plat in self.platforms:
                bx1,by1=plat.x-plat.w/2,plat.y-plat.h/2
                bx2,by2=plat.x+plat.w/2,plat.y+plat.h/2
                if px2<bx1 or px1>bx2 or py2<by1 or py1>by2:
                    continue
                ox=min(px2,bx2)-max(px1,bx1)
                oy=min(py2,by2)-max(py1,by1)
                if ox<oy:
                    p.x=bx1-p.w/2-0.5 if p.x<plat.x else bx2+p.w/2+0.5
                    p.vx=0
                else:
                    if p.y<plat.y:
                        p.y=by1-p.h/2-0.5
                        p.vy=0
                        p.on_ground=True
                        p.jump_count=0
                        if plat.type=="bouncy":
                            p.vy=-16
                            p.on_ground=False
                            p.state="jump"
                    else:
                        p.y=by2+p.h/2+0.5
                        p.vy=0
            if p.x<40:
                p.x=40
            if p.x>self.width-40:
                p.x=self.width-40
            if p.y>self.height+200:
                p.x,p.y,p.vx,p.vy=p.spawn_x,p.spawn_y,0,0
            p.trail.append((float(p.x), float(p.y)))
            if len(p.trail)>8:
                p.trail.pop(0)
            if p.coin_flash>0:
                p.coin_flash-=1
            for coin in self.coins:
                if coin.get("collected"):
                    continue
                try:
                    dx=float(p.x)-float(coin["x"])
                    dy=float(p.y)-float(coin["y"])
                except:
                    continue
                if abs(dx)<22 and abs(dy)<28:
                    coin["collected"]=True
                    p.score+=coin.get("val",10)
                    p.coin_flash=10
        for coin in self.coins:
            if not isinstance(coin, dict):
                continue
            coin["bob"]+=0.08

KEYSETS=[
    {"left":"a","right":"d","jump":"w","down":"s"},
    {"left":"arrowleft","right":"arrowright","jump":"arrowup","down":"arrowdown"},
    {"left":"j","right":"l","jump":"i","down":"k"},
    {"left":"4","right":"6","jump":"8","down":"5"},
]
COLORS=[rgb(255,107,107),rgb(78,205,196),rgb(69,183,209),rgb(249,202,36),rgb(108,92,231),rgb(253,121,168)]

def onAppStart(app):
    app.width=1050
    app.height=700
    app.stepsPerSecond=60
    app.background=rgb(15,15,30)
    app.world=World()
    app.camera_x=0.0
    app.keys_held=set()
    app.show_help=True
    app.mode="bgs-multiplayer"
    app.room_id="level1"
    app.client_id=None
    app.mp_client=None
    app.datastar_connected=False
    app.remote_players={}
    app.remote_visuals={}
    app.authority={}
    app.last_send_ms=0
    app.enable_trails=True
    app.trail_length=10
    app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])

    if HAS_MP:
        base_url="https://scs-207.onrender.com"
        try:
            if hasattr(window, 'location') and 'localhost' in window.location.hostname:
                base_url="http://localhost:10000"
        except:
            pass
        app.mp_client=MultiplayerClient(base_url=base_url, environment_name="level1", character_name="Player")
        def on_char_state(updates):
            for u in updates:
                cid=u.get("clientId")
                if cid and cid!=app.client_id:
                    app.remote_players[cid]=u
                    if cid not in app.remote_visuals:
                        app.remote_visuals[cid]=RemoteVisual(clientId=cid, color=rgb(120,180,255))
        def on_item_auth(instanceId, prev, new, reason):
            app.authority[instanceId]=new
        if hasattr(app.mp_client, 'on_character_state'):
            app.mp_client.on_character_state=on_char_state
        app.mp_client.on_item_authority_changed=on_item_auth
        async def join_mp():
            try:
                res=await app.mp_client.join()
                cid=None
                try:
                    cid=res.get("client_id") if isinstance(res, dict) else None
                except:
                    pass
                if not cid:
                    try:
                        import json as _j
                        d=_j.loads(window.JSON.stringify(res)) if hasattr(window, 'JSON') else {}
                        cid=d.get("client_id")
                        res=d
                    except:
                        cid=getattr(res, "client_id", None)
                app.client_id=cid
                app.room_id="level1"
                print(f"[BGS] Joined {app.client_id} env=level1")
            except Exception as e:
                print(f"[BGS] Join failed {e}")
        aio.run(join_mp())

def onKeyPress(app, key):
    if key=='r':
        app.world=World()
        app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])
        app.remote_players.clear()
        app.remote_visuals.clear()
    if key=='p':
        app.paused=not getattr(app,'paused',False)
    if key=='h':
        app.show_help=not app.show_help
    if key=='g':
        app.enable_trails=not app.enable_trails
    if key=='1' and len(app.world.players)<4:
        idx=len(app.world.players)
        app.world.add_player(f"local_{idx}",f"P{idx+1}",COLORS[idx%len(COLORS)],KEYSETS[idx%len(KEYSETS)])
    if key=='c':
        app.world.coins.append({"x":float(random.randint(100,2000)),"y":float(random.randint(100,400)),"collected":False,"val":10,"bob":random.random()*6.28})

def onKeyHold(app, keys):
    app.keys_held=set(keys)
    for pid, p in app.world.players.items():
        km=p.keys
        move_x=0
        if km["left"] in app.keys_held:
            move_x-=1
        if km["right"] in app.keys_held:
            move_x+=1
        jump=km["jump"] in app.keys_held
        app.world.apply_input(pid, move_x, jump)

def onStep(app):
    if HAS_MP:
        try:
            sig=get_signal("character-state-update")
            if sig and isinstance(sig, dict):
                for u in sig.get("updates",[]):
                    cid=u.get("clientId")
                    if cid and cid != app.client_id:
                        app.remote_players[cid]=u
                        if cid not in app.remote_visuals:
                            app.remote_visuals[cid]=RemoteVisual(clientId=cid, color=rgb(120,180,255))
            app.datastar_connected=is_datastar_connected()
        except Exception as e:
            pass
    app.world.step()

    for cid, remote in list(app.remote_players.items()):
        vis = app.remote_visuals.get(cid)
        if not vis:
            vis = RemoteVisual(clientId=cid, color=rgb(120,180,255))
            app.remote_visuals[cid]=vis
        pos = remote.get("position")
        vel = remote.get("velocity", [0,0,0])
        if not pos or len(pos)<2:
            continue
        try:
            px = float(pos[0])
            py = float(pos[1])
            vx = float(vel[0]) if len(vel)>0 else 0.0
        except:
            continue
        if abs(vx) > 0.3:
            vis.facing = 1 if vx > 0 else -1
        vis.trail.append((px, py))
        if len(vis.trail) > app.trail_length:
            vis.trail.pop(0)
        vis.blink_phase += 0.05
        vis.is_blinking = (app.world.tick + hash(cid) % 60) % 120 == 0

    if "local_0" in app.world.players:
        try:
            target=float(app.world.players["local_0"].x)-float(app.width)//2
            app.camera_x=float(app.camera_x)*0.85+float(target)*0.15
            app.camera_x=clamp(app.camera_x,0,float(app.world.width-app.width))
        except:
            pass

    if HAS_MP and app.mp_client and app.client_id and "local_0" in app.world.players:
        now=0
        try:
            now=int(window.Date.now())
        except:
            now=app.world.tick*16
        if now - app.last_send_ms > 100:
            app.last_send_ms=now
            lp=app.world.players["local_0"]
            try:
                # server expects floats, not strings - ensure float
                safe_x = float(lp.x)
                safe_y = float(lp.y)
                safe_vx = float(lp.vx)
                safe_vy = float(lp.vy)
                window.eval(f"fetch('{app.mp_client.base_url}/api/multiplayer/character-state', {{method:'PATCH',headers:{{'Content-Type':'application/json','X-Client-ID':'{app.client_id}'}},body:JSON.stringify({{updates:[{{clientId:'{app.client_id}',characterModelId:'platformer_default',position:[{safe_x},{safe_y},0],velocity:[{safe_vx},{safe_vy},0],animationState:'{lp.state}',animationFrame:0,isJumping:{str(not lp.on_ground).lower()},isBoosting:false,boostTimeRemaining:0,timestamp:Date.now()}}],timestamp:Date.now()}})}}).catch(()=>{{}})")
            except Exception as e:
                print(f"[BGS] send fail {e}")

def drawTrail(trail, color, camera_x):
    if not trail or len(trail)<2:
        return
    for i,(tx,ty) in enumerate(trail[:-1]):
        try:
            tx_f = float(tx)
            ty_f = float(ty)
            cam_f = float(camera_x)
        except:
            continue
        t = i / max(1, len(trail)-1)
        alpha = t * 0.35
        size = 3 + t * 8
        x = tx_f - cam_f
        try:
            drawCircle(x, ty_f, size, fill=color, opacity=alpha*0.7)
        except:
            try:
                drawCircle(x, ty_f, size, fill=color)
            except:
                pass

def redrawAll(app):
    try:
        drawRect(0,0,app.width,app.height,fill=app.background)
    except:
        pass
    # stars
    for i in range(40):
        try:
            sx=(i*137%app.world.width-float(app.camera_x)*0.2)%app.width
            sy=(i*237%app.height*0.8)%app.height
            drawCircle(sx,sy,(i%3)+1,fill=rgb(200,200,255))
        except:
            pass

    for plat in app.world.platforms:
        try:
            left = float(plat.x) - float(plat.w)/2
            top = float(plat.y) - float(plat.h)/2
            x = left - float(app.camera_x)
            y = top
            if x+plat.w<-120 or x>app.width+120:
                continue
            if plat.type=="bouncy":
                drawRect(x,y+3,plat.w,plat.h,fill=rgb(20,50,20))
                drawRect(x,y,plat.w,plat.h,fill=rgb(100,200,100))
            elif plat.type=="wall":
                drawRect(x,y,plat.w,plat.h,fill=plat.color)
            else:
                drawRect(x,y+3,plat.w,plat.h,fill=rgb(20,20,35))
                drawRect(x,y,plat.w,plat.h,fill=plat.color)
        except Exception as e:
            continue

    for c in app.world.coins:
        if c.get("collected"):
            continue
        try:
            cx=float(c["x"])-float(app.camera_x)
            cy=float(c["y"])+math.sin(float(c.get("bob",0)))*6
        except:
            continue
        if cx<-50 or cx>app.width+50:
            continue
        drawCircle(cx,cy,10,fill=rgb(255,235,100))
        drawCircle(cx,cy-2,10,fill=rgb(255,250,180))
        drawLabel("$",cx,cy,size=12,fill=rgb(100,80,0))

    for pid, p in app.world.players.items():
        try:
            x=float(p.x)-float(app.camera_x)
            y=float(p.y)
        except:
            continue
        if x<-100 or x>app.width+100:
            continue
        if app.enable_trails:
            for i,(tx,ty) in enumerate(p.trail):
                try:
                    t = i / max(1, len(p.trail)-1)
                    drawCircle(float(tx)-float(app.camera_x), float(ty), 2+i*0.6, fill=p.color, opacity=0.15 + t*0.4)
                except:
                    pass
        col=p.color
        if p.coin_flash>0:
            col=rgb(255,255,255) if p.coin_flash%2==0 else p.color
        try:
            drawRect(x-p.w/2,y-p.h/2,p.w,p.h*0.9,fill=col)
            eye_x=x+int(p.facing)*6
            drawCircle(eye_x,y-6,5,fill=rgb(255,255,255))
            drawCircle(eye_x+int(p.facing)*2,y-6,2,fill=rgb(0,0,0))
            drawLabel(p.name,x,y-p.h*0.7-14,size=11,fill=rgb(255,255,255))
            if p.score>0:
                drawLabel(f"{p.score}",x,y-p.h*0.7-26,size=9,fill=rgb(255,235,100))
        except Exception as e:
            pass

    for cid in list(app.remote_players.keys()):
        remote = app.remote_players.get(cid)
        if not remote:
            continue
        pos = remote.get("position")
        if not pos or len(pos) < 2:
            continue
        try:
            px = float(pos[0])
            py = float(pos[1])
        except:
            continue
        try:
            x = px - float(app.camera_x)
            y = py
        except:
            continue
        if x < -300 or x > app.width + 300:
            continue
        vis = app.remote_visuals.get(cid)
        if not vis:
            continue
        if app.enable_trails and vis.trail:
            drawTrail(vis.trail, vis.color, app.camera_x)
        try:
            drawRect(x-15,y-20,30,40,fill=vis.color)
            drawRect(x-15,y+18,30,4,fill=rgb(0,0,0), opacity=0.25)
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
            if st:
                drawLabel(st, x, y+28, size=8, fill=rgb(180,180,255))
        except Exception as e:
            print(f"[BGS] draw remote fail {e}")
            continue

    drawRect(app.width//2,22,app.width,44,fill=rgb(0,0,0))
    status=f"BGS-MP-SYNC | ENV: {app.room_id} | LOCAL: {len(app.world.players)} | REMOTE: {len(app.remote_players)} | TICK: {app.world.tick}"
    if app.datastar_connected:
        status+=" | DATASTAR: CONNECTED"
    else:
        status+=" | LOCAL DEMO"
    drawLabel(status,app.width//2,14,size=11,fill=rgb(220,220,230))
    drawCircle(app.width-20,14,6,fill=rgb(100,255,100) if app.datastar_connected else rgb(255,200,100))

    y=50
    drawRect(90,y+20,160,20+len(app.world.players)*18,fill=rgb(0,0,0))
    drawLabel("LOCAL",90,y,size=12,fill=rgb(255,255,255))
    y+=18
    for p in list(app.world.players.values())[:6]:
        drawLabel(f"{p.name}: {p.score}",90,y,size=11,fill=p.color)
        y+=18
    if app.remote_players:
        y+=10
        drawRect(90,y+10,160,10+len(app.remote_players)*16,fill=rgb(0,0,0))
        drawLabel("REMOTE (BGS)",90,y,size=11,fill=rgb(180,200,255))
        y+=14
        for cid, r in list(app.remote_players.items())[:6]:
            st=r.get("animationState","?")
            drawLabel(f"{cid[:6]} {st}",90,y,size=10,fill=rgb(180,180,255))
            y+=16

    if app.show_help:
        hx=app.width-160
        hy=80
        drawRect(hx,hy+60,300,140,fill=rgb(0,0,0))
        drawLabel("BGS CONTROLS",hx,hy-20,size=12,fill=rgb(255,255,255))
        drawLabel("WASD / Arrows move",hx,hy,size=10,fill=rgb(200,220,255))
        drawLabel("R reset G trails P pause 1 add",hx,hy+16,size=10,fill=rgb(200,220,255))
        drawLabel("BGS API: CharacterState",hx,hy+32,size=10,fill=rgb(78,205,196))
        drawLabel("pos[xyz] vel[xyz] animState",hx,hy+48,size=10,fill=rgb(78,205,196))
        drawLabel("isJumping isBoosting ts",hx,hy+64,size=10,fill=rgb(78,205,196))

    drawRect(app.width//2,app.height-18,app.width,36,fill=rgb(0,0,0))
    drawLabel("BGS-MP-SYNC: PATCH char-state + SSE | server: scs-datastar-extension",app.width//2,app.height-18,size=9,fill=rgb(120,255,180))
