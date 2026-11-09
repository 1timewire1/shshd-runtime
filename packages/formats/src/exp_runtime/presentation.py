"""shshd-runtime: an episode's opt-in to this fork's presentation features (resource 3, SCHEMA.md "Presentation
extension"). Native players and upstream exp-runtime never read it; an app without a feature shows the line as SHS does.

Each member names what the runtime reads, all optional:

- `duet`: [partner key, expression key], SHS global numbers set around a two-speaker line (the partner as its ID + 1,
  0 none) (Session.dialogue_duet).
- `narration_theme`: the global number giving a named line without a portrait its colour: 1 blue, 2 pink, 3 gray
  (Session.narration_theme).
- `portrait_effects`: {key, images}: the global number holding a line's emoticon (emoticon_effects, 1-6) and the
  episode image of each of the six effects, null for one the episode lacks (Session.portrait_effect).
- `music_loops`: {intro: loop}: music resources that are an intro running into a loop (music_stream.MusicStream.chain).

Members for episodes made in the Creator (owner, 2026-11-09; CREATOR_ADDONS_PLAN.md):

- `creator`: true. The episode keeps the Creator's own names table (player.json `name_sets`), apart from the smartphone
  stories' and every translation's.
- `addons`: {primary, edition}: the add-on whose settings the episode takes, where they need its pictures and sounds
  (frame backdrop, relationship icons, answer-feedback music, its switches); `edition` picks between an add-on's games
  ('07 or '08 for the BREW add-on, '' for the others). The profile maps it to a translated pack (ADDON_FEATURE_PACKS).
- Settings that need no add-on, each true to use: `word_forms` ("a(n)" and "word(s)" in formatted lines), `date_first`
  (title and date cards show the date as the title), `three_word_games` (a word game of three words, one or two good)
  and `big_pickers` (a portrait picker of up to ten photos). `minigames`: the episode plays translated mini-games, so
  the player offers the "Use Translated Mini-Games" switch for it.
- `aliases`: {episode resource: [add-on, its resource]}: a picture or sound taken from an extra add-on (not the primary),
  under a number of the episode's own. The add-ons reuse numbers, and an episode reads a number from the first add-on it
  lists that has it, which is the primary; an alias always reaches the add-on it names.
"""
import json

from .exp import ContentError

RESOURCE = 3
MAGIC = b'SHSHD-PRESENTATION\0'
FORMAT = 'shshd-presentation'
VERSION = 1
EFFECTS = 6
MEMBERS = ('duet', 'narration_theme', 'portrait_effects', 'music_loops', 'creator', 'addons', 'word_forms', 'date_first',
           'three_word_games', 'big_pickers', 'minigames', 'aliases')
FLAGS = ('creator', 'word_forms', 'date_first', 'three_word_games', 'big_pickers', 'minigames')
EDITIONS = ('', '07', '08')


def _number(value, what):
    if type(value) is not int or not 0 <= value <= 0xffff:
        raise ValueError(f'{what} must be a number from 0 to 65535')
    return value


def normalize(record):
    """The record's members in the runtime's form: duet (partner key, expression key), narration_theme key,
    portrait_effects (key, six image IDs or None), music_loops {intro: loop}. Raises ValueError."""
    if not isinstance(record, dict) or record.get('format') != FORMAT or record.get('version') != VERSION:
        raise ValueError('unsupported presentation record version')
    unknown = set(record) - {'format', 'version', *MEMBERS}
    if unknown:
        raise ValueError(f'unknown members {sorted(unknown)}')
    result = {}
    if 'duet' in record:
        duet = record['duet']
        if not isinstance(duet, list) or len(duet) != 2:
            raise ValueError('duet must be [partner key, expression key]')
        result['duet'] = tuple(_number(key, 'a duet key') for key in duet)
    if 'narration_theme' in record:
        result['narration_theme'] = _number(record['narration_theme'], 'narration_theme')
    if 'portrait_effects' in record:
        effects = record['portrait_effects']
        if not isinstance(effects, dict) or set(effects) != {'key', 'images'}:
            raise ValueError('portrait_effects must be {key, images}')
        images = effects['images']
        if not isinstance(images, list) or len(images) != EFFECTS:
            raise ValueError(f'portrait_effects images must list {EFFECTS} images')
        result['portrait_effects'] = (_number(effects['key'], 'portrait_effects key'),
                                      tuple(None if image is None else _number(image, 'an effect image')
                                            for image in images))
    if 'music_loops' in record:
        loops = record['music_loops']
        if not isinstance(loops, dict):
            raise ValueError('music_loops must be {intro: loop}')
        result['music_loops'] = {_number(int(intro), 'an intro'): _number(loop, 'a loop')
                                 for intro, loop in loops.items()}
    for flag in FLAGS:
        if flag in record:
            if record[flag] is not True:
                raise ValueError(f'{flag} must be true')
            result[flag] = True
    if 'aliases' in record:
        aliases = record['aliases']
        if not isinstance(aliases, dict):
            raise ValueError('aliases must be {episode resource: [add-on, resource]}')
        result['aliases'] = {}
        for resource, target in aliases.items():
            if (not isinstance(target, list) or len(target) != 2 or not isinstance(target[0], str) or not target[0]):
                raise ValueError('an alias must be [add-on, resource]')
            result['aliases'][_number(int(resource), 'an aliased resource')] = (target[0], _number(target[1], 'a resource'))
    if 'addons' in record:
        addons = record['addons']
        if (not isinstance(addons, dict) or set(addons) != {'primary', 'edition'} or not isinstance(addons['primary'], str)
                or not addons['primary'] or addons['edition'] not in EDITIONS):
            raise ValueError("addons must be {primary: an add-on's ID, edition: '', '07' or '08'}")
        result['addons'] = (addons['primary'], addons['edition'])
    return result


def presentation_bytes(record):
    """Resource 3's payload for a record (its members, without format/version)."""
    record = dict(format=FORMAT, version=VERSION, **record)
    normalize(record)
    return MAGIC + json.dumps(record, separators=(',', ':')).encode('utf-8')


def presentation_record(archive):
    """The archive's normalized record, None without one. Raises ContentError for a malformed one."""
    if RESOURCE not in archive.entries:
        return None
    data = archive.read(RESOURCE)
    if not data.startswith(MAGIC):
        return None
    try:
        return normalize(json.loads(data[len(MAGIC):]))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ContentError(f'Invalid presentation record: {error}') from error
