"""Native decision-tree (DTView) and message-wall (Faceplace) state.

Real per-argument semantics recovered by hand-disassembling the raw Thumb-2
call sites in the HD ipa's own `SHSScript::syscall` for native cases
0x66/0x67 (`addNode:innerLabel:upperLabel:lowerLabel:exw:`), 0x6a/0x6b
(`addResult:exitLabel:`) and 0x73-0x75 (Faceplace `incomingMessage:from:
expression:` / `incomingContinuationMessage{Text,Image}:url:`) -- see
docs/ENGINE_ABI.md section 6.2 for the full disassembly. Ghidra's decompiler
is confirmed unreliable for these specific calls (it visibly fetches real
strings off the VM stack and then discards them before the call, showing
only 2 of a selector's 5 real arguments); every field below is sourced from
raw register-level tracing instead, cross-checked against the yield's
already-empirically-verified argument count (`need()` in engine.py).

Confirmed against a real device's own live tree_<serial>.sav debug dump
(captured over USB via a real jailbroken iPad on iOS 8.4.1, see
legacy/findings.md): every resolved node in the real tree also carries a
label for *each* of its result slots, not just the one actually taken (e.g.
a 3-way node showing `Sports|Girls|TV` even when only one branch was ever
explored). This does NOT come from addNode's own innerLabel/upperLabel
arguments -- those really are hardcoded empty per the disassembly above --
it comes from the entirely separate choice-presentation syscalls (engine.py
y=1/2/3/4, `EngineAction('choice', ...)`/`choice_builder`), whose own
`options`/`values` lists are exactly the button text the player saw and the
slot index each button resolves to. `DTNode.choice_labels` below captures
that correlation (see `Session.advance()`), letting the side panel show
every known branch, explored or not -- matching "the intended story tree
feature where you can see all the choices map out."
"""
from dataclasses import dataclass, field

from .dt_state import apply_deltas, autobranch, compute_deltas, zero_state


JOIN_NODE = 0x4c8
AUTOBRANCH_NODES = (0x4c5, 0x4c6, 0x4c7)      # script-driven branches the player never sees
NOT_WARPABLE = (*AUTOBRANCH_NODES, JOIN_NODE)
CHOICE_NODES = (0x4b9, 0x4c3)     # `iVar4 - 0x4b9 < 10`
AWAITING_NODES = (0x4b9, 0x4c7)


@dataclass
class DTNode:
    node_type: int
    lower_label: str
    exw: int
    children: 'dict[int, DTNode]' = field(default_factory=dict)
    result_index: int | None = None
    exit_label: str = ''
    condition: int = 0          # addBranchNode's condition (yield 111)
    # The ids a node is created with (`DTNode` +0x1c8 / +0x1cc) and whether it is the first node to carry them; a join node
    # (type 0x4c8) that is not primary sends the next `addNode` to the node that does (see DTView.add_node).
    uid: int = 0
    script: int = 0
    primary: bool = True
    # The number of this node's `tree_<serial>.sav`: a primary node gets the next one, a join that duplicates the ids of
    # an earlier node shares that node's (`SHSDTView addNode`, DTNode +0x1bc).
    serial: int = 0
    # What changed in the game since the previous scene (`DTNode` +0x258, the gates of a `tree_nodes.txt` line): (id, value) pairs, a
    # negative id an absolute value (`dt_state`). None is a scene recorded before this was kept, whose state (and so any automatic
    # branch decided from it) is unknown.
    deltas: 'list[tuple[int, int]] | None' = field(default=None, compare=False)
    # The game state at this scene (`DTNode` +0x1d0), rebuilt from the deltas along the story by `DTView.sweep_forward`; not saved.
    snapshot: list = field(default_factory=zero_state, repr=False, compare=False)
    # What the panel colors by (`DTNode` +0x1b1 and +0x1b0), recomputed by `DTView.sweep_forward`, never saved: `active` is
    # on the chain of results followed from the start (in color, black lines); `path` is on the way from the start to the
    # current scene (yellow lines).
    active: bool = field(default=False, repr=False, compare=False)
    path: bool = field(default=False, repr=False, compare=False)
    # Label for each result slot as shown on the choice buttons the player
    # actually saw (keyed by the same slot index `children` and
    # `result_index` use), populated from the choice-presentation syscalls
    # while this node is `DTView.current` -- see module docstring and
    # `Session.advance()`. A slot present here with no matching entry in
    # `children` is a choice the player has seen offered but never taken on
    # any playthrough; the side panel renders it as an unfilled placeholder
    # rather than omitting it, matching real device behavior.
    choice_labels: 'dict[int, str]' = field(default_factory=dict)
    # The exit label of every result the player has taken from this node, by slot (`addResult:exitLabel:`), which the
    # tree draws beside each taken branch ("Sports", "Girls", "TV"); a result never taken has none.
    result_labels: 'dict[int, str]' = field(default_factory=dict)
    # innerLabel/upperLabel are real CSString parameters in the ObjC method,
    # but both real native call sites (0x66 and 0x67) construct them from a
    # hardcoded empty-string literal, never from a script argument -- not an
    # omission, confirmed in the raw disassembly.
    #
    # Deliberately no parent back-reference: DTView.current already tracks
    # tree position without one, and a parent<->children cycle would break
    # dataclasses.asdict() (runtime.py's save format) with infinite
    # recursion -- found live running this against a real save/checkpoint,
    # not caught by any test or audit tool since neither ever calls
    # Session.save(). DTView.to_dict()/from_dict() below (the cross-session
    # tree file, a separate concern from the per-episode save) walk the
    # tree explicitly for the same reason.

    def to_dict(self) -> dict:
        return dict(node_type=self.node_type, lower_label=self.lower_label, exw=self.exw,
                    result_index=self.result_index, exit_label=self.exit_label, condition=self.condition, uid=self.uid, script=self.script, primary=self.primary, serial=self.serial,
                    choice_labels={str(key): value for key, value in self.choice_labels.items()},
                    result_labels={str(key): value for key, value in self.result_labels.items()},
                    **(dict(deltas=[list(delta) for delta in self.deltas]) if self.deltas is not None else {}),
                    children={str(key): child.to_dict() for key, child in self.children.items()})

    @staticmethod
    def from_dict(data: dict) -> 'DTNode':
        node = DTNode(data['node_type'], data['lower_label'], data['exw'],
                     result_index=data.get('result_index'), exit_label=data.get('exit_label', ''),
                     condition=data.get('condition', 0), uid=data.get('uid', 0), script=data.get('script', 0),
                     primary=data.get('primary', True), serial=data.get('serial', 0))
        if data.get('deltas') is not None:
            node.deltas = [(int(identifier), int(value)) for identifier, value in data['deltas']]
        node.choice_labels = {int(key): value for key, value in data.get('choice_labels', {}).items()}
        node.result_labels = {int(key): value for key, value in data.get('result_labels', {}).items()}
        if 'result_labels' not in data and node.exit_label and node.result_index is not None:
            node.result_labels[node.result_index] = node.exit_label       # a tree from before every taken result was kept
        node.children = {int(key): DTNode.from_dict(child) for key, child in data.get('children', {}).items()}
        return node


@dataclass
class DTView:
    """Mirrors SHSDTView's `_cur_node`/`_awaiting_result`/`_new_result_index`
    globals. `add_node` reuses an existing child at the current result slot
    instead of always creating a fresh one -- confirmed from the real
    decompile (`if (_cur_node == NULL) { if (DTNode::root != NULL) goto
    reuse_root; }`, and the equivalent check against `_cur_node->field13_
    0x34[_new_result_index]` for non-root nodes) and independently
    confirmed against a real device's own tree_<serial>.sav debug dump
    (`Meet Adam|||...` etc.): a node revisited on a later playthrough
    reuses its prior entry rather than duplicating it, which is what makes
    a real replay show every previously-explored branch, not just the
    current one. The recursive `sweepForward` (which scenes are on the story followed and on the path to the current one) is `sweep_forward`; the
    rest of the view's drawing and layout is `dt_layout.py`.

    to_dict()/from_dict() serialize this to a small JSON file kept
    *outside* the normal per-episode save (see Session.dt_view_path) --
    the real app's own tree_<serial>.sav files are similarly saved outside
    the episode's own save, once per addNode/addResult call, and persist
    across separate playthroughs of the same content. Only the tree shape
    persists, not `current`: confirmed against a real device, a fresh
    playthrough starts back at the root with the full history of earlier
    playthroughs still visible around it, not resuming wherever an earlier
    one left off -- `Session.__init__` loading a persisted tree therefore
    leaves `current` at its dataclass default (None), and the first
    `add_node` call naturally reuses the persisted root from there.
    """
    root: DTNode | None = None
    current: DTNode | None = None
    pending_result_index: int = 0
    awaiting_result: bool = False
    # `SHSDTView.script_enable`: set by the script's own scriptEnable call (service 101). Until then a
    # downloaded episode's panel is the "not supported in this episode" state.
    enabled: bool = False
    # `_last_call_was_addResult`: the current scene has been answered (its result stub is drawn yellow) rather than just arrived at
    # (its outline is drawn yellow).
    last_was_result: bool = False
    # Counts the changes the panel has to lay the tree out again for: a drawing cache key, not story state, so
    # it takes no part in comparisons.
    version: int = field(default=0, compare=False)
    # `DTNode::accumulators_set`: variables `clearGlobalAccumulator:` emptied since the last scene was added, whose changes that scene
    # keeps as absolute values. Part of a game save (`SHSDTView saveGame:`), not of the tree.
    accumulators: list[int] = field(default_factory=list)

    def clear_flags(self, node: 'DTNode') -> None:
        """`DTNode::clearFlags`: nothing active; the way to the current scene (and the scene itself) on the path."""
        node.active = node.path = False
        for child in node.children.values():
            self.clear_flags(child)
            if child.path:
                node.path = True
        if node is self.current:
            node.path = True

    def sweep_forward(self, start: 'DTNode | None') -> None:
        """`DTNode::sweepForward`: from `start`, follow each scene's last result, marking the chain active and the part of it
        up to the current scene as the path; a join that repeats another's ids carries on from that node's next scene."""
        self.version += 1
        if start is None:
            return
        self.clear_flags(start)
        reached = self.current is None
        node, seen = start, set()
        snapshot, known = start.snapshot, start.deltas is not None
        while node is not None and id(node) not in seen:        # (a tree that loops back on itself is only walked once)
            seen.add(id(node))
            node.active, node.path = True, not reached
            if node is self.current:
                reached = True
            if known:
                decided = autobranch(node.condition, node.snapshot)      # `DTNode::autobranch`, from this scene's own state
                if decided is not None:
                    node.result_index = decided
            follows = self.find(node.uid, node.script) if node.node_type == JOIN_NODE and not node.primary else node
            child = self.path_child(follows)
            if child is not None:
                # `applyDeltaVector(snapshot so far, the child's deltas, the child's snapshot)`.
                known = known and child.deltas is not None
                if known:
                    child.snapshot = apply_deltas(node.snapshot if follows is node else snapshot, child.deltas)
                    snapshot = child.snapshot
            node = child

    def refresh_flags(self) -> None:
        self.sweep_forward(self.root)

    def find(self, uid: int, script: int, start: 'DTNode | None' = None) -> 'DTNode | None':
        """The node that owns these ids -- the primary one, which is the first node created with them: `DTNode::find_prototype`
        (a repeat of the ids elsewhere in the tree is not it, wherever it falls in the walk)."""
        node = start if start is not None else self.root
        if node is None:
            return None
        if node.primary and (node.uid, node.script) == (uid, script):
            return node
        for index in sorted(node.children):
            found = self.find(uid, script, node.children[index])
            if found is not None:
                return found
        return None

    def add_node(self, node_type: int, lower_label: str, exw: int, uid: int = 0, script: int = 0, state=None) -> DTNode:
        """`state` is the game's current `dt_state.read_state`; with it the scene records what changed since the previous one."""
        previous = self.current
        if self.current is not None and self.current.node_type == JOIN_NODE and not self.current.primary:
            # A join that duplicates an earlier node's ids continues from that node.
            target = self.find(self.current.uid, self.current.script)
            if target is not None:
                self.current = target
        if self.current is None and self.root is not None:
            node = self.root  # Reuse a persisted root instead of starting over.
        else:
            node = self.current.children.get(self.pending_result_index) if self.current else None
            if (node is None and self.current is not None and self.current.children
                    and CHOICE_NODES[0] <= self.current.node_type < CHOICE_NODES[1]):
                # A choice node whose results came back in another order keeps its branch under the new slot.
                first = min(self.current.children)
                node = self.current.children[self.pending_result_index] = self.current.children.pop(first)
                self.current.result_index = self.pending_result_index
        if node is None:
            first = self.find(uid, script)
            primary = first is None
            node = DTNode(node_type, lower_label, exw, uid=uid, script=script, primary=primary,
                          serial=self.max_serial() + 1 if primary else first.serial)
            if self.current is None:
                self.root = node
            else:
                self.current.children[self.pending_result_index] = node
        else:
            # Reused nodes still get their content refreshed every visit --
            # confirmed native does the same (the label-setting code runs
            # unconditionally after the reuse-vs-create branch merges).
            node.node_type, node.lower_label, node.exw = node_type, lower_label, exw
        self.current = node
        self.last_was_result = False
        if state is not None:
            if previous is None:
                if node.deltas is None:
                    node.deltas = []                            # the first scene: nothing before it
            else:
                node.snapshot, node.deltas = compute_deltas(previous.snapshot, state, self.accumulators)
        # Only the types 0x4b9-0x4c7 (decisions, games, quizzes) wait for an addResult.
        self.awaiting_result = AWAITING_NODES[0] <= node_type <= AWAITING_NODES[1]
        # `addNode` ends with `_new_result_index = 0`: a node with no results of its own continues in slot 0, not in
        # the slot the previous decision took.
        self.pending_result_index = 0
        self.sweep_forward(node)
        return node

    def nodes(self):
        """Every node, depth first in slot order."""
        stack = [self.root] if self.root else []
        while stack:
            node = stack.pop()
            yield node
            stack.extend(node.children[key] for key in sorted(node.children, reverse=True))

    def max_serial(self) -> int:
        return max((node.serial for node in self.nodes()), default=0)

    def ensure_serials(self) -> None:
        """Number the nodes of a tree saved before serials existed (a shared join takes its first node's number)."""
        if all(node.serial for node in self.nodes()):
            return
        next_serial = self.max_serial()
        by_ids = {}
        for node in self.nodes():
            if node.serial:
                by_ids.setdefault((node.uid, node.script), node.serial)
        for node in self.nodes():
            if node.serial:
                continue
            key = (node.uid, node.script)
            if key not in by_ids or node.primary:
                next_serial += 1
                by_ids[key] = next_serial
            node.serial = by_ids[key]

    def by_serial(self, serial: int) -> 'DTNode | None':
        """`DTNode::find_serial_number`: the first node carrying this number."""
        return next((node for node in self.nodes() if node.serial == serial), None)

    @staticmethod
    def path_child(node: 'DTNode | None') -> 'DTNode | None':
        """The node's child along the result it last took (`children[result index]`)."""
        return None if node is None else node.children.get(node.result_index or 0)      # +0x1ac starts at slot 0

    def _pass_through(self, node: 'DTNode') -> 'DTNode | None':
        """Past a node the tree view treats as invisible: an automatic branch, or a join (which continues from
        the earlier node whose ids it shares when it is not the first)."""
        if node.node_type == JOIN_NODE and not node.primary:
            node = self.find(node.uid, node.script) or node
        return self.path_child(node)

    def real_child(self, node: 'DTNode | None') -> 'DTNode | None':
        """`SHSDTHelpOverView find_real_child:` (Fast Forward): the next node the player would see."""
        child, seen = self.path_child(node), set()
        while child is not None and child.node_type in NOT_WARPABLE:
            if id(child) in seen:
                return None         # the path only loops through invisible nodes from here: nothing further to show
            seen.add(id(child))
            child = self._pass_through(child)
        return child

    def real_parent(self, target: 'DTNode | None') -> 'DTNode | None':
        """`SHSDTTitleOverView find_real_parent:` (Rewind): the visible node before `target` on the path from the
        root; None for the root itself."""
        if self.root is None or target is None or target is self.root:
            return None
        # A replayed hub (Football Star's practice loop: a repeated join continues from its first node) makes the path
        # loop back on itself, as sweep_forward allows for; a target off that loop is then never reached, so each node
        # is walked once.
        previous, node, seen = None, self.root, set()
        while node is not None and node is not target and id(node) not in seen:
            seen.add(id(node))
            previous = node
            node = self.real_child(node)
        return previous if node is target else None

    def add_result(self, index: int, exit_label: str) -> None:
        if self.current is not None:
            self.current.result_index = index
            self.current.exit_label = exit_label
            self.current.result_labels[index] = exit_label
        self.pending_result_index = index
        self.awaiting_result = False
        self.last_was_result = True
        self.sweep_forward(self.root)

    def to_dict(self) -> dict:
        # Deliberately only the tree shape: `current`/`pending_result_index`
        # /`awaiting_result` are this *session's* position within it, not
        # part of what persists. A new playthrough starts back at the
        # beginning with the full history of past playthroughs still
        # visible around it, not resuming wherever an earlier one left off
        # -- confirmed against a real device (see legacy/findings.md).
        return dict(root=self.root.to_dict() if self.root else None)

    @staticmethod
    def from_dict(data: dict) -> 'DTView':
        view = DTView()
        root_data = data.get('root')
        if root_data:
            view.root = DTNode.from_dict(root_data)
            view.ensure_serials()
            view.refresh_flags()
        return view


@dataclass
class FaceplaceMessage:
    kind: str  # 'message' | 'continuation_text' | 'continuation_image'
    text: str = ''
    from_id: int = -1
    expression: int = -1
    url: str = ''
    image_id: int = -1
    # Continuation calls ("Tap here to ...") that follow a message belong to it: HD shows them as further
    # paragraphs of the same post and the same alert, not as new posts.
    continuations: list['FaceplaceMessage'] = field(default_factory=list)


@dataclass
class FaceplaceWall:
    messages: list[FaceplaceMessage] = field(default_factory=list)
    enabled: bool = False       # `SHSFSView.script_enable`, set by service 114

    def incoming_message(self, text: str, from_id: int, expression: int) -> None:
        self.messages.append(FaceplaceMessage('message', text=text, from_id=from_id, expression=expression))

    def _continue(self, message: FaceplaceMessage) -> FaceplaceMessage:
        """Attach a continuation to the newest post (or start one if the wall is empty); returns the post."""
        if not self.messages:
            self.messages.append(message)
            return message
        self.messages[-1].continuations.append(message)
        return self.messages[-1]

    def incoming_continuation_text(self, text: str, url: str) -> FaceplaceMessage:
        return self._continue(FaceplaceMessage('continuation_text', text=text, url=url))

    def incoming_continuation_image(self, image_id: int, text: str, url: str) -> FaceplaceMessage:
        # Case 0x75 fires both incomingContinuationMessageImage:url: and
        # incomingContinuationMessageText:url: with the same url, back to
        # back -- confirmed in the raw disassembly, not a guess; recorded as
        # one logical wall entry carrying both the image and its caption.
        return self._continue(FaceplaceMessage('continuation_image', image_id=image_id, text=text, url=url))

    def clear(self) -> None:
        self.messages.clear()


# Not a decompiled constant: an exhaustive symbol-table search of SHSFSView
# and SHSViewController (every method, not a sample) found nothing matching
# a corner alert/toast/badge -- SHSEngine::handleBadges/decrementBadgeNumber
# turned out to be the iOS home-screen app-icon badge, unrelated. Only the
# pop-in itself is timed; real-device testing found the earlier assumption
# of a timed fade-out was wrong -- see FaceplaceToast's own docstring.
FACEPLACE_TOAST_ENTER_MS = 200


@dataclass
class FaceplaceToast:
    """A transient corner alert for a newly-arrived Faceplace post --
    distinct from the persistent message wall (still unrendered), which
    will retain this content indefinitely once built. Every new wall entry
    replaces any toast already showing, matching "pops up... as soon as
    they are called" -- confirmed against a real reference screenshot.

    Real device testing (not a timer) confirmed it does *not* fade out on
    its own: it pops in alongside the next dialogue beat and then just sits
    there until the player explicitly dismisses it by advancing dialogue,
    opening the settings/pause menu, or opening the side panels (that data
    is visible there already) -- see Session.answer()'s dialogue branch and
    Desktop.command()/the panels-open toggle. An earlier version of this
    class carried its own multi-second auto-fade timer; that assumption
    is what real testing overturned, not the pop-in animation itself.
    """
    message: FaceplaceMessage
    elapsed_ms: int = 0

    def tick(self, elapsed_ms: int) -> None:
        self.elapsed_ms += elapsed_ms

    @property
    def enter_progress(self) -> float:
        return min(1.0, self.elapsed_ms / FACEPLACE_TOAST_ENTER_MS)

    @property
    def alpha(self) -> int:
        return round(255 * self.enter_progress)
