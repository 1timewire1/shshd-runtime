"""Compile story graphs into native KiWi, with exact source locations for tools."""
from copy import deepcopy
from dataclasses import dataclass, replace
import json
from pathlib import Path
import struct

from exp_runtime.exp import ExpArchive, Metadata, encode_exp
from exp_runtime.authored import RESOURCE as AUTHORING_RESOURCE, MAGIC as AUTHORING_MAGIC
from exp_runtime.decode.bytecode import decode_program
from .model import Project, ProjectError, atomic_write, project_record, validate_structure
from .features import DEFAULTS, INPUT_GATES, parameters, translated
from . import expressions, minigames

VARIABLE_OWNER = -30000


def _node_expression(node):
    p = parameters(node)
    if node.kind == 'set':
        return p['expression'] or str(node.value)
    if node.kind == 'branch':
        return p['expression'] or None
    return None


def variable_names(project):
    names = {n.variable for n in project.nodes if n.kind in ('set', 'branch') and n.variable}
    for node in project.nodes:
        p = parameters(node)
        if node.kind in ('random', 'word_game', 'football', 'grid', 'relationship', 'score'):
            names.add(p['result'])
        for expression in ([_node_expression(node)] + [o.condition for o in node.options]):
            if expression:
                names.update(expressions.parse(expression)[1])
    return sorted(names)


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
    if node.kind == 'music' and p['resource'] not in range(8201, 8210 if project.game == 'cod' else 8233):
        raise ProjectError('Choose a native music ID for the selected game')
    if node.kind == 'sound' and p['resource'] in range(8201, 8210 if project.game == 'cod' else 8233):
        raise ProjectError('This ID selects music; use a Music node')
    if node.kind == 'pan' and p['alignment'] not in (1, 2, 3):
        raise ProjectError('Pan alignment must be 1 (left), 2 (center) or 3 (right)')
    if node.kind in ('word_game', 'football', 'grid'):
        minigames.validate(node.kind, p)
    if node.kind == 'grid':
        for key in ('left_character', 'right_character'):
            if p[key] and p[key] not in characters:
                raise ProjectError(f'{label}: unknown grid character')


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
    variable_names(project)  # Validate all expression syntax before writing.
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
            expressions.emit(asm, expressions.parse(value)[0], read_variable)

        for node in project.nodes:
            if node.scene != scene: continue
            asm.labels[node.id] = locations[script_id][node.id] = len(asm.code)
            p = parameters(node)
            base = f'node.{node.id}.'
            def text(field, fallback=None, *, raw=False):
                key = base + field if field in ('text', 'speaker') else base + 'param.' + field
                if fallback is None: fallback = getattr(node, field) if field in ('text', 'speaker') else p[field]
                value = translated(project, key, fallback)
                return value if raw else asm.text(value)
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
                else:
                    asm.call(13, text('text'), 0, 0)
            elif kind == 'choice':
                asm.call(52, 0, 651, node.theme)
                asm.call(2, text('speaker'), text('text'), node.timeout_ms, node.timeout_option, character(), 0)
                for i, option in enumerate(node.options):
                    asm.emit(0x1a, asm.text(translated(project, base + f'option.{i}', option.text)))
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
                    asm.call(47, asm.text('{' + p['variable'] + '}'), asm.text(''), -1)
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
                asm.call(46, asm.text('{' + p['result'] + '}'), 0x7ff5)
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
                minigames.emit(asm, kind, p, text, character)
                asm.emit(0x21); store_variable(p['result'])
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
