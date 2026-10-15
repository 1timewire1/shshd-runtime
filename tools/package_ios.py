"""Audit and package an unsigned arm64 iPhone app for user signing."""
import argparse
import hashlib
from pathlib import Path
import plistlib
import re
import shutil
import stat
import struct
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

try:
    from tools.package_desktop import audit_bundle
except ModuleNotFoundError:
    from package_desktop import audit_bundle


def audit_binary(path):
    """Require unsigned, thin arm64 device code, including every extension."""
    with path.open('rb') as stream:
        header = stream.read(32)
        if len(header) != 32:
            raise ValueError(f'Truncated native binary: {path.name}')
        magic, cpu, _, _, count, size, _, _ = struct.unpack('<8I', header)
        if magic != 0xfeedfacf or cpu != 0x100000c or count > 10000 or size > 16 * 1024 * 1024:
            raise ValueError(f'Expected a thin arm64 Mach-O binary: {path.name}')
        commands = stream.read(size)
    position, device = 0, False
    for _ in range(count):
        if position + 8 > len(commands):
            raise ValueError(f'Truncated Mach-O load commands: {path.name}')
        command, length = struct.unpack_from('<II', commands, position)
        if length < 8 or position + length > len(commands):
            raise ValueError(f'Invalid Mach-O load command: {path.name}')
        if command == 0x1d:
            raise ValueError(f'Expected unsigned code: {path.name}')
        if command == 0x32:
            if length < 24 or struct.unpack_from('<I', commands, position + 8)[0] != 2:
                raise ValueError(f'Expected iPhone device code, not simulator code: {path.name}')
            device = True
        if command == 0x25:
            device = True
        position += length
    if position != len(commands) or not device:
        raise ValueError(f'Missing or invalid iPhone build metadata: {path.name}')


def audit_ios(bundle):
    """Validate the payload and return its executable paths for ZIP permissions."""
    audit_bundle(bundle)
    info = plistlib.loads((bundle / 'Info.plist').read_bytes())
    if info.get('CFBundleSupportedPlatforms') != ['iPhoneOS']:
        raise ValueError('Only an iPhoneOS device build can be packaged as an IPA')
    executable = bundle / info['CFBundleExecutable']
    audit_binary(executable)
    executables = {executable}
    frameworks = bundle / 'Frameworks'
    if not (frameworks / 'Python.framework/Python').is_file():
        raise ValueError('The embedded Python framework is missing')
    for item in frameworks.iterdir():
        if item.suffix != '.framework' or not item.is_dir():
            raise ValueError(f'Unexpected framework content: {item.name}')
        metadata = plistlib.loads((item / 'Info.plist').read_bytes())
        executable = item / metadata['CFBundleExecutable']
        audit_binary(executable)
        executables.add(executable)
    for path in bundle.rglob('*'):
        if path.is_symlink() or path.name in ('_CodeSignature', 'embedded.mobileprovision'):
            raise ValueError(f'Unexpected link or signing material: {path.relative_to(bundle)}')
        if path.suffix in ('.so', '.dylib', '.a'):
            raise ValueError(f'Native extension outside its framework: {path.relative_to(bundle)}')
        if path.suffix == '.fwork':
            relative = Path(path.read_text().strip())
            if not relative.parts or relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'Frameworks':
                raise ValueError('Invalid embedded Python framework reference')
            target = bundle / relative
            if not target.is_file() or target.with_name(target.name + '.origin').read_text().strip() != path.relative_to(bundle).as_posix():
                raise ValueError(f'Broken embedded Python framework reference: {path.name}')
    return executables


def package(root, label='local'):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', label):
        raise ValueError('Build label must be 1–80 letters, digits, dots, underscores or hyphens')
    if re.fullmatch(r'[0-9a-f]{40}', label):
        label = label[:12]
    bundle = root / 'dist/ios/iphoneos/EXP Runtime.app'
    executables = audit_ios(bundle)
    output = root / 'dist/downloads'
    output.mkdir(parents=True, exist_ok=True)
    target = output / f'shshd-runtime-{label}-ios-arm64-unsigned.ipa'      # this fork's download name
    with tempfile.TemporaryDirectory(prefix='exp-ios-package-', dir=output) as temporary:
        archive = Path(temporary) / target.name
        with ZipFile(archive, 'w', ZIP_DEFLATED) as stream:
            for path in sorted(bundle.rglob('*')):
                if path.is_file():
                    member = ZipInfo.from_file(path, (Path('Payload') / bundle.name / path.relative_to(bundle)).as_posix())
                    # The IPA targets iOS even when its inputs were copied through
                    # a Windows filesystem, which cannot retain Unix mode bits.
                    member.create_system = 3
                    member.external_attr = (stat.S_IFREG | (0o755 if path in executables else 0o644)) << 16
                    member.compress_type = ZIP_DEFLATED
                    with path.open('rb') as source, stream.open(member, 'w') as destination:
                        shutil.copyfileobj(source, destination)
        with ZipFile(archive) as stream:
            if stream.testzip() is not None:
                raise ValueError('The packaged IPA failed its CRC check')
        archive.replace(target)
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.ipa.sha256').write_text(f'{checksum}  {target.name}\n', encoding='ascii')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='local')
    args = parser.parse_args()
    print(package(Path(__file__).resolve().parents[1], args.label))
