"""
apps/tetr.py — V6 SOLO + ZEN — Final deploy ready
Includes:
- V5 fixes: keyboard normalized, hard drop unified lock handler, combo/B2B surge fixed, full click/drag handlers for all 20 Wa components
- NEW: SOLO menu per TETR.IO — ZEN (relaxed infinite practice, no top-out), 40 LINES, BLITZ
- TETR.IO accurate: 10x40, SRS+, Multiplier combo base*(1+0.25x) / ln, B2B Charging Surge, Opener Phase, change-on-attack
- BGS single opponent lock: tetr_1v1 env, one opponent only
"""

from scs import *
from browser import window, aio
import math, random, json as py_json, time

try:
    from extensions.canvas_ui import (
        WaTheme, WaButton, WaCard, WaInput, WaDialog, WaBadge, WaCallout,
        WaCheckbox, WaSelect, WaTextarea, WaProgressBar, WaSpinner,
        WaTooltip, WaTabGroup, WaDropdown, WaDropdownItem, WaAvatar,
        WaTag, WaSwitch, WaSlider, WaBreadcrumb, WaDivider
    )
except:
    from canvas_ui import *

# BGS boilerplate (platformer_bgs.py V4 pattern)
_bgs_signals_py = {}
try: window._bgs_signals = {}
except: pass
try: window._bgs_es = None
except: pass
ds_ext = None
USE_EXTENSION_SIGNAL_STORE = False

def _bgs_on_datastar_patch(evt):
    try:
        raw = evt.data
        if isinstance(raw, str) and raw.startswith("signals "): raw = raw[8:]
        try: import json as _jj; parsed=_jj.loads(raw)
        except: parsed=window.JSON.parse(raw)
        import json as _jj2; parsed=_jj2.loads(window.JSON.stringify(parsed))
        if isinstance(parsed, dict):
            for k,v in parsed.items(): _bgs_signals_py[k]=v
            try:
                for k,v in parsed.items(): window._bgs_signals[k]=v
            except: pass
    except: pass

def get_signal(n,d=None):
    if USE_EXTENSION_SIGNAL_STORE and ds_ext:
        try: return ds_ext.get_signal(n,d)
        except: pass
    try:
        if n in _bgs_signals_py: return _bgs_signals_py.get(n,d)
        return window._bgs_signals.get(n,d)
    except: return _bgs_signals_py.get(n,d) if n in _bgs_signals_py else d

def is_datastar_connected():
    if USE_EXTENSION_SIGNAL_STORE and ds_ext:
        try: return ds_ext.is_datastar_connected()
        except: pass
    try:
        es=window._bgs_es
        if not es: return False
        return es.readyState==1
    except: return False

try:
    import extensions.multiplayer as mp_ext
    import extensions.datastar as ds_ext
    if not hasattr(mp_ext,'MultiplayerClient'): raise AttributeError
    MultiplayerClient=mp_ext.MultiplayerClient
    USE_EXTENSION_SIGNAL_STORE=True
    HAS_MP=True
except:
    HAS_MP=True
    class MultiplayerClient:
        def __init__(self,base_url="https://scs-207.onrender.com",environment="level1",environment_name=None,character_name="Player",**kw):
            self.base_url=base_url.rstrip("/"); self.environment_name=environment_name or environment or "level1"; self.client_id=None; self.session_id=None
        async def join(self,retries=3):
            base_url=self.base_url; env_name=self.environment_name
            for _ in range(retries):
                try:
                    url=base_url+"/api/multiplayer/join"
                    payload={"environment_name":env_name,"character_name":"Player"}
                    body=window.JSON.stringify(payload)
                    resp=await window.fetch(url,{"method":"POST","headers":{"Content-Type":"application/json"},"body":body,"mode":"cors"})
                    js=await resp.json(); data=py_json.loads(window.JSON.stringify(js))
                    cid=data.get("client_id"); sid=data.get("session_id")
                    if not cid or not sid: raise Exception("no ids")
                    self.client_id=cid; self.session_id=sid
                    try:
                        su=base_url+"/api/multiplayer/stream?sid="+str(sid)
                        es=window.eval("new EventSource('"+su+"')")
                        window._bgs_es=es; es.addEventListener("datastar-patch-signals",_bgs_on_datastar_patch)
                    except: pass
                    return data
                except: await aio.sleep(1.5)
            return {"client_id":None,"session_id":None}

def send_bgs_patch(app,path,payload):
    try:
        url=app.mp_client.base_url+path
        headers={"Content-Type":"application/json","X-Client-ID":str(app.client_id)}
        body=py_json.dumps(payload,separators=(",",":"))
        script=f"fetch({py_json.dumps(url)},{{method:'PATCH',headers:{py_json.dumps(headers)},body:{py_json.dumps(body)}}}).catch(function(e){{}})"
        window.eval(script); return True
    except: return False

# TETR.IO mechanics
BOARD_W, BOARD_H_INTERNAL = 10, 40
BOARD_H_VISIBLE = 20
CELL = 26
PREVIEW_CELL = 16
TETROMINOES = {'I':[[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],'J':[[1,0,0],[1,1,1],[0,0,0]],'L':[[0,0,1],[1,1,1],[0,0,0]],'O':[[1,1],[1,1]],'S':[[0,1,1],[1,1,0],[0,0,0]],'T':[[0,1,0],[1,1,1],[0,0,0]],'Z':[[1,1,0],[0,1,1],[0,0,0]]}
COLORS = {'I':rgb(0,240,240),'J':rgb(0,0,240),'L':rgb(240,160,0),'O':rgb(240,240,0),'S':rgb(0,240,0),'T':rgb(160,0,240),'Z':rgb(240,0,0),'G':rgb(120,120,120)}
KICKS_JLSTZ={(0,1):[(0,0),(-1,0),(-1,1),(0,-2),(-1,-2)],(1,0):[(0,0),(1,0),(1,-1),(0,2),(1,2)],(1,2):[(0,0),(1,0),(1,-1),(0,2),(1,2)],(2,1):[(0,0),(-1,0),(-1,1),(0,-2),(-1,-2)],(2,3):[(0,0),(1,0),(1,1),(0,-2),(1,-2)],(3,2):[(0,0),(-1,0),(-1,-1),(0,2),(-1,2)],(3,0):[(0,0),(-1,0),(-1,-1),(0,2),(-1,2)],(0,3):[(0,0),(1,0),(1,1),(0,-2),(1,-2)]}
KICKS_I={(0,1):[(0,0),(-2,0),(1,0),(-2,-1),(1,2)],(1,0):[(0,0),(2,0),(-1,0),(2,1),(-1,-2)],(1,2):[(0,0),(-1,0),(2,0),(-1,2),(2,-1)],(2,1):[(0,0),(1,0),(-2,0),(1,-2),(-2,1)],(2,3):[(0,0),(2,0),(-1,0),(2,1),(-1,-2)],(3,2):[(0,0),(-2,0),(1,0),(-2,-1),(1,2)],(3,0):[(0,0),(1,0),(-2,0),(1,-2),(-2,1)],(0,3):[(0,0),(-1,0),(2,0),(-1,2),(2,-1)]}
BASE_ATTACK={(1,False,False,False):0,(2,False,False,False):1,(3,False,False,False):2,(4,False,False,False):4,(0,True,False,False):0,(1,True,False,False):2,(2,True,False,False):4,(3,True,False,False):6,(1,True,True,False):0,(2,True,True,False):1,(0,False,False,True):10}

def calc_attack(base,combo,mode="DOWN"):
    if combo<=0: return base
    if base==0:
        val=math.log(1+1.25*combo) if combo>=2 else 0
    else:
        val=base*(1+0.25*combo)
    if mode=="DOWN": return math.floor(val)
    else:
        f=math.floor(val); frac=val-f
        return f+(1 if random.random()<frac else 0)

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
            # ZEN: garbage never kills, just pushes if possible
            for _ in range(lines):
                if any(self.grid[0][c] is not None for _ in range(BOARD_W)):
                    # in ZEN, clear top rows instead of topping out
                    self.grid.pop(0); self.grid.insert(0,[None]*BOARD_W)
                cur=hole if random.random()>mess else random.randint(0,BOARD_W-1)
                self.grid.pop(0); self.grid.append([('G' if c!=cur else None) for c in range(BOARD_W)])
            return False
        for _ in range(lines):
            if any(self.grid[0][c] is not None for _ in range(BOARD_W)): return True
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
        self.mode=mode
        self.board=Board()
        self.board.zen = (mode=="zen")
        self.bag=new_bag(); self.next_queue=[]
        for _ in range(5):
            if not self.bag: self.bag=new_bag()
            self.next_queue.append(self.bag.pop())
        self.current=Piece(self.next_queue.pop(0))
        if not self.bag: self.bag=new_bag()
        self.next_queue.append(self.bag.pop())
        self.hold_piece=None; self.ghost_y=0; self.lock_delay=0; self.lock_max=30; self.gravity_timer=0
        # ZEN: much slower gravity, longer lock delay
        if mode=="zen":
            self.gravity_speed=55
            self.lock_max=45
        elif mode=="40lines":
            self.gravity_speed=20
            self.lock_max=30
        elif mode=="blitz":
            self.gravity_speed=18
            self.lock_max=25
        else:
            self.gravity_speed=40
            self.lock_max=30
        self.das_left=0; self.das_right=0; self.arr=2; self.das=10; self.sdf=6; self.soft_drop=False; self.game_over=False
        self.stats={"apm":0,"pps":0,"attack":0,"pieces":0,"start":time.time(),"lines":0,"score":0,"time":0}
        self.rounding="DOWN" if mode not in ("quick_play","blitz") else "RNG"
        self.last_combo_text=""; self.last_b2b_text=""
        self.solo_target=40 if mode=="40lines" else None
        self.blitz_time=120 if mode=="blitz" else None
    def spawn(self):
        k=self.next_queue.pop(0)
        if not self.bag: self.bag=new_bag()
        self.next_queue.append(self.bag.pop())
        self.current=Piece(k); self.lock_delay=0
        if self.board.collides(self.current):
            if self.mode=="zen":
                # ZEN: never top out — clear top 6 rows and keep going (relaxed practice)
                for _ in range(6):
                    if any(self.board.grid[0][c] is not None for c in range(BOARD_W)):
                        self.board.grid.pop(0)
                        self.board.grid.insert(0,[None]*BOARD_W)
                # try again
                if self.board.collides(self.current):
                    # still colliding? shift up
                    self.current.y = -2
            else:
                self.game_over=True
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
            if self.board.b2b_streak>=4:
                self.board.surge_charged=self.board.b2b_streak if self.mode!="quick_play" else max(1,self.board.b2b_streak-3)
            self.last_b2b_text=f"B2B x{self.board.b2b_streak}" if self.board.b2b_streak>=1 else ""
        else:
            if cleared>0:
                if self.board.b2b_streak>=4:
                    base+=self.board.surge_charged
                    self.board.surge_charged=0
                    self.last_b2b_text=f"SURGE {base}"
                self.board.b2b_streak=-1
                if cleared==0: self.last_b2b_text=""
        cur_combo_for_calc = self.board.combo + 1 if cleared>0 else self.board.combo
        attack=calc_attack(base,cur_combo_for_calc,self.rounding)
        if self.mode=="quick_play" and cleared==1 and not is_tspin and self.board.combo<0:
            attack=max(attack,1)
        is_opener=self.board.pieces_placed<=14
        if cleared>0:
            self.board.combo+=1
            if self.board.combo>=1:
                self.last_combo_text=f"{self.board.combo+1} COMBO"
            else:
                self.last_combo_text=""
            self.stats["lines"]+=cleared
            self.stats["score"]+= [0,100,300,500,800][cleared] if cleared<=4 else 800
            if is_tspin:
                self.stats["score"]+= [0,400,800,1200][cleared] if cleared<=3 else 0
        else:
            self.board.combo=-1
            self.last_combo_text=""
        self.board.attack=attack; self.board.lines+=cleared; self.stats["attack"]+=attack; self.stats["pieces"]+=1
        return attack,cleared,is_tspin,is_pc,is_opener,difficult

def handle_piece_lock(app, attack, cleared, is_tspin, is_pc, is_opener, difficult):
    inc = app.mp_wrapper.match["garbage"]["incoming"]
    remaining_attack = attack
    if app.tetr.mode in ("zen","40lines","blitz"):
        # SOLO: no opponent garbage, but ZEN still has no incoming
        remaining_attack=0
        app.progressGarbage.value=0.0
        app.tetr.board.attack=0
        return
    if is_opener and inc and remaining_attack>0:
        pending_total = sum(g["lines"] for g in inc)
        if remaining_attack < pending_total:
            cancel_target = remaining_attack*2
            while cancel_target>0 and inc:
                g=inc[0]
                if g["lines"]<=cancel_target: cancel_target-=g["lines"]; inc.pop(0)
                else: g["lines"]-=cancel_target; cancel_target=0
            remaining_attack=0
        else:
            while remaining_attack>0 and inc:
                g=inc[0]
                if g["lines"]<=remaining_attack: remaining_attack-=g["lines"]; inc.pop(0)
                else: g["lines"]-=remaining_attack; remaining_attack=0
    else:
        while remaining_attack>0 and inc:
            g=inc[0]
            if g["lines"]<=remaining_attack: remaining_attack-=g["lines"]; inc.pop(0)
            else: g["lines"]-=remaining_attack; remaining_attack=0
    if remaining_attack>0:
        app.progressGarbage.value=min(1.0,remaining_attack/8.0)
        app.tetr.board.attack=remaining_attack
    else:
        app.tetr.board.attack=0
        app.progressGarbage.value=0.0
    if inc and cleared==0 and random.random()<0.15:
        g=inc.pop(0)
        topped=app.tetr.board.add_garbage(g["lines"],g["hole"],0.15)
        if topped and not app.tetr.board.zen:
            app.tetr.game_over=True

def onAppStart(app):
    app.width=1120; app.height=760; app.stepsPerSecond=60
    app.background=rgb(15,17,21)
    app.tetr=TetrGame(mode="tetra_league")
    app.mp_wrapper=SingleOpponentClient(app)
    app.game_state="menu"; app.username="Player1"
    app.room_id="tetr_1v1"; app.client_id=None; app.mp_client=None; app.datastar_connected=False
    app.remote_players={}; app.single_opponent_id=None; app.single_opponent_board=None
    app.last_send_ms=0; app.last_character_state=None; app.remote_timestamps={}

    LEFT_X=20; LEFT_W=240
    BOARD_X=300; BOARD_Y=84
    NEXT_X=BOARD_X+BOARD_W*CELL+24
    OPP_X=NEXT_X+120+24
    app.BOARD_X=BOARD_X; app.BOARD_Y=BOARD_Y; app.NEXT_X=NEXT_X; app.OPP_X=OPP_X; app.LEFT_X=LEFT_X

    # Top — now includes SOLO modes
    app.breadcrumb=WaBreadcrumb(LEFT_X,10,["Home","Arcade","TETR.IO 1v1","SOLO"])
    app.tabGroup=WaTabGroup(LEFT_X,30,w=320,tabs=["Tetra League","Quick Play","SOLO: ZEN","SOLO: 40L","SOLO: Blitz"])
    y=72
    app.avatarLocal=WaAvatar(LEFT_X,y,size=40,initials="YOU",variant="brand")
    app.inputName=WaInput(LEFT_X+52,y+4,w=LEFT_W-52-4,h=32,placeholder="Username",value=app.username,label="Player")
    y+=52
    app.avatarOpp=WaAvatar(LEFT_X,y,size=40,initials="OPP",variant="neutral")
    app.badgeOPP=WaBadge("NO OPP",LEFT_X+52,y+8,variant="neutral")
    y+=52
    app.btnFind=WaButton("FIND OPPONENT (1v1 BGS)",LEFT_X,y,w=LEFT_W,h=40,variant="brand",onClick=lambda: start_search(app))
    y+=52
    app.btnCancel=WaButton("CANCEL",LEFT_X,y,w=LEFT_W,h=36,variant="neutral",appearance="outlined",onClick=lambda: cancel_search(app))
    y+=12
    app.badgeTR=WaBadge("TR 12500",LEFT_X,y,variant="brand")
    app.badgeAPM=WaBadge("APM 0",LEFT_X+90,y,variant="success")
    app.badgePPS=WaBadge("PPS 0",LEFT_X+160,y,variant="warning")
    y+=30
    app.selectMode=WaSelect(LEFT_X,y,w=LEFT_W,options=["Tetra League","Quick Play","ZEN (Relaxed)","40 Lines","Blitz (2min)"],value="Tetra League",label="Mode / SOLO")
    y+=52
    app.switchGhost=WaSwitch(LEFT_X,y,checked=True,label="Ghost piece",variant="brand")
    y+=28
    app.switchHold=WaSwitch(LEFT_X,y,checked=True,label="Hold allowed")
    y+=28
    app.checkboxSFX=WaCheckbox(LEFT_X,y,label="SFX / Proc Audio",checked=True)
    y+=28
    app.sliderDAS=WaSlider(LEFT_X,y,w=LEFT_W,min=4,max=20,value=10,label="DAS",variant="brand")
    y+=32
    app.sliderARR=WaSlider(LEFT_X,y,w=LEFT_W,min=0,max=8,value=2,label="ARR")
    y+=32
    app.sliderSDF=WaSlider(LEFT_X,y,w=LEFT_W,min=1,max=20,value=6,label="SDF")
    y+=36
    app.progressGarbage=WaProgressBar(LEFT_X,y,w=LEFT_W,h=8,value=0.0,variant="danger")
    y+=18
    app.tagQuad=WaTag("Quad",LEFT_X,y,variant="brand")
    app.tagTSpin=WaTag("T-Spin",LEFT_X+64,y,variant="warning")
    y+=32
    app.callout=WaCallout(LEFT_X,y,w=LEFT_W,message="SOLO: ZEN = no lose, infinite practice. 40L = clear 40 lines. Blitz = 2min score.",variant="brand",title="SOLO + 1v1 INVARIANT")
    y+=60
    app.divider=WaDivider(LEFT_X,y,w=LEFT_W,label="stats")
    y+=20
    app.dropdown=WaDropdown(LEFT_X,y,w=100,items=[WaDropdownItem("Profile"),WaDropdownItem("Settings"),WaDropdownItem("Report Bug","warning")],label="More")
    app.tooltipControls=WaTooltip("Arrows/WASD, Z/X rotate, C hold, Space hard drop",LEFT_X+110,y,w=130)
    app.tooltipControls.visible=True
    y+=38
    app.btnHold=WaButton("HOLD (C)",LEFT_X,y,w=100,h=32,variant="neutral",appearance="outlined",onClick=lambda: do_hold(app))
    app.btn180=WaButton("180° (X)",LEFT_X+110,y,w=100,h=32,variant="neutral",appearance="outlined",onClick=lambda: app.tetr.try_rotate(2))
    app.spinner=WaSpinner(BOARD_X+BOARD_W*CELL//2-14,BOARD_Y+200,size=28)

    app.board_x=BOARD_X; app.board_y=BOARD_Y; app.opp_board_x=OPP_X; app.opp_board_y=BOARD_Y

    if HAS_MP:
        base_url="https://scs-207.onrender.com"
        try:
            if hasattr(window,'location') and 'localhost' in window.location.hostname: base_url="http://localhost:10000"
        except: pass
        app.mp_client=MultiplayerClient(base_url=base_url,environment_name="tetr_1v1",character_name="TetrPlayer")
        def on_char_state(updates):
            for u in updates:
                cid=u.get("clientId")
                if cid and cid!=app.client_id: app.remote_players[cid]=u
        if hasattr(app.mp_client,'on_character_state'): app.mp_client.on_character_state=on_char_state
        async def join_mp():
            try:
                res=await app.mp_client.join()
                cid=None
                try: cid=res.get("client_id") if isinstance(res,dict) else None
                except: pass
                if not cid:
                    try:
                        import json as _j
                        d=_j.loads(window.JSON.stringify(res)) if hasattr(window,'JSON') else {}
                        cid=d.get("client_id")
                    except: cid=getattr(res,"client_id",None)
                app.client_id=cid; app.room_id="tetr_1v1"
            except Exception as e: print(f"[TETR] Join failed {e}")
        aio.run(join_mp())

    app.dialogGameOver=WaDialog("Match Finished","You topped out.",w=420,h=180,variant="danger")
    app.dialogGameOver.buttons=[WaButton("RETRY",0,0,w=100,h=36,variant="brand",onClick=lambda: reset_game(app)), WaButton("MENU",0,0,w=80,h=36,variant="neutral",appearance="outlined",onClick=lambda: go_menu(app))]

def start_search(app):
    if app.game_state=="searching": return
    tab = app.tabGroup.tabs[app.tabGroup.active] if hasattr(app.tabGroup,'tabs') else "Tetra League"
    # Map tabs + selectMode to actual mode
    if "ZEN" in tab or "ZEN" in app.selectMode.value:
        mode="zen"; env="tetr_zen"
    elif "40L" in tab or "40" in app.selectMode.value:
        mode="40lines"; env="tetr_40l"
    elif "Blitz" in tab or "Blitz" in app.selectMode.value:
        mode="blitz"; env="tetr_blitz"
    elif "Quick" in tab or "Quick" in app.selectMode.value:
        mode="quick_play"; env="tetr_1v1_quick"
    else:
        mode="tetra_league"; env="tetr_1v1"
    app.room_id=env
    app.tetr=TetrGame(mode=mode)
    if mode in ("zen","40lines","blitz"):
        # SOLO: no opponent needed
        app.game_state="playing"
        app.single_opponent_id=None
        app.badgeOPP.text="SOLO"
        app.mp_wrapper.match["queue"]["status"]="solo"
    else:
        app.mp_wrapper.findOpponent()
        app.game_state="searching"
        app.single_opponent_id=None; app.single_opponent_board=None
        app.badgeOPP.text="SEARCHING..."

def cancel_search(app):
    app.mp_wrapper.cancelSearch(); app.game_state="menu"; app.single_opponent_id=None; app.badgeOPP.text="NO OPP"

def reset_game(app):
    # Keep same mode on retry (ZEN/40L/Blitz keep their solo logic)
    cur_mode = app.tetr.mode
    app.tetr=TetrGame(mode=cur_mode)
    app.mp_wrapper.match["garbage"]["incoming"]=[]; app.dialogGameOver.hide()
    if cur_mode in ("zen","40lines","blitz"):
        app.game_state="playing"
        app.badgeOPP.text="SOLO"
    else:
        app.game_state="playing"
        app.badgeOPP.text=f"OPP {str(app.single_opponent_id)[:6]}" if app.single_opponent_id else "NO OPP"

def go_menu(app):
    app.dialogGameOver.hide(); app.game_state="menu"; app.mp_wrapper.match["players"]["opponent"]=None; app.mp_wrapper.match["queue"]["status"]="idle"; app.single_opponent_id=None; app.badgeOPP.text="NO OPP"

def onStep(app):
    if HAS_MP:
        try:
            sig=get_signal("character-state-update")
            if sig and isinstance(sig,dict):
                for u in sig.get("updates",[]):
                    cid=u.get("clientId")
                    if not cid or cid==app.client_id: continue
                    if app.tetr.mode in ("zen","40lines","blitz"): continue
                    if app.single_opponent_id is None:
                        app.single_opponent_id=cid
                        app.mp_wrapper._secureOpponent({"id":cid,"username":f"OPP_{cid[:4]}"})
                        app.badgeOPP.text=f"OPP {cid[:4]}"
                    if cid!=app.single_opponent_id: continue
                    ts=u.get("timestamp",0)
                    if ts>app.remote_timestamps.get(cid,-1):
                        app.remote_timestamps[cid]=ts
                        app.remote_players[cid]=u
                        if "tetrBoard" in u: app.single_opponent_board=u.get("tetrBoard")
                        if "tetrAttack" in u:
                            atk=int(u.get("tetrAttack",0))
                            if atk>0 and app.tetr.mode not in ("zen","40lines","blitz"):
                                is_opener=app.tetr.board.pieces_placed<=14
                                pending=len(app.mp_wrapper.match["garbage"]["incoming"])
                                if is_opener and atk < pending:
                                    cancel=atk*2
                                    while cancel>0 and app.mp_wrapper.match["garbage"]["incoming"]:
                                        g=app.mp_wrapper.match["garbage"]["incoming"][0]
                                        if g["lines"]<=cancel: cancel-=g["lines"]; app.mp_wrapper.match["garbage"]["incoming"].pop(0)
                                        else: g["lines"]-=cancel; cancel=0
                                else:
                                    hole=random.randint(0,BOARD_W-1)
                                    app.mp_wrapper.match["garbage"]["incoming"].append({"lines":atk,"hole":hole})
            app.datastar_connected=is_datastar_connected()
        except: pass

    if app.game_state=="searching":
        app.mp_wrapper.search_timer+=1
        app.spinner.angle+=8
        if app.single_opponent_id is not None:
            app.game_state="playing"; app.tetr=TetrGame(mode=app.tetr.mode)
        elif app.mp_wrapper.search_timer>180:
            opp={"id":f"bot_{random.randint(1000,9999)}","tr":12000,"bot_ai":{"timer":0}}
            if app.single_opponent_id is None and app.tetr.mode not in ("zen","40lines","blitz"):
                app.single_opponent_id=opp["id"]
                app.mp_wrapper._secureOpponent(opp)
                app.game_state="playing"; app.tetr=TetrGame(mode=app.tetr.mode)
                app.badgeOPP.text=f"BOT {opp['id'][-4:]}"

    if app.game_state!="playing": return
    if app.tetr.game_over:
        app.game_state="gameover"; app.dialogGameOver.show(); return

    # SOLO win/lose conditions
    if app.tetr.mode=="40lines" and app.tetr.stats["lines"]>=40:
        app.game_state="gameover"
        app.dialogGameOver.title="40 LINES CLEAR!"
        app.dialogGameOver.message=f"Time: {time.time()-app.tetr.stats['start']:.2f}s"
        app.dialogGameOver.show()
        return
    if app.tetr.mode=="blitz":
        elapsed=time.time()-app.tetr.stats["start"]
        if elapsed>=120:
            app.game_state="gameover"
            app.dialogGameOver.title="BLITZ FINISH!"
            app.dialogGameOver.message=f"Score: {app.tetr.stats['score']} lines {app.tetr.stats['lines']}"
            app.dialogGameOver.show()
            return

    app.tetr.gravity_timer+=1
    grav=app.tetr.gravity_speed
    if app.tetr.soft_drop:
        sdf_val=int(app.sliderSDF.value) if hasattr(app,'sliderSDF') else 6
        grav=max(1,40//max(1,int(sdf_val)))
    if app.tetr.gravity_timer>=grav:
        app.tetr.gravity_timer=0
        if not app.tetr.try_move(0,1):
            app.tetr.lock_delay+=1
            if app.tetr.lock_delay>app.tetr.lock_max:
                attack,cleared,tspin,is_pc,is_opener,difficult=app.tetr.lock()
                handle_piece_lock(app,attack,cleared,tspin,is_pc,is_opener,difficult)
                app.tetr.spawn()
                app.tetr.lock_delay=0
        else:
            app.tetr.lock_delay=0

    if app.tetr.das_left>0:
        app.tetr.das_left+=1
        if app.tetr.das_left>int(app.sliderDAS.value):
            if (app.tetr.das_left - int(app.sliderDAS.value)) % max(1,int(app.sliderARR.value)+1)==0:
                app.tetr.try_move(-1,0)
    if app.tetr.das_right>0:
        app.tetr.das_right+=1
        if app.tetr.das_right>int(app.sliderDAS.value):
            if (app.tetr.das_right - int(app.sliderDAS.value)) % max(1,int(app.sliderARR.value)+1)==0:
                app.tetr.try_move(1,0)

    opp=app.mp_wrapper.getOpponent()
    if opp and isinstance(opp,dict) and "bot_ai" in opp:
        opp["bot_ai"]["timer"]+=1
        if opp["bot_ai"]["timer"]%90==0 and random.random()<0.3 and app.tetr.mode not in ("zen","40lines","blitz"):
            app.mp_wrapper.match["garbage"]["incoming"].append({"lines":random.choice([1,1,2]),"hole":random.randint(0,BOARD_W-1)})

    app.tetr.update_ghost()
    elapsed=max(1,time.time()-app.tetr.stats["start"])
    app.badgeAPM.text=f"APM {int(app.tetr.stats['attack']/elapsed*60)}"
    app.badgePPS.text=f"PPS {app.tetr.stats['pieces']/elapsed:.2f}"

    if HAS_MP and app.mp_client and app.client_id and app.game_state=="playing" and app.tetr.mode not in ("zen","40lines","blitz"):
        now=0
        try: now=int(window.Date.now())
        except: now=int(app.tetr.board.lines*100)
        flat=[]
        for r in range(BOARD_H_INTERNAL-20,BOARD_H_INTERNAL):
            for c in range(BOARD_W):
                flat.append(1 if app.tetr.board.grid[r][c] is not None else 0)
        state=(round(float(app.tetr.current.x),2),round(float(app.tetr.current.y),2),float(app.tetr.board.attack))
        changed=state!=app.last_character_state
        if now-app.last_send_ms>=100 and (changed or now-app.last_send_ms>=1000):
            app.last_send_ms=now; app.last_character_state=state
            payload={"updates":[{"clientId":str(app.client_id),"characterModelId":"tetr-1v1","position":[float(app.tetr.current.x),float(app.tetr.current.y)],"velocity":[float(app.tetr.board.attack),float(app.tetr.board.combo)],"animationState":"topped" if app.tetr.game_over else "playing","score":int(app.tetr.board.lines),"timestamp":now,"tetrBoard":flat,"tetrAttack":int(app.tetr.board.attack),"tetrB2B":int(app.tetr.board.b2b_streak),"tetrSurge":int(app.tetr.board.surge_charged),"tetrCombo":int(app.tetr.board.combo)}],"timestamp":now}
            send_bgs_patch(app,"/api/multiplayer/character-state",payload)
            if app.tetr.board.attack>0:
                app.tetr.board.attack=0

def redrawAll(app):
    app.breadcrumb.draw()
    app.tabGroup.draw()
    app.avatarLocal.draw()
    app.avatarOpp.draw()
    app.inputName.draw()
    app.badgeOPP.draw()
    app.btnFind.draw()
    if app.game_state=="searching":
        app.btnCancel.draw()
    app.badgeTR.draw()
    app.badgeAPM.draw()
    app.badgePPS.draw()
    app.selectMode.draw()
    app.switchGhost.draw()
    app.switchHold.draw()
    app.checkboxSFX.draw()
    app.sliderDAS.draw()
    app.sliderARR.draw()
    app.sliderSDF.draw()
    app.progressGarbage.draw()
    app.tagQuad.draw()
    app.tagTSpin.draw()
    app.callout.draw()
    app.divider.draw()
    app.dropdown.draw()
    app.tooltipControls.draw()
    app.btnHold.draw()
    app.btn180.draw()

    if app.game_state in ("playing","searching","gameover"):
        draw_board(app,app.tetr.board,app.board_x,app.board_y,CELL,app.tetr.current,app.tetr.ghost_y,app.switchGhost.checked)
        draw_next(app)
        draw_hold(app)
        draw_opponent_board(app)
        if app.tetr.last_combo_text:
            drawLabel(app.tetr.last_combo_text,app.board_x+BOARD_W*CELL//2,app.board_y+80,size=18,fill=rgb(255,230,100),bold=True)
        if app.tetr.last_b2b_text:
            drawLabel(app.tetr.last_b2b_text,app.board_x+BOARD_W*CELL//2,app.board_y+105,size=14,fill=rgb(150,220,255),bold=True)
        # SOLO HUD
        if app.tetr.mode=="40lines":
            drawLabel(f"40L: {app.tetr.stats['lines']}/40",app.board_x+BOARD_W*CELL//2,app.board_y-18,size=14,fill="white",bold=True)
        elif app.tetr.mode=="blitz":
            elapsed=int(time.time()-app.tetr.stats["start"])
            drawLabel(f"BLITZ {120-elapsed}s Score {app.tetr.stats['score']}",app.board_x+BOARD_W*CELL//2,app.board_y-18,size=12,fill="white",bold=True)
        elif app.tetr.mode=="zen":
            drawLabel(f"ZEN — Relaxed Practice (No Top-Out)",app.board_x+BOARD_W*CELL//2,app.board_y-18,size=12,fill=rgb(120,255,150),bold=True)

    if app.game_state=="searching":
        app.spinner.draw()
        drawLabel(f"Searching {app.room_id} — lock {app.single_opponent_id or '...'}",app.board_x+130,app.board_y+220,size=12,fill="white",bold=True)
        drawLabel(f"BGS { 'CONNECTED' if app.datastar_connected else 'LOCAL DEMO'} | remote {len(app.remote_players)} -> 1",app.board_x+130,app.board_y+238,size=9,fill=rgb(150,160,180))

    app.selectMode.drawOverlay()
    app.dropdown.drawOverlay()

    app.dialogGameOver.draw(app.width,app.height)
    if app.dialogGameOver.open:
        cx=app.width/2; cy=app.height/2
        app.dialogGameOver.buttons[0].x=cx-110; app.dialogGameOver.buttons[0].y=cy+40
        app.dialogGameOver.buttons[1].x=cx+10; app.dialogGameOver.buttons[1].y=cy+40
        for b in app.dialogGameOver.buttons: b.draw()

    drawLabel(f"MATCH {app.mp_wrapper.match['match_id']} | 10x40 SRS+ | {app.tetr.rounding} | B2B {app.tetr.board.b2b_streak} Surge {app.tetr.board.surge_charged} Combo {app.tetr.board.combo} | {app.single_opponent_id} | {app.tetr.mode.upper()}",app.width/2,app.height-12,size=8,fill=rgb(120,120,130))
    drawLabel(f"BGS-MP-SYNC | ENV: {app.room_id} | SINGLE OPP: {app.single_opponent_id or 'none'} | REMOTE: {len(app.remote_players)}->1 | MULT + B2B CHARGING + SOLO ZEN",app.width/2,14,size=10,fill=rgb(200,210,230))
    drawCircle(app.width-20,14,5,fill=rgb(100,255,100) if app.datastar_connected else rgb(255,200,100))

def draw_board(app,board,ox,oy,cell,cur_piece=None,ghost_y=None,show_ghost=True):
    try:
        from scs import drawRect, drawLine
        drawRect(ox-6,oy-6,BOARD_W*cell+12,BOARD_H_VISIBLE*cell+12,fill=rgb(20,22,28),border=rgb(60,64,80),borderWidth=1,roundness=12)
        for y in range(BOARD_H_VISIBLE+1): drawLine(ox,oy+y*cell,ox+BOARD_W*cell,oy+y*cell,fill=rgb(35,38,50),lineWidth=1)
        for x in range(BOARD_W+1): drawLine(ox+x*cell,oy,ox+x*cell,oy+BOARD_H_VISIBLE*cell,fill=rgb(35,38,50),lineWidth=1)
        start_r=BOARD_H_INTERNAL-BOARD_H_VISIBLE
        for r in range(BOARD_H_VISIBLE):
            gr=start_r+r
            for c in range(BOARD_W):
                k=board.grid[gr][c]
                if k:
                    col=COLORS.get(k,rgb(40,40,50))
                    drawRect(ox+c*cell+1,oy+r*cell+1,cell-2,cell-2,fill=col,roundness=4)
                    drawRect(ox+c*cell+2,oy+r*cell+2,cell-4,4,fill="white",opacity=22,roundness=2)
        if cur_piece and show_ghost and ghost_y is not None:
            for r in range(len(cur_piece.shape)):
                for c in range(len(cur_piece.shape[0])):
                    if cur_piece.shape[r][c]:
                        x=cur_piece.x+c; y=ghost_y+r; vis_y=y-start_r
                        if 0<=vis_y<BOARD_H_VISIBLE and 0<=x<BOARD_W:
                            drawRect(ox+x*cell+1,oy+vis_y*cell+1,cell-2,cell-2,fill=None,border=COLORS[cur_piece.kind],borderWidth=2,roundness=4,opacity=35)
        if cur_piece:
            for r in range(len(cur_piece.shape)):
                for c in range(len(cur_piece.shape[0])):
                    if cur_piece.shape[r][c]:
                        x=cur_piece.x+c; y=cur_piece.y+r; vis_y=y-start_r
                        if 0<=vis_y<BOARD_H_VISIBLE and 0<=x<BOARD_W:
                            col=COLORS[cur_piece.kind]
                            drawRect(ox+x*cell+1,oy+vis_y*cell+1,cell-2,cell-2,fill=col,roundness=4)
    except: pass

def draw_next(app):
    try:
        from scs import drawRect, drawLabel
        nx=app.NEXT_X; ny=app.board_y
        drawRect(nx,ny,110,280,fill=rgb(26,29,36),border=rgb(50,54,70),borderWidth=1,roundness=12)
        drawLabel("NEXT (5)",nx+55,ny+14,size=12,fill="white",bold=True)
        for i,kind in enumerate(app.tetr.next_queue[:5]):
            shape=TETROMINOES[kind]; base_y=ny+30+i*50; base_x=nx+20
            for r in range(len(shape)):
                for c in range(len(shape[0])):
                    if shape[r][c]: drawRect(base_x+c*PREVIEW_CELL,base_y+r*PREVIEW_CELL,PREVIEW_CELL-2,PREVIEW_CELL-2,fill=COLORS[kind],roundness=3)
    except: pass

def draw_hold(app):
    try:
        from scs import drawRect, drawLabel
        hx=app.board_x-90; hy=app.board_y
        drawRect(hx,hy,80,70,fill=rgb(26,29,36),border=rgb(50,54,70),borderWidth=1,roundness=12)
        drawLabel("HOLD",hx+40,hy+10,size=10,fill=rgb(180,180,190),bold=True)
        if app.tetr.hold_piece:
            shape=TETROMINOES[app.tetr.hold_piece]
            for r in range(len(shape)):
                for c in range(len(shape[0])):
                    if shape[r][c]: drawRect(hx+12+c*PREVIEW_CELL,hy+22+r*PREVIEW_CELL,PREVIEW_CELL-2,PREVIEW_CELL-2,fill=COLORS[app.tetr.hold_piece],roundness=3)
    except: pass

def draw_opponent_board(app):
    try:
        from scs import drawRect, drawLabel
        ox=app.opp_board_x; oy=app.opp_board_y; cell=14
        drawRect(ox-6,oy-6,BOARD_W*cell+12,BOARD_H_VISIBLE*cell+12,fill=rgb(18,20,26),border=rgb(60,64,80),borderWidth=1,roundness=12)
        opp_id=app.single_opponent_id or "none"
        if app.tetr.mode in ("zen","40lines","blitz"):
            label=f"SOLO {app.tetr.mode.upper()} — No OPP"
        else:
            label=f"OPP {str(opp_id)[:6]} B2B:{app.tetr.board.b2b_streak} S:{app.tetr.board.surge_charged} C:{app.tetr.board.combo}" if opp_id!="none" else "NO OPPONENT LOCKED (1v1)"
        drawLabel(label,ox+BOARD_W*cell//2,oy-12,size=9,fill="white",bold=True)
        board=app.single_opponent_board
        if board and len(board)>=200 and app.tetr.mode not in ("zen","40lines","blitz"):
            for r in range(BOARD_H_VISIBLE):
                for c in range(BOARD_W):
                    idx=r*BOARD_W+c
                    if idx < len(board) and board[idx]:
                        drawRect(ox+c*cell+1,oy+r*cell+1,cell-2,cell-2,fill=rgb(100,120,160),roundness=3)
        if app.tetr.mode in ("zen","40lines","blitz"):
            drawLabel("ZEN = relaxed infinite",ox+BOARD_W*cell//2,oy+BOARD_H_VISIBLE*cell//2,size=9,fill=rgb(100,140,120))
        else:
            inc=len(app.mp_wrapper.match["garbage"]["incoming"])
            if inc:
                drawRect(ox-6,oy+BOARD_H_VISIBLE*cell+8,BOARD_W*cell+12,10,fill=rgb(60,20,20),roundness=6)
                drawRect(ox-6,oy+BOARD_H_VISIBLE*cell+8,min(BOARD_W*cell+12,inc*12),10,fill=rgb(220,50,50),roundness=6)
    except: pass

def onMousePress(app,mx,my):
    if app.dialogGameOver.open:
        for b in app.dialogGameOver.buttons:
            if b.contains(mx,my) and b.handlePress(mx,my): return True
    if app.selectMode.expanded:
        if app.selectMode.handlePress(mx,my): return True
    if app.dropdown.open:
        res = app.dropdown.handlePress(mx,my)
        if res: return True
    if app.tabGroup.handlePress(mx,my):
        # Sync selectMode with tab
        tab = app.tabGroup.tabs[app.tabGroup.active]
        if "ZEN" in tab: app.selectMode.value="ZEN (Relaxed)"
        elif "40L" in tab: app.selectMode.value="40 Lines"
        elif "Blitz" in tab: app.selectMode.value="Blitz (2min)"
        elif "Quick" in tab: app.selectMode.value="Quick Play"
        else: app.selectMode.value="Tetra League"
        return True
    if app.btnFind.contains(mx,my) and app.btnFind.handlePress(mx,my): return True
    if app.game_state=="searching" and app.btnCancel.contains(mx,my) and app.btnCancel.handlePress(mx,my): return True
    if app.selectMode.contains(mx,my) and app.selectMode.handlePress(mx,my): return True
    if app.switchGhost.handlePress(mx,my): return True
    if app.switchHold.handlePress(mx,my): return True
    if app.checkboxSFX.toggle(mx,my): return True
    if app.sliderDAS.handlePress(mx,my): return True
    if app.sliderARR.handlePress(mx,my): return True
    if app.sliderSDF.handlePress(mx,my): return True
    if app.dropdown.contains(mx,my) and app.dropdown.handlePress(mx,my): return True
    if app.tagQuad.contains(mx,my) and app.tagQuad.handlePress(mx,my): return True
    if app.tagTSpin.contains(mx,my) and app.tagTSpin.handlePress(mx,my): return True
    if app.btnHold.contains(mx,my) and app.btnHold.handlePress(mx,my): do_hold(app); return True
    if app.btn180.contains(mx,my) and app.btn180.handlePress(mx,my): app.tetr.try_rotate(2); return True
    if app.inputName.contains(mx,my):
        app.inputName.focused=True; return True
    else:
        app.inputName.focused=False
    return False

def onMouseMove(app,mx,my):
    for comp in [app.btnFind, app.btnCancel, app.tabGroup, app.selectMode, app.switchGhost, app.switchHold, app.checkboxSFX, app.sliderDAS, app.sliderARR, app.sliderSDF, app.dropdown, app.tagQuad, app.tagTSpin, app.btnHold, app.btn180, app.inputName]:
        if hasattr(comp,'handleMove'): comp.handleMove(mx,my)
    if app.sliderDAS.dragging and app.sliderDAS.handleDrag(mx,my): return True
    if app.sliderARR.dragging and app.sliderARR.handleDrag(mx,my): return True
    if app.sliderSDF.dragging and app.sliderSDF.handleDrag(mx,my): return True
    return False

def onMouseRelease(app,mx,my):
    for comp in [app.sliderDAS, app.sliderARR, app.sliderSDF, app.btnFind, app.btnCancel, app.btnHold, app.btn180]:
        if hasattr(comp,'handleRelease'): comp.handleRelease(mx,my)
    return False

def onMouseDrag(app,mx,my): return onMouseMove(app,mx,my)

def _norm_key(k):
    if not k: return ""
    kl = str(k).lower()
    mapping = {"arrowleft":"left","arrowright":"right","arrowup":"up","arrowdown":"down"," ":"space","spacebar":"space"}
    return mapping.get(kl, kl)

def onKeyPress(app,key):
    k = _norm_key(key)
    if app.game_state!="playing":
        if k=="r": reset_game(app)
        return
    if k in ("left","a"):
        app.tetr.try_move(-1,0)
    elif k in ("right","d"):
        app.tetr.try_move(1,0)
    elif k in ("down","s"):
        app.tetr.soft_drop=True
    elif k in ("up","w"):
        app.tetr.try_rotate(1)
    elif k=="z":
        app.tetr.try_rotate(-1)
    elif k=="x":
        app.tetr.try_rotate(2)
    elif k=="c":
        do_hold(app)
    elif k in ("space"," "):
        while not app.tetr.board.collides(app.tetr.current,0,1):
            app.tetr.current.y+=1
        attack,cleared,tspin,is_pc,is_opener,difficult = app.tetr.lock()
        handle_piece_lock(app,attack,cleared,tspin,is_pc,is_opener,difficult)
        app.tetr.spawn()
        app.tetr.lock_delay=0

def onKeyRelease(app,key):
    k = _norm_key(key)
    if k in ("left","a"): app.tetr.das_left=0
    if k in ("right","d"): app.tetr.das_right=0
    if k in ("down","s"): app.tetr.soft_drop=False

def onKeyHold(app,keys):
    normed = set(_norm_key(k) for k in keys)
    if app.game_state!="playing": return
    if "left" in normed or "a" in normed:
        if app.tetr.das_left==0:
            app.tetr.try_move(-1,0)
            app.tetr.das_left=1
    if "right" in normed or "d" in normed:
        if app.tetr.das_right==0:
            app.tetr.try_move(1,0)
            app.tetr.das_right=1
    if "down" in normed or "s" in normed:
        app.tetr.soft_drop=True

def do_hold(app):
    if not app.switchHold.checked: return
    if not app.tetr.board.can_hold: return
    if app.tetr.hold_piece is None:
        app.tetr.hold_piece=app.tetr.current.kind; app.tetr.spawn()
    else:
        cur=app.tetr.current.kind; app.tetr.current=Piece(app.tetr.hold_piece); app.tetr.hold_piece=cur
    app.tetr.board.can_hold=False
