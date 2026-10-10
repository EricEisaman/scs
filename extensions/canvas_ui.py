
"""
extensions/canvas_ui.py — V3 — Rounded rect sandbox integrated + dark TETR.IO theme
Your sandbox:
    drawRoundedRect(x,y,w,h,r,fill) using rects + 4 circles — avoids SCS roundness bugs

Now _drawRect uses that when roundness>0, else plain rect.
Also includes _drawRoundedRectBorder for frames.

Uses only required components in V8: Breadcrumb, TabGroup, Input, Avatar, Button, Badge, Dialog
But keeps all 20 for compatibility.
"""

class WaTheme:
    colors = {
        "brand":   {"50":"#eef2ff","100":"#e0e7ff","500":"#615fff","600":"#4f39f6","700":"#432dd7"},
        "neutral": {"50":"#f8fafc","100":"#f1f5f9","200":"#e2e8f0","300":"#cbd5e1","400":"#90a1b9","500":"#62748e","700":"#364153","800":"#1e293b","900":"#101828"},
        "success": {"50":"#f0fdf4","500":"#00c950","600":"#16a34a"},
        "warning": {"50":"#fefce8","500":"#fdc700","600":"#d97706"},
        "danger":  {"50":"#fef2f2","500":"#fb2c36","600":"#dc2626"},
        "dark": {"card":"#1f2333","card2":"#2a2e42","border":"#353a50","input":"#232738","text":"#e2e8f0","subtext":"#94a3b8"},
        "tetrio": {"frame":"#c9a87c","frameDark":"#2d231c","bg":"#121317"}
    }
    radius = {"small":6, "medium":10, "large":16, "pill":999}
    @staticmethod
    def variant_fill(v): return WaTheme.colors.get(v, WaTheme.colors["brand"])["500"]
    @staticmethod
    def variant_soft(v): return WaTheme.colors.get(v, WaTheme.colors["brand"])["50"]
    @staticmethod
    def dark_soft(v):
        mapd={"brand":"#252a40","success":"#1e2f25","warning":"#2f2a1e","danger":"#2f1e25","neutral":"#252a3a"}
        return mapd.get(v,"#252a40")

class WaComponent:
    def __init__(self, x, y, w, h, variant="neutral", size="medium", disabled=False):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.variant = variant
        self.size = size
        self.disabled = disabled
        self.hovered=False; self.pressed=False; self.focused=False
    def contains(self,mx,my): return self.x <= mx <= self.x+self.w and self.y <= my <= self.y+self.h
    def handleMove(self,mx,my): self.hovered=self.contains(mx,my)

def _drawRoundedRectImpl(x, y, w, h, r, fill, opacity=100):
    try:
        from scs import drawRect, drawCircle
        r = max(0, min(r, w/2, h/2))
        if r == 0:
            drawRect(x, y, w, h, fill=fill, opacity=opacity)
            return
        if w > 2*r:
            drawRect(x+r, y, w-2*r, h, fill=fill, opacity=opacity)
        if h > 2*r:
            drawRect(x, y+r, w, h-2*r, fill=fill, opacity=opacity)
        for cx in (x+r, x+w-r):
            for cy in (y+r, y+h-r):
                drawCircle(cx, cy, r, fill=fill, opacity=opacity)
    except: pass

def _drawRect(x,y,w,h,fill=None,border=None,borderWidth=1,roundness=0,opacity=100):
    try:
        from scs import drawRect, drawCircle
        # Your rounded rect sandbox for all cases
        if roundness and roundness>0:
            r = max(0, min(roundness, w/2, h/2))
            if border and borderWidth>0:
                # outer with border color
                if w > 2*r:
                    drawRect(x+r, y, w-2*r, h, fill=border, opacity=opacity)
                if h > 2*r:
                    drawRect(x, y+r, w, h-2*r, fill=border, opacity=opacity)
                for cx in (x+r, x+w-r):
                    for cy in (y+r, y+h-r):
                        drawCircle(cx, cy, r, fill=border, opacity=opacity)
                # inner with fill
                if fill is not None:
                    ir = max(0, r-borderWidth)
                    ix = x+borderWidth; iy = y+borderWidth; iw = w-2*borderWidth; ih = h-2*borderWidth
                    if iw>0 and ih>0:
                        if iw > 2*ir:
                            drawRect(ix+ir, iy, iw-2*ir, ih, fill=fill, opacity=opacity)
                        if ih > 2*ir:
                            drawRect(ix, iy+ir, iw, ih-2*ir, fill=fill, opacity=opacity)
                        for cx in (ix+ir, ix+iw-ir):
                            for cy in (iy+ir, iy+ih-ir):
                                drawCircle(cx, cy, ir, fill=fill, opacity=opacity)
            else:
                # fill only rounded
                _drawRoundedRectImpl(x,y,w,h,roundness,fill,opacity)
            return
        # sharp rect
        drawRect(x,y,w,h,fill=fill,border=border,borderWidth=borderWidth,roundness=roundness,opacity=opacity)
    except: pass

def _drawLabel(text,x,y,size=14,fill="black",bold=False,align="center"):
    try:
        from scs import drawLabel
        drawLabel(text,x,y,size=size,fill=fill,bold=bold,align=align)
    except: pass
def _drawCircle(x,y,r,fill=None,border=None,opacity=100):
    try:
        from scs import drawCircle
        drawCircle(x,y,r,fill=fill,border=border,opacity=opacity)
    except: pass
def _drawLine(x1,y1,x2,y2,fill="black",lineWidth=1):
    try:
        from scs import drawLine
        drawLine(x1,y1,x2,y2,fill=fill,lineWidth=lineWidth)
    except: pass

class WaButton(WaComponent):
    def __init__(self,label,x,y,w=140,h=40,variant="brand",appearance="filled",pill=False,onClick=None):
        super().__init__(x,y,w,h,variant)
        self.label=label; self.appearance=appearance; self.pill=pill; self.onClick=onClick; self.loading=False
    def draw(self):
        fill=WaTheme.variant_fill(self.variant)
        border=fill
        if self.appearance=="outlined":
            fill=WaTheme.colors["dark"]["card"]; border=WaTheme.variant_fill(self.variant)
        if self.disabled:
            fill=WaTheme.colors["dark"]["card"]; border=WaTheme.colors["dark"]["border"]
        opacity=90 if self.pressed else 100
        r=WaTheme.radius["pill"] if self.pill else WaTheme.radius["medium"]
        _drawRect(self.x+1,self.y+2,self.w,self.h,fill="black",roundness=r,opacity=12)
        _drawRect(self.x,self.y,self.w,self.h,fill=fill,border=border,borderWidth=1.5,roundness=r,opacity=opacity)
        txt="white" if self.appearance=="filled" else WaTheme.variant_fill(self.variant)
        if self.disabled: txt=WaTheme.colors["neutral"]["400"]
        _drawLabel(self.label,self.x+self.w/2,self.y+self.h/2+1,size=13,fill=txt,bold=True)
    def handlePress(self,mx,my):
        if self.disabled: return False
        if self.contains(mx,my):
            self.pressed=True
            if self.onClick: self.onClick()
            return True
        return False
    def handleRelease(self,mx,my): self.pressed=False

class WaCard(WaComponent):
    def __init__(self,x,y,w,h,header="",footer="",variant="neutral"):
        super().__init__(x,y,w,h,variant)
        self.header=header; self.footer=footer
    def draw(self,body_draw_fn=None):
        _drawRect(self.x+2,self.y+3,self.w,self.h,fill="black",roundness=16,opacity=15)
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.colors["dark"]["card"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=16)
        if self.header:
            _drawRect(self.x,self.y,self.w,38,fill=WaTheme.colors["dark"]["card2"],roundness=16)
            _drawRect(self.x,self.y+19,self.w,19,fill=WaTheme.colors["dark"]["card2"])
            _drawLabel(self.header,self.x+14,self.y+19,size=12,fill=WaTheme.colors["dark"]["text"],bold=True,align="left-top")
        if self.footer:
            _drawLabel(self.footer,self.x+12,self.y+self.h-14,size=10,fill=WaTheme.colors["dark"]["subtext"],align="left-top")
        if body_draw_fn: body_draw_fn(self.x+12,self.y+(48 if self.header else 12))

class WaInput(WaComponent):
    def __init__(self,x,y,w=220,h=36,placeholder="Enter...",label="",value="",variant="neutral"):
        super().__init__(x,y,w,h,variant)
        self.placeholder=placeholder; self.label=label; self.value=value; self.hint=""
    def draw(self):
        if self.label:
            _drawLabel(self.label,self.x,self.y-8,size=11,fill=WaTheme.colors["dark"]["subtext"],bold=True,align="left-top")
        fill=WaTheme.colors["dark"]["input"]
        border=WaTheme.colors["dark"]["border"]
        if self.focused: border=WaTheme.variant_fill("brand")
        _drawRect(self.x,self.y,self.w,self.h,fill=fill,border=border,borderWidth=1.2 if self.focused else 1,roundness=10)
        txt=self.value if self.value else self.placeholder
        col=WaTheme.colors["dark"]["text"] if self.value else WaTheme.colors["dark"]["subtext"]
        _drawLabel(txt,self.x+10,self.y+self.h/2+1,size=12,fill=col,align="left-top")

class WaDialog(WaComponent):
    def __init__(self,title,message="",w=400,h=200,variant="neutral"):
        super().__init__(0,0,w,h,variant)
        self.title=title; self.message=message; self.open=False; self.buttons=[]
    def show(self): self.open=True
    def hide(self): self.open=False
    def draw(self,screen_w,screen_h):
        if not self.open: return
        try:
            from scs import drawRect
            drawRect(0,0,screen_w,screen_h,fill="black",opacity=55)
        except: pass
        cx=screen_w/2-self.w/2; cy=screen_h/2-self.h/2
        self.x=cx; self.y=cy
        _drawRect(cx+3,cy+4,self.w,self.h,fill="black",roundness=18,opacity=25)
        _drawRect(cx,cy,self.w,self.h,fill=WaTheme.colors["dark"]["card2"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=18)
        _drawLabel(self.title,cx+20,cy+24,size=14,fill=WaTheme.colors["dark"]["text"],bold=True,align="left-top")
        _drawLabel(self.message,cx+20,cy+48,size=11,fill=WaTheme.colors["dark"]["subtext"],align="left-top")

class WaBadge(WaComponent):
    def __init__(self,text,x,y,variant="neutral"):
        super().__init__(x,y,len(text)*7+16,22,variant)
        self.text=text
    def draw(self):
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.dark_soft(self.variant),border=WaTheme.variant_fill(self.variant),borderWidth=1,roundness=7)
        _drawLabel(self.text,self.x+self.w/2,self.y+self.h/2+1,size=10,fill=WaTheme.variant_fill(self.variant),bold=True)

class WaCallout(WaComponent):
    def __init__(self,x,y,w=240,message="",variant="brand",title=""):
        super().__init__(x,y,w,60,variant)
        self.message=message; self.title=title
    def draw(self):
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.dark_soft(self.variant),border=WaTheme.variant_fill(self.variant),borderWidth=1,roundness=10)
        if self.title:
            _drawLabel(self.title,self.x+10,self.y+12,size=11,fill=WaTheme.variant_fill(self.variant),bold=True,align="left-top")
            _drawLabel(self.message,self.x+10,self.y+28,size=10,fill=WaTheme.colors["dark"]["subtext"],align="left-top")
        else:
            _drawLabel(self.message,self.x+10,self.y+18,size=10,fill=WaTheme.colors["dark"]["text"],align="left-top")

class WaCheckbox(WaComponent):
    def __init__(self,x,y,label="",checked=False,variant="brand"):
        super().__init__(x,y,20,20,variant)
        self.label=label; self.checked=checked
    def draw(self):
        _drawRect(self.x,self.y,18,18,fill=WaTheme.colors["dark"]["card"] if not self.checked else WaTheme.variant_fill(self.variant),border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=6)
        if self.checked:
            _drawLabel("✓",self.x+9,self.y+9,size=11,fill="white",bold=True)
        if self.label:
            _drawLabel(self.label,self.x+26,self.y+9,size=11,fill=WaTheme.colors["dark"]["text"],align="left-top")
    def toggle(self,mx,my):
        if self.x-2 <= mx <= self.x+self.w+len(self.label)*6+30 and self.y-2 <= my <= self.y+self.h+4:
            self.checked=not self.checked; return True
        return False

class WaSelect(WaComponent):
    def __init__(self,x,y,w=180,options=None,value=None,label="",variant="neutral"):
        super().__init__(x,y,w,32,variant)
        self.options=options or []; self.value=value or (self.options[0] if self.options else ""); self.label=label; self.expanded=False
    def draw(self):
        if self.label:
            _drawLabel(self.label,self.x,self.y-8,size=11,fill=WaTheme.colors["dark"]["subtext"],bold=True,align="left-top")
        _drawRect(self.x,self.y,self.w,32,fill=WaTheme.colors["dark"]["input"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=10)
        _drawLabel(self.value+" ▾",self.x+10,self.y+16,size=12,fill=WaTheme.colors["dark"]["text"],align="left-top")
    def drawOverlay(self):
        if not self.expanded: return
        h=len(self.options)*30+8
        _drawRect(self.x+2,self.y+36,self.w,h,fill="black",roundness=12,opacity=25)
        _drawRect(self.x,self.y+34,self.w,h,fill=WaTheme.colors["dark"]["card2"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=12)
        for i,opt in enumerate(self.options):
            y=self.y+38+i*30
            _drawLabel(opt,self.x+12,y+10,size=11,fill=WaTheme.colors["dark"]["text"],align="left-top")
    def handlePress(self,mx,my):
        if self.contains(mx,my):
            self.expanded=not self.expanded; return True
        if self.expanded:
            for i in range(len(self.options)):
                y=self.y+38+i*30
                if self.x <= mx <= self.x+self.w and y <= my <= y+26:
                    self.value=self.options[i]; self.expanded=False; return True
        self.expanded=False; return False

class WaTextarea(WaComponent):
    def __init__(self,x,y,w=240,h=80,placeholder="",value="",label=""):
        super().__init__(x,y,w,h)
        self.placeholder=placeholder; self.value=value; self.label=label
    def draw(self):
        if self.label:
            _drawLabel(self.label,self.x,self.y-8,size=11,fill=WaTheme.colors["dark"]["subtext"],bold=True,align="left-top")
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.colors["dark"]["input"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=10)
        txt=self.value if self.value else self.placeholder
        _drawLabel(txt,self.x+10,self.y+14,size=11,fill=WaTheme.colors["dark"]["text"],align="left-top")

class WaProgressBar(WaComponent):
    def __init__(self,x,y,w=200,h=8,value=0.5,variant="brand"):
        super().__init__(x,y,w,h,variant)
        self.value=value
    def draw(self):
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.colors["dark"]["border"],roundness=6)
        _drawRect(self.x,self.y,self.w*self.value,self.h,fill=WaTheme.variant_fill(self.variant),roundness=6)

class WaSpinner(WaComponent):
    def __init__(self,x,y,size=24,variant="brand"):
        super().__init__(x,y,size,size,variant)
        self.angle=0
    def draw(self):
        _drawCircle(self.x+self.w/2,self.y+self.h/2,self.w/2,fill=None,border=WaTheme.colors["dark"]["border"])
        import math
        ax=self.x+self.w/2+math.cos(math.radians(self.angle))*self.w/2
        ay=self.y+self.h/2+math.sin(math.radians(self.angle))*self.h/2
        _drawCircle(ax,ay,4,fill=WaTheme.variant_fill(self.variant))

class WaTooltip(WaComponent):
    def __init__(self,text,x,y,w=200,variant="neutral"):
        super().__init__(x,y,w,30,variant)
        self.text=text; self.visible=False
    def draw(self):
        if not self.visible: return
        _drawRect(self.x,self.y,self.w,28,fill=WaTheme.colors["dark"]["card2"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=8)
        _drawLabel(self.text,self.x+self.w/2,self.y+14,size=10,fill=WaTheme.colors["dark"]["subtext"])

class WaTabGroup(WaComponent):
    def __init__(self,x,y,w=300,tabs=None):
        super().__init__(x,y,w,32)
        self.tabs=tabs or ["Tab1","Tab2"]; self.active=0
    def draw(self):
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.colors["dark"]["card"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=10)
        tw=self.w/len(self.tabs)
        for i,t in enumerate(self.tabs):
            is_active=i==self.active
            if is_active:
                _drawRect(self.x+i*tw+2,self.y+2,tw-4,self.h-4,fill=WaTheme.colors["dark"]["card2"],roundness=8)
            _drawLabel(t,self.x+i*tw+tw/2,self.y+self.h/2+1,size=11,fill=WaTheme.colors["dark"]["text"] if is_active else WaTheme.colors["dark"]["subtext"],bold=is_active)
    def handlePress(self,mx,my):
        if not self.contains(mx,my): return False
        tw=self.w/len(self.tabs)
        idx=int((mx-self.x)//tw)
        if 0<=idx<len(self.tabs):
            self.active=idx; return True
        return False

class WaDropdownItem:
    def __init__(self,label,variant="neutral"):
        self.label=label; self.variant=variant

class WaDropdown(WaComponent):
    def __init__(self,x,y,w=120,items=None,label="Menu",variant="neutral"):
        super().__init__(x,y,w,32,variant)
        self.items=items or []; self.label=label; self.open=False
    def draw(self):
        _drawRect(self.x,self.y,self.w,32,fill=WaTheme.colors["dark"]["card"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=10)
        _drawLabel(self.label+" ▾",self.x+self.w/2,self.y+16,size=11,fill=WaTheme.colors["dark"]["text"],bold=True)
    def drawOverlay(self):
        if not self.open: return
        h=len(self.items)*30+8
        _drawRect(self.x+2,self.y+36,self.w,h,fill="black",roundness=12,opacity=25)
        _drawRect(self.x,self.y+34,self.w,h,fill=WaTheme.colors["dark"]["card2"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=12)
        for i,it in enumerate(self.items):
            y=self.y+38+i*30
            col=WaTheme.variant_fill(it.variant) if it.variant!="neutral" else WaTheme.colors["dark"]["text"]
            _drawLabel(it.label,self.x+12,y+10,size=11,fill=col,align="left-top")
    def handlePress(self,mx,my):
        if self.contains(mx,my):
            self.open=not self.open; return True
        if self.open:
            for i in range(len(self.items)):
                y=self.y+38+i*30
                if self.x <= mx <= self.x+self.w and y <= my <= y+26:
                    self.open=False; return self.items[i].label
        self.open=False; return False

class WaAvatar(WaComponent):
    def __init__(self,x,y,size=40,initials="P1",variant="brand",image=None):
        super().__init__(x,y,size,size,variant)
        self.initials=initials; self.image=image
    def draw(self):
        _drawCircle(self.x+self.w/2,self.y+self.h/2,self.w/2,fill=WaTheme.colors["dark"]["card2"],border=WaTheme.colors["dark"]["border"])
        _drawLabel(self.initials,self.x+self.w/2,self.y+self.h/2+1,size=int(self.w*0.35),fill=WaTheme.variant_fill(self.variant),bold=True)

class WaTag(WaComponent):
    def __init__(self,label,x,y,variant="neutral",removable=True):
        super().__init__(x,y,len(label)*8+28,22,variant)
        self.label=label; self.removable=removable; self.removed=False
    def draw(self):
        if self.removed: return
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.dark_soft(self.variant),border=WaTheme.variant_fill(self.variant),borderWidth=1,roundness=7)
        _drawLabel(self.label,self.x+8,self.y+self.h/2+1,size=10,fill=WaTheme.variant_fill(self.variant),bold=True,align="left-top")
        if self.removable: _drawLabel("×",self.x+self.w-10,self.y+self.h/2+1,size=11,fill=WaTheme.variant_fill(self.variant),bold=True)
    def handlePress(self,mx,my):
        if self.removed: return False
        if self.x+self.w-16 <= mx <= self.x+self.w and self.y <= my <= self.y+self.h:
            self.removed=True; return True
        return False

class WaSwitch(WaComponent):
    def __init__(self,x,y,checked=False,label="",variant="brand"):
        super().__init__(x,y,40,22,variant)
        self.checked=checked; self.label=label
    def draw(self):
        fill=WaTheme.variant_fill(self.variant) if self.checked else WaTheme.colors["dark"]["border"]
        _drawRect(self.x,self.y,self.w,self.h,fill=fill,roundness=999)
        thumb_x=self.x+(self.w-18) if self.checked else self.x+2
        _drawCircle(thumb_x+9,self.y+11,8,fill="white",border=WaTheme.colors["dark"]["border"])
        if self.label:
            _drawLabel(self.label,self.x+self.w+8,self.y+11,size=11,fill=WaTheme.colors["dark"]["text"],align="left-top")
    def handlePress(self,mx,my):
        if self.x-4 <= mx <= self.x+self.w+len(self.label)*6+20 and self.y-4 <= my <= self.y+self.h+4:
            self.checked=not self.checked; return True
        return False

class WaSlider(WaComponent):
    def __init__(self,x,y,w=180,min=0,max=100,value=50,label="",variant="brand"):
        super().__init__(x,y,w,20,variant)
        self.min=min; self.max=max; self.value=value; self.label=label; self.dragging=False
    def draw(self):
        if self.label:
            _drawLabel(f"{self.label}: {int(self.value)}",self.x,self.y-6,size=10,fill=WaTheme.colors["dark"]["subtext"],bold=True,align="left-top")
        _drawRect(self.x,self.y+8,self.w,4,fill=WaTheme.colors["dark"]["border"],roundness=4)
        pct=(self.value-self.min)/(self.max-self.min) if self.max!=self.min else 0
        _drawRect(self.x,self.y+8,self.w*pct,4,fill=WaTheme.variant_fill(self.variant),roundness=4)
        _drawCircle(self.x+self.w*pct,self.y+10,7,fill="white",border=WaTheme.variant_fill(self.variant))
    def handlePress(self,mx,my):
        if self.y <= my <= self.y+20 and self.x-6 <= mx <= self.x+self.w+6:
            self.dragging=True; self._updateFromX(mx); return True
        return False
    def handleDrag(self,mx,my):
        if self.dragging: self._updateFromX(mx); return True
        return False
    def handleRelease(self,mx,my): self.dragging=False
    def _updateFromX(self,mx):
        pct=max(0,min(1,(mx-self.x)/self.w)); self.value=self.min+pct*(self.max-self.min)

class WaBreadcrumb(WaComponent):
    def __init__(self,x,y,items=None):
        super().__init__(x,y,300,20,"neutral")
        self.items=items or ["Home","Arcade","TETR.IO"]
    def draw(self):
        x=self.x
        for i,it in enumerate(self.items):
            is_last=i==len(self.items)-1
            col=WaTheme.colors["dark"]["text"] if is_last else WaTheme.colors["dark"]["subtext"]
            _drawLabel(it,x,self.y+6,size=11,fill=col,bold=is_last,align="left-top")
            x+=len(it)*6+8
            if not is_last:
                _drawLabel("/",x,self.y+6,size=11,fill=WaTheme.colors["dark"]["border"],align="left-top")
                x+=10

class WaDivider(WaComponent):
    def __init__(self,x,y,w=240,vertical=False,label=""):
        super().__init__(x,y,w,1 if not vertical else 100)
        self.vertical=vertical; self.label=label
    def draw(self):
        if self.vertical:
            _drawRect(self.x,self.y,1,self.h,fill=WaTheme.colors["dark"]["border"])
        else:
            _drawRect(self.x,self.y+self.h/2,self.w,1,fill=WaTheme.colors["dark"]["border"])
            if self.label:
                _drawRect(self.x+self.w/2-24,self.y,48,14,fill=WaTheme.colors["dark"]["card"])
                _drawLabel(self.label,self.x+self.w/2,self.y+7,size=9,fill=WaTheme.colors["dark"]["subtext"])

__all__=["WaTheme","WaComponent","WaButton","WaCard","WaInput","WaDialog","WaBadge","WaCallout","WaCheckbox","WaSelect","WaTextarea","WaProgressBar","WaSpinner","WaTooltip","WaTabGroup","WaDropdown","WaDropdownItem","WaAvatar","WaTag","WaSwitch","WaSlider","WaBreadcrumb","WaDivider"]
