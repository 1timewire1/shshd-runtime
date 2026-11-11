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
from exp_runtime.episode_version import RESOURCE as VERSION_RECORD, version_bytes
from exp_runtime.decode.bytecode import decode_program
from exp_runtime.exp import ExpArchive, Metadata, encode_exp
from exp_runtime.vm import KiwiVM, StopKind, signed16

sys.path.insert(0, str(Path(__file__).resolve().parent))

import brew_art  # noqa: E402
from exp_runtime.brew_services import ANGLED, BREW_CATCH, BREW_MINIGAMES_QUERY, ORBIT, SIDEWAYS  # noqa: E402
from kiwi_rewrite import Rewriter  # noqa: E402
import newrules  # noqa: E402
import nr_art  # noqa: E402

ADDON_ID, ADDON_TITLE, ADDON_REVISION = 'shsbrew', 'Surviving High School (BREW)', 10   # 10: badge icons the smartphone's size (EVENT_ICON_SIZE); 9: the Kid lowered (LOWERED_BODIES); 8: the TV faces in (MIRRORED_BODIES); 2: the event icons; 3: the Java '08 look;
# 4: Classic stories' own backgrounds; 5: '08's redraws of them; 6: the stories' own catch picture (OWN_CATCH_PICTURES); 7: that
# picture as an event icon too (OWN_ICON_BASE), and King of the Road's Michael centred (CENTRE_OWN_BODY)
ADDON_REQUIRED = 7                      # what a story needs: rev 8 only redraws the TV, so the stories built for 7 stay as they are
PACK_CAMPAIGN, PACK_CLASSIC, PACK_SEASON = 31000, 31100, 31200
# The stories' version (episode_version.py): a newer one replaces an older copy on import, and a rebuild at the same
# version replaces it too. Raise it when a build must never be replaced by an earlier one.
STORY_VERSION = 1
ADDON_EPISODE = 9999
TITLE_SUFFIX_07, TITLE_SUFFIX_08 = ' (SHS07)', ' (SHS08)'
FIRST_SCRIPT, STORY_SCRIPT, BREW_STORY_SCRIPT = 25001, 25002, 26000

# The addon's resources. A resource keeps its ID once shipped: new ones go at the end of their range.
BACKGROUND_BASE = 26000                 # + SKY_MODES x location index + sky mode
SKY_MODES = 3
LOCATIONS_08 = 28                       # 1000-1027; then 2000-2011
LOCATIONS_08_EXTRA = 12
LOCATION_07_OFFSET = 40                 # '07's own 1000-1027, after '08's
OWN_BACKGROUND_BASE = 29000             # + SKY_MODES x n + sky: Classic stories' own backgrounds (spec `backgrounds`: story -> location -> n)
OWN_BACKGROUND_INDEX = (OWN_BACKGROUND_BASE - BACKGROUND_BASE) // SKY_MODES
# The "'08 Backgrounds" switch for a Classic story's own pictures: '08 redrew 11 of the 12 as its extra locations (2000-2011; owner,
# 2026-11-06, from reference/screenshots/verify/brew_07_08/classic_own_vs_08_extra.png). Each copy sits this far above the own
# picture it stands in for (profile BREW_08_BACKGROUNDS); by the own picture's fingerprint (own_fingerprint), its '08 location.
OWN_08_OFFSET = 500
OWN_08_REDRAWS = {
    '2a495df62e233b9d': 2000,       # theme park
    'f55072a28d04c393': 2011,       # plaza / skate park
    '6cec3487fde86bd1': 2010,       # shop street / city street
    'c1001953cd681668': 2006,       # suburb street
    '2d1f15ab43889eef': 2009,       # science lab
    '5c427400a83bbf1c': 2002,       # cafeteria
    '6a497f669500850a': 2005,       # park with a gazebo
    '4a0d43d56c9e2887': 2007,       # nurse's office
    '63b0dedd969cd5fd': 2004,       # lake and mountains
    'f1535d5d1c3efc04': 2003,       # restaurant
    'a7d7ccea6341b383': 2008,       # parking lot (the night skyline has no '08 copy)
}
SKY_ONLY = 68                           # a scene with no location: its sky alone
CATCH_BASE = 26300                      # the catch game's frame, ring, digits and captions, then its pictures
EVENT_ICON_BASE = 26400                 # + a BREW picture's own ID (100-180): its small pictures, which the planner's events use as icons
EVENT_ICONS = range(100, 181)
# The "Java '08 Look" (Stage 2d): the Java demo's own picture for one of the addon's, this far above it (profile JAVA_LOOK_ART).
# Built only when the demo's jar is given (build_addon java_jar); a picture with no Java copy stays BREW's.
JAVA_OFFSET = 10000
# The smartphone's own badge icons are 2x art, 86 to 110 pixels a side (the location badge 3104: 90 x 94), and the badge draws an
# icon's pixels as frame points: so BREW's are fitted to this (rev 10; 46 before, half the smartphone's; owner, 2026-11-09).
EVENT_ICON_SIZE = 92
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
# The calendar (Classic, Stage 3a): the events a story schedules, kept in saved numbers as Battle of the Schools keeps its own,
# and run in BREW's order (Tardy-Slip's brew-calendar.js `step`/`finish`, for one day): the clock is CLOCK_KEY.
EVENTS_KEY, ACTIVE_KEY, TIMED_KEY, DAY_END_KEY, STARTED_KEY = 31070, 31071, 31072, 31073, 31074
# The calendar's days (69): its first month and date, day 0's weekday, the day's first minute, its last day, today, and the day
# a card last showed. A day is counted from the first, as brew-calendar.js `dayIndex`.
START_MONTH_KEY, START_DATE_KEY, WEEKDAY_KEY, DAY_START_KEY, LAST_DAY_KEY, DAY_KEY, SHOWN_DAY_KEY = (
    31075, 31076, 31077, 31078, 31079, 31080, 31081)
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
EVENT_BASE, EVENT_STRIDE, MOST_EVENTS = 31100, 24, 32     # event n's numbers at EVENT_BASE + (n - 1) x EVENT_STRIDE
EVENT_MINUTE, EVENT_DURATION, EVENT_ICON, EVENT_FLAG, EVENT_STATE, EVENT_DAY, EVENT_FIELDS = 0, 1, 2, 3, 4, 5, 8
# The SHS script an event runs (the story's, or another its setup schedules: CS Idol's school days), and on a recurring event's
# first copy, how many copies it has (34: one per day; 35 sets a field on them all). Stage 5.
EVENT_SCRIPT, EVENT_COPIES = 6, 7
NO_BADGE = -32768                       # an event's icon when it has no name, and so no badge
WEEKLY_FIRST_KEY = 31082                # 34's answer, the first copy's number (read into R with 55)
# A badge is up (it goes after the next message), the running event's badge icon, and where a date caption was just formatted
# (date_caption): saved numbers, so that every script of a story sees them (CS Idol's school days run a script of their own).
BADGE_UP_KEY, BADGE_ICON_KEY, DATE_CAPTION_KEY = 31083, 31084, 31085
OPENER_WORDS = 30                       # the longest event opener (in words of two letters) that dots() looks at: 60 characters
# The running event's planner slot (its minute, to the half hour, as the planner's rows), for its badge's time; and an event just
# started, whose first line is its opener (dots), badge or not (owner, 2026-11-07).
BADGE_TIME_KEY, OPENER_KEY = 31086, 31087
BADGE_TIME_FORMAT = '%d:%d%d %s - '     # `3:00 PM - `, then the event's name
WAITING, PENDING, DONE = 0, 1, 2                 # an event's state: not reached, due with no time of its own, run
# The season driver (Fall '06, Stage 6): a whole term's calendar, about 240 events with a weekly event on every school day, so
# each event is kept once (SEASON_EVENTS + (n - 1) x EVENT_STRIDE, the Classic driver's offsets) and each day has a list of the
# events on it (DAY_LISTS + day x DAY_SLOTS: the count, then the events in the order they were put there), as brew-calendar.js
# keeps `events` and `entries`. Below 20000, clear of the stories' own numbers (all under 1100) and the lists (LIST_KEYS).
SEASON_EVENTS, SEASON_MOST_EVENTS = 4000, 400
DAY_LISTS, DAY_SLOTS, SEASON_MOST_DAYS = 14000, 32, 120
PENDING_LIST, PENDING_SLOTS = 18000, 64     # the due events, in order (count, then events), as brew-calendar.js `pending`
CHECKED_KEY, CURRENT_KEY, LAST_ENTRY_DAY_KEY = 31088, 31089, 31090     # brew-calendar.js `checked` and `current`; the last day with an entry
DRIVER_SCRIPT = 25099                   # a season story's driver, a script of its own (every event has its own script)
FLAG_KEYS = 10000                       # 56 / 57's flags (character, key, index): the character's number FLAG_KEYS + key x 64 + index
SEASON_TITLE, SEASON_EPISODE = "Fall '06 Football Season", 1
RESULT_KEY = 31091                      # a season service's answer, read into R with 55
# Events BREW runs inside another (Stage 6b): 37 puts the due ones with no time of their own on the nested list, and at the
# script's next wait (72, 12, 74, 29: BREW_WAITING_SYSCALLS), or when it ends, the nest runner (NEST_SCRIPT) runs each through the
# runtime's service 223, which comes back to the waiting script, its registers and event text kept (NEST_SAVES + depth x 20).
NESTED_LIST, NEST_SCRIPT, NEST_DEPTH_KEY, NEST_SAVES, NESTED_SCRIPT_SERVICE = 18070, 25098, 31092, 19000, 223
NEST_WAITS = (72, 12, 74, 29)
# Fall '06's dates (owner, 2026-11-07): a card each week, `Week 1 of 13` over the school days it holds (`September 13-17`, Monday to
# Friday, as BREW's calendar keeps Monday, Wednesday and Friday), as Football Star's week cards (`Week 1 of 8` over a line); and a
# narration line at the start of each day, `Monday, September 13.` The week last shown is a saved number.
SHOWN_WEEK_KEY = 31093
WEEK_TITLE, DAY_LINE = 'Week %d of %d', '%s.'
WEEK_RANGE, WEEK_RANGE_MONTHS, WEEK_ONE_DAY = '%s %d-%d', '%s %d - %s %d', '%s %d'
EVENT_TEXT_KEY, EVENT_NAME_KEY = '$BREWEV%d', '$BREWNAME%d'     # each event's text (7) and name (its badge)
SLOT_MINUTES, DAY_MINUTES = 30, 1440
# An event with no icon of BREW's own shows its cell phone (143, the add-on's 26543) for now; it took the smartphone's location badge
# (3104) before (owner, 2026-11-09: to be assigned in the badge review).
NO_ICON_BADGE = 143
SCENE_LOCATION_KEY, SCENE_SKY_KEY = 31030, 31050    # + depth
# A season's scene stack has room of its own (Stage 6): Fall '06 opens more scenes than it closes (BREW only counts them), about
# one level every two school days, and past 20 the Classic places (31030, 31050 + depth) run into the calendar's own numbers.
SEASON_SCENE_LOCATION_KEY, SEASON_SCENE_SKY_KEY = 18100, 18600    # + depth, to 499
_SCENE_LAYOUT = {'location': SCENE_LOCATION_KEY, 'sky': SCENE_SKY_KEY}
EVENT_TEXT = '$BREWEVENT'
# A story's first line, `Surviving High School` and its title (`%s\n\n%s`, said by Event): the title card already shows the title.
TITLE_FORMAT = b'%s\n\n%s'
# The smartphone's own lines run to about 190 characters (99.9% of 209,628 spoken and 54,926 narrated lines, 2026-11-05); BREW's
# longer ones go out as several, at sentence ends, as the novels' do (novel_patch.LONGEST_LINE).
LONGEST_LINE = 190
SENTENCE_END = re.compile(r'(?<!Mr\.)(?<!Ms\.)(?<!Mrs\.)(?<!Dr\.)(?<=[.!?])\s+')
# Chapter 1's captions (1.1 to 1.3: `Monday, after school: At the Gym.`), which BREW has Event say after a scene change, are
# the smartphone's time badges (90), shown with the next line only, as Football Star's are.
# BREW's own icons (owner, 2026-11-05), by what the caption says: car, house, music, plate, TV, heart, basketball, books.
CAPTION_ICONS = ((('driving', 'riding'), 113), (('home', 'your room'), 166), (('party',), 138), (('coffee', 'ice cream'), 117),
                 (('movie',), 164), (('hills', "brian's place"), 133),
                 (('gym', 'game', 'court', 'tryouts', 'halftime', 'locker', 'practice', 'rebounding', 'dribbling', 'championship'), 104))
CAPTION_ICON = 108
WEEKDAYS = ('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')
# A school day's caption, `School\nMarch %d` (CS Idol, Artistic Differences, The School Paper: formatted with today's date, 43, then
# said): the badge `March 1 - School`, as Battle of the Schools: Guys words its badges (owner, 2026-11-07).
DATE_CAPTION = re.compile(rb'^([^\n]+)\n(' + b'|'.join(m.encode() for m in MONTHS) + rb') %d$')
EVENT_NAME = 'Event'
PLAYER = 0                              # BREW's character 0, You, is the player: SHS's primary speaker (74)
NAME_WORDS = 24                         # room for a character's name, for a voice with no picture
NIGHT_FROM = 1080                       # sky mode -1 is night from this minute (screens.js drawSky)
NARRATOR = 199                          # no speaker; SHS needs a character (as newrules.NARRATOR)
RELATIONSHIP, THEME = 407, 651          # SHS keys
RELATIONSHIP_BREW = 30407               # BREW's own 0-100 value
LIST_KEYS, LIST_SLOTS, LIST_LENGTH = 20000, 32, 31      # an entity's list `key`: LIST_KEYS + (key - 600) x LIST_SLOTS + entry
LOOK_LIST, LOOK_HASH, LOOK_SHOWN, PINK_ENTRY = 635, 19999, 19998, 2
# A look whose entry 0 (its body) is one of these isn't a person: no picture at all (Book, Note, Radio), or a thing's (the computer
# 143, the phone 144, the TV 164; brew_casts.json). Its box is the smartphone's grey one (theme 3), as the smartphone's things speak
# (owner, 2026-11-07). So are the animals' (Barry/Badger 276, the dogs 277 and 280, Lyle/Lizard 279), as the smartphone's speak
# (owner, 2026-11-09); the Kid (278) is a person.
GREY_BODIES = (-1, 143, 144, 164, 276, 277, 279, 280)
BLUE_THEME, PINK_THEME, GREY_THEME = 1, 2, 3
# A thing drawn turned to one side, mirrored in the add-on's portraits so it faces the middle from the right, where a thing always
# speaks: the smartphone mirrors a right-hand portrait except in the grey box (owner, 2026-11-08: the TV, 164; the desk phone and
# the handheld computer already face the right way). Only its portraits: the event icons and catch pictures stay as drawn.
MIRRORED_BODIES = (164,)
# A person drawn standing higher in its frame than the rest, lowered this many art pixels in the add-on's portraits so it sits on the
# ring as they do (their busts end 7 art pixels above the picture's foot): the Kid, 278 (18 above; owner, 2026-11-09).
LOWERED_BODIES = {278: 11}
CHOICE_PORTRAIT = 1
CHOICE_TITLE = 'Make your choice!'      # for a quiz: the real player answers, as in New Rules' Train That Brain!
# BREW's menus are mostly titled `You` (the scripts' own string: 967 menus in 120 stories), which the smartphone's are not: a menu with
# that title says CHOICE_TITLE instead (owner, 2026-11-11), and so do the M.A.S.H. packs' food menus, whose description already says
# what their title did (`Pick your favorite food from the list.`). A menu with any other title of its own keeps it, unless it has no
# description: then CHOICE_TITLE is its title and its own title the description (Fall '06's `Action?`, `Which class?`, `Eavesdrop?`
# and `See tutorial?`; owner, 2026-11-11).
YOU_TITLE = 'You'
CHOICE_TITLED = (YOU_TITLE, 'Food you like', 'Food you hate')
MENU_OWN_TITLE = 5                      # the menu words' flag: 1 while the pending menu shows a title of its own
# The portrait choice's title (27): BREW's string 51 is `Pick Your Best Self Portrait`, wider than the HD picker's one line (412 of
# 300 units in its title face; the native picker overlaps a second line), so this shorter one (275).
PORTRAIT_TITLE = 'Pick a Self Portrait'
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
# A story's own pictures that its catch game shows: {picture: the SHA-1 of its BMP}. Invisible Man, Skating Dating and CS Idol (as an
# event's icon) each carry the same yawning face as 26501, in their 26500 bundle; other stories' 26501 is something else, so a story
# gets this picture's size only when its own copy is this one, and otherwise its catch game stops as before.
OWN_CATCH_PICTURES = {26501: '8204515d46f4e7a38e12bb9e4f749bb27b011893'}
OWN_ICON_BASE = 26600                   # + n: the n-th of OWN_CATCH_PICTURES as an event icon (CS Idol's Practice shows the yawning face)
# A look whose body is a story's own whole picture (entry 0, 26000 up) is centred on that picture when its hotspot sits this many
# art pixels or more off its middle: King of the Road's Michael (4.5 to the left; BREW draws him off-centre too). The other own-picture
# looks (Emalee, Yewande, Stephanie, Josh) are centred already (owner, 2026-11-07).
CENTRE_OWN_BODY = 2
CATCH_TITLE, CATCH_TEXT = 'Think fast!', 'Catch the good things. Dodge the bad.'
# The catch game's own points, which mean nothing in the word game played in its place (`45 pts to pass.`, `55 points to win!`); its
# generic page title, which becomes the smartphone's banner there (its word games are titled `Snacks!`, `Fight!` and the like).
CATCH_POINTS = re.compile(rb'\s*\d+\s*(?:pts|points)\s+to\s+(?:pass|win)\s*[.!]?', re.I)
CATCH_GENERIC_TITLE = b'Instructions'
# 9.2's two games won by dodging everything (`Don't hit the pows! Get the lowest score you can!`): the word game in their place
# turns its lists and its result around, and loses the sentence.
CATCH_LOW = re.compile(rb'\s*Get the lowest score you can!', re.I)
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
    """Store an entry and, in a look list, keep its hash and BREW's box colour: entry 2 at 0 is the pink box, and a look that isn't a
    person's (GREY_BODIES, by entry 0, which a list sets first) the grey one. `base` pushes the list's first number, `old` what the
    entry held."""
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
    plain, end, grey = s.label(), s.label(), s.label()
    entity(); base(); s.call(53, 2)                         # R: entry 0
    for body in GREY_BODIES:
        s.push_result(); s.push(body); s.emit(0x0a); s.jump_if_nonzero(grey)
    value(); s.jump_if_nonzero(plain)
    s.push(PINK_THEME); s.jump(end)
    s.label(grey); s.push(GREY_THEME); s.jump(end)
    s.label(plain); s.push(BLUE_THEME)
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


def push_picture(s, location, sky, context):
    """Push the addon's picture of a location under a sky mode (-1: by the clock). Two locals' worth of work on the stack only. A
    Classic story's own pictures (context `own_backgrounds`: its location -> the addon's index) come from the addon too, and its shared
    locations are '07's (decision 7B; the "'08 Backgrounds" switch moves them back: the profile's BREW_08_BACKGROUNDS)."""
    night, day, picked, add = s.label(), s.label(), s.label(), s.label()
    extra, have, placed = s.label(), s.label(), s.label()
    for own, index in context.get('own_backgrounds', ()):
        other = s.label()
        location(); s.push(own); s.emit(0x0a); s.jump_if_zero(other)
        s.push(index); s.jump(have)
        s.label(other)
    location(); s.push(0); s.emit(0x0e); s.jump_if_zero(placed)
    s.push(SKY_ONLY); s.jump(have)
    s.label(placed)
    location(); s.push(2000); s.emit(0x0e); s.jump_if_zero(extra)
    location(); s.push(1000 - (LOCATION_07_OFFSET if context.get('backgrounds_07') else 0)); s.emit(0x51); s.jump(have)
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


def show_top_scene(s, context):
    """SHS's background for the top scene."""
    s.push(0)
    get_depth = lambda: (s.push(DEPTH_KEY), s.call(55, 1), s.push_result())
    top = lambda base: (lambda: (s.push(base), get_depth(), s.emit(0x50), s.call(55, 1), s.push_result()))
    push_picture(s, top(_SCENE_LAYOUT['location']), top(_SCENE_LAYOUT['sky']), context)
    s.call(11, 2)


def scene_open(rewriter, pc, argc, context):
    """13: (sky mode, location) a new scene on the stack, with no speaker; returns 1."""
    def build(s):
        depth = lambda: (s.push(DEPTH_KEY), s.call(55, 1), s.push_result())
        s.push(DEPTH_KEY); depth(); s.push(1); s.emit(0x50); s.call(54, 2)
        s.push(_SCENE_LAYOUT['location']); depth(); s.emit(0x50); s.arg(2); s.call(54, 2)
        s.push(_SCENE_LAYOUT['sky']); depth(); s.emit(0x50); s.arg(1); s.call(54, 2)
        set_global(s, SPEAKER_KEY, lambda: s.push(-1))
        show_top_scene(s, context)
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
        s.push(_SCENE_LAYOUT['sky']); depth(); s.emit(0x50); s.arg(2); s.call(54, 2)
        s.label(no_sky)
        s.arg(3); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(no_location)
        s.push(_SCENE_LAYOUT['location']); depth(); s.emit(0x50); s.arg(3); s.call(54, 2)
        s.label(no_location)
        s.arg(2); s.push(-1); s.emit(0x0a); s.jump_if_zero(change)
        s.arg(3); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(shown)
        s.label(change)
        show_top_scene(s, context)
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
        show_top_scene(s, context)
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


def dots(s, shown, context):
    """With a badge just up (the narration that opens an event, as `Lunch time.`), a short line that ends in a single stop ends
    in three, so it runs on into what follows (owner, 2026-11-07): `shown` then points at a copy in context's dots buffer."""
    at, last_word, last, before = (context['dots'] + k for k in range(4))
    plain, walk, found, full = s.label(), s.label(), s.label(), s.label()
    s.emit(0x40, context['opener_now']); get_global(s, BADGE_UP_KEY); s.emit(0x11); s.jump_if_zero(plain)
    s.emit(0x40, shown); s.push(0); s.emit(0x0e); s.jump_if_nonzero(plain)              # (a string handle or nothing: as it is)
    s.emit(0x40, shown); s.push(0x7FF5); s.emit(0x0d); s.jump_if_nonzero(plain)
    set_word(s, at, lambda: s.emit(0x40, shown))
    set_word(s, last_word, lambda: s.push(0))
    s.label(walk)
    s.emit(0x40, at); s.emit(0x40, shown); s.emit(0x51); s.push(OPENER_WORDS); s.emit(0x0c); s.jump_if_nonzero(plain)
    s.emit(0x40, at); s.emit(0x3f); s.jump_if_zero(full)                                 # a word of 0: the last ended the word before
    s.emit(0x40, at); s.emit(0x3f); s.push(256); s.emit(0x54); s.jump_if_zero(found)     # its second letter is the end
    set_word(s, last_word, lambda: (s.emit(0x40, at), s.emit(0x3f)))
    set_word(s, at, lambda: (s.emit(0x40, at), s.push(1), s.emit(0x50)))
    s.jump(walk)
    s.label(found)
    set_word(s, last, lambda: (s.emit(0x40, at), s.emit(0x3f), s.push(256), s.emit(0x53)))
    set_word(s, before, lambda: (s.emit(0x40, last_word), s.push(256), s.emit(0x54)))
    end = s.label()
    s.jump(end)
    s.label(full)
    set_word(s, last, lambda: (s.emit(0x40, last_word), s.push(256), s.emit(0x54)))
    set_word(s, before, lambda: (s.emit(0x40, last_word), s.push(256), s.emit(0x53)))
    s.label(end)
    s.emit(0x40, last); s.push(ord('.')); s.emit(0x0b); s.jump_if_nonzero(plain)
    s.emit(0x40, before); s.push(ord('.')); s.emit(0x0a); s.jump_if_nonzero(plain)
    s.push(context['dots_buffer']); s.text('%s..'); s.emit(0x40, shown); s.call(22, 3)
    set_word(s, shown, lambda: s.push(context['dots_buffer']))
    s.label(plain)


def say(s, text, speaker, expression, context):
    """SHS's dialogue for `text` under BREW's speaker (callables pushing them): no speaker or Event is the narrator, a character with no
    picture says it under its name with none (service 76), and anyone else with their face. A whole line in brackets loses them: it's
    plain narration from the narrator, and a thought from anyone else. What's shown is kept as the last line, for a choice's question."""
    done, found, spoken = s.label(), s.label(), s.label()
    shown, twin = context['last_line'], context['line_twin']
    set_word(s, shown, text)
    set_word(s, twin, lambda: s.push(-1))
    # An empty line (the story's first, its title: title_line) isn't shown.
    s.emit(0x40, shown); s.emit(0x3f); s.push(0); s.emit(0x0d)
    s.emit(0x40, shown); s.emit(0x3f); s.push(256); s.emit(0x0e); s.emit(0x12); s.jump_if_nonzero(done)
    for address, icon, badge in context['captions']:
        other = s.label()
        s.emit(0x40, shown); s.push(address); s.emit(0x0a); s.jump_if_zero(other)
        s.push(icon); s.push(badge); s.call(90, 2)
        set_global(s, BADGE_UP_KEY, lambda: s.push(1))
        s.jump(done)
        s.label(other)
    if context.get('date_captions'):
        not_date = s.label()
        s.emit(0x40, shown); get_global(s, DATE_CAPTION_KEY); s.emit(0x0a); s.jump_if_zero(not_date)
        set_global(s, DATE_CAPTION_KEY, lambda: s.push(0))
        get_global(s, BADGE_ICON_KEY); s.emit(0x40, shown); s.call(90, 2)
        set_global(s, BADGE_UP_KEY, lambda: s.push(1))
        s.jump(done)
        s.label(not_date)
    for address, bare in context['bracketed']:
        other = s.label()
        s.emit(0x40, shown); s.push(address); s.emit(0x0a); s.jump_if_zero(other)
        set_word(s, twin, lambda bare=bare: s.push(bare))
        set_word(s, shown, lambda bare=bare: s.push(bare))
        s.jump(found)
        s.label(other)
    s.label(found)
    set_word(s, context['opener_now'], lambda: get_global(s, OPENER_KEY))
    set_global(s, OPENER_KEY, lambda: s.push(0))

    def output(end):
        narrated, voice, plain, unnamed = s.label(), s.label(), s.label(), s.label()
        # A name the story set for this line's plate (15): the line goes out under it, with no portrait. A plate that adds nothing
        # (blank, or the line's own first word: `Art` over `Art class.`) goes, and the line is the narrator's (owner, 2026-11-08).
        s.emit(0x40, context['plate']); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(unnamed)
        if context.get('plates'):
            plate_is_noise(s, context, shown, narrated)
            # The plate is only the name BREW's panel shows: its picture stays the scene's speaker's (14), as Tardy-Slip's
            # brewName sets only the dialogue's name (Fall '06's ending: the Kid's face under `Elmo`; owner, 2026-11-09). A
            # speaker with a face says it under the plate's name for that line; anyone else's goes out as the name alone.
            faceless = s.label()
            speaker(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(faceless)
            speaker(); s.push(EVENT_CHARACTER_KEY); s.call(55, 1); s.push_result(); s.emit(0x0a); s.jump_if_nonzero(faceless)
            resolve_look(s, speaker, context)
            speaker(); s.call(73, 1); s.push_result(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(faceless)
            speaker(); s.push(context['plate_name']); s.call(61, 2)
            speaker(); s.emit(0x40, context['plate']); s.call(64, 2)
            s.emit(0x40, shown); speaker(); push_face(s, expression); s.call(13, 3)
            speaker(); s.push(context['plate_name']); s.call(64, 2)
            s.jump(end)
            s.label(faceless)
        s.emit(0x40, context['plate']); s.emit(0x40, shown); s.call(76, 2)
        s.jump(end)
        s.label(unnamed)
        speaker(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(narrated)
        speaker(); s.push(EVENT_CHARACTER_KEY); s.call(55, 1); s.push_result(); s.emit(0x0a); s.jump_if_nonzero(narrated)
        resolve_look(s, speaker, context)
        speaker(); s.call(73, 1); s.push_result(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(voice)
        s.emit(0x40, twin); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(plain)
        s.push(-2); s.emit(0x40, twin); speaker(); push_face(s, expression); s.call(13, 4)
        s.jump(end)
        s.label(plain)
        s.emit(0x40, shown); speaker(); push_face(s, expression); s.call(13, 3)
        s.jump(end)
        s.label(voice)
        speaker(); s.push(context['name_buffer']); s.call(61, 2)
        s.push(context['name_buffer']); s.emit(0x40, shown); s.call(76, 2)
        s.jump(end)
        s.label(narrated)
        dots(s, shown, context)
        s.emit(0x40, shown); s.push(NARRATOR); s.call(13, 2)
        s.jump(end)
    def clear_badge(then):
        """Take a time badge away once the message it came with has been read, then go on to `then`."""
        get_global(s, BADGE_UP_KEY); s.jump_if_zero(then)
        s.push(-1); s.push(-1); s.call(90, 2)
        set_global(s, BADGE_UP_KEY, lambda: s.push(0))
        s.jump(then)
    # A line longer than LONGEST_LINE goes out in pieces (long_lines: [count, piece...]), each as the line itself would.
    table, index = context['pieces'], context['pieces'] + 1
    chosen, whole, next_piece = s.label(), s.label(), s.label()
    set_word(s, table, lambda: s.push(-1))
    for key, pieces in context['long_lines']:
        other = s.label()
        s.emit(0x40, shown); s.push(key); s.emit(0x0a); s.jump_if_zero(other)
        set_word(s, table, lambda pieces=pieces: s.push(pieces))
        s.jump(chosen)
        s.label(other)
    s.label(chosen)
    s.emit(0x40, table); s.push(-1); s.emit(0x0a); s.jump_if_zero(whole)
    output(spoken)
    s.label(whole)
    set_word(s, index, lambda: s.push(0))
    thought_line = context['pieces'] + 2                    # the whole line is a thought (its twin is set)
    set_word(s, thought_line, lambda: (s.emit(0x40, twin), s.push(-1), s.emit(0x0b)))
    s.label(next_piece)
    s.emit(0x40, index); s.emit(0x40, table); s.emit(0x3f); s.emit(0x0e); s.jump_if_zero(spoken)
    set_word(s, shown, lambda: (s.emit(0x40, table), s.push(1), s.emit(0x50), s.emit(0x40, index), s.emit(0x50), s.emit(0x3f)))
    kept, speech, plain_piece = s.label(), s.label(), s.label()
    # A negative entry is an aside: the speaker's thought (a line led by speech, shown_parts).
    s.emit(0x40, shown); s.push(0); s.emit(0x0e); s.jump_if_zero(speech)
    set_word(s, shown, lambda: (s.push(0), s.emit(0x40, shown), s.emit(0x51)))
    set_word(s, twin, lambda: s.emit(0x40, shown))
    s.jump(kept)
    s.label(speech)
    s.emit(0x40, thought_line); s.jump_if_zero(plain_piece)
    set_word(s, twin, lambda: s.emit(0x40, shown))
    s.jump(kept)
    s.label(plain_piece)
    set_word(s, twin, lambda: s.push(-1))
    s.label(kept)
    set_word(s, index, lambda: (s.emit(0x40, index), s.push(1), s.emit(0x50)))
    after = s.label()
    output(after)
    s.label(after)
    clear_badge(next_piece)                                 # each piece is a message of its own
    # A time badge stays for the line after it only, as Football Star's do (90, a line, then 90 with -1).
    s.label(spoken)
    set_word(s, context['plate'], lambda: s.push(-1))
    clear_badge(done)
    s.label(done)


def push_text_byte(s, text, index):
    """Push byte `index` (a word) of the string at the address in word `text`: high byte first, two to a word. A byte from 0x80 up
    comes out other than itself, but the same from either string, which is all plate_is_noise compares."""
    s.emit(0x40, text); s.emit(0x40, index); s.push(2); s.emit(0x53); s.emit(0x50); s.emit(0x3f)
    odd, done = s.label(), s.label()
    s.emit(0x40, index); s.push(2); s.emit(0x54); s.jump_if_nonzero(odd)
    s.push(256); s.emit(0x53); s.jump(done)
    s.label(odd)
    s.push(256); s.emit(0x54)
    s.label(done)


def plate_is_noise(s, context, line, noise):
    """Jump to `noise` when the plate (word context['plate']) adds nothing to the line (the address in word `line`): it's blank, or
    the line starts with it and then a space (`Art` over `Art class.`; owner, 2026-11-08)."""
    i, byte = context['plate_scan'], context['plate_scan'] + 1
    top, kept = s.label(), s.label()
    for text in (context['plate'], line):                   # (a dynamic string's handle, 0x7FF5 up, isn't an address to read)
        s.emit(0x40, text); s.push(0x7FF5); s.emit(0x0d); s.emit(0x40, text); s.push(0); s.emit(0x0e); s.emit(0x11)
        s.jump_if_nonzero(kept)
    set_word(s, i, lambda: s.push(0))
    push_text_byte(s, context['plate'], i); s.push(0x20); s.emit(0x0c); s.jump_if_zero(noise)     # blank: nothing above a space
    s.label(top)
    s.emit(0x40, i); s.push(40); s.emit(0x0c); s.jump_if_nonzero(kept)
    set_word(s, byte, lambda: push_text_byte(s, context['plate'], i))
    end_of_plate = s.label()
    s.emit(0x40, byte); s.jump_if_zero(end_of_plate)
    push_text_byte(s, line, i); s.emit(0x40, byte); s.emit(0x0b); s.jump_if_nonzero(kept)
    set_word(s, i, lambda: (s.emit(0x40, i), s.push(1), s.emit(0x50)))
    s.jump(top)
    s.label(end_of_plate)
    push_text_byte(s, line, i); s.push(0x20); s.emit(0x0a); s.jump_if_nonzero(noise)
    s.label(kept)


def name_plate(rewriter, pc, argc, context):
    """15: (text) the name plate's text for the line that follows (Bad Meatloaf's helper: 14, 15, 16, 74)."""
    def build(s):
        set_word(s, context['plate'], lambda: s.arg(1))
        s.result(0)
    rewriter.redirect(pc, 'name_plate', build)


def line(rewriter, pc, argc, context):
    """72: (speaker, text, expression), dropped with no scene open (shs08.5.mod)."""
    def build(s):
        done = s.label()
        # A name plate (15) is for the text 74 shows (16's), not a speaker's line: one set by a helper that queues a line and
        # never shows it (Trouble with MoonDog's Radio, Goth Girls Cry Too's Phone; Stage 5) goes, as Tardy-Slip's 72 names
        # the speaker.
        set_word(s, context['plate'], lambda: s.push(-1))
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
    """28: (title, `a|b|c`) the menu 74 shows; returns 1. A menu titled `You` (or a food menu: CHOICE_TITLED) says CHOICE_TITLE; any
    other keeps its own title, flagged (MENU_OWN_TITLE) for 74, which moves it under CHOICE_TITLE when the menu has no description."""
    def build(s):
        set_word(s, context['menu'], lambda: s.arg(1))
        set_word(s, context['menu'] + MENU_OWN_TITLE, lambda: s.push(1))
        for address in context.get('you_titles', ()):
            other = s.label()
            s.arg(1); s.push(address); s.emit(0x0a); s.jump_if_zero(other)
            set_word(s, context['menu'], lambda: s.text(CHOICE_TITLE))
            set_word(s, context['menu'] + MENU_OWN_TITLE, lambda: s.push(0))
            s.label(other)
        set_word(s, context['menu'] + 1, lambda: s.arg(2))
        set_word(s, context['menu'] + 2, lambda: s.push(-1))
        set_word(s, context['menu'] + 4, lambda: s.push(-1))
        s.result(1)
    rewriter.redirect(pc, ('menu', context['rid']), build)


def portrait_choice(rewriter, pc, argc, context):
    """27: (count, list) the portrait choice 74 shows: the characters in the list (the M.A.S.H. packs' photos) as SHS's portrait
    picker (78), whose answer is the chosen one's place in the list, as BREW's. Returns 1."""
    def build(s):
        set_word(s, context['portraits'], lambda: s.arg(1))
        set_word(s, context['portraits'] + 1, lambda: s.arg(2))
        s.result(1)
    rewriter.redirect(pc, ('portrait_choice', context['rid']), build)


def spinning_menu(rewriter, pc, argc, context):
    """30: (title, `a|b|c`, ms) a menu whose cursor jumps to a random other option every interval, and 31 gives it a limit. Only
    single-round questions get here (word_game takes the rest), and they become the smartphone's "Think fast!", with BREW's title, the
    question, under it. Time running out takes wherever the cursor is, so here a random option. The spin itself isn't reproduced."""
    def build(s):
        set_word(s, context['menu'], lambda: s.text(TIMED_TITLE))
        set_word(s, context['menu'] + MENU_OWN_TITLE, lambda: s.push(0))
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
        if context.get('portraits') is not None:
            portraits, no_portraits, each, shown = context['portraits'], s.label(), s.label(), s.label()
            s.emit(0x40, portraits); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(no_portraits)
            # Each photo's look first, as a line's speaker gets: the picker shows the faces their lists name.
            set_word(s, portraits + 2, lambda: s.push(0))
            s.label(each)
            s.emit(0x40, portraits + 2); s.emit(0x40, portraits); s.emit(0x0e); s.jump_if_zero(shown)
            resolve_look(s, lambda: (s.emit(0x40, portraits + 1), s.emit(0x40, portraits + 2), s.emit(0x50), s.emit(0x3f)), context)
            set_word(s, portraits + 2, lambda: (s.emit(0x40, portraits + 2), s.push(1), s.emit(0x50)))
            s.jump(each)
            s.label(shown)
            s.text(PORTRAIT_TITLE); s.emit(0x40, portraits); s.emit(0x40, portraits + 1); s.call(78, 3)
            s.push_result()
            set_word(s, portraits, lambda: s.push(-1))
            set_global(s, FIELD_KEY, lambda: s.emit(0x41, 0))
            s.push(FIELD_KEY); s.call(55, 1)
            s.jump(done)
            s.label(no_portraits)
        s.emit(0x40, context['menu'] + 1); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(no_menu)
        # A title of its own with nothing under it (no question, no line before): CHOICE_TITLE, and the title as the description.
        kept = s.label()
        s.emit(0x40, context['menu'] + MENU_OWN_TITLE); s.jump_if_zero(kept)
        s.emit(0x40, context['menu'] + 4); s.push(-1); s.emit(0x0a); s.jump_if_zero(kept)
        s.emit(0x40, context['last_line']); s.push(-1); s.emit(0x0a); s.jump_if_zero(kept)
        set_word(s, context['menu'] + 4, lambda: s.emit(0x40, context['menu']))
        set_word(s, context['menu'], lambda: s.text(CHOICE_TITLE))
        s.label(kept)
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


CATCH_COMPARES = {0x0a: '==', 0x0b: '!=', 0x0c: '>', 0x0d: '>=', 0x0e: '<', 0x0f: '<='}
CATCH_CUT_REACH = 400                   # instructions after a catch game in which its score is read


# BREW services that answer in R, replacing what a catch game left there: random (6), a field (8), stored numbers (51, 59, 61),
# list reads (63, 65), string equality (3), a weighted pick (73).
R_SERVICES = {3, 6, 8, 51, 59, 61, 63, 65, 73}
CATCH_PUSHES = {0x1a: 1, 0x1b: 2, 0x40: 1, 0x41: 1, 0x5a: 1, 0x5b: 1, 0x5f: 1, 0x60: 1, 0x61: 1, 0x62: 1}


def catch_store_target(code, pc):
    """The frame address (0x5f-0x62, or 0x23 n: a local's place) the catch game at `pc` stores its score in, when its arguments are single
    pushes (0x1b pushes two) and that address comes just before them; else None."""
    wanted, k = code[pc][1] & 255, pc - 1
    while wanted > 0 and k >= 0 and code[k][0] in CATCH_PUSHES:
        wanted -= CATCH_PUSHES[code[k][0]]
        k -= 1
    if wanted != 0 or k < 0 or not (0x5f <= code[k][0] <= 0x62 or code[k][0] == 0x23):
        return None
    return code[k]


def catch_cuts(code, pc):
    """The scores at which the story after the catch game at `pc` can go another way, for its skip prompt
    (choice_hints.brew_catch_outcomes), or None when it can't tell. BREW stores the result (R) and reads it back with a short
    load; every read up to the next catch game (or CATCH_CUT_REACH) must compare it with a constant (`>= 45`, `== 0`), each
    giving where the answer changes. A read used any other way (a sum, a call) gives None, and the prompt tries the scores
    one by one instead. A read can be another value kept in the same place later on: that only adds cuts, which costs a
    preview, never an outcome. Checked against the score-by-score search on every catch game the Campaign reaches."""
    ops = [item[0] for item in code]
    if ops[pc + 1:pc + 4] != [0x21, 0x3e, 0x15]:
        # A score never taken (M.A.S.H. 2 and 6): before anything reads R, straight on, a service that answers in R (BREW's 6,
        # a random number) replaces it. It changes nothing. Services that answer nothing leave R as it was, so they don't count.
        k = pc + 1
        while k < len(code) and (ops[k] in CATCH_PUSHES or ops[k] in (0x23, 0x1f)):
            if ops[k] == 0x1f and code[k][1] >> 8 in R_SERVICES:
                return []
            k += 1
        return None
    load = tuple(code[pc + 4:pc + 6])
    end = next((k for k in range(pc + 1, min(pc + CATCH_CUT_REACH, len(code)))
                if code[k][0] == 0x1f and (code[k][1] >> 8) in CATCH_MODES), min(pc + CATCH_CUT_REACH, len(code)))
    # A helper keeping the score in a local of its own (Classic, M.A.S.H.; Stage 4): the local is the frame address pushed before
    # the call's arguments, and only the helper's own code (up to the next function's PUSH_FP) can read it; other functions'
    # locals of the same number aren't it. A score it never reads back changes nothing: no cuts, one outcome.
    target = catch_store_target(code, pc)
    local = None
    if target is not None:
        load = (target, (0x3f, None))
        # (Its value is also read as 0x41 with the local's number: 9.3 Monkeyssori.)
        local = target[1] if target[0] == 0x23 else target[0] - 0x5f
        end = next((k for k in range(pc + 1, len(code)) if code[k][0] == 0x48), len(code))

    def read(k):
        """How many instructions read the score at `k` (a load and a dereference, or one 0x41), or 0."""
        if tuple(code[k:k + 2]) == load:
            return 2
        return 1 if local is not None and code[k][0] == 0x41 and signed16(code[k][1]) == local else 0
    if target is not None and not any(read(k) for k in range(pc + 4, end - 1)):
        return []
    cuts, k = set(), pc + 4
    while k < end - 1:
        size = read(k)
        if not size:
            k += 1
            continue
        if k + size + 1 >= len(code):
            return None
        (push, value), (compare, _) = code[k + size], code[k + size + 1]
        flipped = False
        if code[k + size][0] in CATCH_COMPARES and code[k - 1][0] in (0x1a, 0x5a, 0x5b):
            # The constant first (`30 <= score`, Classic's ranges): the same test, the other way round.
            (push, value), compare, flipped = code[k - 1], code[k + 2][0], True
        if push in (0x5a, 0x5b):
            value = push - 0x5a
        elif push in (0x1a, 0x1b) and not (flipped and push == 0x1b):
            value = signed16(value)
        else:
            return None
        if compare not in CATCH_COMPARES:
            return None
        sign = CATCH_COMPARES[compare]
        if flipped:
            sign = {'<=': '>=', '<': '>', '>=': '<=', '>': '<'}.get(sign, sign)
        cuts |= {value} if sign in ('>=', '<') else {value + 1} if sign in ('>', '<=') else {value, value + 1}
        k += size + (1 if flipped else 2)
    return sorted(c for c in cuts if c > 0)


def catch_game(rewriter, pc, argc, context):
    """19, 20, 21: the catch game, whose score BREW's scripts read from R, usually testing it against the target. Service 221 where
    the player has the switch on, with the page before it as a panel. Otherwise, a word game under that page, its items' words good or
    bad by their value: its result out of the smartphone's pass mark is that share of the target, which reaches every band the
    scripts test (all 181 sites' constants, 2026-11-05: at a target of 45, a score of 6 gives 45, then 37, 30, 22 and so on). It goes on
    in B for the push after the call, as what it has to do on the way out would replace R."""
    service = rewriter.code[pc][1] >> 8
    mode = CATCH_MODES[service]
    reads = rewriter.code[pc + 1] == (0x21, None)
    cuts = catch_cuts(rewriter.code, pc)
    cut_table = -1 if cuts is None else rewriter.words([len(cuts), *cuts])
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
        # A picture an earlier kind has shown adds its words once (9.2's weights are two kinds of dumbbell).
        s.emit(0x23, 1); s.push(0); s.emit(0x3e); s.emit(0x15)
        earlier, new_picture = s.label(), s.label()
        s.label(earlier)
        s.emit(0x41, 1); s.emit(0x41, 0); s.emit(0x0e); s.jump_if_zero(new_picture)
        s.arg(list_arg); s.push(2); s.emit(0x50); s.emit(0x41, 1); s.push(3); s.emit(0x52); s.emit(0x50); s.emit(0x3f)
        count_at(1); s.emit(0x0a); s.jump_if_nonzero(kept)
        s.emit(0x23, 1); s.emit(0x41, 1); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.jump(earlier)
        s.label(new_picture)
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
        low, flagged = s.label(), s.label()
        for address in context['catch_low']:
            s.emit(0x40, page + 1); s.push(address); s.emit(0x0a); s.jump_if_nonzero(low)
        s.push(0); s.jump(flagged)
        s.label(low)
        s.push(1)
        s.label(flagged)                                    # local 2: won by the lowest score

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
        # A game won by the lowest score (catch_low): the pictures' words are the ones to avoid, and the score turns around.
        swapped, lists = s.label(), s.label()
        s.emit(0x41, 2); s.jump_if_nonzero(swapped)
        s.push(good); s.push(bad); s.jump(lists)
        s.label(swapped)
        s.push(bad); s.push(good)
        s.label(lists)
        s.push(WORD_GAME_MS); s.push(PLAYER); s.push(1); s.push(WORD_GAME_REFRESH_MS)
        s.call(71, 8)
        s.push_result()                                     # local 3: the result
        set_word(s, page + 1, lambda: s.push(-1))
        short, scored, kept_score = s.label(), s.label(), s.label()
        s.emit(0x41, 3); s.push(WORD_GAME_PASS); s.emit(0x0d); s.jump_if_zero(short)
        s.arg(1); s.jump(scored)
        s.label(short)
        s.emit(0x41, 3); s.arg(1); s.emit(0x52); s.push(WORD_GAME_PASS); s.emit(0x53)
        s.label(scored)
        s.emit(0x41, 2); s.jump_if_zero(kept_score)
        s.arg(1); s.emit(0x51); s.push(-1); s.emit(0x52)       # the target less it
        s.label(kept_score)
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
        s.push(cut_table)
        s.call(BREW_CATCH, 12)
        s.push_result(); s.emit(0x04)
        s.label(done)
        s.result(0)
    rewriter.redirect(pc, ('catch', context['rid'], service, reads, None if cuts is None else tuple(cuts)), build)


def game_page(rewriter, pc, argc, context):
    """12: (title, text) the page before a word game: its title and description, on the game's own screen."""
    def build(s):
        set_word(s, context['page'], lambda: s.arg(1))
        set_word(s, context['page'] + 1, lambda: s.arg(2))
        s.result(0)
    rewriter.redirect(pc, ('game_page', context['rid']), build)


NAME_TAG = re.compile(rb'\$[A-Za-z_][A-Za-z0-9_]*')


def named_texts(program, rewriter):
    """[(address, format, keys)]: each string with `$NAME` tags (and no `%`), as a format with `%s` for each tag. Service 71 shows
    its texts raw, as the native game does (ENGINE_ABI), so a word game's title and question get their names from these."""
    found = []
    for address, text, _ in data_strings(program):
        keys = NAME_TAG.findall(text)
        if keys and b'%' not in text:
            found.append((address, rewriter.text(NAME_TAG.sub(b'%s', text).decode('latin-1')), [k.decode('latin-1') for k in keys]))
    return found


def named_words(program, rewriter, start):
    """What a script with a word game needs to fill names into its texts (named_texts): nothing for the rest, as a big story's data
    is close to the VM's stack (5.6 Blake Reformed, 2026-11-06)."""
    found = named_texts(program, rewriter) if start is not None else []
    if not found:
        return dict(named_texts=[], named_question=rewriter.words([0])) if start is not None else dict(named_texts=[])
    longest = max(len(text) for _, text, _ in data_strings(program) if NAME_TAG.search(text))
    room = (longest + 2 * NAME_WORDS * 2) // 2 + 2
    return dict(named_texts=found, named_held=rewriter.words([0]), named_question=rewriter.words([0]),
                named_title=rewriter.words([0] * room), named_text=rewriter.words([0] * room))


def calendar_words(rewriter):
    """What a Classic story's scripts need for the calendar (calendar_step), added only to theirs."""
    return dict(key_buffer=rewriter.words([0] * 16), cal_j=rewriter.words([0]), cal_best=rewriter.words([0]),
                cal_slot=rewriter.words([0]), cal_t=rewriter.words([0, 0, 0]), date_buffer=rewriter.words([0] * 24), badge_buffer=rewriter.words([0] * 32),
                month_days=rewriter.words(MONTH_DAYS), weekday_names=rewriter.words([rewriter.text(n) for n in WEEKDAYS]),
                month_names=rewriter.words([rewriter.text(n) for n in MONTHS]))


def push_named(s, context, push_text, buffer):
    """Push a text (`push_text` pushes its address), with its `$NAME` tags filled in when it's one of the story's named texts."""
    if not context['named_texts']:
        push_text()
        return
    held, done = context['named_held'], s.label()
    set_word(s, held, push_text)
    for address, form, keys in context['named_texts']:
        other = s.label()
        s.emit(0x40, held); s.push(address); s.emit(0x0a); s.jump_if_zero(other)
        s.push(buffer); s.push(form)
        for n, key in enumerate(keys):
            s.text(key); s.text(''); s.push(-1 - n); s.call(47, 3); s.push_result()
        s.call(22, 2 + len(keys))
        s.push(buffer); s.jump(done)
        s.label(other)
    s.emit(0x40, held)
    s.label(done)


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
        push_named(s, context, lambda: s.emit(0x40, page), context.get('named_title'))
        s.label(title)
        question = s.label()
        s.emit(0x40, page + 1); s.push(-1); s.emit(0x0a); s.jump_if_zero(described)
        set_word(s, context['named_question'], lambda: s.emit(0x40, context['last_line'])); s.jump(question)
        s.label(described)
        set_word(s, context['named_question'], lambda: s.emit(0x40, page + 1))
        s.label(question)
        push_named(s, context, lambda: s.emit(0x40, context['named_question']), context.get('named_text'))
        s.label(described_end)
        s.push(good); s.push(bad); s.push(WORD_GAME_MS); s.push(PLAYER); s.push(1); s.push(WORD_GAME_REFRESH_MS)
        s.call(71, 8)
        s.push_result()                                     # local 2: the result
        set_word(s, page + 1, lambda: s.push(-1))
        # A pass is the best total; anything less, its share. Compared before multiplying: the skip prompt's Win is 32767
        # (Session.skip_minigame), which times the rounds and the best score overflowed a word into a loss (1.1, 2026-11-05).
        short, returned = s.label(), s.label()
        s.emit(0x41, 2); s.push(WORD_GAME_PASS); s.emit(0x0d); s.jump_if_zero(short)
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
    if context['kind'] == 'calendar':
        return field_set_calendar(rewriter, pc, argc, context)
    if context['kind'] == 'season':
        return season_field_set(rewriter, pc, argc, context)
    rewriter.redirect(pc, 'field_set', lambda s: (s.arg(2), s.push(FIELD_KEY), s.emit(0x50), s.arg(3), s.call(54, 2), s.result(0)))


def event_text(rewriter, pc, argc, context):
    """7: (destination) the event's text."""
    def build(s):
        s.text(EVENT_TEXT); s.text(''); s.push(-1); s.call(47, 3); s.push_result()
        s.arg(1); s.text('%s'); s.emit(0x41, 0); s.call(22, 3)
        s.result(0)
    rewriter.redirect(pc, ('event_text', context['rid']), build)


_EVENT_LAYOUT = {'base': EVENT_BASE}   # (where events are kept: the Classic driver's, or SEASON_EVENTS while a season is translated)


def event_key(s, number, offset):
    """Push event `number`'s (a callable pushing it, 1 first) saved-number key at `offset`."""
    number(); s.push(1); s.emit(0x51); s.push(EVENT_STRIDE); s.emit(0x52); s.push(_EVENT_LAYOUT['base'] + offset); s.emit(0x50)


def event_get(s, number, offset):
    event_key(s, number, offset); s.call(55, 1); s.push_result()


def event_set(s, number, offset, value):
    event_key(s, number, offset); value(); s.call(54, 2)


def keyed_text(s, form, number, buffer):
    """Write event `number`'s text key (`form`, with its number) into `buffer`."""
    s.push(buffer); s.text(form); number(); s.call(22, 3)


def push_month_days(s, context, month):
    """Push the length of `month` (a callable; 13 and on are the next year's)."""
    s.push(context['month_days']); month(); s.push(1); s.emit(0x51); s.push(12); s.emit(0x54); s.emit(0x50); s.emit(0x3f)


def push_day_index(s, context, month, date):
    """Push the calendar's day number of `month`/`date` (callables), as brew-calendar.js `dayIndex`."""
    m, n, k = context['cal_t'], context['cal_t'] + 1, context['cal_t'] + 2
    M, N, K = (lambda: s.emit(0x40, m)), (lambda: s.emit(0x40, n)), (lambda: s.emit(0x40, k))
    first = lambda: get_global(s, START_MONTH_KEY)
    later, loop, done, end = s.label(), s.label(), s.label(), s.label()
    set_word(s, m, month)
    M(); first(); s.emit(0x0e); s.jump_if_zero(later)
    set_word(s, m, lambda: (M(), s.push(12), s.emit(0x50)))
    s.label(later)
    other = s.label()
    M(); first(); s.emit(0x0a); s.jump_if_zero(other)
    date(); get_global(s, START_DATE_KEY); s.emit(0x51); s.jump(end)
    s.label(other)
    set_word(s, n, lambda: (push_month_days(s, context, first), get_global(s, START_DATE_KEY), s.emit(0x51)))
    set_word(s, k, lambda: (first(), s.push(1), s.emit(0x50)))
    s.label(loop)
    K(); M(); s.emit(0x0e); s.jump_if_zero(done)
    set_word(s, n, lambda: (N(), push_month_days(s, context, K), s.emit(0x50)))
    set_word(s, k, lambda: (K(), s.push(1), s.emit(0x50)))
    s.jump(loop)
    s.label(done)
    N(); date(); s.emit(0x50)
    s.label(end)


def push_weekday(s, day):
    """Push day `day`'s weekday (0 Sunday)."""
    get_global(s, WEEKDAY_KEY); day(); s.emit(0x50); s.push(7); s.emit(0x54); s.push(7); s.emit(0x50); s.push(7); s.emit(0x54)


def push_next_school_day(s, day):
    """Push the school day after `day` (BREW's calendar keeps Monday, Wednesday and Friday), or -1 after a Friday's... none."""
    two, three, end = s.label(), s.label(), s.label()
    push_weekday(s, day); s.push(1); s.emit(0x0a); push_weekday(s, day); s.push(3); s.emit(0x0a); s.emit(0x11)
    s.jump_if_nonzero(two)
    push_weekday(s, day); s.push(5); s.emit(0x0a); s.jump_if_nonzero(three)
    s.push(-1); s.jump(end)
    s.label(two)
    day(); s.push(2); s.emit(0x50); s.jump(end)
    s.label(three)
    day(); s.push(3); s.emit(0x50)
    s.label(end)


def date_of(s, context, day):
    """Day `day`'s month (1-12, in cal_t) and date (cal_t + 1), as brew-calendar.js `dateOf`."""
    m, d, k = context['cal_t'], context['cal_t'] + 1, context['cal_t'] + 2
    loop, done, same = s.label(), s.label(), s.label()
    set_word(s, m, lambda: get_global(s, START_MONTH_KEY))
    set_word(s, d, lambda: get_global(s, START_DATE_KEY))
    set_word(s, k, lambda: s.push(0))
    s.label(loop)
    s.emit(0x40, k); day(); s.emit(0x0e); s.jump_if_zero(done)
    set_word(s, d, lambda: (s.emit(0x40, d), s.push(1), s.emit(0x50)))
    s.emit(0x40, d); push_month_days(s, context, lambda: s.emit(0x40, m)); s.emit(0x0f); s.jump_if_nonzero(same)
    set_word(s, d, lambda: s.push(1))
    set_word(s, m, lambda: (s.emit(0x40, m), s.push(12), s.emit(0x54), s.push(1), s.emit(0x50)))
    s.label(same)
    set_word(s, k, lambda: (s.emit(0x40, k), s.push(1), s.emit(0x50)))
    s.jump(loop)
    s.label(done)


def write_date(s, context, day):
    """`Wednesday, April 12` for day `day` into the context's date buffer (as BREW's planner heads a day)."""
    m, d = context['cal_t'], context['cal_t'] + 1
    date_of(s, context, day)
    s.push(context['date_buffer']); s.text('%s, %s %d')
    s.push(context['weekday_names']); push_weekday(s, day); s.emit(0x50); s.emit(0x3f)
    s.push(context['month_names']); s.emit(0x40, m); s.push(1); s.emit(0x51); s.emit(0x50); s.emit(0x3f)
    s.emit(0x40, d)
    s.call(22, 5)


def calendar_setup(rewriter, pc, argc, context):
    """69: (day start, day end, start month, start day, weekday, end month, end day). The clock starts at the day's start; the
    events kept from another playthrough go."""
    def build(s):
        set_global(s, CLOCK_KEY, lambda: s.arg(1))
        set_global(s, DAY_START_KEY, lambda: s.arg(1))
        set_global(s, DAY_END_KEY, lambda: s.arg(2))
        set_global(s, START_MONTH_KEY, lambda: s.arg(3))
        set_global(s, START_DATE_KEY, lambda: s.arg(4))
        set_global(s, WEEKDAY_KEY, lambda: s.arg(5))
        set_global(s, LAST_DAY_KEY, lambda: push_day_index(s, context, lambda: s.arg(6), lambda: s.arg(7)))
        for key in (EVENTS_KEY, ACTIVE_KEY, TIMED_KEY, STARTED_KEY, DAY_KEY, SHOWN_DAY_KEY):
            set_global(s, key, lambda: s.push(0))
        s.result(0)
    rewriter.redirect(pc, ('calendar_setup', context['rid']), build)


def push_event_script(s, context, script):
    """Push the SHS script that BREW script `script` (a callable) became (context's script map; the story's for any other)."""
    end = s.label()
    for brew_id, shs_id in sorted(context['script_map'].items()):
        if shs_id == STORY_SCRIPT:
            continue
        other = s.label()
        script(); s.push(brew_id); s.emit(0x0a); s.jump_if_zero(other)
        s.push(shs_id); s.jump(end)
        s.label(other)
    s.push(STORY_SCRIPT)
    s.label(end)


def add_event(s, context, script, minute, duration, icon, flag, text, name, day):
    """A new event on the list (EVENTS_KEY up by one), waiting, with no fields yet; its text and name kept under its number."""
    buffer, field, fields_done = context['key_buffer'], s.label(), s.label()
    set_global(s, EVENTS_KEY, lambda: (get_global(s, EVENTS_KEY), s.push(1), s.emit(0x50)))
    number = lambda: get_global(s, EVENTS_KEY)
    for offset, value in ((EVENT_MINUTE, minute), (EVENT_DURATION, duration), (EVENT_ICON, icon), (EVENT_FLAG, flag)):
        event_set(s, number, offset, value)
    event_set(s, number, EVENT_STATE, lambda: s.push(WAITING))
    event_set(s, number, EVENT_DAY, day)
    event_set(s, number, EVENT_SCRIPT, lambda: push_event_script(s, context, script))
    event_set(s, number, EVENT_COPIES, lambda: s.push(1))
    set_word(s, context['cal_j'], lambda: s.push(0))
    s.label(field)
    s.emit(0x40, context['cal_j']); s.push(16); s.emit(0x0e); s.jump_if_zero(fields_done)
    event_key(s, number, EVENT_FIELDS); s.emit(0x40, context['cal_j']); s.emit(0x50); s.push(0); s.call(54, 2)
    set_word(s, context['cal_j'], lambda: (s.emit(0x40, context['cal_j']), s.push(1), s.emit(0x50)))
    s.jump(field)
    s.label(fields_done)
    keyed_text(s, EVENT_TEXT_KEY, number, buffer); s.push(buffer); text(); s.call(46, 2)
    keyed_text(s, EVENT_NAME_KEY, number, buffer); s.push(buffer); name(); s.call(46, 2)
    named = s.label()
    name(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(named)   # (a string handle, 0x7FF5 on, or any address not in the data:
    name(); s.push(0x7FF5); s.emit(0x0e); s.jump_if_zero(named) #  taken as named)
    name(); s.emit(0x3f); s.jump_if_nonzero(named)              # (the name's first two letters: 0 for none)
    event_set(s, number, EVENT_ICON, lambda: s.push(NO_BADGE))
    s.label(named)


def schedule_calendar(rewriter, pc, argc, context):
    """33 with the calendar: (script, text, name, caption, month, day, minute, duration, icon, flag). The event joins the list.
    Returns its number (0 for no script, as BREW)."""
    def build(s):
        none, end = s.label(), s.label()
        s.arg(1); s.push(0); s.emit(0x0f); s.jump_if_nonzero(none)
        add_event(s, context, lambda: s.arg(1), lambda: s.arg(7), lambda: s.arg(8), lambda: s.arg(9), lambda: s.arg(10),
                  lambda: s.arg(2), lambda: s.arg(3), lambda: push_day_index(s, context, lambda: s.arg(5), lambda: s.arg(6)))
        s.push(EVENTS_KEY); s.call(55, 1)                   # R: its number
        s.jump(end)
        s.label(none)
        s.result(0)
        s.label(end)
    rewriter.redirect(pc, ('schedule_calendar', context['rid']), build)


WEEKDAY_ABBREVIATIONS = ('su', 'mo', 'tu', 'we', 'th', 'fr', 'sa')


def weekday_mask(text):
    """The weekdays a 34 call names (`Mon|Wed|Fri`, by their first two letters, as brew-calendar.js `weekdaysBetween`), as bits."""
    mask = 0
    for part in text.replace(',', '|').split('|'):
        key = part.strip().lower()[:2]
        if key in WEEKDAY_ABBREVIATIONS:
            mask |= 1 << WEEKDAY_ABBREVIATIONS.index(key)
    return mask


def schedule_weekly(rewriter, pc, argc, context):
    """34: (script, text, name, caption, weekdays, month, day, to month, to day, minute, duration, icon, flag): an event on each of
    those weekdays from the one date to the other, as copies on the list (one a day; 35 sets a field on them all). Returns the
    first's number (0 for no script, as BREW). The weekdays are a constant the translator reads (CS Idol, Stage 5)."""
    if context['kind'] == 'season':
        return season_weekly(rewriter, pc, argc, context)
    program = context['program']
    values = newrules.pushed_values(program, rewriter.code_base + pc, argc)
    weekdays = values[4] if values and len(values) > 4 else None
    if isinstance(weekdays, int):                           # (a string's data address: CS Idol's `Mo,We,Fr` is at 65)
        weekdays = next((text for address, text, _ in data_strings(program) if address == weekdays), None)
    if not isinstance(weekdays, (bytes, str)):
        raise StoryError(f'34 at {pc}: its weekdays are not a constant')
    mask = weekday_mask(weekdays.decode('latin-1') if isinstance(weekdays, bytes) else weekdays)
    if context['kind'] != 'calendar':
        raise StoryError('34 schedules an event on several days, which needs the calendar driver')
    first, day = context['cal_t'] + 2, context['cal_best']        # (scratch: the first copy's number, and the day)

    def build(s):
        none, end, loop, next_day, done = s.label(), s.label(), s.label(), s.label(), s.label()
        s.arg(1); s.push(0); s.emit(0x0f); s.jump_if_nonzero(none)
        set_word(s, first, lambda: (get_global(s, EVENTS_KEY), s.push(1), s.emit(0x50)))
        set_word(s, day, lambda: push_day_index(s, context, lambda: s.arg(6), lambda: s.arg(7)))
        s.label(loop)
        s.emit(0x40, day); push_day_index(s, context, lambda: s.arg(8), lambda: s.arg(9)); s.emit(0x0f); s.jump_if_zero(done)
        # Bit `weekday` of the mask: the mask divided by 2 ** weekday, odd.
        power, shifted = s.label(), s.label()
        s.push(mask)
        set_word(s, context['cal_j'], lambda: push_weekday(s, lambda: s.emit(0x40, day)))
        s.label(power)
        s.emit(0x40, context['cal_j']); s.jump_if_zero(shifted)
        s.push(2); s.emit(0x53)
        set_word(s, context['cal_j'], lambda: (s.emit(0x40, context['cal_j']), s.push(1), s.emit(0x51)))
        s.jump(power)
        s.label(shifted)
        s.push(2); s.emit(0x54); s.jump_if_zero(next_day)
        add_event(s, context, lambda: s.arg(1), lambda: s.arg(10), lambda: s.arg(11), lambda: s.arg(12), lambda: s.arg(13),
                  lambda: s.arg(2), lambda: s.arg(3), lambda: s.emit(0x40, day))
        s.label(next_day)
        set_word(s, day, lambda: (s.emit(0x40, day), s.push(1), s.emit(0x50)))
        s.jump(loop)
        s.label(done)
        # The first copy keeps how many there are; with none, nothing was added and the answer is 0.
        nothing = s.label()
        get_global(s, EVENTS_KEY); s.emit(0x40, first); s.emit(0x0e); s.jump_if_nonzero(nothing)
        event_set(s, lambda: s.emit(0x40, first), EVENT_COPIES,
                  lambda: (get_global(s, EVENTS_KEY), s.emit(0x40, first), s.emit(0x51), s.push(1), s.emit(0x50)))
        set_global(s, WEEKLY_FIRST_KEY, lambda: s.emit(0x40, first))
        s.push(WEEKLY_FIRST_KEY); s.call(55, 1)             # R: the first copy's number
        s.jump(end)
        s.label(nothing)
        s.result(0)
        s.jump(end)
        s.label(none)
        s.result(0)
        s.label(end)
    rewriter.redirect(pc, ('schedule_weekly', context['rid'], pc), build)


def today_date(rewriter, pc, argc, context):
    """43: (month, date) addresses: today's month and date (42: the next school day's), as brew-calendar.js `dateOf`."""
    service = rewriter.code[pc][1] >> 8
    m, d = context['cal_t'], context['cal_t'] + 1

    def build(s):
        if service == 42:
            set_word(s, context['cal_best'], lambda: push_next_school_day(s, lambda: get_global(s, DAY_KEY)))
            date_of(s, context, lambda: s.emit(0x40, context['cal_best']))
        else:
            date_of(s, context, lambda: get_global(s, DAY_KEY))
        s.arg(1); s.emit(0x40, m); s.emit(0x3e); s.emit(0x15)
        s.arg(2); s.emit(0x40, d); s.emit(0x3e); s.emit(0x15)
        s.result(0)
    rewriter.redirect(pc, ('today_date', context['rid'], service), build)


def field_set_calendar(rewriter, pc, argc, context):
    """35 with the calendar: (event, field, value) on that event's own fields, which its script reads (8) when it runs."""
    def build(s):
        skip, each, done = s.label(), s.label(), s.label()
        s.arg(1); s.push(1); s.emit(0x0e); s.arg(2); s.push(0); s.emit(0x0e); s.emit(0x11)
        s.arg(2); s.push(15); s.emit(0x0c); s.emit(0x11); s.jump_if_nonzero(skip)
        # (A recurring event's copies (34) all take it: copies 0 to EVENT_COPIES - 1 after the one named.)
        s.push(0)                                           # local 0: the copy
        s.label(each)
        s.emit(0x41, 0); event_get(s, lambda: s.arg(1), EVENT_COPIES); s.emit(0x0e); s.jump_if_zero(done)
        event_key(s, lambda: (s.arg(1), s.emit(0x41, 0), s.emit(0x50)), EVENT_FIELDS); s.arg(2); s.emit(0x50); s.arg(3)
        s.call(54, 2)
        s.emit(0x23, 0); s.emit(0x41, 0); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.jump(each)
        s.label(done)
        s.label(skip)
        s.result(0)
    rewriter.redirect(pc, 'field_set_calendar', build)


def push_badge_time(s):
    """Push the running event's planner slot (BADGE_TIME_KEY) as BADGE_TIME_FORMAT's four values: hour (1-12), the minutes' two
    digits, and `AM` or `PM`."""
    minute = lambda: get_global(s, BADGE_TIME_KEY)
    minute(); s.push(60); s.emit(0x53); s.push(11); s.emit(0x50); s.push(12); s.emit(0x54); s.push(1); s.emit(0x50)
    minute(); s.push(60); s.emit(0x54); s.push(10); s.emit(0x53)
    minute(); s.push(10); s.emit(0x54)
    pm, done = s.label(), s.label()
    minute(); s.push(720); s.emit(0x0e); s.jump_if_zero(pm)
    s.text('AM'); s.jump(done)
    s.label(pm)
    s.text('PM')
    s.label(done)


def calendar_step(s, context, title_card, end_story, date_card):
    """The story script's prologue with the calendar: close the timed event that just ran, pick the next by BREW's rule, queue this
    script again behind it, and run it (its fields as the registers 8 reads, its text as 7's), under the title card the first
    time and its name's badge after. With nothing left, the story ends (each Classic story ends itself with 70 first)."""
    j, best, slot_end = context['cal_j'], context['cal_best'], context['cal_slot']
    J = lambda: s.emit(0x40, j)
    B = lambda: s.emit(0x40, best)
    count = lambda: get_global(s, EVENTS_KEY)
    now = lambda: get_global(s, CLOCK_KEY)

    def each(body):
        """for j in 1..count: body() (which may jump out)."""
        top, done = s.label(), s.label()
        set_word(s, j, lambda: s.push(1))
        s.label(top)
        J(); count(); s.emit(0x0f); s.jump_if_zero(done)
        body()
        set_word(s, j, lambda: (J(), s.push(1), s.emit(0x50)))
        s.jump(top)
        s.label(done)

    def larger(a, b):
        """Push the larger of two pushed values (callables)."""
        first, end = s.label(), s.label()
        a(); b(); s.emit(0x0d); s.jump_if_nonzero(first)
        b(); s.jump(end)
        s.label(first)
        a()
        s.label(end)

    loop, run, over, timed_done = s.label(), s.label(), s.label(), s.label()
    # finish(): the timed event that ran. Untimed events inside its span become due; the clock moves past its end.
    get_global(s, TIMED_KEY); s.jump_if_zero(timed_done)
    T = lambda: get_global(s, TIMED_KEY)
    span_end = lambda: (event_get(s, T, EVENT_MINUTE), larger(lambda: event_get(s, T, EVENT_DURATION), lambda: s.push(0)),
                        s.emit(0x50), s.push(1), s.emit(0x51))

    def inside():
        skip = s.label()
        event_get(s, J, EVENT_STATE); s.push(WAITING); s.emit(0x0b); s.jump_if_nonzero(skip)
        event_get(s, J, EVENT_DAY); get_global(s, DAY_KEY); s.emit(0x0b); s.jump_if_nonzero(skip)
        event_get(s, J, EVENT_DURATION); s.push(0); s.emit(0x0d); s.jump_if_nonzero(skip)
        event_get(s, J, EVENT_MINUTE); event_get(s, T, EVENT_MINUTE); s.emit(0x0f); s.jump_if_nonzero(skip)
        event_get(s, J, EVENT_MINUTE); span_end(); s.emit(0x0c); s.jump_if_nonzero(skip)
        event_set(s, J, EVENT_STATE, lambda: s.push(PENDING))
        s.label(skip)
    each(inside)
    set_global(s, CLOCK_KEY, lambda: larger(now, lambda: larger(lambda: (span_end(), s.push(1), s.emit(0x50)),
                                                                lambda: (event_get(s, T, EVENT_MINUTE), s.push(1), s.emit(0x50)))))
    set_global(s, TIMED_KEY, lambda: s.push(0))
    s.label(timed_done)
    s.label(loop)

    # An event already due runs first, in the order they were scheduled.
    def pending():
        skip = s.label()
        event_get(s, J, EVENT_STATE); s.push(PENDING); s.emit(0x0b); s.jump_if_nonzero(skip)
        set_word(s, best, J); s.jump(run)
        s.label(skip)
    each(pending)
    get_global(s, DAY_KEY); s.push(0); s.emit(0x0e); s.jump_if_nonzero(over)
    # Past the day's end: the next school day, or none (brew-calendar.js `advanceTo`).
    today = s.label()
    now(); get_global(s, DAY_END_KEY); s.emit(0x0f); s.jump_if_nonzero(today)
    set_word(s, slot_end, lambda: push_next_school_day(s, lambda: get_global(s, DAY_KEY)))
    finished = s.label()
    s.emit(0x40, slot_end); s.push(0); s.emit(0x0e); s.emit(0x40, slot_end); get_global(s, LAST_DAY_KEY); s.emit(0x0c); s.emit(0x11)
    s.jump_if_nonzero(finished)
    set_global(s, DAY_KEY, lambda: s.emit(0x40, slot_end))
    set_global(s, CLOCK_KEY, lambda: get_global(s, DAY_START_KEY))
    s.jump(loop)
    s.label(finished)
    set_global(s, DAY_KEY, lambda: s.push(-1))
    s.jump(loop)
    s.label(today)
    # Anything left, today or after?
    set_word(s, best, lambda: s.push(0))

    def left():
        skip, take = s.label(), s.label()
        event_get(s, J, EVENT_STATE); s.push(WAITING); s.emit(0x0b); s.jump_if_nonzero(skip)
        event_get(s, J, EVENT_DAY); get_global(s, DAY_KEY); s.emit(0x0c); s.jump_if_nonzero(take)
        event_get(s, J, EVENT_DAY); get_global(s, DAY_KEY); s.emit(0x0b); s.jump_if_nonzero(skip)
        event_get(s, J, EVENT_MINUTE); now(); s.emit(0x0e); s.jump_if_nonzero(skip)
        s.label(take)
        set_word(s, best, lambda: s.push(1))
        s.label(skip)
    each(left)
    B(); s.jump_if_zero(over)
    # This half hour's events: the timed one (a flagged one first) runs; with none, the rest are due and the clock moves on.
    set_word(s, slot_end, lambda: (now(), s.push(SLOT_MINUTES), s.emit(0x53), s.push(SLOT_MINUTES), s.emit(0x52),
                                   s.push(SLOT_MINUTES - 1), s.emit(0x50)))
    capped = s.label()
    s.emit(0x40, slot_end); s.push(DAY_MINUTES); s.emit(0x0f); s.jump_if_nonzero(capped)
    set_word(s, slot_end, lambda: s.push(DAY_MINUTES))
    s.label(capped)
    set_word(s, best, lambda: s.push(0))
    in_slot = lambda skip: (event_get(s, J, EVENT_STATE), s.push(WAITING), s.emit(0x0b), s.jump_if_nonzero(skip),
                            event_get(s, J, EVENT_DAY), get_global(s, DAY_KEY), s.emit(0x0b), s.jump_if_nonzero(skip),
                            event_get(s, J, EVENT_MINUTE), now(), s.emit(0x0e), s.jump_if_nonzero(skip),
                            event_get(s, J, EVENT_MINUTE), s.emit(0x40, slot_end), s.emit(0x0c), s.jump_if_nonzero(skip))

    def timed():
        skip, take = s.label(), s.label()
        in_slot(skip)
        event_get(s, J, EVENT_DURATION); s.push(0); s.emit(0x0e); s.jump_if_nonzero(skip)
        B(); s.jump_if_zero(take)
        event_get(s, J, EVENT_FLAG); s.jump_if_zero(skip)
        event_get(s, B, EVENT_FLAG); s.jump_if_nonzero(skip)
        s.label(take)
        set_word(s, best, J)
        s.label(skip)
    each(timed)
    untimed = s.label()
    B(); s.jump_if_zero(untimed)
    set_global(s, CLOCK_KEY, lambda: larger(now, lambda: event_get(s, B, EVENT_MINUTE)))
    set_global(s, TIMED_KEY, B)
    s.jump(run)
    s.label(untimed)

    def due():
        skip = s.label()
        in_slot(skip)
        event_set(s, J, EVENT_STATE, lambda: s.push(PENDING))
        s.label(skip)
    each(due)
    set_global(s, CLOCK_KEY, lambda: (s.emit(0x40, slot_end), s.push(1), s.emit(0x50)))
    s.jump(loop)

    s.label(over)
    end_story()
    s.label(run)
    run_event(s, context, B, title_card, date_card, STORY_SCRIPT)


def run_event(s, context, B, title_card, date_card, driver):
    """Run event B (a callable pushing its number): its fields become the registers 8 reads, its text 7's; the driver's script
    (`driver`) is queued to come back after it, then the event's own script, unless that is the driver's (a Classic story's
    events run on in its story script). The first event comes under the title card, a new day's under its card, and each
    with its badge."""
    event_set(s, B, EVENT_STATE, lambda: s.push(DONE))
    set_global(s, ACTIVE_KEY, B)
    for field in range(16):
        set_global(s, FIELD_KEY + field, lambda field=field: event_get(s, B, EVENT_FIELDS + field))
    keyed_text(s, EVENT_TEXT_KEY, B, context['key_buffer'])
    s.text(EVENT_TEXT); s.push(context['key_buffer']); s.text(''); s.push(-1); s.call(47, 3); s.push_result(); s.call(46, 2)
    s.push(driver); s.push(0); s.call(10, 2)
    badge, icon, chosen, started = s.label(), s.label(), s.label(), s.label()
    set_global(s, BADGE_TIME_KEY, lambda: (event_get(s, B, EVENT_MINUTE), s.push(SLOT_MINUTES), s.emit(0x53), s.push(SLOT_MINUTES),
                                           s.emit(0x52)))
    # The event's badge icon (an icon outside BREW's own small pictures, as CS Idol's 26501, one of its registered pictures, or none,
    # takes NO_ICON_BADGE), kept for a date caption its script shows (date_caption).
    for n, picture in enumerate(sorted(OWN_CATCH_PICTURES)):
        if picture not in context.get('own_missing', set(OWN_CATCH_PICTURES)):
            not_own = s.label()
            event_get(s, B, EVENT_ICON); s.push(picture); s.emit(0x0a); s.jump_if_zero(not_own)
            set_global(s, BADGE_ICON_KEY, lambda n=n: s.push(OWN_ICON_BASE + n)); s.jump(chosen)
            s.label(not_own)
    event_get(s, B, EVENT_ICON); s.push(EVENT_ICONS.start); s.emit(0x0e)
    event_get(s, B, EVENT_ICON); s.push(EVENT_ICONS.stop); s.emit(0x0d); s.emit(0x11); s.jump_if_zero(icon)
    set_global(s, BADGE_ICON_KEY, lambda: s.push(EVENT_ICON_BASE + NO_ICON_BADGE)); s.jump(chosen)
    s.label(icon)
    set_global(s, BADGE_ICON_KEY, lambda: (event_get(s, B, EVENT_ICON), s.push(EVENT_ICON_BASE), s.emit(0x50)))
    s.label(chosen)
    get_global(s, STARTED_KEY); s.jump_if_nonzero(badge)
    set_global(s, STARTED_KEY, lambda: s.push(1))
    set_global(s, SHOWN_DAY_KEY, lambda: get_global(s, DAY_KEY))
    title_card()
    s.jump(started)
    s.label(badge)
    # Every event after the first (which the title card opens) starts with its opener (dots), badge or not.
    set_global(s, OPENER_KEY, lambda: s.push(1))
    # A new date: its card first (decision 3), as Battle of the Schools' week cards.
    same_day = s.label()
    get_global(s, DAY_KEY); get_global(s, SHOWN_DAY_KEY); s.emit(0x0a); s.jump_if_nonzero(same_day)
    set_global(s, SHOWN_DAY_KEY, lambda: get_global(s, DAY_KEY))
    write_date(s, context, lambda: get_global(s, DAY_KEY))
    date_card()
    s.label(same_day)
    named, shown = s.label(), s.label()
    event_get(s, B, EVENT_ICON); s.push(NO_BADGE); s.emit(0x0a); s.jump_if_zero(named)
    # An event with no name (CS Idol's lunchtimes, Rock Band Pt 1's `After school.`; BREW's planner has no row for them) shows just
    # its time, `12:00 PM`, under the location badge (owner, 2026-11-07, to be looked at in the badge review); unless a badge is
    # still up that no message has shown yet (CS Idol's `9:00 AM - School`, which comes with lunch's first line), which stays.
    get_global(s, BADGE_UP_KEY); s.jump_if_nonzero(started)
    s.push(context['badge_buffer']); s.text(BADGE_TIME_FORMAT[:-len(' - ')])
    push_badge_time(s)
    s.call(22, 6)
    s.jump(shown)
    s.label(named)
    # `3:00 PM - Practice`: the time the planner jumps to, then the event's name (owner, 2026-11-07).
    s.push(context['badge_buffer']); s.text(BADGE_TIME_FORMAT + '%s')
    push_badge_time(s)
    keyed_text(s, EVENT_NAME_KEY, B, context['key_buffer'])
    s.push(context['key_buffer']); s.text(''); s.push(-1); s.call(47, 3); s.push_result()
    s.call(22, 7)
    s.label(shown)
    get_global(s, BADGE_ICON_KEY); s.push(context['badge_buffer']); s.call(90, 2)
    set_global(s, BADGE_UP_KEY, lambda: s.push(1))
    s.label(started)
    own = s.label()
    event_get(s, B, EVENT_SCRIPT); s.push(driver); s.emit(0x0a); s.jump_if_nonzero(own)
    event_get(s, B, EVENT_SCRIPT); s.jump_if_zero(own)        # (0: an event scheduled before Stage 5's script numbers)
    event_get(s, B, EVENT_SCRIPT); s.push(0); s.call(10, 2)
    s.emit(0x33)
    s.label(own)


# -- the season driver (Fall '06, Stage 6) ---------------------------------------------------------------------------------------
def season_words(rewriter):
    """Scratch words for the season driver and its services."""
    return dict(season=rewriter.words([0] * 16))


def sw(context, i):
    """Scratch word i of the season driver's (season_words)."""
    return context['season'] + i


def day_key(s, day, entry=None):
    """Push day `day`'s list count key, or with `entry` (a callable, from 0) that entry's."""
    s.push(DAY_LISTS); day(); s.push(DAY_SLOTS); s.emit(0x52); s.emit(0x50)
    if entry is not None:
        entry(); s.emit(0x50); s.push(1); s.emit(0x50)


def day_count(s, day):
    day_key(s, day); s.call(55, 1); s.push_result()


def each_day_entry(s, context, day, body):
    """for each event on day `day` (a callable), in the order they were put there: body(), with the event's number in scratch
    word 1 (body may jump out). Uses scratch words 0 and 1."""
    k, ent = sw(context, 0), sw(context, 1)
    top, done = s.label(), s.label()
    set_word(s, k, lambda: s.push(0))
    s.label(top)
    s.emit(0x40, k); day_count(s, day); s.emit(0x0e); s.jump_if_zero(done)
    set_word(s, ent, lambda: (day_key(s, day, lambda: s.emit(0x40, k)), s.call(55, 1), s.push_result()))
    body()
    set_word(s, k, lambda: (s.emit(0x40, k), s.push(1), s.emit(0x50)))
    s.jump(top)
    s.label(done)


def day_add(s, context, day, number):
    """Put event `number` on day `day`'s list (callables; days outside the season's are left off, as brew-calendar.js never
    reaches them)."""
    skip, later = s.label(), s.label()
    D = lambda: s.emit(0x40, sw(context, 12))
    set_word(s, sw(context, 12), day)
    D(); s.push(0); s.emit(0x0e); D(); s.push(SEASON_MOST_DAYS); s.emit(0x0d); s.emit(0x11); s.jump_if_nonzero(skip)
    day_count(s, D); s.push(DAY_SLOTS - 1); s.emit(0x0d); s.jump_if_nonzero(skip)
    day_key(s, D, lambda: day_count(s, D)); number(); s.call(54, 2)
    day_key(s, D); day_count(s, D); s.push(1); s.emit(0x50); s.call(54, 2)
    D(); get_global(s, LAST_ENTRY_DAY_KEY); s.emit(0x0f); s.jump_if_nonzero(later)
    set_global(s, LAST_ENTRY_DAY_KEY, D)
    s.label(later)
    s.label(skip)


def pending_push(s, number, queue=PENDING_LIST):
    """Event `number` joins the due list (brew-calendar.js `pending`), or another list (`queue`: its count, then its events)."""
    full = s.label()
    get_global(s, queue); s.push(PENDING_SLOTS - 1); s.emit(0x0d); s.jump_if_nonzero(full)
    s.push(queue + 1); get_global(s, queue); s.emit(0x50); number(); s.call(54, 2)
    set_global(s, queue, lambda: (get_global(s, queue), s.push(1), s.emit(0x50)))
    s.label(full)


def pending_shift(s, context, into, queue=PENDING_LIST):
    """The first due event (or `queue`'s) into word `into`, the rest moved up."""
    i = sw(context, 13)
    top, done = s.label(), s.label()
    set_word(s, into, lambda: get_global(s, queue + 1))
    set_word(s, i, lambda: s.push(1))
    s.label(top)
    s.emit(0x40, i); get_global(s, queue); s.emit(0x0e); s.jump_if_zero(done)
    s.push(queue); s.emit(0x40, i); s.emit(0x50)
    s.push(queue + 1); s.emit(0x40, i); s.emit(0x50); s.call(55, 1); s.push_result()
    s.call(54, 2)
    set_word(s, i, lambda: (s.emit(0x40, i), s.push(1), s.emit(0x50)))
    s.jump(top)
    s.label(done)
    set_global(s, queue, lambda: (get_global(s, queue), s.push(1), s.emit(0x51)))


def nested_check(s):
    """With events on the nested list, run them now (the nest runner, through service 223), then go on. Not inside a nested event:
    the native engine runs them in a slot of their own, one after another, each to its end (FUN_0000af08, FUN_0000c09c), so a
    nested event's waits don't start the next (Tardy-Slip's `runNested` does)."""
    none = s.label()
    get_global(s, NESTED_LIST); s.jump_if_zero(none)
    get_global(s, NEST_DEPTH_KEY); s.jump_if_nonzero(none)
    s.push(NEST_SCRIPT); s.call(NESTED_SCRIPT_SERVICE, 1)
    s.label(none)


def nest_runner(s, context):
    """The nest runner's script (NEST_SCRIPT): story.js `runNested`. Each event on the nested list, in order, runs its script to its
    end inside the waiting one (events it fires join the list and run after it): the registers (FIELD_KEY) and event text are kept by depth and the event's own set, then put back. The current
    timed event stays the one that was running."""
    ent, depth = sw(context, 1), sw(context, 2)
    E = lambda: s.emit(0x40, ent)
    top, done = s.label(), s.label()
    set_global(s, NEST_DEPTH_KEY, lambda: (get_global(s, NEST_DEPTH_KEY), s.push(1), s.emit(0x50)))
    set_word(s, depth, lambda: get_global(s, NEST_DEPTH_KEY))
    s.label(top)
    get_global(s, NESTED_LIST); s.jump_if_zero(done)
    pending_shift(s, context, ent, NESTED_LIST)
    save = lambda field: (s.push(NEST_SAVES), s.emit(0x40, depth), s.push(20), s.emit(0x52), s.emit(0x50), s.push(field), s.emit(0x50))
    for field in range(16):
        save(field); get_global(s, FIELD_KEY + field); s.call(54, 2)
        set_global(s, FIELD_KEY + field, lambda field=field: event_get(s, E, EVENT_FIELDS + field))
    keyed_text(s, '$BREWNEST%d', lambda: s.emit(0x40, depth), context['key_buffer'])
    s.push(context['key_buffer']); s.text(EVENT_TEXT); s.text(''); s.push(-1); s.call(47, 3); s.push_result(); s.call(46, 2)
    keyed_text(s, EVENT_TEXT_KEY, E, context['key_buffer'])
    s.text(EVENT_TEXT); s.push(context['key_buffer']); s.text(''); s.push(-1); s.call(47, 3); s.push_result(); s.call(46, 2)
    event_get(s, E, EVENT_SCRIPT); s.call(NESTED_SCRIPT_SERVICE, 1)
    for field in range(16):
        set_global(s, FIELD_KEY + field, lambda field=field: (save(field), s.call(55, 1), s.push_result()))
    keyed_text(s, '$BREWNEST%d', lambda: s.emit(0x40, depth), context['key_buffer'])
    s.text(EVENT_TEXT); s.push(context['key_buffer']); s.text(''); s.push(-1); s.call(47, 3); s.push_result(); s.call(46, 2)
    s.jump(top)
    s.label(done)
    set_global(s, NEST_DEPTH_KEY, lambda: (get_global(s, NEST_DEPTH_KEY), s.push(1), s.emit(0x51)))


def push_larger(s, a, b):
    """Push the larger of two values (callables)."""
    first, end = s.label(), s.label()
    a(); b(); s.emit(0x0d); s.jump_if_nonzero(first)
    b(); s.jump(end)
    s.label(first)
    a()
    s.label(end)


def advance_to(s, context, t):
    """brew-calendar.js `advanceTo`: the clock moves on to `t` (a callable) if that's later; past the day's end, the next school day
    at its start, or none (day -1) after the last."""
    T, N = sw(context, 10), sw(context, 11)
    later, done, finished = s.label(), s.label(), s.label()
    set_word(s, T, t)
    s.emit(0x40, T); get_global(s, CLOCK_KEY); s.emit(0x0c); s.jump_if_zero(later)
    set_global(s, CLOCK_KEY, lambda: s.emit(0x40, T))
    s.label(later)
    get_global(s, CLOCK_KEY); get_global(s, DAY_END_KEY); s.emit(0x0f); s.jump_if_nonzero(done)
    set_word(s, N, lambda: push_next_school_day(s, lambda: get_global(s, DAY_KEY)))
    s.emit(0x40, N); s.push(0); s.emit(0x0e); s.emit(0x40, N); get_global(s, LAST_DAY_KEY); s.emit(0x0c); s.emit(0x11)
    s.jump_if_nonzero(finished)
    set_global(s, DAY_KEY, lambda: s.emit(0x40, N))
    set_global(s, CLOCK_KEY, lambda: get_global(s, DAY_START_KEY))
    set_global(s, CHECKED_KEY, lambda: (get_global(s, DAY_START_KEY), s.push(1), s.emit(0x51)))
    s.jump(done)
    s.label(finished)
    set_global(s, DAY_KEY, lambda: s.push(-1))
    s.label(done)


def push_school_weekday(s, day):
    """Push day `day`'s weekday counted from Monday (0 Monday, 6 Sunday)."""
    push_weekday(s, day); s.push(6); s.emit(0x50); s.push(7); s.emit(0x54)


def push_week(s, day):
    """Push the season's week number (from 1) of day `day` (a callable): weeks run Monday to Sunday, the first from the calendar's
    first day."""
    day(); push_school_weekday(s, day); s.emit(0x51)
    push_school_weekday(s, lambda: s.push(0)); s.emit(0x50)
    s.push(7); s.emit(0x53); s.push(1); s.emit(0x50)


def week_card(s, context, card):
    """A new week's card, when today is in a week not shown yet: `Week 1 of 13` over the dates of its school days, Monday (or the
    calendar's first day) to Friday (or its last)."""
    first, last, first_month, first_date, week = (context['week_words'] + n for n in range(5))
    m, d = context['cal_t'], context['cal_t'] + 1
    W = lambda word: (lambda: s.emit(0x40, word))
    today = lambda: get_global(s, DAY_KEY)
    shown = s.label()
    set_word(s, week, lambda: push_week(s, today))
    s.emit(0x40, week); get_global(s, SHOWN_WEEK_KEY); s.emit(0x0a); s.jump_if_nonzero(shown)
    set_global(s, SHOWN_WEEK_KEY, W(week))
    set_word(s, first, lambda: (today(), push_school_weekday(s, today), s.emit(0x51)))
    set_word(s, last, lambda: (s.emit(0x40, first), s.push(4), s.emit(0x50)))
    on, within = s.label(), s.label()
    s.emit(0x40, first); s.push(0); s.emit(0x0e); s.jump_if_zero(on)
    set_word(s, first, lambda: s.push(0))
    s.label(on)
    s.emit(0x40, last); get_global(s, LAST_DAY_KEY); s.emit(0x0d); s.jump_if_zero(within)
    set_word(s, last, lambda: get_global(s, LAST_DAY_KEY))
    s.label(within)
    date_of(s, context, W(first))
    set_word(s, first_month, W(m))
    set_word(s, first_date, W(d))
    date_of(s, context, W(last))
    month = lambda word: (s.push(context['month_names']), s.emit(0x40, word), s.push(1), s.emit(0x51), s.emit(0x50), s.emit(0x3f))
    months, written, one_day = s.label(), s.label(), s.label()
    s.emit(0x40, first_month); s.emit(0x40, m); s.emit(0x0a); s.jump_if_zero(months)
    s.emit(0x40, first_date); s.emit(0x40, d); s.emit(0x0a); s.jump_if_nonzero(one_day)
    s.push(context['date_range_buffer']); s.text(WEEK_RANGE); month(first_month); s.emit(0x40, first_date); s.emit(0x40, d)
    s.call(22, 5); s.jump(written)
    s.label(one_day)
    s.push(context['date_range_buffer']); s.text(WEEK_ONE_DAY); month(first_month); s.emit(0x40, first_date)
    s.call(22, 4); s.jump(written)
    s.label(months)
    s.push(context['date_range_buffer']); s.text(WEEK_RANGE_MONTHS); month(first_month); s.emit(0x40, first_date); month(m)
    s.emit(0x40, d)
    s.call(22, 6)
    s.label(written)
    s.push(context['week_buffer']); s.text(WEEK_TITLE); s.emit(0x40, week); push_week(s, lambda: get_global(s, LAST_DAY_KEY))
    s.call(22, 4)
    s.push(context['week_buffer']); s.push(context['date_range_buffer']); s.push(card); s.push(0); s.call(8, 4)
    s.label(shown)


def day_line(s, context):
    """Today's narration line, `Monday, September 13.`, from the date (write_date) in the date buffer."""
    s.push(context['day_line_buffer']); s.text(DAY_LINE); s.push(context['date_buffer']); s.call(22, 3)
    s.push(context['day_line_buffer']); s.push(NARRATOR); s.call(13, 2)


def season_step(s, context, title_card, end_story, date_card):
    """The season driver's script (DRIVER_SCRIPT): brew-calendar.js `finish` then `step`, until an event runs (run_event) or the
    calendar is over. Events due with no time of their own run first, in order; then this half hour's timed event (a flagged one
    first) runs; with none, the half hour's untimed events become due and the clock moves on. A half hour with nothing on is passed
    straight to the next that has something, which ends where stepping through each would."""
    ent, best, slot, cur, end, anything, nxt, target = (sw(context, i) for i in (1, 2, 3, 8, 9, 7, 5, 6))
    E, B, C = (lambda: s.emit(0x40, ent)), (lambda: s.emit(0x40, best)), (lambda: s.emit(0x40, cur))
    today = lambda: get_global(s, DAY_KEY)
    clock = lambda: get_global(s, CLOCK_KEY)
    loop, run, over = s.label(), s.label(), s.label()
    # A script has just ended: events on the nested list run first, as story.js runs them before its next event.
    nested_check(s)
    # finish(): the timed event that ran. Untimed events inside its span become due; the clock moves past its end.
    no_current, not_later = s.label(), s.label()
    get_global(s, CURRENT_KEY); s.jump_if_zero(no_current)
    set_word(s, cur, lambda: get_global(s, CURRENT_KEY))
    set_global(s, CURRENT_KEY, lambda: s.push(0))
    today(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(no_current)
    set_word(s, end, lambda: (event_get(s, C, EVENT_MINUTE), push_larger(s, lambda: event_get(s, C, EVENT_DURATION), lambda: s.push(0)),
                              s.emit(0x50), s.push(1), s.emit(0x51)))
    s.emit(0x40, end); get_global(s, CHECKED_KEY); s.emit(0x0c); s.jump_if_zero(not_later)

    def inside():
        skip = s.label()
        event_get(s, E, EVENT_MINUTE); get_global(s, CHECKED_KEY); s.emit(0x0f); s.jump_if_nonzero(skip)
        event_get(s, E, EVENT_MINUTE); s.emit(0x40, end); s.emit(0x0c); s.jump_if_nonzero(skip)
        event_get(s, E, EVENT_DURATION); s.push(0); s.emit(0x0e); s.jump_if_zero(skip)
        pending_push(s, E)
        s.label(skip)
    each_day_entry(s, context, today, inside)
    set_global(s, CHECKED_KEY, lambda: s.emit(0x40, end))
    s.label(not_later)
    advance_to(s, context, lambda: push_larger(s, clock, lambda: push_larger(s, lambda: (s.emit(0x40, end), s.push(1), s.emit(0x50)),
                                                                               lambda: (event_get(s, C, EVENT_MINUTE), s.push(1), s.emit(0x50)))))
    s.label(no_current)

    s.label(loop)
    none_due = s.label()
    get_global(s, PENDING_LIST); s.jump_if_zero(none_due)
    pending_shift(s, context, best)
    s.jump(run)
    s.label(none_due)
    today(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(over)
    # Anything left, today or after?
    left = s.label()
    get_global(s, LAST_ENTRY_DAY_KEY); today(); s.emit(0x0c); s.jump_if_nonzero(left)

    def later_today():
        skip = s.label()
        event_get(s, E, EVENT_MINUTE); clock(); s.emit(0x0e); s.jump_if_nonzero(skip)
        s.jump(left)
        s.label(skip)
    each_day_entry(s, context, today, later_today)
    s.jump(over)
    s.label(left)
    # This half hour.
    capped = s.label()
    set_word(s, slot, lambda: (clock(), s.push(SLOT_MINUTES), s.emit(0x53), s.push(SLOT_MINUTES), s.emit(0x52),
                               s.push(SLOT_MINUTES - 1), s.emit(0x50)))
    s.emit(0x40, slot); s.push(DAY_MINUTES); s.emit(0x0f); s.jump_if_nonzero(capped)
    set_word(s, slot, lambda: s.push(DAY_MINUTES))
    s.label(capped)
    in_slot = lambda skip: (event_get(s, E, EVENT_MINUTE), clock(), s.emit(0x0e), s.jump_if_nonzero(skip),
                            event_get(s, E, EVENT_MINUTE), s.emit(0x40, slot), s.emit(0x0c), s.jump_if_nonzero(skip))
    set_word(s, best, lambda: s.push(0))

    def timed():
        skip, take = s.label(), s.label()
        in_slot(skip)
        event_get(s, E, EVENT_DURATION); s.push(0); s.emit(0x0e); s.jump_if_nonzero(skip)
        B(); s.jump_if_zero(take)
        event_get(s, E, EVENT_FLAG); s.jump_if_zero(skip)
        event_get(s, B, EVENT_FLAG); s.jump_if_nonzero(skip)
        s.label(take)
        set_word(s, best, E)
        s.label(skip)
    each_day_entry(s, context, today, timed)
    untimed = s.label()
    B(); s.jump_if_zero(untimed)
    set_global(s, CLOCK_KEY, lambda: push_larger(s, clock, lambda: event_get(s, B, EVENT_MINUTE)))
    set_global(s, CHECKED_KEY, clock)
    set_global(s, CURRENT_KEY, B)
    s.jump(run)
    s.label(untimed)
    set_word(s, anything, lambda: s.push(0))

    def due():
        skip = s.label()
        in_slot(skip)
        pending_push(s, E)
        set_word(s, anything, lambda: s.push(1))
        s.label(skip)
    each_day_entry(s, context, today, due)
    set_global(s, CHECKED_KEY, lambda: push_larger(s, lambda: get_global(s, CHECKED_KEY), lambda: s.emit(0x40, slot)))
    idle = s.label()
    s.emit(0x40, anything); s.jump_if_zero(idle)
    advance_to(s, context, lambda: (s.emit(0x40, slot), s.push(1), s.emit(0x50)))
    s.jump(loop)
    s.label(idle)
    # Nothing this half hour: on to the next half hour today that has something, or past the day's end.
    set_word(s, nxt, lambda: s.push(32767))

    def after():
        skip = s.label()
        event_get(s, E, EVENT_MINUTE); s.emit(0x40, slot); s.emit(0x0f); s.jump_if_nonzero(skip)
        event_get(s, E, EVENT_MINUTE); s.emit(0x40, nxt); s.emit(0x0d); s.jump_if_nonzero(skip)
        set_word(s, nxt, lambda: event_get(s, E, EVENT_MINUTE))
        s.label(skip)
    each_day_entry(s, context, today, after)
    next_day = s.label()
    s.emit(0x40, nxt); s.push(32767); s.emit(0x0a); s.jump_if_nonzero(next_day)
    set_word(s, target, lambda: (s.emit(0x40, nxt), s.push(SLOT_MINUTES), s.emit(0x53), s.push(SLOT_MINUTES), s.emit(0x52)))
    s.emit(0x40, target); get_global(s, DAY_END_KEY); s.emit(0x0c); s.jump_if_nonzero(next_day)
    set_global(s, CHECKED_KEY, lambda: push_larger(s, lambda: get_global(s, CHECKED_KEY), lambda: (s.emit(0x40, target), s.push(1), s.emit(0x51))))
    advance_to(s, context, lambda: s.emit(0x40, target))
    s.jump(loop)
    s.label(next_day)
    advance_to(s, context, lambda: push_larger(s, lambda: (s.emit(0x40, slot), s.push(1), s.emit(0x50)),
                                               lambda: (get_global(s, DAY_END_KEY), s.push(1), s.emit(0x50))))
    s.jump(loop)
    s.label(over)
    end_story()
    s.label(run)
    run_event(s, context, B, title_card, date_card, DRIVER_SCRIPT)


def season_answer(s, value):
    """R = value (a callable): through RESULT_KEY, as a shim can only set a constant otherwise."""
    set_global(s, RESULT_KEY, value)
    s.push(RESULT_KEY); s.call(55, 1)


def season_setup(rewriter, pc, argc, context):
    """69 in a season: as calendar_setup, and the season's own state: nothing checked, no current event, no day lists, nothing due."""
    def build(s):
        set_global(s, CLOCK_KEY, lambda: s.arg(1))
        set_global(s, DAY_START_KEY, lambda: s.arg(1))
        set_global(s, DAY_END_KEY, lambda: s.arg(2))
        set_global(s, START_MONTH_KEY, lambda: s.arg(3))
        set_global(s, START_DATE_KEY, lambda: s.arg(4))
        set_global(s, WEEKDAY_KEY, lambda: s.arg(5))
        set_global(s, LAST_DAY_KEY, lambda: push_day_index(s, context, lambda: s.arg(6), lambda: s.arg(7)))
        for key in (EVENTS_KEY, ACTIVE_KEY, STARTED_KEY, DAY_KEY, SHOWN_DAY_KEY, CURRENT_KEY, PENDING_LIST, NESTED_LIST, NEST_DEPTH_KEY,
                    SHOWN_WEEK_KEY):
            set_global(s, key, lambda: s.push(0))
        set_global(s, CHECKED_KEY, lambda: (s.arg(1), s.push(1), s.emit(0x51)))
        set_global(s, LAST_ENTRY_DAY_KEY, lambda: s.push(-1))
        d, top, done = sw(context, 14), s.label(), s.label()
        set_word(s, d, lambda: s.push(0))
        s.label(top)
        s.emit(0x40, d); s.push(SEASON_MOST_DAYS); s.emit(0x0e); s.jump_if_zero(done)
        day_key(s, lambda: s.emit(0x40, d)); s.push(0); s.call(54, 2)
        set_word(s, d, lambda: (s.emit(0x40, d), s.push(1), s.emit(0x50)))
        s.jump(top)
        s.label(done)
        s.result(0)
    rewriter.redirect(pc, ('season_setup', context['rid']), build)


def season_schedule(rewriter, pc, argc, context):
    """33 in a season: the event, once, on its day's list. Returns its number (0 for no script)."""
    def build(s):
        none, end = s.label(), s.label()
        s.arg(1); s.push(0); s.emit(0x0f); s.jump_if_nonzero(none)
        add_event(s, context, lambda: s.arg(1), lambda: s.arg(7), lambda: s.arg(8), lambda: s.arg(9), lambda: s.arg(10),
                  lambda: s.arg(2), lambda: s.arg(3), lambda: s.push(-1))
        day_add(s, context, lambda: push_day_index(s, context, lambda: s.arg(5), lambda: s.arg(6)), lambda: get_global(s, EVENTS_KEY))
        s.push(EVENTS_KEY); s.call(55, 1)
        s.jump(end)
        s.label(none)
        s.result(0)
        s.label(end)
    rewriter.redirect(pc, ('season_schedule', context['rid']), build)


def constant_text(rewriter, pc, argc, context, index, what):
    """A call's argument `index` (from 0) as a constant string (pushed directly, or by its data address)."""
    program = context['program']
    values = newrules.pushed_values(program, rewriter.code_base + pc, argc)
    value = values[index] if values and len(values) > index else None
    if isinstance(value, int):
        value = next((text for address, text, _ in data_strings(program) if address == value), None)
    if not isinstance(value, (bytes, str)) and what in ('34', '44'):
        # Fall '06's weekly calls build their other arguments from tables, which pushed_values can't follow; the weekdays are
        # still a string pushed for the call, the only one that names weekdays (`Mo,We,Fr`).
        strings = {address: text for address, text, _ in data_strings(program)}
        instructions = program.instructions
        k = next(n for n, i in enumerate(instructions) if i.pc == rewriter.code_base + pc)
        start = next((j + 1 for j in range(k - 1, -1, -1) if instructions[j].opcode == 0x1f), 0)
        names = {strings[i.operand] for i in instructions[start:k] if i.opcode == 0x1a and i.operand in strings
                 and is_weekday_list(strings[i.operand])}
        if len(names) == 1:
            value = names.pop()
    if not isinstance(value, (bytes, str)):
        raise StoryError(f'{what} at {pc}: not a constant')
    return value.decode('latin-1') if isinstance(value, bytes) else value


def is_weekday_list(text):
    """Whether a string is a list of weekdays (`Mo,We,Fr`, `Friday`)."""
    parts = [part.strip().lower() for part in text.decode('latin-1').replace(',', '|').split('|')]
    return bool(parts) and all(part[:2] in WEEKDAY_ABBREVIATIONS and WEEKDAYS[WEEKDAY_ABBREVIATIONS.index(part[:2])].lower()
                                .startswith(part) for part in parts)


def season_weekly(rewriter, pc, argc, context):
    """34 in a season: the event once, on each of the weekdays (a constant) from the one date to the other. Returns its number."""
    mask = weekday_mask(constant_text(rewriter, pc, argc, context, 4, '34'))

    def build(s):
        none, end, loop, next_day, done, power, shifted = (s.label() for _ in range(7))
        day, j = sw(context, 14), sw(context, 15)
        s.arg(1); s.push(0); s.emit(0x0f); s.jump_if_nonzero(none)
        add_event(s, context, lambda: s.arg(1), lambda: s.arg(10), lambda: s.arg(11), lambda: s.arg(12), lambda: s.arg(13),
                  lambda: s.arg(2), lambda: s.arg(3), lambda: s.push(-1))
        set_word(s, day, lambda: push_day_index(s, context, lambda: s.arg(6), lambda: s.arg(7)))
        s.label(loop)
        s.emit(0x40, day); push_day_index(s, context, lambda: s.arg(8), lambda: s.arg(9)); s.emit(0x0f); s.jump_if_zero(done)
        s.push(mask)
        set_word(s, j, lambda: push_weekday(s, lambda: s.emit(0x40, day)))
        s.label(power)
        s.emit(0x40, j); s.jump_if_zero(shifted)
        s.push(2); s.emit(0x53)
        set_word(s, j, lambda: (s.emit(0x40, j), s.push(1), s.emit(0x51)))
        s.jump(power)
        s.label(shifted)
        s.push(2); s.emit(0x54); s.jump_if_zero(next_day)
        day_add(s, context, lambda: s.emit(0x40, day), lambda: get_global(s, EVENTS_KEY))
        s.label(next_day)
        set_word(s, day, lambda: (s.emit(0x40, day), s.push(1), s.emit(0x50)))
        s.jump(loop)
        s.label(done)
        s.push(EVENTS_KEY); s.call(55, 1)
        s.jump(end)
        s.label(none)
        s.result(0)
        s.label(end)
    rewriter.redirect(pc, ('season_weekly', context['rid'], pc), build)


def season_field_set(rewriter, pc, argc, context):
    """35 in a season: (event, field, value) on the event, which every day it's on shares (brew-calendar.js keeps it once)."""
    def build(s):
        skip = s.label()
        s.arg(1); s.push(1); s.emit(0x0e); s.arg(2); s.push(0); s.emit(0x0e); s.emit(0x11)
        s.arg(2); s.push(15); s.emit(0x0c); s.emit(0x11); s.jump_if_nonzero(skip)
        event_key(s, lambda: s.arg(1), EVENT_FIELDS); s.arg(2); s.emit(0x50); s.arg(3); s.call(54, 2)
        s.label(skip)
        s.result(0)
    rewriter.redirect(pc, 'season_field_set', build)


def season_only(rewriter, pc, service, context):
    if context['kind'] != 'season':
        raise StoryError(f'service {service} at {pc} needs the season driver')


def unschedule(rewriter, pc, argc, context):
    """36: (name, month, day): the first event of that name off that day's list (brew-calendar.js `unscheduleByName`)."""
    season_only(rewriter, pc, 36, context)

    def build(s):
        ent, k = sw(context, 1), sw(context, 0)
        day, gone, done = sw(context, 14), s.label(), s.label()
        set_word(s, day, lambda: push_day_index(s, context, lambda: s.arg(2), lambda: s.arg(3)))
        D = lambda: s.emit(0x40, day)

        def same():
            skip = s.label()
            keyed_text(s, EVENT_NAME_KEY, lambda: s.emit(0x40, ent), context['key_buffer'])
            s.push(context['key_buffer']); s.text(''); s.push(-1); s.call(47, 3); s.push_result()
            s.arg(1); s.call(24, 2); s.push_result(); s.jump_if_zero(skip)
            s.jump(gone)
            s.label(skip)
        each_day_entry(s, context, D, same)
        s.jump(done)
        # Take entry k off: the ones after it move up.
        s.label(gone)
        top, moved = s.label(), s.label()
        s.label(top)
        s.emit(0x40, k); s.push(1); s.emit(0x50); day_count(s, D); s.emit(0x0e); s.jump_if_zero(moved)
        day_key(s, D, lambda: s.emit(0x40, k))
        day_key(s, D, lambda: (s.emit(0x40, k), s.push(1), s.emit(0x50))); s.call(55, 1); s.push_result()
        s.call(54, 2)
        set_word(s, k, lambda: (s.emit(0x40, k), s.push(1), s.emit(0x50)))
        s.jump(top)
        s.label(moved)
        day_key(s, D); day_count(s, D); s.push(1); s.emit(0x51); s.call(54, 2)
        s.label(done)
        s.result(0)
    rewriter.redirect(pc, ('unschedule', context['rid']), build)


def fire_due(rewriter, pc, argc, context):
    """37: the untimed events whose minute has come since the last check (brew-calendar.js `fireDue`), on the nested list: BREW
    runs them at the script's next wait (NEST_WAITS), or when it ends. As the native fire (FUN_00017c88): a window with any event
    in it starts the list afresh, and the check moves to now (capped at the day's end) even when nothing was due."""
    season_only(rewriter, pc, 37, context)

    def build(s):
        now, done, fresh = sw(context, 14), s.label(), sw(context, 15)
        E = lambda: s.emit(0x40, sw(context, 1))
        set_word(s, now, lambda: get_global(s, CLOCK_KEY))
        capped = s.label()
        s.emit(0x40, now); s.push(DAY_MINUTES); s.emit(0x0f); s.jump_if_nonzero(capped)
        set_word(s, now, lambda: s.push(DAY_MINUTES))
        s.label(capped)
        get_global(s, DAY_KEY); s.push(0); s.emit(0x0e); s.jump_if_nonzero(done)
        checked = s.label()
        s.emit(0x40, now); get_global(s, CHECKED_KEY); s.emit(0x0f); s.jump_if_nonzero(checked)
        set_word(s, fresh, lambda: s.push(1))

        def due():
            skip, kept = s.label(), s.label()
            event_get(s, E, EVENT_MINUTE); get_global(s, CHECKED_KEY); s.emit(0x0f); s.jump_if_nonzero(skip)
            event_get(s, E, EVENT_MINUTE); s.emit(0x40, now); s.emit(0x0c); s.jump_if_nonzero(skip)
            s.emit(0x40, fresh); s.jump_if_zero(kept)
            set_global(s, NESTED_LIST, lambda: s.push(0))
            set_word(s, fresh, lambda: s.push(0))
            s.label(kept)
            event_get(s, E, EVENT_DURATION); s.push(0); s.emit(0x0e); s.jump_if_zero(skip)
            pending_push(s, E, NESTED_LIST)
            s.label(skip)
        each_day_entry(s, context, lambda: get_global(s, DAY_KEY), due)
        s.label(checked)
        set_global(s, CHECKED_KEY, lambda: s.emit(0x40, now))
        s.label(done)
        s.result(0)
    rewriter.redirect(pc, ('fire_due', context['rid']), build)


def advance_within(rewriter, pc, argc, context):
    """38: (percent) the clock to that share of the current event's span (brew-calendar.js `advanceWithin`). The share is worked
    out in whole hundreds and the rest, as a word can't hold a percent of a day."""
    season_only(rewriter, pc, 38, context)

    def build(s):
        done, span = s.label(), sw(context, 14)
        C = lambda: get_global(s, CURRENT_KEY)
        C(); s.jump_if_zero(done)
        set_word(s, span, lambda: (push_larger(s, lambda: event_get(s, C, EVENT_DURATION), lambda: s.push(0)), s.push(1), s.emit(0x51)))
        set_global(s, CLOCK_KEY, lambda: (event_get(s, C, EVENT_MINUTE),
                                          s.arg(1), s.emit(0x40, span), s.push(100), s.emit(0x53), s.emit(0x52), s.emit(0x50),
                                          s.arg(1), s.emit(0x40, span), s.push(100), s.emit(0x54), s.emit(0x52), s.push(100), s.emit(0x53),
                                          s.emit(0x50)))
        s.label(done)
        s.result(0)
    rewriter.redirect(pc, ('advance_within', context['rid']), build)


def clock_set(rewriter, pc, argc, context):
    """39: (minute) the clock."""
    season_only(rewriter, pc, 39, context)
    rewriter.redirect(pc, 'clock_set', lambda s: (set_global(s, CLOCK_KEY, lambda: s.arg(1)), s.result(0)))


def clock_get(rewriter, pc, argc, context):
    """41: the clock."""
    season_only(rewriter, pc, 41, context)
    rewriter.redirect(pc, 'clock_get', lambda s: (s.push(CLOCK_KEY), s.call(55, 1)))


def next_weekday(rewriter, pc, argc, context):
    """44: (weekday, month address, date address): the date there moved on, school day by school day, to that weekday (story.js:
    a day whose name shares the weekday's first or second letter). The weekday is read as it runs (Fall '06 works some out)."""
    season_only(rewriter, pc, 44, context)
    m, d = context['cal_t'], context['cal_t'] + 1
    letters = rewriter.words([ord(c) for day in WEEKDAYS for c in day[:2]])

    def build(s):
        day, j, tries, word = sw(context, 14), sw(context, 15), sw(context, 13), sw(context, 12)
        loop, found = s.label(), s.label()
        set_word(s, word, lambda: (s.arg(1), s.emit(0x3f)))
        set_word(s, day, lambda: push_day_index(s, context, lambda: (s.arg(2), s.emit(0x3f)), lambda: (s.arg(3), s.emit(0x3f))))
        set_word(s, tries, lambda: s.push(0))
        s.label(loop)
        s.emit(0x40, tries); s.push(400); s.emit(0x0d); s.jump_if_nonzero(found)
        set_word(s, j, lambda: (push_weekday(s, lambda: s.emit(0x40, day)), s.push(2), s.emit(0x52), s.push(letters), s.emit(0x50)))
        s.emit(0x40, j); s.emit(0x3f); s.emit(0x40, word); s.push(256); s.emit(0x53); s.emit(0x0a)
        s.emit(0x40, j); s.push(1); s.emit(0x50); s.emit(0x3f); s.emit(0x40, word); s.push(256); s.emit(0x54); s.emit(0x0a)
        s.emit(0x11); s.jump_if_nonzero(found)
        set_word(s, j, lambda: push_next_school_day(s, lambda: s.emit(0x40, day)))
        s.emit(0x40, j); s.push(0); s.emit(0x0e); s.jump_if_nonzero(found)
        set_word(s, day, lambda: s.emit(0x40, j))
        set_word(s, tries, lambda: (s.emit(0x40, tries), s.push(1), s.emit(0x50)))
        s.jump(loop)
        s.label(found)
        date_of(s, context, lambda: s.emit(0x40, day))
        s.arg(2); s.emit(0x40, m); s.emit(0x3e); s.emit(0x15)
        s.arg(3); s.emit(0x40, d); s.emit(0x3e); s.emit(0x15)
        s.result(0)
    rewriter.redirect(pc, ('next_weekday', context['rid']), build)


def days_between(rewriter, pc, argc, context):
    """45: (month, day, month, day): days from the first date to the second."""
    season_only(rewriter, pc, 45, context)
    rewriter.redirect(pc, ('days_between', context['rid']), lambda s: season_answer(s, lambda: (
        push_day_index(s, context, lambda: s.arg(3), lambda: s.arg(4)),
        push_day_index(s, context, lambda: s.arg(1), lambda: s.arg(2)), s.emit(0x51))))


def event_flag(rewriter, pc, argc, context):
    """46: (event) whether its flag is set."""
    season_only(rewriter, pc, 46, context)

    def build(s):
        no = s.label()
        season_answer(s, lambda: s.push(0))
        event_get(s, lambda: s.arg(1), EVENT_FLAG); s.jump_if_zero(no)
        season_answer(s, lambda: s.push(1))
        s.label(no)
    rewriter.redirect(pc, ('event_flag', context['rid']), build)


def window_events(rewriter, pc, argc, context):
    """47: (month, day, from, to) how many of that day's events overlap the window; 48 (the same, address) writes their numbers
    there and answers nothing (brew-calendar.js `inWindow`: an event starts or ends inside it, or spans it)."""
    service = rewriter.code[pc][1] >> 8
    season_only(rewriter, pc, service, context)

    def build(s):
        day, count, end = sw(context, 14), sw(context, 15), sw(context, 13)
        E = lambda: s.emit(0x40, sw(context, 1))
        set_word(s, day, lambda: push_day_index(s, context, lambda: s.arg(1), lambda: s.arg(2)))
        set_word(s, count, lambda: s.push(0))

        def check():
            take, skip, second, third = s.label(), s.label(), s.label(), s.label()
            set_word(s, end, lambda: (event_get(s, E, EVENT_MINUTE), event_get(s, E, EVENT_DURATION), s.emit(0x50)))
            s.arg(3); event_get(s, E, EVENT_MINUTE); s.emit(0x0f); event_get(s, E, EVENT_MINUTE); s.arg(4); s.emit(0x0f); s.emit(0x12)
            s.jump_if_zero(second)
            s.jump(take)
            s.label(second)
            s.arg(3); s.emit(0x40, end); s.emit(0x0f); s.emit(0x40, end); s.arg(4); s.emit(0x0f); s.emit(0x12)
            s.jump_if_zero(third)
            s.jump(take)
            s.label(third)
            event_get(s, E, EVENT_MINUTE); s.arg(3); s.emit(0x0f); s.arg(4); s.emit(0x40, end); s.emit(0x0f); s.emit(0x12)
            s.jump_if_zero(skip)
            s.label(take)
            if service == 48:
                s.arg(5); s.emit(0x40, count); s.emit(0x50); E(); s.emit(0x3e); s.emit(0x15)
            set_word(s, count, lambda: (s.emit(0x40, count), s.push(1), s.emit(0x50)))
            s.label(skip)
        each_day_entry(s, context, lambda: s.emit(0x40, day), check)
        if service == 47:
            season_answer(s, lambda: s.emit(0x40, count))
        else:
            s.result(0)
    rewriter.redirect(pc, ('window_events', context['rid'], service), build)


def flag_set(rewriter, pc, argc, context):
    """56: (character, key, index, value) a flag, kept as the character's number FLAG_KEYS + key x 64 + index."""
    rewriter.redirect(pc, 'flag_set', lambda s: (s.arg(1), s.arg(2), s.push(64), s.emit(0x52), s.arg(3), s.emit(0x50),
                                                 s.push(FLAG_KEYS), s.emit(0x50), s.arg(4), s.call(52, 3), s.result(0)))


def flag_get(rewriter, pc, argc, context):
    """57: (character, key, index) a flag (0 when unset)."""
    rewriter.redirect(pc, 'flag_get', lambda s: (s.arg(1), s.arg(2), s.push(64), s.emit(0x52), s.arg(3), s.emit(0x50),
                                                 s.push(FLAG_KEYS), s.emit(0x50), s.call(53, 2)))


def list_remove(rewriter, pc, argc, context):
    """66: (entity, key, entry) that entry out of the list, the ones after it moved up (story.js: `splice`)."""
    def build(s):
        entity, key = (lambda: s.arg(1)), (lambda: s.arg(2))
        base, entry, length = (lambda: s.emit(0x41, 0)), (lambda: s.emit(0x41, 1)), (lambda: s.emit(0x41, 2))
        top, done, skip = s.label(), s.label(), s.label()
        push_list_base(s, key)                                                                  # local 0: the list's first number
        s.arg(3)                                                                                # local 1: the entry
        entity(); base(); s.push(LIST_LENGTH); s.emit(0x50); s.call(53, 2); s.push_result()     # local 2: the length
        entry(); s.push(0); s.emit(0x0e); entry(); length(); s.emit(0x0d); s.emit(0x11); s.jump_if_nonzero(skip)
        s.label(top)
        entry(); s.push(1); s.emit(0x50); length(); s.emit(0x0e); s.jump_if_zero(done)
        list_store(s, entity, key, base, entry,
                   lambda: (entity(), base(), entry(), s.emit(0x50), s.push(1), s.emit(0x50), s.call(53, 2), s.push_result()),
                   lambda: (entity(), base(), entry(), s.emit(0x50), s.call(53, 2), s.push_result()), context)
        s.emit(0x23, 1); entry(); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.jump(top)
        s.label(done)
        list_store(s, entity, key, base, entry, lambda: s.push(0),
                   lambda: (entity(), base(), entry(), s.emit(0x50), s.call(53, 2), s.push_result()), context)
        entity(); base(); s.push(LIST_LENGTH); s.emit(0x50); length(); s.push(1); s.emit(0x51); s.call(52, 3)
        s.label(skip)
        s.result(0)
    rewriter.redirect(pc, ('list_remove', context['rid']), build)


CAST_MOST = 100                         # characters 67 looks among


def character_named(rewriter, pc, argc, context):
    """67: (name) the first character with that name, or -1 (story.js: case aside, which SHS's string check doesn't)."""
    def build(s):
        i, top, found, none = sw(context, 14), s.label(), s.label(), s.label()
        set_word(s, i, lambda: s.push(0))
        s.label(top)
        s.emit(0x40, i); s.push(CAST_MOST); s.emit(0x0e); s.jump_if_zero(none)
        s.emit(0x40, i); s.push(context['name_buffer']); s.call(61, 2)
        s.push(context['name_buffer']); s.arg(1); s.call(24, 2); s.push_result(); s.jump_if_nonzero(found)
        set_word(s, i, lambda: (s.emit(0x40, i), s.push(1), s.emit(0x50)))
        s.jump(top)
        s.label(none)
        set_word(s, i, lambda: s.push(-1))
        s.label(found)
        season_answer(s, lambda: s.emit(0x40, i))
    rewriter.redirect(pc, ('character_named', context['rid']), build)


def schedule(rewriter, pc, argc, context):
    """33: (script, text, name, caption, month, day, minute, duration, icon, flag). A Campaign story's one event: its script is
    queued, its text and clock kept. Returns the event's ID. A Classic story's events go on the calendar (schedule_calendar)."""
    if context['kind'] == 'calendar':
        return schedule_calendar(rewriter, pc, argc, context)
    if context['kind'] == 'season':
        return season_schedule(rewriter, pc, argc, context)
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


def text_entry(rewriter, pc, argc, context):
    """29: (title, default, 0): BREW's text entry, as the smartphone's own (17). BREW keeps the answer as the event's text, which
    its scripts read straight after with 7 (and store with 52, as `$USR` or `$CAT_NAME`), so it goes under EVENT_TEXT, where
    event_text reads it. BREW's entry has only a title, as '11's does."""
    def build(s):
        s.arg(1); s.text(''); s.arg(2); s.call(17, 3)
        s.push_result()                                     # a local: the next call replaces R
        s.text(EVENT_TEXT); s.emit(0x41, 0); s.call(46, 2)
        s.result(1)
    rewriter.redirect(pc, 'text_entry', build)


def title_line(rewriter, pc, argc, context):
    """1: (destination, TITLE_FORMAT, `Surviving High School`, title): the story's first line, which the title card already
    says. It's left empty, and say() shows no empty line."""
    rewriter.redirect(pc, 'title_line', lambda s: (s.arg(1), s.push(0), s.emit(0x3e), s.emit(0x15), s.result(0)))


def titled_page(rewriter, pc, argc, context):
    """12: (title, text) -> SHS 33."""
    rewriter.redirect(pc, 'titled_page', lambda s: (s.arg(1), s.arg(2), s.push(0), s.call(33, 3)))


def the_end(rewriter, pc, argc, context):
    """70: the smartphone's closing message and the episode's exit."""
    rewriter.redirect(pc, ('end', context['rid']), lambda s: (s.text(END_TITLE), s.text(END_TEXT), s.push(END_ARGUMENT), s.call(33, 3),
                                                              s.call(7, 0)))


HANDLERS = {7: event_text, 8: field, 9: music, 12: titled_page, 13: scene_open, 14: scene_change, 15: name_plate, 16: narration_queue,
            18: scene_close,
            27: portrait_choice, 28: menu, 34: schedule_weekly, 42: today_date, 43: today_date,
            36: unschedule, 37: fire_due, 38: advance_within, 39: clock_set, 41: clock_get, 44: next_weekday, 45: days_between,
            46: event_flag, 47: window_events, 48: window_events, 56: flag_set, 57: flag_get, 66: list_remove, 67: character_named, 29: text_entry, 30: spinning_menu, 31: menu_timer, 33: schedule, 35: field_set, 49: player_name, 53: stored_text_get, 55: cast_name, 58: owned_set, 59: owned_get,
            62: list_push, 63: list_get, 64: list_set, 65: list_length, 70: the_end, 71: cast_name, 72: line, 74: wait, 80: build_query}
# No-ops in BREW (0, 2, 10, 22-26, 32, 54, 75-79); the calendar's setup where there's no calendar (69); art registration, since
# the addon holds the art (11).
DROPPED = {0, 2, 10, 11, 17, 22, 23, 24, 25, 26, 32, 54, 69, 75, 76, 77, 78, 79}   # 17: Fall '06 only ever clears the box's icons
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


def unquote(text):
    """A line (or each option of a `|` list) wrapped whole in double quotes, without them: '07's stories quote every spoken line
    (`"Yeah. I wonder what this is all about?"`), which SHS's box doesn't (owner, 2026-11-06). Quotes inside a line, a line that
    only starts or ends with one (`"Hi," she said.`) and apostrophes stay. Speech that quotes a name or title (`"I just got this one,
    "Alone," that's pretty cool."`) loses its outer pair too (owner, 2026-11-07; nested_quotes). None when nothing changes."""
    parts, changed = text.split(b'|'), False
    for k, part in enumerate(parts):
        core = part.strip()
        if (len(core) >= 2 and core[:1] == b'"' and core[-1:] == b'"'
                and (core.count(b'"') == 2 or nested_quotes(core[1:-1]))):
            start = part.index(b'"')
            parts[k] = part[:start] + core[1:-1] + part[start + len(core):]
            changed = True
    return b'|'.join(parts) if changed else None


def nested_quotes(inner):
    """Whether the quotes in `inner` (a line without its outer pair) pair up, each an opening one (at the start or after a space or
    bracket, before a letter) then a closing one (at the end or before a space or punctuation): a name or title quoted inside speech.
    `A" and "B` (two quoted things, narrated) doesn't, nor does `"Hi." (Aside.) "Bye."`, which splits instead (shown_parts)."""
    at = [k for k, c in enumerate(inner) if c == ord('"')]
    if not at or len(at) % 2:
        return False
    for opening, closing in zip(at[::2], at[1::2]):
        if not ((opening == 0 or inner[opening - 1:opening] in (b' ', b'(', b'-')) and inner[opening + 1:opening + 2].isalnum()):
            return False
        if not (closing == len(inner) - 1 or inner[closing + 1:closing + 2] in (b' ', b',', b'.', b'!', b'?', b';', b':', b')')):
            return False
    return True


MIXED_PART = re.compile(rb'\s*(?:"([^"]*)"|\(([^()]*)\))\s*')


def mixed_parts(text):
    """[(text, aside)] for a line made only of quoted speech and bracketed asides, at least one of each (`"Excellent." (She opens a
    pocket.)`); else None. An aside keeps no brackets here."""
    parts, at = [], 0
    while at < len(text):
        match = MIXED_PART.match(text, at)
        if match is None or match.end() == at:
            return None
        parts.append((match.group(1), False) if match.group(1) is not None else (match.group(2), True))
        at = match.end()
    if not any(aside for _, aside in parts) or all(aside for _, aside in parts):
        return None
    return parts


def unbracket_options(text):
    """A choice list (`|`) without the brackets wrapping a whole option: `(Kiss Angie.)` is `Kiss Angie.` (owner, 2026-11-06). Lines
    keep theirs: a whole bracketed line is narration or a thought (bracketed)."""
    if b'|' not in text:
        return None
    parts, changed = text.split(b'|'), False
    for k, part in enumerate(parts):
        core = part.strip()
        # (Male Cheerleader's `"(Point over at Beth and say, "Let's just say...")"` is quoted as well: both go.)
        cut = 2 if len(core) >= 4 and core[:2] == b'"(' and core[-2:] == b')"' else 1
        if (len(core) >= 2 and core[cut - 1:cut] == b'(' and core[-cut:len(core) - cut + 1] == b')' and core.count(b'(') == 1
                and core.count(b')') == 1):
            start = part.index(core[:1])
            parts[k] = part[:start] + core[cut:-cut] + part[start + len(core):]
            changed = True
    return b'|'.join(parts) if changed else None


# Text entry titles shown as the smartphone's prompt: '07's `(Enter name:)` without its brackets (owner, 2026-11-07).
ENTRY_TITLES = {b'(Enter name:)': b'Enter name:'}


def tidy(text):
    """A string as the translation shows it: unquote, unbracket_options, and a line led by an aside (`(Whispers.) "Calm down..."`)
    without its quotes (a line led by speech splits instead: shown_parts), and ENTRY_TITLES. None when nothing changes."""
    if text in ENTRY_TITLES:
        return ENTRY_TITLES[text]
    changed = unquote(text)
    text = changed if changed is not None else text
    options = unbracket_options(text)
    if options is not None:
        return options
    parts = mixed_parts(text)
    if parts is not None and parts[0][1]:
        return b' '.join(b'(' + part + b')' if aside else part for part, aside in parts)
    return changed


def strip_quotes(program):
    """Every string as the translation shows it (tidy)."""
    return rewrite_strings(program, tidy)


def shown_parts(text):
    """[(text, aside)]: what a line becomes on screen. A line led by speech that goes on into asides is several (`"Excellent." (She
    opens a pocket.)`: the speech, then each aside as the speaker's thought); else the line itself."""
    parts = mixed_parts(text)
    if parts is not None and not parts[0][1]:
        return parts
    return [(text, False)]


def strip_round_counts(program):
    """Take the round count off a word game's title format, `Bust a move. %d/%d`: only single-round questions still show one."""
    return rewrite_strings(program, lambda text: text[:-len(b' %d/%d')] if text.endswith(b' %d/%d') else None)


def is_printable(text):
    return all(32 <= byte < 250 or byte in (10, 13) for byte in text)


def split_long(text):
    """A line longer than LONGEST_LINE as several, at sentence ends (one sentence longer than that stays whole)."""
    if len(text) <= LONGEST_LINE:
        return [text]
    lines, current = [], ''
    for sentence in SENTENCE_END.split(text):
        if current and len(current) + 1 + len(sentence) > LONGEST_LINE:
            lines.append(current)
            current = sentence
        else:
            current = f'{current} {sentence}'.strip()
    lines.append(current)
    return lines


def helper_calls(program, shape):
    """{string address: count} of the strings passed last to a subroutine whose host calls are `shape` (a call is SAVE_RETURN
    0x42 then JUMP_ABS 0x29, the subroutine running to RETURN 0x43)."""
    instructions, helpers, out = program.instructions, set(), {}
    for k in range(len(instructions) - 1):
        if instructions[k].opcode == 0x42 and instructions[k + 1].opcode == 0x29:
            start = instructions[k + 1].operand
            end = next((m for m in range(start, min(start + 30, len(instructions))) if instructions[m].opcode == 0x43), None)
            if end is not None and [instructions[m].operand >> 8 for m in range(start, end) if instructions[m].opcode == 0x1f] == shape:
                helpers.add(start)
    for k in range(len(instructions) - 2):
        if (instructions[k].opcode == 0x1a and instructions[k + 1].opcode == 0x42 and instructions[k + 2].opcode == 0x29
                and instructions[k + 2].operand in helpers):
            out[instructions[k].operand] = out.get(instructions[k].operand, 0) + 1
    return out


def caption_badge(text):
    """(icon, badge text) for a Chapter 1 caption: `Wednesday, after school: Tryouts.` is `WED - Tryouts`, as Battle of the
    Schools writes `Wk. 1, MON - Lunch`. The time of day goes (the icon tells most of it): the badge's region takes about 18
    characters a line and wraps the rest, to three lines at most, ignoring a line break."""
    when, colon, where = text.rstrip('.').partition(': ')
    day, _, time = when.partition(', ')
    if not colon:                                           # `Wednesday night, Inside the party`
        where = time
    if day.split()[0] in WEEKDAYS:
        words = day.split()
        day = ' '.join([words[0][:3].upper()] + [w.title() for w in words[1:]])
    label = f'{day} - {where}' if where else day
    lower = text.lower()
    icon = next((icon for words, icon in CAPTION_ICONS if any(w in lower for w in words)), CAPTION_ICON)
    return EVENT_ICON_BASE + icon, label


def date_captions(program, rewriter):
    """{pc: the new format's address} of the format calls (1) that fill a school day's caption (DATE_CAPTION) with a date."""
    captions = {address: DATE_CAPTION.match(text) for address, text, _ in data_strings(program) if DATE_CAPTION.match(text)}
    out, instructions = {}, program.instructions
    for k, i in enumerate(instructions):
        if i.opcode != 0x1f or i.operand >> 8 != 1 or (i.operand & 255) != 3:
            continue
        # The caption's address pushed since the previous host call (0x5a pushes 0: CS Idol's caption is its script's first string).
        start = next((j + 1 for j in range(k - 1, -1, -1) if instructions[j].opcode == 0x1f), 0)
        pushed = [0 if x.opcode == 0x5a else x.operand for x in instructions[start:k] if x.opcode in (0x1a, 0x5a)]
        found = [address for address in pushed if address in captions]
        if len(found) == 1:
            match = captions[found[0]]
            out[i.pc] = rewriter.text(BADGE_TIME_FORMAT + match.group(1).decode('latin-1'))
    return out


def date_caption(rewriter, pc, argc, context):
    """1: (destination, a school day's caption, date): `9:00 AM - School`, the running event's time, into the destination, remembered
    (DATE_CAPTION_KEY) so that say() shows it as the event's badge, not a line (owner, 2026-11-07: dates are on the cards)."""
    new = context['date_captions'][pc]
    rewriter.redirect(pc, ('date_caption', pc), lambda s: (set_global(s, DATE_CAPTION_KEY, lambda: s.arg(1)),
                                                           s.arg(1), s.push(new), push_badge_time(s), s.call(22, 6)))


def title_formats(program):
    """The pcs of the format calls (1) that build a story's first line from TITLE_FORMAT."""
    address = next((a for a, text, _ in data_strings(program) if text == TITLE_FORMAT), None)
    instructions, out = program.instructions, set()
    for k, i in enumerate(instructions):
        if i.opcode == 0x1f and i.operand >> 8 == 1 and address is not None and (i.operand & 255) >= 2:
            pushed = instructions[k - (i.operand & 255) + 1]
            if (pushed.opcode == 0x5a and address == 0) or (pushed.opcode == 0x1a and pushed.operand == address):
                out.add(i.pc)
    return out


def event_date(resources):
    """`Friday, November 9`: the day a Campaign story's setup puts its one event on (33's month and day), and its weekday by
    the calendar the setup describes (69: start month and day, and that day's weekday), as BREW's planner heads a day. Run
    in the VM with every other call answered 0; None where there's no event."""
    vm = KiwiVM(decode_program(upgrade(resources[FIRST_SCRIPT])))
    event = calendar = None
    for _ in range(200000):
        stop = vm.run()
        if stop.kind == StopKind.HALT:
            break
        args = [signed16(a) for a in stop.args]
        if stop.yield_id == 69:
            calendar = args
        elif stop.yield_id == 33:
            event = args
        vm.resume(1 if stop.yield_id == 33 else 0)
    if event is None or calendar is None or not 1 <= event[4] <= 12:
        return None
    lengths = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    month, day, index = calendar[2], calendar[3], 0
    while (month, day) != (event[4], event[5]) and index < 400:
        day, index = day + 1, index + 1
        if day > lengths[month - 1]:
            month, day = month % 12 + 1, 1
    return f'{WEEKDAYS[(calendar[4] + index) % 7]}, {MONTHS[event[4] - 1]} {event[5]}'


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


ROUTINE_SHAPE = '443018798db8'           # the first 12 hex digits of the SHA-1 of the word-game routine's opcodes


def routine_shape(instructions, start):
    """The fingerprint of the function starting at `start`: its opcodes up to the next function, SHA-1, 12 hex digits."""
    k = next(n for n, i in enumerate(instructions) if i.pc == start)
    end = next((n for n in range(k + 1, len(instructions)) if instructions[n].opcode == 0x48), len(instructions))
    return hashlib.sha1(bytes(i.opcode for i in instructions[k:end])).hexdigest()[:12]


def spin_routine(program):
    """Where the routine with the spinning menu starts, or None. It's the same code everywhere it appears (55 scripts, 2026-11-05)."""
    instructions = program.instructions
    # (A spinning menu outside any function is a question of its own, which spinning_menu handles: Fall '06's 25023 has two, its
    # exercise rounds `Lap %d/%d` and `Rep %d/%d`; Stage 6.)
    starts = {}
    for i in instructions:
        if i.opcode == 0x1f and i.operand >> 8 == 30:
            start = max((j.pc for j in instructions if j.opcode == 0x48 and j.pc <= i.pc), default=None)
            if start is not None:
                starts.setdefault(start, i.pc)
    # Only BREW's shared word-game routine is replaced (word_game): the same 70 instructions in all 64 scripts that have it, by the
    # opcodes' fingerprint. Fall '06's other functions with a spinning menu (25002's mood tutorial, 25040's `Say something:`
    # conversation, whose words count as flirty, nice or stupid) keep theirs as a question, its answer in register 0 (Stage 6).
    starts = {start: site for start, site in starts.items() if routine_shape(instructions, start) == ROUTINE_SHAPE}
    if not starts:
        return None
    if len(starts) > 1:
        raise StoryError('a script has more than one spinning menu routine')
    start, site = next(iter(starts.items()))
    sites = [site]
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
            # (20: The School Paper's page has a pause and six two-value pushes before its call; Stage 5.)
            for j in range(i + 1, min(i + 20, len(instructions) - 1)):
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


FUNKY_MONKEY_ENDINGS = (2507, 2568, 2623, 2684, 2751)     # '07 monkey.exp: each ending's music push, its first instruction
OWN_SCENE_26505 = 26505


def fix_funky_monkey_07(rewriter, context):
    """'08's Funky Monkey opens five of its endings with a scene change (14: speaker kept, day sky, its own picture 26505), where '07's
    keep whatever was showing. '07's copy keeps its own writing, and its date, but takes '08's fixes to its code (owner, 2026-11-07)."""
    code = rewriter.code
    for pc in FUNKY_MONKEY_ENDINGS:
        if not (code[pc - 2][0] == 0x48 and code[pc][0] == 0x1a and 8000 <= code[pc][1] < 8000 + MUSIC_TRACKS and code[pc + 1] == (0x1f, 9 << 8 | 1)):
            raise StoryError(f"Funky Monkey ('07): no ending starts at {pc}")

        def build(s):
            depth = lambda: (s.push(DEPTH_KEY), s.call(55, 1), s.push_result())
            s.push(_SCENE_LAYOUT['sky']); depth(); s.emit(0x50); s.push(0); s.call(54, 2)
            s.push(_SCENE_LAYOUT['location']); depth(); s.emit(0x50); s.push(OWN_SCENE_26505); s.call(54, 2)
            show_top_scene(s, context)
        rewriter.insert(pc, build)


CONTEXT_FIXES = {'monkey.exp': fix_funky_monkey_07}     # story fixes that need the script's context (its own pictures)


def catch_pages(program):
    """The calls of 12 that introduce a catch game: the last host call before one, and one that jumps past that to the game. A
    music call (9) between doesn't count: Trick or Treat starts the game's track after its page (Stage 3b)."""
    instructions = program.instructions
    hosts = [k for k, i in enumerate(instructions) if i.opcode == 0x1f and i.operand >> 8 != 9]
    pages = set()
    for n, k in enumerate(hosts):
        if instructions[k].operand >> 8 not in CATCH_MODES or not n or instructions[hosts[n - 1]].operand >> 8 != 12:
            continue
        pages.add(instructions[hosts[n - 1]].pc)
        if n > 1 and instructions[hosts[n - 2]].operand >> 8 == 12 and any(i.opcode == 0x28 for i in instructions[hosts[n - 2]:hosts[n - 1]]):
            pages.add(instructions[hosts[n - 2]].pc)
    return pages


def drop_page_pauses(rewriter):
    """A PAUSE (0x32) straight after a page (12) waits for nothing: BREW's page draws and returns, and the script waits for a key
    itself, where SHS's page (33) or the game screen it becomes already waits for a tap. A pause stays in the VM as an untitled
    stop, so it goes: a jump to the next instruction, the same length (Trick or Treat, Stage 3b)."""
    for pc, service, _ in rewriter.calls():
        if service == 12 and pc + 1 < rewriter.original and rewriter.code[pc + 1] == (0x32, None):
            rewriter.code[pc + 1] = (0x29, rewriter.code_base + pc + 2)


def script_context(rewriter, script, looks, player, program, catch_sizes=None):
    """What a script's shims share: scratch words in its data, and its bracketed strings' bare twins."""
    start = spin_routine(program)
    thoughts, game_words, long_lines = [], [], []

    def pieces(key, text):
        parts = [(piece, aside) for part, aside in shown_parts(text.encode('latin-1'))
                 for piece in split_long(part.decode('latin-1'))]
        if len(parts) > 1:                                  # (only a line that splits takes copies of its pieces)
            entries = [-rewriter.text(piece) if aside else rewriter.text(piece) for piece, aside in parts]
            long_lines.append((key, rewriter.words([len(entries)] + entries)))
    for address, text, _ in data_strings(program):
        bare = bracketed(text)
        if bare is not None:
            thoughts.append((address, rewriter.text(bare.decode('latin-1'))))
            pieces(thoughts[-1][1], bare.decode('latin-1'))
        elif is_printable(text):
            pieces(address, text.decode('latin-1'))
        word = bare_word(text) if start is not None else None
        if word is not None:
            game_words.append((address, rewriter.text(word.decode('latin-1'))))
    strings = {address: text.decode('latin-1') for address, text, _ in data_strings(program)}
    catch = {}
    if any(i.opcode == 0x1f and i.operand >> 8 in CATCH_MODES for i in program.instructions):
        words = sorted(CATCH_WORDS.items())
        sizes = sorted((catch_sizes or {}).items())
        # Each page string's twin for the word game: the generic title as the banner, a text without the catch game's points.
        plain, low = [], []
        for address, text, _ in data_strings(program):
            if text == CATCH_GENERIC_TITLE:
                plain.append((address, rewriter.text(CATCH_TITLE)))
            elif CATCH_POINTS.search(text) or CATCH_LOW.search(text):
                if CATCH_LOW.search(text):
                    low.append(address)
                plain.append((address, rewriter.text(CATCH_LOW.sub(b'', CATCH_POINTS.sub(b'', text)).decode('latin-1'))))
        catch = dict(catch_good=rewriter.words([0] * CATCH_LIST_WORDS), catch_bad=rewriter.words([0] * CATCH_LIST_WORDS),
                     catch_plain=plain, catch_low=low,
                     catch_words=rewriter.words([value for picture, pair in words for value in (picture, rewriter.text(pair[0]), rewriter.text(pair[1]))]),
                     catch_words_count=len(words), catch_sizes_count=len(sizes),
                     catch_sizes=rewriter.words([value for picture, size in sizes for value in (picture, *size)] or [0]))
    return dict(rid=script, kind='single', looks=sorted(looks.items()), hash_factors=rewriter.words(HASH_FACTORS),
                plate=rewriter.words([-1]), plate_scan=rewriter.words([0, 0]) if any(i.opcode == 0x1f and i.operand >> 8 == 15 for i in program.instructions) else None,
                plate_name=rewriter.words([0] * NAME_WORDS) if any(i.opcode == 0x1f and i.operand >> 8 == 15 for i in program.instructions) else None,
                plates=any(i.opcode == 0x1f and i.operand >> 8 == 15 for i in program.instructions), **named_words(program, rewriter, start),
                last_line=rewriter.words([-1]), dots=rewriter.words([0, 0, 0, 0]), opener_now=rewriter.words([0]), dots_buffer=rewriter.words([0] * (OPENER_WORDS + 4)), narration=rewriter.words([-1]), menu=rewriter.words([-1, -1, -1, 0, -1, 0]),
                name_buffer=rewriter.words([0] * NAME_WORDS), hash_temp=rewriter.words([0]), line_twin=rewriter.words([-1]), player=player,
                bracketed=thoughts, game_words=game_words, routine=start, long_lines=long_lines, pieces=rewriter.words([-1, 0, 0]),
                you_titles=tuple(address for address, text in strings.items() if text in CHOICE_TITLED),
                captions=[(address, *badge[:1], rewriter.text(badge[1])) for address in helper_calls(program, [14, 72])
                          for badge in [caption_badge(strings[address])]],
                title_formats=title_formats(program), date_captions=date_captions(program, rewriter), game_pages=game_pages(program, start) if start is not None else (),
                page=rewriter.words([-1, -1]), word=rewriter.words([0]), catch_pages=catch_pages(program), **catch,
                # (only a script with a portrait choice takes its words: a big story's data is close to the VM's stack)
                portraits=rewriter.words([-1, 0, 0]) if any(i.opcode == 0x1f and i.operand >> 8 == 27 for i in program.instructions) else None,
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


def translate(archive_resources, name, spec, pack=PACK_CAMPAIGN, episode=0, suffix=TITLE_SUFFIX_08, calendar=None,
              title_extra='', title=None):
    """A story's SHS `.exp` bytes, from its resources by ID and the addon's spec. Twice over: its title card shows the first
    picture the story does, which takes the story itself to find. `calendar` (default: a Classic story) runs its events on the
    calendar driver, as an '08 `(Classic)` copy does in the Campaign's pack; `title_extra` follows its title."""
    calendar = pack == PACK_CLASSIC if calendar is None else calendar
    # (A season keeps its events in its own place: SEASON_EVENTS.)
    _EVENT_LAYOUT['base'] = SEASON_EVENTS if calendar == 'season' else EVENT_BASE
    _SCENE_LAYOUT.update(location=SEASON_SCENE_LOCATION_KEY, sky=SEASON_SCENE_SKY_KEY) if calendar == 'season' else None
    try:
        return _translate(archive_resources, name, spec, pack, episode, suffix,
                          opening_picture(_translate(archive_resources, name, spec, pack, episode, suffix, -1, calendar,
                                                     title_extra, title)), calendar, title_extra, title)
    finally:
        _EVENT_LAYOUT['base'] = EVENT_BASE
        _SCENE_LAYOUT.update(location=SCENE_LOCATION_KEY, sky=SCENE_SKY_KEY)


def _translate(archive_resources, name, spec, pack, episode, suffix, card, calendar, title_extra='', title=None):
    looks = spec['stories'].get(name)
    if looks is None:
        raise StoryError(f'the addon has no looks for {name}')
    table = {}
    for key, bank in looks.items():
        entries = [int(v) for v in key.split(',')]
        if table.setdefault(look_hash(entries), bank) != bank:
            raise StoryError(f'{name}: two looks have the same hash')
    season = calendar == 'season'
    title = (title or clean_title(title_of(archive_resources[1]))) + title_extra
    date = event_date(archive_resources) if FIRST_SCRIPT in archive_resources else None
    scripts = sorted(rid for rid, data in archive_resources.items() if data[:4] == b'kiwi')
    # The story script is 26000, or 25002 in a story without one (the M.A.S.H. packs, whose setup schedules 25002; Stage 4): a
    # Classic event runs the story script whichever its number (calendar_step), so only where it goes changes. A Classic story
    # whose events all schedule one other script has that as its story (Artistic Differences' 25003; Stage 5).
    story_script = STORY_SCRIPT if calendar and BREW_STORY_SCRIPT not in scripts and STORY_SCRIPT in scripts else BREW_STORY_SCRIPT
    scheduled = scheduled_scripts(archive_resources, scripts)
    if calendar and len(scheduled) == 1 and next(iter(scheduled)) in scripts:
        story_script = next(iter(scheduled))
    # A script nothing schedules or names is left out: Stage 5's CS Idol, Artistic Differences and The School Paper carry an
    # 88-byte `School / March %d` date screen no event runs.
    if season:
        # A season's events run scripts 25002 to 25050, each its own, so every script keeps its number and the driver has one of
        # its own (DRIVER_SCRIPT, made below). All of them are kept: they choose one another at run time.
        story_script, unused = None, []
        script_map = {rid: rid for rid in scripts}
        if DRIVER_SCRIPT in scripts or NEST_SCRIPT in scripts:
            raise StoryError(f'{name} has a script {DRIVER_SCRIPT} or {NEST_SCRIPT}, which the season driver takes')
    else:
        unused = [rid for rid in scripts if rid not in (FIRST_SCRIPT, story_script) and not script_named(archive_resources, scripts, rid)]
    scripts = [rid for rid in scripts if rid not in unused]
    if not season:
        # Other scripts the events schedule (CS Idol's school days, 26001; Stage 5) follow the story's, from 25003 on.
        script_map = {FIRST_SCRIPT: FIRST_SCRIPT, story_script: STORY_SCRIPT}
        for rid in sorted(scheduled - {story_script}):
            if calendar and rid in scripts:
                script_map[rid] = STORY_SCRIPT + len(script_map) - 1
    extra = [rid for rid in scripts if rid not in script_map]
    if extra:
        raise StoryError(f'{name}: scripts {extra} need the calendar driver or a script map')
    own_missing = missing_own_pictures(archive_resources)
    resources = {}
    for script in scripts:
        program = strip_quotes(strip_round_counts(strip_name_marks(decode_program(upgrade(archive_resources[script])))))
        rewriter = Rewriter(program, zero_gap=True)
        drop_page_pauses(rewriter)
        if name in STORY_FIXES and script == story_script:
            STORY_FIXES[name](rewriter)
        sizes = {int(picture): tuple(entry[1:]) for picture, entry in spec.get('catch', {}).get('pictures', {}).items()
                 if int(picture) not in own_missing}
        context = script_context(rewriter, script, table, not title.startswith('Quiz '), program, sizes)
        context['kind'] = 'season' if season else 'calendar' if calendar else 'single'
        context['program'], context['script_map'] = program, script_map
        context['own_missing'] = own_missing
        if calendar:
            context.update(calendar_words(rewriter))
        if season:
            context.update(season_words(rewriter))
        context['backgrounds_07'] = pack != PACK_CAMPAIGN          # '07's shared locations; an '08 copy shows '08's
        context['own_backgrounds'] = sorted((int(location), OWN_BACKGROUND_INDEX + n)
                                            for location, n in spec.get('backgrounds', {}).get(name, {}).items())
        if name in CONTEXT_FIXES and script == story_script:
            CONTEXT_FIXES[name](rewriter, context)
        for pc, service, argc in rewriter.calls():
            if service == 69 and season:
                season_setup(rewriter, pc, argc, context)
            elif service == 69 and calendar:
                calendar_setup(rewriter, pc, argc, context)
            elif service == 12 and (pc in context['game_pages'] or pc in context['catch_pages']):
                game_page(rewriter, pc, argc, context)
            elif service in CATCH_MODES:
                catch_game(rewriter, pc, argc, context)
            elif service == 1 and pc in context['date_captions']:
                date_caption(rewriter, pc, argc, context)
            elif service == 1 and pc in context['title_formats']:
                title_line(rewriter, pc, argc, context)
            elif service in RENAME:
                rewriter.rename(pc, RENAME[service])
            elif service in DROPPED:
                dropped(rewriter, pc, argc, context)
            elif service in HANDLERS:
                HANDLERS[service](rewriter, pc, argc, context)
            else:
                raise StoryError(f'{name}, script {script}: service {service} with {argc} arguments has no translation yet')
            if season and service in NEST_WAITS and rewriter.sites.get(pc, ('',))[0] == 'shim':
                rewriter.before(pc, nested_check)
        if context['routine'] is not None:
            word_game(rewriter, context['routine'], context)
        if script == FIRST_SCRIPT:
            # With the calendar, the setup also queues the story script, whose prologue runs the events (calendar_step).
            rewriter.prologue(lambda s: (s.push(NARRATOR), s.call(75, 1), s.push(PLAYER), s.call(74, 1),
                                         s.push(EVENT_CHARACTER_KEY), s.push(-1), s.call(54, 2),
                                         s.push(NARRATOR), s.text(''), s.call(64, 2),
                                         s.push(NARRATOR), s.push(-1), s.call(72, 2),
                                         *((s.push(DRIVER_SCRIPT if season else STORY_SCRIPT), s.push(0), s.call(10, 2))
                                           if calendar else ())))
        elif calendar and script == story_script:
            # The title card has the day the first event runs on (CS Idol's setup schedules its last school day last, Stage 5).
            rewriter.prologue(lambda s, context=context: calendar_step(
                s, context, lambda: (write_date(s, context, lambda: get_global(s, DAY_KEY)),
                                     s.text(title), s.push(context['date_buffer']), s.push(card), s.push(0), s.call(8, 4)),
                lambda: (s.text(END_TITLE), s.text(END_TEXT), s.push(END_ARGUMENT), s.call(33, 3), s.call(7, 0), s.emit(0x33)),
                lambda: (s.text(title), s.push(context['date_buffer']), s.push(card), s.push(0), s.call(8, 4))))
        elif calendar:
            pass                                            # an event's own script: the driver already showed its card or badge
        else:
            rewriter.prologue(lambda s: (s.text(title), s.text(date or ''), s.push(card), s.push(0), s.call(8, 4)))
        target = script_map[script]
        resources[target] = rewriter.finish().to_bytes()
    if season:
        resources[DRIVER_SCRIPT] = season_driver(name, spec, table, title, card, own_missing)
        resources[NEST_SCRIPT] = season_script(spec, table, own_missing, nest_runner)
    resources[ADDON_RECORD] = requires_bytes([(ADDON_ID, ADDON_REQUIRED)])
    resources[VERSION_RECORD] = version_bytes(STORY_VERSION)
    resources[1] = Metadata(pack, episode, (title + suffix,) * 5).to_bytes()
    return encode_exp(resources)


EMPTY_SCRIPT = b'kiwi\x01\x00' + bytes(6) + b'\x00\x01' + bytes((0x33,))   # KiWi v1: no data, one instruction, HALT


def season_driver(name, spec, table, title, card, own_missing):
    """The season driver's script (DRIVER_SCRIPT): a script that is only the driver (season_step), with its title card, date cards and
    the story's end."""
    program = decode_program(upgrade(EMPTY_SCRIPT))
    rewriter = Rewriter(program, zero_gap=True)
    sizes = {int(picture): tuple(entry[1:]) for picture, entry in spec.get('catch', {}).get('pictures', {}).items()
             if int(picture) not in own_missing}
    context = script_context(rewriter, DRIVER_SCRIPT, table, True, program, sizes)
    context.update(kind='season', program=program, script_map={}, own_missing=own_missing)
    context.update(calendar_words(rewriter))
    context.update(season_words(rewriter))
    context.update(week_words=rewriter.words([0] * 5), week_buffer=rewriter.words([0] * 12),
                   date_range_buffer=rewriter.words([0] * 24), day_line_buffer=rewriter.words([0] * 24))
    # The first event opens on week 1's card, as later weeks' (the story's name is the library's: owner, 2026-11-07); every new day
    # starts with its narration line, under a new week's card first.
    def step(s):
        new_day = lambda: (week_card(s, context, card), day_line(s, context))
        season_step(
            s, context, lambda: (write_date(s, context, lambda: get_global(s, DAY_KEY)), new_day()),
            lambda: (s.text(END_TITLE), s.text(END_TEXT), s.push(END_ARGUMENT), s.call(33, 3), s.call(7, 0), s.emit(0x33)),
            new_day)
    rewriter.prologue(step)
    return rewriter.finish().to_bytes()


def season_script(spec, table, own_missing, body):
    """A season's own script, holding only `body(s, context)`."""
    program = decode_program(upgrade(EMPTY_SCRIPT))
    rewriter = Rewriter(program, zero_gap=True)
    sizes = {int(picture): tuple(entry[1:]) for picture, entry in spec.get('catch', {}).get('pictures', {}).items()
             if int(picture) not in own_missing}
    context = script_context(rewriter, NEST_SCRIPT, table, True, program, sizes)
    context.update(kind='season', program=program, script_map={}, own_missing=own_missing)
    context.update(calendar_words(rewriter))
    context.update(season_words(rewriter))
    rewriter.prologue(lambda s: body(s, context))
    return rewriter.finish().to_bytes()


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


CLASSIC_NUMBER = re.compile(r'clsc_(?:(\d+)_|.*_(\d+)\.exp$)', re.I)     # clsc_034_Hooky.exp, clsc_fr_conn_014.exp
# Classic files without a number, after the last (73), by file name (the plan's "unnumbered ones after the last").
CLASSIC_UNNUMBERED = {'clsc_cs_idol.exp': 74, 'clsc_halloween.exp': 75, **{f'clsc_mash0{n}.exp': 75 + n for n in range(1, 7)},
                      'clsc_winter_love_day.exp': 82}
# An '08 `(Classic)` copy (a Classic story whose '08 file really differs from '07's) in the Campaign's pack: after its
# specials, by Classic number (Funky Monkey, 38, is 9238).
CLASSIC_COPY_BASE, CLASSIC_COPY_SUFFIX = 9200, ' (Classic)'


def classic_number(path, classic_folder=None):
    """A Classic story's number (pack 31100): `clsc_034_Hooky.exp` is 34. An '07 copy (the VX9800's `meatloaf.exp`) takes its '08
    copy's, found by title in `classic_folder`."""
    path = Path(path)
    if (number := _file_classic_number(path.name)) is not None:
        return number
    if classic_folder is not None:
        title = clean_title(title_of(read_archive(path)[1]))
        for other in sorted(Path(classic_folder).glob('clsc_*.exp')):
            if clean_title(title_of(read_archive(other)[1])) == title and (number := _file_classic_number(other.name)) is not None:
                return number
    raise StoryError(f'{path.name} has no Classic number')


def _file_classic_number(name):
    if (match := CLASSIC_NUMBER.match(name)):
        return int(match.group(1) or match.group(2))
    return CLASSIC_UNNUMBERED.get(name.lower())


def build_classic_copy(path, addon_path):
    """(file name, bytes) of an '08 `(Classic)` copy: '08's file of a Classic story, in the Campaign's pack and badge, on the calendar,
    with '08's shared locations and the story's own pictures."""
    path = Path(path)
    spec = json.loads(ExpArchive(Path(addon_path).read_bytes()).read(SPEC))
    resources = read_archive(path)
    story = translate(resources, path.name, spec, PACK_CAMPAIGN, CLASSIC_COPY_BASE + classic_number(path), TITLE_SUFFIX_08,
                      calendar=True, title_extra=CLASSIC_COPY_SUFFIX)
    return file_name(clean_title(title_of(resources[1])) + CLASSIC_COPY_SUFFIX, TITLE_SUFFIX_08), story


def build_classic(path, addon_path, classic_folder=None):
    """(file name, bytes) of a Classic story (`'07`, pack 31100), from its file and the addon: its events run on the calendar."""
    path = Path(path)
    spec = json.loads(ExpArchive(Path(addon_path).read_bytes()).read(SPEC))
    resources = read_archive(path)
    story = translate(resources, path.name, spec, PACK_CLASSIC, classic_number(path, classic_folder), TITLE_SUFFIX_07)
    return file_name(clean_title(title_of(resources[1])), TITLE_SUFFIX_07), story


def build_season(path, addon_path):
    """(file name, bytes) of Fall '06 Football Season (`'07`, pack 31200), from '07's base pack and the addon: a whole term on the
    season driver."""
    path = Path(path)
    spec = json.loads(ExpArchive(Path(addon_path).read_bytes()).read(SPEC))
    resources = read_archive(path)
    story = translate(resources, path.name, spec, PACK_SEASON, SEASON_EPISODE, TITLE_SUFFIX_07, calendar='season', title=SEASON_TITLE)
    return file_name(SEASON_TITLE, TITLE_SUFFIX_07), story


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


def own_fingerprint(png):
    """A stored own background's fingerprint (its day sky), for OWN_08_REDRAWS."""
    import io
    return hashlib.sha256(Image.open(io.BytesIO(png)).convert('RGB').tobytes()).hexdigest()[:16]


def scheduled_scripts(resources, scripts):
    """The scripts a story's events schedule (33's first argument, where it is a constant)."""
    found = set()
    for rid in scripts:
        program = decode_program(upgrade(resources[rid]))
        for instruction in program.instructions:
            if instruction.opcode == 0x1f and instruction.operand >> 8 in (33, 34):
                values = newrules.pushed_values(program, instruction.pc, instruction.operand & 255)
                if values and isinstance(values[0], int):
                    found.add(values[0])
    return found


def script_named(resources, scripts, rid):
    """Whether any script pushes `rid` (to schedule it, queue it or name it in any other way)."""
    for other in scripts:
        if any(i.opcode == 0x1a and i.operand == rid for i in decode_program(upgrade(resources[other])).instructions):
            return True
    return False


def own_locations(pack):
    """The locations a story's scenes (13, 14) name that aren't the shared ones (1000-1027, 2000-2011): its own pictures."""
    found = set()
    for data in pack.values():
        if data[:4] != b'kiwi':
            continue
        program = decode_program(upgrade(data))
        for instruction in program.instructions:
            if instruction.opcode == 0x1f and instruction.operand >> 8 in (13, 14):
                values = newrules.pushed_values(program, instruction.pc, instruction.operand & 255)
                location = values[1] if instruction.operand >> 8 == 13 else values[2]
                if location is not None and location >= 0 and not (1000 <= location < 1000 + LOCATIONS_08
                                                                     or 2000 <= location < 2000 + LOCATIONS_08_EXTRA):
                    found.add(location)
    return sorted(found)


def own_resources(archive_resources):
    """A story's resources with its CMB0 bundles opened (BREW numbers a bundle's members resource + 1 + k)."""
    found = dict(archive_resources)
    for rid, data in archive_resources.items():
        if data[:4] == b'CMB0':
            for member, payload in nr_art.cmb0(data, rid).items():
                found.setdefault(member, payload)
    return found


def missing_own_pictures(archive_resources):
    """The OWN_CATCH_PICTURES this story doesn't hold as the addon's copy (none, or a picture of its own by that number)."""
    found = own_resources(archive_resources)
    return {picture for picture, digest in OWN_CATCH_PICTURES.items()
            if picture not in found or hashlib.sha1(found[picture]).hexdigest() != digest}


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


def shifted(picture, dx, dy=0):
    """A picture moved `dx` pixels across (and `dy` down) on a canvas of its own size."""
    out = Image.new(picture.mode, picture.size, (0, 0, 0, 0))
    out.paste(picture, (dx, dy))
    return out


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


def build_addon(casts, games, render_music=None, java_jar=None):
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
    # Classic stories' own backgrounds, each picture once (an '07 copy and its '08 file share theirs).
    spec['backgrounds'], drawn = {}, {}
    for entry in casts:
        if entry['kind'] != 'classic' and not entry['file'].startswith('32411/'):
            continue
        packs = story_packs(entry, games, bases)
        art = brew_art.Art(packs)
        table = {}
        for location in own_locations(packs[0]):
            strips = [brew_art.location(art, location, sky) for sky in range(SKY_MODES)]
            if strips[0] is None:
                continue
            key = hashlib.sha256(b''.join(strip.tobytes() for strip in strips)).hexdigest()
            if key not in drawn:
                drawn[key] = len(drawn)
                for sky, strip in enumerate(strips):
                    resources[OWN_BACKGROUND_BASE + SKY_MODES * drawn[key] + sky] = strip_png(strip)
            table[str(location)] = drawn[key]
        if table:
            for n in set(table.values()):
                extra = OWN_08_REDRAWS.get(own_fingerprint(resources[OWN_BACKGROUND_BASE + SKY_MODES * n]))
                for sky in range(SKY_MODES) if extra is not None else ():
                    resources[OWN_BACKGROUND_BASE + SKY_MODES * n + sky + OWN_08_OFFSET] =                         resources[BACKGROUND_BASE + SKY_MODES * (LOCATIONS_08 + extra - 2000) + sky]
            spec['backgrounds'][Path(entry['file']).name] = table
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
            body = member['list'][0]
            bounds = art.bounds(body) if isinstance(body, int) and body >= 26000 else None
            if bounds and abs(bounds[0] + bounds[2]) >= 2 * CENTRE_OWN_BODY:
                faces = [shifted(face, -round((bounds[0] + bounds[2]) / 2)) for face in faces]
            if body in MIRRORED_BODIES:
                faces = [face.transpose(Image.FLIP_LEFT_RIGHT) for face in faces]
            if body in LOWERED_BODIES:
                faces = [shifted(face, 0, LOWERED_BODIES[body]) for face in faces]
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
    resources.update(event_icons(art08))
    own_art = {}
    for entry in casts:
        packs = loaded.get(entry['file']) or story_packs(entry, games, bases)
        for picture in set(OWN_CATCH_PICTURES) - set(own_art) - missing_own_pictures(packs[0]):
            own_art[picture] = brew_art.Art(packs[:1])
    if set(own_art) != set(OWN_CATCH_PICTURES):
        raise StoryError(f'No story holds the own catch pictures {sorted(set(OWN_CATCH_PICTURES) - set(own_art))}')
    catch_resources, spec['catch'] = catch_pictures(art08, bases['08'], own_art)
    for n, picture in enumerate(sorted(OWN_CATCH_PICTURES)):
        resources.update(event_icons(own_art[picture], {picture: OWN_ICON_BASE + n}))
    if java_jar is not None:
        java_resources, spec['catch']['java'] = java_look(java_jar, spec['catch'], art08)
        resources.update(java_resources)
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


def event_icons(art, pictures=None):
    """{resource: PNG} of BREW's small pictures (EVENT_ICONS, or `pictures`: {picture: resource}), for time badges: 8 times with no
    smoothing, then fitted to EVENT_ICON_SIZE, so their pixels stay sharp at the smartphone's icon size."""
    out = {}
    targets = pictures or {picture: EVENT_ICON_BASE + picture for picture in EVENT_ICONS}
    for picture, resource in targets.items():
        try:
            left, top, right, bottom = art.bounds(picture)
        except Exception:
            continue
        if not 0 < right - left <= 64 or not 0 < bottom - top <= 64:
            continue
        canvas = Image.new('RGBA', (right - left, bottom - top), (0, 0, 0, 0))
        art.draw(canvas, picture, -left, -top)
        big = canvas.resize((canvas.width * 8, canvas.height * 8), Image.NEAREST)
        scale = EVENT_ICON_SIZE / max(canvas.width, canvas.height)
        out[resource] = brew_art.png(big.resize((round(canvas.width * scale), round(canvas.height * scale)), Image.LANCZOS))
    return out


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


def catch_pictures(art, pack, own_art=None):
    """({resource: PNG}, spec) of the catch game: BREW's frame (FUN_00005b94, as Tardy-Slip's CatchScreen draws it), its ring, digits and
    captions, and every item and player picture, at 3 times with no smoothing; then the stories' own (`own_art`: picture -> an Art
    over the story that holds it)."""
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
    shown = [(picture, art) for picture in sorted(CATCH_WORDS)] + sorted((own_art or {}).items())
    for n, (picture, art) in enumerate(shown):
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


def strip_edges():
    """(width, height) of the frame backdrop at the strip's density, and where the strip's top and bottom are in it once
    scaled BACKGROUND_SCALE times."""
    per_unit = STRIP_WIDTH / nr_art.BACKGROUND_UNITS
    width, height = (round(side * per_unit) for side in nr_art.FRAME_UNITS)
    pixels = per_unit * BACKGROUND_SCALE
    half = STRIP_HEIGHT * nr_art.BACKGROUND_UNITS / STRIP_WIDTH / 2
    return (width, height), round((nr_art.STRIP_CENTRE_UNITS - half) * pixels), round((nr_art.STRIP_CENTRE_UNITS + half) * pixels)


def java_look(jar, catch_spec, art):
    """({resource: PNG}, the catch game's Java skin spec) of the Java '08 demo's look, each picture JAVA_OFFSET above the BREW one
    it stands in for: the frame's backdrop (its "SHS" tile, with its name bar above and below the strip), the relationship icons,
    the small pictures as time-badge icons, and the catch game's screen, header text, end panel and pictures (its skin is drawn
    by desktop_brew_catch). Java's pictures are about half BREW's size, so they go in at twice BREW's scale, and keep whole
    pixels. Java has no copy of BREW's house (166), which stays BREW's."""
    import brew_java
    jar_resources = brew_java.resources(jar)
    frames = brew_java.sheet(jar_resources[brew_java.UI_SHEET])
    lettering = brew_java.font(jar_resources[brew_java.OUTLINED_FONT])
    out = {}
    size, top, bottom = strip_edges()
    backdrop = brew_art.png(brew_java.backdrop(frames, size, top, bottom, BACKGROUND_SCALE).quantize(255))
    out[FRAME_BACKDROP + JAVA_OFFSET] = out[PINK_BACKDROP + JAVA_OFFSET] = backdrop
    margin = BADGE_MARGIN // 2
    for number, frame in enumerate((brew_java.HEART, brew_java.SKULL, brew_java.SMILEY)):
        picture = frames[frame].crop(frames[frame].getbbox())
        whole = Image.new('RGBA', (picture.width + 2 * margin, picture.height + 2 * margin), (0, 0, 0, 0))
        whole.paste(picture, (margin, margin))
        half = picture.width // 2
        broken = Image.new('RGBA', whole.size, (0, 0, 0, 0))
        broken.paste(picture.crop((0, 0, half, picture.height)), (margin - BROKEN_GAP // 4, margin))
        broken.paste(picture.crop((half, 0, picture.width, picture.height)), (margin + half + BROKEN_GAP // 4, margin))
        for base, image in ((BADGE_BASE + number, whole), (BADGE_BASE + 3 + number, broken)):
            out[base + JAVA_OFFSET] = brew_art.png(image.resize((image.width * BADGE_SCALE * 2, image.height * BADGE_SCALE * 2), Image.NEAREST))
    pairs = brew_java.pairs(small_pictures(art))
    for picture, index in pairs.items():
        image = brew_java.small_picture(jar_resources, index)
        big = image.resize((image.width * 8, image.height * 8), Image.NEAREST)
        scale = EVENT_ICON_SIZE / max(image.width * 2, image.height * 2)
        out[EVENT_ICON_BASE + picture + JAVA_OFFSET] = brew_art.png(
            big.resize((round(image.width * 2 * scale), round(image.height * 2 * scale)), Image.LANCZOS))

    def up(image, times=CATCH_SCALE):
        return brew_art.png(image.resize((image.width * times, image.height * times), Image.NEAREST))
    base = CATCH_BASE + JAVA_OFFSET
    out[base] = up(brew_java.catch_frame(frames))
    out[base + 1] = up(brew_java.text(lettering, 'SCORE: '))
    for digit in range(10):
        out[base + 2 + digit] = up(brew_java.text(lettering, str(digit)))
    out[base + 12] = up(brew_java.finished_panel(lettering))
    skin = dict(frame=base, label=base + 1, digits=list(range(base + 2, base + 12)), finished=base + 12, pictures={})
    for n, picture in enumerate(sorted(int(p) for p in catch_spec['pictures'])):
        if picture in pairs:
            image = brew_java.small_picture(jar_resources, pairs[picture])
            out[base + 14 + n] = up(image, CATCH_SCALE * 2)
            skin['pictures'][str(picture)] = [base + 14 + n, image.width * 2, image.height * 2]
    return out, skin


def small_pictures(art):
    """BREW's 56 small pictures (EVENT_ICONS at most 64 pixels a side), which Java's 56 pair with (brew_java.pairs)."""
    found = []
    for picture in EVENT_ICONS:
        try:
            left, top, right, bottom = art.bounds(picture)
        except Exception:
            continue
        if 0 < right - left <= 64 and 0 < bottom - top <= 64:
            found.append(picture)
    return found


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
