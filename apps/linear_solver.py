from scs import *
from browser import document, aio
from extensions.pyodide import root
import re


BG = rgb(15, 20, 23)
PANEL = rgb(25, 33, 37)
INK = rgb(229, 238, 232)
MUTED = rgb(137, 157, 151)
MINT = rgb(102, 224, 177)
GOLD = rgb(244, 190, 92)
RED = rgb(244, 111, 104)

_PANEL_ID = 'linear-solver-controls'
_EXAMPLES = {
    'nonlinear': ('Nonlinear system', 'x^2 + y^2 = 25\nx - y = 1', 'x, y', '2, 1'),
    'exp-command': ('Exponential: exp(x)', r'\exp x = 2', 'x', '0.5'),
    'exp-power': ('Exponential: e^x', 'e^x = 2', 'x', '0.5'),
    'log-natural': ('Natural logarithm: ln(x)', r'\ln x = 1', 'x', '2.5'),
    'log-base': ('Base logarithm: log_2(x)', r'\log_{2}x = 3', 'x', '7'),
    'trig-sincos': ('Trigonometric: sin(x) = cos(x)', r'\sin x = \cos x', 'x', '0.7'),
    'trig-tan': ('Trigonometric: tan(x) = 1', r'\tan x = 1', 'x', '0.7'),
    'matrix-brackets': ('Ax=b: bracket notation', '[[2,1],[1,3]] * [x,y] = [5,7]', 'x, y', '1, 1'),
    'matrix-latex': (
        'Ax=b: LaTeX bmatrix',
        r'\begin{bmatrix}2 & 1 \\ 1 & 3\end{bmatrix}\begin{bmatrix}x \\ y\end{bmatrix}=\begin{bmatrix}5 \\ 7\end{bmatrix}',
        'x, y', '1, 1'
    )
}


def _math_group(source, position):
    while position < len(source) and source[position].isspace():
        position += 1
    if position >= len(source) or source[position] != '{':
        raise ValueError('Expected a braced LaTeX argument')
    depth = 1
    start = position + 1
    position += 1
    while position < len(source) and depth:
        if source[position] == '{':
            depth += 1
        elif source[position] == '}':
            depth -= 1
        position += 1
    if depth:
        raise ValueError('Unclosed LaTeX group')
    return source[start:position - 1], position


def _math_argument(source, position):
    while position < len(source) and source[position].isspace():
        position += 1
    if source.startswith('\\left', position):
        position += 5
        while position < len(source) and source[position].isspace():
            position += 1
    if position >= len(source):
        raise ValueError('Expected a LaTeX function argument')
    if source[position] == '{':
        return _math_group(source, position)
    if source[position] == '(':
        start = position
        depth = 0
        while position < len(source):
            if source[position] == '(':
                depth += 1
            elif source[position] == ')':
                depth -= 1
                if depth == 0:
                    return source[start + 1:position], position + 1
            position += 1
        raise ValueError('Unclosed function argument')
    if source[position] == '\\':
        match = re.match(r'\\([A-Za-z]+)', source[position:])
        if not match:
            raise ValueError('Invalid LaTeX command in function argument')
        command_end = position + len(match.group(0))
        command = match.group(1)
        if command in ('frac',):
            start = position
            _, position = _math_group(source, command_end)
            _, position = _math_group(source, position)
            return source[start:position], position
        if command == 'sqrt':
            start = position
            _, position = _math_argument(source, command_end)
            return source[start:position], position
        return match.group(0), command_end

    start = position
    match = re.match(r'[A-Za-z][A-Za-z0-9]*|[0-9]+(?:\.[0-9]+)?', source[position:])
    if not match:
        raise ValueError('Expected a variable, number, or grouped LaTeX argument')
    position += len(match.group(0))
    if position < len(source) and source[position] == '_':
        position += 1
        if position < len(source) and source[position] == '{':
            _, position = _math_group(source, position)
        else:
            subscript = re.match(r'[A-Za-z0-9]+', source[position:])
            if subscript:
                position += len(subscript.group(0))
    if position < len(source) and source[position] == '^':
        position += 1
        if position < len(source) and source[position] == '{':
            _, position = _math_group(source, position)
        else:
            power = re.match(r'[A-Za-z0-9]+', source[position:])
            if power:
                position += len(power.group(0))
    return source[start:position], position


def _latex_expression(source):
    source = source.strip().replace('$', '').replace('−', '-')
    output = []
    position = 0
    while position < len(source):
        if source[position] == '\\':
            match = re.match(r'\\([A-Za-z]+)', source[position:])
            if not match:
                raise ValueError('Invalid LaTeX command')
            command = match.group(1)
            command_end = position + len(match.group(0))
            if command in ('left', 'right'):
                position = command_end
                continue
            if command == 'frac':
                numerator, next_position = _math_group(source, command_end)
                denominator, position = _math_group(source, next_position)
                output.append('((' + _latex_expression(numerator) + ')/(' + _latex_expression(denominator) + '))')
                continue
            if command == 'sqrt':
                argument, position = _math_argument(source, command_end)
                output.append('sqrt(' + _latex_expression(argument) + ')')
                continue
            functions = {
                'sin': 'sin', 'cos': 'cos', 'tan': 'tan',
                'sec': 'sec', 'csc': 'csc', 'cot': 'cot',
                'arcsin': 'asin', 'arccos': 'acos', 'arctan': 'atan',
                'sinh': 'sinh', 'cosh': 'cosh', 'tanh': 'tanh',
                'exp': 'exp', 'ln': 'ln', 'log': 'log'
            }
            if command in functions:
                argument_position = command_end
                base = None
                if command == 'log' and argument_position < len(source) and source[argument_position] == '_':
                    base, argument_position = _math_argument(source, argument_position + 1)
                argument, position = _math_argument(source, argument_position)
                call = functions[command] + '(' + _latex_expression(argument)
                if base is not None:
                    call += ', ' + _latex_expression(base)
                output.append(call + ')')
                continue
            symbols = {
                'cdot': '*', 'times': '*', 'pi': 'pi',
                'theta': 'theta', 'alpha': 'alpha', 'beta': 'beta'
            }
            if command in symbols:
                output.append(symbols[command])
                position = command_end
                continue
            raise ValueError('Unsupported LaTeX command: \\' + command)
        if source[position] == '{':
            output.append('(')
        elif source[position] == '}':
            output.append(')')
        else:
            output.append(source[position])
        position += 1

    expression = ''.join(output).replace('^', '**')
    functions = r'(?:sin|cos|tan|sec|csc|cot|asin|acos|atan|sinh|cosh|tanh|exp|ln|log)'
    expression = re.sub(r'(?<=[0-9)])\s*(?=[A-Za-z(])', '*', expression)
    expression = re.sub(r'(?<=[A-Za-z0-9_)])(?=' + functions + r'\()', '*', expression)
    expression = re.sub(r'(?<=[A-Za-z0-9_)])\s+(?=' + functions + r'\()', '*', expression)
    return expression.strip()


def _split_top_level(source, delimiter):
    parts = []
    start = 0
    depth = 0
    for position, character in enumerate(source):
        if character in '[({':
            depth += 1
        elif character in '])}':
            depth -= 1
        elif character == delimiter and depth == 0:
            parts.append(source[start:position].strip())
            start = position + 1
    parts.append(source[start:].strip())
    return parts


def _take_bracket_group(source):
    source = source.strip()
    if not source.startswith('['):
        raise ValueError('Expected a bracketed matrix or vector')
    depth = 0
    for position, character in enumerate(source):
        if character == '[':
            depth += 1
        elif character == ']':
            depth -= 1
            if depth == 0:
                return source[:position + 1], source[position + 1:].strip()
    raise ValueError('Unclosed matrix or vector bracket')


def _plain_vector(source):
    group, remainder = _take_bracket_group(source)
    if remainder:
        raise ValueError('Unexpected text after vector')
    values = _split_top_level(group[1:-1], ',')
    if not values or any(not value for value in values):
        raise ValueError('Vectors cannot be empty')
    return values


def _plain_matrix(source):
    group, remainder = _take_bracket_group(source)
    if remainder:
        raise ValueError('Unexpected text after matrix')
    contents = group[1:-1]
    rows = _split_top_level(contents, ';')
    if len(rows) == 1:
        rows = _split_top_level(contents, ',')
    return [_plain_vector(row) for row in rows]


def _latex_matrices(source):
    blocks = []
    remaining = []
    cursor = 0
    while True:
        match = re.search(r'\\begin\{([A-Za-z]+)\}', source[cursor:])
        if not match:
            remaining.append(source[cursor:])
            break
        start = cursor + match.start()
        command_end = cursor + match.end()
        environment = match.group(1)
        if environment not in ('matrix', 'bmatrix', 'pmatrix'):
            raise ValueError('Use matrix, bmatrix, or pmatrix notation')
        end_token = r'\end{' + environment + '}'
        end = source.find(end_token, command_end)
        if end < 0:
            raise ValueError('Unclosed LaTeX matrix')
        remaining.append(source[cursor:start])
        body = source[command_end:end]
        rows = [row.strip() for row in re.split(r'\\|\n', body) if row.strip()]
        blocks.append([[_latex_expression(cell.strip()) for cell in row.split('&')] for row in rows])
        cursor = end + len(end_token)
    return blocks, ''.join(remaining)


def _flatten_matrix_vector(matrix):
    if all(len(row) == 1 for row in matrix):
        return [row[0] for row in matrix]
    if len(matrix) == 1:
        return matrix[0]
    raise ValueError('A vector must have one row or one column')


def _matrix_residuals(equation, variables):
    if equation.count('=') != 1:
        raise ValueError('Enter one Ax=b matrix equation at a time')
    left, right = equation.split('=')
    if '\\begin{' in equation:
        left_blocks, left_text = _latex_matrices(left)
        right_blocks, right_text = _latex_matrices(right)
        if len(left_blocks) != 2 or len(right_blocks) != 1:
            raise ValueError('Ax=b needs one matrix, one variable vector, and one result vector')
        left_text = re.sub(r'\\(?:cdot|times)|\*', '', left_text).strip()
        if left_text or right_text.strip():
            raise ValueError('Unexpected text outside the matrix and vectors')
        matrix = left_blocks[0]
        vector = _flatten_matrix_vector(left_blocks[1])
        values = _flatten_matrix_vector(right_blocks[0])
    else:
        matrix_text, left_remainder = _take_bracket_group(left)
        matrix = _plain_matrix(matrix_text)
        left_remainder = re.sub(r'^(?:\\cdot|\\times|\*)\s*', '', left_remainder).strip()
        vector_text, left_remainder = _take_bracket_group(left_remainder)
        if left_remainder:
            raise ValueError('Unexpected text after the variable vector')
        vector = _plain_vector(vector_text)
        values = _plain_vector(right)

    vector_names = [_latex_expression(value) for value in vector]
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) for name in vector_names):
        raise ValueError('The Ax=b vector must contain variable names only')
    if variables and vector_names != variables:
        raise ValueError('The variable vector must match the Variables field in order')
    if not variables:
        variables = vector_names
    row_count = len(matrix)
    column_count = len(matrix[0]) if matrix else 0
    if (not matrix or any(len(row) != column_count for row in matrix)
            or column_count != len(vector) or row_count != len(values)):
        raise ValueError('Matrix and vector dimensions do not match')
    if row_count != len(variables):
        raise ValueError('SciPy root requires a square system: rows must equal variables')

    residuals = []
    for row, target in zip(matrix, values):
        terms = ['(' + coefficient + ')*(' + variable + ')'
                 for coefficient, variable in zip(row, vector_names)]
        residuals.append('(' + '+'.join(terms) + ')-(' + target + ')')
    return residuals


def _residuals(equations, variables=None):
    if '\\begin{' in equations or equations.lstrip().startswith('[['):
        return _matrix_residuals(equations.strip().replace('$', ''), variables or [])
    residuals = []
    for line in equations.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.count('=') != 1:
            raise ValueError('Enter one equality per line, such as x^2 + y^2 = 25')
        left, right = line.split('=')
        residuals.append('(' + _latex_expression(left) + ')-(' + _latex_expression(right) + ')')
    if not residuals:
        raise ValueError('Enter at least one equation')
    return residuals


def _parse_csv_numbers(source, field_name):
    try:
        return [float(value.strip()) for value in source.split(',')]
    except Exception:
        raise ValueError(field_name + ' must be comma-separated numbers')


def _install_controls(app):
    existing = document.getElementById(_PANEL_ID)
    if existing:
        existing.parentNode.removeChild(existing)

    panel = document.createElement('section')
    panel.id = _PANEL_ID
    panel.style.cssText = (
        'box-sizing:border-box;width:1050px;max-width:95vw;padding:20px 24px 18px;'
        'margin:0 0 12px;background:#191f22;border:1px solid #34413e;color:#e5eee8;'
        'font:13px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace;'
    )
    panel.innerHTML = '''
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:14px">
        <strong style="font-size:18px;color:#66e0b1">ROOT / NONLINEAR SYSTEMS</strong>
        <span style="color:#899d97">SciPy optimize.root · Pyodide worker · lazy startup</span>
      </div>
            <form id="solver-form" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:12px;align-items:end">
                <label style="display:grid;grid-column:1/-1;gap:6px;color:#b6c6bf">Example
                    <select id="solver-example" style="box-sizing:border-box;width:100%;max-width:420px;background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:10px;font:13px ui-monospace,SFMono-Regular,Consolas,monospace">
                        <option value="nonlinear" selected>Nonlinear system</option>
                        <option value="exp-command">Exponential: exp(x)</option>
                        <option value="exp-power">Exponential: e^x</option>
                        <option value="log-natural">Natural logarithm: ln(x)</option>
                        <option value="log-base">Base logarithm: log_2(x)</option>
                        <option value="trig-sincos">Trigonometric: sin(x) = cos(x)</option>
                        <option value="trig-tan">Trigonometric: tan(x) = 1</option>
                        <option value="matrix-brackets">Ax=b: bracket notation</option>
                        <option value="matrix-latex">Ax=b: LaTeX bmatrix</option>
                    </select>
                </label>
                <label style="display:grid;grid-column:1/-1;gap:6px;color:#b6c6bf">Equations <span style="color:#899d97">one LaTeX-style equality per line</span>
          <textarea id="solver-equations" rows="3" spellcheck="false" style="box-sizing:border-box;width:100%;resize:vertical;background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:9px;font:13px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace">x^2 + y^2 = 25
x - y = 1</textarea>
        </label>
        <label style="display:grid;gap:6px;color:#b6c6bf">Variables
          <input id="solver-variables" value="x, y" autocomplete="off" style="box-sizing:border-box;width:100%;background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:10px;font:13px ui-monospace,SFMono-Regular,Consolas,monospace">
        </label>
        <label style="display:grid;gap:6px;color:#b6c6bf">Initial guess
          <input id="solver-initial" value="2, 1" autocomplete="off" style="box-sizing:border-box;width:100%;background:#0f1417;color:#e5eee8;border:1px solid #43524d;padding:10px;font:13px ui-monospace,SFMono-Regular,Consolas,monospace">
        </label>
        <button id="solver-submit" type="submit" style="height:39px;padding:0 16px;border:0;background:#66e0b1;color:#10201a;font-weight:bold;font-family:inherit;cursor:pointer">Solve</button>
    </form>
    <div id="solver-note" style="margin-top:10px;color:#899d97">Supports powers, fractions, roots, exp, ln, log bases, and trig functions in radians. For Ax=b, try [[2,1],[1,3]] * [x,y] = [5,7]. First solve downloads SciPy.</div>
    '''
    container = document.getElementById('canvas-container')
    container.parentNode.insertBefore(panel, container)

    def submit(event):
        event.preventDefault()
        variable_names = [item.strip() for item in document['solver-variables'].value.split(',')]
        try:
            residual_expressions = _residuals(document['solver-equations'].value, variable_names)
            initial_values = _parse_csv_numbers(document['solver-initial'].value, 'Initial guess')
            if len(variable_names) != len(initial_values):
                raise ValueError('Enter one initial value for each variable')
            if len(residual_expressions) != len(variable_names):
                raise ValueError('For root finding, equations and variables must have the same count')
        except Exception as error:
            app.error = str(error)
            app.status = 'Check the system'
            app.result = None
            return

        app.equationLines = [line.strip() for line in document['solver-equations'].value.splitlines() if line.strip()]
        app.variableNames = variable_names
        app.initialValues = initial_values
        app.result = None
        app.error = None
        app.status = 'Starting Pyodide and loading SciPy...'
        app.busy = True
        aio.run(_solve(app, residual_expressions, variable_names, initial_values))

    def load_example(event):
        label, equations, variables, initial = _EXAMPLES[document['solver-example'].value]
        document['solver-equations'].value = equations
        document['solver-variables'].value = variables
        document['solver-initial'].value = initial
        app.equationLines = [line.strip() for line in equations.splitlines() if line.strip()]
        app.variableNames = [item.strip() for item in variables.split(',')]
        app.initialValues = _parse_csv_numbers(initial, 'Initial guess')
        app.result = None
        app.error = None
        app.status = 'Example loaded: ' + label

    document['solver-example'].bind('change', load_example)
    document['solver-form'].bind('submit', submit)


async def _solve(app, residual_expressions, variable_names, initial_values):
    try:
        app.result = await root(residual_expressions, initial_values, variables=variable_names)
        app.status = 'Converged' if app.result['success'] else 'Solver stopped without convergence'
    except Exception as error:
        app.error = str(error)
        app.status = 'Solve failed'
    finally:
        app.busy = False


def onAppStart(app):
    app.width = 1050
    app.height = 700
    app.stepsPerSecond = 20
    app.background = BG
    app.status = 'Ready · enter a system and solve'
    app.busy = False
    app.error = None
    app.result = None
    app.equationLines = ['x^2 + y^2 = 25', 'x - y = 1']
    app.variableNames = ['x', 'y']
    app.initialValues = [2.0, 1.0]
    _install_controls(app)


def onStep(app):
    pass


def _draw_residual_chart(app):
    result = app.result
    chart_x, chart_y, chart_width = 90, 370, 500
    drawLabel('RESIDUAL NORM', chart_x, chart_y - 28, size=12, fill=MUTED, align='left')
    drawLine(chart_x, chart_y, chart_x + chart_width, chart_y, fill=rgb(67, 82, 77), lineWidth=1)
    initial = max(float(result['initialResidualNorm']), 1e-16)
    final = max(float(result['residualNorm']), 1e-16)
    maximum = max(initial, final)
    for index, (label, value, color) in enumerate((
        ('Initial', initial, GOLD), ('Solved', final, MINT)
    )):
        y = chart_y + 35 + index * 64
        width = chart_width * min(1.0, value / maximum)
        drawLabel(label, chart_x, y, size=13, fill=INK, align='left')
        drawRect(chart_x, y + 13, chart_width, 14, fill=rgb(35, 46, 43))
        drawRect(chart_x, y + 13, max(2, width), 14, fill=color)
        drawLabel('{:.3g}'.format(value), chart_x + chart_width, y, size=12, fill=color, align='right')
    drawLabel('Before / after residual size, not iteration history', chart_x, chart_y + 174, size=11, fill=MUTED, align='left')


def _format_number(value, precision=10):
    try:
        return ('{:.%dg}' % precision).format(float(value))
    except Exception:
        return str(value)


def redrawAll(app):
    drawRect(0, 0, app.width, app.height, fill=BG)
    drawLabel('NONLINEAR ROOT FINDER', 54, 48, size=22, fill=INK, bold=True, align='left')
    drawLabel('SCIPY / OPTIMIZE.ROOT', 54, 77, size=12, fill=MINT, align='left')
    drawLine(54, 105, 996, 105, fill=rgb(55, 69, 64), lineWidth=1)

    drawLabel(app.status, 54, 140, size=15, fill=GOLD if app.busy else MINT if app.result and app.result['success'] else RED if app.error else MUTED, align='left')
    if app.error:
        drawLabel(app.error[:110], 54, 169, size=12, fill=RED, align='left')

    drawLabel('SYSTEM', 54, 220, size=11, fill=MUTED, align='left')
    for index, equation in enumerate(app.equationLines[:5]):
        drawLabel(equation[:70], 54, 251 + index * 27, size=15, fill=INK, align='left')

    if not app.result:
        drawLabel('Enter equations above, then solve.', 54, 570, size=14, fill=MUTED, align='left')
        return

    _draw_residual_chart(app)
    drawLine(650, 145, 650, 620, fill=rgb(55, 69, 64), lineWidth=1)
    drawLabel('SOLUTION', 700, 178, size=12, fill=MUTED, align='left')
    for index, value in enumerate(app.result['x']):
        name = app.variableNames[index]
        drawLabel(name + ' =', 700, 225 + index * 48, size=18, fill=INK, align='left')
        drawLabel(_format_number(value), 970, 225 + index * 48, size=20, fill=MINT, bold=True, align='right')
    drawLabel('Evaluations', 700, 365, size=13, fill=MUTED, align='left')
    drawLabel(str(app.result['nfev']), 970, 365, size=14, fill=INK, align='right')
    drawLabel('Residuals', 700, 410, size=13, fill=MUTED, align='left')
    for index, value in enumerate(app.result['fun']):
        drawLabel('F{} = {}'.format(index + 1, _format_number(value, 3)), 700, 442 + index * 25, size=13, fill=INK, align='left')
