"""Verify authored exports in supplied native ARM KiWi loaders/interpreters.

Optional research check, not a player dependency or full original-app test.
Unicorn executes the actual loader, endian readers, interpreter and memory
accessors. This harness supplies allocation, stream I/O and known UI callback
results; it does not execute the original UI, operating system or game host.
Only the four exact, audited binaries are accepted. No original bytes are
stored in this tool or its report.

uv run --locked --with 'unicorn>=2,<3' python tools/test_creator_native.py \
    --profile cod-ios --binary /path/to/CoD
"""
import argparse
import bisect
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import struct
from exp_runtime.creator import Asset, Character, compile_project, Node, Choice, Project
from exp_runtime.exp import ExpArchive
from exp_runtime.vm import KiwiVM, StopKind
try:
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_UNMAPPED
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_LR,
                                   UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC)
except ImportError:         # The probe list (`probes`) stays importable for tests/test_creator_coverage.py.
    Uc = None

SPECS = {
    'cod-ios': ('375f370fa62e43bfd9974b456a4bbeee9310d3bc39095fa1ac880040d27a2301',
                0xd53d, 0xcb8d, 0xe3ee8, 0xe3ed0, None, 0),
    'shs-ios': ('9d779bd7a5d1fa3645281030e7ddadd36046edba04801fad23aa86682eb04fbe',
                0x10e9c, 0x11410, 0x313eac, 0x313ea4, None, 12),
    'shs-android': ('b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b',
                    0x57068, 0x55ce0, 0xf3750, 0xf34fc, 0x4002c, 0),
    # SHS HD 1.4.38 (com.ea.shs.ipad.inc, armv7 Thumb): CSKiwiEngine::loadScript / execute; operator new[] / delete[]
    # stubs; its loader also logs through a printf stub, which returns at once here.
    'shs-hd-ios': ('327cf59ddb8efd704795099d5b5e9a04ceec51f6c084bf7d0962e78e3ae7e875',
                   0xf87d, 0xefe5, 0x274c6c, 0x274c64, None, 0, (0x274ea8,)),
}


# The HD build's own host dispatcher, `SHSScript::syscall(int)`, run on each yield's live VM to see which frame words it
# reads (SHSScript derives from CSKiwiEngine at offset 0). The code of the classes named by `run` executes, with these
# imports done by the harness; the functions in `panels` return a zeroed stand-in object (the open dialogue panel the
# dialogue cases look up before reading their text); any other call (UI methods, the rest of GameModel, the entity
# table, Objective-C) returns 0 at once, so words a UI element reads later are not seen.
DISPATCH = {'shs-hd-ios': dict(
    syscall=0x3d9b9, stubs=(0x2748a0, 0x274ff4),
    run=('__ZN9SHSScript', '__ZN12CSKiwiEngine', '__ZN8CSString', '__ZNK8CSString', '__ZN12CSSafeArrayT',
         '__ZNK12CSSafeArrayT'),
    panels=('__ZN9GameModel12getTopMostUIEc',),
    imports={0x274c6c: 'new', 0x274c70: 'new', 0x274c64: 'delete', 0x274c68: 'delete', 0x274edc: 'sprintf',
             0x274f58: 'strlen', 0x274f50: 'strcpy', 0x274f4c: 'strcmp', 0x274cbc: 'atoi', 0x274c84: 'divsi3',
             0x274ca0: 'modsi3', 0x274ca4: 'udivsi3', 0x274ca8: 'umodsi3', 0x274e44: 'memcpy', 0x274e48: 'memcpy',
             0x274e4c: 'memset', 0x274ea8: 'ignore', 0x274c28: 'ignore', 0x274c30: 'ignore', 0x274e84: 'ignore',
             0x274c2c: 'fail', 0x274c60: 'fail'},
)}


def story(game, operator):
    return Project(title='Authored native compatibility probe', game=game, start='ask', nodes=[
        Node('end', 'end'),
        Node('no', text='The comparison is false.', next='end'),
        Node('yes', text='The comparison is true.', speaker='Author', next='end'),
        Node('compare', 'branch', variable='probe', value=7, operator=operator, next='yes', otherwise='no'),
        Node('set', 'set', variable='probe', value=7, next='compare'),
        Node('negative', 'set', variable='probe', value=-8, next='compare'),
        Node('ask', 'choice', text='Choose a test branch.', timeout_ms=900, timeout_option=1,
             options=[Choice('Write a positive value', 'set'), Choice('Use initialized zero', 'compare'),
                      Choice('Write a negative value', 'negative'), Choice('End', 'end')]),
    ])

def story_services(game):
    """One probe per story service added for translated episodes: formatting, game-state reads, speakers, stored
    texts, character changes, the portrait picker and vibration."""
    def probe(*nodes):
        nodes = list(nodes) + [Node('end', 'end')]
        for node, following in zip(nodes, nodes[1:]):
            node.next = node.next or following.id
        return Project(game=game, start=nodes[0].id, nodes=nodes, assets=[Asset(100, 'Base art')],
                       characters=[Character('alex', 'Alex', 100), Character('sam', 'Sam', 100)])
    return [
        probe(Node('set', 'set', variable='points', value=-7),
              Node('say', text='{points} points, {points * 3} tripled, {prop(0, 400)} total (100%)', expression=-1),
              Node('ask', 'choice', text='Spend {points}?', options=[Choice('Spend {-points}', 'end'), Choice('Keep', 'end')])),
        probe(Node('flag', 'flag', character='alex', params={'key': 3010, 'bit': 4}),
              Node('test', 'branch', params={'expression': "bit('alex', 3010, 4) + prop('alex', 407) + art('sam') == 0"},
                   next='yes', otherwise='no'), Node('yes', text='Zero'), Node('no', text='Other')),
        probe(Node('who', 'speakers', params={'player': 'alex', 'narrator': 'sam'}), Node('line', text='Narrated'),
              Node('reset', 'speakers'), Node('plain', text='Plain')),
        probe(Node('default', 'text_default', text='Zoe', params={'key': '$ZOE'}),
              Node('store', 'set_text', text='Mr. Doom', params={'key': '$Antagonist'}),
              Node('ask', 'input', params={'result': '$USR'}),
              Node('check', 'text_branch', params={'variable': '$USR', 'equals': 'Alex'}, next='end', otherwise='end')),
        probe(Node('expression', 'expression_default', character='alex', expression=3),
              Node('line', character='alex', text='Default face', expression=-1),
              Node('art', 'character_art', character='alex', asset=100),
              Node('name', 'character_name', character='alex', text='$USR', params={'capitalize': True})),
        probe(Node('pick', 'picker', text='Choose a look', character='alex', params={'characters': ['alex', 'sam']}),
              Node('buzz', 'vibrate')),
        probe(Node('title', 'set_text', text='Mr.', params={'key': '$Title'}),
              Node('more', 'append_text', text=' Doom', params={'key': '$Title'}),
              Node('link', 'open_url', params={'url': 'https://example.com'}),
              Node('test', 'branch', params={'expression': 'build(9) + build(10) > 0'}, next='end', otherwise='end')),
        probe(Node('scene', 'background', asset=100), Node('variant', 'background', asset=100, params={'variant': 2}),
              Node('like', 'relationship', character='alex', params={'romantic': True, 'hide': True}),
              Node('score', 'score', params={'owner': 0, 'key': 400, 'value': 2, 'notification': 'Score +{prop(0, 400)}'}),
              Node('say', character='alex', text='Again', expression=4)),
    ] + ([
        probe(Node('wait', 'loading'),
              Node('send', 'survey', params={'answers': ['1', '2 * 3'], 'results': ['first', 'second']}),
              Node('say', text='{first}')),
        # SHS HD's side panels: the probes check that these interpreters build the same frames the HD build reads
        # (what each original dispatcher then does with them is outside this harness).
        probe(Node('on', 'faceplace'), Node('name', 'faceplace', text='John', params={'action': 'default_name'}),
              Node('post', 'faceplace_post', character='alex', expression=2, text='$USR has {points} points'),
              Node('link', 'faceplace_link', text='Tap here', params={'url': 'https://example.com'}),
              Node('photo', 'faceplace_link', text='Caption', asset=100),
              Node('named', 'faceplace', params={'action': 'name_chosen'}),
              Node('chosen', 'faceplace', params={'action': 'face_chosen'}), Node('clear', 'faceplace', params={'action': 'clear'}),
              Node('points', 'set', variable='points', value=3)),
        probe(Node('on', 'tree'), Node('meet', 'tree_node', text='Meet', params={'type': 1215}),
              Node('ask', 'choice', text='Talk?', options=[Choice('Yes', 'yes'), Choice('No', 'no')]),
              Node('yes', 'tree_result', text='Talked', next='wide'), Node('no', 'tree_result', params={'index': 1}, next='wide'),
              Node('wide', 'tree_node', text='Wide', params={'width': 20}),
              Node('auto', 'tree_node', text='Auto', params={'type': 1221, 'condition': 0x4b}),
              Node('taken', 'tree_result'), Node('join', 'tree', params={'action': 'join'}),
              Node('clear', 'tree', params={'action': 'clear_accumulator', 'id': 3038})),
    ] if game == 'shs' else [])


def scenes(project):
    """The same story with every node in its own scene script: scene links (service 10 and HALT), the scene-entry
    selectors and variables kept in the multi-scene property store."""
    project = deepcopy(project)
    for i, node in enumerate(project.nodes):
        node.scene = 25001 + i
    return project


def probes(game):
    """Every (project, answer) the harness runs for a game; each choice resumes with `answer`."""
    cases = [(story(game, operator), answer) for operator in ('==', '!=', '<', '<=', '>', '>=')
             for answer in range(4)]
    for kind in ('music', 'sound', 'stop_audio', 'score', 'input', 'title', 'message',
                 'notice', 'emphasis', 'scene_label', 'pan', 'transition', 'close_dialogue',
                 'random', 'word_game', *(('football', 'grid') if game == 'shs' else ())):
        params = {'home_result': 'home', 'away_result': 'away'} if kind == 'football' else {}
        cases.append((Project(game=game, start='feature', nodes=[
            Node('feature', kind, text='Authored feature probe', next='math', params=params),
            Node('math', 'set', variable='value', params={'expression': '-12 + 5 * 3'}, next='logic'),
            Node('logic', 'branch', params={'expression': 'value == 3 and (zero == 0 or value // zero > 0)'},
                 next='end', otherwise='wrong'), Node('wrong', text='Unexpected branch', next='end'),
            Node('end', 'end')]), 0))
    services = story_services(game)
    return cases + [(project, 0) for project in services] + [(scenes(project), 0) for project in services]


def segments(data):
    if data[:4] == b'\x7fELF':
        off = struct.unpack_from('<I', data, 28)[0]
        stride, count = struct.unpack_from('<HH', data, 42)
        for i in range(count):
            kind, fileoff, address, _, size, memory, _, _ = struct.unpack_from('<8I', data, off + i * stride)
            if kind == 1:
                yield address + 0x10000, memory, data[fileoff:fileoff + size]
        return
    data = macho(data)
    count, = struct.unpack_from('<I', data, 16)
    pos = 28
    for _ in range(count):
        kind, length = struct.unpack_from('<II', data, pos)
        if kind == 1:
            address, memory, fileoff, size = struct.unpack_from('<4I', data, pos + 24)
            if address and memory:
                yield address, memory, data[fileoff:fileoff + size]
        pos += length


def macho(data):
    """The 32-bit Mach-O image; of a fat binary, its ARMv6 slice."""
    if data[:4] == b'\xca\xfe\xba\xbe':
        count, = struct.unpack_from('>I', data, 4)
        for i in range(count):
            cpu, subtype, offset, size, align = struct.unpack_from('>5I', data, 8 + i * 20)
            if cpu == 12 and subtype == 6:
                data = data[offset:offset + size]
                break
    assert data[:4] == b'\xce\xfa\xed\xfe'
    return data


def functions(data):
    """(address, name) of every defined function symbol of a Mach-O image, sorted by address."""
    data = macho(data)
    count, = struct.unpack_from('<I', data, 16)
    pos, result = 28, []
    for _ in range(count):
        kind, length = struct.unpack_from('<II', data, pos)
        if kind == 2:
            symoff, nsyms, stroff, _ = struct.unpack_from('<4I', data, pos + 8)
            for i in range(nsyms):
                strx, ntype, _, _, value = struct.unpack_from('<IBBHI', data, symoff + i * 12)
                if ntype & 0x0e == 0x0e and value:
                    end = data.index(b'\0', stroff + strx)
                    result.append((value & ~1, data[stroff + strx:end].decode('latin-1')))
        pos += length
    return sorted(result)


def c_format(pattern, words, text):
    """printf for the conversions the HD build's own formatting uses: %d %i %u %x %c %s %%."""
    out, index, position = [], 0, 0
    while position < len(pattern):
        char = pattern[position]
        if char == '%' and position + 1 < len(pattern):
            spec = pattern[position + 1]
            position += 2
            if spec == '%':
                out.append('%'); continue
            value = words[index] if index < len(words) else 0
            index += 1
            signed = value - (1 << 32) if value & 0x80000000 else value
            out.append({'d': str(signed), 'i': str(signed), 'u': str(value), 'x': format(value, 'x'),
                        'c': chr(value & 255), 's': text(value) if spec == 's' else ''}.get(spec, ''))
            continue
        out.append(char)
        position += 1
    return ''.join(out)


# The iOS builds compile KiWi's division and remainder (0x53, 0x54) to calls into libgcc's helpers; these are their
# symbol stubs (Android divides inline). The hook answers them with C's truncating division.
EXP_FRAMES = 1500                       # host calls per script of a --exp episode before its run stops as unfinished
ARITHMETIC = {
    'cod-ios': {0xe3f30: '___divsi3', 0xe4044: '___modsi3', 0xe40bc: '___udivsi3', 0xe40c8: '___umodsi3'},
    'shs-ios': {0x313ed0: '___divsi3', 0x313f30: '___modsi3', 0x313f54: '___udivsi3', 0x313f58: '___umodsi3'},
    'shs-hd-ios': {0x274c84: '___divsi3', 0x274ca0: '___modsi3', 0x274ca4: '___udivsi3', 0x274ca8: '___umodsi3'},
}


def arithmetic(name, a, b):
    if name in ('___divsi3', '___modsi3'):
        a, b = (a - (1 << 32) if a & 0x80000000 else a), (b - (1 << 32) if b & 0x80000000 else b)
    if b == 0:
        raise AssertionError(f'{name} by zero')
    quotient = abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1)
    return (quotient if name.endswith('divsi3') else a - quotient * b) & 0xffffffff


class Native:
    def __init__(self, profile, path, script):
        if Uc is None:
            raise RuntimeError('Install unicorn>=2,<3 to run the native check')
        sha, self.loader, self.execute, alloc, free, memset, self.shift, *quiet = SPECS[profile]
        quiet = set(quiet[0]) if quiet else set()
        helpers = ARITHMETIC.get(profile, {})
        self.handled = {alloc, free, memset, *quiet, *helpers} - {None}   # done by this hook during dispatcher traces too
        data = Path(path).read_bytes()
        assert hashlib.sha256(data).hexdigest() == sha
        self.data = data
        self.mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        pages = set()
        for address, size, payload in segments(data):
            start, end = address & ~4095, (address + size + 4095) & ~4095
            for page in range(start, end, 4096):
                if page not in pages:
                    self.mu.mem_map(page, 4096)
                    pages.add(page)
            self.mu.mem_write(address, payload)
        self.mu.mem_map(0x10000000, 0x1000000)
        self.obj = 0x10000000
        self.stack = self.obj + 0x1000
        self.stream = self.obj + 0x2000
        self.vtable = self.obj + 0x2100
        self.read_stub = self.obj + 0x2200
        self.sentinel = self.obj + 0x2300
        self.heap = self.obj + 0x10000
        self.script, self.position = script, 0
        self.put32(self.obj + 0x24, 0x8000)
        self.put32(self.obj + 0x28, 0x8000)
        self.put16(self.obj + 0x3c + self.shift, 0x7bf5)
        self.put32(self.obj + 0x40 + self.shift, 1024)
        self.put32(self.obj + 0x44 + self.shift, self.stack)
        self.put32(self.stream, self.vtable)
        self.put32(self.vtable + 12, self.read_stub)
        self.mu.mem_write(self.read_stub, b'\x1e\xff\x2f\xe1')
        self.mu.mem_write(self.sentinel, b'\x1e\xff\x2f\xe1')
        def hook(mu, address, size, _):
            if address == alloc:
                result = self.allocate(mu.reg_read(UC_ARM_REG_R0))
            elif address == free or address in quiet:
                result = 0
            elif address in helpers:
                result = arithmetic(helpers[address], mu.reg_read(UC_ARM_REG_R0), mu.reg_read(UC_ARM_REG_R1))
            elif address == self.read_stub:
                destination, length = mu.reg_read(UC_ARM_REG_R1), mu.reg_read(UC_ARM_REG_R2)
                payload = self.script[self.position:self.position + length]
                self.position += len(payload)
                mu.mem_write(destination, payload)
                result = len(payload)
            elif address == memset:
                destination = mu.reg_read(UC_ARM_REG_R0)
                value, length = mu.reg_read(UC_ARM_REG_R1), mu.reg_read(UC_ARM_REG_R2)
                assert length <= 0x100000
                mu.mem_write(destination, bytes([value & 255]) * length)
                result = destination
            else:
                return
            mu.reg_write(UC_ARM_REG_R0, result)
            mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR))
        self.mu.hook_add(UC_HOOK_CODE, hook)
        self.call(self.loader, self.obj, self.stream)
        assert self.position == len(script), (self.position, len(script))
    def allocate(self, size):
        assert 0 <= size < 0x100000
        result = self.heap
        self.heap += max(16, (size + 15) & ~15)
        assert self.heap < self.obj + 0xe00000, 'native heap exhausted'
        return result
    def put16(self, addr, value): self.mu.mem_write(addr, struct.pack('<H', value & 65535))
    def put32(self, addr, value): self.mu.mem_write(addr, struct.pack('<I', value))
    def get16(self, addr): return struct.unpack('<h', self.mu.mem_read(addr, 2))[0]
    def get32(self, addr): return struct.unpack('<I', self.mu.mem_read(addr, 4))[0]
    def call(self, address, r0, r1):
        self.mu.reg_write(UC_ARM_REG_SP, 0x10fff000)
        self.mu.reg_write(UC_ARM_REG_LR, self.sentinel)
        self.mu.reg_write(UC_ARM_REG_R0, r0)
        self.mu.reg_write(UC_ARM_REG_R1, r1)
        try:
            self.mu.emu_start(address, self.sentinel, timeout=2000000, count=2000000)
        except Exception as error:
            raise RuntimeError(f'At native PC {self.mu.reg_read(UC_ARM_REG_PC):x}: {error}') from error
        assert self.mu.reg_read(UC_ARM_REG_PC) == self.sentinel, 'Native instruction/time budget exhausted'
    def run(self):
        self.call(self.execute, self.obj, 100000)
        count = self.get16(self.obj + 0x36 + self.shift)
        sp = self.get16(self.obj + 0x32 + self.shift)
        status = self.mu.mem_read(self.obj + 0x52 + self.shift, 1)[0]
        service = self.get16(self.obj + 0x50 + self.shift)
        args = tuple(self.get16(self.stack + 2 * i) for i in range(sp - count, sp)) if status == 1 else ()
        return status, service, args
    def resume(self, result):
        count = self.get16(self.obj + 0x36 + self.shift)
        sp = self.get16(self.obj + 0x32 + self.shift)
        self.put16(self.obj + 0x32 + self.shift, sp - count)
        self.put16(self.obj + 0x36 + self.shift, result)

    def c_string(self, address, limit=4096):
        data = bytearray()
        while len(data) < limit:
            chunk = bytes(self.mu.mem_read(address + len(data), 64))
            end = chunk.find(b'\0')
            if end >= 0:
                return bytes(data + chunk[:end])
            data += chunk
        raise AssertionError('unterminated native string')

    def libc(self, name):
        """The import `name`, done here: its result in r0 (the caller returns at once)."""
        mu = self.mu
        r = [mu.reg_read(register) for register in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        signed = [value - (1 << 32) if value & 0x80000000 else value for value in r]
        if name == 'new':
            return self.allocate(r[0])
        if name in ('delete', 'ignore'):
            return 0
        if name == 'strlen':
            return len(self.c_string(r[0]))
        if name == 'strcpy':
            mu.mem_write(r[0], self.c_string(r[1]) + b'\0'); return r[0]
        if name == 'strcmp':
            a, b = self.c_string(r[0]), self.c_string(r[1])
            return 0 if a == b else (1 if a > b else 0xffffffff)
        if name == 'atoi':
            text, digits = self.c_string(r[0]).strip(), b''
            for i, byte in enumerate(text):
                if chr(byte).isdigit() or i == 0 and byte in b'+-':
                    digits += bytes([byte])
                else:
                    break
            try: return int(digits) & 0xffffffff
            except ValueError: return 0
        if name in ('divsi3', 'modsi3'):
            if not signed[1]:
                return 0
            quotient = abs(signed[0]) // abs(signed[1]) * (1 if (signed[0] < 0) == (signed[1] < 0) else -1)
            return (quotient if name == 'divsi3' else signed[0] - quotient * signed[1]) & 0xffffffff
        if name in ('udivsi3', 'umodsi3'):
            return 0 if not r[1] else (r[0] // r[1] if name == 'udivsi3' else r[0] % r[1])
        if name == 'memcpy':
            mu.mem_write(r[0], bytes(mu.mem_read(r[1], r[2]))); return r[0]
        if name == 'memset':
            mu.mem_write(r[0], bytes([r[1] & 255]) * r[2]); return r[0]
        if name == 'sprintf':
            sp = mu.reg_read(UC_ARM_REG_SP)
            words = [r[2], r[3]] + [struct.unpack('<I', mu.mem_read(sp + 4 * i, 4))[0] for i in range(16)]
            text = c_format(self.c_string(r[1]).decode('latin-1'), words,
                            lambda address: self.c_string(address).decode('latin-1'))
            mu.mem_write(r[0], text.encode('latin-1') + b'\0'); return len(text)
        raise AssertionError(f'native code reached {name}')

    def dispatch_reads(self, profile, service):
        """The argument words (frame-relative) `SHSScript::syscall(service)` reads from this yield's frame."""
        spec, mu = DISPATCH[profile], self.mu
        if not hasattr(self, 'symbols'):
            self.symbols = functions(self.data)
            self.starts = [address for address, _ in self.symbols]
        count = self.get16(self.obj + 0x36 + self.shift)
        first = self.get16(self.obj + 0x32 + self.shift) - count
        reads, mapped, failure = set(), [], []
        allowed = {}
        panels = {address for address, name in self.symbols if name in spec['panels']}
        panel = self.allocate(0x1000)
        mu.mem_write(panel, bytes(0x1000))
        def runs(address):
            index = bisect.bisect_right(self.starts, address) - 1
            start, name = self.symbols[index] if index >= 0 else (None, '')
            if start not in allowed:
                allowed[start] = name.startswith(spec['run'])
            return allowed[start]
        def code(mu, address, size, _):
            if address == self.sentinel or address in self.handled:
                return
            if spec['stubs'][0] <= address < spec['stubs'][1]:
                name = spec['imports'].get(address, 'unknown import')
                try:
                    result = self.libc(name)
                except Exception as error:      # AssertionError, a bad pointer: report after the run, not mid-hook
                    failure.append(f'{name} at {address:x}: {error}')
                    mu.emu_stop()
                    return
            elif address in panels:
                result = panel
            elif runs(address):
                return
            else:
                result = 0                                       # a call out of the code that runs
            mu.reg_write(UC_ARM_REG_R0, result)
            mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR))
        def read(mu, access, address, size, value, _):
            if self.stack <= address < self.stack + 2048:
                reads.add((address - self.stack) // 2 - first)
        def unmapped(mu, access, address, size, value, _):
            if len(mapped) > 4096:
                return False
            mapped.append(address & ~0xfff)
            mu.mem_map(address & ~0xfff, 0x1000)                # fields past the VM object, and what stubs return
            return True
        mu.reg_write(UC_ARM_REG_C1_C0_2, mu.reg_read(UC_ARM_REG_C1_C0_2) | 0xf << 20)    # VFP: the prologue saves d8-d15
        mu.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        hooks = [mu.hook_add(UC_HOOK_CODE, code), mu.hook_add(UC_HOOK_MEM_READ, read),
                 mu.hook_add(UC_HOOK_MEM_UNMAPPED, unmapped)]
        heap = self.heap
        saved = bytes(mu.mem_read(self.obj, heap - self.obj))       # the VM object, its stack and data bank
        try:
            mu.reg_write(UC_ARM_REG_R0, self.obj)
            mu.reg_write(UC_ARM_REG_R1, service)
            mu.reg_write(UC_ARM_REG_LR, self.sentinel)
            mu.reg_write(UC_ARM_REG_SP, self.obj + 0xf000)
            mu.emu_start(spec['syscall'], self.sentinel, timeout=10000000, count=2000000)
            assert not failure, failure[0]
            assert mu.reg_read(UC_ARM_REG_PC) == self.sentinel, f'service {service} did not return'
        finally:
            for hook in hooks:
                mu.hook_del(hook)
            for page in mapped:
                mu.mem_unmap(page, 0x1000)
            mu.mem_write(self.obj, saved)                       # the dispatcher's own writes (25, 28...) are not checked
            self.heap = heap
        return reads
    def words(self):
        address = self.get32(self.obj + 0x14)
        count = self.get16(self.obj + 0x48 + self.shift)
        return list(struct.unpack(f'<{count}h', self.mu.mem_read(address, count * 2)))


class Host:
    """The host results both interpreters get: numeric properties (52/53, globals 54/55, bits 50/51) are kept, so stories split into
    scenes route through their stored scene selectors; a choice answers `answer`; everything else returns 0."""
    def __init__(self, answer):
        self.answer, self.numbers = answer, {}

    def result(self, service, args):
        if service == 4:
            return self.answer
        if service == 52:
            self.numbers[args[0], args[1]] = args[2]
        elif service == 54:
            self.numbers[0, args[0]] = args[1]
        elif service == 55:
            return self.numbers.get((0, args[0]), 0)    # a global set by 54 (the Demos' choice, read in its next script)
        elif service == 53:
            return self.numbers.get((args[0], args[1]), 0)
        elif service == 50:
            value = self.numbers.get((args[0], args[1]), 0)
            self.numbers[args[0], args[1]] = value | 1 << args[2] if args[3] == 1 else value & ~(1 << args[2])
        elif service == 51:
            return self.numbers.get((args[0], args[1]), 0) >> args[2] & 1
        return 0


def verify(profile, binary, exps=()):
    """The creator's probes, or with `exps` those `.exp` files instead (each played from 25001 with first answers;
    one that stops before its ending, e.g. at a script the host stub can't satisfy, is reported, not failed)."""
    total, scripts, dispatch, unfinished = 0, 0, {}, []
    game = 'cod' if profile == 'cod-ios' else 'shs'
    cases = ([(ExpArchive(Path(path).read_bytes()).programs(), 0, Path(path).name) for path in exps] if exps else
             [(ExpArchive(compile_project(project)).programs(), answer, None) for project, answer in probes(game)])
    for programs, answer, name in cases:
        host = Host(answer)
        queue, ended = [25001], False
        while queue and not ended:
            script = programs[queue.pop()]                    # scheduled scripts load last in, first out
            native, vm = Native(profile, binary, script.to_bytes()), KiwiVM(script)
            scripts += 1
            # An episode can loop on the stub's answers (Train That Brain! replays while "keep training" is answered 0):
            # past EXP_FRAMES the run stops there, as unfinished, before the bump allocator's heap runs out.
            for _ in range(EXP_FRAMES if name else 200):
                request = vm.run()
                status, service, args = native.run()
                assert native.words() == vm.data
                if request.kind == StopKind.HALT:
                    assert status == 4, (profile, status)
                    break
                assert status == 1 and request.kind == StopKind.YIELD
                assert (service, args) == (request.yield_id, request.args), (profile, service, args, request)
                if profile in DISPATCH:
                    # Every word the dispatcher reads lies in the frame (word 0 of an empty frame is the native preload
                    # of stack[SP - argc], which every case shares).
                    reads = native.dispatch_reads(profile, service)
                    assert all(0 <= word < max(len(args), 1) for word in reads), (profile, service, args, sorted(reads))
                    dispatch.setdefault(service, set()).update(reads)
                if service == 7:
                    ended = True
                    break
                if service == 10:
                    queue.append(args[0])
                result = host.result(service, args)
                vm.resume(result)
                native.resume(result)
                total += 1
            else:
                if not name:
                    raise AssertionError('Fixture did not terminate')
                break
        if name and not ended:
            unfinished.append(name)
            continue
        assert ended, 'Fixture did not reach its ending'
    report = dict(profile=profile, status='passed', programs=len(cases), scripts=scripts, yield_frames=total,
                  binary_sha256=SPECS[profile][0],
                  scope='Native KiWi loader and interpreter; UI/host callbacks supplied by test harness')
    if exps:
        report.update(episodes=[name for _, _, name in cases], unfinished=unfinished)
    if dispatch:
        report['dispatcher_words_read'] = {str(service): sorted(words) for service, words in sorted(dispatch.items())}
        report['scope'] += '; SHSScript::syscall reads only frame words'
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=SPECS, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--exp', type=Path, action='append', default=[],
                        help='run this .exp (e.g. a translated episode) instead of the probes; repeatable')
    args = parser.parse_args()
    report = json.dumps(verify(args.profile, args.binary, args.exp), indent=2) + '\n'
    if args.report:
        args.report.write_text(report, encoding='utf-8')
    print(report, end='')
