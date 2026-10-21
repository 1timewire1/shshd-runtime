"""A small numeric expression language compiled to native KiWi instructions.

No Python evaluation, calls, attribute access, indexing or external data.
Arithmetic uses the VM's signed-word wrapping and truncating division.
"""
import ast
from .model import ProjectError

BINARY = {ast.Add: 0x50, ast.Sub: 0x51, ast.Mult: 0x52, ast.FloorDiv: 0x53, ast.Mod: 0x54}
COMPARE = {ast.Eq: 0x0a, ast.NotEq: 0x0b, ast.Gt: 0x0c, ast.GtE: 0x0d, ast.Lt: 0x0e, ast.LtE: 0x0f}


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
        else:
            raise ProjectError('Use integers, variables, arithmetic, comparisons, and/or/not only')
    check(tree)
    return tree, names


def emit(asm, tree, read_variable):
    if isinstance(tree, ast.Constant):
        asm.emit(0x1a, int(tree.value))
    elif isinstance(tree, ast.Name):
        read_variable(tree.id)
    elif isinstance(tree, ast.UnaryOp):
        if isinstance(tree.op, ast.USub):
            asm.emit(0x1a, 0)
            emit(asm, tree.operand, read_variable)
            asm.emit(0x51)
        else:
            emit(asm, tree.operand, read_variable)
            if isinstance(tree.op, ast.Not):
                asm.emit(0x1a, 0); asm.emit(0x0a)
    elif isinstance(tree, ast.BinOp):
        emit(asm, tree.left, read_variable); emit(asm, tree.right, read_variable)
        asm.emit(BINARY[type(tree.op)])
    elif isinstance(tree, ast.BoolOp):
        stop, end = ('boolean', len(asm.code), 0), ('boolean', len(asm.code), 1)
        conjunction = isinstance(tree.op, ast.And)
        for value in tree.values:
            emit(asm, value, read_variable)
            if conjunction:
                asm.emit(0x1a, 0); asm.emit(0x0a)
            asm.jump_if(stop)
        asm.emit(0x1a, int(conjunction)); asm.jump(end)
        asm.labels[stop] = len(asm.code)
        asm.emit(0x1a, int(not conjunction))
        asm.labels[end] = len(asm.code)
    elif isinstance(tree, ast.Compare):
        for i, (left, op, right) in enumerate(zip((tree.left, *tree.comparators), tree.ops, tree.comparators)):
            emit(asm, left, read_variable); emit(asm, right, read_variable)
            asm.emit(COMPARE[type(op)])
            if i: asm.emit(0x12)
