"""Compile the supported authoring graph into native KiWi v2 and CSPUD."""
from dataclasses import replace
from pathlib import Path
import struct

from exp_runtime.exp import ExpArchive, Metadata, encode_exp
from exp_runtime.decode.bytecode import decode_program
from .model import Project, ProjectError, atomic_write, validate_structure


def validate(project: Project):
    validate_structure(project)
    if not project.title.strip():
        raise ProjectError('Give the episode a title')
    nodes = {node.id: node for node in project.nodes}
    if project.start not in nodes:
        raise ProjectError('Choose a valid starting node')
    assets = {asset.id for asset in project.assets}
    characters = {(n.speaker, n.portrait, n.theme) for n in project.nodes
                  if n.kind == 'dialogue' and n.portrait is not None}
    if len(characters) > 199:
        raise ProjectError('The native character table allows 199 portrait speakers plus the narrator')
    for node in project.nodes:
        label = node.label or node.id
        for _, target in node.links():
            if target not in nodes:
                raise ProjectError(f'{label}: choose a destination for every connection')
        if node.kind == 'choice':
            if not 2 <= len(node.options) <= 8 or any(not o.text.strip() for o in node.options):
                raise ProjectError(f'{label}: provide two to eight nonempty choices')
            if node.timeout_option >= len(node.options):
                raise ProjectError(f'{label}: select an existing answer for timer expiry')
        if node.kind in ('dialogue', 'choice') and not node.text.strip():
            raise ProjectError(f'{label}: enter dialogue or a choice prompt')
        if node.kind in ('set', 'branch') and not node.variable.strip():
            raise ProjectError(f'{label}: enter a variable name')
        if node.kind == 'background' and node.asset not in assets:
            raise ProjectError(f'{label}: select an imported background image')
        if node.kind == 'dialogue' and node.portrait is not None:
            if node.portrait not in assets or not node.speaker.strip():
                raise ProjectError(f'{label}: a portrait needs an imported image and a speaker name')
    # A cycle without an input gate never yields to the player. Check the
    # automatic subgraph, including unreachable nodes, without recursion.
    automatic = {n.id: n for n in project.nodes if n.kind in ('set', 'branch', 'background')}
    degrees = {key: 0 for key in automatic}
    for node in automatic.values():
        for _, target in node.links():
            if target in degrees:
                degrees[target] += 1
    ready = [key for key, degree in degrees.items() if degree == 0]
    visited = 0
    while ready:
        node = automatic[ready.pop()]
        visited += 1
        for _, target in node.links():
            if target in degrees:
                degrees[target] -= 1
                if degrees[target] == 0:
                    ready.append(target)
    if visited != len(automatic):
        raise ProjectError('A background/variable/condition loop needs a dialogue or choice to wait for input')


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
                value = self.labels[arg] if isinstance(arg, str) else arg
                code.extend(struct.pack('>H', value & 65535))
        result = (b'kiwi\x02\x00\x00' + struct.pack('>4H', len(self.words) // 2, 0, 0, len(self.code))
                  + self.words + code)
        return decode_program(bytes(result)).to_bytes()


def compile_project(project: Project) -> bytes:
    """Return an importable EXP without opening the project's asset library."""
    validate(project)
    asm = _Assembler()
    # Initialized VM data words keep authored variables separate from the
    # original apps' global entity/property tables and saved game properties.
    variables = {name: i for i, name in enumerate(sorted(
        {n.variable for n in project.nodes if n.kind in ('set', 'branch')}))}
    asm.words.extend(b'\0\0' * len(variables))
    characters = {key: i + 1 for i, key in enumerate(sorted(
        {(n.speaker, n.portrait, n.theme) for n in project.nodes
         if n.kind == 'dialogue' and n.portrait is not None}))}
    # Native getPersistedExpression indexes a fixed 200-byte array without
    # checking negative IDs. Give narration a valid slot and explicit role.
    asm.call(75, 0)
    asm.call(74, 0)
    asm.call(72, 0, -1)
    for (speaker, portrait, theme), character in characters.items():
        asm.call(64, character, asm.text(speaker))
        asm.call(72, character, portrait)
        asm.call(52, character, 651, theme)
    asm.jump(project.start)
    for node in project.nodes:
        asm.labels[node.id] = len(asm.code)
        if node.kind == 'dialogue':
            if node.portrait is not None:
                asm.call(13, asm.text(node.text), characters[node.speaker, node.portrait, node.theme], 0)
            elif node.speaker:
                asm.call(76, asm.text(node.speaker), asm.text(node.text))
            else:
                asm.call(13, asm.text(node.text), 0, 0)
        elif node.kind == 'choice':
            asm.call(52, 0, 651, node.theme)
            asm.call(2, asm.text(node.speaker), asm.text(node.text), node.timeout_ms,
                     node.timeout_option, 0, 0)
            for i, option in enumerate(node.options):
                asm.call(3, asm.text(option.text), i, 1)
            asm.call(4, 0)
            for i, option in enumerate(node.options[:-1]):
                asm.emit(0x21)
                asm.emit(0x1a, i)
                asm.emit(0x0a)
                asm.jump_if(option.target)
            asm.jump(node.options[-1].target)
        elif node.kind == 'background':
            asm.call(11, 0, node.asset)
        elif node.kind == 'set':
            asm.emit(0x1a, variables[node.variable])
            asm.emit(0x1a, node.value)
            asm.emit(0x3e)  # STORE_KEEP: store to initialized script memory.
            asm.emit(0x15)  # Discard the retained value, keeping SP balanced.
        elif node.kind == 'branch':
            asm.emit(0x40, variables[node.variable])
            asm.emit(0x1a, node.value)
            asm.emit({'==': 0x0a, '!=': 0x0b, '<': 0x0e, '<=': 0x0f, '>': 0x0c, '>=': 0x0d}[node.operator])
            asm.jump_if(node.next)
            asm.jump(node.otherwise)
        else:
            asm.call(7)
            asm.emit(0x33)
        if node.kind not in ('choice', 'branch', 'end'):
            asm.jump(node.next)
    resources = {1: Metadata(project.pack_id, project.episode_id, (project.title,) * 5).to_bytes(),
                 25001: asm.finish()}
    resources.update({asset.id: asset.data for asset in project.assets if asset.data is not None})
    return encode_exp(resources)


def export_project(project: Project, path):
    atomic_write(path, compile_project(project))


def export_native_slot(project: Project, reference: Path, destination: Path):
    """Export for an existing native catalog slot without touching that slot.

    The original apps select episodes through their own catalogs. Preserve the
    reference episode's numeric identity in a separate replacement file. The
    caller installs it manually under the original catalog filename and starts
    a new game; this does not edit a native catalog or convert a native save.
    """
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
