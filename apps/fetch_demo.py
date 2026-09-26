# apps/fetch_demo.py - DIRECT window.fetch - old working method
from scs import *
from browser import window, aio
import json as py_json

__version__ = "0.2.2-direct"
__build__ = "2026-09-26-direct-window-fetch"

try:
    window.console.log("[fetch_demo] DIRECT window.fetch version")
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
    try:
        window.console.log("[fetch_demo] load_poem direct window.fetch")
        # Direct window.fetch - old working method, no extensions.fetch
        js_resp = await window.fetch("https://poetrydb.org/random")
        last_status = f"fetch status {js_resp.status} ok={js_resp.ok}"
        if not js_resp.ok:
            raise RuntimeError(f"HTTP {js_resp.status}")
        js_data = await js_resp.json()
        # One-shot conversion at boundary
        try:
            text = window.JSON.stringify(js_data)
            data = py_json.loads(text)
        except Exception as e:
            window.console.error("[fetch_demo] conversion failed, using js_data directly", e)
            data = js_data

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
                # JS object access
                try:
                    poem_title = item["title"] if "title" in item else getattr(item, "title", "Untitled")
                except:
                    poem_title = str(getattr(item, "title", "Untitled"))
                try:
                    poem_author = item["author"] if "author" in item else getattr(item, "author", "Unknown")
                except:
                    poem_author = str(getattr(item, "author", "Unknown"))
                try:
                    lines = item["lines"] if "lines" in item else getattr(item, "lines", [])
                except:
                    lines = []
            if isinstance(lines, list):
                poem_text = "\n".join(lines[:25])
            else:
                try:
                    # JS array
                    poem_text = "\n".join([str(lines[i]) for i in range(len(lines))][:25])
                except:
                    poem_text = str(lines)[:800]
        except Exception as e:
            poem_text = str(item)[:800]
            window.console.error("[fetch_demo] parse failed", e)
        loading = False
        error_msg = ""
    except Exception as e:
        loading = False
        error_msg = f"Direct fetch failed: {str(e)[:200]} | {last_status}"
        try:
            window.console.error("[fetch_demo] direct fetch failed", e)
        except:
            pass
        # Fallback - NO random import inside async, use first fallback
        try:
            fb = FALLBACK_POEMS[0]
            poem_title = fb["title"] + " (fallback - PoetryDB failed)"
            poem_author = fb["author"]
            poem_text = "\n".join(fb["lines"])
        except:
            poem_text = f"Failed: {error_msg}"

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
        drawLabel("Fetch Demo - PoetryDB DIRECT", app.width//2, 40, size=24, fill=rgb(255,255,255), bold=True)
        if loading:
            drawLabel("Loading...", app.width//2, app.height//2, size=20, fill=rgb(200,200,255))
            drawLabel(last_status[:80], app.width//2, app.height//2 + 30, size=10, fill=rgb(150,150,150))
        elif error_msg and "fallback" in poem_title.lower():
            drawLabel("PoetryDB failed - fallback:", app.width//2, 80, size=14, fill=rgb(255,150,100))
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
        drawLabel("v0.2.2 DIRECT window.fetch - old working", app.width//2, app.height-15, size=8, fill=rgb(100,255,100))
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
