"""Surviving Hollywood's lite Chapter 1, *The Bright Lights* as the low-end 1.0.4 demo ("88K") retells it, as an SHS episode.

    python tools/translate/shw_lite.py --jar LITE_DEMO_JAR --addon shshw.exp --out DIR

Phase 2 of the owner's plan (reference/Other Games/docs/SURVIVING_HOLLYWOOD_ADDON_PLAN.md, 2026-11-14). The 1.0.4 jar holds one
KiWi v1 script (10002) on the demo engine's own host ABI (SURVIVING_HOLLYWOOD_ENGINE.md section 9). This keeps that script and
sends each host call to SHS's services, as brew.py does BREW's. Owner's choices (2026-11-14): the badge SHW in the logo's gold,
the group Surviving Hollywood, the title `The Bright Lights (Lite)`; the 1.0.2 demo's painted art only (no silhouettes); the demo's
own frame; nothing from the BREW add-on: every picture, sound and the catch game's look come from `shshw` (shw.py), which the
episode requires (revision ADDON_REQUIRED). Its names (`$USR`) are its own table, apart from every other game's (owner,
2026-11-14; the profile's TRANSLATED_NAME_SETS).

- **One script, re-run.** The phone starts 10002 at entry 32001 (its setup) and chains to it again (78) at entries 1, 3, 7 and
  9, which the script reads back with 9. SHS queues a script with no entry, so the entry is a saved number (ENTRY_KEY): 78 sets
  it, queues the script and halts; 9 reads it, SETUP_ENTRY while it's unset. 78's checkpoint save has no counterpart: the
  player's own autosave covers it.
- **The cast** (built by the setup's loop: 26 names, 31 pictures, 87 colours): each entry's face is a 1.0.2 portrait
  (CAST_FACES), turned where it would look away from the middle on the right (case by case, as the Preview's). New Game's photo
  choice (21) is SHS's picker (78) over entries 0-2, and 30/31 give the player the chosen one's face. Box colours by entry.
- **Lines** (16): Event's are the narrator's, without their brackets; anyone else's line wholly in brackets is a thought (13's
  -2 mode); Instructions speaks in the named box (76). The emoticon glyphs `{ } [ ]` are left out (SHS has none).
- **Places** (45): the 1.0.2 painted backgrounds (LOCATIONS) at each scene's time of day (SITE_SKY); a travel card (45's second
  argument) is a badge with the place's name and the demo's map star, cleared after the next line. 1.0.4 keeps no clock: its
  travel card (mode 4 in h.java) draws the place's picture and name only, and the script never sets the time (42/44), so the
  badges carry no time, unlike 1.0.2's.
- **Choices**: 18 is SHS's choice (1), 19 the name entry (17).
- **The fight** (the function holding the one action menu, 20): four rounds of `Punch!`, `Be cool`, `Be good` and `Smack!` jumping
  under `n/4: Don't get riled.`, each word's score (1 for the calm ones) added up and passed at 3. It's SHS's timed word game
  (71) instead, as brew.word_game makes BREW's spinning-menu routine (owner, 2026-11-14): the words scoring above 0 are good, the
  rest bad; a pass is the best total, less its share.
- **The catch game** (63, peanut butter at the gym): BREW's catch game (service 221, its orbit kind) in the demo's skin from
  `shshw` (desktop_brew_catch, the profile's TRANSLATED_CATCH_ADDON), the jar (2531) for 1.0.4's peanut butter and the demo's
  star for the player. Its score is the hits, as 1.0.4's. The Instructions line just before it is the page BREW's catch games
  open with (33, titled `Instructions`), not a line (owner, 2026-11-14). With "Use Translated Mini-Games" off, a word game under
  its own title and text: a pass is no hits.
- **Sounds** (10): 1.0.4 plays only two tones (45 success, 14 fail), the demo's cues 3014 and 3006 here.
- **The end** (34): the smartphone's closing message and the episode's exit.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import brew  # noqa: E402
import newrules  # noqa: E402
import shw  # noqa: E402
from brew import get_global, set_global, set_word  # noqa: E402
from exp_runtime.addons import RESOURCE as ADDON_RECORD, requires_bytes  # noqa: E402
from exp_runtime.brew_services import BREW_CATCH, BREW_MINIGAMES_QUERY, ORBIT  # noqa: E402
from exp_runtime.decode.bytecode import decode_program  # noqa: E402
from exp_runtime.episode_version import RESOURCE as VERSION_RECORD, version_bytes  # noqa: E402
from exp_runtime.exp import ExpArchive, Metadata, encode_exp  # noqa: E402
from kiwi_rewrite import Rewriter  # noqa: E402

PACK, EPISODE, VERSION = 31700, 2, 1      # episode 2: the full chapter (shw_full.py) is 1 (owner, 2026-11-14)
TITLE, SUFFIX = 'The Bright Lights (Lite)', ' (SHW)'
ADDON_REQUIRED = 4                      # shshw: the catch star by number and the map star badge
SCRIPT, STORY = 10002, 25001
SETUP_ENTRY = 32001                     # the phone's first entry (h.java: a(10002, 32001, ...))
PLAYER, EVENT, INSTRUCTIONS, NARRATOR = 0, 3, 10, 199
# Saved numbers (owner 0) the translation keeps for itself; the script's own globals are 0-16.
ENTRY_KEY, BADGE_UP_KEY, RESULT_KEY = 31701, 31702, 31703
ENTRY_TEXT = '$SHWENTRY'
THEME, NO_BADGE = 651, 629             # SHS character keys: box colour; 1 hides the relationship icon
BLUE, PINK, GREY = 1, 2, 3
# Each cast entry's face: a 1.0.2 portrait and whether it's turned (shw.FLIPPED_BASE). Entries 0-2 are New Game's three photos
# (1.0.2's photos 1-3), of which the player's becomes entry 0's. Shown on the right in play, Chelsea, the Secretary and The Jeff
# look away from the middle as drawn, so they're turned (owner's rule, 2026-11-13: case by case).
CAST_FACES = {0: (2015, False), 1: (2013, False), 2: (2037, False), 4: (2049, False), 5: (2033, False), 6: (2006, True),
              7: (2042, True), 8: (2031, False), 9: (2048, True)}
# Box colours: the women pink, the men blue, Event and Instructions grey.
CAST_THEMES = {0: PINK, 1: PINK, 2: PINK, 3: GREY, 4: BLUE, 5: BLUE, 6: PINK, 7: PINK, 8: BLUE, 9: BLUE, 10: GREY}
# 1.0.4's places (38: index, name) as 1.0.2's painted backgrounds: the airport, All-Star-Agents, home, inside Club Franken-Stein
# (the scene is on the dance floor), the beach.
LOCATIONS = {0: 1504, 1: 1529, 2: 1505, 3: 1518, 4: 1512}
LOCATION_NAMES = {0: 'Airport', 1: 'All-Star-Agents', 2: 'Home', 3: 'Club Franken-Stein', 4: 'Beach'}
DAY, NIGHT, SUNSET = 0, 1, 2
# Each place's time of day, by the pc of its 45 in 10002, as the story tells it: the evening arrival and unpacking, the airport
# and the night after, then the next days, the club at night.
SITE_SKY = {438: SUNSET, 501: SUNSET, 600: NIGHT, 647: NIGHT, 675: DAY, 733: DAY, 814: NIGHT, 918: DAY, 1090: DAY,
            1159: DAY, 1220: DAY}
CARD_PICTURE = (1523, SUNSET)           # the title card: the city from the hills, at sunset
SOUNDS = {45: shw.MUSIC_BASE + 3014 - 3000, 14: shw.MUSIC_BASE + 3006 - 3000}
# The catch list's pictures: 1.0.4's peanut butter (2028) is 1.0.2's jar (2531). Its items are (value, picture, count): two
# kinds, 15 and 25 of them, each hit 1.
CATCH_PICTURES = {2028: 2531}
CATCH_COUNTS = (15, 25)
CATCH_TITLE = 'Dodge the peanut butter!'
CATCH_TEXT = 'Pick the moves that keep you clean.'
CATCH_GOOD, CATCH_BAD = 'Dodge|Duck|Spin|Twirl', 'Catch|Grab|Taste|Snack'
PAGE_TITLE = brew.CATCH_GENERIC_TITLE.decode('latin-1')      # the catch page's title, as BREW's
# The fight's routine: (options buffer, words, scores, count, shown, -1, rounds, question, jump ms, timer ms, numbered, speaker).
QUIZ_ARGS = 12
QUIZ_LIST_WORDS = 40                    # each of the word game's lists: the routine's four words, `|` between
EMOTICONS = re.compile(rb' ?[{}\[\]]')
DEFAULT_NAME = 'Kate'                   # 1.0.4's own (`$usr` is "kate" in 10002), as the Preview's


def tidy(text):
    """A string of the script as SHS shows it: no emoticon glyphs; `$usr` as SHS's token `$USR`."""
    changed = EMOTICONS.sub(b'', text).replace(b'$usr', b'$USR')
    return changed if changed != text else None


def string_at(program, address):
    out = bytearray()
    for w in program.main_words[address:address + 400]:
        for b in (w >> 8, w & 255):
            if b == 0:
                return bytes(out)
            out.append(b)
    return bytes(out)


def set_result(s, value):
    """R = the value `value()` pushes (KiWi has no instruction for that: a saved number read back with 55)."""
    set_global(s, RESULT_KEY, value)
    s.push(RESULT_KEY); s.call(55, 1)


class Lite:
    def __init__(self, raw, shw_spec):
        self.spec = shw_spec
        self.program = brew.rewrite_strings(decode_program(brew.upgrade(raw)), tidy)
        self.r = Rewriter(self.program, zero_gap=True)
        self.page_line, self.page_text = self.catch_page()

    def catch_page(self):
        """(pc, text) of the Instructions line that comes just before the catch game (the host call before 63), or (None, None)."""
        ins = self.program.instructions
        hosts = [i for i in ins if i.opcode == 0x1f]
        for before, call in zip(hosts, hosts[1:]):
            if call.operand >> 8 == 63 and before.operand >> 8 == 16:
                speaker, address = newrules.pushed_values(self.program, before.pc, 2)
                if speaker == INSTRUCTIONS and address is not None:
                    return before.pc, self.r.text(string_at(self.program, address).decode('cp1252'))
        return None, None

    def face(self, s, entry):
        """Push the shshw portrait of the cast entry `entry()` pushes: CAST_FACES, else -1 (none)."""
        end = s.label()
        for index, (portrait, turned) in sorted(CAST_FACES.items()):
            other = s.label()
            entry(); s.push(index); s.emit(0x0a); s.jump_if_zero(other)
            s.push((shw.FLIPPED_BASE if turned else shw.PORTRAIT_BASE) + portrait - 2000); s.jump(end)
            s.label(other)
        s.push(-1)
        s.label(end)

    def clear_badge(self, s):
        done = s.label()
        get_global(s, BADGE_UP_KEY); s.jump_if_zero(done)
        s.push(-1); s.push(-1); s.call(90, 2)
        set_global(s, BADGE_UP_KEY, lambda: s.push(0))
        s.label(done)

    # -- what each call becomes ---------------------------------------------------------------------------------------
    def line(self, pc, argc):
        """16: (speaker, text). Every one of 1.0.4's 158 has both as constants."""
        speaker, address = newrules.pushed_values(self.program, pc, 2)
        if speaker is None or address is None:
            raise brew.StoryError(f'1.0.4 pc {pc}: a line whose speaker or text is worked out')
        text = string_at(self.program, address)
        whole = text.startswith(b'(') and text.endswith(b')') and text.count(b'(') == 1
        bare = self.r.text(text[1:-1].decode('cp1252')) if whole else None
        if pc == self.page_line:
            def build(s):                                   # (the catch game's page: catch)
                self.clear_badge(s); s.result(0)
            key = 'catch_page'
        elif speaker == EVENT:
            def build(s):
                (s.push(bare) if whole else s.arg(2)); s.push(NARRATOR); s.call(13, 2)
                self.clear_badge(s); s.result(0)
            key = ('narration', bare)
        elif speaker == INSTRUCTIONS:
            def build(s):
                s.text('Instructions'); s.arg(2); s.call(76, 2)
                self.clear_badge(s); s.result(0)
            key = 'instructions'
        elif whole:
            def build(s):
                s.push(-2); s.push(bare); s.arg(1); s.push(0); s.call(13, 4)
                self.clear_badge(s); s.result(0)
            key = ('thought', bare)
        else:
            def build(s):
                s.arg(2); s.arg(1); s.push(0); s.call(13, 3)
                self.clear_badge(s); s.result(0)
            key = 'line'
        self.r.redirect(pc, key, build)

    def menu(self, pc, argc):
        """18: (title, `a|b|c`, speaker, timer ms): SHS's choice (1), its answer the option's index as 1.0.4's. A menu titled
        `You` says brew.CHOICE_TITLE, as BREW's do."""
        def build(s):
            other, titled = s.label(), s.label()
            s.arg(1); s.text('You'); s.call(24, 2); s.push_result(); s.jump_if_zero(other)
            s.text(brew.CHOICE_TITLE); s.jump(titled)
            s.label(other)
            s.arg(1)
            s.label(titled)
            s.arg(2); s.push(-1); s.arg(4); s.push(0); s.arg(3); s.push(-1); s.push(brew.CHOICE_PORTRAIT)
            s.call(1, 8)
        self.r.redirect(pc, 'menu', build)

    def name_entry(self, pc, argc):
        """19: (title, initial): SHS's text entry (17), the answer kept under ENTRY_TEXT for 7 (as brew.text_entry)."""
        def build(s):
            s.arg(1); s.text(''); s.arg(2); s.call(17, 3)
            s.push_result()
            s.text(ENTRY_TEXT); s.emit(0x41, 0); s.call(46, 2)
            s.result(0)
        self.r.redirect(pc, 'name_entry', build)

    def entry_text(self, pc, argc):
        """7: (destination) the last text entered."""
        def build(s):
            s.text(ENTRY_TEXT); s.text(''); s.push(-1); s.call(47, 3); s.push_result()
            s.arg(1); s.text('%s'); s.emit(0x41, 0); s.call(22, 3)
            s.result(0)
        self.r.redirect(pc, 'entry_text', build)

    def token_get(self, pc, argc):
        """25: (`$KEY`, destination) a token into memory; `$USR` is DEFAULT_NAME until the player names herself."""
        def build(s):
            s.arg(1); s.text(DEFAULT_NAME); s.push(-1); s.call(47, 3); s.push_result()
            s.arg(2); s.text('%s'); s.emit(0x41, 0); s.call(22, 3)
            s.result(0)
        self.r.redirect(pc, 'token_get', build)

    def photo(self, pc, argc):
        """21: (count, list of cast entries): SHS's portrait picker (78), which answers the chosen one's place in the list."""
        def build(s):
            s.text(brew.PORTRAIT_TITLE); s.arg(1); s.arg(2); s.call(78, 3)
        self.r.redirect(pc, 'photo', build)

    def cast_picture(self, pc, argc):
        """30: (entry) its picture, which 31 gives another entry (the player): the entry itself stands for it here."""
        self.r.redirect(pc, 'cast_picture', lambda s: set_result(s, lambda: s.arg(1)))

    def set_picture(self, pc, argc):
        """31: (entry, picture). In the setup, 1.0.4's silhouettes (negative): the entry's own face. After the photo choice, an
        entry (30's answer): that one's face."""
        def build(s):
            own, done = s.label(), s.label()
            s.arg(2); s.push(0); s.emit(0x0e); s.jump_if_nonzero(own)
            s.arg(1); self.face(s, lambda: s.arg(2)); s.call(72, 2); s.jump(done)
            s.label(own)
            s.arg(1); self.face(s, lambda: s.arg(1)); s.call(72, 2)
            s.label(done)
            s.result(0)
        self.r.redirect(pc, 'set_picture', build)

    def colours(self, pc, argc):
        """87: (entry, name bar colours): the entry's box colour (CAST_THEMES), SHS's 651. 1.0.4 keeps no relationships, so
        the entry's relationship icon is hidden (629) too."""
        def build(s):
            s.arg(1); s.push(THEME); s.select(1, CAST_THEMES, BLUE); s.call(52, 3)
            s.arg(1); s.push(NO_BADGE); s.push(1); s.call(52, 3)
            s.result(0)
        self.r.redirect(pc, 'colours', build)

    def cast_name(self, pc, argc):
        """26: (entry, name)."""
        self.r.redirect(pc, 'cast_name', lambda s: (s.arg(1), s.arg(2), s.call(64, 2), s.result(0)))

    def goto(self, pc, argc):
        """45: (place, card): the place's background at the scene's sky; with a card, a badge naming the place until the next
        line is read."""
        sky = SITE_SKY.get(pc)
        if sky is None:
            raise brew.StoryError(f'1.0.4 pc {pc}: a scene change with no sky in SITE_SKY')
        names = {k: self.r.text(v) for k, v in LOCATION_NAMES.items()}
        pictures = {k: shw.BACKGROUND_BASE + shw.SKY_MODES * (v - 1500) + sky for k, v in LOCATIONS.items()}

        def build(s):
            plain = s.label()
            s.push(0); s.select(1, pictures, pictures[2]); s.call(11, 2)
            s.arg(2); s.push(0); s.emit(0x0c); s.jump_if_zero(plain)
            s.push(shw.STAR_BADGE); s.select(1, names, names[2]); s.call(90, 2)
            set_global(s, BADGE_UP_KEY, lambda: s.push(1))
            s.label(plain)
            s.result(0)
        self.r.redirect(pc, ('goto', sky), build)

    def chapter(self, pc, argc):
        """73: (`Chapter 1`, `The Bright Lights`): SHS's title card, the story's name over the chapter's."""
        picture = shw.BACKGROUND_BASE + shw.SKY_MODES * (CARD_PICTURE[0] - 1500) + CARD_PICTURE[1]

        def build(s):
            s.arg(2); s.arg(1); s.push(picture); s.push(0); s.call(8, 4); s.result(0)
        self.r.redirect(pc, 'chapter', build)

    def sound(self, pc, argc):
        """10: (tone): the demo's success and fail cues; any other tone (none in 10002) plays nothing."""
        def build(s):
            done = s.label()
            s.select(1, SOUNDS, -1); s.push(0); s.emit(0x0e); s.jump_if_nonzero(done)
            s.select(1, SOUNDS, -1); s.call(79, 1)
            s.label(done)
            s.result(0)
        self.r.redirect(pc, 'sound', build)

    def entry(self, pc, argc):
        """9: the entry this run started at: ENTRY_KEY's, SETUP_ENTRY while it's unset. Both ways R holds it."""
        def build(s):
            done = s.label()
            get_global(s, ENTRY_KEY); s.jump_if_nonzero(done)
            s.result(SETUP_ENTRY)
            s.label(done)
        self.r.redirect(pc, 'entry', build)

    def chain(self, pc, argc):
        """78: (script, entry, checkpoint): run the script again at that entry; this run ends."""
        def build(s):
            set_global(s, ENTRY_KEY, lambda: s.arg(2))
            s.push(STORY); s.push(0); s.call(10, 2)
            s.emit(0x33)
        self.r.redirect(pc, 'chain', build)

    def the_end(self, pc, argc):
        """34: the chapter is over: the smartphone's closing message and the episode's exit."""
        self.r.redirect(pc, 'end', lambda s: (s.text(brew.END_TITLE), s.text(brew.END_TEXT), s.push(brew.END_ARGUMENT),
                                              s.call(33, 3), s.call(7, 0), s.emit(0x33)))

    def catch(self, pc, argc):
        """63: (target, interval, speed, spread, list, picture, label): BREW's catch game, the orbit kind, its score the hits
        (each item is worth 1); with "Use Translated Mini-Games" off, a word game, whose pass is no hits and miss the target's
        worth. 1.0.4's picture (2035) and label (`hits`) have no counterpart: the star and `Score` are the skin's."""
        sizes = self.spec['catch']['pictures']
        numbers = sorted({*CATCH_PICTURES.values(), shw.CATCH_STAR_PICTURE})
        table = self.r.words([v for n in numbers for v in (n, *sizes[str(n)][1:])])
        cuts = brew.catch_cuts(self.r.code, pc)
        cut_table = -1 if cuts is None else self.r.words([len(cuts), *cuts])

        def build(s):
            real, done, passed = s.label(), s.label(), s.label()
            s.push(BREW_MINIGAMES_QUERY); s.call(70, 1)
            s.push_result(); s.jump_if_nonzero(real)
            s.text(CATCH_TITLE); s.text(CATCH_TEXT); s.text(CATCH_GOOD); s.text(CATCH_BAD)
            s.push(brew.WORD_GAME_MS); s.push(PLAYER); s.push(1); s.push(brew.WORD_GAME_REFRESH_MS)
            s.call(71, 8)
            s.push_result(); s.push(brew.WORD_GAME_PASS); s.emit(0x0d); s.jump_if_nonzero(passed)
            set_result(s, lambda: s.arg(1)); s.jump(done)
            s.label(passed)
            s.result(0); s.jump(done)
            s.label(real)
            if self.page_text is not None:
                s.text(PAGE_TITLE); s.push(self.page_text); s.push(0); s.call(33, 3)
            s.push(ORBIT); s.arg(1); s.arg(2); s.arg(3); s.arg(4); s.push(0); s.push(0)
            s.push(shw.CATCH_STAR_PICTURE); s.arg(5); s.push(table); s.push(len(numbers)); s.push(cut_table)
            s.call(BREW_CATCH, 12)
            s.label(done)
        self.r.redirect(pc, 'catch', build)

    def quiz_routine(self):
        """Where the fight's routine starts: the function holding the one action menu (20), whose callers drop QUIZ_ARGS."""
        ins = self.program.instructions
        sites = [i.pc for i in ins if i.opcode == 0x1f and i.operand >> 8 == 20]
        if len(sites) != 1:
            raise brew.StoryError(f'the lite fight: {len(sites)} action menus, 1 expected')
        start = max(i.pc for i in ins if i.opcode == 0x48 and i.pc <= sites[0])
        callers = [k for k in range(len(ins) - 2) if ins[k].opcode == 0x42 and ins[k + 1].opcode == 0x29 and ins[k + 1].operand == start]
        if not callers or any(ins[k + 2].opcode != 0x19 or ins[k + 2].operand != QUIZ_ARGS for k in callers):
            raise brew.StoryError(f'the lite fight: the routine at {start} is not called with {QUIZ_ARGS} arguments')
        return start

    def quiz(self, start):
        """The fight's routine as SHS's timed word game (71) under `Think fast!` and the routine's question: the words scoring above 0
        good, the rest bad. It returns the total in B, as the routine does: a pass is the rounds times the best score, less that
        share (compared before multiplying, as brew.word_game, since the skip prompt's Win is 32767)."""
        good, bad = self.r.words([0] * QUIZ_LIST_WORDS), self.r.words([0] * QUIZ_LIST_WORDS)

        def build(s):
            words, scores, count, rounds = (lambda: s.arg(2)), (lambda: s.arg(3)), (lambda: s.arg(4)), (lambda: s.arg(7))
            score = lambda: (scores(), s.emit(0x41, 0), s.emit(0x50), s.emit(0x3f))         # noqa: E731
            for buffer in (good, bad):
                set_word(s, buffer, lambda: s.push(0))
            s.push(0)                                       # local 0: the word
            s.push(1)                                       # local 1: the best score
            top, end = s.label(), s.label()
            s.label(top)
            s.emit(0x41, 0); count(); s.emit(0x0e); s.jump_if_zero(end)

            def append(buffer):
                first = s.label()
                s.emit(0x40, buffer); s.jump_if_zero(first)
                s.push(buffer); s.text('|'); s.call(25, 2)
                s.label(first)
                s.push(buffer); words(); s.emit(0x41, 0); s.emit(0x50); s.emit(0x3f); s.call(25, 2)
            worse, kept, following = s.label(), s.label(), s.label()
            score(); s.push(0); s.emit(0x0c); s.jump_if_zero(worse)
            score(); s.emit(0x41, 1); s.emit(0x0c); s.jump_if_zero(kept)
            s.emit(0x23, 1); score(); s.emit(0x3e); s.emit(0x15)
            s.label(kept)
            append(good)
            s.jump(following)
            s.label(worse)
            append(bad)
            s.label(following)
            s.emit(0x23, 0); s.emit(0x41, 0); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
            s.jump(top)
            s.label(end)
            s.text(brew.TIMED_TITLE); s.arg(8); s.push(good); s.push(bad)
            s.push(brew.WORD_GAME_MS); s.push(PLAYER); s.push(1); s.push(brew.WORD_GAME_REFRESH_MS)
            s.call(71, 8)
            s.push_result()                                 # local 2: the result
            short, returned = s.label(), s.label()
            s.emit(0x41, 2); s.push(brew.WORD_GAME_PASS); s.emit(0x0d); s.jump_if_zero(short)
            rounds(); s.emit(0x41, 1); s.emit(0x52); s.jump(returned)
            s.label(short)
            s.emit(0x41, 2); rounds(); s.emit(0x52); s.emit(0x41, 1); s.emit(0x52); s.push(brew.WORD_GAME_PASS); s.emit(0x53)
            s.label(returned)
            s.emit(0x04)
        self.r.replace_function(start, 'quiz', build, QUIZ_ARGS)

    def catch_list(self):
        """Where the catch list's pictures are (its address is in word 5874 at run time, so it's found by its shape)."""
        words, found = self.program.main_words, []
        for k in range(1, len(words) - 1):
            if words[k] in CATCH_PICTURES and words[k - 1] == 1 and words[k + 1] in CATCH_COUNTS:
                found.append(k)
        if len(found) != len(CATCH_COUNTS):
            raise brew.StoryError(f'the lite catch list: {len(found)} pictures found, {len(CATCH_COUNTS)} expected')
        return found

    HANDLERS = {16: line, 18: menu, 19: name_entry, 21: photo, 7: entry_text, 25: token_get, 30: cast_picture,
                31: set_picture, 87: colours, 26: cast_name, 45: goto, 73: chapter, 10: sound, 9: entry, 78: chain, 34: the_end,
                63: catch}
    RENAME = {1: 22, 4: 25, 6: 27, 22: 54, 23: 55, 24: 46}
    # The debug print, the places' and cast's setup (the background is 45's), the status flash and the calendar; the action menu
    # (20), inside the fight's routine, which quiz replaces whole, so it's never reached.
    DROPPED = {0, 20, 36, 37, 38, 70, 80, 81, 82, 86}

    def translate(self):
        self.quiz(self.quiz_routine())
        for pc, service, argc in self.r.calls():
            if service in self.HANDLERS:
                self.HANDLERS[service](self, pc, argc)
            elif service in self.RENAME:
                self.r.rename(pc, self.RENAME[service])
            elif service in self.DROPPED:
                self.r.redirect(pc, 'drop', lambda s: s.result(0))
            else:
                raise brew.StoryError(f'1.0.4 pc {pc}: service {service} ({argc} arguments) has no translation')
        found = self.catch_list()
        # The player is SHS's primary speaker and the narrator a character of its own with no name or picture (as brew.py's).
        self.r.prologue(lambda s: (s.push(NARRATOR), s.call(75, 1), s.push(PLAYER), s.call(74, 1),
                                   s.push(NARRATOR), s.text(''), s.call(64, 2), s.push(NARRATOR), s.push(-1), s.call(72, 2)))
        program = self.r.finish()
        words = list(program.main_words)
        for k in found:
            words[k] = CATCH_PICTURES[words[k]]
        return replace(program, main_words=tuple(words)).to_bytes()


def build_story(jar, addon_path):
    """(file name, bytes) of the lite chapter, from the 1.0.4 jar and the shshw add-on (its spec's catch picture sizes)."""
    found = shw.jar_resources(jar)
    if SCRIPT not in found:
        raise brew.StoryError(f'{jar}: not the 1.0.4 (88K) demo')
    spec = json.loads(ExpArchive(Path(addon_path).read_bytes()).read(shw.SPEC))
    if str(shw.CATCH_STAR_PICTURE) not in spec.get('catch', {}).get('pictures', {}):
        raise brew.StoryError(f'the shshw add-on is too old: build revision {ADDON_REQUIRED} or later')
    resources = {STORY: Lite(found[SCRIPT], spec).translate()}
    resources[ADDON_RECORD] = requires_bytes([(shw.ADDON_ID, ADDON_REQUIRED)])
    resources[VERSION_RECORD] = version_bytes(VERSION)
    resources[1] = Metadata(PACK, EPISODE, (TITLE + SUFFIX,) * 5).to_bytes()
    return brew.file_name(TITLE, SUFFIX), encode_exp(resources)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--jar', required=True, help="the 1.0.4 (88K) demo's jar")
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
