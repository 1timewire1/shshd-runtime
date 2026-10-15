"""Archive a built app for download, preserving Unix modes and macOS links.

Only the platform's application bundle/directory is included. The optional
smoke test extracts the finished archive and renders first-launch setup using
SDL's dummy drivers. No player library, APK or episodes are required.
"""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile


TARGETS = ('windows-x64', 'linux-x64', 'macos-arm64', 'macos-x64')
FORBIDDEN_SUFFIXES = {'.apk', '.ipa', '.exp', '.rar', '.kiw', '.sav', '.c', '.asm', '.expproj'}
FORBIDDEN_NAMES = {
    'libshs09.so', 'surviving_hs', 'surviving_hs.app', 'cod.app', 'res_generated',
    'library.json', 'player.json', 'launcher.json',
    '.shs-library', 'episodes', 'extract', 'game-assets', 'original-screenshots',
    'converted_assets', 'debug_images', 'saves', 'renpy',
}


def host_target():
    system = {'win32': 'windows', 'linux': 'linux', 'darwin': 'macos'}.get(sys.platform)
    machine = platform.machine().lower()
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine)
    target = f'{system}-{arch}'
    if target not in TARGETS:
        raise ValueError(f'Unsupported build host: {sys.platform}/{machine}')
    return target


def bundle_name(target, creator=False):
    if creator: return 'EXP Runtime Creator.app' if target.startswith('macos-') else 'EXP Runtime Creator'
    return 'EXP Runtime.app' if target.startswith('macos-') else 'EXP Runtime'


def executable(bundle, target, creator=False):
    if creator:
        return (bundle / 'Contents' / 'MacOS' / 'EXP Runtime Creator' if target.startswith('macos-') else
                bundle / ('EXP Runtime Creator.exe' if target.startswith('windows-') else 'EXP Runtime Creator'))
    if target.startswith('macos-'):
        return bundle / 'Contents' / 'MacOS' / 'EXP Runtime'
    return bundle / ('EXP Runtime.exe' if target.startswith('windows-') else 'EXP Runtime')


def audit_bundle(bundle):
    """Reject known game/research inputs and links outside the built app."""
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError(f'Built application directory is absent or symlinked: {bundle}')
    root = bundle.resolve()
    for path in bundle.rglob('*'):
        relative = path.relative_to(bundle)
        name = path.name.lower()
        if (name in FORBIDDEN_NAMES or (name == 'cod' and path.is_file()) or path.suffix.lower() in FORBIDDEN_SUFFIXES
                or name.startswith(('native-', '.exp-import-'))
                or name.endswith(('.shs-save.json', '.shs-auto.json', '-audit.json', '-trace.json'))):
            raise ValueError(f'Game content or research output found in app: {relative}')
        if path.is_symlink():
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                raise ValueError(f'Broken application link: {relative}') from error
            if not resolved.is_relative_to(root):
                raise ValueError(f'Application link escapes its bundle: {relative}')
        elif not path.is_dir() and not path.is_file():
            raise ValueError(f'Unsupported application file: {relative}')


def _tar_metadata(info):
    # Runner usernames are irrelevant to an installed application.
    info.uid = info.gid = 0
    info.uname = info.gname = ''
    return info


def package(root, target, label, *, creator=False):
    if target not in TARGETS:
        raise ValueError(f'Unknown download target: {target}')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', label):
        raise ValueError('Build label must be 1–80 letters, digits, dots, underscores or hyphens')
    # Commit downloads remain identifiable without forty-character filenames.
    if re.fullmatch(r'[0-9a-f]{40}', label):
        label = label[:12]
    root = root.resolve()
    bundle = root / 'dist' / 'desktop' / bundle_name(target, creator)
    audit_bundle(bundle)
    if not executable(bundle, target, creator).is_file():
        raise ValueError(f'Application executable is absent: {executable(bundle, target, creator)}')
    output = root / 'dist' / 'downloads'
    output.mkdir(parents=True, exist_ok=True)
    suffix = '.tar.gz' if target.startswith('linux-') else '.zip'
    destination = output / f'exp-runtime-{"creator-" if creator else ""}{label}-{target}{suffix}'
    with tempfile.TemporaryDirectory(prefix='exp-package-', dir=output) as temporary:
        archive = Path(temporary) / destination.name
        if target.startswith('macos-'):
            # zipfile/shutil dereference links; ditto preserves the signed app's
            # framework links, executable modes and macOS metadata.
            subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                            str(bundle), str(archive)], check=True)
        elif target.startswith('linux-'):
            with tarfile.open(archive, 'w:gz', dereference=False) as stream:
                stream.add(bundle, arcname=bundle.name, filter=_tar_metadata)
        else:
            shutil.make_archive(str(archive.with_suffix('')), 'zip',
                                root_dir=bundle.parent, base_dir=bundle.name)
        archive.replace(destination)
    checksum = hashlib.sha256()
    with destination.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    destination.with_name(destination.name + '.sha256').write_text(
        f'{checksum.hexdigest()}  {destination.name}\n', encoding='ascii', newline='\n')
    return destination


def smoke_test(archive, target, *, creator=False):
    """Launch the extracted download from a separate working directory."""
    with tempfile.TemporaryDirectory(prefix='exp-download-test-') as temporary:
        stage = Path(temporary)
        if target.startswith('macos-'):
            subprocess.run(['ditto', '-x', '-k', str(archive), str(stage)], check=True)
        elif target.startswith('linux-'):
            with tarfile.open(archive) as stream:
                # Older Python 3.10 patch releases predate extraction filters.
                # This input is the archive just produced by package(), not a
                # player-supplied download.
                filters = {'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}
                stream.extractall(stage, **filters)
        else:
            with zipfile.ZipFile(archive) as stream:
                stream.extractall(stage)
        bundle = stage / bundle_name(target, creator)
        audit_bundle(bundle)
        if target.startswith('macos-'):
            subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)
        env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
                   PYGAME_HIDE_SUPPORT_PROMPT='1', QT_QPA_PLATFORM='offscreen')
        subprocess.run([str(executable(bundle, target, creator)), '--smoke-test'],
                       cwd=stage, env=env, check=True, timeout=30)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--creator', action='store_true', help='Package the standalone creator')
    parser.add_argument('--target', choices=TARGETS, help='Must match the current OS and Python architecture')
    parser.add_argument('--label', default='local', help='Version tag or commit SHA used in the filename')
    parser.add_argument('--smoke-test', action='store_true', help='Extract and test the packaged app before uploading')
    args = parser.parse_args(argv)
    try:
        actual = host_target()
        if args.target and args.target != actual:
            raise ValueError(f'Requested {args.target}, but this Python is running on {actual}')
        result = package(Path(__file__).resolve().parents[1], actual, args.label, creator=args.creator)
        if args.smoke_test:
            smoke_test(result, actual, creator=args.creator)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Packaging failed: {error}\n')
    print(f'Download and SHA-256 checksum ready: {result}')


if __name__ == '__main__':
    main()
