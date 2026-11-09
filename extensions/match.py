"""
extensions.match -- SCS Extension: multiplayer over plain JSON + EventSource.

Generic. No game in this file is named, no game shape is assumed,
no game default is baked in. Each app passes its own game_id,
environment_name, player counts, game_mode, and config. When the
caller passes config, it is used verbatim. When the caller does not,
a config is built only from the values the caller actually passed;
values the caller left out are left out, so the server decides.

Transport:
  * join, turn/state, turn/action, character-state, item-state,
    item-authority, leave are plain JSON over fetch. Request body
    is JSON. Response body is JSON. Headers are Content-Type
    application/json and X-Client-ID once joined.
  * turn/state is a single GET. It is used once on join when
    matched, and once when a stream patch reports matched without
    a turn state. It is not a loop.
  * stream is EventSource to GET /api/multiplayer/stream with
    session_id in the query. EventSource carries the connection.
    It fires datastar-patch-signals events and generic message
    events. Each event data payload starts with signals and holds
    JSON. The mp dict is extracted from it and handed to on_mp.
  * turn/action returns JSON with accepted, reason, and a turn
    state. The caller applies that turn state. The caller also
    sets its own move locally when accepted, per the caller
    contract below.

Endpoints:
  POST  /api/multiplayer/join
  GET   /api/multiplayer/turn/state
  GET   /api/multiplayer/stream?session_id=<session_id>
  POST  /api/multiplayer/turn/action
  PATCH /api/multiplayer/character-state
  PATCH /api/multiplayer/item-state
  PATCH /api/multiplayer/item-authority-claim
  PATCH /api/multiplayer/item-authority-release
  POST  /api/multiplayer/leave

Strict MVC: Model-only. No scs import, no drawing, no app.*.
The server is the authority. The client sends an action and
applies the server turn state from the action reply or from
the stream. The client never invents shared state.

Brython notes: HTTP APIs are async def. Start them from a user
gesture with browser.aio. Stream APIs are sync: connect_stream
creates the EventSource and returns it. Close it with
disconnect_stream or leave.
"""

import json
import random
import time

try:
    from browser import window
except ImportError:
    window = None


BASE_URL = 'https://matchgod.onrender.com'
DEFAULT_BASE_URL = BASE_URL

TURN_BASED = 'turn_based'
REALTIME = 'realtime'

__all__ = [
    'BASE_URL', 'DEFAULT_BASE_URL', 'TURN_BASED', 'REALTIME',
    'MatchClient', 'create_client',
    'join_match', 'send_turn_action', 'leave_match',
    'extract_mp', 'extract_turn_state',
    'normalize_signals', 'make_player_id', 'main',
]


def _generate_client_id():
    # Unique per MatchClient instance — per app/tab, not shared.
    try:
        stamp = int(time.time() * 1000)
    except Exception:
        stamp = 0
    rand = str(int(random.random() * 1000000000))
    return 'client-' + str(stamp) + '-' + rand


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
    return clean + '-' + suffix


def _to_vec2(value, x=None, y=None):
    # Server wants position as exactly [x, y], not {x, y}.
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return [value[0], value[1]]
    if isinstance(value, dict):
        return [value.get('x'), value.get('y')]
    return [x, y]


def _now_ms():
    try:
        return int(time.time() * 1000)
    except Exception:
        pass
    if window is not None:
        try:
            return int(window.Date.new().getTime())
        except Exception:
            pass
    return 0


def _loads(text):
    if text is None:
        return None
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(str(text))
    except Exception:
        return None


def _deep_copy(value):
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value))
    except Exception:
        return value


def _to_py(value):
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
        inner = data.get('data')
        if isinstance(inner, dict):
            if isinstance(inner.get('turn_state'), dict):
                return inner['turn_state']
            if isinstance(inner.get('turnState'), dict):
                return inner['turnState']
        if 'turn_order' in data or 'current_player_id' in data:
            return data
    return None


def _unwrap_action_data(data):
    if isinstance(data, dict):
        inner = data.get('data')
        if isinstance(inner, dict) and 'accepted' not in data and 'ok' not in data:
            return inner
    return data


def _parse_stream_data(raw):
    """Parse one EventSource event data payload into a signals dict.

    Event data looks like: signals {...}
    A bare JSON object is also accepted.
    """
    text = str(raw or '').strip()
    if text == '':
        return {}
    if 'data:' in text:
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('data:'):
                value = line[len('data:'):]
                if value.startswith(' '):
                    value = value[1:]
                lines.append(value)
        text = '\n'.join(lines).strip()
    if text.startswith('signals '):
        text = text[len('signals '):].strip()
    parsed = _loads(text)
    if isinstance(parsed, dict):
        inner = parsed.get('signals')
        if isinstance(inner, dict):
            return inner
        return parsed
    return {}


class MatchClient(object):
    def __init__(self, base_url=None, on_mp=None, on_signal=None,
                 on_character=None, on_item=None, on_match=None,
                 on_elements=None, on_stream_open=None,
                 on_stream_close=None):
        self.base_url = base_url or BASE_URL
        if self.base_url.endswith('/'):
            self.base_url = self.base_url[:-1]
        # Each app instance gets its own clientId up front, so publish
        # never sends an empty one even if join doesn't return one.
        self.client_id = _generate_client_id()
        self.session_id = None
        self.room_id = None
        self.match_status = None
        self.queue_position = None
        self.turn_state = None
        self.characters = {}
        self.items = {}
        self.requires_turn_based = None
        self.stream_open = False
        self.last_error = None
        self._stream = None
        self.on_mp = on_mp
        self.on_signal = on_signal
        self.on_character = on_character
        self.on_item = on_item
        self.on_match = on_match
        self.on_elements = on_elements
        self.on_stream_open = on_stream_open
        self.on_stream_close = on_stream_close

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

    @property
    def stream_connected(self):
        return self.stream_open

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

    def build_join_signals(self, environment_name, character_name,
                           game_id, player_id=None, display_name=None,
                           skill=None, config=None,
                           requires_turn_based=None,
                           max_players_per_room=None,
                           min_players_per_room=None,
                           game_mode=None, allow_pass=None,
                           allow_resign=None,
                           requires_matchmaking=None):
        """Build the join body. Nothing is assumed.

        Pass config to use it verbatim. Otherwise a config is built
        only from the values actually passed; values left out are
        left out, so the server decides them.
        """
        if player_id is None:
            player_id = make_player_id(character_name)
        if display_name is None:
            display_name = character_name
        if config is None:
            config = {}
            config['game_id'] = game_id
            if requires_matchmaking is not None:
                config['requires_matchmaking'] = bool(requires_matchmaking)
            if requires_turn_based is not None:
                config['requires_turn_based'] = bool(requires_turn_based)
            if max_players_per_room is not None:
                config['max_players_per_room'] = max_players_per_room
            if min_players_per_room is not None:
                config['min_players_per_room'] = min_players_per_room
            if game_mode is not None:
                config['matchmaking'] = {'game_mode': game_mode}
            if allow_pass is not None or allow_resign is not None:
                turn_cfg = {}
                if allow_pass is not None:
                    turn_cfg['allow_pass'] = bool(allow_pass)
                if allow_resign is not None:
                    turn_cfg['allow_resign'] = bool(allow_resign)
                config['turn'] = turn_cfg
            if requires_turn_based is True:
                config['authority'] = {'scopes': ['turns'],
                                       'resource_types': ['*']}
            elif requires_turn_based is False:
                config['authority'] = {'scopes': ['characters', 'items'],
                                       'resource_types': ['*']}
        body = {'environment_name': environment_name,
                'character_name': character_name,
                'game_id': game_id,
                'player_id': player_id,
                'display_name': display_name,
                'config': config}
        # Identify this app instance to the server from the start.
        if self.client_id:
            body['client_id'] = self.client_id
            body['clientId'] = self.client_id
        if skill is not None:
            body['skill'] = {'rating': skill}
        return body

    build_join_body = build_join_signals

    async def join(self, environment_name, character_name, game_id,
                   player_id=None, display_name=None, skill=None,
                   config=None, requires_turn_based=None,
                   max_players_per_room=None, min_players_per_room=None,
                   game_mode=None, allow_pass=None, allow_resign=None,
                   requires_matchmaking=None):
        if requires_turn_based is not None:
            self.requires_turn_based = bool(requires_turn_based)
        elif isinstance(config, dict) and config.get('requires_turn_based') is not None:
            self.requires_turn_based = bool(config['requires_turn_based'])
        body = self.build_join_signals(
            environment_name, character_name, game_id,
            player_id=player_id, display_name=display_name, skill=skill,
            config=config, requires_turn_based=requires_turn_based,
            max_players_per_room=max_players_per_room,
            min_players_per_room=min_players_per_room,
            game_mode=game_mode, allow_pass=allow_pass,
            allow_resign=allow_resign,
            requires_matchmaking=requires_matchmaking)
        self.last_error = None
        result = await self._http('POST', '/api/multiplayer/join', body)
        data = result.get('data')
        if not isinstance(data, dict):
            data = {}
        fields = _extract_join_fields(data)
        # Don't let an empty server value wipe our per-app generated ID.
        if fields.get('client_id'):
            self.client_id = fields['client_id']
        if fields.get('session_id'):
            self.session_id = fields['session_id']
        if fields.get('room_id') is not None:
            self.room_id = fields['room_id']
        if fields.get('match_status') is not None:
            self.match_status = fields['match_status']
        if fields.get('queue_position') is not None:
            self.queue_position = fields['queue_position']
        if not result.get('ok'):
            self.last_error = str(data)
        return data

    async def join_turn_based(self, environment_name, character_name,
                              game_id, player_id=None, display_name=None,
                              skill=None, config=None,
                              max_players_per_room=None,
                              min_players_per_room=None,
                              game_mode=None, allow_pass=None,
                              allow_resign=None,
                              requires_matchmaking=None):
        return await self.join(
            environment_name, character_name, game_id,
            player_id=player_id, display_name=display_name, skill=skill,
            config=config, requires_turn_based=True,
            max_players_per_room=max_players_per_room,
            min_players_per_room=min_players_per_room,
            game_mode=game_mode, allow_pass=allow_pass,
            allow_resign=allow_resign,
            requires_matchmaking=requires_matchmaking)

    async def join_realtime(self, environment_name, character_name,
                            game_id, player_id=None, display_name=None,
                            skill=None, config=None,
                            max_players_per_room=None,
                            min_players_per_room=None,
                            game_mode=None,
                            requires_matchmaking=None):
        """Join without turns. Caller passes its own counts and mode.

        No turn state exists in this mode. Use the character and
        item actions to send state and the character and item
        signals to receive it.
        """
        return await self.join(
            environment_name, character_name, game_id,
            player_id=player_id, display_name=display_name, skill=skill,
            config=config, requires_turn_based=False,
            max_players_per_room=max_players_per_room,
            min_players_per_room=min_players_per_room,
            game_mode=game_mode, allow_pass=None, allow_resign=None,
            requires_matchmaking=requires_matchmaking)

    async def refresh_turn_state(self):
        """GET turn/state and apply it. Single fetch, not a loop.

        Called once on join when matched, and once when a stream
        patch reports matched without a turn state.
        """
        if self.client_id is None:
            return None
        result = await self._http('GET', '/api/multiplayer/turn/state')
        state = _extract_turn_state_response(result.get('data'))
        if state is not None:
            self.turn_state = _deep_copy(state)
            if self.on_mp is not None:
                try:
                    self.on_mp({'turnState': _deep_copy(state)})
                except Exception:
                    pass
        return state

    get_turn_state = refresh_turn_state

    async def send_turn_action(self, action_type, payload=None,
                               proposed_state=None,
                               claimed_winner_id=None,
                               claimed_is_draw=False,
                               claimed_end_reason=None):
        """POST turn/action. Returns the server JSON reply.

        The reply holds accepted, reason, and a turn state. The
        caller applies that turn state. The server decides
        acceptance, winner, and draw.
        """
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
        return _unwrap_action_data(result.get('data'))

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
        # Server requires {updates, timestamp} — flat x/y 422s.
        # Caller passes flat {x, y, name, ...}, we wrap it.
        state = self._with_identity(character_state)
        if character_id is not None:
            state['character_id'] = character_id
        elif 'character_id' not in state and self.client_id:
            state['character_id'] = self.client_id
        if isinstance(character_state, dict) and isinstance(character_state.get('updates'), list):
            updates = character_state['updates']
        else:
            # Server rejects flat x/y/name/color. It wants vectors:
            # updates=[{position:{x,y}, score:...}]
            # score passed last round (not listed as unsupported).
            # name/color are client-side only — don't send them.
            one = {}
            # Each update must carry its own app's clientId — server
            # validates clientId inside updates, not just top-level body.
            if 'client_id' in state:
                one['clientId'] = state['client_id']
            # NOTE: characterId is NOT allowed inside updates — only top-level.
            # Server 422s with "unsupported character fields: characterId" if we put it here.
            if 'position' in state:
                one['position'] = _to_vec2(state['position'], state.get('x'), state.get('y'))
            elif 'x' in state or 'y' in state:
                one['position'] = [state.get('x'), state.get('y')]
            for key in state:
                if key in ('client_id', 'session_id', 'character_id', 'updates', 'timestamp', 'x', 'y', 'name', 'color', 'position'):
                    continue
                one[key] = state[key]
            updates = [one]
        body = {}
        for key in ('client_id', 'session_id', 'character_id'):
            if key in state:
                body[key] = state[key]
        # Server checks camelCase clientId (custom 422, not Pydantic).
        # Send both casings so we don't round-trip again on sessionId/characterId.
        if 'client_id' in state:
            body['clientId'] = state['client_id']
        if 'session_id' in state:
            body['sessionId'] = state['session_id']
        if 'character_id' in state:
            body['characterId'] = state['character_id']
        body['updates'] = updates
        if isinstance(character_state, dict) and character_state.get('timestamp') is not None:
            body['timestamp'] = character_state['timestamp']
        else:
            body['timestamp'] = _now_ms()
        result = await self._http(
            'PATCH', '/api/multiplayer/character-state', body)
        data = _unwrap_action_data(result.get('data'))
        # Don't hide 403/422 as "pub ok" — attach status so the app can log the real detail.
        if not result.get('ok') and isinstance(data, dict):
            data = dict(data)
            data['_status'] = result.get('status')
        return data

    async def publish_item_state(self, item_state, item_id=None):
        state = self._with_identity(item_state)
        if item_id is not None:
            state['item_id'] = item_id
        if isinstance(item_state, dict) and isinstance(item_state.get('updates'), list):
            updates = item_state['updates']
        else:
            # Protocol: ItemInstanceState = {instanceId, pos, isCollected,
            # collectedByClientId, ...}. NOT position/collected/clientId.
            # Server rejects unknown fields, so map exactly.
            one = {}
            iid = state.get('item_id') or state.get('itemId') or state.get('instanceId') or state.get('instance_id')
            if iid is not None:
                one['instanceId'] = iid
            if 'position' in state:
                one['pos'] = _to_vec2(state['position'], state.get('x'), state.get('y'))
            elif 'pos' in state:
                one['pos'] = _to_vec2(state['pos'], state.get('x'), state.get('y'))
            elif 'x' in state or 'y' in state:
                one['pos'] = [state.get('x'), state.get('y')]
            # collected -> isCollected, taken_by -> collectedByClientId
            coll = state.get('collected')
            if coll is None:
                coll = state.get('isCollected')
            if coll is not None:
                one['isCollected'] = bool(coll)
            taker = state.get('taken_by') or state.get('takenBy') or state.get('collectedByClientId') or state.get('collected_by') or state.get('collectedBy')
            if taker is None and 'client_id' in state:
                taker = state['client_id']
            if taker is not None:
                one['collectedByClientId'] = taker
            # Pass through only protocol-allowed item fields.
            for key in ('itemName', 'item_name', 'rot', 'ownerClientId', 'owner_client_id'):
                if key in state:
                    out_key = 'itemName' if key in ('itemName','item_name') else ('ownerClientId' if key in ('ownerClientId','owner_client_id') else key)
                    one[out_key] = state[key]
            updates = [one]
        body = {}
        for key in ('client_id', 'session_id', 'item_id'):
            if key in state:
                body[key] = state[key]
        if 'client_id' in state:
            body['clientId'] = state['client_id']
        if 'session_id' in state:
            body['sessionId'] = state['session_id']
        if 'item_id' in state:
            body['itemId'] = state['item_id']
            body['instanceId'] = state['item_id']
        body['updates'] = updates
        if isinstance(item_state, dict) and item_state.get('timestamp') is not None:
            body['timestamp'] = item_state['timestamp']
        else:
            body['timestamp'] = _now_ms()
        result = await self._http(
            'PATCH', '/api/multiplayer/item-state', body)
        data = _unwrap_action_data(result.get('data'))
        if not result.get('ok') and isinstance(data, dict):
            data = dict(data)
            data['_status'] = result.get('status')
        return data

    async def claim_item_authority(self, item_id):
        body = self._with_identity({'item_id': item_id})
        if 'client_id' in body:
            body['clientId'] = body['client_id']
        if 'session_id' in body:
            body['sessionId'] = body['session_id']
        body['itemId'] = item_id
        body['instanceId'] = item_id
        result = await self._http(
            'PATCH', '/api/multiplayer/item-authority-claim', body)
        data = _unwrap_action_data(result.get('data'))
        if not result.get('ok') and isinstance(data, dict):
            data = dict(data)
            data['_status'] = result.get('status')
        return data

    async def release_item_authority(self, item_id):
        body = self._with_identity({'item_id': item_id})
        if 'client_id' in body:
            body['clientId'] = body['client_id']
        if 'session_id' in body:
            body['sessionId'] = body['session_id']
        body['itemId'] = item_id
        body['instanceId'] = item_id
        result = await self._http(
            'PATCH', '/api/multiplayer/item-authority-release', body)
        data = _unwrap_action_data(result.get('data'))
        if not result.get('ok') and isinstance(data, dict):
            data = dict(data)
            data['_status'] = result.get('status')
        return data

    async def publish(self, state, kind='character'):
        if kind == 'item':
            return await self.publish_item_state(state)
        return await self.publish_character_state(state)

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
            self.turn_state = _deep_copy(state)
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
                    key = entry.get('character_id') or entry.get('client_id') or entry.get('id')
                    if key is not None:
                        self.characters[key] = entry
        character = signals.get('character')
        if isinstance(character, dict):
            key = character.get('character_id') or character.get('client_id') or character.get('id')
            if key is not None:
                self.characters[key] = character
        items = signals.get('items')
        if isinstance(items, dict):
            for key in items:
                self.items[key] = items[key]
        elif isinstance(items, list):
            for entry in items:
                if isinstance(entry, dict):
                    key = entry.get('item_id') or entry.get('id')
                    if key is not None:
                        self.items[key] = entry
        item = signals.get('item')
        if isinstance(item, dict):
            key = item.get('item_id') or item.get('id')
            if key is not None:
                self.items[key] = item
        return signals

    def handle_stream_text(self, raw):
        """Parse one EventSource event payload, update client, fire callbacks."""
        signals = _parse_stream_data(raw)
        if not isinstance(signals, dict) or not signals:
            return None
        mp = extract_mp(signals)
        if mp is not None:
            self.apply_mp(mp)
            if self.on_mp is not None:
                try:
                    self.on_mp(_deep_copy(mp))
                except Exception:
                    pass
            if self.on_match is not None:
                try:
                    self.on_match(_deep_copy(mp))
                except Exception:
                    pass
        # Server sends characters INSIDE mp: signals={mp:{timestamp, characters}}.
        # Old code only checked top-level 'characters', so mp-nested updates
        # never hit apply_realtime / on_character here. Top-down's _on_signal
        # compensated, but fix it at the source so both paths work.
        mp_chars = isinstance(mp, dict) and ('characters' in mp or 'character' in mp or 'items' in mp or 'item' in mp)
        if 'characters' in signals or 'character' in signals or 'items' in signals or 'item' in signals or mp_chars:
            # Feed apply_realtime the mp payload itself, not just the wrapper.
            if mp_chars:
                self.apply_realtime(mp)
            self.apply_realtime(signals)
            if self.on_character is not None and ('characters' in signals or 'character' in signals or (isinstance(mp, dict) and ('characters' in mp or 'character' in mp))):
                try:
                    self.on_character(_deep_copy(signals))
                except Exception:
                    pass
            if self.on_item is not None and ('items' in signals or 'item' in signals or (isinstance(mp, dict) and ('items' in mp or 'item' in mp))):
                try:
                    self.on_item(_deep_copy(signals))
                except Exception:
                    pass
        if self.on_signal is not None:
            try:
                self.on_signal(_deep_copy(signals))
            except Exception:
                pass
        return signals

    def connect_stream(self, on_signal=None, on_mp=None):
        """Open the stream with EventSource. Sync. Returns the EventSource.

        A previous stream is closed first. EventSource carries the
        connection and reopens it on an error. on_stream_open fires
        on open. An error is reported through on_signal so the app
        can log it; it does not close the stream.
        """
        if self.session_id is None:
            raise RuntimeError('connect_stream needs join() first (no session_id)')
        if on_signal is not None:
            self.on_signal = on_signal
        if on_mp is not None:
            self.on_mp = on_mp
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if window is None:
            raise RuntimeError('connect_stream needs a browser (EventSource)')
        url = self.base_url + '/api/multiplayer/stream?session_id=' + _quote(self.session_id)
        stream = window.EventSource.new(url)
        self._stream = stream
        self.stream_open = True

        def _on_open(event):
            self.stream_open = True
            if self.on_stream_open is not None:
                try:
                    self.on_stream_open()
                except Exception:
                    pass

        def _on_patch(event):
            try:
                self.handle_stream_text(event.data)
            except Exception:
                pass

        def _on_message(event):
            try:
                self.handle_stream_text(event.data)
            except Exception:
                pass

        def _on_error(event):
            if self.on_signal is not None:
                try:
                    self.on_signal({'event': 'stream_error'})
                except Exception:
                    pass

        try:
            stream.onopen = _on_open
        except Exception:
            pass
        try:
            stream.addEventListener('datastar-patch-signals', _on_patch)
        except Exception:
            pass
        try:
            stream.onmessage = _on_message
        except Exception:
            pass
        try:
            stream.onerror = _on_error
        except Exception:
            pass
        return stream

    def disconnect_stream(self):
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
        was_open = self.stream_open
        self.stream_open = False
        if was_open and self.on_stream_close is not None:
            try:
                self.on_stream_close()
            except Exception:
                pass

    async def leave(self):
        try:
            result = await self._http('POST', '/api/multiplayer/leave', {})
            data = result.get('data')
        except Exception as err:
            self.last_error = str(err)
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
        return _unwrap_action_data(data)


def create_client(base_url=None, on_mp=None, on_signal=None,
                  on_character=None, on_item=None, on_match=None,
                  on_elements=None, on_stream_open=None,
                  on_stream_close=None):
    return MatchClient(
        base_url=base_url, on_mp=on_mp, on_signal=on_signal,
        on_character=on_character, on_item=on_item, on_match=on_match,
        on_elements=on_elements, on_stream_open=on_stream_open,
        on_stream_close=on_stream_close)


async def join_match(client, environment_name, character_name, game_id,
                     player_id=None, display_name=None, skill=None,
                     config=None, requires_turn_based=None,
                     max_players_per_room=None, min_players_per_room=None,
                     game_mode=None, allow_pass=None,
                     allow_resign=None, requires_matchmaking=None):
    return await client.join(
        environment_name, character_name, game_id,
        player_id=player_id, display_name=display_name, skill=skill,
        config=config, requires_turn_based=requires_turn_based,
        max_players_per_room=max_players_per_room,
        min_players_per_room=min_players_per_room,
        game_mode=game_mode, allow_pass=allow_pass,
        allow_resign=allow_resign,
        requires_matchmaking=requires_matchmaking)


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


def main():
    client = create_client()
    print('extensions.match: MatchClient ready')
    print('extensions.match: base_url=' + client.base_url)
    print('extensions.match: turn mode = join_turn_based + turn/action')
    print('extensions.match: realtime mode = join_realtime + character-state + item-state')
    return client


if __name__ == '__main__':
    main()
