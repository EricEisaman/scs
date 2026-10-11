"""
V13 — Multiplayer fix + Config screen, hands off proc_audio core
- Multiplayer: true split-screen like tetrio.webp — two boards, HOLD top, NEXT right, B2B/PIECES/ATTACK/TIME stats, VS SCORE, gray garbage
- Config: CONTROLS screen matching config.png — GUIDELINE/WASD/CUSTOM tabs, 18 actions, 3 bindings each, editable
- Preserves V12 audio calls (does not modify proc_audio.py core — only uses it)
- Fixed SOLO ZEN chip via canvas_ui dynamic width
"""

from scs import *
from browser import window, aio
import math, random, json as py_json, time

# ===== Audio — TETR.IO kinetic soundscape (proper sound) =====
# Uses proc_audio.py 1662-line core + proc_audio_tetrio.py extension — ONLY extensions path to avoid 404
# Implements: B2B escalating, thunder attacks, garbage pressure cues, clutch, surge, mode-varying BGM, Watchful Eye, Zenith floor adaptive
try:
    from extensions.proc_audio_tetrio import tetrio_sfx as _sfx, tetrio_bgm as _bgm_engine, TETR_PRESETS
    HAS_AUDIO = True
    HAS_TETRIO_AUDIO = True
    sfx = _sfx
    tetrio_bgm = _bgm_engine
    print(f"TETR.IO audio loaded: {len(TETR_PRESETS)} presets")
except Exception as e:
    print(f"tetrio audio import failed: {e}, trying base")
    try:
        from extensions.proc_audio import sfx as _sfx
        HAS_AUDIO = True
        HAS_TETRIO_AUDIO = False
        sfx = _sfx
        tetrio_bgm = None
        print("Base proc_audio loaded from extensions")
    except Exception as e2:
        print(f"proc_audio import failed: {e2}")
        HAS_AUDIO = False
        HAS_TETRIO_AUDIO = False
        sfx = None
        tetrio_bgm = None

try:
    from extensions.proc_audio import AudioEngine as _AudioEngine
    audio = _AudioEngine(quality="high")
except Exception as e3:
    print(f"AudioEngine load failed: {e3}")
    audio = None

# Fallback direct WebAudio (only for emergency)
_fallback_ctx = None
def _ensure_fallback_ctx():
    global _fallback_ctx
    if _fallback_ctx:
        return _fallback_ctx
    try:
        AC = getattr(window, "AudioContext", None) or getattr(window, "webkitAudioContext", None)
        if not AC:
            return None
        try:
            ctx = AC.new()
        except:
            ctx = window.AudioContext.new()
        _fallback_ctx = ctx
        return ctx
    except:
        return None

def _fallback_beep(freq=440, dur=0.10, vol=0.25, wave="sine"):
    try:
        ctx = _ensure_fallback_ctx()
        if not ctx:
            return
        if ctx.state == "suspended":
            try:
                ctx.resume()
            except:
                pass
        o = ctx.createOscillator()
        g = ctx.createGain()
        o.type = wave
        o.frequency.value = float(freq)
        g.gain.value = float(vol)
        g.gain.setValueAtTime(float(vol), ctx.currentTime)
        g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + dur)
        o.connect(g)
        g.connect(ctx.destination)
        o.start(ctx.currentTime + 0.01)
        o.stop(ctx.currentTime + dur + 0.05)
    except Exception as e:
        pass

# Proper TETR.IO kinetic SFX — escalating B2B, thunder, garbage pressure, clutch, surge
def play_sfx(name, **kw):
    if not HAS_AUDIO or not sfx:
        return
    try:
        sfx.resume()
        # Ensure seed for determinism
        if "seed" not in kw:
            kw["seed"] = random.randint(0, 999999)
        # Floor adaptive pitch for Zenith Tower — SFX pitch matches floor key
        floor = kw.get("floor", getattr(sfx, "_floor", 0))
        # Map generic names to tetr presets if using base
        if not HAS_TETRIO_AUDIO:
            tetr_map = {
                "tetr.move": "ui.hover",
                "tetr.rotate": "character.jump",
                "tetr.hold": "ui.coin_pickup",
                "tetr.softdrop": "ui.hover",
                "tetr.harddrop": "character.footstep_grass",
                "tetr.lock": "character.footstep_grass",
                "tetr.clear1": "ui.coin_pickup",
                "tetr.clear2": "ui.coin_pickup",
                "tetr.clear3": "ui.coin_pickup",
                "tetr.clear4": "weapon.laser_01",
                "tetr.tspin": "weapon.laser_01",
                "tetr.tspin_mini": "weapon.laser_01",
                "tetr.perfect_clear": "ui.coin_pickup",
                "tetr.combo1": "ui.coin_pickup",
                "tetr.b2b1": "weapon.laser_01",
                "tetr.garbage_incoming": "ui.hover",
                "tetr.clutch": "ui.coin_pickup",
                "tetr.topout": "character.jump",
            }
            base = name
            if "combo" in name: base = "tetr.combo1"
            if "b2b" in name: base = "tetr.b2b1"
            if "surge" in name: base = "tetr.b2b1"
            if "garbage" in name: base = "tetr.garbage_incoming"
            if "clutch" in name: base = "tetr.clutch"
            mapped = tetr_map.get(base, tetr_map.get(name, "ui.hover"))
            sfx.play(mapped, pitch=kw.get("pitch",1.0), brightness=kw.get("volume",0.35), seed=kw["seed"])
            return
        # TETR.IO proper: use tetrio_sfx which handles B2B escalating, thunder, garbage, clutch, surge
        # Pass through pitch/volume/seed/floor/lines
        sfx.play(name, **kw)
    except Exception as e:
        print(f"play_sfx failed {name}: {e}")

def play_bgm(name, **kw):
    # Mode-varying BGM per spec
    # TETRA LEAGUE: menu_watchful_eye fades instruments, adds drums spectating
    # Battle/victory/defeat distinct
    # Quick Play Zenith: floor adaptive, transitions support ascent, skip bars on fast climb
    if not HAS_AUDIO or not sfx:
        return
    try:
        sfx.resume()
        floor = kw.get("floor", 0)
        spectating = kw.get("spectating", False)
        if HAS_TETRIO_AUDIO and tetrio_bgm:
            # Use proper TETR.IO BGM engine
            tetrio_bgm.play(name, floor=floor, spectating=spectating)
        else:
            # Base fallback: silent (avoid 5s noise)
            try:
                sfx.mute("music", mute=False)
                sfx.set_volume("music", -24)
            except:
                pass
    except Exception as e:
        print(f"play_bgm failed {name}: {e}")

def stop_bgm():
    if not HAS_AUDIO or not sfx:
        return
    try:
        if HAS_TETRIO_AUDIO and tetrio_bgm:
            tetrio_bgm.stop()
        else:
            sfx.mute("music", mute=True)
    except:
        pass

def set_floor(floor):
    if not HAS_AUDIO or not sfx:
        return
    try:
        if HAS_TETRIO_AUDIO:
            sfx.set_floor(floor)
        if tetrio_bgm:
            tetrio_bgm.update_floor(floor)
    except:
        pass

def set_spectating(is_spec):
    try:
        if HAS_TETRIO_AUDIO and hasattr(sfx, 'set_spectating'):
            sfx.set_spectating(is_spec)
        if tetrio_bgm:
            tetrio_bgm.set_spectating(is_spec)
    except:
        pass


# Only extensions path — avoids 404
from extensions.canvas_ui import WaBreadcrumb, WaTabGroup, WaInput, WaAvatar, WaButton, WaBadge, WaDialog

# Global signals - V24 FIX from platformer_bgs: use Python global dict, not window dict (Brython window dict bug)
_bgs_signals_py = {}
try:
    window._bgs_signals = {}
except:
    pass
try:
    window._bgs_es = None
except:
    pass
ds_ext = None
USE_EXTENSION_SIGNAL_STORE = False

def _bgs_on_datastar_patch(evt):
    # V25 FIX: No inner imports — Brython $B.$import bug reading '2'/'3' when import inside function
    # Uses py_json (global import json as py_json) and window.JSON
    try:
        raw = evt.data
        if isinstance(raw, str) and raw.startswith("signals "):
            raw = raw[8:]
        parsed = None
        # Try py_json first
        try:
            parsed = py_json.loads(raw)
        except:
            try:
                # raw may be JS object already parsed by EventSource? Try window.JSON path
                js_obj = window.JSON.parse(raw) if isinstance(raw, str) else raw
                # Stringify via window.JSON then parse via py_json for Python dict
                json_str = window.JSON.stringify(js_obj)
                parsed = py_json.loads(json_str)
            except:
                # Last resort: if raw is already dict-like from Brython, use as is
                try:
                    parsed = raw if isinstance(raw, dict) else {}
                except:
                    parsed = {}
        if isinstance(parsed, dict):
            for kk, vv in parsed.items():
                _bgs_signals_py[kk] = vv
                try:
                    window._bgs_signals[kk] = vv
                except:
                    pass
    except Exception as ex:
        # print(f"[BGS] patch parse fail {ex}")
        pass

def get_signal(n,d=None):
    if USE_EXTENSION_SIGNAL_STORE and ds_ext:
        try:
            return ds_ext.get_signal(n,d)
        except:
            pass
    try:
        # V24: try Python global first (reliable)
        if n in _bgs_signals_py:
            return _bgs_signals_py.get(n,d)
        return window._bgs_signals.get(n,d)
    except:
        try:
            return _bgs_signals_py.get(n,d)
        except:
            return d

def is_datastar_connected():
    if USE_EXTENSION_SIGNAL_STORE and ds_ext:
        try:
            return ds_ext.is_datastar_connected()
        except:
            pass
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

# ---------- FORCED FALLBACK V25 — extension join has $B.$import bug reading '2'/'3', use inline V24 FIXED ----------
try:
    import extensions.multiplayer as mp_ext
    import extensions.datastar as ds_ext
    # Force fallback to avoid extension's Brython $B.$import bug in async join
    raise Exception("force fallback V25 to fix SIGMA $B.$import bug")
    if not hasattr(mp_ext,'MultiplayerClient'):
        raise AttributeError("cached mp_ext has no MultiplayerClient")
    MultiplayerClient = mp_ext.MultiplayerClient
    USE_EXTENSION_SIGNAL_STORE = True
    HAS_MP = True
    print("[BGS] MP imports OK from extensions/ - using V4 handlers")
except Exception as e:
    print(f"[BGS] MP import failed ({e}) - using inline fallback client V24 FIXED")
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
            base_url = self.base_url
            env_name = self.environment_name
            char_name = self.character_name
            for attempt in range(retries):
                try:
                    url = base_url + "/api/multiplayer/join"
                    payload = {"environment_name": env_name, "character_name": char_name}
                    body = window.JSON.stringify(payload)
                    print(f"[BGS] Joining {url} env={env_name} attempt {attempt+1}")
                    resp = await window.fetch(url, {"method":"POST","headers":{"Content-Type":"application/json"},"body":body,"mode":"cors"})
                    # check ok - Render 502 returns no CORS
                    ok = True
                    try:
                        _tmp_ok = resp.ok
                    except:
                        ok = True
                    if not ok:
                        raise Exception(f"HTTP {resp.status if hasattr(resp,'status') else 'fail'}")
                    js_data = await resp.json()
                    data = py_json.loads(window.JSON.stringify(js_data))
                    cid = data.get("client_id")
                    sid = data.get("session_id")
                    if not cid or not sid:
                        raise Exception("missing ids")
                    self.client_id = cid
                    self.session_id = sid
                    print(f"[BGS] Joined {cid} sid={sid} - MP V24")
                    try:
                        stream_url = base_url + "/api/multiplayer/stream?sid=" + str(sid)
                        es_obj = window.eval("new EventSource('" + stream_url + "')")
                        window._bgs_es = es_obj
                        es_obj.addEventListener("datastar-patch-signals", _bgs_on_datastar_patch)
                        print(f"[BGS] SSE OPEN V24 {stream_url}")
                    except Exception as sse_e:
                        print(f"[BGS] SSE fail {sse_e}")
                    return data
                except Exception as ex:
                    print(f"[BGS] join fail attempt {attempt+1}: {ex}")
                    # No aio.sleep to avoid $B.$import bug, use JS promise delay via window
                    try:
                        await window.eval("new Promise(r=>setTimeout(r,1500))")
                    except:
                        pass
            print("[BGS] join failed after retries - running LOCAL DEMO mode")
            return {"client_id": None, "session_id": None, "local_demo": True}
def send_bgs_patch(app,path,payload):
    try:
        url=app.mp_client.base_url+path
        headers={"Content-Type":"application/json","X-Client-ID":str(app.client_id)}
        body=py_json.dumps(payload,separators=(",",":"))
        script=f"fetch({py_json.dumps(url)},{{method:'PATCH',headers:{py_json.dumps(headers)},body:{py_json.dumps(body)}}}).catch(function(e){{}})"
        window.eval(script); return True
    except: return False

def drawRoundedRect(x, y, width, height, radius, fill, border=None, borderWidth=1, opacity=100):
    r = max(0, min(radius, width/2, height/2))
    if r == 0:
        drawRect(x, y, width, height, fill=fill, border=border, borderWidth=borderWidth, opacity=opacity)
        return
    if border and borderWidth>0:
        if width > 2*r:
            drawRect(x+r, y, width-2*r, height, fill=border, opacity=opacity)
        if height > 2*r:
            drawRect(x, y+r, width, height-2*r, fill=border, opacity=opacity)
        for cx in (x+r, x+width-r):
            for cy in (y+r, y+height-r):
                drawCircle(cx, cy, r, fill=border, opacity=opacity)
        if fill:
            ir = max(0, r-borderWidth)
            ix = x+borderWidth; iy = y+borderWidth; iw = width-2*borderWidth; ih = height-2*borderWidth
            if iw>0 and ih>0:
                if iw > 2*ir:
                    drawRect(ix+ir, iy, iw-2*ir, ih, fill=fill, opacity=opacity)
                if ih > 2*ir:
                    drawRect(ix, iy+ir, iw, ih-2*ir, fill=fill, opacity=opacity)
                for cx in (ix+ir, ix+iw-ir):
                    for cy in (iy+ir, iy+ih-ir):
                        drawCircle(cx, cy, ir, fill=fill, opacity=opacity)
        return
    if fill:
        if width > 2*r:
            drawRect(x+r, y, width-2*r, height, fill=fill, opacity=opacity)
        if height > 2*r:
            drawRect(x, y+r, width, height-2*r, fill=fill, opacity=opacity)
        for cx in (x+r, x+width-r):
            for cy in (y+r, y+height-r):
                drawCircle(cx, cy, r, fill=fill, opacity=opacity)

BOARD_W, BOARD_H_INTERNAL = 10, 40
BOARD_H_VISIBLE = 20
CELL = 28
CELL_MP = 20  # smaller for 1v1 split
PREVIEW_CELL = 14
PREVIEW_CELL_MP = 11
TETROMINOES = {'I':[[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],'J':[[1,0,0],[1,1,1],[0,0,0]],'L':[[0,0,1],[1,1,1],[0,0,0]],'O':[[1,1],[1,1]],'S':[[0,1,1],[1,1,0],[0,0,0]],'T':[[0,1,0],[1,1,1],[0,0,0]],'Z':[[1,1,0],[0,1,1],[0,0,0]]}
COLORS = {'I':rgb(0,212,212),'J':rgb(0,75,212),'L':rgb(212,127,0),'O':rgb(212,212,0),'S':rgb(0,212,0),'T':rgb(138,0,212),'Z':rgb(212,0,0),'G':rgb(80,80,80)}
COLORS_MP = {'I':rgb(0,200,200),'J':rgb(30,90,220),'L':rgb(220,140,10),'O':rgb(220,210,10),'S':rgb(20,200,20),'T':rgb(150,20,220),'Z':rgb(220,20,20),'G':rgb(85,85,85)}
KICKS_JLSTZ={(0,1):[(0,0),(-1,0),(-1,1),(0,-2),(-1,-2)],(1,0):[(0,0),(1,0),(1,-1),(0,2),(1,2)],(1,2):[(0,0),(1,0),(1,-1),(0,2),(1,2)],(2,1):[(0,0),(-1,0),(-1,1),(0,-2),(-1,-2)],(2,3):[(0,0),(1,0),(1,1),(0,-2),(1,-2)],(3,2):[(0,0),(-1,0),(-1,-1),(0,2),(-1,2)],(3,0):[(0,0),(-1,0),(-1,-1),(0,2),(-1,2)],(0,3):[(0,0),(1,0),(1,1),(0,-2),(1,-2)]}
KICKS_I={(0,1):[(0,0),(-2,0),(1,0),(-2,-1),(1,2)],(1,0):[(0,0),(2,0),(-1,0),(2,1),(-1,-2)],(1,2):[(0,0),(-1,0),(2,0),(-1,2),(2,-1)],(2,1):[(0,0),(1,0),(-2,0),(1,-2),(-2,1)],(2,3):[(0,0),(2,0),(-1,0),(2,1),(-1,-2)],(3,2):[(0,0),(-2,0),(1,0),(-2,-1),(1,2)],(3,0):[(0,0),(1,0),(-2,0),(1,-2),(-2,1)],(0,3):[(0,0),(-1,0),(2,0),(-1,2),(2,-1)]}
# TETR.IO 180 KICK TABLE — from 1400px-TETR.IO_180kicks.png
# Engine tries every kick left to right until one fits. If none, rotation canceled.
# Note: no downward 180 kicks from East/West — instead "jumps" that kick 2 up.
KICKS_180_JLSTZ={
    (0,2):[(0,0),(0,1),(1,1),(-1,1),(1,0),(-1,0)],  # NORTH->SOUTH: NO KICK, OFF-THE-FLOOR, UNHOOK RIGHT/LEFT, RIGHT/LEFT ZIPPER
    (2,0):[(0,0),(0,-1),(-1,-1),(1,-1),(-1,0),(1,0)], # SOUTH->NORTH: NO KICK, OFF-THE-CEILING, UNHOOK LEFT/RIGHT, LEFT/RIGHT ZIPPER
    (1,3):[(0,0),(1,0),(1,2),(1,1),(0,2),(0,1)],     # EAST->WEST: NO KICK, OFF-THE-WALL, TALL JUMP, CONSTRICTED JUMP, TALL ZIPPER, CONSTRICTED ZIPPER
    (3,1):[(0,0),(-1,0),(-1,2),(-1,1),(0,2),(0,1)],  # WEST->EAST: NO KICK, OFF-THE-WALL, TALL JUMP, CONSTRICTED JUMP, TALL ZIPPER, CONSTRICTED ZIPPER
}
KICKS_180_I={
    (0,2):[(0,0),(0,1)],  # N->S: try no kick first, then OFF-THE-FLOOR up1
    (2,0):[(0,0),(0,-1)], # S->N: no kick, OFF-THE-CEILING down1
    (1,3):[(0,0),(1,0)],  # E->W: no kick, OFF-THE-WALL right
    (3,1):[(0,0),(-1,0)], # W->E: no kick, OFF-THE-WALL left
}
KICKS_180_O={
    (0,2):[(0,0)],
    (2,0):[(0,0)],
    (1,3):[(0,0)],
    (3,1):[(0,0)],
}
BASE_ATTACK={(1,False,False,False):0,(2,False,False,False):1,(3,False,False,False):2,(4,False,False,False):4,(0,True,False,False):0,(1,True,False,False):2,(2,True,False,False):4,(3,True,False,False):6,(1,True,True,False):0,(2,True,True,False):1,(0,False,False,True):10}
def calc_attack(base,combo,mode="DOWN"):
    if combo<=0: return base
    if base==0: val=math.log(1+1.25*combo) if combo>=2 else 0
    else: val=base*(1+0.25*combo)
    return math.floor(val) if mode=="DOWN" else math.floor(val)+(1 if random.random()<(val-math.floor(val)) else 0)
def make_empty_match(local_id="local"):
    return {"version":"tetr_mp_v1_single","match_id":f"tetr_{int(time.time()*1000)}_{random.randint(1000,9999)}","environment":"tetr_1v1","max_players":2,"opponent_lock":True,"players":{"local":{"id":local_id,"tr":12500.0},"opponent":None},"queue":{"status":"idle"},"rules":{"garbage_target":"single_opponent_only","garbage_system":"change_on_attack","garbage_messiness":0.15,"passthrough":False,"b2b_system":"charging","combo_system":"multiplier","opener_phase":14,"playfield":"10x40"},"garbage":{"incoming":[],"outgoing":[]}}
class SingleOpponentClient:
    def __init__(self,app): self.app=app; self.match=make_empty_match(); self.search_timer=0
    def getOpponent(self): return self.match["players"]["opponent"]
    def hasOpponent(self): return self.match["players"]["opponent"] is not None
    def findOpponent(self):
        if self.hasOpponent(): return self.getOpponent()
        self.match["queue"]["status"]="searching"; self.search_timer=0; return None
    def _secureOpponent(self,opp):
        if self.match["players"]["opponent"] is not None: return False
        self.match["players"]["opponent"]=opp; self.match["queue"]["status"]="matched"; return True
    def cancelSearch(self):
        if not self.hasOpponent(): self.match["queue"]["status"]="idle"; self.search_timer=0
def rotate_matrix(mat,dir):
    if dir==1: return [list(reversed(col)) for col in zip(*mat)]
    elif dir==-1:
        m=mat
        for _ in range(3): m=[list(reversed(col)) for col in zip(*m)]
        return m
    else:
        m=mat
        for _ in range(2): m=[list(reversed(col)) for col in zip(*m)]
        return m
class Piece:
    def __init__(self,kind=None):
        self.kind=kind or random.choice(list(TETROMINOES.keys()))
        self.shape=[r[:] for r in TETROMINOES[self.kind]]
        self.x=BOARD_W//2-len(self.shape[0])//2; self.y=0; self.rot=0
class Board:
    def __init__(self):
        self.grid=[[None]*BOARD_W for _ in range(BOARD_H_INTERNAL)]
        self.can_hold=True; self.b2b_streak=-1; self.combo=-1; self.surge_charged=0; self.attack=0; self.lines=0; self.pieces_placed=0; self.zen=False
    def collides(self,piece,dx=0,dy=0,shape=None):
        sh=shape or piece.shape
        for r in range(len(sh)):
            for c in range(len(sh[0])):
                if not sh[r][c]: continue
                x=piece.x+c+dx; y=piece.y+r+dy
                if x<0 or x>=BOARD_W or y>=BOARD_H_INTERNAL: return True
                if y>=0 and self.grid[y][x] is not None: return True
        return False
    def add_garbage(self,lines,hole,mess=0.0):
        if self.zen:
            for _ in range(lines):
                if any(self.grid[0][c] is not None for c in range(BOARD_W)):
                    self.grid.pop(0); self.grid.insert(0,[None]*BOARD_W)
                cur=hole if random.random()>mess else random.randint(0,BOARD_W-1)
                self.grid.pop(0); self.grid.append([('G' if c!=cur else None) for c in range(BOARD_W)])
            return False
        for _ in range(lines):
            if any(self.grid[0][c] is not None for c in range(BOARD_W)): return True
            cur=hole if random.random()>mess else random.randint(0,BOARD_W-1)
            self.grid.pop(0); self.grid.append([('G' if c!=cur else None) for c in range(BOARD_W)])
        return False
    def clear_lines(self):
        ng=[]; cl=0
        for row in self.grid:
            if all(c is not None for c in row): cl+=1
            else: ng.append(row)
        for _ in range(cl): ng.insert(0,[None]*BOARD_W)
        self.grid=ng; return cl
    def is_tspin(self,piece):
        if piece.kind!='T': return False,False
        corners=[(piece.x,piece.y),(piece.x+2,piece.y),(piece.x,piece.y+2),(piece.x+2,piece.y+2)]
        filled=0
        for cx,cy in corners:
            if cx<0 or cx>=BOARD_W or cy>=BOARD_H_INTERNAL or (cy>=0 and self.grid[cy][cx] is not None): filled+=1
        return filled>=3, filled==3
    def is_pc(self): return all(all(c is None for c in r) for r in self.grid)
    def lock_piece(self,piece):
        for r in range(len(piece.shape)):
            for c in range(len(piece.shape[0])):
                if piece.shape[r][c]:
                    x=piece.x+c; y=piece.y+r
                    if 0<=y<BOARD_H_INTERNAL and 0<=x<BOARD_W: self.grid[y][x]=piece.kind
        self.can_hold=True; self.pieces_placed+=1
def new_bag():
    b=list(TETROMINOES.keys()); random.shuffle(b); return b
class TetrGame:
    def __init__(self,mode="tetra_league"):
        self.mode=mode; self.board=Board(); self.board.zen=(mode=="zen")
        self.bag=new_bag(); self.next_queue=[]
        for _ in range(5):
            if not self.bag: self.bag=new_bag()
            self.next_queue.append(self.bag.pop())
        self.current=Piece(self.next_queue.pop(0))
        if not self.bag: self.bag=new_bag()
        self.next_queue.append(self.bag.pop())
        self.hold_piece=None; self.ghost_y=0; self.lock_delay=0; self.lock_max=45 if mode=="zen" else 30; self.gravity_timer=0
        self.gravity_speed=60 if mode=="zen" else 22 if mode=="40lines" else 18 if mode=="blitz" else 40
        self.das_left=0; self.das_right=0; self.soft_drop=False; self.game_over=False
        self.stats={"apm":0,"pps":0,"attack":0,"pieces":0,"start":time.time(),"lines":0,"score":0}
        self.rounding="DOWN" if mode not in ("quick_play","blitz") else "RNG"
    def spawn(self):
        k=self.next_queue.pop(0)
        if not self.bag: self.bag=new_bag()
        self.next_queue.append(self.bag.pop())
        self.current=Piece(k); self.lock_delay=0
        if self.board.collides(self.current):
            if self.mode=="zen":
                for _ in range(6):
                    if any(self.board.grid[0][c] is not None for c in range(BOARD_W)):
                        self.board.grid.pop(0); self.board.grid.insert(0,[None]*BOARD_W)
                if self.board.collides(self.current): self.current.y=-2
            else: self.game_over=True
    def try_move(self,dx,dy):
        if self.game_over: return False
        if not self.board.collides(self.current,dx,dy):
            self.current.x+=dx; self.current.y+=dy
            if dx!=0: self.lock_delay=0
            return True
        return False
    def try_rotate(self,dir):
        if self.game_over: return False
        old=[r[:] for r in self.current.shape]; old_rot=self.current.rot; ox,oy=self.current.x,self.current.y
        new=rotate_matrix(old,dir); new_rot=(old_rot+(1 if dir==1 else -1 if dir==-1 else 2))%4
        # Proper kicks: 90 deg uses SRS, 180 uses TETR.IO 180 table from image
        if dir==2 or abs(new_rot-old_rot)==2:
            if self.current.kind=='I':
                kicks=KICKS_180_I
            elif self.current.kind=='O':
                kicks=KICKS_180_O
            else:
                kicks=KICKS_180_JLSTZ
        else:
            kicks=KICKS_I if self.current.kind=='I' else KICKS_JLSTZ
        table=kicks.get((old_rot,new_rot),[(0,0)])
        for kx,ky in table:
            self.current.shape=new; self.current.x=ox+kx; self.current.y=oy-ky; self.current.rot=new_rot
            if not self.board.collides(self.current): self.lock_delay=0; return True
        self.current.shape=old; self.current.rot=old_rot; self.current.x=ox; self.current.y=oy
        return False
    def update_ghost(self):
        gy=self.current.y
        while not self.board.collides(self.current,0,gy-self.current.y+1): gy+=1
        self.ghost_y=gy
    def lock(self):
        is_tspin,is_mini=self.board.is_tspin(self.current)
        self.board.lock_piece(self.current)
        cleared=self.board.clear_lines()
        is_pc=self.board.is_pc() and cleared>0
        if is_pc: base=10 if self.mode!="quick_play" else 3
        else: base=BASE_ATTACK.get((cleared,is_tspin,is_mini,False),0)
        difficult=cleared==4 or is_tspin or is_pc
        if difficult:
            if self.board.b2b_streak>=0: base+=1
            self.board.b2b_streak+=1
            if self.board.b2b_streak>=4: self.board.surge_charged=self.board.b2b_streak if self.mode!="quick_play" else max(1,self.board.b2b_streak-3)
        else:
            if cleared>0 and self.board.b2b_streak>=4: base+=self.board.surge_charged; self.board.surge_charged=0
            if cleared>0: self.board.b2b_streak=-1
        cur_combo=self.board.combo+1 if cleared>0 else self.board.combo
        attack=calc_attack(base,cur_combo,self.rounding)
        if self.mode=="quick_play" and cleared==1 and not is_tspin and self.board.combo<0: attack=max(attack,1)
        is_opener=self.board.pieces_placed<=14
        if cleared>0:
            self.board.combo+=1
            self.stats["lines"]+=cleared; self.stats["score"]+= [0,100,300,500,800][cleared] if cleared<=4 else 800
        else: self.board.combo=-1
        self.board.attack=attack; self.board.lines+=cleared; self.stats["attack"]+=attack; self.stats["pieces"]+=1
        return attack,cleared,is_tspin,is_pc,is_opener,difficult

def handle_piece_lock(app, attack, cleared, is_tspin, is_pc, is_opener, difficult):
    inc=app.mp_wrapper.match["garbage"]["incoming"]
    had_incoming = len(inc) > 0
    floor = app.tetr.stats["lines"] // 5 if app.tetr.mode in ("zen","40lines","blitz") else app.tetr.stats["lines"] // 8
    # Lock with subtle pitch variation from combo for momentum
    play_sfx("tetr.lock", pitch=0.95+app.tetr.board.combo*0.02, floor=floor)
    if cleared:
        # Clutch — own effect when clearing under pressure
        if had_incoming and cleared>=2: 
            play_sfx("tetr.clutch", volume=0.9, floor=floor)
        if is_pc: 
            play_sfx("tetr.perfect_clear", volume=1.0, floor=floor)
        elif is_tspin:
            # T-Spin punctuates achievement, pitch escalates with B2B for momentum
            b2b_pitch = 1.0+app.tetr.board.b2b_streak*0.045
            if cleared==1: 
                play_sfx("tetr.tspin_mini" if app.tetr.board.combo<0 else "tetr.tspin", pitch=b2b_pitch, volume=0.95, floor=floor)
            else: 
                play_sfx("tetr.tspin", pitch=b2b_pitch, volume=0.98, floor=floor)
        else:
            # Clears — increasingly consequential, musical, forceful
            b2b_pitch = 1.0+app.tetr.board.b2b_streak*0.035
            if cleared==1: 
                play_sfx("tetr.clear1", pitch=b2b_pitch, floor=floor)
            elif cleared==2: 
                play_sfx("tetr.clear2", pitch=b2b_pitch*1.02, floor=floor)
            elif cleared==3: 
                play_sfx("tetr.clear3", pitch=b2b_pitch*1.04, floor=floor)
            elif cleared>=4: 
                # Thunder impact for powerful attacks
                play_sfx("tetr.clear4", volume=1.1, pitch=b2b_pitch, floor=floor)
        if app.tetr.board.combo>=1:
            combo_n = app.tetr.board.combo+1
            # Combo escalates — sustained success sounds increasingly consequential
            play_sfx(f"tetr.combo{combo_n}", volume=0.6+min(combo_n*0.04,0.4), pitch=1.0+combo_n*0.04, floor=floor)
        if difficult and app.tetr.board.b2b_streak>=1:
            b2b_n = app.tetr.board.b2b_streak
            # Back-to-back chains receive escalating audio cues
            play_sfx(f"tetr.b2b{b2b_n}", volume=0.65+min(b2b_n*0.05,0.35), pitch=1.0+b2b_n*0.03, floor=floor)
        if app.tetr.board.b2b_streak>=4:
            # Surge changing with streak — audible conversation of building pressure
            play_sfx(f"tetr.surge{app.tetr.board.surge_charged}", volume=0.7, floor=floor)
        if app.tetr.mode in ("zen","40lines","blitz"):
            set_floor(floor)
    remaining=attack
    if app.tetr.mode in ("zen","40lines","blitz"):
        app.tetr.board.attack=0; return
    if is_opener and inc and remaining>0:
        pending=sum(g["lines"] for g in inc)
        if remaining < pending:
            cancel=remaining*2
            while cancel>0 and inc:
                g=inc[0]
                if g["lines"]<=cancel: cancel-=g["lines"]; inc.pop(0)
                else: g["lines"]-=cancel; cancel=0
            remaining=0
        else:
            while remaining>0 and inc:
                g=inc[0]
                if g["lines"]<=remaining: remaining-=g["lines"]; inc.pop(0)
                else: g["lines"]-=remaining; remaining=0
    else:
        while remaining>0 and inc:
            g=inc[0]
            if g["lines"]<=remaining: remaining-=g["lines"]; inc.pop(0)
            else: g["lines"]-=remaining; remaining=0
    app.tetr.board.attack=remaining
    if inc and cleared==0 and random.random()<0.12:
        g=inc.pop(0)
        topped=app.tetr.board.add_garbage(g["lines"],g["hole"],0.15)
        play_sfx("tetr.garbage_incoming", volume=0.6+g["lines"]*0.08, pitch=0.9+g["lines"]*0.06, floor=floor, lines=g["lines"])  # pressure cue
        if topped and not app.tetr.board.zen: 
            play_sfx("tetr.topout")
            app.tetr.game_over=True
    if attack>0 and app.single_opponent_id:
        play_sfx("tetr.garbage_incoming", volume=0.5+min(attack*0.12,0.5), pitch=1.0+attack*0.04, floor=floor, lines=attack)  # audible pressure

# ===== KEYBINDS =====
DEFAULT_BINDS_GUIDELINE = {
    "move_left": ["ARROWLEFT","[NOT SET]","[NOT SET]"],
    "move_right": ["ARROWRIGHT","[NOT SET]","[NOT SET]"],
    "soft_drop": ["ARROWDOWN","[NOT SET]","[NOT SET]"],
    "hard_drop": ["ARROWUP","[NOT SET]","[NOT SET]"],
    "rotate_ccw": ["KEYZ","[NOT SET]","[NOT SET]"],
    "rotate_cw": ["KEYX","[NOT SET]","[NOT SET]"],
    "rotate_180": ["KEYC","[NOT SET]","[NOT SET]"],
    "hold": ["SHIFTLEFT","[NOT SET]","[NOT SET]"],
    "forfeit": ["ALTLEFT","[NOT SET]","[NOT SET]"],
    "retry": ["CONTROLLEFT","[NOT SET]","[NOT SET]"],
    "open_chat": ["SLASH","[NOT SET]","[NOT SET]"],
    "target_even": ["[NOT SET]","[NOT SET]","[NOT SET]"],
    "target_elim": ["[NOT SET]","[NOT SET]","[NOT SET]"],
    "target_random": ["[NOT SET]","[NOT SET]","[NOT SET]"],
    "target_payback": ["[NOT SET]","[NOT SET]","[NOT SET]"],
    "menu_up": ["[NOT SET]","[NOT SET]","[NOT SET]"],
    "menu_down": ["[NOT SET]","[NOT SET]","[NOT SET]"],
    "menu_left": ["[NOT SET]","[NOT SET]","[NOT SET]"],
    "menu_right": ["[NOT SET]","[NOT SET]","[NOT SET]"],
}
DEFAULT_BINDS_WASD = {
    "move_left": ["KEYA","ARROWLEFT","[NOT SET]"],
    "move_right": ["KEYD","ARROWRIGHT","[NOT SET]"],
    "soft_drop": ["KEYS","ARROWDOWN","[NOT SET]"],
    "hard_drop": ["KEYW","ARROWUP","[NOT SET]"],
    "rotate_ccw": ["KEYZ","ARROWLEFT","[NOT SET]"],
    "rotate_cw": ["KEYX","ARROWRIGHT","[NOT SET]"],
    "rotate_180": ["KEYC","[NOT SET]","[NOT SET]"],
    "hold": ["KEYC","SHIFTLEFT","[NOT SET]"],
    "forfeit": ["ESCAPE","[NOT SET]","[NOT SET]"],
    "retry": ["KEYR","[NOT SET]","[NOT SET]"],
    "open_chat": ["KEYT","[NOT SET]","[NOT SET]"],
    "target_even": ["DIGIT1","[NOT SET]","[NOT SET]"],
    "target_elim": ["DIGIT2","[NOT SET]","[NOT SET]"],
    "target_random": ["DIGIT3","[NOT SET]","[NOT SET]"],
    "target_payback": ["DIGIT4","[NOT SET]","[NOT SET]"],
    "menu_up": ["ARROWUP","KEYW","[NOT SET]"],
    "menu_down": ["ARROWDOWN","KEYS","[NOT SET]"],
    "menu_left": ["ARROWLEFT","KEYA","[NOT SET]"],
    "menu_right": ["ARROWRIGHT","KEYD","[NOT SET]"],
}
ACTION_LABELS = [
    ("move_left","MOVE FALLING PIECE LEFT"),
    ("move_right","MOVE FALLING PIECE RIGHT"),
    ("soft_drop","SOFT DROP"),
    ("hard_drop","HARD DROP"),
    ("rotate_ccw","ROTATE COUNTERCLOCKWISE"),
    ("rotate_cw","ROTATE CLOCKWISE"),
    ("rotate_180","ROTATE 180"),
    ("hold","SWAP HOLD PIECE"),
    ("forfeit","FORFEIT GAME"),
    ("retry","RETRY GAME"),
    ("open_chat","OPEN CHAT"),
    ("target_even","TARGETING STRATEGY EVEN"),
    ("target_elim","TARGETING STRATEGY ELIMINATIONS"),
    ("target_random","TARGETING STRATEGY RANDOM"),
    ("target_payback","TARGETING STRATEGY PAYBACK"),
    ("menu_up","MENUS: UP"),
    ("menu_down","MENUS: DOWN"),
    ("menu_left","MENUS: LEFT"),
    ("menu_right","MENUS: RIGHT"),
]

def onAppStart(app):
    app.width=1120; app.height=700; app.stepsPerSecond=60
    app.background=rgb(18,19,23)
    try:
        window.eval('''if(!window._tetrio_space_fix){window._tetrio_space_fix=true; window.addEventListener("keydown", function(e){ const isSpace=e.code==="Space"||e.key===" "||e.keyCode===32; if(isSpace){ const ae=document.activeElement; const isInput=ae && (ae.tagName==="INPUT"||ae.tagName==="TEXTAREA"||ae.isContentEditable); if(!isInput){ e.preventDefault(); } } }, {passive:false, capture:true});}''')
    except: pass

    app.tetr=TetrGame(mode="zen")
    app.mp_wrapper=SingleOpponentClient(app)
    app.game_state="title"
    app.username="Player1"
    app.room_id="tetr_zen"; app.client_id=None; app.mp_client=None; app.datastar_connected=False
    app.remote_players={}; app.single_opponent_id=None; app.single_opponent_board=None
    app.last_send_ms=0; app.last_character_state=None; app.remote_timestamps={}
    # TETR.IO welcome screen state — enter username to join, blank = random
    app.welcome_state="enter"  # enter | available | taken | login
    app.welcome_username=""  # what user typed
    app.welcome_password=""  # for registered login
    app.welcome_error=""
    app.welcome_anon=True  # is anonymous?
    app.is_anonymous=False  # final flag
    app.registered_users={"OSK","ZET","TETR.IO","ADMIN","MOD","BOT"}  # simulated registered names
    app.random_names=["GUEST","ANON","TETRON","BLOCKER","STACKER","SPINNER","CLUTCH","ZENITH","BLITZ","COMBO","B2B","T-SPIN","PERFECT","TETRA","LEAGUE","QUICK","SWEeper","LINES","ATTACK","GARBAGE"]
    # Load registered from localStorage if available
    try:
        ls = window.localStorage
        if ls:
            reg = ls.getItem("tetrio_registered")
            if reg:
                extra = py_json.loads(reg)
                if isinstance(extra, list):
                    for n in extra:
                        app.registered_users.add(n.upper())
    except:
        pass

    BOARD_X=420; BOARD_Y=95
    HOLD_W=100
    HOLD_X=BOARD_X - HOLD_W - 16
    NEXT_X=BOARD_X + BOARD_W*CELL + 12
    app.BOARD_X=BOARD_X; app.BOARD_Y=BOARD_Y; app.NEXT_X=NEXT_X; app.HOLD_X=HOLD_X; app.OPP_X=NEXT_X+128+18
    app.board_x=BOARD_X; app.board_y=BOARD_Y; app.opp_board_x=app.OPP_X; app.opp_board_y=BOARD_Y

    app.titleItems=[
        {"id":"multiplayer","label":"MULTIPLAYER","sub":"PLAY ONLINE WITH FRIENDS AND FOES","icon":"MP","color":rgb(232,90,130),"dark":rgb(45,20,32),"y":120},
        {"id":"solo","label":"SOLO","sub":"CHALLENGE YOURSELF AND TOP THE LEADERBOARDS","icon":"1P","color":rgb(130,120,220),"dark":rgb(25,25,45),"y":195},
        {"id":"tetra","label":"TETRA CHANNEL","sub":"LEADERBOARDS, REPLAYS AND MORE","icon":"4CH","color":rgb(90,210,120),"dark":rgb(20,45,30),"y":270},
        {"id":"config","label":"CONFIG","sub":"TWEAK YOUR TETR.IO EXPERIENCE","icon":"CFG","color":rgb(90,160,230),"dark":rgb(20,35,55),"y":345},
        {"id":"about","label":"ABOUT","sub":"ALL ABOUT TETR.IO","icon":"ABT","color":rgb(140,140,150),"dark":rgb(35,35,38),"y":420},
    ]

    app.breadcrumb=WaBreadcrumb(20,8,["Home","Arcade","TETR.IO 1v1","SOLO"])
    app.tabGroup=WaTabGroup(20,28,w=520,tabs=["Tetra League","Quick Play","ZEN","40 LINES","BLITZ"])
    app.tabGroup.active=2
    app.avatarLocal=WaAvatar(20,68,size=36,initials="YOU",variant="brand")
    app.inputName=WaInput(66,72,w=150,h=28,placeholder="Player1",value="Player1",label="")
    app.inputName.focused=False
    app.avatarOpp=WaAvatar(20,110,size=36,initials="OPP",variant="neutral")
    app.badgeOPP=WaBadge("SOLO ZEN",66,118,variant="neutral")
    app.btnFind=WaButton("FIND OPPONENT (1v1 BGS)",20,156,w=200,h=36,variant="brand",onClick=lambda: start_search(app))
    app.btnCancel=WaButton("CANCEL",20,156,w=200,h=36,variant="neutral",appearance="outlined",onClick=lambda: cancel_search(app))
    app.btnBot=WaButton("PLAY VS BOT",20,200,w=200,h=32,variant="warning",appearance="outlined",onClick=lambda: play_vs_bot(app))
    app.btnReset=WaButton("RESET (R)",20,156,w=200,h=36,variant="brand",onClick=lambda: reset_game(app))
    app.btnBack=WaButton("BACK TO HOME",20,600,w=200,h=32,variant="neutral",appearance="outlined",onClick=lambda: go_title(app))
    app.btnConfig=WaButton("CONFIG",20,560,w=200,h=32,variant="neutral",appearance="outlined",onClick=lambda: go_config(app))
    app.badgeTR=WaBadge("TR 12500",20,204,variant="brand")
    app.badgeAPM=WaBadge("APM 0",100,204,variant="success")
    app.badgePPS=WaBadge("PPS 0",170,204,variant="warning")

    # config state
    app.configTab="CUSTOM"
    app.keybinds = {k:v[:] for k,v in DEFAULT_BINDS_WASD.items()}
    app.keybinds_guideline = {k:v[:] for k,v in DEFAULT_BINDS_GUIDELINE.items()}
    app.keybinds_custom = {k:v[:] for k,v in DEFAULT_BINDS_WASD.items()}
    app.config_selected = None  # (action, slot)
    app.config_scroll = 0

    if HAS_MP:
        base_url="https://scs-207.onrender.com"
        try:
            if hasattr(window,'location') and 'localhost' in window.location.hostname:
                base_url="http://localhost:10000"
        except:
            pass
        app.mp_client=MultiplayerClient(base_url=base_url,environment_name="tetr_1v1",character_name="TetrPlayer")
        def on_char_state(updates):
            for u in updates:
                cid=u.get("clientId")
                if cid and cid!=app.client_id:
                    app.remote_players[cid]=u
        if hasattr(app.mp_client,'on_character_state'):
            app.mp_client.on_character_state=on_char_state

        async def join_mp():
            try:
                res=await app.mp_client.join()
                cid=res.get("client_id") if isinstance(res,dict) else None
                if not cid:
                    try:
                        json_str = window.JSON.stringify(res) if hasattr(window,'JSON') else "{}"
                        d=py_json.loads(json_str) if isinstance(json_str, str) else {}
                        cid=d.get("client_id")
                    except:
                        cid=getattr(res,"client_id",None)
                if not cid:
                    cid = f"local_{int(time.time()*1000)}_{random.randint(1000,9999)}"
                    print(f"BGS offline, using local {cid}")
                app.client_id=cid
                print(f"Joined BGS as {cid}")
            except Exception as e:
                print(f"Join failed {e}")
                app.client_id = f"local_{int(time.time()*1000)}_{random.randint(1000,9999)}"

        try:
            aio.run(join_mp())
        except Exception as e:
            print(f"aio.run join failed {e}")
            app.client_id = f"local_{int(time.time()*1000)}_{random.randint(1000,9999)}"
        if not app.client_id:
            app.client_id = f"local_{int(time.time()*1000)}_{random.randint(1000,9999)}"
            print(f"Fallback local id {app.client_id}")

    app.dialogGameOver=WaDialog("Match Finished","You topped out.",w=380,h=160,variant="danger")
    app.dialogGameOver.buttons=[WaButton("RETRY (R)",0,0,w=110,h=36,variant="brand",onClick=lambda: reset_game(app)), WaButton("MENU",0,0,w=80,h=36,variant="neutral",appearance="outlined",onClick=lambda: go_title(app))]
    app.das=10; app.arr=2; app.sdf=6
    app.audio_ready=False
    if HAS_AUDIO:
        try:
            sfx.resume()
            app.audio_ready=True
            play_bgm("bgm.menu_watchful_eye", spectating=False)
        except: pass

def go_title(app):
    app.game_state="title"
    app.dialogGameOver.hide()
    app.single_opponent_id=None
    app.mp_wrapper.match["queue"]["status"]="idle"
    app.badgeOPP.text="SOLO ZEN"
    app.inputName.focused=False
    stop_bgm()
    play_bgm("bgm.menu_watchful_eye", spectating=False)
    play_sfx("ui.back")

def go_config(app):
    app.game_state="config"
    app.config_selected=None
    play_sfx("ui.click")

def start_search(app):
    if HAS_AUDIO:
        try: sfx.resume()
        except: pass
    play_sfx("ui.click")
    stop_bgm()
    tab=app.tabGroup.tabs[app.tabGroup.active]
    if "ZEN" in tab: mode="zen"; env="tetr_zen"; bgm="bgm.zen"
    elif "40" in tab: mode="40lines"; env="tetr_40l"; bgm="bgm.40lines"
    elif "BLITZ" in tab: mode="blitz"; env="tetr_blitz"; bgm="bgm.blitz"
    elif "Quick" in tab: mode="quick_play"; env="tetr_1v1_quick"; bgm="bgm.battle_tetra_league"
    else: mode="tetra_league"; env="tetr_1v1"; bgm="bgm.battle_tetra_league"
    app.room_id=env; app.tetr=TetrGame(mode=mode)
    app.inputName.focused=False
    if mode in ("zen","40lines","blitz"):
        app.game_state="playing"; app.single_opponent_id=None; app.badgeOPP.text=f"SOLO {mode.upper()}"
        play_bgm(bgm, floor=0)
    else:
        app.mp_wrapper.findOpponent(); app.game_state="searching"; app.single_opponent_id=None; app.badgeOPP.text="SEARCHING..."
        play_bgm("bgm.menu_watchful_eye", spectating=True)

def cancel_search(app): 
    app.mp_wrapper.cancelSearch(); app.game_state="menu"; app.single_opponent_id=None; app.badgeOPP.text="NO OPP"; app.inputName.focused=False
    stop_bgm()
    play_bgm("bgm.menu_watchful_eye", spectating=False)
    play_sfx("ui.back")

def play_vs_bot(app):
    # User explicitly chose to play bot — no auto-match
    opp={"id":f"bot_{random.randint(1000,9999)}","tr":12000,"bot_ai":{"timer":0}}
    if app.single_opponent_id is None:
        app.single_opponent_id=opp["id"]; app.mp_wrapper._secureOpponent(opp); app.game_state="playing"; app.tetr=TetrGame(mode=app.tetr.mode); app.badgeOPP.text=f"BOT {opp['id'][-4:]}"; app.inputName.focused=False
        stop_bgm()
        play_bgm("bgm.battle_tetra_league")
        play_sfx("ui.click")
        play_sfx("tetr.clutch", volume=0.8)


def reset_game(app):
    cur=app.tetr.mode; app.tetr=TetrGame(mode=cur); app.mp_wrapper.match["garbage"]["incoming"]=[]; app.dialogGameOver.hide()
    app.game_state="playing"; app.inputName.focused=False
    set_floor(0)
    play_sfx("ui.click")

def onStep(app):
    if app.game_state=="title" or app.game_state=="config": return
    if HAS_MP:
        try:
            sig=get_signal("character-state-update")
            if sig and isinstance(sig, dict):
                for u in sig.get("updates",[]):
                    cid=u.get("clientId")
                    if not cid or cid==app.client_id:
                        continue
                    if app.tetr.mode in ("zen","40lines","blitz"):
                        continue
                    if app.single_opponent_id is None:
                        # Lock to real client ID for 1v1, store username separately for display
                        app.single_opponent_id=cid
                        app.single_opponent_username=str(u.get("username",""))[:16] if "username" in u else cid[:6]
                        app.mp_wrapper._secureOpponent({"id":cid, "username": app.single_opponent_username})
                        app.badgeOPP.text=f"OPP {app.single_opponent_username[:4].upper()}"
                        print(f"[BGS] Locked opponent {cid} username={app.single_opponent_username}")
                        stop_bgm()
                        play_bgm("bgm.battle_tetra_league")
                        play_sfx("tetr.clutch", volume=0.8)
                    # Only process designated opponent (strict clientId lock for 1v1)
                    if cid!=app.single_opponent_id:
                        continue
                    ts=u.get("timestamp",0)
                    if ts>app.remote_timestamps.get(cid,-1):
                        app.remote_timestamps[cid]=ts
                        app.remote_players[cid]=u
                        # Full board with types preferred
                        # Username always update for display
                        if "username" in u:
                            app.single_opponent_username = str(u.get("username",""))[:16]
                        if "isAnonymous" in u:
                            app.single_opponent_anon = bool(u.get("isAnonymous", False))
                        if "tetrBoardFull" in u:
                            app.single_opponent_board = u.get("tetrBoardFull")
                        elif "tetrBoard" in u:
                            app.single_opponent_board = u.get("tetrBoard")
                        # Meta
                        if "tetrScore" in u:
                            app._opp_score = int(u.get("tetrScore",0))
                        if "tetrB2B" in u:
                            app._opp_b2b = int(u.get("tetrB2B",0))
                        if "tetrCombo" in u:
                            app._opp_combo = int(u.get("tetrCombo",0))
                        if "tetrAPM" in u:
                            app._opp_apm = int(u.get("tetrAPM",0))
                        if "tetrPPS" in u:
                            app._opp_pps = float(u.get("tetrPPS",0))
                        if "tetrHold" in u:
                            app._opp_hold = u.get("tetrHold")
                        if "tetrNext" in u:
                            app._opp_next = u.get("tetrNext",[])[:5]
                        if "tetrCurrent" in u:
                            app._opp_cur = u.get("tetrCurrent")
                            app._opp_cur_x = float(u.get("tetrCurrentX",0))
                            app._opp_cur_y = float(u.get("tetrCurrentY",0))
                        if "tetrAttack" in u:
                            atk=int(u.get("tetrAttack",0))
                            if atk>0:
                                hole=random.randint(0,BOARD_W-1)
                                app.mp_wrapper.match["garbage"]["incoming"].append({"lines":atk,"hole":hole})
                                play_sfx("tetr.garbage_incoming", volume=0.5+min(atk*0.12,0.5), pitch=1.0+atk*0.04)
            app.datastar_connected=is_datastar_connected()
        except Exception as _e:
            print(f"[BGS] onStep parse fail {_e}")
            pass
    if app.game_state=="searching":
        app.mp_wrapper.search_timer+=1
        if app.single_opponent_id is not None: 
            # Found real opponent via BGS — start
            app.game_state="playing"; app.tetr=TetrGame(mode=app.tetr.mode); app.inputName.focused=False
            stop_bgm()
            play_bgm("bgm.battle_tetra_league")
        # NO auto-bot — user must choose PLAY VS BOT or keep waiting
    if app.game_state!="playing": return
    if app.tetr.game_over: 
        app.game_state="gameover"; app.dialogGameOver.show()
        stop_bgm()
        if app.tetr.mode in ("zen","40lines","blitz"): play_sfx("bgm.defeat")
        else: play_bgm("bgm.defeat"); play_sfx("tetr.topout")
        return
    if app.tetr.mode=="40lines" and app.tetr.stats["lines"]>=40:
        app.game_state="gameover"; app.dialogGameOver.title="40 LINES CLEAR!"; app.dialogGameOver.message=f"Time: {time.time()-app.tetr.stats['start']:.2f}s"; app.dialogGameOver.show()
        stop_bgm(); play_sfx("bgm.victory"); play_sfx("tetr.perfect_clear", volume=1.0)
        return
    if app.tetr.mode=="blitz":
        elapsed=time.time()-app.tetr.stats["start"]
        if elapsed>=120: 
            app.game_state="gameover"; app.dialogGameOver.title="BLITZ FINISH!"; app.dialogGameOver.message=f"Score: {app.tetr.stats['score']} lines {app.tetr.stats['lines']}"; app.dialogGameOver.show()
            stop_bgm(); play_sfx("bgm.victory")
            return
    app.tetr.gravity_timer+=1
    grav=app.tetr.gravity_speed
    if app.tetr.soft_drop: grav=max(1,40//max(1,int(app.sdf)))
    if app.tetr.gravity_timer>=grav:
        app.tetr.gravity_timer=0
        if not app.tetr.try_move(0,1):
            app.tetr.lock_delay+=1
            if app.tetr.lock_delay>app.tetr.lock_max:
                attack,cleared,tspin,is_pc,is_opener,difficult=app.tetr.lock()
                handle_piece_lock(app,attack,cleared,tspin,is_pc,is_opener,difficult)
                app.tetr.spawn(); app.tetr.lock_delay=0
        else: app.tetr.lock_delay=0
    if app.tetr.das_left>0:
        app.tetr.das_left+=1
        if app.tetr.das_left>app.das:
            if (app.tetr.das_left-app.das) % max(1,app.arr+1)==0: 
                if app.tetr.try_move(-1,0): play_sfx("tetr.move", pitch=0.98, volume=0.35)
    if app.tetr.das_right>0:
        app.tetr.das_right+=1
        if app.tetr.das_right>app.das:
            if (app.tetr.das_right-app.das) % max(1,app.arr+1)==0: 
                if app.tetr.try_move(1,0): play_sfx("tetr.move", pitch=1.02, volume=0.35)
    app.tetr.update_ghost()
    elapsed=max(1,time.time()-app.tetr.stats["start"])
    app.badgeAPM.text=f"APM {int(app.tetr.stats['attack']/elapsed*60)}"
    app.badgePPS.text=f"PPS {app.tetr.stats['pieces']/elapsed:.2f}"
    if app.tetr.mode in ("zen","40lines"):
        floor = app.tetr.stats["lines"] // 5
        if floor != getattr(app, "_last_floor", -1):
            app._last_floor = floor
            set_floor(floor)
    if HAS_MP and app.mp_client and app.client_id and app.game_state in ("searching","playing") and app.tetr.mode not in ("zen","40lines","blitz"):
        now=0
        try: now=int(window.Date.now())
        except: now=int(app.tetr.board.lines*100)
        # === TETR.IO-appropriate sync schema — full board with types ===
        kind_to_code = {"I":1,"J":2,"L":3,"O":4,"S":5,"T":6,"Z":7,"G":8}
        flat=[]
        flat_full=[]
        for r in range(BOARD_H_INTERNAL-20,BOARD_H_INTERNAL):
            for c in range(BOARD_W):
                k = app.tetr.board.grid[r][c]
                if k is None:
                    flat.append(0)
                    flat_full.append(0)
                else:
                    flat.append(1)
                    flat_full.append(kind_to_code.get(k,8))
        cur_kind = getattr(app.tetr.current, 'kind', 'T')
        cur_x = float(app.tetr.current.x)
        cur_y = float(app.tetr.current.y)
        cur_rot = int(getattr(app.tetr.current, 'rot', 0))
        hold_kind = app.tetr.hold_piece if app.tetr.hold_piece else None
        next_queue = app.tetr.next_queue[:5] if hasattr(app.tetr, 'next_queue') else []
        ghost_y = float(getattr(app.tetr, 'ghost_y', cur_y))
        elapsed = max(1, time.time()-app.tetr.stats["start"])
        pps = app.tetr.stats["pieces"]/elapsed
        apm = int(app.tetr.stats["attack"]/elapsed*60)
        board_hash = sum(flat_full[::7])
        state=(round(cur_x,2),round(cur_y,2),cur_rot,cur_kind,board_hash,int(app.tetr.board.attack),int(app.tetr.board.b2b_streak),int(app.tetr.board.combo))
        changed=state!=app.last_character_state
        if now-app.last_send_ms>=80 and (changed or now-app.last_send_ms>=600):
            app.last_send_ms=now; app.last_character_state=state
            payload={"updates":[{
                "clientId":str(app.client_id),
                "characterModelId":"tetr-1v1",
                "position":[cur_x,cur_y],
                "velocity":[float(app.tetr.board.attack),float(app.tetr.board.combo)],
                "animationState":"topped" if app.tetr.game_over else "playing",
                "score":int(app.tetr.stats["score"]),
                "lines":int(app.tetr.stats["lines"]),
                "timestamp":now,
                "username":str(app.username)[:16],
                "isAnonymous":bool(app.is_anonymous),
                "tetrBoard":flat,
                "tetrBoardFull":flat_full,
                "tetrBoardW":BOARD_W,
                "tetrBoardH":BOARD_H_VISIBLE,
                "tetrCurrent":cur_kind,
                "tetrCurrentX":cur_x,
                "tetrCurrentY":cur_y,
                "tetrCurrentRot":cur_rot,
                "tetrGhostY":ghost_y,
                "tetrHold":hold_kind,
                "tetrNext":next_queue,
                "tetrAttack":int(app.tetr.board.attack),
                "tetrB2B":int(app.tetr.board.b2b_streak),
                "tetrSurge":int(app.tetr.board.surge_charged),
                "tetrCombo":int(app.tetr.board.combo),
                "tetrAPM":int(apm),
                "tetrPPS":float(f"{pps:.2f}"),
                "tetrLines":int(app.tetr.stats["lines"]),
                "tetrScore":int(app.tetr.stats["score"]),
                "tetrPieces":int(app.tetr.stats["pieces"]),
                "tetrTime":int(elapsed),
                "tetrGarbageIncoming":len(app.mp_wrapper.match["garbage"]["incoming"]),
            }],"timestamp":now}
            send_bgs_patch(app,"/api/multiplayer/character-state",payload)
            if app.tetr.board.attack>0: app.tetr.board.attack=0


def redrawAll(app):
    if app.game_state=="title":
        drawTitleScreen(app)
        return
    if app.game_state=="config":
        drawConfigScreen(app)
        return
    drawRect(0,0,app.width,app.height,fill=rgb(18,19,23))
    app.breadcrumb.draw()
    app.tabGroup.draw()

    active_tab = app.tabGroup.tabs[app.tabGroup.active] if hasattr(app.tabGroup,'tabs') and app.tabGroup.active < len(app.tabGroup.tabs) else ""
    is_solo_tab = any(k in active_tab for k in ("ZEN","40 LINES","BLITZ"))
    is_mp_tab = not is_solo_tab
    is_mp_mode = app.tetr.mode not in ("zen","40lines","blitz")
    is_mp = is_mp_tab and (is_mp_mode or app.game_state in ("menu","searching","playing","gameover"))

    if is_mp:
        # MP — true split-screen, no overlapping HUD
        # Connection indicator top-right, not behind HOLD
        try:
            col = rgb(100,255,100) if app.datastar_connected else rgb(255,180,80) if app.client_id else rgb(255,80,80)
            # Top bar connection — to the right of tabs, not overlapping board
            drawRoundedRect(540, 32, 160, 22, 6, rgb(30,32,48), border=rgb(60,65,90), borderWidth=1)
            drawCircle(552, 43, 4, fill=col)
            status = "BGS" if app.datastar_connected else f"{str(app.client_id)[:8]}" if app.client_id else "OFFLINE"
            drawLabel(status, 562, 38, size=8, fill=rgb(180,180,200), bold=True, align="left-top")
            drawLabel("BOT READY" if not app.datastar_connected else "VS", 620, 38, size=8, fill=rgb(120,200,120) if not app.datastar_connected else rgb(120,140,180), bold=True, align="left-top")
        except:
            pass

        app.btnBack.draw()
        bh = BOARD_H_VISIBLE*CELL_MP
        base_y = 110 + bh + 16  # boards now at y=110
        if app.game_state=="searching":
            app.btnCancel.x = app.width/2 - 220
            app.btnCancel.y = base_y
            app.btnCancel.w = 200
            app.btnBot.x = app.width/2 + 20
            app.btnBot.y = base_y
            app.btnBot.w = 200
            app.btnCancel.draw()
            app.btnBot.draw()
        elif app.game_state in ("menu","title"):
            app.btnFind.x = app.width/2 - 100
            app.btnFind.y = base_y
            app.btnFind.draw()
        elif app.game_state=="menu":
            # MODE PICKER SECOND SCREEN — MUST HAVE: tabs for mode + FIND + CONFIG
            app.btnFind.x = app.width/2 - 220
            app.btnFind.y = base_y
            app.btnFind.w = 200
            app.btnFind.draw()
            app.btnConfig.x = app.width/2 + 20
            app.btnConfig.y = base_y
            app.btnConfig.w = 200
            app.btnConfig.draw()
            app.btnBack.x = app.width/2 - 100
            app.btnBack.y = base_y + 48
            app.btnBack.draw()
        else:
            app.btnReset.x = app.width/2 - 100
            app.btnReset.y = base_y
            app.btnReset.draw()
        draw_multiplayer_vs(app)
    else:
        # SOLO — original centered layout
        app.avatarLocal.draw()
        app.inputName.draw()
        app.avatarOpp.draw()
        app.badgeOPP.draw()
        if app.game_state=="playing": 
            app.btnReset.draw()
        elif app.game_state=="searching": 
            app.btnCancel.draw()
        else: 
            app.btnReset.draw()
        app.btnBack.draw()
        app.badgeTR.draw()
        app.badgeAPM.draw()
        app.badgePPS.draw()
        if app.game_state in ("playing","searching","gameover","menu"):
            draw_tetrio_frame(app)
            draw_board_tetrio(app,app.tetr.board,app.board_x,app.board_y,CELL,app.tetr.current,app.tetr.ghost_y,True)
            draw_hold_tetrio(app)
            draw_next_tetrio(app)
            draw_opponent_tetrio(app)
            draw_stats_tetrio(app)
            draw_garbage_meter(app)

    app.dialogGameOver.draw(app.width,app.height)
    if app.dialogGameOver.open:
        cx=app.width/2; cy=app.height/2
        app.dialogGameOver.buttons[0].x=cx-110; app.dialogGameOver.buttons[0].y=cy+30
        app.dialogGameOver.buttons[1].x=cx+10; app.dialogGameOver.buttons[1].y=cy+30
        for b in app.dialogGameOver.buttons: b.draw()
    drawLabel(f"BGS | {app.room_id} | {app.tetr.mode.upper()} | {'🔊' if HAS_AUDIO else '🔇'} | {app.client_id or 'no-id'}",app.width/2,app.height-10,size=8,fill=rgb(90,90,95))
    drawCircle(app.width-16,12,4,fill=rgb(100,255,100) if app.datastar_connected else rgb(255,180,80))

# ===== TITLE =====
def drawTitleScreen(app):
    # TETR.IO welcome screen — enter username to join, blank = random
    # Matches spec: "enter a username to join, or leave it blank to get a random one."
    # If available: STAY ANONYMOUS or REGISTER
    # If registered: ask password, login or back
    # Blank -> random name
    # Anonymous cannot submit leaderboard or ranked
    drawRect(0,0,app.width,app.height,fill=rgb(18,19,23))
    drawRoundedRect(0,0,app.width,28,0,rgb(25,26,32))
    drawLabel("HOME",20,14,size=12,fill=rgb(200,200,210),bold=True,align="left-top")
    anon_label = f"ANONYMOUS" if app.is_anonymous else (app.username if app.username else "GUEST")
    drawLabel(f"TETR.IO  {anon_label}",app.width-20,14,size=10,fill=rgb(220,80,80) if app.is_anonymous else rgb(120,200,120),bold=True,align="right-top")

    # Center card — TETR.IO welcome
    cx = app.width//2
    card_w = 460
    card_x = cx - card_w//2
    card_y = 88
    card_h = 420

    drawRoundedRect(card_x-2,card_y-2,card_w+4,card_h+4,16,rgb(0,0,0),opacity=30)
    drawRoundedRect(card_x,card_y,card_w,card_h,14,rgb(32,36,52),border=rgb(70,80,110),borderWidth=1.2)

    # Logo
    drawLabel("TETR.IO",cx,card_y+38,size=32,fill=rgb(240,240,255),bold=True)
    drawLabel("WELCOME BACK" if app.welcome_state!="enter" else "WELCOME",cx,card_y+68,size=12,fill=rgb(160,170,190),bold=True)

    # State: enter username
    if app.welcome_state=="enter":
        drawLabel("enter a username to join, or leave it blank to get a random one.",cx,card_y+96,size=9,fill=rgb(140,150,170),align="center")
        # Input field
        input_w = 300
        input_x = cx - input_w//2
        input_y = card_y+118
        is_focused = getattr(app.inputName,'focused',False) or app.welcome_state=="enter"
        bg = rgb(22,26,38) if not is_focused else rgb(28,34,52)
        border = rgb(90,110,160) if is_focused else rgb(60,70,95)
        drawRoundedRect(input_x,input_y,input_w,38,8,bg,border=border,borderWidth=1.2)
        txt = app.welcome_username if app.welcome_username else ""
        placeholder = "username"
        if txt:
            drawLabel(txt,input_x+12,input_y+19,size=13,fill=rgb(230,235,245),bold=True,align="left-top")
        else:
            drawLabel(placeholder,input_x+12,input_y+19,size=13,fill=rgb(100,110,130),align="left-top")
        # Cursor
        if is_focused:
            try:
                blink = int(time.time()*2) % 2
                if blink==0:
                    drawRect(input_x+12+len(txt)*7.2,input_y+10,2,18,fill=rgb(180,190,220))
            except:
                pass
        # JOIN button
        btn_w = 300
        btn_x = cx - btn_w//2
        btn_y = input_y+56
        drawRoundedRect(btn_x+1,btn_y+2,btn_w,36,8,rgb(0,0,0),opacity=18)
        drawRoundedRect(btn_x,btn_y,btn_w,36,8,rgb(90,100,220),border=rgb(120,130,250),borderWidth=1)
        drawLabel("JOIN",cx,btn_y+18,size=14,fill="white",bold=True)

        # Error
        if app.welcome_error:
            drawLabel(app.welcome_error,cx,btn_y+54,size=9,fill=rgb(255,120,120),bold=True)

        # Info bottom
        drawLabel("Anonymous players cannot submit leaderboard scores",cx,card_y+card_h-52,size=8,fill=rgb(110,120,140))
        drawLabel("or participate in ranked matchmaking.",cx,card_y+card_h-40,size=8,fill=rgb(110,120,140))

    elif app.welcome_state=="available":
        # Nickname available — choose STAY ANONYMOUS or REGISTER
        drawLabel(f'"{app.welcome_username}" is available!',cx,card_y+96,size=12,fill=rgb(120,220,130),bold=True)
        drawLabel("You can play anonymously with this name, or register to claim it.",cx,card_y+118,size=8,fill=rgb(140,150,170))
        # Buttons
        btn_w = 300
        btn_x = cx - btn_w//2
        # Stay anonymous
        y1 = card_y+150
        drawRoundedRect(btn_x+1,y1+2,btn_w,38,8,rgb(0,0,0),opacity=18)
        drawRoundedRect(btn_x,y1,btn_w,38,8,rgb(45,55,80),border=rgb(80,95,130),borderWidth=1)
        drawLabel("STAY ANONYMOUS",cx,y1+19,size=12,fill=rgb(200,210,230),bold=True)
        drawLabel(f'Play as "{app.welcome_username}" without account',cx,y1+32,size=7,fill=rgb(110,120,140))
        # Register
        y2 = y1+62
        drawRoundedRect(btn_x+1,y2+2,btn_w,38,8,rgb(0,0,0),opacity=18)
        drawRoundedRect(btn_x,y2,btn_w,38,8,rgb(90,160,90),border=rgb(120,200,120),borderWidth=1)
        drawLabel("REGISTER",cx,y2+19,size=12,fill="white",bold=True)
        drawLabel(f'Claim "{app.welcome_username}" with password',cx,y2+32,size=7,fill=rgb(200,230,200))
        # Back
        drawLabel("BACK",cx,card_y+card_h-32,size=10,fill=rgb(120,130,150),bold=True)

    elif app.welcome_state=="taken":
        # Nickname belongs to registered account — ask password
        drawLabel(f'"{app.welcome_username}" is taken!',cx,card_y+96,size=12,fill=rgb(255,120,120),bold=True)
        drawLabel("This nickname belongs to a registered account.",cx,card_y+118,size=8,fill=rgb(140,150,170))
        drawLabel("Enter password to log in, or go back and choose another name.",cx,card_y+132,size=8,fill=rgb(140,150,170))
        # Password field
        input_w = 300
        input_x = cx - input_w//2
        input_y = card_y+154
        is_focused = True
        bg = rgb(28,34,52)
        border = rgb(90,110,160)
        drawRoundedRect(input_x,input_y,input_w,38,8,bg,border=border,borderWidth=1.2)
        masked = "*" * len(app.welcome_password)
        if masked:
            drawLabel(masked,input_x+12,input_y+19,size=13,fill=rgb(230,235,245),bold=True,align="left-top")
        else:
            drawLabel("password",input_x+12,input_y+19,size=13,fill=rgb(100,110,130),align="left-top")
        # Login button
        btn_w = 300
        btn_x = cx - btn_w//2
        btn_y = input_y+56
        drawRoundedRect(btn_x+1,btn_y+2,btn_w,36,8,rgb(0,0,0),opacity=18)
        drawRoundedRect(btn_x,btn_y,btn_w,36,8,rgb(90,100,220),border=rgb(120,130,250),borderWidth=1)
        drawLabel("LOG IN",cx,btn_y+18,size=14,fill="white",bold=True)
        if app.welcome_error:
            drawLabel(app.welcome_error,cx,btn_y+54,size=9,fill=rgb(255,120,120),bold=True)
        drawLabel("BACK",cx,card_y+card_h-32,size=10,fill=rgb(120,130,150),bold=True)

    # Footer music
    drawLabel("♪ Watchful Eye — Lobby Theme",app.width/2,app.height-28,size=9,fill=rgb(120,140,160))
    drawLabel("TETR.IO is developed by a single person — please consider supporting them!",app.width/2,app.height-12,size=8,fill=rgb(100,110,130))

# ===== CONFIG — matching config.png =====
def drawConfigScreen(app):
    drawRect(0,0,app.width,app.height,fill=rgb(32,38,58))
    # header
    drawRoundedRect(0,0,app.width,48,0,rgb(28,34,52),border=rgb(50,60,85),borderWidth=1)
    drawRoundedRect(12,8,32,32,6,rgb(45,55,80))
    drawLabel("▲",28,20,size=12,fill=rgb(180,190,220),bold=True)
    drawLabel("CONTROLS",58,22,size=22,fill=rgb(140,160,200),bold=True,align="left-top")
    drawLabel("HOVER OVER A SETTING FOR MORE INFO",app.width/2,6,size=8,fill=rgb(90,100,120))
    # tabs
    tab_y=56; tab_w= (app.width-24)//3
    tabs=["GUIDELINE","WASD","CUSTOM"]
    for i,t in enumerate(tabs):
        x=12+i*(tab_w+4)
        is_active = app.configTab==t
        bg = rgb(50,62,90) if is_active else rgb(36,44,68)
        border = rgb(80,95,130) if is_active else rgb(50,60,85)
        drawRoundedRect(x,tab_y,tab_w,28,6,bg,border=border,borderWidth=1)
        drawLabel(t,x+tab_w/2,tab_y+14,size=13,fill=rgb(180,200,230) if is_active else rgb(120,140,170),bold=True)
    # column headers
    y0=100
    # list
    # choose bind source
    if app.configTab=="GUIDELINE": binds=app.keybinds_guideline
    elif app.configTab=="CUSTOM": binds=app.keybinds_custom
    else: binds=app.keybinds

    # scroll
    visible = 14
    start = app.config_scroll
    for idx in range(visible):
        real_idx = start+idx
        if real_idx>=len(ACTION_LABELS): break
        action,label = ACTION_LABELS[real_idx]
        y = y0 + idx*36
        # row bg alternating
        bg = rgb(38,44,68) if idx%2==0 else rgb(32,38,60)
        drawRoundedRect(12,y,app.width-24,34,4,bg)
        drawLabel(label,20,y+17,size=12,fill=rgb(120,140,180),align="left-top")
        # 3 slots
        slot_w=90
        for s in range(3):
            sx = app.width - 300 + s*(slot_w+6)
            key = binds.get(action, ["[NOT SET]"]*3)[s] if s < len(binds.get(action,[])) else "[NOT SET]"
            is_sel = app.config_selected==(action,s)
            bgc = rgb(55,70,100) if is_sel else rgb(35,42,62)
            borderc = rgb(110,150,220) if is_sel else rgb(50,60,80)
            drawRoundedRect(sx,y+4,slot_w,26,4,bgc,border=borderc,borderWidth=1)
            drawLabel(key,sx+slot_w/2,y+17,size=9,fill=rgb(180,190,210),bold=True)
    # footer hint
    drawLabel("CLICK A SLOT TO REBIND — PRESS ESC TO CLEAR — BACK TO HOME TO SAVE",app.width/2,app.height-16,size=9,fill=rgb(100,115,140))
    # back button
    drawRoundedRect(12,app.height-52,160,32,8,rgb(45,55,80),border=rgb(70,85,115),borderWidth=1)
    drawLabel("BACK TO HOME",92,app.height-36,size=11,fill=rgb(180,190,220),bold=True)

def draw_tetrio_frame(app):
    ox=app.board_x; oy=app.board_y; bw=BOARD_W*CELL; bh=BOARD_H_VISIBLE*CELL
    frame=rgb(201,168,124)
    drawRoundedRect(ox-12,oy-10,bw+24+120+16+24,bh+20,12,rgb(0,0,0),opacity=15)
    hx=app.HOLD_X; hy=oy
    drawRoundedRect(hx-6,hy-6,100+12,78+12,10,frame,border=frame,borderWidth=1)
    drawRoundedRect(hx,hy,100,78,8,rgb(0,0,0))
    drawLabel("HOLD",hx+50,hy+10,size=11,fill=frame,bold=True)
    nx=app.NEXT_X; ny=oy
    drawRoundedRect(nx-6,ny-6,120+12,340+12,10,frame,border=frame,borderWidth=1)
    drawRoundedRect(nx,ny,120,340,8,rgb(0,0,0))
    drawLabel("NEXT",nx+60,ny+12,size=11,fill=frame,bold=True)
    drawRoundedRect(ox-8,oy-8,bw+16,bh+16,10,frame,border=frame,borderWidth=1)
    drawRoundedRect(ox-4,oy-4,bw+8,bh+8,6,rgb(0,0,0))

def draw_board_tetrio(app,board,ox,oy,cell,cur_piece=None,ghost_y=None,show_ghost=True,colors=COLORS):
    try:
        for y in range(BOARD_H_VISIBLE+1): drawLine(ox,oy+y*cell,ox+BOARD_W*cell,oy+y*cell,fill=rgb(35,32,28),lineWidth=1)
        for x in range(BOARD_W+1): drawLine(ox+x*cell,oy,ox+x*cell,oy+BOARD_H_VISIBLE*cell,fill=rgb(35,32,28),lineWidth=1)
        start_r=BOARD_H_INTERNAL-BOARD_H_VISIBLE
        # garbage gray at bottom like tetrio.webp
        for r in range(BOARD_H_VISIBLE):
            gr=start_r+r
            for c in range(BOARD_W):
                k=board.grid[gr][c]
                if k:
                    col=colors.get(k,rgb(60,60,60))
                    if k=='G':
                        drawRect(ox+c*cell+1,oy+r*cell+1,cell-2,cell-2,fill=rgb(80,80,80))
                    else:
                        drawRoundedRect(ox+c*cell+1,oy+r*cell+1,cell-2,cell-2,2,col)
                        # inner highlight like tetrio
                        drawRect(ox+c*cell+3,oy+r*cell+3,cell-6,cell-6,fill=None,border=rgb(255,255,255),borderWidth=1,opacity=12)
        if cur_piece and show_ghost and ghost_y is not None:
            for r in range(len(cur_piece.shape)):
                for c in range(len(cur_piece.shape[0])):
                    if cur_piece.shape[r][c]:
                        x=cur_piece.x+c; y=ghost_y+r; vy=y-start_r
                        if 0<=vy<BOARD_H_VISIBLE and 0<=x<BOARD_W:
                            drawRoundedRect(ox+x*cell+1,oy+vy*cell+1,cell-2,cell-2,2,None,border=colors[cur_piece.kind],borderWidth=2,opacity=28)
        if cur_piece:
            for r in range(len(cur_piece.shape)):
                for c in range(len(cur_piece.shape[0])):
                    if cur_piece.shape[r][c]:
                        x=cur_piece.x+c; y=cur_piece.y+r; vy=y-start_r
                        if 0<=vy<BOARD_H_VISIBLE and 0<=x<BOARD_W:
                            drawRoundedRect(ox+x*cell+1,oy+vy*cell+1,cell-2,cell-2,2,colors[cur_piece.kind])
                            drawRect(ox+x*cell+3,oy+vy*cell+3,cell-6,cell-6,fill=None,border=rgb(255,255,255),borderWidth=1,opacity=18)
    except: pass

def draw_hold_tetrio(app, ox=None, oy=None, cell=PREVIEW_CELL, hold_kind=None):
    try:
        if ox is None: ox=app.HOLD_X; oy=app.board_y
        kind = hold_kind if hold_kind is not None else app.tetr.hold_piece
        if not kind: return
        shape=TETROMINOES[kind]
        bx=ox+50 - (len(shape[0])*cell)//2; by=oy+28
        for r in range(len(shape)):
            for c in range(len(shape[0])):
                if shape[r][c]:
                    drawRoundedRect(bx+c*cell,by+r*cell,cell-1,cell-1,2,COLORS[kind])
    except: pass

def draw_next_tetrio(app, ox=None, oy=None, cell=PREVIEW_CELL, queue=None):
    try:
        if ox is None: ox=app.NEXT_X; oy=app.board_y; queue=app.tetr.next_queue
        if queue is None: queue=app.tetr.next_queue
        for i,kind in enumerate(queue[:5]):
            shape=TETROMINOES[kind]
            base_y=oy+34+i*58; base_x=ox+24
            for r in range(len(shape)):
                for c in range(len(shape[0])):
                    if shape[r][c]: drawRoundedRect(base_x+c*cell,base_y+r*cell,cell-1,cell-1,2,COLORS[kind])
    except: pass

def draw_opponent_tetrio(app):
    try:
        ox=app.opp_board_x; oy=app.opp_board_y
        if app.tetr.mode in ("zen","40lines","blitz"):
            drawRoundedRect(ox-6,oy-6,150,240,10,rgb(0,0,0),border=rgb(201,168,124),borderWidth=1)
            drawLabel("SOLO MODE",ox+75,oy+18,size=10,fill=rgb(201,168,124),bold=True)
            if app.tetr.mode=="zen":
                drawLabel("ZEN",ox+75,oy+44,size=14,fill=rgb(120,255,150),bold=True)
                drawLabel("Relaxed",ox+75,oy+64,size=10,fill=rgb(160,200,160))
                drawLabel("No Game Over",ox+75,oy+80,size=9,fill=rgb(120,180,120))
                drawLabel("Practice",ox+75,oy+96,size=9,fill=rgb(120,180,120))
                drawLabel(f"{app.tetr.stats['lines']} lines",ox+75,oy+120,size=10,fill="white")
            elif app.tetr.mode=="40lines":
                drawLabel("40 LINES",ox+75,oy+44,size=12,fill="white",bold=True)
                drawLabel(f"{app.tetr.stats['lines']}/40",ox+75,oy+68,size=14,fill=rgb(220,200,180),bold=True)
            else:
                elapsed=int(time.time()-app.tetr.stats["start"])
                drawLabel("BLITZ",ox+75,oy+44,size=12,fill="white",bold=True)
                drawLabel(f"{120-elapsed}s",ox+75,oy+66,size=12,fill=rgb(220,200,180),bold=True)
            return
        # old fallback for non-vs
        cell=14
        drawRoundedRect(ox-6,oy-6,BOARD_W*cell+12,BOARD_H_VISIBLE*cell//2+12,8,rgb(0,0,0),border=rgb(201,168,124),borderWidth=1)
        drawLabel(f"OPP {str(app.single_opponent_id)[:6] if app.single_opponent_id else '---'}",ox+70,oy-12,size=9,fill=rgb(201,168,124),bold=True)
        board=app.single_opponent_board
        if board and len(board)>=200:
            for r in range(BOARD_H_VISIBLE//2):
                for c in range(BOARD_W):
                    idx=r*BOARD_W+c
                    if idx < len(board) and board[idx]: drawRoundedRect(ox+c*cell+1,oy+r*cell+1,cell-2,cell-2,2,rgb(100,120,160))
    except: pass


def draw_stats_tetrio(app):
    try:
        ox=app.board_x; oy=app.board_y
        if app.tetr.board.b2b_streak>=1:
            drawLabel(f"B2B x{app.tetr.board.b2b_streak}",ox-90,oy+160,size=13,fill=rgb(255,210,120),bold=True)
        if app.tetr.board.combo>=1:
            combo_num=app.tetr.board.combo+1
            cx=ox-70; cy=oy+190
            for i in range(8):
                ang=i*45*math.pi/180
                x2=cx+math.cos(ang)*30; y2=cy+math.sin(ang)*30
                drawLine(cx,cy,x2,y2,fill=rgb(255,210,60),lineWidth=7)
            drawCircle(cx,cy,24,fill=rgb(255,210,60),border=rgb(255,230,120))
            drawLabel(str(combo_num),cx,cy+2,size=20,fill="black",bold=True)
        elapsed=time.time()-app.tetr.stats["start"]
        pps=app.tetr.stats["pieces"]/max(1,elapsed)
        apm=int(app.tetr.stats["attack"]/max(1,elapsed)*60)
        drawLabel(f"PIECES",ox-90,oy+260,size=10,fill=rgb(201,168,124))
        drawLabel(f"{app.tetr.stats['pieces']}",ox-90,oy+278,size=18,fill=rgb(220,200,180),bold=True)
        drawLabel(f"{pps:.2f}/S",ox-30,oy+280,size=10,fill=rgb(150,130,110))
        drawLabel(f"ATTACK",ox-90,oy+304,size=10,fill=rgb(201,168,124))
        drawLabel(f"{app.tetr.stats['attack']}",ox-90,oy+322,size=18,fill=rgb(220,200,180),bold=True)
        drawLabel(f"{apm}/M",ox-30,oy+324,size=10,fill=rgb(150,130,110))
        drawLabel(f"TIME",ox-90,oy+348,size=10,fill=rgb(201,168,124))
        drawLabel(f"{int(elapsed//60)}:{elapsed%60:06.3f}",ox-90,oy+366,size=16,fill=rgb(220,200,180),bold=True)
    except Exception as e:
        print(f"draw_stats fail {e}")

def draw_garbage_meter(app):
    try:
        ox=app.board_x; oy=app.board_y; bh=BOARD_H_VISIBLE*CELL
        drawRoundedRect(ox-12,oy,6,bh,3,rgb(40,35,25))
        inc=len(app.mp_wrapper.match["garbage"]["incoming"])
        if inc:
            h=min(bh,inc*18)
            drawRoundedRect(ox-12,oy+bh-h,6,h,3,rgb(220,200,80))
    except Exception as e:
        print(f"garbage meter fail {e}")


# ===== TRUE 1v1 like tetrio.webp — faithful recreation =====
def draw_multiplayer_vs(app):
    try:
        # Layout from tetrio.webp — exact
        # Left: HOLD | BOARD | NEXT+REPLAY, Right: HOLD | BOARD | NEXT+REPLAY
        # Boards y=88 to avoid tabs (tabs at 0-60), x positions from screenshot
        p1_hold_x, p1_hold_y = 48, 88
        p1_board_x, p1_board_y = 128, 88
        p1_next_x, p1_next_y = 352, 88

        p2_hold_x, p2_hold_y = 604, 88
        p2_board_x, p2_board_y = 684, 88
        p2_next_x, p2_next_y = 908, 88

        cell = 18  # smaller to fit both boards + stats in 1120 width, like screenshot
        bw = BOARD_W*cell
        bh = BOARD_H_VISIBLE*cell
        # Pink frame like tetrio
        frame = rgb(201,70,130)
        grid_col = rgb(28,28,34)
        bg_col = rgb(12,12,16)

        # Helper to draw HOLD box
        def draw_hold_box(hx, hy, kind=None):
            # Outer pink border
            drawRoundedRect(hx-6, hy-6, 74, 56, 8, rgb(0,0,0), border=frame, borderWidth=1.2)
            drawRoundedRect(hx-2, hy-2, 66, 48, 6, bg_col)
            drawLabel("HOLD", hx+33, hy+7, size=8, fill=rgb(255,90,160), bold=True)
            if kind:
                try:
                    shape=TETROMINOES[kind]
                    # Center in 66x48, minus header 12px
                    bx = hx + 33 - (len(shape[0])*9)//2
                    by = hy + 18
                    for r in range(len(shape)):
                        for c in range(len(shape[0])):
                            if shape[r][c]:
                                drawRoundedRect(bx+c*9, by+r*9, 8, 8, 2, COLORS_MP.get(kind, rgb(200,200,200)))
                except:
                    pass

        # Helper to draw NEXT box with 5 previews
        def draw_next_box(nx, ny, queue, replay_label=True):
            drawRoundedRect(nx-6, ny-6, 96, bh+12, 8, rgb(0,0,0), border=frame, borderWidth=1.2)
            drawRoundedRect(nx-2, ny-2, 88, bh+4, 6, bg_col)
            drawLabel("NEXT", nx+44, ny+8, size=8, fill=rgb(255,90,160), bold=True)
            if replay_label:
                # REPLAY gray pill at top of board edge like screenshot
                drawRoundedRect(nx-38, ny+6, 56, 14, 4, rgb(60,60,68))
                drawLabel("REPLAY", nx-10, ny+13, size=7, fill=rgb(200,200,210), bold=True)
            # 5 next
            for i,kind in enumerate(queue[:5]):
                try:
                    shape=TETROMINOES[kind]
                    base_y=ny+28+i*58
                    base_x=nx+18
                    for r in range(len(shape)):
                        for c in range(len(shape[0])):
                            if shape[r][c]:
                                drawRoundedRect(base_x+c*9, base_y+r*9, 8, 8, 2, COLORS_MP.get(kind, rgb(200,200,200)))
                except:
                    pass

        # Helper to draw board with garbage at bottom
        def draw_board_with_garbage(bx, by, board_obj, is_p1=True):
            # Outer frame
            drawRoundedRect(bx-8, by-8, bw+16, bh+16, 10, rgb(0,0,0), border=frame, borderWidth=1.5)
            drawRoundedRect(bx-2, by-2, bw+4, bh+4, 6, rgb(0,0,0))
            # Grid
            for y in range(BOARD_H_VISIBLE+1):
                try: drawLine(bx, by+y*cell, bx+bw, by+y*cell, fill=grid_col, lineWidth=1)
                except: pass
            for x in range(BOARD_W+1):
                try: drawLine(bx+x*cell, by, bx+x*cell, by+bh, fill=grid_col, lineWidth=1)
                except: pass
            # Pieces
            try:
                if is_p1 and board_obj:
                    start_r=BOARD_H_INTERNAL-BOARD_H_VISIBLE
                    for r in range(BOARD_H_VISIBLE):
                        gr=start_r+r
                        for c in range(BOARD_W):
                            k=board_obj.grid[gr][c]
                            if k:
                                col=COLORS_MP.get(k, rgb(80,80,80))
                                if k=='G':
                                    drawRect(bx+c*cell+1, by+r*cell+1, cell-2, cell-2, fill=rgb(72,72,76))
                                else:
                                    drawRoundedRect(bx+c*cell+1, by+r*cell+1, cell-2, cell-2, 2, col)
                                    drawRect(bx+c*cell+3, by+r*cell+3, cell-6, 2, fill=rgb(255,255,255), opacity=18)
                    # Ghost and current
                    cur = app.tetr.current
                    ghost_y = app.tetr.ghost_y
                    # Ghost
                    if cur and ghost_y is not None:
                        for r in range(len(cur.shape)):
                            for c in range(len(cur.shape[0])):
                                if cur.shape[r][c]:
                                    x=cur.x+c; y=ghost_y+r; vy=y-start_r
                                    if 0<=vy<BOARD_H_VISIBLE and 0<=x<BOARD_W:
                                        drawRoundedRect(bx+x*cell+1, by+vy*cell+1, cell-2, cell-2, 2, None, border=COLORS_MP.get(cur.kind, rgb(200,200,200)), borderWidth=1, opacity=32)
                    # Current
                    if cur:
                        for r in range(len(cur.shape)):
                            for c in range(len(cur.shape[0])):
                                if cur.shape[r][c]:
                                    x=cur.x+c; y=cur.y+r; vy=y-start_r
                                    if 0<=vy<BOARD_H_VISIBLE and 0<=x<BOARD_W:
                                        drawRoundedRect(bx+x*cell+1, by+vy*cell+1, cell-2, cell-2, 2, COLORS_MP.get(cur.kind, rgb(200,200,200)))
            except Exception as e:
                print(f"P1 board fail {e}")

        # Helper to draw opponent board from flat_full or flat
        def draw_opp_board(bx, by, opp_board):
            # Grid
            for y in range(BOARD_H_VISIBLE+1):
                try: drawLine(bx, by+y*cell, bx+bw, by+y*cell, fill=grid_col, lineWidth=1)
                except: pass
            for x in range(BOARD_W+1):
                try: drawLine(bx+x*cell, by, bx+x*cell, by+bh, fill=grid_col, lineWidth=1)
                except: pass
            if not opp_board or len(opp_board)<200:
                # SEARCHING / WAITING
                if app.game_state=="searching":
                    try:
                        drawLabel("SEARCHING...", bx+bw/2, by+bh/2-16, size=12, fill=rgb(160,170,190), bold=True)
                        drawLabel(f"{app.mp_wrapper.search_timer//60}s", bx+bw/2, by+bh/2+2, size=10, fill=rgb(110,120,135))
                        drawLabel("WAIT or PLAY VS BOT", bx+bw/2, by+bh/2+18, size=8, fill=rgb(201,168,124), bold=True)
                    except: pass
                else:
                    try: drawLabel("WAITING", bx+bw/2, by+bh/2, size=11, fill=rgb(130,140,160), bold=True)
                    except: pass
                return
            # Decode full board
            code_to_color = {1:rgb(0,212,212),2:rgb(0,70,200),3:rgb(210,120,0),4:rgb(210,210,0),5:rgb(0,200,0),6:rgb(150,0,200),7:rgb(200,0,0),8:rgb(72,72,76)}
            is_full = max(opp_board) > 1 if opp_board else False
            # Current piece of opponent if available
            opp_cur_kind = getattr(app, '_opp_cur', None)
            opp_cur_x = getattr(app, '_opp_cur_x', 0)
            opp_cur_y = getattr(app, '_opp_cur_y', 0)
            for r in range(BOARD_H_VISIBLE):
                for c in range(BOARD_W):
                    idx = r*BOARD_W + c
                    if idx < len(opp_board) and opp_board[idx]:
                        val = opp_board[idx]
                        if is_full:
                            col = code_to_color.get(val, rgb(120,140,180))
                            if val==8:
                                drawRect(bx+c*cell+1, by+r*cell+1, cell-2, cell-2, fill=rgb(72,72,76))
                            else:
                                drawRoundedRect(bx+c*cell+1, by+r*cell+1, cell-2, cell-2, 2, col)
                                drawRect(bx+c*cell+3, by+r*cell+3, cell-6, 2, fill=rgb(255,255,255), opacity=16)
                        else:
                            # legacy binary: bottom 3 rows gray = garbage
                            if r >= BOARD_H_VISIBLE-3 and opp_board[idx]:
                                drawRect(bx+c*cell+1, by+r*cell+1, cell-2, cell-2, fill=rgb(72,72,76))
                            elif opp_board[idx]:
                                drawRoundedRect(bx+c*cell+1, by+r*cell+1, cell-2, cell-2, 2, rgb(120,140,180))
            # Opponent current ghost/current if we have it
            try:
                if opp_cur_kind and opp_cur_kind in TETROMINOES:
                    shape = TETROMINOES[opp_cur_kind]
                    # Simple draw at opp_cur_x/y
                    for r in range(len(shape)):
                        for c in range(len(shape[0])):
                            if shape[r][c]:
                                x = int(opp_cur_x + c)
                                y = int(opp_cur_y + r)
                                if 0 <= y < BOARD_H_VISIBLE and 0 <= x < BOARD_W:
                                    drawRoundedRect(bx+x*cell+1, by+y*cell+1, cell-2, cell-2, 2, COLORS_MP.get(opp_cur_kind, rgb(200,200,200)), opacity=88)
            except:
                pass

        # ===== P1 =====
        draw_hold_box(p1_hold_x, p1_hold_y, app.tetr.hold_piece)
        draw_board_with_garbage(p1_board_x, p1_board_y, app.tetr.board, is_p1=True)
        draw_next_box(p1_next_x, p1_next_y, app.tetr.next_queue[:5], replay_label=True)

        # P1 stats — left of board like screenshot
        try:
            sx = 8
            sy = p1_board_y + 98
            # B2B
            if app.tetr.board.b2b_streak>=1:
                drawLabel(f"B2B x{app.tetr.board.b2b_streak}", sx+28, sy, size=12, fill=rgb(255,220,120), bold=True, align="left-top")
                sy+=26
            else:
                sy+=8
            drawLabel("PIECES", sx, sy, size=8, fill=rgb(160,160,180), align="left-top"); sy+=10
            elapsed=time.time()-app.tetr.stats["start"]
            pps=app.tetr.stats["pieces"]/max(1,elapsed)
            drawLabel(f"{app.tetr.stats['pieces']}", sx, sy, size=16, fill=rgb(230,230,245), bold=True, align="left-top")
            drawLabel(f"{pps:.1f}/S", sx+44, sy+3, size=9, fill=rgb(130,130,150), align="left-top"); sy+=22
            drawLabel("ATTACK", sx, sy, size=8, fill=rgb(160,160,180), align="left-top"); sy+=10
            drawLabel(f"{app.tetr.stats['attack']}", sx, sy, size=16, fill=rgb(230,230,245), bold=True, align="left-top")
            apm=int(app.tetr.stats["attack"]/max(1,elapsed)*60)
            drawLabel(f"{apm}/M", sx+32, sy+3, size=9, fill=rgb(130,130,150), align="left-top"); sy+=22
            drawLabel("TIME", sx, sy, size=8, fill=rgb(160,160,180), align="left-top"); sy+=10
            drawLabel(f"{int(elapsed//60)}:{elapsed%60:02d}", sx, sy, size=16, fill=rgb(230,230,245), bold=True, align="left-top")
        except Exception as e:
            print(f"P1 stats fail {e}")

        # ===== P2 =====
        opp_hold = getattr(app, '_opp_hold', None)
        opp_next = getattr(app, '_opp_next', [])
        draw_hold_box(p2_hold_x, p2_hold_y, opp_hold)
        # Board frame
        drawRoundedRect(p2_board_x-8, p2_board_y-8, bw+16, bh+16, 10, rgb(0,0,0), border=frame, borderWidth=1.5)
        drawRoundedRect(p2_board_x-2, p2_board_y-2, bw+4, bh+4, 6, rgb(0,0,0))
        draw_opp_board(p2_board_x, p2_board_y, app.single_opponent_board)
        draw_next_box(p2_next_x, p2_next_y, opp_next if opp_next else [], replay_label=True)

        # P2 stats — middle gap like screenshot (left of P2 board)
        try:
            sx2 = 464  # center gap between boards
            sy2 = p2_board_y + 98
            opp_b2b = getattr(app, '_opp_b2b', 0)
            opp_combo = getattr(app, '_opp_combo', 0)
            opp_apm = getattr(app, '_opp_apm', 0)
            opp_pps = getattr(app, '_opp_pps', 0.0)
            # Count pieces from opponent board? Use _opp_pieces if available else estimate
            opp_pieces = getattr(app, '_opp_pieces', 0) or len([v for v in (app.single_opponent_board or []) if v])//4

            if opp_b2b>=1:
                drawLabel(f"B2B x{opp_b2b}", sx2+28, sy2, size=12, fill=rgb(255,220,120), bold=True, align="left-top")
                sy2+=26
            else:
                sy2+=8
            # PIECES
            drawLabel("PIECES", sx2, sy2, size=8, fill=rgb(160,160,180), align="left-top"); sy2+=10
            drawLabel(f"{getattr(app, '_opp_pieces', 26) if hasattr(app, '_opp_pieces') else (app.single_opponent_board.count(1) if app.single_opponent_board and max(app.single_opponent_board)<=1 else 26)}", sx2, sy2, size=16, fill=rgb(230,230,245), bold=True, align="left-top")
            drawLabel(f"{opp_pps:.1f}/S" if opp_pps else "2.2/S", sx2+44, sy2+3, size=9, fill=rgb(130,130,150), align="left-top"); sy2+=22
            drawLabel("ATTACK", sx2, sy2, size=8, fill=rgb(160,160,180), align="left-top"); sy2+=10
            drawLabel(f"{getattr(app, '_opp_score', 3) if hasattr(app, '_opp_score') else 3}", sx2, sy2, size=16, fill=rgb(230,230,245), bold=True, align="left-top")
            drawLabel(f"{opp_apm}/M" if opp_apm else "15/M", sx2+32, sy2+3, size=9, fill=rgb(130,130,150), align="left-top"); sy2+=22
            drawLabel("TIME", sx2, sy2, size=8, fill=rgb(160,160,180), align="left-top"); sy2+=10
            drawLabel(f"{int(elapsed//60)}:{int(elapsed%60):02d}" if 'elapsed' in locals() else "0:12", sx2, sy2, size=16, fill=rgb(230,230,245), bold=True, align="left-top")
        except Exception as e:
            print(f"P2 stats fail {e}")

        # VS SCORE — like screenshot: below boards, centered under NEXT
        try:
            # P1 VS SCORE 58
            drawLabel("VS SCORE", p1_next_x+12, p1_board_y+bh+16, size=8, fill=rgb(160,160,180), bold=True, align="left-top")
            drawLabel(f"{app.tetr.stats['score']}", p1_next_x+12, p1_board_y+bh+28, size=18, fill=rgb(240,240,255), bold=True, align="left-top")
            # P2 VS SCORE 33
            drawLabel("VS SCORE", p2_next_x+12, p2_board_y+bh+16, size=8, fill=rgb(160,160,180), bold=True, align="left-top")
            drawLabel(f"{getattr(app, '_opp_score', 33)}", p2_next_x+12, p2_board_y+bh+28, size=18, fill=rgb(210,210,220), bold=True, align="left-top")
            # Player names — proper nickname handling
            p1_name = str(getattr(app, "username", "YOU")).upper()[:12] or "YOU"
            # Show ANON tag if anonymous
            if getattr(app, "is_anonymous", False):
                p1_name = f"{p1_name} (ANON)"[:16]
            drawLabel(p1_name, p1_board_x+bw/2, p1_board_y+bh+52, size=11, fill=rgb(220,220,230), bold=True)
            opp_name = str(getattr(app, "single_opponent_username", "") or getattr(app, "single_opponent_id", "") or "WOORAM")[:12].upper() or "WOORAM"
            if getattr(app, "single_opponent_anon", False):
                opp_name = f"{opp_name} (ANON)"[:16]
            drawLabel(opp_name, p2_board_x+bw/2, p2_board_y+bh+52, size=11, fill=rgb(190,190,200), bold=True)
        except Exception as e:
            print(f"VS score fail {e}")

        # Garbage meters — left edge of each board like tetrio (thin pink bar)
        try:
            inc = len(app.mp_wrapper.match["garbage"]["incoming"])
            if inc>0:
                gh = min(bh, inc*12)
                drawRoundedRect(p1_board_x-10, p1_board_y+bh-gh, 4, gh, 2, rgb(220,60,60))
            # Outgoing
            outg = getattr(app.tetr.board, 'attack', 0)
            if outg>0:
                gh2 = min(bh, outg*12)
                drawRoundedRect(p1_board_x+bw+6, p1_board_y+bh-gh2, 4, gh2, 2, rgb(60,220,60))
        except:
            pass

    except Exception as e:
        print(f"draw_multiplayer_vs fail {e}")
        # Fallback simple
        try:
            drawLabel("VS MODE", 560, 200, size=20, fill=rgb(255,255,255), bold=True)
        except:
            pass


def onMousePress(app,mx,my):
    if app.game_state=="title":
        # TETR.IO welcome screen handling
        cx = app.width//2
        card_w = 460
        card_x = cx - card_w//2
        card_y = 88
        def gen_random_name():
            adj = random.choice(app.random_names) if hasattr(app,'random_names') else "GUEST"
            num = random.randint(100,9999)
            return f"{adj}_{num}"

        def is_registered(name):
            if not name:
                return False
            return name.strip().upper() in app.registered_users

        if app.welcome_state=="enter":
            # Input field
            input_w = 300
            input_x = cx - input_w//2
            input_y = card_y+118
            # Click on input -> focus
            if input_x <= mx <= input_x+input_w and input_y <= my <= input_y+38:
                app.inputName.focused=True
                play_sfx("ui.click")
                return True
            else:
                app.inputName.focused=False
            # JOIN button
            btn_w = 300
            btn_x = cx - btn_w//2
            btn_y = input_y+56
            if btn_x <= mx <= btn_x+btn_w and btn_y <= my <= btn_y+36:
                play_sfx("ui.click")
                name = app.welcome_username.strip()
                if not name:
                    # Blank -> random -> go to MODE PICKER (second screen) NOT directly to playing
                    rnd = gen_random_name()
                    app.username = rnd
                    app.is_anonymous = True
                    app.welcome_error=""
                    app.game_state="menu"
                    app.tabGroup.active=2
                    app.tetr=TetrGame(mode="zen")
                    app.badgeOPP.text="SOLO ZEN"
                    app.inputName.focused=False
                    stop_bgm(); play_bgm("bgm.menu_watchful_eye", spectating=False)
                    print(f"Random name {rnd} -> menu")
                else:
                    if len(name) < 2:
                        app.welcome_error="Name too short"
                    elif len(name) > 16:
                        app.welcome_error="Name too long (max 16)"
                    elif is_registered(name):
                        app.welcome_state="taken"
                        app.welcome_error=""
                        app.welcome_password=""
                        print(f"Name taken {name}")
                    else:
                        app.welcome_state="available"
                        app.welcome_error=""
                        print(f"Name available {name}")
                return True
            return False

        elif app.welcome_state=="available":
            btn_w = 300
            btn_x = cx - btn_w//2
            y1 = card_y+150
            y2 = y1+62
            # STAY ANONYMOUS -> MODE PICKER second screen
            if btn_x <= mx <= btn_x+btn_w and y1 <= my <= y1+38:
                play_sfx("ui.click")
                app.username = app.welcome_username.strip()
                app.is_anonymous = True
                app.inputName.value = app.username
                app.inputName.text = app.username
                # Go to MODE PICKER (second screen) - MUST HAVE
                app.game_state="menu"
                app.tabGroup.active=2
                app.tetr=TetrGame(mode="zen")
                app.badgeOPP.text="SOLO ZEN"
                app.inputName.focused=False
                stop_bgm(); play_bgm("bgm.menu_watchful_eye", spectating=False)
                print(f"Stay anonymous as {app.username} -> menu")
                return True
            # REGISTER
            if btn_x <= mx <= btn_x+btn_w and y2 <= my <= y2+38:
                play_sfx("ui.click")
                # Simulate registration — add to registered, not anonymous
                name = app.welcome_username.strip()
                app.registered_users.add(name.upper())
                try:
                    ls = window.localStorage
                    if ls:
                        lst = list(app.registered_users)
                        ls.setItem("tetrio_registered", json.dumps(lst))
                except:
                    pass
                app.username = name
                app.is_anonymous = False
                app.inputName.value = name
                app.inputName.text = name
                app.game_state="menu"
                app.tabGroup.active=2
                app.tetr=TetrGame(mode="zen")
                app.game_state="playing"
                app.badgeOPP.text="SOLO ZEN"
                app.inputName.focused=False
                stop_bgm(); play_bgm("bgm.zen", floor=0)
                print(f"Registered {name}")
                return True
            # BACK
            back_y = card_y+420-32
            if cx-30 <= mx <= cx+30 and back_y-10 <= my <= back_y+10:
                app.welcome_state="enter"
                app.welcome_error=""
                play_sfx("ui.back")
                return True
            return False

        elif app.welcome_state=="taken":
            input_w = 300
            input_x = cx - input_w//2
            input_y = card_y+154
            btn_w = 300
            btn_x = cx - btn_w//2
            btn_y = input_y+56
            # Password field focus
            if input_x <= mx <= input_x+input_w and input_y <= my <= input_y+38:
                # focus password — for simplicity use same inputName focused
                app.inputName.focused=True
                play_sfx("ui.click")
                return True
            # LOGIN
            if btn_x <= mx <= btn_x+btn_w and btn_y <= my <= btn_y+36:
                play_sfx("ui.click")
                # Simulate login — any password works if name registered, unless we stored one
                # For demo, accept any non-empty password
                if not app.welcome_password:
                    app.welcome_error="Enter password"
                else:
                    app.username = app.welcome_username.strip()
                    app.is_anonymous = False
                    app.inputName.value = app.username
                    app.inputName.text = app.username
                    app.game_state="menu"
                    app.tabGroup.active=2
                    app.tetr=TetrGame(mode="zen")
                    app.badgeOPP.text="SOLO ZEN"
                    app.inputName.focused=False
                    stop_bgm(); play_bgm("bgm.menu_watchful_eye", spectating=False)
                    print(f"Logged in as {app.username} -> menu")
                return True
            # BACK
            back_y = card_y+420-32
            if cx-30 <= mx <= cx+30 and back_y-10 <= my <= back_y+10:
                app.welcome_state="enter"
                app.welcome_error=""
                app.welcome_password=""
                play_sfx("ui.back")
                return True
            app.inputName.focused=False
            return False

        # Old titleItems fallback (should not happen with new welcome)
        for item in app.titleItems:
            x=120; y=item["y"]; w=880; h=58
            if x<=mx<=x+w and y<=my<=y+h:
                if item["id"]=="multiplayer":
                    app.game_state="menu"; app.tabGroup.active=0; start_search(app); app.game_state="searching"
                elif item["id"]=="solo":
                    app.game_state="menu"; app.tabGroup.active=2; app.tetr=TetrGame(mode="zen"); app.badgeOPP.text="SOLO ZEN"; app.inputName.focused=False
                    stop_bgm(); play_bgm("bgm.menu_watchful_eye", spectating=False)
                elif item["id"]=="config":
                    go_config(app)
                elif item["id"]=="tetra":
                    app.game_state="menu"; app.tabGroup.active=0; start_search(app); app.game_state="searching"
                else:
                    go_config(app)
                return True
        return False
    if app.dialogGameOver.open:
        for b in app.dialogGameOver.buttons:
            if b.contains(mx,my) and b.handlePress(mx,my): 
                play_sfx("ui.click")
                return True
    if app.tabGroup.handlePress(mx,my): 
        play_sfx("ui.click")
        start_search(app); return True
    if app.tetr.mode in ("zen","40lines","blitz") or app.tabGroup.tabs[app.tabGroup.active] in ("ZEN","40 LINES","BLITZ"):
        if app.btnReset.contains(mx,my) and app.btnReset.handlePress(mx,my): 
            play_sfx("ui.click")
            return True
        if app.btnCancel.contains(mx,my) and app.btnCancel.handlePress(mx,my): 
            play_sfx("ui.back")
            return True
    else:
        if app.btnFind.contains(mx,my) and app.btnFind.handlePress(mx,my): 
            # Check anonymous restriction for ranked
            if app.is_anonymous and app.tetr.mode=="tetra_league":
                app.welcome_error="Anonymous cannot play ranked"
                # Force quick play
                app.tabGroup.active=1
                start_search(app)
                return True
            play_sfx("ui.click")
            return True
        if app.btnCancel.contains(mx,my) and app.btnCancel.handlePress(mx,my): 
            play_sfx("ui.back")
            return True
        if hasattr(app, "btnBot") and app.btnBot.contains(mx,my) and app.btnBot.handlePress(mx,my): 
            play_sfx("ui.click")
            return True
    if app.btnBack.contains(mx,my) and app.btnBack.handlePress(mx,my): 
        play_sfx("ui.back")
        return True
    if hasattr(app, "btnConfig") and app.btnConfig.contains(mx,my) and app.btnConfig.handlePress(mx,my):
        play_sfx("ui.click")
        return True
    if app.inputName.contains(mx,my): app.inputName.focused=True; return True
    else: app.inputName.focused=False
    return False

def onMouseMove(app,mx,my):
    if app.game_state=="title":
        hover=None
        for item in app.titleItems:
            x=120; y=item["y"]; w=880; h=58
            if x<=mx<=x+w and y<=my<=y+h: hover=item["id"]
        if hover and hover != getattr(app,"_hoverTitle",None):
            play_sfx("ui.hover", volume=0.15)
        app._hoverTitle=hover
        return False
    for comp in [app.btnFind, app.btnCancel, app.btnBot, app.btnReset, app.btnBack, getattr(app, "btnConfig", app.btnBack), app.tabGroup, app.inputName]:
        if hasattr(comp,'handleMove'): comp.handleMove(mx,my)
    return False
def onMouseRelease(app,mx,my):
    for comp in [app.btnFind, app.btnCancel, app.btnBot, app.btnReset, app.btnBack, getattr(app, "btnConfig", app.btnBack)]:
        if hasattr(comp,'handleRelease'): comp.handleRelease(mx,my)
    return False
def onMouseDrag(app,mx,my): return onMouseMove(app,mx,my)

def key_code_to_display(code):
    # code like "ARROWLEFT" -> display
    return code

def _norm_key(k):
    if not k: return ""
    kl=str(k).lower()
    mapping={"arrowleft":"left","arrowright":"right","arrowup":"up","arrowdown":"down"," ":"space","spacebar":"space"}
    return mapping.get(kl,kl)

def _code_from_key(k):
    # browser key -> code format like config.png ARROWLEFT etc
    if not k: return "[NOT SET]"
    kl=str(k).upper()
    mapping={" ":"SPACE","ARROWLEFT":"ARROWLEFT","ARROWRIGHT":"ARROWRIGHT","ARROWUP":"ARROWUP","ARROWDOWN":"ARROWDOWN",
             "A":"KEYA","B":"KEYB","C":"KEYC","D":"KEYD","E":"KEYE","F":"KEYF","G":"KEYG","H":"KEYH","I":"KEYI","J":"KEYJ","K":"KEYK","L":"KEYL","M":"KEYM","N":"KEYN","O":"KEYO","P":"KEYP","Q":"KEYQ","R":"KEYR","S":"KEYS","T":"KEYT","U":"KEYU","V":"KEYV","W":"KEYW","X":"KEYX","Y":"KEYY","Z":"KEYZ",
             "SHIFT":"SHIFTLEFT","CONTROL":"CONTROLLEFT","ALT":"ALTLEFT","/":"SLASH"}
    if kl in mapping: return mapping[kl]
    if len(kl)==1: return f"KEY{kl}"
    return kl

def onKeyPress(app,key):
    # Welcome screen typing
    if app.game_state=="title":
        k=_norm_key(key)
        code = _code_from_key(key)
        # Handle backspace, enter, typing for username/password
        if app.welcome_state=="enter":
            if k=="backspace":
                app.welcome_username = app.welcome_username[:-1]
                app.inputName.value = app.welcome_username
                play_sfx("tetr.move", volume=0.15)
                return
            elif k=="enter" or k==" " and False:
                # Simulate JOIN click
                def gen_random_name():
                    adj = _r.choice(app.random_names) if hasattr(app,'random_names') else "GUEST"
                    num = _r.randint(100,9999)
                    return f"{adj}_{num}"
                def is_registered(name):
                    return name.strip().upper() in app.registered_users if name else False
                name = app.welcome_username.strip()
                if not name:
                    rnd = gen_random_name()
                    app.username = rnd
                    app.is_anonymous = True
                    app.game_state="menu"; app.tabGroup.active=2; app.tetr=TetrGame(mode="zen"); app.badgeOPP.text="SOLO ZEN"; app.inputName.focused=False
                    stop_bgm(); play_bgm("bgm.menu_watchful_eye", spectating=False)
                else:
                    if is_registered(name):
                        app.welcome_state="taken"; app.welcome_password=""
                    else:
                        app.welcome_state="available"
                play_sfx("ui.click")
                return
            elif len(k)==1 and k.isprintable() and len(app.welcome_username)<16:
                # Only allow alphanumeric and _ and -
                if k in "abcdefghijklmnopqrstuvwxyz0123456789_-" or (k.isalnum()):
                    app.welcome_username += key if len(key)==1 else k
                    # Keep original case for display — use key as typed
                    if len(key)==1 and key.isalnum():
                        # Replace last char with actual key to preserve case
                        app.welcome_username = app.welcome_username[:-1] + key
                    app.inputName.value = app.welcome_username
                    play_sfx("tetr.move", volume=0.1, pitch=1.1)
                return
            elif k=="escape":
                app.welcome_username=""
                app.welcome_error=""
                return
        elif app.welcome_state=="taken":
            # typing password
            if k=="backspace":
                app.welcome_password = app.welcome_password[:-1]
                play_sfx("tetr.move", volume=0.15)
                return
            elif k=="enter":
                # Try login
                if app.welcome_password:
                    app.username = app.welcome_username.strip()
                    app.is_anonymous=False
                    app.inputName.value=app.username
                    app.game_state="menu"; app.tabGroup.active=2; app.tetr=TetrGame(mode="zen"); app.game_state="playing"; app.badgeOPP.text="SOLO ZEN"; app.inputName.focused=False
                    stop_bgm(); play_bgm("bgm.zen", floor=0)
                    play_sfx("ui.click")
                return
            elif len(k)==1 and k.isprintable() and len(app.welcome_password)<24:
                app.welcome_password += key if len(key)==1 else k
                play_sfx("tetr.move", volume=0.1)
                return
            elif k=="escape":
                app.welcome_state="enter"; app.welcome_password=""; app.welcome_error=""
                play_sfx("ui.back")
                return

    k=_norm_key(key)
    code = _code_from_key(key)

    # CONFIG rebinding
    if app.game_state=="config":
        if app.config_selected:
            action,slot = app.config_selected
            if k=="escape":
                if app.configTab=="GUIDELINE": app.keybinds_guideline[action][slot]="[NOT SET]"
                elif app.configTab=="CUSTOM": app.keybinds_custom[action][slot]="[NOT SET]"; app.keybinds[action][slot]="[NOT SET]"
                else: app.keybinds[action][slot]="[NOT SET]"
            else:
                disp = code
                if app.configTab=="GUIDELINE": app.keybinds_guideline[action][slot]=disp
                elif app.configTab=="CUSTOM": app.keybinds_custom[action][slot]=disp; app.keybinds[action][slot]=disp
                else: app.keybinds[action][slot]=disp
            app.config_selected=None
            play_sfx("ui.click")
            return
        if k=="escape":
            go_title(app)
        return

    if hasattr(app,'inputName') and app.inputName.focused:
        if k=="escape": app.inputName.focused=False
        return
    if app.game_state=="title":
        if k in ("enter"," "):
            play_sfx("ui.click")
            app.game_state="menu"; app.tabGroup.active=2; app.tetr=TetrGame(mode="zen"); app.game_state="playing"; app.inputName.focused=False
            stop_bgm(); play_bgm("bgm.zen", floor=0)
        return
    if app.game_state!="playing":
        if k=="r": reset_game(app)
        if k=="escape": go_title(app)
        return

    def is_bound(action_name, key_code):
        binds = app.keybinds.get(action_name, [])
        # Check code exact or key lower
        if key_code in binds:
            return True
        # Also check normalized lower versions
        low_binds = [b.lower() for b in binds if isinstance(b,str)]
        if k in low_binds:
            return True
        # Check if any bind's normalized equals k
        for b in binds:
            if isinstance(b,str) and _norm_key(b).lower()==k:
                return True
        return False

    # Movement first
    if k in ("left","a") or is_bound("move_left", code): 
        if app.tetr.try_move(-1,0): play_sfx("tetr.move", pitch=0.98, floor=app.tetr.stats["lines"]//5)
        return
    if k in ("right","d") or is_bound("move_right", code): 
        if app.tetr.try_move(1,0): play_sfx("tetr.move", pitch=1.02, floor=app.tetr.stats["lines"]//5)
        return
    if k in ("down","s") or is_bound("soft_drop", code): 
        app.tetr.soft_drop=True
        play_sfx("tetr.softdrop", volume=0.2, floor=app.tetr.stats["lines"]//5)
        return

    # Rotation — FIXED: up and w now work for rotation, not just hard_drop
    # TETR.IO: x= cw, z= ccw, c= 180/hold, up= cw (many players), w= cw (WASD)
    # We prioritize rotation binds over hard_drop for up/w if they are bound to rotate
    if k=="z" or is_bound("rotate_ccw", code) or (k in ("left",) and is_bound("rotate_ccw", code)):
        if app.tetr.try_rotate(-1): 
            play_sfx("tetr.rotate", pitch=0.92, floor=app.tetr.stats["lines"]//5)
        return
    if k=="x" or is_bound("rotate_cw", code) or k in ("up","w") or is_bound("rotate_cw", "KEYW") or is_bound("rotate_cw", "ARROWUP"):
        # If up/w is explicitly bound to hard_drop, don't rotate — let hard_drop below handle it
        # But if up/w is bound to rotate_cw (user custom), rotate
        # Check: if key is up/w and hard_drop bind is exclusive and rotate not bound, treat as hard_drop
        is_hard_only = False
        if k in ("up","w"):
            # If this key code is ONLY bound to hard_drop and not rotate, do hard_drop later
            if is_bound("hard_drop", code) and not is_bound("rotate_cw", code) and not is_bound("rotate_ccw", code):
                is_hard_only = True
        if not is_hard_only:
            if app.tetr.try_rotate(1): 
                play_sfx("tetr.rotate", pitch=1.0, floor=app.tetr.stats["lines"]//5)
            return

    if k=="c" or is_bound("rotate_180", code):
        # 180 — try hold first if hold is bound to same key
        if is_bound("hold", code) and k=="c":
            # In WASD, c is both 180 and hold — prioritize hold
            do_hold(app)
        else:
            if app.tetr.try_rotate(2): 
                play_sfx("tetr.rotate", pitch=0.85, floor=app.tetr.stats["lines"]//5)
        return

    if is_bound("hold", code) or k in ("shift","shiftleft"):
        do_hold(app)
        return

    # Hard drop — space always, plus up/w if they are bound to hard_drop and not rotate
    if k in ("space"," ") or is_bound("hard_drop", code) or (k in ("up","w") and not is_bound("rotate_cw", code) and not is_bound("rotate_ccw", code)):
        dist = 0
        while not app.tetr.board.collides(app.tetr.current,0,1): 
            app.tetr.current.y+=1
            dist+=1
        play_sfx("tetr.harddrop", volume=0.5+min(dist*0.05,0.5), pitch=1.0-dist*0.01, floor=app.tetr.stats["lines"]//5)
        attack,cleared,tspin,is_pc,is_opener,difficult=app.tetr.lock()
        handle_piece_lock(app,attack,cleared,tspin,is_pc,is_opener,difficult)
        app.tetr.spawn(); app.tetr.lock_delay=0
        return

    if k=="escape" or is_bound("forfeit", code): 
        go_title(app)
        return

def onKeyRelease(app,key):
    k=_norm_key(key)
    if k in ("left","a"): app.tetr.das_left=0
    if k in ("right","d"): app.tetr.das_right=0
    if k in ("down","s"): app.tetr.soft_drop=False

def onKeyHold(app,keys):
    if hasattr(app,'inputName') and app.inputName.focused: return
    if app.game_state=="config": return
    normed=set(_norm_key(k) for k in keys)
    if app.game_state!="playing": return
    if "left" in normed or "a" in normed:
        if app.tetr.das_left==0: 
            if app.tetr.try_move(-1,0): play_sfx("tetr.move", pitch=0.96, volume=0.4)
            app.tetr.das_left=1
    if "right" in normed or "d" in normed:
        if app.tetr.das_right==0: 
            if app.tetr.try_move(1,0): play_sfx("tetr.move", pitch=1.04, volume=0.4)
            app.tetr.das_right=1
    if "down" in normed or "s" in normed: app.tetr.soft_drop=True

def do_hold(app):
    if not app.tetr.board.can_hold: 
        play_sfx("tetr.lock", pitch=0.7, volume=0.3)
        return
    play_sfx("tetr.hold")
    if app.tetr.hold_piece is None: app.tetr.hold_piece=app.tetr.current.kind; app.tetr.spawn()
    else: cur=app.tetr.current.kind; app.tetr.current=Piece(app.tetr.hold_piece); app.tetr.hold_piece=cur
    app.tetr.board.can_hold=False
