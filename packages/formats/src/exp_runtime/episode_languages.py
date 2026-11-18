"""shshd-runtime: an episode's own translations (owner, 2026-11-17), resource 6 (SCHEMA.md "Episode languages extension").

An episode can carry its text in other languages, shown in place of its own when the switch it names says so (SHS '11's
Italian: the "'11 Language" switch, `shs11_language`). The record is MAGIC, then gzip'd JSON:

    {format, version, setting, languages: {code: name}, titles: {code: title},
     lines, context, menu, words: {key: {code: text}} (and context: {key: {previous key: {code: text}}}),
     ui: {code: {game: {name: text}}}}

`lines`, `context`, `menu` and `words` are the DSiWare add-on's table shape (dsi.Translation reads either): a line is
found by its key (dsi.key: lower case, letters, digits and name tokens), a line translated two ways by the line shown
before it, a name or title in `menu`, a word grid's words and letters in `words`. `ui` holds a translated game's own
interface text (SHS '11's Memory and Reflex). Native players and upstream exp-runtime never read resource 6.
"""
import gzip
import json

from .exp import ContentError

RESOURCE = 6
MAGIC = b'SHSHD-LANGUAGES\0'
FORMAT = 'shshd-languages'
VERSION = 1
SETTINGS = ('shs11_language',)          # the switches a record may answer to
TABLES = ('lines', 'context', 'menu', 'words')
OFF = 'off'


def _texts(value, codes, where):
    if not isinstance(value, dict) or not value or not set(value) <= codes or not all(
            isinstance(text, str) for text in value.values()):
        raise ValueError(f'{where} must give text for the record\'s languages')


def normalize(record):
    """The record, checked. Raises ValueError."""
    if not isinstance(record, dict) or record.get('format') != FORMAT or record.get('version') != VERSION:
        raise ValueError('unsupported episode languages record')
    if record.get('setting') not in SETTINGS:
        raise ValueError(f'an episode languages record answers to one of {", ".join(SETTINGS)}')
    languages = record.get('languages')
    if (not isinstance(languages, dict) or not languages or OFF in languages
            or not all(isinstance(k, str) and 2 <= len(k) <= 8 and isinstance(v, str) for k, v in languages.items())):
        raise ValueError('an episode languages record names its languages: {code: name}')
    codes = set(languages)
    if 'titles' in record:
        _texts(record['titles'], codes, 'titles')
    for table in TABLES:
        entries = record.get(table, {})
        if not isinstance(entries, dict):
            raise ValueError(f'{table} must be a table')
        for found, entry in entries.items():
            if table == 'context':
                if not isinstance(entry, dict):
                    raise ValueError('context must be {key: {previous key: texts}}')
                for previous, texts in entry.items():
                    _texts(texts, codes, f'context {found!r}')
            else:
                _texts(entry, codes, f'{table} {found!r}')
    ui = record.get('ui', {})
    if not isinstance(ui, dict) or not set(ui) <= codes or not all(
            isinstance(games, dict) and all(isinstance(texts, dict) and all(isinstance(t, str) for t in texts.values())
                                            for texts in games.values()) for games in ui.values()):
        raise ValueError('ui must be {code: {game: {name: text}}}')
    unknown = set(record) - {'format', 'version', 'setting', 'languages', 'titles', 'ui', *TABLES}
    if unknown:
        raise ValueError(f'an episode languages record has no {", ".join(sorted(unknown))}')
    return record


def languages_bytes(record):
    """Resource 6's payload for `record` (format and version added)."""
    record = normalize(dict(record, format=FORMAT, version=VERSION))
    return MAGIC + gzip.compress(json.dumps(record, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), mtime=0)


def episode_languages(archive):
    """The archive's languages record, None without one. Raises ContentError for a malformed record."""
    if RESOURCE not in archive.entries:
        return None
    data = archive.read(RESOURCE)
    if not data.startswith(MAGIC):
        return None
    try:
        return normalize(json.loads(gzip.decompress(data[len(MAGIC):])))
    except (ValueError, UnicodeError, RecursionError, OSError, EOFError) as error:
        raise ContentError(f'Invalid episode languages record: {error}') from error


def import_fields(archive):
    """What the library keeps of an episode's languages, read at import: {languages: {setting, names, titles}}, or {}
    (none, or a malformed record, which then plays in its own language only)."""
    try:
        record = episode_languages(archive)
    except ContentError:
        return {}
    if record is None:
        return {}
    return dict(languages=dict(setting=record['setting'], names=record['languages'], titles=record.get('titles', {})))
