"""A parser for the Lua 5.1 subset the cancelled Xbox 360 SHS prototype's scripts use (x360.py).

It covers statements (assignment, calls, if/elseif/else, while, numeric for, local, function, return, break, do) and
expressions (literals, names, fields, indexing, calls, method calls, unary/binary operators with Lua's precedence,
table constructors, anonymous functions), with Lua's comments and string forms. It builds tuples; nothing is run.

Statements:  ('assign', [target...], [expr...])  ('call', expr)  ('if', [(cond, block)...], else_block or None)
             ('while', cond, block)  ('for', name, start, stop, step, block)  ('local', [name...], [expr...])
             ('function', name_expr, params, block)  ('return', [expr...])  ('break',)  ('do', block)
Expressions: ('num', n)  ('str', s)  ('bool', b)  ('nil',)  ('name', s)  ('field', obj, name)  ('index', obj, key)
             ('callx', func, [args])  ('method', obj, name, [args])  ('binop', op, a, b)  ('unop', op, a)
             ('table', [(key or None, value)...])  ('lambda', params, block)  ('vararg',)
"""
import re

KEYWORDS = {'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function', 'if', 'in', 'local', 'nil',
            'not', 'or', 'repeat', 'return', 'then', 'true', 'until', 'while'}
# Binary operators: (left, right) binding power, as in Lua 5.1's parser (lparser.c priority[]).
BINARY = {'or': (1, 1), 'and': (2, 2), '<': (3, 3), '>': (3, 3), '<=': (3, 3), '>=': (3, 3), '~=': (3, 3),
          '==': (3, 3), '..': (5, 4), '+': (6, 6), '-': (6, 6), '*': (7, 7), '/': (7, 7), '%': (7, 7),
          '^': (10, 9)}
UNARY_PRIORITY = 8
TOKEN = re.compile(r'''
    (?P<space>\s+)
  | (?P<comment>--(?:\[(?P<ceq>=*)\[[\s\S]*?\](?P=ceq)\]|[^\n]*))
  | (?P<long>\[(?P<leq>=*)\[[\s\S]*?\](?P=leq)\])
  | (?P<num>0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<str>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')
  | (?P<name>[A-Za-z_][A-Za-z_0-9]*)
  | (?P<op>\.\.\.|\.\.|==|~=|<=|>=|[-+*/%^\#<>=(){}\[\];:,.])
''', re.VERBOSE)
ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', 'a': '\a', 'b': '\b', 'f': '\f', 'v': '\v', '\\': '\\', '"': '"',
           "'": "'", '\n': '\n'}


class LuaSyntaxError(ValueError):
    pass


def unquote(token):
    body, out, i = token[1:-1], [], 0
    while i < len(body):
        c = body[i]
        if c != '\\':
            out.append(c); i += 1
            continue
        nxt = body[i + 1]
        if nxt.isdigit():
            digits = re.match(r'\d{1,3}', body[i + 1:]).group(0)
            out.append(chr(int(digits))); i += 1 + len(digits)
        else:
            out.append(ESCAPES.get(nxt, nxt)); i += 2
    return ''.join(out)


def tokenize(source):
    tokens, pos = [], 0
    while pos < len(source):
        m = TOKEN.match(source, pos)
        if not m:
            raise LuaSyntaxError(f'unexpected {source[pos:pos + 20]!r} at {pos}')
        pos = m.end()
        kind = m.lastgroup if m.lastgroup not in ('ceq', 'leq') else None
        if m.group('space') or m.group('comment'):
            continue
        if m.group('long'):
            text = m.group('long')
            level = len(m.group('leq'))
            body = text[2 + level:-2 - level]
            tokens.append(('str', body[1:] if body.startswith('\n') else body))
        elif m.group('num'):
            text = m.group('num')
            tokens.append(('num', int(text, 16) if text[:2].lower() == '0x' else float(text)))
        elif m.group('str'):
            tokens.append(('str', unquote(m.group('str'))))
        elif m.group('name'):
            text = m.group('name')
            tokens.append(('kw' if text in KEYWORDS else 'name', text))
        else:
            tokens.append(('op', m.group('op')))
        del kind
    tokens.append(('eof', None))
    return tokens


class Parser:
    def __init__(self, source):
        self.tokens = tokenize(source)
        self.i = 0

    def peek(self, offset=0):
        return self.tokens[self.i + offset]

    def next(self):
        token = self.tokens[self.i]
        self.i += 1
        return token

    def check(self, kind, value=None):
        token = self.peek()
        return token[0] == kind and (value is None or token[1] == value)

    def accept(self, kind, value=None):
        if self.check(kind, value):
            return self.next()
        return None

    def expect(self, kind, value=None):
        token = self.accept(kind, value)
        if token is None:
            raise LuaSyntaxError(f'expected {value or kind}, got {self.peek()} (token {self.i})')
        return token

    # -- statements -----------------------------------------------------------------------------------------------
    def chunk(self):
        block = self.block()
        self.expect('eof')
        return block

    def block(self):
        statements = []
        while not (self.check('eof') or self.check('kw', 'end') or self.check('kw', 'else')
                   or self.check('kw', 'elseif') or self.check('kw', 'until')):
            statement = self.statement()
            if statement is not None:
                statements.append(statement)
        return statements

    def statement(self):
        if self.accept('op', ';'):
            return None
        if self.accept('kw', 'if'):
            arms = [(self.expr(), self.then_block())]
            otherwise = None
            while True:
                if self.accept('kw', 'elseif'):
                    arms.append((self.expr(), self.then_block()))
                elif self.accept('kw', 'else'):
                    otherwise = self.block()
                    self.expect('kw', 'end')
                    break
                else:
                    self.expect('kw', 'end')
                    break
            return ('if', arms, otherwise)
        if self.accept('kw', 'while'):
            cond = self.expr()
            self.expect('kw', 'do')
            body = self.block()
            self.expect('kw', 'end')
            return ('while', cond, body)
        if self.accept('kw', 'do'):
            body = self.block()
            self.expect('kw', 'end')
            return ('do', body)
        if self.accept('kw', 'for'):
            name = self.expect('name')[1]
            if self.accept('op', '='):
                start = self.expr(); self.expect('op', ','); stop = self.expr()
                step = self.expr() if self.accept('op', ',') else ('num', 1)
                self.expect('kw', 'do'); body = self.block(); self.expect('kw', 'end')
                return ('for', name, start, stop, step, body)
            names = [name]
            while self.accept('op', ','):
                names.append(self.expect('name')[1])
            self.expect('kw', 'in')
            iterators = self.expr_list()
            self.expect('kw', 'do'); body = self.block(); self.expect('kw', 'end')
            return ('forin', names, iterators, body)
        if self.accept('kw', 'repeat'):
            body = self.block(); self.expect('kw', 'until')
            return ('repeat', body, self.expr())
        if self.accept('kw', 'function'):
            target = ('name', self.expect('name')[1])
            while self.check('op', '.') or self.check('op', ':'):
                self.next()
                target = ('field', target, self.expect('name')[1])
            params, body = self.function_body()
            return ('function', target, params, body)
        if self.accept('kw', 'local'):
            if self.accept('kw', 'function'):
                name = self.expect('name')[1]
                params, body = self.function_body()
                return ('function', ('name', name), params, body)
            names = [self.expect('name')[1]]
            while self.accept('op', ','):
                names.append(self.expect('name')[1])
            values = self.expr_list() if self.accept('op', '=') else []
            return ('local', names, values)
        if self.accept('kw', 'return'):
            values = [] if self.check('kw', 'end') or self.check('eof') or self.check('op', ';') else self.expr_list()
            return ('return', values)
        if self.accept('kw', 'break'):
            return ('break',)
        target = self.suffixed()
        if self.check('op', '=') or self.check('op', ','):
            targets = [target]
            while self.accept('op', ','):
                targets.append(self.suffixed())
            self.expect('op', '=')
            return ('assign', targets, self.expr_list())
        if target[0] not in ('callx', 'method'):
            raise LuaSyntaxError(f'not a statement: {target} (token {self.i})')
        return ('call', target)

    def then_block(self):
        self.expect('kw', 'then')
        return self.block()

    def function_body(self):
        self.expect('op', '(')
        params = []
        while not self.check('op', ')'):
            if self.accept('op', '...'):
                params.append('...')
            else:
                params.append(self.expect('name')[1])
            if not self.accept('op', ','):
                break
        self.expect('op', ')')
        body = self.block()
        self.expect('kw', 'end')
        return params, body

    # -- expressions ----------------------------------------------------------------------------------------------
    def expr_list(self):
        values = [self.expr()]
        while self.accept('op', ','):
            values.append(self.expr())
        return values

    def expr(self, limit=0):
        token = self.peek()
        if token in (('kw', 'not'), ('op', '-'), ('op', '#')):
            self.next()
            left = ('unop', token[1], self.expr(UNARY_PRIORITY))
        else:
            left = self.simple()
        while True:
            token = self.peek()
            op = token[1] if token[0] in ('op', 'kw') else None
            if op not in BINARY or BINARY[op][0] <= limit:
                return left
            self.next()
            left = ('binop', op, left, self.expr(BINARY[op][1]))

    def simple(self):
        kind, value = self.peek()
        if kind == 'num':
            self.next(); return ('num', value)
        if kind == 'str':
            self.next(); return ('str', value)
        if (kind, value) == ('kw', 'true'):
            self.next(); return ('bool', True)
        if (kind, value) == ('kw', 'false'):
            self.next(); return ('bool', False)
        if (kind, value) == ('kw', 'nil'):
            self.next(); return ('nil',)
        if (kind, value) == ('op', '...'):
            self.next(); return ('vararg',)
        if (kind, value) == ('op', '{'):
            return self.table()
        if (kind, value) == ('kw', 'function'):
            self.next()
            params, body = self.function_body()
            return ('lambda', params, body)
        return self.suffixed()

    def primary(self):
        if self.accept('op', '('):
            inner = self.expr()
            self.expect('op', ')')
            return inner
        return ('name', self.expect('name')[1])

    def suffixed(self):
        node = self.primary()
        while True:
            if self.accept('op', '.'):
                node = ('field', node, self.expect('name')[1])
            elif self.accept('op', '['):
                key = self.expr()
                self.expect('op', ']')
                node = ('index', node, key)
            elif self.accept('op', ':'):
                name = self.expect('name')[1]
                node = ('method', node, name, self.call_args())
            elif self.check('op', '(') or self.check('str') or self.check('op', '{'):
                node = ('callx', node, self.call_args())
            else:
                return node

    def call_args(self):
        if self.check('str'):
            return [('str', self.next()[1])]
        if self.check('op', '{'):
            return [self.table()]
        self.expect('op', '(')
        args = [] if self.check('op', ')') else self.expr_list()
        self.expect('op', ')')
        return args

    def table(self):
        self.expect('op', '{')
        fields = []
        while not self.check('op', '}'):
            if self.check('op', '['):
                self.next(); key = self.expr(); self.expect('op', ']'); self.expect('op', '=')
                fields.append((key, self.expr()))
            elif self.check('name') and self.peek(1) == ('op', '='):
                key = ('str', self.next()[1]); self.next()
                fields.append((key, self.expr()))
            else:
                fields.append((None, self.expr()))
            if not (self.accept('op', ',') or self.accept('op', ';')):
                break
        self.expect('op', '}')
        return ('table', fields)


def parse(source):
    """A chunk of Lua source -> its block (a list of statements)."""
    return Parser(source).chunk()


def dotted(expr):
    """'a.b.c' for a name/field chain (a string index counts as a field), else None."""
    if expr[0] == 'name':
        return expr[1]
    if expr[0] == 'field':
        head = dotted(expr[1])
        return None if head is None else f'{head}.{expr[2]}'
    if expr[0] == 'index' and expr[2][0] == 'str':
        head = dotted(expr[1])
        return None if head is None else f'{head}.{expr[2][1]}'
    return None
