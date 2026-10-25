
"""
apps/ferrers.py — Ferrers Diagram Explorer
SCS app 1050x700

Heavy combinatorics (p(n) Euler recurrence, hook-length formula, f^lambda)
runs in Pyodide WASM worker, canvas stays 60fps.

Controls are injected via browser.document into #canvas-container parent.
"""

from scs import *
from browser import document, aio
from extensions.pyodide import partition_stats

import re
import math

BG = rgb(15, 20, 23)
INK = rgb(229, 238, 232)
MUTED = rgb(137, 157, 151)
MINT = rgb(102, 224, 177)
GOLD = rgb(244, 190, 92)
RED = rgb(244, 111, 104)
BLUE = rgb(110, 180, 255)

_PANEL_ID = "ferrers-controls"

_EXAMPLES = {
    "classic17": ("1. Classic 17 — 6+4+4+2+1", "6+4+4+2+1", "MathWorld classic, Durfee 3, conj (5,4,3,3,1,1)"),
    "staircase15": ("2. Staircase 15 — 5+4+3+2+1 (self-conj)", "5+4+3+2+1", "self-conjugate, λ=λ', Durfee 3"),
    "square16": ("3. Square 16 — 4+4+4+4 (in 4×4 box)", "4+4+4+4", "1 of C(8,4)=70 diagrams in 4×4 box"),
    "hook12": ("4. Hook 12 — 7+1+1+1+1+1", "7+1+1+1+1+1", "hook shape, Durfee 1"),
    "irregular21": ("5. Irregular 21 — 8+5+3+2+2+1", "8+5+3+2+2+1", "conj (6,5,3,2,2,1,1,1), Durfee 3"),
}

def _parse_partition(text):
    if not text or not text.strip():
        return None
    s = text.strip().replace("$", "")
    parts = re.split(r"=|⊢|\\vdash", s)
    cand = s
    best = -1
    for seg in parts:
        score = seg.count("+")*2 + seg.count(",") + seg.count("(")
        if len(re.findall(r"\d+", seg)) >= 2:
            score += len(re.findall(r"\d+", seg))
        if score > best:
            best = score
            cand = seg
    cand = cand.replace("(", " ").replace(")", " ").replace("[", " ").replace("]", " ").replace("{", " ").replace("}", " ")
    if "+" in cand:
        toks = cand.split("+")
    elif "," in cand:
        toks = cand.split(",")
    else:
        toks = re.split(r"\s+", cand)
    nums = []
    for t in toks:
        m = re.search(r"\d+", t)
        if m:
            v = int(m.group(0))
            if v > 0:
                nums.append(v)
    if not nums:
        all_nums = [int(x) for x in re.findall(r"\d+", s)]
        if len(all_nums) >= 2 and all_nums[0] == sum(all_nums[1:]):
            nums = all_nums[1:]
        elif all_nums:
            nums = all_nums
    if not nums:
        return None
    nums = sorted([x for x in nums if x > 0], reverse=True)
    if len(nums) > 30:
        nums = nums[:30]
    nums = [min(x, 50) for x in nums]
    return nums or None

def _get_cell_pos(app, r, c):
    max_len = max(app.partition) if app.partition else 1
    cell = app.cellSize
    gap = app.cellGap
    tw = max_len * (cell + gap) - gap
    th = len(app.partition) * (cell + gap) - gap
    sx = app.diagramCenterX - tw // 2
    sy = app.diagramCenterY - th // 2
    return (sx + c * (cell + gap), sy + r * (cell + gap))

def _hit_test(app, mx, my):
    if not app.partition:
        return None
    for r, rl in enumerate(app.partition):
        for c in range(rl):
            x, y = _get_cell_pos(app, r, c)
            if x <= mx <= x + app.cellSize and y <= my <= y + app.cellSize:
                return (r, c, "cell")
        x, y = _get_cell_pos(app, r, rl)
        if x <= mx <= x + app.cellSize and y <= my <= y + app.cellSize and rl < 50:
            return (r, rl, "add_right")
    max_len = max(app.partition) if app.partition else 1
    cell = app.cellSize
    gap = app.cellGap
    tw = max_len * (cell + gap) - gap
    th = len(app.partition) * (cell + gap) - gap
    sx = app.diagramCenterX - tw // 2
    sy = app.diagramCenterY - th // 2
    ny = sy + len(app.partition) * (cell + gap)
    if sx <= mx <= sx + cell and ny <= my <= ny + cell and len(app.partition) < 30:
        return (len(app.partition), 0, "add_new_row")
    return None

def _install_controls(app):
    existing = document.getElementById(_PANEL_ID)
    if existing:
        existing.parentNode.removeChild(existing)
    panel = document.createElement("section")
    panel.id = _PANEL_ID
    panel.style.cssText = "box-sizing:border-box;width:1050px;max-width:95vw;padding:20px 24px 16px;margin:0 0 14px;background:#191f22;border:1px solid #34413e;color:#e5eee8;font:15px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;border-radius:10px;"
    options_html = ""
    for key, (label, val, desc) in _EXAMPLES.items():
        sel = " selected" if key == "classic17" else ""
        options_html += f'<option value="{key}"{sel}>{label}</option>'
    panel.innerHTML = f"""
<div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:16px">
  <div>
    <strong style="font-size:22px;color:#66e0b1;letter-spacing:0.5px">FERRERS DIAGRAMS — PARTITION GEOMETRY</strong>
    <div style="margin-top:4px;color:#899d97;font-size:15px">Pyodide WASM · Euler recurrence · Hook-length · Durfee square</div>
  </div>
  <span style="color:#f4be5c;font-size:15px" id="ferrers-status">Ready</span>
</div>
<div style="display:grid;grid-template-columns:320px 1fr;gap:18px;align-items:start;margin-bottom:14px">
  <label style="display:grid;gap:8px;color:#b6c6bf">
    <span style="font-size:15px;font-weight:600;color:#e5eee8">EXAMPLES</span>
    <select id="ferrers-example" style="box-sizing:border-box;width:100%;background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:12px;font:15px ui-monospace,SFMono-Regular,Consolas,monospace;border-radius:8px">
      {options_html}
    </select>
    <span style="color:#899d97;font-size:14px" id="ferrers-example-desc">MathWorld classic, Durfee 3</span>
  </label>
  <label style="display:grid;gap:8px;color:#b6c6bf">
    <span style="font-size:15px;font-weight:600;color:#e5eee8">PARTITION — LaTeX or + notation</span>
    <input id="ferrers-input" value="6+4+4+2+1" spellcheck="false" style="box-sizing:border-box;width:100%;background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:12px;font:15px ui-monospace,SFMono-Regular,Consolas,monospace;border-radius:8px" placeholder="e.g. 6+4+4+2+1 or (6,4,4,2,1)">
    <span style="color:#899d97;font-size:14px">Supports 6+4+4+2+1, (6,4,4,2,1), λ=(6,4,4,2,1)⊢17 — Enter to parse, Space cycles</span>
  </label>
</div>
<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px">
  <button id="ferrers-parse" style="height:42px;padding:0 18px;border:0;background:#66e0b1;color:#10201a;font-weight:800;font-size:15px;font-family:inherit;cursor:pointer;border-radius:8px">Parse</button>
  <button id="ferrers-boxes" style="height:42px;padding:0 16px;border:1px solid #43524d;background:#232e2b;color:#e5eee8;font-weight:600;font-size:15px;font-family:inherit;cursor:pointer;border-radius:8px">Boxes</button>
  <button id="ferrers-conj" style="height:42px;padding:0 16px;border:1px solid #43524d;background:#232e2b;color:#e5eee8;font-weight:600;font-size:15px;font-family:inherit;cursor:pointer;border-radius:8px">Conj OFF</button>
  <button id="ferrers-durfee" style="height:42px;padding:0 16px;border:1px solid #43524d;background:#34413e;color:#f4be5c;font-weight:700;font-size:15px;font-family:inherit;cursor:pointer;border-radius:8px">Durfee ON</button>
  <button id="ferrers-hooks" style="height:42px;padding:0 16px;border:1px solid #43524d;background:#232e2b;color:#e5eee8;font-weight:600;font-size:15px;font-family:inherit;cursor:pointer;border-radius:8px">Hooks OFF</button>
  <span style="margin-left:8px;color:#899d97;font-size:14px">Click row end + to add, cell to remove • b/c/d/h • i info</span>
</div>
<div id="ferrers-latex" style="margin-top:8px;color:#f4be5c;font-size:16px;min-height:22px"></div>
"""
    container = document.getElementById("canvas-container")
    container.parentNode.insertBefore(panel, container)

    def submit_example(event):
        key = document["ferrers-example"].value
        label, val, desc = _EXAMPLES.get(key, _EXAMPLES["classic17"])
        document["ferrers-input"].value = val
        document["ferrers-example-desc"].innerText = desc[:110]
        app.exampleKey = key
        part = _parse_partition(val)
        if part:
            aio.run(_analyze(app, part))

    def submit_parse(event):
        if event:
            event.preventDefault()
        txt = document["ferrers-input"].value
        part = _parse_partition(txt)
        if not part:
            app.error = f"Could not parse '{txt[:30]}'"
            app.status = "Parse error"
            _update_status(app)
            return
        aio.run(_analyze(app, part))

    def toggle_boxes(event):
        app.modeBoxes = not app.modeBoxes
        document["ferrers-boxes"].innerText = "Boxes" if app.modeBoxes else "Dots"
    def toggle_conj(event):
        app.showConjugate = not app.showConjugate
        document["ferrers-conj"].innerText = "Conj ON" if app.showConjugate else "Conj OFF"
        document["ferrers-conj"].style.background = "#66e0b1" if app.showConjugate else "#232e2b"
        document["ferrers-conj"].style.color = "#10201a" if app.showConjugate else "#e5eee8"
    def toggle_durfee(event):
        app.showDurfee = not app.showDurfee
        document["ferrers-durfee"].innerText = "Durfee ON" if app.showDurfee else "Durfee OFF"
    def toggle_hooks(event):
        app.showHooks = not app.showHooks
        document["ferrers-hooks"].innerText = "Hooks ON" if app.showHooks else "Hooks OFF"
        document["ferrers-hooks"].style.background = "#66e0b1" if app.showHooks else "#232e2b"
        document["ferrers-hooks"].style.color = "#10201a" if app.showHooks else "#e5eee8"

    document["ferrers-example"].bind("change", submit_example)
    document["ferrers-parse"].bind("click", submit_parse)
    document["ferrers-input"].bind("change", submit_parse)
    document["ferrers-boxes"].bind("click", toggle_boxes)
    document["ferrers-conj"].bind("click", toggle_conj)
    document["ferrers-durfee"].bind("click", toggle_durfee)
    document["ferrers-hooks"].bind("click", toggle_hooks)
    def on_key(event):
        if event.keyCode == 13:
            submit_parse(event)
    document["ferrers-input"].bind("keydown", on_key)

def _update_status(app):
    el = document.getElementById("ferrers-status")
    if not el:
        return
    if app.busy:
        el.innerText = "Computing in Pyodide…"
        el.style.color = "#f4be5c"
    elif app.error:
        el.innerText = f"Error: {app.error[:60]}"
        el.style.color = "#f46f68"
    else:
        if app.partitionNumber is not None:
            pn = app.partitionNumber
            pn_str = str(pn)
            if len(pn_str) > 12:
                pn_str = pn_str[:5] + "…" + pn_str[-4:] + f" ({len(str(pn))}d)"
            fl = app.f_lambda
            fl_str = str(fl)
            if len(fl_str) > 12:
                fl_str = fl_str[:5] + "…" + fl_str[-4:]
            el.innerText = f"p({app.n})={pn_str} · f^λ={fl_str} · Pyodide ✓"
            el.style.color = "#66e0b1"
        else:
            el.innerText = app.status or "Ready"
            el.style.color = "#66e0b1"
    latex_el = document.getElementById("ferrers-latex")
    if latex_el and app.partition:
        inner = ",".join(map(str, app.partition))
        plus = "+".join(map(str, app.partition))
        conj = ",".join(map(str, app.conjugate)) if app.conjugate else ""
        latex_el.innerText = f"λ=({inner})={plus}⊢{app.n}  λ'=({conj})  Durfee={app.durfee}  self={app.selfConj}  n={app.n} k={len(app.partition)}"

async def _analyze(app, part):
    app.busy = True
    app.error = None
    app.status = f"Computing p({sum(part)})…"
    _update_status(app)
    try:
        result = await partition_stats(part)
        app.partition = result.get("part", part)
        app.conjugate = result.get("conj", [])
        app.durfee = result.get("durfee", 0)
        app.hooks = result.get("hooks", [])
        app.partitionNumber = result.get("p_n", 0)
        app.partitionNumberN = result.get("n", sum(part))
        app.f_lambda = result.get("f_lambda", 0)
        app.prodHooks = result.get("prod_hooks", 1)
        app.n = result.get("n", sum(part))
        app.selfConj = app.partition == app.conjugate
        app.animT = 0
        app.status = f"Ready — p({app.n})={app.partitionNumber}"
        app.error = None
        try:
            document["ferrers-input"].value = "+".join(map(str, app.partition))
        except:
            pass
    except Exception as err:
        app.error = str(err)
        app.status = "Computation failed"
    finally:
        app.busy = False
        _update_status(app)

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 60
    app.background = BG
    app.partition = [6, 4, 4, 2, 1]
    app.conjugate = [5, 4, 3, 3, 1, 1]
    app.durfee = 3
    app.hooks = []
    app.selfConj = False
    app.n = 17
    app.cellSize = 44
    app.cellGap = 8
    app.diagramCenterX = app.width // 2 - 10
    app.diagramCenterY = app.height // 2 + 60
    app.modeBoxes = True
    app.showConjugate = False
    app.showDurfee = True
    app.showHooks = False
    app.showInfo = False
    app.animT = 0
    app.hover = None
    app.cursorBlink = 0
    app.busy = False
    app.error = None
    app.status = "Ready"
    app.exampleKey = "classic17"
    app.partitionNumber = None
    app.partitionNumberN = None
    app.f_lambda = 0
    app.prodHooks = 1
    _install_controls(app)
    aio.run(_analyze(app, app.partition))

def onStep(app):
    if app.animT < 1.0:
        app.animT = min(1.0, app.animT + 0.10)
    app.cursorBlink = (app.cursorBlink + 1) % 60
    if app.partition:
        max_len = max(app.partition)
        rows = len(app.partition)
        scale = min(1.0, 520 / max(1, max_len * 52), 380 / max(1, rows * 52))
        target = max(28, min(48, int(44 * scale)))
        app.cellSize = int(app.cellSize * 0.88 + target * 0.12)

def onMouseMove(app, mx, my):
    app.hover = _hit_test(app, mx, my)

def onMousePress(app, mx, my):
    if app.showInfo:
        app.showInfo = False
        return
    hit = _hit_test(app, mx, my)
    if hit:
        r, c, typ = hit
        if typ == "cell" and c == app.partition[r] - 1:
            app.partition[r] -= 1
            if app.partition[r] == 0:
                app.partition.pop(r)
            app.partition = [x for x in app.partition if x > 0]
            app.partition = sorted(app.partition, reverse=True) or [1]
            aio.run(_analyze(app, app.partition))
        elif typ == "add_right":
            app.partition[r] += 1
            if r > 0 and app.partition[r] > app.partition[r - 1]:
                app.partition[r] = app.partition[r - 1]
            for j in range(r + 1, len(app.partition)):
                if app.partition[j] > app.partition[r]:
                    app.partition[j] = app.partition[r]
            aio.run(_analyze(app, app.partition))
        elif typ == "add_new_row":
            app.partition.append(1)
            aio.run(_analyze(app, app.partition))

def onKeyPress(app, key):
    if key.lower() == "i":
        app.showInfo = not app.showInfo
        return
    if key.lower() == "h":
        app.showHooks = not app.showHooks
        try:
            document["ferrers-hooks"].innerText = "Hooks ON" if app.showHooks else "Hooks OFF"
        except:
            pass
        return
    if key.lower() == "c":
        app.showConjugate = not app.showConjugate
        try:
            document["ferrers-conj"].innerText = "Conj ON" if app.showConjugate else "Conj OFF"
        except:
            pass
        return
    if key.lower() == "b":
        app.modeBoxes = not app.modeBoxes
        try:
            document["ferrers-boxes"].innerText = "Boxes" if app.modeBoxes else "Dots"
        except:
            pass
        return
    if key.lower() == "d":
        app.showDurfee = not app.showDurfee
        return
    if key == "Escape":
        app.showInfo = False
        return
    if key == "Enter":
        try:
            txt = document["ferrers-input"].value
        except:
            txt = ""
        part = _parse_partition(txt)
        if part:
            aio.run(_analyze(app, part))
        return
    if key == " ":
        keys = list(_EXAMPLES.keys())
        try:
            idx = keys.index(app.exampleKey)
        except:
            idx = 0
        nxt = keys[(idx + 1) % len(keys)]
        app.exampleKey = nxt
        label, val, desc = _EXAMPLES[nxt]
        try:
            document["ferrers-example"].value = nxt
            document["ferrers-input"].value = val
            document["ferrers-example-desc"].innerText = desc[:110]
        except:
            pass
        part = _parse_partition(val)
        if part:
            aio.run(_analyze(app, part))
        return

def _draw_rounded_rect(x, y, w, h, r, fill=None, border=None, borderWidth=1, opacity=100):
    try:
        drawRect(x, y, w, h, fill=fill, border=border, borderWidth=borderWidth, roundness=r, opacity=opacity)
    except:
        drawRect(x, y, w, h, fill=fill, border=border, borderWidth=borderWidth, opacity=opacity)

def _draw_cell_box(app, x, y, size, r, c, is_hover, is_durfee, is_ghost=False):
    if not is_ghost:
        _draw_rounded_rect(x + 3, y + 3, size, size, 9, fill=rgb(0, 0, 0), opacity=14)
    if is_ghost:
        _draw_rounded_rect(x, y, size, size, 11, fill=gradient(rgb(70, 80, 110), rgb(50, 60, 90), start="top-left"), opacity=22, border=rgb(100, 110, 150), borderWidth=1)
        return
    if is_durfee and app.showDurfee:
        fa = GOLD
        fb = rgb(200, 140, 40)
    else:
        pals = [(rgb(110, 180, 255), rgb(60, 120, 220)), (rgb(120, 220, 180), rgb(70, 170, 130)), (rgb(255, 180, 120), rgb(230, 120, 70)), (rgb(200, 150, 255), rgb(150, 90, 220)), (rgb(255, 130, 180), rgb(220, 80, 130)), (BLUE, rgb(80, 140, 200))]
        fa, fb = pals[r % len(pals)]
    if is_hover:
        _draw_rounded_rect(x, y, size, size, 12, fill=rgb(255, 255, 200), opacity=92, border=rgb(255, 255, 255), borderWidth=2)
        _draw_rounded_rect(x + 1, y + 1, size - 2, size - 2, 11, fill=gradient(fa, fb, start="top"), opacity=98)
    else:
        _draw_rounded_rect(x, y, size, size, 11, fill=gradient(fa, fb, start="top-left"), opacity=94, border=rgb(255, 255, 255), borderWidth=1)
        _draw_rounded_rect(x + 4, y + 4, size * 0.38, size * 0.24, 5, fill=rgb(255, 255, 255), opacity=32)

def _draw_cell_dot(app, x, y, size, r, c, is_hover, is_durfee):
    cx = x + size // 2
    cy = y + size // 2
    rr = size // 2 - 3
    drawCircle(cx + 2, cy + 3, rr, fill=rgb(0, 0, 0), opacity=14)
    cols = [rgb(120, 190, 255), rgb(140, 230, 190), rgb(255, 190, 130), rgb(210, 160, 255), rgb(255, 140, 190)]
    c1 = GOLD if (is_durfee and app.showDurfee) else cols[r % len(cols)]
    drawCircle(cx, cy, rr, fill=c1, border=rgb(255, 255, 255), borderWidth=1, opacity=92)
    drawCircle(cx - rr * 0.28, cy - rr * 0.28, rr * 0.36, fill=rgb(255, 255, 255), opacity=42)
    if is_hover:
        drawCircle(cx, cy, rr + 5, fill=None, border=rgb(255, 255, 150), borderWidth=2, opacity=75)

def _draw_info_overlay(app):
    drawRect(0, 0, app.width, app.height, fill=rgb(8, 10, 18), opacity=88)
    px = 60
    py = 50
    pw = app.width - 120
    ph = app.height - 100
    _draw_rounded_rect(px, py, pw, ph, 18, fill=gradient(rgb(20, 24, 38), rgb(28, 32, 52), start="top"), opacity=98, border=rgb(80, 90, 130), borderWidth=1)
    drawLabel("Ferrers Diagrams — Partition Geometry", px + pw // 2, py + 36, size=26, fill=rgb(235, 240, 255), bold=True)
    drawLabel("Pyodide WASM · Conjugate · Durfee · Hooks", px + pw // 2, py + 66, size=16, fill=MINT, bold=True)
    lines = [
        "USAGE:",
        "  from browser import document, aio",
        "  from extensions.pyodide import partition_stats",
        "",
        "  async def _analyze(app, part):",
        "      result = await partition_stats(part)",
        "      app.conjugate = result['conj']",
        "      app.partitionNumber = result['p_n']",
        "      app.f_lambda = result['f_lambda']",
        "",
        "  def onAppStart(app):",
        "      aio.run(_analyze(app, [6,4,4,2,1]))",
        "",
        "Heavy combinatorics runs in Pyodide worker, UI stays 60fps.",
        "",
        "MATHEMATICS:",
        "• Ferrers diagram: left-justified rows, λ1 ≥ λ2 ≥ ... ⊢ n",
        "• Conjugate λ': transpose, Durfee square d = max{i: λi ≥ i}",
        "• Self-conjugate ⇔ λ = λ' — symmetric",
        "• Hook length h(i,j) = λi - j + λ'j - i +1, f^λ = n! / ∏ h",
        "• p(n): # partitions of n, Euler recurrence with pentagonal numbers",
        "",
        "INTERACTION: Click row end + to add, click cell to remove, Space cycles examples",
    ]
    y = py + 100
    for line in lines:
        if y > py + ph - 30:
            break
        col = MINT if "from" in line or "await" in line or "def " in line or "import" in line else (GOLD if line.startswith("•") or "MATH" in line else rgb(210, 220, 240))
        drawLabel(line, px + 28, y, size=15, fill=col, align="left-top")
        y += 20

def redrawAll(app):
    drawRect(0, 0, app.width, app.height, fill=BG)
    for i in range(60):
        sx = (i * 137) % app.width
        sy = (i * 211) % app.height
        if sy < 280:
            continue
        alpha = (math.sin(i * 0.7 + app.animT * 0.08) * 0.3 + 0.7) * 32
        drawCircle(sx, sy, 1, fill=rgb(200, 210, 255), opacity=int(alpha))
    drawLabel("FERRERS DIAGRAM — PARTITION GEOMETRY", app.width // 2, 28, size=18, fill=INK, bold=True)
    if app.busy:
        drawLabel("Computing p(n) in Pyodide…", app.width // 2, 52, size=15, fill=GOLD)
    elif app.error:
        drawLabel(f"Error: {app.error[:70]}", app.width // 2, 52, size=15, fill=RED)
    else:
        if app.partitionNumber is not None:
            drawLabel(f"n={app.n}  λ=({','.join(map(str, app.partition))})  λ'=({','.join(map(str, app.conjugate))})  d={app.durfee}  p({app.n})={app.partitionNumber}  f^λ={app.f_lambda}", app.width // 2, 52, size=15, fill=MUTED)
    if app.showConjugate and app.conjugate:
        max_c = max(app.conjugate) if app.conjugate else 0
        cell = app.cellSize
        gap = app.cellGap
        twc = max_c * (cell + gap) - gap
        thc = len(app.conjugate) * (cell + gap) - gap
        sxc = app.diagramCenterX - twc // 2
        syc = app.diagramCenterY - thc // 2
        for r, rl in enumerate(app.conjugate):
            for c in range(rl):
                x = sxc + c * (cell + gap)
                y = syc + r * (cell + gap)
                _draw_cell_box(app, x, y, cell, r, c, False, False, is_ghost=True)
    if app.partition:
        for r, rl in enumerate(app.partition):
            for c in range(rl):
                x, y = _get_cell_pos(app, r, c)
                prog = app.animT
                delay = r * 0.05 + c * 0.02
                local = max(0, min(1, (prog - delay) * 3))
                if local <= 0:
                    continue
                sz = int(app.cellSize * (0.2 + 0.8 * local))
                ox = x + (app.cellSize - sz) // 2
                oy = y + (app.cellSize - sz) // 2
                is_h = app.hover and app.hover[0] == r and app.hover[1] == c and app.hover[2] == "cell"
                is_d = r < app.durfee and c < app.durfee
                if app.modeBoxes:
                    _draw_cell_box(app, ox, oy, sz, r, c, is_h, is_d)
                    if app.showHooks:
                        h = app.hooks[r][c] if r < len(app.hooks) and c < len(app.hooks[r]) else 0
                        drawLabel(str(h), x + app.cellSize // 2, y + app.cellSize // 2, size=16, fill=rgb(15, 20, 23), bold=True)
                else:
                    _draw_cell_dot(app, ox, oy, sz, r, c, is_h, is_d)
                    if app.showHooks:
                        h = app.hooks[r][c] if r < len(app.hooks) and c < len(app.hooks[r]) else 0
                        drawLabel(str(h), x + app.cellSize // 2, y + app.cellSize // 2 - 12, size=15, fill=INK, bold=True)
                if app.hover and app.hover[2] == "add_right" and app.hover[0] == r:
                    ax, ay = _get_cell_pos(app, r, rl)
                    _draw_rounded_rect(ax, ay, app.cellSize, app.cellSize, 11, fill=rgb(102, 224, 177), opacity=28, border=MINT, borderWidth=2)
                    drawLabel("+", ax + app.cellSize // 2, ay + app.cellSize // 2, size=22, fill=MINT, bold=True)
        if app.hover and app.hover[2] == "add_new_row":
            max_len = max(app.partition) if app.partition else 1
            cell = app.cellSize
            gap = app.cellGap
            tw = max_len * (cell + gap) - gap
            th = len(app.partition) * (cell + gap) - gap
            sx = app.diagramCenterX - tw // 2
            sy = app.diagramCenterY - th // 2
            ny = sy + len(app.partition) * (cell + gap)
            _draw_rounded_rect(sx, ny, cell, cell, 11, fill=rgb(102, 224, 177), opacity=28, border=MINT, borderWidth=2)
            drawLabel("+", sx + cell // 2, ny + cell // 2, size=22, fill=MINT, bold=True)
    rx = app.width - 240
    ry = 90
    rw = 220
    rh = 420
    _draw_rounded_rect(rx, ry, rw, rh, 14, fill=gradient(rgb(28, 32, 52), rgb(22, 26, 42), start="top"), border=rgb(70, 80, 110), borderWidth=1, opacity=96)
    drawLabel("Partition Data", rx + rw // 2, ry + 20, size=18, fill=INK, bold=True)
    y = ry + 48
    def stat_line(label, value):
        nonlocal y
        drawLabel(f"{label}:", rx + 14, y, size=15, fill=MUTED, align="left-top")
        drawLabel(str(value), rx + rw - 14, y, size=15, fill=INK, align="right-top", bold=True)
        y += 24
    if app.partition:
        stat_line("λ", f"({','.join(map(str, app.partition))})")
        stat_line("n", app.n)
        stat_line("k", len(app.partition))
        stat_line("λ'", f"({','.join(map(str, app.conjugate))})")
        stat_line("Durfee d", app.durfee)
        stat_line("Self", "Yes" if app.selfConj else "No")
        y += 8
        drawLabel("Hook lengths:", rx + 14, y, size=15, fill=MUTED, align="left-top")
        y += 22
        for r, row in enumerate(app.hooks[:5]):
            txt = " ".join(f"{h:2d}" for h in row[:7])
            drawLabel(f"r{r+1}: {txt}", rx + 14, y, size=15, fill=rgb(200, 210, 230), align="left-top")
            y += 20
        y += 8
        drawLabel("Pyodide", rx + 14, y, size=15, fill=MINT, bold=True, align="left-top")
        y += 22
        if app.busy:
            drawLabel("Computing…", rx + 14, y, size=15, fill=GOLD, align="left-top")
        else:
            if app.partitionNumber is not None:
                vs = str(app.partitionNumber)
                if len(vs) > 14:
                    vs = vs[:5] + "…" + vs[-4:] + f" ({len(str(app.partitionNumber))}d)"
                drawLabel(f"p({app.n})={vs}", rx + 14, y, size=15, fill=rgb(200, 230, 255), align="left-top")
                y += 22
                fl = str(app.f_lambda)
                if len(fl) > 14:
                    fl = fl[:5] + "…" + fl[-4:]
                drawLabel(f"f^λ={fl}", rx + 14, y, size=15, fill=rgb(160, 200, 255), align="left-top")
                y += 22
                drawLabel(f"∏h={app.prodHooks}", rx + 14, y, size=15, fill=MUTED, align="left-top")
    drawLabel("Click end + to add/remove • Space cycles • Enter parses • b/c/d/h/i", app.width // 2, app.height - 16, size=15, fill=rgb(120, 130, 160), align="center")
    if app.showInfo:
        _draw_info_overlay(app)
