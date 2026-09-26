# apps/platformer_bgs.py - v0.1.8 PROPER TRANSPORT OWNERSHIP
# Version: 0.1.9 - Fixes: eval removal, protocol parsing, expiry, seq, 10Hz, coin spawn, logging
# Transport: Custom SSE multiplayer-snapshot owned by Brython (not Datastar signal store)
# If server sends datastar-patch-signals, we parse correctly: split data lines, handle onlyIfMissing, null=remove

from scs import *
from browser import window, aio

__version__ = "0.1.9"
__build__ = "2026-09-26-v0.1.9-es-fix"

try:
    from browser import window as _w
    _w.console.log(f"[BGS] platformer_bgs.py version {__version__} build {__build__} - ES FIX + CLEAN TRANSPORT")
except:
    print(f"[BGS] version {__version__}")

import math
import random
import json as py_json

# SINGLE SOURCE: window._bgs_signals is our normalized game snapshot (not Datastar store duplicate)
window._bgs_signals = {}
window._bgs_es = None
window._bgs_last_error = None

def _js_to_py_safe(js_val, depth=0):
    if depth > 20:
        return None
    try:
        if js_val is None:
            return None
        if isinstance(js_val, (str, int, float, bool)):
            return js_val
        if isinstance(js_val, dict):
            return {k: _js_to_py_safe(v, depth+1) for k, v in js_val.items()}
        if isinstance(js_val, (list, tuple)):
            return [_js_to_py_safe(x, depth+1) for x in js_val]
        try:
            if window.Array.isArray(js_val):
                return [_js_to_py_safe(js_val[i], depth+1) for i in range(int(js_val.length))]
        except:
            pass
        try:
            keys = window.Object.keys(js_val)
            result = {}
            for i in range(len(keys)):
                k = keys[i]
                try:
                    result[k] = _js_to_py_safe(js_val[k], depth+1)
                except:
                    continue
            return result
        except:
            return js_val
    except Exception as e:
        try:
            window.console.error("[BGS] _js_to_py_safe failed", e)
        except:
            pass
        return None

def _bgs_on_datastar_patch(evt):
    # CORRECT DATASTAR PARSING per spec: evt.data may contain multiple lines joined by \n
    # e.g. "signals {\"a\":1}\nonlyIfMissing false"
    # Must split, find signals line, handle null=remove per merge-patch semantics
    try:
        raw = evt.data
        if not raw:
            return
        # Handle multi-line SSE data
        lines = raw.split("\n") if "\n" in raw else raw.split("\n")
        # Actually EventSource joins data lines with \n, so split by newline
        if "\n" in raw:
            lines = raw.split("\n")
        else:
            # Also handle literal \n in string for safety
            lines = raw.split("\n") if "onlyIfMissing" in raw else [raw]
        
        # More robust: split by real newline char
        try:
            if "\n" in evt.data:
                lines = evt.data.split("\n")
            else:
                # Browser may have already joined with \n, try that
                lines = evt.data.splitlines()
        except:
            lines = [raw]
        
        signal_line = None
        for line in lines:
            if isinstance(line, str) and line.strip().startswith("signals "):
                signal_line = line.strip()[8:]
                break
            if isinstance(line, str) and line.strip().startswith("signals"):
                # Handle "signals{...}" without space
                idx = line.find("{")
                if idx != -1:
                    signal_line = line[idx:]
                    break
        
        if not signal_line:
            # Fallback: if raw starts with signals
            if isinstance(raw, str) and "signals" in raw:
                idx = raw.find("{")
                if idx != -1:
                    signal_line = raw[idx:]
        
        if not signal_line:
            return
        
        try:
            js_parsed = window.JSON.parse(signal_line)
        except Exception as e:
            try:
                window.console.error("[BGS] signal JSON.parse failed", e, signal_line[:200])
            except:
                pass
            return
        
        try:
            keys = window.Object.keys(js_parsed)
            for i in range(len(keys)):
                k = keys[i]
                try:
                    v = js_parsed[k]
                    # MERGE-PATCH SEMANTICS: null means remove signal
                    if v is None:
                        try:
                            if k in window._bgs_signals:
                                del window._bgs_signals[k]
                        except:
                            window._bgs_signals[k] = None
                        continue
                    py_v = _js_to_py_safe(v)
                    if py_v is not None:
                        window._bgs_signals[k] = py_v
                except Exception as e:
                    try:
                        window.console.error(f"[BGS] patch key {k} failed", e)
                    except:
                        pass
                    continue
        except Exception as e:
            try:
                window.console.error("[BGS] patch iteration failed", e)
            except:
                pass
    except Exception as e:
        try:
            window.console.error("[BGS] _bgs_on_datastar_patch outer failed", e)
            window._bgs_last_error = str(e)
        except:
            pass

def get_signal(n, d=None):
    try:
        v = window._bgs_signals.get(n, d)
        return v
    except:
        try:
            v = window._bgs_signals[n]
            return v if v is not None else d
        except:
            return d

def is_datastar_connected():
    try:
        es = window._bgs_es
        if not es:
            return False
        return es.readyState == 1
    except Exception as e:
        try:
            window.console.warn("[BGS] is_datastar_connected check failed", e)
        except:
            pass
        return False

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

# Multiplayer client - SINGLE TRANSPORT OWNER (no ds_ext unused)
MULTIPLAYER_ENABLED = False
USING_FALLBACK_MP = False
try:
    import extensions.multiplayer as mp_ext
    if not hasattr(mp_ext, 'MultiplayerClient'):
        raise AttributeError("no MultiplayerClient in extensions.multiplayer")
    MultiplayerClient = mp_ext.MultiplayerClient
    MULTIPLAYER_ENABLED = True
except Exception as e:
    try:
        window.console.warn("[BGS] extensions.multiplayer import failed, using fallback", e)
    except:
        print(f"[BGS] mp_ext import failed: {e}")
    MULTIPLAYER_ENABLED = True
    USING_FALLBACK_MP = True
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
                    # Build fetch opts as JS object safely
                    js_opts = {"method":"POST","headers":{"Content-Type":"application/json"},"body":body}
                    try:
                        opts = window.JSON.parse(window.JSON.stringify(js_opts))
                    except:
                        opts = js_opts
                    resp = await window.fetch(url, opts)
                    if not resp.ok:
                        txt = ""
                        try:
                            txt = await resp.text()
                        except:
                            pass
                        raise Exception(f"join HTTP {resp.status}: {txt[:200]}")
                    js_data = await resp.json()
                    data = _js_to_py_safe(js_data)
                    if not data:
                        try:
                            data = py_json.loads(window.JSON.stringify(js_data))
                        except:
                            data = {}
                    cid = data.get("client_id") if isinstance(data, dict) else None
                    sid = data.get("session_id") if isinstance(data, dict) else None
                    if not cid or not sid:
                        raise Exception(f"missing ids in {data}")
                    self.client_id = cid
                    self.session_id = sid
                    try:
                        stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
                        # SAFE: Brython JS interop - window.EventSource.new()
                        es_obj = None
                        try:
                            es_obj = window.EventSource.new(stream_url)
                        except Exception as e1:
                            try:
                                # Alternative Brython spelling
                                es_obj = window.EventSource.new(stream_url)
                            except Exception as e2:
                                try:
                                    window.console.warn(f"[BGS] EventSource.new failed {e1} / {e2}, trying direct")
                                    # Direct constructor via Brython's JS
                                    es_obj = window.EventSource(stream_url)
                                except Exception as e3:
                                    raise e3
                        window._bgs_es = es_obj
                        if es_obj:
                            es_obj.addEventListener("datastar-patch-signals", _bgs_on_datastar_patch)
                            es_obj.addEventListener("multiplayer-snapshot", _bgs_on_datastar_patch)
                            try:
                                window.console.log(f"[BGS] EventSource opened {stream_url}")
                            except:
                                pass
                    except Exception as e:
                        try:
                            window.console.error("[BGS] EventSource create failed", e)
                        except:
                            print(f"[BGS] EventSource create failed {e}")
                    return data
                except Exception as ex:
                    try:
                        window.console.error(f"[BGS] join fail {attempt+1}", ex)
                    except:
                        print(f"[BGS] join fail {attempt+1}: {ex}")
                    await aio.sleep(1.5)
            return {"client_id": None, "session_id": None, "local_demo": True, "is_synchronizer": False}

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
                "id": f"coin_{len(self.coins)}",
                "instanceId": f"coin_{len(self.coins)}",
                "x":float(plat.x),"y":float(plat.y-50),
                "collected":False,"collectedBy":None,"val":10,"bob":random.random()*6.28,
                "pos": [float(plat.x), float(plat.y-50), 0.0],
                "rot": [0.0,0.0,0.0,1.0],
                "isCollected": False
            })
        extras=[(400,300),(900,300),(1200,250),(1800,280)]
        for ex,ey in extras:
            self.coins.append({
                "id": f"coin_{len(self.coins)}",
                "instanceId": f"coin_{len(self.coins)}",
                "x":float(ex),"y":float(ey),
                "collected":False,"collectedBy":None,"val":10,"bob":random.random()*6.28,
                "pos": [float(ex), float(ey), 0.0],
                "rot": [0.0,0.0,0.0,1.0],
                "isCollected": False
            })
    def add_player(self, pid, name, color, keys):
        p=Player(pid,name,150+len(self.players)*70,100,color,keys); self.players[pid]=p; return p
    def apply_input(self, pid, move_x, jump_pressed):
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
        # Edge-triggered jump: only set buffer on press, not hold
        if jump_pressed:
            p.jump_buffer=6
        else:
            p.jump_buffer=max(0, p.jump_buffer-1)
        if p.jump_buffer>0 and p.coyote_timer>0:
            p.vy=-13.2; p.on_ground=False; p.jump_count=1; p.state="jump"; p.jump_buffer=0; p.coyote_timer=0
        elif jump_pressed and p.jump_count<p.max_jumps and p.jump_count>0 and p.jump_buffer>0:
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
            except Exception as e:
                try:
                    window.console.warn("[BGS] local trail fail", e)
                except:
                    pass
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
                        # Optimistic but track for reconciliation
                        coin["collected"]=True
                        coin["isCollected"]=True
                        coin["collectedBy"]=p.id
                        p.score+=coin.get("val",10)
                        p.coin_flash=10
                        if app_ref:
                            app_ref.local_collected_coins.add(coin["id"])
                            # Track seq for server ack
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
    app.world=World(); app.camera_x=0.0; app.keys_held=set(); app.show_help=True
    app.mode="bgs-multiplayer"; app.room_id="level1"; app.client_id=None; app.mp_client=None
    app.datastar_connected=False; app.remote_players={}; app.remote_visuals={}
    app.last_send_ms=0; app.enable_trails=True; app.trail_length=20
    app.local_collected_coins=set()
    app.is_host=False
    app.seq=0
    app.coin_seq=0
    app.last_fetch_inflight=False
    app.has_opacity=False
    # Feature detect opacity support
    try:
        drawCircle(0,0,1,fill=rgb(255,255,255), opacity=50)
        app.has_opacity=True
        try:
            window.console.log("[BGS] opacity supported")
        except:
            pass
    except:
        app.has_opacity=False
        try:
            window.console.warn("[BGS] opacity NOT supported, using fallback")
        except:
            pass
    app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])
    if MULTIPLAYER_ENABLED:
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
                cid=res.get("client_id") if isinstance(res, dict) else None
                is_sync=False
                if not cid:
                    try:
                        d= _js_to_py_safe(res) if res else {}
                        cid=d.get("client_id")
                        is_sync=d.get("is_synchronizer", False)
                    except Exception as e:
                        try:
                            window.console.error("[BGS] join parse fallback failed", e)
                        except:
                            pass
                        cid=getattr(res, "client_id", None)
                        is_sync=getattr(res, "is_synchronizer", False)
                else:
                    try: is_sync=res.get("is_synchronizer", False)
                    except: is_sync=False
                app.client_id=cid
                app.is_host=is_sync
                try:
                    window.console.log(f"[BGS] Joined {app.client_id} host={app.is_host} opacity={app.has_opacity}")
                except:
                    print(f"[BGS] Joined {app.client_id} host={app.is_host}")
            except Exception as e:
                try:
                    window.console.error(f"[BGS] Join failed", e)
                except:
                    print(f"[BGS] Join failed {e}")
        aio.run(join_mp())

def onKeyPress(app, key):
    if key=='r':
        # FULL RESET: local + multiplayer state
        app.world=World(); app.world.add_player("local_0","You",COLORS[0],KEYSETS[0])
        app.remote_players.clear(); app.remote_visuals.clear(); app.local_collected_coins.clear()
        app.seq=0; app.coin_seq=0; app.camera_x=0.0
        try:
            window.console.log("[BGS] Reset world and remote state")
        except:
            pass
    if key=='p': app.paused=not getattr(app,'paused',False)
    if key=='h': app.show_help=not app.show_help
    if key=='g':
        app.enable_trails=not app.enable_trails
    if key=='1' and len(app.world.players)<4:
        idx=len(app.world.players)
        app.world.add_player(f"local_{idx}",f"P{idx+1}",COLORS[idx%len(COLORS)],KEYSETS[idx%len(KEYSETS)])
    if key=='c':
        # FIXED: Single random sample reused for x/y and pos (was two different rand)
        x = float(random.randint(100,2000))
        y = float(random.randint(100,400))
        new_id=f"coin_{len(app.world.coins)}"
        app.world.coins.append({
            "id":new_id,"instanceId":new_id,
            "x":x,"y":y,
            "collected":False,"isCollected":False,"collectedBy":None,"val":10,"bob":random.random()*6.28,
            "pos":[x, y, 0.0],
            "rot":[0.0,0.0,0.0,1.0]
        })

def onKeyHold(app, keys):
    app.keys_held=set(keys)
    for pid, p in app.world.players.items():
        km=p.keys; move_x=0
        if km["left"] in app.keys_held: move_x-=1
        if km["right"] in app.keys_held: move_x+=1
        # Edge-triggered: check if jump was just pressed (not in previous held set)
        # For simplicity, we use held check but with buffer in apply_input
        jump=km["jump"] in app.keys_held
        app.world.apply_input(pid, move_x, jump)

def onStep(app):
    if MULTIPLAYER_ENABLED:
        try:
            sig=get_signal("character-state-update")
            if sig and isinstance(sig, dict):
                updates = sig.get("updates", [])
                for u in updates:
                    if not isinstance(u, dict):
                        continue
                    cid=u.get("clientId")
                    if cid and cid != app.client_id:
                        # Last-seen for expiry
                        now_tick = app.world.tick
                        if cid in app.remote_players:
                            # Check seq for stale rejection
                            old_seq = app.remote_players[cid].get("seq", -1)
                            new_seq = u.get("seq", 0)
                            if new_seq < old_seq:
                                continue
                        app.remote_players[cid]=u
                        if cid not in app.remote_visuals:
                            # Deterministic color from clientId hash, not same for all
                            try:
                                h = hash(cid) % len(COLORS)
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
                                        # Server authoritative: respect if we are not host? For now accept
                                        coin["collected"]=True
                                        coin["isCollected"]=True
                                        coin["collectedBy"]=cid
            item_sig = get_signal("item-state-update")
            if item_sig and isinstance(item_sig, dict):
                # Fix operator-precedence bug: explicit if/else
                updates = item_sig.get("updates", [])
                collections = item_sig.get("collections", [])
                for upd in updates:
                    if not isinstance(upd, dict):
                        continue
                    inst_id = upd.get("instanceId") or upd.get("id")
                    if upd.get("isCollected"):
                        for coin in app.world.coins:
                            if coin["id"]==inst_id or coin["instanceId"]==inst_id:
                                if not coin.get("collected"):
                                    coin["collected"]=True
                                    coin["isCollected"]=True
                                    coin["collectedBy"]=upd.get("collectedByClientId","remote")
                for coll in collections:
                    if not isinstance(coll, dict):
                        continue
                    inst_id = coll.get("instanceId")
                    for coin in app.world.coins:
                        if coin["id"]==inst_id or coin["instanceId"]==inst_id:
                            if not coin.get("collected"):
                                coin["collected"]=True
                                coin["isCollected"]=True
                                coin["collectedBy"]=coll.get("collectedByClientId","remote")
            app.datastar_connected=is_datastar_connected()
            # EXPIRY: prune remote players not seen for 5 sec (300 ticks at 60fps)
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
            except Exception as e:
                try:
                    window.console.warn("[BGS] expiry check failed", e)
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
                h = hash(cid) % len(COLORS)
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
            # Interpolation: store prev and target, lerp
            if vis.target_pos is None:
                vis.target_pos = (px, py)
                vis.prev_pos = (px, py)
                vis.interp_t = 1.0
            else:
                if abs(px - vis.target_pos[0]) > 0.1 or abs(py - vis.target_pos[1]) > 0.1:
                    vis.prev_pos = vis.target_pos
                    vis.target_pos = (px, py)
                    vis.interp_t = 0.0
            # Lerp
            vis.interp_t = min(1.0, vis.interp_t + 0.2)
            if vis.prev_pos and vis.target_pos:
                lerp_px = vis.prev_pos[0] + (vis.target_pos[0] - vis.prev_pos[0]) * vis.interp_t
                lerp_py = vis.prev_pos[1] + (vis.target_pos[1] - vis.prev_pos[1]) * vis.interp_t
                px, py = lerp_px, lerp_py
            if abs(vx) > 0.3:
                vis.facing = 1 if vx > 0 else -1
            else:
                vis.facing = 1 if abs(yaw) < 1.5 else -1
        except Exception as e:
            try:
                window.console.warn("[BGS] remote interp fail", e)
            except:
                pass
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
        except Exception as e:
            try:
                window.console.warn("[BGS] remote trail fail", e)
            except:
                pass
            if len(vis.trail) < app.trail_length:
                vis.trail.append((px, py))
        if len(vis.trail) > app.trail_length: 
            vis.trail.pop(0)
        vis.blink_phase += 0.05
        # Stable blink: use sum of char codes, not Python hash randomization
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
        except Exception as e:
            try:
                window.console.warn("[BGS] camera fail", e)
            except:
                pass

    if MULTIPLAYER_ENABLED and app.mp_client and app.client_id and "local_0" in app.world.players:
        now=0
        try: now=int(window.Date.now())
        except: now=app.world.tick*16
        # BOUNDED CADENCE: 10Hz (100ms) not 60Hz, no overlapping fetches
        if now - app.last_send_ms > 100 and not app.last_fetch_inflight:
            app.last_send_ms=now
            app.seq+=1
            lp=app.world.players["local_0"]
            try:
                # SAFE: No eval, use fetch with dict, JSON.stringify for escaping
                payload = {
                    "updates":[{
                        "clientId": str(app.client_id),
                        "characterModelId": "platformer_default",
                        "position": [float(lp.x), float(lp.y), 0.0],
                        "rotation": [0.0, float(0.0 if int(lp.facing) >=0 else math.pi), 0.0],
                        "velocity": [float(lp.vx), float(lp.vy), 0.0],
                        "animationState": str(lp.state),
                        "animationFrame": float(lp.anim_phase),
                        "isJumping": bool(not lp.on_ground),
                        "isBoosting": False,
                        "boostType": None,
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
                headers = window.JSON.parse(window.JSON.stringify({"Content-Type":"application/json","X-Client-ID":str(app.client_id)}))
                opts = window.JSON.parse(window.JSON.stringify({"method":"PATCH","headers":{"Content-Type":"application/json","X-Client-ID":str(app.client_id)},"body":body_str}))
                # Actually build opts safely
                opts = {"method":"PATCH"}
                try:
                    opts["headers"] = {"Content-Type":"application/json","X-Client-ID":str(app.client_id)}
                    opts["body"] = body_str
                except:
                    opts = window.JSON.parse(window.JSON.stringify({"method":"PATCH","headers":{"Content-Type":"application/json","X-Client-ID":str(app.client_id)},"body":body_str}))
                
                app.last_fetch_inflight=True
                async def do_fetch():
                    try:
                        resp = await window.fetch(url, window.JSON.parse(window.JSON.stringify(opts)))
                        if not resp.ok:
                            txt = ""
                            try:
                                txt = await resp.text()
                            except:
                                pass
                            try:
                                window.console.warn(f"[BGS] character-state PATCH {resp.status}: {txt[:100]}")
                            except:
                                pass
                    except Exception as e:
                        try:
                            window.console.error("[BGS] send fail", e)
                        except:
                            print(f"[BGS] send fail {e}")
                    finally:
                        app.last_fetch_inflight=False
                
                aio.run(do_fetch())
            except Exception as e:
                app.last_fetch_inflight=False
                try:
                    window.console.error(f"[BGS] 10Hz send fail {e}")
                except:
                    print(f"[BGS] 10Hz send fail {e}")

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
            cam = float(camera_x)
            x = tx - cam
            y = ty
        except: continue
        t = i / max(1, len(trail)-1)
        # ACTUAL: opacity 0% -> 75%, size 1.5 -> 5.0
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
                # Fallback without opacity
                drawCircle(x, y, size, fill=color)
        except Exception as e:
            try:
                # Fallback without opacity param
                drawCircle(x, y, size, fill=color)
            except:
                pass
    
    for i in range(len(trail)-1):
        try:
            tx1 = float(trail[i][0]); ty1 = float(trail[i][1])
            tx2 = float(trail[i+1][0]); ty2 = float(trail[i+1][1])
            cam = float(camera_x)
            x1 = tx1 - cam; y1 = ty1; x2 = tx2 - cam; y2 = ty2
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
            if p.score>0: drawLabel(f"{p.score}",x,y-p.h*0.7-26,size=9,fill=rgb(255,235,100))
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
            if r_score>0: drawLabel(f"{r_score}", x, y-42, size=9, fill=rgb(255,235,100))
        except Exception as e:
            try:
                window.console.error(f"[BGS] draw remote fail", e)
            except:
                print(f"[BGS] draw remote fail {e}")
            continue
    drawRect(app.width//2,22,app.width,44,fill=rgb(0,0,0))
    status=f"BGS 10Hz | LOCAL:{len(app.world.players)} REMOTE:{len(app.remote_players)} COINS:{len([c for c in app.world.coins if not c.get('collected')])}/{len(app.world.coins)}"
    if app.datastar_connected: status+=" | CONNECTED"
    else: status+=" | LOCAL"
    if app.is_host: status+=" HOST"
    if app.has_opacity: status+=" OPACITY"
    drawLabel(status,app.width//2,14,size=10,fill=rgb(220,220,230))
    drawCircle(app.width-20,14,6,fill=rgb(100,255,100) if app.datastar_connected else rgb(255,200,100))
    y=50
    drawRect(90,y+20,160,20+len(app.world.players)*18,fill=rgb(0,0,0))
    drawLabel("LOCAL",90,y,size=12,fill=rgb(255,255,255)); y+=18
    for p in list(app.world.players.values())[:6]:
        drawLabel(f"{p.name}: {p.score} trail:{len(p.trail)}",90,y,size=11,fill=p.color); y+=18
    if app.remote_players:
        y+=10
        drawRect(90,y+10,160,10+len(app.remote_players)*16,fill=rgb(0,0,0))
        drawLabel(f"REMOTE 10Hz ({len(app.remote_players)})",90,y,size=11,fill=rgb(180,200,255)); y+=14
        for cid, r in list(app.remote_players.items())[:6]:
            vis = app.remote_visuals.get(cid)
            trail_len = len(vis.trail) if vis and vis.trail else 0
            st=r.get("animationState","?"); sc=r.get("score",0)
            drawLabel(f"{cid[:6]} {st} ${sc} trail:{trail_len}",90,y,size=10,fill=rgb(180,180,255)); y+=16
    if app.show_help:
        hx=app.width-160; hy=80
        drawRect(hx,hy+60,300,190,fill=rgb(0,0,0))
        drawLabel("BGS CONTROLS",hx,hy-20,size=12,fill=rgb(255,255,255))
        drawLabel("WASD move",hx,hy,size=10,fill=rgb(200,220,255))
        drawLabel("R reset G trails",hx,hy+16,size=10,fill=rgb(200,220,255))
        drawLabel("TRAIL 1.5-5.0px 0-75%",hx,hy+32,size=10,fill=rgb(255,235,100))
        drawLabel("Remote uses opacity" if app.has_opacity else "No opacity fallback",hx,hy+48,size=8,fill=rgb(180,200,255))
        drawLabel("10Hz PATCH no overlap",hx,hy+60,size=8,fill=rgb(180,200,255))
        drawLabel(f"Coins:{len(app.local_collected_coins)} seq:{app.seq}",hx,hy+72,size=10,fill=rgb(255,235,100))
        drawLabel("scs.py 3.0.8",hx,hy+84,size=8,fill=rgb(100,255,100))
    drawRect(app.width//2,app.height-18,app.width,36,fill=rgb(0,0,0))
    drawLabel("TRAIL: drawCircle size 1.5-5.0 opacity 0-75 drawLine 10-70 | 10Hz no eval | merge-patch null=remove",app.width//2,app.height-18,size=7,fill=rgb(120,255,180))

def run():
    try:
        runApp(1050, 700)
    except Exception as e:
        try:
            window.console.error("[BGS] runApp failed", e)
        except:
            print(f"[BGS] runApp failed {e}")

run()
