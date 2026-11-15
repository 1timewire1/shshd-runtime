"""Surviving Hollywood's full Chapter 1, *The Bright Lights* as the 240 x 320 1.0.2 demo plays it, as an SHS episode.

    python tools/translate/shw_full.py --jar DEMO_JAR --addon shshw.exp --out DIR

Phase 3 of the owner's plan (reference/Other Games/docs/SURVIVING_HOLLYWOOD_ADDON_PLAN.md; decisions settled 2026-11-14). The
1.0.2 jar holds 21 KiWi v1 scripts on the demo engine's own host ABI (SURVIVING_HOLLYWOOD_ENGINE.md section 3) and the game loop
around them in Java (`d.java`, section 3a; Tardy-Slip's `engine/shw.js` follows it). Here the scripts stay as they are, each an
SHS script of its own (SHS_SCRIPT), their host calls sent to SHS's services as shw_lite.py does 1.0.4's, and the loop is KiWi too:
a driver script (DRIVER, the episode's first) holding the schedule (resource 10000) as data and its state in saved numbers.

**The loop** (the driver: `map_turn`, `after_script`, `slept`, as engine/shw.js `mapTurn`, `afterScript`, `sleep`). The driver
runs a Hollywood script by setting its entry (ENTRY_KEY, read back by 9), queueing itself and then the script (SHS runs the queue
last in, first out) and halting, with PHASE_KEY saying where to carry on. Its state:
- the day (0-28) and slot (0-7: 8 AM, 9 AM, 12 PM, 3 PM, 6 PM, 9 PM, 12 AM, 3 AM; 7 is bedtime);
- where the player is, was and lives; a script left pending by 78 or 48; the story event running; the activity after it;
- whether the script that just ended set the clock (42/44) or left without spending time (50, 78).
On the map it runs a pending script, else the slot's forced event, else asks **Where to?**: SHS's choice of the places open now
(listed and the opening grid's entry above 0), each `District: Place`, then Quest Journal and Stats (owner, 2026-11-14). A place
runs the slot's story event if it isn't done (74), else the place kind's script after its travel card. After a script: a pending
one, the activity after a story event that left with 50, or the next slot; at bedtime home and the sleep script (10007), then the
next day under its date card.

**State**: the scripts' 103 globals are saved numbers (GLOBAL_BASE + n), their bit operations (27, 28, 51) worked out in KiWi
arithmetic (it has no bit instructions); places' listing (40, 41) and the cast's portraits (30, 31) likewise; the places
themselves (38: kind, background, district, name), the districts (37), the stats' names (58) and the schedule are the setup's
constants, read here by running the setup (`setup_tables`) and kept as data. Quests (66-69) are stored texts.

**Presentation** (the owner's decisions, 2026-11-14): a travel card is a time badge, `3:00 PM - The Flats: Home` (the demo's star
by day, its moon by night); each morning a date card, `Monday, February 2`; the stat-change panel (60) a `Stat changes` page that
waits, as the demo's; Stats in Where to? shows money and the three stats; relationships stay hidden; the status bar (79, 80) is
dropped; options the demo greys out (17) are left off the menu. The demo's numbers are kept.

**Not yet** (later Phase 3 steps): the minigames (61 word association, 62 spelling as SHS's word grid, 63-65 catch, the action
menus' routines as word games) are provisional stand-ins; the text is still the demo's lowercase; the add-on's sun icon and
minigame art.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import brew  # noqa: E402
import newrules  # noqa: E402
import shw  # noqa: E402
from brew import get_global, set_global, set_word  # noqa: E402
from exp_runtime.addons import RESOURCE as ADDON_RECORD, requires_bytes  # noqa: E402
from exp_runtime.decode.bytecode import decode_program  # noqa: E402
from exp_runtime.episode_version import RESOURCE as VERSION_RECORD, version_bytes  # noqa: E402
from exp_runtime.exp import Metadata, encode_exp  # noqa: E402
from exp_runtime.vm import KiwiVM, StopKind  # noqa: E402
from kiwi_rewrite import Rewriter  # noqa: E402

PACK, EPISODE, VERSION = 31700, 1, 1    # episode 1: the lite moves to 2 (owner, 2026-11-14)
TITLE, SUFFIX = 'The Bright Lights', ' (SHW)'
ADDON_REQUIRED = 4
DRIVER = 25001
SETUP_SCRIPT, SETUP_ENTRY, SCHEDULE = 10002, 32001, 10000
SLEEP_SCRIPT, QUEST_SCRIPT = 10007, 10005           # 49's, as 10002 names them (checked in setup_tables)
SCRIPTS = (*range(10002, 10018), *range(11000, 11008))


def shs_script(rid):
    """The SHS script number of the demo's script `rid`: 10002-10017 as 25002-25017, 11000-11007 as 25100-25107."""
    return rid + 15000 if rid < 11000 else rid + 14100


# Cast entries (10002's table, SURVIVING_HOLLYWOOD_ENGINE.md section 5).
PLAYER, EVENT = 0, 25
NAMED = {2: 'Advice Column', 35: 'Instructions', 52: 'Phone', 56: 'Reel Times'}     # no portrait (-1): a named box (76)
NARRATOR = 199
# Faces turned the other way: as the lite's and the Preview's, drawn looking away from the middle on the right (owner's rule,
# case by case; the full cast's sheet comes for review once it plays).
TURNED = frozenset({2006, 2034, 2042, 2048})       # Chelsea, Milan, the Secretary, The Jeff
NO_BADGE = 629                                       # SHS character key: 1 hides the relationship icon (owner: hidden)

# Saved numbers (owner 0). The lite's are 31701-31703.
(ENTRY_KEY, PHASE_KEY, DAY_KEY, SLOT_KEY, BED_KEY, HOME_KEY, HERE_KEY, PREVIOUS_KEY, PENDING_SCRIPT_KEY, PENDING_ENTRY_KEY,
 TIME_SET_KEY, STOPPED_KEY, AFTER_EVENT_KEY, EVENT_KEY, ACTIVITY_SCRIPT_KEY, ACTIVITY_ENTRY_KEY, BADGE_UP_KEY, RESULT_KEY,
 QUEST_COUNT_KEY, PICK_KEY, PLATE_KEY) = range(31710, 31731)
GLOBAL_BASE = 32000                     # + the script's global (0-102)
LISTED_BASE = 32200                     # + place: 1 while it's on the map
PORTRAIT_KEY = 32240                    # + cast entry: its demo portrait (30, 31)
MASK_BASE = 32320                       # + option: 1 while the next menu greys it out (17)
DONE_BASE = 32400                       # + story event: 1 once it's done (74)
STAT_CHANGES = (6, 7, 8)                # the globals holding each stat's change since the snapshot
MONEY = 0

# Driver phases: what the driver does when it next runs.
NEW_GAME, SET_UP, AFTER, SLEPT, JOURNAL = 0, 1, 2, 3, 4
SLOTS = 8
BED_SLOT = 7
SLOT_TIMES = ('8:00 AM', '9:00 AM', '12:00 PM', '3:00 PM', '6:00 PM', '9:00 PM', '12:00 AM', '3:00 AM')
DAY_SKY, NIGHT_SKY, SUNSET_SKY = 0, 1, 2            # brew's sky modes (shw.SKY_STRIPS)
SLOT_SKY = (DAY_SKY, DAY_SKY, DAY_SKY, DAY_SKY, SUNSET_SKY, NIGHT_SKY, NIGHT_SKY, NIGHT_SKY)    # engine/shw.js SLOT_SKY
NIGHT_SLOT = 5                          # the moon from 9 PM (SLOT_SKY's night)
MAP_DAY, MAP_NIGHT = 3008, 3009         # the map's music by day and by night (engine/shw.js mapTurn)
SOUND_CUES = frozenset({3006, 3010, 3014})      # the fail and success tones and the ringtone play over the music
JOURNAL_CUE = 3014
CITY = 1523                             # the city from the hills: the map (1100), the date and title cards
HOME_PICTURE = 1505
MAP_PICTURE = 1100
WHERE_TITLE = 'Where to?'
JOURNAL_OPTION, STATS_OPTION, BACK_OPTION = 100, 101, -1
JOURNAL_TITLE, STATS_TITLE, CHANGES_TITLE = 'Quest Journal', 'Stats', 'Stat changes'
JOURNAL_UPDATED = 'Quest journal updated'
MAX_QUESTS = 16
KEY_WORDS, OPTION_WORDS, BADGE_WORDS, TEXT_WORDS = 8, 100, 40, 400
WEEKDAYS = brew.WEEKDAYS
MONTHS = brew.MONTHS
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)     # engine/shw.js dateOf: no leap day
EMOTICONS = re.compile(rb' ?[{}\[\]]')
DEFAULT_NAME = 'Kate'
# The places' and districts' names as SHS shows them (the demo's fonts have no capitals). The lite's spellings where it has them.
DISTRICT_NAMES = {'downtown': 'Downtown', 'the flats': 'The Flats', 'entertainment strip': 'Entertainment Strip',
                  'studio central': 'Studio Central', 'the uplands': 'The Uplands', 'seaside': 'Seaside'}
PLACE_NAMES = {'airport': 'Airport', 'all-star-agents': 'All-Star-Agents', 'award ceremony': 'Award Ceremony',
               'basketball court': 'Basketball Court', 'city park': 'City Park', 'pet groomer job': 'Pet Groomer Job',
               'exec. asst. job': 'Exec. Asst. Job', 'advertising job': 'Advertising Job', 'lifeguard job': 'Lifeguard Job',
               'photo studio': 'Photo Studio', 'red carpet': 'Red Carpet', 'gym': 'Gym', 'home': 'Home',
               'beauty salon': 'Beauty Salon', 'club franken-stein': 'Club Franken-Stein', 'community theatre': 'Community Theatre',
               'diner': 'Diner', 'mall': 'Mall', 'vip room': 'VIP Room', 'backstage': 'Backstage', 'the beanstalk': 'The Beanstalk',
               'dressing room': 'Dressing Room', 'excess hollywood': 'Excess Hollywood', 'nice studio': 'Nice Studio',
               'recording studio': 'Recording Studio', 'chez expensif': 'Chez Expensif', 'party scene': 'Party Scene',
               'beach': 'Beach'}
STAT_NAMES = {'looks': 'Looks', 'body': 'Body', 'stress': 'Stress'}


def tidy(text):
    """A string of the script as SHS shows it: no emoticon glyphs; `$usr` as SHS's token `$USR`. Only text: brew.data_strings reads
    all of a script's data as strings, and the setup's tables (the cast's addresses and portraits, words under 0x2000) come out
    with control bytes, which leaves them alone (a `[` or `]` byte among them would otherwise shift the table)."""
    if any(b < 0x20 and b != 0x0a for b in text):
        return None
    changed = EMOTICONS.sub(b'', text).replace(b'$usr', b'$USR')
    return changed if changed != text else None


def string_at(words, address):
    out = bytearray()
    for w in words[address:address + 400]:
        for b in (w >> 8, w & 255):
            if b == 0:
                return bytes(out)
            out.append(b)
    return bytes(out)


def program_of(raw):
    return brew.rewrite_strings(decode_program(brew.upgrade(raw)), tidy)


# -- the setup's constants ---------------------------------------------------------------------------------------------------
def parse_schedule(data):
    """Table 10000 (Tardy-Slip data/shw-pack.js parseSchedule): the place kinds' scripts, the calendar, the opening grid (days x 7
    slots x kinds, the entry each kind's script starts at, 0 closed), story and forced events ((day x 7 + slot) -> entry)."""
    p = 0

    def s16():
        nonlocal p
        p += 2
        return struct.unpack_from('>h', data, p - 2)[0]

    def s8():
        nonlocal p
        p += 1
        return struct.unpack_from('>b', data, p - 1)[0]
    kinds = s16()
    scripts = [s16() for _ in range(kinds)]
    days = s16()
    weekday0, month0, date0 = s8(), s8(), s8()
    grid = list(struct.unpack_from(f'>{days * 7 * kinds}b', data, p))
    p += len(grid)

    def pairs():
        script, n = s16(), s16()
        return script, dict((s16(), s16()) for _ in range(n))
    story_script, story = pairs()
    forced_script, forced = pairs()
    if p != len(data):
        raise brew.StoryError(f'schedule: read {p} of {len(data)} bytes')
    return dict(kinds=kinds, scripts=scripts, days=days, weekday0=weekday0, month0=month0, date0=date0, grid=grid,
                story_script=story_script, story=story, forced_script=forced_script, forced=forced)


def setup_tables(raw):
    """Run 10002 at its New Game entry on the KiWi VM under a stub host, and keep what it defines: places (38: kind, name,
    background, district), districts (37), descriptions (47), stats (58), cast names and portraits (26, 31), the home (70) and the
    sleep and quest scripts (49)."""
    program = decode_program(brew.upgrade(raw))
    program = replace(program, main_words=program.main_words + (0,) * program.gap_count, gap_count=0)
    vm = KiwiVM(program)

    def read(address):
        out = bytearray()
        for k in range(400):
            w = vm.read_word(address + k) & 0xffff
            for b in (w >> 8, w & 255):
                if b == 0:
                    return out.decode('cp1252')
                out.append(b)
        return out.decode('cp1252')
    out = dict(places={}, districts={}, about={}, stats=[], cast={}, portraits={}, home=None, scripts=None)
    for _ in range(200000):
        stop = vm.run()
        if stop.kind == StopKind.HALT:
            break
        if stop.kind != StopKind.YIELD:
            raise brew.StoryError(f'the setup stopped: {stop}')
        service, a = stop.yield_id, [v - 65536 if v > 32767 else v for v in stop.args]
        result = 0
        if service == 9:
            result = SETUP_ENTRY
        elif service == 26:
            out['cast'][a[0]] = read(a[1])
        elif service == 31:
            out['portraits'][a[0]] = a[1]
        elif service == 37:
            out['districts'][a[0]] = read(a[1])
        elif service == 38:
            kind = a[1] & 255
            out['places'][a[0]] = dict(kind=kind - 256 if kind > 127 else kind, name=read(a[2]), background=a[3], district=a[4])
        elif service == 47:
            out['about'][a[0]] = read(a[1])
        elif service == 58:
            out['stats'] = [(a[k], read(a[k + 1])) for k in range(0, len(a) - 3, 4)]
        elif service == 70:
            out['home'] = a[0]
        elif service == 49:
            out['scripts'] = (a[0], a[1])
        vm.resume(result)
    else:
        raise brew.StoryError('the setup did not finish')
    if out['scripts'] != (SLEEP_SCRIPT, QUEST_SCRIPT):
        raise brew.StoryError(f'the setup names the sleep and quest scripts {out["scripts"]}')
    if [i for i, _ in out['stats']] != [1, 2, 3]:
        raise brew.StoryError(f'the setup defines the stats {out["stats"]}')
    return out


def date_texts(schedule):
    """`Sunday, February 1` for each day (engine/shw.js dateOf: the demo's February has 28 days)."""
    out, month, date = [], schedule['month0'], schedule['date0']
    for day in range(schedule['days'] + 1):
        out.append(f'{WEEKDAYS[(day + schedule["weekday0"]) % 7]}, {MONTHS[month - 1]} {date}')
        date += 1
        if date > MONTH_DAYS[month - 1]:
            date, month = 1, month % 12 + 1
    return out


class Story:
    """What every script's translation shares: the setup's constants and the schedule."""

    def __init__(self, resources, spec):
        self.spec = spec
        self.schedule = parse_schedule(resources[SCHEDULE])
        self.setup = setup_tables(resources[SETUP_SCRIPT])
        places = self.setup['places']
        self.place_count = max(places) + 1
        self.labels = {}
        for i, place in places.items():
            district = self.setup['districts'][place['district']]
            self.labels[i] = f'{DISTRICT_NAMES[district]}: {PLACE_NAMES[place["name"]]}'
        self.dates = date_texts(self.schedule)
        sched = self.schedule
        self.months = [int(MONTHS.index(t.split(', ')[1].split(' ')[0]) + 1) for t in self.dates]
        self.day_dates = [int(t.rsplit(' ', 1)[1]) for t in self.dates]
        if self.setup['home'] is None or sched['story_script'] != 10015 or sched['forced_script'] != 10014:
            raise brew.StoryError('the schedule is not the 1.0.2 demo\'s')


# -- shared emitters -----------------------------------------------------------------------------------------------------------
def dyn_get(s, base, index):
    s.push(base); index(); s.emit(0x50); s.call(55, 1); s.push_result()


def dyn_set(s, base, index, value):
    s.push(base); index(); s.emit(0x50); value(); s.call(54, 2)


def set_result(s, value):
    set_global(s, RESULT_KEY, value)
    s.push(RESULT_KEY); s.call(55, 1)


def push_shs_script(s, rid):
    """Push the SHS script number of the demo script `rid()` pushes."""
    low, done = s.label(), s.label()
    rid(); s.push(11000); s.emit(0x0e); s.jump_if_nonzero(low)
    rid(); s.push(14100); s.emit(0x50); s.jump(done)
    s.label(low)
    rid(); s.push(15000); s.emit(0x50)
    s.label(done)


def table_get(s, table, index):
    s.push(table); index(); s.emit(0x50); s.emit(0x3f)


def clear_badge(s):
    done = s.label()
    get_global(s, BADGE_UP_KEY); s.jump_if_zero(done)
    s.push(-1); s.push(-1); s.call(90, 2)
    set_global(s, BADGE_UP_KEY, lambda: s.push(0))
    s.label(done)


def push_face(s, portrait):
    """Push the shshw picture for the demo portrait `portrait()` pushes: turned for TURNED, -1 for none (negative)."""
    end, none = s.label(), s.label()
    portrait(); s.push(0); s.emit(0x0e); s.jump_if_nonzero(none)
    for p in sorted(TURNED):
        other = s.label()
        portrait(); s.push(p); s.emit(0x0a); s.jump_if_zero(other)
        s.push(shw.FLIPPED_BASE + p - 2000); s.jump(end)
        s.label(other)
    portrait(); s.push(shw.PORTRAIT_BASE - 2000); s.emit(0x50); s.jump(end)
    s.label(none)
    s.push(-1)
    s.label(end)


def music(s, cue):
    """The demo's cue `cue()` pushes: the tones as sounds (79), the rest as music (80)."""
    sound, done = s.label(), s.label()
    for c in sorted(SOUND_CUES):
        cue(); s.push(c); s.emit(0x0a); s.jump_if_nonzero(sound)
    cue(); s.push(shw.MUSIC_BASE - 3000); s.emit(0x50); s.push(0); s.call(80, 2); s.jump(done)
    s.label(sound)
    cue(); s.push(shw.MUSIC_BASE - 3000); s.emit(0x50); s.call(79, 1)
    s.label(done)


def snapshot(s):
    """d.l(): the stats' change counters cleared."""
    for g in STAT_CHANGES:
        set_global(s, GLOBAL_BASE + g, lambda: s.push(0))


class Tables:
    """A program's copies of the tables the place and time code reads (each script's memory is its own)."""

    def __init__(self, rewriter, story):
        self.r, self.story = rewriter, story
        self._cache = {}

    def _get(self, name, build):
        if name not in self._cache:
            self._cache[name] = build()
        return self._cache[name]

    def labels(self):
        st = self.story
        return self._get('labels', lambda: self.r.words([self.r.text(st.labels.get(i, '')) for i in range(st.place_count)]))

    def pictures(self):
        """Each place's background, at sky 0 (the sky mode is added)."""
        st = self.story

        def build():
            out = []
            for i in range(st.place_count):
                bg = st.setup['places'].get(i, {}).get('background', HOME_PICTURE)
                out.append(shw.BACKGROUND_BASE + shw.SKY_MODES * (bg - 1500))
            return self.r.words(out)
        return self._get('pictures', build)

    def skies(self):
        return self._get('skies', lambda: self.r.words(list(SLOT_SKY)))

    def times(self):
        return self._get('times', lambda: self.r.words([self.r.text(t) for t in SLOT_TIMES]))

    def dates(self):
        return self._get('dates', lambda: self.r.words([self.r.text(t) for t in self.story.dates]))

    def months(self):
        return self._get('months', lambda: self.r.words(self.story.months))

    def day_dates(self):
        return self._get('day_dates', lambda: self.r.words(self.story.day_dates))

    def badge(self):
        return self._get('badge', lambda: self.r.words([0] * BADGE_WORDS))

    def key(self):
        return self._get('key', lambda: self.r.words([0] * KEY_WORDS))

    def option(self):
        return self._get('option', lambda: self.r.words([0] * OPTION_WORDS))

    def text(self):
        return self._get('text', lambda: self.r.words([0] * TEXT_WORDS))

    def powers(self):
        return self._get('powers', lambda: self.r.words([1 << b if b < 15 else -32768 for b in range(16)]))


def background(s, tables, place):
    """The place's background at the slot's sky."""
    s.push(0)
    table_get(s, tables.pictures(), place); table_get(s, tables.skies(), lambda: get_global(s, SLOT_KEY)); s.emit(0x50)
    s.call(11, 2)


def picture(s, tables, picture_id):
    """A demo background `picture_id()` pushes (15xx; the map, 1100, as the city) at the slot's sky."""
    city, done = s.label(), s.label()
    s.push(0)
    picture_id(); s.push(MAP_PICTURE); s.emit(0x0a); s.jump_if_nonzero(city)
    picture_id(); s.push(1500); s.emit(0x51); s.push(shw.SKY_MODES); s.emit(0x52); s.push(shw.BACKGROUND_BASE); s.emit(0x50)
    s.jump(done)
    s.label(city)
    s.push(shw.BACKGROUND_BASE + shw.SKY_MODES * (CITY - 1500))
    s.label(done)
    table_get(s, tables.skies(), lambda: get_global(s, SLOT_KEY)); s.emit(0x50)
    s.call(11, 2)


def card(s, tables, place):
    """The travel card: the place's background, and a badge `3:00 PM - The Flats: Home` (the star by day, the moon by night),
    cleared after the next line."""
    background(s, tables, place)
    s.push(tables.badge()); s.text('%s - %s')
    table_get(s, tables.times(), lambda: get_global(s, SLOT_KEY))
    table_get(s, tables.labels(), place)
    s.call(22, 4)
    moon, icon = s.label(), s.label()
    get_global(s, SLOT_KEY); s.push(NIGHT_SLOT); s.emit(0x0d); s.jump_if_nonzero(moon)
    s.push(shw.STAR_BADGE); s.jump(icon)
    s.label(moon)
    s.push(shw.MOON)
    s.label(icon)
    s.push(tables.badge()); s.call(90, 2)
    set_global(s, BADGE_UP_KEY, lambda: s.push(1))


def move_to(s, place):
    set_global(s, PREVIOUS_KEY, lambda: get_global(s, HERE_KEY))
    set_global(s, HERE_KEY, place)


def quest_key(s, tables, form, quest):
    """Write the stored-text key `form % quest()` into the key buffer, and push the buffer."""
    s.push(tables.key()); s.text(form); quest(); s.call(22, 3)
    s.push(tables.key())


def stored(s, tables, form, quest, slot=-1):
    """Push a handle to the stored text under `form % quest()` (empty if unset), in runtime string slot `slot` (-1, -2...)."""
    quest_key(s, tables, form, quest); s.text(''); s.push(slot); s.call(47, 3); s.push_result()


QUEST_TITLE, QUEST_LINES = '$SHWQT%d', '$SHWQL%d'


def stat_page(s, tables, title, value, signed):
    """A page `title` of money (unless signed) and the three stats: each `Name value`, `+` before a rise when `signed`."""
    names = [STAT_NAMES.get(n, n) for n in ('looks', 'body', 'stress')]
    lines = [] if signed else ['Money: $%d']
    lines += [f'{n}: %s%d' if signed else f'{n}: %d' for n in names]
    s.push(tables.text()); s.text('\n'.join(lines))
    if not signed:
        get_global(s, GLOBAL_BASE + MONEY)
    for k, g in enumerate(STAT_CHANGES if signed else (1, 2, 3)):
        if signed:
            plus, sign = s.label(), s.label()
            get_global(s, GLOBAL_BASE + g); s.push(0); s.emit(0x0c); s.jump_if_nonzero(plus)
            s.text(''); s.jump(sign)
            s.label(plus)
            s.text('+')
            s.label(sign)
        get_global(s, GLOBAL_BASE + g)
    s.call(22, 2 + (6 if signed else 4))
    s.text(title); s.push(tables.text()); s.push(0); s.call(33, 3)


# -- a script's host calls -----------------------------------------------------------------------------------------------------
class Script:
    def __init__(self, rid, raw, story):
        self.rid, self.story = rid, story
        self.program = program_of(raw)
        self.words = self.program.main_words
        self.r = Rewriter(self.program, zero_gap=True)
        self.t = Tables(self.r, story)

    def constant(self, pc, argc):
        return newrules.pushed_values(self.program, pc, argc)

    # lines and boxes
    def line(self, pc, argc):
        """16: (speaker, text). Event is the narrator (a line wholly in brackets loses them); a cast entry with no portrait and
        a name of its own (NAMED) speaks in a named box; anyone else's line wholly in brackets is a thought (13's -2 mode)."""
        speaker, address = self.constant(pc, 2)
        text = string_at(self.words, address) if address is not None else None
        whole = text is not None and text.startswith(b'(') and text.endswith(b')') and text.count(b'(') == 1
        bare = self.r.text(text[1:-1].decode('cp1252')) if whole else None
        if speaker == EVENT:
            def build(s):
                (s.push(bare) if whole else s.arg(2)); s.push(NARRATOR); s.call(13, 2)
                clear_badge(s); s.result(0)
            key = ('narration', bare)
        elif speaker in NAMED:
            def build(s):
                s.text(NAMED[speaker]); s.arg(2); s.call(76, 2)
                clear_badge(s); s.result(0)
            key = ('named', speaker)
        elif whole and speaker is not None:
            def build(s):
                s.push(-2); s.push(bare); s.arg(1); s.push(0); s.call(13, 4)
                clear_badge(s); s.result(0)
            key = ('thought', bare)
        else:
            def build(s):
                narration, named, done = s.label(), s.label(), s.label()
                s.arg(1); s.push(EVENT); s.emit(0x0a); s.jump_if_nonzero(narration)
                for entry, name in NAMED.items():
                    other = s.label()
                    s.arg(1); s.push(entry); s.emit(0x0a); s.jump_if_zero(other)
                    s.text(name); s.arg(2); s.call(76, 2); s.jump(done)
                    s.label(other)
                s.arg(2); s.arg(1); s.push(0); s.call(13, 3); s.jump(done)
                s.label(narration)
                s.arg(2); s.push(NARRATOR); s.call(13, 2)
                s.label(done)
                clear_badge(s); s.result(0)
            key = 'line'
        self.r.redirect(pc, key, build)

    def plate(self, pc, argc):
        """14: (text) the name plate for the page that follows (15): kept, as the text's address."""
        self.r.redirect(pc, 'plate', lambda s: (set_global(s, PLATE_KEY, lambda: s.arg(1)), s.result(0)))

    def page(self, pc, argc):
        """15: (text) a page in the dialogue box: a named box under 14's plate."""
        def build(s):
            get_global(s, PLATE_KEY); s.arg(1); s.call(76, 2)
            clear_badge(s); s.result(0)
        self.r.redirect(pc, 'page', build)

    def menu(self, pc, argc):
        """18: (title, `a|b|c`, speaker, timer ms): SHS's choice, its answer the option's index. With options greyed out (17), SHS's
        choice builder (2-4) with only the others, each answering its own index (owner, 2026-11-14: left off the menu)."""
        def build(s):
            title, built, done = s.label(), s.label(), s.label()
            other = s.label()
            s.arg(1); s.text('you'); s.call(24, 2); s.push_result(); s.jump_if_zero(other)
            s.text(brew.CHOICE_TITLE); s.jump(title)
            s.label(other)
            s.arg(1)
            s.label(title)
            s.push(0)                                       # local 0: the title; local 1: any option greyed
            for k in range(16):
                s.emit(0x23, 1); s.emit(0x41, 1); get_global(s, MASK_BASE + k); s.emit(0x11); s.emit(0x3e); s.emit(0x15)
            s.emit(0x41, 1); s.jump_if_nonzero(built)
            s.emit(0x41, 0); s.arg(2); s.push(-1); s.arg(4); s.push(0); s.arg(3); s.push(-1); s.push(brew.CHOICE_PORTRAIT)
            s.call(1, 8); s.jump(done)
            s.label(built)
            s.emit(0x41, 0); s.push(-1); s.arg(4); s.push(0); s.arg(3); s.push(brew.CHOICE_PORTRAIT); s.call(2, 6)
            self.each_option(s, lambda: s.arg(2), lambda k: (
                dyn_get(s, MASK_BASE, k), s.jump_if_nonzero('skip'),
                s.push(self.t.option()), k(), s.push(1), s.call(3, 3)))
            s.push(0); s.call(4, 1)
            s.label(done)
            s.push_result()                                 # local 2: the answer
            for k in range(16):
                set_global(s, MASK_BASE + k, lambda: s.push(0))
            set_result(s, lambda: s.emit(0x41, 2))
        self.r.redirect(pc, 'menu', build)

    def each_option(self, s, options, body):
        """For each `|`-separated option of the string `options()` pushes (a trailing blank one dropped, as i.a): its text copied
        into the option buffer (OPTION_WORDS words, cut there), then `body(k)` with `k()` pushing its index. In `body`, a jump to the
        label 'skip' goes to the next option. Uses locals 2-5 (byte, option, the option's length, the byte read)."""
        buf = self.t.option()
        top, end, copy, emit_option, after = s.label(), s.label(), s.label(), s.label(), s.label()
        s.push(0); s.push(0); s.push(0); s.push(0)        # locals 2-5
        s.label(top)
        # local 5 = byte local 2 of the options
        s.emit(0x23, 5)
        options(); s.emit(0x41, 2); s.push(2); s.emit(0x53); s.emit(0x50); s.emit(0x3f)
        odd, got, positive = s.label(), s.label(), s.label()
        s.emit(0x41, 2); s.push(2); s.emit(0x54); s.jump_if_nonzero(odd)
        s.emit(0x1c); s.push(0); s.emit(0x0e); s.jump_if_zero(positive)
        s.push(1); s.emit(0x50); s.push(256); s.emit(0x53); s.push(1); s.emit(0x51); s.jump(got)
        s.label(positive)
        s.push(256); s.emit(0x53); s.jump(got)
        s.label(odd)
        s.push(256); s.emit(0x54)
        s.label(got)
        # a byte from 0x80 up comes out negative: back to 0-255 (high bytes divide toward zero, so (w + 1) / 256 - 1 is the
        # floor for a negative word w)
        fix = s.label()
        s.emit(0x1c); s.push(0); s.emit(0x0e); s.jump_if_zero(fix)
        s.push(256); s.emit(0x50)
        s.label(fix)
        s.emit(0x3e); s.emit(0x15)
        s.emit(0x41, 5); s.push(ord('|')); s.emit(0x0a); s.jump_if_nonzero(emit_option)
        s.emit(0x41, 5); s.jump_if_zero(emit_option)
        # append the byte (when there's room)
        s.emit(0x41, 4); s.push(OPTION_WORDS * 2 - 2); s.emit(0x0d); s.jump_if_nonzero(copy)
        high, stored_ = s.label(), s.label()
        s.emit(0x41, 4); s.push(2); s.emit(0x54); s.jump_if_zero(high)
        s.push(buf); s.emit(0x41, 4); s.push(2); s.emit(0x53); s.emit(0x50)
        s.push(buf); s.emit(0x41, 4); s.push(2); s.emit(0x53); s.emit(0x50); s.emit(0x3f)
        s.emit(0x41, 5); s.emit(0x50); s.emit(0x3e); s.emit(0x15); s.jump(stored_)
        s.label(high)
        s.push(buf); s.emit(0x41, 4); s.push(2); s.emit(0x53); s.emit(0x50)
        s.emit(0x41, 5); s.push(256); s.emit(0x52); s.emit(0x3e); s.emit(0x15)
        s.label(stored_)
        s.emit(0x23, 4); s.emit(0x41, 4); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.label(copy)
        s.emit(0x23, 2); s.emit(0x41, 2); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.jump(top)
        s.label(emit_option)
        # terminate the option's text; an empty last option is dropped
        last_blank = s.label()
        self._terminate(s, buf)
        s.emit(0x41, 5); s.jump_if_nonzero(last_blank)
        s.emit(0x41, 4); s.jump_if_zero(end)
        s.label(last_blank)
        body(lambda: s.emit(0x41, 3))
        s.label('skip')
        s.emit(0x23, 3); s.emit(0x41, 3); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.emit(0x23, 4); s.push(0); s.emit(0x3e); s.emit(0x15)
        s.emit(0x41, 5); s.jump_if_zero(end)
        s.emit(0x23, 2); s.emit(0x41, 2); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
        s.jump(top)
        s.label(end)
        s.emit(0x15); s.emit(0x15); s.emit(0x15); s.emit(0x15)

    def _terminate(self, s, buf):
        """The NUL after the option's local 4 bytes: a zero word when they're even (an odd count ends on a high byte, whose
        word's low byte is already 0)."""
        done = s.label()
        s.emit(0x41, 4); s.push(2); s.emit(0x54); s.jump_if_nonzero(done)
        s.push(buf); s.emit(0x41, 4); s.push(2); s.emit(0x53); s.emit(0x50); s.push(0); s.emit(0x3e); s.emit(0x15)
        s.label(done)

    def mask(self, pc, argc):
        """17: (option) grey it out in the next menu."""
        self.r.redirect(pc, 'mask', lambda s: (dyn_set(s, MASK_BASE, lambda: s.arg(1), lambda: s.push(1)), s.result(0)))

    def action_menu(self, pc, argc):
        """20: (title, options, interval ms, timer ms, speaker). Provisional (the minigame step makes the routines word games):
        SHS's choice with the timer."""
        def build(s):
            s.arg(1); s.arg(2); s.push(-1); s.arg(4); s.push(0); s.arg(5); s.push(-1); s.push(brew.CHOICE_PORTRAIT)
            s.call(1, 8)
        self.r.redirect(pc, 'action_menu', build)

    def provisional_game(self, pc, argc):
        """61-65: provisional until the minigame step: no game, 0."""
        self.r.redirect(pc, ('provisional', self.r.code[pc][1] >> 8), lambda s: s.result(0))

    def name_entry(self, pc, argc):
        """19: (title, initial): SHS's text entry (17), the answer kept for 7 (as shw_lite)."""
        def build(s):
            s.arg(1); s.text(''); s.arg(2); s.call(17, 3)
            s.push_result()
            s.text('$SHWENTRY'); s.emit(0x41, 0); s.call(46, 2)
            s.result(0)
        self.r.redirect(pc, 'name_entry', build)

    def entry_text(self, pc, argc):
        def build(s):
            s.text('$SHWENTRY'); s.text(''); s.push(-1); s.call(47, 3); s.push_result()
            s.arg(1); s.text('%s'); s.emit(0x41, 0); s.call(22, 3)
            s.result(0)
        self.r.redirect(pc, 'entry_text', build)

    def token_get(self, pc, argc):
        """25: (`$KEY`, destination): a stored text; `$USR` is DEFAULT_NAME until the player names herself."""
        def build(s):
            user, read = s.label(), s.label()
            s.arg(1); s.text('$USR'); s.call(24, 2); s.push_result(); s.jump_if_nonzero(user)
            s.arg(1); s.text(''); s.push(-1); s.call(47, 3); s.push_result(); s.jump(read)
            s.label(user)
            s.arg(1); s.text(DEFAULT_NAME); s.push(-1); s.call(47, 3); s.push_result()
            s.label(read)
            s.arg(2); s.text('%s'); s.emit(0x41, 0); s.call(22, 3)
            s.result(0)
        self.r.redirect(pc, 'token_get', build)

    def photo(self, pc, argc):
        """21: (count, list of cast entries): SHS's portrait picker (78) over their faces."""
        self.r.redirect(pc, 'photo', lambda s: (s.text(brew.PORTRAIT_TITLE), s.arg(1), s.arg(2), s.call(78, 3)))

    def cast_picture(self, pc, argc):
        """30: (entry) its portrait."""
        self.r.redirect(pc, 'cast_picture', lambda s: (s.push(PORTRAIT_KEY), s.arg(1), s.emit(0x50), s.call(55, 1)))

    def set_picture(self, pc, argc):
        """31: (entry, portrait): kept for 30, and the entry's face (72)."""
        def build(s):
            dyn_set(s, PORTRAIT_KEY, lambda: s.arg(1), lambda: s.arg(2))
            s.arg(1); push_face(s, lambda: s.arg(2)); s.call(72, 2)
            s.arg(1); s.push(NO_BADGE); s.push(1); s.call(52, 3)
            s.result(0)
        self.r.redirect(pc, 'set_picture', build)

    # the clock, places and globals
    def sprintf(self, pc, argc):
        """1: (dest, format, values...) SHS's 22, returning dest (scripts pass it straight on)."""
        def build(s):
            for i in range(1, argc + 1):
                s.arg(i)
            s.call(22, argc)
            set_result(s, lambda: s.arg(1))
        self.r.redirect(pc, 'sprintf', build)

    def global_set(self, pc, argc):
        self.r.redirect(pc, 'global_set', lambda s: (dyn_set(s, GLOBAL_BASE, lambda: s.arg(1), lambda: s.arg(2)), s.result(0)))

    def global_get(self, pc, argc):
        self.r.redirect(pc, 'global_get', lambda s: (s.push(GLOBAL_BASE), s.arg(1), s.emit(0x50), s.call(55, 1)))

    def global_clear(self, pc, argc):
        self.r.redirect(pc, 'global_clear', lambda s: (dyn_set(s, GLOBAL_BASE, lambda: s.arg(1), lambda: s.push(0)), s.result(0)))

    def bit_of(self, s, value, bit):
        """Push bit `bit()` of the 16-bit `value()` (no bit instructions: the top bit is the sign, the rest by division)."""
        top, negative, divide, end = s.label(), s.label(), s.label(), s.label()
        bit(); s.push(15); s.emit(0x0a); s.jump_if_zero(top)
        value(); s.push(0); s.emit(0x0e); s.jump(end)
        s.label(top)
        value(); s.push(0); s.emit(0x0e); s.jump_if_zero(negative)
        value(); s.push(-32768); s.emit(0x51); s.jump(divide)
        s.label(negative)
        value()
        s.label(divide)
        table_get(s, self.t.powers(), bit); s.emit(0x53); s.push(2); s.emit(0x54)
        s.label(end)

    def bit_set(self, pc, argc):
        """27: (global, bit, 0|1)."""
        def build(s):
            value = lambda: dyn_get(s, GLOBAL_BASE, lambda: s.arg(1))       # noqa: E731
            on, done = s.label(), s.label()
            s.arg(3); s.push(1); s.emit(0x0a); s.jump_if_nonzero(on)
            self.bit_of(s, value, lambda: s.arg(2)); s.jump_if_zero(done)
            dyn_set(s, GLOBAL_BASE, lambda: s.arg(1), lambda: (value(), table_get(s, self.t.powers(), lambda: s.arg(2)), s.emit(0x51)))
            s.jump(done)
            s.label(on)
            self.bit_of(s, value, lambda: s.arg(2)); s.jump_if_nonzero(done)
            dyn_set(s, GLOBAL_BASE, lambda: s.arg(1), lambda: (value(), table_get(s, self.t.powers(), lambda: s.arg(2)), s.emit(0x50)))
            s.label(done)
            s.result(0)
        self.r.redirect(pc, 'bit_set', build)

    def bit_get(self, pc, argc):
        """28: (global, bit)."""
        self.r.redirect(pc, 'bit_get', lambda s: (
            self.bit_of(s, lambda: dyn_get(s, GLOBAL_BASE, lambda: s.arg(1)), lambda: s.arg(2)),     # local 0
            set_result(s, lambda: s.emit(0x41, 0))))

    def random_bit(self, pc, argc):
        """51: (global, n, take, refill): a random clear bit of the global's low n bits (-1 if none), set if `take`; with
        `refill`, the global cleared and tried again when none is clear (engine/shw.js)."""
        def build(s):
            value = lambda: dyn_get(s, GLOBAL_BASE, lambda: s.arg(1))       # noqa: E731
            again, count, counted, none, find, found, done = (s.label() for _ in range(7))
            s.push(0); s.push(0); s.push(0)                 # locals 0 bit, 1 free count, 2 the pick
            s.label(again)
            s.emit(0x23, 0); s.push(0); s.emit(0x3e); s.emit(0x15)
            s.emit(0x23, 1); s.push(0); s.emit(0x3e); s.emit(0x15)
            s.label(count)
            s.emit(0x41, 0); s.arg(2); s.emit(0x0e); s.jump_if_zero(counted)
            skip = s.label()
            self.bit_of(s, value, lambda: s.emit(0x41, 0)); s.jump_if_nonzero(skip)
            s.emit(0x23, 1); s.emit(0x41, 1); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
            s.label(skip)
            s.emit(0x23, 0); s.emit(0x41, 0); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
            s.jump(count)
            s.label(counted)
            s.emit(0x41, 1); s.jump_if_zero(none)
            s.emit(0x23, 2); s.emit(0x41, 1); s.call(27, 1); s.push_result(); s.emit(0x3e); s.emit(0x15)
            s.emit(0x23, 0); s.push(0); s.emit(0x3e); s.emit(0x15)
            s.label(find)
            used = s.label()
            self.bit_of(s, value, lambda: s.emit(0x41, 0)); s.jump_if_nonzero(used)
            s.emit(0x41, 2); s.jump_if_zero(found)
            s.emit(0x23, 2); s.emit(0x41, 2); s.push(1); s.emit(0x51); s.emit(0x3e); s.emit(0x15)
            s.label(used)
            s.emit(0x23, 0); s.emit(0x41, 0); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
            s.jump(find)
            s.label(found)
            take = s.label()
            s.arg(3); s.push(1); s.emit(0x0a); s.jump_if_zero(take)
            dyn_set(s, GLOBAL_BASE, lambda: s.arg(1), lambda: (value(), table_get(s, self.t.powers(), lambda: s.emit(0x41, 0)),
                                                                 s.emit(0x50)))
            s.label(take)
            set_result(s, lambda: s.emit(0x41, 0)); s.jump(done)
            s.label(none)
            stay = s.label()
            s.arg(4); s.push(1); s.emit(0x0a); s.jump_if_zero(stay)
            s.arg(2); s.jump_if_zero(stay)
            dyn_set(s, GLOBAL_BASE, lambda: s.arg(1), lambda: s.push(0)); s.jump(again)
            s.label(stay)
            s.result(-1)
            s.label(done)
        self.r.redirect(pc, 'random_bit', build)

    def place_define(self, pc, argc):
        """38: (place, kind, ...): listed while its kind is 0 or more (the rest of it is the setup's constants)."""
        def build(s):
            dyn_set(s, LISTED_BASE, lambda: s.arg(1), lambda: (s.arg(2), s.push(0), s.emit(0x0d), s.arg(2), s.push(128),
                                                               s.emit(0x0e), s.emit(0x12)))
            s.result(0)
        self.r.redirect(pc, 'place_define', build)

    def unlist(self, pc, argc):
        self.r.redirect(pc, 'unlist', lambda s: (dyn_set(s, LISTED_BASE, lambda: s.arg(1), lambda: s.push(0)), s.result(0)))

    def relist(self, pc, argc):
        self.r.redirect(pc, 'relist', lambda s: (dyn_set(s, LISTED_BASE, lambda: s.arg(1), lambda: s.push(1)), s.result(0)))

    def keyed_get(self, pc, argc, key, name):
        self.r.redirect(pc, name, lambda s: (s.push(key), s.call(55, 1)))

    def keyed_set(self, pc, argc, keys, name):
        self.r.redirect(pc, name, lambda s: ([set_global(s, k, v(s)) for k, v in keys], s.result(0)))

    def here(self, pc, argc):
        self.keyed_get(pc, argc, HERE_KEY, 'here')

    def slot(self, pc, argc):
        self.keyed_get(pc, argc, SLOT_KEY, 'slot')

    def day(self, pc, argc):
        self.keyed_get(pc, argc, DAY_KEY, 'day')

    def home_get(self, pc, argc):
        self.keyed_get(pc, argc, HOME_KEY, 'home_get')

    def entry(self, pc, argc):
        self.keyed_get(pc, argc, ENTRY_KEY, 'entry')

    def set_slot(self, pc, argc):
        self.keyed_set(pc, argc, [(SLOT_KEY, lambda s: lambda: s.arg(1)), (TIME_SET_KEY, lambda s: lambda: s.push(1))], 'set_slot')

    def set_day(self, pc, argc):
        self.keyed_set(pc, argc, [(DAY_KEY, lambda s: lambda: s.arg(1)), (TIME_SET_KEY, lambda s: lambda: s.push(1))], 'set_day')

    def home_set(self, pc, argc):
        self.keyed_set(pc, argc, [(HOME_KEY, lambda s: lambda: s.arg(1))], 'home_set')

    def weekday(self, pc, argc):
        wd = self.story.schedule['weekday0']
        self.r.redirect(pc, 'weekday', lambda s: set_result(s, lambda: (get_global(s, DAY_KEY), s.push(wd), s.emit(0x50),
                                                                         s.push(7), s.emit(0x54))))

    def days(self, pc, argc):
        self.r.redirect(pc, 'days', lambda s: s.result(self.story.schedule['days']))

    def month(self, pc, argc):
        self.r.redirect(pc, 'month', lambda s: set_result(s, lambda: table_get(s, self.t.months(), lambda: get_global(s, DAY_KEY))))

    def date(self, pc, argc):
        self.r.redirect(pc, 'date', lambda s: set_result(s, lambda: table_get(s, self.t.day_dates(),
                                                                               lambda: get_global(s, DAY_KEY))))

    def goto(self, pc, argc):
        """45: (place, card): there, its background at the slot's sky, with the travel card's badge if card > 0."""
        def build(s):
            plain, done = s.label(), s.label()
            move_to(s, lambda: s.arg(1))
            s.arg(2); s.push(0); s.emit(0x0c); s.jump_if_zero(plain)
            card(s, self.t, lambda: s.arg(1)); s.jump(done)
            s.label(plain)
            background(s, self.t, lambda: s.arg(1))
            s.label(done)
            s.result(0)
        self.r.redirect(pc, 'goto', build)

    def card_here(self, pc, argc):
        """46: the travel card of the place you're at."""
        self.r.redirect(pc, 'card_here', lambda s: (card(s, self.t, lambda: get_global(s, HERE_KEY)), s.result(0)))

    def scene(self, pc, argc):
        """13: (picture) a background, at the slot's sky."""
        self.r.redirect(pc, 'scene', lambda s: (picture(s, self.t, lambda: s.arg(1)), s.result(0)))

    def title_bar(self, pc, argc):
        """72: (text) the location's title bar (`car`, `hollywood streets`): a badge with the demo's star, cleared after the next
        line."""
        def build(s):
            s.push(shw.STAR_BADGE); s.arg(1); s.call(90, 2)
            set_global(s, BADGE_UP_KEY, lambda: s.push(1))
            s.result(0)
        self.r.redirect(pc, 'title_bar', build)

    def chapter(self, pc, argc):
        """73: (`chapter 1`, `the bright lights`): SHS's title card, the story's name over the chapter's."""
        p = shw.BACKGROUND_BASE + shw.SKY_MODES * (CITY - 1500) + SUNSET_SKY
        self.r.redirect(pc, 'chapter', lambda s: (s.text(TITLE), s.text('Chapter 1'), s.push(p), s.push(0), s.call(8, 4),
                                                  s.result(0)))

    def sound(self, pc, argc):
        self.r.redirect(pc, 'sound', lambda s: (music(s, lambda: s.arg(1)), s.result(0)))

    def end_day(self, pc, argc):
        """48: (script, entry): remember the script for the next turn (if 0 or more), global 12 the slot, bedtime. Carries on."""
        def build(s):
            none = s.label()
            s.arg(1); s.push(0); s.emit(0x0e); s.jump_if_nonzero(none)
            set_global(s, PENDING_SCRIPT_KEY, lambda: push_shs_script(s, lambda: s.arg(1)))
            set_global(s, PENDING_ENTRY_KEY, lambda: s.arg(2))
            s.label(none)
            set_global(s, GLOBAL_BASE + 12, lambda: get_global(s, SLOT_KEY))
            set_global(s, BED_KEY, lambda: (get_global(s, SLOT_KEY), s.push(1), s.emit(0x50)))
            set_global(s, SLOT_KEY, lambda: s.push(BED_SLOT))
            s.result(0)
        self.r.redirect(pc, 'end_day', build)

    def leave(self, pc, argc):
        """50: leave without spending time: the script ends."""
        self.r.redirect(pc, 'leave', lambda s: (set_global(s, STOPPED_KEY, lambda: s.push(1)), s.emit(0x33)))

    def chain(self, pc, argc):
        """78: (script, entry, checkpoint): run that script next; this one ends."""
        def build(s):
            set_global(s, PENDING_SCRIPT_KEY, lambda: push_shs_script(s, lambda: s.arg(1)))
            set_global(s, PENDING_ENTRY_KEY, lambda: s.arg(2))
            set_global(s, STOPPED_KEY, lambda: s.push(1))
            s.emit(0x33)
        self.r.redirect(pc, 'chain', build)

    def done(self, pc, argc):
        """74: (event) mark a story event done."""
        self.r.redirect(pc, 'done', lambda s: (dyn_set(s, DONE_BASE, lambda: s.arg(1), lambda: s.push(1)), s.result(0)))

    def the_end(self, pc, argc):
        """34: the chapter is over: the smartphone's closing message and the episode's exit."""
        self.r.redirect(pc, 'end', lambda s: (s.text(brew.END_TITLE), s.text(brew.END_TEXT), s.push(brew.END_ARGUMENT),
                                              s.call(33, 3), s.call(7, 0), s.emit(0x33)))

    # stats and quests
    def stats_define(self, pc, argc):
        """58: (index, name, icon, initial)...: the initial values (the names are the setup's constants)."""
        def build(s):
            for k in range(0, argc - 3, 4):
                dyn_set(s, GLOBAL_BASE, lambda k=k: s.arg(k + 1), lambda k=k: s.arg(k + 4))
            s.result(0)
        self.r.redirect(pc, 'stats_define', build)

    def snapshot(self, pc, argc):
        self.r.redirect(pc, 'snapshot', lambda s: (snapshot(s), s.result(0)))

    def stat_changes(self, pc, argc):
        """60: the stat-change panel: a `Stat changes` page that waits (owner, 2026-11-14), then the snapshot."""
        self.r.redirect(pc, 'stat_changes', lambda s: (stat_page(s, self.t, CHANGES_TITLE, None, True), snapshot(s), s.result(0)))

    def quests_clear(self, pc, argc):
        """66: (n) the quest table, emptied."""
        self.r.redirect(pc, 'quests_clear', lambda s: (set_global(s, QUEST_COUNT_KEY, lambda: s.push(0)), s.result(0)))

    def quest_add(self, pc, argc):
        """67: (title) a quest, its lines empty."""
        def build(s):
            n = lambda: get_global(s, QUEST_COUNT_KEY)      # noqa: E731
            quest_key(s, self.t, QUEST_TITLE, n); s.arg(1); s.call(46, 2)
            quest_key(s, self.t, QUEST_LINES, n); s.text(''); s.call(46, 2)
            set_global(s, QUEST_COUNT_KEY, lambda: (n(), s.push(1), s.emit(0x50)))
            s.result(0)
        self.r.redirect(pc, 'quest_add', build)

    def quest_lines(self, pc, argc):
        """68: (quest, n) its lines, emptied."""
        self.r.redirect(pc, 'quest_lines', lambda s: (quest_key(s, self.t, QUEST_LINES, lambda: s.arg(1)), s.text(''),
                                                      s.call(46, 2), s.result(0)))

    def quest_line(self, pc, argc):
        """69: (quest, line) a line added, under the others."""
        def build(s):
            first, write = s.label(), s.label()
            stored(s, self.t, QUEST_LINES, lambda: s.arg(1))        # local 0: the lines so far
            s.emit(0x41, 0); s.text(''); s.call(24, 2); s.push_result(); s.jump_if_nonzero(first)
            s.push(self.t.text()); s.text('%s\n%s'); s.emit(0x41, 0); s.arg(2); s.call(22, 4); s.jump(write)
            s.label(first)
            s.push(self.t.text()); s.text('%s'); s.arg(2); s.call(22, 3)
            s.label(write)
            quest_key(s, self.t, QUEST_LINES, lambda: s.arg(1)); s.push(self.t.text()); s.call(46, 2)
            s.result(0)
        self.r.redirect(pc, 'quest_line', build)

    def journal_updated(self, pc, argc):
        """76: "quest journal updated": its jingle and a badge, cleared after the next line."""
        def build(s):
            music(s, lambda: s.push(JOURNAL_CUE))
            s.push(shw.STAR_BADGE); s.text(JOURNAL_UPDATED); s.call(90, 2)
            set_global(s, BADGE_UP_KEY, lambda: s.push(1))
            s.result(0)
        self.r.redirect(pc, 'journal_updated', build)

    HANDLERS = {16: line, 14: plate, 15: page, 18: menu, 17: mask, 20: action_menu, 19: name_entry, 7: entry_text, 25: token_get,
                21: photo, 30: cast_picture, 31: set_picture, 1: sprintf, 22: global_set, 23: global_get, 29: global_clear,
                27: bit_set, 28: bit_get, 51: random_bit, 38: place_define, 40: unlist, 41: relist, 39: here, 43: slot, 53: day,
                71: home_get, 9: entry, 42: set_slot, 44: set_day, 70: home_set, 52: weekday, 54: days, 55: month, 56: date,
                45: goto, 46: card_here, 13: scene, 72: title_bar, 73: chapter, 10: sound, 48: end_day, 50: leave, 78: chain,
                74: done, 34: the_end, 58: stats_define, 59: snapshot, 60: stat_changes, 66: quests_clear, 67: quest_add,
                68: quest_lines, 69: quest_line, 76: journal_updated,
                61: provisional_game, 62: provisional_game, 63: provisional_game, 64: provisional_game, 65: provisional_game}
    RENAME = {3: 24, 4: 25, 6: 27, 24: 46, 26: 64, 33: 61}
    # The no-ops (0, 2, 11, 12, 32, 57, 84), the setup's tables kept as constants (36, 37, 47, 49, 75, 81, 82), the status bar
    # (79, 80), 8 (never written: 0) and 85 (a menu flag, 0 in play).
    DROPPED = {0, 2, 5, 8, 11, 12, 32, 36, 37, 47, 49, 57, 75, 79, 80, 81, 82, 84, 85, 86}

    def translate(self):
        for pc, service, argc in self.r.calls():
            if service in self.HANDLERS:
                self.HANDLERS[service](self, pc, argc)
            elif service in self.RENAME:
                self.r.rename(pc, self.RENAME[service])
            elif service in self.DROPPED:
                self.r.redirect(pc, 'drop', lambda s: s.result(0))
            else:
                raise brew.StoryError(f'{self.rid} pc {pc}: service {service} ({argc} arguments) has no translation')
        self.r.prologue(lambda s: (s.push(NARRATOR), s.call(75, 1), s.push(PLAYER), s.call(74, 1),
                                   s.push(NARRATOR), s.text(''), s.call(64, 2), s.push(NARRATOR), s.push(-1), s.call(72, 2)))
        return self.r.finish().to_bytes()


# -- the driver ----------------------------------------------------------------------------------------------------------------
class Driver:
    def __init__(self, story):
        self.story = story
        self.program = decode_program(brew.upgrade(brew.EMPTY_SCRIPT))
        self.r = Rewriter(self.program, zero_gap=True)
        self.t = Tables(self.r, story)
        sched = story.schedule
        r = self.r
        self.kinds = sched['kinds']
        self.grid = r.words(sched['grid'])
        n = sched['days'] * 7
        self.forced = r.words([sched['forced'].get(k, 0) for k in range(n)])
        self.story_events = r.words([sched['story'].get(k, 0) for k in range(n)])
        self.kind_scripts = r.words([shs_script(x) for x in sched['scripts']])
        places = story.setup['places']
        self.place_kinds = r.words([places.get(i, {}).get('kind', -1) for i in range(story.place_count)])
        self.pick = r.words([0])

    def run(self, s, script, entry, phase):
        """Run the SHS script `script()` pushes at the demo entry `entry()` pushes; the driver carries on at `phase` after it."""
        set_global(s, ENTRY_KEY, entry)
        set_global(s, TIME_SET_KEY, lambda: s.push(0))
        set_global(s, STOPPED_KEY, lambda: s.push(0))
        snapshot(s)
        set_global(s, PHASE_KEY, lambda: s.push(phase))
        s.push(DRIVER); s.push(0); s.call(10, 2)
        script(); s.push(0); s.call(10, 2)
        s.emit(0x33)

    def slot_index(self, s):
        get_global(s, DAY_KEY); s.push(7); s.emit(0x52); get_global(s, SLOT_KEY); s.emit(0x50)

    def grid_entry(self, s, kind):
        """Push the opening grid's entry for the place kind `kind()` pushes, now."""
        s.push(self.grid); kind(); s.emit(0x50); self.slot_index(s); s.push(self.kinds); s.emit(0x52); s.emit(0x50); s.emit(0x3f)

    def build(self):
        st, t = self.story, self.t
        sched = st.schedule

        def body(s):
            dispatch = {NEW_GAME: s.label(), SET_UP: s.label(), AFTER: s.label(), SLEPT: s.label(), JOURNAL: s.label()}
            the_map, where, finished = s.label(), s.label(), s.label()
            s.push(NARRATOR); s.call(75, 1); s.push(PLAYER); s.call(74, 1)
            s.push(NARRATOR); s.text(''); s.call(64, 2); s.push(NARRATOR); s.push(-1); s.call(72, 2)
            for phase, label in dispatch.items():
                get_global(s, PHASE_KEY); s.push(phase); s.emit(0x0a); s.jump_if_nonzero(label)
            s.jump(dispatch[NEW_GAME])

            # New Game: the setup, then the map (engine/shw.js newGame; the setup's 73 shows the title card).
            s.label(dispatch[NEW_GAME])
            set_global(s, BED_KEY, lambda: s.push(0))
            self.run(s, lambda: s.push(shs_script(SETUP_SCRIPT)), lambda: s.push(SETUP_ENTRY), SET_UP)
            s.label(dispatch[SET_UP])
            s.jump(the_map)

            # After a script (d.o()).
            s.label(dispatch[AFTER])
            no_pending, not_event, stopped, bedtime, listed = (s.label() for _ in range(5))
            get_global(s, PENDING_SCRIPT_KEY); s.jump_if_zero(no_pending)
            get_global(s, SLOT_KEY); s.push(BED_SLOT); s.emit(0x0e); s.jump_if_zero(no_pending)
            self.run_pending(s)
            s.label(no_pending)
            get_global(s, EVENT_KEY); get_global(s, STOPPED_KEY); s.emit(0x12); s.jump_if_zero(not_event)
            set_global(s, AFTER_EVENT_KEY, lambda: s.push(1))
            set_global(s, EVENT_KEY, lambda: s.push(0))
            card(s, t, lambda: get_global(s, HERE_KEY))
            self.run(s, lambda: get_global(s, ACTIVITY_SCRIPT_KEY), lambda: get_global(s, ACTIVITY_ENTRY_KEY), AFTER)
            s.label(not_event)
            get_global(s, STOPPED_KEY); s.jump_if_nonzero(stopped)
            set_global(s, AFTER_EVENT_KEY, lambda: s.push(0))
            get_global(s, TIME_SET_KEY); s.jump_if_nonzero(stopped)
            set_global(s, SLOT_KEY, lambda: (get_global(s, SLOT_KEY), s.push(1), s.emit(0x50)))
            s.label(stopped)
            get_global(s, SLOT_KEY); s.push(BED_SLOT); s.emit(0x0d); s.jump_if_zero(bedtime)
            set_global(s, SLOT_KEY, lambda: s.push(BED_SLOT))
            at_home, slept_in = s.label(), s.label()
            get_global(s, BED_KEY); s.jump_if_nonzero(slept_in)
            set_global(s, BED_KEY, lambda: s.push(BED_SLOT + 1))
            s.label(slept_in)
            get_global(s, HERE_KEY); get_global(s, HOME_KEY); s.emit(0x0a); s.jump_if_nonzero(at_home)
            move_to(s, lambda: get_global(s, HOME_KEY))
            card(s, t, lambda: get_global(s, HOME_KEY))
            s.label(at_home)
            self.run(s, lambda: s.push(shs_script(SLEEP_SCRIPT)), lambda: s.push(0), SLEPT)
            s.label(bedtime)
            dyn_get(s, LISTED_BASE, lambda: get_global(s, HERE_KEY)); s.jump_if_nonzero(listed)
            move_to(s, lambda: get_global(s, HOME_KEY))
            s.label(listed)
            s.jump(the_map)

            # After the sleep script: the next morning, under its date card.
            s.label(dispatch[SLEPT])
            set_global(s, DAY_KEY, lambda: (get_global(s, DAY_KEY), s.push(1), s.emit(0x50)))
            set_global(s, SLOT_KEY, lambda: s.push(0))
            set_global(s, BED_KEY, lambda: s.push(0))
            get_global(s, DAY_KEY); s.push(sched['days']); s.emit(0x0d); s.jump_if_nonzero(finished)
            s.text(TITLE); table_get(s, t.dates(), lambda: get_global(s, DAY_KEY))
            s.push(shw.BACKGROUND_BASE + shw.SKY_MODES * (HOME_PICTURE - 1500) + DAY_SKY); s.push(0); s.call(8, 4)
            s.jump(the_map)

            # The quest journal: the quest script has just rebuilt the quests.
            s.label(dispatch[JOURNAL])
            self.journal(s, the_map)

            # The map (mapTurn).
            s.label(the_map)
            no_forced = s.label()
            get_global(s, PENDING_SCRIPT_KEY); s.jump_if_zero(no_forced)
            self.run_pending(s)
            s.label(no_forced)
            no_force = s.label()
            get_global(s, DAY_KEY); s.push(sched['days']); s.emit(0x0d); s.jump_if_nonzero(finished)
            table_get(s, self.forced, lambda: self.slot_index(s)); s.jump_if_zero(no_force)
            set_global(s, ACTIVITY_SCRIPT_KEY, lambda: s.push(shs_script(sched['forced_script'])))
            set_global(s, ACTIVITY_ENTRY_KEY, lambda: table_get(s, self.forced, lambda: self.slot_index(s)))
            background(s, t, lambda: get_global(s, HERE_KEY))
            self.run(s, lambda: get_global(s, ACTIVITY_SCRIPT_KEY), lambda: get_global(s, ACTIVITY_ENTRY_KEY), AFTER)
            s.label(no_force)
            night, played = s.label(), s.label()
            get_global(s, SLOT_KEY); s.push(NIGHT_SLOT); s.emit(0x0d); s.jump_if_nonzero(night)
            music(s, lambda: s.push(MAP_DAY)); s.jump(played)
            s.label(night)
            music(s, lambda: s.push(MAP_NIGHT))
            s.label(played)
            background(s, t, lambda: get_global(s, HERE_KEY))
            s.label(where)
            self.where_to(s)
            stats, journal, place = s.label(), s.label(), s.label()
            s.emit(0x40, self.pick); s.push(STATS_OPTION); s.emit(0x0a); s.jump_if_nonzero(stats)
            s.emit(0x40, self.pick); s.push(JOURNAL_OPTION); s.emit(0x0a); s.jump_if_nonzero(journal)
            s.jump(place)
            s.label(stats)
            stat_page(s, t, STATS_TITLE, None, False)
            s.jump(where)
            s.label(journal)
            self.run(s, lambda: s.push(shs_script(QUEST_SCRIPT)), lambda: s.push(0), JOURNAL)
            s.label(place)
            pick = lambda: s.emit(0x40, self.pick)          # noqa: E731
            move_to(s, pick)
            kind = lambda: table_get(s, self.place_kinds, pick)     # noqa: E731
            no_story = s.label()
            get_global(s, AFTER_EVENT_KEY); s.jump_if_nonzero(no_story)
            set_global(s, EVENT_KEY, lambda: table_get(s, self.story_events, lambda: self.slot_index(s)))
            s.label(no_story)
            set_global(s, ACTIVITY_SCRIPT_KEY, lambda: table_get(s, self.kind_scripts, kind))
            set_global(s, ACTIVITY_ENTRY_KEY, lambda: self.grid_entry(s, kind))
            activity = s.label()
            get_global(s, EVENT_KEY); s.jump_if_zero(activity)
            dyn_get(s, DONE_BASE, lambda: get_global(s, EVENT_KEY)); s.jump_if_nonzero(activity)
            self.run(s, lambda: s.push(shs_script(sched['story_script'])), lambda: get_global(s, EVENT_KEY), AFTER)
            s.label(activity)
            card(s, t, pick)
            self.run(s, lambda: get_global(s, ACTIVITY_SCRIPT_KEY), lambda: get_global(s, ACTIVITY_ENTRY_KEY), AFTER)

            # Past the month's last day (34 normally ends it first).
            s.label(finished)
            s.text(brew.END_TITLE); s.text(brew.END_TEXT); s.push(brew.END_ARGUMENT); s.call(33, 3); s.call(7, 0)
            s.emit(0x33)
        self.r.prologue(body)
        return self.r.finish().to_bytes()

    def run_pending(self, s):
        script, entry = self.r.words([0]), self.r.words([0])
        set_word(s, script, lambda: get_global(s, PENDING_SCRIPT_KEY))
        set_word(s, entry, lambda: get_global(s, PENDING_ENTRY_KEY))
        set_global(s, PENDING_SCRIPT_KEY, lambda: s.push(0))
        self.run(s, lambda: s.emit(0x40, script), lambda: s.emit(0x40, entry), AFTER)

    def where_to(self, s):
        """Where to?: the places listed and open now, in district order, each `District: Place`, then the journal and the
        stats. The pick into self.pick."""
        st, t = self.story, self.t
        s.push(t.text()); s.text('%s, %s')
        table_get(s, t.times(), lambda: get_global(s, SLOT_KEY))
        table_get(s, t.dates(), lambda: get_global(s, DAY_KEY))
        s.call(22, 4)
        s.text(WHERE_TITLE); s.push(t.text()); s.push(0); s.push(0); s.push(PLAYER); s.push(brew.CHOICE_PORTRAIT); s.call(2, 6)
        places = st.setup['places']
        order = sorted((i for i, p in places.items() if p['kind'] >= 0), key=lambda i: (places[i]['district'], i))
        for i in order:
            skip = s.label()
            dyn_get(s, LISTED_BASE, lambda i=i: s.push(i)); s.jump_if_zero(skip)
            self.grid_entry(s, lambda i=i: s.push(places[i]['kind'])); s.push(0); s.emit(0x0c); s.jump_if_zero(skip)
            s.text(st.labels[i]); s.push(i); s.push(1); s.call(3, 3)
            s.label(skip)
        s.text(JOURNAL_TITLE); s.push(JOURNAL_OPTION); s.push(1); s.call(3, 3)
        s.text(STATS_TITLE); s.push(STATS_OPTION); s.push(1); s.call(3, 3)
        s.push(0); s.call(4, 1)
        set_word(s, self.pick, lambda: s.push_result())

    def journal(self, s, the_map):
        """The quest journal: a choice of the quests' titles (and Back), each opening its page of lines."""
        t = self.t
        top = s.label()
        s.label(top)
        s.text(JOURNAL_TITLE); s.push(-1); s.push(0); s.push(0); s.push(PLAYER); s.push(brew.CHOICE_PORTRAIT); s.call(2, 6)
        for q in range(MAX_QUESTS):
            skip = s.label()
            get_global(s, QUEST_COUNT_KEY); s.push(q); s.emit(0x0c); s.jump_if_zero(skip)
            stored(s, t, QUEST_TITLE, lambda q=q: s.push(q)); s.push(q); s.push(1); s.call(3, 3)
            s.label(skip)
        s.text('Back'); s.push(BACK_OPTION); s.push(1); s.call(3, 3)
        s.push(0); s.call(4, 1)
        set_word(s, self.pick, lambda: s.push_result())
        back = s.label()
        s.emit(0x40, self.pick); s.push(0); s.emit(0x0e); s.jump_if_nonzero(back)
        stored(s, t, QUEST_TITLE, lambda: s.emit(0x40, self.pick), -1)
        stored(s, t, QUEST_LINES, lambda: s.emit(0x40, self.pick), -2)
        s.push(0); s.call(33, 3)
        s.jump(top)
        s.label(back)
        set_global(s, PHASE_KEY, lambda: s.push(AFTER))
        s.jump(the_map)


def build_story(jar, addon_path):
    """(file name, bytes) of the full chapter, from the 1.0.2 jar and the shshw add-on."""
    from exp_runtime.exp import ExpArchive
    found = shw.jar_resources(jar)
    missing = [rid for rid in (SCHEDULE, *SCRIPTS) if rid not in found and rid not in (10009, 10013, 10016)]
    if missing:
        raise brew.StoryError(f'{jar}: not the 1.0.2 demo (missing {missing})')
    spec = json.loads(ExpArchive(Path(addon_path).read_bytes()).read(shw.SPEC))
    story = Story(found, spec)
    resources = {DRIVER: Driver(story).build()}
    for rid in SCRIPTS:
        if rid in found:
            resources[shs_script(rid)] = Script(rid, found[rid], story).translate()
    resources[ADDON_RECORD] = requires_bytes([(shw.ADDON_ID, ADDON_REQUIRED)])
    resources[VERSION_RECORD] = version_bytes(VERSION)
    resources[1] = Metadata(PACK, EPISODE, (TITLE + SUFFIX,) * 5).to_bytes()
    return brew.file_name(TITLE, SUFFIX), encode_exp(resources)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--jar', required=True, help="the 1.0.2 demo's jar (560_ver1.0_b2_hs92_english.jar)")
    parser.add_argument('--addon', required=True, help=f'shshw.exp (shw.py), revision {ADDON_REQUIRED} or later')
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    name, data = build_story(args.jar, args.addon)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_bytes(data)
    print(f'{name}: {len(data):,} bytes')


if __name__ == '__main__':
    main()
