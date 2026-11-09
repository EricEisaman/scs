"""
apps/top_down.py -- SCS App: realtime top-down scroller, 1050 x 700.

Realtime mp, not turn-based. Uses extensions.match (MatchGod API).
Server: https://matchgod.onrender.com

How it works:
  * join_realtime, not join_turn_based. No turn/state, no turn/action,
    no pass, no resign. min_players_per_room=1, so one player can
    play alone and others can join the same room later.
  * Movement is local and optimistic. The client moves on onStep,
    then publishes its character with PATCH character-state.
  * Collectibles are a fixed layout, shared by definition. Every
    client starts with the same 12 gems. When you touch one, you
    mark it collected locally, publish PATCH item-state with
    collected=True, and publish your new score with your character.
    The server broadcasts both on the stream, other clients apply
    them and hide that gem. No claim step: fixed-layout items are
    not server-registered, so claim would block collection.
  * Stream is EventSource. on_mp handles queued / matched.
    on_character / on_item / on_signal all feed apply_realtime,
    which accepts characters / character / items / item as a
    dict or a list, and accepts mp-wrapped payloads too.

Layout, 1050 x 700:
  Top bar (0..110): title, Name field, Join / Leave / Respawn /
  Reconnect, status, score, players.
  Game view (0..1050, 110..700): a 2000 x 1400 world, camera
  follows you, clamped to the world edges.

Controls:
  Click Name to edit, type, Backspace, Enter to Join, Esc to stop.
  WASD or arrow keys to move, 4-way only, last-pressed wins,
  so no diagonals. J Join, L Leave, when not editing a name.
  Click Join / Leave / Respawn / Reconnect.

Run it:
  http://localhost:8000/?app=top_down
"""

from scs import *
from browser import aio
from extensions.match import MatchClient


APP_WIDTH = 1050
APP_HEIGHT = 700

WORLD_W = 2000
WORLD_H = 1400
VIEW_X = 0
VIEW_Y = 110
VIEW_W = 1050
VIEW_H = 590

PLAYER_R = 14
ITEM_R = 11
SPEED = 5

NAME_RECT = (40, 56, 260, 32)
JOIN_RECT = (320, 56, 100, 32)
LEAVE_RECT = (430, 56, 100, 32)
RESPAWN_RECT = (540, 56, 110, 32)
RECONNECT_RECT = (660, 56, 130, 32)

ENVIRONMENT_NAME = 'top-down-demo'
GAME_ID = 'top-down-demo'
GAME_MODE = 'default'

PLAYER_COLORS = ['rgb(90,160,255)', 'rgb(255,120,120)',
                 'rgb(120,220,130)', 'rgb(255,210,90)',
                 'rgb(200,140,255)', 'rgb(90,220,220)',
                 'rgb(255,160,90)', 'rgb(255,120,200)']

ITEM_DEFS = [
    ('gem-0', 300, 300, 'rgb(255,215,0)'),
    ('gem-1', 700, 250, 'rgb(0,220,220)'),
    ('gem-2', 1100, 350, 'rgb(255,120,200)'),
    ('gem-3', 1500, 300, 'rgb(255,215,0)'),
    ('gem-4', 1700, 700, 'rgb(0,220,220)'),
    ('gem-5', 1300, 800, 'rgb(255,120,200)'),
    ('gem-6', 900, 1000, 'rgb(255,215,0)'),
    ('gem-7', 500, 1100, 'rgb(0,220,220)'),
    ('gem-8', 300, 800, 'rgb(255,120,200)'),
    ('gem-9', 1600, 1100, 'rgb(255,215,0)'),
    ('gem-10', 1000, 650, 'rgb(0,220,220)'),
    ('gem-11', 650, 600, 'rgb(255,120,200)'),
]


def _inside(x, y, rect):
    return rect[0] <= x <= rect[0] + rect[2] and rect[1] <= y <= rect[1] + rect[3]


def _shorten(text, limit):
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit - 3] + '...'


def _clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def _dir_for_key(key):
    if key is None:
        return None
    if key in ('up', 'down', 'left', 'right'):
        return key
    low = str(key).lower()
    if low == 'w':
        return 'up'
    if low == 's':
        return 'down'
    if low == 'a':
        return 'left'
    if low == 'd':
        return 'right'
    return None


def _color_for_id(client_id, index):
    if client_id is None:
        return PLAYER_COLORS[0]
    total = 0
    for ch in str(client_id):
        total = total + ord(ch)
    return PLAYER_COLORS[(total + index) % len(PLAYER_COLORS)]


def add_log(app, message):
    app.log.append(_shorten(message, 72))
    while len(app.log) > 7:
        app.log.pop(0)


def _camera(app):
    cam_x = _clamp(app.x - VIEW_W // 2, 0, WORLD_W - VIEW_W)
    cam_y = _clamp(app.y - VIEW_H // 2, 0, WORLD_H - VIEW_H)
    return cam_x, cam_y


def _parse_character(app, entry, fallback_id=None):
    if not isinstance(entry, dict):
        return
    # Server may nest the state: {state: {x, y, ...}} / {data: {...}}
    # / {character_state: {...}}. Unwrap so x/y/name still read.
    src = entry
    # Server broadcasts updates as a LIST: {updates: [{x, y, ...}]}
    if isinstance(entry.get('updates'), list) and len(entry['updates']) > 0 and isinstance(entry['updates'][0], dict):
        merged = {}
        merged.update(entry['updates'][0])
        merged.update(entry)
        src = merged
    else:
        for nest in ('updates', 'state', 'data', 'character_state', 'character', 'value'):
            if isinstance(entry.get(nest), dict):
                merged = {}
                merged.update(entry[nest])
                merged.update(entry)
                src = merged
                break
    cid = src.get('character_id')
    if cid is None:
        cid = src.get('characterId')
    if cid is None:
        cid = src.get('client_id')
    if cid is None:
        cid = src.get('clientId')
    if cid is None:
        cid = src.get('id')
    if cid is None:
        cid = src.get('player_id')
    if cid is None:
        cid = fallback_id
    if cid is None or cid == app.client_id:
        return
    x = src.get('x')
    y = src.get('y')
    pos = src.get('position')
    if isinstance(pos, dict):
        if x is None:
            x = pos.get('x')
        if y is None:
            y = pos.get('y')
    elif isinstance(pos, (list, tuple)) and len(pos) == 2:
        if x is None:
            x = pos[0]
        if y is None:
            y = pos[1]
    name = src.get('name')
    if name is None:
        name = src.get('display_name')
    if name is None:
        name = src.get('character_name')
    if name is None:
        name = src.get('displayName')
    if name is None:
        name = 'player'
    score = src.get('score')
    if score is None and isinstance(src.get('stats'), dict):
        score = src['stats'].get('score')
    color = src.get('color')
    old = app.players.get(cid)
    if old is None:
        old = {'x': app.x, 'y': app.y, 'name': str(name),
               'score': 0, 'color': _color_for_id(cid, len(app.players))}
        app.players[cid] = old
    if isinstance(x, (int, float)):
        old['x'] = float(x)
    if isinstance(y, (int, float)):
        old['y'] = float(y)
    old['name'] = str(name)
    if isinstance(score, (int, float)):
        old['score'] = int(score)
    if isinstance(color, str) and color != '':
        old['color'] = color


def _parse_item(app, entry, fallback_id=None):
    if not isinstance(entry, dict):
        return
    src = entry
    if isinstance(entry.get('updates'), list) and len(entry['updates']) > 0 and isinstance(entry['updates'][0], dict):
        merged = {}
        merged.update(entry['updates'][0])
        merged.update(entry)
        src = merged
    else:
        for nest in ('updates', 'state', 'data', 'item_state', 'item', 'value'):
            if isinstance(entry.get(nest), dict):
                merged = {}
                merged.update(entry[nest])
                merged.update(entry)
                src = merged
                break
    iid = src.get('item_id')
    if iid is None:
        iid = src.get('id')
    if iid is None:
        iid = fallback_id
    if iid is None or iid not in app.items:
        return
    collected = src.get('collected')
    if collected is None:
        collected = src.get('taken')
    if collected is None and src.get('state') in ('collected', 'taken', 'gone'):
        collected = True
    if collected is None and src.get('state') in ('available', 'active'):
        collected = False
    if collected is None:
        return
    app.items[iid]['collected'] = bool(collected)
    taken_by = src.get('taken_by')
    if taken_by is None:
        taken_by = src.get('collected_by')
    if taken_by is None:
        taken_by = src.get('client_id')
    if taken_by is not None:
        app.items[iid]['taken_by'] = str(taken_by)


def apply_realtime(app, signals):
    if not isinstance(signals, dict):
        return
    candidates = [signals]
    for key in ('mp', 'signals', 'state', 'room', 'data', 'realtime', 'turnState', 'turn_state', 'match', 'game_state', 'game'):
        if isinstance(signals.get(key), dict):
            candidates.append(signals[key])
            # mp may itself nest state/room/data
            for sub in ('state', 'room', 'data', 'realtime', 'turnState', 'turn_state', 'match', 'game_state'):
                if isinstance(signals[key].get(sub), dict):
                    candidates.append(signals[key][sub])
    for cand in candidates:
        chars = cand.get('characters')
        if isinstance(chars, dict):
            for key in chars:
                # dict-keyed: {client_id: {x, y, ...}} — key IS the id.
                # Old code ignored the key and dropped these.
                _parse_character(app, chars[key], fallback_id=key)
        elif isinstance(chars, list):
            for entry in chars:
                _parse_character(app, entry)
        if isinstance(cand.get('character'), dict):
            _parse_character(app, cand['character'])
        # Some servers send players/clients instead of characters.
        for alt in ('players', 'clients', 'character_states'):
            alt_chars = cand.get(alt)
            if isinstance(alt_chars, dict):
                for key in alt_chars:
                    _parse_character(app, alt_chars[key], fallback_id=key)
            elif isinstance(alt_chars, list):
                for entry in alt_chars:
                    _parse_character(app, entry)
        items = cand.get('items')
        if isinstance(items, dict):
            for key in items:
                _parse_item(app, items[key], fallback_id=key)
        elif isinstance(items, list):
            for entry in items:
                _parse_item(app, entry)
        if isinstance(cand.get('item'), dict):
            _parse_item(app, cand['item'])


def apply_mp(app, mp):
    if not isinstance(mp, dict):
        return
    room = mp.get('room')
    if isinstance(room, dict):
        room_id = room.get('roomId')
        if room_id is None:
            room_id = room.get('room_id')
        if room_id is not None:
            app.room_id = room_id
    match = mp.get('match')
    if not isinstance(match, dict):
        return
    if match.get('roomId') is not None:
        app.room_id = match['roomId']
    if match.get('room_id') is not None:
        app.room_id = match['room_id']
    status = match.get('status')
    if status == 'queued':
        app.match_status = 'queued'
        pos = match.get('queuePosition')
        if pos is None:
            pos = match.get('queue_position')
        app.queue_position = pos
        app.status = 'Queued (position ' + str(pos) + ') - waiting...'
    elif status in ('matched', 'ready'):
        if app.match_status != 'matched':
            app.status = 'Matched! Room ' + str(app.room_id or '')
        app.match_status = 'matched'
    elif status == 'finished':
        app.match_status = 'finished'
        app.status = 'Game over.'


async def do_publish_character(app):
    if app.client is None:
        return
    if app.publishing:
        return
    app.publishing = True
    try:
        result = await app.client.publish_character_state({
            'x': int(app.x), 'y': int(app.y),
            'name': app.name, 'score': app.score,
            'color': app.my_color})
        add_log(app, 'pub ok: ' + _shorten(str(result), 60))
    except Exception as err:
        add_log(app, 'publish: ' + str(err))
    app.publishing = False


async def do_collect(app, item_id):
    item = app.items.get(item_id)
    if item is None or item['collected']:
        return
    if item_id in app.collecting:
        return
    app.collecting.add(item_id)
    item['collected'] = True
    item['taken_by'] = app.client_id or 'you'
    app.score = app.score + 1
    add_log(app, 'collected ' + str(item_id) + ' - score ' + str(app.score))
    if app.client is not None:
        try:
            await app.client.publish_item_state({
                'item_id': item_id, 'x': int(item['x']), 'y': int(item['y']),
                'collected': True, 'taken_by': app.client_id})
        except Exception as err:
            add_log(app, 'item publish: ' + str(err))
        await do_publish_character(app)
    app.collecting.discard(item_id)


async def do_join(app):
    if app.joining or app.client is not None:
        return
    app.joining = True
    app.status = 'Joining...'
    name = app.name or 'player'

    def _on_mp(mp):
        apply_mp(app, mp)

    def _on_character(signals):
        apply_realtime(app, signals)

    def _on_item(signals):
        apply_realtime(app, signals)

    def _on_signal(signals):
        if isinstance(signals, dict):
            if app.debug_signals < 10:
                app.debug_signals = app.debug_signals + 1
                add_log(app, 'signal keys: ' + _shorten(str(list(signals.keys())), 60))
                if isinstance(signals.get('mp'), dict):
                    add_log(app, 'mp keys: ' + _shorten(str(list(signals['mp'].keys())), 60))
            if 'characters' in signals or 'items' in signals or 'mp' in signals:
                apply_realtime(app, signals)

    def _on_open():
        app.stream_open = True
        app.stream_status = 'Stream: open'
        add_log(app, 'stream open')

    def _on_close():
        app.stream_open = False
        app.stream_status = 'Stream: closed - Reconnect to reopen'
        add_log(app, 'stream closed')

    client = MatchClient(on_mp=_on_mp, on_character=_on_character,
                         on_item=_on_item, on_signal=_on_signal,
                         on_stream_open=_on_open,
                         on_stream_close=_on_close)
    app.client = client
    try:
        data = await client.join_realtime(
            environment_name=ENVIRONMENT_NAME,
            character_name=name,
            game_id=GAME_ID,
            display_name=name,
            skill=None,
            game_mode=GAME_MODE,
            max_players_per_room=8,
            min_players_per_room=1,
            requires_matchmaking=False)
        app.client_id = client.client_id
        app.session_id = client.session_id
        app.room_id = client.room_id
        app.match_status = client.match_status
        app.queue_position = client.queue_position
        app.my_color = _color_for_id(app.client_id, 0)
        if client.match_status == 'queued':
            app.status = 'Queued (position ' + str(client.queue_position) + ') - waiting...'
        else:
            app.status = 'Matched! Room ' + str(app.room_id or '')
        add_log(app, 'joined: ' + _shorten(str(data), 100))
        client.connect_stream()
        await do_publish_character(app)
    except Exception as err:
        add_log(app, 'join failed: ' + str(err))
        app.status = 'Join failed - see log.'
        app.client = None
    app.joining = False


async def do_leave(app):
    if app.client is not None:
        try:
            await app.client.leave()
        except Exception as err:
            add_log(app, 'leave: ' + str(err))
    app.client = None
    app.client_id = None
    app.session_id = None
    app.room_id = None
    app.match_status = None
    app.queue_position = None
    app.players = {}
    app.stream_open = False
    app.stream_status = 'Stream: closed'
    app.status = 'Left - still moving locally.'


async def do_respawn(app):
    app.x = WORLD_W // 2
    app.y = WORLD_H // 2
    app.held = set()
    app.last_dir = None
    add_log(app, 'respawned')
    await do_publish_character(app)


async def do_reconnect(app):
    if app.client is None:
        return
    try:
        app.client.connect_stream()
    except Exception as err:
        add_log(app, 'reconnect: ' + str(err))
        return
    await do_publish_character(app)


def onAppStart(app):
    app.background = gradient(rgb(18, 18, 20), rgb(30, 34, 48), start='top')
    app.stepsPerSecond = 30
    app.name = 'player'
    app.focus = 'name'
    app.client = None
    app.client_id = None
    app.session_id = None
    app.room_id = None
    app.match_status = None
    app.queue_position = None
    app.x = WORLD_W // 2
    app.y = WORLD_H // 2
    app.held = set()
    app.last_dir = None
    app.score = 0
    app.my_color = PLAYER_COLORS[0]
    app.players = {}
    app.items = {}
    for iid, ix, iy, icol in ITEM_DEFS:
        app.items[iid] = {'x': ix, 'y': iy, 'color': icol,
                          'collected': False, 'taken_by': None}
    app.collecting = set()
    app.log = []
    app.step = 0
    app.status = 'Not joined - move locally, Join to play together.'
    app.stream_open = False
    app.stream_status = 'Stream: closed'
    app.joining = False
    app.publishing = False
    app.debug_signals = 0
    add_log(app, 'WASD / arrows to move. Touch a gem to collect it.')


def onStep(app):
    app.step = app.step + 1
    moved = False
    if app.last_dir is not None and app.last_dir in app.held:
        if app.last_dir == 'up':
            app.y = app.y - SPEED
        elif app.last_dir == 'down':
            app.y = app.y + SPEED
        elif app.last_dir == 'left':
            app.x = app.x - SPEED
        elif app.last_dir == 'right':
            app.x = app.x + SPEED
        moved = True
    app.x = _clamp(app.x, PLAYER_R, WORLD_W - PLAYER_R)
    app.y = _clamp(app.y, PLAYER_R, WORLD_H - PLAYER_R)
    if moved:
        for iid in list(app.items.keys()):
            item = app.items[iid]
            if item['collected']:
                continue
            dx = app.x - item['x']
            dy = app.y - item['y']
            if dx * dx + dy * dy < (PLAYER_R + ITEM_R + 4) * (PLAYER_R + ITEM_R + 4):
                aio.run(do_collect(app, iid))
    if app.client is not None and moved and app.step % 3 == 0:
        aio.run(do_publish_character(app))


def onMousePress(app, x, y):
    x = int(x)
    y = int(y)
    if _inside(x, y, NAME_RECT):
        app.focus = 'name'
        return
    if _inside(x, y, JOIN_RECT):
        app.focus = None
        if app.client is None and not app.joining:
            aio.run(do_join(app))
        return
    if _inside(x, y, LEAVE_RECT):
        app.focus = None
        if app.client is not None:
            aio.run(do_leave(app))
        return
    if _inside(x, y, RESPAWN_RECT):
        app.focus = None
        aio.run(do_respawn(app))
        return
    if _inside(x, y, RECONNECT_RECT):
        app.focus = None
        if app.client is not None:
            aio.run(do_reconnect(app))
        return
    app.focus = None


def onKeyPress(app, key):
    if key == 'escape':
        app.focus = None
        return
    if key == 'enter':
        if app.client is None and not app.joining:
            aio.run(do_join(app))
        return
    if app.focus == 'name':
        if key == 'backspace':
            app.name = app.name[:-1]
        elif key == 'space':
            if len(app.name) < 16:
                app.name = app.name + ' '
        elif len(key) == 1 and (key.isalnum() or key in '-_'):
            if len(app.name) < 16:
                app.name = app.name + key
        return
    direction = _dir_for_key(key)
    if direction is not None:
        app.held.add(direction)
        app.last_dir = direction
        return
    if key == 'j' or key == 'J':
        if app.client is None and not app.joining:
            aio.run(do_join(app))
    elif key == 'l' or key == 'L':
        if app.client is not None:
            aio.run(do_leave(app))


def onKeyRelease(app, key):
    direction = _dir_for_key(key)
    if direction is None:
        return
    app.held.discard(direction)
    if app.last_dir == direction:
        if len(app.held) > 0:
            app.last_dir = sorted(app.held)[0]
        else:
            app.last_dir = None


def _draw_button(rect, label, enabled):
    x = rect[0]
    y = rect[1]
    w = rect[2]
    h = rect[3]
    if enabled:
        fill = rgb(42, 92, 170)
        border = rgb(90, 140, 220)
    else:
        fill = rgb(45, 45, 52)
        border = rgb(90, 90, 100)
    drawRect(x, y, w, h, fill=fill, border=border, borderWidth=1, roundness=6)
    drawLabel(label, x + w // 2, y + h // 2, size=14, bold=True, fill='white')


def _draw_field(rect, label, value, focused):
    drawLabel(label, rect[0], rect[1] - 8, size=12, fill=rgb(214, 224, 255), align='leftTop')
    if focused:
        fill = rgb(40, 44, 60)
        border = rgb(120, 170, 255)
    else:
        fill = rgb(30, 30, 34)
        border = rgb(68, 68, 78)
    drawRect(rect[0], rect[1], rect[2], rect[3], fill=fill, border=border, borderWidth=1, roundness=6)
    shown = value
    if focused:
        shown = value + '|'
    drawLabel(shown, rect[0] + 8, rect[1] + rect[3] // 2, size=16, fill='white', align='left')


def redrawAll(app):
    drawRect(0, 0, APP_WIDTH, VIEW_Y, fill=rgb(18, 18, 20))
    drawLabel('Top-Down - Realtime - MatchGod', APP_WIDTH // 2, 24, size=24, bold=True, fill='white')
    joined = app.client is not None
    _draw_field(NAME_RECT, 'Name', app.name, app.focus == 'name')
    _draw_button(JOIN_RECT, 'Join', not joined and not app.joining)
    _draw_button(LEAVE_RECT, 'Leave', joined)
    _draw_button(RESPAWN_RECT, 'Respawn', True)
    _draw_button(RECONNECT_RECT, 'Reconnect', joined)
    drawLabel(app.status, 810, 62, size=12, bold=True, fill=rgb(214, 224, 255), align='leftTop')
    drawLabel('Score: ' + str(app.score) + '  Players: ' + str(len(app.players) + 1) + '  ' + app.stream_status,
              810, 82, size=12, fill=rgb(214, 224, 255), align='leftTop')
    cam_x, cam_y = _camera(app)
    drawRect(VIEW_X, VIEW_Y, VIEW_W, VIEW_H, fill=rgb(24, 38, 28))
    for gx in range(0, WORLD_W + 1, 200):
        sx = VIEW_X + gx - cam_x
        if VIEW_X <= sx <= VIEW_X + VIEW_W:
            drawLine(sx, VIEW_Y, sx, VIEW_Y + VIEW_H, fill=rgb(40, 58, 44), lineWidth=1)
    for gy in range(0, WORLD_H + 1, 200):
        sy = VIEW_Y + gy - cam_y
        if VIEW_Y <= sy <= VIEW_Y + VIEW_H:
            drawLine(VIEW_X, sy, VIEW_X + VIEW_W, sy, fill=rgb(40, 58, 44), lineWidth=1)
    drawRect(VIEW_X + 0 - cam_x, VIEW_Y + 0 - cam_y, WORLD_W, WORLD_H,
             fill=None, border=rgb(120, 180, 130), borderWidth=3)
    for iid in sorted(app.items.keys()):
        item = app.items[iid]
        if item['collected']:
            continue
        sx = VIEW_X + item['x'] - cam_x
        sy = VIEW_Y + item['y'] - cam_y
        if sx < VIEW_X - 20 or sx > VIEW_X + VIEW_W + 20:
            continue
        if sy < VIEW_Y - 20 or sy > VIEW_Y + VIEW_H + 20:
            continue
        drawCircle(sx, sy, ITEM_R, fill=item['color'], border='white', borderWidth=2)
        drawLabel('*', sx, sy, size=14, bold=True, fill='white')
    for cid in sorted(app.players.keys()):
        other = app.players[cid]
        sx = VIEW_X + other['x'] - cam_x
        sy = VIEW_Y + other['y'] - cam_y
        if sx < VIEW_X - 30 or sx > VIEW_X + VIEW_W + 30:
            continue
        if sy < VIEW_Y - 30 or sy > VIEW_Y + VIEW_H + 30:
            continue
        drawCircle(sx, sy, PLAYER_R, fill=other['color'], border='white', borderWidth=2)
        drawLabel(other['name'], sx, sy - 24, size=12, bold=True, fill='white')
        drawLabel(str(other['score']), sx, sy + 26, size=11, fill=rgb(214, 224, 255))
    me_x = VIEW_X + app.x - cam_x
    me_y = VIEW_Y + app.y - cam_y
    drawCircle(me_x, me_y, PLAYER_R, fill=app.my_color, border='white', borderWidth=3)
    drawLabel(app.name, me_x, me_y - 24, size=13, bold=True, fill='white')
    drawLabel(str(app.score), me_x, me_y + 26, size=12, bold=True, fill='white')
    drawLabel('WASD / arrows to move. Touch a gem. Camera follows you.',
              40, APP_HEIGHT - 18, size=12, fill=rgb(214, 224, 255), align='left')
    drawLabel('Log: ' + (' | '.join(app.log[-2:]) if len(app.log) > 0 else ''),
              40, APP_HEIGHT - 36, size=11, fill=rgb(180, 190, 210), align='left')


_STARTED = False


def main():
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    runApp(width=APP_WIDTH, height=APP_HEIGHT)


main()
