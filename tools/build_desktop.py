"""Build a native desktop app without original game assets: the player, or with --creator the standalone episode
creator (owner, 2026-11-17; upstream's commit 0df4f13, renamed for this fork: SHSHD Runtime Creator, org.shshd.creator).

Run after `uv sync --locked --extra build` (--creator: also `--extra creator --extra creator-mcp`). Only licenses, runtime metadata and
the authored kiwi logo are explicitly collected as data. User game files,
screenshots, saves and native decompilations have no path into the executable's
resource collection.
"""
import argparse
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


APP, CREATOR_APP = 'SHSHD Runtime', 'SHSHD Runtime Creator'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--creator', action='store_true', help='Build the standalone episode creator')
    creator = parser.parse_args(argv).creator
    name = CREATOR_APP if creator else APP
    components = (*COMPONENTS, 'creator') if creator else COMPONENTS
    root = Path(__file__).resolve().parents[1]
    check_versions(root)
    output = root / 'dist' / 'desktop'
    work = root / 'build' / ('creator-desktop' if creator else 'desktop')
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='exp-build-') as temporary:
        stage = Path(temporary)
        entry = stage / 'exp_launcher.py'
        module = 'exp_runtime.creator.__main__' if creator else 'exp_runtime.application'
        entry.write_text(f'from {module} import main\n\nif __name__ == "__main__":\n    main()\n', encoding='utf-8')
        logo = root / 'packages/player/src/exp_runtime/assets/kiwi.svg'
        # Every bundled package's licence, generated from this build's environment (decision 2: both apps).
        if __package__:
            from .notices import write as write_notices
        else:
            from notices import write as write_notices
        notices = write_notices(stage / 'THIRD_PARTY_NOTICES.txt', creator)
        # pygame's hook supplies its bundled fallback font and SDL libraries.
        # Only authored runtime modules are reachable through this entry point.
        args = [sys.executable, '-m', 'PyInstaller', '--windowed', '--onedir', '--noconfirm',
                '--name', name, '--distpath', str(output), '--workpath', str(work),
                '--specpath', str(stage), '--noupx',
                '--add-data', str(root / 'LICENSE') + ':.',
                '--add-data', str(notices) + ':.',
                '--add-data', str(logo) + ':exp_runtime/assets',
                '--copy-metadata', 'shshd-runtime',
                '--exclude-module', 'tkinter']
        if creator:
            # The kiwi-and-hammer icon, and its MCP server (decision 5: `--mcp --workspace DIR` in the frozen app), reached only
            # through those flags, so named here; PyInstaller follows its imports. (Collecting all of `mcp` would import its
            # command line, which exits without the optional typer.)
            logo = root / 'packages/creator/src/exp_runtime/creator/kiwi-hammer.svg'
            args += ['--add-data', str(logo) + ':exp_runtime/creator',
                     '--hidden-import', 'exp_runtime.creator.mcp_server', '--hidden-import', 'exp_runtime.creator.media',
                     '--copy-metadata', 'mcp']
        for source in source_roots(root, components):
            args += ['--paths', str(source)]
        for component in components:
            args += ['--copy-metadata', f'shshd-runtime-{component}']
        # Profiles are discovered dynamically in minimal Python installs.
        # Standalone apps deliberately include both available games.
        args += ['--hidden-import', 'exp_runtime.shs.profile',
                 '--hidden-import', 'exp_runtime.cod.profile']
        if sys.platform in ('darwin', 'win32'):
            icon = stage / (('kiwi-hammer' if creator else 'kiwi') + ('.icns' if sys.platform == 'darwin' else '.ico'))
            build_icon(logo, icon)
            args += ['--icon', str(icon)]
        if sys.platform == 'darwin':
            args += ['--osx-bundle-identifier', 'org.shshd.creator' if creator else 'org.shshd.runtime']   # this fork's own
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
    app_dir = output / APP
    if not creator and app_dir.is_dir():
        for name in ('shs_episodes', 'shshd_episodes', 'cod_episodes'):
            (app_dir / 'import' / name).mkdir(parents=True, exist_ok=True)
    print(f'Built {name} in {output}')


if __name__ == '__main__':
    main()
