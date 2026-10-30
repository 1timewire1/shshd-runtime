"""shshd-runtime: addons, shared resource packs that episodes declare (resource 4, SCHEMA.md "Addon extension").

An addon is an ordinary EXP archive holding resources several episodes use (a translated game's backgrounds and
music), so each episode need not carry its own copy. It names itself with a `provides` record; an episode lists the
addons it reads with a `requires` record. Its episode-bank resources (26000 and up) then resolve from the episode
first, then from each addon in the order listed. Native players and upstream exp-runtime never read resource 4.

- `provides`: {id, title, revision}: what the addon is. `id` is a short name ([a-z0-9-], at most 32), `revision` the
  addon's resource layout (1-65535): an addon of a higher revision serves every episode of a lower one.
- `requires`: [{id, revision}, ...]: the addons an episode needs, each at least that revision.
"""
import json
import re

from .exp import ContentError

RESOURCE = 4
MAGIC = b'SHSHD-ADDONS\0'
FORMAT = 'shshd-addons'
VERSION = 1
IDENTIFIER = re.compile('[a-z0-9][a-z0-9-]{0,31}')
TITLE_LIMIT = 120


def _revision(value):
    if type(value) is not int or not 1 <= value <= 0xffff:
        raise ValueError('a revision must be a number from 1 to 65535')
    return value


def _identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f'an addon id must be up to 32 of a-z, 0-9 and -: {value!r}')
    return value


def normalize(record):
    """The record in the runtime's form: ('provides', {id, title, revision}) or ('requires', ((id, revision), ...)).
    Raises ValueError."""
    if not isinstance(record, dict) or record.get('format') != FORMAT or record.get('version') != VERSION:
        raise ValueError('unsupported addon record version')
    members = set(record) - {'format', 'version'}
    if members == {'provides'}:
        provides = record['provides']
        if not isinstance(provides, dict) or set(provides) != {'id', 'title', 'revision'}:
            raise ValueError('provides must be {id, title, revision}')
        title = provides['title']
        if not isinstance(title, str) or not 0 < len(title) <= TITLE_LIMIT:
            raise ValueError(f'an addon title must be 1 to {TITLE_LIMIT} characters')
        return 'provides', dict(id=_identifier(provides['id']), title=title, revision=_revision(provides['revision']))
    if members == {'requires'}:
        requires = record['requires']
        if not isinstance(requires, list) or not requires:
            raise ValueError('requires must list at least one addon')
        result = []
        for item in requires:
            if not isinstance(item, dict) or set(item) != {'id', 'revision'}:
                raise ValueError('each required addon must be {id, revision}')
            result.append((_identifier(item['id']), _revision(item['revision'])))
        if len({name for name, _ in result}) != len(result):
            raise ValueError('an addon is required twice')
        return 'requires', tuple(result)
    raise ValueError('an addon record holds either provides or requires')


def provides_bytes(addon_id, title, revision):
    """Resource 4's payload for an addon."""
    record = dict(format=FORMAT, version=VERSION, provides=dict(id=addon_id, title=title, revision=revision))
    normalize(record)
    return MAGIC + json.dumps(record, separators=(',', ':')).encode('utf-8')


def requires_bytes(requires):
    """Resource 4's payload for an episode needing `requires`, [(id, revision), ...]."""
    record = dict(format=FORMAT, version=VERSION, requires=[dict(id=name, revision=revision)
                                                            for name, revision in requires])
    normalize(record)
    return MAGIC + json.dumps(record, separators=(',', ':')).encode('utf-8')


def addon_record(archive):
    """The archive's normalized record (see `normalize`), None without one. Raises ContentError for a malformed one."""
    if RESOURCE not in archive.entries:
        return None
    data = archive.read(RESOURCE)
    if not data.startswith(MAGIC):
        return None
    try:
        return normalize(json.loads(data[len(MAGIC):]))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ContentError(f'Invalid addon record: {error}') from error
