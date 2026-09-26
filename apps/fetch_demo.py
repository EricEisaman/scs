# apps/fetch_demo.py - FIXED v0.3.1 - NO local imports in async
from scs import *
from extensions.fetch import fetch_json
from browser import aio, window
import json as py_json

__version__ = "0.3.1-no-local-import"
__build__ = "2026-09-26-no-local-import-anywhere"

try:
    window.console.log("[fetch_demo] SIMPLE README VERSION - NO LOCAL IMPORTS")
except:
    pass

def parse_poem(raw):
    if isinstance(raw, list):
        data = raw[0]
    else:
        data = raw
    try:
        title = data.get("title", "Untitled") if isinstance(data, dict) else data["title"]
    except:
        try:
            title = getattr(data, "title", "Untitled")
        except:
            title = "Untitled"
    try:
        author = data.get("author", "Unknown") if isinstance(data, dict) else data["author"]
    except:
        try:
            author = getattr(data, "author", "Unknown")
        except:
            author = "Unknown"
    try:
        lines = data.get("lines", []) if isinstance(data, dict) else data["lines"]
    except:
        try:
            lines = getattr(data, "lines", [])
        except:
            lines = []
    return {"title": title, "author": author, "lines": lines}

async def load_poem(app):
    app.loading = True
    try:
        data = await fetch_json("https://poetrydb.org/random")
        app.poem = parse_poem(data)
    except Exception as e:
        try:
            window.console.error("[fetch_demo] load failed", e)
        except:
            pass
        app.poem = {"title": "Error", "author": "PoetryDB", "lines": [str(e)[:200]]}
    app.loading = False

def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.background = gradient(rgb(15, 17, 21), rgb(26, 29, 36), start="top")
    app.loading = True
    app.poem = {"title": "", "author": "", "lines": []}
    aio.run(load_poem(app))

def onMousePress(app, x, y):
    aio.run(load_poem(app))

def onKeyPress(app, key):
    if key.lower() in ("r", " ", "space"):
        aio.run(load_poem(app))

def redrawAll(app):
    try:
        drawRect(0, 0, app.width, app.height, fill=app.background)
    except:
        pass
    if getattr(app, "loading", False):
        drawLabel("Loading poem...", app.width//2, app.height//2, size=20, fill=rgb(255,255,255))
    else:
        poem = getattr(app, "poem", None)
        if not poem:
            drawLabel("No poem", app.width//2, app.height//2, size=20)
            return
        drawLabel(poem.get("title", "Untitled"), app.width//2, 80, size=24, bold=True, fill=rgb(255,235,100))
        drawLabel("by " + poem.get("author", ""), app.width//2, 110, size=14, fill=rgb(200,220,255))
        y = 150
        lines = poem.get("lines", [])
        # Use simple for loop, no range(len()) complex that might trigger resolve_local in sync is okay, but keep safe
        count = 0
        for line in lines:
            if count >= 20:
                break
            drawLabel(str(line), app.width//2, y, size=12, fill=rgb(220,220,220))
            y += 22
            count += 1
        drawLabel("Press R / SPACE / Click for new poem", app.width//2, app.height-30, size=12, fill=rgb(150,150,150))
        drawLabel("v0.3.1 NO LOCAL IMPORTS", app.width//2, app.height-15, size=8, fill=rgb(100,255,100))

def run():
    try:
        runApp(1050, 700)
    except Exception as e:
        try:
            window.console.error("[fetch_demo] runApp failed", e)
        except:
            pass

run()
