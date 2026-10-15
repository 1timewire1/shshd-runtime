"""User-supplied game content, isolated from the distributable runtime.

APKs, IPAs and episode ZIPs/RARs are opened as data only. No supplied native code
is executed, and archive paths are never used as output paths. Imported files use
content-derived names.
"""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
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
from .games import COD_IOS, GAMES, PROFILES, SHS_ANDROID, SHS_IOS


PROFILE = SHS_ANDROID
IOS_PROFILE = SHS_IOS
MAX_EPISODE_ZIP_MEMBERS = 10_000
MAX_EPISODE_ZIP_BYTES = 2 * 1024 * 1024 * 1024


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


def file_digest(path: Path) -> str:
    with path.open('rb') as stream:
        result = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
        return result.hexdigest()



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
    game = _ipa_game(identifier)
    if game == 'cod':
        from .cod.profile import profile_for
        profile = profile_for(lambda resource: _zip_read(
            package, root + 'res_generated/' + str(resource)))
    else:
        from .shs.ios_assets import validate_assets
        validate_assets(lambda resource: _zip_read(package, root + 'res_generated/' + str(resource)))
        profile = IOS_PROFILE
    # Version fields are informative. Source identity is the complete
    # archive hash, including repacks or differently encrypted executables.
    details = {key: info[key] for key in ('CFBundleIdentifier', 'CFBundleShortVersionString', 'CFBundleVersion')
               if isinstance(info.get(key), str)}
    return root, details, profile


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
    episodes, sidecars, checked, checked_archives = {}, {}, set(), set()
    # Keep archives open only for this batch, including validation and rollback.
    # Each EXP is read on demand, so a collection is not loaded into RAM at once.
    with ExitStack() as stack:
        for candidate in paths:
            path = Path(candidate)
            if path.is_dir():
                candidates = sorted(p for p in path.rglob('*') if p.is_file())
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


def _apk_music_members(apk: ZipFile, ipa_members):
    """Verify only the known iOS download bank; IPA bytes always win."""
    members = {}
    for resource in GAMES['shs'].DOWNLOADED_MUSIC:
        if resource not in ipa_members:
            name = f'assets/Assets/audio/music/{resource}.mp3'
            _zip_read(apk, name)  # Validate presence, ZIP integrity and size before publishing.
            members[resource] = name
    return members


def import_game(apk_path: Path, episode_paths: list[Path], destination: Path, *,
                music_apk: Path | None = None, game: str | None = None) -> dict:
    """Create a relocatable library atomically; keep original inputs untouched.

    A failed import leaves no partly usable library. Additional episodes are
    optional because the supplied APK or IPA includes playable episode data.
    The historical ``apk_path`` argument also accepts the supported iOS IPA.
    """
    apk_path, destination = Path(apk_path), Path(destination)
    kind = apk_path.suffix.lower().lstrip('.')
    if kind not in ('apk', 'ipa'):
        raise ContentError('Choose an SHS Android 1.0.9 APK, SHS IPA or Cause of Death IPA')
    if game is not None:
        GAMES[game]
    if music_apk is not None and kind != 'ipa':
        raise ContentError('An optional music APK can only supplement an SHS IPA library')
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
                                    titles=list(meta.titles), scripts=sorted(programs), **location)
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
                built_in = GAMES[source_game].extract_builtin(apk, assets, ios=kind == 'ipa')
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
        manifest = dict(format='exp-content-library', version=1, game=source_game, profile=profile,
                        episodes=list(records.values()))
        manifest[kind] = dict(file=f'content/{apk_hash}.{kind}', sha256=apk_hash,
                              **(dict(app=app_info) if kind == 'ipa' else dict(native_sha256=native_hash)))
        if catalog.entries:
            manifest['episode_catalog'] = catalog.to_data()
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
        self.profile = m['profile']
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
                    or not isinstance(record.get('aliases', []), list)
                    or not all(isinstance(alias, str) for alias in record.get('aliases', []))
                    or (member_key in record and not isinstance(record[member_key], str))):
                raise ContentError('Invalid episode entry in content library manifest')
            seen.add(record['id'])
        from .episode_catalog import EpisodeCatalog
        self.catalog = EpisodeCatalog.from_data(m.get('episode_catalog', []))
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
                    raise ContentError('IPA asset layout does not match the library profile')
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
        self.base_members = {}
        # Only native resource locations participate. UI atlas names such as
        # images/1.png are not aliases of global resource 1.
        for name in self.apk.namelist():
            relative = name.removeprefix(self.asset_root)
            if name.startswith(self.asset_root) and re.fullmatch(r'(0|[1-9][0-9]*)', relative):
                self.base_members[int(relative)] = name
        if self.game_id == 'cod':
            from .cod.profile import translate_members
            self.base_members = translate_members(self.profile, self.base_members)
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
        matches = [e for e in self.episodes if e['id'].startswith(selector)
                   or e['name'] == selector or (selector.strip() and selector in e['titles'])
                   or selector.casefold() in [alias.casefold() for alias in e.get('aliases', [])]]
        if len(matches) != 1:
            raise ContentError(f'Episode selector {selector!r} matched {len(matches)} episodes; use a unique ID from list')
        return matches[0]

    def open_episode(self, selector: str):
        record = self.select(selector)
        if self.kind + '_member' in record:
            data = _zip_read(self.package, record[self.kind + '_member'])
        else:
            data = self._content_file(record, '.exp').read_bytes()
        if digest(data) != record['sha256']:
            raise ContentError('Episode content does not match its imported hash')
        return EpisodeResources(self, record, ExpArchive(data))

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
        """Read the base package bank without opening an episode."""
        try:
            return _zip_read(self.apk, self.base_members[resource_id])
        except KeyError:
            if resource_id in self.music_members:
                return _zip_read(self.music_apk, self.music_members[resource_id])
            raise ContentError(f'{self.kind.upper()} resource {resource_id} is missing') from None

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
        failed validation leaves the entire library unchanged.
        """
        with _episode_inputs(paths, game=self.game_id) as (candidates, catalog):
            if not candidates and not catalog.entries:
                raise ContentError('No EXP episodes found in the selected files, ZIPs, RARs or folders')
            return self._install_episodes(((path.read_bytes(), path.name, {}) for path in candidates), catalog=catalog)

    def ensure_builtin_episodes(self) -> int:
        """Upgrade a library using its retained game package, once per story."""
        profile = GAMES[self.game_id]
        if any(e.get('builtin') == profile.BUILTIN for e in self.episodes):
            return 0
        record = profile.extract_builtin(self.package, self.asset_root, ios=self.kind == 'ipa')
        if record is None:
            return 0
        return self._install_episodes([record])

    def _install_episodes(self, episodes, *, catalog=None) -> int:
        records = {e['id']: e for e in self.episodes}
        catalog = self.catalog.merge(catalog) if catalog is not None else self.catalog
        with tempfile.TemporaryDirectory(prefix='.exp-import-', dir=self.directory) as temporary:
            stage = Path(temporary)
            additions = []
            for data, name, source in episodes:
                sha = digest(data)
                if sha in records:
                    records[sha] = _with_episode_alias(records[sha], name)
                    continue
                archive = ExpArchive(data)
                meta, programs = archive.metadata(), archive.programs()
                if not programs:
                    raise ContentError(f'No KiWi scripts in {name}')
                record = dict(id=sha, sha256=sha, name=name, pack_id=meta.pack_id,
                              episode_id=meta.episode_id, titles=list(meta.titles),
                              scripts=sorted(programs), file=f'content/{sha}.exp', **source)
                (stage / (sha + '.exp')).write_bytes(data)
                records[sha] = record
                additions.append(record)
            if (not additions and list(records.values()) == self.episodes
                    and catalog.entries == self.catalog.entries):
                return 0
            # Refuse to lose additions made by another importer since we opened.
            current = json.loads((self.directory / 'library.json').read_text(encoding='utf-8'))
            if current != self.manifest:
                raise ContentError('The library changed during import; reopen it and try again')
            updated = dict(self.manifest, episodes=list(records.values()))
            if catalog.entries:
                updated['episode_catalog'] = catalog.to_data()
            manifest_path = stage / 'library.json'
            manifest_path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            for record in additions:
                (stage / (record['id'] + '.exp')).replace(self.directory / record['file'])
            manifest_path.replace(self.directory / 'library.json')
            self.manifest, self.episodes = updated, updated['episodes']
            self.catalog = catalog
            return len(additions)

    def close(self):
        self.apk.close()
        if self.music_apk is not None:
            self.music_apk.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class EpisodeResources:
    def __init__(self, library: ContentLibrary, record: dict, archive: ExpArchive):
        self.library, self.record, self.archive = library, record, archive
        self.programs = archive.programs()

    @property
    def identity(self):
        # Optional music is presentation-only: attaching it must not invalidate
        # an existing IPA checkpoint. Both source archives are still hashed and
        # checked on open; script/layout/font identities stay with the IPA.
        return dict(profile=self.library.profile, episode_sha256=self.record['sha256'],
                    **{self.library.kind + '_sha256': self.library.manifest[self.library.kind]['sha256']})

    def read_ui_resource(self, role: int) -> bytes:
        return self.library.read_ui_resource(role)

    def exists(self, resource_id: int) -> bool:
        # FUN_00082bc0 selects the episode bank at 26000 for art resources.
        if resource_id >= 26000:
            return resource_id in self.archive.entries
        return resource_id in self.library.base_members or resource_id in self.library.music_members

    def read_asset(self, resource_id: int) -> bytes:
        if resource_id >= 26000:
            return self.archive.read(resource_id)
        return self.library.read_asset(resource_id)

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
