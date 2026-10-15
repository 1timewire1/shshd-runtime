"""Build and audit the six Python distributions; never publish them."""
import argparse
from email.parser import BytesParser
import hashlib
from pathlib import Path
import subprocess
import tarfile
from zipfile import ZipFile

if __package__:
    from .components import COMPONENTS, check_versions, source_files
else:
    from components import COMPONENTS, check_versions, source_files

ROOT = Path(__file__).resolve().parents[1]


def audit(directory, root=ROOT):
    version = check_versions(root)
    expected = source_files(root)
    owners = {relative: path.relative_to(Path(root) / 'packages').parts[0]
              for relative, path in expected.items()}
    installed = set()
    artifacts = []
    for component in ('', *COMPONENTS):
        # This fork's distributions are shshd-runtime(-component); the import namespace inside stays exp_runtime.
        name = 'shshd_runtime' + ('_' + component if component else '')
        wheel = directory / f'{name}-{version}-py3-none-any.whl'
        with ZipFile(wheel) as archive:
            if any(not n.startswith(('exp_runtime/', f'{name}-{version}.dist-info/'))
                   for n in archive.namelist()):
                raise ValueError(f'{name}: unexpected files outside the component and its metadata')
            payload = {Path(n) for n in archive.namelist() if n.startswith('exp_runtime/')}
            wanted = {p for p, owner in owners.items() if owner == component}
            if payload != wanted or payload & installed:
                raise ValueError(f'{name}: wheel payload differs from its disjoint source component')
            for path in payload:
                if archive.read(path.as_posix()) != expected[path].read_bytes():
                    raise ValueError(f'{name}: stale source in {path}')
            installed.update(payload)
            info = BytesParser().parsebytes(archive.read(f'{name}-{version}.dist-info/METADATA'))
            if info['Version'] != version or any('@' in r for r in info.get_all('Requires-Dist', [])):
                raise ValueError(f'{name}: version mismatch or nonportable dependency metadata')
        source = directory / f'{name}-{version}.tar.gz'
        with tarfile.open(source) as archive:
            prefix = f'{name}-{version}/'
            paths = [m.name.removeprefix(prefix) for m in archive.getmembers() if m.isfile()]
            if not all(m.name.startswith(prefix) and not (m.issym() or m.islnk()) for m in archive.getmembers() if not m.isdir()):
                raise ValueError(f'{name}: unsafe source archive member')
            for path in paths:
                if (Path(path).suffix.lower() in ('.apk', '.ipa', '.exp', '.rar', '.sav', '.so', '.dylib', '.dll')
                        or any(part in ('decomp', 'build', '.shs-library', '__pycache__') for part in Path(path).parts)
                        or path.endswith('Signing.local.xcconfig')):
                    raise ValueError(f'{name}: private or generated input in source archive: {path}')
            for relative in wanted:
                if f'src/{relative.as_posix()}' not in paths:
                    raise ValueError(f'{name}: source archive omits {relative}')
            if not component:
                # The umbrella sdist is also a relocatable source workspace.
                for component_root in (Path(root) / 'packages').glob('*/pyproject.toml'):
                    if component_root.relative_to(root).as_posix() not in paths:
                        raise ValueError(f'Missing component metadata in the source workspace: {component_root}')
                for path in expected.values():
                    if path.relative_to(root).as_posix() not in paths:
                        raise ValueError(f'Missing source workspace file: {path}')
        artifacts.extend((wheel, source))
    if installed != set(expected):
        raise ValueError('The component wheels do not cover all authored runtime source')
    for path in artifacts:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_name(path.name + '.sha256').write_text(f'{digest}  {path.name}\n', encoding='ascii')
    return artifacts


def build(directory, *, offline=False, tag=None):
    version = check_versions(ROOT)
    if tag is not None and tag != f'v{version}':
        raise ValueError(f'Release tag {tag!r} must match the package version: v{version}')
    args = ['uv', 'build', '--all-packages', '--out-dir', str(directory), '--no-build-logs']
    if offline:
        args.append('--offline')
    subprocess.run(args, cwd=ROOT, check=True)
    paths = audit(directory)
    print(f'Audited {len(paths) // 2} component/umbrella wheels and their source archives in {directory}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/packages')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--tag', help='Require this release tag to equal v plus the common package version')
    args = parser.parse_args()
    build(args.output.resolve(), offline=args.offline, tag=args.tag)
