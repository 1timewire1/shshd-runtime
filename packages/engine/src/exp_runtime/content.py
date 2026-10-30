"""User-supplied game content, isolated from the distributable runtime.

APKs, IPAs and episode ZIPs/RARs are opened as data only. No supplied native code
is executed, and archive paths are never used as output paths. Imported files use
content-derived names.
"""
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import logging
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import struct
import tempfile
from zipfile import BadZipFile, ZipFile, ZipInfo
from xml.parsers.expat import ExpatError
from zlib import error as ZlibError

from .exp import ContentError, ExpArchive, Metadata, MAX_PAYLOAD
from .decode.bytecode import decode_program
from .games import GAMES, PROFILES, SHS_ANDROID, SHS_IOS, game_id
from .presentation import EFFECTS, presentation_record


PROFILE = SHS_ANDROID
IOS_PROFILE = SHS_IOS
MAX_EPISODE_ZIP_MEMBERS = 10_000
MAX_EPISODE_ZIP_BYTES = 2 * 1024 * 1024 * 1024

# Optional companion import: the SHS HD (iPad) app bundle, supplementing an Android APK library. Unlike the APK
# (or a base-game IPA, which replaces it), this is never required -- it unlocks HD-native art: a handful of
# verified low-id chrome assets (HD_ASSET_MAP), same-id per-scene content (HD_SHARED_CONTENT_RANGE), its own
# raw resources (fonts, layout/menu banks) and Football Star's HD scripts. See legacy/findings.md, "HD chrome
# assets may be directly usable after all". Its bundle identifier also satisfies the SHS base-game pattern
# (shs/profile.py BUNDLE_PATTERN), so `_inspect_ipa` refuses it explicitly rather than misreading it as one.
HD_APP_EXECUTABLE = 'Payload/Surviving_HS.app/Surviving_HS'
HD_APP_SHA256 = '327cf59ddb8efd704795099d5b5e9a04ceec51f6c084bf7d0962e78e3ae7e875'
HD_RESOURCE_PREFIX = 'Payload/Surviving_HS.app/res_generated/'
HD_BUNDLE_PATTERN = r'com\.ea\.shs\.ipad(?:\.[A-Za-z0-9-]+)*'
HD_ASSET_MAP = {
    # Dialogue/choice/character-picker portrait mask (a plain bottom-aligned
    # rounded cutout, see ui_assets.Raster.portrait_mask): Android ships it
    # at 128x150; HD's own id 311 is the identical shape at a clean native
    # 256x300 -- confirmed by rendering both and comparing, not assumed from
    # the size match alone.
    268: 311,
    # Dialogue/choice box border pack, per speaker theme (see
    # desktop_dialogue.DialogueRenderer.box's own {1: 204, 2: 220, 3: 252}
    # .get(theme, 236)): HD renumbers each one, but every HD pack has the
    # identical 14-frame layout as its Android counterpart, confirmed by
    # parsing both -- a direct substitution, no frame remapping needed.
    # Which HD id belongs to which theme is read directly off
    # GameModel::setBubbleSex's own branches (param_1 0/1/2/3 -> resource
    # 0x117/0xf7/0x107/0x127), and `theme` here is already sourced from the
    # same per-character number (entity property 651) that native's
    # "sex" parameter is, so the branch numbering lines up directly.
    204: 247,
    220: 263,
    236: 279,
    252: 295,
    # The dialogue "Continue" button and the choice-timer wheel: genuinely
    # new HD-only content with no Android original at all (Android's build
    # never implemented either), both loaded from one master image at HD id
    # 155 (SHSEngine::initPermanents's own `CSResourceMgr::getData(mgr,
    # 0x9b, true)`). Self-mapped (155 -> 155) so hd_asset() can still serve
    # it through this same lookup path -- but unlike every entry above,
    # android_asset(155) always raises ContentError (there is truly nothing
    # to fall back to); callers must treat a missing hd_asset(155) as "skip
    # this feature entirely", not fall back to an Android original.
    155: 155,
}

# Per-scene content (backgrounds/portraits) ships at the SAME numeric id on
# both platforms, unlike the chrome ids above (which HD renumbers or omits
# entirely). Verified by sampling 667 ids that exist in both the Android
# APK and a real HD ipa: 606 are genuine HD upgrades of the identical asset
# (confirmed by rendering and comparing, not just size), and every mismatch
# found was a low chrome/icon id well below this range. Also confirmed
# every Android base id in this window decodes as an image (zero KiWi
# programs; those start at 25000) -- see legacy/findings.md, "53% ...
# questioned and checked properly" and "HD chrome assets may be directly
# usable after all". Below this, ids are chrome with different numbering
# and sometimes coincidentally-reused numbers meaning unrelated content
# (e.g. id 10 is a menu button on Android, an unrelated loading-screen
# collage on HD) -- never substituted except via the explicit,
# individually-verified HD_ASSET_MAP above. At or above it, ids are KiWi
# bytecode programs, confirmed by their `kiwi` header -- substituting those
# would run the wrong script dialect entirely.
HD_SHARED_CONTENT_RANGE = range(1000, 25000)


def _inspect_apk(apk):
    return GAMES['shs'].inspect_apk(apk)


def __getattr__(name):
    # Compatibility for existing diagnostics without making all libraries
    # import the optional Android adapter.
    if name in ('NATIVE_MEMBER', 'NATIVE_SHA256'):
        GAMES['shs']
        from .shs import content
        return getattr(content, name)
    if name == 'IOS_DOWNLOADED_MUSIC':
        return GAMES['shs'].DOWNLOADED_MUSIC
    raise AttributeError(name)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_bundled(record: dict) -> bool:
    return any(key in record for key in ('apk_member', 'ipa_member')) or record.get('builtin') in ('football-star', 'volume-one')


def _with_episode_alias(record, name):
    """Remember a duplicate's filename without changing its identity or source."""
    if name.casefold() in {n.casefold() for n in (record['name'], *record.get('aliases', []))}:
        return record
    return dict(record, aliases=[*record.get('aliases', []), name])


def legacy_fields(titles, game, episode_id=None):
    """shshd-runtime: an episode translated from another SHS game is recognised by its title's tag (the game profile's
    LEGACY_GAMES: " (SHSNR)" for New Rules). The tag is dropped from every title and recorded with the category the
    episode is filed under, so the picker can badge it and never takes it for its smartphone twin, and with its place
    in that category where the game gives one. Returns {titles, legacy, category[, order]}, or {} for any other
    episode."""
    profile = GAMES.get(game)
    for tag, info in getattr(profile, 'LEGACY_GAMES', {}).items():
        suffix = f' ({tag})'
        if titles and titles[0].endswith(suffix):
            fields = dict(titles=[t[:-len(suffix)] if t.endswith(suffix) else t for t in titles], legacy=tag,
                          category=info['category'])
            if episode_id in info.get('order', {}):
                fields['order'] = info['order'][episode_id]
            return fields
    return {}


def file_digest(path: Path) -> str:
    with path.open('rb') as stream:
        result = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
        return result.hexdigest()



def episode_index_fields(archive, programs, variant=None):
    """What the picker needs to know about an episode, read once at import: its release (from its portrait art,
    when it has any) and a sketch of its script text (episode_index.py)."""
    from .episode_index import INDEX_VERSION, image_variant, script_signature
    return dict(variant=variant or image_variant(archive), signature=script_signature(programs), index=INDEX_VERSION)


def _zip_read(apk: ZipFile, name: str | ZipInfo, *, limit=MAX_PAYLOAD) -> bytes:
    kind = Path(str(apk.filename)).suffix[1:].upper()
    kind = kind if kind in ('IPA', 'APK') else 'ZIP'
    label = name.filename if isinstance(name, ZipInfo) else name
    try:
        info = name if isinstance(name, ZipInfo) else apk.getinfo(name)
        if info.file_size > limit:
            raise ContentError(f'{kind} member exceeds supported size: {label}')
        return apk.read(info)
    except KeyError:
        raise ContentError(f'{kind} is missing {label}') from None
    except (BadZipFile, RuntimeError, NotImplementedError, EOFError, ZlibError) as error:
        raise ContentError(f'Cannot read {kind} member {label}: {error}') from error


def _ipa_game(identifier):
    if isinstance(identifier, str):
        for game, profile in GAMES.items():
            if re.fullmatch(profile.BUNDLE_PATTERN, identifier, re.IGNORECASE):
                return game
    raise ContentError(f'IPA bundle identifier {identifier!r} does not identify SHS or Cause of Death')


def _resource_members(names, asset_root, game):
    """Numeric resource id -> member name. Only native resource locations participate: UI atlas names such as
    images/1.png are not aliases of global resource 1. A CoD 1.4.7 IPA is exposed under its 1.3.4 ids
    (cod/assets.py, `logical_members`)."""
    members = {}
    for name in names:
        relative = name.removeprefix(asset_root)
        if name.startswith(asset_root) and re.fullmatch(r'(0|[1-9][0-9]*)', relative):
            members[int(relative)] = name
    if game == 'cod':
        from .cod.assets import logical_members
        members = logical_members(members)
    return members


def _inspect_ipa(package: ZipFile):
    """Identify compatible assets without requiring a particular executable."""
    names = package.namelist()
    if len(names) != len(set(names)):
        raise ContentError('IPA contains ambiguous duplicate member names')
    plists = [name for name in names if re.fullmatch(r'Payload/[^/]+\.app/Info\.plist', name)]
    if len(plists) != 1:
        raise ContentError('IPA must contain exactly one Payload app with Info.plist')
    root = plists[0].removesuffix('Info.plist')
    try:
        info = plistlib.loads(_zip_read(package, plists[0]))
    except (ValueError, TypeError, OverflowError, ExpatError) as error:
        raise ContentError('Invalid IPA Info.plist') from error
    if not isinstance(info, dict):
        raise ContentError('Invalid IPA Info.plist dictionary')
    identifier = info.get('CFBundleIdentifier')
    if isinstance(identifier, str) and re.fullmatch(HD_BUNDLE_PATTERN, identifier, re.IGNORECASE):
        raise ContentError('This is the SHS HD (iPad) app, which supplements the SHS Android 1.0.9 APK rather '
                           'than replacing it: choose the APK as the game, with this IPA alongside it')
    game = _ipa_game(identifier)
    members = _resource_members(names, root + 'res_generated/', game)
    if game == 'cod':
        from .cod.profile import profile_for
        profile = profile_for(lambda resource: _zip_read(
            package, root + 'res_generated/' + str(resource)))
    else:
        from .shs.ios_assets import validate_assets

        def read(resource):
            if resource not in members:
                raise ContentError(f'IPA is missing {root}res_generated/{resource}')
            return _zip_read(package, members[resource])
        validate_assets(read)
        profile = IOS_PROFILE
    # Version fields are informative. Source identity is the complete
    # archive hash, including repacks or differently encrypted executables.
    details = {key: info[key] for key in ('CFBundleIdentifier', 'CFBundleShortVersionString', 'CFBundleVersion')
               if isinstance(info.get(key), str)}
    return root, details, profile


def is_hd_ipa(path) -> bool:
    """Whether `path` is an SHS HD (iPad) app bundle, by its bundle identifier (unvalidated otherwise)."""
    try:
        with ZipFile(path) as package:
            plists = [name for name in package.namelist() if re.fullmatch(r'Payload/[^/]+\.app/Info\.plist', name)]
            if len(plists) != 1:
                return False
            info = plistlib.loads(_zip_read(package, plists[0]))
    except (BadZipFile, OSError, ContentError, ValueError, TypeError, OverflowError, ExpatError):
        return False
    identifier = info.get('CFBundleIdentifier') if isinstance(info, dict) else None
    return isinstance(identifier, str) and re.fullmatch(HD_BUNDLE_PATTERN, identifier, re.IGNORECASE) is not None


def ipa_kind(path) -> str:
    """Which app an IPA holds, unvalidated otherwise: 'hd' for the SHS HD (iPad) app (its executable, or its bundle
    identifier), else the game its bundle identifier names ('shs' or 'cod'). Raises ContentError for anything else."""
    try:
        with ZipFile(path) as package:
            names = package.namelist()
            if HD_APP_EXECUTABLE in names:
                return 'hd'
            plists = [name for name in names if re.fullmatch(r'Payload/[^/]+\.app/Info\.plist', name)]
            if len(plists) != 1:
                raise ContentError(f'{Path(path).name} is not an iOS app (one Payload app with an Info.plist)')
            info = plistlib.loads(_zip_read(package, plists[0]))
    except (BadZipFile, OSError, ValueError, TypeError, OverflowError, ExpatError) as error:
        raise ContentError(f'{Path(path).name} is not a readable IPA') from error
    identifier = info.get('CFBundleIdentifier') if isinstance(info, dict) else None
    if isinstance(identifier, str) and re.fullmatch(HD_BUNDLE_PATTERN, identifier, re.IGNORECASE):
        return 'hd'
    return _ipa_game(identifier)


def _inspect_hd_ipa(ipa: ZipFile):
    names = ipa.namelist()
    if len(names) != len(set(names)):
        raise ContentError('HD ipa contains ambiguous duplicate member names')
    actual = digest(_zip_read(ipa, HD_APP_EXECUTABLE))
    if actual != HD_APP_SHA256:
        raise ContentError(f'Unsupported HD ipa executable ({actual}); '
                           'the currently supported build is SHS HD (iPad) 1.4.38')
    return actual


@dataclass(frozen=True)
class _ZippedEpisodeInput:
    package: ZipFile
    member: ZipInfo
    name: str

    def read_bytes(self, *, limit=MAX_PAYLOAD):
        return _zip_read(self.package, self.member, limit=limit)


@dataclass(frozen=True)
class _StagedEpisodeInput:
    path: Path
    name: str

    def read_bytes(self, *, limit=MAX_PAYLOAD):
        with self.path.open('rb') as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ContentError(f'RAR member exceeds supported size: {self.name}')
        return data


def _episode_rar_inputs(path, catalog_name, stack):
    from .episode_catalog import MAX_CATALOG_BYTES
    from .rar import RarReader, RarError
    stage = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='exp-rar-')))
    episodes, sidecars, seen, total = [], [], set(), 0
    try:
        with RarReader(path) as reader:
            for index, member in enumerate(reader):
                if index >= MAX_EPISODE_ZIP_MEMBERS:
                    raise ContentError('Episode RAR contains too many entries')
                if member['size'] < 0:
                    raise ContentError('Episode RAR has an unknown member size')
                # Solid archives may decode skipped entries to build their
                # dictionary, so bound all declared data, including ignored files.
                total += member['size']
                if total > MAX_EPISODE_ZIP_BYTES:
                    raise ContentError('Episode RAR exceeds the supported total size')
                normalized = member['name'].replace('\\', '/')
                parts, name = normalized.split('/'), normalized.rsplit('/', 1)[-1]
                is_catalog = name.lower() == catalog_name
                if (member['mode'] == stat.S_IFDIR or not name or name.startswith('._')
                        or any(part.casefold() == '__macosx' for part in parts)
                        or not (is_catalog or name.lower().endswith('.exp'))):
                    reader.skip()
                    continue
                if ('\0' in normalized or normalized.startswith('/') or '..' in parts
                        or re.match(r'^[A-Za-z]:', normalized)):
                    raise ContentError(f'Invalid episode RAR member path: {member["name"]}')
                normalized = '/'.join(part for part in parts if part not in ('', '.'))
                if member['mode'] not in (0, stat.S_IFREG) or member['link']:
                    raise ContentError(f'Episode RAR member is not a regular file: {name}')
                if normalized in seen:
                    raise ContentError(f'Episode RAR contains duplicate member names: {normalized}')
                seen.add(normalized)
                if member['encrypted']:
                    raise ContentError('Encrypted episode RARs are not supported; extract the EXP files first')
                limit = MAX_CATALOG_BYTES if is_catalog else MAX_PAYLOAD
                if member['size'] > limit:
                    raise ContentError(f'RAR member exceeds supported size: {name}')
                destination = stage / str(index)  # Never the archive's pathname.
                with destination.open('wb') as output:
                    reader.copy_to(output, member['size'])
                source = _StagedEpisodeInput(destination, name)
                (sidecars if is_catalog else episodes).append(source)
    except RarError as error:
        raise ContentError(f'Cannot import episode RAR {path.name}: {error}') from error
    if not episodes and not sidecars:
        raise ContentError(f'No EXP episodes or {catalog_name} found in {path.name}')
    return episodes, sidecars


def _episode_zip_inputs(package, catalog_name):
    """Select data members without ever materializing their archive paths."""
    from .episode_catalog import MAX_CATALOG_BYTES
    members = package.infolist()
    if len(members) > MAX_EPISODE_ZIP_MEMBERS:
        raise ContentError('Episode ZIP contains too many entries')
    episodes, sidecars, seen, total = [], [], set(), 0
    for member in sorted(members, key=lambda member: member.filename):
        normalized = member.filename.replace('\\', '/')
        parts = normalized.split('/')
        name = parts[-1]
        if (member.is_dir() or not name or name.startswith('._')
                or any(part.casefold() == '__macosx' for part in parts)):
            continue
        is_catalog = name.lower() == catalog_name
        if not is_catalog and not name.lower().endswith('.exp'):
            continue
        if ('\0' in member.orig_filename or normalized.startswith('/') or '..' in parts
                or re.match(r'^[A-Za-z]:', normalized)):
            raise ContentError(f'Invalid episode ZIP member path: {member.filename}')
        normalized = '/'.join(part for part in parts if part not in ('', '.'))
        if stat.S_IFMT(member.external_attr >> 16) not in (0, stat.S_IFREG):
            raise ContentError(f'Episode ZIP member is not a regular file: {member.filename}')
        if normalized in seen:
            raise ContentError(f'Episode ZIP contains duplicate member names: {normalized}')
        seen.add(normalized)
        limit = MAX_CATALOG_BYTES if is_catalog else MAX_PAYLOAD
        if member.file_size > limit:
            raise ContentError(f'ZIP member exceeds supported size: {member.filename}')
        total += member.file_size
        if total > MAX_EPISODE_ZIP_BYTES:
            raise ContentError('Episode ZIP exceeds the supported total size')
        source = _ZippedEpisodeInput(package, member, name)
        (sidecars if is_catalog else episodes).append(source)
    if not episodes and not sidecars:
        raise ContentError(f'No EXP episodes or {catalog_name} found in {Path(package.filename).name}')
    return episodes, sidecars


@contextmanager
def _episode_inputs(paths, *, game):
    """Collect EXPs and optional native category sidecars as one import batch."""
    from .episode_catalog import EpisodeCatalog, MAX_CATALOG_BYTES, read_options_catalog
    catalog_name = GAMES[game].CATALOG_FILENAME
    store_name = getattr(GAMES[game], 'STORE_FILENAME', None)
    episodes, sidecars, checked, checked_archives = {}, {}, set(), set()
    # Keep archives open only for this batch, including validation and rollback.
    # Each EXP is read on demand, so a collection is not loaded into RAM at once.
    with ExitStack() as stack:
        for candidate in paths:
            path = Path(candidate)
            if path.is_dir():
                candidates = sorted(p for p in path.rglob('*') if p.is_file())
            elif path.is_file() and store_name and path.name.lower() == store_name:
                continue                    # read by _store_listing
            elif path.is_file() and (path.suffix.lower() in ('.exp', '.zip', '.rar') or path.name.lower() == catalog_name):
                candidates = [path]
            else:
                raise ContentError(f'Choose an EXP file, episode ZIP/RAR, folder, or {catalog_name}: {path}')
            for item in candidates:
                if item.suffix.lower() in ('.zip', '.rar'):
                    key = item.resolve()
                    if key in checked_archives:
                        continue
                    checked_archives.add(key)
                    if item.suffix.lower() == '.rar':
                        zipped, catalogs = _episode_rar_inputs(item, catalog_name, stack)
                    else:
                        try:
                            package = stack.enter_context(ZipFile(item))
                        except (BadZipFile, UnicodeError) as error:
                            raise ContentError(f'Invalid episode ZIP: {item.name}') from error
                        zipped, catalogs = _episode_zip_inputs(package, catalog_name)
                    for entries, sources in ((episodes, zipped), (sidecars, catalogs)):
                        for index, source in enumerate(sources):
                            entries[key, index] = source
                elif item.suffix.lower() == '.exp':
                    episodes[item.resolve()] = item
                    parent = item.parent.resolve()
                    if parent not in checked:
                        checked.add(parent)
                        for sibling in parent.glob('*'):
                            if sibling.is_file() and sibling.name.lower() == catalog_name:
                                sidecars[sibling.resolve()] = sibling
                elif item.name.lower() == catalog_name:
                    sidecars[item.resolve()] = item
        catalog = EpisodeCatalog()
        for path in sidecars.values():
            if isinstance(path, (_ZippedEpisodeInput, _StagedEpisodeInput)):
                data = path.read_bytes(limit=MAX_CATALOG_BYTES)
            else:
                with path.open('rb') as stream:
                    data = stream.read(MAX_CATALOG_BYTES + 1)
            catalog = catalog.merge(read_options_catalog(data, game=game))
        yield list(episodes.values()), catalog


def _store_listing(paths, *, game):
    """The kept store listing (JSON bytes) from a game's store file among loose import paths and folders (this fork:
    CoD's `mtxprods`, cod/store.py), or None. Archives are not searched. Two different listings are refused."""
    profile = GAMES[game]
    name = getattr(profile, 'STORE_FILENAME', None)
    if name is None:
        return None
    files = []
    for candidate in paths:
        path = Path(candidate)
        if path.is_dir():
            files += sorted(p for p in path.rglob('*') if p.is_file() and p.name.lower() == name)
        elif path.is_file() and path.name.lower() == name:
            files.append(path)
    listings = {profile.read_store_listing(path.read_bytes()) for path in files}
    if len(listings) > 1:
        raise ContentError(f'More than one different {name} was supplied; keep one')
    return listings.pop() if listings else None


def _apk_music_members(apk: ZipFile, ipa_members):
    """Verify only the known iOS download bank; IPA bytes always win."""
    members = {}
    for resource in GAMES['shs'].DOWNLOADED_MUSIC:
        if resource not in ipa_members:
            name = f'assets/Assets/audio/music/{resource}.mp3'
            _zip_read(apk, name)  # Validate presence, ZIP integrity and size before publishing.
            members[resource] = name
    return members


def import_game(apk_path: Path, episode_paths: list[Path], destination: Path, hd_ipa_path: Path | None = None, *,
                music_apk: Path | None = None, game: str | None = None) -> dict:
    """Create a relocatable library atomically; keep original inputs untouched.

    A failed import leaves no partly usable library. Additional episodes are
    optional because the supplied APK or IPA includes playable episode data.
    The historical ``apk_path`` argument also accepts the supported iOS IPA.
    ``hd_ipa_path`` is the optional SHS HD (iPad) bundle, accepted only alongside
    an SHS APK: it unlocks HD-native art (see HD_ASSET_MAP) but nothing requires it.
    """
    apk_path, destination = Path(apk_path), Path(destination)
    hd_ipa_path = Path(hd_ipa_path) if hd_ipa_path is not None else None
    if (hd_ipa_path is None and music_apk is not None and apk_path.suffix.lower() == '.ipa'
            and is_hd_ipa(apk_path)):
        # One IPA plus one APK reads as an IPA library with a music APK; the HD (iPad) app instead
        # supplements that APK (see _inspect_ipa), so swap the roles.
        apk_path, hd_ipa_path, music_apk = Path(music_apk), apk_path, None
    kind = apk_path.suffix.lower().lstrip('.')
    if kind not in ('apk', 'ipa'):
        raise ContentError('Choose an SHS Android 1.0.9 APK, SHS IPA or Cause of Death IPA')
    if game is not None:
        GAMES[game]
    if music_apk is not None and kind != 'ipa':
        raise ContentError('An optional music APK can only supplement an SHS IPA library')
    if hd_ipa_path is not None and kind != 'apk':
        raise ContentError('The SHS HD (iPad) IPA can only supplement an SHS Android APK library')
    if destination.exists():
        raise ContentError(f'Library already exists: {destination}; choose a new directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.exp-import-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'library'
        (staged / 'content').mkdir(parents=True)
        # Validate the private copy, so source changes during import cannot
        # leave a manifest describing different bytes from those we retain.
        copied_apk = staged / 'content' / ('input.' + kind)
        shutil.copyfile(apk_path, copied_apk)
        apk_hash = file_digest(copied_apk)
        final_apk = copied_apk.with_name(apk_hash + '.' + kind)
        copied_apk.rename(final_apk)
        hd_ipa_manifest = final_ipa = None
        if hd_ipa_path is not None:
            copied_ipa = staged / 'content' / 'input.ipa'
            shutil.copyfile(hd_ipa_path, copied_ipa)
            ipa_hash = file_digest(copied_ipa)
            final_ipa = copied_ipa.with_name(ipa_hash + '.ipa')
            copied_ipa.rename(final_ipa)
            try:
                with ZipFile(final_ipa) as ipa:
                    executable_hash = _inspect_hd_ipa(ipa)
            except BadZipFile as error:
                raise ContentError('The supplied HD ipa is not a valid ZIP archive') from error
            hd_ipa_manifest = dict(file=f'content/{ipa_hash}.ipa', sha256=ipa_hash,
                                   executable_sha256=executable_hash)
        records = {}

        def episode_record(data, name, location):
            archive = ExpArchive(data)
            meta = archive.metadata()
            programs = archive.programs()
            if not programs:
                raise ContentError(f'No KiWi scripts in {name}')
            sha = digest(data)
            if sha not in records:
                records[sha] = dict(id=sha, sha256=sha, name=name,
                                    pack_id=meta.pack_id, episode_id=meta.episode_id,
                                    titles=list(meta.titles), scripts=sorted(programs), **location,
                                    **episode_index_fields(archive, programs))
                records[sha].update(legacy_fields(records[sha]['titles'], source_game, meta.episode_id))
            else:
                records[sha] = _with_episode_alias(records[sha], name)
            return sha

        try:
            with ZipFile(final_apk) as apk:
                if kind == 'ipa':
                    root, app_info, profile = _inspect_ipa(apk)
                    source_game = _ipa_game(app_info['CFBundleIdentifier'])
                    assets = root + 'res_generated/'
                else:
                    native_hash = _inspect_apk(apk)
                    source_game = 'shs'
                    profile = PROFILE
                    root = assets = 'assets/Assets/'
                if game is not None and source_game != game:
                    raise ContentError(f'This package belongs to {GAMES[source_game].TITLE}; '
                                       f'choose assets for {GAMES[game].TITLE}')
                if music_apk is not None and source_game != 'shs':
                    raise ContentError('SHS APK music can only supplement an SHS IPA')
                with (ZipFile(final_ipa) if final_ipa is not None else nullcontext()) as hd_zip:
                    built_in = GAMES[source_game].extract_builtin(
                        apk, assets, ios=kind == 'ipa', **({} if hd_zip is None else dict(hd_ipa=hd_zip)))
                if built_in is not None:
                    data, name, tag = built_in
                    sha = digest(data)
                    location = dict(file=f'content/{sha}.exp', **tag)
                    episode_record(data, name, location)
                    (staged / location['file']).write_bytes(data)
                for name in sorted(apk.namelist()):
                    rest = name.removeprefix(root)
                    if name.startswith(root) and '/' not in rest and rest.lower().endswith('.exp'):
                        episode_record(_zip_read(apk, name), rest, {kind + '_member': name})
        except BadZipFile as error:
            raise ContentError(f'The supplied {kind.upper()} is not a valid ZIP archive') from error
        with _episode_inputs(episode_paths, game=source_game) as (external, catalog):
            for path in external:
                data = path.read_bytes()
                sha = digest(data)
                episode_record(data, path.name, dict(file=f'content/{sha}.exp'))
                if 'file' in records[sha]:
                    (staged / records[sha]['file']).write_bytes(data)
        if not records:
            raise ContentError('No episodes found; supply episode EXP files')
        store = _store_listing(episode_paths, game=source_game)
        manifest = dict(format='exp-content-library', version=1, game=source_game, profile=profile,
                        episodes=list(records.values()))
        manifest[kind] = dict(file=f'content/{apk_hash}.{kind}', sha256=apk_hash,
                              **(dict(app=app_info) if kind == 'ipa' else dict(native_sha256=native_hash)))
        if hd_ipa_manifest is not None:
            manifest['hd_ipa'] = hd_ipa_manifest
        if catalog.entries:
            manifest['episode_catalog'] = catalog.to_data()
        if store is not None:
            sha = digest(store)
            (staged / 'content' / f'{sha}.json').write_bytes(store)
            manifest['store'] = dict(file=f'content/{sha}.json', sha256=sha)
        (staged / 'library.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        if music_apk is not None:
            with ContentLibrary(staged) as library:
                library.add_music_apk(music_apk)
                manifest = library.manifest
        staged.rename(destination)
    return manifest


class ContentLibrary:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        try:
            self.manifest = json.loads((self.directory / 'library.json').read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise ContentError(f'Cannot open content library: {error}') from error
        m = self.manifest
        if not isinstance(m, dict) or m.get('profile') not in PROFILES:
            raise ContentError('Unsupported content library format or game profile')
        self.profile = self.recorded_profile = m['profile']
        self.game_id, self.kind = PROFILES[self.profile]
        legacy = m.get('format') == 'shs-content-library'
        if legacy:
            valid = (m.get('version'), self.profile) in ((1, PROFILE), (2, IOS_PROFILE), (3, IOS_PROFILE))
        else:
            valid = (m.get('format') == 'exp-content-library' and m.get('version') == 1
                     and m.get('game') == self.game_id)
        if not valid or ('game' in m and m['game'] != self.game_id):
            raise ContentError('Unsupported content library format or conflicting game identity')
        self.game_title = GAMES[self.game_id].TITLE
        member_key = self.kind + '_member'
        if (not isinstance(m.get(self.kind), dict) or ('apk' in m and 'ipa' in m)
                or (legacy and ('music_apk' in m) != (m['version'] == 3))
                or ('music_apk' in m and (self.game_id, self.kind) != ('shs', 'ipa'))
                or ('music_apk' in m and not isinstance(m['music_apk'], dict))
                or not isinstance(m.get('episodes'), list) or not m['episodes']):
            raise ContentError('Invalid content library manifest')
        if 'hd_ipa' in m and ((self.game_id, self.kind) != ('shs', 'apk') or not isinstance(m['hd_ipa'], dict)
                              or not isinstance(m['hd_ipa'].get('sha256'), str)
                              or not re.fullmatch('[0-9a-f]{64}', m['hd_ipa']['sha256'])
                              or not isinstance(m['hd_ipa'].get('executable_sha256'), str)):
            raise ContentError('Invalid content library manifest')
        # Cause of Death may name the SHS HD bundle as a presentation-only art source (cod/hd_art.py); it never becomes
        # `hd_ipa`, so none of SHS HD's screens, strings or scripts apply to CoD.
        if 'shs_hd_art' in m and (self.game_id != 'cod' or not isinstance(m['shs_hd_art'], dict)
                                  or not isinstance(m['shs_hd_art'].get('sha256'), str)
                                  or not re.fullmatch('[0-9a-f]{64}', m['shs_hd_art']['sha256'])
                                  or not isinstance(m['shs_hd_art'].get('executable_sha256'), str)):
            raise ContentError('Invalid content library manifest')
        seen = set()
        for record in m['episodes']:
            if (not isinstance(record, dict) or not isinstance(record.get('sha256'), str)
                    or not re.fullmatch('[0-9a-f]{64}', record['sha256'])
                    or record.get('id') != record['sha256'] or record['id'] in seen
                    or not isinstance(record.get('name'), str)
                    or not isinstance(record.get('titles'), list) or len(record['titles']) != 5
                    or not all(isinstance(title, str) for title in record['titles'])
                    or any(type(record.get(key)) is not int or not 0 <= record[key] <= 65535
                           for key in ('pack_id', 'episode_id'))
                    or sum(key in record for key in ('file', 'apk_member', 'ipa_member')) != 1
                    or ('ipa_member' if self.kind == 'apk' else 'apk_member') in record
                    or ('builtin' in record and (record['builtin'] != GAMES[self.game_id].BUILTIN or 'file' not in record))
                    or not isinstance(record.get('legacy', ''), str) or not isinstance(record.get('category', ''), str)
                    or type(record.get('order', 0)) not in (int, float)
                    or not isinstance(record.get('aliases', []), list)
                    or not all(isinstance(alias, str) for alias in record.get('aliases', []))
                    or (member_key in record and not isinstance(record[member_key], str))):
                raise ContentError('Invalid episode entry in content library manifest')
            seen.add(record['id'])
        from .episode_catalog import EpisodeCatalog
        self.catalog = EpisodeCatalog.from_data(m.get('episode_catalog', []))
        if 'store' in m and (getattr(GAMES[self.game_id], 'STORE_FILENAME', None) is None
                             or not isinstance(m['store'], dict) or not isinstance(m['store'].get('sha256'), str)
                             or m['store'].get('file') != f"content/{m['store']['sha256']}.json"
                             or not re.fullmatch('[0-9a-f]{64}', m['store']['sha256'])):
            raise ContentError('Invalid store listing in the content library manifest')
        self._store = None
        path = self._content_file(m[self.kind], '.' + self.kind)
        try:
            self.package = ZipFile(path)
            # Retain the existing APK API for clients and old test fixtures.
            self.apk = self.package
            if self.kind == 'ipa':
                self.app_root, self.app_info, profile = _inspect_ipa(self.package)
                if _ipa_game(self.app_info['CFBundleIdentifier']) != self.game_id:
                    raise ContentError('IPA game does not match the library profile')
                if profile != self.profile:
                    # shshd-runtime 1.0.x recorded every CoD library under the paid layout, the free editions' too
                    # (assets.logical_members reads members by content), so such a library opens under the layout
                    # its IPA actually has. library.json is left as it is.
                    legacy = (self.game_id == 'cod' and self.profile == GAMES['cod'].PAID_PROFILE
                              and profile != self.profile)
                    if not legacy:
                        raise ContentError('IPA asset layout does not match the library profile')
                    self.profile = profile
                self.asset_root = self.app_root + 'res_generated/'
            else:
                native_hash = _inspect_apk(self.package)
                self.app_root = self.asset_root = 'assets/Assets/'
            if self.kind == 'apk' and native_hash != m[self.kind].get('native_sha256'):
                raise ContentError('Native profile hash does not match the library manifest')
            for record in m['episodes']:
                if member_key in record:
                    member = record[member_key]
                    relative = member.removeprefix(self.app_root)
                    if (not member.startswith(self.app_root) or '/' in relative
                            or not relative.lower().endswith('.exp')):
                        raise ContentError('Invalid bundled episode path')
        except (BadZipFile, ContentError) as error:
            if hasattr(self, 'apk'):
                self.apk.close()
            raise ContentError(f'Invalid imported {self.kind.upper()}: {error}') from error
        self.episodes = m['episodes']
        self.base_members = _resource_members(self.apk.namelist(), self.asset_root, self.game_id)
        self._android_resource_cache = {}
        for name in self.apk.namelist() if self.kind == 'apk' else ():
            if re.fullmatch(r'assets/Assets/audio/(music/[1-9][0-9]*\.mp3|sfx/[1-9][0-9]*\.wav)', name):
                stem = Path(name).stem
                self.base_members.setdefault(int(stem), name)
        # FUN_0004b4fc appends .mp3 to these six resource names. The suffix
        # does not identify an audio stream: resource 16 is an image pack.
        for resource_id in (16, 290, 446, 496, 499, 502) if self.kind == 'apk' else ():
            name = f'assets/Assets/{resource_id}.mp3'
            if name in self.apk.namelist():
                self.base_members[resource_id] = name
        self.music_apk, self.music_members = None, {}
        if 'music_apk' in m:
            try:
                self.music_apk = ZipFile(self._content_file(m['music_apk'], '.apk'))
                if _inspect_apk(self.music_apk) != m['music_apk'].get('native_sha256'):
                    raise ContentError('Music APK native profile does not match the library manifest')
                self.music_members = _apk_music_members(self.music_apk, self.base_members)
            except (BadZipFile, ContentError, OSError) as error:
                self.close()
                raise ContentError(f'Invalid imported music APK: {error}') from error
        # Higher-density art for standard episodes (hd_twins.py): 'off', 'twins' or 'fill'. 'fill' is the only
        # mode a player reaches through the app itself (there is no in-game toggle for this); 'off'/'twins'
        # stay reachable only through SHS_HD_ART or a hand-edited player.json, for this project's own testing.
        self.hd_art_mode = os.environ.get('SHS_HD_ART', 'fill')
        # shshd-runtime: translated New Rules episodes carry two portrait sets; True shows the X1i jar's redrawn,
        # higher-resolution ones (the game profile's TRANSLATED_PORTRAIT_ART), False New Rules' WinMo ones.
        self.hires_portraits = True
        self._twins = None
        self.hd_ipa, self.hd_members = None, {}
        self._hd_resource_cache = {}
        if 'hd_ipa' in m:
            try:
                self.hd_ipa = ZipFile(self._content_file(m['hd_ipa'], '.ipa'))
                if _inspect_hd_ipa(self.hd_ipa) != m['hd_ipa'].get('executable_sha256'):
                    raise ContentError('HD executable hash does not match the library manifest')
            except (BadZipFile, ContentError) as error:
                self.close()
                raise ContentError(f'Invalid imported HD ipa: {error}') from error
            for name in self.hd_ipa.namelist():
                relative = name.removeprefix(HD_RESOURCE_PREFIX)
                if name.startswith(HD_RESOURCE_PREFIX) and re.fullmatch(r'(0|[1-9][0-9]*)', relative):
                    self.hd_members[int(relative)] = name
        self.shs_hd_art, self.shs_hd_members, self._shs_hd_cache = None, {}, {}
        if 'shs_hd_art' in m:
            self._open_shs_hd_art(m['shs_hd_art'])

    def _open_shs_hd_art(self, record):
        try:
            art = ZipFile(self._content_file(record, '.ipa'))
            if _inspect_hd_ipa(art) != record.get('executable_sha256'):
                art.close()
                raise ContentError('HD executable hash does not match the library manifest')
        except (BadZipFile, ContentError) as error:
            self.close()
            raise ContentError(f'Invalid imported SHS HD art source: {error}') from error
        self.shs_hd_art = art
        self.shs_hd_members = {int(name.removeprefix(HD_RESOURCE_PREFIX)): name for name in art.namelist()
                               if name.startswith(HD_RESOURCE_PREFIX)
                               and re.fullmatch(r'(0|[1-9][0-9]*)', name.removeprefix(HD_RESOURCE_PREFIX))}

    def shs_hd_resource(self, resource_id):
        """A resource of the SHS HD bundle linked to a CoD library as an art source, or None."""
        if resource_id not in self.shs_hd_members:
            return None
        if resource_id not in self._shs_hd_cache:
            self._shs_hd_cache[resource_id] = _zip_read(self.shs_hd_art, self.shs_hd_members[resource_id])
        return self._shs_hd_cache[resource_id]

    def cod_hd_common(self) -> bytes | None:
        """CoD's common frames at HD density (cod/hd_art.COMMON_FRAMES): SHS HD's pack 155 with those frames in
        CoD's look. None unless this is a CoD library with the SHS HD art source linked. Deliberately not served as
        hd_asset(155), which would switch on SHS HD's own screens and behaviour."""
        if self.game_id != 'cod' or self.shs_hd_art is None:
            return None
        hd = self.shs_hd_resource(155)
        if hd is None:
            return None
        from .cod.hd_art import derived_common
        return derived_common(self.android_asset(126), hd)

    def add_shs_hd_art(self, source: Path) -> bool:
        """Link the SHS HD (iPad) IPA to a CoD library as its HD art source, transactionally (cod/hd_art.py)."""
        source = Path(source)
        if self.game_id != 'cod':
            raise ContentError('Only a Cause of Death library takes the SHS HD IPA as an art source')
        with tempfile.TemporaryDirectory(prefix='.exp-import-', dir=self.directory) as temporary:
            copied = Path(temporary) / 'shs-hd.ipa'
            shutil.copyfile(source, copied)
            sha = file_digest(copied)
            try:
                with ZipFile(copied) as ipa:
                    executable = _inspect_hd_ipa(ipa)
            except BadZipFile as error:
                raise ContentError('The supplied SHS HD IPA is not a valid ZIP archive') from error
            record = dict(file=f'content/{sha}.ipa', sha256=sha, executable_sha256=executable)
            current = json.loads((self.directory / 'library.json').read_text(encoding='utf-8'))
            if current != self.manifest:
                raise ContentError('The library changed during import; reopen it and try again')
            if self.manifest.get('shs_hd_art') == record:
                return False
            updated = dict(self.manifest, shs_hd_art=record)
            manifest_path = Path(temporary) / 'library.json'
            manifest_path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            copied.replace(self.directory / record['file'])
            manifest_path.replace(self.directory / 'library.json')
        if self.shs_hd_art is not None:
            self.shs_hd_art.close()
        self.manifest = updated
        self._open_shs_hd_art(record)
        return True

    def twin_store(self):
        """The library's HD twin store (empty until `tools/build_hd_twins.py` fills it)."""
        if self._twins is None:
            from .hd_twins import TwinStore
            self._twins = TwinStore(self.directory)
        return self._twins

    def hd_app_version(self) -> str | None:
        """The HD bundle's `CFBundleVersion` (SHSEngine::getAppVersionString), or None without one."""
        if self.hd_ipa is None:
            return None
        for name in self.hd_ipa.namelist():
            if name.startswith('Payload/') and name.endswith('.app/Info.plist') and name.count('/') == 2:
                try:
                    return str(plistlib.loads(self.hd_ipa.read(name)).get('CFBundleVersion', ''))
                except (plistlib.InvalidFileException, ValueError):
                    return None
        return None

    def app_icon(self):
        if self.kind == 'ipa':
            try:
                info = plistlib.loads(_zip_read(self.package, self.app_root + 'Info.plist'))
            except (ContentError, ValueError, TypeError, OverflowError, ExpatError):
                return None
            listed = [info.get('CFBundleIconFile'), *info.get('CFBundleIconFiles', ())]
            for icons in (info.get('CFBundleIcons'), info.get('CFBundleIcons~ipad')):
                if isinstance(icons, dict) and isinstance(icons.get('CFBundlePrimaryIcon'), dict):
                    listed += icons['CFBundlePrimaryIcon'].get('CFBundleIconFiles', ())
            stems = {name.removesuffix('.png') for name in listed if isinstance(name, str) and name}
            wanted = {self.app_root + stem + suffix for stem in stems for suffix in ('.png', '@2x.png')}
            members = [name for name in self.package.namelist() if name in wanted]
        else:
            members = [name for name in self.package.namelist()
                       if re.fullmatch(r'res/drawable[a-z-]*/icon\.png', name)]
        from .cgbi import CgBIError, decode
        best = None
        for name in sorted(members):
            try:
                image = decode(_zip_read(self.package, name))
            except (CgBIError, ContentError):
                continue
            if best is None or image.width * image.height > best.width * best.height:
                best = image
        return best

    def hd_asset(self, resource_id: int) -> bytes | None:
        """The verified HD-native equivalent of a low-id asset, if an HD app
        bundle was imported. Two disjoint cases: HD_ASSET_MAP is a small,
        individually-verified table for chrome ids below the shared-content
        range (renumbered or reformatted on HD, so never trusted by number
        alone); ids inside HD_SHARED_CONTENT_RANGE are per-scene content
        that ships at the same id on both platforms, trusted directly. See
        the comments on both constants. None otherwise -- always optional;
        callers must keep working from the base package alone.
        """
        if self.game_id == 'cod':
            # Only CoD's own verified map, from the SHS HD art source (cod/hd_art.py); nothing by number alone.
            if self.shs_hd_art is None:
                return None
            from .cod.hd_art import IDENTICAL, SKIN_PACKS, derived_pack
            if resource_id in SKIN_PACKS:
                hd = self.shs_hd_resource(SKIN_PACKS[resource_id])
                return None if hd is None else derived_pack(self.android_asset(resource_id), hd)
            if resource_id in IDENTICAL:
                return self.shs_hd_resource(IDENTICAL[resource_id])
            return None
        if resource_id in HD_SHARED_CONTENT_RANGE:
            hd_id = resource_id
        else:
            hd_id = HD_ASSET_MAP.get(resource_id)
        if hd_id is None or hd_id not in self.hd_members:
            return None
        return self._cached_hd_read(hd_id)

    def hd_raw_resource(self, resource_id: int) -> bytes | None:
        """An HD app bundle resource by its exact id, with no Android
        counterpart implied -- e.g. the embedded TrueType fonts (568 is
        Pajama Hip). None when no HD bundle was imported or it lacks the id."""
        if resource_id not in self.hd_members:
            return None
        return self._cached_hd_read(resource_id)

    def _cached_hd_read(self, hd_id: int) -> bytes:
        """`hd_id`'s bytes from the HD ipa, decompressed once and kept for the life of this library: the ipa's
        own content never changes mid-session, but callers that only check a resource's presence (an
        `available()` gate re-evaluated every frame, e.g. `HdFootballRenderer.available()`) would otherwise
        re-read and re-`zlib`-decompress it from the zip archive on every single call."""
        if hd_id not in self._hd_resource_cache:
            self._hd_resource_cache[hd_id] = _zip_read(self.hd_ipa, self.hd_members[hd_id])
        return self._hd_resource_cache[hd_id]

    def _content_file(self, record: dict, suffix: str) -> Path:
        sha = record.get('sha256')
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
            raise ContentError('Invalid content hash in library')
        expected = f'content/{sha}{suffix}'
        if record.get('file') != expected:
            raise ContentError('Invalid content path in library')
        path = self.directory / expected
        try:
            actual = file_digest(path)
        except OSError as error:
            raise ContentError(f'Cannot read imported content: {error}') from error
        if actual != sha:
            raise ContentError(f'Imported content changed: {path.name}')
        return path

    def select(self, selector: str) -> dict:
        if len(selector) == 64:
            # A whole ID (IDs are content hashes): the menus look up every episode's saves this way each time they
            # refresh, so the full scan below (prefixes, names, titles, aliases) is kept for other selectors.
            exact = next((e for e in self.episodes if e['id'] == selector), None)
            if exact is not None:
                return exact
        matches = [e for e in self.episodes if e['id'].startswith(selector)
                   or e['name'] == selector or (selector.strip() and selector in e['titles'])
                   or selector.casefold() in [alias.casefold() for alias in e.get('aliases', [])]]
        if len(matches) != 1:
            raise ContentError(f'Episode selector {selector!r} matched {len(matches)} episodes; use a unique ID from list')
        return matches[0]

    def open_episode(self, selector: str):
        record = self.select(selector)
        return EpisodeResources(self, record, ExpArchive(self.episode_bytes(record)))

    def episode_bytes(self, record: dict) -> bytes:
        """An episode's EXP file as it was imported (from the library's content, or the game package it ships in)."""
        if self.kind + '_member' in record:
            data = _zip_read(self.package, record[self.kind + '_member'])
        else:
            data = self._content_file(record, '.exp').read_bytes()
        if digest(data) != record['sha256']:
            raise ContentError('Episode content does not match its imported hash')
        return data

    def remove_episodes(self, ids) -> int:
        """Take episodes out of the library (Delete Episodes): a new manifest without them, then their content files.
        Built-in episodes, and those inside the game's package, stay (the next open would list them again). Returns
        how many went."""
        ids = set(ids)
        gone = [e for e in self.episodes if e['id'] in ids and 'file' in e and not e.get('builtin')]
        if not gone:
            return 0
        current = json.loads((self.directory / 'library.json').read_text(encoding='utf-8'))
        if current != self.manifest:
            raise ContentError('The library changed since it was opened; reopen it and try again')
        updated = dict(self.manifest, episodes=[e for e in self.episodes if e not in gone])
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.directory, prefix='.library-',
                                         suffix='.json', delete=False) as stream:
            stream.write(json.dumps(updated, indent=2, ensure_ascii=False) + '\n')
        Path(stream.name).replace(self.directory / 'library.json')
        self.manifest, self.episodes = updated, updated['episodes']
        for record in gone:
            (self.directory / record['file']).unlink(missing_ok=True)
        return len(gone)

    def read_ui_asset(self, name: str) -> bytes:
        """Read an exact named UI asset, separately from numeric EXP resources.

        Descriptors refer to atlases by filename. Keep those references in
        their APK namespace; never resolve them against the host filesystem.
        """
        if (not isinstance(name, str)
                or not re.fullmatch(r'(fonts|images)/[A-Za-z0-9_][A-Za-z0-9_.-]*', name)):
            raise ContentError(f'Invalid named UI asset: {name!r}')
        if self.kind == 'ipa':
            raise ContentError(f'IPA has no named UI asset {name}; its text uses installed system fonts')
        return _zip_read(self.package, self.asset_root + name)

    def read_ui_resource(self, role: int) -> bytes:
        """Resolve a host UI role without changing script-visible numeric IDs."""
        if self.game_id == 'cod':
            from .cod.assets import ui_resource
            return ui_resource(self, role)
        if self.kind == 'ipa':
            from .shs.ios_assets import ui_resource
            return ui_resource(self, role)
        return self.read_asset(role)

    def read_asset(self, resource_id: int) -> bytes:
        """Read the base package bank without opening an episode -- upgraded
        transparently to the HD ipa's own bytes where hd_asset() has a verified
        correspondence (never required; see its docstring).
        """
        hd_data = self.hd_asset(resource_id)
        if hd_data is not None:
            return hd_data
        return self.android_asset(resource_id)

    def android_asset(self, resource_id: int) -> bytes:
        """The base package's own bytes for a resource id (the APK, or a base-game
        IPA), bypassing any HD substitution. Needed by small UI chrome (icons,
        badges) that has no scale compensation of its own: unlike backgrounds and
        portraits, which are meant to gain real extra density and explicitly
        compensate for it (see desktop_dialogue.py's ANDROID_MASK_SIZE), these
        assets must keep their original apparent size no matter which density
        actually decoded -- see Desktop._chrome_image. Cached: the package never
        changes while open.
        """
        if resource_id not in self._android_resource_cache:
            try:
                data = _zip_read(self.apk, self.base_members[resource_id])
            except KeyError:
                if resource_id not in self.music_members:
                    raise ContentError(f'{self.kind.upper()} resource {resource_id} is missing') from None
                data = _zip_read(self.music_apk, self.music_members[resource_id])
            self._android_resource_cache[resource_id] = data
        return self._android_resource_cache[resource_id]

    @property
    def missing_music_ids(self):
        if (self.game_id, self.kind) != ('shs', 'ipa'):
            return ()
        return tuple(resource for resource in GAMES['shs'].DOWNLOADED_MUSIC
                     if resource not in self.base_members and resource not in self.music_members)

    def add_music_apk(self, source: Path) -> int:
        """Attach optional music transactionally, preserving IPA assets and saves.

        Only the verified iOS download IDs are exposed. Android fonts, UI,
        scripts, episodes and other resources never enter the IPA's banks.
        """
        source = Path(source)
        if (self.game_id, self.kind) != ('shs', 'ipa'):
            raise ContentError('An optional music APK can only supplement an SHS IPA library')
        if source.suffix.lower() != '.apk':
            raise ContentError('Choose your SHS Android 1.0.9 APK for missing music')
        if not self.missing_music_ids:
            return 0
        with tempfile.TemporaryDirectory(prefix='.exp-import-', dir=self.directory) as temporary:
            stage = Path(temporary)
            copied = stage / 'music.apk'
            shutil.copyfile(source, copied)
            sha = file_digest(copied)
            try:
                with ZipFile(copied) as apk:
                    native = _inspect_apk(apk)
                    members = _apk_music_members(apk, self.base_members)
            except BadZipFile as error:
                raise ContentError('The supplied music APK is not a valid ZIP archive') from error
            record = dict(file=f'content/{sha}.apk', sha256=sha, native_sha256=native)
            current = json.loads((self.directory / 'library.json').read_text(encoding='utf-8'))
            if current != self.manifest:
                raise ContentError('The library changed during import; reopen it and try again')
            version = 3 if self.manifest['format'] == 'shs-content-library' else 1
            updated = dict(self.manifest, version=version, music_apk=record)
            manifest_path = stage / 'library.json'
            manifest_path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            target = self.directory / record['file']
            existed = target.exists()
            copied.replace(target)
            retained = None
            try:
                retained = ZipFile(target)
                manifest_path.replace(self.directory / 'library.json')
            except BaseException:
                if retained is not None:
                    retained.close()
                if not existed:
                    target.unlink(missing_ok=True)
                raise
            self.manifest, self.music_apk, self.music_members = updated, retained, members
            return len(members)

    def add_episodes(self, paths: list[Path]) -> int:
        """Validate a batch before atomically publishing an expanded manifest.

        Content is copied under its hash; existing content and saves are never
        replaced. Duplicate filenames become aliases for catalog matching. A
        failed validation leaves the entire library unchanged. A store listing
        (CoD's mtxprods) in the batch replaces the library's.
        """
        with _episode_inputs(paths, game=self.game_id) as (candidates, catalog):
            store = _store_listing(paths, game=self.game_id)
            if not candidates and not catalog.entries and store is None:
                raise ContentError('No EXP episodes found in the selected files, ZIPs, RARs or folders')
            return self._install_episodes(((path.read_bytes(), path.name, {}) for path in candidates), catalog=catalog,
                                          store=store)

    def store_listing(self):
        """The imported store listing (CoD's mtxprods products, cod/store.py) as data, or None."""
        record = self.manifest.get('store')
        if record is None:
            return None
        if self._store is None:
            data = (self.directory / record['file']).read_bytes()
            if digest(data) != record['sha256']:
                raise ContentError('The library\'s store listing does not match its manifest')
            self._store = json.loads(data.decode('utf-8'))
        return self._store

    def unindexed(self) -> list:
        """Episodes imported before the picker existed (no script signature), or whose release an older
        `image_variant` left undecided (it read widths only: HD art narrower than 256 told nothing)."""
        from .episode_index import INDEX_VERSION
        return [r for r in self.episodes if 'signature' not in r
                or (r.get('variant') is None and r.get('index', 1) < INDEX_VERSION)]

    def index_missing(self) -> int:
        """Give `unindexed()` episodes their release and script signature.

        Published atomically like an import; a library another importer changed meanwhile is left for next time.
        """
        missing = self.unindexed()
        if not missing:
            return 0
        updated = {}
        for record in missing:
            resources = self.open_episode(record['id'])
            updated[record['id']] = dict(record, **episode_index_fields(resources.archive, resources.programs))
        current = json.loads((self.directory / 'library.json').read_text(encoding='utf-8'))
        if current != self.manifest:
            raise ContentError('The library changed while indexing; reopen it and try again')
        episodes = [updated.get(r['id'], r) for r in self.episodes]
        manifest = dict(self.manifest, episodes=episodes)
        with tempfile.TemporaryDirectory(prefix='.exp-import-', dir=self.directory) as temporary:
            staged = Path(temporary) / 'library.json'
            staged.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            staged.replace(self.directory / 'library.json')
        self.manifest, self.episodes = manifest, episodes
        return len(updated)

    def ensure_builtin_episodes(self) -> int:
        """Upgrade a library using its retained game package, once per story. SHS's Football Star follows the HD
        (iPad) bundle when an APK library has one (its scripts have Faceplace and Decision Tree support), so a
        library that gained or lost the ipa swaps its copy; progress in the old copy stays in its own save files."""
        profile = GAMES[self.game_id]
        existing = [e for e in self.episodes if e.get('builtin') == profile.BUILTIN]
        if self.game_id == 'shs' and self.kind == 'apk':
            from .shs.builtin_episode import hd_scripts_available
            wanted = hd_scripts_available(self.hd_ipa)
            if existing and all(bool(e.get('hd_scripts')) == wanted for e in existing):
                return 0
            record = profile.extract_builtin(self.package, self.asset_root, ios=False, hd_ipa=self.hd_ipa)
            if record is None:
                return 0
            return self._install_episodes([record], drop={e['id'] for e in existing})
        if existing:
            return 0
        record = profile.extract_builtin(self.package, self.asset_root, ios=self.kind == 'ipa')
        if record is None:
            return 0
        return self._install_episodes([record])

    def restore_builtin_episodes(self) -> int:
        """Write a built-in episode's missing content file again from the retained game package (Verify Library);
        returns how many came back. Only the copy the library already lists is restored (its checksum must match)."""
        profile = GAMES[self.game_id]
        lost = [e for e in self.episodes if e.get('builtin') == profile.BUILTIN and 'file' in e
                and not (self.directory / e['file']).is_file()]
        if not lost:
            return 0
        hd = dict(hd_ipa=self.hd_ipa) if self.game_id == 'shs' and self.kind == 'apk' else {}
        record = profile.extract_builtin(self.package, self.asset_root, ios=self.kind == 'ipa', **hd)
        if record is None or digest(record[0]) not in {e['id'] for e in lost}:
            return 0
        self._install_episodes([record])
        return sum(1 for e in lost if (self.directory / e['file']).is_file())

    def _install_episodes(self, episodes, *, catalog=None, drop=(), store=None) -> int:
        records = {e['id']: e for e in self.episodes if e['id'] not in drop}
        catalog = self.catalog.merge(catalog) if catalog is not None else self.catalog
        with tempfile.TemporaryDirectory(prefix='.exp-import-', dir=self.directory) as temporary:
            stage = Path(temporary)
            additions, repairs, repaired = [], [], set()
            listed = {record['id'] for record in self.episodes}     # in the library before this batch
            for data, name, source in episodes:
                sha = digest(data)
                if sha in records:
                    records[sha] = _with_episode_alias(records[sha], name)
                    if (sha in listed and sha not in repaired and 'file' in records[sha]
                            and not (self.directory / records[sha]['file']).is_file()):
                        # Its file went missing (Verify Library removes a damaged one): this copy restores it.
                        (stage / (sha + '.exp')).write_bytes(data)
                        repairs.append(records[sha])
                        repaired.add(sha)
                    continue
                archive = ExpArchive(data)
                meta, programs = archive.metadata(), archive.programs()
                if not programs:
                    raise ContentError(f'No KiWi scripts in {name}')
                record = dict(id=sha, sha256=sha, name=name, pack_id=meta.pack_id,
                              episode_id=meta.episode_id, titles=list(meta.titles),
                              scripts=sorted(programs), file=f'content/{sha}.exp', **source,
                              **episode_index_fields(archive, programs))
                record.update(legacy_fields(record['titles'], self.game_id, meta.episode_id))
                (stage / (sha + '.exp')).write_bytes(data)
                records[sha] = record
                additions.append(record)
            store_sha = digest(store) if store is not None else None
            for record in repairs:
                (stage / (record['id'] + '.exp')).replace(self.directory / record['file'])
            if (not additions and not drop and list(records.values()) == self.episodes
                    and catalog.entries == self.catalog.entries
                    and (store is None or self.manifest.get('store', {}).get('sha256') == store_sha)):
                return 0
            # Refuse to lose additions made by another importer since we opened.
            current = json.loads((self.directory / 'library.json').read_text(encoding='utf-8'))
            if current != self.manifest:
                raise ContentError('The library changed during import; reopen it and try again')
            updated = dict(self.manifest, episodes=list(records.values()))
            if catalog.entries:
                updated['episode_catalog'] = catalog.to_data()
            if store is not None:
                (stage / f'{store_sha}.json').write_bytes(store)
                updated['store'] = dict(file=f'content/{store_sha}.json', sha256=store_sha)
            manifest_path = stage / 'library.json'
            manifest_path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            for record in additions:
                (stage / (record['id'] + '.exp')).replace(self.directory / record['file'])
            if store is not None:
                (stage / f'{store_sha}.json').replace(self.directory / updated['store']['file'])
            manifest_path.replace(self.directory / 'library.json')
            self.manifest, self.episodes = updated, updated['episodes']
            self._store = None
            self.catalog = catalog
            return len(additions)

    def close(self):
        self.apk.close()
        if self.music_apk is not None:
            self.music_apk.close()
        if getattr(self, 'hd_ipa', None) is not None:
            self.hd_ipa.close()
        if getattr(self, 'shs_hd_art', None) is not None:
            self.shs_hd_art.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# shshd-runtime: the game profile's table holding each presentation feature for the translated packs, and how its
# entry becomes the episode record's form (presentation.normalize). Portrait effects there name the first image.
PRESENTATION_TABLES = dict(duet=('TRANSLATED_DUETS', tuple), narration_theme=('TRANSLATED_NARRATION_THEMES', int),
                           portrait_effects=('TRANSLATED_PORTRAIT_EFFECTS',
                                             lambda spec: (spec[0], tuple(range(spec[1], spec[1] + EFFECTS)))),
                           music_loops=('TRANSLATED_MUSIC_LOOPS', dict))


def presentation_feature(resources, name):
    """shshd-runtime: an episode's setting for a presentation feature (presentation.MEMBERS), in the record's form, or
    None. The game profile's table for the episode's pack comes first (the translations: New Rules 31300, the X360
    prototype 31400); any other episode uses its own declaration (resource 3) where the profile accepts one
    (PRESENTATION_RECORD)."""
    record = getattr(resources, 'record', None) or {}
    profile = GAMES.get(game_id(resources))
    table, convert = PRESENTATION_TABLES[name]
    value = getattr(profile, table, {}).get(record.get('pack_id'))
    if value is not None:
        return convert(value)
    if not getattr(profile, 'PRESENTATION_RECORD', False):
        return None
    return (getattr(resources, 'presentation', None) or {}).get(name)


class EpisodeResources:
    def __init__(self, library: ContentLibrary, record: dict, archive: ExpArchive):
        self.library, self.record, self.archive = library, record, archive
        self.programs = archive.programs()
        self._presentation = False

    @property
    def presentation(self):
        """shshd-runtime: the episode's declared presentation features (resource 3, presentation.normalize), {} for
        none. A malformed record is set aside with a warning: the episode plays as SHS shows it."""
        if self._presentation is False:
            try:
                self._presentation = presentation_record(self.archive) or {}
            except ContentError as error:
                logging.warning('%s: %s', self.record.get('name', 'episode'), error)
                self._presentation = {}
        return self._presentation

    @property
    def identity(self):
        # Optional music is presentation-only: attaching it must not invalidate
        # an existing IPA checkpoint. Both source archives are still hashed and
        # checked on open; script/layout/font identities stay with the IPA.
        return dict(profile=self.library.profile, episode_sha256=self.record['sha256'],
                    **{self.library.kind + '_sha256': self.library.manifest[self.library.kind]['sha256']})

    def same_content(self, content) -> bool:
        """Whether a save's `content` is this episode's. A CoD library from shshd-runtime 1.0.x is recorded under the paid
        layout and opens under its IPA's own (ContentLibrary.__init__), so the saves made before carry the recorded
        profile with the same IPA and episode."""
        if content == self.identity:
            return True
        recorded = getattr(self.library, 'recorded_profile', self.library.profile)
        return recorded != self.library.profile and content == dict(self.identity, profile=recorded)

    def read_ui_resource(self, role: int) -> bytes:
        return self.library.read_ui_resource(role)

    def exists(self, resource_id: int) -> bool:
        # FUN_00082bc0 selects the episode bank at 26000 for art resources.
        if resource_id >= 26000:
            return resource_id in self.archive.entries
        return resource_id in self.library.base_members or resource_id in self.library.music_members

    def read_asset(self, resource_id: int) -> bytes:
        hires = self._hires_portrait(resource_id)
        if hires is not None:
            return self.archive.read(hires)     # already HD-sized: no twin store fill on top
        if resource_id >= 26000:
            data = self.archive.read(resource_id)
        else:
            # A verified HD-native upgrade (ContentLibrary.hd_asset) always wins outright and is returned as-is:
            # it is already HD, so running it through the twin store below too would upscale it a second time.
            hd_data = self.library.hd_asset(resource_id)
            if hd_data is not None:
                return hd_data
            data = self.library.android_asset(resource_id)
        mode = self.library.hd_art_mode
        if mode != 'off' and self.record.get('variant') == 'standard':
            return self.library.twin_store().art(data, mode)      # the HD release's picture, or a 2x fill
        if mode != 'off' and getattr(self.library, 'game_id', None) == 'cod':
            # Cause of Death: the SHS HD picture a background is (cod/hd_twins.py), never a 2x fill.
            twin = self.library.twin_store().twin(data)
            if twin is not None:
                return twin
        return data

    def standard_portrait(self, resource_id):
        """The episode's own portrait (raw bytes) that `read_asset`'s hi-res copy stands in for, so the player can
        show the copy at the size the original fills; None when `read_asset` returns no hi-res copy."""
        return None if self._hires_portrait(resource_id) is None else self.raw_asset(resource_id)

    def _hires_portrait(self, resource_id):
        """shshd-runtime: the resource holding the hi-res copy of a translated episode's portrait, when the player
        wants them (library.hires_portraits) and the episode has one: the game profile's TRANSLATED_PORTRAIT_ART,
        pack -> (first, end, offset), moves portraits in [first, end) by offset. Else None."""
        if not getattr(self.library, 'hires_portraits', False):
            return None
        profile = GAMES.get(getattr(self.library, 'game_id', None))
        span = getattr(profile, 'TRANSLATED_PORTRAIT_ART', {}).get(self.record.get('pack_id'))
        if span is None or not span[0] <= resource_id < span[1]:
            return None
        hires = resource_id + span[2]
        return hires if hires in self.archive.entries else None

    def raw_asset(self, resource_id: int) -> bytes:
        """The episode's own bytes, never substituted (what the twin store is built from). `library.read_asset`
        is not used here for a low id: it silently prefers a verified HD-native upgrade when one is imported
        (ContentLibrary.hd_asset), which is a different, unrelated substitution this must stay clear of."""
        if resource_id >= 26000:
            return self.archive.read(resource_id)
        return self.library.android_asset(resource_id)

    def hd_asset(self, resource_id: int) -> bytes | None:
        return self.library.hd_asset(resource_id)

    def android_asset(self, resource_id: int) -> bytes:
        return self.library.android_asset(resource_id)

    def program(self, resource_id: int):
        if resource_id not in self.programs:
            # Engine script loading and image-bank selection are different
            # paths: episode scripts in the 25000 range take precedence here.
            try:
                self.programs[resource_id] = decode_program(self.read_asset(resource_id))
            except ValueError as error:
                raise ContentError(f'Cannot load script {resource_id}: {error}') from error
        return self.programs[resource_id]

    @lru_cache(maxsize=1)
    def dialogue_layout(self):
        from .dialogue import DialogueLayout
        return DialogueLayout(self)
