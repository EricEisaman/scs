"""
extensions.match -- SCS Extension: multiplayer over DataStar SSE + patches.

Generic. No game in this file is named, no game shape is assumed,
no game default is baked in. Each app passes its own game_id,
environment_name, player counts, game_mode, and config. When the
caller passes config, it is used verbatim. When the caller does not,
a config is built only from the values the caller actually passed;
values the caller left out are left out, so the server decides.

Transport -- DataStar, event driven only:
  * Every request carries Datastar-Request: true and
    Accept: text/event-stream.
  * GET: signals travel in the datastar query param.
  * POST / PATCH: the request body IS the signals object.
  * Every response is read as a DataStar SSE stream with fetch +
    a manual reader + a manual SSE parser. State changes only
    when the server sends a patch, or when a user gesture sends
    an action.
  * datastar-patch-signals is applied with JSON Merge Patch
    (RFC 7396): a key that is present updates, a key set to null
    removes, a key that is omitted is left alone. Nested objects
    merge, they are not replaced whole.
  * datastar-patch-elements is parsed and handed to on_elements.
    This file never touches the DOM: in an SCS canvas app there
    is no DOM to morph, so element patches are surfaced, not applied.
  * A response with Content-Type application/json is treated as
    one patch-signals payload, per DataStar: its JSON merges into
    the signals store.
  * onlyIfMissing is honoured: with it set, a patch only fills in
    signals that do not already exist.
  * id: is stored as last_event_id and sent back as Last-Event-ID
    on the next stream the app opens.
  * A one-shot action returns after its first patch-signals event.
    The open stream delivers the rest. A one-shot action must not
    stay open on a stream the server keeps open, or it would
    block the gesture that sent it.
  * When a long-lived stream ends, it ends. It is not reopened
    here. The app reopens it only on a later user gesture, for
    example a Reconnect click. That keeps all reconnects
    event driven.

Endpoints (matchgod.onrender.com):
  POST  /api/multiplayer/join
  GET   /api/multiplayer/stream?session_id=<session_id>
  POST  /api/multiplayer/turn/action
  PATCH /api/multiplayer/character-state
  PATCH /api/multiplayer/item-state
  PATCH /api/multiplayer/item-authority-claim
  PATCH /api/multiplayer/item-authority-release
  POST  /api/multiplayer/leave
  Every call also carries X-Client-ID once joined. That header
  is the MatchGod session header; Datastar-Request is the
  DataStar header. Both are sent.

Strict MVC: Model-only. No scs import, no drawing, no app.*.
The client keeps one signals store. The app reads derived
fields from it and renders them. The server is the authority:
the client never mutates shared state locally; it sends an
action and waits for the server patch that carries the result.

Brython notes: all public APIs are async def. Start them from
a user gesture with browser.aio, for example:

    from extensions.match import MatchClient
    from browser import aio

    async def join_flow(app):
        app.client = MatchClient(on_mp=lambda mp: apply_mp(app, mp))
        await app.client.join_turn_based(
            environment_name=app.environment_name,
            character_name=app.name,
            game_id=app.game_id,
            display_name=app.name,
            skill=app.skill,
            max_players_per_room=app.max_players,
            min_players_per_room=app.min_players,
            game_mode=app.game_mode,
            allow_pass=True,
            allow_resign=True,
            requires_matchmaking=True)
        aio.run(app.client.connect_stream())
"""

import json
import random

try:
    from browser import window
except ImportError:
    window = None


BASE_URL = 'https://matchgod.onrender.com'
DEFAULT_BASE_URL = BASE_URL

TURN_BASED = 'turn_based'
REALTIME = 'realtime'

NL = chr(10)
CR = chr(13)

__all__ = [
    'BASE_URL', 'DEFAULT_BASE_URL', 'TURN_BASED', 'REALTIME',
    'MatchClient', 'create_client',
    'join_match', 'send_turn_action', 'leave_match',
    'merge_patch', 'parse_patch_signals_data',
    'parse_patch_elements_data', 'DatastarSSEParser',
    'extract_mp', 'extract_turn_state',
    'normalize_signals', 'make_player_id', 'main',
]


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


def merge_patch(target, patch, only_if_missing=False):
    """JSON Merge Patch, RFC 7396, in place on target. Returns target.

    A key present in patch updates, a key set to null removes,
    a key omitted is left alone. Dict values merge recursively.
    With only_if_missing set, a top-level key that already exists
    in target is left alone.
    """
    if not isinstance(target, dict):
        target = {}
    if not isinstance(patch, dict):
        return target
    for key in patch:
        if only_if_missing and key in target:
            continue
        value = patch[key]
        if value is None:
            if key in target:
                del target[key]
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_patch(target[key], value, False)
        else:
            target[key] = _deep_copy(value)
    return target


def parse_patch_signals_data(data_text):
    """Parse the data lines of one datastar-patch-signals event.

    Returns (patch_dict_or_None, only_if_missing_bool).
    Data lines look like:
      signals {...}
      onlyIfMissing true
    """
    patch = None
    only_if_missing = False
    text = str(data_text or '')
    for line in text.split(NL):
        line = line.strip()
        if line.startswith('signals '):
            parsed = _loads(line[len('signals '):].strip())
            if isinstance(parsed, dict):
                patch = parsed
        elif line.startswith('onlyIfMissing '):
            value = line[len('onlyIfMissing '):].strip().lower()
            only_if_missing = value in ('true', '1', 'yes')
    return (patch, only_if_missing)


def parse_patch_elements_data(data_text):
    """Parse the data lines of one datastar-patch-elements event.

    Returns a dict with selector, mode, namespace,
    useViewTransition, viewTransitionSelector, elements.
    Element lines are joined back with NL, per the SSE spec.
    """
    out = {'selector': None, 'mode': None, 'namespace': None,
           'useViewTransition': False, 'viewTransitionSelector': None,
           'elements': ''}
    element_lines = []
    text = str(data_text or '')
    for line in text.split(NL):
        line = line.strip()
        if line.startswith('selector '):
            out['selector'] = line[len('selector '):].strip()
        elif line.startswith('mode '):
            out['mode'] = line[len('mode '):].strip()
        elif line.startswith('namespace '):
            out['namespace'] = line[len('namespace '):].strip()
        elif line.startswith('useViewTransition '):
            value = line[len('useViewTransition '):].strip().lower()
            out['useViewTransition'] = value in ('true', '1', 'yes')
        elif line.startswith('viewTransitionSelector '):
            out['viewTransitionSelector'] = line[len('viewTransitionSelector '):].strip()
        elif line.startswith('elements '):
            element_lines.append(line[len('elements '):])
        elif line.startswith('elements'):
            element_lines.append('')
    out['elements'] = NL.join(element_lines)
    return out


class DatastarSSEParser(object):
    """Incremental SSE parser. feed() returns complete events.

    Each event is a dict: {event, data, id}.
    Events end at a blank line. data: lines are joined with NL.
    A leading single space after data: is stripped, per SSE.
    """

    def __init__(self):
        self.buffer = ''

    def feed(self, chunk):
        text = str(chunk or '')
        text = text.replace(CR, '')
        self.buffer = self.buffer + text
        events = []
        marker = NL + NL
        while marker in self.buffer:
            pos = self.buffer.find(marker)
            raw = self.buffer[:pos]
            self.buffer = self.buffer[pos + len(marker):]
            events.append(self._parse_one(raw))
        return events

    def flush(self):
        raw = self.buffer
        self.buffer = ''
        if raw.strip() == '':
            return []
        return [self._parse_one(raw)]

    def _parse_one(self, raw):
        event_type = 'message'
        data_lines = []
        event_id = None
        for line in raw.split(NL):
            if line.startswith('event:'):
                value = line[len('event:'):].strip()
                if value != '':
                    event_type = value
            elif line.startswith('data:'):
                value = line[len('data:'):]
                if value.startswith(' '):
                    value = value[1:]
                data_lines.append(value)
            elif line.startswith('id:'):
                value = line[len('id:'):].strip()
                if value != '':
                    event_id = value
        return {'event': event_type, 'data': NL.join(data_lines),
                'id': event_id}


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


class MatchClient(object):
    def __init__(self, base_url=None, on_mp=None, on_signal=None,
                 on_character=None, on_item=None, on_match=None,
                 on_elements=None, on_stream_open=None,
                 on_stream_close=None):
        self.base_url = base_url or BASE_URL
        if self.base_url.endswith('/'):
            self.base_url = self.base_url[:-1]
        self.signals = {}
        self.client_id = None
        self.session_id = None
        self.room_id = None
        self.match_status = None
        self.queue_position = None
        self.turn_state = None
        self.characters = {}
        self.items = {}
        self.requires_turn_based = None
        self.stream_open = False
        self.last_event_id = None
        self.last_error = None
        self._abort_controller = None
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

    def signals_snapshot(self):
        return _deep_copy(self.signals)

    def _sync_from_signals(self):
        signals = self.signals
        mp = extract_mp(signals)
        if mp is None:
            mp = {}
        top = signals
        self.client_id = _pick(top, ['client_id', 'clientId'])
        if self.client_id is None:
            self.client_id = _pick(mp, ['client_id', 'clientId'])
        if self.client_id is None:
            client = mp.get('client')
            if isinstance(client, dict):
                self.client_id = _pick(client, ['client_id', 'clientId', 'id'])
        self.session_id = _pick(top, ['session_id', 'sessionId'])
        if self.session_id is None:
            self.session_id = _pick(mp, ['session_id', 'sessionId'])
        if self.session_id is None:
            session = mp.get('session')
            if isinstance(session, dict):
                self.session_id = _pick(session, ['session_id', 'sessionId', 'id'])
        self.room_id = _pick(top, ['room_id', 'roomId'])
        if self.room_id is None:
            self.room_id = _pick(mp, ['room_id', 'roomId'])
        if self.room_id is None:
            room = mp.get('room')
            if isinstance(room, dict):
                self.room_id = _pick(room, ['room_id', 'roomId'])
        match = mp.get('match')
        if not isinstance(match, dict):
            match = top.get('match')
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
        elif top.get('match_status') is not None:
            self.match_status = top.get('match_status')
        state = extract_turn_state(mp)
        if state is None:
            state = extract_turn_state(top)
        if state is not None:
            self.turn_state = _deep_copy(state)
        self._sync_realtime(top, mp)

    def _sync_realtime(self, top, mp):
        characters = top.get('characters')
        if characters is None:
            characters = mp.get('characters')
        if isinstance(characters, dict):
            self.characters = _deep_copy(characters)
        elif isinstance(characters, list):
            out = {}
            for entry in characters:
                if isinstance(entry, dict):
                    key = entry.get('character_id') or entry.get('client_id') or entry.get('id')
                    if key is not None:
                        out[key] = _deep_copy(entry)
            self.characters = out
        character = top.get('character')
        if character is None:
            character = mp.get('character')
        if isinstance(character, dict):
            key = character.get('character_id') or character.get('client_id') or character.get('id')
            if key is not None:
                self.characters[key] = _deep_copy(character)
        items = top.get('items')
        if items is None:
            items = mp.get('items')
        if isinstance(items, dict):
            self.items = _deep_copy(items)
        elif isinstance(items, list):
            out = {}
            for entry in items:
                if isinstance(entry, dict):
                    key = entry.get('item_id') or entry.get('id')
                    if key is not None:
                        out[key] = _deep_copy(entry)
            self.items = out
        item = top.get('item')
        if item is None:
            item = mp.get('item')
        if isinstance(item, dict):
            key = item.get('item_id') or item.get('id')
            if key is not None:
                self.items[key] = _deep_copy(item)

    def _headers(self):
        headers = {'Content-Type': 'application/json',
                   'Datastar-Request': 'true',
                   'Accept': 'text/event-stream'}
        if self.client_id:
            headers['X-Client-ID'] = self.client_id
        if self.last_event_id:
            headers['Last-Event-ID'] = self.last_event_id
        return headers

    def _datastar_url(self, path, query_params=None, signals_for_get=None):
        url = self.base_url + path
        parts = []
        if query_params:
            for key in query_params:
                parts.append(_quote(key) + '=' + _quote(query_params[key]))
        if signals_for_get is not None:
            parts.append('datastar=' + _quote(json.dumps(signals_for_get)))
        if parts:
            sep = '&'.join(parts)
            if '?' in url:
                url = url + '&' + sep
            else:
                url = url + '?' + sep
        return url

    async def _datastar_action(self, method, path, signals_body=None,
                              query_params=None, signals_for_get=None,
                              long_lived=False, stop_after_first_patch=False):
        """One DataStar action: fetch, read its SSE stream, apply patches.

        The coroutine returns only when the server closes the stream,
        unless stop_after_first_patch is set. With that set, it
        returns after the first patch-signals event is applied and
        cancels the reader. One-shot actions use that form: the
        open stream delivers the rest. Each patch is applied the
        moment its event arrives; nothing here waits for the
        stream to end first.
        """
        if window is None:
            raise RuntimeError('extensions.match needs a browser (fetch)')
        if signals_body is None:
            signals_body = {}
        url = self._datastar_url(path, query_params, signals_for_get)
        opts_py = {'method': method, 'headers': self._headers()}
        if method != 'GET':
            opts_py['body'] = json.dumps(signals_body)
        opts_js = _to_js(opts_py)
        controller = None
        try:
            controller = window.AbortController.new()
            opts_js.signal = controller.signal
        except Exception:
            controller = None
        if long_lived:
            self._abort_controller = controller
        try:
            resp = await window.fetch(url, opts_js)
            await self._read_response(resp, stop_after_first_patch)
        finally:
            if long_lived and self._abort_controller is controller:
                self._abort_controller = None
        return self.signals_snapshot()

    async def _read_response(self, resp, stop_after_first_patch=False):
        content_type = ''
        try:
            content_type = str(resp.headers.get('content-type') or '')
        except Exception:
            content_type = ''
        content_type = content_type.lower()
        if 'text/event-stream' in content_type:
            await self._read_sse_body(resp, stop_after_first_patch)
            return
        text = ''
        try:
            text = str(await resp.text())
        except Exception:
            text = ''
        if text.strip() == '':
            return
        if 'event:' in text or 'data:' in text:
            self._feed_text(text)
            return
        patch = _loads(text)
        if isinstance(patch, dict):
            self.apply_patch_signals(patch, False)

    async def _read_sse_body(self, resp, stop_after_first_patch=False):
        reader = None
        try:
            reader = resp.body.getReader()
        except Exception:
            reader = None
        if reader is None:
            text = ''
            try:
                text = str(await resp.text())
            except Exception:
                text = ''
            if text != '':
                self._feed_text(text)
            return
        decoder = None
        try:
            decoder = window.TextDecoder.new('utf-8')
        except Exception:
            decoder = None
        parser = DatastarSSEParser()
        while True:
            try:
                result = await reader.read()
            except Exception:
                break
            done = False
            value = None
            try:
                done = bool(result.done)
                value = result.value
            except Exception:
                done = True
            if done:
                break
            chunk = ''
            if decoder is not None and value is not None:
                try:
                    chunk = str(decoder.decode(value, _to_js({'stream': True})))
                except Exception:
                    chunk = ''
            if chunk != '':
                stop = False
                for event in parser.feed(chunk):
                    if self._handle_event(event) and stop_after_first_patch:
                        stop = True
                if stop:
                    try:
                        reader.cancel()
                    except Exception:
                        pass
                    break
        if decoder is not None:
            try:
                tail = str(decoder.decode())
                if tail != '':
                    for event in parser.feed(tail):
                        self._handle_event(event)
            except Exception:
                pass
        for event in parser.flush():
            self._handle_event(event)

    def _feed_text(self, text):
        parser = DatastarSSEParser()
        for event in parser.feed(str(text)):
            self._handle_event(event)
        for event in parser.flush():
            self._handle_event(event)

    def _handle_event(self, event):
        if not isinstance(event, dict):
            return False
        if event.get('id') is not None:
            self.last_event_id = event['id']
        event_type = event.get('event') or 'message'
        data = event.get('data') or ''
        if event_type == 'datastar-patch-signals':
            patch, only_if_missing = parse_patch_signals_data(data)
            if patch is not None:
                self.apply_patch_signals(patch, only_if_missing)
                return True
            return False
        if event_type == 'datastar-patch-elements':
            elements = parse_patch_elements_data(data)
            self.apply_patch_elements(elements)
            return False
        if event_type == 'message':
            text = str(data).strip()
            if text.startswith('signals '):
                patch, only_if_missing = parse_patch_signals_data(text)
                if patch is not None:
                    self.apply_patch_signals(patch, only_if_missing)
                    return True
                return False
            if text.startswith('{'):
                patch = _loads(text)
                if isinstance(patch, dict):
                    self.apply_patch_signals(patch, False)
                    return True
                return False
        if self.on_signal is not None:
            try:
                self.on_signal({'event': event_type, 'data': data})
            except Exception:
                pass
        return False

    def apply_patch_signals(self, patch, only_if_missing=False):
        if not isinstance(patch, dict):
            return None
        merge_patch(self.signals, patch, only_if_missing)
        self._sync_from_signals()
        mp = extract_mp(self.signals)
        if 'mp' in patch or 'match' in patch or 'turnState' in patch or 'turn_state' in patch:
            if self.on_mp is not None and mp is not None:
                try:
                    self.on_mp(_deep_copy(mp))
                except Exception:
                    pass
            if self.on_match is not None:
                try:
                    self.on_match(_deep_copy(mp))
                except Exception:
                    pass
        has_character = ('characters' in patch or 'character' in patch or
                         'characters' in (mp or {}) or 'character' in (mp or {}))
        if has_character and self.on_character is not None:
            try:
                self.on_character(_deep_copy(self.signals))
            except Exception:
                pass
        has_item = ('items' in patch or 'item' in patch or
                    'items' in (mp or {}) or 'item' in (mp or {}))
        if has_item and self.on_item is not None:
            try:
                self.on_item(_deep_copy(self.signals))
            except Exception:
                pass
        if self.on_signal is not None:
            try:
                self.on_signal(_deep_copy(patch))
            except Exception:
                pass
        return _deep_copy(patch)

    def apply_patch_elements(self, elements):
        if self.on_elements is not None:
            try:
                self.on_elements(_deep_copy(elements))
            except Exception:
                pass
        if self.on_signal is not None:
            try:
                self.on_signal({'elements': _deep_copy(elements)})
            except Exception:
                pass
        return _deep_copy(elements)

    def build_join_signals(self, environment_name, character_name,
                           game_id, player_id=None, display_name=None,
                           skill=None, config=None,
                           requires_turn_based=None,
                           max_players_per_room=None,
                           min_players_per_room=None,
                           game_mode=None, allow_pass=None,
                           allow_resign=None,
                           requires_matchmaking=None):
        """Build the join signals object. Nothing is assumed.

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
        try:
            await self._datastar_action('POST', '/api/multiplayer/join', body)
        except Exception as err:
            self.last_error = str(err)
            raise
        return self.signals_snapshot()

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

    async def send_turn_action(self, action_type, payload=None,
                               proposed_state=None,
                               claimed_winner_id=None,
                               claimed_is_draw=False,
                               claimed_end_reason=None):
        """Send one turn action. The result arrives as server patches.

        The client does not decide acceptance, winner, or draw.
        It sends the action and the patch stream carries the
        server decision. Shared state is only ever changed by
        those patches. This call returns after the first patch,
        so a one-shot action never blocks the gesture that
        sent it; the open stream delivers the rest.
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
        await self._datastar_action(
            'POST', '/api/multiplayer/turn/action', body,
            stop_after_first_patch=True)
        return self.signals_snapshot()

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
        state = self._with_identity(character_state)
        if character_id is not None:
            state['character_id'] = character_id
        elif 'character_id' not in state and self.client_id:
            state['character_id'] = self.client_id
        await self._datastar_action(
            'PATCH', '/api/multiplayer/character-state', state,
            stop_after_first_patch=True)
        return self.signals_snapshot()

    async def publish_item_state(self, item_state, item_id=None):
        state = self._with_identity(item_state)
        if item_id is not None:
            state['item_id'] = item_id
        await self._datastar_action(
            'PATCH', '/api/multiplayer/item-state', state,
            stop_after_first_patch=True)
        return self.signals_snapshot()

    async def claim_item_authority(self, item_id):
        body = self._with_identity({'item_id': item_id})
        await self._datastar_action(
            'PATCH', '/api/multiplayer/item-authority-claim', body,
            stop_after_first_patch=True)
        return self.signals_snapshot()

    async def release_item_authority(self, item_id):
        body = self._with_identity({'item_id': item_id})
        await self._datastar_action(
            'PATCH', '/api/multiplayer/item-authority-release', body,
            stop_after_first_patch=True)
        return self.signals_snapshot()

    async def publish(self, state, kind='character'):
        if kind == 'item':
            return await self.publish_item_state(state)
        return await self.publish_character_state(state)

    async def connect_stream(self, on_signal=None, on_mp=None):
        """Open the long-lived stream. Stays open until the server closes it.

        Patches arrive through the same reader as every other action.
        When the stream ends, on_stream_close fires. This method does
        not reopen the stream. The app reopens it only on a later
        user gesture.
        """
        if self.session_id is None:
            raise RuntimeError('connect_stream needs join() first (no session_id)')
        if on_signal is not None:
            self.on_signal = on_signal
        if on_mp is not None:
            self.on_mp = on_mp
        if self.stream_open:
            return self.signals_snapshot()
        self.stream_open = True
        if self.on_stream_open is not None:
            try:
                self.on_stream_open()
            except Exception:
                pass
        signals_for_get = {}
        if self.client_id:
            signals_for_get['client_id'] = self.client_id
        if self.session_id:
            signals_for_get['session_id'] = self.session_id
        try:
            await self._datastar_action(
                'GET', '/api/multiplayer/stream',
                query_params={'session_id': self.session_id},
                signals_for_get=signals_for_get,
                long_lived=True)
        except Exception as err:
            self.last_error = str(err)
        finally:
            self.stream_open = False
            if self.on_stream_close is not None:
                try:
                    self.on_stream_close()
                except Exception:
                    pass
        return self.signals_snapshot()

    def disconnect_stream(self):
        controller = self._abort_controller
        self._abort_controller = None
        if controller is not None:
            try:
                controller.abort()
            except Exception:
                pass
        self.stream_open = False

    async def leave(self):
        try:
            await self._datastar_action(
                'POST', '/api/multiplayer/leave', {},
                stop_after_first_patch=True)
        except Exception as err:
            self.last_error = str(err)
        self.disconnect_stream()
        self.signals = {}
        self.client_id = None
        self.session_id = None
        self.room_id = None
        self.match_status = None
        self.queue_position = None
        self.turn_state = None
        self.characters = {}
        self.items = {}
        return self.signals_snapshot()


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
