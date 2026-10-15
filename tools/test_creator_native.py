"""Verify authored exports in supplied native ARM KiWi loaders/interpreters.

Optional research check, not a player dependency or full original-app test.
Unicorn executes the actual loader, endian readers, interpreter and memory
accessors. This harness supplies allocation, stream I/O and known UI callback
results; it does not execute the original UI, operating system or game host.
Only the three exact, audited binaries are accepted. No original bytes are
stored in this tool or its report.

uv run --locked --with 'unicorn>=2,<3' python tools/test_creator_native.py \
    --profile cod-ios --binary /path/to/CoD
"""
import argparse
from pathlib import Path
import hashlib
import json
import struct
from exp_runtime.creator import compile_project, Node, Choice, Project
from exp_runtime.exp import ExpArchive
from exp_runtime.vm import KiwiVM, StopKind
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP

SPECS = {
    'cod-ios': ('375f370fa62e43bfd9974b456a4bbeee9310d3bc39095fa1ac880040d27a2301',
                0xd53d, 0xcb8d, 0xe3ee8, 0xe3ed0, None, 0),
    'shs-ios': ('9d779bd7a5d1fa3645281030e7ddadd36046edba04801fad23aa86682eb04fbe',
                0x10e9c, 0x11410, 0x313eac, 0x313ea4, None, 12),
    'shs-android': ('b17aa4c71bc46666d414cafae6fac92bbcd755f3dcccd73975cf05f4a119665b',
                    0x57068, 0x55ce0, 0xf3750, 0xf34fc, 0x4002c, 0),
}


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

def segments(data):
    if data[:4] == b'\x7fELF':
        off = struct.unpack_from('<I', data, 28)[0]
        stride, count = struct.unpack_from('<HH', data, 42)
        for i in range(count):
            kind, fileoff, address, _, size, memory, _, _ = struct.unpack_from('<8I', data, off + i * stride)
            if kind == 1:
                yield address + 0x10000, memory, data[fileoff:fileoff + size]
        return
    if data[:4] == b'\xca\xfe\xba\xbe':
        count, = struct.unpack_from('>I', data, 4)
        for i in range(count):
            cpu, subtype, offset, size, align = struct.unpack_from('>5I', data, 8 + i * 20)
            if cpu == 12 and subtype == 6:
                data = data[offset:offset + size]
                break
    assert data[:4] == b'\xce\xfa\xed\xfe'
    count, = struct.unpack_from('<I', data, 16)
    pos = 28
    for _ in range(count):
        kind, length = struct.unpack_from('<II', data, pos)
        if kind == 1:
            address, memory, fileoff, size = struct.unpack_from('<4I', data, pos + 24)
            if address and memory:
                yield address, memory, data[fileoff:fileoff + size]
        pos += length

class Native:
    def __init__(self, profile, path, script):
        sha, self.loader, self.execute, alloc, free, memset, self.shift = SPECS[profile]
        data = Path(path).read_bytes()
        assert hashlib.sha256(data).hexdigest() == sha
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
                size = mu.reg_read(UC_ARM_REG_R0)
                assert 0 <= size < 0x100000
                result = self.heap
                self.heap += max(16, (size + 15) & ~15)
            elif address == free:
                result = 0
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
    def words(self):
        address = self.get32(self.obj + 0x14)
        count = self.get16(self.obj + 0x48 + self.shift)
        return list(struct.unpack(f'<{count}h', self.mu.mem_read(address, count * 2)))

def verify(profile, binary):
    total = 0
    for operator in ('==', '!=', '<', '<=', '>', '>='):
        for answer in range(4):
            project = story('cod' if profile == 'cod-ios' else 'shs', operator)
            script = ExpArchive(compile_project(project)).programs()[25001]
            native, vm = Native(profile, binary, script.to_bytes()), KiwiVM(script)
            for _ in range(100):
                request = vm.run()
                status, service, args = native.run()
                assert status == 1 and request.kind == StopKind.YIELD
                assert (service, args) == (request.yield_id, request.args), (profile, service, args, request)
                assert native.words() == vm.data
                if service == 7:
                    break
                result = answer if service == 4 else 0
                vm.resume(result)
                native.resume(result)
                total += 1
            else:
                raise AssertionError('Fixture did not terminate')
    return dict(profile=profile, status='passed', programs=24, yield_frames=total,
                binary_sha256=SPECS[profile][0],
                scope='Native KiWi loader and interpreter; UI/host callbacks supplied by test harness')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=SPECS, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = json.dumps(verify(args.profile, args.binary), indent=2) + '\n'
    if args.report:
        args.report.write_text(report, encoding='utf-8')
    print(report, end='')
