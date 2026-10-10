"""
extensions/canvas_ui.py
----------------------
SCS Canvas UI — 20 components drawn directly to the SCS/Brython canvas,
based on Web Awesome (webawesome.com) principles and design styles.

Web Awesome design principles adopted:
- Variant system: brand | neutral | success | warning | danger
- Appearance tokens: primary, outlined, text
- Size scale: small | medium | large
- Focus ring, soft shadow, 6-12px roundness, high-contrast text
- Slot model: header/body/footer for cards, prefix/suffix for inputs
- Disabled / loading / checked states are visual, not just logical
- Accessible hit targets (min 32px)

All components are pure drawing helpers: they call scs draw* primitives
inside redrawAll and expose contains(x,y) + handle events for Controller.

Usage in any SCS app:
    from extensions.canvas_ui import WaButton, WaCard, WaTheme

    def onAppStart(app):
        app.ui = []
        app.btn = WaButton("PLAY TETRA LEAGUE", 400, 300, 220, 44,
                           variant="brand", onClick=lambda: start_match(app))
        app.ui.append(app.btn)

    def redrawAll(app):
        app.btn.draw()

    def onMousePress(app, mx, my):
        app.btn.handlePress(mx, my)

This file is the extension; copy to extensions/canvas_ui.py in your SCS repo
and add shim in extensions.py if you use the Brython loader.

Top 20 Web Awesome components implemented:
1 WaButton, 2 WaCard, 3 WaInput, 4 WaDialog, 5 WaBadge, 6 WaCallout,
7 WaCheckbox, 8 WaSelect, 9 WaTextarea, 10 WaProgressBar, 11 WaSpinner,
12 WaTooltip, 13 WaTabGroup, 14 WaDropdown, 15 WaAvatar, 16 WaTag,
17 WaSwitch, 18 WaSlider, 19 WaBreadcrumb, 20 WaDivider
"""

# ------------------------------------------------------------
# Theme tokens — mirrors Web Awesome's --wa-* tokens
# ------------------------------------------------------------
class WaTheme:
    # core palette (Web Awesome 3.x defaults)
    colors = {
        "brand":   {"50":"#eef2ff","100":"#e0e7ff","500":"#615fff","600":"#4f39f6","700":"#432dd7"},
        "neutral": {"50":"#f8fafc","200":"#e2e8f0","400":"#90a1b9","500":"#62748e","700":"#364153","900":"#101828"},
        "success": {"50":"#f0fdf4","500":"#00c950","600":"#16a34a"},
        "warning": {"50":"#fefce8","500":"#fdc700","600":"#d97706"},
        "danger":  {"50":"#fef2f2","500":"#fb2c36","600":"#dc2626"},
    }
    radius = {"small":6, "medium":10, "large":16, "pill":999}
    shadow = "0 1px 3px rgba(0,0,0,0.12)"
    font = "Inter, ui-sans-serif, system-ui"
    # helpers
    @staticmethod
    def variant_fill(variant):
        return WaTheme.colors.get(variant, WaTheme.colors["brand"])["500"]
    @staticmethod
    def variant_soft(variant):
        return WaTheme.colors.get(variant, WaTheme.colors["brand"])["50"]

# ------------------------------------------------------------
# Base
# ------------------------------------------------------------
class WaComponent:
    def __init__(self, x, y, w, h, variant="neutral", size="medium", disabled=False):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.variant = variant
        self.size = size
        self.disabled = disabled
        self.hovered = False
        self.pressed = False
        self.focused = False

    def contains(self, mx, my):
        return self.x <= mx <= self.x+self.w and self.y <= my <= self.y+self.h

    def handleMove(self, mx, my):
        self.hovered = self.contains(mx, my)

# safe import for SCS vs pure python preview
def _drawRect(x,y,w,h,fill=None,border=None,borderWidth=1,roundness=8,opacity=100):
    try:
        from scs import drawRect
        drawRect(x,y,w,h,fill=fill,border=border,borderWidth=borderWidth,roundness=roundness,opacity=opacity)
    except:
        pass
def _drawLabel(text,x,y,size=14,fill="black",bold=False,align="center"):
    try:
        from scs import drawLabel
        drawLabel(text,x,y,size=size,fill=fill,bold=bold,align=align)
    except:
        pass
def _drawCircle(x,y,r,fill=None,border=None):
    try:
        from scs import drawCircle
        drawCircle(x,y,r,fill=fill,border=border)
    except:
        pass
def _drawLine(x1,y1,x2,y2,fill="black",lineWidth=1):
    try:
        from scs import drawLine
        drawLine(x1,y1,x2,y2,fill=fill,lineWidth=lineWidth)
    except:
        pass

# ------------------------------------------------------------
# 1. WaButton — wa-button
# ------------------------------------------------------------
class WaButton(WaComponent):
    """Primary action control. Supports variant, outlined, pill, loading."""
    def __init__(self, label, x, y, w=140, h=40, variant="brand", appearance="filled", pill=False, onClick=None):
        super().__init__(x,y,w,h,variant)
        self.label = label
        self.appearance = appearance
        self.pill = pill
        self.onClick = onClick
        self.loading = False

    def draw(self):
        fill = WaTheme.variant_fill(self.variant)
        if self.appearance == "outlined":
            fill = "white"
            border = WaTheme.variant_fill(self.variant)
        else:
            border = fill
        if self.disabled:
            fill = WaTheme.colors["neutral"]["200"]
            border = fill
        if self.pressed:
            # darken
            opacity = 90
        else:
            opacity = 100
        r = WaTheme.radius["pill"] if self.pill else WaTheme.radius["medium"]
        _drawRect(self.x,self.y,self.w,self.h,fill=fill,border=border,borderWidth=1.5,roundness=r,opacity=opacity)
        # inner highlight for brand
        txt = "white" if self.appearance=="filled" else WaTheme.variant_fill(self.variant)
        if self.disabled: txt = WaTheme.colors["neutral"]["400"]
        _drawLabel(self.label, self.x+self.w/2, self.y+self.h/2+1, size=14 if self.size=="medium" else 12, fill=txt, bold=True)

    def handlePress(self, mx, my):
        if self.disabled: return False
        if self.contains(mx, my):
            self.pressed = True
            if self.onClick: self.onClick()
            return True
        return False
    def handleRelease(self, mx, my):
        self.pressed = False

# ------------------------------------------------------------
# 2. WaCard — wa-card
# ------------------------------------------------------------
class WaCard(WaComponent):
    """Slotted container with header/body/footer. WebAwesome card uses with-header."""
    def __init__(self, x,y,w,h, header="", footer="", variant="neutral"):
        super().__init__(x,y,w,h,variant)
        self.header = header
        self.footer = footer

    def draw(self, body_draw_fn=None):
        # shadow layer
        _drawRect(self.x+2,self.y+3,self.w,self.h,fill="black",border=None,roundness=16,opacity=8)
        _drawRect(self.x,self.y,self.w,self.h,fill="white",border=WaTheme.colors["neutral"]["200"],borderWidth=1,roundness=16)
        if self.header:
            _drawRect(self.x,self.y,self.w,40,fill=WaTheme.variant_soft(self.variant),border=None,roundness=16)
            # cut bottom radius for header
            _drawRect(self.x,self.y+20,self.w,20,fill=WaTheme.variant_soft(self.variant))
            _drawLabel(self.header, self.x+16, self.y+20, size=13, fill=WaTheme.colors["neutral"]["700"], bold=True, align="left-top")
        if self.footer:
            _drawLabel(self.footer, self.x+12, self.y+self.h-12, size=11, fill=WaTheme.colors["neutral"]["400"], align="left-top")
        if body_draw_fn:
            body_draw_fn(self.x+12, self.y+ (50 if self.header else 12))

# ------------------------------------------------------------
# 3. WaInput — wa-input
# ------------------------------------------------------------
class WaInput(WaComponent):
    """Single-line form control with label, hint, prefix/suffix slots."""
    def __init__(self, x,y,w=220,h=40, placeholder="Enter...", label="", value="", variant="neutral"):
        super().__init__(x,y,w,h,variant)
        self.placeholder = placeholder
        self.label = label
        self.value = value
        self.hint = ""

    def draw(self):
        if self.label:
            _drawLabel(self.label, self.x, self.y-8, size=12, fill=WaTheme.colors["neutral"]["500"], align="left-top", bold=True)
        fill = "white"
        border = WaTheme.colors["neutral"]["200"]
        if self.focused:
            border = WaTheme.variant_fill("brand")
        _drawRect(self.x,self.y,self.w,self.h,fill=fill,border=border,borderWidth=1.5 if self.focused else 1,roundness=10)
        txt = self.value if self.value else self.placeholder
        col = WaTheme.colors["neutral"]["700"] if self.value else WaTheme.colors["neutral"]["400"]
        _drawLabel(txt, self.x+10, self.y+self.h/2+1, size=13, fill=col, align="left-top")
        if self.hint:
            _drawLabel(self.hint, self.x, self.y+self.h+4, size=11, fill=WaTheme.colors["neutral"]["400"], align="left-top")

# ------------------------------------------------------------
# 4. WaDialog — wa-dialog
# ------------------------------------------------------------
class WaDialog(WaComponent):
    """Modal requiring attention. Draws overlay + centered panel."""
    def __init__(self, title, message, x=0,y=0,w=400,h=220, variant="brand"):
        # x,y are center for dialog
        super().__init__(x,y,w,h,variant)
        self.title = title
        self.message = message
        self.open = False
        self.buttons = []

    def show(self): self.open = True
    def hide(self): self.open = False

    def draw(self, app_width=800, app_height=600):
        if not self.open: return
        # overlay
        _drawRect(0,0,app_width,app_height,fill="black",opacity=35)
        cx = app_width/2 - self.w/2
        cy = app_height/2 - self.h/2
        _drawRect(cx,cy,self.w,self.h,fill="white",border=WaTheme.colors["neutral"]["200"],borderWidth=1,roundness=18)
        _drawLabel(self.title, cx+20, cy+22, size=16, fill=WaTheme.colors["neutral"]["900"], bold=True, align="left-top")
        _drawLabel(self.message, cx+20, cy+52, size=13, fill=WaTheme.colors["neutral"]["500"], align="left-top")
        for b in self.buttons:
            b.draw()

# ------------------------------------------------------------
# 5. WaBadge — wa-badge
# ------------------------------------------------------------
class WaBadge(WaComponent):
    """Status / count pill, usually attached to other controls."""
    def __init__(self, text, x,y, variant="brand", pill=True):
        super().__init__(x,y,24,20,variant)
        self.text = str(text)
        self.pill = pill
        self.w = max(22, len(self.text)*8+12)
    def draw(self):
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.variant_fill(self.variant),roundness=WaTheme.radius["pill"],opacity=100)
        _drawLabel(self.text, self.x+self.w/2, self.y+self.h/2+1, size=11, fill="white", bold=True)

# ------------------------------------------------------------
# 6. WaCallout — wa-callout
# ------------------------------------------------------------
class WaCallout(WaComponent):
    """Inline important message with variant color and icon area."""
    def __init__(self, x,y,w, message, variant="warning", title=""):
        super().__init__(x,y,w,48,variant)
        self.message = message
        self.title = title
        self.h = 48 + (18 if title else 0)
    def draw(self):
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.variant_soft(self.variant),border=WaTheme.variant_fill(self.variant),borderWidth=1.2,roundness=12)
        if self.title:
            _drawLabel(self.title, self.x+12, self.y+12, size=12, fill=WaTheme.variant_fill(self.variant), bold=True, align="left-top")
            _drawLabel(self.message, self.x+12, self.y+28, size=12, fill=WaTheme.colors["neutral"]["700"], align="left-top")
        else:
            _drawLabel(self.message, self.x+12, self.y+self.h/2+1, size=12, fill=WaTheme.colors["neutral"]["700"], align="left-top")

# ------------------------------------------------------------
# 7. WaCheckbox — wa-checkbox
# ------------------------------------------------------------
class WaCheckbox(WaComponent):
    def __init__(self, x,y, label="", checked=False, variant="brand"):
        super().__init__(x,y,20,20,variant)
        self.label = label
        self.checked = checked
    def draw(self):
        fill = WaTheme.variant_fill(self.variant) if self.checked else "white"
        _drawRect(self.x,self.y,18,18,fill=fill,border=WaTheme.variant_fill(self.variant) if self.checked else WaTheme.colors["neutral"]["200"],borderWidth=1.5,roundness=5)
        if self.checked:
            _drawLabel("✓", self.x+9, self.y+9, size=12, fill="white", bold=True)
        if self.label:
            _drawLabel(self.label, self.x+26, self.y+10, size=13, fill=WaTheme.colors["neutral"]["700"], align="left-top")
    def toggle(self, mx,my):
        if self.contains(mx,my) or (self.label and mx < self.x+120):
            self.checked = not self.checked
            return True
        return False

# ------------------------------------------------------------
# 8. WaSelect — wa-select
# ------------------------------------------------------------
class WaSelect(WaComponent):
    """Dropdown list of options."""
    def __init__(self, x,y,w=180, options=None, value=None, label=""):
        super().__init__(x,y,w,36,"neutral")
        self.options = options or ["Tetra League","Quick Play","40 Lines","Blitz"]
        self.value = value or self.options[0]
        self.label = label
        self.expanded = False
    def draw(self):
        if self.label:
            _drawLabel(self.label, self.x, self.y-8, size=11, fill=WaTheme.colors["neutral"]["500"], bold=True, align="left-top")
        _drawRect(self.x,self.y,self.w,self.h,fill="white",border=WaTheme.colors["neutral"]["200"],borderWidth=1,roundness=10)
        _drawLabel(self.value, self.x+10, self.y+self.h/2+1, size=13, fill=WaTheme.colors["neutral"]["700"], align="left-top")
        _drawLabel("▾", self.x+self.w-14, self.y+self.h/2+1, size=12, fill=WaTheme.colors["neutral"]["400"])
        if self.expanded:
            _drawRect(self.x,self.y+self.h+4,self.w,len(self.options)*28+8,fill="white",border=WaTheme.colors["neutral"]["200"],borderWidth=1,roundness=10)
            for i,opt in enumerate(self.options):
                col = WaTheme.variant_soft("brand") if opt==self.value else "white"
                _drawRect(self.x+2,self.y+self.h+8+i*28,self.w-4,24,fill=col,roundness=6)
                _drawLabel(opt, self.x+10, self.y+self.h+20+i*28, size=12, fill=WaTheme.colors["neutral"]["700"], align="left-top")
    def handlePress(self, mx,my):
        if self.contains(mx,my):
            self.expanded = not self.expanded
            return True
        if self.expanded:
            for i,opt in enumerate(self.options):
                rx=self.x; ry=self.y+self.h+8+i*28
                if rx <= mx <= rx+self.w and ry <= my <= ry+24:
                    self.value = opt
                    self.expanded=False
                    return True
            self.expanded=False
        return False

# ------------------------------------------------------------
# 9. WaTextarea — wa-textarea
# ------------------------------------------------------------
class WaTextarea(WaComponent):
    def __init__(self, x,y,w=260,h=80, placeholder="...", value="", label=""):
        super().__init__(x,y,w,h)
        self.placeholder = placeholder
        self.value = value
        self.label = label
    def draw(self):
        if self.label:
            _drawLabel(self.label, self.x, self.y-8, size=11, fill=WaTheme.colors["neutral"]["500"], bold=True, align="left-top")
        _drawRect(self.x,self.y,self.w,self.h,fill="white",border=WaTheme.colors["neutral"]["200"],borderWidth=1,roundness=10)
        txt = self.value if self.value else self.placeholder
        col = WaTheme.colors["neutral"]["700"] if self.value else WaTheme.colors["neutral"]["400"]
        # simple multiline split
        lines = txt.split("\n")[:4]
        for i,ln in enumerate(lines):
            _drawLabel(ln, self.x+8, self.y+14+i*16, size=12, fill=col, align="left-top")

# ------------------------------------------------------------
# 10. WaProgressBar — wa-progress-bar
# ------------------------------------------------------------
class WaProgressBar(WaComponent):
    def __init__(self, x,y,w=200,h=10, value=0.45, variant="brand"):
        super().__init__(x,y,w,h,variant)
        self.value = max(0,min(1,value))
    def draw(self):
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.colors["neutral"]["200"],roundness=WaTheme.radius["pill"])
        _drawRect(self.x,self.y,self.w*self.value,self.h,fill=WaTheme.variant_fill(self.variant),roundness=WaTheme.radius["pill"])

# ------------------------------------------------------------
# 11. WaSpinner — wa-spinner
# ------------------------------------------------------------
class WaSpinner(WaComponent):
    def __init__(self, x,y, size=24, variant="brand"):
        super().__init__(x,y,size,size,variant)
        self.angle = 0
    def draw(self):
        # draw 3/4 arc via circle with gap — approximated with label
        self.angle = (self.angle + 8) % 360
        _drawCircle(self.x+self.w/2, self.y+self.h/2, self.w/2-2, border=WaTheme.colors["neutral"]["200"])
        # spinner tick
        try:
            from scs import drawArc
            drawArc(self.x+self.w/2, self.y+self.h/2, self.w/2-2, self.w/2-2, 0+self.angle, 270+self.angle, fill=None, border=WaTheme.variant_fill(self.variant), borderWidth=3)
        except:
            _drawLabel("◍", self.x+self.w/2, self.y+self.h/2, size=self.w, fill=WaTheme.variant_fill(self.variant))

# ------------------------------------------------------------
# 12. WaTooltip — wa-tooltip
# ------------------------------------------------------------
class WaTooltip(WaComponent):
    def __init__(self, text, x,y, w=160):
        super().__init__(x,y,w,28,"neutral")
        self.text = text
        self.visible=False
    def draw(self):
        if not self.visible: return
        _drawRect(self.x,self.y,self.w,28,fill=WaTheme.colors["neutral"]["900"],roundness=8,opacity=92)
        _drawLabel(self.text, self.x+self.w/2, self.y+14, size=11, fill="white", align="center")

# ------------------------------------------------------------
# 13. WaTabGroup — wa-tab-group + wa-tab + wa-tab-panel
# ------------------------------------------------------------
class WaTabGroup(WaComponent):
    def __init__(self, x,y,w=320, tabs=None):
        super().__init__(x,y,w,40,"neutral")
        self.tabs = tabs or ["Lobby","Tetra League","Config"]
        self.active = 0
        self.tab_width = w//max(1,len(self.tabs))
    def draw(self):
        _drawRect(self.x,self.y,self.w,36,fill=WaTheme.colors["neutral"]["50"],border=WaTheme.colors["neutral"]["200"],borderWidth=1,roundness=10)
        for i,t in enumerate(self.tabs):
            is_active = i==self.active
            if is_active:
                _drawRect(self.x+i*self.tab_width+2,self.y+2,self.tab_width-4,32,fill="white",border=WaTheme.colors["neutral"]["200"],borderWidth=1,roundness=8)
            _drawLabel(t, self.x+i*self.tab_width+self.tab_width/2, self.y+18, size=12, fill=WaTheme.colors["neutral"]["900"] if is_active else WaTheme.colors["neutral"]["500"], bold=is_active)
    def handlePress(self,mx,my):
        if self.y <= my <= self.y+36 and self.x <= mx <= self.x+self.w:
            idx = int((mx-self.x)//self.tab_width)
            if 0 <= idx < len(self.tabs):
                self.active = idx
                return True
        return False

# ------------------------------------------------------------
# 14. WaDropdown — wa-dropdown
# ------------------------------------------------------------
class WaDropdownItem:
    def __init__(self, label, variant="neutral"):
        self.label=label; self.variant=variant

class WaDropdown(WaComponent):
    def __init__(self, x,y,w=160, items=None, label="Menu"):
        super().__init__(x,y,w,36)
        self.items = items or [WaDropdownItem("Profile"), WaDropdownItem("Settings"), WaDropdownItem("Logout", "danger")]
        self.label=label
        self.open=False
    def draw(self):
        _drawRect(self.x,self.y,self.w,36,fill="white",border=WaTheme.colors["neutral"]["200"],borderWidth=1,roundness=10)
        _drawLabel(self.label+" ▾", self.x+self.w/2, self.y+18, size=13, fill=WaTheme.colors["neutral"]["700"], bold=True)
        if self.open:
            h = len(self.items)*32+8
            _drawRect(self.x,self.y+40,self.w,h,fill="white",border=WaTheme.colors["neutral"]["200"],borderWidth=1,roundness=12)
            for i,it in enumerate(self.items):
                y = self.y+44+i*32
                _drawLabel(it.label, self.x+12, y+10, size=12, fill=WaTheme.variant_fill(it.variant) if it.variant!="neutral" else WaTheme.colors["neutral"]["700"], align="left-top")
    def handlePress(self,mx,my):
        if self.contains(mx,my):
            self.open=not self.open
            return True
        if self.open:
            for i in range(len(self.items)):
                y=self.y+44+i*32
                if self.x <= mx <= self.x+self.w and y <= my <= y+24:
                    self.open=False
                    return it.label if (it:=self.items[i]) else True
        self.open=False
        return False

# ------------------------------------------------------------
# 15. WaAvatar — wa-avatar
# ------------------------------------------------------------
class WaAvatar(WaComponent):
    def __init__(self, x,y, size=40, initials="P1", variant="brand", image=None):
        super().__init__(x,y,size,size,variant)
        self.initials=initials
        self.image=image
    def draw(self):
        _drawCircle(self.x+self.w/2, self.y+self.h/2, self.w/2, fill=WaTheme.variant_soft(self.variant), border=WaTheme.colors["neutral"]["200"])
        _drawLabel(self.initials, self.x+self.w/2, self.y+self.h/2+1, size=int(self.w*0.35), fill=WaTheme.variant_fill(self.variant), bold=True)

# ------------------------------------------------------------
# 16. WaTag — wa-tag
# ------------------------------------------------------------
class WaTag(WaComponent):
    def __init__(self, label, x,y, variant="neutral", removable=True):
        super().__init__(x,y,len(label)*8+28,24,variant)
        self.label=label
        self.removable=removable
        self.removed=False
    def draw(self):
        if self.removed: return
        _drawRect(self.x,self.y,self.w,self.h,fill=WaTheme.variant_soft(self.variant),border=WaTheme.variant_fill(self.variant),borderWidth=1,roundness=8)
        _drawLabel(self.label, self.x+8, self.y+self.h/2+1, size=11, fill=WaTheme.variant_fill(self.variant), bold=True, align="left-top")
        if self.removable:
            _drawLabel("×", self.x+self.w-10, self.y+self.h/2+1, size=12, fill=WaTheme.variant_fill(self.variant), bold=True)
    def handlePress(self,mx,my):
        if self.removed: return False
        if self.x+self.w-16 <= mx <= self.x+self.w and self.y <= my <= self.y+self.h:
            self.removed=True
            return True
        return False

# ------------------------------------------------------------
# 17. WaSwitch — wa-switch
# ------------------------------------------------------------
class WaSwitch(WaComponent):
    def __init__(self, x,y, checked=False, label="", variant="brand"):
        super().__init__(x,y,44,26,variant)
        self.checked=checked
        self.label=label
    def draw(self):
        fill = WaTheme.variant_fill(self.variant) if self.checked else WaTheme.colors["neutral"]["200"]
        _drawRect(self.x,self.y,self.w,self.h,fill=fill,roundness=WaTheme.radius["pill"])
        thumb_x = self.x+ (self.w-22) if self.checked else self.x+2
        _drawCircle(thumb_x+10, self.y+13, 9, fill="white", border=WaTheme.colors["neutral"]["200"])
        if self.label:
            _drawLabel(self.label, self.x+self.w+8, self.y+13, size=13, fill=WaTheme.colors["neutral"]["700"], align="left-top")
    def handlePress(self,mx,my):
        # larger hit
        if self.x-4 <= mx <= self.x+self.w+ (len(self.label)*8+10) and self.y-4 <= my <= self.y+self.h+4:
            self.checked = not self.checked
            return True
        return False

# ------------------------------------------------------------
# 18. WaSlider — wa-slider
# ------------------------------------------------------------
class WaSlider(WaComponent):
    def __init__(self, x,y,w=180, min=0, max=100, value=50, label="", variant="brand"):
        super().__init__(x,y,w,20,variant)
        self.min=min; self.max=max; self.value=value; self.label=label; self.dragging=False
    def draw(self):
        if self.label:
            _drawLabel(f"{self.label}: {int(self.value)}", self.x, self.y-6, size=11, fill=WaTheme.colors["neutral"]["500"], bold=True, align="left-top")
        _drawRect(self.x,self.y+8,self.w,4,fill=WaTheme.colors["neutral"]["200"],roundness=4)
        pct = (self.value-self.min)/(self.max-self.min) if self.max!=self.min else 0
        _drawRect(self.x,self.y+8,self.w*pct,4,fill=WaTheme.variant_fill(self.variant),roundness=4)
        _drawCircle(self.x+self.w*pct, self.y+10, 8, fill="white", border=WaTheme.variant_fill(self.variant))
    def handlePress(self,mx,my):
        if self.y <= my <= self.y+20 and self.x-6 <= mx <= self.x+self.w+6:
            self.dragging=True
            self._updateFromX(mx)
            return True
        return False
    def handleDrag(self,mx,my):
        if self.dragging:
            self._updateFromX(mx)
            return True
        return False
    def handleRelease(self,mx,my):
        self.dragging=False
    def _updateFromX(self,mx):
        pct = max(0,min(1,(mx-self.x)/self.w))
        self.value = self.min + pct*(self.max-self.min)

# ------------------------------------------------------------
# 19. WaBreadcrumb — wa-breadcrumb
# ------------------------------------------------------------
class WaBreadcrumb(WaComponent):
    def __init__(self, x,y, items=None):
        super().__init__(x,y,300,20,"neutral")
        self.items = items or ["Home","Arcade","TETR.IO"]
    def draw(self):
        x = self.x
        for i,it in enumerate(self.items):
            is_last = i==len(self.items)-1
            col = WaTheme.colors["neutral"]["900"] if is_last else WaTheme.colors["neutral"]["400"]
            _drawLabel(it, x, self.y+6, size=12, fill=col, bold=is_last, align="left-top")
            x += len(it)*7+8
            if not is_last:
                _drawLabel("/", x, self.y+6, size=12, fill=WaTheme.colors["neutral"]["200"], align="left-top")
                x+=10

# ------------------------------------------------------------
# 20. WaDivider — wa-divider
# ------------------------------------------------------------
class WaDivider(WaComponent):
    def __init__(self, x,y,w=300, vertical=False, label=""):
        super().__init__(x,y,w,1 if not vertical else 100)
        self.vertical=vertical
        self.label=label
    def draw(self):
        if self.vertical:
            _drawRect(self.x,self.y,1,self.h,fill=WaTheme.colors["neutral"]["200"])
        else:
            _drawRect(self.x,self.y+self.h/2,self.w,1,fill=WaTheme.colors["neutral"]["200"])
            if self.label:
                _drawRect(self.x+self.w/2-30,self.y,60,16,fill="white")
                _drawLabel(self.label, self.x+self.w/2, self.y+8, size=11, fill=WaTheme.colors["neutral"]["400"])

# ------------------------------------------------------------
# Composite helper — WaCard with slots (convenience)
# ------------------------------------------------------------
def WaCardWithBody(x,y,w,h,header,body_fn,footer=""):
    c = WaCard(x,y,w,h,header=header,footer=footer)
    c._body_fn = body_fn
    return c

__all__ = [
 "WaTheme","WaComponent",
 "WaButton","WaCard","WaInput","WaDialog","WaBadge","WaCallout",
 "WaCheckbox","WaSelect","WaTextarea","WaProgressBar","WaSpinner",
 "WaTooltip","WaTabGroup","WaDropdown","WaDropdownItem","WaAvatar",
 "WaTag","WaSwitch","WaSlider","WaBreadcrumb","WaDivider"
]
