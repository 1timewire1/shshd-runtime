"""The iOS app's `tree_nodes.txt` (the Decision Tree as the app writes it) read, written and made from a tree of ours.

One line per node object, children before their parent (`DTNode::writeFile`), fields split by `|`:

    N<line> <type> <child line or x per result slot>|||<label>|<exit label per result slot>|<numbers>

`<numbers>` is `exw 1 serial uid script+1 result-index condition N` followed by N `variable=value` gates. `line` is the
node object's own number; `serial` is the number of its saved game (`tree_<serial>.sav`), which several objects that are the
same scene reached by different paths share. `uid` and `script` are the ids the node is created with (`script` is our
`DTNode.script` plus one), which is how a scene of a tree we generated is matched to the same scene of a saved game.

`DTNode::readFile` (decompiled) reads the lines in order, makes a node of each, and attaches every child token to the
earlier, still parentless node with that line number. It fails -- and the app then deletes the game's main save and this
file -- when a line is not `N...` or is over 490 characters, or when anything but exactly one parentless node (the root)
remains at the end. A child that cannot be found is only reported. The number of result slots of a line (child tokens and
exit-label fields) is fixed by the node type.

Comparing the completed Football Star save's 209 scenes with a tree our playthroughs built, every scene matches by
those ids with the same type and label.
"""
from dataclasses import dataclass, field

SLOTS = {0x4b2: 0, 0x4b3: 1, 0x4b4: 1, 0x4b5: 1, 0x4b6: 1, 0x4b7: 1, 0x4b8: 1, 0x4ba: 2, 0x4bb: 3, 0x4bc: 2, 0x4be: 2,
         0x4bf: 2, 0x4c0: 3, 0x4c1: 4, 0x4c2: 5, 0x4c3: 2, 0x4c4: 3, 0x4c5: 2, 0x4c6: 3, 0x4c7: 4, 0x4c8: 1}
MAX_LINE = 490          # `readFile` gives up on a longer line


@dataclass
class NativeNode:
    line: int
    node_type: int
    kids: list = field(default_factory=list)         # line number or None per result slot
    label: str = ''
    results: list = field(default_factory=list)      # exit label per result slot
    exw: int = 0
    flag: int = 1
    serial: int = 0
    uid: int = 0
    script: int = 0                                   # the file's own value (ours plus one)
    result_index: int = 0
    condition: int = 0
    gates: list = field(default_factory=list)         # 'variable=value' strings

    @property
    def ids(self):
        return self.uid, self.script

    def text(self):
        head = ' '.join(['N%d' % self.line, str(self.node_type), *('x' if kid is None else str(kid) for kid in self.kids)])
        numbers = ' '.join(map(str, [self.exw, self.flag, self.serial, self.uid, self.script, self.result_index,
                                     self.condition, len(self.gates), *self.gates]))
        return '|'.join([head, '', '', self.label, *self.results, numbers])


def parse(text):
    """`{line: NativeNode}` from the text of a tree_nodes.txt."""
    nodes = {}
    for row in text.splitlines():
        if not row.strip():
            continue
        fields = row.split('|')
        head = fields[0].split(' ')
        numbers = fields[-1].split(' ')
        kids = [None if kid == 'x' else int(kid) for kid in head[2:]]
        if len(fields) != 5 + len(kids):
            raise ValueError(f'Not a tree_nodes.txt line: {row[:60]}')
        nodes[int(head[0][1:])] = NativeNode(int(head[0][1:]), int(head[1]), kids, fields[3], fields[4:-1], int(numbers[0]),
                                             int(numbers[1]), int(numbers[2]), int(numbers[3]), int(numbers[4]),
                                             int(numbers[5]), int(numbers[6]), numbers[8:8 + int(numbers[7])])
    return nodes


def format_nodes(nodes):
    """The text, highest line first so that every child comes before its parent."""
    return ''.join(node.text() + '\n' for _, node in sorted(nodes.items(), reverse=True))


def check(nodes):
    """What `readFile` needs of `nodes`: the problems it would fail on (an empty list when it would load them)."""
    problems, parentless = [], set(nodes)
    for line, node in sorted(nodes.items(), reverse=True):
        if len(node.text()) > MAX_LINE:
            problems.append(f'N{line} is longer than {MAX_LINE} characters')
        if len(node.kids) != SLOTS.get(node.node_type, len(node.kids)) or len(node.results) != len(node.kids):
            problems.append(f'N{line} has the wrong number of result slots for type {node.node_type}')
        for kid in node.kids:
            if kid is None:
                continue
            if kid not in parentless or kid <= line:
                problems.append(f'N{line} names child N{kid}, which is not an earlier parentless line')
            else:
                parentless.discard(kid)
    if len(parentless) != 1:
        problems.append(f'{len(parentless)} parentless lines at the end (exactly one is needed)')
    return problems


def export(real, tree):
    """The whole of `tree` (a `DTView`) as tree_nodes.txt lines. A scene that is also in `real` (the lines of a saved
    game's file) takes that scene's serial and state gates, so the saved game keeps working for it; each other scene is
    numbered on from the highest real serial, has no saved game and carries the deltas our own playthroughs recorded (its gates). Branches beyond a type's result slots are left out
    with what lies under them. Returns (nodes, report)."""
    serials, gates = {}, {}
    for node in real.values():
        serials.setdefault(node.ids, node.serial)
        gates.setdefault(node.ids, (node.exw, node.gates))
    next_serial = max((node.serial for node in real.values()), default=0)
    report = dict(nodes=0, matched=0, new_scenes=0, left_out=0, labels=0)
    out, count = {}, 0
    stack = [(tree.root, None, 0)]
    while stack:                                     # depth first, a node before its children, so its line is lower
        node, parent, slot = stack.pop()
        count += 1
        ids = (node.uid, node.script + 1)
        if ids not in serials:
            next_serial += 1
            serials[ids] = next_serial
            report['new_scenes'] += 1
        elif ids in gates and node.primary:
            report['matched'] += 1
        slots = SLOTS[node.node_type]
        exw, conditions = gates.get(ids, (node.exw, ['%d=%d' % delta for delta in node.deltas or ()]))
        mine = out[count] = NativeNode(count, node.node_type, [None] * slots, node.lower_label, [''] * slots, exw, 1,
                                       serials[ids], node.uid, node.script + 1,
                                       min(node.result_index or 0, max(slots - 1, 0)), node.condition, list(conditions))
        if parent is not None:
            out[parent].kids[slot] = count
        for index, label in node.result_labels.items():
            if index < slots:
                mine.results[index] = label
                report['labels'] += bool(label)
        for index in sorted(node.children, reverse=True):
            if index < slots:
                stack.append((node.children[index], count, index))
            else:
                report['left_out'] += 1
    report['nodes'] = len(out)
    return out, report
