"""
apps/top_down.py -- SCS App: realtime top-down scroller, 1050 x 700.

Realtime mp, not turn-based. Uses extensions.match (MatchGod API).
Server: https://matchgod.onrender.com

How it works (new MATCH protocol -- see EricEisaman/match README,
"Character state -- schema-declared" and "Client protocol"):
  * join_realtime, not join_turn_based. No turn/state, no turn/action,
    no pass, no resign. min_players_per_room=1, so one player can
    play alone and others can join the same room later.
    Direct room: requires_matchmaking=False, match_status comes
    back "ready" (not "matched"). Join also declares
    disconnection_time_sec=60 / empty_game_ttl_sec=300, AND the
    character_schema below. The first join for a game_id stores
    the schema; a later join with a different schema gets 409
    + the stored schema, and this app retries once with it.
  * Movement is local and optimistic. The client moves on onStep,
    then publishes its character with PATCH character-state.
    Canonical update is {clientId, state: {position, health,
    name, color}} -- characters use position inside state,
    ITEMS use pos (different fields, different endpoint).
    Name/colour live in state.name / state.color. There is no
    legacy wrapper, no top-level position/health/score outside
    state, no velocity / facing / animation fields. The old
    shape is rejected with 422.
  * Score is SERVER-authoritative (authority "server" in the
    schema). The client NEVER sends it and NEVER increments it
    locally when online. On collection the server increments
    it and broadcasts the updated character state with
    source "server". Own character entries are the score
    channel: this app applies score (only score) from its own
    broadcast entries and never overwrites its own position
    from its own echo. A patch that tries to send score is
    dropped (dropped_server_fields) and never broadcast.
  * Gems are SERVER-SPAWNED and server-authoritative. The client
    never invents gems once joined: the stream bootstrap carries
    the field (24 live gems, instanceId "top-down-demo:gem-N")
    and every collection is followed by a server respawn
    ("gem-25", "gem-26", ...). A gem the client has never seen
    is CREATED on arrival, never dropped -- dropping unknown ids
    was why respawns never appeared.
  * Collecting is a COLLECTION, not an update and not a claim.
    When you touch a gem you mark it collected locally, publish
    PATCH item-state with updates=[] and
    collections=[{instanceId, collectedByClientId, environment}],
    and wait for the server broadcast for your new score.
    No claim/release: server gems are owned by the server,
    claim would block collection. No publish-character for
    score: score is not a client field.
  * Heartbeat: if you stop moving you stop publishing, and the
    server evicts a client silent for disconnection_time_sec.
    onStep therefore heartbeats every ~20s (budget / 3) while
    joined. A 403 "disconnected: timeout" means re-join -- the
    old client_id is dead.
  * Stream is EventSource. The first event is a full bootstrap
    (connection, clients, characters LIST of {clientId, state,
    source}, items {updates, collections}, room, match,
    character_schema); later events are single-signal patches
    (character-state-update, item-state-update, client-joined,
    client-left, ...). extensions.match normalises both forms
    to the same canonical shape before the callbacks fire, so
    apply_realtime only ever sees characters / items / clients /
    client_left. Broadcasts are full merged states, but this
    app still treats them as partial-safe: only fields present
    overwrite the stored value.
  * Offline (not joined) the app still plays locally against a
    fixed 12-gem field, so movement/collecting can be tried
    without a server. Offline collecting DOES increment score
    locally (there is no server). Joining clears the offline
    field and replaces it with the server field, resets score
    to the server value (0), and leaving restores the offline
    field.

  Required extensions.match contract (companion update):
    - join_realtime(..., character_schema=...) must forward
      it as config.character_schema on POST /join, and surface
      a 409 character_schema_mismatch (with the stored schema)
      instead of swallowing it.
    - publish_character_state(state_dict) takes the STATE dict
      itself -- {"position": [...], "health": .., "name": ..,
      "color": ..} -- and wraps it as
      {updates: [{clientId, state: state_dict}]} on
      PATCH /character-state. Do NOT add a second "state" key
      at this call site.
    - publish_item_state(...) still takes the item form and
      wraps it as {updates: [], collections: [...]}.

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
# View ends where footer starts (652), not at 700 -- old 590px view
# overlapped the 48px footer, so player/gems at the bottom were drawn
# under the footer rect and looked like they went off-screen.
VIEW_H = APP_HEIGHT - VIEW_Y - 48

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
# New server budgets, declared on join (see match README,
# "Disconnect Time" / "Empty-game cleanup").
DISCONNECTION_TIME_SEC = 60
EMPTY_GAME_TTL_SEC = 300
# Heartbeat at budget/3: 20s at 30 steps/sec = 600 steps.
HEARTBEAT_STEPS = 600

# Character schema for this game_id -- must match the server's
# stored schema exactly (same fields, same version), or join
# gets 409. This is the top-down schema from the match README.
# position/health/name/color are client-authoritative;
# score is server-authoritative: never send it.
CHARACTER_SCHEMA = {
    'version': 1,
    'fields': {
        'position': {'type': 'vec2', 'required': True,
                     'authority': 'client', 'semantic': 'position'},
        'health': {'type': 'int', 'required': True,
                   'min': 0, 'max': 100,
                   'authority': 'client', 'semantic': 'health'},
        'score': {'type': 'int', 'authority': 'server',
                  'default': 0, 'min': 0, 'semantic': 'score'},
        'name': {'type': 'string', 'authority': 'client',
                 'semantic': 'name'},
        'color': {'type': 'string', 'authority': 'client'},
    },
}

PLAYER_COLORS = ['rgb(90,160,255)', 'rgb(255,120,120)',
                 'rgb(120,220,130)', 'rgb(255,210,90)',
                 'rgb(200,140,255)', 'rgb(90,220,220)',
                 'rgb(255,160,90)', 'rgb(255,120,200)']

# OFFLINE field only. Once joined, gems come from the server
# bootstrap / patches -- never from this list.
OFFLINE_ITEM_DEFS = [
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
# Back-compat alias: old code imported ITEM_DEFS.
ITEM_DEFS = OFFLINE_ITEM_DEFS

GEM_PALETTE = ['rgb(255,215,0)', 'rgb(0,220,220)', 'rgb(255,120,200)']


def _inside(x, y, rect):
    return rect[0] <= x <= rect[0] + rect[2] and rect[1] <= y <= rect[1] + rect[3]


def _shorten(text, limit):
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit - 3] + '...'


def _to_rgb(c):
    if not isinstance(c, str):
        return c
    s = c.strip()
    if s.startswith('rgb(') and s.endswith(')'):
        try:
            parts = s[4:-1].split(',')
            return rgb(int(float(parts[0])), int(float(parts[1])), int(float(parts[2])))
        except Exception:
            return c
    return c


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


def _spawn_for_id(client_id):
    total = 0
    for ch in str(client_id or ''):
        total = total + ord(ch)
    ox = (total % 200) - 100
    oy = ((total // 200) % 200) - 100
    return (WORLD_W // 2 + ox, WORLD_H // 2 + oy)


def _num(v):
    # Force PYTHON float: float() on a JS value (from window.JSON.parse) can
    # return the JS value unchanged -- 110 + "615" = "110615" in JS, -309 = 110306.
    # str(v) first gives a Python str, float() then gives a Python float.
    try:
        return float(str(v))
    except Exception:
        try:
            return float(v)
        except Exception:
            return 0.0


def _to_num(v):
    # Server may send positions as strings ("1000") -- coerce, don't drop.
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except Exception:
            return None
    return None


def _color_for_id(client_id, index):
    if client_id is None:
        return PLAYER_COLORS[0]
    total = 0
    for ch in str(client_id):
        total = total + ord(ch)
    return PLAYER_COLORS[(total + index) % len(PLAYER_COLORS)]


def _gem_color_for_id(iid):
    # Deterministic colour for server gems, incl. respawns
    # (gem-25, gem-26, ...) the client has never seen before.
    total = 0
    for ch in str(iid):
        total = total + ord(ch)
    return GEM_PALETTE[total % len(GEM_PALETTE)]


def _local_item_id(iid):
    """'top-down-demo:gem-1' -> 'gem-1'. Bare ids pass through."""
    if iid is None:
        return None
    s = str(iid)
    if ':' in s:
        return s.split(':', 1)[1]
    return s


def _namespaced_item_id(iid):
    """'gem-1' -> 'top-down-demo:gem-1'. Already-namespaced: unchanged."""
    if iid is None:
        return None
    s = str(iid)
    if ':' in s:
        return s
    return ENVIRONMENT_NAME + ':' + s


def _fresh_offline_items():
    out = {}
    for iid, ix, iy, icol in OFFLINE_ITEM_DEFS:
        out[iid] = {'x': ix, 'y': iy, 'color': icol,
                    'collected': False, 'taken_by': None}
    return out


def add_log(app, message):
    # CONSOLE ONLY -- never draw logs on screen. SCS print() goes to the console.
    try:
        print('[top-down] ' + str(message))
    except Exception:
        pass


def _camera(app):
    # Literals -- VIEW_W/VIEW_H globals may be corrupted in the browser.
    # View 1050x542, world 2000x1400.
    cam_x = _clamp(_num(app.x) - 525.0, 0, 950.0)
    cam_y = _clamp(_num(app.y) - 271.0, 0, 858.0)
    return cam_x, cam_y


def _state_of(entry):
    """New-protocol character entry -> its state dict.

    Canonical entry: {clientId, state: {position, health, score,
    name, color}, source, timestamp}. If a caller already
    normalised to flat state fields, the entry itself IS the
    state. State wins when both are present.
    """
    if isinstance(entry, dict) and isinstance(entry.get('state'), dict):
        return entry['state']
    if isinstance(entry, dict):
        return entry
    return {}


def _client_id_of(entry, fallback_id=None):
    if not isinstance(entry, dict):
        return fallback_id
    cid = entry.get('clientId')
    if cid is None:
        cid = entry.get('client_id')
    if cid is None:
        cid = entry.get('character_id')
    if cid is None:
        cid = entry.get('characterId')
    if cid is None:
        cid = entry.get('id')
    if cid is None:
        cid = entry.get('player_id')
    if cid is None:
        cid = entry.get('playerId')
    if cid is None:
        cid = fallback_id
    return cid


def _parse_client_name(app, entry, fallback_id=None):
    """Clients carry NAMES only. Never create a player, never touch x/y.
    Only rename a player that already exists from a real characters update."""
    if isinstance(entry, str):
        if fallback_id is not None and entry and len(entry) < 40 and fallback_id in app.players:
            app.players[fallback_id]['name'] = entry
        return
    if isinstance(entry, (list, tuple)) and len(entry) == 2 and isinstance(entry[0], (int, float)):
        return  # bare [x,y] is a character, not a client -- handled elsewhere
    if not isinstance(entry, dict):
        return
    # Unwrap one level if nested
    src = entry
    for nest in ('player', 'user', 'data'):
        if isinstance(entry.get(nest), dict) and (entry.get(nest).get('name') or entry.get(nest).get('display_name')):
            src = entry[nest]
            break
    cid = _client_id_of(src, fallback_id)
    if cid is None or cid == app.client_id:
        return
    state = _state_of(src)
    name = state.get('name')
    if name is None:
        name = state.get('display_name')
    # SERVER: clients = [{"clientId": ..., "character": "<name>", ...}] -- `character` IS the name string.
    if name is None and isinstance(src.get('character'), str) and src.get('character'):
        name = src.get('character')
    if name is None and isinstance(entry.get('character'), str) and entry.get('character'):
        name = entry.get('character')
    if name is None:
        name = src.get('name') or src.get('display_name') or src.get('character_name') or src.get('displayName') or src.get('player_name')
    if cid in app.players:
        if name is not None:
            app.players[cid]['name'] = str(name)


def _parse_self_character(app, state):
    """Own broadcast entries are the SCORE channel only.

    The server's source="server" broadcast after a collection is
    the only place our online score changes. Never overwrite our
    own position from our own echo -- local movement is the
    source of truth for x/y. Name is ours to send, not to learn.
    """
    if not isinstance(state, dict):
        return
    score = state.get('score')
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        app.score = int(score)


def _parse_character(app, entry, fallback_id=None):
    # A broadcast may bundle several updates: {updates: [{...}, ...]}.
    # Apply every one -- taking only updates[0] drops the rest.
    if isinstance(entry, dict) and isinstance(entry.get('updates'), list):
        for sub in entry['updates']:
            _parse_character(app, sub, fallback_id=fallback_id)
        return
    # Characters value may be a bare [x, y] or a JSON string, not a dict.
    if isinstance(entry, (list, tuple)) and len(entry) == 2:
        entry = {'state': {'position': [entry[0], entry[1]]}}
    if isinstance(entry, str):
        # Bare string from clients: {client_id: 'Milo'} -- name only, NOT a character.
        # Never create a player from this (that was the spawn-phantom bug).
        # Only rename if the player already exists from a real characters update.
        if fallback_id is not None and len(entry) > 0 and len(entry) < 40:
            _o = app.players.get(fallback_id)
            if _o is not None:
                _o['name'] = entry
            return
        # Otherwise it might be a JSON character string.
        try:
            import json as _j
            entry = _j.loads(entry)
        except Exception:
            return
    if not isinstance(entry, dict):
        return
    cid = _client_id_of(entry, fallback_id)
    if cid is None:
        return
    state = _state_of(entry)
    # OWN entry: score channel only. See _parse_self_character.
    if cid == app.client_id:
        _parse_self_character(app, state)
        return
    # Characters use position inside state: [x, y] (items use pos --
    # different field, different endpoint). Accept a flat
    # position on the entry itself only as a tolerance fallback
    # for a normaliser that already flattened state.
    x = None
    y = None
    pos = state.get('position')
    if pos is None:
        pos = entry.get('position')
    if pos is None:
        pos = state.get('pos')
    if isinstance(pos, (list, tuple)) and len(pos) == 2:
        x = _to_num(pos[0])
        y = _to_num(pos[1])
    elif isinstance(pos, dict):
        if x is None:
            x = _to_num(pos.get('x'))
        if y is None:
            y = _to_num(pos.get('y'))
    elif isinstance(pos, str) and ',' in pos:
        cleaned = pos.strip().strip('[]()').strip()
        parts = cleaned.split(',')
        if len(parts) > 0:
            x = _to_num(parts[0])
        if len(parts) > 1:
            y = _to_num(parts[1])
    if x is None:
        x = _to_num(state.get('x'))
    if y is None:
        y = _to_num(state.get('y'))
    # Name / colour / score live in state. Partial-safe: only
    # fields actually present overwrite the stored value.
    name = state.get('name')
    if name is None:
        name = entry.get('name')
    if name is None and isinstance(entry.get('character'), str) and entry.get('character'):
        name = entry.get('character')
    color = state.get('color')
    if color is None:
        color = entry.get('color')
    score = state.get('score')
    if score is None:
        score = entry.get('score')
    # NO POSITION = NOT A CHARACTER UPDATE (or a partial update
    # with no position). If the player already exists, apply the
    # name/score/colour it did carry; otherwise ignore -- never
    # create a spawn phantom from a name-only entry. This is the
    # fix for 'all players clustered at spawn'.
    if x is None and y is None:
        if cid in app.players:
            if name is not None:
                app.players[cid]['name'] = str(name)
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                app.players[cid]['score'] = int(score)
            if isinstance(color, str) and color != '':
                app.players[cid]['color'] = color
        return
    old = app.players.get(cid)
    if old is None:
        # No spawn placeholder: a new remote starts exactly at the position
        # in THIS packet.
        _ix = _num(x)
        _iy = _num(y)
        old = {'x': _ix, 'y': _iy, 'name': str(name) if name is not None else 'player',
               'score': 0, 'color': _color_for_id(cid, len(app.players))}
        app.players[cid] = old
    if isinstance(x, (int, float)):
        old['x'] = float(x)
    if isinstance(y, (int, float)):
        old['y'] = float(y)
    if name is not None:
        old['name'] = str(name)
    # If this update had no name, keep the one we already have (or 'player' on first sight).
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        old['score'] = int(score)
    if isinstance(color, str) and color != '':
        old['color'] = color


def _parse_item(app, entry, fallback_id=None, from_collection=False):
    """Apply one item update OR one collection to app.items.

    New server: ItemInstanceState = {instanceId ("env:gem-N"),
    pos, isCollected, collectedByClientId, environment}. A
    collection entry is {instanceId, collectedByClientId,
    environment} with NO isCollected -- it means collected=True.
    Unknown ids are CREATED (server respawns: gem-25, ...),
    never dropped -- dropping them was why respawns never
    appeared. from_collection=True forces collected=True.
    """
    if not isinstance(entry, dict):
        return
    # A bundle: {updates: [...]} / {collections: [...]} -- expand.
    if isinstance(entry.get('updates'), list) or isinstance(entry.get('collections'), list):
        for sub in entry.get('updates') or []:
            _parse_item(app, sub)
        for sub in entry.get('collections') or []:
            _parse_item(app, sub, from_collection=True)
        if isinstance(entry.get('updates'), list) or isinstance(entry.get('collections'), list):
            # If the bundle ALSO carries a single item, fall through
            # only when it has its own instanceId.
            if entry.get('instanceId') is None and entry.get('instance_id') is None and entry.get('id') is None:
                return
    src = entry
    for nest in ('data', 'item_state', 'item', 'value'):
        if isinstance(entry.get(nest), dict):
            merged = {}
            merged.update(entry[nest])
            merged.update(entry)
            src = merged
            break
    iid = src.get('instanceId')
    if iid is None:
        iid = src.get('instance_id')
    if iid is None:
        iid = src.get('item_id')
    if iid is None:
        iid = src.get('itemId')
    if iid is None:
        iid = src.get('id')
    if iid is None:
        iid = fallback_id
    _raw_iid = iid
    # Normalise to the local id the app renders with: strip the
    # "top-down-demo:" namespace, "gem-12" <- 12, "item-3" <- gem-3.
    if isinstance(iid, int):
        iid = 'gem-' + str(iid)
    elif isinstance(iid, str):
        iid = _local_item_id(iid)
        if iid.isdigit():
            iid = 'gem-' + iid
        elif iid.startswith('item-'):
            iid = 'gem-' + iid[5:]
    if iid is None:
        add_log(app, 'item patch DROPPED raw=' + _shorten(str(_raw_iid), 30))
        return
    # Position: pos is canonical ([x, y] / {x, y}); fall back to
    # position / top-level x+y.
    ix = None
    iy = None
    pos = src.get('pos')
    if pos is None:
        pos = src.get('position')
    if isinstance(pos, dict):
        _px = pos.get('x') if pos.get('x') is not None else pos.get('0')
        _py = pos.get('y') if pos.get('y') is not None else pos.get('1')
        ix = _to_num(_px)
        iy = _to_num(_py)
    elif isinstance(pos, (list, tuple)) and len(pos) == 2:
        ix = _to_num(pos[0])
        iy = _to_num(pos[1])
    elif isinstance(pos, str) and ',' in pos:
        parts = pos.strip().strip('[]()').split(',')
        if len(parts) > 0:
            ix = _to_num(parts[0])
        if len(parts) > 1:
            iy = _to_num(parts[1])
    if ix is None:
        ix = _to_num(src.get('x'))
    if iy is None:
        iy = _to_num(src.get('y'))
    # Collected: collection entries have no flag -- they ARE collected.
    collected = None
    if from_collection:
        collected = True
    else:
        collected = src.get('isCollected')
        if collected is None:
            collected = src.get('is_collected')
        if collected is None:
            collected = src.get('collected')
        if collected is None:
            collected = src.get('taken')
        if collected is None and src.get('state') in ('collected', 'taken', 'gone'):
            collected = True
        if collected is None and src.get('state') in ('available', 'active'):
            collected = False
    taken_by = src.get('collectedByClientId')
    if taken_by is None:
        taken_by = src.get('collected_by_client_id')
    if taken_by is None:
        taken_by = src.get('taken_by')
    if taken_by is None:
        taken_by = src.get('takenBy')
    if taken_by is None:
        taken_by = src.get('collected_by')
    if taken_by is None:
        taken_by = src.get('collectedBy')
    if taken_by is None:
        taken_by = src.get('client_id')
    if taken_by is None:
        taken_by = src.get('clientId')
    # CREATE unknown gems (server respawn). Default position is
    # centre -- overwritten below if the packet carried a pos.
    if iid not in app.items:
        app.items[iid] = {'x': ix if ix is not None else WORLD_W // 2,
                          'y': iy if iy is not None else WORLD_H // 2,
                          'color': _gem_color_for_id(iid),
                          'collected': False, 'taken_by': None}
        add_log(app, 'item created from server: ' + str(iid))
    if ix is not None and iy is not None:
        app.items[iid]['x'] = float(ix)
        app.items[iid]['y'] = float(iy)
    if collected is not None:
        app.items[iid]['collected'] = bool(collected)
    if taken_by is not None:
        app.items[iid]['taken_by'] = str(taken_by)


def _parse_client_left(app, entry):
    """Remove a player the server says left / timed out."""
    cid = None
    if isinstance(entry, str):
        cid = entry
    elif isinstance(entry, dict):
        cid = entry.get('clientId') or entry.get('client_id') or entry.get('characterId') or entry.get('character_id') or entry.get('id') or entry.get('player_id')
    if cid is not None and cid in app.players:
        del app.players[cid]
        add_log(app, 'player left: ' + _shorten(str(cid), 20))


def _schema_from_error(err):
    """Extract a stored character_schema from a 409 error, if present.

    MatchClient may raise a dict, a stringified dict, or an object
    with the schema on it. Returns the schema dict or None.
    """
    if isinstance(err, dict):
        if isinstance(err.get('character_schema'), dict):
            return err['character_schema']
        detail = err.get('detail')
        if isinstance(detail, dict) and isinstance(detail.get('character_schema'), dict):
            return detail['character_schema']
        return None
    if hasattr(err, 'character_schema'):
        try:
            _s = err.character_schema
            if isinstance(_s, dict):
                return _s
        except Exception:
            pass
    try:
        import json as _j
        text = str(err)
        start = text.find('{')
        if start >= 0:
            parsed = _j.loads(text[start:])
            if isinstance(parsed, dict):
                if isinstance(parsed.get('character_schema'), dict):
                    return parsed['character_schema']
                detail = parsed.get('detail')
                if isinstance(detail, dict) and isinstance(detail.get('character_schema'), dict):
                    return detail['character_schema']
    except Exception:
        pass
    return None


def apply_realtime(app, signals):
    if not isinstance(signals, dict):
        return
    # Effective schema may arrive in the bootstrap or a patch.
    # Keep it: it is what the next join must declare.
    if isinstance(signals.get('character_schema'), dict):
        app.character_schema = signals['character_schema']
    candidates = [signals]
    for key in ('mp', 'signals', 'state', 'room', 'data', 'realtime', 'turnState', 'turn_state', 'match', 'game_state', 'game'):
        if isinstance(signals.get(key), dict):
            if isinstance(signals[key].get('character_schema'), dict):
                app.character_schema = signals[key]['character_schema']
            candidates.append(signals[key])
            # mp may itself nest state/room/data
            for sub in ('state', 'room', 'data', 'realtime', 'turnState', 'turn_state', 'match', 'game_state'):
                if isinstance(signals[key].get(sub), dict):
                    if isinstance(signals[key][sub].get('character_schema'), dict):
                        app.character_schema = signals[key][sub]['character_schema']
                    candidates.append(signals[key][sub])
    for cand in candidates:
        # --- single-signal patches (already normalised by
        # extensions.match, but accept the raw names too) ---
        for _pk in ('character-state-update', 'character_state_update'):
            _v = cand.get(_pk)
            if isinstance(_v, dict):
                if isinstance(_v.get('updates'), list):
                    for _e in _v['updates']:
                        _parse_character(app, _e)
                else:
                    _parse_character(app, _v)
            elif isinstance(_v, list):
                for _e in _v:
                    _parse_character(app, _e)
        for _pk in ('item-state-update', 'item_state_update'):
            _v = cand.get(_pk)
            if isinstance(_v, dict):
                if isinstance(_v.get('updates'), list):
                    for _e in _v['updates']:
                        _parse_item(app, _e)
                if isinstance(_v.get('collections'), list):
                    for _e in _v['collections']:
                        _parse_item(app, _e, from_collection=True)
                elif 'instanceId' in _v or 'instance_id' in _v or 'item_id' in _v or 'id' in _v:
                    _parse_item(app, _v)
            elif isinstance(_v, list):
                for _e in _v:
                    _parse_item(app, _e)
        for _pk in ('client-left', 'client_left', 'clientLeft'):
            _v = cand.get(_pk)
            if isinstance(_v, dict):
                _parse_client_left(app, _v)
            elif isinstance(_v, list):
                for _e in _v:
                    _parse_client_left(app, _e)
            elif isinstance(_v, str):
                _parse_client_left(app, _v)
        for _pk in ('client-joined', 'client_joined'):
            _v = cand.get(_pk)
            if isinstance(_v, dict):
                _parse_client_name(app, _v)
            elif isinstance(_v, list):
                for _e in _v:
                    _parse_client_name(app, _e)
        # --- canonical characters ---
        chars = cand.get('characters')
        if isinstance(chars, dict):
            for key in chars:
                # dict-keyed: {client_id: {state, ...}} -- key IS the id.
                _parse_character(app, chars[key], fallback_id=key)
        elif isinstance(chars, list):
            for entry in chars:
                _parse_character(app, entry)
        _ch = cand.get('character')
        if isinstance(_ch, dict):
            _parse_character(app, _ch)
        elif isinstance(_ch, list):
            for _e in _ch:
                _parse_character(app, _e)
        for alt in ('character_states',):
            alt_chars = cand.get(alt)
            if isinstance(alt_chars, dict):
                for key in alt_chars:
                    _parse_character(app, alt_chars[key], fallback_id=key)
            elif isinstance(alt_chars, list):
                for entry in alt_chars:
                    _parse_character(app, entry)
        # 'clients' is NAMES ONLY -- never positions, never create a player.
        _clients = cand.get('clients')
        if isinstance(_clients, dict):
            for _k, _v in _clients.items():
                _parse_client_name(app, _v, fallback_id=_k)
        elif isinstance(_clients, list):
            for _e in _clients:
                _parse_client_name(app, _e, fallback_id=None)
        # 'players' -- check each entry: position? -> character, else name-only.
        _players = cand.get('players')
        if isinstance(_players, dict):
            for _k, _v in _players.items():
                if isinstance(_v, dict) and (_state_of(_v).get('position') is not None or _v.get('position') is not None or _v.get('pos') is not None or _v.get('x') is not None or _v.get('y') is not None):
                    _parse_character(app, _v, fallback_id=_k)
                else:
                    _parse_client_name(app, _v, fallback_id=_k)
        elif isinstance(_players, list):
            for _e in _players:
                if isinstance(_e, dict) and (_state_of(_e).get('position') is not None or _e.get('position') is not None or _e.get('pos') is not None or _e.get('x') is not None or _e.get('y') is not None):
                    _parse_character(app, _e)
                else:
                    _parse_client_name(app, _e, fallback_id=None)
        # --- canonical items ---
        for _ik in ('items', 'itemStates', 'item_states', 'itemStatesMap'):
            _items = cand.get(_ik)
            if isinstance(_items, dict):
                # Server shape: items = {updates: [...], collections: [...]}
                # -- NOT {item_id: entry}. Unwrap those lists first, else every
                # remote collection is dropped and gems never disappear.
                _unwrapped = False
                for _sub in ('updates', 'collections'):
                    _lst = _items.get(_sub)
                    if isinstance(_lst, list):
                        _unwrapped = True
                        for entry in _lst:
                            _parse_item(app, entry, from_collection=(_sub == 'collections'))
                if not _unwrapped:
                    for key in _items:
                        _parse_item(app, _items[key], fallback_id=key)
            elif isinstance(_items, list):
                for entry in _items:
                    _parse_item(app, entry)
        _it = cand.get('item')
        if isinstance(_it, dict):
            _parse_item(app, _it)
        elif isinstance(_it, list):
            for _e in _it:
                _parse_item(app, _e)
        # Top-level collections list (bootstrap / patch).
        _colls = cand.get('collections')
        if isinstance(_colls, list):
            for _e in _colls:
                _parse_item(app, _e, from_collection=True)
        # Game-over / synchronizer are informational here.
        if isinstance(cand.get('game_over'), dict) or isinstance(cand.get('game-over'), dict):
            app.match_status = 'finished'
            app.status = 'Game over.'


def apply_mp(app, mp):
    if not isinstance(mp, dict):
        return
    if isinstance(mp.get('character_schema'), dict):
        app.character_schema = mp['character_schema']
    room = mp.get('room')
    if isinstance(room, dict):
        room_id = room.get('roomId')
        if room_id is None:
            room_id = room.get('room_id')
        if room_id is not None:
            app.room_id = room_id
    if isinstance(mp.get('connection'), dict):
        conn = mp['connection']
        if conn.get('disconnectionTimeSec') is not None:
            try:
                app.disconnection_time_sec = float(conn['disconnectionTimeSec'])
            except Exception:
                pass
        if conn.get('isSynchronizer') is not None:
            app.is_synchronizer = bool(conn['isSynchronizer'])
    if mp.get('synchronizer') is not None:
        sync = mp['synchronizer']
        if isinstance(sync, str):
            app.is_synchronizer = (sync == app.client_id)
        elif isinstance(sync, dict):
            _sid = sync.get('clientId') or sync.get('client_id')
            if _sid is not None:
                app.is_synchronizer = (_sid == app.client_id)
    match = mp.get('match')
    if not isinstance(match, dict):
        # Direct rooms may carry status at mp level.
        if mp.get('match_status') is not None:
            match = {'status': mp.get('match_status')}
        else:
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
        # "ready" is what a direct room (requires_matchmaking=False)
        # returns -- the old code only expected "matched".
        if app.match_status != 'matched' and app.match_status != 'ready':
            app.status = 'Ready! Room ' + str(app.room_id or '')
        app.match_status = status
    elif status == 'finished':
        app.match_status = 'finished'
        app.status = 'Game over.'


async def do_publish_character(app):
    if app.client is None or app.client_id is None:
        return
    if app.publishing:
        return
    app.publishing = True
    try:
        # Argument IS the state dict. extensions.match wraps it as
        # {clientId, state: <this>} on PATCH /character-state.
        # Do NOT add a second "state" key here, and NEVER send
        # score: it is server-authoritative and would be dropped
        # (dropped_server_fields). No velocity / facing /
        # animation / legacy wrapper fields -- the schema has
        # only position, health, name, color for clients.
        result = await app.client.publish_character_state({
            'position': [int(app.x), int(app.y)],
            'health': 100,
            'name': app.name,
            'color': app.my_color})
        if isinstance(result, dict):
            dropped = result.get('dropped_server_fields')
            if dropped is None:
                dropped = result.get('droppedServerFields')
            if dropped:
                # Should not happen now that we never send score --
                # log it so a future schema change is visible.
                add_log(app, 'publish dropped server fields: ' + _shorten(str(dropped), 80))
            if result.get('_status'):
                add_log(app, 'publish ' + str(result.get('_status')) + ': ' + _shorten(str(result), 80))
    except Exception as err:
        add_log(app, 'publish: ' + str(err))
    app.publishing = False


async def do_heartbeat(app):
    if app.client is None or app.client_id is None:
        return
    try:
        res = await app.client.heartbeat()
        if isinstance(res, dict) and res.get('_status') == 403:
            # Already evicted -- the old client_id is dead. Re-join.
            add_log(app, 'heartbeat 403 disconnected -- re-join needed')
            app.status = 'Disconnected (silent too long) - press Join to re-join.'
            app.client = None
            app.client_id = None
            app.session_id = None
            app.room_id = None
            app.match_status = None
            app.players = {}
            app.items = _fresh_offline_items()
            app.server_items = False
    except Exception as err:
        add_log(app, 'heartbeat: ' + str(err))


async def do_collect(app, item_id):
    item = app.items.get(item_id)
    if item is None or item['collected']:
        return
    if app.client is not None and app.client_id is None:
        return
    if item_id in app.collecting:
        return
    app.collecting.add(item_id)
    item['collected'] = True
    item['taken_by'] = app.client_id or 'you'
    if app.client is None:
        # OFFLINE ONLY: no server, so the local increment IS the score.
        app.score = app.score + 1
        add_log(app, 'collected (offline) ' + str(item_id) + ' - score ' + str(app.score))
    else:
        # ONLINE: do NOT increment locally. The server increments
        # the server-authoritative score and broadcasts it with
        # source "server"; _parse_self_character applies it.
        # Incrementing here would double-count.
        add_log(app, 'collected ' + str(item_id) + ' - waiting for server score')
    if app.client is not None:
        try:
            # COLLECTION ONLY. No claim/release (server owns the
            # gems), no update for the same item (server drops
            # updates for server-spawned items). extensions.match
            # turns this single-item form into
            # {updates: [], collections: [...]}.
            # NO publish-character for score: score is not ours to send.
            res = await app.client.publish_item_state({
                'instanceId': _namespaced_item_id(item_id),
                'pos': [int(item['x']), int(item['y'])],
                'isCollected': True,
                'collectedByClientId': app.client_id,
                'environment': ENVIRONMENT_NAME})
            if isinstance(res, dict) and res.get('_status'):
                add_log(app, 'item publish ' + str(res.get('_status')) + ': ' + _shorten(str(res), 60))
            else:
                add_log(app, 'item pub ok: ' + _shorten(str(res), 60))
        except Exception as err:
            add_log(app, 'item publish: ' + str(err))
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
        try:
            apply_realtime(app, signals)
        except Exception as _err:
            add_log(app, 'on_character ERR: ' + str(_err))

    def _on_item(signals):
        try:
            apply_realtime(app, signals)
        except Exception as _err:
            add_log(app, 'on_item ERR: ' + str(_err))

    def _on_signal(signals):
        if isinstance(signals, dict):
            try:
                apply_realtime(app, signals)
            except Exception as _err:
                add_log(app, 'on_signal ERR: ' + str(_err))

    def _on_client_left(signals):
        try:
            apply_realtime(app, signals)
        except Exception as _err:
            add_log(app, 'on_client_left ERR: ' + str(_err))

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
                         on_client_left=_on_client_left,
                         on_stream_open=_on_open,
                         on_stream_close=_on_close)
    # Do NOT set app.client yet: onStep publishes whenever app.client is not
    # None, and client_id is still None until join_realtime returns -> server
    # 400s 'Missing X-Client-ID'. Assign only after join succeeds below.
    try:
        data = None
        schema = CHARACTER_SCHEMA
        try:
            data = await client.join_realtime(
                environment_name=ENVIRONMENT_NAME,
                character_name=name,
                game_id=GAME_ID,
                display_name=name,
                game_mode=GAME_MODE,
                max_players_per_room=8,
                min_players_per_room=1,
                requires_matchmaking=False,
                disconnection_time_sec=DISCONNECTION_TIME_SEC,
                empty_game_ttl_sec=EMPTY_GAME_TTL_SEC,
                character_schema=schema)
        except TypeError as _te:
            # Old extensions.match that does not accept
            # character_schema yet. Do NOT silently fall back to
            # an empty schema -- the server would then 422 every
            # character-state patch. Fail loudly instead.
            if 'character_schema' in str(_te):
                add_log(app, 'join needs updated extensions.match: join_realtime must accept character_schema')
                app.status = 'Join failed - update extensions.match to forward character_schema.'
                app.client = None
                app.joining = False
                return
            raise
        except Exception as _err:
            # 409 character_schema_mismatch: another client already
            # stored a different schema for this game_id. Retry
            # ONCE with the stored schema from the error.
            _text = str(_err)
            if '409' in _text or 'character_schema_mismatch' in _text or 'schema_mismatch' in _text:
                stored = _schema_from_error(_err)
                if stored is None and isinstance(data, dict):
                    stored = data.get('character_schema')
                if stored is not None:
                    add_log(app, 'join 409 schema mismatch -- retrying with stored schema')
                    app.character_schema = stored
                    data = await client.join_realtime(
                        environment_name=ENVIRONMENT_NAME,
                        character_name=name,
                        game_id=GAME_ID,
                        display_name=name,
                        game_mode=GAME_MODE,
                        max_players_per_room=8,
                        min_players_per_room=1,
                        requires_matchmaking=False,
                        disconnection_time_sec=DISCONNECTION_TIME_SEC,
                        empty_game_ttl_sec=EMPTY_GAME_TTL_SEC,
                        character_schema=stored)
                else:
                    raise
            else:
                raise
        app.client_id = client.client_id
        app.session_id = client.session_id
        app.room_id = client.room_id
        app.match_status = client.match_status
        app.queue_position = client.queue_position
        app.is_synchronizer = client.is_synchronizer
        if client.disconnection_time_sec is not None:
            app.disconnection_time_sec = client.disconnection_time_sec
        # Effective schema: prefer what the server echoed back.
        if getattr(client, 'character_schema', None) is not None:
            app.character_schema = client.character_schema
        elif isinstance(data, dict) and isinstance(data.get('character_schema'), dict):
            app.character_schema = data['character_schema']
        else:
            app.character_schema = schema
        app.client = client
        # SERVER FIELD: drop the offline gems. The bootstrap that
        # arrives on connect_stream() repopulates app.items with
        # the server's 24 gems. Keeping the offline 12 would draw
        # phantom gems the server knows nothing about.
        app.items = {}
        app.server_items = True
        app.last_heartbeat_step = app.step
        # Score is server-authoritative online: reset to the
        # server value (0). The next server broadcast (own entry,
        # source "server") is what moves it after that.
        app.score = 0
        # DO NOT reassign my_color on join -- the avatar colour is fixed at
        # onAppStart (PLAYER_COLORS[0]). Reassigning to _color_for_id(client_id)
        # made the square change colour the moment you joined.
        # KEEP EXACT POSITION: do NOT teleport to _spawn_for_id on join.
        # Where you are when you press Join IS your join position. The next
        # publish sends this exact app.x/app.y.
        add_log(app, 'join keep pos: ' + str(int(app.x)) + ',' + str(int(app.y)))
        if client.match_status == 'queued':
            app.status = 'Queued (position ' + str(client.queue_position) + ') - waiting...'
        else:
            app.status = 'Ready! Room ' + str(app.room_id or '')
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
    # Back to the offline field.
    app.items = _fresh_offline_items()
    app.server_items = False
    app.is_synchronizer = False


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
    app.is_synchronizer = False
    app.disconnection_time_sec = DISCONNECTION_TIME_SEC
    app.character_schema = CHARACTER_SCHEMA
    app.x = WORLD_W // 2
    app.y = WORLD_H // 2
    app.held = set()
    app.last_dir = None
    app.score = 0
    app.my_color = PLAYER_COLORS[0]
    app.players = {}
    app.items = _fresh_offline_items()
    app.server_items = False
    app.collecting = set()
    app.log = []
    app.step = 0
    app.last_heartbeat_step = 0
    app.status = 'Not joined - move locally, Join to play together.'
    app.stream_open = False
    app.stream_status = 'Stream: closed'
    app.joining = False
    app.publishing = False
    app.debug_signals = 0
    add_log(app, 'WASD / arrows to move. Touch a gem to collect it.')


def onStep(app):
    app.step = app.step + 1
    # Heartbeat while joined even when standing still -- otherwise
    # the server evicts a silent client after disconnection_time_sec.
    if app.client is not None and app.client_id is not None:
        if app.step - app.last_heartbeat_step >= HEARTBEAT_STEPS:
            app.last_heartbeat_step = app.step
            aio.run(do_heartbeat(app))
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
    if app.client is not None and moved:
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
    gems_on_map = 0
    for _iid in app.items:
        if not app.items[_iid].get('collected'):
            gems_on_map = gems_on_map + 1
    sync_tag = '  Sync' if getattr(app, 'is_synchronizer', False) else ''
    drawLabel('Score: ' + str(app.score) + '  Players: ' + str(len(app.players) + 1) + '  Gems: ' + str(gems_on_map) + sync_tag + '  ' + app.stream_status,
              810, 82, size=12, fill=rgb(214, 224, 255), align='leftTop')
    cam_x, cam_y = _camera(app)
    # LITERAL view origin -- do NOT use VIEW_X/VIEW_Y globals in world math.
    # The globals still log as 110231 in the browser even after float() coercion,
    # so the deployed file is either cached old code or the globals are corrupted
    # to "110" / 110000 in Brython. Literals cannot be corrupted.
    # View: x 0..1050, y 110..652 (700 - 110 - 48 = 542 tall).
    _VX = 0.0; _VY = 110.0; _VW = 1050.0; _VH = 542.0
    _cx = float(cam_x); _cy = float(cam_y)
    drawRect(_VX, _VY, _VW, _VH, fill=rgb(24, 38, 28))
    for gx in range(0, WORLD_W + 1, 200):
        sx = _VX + _num(gx) - _cx
        if _VX <= sx <= _VX + _VW:
            drawLine(sx, _VY, sx, _VY + _VH, fill=rgb(40, 58, 44), lineWidth=1)
    for gy in range(0, WORLD_H + 1, 200):
        sy = _VY + _num(gy) - _cy
        if _VY <= sy <= _VY + _VH:
            drawLine(_VX, sy, _VX + _VW, sy, fill=rgb(40, 58, 44), lineWidth=1)
    # World border, clipped to view -- old full 2000x1400 rect bled into header/footer.
    wx0 = _VX - _cx
    wy0 = _VY - _cy
    wx1 = wx0 + float(WORLD_W)
    wy1 = wy0 + float(WORLD_H)
    if _VY <= wy0 <= _VY + _VH:
        drawLine(max(_VX, wx0), wy0, min(_VX + _VW, wx1), wy0, fill=rgb(120, 180, 130), lineWidth=3)
    if _VY <= wy1 <= _VY + _VH:
        drawLine(max(_VX, wx0), wy1, min(_VX + _VW, wx1), wy1, fill=rgb(120, 180, 130), lineWidth=3)
    if _VX <= wx0 <= _VX + _VW:
        drawLine(wx0, max(_VY, wy0), wx0, min(_VY + _VH, wy1), fill=rgb(120, 180, 130), lineWidth=3)
    if _VX <= wx1 <= _VX + _VW:
        drawLine(wx1, max(_VX, wx0), wx1, min(_VY + _VH, wy1), fill=rgb(120, 180, 130), lineWidth=3)
    if app.server_items and len(app.items) == 0:
        drawLabel('Waiting for server gems...', _VX + _VW // 2, _VY + _VH // 2, size=16, bold=True, fill='white')
    for iid in sorted(app.items.keys()):
        item = app.items[iid]
        if item['collected']:
            continue
        sx = _VX + _num(item['x']) - _cx
        sy = _VY + _num(item['y']) - _cy
        # Strict view bounds -- no 20px slack into header/footer.
        if sx < _VX or sx > _VX + _VW:
            continue
        if sy < _VY or sy > _VY + _VH:
            continue
        drawCircle(sx, sy, ITEM_R, fill=_to_rgb(item['color']), border='white', borderWidth=2)
        drawLabel('*', sx, sy, size=14, bold=True, fill='white')
    # NO TIMEOUTS -- no prune. A remote stays until the server says it left.
    # Idle players don't publish when not moving, so any time-based prune
    # deletes live players (that's why Ling showed Players:1). Dead tabs
    # staying in the list is better than live players vanishing.
    # Remotes at EXACT positions, no nudge / no ring / no spread.
    def _draw_player_square(sx, sy, color, name, score, is_self):
        # Single path for self + remotes -- no divergent fill/border code.
        # Halo first: a remote stacked exactly on self still shows a white rim
        # instead of vanishing under self (the white speck in screenshots).
        if not is_self:
            drawRect(sx - PLAYER_R - 2, sy - PLAYER_R - 2, (PLAYER_R + 2) * 2, (PLAYER_R + 2) * 2, fill=_to_rgb(color), border='white', borderWidth=1)
        drawRect(sx - PLAYER_R, sy - PLAYER_R, PLAYER_R * 2, PLAYER_R * 2, fill=_to_rgb(color), border='white', borderWidth=3)
        if not is_self:
            # PROBE: tiny red centre dot. If the square's fill is transparent
            # the dot still shows. If neither shows, the loop is not running.
            drawCircle(sx, sy, 3, fill='red')
        if sy - 30 >= _VY:
            drawLabel(name, sx + 1, sy - 30 + 1, size=13 if is_self else 12, bold=True, fill='black')
            drawLabel(name, sx, sy - 30, size=13 if is_self else 12, bold=True, fill='white')
        if sy + 32 <= _VY + _VH:
            drawLabel(str(score), sx + 1, sy + 32 + 1, size=12 if is_self else 11, bold=True, fill='black')
            drawLabel(str(score), sx, sy + 32, size=12 if is_self else 11, bold=True, fill=rgb(214, 224, 255))
    me_x = _VX + _num(app.x) - _cx
    me_y = _VY + _num(app.y) - _cy
    _draw_player_square(me_x, me_y, app.my_color, app.name, app.score, True)
    for cid in sorted(app.players.keys()):
        other = app.players[cid]
        try:
            sx = int(_VX + _num(other['x']) - _cx)
            sy = int(_VY + _num(other['y']) - _cy)
            _draw_player_square(sx, sy, other['color'], other['name'], other['score'], False)
        except Exception as _derr:
            add_log(app, 'draw remote ERR ' + str(cid)[:8] + ' ' + str(_derr) + ' entry=' + _shorten(str(other), 120))
    # Footer on a solid strip -- keeps WASD hint readable over the map.
    drawRect(0, APP_HEIGHT - 48, APP_WIDTH, 48, fill=rgb(18, 18, 20))
    drawLabel('WASD / arrows to move. Touch a gem. Camera follows you.',
              40, APP_HEIGHT - 18, size=12, fill=rgb(214, 224, 255), align='left')
    # No Log: / P: on screen -- logs are console-only (see add_log).
    # Header redrawn last -- header was drawn first, so map elements at the
    # top edge could paint over it. Redrawing it here guarantees it stays on top.
    drawRect(0, 0, APP_WIDTH, VIEW_Y, fill=rgb(18, 18, 20))
    drawLabel('Top-Down - Realtime - MatchGod', APP_WIDTH // 2, 24, size=24, bold=True, fill='white')
    _draw_field(NAME_RECT, 'Name', app.name, app.focus == 'name')
    _draw_button(JOIN_RECT, 'Join', not joined and not app.joining)
    _draw_button(LEAVE_RECT, 'Leave', joined)
    _draw_button(RESPAWN_RECT, 'Respawn', True)
    _draw_button(RECONNECT_RECT, 'Reconnect', joined)
    drawLabel(app.status, 810, 62, size=12, bold=True, fill=rgb(214, 224, 255), align='leftTop')
    drawLabel('Score: ' + str(app.score) + '  Players: ' + str(len(app.players) + 1) + '  Gems: ' + str(gems_on_map) + sync_tag + '  ' + app.stream_status,
              810, 82, size=12, fill=rgb(214, 224, 255), align='leftTop')


_STARTED = False


def main():
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    runApp(width=APP_WIDTH, height=APP_HEIGHT)


main()
