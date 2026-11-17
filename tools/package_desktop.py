"""Archive a built app for download, preserving Unix modes and macOS links.

Only the platform's application bundle/directory is included. The optional
smoke test extracts the finished archive and renders first-launch setup using
SDL's dummy drivers. No player library, APK or episodes are required.

With --creator, the standalone episode creator (owner, 2026-11-17; upstream's
0df4f13): its smoke test opens the editor offscreen, then checks its notices,
that it finds the player's data folder from a scratch one (decision 6), its
MCP server over stdio (decision 5) and its media worker.
"""
import json
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
NOTICES = 'THIRD_PARTY_NOTICES.txt'         # (decision 2: in both apps)
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


def app_name(creator=False):
    return 'SHSHD Runtime Creator' if creator else 'SHSHD Runtime'


def bundle_name(target, creator=False):
    return app_name(creator) + ('.app' if target.startswith('macos-') else '')


def executable(bundle, target, creator=False):
    name = app_name(creator)
    if target.startswith('macos-'):
        return bundle / 'Contents' / 'MacOS' / name
    return bundle / (name + '.exe' if target.startswith('windows-') else name)


def archive_name(label, target, creator=False):
    """This fork's downloads, not upstream's: shshd-runtime-<label>-<target>, the Creator's shshd-runtime-creator-..."""
    suffix = '.tar.gz' if target.startswith('linux-') else '.zip'
    return f'shshd-runtime-{"creator-" if creator else ""}{label}-{target}{suffix}'


def check_notices(bundle):
    """The app carries its third-party notices (PyInstaller puts data beside its libraries)."""
    found = [path for path in bundle.rglob(NOTICES) if path.is_file() and path.stat().st_size > 1000]
    if not found:
        raise ValueError(f'{NOTICES} is missing from {bundle.name}')


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
    check_notices(bundle)
    if not executable(bundle, target, creator).is_file():
        raise ValueError(f'Application executable is absent: {executable(bundle, target, creator)}')
    output = root / 'dist' / 'downloads'
    output.mkdir(parents=True, exist_ok=True)
    destination = output / archive_name(label, target, creator)
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
        check_notices(bundle)
        if target.startswith('macos-'):
            subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)
        env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
                   PYGAME_HIDE_SUPPORT_PROMPT='1', QT_QPA_PLATFORM='offscreen')
        program = str(executable(bundle, target, creator))
        subprocess.run([program, '--smoke-test'], cwd=stage, env=env, check=True, timeout=60 if creator else 30)
        if creator:
            creator_checks([program], stage, env)


def scratch_data_env(env, folder):
    """`env` with the platform's data root at `folder` (launcher.user_data_directory)."""
    env = dict(env)
    if sys.platform == 'win32':
        env['LOCALAPPDATA'] = str(folder)
    elif sys.platform == 'darwin':
        env['HOME'] = str(folder)
    else:
        env['XDG_DATA_HOME'] = str(folder)
    return env


def creator_checks(command, stage, env):
    """The frozen Creator (`command`: its executable, as a list): it finds the player's data folder (a scratch one), its MCP
    server answers over stdio, and its media worker runs inside it."""
    scratch = stage / 'scratch-data'
    scratch.mkdir()
    answer = subprocess.run([*command, '--data-folder'], cwd=stage, env=scratch_data_env(env, scratch), check=True,
                            timeout=60, capture_output=True, text=True)
    found = json.loads(answer.stdout.strip().splitlines()[-1])
    data = Path(found['data'])
    if not data.name == 'SHSHD Runtime' or scratch.resolve() not in data.resolve().parents:
        raise ValueError(f'The Creator looks for the player\'s data in {data}, not under {scratch}')
    workspace = stage / 'workspace'
    workspace.mkdir()
    request = json.dumps(dict(jsonrpc='2.0', id=1, method='initialize', params=dict(
        protocolVersion='2025-06-18', capabilities={}, clientInfo=dict(name='smoke-test', version='1')))) + '\n'
    process = subprocess.Popen([*command, '--mcp', '--workspace', str(workspace)], cwd=stage, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        process.stdin.write(request)
        process.stdin.flush()
        line = process.stdout.readline()
    finally:
        process.kill()
        process.communicate(timeout=30)
    reply = json.loads(line)
    if reply.get('result', {}).get('serverInfo', {}).get('name') != 'SHSHD Runtime Creator':
        raise ValueError(f'The Creator\'s MCP server did not answer: {line[:300]!r}')
    import io
    import wave
    sound = io.BytesIO()
    with wave.open(sound, 'wb') as stream:
        stream.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\0\0' * 2205)
    import base64
    request = json.dumps(dict(mode='audio_info', data=base64.b64encode(sound.getvalue()).decode()))
    answer = subprocess.run([*command, '--media-worker'], cwd=stage, env=env, input=request.encode(), check=True,
                            timeout=60, capture_output=True)
    if json.loads(answer.stdout).get('duration_ms') not in range(90, 110):
        raise ValueError(f'The Creator\'s media worker answered {answer.stdout[:200]!r}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=TARGETS, help='Must match the current OS and Python architecture')
    parser.add_argument('--label', default='local', help='Version tag or commit SHA used in the filename')
    parser.add_argument('--smoke-test', action='store_true', help='Extract and test the packaged app before uploading')
    parser.add_argument('--creator', action='store_true', help='Package the standalone episode creator')
    args = parser.parse_args(argv)
    try:
        actual = host_target()
        if args.target and args.target != actual:
            raise ValueError(f'Requested {args.target}, but this Python is running on {actual}')
        result = package(Path(__file__).resolve().parents[1], actual, args.label, creator=args.creator)
        if args.smoke_test:
            smoke_test(result, actual, creator=args.creator)
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        parser.exit(1, f'Packaging failed: {error}\n')
    print(f'Download and SHA-256 checksum ready: {result}')


if __name__ == '__main__':
    main()
