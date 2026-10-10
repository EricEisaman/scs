"""
V11 — Fixes for screenshot cant-move-left-by-yellow
1. A key left movement blocked by input focus — now blur input on play, ignore keys if input focused
2. Rounded corners everywhere — canvas_ui border now uses double rounded rect, not SCS roundness param
3. HOLD border under board — fixed flush positions, draw order HOLD/NEXT after board shadow but before board inner? Actually now HOLD/NEXT flush with 8px gap, no overlap
4. SOLO box overflow — increased box height, wrapped text, clipped
"""

from scs import *
from browser import window, aio
import math, random, json as py_json, time

try:
    from extensions.canvas_ui import WaBreadcrumb, WaTabGroup, WaInput, WaAvatar, WaButton, WaBadge, WaDialog
except:
    from canvas_ui import WaBreadcrumb, WaTabGroup, WaInput, WaAvatar, WaButton, WaBadge, WaDialog

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

def drawRoundedRect(x, y, width, height, radius, fill, border=None, borderWidth=1, opacity=100):
    r = max(0, min(radius, width/2, height/2))
    if r == 0:
        drawRect(x, y, width, height, fill=fill, border=border, borderWidth=borderWidth, opacity=opacity)
        return
    # If border, draw outer with border color then inner with fill
    if border and borderWidth>0:
        # outer
        if width > 2*r:
            drawRect(x+r, y, width-2*r, height, fill=border, opacity=opacity)
        if height > 2*r:
            drawRect(x, y+r, width, height-2*r, fill=border, opacity=opacity)
        for cx in (x+r, x+width-r):
            for cy in (y+r, y+height-r):
                drawCircle(cx, cy, r, fill=border, opacity=opacity)
        # inner
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
    # no border — just fill
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
PREVIEW_CELL = 14
TETROMINOES = {'I':[[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],'J':[[1,0,0],[1,1,1],[0,0,0]],'L':[[0,0,1],[1,1,1],[0,0,0]],'O':[[1,1],[1,1]],'S':[[0,1,1],[1,1,0],[0,0,0]],'T':[[0,1,0],[1,1,1],[0,0,0]],'Z':[[1,1,0],[0,1,1],[0,0,0]]}
COLORS = {'I':rgb(0,212,212),'J':rgb(0,75,212),'L':rgb(212,127,0),'O':rgb(212,212,0),'S':rgb(0,212,0),'T':rgb(138,0,212),'Z':rgb(212,0,0),'G':rgb(80,80,80)}
KICKS_JLSTZ={(0,1):[(0,0),(-1,0),(-1,1),(0,-2),(-1,-2)],(1,0):[(0,0),(1,0),(1,-1),(0,2),(1,2)],(1,2):[(0,0),(1,0),(1,-1),(0,2),(1,2)],(2,1):[(0,0),(-1,0),(-1,1),(0,-2),(-1,-2)],(2,3):[(0,0),(1,0),(1,1),(0,-2),(1,-2)],(3,2):[(0,0),(-1,0),(-1,-1),(0,2),(-1,2)],(3,0):[(0,0),(-1,0),(-1,-1),(0,2),(-1,2)],(0,3):[(0,0),(1,0),(1,1),(0,-2),(1,-2)]}
KICKS_I={(0,1):[(0,0),(-2,0),(1,0),(-2,-1),(1,2)],(1,0):[(0,0),(2,0),(-1,0),(2,1),(-1,-2)],(1,2):[(0,0),(-1,0),(2,0),(-1,2),(2,-1)],(2,1):[(0,0),(1,0),(-2,0),(1,-2),(-2,1)],(2,3):[(0,0),(2,0),(-1,0),(2,1),(-1,-2)],(3,2):[(0,0),(-2,0),(1,0),(-2,-1),(1,2)],(3,0):[(0,0),(1,0),(-2,0),(1,-2),(-2,1)],(0,3):[(0,0),(-1,0),(2,0),(-1,2),(2,-1)]}
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
        if topped and not app.tetr.board.zen: app.tetr.game_over=True

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

    # FLUSH layout — no overlap
    BOARD_X=420; BOARD_Y=95
    HOLD_W=100; NEXT_W=120
    HOLD_X=BOARD_X - HOLD_W - 16  # 304, flush with 8px gap
    NEXT_X=BOARD_X + BOARD_W*CELL + 12  # 712, flush
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
    app.badgeOPP=WaBadge("SOLO",66,118,variant="neutral")
    app.btnFind=WaButton("FIND OPPONENT (1v1 BGS)",20,156,w=200,h=36,variant="brand",onClick=lambda: start_search(app))
    app.btnCancel=WaButton("CANCEL",20,156,w=200,h=36,variant="neutral",appearance="outlined",onClick=lambda: cancel_search(app))
    app.btnReset=WaButton("RESET (R)",20,156,w=200,h=36,variant="brand",onClick=lambda: reset_game(app))
    app.btnBack=WaButton("BACK TO HOME",20,600,w=200,h=32,variant="neutral",appearance="outlined",onClick=lambda: go_title(app))
    app.badgeTR=WaBadge("TR 12500",20,204,variant="brand")
    app.badgeAPM=WaBadge("APM 0",100,204,variant="success")
    app.badgePPS=WaBadge("PPS 0",170,204,variant="warning")

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
                cid=res.get("client_id") if isinstance(res,dict) else None
                if not cid:
                    try:
                        import json as _j
                        d=_j.loads(window.JSON.stringify(res)) if hasattr(window,'JSON') else {}
                        cid=d.get("client_id")
                    except: cid=getattr(res,"client_id",None)
                app.client_id=cid
            except Exception as e: print(f"Join failed {e}")
        aio.run(join_mp())

    app.dialogGameOver=WaDialog("Match Finished","You topped out.",w=380,h=160,variant="danger")
    app.dialogGameOver.buttons=[WaButton("RETRY (R)",0,0,w=110,h=36,variant="brand",onClick=lambda: reset_game(app)), WaButton("MENU",0,0,w=80,h=36,variant="neutral",appearance="outlined",onClick=lambda: go_title(app))]
    app.das=10; app.arr=2; app.sdf=6

def go_title(app):
    app.game_state="title"
    app.dialogGameOver.hide()
    app.single_opponent_id=None
    app.mp_wrapper.match["queue"]["status"]="idle"
    app.badgeOPP.text="HOME"
    app.inputName.focused=False

def start_search(app):
    tab=app.tabGroup.tabs[app.tabGroup.active]
    if "ZEN" in tab: mode="zen"; env="tetr_zen"
    elif "40" in tab: mode="40lines"; env="tetr_40l"
    elif "BLITZ" in tab: mode="blitz"; env="tetr_blitz"
    elif "Quick" in tab: mode="quick_play"; env="tetr_1v1_quick"
    else: mode="tetra_league"; env="tetr_1v1"
    app.room_id=env; app.tetr=TetrGame(mode=mode)
    app.inputName.focused=False
    if mode in ("zen","40lines","blitz"):
        app.game_state="playing"; app.single_opponent_id=None; app.badgeOPP.text=f"SOLO {mode.upper()}"
    else:
        app.mp_wrapper.findOpponent(); app.game_state="searching"; app.single_opponent_id=None; app.badgeOPP.text="SEARCHING..."

def cancel_search(app): app.mp_wrapper.cancelSearch(); app.game_state="menu"; app.single_opponent_id=None; app.badgeOPP.text="NO OPP"; app.inputName.focused=False
def reset_game(app):
    cur=app.tetr.mode; app.tetr=TetrGame(mode=cur); app.mp_wrapper.match["garbage"]["incoming"]=[]; app.dialogGameOver.hide()
    app.game_state="playing"; app.inputName.focused=False

def onStep(app):
    if app.game_state=="title": return
    if HAS_MP:
        try:
            sig=get_signal("character-state-update")
            if sig and isinstance(sig,dict):
                for u in sig.get("updates",[]):
                    cid=u.get("clientId")
                    if not cid or cid==app.client_id: continue
                    if app.tetr.mode in ("zen","40lines","blitz"): continue
                    if app.single_opponent_id is None:
                        app.single_opponent_id=cid; app.mp_wrapper._secureOpponent({"id":cid}); app.badgeOPP.text=f"OPP {cid[:4]}"
                    if cid!=app.single_opponent_id: continue
                    ts=u.get("timestamp",0)
                    if ts>app.remote_timestamps.get(cid,-1):
                        app.remote_timestamps[cid]=ts; app.remote_players[cid]=u
                        if "tetrBoard" in u: app.single_opponent_board=u.get("tetrBoard")
                        if "tetrAttack" in u:
                            atk=int(u.get("tetrAttack",0))
                            if atk>0:
                                hole=random.randint(0,BOARD_W-1)
                                app.mp_wrapper.match["garbage"]["incoming"].append({"lines":atk,"hole":hole})
            app.datastar_connected=is_datastar_connected()
        except: pass
    if app.game_state=="searching":
        app.mp_wrapper.search_timer+=1
        if app.single_opponent_id is not None: app.game_state="playing"; app.tetr=TetrGame(mode=app.tetr.mode); app.inputName.focused=False
        elif app.mp_wrapper.search_timer>180:
            opp={"id":f"bot_{random.randint(1000,9999)}","tr":12000,"bot_ai":{"timer":0}}
            if app.single_opponent_id is None and app.tetr.mode not in ("zen","40lines","blitz"):
                app.single_opponent_id=opp["id"]; app.mp_wrapper._secureOpponent(opp); app.game_state="playing"; app.tetr=TetrGame(mode=app.tetr.mode); app.badgeOPP.text=f"BOT {opp['id'][-4:]}"; app.inputName.focused=False
    if app.game_state!="playing": return
    if app.tetr.game_over: app.game_state="gameover"; app.dialogGameOver.show(); return
    if app.tetr.mode=="40lines" and app.tetr.stats["lines"]>=40:
        app.game_state="gameover"; app.dialogGameOver.title="40 LINES CLEAR!"; app.dialogGameOver.message=f"Time: {time.time()-app.tetr.stats['start']:.2f}s"; app.dialogGameOver.show(); return
    if app.tetr.mode=="blitz":
        elapsed=time.time()-app.tetr.stats["start"]
        if elapsed>=120: app.game_state="gameover"; app.dialogGameOver.title="BLITZ FINISH!"; app.dialogGameOver.message=f"Score: {app.tetr.stats['score']} lines {app.tetr.stats['lines']}"; app.dialogGameOver.show(); return
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
            if (app.tetr.das_left-app.das) % max(1,app.arr+1)==0: app.tetr.try_move(-1,0)
    if app.tetr.das_right>0:
        app.tetr.das_right+=1
        if app.tetr.das_right>app.das:
            if (app.tetr.das_right-app.das) % max(1,app.arr+1)==0: app.tetr.try_move(1,0)
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
            if app.tetr.board.attack>0: app.tetr.board.attack=0

def redrawAll(app):
    if app.game_state=="title":
        drawTitleScreen(app)
        return
    drawRect(0,0,app.width,app.height,fill=rgb(18,19,23))
    app.breadcrumb.draw()
    app.tabGroup.draw()
    app.avatarLocal.draw()
    app.inputName.draw()
    app.avatarOpp.draw()
    app.badgeOPP.draw()
    if app.tetr.mode in ("zen","40lines","blitz") or app.tabGroup.tabs[app.tabGroup.active] in ("ZEN","40 LINES","BLITZ"):
        if app.game_state=="playing": app.btnReset.draw()
        elif app.game_state=="searching": app.btnCancel.draw()
        else: app.btnReset.draw()
    else:
        if app.game_state=="searching": app.btnCancel.draw()
        else: app.btnFind.draw()
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
    drawLabel(f"BGS | {app.room_id} | {app.tetr.mode.upper()}",app.width/2,app.height-10,size=8,fill=rgb(90,90,95))
    drawCircle(app.width-16,12,4,fill=rgb(100,255,100) if app.datastar_connected else rgb(255,180,80))

def drawTitleScreen(app):
    drawRect(0,0,app.width,app.height,fill=rgb(18,19,23))
    drawRoundedRect(0,app.height-80,app.width,80,0,rgb(0,0,0),opacity=60)
    drawRoundedRect(0,0,app.width,28,0,rgb(25,26,32))
    drawLabel("HOME",20,14,size=12,fill=rgb(200,200,210),bold=True,align="left-top")
    drawLabel("TETRISWIKI  ANONYMOUS",app.width-20,14,size=10,fill=rgb(220,80,80),bold=True,align="right-top")
    banner_y=52
    drawRoundedRect(120,banner_y,880,38,8,rgb(45,28,18),border=rgb(210,120,40),borderWidth=1,opacity=90)
    drawLabel("★",app.width/2,banner_y-8,size=20,fill=rgb(255,200,80),bold=True)
    drawLabel("DID YOU KNOW: TETR.IO IS DEVELOPED BY A SINGLE PERSON",app.width/2,banner_y+12,size=9,fill=rgb(220,180,160),bold=True)
    drawLabel("PLEASE CONSIDER SUPPORTING THEM!",app.width/2,banner_y+24,size=9,fill=rgb(200,160,140))
    for item in app.titleItems:
        x=120; y=item["y"]; w=880; h=58; r=10
        is_hover=getattr(app,"_hoverTitle",None)==item["id"]
        drawRoundedRect(x+2,y+3,w,h,r,rgb(0,0,0),opacity=18)
        drawRoundedRect(x,y,w,h,r,item["dark"],border=item["color"],borderWidth=1,opacity=100 if is_hover else 90)
        drawRoundedRect(x+6,y+6,78,h-12,8,item["color"],opacity=95)
        drawLabel(item["icon"],x+45,y+h/2+2,size=20,fill="black",bold=True)
        drawLabel(item["label"],x+100,y+18,size=16,fill=rgb(235,230,240),bold=True,align="left-top")
        drawLabel(item["sub"],x+100,y+36,size=9,fill=rgb(160,160,180),align="left-top")
    drawLabel("WELCOME TO TETR.IO!",14,app.height-12,size=10,fill=rgb(180,180,190),align="left-top")

def draw_tetrio_frame(app):
    ox=app.board_x; oy=app.board_y; bw=BOARD_W*CELL; bh=BOARD_H_VISIBLE*CELL
    frame=rgb(201,168,124)
    # shadow first, does not overlap HOLD/NEXT because HOLD/NEXT drawn after
    drawRoundedRect(ox-12,oy-10,bw+24+120+16+24,bh+20,12,rgb(0,0,0),opacity=15)
    # HOLD and NEXT flush — drawn BEFORE board so board border sits between with gap
    hx=app.HOLD_X; hy=oy
    drawRoundedRect(hx-6,hy-6,100+12,78+12,10,frame,border=frame,borderWidth=1)
    drawRoundedRect(hx,hy,100,78,8,rgb(0,0,0))
    drawLabel("HOLD",hx+50,hy+10,size=11,fill=frame,bold=True)
    nx=app.NEXT_X; ny=oy
    drawRoundedRect(nx-6,ny-6,120+12,340+12,10,frame,border=frame,borderWidth=1)
    drawRoundedRect(nx,ny,120,340,8,rgb(0,0,0))
    drawLabel("NEXT",nx+60,ny+12,size=11,fill=frame,bold=True)
    # board frame flush, with 8px gap from HOLD/NEXT — no overlap
    drawRoundedRect(ox-8,oy-8,bw+16,bh+16,10,frame,border=frame,borderWidth=1)
    drawRoundedRect(ox-4,oy-4,bw+8,bh+8,6,rgb(0,0,0))

def draw_board_tetrio(app,board,ox,oy,cell,cur_piece=None,ghost_y=None,show_ghost=True):
    try:
        for y in range(BOARD_H_VISIBLE+1): drawLine(ox,oy+y*cell,ox+BOARD_W*cell,oy+y*cell,fill=rgb(35,32,28),lineWidth=1)
        for x in range(BOARD_W+1): drawLine(ox+x*cell,oy,ox+x*cell,oy+BOARD_H_VISIBLE*cell,fill=rgb(35,32,28),lineWidth=1)
        start_r=BOARD_H_INTERNAL-BOARD_H_VISIBLE
        for r in range(BOARD_H_VISIBLE):
            gr=start_r+r
            for c in range(BOARD_W):
                k=board.grid[gr][c]
                if k:
                    col=COLORS.get(k,rgb(60,60,60))
                    drawRoundedRect(ox+c*cell+1,oy+r*cell+1,cell-2,cell-2,3,col)
        if cur_piece and show_ghost and ghost_y is not None:
            for r in range(len(cur_piece.shape)):
                for c in range(len(cur_piece.shape[0])):
                    if cur_piece.shape[r][c]:
                        x=cur_piece.x+c; y=ghost_y+r; vy=y-start_r
                        if 0<=vy<BOARD_H_VISIBLE and 0<=x<BOARD_W:
                            # ghost as border only
                            drawRoundedRect(ox+x*cell+1,oy+vy*cell+1,cell-2,cell-2,3,None,border=COLORS[cur_piece.kind],borderWidth=2,opacity=35)
        if cur_piece:
            for r in range(len(cur_piece.shape)):
                for c in range(len(cur_piece.shape[0])):
                    if cur_piece.shape[r][c]:
                        x=cur_piece.x+c; y=cur_piece.y+r; vy=y-start_r
                        if 0<=vy<BOARD_H_VISIBLE and 0<=x<BOARD_W:
                            drawRoundedRect(ox+x*cell+1,oy+vy*cell+1,cell-2,cell-2,3,COLORS[cur_piece.kind])
    except: pass

def draw_hold_tetrio(app):
    try:
        if not app.tetr.hold_piece: return
        hx=app.HOLD_X; hy=app.board_y
        shape=TETROMINOES[app.tetr.hold_piece]
        bx=hx+50 - (len(shape[0])*PREVIEW_CELL)//2; by=hy+28
        for r in range(len(shape)):
            for c in range(len(shape[0])):
                if shape[r][c]:
                    drawRoundedRect(bx+c*PREVIEW_CELL,by+r*PREVIEW_CELL,PREVIEW_CELL-1,PREVIEW_CELL-1,2,COLORS[app.tetr.hold_piece])
    except: pass

def draw_next_tetrio(app):
    try:
        nx=app.NEXT_X; ny=app.board_y
        for i,kind in enumerate(app.tetr.next_queue[:5]):
            shape=TETROMINOES[kind]
            base_y=ny+34+i*58; base_x=nx+24
            for r in range(len(shape)):
                for c in range(len(shape[0])):
                    if shape[r][c]: drawRoundedRect(base_x+c*PREVIEW_CELL,base_y+r*PREVIEW_CELL,PREVIEW_CELL-1,PREVIEW_CELL-1,2,COLORS[kind])
    except: pass

def draw_opponent_tetrio(app):
    try:
        ox=app.opp_board_x; oy=app.opp_board_y
        if app.tetr.mode in ("zen","40lines","blitz"):
            # FIXED: box height 240, no overflow, wrapped text
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
    except: pass

def draw_garbage_meter(app):
    try:
        ox=app.board_x; oy=app.board_y; bh=BOARD_H_VISIBLE*CELL
        drawRoundedRect(ox-12,oy,6,bh,3,rgb(40,35,25))
        inc=len(app.mp_wrapper.match["garbage"]["incoming"])
        if inc:
            h=min(bh,inc*18)
            drawRoundedRect(ox-12,oy+bh-h,6,h,3,rgb(220,200,80))
    except: pass

def onMousePress(app,mx,my):
    if app.game_state=="title":
        for item in app.titleItems:
            x=120; y=item["y"]; w=880; h=58
            if x<=mx<=x+w and y<=my<=y+h:
                if item["id"]=="multiplayer":
                    app.game_state="menu"; app.tabGroup.active=0; start_search(app); app.game_state="searching"
                elif item["id"]=="solo":
                    app.game_state="menu"; app.tabGroup.active=2; app.tetr=TetrGame(mode="zen"); app.game_state="playing"; app.badgeOPP.text="SOLO ZEN"; app.inputName.focused=False
                else:
                    app.game_state="menu"; app.tabGroup.active=2; app.tetr=TetrGame(mode="zen"); app.game_state="playing"; app.inputName.focused=False
                return True
        return False
    if app.dialogGameOver.open:
        for b in app.dialogGameOver.buttons:
            if b.contains(mx,my) and b.handlePress(mx,my): return True
    if app.tabGroup.handlePress(mx,my): start_search(app); return True
    if app.tetr.mode in ("zen","40lines","blitz") or app.tabGroup.tabs[app.tabGroup.active] in ("ZEN","40 LINES","BLITZ"):
        if app.btnReset.contains(mx,my) and app.btnReset.handlePress(mx,my): return True
        if app.btnCancel.contains(mx,my) and app.btnCancel.handlePress(mx,my): return True
    else:
        if app.btnFind.contains(mx,my) and app.btnFind.handlePress(mx,my): return True
        if app.btnCancel.contains(mx,my) and app.btnCancel.handlePress(mx,my): return True
    if app.btnBack.contains(mx,my) and app.btnBack.handlePress(mx,my): return True
    if app.inputName.contains(mx,my): app.inputName.focused=True; return True
    else: app.inputName.focused=False
    return False
def onMouseMove(app,mx,my):
    if app.game_state=="title":
        hover=None
        for item in app.titleItems:
            x=120; y=item["y"]; w=880; h=58
            if x<=mx<=x+w and y<=my<=y+h: hover=item["id"]
        app._hoverTitle=hover
        return False
    for comp in [app.btnFind, app.btnCancel, app.btnReset, app.btnBack, app.tabGroup, app.inputName]:
        if hasattr(comp,'handleMove'): comp.handleMove(mx,my)
    return False
def onMouseRelease(app,mx,my):
    for comp in [app.btnFind, app.btnCancel, app.btnReset, app.btnBack]:
        if hasattr(comp,'handleRelease'): comp.handleRelease(mx,my)
    return False
def onMouseDrag(app,mx,my): return onMouseMove(app,mx,my)
def _norm_key(k):
    if not k: return ""
    kl=str(k).lower()
    mapping={"arrowleft":"left","arrowright":"right","arrowup":"up","arrowdown":"down"," ":"space","spacebar":"space"}
    return mapping.get(kl,kl)
def onKeyPress(app,key):
    k=_norm_key(key)
    # FIX: if input focused, don't move
    if hasattr(app,'inputName') and app.inputName.focused:
        if k=="escape": app.inputName.focused=False
        return
    if app.game_state=="title":
        if k in ("enter"," "):
            app.game_state="menu"; app.tabGroup.active=2; app.tetr=TetrGame(mode="zen"); app.game_state="playing"; app.inputName.focused=False
        return
    if app.game_state!="playing":
        if k=="r": reset_game(app)
        if k=="escape": go_title(app)
        return
    if k in ("left","a"): app.tetr.try_move(-1,0)
    elif k in ("right","d"): app.tetr.try_move(1,0)
    elif k in ("down","s"): app.tetr.soft_drop=True
    elif k in ("up","w"): app.tetr.try_rotate(1)
    elif k=="z": app.tetr.try_rotate(-1)
    elif k=="x": app.tetr.try_rotate(2)
    elif k=="c": do_hold(app)
    elif k in ("space"," "):
        while not app.tetr.board.collides(app.tetr.current,0,1): app.tetr.current.y+=1
        attack,cleared,tspin,is_pc,is_opener,difficult=app.tetr.lock()
        handle_piece_lock(app,attack,cleared,tspin,is_pc,is_opener,difficult)
        app.tetr.spawn(); app.tetr.lock_delay=0
    elif k=="escape": go_title(app)
def onKeyRelease(app,key):
    k=_norm_key(key)
    if k in ("left","a"): app.tetr.das_left=0
    if k in ("right","d"): app.tetr.das_right=0
    if k in ("down","s"): app.tetr.soft_drop=False
def onKeyHold(app,keys):
    # ignore if input focused
    if hasattr(app,'inputName') and app.inputName.focused: return
    normed=set(_norm_key(k) for k in keys)
    if app.game_state!="playing": return
    if "left" in normed or "a" in normed:
        if app.tetr.das_left==0: app.tetr.try_move(-1,0); app.tetr.das_left=1
    if "right" in normed or "d" in normed:
        if app.tetr.das_right==0: app.tetr.try_move(1,0); app.tetr.das_right=1
    if "down" in normed or "s" in normed: app.tetr.soft_drop=True
def do_hold(app):
    if not app.tetr.board.can_hold: return
    if app.tetr.hold_piece is None: app.tetr.hold_piece=app.tetr.current.kind; app.tetr.spawn()
    else: cur=app.tetr.current.kind; app.tetr.current=Piece(app.tetr.hold_piece); app.tetr.hold_piece=cur
    app.tetr.board.can_hold=False
