"""Round-trip authored graphs or edit lossless native basic blocks.

Original bytecode is never guessed into dialogue or flattened past unknown
services. Fixed instruction counts preserve every native PC and callback.
"""
import base64
from dataclasses import replace

from exp_runtime.authored import authoring_record
from exp_runtime.exp import ExpArchive, Metadata, encode_exp
from exp_runtime.decode.bytecode import OPERAND_OPCODES, decode_program
from .model import Asset, Node, Project, ProjectError, project_from_record, validate_structure


def _resources(project):
    try:
        return {int(key): base64.b64decode(value, validate=True)
                for key, value in project.native['resources'].items()}
    except (KeyError, TypeError, ValueError) as error:
        raise ProjectError('Invalid native resource bank') from error


def import_exp(data, *, game='shs'):
    archive = ExpArchive(data)
    record = authoring_record(archive)
    if record and record.get('project'):
        document = record['project']
        for asset in document.get('assets', []):
            if asset.get('data') == '@resource':
                asset['data'] = base64.b64encode(archive.read(asset['id'])).decode('ascii')
        project = project_from_record(document)
        project.library = ''
        return project
    meta = archive.metadata()
    resources = {key: archive.read(key) for key in archive.entries}
    project = Project(title=meta.title, game=game, pack_id=meta.pack_id, episode_id=meta.episode_id,
                      nodes=[], native={'resources': {str(key): base64.b64encode(value).decode('ascii')
                                                     for key, value in resources.items()}})
    project.locales = {language: {'title': title} for language, title in
                      zip(('en', 'fr', 'it', 'de', 'es'), meta.titles)}
    for script, program in sorted(archive.programs().items()):
        instructions = program.instructions
        if not instructions:
            continue
        boundaries = {instructions[0].pc}
        pcs = {ins.pc for ins in instructions}
        for ins in instructions:
            target = ins.branch_target()
            if target in pcs:
                boundaries.add(target)
            if target is not None or ins.opcode in (0x1e, 0x1f, 0x33, 0x43):
                if ins.pc + 1 in pcs:
                    boundaries.add(ins.pc + 1)
        starts = sorted(boundaries)
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else instructions[-1].pc + 1
            base = instructions[0].pc
            block = instructions[start - base:end - base]
            last = block[-1]
            targets = []
            if last.branch_target() in pcs:
                targets.append(last.branch_target())
            if last.opcode not in (0x29, 0x33, 0x43) and end in pcs:
                targets.append(end)
            node = Node(f'{script}:{start}', 'native', f'Script {script} · PC {start}',
                        x=index % 6 * 290, y=(index // 6 + len(project.nodes) // 6) * 160,
                        scene=script, params={'script': script, 'pc': start,
                        'instructions': [[ins.opcode, ins.operand] for ins in block],
                        'edges': [f'{script}:{pc}' for pc in dict.fromkeys(targets)]})
            project.nodes.append(node)
    if not project.nodes:
        raise ProjectError('EXP has no editable KiWi programs')
    project.start = next((n.id for n in project.nodes if n.scene == 25001), project.nodes[0].id)
    project.assets = [Asset(key, f'Resource {key}', value) for key, value in resources.items()
                      if value.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8'))]
    from .editing import auto_layout
    auto_layout(project)
    validate_structure(project)
    return project


def compile_native(project):
    resources = _resources(project)
    programs = {key: decode_program(value) for key, value in resources.items() if value.startswith(b'kiwi')}
    originals = {key: {ins.pc: ins for ins in program.instructions} for key, program in programs.items()}
    edits = {key: {} for key in programs}
    for node in project.nodes:
        if node.kind != 'native':
            raise ProjectError('Native projects require native blocks; create a new project for high-level nodes')
        p = node.params
        try:
            script, start, rows = p['script'], p['pc'], p['instructions']
            if type(start) is not int or type(script) is not int or not isinstance(rows, list) or not rows:
                raise ValueError('invalid block')
            original = originals[script]
            for index, row in enumerate(rows):
                pc = start + index
                op, arg = row
                if pc not in original or pc in edits[script] or type(op) is not int or not 0 <= op <= 255:
                    raise ValueError('overlapping block or invalid PC/opcode')
                if (op in OPERAND_OPCODES and (type(arg) is not int or not 0 <= arg <= 65535)
                        or op not in OPERAND_OPCODES and arg is not None):
                    raise ValueError('operand does not match opcode width')
                edits[script][pc] = replace(original[pc], opcode=op, operand=arg)
        except (KeyError, TypeError, ValueError) as error:
            raise ProjectError(f'{node.label}: invalid native block: {error}') from error
    for script, program in programs.items():
        if set(edits[script]) != {ins.pc for ins in program.instructions}:
            raise ProjectError('Preserve every instruction in an imported native project')
        resources[script] = replace(program, instructions=tuple(edits[script][ins.pc] for ins in program.instructions)).to_bytes()
    for asset in project.assets:
        if asset.data is not None:
            resources[asset.id] = asset.data
    old = ExpArchive(encode_exp(resources)).metadata()
    titles = tuple(project.title if lang == 'en' and project.title != old.title else
                   project.locales.get(lang, {}).get('title', project.title)
                   for lang in ('en', 'fr', 'it', 'de', 'es'))
    if (old.pack_id, old.episode_id, old.titles) != (project.pack_id, project.episode_id, titles):
        resources[1] = Metadata(project.pack_id, project.episode_id, titles).to_bytes()
    return encode_exp(resources)


def validate_native(project):
    compile_native(project)


def set_data_words(project, script, words, *, extra=False):
    """Explicit data-bank editing; addresses and bank lengths remain stable."""
    resources = _resources(project)
    program = decode_program(resources[script])
    key = 'extra_words' if extra else 'main_words'
    if (len(words) != len(getattr(program, key))
            or any(type(word) is not int or not 0 <= word <= 65535 for word in words)):
        raise ProjectError('Keep the original data-bank length and use unsigned 16-bit words')
    resources[script] = replace(program, **{key: tuple(words)}).to_bytes()
    project.native['resources'][str(script)] = base64.b64encode(resources[script]).decode('ascii')


def packed_strings(project, script):
    """Offer printable packed-text candidates with exact main-bank addresses.

    Data words are untyped; this list is a viewing aid, never decompilation.
    """
    import struct
    program = decode_program(_resources(project)[script])
    data = struct.pack(f'>{len(program.main_words)}H', *program.main_words)
    result, position = [], 0
    while position < len(data):
        end = data.find(b'\0', position)
        if end < 0: break
        text = data[position:end].decode('latin-1')
        if len(text) >= 2 and all(c.isprintable() or c in '\n\r\t' for c in text):
            result.append({'address': position // 2, 'text': text})
        position = (end + 2) // 2 * 2
    return result


def edit_packed_text(project, script, address, text):
    """Replace a confirmed main-bank string without relocating other addresses."""
    import struct
    resources = _resources(project)
    program = decode_program(resources[script])
    data = bytearray(struct.pack(f'>{len(program.main_words)}H', *program.main_words))
    if type(address) is not int or not 0 <= address < len(program.main_words):
        raise ProjectError('Text address must identify a main-bank word')
    start = address * 2
    end = data.find(b'\0', start)
    if end < 0: raise ProjectError('Text must have an existing NUL terminator')
    try: encoded = text.encode('latin-1')
    except UnicodeError as error: raise ProjectError('Native text uses Latin-1') from error
    if b'\0' in encoded or len(encoded) > end - start:
        raise ProjectError('Replacement must fit the original string allocation without NULs')
    data[start:end] = encoded + b'\0' * (end - start - len(encoded))
    set_data_words(project, script, list(struct.unpack(f'>{len(program.main_words)}H', data)))
