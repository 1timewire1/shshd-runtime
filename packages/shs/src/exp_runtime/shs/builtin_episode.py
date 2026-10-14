"""Extract the base game's built-in story into an ordinary local CSPUD episode.

Only resource IDs and container structure live in the engine. Story text,
bytecode and localized titles are copied from the player's validated APK/IPA.
"""
import struct

from ..content import ContentError, ExpArchive, _zip_read


FOOTBALL_SCRIPTS = (*range(25001, 25022), 25023)
FOOTBALL_SOURCE = 'football-star'
FOOTBALL_NAME = 'Football_Star.exp'
FOOTBALL_ALIASES = ['Football Season', 'Football_Season.exp', 'footballseason', 'footballstar']


def extract_football(apk, asset_root='assets/Assets/', *, ios=False):
    """Return deterministic EXP bytes, or None when no base story is present."""
    if asset_root + '25001' not in apk.namelist():
        return None
    # Imported lazily: menu strings share the asset parser, not a pygame UI.
    from ..menu import MenuStrings
    titles = MenuStrings.parse(_zip_read(apk, asset_root + ('12' if ios else '13')))
    # Native built-in episode key is zero; FUN_0009794c packs (pack, episode).
    metadata = bytearray(struct.pack('>HH', 0, 0))
    for index in range(193, 198):
        title = titles[index].encode('utf-8')
        if not title or len(title) > 65535:
            raise ContentError('Invalid built-in episode title')
        metadata += struct.pack('>H', len(title)) + title
    records = {1: bytes(metadata)}
    for resource_id in range(25001, 25022) if ios else FOOTBALL_SCRIPTS:
        data = _zip_read(apk, f'{asset_root}{resource_id}')
        if not data.startswith(b'kiwi'):
            raise ContentError(f'Built-in story resource {resource_id} is not KiWi')
        records[resource_id] = data
    # Literal records preserve every byte, address and script ID. Art/audio
    # keep their native base namespace, just as they do for external episodes.
    index, bodies = bytearray(), bytearray()
    start = 9 + 6 * len(records)
    for resource_id, data in sorted(records.items()):
        index += struct.pack('>HI', resource_id, start + len(bodies))
        bodies += struct.pack('>III', len(data), len(data), 0) + data
    result = b'CSPUD' + struct.pack('>I', len(records)) + index + bodies
    ExpArchive(result).programs()  # Validate every copied script before publishing.
    return bytes(result)


def football_source():
    return dict(builtin=FOOTBALL_SOURCE, aliases=FOOTBALL_ALIASES[:])
