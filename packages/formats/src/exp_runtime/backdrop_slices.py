"""shshd-runtime: an episode's backdrop slices (Claire Hart plan Stage 2, decision M; owner, 2026-11-19), resource 7.

Claire Hart's scenes are 4:3 (1024 x 768) while Cause of Death's frame is 3:4. A translated case shows each scene's 3:4
slice, a window as tall as the picture, its left edge at x. Its add-on's spec holds every scene's slice (chc 26998,
`scenes`); a case carries the slices of the scenes it shows here as well, so moving one is an episode update rather than
a new add-on. The record is JSON:

    {"format": "shshd-backdrop-slices", "version": 1, "slices": {"<resource>": x, ...}}

Native players and upstream exp-runtime never read resource 7.
"""
import json

from .exp import ContentError

RESOURCE = 7
FORMAT = 'shshd-backdrop-slices'
VERSION = 1


def encode(slices):
    """The record's bytes for {resource: x}."""
    clean = {}
    for resource, x in slices.items():
        if type(resource) is not int or not 0 <= resource <= 65535 or type(x) is not int or x < 0:
            raise ContentError(f'Invalid backdrop slice {resource!r}: {x!r}')
        clean[str(resource)] = x
    return json.dumps({'format': FORMAT, 'version': VERSION, 'slices': clean}, separators=(',', ':'),
                      sort_keys=True).encode('utf-8')


def decode(data):
    """{resource: x} from the record's bytes; ContentError if it isn't one."""
    try:
        record = json.loads(data)
    except (ValueError, UnicodeDecodeError) as error:
        raise ContentError(f'Unreadable backdrop slices: {error}') from None
    if not isinstance(record, dict) or record.get('format') != FORMAT or record.get('version') != VERSION:
        raise ContentError('Not a backdrop slices record')
    slices = record.get('slices')
    if not isinstance(slices, dict):
        raise ContentError('Backdrop slices without a table')
    out = {}
    for key, x in slices.items():
        if not key.isdigit() or type(x) is not int or x < 0 or int(key) > 65535:
            raise ContentError(f'Invalid backdrop slice {key!r}: {x!r}')
        out[int(key)] = x
    return out


def slice_box(size, x):
    """The 3:4 window (left, top, width, height) of a picture `size` (width, height) at x, kept inside the picture."""
    width, height = size
    span = min(width, round(height * 3 / 4))
    left = max(0, min(width - span, x))
    return left, 0, span, height
