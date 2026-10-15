"""Original episode categories retained in user-supplied native options files.

Game profiles select the verified save envelopes; episode records share the
same wire format. No original catalog ships with the app.
"""
from dataclasses import asdict, dataclass, replace
from pathlib import PurePosixPath
import struct

from .content import ContentError
from .games import GAMES


MAX_ENTRIES = 4096
MAX_CATALOG_BYTES = 4 * 1024 * 1024


def basename(filename):
    # Catalog filenames identify records only. Never open their paths.
    return PurePosixPath(filename.replace('\\', '/')).name.casefold()


@dataclass(frozen=True)
class CatalogEntry:
    pack_id: int
    episode_id: int
    title: str
    category: str
    filename: str
    # 'hd' for the iOS HD build's version-19 catalog, 'standard' for the Android ones, '' for libraries imported
    # before catalogs were told apart.
    source: str = ''

    @property
    def key(self):
        return self.pack_id, self.episode_id, self.title, basename(self.filename), self.source

    def validate(self):
        if (any(type(value) is not int or not 0 <= value <= 65535
                for value in (self.pack_id, self.episode_id))
                or any(not isinstance(value, str) or len(value) > 32767 or '\0' in value
                       for value in (self.title, self.category, self.filename))
                or self.source not in ('', 'hd', 'standard')):
            raise ContentError('Invalid episode catalog entry')


class EpisodeCatalog:
    def __init__(self, entries=()):
        unique = {}
        for entry in entries:
            entry.validate()
            unique[entry.key] = entry
        if len(unique) > MAX_ENTRIES:
            raise ContentError('Episode catalog contains too many entries')
        self.entries = tuple(unique.values())
        self.by_filename, self.by_title = {}, {}
        for entry in self.entries:
            if entry.filename:
                self.by_filename.setdefault(basename(entry.filename), []).append(entry)
            key = entry.pack_id, entry.episode_id, entry.title
            self.by_title.setdefault(key, []).append(entry)

    def merge(self, other):
        return EpisodeCatalog((*self.entries, *other.entries))

    @classmethod
    def from_data(cls, data):
        if not isinstance(data, list) or len(data) > MAX_ENTRIES:
            raise ContentError('Invalid episode catalog in library')
        try:
            return cls(CatalogEntry(**entry) for entry in data)
        except (TypeError, AttributeError) as error:
            raise ContentError('Invalid episode catalog in library') from error

    def to_data(self):
        return [asdict(entry) for entry in self.entries]

    def candidates(self, record, prefer=None, source=None):
        names = {basename(name) for name in (record['name'], *record.get('aliases', []))}
        found = [entry for name in sorted(names) for entry in self.by_filename.get(name, ())]
        if found:
            # A catalog filename can recur in different downloads. Prefer the
            # matching title; filenames still handle native synthetic IDs for
            # the bundled Season 1 and novel entries.
            found = [e for e in found if e.title == record['titles'][0]] or found
        else:
            found = self.by_title.get((record['pack_id'], record['episode_id'], record['titles'][0]), ())
        if prefer:
            # The catalog of the release the episode belongs to wins; another release's only fills gaps.
            own = [e for e in found if e.source in (prefer, '')]
            found = own or found
        if source:
            found = [e for e in found if e.source in (source, '')]
        return list(found)

    def category(self, record, prefer=None, source=None):
        categories = {e.category for e in self.candidates(record, prefer, source) if e.category.strip()}
        return next(iter(categories)) if len(categories) == 1 else None

    def sources(self, record):
        """The releases whose catalog lists this episode."""
        return {e.source for e in self.candidates(record) if e.source}

    def pack_title(self, pack_id):
        """The category of a pack's own season entry (episode ids from 9000 up), e.g. 'A New Start: Season 2'."""
        titles = {e.category for e in self.entries if e.pack_id == pack_id and e.episode_id >= 9000 and e.category.strip()}
        return next(iter(titles)) if len(titles) == 1 else None


class _Reader:
    def __init__(self, data, position):
        self.data, self.position = data, position

    def take(self, count):
        end = self.position + count
        if count < 0 or end > len(self.data):
            raise ContentError('Truncated native episode catalog')
        value = self.data[self.position:end]
        self.position = end
        return value

    def integer(self, format):
        return struct.unpack(format, self.take(struct.calcsize(format)))[0]

    def boolean(self):
        value = self.integer('B')
        if value not in (0, 1):
            raise ContentError('Invalid native catalog presence flag')
        return bool(value)

    def string(self):
        raw = self.take(self.integer('>H'))
        if len(raw) > 32767 or b'\0' in raw:
            raise ContentError('Invalid native catalog string')
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            # Legacy saves contain byte characters in some translated titles.
            # EXP resource 1 remains strictly UTF-8; this is a different format.
            return raw.decode('latin-1')

    def entry(self, alias=False):
        if not self.boolean():
            return None
        pack, episode = self.integer('>H'), self.integer('>H')
        titles = [self.string() for _ in range(5)]
        categories = [self.string() for _ in range(5)]
        filename = self.string()
        if alias:
            self.string()  # iOS HD: plain-text alias/search title, unused here.
        self.integer('>i')  # Native download identifier, not a content hash.
        return CatalogEntry(pack, episode, titles[0], categories[0], basename(filename))

    def catalog(self, trailing_flags):
        current = self.entry()
        count = self.integer('>i')
        if not 0 <= count <= MAX_ENTRIES:
            raise ContentError('Invalid native catalog entry count')
        entries = [self.entry() for _ in range(count)]
        pairs = self.integer('>h')
        if not 0 <= pairs <= MAX_ENTRIES:
            raise ContentError('Invalid native string-pair count')
        for _ in range(pairs * 2):
            self.string()  # Discard native runtime/user strings.
        for _ in range(trailing_flags):
            self.boolean()
        if self.position != len(self.data):
            raise ContentError('Unsupported trailing native options data')
        return EpisodeCatalog(e for e in [current, *entries] if e is not None)

def _read_v19_catalog(data):
    """Read the iOS HD build's version-19 catalog envelope.

    Confirmed by hand against one real HD shs_options.sav (iPad build,
    48549 bytes; entries recovered included real pack/episode ids, titles,
    filenames matching the known EXP corpus, and player pairs such as
    ``$USR``). That envelope differs from the Android versions 16-18 in three
    ways: there is no separate current-episode slot (the list starts right
    after the entry count, and its first record is a pack=0/episode=0
    built-in placeholder); the entry count is a u16, not a s32; and each
    entry carries one extra plain-text alias string (a punctuation-stripped
    title) between the filename and the download id. A fixed 200-byte
    trailer follows the string-pair table -- its structure is unconfirmed,
    but it was entirely zero in the one sample available, so it is only
    required to be present, not validated byte-for-byte.
    """
    r = _Reader(data, 38)
    count = r.integer('>H')
    if not 0 <= count <= MAX_ENTRIES:
        raise ContentError('Invalid native catalog entry count')
    entries = [r.entry(alias=True) for _ in range(count)]
    pairs = r.integer('>h')
    if not 0 <= pairs <= MAX_ENTRIES:
        raise ContentError('Invalid native string-pair count')
    for _ in range(pairs * 2):
        r.string()  # Discard native runtime/user strings.
    r.take(200)  # Reserved trailer; unconfirmed structure, zero in the one sample seen.
    if r.position != len(data):
        raise ContentError('Unsupported trailing native options data')
    return EpisodeCatalog(replace(e, source='hd') for e in entries if e is not None)


def read_options_catalog(data, *, game='shs'):
    """Read categories only; never import native preferences or saved progress.

    CoD retains the SHS signature but has its own version-17 envelope. Select
    layouts by game, then validate all records, string pairs, flags and EOF;
    never scan for a plausible entry or guess the game from this signature.
    Version 19 (the SHS iOS HD build) uses a distinct fixed envelope; see
    _read_v19_catalog.
    """
    if game not in GAMES:
        raise ContentError(f'Unknown catalog game: {game!r}')
    profile = GAMES[game]
    if len(data) > MAX_CATALOG_BYTES or len(data) < 16 or data[:12] != b'SHS_OPTIONS\0':
        raise ContentError(f'Not a supported {profile.CATALOG_FILENAME} catalog')
    version = struct.unpack_from('>i', data, 12)[0]
    if version == 19 and game == 'shs':
        return _read_v19_catalog(data)
    if version not in profile.CATALOG_LAYOUTS:
        raise ContentError(f'Unsupported native options version: {version}')
    results = []
    for prefix, trailing_flags in profile.CATALOG_LAYOUTS[version]:
        try:
            catalog = _Reader(data, prefix).catalog(trailing_flags)
            if game == 'shs':
                # Android's catalogs, told apart from the iOS HD build's version-19 one (source='hd').
                catalog = EpisodeCatalog(replace(e, source='standard') for e in catalog.entries)
            results.append(catalog)
        except ContentError:
            continue
    if len(results) != 1:
        raise ContentError('Invalid or ambiguous native episode catalog')
    return results[0]
