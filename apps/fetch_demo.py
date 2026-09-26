# apps/fetch_demo.py - v3.0.21 FIX JSON + fallback poem
from scs import *
from extensions.fetch import fetch_json
from browser import aio, window

def parse_poem(raw):
    if isinstance(raw, list):
        data = raw[0]
    else:
        data = raw
    try:
        title = data["title"]
    except:
        try:
            title = getattr(data, "title", "Untitled")
        except:
            title = "Untitled"
    try:
        author = data["author"]
    except:
        try:
            author = getattr(data, "author", "Unknown")
        except:
            author = "Unknown"
    try:
        lines = data["lines"]
    except:
        try:
            lines = getattr(data, "lines", [])
        except:
            lines = []
    return {"title": title, "author": author, "lines": lines}

async def load_poem(app):
    app.loading = True
    try:
        window.console.log("[fetch_demo] fetching poetrydb")
        data = await fetch_json("https://poetrydb.org/random")
        app.poem = parse_poem(data)
    except Exception as e:
        try:
            window.console.error("[fetch_demo] load failed", str(type(e)), str(e))
        except:
            pass
        app.poem = {"title": "The Road Not Taken (fallback)", "author": "Robert Frost - PoetryDB error: " + str(e)[:60], "lines": ["Two roads diverged in a yellow wood,", "And sorry I could not travel both", "Press R to retry", str(e)[:80]]}
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
    if getattr(app, "loading", False):
        drawLabel("Loading poem...", app.width//2, app.height//2, size=20, fill=rgb(255,255,255))
    else:
        poem = getattr(app, "poem", {})
        drawLabel(poem.get("title", "Untitled"), app.width//2, 80, size=24, bold=True, fill=rgb(255,235,100))
        drawLabel("by " + poem.get("author", ""), app.width//2, 110, size=14, fill=rgb(200,220,255))
        y = 150
        for line in poem.get("lines", [])[:20]:
            drawLabel(str(line), app.width//2, y, size=12, fill=rgb(220,220,220))
            y += 22
        drawLabel("Press R / SPACE / Click for new poem", app.width//2, app.height-30, size=12, fill=rgb(150,150,150))
        drawLabel("v3.0.21 FIX JSON scientific notation", app.width//2, app.height-15, size=8, fill=rgb(100,255,100))

runApp(1050, 700)
