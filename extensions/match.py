"""
extensions.match -- SCS Extension: MatchGod multiplayer (Model-only).

Works for BOTH kinds of app:

  * TURN-BASED apps (tic-tac-toe, chess, card games, ...)
    join with requires_turn_based=True, then use
    get_turn_state() / send_turn_action() and the ``mp`` signal
    on the SSE stream. The server is authoritative: it enforces
    turns, validates the proposed state, and decides the winner.

  * NON-TURN-BASED / REALTIME apps (platformer, shared world, ...)
    join with requires_turn_based=False, then use
    publish_character_state() / publish_item_state() and the
    character / item signals on the same SSE stream. There is no
    turn_state in this mode; every client publishes its own
    state and every client receives everyone else's.

Server protocol (matchgod.onrender.com, see EricEisaman/match --
server/app/multiplayer, README "Client protocol"):

  POST  /api/multiplayer/join
        body: environment_name, character_name, game_id,
              player_id, display_name, skill, room_id, room_code,
              config (GameSessionConfig)
        returns: client_id, session_id, is_synchronizer, room_id,
                 game_id, match_status ("ready" for direct rooms,
                 "queued" for matchmaking), queue_position,
                 disconnection_time_sec, empty_game_ttl_sec,
                 character_schema (the effective schema for this
                 game_id -- what you declared, or the stored one
                 after a 409 retry).
        config.character_schema declares the shape of
        per-player state for this game_id. The FIRST join for a
        game_id stores it; a later join with a different schema
        gets 409 + the stored schema in the response detail, and
        this client retries ONCE with that stored schema (see
        MatchClient.join). An empty schema ({version: 1,
        fields: {}}) means the game sends no character state
        (e.g. tic-tac-toe). To change a schema, use a new
        game_id or wait for the old game data to expire
        (empty_game_ttl_sec, 300s).
  GET   /api/multiplayer/stream?session_id=<session_id>
        SSE / Datastar: ``datastar-patch-signals`` events whose
        data is ``signals {...}``. First event is a FULL BOOTSTRAP:
        signals.mp = {connection, clients, characters (LIST),
        items ({updates, collections}), room, custom, turnState,
        match, characterSchema}. Later events are PATCHES: a single
        signal name such as character-state-update,
        item-state-update, client-joined, client-left,
        synchronizer-changed, game-over, matchmaking-queued.
        This extension normalises both forms to the same
        canonical shape before it calls the app callbacks, so
        apps never have to know which form arrived.
  GET   /api/multiplayer/turn/state?room_id=<room_id> (turn-based)
        header: X-Client-ID. Returns { turnState / turn_state }.
  POST  /api/multiplayer/turn/action         (turn-based)
        header: X-Client-ID. Body: {room_id, action, action_type,
        payload, timestamp}. The new server reads ``action``;
        the older server reads ``action_type`` + ``payload``.
        This extension sends all of them so either server
        accepts the same call.
  POST  /api/multiplayer/turn/pass          (turn-based, new)
  POST  /api/multiplayer/turn/resign        (turn-based, new)
        Fall back to turn/action with action_type pass/resign
        when the dedicated endpoint 404s (older server).
  PATCH /api/multiplayer/character-state     (realtime)
        Protocol v1 -- SCHEMA-DECLARED. Body:
        {updates: [{clientId, state: {...}}], timestamp}.
        The ONLY universal top-level character field is
        ``clientId``. Everything else lives inside ``state``
        and must be declared in ``config.character_schema``
        on join. The working non-SCS demo (Real-time Demo /
        top-down) sends exactly this: it declares
        position (vec2, required, client), health (int 0..100,
        required, client), score (int, SERVER, default 0),
        name (string, client), color (string, client), and
        publishes {clientId, state: {position, health, name,
        color}} -- never score, never anything top-level.
        Legacy top-level fields -- position, health, velocity,
        score, metadata, pos, characterModelId, animationState,
        animationFrame, isJumping, facing, onGround -- are
        REJECTED by the server with
        422 {"detail": "unsupported character fields: ..."}.
        (An older version of this file claimed the demo sent
        those fields top-level. It does not. Do NOT "fix" this
        back to the flat shape.) Name / colour live in
        state.name / state.color when declared -- never in
        metadata, never top-level. A client patch that
        includes a server-authoritative field (e.g. score)
        has that field DROPPED, never broadcast; the response
        reports it in dropped_server_fields. Unknown fields
        are rejected (422) unless the schema opts into
        allow_unknown. Patches are partial: required-ness is
        enforced on the merged full state, not on each patch.
  PATCH /api/multiplayer/item-state          (realtime)
        Body: {updates: [...], collections: [...], timestamp}.
        An update is {instanceId, pos, isCollected,
        collectedByClientId, environment}. A collection is
        {instanceId, collectedByClientId, environment}.
        instanceId is namespaced: "<environment>:<local-id>".
        For SERVER-SPAWNED items (e.g. top-down gems) updates
        are dropped by the server -- only collections are
        accepted. So a collect sends updates=[] + collections=[...]
        and never an update for the same item. Exactly-once:
        the first valid collection wins.
  PATCH /api/multiplayer/item-authority-claim   (realtime)
  PATCH /api/multiplayer/item-authority-release (realtime)
        Body: {instanceId, reason, timestamp}. Only for
        client-owned items. NEVER claim a server-spawned gem.
  PATCH /api/multiplayer/custom-state        (realtime/turn)
        Body: {custom: {...}, timestamp}. Opaque per-room dict.
  PATCH /api/multiplayer/effects-state       (realtime/turn)
        Body: {effects: {...}, timestamp}. Visual/audio effects.
  POST  /api/multiplayer/heartbeat
        header: X-Client-ID. Body: {}. Keep-alive. Also triggers
        the server's lazy disconnect / empty-game sweeps.
        Returns 403 {detail: "disconnected: timeout"} if the
        client was already evicted -- re-join, do not retry.
  POST  /api/multiplayer/matchmaking/cancel
  GET   /api/multiplayer/matchmaking/status?client_id=...
  POST  /api/multiplayer/switch-environment
  GET   /api/v1/capabilities
  POST  /api/multiplayer/leave
        header: X-Client-ID. Body: {}.

Strict MVC: this file is Model-only. It never imports scs,
never draws, never touches app.*. It fetches data and calls
the plain Python callbacks the app gave it. The app (Controller)
stores results in app.* and its redrawAll (View) renders them.

Brython notes: all public APIs are async def. Use browser.aio:

    from extensions.match import MatchClient
    from browser import aio

    async def join_flow(app):
        app.client = MatchClient(on_mp=lambda mp: apply_mp(app, mp))
        await app.client.join_turn_based(
            environment_name='tic-tac-toe-demo',
            character_name=app.name, game_id='tic-tac-toe-demo',
            display_name=app.name, skill=app.skill)
        app.client.connect_stream()

Realtime apps pass their schema to join_realtime:

    await app.client.join_realtime(
        environment_name='top-down-demo',
        character_name=app.name, game_id='top-down-demo',
        display_name=app.name, skill={'rating': 1000},
        character_schema={
            'version': 1,
            'fields': {
                'position': {'type': 'vec2', 'required': True,
                             'authority': 'client', 'semantic': 'position'},
                'health': {'type': 'int', 'required': True,
                           'min': 0, 'max': 100, 'authority': 'client',
                           'semantic': 'health'},
                'score': {'type': 'int', 'authority': 'server',
                          'default': 0, 'min': 0, 'semantic': 'score'},
                'name': {'type': 'string', 'authority': 'client',
                         'semantic': 'name'},
                'color': {'type': 'string', 'authority': 'client'},
            }},
        disconnection_time_sec=60, empty_game_ttl_sec=300)
    # ... then publish_character_state({'state': {
    #     'position': [x, y], 'health': 100,
    #     'name': app.name, 'color': app.color}}) -- never score.

Polling fallback: if EventSource callbacks do not reach Brython
in some browser, an app can also poll with
``await client.refresh_turn_state()`` from onStep. Applying the
same turn_state twice is harmless -- it just overwrites app.*
with the same server state.
"""

import json
import random
import time

try:
    from browser import window, aio
except ImportError:
    window = None
    aio = None

# NOTE: do NOT import asyncio here. Brython ships a stub asyncio
# that implements nothing (browser limitation) and importing it
# prints "Brython implementation of asyncio is present...".
# For async programming use browser.aio (imported above) and
# window.fetch / window.Promise only.


BASE_URL = 'https://matchgod.onrender.com'
DEFAULT_BASE_URL = BASE_URL

TURN_BASED = 'turn_based'
REALTIME = 'realtime'

__all__ = [
    'BASE_URL', 'DEFAULT_BASE_URL', 'TURN_BASED', 'REALTIME',
    'MatchClient', 'create_client',
    'join_match', 'get_turn_state', 'send_turn_action', 'leave_match',
    'parse_stream_text', 'extract_mp', 'extract_turn_state',
    'normalize_signals', 'make_player_id', 'main',
    'normalize_patch', 'canonical_character_update',
    'canonical_item_update', 'canonical_collection',
    'namespaced_item_id', 'local_item_id',
]


# ---------------------------------------------------------------------------
# Small pure helpers -- no browser, no network. Testable in CPython too.
# ---------------------------------------------------------------------------

def make_player_id(name):
    clean = ''
    for ch in str(name).lower():
        if ch.isalnum():
            clean = clean + ch
        elif not clean.endswith('-'):
            clean = clean + '-'
    clean = clean.strip('-')
    if clean == '':
        clean = 'player'
    suffix = str(int(random.random() * 1000000))
    return 'demo-' + clean + '-' + suffix


def _loads(text):
    if text is None:
        return None
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(str(text))
    except Exception:
        return None


def _strip_signals_prefix(text):
    text = str(text or '').strip()
    if text.startswith('signals '):
        text = text[len('signals '):].strip()
    return text


def parse_stream_text(raw):
    """Parse one SSE data payload into a signals dict (or None)."""
    text = _strip_signals_prefix(raw)
    if text == '':
        return None
    data = _loads(text)
    if data is None:
        return None
    if isinstance(data, dict) and 'signals' in data:
        data = data['signals']
    if isinstance(data, dict):
        return data
    return None


def normalize_signals(signals):
    if signals is None:
        return {}
    if isinstance(signals, dict):
        return signals
    return {}


def extract_mp(signals):
    """Return the mp dict from a signals dict, or None.

    Handles: signals.mp, and a signals dict that IS the mp payload
    (it already has match / turnState / turn_state / room), and
    signals.mp that is itself a patch wrapper.
    """
    signals = normalize_signals(signals)
    if 'mp' in signals and isinstance(signals['mp'], dict):
        return signals['mp']
    if 'match' in signals or 'turnState' in signals or 'turn_state' in signals:
        return signals
    if 'characters' in signals or 'character' in signals or 'items' in signals or 'item' in signals:
        return signals
    return None


def extract_turn_state(mp):
    if not isinstance(mp, dict):
        return None
    if isinstance(mp.get('turnState'), dict):
        return mp['turnState']
    if isinstance(mp.get('turn_state'), dict):
        return mp['turn_state']
    return None


def _pick(data, names):
    for name in names:
        if isinstance(data, dict) and data.get(name) is not None:
            return data.get(name)
    return None


def _schema_fields(schema):
    """fields dict of a character_schema, or {}.

    Accepts the server shape {version, fields: {...}} and the
    {properties: {...}} alias the server also accepts on join.
    """
    if not isinstance(schema, dict):
        return {}
    fields = schema.get('fields')
    if fields is None:
        fields = schema.get('properties')
    if isinstance(fields, dict):
        return fields
    return {}


def _schema_is_empty(schema):
    return len(_schema_fields(schema)) == 0


def _field_authority(schema, name):
    """'server' / 'client' / None for one schema field.

    Field specs are dicts like {'type': 'int', 'authority':
    'server'} in the JSON the server returns. Anything else is
    treated as client-owned (the server validates the value).
    """
    spec = _schema_fields(schema).get(name)
    if isinstance(spec, dict):
        auth = spec.get('authority')
        if isinstance(auth, str):
            return auth
    return None


def _extract_character_schema(data):
    """Character schema out of a join response / error payload.

    Success: data['character_schema'] (top level). 409 mismatch:
    FastAPI wraps the detail, so it is
    data['detail']['character_schema']. Also accepts the
    camelCase characterSchema spelling and a schema nested in
    data['config']. Returns the schema dict or None.
    """
    if not isinstance(data, dict):
        return None
    for key in ('character_schema', 'characterSchema'):
        v = data.get(key)
        if isinstance(v, dict):
            return v
    detail = data.get('detail')
    if isinstance(detail, dict):
        for key in ('character_schema', 'characterSchema'):
            v = detail.get(key)
            if isinstance(v, dict):
                return v
    cfg = data.get('config')
    if isinstance(cfg, dict):
        for key in ('character_schema', 'characterSchema',
                    'character_state_schema', 'characterStateSchema'):
            v = cfg.get(key)
            if isinstance(v, dict):
                return v
    return None


def _extract_join_fields(data):
    """Join responses vary a little by server version; accept all."""
    out = {}
    if not isinstance(data, dict):
        return out
    out['client_id'] = _pick(data, ['client_id', 'clientId'])
    out['session_id'] = _pick(data, ['session_id', 'sessionId'])
    out['room_id'] = _pick(data, ['room_id', 'roomId'])
    out['match_status'] = _pick(data, ['match_status', 'matchStatus', 'status'])
    out['queue_position'] = _pick(data, ['queue_position', 'queuePosition'])
    out['is_synchronizer'] = _pick(data, ['is_synchronizer', 'isSynchronizer'])
    out['game_id'] = _pick(data, ['game_id', 'gameId'])
    out['environment_name'] = _pick(data, ['environment_name', 'environmentName', 'environment'])
    out['disconnection_time_sec'] = _pick(data, ['disconnection_time_sec', 'disconnectionTimeSec', 'disconnectionTime', 'disconnect_timeout_sec'])
    out['empty_game_ttl_sec'] = _pick(data, ['empty_game_ttl_sec', 'emptyGameTtlSec', 'emptyGameTtl'])
    out['character_schema'] = _extract_character_schema(data)
    client = data.get('client')
    if isinstance(client, dict):
        if out['client_id'] is None:
            out['client_id'] = _pick(client, ['client_id', 'clientId', 'id'])
        if out['session_id'] is None:
            out['session_id'] = _pick(client, ['session_id', 'sessionId'])
    session = data.get('session')
    if isinstance(session, dict):
        if out['session_id'] is None:
            out['session_id'] = _pick(session, ['session_id', 'sessionId', 'id'])
        if out['room_id'] is None:
            out['room_id'] = _pick(session, ['room_id', 'roomId'])
    match = data.get('match')
    if isinstance(match, dict):
        if out['match_status'] is None:
            out['match_status'] = _pick(match, ['status', 'match_status'])
        if out['room_id'] is None:
            out['room_id'] = _pick(match, ['room_id', 'roomId'])
        if out['queue_position'] is None:
            out['queue_position'] = _pick(match, ['queue_position', 'queuePosition'])
    return out


def _extract_turn_state_response(data):
    if isinstance(data, dict):
        if isinstance(data.get('turnState'), dict):
            return data['turnState']
        if isinstance(data.get('turn_state'), dict):
            return data['turn_state']
        if 'turn_order' in data or 'current_player_id' in data or 'currentPlayerId' in data:
            return data
        if isinstance(data.get('turnState'), dict) is False and 'turn_order' in data:
            return data
    return None


def _to_py(value):
    """Convert a JS value from window.fetch into plain Python."""
    if value is None:
        return None
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    if window is None:
        return value
    try:
        text = window.JSON.stringify(value)
        return json.loads(str(text))
    except Exception:
        return value


def _to_js(value):
    """Convert a Python dict/list into a real JS object for fetch()."""
    if window is None:
        return json.dumps(value)
    try:
        return window.JSON.parse(json.dumps(value))
    except Exception:
        return json.dumps(value)


def _quote(text):
    if window is not None:
        try:
            return str(window.encodeURIComponent(str(text)))
        except Exception:
            pass
    out = ''
    for ch in str(text):
        if ch.isalnum() or ch in '-_.~':
            out = out + ch
        else:
            out = out + '%' + format(ord(ch), '02X')
    return out


async def _sleep(seconds):
    # browser.aio is the only working sleep in Brython. No asyncio.
    if aio is not None:
        try:
            await aio.sleep(seconds)
            return
        except Exception:
            pass
    if window is not None:
        await window.Promise.new(lambda resolve, reject: window.setTimeout(resolve, int(seconds * 1000)))


# ---------------------------------------------------------------------------
# Canonical shapes -- the new server's wire format.
# ---------------------------------------------------------------------------

def namespaced_item_id(local_id, environment):
    """'gem-1' + 'top-down-demo' -> 'top-down-demo:gem-1'.

    Already-namespaced ids pass through unchanged. Bare ids with
    no environment pass through unchanged (server binds them to
    the sender's env on first sight).
    """
    if local_id is None:
        return None
    s = str(local_id)
    if ':' in s:
        return s
    if environment:
        return str(environment) + ':' + s
    return s


def local_item_id(instance_id):
    """'top-down-demo:gem-1' -> 'gem-1'. Bare ids pass through."""
    if instance_id is None:
        return None
    s = str(instance_id)
    if ':' in s:
        return s.split(':', 1)[1]
    return s


def _pos_from(src):
    """Read a position out of any shape the client/server uses.

    Canonical is pos: [x, y]. Also accepts position / x+y /
    {x, y} / {0, 1} so old payloads still parse.
    Returns [x, y] floats or None.
    """
    if not isinstance(src, dict):
        return None
    for key in ('pos', 'position'):
        v = src.get(key)
        if isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                return [float(v[0]), float(v[1])]
            except Exception:
                pass
        elif isinstance(v, dict):
            try:
                x = v.get('x') if v.get('x') is not None else v.get('0')
                y = v.get('y') if v.get('y') is not None else v.get('1')
                if x is not None and y is not None:
                    return [float(x), float(y)]
            except Exception:
                pass
        elif isinstance(v, str) and ',' in v:
            try:
                parts = v.strip().strip('[]()').split(',')
                return [float(parts[0]), float(parts[1])]
            except Exception:
                pass
    if src.get('x') is not None and src.get('y') is not None:
        try:
            return [float(src.get('x')), float(src.get('y'))]
        except Exception:
            pass
    return None


# Top-level keys that are NEVER character state. Old (pre-v1)
# callers passed them flat next to / instead of inside state;
# canonical_character_update drops them instead of forwarding
# them, because the server 422s every one of them top-level.
# 'score' is dropped by the server-authority rule below (it is
# server-owned in every shipped schema), but it is listed here
# too so a schema-less caller can never send it.
_LEGACY_CHARACTER_KEYS = {
    'velocity', 'animationState', 'animation_state',
    'animationFrame', 'animation_frame', 'isJumping', 'facing',
    'onGround', 'characterModelId', 'metadata', 'score',
    'clientId', 'client_id', 'characterId', 'character_id',
    'id', 'timestamp', 'source', 'updates', 'state',
}


def canonical_character_update(src, default_client_id=None, position_field=None, character_schema=None, **kwargs):
    """Normalise any caller shape to a protocol-v1 CharacterState update.

    Output: {clientId, state: {...}} -- and NOTHING else.
    The server accepts exactly {clientId, state, timestamp,
    source} per update, and this function sends only the first
    two (the body carries the timestamp; the server stamps
    source). Any top-level legacy field -- position, health,
    velocity, score, metadata, pos, characterModelId,
    animationState, animationFrame, isJumping, facing, onGround
    -- is rejected by the server with 422, so none of them ever
    appears top-level here.

    Accepted inputs (both keep working, so old apps do not break):
      * canonical: {'clientId': ..., 'state': {position, health,
        name, color, ...}} -- passed through (minus dropped
        server-authority fields).
      * flat (pre-v1): {'position': [x, y], 'health': 100,
        'name': 'Zed', 'color': 'red'} -- folded into state.
        A flat 'metadata' dict ({name, color, health}) is also
        folded in, so old metadata callers keep working. A flat
        'pos' is renamed to 'position'. Any other flat key that
        is not a legacy key is passed through as a custom
        state field, so games with extra declared fields
        (e.g. state: {direction: ...}) work without a code
        change here.

    Server-authority fields are DROPPED, never sent: if
    character_schema declares a field authority 'server'
    (score in every shipped schema), it is removed from
    state. With no schema, 'score' is still dropped -- it is
    server-owned in every shipped schema and the demo never
    sends it. Unknown fields are NOT dropped here: the server
    422s them (unless the schema opts into allow_unknown),
    which is the fail-fast signal that the caller is sending
    a field it never declared.

    position_field is accepted for backwards compatibility
    and IGNORED: characters always use 'position' inside
    state. ('pos' is items only, never characters.)
    character_schema may also be passed as kwarg schema=...
    """
    if not isinstance(src, dict):
        src = {}
    if character_schema is None and isinstance(kwargs.get('schema'), dict):
        character_schema = kwargs.get('schema')
    cid = src.get('clientId') or src.get('client_id') or src.get('characterId') or src.get('character_id') or src.get('id') or default_client_id
    # --- Build the state dict. Canonical state wins; flat keys
    # fill in anything the state dict does not already have.
    state = {}
    raw_state = src.get('state')
    if isinstance(raw_state, dict):
        for k, v in raw_state.items():
            state[k] = v
    # 'pos' inside state is the old name -- rename to position.
    if 'pos' in state and 'position' not in state:
        state['position'] = state.pop('pos')
    elif 'pos' in state:
        state.pop('pos')
    # Flat known fields.
    pos = _pos_from(src)
    if pos is not None and 'position' not in state:
        state['position'] = [float(pos[0]), float(pos[1])]
    for key in ('health', 'name', 'color'):
        if key not in state and src.get(key) is not None:
            state[key] = src.get(key)
    # Flat metadata -- old callers put name / color / health there.
    meta = src.get('metadata')
    if isinstance(meta, dict):
        if 'name' not in state and meta.get('name') is not None:
            state['name'] = meta.get('name')
        if 'name' not in state and meta.get('display_name') is not None:
            state['name'] = meta.get('display_name')
        if 'name' not in state and meta.get('displayName') is not None:
            state['name'] = meta.get('displayName')
        if 'color' not in state and meta.get('color') is not None:
            state['color'] = meta.get('color')
        if 'health' not in state and meta.get('health') is not None:
            state['health'] = meta.get('health')
    # Any other flat key that is not a legacy key is a custom
    # state field -- pass it through (server validates it
    # against the schema).
    for key in src:
        if key in _LEGACY_CHARACTER_KEYS:
            continue
        if key in ('pos', 'position', 'health', 'name', 'color'):
            continue
        if key not in state:
            state[key] = src[key]
    # Normalise position to [x, y] floats when we have one.
    if 'position' in state:
        norm = _pos_from({'position': state.get('position')})
        if norm is not None:
            state['position'] = [float(norm[0]), float(norm[1])]
    # Drop server-authority fields. With a schema, drop exactly
    # what the schema marks server-owned. Without one, drop
    # 'score' (server-owned in every shipped schema).
    for key in list(state.keys()):
        auth = _field_authority(character_schema, key) if character_schema is not None else None
        if auth == 'server':
            del state[key]
        elif auth is None and key == 'score':
            del state[key]
    return {'clientId': cid, 'state': state}


def canonical_item_update(src, default_client_id=None, environment=None):
    """Normalise any caller shape to the new ItemInstanceState update.

    Output: {instanceId, pos, isCollected, collectedByClientId,
    environment}. ``environment`` is filled from the caller, the
    instanceId prefix, or the client's environment.
    """
    if not isinstance(src, dict):
        src = {}
    iid = src.get('instanceId') or src.get('instance_id') or src.get('item_id') or src.get('itemId') or src.get('id')
    env = src.get('environment') or environment
    if env is None and isinstance(iid, str) and ':' in iid:
        env = iid.split(':', 1)[0]
    # Namespace bare ids when we know the environment -- the server
    # expects <env>:<local-id> and binds bare ids only on first sight.
    iid = namespaced_item_id(iid, env)
    pos = _pos_from(src)
    if pos is None:
        pos = [0.0, 0.0]
    collected = src.get('isCollected')
    if collected is None:
        collected = src.get('is_collected')
    if collected is None:
        collected = src.get('collected')
    if collected is None:
        collected = src.get('taken')
    if collected is None:
        collected = False
    by = src.get('collectedByClientId') or src.get('collected_by_client_id') or src.get('taken_by') or src.get('takenBy') or src.get('collectedBy') or src.get('collected_by') or src.get('clientId') or src.get('client_id') or default_client_id
    upd = {'instanceId': iid, 'pos': [float(pos[0]), float(pos[1])], 'isCollected': bool(collected), 'collectedByClientId': by}
    if env is not None:
        upd['environment'] = env
    if src.get('itemName') is not None:
        upd['itemName'] = src.get('itemName')
    if src.get('rot') is not None:
        upd['rot'] = src.get('rot')
    return upd


def canonical_collection(src, default_client_id=None, environment=None):
    """Normalise any caller shape to the new collection entry.

    Output: {instanceId, collectedByClientId, environment}.
    No pos, no isCollected -- a collection IS collected.
    """
    if not isinstance(src, dict):
        src = {}
    iid = src.get('instanceId') or src.get('instance_id') or src.get('item_id') or src.get('itemId') or src.get('id')
    env = src.get('environment') or environment
    if env is None and isinstance(iid, str) and ':' in iid:
        env = iid.split(':', 1)[0]
    iid = namespaced_item_id(iid, env)
    by = src.get('collectedByClientId') or src.get('collected_by_client_id') or src.get('taken_by') or src.get('takenBy') or src.get('collectedBy') or src.get('collected_by') or src.get('clientId') or src.get('client_id') or default_client_id
    out = {'instanceId': iid, 'collectedByClientId': by}
    if env is not None:
        out['environment'] = env
    return out


# Patch signal names the new server sends after the bootstrap.
_PATCH_KEYS = {
    'character-state-update': 'characters',
    'character_state_update': 'characters',
    'item-state-update': 'items',
    'item_state_update': 'items',
    'client-joined': 'clients',
    'client_joined': 'clients',
    'client-left': 'client_left',
    'client_left': 'client_left',
    'synchronizer-changed': 'synchronizer',
    'synchronizer_changed': 'synchronizer',
    'env-item-authority-changed': 'authority',
    'env_item_authority_changed': 'authority',
    'item-authority-changed': 'authority',
    'item_authority_changed': 'authority',
    'game-over': 'game_over',
    'game_over': 'game_over',
    'matchmaking-queued': 'match',
    'matchmaking_queued': 'match',
    'custom-state-update': 'custom',
    'custom_state_update': 'custom',
    'effects-state-update': 'effects',
    'effects_state_update': 'effects',
}


def normalize_patch(mp):
    """Flatten one bootstrap-or-patch mp dict to canonical keys.

    Returns a NEW dict with: characters (list), items
    ({updates: [...], collections: [...]}), character (single),
    item (single), clients (list), client_left (list),
    synchronizer, authority, game_over, match, room, custom,
    effects, turnState, connection, plus any other keys the
    server sent. Patch-only keys are removed after flattening
    so apps only ever see the canonical shape.
    """
    if not isinstance(mp, dict):
        return {}
    out = {}
    for k in mp:
        if k not in _PATCH_KEYS:
            out[k] = mp[k]
    chars = []
    if isinstance(mp.get('characters'), list):
        chars = chars + mp['characters']
    elif isinstance(mp.get('characters'), dict):
        for key in mp['characters']:
            entry = mp['characters'][key]
            if isinstance(entry, dict):
                merged = {}
                merged.update(entry)
                if merged.get('clientId') is None and merged.get('client_id') is None:
                    merged['clientId'] = key
                chars.append(merged)
            else:
                chars.append({'clientId': key, 'value': entry})
    if isinstance(mp.get('character'), dict):
        chars.append(mp['character'])
    elif isinstance(mp.get('character'), list):
        chars = chars + mp['character']
    # Patch form: character-state-update is one update or a list.
    for pk in ('character-state-update', 'character_state_update'):
        v = mp.get(pk)
        if isinstance(v, dict):
            chars.append(v)
        elif isinstance(v, list):
            chars = chars + v
    if len(chars) > 0:
        out['characters'] = chars
    # Items: bootstrap is {updates, collections}; patches are a
    # single update, a list, or {updates, collections}.
    updates = []
    collections = []
    raw_items = mp.get('items')
    if isinstance(raw_items, dict):
        if isinstance(raw_items.get('updates'), list):
            updates = updates + raw_items['updates']
        if isinstance(raw_items.get('collections'), list):
            collections = collections + raw_items['collections']
        # Dict keyed by instanceId (old form) -- entries that are
        # not the updates/collections wrapper.
        for key in raw_items:
            if key in ('updates', 'collections'):
                continue
            entry = raw_items[key]
            if isinstance(entry, dict):
                merged = {}
                merged.update(entry)
                if merged.get('instanceId') is None and merged.get('instance_id') is None:
                    merged['instanceId'] = key
                updates.append(merged)
    elif isinstance(raw_items, list):
        updates = updates + raw_items
    if isinstance(mp.get('item'), dict):
        updates.append(mp['item'])
    elif isinstance(mp.get('item'), list):
        updates = updates + mp['item']
    for pk in ('item-state-update', 'item_state_update'):
        v = mp.get(pk)
        if isinstance(v, dict):
            if isinstance(v.get('updates'), list):
                updates = updates + v['updates']
            if isinstance(v.get('collections'), list):
                collections = collections + v['collections']
            elif 'instanceId' in v or 'instance_id' in v or 'item_id' in v:
                updates.append(v)
        elif isinstance(v, list):
            updates = updates + v
    if isinstance(mp.get('collections'), list):
        collections = collections + mp['collections']
    if len(updates) > 0 or len(collections) > 0:
        out['items'] = {'updates': updates, 'collections': collections}
    # Clients / joins / leaves.
    clients = []
    if isinstance(mp.get('clients'), list):
        clients = clients + mp['clients']
    elif isinstance(mp.get('clients'), dict):
        for key in mp['clients']:
            entry = mp['clients'][key]
            if isinstance(entry, dict):
                merged = {}
                merged.update(entry)
                if merged.get('clientId') is None and merged.get('client_id') is None:
                    merged['clientId'] = key
                clients.append(merged)
            else:
                clients.append({'clientId': key, 'character': entry})
    for pk in ('client-joined', 'client_joined'):
        v = mp.get(pk)
        if isinstance(v, dict):
            clients.append(v)
        elif isinstance(v, list):
            clients = clients + v
    if len(clients) > 0:
        out['clients'] = clients
    left = []
    for pk in ('client-left', 'client_left'):
        v = mp.get(pk)
        if isinstance(v, dict):
            left.append(v)
        elif isinstance(v, list):
            left = left + v
        elif isinstance(v, str):
            left.append({'clientId': v})
    if isinstance(mp.get('clientLeft'), dict):
        left.append(mp['clientLeft'])
    if len(left) > 0:
        out['client_left'] = left
    for pk, dest in (('synchronizer-changed', 'synchronizer'), ('synchronizer_changed', 'synchronizer')):
        if mp.get(pk) is not None:
            out[dest] = mp[pk]
    for pk in ('env-item-authority-changed', 'env_item_authority_changed', 'item-authority-changed', 'item_authority_changed'):
        if mp.get(pk) is not None:
            out['authority'] = mp[pk]
    for pk in ('game-over', 'game_over'):
        if mp.get(pk) is not None:
            out['game_over'] = mp[pk]
    for pk in ('matchmaking-queued', 'matchmaking_queued'):
        if mp.get(pk) is not None:
            out['match'] = mp[pk]
    for pk in ('custom-state-update', 'custom_state_update'):
        if mp.get(pk) is not None:
            out['custom'] = mp[pk]
    for pk in ('effects-state-update', 'effects_state_update'):
        if mp.get(pk) is not None:
            out['effects'] = mp[pk]
    return out


# ---------------------------------------------------------------------------
# MatchClient -- one joined player. One client per app.
# ---------------------------------------------------------------------------

class MatchClient(object):
    def __init__(self, base_url=None, on_mp=None, on_signal=None,
                 on_character=None, on_item=None, on_match=None,
                 on_stream_open=None, on_stream_close=None, on_stream_error=None,
                 on_client_joined=None, on_client_left=None,
                 on_game_over=None, on_custom=None, on_effects=None,
                 **kwargs):
        self.base_url = base_url or BASE_URL
        if self.base_url.endswith('/'):
            self.base_url = self.base_url[:-1]
        self.client_id = None
        self.session_id = None
        self.room_id = None
        self.match_status = None
        self.queue_position = None
        self.turn_state = None
        self.characters = {}
        self.items = {}
        self.custom = {}
        self.effects = {}
        self.requires_turn_based = None
        self.is_synchronizer = False
        self.synchronizer_id = None
        self.game_id = None
        self.environment_name = None
        self.disconnection_time_sec = None
        self.empty_game_ttl_sec = None
        self.disconnected = False
        # Effective character_schema for this game_id: what we
        # declared on join, or the stored schema after a 409
        # retry, or what the stream bootstrap carried
        # (mp.characterSchema). publish_character_state uses it
        # to drop server-authority fields (e.g. score) before
        # they reach the server. None until the first join.
        self.character_schema = None
        self._stream = None
        self.stream_connected = False
        self.on_mp = on_mp
        self.on_signal = on_signal
        self.on_character = on_character
        self.on_item = on_item
        self.on_match = on_match
        self.on_stream_open = on_stream_open
        self.on_stream_close = on_stream_close
        self.on_stream_error = on_stream_error
        self.on_client_joined = on_client_joined
        self.on_client_left = on_client_left
        self.on_game_over = on_game_over
        self.on_custom = on_custom
        self.on_effects = on_effects
        # Tolerate future app callbacks (e.g. on_connect) instead of TypeError on join.
        for _k, _v in kwargs.items():
            if _k.startswith('on_'):
                setattr(self, _k, _v)
        self._stream_open_fired = False
        self.last_error = None

    # -- identity helpers -------------------------------------------------

    @property
    def is_joined(self):
        return self.client_id is not None and not self.disconnected

    @property
    def is_queued(self):
        return self.match_status == 'queued'

    @property
    def is_matched(self):
        return self.match_status in ('matched', 'ready')

    @property
    def is_finished(self):
        if isinstance(self.turn_state, dict):
            return self.turn_state.get('phase') == 'finished'
        return self.match_status == 'finished'

    @property
    def turn_order(self):
        if isinstance(self.turn_state, dict):
            order = self.turn_state.get('turn_order')
            if isinstance(order, list):
                return order
            order = self.turn_state.get('turnOrder')
            if isinstance(order, list):
                return order
        return []

    @property
    def my_index(self):
        order = self.turn_order
        if self.client_id in order:
            return order.index(self.client_id)
        return None

    @property
    def current_player_id(self):
        if isinstance(self.turn_state, dict):
            cid = self.turn_state.get('current_player_id')
            if cid is None:
                cid = self.turn_state.get('currentPlayerId')
            return cid
        return None

    # -- low-level HTTP ---------------------------------------------------

    def _headers(self):
        headers = {'Content-Type': 'application/json'}
        if self.client_id:
            headers['X-Client-ID'] = self.client_id
        if self.session_id:
            headers['X-Session-ID'] = self.session_id
        return headers

    async def _http(self, method, path, body=None):
        if window is None:
            raise RuntimeError('extensions.match needs a browser (window.fetch)')
        url = self.base_url + path
        opts = {'method': method, 'headers': self._headers()}
        if body is not None:
            opts['body'] = json.dumps(body)
        resp = await window.fetch(url, _to_js(opts))
        status = 0
        ok = False
        try:
            status = int(resp.status)
        except Exception:
            status = 0
        try:
            ok = bool(resp.ok)
        except Exception:
            ok = False
        data = None
        try:
            raw = await resp.json()
            data = _to_py(raw)
        except Exception:
            try:
                text = await resp.text()
                data = _loads(text)
                if data is None:
                    data = text
            except Exception:
                data = None
        return {'ok': ok, 'status': status, 'data': data}

    def _failed(self, result):
        """{'_status': 403, 'detail': ...} for a non-OK HTTP result, else None."""
        if result.get('ok'):
            return None
        return {'_status': result.get('status'), 'detail': result.get('data')}

    def _note_disconnect(self, result):
        """If the server says we were evicted, remember it (403 disconnected)."""
        data = result.get('data')
        text = ''
        if isinstance(data, dict):
            text = str(data.get('detail') or '')
        elif isinstance(data, str):
            text = data
        if result.get('status') == 403 and 'disconnect' in text.lower():
            self.disconnected = True
        return text

    # -- join -------------------------------------------------------------

    def build_join_body(self, environment_name, character_name, game_id,
                        player_id=None, display_name=None, skill=1000,
                        config=None, requires_turn_based=None,
                        max_players_per_room=None, min_players_per_room=None,
                        game_mode='default', allow_pass=True,
                        allow_resign=True, requires_matchmaking=None,
                        room_id=None, room_code=None, visibility=None,
                        disconnection_time_sec=None,
                        empty_game_ttl_sec=None,
                        custom_rules=None, metadata=None,
                        max_turns=None, turn_order_strategy=None,
                        max_initial_skill_gap=None, gap_widen_per_sec=None,
                        max_skill_gap=None, character_schema=None,
                        **kwargs):
        """Build the exact join body the server expects.

        Pass config=... to override everything. Otherwise config is
        derived from the arguments so one call serves both
        turn-based and realtime apps. New fields vs the old client:
        room_id / room_code / visibility, disconnection_time_sec,
        empty_game_ttl_sec, custom_rules, matchmaking tolerances,
        turn max_turns / turn_order_strategy, and the authority
        scopes the server actually uses.

        character_schema: the declared shape of per-player state
        for this game_id, e.g. the top-down schema in the module
        docstring. It is stored as config.character_schema. When
        config=... is passed AND character_schema=... is also
        passed, the explicit character_schema wins. When neither
        is passed and config is derived here, an empty schema
        ({version: 1, fields: {}}) is declared -- the server's
        "this game sends no character state" (tic-tac-toe).
        When config=... is passed and it already carries a
        schema, that schema is left alone. characterSchema /
        character_state_schema spellings are accepted as aliases.
        """
        if requires_turn_based is None:
            requires_turn_based = True
        if requires_matchmaking is None and 'requires_matchmaking' in kwargs:
            requires_matchmaking = kwargs.get('requires_matchmaking')
        if requires_matchmaking is None:
            requires_matchmaking = True
        if character_schema is None:
            for _alias in ('characterSchema', 'character_state_schema',
                           'characterStateSchema'):
                if isinstance(kwargs.get(_alias), dict):
                    character_schema = kwargs.get(_alias)
                    break
        if player_id is None:
            player_id = make_player_id(character_name)
        if display_name is None:
            display_name = character_name
        # skill=None (what top_down used to pass) means "default", not null.
        if skill is None:
            skill = 1000
        if isinstance(skill, dict):
            skill_obj = skill
        else:
            try:
                skill_obj = {'rating': float(skill)}
            except Exception:
                skill_obj = {'rating': 1000}
        if room_id is None and 'roomId' in kwargs:
            room_id = kwargs.get('roomId')
        if room_code is None and 'roomCode' in kwargs:
            room_code = kwargs.get('roomCode')
        if visibility is None and 'visibility' in kwargs:
            visibility = kwargs.get('visibility')
        if disconnection_time_sec is None and 'disconnectionTime' in kwargs:
            disconnection_time_sec = kwargs.get('disconnectionTime')
        if empty_game_ttl_sec is None and 'emptyGameTtlSec' in kwargs:
            empty_game_ttl_sec = kwargs.get('emptyGameTtlSec')
        if config is None:
            if requires_turn_based:
                max_players = max_players_per_room
                if max_players is None:
                    max_players = 2
                min_players = min_players_per_room
                if min_players is None:
                    min_players = 2
            else:
                max_players = max_players_per_room
                if max_players is None:
                    max_players = 4
                min_players = min_players_per_room
                if min_players is None:
                    min_players = 1
            matchmaking_cfg = {'game_mode': game_mode}
            if max_initial_skill_gap is not None:
                matchmaking_cfg['max_initial_skill_gap'] = max_initial_skill_gap
            if gap_widen_per_sec is not None:
                matchmaking_cfg['gap_widen_per_sec'] = gap_widen_per_sec
            if max_skill_gap is not None:
                matchmaking_cfg['max_skill_gap'] = max_skill_gap
            turn_cfg = {'allow_pass': bool(allow_pass),
                        'allow_resign': bool(allow_resign)}
            if max_turns is not None:
                turn_cfg['max_turns'] = max_turns
            if turn_order_strategy is not None:
                turn_cfg['turn_order_strategy'] = turn_order_strategy
            config = {
                'game_id': game_id,
                'requires_matchmaking': bool(requires_matchmaking),
                'requires_turn_based': bool(requires_turn_based),
                'max_players_per_room': max_players,
                'min_players_per_room': min_players,
                'matchmaking': matchmaking_cfg,
                'turn': turn_cfg,
                # Server authority scopes: items + environment +
                # character_state. The old client sent
                # ['characters', 'items'] / ['turns'], which do not
                # match the server's AuthorityConfig.
                'authority': {'scopes': ['items', 'environment', 'character_state'],
                              'resource_types': ['*'],
                              'allow_client_claims': True},
                # Empty schema = no character state. Realtime
                # callers pass their real schema; turn-based
                # callers get the empty default.
                'character_schema': character_schema if isinstance(character_schema, dict) else {'version': 1, 'fields': {}},
            }
            if visibility is not None:
                config['visibility'] = visibility
            if room_code is not None:
                config['room_code'] = room_code
            if disconnection_time_sec is not None:
                config['disconnection_time_sec'] = disconnection_time_sec
                config['disconnectionTime'] = disconnection_time_sec
            if empty_game_ttl_sec is not None:
                config['empty_game_ttl_sec'] = empty_game_ttl_sec
            if custom_rules is not None:
                config['custom_rules'] = custom_rules
            if metadata is not None:
                config['metadata'] = metadata
        elif isinstance(character_schema, dict):
            # Explicit schema wins over a caller-supplied config.
            # Copy so we never mutate the caller's dict.
            config = dict(config)
            config['character_schema'] = character_schema
            if 'characterSchema' in config:
                del config['characterSchema']
        body = {
            'environment_name': environment_name,
            'character_name': character_name,
            'game_id': game_id,
            'player_id': player_id,
            'display_name': display_name,
            'skill': skill_obj,
            'config': config,
        }
        if room_id is not None:
            body['room_id'] = room_id
        if room_code is not None:
            body['room_code'] = room_code
        return body

    async def join(self, environment_name, character_name, game_id,
                   player_id=None, display_name=None, skill=1000,
                   config=None, requires_turn_based=None,
                   max_players_per_room=None, min_players_per_room=None,
                   game_mode='default', allow_pass=True, allow_resign=True,
                   requires_matchmaking=None, room_id=None, room_code=None,
                   visibility=None, disconnection_time_sec=None,
                   empty_game_ttl_sec=None, custom_rules=None,
                   metadata=None, max_turns=None,
                   turn_order_strategy=None, max_initial_skill_gap=None,
                   gap_widen_per_sec=None, max_skill_gap=None,
                   character_schema=None, **kwargs):
        if requires_turn_based is None:
            requires_turn_based = True
        if character_schema is None:
            for _alias in ('characterSchema', 'character_state_schema',
                           'characterStateSchema'):
                if isinstance(kwargs.get(_alias), dict):
                    character_schema = kwargs.get(_alias)
                    break
        self.requires_turn_based = bool(requires_turn_based)
        self.game_id = game_id
        self.environment_name = environment_name
        body = self.build_join_body(
            environment_name, character_name, game_id,
            player_id=player_id, display_name=display_name, skill=skill,
            config=config, requires_turn_based=requires_turn_based,
            max_players_per_room=max_players_per_room,
            min_players_per_room=min_players_per_room,
            game_mode=game_mode, allow_pass=allow_pass,
            allow_resign=allow_resign, requires_matchmaking=requires_matchmaking,
            room_id=room_id, room_code=room_code, visibility=visibility,
            disconnection_time_sec=disconnection_time_sec,
            empty_game_ttl_sec=empty_game_ttl_sec,
            custom_rules=custom_rules, metadata=metadata,
            max_turns=max_turns, turn_order_strategy=turn_order_strategy,
            max_initial_skill_gap=max_initial_skill_gap,
            gap_widen_per_sec=gap_widen_per_sec,
            max_skill_gap=max_skill_gap, character_schema=character_schema,
            **kwargs)
        # What we declared, before the server answers. The
        # effective schema (self.character_schema) is updated
        # from the join response / a 409 retry below.
        _declared = None
        if isinstance(body.get('config'), dict):
            _declared = _extract_character_schema(body['config'])
            if _declared is None:
                _declared = body['config'].get('character_schema')
        self.character_schema = _declared
        result = await self._http('POST', '/api/multiplayer/join', body)
        data = result.get('data')
        if not isinstance(data, dict):
            data = {}
        if result.get('status') == 409:
            # Another client already stored a different schema
            # for this game_id. Retry ONCE with the stored schema
            # -- but ONLY if it is non-empty. An empty stored
            # schema means an old client joined with no schema
            # (or this is a no-character-state game) and adopting
            # it would join "successfully" and then 422 every
            # character patch with "unknown character field".
            # In that case fail here: close every old tab, wait
            # out empty_game_ttl_sec (300s), then Join again.
            # The 409 detail is wrapped: data = {detail:
            # {character_schema: ...}} (FastAPI).
            stored = _extract_character_schema(data)
            if isinstance(stored, dict) and not _schema_is_empty(stored):
                retry_body = dict(body)
                retry_cfg = dict(body.get('config') or {})
                retry_cfg['character_schema'] = stored
                if 'characterSchema' in retry_cfg:
                    del retry_cfg['characterSchema']
                retry_body['config'] = retry_cfg
                result = await self._http('POST', '/api/multiplayer/join', retry_body)
                data = result.get('data')
                if not isinstance(data, dict):
                    data = {}
                if result.get('ok'):
                    self.character_schema = stored
            else:
                self.character_schema = stored
                self.last_error = str(data)
                return data
        # Effective schema: prefer what the server echoed back.
        _echoed = _extract_character_schema(data)
        if isinstance(_echoed, dict):
            self.character_schema = _echoed
        fields = _extract_join_fields(data)
        if fields.get('client_id') is not None:
            self.client_id = fields['client_id']
        if fields.get('session_id') is not None:
            self.session_id = fields['session_id']
        if fields.get('room_id') is not None:
            self.room_id = fields['room_id']
        if fields.get('match_status') is not None:
            self.match_status = fields['match_status']
        if fields.get('queue_position') is not None:
            self.queue_position = fields['queue_position']
        if fields.get('is_synchronizer') is not None:
            self.is_synchronizer = bool(fields['is_synchronizer'])
        if fields.get('game_id') is not None:
            self.game_id = fields['game_id']
        if fields.get('environment_name') is not None:
            self.environment_name = fields['environment_name']
        if fields.get('disconnection_time_sec') is not None:
            try:
                self.disconnection_time_sec = float(fields['disconnection_time_sec'])
            except Exception:
                pass
        if fields.get('empty_game_ttl_sec') is not None:
            try:
                self.empty_game_ttl_sec = float(fields['empty_game_ttl_sec'])
            except Exception:
                pass
        self.disconnected = False
        self.last_error = None
        if not result.get('ok'):
            self.last_error = str(data)
        return data

    async def join_turn_based(self, environment_name, character_name,
                              game_id, player_id=None, display_name=None,
                              skill=1000, config=None,
                              max_players_per_room=2,
                              min_players_per_room=2,
                              game_mode='default', allow_pass=True,
                              allow_resign=True, requires_matchmaking=None,
                              max_turns=None, turn_order_strategy=None,
                              disconnection_time_sec=None,
                              empty_game_ttl_sec=None, character_schema=None,
                              **kwargs):
        """Convenience: join a turn-based game (tic-tac-toe style).

        Turn-based games normally send no character state, so
        the default declared schema is the empty one. Pass
        character_schema=... if the game does send character
        state alongside turns.
        """
        return await self.join(
            environment_name, character_name, game_id,
            player_id=player_id, display_name=display_name, skill=skill,
            config=config, requires_turn_based=True,
            max_players_per_room=max_players_per_room,
            min_players_per_room=min_players_per_room,
            game_mode=game_mode, allow_pass=allow_pass,
            allow_resign=allow_resign, requires_matchmaking=requires_matchmaking,
            max_turns=max_turns, turn_order_strategy=turn_order_strategy,
            disconnection_time_sec=disconnection_time_sec,
            empty_game_ttl_sec=empty_game_ttl_sec,
            character_schema=character_schema, **kwargs)

    async def join_realtime(self, environment_name, character_name,
                            game_id, player_id=None, display_name=None,
                            skill=1000, config=None,
                            max_players_per_room=4,
                            min_players_per_room=1,
                            game_mode='default', requires_matchmaking=None,
                            disconnection_time_sec=60,
                            empty_game_ttl_sec=300, character_schema=None,
                            **kwargs):
        """Convenience: join a non-turn-based game (platformer style).

        No turn_state exists in this mode. Use
        publish_character_state / publish_item_state to send your
        state and on_character / on_item to receive others'.
        disconnection_time_sec / empty_game_ttl_sec are the new
        server's per-game budgets (60s / 300s defaults).
        Pass character_schema=... to declare the per-player
        state shape (see module docstring for the top-down
        schema). Without it the empty schema is declared,
        which means the game sends no character state.
        """
        return await self.join(
            environment_name, character_name, game_id,
            player_id=player_id, display_name=display_name, skill=skill,
            config=config, requires_turn_based=False,
            max_players_per_room=max_players_per_room,
            min_players_per_room=min_players_per_room,
            game_mode=game_mode, allow_pass=False, allow_resign=False,
            requires_matchmaking=requires_matchmaking,
            disconnection_time_sec=disconnection_time_sec,
            empty_game_ttl_sec=empty_game_ttl_sec,
            character_schema=character_schema, **kwargs)

    # -- session / matchmaking --------------------------------------------

    async def heartbeat(self):
        """POST /heartbeat. Returns data, or {'_status', 'detail'} on error.

        Call at least once per disconnection_time_sec / 2 when the
        game can be silent (lobby, thinking, paused, background
        tab). If the result is 403 disconnected, re-join -- do not
        retry the heartbeat, the old client_id is dead.
        """
        if self.client_id is None:
            return None
        result = await self._http('POST', '/api/multiplayer/heartbeat', {})
        failed = self._failed(result)
        if failed is not None:
            self._note_disconnect(result)
            return failed
        return result.get('data')

    async def get_capabilities(self):
        """GET /api/v1/capabilities -- feature-detect the server."""
        result = await self._http('GET', '/api/v1/capabilities')
        failed = self._failed(result)
        if failed is not None:
            return failed
        return result.get('data')

    async def matchmaking_status(self):
        """GET /matchmaking/status -- queue position for a queued client."""
        path = '/api/multiplayer/matchmaking/status'
        if self.client_id is not None:
            path = path + '?client_id=' + _quote(self.client_id)
        result = await self._http('GET', path)
        failed = self._failed(result)
        if failed is not None:
            return failed
        data = result.get('data')
        if isinstance(data, dict):
            if data.get('queuePosition') is not None:
                self.queue_position = data['queuePosition']
            if data.get('queue_position') is not None:
                self.queue_position = data['queue_position']
            if data.get('status') is not None:
                self.match_status = data['status']
            if data.get('match_status') is not None:
                self.match_status = data['match_status']
        return data

    async def matchmaking_cancel(self):
        """POST /matchmaking/cancel -- leave the queue."""
        result = await self._http('POST', '/api/multiplayer/matchmaking/cancel', {})
        failed = self._failed(result)
        if failed is not None:
            return failed
        return result.get('data')

    async def switch_environment(self, environment_name, **kwargs):
        """POST /switch-environment -- move to another environment_name."""
        body = {'environment_name': environment_name}
        for k in kwargs:
            body[k] = kwargs[k]
        result = await self._http('POST', '/api/multiplayer/switch-environment', body)
        failed = self._failed(result)
        if failed is not None:
            return failed
        data = result.get('data')
        if isinstance(data, dict):
            fields = _extract_join_fields(data)
            if fields.get('room_id') is not None:
                self.room_id = fields['room_id']
            self.environment_name = environment_name
        return data

    # -- turn-based -------------------------------------------------------

    async def refresh_turn_state(self):
        """GET turn/state and apply it. Safe to call repeatedly."""
        if self.client_id is None:
            return None
        path = '/api/multiplayer/turn/state'
        if self.room_id is not None:
            path = path + '?room_id=' + _quote(self.room_id)
        result = await self._http('GET', path)
        state = _extract_turn_state_response(result.get('data'))
        if state is not None:
            self.turn_state = state
            if self.on_mp is not None:
                try:
                    self.on_mp({'turnState': state})
                except Exception:
                    pass
        return state

    get_turn_state = refresh_turn_state

    async def send_turn_action(self, action_type, payload=None,
                               proposed_state=None,
                               claimed_winner_id=None,
                               claimed_is_draw=False,
                               claimed_end_reason=None):
        """POST turn/action. Server decides accepted / winner / draw.

        Sends the new shape (room_id, action, timestamp) AND the
        old shape (action_type, payload) in one body, so the new
        server and the older deployed server both accept it.
        """
        if payload is None:
            payload = {}
        body = {'action_type': action_type, 'payload': payload,
                'action': payload, 'timestamp': self._now()}
        if self.room_id is not None:
            body['room_id'] = self.room_id
        if proposed_state is not None:
            body['proposed_state'] = proposed_state
        if claimed_winner_id is not None:
            body['claimed_winner_id'] = claimed_winner_id
        body['claimed_is_draw'] = bool(claimed_is_draw)
        if claimed_end_reason is not None:
            body['claimed_end_reason'] = claimed_end_reason
        result = await self._http('POST', '/api/multiplayer/turn/action', body)
        failed = self._failed(result)
        if failed is not None:
            self._note_disconnect(result)
            return failed
        return result.get('data')

    async def send_move(self, payload, proposed_state=None,
                        claimed_winner_id=None, claimed_is_draw=False,
                        claimed_end_reason=None):
        return await self.send_turn_action(
            'move', payload=payload, proposed_state=proposed_state,
            claimed_winner_id=claimed_winner_id,
            claimed_is_draw=claimed_is_draw,
            claimed_end_reason=claimed_end_reason)

    async def pass_turn(self):
        """POST /turn/pass, falling back to turn/action pass."""
        body = {'timestamp': self._now()}
        if self.room_id is not None:
            body['room_id'] = self.room_id
        result = await self._http('POST', '/api/multiplayer/turn/pass', body)
        if result.get('ok'):
            return result.get('data')
        if result.get('status') in (404, 405):
            return await self.send_turn_action('pass', payload={})
        failed = self._failed(result)
        if failed is not None:
            return failed
        return result.get('data')

    async def resign(self):
        """POST /turn/resign, falling back to turn/action resign."""
        body = {'timestamp': self._now()}
        if self.room_id is not None:
            body['room_id'] = self.room_id
        result = await self._http('POST', '/api/multiplayer/turn/resign', body)
        if result.get('ok'):
            return result.get('data')
        if result.get('status') in (404, 405):
            return await self.send_turn_action('resign', payload={})
        failed = self._failed(result)
        if failed is not None:
            return failed
        return result.get('data')

    # -- realtime / non-turn-based ----------------------------------------

    def _now(self):
        # Server validates timestamp as int ms.
        try:
            return int(time.time() * 1000)
        except Exception:
            return 0

    def _int_ts(self, v):
        # Coerce any caller-supplied timestamp to int ms.
        # Float seconds -> int ms; int seconds -> int ms; int ms passes through.
        if v is None:
            return self._now()
        try:
            f = float(v)
        except Exception:
            return self._now()
        if f < 1e12:
            return int(f * 1000)
        return int(f)

    def _env(self, src):
        if isinstance(src, dict) and src.get('environment'):
            return src.get('environment')
        if self.environment_name:
            return self.environment_name
        if self.game_id:
            return self.game_id
        return None

    def _with_identity(self, state):
        out = {}
        if isinstance(state, dict):
            for key in state:
                out[key] = state[key]
        if self.client_id and 'client_id' not in out:
            out['client_id'] = self.client_id
        if self.session_id and 'session_id' not in out:
            out['session_id'] = self.session_id
        return out

    async def publish_character_state(self, character_state,
                                      character_id=None):
        """PATCH character-state. Protocol v1, schema-declared.

        Body is {updates: [{clientId, state: {...}}], timestamp}
        -- exactly the live demo's body. The ONLY top-level
        update field is clientId; everything else lives in
        state and must be declared in config.character_schema
        on join. Name / colour ride in state.name / state.color
        (when declared) -- never as top-level fields, never in
        metadata. Server-authority fields (e.g. score) are
        dropped before sending (see canonical_character_update);
        the client NEVER sends score.
        """
        src = character_state if isinstance(character_state, dict) else {}
        if isinstance(src.get('updates'), list):
            updates = []
            for entry in src['updates']:
                updates.append(canonical_character_update(
                    entry, default_client_id=character_id or self.client_id,
                    character_schema=self.character_schema))
            body = {
                'updates': updates,
                'timestamp': self._int_ts(src.get('timestamp')),
            }
            result = await self._http('PATCH', '/api/multiplayer/character-state', body)
            failed = self._failed(result)
            if failed is not None:
                self._note_disconnect(result)
                return failed
            return result.get('data')
        upd = canonical_character_update(
            src, default_client_id=character_id or self.client_id,
            character_schema=self.character_schema)
        body = {
            'updates': [upd], 'timestamp': self._now(),
        }
        result = await self._http('PATCH', '/api/multiplayer/character-state', body)
        failed = self._failed(result)
        if failed is not None:
            self._note_disconnect(result)
            return failed
        return result.get('data')

    async def publish_item_state(self, item_state, item_id=None):
        """PATCH item-state.

        Body is {updates, collections, timestamp}. For a COLLECT,
        send updates=[] + collections=[...] -- the server owns
        server-spawned items and drops updates for them. For a
        MOVE / SPAWN of a client-owned item, send updates=[...]
        + collections=[]. Never send an update and a collection
        for the same item in one call: the caller passes one
        item dict with isCollected=True (collect) or
        isCollected=False (move), and this method picks the
        right half.
        """
        src = item_state if isinstance(item_state, dict) else {}
        env = self._env(src)
        if isinstance(src.get('updates'), list) or isinstance(src.get('collections'), list):
            updates = []
            for entry in (src.get('updates') or []):
                updates.append(canonical_item_update(entry, default_client_id=self.client_id, environment=env))
            collections = []
            for entry in (src.get('collections') or []):
                collections.append(canonical_collection(entry, default_client_id=self.client_id, environment=env))
            body = {
                'updates': updates, 'collections': collections,
                'timestamp': self._int_ts(src.get('timestamp')),
            }
            result = await self._http('PATCH', '/api/multiplayer/item-state', body)
            failed = self._failed(result)
            if failed is not None:
                self._note_disconnect(result)
                return failed
            return result.get('data')
        # Single-item form: decide collect vs move from isCollected.
        if item_id is not None and src.get('instanceId') is None and src.get('instance_id') is None and src.get('item_id') is None:
            src = dict(src)
            src['instanceId'] = item_id
        upd = canonical_item_update(src, default_client_id=self.client_id, environment=env)
        if upd.get('isCollected'):
            coll = canonical_collection(upd, default_client_id=self.client_id, environment=env)
            body = {
                'updates': [], 'collections': [coll], 'timestamp': self._now(),
            }
        else:
            body = {
                'updates': [upd], 'collections': [], 'timestamp': self._now(),
            }
        result = await self._http('PATCH', '/api/multiplayer/item-state', body)
        failed = self._failed(result)
        if failed is not None:
            self._note_disconnect(result)
            return failed
        return result.get('data')

    async def claim_item_authority(self, item_id):
        """PATCH item-authority-claim. Client-owned items ONLY.

        Never call this for a server-spawned gem -- the server
        owns it and the claim is meaningless (and on the old
        client it blocked collection).
        """
        env = self._env({})
        iid = namespaced_item_id(item_id, env) if env else str(item_id)
        body = {'instanceId': iid, 'reason': 'collect', 'timestamp': self._now()}
        result = await self._http(
            'PATCH', '/api/multiplayer/item-authority-claim', body)
        failed = self._failed(result)
        if failed is not None:
            return failed
        return result.get('data')

    async def release_item_authority(self, item_id):
        env = self._env({})
        iid = namespaced_item_id(item_id, env) if env else str(item_id)
        body = {'instanceId': iid, 'reason': 'collect', 'timestamp': self._now()}
        result = await self._http(
            'PATCH', '/api/multiplayer/item-authority-release', body)
        failed = self._failed(result)
        if failed is not None:
            return failed
        return result.get('data')

    async def publish_custom_state(self, custom):
        """PATCH /custom-state. ``custom`` is an opaque per-room dict."""
        if not isinstance(custom, dict):
            custom = {'value': custom}
        body = {'custom': custom, 'timestamp': self._now()}
        result = await self._http('PATCH', '/api/multiplayer/custom-state', body)
        failed = self._failed(result)
        if failed is not None:
            self._note_disconnect(result)
            return failed
        self.custom = custom
        return result.get('data')

    async def publish_effects_state(self, effects):
        """PATCH /effects-state. ``effects`` is visual/audio state."""
        if not isinstance(effects, dict):
            effects = {'value': effects}
        body = {'effects': effects, 'timestamp': self._now()}
        result = await self._http('PATCH', '/api/multiplayer/effects-state', body)
        failed = self._failed(result)
        if failed is not None:
            self._note_disconnect(result)
            return failed
        self.effects = effects
        return result.get('data')

    async def publish(self, state, kind='character'):
        """Generic realtime publish.

        kind='character' -> character-state, kind='item' -> item-state,
        kind='custom' -> custom-state, kind='effects' -> effects-state.
        """
        if kind == 'item':
            return await self.publish_item_state(state)
        if kind == 'custom':
            return await self.publish_custom_state(state)
        if kind == 'effects':
            return await self.publish_effects_state(state)
        return await self.publish_character_state(state)

    # -- stream (both modes share one stream) ------------------------------

    def apply_mp(self, mp):
        if not isinstance(mp, dict):
            return None
        mp = normalize_patch(mp)
        # Bootstrap carries the effective schema (mp.characterSchema
        # camelCase from the server, or character_schema snake_case
        # from a join echo). Learn it before publishing anything.
        _schema = None
        if isinstance(mp.get('characterSchema'), dict):
            _schema = mp.get('characterSchema')
        elif isinstance(mp.get('character_schema'), dict):
            _schema = mp.get('character_schema')
        if isinstance(_schema, dict):
            self.character_schema = _schema
        if isinstance(mp.get('room'), dict):
            room_id = mp['room'].get('roomId')
            if room_id is None:
                room_id = mp['room'].get('room_id')
            if room_id is not None:
                self.room_id = room_id
        match = mp.get('match')
        if isinstance(match, dict):
            if match.get('roomId') is not None:
                self.room_id = match['roomId']
            if match.get('room_id') is not None:
                self.room_id = match['room_id']
            if match.get('status') is not None:
                self.match_status = match['status']
            if match.get('queuePosition') is not None:
                self.queue_position = match['queuePosition']
            if match.get('queue_position') is not None:
                self.queue_position = match['queue_position']
        # Direct rooms report match_status "ready", not "matched".
        if mp.get('match_status') is not None:
            self.match_status = mp['match_status']
        if isinstance(mp.get('connection'), dict):
            conn = mp['connection']
            if conn.get('disconnectionTimeSec') is not None:
                try:
                    self.disconnection_time_sec = float(conn['disconnectionTimeSec'])
                except Exception:
                    pass
            if conn.get('disconnection_time_sec') is not None:
                try:
                    self.disconnection_time_sec = float(conn['disconnection_time_sec'])
                except Exception:
                    pass
            if conn.get('isSynchronizer') is not None:
                self.is_synchronizer = bool(conn['isSynchronizer'])
            if conn.get('is_synchronizer') is not None:
                self.is_synchronizer = bool(conn['is_synchronizer'])
        if mp.get('synchronizer') is not None:
            sync = mp['synchronizer']
            if isinstance(sync, dict):
                self.synchronizer_id = sync.get('clientId') or sync.get('client_id') or sync.get('id')
                if sync.get('clientId') == self.client_id or sync.get('client_id') == self.client_id:
                    self.is_synchronizer = True
            elif isinstance(sync, str):
                self.synchronizer_id = sync
                self.is_synchronizer = (sync == self.client_id)
        if mp.get('is_synchronizer') is not None:
            self.is_synchronizer = bool(mp['is_synchronizer'])
        state = extract_turn_state(mp)
        if state is not None:
            self.turn_state = state
        if isinstance(mp.get('custom'), dict):
            self.custom = mp['custom']
        if isinstance(mp.get('effects'), dict):
            self.effects = mp['effects']
        if mp.get('game_over') is not None:
            go = mp['game_over']
            if isinstance(go, dict) and isinstance(go.get('turnState'), dict):
                self.turn_state = go['turnState']
            elif isinstance(go, dict) and isinstance(go.get('turn_state'), dict):
                self.turn_state = go['turn_state']
        return mp

    def apply_realtime(self, signals):
        signals = normalize_signals(signals)
        mp = signals.get('mp') if isinstance(signals.get('mp'), dict) else signals
        norm = normalize_patch(mp)
        # Characters (list form is canonical now).
        for entry in (norm.get('characters') or []):
            if isinstance(entry, dict):
                key = entry.get('clientId') or entry.get('client_id') or entry.get('characterId') or entry.get('character_id') or entry.get('id')
                if key is not None:
                    self.characters[key] = entry
        # Items: updates upsert, collections mark collected.
        items_norm = norm.get('items') or {}
        for entry in (items_norm.get('updates') or []):
            if isinstance(entry, dict):
                key = entry.get('instanceId') or entry.get('instance_id') or entry.get('item_id') or entry.get('itemId') or entry.get('id')
                if key is not None:
                    self.items[key] = entry
        for entry in (items_norm.get('collections') or []):
            if isinstance(entry, dict):
                key = entry.get('instanceId') or entry.get('instance_id') or entry.get('item_id') or entry.get('itemId') or entry.get('id')
                if key is not None:
                    prev = self.items.get(key)
                    if isinstance(prev, dict):
                        merged = {}
                        merged.update(prev)
                        merged.update(entry)
                        merged['isCollected'] = True
                        merged['collected'] = True
                        self.items[key] = merged
                    else:
                        merged = {}
                        merged.update(entry)
                        merged['isCollected'] = True
                        merged['collected'] = True
                        self.items[key] = merged
        # Client-left: drop the character so the avatar vanishes.
        for entry in (norm.get('client_left') or []):
            if isinstance(entry, dict):
                key = entry.get('clientId') or entry.get('client_id') or entry.get('id')
                if key is not None and key in self.characters:
                    del self.characters[key]
            elif isinstance(entry, str) and entry in self.characters:
                del self.characters[entry]
        return signals

    def handle_stream_text(self, raw):
        """Parse one SSE payload, update client, fire callbacks.

        Callbacks always receive the NORMALISED shape:
        signals = {'mp': normalised_mp, 'characters': [...],
        'items': {updates, collections}, ...} so an app written
        against the bootstrap works unchanged for patches.
        """
        signals = parse_stream_text(raw)
        if signals is None:
            return None
        raw_mp = extract_mp(signals)
        if raw_mp is None:
            raw_mp = {}
        norm_mp = normalize_patch(raw_mp)
        self.apply_mp(norm_mp)
        self.apply_realtime({'mp': norm_mp})
        norm_signals = {'mp': norm_mp}
        if 'characters' in norm_mp:
            norm_signals['characters'] = norm_mp['characters']
        if 'items' in norm_mp:
            norm_signals['items'] = norm_mp['items']
        if 'clients' in norm_mp:
            norm_signals['clients'] = norm_mp['clients']
        if 'client_left' in norm_mp:
            norm_signals['client_left'] = norm_mp['client_left']
        if 'custom' in norm_mp:
            norm_signals['custom'] = norm_mp['custom']
        if 'effects' in norm_mp:
            norm_signals['effects'] = norm_mp['effects']
        if isinstance(signals, dict):
            for k in signals:
                if k not in norm_signals and k != 'mp':
                    norm_signals[k] = signals[k]
        if self.on_mp is not None:
            try:
                self.on_mp(norm_mp)
            except Exception:
                pass
        has_chars = 'characters' in norm_mp
        has_items = 'items' in norm_mp
        if has_chars and self.on_character is not None:
            try:
                self.on_character(norm_signals)
            except Exception:
                pass
        if has_items and self.on_item is not None:
            try:
                self.on_item(norm_signals)
            except Exception:
                pass
        if 'clients' in norm_mp and self.on_client_joined is not None:
            try:
                self.on_client_joined(norm_signals)
            except Exception:
                pass
        if 'client_left' in norm_mp and self.on_client_left is not None:
            try:
                self.on_client_left(norm_signals)
            except Exception:
                pass
        if 'game_over' in norm_mp and self.on_game_over is not None:
            try:
                self.on_game_over(norm_signals)
            except Exception:
                pass
        if 'custom' in norm_mp and self.on_custom is not None:
            try:
                self.on_custom(norm_signals)
            except Exception:
                pass
        if 'effects' in norm_mp and self.on_effects is not None:
            try:
                self.on_effects(norm_signals)
            except Exception:
                pass
        if self.on_signal is not None:
            try:
                self.on_signal(norm_signals)
            except Exception:
                pass
        return norm_signals

    def connect_stream(self, on_signal=None, on_mp=None, on_stream_open=None, on_stream_close=None, on_stream_error=None):
        """Open EventSource for this session. Works in both modes."""
        if window is None:
            raise RuntimeError('extensions.match needs a browser (EventSource)')
        if self.session_id is None:
            raise RuntimeError('connect_stream needs join() first (no session_id)')
        if on_signal is not None:
            self.on_signal = on_signal
        if on_mp is not None:
            self.on_mp = on_mp
        if on_stream_open is not None:
            self.on_stream_open = on_stream_open
        if on_stream_close is not None:
            self.on_stream_close = on_stream_close
        if on_stream_error is not None:
            self.on_stream_error = on_stream_error
        self._stream_open_fired = False
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
        url = self.base_url + '/api/multiplayer/stream?session_id=' + _quote(self.session_id)
        stream = window.EventSource.new(url)
        self._stream = stream
        self.stream_connected = True

        def _fire_open():
            if self._stream_open_fired:
                return
            self._stream_open_fired = True
            if self.on_stream_open is not None:
                try:
                    self.on_stream_open()
                except Exception:
                    pass

        def _fire_close():
            if self.on_stream_close is not None:
                try:
                    self.on_stream_close()
                except Exception:
                    pass

        # EventSource fires 'open' on connect -- that is the real open signal.
        # Also fire immediately so apps that rely on the callback (top_down's
        # 'stream open' status) don't hang if the browser swallows the event.
        _fire_open()

        def _on_patch(event):
            try:
                data = event.data
            except Exception:
                data = ''
            self.handle_stream_text(data)

        def _on_message(event):
            try:
                data = event.data
            except Exception:
                data = ''
            self.handle_stream_text(data)

        def _on_open(event):
            _fire_open()

        def _on_error(event):
            self.stream_connected = False
            if self.on_stream_error is not None:
                try:
                    self.on_stream_error(event)
                except Exception:
                    pass
            _fire_close()

        try:
            stream.addEventListener('open', _on_open)
            stream.addEventListener('datastar-patch-signals', _on_patch)
            stream.addEventListener('message', _on_message)
            stream.addEventListener('error', _on_error)
        except Exception:
            try:
                stream.onmessage = _on_message
                stream.onerror = _on_error
            except Exception:
                pass
        return stream

    def disconnect_stream(self):
        _was_open = self.stream_connected
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
        self._stream = None
        self.stream_connected = False
        self._stream_open_fired = False
        if _was_open and self.on_stream_close is not None:
            try:
                self.on_stream_close()
            except Exception:
                pass

    async def poll_turn_state(self, interval_seconds=1.5, max_rounds=None):
        """Poll turn/state until finished. Turn-based fallback."""
        rounds = 0
        while self.client_id is not None:
            await _sleep(interval_seconds)
            await self.refresh_turn_state()
            rounds = rounds + 1
            if self.is_finished:
                break
            if max_rounds is not None and rounds >= max_rounds:
                break

    # -- leave --------------------------------------------------------------

    async def leave(self):
        try:
            result = await self._http('POST', '/api/multiplayer/leave', {})
            data = result.get('data')
        except Exception:
            data = None
        self.disconnect_stream()
        self.client_id = None
        self.session_id = None
        self.room_id = None
        self.match_status = None
        self.queue_position = None
        self.turn_state = None
        self.characters = {}
        self.items = {}
        self.custom = {}
        self.effects = {}
        self.is_synchronizer = False
        self.synchronizer_id = None
        self.disconnected = False
        self.character_schema = None
        return data


# ---------------------------------------------------------------------------
# Functional wrappers -- same calls, without keeping a MatchClient yourself.
# ---------------------------------------------------------------------------

def create_client(base_url=None, on_mp=None, on_signal=None,
                  on_character=None, on_item=None, on_match=None,
                  on_stream_open=None, on_stream_close=None, on_stream_error=None,
                  on_client_joined=None, on_client_left=None,
                  on_game_over=None, on_custom=None, on_effects=None):
    return MatchClient(
        base_url=base_url, on_mp=on_mp, on_signal=on_signal,
        on_character=on_character, on_item=on_item, on_match=on_match,
        on_stream_open=on_stream_open, on_stream_close=on_stream_close,
        on_stream_error=on_stream_error,
        on_client_joined=on_client_joined, on_client_left=on_client_left,
        on_game_over=on_game_over, on_custom=on_custom,
        on_effects=on_effects)


async def join_match(client, environment_name, character_name, game_id,
                     player_id=None, display_name=None, skill=1000,
                     config=None, requires_turn_based=None,
                     max_players_per_room=None, min_players_per_room=None,
                     game_mode='default', allow_pass=True,
                     allow_resign=True, requires_matchmaking=None,
                     character_schema=None, **kwargs):
    return await client.join(
        environment_name, character_name, game_id,
        player_id=player_id, display_name=display_name, skill=skill,
        config=config, requires_turn_based=requires_turn_based,
        max_players_per_room=max_players_per_room,
        min_players_per_room=min_players_per_room,
        game_mode=game_mode, allow_pass=allow_pass,
        allow_resign=allow_resign, requires_matchmaking=requires_matchmaking,
        character_schema=character_schema, **kwargs)


async def get_turn_state(client):
    return await client.refresh_turn_state()


async def send_turn_action(client, action_type, payload=None,
                           proposed_state=None, claimed_winner_id=None,
                           claimed_is_draw=False, claimed_end_reason=None):
    return await client.send_turn_action(
        action_type, payload=payload, proposed_state=proposed_state,
        claimed_winner_id=claimed_winner_id,
        claimed_is_draw=claimed_is_draw,
        claimed_end_reason=claimed_end_reason)


async def leave_match(client):
    return await client.leave()


# ---------------------------------------------------------------------------
# Entry point -- guarded so importing this extension has no side effects.
# ---------------------------------------------------------------------------

def main():
    """Create a client and report the endpoints. No network is used."""
    client = create_client()
    print('extensions.match: MatchClient ready')
    print('extensions.match: base_url=' + client.base_url)
    print('extensions.match: turn-based = join_turn_based + turn/state + turn/action + turn/pass + turn/resign')
    print('extensions.match: realtime = join_realtime + character-state (state:{position, health, name, color}) + item-state (collections) + heartbeat + custom/effects-state')
    return client


if __name__ == '__main__':
    main()
