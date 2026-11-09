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

Server protocol (matchgod.onrender.com, see
EricEisaman/match -- server/app/multiplayer):

  POST  /api/multiplayer/join
        body: environment_name, character_name, game_id,
              player_id, display_name, skill, config
        returns: client_id, session_id, room_id,
                 match_status, queue_position
  GET   /api/multiplayer/stream?session_id=<session_id>
        SSE / Datastar: ``datastar-patch-signals`` events whose
        data is ``signals {...}``. Turn apps read signals.mp.
        Realtime apps read signals.characters / signals.items.
        The older SCS platformer form ?sid=<session_id> is the
        same stream; this extension uses session_id, as in the
        tic-tac-toe demo.
  GET   /api/multiplayer/turn/state          (turn-based only)
        header: X-Client-ID. Returns { turn_state: {...} }.
  POST  /api/multiplayer/turn/action         (turn-based only)
        header: X-Client-ID. Body: action_type, payload,
        proposed_state, claimed_winner_id, claimed_is_draw,
        claimed_end_reason. Returns { accepted, reason, ... }.
  PATCH /api/multiplayer/character-state     (realtime only)
  PATCH /api/multiplayer/item-state          (realtime only)
  PATCH /api/multiplayer/item-authority-claim   (realtime)
  PATCH /api/multiplayer/item-authority-release (realtime)
        header: X-Client-ID on every call.
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

try:
    import asyncio as _asyncio
except ImportError:
    _asyncio = None


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
    (it already has match / turnState / turn_state / room).
    """
    signals = normalize_signals(signals)
    if 'mp' in signals and isinstance(signals['mp'], dict):
        return signals['mp']
    if 'match' in signals or 'turnState' in signals or 'turn_state' in signals:
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
        if isinstance(data.get('turn_state'), dict):
            return data['turn_state']
        if isinstance(data.get('turnState'), dict):
            return data['turnState']
        if isinstance(data.get('turn_state'), dict) is False and 'turn_order' in data:
            return data
        if 'turn_order' in data or 'current_player_id' in data:
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
    if aio is not None:
        try:
            await aio.sleep(seconds)
            return
        except Exception:
            pass
    if _asyncio is not None:
        await _asyncio.sleep(seconds)
        return
    if window is not None:
        await window.Promise.new(lambda resolve, reject: window.setTimeout(resolve, int(seconds * 1000)))


# ---------------------------------------------------------------------------
# MatchClient -- one joined player. One client per app.
# ---------------------------------------------------------------------------

class MatchClient(object):
    def __init__(self, base_url=None, on_mp=None, on_signal=None,
                 on_character=None, on_item=None, on_match=None,
                 on_stream_open=None, on_stream_close=None, on_stream_error=None,
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
        self.requires_turn_based = None
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
        # Tolerate future app callbacks (e.g. on_connect) instead of TypeError on join.
        for _k, _v in kwargs.items():
            if _k.startswith('on_'):
                setattr(self, _k, _v)
        self._stream_open_fired = False
        self.last_error = None

    # -- identity helpers -------------------------------------------------

    @property
    def is_joined(self):
        return self.client_id is not None

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
            return self.turn_state.get('current_player_id')
        return None

    # -- low-level HTTP ---------------------------------------------------

    def _headers(self):
        headers = {'Content-Type': 'application/json'}
        if self.client_id:
            headers['X-Client-ID'] = self.client_id
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

    # -- join -------------------------------------------------------------

    def build_join_body(self, environment_name, character_name, game_id,
                        player_id=None, display_name=None, skill=1000,
                        config=None, requires_turn_based=None,
                        max_players_per_room=None, min_players_per_room=None,
                        game_mode='default', allow_pass=True,
                        allow_resign=True):
        """Build the exact join body the demo sends.

        Pass config=... to override everything. Otherwise config is
        derived from requires_turn_based so one call serves both
        turn-based and realtime apps.
        """
        if requires_turn_based is None:
            requires_turn_based = True
        if player_id is None:
            player_id = make_player_id(character_name)
        if display_name is None:
            display_name = character_name
        if config is None:
            if requires_turn_based:
                max_players = max_players_per_room
                if max_players is None:
                    max_players = 2
                min_players = min_players_per_room
                if min_players is None:
                    min_players = 2
                scopes = ['turns']
            else:
                max_players = max_players_per_room
                if max_players is None:
                    max_players = 4
                min_players = min_players_per_room
                if min_players is None:
                    min_players = 1
                scopes = ['characters', 'items']
            config = {
                'game_id': game_id,
                'requires_matchmaking': True,
                'requires_turn_based': bool(requires_turn_based),
                'max_players_per_room': max_players,
                'min_players_per_room': min_players,
                'matchmaking': {'game_mode': game_mode},
                'turn': {'allow_pass': bool(allow_pass),
                         'allow_resign': bool(allow_resign)},
                'authority': {'scopes': scopes, 'resource_types': ['*']},
            }
        return {
            'environment_name': environment_name,
            'character_name': character_name,
            'game_id': game_id,
            'player_id': player_id,
            'display_name': display_name,
            'skill': {'rating': skill},
            'config': config,
        }

    async def join(self, environment_name, character_name, game_id,
                   player_id=None, display_name=None, skill=1000,
                   config=None, requires_turn_based=None,
                   max_players_per_room=None, min_players_per_room=None,
                   game_mode='default', allow_pass=True, allow_resign=True):
        if requires_turn_based is None:
            requires_turn_based = True
        self.requires_turn_based = bool(requires_turn_based)
        body = self.build_join_body(
            environment_name, character_name, game_id,
            player_id=player_id, display_name=display_name, skill=skill,
            config=config, requires_turn_based=requires_turn_based,
            max_players_per_room=max_players_per_room,
            min_players_per_room=min_players_per_room,
            game_mode=game_mode, allow_pass=allow_pass,
            allow_resign=allow_resign)
        result = await self._http('POST', '/api/multiplayer/join', body)
        data = result.get('data')
        if not isinstance(data, dict):
            data = {}
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
                              allow_resign=True):
        """Convenience: join a turn-based game (tic-tac-toe style)."""
        return await self.join(
            environment_name, character_name, game_id,
            player_id=player_id, display_name=display_name, skill=skill,
            config=config, requires_turn_based=True,
            max_players_per_room=max_players_per_room,
            min_players_per_room=min_players_per_room,
            game_mode=game_mode, allow_pass=allow_pass,
            allow_resign=allow_resign)

    async def join_realtime(self, environment_name, character_name,
                            game_id, player_id=None, display_name=None,
                            skill=1000, config=None,
                            max_players_per_room=4,
                            min_players_per_room=1,
                            game_mode='default'):
        """Convenience: join a non-turn-based game (platformer style).

        No turn_state exists in this mode. Use
        publish_character_state / publish_item_state to send your
        state and on_character / on_item to receive others'.
        """
        return await self.join(
            environment_name, character_name, game_id,
            player_id=player_id, display_name=display_name, skill=skill,
            config=config, requires_turn_based=False,
            max_players_per_room=max_players_per_room,
            min_players_per_room=min_players_per_room,
            game_mode=game_mode, allow_pass=False, allow_resign=False)

    # -- turn-based -------------------------------------------------------

    async def refresh_turn_state(self):
        """GET turn/state and apply it. Safe to call repeatedly."""
        if self.client_id is None:
            return None
        result = await self._http('GET', '/api/multiplayer/turn/state')
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
        """POST turn/action. Server decides accepted / winner / draw."""
        if payload is None:
            payload = {}
        body = {'action_type': action_type, 'payload': payload}
        if proposed_state is not None:
            body['proposed_state'] = proposed_state
        if claimed_winner_id is not None:
            body['claimed_winner_id'] = claimed_winner_id
        body['claimed_is_draw'] = bool(claimed_is_draw)
        if claimed_end_reason is not None:
            body['claimed_end_reason'] = claimed_end_reason
        result = await self._http('POST', '/api/multiplayer/turn/action', body)
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
        return await self.send_turn_action('pass', payload={})

    async def resign(self):
        return await self.send_turn_action('resign', payload={})

    # -- realtime / non-turn-based ----------------------------------------

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
        """PATCH character-state. character_state holds x, y, vx, vy...

        The server validates finite 2D vectors, broadcasts to the
        room, and handles synchronizer failover. character_id
        defaults to this client's id.
        """
        state = self._with_identity(character_state)
        if character_id is not None:
            state['character_id'] = character_id
        elif 'character_id' not in state and self.client_id:
            state['character_id'] = self.client_id
        result = await self._http(
            'PATCH', '/api/multiplayer/character-state', state)
        return result.get('data')

    async def publish_item_state(self, item_state, item_id=None):
        """PATCH item-state. item_state holds item pose / collected..."""
        state = self._with_identity(item_state)
        if item_id is not None:
            state['item_id'] = item_id
        result = await self._http(
            'PATCH', '/api/multiplayer/item-state', state)
        return result.get('data')

    async def claim_item_authority(self, item_id):
        body = self._with_identity({'item_id': item_id, 'instanceId': item_id, 'instance_id': item_id})
        result = await self._http(
            'PATCH', '/api/multiplayer/item-authority-claim', body)
        return result.get('data')

    async def release_item_authority(self, item_id):
        body = self._with_identity({'item_id': item_id, 'instanceId': item_id, 'instance_id': item_id})
        result = await self._http(
            'PATCH', '/api/multiplayer/item-authority-release', body)
        return result.get('data')

    async def publish(self, state, kind='character'):
        """Generic realtime publish.

        kind='character' -> character-state, kind='item' -> item-state.
        Use this when a realtime app has one shared state dict and
        does not want to care which realtime endpoint it rides on.
        """
        if kind == 'item':
            return await self.publish_item_state(state)
        return await self.publish_character_state(state)

    # -- stream (both modes share one stream) ------------------------------

    def apply_mp(self, mp):
        if not isinstance(mp, dict):
            return None
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
        state = extract_turn_state(mp)
        if state is not None:
            self.turn_state = state
        return mp

    def apply_realtime(self, signals):
        signals = normalize_signals(signals)
        characters = signals.get('characters')
        if isinstance(characters, dict):
            for key in characters:
                self.characters[key] = characters[key]
        elif isinstance(characters, list):
            for entry in characters:
                if isinstance(entry, dict):
                    # Server sends CharacterState with camelCase clientId — snake_case-only dropped every entry.
                    key = entry.get('character_id') or entry.get('characterId') or entry.get('client_id') or entry.get('clientId') or entry.get('id')
                    if key is not None:
                        self.characters[key] = entry
        character = signals.get('character')
        if isinstance(character, dict):
            key = character.get('character_id') or character.get('characterId') or character.get('client_id') or character.get('clientId') or character.get('id')
            if key is not None:
                self.characters[key] = character
        elif isinstance(character, list):
            for entry in character:
                if isinstance(entry, dict):
                    key = entry.get('character_id') or entry.get('characterId') or entry.get('client_id') or entry.get('clientId') or entry.get('id')
                    if key is not None:
                        self.characters[key] = entry
        items = signals.get('items')
        if isinstance(items, dict):
            for key in items:
                self.items[key] = items[key]
        elif isinstance(items, list):
            for entry in items:
                if isinstance(entry, dict):
                    # Server sends ItemInstanceState with instanceId — item_id-only dropped every entry.
                    key = entry.get('instanceId') or entry.get('instance_id') or entry.get('item_id') or entry.get('itemId') or entry.get('id')
                    if key is not None:
                        self.items[key] = entry
        item = signals.get('item')
        if isinstance(item, dict):
            key = item.get('instanceId') or item.get('instance_id') or item.get('item_id') or item.get('itemId') or item.get('id')
            if key is not None:
                self.items[key] = item
        elif isinstance(item, list):
            for entry in item:
                if isinstance(entry, dict):
                    key = entry.get('instanceId') or entry.get('instance_id') or entry.get('item_id') or entry.get('itemId') or entry.get('id')
                    if key is not None:
                        self.items[key] = entry
        return signals

    def handle_stream_text(self, raw):
        """Parse one SSE payload, update client, fire callbacks."""
        signals = parse_stream_text(raw)
        if signals is None:
            return None
        mp = extract_mp(signals)
        if mp is not None:
            self.apply_mp(mp)
            if self.on_mp is not None:
                try:
                    self.on_mp(mp)
                except Exception:
                    pass
        # Server sends characters/items INSIDE mp: signals={mp:{timestamp, characters, items}}.
        # Top-level-only check never fired on_character/on_item for the real payload.
        mp_chars = isinstance(mp, dict) and ('characters' in mp or 'character' in mp or 'items' in mp or 'item' in mp)
        if 'characters' in signals or 'character' in signals or 'items' in signals or 'item' in signals or mp_chars:
            if mp_chars:
                self.apply_realtime(mp)
            self.apply_realtime(signals)
            if self.on_character is not None and ('characters' in signals or 'character' in signals or (isinstance(mp, dict) and ('characters' in mp or 'character' in mp))):
                try:
                    self.on_character(signals)
                except Exception:
                    pass
            if self.on_item is not None and ('items' in signals or 'item' in signals or (isinstance(mp, dict) and ('items' in mp or 'item' in mp))):
                try:
                    self.on_item(signals)
                except Exception:
                    pass
        if self.on_signal is not None:
            try:
                self.on_signal(signals)
            except Exception:
                pass
        return signals

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

        # EventSource fires 'open' on connect — that is the real open signal.
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
        return data


# ---------------------------------------------------------------------------
# Functional wrappers -- same calls, without keeping a MatchClient yourself.
# ---------------------------------------------------------------------------

def create_client(base_url=None, on_mp=None, on_signal=None,
                  on_character=None, on_item=None, on_match=None,
                  on_stream_open=None, on_stream_close=None, on_stream_error=None):
    return MatchClient(
        base_url=base_url, on_mp=on_mp, on_signal=on_signal,
        on_character=on_character, on_item=on_item, on_match=on_match,
        on_stream_open=on_stream_open, on_stream_close=on_stream_close,
        on_stream_error=on_stream_error)


async def join_match(client, environment_name, character_name, game_id,
                     player_id=None, display_name=None, skill=1000,
                     config=None, requires_turn_based=None,
                     max_players_per_room=None, min_players_per_room=None,
                     game_mode='default', allow_pass=True,
                     allow_resign=True):
    return await client.join(
        environment_name, character_name, game_id,
        player_id=player_id, display_name=display_name, skill=skill,
        config=config, requires_turn_based=requires_turn_based,
        max_players_per_room=max_players_per_room,
        min_players_per_room=min_players_per_room,
        game_mode=game_mode, allow_pass=allow_pass,
        allow_resign=allow_resign)


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
    print('extensions.match: turn-based = join_turn_based + turn/state + turn/action')
    print('extensions.match: realtime = join_realtime + character-state + item-state')
    return client


if __name__ == '__main__':
    main()
