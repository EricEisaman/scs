"""
extensions/canvas_ui.py — V2 Clean — 20 WebAwesome components for dark SCS canvas
Fixed: z-index layering, dark theme readability, dropdown overlay, spacing

WebAwesome principles retained:
- variant: brand / neutral / success / warning / danger
- appearance: filled / outlined / text
- size: small / medium / large
- radius, shadow, focus ring
- Slots: header/body/footer
- Accessible hit targets 32px+

Dark theme adaptation (TETR.IO style):
- Cards / inputs use #1f2333 / #2a2e42 fills
- Labels use #e2e8f0 light for readability on #0f1115 bg
- Borders #353a50

Top 20 WA components:
1 Button, 2 Card, 3 Input, 4 Dialog, 5 Badge, 6 Callout, 7 Checkbox, 8 Select, 9 Textarea, 10 ProgressBar, 11 Spinner, 12 Tooltip, 13 TabGroup, 14 Dropdown, 15 Avatar, 16 Tag, 17 Switch, 18 Slider, 19 Breadcrumb, 20 Divider

Usage: import and call draw() in redrawAll, handlePress in onMousePress.
For overlay components (Select, Dropdown) call drawOverlay() after board to avoid under-draw.
"""

class WaTheme:
    colors = {
        "brand":   {"50":"#eef2ff","100":"#e0e7ff","500":"#615fff","600":"#4f39f6","700":"#432dd7"},
        "neutral": {"50":"#f8fafc","100":"#f1f5f9","200":"#e2e8f0","300":"#cbd5e1","400":"#90a1b9","500":"#62748e","700":"#364153","800":"#1e293b","900":"#101828"},
        "success": {"50":"#f0fdf4","500":"#00c950","600":"#16a34a"},
        "warning": {"50":"#fefce8","500":"#fdc700","600":"#d97706"},
        "danger":  {"50":"#fef2f2","500":"#fb2c36","600":"#dc2626"},
        "dark": {"card":"#1f2333","card2":"#2a2e42","border":"#353a50","input":"#232738","text":"#e2e8f0","subtext":"#94a3b8"}
    }
    radius = {"small":6, "medium":10, "large":16, "pill":999}
    @staticmethod
    def variant_fill(v):
        return WaTheme.colors.get(v, WaTheme.colors["brand"])["500"]
    @staticmethod
    def variant_soft(v):
        return WaTheme.colors.get(v, WaTheme.colors["brand"])["50"]
    @staticmethod
    def dark_soft(v):
        mapd = {"brand":"#252a40","success":"#1e2f25","warning":"#2f2a1e","danger":"#2f1e25","neutral":"#252a3a"}
        return mapd.get(v,"#252a40")

class WaComponent:
    def __init__(self, x, y, w, h, variant="neutral", size="medium", disabled=False):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.variant = variant
        self.size = size
        self.disabled = disabled
        self.hovered=False; self.pressed=False; self.focused=False
    def contains(self,mx,my):
        return self.x <= mx <= self.x+self.w and self.y <= my <= self.y+self.h
    def handleMove(self,mx,my):
        self.hovered=self.contains(mx,my)

def _drawRect(x,y,w,h,fill=None,border=None,borderWidth=1,roundness=8,opacity=100):
    try:
        from scs import drawRect
        drawRect(x,y,w,h,fill=fill,border=border,borderWidth=borderWidth,roundness=roundness,opacity=opacity)
    except: pass
def _drawLabel(text,x,y,size=14,fill="black",bold=False,align="center"):
    try:
        from scs import drawLabel
        drawLabel(text,x,y,size=size,fill=fill,bold=bold,align=align)
    except: pass
def _drawCircle(x,y,r,fill=None,border=None):
    try:
        from scs import drawCircle
        drawCircle(x,y,r,fill=fill,border=border)
    except: pass

# WaButton
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

# WaCard
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

# WaInput
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

# WaDialog
class WaDialog(WaComponent):
    def __init__(self,title,message,x=0,y=0,w=400,h=200,variant="brand"):
        super().__init__(x,y,w,h,variant)
        self.title=title; self.message=message; self.open=False; self.buttons=[]
    def show(self): self.open=True
    def hide(self): self.open=False
    def draw(self,app_width=800,app_height=600):
        if not self.open: return
        _drawRect(0,0,app_width,app_height,fill="black",opacity=45)
        cx=app_width/2-self.w/2; cy=app_height/2-self.h/2
        _drawRect(cx+3,cy+4,self.w,self.h,fill="black",roundness=20,opacity=20)
        _drawRect(cx,cy,self.w,self.h,fill=WaTheme.colors["dark"]["card"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=18)
        _drawLabel(self.title,cx+20,cy+22,size=15,fill=WaTheme.colors["dark"]["text"],bold=True,align="left-top")
        _drawLabel(self.message,cx+20,cy+48,size=12,fill=WaTheme.colors["dark"]["subtext"],align="left-top")
        for b in self.buttons: b.draw()

# WaBadge
class WaBadge(WaComponent):
    def __init__(self,text,x,y,variant="brand",pill=True):
        super().__init__(x,y,24,20,variant)
        self.text=str(text); self.pill=pill; self.w=max(28,len(self.text)*7+16)
    def draw(self):
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.variant_fill(self.variant),roundness=WaTheme.radius["pill"])
        _drawLabel(self.text,self.x+self.w/2,self.y+self.h/2+1,size=10,fill="white",bold=True)

# WaCallout
class WaCallout(WaComponent):
    def __init__(self,x,y,w,message,variant="warning",title=""):
        super().__init__(x,y,w,48,variant)
        self.message=message; self.title=title; self.h=46+(18 if title else 0)
    def draw(self):
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.dark_soft(self.variant),border=WaTheme.variant_fill(self.variant),borderWidth=1.2,roundness=10)
        if self.title:
            _drawLabel(self.title,self.x+10,self.y+10,size=11,fill=WaTheme.variant_fill(self.variant),bold=True,align="left-top")
            _drawLabel(self.message,self.x+10,self.y+26,size=10,fill=WaTheme.colors["dark"]["subtext"],align="left-top")
        else:
            _drawLabel(self.message,self.x+10,self.y+self.h/2+1,size=10,fill=WaTheme.colors["dark"]["text"],align="left-top")

# WaCheckbox
class WaCheckbox(WaComponent):
    def __init__(self,x,y,label="",checked=False,variant="brand"):
        super().__init__(x,y,20,20,variant)
        self.label=label; self.checked=checked
    def draw(self):
        fill=WaTheme.variant_fill(self.variant) if self.checked else WaTheme.colors["dark"]["card"]
        border=WaTheme.variant_fill(self.variant) if self.checked else WaTheme.colors["dark"]["border"]
        _drawRect(self.x,self.y,18,18,fill=fill,border=border,borderWidth=1.5,roundness=5)
        if self.checked: _drawLabel("✓",self.x+9,self.y+9,size=11,fill="white",bold=True)
        if self.label: _drawLabel(self.label,self.x+26,self.y+10,size=11,fill=WaTheme.colors["dark"]["text"],align="left-top")
    def toggle(self,mx,my):
        if self.x-4 <= mx <= self.x+len(self.label)*6+30 and self.y-4 <= my <= self.y+20:
            self.checked=not self.checked; return True
        return False

# WaSelect with overlay
class WaSelect(WaComponent):
    def __init__(self,x,y,w=200,options=None,value=None,label=""):
        super().__init__(x,y,w,36,"neutral")
        self.options=options or ["Tetra League","Quick Play","40 Lines","Blitz"]
        self.value=value or self.options[0]; self.label=label; self.expanded=False
    def draw(self):
        if self.label:
            _drawLabel(self.label,self.x,self.y-8,size=10,fill=WaTheme.colors["dark"]["subtext"],bold=True,align="left-top")
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.colors["dark"]["input"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=10)
        _drawLabel(self.value,self.x+10,self.y+self.h/2+1,size=12,fill=WaTheme.colors["dark"]["text"],align="left-top")
        _drawLabel("▾",self.x+self.w-16,self.y+self.h/2+1,size=12,fill=WaTheme.colors["dark"]["subtext"])
    def drawOverlay(self):
        if not self.expanded: return
        h=len(self.options)*30+8
        _drawRect(self.x+2,self.y+self.h+6,self.w,h,fill="black",roundness=12,opacity=25)
        _drawRect(self.x,self.y+self.h+4,self.w,h,fill=WaTheme.colors["dark"]["card2"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=12)
        for i,opt in enumerate(self.options):
            is_sel=opt==self.value
            if is_sel:
                _drawRect(self.x+3,self.y+self.h+8+i*30,self.w-6,26,fill=WaTheme.colors["brand"]["500"],roundness=8,opacity=20)
            _drawLabel(opt,self.x+12,self.y+self.h+21+i*30,size=11,fill=WaTheme.colors["dark"]["text"] if not is_sel else "white",align="left-top",bold=is_sel)
    def handlePress(self,mx,my):
        if self.contains(mx,my):
            self.expanded=not self.expanded; return True
        if self.expanded:
            for i,opt in enumerate(self.options):
                ry=self.y+self.h+8+i*30
                if self.x <= mx <= self.x+self.w and ry <= my <= ry+26:
                    self.value=opt; self.expanded=False; return True
            self.expanded=False
            return False
        return False

# WaTextarea
class WaTextarea(WaComponent):
    def __init__(self,x,y,w=260,h=80,placeholder="...",value="",label=""):
        super().__init__(x,y,w,h)
        self.placeholder=placeholder; self.value=value; self.label=label
    def draw(self):
        if self.label: _drawLabel(self.label,self.x,self.y-8,size=10,fill=WaTheme.colors["dark"]["subtext"],bold=True,align="left-top")
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.colors["dark"]["input"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=10)
        txt=self.value if self.value else self.placeholder
        col=WaTheme.colors["dark"]["text"] if self.value else WaTheme.colors["dark"]["subtext"]
        for i,ln in enumerate(txt.split("\n")[:4]):
            _drawLabel(ln,self.x+8,self.y+14+i*15,size=11,fill=col,align="left-top")

# WaProgressBar
class WaProgressBar(WaComponent):
    def __init__(self,x,y,w=200,h=8,value=0.45,variant="brand"):
        super().__init__(x,y,w,h,variant)
        self.value=max(0,min(1,value))
    def draw(self):
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.colors["dark"]["border"],roundness=WaTheme.radius["pill"])
        _drawRect(self.x,self.y,self.w*self.value,self.h,fill=WaTheme.variant_fill(self.variant),roundness=WaTheme.radius["pill"])

# WaSpinner
class WaSpinner(WaComponent):
    def __init__(self,x,y,size=24,variant="brand"):
        super().__init__(x,y,size,size,variant)
        self.angle=0
    def draw(self):
        self.angle=(self.angle+12)%360
        _drawCircle(self.x+self.w/2,self.y+self.h/2,self.w/2-2,border=WaTheme.colors["dark"]["border"])
        try:
            from scs import drawArc
            drawArc(self.x+self.w/2,self.y+self.h/2,self.w/2-2,self.w/2-2,0+self.angle,270+self.angle,fill=None,border=WaTheme.variant_fill(self.variant),borderWidth=3)
        except:
            _drawLabel("◍",self.x+self.w/2,self.y+self.h/2,size=self.w,fill=WaTheme.variant_fill(self.variant))

# WaTooltip
class WaTooltip(WaComponent):
    def __init__(self,text,x,y,w=260):
        super().__init__(x,y,w,28,"neutral")
        self.text=text; self.visible=False
    def draw(self):
        if not self.visible: return
        _drawRect(self.x,self.y,self.w,24,fill=WaTheme.colors["neutral"]["900"],roundness=8,opacity=90)
        _drawLabel(self.text,self.x+self.w/2,self.y+12,size=10,fill="white",align="center")

# WaTabGroup
class WaTabGroup(WaComponent):
    def __init__(self,x,y,w=300,tabs=None):
        super().__init__(x,y,w,36,"neutral")
        self.tabs=tabs or ["Lobby","Tetra League","Config"]
        self.active=0; self.tab_width=w//max(1,len(self.tabs))
    def draw(self):
        _drawRect(self.x,self.y,self.w,34,fill=WaTheme.colors["dark"]["card"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=10)
        for i,t in enumerate(self.tabs):
            is_active=i==self.active
            if is_active:
                _drawRect(self.x+i*self.tab_width+2,self.y+2,self.tab_width-4,30,fill=WaTheme.colors["dark"]["card2"],border=WaTheme.colors["dark"]["border"],borderWidth=1,roundness=8)
            _drawLabel(t,self.x+i*self.tab_width+self.tab_width/2,self.y+17,size=11,fill=WaTheme.colors["dark"]["text"] if is_active else WaTheme.colors["dark"]["subtext"],bold=is_active)
    def handlePress(self,mx,my):
        if self.y <= my <= self.y+36 and self.x <= mx <= self.x+self.w:
            idx=int((mx-self.x)//self.tab_width)
            if 0 <= idx < len(self.tabs):
                self.active=idx; return True
        return False

# WaDropdown
class WaDropdownItem:
    def __init__(self,label,variant="neutral"): self.label=label; self.variant=variant

class WaDropdown(WaComponent):
    def __init__(self,x,y,w=140,items=None,label="More"):
        super().__init__(x,y,w,32)
        self.items=items or [WaDropdownItem("Profile"), WaDropdownItem("Settings"), WaDropdownItem("Report Bug","warning")]
        self.label=label; self.open=False
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

# WaAvatar
class WaAvatar(WaComponent):
    def __init__(self,x,y,size=40,initials="P1",variant="brand",image=None):
        super().__init__(x,y,size,size,variant)
        self.initials=initials; self.image=image
    def draw(self):
        _drawCircle(self.x+self.w/2,self.y+self.h/2,self.w/2,fill=WaTheme.colors["dark"]["card2"],border=WaTheme.colors["dark"]["border"])
        _drawLabel(self.initials,self.x+self.w/2,self.y+self.h/2+1,size=int(self.w*0.35),fill=WaTheme.variant_fill(self.variant),bold=True)

# WaTag
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

# WaSwitch
class WaSwitch(WaComponent):
    def __init__(self,x,y,checked=False,label="",variant="brand"):
        super().__init__(x,y,40,22,variant)
        self.checked=checked; self.label=label
    def draw(self):
        fill=WaTheme.variant_fill(self.variant) if self.checked else WaTheme.colors["dark"]["border"]
        _drawRect(self.x,self.y,self.w,self.h,fill=fill,roundness=WaTheme.radius["pill"])
        thumb_x=self.x+(self.w-18) if self.checked else self.x+2
        _drawCircle(thumb_x+9,self.y+11,8,fill="white",border=WaTheme.colors["dark"]["border"])
        if self.label:
            _drawLabel(self.label,self.x+self.w+8,self.y+11,size=11,fill=WaTheme.colors["dark"]["text"],align="left-top")
    def handlePress(self,mx,my):
        if self.x-4 <= mx <= self.x+self.w+len(self.label)*6+20 and self.y-4 <= my <= self.y+self.h+4:
            self.checked=not self.checked; return True
        return False

# WaSlider
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

# WaBreadcrumb
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

# WaDivider
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
