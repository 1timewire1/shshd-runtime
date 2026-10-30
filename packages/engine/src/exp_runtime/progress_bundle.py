"""Progress bundles (Data Management, owner 2026-10-30): a library's saved games, Decision Trees and names in one zip.

An episode's id is its file's SHA-256, the same in every library imported from that file, and every saved game and
tree is named by it; so a bundle restores into any library of the same game, and progress for an episode the library
lacks waits there until the episode is added. Back Up / Restore Progress write and read bundles; LAN sync sends one
and merges it (`merge_bundle`: each episode it holds replaces that episode's saves and tree, the rest stay).

A bundle holds `manifest.json` (what it is and what it holds), `player.json` (the library's name tables and its warp
lock, PLAYER_KEYS) and the library's own progress files (FOLDERS and FILES), at their paths in the library. Options
(shared by both games, in the app's settings.json) are in `options.json` only when a sync put them there: its
backup of what it would overwrite, or what it sends.
"""
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import tempfile
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

FORMAT, VERSION = 'shshd-progress', 1
MANIFEST, PLAYER, OPTIONS = 'manifest.json', 'player.json', 'options.json'
FOLDERS = ('saves', 'dtsaves', 'dtview')
FILES = ('dtview_tree.json',)
PLAYER_KEYS = ('names', 'name_sets', 'warp_unlocked')
# A progress file's path in the library: a file of FOLDERS (Decision Tree scenes one folder deeper), or FILES.
MEMBER = re.compile(r'(?:saves|dtsaves|dtview)/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?|dtview_tree\.json')
SAVE_SUFFIXES = ('.shs-auto.json', '.shs-save.json')
SHARED_TREE = '*tree'     # member_episode's name for Football Star's tree (not one episode id's)


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


def member_episode(name):
    """Whose progress a progress file is: an episode id, SHARED_TREE (Football Star's tree: the library's top-level
    tree file and scenes), or None."""
    parts = name.split('/')
    if name == 'dtview_tree.json' or (parts[0] == 'dtsaves' and len(parts) == 2):
        return SHARED_TREE
    if parts[0] == 'saves' or (parts[0] == 'dtview' and len(parts) == 2):
        return parts[1].split('.', 1)[0]
    if parts[0] == 'dtsaves':
        return parts[1]
    return None



def write_bundle(directory, game, player, titles, target, *, note='', keep=None, options=None):
    """Write the library's progress to `target` (a .zip, replaced whole); returns its manifest. `player` is the
    library's player.json data (PLAYER_KEYS are kept), `titles` {episode id: title} names the saved episodes. `keep`
    (a test of a progress file's path) leaves the others out; `options` (the shared options) go in `options.json`."""
    files = [(name, path) for name, path in progress_files(directory) if keep is None or keep(name)]
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
            if options is not None:
                bundle.writestr(OPTIONS, json.dumps(options, ensure_ascii=False))
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


def _checked(bundle, game):
    """A bundle's manifest, its progress files (ZipInfo) and its player.json data, every path checked first."""
    try:
        manifest = json.loads(bundle.read(MANIFEST))
    except (KeyError, ValueError) as error:
        raise BundleError('Not a progress backup') from error
    if not isinstance(manifest, dict) or manifest.get('format') != FORMAT or manifest.get('version') != VERSION:
        raise BundleError('Not a progress backup this version reads')
    if manifest.get('game') != game:
        raise BundleError('That backup is of the other game')
    members = [info for info in bundle.infolist() if not info.is_dir()
               and info.filename not in (MANIFEST, PLAYER, OPTIONS)]
    for info in members:
        if not MEMBER.fullmatch(info.filename) or any(part in ('.', '..') for part in info.filename.split('/')):
            raise BundleError(f'The backup holds an unexpected file: {info.filename}')
    try:
        player = json.loads(bundle.read(PLAYER))
    except (KeyError, ValueError) as error:
        raise BundleError('The backup has no names') from error
    if not isinstance(player, dict):
        raise BundleError('The backup has no names')
    return manifest, members, {key: player[key] for key in PLAYER_KEYS if key in player}


def bundle_options(path):
    """The options a bundle carries (a dict), or None."""
    with ZipFile(path) as bundle:
        try:
            options = json.loads(bundle.read(OPTIONS))
        except KeyError:
            return None
        except ValueError as error:
            raise BundleError('The backup\'s options are damaged') from error
    return options if isinstance(options, dict) else None


def replaced_by(names):
    """A test of a library's progress file: whether merging a bundle of progress files `names` replaces it. An episode's
    saved games go when the bundle has saved games of it; its tree files when the bundle has tree files of it."""
    saves = {member_episode(name) for name in names if name.startswith('saves/')}
    trees = {member_episode(name) for name in names if not name.startswith('saves/')}
    return lambda name: member_episode(name) in (saves if name.startswith('saves/') else trees)


def overwritten(path):
    """A `keep` test for write_bundle: the progress files that merging the bundle at `path` would replace."""
    with ZipFile(path) as bundle:
        return replaced_by([name for name in bundle.namelist() if MEMBER.fullmatch(name)])


def merge_bundle(directory, path, game):
    """Merge a bundle (LAN sync): for each episode it holds progress for, the library's saved games of that episode are
    replaced by the bundle's (all of them: the automatic checkpoint, the manual slot, the picture), and likewise its
    Decision Tree; every other episode's progress stays. Returns (manifest, its player.json data)."""
    directory = Path(directory)
    with ZipFile(path) as bundle:
        manifest, members, player = _checked(bundle, game)
        replaced = replaced_by([info.filename for info in members])
        stage = Path(tempfile.mkdtemp(prefix='.merge-', dir=directory))
        try:
            for info in members:
                target = stage / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.read(info))
            for name, file in progress_files(directory):
                if replaced(name):
                    file.unlink()
            for info in members:
                target = directory / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                (stage / info.filename).replace(target)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    for folder in (directory / 'dtsaves').glob('*') if (directory / 'dtsaves').is_dir() else ():
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    return manifest, player


def restore_bundle(directory, path, game):
    """Replace the library's progress files with the bundle's; returns (manifest, its player.json data). The bundle is
    checked whole before anything changes, then unpacked beside the library and swapped in."""
    directory = Path(directory)
    with ZipFile(path) as bundle:
        manifest, members, player = _checked(bundle, game)
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
    return manifest, player


# -- both games in one file (the chooser's Back Up Progress, owner 2026-10-30) -----------------------------------------
# A set holds each game's ordinary bundle as `<game>.zip`, beside a manifest of its own; Restore Progress treats each
# as it would a single game's backup.
SET_FORMAT = 'shshd-progress-set'


def write_set(target, bundles, *, note=''):
    """Write a set of bundles ({game: its bundle's file}) to `target`, replaced whole; returns its manifest."""
    games = sorted(bundles)
    manifest = dict(format=SET_FORMAT, version=VERSION, created=datetime.now().isoformat(timespec='seconds'),
                    note=note, games=games, saved={game: len(read_manifest(bundles[game]).get('saved', ()))
                                                    for game in games})
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.progress-', suffix='.zip', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with ZipFile(temporary, 'w') as bundle:             # the games' bundles are compressed already
            bundle.writestr(MANIFEST, json.dumps(manifest, indent=2))
            for game in games:
                bundle.write(bundles[game], f'{game}.zip')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def read_backup(path):
    """Any backup's manifest, a game's or a set's, with `games` (the games it holds) and `saved` ({game: how many
    saved games}) either way; BundleError if it is neither."""
    try:
        with ZipFile(path) as bundle:
            manifest = json.loads(bundle.read(MANIFEST))
    except (OSError, KeyError, BadZipFile, ValueError) as error:
        raise BundleError(f'Not a progress backup: {Path(path).name}') from error
    if isinstance(manifest, dict) and manifest.get('format') == SET_FORMAT:
        if manifest.get('version') != VERSION:
            raise BundleError(f'{Path(path).name} was made by a newer version of this app')
        if not isinstance(manifest.get('games'), list) or not isinstance(manifest.get('saved'), dict):
            raise BundleError(f'Not a progress backup: {Path(path).name}')
        return manifest
    manifest = read_manifest(path)
    return dict(manifest, games=[manifest.get('game')], saved={manifest.get('game'): len(manifest.get('saved', ()))})


def set_member(path, game, folder):
    """A set's bundle for `game`, unpacked into `folder`; returns its file (a game's own backup: the file itself)."""
    if read_backup(path).get('format') != SET_FORMAT:
        return Path(path)
    if not re.fullmatch('[a-z]+', game):
        raise BundleError(f'Not a game: {game}')
    target = Path(folder) / f'{game}.zip'
    with ZipFile(path) as bundle:
        try:
            target.write_bytes(bundle.read(f'{game}.zip'))
        except KeyError as error:
            raise BundleError(f'The backup has no {game} progress') from error
    return target
