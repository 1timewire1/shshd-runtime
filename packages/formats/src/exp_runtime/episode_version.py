"""shshd-runtime: an episode's version (owner, 2026-11-06), resource 5 (SCHEMA.md "Episode version extension").

A translated or authored episode can say which version of itself it is, so importing a newer build replaces the copy a
library already holds rather than sitting beside it. The record is `{format, version, revision}`; `revision` is the
episode's version, 1-65535, as an addon's revision is (addons.py). Copies are the same episode when their pack, episode
number and release (`variant`) match. Native players and upstream exp-runtime never read resource 5.
"""
import json

from .exp import ContentError

RESOURCE = 5
MAGIC = b'SHSHD-EPISODE\0'
FORMAT = 'shshd-episode'
VERSION = 1


def _revision(value):
    if type(value) is not int or not 1 <= value <= 0xffff:
        raise ValueError('an episode version must be a number from 1 to 65535')
    return value


def normalize(record):
    """The record's revision. Raises ValueError."""
    if not isinstance(record, dict) or record.get('format') != FORMAT or record.get('version') != VERSION:
        raise ValueError('unsupported episode version record')
    if set(record) != {'format', 'version', 'revision'}:
        raise ValueError('an episode version record holds only its revision')
    return _revision(record['revision'])


def version_bytes(revision):
    """Resource 5's payload for an episode at `revision`."""
    record = dict(format=FORMAT, version=VERSION, revision=revision)
    normalize(record)
    return MAGIC + json.dumps(record, separators=(',', ':')).encode('utf-8')


def episode_revision(archive):
    """The archive's episode version, None without one. Raises ContentError for a malformed record."""
    if RESOURCE not in archive.entries:
        return None
    data = archive.read(RESOURCE)
    if not data.startswith(MAGIC):
        return None
    try:
        return normalize(json.loads(data[len(MAGIC):]))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ContentError(f'Invalid episode version record: {error}') from error
