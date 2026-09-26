# apps/fetch_demo.py - FIXED - top-level imports only, no local imports in async
from scs import *
from browser import window, aio
from extensions.fetch import fetch_json, FetchError
import json as py_json

__version__ = "0.2.0-fixed"
__build__ = "2026-09-26-no-local-import-async"

try:
    window.console.log("[fetch_demo] scs imported, extensions.fetch imported - FIXED top-level only")
except:
    pass

poem_text = "Loading..."
poem_title = ""
poem_author = ""
loading = True
error_msg = ""

async def load_poem(app=None):
    global poem_text, poem_title, poem_author, loading, error_msg
    loading = True
    error_msg = ""
    try:
        window.console.log("[fetch_demo] load_poem called")
        # No local imports here - fetch_json already imported at top
        data = await fetch_json("https://poetrydb.org/random")
        # data is already Python dict via one-shot conversion
        if isinstance(data, list) and len(data) > 0:
            item = data[0]
        else:
            item = data
        # item should be dict
        try:
            poem_title = item.get("title", "Untitled") if isinstance(item, dict) else getattr(item, "title", "Untitled")
            poem_author = item.get("author", "Unknown") if isinstance(item, dict) else getattr(item, "author", "Unknown")
            # lines may be list
            if isinstance(item, dict):
                lines = item.get("lines", [])
            else:
                lines = getattr(item, "lines", [])
            if isinstance(lines, list):
                poem_text = "\n".join(lines[:20])
            else:
                poem_text = str(lines)[:500]
        except Exception as e:
            poem_text = str(item)[:500]
            try:
                window.console.error("[fetch_demo] parse failed", e)
            except:
                pass
        loading = False
    except Exception as e:
        loading = False
        error_msg = str(e)
        poem_text = "Failed: " + error_msg
        try:
            window.console.error("[fetch_demo] load_poem failed", e)
        except:
            pass

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.background = rgb(15,15,30)
    app.stepsPerSecond = 30
    global poem_text
    poem_text = "Loading poem..."
    # Start async load
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
        elif error_msg:
            drawLabel("Error:", app.width//2, 80, size=16, fill=rgb(255,100,100))
            drawLabel(error_msg[:80], app.width//2, 110, size=12, fill=rgb(255,150,150))
            drawLabel(poem_text[:100], app.width//2, 140, size=12, fill=rgb(200,200,200))
        else:
            drawLabel(poem_title, app.width//2, 80, size=18, fill=rgb(255,235,100), bold=True)
            drawLabel("by " + poem_author, app.width//2, 110, size=14, fill=rgb(200,220,255))
            # Draw poem lines
            y = 150
            for line in poem_text.split("\n")[:20]:
                drawLabel(line, app.width//2, y, size=12, fill=rgb(220,220,220))
                y += 20
        drawLabel("Press R to reload, click to fetch new", app.width//2, app.height-30, size=12, fill=rgb(150,150,150))
        drawLabel("v3.0.18 NO $B.$is + NO local import async", app.width//2, app.height-15, size=8, fill=rgb(100,255,100))
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
