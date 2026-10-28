"""Stage only owned runtime sources, optionally build a debug ARM64 APK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ('formats', 'engine', 'player', 'shs', 'cod')


def prepare_recipe_cache(storage):
    """Keep compiled dependencies, rebuilding only changed custom recipes."""
    storage = Path(storage)
    marker = storage / '.shshd-recipes.json'
    try:
        previous = json.loads(marker.read_text())
    except (FileNotFoundError, ValueError):
        previous = {}
    current = {}
    changed = False
    for name, module in (('android', 'android'), ('pygame_ce', 'pygame')):
        recipe = ROOT / 'android/recipes' / name
        digest = hashlib.sha256()
        for path in sorted(recipe.rglob('*.py')):
            digest.update(path.relative_to(recipe).as_posix().encode())
            digest.update(path.read_bytes())
        current[name] = digest.hexdigest()
        if previous.get(name) == current[name]:
            continue
        changed = True
        builds = storage / 'build/other_builds'
        for directory in builds.glob(name + '*'):
            if directory.name == name or directory.name.startswith(name + '-'):
                shutil.rmtree(directory)
        installs = storage / 'build/python-installs/shshd'
        for arch in installs.glob('*'):
            if arch.is_dir():
                shutil.rmtree(arch / module, ignore_errors=True)
        print(f'Custom Android recipe will rebuild: {name}', flush=True)
    if changed:
        shutil.rmtree(storage / 'dists/shshd', ignore_errors=True)
    storage.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(current, sort_keys=True) + '\n')


def stage(destination):
    destination = Path(destination).resolve()
    # Never let --source-dir wipe arbitrary data. Staging is an owned build path.
    build_root = (ROOT / 'build/android').resolve()
    if not destination.is_relative_to(build_root) or destination == build_root:
        raise ValueError('Source staging must be a subdirectory of build/android')
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True)
    shutil.copy2(ROOT / 'android/main.py', destination / 'main.py')
    for component in COMPONENTS:
        source = ROOT / 'packages' / component / 'src'
        for path in sorted((source / 'exp_runtime').rglob('*')):
            if not path.is_file() or path.is_symlink() or '__pycache__' in path.parts:
                continue
            if path.suffix != '.py' and path.relative_to(source).as_posix() != 'exp_runtime/assets/kiwi.svg':
                continue
            target = destination / path.relative_to(source)
            if target.exists():
                raise ValueError(f'Duplicate namespace owner: {target}')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    # Embedded Python does not run pip for the runtime: the same distribution record build_ios writes, so
    # app_info.runtime_version (the About page, the update check) knows this build's version.
    version = project_version()
    record = destination / f'shshd_runtime-{version}.dist-info'
    record.mkdir()
    (record / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: shshd-runtime\nVersion: {version}\n')
    licenses = destination / 'licenses'
    licenses.mkdir()
    shutil.copy2(ROOT / 'LICENSE', licenses / 'runtime-MIT.txt')
    for component in COMPONENTS:
        shutil.copy2(ROOT / 'packages' / component / 'LICENSE', licenses / f'{component}-MIT.txt')
    manifest = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(destination.rglob('*')) if p.is_file()}
    (destination / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return destination


ARCHES = ('arm64-v8a', 'x86_64')     # phones, and the x86-64 emulator images


# The iOS app's icon background (build_ios.icons) and its plain launch screen.
ICON_BACKGROUND = (243, 244, 247)
SAFE_ZONE = 66 / 108                    # an adaptive icon's foreground keeps its art in the middle 66 of 108 dp


def project_version():
    sys.path.insert(0, str(ROOT / 'tools'))
    from components import check_versions
    return check_versions(ROOT)


def render_icons(directory):
    """The launcher icon as the iOS app's (build_ios.icons): the authored kiwi.svg on its light background, as a
    square icon and as an adaptive icon's two layers (the kiwi inside the safe zone, over that background); and the
    plain launch screen. Never a player's artwork, nor python-for-android's own Kivy logo."""
    os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
    import pygame
    directory.mkdir(parents=True, exist_ok=True)
    source = str(ROOT / 'packages/player/src/exp_runtime/assets/kiwi.svg')
    square = pygame.Surface((1024, 1024))
    square.fill(ICON_BACKGROUND)
    square.blit(pygame.image.load_sized_svg(source, (1024, 1024)), (0, 0))
    pygame.image.save(square, str(directory / 'icon.png'))
    foreground = pygame.Surface((1024, 1024), pygame.SRCALPHA)
    side = round(1024 * SAFE_ZONE)
    foreground.blit(pygame.image.load_sized_svg(source, (side, side)), ((1024 - side) // 2,) * 2)
    pygame.image.save(foreground, str(directory / 'icon_foreground.png'))
    background = pygame.Surface((1024, 1024))
    background.fill(ICON_BACKGROUND)
    pygame.image.save(background, str(directory / 'icon_background.png'))
    return directory


def build_command(source, sdk, ndk, arches=ARCHES, icons=None, version=None):
    return [sys.executable, '-m', 'pythonforandroid.toolchain', 'apk',
            '--bootstrap=sdl2', '--dist-name=shshd', *(f'--arch={arch}' for arch in arches),
            '--requirements=python3,pygame_ce,pillow,pyjnius,android,libbz2,liblzma',
            f'--local-recipes={ROOT / "android/recipes"}',
            f'--private={source}', f'--storage-dir={ROOT / "build/android/p4a"}',
            f'--sdk-dir={sdk}', f'--ndk-dir={ndk}', '--android-api=35', '--ndk-api=24',
            # The iOS app's name and identifier; the project's version (Android's versionCode follows from it).
            '--package=org.shshd.runtime', '--name=SHSHD Runtime', f'--version={version or project_version()}',
            # Portrait first; landscape for the side panels (platforms/android.py, OrientationBridge).
            '--orientation=portrait', '--orientation=landscape', '--orientation=landscape-reverse',
            f'--add-source={ROOT / "android/java"}', '--permission=INTERNET', '--debug',
            *((f'--icon={icons / "icon.png"}', f'--icon-fg={icons / "icon_foreground.png"}',
               f'--icon-bg={icons / "icon_background.png"}', f'--presplash={icons / "icon_background.png"}',
               '--presplash-color=#{:02x}{:02x}{:02x}'.format(*ICON_BACKGROUND)) if icons else ())]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='Compile with the installed Android toolchain')
    parser.add_argument('--arch', action='append', choices=ARCHES,
                        help='An ABI to build (repeatable); default: both, arm64-v8a for devices and x86_64 for the emulator')
    args = parser.parse_args(argv)
    source = stage(ROOT / 'build/android/source')
    print(f'Staged runtime sources: {source}', flush=True)
    if not args.build:
        return
    if platform.system() == 'Linux' and platform.machine() not in ('x86_64', 'AMD64'):
        parser.error('The official Linux Android NDK needs an x86-64 host. Use the Android APK workflow.')
    sdk = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    ndk = os.environ.get('ANDROID_NDK_HOME')
    if not sdk or not ndk:
        parser.error('Set ANDROID_HOME and ANDROID_NDK_HOME; see docs/ANDROID_APP.md')
    prepare_recipe_cache(ROOT / 'build/android/p4a')
    output = ROOT / 'dist/android'
    output.mkdir(parents=True, exist_ok=True)
    icons = render_icons(ROOT / 'build/android/icons')
    subprocess.run(build_command(source, sdk, ndk, tuple(args.arch or ARCHES), icons), cwd=output, check=True)
    apks = sorted(output.glob('*.apk'))
    if not apks:
        raise RuntimeError('Android toolchain finished without an APK')
    for path in apks:
        (path.with_suffix(path.suffix + '.sha256')).write_text(
            f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n')
        print(f'APK: {path}')


if __name__ == '__main__':
    main()
