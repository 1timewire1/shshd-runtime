"""Per-game library locations, with read-only discovery of legacy SHS paths."""
import json
import os
from pathlib import Path
import sys
import tempfile

from .games import GAMES


def user_data_directory() -> Path:
    if sys.platform == 'ios':
        return Path.home() / 'Documents' / 'EXP Runtime'
    if sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support'
    elif sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    else:
        root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return root / 'EXP Runtime'


def library_locations():
    root = user_data_directory()
    locations = {}
    for directory in (root.with_name('SHS Runtime'), root):
        try:
            data = json.loads((directory / 'launcher.json').read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                continue
            if data.get('version') == 1:
                entries = {'shs': data.get('library')}
            elif data.get('version') == 2 and isinstance(data.get('libraries'), dict):
                entries = data['libraries']
            else:
                continue
            for game, path in entries.items():
                if game not in GAMES or not isinstance(path, str):
                    continue
                candidate = Path(path)
                if sys.platform == 'ios':
                    if candidate.is_absolute() or '..' in candidate.parts:
                        continue
                    candidate = root / candidate
                if candidate.is_absolute():
                    locations[game] = candidate
        except (OSError, ValueError):
            continue
    return locations


def default_library(game='shs') -> Path:
    if game not in GAMES:
        raise ValueError(f'Unknown game: {game}')
    locations = library_locations()
    if game in locations:
        return locations[game]
    root = user_data_directory()
    if game == 'shs' and sys.platform != 'ios':
        # Preserve both source-checkout and installed-app libraries in place.
        if not getattr(sys, 'frozen', False) and Path('.shs-library/library.json').is_file():
            return Path('.shs-library').resolve()
        for candidate in (root / 'library', root.with_name('SHS Runtime') / 'library'):
            if (candidate / 'library.json').is_file():
                return candidate
    return root / 'libraries' / game


def remember_library(directory, game='shs'):
    if game not in GAMES:
        raise ValueError(f'Unknown game: {game}')
    locations = library_locations()
    locations[game] = Path(directory).resolve()
    root = user_data_directory()
    root.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'ios':
        # Documents move with the app container. Store paths relative to the
        # shared library root, never the current installation's UUID.
        locations = {key: path.resolve().relative_to(root.resolve()).as_posix() for key, path in locations.items()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root,
                                         prefix='.launcher-', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(dict(version=2, libraries={key: str(path) for key, path in locations.items()}), stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(root / 'launcher.json')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
