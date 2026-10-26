"""Compile story graphs into native KiWi, with exact source locations for tools."""
from copy import deepcopy
from dataclasses import dataclass, replace
import json
from itertools import cycle
from pathlib import Path
import re
import struct

from exp_runtime.exp import ExpArchive, Metadata, encode_exp
from exp_runtime.authored import RESOURCE as AUTHORING_RESOURCE, MAGIC as AUTHORING_MAGIC
from exp_runtime.decode.bytecode import decode_program
from .model import Project, ProjectError, atomic_write, is_audio, is_image, is_mp3, project_record, validate_structure
from .features import DEFAULTS, INPUT_GATES, parameters, translated
from . import expressions, minigames

VARIABLE_OWNER = -30000
# The hidden variable that holds the narrator's character number once a Player / narrator node has chosen one; not a
# Python identifier, so no authored expression can name it.
NARRATOR = '#narrator'
# `$KEY` names the native substitution table shares across episodes; any other text key is stored as `{name}`.
SHARED_KEY = re.compile(r'\$[A-Za-z0-9_]+')
PLACEHOLDER = re.compile(r'\{([^{}\n]+)\}')
# Service 0 formats into dynamic string slot 1 - a1 for a negative a1. Slots 2-9 are the creator's own: slot 0 holds
# input answers and stored-text reads, 1 is never selected and 10 is the formatter's scratch.
FORMAT_SLOTS = range(2, 10)
TEXT_KEY_KINDS = {'input': 'result', 'text_branch': 'variable', 'set_text': 'key', 'text_default': 'key',
                  'append_text': 'key'}
# Append text concatenates in VM memory (service 25 writes packed words): one scratch text per script, which holds at
# most TEXT_BUFFER_WORDS * 2 - 1 characters. Native writes past it unchecked.
TEXT_BUFFER_WORDS = 512
# What a failed survey upload shows: the offline runtime replaces exactly this response with its local receipt
# (exp_runtime.shs.survey.CONNECTION_ERROR).
SURVEY_FAILURE = 'Connection failed. Please try again later.'
SHS_ONLY_KINDS = frozenset(('loading', 'survey'))
# SHS HD's side panels: Faceplace (services 113-120) and the Decision Tree (101-112). CoD has neither.
HD_KINDS = frozenset(('faceplace', 'faceplace_post', 'faceplace_link', 'tree', 'tree_node', 'tree_result'))
FACEPLACE_ACTIONS = {'enable': 114, 'clear': 118, 'name_chosen': 119, 'face_chosen': 120, 'default_name': 113}
TREE_ACTIONS = {'enable': 101, 'join': 112, 'clear_accumulator': 108}
# Tree scene types and their results (exp_runtime.dt_layout.SPECS): 1202-1208 are scenes that go straight on; 1209-1223
# wait for a Tree result (dtview_faceplace.AWAITING_NODES); 1219-1223 are branches whose results meet again at a join
# (1219/1220 shown, 1221-1223 automatic). The join itself, 1224, is the Decision Tree node's join action.
TREE_EXITS = {1202: 0, 1203: 1, 1204: 1, 1205: 1, 1206: 1, 1207: 1, 1208: 1, 1209: 2, 1210: 2, 1211: 3, 1212: 2,
              1213: 3, 1214: 2, 1215: 2, 1216: 3, 1217: 4, 1218: 5, 1219: 2, 1220: 3, 1221: 2, 1222: 3, 1223: 4}
TREE_AWAITING = range(1209, 1224)
# `addBranchNode`'s conditions are `DTNode::autobranch` tests of Football Star's tracked state (exp_runtime.dt_state).
TREE_CONDITIONS = range(0x4b, 0x69)


def _node_expression(node):
    p = parameters(node)
    if node.kind == 'set':
        return p['expression'] or str(node.value)
    if node.kind == 'branch':
        return p['expression'] or None
    return None


def node_expressions(node):
    answers = parameters(node)['answers'] if node.kind == 'survey' else []
    answers = [value for value in answers if isinstance(value, str)] if isinstance(answers, list) else []
    return [value for value in [_node_expression(node)] + [o.condition for o in node.options] + answers if value]


def text_key(name):
    """The native substitution key a stored text uses."""
    return name if name.startswith('$') else '{' + name + '}'


def text_keys(project):
    """Stored-text names written as `{name}` in story text (the `$KEY` ones are written as themselves)."""
    return {parameters(n)[TEXT_KEY_KINDS[n.kind]] for n in project.nodes if n.kind in TEXT_KEY_KINDS} - {''}


def variable_names(project):
    names = {n.variable for n in project.nodes if n.kind in ('set', 'branch') and n.variable}
    for node in project.nodes:
        p = parameters(node)
        if node.kind in ('random', 'word_game', 'football', 'grid', 'relationship', 'score', 'picker'):
            names.add(p['result'])
        if node.kind == 'football':
            names.update(name for name in (p['home_result'], p['away_result']) if name)
        if node.kind == 'survey' and isinstance(p['results'], list):
            names.update(p['results'])
        for expression in node_expressions(node):
            names.update(expressions.parse(expression)[1])
    if any(n.kind == 'speakers' and parameters(n)['narrator'] for n in project.nodes):
        names.add(NARRATOR)
    return sorted(names)


def placeholders(value, numeric):
    """`{expression}` spans of a text that format a number: the expression parses, reads a variable or game state,
    and every variable it reads is one of `numeric`. Other braces, such as `{name}` of a stored text or a Faceplace
    emoticon, stay literal."""
    spans = []
    for match in PLACEHOLDER.finditer(value):
        try:
            tree, names = expressions.parse(match.group(1).strip())
        except ProjectError:
            continue
        if (names or expressions.has_calls(tree)) and names <= numeric:
            spans.append((match, tree))
    return spans


def validate_node(project, node, nodes, assets, characters):
    label = node.label or node.id
    if node.kind == 'native':
        raise ProjectError('Native blocks belong to imported native projects')
    for _, target in node.links():
        if target not in nodes:
            raise ProjectError(f'{label}: choose a destination for every connection')
    if node.character and node.character not in characters:
        raise ProjectError(f'{label}: unknown character {node.character}')
    if node.kind == 'choice':
        if not 2 <= len(node.options) <= 8 or any(not o.text.strip() for o in node.options):
            raise ProjectError(f'{label}: provide two to eight nonempty choices')
        if node.timeout_option >= len(node.options):
            raise ProjectError(f'{label}: select an existing answer for timer expiry')
    if node.kind in ('dialogue', 'choice') and not node.text.strip():
        raise ProjectError(f'{label}: enter dialogue or a choice prompt')
    if node.kind == 'set' or node.kind == 'branch' and not parameters(node)['expression']:
        if not node.variable.strip():
            raise ProjectError(f'{label}: enter a variable name')
    if node.kind == 'background' and node.asset not in assets:
        raise ProjectError(f'{label}: select an imported background image')
    if node.kind == 'dialogue' and not node.character and node.portrait is not None:
        if node.portrait not in assets or not node.speaker.strip():
            raise ProjectError(f'{label}: a portrait needs an imported image and a speaker name')
    if node.kind in ('football', 'grid') and project.game != 'shs':
        raise ProjectError(f'{label}: the supplied native CoD game does not implement {node.kind}')
    if set(node.params) - DEFAULTS[node.kind].keys():
        raise ProjectError(f'{label}: unknown parameters {sorted(set(node.params) - DEFAULTS[node.kind].keys())}')
    p = parameters(node)
    for key, default in DEFAULTS[node.kind].items():
        value = p[key]
        if type(value) is not type(default):
            raise ProjectError(f'{label}: {key} must be {type(default).__name__}')
        if type(value) is int and not -32768 <= value <= 32767:
            raise ProjectError(f'{label}: {key} exceeds the native signed-word range')
        if isinstance(value, str) and ('\0' in value or len(value) > 60000):
            raise ProjectError(f'{label}: invalid text in {key}')
    if node.kind == 'score' and p['owner'] == VARIABLE_OWNER:
        raise ProjectError('Owner -30000 is reserved for multi-scene authoring state')
    if node.kind in ('relationship', 'score') and p['operation'] not in ('set', 'add'):
        raise ProjectError(f'{label}: property operation must be set or add')
    if node.kind == 'relationship' and not node.character:
        raise ProjectError(f'{label}: choose a reusable character')
    if node.kind in ('random', 'word_game', 'football', 'grid', 'input', 'relationship', 'score') and not p['result'].strip():
        raise ProjectError(f'{label}: enter a result variable')
    if node.kind == 'random' and p['bound'] <= 0:
        raise ProjectError('Random upper bound must be positive')
    if node.kind in ('music', 'sound') and p['resource'] < 0:
        raise ProjectError('Audio resource IDs must be nonnegative')
    music = range(8201, 8210 if project.game == 'cod' else 8233)
    embedded = assets[p['resource']].data if node.kind in ('music', 'sound') and p['resource'] in assets else None
    if node.kind == 'music' and p['resource'] not in music and not (embedded and is_audio(embedded)):
        raise ProjectError('Choose a native music ID for the selected game, or an embedded MP3 or WAV')
    if node.kind == 'sound' and p['resource'] in music:
        raise ProjectError('This ID selects music; use a Music node')
    if node.kind == 'sound' and p['resource'] >= 25000 and not (embedded and is_audio(embedded)):
        raise ProjectError('Embed the sound effect (MP3 or WAV) before using an episode audio ID')
    for resource in ([node.asset] if node.kind in ('background', 'character_art') else
                     [node.portrait] if node.kind == 'dialogue' and not node.character and node.portrait is not None else []):
        if resource in assets and assets[resource].data is not None and not is_image(assets[resource].data):
            raise ProjectError(f'{label}: resource {resource} is audio, not an image')
    if node.kind == 'pan' and p['alignment'] not in (1, 2, 3):
        raise ProjectError('Pan alignment must be 1 (left), 2 (center) or 3 (right)')
    if node.kind in TEXT_KEY_KINDS:
        name = p[TEXT_KEY_KINDS[node.kind]]
        if not name.strip() or name.startswith('$') and not SHARED_KEY.fullmatch(name) or set(name) & set('{}'):
            raise ProjectError(f'{label}: name the stored text, for example answer, or $KEY (letters, digits, _) '
                               'to share it with other episodes')
    for expression in node_expressions(node):
        unknown = expressions.characters(expressions.parse(expression)[0]) - characters.keys()
        if unknown:
            raise ProjectError(f'{label}: unknown character {sorted(unknown)[0]} in an expression')
    if node.kind == 'flag':
        if not 0 <= p['bit'] <= 31:
            raise ProjectError(f'{label}: a property flag is bit 0 to 31')
        if not node.character and p['owner'] == VARIABLE_OWNER:
            raise ProjectError('Owner -30000 is reserved for multi-scene authoring state')
    if node.kind == 'speakers':
        for key in ('player', 'narrator'):
            if p[key] and p[key] not in characters:
                raise ProjectError(f'{label}: unknown {key} character {p[key]}')
    if node.kind in ('expression_default', 'character_art', 'character_name') and not node.character:
        raise ProjectError(f'{label}: choose a reusable character')
    if node.kind == 'expression_default' and node.expression < 0:
        raise ProjectError(f'{label}: choose expression 0 to 4')
    if node.kind == 'character_art' and node.asset not in assets:
        raise ProjectError(f'{label}: select an imported portrait image')
    if node.kind == 'character_name' and not node.text.strip():
        raise ProjectError(f'{label}: enter the new name')
    if node.kind == 'picker':
        looks = p['characters']
        if not 1 <= len(looks) <= 5 or any(not isinstance(value, str) or value not in characters for value in looks):
            raise ProjectError(f'{label}: choose one to five reusable characters whose portraits are the looks')
        if not p['result'].strip():
            raise ProjectError(f'{label}: enter a result variable')
    if node.kind in HD_KINDS:
        validate_hd_node(project, node, p, label, assets)
    if node.kind in SHS_ONLY_KINDS and project.game != 'shs':
        raise ProjectError(f'{label}: the CoD game has no {node.kind.replace("_", " ")} service')
    if node.kind == 'open_url' and not p['url'].strip():
        raise ProjectError(f'{label}: enter the link to open')
    if node.kind == 'append_text' and len(node.text) > 400:
        raise ProjectError(f'{label}: append at most 400 characters at a time')
    if node.kind == 'survey':
        answers, results = p['answers'], p['results']
        if not 1 <= len(answers) <= 32 or any(not isinstance(a, str) or not a.strip() for a in answers):
            raise ProjectError(f'{label}: a survey sends 1 to 32 answers, each a numeric expression')
        if len(results) > 32 or any(not isinstance(r, str) or not r.isidentifier() for r in results):
            raise ProjectError(f'{label}: survey results are at most 32 variable names')
    if node.kind == 'football':
        for key in ('home_result', 'away_result'):
            if p[key] and not p[key].isidentifier():
                raise ProjectError(f'{label}: {key} must be a variable name')
    if node.kind in ('word_game', 'football', 'grid'):
        minigames.validate(node.kind, p)
    if node.kind == 'grid':
        for key in ('left_character', 'right_character'):
            if p[key] and p[key] not in characters:
                raise ProjectError(f'{label}: unknown grid character')


def validate_hd_node(project, node, p, label, assets):
    if project.game != 'shs':
        raise ProjectError(f'{label}: Faceplace and the Decision Tree are SHS HD features; CoD has neither')
    kind = node.kind
    if kind == 'faceplace':
        if p['action'] not in FACEPLACE_ACTIONS:
            raise ProjectError(f'{label}: Faceplace action must be one of {", ".join(FACEPLACE_ACTIONS)}')
        if p['action'] == 'default_name' and (not SHARED_KEY.fullmatch(p['key']) or not node.text.strip()):
            raise ProjectError(f'{label}: a default name needs a $KEY and the name')
    if kind == 'faceplace_post' and (not node.text.strip() or node.expression < 0):
        raise ProjectError(f'{label}: a post needs text and expression 0 to 4')
    if kind == 'faceplace_link':
        if not node.text.strip():
            raise ProjectError(f'{label}: enter the text shown under the post')
        if node.asset is not None and (node.asset not in assets or assets[node.asset].data is not None
                                       and not is_image(assets[node.asset].data)):
            raise ProjectError(f'{label}: the photo must be an imported image')
    if kind == 'tree' and p['action'] not in TREE_ACTIONS:
        raise ProjectError(f'{label}: Decision Tree action must be one of {", ".join(TREE_ACTIONS)}')
    if kind == 'tree_node':
        if p['type'] not in TREE_EXITS:
            raise ProjectError(f'{label}: tree scene type must be 1202 to 1223')
        if p['condition'] and (p['condition'] not in TREE_CONDITIONS or p['type'] not in range(1219, 1224)):
            raise ProjectError(f"{label}: a condition is one of Football Star's native tests (75 to 104) "
                               'on a branch type 1219-1223')
        if p['condition'] and p['width']:
            raise ProjectError(f'{label}: a conditional branch has no width')
    if kind == 'tree_result' and not 0 <= p['index'] < 5:
        raise ProjectError(f'{label}: a result is 0 to 4')


def validate_tree_pairing(project, nodes):
    """Native `addNode` and `addResult` alternate: a scene of a waiting type takes exactly one result before the next scene,
    and a result only follows such a scene (SHSDTView prints assertions otherwise). Checked along every graph path."""
    def adds_scene(node):
        return node.kind == 'tree_node' or node.kind == 'tree' and parameters(node)['action'] == 'join'
    if not any(adds_scene(n) or n.kind == 'tree_result' for n in project.nodes):
        return
    seen, work = set(), [(project.start, None)]       # state: the waiting scene's result count, or None
    while work:
        key, waiting = work.pop()
        if (key, waiting) in seen or key not in nodes:
            continue
        seen.add((key, waiting))
        node = nodes[key]
        p, label = parameters(node), node.label or node.id
        if adds_scene(node):
            if waiting is not None:
                raise ProjectError(f'{label}: the tree scene before it still waits for a Tree result')
            waiting = TREE_EXITS[p['type']] if node.kind == 'tree_node' and p['type'] in TREE_AWAITING else None
        elif node.kind == 'tree_result':
            if waiting is None:
                raise ProjectError(f'{label}: a Tree result must follow a tree scene that waits for one (types 1209-1223)')
            if p['index'] >= waiting:
                raise ProjectError(f'{label}: result {p["index"]} does not exist; that scene has {waiting}')
            waiting = None
        work.extend((target, waiting) for _, target in node.links())


def validate(project: Project):
    validate_structure(project)
    if project.native:
        from .native import validate_native
        validate_native(project)
        return
    if not project.title.strip():
        raise ProjectError('Give the episode a title')
    nodes = {node.id: node for node in project.nodes}
    if project.start not in nodes:
        raise ProjectError('Choose a valid starting node')
    assets = {a.id: a for a in project.assets}
    characters = {c.id: c for c in project.characters}
    implicit = {(n.speaker, n.portrait, n.theme) for n in project.nodes
                if n.kind == 'dialogue' and not n.character and n.portrait is not None}
    if len(implicit) + len(characters) > 199:
        raise ProjectError('The native character table allows 199 portrait speakers plus the narrator')
    for c in project.characters:
        for resource in (c.portrait, *c.expressions):
            if resource is not None and resource not in assets:
                raise ProjectError(f'{c.name}: select an imported character image')
    for node in project.nodes:
        validate_node(project, node, nodes, assets, characters)
    validate_tree_pairing(project, nodes)
    both = text_keys(project) & set(variable_names(project))  # Also validates all expression syntax before writing.
    if both:
        raise ProjectError(f'{sorted(both)[0]} names both a stored text and a number; rename one of them')
    automatic = {n.id: n for n in project.nodes if n.kind not in INPUT_GATES | {'end'}}
    degrees = {key: 0 for key in automatic}
    for node in automatic.values():
        for _, target in node.links():
            if target in degrees: degrees[target] += 1
    ready, visited = [key for key, degree in degrees.items() if degree == 0], 0
    while ready:
        node = automatic[ready.pop()]
        visited += 1
        for _, target in node.links():
            if target in degrees:
                degrees[target] -= 1
                if degrees[target] == 0: ready.append(target)
    if visited != len(automatic):
        raise ProjectError('An automatic loop needs a dialogue, choice or other input gate')

class _Assembler:
    def __init__(self):
        self.words = bytearray()
        self.strings = {}
        self.code = []
        self.labels = {}
        self.text_buffer = None     # Append text's scratch text, allocated once per script on first use

    def text(self, value):
        if value not in self.strings:
            try:
                encoded = value.encode('latin-1') + b'\0'
            except UnicodeError as error:
                raise ProjectError('Story text must fit the native Latin-1 encoding; '
                                   'use straight quotes/dashes instead of curly punctuation or emoji') from error
            self.strings[value] = len(self.words) // 2
            self.words.extend(encoded + (b'\0' if len(encoded) % 2 else b''))
        return self.strings[value]

    def emit(self, op, arg=None):
        self.code.append((op, arg))

    def table(self, values):
        result = len(self.words) // 2
        for value in values:
            if type(value) is not int or not -32768 <= value <= 65535:
                raise ProjectError('Native table value exceeds a word')
            self.words.extend(struct.pack('>H', value & 65535))
        return result

    def call(self, service, *args):
        for arg in args:
            self.emit(0x1a, arg)
        self.emit(0x1f, service << 8 | len(args))

    def jump(self, target):
        self.emit(0x29, target)

    def jump_if(self, target):
        # Conditional instructions use relative PCs. Skip an absolute jump
        # on false, keeping long/backward graph edges independent of offsets.
        self.emit(0x2b, 2)
        self.jump(target)

    def finish(self):
        if len(self.words) // 2 >= 0x7000 or len(self.code) > 32767:
            raise ProjectError('Episode exceeds the native single-script memory/instruction limit; split the episode')
        code = bytearray()
        for op, arg in self.code:
            code.append(op)
            if arg is not None:
                value = self.labels[arg] if not isinstance(arg, int) else arg
                code.extend(struct.pack('>H', value & 65535))
        result = (b'kiwi\x02\x00\x00' + struct.pack('>4H', len(self.words) // 2, 0, 0, len(self.code))
                  + self.words + code)
        return decode_program(bytes(result)).to_bytes()


@dataclass
class Compilation:
    data: bytes
    locations: dict[int, dict[str, int]]
    variables: dict[str, int]
    shared_variables: bool
    characters: dict[str, int]


def _character_bank(project, resources):
    slots, definitions = {}, []
    assets = {asset.id: asset for asset in project.assets}
    for c in project.characters:
        portrait = c.portrait if c.portrait is not None else -1
        if c.expressions and any(value is not None for value in c.expressions):
            variants = [value if value is not None else c.portrait for value in c.expressions]
            if all(value == portrait + i for i, value in enumerate(variants)):
                pass  # A native base bank already provides the five consecutive slots.
            else:
                if any(value is None or assets[value].data is None for value in variants):
                    raise ProjectError(f'{c.name}: custom expression sets require embedded images in all five slots')
                portrait = next((base for base in range(26000, 32763, 5)
                                 if not set(range(base, base + 5)).intersection(set(resources) | set(assets))), None)
                if portrait is None: raise ProjectError('No space for the character expression bank')
                resources.update({portrait + i: assets[value].data for i, value in enumerate(variants)})
        number = len(definitions) + 1
        slots[c.id] = number
        definitions.append((number, translated(project, f'character.{c.id}.name', c.name), portrait, c.theme))
    for name, portrait, theme in sorted({(n.speaker, n.portrait, n.theme) for n in project.nodes
                                       if n.kind == 'dialogue' and not n.character and n.portrait is not None}):
        number = len(definitions) + 1
        slots[name, portrait, theme] = number
        definitions.append((number, name, portrait, theme))
    return slots, definitions


def compile_details(project: Project, *, language=None, start=None, include_project=True) -> Compilation:
    project = deepcopy(project)
    if language is not None: project.language = language
    if start is not None:
        if project.native: raise ProjectError('Imported native blocks retain their original entry point')
        project.start = start
    validate(project)
    if project.native:
        from .native import compile_native
        locations = {}
        for node in project.nodes:
            locations.setdefault(node.params['script'], {})[node.id] = node.params['pc']
        return Compilation(compile_native(project), locations, {}, False, {})
    variables = {name: i for i, name in enumerate(variable_names(project))}
    numeric = set(variables)
    slots = cycle(FORMAT_SLOTS)
    nodes = {node.id: node for node in project.nodes}
    scenes = sorted({node.scene for node in project.nodes})
    shared = len(scenes) > 1
    if len(scenes) > 998: raise ProjectError('At most 998 authored scenes are supported')
    scripts = {scene: 25002 + i for i, scene in enumerate(scenes)} if shared else {scenes[0]: 25001}
    ordinals = {node.id: i for i, node in enumerate(project.nodes)}
    resources = {asset.id: asset.data for asset in project.assets if asset.data is not None}
    characters, definitions = _character_bank(project, resources)
    locations = {}

    def initialize(asm):
        asm.call(75, 0); asm.call(74, 0); asm.call(72, 0, -1)
        for number, name, portrait, theme in definitions:
            asm.call(64, number, asm.text(name)); asm.call(72, number, portrait)
            asm.call(52, number, 651, theme)

    def route(asm, source_scene, target):
        target_node = nodes[target]
        if source_scene == target_node.scene:
            asm.jump(target)
        else:
            asm.call(52, VARIABLE_OWNER, -1, ordinals[target])
            asm.call(10, scripts[target_node.scene], 0)
            asm.emit(0x33)

    if shared:
        boot = _Assembler()
        initialize(boot)
        for address in variables.values(): boot.call(52, VARIABLE_OWNER, address, 0)
        route(boot, None, project.start)
        resources[25001] = boot.finish()
    for scene in scenes:
        asm = _Assembler()
        if not shared:
            asm.words.extend(b'\0\0' * len(variables))
            initialize(asm)
            asm.jump(project.start)
        else:
            for node in project.nodes:
                if node.scene == scene:
                    asm.call(53, VARIABLE_OWNER, -1); asm.emit(0x21)
                    asm.emit(0x1a, ordinals[node.id]); asm.emit(0x0a); asm.jump_if(node.id)
            asm.emit(0x33)  # Only the compiler's explicit scene-entry selectors can arrive here.
        script_id = scripts[scene]
        locations[script_id] = {}

        def read_variable(name):
            if shared:
                asm.call(53, VARIABLE_OWNER, variables[name]); asm.emit(0x21)
            else:
                asm.emit(0x40, variables[name])

        def store_variable(name):
            # Stack result -> A, then the destination and value in native order.
            asm.emit(0x03)
            if shared:
                asm.emit(0x1a, VARIABLE_OWNER); asm.emit(0x1a, variables[name]); asm.emit(0x07)
                asm.emit(0x1f, 52 << 8 | 3)
            else:
                asm.emit(0x1a, variables[name]); asm.emit(0x07); asm.emit(0x3e); asm.emit(0x15)

        def expression(value):
            expressions.emit(asm, expressions.parse(value)[0], read_variable, characters.__getitem__)

        def store_word(address):
            # Stack value -> data word `address`, as a single-scene variable is stored.
            asm.emit(0x03); asm.emit(0x1a, address); asm.emit(0x07); asm.emit(0x3e); asm.emit(0x15)

        def formatted(value):
            """A text reference. `{expression}` placeholders first format the text into a dynamic slot (service 0),
            whose handle is the reference; slots rotate so that one call's texts never share one."""
            spans = placeholders(value, numeric)
            if not spans:
                return asm.text(value)
            slot, pattern, values, position = next(slots), [], [], 0
            def literal(part):
                for piece in re.split('(%)', part):
                    if piece == '%':        # A literal percent sign would start a format: print it with %c.
                        pattern.append('%c'); values.append(ord('%'))
                    else:
                        pattern.append(piece)
            for match, tree in spans:
                literal(value[position:match.start()])
                pattern.append('%d'); values.append(tree)
                position = match.end()
            literal(value[position:])
            asm.emit(0x1a, 1 - slot); asm.emit(0x1a, asm.text(''.join(pattern)))
            for item in values:
                if isinstance(item, int): asm.emit(0x1a, item)
                else: expressions.emit(asm, item, read_variable, characters.__getitem__)
            if len(values) > 253: raise ProjectError('A text can format at most 253 values')
            asm.emit(0x1f, 0 << 8 | len(values) + 2)
            return 0x7ff5 + slot

        for node in project.nodes:
            if node.scene != scene: continue
            asm.labels[node.id] = locations[script_id][node.id] = len(asm.code)
            p = parameters(node)
            base = f'node.{node.id}.'
            def text(field, fallback=None, *, raw=False, plain=False):
                """The translated field; a reference unless raw. Minigame tables keep plain references, read later."""
                key = base + field if field in ('text', 'speaker') else base + 'param.' + field
                if fallback is None: fallback = getattr(node, field) if field in ('text', 'speaker') else p[field]
                value = translated(project, key, fallback)
                return value if raw else asm.text(value) if plain else formatted(value)
            def character(field='character'):
                key = node.character if field == 'character' else p[field]
                return characters[key] if key else 0
            kind = node.kind
            if kind == 'dialogue':
                if node.character or node.portrait is not None:
                    who = character() if node.character else characters[node.speaker, node.portrait, node.theme]
                    asm.call(13, text('text'), who, node.expression)
                elif node.speaker:
                    asm.call(76, text('speaker'), text('text'))
                elif NARRATOR in variables:
                    narration = text('text')    # The narrator's number is chosen at run time.
                    asm.emit(0x1a, narration); read_variable(NARRATOR); asm.emit(0x1a, 0); asm.emit(0x1f, 13 << 8 | 3)
                else:
                    asm.call(13, text('text'), 0, 0)
            elif kind == 'choice':
                asm.call(52, 0, 651, node.theme)
                asm.call(2, text('speaker'), text('text'), node.timeout_ms, node.timeout_option, character(), 0)
                for i, option in enumerate(node.options):
                    asm.emit(0x1a, formatted(translated(project, base + f'option.{i}', option.text)))
                    asm.emit(0x1a, i); expression(option.condition or '1'); asm.emit(0x1f, 3 << 8 | 3)
                asm.call(4, int(p['shuffle']))
                for i, option in enumerate(node.options):
                    asm.emit(0x21); asm.emit(0x1a, i); asm.emit(0x0a)
                    label = ('choice', node.id, i)
                    asm.jump_if(label)
                asm.emit(0x33)  # Preserve unexpected native outcomes; no invented answer.
                for i, option in enumerate(node.options):
                    asm.labels[('choice', node.id, i)] = len(asm.code)
                    route(asm, scene, option.target)
            elif kind == 'background':
                asm.call(11, p['variant'], node.asset)
            elif kind == 'set':
                expression(_node_expression(node)); store_variable(node.variable)
            elif kind in ('branch', 'text_branch'):
                if kind == 'text_branch':
                    asm.call(47, asm.text(text_key(p['variable'])), asm.text(''), -1)
                    asm.call(24, 0x7ff5, text('equals'))
                    asm.emit(0x21)
                elif p['expression']:
                    expression(p['expression'])
                else:
                    read_variable(node.variable); asm.emit(0x1a, node.value)
                    asm.emit({'==': 0x0a, '!=': 0x0b, '<': 0x0e, '<=': 0x0f, '>': 0x0c, '>=': 0x0d}[node.operator])
                yes = ('yes', node.id)
                asm.jump_if(yes); route(asm, scene, node.otherwise)
                asm.labels[yes] = len(asm.code); route(asm, scene, node.next)
            elif kind in ('music', 'sound', 'stop_audio'):
                if kind == 'music': asm.call(80, p['resource'], int(p['loop']))
                elif kind == 'sound': asm.call(79, p['resource'])
                else: asm.call(81, p['channel'])
            elif kind in ('relationship', 'score'):
                owner, key = (character(), 407) if kind == 'relationship' else (p['owner'], p['key'])
                asm.emit(0x1a, owner); asm.emit(0x1a, key)
                if p['operation'] == 'add':
                    asm.call(53, owner, key); asm.emit(0x21); asm.emit(0x1a, p['value']); asm.emit(0x50)
                else: asm.emit(0x1a, p['value'])
                asm.emit(0x1f, 52 << 8 | 3)
                if kind == 'relationship':
                    asm.call(52, owner, 629, int(p['hide']))
                    if p['romantic']: asm.call(54, 601, owner)
                elif p['notification']: asm.call(88, text('notification'))
                asm.call(53, owner, key); asm.emit(0x21); store_variable(p['result'])
            elif kind == 'input':
                asm.call(17, text('speaker'), text('prompt'), text('default'))
                asm.call(46, asm.text(text_key(p['result'])), 0x7ff5)
            elif kind == 'title': asm.call(8, text('text'), text('subtitle'), p['background'], p['flag'])
            elif kind == 'message': asm.call(33, text('title'), text('text'), p['flag'])
            elif kind == 'notice': asm.call(88, text('text'))
            elif kind == 'emphasis': asm.call(89)
            elif kind == 'scene_label': asm.call(90, p['icon'], text('text') if node.text else -1)
            elif kind == 'pan': asm.call(97, int(p['automatic']), p['alignment'])
            elif kind == 'transition': asm.call(16, p['selector'])
            elif kind == 'close_dialogue': asm.call(39)
            elif kind == 'random':
                asm.call(27, p['bound']); asm.emit(0x21); store_variable(p['result'])
            elif kind in ('word_game', 'football', 'grid'):
                localized = deepcopy(p)
                for field in ('good', 'bad', 'instructions'):
                    if field in localized:
                        localized[field] = [text(f'{field}.{i}', v, raw=True) for i, v in enumerate(p[field])]
                for field in ('problems', 'tutorials'):
                    for i, record in enumerate(localized.get(field, [])):
                        for key, value in list(record.items()):
                            if isinstance(value, str): record[key] = text(f'{field}.{i}.{key}', value, raw=True)
                            elif key == 'words':
                                record[key] = [text(f'{field}.{i}.words.{j}', word, raw=True)
                                               for j, word in enumerate(value)]
                minigames.validate(kind, localized)
                minigames.emit(asm, kind, p, lambda *args, **options: text(*args, plain=True, **options), character)
                asm.emit(0x21); store_variable(p['result'])
                if kind == 'football':
                    for selector, name in ((1, p['home_result']), (0, p['away_result'])):
                        if name: asm.call(95, selector); asm.emit(0x21); store_variable(name)
            elif kind == 'flag':
                asm.call(50, character() if node.character else p['owner'], p['key'], p['bit'], int(p['value']))
            elif kind == 'speakers':
                player, narrator = (characters[p[key]] if p[key] else 0 for key in ('player', 'narrator'))
                asm.call(74, player); asm.call(75, narrator)
                if NARRATOR in variables:
                    asm.emit(0x1a, narrator); store_variable(NARRATOR)
            elif kind in ('set_text', 'text_default'):
                key = asm.text(text_key(p['key']))
                if kind == 'set_text': asm.call(46, key, text('text'))
                else: asm.call(47, key, text('text'), -1)
            elif kind == 'expression_default': asm.call(5, character(), node.expression)
            elif kind == 'character_art': asm.call(72, character(), node.asset)
            elif kind == 'character_name': asm.call(49, character(), text('text'), int(p['capitalize']))
            elif kind == 'picker':
                looks = [characters[key] for key in p['characters']]
                asm.call(78, text('text'), len(looks), asm.table(looks))
                asm.emit(0x21); store_variable(p['result'])
                if node.character:
                    # The chosen look's portrait base becomes the character's (73, then 72), as the original stories do.
                    for i, look in enumerate(looks):
                        other = ('look', node.id, i)
                        read_variable(p['result']); asm.emit(0x1a, i); asm.emit(0x0b); asm.jump_if(other)
                        asm.emit(0x1a, character()); asm.call(73, look); asm.emit(0x21); asm.emit(0x1f, 72 << 8 | 2)
                        asm.labels[other] = len(asm.code)
            elif kind == 'vibrate': asm.call(82)
            elif kind == 'faceplace':
                if p['action'] == 'default_name': asm.call(113, asm.text(p['key']), text('text'))
                else: asm.call(FACEPLACE_ACTIONS[p['action']])
            elif kind == 'faceplace_post':
                asm.call(115, text('text'), character() if node.character else -1, node.expression)
            elif kind == 'faceplace_link':
                if node.asset is None: asm.call(116, text('text'), asm.text(p['url']))
                else: asm.call(117, node.asset, text('text'), asm.text(p['url']))
            elif kind == 'tree':
                asm.call(TREE_ACTIONS[p['action']], *([p['id']] if p['action'] == 'clear_accumulator' else []))
            elif kind == 'tree_node':
                if p['condition']:
                    empty = asm.text('')
                    asm.call(111, p['type'], p['condition'], empty, empty, text('text'))
                elif p['width']: asm.call(103, p['type'], text('text'), p['width'])
                else: asm.call(102, p['type'], text('text'))
            elif kind == 'append_text':
                if asm.text_buffer is None: asm.text_buffer = asm.table([0] * TEXT_BUFFER_WORDS)
                buffer, key = asm.text_buffer, asm.text(text_key(p['key']))
                asm.emit(0x1a, 0); store_word(buffer)                      # empty the scratch text
                asm.call(47, key, asm.text(''), -1)                        # the stored text, in slot 0
                asm.call(25, buffer, 0x7ff5); asm.call(25, buffer, text('text'))
                asm.call(46, key, buffer)
            elif kind == 'loading': asm.call(91, int(p['wait']))
            elif kind == 'open_url': asm.call(100, asm.text(p['url']), -1)
            elif kind == 'survey':
                # HD's getPollURL: pollID, upType 2 (an array of values), the values, upSize, resultsType 2, the results
                # buffer (finishPollDownload writes it through writeArrayToStack) and resultsSize. R is 1 when the
                # server's results came back, else 0.
                answers, results = asm.table([0] * len(p['answers'])), asm.table([0] * len(p['results']))
                for i, answer in enumerate(p['answers']):
                    expression(answer); store_word(answers + i)
                asm.call(9, p['poll_id'], 2, answers, len(p['answers']), 2, results, len(p['results']))
                uploaded = ('uploaded', node.id)
                asm.emit(0x21); asm.jump_if(uploaded)
                asm.call(65, 0, asm.text(SURVEY_FAILURE), -1)
                route(asm, scene, node.next)
                asm.labels[uploaded] = len(asm.code)
                for i, name in enumerate(p['results']):
                    asm.emit(0x40, results + i); store_variable(name)
            elif kind == 'tree_result':
                if node.text: asm.call(106, p['index'], text('text'))
                else: asm.call(107, p['index'])
            elif kind == 'end': asm.call(7); asm.emit(0x33)
            if kind not in ('choice', 'branch', 'text_branch', 'end'):
                route(asm, scene, node.next)
        resources[script_id] = asm.finish()
    titles = tuple(project.locales.get(language, {}).get('title', project.title) for language in ('en', 'fr', 'it', 'de', 'es'))
    resources[1] = Metadata(project.pack_id, project.episode_id, titles).to_bytes()
    record = project_record(project)
    record['library'] = ''  # Never distribute the author's private library path.
    for asset in record['assets']:
        if asset['data'] is not None: asset['data'] = '@resource'
    resources[AUTHORING_RESOURCE] = AUTHORING_MAGIC + json.dumps(dict(
        format='exp-runtime-authored', version=1, project=record if include_project else None,
        locations=locations, variables=variables, shared_variables=shared,
        characters={key: value for key, value in characters.items() if isinstance(key, str)}),
        ensure_ascii=True, separators=(',', ':')).encode()
    return Compilation(encode_exp(resources), locations, variables, shared,
                       {key: value for key, value in characters.items() if isinstance(key, str)})


def compile_project(project: Project, *, language=None, start=None) -> bytes:
    return compile_details(project, language=language, start=start).data


def export_project(project: Project, path, *, language=None):
    atomic_write(path, compile_project(project, language=language))


def export_native_slot(project: Project, reference: Path, destination: Path):
    reference, destination = Path(reference), Path(destination)
    if reference.resolve() == destination.resolve():
        raise ProjectError('Export a separate replacement file; keep the original episode as a backup')
    archive = ExpArchive(reference.read_bytes())
    metadata = archive.metadata()
    if 25001 not in archive.programs():
        raise ProjectError('The reference episode has no native entry script at resource 25001')
    replacement = replace(project, pack_id=metadata.pack_id, episode_id=metadata.episode_id)
    export_project(replacement, destination)
    return metadata
