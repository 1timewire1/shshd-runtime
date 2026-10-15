"""A pre-configured "drop your files here before first boot" folder, read once on startup.

An additional way in alongside the app's own manual browse/drag-and-drop import (application.py's
`import_paths`), not a replacement for it: a player who would rather stage everything in one folder before
ever opening the app can do that instead. Checked next to a frozen build's own executable -- the `import`
folder shipped as a sibling of `_internal` in the distributed zip -- or at `SHS_IMPORT_DIR` for testing a
source checkout, where there is no installed executable to sit beside.

    <import folder>/
        <game>.apk           -- the SHS Android 1.0.9 APK, at most one
        <hd>.ipa             -- the SHS HD (iPad) IPA, at most one, optional
        <cod>.ipa            -- the Cause of Death IPA, at most one
        <font file(s)>       -- TrueType/OpenType font(s) for each new library's own fonts/ folder (vector_text.py);
                                 any number, each copied over as-is and matched by filename at load time
        shs_episodes/        -- standard-edition EXPs (and their own shs_options.sav), root or in subfolders
        shshd_episodes/      -- HD EXPs (and their own shs_options.sav), root or in subfolders
        cod_episodes/        -- Cause of Death EXPs (and cod_options.sav, and 1.4.7's store listing `mtxprods`),
                                 root or in subfolders; `mtxprods` may also sit beside the IPAs

One folder sets up both games (this fork): the APK makes the SHS library, with the HD IPA beside it; the CoD IPA
makes the CoD library, which also takes the HD IPA as its art source (`ContentLibrary.add_shs_hd_art`, the CLI's
`add-hd-art`), and the fonts go into each. Either game may be staged alone. The IPAs are told apart by what they
hold (`content.ipa_kind`), not by name. Empty folders count as nothing staged, so the build's own empty
`import` skeleton never reads as an incomplete drop.

All three episode folders accept files directly inside them or organized into further subfolders -- either way
they flatten into one set at import time, the same as a folder dropped onto the app's own browse screen already
does (content.py's own `_episode_inputs`, which this reuses unchanged by handing it these folders as import
paths). Files there other than EXPs, archives and the game's own catalogue are skipped, so a device's whole
Library/Caches folder can go into `cod_episodes` as it is. An HD-only install needs no SD `shs_options.sav` at
all: an episode with no catalog entry from either source still gets a reasonable category from its own pack
numbering (`episode_index.episode_category`'s existing fallback) -- confirmed against the owner's real library
rather than assumed, see legacy/findings.md.

The same layout also comes as one archive (this fork's bulk import): a ZIP or RAR holding those files at its root,
or inside one wrapping folder. It can sit alone in the import folder, or be dropped on or chosen from the app's
first-boot page (application.py). `import_bulk` extracts only the game files above into a temporary folder beside
the libraries, then imports exactly as a loose folder does.
"""
import logging
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from zipfile import BadZipFile, ZipFile

from .content import ContentError, ContentLibrary, import_game, ipa_kind
from .games import GAMES

SD_EPISODES_DIRNAME = 'shs_episodes'
HD_EPISODES_DIRNAME = 'shshd_episodes'
COD_EPISODES_DIRNAME = 'cod_episodes'
EPISODE_DIRNAMES = (SD_EPISODES_DIRNAME, HD_EPISODES_DIRNAME, COD_EPISODES_DIRNAME)
FONT_SUFFIXES = ('.ttf', '.otf', '.ttc')
EPISODE_SUFFIXES = ('.exp', '.zip', '.rar', '.sav')     # what `_episode_inputs` can take from a folder
ARCHIVE_SUFFIXES = ('.zip', '.rar')
BULK_SUFFIXES = ('.apk', '.ipa', *FONT_SUFFIXES, *EPISODE_SUFFIXES)
STORE_NAMES = tuple(sorted({name for game in GAMES.values() if (name := getattr(game, 'STORE_FILENAME', None))}))
MAX_BULK_MEMBERS = 50_000
MAX_BULK_BYTES = 32 * 1024 ** 3


def staged_import_directory():
    """Where to look for a staged folder, or None where there is nowhere sensible to look (a source checkout
    with no SHS_IMPORT_DIR override -- a bare `import` folder relative to an arbitrary working directory would
    be a surprising, unsafe default to auto-import from)."""
    override = os.environ.get('SHS_IMPORT_DIR')
    if override:
        return Path(override)
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / 'import'
    return None


class StagedImport:
    def __init__(self, apk, hd_ipa, fonts, episode_paths, cod_ipa=None, cod_episode_paths=()):
        self.apk, self.hd_ipa, self.fonts, self.episode_paths = apk, hd_ipa, fonts, episode_paths
        self.cod_ipa, self.cod_episode_paths = cod_ipa, list(cod_episode_paths)

    @property
    def games(self):
        """The games this folder sets up, SHS first."""
        return [game for game, source in (('shs', self.apk), ('cod', self.cod_ipa)) if source is not None]


def _has_episodes(folder):
    return any(path.is_file() and (path.suffix.lower() in EPISODE_SUFFIXES or path.name.lower() in STORE_NAMES)
               for path in folder.rglob('*'))


def discover(directory):
    """A `StagedImport` built from `directory`, or None when there is nothing there to import -- the folder
    being absent or holding no game files (empty subfolders included) is not an error (most players never touch it; that just
    means fall back to the app's own manual import). Files staged with no game among them *is* an error: that
    can only be an incomplete drop, not an intentionally unused folder, and failing silently would leave someone
    wondering why their episodes never showed up. So are episodes staged for a game that is not.
    """
    if directory is None or not directory.is_dir():
        return None
    # Only game files count, so a stray readme or desktop.ini never reads as a drop.
    files = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in ('.apk', '.ipa', *FONT_SUFFIXES)]
    apks = [p for p in files if p.suffix.lower() == '.apk']
    fonts = [p for p in files if p.suffix.lower() in FONT_SUFFIXES]
    folders = {name: directory / name for name in EPISODE_DIRNAMES
               if (directory / name).is_dir() and _has_episodes(directory / name)}
    if not (files or folders):
        return None
    if len(apks) > 1:
        raise ContentError(f"'{directory}' has more than one .apk file; keep only the SHS Android APK there")
    ipas = {}
    for path in sorted(p for p in files if p.suffix.lower() == '.ipa'):
        kind = ipa_kind(path)
        if kind == 'shs':
            raise ContentError(f"'{path.name}' is the standard SHS iOS app. The import folder takes the SHS Android "
                               'APK (with the SHS HD IPA); import the iOS app from the setup screen instead')
        if kind in ipas:
            label = 'SHS HD' if kind == 'hd' else 'Cause of Death'
            raise ContentError(f"'{directory}' has more than one {label} .ipa file; keep only one there")
        ipas[kind] = path
    apk, cod_ipa = (apks[0] if apks else None), ipas.get('cod')
    if apk is None and cod_ipa is None:
        raise ContentError(f"'{directory}' has files staged but no game: add the SHS Android .apk or the Cause of "
                           'Death .ipa before starting the app')
    shs_folders = [folders[name] for name in (SD_EPISODES_DIRNAME, HD_EPISODES_DIRNAME) if name in folders]
    if shs_folders and apk is None:
        raise ContentError(f"'{directory}' has SHS episodes staged but no SHS Android .apk -- add it before "
                           'starting the app')
    if COD_EPISODES_DIRNAME in folders and cod_ipa is None:
        raise ContentError(f"'{directory}' has Cause of Death episodes staged but no Cause of Death .ipa -- add it "
                           'before starting the app')
    cod_paths = [folders[COD_EPISODES_DIRNAME]] if COD_EPISODES_DIRNAME in folders else []
    store = next((p for p in directory.iterdir() if p.is_file() and p.name.lower() in STORE_NAMES), None)
    if store is not None and cod_ipa is not None:
        cod_paths.append(store)               # the store listing beside the IPAs (cod/store.py)
    return StagedImport(apk, ipas.get('hd'), fonts, shs_folders, cod_ipa, cod_paths)


def copy_fonts(fonts, library):
    """Staged font files copied into a new library's `fonts/` folder, where vector_text.py's own
    `system_font_path` matches them by filename, the same as a player who copies one in by hand. One font
    failing to copy (e.g. a permissions issue) does not undo what is otherwise a successful import."""
    if not fonts:
        return
    fonts_dir = Path(library) / 'fonts'
    fonts_dir.mkdir(exist_ok=True)
    for font in fonts:
        try:
            shutil.copyfile(font, fonts_dir / font.name)
        except OSError as error:
            logging.warning('Could not copy staged font %s: %s', font, error)


def import_staged(staged, targets):
    """Import each game in `targets` ({game: new library directory}) from `staged`, SHS first; a worker job.

    Each library is created atomically by `import_game`, then given the fonts (a font belongs to the import that
    already succeeded) and, for CoD, the SHS HD IPA as its art source. One game failing does not undo the other:
    returns ({game: directory} imported, [ContentError, ...])."""
    imported, errors = {}, []
    for game in staged.games:
        if game not in targets:
            continue
        destination = Path(targets[game])
        try:
            if game == 'shs':
                import_game(staged.apk, staged.episode_paths, destination, staged.hd_ipa, game='shs')
            else:
                import_game(staged.cod_ipa, staged.cod_episode_paths, destination, game='cod')
        except (ContentError, OSError) as error:
            errors.append(error if isinstance(error, ContentError) else ContentError(str(error)))
            continue
        imported[game] = destination
        copy_fonts(staged.fonts, destination)
        if game == 'cod' and staged.hd_ipa is not None:
            try:
                with ContentLibrary(destination) as library:
                    library.add_shs_hd_art(staged.hd_ipa)
            except (ContentError, OSError) as error:
                errors.append(ContentError(f'Cause of Death was imported without the SHS HD art: {error}'))
    return imported, errors


def staged_archive(directory):
    """The bulk archive in the import folder, or None. Read only when the folder holds no loose game files
    (`discover` returned None); more than one archive there is ambiguous, so an error."""
    if directory is None or not directory.is_dir():
        return None
    archives = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in ARCHIVE_SUFFIXES]
    if len(archives) > 1:
        raise ContentError(f"'{directory}' has more than one .zip/.rar file; keep only the one holding your games")
    return archives[0] if archives else None


def _member_path(name):
    """An archive member's safe relative path, or None for a member the import does not use."""
    normalized = name.replace('\\', '/')
    parts = normalized.split('/')
    if '\0' in normalized or normalized.startswith('/') or '..' in parts or re.match(r'^[A-Za-z]:', normalized):
        raise ContentError(f'The archive holds an invalid path: {name}')
    parts = [part for part in parts if part not in ('', '.')]
    if (not parts or any(part.casefold() == '__macosx' for part in parts) or parts[-1].startswith('._')
            or not (parts[-1].lower().endswith(BULK_SUFFIXES) or parts[-1].lower() in STORE_NAMES)):
        return None
    return '/'.join(parts)


class _Extraction:
    """Members written under `stage` at their own relative paths, bounded in count and size."""

    def __init__(self, archive, stage):
        self.archive, self.stage, self.seen, self.count, self.total = archive, stage, set(), 0, 0

    def add(self, name, size, copy):
        relative = _member_path(name)
        if relative is None:
            return False
        self.count += 1
        self.total += max(size, 0)
        if self.count > MAX_BULK_MEMBERS or self.total > MAX_BULK_BYTES:
            raise ContentError(f'{self.archive.name} is larger than a bulk import supports')
        if relative.casefold() in self.seen:
            raise ContentError(f'{self.archive.name} holds two files named {relative}')
        self.seen.add(relative.casefold())
        target = self.stage.joinpath(*relative.split('/'))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('wb') as output:
            copy(output)
        return True


def _check_space(archive, folder, size):
    # Extracted files plus the libraries made from them: about twice the archive's contents.
    free = shutil.disk_usage(folder).free
    if free < size * 2:
        raise ContentError(f'Importing {archive.name} needs about {size * 2 / 1024 ** 3:.1f} GB free on that drive '
                           f'({free / 1024 ** 3:.1f} GB is free)')


def _extract_zip(archive, stage):
    try:
        package = ZipFile(archive)
    except (BadZipFile, OSError) as error:
        raise ContentError(f'{archive.name} is not a readable ZIP') from error
    with package:
        infos = [info for info in package.infolist() if not info.is_dir()]
        _check_space(archive, stage, sum(info.file_size for info in infos if _member_path(info.filename)))
        extraction = _Extraction(archive, stage)
        for info in infos:
            try:
                extraction.add(info.filename, info.file_size,
                               lambda output, info=info: shutil.copyfileobj(package.open(info), output, 1 << 20))
            except NotImplementedError as error:
                raise ContentError(f'{archive.name} uses a compression method this app cannot read; re-create it '
                                   'as a standard (Deflate) ZIP') from error
            except RuntimeError as error:
                raise ContentError(f'{archive.name} is password-protected; re-create it without a password') from error
            except (BadZipFile, EOFError) as error:
                raise ContentError(f'{archive.name} is damaged: {info.filename}') from error


def _extract_rar(archive, stage):
    from .rar import RarError, RarReader
    try:
        with RarReader(archive) as reader:
            extraction = _Extraction(archive, stage)
            for member in reader:
                if member['mode'] == stat.S_IFDIR or _member_path(member['name']) is None:
                    reader.skip()
                    continue
                if member['encrypted']:
                    raise ContentError(f'{archive.name} is password-protected; re-create it without a password')
                if member['mode'] not in (0, stat.S_IFREG) or member['link'] or member['size'] < 0:
                    raise ContentError(f'{archive.name} holds a member that is not a regular file: {member["name"]}')
                extraction.add(member['name'], member['size'],
                               lambda output, size=member['size']: reader.copy_to(output, size))
    except RarError as error:
        raise ContentError(f'{archive.name} could not be read: {error}') from error


def extract_bulk(archive, stage):
    """Extract a bulk archive's game files into `stage`; returns the folder holding the import layout (`stage`, or
    the archive's one wrapping folder)."""
    archive, stage = Path(archive), Path(stage)
    suffix = archive.suffix.lower()
    if suffix not in ARCHIVE_SUFFIXES:
        raise ContentError(f'{archive.name} is not a .zip or .rar file')
    try:
        (_extract_zip if suffix == '.zip' else _extract_rar)(archive, stage)
    except OSError as error:
        raise ContentError(f'Could not extract {archive.name}: {error}') from error
    entries = list(stage.iterdir())
    if len(entries) == 1 and entries[0].is_dir() and entries[0].name.lower() not in EPISODE_DIRNAMES:
        return entries[0]
    return stage


def import_bulk(archive, targets):
    """A worker job: import every game a bulk archive holds into `targets` ({game: library directory}).

    A game whose library already exists is left as it is (and said so). Returns `import_staged`'s
    ({game: directory} imported, [ContentError, ...])."""
    archive = Path(archive)
    parent = Path(next(iter(targets.values()))).parent        # beside the libraries, so on the same drive
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.exp-bulk-', dir=parent) as temporary:
        staged = discover(extract_bulk(archive, Path(temporary)))
        if staged is None:
            raise ContentError(f'{archive.name} holds no game files. It needs the SHS Android APK or the Cause of '
                               'Death IPA, with the episode folders beside them')
        existing = [game for game in staged.games if Path(targets[game]).exists()]
        wanted = {game: targets[game] for game in staged.games if game not in existing}
        if not wanted:
            raise ContentError(' '.join(f'{GAMES[game].TITLE} already has a library.' for game in existing)
                               + ' Nothing was imported.')
        imported, errors = import_staged(staged, wanted)
    return imported, errors + [ContentError(f'{GAMES[game].TITLE} already had a library, so it was left as it is.')
                               for game in existing]
