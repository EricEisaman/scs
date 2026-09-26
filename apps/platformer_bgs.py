# apps/platformer_bgs.py - V4.6 - FINAL: visible trails + coin MP + 60Hz server
# 1. Trail now ULTRA VISIBLE and direction-dependent
# 2. Coins handled by multiplayer via character-state channel
# 3. MP server proper 60Hz

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

class RemoteVisual:
    def __init__(self, clientId, color):
        self.clientId = clientId
        self.color = color
        self.trail = []
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
                    except:
                        pass
                    return data
                except Exception as ex:
                    print(f"[BGS] join fail {attempt+1}: {ex}")
                    await aio.sleep(1.5)
            return {"client_id": None, "session_id": None, "local_demo": True}

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
        for idx, plat in enumerate(self.platforms):
            if plat.type=="wall" or plat.w>1000: continue
            self.coins.append({
                "id": f"coin_{len(self.coins)}",
                "instanceId": f"coin_{len(self.coins)}",
                "x":float(plat.x),"y":float(plat.y-50),
                "collected":False,
                "collectedBy":None,
                "val":10,"bob":random.random()*6.28
            })
        extras=[(400,300),(900,300),(1200,250),(1800,280)]
        for ex,ey in extras:
            self.coins.append({
                "id": f"coin_{len(self.coins)}",
                "instanceId": f"coin_{len(self.coins)}",
                "x":float(ex),"y":float(ey),
                "collected":False,
                "collectedBy":None,
                "val":10,"bob":random.random()*6.28
            })
    def add_player(self, pid, name, color, keys):
        p=Player(pid,name,150+len(self.players)*70,100,color,keys); self.players[pid]=p; return p
    def apply_input(self, pid, move_x, jump):
        if pid not in self.players: return
        p=self.players[pid]
        if move_x!=0:
            p.vx=move_x*5.8; p.facing=move_x
            if p.on_ground: p.state="run"
        else:
            p.vx*=self.friction
            if abs(p.vx)<0.2: p.vx=0
            if p.on_ground: p.state="idle"
        if p.on_ground: p.coyote_timer=6
        else: p.coyote_timer=max(0, p.coyote_timer-1)
        if jump: p.jump_buffer=6
        else: p.jump_buffer=max(0, p.jump_buffer-1)
        if p.jump_buffer>0 and p.coyote_timer>0:
            p.vy=-13.2; p.on_ground=False; p.jump_count=1; p.state="jump"; p.jump_buffer=0; p.coyote_timer=0
        elif jump and p.jump_count<p.max_jumps and p.jump_count>0:
            if p.jump_buffer>0:
                p.vy=-11.0; p.jump_count+=1; p.state="jump"; p.jump_buffer=0
    def step(self, app_ref=None):
        self.tick+=1
        for p in list(self.players.values()):
            if not p.on_ground: p.vy+=self.gravity
            p.x+=p.vx; p.y+=p.vy; p.on_ground=False
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
            
            # TRAIL - direction dependent origin
            try:
                facing = int(p.facing) if p.facing!=0 else 1
                trail_origin_x = float(p.x) - float(facing) * (float(p.w) * 0.5)
                trail_origin_y = float(p.y) + float(p.h) * 0.3
                speed = math.hypot(float(p.vx), float(p.vy))
                # ALWAYS add when moving, for visibility
                if speed > 0.3 or abs(float(p.vx)) > 0.5:
                    p.trail.append((trail_origin_x, trail_origin_y, float(p.vx), float(p.vy)))
                else:
                    if p.trail and random.random() < 0.25:
                        p.trail.pop(0)
            except:
                p.trail.append((float(p.x), float(p.y), 0.0, 0.0))
            
            if len(p.trail)>20: p.trail.pop(0)
            if p.coin_flash>0: p.coin_flash-=1
            
            # COIN COLLECTION - MULTIPLAYER HANDLED
            # Check against app_ref coin states that include remote collections
            if app_ref:
                for coin in app_ref.world.coins:
                    if coin.get("collected"): continue
                    try:
                        dx=float(p.x)-float(coin["x"]); dy=float(p.y)-float(coin["y"])
                    except: continue
                    if abs(dx)<22 and abs(dy)<28:
                        # Mark locally and add to multiplayer set
                        coin["collected"]=True
                        coin["collectedBy"]=p.id
                        p.score+=coin.get("val",10)
                        p.coin_flash=10
                        if app_ref:
                            app_ref.local_collected_coins.add(coin["id"])
                            # Try to claim authority if server supports it
                            try:
                                if app_ref.client_id:
                                    # Broadcast coin collection via character-state channel
                                    # This will be picked up by remote peers in onStep
                                    pass
                            except:
                                pass

        for coin in self.coins:
            if not isinstance(coin, dict): continue
            coin["bob"]+=0.08

KEYSETS=[
    {"left":"a","right":"d","jump":"w","down":"s"},
    {"left":"arrowleft","right":"arrowright","jump":"arrowup","down":"arrowdown"},
    {"left":"j","right":"l","jump":"i","down":"k"},
    {"left":"4","right":"6","jump":"8","down":"5"},
]
COLORS=[rgb(255,107,107),rgb(78,205,196),rgb(69,183,209),rgb(249,202,36),rgb(108,92,231),rgb(253,121,168)]

def onAppStart(app):
    app.width=1050; app.height=700; app.stepsPerSecond=60  # 60Hz
    app.background=rgb(15,15,30)
    app.world=World(); app.camera_x=0.0; app.keys_held=set(); app.show_help=True
    app.mode="bgs-multiplayer"; app.room_id="level1"; app.client_id=None; app.mp_client=None
    app.datastar_connected=False; app.remote_players={}; app.remote_visuals={}
    app.authority={}; app.last_send_ms=0; app.enable_trails=True; app.trail_length=20
    app.local_collected_coins=set()  # Multiplayer coin sync
    app.is_host=False
    app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])
    if HAS_MP:
        base_url="https://scs-207.onrender.com"
        try:
            if hasattr(window, 'location') and 'localhost' in window.location.hostname:
                base_url="http://localhost:10000"
        except: pass
        app.mp_client=MultiplayerClient(base_url=base_url, environment_name="level1", character_name="Player")
        def on_char_state(updates):
            for u in updates:
                cid=u.get("clientId")
                if cid and cid!=app.client_id:
                    app.remote_players[cid]=u
                    if cid not in app.remote_visuals:
                        app.remote_visuals[cid]=RemoteVisual(clientId=cid, color=rgb(120,180,255))
        def on_item_auth(instanceId, prev, new, reason): app.authority[instanceId]=new
        if hasattr(app.mp_client, 'on_character_state'): app.mp_client.on_character_state=on_char_state
        app.mp_client.on_item_authority_changed=on_item_auth
        async def join_mp():
            try:
                res=await app.mp_client.join()
                cid=res.get("client_id") if isinstance(res, dict) else None
                if not cid:
                    try:
                        import json as _j
                        d=_j.loads(window.JSON.stringify(res)) if hasattr(window, 'JSON') else {}
                        cid=d.get("client_id")
                        is_sync=d.get("is_synchronizer", False)
                        app.is_host=is_sync
                    except: 
                        cid=getattr(res, "client_id", None)
                        app.is_host=getattr(res, "is_synchronizer", False)
                else:
                    try:
                        app.is_host=res.get("is_synchronizer", False)
                    except:
                        app.is_host=False
                app.client_id=cid
                print(f"[BGS] Joined {app.client_id} host={app.is_host} 60Hz")
            except Exception as e: print(f"[BGS] Join failed {e}")
        aio.run(join_mp())

def onKeyPress(app, key):
    if key=='r':
        app.world=World(); app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])
        app.remote_players.clear(); app.remote_visuals.clear(); app.local_collected_coins.clear()
    if key=='p': app.paused=not getattr(app,'paused',False)
    if key=='h': app.show_help=not app.show_help
    if key=='g':
        app.enable_trails=not app.enable_trails
        print(f"[BGS] Trails {'ON' if app.enable_trails else 'OFF'}")
    if key=='1' and len(app.world.players)<4:
        idx=len(app.world.players)
        app.world.add_player(f"local_{idx}",f"P{idx+1}",COLORS[idx%len(COLORS)],KEYSETS[idx%len(KEYSETS)])
    if key=='c':
        new_id=f"coin_{len(app.world.coins)}"
        app.world.coins.append({"id":new_id,"instanceId":new_id,"x":float(random.randint(100,2000)),"y":float(random.randint(100,400)),"collected":False,"collectedBy":None,"val":10,"bob":random.random()*6.28})

def onKeyHold(app, keys):
    app.keys_held=set(keys)
    for pid, p in app.world.players.items():
        km=p.keys; move_x=0
        if km["left"] in app.keys_held: move_x-=1
        if km["right"] in app.keys_held: move_x+=1
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
                        # COIN SYNC - handle remote coin collections
                        remote_coins = u.get("collectedCoins", [])
                        if remote_coins:
                            for rc_id in remote_coins:
                                # Mark local coin as collected if remote collected it
                                for coin in app.world.coins:
                                    if coin["id"]==rc_id and not coin.get("collected"):
                                        coin["collected"]=True
                                        coin["collectedBy"]=cid
                                        print(f"[BGS] Remote {cid} collected {rc_id}")
            # Also check for dedicated coin-state-update signal if server sends it
            coin_sig = get_signal("coin-state-update")
            if coin_sig and isinstance(coin_sig, dict):
                for c_id, c_state in coin_sig.items():
                    if c_state.get("collected"):
                        for coin in app.world.coins:
                            if coin["id"]==c_id and not coin.get("collected"):
                                coin["collected"]=True
                                coin["collectedBy"]=c_state.get("by","remote")
            app.datastar_connected=is_datastar_connected()
        except Exception as e:
            # print(f"[BGS] signal parse fail {e}")
            pass
    # Pass app ref for coin handling
    app.world.step(app_ref=app)

    for cid, remote in list(app.remote_players.items()):
        vis = app.remote_visuals.get(cid)
        if not vis:
            vis = RemoteVisual(clientId=cid, color=rgb(120,180,255))
            app.remote_visuals[cid]=vis
        pos = remote.get("position"); vel = remote.get("velocity", [0,0,0])
        if not pos or len(pos)<2: continue
        try:
            px = float(pos[0]); py = float(pos[1])
            vx = float(vel[0]) if len(vel)>0 else 0.0
            vy = float(vel[1]) if len(vel)>1 else 0.0
        except: continue
        if abs(vx) > 0.3: vis.facing = 1 if vx > 0 else -1
        # Direction-dependent trail origin for remote
        try:
            facing = int(vis.facing) if vis.facing!=0 else 1
            trail_origin_x = px - float(facing) * 15.0
            trail_origin_y = py + 10.0
            speed = math.hypot(vx, vy)
            if speed > 0.5:
                vis.trail.append((trail_origin_x, trail_origin_y, vx, vy))
            else:
                if vis.trail and random.random() < 0.2:
                    vis.trail.pop(0)
        except:
            vis.trail.append((px, py, 0.0, 0.0))
        if len(vis.trail) > app.trail_length: vis.trail.pop(0)
        vis.blink_phase += 0.05
        vis.is_blinking = (app.world.tick + hash(cid) % 60) % 120 == 0

    if "local_0" in app.world.players:
        try:
            target=float(app.world.players["local_0"].x)-float(app.width)//2
            app.camera_x=float(app.camera_x)*0.85+float(target)*0.15
            app.camera_x=clamp(app.camera_x,0,float(app.world.width-app.width))
        except: pass

    # 60Hz SEND RATE - was 100ms (10Hz), now 16ms (60Hz)
    if HAS_MP and app.mp_client and app.client_id and "local_0" in app.world.players:
        now=0
        try: now=int(window.Date.now())
        except: now=app.world.tick*16
        if now - app.last_send_ms > 16:  # 60Hz
            app.last_send_ms=now
            lp=app.world.players["local_0"]
            try:
                safe_x = float(lp.x); safe_y = float(lp.y)
                safe_vx = float(lp.vx); safe_vy = float(lp.vy)
                # Include collected coins for multiplayer sync
                collected_list = list(app.local_collected_coins)
                collected_json = py_json.dumps(collected_list)
                # Use window.eval to send at 60Hz - compatible with scs-datastar-extension
                # Server at scs-207.onrender.com runs at 60Hz tick and broadcasts via SSE
                window.eval(f"""
                    fetch('{app.mp_client.base_url}/api/multiplayer/character-state', {{
                        method:'PATCH',
                        headers:{{'Content-Type':'application/json','X-Client-ID':'{app.client_id}'}},
                        body: JSON.stringify({{
                            updates:[{{
                                clientId:'{app.client_id}',
                                characterModelId:'platformer_default',
                                position:[{safe_x},{safe_y},0],
                                velocity:[{safe_vx},{safe_vy},0],
                                animationState:'{lp.state}',
                                animationFrame:0,
                                isJumping:{str(not lp.on_ground).lower()},
                                isBoosting:false,
                                boostTimeRemaining:0,
                                collectedCoins:{collected_json},
                                score:{lp.score},
                                timestamp:Date.now()
                            }}],
                            timestamp:Date.now()
                        }})
                    }}).catch(()=>{{}})
                """)
            except Exception as e:
                print(f"[BGS] send fail {e}")

def drawTrail(trail, color, camera_x, is_local=False, facing=1):
    """ULTRA VISIBLE - no opacity tricks that might fail, solid colors"""
    if not trail or len(trail)<1:
        return
    # Draw all points as solid large circles first (guaranteed visible)
    for i in range(len(trail)):
        try:
            # trail entry can be (x,y) or (x,y,vx,vy)
            entry = trail[i]
            tx = float(entry[0])
            ty = float(entry[1])
            cam = float(camera_x)
            x = tx - cam
            y = ty
        except:
            continue
        t = i / max(1, len(trail)-1)
        # Size grows towards newest
        size = 4 + t * 12
        # Use bright yellow/white for local, color for remote
        if is_local:
            # White core + color outline for local
            if t > 0.5:
                try:
                    # Outer color
                    drawCircle(x, y, size+2, fill=color)
                    # Inner white for pop
                    drawCircle(x, y, size*0.6, fill=rgb(255,255,200))
                except:
                    try:
                        drawCircle(x, y, size, fill=rgb(255,255,100))
                    except:
                        pass
            else:
                try:
                    drawCircle(x, y, size*0.7, fill=rgb(255,255,100))
                except:
                    pass
        else:
            # Remote - solid color trail
            try:
                drawCircle(x, y, size, fill=color)
                # Add white highlight
                if t > 0.7:
                    drawCircle(x, y, size*0.4, fill=rgb(200,220,255))
            except:
                try:
                    drawCircle(x, y, size, fill=rgb(100,200,255))
                except:
                    pass
    
    # Connect with thick lines for motion blur
    for i in range(len(trail)-1):
        try:
            tx1 = float(trail[i][0]); ty1 = float(trail[i][1])
            tx2 = float(trail[i+1][0]); ty2 = float(trail[i+1][1])
            cam = float(camera_x)
            x1 = tx1 - cam; y1 = ty1; x2 = tx2 - cam; y2 = ty2
        except:
            continue
        t = i / max(1, len(trail)-1)
        if math.hypot(x2-x1, y2-y1) < 0.5:
            continue
        width = 3 + t * 8
        try:
            drawLine(x1, y1, x2, y2, fill=color, lineWidth=width)
        except:
            try:
                drawLine(x1, y1, x2, y2, fill=rgb(255,255,0), lineWidth=width)
            except:
                pass

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
        if c.get("collected"): continue
        try:
            cx=float(c["x"])-float(app.camera_x); cy=float(c["y"])+math.sin(float(c.get("bob",0)))*6
        except: continue
        if cx<-50 or cx>app.width+50: continue
        # Different color if collected by remote
        if c.get("collectedBy"):
            drawCircle(cx,cy,10,fill=rgb(100,100,100))
        else:
            drawCircle(cx,cy,10,fill=rgb(255,235,100))
            drawCircle(cx,cy-2,10,fill=rgb(255,250,180))
            drawLabel("$",cx,cy,size=12,fill=rgb(100,80,0))

    # LOCAL - trail FIRST, then player
    for pid, p in app.world.players.items():
        try: x=float(p.x)-float(app.camera_x); y=float(p.y)
        except: continue
        if x<-100 or x>app.width+100: continue
        if app.enable_trails and p.trail:
            drawTrail(p.trail, p.color, app.camera_x, is_local=True, facing=int(p.facing))
        col=p.color
        if p.coin_flash>0: col=rgb(255,255,255) if p.coin_flash%2==0 else p.color
        try:
            drawRect(x-p.w/2,y-p.h/2,p.w,p.h*0.9,fill=col)
            eye_x=x+int(p.facing)*6
            drawCircle(eye_x,y-6,5,fill=rgb(255,255,255))
            drawCircle(eye_x+int(p.facing)*2,y-6,2,fill=rgb(0,0,0))
            drawLabel(p.name,x,y-p.h*0.7-14,size=11,fill=rgb(255,255,255))
            if p.score>0: drawLabel(f"{p.score}",x,y-p.h*0.7-26,size=9,fill=rgb(255,235,100))
        except: pass

    # REMOTE - trail FIRST
    for cid in list(app.remote_players.keys()):
        remote = app.remote_players.get(cid)
        if not remote: continue
        pos = remote.get("position")
        if not pos or len(pos) < 2: continue
        try: px = float(pos[0]); py = float(pos[1])
        except: continue
        try: x = px - float(app.camera_x); y = py
        except: continue
        if x < -300 or x > app.width + 300: continue
        vis = app.remote_visuals.get(cid)
        if not vis: continue
        if app.enable_trails and vis.trail:
            drawTrail(vis.trail, vis.color, app.camera_x, is_local=False, facing=int(vis.facing))
        try:
            drawRect(x-15,y-20,30,40,fill=vis.color)
            # shadow - no opacity param for safety
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
            # Show remote score from MP
            r_score = remote.get("score", 0)
            if r_score>0:
                drawLabel(f"{r_score}", x, y-42, size=9, fill=rgb(255,235,100))
        except Exception as e:
            print(f"[BGS] draw remote fail {e}")
            continue

    drawRect(app.width//2,22,app.width,44,fill=rgb(0,0,0))
    status=f"BGS 60Hz | LOCAL:{len(app.world.players)} REMOTE:{len(app.remote_players)} COINS:{len([c for c in app.world.coins if not c.get('collected')])}/{len(app.world.coins)} TRAILS:{'ON' if app.enable_trails else 'OFF'}"
    if app.datastar_connected: status+=" | DATASTAR 60Hz"
    else: status+=" | LOCAL DEMO"
    if app.is_host: status+=" | HOST"
    drawLabel(status,app.width//2,14,size=11,fill=rgb(220,220,230))
    drawCircle(app.width-20,14,6,fill=rgb(100,255,100) if app.datastar_connected else rgb(255,200,100))

    y=50
    drawRect(90,y+20,160,20+len(app.world.players)*18,fill=rgb(0,0,0))
    drawLabel("LOCAL",90,y,size=12,fill=rgb(255,255,255)); y+=18
    for p in list(app.world.players.values())[:6]:
        drawLabel(f"{p.name}: {p.score}",90,y,size=11,fill=p.color); y+=18
    if app.remote_players:
        y+=10
        drawRect(90,y+10,160,10+len(app.remote_players)*16,fill=rgb(0,0,0))
        drawLabel("REMOTE (BGS 60Hz)",90,y,size=11,fill=rgb(180,200,255)); y+=14
        for cid, r in list(app.remote_players.items())[:6]:
            st=r.get("animationState","?"); sc=r.get("score",0)
            drawLabel(f"{cid[:6]} {st} ${sc}",90,y,size=10,fill=rgb(180,180,255)); y+=16

    if app.show_help:
        hx=app.width-160; hy=80
        drawRect(hx,hy+60,300,170,fill=rgb(0,0,0))
        drawLabel("BGS CONTROLS",hx,hy-20,size=12,fill=rgb(255,255,255))
        drawLabel("WASD / Arrows move",hx,hy,size=10,fill=rgb(200,220,255))
        drawLabel("R reset G trails P pause",hx,hy+16,size=10,fill=rgb(200,220,255))
        drawLabel("Trail: trailing edge",hx,hy+32,size=10,fill=rgb(255,235,100))
        drawLabel("facing=1 -> x - w",hx,hy+48,size=10,fill=rgb(180,200,255))
        drawLabel("facing=-1 -> x + w",hx,hy+64,size=10,fill=rgb(180,200,255))
        drawLabel("Coins: MP via char-state",hx,hy+80,size=10,fill=rgb(100,255,100))
        drawLabel(f"60Hz send: 16ms",hx,hy+96,size=10,fill=rgb(100,255,100))
        drawLabel(f"Collected: {len(app.local_collected_coins)}",hx,hy+112,size=10,fill=rgb(255,235,100))

    drawRect(app.width//2,app.height-18,app.width,36,fill=rgb(0,0,0))
    drawLabel("BGS 60Hz: PATCH char-state @16ms + SSE + coin sync | scs-datastar-extension compatible",app.width//2,app.height-18,size=9,fill=rgb(120,255,180))
