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

import lua_subset
import nr_art

PAK_MAGIC = b'tongas_pack_v20000'
PACK_ID = 31400                         # shs/profile.py: TRANSLATED_PORTRAIT_ART
BACKGROUND_BASE = 26000                 # five IDs apart, as the creator allocates
PORTRAIT_BASE = 26200                   # five consecutive IDs per look
HIRES_PORTRAIT_OFFSET = 1000            # the X1i (HD-sized) set, as the New Rules translation stores it
FRAME_BACKDROP = 26999                  # New Rules' UI backdrop under the strips (shs/profile.py TRANSLATED_FRAME_BACKDROP)
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
        string, "<:color,...><:font,1>Josh<:color,...><:font,0>", without its codes); other codes kept."""
        if key not in self.strings:
            raise TranslateError(f'no unistring {key!r}')
        value = self.strings[key]
        if depth < 8:
            value = re.sub(r'\[:([^\]]+)\]', lambda m: self.text(m.group(1), depth + 1), value)
            value = re.sub(r'<:str,([^>]+)>', lambda m: re.sub(r'<:[^>]*>', '', self.text(m.group(1), depth + 1)),
                           value)
        return value


PLAIN = str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"', '…': '...', '–': '-',
                       '—': '-', ' ': ' '})


def story_text(value, *, label=False):
    """The X360's formatting taken out: colour (`&:R G B;`, `<:color,..>`), size (`!:N;`), font (`<:font,N>`) and
    inline images (`{:...}`); line breaks
    become spaces. Backticks (King of Diss's rhyme emphasis) stay in dialogue, where SHS shows them as emphasis, and
    leave menu labels, where SHS would print them. Latin-1, as the creator compiles story text."""
    value = re.sub(r'&:\d+ \d+ \d+;|!:\d+;|\{:[^}]*\}|<:[^>]*>', '', value).replace('\r', '').replace('\n', ' ')
    value = re.sub(r' {2,}', ' ', value.translate(PLAIN)).strip()
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

    def __init__(self, proto: Prototype, story: Story, music=None):
        self.proto, self.story, self.music = proto, story, music or {}
        self.nodes, self.pending, self.count = [], [], 0
        self.speaker = None
        self.emotions = {}
        self.choices = []
        self.choice_emotions = {}
        self.conditions = []
        self.event_starts = {}
        self.hub = None
        self.gameover = False
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
            if cue.startswith('SNFX:music/') and cue[11:] in self.music:
                self.add('music', params={'resource': self.music[cue[11:]], 'loop': True})
            return
        if name.endswith('.gameovertext.Text') and self.gameover:
            key = string_arg([value], 0)
            text = self.proto.text(key[2:-1]) if key and key.startswith('[:') else key
            self.add('message', text=story_text(text), params={'title': '', 'flag': 0})
            self.add('end')
            return
        var = variable(name)
        if var is None or value[0] == 'table' or var in GUI_STATE:
            return
        self.add('set', variable=var, params={'expression': expression(value)})
        m = re.fullmatch(r'check([123])', var)
        if m and value == ('bool', True):
            label = story_text(self.proto.labels[OBJECTIVE_LABELS[int(m.group(1)) - 1]])
            self.add('notice', text=f'Objective complete: {label}')

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
        if name is None or IGNORED_CALLS.match(name):
            return
        if name == 'OpenDialog':
            self.speaker = string_arg(args, 0)
        elif name == 'CloseDialog':
            self.speaker = None
        elif name == 'DialogText':
            self.line(self.speaker, string_arg(args, 0))
        elif name == 'Dialog':
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
            self.run_event(string_arg(args, 0))
        else:
            raise TranslateError(f'call {name}')

    def line(self, who, key):
        text = story_text(self.proto.text(key))
        if not who:
            self.add('dialogue', text=text)
            return
        if who not in self.cast:
            raise TranslateError(f'speaker {who!r} has no cast entry')
        emotion = self.emotions.get(who, 'neutral')
        if emotion not in EMOTION:
            raise TranslateError(f'emotion {emotion!r}')
        self.add('dialogue', text=text, character=who, expression=EMOTION[emotion])

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


def translate(proto: Prototype, story: Story, art: nr_art.Art, hires_art=None, looks=None, music=None) -> Project:
    """One story as a creator Project. `art`/`hires_art`: nr_art.Art over res_large.pud / the X1i jar; `looks`:
    nr_looks.json's records; `music`: X360 cue name -> SHS resource ID."""
    builder = Builder(proto, story, music)
    project = Project(title=story.title, game='shs', pack_id=PACK_ID, episode_id=story.episode_id, nodes=[])
    for k, location in enumerate(sorted(set(story.locations.values()))):
        asset_id = BACKGROUND_BASE + 5 * k
        project.assets.append(Asset(asset_id, f'location {location}', nr_art.jpeg(art.background(location, 0))))
        builder.backgrounds[location] = asset_id
    backdrop = art.backdrop()
    if backdrop is not None:
        project.assets.append(Asset(FRAME_BACKDROP, 'frame backdrop', nr_art.png(backdrop)))
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
    for name in story.events:
        builder.run_event(name)
    if builder.pending:
        builder.add('end')
    project.nodes = builder.nodes
    project.start = builder.nodes[0].id
    for i, node in enumerate(project.nodes):
        node.x, node.y = 40 + 320 * (i % 12), 80 + 140 * (i // 12)
    return project
