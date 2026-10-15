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
VERSION = 1
MAX_PROJECT_BYTES = 96 * 1024 * 1024
MAX_ASSET_BYTES = 64 * 1024 * 1024
KINDS = ('dialogue', 'choice', 'background', 'set', 'branch', 'end')
OPERATORS = ('==', '!=', '<', '<=', '>', '>=')


class ProjectError(ContentError):
    pass


@dataclass
class Choice:
    text: str = 'Choice'
    target: str = ''


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

    def links(self):
        if self.kind == 'end':
            return []
        if self.kind == 'choice':
            return [(option.text, option.target) for option in self.options]
        if self.kind == 'branch':
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
    if not isinstance(project.nodes, list) or not 1 <= len(project.nodes) <= 2000:
        raise ProjectError('A project needs between 1 and 2000 nodes')
    ids = set()
    for node in project.nodes:
        if not isinstance(node, Node) or node.kind not in KINDS:
            raise ProjectError('Unknown node type')
        for name in ('id', 'label', 'speaker', 'next', 'otherwise', 'variable'):
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
        if node.operator not in OPERATORS:
            raise ProjectError('Unknown comparison operator')
        if not isinstance(node.options, list) or len(node.options) > 8:
            raise ProjectError('A choice can have at most eight answers')
        for option in node.options:
            if not isinstance(option, Choice):
                raise ProjectError('Invalid choice option')
            _string(option.text, 'option text', 2000)
            _string(option.target, 'option target', 200)
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
            if asset.id < 26000 or not isinstance(asset.data, bytes):
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


def save_project(project: Project, path: Path):
    validate_structure(project)
    data = asdict(project)
    for asset, record in zip(project.assets, data['assets']):
        record['data'] = base64.b64encode(asset.data).decode('ascii') if asset.data is not None else None
    if project.library:
        try:
            data['library'] = Path(os.path.relpath(Path(project.library).resolve(), Path(path).resolve().parent)).as_posix()
        except ValueError:  # Separate Windows volumes.
            data['library'] = str(Path(project.library).resolve())
    encoded = (json.dumps(dict(format=FORMAT, version=VERSION, **data), indent=2,
                          ensure_ascii=False) + '\n').encode('utf-8')
    if len(encoded) > MAX_PROJECT_BYTES:
        raise ProjectError('Project file exceeds 96 MiB')
    atomic_write(path, encoded)


def _construct(kind, data):
    if not isinstance(data, dict) or set(data) != {f.name for f in fields(kind)}:
        raise ProjectError(f'Invalid {kind.__name__} fields')
    return kind(**data)


def load_project(path: Path) -> Project:
    path = Path(path)
    if path.stat().st_size > MAX_PROJECT_BYTES:
        raise ProjectError('Project file exceeds 96 MiB')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or data.pop('format', None) != FORMAT
                or type(data.get('version')) is not int or data.pop('version') != VERSION):
            raise ProjectError('Unsupported episode project format or version')
        nodes = []
        for record in data['nodes']:
            node = _construct(Node, record)
            node.options = [_construct(Choice, option) for option in node.options]
            nodes.append(node)
        data['nodes'] = nodes
        assets = []
        for record in data['assets']:
            asset = _construct(Asset, record)
            if asset.data is not None:
                asset.data = base64.b64decode(asset.data, validate=True)
            assets.append(asset)
        data['assets'] = assets
        project = _construct(Project, data)
        validate_structure(project)
        if project.library:
            project.library = str((path.resolve().parent / project.library).resolve())
        return project
    except (KeyError, TypeError, ValueError, UnicodeError, binascii.Error, RecursionError) as error:
        raise ProjectError(f'Cannot read episode project: {error}') from error
