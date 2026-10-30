"""Progress bundles (Data Management, owner 2026-10-30): a library's saved games, Decision Trees and names in one zip.

An episode's id is its file's SHA-256, the same in every library imported from that file, and every saved game and
tree is named by it; so a bundle restores into any library of the same game, and progress for an episode the library
lacks waits there until the episode is added. Back Up / Restore Progress write and read bundles; LAN sync is meant to
send the same bundle.

A bundle holds `manifest.json` (what it is and what it holds), `player.json` (the library's name tables and its warp
lock, PLAYER_KEYS) and the library's own progress files (FOLDERS and FILES), at their paths in the library. Options are
not in it: they are shared by both games and live in the app's settings.json.
"""
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import tempfile
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

FORMAT, VERSION = 'shshd-progress', 1
MANIFEST, PLAYER = 'manifest.json', 'player.json'
FOLDERS = ('saves', 'dtsaves', 'dtview')
FILES = ('dtview_tree.json',)
PLAYER_KEYS = ('names', 'name_sets', 'warp_unlocked')
# A progress file's path in the library: a file of FOLDERS (Decision Tree scenes one folder deeper), or FILES.
MEMBER = re.compile(r'(?:saves|dtsaves|dtview)/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?|dtview_tree\.json')
SAVE_SUFFIXES = ('.shs-auto.json', '.shs-save.json')


class BundleError(ValueError):
    pass


def _remove(path):
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def progress_files(directory):
    """The library's progress files: [(path in the library, file)]."""
    directory = Path(directory)
    files = [(name, directory / name) for name in FILES if (directory / name).is_file()]
    for name in FOLDERS:
        if (directory / name).is_dir():
            files += [(path.relative_to(directory).as_posix(), path) for path in sorted((directory / name).rglob('*'))
                      if path.is_file()]
    return [(name, path) for name, path in files if MEMBER.fullmatch(name)]


def saved_ids(names):
    """The episodes with a saved game, from progress file paths."""
    return sorted({name.split('/', 1)[1].split('.', 1)[0] for name in names
                   if name.startswith('saves/') and name.endswith(SAVE_SUFFIXES)})


def write_bundle(directory, game, player, titles, target, *, note=''):
    """Write the library's progress to `target` (a .zip, replaced whole); returns its manifest. `player` is the
    library's player.json data (PLAYER_KEYS are kept), `titles` {episode id: title} names the saved episodes."""
    files = progress_files(directory)
    names = [name for name, _ in files]
    saved = saved_ids(names)
    manifest = dict(format=FORMAT, version=VERSION, game=game, created=datetime.now().isoformat(timespec='seconds'),
                    note=note, saved=[dict(id=key, title=titles.get(key, '')) for key in saved],
                    trees=sum(1 for name in names if name.endswith('.json.gz')),
                    names=len(player.get('names', {})) + sum(len(table) for table in player.get('name_sets', {}).values()))
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.progress-', suffix='.zip', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with ZipFile(temporary, 'w', ZIP_DEFLATED) as bundle:
            bundle.writestr(MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False))
            bundle.writestr(PLAYER, json.dumps({key: player[key] for key in PLAYER_KEYS if key in player},
                                               ensure_ascii=False))
            for name, path in files:
                bundle.write(path, name)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def read_manifest(path):
    """A bundle's manifest, checked; BundleError if it is not a progress bundle this version reads."""
    try:
        with ZipFile(path) as bundle:
            manifest = json.loads(bundle.read(MANIFEST))
    except (OSError, KeyError, BadZipFile, ValueError) as error:
        raise BundleError(f'Not a progress backup: {Path(path).name}') from error
    if not isinstance(manifest, dict) or manifest.get('format') != FORMAT:
        raise BundleError(f'Not a progress backup: {Path(path).name}')
    if manifest.get('version') != VERSION:
        raise BundleError(f'{Path(path).name} was made by a newer version of this app')
    return manifest


def restore_bundle(directory, path, game):
    """Replace the library's progress files with the bundle's; returns (manifest, its player.json data). The bundle is
    checked whole before anything changes, then unpacked beside the library and swapped in."""
    manifest = read_manifest(path)
    if manifest.get('game') != game:
        raise BundleError('That backup is of the other game')
    directory = Path(directory)
    with ZipFile(path) as bundle:
        members = [info for info in bundle.infolist() if not info.is_dir() and info.filename not in (MANIFEST, PLAYER)]
        for info in members:
            if not MEMBER.fullmatch(info.filename) or any(part in ('.', '..') for part in info.filename.split('/')):
                raise BundleError(f'The backup holds an unexpected file: {info.filename}')
        try:
            player = json.loads(bundle.read(PLAYER))
        except (KeyError, ValueError) as error:
            raise BundleError('The backup has no names') from error
        if not isinstance(player, dict):
            raise BundleError('The backup has no names')
        stage = Path(tempfile.mkdtemp(prefix='.restore-', dir=directory))
        try:
            for info in members:
                target = stage / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.read(info))
            old = stage / '.old'
            old.mkdir()
            try:
                for name in FOLDERS + FILES:
                    if (directory / name).exists():
                        (directory / name).replace(old / name)
                for name in FOLDERS + FILES:
                    if (stage / name).exists():
                        (stage / name).replace(directory / name)
            except OSError:
                # Put the library's own progress back before the stage (and `old` in it) is removed.
                for name in FOLDERS + FILES:
                    if (old / name).exists():
                        _remove(directory / name)
                        (old / name).replace(directory / name)
                raise
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    return manifest, {key: player[key] for key in PLAYER_KEYS if key in player}
