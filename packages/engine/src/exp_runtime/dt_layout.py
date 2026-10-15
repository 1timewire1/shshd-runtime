"""The Decision Tree's layout and drawing, ported from the iOS app's `DTNode` classes (decompiled).

Every node type has a class in the app (`DTNode_Event_Generic`, `DTNode_Choice3`, `DTNode_AutoBranch2`, ...) that fixes where
its children go relative to it, how tall it is, how wide its labels make it, and what its icon, outline, stubs and labels look
like. Lengths are in units of `sz`, the zoom (50 when the app starts, pinch-zoomed between 10 and 60):

* a node's `y` is its top; its icon is centered about `y + sz`, and the next row is `overhead_dy` below (`2 sz + 8 sz/35`, more
  for events with an `exw`);
* the children of a node with N exits sit at fixed offsets across (`+-0.7 sz` for two or three, `-0.45 ... 0.45 sz` for four,
  `-0.5 ... 0.5 sz` for five); a branch node instead spaces its children by how wide each one's own extents are;
* an extent is how far a node and everything under it reaches to the left, right and down, labels included; a branch node also
  works out where its branches meet again (at a *join* node) and the story carries on from that point.

`Layout` works the positions out; `Layout.draw_ops()` then lists what to draw -- exit stubs and the lines to the children, icons,
outlines, labels -- in the order the app's tiles draw them, in tree coordinates, for any renderer to paint.
"""
from dataclasses import dataclass
import math
import sys

JOIN = 0x4c8
BRANCHES = range(0x4c3, 0x4c8)          # `type - 0x4c3 < 5`: the nodes whose children later meet at a join
AUTO_BRANCHES = range(0x4c5, 0x4c8)
DEFAULT_SZ = 52.7                       # `DTNode::sz` in the app's screenshots (its static starts at 50; the rows and stub offsets of a fresh tree measure 52.7)
SZ_RANGE = (10.0, 60.0)                 # the zoom limits (`setMinimumZoomScale: 10 / sz`, maximum 60 / sz)
FONT_UNIT = 35.0                        # the labels' "original size" scale: a length at size 35 is drawn at sz / 35
SPLIT_LENGTH = 55.0                     # a label longer than this (at its original size) is broken in two at a space
BIG = 50000.0

sys.setrecursionlimit(max(sys.getrecursionlimit(), 100_000))


@dataclass(frozen=True)
class Spec:
    exits: int
    layout: str = 'n'                   # 'n' (fixed offsets), 'branch2', 'branch3', 'even', 'join'
    overhead: str = 'base'              # 'base', 'event' (adds exw), 'football', 'quiz', 'auto', 'join'
    image: int = -1
    image_offset: tuple = (0.0, 1.0)
    image_scale: float = 105.0
    label_dy: float = 0.5               # the label's start right of the node centre, in sz (`get_label_dy`)
    label_dx_exw: bool = False          # events: the label also clears the widened box
    factor: float = 10 / 7
    shape: str = 'rect'
    stubs: str = 'none'
    stub_drop: float = 0.25             # where the diagonal stubs start below the icon centre, in sz
    child_labels: tuple = ()            # ((x, y) in sz, ...) per exit, about (node.x, node.y + label_origin)
    label_origin: float = 1.5


def _two(drop, x, y):
    return dict(stubs='two', stub_drop=drop, child_labels=((-x - 5 / 35, y), (x + 5 / 35, y)))


def _three(drop, x, y_side, y_mid):
    return dict(stubs='three', stub_drop=drop,
                child_labels=((-x - 5 / 35, y_side), (0.0, y_mid), (x + 5 / 35, y_side)))


def _event(image, **more):
    return Spec(1, 'n', 'event', image, (0.0, 0.993), 105.0, 0.5, True, shape='rect', stubs='one', stub_drop=0.125, **more)


_HEART = dict(image=1, image_offset=(-0.005, 1.05), image_scale=104.0, shape='heart')
_DIAMOND = dict(image=0, image_offset=(-0.005, 1.0), label_dy=0.7, shape='diamond')

SPECS = {
    0x4b2: Spec(0, 'n', 'event', 2, (0.0, 0.993), 105.0, 0.5, True, shape='rect'),
    0x4b3: _event(2), 0x4b4: _event(3), 0x4b5: _event(4), 0x4b6: _event(5), 0x4b7: _event(6),
    0x4b8: Spec(1, 'n', 'base', shape='heart', stubs='one', stub_drop=0.125, image=1, image_offset=(-0.005, 1.05),
                image_scale=104.0),
    0x4b9: Spec(2, 'n', 'base', **_HEART, **_two(0.125, 0.2, 0.1)),
    0x4ba: Spec(2, 'n', 'base', image=8, shape='circle', **_two(0.25, 0.2, 0.1)),
    0x4bb: Spec(3, 'n', 'base', image=8, shape='circle', **_three(0.25, 0.2, 0.1, 0.2)),
    0x4bc: Spec(2, 'n', 'base', image=9, shape='circle', **_two(0.25, 0.2, 0.1)),
    0x4bd: Spec(3, 'n', 'base', image=9, shape='circle', **_three(0.25, 0.2, 0.1, 0.2)),
    0x4be: Spec(2, 'n', 'football', 7, (0.0, 0.985), 105.0, 0.5, factor=16 / 7, shape='football', stubs='football',
                child_labels=((-0.2 - 5 / 35, 0.0), (0.2 + 5 / 35, 0.0)), label_origin=1.61),
    0x4bf: Spec(2, 'n', 'base', **_DIAMOND, **_two(0.25, 0.25, 0.15)),
    0x4c0: Spec(3, 'n', 'base', **_DIAMOND, **_three(0.25, 0.3, 0.2, 0.3)),
    0x4c1: Spec(4, 'n', 'quiz', 10, (0.0, 1.0), 104.0, 0.7, shape='triangle', stubs='quiz',
                child_labels=((-0.45, 0.5), (-0.15, 0.5), (0.15, 0.5), (0.45, 0.5))),
    0x4c2: Spec(5, 'n', 'quiz', 10, (0.0, 1.0), 104.0, 0.7, shape='triangle', stubs='final',
                child_labels=((-0.5, 0.5), (-0.25, 0.5), (0.0, 0.5), (0.25, 0.5), (0.5, 0.5))),
    0x4c3: Spec(2, 'branch2', 'base', **_DIAMOND, **_two(0.25, 0.25, 0.15)),
    0x4c4: Spec(3, 'branch3', 'base', **_DIAMOND, **_three(0.25, 0.3, 0.2, 0.3)),
    0x4c5: Spec(2, 'even', 'auto', label_dy=0.65, shape='dot', stubs='auto', **{'child_labels': ((-0.25 - 5 / 35, 0.15),
                                                                                              (0.25 + 5 / 35, 0.15))}),
    0x4c6: Spec(3, 'even', 'auto', label_dy=0.65, shape='dot', stubs='auto', child_labels=(
        (-0.3 - 5 / 35, 0.2), (0.0, 0.3), (0.3 + 5 / 35, 0.2))),
    0x4c7: Spec(4, 'even', 'auto', label_dy=0.65, shape='dot', stubs='auto', child_labels=(
        (-0.6, 0.4), (-0.2, 0.4), (0.2, 0.4), (0.6, 0.4))),
    0x4c8: Spec(1, 'join', 'join', shape='join'),
}
FIXED_OFFSETS = {0: (), 1: (0.0,), 2: (-0.7, 0.7), 3: (-0.7, 0.0, 0.7), 4: (-0.45, -0.15, 0.15, 0.45),
                 5: (-0.5, -0.25, 0.0, 0.25, 0.5)}
FIXED_MINIMUM = {0: 0.5, 1: 0.5, 2: 0.7, 3: 0.7, 4: 0.9, 5: 0.9}


class Metrics:
    """The label text measures the layout needs. A label is drawn in the outer-label font (size 10 at its original size) or the
    exit-line font (size 6); `length(text, kind)` is the width of a string in that font at its original size."""
    LINE_HEIGHT = 1.15

    def length(self, text, kind):
        return len(text) * (10 if kind == 'outer' else 6) * 0.55

    def line_height(self, kind):
        return (10 if kind == 'outer' else 6) * self.LINE_HEIGHT


class LabelText:
    """`DT2LineText`: a label of one or two lines (a string over 55 units long breaks at the space nearest its middle)."""

    def __init__(self, text, kind, metrics):
        self.text, self.kind, self.metrics = text, kind, metrics
        self.lines = self.split(text, kind, metrics)
        self.width_units = max((metrics.length(line, kind) for line in self.lines), default=0.0)

    @staticmethod
    def split(text, kind, metrics):
        if metrics.length(text, kind) > SPLIT_LENGTH:
            middle = len(text) // 2
            for i in range(middle):
                if middle + i < len(text) and text[middle + i] == ' ':
                    return [text[:middle + i], text[middle + i + 1:]]
                if middle - i >= 0 and text[middle - i] == ' ':
                    return [text[:middle - i], text[middle - i + 1:]]
        return [text]

    def block_width(self, sz):
        return self.width_units * sz / FONT_UNIT

    def text_height(self, sz):
        return len(self.lines) * self.metrics.line_height(self.kind) * sz / FONT_UNIT


class Node:
    """One node of the laid-out tree; `src` is our `DTNode` (or anything with the same fields)."""

    def __init__(self, src, layout, parent=None):
        self.src = src
        self.type = src.node_type
        self.spec = SPECS[self.type]
        self.parent = parent
        self.exw = getattr(src, 'exw', 0) / 100.0
        self.primary = bool(getattr(src, 'primary', True))
        self.ids = (src.uid, src.script)
        self.result_index = src.result_index or 0
        self.kids = [None] * self.spec.exits
        self.x = self.y = self.dx = self.dy = 0.0
        self.xneg = self.xpos = self.ypos = 0.0
        self.exit_width = 0.0
        self.partner = None                      # the branch node whose branches this join closes
        self.jx = self.jy = 0.0
        self.count = 0                           # how many branches meet at this join
        self.active = bool(getattr(src, 'active', False))
        self.path = bool(getattr(src, 'path', False))
        self.lower = LabelText(src.lower_label, 'outer', layout.metrics)
        labels = getattr(src, 'result_labels', {})
        self.exits = [LabelText(labels.get(i, ''), 'exit', layout.metrics) for i in range(self.spec.exits)]
        self.blank = LabelText('', 'outer', layout.metrics)
        self.layout = layout

    # -- what the class says about the node ---------------------------------------------------------------------------
    @property
    def sz(self):
        return self.layout.sz

    def present(self):
        return sum(kid is not None for kid in self.kids)

    def overhead(self):
        sz, kind = self.sz, self.spec.overhead
        if kind == 'event':
            return 2 * sz + sz * self.exw + 8 * sz / FONT_UNIT
        if kind == 'football':
            return 2 * sz
        if kind == 'quiz':
            return 2 * sz + 24 * sz / FONT_UNIT
        if kind == 'auto':
            return 0.0 if self.present() < 2 else float(int(2 * sz + 8 * sz / FONT_UNIT))
        if kind == 'join':
            return 0.0 if self.count < 2 else float(int(2 * sz))
        return 2 * sz + 8 * sz / FONT_UNIT

    def get_xneg(self):
        return self.sz * 0.25 if self.type == JOIN else self.xneg

    def get_xpos(self):
        return self.sz * 0.25 if self.type == JOIN else self.xpos

    def get_ypos(self):
        return self.overhead() if self.type == JOIN else self.ypos

    def label_width(self):
        sz = self.sz
        if self.spec.label_dx_exw:
            width = sz * self.spec.factor
            return width + width * self.exw * 0.5
        if self.type == 0x4be:
            return sz * self.spec.factor * 0.9
        return sz * self.spec.factor

    def label_a(self):                       # `get_label_dy`: where the label starts, right of the centre
        return self.sz * self.spec.label_dy

    def label_b(self):                       # `get_label_dx`
        if self.spec.label_dx_exw:
            return self.sz * self.exw
        return self.sz * 30 / FONT_UNIT if self.type == 0x4be else 0.0

    def label_c(self):                       # `get_label_dx3`: how far the label sits above the icon centre
        return self.sz * 0.13 if self.type == 0x4be else 0.0

    def image_id(self):
        if self.type == 0x4b3 and self.layout.root is self:
            return 0xb
        return self.spec.image


class Layout:
    def __init__(self, root_src, sz=DEFAULT_SZ, metrics=None, current=None, last_was_result=False):
        self.sz = float(sz)
        self.metrics = metrics or Metrics()
        self.current_src = current
        self.last_was_result = last_was_result
        self.root = None
        self.by_src = {}
        if root_src is not None:
            self.root = self._build(root_src, None)
            self.calculate(self.root, False, 0)
            self.propagate(self.root, False, 0)

    def _build(self, src, parent):
        node = Node(src, self, parent)
        self.by_src[id(src)] = node
        for slot, child in src.children.items():
            if slot < node.spec.exits:
                node.kids[slot] = self._build(child, node)
        return node

    def nodes(self):
        out, stack = [], [self.root] if self.root else []
        while stack:
            node = stack.pop()
            out.append(node)
            stack.extend(kid for kid in reversed(node.kids) if kid is not None)
        return out

    # -- extents ---------------------------------------------------------------------------------------------------------
    def calculate(self, node, deep, depth):
        """`DTNode::calculate_extents(bool, int)`; a branch node lays out its own branches (`Branch_base`)."""
        if node.spec.layout in ('branch2', 'branch3', 'even'):
            return self.calculate_branch(node)
        node.exit_width = 0.0
        stop = False
        if deep:
            if node.type == JOIN:
                depth -= 1
                stop = depth < 0
            elif node.type in BRANCHES:
                depth += 1
        if not stop:
            for index, kid in enumerate(node.kids):
                if kid is not None:
                    self.calculate(kid, deep, depth)
                node.exit_width = max(node.exit_width, node.exits[index].block_width(self.sz))
        self.internal(node)

    def limit(self, node, minimum):
        """`DTNode::limit_min_extents`."""
        sz = self.sz
        node.xneg = node.xpos = 0.0
        for kid in node.kids:
            if kid is not None:
                node.xneg = max(node.xneg, kid.get_xneg() - kid.dx)
                node.xpos = max(node.xpos, kid.dx + kid.get_xpos())
        a, b = node.label_a(), node.label_b()
        gap = 2 * sz / FONT_UNIT
        exits = (node.exit_width + a) + b * 0.5 + gap
        upper = max((node.blank.block_width(sz) + a) + b * 0.5 + gap, exits)
        node.xneg = max(node.xneg, upper + minimum)
        lower = max((node.lower.block_width(sz) + a) + b * 0.5 + gap, exits)
        node.xpos = max(node.xpos, lower + minimum)
        node.xneg += sz / FONT_UNIT
        node.xpos += sz / FONT_UNIT
        node.ypos = node.overhead()
        for kid in node.kids:
            if kid is not None:
                below = kid.dy if kid.type == JOIN else kid.dy + kid.ypos
                node.ypos = max(node.ypos, below)
        node.ypos += sz / FONT_UNIT

    def internal(self, node):
        """`calculate_extents_internal`: where each child sits, then this node's own extents."""
        sz, spec = self.sz, node.spec
        drop = node.overhead()
        kids = node.kids
        if spec.layout == 'n':
            for kid, offset in zip(kids, FIXED_OFFSETS[spec.exits]):
                if kid is not None:
                    kid.dx, kid.dy = sz * offset, drop
            self.limit(node, sz * FIXED_MINIMUM[spec.exits])
        elif spec.layout == 'join':
            if kids[0] is not None:
                kids[0].dx, kids[0].dy = 0.0, drop
            self.limit(node, sz * 0.02)
        elif spec.layout == 'branch2':
            self.branch2(node, drop)
            self.limit(node, sz * 0.7)
        elif spec.layout == 'branch3':
            self.branch3(node, drop)
            self.limit(node, sz * 0.7)
        else:
            return self.even(node, drop)

    def branch2(self, node, drop):
        sz = self.sz
        first, second = node.kids
        gap = sz / FONT_UNIT
        if first is None:
            if second is not None:
                second.dx, second.dy = sz * 0.7, drop
        elif second is None:
            first.dx, first.dy = sz * -0.7, drop
        else:
            first.dx = -0.5 * (gap + first.get_xpos() + second.get_xneg())
            first.dy = drop
            first.dx = min(first.dx, sz * -0.7)
            second.dx = first.dx + gap + first.get_xpos() + second.get_xneg()
            second.dy = drop
            second.dx = max(second.dx, sz * 0.7)

    def branch3(self, node, drop):
        sz = self.sz
        gap = sz / FONT_UNIT
        left, middle, right = node.kids
        if middle is not None:
            middle.dx, middle.dy = 0.0, drop
            if left is not None:
                left.dx = -(left.get_xpos() + middle.get_xneg()) - gap
                left.dy = drop
                left.dx = min(left.dx, sz * -0.7)
            if right is not None:
                right.dx = middle.get_xpos() + right.get_xneg() + gap
                right.dy = drop
                right.dx = max(right.dx, sz * 0.7)
        elif left is None:
            if right is not None:
                right.dx, right.dy = sz * 0.7, drop
        elif right is None:
            left.dx, left.dy = sz * -0.7, drop
        else:
            start = -0.5 * (gap + (left.get_xpos() + gap) + (right.get_xneg() + gap))
            left.dx = min(start, sz * -0.7)
            left.dy = drop
            right.dx = max(left.dx + left.get_xpos() + gap + right.get_xneg(), sz * 0.7)
            right.dy = drop

    def even(self, node, drop):
        """`Branch_Even_Dist`: the branches side by side, each clear of the next by its own extents."""
        sz = self.sz
        present = [kid for kid in node.kids if kid is not None]
        if len(present) > 1:
            gap = sz / FONT_UNIT
            total = gap
            for kid in present:
                total += kid.get_xpos() + kid.get_xneg() + gap
            total -= present[0].get_xneg() + present[-1].get_xpos()
            x = total * -0.5
            for kid in node.kids:
                if kid is None:
                    continue
                if kid is not present[0]:
                    x += kid.get_xneg()
                kid.dx, kid.dy = x, drop
                x += kid.get_xpos() + gap
            self.limit(node, sz * 0.7)
        else:
            for kid in present:
                kid.dx, kid.dy = 0.0, drop
            self.limit(node, sz * 0.25)

    def find_next_join(self, node, depth):
        if node.type == JOIN:
            depth -= 1
            if depth < 0:
                return node
        elif node.type in BRANCHES:
            depth += 1
        for kid in node.kids:
            if kid is not None:
                found = self.find_next_join(kid, depth)
                if found is not None:
                    return found
        return None

    def calculate_branch(self, node):
        """`DTNode_Branch_base::calculate_extents`: lay the branches out, find where they meet, and place the join."""
        sz = self.sz
        node.exit_width = 0.0
        joins = [None] * len(node.kids)
        count = 0
        for index, kid in enumerate(node.kids):
            if kid is None:
                continue
            join = self.find_next_join(kid, 0)
            joins[index] = join
            if join is not None:
                count += 1
                join.partner, join.jx, join.jy, join.count = None, 0.0, 0.0, 0
            node.exit_width = max(node.exit_width, node.exits[index].block_width(sz))
        for kid in node.kids:
            if kid is not None:
                self.calculate(kid, True, 0)
        node.x = node.y = 0.0
        self.internal(node)
        self.propagate(node, True, 0)
        low, bottom, right, top, total = BIG, 0.0, 0.0, BIG, 0.0
        for index, kid in enumerate(node.kids):
            if kid is not None and kid.type != JOIN:
                reach, base = kid.dx + kid.xpos, kid.dy + kid.ypos
                low, bottom, right, top = min(low, reach), max(bottom, base), max(right, reach), min(top, base)
            join = joins[index]
            if join is not None:
                low, bottom, right, top = min(low, join.x), max(bottom, join.y), max(right, join.x), min(top, join.y)
                total += join.x
        merge = total / count if count else 0.0
        if count > 1:
            merge = 0.0
        merge = min(max(merge, low), right)
        for join in joins:
            if join is not None:
                join.partner, join.count, join.jx, join.jy = node, count, merge, bottom
                join.x -= merge
        for join in joins:
            if join is not None and join.primary:
                self.calculate(join, False, 0)
                node.ypos += join.ypos - sz / FONT_UNIT
                node.xneg = max(node.xneg, join.xneg - merge)
                node.xpos = max(node.xpos, join.xpos + merge)

    def propagate(self, node, deep, depth):
        """`DTNode::propagate_location`: absolute positions from the children's offsets (a join carries on from its branch
        node's meeting point)."""
        if deep:
            if node.type == JOIN:
                depth -= 1
                if depth < 0:
                    return
            elif node.type in BRANCHES:
                depth += 1
        for kid in node.kids:
            if kid is None:
                continue
            if node.type == JOIN and node.partner is not None:
                kid.x = node.partner.x + node.jx
                kid.y = node.partner.y + node.jy + node.overhead()
            else:
                kid.x, kid.y = node.x + kid.dx, node.y + kid.dy
            self.propagate(kid, deep, depth)

    # -- what the story tree shows -----------------------------------------------------------------------------------------
    def real_child(self, node):
        """`find_real_child`: past joins that close only one branch and automatic branches with one branch."""
        while node is not None:
            if node.type == JOIN:
                if node.count > 1:
                    return node
                node = node.kids[0]
            elif node.type not in AUTO_BRANCHES:
                return node
            else:
                present = [kid for kid in node.kids if kid is not None]
                if len(present) != 1:
                    return node if present else None
                node = present[0]
        return None

    # -- drawing -----------------------------------------------------------------------------------------------------------
    YELLOW, BLACK, GRAY, LABEL, WHITE = (255, 255, 0), (0, 0, 0), (128, 128, 128), (28, 28, 28), (255, 255, 255)

    def line_style(self, node, child, index):
        """`DTNode::render_childline_color`: yellow along the path taken to the current scene (and for the result just
        answered), black along the rest of the story followed, gray where nothing is followed."""
        sz = self.sz
        current = node.src is self.current_src
        if child is None or not child.active:
            if node.active and node.path and node.result_index == index and self.last_was_result:
                return self.YELLOW, max(0.0, 4 * sz / 30)
            return self.GRAY, max(0.0, sz / 30)
        if not child.path:
            if current and node.result_index == index and self.last_was_result:
                return self.YELLOW, max(0.0, 4 * sz / 30)
            return self.BLACK, max(0.0, sz / 30)
        return self.YELLOW, max(0.0, 4 * sz / 30)

    def childline(self, node, index, x1, y1, x2, y2, ops):
        """`DTNode::render_childline`: an exit stub, then on to the child."""
        sz = self.sz
        child = node.kids[index]
        real = self.real_child(child)
        color, width = self.line_style(node, child, index)
        if node.type == JOIN and node.partner is not None:
            points = [(node.partner.x + node.jx, node.partner.y + node.jy + sz)]
        else:
            points = [(x1, y1), (x2, y2)]
        if child is not real:
            if child.y >= points[-1][1]:
                points.append((child.x, child.y))
        target = real
        if target is not None and not (target.type == JOIN and target.count < 1):
            if target.type == JOIN:
                points.append((target.x, target.y))
            else:
                if node.type in BRANCHES:
                    points.append((target.x, target.y))
                points.append((target.x, target.y + sz))
        ops.append(('path', points, color, width))

    def stubs(self, node, ops):
        """`render_lines`: the short lines that leave a node for each exit."""
        sz, x, y, kind = self.sz, node.x, node.y, node.spec.stubs
        if kind in ('one', 'two', 'three'):
            top = y + sz + node.spec.stub_drop * sz
            if kind == 'one':
                self.childline(node, 0, x, top, x, top + sz, ops)
            else:
                self.childline(node, 0, x, top, x - 0.7 * sz, top + 0.7 * sz, ops)
                if kind == 'three':
                    self.childline(node, 1, x, top, x, top + sz, ops)
                    self.childline(node, 2, x, top, x + 0.7 * sz, top + 0.7 * sz, ops)
                else:
                    self.childline(node, 1, x, top, x + 0.7 * sz, top + 0.7 * sz, ops)
        elif kind == 'football':
            top = y + 0.5 * sz + 19 * sz / FONT_UNIT
            self.childline(node, 0, x, top, x - 0.7 * sz, top + 0.7 * sz, ops)
            self.childline(node, 1, x, top, x + 0.7 * sz, top + 0.7 * sz, ops)
        elif kind in ('quiz', 'final'):
            offsets = FIXED_OFFSETS[node.spec.exits]
            for index, offset in enumerate(offsets):
                self.childline(node, index, x + offset * sz, y + sz, x + offset * sz, y + sz + 0.5 * sz + 0.8 * sz, ops)
        elif kind == 'auto':
            if node.present() > 1:
                for index, kid in enumerate(node.kids):
                    if kid is not None:
                        self.childline(node, index, x, y + sz, x, y + sz, ops)
        elif node.type == JOIN and node.count > 1:
            if node.primary:
                self.childline(node, 0, x, y + 2 * sz, x, y + 2 * sz, ops)
            color, width = self.line_style(node, node, 0)
            merge = (node.partner.x + node.jx, node.partner.y + node.jy)
            ops.append(('path', [(x, y), (x, merge[1]), (merge[0], merge[1] + sz)], color, width))

    def shape(self, node, ops, color, width):
        sz, x, y, u = self.sz, node.x, node.y, self.sz / FONT_UNIT
        kind = node.spec.shape
        if kind == 'rect':
            ops.append(('rect', x - 0.5 * sz - 0.5 * sz * node.exw, y + 0.5 * sz, sz * (1 + node.exw), sz, color, width))
        elif kind == 'circle':
            ops.append(('ellipse', x - 0.5 * sz - 0.5 * sz * node.exw, y + 0.5 * sz, sz, sz, color, width, False))
        elif kind == 'diamond':
            r = 0.5 * math.sqrt(2) * sz
            cy = y + 0.3 * sz + r
            ops.append(('polygon', [(x, y + 0.3 * sz), (x + r, cy), (x, cy + r), (x - r, cy)], color, width))
        elif kind == 'heart':
            ops.append(('bezier', (x, y + sz), (0, -9 * u), [((1 * u, -23 * u), (40 * u, -20 * u), (0, 20 * u)),
                                                             ((-40 * u, -20 * u), (-1 * u, -23 * u), (0, -9 * u))],
                        color, width))
        elif kind == 'football':
            ops.append(('bezier', (x, y + 0.98571 * sz), (34 * u, 0),
                        [((15.5 * u, -24 * u), (-15.5 * u, -24 * u), (-34 * u, 0)),
                         ((-15.5 * u, 24 * u), (15.5 * u, 24 * u), (34 * u, 0))], color, width))
        elif kind == 'triangle':
            cy = y + sz
            ops.append(('polygon', [(x, cy - 0.707 * sz), (x + sz, cy + 0.707 * sz), (x - sz, cy + 0.707 * sz)], color, width))
        elif kind == 'dot':
            if node.present() > 1:
                d = sz / 24
                ops.append(('ellipse', x - 0.5 * d, y + sz - 0.5 * d, d, d, self.BLACK, max(0.0, sz / 30), True))
        elif kind == 'join':
            if node.primary and node.count > 1:
                r = sz * 0.0625
                cx, cy = node.partner.x + node.jx, node.partner.y + node.jy + sz
                ops.append(('ellipse', cx - 0.5 * r, cy - 0.5 * r, r, r, color, width, False))

    def labels(self, node, ops):
        """`render_labels`: the node's label beside it and each exit's label by its stub."""
        sz, spec = self.sz, node.spec
        ox, oy = node.x, node.y + spec.label_origin * sz
        if sz >= 20 and node.lower.text and spec.shape not in ('join', 'dot'):
            left = ox + node.label_a() + node.label_b() * 0.5 + 2 * sz / FONT_UNIT
            centre = oy - 0.5 * sz - node.label_c()
            ops.append(('text', node.lower.lines, 'outer', left, centre, None, self.LABEL))
        if sz < 32 or not spec.child_labels:
            return
        if spec.shape == 'dot' and node.present() < 2:
            return
        exits = spec.exits
        for index, label in enumerate(node.exits):
            if not label.text:
                continue
            width, height = label.block_width(sz), label.text_height(sz)
            dx, dy = spec.child_labels[index]
            x, y = ox + dx * sz, oy + dy * sz
            if exits == 2 or (exits == 3 and index != 1):
                left = x - width if index == 0 else x
            elif exits == 3:
                y += 0.667 * height
                left = x - 0.5 * width
            else:
                left = x - 0.5 * width
            top = y - 0.5 * height
            ops.append(('fill', left, top, width, height, self.WHITE))
            ops.append(('text', label.lines, 'exit', left, top + height / 2, width, self.BLACK))

    def order(self):
        nodes = self.nodes()
        return [n for n in nodes if n.type == JOIN] + sorted((n for n in nodes if n.type != JOIN), key=lambda n: n.y)

    def draw_ops(self):
        """What to paint, node by node (each node draws its lines, then its icon, then its outline and labels), as tuples:
        ('path', points, rgb, width), ('rect'|'ellipse'|'polygon'|'bezier', ...), ('image', id, mono, cx, cy, scale),
        ('fill', x, y, w, h, rgb) and ('text', lines, kind, left, centre, width, rgb), all in tree coordinates."""
        ops = []
        sz = self.sz
        for node in self.order():
            self.stubs(node, ops)
            image = node.image_id()
            if image >= 0:
                cx, cy = node.x + node.spec.image_offset[0] * sz, node.y + node.spec.image_offset[1] * sz
                ops.append(('image', image, not node.active, cx, cy, sz / node.spec.image_scale))
            current = node.src is self.current_src and not self.last_was_result
            if current:
                color, width = self.YELLOW, max(0.0, 4 * sz / 30)
            else:
                color, width = ((self.BLACK if node.active else self.GRAY), max(0.0, sz / 30))
            self.shape(node, ops, color, width)
            self.labels(node, ops)
        return ops

    def find_touched(self, x, y, image_size):
        """`DTNode::find_touched_node`: the node whose icon (a box 1.2 times its size) holds the point; `image_size(id)` is
        the icon's size in the art's own pixels."""
        sz = self.sz
        for node in self.nodes():
            image = node.image_id()
            if image < 0:
                continue
            width, height = image_size(image)
            scale = node.spec.image_scale
            if abs(x - node.x) < width * 0.6 * sz / scale and abs(y - node.y - sz) < height * 0.6 * sz / scale:
                return node
        return None
