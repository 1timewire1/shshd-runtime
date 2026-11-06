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
  hash. When the character is next shown, a changed hash is looked up in the story's table of the looks it can reach (from the
  catalogue), and the character is pointed at that look's bank of faces: searching at every write would run past the Session's
  instruction budget in a setup with a big cast. Entry 2 picks the dialogue box's colour, as BREW's pink one does.
- **Scenes.** 13 pushes a scene and 18 closes the top one, so what's underneath comes back. The stack lives in saved numbers.
- **Word games.** Every story with timed menus has the same routine: several rounds of a spinning menu, drawn from a list of words each
  with a score, returning the total. That's a word game, so it plays as service 71, with the result scaled onto the routine's total
  so that each band its story tests stays reachable. A single round is a question, not a game, and stays a timed choice.
- **Brackets.** BREW puts narration and thoughts alike in `(...)`. Narration loses them, and a character's lines in them become SHS's
  thoughts, which adds its own.

Nothing here keeps art: a story holds only its scripts, and reads pictures and music from the addon (build_addon).
"""
import hashlib
import json
from pathlib import Path
import re
import sys

from PIL import Image, ImageDraw

from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes, requires_bytes
from exp_runtime.decode.bytecode import decode_program
from exp_runtime.exp import ExpArchive, Metadata, encode_exp
from exp_runtime.vm import signed16

sys.path.insert(0, str(Path(__file__).resolve().parent))

import brew_art  # noqa: E402
from exp_runtime.brew_services import ANGLED, BREW_CATCH, BREW_MINIGAMES_QUERY, ORBIT, SIDEWAYS  # noqa: E402
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
CATCH_BASE = 26300                      # the catch game's frame, ring, digits and captions, then its pictures
MUSIC_BASE, MUSIC_TRACKS = 26900, 15    # 8000-8014
# Sorted by ear (owner, 2026-11-05): these play as sound effects, the rest as music. The game itself plays all of them the same way.
SOUND_TRACKS = frozenset({1, 4, 8, 9, 11, 12})
# 8011 is the correct chime and 8001 the incorrect one (owner): the runtime's Answer hints read them (shs/profile.py).
FEEDBACK_TRACKS = {11: 1, 1: -1}
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
LOOK_LIST, LOOK_HASH, LOOK_SHOWN, PINK_ENTRY = 635, 19999, 19998, 2
CHOICE_PORTRAIT = 1
CHOICE_TITLE = 'Make your choice!'      # for a quiz: the real player answers, as in New Rules' Train That Brain!
TIMED_TITLE = 'Think fast!'             # as the smartphone titles its timed choices
WORD_GAME_MS, WORD_GAME_REFRESH_MS, WORD_GAME_PASS = 20000, 3000, 6     # as the smartphone calls service 71 (as shs11_story)
LIST_WORDS = 160                        # room for a word game's list, built at run time
# The catch game. Pictures it shows, each with two words for the word game in its place (the owner's switch off). The art has no names:
# these are by eye, and from what the stories call them on the page before.
CATCH_WORDS = {80: ('Heart', 'Love'), 82: ('Smiley', 'Grin'), 102: ('Paintbrush', 'Paint'), 103: ('Dumbbell', 'Weights'), 104: ('Basketball', 'Hoops'),
               107: ('Blue helmet', 'Blue team'), 108: ('Books', 'Studying'), 109: ('Eye roll', 'Boredom'), 110: ('Whispers', 'Gossip'),
               111: ('Burger', 'Lunch'), 113: ('Red car', 'Hot rod'), 114: ('Blue car', 'Sports car'), 116: ('Cross', 'Prayer'),
               117: ('Plate', 'Dinner'), 119: ('Flowers', 'Bouquet'), 120: ('Football', 'Pass'), 122: ('Fried egg', 'Breakfast'),
               123: ('Garlic', 'Clove'), 125: ('Glasses', 'Laser eyes'), 127: ('Sneaker', 'Fast feet'), 128: ('Laughter', 'Giggles'),
               130: ('Lightning', 'Bolt'), 131: ('Lips', 'Kiss'), 133: ('Hearts', 'Romance'), 134: ('Pi', 'Math'), 136: ('Cash', 'Money'),
               137: ('Sunrise', 'Sunshine'), 138: ('Music', 'Tune'), 140: ('X', 'Mistake'), 143: ('Cell phone', 'Text'), 144: ('Phone', 'Call'),
               145: ('Pow!', 'Wham!'), 146: ('Fist', 'Punch'), 148: ('Red helmet', 'Red team'), 149: ('Runner', 'Sprint'), 150: ('Salad', 'Side dish'),
               151: ('Scared', 'Nervous'), 152: ('Happy', 'Smile'), 154: ('Test tube', 'Chemistry'), 155: ('Shakespeare', 'Bust'), 156: ('Zzz', 'Sleep'),
               157: ('Steak', 'Meat'), 158: ('Suit', 'Tuxedo'), 160: ('Taco', 'Snack'), 162: ('Ticket', 'Coupon'), 163: ('Toilet', 'Flush'),
               164: ('TV', 'Channel'), 165: ('Zombie', 'Brains'), 166: ('House', 'Home'), 279: ('Snake', 'Slither')}
CATCH_GOOD_WORDS, CATCH_BAD_WORDS = ('Catch it!', 'Grab it!'), ('Dodge it!', 'Avoid it!')   # where a story's own pictures have no words
CATCH_TITLE, CATCH_TEXT = 'Think fast!', 'Catch the good things. Dodge the bad.'
# The catch game's own points, which mean nothing in the word game played in its place (`45 pts to pass.`, `55 points to win!`); its
# generic page title, which becomes the smartphone's banner there (its word games are titled `Snacks!`, `Fight!` and the like).
CATCH_POINTS = re.compile(rb'\s*\d+\s*(?:pts|points)\s+to\s+(?:pass|win)\s*[.!]?', re.I)
CATCH_GENERIC_TITLE = b'Instructions'
CATCH_MODES = {19: ORBIT, 20: ANGLED, 21: SIDEWAYS}
CATCH_LIST_WORDS = 192                  # a word game's lists in its place: up to 14 kinds of item, two words each
CATCH_FIELD_COLOUR, CATCH_PANEL_COLOUR = (0x44, 0x44, 0xFF), (0xFF, 0xEB, 0xD3)
CATCH_EDGE_DARK, CATCH_EDGE_LIGHT = (0x75, 0x95, 0xAE), (0xC3, 0xCC, 0xCE)
CATCH_SCALE = 3
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
        for selector, answer in ((3, 5), (1, 2), (2, 1)):        # (3 first: setups ask it for every portrait part)
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


def push_list_base(s, key):
    """Push the number the first entry of list `key` is held in. A setup writes hundreds of entries, so the shims keep this in a
    local and do as little as they can per entry."""
    key(); s.push(600); s.emit(0x51); s.push(LIST_SLOTS); s.emit(0x52); s.push(LIST_KEYS); s.emit(0x50)


def list_store(s, entity, key, base, entry, value, old, context):
    """Store an entry and, in a look list, keep its hash and BREW's box colour: entry 2 at 0 is the pink box. `base` pushes the list's
    first number, `old` what the entry held."""
    done = s.label()
    entity(); base(); entry(); s.emit(0x50); value(); s.call(52, 3)
    key(); s.push(LOOK_LIST); s.emit(0x0a); s.jump_if_zero(done)
    entity(); s.push(LOOK_HASH)
    entity(); s.push(LOOK_HASH); s.call(53, 2); s.push_result()
    value(); old(); s.emit(0x51)
    s.push(context['hash_factors']); entry(); s.emit(0x50); s.emit(0x3f); s.emit(0x52)
    s.emit(0x50)
    s.call(52, 3)
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
    """64: (entity, key, entry, value). The length is one past the highest entry written."""
    def build(s):
        entity, key, entry, value = (lambda: s.arg(1)), (lambda: s.arg(2)), (lambda: s.arg(3)), (lambda: s.arg(4))
        base = lambda: s.emit(0x41, 0)
        shorter = s.label()
        push_list_base(s, key)                                                                  # local 0: the list's first number
        entity(); base(); entry(); s.emit(0x50); s.call(53, 2); s.push_result()                 # local 1: the old value
        list_store(s, entity, key, base, entry, value, lambda: s.emit(0x41, 1), context)
        entity(); base(); s.push(LIST_LENGTH); s.emit(0x50); s.call(53, 2); s.push_result()     # local 2: the length
        entry(); s.emit(0x41, 2); s.emit(0x0d); s.jump_if_zero(shorter)
        entity(); base(); s.push(LIST_LENGTH); s.emit(0x50); entry(); s.push(1); s.emit(0x50); s.call(52, 3)
        s.label(shorter)
        s.result(0)
    rewriter.redirect(pc, ('list_set', context['rid']), build)


def list_push(rewriter, pc, argc, context):
    """62: (entity, key, value), up to 23 entries. A pushed entry was unset, so it held 0."""
    def build(s):
        entity, key, value = (lambda: s.arg(1)), (lambda: s.arg(2)), (lambda: s.arg(3))
        base, entry = (lambda: s.emit(0x41, 0)), (lambda: s.emit(0x41, 1))
        full = s.label()
        push_list_base(s, key)                                                                  # local 0: the list's first number
        entity(); base(); s.push(LIST_LENGTH); s.emit(0x50); s.call(53, 2); s.push_result()     # local 1: the length
        entry(); s.push(brew_art.ENTRIES); s.emit(0x0e); s.jump_if_zero(full)
        list_store(s, entity, key, base, entry, value, lambda: s.push(0), context)
        entity(); base(); s.push(LIST_LENGTH); s.emit(0x50); entry(); s.push(1); s.emit(0x50); s.call(52, 3)
        s.label(full)
        s.result(0)
    rewriter.redirect(pc, ('list_push', context['rid']), build)


def resolve_look(s, character, context):
    """Point a character about to be shown at its look's faces, if its list has changed since it was last shown. A list the story's
    table doesn't know leaves the look it had."""
    done = s.label()
    temp = context['hash_temp']
    s.push(temp); character(); s.push(LOOK_HASH); s.call(53, 2); s.push_result(); s.emit(0x3e); s.emit(0x15)
    character(); s.push(LOOK_SHOWN); s.call(53, 2); s.push_result(); s.emit(0x40, temp); s.emit(0x0a); s.jump_if_nonzero(done)
    character(); s.push(LOOK_SHOWN); s.emit(0x40, temp); s.call(52, 3)
    for hash_value, bank in context['looks']:
        other = s.label()
        s.emit(0x40, temp); s.push(hash_value); s.emit(0x0a); s.jump_if_zero(other)
        character(); s.push(bank); s.call(72, 2)
        s.jump(done)
        s.label(other)
    s.label(done)


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
    """SHS's dialogue for `text` under BREW's speaker (callables pushing them): no speaker or Event is the narrator, a character with no
    picture says it under its name with none (service 76), and anyone else with their face. A whole line in brackets loses them: it's
    plain narration from the narrator, and a thought from anyone else. What's shown is kept as the last line, for a choice's question."""
    narrated, voice, done, plain, found = s.label(), s.label(), s.label(), s.label(), s.label()
    shown, twin = context['last_line'], context['line_twin']
    set_word(s, shown, text)
    set_word(s, twin, lambda: s.push(-1))
    for address, bare in context['bracketed']:
        other = s.label()
        s.emit(0x40, shown); s.push(address); s.emit(0x0a); s.jump_if_zero(other)
        set_word(s, twin, lambda bare=bare: s.push(bare))
        set_word(s, shown, lambda bare=bare: s.push(bare))
        s.jump(found)
        s.label(other)
    s.label(found)
    speaker(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(narrated)
    speaker(); s.push(EVENT_CHARACTER_KEY); s.call(55, 1); s.push_result(); s.emit(0x0a); s.jump_if_nonzero(narrated)
    resolve_look(s, speaker, context)
    speaker(); s.call(73, 1); s.push_result(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(voice)
    s.emit(0x40, twin); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(plain)
    s.push(-2); s.emit(0x40, twin); speaker(); push_face(s, expression); s.call(13, 4)
    s.jump(done)
    s.label(plain)
    s.emit(0x40, shown); speaker(); push_face(s, expression); s.call(13, 3)
    s.jump(done)
    s.label(voice)
    speaker(); s.push(context['name_buffer']); s.call(61, 2)
    s.push(context['name_buffer']); s.emit(0x40, shown); s.call(76, 2)
    s.jump(done)
    s.label(narrated)
    s.emit(0x40, shown); s.push(NARRATOR); s.call(13, 2)
    s.label(done)


def line(rewriter, pc, argc, context):
    """72: (speaker, text, expression), dropped with no scene open (shs08.5.mod)."""
    def build(s):
        done = s.label()
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


def set_word(s, address, value):
    s.push(address); value(); s.emit(0x3e); s.emit(0x15)


def menu(rewriter, pc, argc, context):
    """28: (title, `a|b|c`) the menu 74 shows; returns 1."""
    def build(s):
        set_word(s, context['menu'], lambda: s.arg(1))
        set_word(s, context['menu'] + 1, lambda: s.arg(2))
        set_word(s, context['menu'] + 2, lambda: s.push(-1))
        set_word(s, context['menu'] + 4, lambda: s.push(-1))
        s.result(1)
    rewriter.redirect(pc, ('menu', context['rid']), build)


def spinning_menu(rewriter, pc, argc, context):
    """30: (title, `a|b|c`, ms) a menu whose cursor jumps to a random other option every interval, and 31 gives it a limit. Only
    single-round questions get here (word_game takes the rest), and they become the smartphone's "Think fast!", with BREW's title, the
    question, under it. Time running out takes wherever the cursor is, so here a random option. The spin itself isn't reproduced."""
    def build(s):
        set_word(s, context['menu'], lambda: s.text(TIMED_TITLE))
        set_word(s, context['menu'] + 1, lambda: s.arg(2))
        set_word(s, context['menu'] + 2, lambda: s.push(-1))
        set_word(s, context['menu'] + 4, lambda: s.arg(1))
        # Count the options, packed two bytes a word: local 0 the count, local 1 the word offset.
        s.push(1); s.push(0)
        top, end, low = s.label(), s.label(), s.label()
        s.label(top)
        s.arg(2); s.emit(0x41, 1); s.emit(0x50); s.emit(0x3f); s.push(256); s.emit(0x53)         # the high byte
        s.emit(0x13); s.jump_if_nonzero(end)
        s.arg(2); s.emit(0x41, 1); s.emit(0x50); s.emit(0x3f); s.push(256); s.emit(0x53); s.push(ord('|')); s.emit(0x0a); s.jump_if_zero(low)
        s.emit(0x23, 0); s.emit(0x41, 0); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.label(low)
        s.arg(2); s.emit(0x41, 1); s.emit(0x50); s.emit(0x3f); s.push(256); s.emit(0x54)         # the low byte
        s.emit(0x13); s.jump_if_nonzero(end)
        other = s.label()
        s.arg(2); s.emit(0x41, 1); s.emit(0x50); s.emit(0x3f); s.push(256); s.emit(0x54); s.push(ord('|')); s.emit(0x0a); s.jump_if_zero(other)
        s.emit(0x23, 0); s.emit(0x41, 0); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.label(other)
        s.emit(0x23, 1); s.emit(0x41, 1); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.jump(top)
        s.label(end)
        s.emit(0x41, 0); s.call(27, 1); s.push_result()
        set_word(s, context['menu'] + 3, lambda: s.emit(0x41, 2))
        s.result(1)
    rewriter.redirect(pc, ('spinning_menu', context['rid']), build)


def menu_timer(rewriter, pc, argc, context):
    """31: (ms) the pending menu's limit."""
    rewriter.redirect(pc, ('menu_timer', context['rid']), lambda s: (set_word(s, context['menu'] + 2, lambda: s.arg(1)), s.result(0)))


def wait(rewriter, pc, argc, context):
    """74: shows the pending menu or narration line. A menu's answer also goes in field 0. A story with no player character (a quiz, the
    real player answering) asks in the narrator's gold, with no portrait, as New Rules' Train That Brain! does."""
    def build(s):
        no_menu, done = s.label(), s.label()
        s.emit(0x40, context['menu'] + 1); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(no_menu)
        if context['player']:
            resolve_look(s, lambda: s.push(PLAYER), context)
            s.emit(0x40, context['menu'])
        else:
            timed, chosen = s.label(), s.label()
            s.emit(0x40, context['menu'] + 2); s.push(-1); s.emit(0x0a); s.jump_if_zero(timed)
            s.text(CHOICE_TITLE); s.jump(chosen)
            s.label(timed)
            s.emit(0x40, context['menu'])
            s.label(chosen)
        s.emit(0x40, context['menu'] + 1)
        question, asked = s.label(), s.label()
        s.emit(0x40, context['menu'] + 4); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(question)
        s.emit(0x40, context['menu'] + 4); s.jump(asked)
        s.label(question)
        s.emit(0x40, context['last_line'])
        s.label(asked)
        s.emit(0x40, context['menu'] + 2); s.emit(0x40, context['menu'] + 3)
        s.push(-2 if context['player'] else NARRATOR); s.push(-1); s.push(CHOICE_PORTRAIT)
        s.call(1, 8)
        s.push_result()
        set_word(s, context['menu'] + 1, lambda: s.push(-1))
        set_global(s, FIELD_KEY, lambda: s.emit(0x41, 0))
        s.push(FIELD_KEY); s.call(55, 1)
        s.jump(done)
        s.label(no_menu)
        none = s.label()
        s.emit(0x40, context['narration']); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(none)
        say(s, lambda: s.emit(0x40, context['narration']), lambda: (s.push(SPEAKER_KEY), s.call(55, 1), s.push_result()),
            lambda: (s.push(EXPRESSION_KEY), s.call(55, 1), s.push_result()), context)
        set_word(s, context['narration'], lambda: s.push(-1))
        s.label(none)
        s.result(0)
        s.label(done)
    rewriter.redirect(pc, ('wait', context['rid']), build)


def catch_game(rewriter, pc, argc, context):
    """19, 20, 21: the catch game, whose score BREW's scripts read from R, usually testing it against the target. Service 221 where
    the player has the switch on, with the page before it as a panel. Otherwise, a word game under that page, its items' words good or
    bad by their value: its result out of the smartphone's pass mark is that share of the target, which reaches every band the
    scripts test (all 181 sites' constants, 2026-11-05: at a target of 45, a score of 6 gives 45, then 37, 30, 22 and so on). It goes on
    in B for the push after the call, as what it has to do on the way out would replace R."""
    service = rewriter.code[pc][1] >> 8
    mode = CATCH_MODES[service]
    reads = rewriter.code[pc + 1] == (0x21, None)
    if reads:
        rewriter.code[pc + 1] = (0x08, None)
    page, good, bad = context['page'], context['catch_good'], context['catch_bad']
    list_arg = 5 if mode == ORBIT else 4
    sprite_arg = 6 if mode == ORBIT else 5

    def build(s):
        real, done = s.label(), s.label()
        s.push(BREW_MINIGAMES_QUERY); s.call(70, 1)
        s.push_result(); s.jump_if_nonzero(real)
        for buffer in (good, bad):
            set_word(s, buffer, lambda buffer=buffer: s.push(0))
        s.push(0)                                           # local 0: the kind of item
        s.push(0)                                           # local 1: the entry in the table of words
        items, items_end, kept = s.label(), s.label(), s.label()
        s.label(items)
        s.emit(0x41, 0); s.arg(list_arg); s.emit(0x3f); s.emit(0x0e); s.jump_if_zero(items_end)
        count_at = lambda field: (s.arg(list_arg), s.push(1 + field), s.emit(0x50), s.emit(0x41, 0), s.push(3), s.emit(0x52), s.emit(0x50), s.emit(0x3f))
        count_at(2); s.push(0); s.emit(0x0c); s.jump_if_zero(kept)
        s.emit(0x23, 1); s.push(0); s.emit(0x3e); s.emit(0x15)
        search, found, missing = s.label(), s.label(), s.label()
        s.label(search)
        s.emit(0x41, 1); s.push(context['catch_words_count']); s.emit(0x0e); s.jump_if_zero(missing)
        s.push(context['catch_words']); s.emit(0x41, 1); s.push(3); s.emit(0x52); s.emit(0x50); s.emit(0x3f)
        count_at(1); s.emit(0x0a); s.jump_if_nonzero(found)
        s.emit(0x23, 1); s.emit(0x41, 1); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.jump(search)
        s.label(missing)
        # A picture with no words adds nothing: the lists are filled up below.
        s.jump(kept)
        s.label(found)

        def add(buffer, word):
            first = s.label()
            s.emit(0x40, buffer); s.jump_if_zero(first)
            s.push(buffer); s.text('|'); s.call(25, 2)
            s.label(first)
            s.push(buffer); word(); s.emit(0x3f); s.call(25, 2)
        word_at = lambda k: (lambda: (s.push(context['catch_words'] + 1 + k), s.emit(0x41, 1), s.push(3), s.emit(0x52), s.emit(0x50)))
        worse, following = s.label(), s.label()
        count_at(0); s.push(0); s.emit(0x0c); s.jump_if_zero(worse)
        add(good, word_at(0)); add(good, word_at(1))
        s.jump(following)
        s.label(worse)
        add(bad, word_at(0)); add(bad, word_at(1))
        s.label(following)
        s.label(kept)
        s.emit(0x23, 0); s.emit(0x41, 0); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.jump(items)
        s.label(items_end)
        for buffer, fill in ((good, CATCH_GOOD_WORDS), (bad, CATCH_BAD_WORDS)):
            have = s.label()
            s.emit(0x40, buffer); s.jump_if_nonzero(have)
            s.push(buffer); s.text('|'.join(fill)); s.call(25, 2)
            s.label(have)
        resolve_look(s, lambda: s.push(PLAYER), context)
        def page_string(slot):
            """The page's string, or its word-game twin (catch_plain) where it has one."""
            end = s.label()
            for address, twin in context['catch_plain']:
                other = s.label()
                s.emit(0x40, slot); s.push(address); s.emit(0x0a); s.jump_if_zero(other)
                s.push(twin); s.jump(end)
                s.label(other)
            s.emit(0x40, slot)
            s.label(end)
        titled, title, described, described_end = s.label(), s.label(), s.label(), s.label()
        s.emit(0x40, page + 1); s.push(-1); s.emit(0x0a); s.jump_if_zero(titled)
        s.text(CATCH_TITLE); s.jump(title)
        s.label(titled)
        page_string(page)
        s.label(title)
        s.emit(0x40, page + 1); s.push(-1); s.emit(0x0a); s.jump_if_zero(described)
        s.text(CATCH_TEXT); s.jump(described_end)
        s.label(described)
        page_string(page + 1)
        s.label(described_end)
        s.push(good); s.push(bad); s.push(WORD_GAME_MS); s.push(PLAYER); s.push(1); s.push(WORD_GAME_REFRESH_MS)
        s.call(71, 8)
        s.push_result()                                     # local 2: the result
        set_word(s, page + 1, lambda: s.push(-1))
        short, scored = s.label(), s.label()
        s.emit(0x41, 2); s.push(WORD_GAME_PASS); s.emit(0x0d); s.jump_if_zero(short)
        s.arg(1); s.jump(scored)
        s.label(short)
        s.emit(0x41, 2); s.arg(1); s.emit(0x52); s.push(WORD_GAME_PASS); s.emit(0x53)
        s.label(scored)
        s.emit(0x04)
        s.jump(done)
        s.label(real)
        no_page = s.label()
        s.emit(0x40, page + 1); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(no_page)
        s.emit(0x40, page); s.emit(0x40, page + 1); s.push(0); s.call(33, 3)
        set_word(s, page + 1, lambda: s.push(-1))
        s.label(no_page)
        s.push(mode); s.arg(1); s.arg(2); s.arg(3)
        if mode == ORBIT:
            s.arg(4); s.push(0); s.push(0)
        elif mode == ANGLED:
            s.push(0); s.arg(6); s.arg(7)
        else:
            s.push(0); s.arg(6); s.push(0)
        s.arg(sprite_arg); s.arg(list_arg); s.push(context['catch_sizes']); s.push(context['catch_sizes_count'])
        s.call(BREW_CATCH, 11)
        s.push_result(); s.emit(0x04)
        s.label(done)
        s.result(0)
    rewriter.redirect(pc, ('catch', context['rid'], service, reads), build)


def game_page(rewriter, pc, argc, context):
    """12: (title, text) the page before a word game: its title and description, on the game's own screen."""
    def build(s):
        set_word(s, context['page'], lambda: s.arg(1))
        set_word(s, context['page'] + 1, lambda: s.arg(2))
        s.result(0)
    rewriter.redirect(pc, ('game_page', context['rid']), build)


def word_game(rewriter, start, context):
    """The routine with the spinning menu: (options buffer, word list, scores, word count, shown, spare, rounds, title format, spin ms,
    limit ms, whether the title counts rounds). It returns the total in B, the sum of a score per round. With two rounds or more it plays
    as service 71: scores above 0 are good words, the rest bad, and the result out of the smartphone's pass mark becomes that share of
    the best total. One round goes on into the routine, with its page shown first: the shim's frame is the routine's, once its PUSH_FP
    is done."""
    def build(s):
        words, scores, count, rounds = (lambda: s.arg(2)), (lambda: s.arg(3)), (lambda: s.arg(4)), (lambda: s.arg(7))
        page, good, bad, word = context['page'], context['good'], context['bad'], context['word']
        game = s.label()
        rounds(); s.push(2); s.emit(0x0e); s.jump_if_zero(game)
        no_page = s.label()
        s.emit(0x40, page + 1); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(no_page)
        s.emit(0x40, page); s.emit(0x40, page + 1); s.push(0); s.call(33, 3)
        set_word(s, page + 1, lambda: s.push(-1))
        s.label(no_page)
        s.jump(start + 1)
        s.label(game)
        for buffer in (good, bad):
            set_word(s, buffer, lambda: s.push(0))
        s.push(0)                                           # local 0: the word
        s.push(1)                                           # local 1: the best score
        top, end = s.label(), s.label()
        s.label(top)
        s.emit(0x41, 0); count(); s.emit(0x0e); s.jump_if_zero(end)
        set_word(s, word, lambda: (words(), s.emit(0x41, 0), s.emit(0x50), s.emit(0x3f)))
        chosen = s.label()
        for address, bare in context['game_words']:
            other = s.label()
            s.emit(0x40, word); s.push(address); s.emit(0x0a); s.jump_if_zero(other)
            set_word(s, word, lambda bare=bare: s.push(bare))
            s.jump(chosen)
            s.label(other)
        s.label(chosen)

        def append(buffer):
            first = s.label()
            s.emit(0x40, buffer); s.jump_if_zero(first)
            s.push(buffer); s.text('|'); s.call(25, 2)
            s.label(first)
            s.push(buffer); s.emit(0x40, word); s.call(25, 2)
        worse, kept, following = s.label(), s.label(), s.label()
        scores(); s.emit(0x41, 0); s.emit(0x50); s.emit(0x3f); s.push(0); s.emit(0x0c); s.jump_if_zero(worse)
        scores(); s.emit(0x41, 0); s.emit(0x50); s.emit(0x3f); s.emit(0x41, 1); s.emit(0x0c); s.jump_if_zero(kept)
        s.emit(0x23, 1); scores(); s.emit(0x41, 0); s.emit(0x50); s.emit(0x3f); s.emit(0x3e); s.emit(0x15)
        s.label(kept)
        append(good)
        s.jump(following)
        s.label(worse)
        append(bad)
        s.label(following)
        s.emit(0x23, 0); s.emit(0x41, 0); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.jump(top)
        s.label(end)
        resolve_look(s, lambda: s.push(PLAYER), context)
        titled, title, described, described_end = s.label(), s.label(), s.label(), s.label()
        s.emit(0x40, page + 1); s.push(-1); s.emit(0x0a); s.jump_if_zero(titled)
        s.text(TIMED_TITLE); s.jump(title)
        s.label(titled)
        s.emit(0x40, page)
        s.label(title)
        s.emit(0x40, page + 1); s.push(-1); s.emit(0x0a); s.jump_if_zero(described)
        s.emit(0x40, context['last_line']); s.jump(described_end)
        s.label(described)
        s.emit(0x40, page + 1)
        s.label(described_end)
        s.push(good); s.push(bad); s.push(WORD_GAME_MS); s.push(PLAYER); s.push(1); s.push(WORD_GAME_REFRESH_MS)
        s.call(71, 8)
        s.push_result()                                     # local 2: the result
        set_word(s, page + 1, lambda: s.push(-1))
        short, returned = s.label(), s.label()
        s.emit(0x41, 2); rounds(); s.emit(0x52); s.emit(0x41, 1); s.emit(0x52); s.push(WORD_GAME_PASS); s.emit(0x53)
        rounds(); s.emit(0x41, 1); s.emit(0x52); s.emit(0x0c); s.jump_if_zero(short)
        rounds(); s.emit(0x41, 1); s.emit(0x52); s.jump(returned)
        s.label(short)
        s.emit(0x41, 2); rounds(); s.emit(0x52); s.emit(0x41, 1); s.emit(0x52); s.push(WORD_GAME_PASS); s.emit(0x53)
        s.label(returned)
        s.emit(0x04)
    rewriter.replace_function(start, ('word_game', context['rid']), build, 11)


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
    """9: (track) plays once: SHS 79 for SOUND_TRACKS, which leaves any music playing, or 80 for the rest."""
    def build(s):
        def resource():
            s.arg(1); s.push(8000); s.emit(0x51); s.push(MUSIC_BASE); s.emit(0x50)
        sound, done = s.label(), s.label()
        for track in sorted(SOUND_TRACKS):
            s.arg(1); s.push(8000 + track); s.emit(0x0a); s.jump_if_nonzero(sound)
        resource(); s.push(0); s.call(80, 2)
        s.jump(done)
        s.label(sound)
        resource(); s.call(79, 1)
        s.label(done)
        s.result(0)
    rewriter.redirect(pc, 'music', build)


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
            28: menu, 30: spinning_menu, 31: menu_timer, 33: schedule, 35: field_set, 49: player_name, 53: stored_text_get, 55: cast_name, 58: owned_set, 59: owned_get,
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


def data_strings(program):
    """(address, bytes) of each NUL-terminated string in a program's main data, packed two bytes a word, and the words it takes."""
    words, start = program.main_words, 0
    while start < len(words):
        end, text, finished = start, bytearray(), False
        while end < len(words) and not finished:
            for byte in (words[end] >> 8, words[end] & 255):
                if byte == 0:
                    finished = True
                    break
                text.append(byte)
            end += 1
        yield start, bytes(text), end - start
        start = end


def rewrite_strings(program, change):
    """A program with its strings changed in place: `change(bytes)` gives a string no longer than it was, or None."""
    from dataclasses import replace
    out = list(program.main_words)
    for start, text, length in data_strings(program):
        changed = change(text)
        if changed is not None:
            kept = changed + b'\0' * (2 * length - len(changed))
            for offset in range(length):
                out[start + offset] = kept[2 * offset] << 8 | kept[2 * offset + 1]
    return replace(program, main_words=tuple(out))


def strip_name_marks(program):
    """Take `~` off the ends of short strings: only names end in one, to tell same-named characters apart (`Girl~`, `Girl~~`, `$USR~`), and
    neither the name plate nor a `$` token shows it (the real game neither)."""
    return rewrite_strings(program, lambda text: text.rstrip(b'~') if text.endswith(b'~') and len(text) < 40 else None)


def strip_round_counts(program):
    """Take the round count off a word game's title format, `Bust a move. %d/%d`: only single-round questions still show one."""
    return rewrite_strings(program, lambda text: text[:-len(b' %d/%d')] if text.endswith(b' %d/%d') else None)


def is_printable(text):
    return all(32 <= byte < 250 or byte in (10, 13) for byte in text)


def bracketed(text):
    """The inside of a string wholly in brackets (`(You notice a girl.)`, not `(Oh.) Hi. (Bye.)`), or None."""
    if len(text) < 3 or text[:1] != b'(' or text[-1:] != b')' or not is_printable(text):
        return None
    depth = 0
    for index, byte in enumerate(text):
        depth += (byte == 40) - (byte == 41)
        if depth == 0 and index < len(text) - 1:
            return None
    return text[1:-1]


def bare_word(text):
    """A game word without its bracket or quotes, `(Grab!)` or `"Miss..."`, or None."""
    stripped = text.strip()
    if len(stripped) < 3 or not is_printable(stripped):
        return None
    if stripped[:1] == b'"' and stripped[-1:] == b'"':
        return stripped[1:-1]
    return bracketed(stripped) if stripped[:1] == b'(' else (stripped if stripped != text else None)


def spin_routine(program):
    """Where the routine with the spinning menu starts, or None. It's the same code everywhere it appears (55 scripts, 2026-11-05)."""
    instructions = program.instructions
    sites = [i.pc for i in instructions if i.opcode == 0x1f and i.operand >> 8 == 30]
    if not sites:
        return None
    if len(sites) > 1:
        raise StoryError('a script has more than one spinning menu routine')
    start = max((i.pc for i in instructions if i.opcode == 0x48 and i.pc <= sites[0]), default=None)
    if start is None:
        return None
    follows = [i.operand >> 8 for i in instructions[sites[0]:sites[0] + 8] if i.opcode == 0x1f]
    if follows[:4] != [30, 31, 32, 74]:
        raise StoryError(f'the spinning menu at {sites[0]} is not the usual routine')
    return start


def game_pages(program, start):
    """The calls of 12 that introduce a word game: a page, then, with only constants between, a call of the routine or of a function
    that calls it."""
    instructions = program.instructions
    callers = {start}
    for i in range(len(instructions) - 1):
        if instructions[i].opcode == 0x42 and instructions[i + 1].opcode == 0x29 and instructions[i + 1].operand == start:
            callers.add(max((j.pc for j in instructions if j.opcode == 0x48 and j.pc <= i), default=start))
    pages = set()
    for i, instruction in enumerate(instructions):
        if instruction.opcode == 0x1f and instruction.operand >> 8 == 12:
            for j in range(i + 1, min(i + 12, len(instructions) - 1)):
                if instructions[j].opcode == 0x1f:
                    break
                if instructions[j].opcode == 0x42 and instructions[j + 1].opcode == 0x29 and instructions[j + 1].operand in callers:
                    pages.add(i)
                    break
    return pages


def fix_surviving_college(rewriter):
    """6.1 Surviving College picks its ending from 6 points up, then below 5, so exactly 5 has none and the story stops there,
    in BREW too (Tardy-Slip shows it). The owner's fix (2026-11-05): 5 takes the lower ending, as `< 6`."""
    code = rewriter.code
    found = [k for k in range(len(code) - 5) if code[k] == (0x1A, 5) and code[k + 1] == (0x0E, None)
             and code[k + 3] == (0x1A, 1001) and code[k + 4] == (0x1A, 119)]
    if len(found) != 1:
        raise StoryError(f'6.1: the ending test is not where it was ({len(found)} found)')
    code[found[0]] = (0x1A, 6)


STORY_FIXES = {'shs085_06_01_shs08.exp': fix_surviving_college}


def catch_pages(program):
    """The calls of 12 that introduce a catch game: the last host call before one, and one that jumps past that to the game."""
    instructions = program.instructions
    hosts = [k for k, i in enumerate(instructions) if i.opcode == 0x1f]
    pages = set()
    for n, k in enumerate(hosts):
        if instructions[k].operand >> 8 not in CATCH_MODES or not n or instructions[hosts[n - 1]].operand >> 8 != 12:
            continue
        pages.add(instructions[hosts[n - 1]].pc)
        if n > 1 and instructions[hosts[n - 2]].operand >> 8 == 12 and any(i.opcode == 0x28 for i in instructions[hosts[n - 2]:hosts[n - 1]]):
            pages.add(instructions[hosts[n - 2]].pc)
    return pages


def script_context(rewriter, script, looks, player, program, catch_sizes=None):
    """What a script's shims share: scratch words in its data, and its bracketed strings' bare twins."""
    start = spin_routine(program)
    thoughts, game_words = [], []
    for address, text, _ in data_strings(program):
        bare = bracketed(text)
        if bare is not None:
            thoughts.append((address, rewriter.text(bare.decode('latin-1'))))
        word = bare_word(text) if start is not None else None
        if word is not None:
            game_words.append((address, rewriter.text(word.decode('latin-1'))))
    catch = {}
    if any(i.opcode == 0x1f and i.operand >> 8 in CATCH_MODES for i in program.instructions):
        words = sorted(CATCH_WORDS.items())
        sizes = sorted((catch_sizes or {}).items())
        # Each page string's twin for the word game: the generic title as the banner, a text without the catch game's points.
        plain = []
        for address, text, _ in data_strings(program):
            if text == CATCH_GENERIC_TITLE:
                plain.append((address, rewriter.text(CATCH_TITLE)))
            elif CATCH_POINTS.search(text):
                plain.append((address, rewriter.text(CATCH_POINTS.sub(b'', text).decode('latin-1'))))
        catch = dict(catch_good=rewriter.words([0] * CATCH_LIST_WORDS), catch_bad=rewriter.words([0] * CATCH_LIST_WORDS),
                     catch_plain=plain,
                     catch_words=rewriter.words([value for picture, pair in words for value in (picture, rewriter.text(pair[0]), rewriter.text(pair[1]))]),
                     catch_words_count=len(words), catch_sizes_count=len(sizes),
                     catch_sizes=rewriter.words([value for picture, size in sizes for value in (picture, *size)] or [0]))
    return dict(rid=script, kind='single', looks=sorted(looks.items()), hash_factors=rewriter.words(HASH_FACTORS),
                last_line=rewriter.words([-1]), narration=rewriter.words([-1]), menu=rewriter.words([-1, -1, -1, 0, -1]),
                name_buffer=rewriter.words([0] * NAME_WORDS), hash_temp=rewriter.words([0]), line_twin=rewriter.words([-1]), player=player,
                bracketed=thoughts, game_words=game_words, routine=start, game_pages=game_pages(program, start) if start is not None else (),
                page=rewriter.words([-1, -1]), word=rewriter.words([0]), catch_pages=catch_pages(program), **catch,
                good=rewriter.words([0] * LIST_WORDS), bad=rewriter.words([0] * LIST_WORDS))


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
        if table.setdefault(look_hash(entries), bank) != bank:
            raise StoryError(f'{name}: two looks have the same hash')
    title = clean_title(title_of(archive_resources[1]))
    scripts = sorted(rid for rid, data in archive_resources.items() if data[:4] == b'kiwi')
    extra = [rid for rid in scripts if rid not in (FIRST_SCRIPT, BREW_STORY_SCRIPT)]
    if extra:
        raise StoryError(f'{name}: scripts {extra} need the calendar driver or a script map')
    resources = {}
    for script in scripts:
        program = strip_round_counts(strip_name_marks(decode_program(upgrade(archive_resources[script]))))
        rewriter = Rewriter(program, zero_gap=True)
        if name in STORY_FIXES and script == BREW_STORY_SCRIPT:
            STORY_FIXES[name](rewriter)
        sizes = {int(picture): tuple(entry[1:]) for picture, entry in spec.get('catch', {}).get('pictures', {}).items()}
        context = script_context(rewriter, script, table, not title.startswith('Quiz '), program, sizes)
        for pc, service, argc in rewriter.calls():
            if service == 12 and (pc in context['game_pages'] or pc in context['catch_pages']):
                game_page(rewriter, pc, argc, context)
            elif service in CATCH_MODES:
                catch_game(rewriter, pc, argc, context)
            elif service in RENAME:
                rewriter.rename(pc, RENAME[service])
            elif service in DROPPED:
                dropped(rewriter, pc, argc, context)
            elif service in HANDLERS:
                HANDLERS[service](rewriter, pc, argc, context)
            else:
                raise StoryError(f'{name}, script {script}: service {service} with {argc} arguments has no translation yet')
        if context['routine'] is not None:
            word_game(rewriter, context['routine'], context)
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
    catch_resources, spec['catch'] = catch_pictures(art08, bases['08'])
    resources.update(catch_resources)
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
BADGE_SCALE = 6                         # art pixels to the picture's, with no smoothing: the player scales it to SHS's size (TRANSLATED_BADGE_UNITS)


def badge_pictures(art):
    """{resource: PNG} of BREW's relationship icons, whole and broken: BREW's own icons never break, so a broken one is the whole one
    parted down its middle, for the smartphone's loss animation. They're large and unsmoothed, so that they stay crisp however they're
    scaled for the screen."""
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
        for base, image in ((BADGE_BASE + number, whole), (BADGE_BASE + 3 + number, broken)):
            found[base] = brew_art.png(image.resize((image.width * BADGE_SCALE, image.height * BADGE_SCALE), Image.NEAREST))
    return found


def catch_pictures(art, pack):
    """({resource: PNG}, spec) of the catch game: BREW's frame (FUN_00005b94, as Tardy-Slip's CatchScreen draws it), its ring, digits and
    captions, and every item and player picture, at 3 times with no smoothing."""
    def up(image):
        return brew_art.png(image.resize((image.width * CATCH_SCALE, image.height * CATCH_SCALE), Image.NEAREST))

    frame = Image.new('RGBA', (240, 320), (0, 0, 0, 0))
    paint = ImageDraw.Draw(frame)
    paint.rectangle((1, 29, 238, 318), fill=CATCH_PANEL_COLOUR)
    paint.line((5, 33, 234, 33), fill=CATCH_EDGE_DARK)
    paint.line((5, 33, 5, 314), fill=CATCH_EDGE_DARK)
    paint.line((5, 314, 234, 314), fill=CATCH_EDGE_LIGHT)
    paint.line((234, 33, 234, 314), fill=CATCH_EDGE_LIGHT)
    paint.rectangle((6, 34, 233, 313), fill=CATCH_FIELD_COLOUR)
    for image, x, y in ((34, 1, 29), (35, 227, 29), (32, 1, 307), (33, 227, 307)):
        art.draw(frame, image, x, y)
    bar_x, cap = 36, 8
    for x in range(bar_x + 20, bar_x + 168 - cap, 8):
        art.draw(frame, 40, x, 6)
    art.draw(frame, 41, bar_x + 168 - cap, 6)
    ring = Image.new('RGBA', (28, 34), (0, 0, 0, 0))
    art.draw(ring, 39, 0, 0)
    resources = {CATCH_BASE: up(frame), CATCH_BASE + 1: up(ring)}
    for digit in range(10):
        resources[CATCH_BASE + 2 + digit] = up(brew_art.font_text(pack, str(digit)))
    captions = brew_strings(pack)[58:60]
    for k, caption in enumerate(captions):
        resources[CATCH_BASE + 12 + k] = up(brew_art.font_text(pack, caption))
    pictures = {}
    for n, picture in enumerate(sorted(CATCH_WORDS)):
        left, top, right, bottom = art.bounds(picture)
        canvas = Image.new('RGBA', (right - left, bottom - top), (0, 0, 0, 0))
        art.draw(canvas, picture, -left, -top)
        resources[CATCH_BASE + 14 + n] = up(canvas)
        pictures[str(picture)] = [CATCH_BASE + 14 + n, right - left, bottom - top]
    return resources, dict(frame=CATCH_BASE, ring=CATCH_BASE + 1, digits=list(range(CATCH_BASE + 2, CATCH_BASE + 12)),
                           captions=[CATCH_BASE + 12, CATCH_BASE + 13], pictures=pictures)


def brew_strings(pack):
    """The UI string table (resource 9): a header up to the first, then each with a length before it and a zero after."""
    raw = pack[9]
    at, found = raw.index(b'\x09Main Menu'), []
    while at < len(raw):
        length = raw[at]
        found.append(raw[at + 1:at + 1 + length].decode('latin-1'))
        at += length + 2
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
