"""Build the Swift host with the same Python source used on desktop.

Dependencies are pinned separately because desktop wheels cannot run on iOS.
Only authored source and verified interpreter/dependency packages are bundled.
Device output is unsigned; simulator output receives a local ad-hoc signature.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from zipfile import ZipFile

if __package__:
    from .components import check_versions, source_files
else:
    from components import check_versions, source_files

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = ROOT / 'build/ios/dependencies'
PYTHON = DEPENDENCIES / 'python/Python.xcframework'
SDKS = ('iphoneos', 'iphonesimulator')


def project_version():
    return check_versions(ROOT)


def stage_metadata(directory):
    # Embedded Python does not run pip for our authored package. Retain the
    # same distribution version lookup used by installed and frozen desktops.
    version = project_version()
    # This fork's distribution name, which app_info.runtime_version looks up (else 'development', and no update check).
    path = directory / f'shshd_runtime-{version}.dist-info'
    path.mkdir(parents=True)
    (path / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: shshd-runtime\nVersion: {version}\n')


def sha256(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def download(spec, *, offline=False):
    DEPENDENCIES.mkdir(parents=True, exist_ok=True)
    path = DEPENDENCIES / spec['url'].rsplit('/', 1)[-1]
    if not path.exists():
        if offline:
            raise ValueError(f'Dependency is not cached: {path.name}; run without --offline once')
        temporary = path.with_suffix(path.suffix + '.download')
        try:
            with urllib.request.urlopen(spec['url'], timeout=60) as source, temporary.open('wb') as target:
                shutil.copyfileobj(source, target)
            if sha256(temporary) != spec['sha256']:
                raise ValueError(f'Dependency checksum mismatch: {path.name}')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if sha256(path) != spec['sha256']:
        raise ValueError(f'Dependency checksum mismatch: {path.name}')
    return path


def prepare(sdk, *, offline=False):
    lock = json.loads((ROOT / 'ios/dependencies.json').read_text())
    archive = download(lock['python'], offline=offline)
    marker = DEPENDENCIES / 'python/.verified-sha256'
    if not marker.is_file() or marker.read_text() != lock['python']['sha256']:
        with tempfile.TemporaryDirectory(dir=DEPENDENCIES, prefix='python-') as temporary:
            with tarfile.open(archive) as source:
                source.extractall(temporary, filter='data')
            old = DEPENDENCIES / 'python'
            if old.exists():
                shutil.rmtree(old)
            Path(temporary).rename(old)
        marker.write_text(lock['python']['sha256'])
    icons()
    return download(lock['pillow'][sdk], offline=offline)


def icons():
    """Render only the authored SVG logo, never a player's artwork."""
    directory = ROOT / 'build/ios/Assets.xcassets/AppIcon.appiconset'
    source = ROOT / 'packages/player/src/exp_runtime/assets/kiwi.svg'
    if (directory / 'Contents.json').is_file() and (directory / 'kiwi.png').is_file() and (directory / 'kiwi.png').stat().st_mtime > source.stat().st_mtime:
        return
    os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
    import pygame
    directory.mkdir(parents=True, exist_ok=True)
    surface = pygame.Surface((1024, 1024))
    surface.fill((243, 244, 247))
    logo = pygame.image.load_sized_svg(str(source), (1024, 1024))
    surface.blit(logo, (0, 0))
    pygame.image.save(surface, str(directory / 'kiwi.png'))
    (directory / 'Contents.json').write_text(json.dumps(dict(
        images=[dict(filename='kiwi.png', idiom='universal', platform='ios', size='1024x1024')],
        info=dict(author='exp-runtime', version=1))))
    (directory.parent / 'Contents.json').write_text('{"info":{"author":"exp-runtime","version":1}}')


def _copy_clean(source, destination):
    shutil.copytree(source, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.a', '*.h', '*.c',
                                                 'libpython*.dylib', 'test', 'tests', 'idlelib',
                                                 'tkinter', 'turtledemo', 'ensurepip'))


def stage_runtime(destination):
    """Merge the same disjoint namespace components used by Python installs."""
    for relative, source in source_files(ROOT).items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _frameworks(bundle, base):
    """Use CPython's iOS .fwork loader, without a signing identity at build time."""
    for binary in sorted(base.rglob('*.so')):
        relative = binary.relative_to(base)
        module = '.'.join((*relative.parts[:-1], binary.name.split('.')[0]))
        framework = bundle / 'Frameworks' / (module + '.framework')
        framework.mkdir(parents=True, exist_ok=True)
        info = dict(CFBundleExecutable=module, CFBundleIdentifier='org.shshd.runtime.python.' + module.replace('_', '-'),
                    CFBundleName=module, CFBundlePackageType='FMWK', CFBundleVersion='1',
                    CFBundleShortVersionString='1.0', MinimumOSVersion='15.0')
        (framework / 'Info.plist').write_bytes(plistlib.dumps(info))
        binary.replace(framework / module)
        (framework / module).chmod(0o755)
        placeholder = binary.with_suffix('.fwork')
        placeholder.write_text((framework / module).relative_to(bundle).as_posix() + '\n')
        (framework / (module + '.origin')).write_text(placeholder.relative_to(bundle).as_posix() + '\n')
        privacy = binary.parent / (binary.name.split('.')[0] + '.xcprivacy')
        if privacy.exists():
            shutil.copy2(privacy, framework / 'PrivacyInfo.xcprivacy')


def stage(bundle, sdk):
    wheel = prepare(sdk, offline=True)
    bundle.mkdir(parents=True, exist_ok=True)
    # Replace only the directories owned by this build step, clearing obsolete
    # modules and slices when dependencies or source files change.
    for name in ('python', 'app', 'app_packages', 'Frameworks'):
        path = bundle / name
        if path.exists():
            shutil.rmtree(path)
    slice_name = 'ios-arm64' if sdk == 'iphoneos' else 'ios-arm64_x86_64-simulator'
    _copy_clean(PYTHON / 'lib', bundle / 'python/lib')
    _copy_clean(PYTHON / slice_name / 'lib-arm64', bundle / 'python/lib')
    shutil.copytree(PYTHON / slice_name / 'Python.framework', bundle / 'Frameworks/Python.framework',
                    ignore=shutil.ignore_patterns('Headers', 'Modules'))
    stage_runtime(bundle / 'app')
    stage_metadata(bundle / 'app')
    _copy_clean(ROOT / 'ios/probe', bundle / 'app')
    with ZipFile(wheel) as archive:
        archive.extractall(bundle / 'app_packages')  # Hash-verified dependency, never a user archive.
    _frameworks(bundle, bundle / 'python/lib/python3.14/lib-dynload')
    _frameworks(bundle, bundle / 'app_packages')
    shutil.copy2(ROOT / 'LICENSE', bundle / 'LICENSE')
    shutil.copy2(ROOT / 'ios/dependencies.json', bundle / 'runtime-dependencies.json')
    shutil.copy2(ROOT / 'build/ios/Assets.xcassets/AppIcon.appiconset/kiwi.png', bundle / 'kiwi.png')
    # Strip upstream ad-hoc signatures for the unsigned device artifact. The
    # simulator instead needs all nested binaries to be ad-hoc signed locally.
    for framework in sorted((bundle / 'Frameworks').glob('*.framework')):
        signature = framework / '_CodeSignature'
        if signature.exists():
            shutil.rmtree(signature)
        info = plistlib.loads((framework / 'Info.plist').read_bytes())
        binary = framework / info['CFBundleExecutable']
        with binary.open('rb') as stream:
            fat = stream.read(4) in (b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
                                    b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca')
        if fat:
            thin = binary.with_suffix('.arm64')
            subprocess.run(['xcrun', 'lipo', str(binary), '-thin', 'arm64', '-output', str(thin)], check=True)
            thin.replace(binary)
        subprocess.run(['codesign', '--remove-signature', str(binary)], check=True)
        identity = (os.environ.get('EXPANDED_CODE_SIGN_IDENTITY')
                    if os.environ.get('CODE_SIGNING_ALLOWED') == 'YES' else None)
        if identity or sdk == 'iphonesimulator':
            subprocess.run(['codesign', '--force', '--sign', identity or '-', '--timestamp=none', str(framework)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def build(sdk, *, offline=False):
    if sys.platform != 'darwin':
        raise ValueError('iOS builds require macOS and full Xcode')
    prepare(sdk, offline=offline)
    version = project_version()
    derived = ROOT / 'build/ios' / sdk
    command = ['xcodebuild', '-project', str(ROOT / 'ios/EXPRuntime.xcodeproj'), '-target', 'EXPRuntime',
               '-configuration', 'Release', '-sdk', sdk, 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
               'CODE_SIGNING_ALLOWED=NO', 'DEVELOPMENT_TEAM=', 'PRODUCT_BUNDLE_IDENTIFIER=org.shshd.runtime',
               f'EXP_BUILD_PYTHON={sys.executable}', f'MARKETING_VERSION={version}',
               f'CONFIGURATION_BUILD_DIR={ROOT / "dist/ios" / sdk}', f'OBJROOT={derived / "obj"}',
               f'SYMROOT={derived / "products"}', f'CLANG_MODULE_CACHE_PATH={derived / "ModuleCache"}',
               'build']
    subprocess.run(command, cwd=ROOT, check=True)
    bundle = ROOT / 'dist/ios' / sdk / 'EXP Runtime.app'
    if sdk == 'iphonesimulator':
        subprocess.run(['codesign', '--force', '--sign', '-', '--timestamp=none', str(bundle)], check=True)
    else:
        subprocess.run(['codesign', '--remove-signature', str(bundle)], check=True)
    print(f'Built {sdk}: {bundle}')
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', choices=SDKS, default='iphoneos')
    parser.add_argument('--offline', action='store_true', help='Require checksum-verified cached dependencies')
    parser.add_argument('--prepare', action='store_true', help='Download dependencies without building')
    parser.add_argument('--stage', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.stage:
        stage(args.stage, args.sdk)
    elif args.prepare:
        prepare(args.sdk, offline=args.offline)
    else:
        build(args.sdk, offline=args.offline)


if __name__ == '__main__':
    main()
