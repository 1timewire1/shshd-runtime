"""shshd-runtime: a storyboard cutscene's service numbers and spec (engine `cutscene.py` describes it and runs it).
Here since the creator compiles and checks them without the engine.
"""
import json

CUTSCENE = 218
CUTSCENE_QUERY = 202
FORMAT, VERSION = 'shshd-cutscene', 1       # what the creator writes
VERSIONS = (1, 2)                           # what the player reads (2: taller frames, General's Aspect Ratio)
FITS = ('crop', 'height')


def _is_int(value):
    return type(value) is int


def _box(value):
    return (isinstance(value, list) and len(value) == 4 and all(type(v) in (int, float) for v in value)
            and value[2] > 0 and value[3] > 0)


def read_spec(data):
    """The spec from its resource's bytes, checked; ValueError if it isn't one."""
    try:
        spec = json.loads(data)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError(f'Not a cutscene: {error}') from error
    if not isinstance(spec, dict) or spec.get('format') != FORMAT or spec.get('version') not in VERSIONS:
        raise ValueError('Not a cutscene')
    size, hold, skip = spec.get('size'), spec.get('hold'), spec.get('skip')
    shots, overlays, sounds = spec.get('shots'), spec.get('overlays', []), spec.get('sounds', [])
    if (not isinstance(size, list) or len(size) != 2 or not all(_is_int(v) and v > 0 for v in size)
            or not _is_int(hold) or not _is_int(skip) or not 0 <= skip <= hold
            or not _is_int(spec.get('music', 0))
            or not isinstance(shots, list) or not shots or not isinstance(overlays, list) or not isinstance(sounds, list)):
        raise ValueError('Invalid cutscene')
    for item in shots + overlays:
        if (not isinstance(item, dict) or not _is_int(item.get('image')) or not _is_int(item.get('start'))
                or not _is_int(item.get('end')) or item['end'] < item['start']
                or not _box(item.get('from')) or not _box(item.get('to')) or item.get('ease', 'out') != 'out'):
            raise ValueError('Invalid cutscene picture')
    if shots[0]['start'] != 0 or any(a['start'] > b['start'] for a, b in zip(shots, shots[1:])):
        raise ValueError('A cutscene\'s shots start at 0, in order')
    if (not all(isinstance(s, dict) and _is_int(s.get('at')) and _is_int(s.get('sound')) for s in sounds)
            or any(a['at'] > b['at'] for a, b in zip(sounds, sounds[1:]))):
        raise ValueError('Invalid cutscene sounds')
    if spec['version'] >= 2:
        _check_version_2(spec)
    return spec


def _is_point(value):
    return isinstance(value, list) and len(value) == 2 and all(type(v) in (int, float) for v in value)


def _check_version_2(spec):
    """Version 2 (General's Aspect Ratio; reference/handoff_x360_storyboard_ratios_answers.md): `size` is still the 3:4
    frame (overlays are in its pixels), `tallest` [w, h] the tallest frame the stills serve, as wide as `size` (9:16:
    768 x 1366). A shot's `fit`: 'crop' (the default), its windows at `tallest`'s shape, cropped about their centre to
    the frame's; 'height', its windows at `size`'s shape (a painting no taller than 3:4), the frame's height kept and the
    sides narrowed about its `anchor` [x, y] (picture pixels), so a taller frame zooms in on the anchor; with
    `anchor_to` [x, y] the anchor travels there as the window travels to `to` (its pace and easing: a pan from shoes to
    face, reference/handoff_x360_storyboard_v2_reply.md). An overlay may `follow` a shot (its index): its centre stays on
    the same place in that shot's picture, its size in frame pixels, kept on the canvas (desktop_cutscene._placed)."""
    size, tallest = spec['size'], spec.get('tallest')
    if (not isinstance(tallest, list) or len(tallest) != 2 or not all(_is_int(v) and v > 0 for v in tallest)
            or tallest[0] != size[0] or tallest[1] < size[1]):
        raise ValueError('A version 2 cutscene names its tallest frame, as wide as its size')
    shots = spec['shots']
    for shot in shots:
        fit = shot.get('fit', 'crop')
        if fit not in FITS or (fit == 'height' and not _is_point(shot.get('anchor'))):
            raise ValueError('Invalid cutscene fit')
        if 'anchor_to' in shot and not (fit == 'height' and _is_point(shot['anchor_to'])):
            raise ValueError('Invalid cutscene anchor_to')
    for overlay in spec.get('overlays', []):
        follow = overlay.get('follow')
        if follow is not None and not (_is_int(follow) and 0 <= follow < len(shots)):
            raise ValueError('Invalid cutscene overlay follow')
