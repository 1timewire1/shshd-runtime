"""Build a native desktop app without original game assets.

Run after `uv sync --locked --extra build`. Only licenses, runtime metadata and
the authored kiwi logo are explicitly collected as data. User game files,
screenshots, saves and native decompilations have no path into the executable's
resource collection.
"""
import ast
from importlib.metadata import version as package_version
from pathlib import Path
import os
import subprocess
import sys
import tempfile

if __package__:
    from .components import COMPONENTS, check_versions, source_roots
else:
    from components import COMPONENTS, check_versions, source_roots


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
        args = ['--windowed', '--onedir', '--name', 'EXP Runtime',
                '--specpath', str(stage), '--noupx',
                '--add-data', str(root / 'LICENSE') + ':.',
                '--add-data', str(logo) + ':exp_runtime/assets',
                '--copy-metadata', 'exp-runtime',
                '--exclude-module', 'tkinter']
        for source in source_roots(root):
            args += ['--paths', str(source)]
        for component in COMPONENTS:
            args += ['--copy-metadata', f'exp-runtime-{component}']
        # Profiles are discovered dynamically in minimal Python installs.
        # Standalone apps deliberately include both available games.
        args += ['--hidden-import', 'exp_runtime.shs.profile',
                 '--hidden-import', 'exp_runtime.cod.profile']
        if sys.platform in ('darwin', 'win32'):
            icon = stage / ('kiwi.icns' if sys.platform == 'darwin' else 'kiwi.ico')
            build_icon(logo, icon)
            args += ['--icon', str(icon)]
        if sys.platform == 'darwin':
            args += ['--osx-bundle-identifier', 'org.expruntime.player']
        else:
            from build_rar import build
            binary, license = build()
            args += ['--add-binary', str(binary) + ':.', '--add-data', str(license) + ':.']
        env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(work / 'pyinstaller-cache'))
        subprocess.run([sys.executable, '-m', 'PyInstaller.utils.cliutils.makespec', *args, str(entry)],
                       cwd=stage, env=env, check=True)
        spec = stage / 'EXP Runtime.spec'
        if sys.platform == 'darwin':
            # The CLI exposes only Windows executable version resources.
            # Set the macOS bundle version in the generated spec, before
            # PyInstaller creates and signs Info.plist (default: 0.0.0).
            tree = ast.parse(spec.read_text(encoding='utf-8'))
            bundles = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Name) and node.func.id == 'BUNDLE']
            if len(bundles) != 1:
                raise ValueError('Expected one macOS application bundle in the generated spec')
            bundle = bundles[0]
            bundle.keywords = [key for key in bundle.keywords if key.arg != 'version']
            bundle.keywords.append(ast.keyword(arg='version', value=ast.Constant(package_version('exp-runtime'))))
            spec.write_text(ast.unparse(tree) + '\n', encoding='utf-8')
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm',
                        '--distpath', str(output), '--workpath', str(work), str(spec)],
                       cwd=stage, env=env, check=True)
    print(f'Built desktop app in {output}')


if __name__ == '__main__':
    main()
