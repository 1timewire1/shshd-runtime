"""Build a native desktop app without original game assets.

Run after `uv sync --locked --extra build`. Only licenses, runtime metadata and
the authored kiwi logo are explicitly collected as data. User game files,
screenshots, saves and native decompilations have no path into the executable's
resource collection.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

if __package__:
    from .components import RUNTIME_COMPONENTS as COMPONENTS, check_versions, source_roots
else:
    from components import RUNTIME_COMPONENTS as COMPONENTS, check_versions, source_roots


def build_icon(svg, destination):
    """Render the single SVG source into a native ICO or ICNS container."""
    os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
    import pygame
    from PIL import Image

    surface = pygame.image.load_sized_svg(str(svg), (1024, 1024))
    image = Image.frombytes('RGBA', surface.get_size(), pygame.image.tobytes(surface, 'RGBA'))
    if destination.suffix == '.ico':
        image.save(destination, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    else:
        image.save(destination)


def main():
    root = Path(__file__).resolve().parents[1]
    check_versions(root)
    output = root / 'dist' / 'desktop'
    work = root / 'build' / 'desktop'
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='exp-build-') as temporary:
        stage = Path(temporary)
        entry = stage / 'exp_launcher.py'
        entry.write_text('from exp_runtime.application import main\n\nif __name__ == "__main__":\n    main()\n', encoding='utf-8')
        logo = root / 'packages/player/src/exp_runtime/assets/kiwi.svg'
        # pygame's hook supplies its bundled fallback font and SDL libraries.
        # Only authored runtime modules are reachable through this entry point.
        args = [sys.executable, '-m', 'PyInstaller', '--windowed', '--onedir', '--noconfirm',
                '--name', 'SHSHD Runtime', '--distpath', str(output), '--workpath', str(work),
                '--specpath', str(stage), '--noupx',
                '--add-data', str(root / 'LICENSE') + ':.',
                '--add-data', str(logo) + ':exp_runtime/assets',
                '--copy-metadata', 'shshd-runtime',
                '--exclude-module', 'tkinter']
        for source in source_roots(root, COMPONENTS):
            args += ['--paths', str(source)]
        for component in COMPONENTS:
            args += ['--copy-metadata', f'shshd-runtime-{component}']
        # Profiles are discovered dynamically in minimal Python installs.
        # Standalone apps deliberately include both available games.
        args += ['--hidden-import', 'exp_runtime.shs.profile',
                 '--hidden-import', 'exp_runtime.cod.profile']
        if sys.platform in ('darwin', 'win32'):
            icon = stage / ('kiwi.icns' if sys.platform == 'darwin' else 'kiwi.ico')
            build_icon(logo, icon)
            args += ['--icon', str(icon)]
        if sys.platform == 'darwin':
            args += ['--osx-bundle-identifier', 'org.shshd.runtime']       # this fork's own (never upstream's)
        else:
            # RAR import needs the pinned libarchive (tools/build_rar.py, which downloads its source and needs
            # CMake and a C compiler). Bundle it when it has been built; otherwise the app imports EXP/ZIP only.
            binary = root / 'build/rar/install' / ('bin/archive.dll' if sys.platform == 'win32' else 'lib/libarchive.so.13')
            if binary.is_file():
                from build_rar import build
                binary, license = build(offline=True)
                args += ['--add-binary', str(binary) + ':.', '--add-data', str(license) + ':.']
            else:
                print('warning: libarchive is not built (tools/build_rar.py); this build cannot import RAR archives')
        env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(work / 'pyinstaller-cache'))
        subprocess.run([*args, str(entry)], cwd=stage, env=env, check=True)
    # An empty staging folder beside the executable, ready for a player to drop their own APK, HD ipa, CoD ipa,
    # font and episodes into before first launch (staged_import.py). Only on the onedir layout PyInstaller produces
    # on Windows/Linux -- macOS's .app bundle has no such sibling-of-_internal location to match.
    app_dir = output / 'SHSHD Runtime'
    if app_dir.is_dir():
        for name in ('shs_episodes', 'shshd_episodes', 'cod_episodes'):
            (app_dir / 'import' / name).mkdir(parents=True, exist_ok=True)
    print(f'Built desktop app in {output}')


if __name__ == '__main__':
    main()
