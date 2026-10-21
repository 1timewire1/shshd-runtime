"""Portable, versioned authoring documents, separate from executable EXP files."""
from dataclasses import asdict, dataclass, field, fields
import base64
import binascii
import json
import math
import os
from pathlib import Path
import tempfile

from exp_runtime.exp import ContentError

FORMAT = 'exp-runtime-project'
VERSION = 2
MAX_PROJECT_BYTES = 96 * 1024 * 1024
MAX_ASSET_BYTES = 64 * 1024 * 1024
KINDS = ('dialogue', 'choice', 'background', 'set', 'branch', 'music', 'sound', 'stop_audio',
         'relationship', 'score', 'input', 'text_branch', 'title', 'message', 'notice',
         'emphasis', 'scene_label', 'pan', 'transition', 'close_dialogue', 'random',
         'word_game', 'football', 'grid', 'scene', 'end', 'native')
OPERATORS = ('==', '!=', '<', '<=', '>', '>=')


class ProjectError(ContentError):
    pass


@dataclass
class Choice:
    text: str = 'Choice'
    target: str = ''
    condition: str = ''


@dataclass
class Node:
    id: str
    kind: str = 'dialogue'
    label: str = ''
    x: float = 0
    y: float = 0
    text: str = ''
    speaker: str = ''
    portrait: int | None = None
    theme: int = 2
    next: str = ''
    options: list[Choice] = field(default_factory=list)
    timeout_ms: int = 0
    timeout_option: int = 0
    asset: int | None = None
    variable: str = ''
    value: int = 0
    operator: str = '=='
    otherwise: str = ''
    scene: int = 25001
    character: str = ''
    expression: int = 0
    params: dict = field(default_factory=dict)

    def links(self):
        if self.kind == 'native':
            from exp_runtime.decode.bytecode import BytecodeInstruction
            rows = self.params.get('instructions', [])
            if not rows: return []
            try:
                pc = self.params['pc'] + len(rows) - 1
                ins = BytecodeInstruction(pc, 0, *rows[-1])
                targets = []
                if ins.branch_target() is not None: targets.append(ins.branch_target())
                if ins.opcode not in (0x29, 0x33, 0x43): targets.append(pc + 1)
                return [('Native', f'{self.params["script"]}:{target}') for target in dict.fromkeys(targets)]
            except (KeyError, TypeError, ValueError):
                return []
        if self.kind == 'end':
            return []
        if self.kind == 'choice':
            return [(option.text, option.target) for option in self.options]
        if self.kind in ('branch', 'text_branch'):
            return [('Yes', self.next), ('No', self.otherwise)]
        return [('Next', self.next)]


@dataclass
class Asset:
    id: int
    name: str
    # None is an exact reference into the selected game's original base bank.
    # Embedded assets are owned by this document, never by an external path.
    data: bytes | None = None


@dataclass
class Character:
    id: str
    name: str = 'Character'
    portrait: int | None = None
    theme: int = 2
    expressions: list[int | None] = field(default_factory=list)


@dataclass
class Project:
    title: str = 'Untitled episode'
    game: str = 'shs'
    pack_id: int = 30000
    episode_id: int = 1
    start: str = 'start'
    nodes: list[Node] = field(default_factory=lambda: [
        Node('start', label='Opening', text='Your story begins here.', next='end', x=40, y=80),
        Node('end', 'end', label='The end', x=360, y=80),
    ])
    assets: list[Asset] = field(default_factory=list)
    library: str = ''
    characters: list[Character] = field(default_factory=list)
    locales: dict[str, dict[str, str]] = field(default_factory=dict)
    language: str = 'en'
    native: dict = field(default_factory=dict)

    def node(self, node_id):
        return next(node for node in self.nodes if node.id == node_id)

    def add_image(self, name: str, data: bytes) -> Asset:
        if not data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8')):
            raise ProjectError('Choose a PNG or JPEG image')
        if len(data) > MAX_ASSET_BYTES:
            raise ProjectError('Image exceeds the EXP resource size limit')
        # Reserve five IDs per imported image. Service 72 probes base+1..4
        # for expressions; unrelated images must not become expressions.
        used = {asset.id for asset in self.assets}
        resource = next((i for i in range(26000, 32763, 5)
                         if not used.intersection(range(i, i + 5))), None)
        if resource is None:
            raise ProjectError('No free episode image IDs remain')
        asset = Asset(resource, name, data)
        self.assets.append(asset)
        return asset


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ProjectError(f'{label} must be an integer between {low} and {high}')


def _string(value, label, limit=60000):
    if not isinstance(value, str) or len(value) > limit or '\0' in value:
        raise ProjectError(f'Invalid {label}')
    try:
        value.encode('utf-8')
    except UnicodeError as error:
        raise ProjectError(f'Invalid Unicode in {label}') from error


def validate_structure(project: Project):
    """Check data types and sizes, while allowing unfinished stories to save."""
    _string(project.title, 'episode title', 1000)
    _string(project.start, 'start node ID', 100)
    _string(project.library, 'library location', 4096)
    if project.game not in ('shs', 'cod'):
        raise ProjectError('Choose the SHS or CoD game profile')
    _integer(project.pack_id, 0, 32767, 'Pack ID')
    _integer(project.episode_id, 1, 32767, 'Episode ID')
    if not isinstance(project.nodes, list) or not 1 <= len(project.nodes) <= 20000:
        raise ProjectError('A project needs between 1 and 20000 nodes')
    ids = set()
    for node in project.nodes:
        if not isinstance(node, Node) or node.kind not in KINDS:
            raise ProjectError('Unknown node type')
        for name in ('id', 'label', 'speaker', 'next', 'otherwise', 'variable', 'character'):
            _string(getattr(node, name), name, 200)
        _string(node.text, 'node text')
        if not node.id or node.id in ids:
            raise ProjectError(f'Duplicate or empty node ID: {node.id}')
        ids.add(node.id)
        for coord in (node.x, node.y):
            if type(coord) not in (float, int) or not math.isfinite(coord) or abs(coord) > 100000:
                raise ProjectError('Invalid node position')
        for resource in (node.portrait, node.asset):
            if resource is not None:
                _integer(resource, 0, 32767, 'Image resource ID')
        _integer(node.theme, 0, 3, 'Portrait theme')
        _integer(node.timeout_ms, 0, 32767, 'Choice timer (milliseconds)')
        _integer(node.timeout_option, 0, 7, 'Timeout option')
        _integer(node.value, -32768, 32767, 'Variable value')
        _integer(node.scene, 25001, 25999, 'Scene script ID')
        _integer(node.expression, 0, 4, 'Expression slot')
        if not isinstance(node.params, dict):
            raise ProjectError('Node parameters must be an object')
        try:
            if len(json.dumps(node.params, allow_nan=False)) > MAX_PROJECT_BYTES:
                raise ValueError('Parameters exceed the project size limit')
        except (TypeError, ValueError, RecursionError) as error:
            raise ProjectError(f'Invalid node parameters: {error}') from error
        if node.operator not in OPERATORS:
            raise ProjectError('Unknown comparison operator')
        if not isinstance(node.options, list) or len(node.options) > 8:
            raise ProjectError('A choice can have at most eight answers')
        for option in node.options:
            if not isinstance(option, Choice):
                raise ProjectError('Invalid choice option')
            _string(option.text, 'option text', 2000)
            _string(option.target, 'option target', 200)
            _string(option.condition, 'option condition', 2000)
    if not isinstance(project.characters, list) or len(project.characters) > 199:
        raise ProjectError('At most 199 reusable characters are supported')
    character_ids = set()
    for character in project.characters:
        if not isinstance(character, Character):
            raise ProjectError('Invalid character definition')
        _string(character.id, 'character ID', 100)
        _string(character.name, 'character name', 200)
        if not character.id or character.id in character_ids:
            raise ProjectError('Character IDs must be nonempty and unique')
        character_ids.add(character.id)
        _integer(character.theme, 0, 3, 'Character color')
        if not isinstance(character.expressions, list) or len(character.expressions) not in (0, 5):
            raise ProjectError('Character expressions need exactly five slots')
        for resource in (character.portrait, *character.expressions):
            if resource is not None:
                _integer(resource, 0, 32767, 'Character image')
    if project.language not in ('en', 'fr', 'it', 'de', 'es'):
        raise ProjectError('Choose en, fr, it, de or es as the export language')
    if not isinstance(project.locales, dict) or set(project.locales) - {'en', 'fr', 'it', 'de', 'es'}:
        raise ProjectError('Invalid translation languages')
    for language, translations in project.locales.items():
        if not isinstance(translations, dict):
            raise ProjectError('Translations must map field keys to text')
        for key, value in translations.items():
            _string(key, 'translation key', 300)
            _string(value, 'translated text')
    if not isinstance(project.native, dict):
        raise ProjectError('Invalid native archive data')
    if not isinstance(project.assets, list) or len(project.assets) > 2000:
        raise ProjectError('Too many image assets')
    ids, size = set(), 0
    for asset in project.assets:
        if not isinstance(asset, Asset):
            raise ProjectError('Invalid asset')
        _integer(asset.id, 0, 32767, 'Asset ID')
        _string(asset.name, 'asset name', 1000)
        if asset.id in ids:
            raise ProjectError(f'Duplicate asset ID: {asset.id}')
        ids.add(asset.id)
        if asset.data is None:
            if asset.id >= 25000:
                raise ProjectError('Only base-bank images may be external references')
        else:
            if (asset.id < 26000 and not project.native) or not isinstance(asset.data, bytes):
                raise ProjectError('Embedded images must use episode IDs starting at 26000')
            size += len(asset.data)
            if len(asset.data) > MAX_ASSET_BYTES or size > MAX_ASSET_BYTES:
                raise ProjectError('Embedded images exceed 64 MiB')


def atomic_write(path: Path, data: bytes):
    """Replace only after the complete file has reached disk."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name,
                                         suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def project_record(project: Project):
    validate_structure(project)
    data = asdict(project)
    for asset, record in zip(project.assets, data['assets']):
        record['data'] = base64.b64encode(asset.data).decode('ascii') if asset.data is not None else None
    return dict(format=FORMAT, version=VERSION, **data)


def project_bytes(project: Project, path: Path) -> bytes:
    data = project_record(project)
    if project.library:
        try:
            data['library'] = Path(os.path.relpath(Path(project.library).resolve(), Path(path).resolve().parent)).as_posix()
        except ValueError:  # Separate Windows volumes.
            data['library'] = str(Path(project.library).resolve())
    encoded = (json.dumps(data, indent=2,
                          ensure_ascii=False) + '\n').encode('utf-8')
    if len(encoded) > MAX_PROJECT_BYTES:
        raise ProjectError('Project file exceeds 96 MiB')
    return encoded


def save_project(project: Project, path: Path):
    atomic_write(path, project_bytes(project, path))


def _construct(kind, data):
    if not isinstance(data, dict) or set(data) != {f.name for f in fields(kind)}:
        raise ProjectError(f'Invalid {kind.__name__} fields')
    return kind(**data)


def _upgrade_episode_links(nodes):
    """Retire the unreleased link extension, preserving its optional message."""
    ids = {node.id for node in nodes}
    endings = []
    for node in nodes:
        if node.kind != 'episode_link': continue
        if not isinstance(node.params, dict): raise ProjectError('Node parameters must be an object')
        title = node.params.get('title', 'Next episode')
        node.kind, node.params = 'end', {}
        if node.text:
            base = node.id[:180] + '_end'
            target, suffix = base, 1
            while target in ids:
                target, suffix = f'{base}_{suffix}', suffix + 1
            ids.add(target)
            endings.append(Node(target, 'end', label='End episode', scene=node.scene,
                                x=min(100000, node.x + 320), y=node.y))
            node.kind, node.params, node.next = 'message', {'title': title}, target
    nodes.extend(endings)


def project_from_record(data):
    from copy import deepcopy
    data = deepcopy(data)
    try:
        if (not isinstance(data, dict) or data.pop('format', None) != FORMAT
                or type(data.get('version')) is not int or data['version'] not in (1, VERSION)):
            raise ProjectError('Unsupported episode project format or version')
        version = data.pop('version')
        if version == 1:
            data.update(characters=[], locales={}, language='en', native={})
            for node in data['nodes']:
                node.update(scene=25001, character='', expression=0, params={})
                for option in node['options']:
                    option['condition'] = ''
        nodes = []
        for record in data['nodes']:
            node = _construct(Node, record)
            node.options = [_construct(Choice, option) for option in node.options]
            nodes.append(node)
        _upgrade_episode_links(nodes)
        data['nodes'] = nodes
        data['characters'] = [_construct(Character, c) for c in data['characters']]
        assets = []
        for record in data['assets']:
            asset = _construct(Asset, record)
            if asset.data is not None:
                asset.data = base64.b64decode(asset.data, validate=True)
            assets.append(asset)
        data['assets'] = assets
        project = _construct(Project, data)
        validate_structure(project)
        return project
    except (KeyError, TypeError, ValueError, UnicodeError, binascii.Error, RecursionError) as error:
        raise ProjectError(f'Cannot read episode project: {error}') from error


def project_from_bytes(data: bytes, path: Path) -> Project:
    path = Path(path)
    if len(data) > MAX_PROJECT_BYTES:
        raise ProjectError('Project file exceeds 96 MiB')
    try:
        project = project_from_record(json.loads(data.decode('utf-8')))
        if project.library:
            project.library = str((path.resolve().parent / project.library).resolve())
        return project
    except (KeyError, TypeError, ValueError, UnicodeError, binascii.Error, RecursionError) as error:
        raise ProjectError(f'Cannot read episode project: {error}') from error


def load_project(path: Path) -> Project:
    path = Path(path)
    if path.stat().st_size > MAX_PROJECT_BYTES:
        raise ProjectError('Project file exceeds 96 MiB')
    return project_from_bytes(path.read_bytes(), path)
