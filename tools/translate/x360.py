"""The cancelled Xbox 360 SHS prototype's stories as creator projects (reference/Other Games/docs/SHS_X360.md).

The prototype (MS4, 2009-05-26) is a 3D game on Wanako's "Tongas" engine. Its story logic is Lua 5.1 source: event
scripts embedded in templates/eventconfig.wxr and the conversations in scripts/dialogs/. This module reads its
data.pak directly, walks that Lua (lua_subset.py) and writes the story as an exp_runtime.creator Project, the route
TRANSLATOR_PLAN.md gives sources without bytecode. Two stories are new to this prototype:

* "Day of Diss" (kingofdiss/*): the King of Diss prequel. A hub picks Kim, Hector, Ryan or Nicole to talk to; five
  talks, then Hector's diss battle intro and the demo's end card;
* the puzzle test (prototype/puzzle/event1-2): two short scenes, Moondog and then Beth.

What carries over: every line, speaker, choice (with its enable condition), numeric state (gameStats.*, the
*Dialogs flags), condition, scene jump and the hub's min/max gating, as the scripts have them, including the
prototype's unfinished hub (five talks among four people, so someone is talked to twice). An answer's preview
emotion (AddChoices' third argument) becomes the speaker's expression on that answer's branch. Objectives the
selection post-it checks off become notices. What is dropped: cameras, 3D animation, waits, sound effects, emoticon
effects, the presentation card and the skip button. Music is the X360's placeholder tracks (licensed songs), so the
translation plays none unless a cue is mapped (`music`).

Art: the King of Diss cast wears its New Rules looks (nr_art), as the New Rules translation of King of Diss does;
the puzzle test's Beth is the SHS shared-bank Beth. Backgrounds are New Rules' location strips.
"""
from dataclasses import dataclass, field
import lzma
import re
import struct

from exp_runtime.creator.model import Asset, Character, Choice, Node, Project
from exp_runtime.emoticon_effects import HEART, LIGHTNING, SWEAT, X360_EFFECTS

import lua_subset
import nr_art

PAK_MAGIC = b'tongas_pack_v20000'
PACK_ID = 31400                         # shs/profile.py: TRANSLATED_PORTRAIT_ART
BACKGROUND_BASE = 26000                 # five IDs apart, as the creator allocates
PORTRAIT_BASE = 26200                   # five consecutive IDs per look
HIRES_PORTRAIT_OFFSET = 1000            # the X1i (HD-sized) set, as the New Rules translation stores it
FRAME_BACKDROP = 26999                  # New Rules' UI backdrop under the strips (shs/profile.py TRANSLATED_FRAME_BACKDROP)
# Line emoticons (shs/profile.py TRANSLATED_PORTRAIT_EFFECTS, emoticon_effects): the global number set around a line,
# the six cells of the X360's 4x4 emoticon sheet (effect n = cell n - 1), and the sounds its effects play.
EFFECT_KEY, EFFECT_IMAGE_BASE = 31410, 26990
EFFECT_SHEET, EFFECT_CELLS, EFFECT_GRID = 'data/art/hud/emoticons.png', 6, 4
EFFECT_SOUNDS = {HEART: ('data/sound/fx/chimes2.wav', 26985), LIGHTNING: ('data/sound/fx/angry_spark.wav', 26986),
                 SWEAT: ('data/sound/fx/sweat1.wav', 26987)}
# `camera.CreateFx("sound/success")`, played as an objective is checked off (fx.wxr: SNFX:fx/success)
OBJECTIVE_SOUND = ('data/sound/fx/success.wav', 26988)
SING_TYPE, SING_MARK = 6, '{'           # OpenDialog type 6 is the X360's sing bubble; '{' is SHS's music note
# The prototype's own music, when the translation is given its files (music_assets): an intro and the loop it runs
# into (shs/profile.py TRANSLATED_MUSIC_LOOPS: Day of Diss's `dont_trust_me`), then any other cue.
MUSIC_INTRO, MUSIC_LOOP, MUSIC_OTHER = 26900, 26901, 26902
EXPRESSIONS = (1, 4, 2, 3, 5)           # New Rules faces in SHS slots 0-4: neutral, angry, happy, sad, surprised
# X360 emotion names (game._SetCharacterEmotion) -> SHS expression slot.
EMOTION = {'neutral': 0, 'happy': 2, 'sad': 3, 'angry': 1, 'brag': 2, 'exited': 4, 'excited': 4, 'question': 4,
           'rap': 0, 'rap_angry': 1, 'cruel': 1, 'concerned': 3, 'boxsearch': 0, 'walk': 0, 'shy': 3,
           'surprised': 4}
CHOICE_TITLE = 'Make your choice!'      # as the New Rules translation titles its choices
HUB_TITLE = 'Who do you want to talk to?'
# The selection hub (guigroup hud/selection/main): gameStats.cam 1-4 within [minSel, maxSel], A runs the dialog.
HUB = (('Kim', 'kim'), ('Hector', 'hector'), ('Ryan', 'ryan'), ('Nicole', 'nicole'))
# The objectives post-it (guilabel menus/objectives/objective_00N), checked by gameStats.checkN.
OBJECTIVE_LABELS = ('menus/objectives/objective_001', 'menus/objectives/objective_002',
                    'menus/objectives/objective_003')
# Owner's additions (2026-10-26), not the X360's: before the end card, a tally of the objectives checked off
# (`checkN`), then one of these.
TALLY_TEXT = 'You completed {} out of {} objectives.'
TALLY_ALL, TALLY_SOME = 'Congratulations, you are the King of Diss!', 'Try again to complete them all.'
# ...and a scene transition into these events (SHS's location-change selector, 20: one of its two blinds). The X360
# cuts there; the condition is the one its scripts run the event under after a talk's last line.
TRANSITION_EVENTS = {'kingofdiss/diss_battle': '(conversations >= 5)'}
SCENE_TRANSITION = 20
# Script state that only drives the 3D/GUI presentation.
GUI_STATE = {'cam', 'firstChoice', 'scrolling', 'choiceStarted', 'optionSelected', 'objectives', 'newObj', 'tod'}
IGNORED_CALLS = re.compile(r'^(Wait|WaitFrames|Log|CreateCharacter|scene\..*|game\._.*|camera\..*|gui\..*|me\..*'
                           r'|guiscreen\..*|GuiScreen\.CloseControl|gameSHS\.(CameraPanTo|CameraPathLookAt|AddCharacter|'
                           r'SetCharacterPosition|PlayCharacterEmotion|MoveCharacter|PlayBlockingAnim|CloseChoice)'
                           r'|DissComment|rotateToAndBack.*|dissTutorial)$')


@dataclass
class Cast:
    id: str
    name: str
    theme: int                          # 1 male (blue), 2 female (pink)
    look: str = ''                      # a New Rules look (nr_looks.json key), drawn by nr_art
    bank: int | None = None             # or a shared-bank portrait base (five consecutive IDs)


@dataclass
class Story:
    title: str
    episode_id: int
    events: list                        # events played in order (a later one only if the earlier falls through)
    cast: list
    locations: dict                     # X360 LocationName -> New Rules location number
    player: str = ''


# The New Rules looks King of Diss gives these characters (nr_looks.json; its $josh's first look).
DAY_OF_DISS = Story('Day of Diss', 1, ['kingofdiss/introduction'], [
    Cast('josh', 'Josh', 1, '0020'), Cast('kim', 'Kim', 2, '0027'), Cast('ryan', 'Ryan', 1, '0042'),
    Cast('nicole', 'Nicole', 2, '0038'), Cast('hector', 'Hector', 1, '0016')],
    {'parking_lot': 23, 'diss_battle': 23}, player='josh')
# The test's hero is the zach model, called Josh in its text; Moondog's look is Dancing Queen's.
PUZZLE_TEST = Story('Puzzle Test', 2, ['prototype/puzzle/event1', 'prototype/puzzle/event2'], [
    Cast('zach', 'Josh', 1, '0020'), Cast('moondog', 'Moondog', 1, '0214'), Cast('beth', 'Beth', 2, bank=2050)],
    {'zachs_room': 5, 'beths_room': 4}, player='zach')
STORIES = {'day-of-diss': DAY_OF_DISS, 'puzzle-test': PUZZLE_TEST}


class TranslateError(ValueError):
    pass


# -- the prototype's files ------------------------------------------------------------------------------------------
def read_pak(data):
    """data.pak -> {path: bytes}: a tongas_pack_v20000 table of (offset, size, name), every blob LZMA "alone"."""
    if data[:18] != PAK_MAGIC:
        raise TranslateError('not a tongas_pack_v20000 data.pak')
    count = struct.unpack_from('<I', data, 18)[0]
    pos, files = 26, {}
    for _ in range(count):
        offset, size, length = struct.unpack_from('<III', data, pos)
        name = data[pos + 12:pos + 12 + length].decode('latin-1')
        pos += 12 + length
        files[name] = lzma.decompress(data[offset:offset + size], format=lzma.FORMAT_ALONE)
    return files


WC_DIGITS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789*+'


def decode_wc(value):
    """A unistring "Text" property: 'WC' + three base-64 digits per UTF-16 unit, low digit first."""
    body = value[2:]
    return ''.join(chr(sum(WC_DIGITS.index(body[i + k]) << 6 * k for k in range(3)))
                   for i in range(0, len(body) - 2, 3))


def template_objects(xml, kind):
    """{name: {property: value}} for one object type in a .wxr template (WC text decoded, CDATA unwrapped)."""
    objects = {}
    for m in re.finditer(rf'<object key="[^"]*" type="{kind}" name="([^"]*)"(.*?)</object>', xml, re.S):
        props = {}
        for p in re.finditer(r'<p k="[^"]*" n="(\w+)"[^>]*>(.*?)</p>', m.group(2), re.S):
            value = p.group(2).strip()
            cdata = re.fullmatch(r'<!\[CDATA\[(.*)\]\]>', value, re.S)
            if cdata:
                value = cdata.group(1)
            elif value.startswith('WC'):
                value = decode_wc(value)
            props.setdefault(p.group(1), value)
        objects[m.group(1)] = props
    return objects


class Prototype:
    def __init__(self, pak_bytes):
        self.files = read_pak(pak_bytes)
        text = lambda path: self.files[path].decode('utf-8')        # noqa: E731
        self.strings = {k: v.get('Text', '') for k, v in
                        template_objects(text('data/templates/unistrings.wxr'), 'UNISTRINGSMASTER').items()}
        self.events = template_objects(text('data/templates/eventconfig.wxr'), 'EVENTCONFIGMASTER')
        self.labels = {k: v.get('Text', '') for k, v in
                       template_objects(text('data/templates/guilabel.wxr'), 'GUILABELMASTER').items()}

    def script(self, path):
        return lua_subset.parse(self.files[f'data/scripts/{path}.lua'].decode('utf-8'))

    def event(self, name):
        event = self.events[name]
        return event.get('LocationName', ''), lua_subset.parse(event['Script'])

    def text(self, key, depth=0):
        """A unistring with its `[:id]` includes and `<:str,id>` names resolved (a name is the speaker's name-plate
        string, "<:color,...><:font,1>Josh<:color,...><:font,0>", without its codes and in backticks: the X360 draws
        an inserted name in its plate colour, SHS draws backticked text in the emphasis colour); other codes kept."""
        if key not in self.strings:
            raise TranslateError(f'no unistring {key!r}')
        value = self.strings[key]
        if depth < 8:
            value = re.sub(r'\[:([^\]]+)\]', lambda m: self.text(m.group(1), depth + 1), value)
            value = re.sub(r'<:str,([^>]+)>',
                           lambda m: '`' + re.sub(r'<:[^>]*>', '', self.text(m.group(1), depth + 1)) + '`', value)
        return value


IMA_STEPS = (7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88,
             97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
             724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660,
             4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818,
             18500, 20350, 22385, 24623, 27086, 29794, 32767)
IMA_INDEX = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)


def pcm_wav(data):
    """A RIFF WAVE as 16-bit PCM: the X360's effect sounds are mono IMA ADPCM (format 0x11), decoded here so the
    player needs no ADPCM codec; PCM passes through."""
    pos, fmt, body = 12, None, None
    while pos + 8 <= len(data):
        tag, size = data[pos:pos + 4], struct.unpack_from('<I', data, pos + 4)[0]
        if tag == b'fmt ':
            fmt = struct.unpack_from('<HHIIHH', data, pos + 8) + (data[pos + 8 + 16:pos + 8 + size],)
        elif tag == b'data':
            body = data[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)
    code, channels, rate, _, block, _, _ = fmt
    if code == 1:
        return data
    if code != 0x11 or channels != 1:
        raise TranslateError(f'unsupported WAV format {code:#x}, {channels} channels')
    out = bytearray()
    for start in range(0, len(body) - 3, block):
        chunk = body[start:start + block]
        sample, index = struct.unpack_from('<hB', chunk)
        out += struct.pack('<h', sample)
        for byte in chunk[4:]:
            for nibble in (byte & 15, byte >> 4):
                step = IMA_STEPS[index]
                diff = step >> 3
                if nibble & 1: diff += step >> 2                    # noqa: E701
                if nibble & 2: diff += step >> 1                    # noqa: E701
                if nibble & 4: diff += step                         # noqa: E701
                sample = max(-32768, min(32767, sample - diff if nibble & 8 else sample + diff))
                index = max(0, min(88, index + IMA_INDEX[nibble]))
                out += struct.pack('<h', sample)
    header = struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + len(out), b'WAVE', b'fmt ', 16, 1, 1, rate, rate * 2, 2, 16,
                         b'data', len(out))
    return header + bytes(out)


def emoticon_cells(png):
    """The first EFFECT_CELLS cells of the X360's square emoticon sheet (EFFECT_GRID x EFFECT_GRID), as PNG bytes."""
    from io import BytesIO
    from PIL import Image
    sheet = Image.open(BytesIO(png)).convert('RGBA')
    cell = sheet.width // EFFECT_GRID
    return [nr_art.png(sheet.crop(((i % EFFECT_GRID) * cell, (i // EFFECT_GRID) * cell,
                                   (i % EFFECT_GRID + 1) * cell, (i // EFFECT_GRID + 1) * cell)))
            for i in range(EFFECT_CELLS)]


PLAIN = str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"', '…': '...', '–': '-',
                       '—': '-', ' ': ' '})


def story_text(value, *, label=False):
    """The X360's formatting taken out: colour (`&:R G B;`, `<:color,..>`), size (`!:N;`), font (`<:font,N>`) and
    inline images (`{:...}`); line breaks
    become spaces, and a spaced ellipsis (". . .") is joined into "..." (onto the word it ends or starts a line
    with). Backticks (King of Diss's rhyme emphasis, inserted names) stay in dialogue, where SHS shows them as
    emphasis, and leave menu labels, where SHS would print them. Latin-1, as the creator compiles story text."""
    value = re.sub(r'&:\d+ \d+ \d+;|!:\d+;|\{:[^}]*\}|<:[^>]*>', '', value).replace('\r', '').replace('\n', ' ')
    value = re.sub(r'\.(?: *\.){2,}', '...', value.translate(PLAIN))
    value = re.sub(r' {2,}', ' ', value).strip()
    value = re.sub(r' +\.\.\.$', '...', re.sub(r'^\.\.\. +', '...', value))
    if label:
        value = value.replace('`', '')
    try:
        value.encode('latin-1')
    except UnicodeEncodeError as error:
        raise TranslateError(f'text outside Latin-1: {value!r}') from error
    return value


# -- Lua -> graph -----------------------------------------------------------------------------------------------------
def variable(dotted):
    """A script variable -> a creator variable: gameStats.kim -> kim, kimDialogs.side -> kim_side."""
    head, _, tail = dotted.partition('.')
    if head == 'gameStats' and tail and '.' not in tail:
        return tail
    m = re.fullmatch(r'(\w+)Dialogs', head)
    if m and tail and '.' not in tail:
        return f'{m.group(1)}_{tail}'
    return None


def expression(expr):
    """A Lua expression over script variables -> creator expression syntax."""
    kind = expr[0]
    if kind == 'num':
        if expr[1] != int(expr[1]):
            raise TranslateError(f'not an integer: {expr[1]}')
        return str(int(expr[1]))
    if kind == 'bool':
        return '1' if expr[1] else '0'
    if kind == 'nil':
        return '0'
    if kind in ('name', 'field', 'index'):
        name = variable(lua_subset.dotted(expr) or '')
        if name is None:
            raise TranslateError(f'not a story variable: {expr}')
        return name
    if kind == 'unop':
        op = {'not': 'not ', '-': '-'}.get(expr[1])
        if op is None:
            raise TranslateError(f'operator {expr[1]}')
        return f'{op}({expression(expr[2])})'
    if kind == 'binop':
        op = {'~=': '!=', '/': '//'}.get(expr[1], expr[1])
        if op not in ('or', 'and', '<', '>', '<=', '>=', '!=', '==', '+', '-', '*', '//', '%'):
            raise TranslateError(f'operator {expr[1]}')
        return f'({expression(expr[2])} {op} {expression(expr[3])})'
    raise TranslateError(f'expression {expr}')


def call_name(expr):
    return lua_subset.dotted(expr[1]) if expr[0] == 'callx' else None


def string_arg(args, index):
    if len(args) <= index:
        return None
    arg = args[index]
    if arg[0] == 'str':
        return arg[1]
    if arg[0] == 'callx' and call_name(arg) == 'ToUniString' and arg[2] and arg[2][0][0] == 'str':
        return arg[2][0][1]
    return None


class Builder:
    """Walks the scripts in order, appending graph nodes. `pending` holds the open exits, (node id, slot): 'next',
    'otherwise' or ('option', i); the next node created takes them all."""

    def __init__(self, proto: Prototype, story: Story, music=None, chained=()):
        self.proto, self.story, self.music = proto, story, music or {}
        self.chained = set(chained)         # loop cues an intro already runs into (MUSIC_INTRO / MUSIC_LOOP)
        self.nodes, self.pending, self.count = [], [], 0
        self.speaker = None
        self.emotions = {}
        self.choices = []
        self.choice_emotions = {}
        self.conditions = []
        self.event_starts = {}
        self.hub = None
        self.gameover = False
        self.bubble = 0                 # the open dialogue's OpenDialog type (SING_TYPE: the sing bubble)
        self.effects = []               # (character, emoticon effect) waiting for the next line
        self.effects_skipped = 0
        self.sounds = {}                # effect -> its embedded sound's ID (translate() fills it)
        self.objective_sound = None     # OBJECTIVE_SOUND's ID, when embedded
        self.line_start = None          # the first node of the latest line (its effect's score node, or the line)
        self.line_exit = None           # `pending` as that line left it
        self.transitions = 0            # lines given a transition (transition_into)
        self.cast = {c.id: c for c in story.cast}
        self.backgrounds = {}

    # graph plumbing
    def add(self, kind, **fields):
        self.count += 1
        node = Node(f'n{self.count}', kind, **fields)
        self.nodes.append(node)
        self.link(node.id)
        self.pending = [] if kind in ('end', 'choice', 'branch') else [(node.id, 'next')]
        return node

    def link(self, target):
        by_id = {n.id: n for n in self.nodes}
        for node_id, slot in self.pending:
            node = by_id[node_id]
            if slot == 'next':
                node.next = target
            elif slot == 'otherwise':
                node.otherwise = target
            else:
                node.options[slot[1]].target = target
        self.pending = []

    def insert_before(self, target, kind, **fields):
        """A node spliced in ahead of an already-linked one: everything that led to `target` leads to it instead."""
        self.count += 1
        node = Node(f'n{self.count}', kind, **fields)
        for other in self.nodes:
            if other.next == target:
                other.next = node.id
            if other.otherwise == target:
                other.otherwise = node.id
            for option in other.options or ():
                if option.target == target:
                    option.target = node.id
        for name, start in self.event_starts.items():
            if start == target:
                self.event_starts[name] = node.id
        node.next = target
        self.nodes.append(node)
        return node

    # statements
    def block(self, statements):
        for statement in statements:
            self.statement(statement)

    def statement(self, s):
        kind = s[0]
        if kind == 'call':
            self.call(s[1])
        elif kind == 'assign':
            for target, value in zip(s[1], s[2]):
                self.assign(target, value)
        elif kind == 'if':
            self.branch(s[1], s[2])
        elif kind in ('while', 'local', 'function', 'repeat'):
            pass                    # waits, helpers and locals only drive the presentation
        elif kind == 'do':
            self.block(s[1])
        else:
            raise TranslateError(f'statement {kind}')

    def assign(self, target, value):
        name = lua_subset.dotted(target) or ''
        if name == 'scene.level.Resources.0' or target[0] == 'index' and lua_subset.dotted(target[1]) == \
                'scene.level.Resources':
            cue = value[1] if value[0] == 'str' else ''
            if cue.startswith('SNFX:music/') and cue[11:] in self.chained:
                return                      # the runtime runs the intro into this loop by itself
            if cue.startswith('SNFX:music/') and cue[11:] in self.music:
                self.add('music', params={'resource': self.music[cue[11:]], 'loop': True})
            return
        if name.endswith('.gameovertext.Text') and self.gameover:
            key = string_arg([value], 0)
            text = self.proto.text(key[2:-1]) if key and key.startswith('[:') else key
            if self.hub is not None:            # a story with objectives (the hub lists them)
                self.objective_tally()
            self.add('message', text=story_text(text), params={'title': '', 'flag': 0})
            self.add('end')
            return
        var = variable(name)
        if var is None or value[0] == 'table' or var in GUI_STATE:
            return
        follows_line = self.line_start is not None and self.pending == self.line_exit
        self.add('set', variable=var, params={'expression': expression(value)})
        m = re.fullmatch(r'check([123])', var)
        if m and value == ('bool', True):
            # SHS shows a notice with the next line, and each conversation goes straight back to the hub's choice,
            # which would hold it to the next talk: when the objective comes straight after a line, it goes ahead
            # of that line instead. With the X360's success sound.
            put = (lambda kind, **f: self.insert_before(self.line_start, kind, **f)) if follows_line else self.add
            notice = put('notice', text='Objective Complete')
            if self.objective_sound is not None:
                put('sound', params={'resource': self.objective_sound})
            if follows_line:
                self.line_start = notice.id

    def objective_tally(self):
        """Narration: how many objectives were checked off, then TALLY_ALL or TALLY_SOME."""
        total = len(OBJECTIVE_LABELS)
        count = ' + '.join(f'check{i}' for i in range(1, total + 1))
        self.add('set', variable='objectives_done', params={'expression': f'({count})'})
        ends = []
        for n in range(total, -1, -1):
            if n:
                node = self.add('branch', params={'expression': f'(objectives_done == {n})'})
                self.pending = [(node.id, 'next')]
            self.add('dialogue', text=TALLY_TEXT.format(n, total))
            self.add('dialogue', text=TALLY_ALL if n == total else TALLY_SOME)
            ends += self.pending
            if n:
                self.pending = [(node.id, 'otherwise')]
        self.pending = ends

    def transition_into(self, condition):
        """SHS plays a queued transition when the next panel is dismissed, so the transition into an event goes ahead
        of each line that can be the last before it (under the condition the event runs on): that line leaves through
        it, and the event's first line comes in through it."""
        by_id = {n.id: n for n in self.nodes}
        leads = {}
        for node in self.nodes:
            for target in [node.next, node.otherwise] + [o.target for o in node.options or ()]:
                if target:
                    leads.setdefault(target, []).append(node.id)
        lines, seen, todo = [], set(), [node_id for node_id, _ in self.pending]
        while todo:
            node_id = todo.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            node = by_id[node_id]
            if node.kind == 'dialogue':
                lines.append(node_id)
            elif node.kind == 'choice':
                # Only through an answer test's fall-through (`if choice == 0 ... elseif choice == 1 ... end`), which
                # no answer takes; x360_check confirms every played path's transition.
                continue
            elif node.kind in ('message', 'end'):
                raise TranslateError(f'{node.kind} {node_id} comes between a transition and its last line')
            else:
                todo += leads.get(node_id, [])
        def last(line):                         # no line can follow it before the event (or the hub's choice)
            todo, walked = [by_id[line].next], set()
            while todo:
                node_id = todo.pop()
                if not node_id or node_id in walked:
                    continue
                walked.add(node_id)
                node = by_id[node_id]
                if node.kind == 'dialogue':
                    return False
                if node.kind != 'choice':
                    todo += [node.next, node.otherwise] + [o.target for o in node.options or ()]
            return True
        # A line that another can follow was only reached back through a fall-through no value takes (Kim's
        # `kim >= 5` / `kim <= -5` / in between): it is never the last.
        lines = [line for line in lines if last(line)]
        for line in sorted(lines, key=lambda node_id: int(node_id[1:])):
            fade = self.insert_before(line, 'transition', params={'selector': SCENE_TRANSITION})
            test = self.insert_before(fade.id, 'branch', params={'expression': condition})
            test.otherwise = line
        return lines

    def branch(self, arms, otherwise):
        # `if gameStats == nil then gameStats = {} end` and the like only set up tables.
        if len(arms) == 1 and otherwise is None and arms[0][0][0] == 'binop' and arms[0][0][3] == ('nil',):
            if lua_subset.dotted(arms[0][0][2]) in ('gameStats', 'gameStats.tod'):
                return
        (cond, body), rest = arms[0], arms[1:]
        if self.collecting and all(
                st[0] == 'call' and call_name(st[1]) == 'gameSHS.AddChoices' for st in body) and not rest \
                and otherwise is None:
            self.conditions.append(expression(cond))
            self.block(body)
            self.conditions.pop()
            return
        node = self.add('branch', params={'expression': expression(cond)})
        saved = dict(self.emotions)
        self.pending = [(node.id, 'next')]
        m = self.choice_test(cond)
        if m is not None and m in self.choice_emotions:
            self.emotions.update(self.choice_emotions[m])
        self.block(body)
        ends = self.pending
        self.emotions = dict(saved)
        self.pending = [(node.id, 'otherwise')]
        if rest:
            self.branch(rest, otherwise)
        elif otherwise:
            self.block(otherwise)
        self.emotions = saved
        self.pending = ends + self.pending

    @staticmethod
    def choice_test(cond):
        if cond[0] == 'binop' and cond[1] == '==' and lua_subset.dotted(cond[2]) == 'gameStats.choice' \
                and cond[3][0] == 'num':
            return int(cond[3][1])
        return None

    collecting = False

    def call(self, expr):
        if expr[0] == 'method':
            return
        name, args = call_name(expr), expr[2]
        effect = re.fullmatch(r'scene\.(\w+)\.CreateFx', name or '')
        if effect:                              # an emoticon over a character, shown with their next line
            fx = (string_arg(args, 0) or '').rpartition('hud/emoticon/')[2]
            if fx in X360_EFFECTS:
                self.effects.append((effect.group(1), X360_EFFECTS[fx]))
            return
        if name is None or IGNORED_CALLS.match(name):
            return
        if name == 'OpenDialog':
            self.speaker = string_arg(args, 0)
            self.bubble = int(args[1][1]) if len(args) > 1 and args[1][0] == 'num' else 0
        elif name == 'CloseDialog':
            self.speaker = None
        elif name == 'DialogText':
            self.line(self.speaker, string_arg(args, 0))
        elif name == 'Dialog':
            self.bubble = 0                     # the older call names its bubble group; no sing type
            self.line(string_arg(args, 0), string_arg(args, 3))
        elif name == 'gameSHS.SetCharacterEmotion':
            self.emotions[string_arg(args, 0)] = string_arg(args, 1)
        elif name == 'gameSHS.ClearChoices':
            self.choices, self.collecting = [], True
        elif name == 'gameSHS.AddChoices':
            self.choices.append((string_arg(args, 0), string_arg(args, 2) or '', string_arg(args, 3) or '',
                                 ' and '.join(self.conditions)))
        elif name == 'gameSHS.OpenChoice':
            self.choice()
        elif name == 'RunScript':
            path = string_arg(args, 0)
            if path.startswith('dialogs/'):
                self.block(self.proto.script(path))
        elif name in ('GuiScreen.AddControl', 'guiscreen.AddControl'):
            group = string_arg(args, 1) or ''
            if group == 'GGRP:hud/selection/main':
                self.open_hub()
            elif group == 'GGRP:hud/gameover/main':
                self.gameover = True
        elif name == 'game.RunEvent':
            event = string_arg(args, 0)
            if event in TRANSITION_EVENTS:
                self.transitions += len(self.transition_into(TRANSITION_EVENTS[event]))
            self.run_event(event)
        else:
            raise TranslateError(f'call {name}')

    def line(self, who, key):
        text = story_text(self.proto.text(key))
        if self.bubble == SING_TYPE:            # the sing bubble: SHS frames a song line in its music notes
            text = f'{SING_MARK} {text} {SING_MARK}'
        effects, self.effects = self.effects, []
        self.line_start = f'n{self.count + 1}'
        if not who:
            self.add('dialogue', text=text)
            self.line_exit = self.pending
            return
        if who not in self.cast:
            raise TranslateError(f'speaker {who!r} has no cast entry')
        emotion = self.emotions.get(who, 'neutral')
        if emotion not in EMOTION:
            raise TranslateError(f'emotion {emotion!r}')
        # Only the speaker's portrait is on screen: an emoticon on anyone else is left out (counted).
        mine = [number for target, number in effects if target == who]
        self.effects_skipped += len(effects) - len(mine)
        if mine:
            number = mine[-1]
            self.add('score', params={'owner': 0, 'key': EFFECT_KEY, 'operation': 'set', 'value': number,
                                      'notification': '', 'result': 'effect'})
            if number in self.sounds:
                self.add('sound', params={'resource': self.sounds[number]})
        self.add('dialogue', text=text, character=who, expression=EMOTION[emotion])
        if mine:
            self.add('score', params={'owner': 0, 'key': EFFECT_KEY, 'operation': 'set', 'value': 0,
                                      'notification': '', 'result': 'effect'})
        self.line_exit = self.pending

    def choice(self):
        options = self.choices
        self.collecting = False
        if not 2 <= len(options) <= 8:
            raise TranslateError(f'{len(options)} choice options')
        node = self.add('choice', text=CHOICE_TITLE, character=self.story.player, theme=1,
                        options=[Choice(story_text(self.proto.text(t[2:-1]) if t.startswith('[:') else t,
                                                   label=True), '', cond) for t, _, _, cond in options])
        ends, self.choice_emotions = [], {}
        for i, (_, preview, real, _) in enumerate(options):
            self.pending = [(node.id, ('option', i))]
            before = dict(self.emotions)
            for statement in lua_subset.parse(preview):
                if statement[0] == 'call' and call_name(statement[1]) == 'gameSHS.SetCharacterEmotion':
                    self.call(statement[1])
            value = None
            for statement in lua_subset.parse(real):
                if statement[0] == 'assign' and lua_subset.dotted(statement[1][0]) == 'gameStats.choice':
                    value = int(statement[2][0][1])
                self.statement(statement)
            if value is not None:
                self.choice_emotions[value] = {k: v for k, v in self.emotions.items() if before.get(k) != v}
            self.emotions = before
            ends += self.pending
        self.pending = ends
        self.choices = []

    def open_hub(self):
        if self.hub is not None:
            self.link(self.hub)
            return
        labels = [story_text(self.proto.labels[key]) for key in OBJECTIVE_LABELS]
        self.add('message', text='\n'.join(f'- {label}' for label in labels), params={'title': 'Objectives',
                                                                                    'flag': 0})
        hub = self.add('choice', text=HUB_TITLE, character=self.story.player, theme=1,
                       options=[Choice(name, '', f'(minSel <= {i}) and ({i} <= maxSel)')
                                for i, (name, _) in enumerate(HUB, 1)])
        self.hub = hub.id
        ends = []
        for i, (_, who) in enumerate(HUB):
            self.pending = [(hub.id, ('option', i))]
            self.emotions, self.speaker = dict(self.emotions), None
            self.block(self.proto.script(f'dialogs/{who}/dialog_001'))
            ends += self.pending
        self.pending = ends

    def run_event(self, name):
        if name in self.event_starts:
            self.link(self.event_starts[name])
            return
        location, script = self.proto.event(name)
        if location not in self.story.locations:
            raise TranslateError(f'{name}: location {location!r} has no background')
        node = self.add('background', asset=self.backgrounds[self.story.locations[location]], params={'variant': 0})
        self.event_starts[name] = node.id
        self.block(script)


def even_level(intro, loop, window_s=2.0, settle_s=4.0, peak=0.89):
    """(intro, loop) 16-bit WAV bytes at one level (owner, 2026-10-26: Day of Diss's dont_trust_me opens loud, scoring
    the prototype's cutscene, then settles at the loop's level). The intro is turned down, never up, wherever its
    loudness over `window_s` passes the loop's, through a gain smoothed over the same window; over its last
    `settle_s` the gain eases to 1, so the intro still meets the loop exactly. Then both take one shared gain that puts
    the louder peak at `peak` (as midi_render's renders)."""
    import io
    import wave
    import numpy as np

    def read(data):
        with wave.open(io.BytesIO(data)) as clip:
            params = clip.getparams()
            samples = np.frombuffer(clip.readframes(params.nframes), '<i2').astype(np.float64) / 32768
        return samples.reshape(-1, params.nchannels), params

    def average(values, n):
        sums = np.concatenate(([0.0], np.cumsum(values)))
        low = np.clip(np.arange(len(values)) - n // 2, 0, len(values))
        high = np.clip(np.arange(len(values)) + n // 2 + 1, 0, len(values))
        return (sums[high] - sums[low]) / (high - low)

    def write(samples, params):
        out = io.BytesIO()
        with wave.open(out, 'wb') as clip:
            clip.setparams(params)
            clip.writeframes((np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())
        return out.getvalue()

    a, a_params = read(intro)
    b, b_params = read(loop)
    target = np.sqrt((b ** 2).mean())
    n = max(1, int(window_s * a_params.framerate))
    loudness = np.sqrt(average((a ** 2).mean(axis=1), n))
    gain = average(np.minimum(1.0, target / np.maximum(loudness, 1e-9)), n)
    tail = min(len(gain), int(settle_s * a_params.framerate))
    if tail:
        gain[-tail:] = gain[-tail:] + (1.0 - gain[-tail:]) * np.linspace(0, 1, tail)
    a = a * gain[:, None]
    shared = peak / max(np.abs(a).max(), np.abs(b).max())
    return write(a * shared, a_params), write(b * shared, b_params)


def music_assets(files, music):
    """Assets for the prototype's own music (cue -> bytes), each cue mapped in `music` to its resource. A cue with a
    `<cue>_loop` file is an intro the runtime runs into that loop without a gap (MUSIC_INTRO into MUSIC_LOOP, shs
    profile TRANSLATED_MUSIC_LOOPS): only the intro is started, and the prototype's later switch to the loop cue is
    left to the runtime (the returned `chained` cues). A WAV pair is brought to one level first (even_level). Any other
    cue takes the next ID from MUSIC_OTHER."""
    assets, chained, other = [], set(), MUSIC_OTHER
    for cue, data in sorted(files.items()):
        if cue.endswith('_loop') and cue[:-5] in files:
            continue
        if cue + '_loop' in files:
            if chained:
                raise TranslateError('only one intro and loop pair has IDs of its own (MUSIC_INTRO, MUSIC_LOOP)')
            loop = files[cue + '_loop']
            if data[:4] == b'RIFF' and loop[:4] == b'RIFF':
                data, loop = even_level(data, loop)            # the WAVs, at one level
            assets += [Asset(MUSIC_INTRO, f'music {cue}', data), Asset(MUSIC_LOOP, f'music {cue}_loop', loop)]
            music[cue] = MUSIC_INTRO
            chained.add(cue + '_loop')
        else:
            assets.append(Asset(other, f'music {cue}', data))
            music[cue], other = other, other + 1
    return assets, chained


def translate(proto: Prototype, story: Story, art: nr_art.Art, hires_art=None, looks=None, music=None,
              music_files=None) -> Project:
    """One story as a creator Project. `art`/`hires_art`: nr_art.Art over res_large.pud / the X1i jar; `looks`:
    nr_looks.json's records; `music`: X360 cue name -> SHS resource ID; `music_files`: X360 cue name -> the
    prototype's own audio (WAV or MP3 bytes), embedded in the episode (music_assets)."""
    music = dict(music or {})
    assets, chained = music_assets(music_files or {}, music)
    builder = Builder(proto, story, music, chained)
    project = Project(title=story.title, game='shs', pack_id=PACK_ID, episode_id=story.episode_id, nodes=[])
    project.assets.extend(assets)
    for k, location in enumerate(sorted(set(story.locations.values()))):
        asset_id = BACKGROUND_BASE + 5 * k
        project.assets.append(Asset(asset_id, f'location {location}', nr_art.jpeg(art.background(location, 0))))
        builder.backgrounds[location] = asset_id
    backdrop = art.backdrop()
    if backdrop is not None:
        project.assets.append(Asset(FRAME_BACKDROP, 'frame backdrop', nr_art.png(backdrop)))
    if EFFECT_SHEET in proto.files:
        for i, cell in enumerate(emoticon_cells(proto.files[EFFECT_SHEET])):
            project.assets.append(Asset(EFFECT_IMAGE_BASE + i, f'emoticon {i + 1}', cell))
    for number, (path, asset_id) in sorted(EFFECT_SOUNDS.items()):
        if path in proto.files:
            project.assets.append(Asset(asset_id, f'emoticon {number} sound', pcm_wav(proto.files[path])))
            builder.sounds[number] = asset_id
    if OBJECTIVE_SOUND[0] in proto.files:
        builder.objective_sound = OBJECTIVE_SOUND[1]        # embedded below if an objective is checked off
    for k, cast in enumerate(story.cast):
        if cast.bank is not None:
            base = cast.bank
            for i in range(5):
                project.assets.append(Asset(base + i, f'{cast.name} {i}', None))
        else:
            base = PORTRAIT_BASE + 5 * k
            slots = looks[cast.look]['slots']
            for i, picture in enumerate(art.portrait_bank(list(slots), EXPRESSIONS)):
                project.assets.append(Asset(base + i, f'{cast.name} {i}', nr_art.png(picture)))
            if hires_art is not None:
                pictures = hires_art.portrait_bank(list(slots), EXPRESSIONS, nr_art.HIRES_PORTRAIT_SCALE)
                for i, picture in enumerate(pictures):
                    project.assets.append(Asset(base + HIRES_PORTRAIT_OFFSET + i, f'{cast.name} HD {i}',
                                                nr_art.png(picture)))
        project.characters.append(Character(cast.id, cast.name, base, cast.theme, [base + i for i in range(5)]))
    builder.add('speakers', params={'player': story.player, 'narrator': ''})
    # No SHS relationship badges (the owner's call, 2026-10-26): the X360 shows none, and its own emoticons take the
    # portrait's corner. Property 629 = 1 hides a character's badge; the relationship (407) is left as it is.
    for cast in story.cast:
        builder.add('relationship', character=cast.id, params={'operation': 'add', 'value': 0, 'romantic': False,
                                                                'hide': True, 'result': f'badge_{cast.id}'})
    for name in story.events:
        builder.run_event(name)
    if builder.pending:
        builder.add('end')
    if any(n.kind == 'notice' for n in builder.nodes) and builder.objective_sound is not None:
        project.assets.append(Asset(OBJECTIVE_SOUND[1], 'objective sound', pcm_wav(proto.files[OBJECTIVE_SOUND[0]])))
    project.nodes = builder.nodes
    project.start = builder.nodes[0].id
    for i, node in enumerate(project.nodes):
        node.x, node.y = 40 + 320 * (i % 12), 80 + 140 * (i // 12)
    return project
