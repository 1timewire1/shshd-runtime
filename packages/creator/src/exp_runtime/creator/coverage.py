"""Which host services the creator can express, against the services real episodes call.

`CORPUS` holds statistics, not content: for each service, its calls and episodes in a 2026-10-23 static scan of an imported
SHS SD (97 episodes), SHS HD (187) and CoD (74) library. `STATUS` classifies every one of them:

- `emits`: the listed node kinds compile to this service (tests check that they really do);
- `equivalent`: the creator reaches the same effect through another service;
- `no_op`: a native default or offline stub with nothing to author;
- `pending`: not expressible yet; the text says what is missing.
"""
from typing import NamedTuple

GROUPS = ('shs-sd', 'shs-hd', 'cod')
EPISODES = dict(zip(GROUPS, (97, 187, 74)))

# service: ((calls SD, HD, CoD), (episodes SD, HD, CoD))
CORPUS = {
    0: ((8859, 5182, 6743), (91, 168, 59)), 1: ((2626, 3001, 3444), (93, 177, 68)),
    2: ((283, 247, 152), (54, 63, 25)), 3: ((6711, 3852, 5115), (54, 63, 25)),
    4: ((282, 246, 152), (54, 63, 25)), 5: ((1028, 2740, 1), (23, 33, 1)),
    7: ((114, 187, 162), (88, 171, 61)), 8: ((322, 323, 268), (96, 187, 73)),
    9: ((76, 159, 0), (74, 158, 0)), 10: ((754, 896, 1393), (89, 177, 67)),
    11: ((3814, 6037, 0), (94, 185, 0)), 13: ((91849, 122896, 80707), (97, 187, 74)),
    14: ((0, 14, 0), (0, 2, 0)), 15: ((291, 118, 996), (30, 34, 59)),
    16: ((2877, 4280, 1730), (96, 184, 73)), 18: ((390, 601, 365), (97, 187, 74)),
    21: ((4, 1, 0), (4, 1, 0)), 24: ((10, 44, 172), (5, 12, 20)),
    25: ((8, 4, 0), (4, 1, 0)), 27: ((301, 153, 135), (53, 38, 26)),
    28: ((19, 19, 40), (13, 18, 21)), 33: ((114, 199, 162), (88, 171, 61)),
    34: ((0, 1, 0), (0, 1, 0)), 35: ((1665, 1787, 7451), (82, 139, 74)),
    39: ((0, 20, 0), (0, 1, 0)), 40: ((19, 19, 40), (13, 18, 21)),
    44: ((5115, 6111, 6974), (97, 187, 74)), 45: ((6056, 7287, 6078), (97, 187, 74)),
    46: ((82, 104, 63), (23, 38, 20)), 47: ((508, 547, 30), (81, 153, 8)),
    49: ((97, 187, 74), (97, 187, 74)), 50: ((4, 1, 0), (4, 1, 0)),
    51: ((8, 2, 0), (4, 1, 0)), 52: ((1776, 3537, 148), (97, 187, 74)),
    53: ((31, 39, 0), (5, 2, 0)), 54: ((3, 11, 0), (2, 2, 0)),
    65: ((26773, 34102, 44076), (97, 187, 74)), 70: ((38, 35, 0), (10, 16, 0)),
    71: ((192, 224, 18), (80, 137, 15)), 72: ((193, 317, 107), (97, 187, 74)),
    73: ((71, 116, 33), (39, 71, 19)), 74: ((828, 1015, 1854), (92, 186, 74)),
    75: ((97, 187, 74), (97, 187, 74)), 76: ((0, 3, 0), (0, 1, 0)),
    78: ((24, 12, 2), (20, 9, 2)), 79: ((4515, 6193, 5040), (92, 176, 61)),
    80: ((4390, 5573, 3327), (96, 187, 73)), 81: ((641, 794, 1985), (71, 122, 73)),
    82: ((209, 326, 731), (25, 58, 47)), 86: ((0, 3, 0), (0, 1, 0)),
    88: ((1408, 1169, 1443), (67, 77, 58)), 89: ((256, 540, 1686), (29, 42, 57)),
    90: ((210, 206, 1), (2, 1, 1)), 91: ((49, 119, 0), (23, 61, 0)),
    94: ((7, 15, 0), (7, 5, 0)), 95: ((14, 30, 0), (7, 5, 0)),
    96: ((46, 108, 0), (18, 58, 0)), 99: ((622, 647, 731), (65, 125, 65)),
    100: ((15, 7, 4), (9, 5, 2)), 101: ((0, 2, 0), (0, 1, 0)),
    102: ((0, 126, 0), (0, 1, 0)), 103: ((0, 74, 0), (0, 1, 0)),
    106: ((0, 293, 0), (0, 1, 0)), 107: ((0, 9, 0), (0, 1, 0)),
    108: ((0, 12, 0), (0, 1, 0)), 111: ((0, 30, 0), (0, 1, 0)),
    112: ((0, 30, 0), (0, 1, 0)), 113: ((0, 1, 0), (0, 1, 0)),
    114: ((0, 2, 0), (0, 1, 0)), 115: ((0, 226, 0), (0, 1, 0)),
    116: ((0, 11, 0), (0, 1, 0)), 119: ((0, 1, 0), (0, 1, 0)),
    120: ((0, 1, 0), (0, 1, 0)),
}


class Coverage(NamedTuple):
    status: str
    detail: tuple | str


def emits(*kinds):
    return Coverage('emits', kinds)


def equivalent(text):
    return Coverage('equivalent', text)


def no_op(text):
    return Coverage('no_op', text)


def pending(text):
    return Coverage('pending', text)


STATUS = {
    0: emits('dialogue'),
    1: equivalent('choice: incremental 2/3/4 builds the same native panel'),
    2: emits('choice'), 3: emits('choice'), 4: emits('choice'),
    5: emits('expression_default'),
    7: emits('end'), 8: emits('title'),
    9: emits('survey'),
    10: emits('scene'), 11: emits('background'), 13: emits('dialogue'),
    14: no_op('native default'),
    15: equivalent('dialogue with a speaker and no portrait (76, the same native case)'),
    16: emits('transition'), 18: no_op('native default'), 21: no_op('native default'),
    24: emits('text_branch'),
    25: emits('append_text'),
    27: emits('random'),
    28: equivalent('input: the answer is stored and substituted through 46/47'),
    33: emits('message'),
    34: equivalent('background (11)'),
    35: equivalent('background (11); its character half only feeds services 36/37, which no episode calls'),
    39: emits('close_dialogue'),
    40: equivalent('input (17, the same native panel)'),
    44: equivalent('score with owner 0 (52)'),
    45: equivalent('score with owner 0 (53)'),
    46: emits('input', 'set_text'), 47: emits('text_branch', 'text_default'),
    49: emits('character_name'),
    50: emits('flag'), 51: emits('branch'),
    52: emits('score'), 53: emits('score', 'branch'), 54: emits('relationship'),
    65: equivalent('dialogue (13 with the character)'),
    70: emits('branch'),
    71: emits('word_game'),
    72: emits('character_art', 'picker'), 73: emits('branch', 'picker'),
    74: emits('speakers'), 75: emits('speakers'),
    76: emits('dialogue'),
    78: emits('picker'),
    79: emits('sound'), 80: emits('music'), 81: emits('stop_audio'),
    82: emits('vibrate'),
    86: equivalent('background (11); its extra flag is unresolved'),
    88: emits('notice'), 89: emits('emphasis'), 90: emits('scene_label'),
    91: emits('loading'),
    94: emits('football'),
    95: emits('football'),
    96: emits('grid'),
    99: no_op('ad stub; the offline runtime completes it'),
    100: emits('open_url'),
    101: emits('tree'), 102: emits('tree_node'), 103: emits('tree_node'), 106: emits('tree_result'),
    107: emits('tree_result'), 108: emits('tree'), 111: emits('tree_node'), 112: emits('tree'),
    113: emits('faceplace'), 114: emits('faceplace'), 115: emits('faceplace_post'), 116: emits('faceplace_link'),
    119: emits('faceplace'), 120: emits('faceplace'),
}


def calls(service):
    return sum(CORPUS[service][0])


def summary():
    """Rows of (service, status, detail, calls, episodes) in service order."""
    return [(service, STATUS[service].status, STATUS[service].detail, calls(service), sum(CORPUS[service][1]))
            for service in sorted(CORPUS)]
