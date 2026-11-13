"""Per-game library locations.

This fork (shshd-runtime) keeps its data under its own name, `APP_NAME`, never the original's "EXP Runtime" (or its
older "SHS Runtime"), and does not look in the original's folders: the two are distinct apps that never open, write
or remember each other's libraries, saves or settings (owner, 2026-10-14)."""
import json
import os
from pathlib import Path
import sys
import tempfile

from .games import GAMES

APP_NAME = 'SHSHD Runtime'


def user_data_directory() -> Path:
    if sys.platform == 'ios':
        return Path.home() / 'Documents' / APP_NAME
    if sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support'
    elif sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    else:
        root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return root / APP_NAME


DEV_MODULES = 'dev-modules'


def install_dev_modules():
    """shshd-runtime: with the test channel switched on by the hidden settings key (`test_channel`), the data folder's
    `dev-modules` (laid out as `exp_runtime/NAME.py`) goes first on the module path, so a module copied there by the
    channel's `put` is loaded in place of the app's own: a change tried on a device without a new build (owner,
    2026-11-12, for iOS). Called by a host before it imports the app; True when installed. Nothing happens without the
    key or the folder."""
    import json
    folder = user_data_directory() / DEV_MODULES
    try:
        settings = json.loads((user_data_directory() / 'settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    if type(settings.get('test_channel') if isinstance(settings, dict) else None) is not int or not folder.is_dir():
        return False
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    # A regular package already loaded (exp_runtime.platforms, when its iOS host calls this) finds its modules only on its
    # own __path__: dev-modules' copy of the package's folder goes first there too.
    for name, module in list(sys.modules.items()):
        if name.startswith('exp_runtime.') and isinstance(getattr(module, '__path__', None), list):
            overlay = folder.joinpath(*name.split('.'))
            if overlay.is_dir() and str(overlay) not in module.__path__:
                module.__path__.insert(0, str(overlay))
    return True


def library_locations():
    root = user_data_directory()
    locations = {}
    for directory in (root,):
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
        for candidate in (root / 'library',):
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
