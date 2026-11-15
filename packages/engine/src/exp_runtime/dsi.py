"""shshd-runtime: the optional `shsdsi` add-on, SHS DSiWare's redrawn backgrounds (tools/translate/dsi.py builds it from the
player's own DSiWare image).

The DSi draws each location as two 192 x 256 screens, a left and a right one, where the smartphone's picture pans. With the
add-on imported and DSi Backgrounds on, an episode shows them when every background it can show has a DSi counterpart
(owner, 2026-11-15, reference/Other Games/docs/DSI_ADDON_SCOPE.md):
- in the eight stories the DSi ported (`stories`), whatever the DSi showed for that picture, its stand-in times included;
- in any other episode, only a picture of the same location at the same time of day (`exact`).
The spec (resource SPEC) maps a smartphone bank picture to a DSi picture (`bank`: id -> [picture, exact]) and a DSi picture
to its two screens (`screens`: picture -> [left resource, right resource]).

Which backgrounds an episode can show is read from its scripts without running them: every constant base and variant its
background services (11, 34, 35, 86) are given, and every title card's picture (8). A background chosen at run time from a
variable isn't counted.
"""
import json
import logging
import re

ADDON = 'shsdsi'
SPEC = 26000
# Background services: (the argument holding the base, the one holding the variant), as engine.Engine reads them.
BACKGROUND_SERVICES = {11: (1, 0), 34: (1, 0), 35: (2, 1), 86: (0, 1)}
TITLE_CARD = 8
PUSH, PUSH_BYTES, PUSH_FALSE, PUSH_TRUE, CALL = 0x1A, 0x1B, 0x5A, 0x5B, 0x1F


def spec(library):
    """The add-on's spec (dict) while the library holds it, else None. Kept on the library until the add-on changes."""
    found = library.addon(ADDON) if hasattr(library, 'addon') else None
    if found is None:
        return None
    record, archive = found
    key = (record.get('file'), record.get('revision'))
    cached = library.__dict__.get('_dsi_spec')
    if cached is None or cached[0] != key:
        try:
            value = json.loads(archive.read(SPEC))
        except (KeyError, ValueError, OSError) as error:
            logging.warning('The DSiWare add-on has no readable spec: %s', error)
            value = None
        library._dsi_spec = cached = (key, value)
    return cached[1]


def story_key(title):
    """A title as the spec's `stories` list it: lower case, letters and digits, a leading episode number dropped."""
    title = re.sub(r'^\s*\d+\s*[:.]\s*', '', title or '')
    return re.sub(r'[^a-z0-9]+', ' ', title.lower()).strip()


def is_story(record, value):
    """Whether an episode's record is one of the eight stories the DSi ported (by its titles or aliases)."""
    names = list(record.get('titles') or ()) + list(record.get('aliases') or ())
    stories = set(value.get('stories', ()))
    return any(story_key(name) in stories for name in names)


def _signed(value):
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def shown_backgrounds(programs, exists):
    """Every background a script can set from constants: {resource}. `exists(id)` tells whether a variant picture is there
    (the engine falls back to the base when it isn't)."""
    found = set()
    for program in programs:
        stack = []
        for instruction in program.instructions:
            op, arg = instruction.opcode, instruction.operand
            if op == PUSH:
                stack.append(_signed(arg))
            elif op == PUSH_BYTES:
                stack += [b - 0x100 if b > 0x7F else b for b in (arg & 0xFF, arg >> 8)]
            elif op in (PUSH_FALSE, PUSH_TRUE):
                stack.append(op - PUSH_FALSE)
            elif op == CALL:
                service, count = arg >> 8, arg & 0xFF
                args = stack[-count:] if count and len(stack) >= count else [None] * count
                if service in BACKGROUND_SERVICES and count >= 2:
                    at_base, at_variant = BACKGROUND_SERVICES[service]
                    base, variant = args[at_base], args[at_variant]
                    if base is not None and base >= 0:
                        shown = base + variant if variant in (1, 2) else base
                        found.add(shown if exists(shown) else base)
                elif service == TITLE_CARD and count >= 3 and args[2] is not None and args[2] >= 0:
                    found.add(args[2])
                stack = []
            else:
                stack.append(None)
    return found


TRANSLATED_PACKS = 30000     # a translated game's packs (31000 and up) draw their own add-ons' art


def smartphone_episode(resources):
    """Whether an episode is SHS's own (smartphone or HD): not a translation from another game, which draws its add-on's
    pictures, nor one made in the Creator on an add-on."""
    record = getattr(resources, 'record', None) or {}
    return (record.get('pack_id') or 0) < TRANSLATED_PACKS and not getattr(resources, 'required_addons', ())


def picture_for(resources, background):
    """The DSi picture an episode that qualifies shows for a background (one its scripts choose at run time too), or None."""
    pictures = resources.dsi_pictures()
    if not pictures:
        return None
    if background in pictures:
        return pictures[background]
    value = spec(resources.library) or {}
    entry = value.get('bank', {}).get(str(background))
    if entry is None or not (entry[1] or is_story(resources.record, value)):
        return None
    return entry[0]


def episode_pictures(resources):
    """{background: DSi picture} for an episode that qualifies, None for one that doesn't (or without the add-on)."""
    value = spec(resources.library)
    if value is None or not smartphone_episode(resources):
        return None
    bank = value.get('bank', {})
    story = is_story(resources.record, value)
    shown = shown_backgrounds(resources.programs.values(), resources.exists)
    pictures = {}
    for background in shown:
        entry = bank.get(str(background))
        if entry is None or not (story or entry[1]):
            return None
        pictures[background] = entry[0]
    return pictures or None


def screens(resources, picture):
    """The resources of a DSi picture's (left, right) screens, or None."""
    value = spec(resources.library)
    found = None if value is None else value.get('screens', {}).get(picture)
    return None if found is None else tuple(found)
