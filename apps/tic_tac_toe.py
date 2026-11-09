"""
apps/tic_tac_toe.py -- SCS app, 1050 x 700, tic-tac-toe over MatchGod.

Model: extensions.match, generic. Controller: onAppStart, onMousePress,
onKeyPress, async flows here. View: redrawAll here, and only here.

Transport: DataStar SSE + patches. Join, stream, turn/action, leave
are DataStar actions. Shared state changes only when a server patch
arrives. The client never sets the board locally.

Layout: top row Name, Skill, -10, +10, Join, Leave, Rematch.
Status line below. Left: 3x3 board. Right panel: You, Turn, Opponent,
Pass, Resign, Stream, Reconnect, Log.
Controls: click Name or Skill to edit, type, Backspace, Enter Join,
Esc stop editing. Click an empty cell on your turn. Click Pass,
Resign, Reconnect, or press P, R, C with nothing being edited.
Run: http://localhost:8000/?app=tic_tac_toe
"""

from scs import *
from browser import aio
from extensions.match import MatchClient


APP_WIDTH = 1050
APP_HEIGHT = 700

BOARD_X = 40
BOARD_Y = 160
CELL = 148
GAP = 8
BOARD_W = 3 * CELL + 2 * GAP
BOARD_H = 3 * CELL + 2 * GAP

NAME_RECT = (40, 82, 260, 36)
SKILL_RECT = (330, 82, 120, 36)
SKILL_MINUS_RECT = (460, 82, 36, 36)
SKILL_PLUS_RECT = (500, 82, 36, 36)
JOIN_RECT = (560, 82, 120, 36)
LEAVE_RECT = (690, 82, 120, 36)
REMATCH_RECT = (820, 82, 140, 36)
PASS_RECT = (560, 250, 180, 36)
RESIGN_RECT = (760, 250, 180, 36)
RECONNECT_RECT = (560, 316, 180, 36)

PANEL_X = 540
PANEL_Y = 160
PANEL_W = 460
PANEL_H = 460

ENVIRONMENT_NAME = 'tic-tac-toe-demo'
GAME_ID = 'tic-tac-toe-demo'
GAME_MODE = 'default'

WIN_LINES = [[0, 1, 2], [3, 4, 5], [6, 7, 8],
              [0, 3, 6], [1, 4, 7], [2, 5, 8],
              [0, 4, 8], [2, 4, 6]]


def winner_of(board):
    for line in WIN_LINES:
        a = line[0]
        b = line[1]
        c = line[2]
        if board[a] != '' and board[a] == board[b] and board[a] == board[c]:
            return board[a]
    return None


def winner_line(board):
    for line in WIN_LINES:
        a = line[0]
        b = line[1]
        c = line[2]
        if board[a] != '' and board[a] == board[b] and board[a] == board[c]:
            return line
    return None


def is_draw_board(board):
    if winner_of(board) is not None:
        return False
    for cell in board:
        if cell == '':
            return False
    return True


def marks_for(turn_order):
    marks = {}
    for i in range(len(turn_order)):
        if i == 0:
            marks[turn_order[i]] = 'X'
        elif i == 1:
            marks[turn_order[i]] = 'O'
    return marks


def _inside(x, y, rect):
    return rect[0] <= x <= rect[0] + rect[2] and rect[1] <= y <= rect[1] + rect[3]


def _shorten(text, limit):
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit - 3] + '...'


def _cell_at(x, y):
    if x < BOARD_X or y < BOARD_Y:
        return None
    if x >= BOARD_X + BOARD_W or y >= BOARD_Y + BOARD_H:
        return None
    col = (x - BOARD_X) // (CELL + GAP)
    row = (y - BOARD_Y) // (CELL + GAP)
    local_x = (x - BOARD_X) % (CELL + GAP)
    local_y = (y - BOARD_Y) % (CELL + GAP)
    if local_x >= CELL or local_y >= CELL:
        return None
    return row * 3 + col


def _cell_rect(index):
    col = index % 3
    row = index // 3
    x = BOARD_X + col * (CELL + GAP)
    y = BOARD_Y + row * (CELL + GAP)
    return (x, y, CELL, CELL)


def add_log(app, message):
    app.log.append(_shorten(message, 72))
    while len(app.log) > 7:
        app.log.pop(0)


def update_you_line(app):
    if app.my_mark is None:
        app.you_text = ''
    else:
        room = app.room_id or ''
        app.you_text = 'You are ' + app.my_mark + ' - Seat ' + str(app.my_index) + ' - Room ' + str(room)


def apply_mp(app, mp):
    if mp is None:
        return
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
    if isinstance(match, dict):
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
            app.status = 'Queued (position ' + str(pos) + ') - opponent needed...'
            update_you_line(app)
            return
        if status in ('matched', 'ready'):
            app.match_status = 'matched'
            app.status = 'Matched!'
            if mp.get('turnState') is None and mp.get('turn_state') is None:
                return
        if status == 'finished' and mp.get('turnState') is None and mp.get('turn_state') is None:
            app.match_status = 'finished'
            app.status = 'Game over.'
            return
    ts = mp.get('turnState')
    if ts is None:
        ts = mp.get('turn_state')
    if ts is None:
        return
    if not isinstance(ts, dict):
        return
    turn_order = ts.get('turn_order')
    if isinstance(turn_order, list):
        app.turn_order = turn_order
    my_index = None
    if app.client_id is not None and app.client_id in app.turn_order:
        my_index = app.turn_order.index(app.client_id)
    app.my_index = my_index
    if my_index == 0:
        app.my_mark = 'X'
    elif my_index == 1:
        app.my_mark = 'O'
    else:
        app.my_mark = None
    state = ts.get('state')
    if isinstance(state, dict):
        board = state.get('board')
        if isinstance(board, list) and len(board) == 9:
            app.board = [str(v) for v in board]
    app.current_player_id = ts.get('current_player_id')
    app.turn_number = ts.get('turn_number')
    app.phase = ts.get('phase')
    app.winner_id = ts.get('winner_id')
    app.is_draw = ts.get('is_draw')
    app.end_reason = ts.get('end_reason')
    update_you_line(app)
    if app.phase == 'finished':
        app.match_status = 'finished'
        if app.is_draw:
            app.status = 'Draw!'
        elif app.winner_id == app.client_id:
            app.status = 'You win!'
        elif app.winner_id:
            app.status = 'You lose.'
        else:
            app.status = 'Game over - ' + str(app.end_reason or '')
    elif app.current_player_id == app.client_id:
        app.status = 'Your turn (' + str(app.my_mark) + ') - click an empty cell. Turn ' + str(app.turn_number) + '.'
    else:
        app.status = 'Opponent turn... Turn ' + str(app.turn_number) + '.'


def _on_mp_callback(app, mp):
    apply_mp(app, mp)


def _on_signal_callback(app, signals):
    if isinstance(signals, dict) and 'mp' not in signals:
        add_log(app, 'signal: ' + _shorten(str(signals), 60))


def _on_stream_open_callback(app):
    app.stream_open = True
    app.stream_status = 'Stream: open'
    add_log(app, 'stream open')


def _on_stream_close_callback(app):
    app.stream_open = False
    app.stream_status = 'Stream: closed - Reconnect to reopen'
    add_log(app, 'stream closed')


async def do_join(app):
    if app.joining:
        return
    if app.client is not None:
        return
    app.joining = True
    app.status = 'Joining...'
    name = app.name or 'player'
    skill = app.skill

    def _on_mp(mp):
        _on_mp_callback(app, mp)

    def _on_signal(signals):
        _on_signal_callback(app, signals)

    def _on_open():
        _on_stream_open_callback(app)

    def _on_close():
        _on_stream_close_callback(app)

    client = MatchClient(on_mp=_on_mp, on_signal=_on_signal,
                         on_stream_open=_on_open,
                         on_stream_close=_on_close)
    app.client = client
    try:
        data = await client.join_turn_based(
            environment_name=ENVIRONMENT_NAME,
            character_name=name,
            game_id=GAME_ID,
            display_name=name,
            skill=skill,
            game_mode=GAME_MODE,
            max_players_per_room=2,
            min_players_per_room=2,
            allow_pass=True,
            allow_resign=True,
            requires_matchmaking=True)
        app.client_id = client.client_id
        app.session_id = client.session_id
        app.room_id = client.room_id
        app.match_status = client.match_status
        app.queue_position = client.queue_position
        if client.match_status == 'queued':
            app.status = 'Queued (position ' + str(client.queue_position) + ') - opponent needed...'
        else:
            app.status = 'Matched!'
        add_log(app, 'joined: ' + _shorten(str(data), 100))
        aio.run(client.connect_stream())
    except Exception as err:
        add_log(app, 'join failed: ' + str(err))
        app.status = 'Join failed - see log.'
        app.client = None
    app.joining = False


async def do_move(app, cell):
    if app.client is None or app.my_mark is None:
        add_log(app, 'not matched yet')
        return
    if app.board[cell] != '':
        return
    if app.sending:
        return
    app.sending = True
    next_board = list(app.board)
    next_board[cell] = app.my_mark
    winner = winner_of(next_board)
    draw = False
    if winner is None:
        draw = is_draw_board(next_board)
    marks = marks_for(app.turn_order)
    end_reason = None
    if winner is not None:
        end_reason = 'win'
    elif draw:
        end_reason = 'draw'
    claimed_winner = None
    if winner is not None:
        claimed_winner = app.client_id
    try:
        data = await app.client.send_turn_action(
            'move',
            payload={'cell': cell, 'mark': app.my_mark},
            proposed_state={'board': next_board, 'marks': marks},
            claimed_winner_id=claimed_winner,
            claimed_is_draw=draw,
            claimed_end_reason=end_reason)
        add_log(app, 'move sent: ' + _shorten(str(data), 100))
    except Exception as err:
        add_log(app, 'move failed: ' + str(err))
    app.sending = False


async def do_pass(app):
    if app.client is None:
        return
    try:
        data = await app.client.pass_turn()
        add_log(app, 'pass -> ' + _shorten(str(data), 100))
    except Exception as err:
        add_log(app, 'pass failed: ' + str(err))


async def do_resign(app):
    if app.client is None:
        return
    try:
        data = await app.client.resign()
        add_log(app, 'resign -> ' + _shorten(str(data), 100))
    except Exception as err:
        add_log(app, 'resign failed: ' + str(err))


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
    app.turn_order = []
    app.my_mark = None
    app.my_index = None
    app.board = ['', '', '', '', '', '', '', '', '']
    app.current_player_id = None
    app.turn_number = 0
    app.phase = None
    app.winner_id = None
    app.is_draw = False
    app.end_reason = None
    app.status = 'Left.'
    app.you_text = ''
    app.sending = False
    app.stream_open = False
    app.stream_status = 'Stream: closed'


async def do_rematch(app):
    await do_leave(app)
    await do_join(app)


async def do_reconnect(app):
    if app.client is None:
        return
    if app.stream_open:
        return
    aio.run(app.client.connect_stream())


def onAppStart(app):
    app.background = gradient(rgb(18, 18, 20), rgb(30, 34, 48), start='top')
    app.name = 'player'
    app.skill = 1000
    app.focus = 'name'
    app.client = None
    app.client_id = None
    app.session_id = None
    app.room_id = None
    app.match_status = None
    app.queue_position = None
    app.turn_order = []
    app.my_mark = None
    app.my_index = None
    app.board = ['', '', '', '', '', '', '', '', '']
    app.current_player_id = None
    app.turn_number = 0
    app.phase = None
    app.winner_id = None
    app.is_draw = False
    app.end_reason = None
    app.status = 'Not joined.'
    app.you_text = ''
    app.log = []
    app.sending = False
    app.joining = False
    app.stream_open = False
    app.stream_status = 'Stream: closed'
    add_log(app, 'Click Join to find an opponent.')


def onMousePress(app, x, y):
    if _inside(x, y, NAME_RECT):
        app.focus = 'name'
        return
    if _inside(x, y, SKILL_RECT):
        app.focus = 'skill'
        return
    if _inside(x, y, SKILL_MINUS_RECT):
        app.focus = None
        app.skill = max(0, app.skill - 10)
        return
    if _inside(x, y, SKILL_PLUS_RECT):
        app.focus = None
        app.skill = min(3000, app.skill + 10)
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
    if _inside(x, y, REMATCH_RECT):
        app.focus = None
        if app.client is not None:
            aio.run(do_rematch(app))
        return
    if _inside(x, y, PASS_RECT):
        app.focus = None
        if app.client is not None and app.match_status == 'matched':
            aio.run(do_pass(app))
        return
    if _inside(x, y, RESIGN_RECT):
        app.focus = None
        if app.client is not None and app.match_status == 'matched':
            aio.run(do_resign(app))
        return
    if _inside(x, y, RECONNECT_RECT):
        app.focus = None
        if app.client is not None:
            aio.run(do_reconnect(app))
        return
    cell = _cell_at(x, y)
    if cell is not None:
        app.focus = None
        if app.client is None or app.match_status != 'matched':
            add_log(app, 'not matched yet')
            return
        if app.phase == 'finished':
            return
        if app.current_player_id != app.client_id:
            add_log(app, 'not your turn')
            return
        aio.run(do_move(app, cell))
        return
    app.focus = None


def onKeyPress(app, key):
    if key == 'escape':
        app.focus = None
        return
    if key == 'enter':
        if app.client is None and not app.joining:
            aio.run(do_join(app))
        elif app.client is not None:
            aio.run(do_rematch(app))
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
    if app.focus == 'skill':
        if key == 'backspace':
            text = str(app.skill)
            text = text[:-1]
            if text == '':
                app.skill = 0
            else:
                app.skill = int(text)
        elif len(key) == 1 and key.isdigit():
            text = str(app.skill) + key
            if len(text) <= 5:
                app.skill = min(3000, int(text))
        return
    if key == 'p' or key == 'P':
        if app.client is not None and app.match_status == 'matched':
            aio.run(do_pass(app))
    elif key == 'r' or key == 'R':
        if app.client is not None:
            aio.run(do_rematch(app))
    elif key == 'c' or key == 'C':
        if app.client is not None:
            aio.run(do_reconnect(app))
    elif key == 'j' or key == 'J':
        if app.client is None and not app.joining:
            aio.run(do_join(app))
    elif key == 'l' or key == 'L':
        if app.client is not None:
            aio.run(do_leave(app))


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
    drawLabel(label, x + w // 2, y + h // 2, size=15, bold=True, fill='white')


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
    drawLabel('Tic-Tac-Toe - MatchGod', APP_WIDTH // 2, 32, size=28, bold=True, fill='white')
    drawLabel('Rules live on the server. The server enforces turns. State arrives as one mp signal.',
              APP_WIDTH // 2, 58, size=13, fill=rgb(214, 224, 255))
    joined = app.client is not None
    matched = app.match_status == 'matched'
    my_turn = matched and app.phase != 'finished' and app.current_player_id == app.client_id
    _draw_field(NAME_RECT, 'Name', app.name, app.focus == 'name')
    _draw_field(SKILL_RECT, 'Skill (client-reported)', str(app.skill), app.focus == 'skill')
    _draw_button(SKILL_MINUS_RECT, '-10', True)
    _draw_button(SKILL_PLUS_RECT, '+10', True)
    _draw_button(JOIN_RECT, 'Join', not joined and not app.joining)
    _draw_button(LEAVE_RECT, 'Leave', joined)
    _draw_button(REMATCH_RECT, 'Rematch', joined)
    drawRect(40, 130, 920, 24, fill=rgb(30, 34, 48), border=rgb(47, 58, 90), borderWidth=1, roundness=6)
    drawLabel(app.status, 48, 142, size=13, bold=True, fill=rgb(214, 224, 255), align='left')
    win = winner_line(app.board)
    for i in range(9):
        rect = _cell_rect(i)
        mark = app.board[i]
        if win is not None and i in win:
            fill = rgb(32, 90, 50)
            border = rgb(80, 200, 120)
        elif mark == 'X':
            fill = rgb(28, 52, 78)
            border = rgb(70, 130, 180)
        elif mark == 'O':
            fill = rgb(78, 52, 22)
            border = rgb(200, 140, 60)
        elif my_turn:
            fill = rgb(38, 38, 46)
            border = rgb(110, 110, 130)
        else:
            fill = rgb(30, 30, 34)
            border = rgb(68, 68, 78)
        drawRect(rect[0], rect[1], rect[2], rect[3], fill=fill, border=border, borderWidth=1, roundness=8)
        if mark != '':
            drawLabel(mark, rect[0] + rect[2] // 2, rect[1] + rect[2] // 2, size=64, bold=True, fill='white')
    drawRect(PANEL_X, PANEL_Y, PANEL_W, PANEL_H, fill=rgb(30, 34, 48), border=rgb(47, 58, 90), borderWidth=1, roundness=8)
    drawLabel(app.you_text, PANEL_X + 16, PANEL_Y + 24, size=14, bold=True, fill='white', align='leftTop')
    turn_text = 'Turn ' + str(app.turn_number)
    if app.phase is not None:
        turn_text = turn_text + ' - ' + str(app.phase)
    if app.my_mark is not None:
        turn_text = turn_text + ' - You: ' + str(app.my_mark)
    drawLabel(turn_text, PANEL_X + 16, PANEL_Y + 48, size=13, fill=rgb(214, 224, 255), align='leftTop')
    drawLabel('Opponent: ' + ('O' if app.my_mark == 'X' else 'X' if app.my_mark == 'O' else '-'),
              PANEL_X + 16, PANEL_Y + 68, size=13, fill=rgb(214, 224, 255), align='leftTop')
    _draw_button(PASS_RECT, 'Pass', matched and app.phase != 'finished')
    _draw_button(RESIGN_RECT, 'Resign', matched and app.phase != 'finished')
    drawLabel(app.stream_status, PANEL_X + 16, PANEL_Y + 140, size=13, fill=rgb(214, 224, 255), align='leftTop')
    _draw_button(RECONNECT_RECT, 'Reconnect', joined and not app.stream_open)
    drawLabel('Log', PANEL_X + 16, PANEL_Y + 180, size=14, bold=True, fill='white', align='leftTop')
    drawRect(PANEL_X + 16, PANEL_Y + 204, PANEL_W - 32, 200, fill=rgb(10, 10, 10), border=rgb(68, 68, 78), borderWidth=1, roundness=6)
    for i in range(len(app.log)):
        drawLabel(app.log[i], PANEL_X + 26, PANEL_Y + 226 + i * 28, size=12, fill=rgb(214, 255, 214), align='leftTop')
    drawLabel('Click a cell on your turn. Keys: Enter Join, P Pass, R Rematch, C Reconnect, Esc stop editing.',
              PANEL_X + 16, PANEL_Y + 404, size=12, fill=rgb(214, 224, 255), align='leftTop')
    drawLabel('X goes first. Server decides win / draw / rejected moves.',
              PANEL_X + 16, PANEL_Y + 428, size=12, fill=rgb(214, 224, 255), align='leftTop')
    drawLabel('Server: https://matchgod.onrender.com  -  Join: POST /api/multiplayer/join  -  Stream: GET /api/multiplayer/stream',
              APP_WIDTH // 2, 660, size=12, fill=rgb(180, 190, 210))
    drawLabel('Move: POST /api/multiplayer/turn/action  -  Leave: POST /api/multiplayer/leave',
              APP_WIDTH // 2, 682, size=12, fill=rgb(180, 190, 210))


_STARTED = False


def main():
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    runApp(width=APP_WIDTH, height=APP_HEIGHT)


main()
