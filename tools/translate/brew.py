"""The BREW games' ('07, '08) stories as smartphone SHS episodes: their KiWi scripts, with every host call rewritten for SHS's
services, and the `shsbrew` addon that holds all their art and music.

BREW's machine is SHS's, in KiWi's older header. Its host services are its own (SHS_BREW_ENGINE.md, section 3, in the owner's
reference folder; Tardy-Slip's player is the behavioural reference). What a call becomes is in HANDLERS, and a service with no
handler stops the translation, so a story that needs something new says so. Underneath:

- **Scripts.** A story's first script stays 25001. Its story script, 26000, becomes 25002, since 26000 and up are SHS's episode
  bank. BREW's calendar is only as live as a story needs it to be: a Campaign story runs one event, so scheduling it just queues
  its script.
- **Numbers.** BREW's and SHS's numbered values work alike and share the meaning of 601 and 629. Only 407 differs: BREW's runs 0 to
  100 and SHS's counts icons, so BREW's value stays under RELATIONSHIP_BREW and 407 follows it.
- **Portraits.** A character's look is a 23-entry list built by 62 and 64. A list's entries live in saved numbers, with a running
  hash, and each change looks the hash up in the story's table of the looks it can reach (from the catalogue), then points the
  character at that look's bank of faces. Entry 2 picks the dialogue box's colour, as BREW's pink one does.
- **Scenes.** 13 pushes a scene and 18 closes the top one, so what's underneath comes back. The stack lives in saved numbers.

Nothing here keeps art: a story holds only its scripts, and reads pictures and music from the addon (build_addon).
"""
import hashlib
import json
from pathlib import Path
import re
import sys

from PIL import Image

from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes, requires_bytes
from exp_runtime.decode.bytecode import decode_program
from exp_runtime.exp import ExpArchive, Metadata, encode_exp
from exp_runtime.vm import signed16

sys.path.insert(0, str(Path(__file__).resolve().parent))

import brew_art  # noqa: E402
from kiwi_rewrite import Rewriter  # noqa: E402
import nr_art  # noqa: E402

ADDON_ID, ADDON_TITLE, ADDON_REVISION = 'shsbrew', 'Surviving High School (BREW)', 1
PACK_CAMPAIGN, PACK_CLASSIC, PACK_SEASON = 31000, 31100, 31200
ADDON_EPISODE = 9999
TITLE_SUFFIX_07, TITLE_SUFFIX_08 = ' (SHS07)', ' (SHS08)'
FIRST_SCRIPT, STORY_SCRIPT, BREW_STORY_SCRIPT = 25001, 25002, 26000

# The addon's resources. A resource keeps its ID once shipped: new ones go at the end of their range.
BACKGROUND_BASE = 26000                 # + SKY_MODES x location index + sky mode
SKY_MODES = 3
LOCATIONS_08 = 28                       # 1000-1027; then 2000-2011
LOCATIONS_08_EXTRA = 12
LOCATION_07_OFFSET = 40                 # '07's own 1000-1027, after '08's
SKY_ONLY = 68                           # a scene with no location: its sky alone
MUSIC_BASE, MUSIC_TRACKS = 26900, 15    # 8000-8014
SPEC = 26998                            # what the addon holds, JSON
FRAME_BACKDROP, PINK_BACKDROP = 26999, 26991        # the panel, and behind a pink box (profile TRANSLATED_THEME_BACKDROP)
BADGE_BASE = 26992                      # heart, skull, smiley, each whole then each broken (profile TRANSLATED_BADGE_ART)
PORTRAIT_BASE = 27000                   # + EXPRESSIONS x look + face
EXPRESSIONS = brew_art.EXPRESSIONS
PORTRAIT_SIZE = (72, 84)                # art pixels: at 3.5 times, 252 x 294, within twice the player's portrait mask
PORTRAIT_LIFT = 7                       # art pixels clear under a portrait
BACKGROUND_SCALE = 6
STRIP_WIDTH, STRIP_HEIGHT = brew_art.STRIP_SIZE
BACKDROP_COLOUR = (0x90, 0x98, 0xD1)     # colour 0 of BREW's main layout set
SPEC_FORMAT, SPEC_VERSION = 'shsbrew', 1

# Global numbers (SHS's owner 0) and text keys this translation keeps for itself. BREW's own keys stay below 3000.
SPEAKER_KEY, EXPRESSION_KEY, DEPTH_KEY, CLOCK_KEY, EVENT_CHARACTER_KEY = 31001, 31002, 31003, 31004, 31005
FIELD_KEY = 31010                       # + field: the current event's 16 fields
SCENE_LOCATION_KEY, SCENE_SKY_KEY = 31030, 31050    # + depth
EVENT_TEXT = '$BREWEVENT'
EVENT_NAME = 'Event'
PLAYER = 0                              # BREW's character 0, You, is the player: SHS's primary speaker (74)
NAME_WORDS = 24                         # room for a character's name, for a voice with no picture
NIGHT_FROM = 1080                       # sky mode -1 is night from this minute (screens.js drawSky)
NARRATOR = 199                          # no speaker; SHS needs a character (as newrules.NARRATOR)
RELATIONSHIP, THEME = 407, 651          # SHS keys
RELATIONSHIP_BREW = 30407               # BREW's own 0-100 value
LIST_KEYS, LIST_SLOTS, LIST_LENGTH = 20000, 32, 31      # an entity's list `key`: LIST_KEYS + (key - 600) x LIST_SLOTS + entry
LOOK_LIST, LOOK_HASH, PINK_ENTRY = 635, 19999, 2
CHOICE_PORTRAIT = 1
END_TITLE, END_TEXT, END_ARGUMENT = 'End of game', 'Thanks for playing!', 4000      # as the smartphone's closing message
# A prime for each of a look list's 23 entries, for its hash (16-bit wrapping, as the machine's stored words).
HASH_FACTORS = (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89)


class StoryError(ValueError):
    pass


def upgrade(script):
    """A BREW script's KiWi v1 as v2: the machine is the same, and v2's header adds the link flag v1 can't set."""
    if script[:5] != b'kiwi\x01':
        raise StoryError('not a KiWi v1 script')
    return b'kiwi\x02\x00' + script[5:]


def look_hash(entries):
    """A look's hash, as the shims keep it. A list's unset entries read 0."""
    total = 0
    for factor, entry in zip(HASH_FACTORS, entries):
        total = signed16(total + signed16(entry * factor))
    return total


def title_of(archive_bytes):
    return archive_bytes.split(b'\r')[0].split(b'\n')[0].decode('cp1252').strip()


def clean_title(title):
    return title[len('Clsc. - '):] if title.startswith('Clsc. - ') else title


# -- what a story's calls become ---------------------------------------------------------------------------------------
def dropped(rewriter, pc, argc, context):
    rewriter.redirect(pc, 'drop', lambda s: s.result(0))


def get_global(s, key):
    s.push(key); s.call(55, 1); s.push_result()


def set_global(s, key, value):
    s.push(key); value(); s.call(54, 2)


def build_query(rewriter, pc, argc, context):
    """80: (selector) what the build is: 1 -> 2, 2 -> 1, 3 -> 5, else 0 ('08's answers)."""
    def build(s):
        done = s.label()
        for selector, answer in ((1, 2), (2, 1), (3, 5)):
            other = s.label()
            s.arg(1); s.push(selector); s.emit(0x0a); s.jump_if_zero(other)
            s.result(answer); s.jump(done)
            s.label(other)
        s.result(0)
        s.label(done)
    rewriter.redirect(pc, 'build_query', build)


def owned_set(rewriter, pc, argc, context):
    """58: (owner, key, value), with 407's icons following BREW's value."""
    def build(s):
        other, done = s.label(), s.label()
        s.arg(2); s.push(RELATIONSHIP); s.emit(0x0a); s.jump_if_zero(other)
        s.arg(1); s.push(RELATIONSHIP_BREW); s.arg(3); s.call(52, 3)
        relationship_icons(s, lambda: s.arg(1), lambda: s.arg(3))
        s.jump(done)
        s.label(other)
        s.arg(1); s.arg(2); s.arg(3); s.call(52, 3)
        s.label(done)
        s.result(0)
    rewriter.redirect(pc, 'owned_set', build)


def relationship_icons(s, owner, value):
    """SHS's 407 for a BREW value (screens.js relationshipIcons): below 20, 30 and 40 are 3, 2 and 1 skulls (-3, -2, -1), and from
    40, 66 and 76 are 1, 2 and 3 smileys or hearts (0, 1, 2)."""
    done = s.label()
    owner(); s.push(RELATIONSHIP)
    for limit, icons in ((20, -3), (30, -2), (40, -1), (66, 0), (76, 1)):
        other = s.label()
        value(); s.push(limit); s.emit(0x0e); s.jump_if_zero(other)
        s.push(icons); s.jump(done)
        s.label(other)
    s.push(2)
    s.label(done)
    s.call(52, 3)


def owned_get(rewriter, pc, argc, context):
    """59: (owner, key). The call left last gives the result."""
    def build(s):
        other, done = s.label(), s.label()
        s.arg(2); s.push(RELATIONSHIP); s.emit(0x0a); s.jump_if_zero(other)
        s.arg(1); s.push(RELATIONSHIP_BREW); s.call(53, 2); s.jump(done)
        s.label(other)
        s.arg(1); s.arg(2); s.call(53, 2)
        s.label(done)
    rewriter.redirect(pc, 'owned_get', build)


def cast_name(rewriter, pc, argc, context):
    """55, 71: (character, name). A name's trailing `~` only tells same-named characters apart (strip_name_marks takes it off).
    Unset, BREW's value is 0, which it shows as three skulls unless 629 hides them. A character named Event is the narrator, as on
    the smartphone, whose scripts give that name to the character they pass to service 75."""
    def build(s):
        other = s.label()
        s.arg(1); s.arg(2); s.call(64, 2)
        was_set = s.label()
        s.arg(1); s.push(RELATIONSHIP_BREW); s.call(53, 2); s.push_result(); s.jump_if_nonzero(was_set)
        s.arg(1); s.push(RELATIONSHIP); s.push(-3); s.call(52, 3)
        s.label(was_set)
        s.arg(2); s.text(EVENT_NAME); s.call(24, 2); s.push_result(); s.jump_if_zero(other)
        set_global(s, EVENT_CHARACTER_KEY, lambda: s.arg(1))
        s.label(other)
        s.result(0)
    rewriter.redirect(pc, ('cast_name', context['rid']), build)


def list_key(s, key, entry):
    """Push the number holding entry `entry` (a callable) of list `key` (a callable)."""
    key(); s.push(600); s.emit(0x51); s.push(LIST_SLOTS); s.emit(0x52); entry(); s.emit(0x50); s.push(LIST_KEYS); s.emit(0x50)


def list_write(s, entity, key, entry, value, context):
    """Store an entry, keep the list's length, and for a look list its hash, the look it now is and its box colour. Three locals
    come after whatever the caller has: this runs with none pushed before it."""
    longer, done = s.label(), s.label()
    # Local 0: the entry's old value.
    entity(); list_key(s, key, entry); s.call(53, 2); s.push_result()
    entity(); list_key(s, key, entry); value(); s.call(52, 3)
    # The length is one past the highest entry written.
    entity(); list_key(s, key, lambda: s.push(LIST_LENGTH)); s.call(53, 2); s.push_result()   # local 1
    entry(); s.emit(0x41, 1); s.emit(0x0d); s.jump_if_zero(longer)
    entity(); list_key(s, key, lambda: s.push(LIST_LENGTH)); entry(); s.push(1); s.emit(0x50); s.call(52, 3)
    s.label(longer)
    key(); s.push(LOOK_LIST); s.emit(0x0a); s.jump_if_zero(done)
    # Local 2: the new hash.
    entity(); s.push(LOOK_HASH); s.call(53, 2); s.push_result()
    value(); s.emit(0x41, 0); s.emit(0x51)
    s.push(context['hash_factors']); entry(); s.emit(0x50); s.emit(0x3f); s.emit(0x52)
    s.emit(0x50)
    entity(); s.push(LOOK_HASH); s.emit(0x41, 2); s.call(52, 3)
    # Local 3: the running offset through the table of (hash, bank).
    for hash_value, bank in context['looks']:
        other = s.label()
        s.emit(0x41, 2); s.push(hash_value); s.emit(0x0a); s.jump_if_zero(other)
        entity(); s.push(bank); s.call(72, 2)
        s.label(other)
    # BREW draws its pink box when entry 2 is 0.
    entry(); s.push(PINK_ENTRY); s.emit(0x0a); s.jump_if_zero(done)
    entity(); s.push(THEME)
    plain, end = s.label(), s.label()
    value(); s.jump_if_nonzero(plain)
    s.push(2); s.jump(end)
    s.label(plain); s.push(1)
    s.label(end)
    s.call(52, 3)
    s.label(done)


def list_set(rewriter, pc, argc, context):
    """64: (entity, key, entry, value)."""
    def build(s):
        list_write(s, lambda: s.arg(1), lambda: s.arg(2), lambda: s.arg(3), lambda: s.arg(4), context)
        s.result(0)
    rewriter.redirect(pc, ('list_set', context['rid']), build)


def list_push(rewriter, pc, argc, context):
    """62: (entity, key, value), up to 23 entries."""
    def build(s):
        full = s.label()
        s.arg(1); list_key(s, lambda: s.arg(2), lambda: s.push(LIST_LENGTH)); s.call(53, 2); s.push_result()   # local 0: the length
        s.emit(0x41, 0); s.push(brew_art.ENTRIES); s.emit(0x0e); s.jump_if_zero(full)
        # (The helper's locals start after this one.)
        _list_write_at(s, context)
        s.label(full)
        s.result(0)
    rewriter.redirect(pc, ('list_push', context['rid']), build)


def _list_write_at(s, context):
    """list_write with the length in local 0 as the entry, and its locals one higher."""
    done, longer_done = s.label(), s.label()
    entity, key, value = (lambda: s.arg(1)), (lambda: s.arg(2)), (lambda: s.arg(3))
    entry = lambda: s.emit(0x41, 0)
    entity(); list_key(s, key, entry); value(); s.call(52, 3)
    entity(); list_key(s, key, lambda: s.push(LIST_LENGTH)); entry(); s.push(1); s.emit(0x50); s.call(52, 3)
    key(); s.push(LOOK_LIST); s.emit(0x0a); s.jump_if_zero(done)
    # Local 1: the new hash. A pushed entry was unset, so it reads 0.
    entity(); s.push(LOOK_HASH); s.call(53, 2); s.push_result()
    value(); s.push(context['hash_factors']); entry(); s.emit(0x50); s.emit(0x3f); s.emit(0x52)
    s.emit(0x50)
    entity(); s.push(LOOK_HASH); s.emit(0x41, 1); s.call(52, 3)
    for hash_value, bank in context['looks']:
        other = s.label()
        s.emit(0x41, 1); s.push(hash_value); s.emit(0x0a); s.jump_if_zero(other)
        entity(); s.push(bank); s.call(72, 2)
        s.label(other)
    entry(); s.push(PINK_ENTRY); s.emit(0x0a); s.jump_if_zero(done)
    entity(); s.push(THEME)
    plain, end = s.label(), s.label()
    value(); s.jump_if_nonzero(plain)
    s.push(2); s.jump(end)
    s.label(plain); s.push(1)
    s.label(end)
    s.call(52, 3)
    s.label(done)
    del longer_done


def list_get(rewriter, pc, argc, context):
    """63: (entity, key, entry)."""
    rewriter.redirect(pc, 'list_get', lambda s: (s.arg(1), list_key(s, lambda: s.arg(2), lambda: s.arg(3)), s.call(53, 2)))


def list_length(rewriter, pc, argc, context):
    """65: (entity, key)."""
    rewriter.redirect(pc, 'list_length', lambda s: (s.arg(1), list_key(s, lambda: s.arg(2), lambda: s.push(LIST_LENGTH)), s.call(53, 2)))


def push_picture(s, location, sky):
    """Push the addon's picture of a location under a sky mode (-1: by the clock). Two locals' worth of work on the stack only."""
    night, day, picked, add = s.label(), s.label(), s.label(), s.label()
    extra, have, placed = s.label(), s.label(), s.label()
    location(); s.push(0); s.emit(0x0e); s.jump_if_zero(placed)
    s.push(SKY_ONLY); s.jump(have)
    s.label(placed)
    location(); s.push(2000); s.emit(0x0e); s.jump_if_zero(extra)
    location(); s.push(1000); s.emit(0x51); s.jump(have)
    s.label(extra)
    location(); s.push(2000 - LOCATIONS_08); s.emit(0x51)
    s.label(have)
    s.push(SKY_MODES); s.emit(0x52); s.push(BACKGROUND_BASE); s.emit(0x50)
    sky(); s.push(0); s.emit(0x0e); s.jump_if_zero(picked)
    s.push(CLOCK_KEY); s.call(55, 1); s.push_result(); s.push(NIGHT_FROM); s.emit(0x0d); s.jump_if_zero(day)
    s.jump(night)
    s.label(picked)
    sky(); s.jump(add)
    s.label(night)
    s.push(1); s.jump(add)
    s.label(day)
    s.push(0)
    s.label(add)
    s.emit(0x50)


def show_top_scene(s):
    """SHS's background for the top scene."""
    s.push(0)
    get_depth = lambda: (s.push(DEPTH_KEY), s.call(55, 1), s.push_result())
    top = lambda base: (lambda: (s.push(base), get_depth(), s.emit(0x50), s.call(55, 1), s.push_result()))
    push_picture(s, top(SCENE_LOCATION_KEY), top(SCENE_SKY_KEY))
    s.call(11, 2)


def scene_open(rewriter, pc, argc, context):
    """13: (sky mode, location) a new scene on the stack, with no speaker; returns 1."""
    def build(s):
        depth = lambda: (s.push(DEPTH_KEY), s.call(55, 1), s.push_result())
        s.push(DEPTH_KEY); depth(); s.push(1); s.emit(0x50); s.call(54, 2)
        s.push(SCENE_LOCATION_KEY); depth(); s.emit(0x50); s.arg(2); s.call(54, 2)
        s.push(SCENE_SKY_KEY); depth(); s.emit(0x50); s.arg(1); s.call(54, 2)
        set_global(s, SPEAKER_KEY, lambda: s.push(-1))
        show_top_scene(s)
        s.result(1)
    rewriter.redirect(pc, 'scene_open', build)


def scene_change(rewriter, pc, argc, context):
    """14: (speaker, sky mode, location, expression): speaker -1 keeps the speaker, -2 clears it, and an expression only comes with a
    speaker, where -1 means the default face. Sky and location -1 keep theirs."""
    def build(s):
        keep, shown, change = s.label(), s.label(), s.label()
        depth = lambda: (s.push(DEPTH_KEY), s.call(55, 1), s.push_result())
        s.arg(1); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(keep)
        set_global(s, SPEAKER_KEY, lambda: s.arg(1))
        set_global(s, EXPRESSION_KEY, lambda: s.arg(4))
        s.label(keep)
        no_sky, no_location = s.label(), s.label()
        s.arg(2); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(no_sky)
        s.push(SCENE_SKY_KEY); depth(); s.emit(0x50); s.arg(2); s.call(54, 2)
        s.label(no_sky)
        s.arg(3); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(no_location)
        s.push(SCENE_LOCATION_KEY); depth(); s.emit(0x50); s.arg(3); s.call(54, 2)
        s.label(no_location)
        s.arg(2); s.push(-1); s.emit(0x0a); s.jump_if_zero(change)
        s.arg(3); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(shown)
        s.label(change)
        show_top_scene(s)
        s.label(shown)
        s.result(0)
    rewriter.redirect(pc, 'scene_change', build)


def scene_close(rewriter, pc, argc, context):
    """18: the top scene goes, and the one underneath comes back with its picture."""
    def build(s):
        done = s.label()
        depth = lambda: (s.push(DEPTH_KEY), s.call(55, 1), s.push_result())
        s.push(DEPTH_KEY); depth(); s.push(1); s.emit(0x51); s.call(54, 2)
        depth(); s.push(1); s.emit(0x0e); s.jump_if_nonzero(done)
        show_top_scene(s)
        s.label(done)
        s.result(0)
    rewriter.redirect(pc, 'scene_close', build)


def push_face(s, expression):
    """A look's bank index for a BREW expression: 2-4 are their own faces, and anything else the default."""
    other, done = s.label(), s.label()
    expression(); s.push(2); s.emit(0x0d); expression(); s.push(4); s.emit(0x0f); s.emit(0x12); s.jump_if_zero(other)
    expression(); s.push(1); s.emit(0x51); s.jump(done)
    s.label(other)
    s.push(0)
    s.label(done)


def say(s, text, speaker, expression, context):
    """SHS's dialogue for `text` under BREW's speaker (callables pushing them): no speaker or Event is the narrator, a character
    with no picture says it under its name with none (service 76), and anyone else with their face."""
    narrated, voice, done = s.label(), s.label(), s.label()
    speaker(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(narrated)
    speaker(); s.push(EVENT_CHARACTER_KEY); s.call(55, 1); s.push_result(); s.emit(0x0a); s.jump_if_nonzero(narrated)
    speaker(); s.call(73, 1); s.push_result(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(voice)
    text(); speaker(); push_face(s, expression); s.call(13, 3)
    s.jump(done)
    s.label(voice)
    speaker(); s.push(context['name_buffer']); s.call(61, 2)
    s.push(context['name_buffer']); text(); s.call(76, 2)
    s.jump(done)
    s.label(narrated)
    text(); s.push(NARRATOR); s.call(13, 2)
    s.label(done)


def line(rewriter, pc, argc, context):
    """72: (speaker, text, expression), dropped with no scene open (shs08.5.mod)."""
    def build(s):
        done = s.label()
        s.push(context['last_line']); s.arg(2); s.emit(0x3e); s.emit(0x15)
        s.push(DEPTH_KEY); s.call(55, 1); s.push_result(); s.push(1); s.emit(0x0e); s.jump_if_nonzero(done)
        set_global(s, SPEAKER_KEY, lambda: s.arg(1))
        set_global(s, EXPRESSION_KEY, lambda: s.arg(3))
        say(s, lambda: s.arg(2), lambda: s.arg(1), lambda: s.arg(3), context)
        s.label(done)
    rewriter.redirect(pc, ('line', context['rid']), build)


def narration_queue(rewriter, pc, argc, context):
    """16: (text) the line 74 shows."""
    rewriter.redirect(pc, ('narration', context['rid']),
                      lambda s: (s.push(context['narration']), s.arg(1), s.emit(0x3e), s.emit(0x15), s.result(0)))


def menu(rewriter, pc, argc, context):
    """28: (title, `a|b|c`) the menu 74 shows; returns 1."""
    def build(s):
        s.push(context['menu']); s.arg(1); s.emit(0x3e); s.emit(0x15)
        s.push(context['menu'] + 1); s.arg(2); s.emit(0x3e); s.emit(0x15)
        s.result(1)
    rewriter.redirect(pc, ('menu', context['rid']), build)


def wait(rewriter, pc, argc, context):
    """74: shows the pending menu or narration line. A menu's answer also goes in field 0."""
    def build(s):
        no_menu, done = s.label(), s.label()
        s.emit(0x40, context['menu'] + 1); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(no_menu)
        s.emit(0x40, context['menu']); s.emit(0x40, context['menu'] + 1); s.emit(0x40, context['last_line'])
        s.push(-1); s.push(0); s.push(-2); s.push(-1); s.push(CHOICE_PORTRAIT)
        s.call(1, 8)
        s.push_result()
        s.push(context['menu'] + 1); s.push(-1); s.emit(0x3e); s.emit(0x15)
        set_global(s, FIELD_KEY, lambda: s.emit(0x41, 0))
        s.push(FIELD_KEY); s.call(55, 1)
        s.jump(done)
        s.label(no_menu)
        none = s.label()
        s.emit(0x40, context['narration']); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(none)
        say(s, lambda: s.emit(0x40, context['narration']), lambda: (s.push(SPEAKER_KEY), s.call(55, 1), s.push_result()),
            lambda: (s.push(EXPRESSION_KEY), s.call(55, 1), s.push_result()), context)
        s.push(context['narration']); s.push(-1); s.emit(0x3e); s.emit(0x15)
        s.label(none)
        s.result(0)
        s.label(done)
    rewriter.redirect(pc, ('wait', context['rid']), build)


def field(rewriter, pc, argc, context):
    """8: (i) a field of the current event."""
    rewriter.redirect(pc, 'field', lambda s: (s.arg(1), s.push(FIELD_KEY), s.emit(0x50), s.call(55, 1)))


def field_set(rewriter, pc, argc, context):
    """35: (event, field, value). A Campaign story has one event, so its fields are simply the current ones."""
    rewriter.redirect(pc, 'field_set', lambda s: (s.arg(2), s.push(FIELD_KEY), s.emit(0x50), s.arg(3), s.call(54, 2), s.result(0)))


def event_text(rewriter, pc, argc, context):
    """7: (destination) the event's text."""
    def build(s):
        s.text(EVENT_TEXT); s.text(''); s.push(-1); s.call(47, 3); s.push_result()
        s.arg(1); s.text('%s'); s.emit(0x41, 0); s.call(22, 3)
        s.result(0)
    rewriter.redirect(pc, ('event_text', context['rid']), build)


def schedule(rewriter, pc, argc, context):
    """33: (script, text, name, caption, month, day, minute, duration, icon, flag). A Campaign story's one event: its script is
    queued, its text and clock kept. Returns the event's ID."""
    if context['kind'] != 'single':
        raise StoryError('this story schedules more than one event, which needs the calendar driver')

    def build(s):
        s.text(EVENT_TEXT); s.arg(2); s.call(46, 2)
        set_global(s, CLOCK_KEY, lambda: s.arg(7))
        s.arg(1); s.push(BREW_STORY_SCRIPT); s.emit(0x51); s.push(STORY_SCRIPT); s.emit(0x50); s.push(0); s.call(10, 2)
        s.result(1)
    rewriter.redirect(pc, ('schedule', context['rid']), build)


def music(rewriter, pc, argc, context):
    """9: (track) plays once; a short MIDI cue on the phones, so it stops nothing else."""
    rewriter.redirect(pc, 'music', lambda s: (s.arg(1), s.push(8000), s.emit(0x51), s.push(MUSIC_BASE), s.emit(0x50), s.push(0),
                                              s.call(80, 2), s.result(0)))


def stored_text_get(rewriter, pc, argc, context):
    """53: (`$KEY`, destination)."""
    def build(s):
        s.arg(1); s.text(''); s.push(-1); s.call(47, 3); s.push_result()
        s.arg(2); s.text('%s'); s.emit(0x41, 0); s.call(22, 3)
        s.result(0)
    rewriter.redirect(pc, ('stored_text_get', context['rid']), build)


def player_name(rewriter, pc, argc, context):
    """49: (text) `$USR`."""
    rewriter.redirect(pc, ('player_name', context['rid']), lambda s: (s.text('$USR'), s.arg(1), s.call(46, 2), s.result(0)))


def titled_page(rewriter, pc, argc, context):
    """12: (title, text) -> SHS 33."""
    rewriter.redirect(pc, 'titled_page', lambda s: (s.arg(1), s.arg(2), s.push(0), s.call(33, 3)))


def the_end(rewriter, pc, argc, context):
    """70: the smartphone's closing message and the episode's exit."""
    rewriter.redirect(pc, ('end', context['rid']), lambda s: (s.text(END_TITLE), s.text(END_TEXT), s.push(END_ARGUMENT), s.call(33, 3),
                                                              s.call(7, 0)))


HANDLERS = {7: event_text, 8: field, 9: music, 12: titled_page, 13: scene_open, 14: scene_change, 16: narration_queue, 18: scene_close,
            28: menu, 33: schedule, 35: field_set, 49: player_name, 53: stored_text_get, 55: cast_name, 58: owned_set, 59: owned_get,
            62: list_push, 63: list_get, 64: list_set, 65: list_length, 70: the_end, 71: cast_name, 72: line, 74: wait, 80: build_query}
# No-ops in BREW (0, 2, 10, 22-26, 32, 54, 75-79); the calendar's setup where there's no calendar (69); art registration, since
# the addon holds the art (11).
DROPPED = {0, 2, 10, 11, 22, 23, 24, 25, 26, 32, 54, 69, 75, 76, 77, 78, 79}
RENAME = {1: 22,                         # (destination, format, values...)
          3: 24,                         # string equality
          4: 25,                         # concatenate
          6: 27,                         # random below a bound
          50: 54, 60: 54, 51: 55, 61: 55,    # global numbers
          52: 46,                        # (`$KEY`, text)
          68: 61,                        # character name to memory
          73: 66}                        # weighted random


def strip_name_marks(program):
    """A program with `~` taken off the ends of its short strings with no spaces before it: only names end in one, to tell
    same-named characters apart (`Girl~`, `Girl~~`, `$USR~`), and neither the name plate nor a `$` token shows it."""
    words = list(program.main_words)
    out, start = list(words), 0
    while start < len(words):
        end, text = start, bytearray()
        finished = False
        while end < len(words) and not finished:
            for byte in (words[end] >> 8, words[end] & 255):
                if byte == 0:
                    finished = True
                    break
                text.append(byte)
            end += 1
        if text.endswith(b'~') and len(text) < 40:
            kept = text.rstrip(b'~') + b'\0'
            kept += b'\0' * (2 * (end - start) - len(kept))
            for offset in range(end - start):
                out[start + offset] = kept[2 * offset] << 8 | kept[2 * offset + 1]
        start = end
    from dataclasses import replace
    return replace(program, main_words=tuple(out))


def opening_picture(story):
    """The first background a story shows, found by playing it that far: its title card's picture. Scripts choose it through
    helpers, so it can't be read from the code. -1 if it asks for an answer first."""
    import playthrough
    session = playthrough.session(story)
    action = session.advance()
    for _ in range(200):
        while session.transitioning:
            action = session.tick(session.engine.scene_transition.duration_ms)
        if session.engine.panel.background_id >= 0:
            return session.engine.panel.background_id
        action = action or session.pending
        if action is None:
            break
        if action.name == 'presentation':
            action = session.tick(4000)
            if session.pending is not None and session.pending.name == 'presentation':
                action = session.answer()
        elif action.name == 'loading':
            action = session.tick(2000)
        else:
            break
    return -1


def translate(archive_resources, name, spec, pack=PACK_CAMPAIGN, episode=0, suffix=TITLE_SUFFIX_08):
    """A story's SHS `.exp` bytes, from its resources by ID and the addon's spec. Twice over: its title card shows the first
    picture the story does, which takes the story itself to find."""
    return _translate(archive_resources, name, spec, pack, episode, suffix,
                      opening_picture(_translate(archive_resources, name, spec, pack, episode, suffix, -1)))


def _translate(archive_resources, name, spec, pack, episode, suffix, card):
    looks = spec['stories'].get(name)
    if looks is None:
        raise StoryError(f'the addon has no looks for {name}')
    table = {}
    for key, bank in looks.items():
        entries = [int(v) for v in key.split(',')]
        table[look_hash(entries)] = bank
    title = clean_title(title_of(archive_resources[1]))
    scripts = sorted(rid for rid, data in archive_resources.items() if data[:4] == b'kiwi')
    extra = [rid for rid in scripts if rid not in (FIRST_SCRIPT, BREW_STORY_SCRIPT)]
    if extra:
        raise StoryError(f'{name}: scripts {extra} need the calendar driver or a script map')
    resources = {}
    for script in scripts:
        program = strip_name_marks(decode_program(upgrade(archive_resources[script])))
        rewriter = Rewriter(program, zero_gap=True)
        context = dict(rid=script, kind='single', looks=sorted(table.items()), hash_factors=rewriter.words(HASH_FACTORS),
                       last_line=rewriter.words([-1]), narration=rewriter.words([-1]), menu=rewriter.words([-1, -1]),
                       name_buffer=rewriter.words([0] * NAME_WORDS))
        for pc, service, argc in rewriter.calls():
            if service in RENAME:
                rewriter.rename(pc, RENAME[service])
            elif service in DROPPED:
                dropped(rewriter, pc, argc, context)
            elif service in HANDLERS:
                HANDLERS[service](rewriter, pc, argc, context)
            else:
                raise StoryError(f'{name}, script {script}: service {service} with {argc} arguments has no translation yet')
        if script == FIRST_SCRIPT:
            rewriter.prologue(lambda s: (s.push(NARRATOR), s.call(75, 1), s.push(PLAYER), s.call(74, 1),
                                         s.push(EVENT_CHARACTER_KEY), s.push(-1), s.call(54, 2),
                                         s.push(NARRATOR), s.text(''), s.call(64, 2),
                                         s.push(NARRATOR), s.push(-1), s.call(72, 2)))
        else:
            rewriter.prologue(lambda s: (s.text(title), s.text(''), s.push(card), s.push(0), s.call(8, 4)))
        target = STORY_SCRIPT if script == BREW_STORY_SCRIPT else FIRST_SCRIPT
        resources[target] = rewriter.finish().to_bytes()
    resources[ADDON_RECORD] = requires_bytes([(ADDON_ID, ADDON_REVISION)])
    resources[1] = Metadata(pack, episode, (title + suffix,) * 5).to_bytes()
    return encode_exp(resources)


def campaign_number(name):
    """A Campaign file's episode number: 1.2 is 102, with the quizzes and specials past the chapters. By-date placing is the game
    profile's (LEGACY_GAMES `order`)."""
    stem = Path(name).stem.lower()
    if '_pt1' in stem:
        return 101
    if (match := re.search(r'quiz_(\d+)', stem)):
        return 9000 + int(match.group(1))
    if (match := re.search(r'_sp(\d+)_', stem)):
        return 9100 + int(match.group(1))
    if (match := re.search(r'shs085_(\d+)_(\d+)_', stem)):
        return int(match.group(1)) * 100 + int(match.group(2))
    raise StoryError(f'{name} has no Campaign number')


def file_name(title, suffix):
    return re.sub(r'\W+', '_', title).strip('_') + suffix.strip().strip('()').join(('_', '')) + '.exp'


def build_story(path, addon_path):
    """(file name, bytes) of a Campaign story, from its file and the addon."""
    path = Path(path)
    archive = ExpArchive(Path(addon_path).read_bytes())
    spec = json.loads(archive.read(SPEC))
    resources = read_archive(path)
    story = translate(resources, path.name, spec, PACK_CAMPAIGN, campaign_number(path.name), TITLE_SUFFIX_08)
    return file_name(clean_title(title_of(resources[1])), TITLE_SUFFIX_08), story


# -- the addon ---------------------------------------------------------------------------------------------------------
def load_pack(path):
    return nr_art.load(Path(path))


def story_packs(entry, games, bases):
    """The packs a catalogue entry's story draws from, its own first, and its registered sheets."""
    file = entry['file']
    base = bases['07'] if entry['kind'] == 'season07' or file.startswith('32411') else bases['08']
    if file.startswith('32411/'):
        return [load_pack(games['07'] / file.split('/', 1)[1]), base]
    if file.endswith('res_xlarge.pud'):
        return [base]
    return [load_pack(games['08'] / file), base]


def clear_edges(picture):
    return picture


def faces_of(art, entries):
    """A look's five faces at the portrait's scale, or None for a voice with no picture: BREW's 1-4 and the default again."""
    pictures = [brew_art.portrait(art, entries, expression) for expression in (1, 2, 3, 4, 1)]
    if pictures[0] is None or pictures[0].getbbox() is None:
        return None
    return pictures


def portrait_box(canvas_size):
    """The part of a portrait canvas every bank keeps. Scaled up, it's exactly twice the player's 128 x 150 portrait mask, which the
    player reads as 2x art and shows evenly (desktop_dialogue._episode_portrait_size: anything larger is squeezed into the mask's
    shape, out of proportion). BREW stands a portrait on the bar 32 pixels below its portrait point, and PORTRAIT_LIFT raises it from
    the bottom of the picture, which the ring hides, so the whole bust shows."""
    width, height = canvas_size
    bottom = height // 2 + 32 + PORTRAIT_LIFT
    return width // 2 - PORTRAIT_SIZE[0] // 2, bottom - PORTRAIT_SIZE[1], width // 2 + PORTRAIT_SIZE[0] // 2, bottom


def portrait_picture(face):
    """A portrait at 3.5 times its pixels, the owner's choice between 3 and 4 by the look of the ring (2026-11-05). Seven times with no
    smoothing, then halved, so every art pixel is the same size: a plain 3.5 times would alternate 3 and 4. The player scales the
    picture to the window afterwards anyway."""
    big = face.resize((face.width * 7, face.height * 7), Image.NEAREST)
    return big.resize((big.width // 2, big.height // 2), Image.BOX)


def build_addon(casts, games, render_music=None):
    """The addon's resources and spec, from the portrait catalogue's casts (brew_casts.json) and the games' folders: `games`
    {'08': the '08 folder, '07: the VX9800 module folder}. Every look any story shows, every location at every sky, the music,
    the relationship icons and the frame's backdrop."""
    bases = dict(zip(('08', '07'), (load_pack(games['08'] / 'game/SHS/res_xlarge.pud'), load_pack(games['07'] / 'res_xlarge.pud'))))
    resources, spec = {}, dict(format=SPEC_FORMAT, version=SPEC_VERSION, stories={}, looks=[])
    art08, art07 = brew_art.Art([bases['08']]), brew_art.Art([bases['07']])
    for index in range(LOCATIONS_08 + LOCATIONS_08_EXTRA):
        location = 1000 + index if index < LOCATIONS_08 else 2000 + index - LOCATIONS_08
        for sky in range(SKY_MODES):
            scene = brew_art.location(art08, location, sky)
            if scene is not None:
                resources[BACKGROUND_BASE + SKY_MODES * index + sky] = strip_png(scene)
    for index in range(LOCATIONS_08):
        for sky in range(SKY_MODES):
            scene = brew_art.location(art07, 1000 + index, sky)
            if scene is not None:
                resources[BACKGROUND_BASE + SKY_MODES * (LOCATION_07_OFFSET + index) + sky] = strip_png(scene)
    for sky in range(SKY_MODES):
        resources[BACKGROUND_BASE + SKY_MODES * SKY_ONLY + sky] = strip_png(brew_art.sky(sky))
    banks, loaded, clipped = {}, {}, []
    for entry in casts:
        file = entry['file']
        if file not in loaded:
            loaded[file] = story_packs(entry, games, bases)
        art = brew_art.Art(loaded[file], [tuple(sheet) for sheet in entry.get('sheets', [])])
        looks = {}
        for member in entry.get('shown', []) + entry.get('defined', []):
            key = ','.join(str(value) for value in member['list'])
            if key in looks:
                continue
            faces = faces_of(art, member['list'])
            if faces is None:
                looks[key] = -1
                continue
            box = portrait_box(faces[0].size)
            for face in faces:
                drawn = face.getbbox()
                if drawn and not (box[0] <= drawn[0] and box[1] <= drawn[1] and drawn[2] <= box[2] and drawn[3] <= box[3]):
                    clipped.append((file, member['name'], drawn))
            cropped = [face.crop(box) for face in faces]
            print_key = hashlib.sha256(b''.join(face.tobytes() for face in cropped)).hexdigest()
            if print_key not in banks:
                banks[print_key] = PORTRAIT_BASE + EXPRESSIONS * len(banks)
                for offset, face in enumerate(cropped):
                    resources[banks[print_key] + offset] = brew_art.png(portrait_picture(face))
                spec['looks'].append(dict(id=banks[print_key], first=member['name'], story=file))
            looks[key] = banks[print_key]
        spec['stories'][Path(file).name] = looks
    spec['clipped'] = sorted({(file, name) for file, name, _ in clipped})
    if render_music is not None:
        for track in range(MUSIC_TRACKS):
            data = bases['08'].get(8000 + track)
            if data is not None:
                resources[MUSIC_BASE + track] = render_music(data)
    resources.update(badge_pictures(art08))
    resources[FRAME_BACKDROP] = frame_backdrop(art08)
    resources[PINK_BACKDROP] = frame_backdrop(art08, PINK_PANEL_FRAME)
    resources[SPEC] = json.dumps(spec, separators=(',', ':')).encode()
    resources[ADDON_RECORD] = provides_bytes(ADDON_ID, ADDON_TITLE, ADDON_REVISION)
    resources[1] = Metadata(PACK_CAMPAIGN, ADDON_EPISODE, (ADDON_TITLE + ' (addon)',) * 5).to_bytes()
    return encode_exp(resources), spec


def strip_png(scene):
    return brew_art.png(scene.resize((scene.width * BACKGROUND_SCALE, scene.height * BACKGROUND_SCALE), Image.NEAREST).quantize(255))


BADGE_MARGIN = 2
BROKEN_GAP = 2


def badge_pictures(art):
    """{resource: PNG} of BREW's relationship icons, whole and broken: BREW's own icons never break, so a broken one is the whole
    one parted down its middle, for the smartphone's loss animation."""
    found = {}
    for number, name in enumerate(('heart', 'skull', 'smiley')):
        picture = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        art.draw(picture, brew_art.RELATIONSHIP_ART[name], 8, 8)
        picture = picture.crop(picture.getbbox())
        whole = Image.new('RGBA', (picture.width + 2 * BADGE_MARGIN, picture.height + 2 * BADGE_MARGIN), (0, 0, 0, 0))
        whole.paste(picture, (BADGE_MARGIN, BADGE_MARGIN))
        half = picture.width // 2
        broken = Image.new('RGBA', whole.size, (0, 0, 0, 0))
        broken.paste(picture.crop((0, 0, half, picture.height)), (BADGE_MARGIN - BROKEN_GAP // 2, BADGE_MARGIN))
        broken.paste(picture.crop((half, 0, picture.width, picture.height)), (BADGE_MARGIN + half + BROKEN_GAP // 2, BADGE_MARGIN))
        found[BADGE_BASE + number] = brew_art.png(whole)
        found[BADGE_BASE + 3 + number] = brew_art.png(broken)
    return found


PANEL_FRAME, PINK_PANEL_FRAME, BAR_FRAME = 12 + 2, 12 + 3, 12 + 30  # BREW's dialogue layout: the panel's tiles and the bar under the location


def frame_backdrop(art, panel=PANEL_FRAME):
    """What SHS's frame shows around BREW's short strip: BREW's dialogue panel tiled at the strip's density, with its bar just above
    and below where the runtime shows the strip, like New Rules' (nr_art.Art.backdrop)."""
    per_unit = STRIP_WIDTH / nr_art.BACKGROUND_UNITS            # art pixels per frame unit
    width, height = (round(side * per_unit) for side in nr_art.FRAME_UNITS)
    canvas = Image.new('RGBA', (width, height), (*BACKDROP_COLOUR, 255))
    tile = _frame_of(art, panel)
    if tile is not None:
        for x in range(0, width, tile.width):
            for y in range(0, height, tile.height):
                canvas.alpha_composite(tile, (x, y))
    image = canvas.convert('RGB').resize((width * BACKGROUND_SCALE, height * BACKGROUND_SCALE), Image.NEAREST)
    bar = _frame_of(art, BAR_FRAME)
    if bar is not None:
        bar = bar.resize((bar.width * BACKGROUND_SCALE, bar.height * BACKGROUND_SCALE), Image.NEAREST)
        pixels = per_unit * BACKGROUND_SCALE
        half = STRIP_HEIGHT * nr_art.BACKGROUND_UNITS / STRIP_WIDTH / 2
        for edge, row in ((nr_art.STRIP_CENTRE_UNITS - half, -bar.height), (nr_art.STRIP_CENTRE_UNITS + half, 0)):
            y = round(edge * pixels) + row
            for x in range(0, image.width, bar.width):
                image.paste(bar, (x, y), bar)
    return brew_art.png(image.quantize(255))


def _frame_of(art, art_id):
    """One sprite frame on its own, or None."""
    bounds = art.bounds(art_id)
    if not bounds or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        return None
    canvas = Image.new('RGBA', (bounds[2] - bounds[0], bounds[3] - bounds[1]), (0, 0, 0, 0))
    art.draw(canvas, art_id, -bounds[0], -bounds[1])
    return canvas


def read_archive(path):
    archive = ExpArchive(Path(path).read_bytes())
    return {rid: archive.read(rid) for rid in archive.entries}
