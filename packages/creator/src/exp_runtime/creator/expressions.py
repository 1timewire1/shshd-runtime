"""A small numeric expression language compiled to native KiWi instructions.

No Python evaluation, attribute access or indexing. The only calls are the game-state reads in FUNCTIONS, compiled to
their native services; a character's ID may name their owner. Arithmetic uses the VM's signed-word wrapping and
truncating division.
"""
import ast
from .model import ProjectError

BINARY = {ast.Add: 0x50, ast.Sub: 0x51, ast.Mult: 0x52, ast.FloorDiv: 0x53, ast.Mod: 0x54}
COMPARE = {ast.Eq: 0x0a, ast.NotEq: 0x0b, ast.Gt: 0x0c, ast.GtE: 0x0d, ast.Lt: 0x0e, ast.LtE: 0x0f}
# name: (service, argument count). prop(owner, key) reads a numeric property (53), bit(owner, key, n) one of its bits
# (51), art(character) a character's portrait base (73).
FUNCTIONS = {'prop': (53, 2), 'bit': (51, 3), 'art': (73, 1), 'build': (70, 1)}
# build(n), the app build query (70): 2 and 3 are constants, 9 is 1 and 10 tells whether the in-app store is available.
BUILD_SELECTORS = (2, 3, 9, 10)
RESERVED_OWNER = -30000


def constant(node):
    """The value of an integer literal, including a negated one, else None."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = constant(node.operand)
        return None if value is None else -value
    return node.value if isinstance(node, ast.Constant) and type(node.value) is int else None


def has_calls(tree):
    return any(isinstance(node, ast.Call) for node in ast.walk(tree))


def parse(expression):
    if not isinstance(expression, str) or len(expression) > 2000:
        raise ProjectError('Expression must be at most 2000 characters')
    try:
        tree = ast.parse(expression or '0', mode='eval').body
    except (SyntaxError, RecursionError) as error:
        raise ProjectError(f'Invalid numeric expression: {expression}') from error
    if sum(1 for _ in ast.walk(tree)) > 256:
        raise ProjectError('Expression is too complex')
    names = set()
    def check(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, bool):
            if not -32768 <= node.value <= 32767:
                raise ProjectError('Expression constants must fit a signed 16-bit word')
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.BinOp) and type(node.op) in BINARY:
            check(node.left); check(node.right)
            if isinstance(node.op, (ast.FloorDiv, ast.Mod)) and isinstance(node.right, ast.Constant) and node.right.value == 0:
                raise ProjectError('Division by zero in expression')
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.Not, ast.UAdd)):
            # -32768 is represented as unary minus over the positive literal.
            if isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) and node.operand.value == 32768:
                return
            check(node.operand)
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            for value in node.values: check(value)
        elif isinstance(node, ast.Compare) and all(type(op) in COMPARE for op in node.ops):
            for value in (node.left, *node.comparators): check(value)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS
              and not node.keywords and len(node.args) == FUNCTIONS[node.func.id][1]):
            owner, *rest = node.args
            if node.func.id == 'build':
                if constant(owner) not in BUILD_SELECTORS:
                    raise ProjectError('build() takes one of the selectors 2, 3, 9 or 10')
                return
            if not (isinstance(owner, ast.Constant) and isinstance(owner.value, str) and owner.value):
                check(owner)
            if constant(owner) == RESERVED_OWNER:
                raise ProjectError('Owner -30000 is reserved for multi-scene authoring state')
            for value in rest: check(value)
        else:
            raise ProjectError('Use integers, variables, arithmetic, comparisons, and/or/not, '
                               'and prop(owner, key), bit(owner, key, n), art(character) or build(n) only')
    check(tree)
    return tree, names


def characters(tree):
    """Character IDs named as owners."""
    return {node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)}


def emit(asm, tree, read_variable, character=None):
    """`character(id)` gives the native number of a character named as an owner."""
    def walk(tree):
        if isinstance(tree, ast.Call):
            service, count = FUNCTIONS[tree.func.id]
            for argument in tree.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    if character is None: raise ProjectError('Character owners need a character table')
                    asm.emit(0x1a, character(argument.value))
                else:
                    walk(argument)
            asm.emit(0x1f, service << 8 | count)
            asm.emit(0x21)
        elif isinstance(tree, ast.Constant):
            asm.emit(0x1a, int(tree.value))
        elif isinstance(tree, ast.Name):
            read_variable(tree.id)
        elif isinstance(tree, ast.UnaryOp):
            if isinstance(tree.op, ast.USub):
                asm.emit(0x1a, 0)
                walk(tree.operand)
                asm.emit(0x51)
            else:
                walk(tree.operand)
                if isinstance(tree.op, ast.Not):
                    asm.emit(0x1a, 0); asm.emit(0x0a)
        elif isinstance(tree, ast.BinOp):
            walk(tree.left); walk(tree.right)
            asm.emit(BINARY[type(tree.op)])
        elif isinstance(tree, ast.BoolOp):
            stop, end = ('boolean', len(asm.code), 0), ('boolean', len(asm.code), 1)
            conjunction = isinstance(tree.op, ast.And)
            for value in tree.values:
                walk(value)
                if conjunction:
                    asm.emit(0x1a, 0); asm.emit(0x0a)
                asm.jump_if(stop)
            asm.emit(0x1a, int(conjunction)); asm.jump(end)
            asm.labels[stop] = len(asm.code)
            asm.emit(0x1a, int(not conjunction))
            asm.labels[end] = len(asm.code)
        elif isinstance(tree, ast.Compare):
            for i, (left, op, right) in enumerate(zip((tree.left, *tree.comparators), tree.ops, tree.comparators)):
                walk(left); walk(right)
                asm.emit(COMPARE[type(op)])
                if i: asm.emit(0x12)
    walk(tree)
