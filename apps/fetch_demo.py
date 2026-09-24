# apps/fetch_demo.py
from scs import *
from extensions.fetch import fetch_json, FetchError
from browser import aio
import random

print("fetch_demo: scs imported, extensions.fetch imported")

def parse_poem(raw):
    print(f"parse_poem: raw type={type(raw)}")
    try:
        print(f"parse_poem: raw str={str(raw)[:800]}")
    except:
        pass
    try:
        if isinstance(raw, list) and len(raw) > 0:
            print(f"parse_poem: raw is list len {len(raw)}, taking [0]")
            data = raw[0]
            print(f"parse_poem: data type={type(data)}, keys={list(data.keys())[:10] if isinstance(data, dict) else 'not dict'}")
        else:
            print(f"parse_poem: raw is not list, using raw as data")
            data = raw
        # Brython JS objects may not have .get, use dict access
        if isinstance(data, dict):
            title = data.get('title', 'Untitled')
            author = data.get('author', 'Unknown')
            lines = data.get('lines', [])
            print(f"parse_poem: got via .get title={title}")
        else:
            # JS object from window.fetch().json() may be JS dict-like
            try:
                title = data['title']
                author = data['author']
                lines = data['lines']
                print(f"parse_poem: got via [] title={title}")
            except Exception as e2:
                print(f"parse_poem: [] access failed {e2}, trying getattr")
                title = getattr(data, 'title', 'Untitled')
                author = getattr(data, 'author', 'Unknown')
                lines = getattr(data, 'lines', [])
        if not isinstance(lines, list):
            lines = [str(lines)]
        print(f"parse_poem: success title={title} author={author} lines={len(lines)}")
        return {'title': title, 'author': author, 'lines': lines}
    except Exception as e:
        import traceback
        print(f"parse_poem exception: {e}")
        traceback.print_exc()
        return {'title': 'Parse Error', 'author': str(e), 'lines': [str(raw)[:300]]}

async def load_poem(app):
    print("load_poem called")
    app.loading = True
    app.error = None
    app.statusText = "Fetching poem..."
    try:
        data = await fetch_json('https://poetrydb.org/random')
        print(f"load_poem: fetch_json returned type={type(data)}")
        try:
            print(f"load_poem: data preview={str(data)[:600]}")
        except:
            pass
        parsed = parse_poem(data)
        app.poem = parsed
        app.titleText = parsed['title']
        app.authorText = parsed['author']
        app.lines = parsed['lines']
        app.loading = False
        app.statusText = f"Loaded: {parsed['title']} by {parsed['author']}"
        print(f"load_poem: done {parsed['title']}")
    except Exception as e:
        import traceback
        print(f"load_poem failed: {e}")
        traceback.print_exc()
        app.error = f"Error: {e}"
        app.loading = False
        app.statusText = app.error

def onAppStart(app):
    print("onAppStart called")
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 30
    app.poem = None
    app.titleText = ""
    app.authorText = ""
    app.lines = []
    app.loading = True
    app.error = None
    app.statusText = "Loading..."
    app.background = gradient(rgb(15, 17, 21), rgb(26, 29, 36), start='top')
    aio.run(load_poem(app))

def onKeyPress(app, key):
    if key == 'space' or key == 'r' or key == 'n':
        aio.run(load_poem(app))

def onMousePress(app, mouseX, mouseY):
    aio.run(load_poem(app))

def redrawAll(app):
    drawRect(0, 0, app.width, app.height, fill=app.background)
    drawLabel("extensions.fetch demo", app.width//2, 30, size=22, fill=rgb(200,210,230), bold=True)
    drawLabel("PoetryDB.org  •  SPACE / R / Click", app.width//2, 55, size=12, fill=rgb(120,130,150))
    if app.loading:
        drawLabel("Loading poem...", app.width//2, app.height//2, size=20, fill=rgb(76,110,245), bold=True)
        drawLabel(app.statusText, app.width//2, app.height//2 + 30, size=12, fill=rgb(150,160,180))
        return
    if app.error:
        drawLabel("Failed", app.width//2, 120, size=18, fill='red', bold=True)
        drawLabel(app.error, app.width//2, 150, size=12, fill=rgb(200,150,150))
        drawLabel("Press SPACE", app.width//2, 180, size=14, fill=rgb(180,180,200))
        return
    if app.poem is None:
        return
    drawLabel(app.titleText, app.width//2, 110, size=24, fill=rgb(235,240,255), bold=True)
    drawLabel(f"by {app.authorText}", app.width//2, 140, size=14, fill=rgb(180,190,210), italic=True)
    y = 190
    for i, line in enumerate(app.lines):
        if y > app.height - 40:
            break
        drawLabel(line, app.width//2, y, size=14, fill=rgb(210,220,235))
        y += 22
    drawLabel(f"{len(app.lines)} lines", app.width//2, app.height - 20, size=11, fill=rgb(100,110,130))
