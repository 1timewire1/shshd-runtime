"""The story tree's game-state snapshots, deltas and automatic branches, ported from the app's `DTNode` code.

Every scene of the tree carries a `StateVarSnapshot`: 67 shorts read from the game's entity table at the moment the scene was
added (`DTNode::computeDeltaVector`), and only the *changes* from the previous scene are kept -- the node's delta vector, which
`tree_nodes.txt` writes as the `variable=value` gates of each line. Walking the followed story (`DTNode::sweepForward`) rebuilds each
scene's snapshot from its parent's plus its own deltas (`applyDeltaVector`), and an automatic branch decides which of its results the
story took from the snapshot of its own scene (`DTNode::autobranch`). Warping installs a scene's snapshot into the game
(`installStateData`). `SHSDTView clearGlobalAccumulator:` (script service 108) empties a counter and marks it as one whose changes are
kept as absolute values.

The first 0x26 snapshot slots are properties of entity 0 (the global counters and flags); the other 29 are property 0x197 (407, a
character's relationship value) of the characters listed in `CHARACTERS`. A delta is `(id, value)`: a negative id is an absolute value
for that variable, a positive one a difference from the previous scene (the first 0x1a slots are always absolute, the rest relative
unless the variable was marked by `clearGlobalAccumulator`).
"""
from .vm import signed16

GLOBAL_COUNT = 0x26
ABSOLUTE_COUNT = 0x1a
RELATIONSHIP_PROPERTY = 0x197

# The table at 0x259720 of the HD binary: the id of each of the 67 slots (a property of entity 0 for the first 0x26, a character for
# the rest). It has duplicates (character 50 is in two slots); the app's lookup finds the first, and so does `apply_deltas`.
STATE_IDS = (
    3010, 601, 3011, 3016, 3003, 3009, 3013, 3014, 3015, 3019, 3020, 3021, 3023, 3024, 3025, 3026, 3027, 3028, 3029, 3030, 3031,
    3032, 3033, 3035, 3037, 3040,
    3017, 3018, 3007, 3008, 3038, 3022, 3100, 3101, 3102, 3103, 3104, 3105,
    50, 11, 10, 1, 110, 13, 14, 44, 30, 115, 102, 41, 108, 7, 118, 96, 50, 63, 62, 24, 3, 2, 100, 107, 99, 6, 120, 22, 12)
SLOTS = len(STATE_IDS)
assert SLOTS == 0x43
CHARACTERS = STATE_IDS[GLOBAL_COUNT:]
CLEARED_WITH_CHARACTER = 600            # `clearGlobalAccumulator:`: an id below this is a character, else a property of entity 0


def zero_state():
    return [0] * SLOTS


def owner_and_key(slot):
    """(entity, property) of a snapshot slot."""
    return (0, STATE_IDS[slot]) if slot < GLOBAL_COUNT else (STATE_IDS[slot], RELATIONSHIP_PROPERTY)


def read_state(engine):
    """`getIntProperty` for each slot: the game's current values as shorts."""
    return [signed16(engine.numbers.get(engine.number_key(*owner_and_key(slot)), 0)) for slot in range(SLOTS)]


def compute_deltas(previous, live, accumulators):
    """`DTNode::computeDeltaVector(previous, out, snapshot)`: the new scene's snapshot (the previous one with every changed variable
    updated) and its delta vector. `accumulators` is emptied by the call."""
    snapshot, deltas = list(previous), []
    for slot in range(SLOTS):
        identifier, value = STATE_IDS[slot], live[slot]
        if value == previous[slot]:
            continue
        if slot < ABSOLUTE_COUNT or identifier in accumulators:
            deltas.append((-identifier, value))
        else:
            deltas.append((identifier, signed16(value - previous[slot])))
        snapshot[slot] = value
    accumulators.clear()
    return snapshot, deltas


def apply_deltas(previous, deltas):
    """`DTNode::applyDeltaVector`: the snapshot a scene has once its deltas are applied to its parent's."""
    snapshot = list(previous)
    for identifier, value in deltas:
        wanted = identifier if identifier >= 0 else -identifier
        slot = STATE_IDS.index(wanted) if wanted in STATE_IDS else -1
        # (an unknown id would index the last slot in the app, `uVar7 = 0xffffffff`; none is ever written)
        if slot < 0:
            continue
        snapshot[slot] = signed16(value + snapshot[slot]) if identifier >= 0 else signed16(value)
    return snapshot


def _zero(value):
    return 1 if value == 0 else 0


def autobranch(condition, snapshot):
    """`DTNode::autobranch`: the result an automatic branch of this condition code (`addBranchNode`'s, +0x1b4) has taken given
    the snapshot of its scene, or None for a code the app does not decide (the node keeps its result). The app addresses the
    snapshot from +0x1d0; slot `k` here is the app's `field37_0x1d4[k - 2]`."""
    s = snapshot
    if condition == 0x4b:
        return {0x2c: 0, 0xb: 1}.get(s[0], 2)
    if condition in (0x4c, 0x4d, 0x4e, 0x4f, 0x50):
        return 0 if s[0] == {0x4c: 0xb, 0x4d: 0x2c, 0x4e: 0x32, 0x4f: 0x76, 0x50: 1}[condition] else 1
    if condition == 0x51:
        return {0xb: 1, 0x2c: 0, 0x32: 2}.get(s[0], 3)
    if condition == 0x52:
        return 0 if s[3] == 0 else 1
    if condition == 0x53:
        return _zero(s[3])
    if condition == 0x54:
        if s[0x1d] != 0 and int(s[0x1c] * 400 / s[0x1d]) > 299:
            return 1
        return 0
    if condition in (0x55, 0x57):
        value = s[0x1f] if condition == 0x55 else s[0x21]
        return 0 if value > 3 else 1 if value > 1 else 2
    if condition == 0x56:
        value = s[0x1b]
        return 0 if value > 14 else 2 if value < 10 else 1
    if condition == 0x58:
        value = s[0x20]
        return 0 if value > 6 else 2 if value < 4 else 1
    if condition in (0x59, 0x5a, 0x5b, 0x5c):
        slot, limit = {0x59: (0x24, 6), 0x5a: (0x22, 0xf), 0x5b: (0x23, 0x10), 0x5c: (0x25, 1)}[condition]
        return 0 if s[slot] > limit else 1
    if condition == 0x5d:
        return 0 if s[2] == 0x1f7 else 2 if s[2] != 0x1f8 else 1
    if condition in (0x5e, 0x5f, 0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68):
        # 0x67 sets its result from slot 10 and then falls into 0x68's code, which overwrites it from slot 4.
        slot = {0x5e: 0x18, 0x5f: 0x19, 0x60: 9, 0x61: 0xe, 0x62: 0x10, 0x63: 0xf, 0x64: 0x12, 0x65: 0xa, 0x66: 0xb,
                0x67: 4, 0x68: 4}[condition]
        return _zero(s[slot])
    return None


def install_state(engine, snapshot):
    """`DTNode::installStateData`: put a scene's snapshot into the game, then derive each character's display properties from it
    (3001 = the relationship + 1, or ~relationship when negative; 3000 = 3010 for the character now dated, 3011 for a negative
    relationship, else 3012)."""
    for slot in range(SLOTS):
        owner, key = owner_and_key(slot)
        engine.numbers[engine.number_key(owner, key)] = snapshot[slot]
    dated = signed16(engine.numbers.get(engine.number_key(0, 601), 0))
    for slot in range(GLOBAL_COUNT, SLOTS):
        character, value = STATE_IDS[slot], snapshot[slot]
        kind = 3010 if character == dated else 3012
        if value >= 0:
            shown = value + 1
        else:
            shown, kind = ~value, 3011
        engine.numbers[engine.number_key(character, 3001)] = shown
        engine.numbers[engine.number_key(character, 3000)] = kind
