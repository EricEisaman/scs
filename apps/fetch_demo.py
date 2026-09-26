# apps/fetch_demo.py - v0.2.1 FIXED - no local import + robust fetch + fallback
from scs import *
from browser import window, aio
from extensions.fetch import fetch_json, fetch_text, FetchError
import json as py_json

__version__ = "0.2.1-fixed-robust"
__build__ = "2026-09-26-robust-fetch"

try:
    window.console.log("[fetch_demo] scs imported, extensions.fetch imported - FIXED top-level only v0.2.1")
except:
    pass

poem_text = "Loading..."
poem_title = ""
poem_author = ""
loading = True
error_msg = ""
last_status = ""

FALLBACK_POEMS = [
    {"title": "The Road Not Taken", "author": "Robert Frost", "lines": ["Two roads diverged in a wood, and I—", "I took the one less traveled by,", "And that has made all the difference."]},
    {"title": "Ozymandias", "author": "Percy Bysshe Shelley", "lines": ["My name is Ozymandias, King of Kings;", "Look on my Works, ye Mighty, and despair!"]},
]

async def load_poem(app=None):
    global poem_text, poem_title, poem_author, loading, error_msg, last_status
    loading = True
    error_msg = ""
    last_status = ""
    try:
        window.console.log("[fetch_demo] load_poem called - trying PoetryDB")
        # Try primary endpoint
        data = None
        try:
            data = await fetch_json("https://poetrydb.org/random")
            last_status = "PoetryDB OK"
        except Exception as e1:
            try:
                window.console.warn("[fetch_demo] PoetryDB failed, trying alternative", str(e1))
                last_status = f"PoetryDB fail: {e1}"
                # Try with fetch_text then parse
                txt = await fetch_text("https://poetrydb.org/random")
                data = py_json.loads(txt)
                last_status += " - text fallback OK"
            except Exception as e2:
                last_status += f" | text fail: {e2}"
                # Use fallback poem
                raise e2

        # Normalize data
        if isinstance(data, list) and len(data) > 0:
            item = data[0]
        else:
            item = data

        try:
            if isinstance(item, dict):
                poem_title = item.get("title", "Untitled")
                poem_author = item.get("author", "Unknown")
                lines = item.get("lines", [])
            else:
                poem_title = getattr(item, "title", "Untitled")
                poem_author = getattr(item, "author", "Unknown")
                lines = getattr(item, "lines", [])
            if isinstance(lines, list):
                poem_text = "\n".join(lines[:25])
            else:
                poem_text = str(lines)[:800]
        except Exception as e:
            poem_text = str(item)[:800]
            window.console.error("[fetch_demo] parse failed", e)
        loading = False
    except Exception as e:
        loading = False
        # Use fallback poem so app still shows something
        try:
            import random as _rand
            fb = _rand.choice(FALLBACK_POEMS)
            poem_title = fb["title"] + " (fallback)"
            poem_author = fb["author"]
            poem_text = "\n".join(fb["lines"])
            error_msg = f"Fetch failed, using fallback. {last_status} Err: {str(e)[:100]}"
            window.console.log("[fetch_demo] using fallback poem")
        except Exception as e2:
            error_msg = f"{last_status} | {str(e)[:200]}"
            poem_text = f"Failed: {error_msg}"
            try:
                window.console.error("[fetch_demo] load_poem failed", e, last_status)
            except:
                pass

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.background = rgb(15,15,30)
    app.stepsPerSecond = 30
    global poem_text
    poem_text = "Loading poem..."
    try:
        aio.run(load_poem(app))
    except Exception as e:
        try:
            window.console.error("[fetch_demo] aio.run failed", e)
        except:
            pass

def redrawAll(app):
    try:
        drawRect(0,0,app.width,app.height,fill=app.background)
    except:
        pass
    try:
        drawLabel("Fetch Demo - PoetryDB", app.width//2, 40, size=24, fill=rgb(255,255,255), bold=True)
        if loading:
            drawLabel("Loading...", app.width//2, app.height//2, size=20, fill=rgb(200,200,255))
            drawLabel(last_status[:80], app.width//2, app.height//2 + 30, size=10, fill=rgb(150,150,150))
        elif error_msg:
            drawLabel("Error - showing fallback:", app.width//2, 80, size=14, fill=rgb(255,150,100))
            drawLabel(error_msg[:90], app.width//2, 100, size=10, fill=rgb(255,100,100))
            drawLabel(poem_title, app.width//2, 130, size=16, fill=rgb(255,235,100), bold=True)
            drawLabel("by " + poem_author, app.width//2, 150, size=12, fill=rgb(200,220,255))
            y = 180
            for line in poem_text.split("\n")[:20]:
                drawLabel(line, app.width//2, y, size=12, fill=rgb(220,220,220))
                y += 20
        else:
            drawLabel(poem_title, app.width//2, 80, size=18, fill=rgb(255,235,100), bold=True)
            drawLabel("by " + poem_author, app.width//2, 110, size=14, fill=rgb(200,220,255))
            y = 150
            for line in poem_text.split("\n")[:25]:
                drawLabel(line, app.width//2, y, size=12, fill=rgb(220,220,220))
                y += 20
        drawLabel("Press R to reload, click to fetch new", app.width//2, app.height-30, size=12, fill=rgb(150,150,150))
        drawLabel(f"Status: {last_status[:60]}", app.width//2, app.height-50, size=8, fill=rgb(150,150,150))
        drawLabel("v3.0.18 FIXED - no $B.$is + no local import", app.width//2, app.height-15, size=8, fill=rgb(100,255,100))
    except Exception as e:
        try:
            window.console.error("[fetch_demo] redrawAll failed", e)
        except:
            pass

def onMousePress(app, x, y):
    try:
        aio.run(load_poem(app))
    except:
        pass

def onKeyPress(app, key):
    if key.lower() == 'r':
        try:
            aio.run(load_poem(app))
        except:
            pass

def run():
    try:
        runApp(1050, 700)
    except Exception as e:
        try:
            window.console.error("[fetch_demo] runApp failed", e)
        except:
            pass

run()
