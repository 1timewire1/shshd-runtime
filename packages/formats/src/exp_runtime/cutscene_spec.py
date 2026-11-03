"""shshd-runtime: a storyboard cutscene's service numbers and spec (engine `cutscene.py` describes it and runs it).
Here since the creator compiles and checks them without the engine.
"""
import json

CUTSCENE = 218
CUTSCENE_QUERY = 202
FORMAT, VERSION = 'shshd-cutscene', 1


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
    if not isinstance(spec, dict) or spec.get('format') != FORMAT or spec.get('version') != VERSION:
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
    return spec
