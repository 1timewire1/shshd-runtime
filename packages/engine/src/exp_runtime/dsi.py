"""shshd-runtime: the optional `shsdsi` add-on, SHS DSiWare's redrawn backgrounds (tools/translate/dsi.py builds it from the
player's own DSiWare image).

The DSi draws each location as two 192 x 256 screens, a left and a right one, where the smartphone's picture pans. With the
add-on imported and DSi Backgrounds on, an episode shows them when every background it can show has a DSi counterpart
(owner, 2026-11-15, reference/Other Games/docs/DSI_ADDON_SCOPE.md):
- in the eight stories the DSi ported (`stories`), whatever the DSi showed for that picture, its stand-in times included;
- in any other episode, only a picture of the same location at the same time of day (`exact`).
An episode's own picture that is plain black (a fade or flashback screen) needs no counterpart: it shows as it is.
An episode made in the Creator may name the DSi location each of its own pictures is (presentation `optional_art`, `shsdsi`:
its picture -> the location's left screen; owner, 2026-11-17), which counts as that picture's counterpart.
The spec (resource SPEC) maps a smartphone bank picture to a DSi picture (`bank`: id -> [picture, exact]) and a DSi picture
to its two screens (`screens`: picture -> [left resource, right resource]).

Which backgrounds an episode can show is read from its scripts without running them: every constant base and variant its
background services (11, 34, 35, 86) are given, and every title card's picture (8). A background chosen at run time from a
variable isn't counted.
"""
import json
import logging
from pathlib import Path
import re
import threading

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


def own_locations(resources, value):
    """{the episode's picture: DSi picture} that its presentation record names (`optional_art`, `shsdsi`: a picture -> the
    location's left screen), {} for none."""
    from .content import declared
    named = (declared(resources, 'optional_art') or {}).get(ADDON) or {}
    lefts = {screens[0]: picture for picture, screens in value.get('screens', {}).items() if screens}
    return {own: lefts[left] for own, left in named.items() if left in lefts}


def episode_pictures(resources):
    """{background: DSi picture} for an episode that qualifies, None for one that doesn't (or without the add-on)."""
    value = spec(resources.library)
    if value is None:
        return None
    own = own_locations(resources, value)
    if not own and not smartphone_episode(resources):
        return None
    bank = value.get('bank', {})
    story = is_story(resources.record, value)
    shown = shown_backgrounds(resources.programs.values(), resources.exists)
    pictures = {}
    for background in shown:
        if background in own:
            pictures[background] = own[background]
            continue
        entry = bank.get(str(background))
        if entry is None and background >= OWN_ART and plain_black(resources, background):
            continue                # its own black screen shows as it is, as it would beside the DSi's art
        if entry is None or not (story or entry[1]):
            return None
        pictures[background] = entry[0]
    return pictures or None


OWN_ART = 26000         # an episode's own pictures, past the game's bank
BLACK = 8               # the brightest a plain black picture's pixels get (a JPEG's noise)


def plain_black(resources, background):
    """Whether an episode's own picture is one flat black: a fade or flashback screen, which needs no DSi counterpart (owner,
    2026-11-15: seven episodes were held back by nothing else). False when it can't be read (or Pillow is missing)."""
    try:
        import io
        from PIL import Image
        with Image.open(io.BytesIO(resources.raw_asset(background))) as image:
            image.draft('RGB', (max(1, image.width // 8), max(1, image.height // 8)))     # (a JPEG decodes small)
            return max(high for _, high in image.convert('RGB').getextrema()) <= BLACK
    except Exception as error:       # (any picture it can't read counts as one the DSi has no counterpart for)
        logging.debug('DSi: picture %s not read: %s', background, error)
        return False


def screens(resources, picture):
    """The resources of a DSi picture's (left, right) screens, or None."""
    value = spec(resources.library)
    found = None if value is None else value.get('screens', {}).get(picture)
    return None if found is None else tuple(found)


# ---------- the translations (revision 2: the spec's `text`) ----------

LANGUAGES = ('fr', 'it', 'de', 'es')
LANGUAGE_OFF = 'off'
PLAYER_TOKENS = frozenset({'$USR'})     # the name the player typed: never translated
GRID = re.compile(r'[a-z]+(\|[a-z]+)*')  # a word grid's words or letters (tools/translate/dsi_text.GRID)


def key(text):
    """A line as the table keys it (tools/translate/dsi_text.norm): lower case, letters, digits and name tokens, so the
    copies of a story that differ in punctuation or spacing find the same line."""
    return ' '.join(re.findall(r'[a-z0-9$]+', text.lower()))


def text_table(library):
    """The add-on's translations (dict: languages, lines, context, menu), or None. Kept on the library."""
    value = spec(library)
    if value is None or 'text' not in value:
        return None
    found = library.addon(ADDON)
    cache_key = (found[0].get('file'), found[0].get('revision'))
    cached = library.__dict__.get('_dsi_text')
    if cached is None or cached[0] != cache_key:
        try:
            table = json.loads(found[1].read(value['text']))
        except (KeyError, ValueError, OSError) as error:
            logging.warning('The DSiWare add-on has no readable translations: %s', error)
            table = None
        library._dsi_text = cached = (cache_key, table)
    return cached[1]


class Translation:
    """One episode's lines in one language. `line(text)` gives a line's translation (the line itself when the DSi has
    none: a line it cut, or one its alignment couldn't place). Where a line is translated differently in different scenes,
    the one after the line shown before it wins (`previous`); `token` gives a default name's translation (German renames
    characters: `$Travis` is Tobias; owner, 2026-11-15)."""

    def __init__(self, table, language):
        self.lines, self.context, self.menu = table.get('lines', {}), table.get('context', {}), table.get('menu', {})
        self.words = table.get('words', {})
        self.language = language
        self.previous = ''

    def _entry(self, found, remember):
        entry = self.context.get(found, {}).get(self.previous) or self.lines.get(found) or self.menu.get(found)
        if remember:
            self.previous = found
        return None if entry is None else entry.get(self.language)

    def line(self, text, *, remember=True):
        if GRID.fullmatch(text):
            # A word grid's words or letters: the DSi's list for this language, found by the English exactly (never a
            # line that reads alike), else the English one.
            return self.words.get(text, {}).get(self.language) or text
        found = key(text)
        if not found:
            return text
        translated = self._entry(found, remember)
        if translated is None:
            # shshd-runtime: a string built of parts (a choice's options `a|b`, an option and its detail line), with no
            # entry of its own, takes each part's (an episode made in the Creator keys its fields one by one).
            for separator in ('\x1f', '|'):
                if separator in text:
                    return separator.join(self.line(part, remember=False) for part in text.split(separator))
        return text if translated is None else translated

    def token(self, name, value):
        """A name token's value as shown: a character's name the DSi translates (German's Brendan is Michael, whether the
        line says `$Player` or `$Brendan`) in this language; the player's own name (`$USR`), and a name the player gave a
        lead (no DSi name), as it is."""
        if name in PLAYER_TOKENS or not value:
            return value
        entry = self.menu.get(key(value)) or self.lines.get(key(value))
        return (entry or {}).get(self.language) or value


class Source:
    """The engine's way to its episode's translation (EpisodeResources.dsi_translation), shared, never copied: a save's
    restore deep-copies the engine, and the resources hold open files."""

    def __init__(self, function, languages=None):
        self.function = function
        self.languages = LANGUAGES if languages is None else tuple(languages)      # those it can give, for shown_forms

    def __call__(self, language=None):
        return self.function(language)

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


def translation(resources, language):
    """The Translation an episode shows in `language`, or None: only the eight stories the DSi ported (`is_story`) are
    translated, and only SHS's own copies of them."""
    if language not in LANGUAGES:
        return None
    library = resources.library
    table = text_table(library)
    value = spec(library)
    if table is None or not smartphone_episode(resources) or not is_story(resources.record, value):
        return None
    made = resources.__dict__.setdefault('_dsi_translations', {})
    if language not in made or made[language][0] is not table:
        made[language] = (table, Translation(table, language))
    return made[language][1]


def episode_title(library, record, language):
    """A DSi story's title in `language` (the DSi's menu text), keeping the record's episode number ("01: "), or None."""
    value = spec(library) if language in LANGUAGES else None
    table = None if value is None else text_table(library)
    if table is None or not is_story(record, value):
        return None
    titles = list(record.get('titles') or ())
    for title in titles + list(record.get('aliases') or ()):           # (Football Star is the DSi's Football Season)
        entry = table.get('menu', {}).get(key(story_key(title))) or table.get('lines', {}).get(key(story_key(title)))
        if entry and entry.get(language):
            number = re.match(r'^\s*\d+\s*[:.]\s*', titles[0] if titles else title)
            # (A title card's string may carry the emphasis marks it's shown with: not in a list.)
            return (number.group(0) if number else '') + entry[language].replace('`', '').strip()
    return None


# ---------- which episodes qualify, kept for the episode list (its DSi tag) ----------

COVERAGE_FILE = 'dsi_backgrounds.json'     # in the library's folder: {"addon": its file, "episodes": {id: true/false}}
_coverage_lock = threading.Lock()


def _coverage(library):
    """The library's record of which episodes qualify, for the add-on it holds now: (dict, its key), loaded once."""
    found = library.addon(ADDON) if hasattr(library, 'addon') else None
    key = None if found is None else found[0].get('file')
    cached = library.__dict__.get('_dsi_coverage')
    if cached is None or cached[0] != key:
        episodes = {}
        path = Path(library.directory) / COVERAGE_FILE
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            if saved.get('addon') == key and isinstance(saved.get('episodes'), dict):
                episodes = {k: bool(v) for k, v in saved['episodes'].items()}
        except (OSError, ValueError, AttributeError):
            pass
        library._dsi_coverage = cached = (key, episodes)
    return cached[1], cached[0]


def known(library, record):
    """Whether an episode shows the DSi backgrounds (True / False), or None while that's still to be found (`measure`, on a
    background thread: opening and reading an episode takes about 0.1 s on a PC)."""
    if not hasattr(library, 'addon') or library.addon(ADDON) is None:
        return False
    with _coverage_lock:
        episodes, _ = _coverage(library)
        return episodes.get(record['id'])


def measure(library, record):
    """Find whether an episode qualifies and keep it in the library's record (written at once: a file of a few KB)."""
    try:
        qualifies = library.open_episode(record['id']).dsi_pictures() is not None
    except Exception as error:      # (an episode that can't be read shows no tag)
        logging.warning('DSi: %s not measured: %s', record.get('name'), error)
        qualifies = False
    with _coverage_lock:
        episodes, key = _coverage(library)
        episodes[record['id']] = qualifies
        try:
            path = Path(library.directory) / COVERAGE_FILE
            staged = path.with_suffix('.tmp')
            staged.write_text(json.dumps(dict(addon=key, episodes=episodes), separators=(',', ':')), encoding='utf-8')
            staged.replace(path)
        except OSError as error:
            logging.warning('DSi: the record of qualifying episodes is not saved: %s', error)
    return qualifies
