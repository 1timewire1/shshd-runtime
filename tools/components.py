"""The authored component set used by desktop, iOS and wheel audits."""
from pathlib import Path
import re


RUNTIME_COMPONENTS = ('formats', 'engine', 'player', 'shs', 'cod')
COMPONENTS = (*RUNTIME_COMPONENTS, 'creator')
PACKAGE_ASSETS = frozenset(('exp_runtime/assets/kiwi.svg', 'exp_runtime/creator/kiwi-hammer.svg'))


def source_roots(root, components=COMPONENTS):
    return tuple(Path(root) / 'packages' / name / 'src' for name in components)


def source_files(root, components=COMPONENTS):
    """Enumerate only distributable Python source and the authored app logos.

    Namespace directories may overlap; files must not. In particular no
    component may install exp_runtime/__init__.py and hide its neighbors.
    """
    files = {}
    for source in source_roots(root, components):
        for path in sorted((source / 'exp_runtime').rglob('*')):
            relative = path.relative_to(source)
            if not path.is_file() or (path.suffix != '.py' and relative.as_posix() not in PACKAGE_ASSETS):
                continue
            if relative.as_posix() == 'exp_runtime/__init__.py':
                raise ValueError('The shared exp_runtime namespace must not have an initializer')
            if relative in files:
                raise ValueError(f'Component files overlap: {relative}')
            files[relative] = path
    return files


def check_versions(root):
    paths = [Path(root) / 'pyproject.toml',
             *(Path(root) / 'packages' / name / 'pyproject.toml' for name in COMPONENTS)]
    versions = [re.search(r'^version = "([^"]+)"', path.read_text(encoding='utf-8'), re.M)[1]
                for path in paths]
    if len(set(versions)) != 1:
        raise ValueError('All EXP Runtime components must share the root project version')
    return versions[0]
