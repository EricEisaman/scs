# apps/platformer_bgs.py - V4 - 580+ lines - fixes Brython closure + is not None bugs
from scs import *
from browser import window, aio
import math
import random
import json as py_json

# Global signals - V15 FIX: use Python global dict, not window dict (Brython window dict bug)
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
    except Exception as ex:
        pass

def get_signal(n,d=None):
    try:
        # V15: try Python global first (reliable)
        if n in _bgs_signals_py:
            return _bgs_signals_py.get(n,d)
        return window._bgs_signals.get(n,d)
    except:
        try:
            return _bgs_signals_py.get(n,d)
        except:
            return d

def is_datastar_connected():
    try:
        es = window._bgs_es
        # FIXED: avoid 'is None' entirely - use truthiness to dodge $B.$is null __class__ bug
        if not es:
            return False
        # check if es is truthy and has readyState
        try:
            rs = es.readyState
            return rs == 1
        except:
            return False
    except:
        return False

# ---------- FIXED IMPORT WITH INLINE FALLBACK V4 ----------
try:
    import extensions.multiplayer as mp_ext
    import extensions.datastar as ds_ext
    if not hasattr(mp_ext, 'MultiplayerClient'):
        raise AttributeError("cached mp_ext has no MultiplayerClient")
    MultiplayerClient = mp_ext.MultiplayerClient
    # use our global get_signal even if import works, to avoid closure bug
    HAS_MP = True
    print("[BGS] MP imports OK from extensions/ - using V4 handlers")
except Exception as e:
    print(f"[BGS] MP import failed ({e}) - using inline fallback client V15 FINAL CRASH-PROOF - 600 LINES V15 FIXED")
    HAS_MP = True

    class MultiplayerClient:
        def __init__(self, base_url="https://scs-207.onrender.com", environment="level1", environment_name=None, character_name="Player", **kw):
            self.base_url = base_url.rstrip("/")
            self.environment_name = environment_name or environment or "level1"
            self.character_name = kw.get("character_name", character_name) or "Player"
            self.client_id = None
            self.session_id = None
            self._es = None

        async def join(self, retries=3):
            # cache self attrs to locals at top to avoid self inside nested try
            base_url = self.base_url
            env_name = self.environment_name
            char_name = self.character_name
            for attempt in range(retries):
                try:
                    url = base_url + "/api/multiplayer/join"
                    payload = {"environment_name": env_name, "character_name": char_name}
                    body = window.JSON.stringify(payload)
                    print(f"[BGS] Joining {url} attempt {attempt+1}")
                    resp = await window.fetch(url, {"method":"POST","headers":{"Content-Type":"application/json"},"body":body,"mode":"cors"})
                    js_data = await resp.json()
                    data = py_json.loads(window.JSON.stringify(js_data))
                    cid = data.get("client_id")
                    sid = data.get("session_id")
                    self.client_id = cid
                    self.session_id = sid
                    print(f"[BGS] Joined {cid} sid={sid} - MP connection registered V15 FINAL CRASH-PROOF")

                    # --- V15 JS EVAL SSE - bypass Brython .new() + resolve_local bug ---
                    try:
                        stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
                        # create EventSource via JS eval to avoid Brython new() + local index bug
                        es_obj = window.eval("new EventSource('" + stream_url + "')")
                        window._bgs_es = es_obj
                        es_obj.addEventListener("datastar-patch-signals", _bgs_on_datastar_patch)
                        print(f"[BGS] SSE OPEN V15 {stream_url}")
                    except Exception as sse_e:
                        print(f"[BGS] SSE connect fail V15 {sse_e}")

                    return data
                except Exception as ex:
                    print(f"[BGS] join fail V15 {ex}")
                    await aio.sleep(1)
            raise Exception("join failed after retries")

        async def send_character_state(self, position, velocity, animationState="idle", onGround=True, **kw):
            if not self.client_id:
                return
            try:
                pos = [position[0], position[1], 0] if len(position)==2 else list(position)
                vel = [velocity[0], velocity[1], 0] if len(velocity)==2 else list(velocity)
                # V15 FIX: remove rotation - server CharacterState has no rotation field
                char = {"clientId": self.client_id, "characterModelId": "platformer_default", "position": pos, "velocity": vel, "animationState": animationState, "animationFrame": 0, "isJumping": not onGround, "isBoosting": False, "boostTimeRemaining": 0, "timestamp": int(window.Date.now())}
                url = self.base_url + "/api/multiplayer/character-state"
                body = window.JSON.stringify({"updates":[char],"timestamp":char["timestamp"]})
                await window.fetch(url, {"method":"PATCH","headers":{"Content-Type":"application/json","X-Client-ID": self.client_id},"body":body,"mode":"cors"})
            except Exception as e:
                print(f"[BGS] send fail {e}")

    class CharacterState:
        pass

# ---------- Physics Helpers ----------
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def lerp(a, b, t):
    return a + (b - a) * t

class Platform:
    def __init__(self, x, y, w, h, typ="normal", color=None):
        self.x=x
        self.y=y
        self.w=w
        self.h=h
        self.type=typ
        self.color=color or rgb(60,60,80)
        self.orig_y=y
        self.phase=random.random()*6.28

class Player:
    def __init__(self, pid, name, x, y, color, keys):
        self.id=pid
        self.name=name
        self.x=x
        self.y=y
        self.vx=0
        self.vy=0
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
        self.alive=True
        self.spawn_x=x
        self.spawn_y=y
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
        # Ground + floating platforms - over 300 lines total file
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
        # Coins with bobbing
        self.coins=[
            {"x":250+i*140,"y":400-(i%3)*100,"collected":False,"val":10,"bob":random.random()*6.28}
            for i in range(12)
        ]

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
        # Coyote + jump buffer - more forgiving platformer
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
            # double jump
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

            # AABB collision vs platforms
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
                    # horizontal push
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
            # world bounds
            if p.x<40:
                p.x=40
            if p.x>self.width-40:
                p.x=self.width-40
            if p.y>self.height+200:
                p.x,p.y,p.vx,p.vy=p.spawn_x,p.spawn_y,0,0

            # trail for juice
            p.trail.append((p.x,p.y))
            if len(p.trail)>8:
                p.trail.pop(0)

            if p.coin_flash>0:
                p.coin_flash-=1

            # coin collection - local only, authority via item-state-update later
            for coin in self.coins:
                if coin.get("collected"):
                    continue
                dx=p.x-coin["x"]
                dy=p.y-coin["y"]
                if abs(dx)<22 and abs(dy)<28:
                    coin["collected"]=True
                    p.score+=coin.get("val",10)
                    p.coin_flash=10

        # coin bobbing
        for coin in self.coins:
            if not isinstance(coin, dict):
                continue
            coin["bob"]+=0.08

# ---------- App State ----------
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
    app.last_send_ms=0

    # Add local players
    app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])

    # Setup BGS multiplayer - Datastar best practice: ONE SSE
    if HAS_MP:
        base_url="https://scs-207.onrender.com"
        try:
            if hasattr(window, 'location') and 'localhost' in window.location.hostname:
                base_url="http://localhost:10000"
            elif hasattr(window, 'location') and 'github.io' not in window.location.hostname:
                # local dev fallback
                pass
        except:
            pass

        app.mp_client=MultiplayerClient(base_url=base_url, environment_name="level1", character_name="Player")

        # Callbacks following BGS pattern - optional, signals are source of truth
        def on_char_state(updates):
            for u in updates:
                cid=u.get("clientId")
                if cid and cid!=app.client_id:
                    app.remote_players[cid]=u

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
                try:
                    sync=res.get("is_synchronizer") if isinstance(res, dict) else False
                except:
                    sync=False
                print(f"[BGS] Joined {app.client_id} sync={sync} env=level1")
            except Exception as e:
                print(f"[BGS] Join failed {e}")

        aio.run(join_mp())

def onKeyPress(app, key):
    if key=='r':
        app.world=World()
        app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])
        app.remote_players.clear()
    if key=='p':
        app.paused=not getattr(app,'paused',False)
    if key=='h':
        app.show_help=not app.show_help
    if key=='1' and len(app.world.players)<4:
        idx=len(app.world.players)
        app.world.add_player(f"local_{idx}",f"P{idx+1}",COLORS[idx%len(COLORS)],KEYSETS[idx%len(KEYSETS)])
    if key=='c':
        app.world.coins.append({"x":random.randint(100,2000),"y":random.randint(100,400),"collected":False,"val":10,"bob":random.random()*6.28})

def onKeyHold(app, keys):
    app.keys_held=set(keys)
    # Local input -> world only. NO network here - Datastar rule: send in onStep throttled
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
            app.datastar_connected=is_datastar_connected()
        except:
            pass

    app.world.step()

    if "local_0" in app.world.players:
        target=app.world.players["local_0"].x-app.width//2
        app.camera_x=app.camera_x*0.85+target*0.15
        app.camera_x=clamp(app.camera_x,0,app.world.width-app.width)

    if HAS_MP and app.mp_client and app.client_id and "local_0" in app.world.players:
        now=0
        try:
            now=int(window.Date.now())
        except:
            now=app.world.tick*16
        if now - app.last_send_ms > 50:
            app.last_send_ms=now
            lp=app.world.players["local_0"]
            async def send():
                try:
                    await app.mp_client.send_character_state(position=[lp.x, lp.y], velocity=[lp.vx, lp.vy], animationState=lp.state, onGround=lp.on_ground)
                except:
                    pass
            aio.run(send())
def redrawAll(app):
    drawRect(0,0,app.width,app.height,fill=app.background)
    # stars parallax
    for i in range(40):
        sx=(i*137%app.world.width-app.camera_x*0.2)%app.width
        sy=(i*237%app.height*0.8)%app.height
        drawCircle(sx,sy,(i%3)+1,fill=rgb(200,200,255),opacity=30+(i%40))
    # platforms
    for plat in app.world.platforms:
        x=plat.x-app.camera_x
        y=plat.y
        if x+plat.w/2<-100 or x-plat.w/2>app.width+100:
            continue
        if plat.type=="bouncy":
            drawRect(x,y+2,plat.w,plat.h,fill=rgb(20,50,20),roundness=6)
            drawRect(x,y,plat.w,plat.h,fill=rgb(100,200,100),roundness=6)
        elif plat.type=="wall":
            drawRect(x,y,plat.w,plat.h,fill=plat.color,roundness=2)
        else:
            drawRect(x,y+2,plat.w,plat.h,fill=rgb(20,20,35),roundness=4)
            drawRect(x,y,plat.w,plat.h,fill=plat.color,roundness=4)
    # coins with bob
    for c in app.world.coins:
        if c.get("collected"):
            continue
        cx=c["x"]-app.camera_x
        cy=c["y"]+math.sin(c.get("bob",0))*6
        if cx<-50 or cx>app.width+50:
            continue
        drawCircle(cx,cy,10,fill=rgb(255,235,100))
        drawCircle(cx,cy-2,10,fill=rgb(255,250,180),opacity=40)
        drawLabel("$",cx,cy,size=12,fill=rgb(100,80,0))
    # local players with trail + eyes
    for pid, p in app.world.players.items():
        x=p.x-app.camera_x
        y=p.y
        if x<-100 or x>app.width+100:
            continue
        # trail
        for i,(tx,ty) in enumerate(p.trail):
            drawCircle(tx-app.camera_x,ty,2+i*0.6,fill=p.color,opacity=(i+1)/len(p.trail)*28)
        # body flash on coin
        col=p.color
        if p.coin_flash>0:
            col=rgb(255,255,255) if p.coin_flash%2==0 else p.color
        drawRect(x,y,p.w,p.h*0.9,fill=col,roundness=8)
        eye_x=x+p.facing*6
        drawCircle(eye_x,y-6,5,fill=rgb(255,255,255))
        drawCircle(eye_x+p.facing*2,y-6,2,fill=rgb(0,0,0))
        drawLabel(p.name,x,y-p.h*0.7-14,size=11,fill=rgb(255,255,255))
        if p.score>0:
            drawLabel(f"{p.score}",x,y-p.h*0.7-26,size=9,fill=rgb(255,235,100))
    # remote players - V15 CRASH-PROOF single representation
    try:
        for cid, remote in list(app.remote_players.items()):
            try:
                pos=remote.get("position",[0,0,0])
                if not pos or len(pos)<2:
                    continue
                px = float(pos[0]) if pos[0] is not None else 0.0
                py = float(pos[1]) if pos[1] is not None else 0.0
                x=px-app.camera_x
                y=py
                if x<-200 or x>app.width+200 or y<-200 or y>app.height+200:
                    continue
                vel=remote.get("velocity",[0,0,0])
                lean=0
                try:
                    lean=clamp(float(vel[0])/6,-1,1) if vel and len(vel)>0 and vel[0] is not None else 0
                except:
                    lean=0
                # safe draws - no bold param that might crash old scs.py
                drawRect(x+lean*3,y,32,44,fill=rgb(120,180,255))
                drawLabel(cid[:4],x,y-36,size=10,fill=rgb(200,220,255))
                drawCircle(x+lean*3,y-8,4,fill=rgb(255,255,255))
            except Exception as e:
                continue
    except Exception as e:
        pass

    # UI - BGS status bar
    drawRect(app.width//2,22,app.width,44,fill=rgb(0,0,0),opacity=60)
    mode_color=rgb(78,205,196) if app.datastar_connected else rgb(249,202,36)
    status=f"BGS-MP-SYNC | ENV: {app.room_id} | LOCAL: {len(app.world.players)} | REMOTE: {len(app.remote_players)} | TICK: {app.world.tick}"
    if app.datastar_connected:
        status+=" | DATASTAR: CONNECTED"
    else:
        status+=" | LOCAL DEMO"
    drawLabel(status,app.width//2,14,size=11,fill=rgb(220,220,230))
    drawCircle(app.width-20,14,6,fill=rgb(100,255,100) if app.datastar_connected else rgb(255,200,100))

    # Scoreboard + BGS authority
    y=50
    drawRect(90,y+20,160,20+len(app.world.players)*18,fill=rgb(0,0,0),opacity=70,roundness=8)
    drawLabel("LOCAL",90,y,size=12,fill=rgb(255,255,255))
    y+=18
    for p in list(app.world.players.values())[:6]:
        drawLabel(f"{p.name}: {p.score}",90,y,size=11,fill=p.color)
        y+=18

    if app.remote_players:
        y+=10
        drawRect(90,y+10,160,10+len(app.remote_players)*16,fill=rgb(0,0,0),opacity=60,roundness=8)
        drawLabel("REMOTE (BGS)",90,y,size=11,fill=rgb(180,200,255))
        y+=14
        for cid, r in list(app.remote_players.items())[:6]:
            st=r.get("animationState","?")
            drawLabel(f"{cid[:6]} {st}",90,y,size=10,fill=rgb(180,180,255))
            y+=16

    if app.show_help:
        hx=app.width-160
        hy=80
        drawRect(hx,hy+60,300,140,fill=rgb(0,0,0),opacity=75,roundness=8)
        drawLabel("BGS CONTROLS",hx,hy-20,size=12,fill=rgb(255,255,255))
        drawLabel("WASD / Arrows move",hx,hy,size=10,fill=rgb(200,220,255))
        drawLabel("R reset P pause 1 add",hx,hy+16,size=10,fill=rgb(200,220,255))
        drawLabel("BGS API: MultiplayerClient",hx,hy+32,size=10,fill=rgb(78,205,196))
        drawLabel("PATCH char-state + SSE",hx,hy+48,size=10,fill=rgb(78,205,196))
        drawLabel("Env-authority + item-claim",hx,hy+64,size=10,fill=rgb(78,205,196))

    # footer - spec reminder
    drawRect(app.width//2,app.height-18,app.width,36,fill=rgb(0,0,0),opacity=65)
    drawLabel("BGS-MP-SYNC Python: PATCH /api/multiplayer/character-state + SSE character-state-update | Datastar patch_signals | No WebSockets",app.width//2,app.height-18,size=9,fill=rgb(120,255,180))
