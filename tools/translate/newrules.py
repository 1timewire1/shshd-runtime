"""Translate a New Rules episode (`.expd`) into an SHS `.exp` for shshd-runtime.

The scripts keep New Rules' own bytecode. Each host call is renamed or sent through a shim (kiwi_rewrite.py) according to
the map below. The map was checked against the 45 New Rules stories that also exist as smartphone EXPs: with the same
answers, the two versions show the same lines through these calls (reference/Other Games/docs/TRANSLATOR_PLAN.md).

Characters keep their numbers (the paired stories number them identically). Portraits are New Rules' paper-doll
looks, pre-rendered into five-picture expression banks; backgrounds are its location strips (nr_art.py).
"""
from collections import Counter
from dataclasses import dataclass, field, replace
import re
import struct

from exp_runtime.decode.bytecode import decode_program
from exp_runtime.exp import ExpArchive, Metadata, encode_exp
from exp_runtime.vm import KiwiVM, StopKind, VMError

from kiwi_rewrite import Rewriter
import nr_art

PACK_ID = 31300                         # the owner's block for New Rules (TRANSLATOR_PLAN.md decision 5)
NARRATOR = 199                          # New Rules narrates without a speaker (box mode -4); SHS needs a character
PLAYER = 1                              # the primary speaker (74) when a story has no dialogue to judge by
THOUGHT_WEIGHT = 4                      # protagonist(): a thought line counts as this many lines
THEME = 651                             # SHS character property: dialogue bubble theme (1 male, 2 female)
NO_BADGE = 629                          # SHS character property: 1 hides the relationship badge
MODES = len(nr_art.SKY_MODES)           # time-of-day modes 0-5 (service 35's first argument)
BACKGROUND_BASE = 26000                 # location L in mode M = BACKGROUND_BASE + MODES * L + M
PORTRAIT_BASE = 26200                   # five consecutive IDs per look
# The same looks drawn from the X1i jar's redrawn parts, HD-sized, this far above: the player shows them while its
# "hi-res portraits" option is on (shs/profile.py TRANSLATED_PORTRAIT_ART); the original apps never ask for them.
HIRES_PORTRAIT_OFFSET = 1000
MUSIC_BASE = 26980                      # New Rules music index i = MUSIC_BASE + i
# New Rules' UI backdrop (nr_art.Art.backdrop), which the runtime draws over SHS's frame under the location strip
# instead of black for this pack (shs/profile.py TRANSLATED_FRAME_BACKDROP).
FRAME_BACKDROP = 26999
MODE_KEY = 31300                        # SHS global number holding the current mode, for title cards
TITLE_SUFFIX = ' (New Rules)'           # on the library title only; the story's own title card is unchanged
# The narrator handing over the player (announcements()); `who` is a name, or empty for a pronoun.
ANNOUNCEMENT = re.compile(r"\bplay(?:ing)? as (?:(?P<who>(?!her\b|him\b|them\b)[a-z.]+(?: [a-z.]+)?)|her|him)\b"
                          r"|\bin (?:his|her) shoes\b|\binto (?P<brain>[a-z.]+)'s brain\b")
ANNOUNCEMENT_CONTEXT = 3                # narration lines before an announcement searched for its pronoun's name
PLAYER_KEY = 31301                      # SHS global number holding the current player (74), for choices and word games
# The smartphone versions' word games (71): 20 s with a word every 3 s in 69 of their 70, passed at a score of 6.
WORD_GAME_MS, WORD_GAME_REFRESH_MS, WORD_GAME_PASS = 20000, 3000, 6
WORD_GAME_GOOD, WORD_GAME_BAD = 2, 3          # the fewest entries SHS 71 can deal
# Music index -> the Java builds' track ID (o.g[]); res_large.pud stores track J as resource 283 + J - 8001.
MUSIC_TRACKS = (8004, 8002, 8005, 8006, 8007, 8003, 8008, 8009, 8001, 8010, 8011, 8012, 8013, 8014, 8015)
MUSIC_PRELOAD = 1                       # service 7 mode that only loads the track (Player.realize/prefetch)
# New Rules' right/wrong answer jingles (music index -> feedback). The smartphone versions play SHS's 8007/8003 there;
# the runtime's choice hints read these as feedback in this pack (shs/profile.py TRANSLATED_FEEDBACK_MUSIC).
FEEDBACK_TRACKS = {13: 1, 1: -1}
# New Rules expression (0 = the character's default) -> SHS expression slot; the banks hold New Rules expressions
# (1, 4, 2, 3, 5) in SHS slots 0-4: neutral, angry, happy, sad, surprised. Found on the paired stories.
EXPRESSION = {0: -1, 1: 0, 2: 2, 3: 3, 4: 1, 5: 4}
BANK_EXPRESSIONS = (1, 4, 2, 3, 5)
DEFAULT_EXPRESSION = {0: 0, 1: 0, 2: 2, 3: 3, 4: 1, 5: 4}
CHOICE_TITLE = 'Make your choice!'
TIMEOUT_OPTION = 0                      # a timed choice's answer when time runs out: the first option shown
# Narration that the smartphone versions show as a notice (88): two-word achievement beats. Every notice in the 45
# paired twins has this shape ("good answer!", "handle approved!", "exhibit successful!"), and no line does.
NOTICE = re.compile(r"^\s*(good [a-z]+|[a-z]+ [a-z]+(ed|ful))!\s*$", re.IGNORECASE)
# Same arguments, same order (New Rules service -> SHS service).
RENAME = {1: 22, 2: 25, 6: 27, 15: 54, 16: 55, 17: 46, 18: 47, 19: 64, 27: 6, 33: 9, 34: 10, 65: 10}
# Owned numbers and bits (owner, key, ...): the same calls as SHS's, but New Rules keeps data of its own in character
# keys 651-654 (h.java reads 651 as a text reference), which SHS reads as the dialogue theme (651). Those keys move up
# by PRIVATE_KEYS; every other key is shared (630 means the same in the smartphone versions).
PROPERTY = {20: 50, 21: 51, 22: 52, 23: 53}
OWN_KEYS, PRIVATE_KEYS = range(651, 655), 31000
# Presentation New Rules has and SHS doesn't (stage layout, UI tints, phone-keypad help, no-ops): the call is removed.
DROPPED = {10, 29, 36, 37, 38, 39, 44, 45, 46, 58, 59, 62, 64, 66}
# New Rules' build query (32): selector -> constant.
BUILD = {1: 1, 3: 8, 4: 3, 5: 4, 7: 0, 8: 1, 9: 2}     # the Java build answers 2 to selector 1 (keyboard_guards)
KEYBOARD_WINDOW = 60                    # keyboard_guards(): how far after a selector-1 query the text entry may be


class TranslateError(ValueError):
    pass


@dataclass
class Episode:
    download_id: int
    title: str
    scripts: dict                       # resource -> KiwiProgram
    library: object = None              # a built-in story's minigame library (KiwiProgram), which it calls into
    text_addresses: dict = None         # resource -> the addresses of its strings, where its data holds other words
                                        # that could read as text (read_lite's tables of string addresses)


def read_expd(data: bytes) -> Episode:
    """`u16` download ID, `u16` length + title, then the CSPUD archive (SCHEMA.md section 7)."""
    download_id, length = struct.unpack_from('>HH', data)
    title = data[4:4 + length].decode('cp1252')
    archive = ExpArchive(data[4 + length:])
    scripts = {rid: decode_program(archive.read(rid)) for rid in archive.entries
               if archive.read(rid)[:4] == b'kiwi'}
    return Episode(download_id, title, scripts)


@dataclass
class Report:
    calls: dict = field(default_factory=dict)       # (New Rules service, argc) -> count
    unmapped: dict = field(default_factory=dict)
    looks: int = 0
    unknown_look_sites: int = 0
    unknown: Counter = field(default_factory=Counter)      # words casing left lowercase (the review list)
    notices: int = 0
    music: int = 0                                          # rendered tracks embedded
    protagonist: int = PLAYER                               # the primary speaker chosen (protagonist())
    word_games: int = 0                                     # minigame rounds played as SHS word games
    library_games: dict = field(default_factory=dict)       # a built-in story's library calls by game (LIBRARY_ENTRIES)


def discover(episode, steps=200000, sexes=None):
    """Each script's look records (service 25: character, address) and character names (19: name -> the characters
    given it), found by running it with a stub host that answers 0. Records are read from the VM's memory, so looks
    built at run time count too. `sexes`, if given, is filled with character -> the look's sex word (1 male, 0
    female)."""
    looks, names = {}, {}
    for rid, program in episode.scripts.items():
        # New Rules' data starts zeroed (kiwi_rewrite.Rewriter zero_gap)
        vm = KiwiVM(replace(program, main_words=program.main_words + (0,) * program.gap_count, gap_count=0))
        for _ in range(4000):
            try:
                stop = vm.run(steps)
            except VMError:
                break               # the stub's answers can lead where the real game never goes: keep what was found
            if stop.kind != StopKind.YIELD:
                break
            if stop.yield_id == 25:
                character, address = stop.args
                record = tuple(vm.read_word(address + 2 + i) for i in range(34))    # property 636, then 33 slots
                looks.setdefault((rid, address), record)
                if sexes is not None:
                    sexes.setdefault(character, record[0])
            if stop.yield_id == 19 and len(stop.args) == 2 and 0 <= stop.args[1] < len(program.main_words):
                name = text_at(program, stop.args[1])
                if name:
                    names.setdefault(name, set()).add(stop.args[0])
            vm.resume(0)
    return looks, names


def used_scenes(episode):
    """The (location, mode) pictures an episode can show. A location change (35) names both; a title card (30) shows
    its location in the current mode, any mode the episode sets. A value computed at run time stands for all."""
    locations, modes = range(len(nr_art.LOCATIONS)), range(MODES)
    changes, cards = set(), set()
    for program in episode.scripts.values():
        for instruction in program.instructions:
            if instruction.opcode != 0x1f or (instruction.operand >> 8) not in (30, 35):
                continue
            service, argc = instruction.operand >> 8, instruction.operand & 255
            if argc < (3 if service == 30 else 2):
                continue
            values = pushed_values(program, instruction.pc, argc)
            if service == 30:
                cards.update(locations if values[2] is None else [values[2]])
                continue
            mode, location = values[0], values[1]
            for m in (modes if mode is None else [mode if mode >= 0 else 0]):
                changes.update((l, m) for l in (locations if location is None else [location]))
    used_modes = {m for _, m in changes} | {0}
    return {(l, m) for l, m in changes | {(l, m) for l in cards for m in used_modes}
            if 0 <= l < len(nr_art.LOCATIONS) and 0 <= m < MODES}


def title_card_titles(program):
    """The addresses of the titles the program's title cards (30) and closing screen (28) show: a constant, or the
    format string of a formatted one ("%s morning.")."""
    titles = set()
    for i in program.instructions:
        if i.opcode == 0x1f and i.operand >> 8 in (28, 30) and i.operand & 255 >= 1:
            title = pushed_values(program, i.pc, i.operand & 255)[0]
            titles.add(title if title is not None else formatted_title(program, i.pc, i.operand & 255))
    return titles - {None}


def plain_options(program):
    """`program` with the emphasis backticks taken out of its choice options (11's list, 13's text): New Rules marks
    King of Diss's rhymes that way ("`phonics`."), and SHS's menu labels show a backtick as it is. The shorter string
    keeps its place, ended early."""
    words = list(program.main_words)
    for i in program.instructions:
        if i.opcode != 0x1f or i.operand >> 8 not in (11, 13):
            continue
        args = pushed_values(program, i.pc, i.operand & 255)
        address = args[1] if i.operand >> 8 == 11 and len(args) > 1 else args[0]
        text = text_at(replace(program, main_words=tuple(words)), address) if address is not None else None
        if not text or '`' not in text:
            continue
        data = text.replace('`', '').encode('latin-1') + b'\0'
        data += b'\0' * (len(data) % 2)
        for k in range(0, len(data), 2):
            words[address + k // 2] = data[k] << 8 | data[k + 1]
    return replace(program, main_words=tuple(words))


def text_at(program, address):
    out = bytearray()
    for w in program.main_words[address:address + 100]:
        for byte in (w >> 8, w & 255):
            if byte == 0:
                return out.decode('latin-1')
            out.append(byte)
    return None


def used_music(episode):
    """The music indices an episode can play (service 7 outside preload mode); every index if one is computed."""
    found = set()
    for program in episode.scripts.values():
        for instruction in program.instructions:
            if instruction.opcode != 0x1f or instruction.operand >> 8 != 7 or instruction.operand & 255 < 2:
                continue
            index, mode = pushed_values(program, instruction.pc, 2)
            if mode == MUSIC_PRELOAD:
                continue
            if index is None:
                return set(range(len(MUSIC_TRACKS)))
            if 0 <= index < len(MUSIC_TRACKS):
                found.add(index)
    return found


def protagonist(episode):
    """The character the story follows, for SHS's primary speaker (74), which New Rules has no notion of: the one with
    the most lines, a thought line (mode -2) counting THOUGHT_WEIGHT times. Each story follows its own character
    (Brendan, Matt, Howard...); on the 45 paired stories this picks the twin's primary speaker in 37. A story that
    switches perspective moves 74 at each choice the new character makes (chooser)."""
    score = speaker_scores(episode)
    return score.most_common(1)[0][0] if score else PLAYER


def speaker_scores(episode):
    """Lines per speaking character, a thought line counting THOUGHT_WEIGHT times."""
    score = Counter()
    for program in episode.scripts.values():
        for instruction in program.instructions:
            if instruction.opcode != 0x1f or instruction.operand >> 8 not in (40, 41, 42):
                continue
            service, argc = instruction.operand >> 8, instruction.operand & 255
            args = pushed_values(program, instruction.pc, argc)
            first = 2 if args[0] is not None and args[0] < 0 else 1
            index = first + (0 if service == 40 else 1)             # the speaking character after the text (and name)
            if index < argc and args[index] is not None and args[index] != NARRATOR:
                score[args[index]] += THOUGHT_WEIGHT if first == 2 and args[0] == -2 else 1
    return score


def chooser(title, names, scores):
    """The character a choice's title names ("kim", "$matt."): New Rules titles a choice with whoever makes it, so a
    story that switches perspective (Kim to Mallika) shows it here. None for a title that is the question itself."""
    if title is None:
        return None
    key = title.strip().rstrip('.!?:').strip().lower()
    # King of Diss Lite titles Josh's choices "josh", whose name is the `$josh` key (set from it by service 18).
    characters = names.get(key) or names.get('$' + key)
    return max(characters, key=lambda c: scores.get(c, 0)) if characters else None


def has_player(episode, names, scores):
    """Whether the story has a player character: someone who thinks (mode -2 lines), makes a choice titled with a
    name, types their name, or is handed over by the narrator. Train That Brain! has none: Spud and Dexter host a
    quiz, so its choices are the narrator's (gold, without a portrait) while Dexter keeps the player's side."""
    for program in episode.scripts.values():
        if announcements(program, names, scores):
            return True
        for i in program.instructions:
            if i.opcode != 0x1f:
                continue
            service, argc = i.operand >> 8, i.operand & 255
            if service == 49:
                return True
            if service == 40 and argc >= 3 and pushed_values(program, i.pc, argc)[0] == -2:
                return True
            if service in (11, 12):
                title = constant_text(program, None, i.pc, 1, argc)
                if title is not None and (title.startswith('$') or chooser(title, names, scores) is not None):
                    return True
    return False


def set_player(s, character):
    """Make `character` the player: SHS's primary speaker (74), remembered in PLAYER_KEY."""
    s.push(character); s.call(74, 1)
    s.push(PLAYER_KEY); s.push(character); s.call(54, 2)


def push_player(s):
    s.push(PLAYER_KEY); s.call(55, 1); s.push_result()


def music_resource(index):
    """The res_large.pud resource holding music index `index`'s MIDI."""
    return 283 + MUSIC_TRACKS[index] - 8001


def translate(episode: Episode, art: nr_art.Art, report=None, music=None, casing_dictionary=None, casing_exact=None,
              twin_games=(), casing_titles=(), hires_art=None):
    """The SHS `.exp` bytes for one New Rules episode. `hires_art`: the X1i jar's parts, for the second, HD-sized
    portrait set (HIRES_PORTRAIT_OFFSET), if any. `music`: index -> rendered MP3 bytes (a callable), if any;
    `casing_dictionary`: casing.learn's dictionary, which restores capitals (else the text stays lowercase);
    `casing_exact`: the paired smartphone story's strings by lowercase text, whose casing wins where they match;
    `twin_games`: its word games' (good, bad) lists (pairs.twin_word_games), whose extra words fill out the rounds."""
    report = report or Report()
    resources = {}
    sexes = {}
    looks, names = discover(episode, sexes=sexes)
    primary = report.protagonist = protagonist(episode)
    scores = speaker_scores(episode)
    player = has_player(episode, names, scores)
    if casing_dictionary is not None:
        import casing
        episode = replace(episode, scripts={
            rid: replace(program, main_words=casing.recase_program(program, casing_dictionary, names,
                                                                   titles=[episode.title, *casing_titles],
                                                                   unknown=report.unknown,
                                                                   exact=casing_exact,
                                                                   addresses=(episode.text_addresses or {}).get(rid),
                                                                   headlines=title_card_titles(program)))
            for rid, program in episode.scripts.items()})
    episode = replace(episode, scripts={rid: plain_options(program) for rid, program in episode.scripts.items()})
    banks, bank_of = {}, {}
    for (rid, address), record in sorted(looks.items()):
        slots = record[1:]
        if slots not in banks:
            base = PORTRAIT_BASE + 5 * len(banks)
            banks[slots] = base
            for i, picture in enumerate(art.portrait_bank(list(slots), BANK_EXPRESSIONS)):
                resources[base + i] = nr_art.png(picture)
            if hires_art is not None:
                pictures = hires_art.portrait_bank(list(slots), BANK_EXPRESSIONS, nr_art.HIRES_PORTRAIT_SCALE)
                for i, picture in enumerate(pictures):
                    resources[base + HIRES_PORTRAIT_OFFSET + i] = nr_art.png(picture)
        bank_of[rid, address] = banks[slots]
    report.looks = len(banks)
    for location, mode in sorted(used_scenes(episode)):
        resources[BACKGROUND_BASE + MODES * location + mode] = nr_art.jpeg(art.background(location, mode))
    backdrop = art.backdrop()
    if backdrop is not None:
        resources[FRAME_BACKDROP] = nr_art.png(backdrop)
    for rid, program in sorted(episode.scripts.items()):
        rewriter = Rewriter(program, zero_gap=True)
        guards = keyboard_guards(program)
        players = scene_players(program, names, scores)
        handovers = announcements(program, names, scores, sexes)
        for start, game in word_games(program).items():
            rewriter.replace_function(start, ('word_game', start), lambda s, game=game: word_game(s, program, game, twin_games, player))
            report.word_games += 1
        for pc, entry, argc in library_calls(program):
            kind = LIBRARY_ENTRIES.get(entry)
            if kind is None or episode.library is None:
                raise TranslateError(f'script {rid} calls library code at {entry}, which has no translation')
            index = report.library_games.get(kind, 0)
            report.library_games[kind] = index + 1
            rewriter.replace_call(pc, ('library', kind, index), argc,
                                  lambda s, kind=kind, index=index: library_game(s, kind, index, episode.library, player,
                                                                                 music is not None))
        last_line = rewriter.words([-1])                       # the last line shown, for a choice's description
        for pc, service, argc in rewriter.calls():
            key = (service, argc)
            report.calls[key] = report.calls.get(key, 0) + 1
            handler = HANDLERS.get(service)
            if service in RENAME:
                rewriter.rename(pc, RENAME[service])
            elif service in DROPPED:
                rewriter.redirect(pc, 'drop', lambda s: s.result(0))
            elif handler is not None:
                handler(rewriter, pc, argc, dict(last_line=last_line, rid=rid, bank_of=bank_of, report=report,
                                                 program=program, music=music, names=names, primary=primary,
                                                 service=service, keyboard_guards=guards, scores=scores,
                                                 scene_players=players, announcements=handovers,
                                                 player=player))
            else:
                report.unmapped[key] = report.unmapped.get(key, 0) + 1
                rewriter.redirect(pc, ('unmapped', service), lambda s: s.result(0))
        if rid == 25001:
            rewriter.prologue(lambda s: (s.push(NARRATOR), s.call(75, 1), set_player(s, players.get('start', primary)),
                                         s.push(NARRATOR), s.text(''), s.call(64, 2),
                                         s.push(NARRATOR), s.push(-1), s.call(72, 2)))
        elif 'start' in players:
            rewriter.prologue(lambda s: set_player(s, players['start']))
        resources[rid] = rewriter.finish().to_bytes()
    if music is not None:
        tracks = used_music(episode)
        if report.library_games.get('rhyme'):
            tracks |= {RIGHT_TRACK, WRONG_TRACK}            # the speed disses' jingles (speed_diss)
        for index in sorted(tracks):
            resources[MUSIC_BASE + index] = music(index)
        report.music = len(tracks)
    # The library's picker hides a second import of a story it already lists (same title, nearly the same text), so
    # a story with a smartphone version would never show; the suffix keeps the two apart.
    resources[1] = Metadata(PACK_ID, episode.download_id, (episode.title + TITLE_SUFFIX,) * 5).to_bytes()
    return encode_exp(resources), report


# -- shims ---------------------------------------------------------------------------------------------------------
def remember_line(s, i, context):
    """Store argument i (a text reference) as the last line shown."""
    s.push(context['last_line']); s.arg(i); s.emit(0x3e); s.emit(0x15)


def dialogue(rewriter, pc, argc, context):
    """40: ([mode], text, char[, expression]), the mode present when the first word is negative (f.java); -2 and -3 are
    SHS's thought and emphasis prefixes too, another box mode (-5) is dropped. Expression 0 means the character's
    default. The scripts push the mode as a constant; a four-word call's computed mode is tested when it runs. A thought
    stays its thinker's: it shows on the player's side only when the player thinks it (Mrs. Faulkner's don't)."""
    mode = pushed_values(context['program'], pc, argc)[0]
    if argc == 3 and mode is not None and mode < 0:
        prefix = mode if mode in (-2, -3) else None

        def build_mode(s):
            remember_line(s, 2, context)
            if prefix is not None:
                s.push(prefix)
            s.arg(2); s.arg(3); s.call(13, 2 + (prefix is not None))
        rewriter.redirect(pc, ('dialogue', 'mode', prefix), build_mode)
        return

    def build(s):
        if argc == 4:
            # SHS 13 understands the -2/-3 prefixes; another box mode is dropped.
            mode_kept = s.label()
            remember_line(s, 2, context)
            s.arg(1); s.push(-2); s.emit(0x0a); s.arg(1); s.push(-3); s.emit(0x0a); s.emit(0x11)
            s.jump_if_nonzero(mode_kept)
            s.arg(2); s.arg(3); s.select(4, EXPRESSION, -1); s.call(13, 3)
            done = s.label(); s.jump(done)
            s.label(mode_kept)
            s.arg(1); s.arg(2); s.arg(3); s.select(4, EXPRESSION, -1); s.call(13, 4)
            s.label(done)
            return
        remember_line(s, 1, context)
        s.arg(1); s.arg(2)
        if argc == 3:
            s.select(3, EXPRESSION, -1)
        s.call(13, argc)
    rewriter.redirect(pc, ('dialogue', 40), build)


def named_dialogue(rewriter, pc, argc, context):
    """41: ([mode], name, text, char[, expression]) and 42: ([mode], name, text, char, expression, ...): a line under
    a given name with the listed characters' portraits (f.java a(boolean, byte, int, boolean)). An empty name, or one
    character's own name, is that character speaking: SHS 13 with the portrait. Any other name ("kay and kel",
    "crowd") is SHS 15, named and without a portrait, as the smartphone versions show crowd lines."""
    program = context['program']
    args = pushed_values(program, pc, argc)
    first = 2 if args[0] is not None and args[0] < 0 else 1
    name = constant_text(program, rewriter, pc, first, argc)
    character = args[first + 1] if argc > first + 1 else None
    words = argc - first - 1                                 # character (and expression) words after the text
    own = words in (1, 2) and character is not None and (
        name == '' or name is not None and character in context['names'].get(name.lower(), ()))
    prefix = args[0] if first == 2 and args[0] in (-2, -3) else None

    def build(s):
        remember_line(s, first + 1, context)
        if not own:
            s.arg(first); s.arg(first + 1); s.call(15, 2)
            return
        if prefix is not None:
            s.push(prefix)
        s.arg(first + 1); s.arg(first + 2)
        if words == 2:
            s.select(first + 3, EXPRESSION, -1)
        s.call(13, (prefix is not None) + 1 + words)
    rewriter.redirect(pc, ('named', own, prefix, first, words), build)


def narration(rewriter, pc, argc, context):
    """43: (text), spoken by no one. An achievement beat ("handle approved!", "good answer!", NOTICE) is shown by the
    smartphone versions as a notice over the next line (88) rather than a line of its own. A line handing the player a
    character ("play as her...", announcements) makes that character the player as it is shown."""
    text = constant_text(context['program'], rewriter, pc, 1, argc)
    if text is not None and NOTICE.match(text):
        context['report'].notices += 1
        rewriter.redirect(pc, 'notice', lambda s: (s.arg(1), s.call(88, 1)))
        return
    who = context.get('announcements', {}).get(pc)

    def build(s):
        if who is not None:
            set_player(s, who)
        remember_line(s, 1, context)
        s.arg(1); s.push(NARRATOR); s.call(13, 2)
    rewriter.redirect(pc, ('narration', who), build)


def padded_limit(s, i):
    """Push argument i, a time limit in ms, padded by 30% as New Rules does (h.java: t + t * 30 / 100, in 32 bits; here
    t + t / 10 * 3, which KiWi's 16-bit words hold, the same for the downloads' whole hundreds); -1 stays -1."""
    s.arg(i); s.arg(i); s.push(10); s.emit(0x53); s.push(3); s.emit(0x52); s.emit(0x50)


def choice(rewriter, pc, argc, context):
    """11: (title, `a|b|c`, cursor interval ms, time limit ms), both -1 in every download (h.java a(String, String,
    int, int); see begin_choice). The paired smartphone stories show "Make your choice!" over the player's portrait,
    and the question underneath: New Rules' title when it is the question, else (it names the chooser, "kim" or
    `$matt.`) the last line shown, with the chooser made the player (set_player)."""
    title = constant_text(context['program'], rewriter, pc, 1, argc)
    who = chooser(title, context['names'], context['scores'])
    names_speaker = who is not None or title is not None and title.startswith('$')

    def build(s):
        if who is not None:
            set_player(s, who)
        s.text(CHOICE_TITLE); s.arg(2)
        if names_speaker:
            s.emit(0x40, context['last_line'])
        else:
            s.arg(1)
        padded_limit(s, 4)
        s.push(TIMEOUT_OPTION)
        s.push(who if who is not None else -2 if context.get('player', True) else NARRATOR)
        s.push(-1); s.push(1)
        s.call(1, 8)
    rewriter.redirect(pc, ('choice', names_speaker, who, context.get('player', True)), build)


def begin_choice(rewriter, pc, argc, context):
    """12: (title, cursor interval ms, time limit ms) -> SHS 2: (title, description, timer, timeout answer, character,
    portrait mode). Both times are padded by 30%. With an interval, New Rules' highlight jumps to a random option at
    every tick and the limit picks whatever it rests on (the minigame rounds: 600 and 3000, h.java); SHS has no jumping
    cursor, so the choice keeps its limit and times out to the first option shown, a random one after the shuffle.
    The title and chooser work as in choice()."""
    title = constant_text(context['program'], rewriter, pc, 1, argc)
    who = chooser(title, context['names'], context['scores'])
    names_speaker = who is not None or title is not None and title.startswith('$')

    def build(s):
        if who is not None:
            set_player(s, who)
        s.text(CHOICE_TITLE)
        if names_speaker:
            s.emit(0x40, context['last_line'])
        else:
            s.arg(1)
        padded_limit(s, 3)
        s.push(TIMEOUT_OPTION)
        if who is None and not context.get('player', True):
            s.push(NARRATOR)                                # no player: the narrator's choice
        elif who is None:
            push_player(s)
        else:
            s.push(who)
        s.push(1)
        s.call(2, 6)
    rewriter.redirect(pc, ('begin_choice', names_speaker, who, context.get('player', True)), build)


def add_option(rewriter, pc, argc, context):
    """13: (text, value, enabled, is-timeout-default) -> SHS 3: (text, value, enabled)."""
    rewriter.redirect(pc, 'add_option', lambda s: (s.arg(1), s.arg(2), s.arg(3), s.call(3, 3)))


def show_choice(rewriter, pc, argc, context):
    rewriter.rename(pc, 4)


def text_entry(rewriter, pc, argc, context):
    """49: ([negative mode], title, prompt, default, type, max length, ...): SHS's text input (17). Both return the
    answer's string handle in R (f.java case 24, and the `$KEY` store that follows it in the scripts)."""
    mode = pushed_values(context['program'], pc, argc)[0]
    first = 2 if mode is not None and mode < 0 else 1

    def build(s):
        s.arg(first); s.arg(first + 1); s.arg(first + 2); s.call(17, 3)
    rewriter.redirect(pc, ('text_entry', first), build)


def title_card(rewriter, pc, argc, context):
    """30: (title, subtitle, location, flag) -> SHS 8 with the location's picture (-1 = none)."""
    def build(s):
        s.arg(1); s.arg(2)
        background(s, 3)
        s.arg(4); s.call(8, 4)
    rewriter.redirect(pc, 'title_card', build)


def background(s, i):
    """Push the background ID of location argument i in the current mode (MODE_KEY): BACKGROUND_BASE + MODES *
    location + mode, or -1 (keep) when the location is negative."""
    keep, done = s.label(), s.label()
    s.arg(i); s.push(0); s.emit(0x0e); s.jump_if_nonzero(keep)
    s.arg(i); s.push(MODES); s.emit(0x52); s.push(BACKGROUND_BASE); s.emit(0x50)
    s.push(MODE_KEY); s.call(55, 1); s.push_result(); s.emit(0x50); s.jump(done)
    s.label(keep); s.push(-1)
    s.label(done)


def scene_players(program, names, scores):
    """Who the player is in each scene: {location change (35) pc, or 'start': character}. A scene's player is the first
    one it shows in program order, by a choice titled with a name (chooser), before the next location change. A thought
    line is no sign: other characters think too (King of Diss's Mrs. Faulkner). Switching there, as the smartphone versions do (74 at the new character's scene), rather than
    at that first sign, keeps the scene's earlier lines on the right side."""
    signals, scenes = [], []
    for i in program.instructions:
        if i.opcode != 0x1f:
            continue
        service, argc = i.operand >> 8, i.operand & 255
        if service == 35:
            scenes.append(i.pc)
        elif service in (11, 12):
            who = chooser(constant_text(program, None, i.pc, 1, argc), names, scores)
            if who is not None:
                signals.append((i.pc, who))
    found = {}
    for start, end in zip(['start'] + scenes, scenes + [len(program.instructions)]):
        first = next((who for pc, who in signals if (start == 'start' or pc > start) and pc < end), None)
        if first is not None:
            found[start] = first
    return found


def announcements(program, names, scores, sexes=None):
    """{narration (43) pc: character} where the narrator hands the player a character: "play as dinah and find out!",
    "we'll let you play as her...", "help spike... we'll put you in his shoes!", "let's slip into mallika's brain".
    A pronoun is the character of its sex (`sexes`, from the looks) named in that line or in the narration just
    before it (ANNOUNCEMENT_CONTEXT lines),
    else the next choice titled with a name or thought line (scene_players' signs)."""
    narration, signals = [], []
    for i in program.instructions:
        if i.opcode != 0x1f:
            continue
        service, argc = i.operand >> 8, i.operand & 255
        if service == 43:
            text = constant_text(program, None, i.pc, 1, argc)
            if text is not None:
                narration.append((i.pc, text.lower()))
        elif service in (11, 12):
            who = chooser(constant_text(program, None, i.pc, 1, argc), names, scores)
            if who is not None:
                signals.append((i.pc, who))
        elif service == 40 and argc >= 3:
            args = pushed_values(program, i.pc, argc)
            if args[0] == -2 and args[2] is not None:
                signals.append((i.pc, args[2]))

    def named(text, sex):
        """The first character the text names, of the pronoun's sex if known ("howard rushes into the parking lot...
        where dinah is waiting. play as her")."""
        found = sorted((m.start(), name) for name in names for m in re.finditer(r'\b' + re.escape(name) + r'\b', text)
                       if not name.startswith('$'))
        for _, name in found:
            who = chooser(name, names, scores)
            if sex is None or (sexes or {}).get(who, sex) == sex:
                return who
        return None

    result = {}
    for index, (pc, text) in enumerate(narration):
        match = ANNOUNCEMENT.search(text)
        if match is None or ' both ' in text:
            continue
        named_as = match.group('who') or match.group('brain')
        who = chooser(named_as, names, scores) if named_as else None
        if who is None and named_as and ' ' in named_as:
            who = chooser(named_as.split()[0], names, scores)
        if who is None and named_as:
            continue                                    # "play as next", "play as a good-natured guy": no one named
        pronoun = re.search(r'\b(her|him|his)\b', match.group())
        sex = {'her': 0, 'him': 1, 'his': 1}[pronoun.group(1)] if pronoun else None
        if who is None:
            for _, earlier in [(pc, text[:match.start()])] + narration[max(0, index - ANNOUNCEMENT_CONTEXT):index][::-1]:
                who = named(earlier, sex)
                if who is not None:
                    break
        if who is None:
            who = next((w for signal, w in signals if signal > pc), None)
        if who is not None:
            result[pc] = who
    return result


def location(rewriter, pc, argc, context):
    """35: (mode, location[, label]) -> SHS 11: (0, background). The mode (time of day: the sky behind windows and
    outdoors, nr_art.SKY_MODES) picks the picture; a negative mode keeps the current one (h.java c(short, short)), and
    it is kept in MODE_KEY for title cards. The label isn't shown by New Rules either. A scene with a player of its own
    (scene_players) switches to it here."""
    who = context['scene_players'].get(pc)

    def build(s):
        if who is not None:
            set_player(s, who)
        keep = s.label()
        s.arg(1); s.push(0); s.emit(0x0e); s.jump_if_nonzero(keep)
        s.push(MODE_KEY); s.arg(1); s.call(54, 2)
        s.label(keep)
        s.push(0)
        background(s, 2)
        s.call(11, 2)
    rewriter.redirect(pc, ('location', who), build)


def music(rewriter, pc, argc, context):
    """7: (index, mode) -> SHS 80 (MUSIC_BASE + index, no repeat). New Rules plays every track once: the Java player
    never changes MIDP's loop count of 1 (j.c). Mode 1 only preloads the track; modes 0 and 2 play it when the scene is
    next drawn (h.java). Without rendered music (decision 4), the call only returns."""
    if context['music'] is None:
        rewriter.redirect(pc, 'drop', lambda s: s.result(0))
        return

    def build(s):
        done = s.label()
        s.result(0)
        s.arg(2); s.push(MUSIC_PRELOAD); s.emit(0x0a); s.jump_if_nonzero(done)
        s.arg(1); s.push(MUSIC_BASE); s.emit(0x50); s.push(0)
        s.call(80, 2)
        s.label(done)
    rewriter.redirect(pc, 'music', build)


def look(rewriter, pc, argc, context):
    """25: (character, address of the look record) -> SHS 72 with the look's portrait bank. The record's first word
    (property 636) is the character's sex, 1 male and 0 female; SHS's bubble theme (651) is 1 male, 2 female, which
    the smartphone versions set for every character. New Rules has no relationship values, so the SHS relationship
    badge is hidden (629 = 1), as the smartphone versions do too."""
    table = {address: bank for (rid, address), bank in context['bank_of'].items() if rid == context['rid']}
    if not table:
        context['report'].unknown_look_sites += 1

    def build(s):
        s.arg(1); s.push(THEME); s.push(2); s.arg(2); s.push(2); s.emit(0x50); s.emit(0x3f); s.emit(0x51)  # 2 - sex
        s.call(52, 3)
        s.arg(1); s.push(NO_BADGE); s.push(1); s.call(52, 3)
        s.arg(1); s.select(2, table, -1); s.call(72, 2)
    rewriter.redirect(pc, ('look', context['rid']), build)


def owned_number(rewriter, pc, argc, context):
    """20-23: owned bits and numbers (owner, key[, ...]) -> SHS 50-53, with New Rules' own keys (OWN_KEYS) moved."""
    service = PROPERTY[context['service']]
    key = pushed_values(context['program'], pc, argc)[1] if argc >= 2 else None
    if key is not None and key not in OWN_KEYS:
        rewriter.rename(pc, service)
        return

    def build(s):
        s.arg(1)
        if key is not None:
            s.push(key + PRIVATE_KEYS)
        else:
            own, done = s.label(), s.label()
            s.arg(2); s.push(OWN_KEYS.start); s.emit(0x0d)                   # key >= 651
            s.arg(2); s.push(OWN_KEYS.stop); s.emit(0x0e); s.emit(0x12)      # and key < 655
            s.jump_if_nonzero(own)
            s.arg(2); s.jump(done)
            s.label(own); s.arg(2); s.push(PRIVATE_KEYS); s.emit(0x50)
            s.label(done)
        for i in range(3, argc + 1):
            s.arg(i)
        s.call(service, argc)
    rewriter.redirect(pc, ('owned', service, key), build)


def copy_look(rewriter, pc, argc, context):
    """26: (from, to) -> SHS 72(to, art of from), with the bubble theme and hidden badge (look())."""
    def build(s):
        s.arg(2); s.push(THEME); s.arg(1); s.push(THEME); s.call(53, 2); s.push_result(); s.call(52, 3)
        s.arg(2); s.push(NO_BADGE); s.push(1); s.call(52, 3)
        s.arg(2); s.arg(1); s.call(73, 1); s.push_result(); s.call(72, 2)
    rewriter.redirect(pc, 'copy_look', build)


def default_expression(rewriter, pc, argc, context):
    """24: (character, expression) -> SHS 5 with the expression mapped."""
    rewriter.redirect(pc, 'default_expression', lambda s: (s.arg(1), s.select(2, DEFAULT_EXPRESSION, 0), s.call(5, 2)))


def format_text(rewriter, pc, argc, context):
    """5: ([negative slot], format, values...) -> SHS 0. New Rules' -k selects slot k-1; SHS's -k slot 1+k, and its
    slot 0 has no selector: -1 drops the selector, -k (k >= 3) becomes 2-k. Slot 1 (-2) is formatted into slot 2,
    then copied there through a stored text (46, 47)."""
    def build(s):
        plain, slot0, slot1, done = s.label(), s.label(), s.label(), s.label()
        s.arg(1); s.push(0); s.emit(0x0d); s.jump_if_nonzero(plain)
        s.arg(1); s.push(-1); s.emit(0x0a); s.jump_if_nonzero(slot0)
        s.arg(1); s.push(-2); s.emit(0x0a); s.jump_if_nonzero(slot1)
        s.arg(1); s.push(2); s.emit(0x50)
        for i in range(2, argc + 1): s.arg(i)
        s.call(0, argc); s.jump(done)
        s.label(plain)
        for i in range(1, argc + 1): s.arg(i)
        s.call(0, argc); s.jump(done)
        s.label(slot0)
        for i in range(2, argc + 1): s.arg(i)
        s.call(0, argc - 1); s.jump(done)
        s.label(slot1)
        s.push(-1)
        for i in range(2, argc + 1): s.arg(i)
        s.call(0, argc)
        s.text('\x01translated slot 1'); s.push_result(); s.call(46, 2)
        s.text('\x01translated slot 1'); s.text(''); s.push(-2); s.call(47, 3)
        s.label(done)
    rewriter.redirect(pc, ('format', argc), build)


def keyboard_guards(program):
    """The pcs of selector-1 build queries (32(1)) that guard keyboard name entry: a text entry (49) follows within
    KEYBOARD_WINDOW instructions. Selector 1 names the platform, and the stories branch on it: 1 plays each minigame-arena
    round as New Rules' own timed choices (the smartphone versions' word games use their words), announces "you'll be
    playing as..." and offers the survey, but picks a name from a list where 2 types one. The smartphone versions follow
    platform 1 except that they type the name, so these queries answer 2 and every other answers 1."""
    instructions = program.instructions
    return {i.pc for i in instructions
            if i.opcode == 0x1f and i.operand >> 8 == 32 and pushed_values(program, i.pc, 1)[0] == 1
            and any(j.opcode == 0x1f and j.operand >> 8 == 49 for j in instructions[i.pc:i.pc + KEYBOARD_WINDOW])}


@dataclass
class WordGame:
    """A minigame round New Rules plays as timed choices: `rounds` jumping-cursor choices under `title`, returning
    (in B) how many good options were picked."""
    rounds: int
    title: int
    good: list
    bad: list


def word_games(program):
    """{function start: WordGame} for each round function: a function whose incremental choice (12) has a jumping
    cursor. Each one runs alone in a VM once per option value (every answer the same), which tells which answers it
    counts and how many rounds it plays, whatever its shape; one that doesn't count answers all-or-nothing is left as
    choices. The smartphone versions play these rounds as SHS word games (71) with the same words."""
    instructions = program.instructions
    starts = sorted(i.pc for i in instructions if i.opcode == 0x48)
    halts = [i.pc for i in instructions if i.opcode == 0x33]
    found = {}
    for i in instructions:
        if i.opcode != 0x1f or i.operand >> 8 != 12 or i.operand & 255 != 3 or not halts:
            continue
        title, interval, _ = pushed_values(program, i.pc, 3)
        start = max((s for s in starts if s <= i.pc), default=None)
        if title is None or interval is None or interval <= 0 or start is None or start in found:
            continue
        first = _play_round(program, start, halts[0], 0)
        if first is None:
            continue
        options = first[1]
        results = {value: _play_round(program, start, halts[0], value) for _, value in options}
        if any(r is None for r in results.values()):
            continue
        count = max(r[0] for r in results.values())
        if count <= 0 or any(r[0] not in (0, count) for r in results.values()):
            continue
        found[start] = WordGame(count, title, [text for text, value in options if results[value][0] == count],
                                [text for text, value in options if results[value][0] == 0])
    return found


def _play_round(program, start, halt, answer):
    """(B, options of the first choice) after running the function at `start` with every choice answered `answer`."""
    vm = KiwiVM(replace(program, main_words=program.main_words + (0,) * program.gap_count, gap_count=0))
    vm._push(halt - 1)                                  # its RETURN resumes one past the saved pc: the halt
    vm.pc = start
    options = []
    for _ in range(400):
        try:
            stop = vm.run(100000)
        except VMError:
            return None
        if stop.kind == StopKind.HALT:
            return vm.b, options
        if stop.kind != StopKind.YIELD:
            return None
        if stop.yield_id == 13 and len(stop.args) >= 2 and len(options) < 8 and not any(
                value == stop.args[1] for _, value in options):
            options.append((stop.args[0], stop.args[1]))
        vm.resume(answer if stop.yield_id == 14 else 0)
    return None


def word_lists(program, game, twin_games=()):
    """The good and bad words for SHS 71: the round's own options, then any extra words of the smartphone twin's word
    game for the same round (one sharing a word), as EA filled them out. SHS deals one good and two different bad
    words plus a fourth of either kind, so it needs at least two good and three bad entries (MINIGAMES.md); a list
    still short repeats its words."""
    key = lambda word: re.sub(r'[^a-z0-9]+', '', word.lower())
    good = [text_at(program, a) for a in game.good]
    bad = [text_at(program, a) for a in game.bad]
    ours = {key(w) for w in good + bad}
    for twin_good, twin_bad in twin_games:
        if ours & {key(w) for w in twin_good + twin_bad}:
            good += [w for w in twin_good if key(w) not in ours]
            bad += [w for w in twin_bad if key(w) not in ours]
            break
    pad = lambda words, least: (words * least)[:max(least, len(words))]
    return pad(good, WORD_GAME_GOOD), pad(bad, WORD_GAME_BAD)


def word_game(s, program, game, twin_games=(), player=True):
    """The body replacing a round function: SHS 71 (title, description, good words, bad words, duration, character,
    portrait mode, refresh) as the smartphone versions call it, then B = good answers: all `rounds` at the twins' pass
    score, else in proportion, so a story's tiers still read the result."""
    full, done = s.label(), s.label()
    good, bad = word_lists(program, game, twin_games)
    s.text(CHOICE_TITLE); s.push(game.title); s.text('|'.join(good)); s.text('|'.join(bad))
    s.push(WORD_GAME_MS)
    if player:
        push_player(s)
    else:
        s.push(NARRATOR)
    s.push(1); s.push(WORD_GAME_REFRESH_MS)
    s.call(71, 8)
    s.push_result(); s.push(WORD_GAME_PASS); s.emit(0x0d); s.jump_if_nonzero(full)
    s.push_result(); s.push(game.rounds); s.emit(0x52); s.push(WORD_GAME_PASS); s.emit(0x53); s.jump(done)
    s.label(full); s.push(game.rounds)
    s.label(done); s.emit(0x04)                         # B, which the caller reads


# -- Built-in stories (King of Diss) ----------------------------------------------------------------------------------
KING_OF_DISS = range(25001, 25008)      # its scripts in res_large.pud (and in the full Java builds)
LIBRARY = 25200                         # the minigame library a built-in story calls into (linked, never translated)
STREAM = 48                             # the compact dialogue stream (expand_streams)
# The library's games that King of Diss calls, by entry PC (its calls pass their intro text, a target score and 40 s):
# the Rhyme battle ("match words that rhyme, son!"), the Rhythm game ("don't hit the wrong notes..."), the team battle's
# beat boxing, and the face picker ("select your face.").
LIBRARY_ENTRIES = {32611: 'rhyme', 31473: 'rhythm', 28903: 'beat boxing', 28201: 'faces'}
LIBRARY_GAME_MS = 30000                 # the library plays 40 s; a KiWi word holds 32,767 ms at most
RHYME_PROMPT = '`%s` rhymes with...'    # the library string before its rhyme pairs' words
RHYME_END = 'rhyming'                   # and the one after them
# The arena games without words of their own, played as SHS word games: (banner, good words, bad words). Rhythm's
# good and bent notes, and beat boxing's sounds, as the story's lines write them.
WORDLESS_GAMES = {
    'rhythm': ('Rhythm!', ('beat', 'groove', 'flow', 'bass', 'tempo', 'rhythm'),
               ('bent note', 'off-key', 'screech', 'clunk', 'sour note', 'static')),
    'beat boxing': ('Beat boxing!', ('ba-dum', 'wicky', 'boots', 'cats', 'boom', 'tss'),
                    ('la la la', 'achoo', 'meow', 'hiccup', 'shh', 'moo')),
}
RHYME_BANNER = 'Speed diss!'
# The speed disses play as the Lite builds' (King of Diss Lite, script 25001's loop): a timed choice per round under
# their prompt, ten hits to finish, three misses to lose, 3 s a round padded 30% as New Rules pads its limits.
SPEED_DISS_PROMPT = 'Flow: %d/10\nMiss: %d/3\nRhymes with { %s {'      # a menu's description shows no emphasis
SPEED_DISS_HITS, SPEED_DISS_MISSES = 10, 3
SPEED_DISS_ROUNDS = SPEED_DISS_HITS + SPEED_DISS_MISSES - 1
SPEED_DISS_MS = 3900
RIGHT_TRACK, WRONG_TRACK = 13, 1                         # FEEDBACK_TRACKS: New Rules' right and wrong jingles


def read_builtin(source, scripts=KING_OF_DISS, title='King of Diss', download_id=1):
    """A built-in story from New Rules' res_large.pud (`source`: resources by ID, nr_art.load) as an Episode, its compact
    dialogue streams written out (expand_streams) and the minigame library it calls kept beside it."""
    library = decode_program(source[LIBRARY]) if LIBRARY in source else None
    boundary = library.previous_data_count if library is not None else None
    return Episode(download_id, title, {rid: expand_streams(decode_program(source[rid]), boundary)
                                        for rid in scripts}, library)


# The Lite Java builds' condensed King of Diss: one script, its text in a string table (script ID + 50) that scripts
# address by index (r.java b(int)), the number of strings in its header. Its data keeps text indices in two tables, found
# through pointer words: the character records (36 words, the name in word 1) and the speed-diss rounds (6 words: the
# number of options, the target word, the options).
LITE_SCRIPT, LITE_TEXT = 25001, 25051
LITE_TABLES = {958: (36, 21, lambda record: (1,)),
               961: (6, 30, lambda record: range(1, 2 + record[0]))}
# Where each service takes text: argument positions, or a rule for a leading negative mode word (dialogue, names,
# formats, text entry).
TEXT_ARGUMENTS = {43: (1,), 11: (1, 2), 12: (1,), 13: (1,), 30: (1, 2), 10: (1,), 66: (1,), 17: (1, 2), 18: (1, 2),
                  19: (2,), 28: (1, 2), 9: (1, 2), 1: (2,), 2: (1, 2), 3: (1,), 4: (1,),
                  40: 'mode', 41: 'mode', 42: 'mode', 5: 'mode', 49: 'mode'}
STACK_EFFECTS = {0x1a: (0, 1), 0x1b: (0, 2), 0x5a: (0, 1), 0x5b: (0, 1), 0x40: (0, 1), 0x41: (0, 1), 0x23: (0, 1),
                 0x5f: (0, 1), 0x60: (0, 1), 0x61: (0, 1), 0x62: (0, 1), 0x21: (0, 1), 0x07: (0, 1), 0x08: (0, 1),
                 0x3f: (1, 1), **{op: (2, 1) for op in (0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x11, 0x12,
                                                       0x50, 0x51, 0x52, 0x53, 0x54)}}


def read_lite(source, title='King of Diss Lite', download_id=100, tables=LITE_TABLES):
    """The Lite builds' King of Diss (`source`: a Lite jar's resources, nr_art.load) as an Episode whose text lives in
    its data, as New Rules' own scripts keep it: the strings are appended after the extra bank, and each index that
    reaches a text argument becomes that string's address (constant pushes, traced through the stack, and LITE_TABLES'
    fields). Dynamic strings (32757 and up) and -1 stay as they are."""
    from exp_runtime.decode.bytecode import BytecodeInstruction
    from kiwi_rewrite import word
    program = decode_program(source[LITE_SCRIPT])
    table = source[LITE_TEXT]
    count = struct.unpack_from('>h', table, 2)[0]
    strings = [s.decode('cp1252') for s in table[6:].split(b'\0')[:count]]
    extra = list(program.extra_words)
    base = len(program.main_words) + program.gap_count
    address = []
    for text in strings:
        data = text.encode('latin-1', 'replace') + b'\0'
        data += b'\0' * (len(data) % 2)
        address.append(base + len(extra))
        extra.extend(data[i] << 8 | data[i + 1] for i in range(0, len(data), 2))
    if base + len(extra) >= 0x7bf5:
        raise TranslateError('the Lite text reaches the VM stack')
    code = [(i.opcode, i.operand) for i in program.instructions]
    packed = {}                                             # a PUSH2's pc -> its two values, those that are text moved
    for i in program.instructions:
        if i.opcode != 0x1f or (i.operand >> 8) not in TEXT_ARGUMENTS:
            continue
        service, argc = i.operand >> 8, i.operand & 255
        producers = argument_producers(program, i.pc, argc)
        positions = TEXT_ARGUMENTS[service]
        if positions == 'mode':
            first = 2 if producers[0] is not None and signed(producers[0][1]) < 0 else 1
            positions = {40: (first,), 41: (first, first + 1), 42: (first, first + 1), 5: (first,),
                         49: (first, first + 1, first + 2)}[service]
        for k in positions:
            if k > argc or producers[k - 1] is None:
                continue
            pc, value, half = producers[k - 1]
            if 0 <= value < count:
                if code[pc][0] == 0x1b:
                    # Two bytes in one word: it can't hold an address, so it becomes a jump to two full pushes.
                    operand = program.instructions[pc].operand
                    pair = packed.setdefault(pc, [signed(operand & 255 | (0xff00 if operand & 128 else 0)),
                                                  signed(operand >> 8 | (0xff00 if operand & 0x8000 else 0))])
                    pair[half] = address[value]
                else:
                    code[pc] = (0x1a, word(address[value]))
    for pc, (low, high) in packed.items():
        code[pc] = (0x29, len(code))
        code.extend([(0x1a, word(low)), (0x1a, word(high)), (0x29, pc + 1)])
    words = list(program.main_words)
    for pointer, (stride, records, fields) in tables.items():
        start = (words + [0] * program.gap_count + list(program.extra_words))[pointer]
        for r in range(records):
            record = words[start + r * stride:start + (r + 1) * stride]
            for f in fields(record):
                if 0 <= record[f] < count:
                    words[start + r * stride + f] = address[record[f]]
    instructions = tuple(BytecodeInstruction(pc, 0, op, operand) for pc, (op, operand) in enumerate(code))
    # Without a gap, the extra bank follows the main one directly: as main data the strings keep their addresses and
    # are cased with the rest (casing.recase_program reads the main bank).
    if program.gap_count:
        raise TranslateError('the Lite script has a gap between its data banks')
    program = decode_program(replace(program, main_words=tuple(words + extra), extra_words=(),
                                     instructions=instructions).to_bytes())
    return Episode(download_id, title, {LITE_SCRIPT: program}, text_addresses={LITE_SCRIPT: set(address)})


def signed(value):
    return value - 0x10000 if value > 0x7fff else value


def formatted_title(program, pc, argc):
    """The format string's address when the call's first argument is a format's result (5 then PUSH_R, "%s morning."
    for King of Diss's day cards), else None."""
    producer = argument_producers(program, pc, argc, every=True)[0]
    if producer is None or program.instructions[producer[0]].opcode != 0x21 or producer[0] == 0:
        return None
    call = program.instructions[producer[0] - 1]
    if call.opcode != 0x1f or call.operand >> 8 != 5:
        return None
    arguments = argument_producers(program, call.pc, call.operand & 255)
    first = arguments[0]
    if first is not None and first[1] is not None and signed(first[1]) < 0:   # a leading dynamic slot
        first = arguments[1] if len(arguments) > 1 else None
    return first[1] if first is not None else None


def argument_producers(program, pc, argc, every=False):
    """For each argument of the call at `pc`: (instruction index, value, which byte of a PUSH2 or None) when a constant
    push made it, else None; with `every`, (instruction index, None, None) for any other single push that made it.
    Traced back through the stack effects of straight-line code (STACK_EFFECTS), so a constant pushed before other
    arguments' arithmetic is still found; anything else ends the trace."""
    pending = list(range(1, argc + 1))                      # what the stack holds, bottom to top: argument numbers
    found = [None] * argc
    position = pc - 1
    while pending and position >= 0:
        instruction = program.instructions[position]
        effect = STACK_EFFECTS.get(instruction.opcode)
        if instruction.opcode == 0x1f:                      # a host call takes its arguments and pushes nothing
            effect = (instruction.operand & 255, 0)
        if effect is None:
            break
        pops, pushes = effect
        # A PUSH2 may also push a value below the arguments ("0, 40" before a title card's 40, 41, 25, 0).
        produced = [None] * max(0, pushes - len(pending)) + pending[max(0, len(pending) - pushes):]
        del pending[max(0, len(pending) - pushes):]
        if instruction.opcode == 0x1a and produced[0] is not None:
            found[produced[0] - 1] = (position, instruction.operand, None)
        elif instruction.opcode in (0x5a, 0x5b) and produced[0] is not None:
            found[produced[0] - 1] = (position, instruction.opcode - 0x5a, None)
        elif instruction.opcode == 0x1b:
            for half, (value, number) in enumerate(zip((instruction.operand & 255, instruction.operand >> 8), produced)):
                if number is not None:
                    found[number - 1] = (position, value - 256 if value > 127 else value, half)
        elif every and pushes == 1 and produced[0] is not None:
            found[produced[0] - 1] = (position, None, None)
        pending.extend([None] * pops)
        position -= 1
    return found


def expand_streams(program, library_data=None):
    """`program` with each compact dialogue stream (48: a data address; SHS_NEW_RULES_ENGINE.md section 7.1) written
    out as the New Rules calls it stands for, in a block after the code: the call becomes a jump there, and the block
    drops the call's argument, makes the calls and jumps back after it. The streams are static data, so this is exact.
    New instructions only follow the code, so no address moves. A read of the linked library's data (an address from
    `library_data`, its first word, on: the team battle passes three of its variables to the library) reads 0."""
    from exp_runtime.decode.bytecode import BytecodeInstruction
    from kiwi_rewrite import word
    code = [(0x1a, 0) if library_data is not None and i.opcode == 0x40 and i.operand >= library_data
            else (i.opcode, i.operand) for i in program.instructions]
    for i in program.instructions:
        if i.opcode != 0x1f or i.operand >> 8 != STREAM:
            continue
        address = pushed_values(program, i.pc, 1)[0]
        if address is None:
            raise TranslateError(f'a dialogue stream at {i.pc} has no constant address')
        block = [(0x15, None)] + [(op, None if operand is None else word(operand))
                                  for op, operand in stream_calls(program.main_words, address)] + [(0x29, i.pc + 1)]
        code[i.pc] = (0x29, len(code))
        code.extend(block)
    if code == [(i.opcode, i.operand) for i in program.instructions]:
        return program
    instructions = tuple(BytecodeInstruction(pc, 0, op, operand) for pc, (op, operand) in enumerate(code))
    return decode_program(replace(program, instructions=instructions).to_bytes())


def stream_calls(words, address):
    """The New Rules calls (opcode, operand) one dialogue stream stands for (f.java a(): the commands, low nibble):
    0-5 a character speaks with that expression (40; box mode -4 or below is narration, 43), 6 narration (43) or a
    line under a name (41), 7 several characters under a name (42), 8 the stage (44/45), 9 a default expression (24),
    10 character property 630 (22), 11 the location (35), 12 engine mode 11 (47), 13 music (7), 14 a character's bounce
    (no SHS counterpart, left out), 15 the end."""
    out = []

    def push(*values):
        out.extend((0x1a, v) for v in values)

    def call(service, argc):
        out.append((0x1f, service << 8 | argc))

    def who(value):                                         # f.java b(): 0xFF is nobody
        return -1 if value & 0xff == 0xff else value & 0xff

    o = address
    while True:
        w = words[o]
        o += 1
        command = w & 15
        if command <= 5:
            mode, character, text = -(w >> 4 & 7), w >> 7 & 0xff, words[o]
            o += 1
            if mode <= -4:
                push(text); call(43, 1)
            elif mode in (-2, -3):
                push(mode, text, character, command); call(40, 4)
            else:
                push(text, character, command); call(40, 3)
        elif command == 6:
            if w >> 4 & 1:
                mode, character, name, text = -(w >> 5 & 7), who(w >> 8), words[o], words[o + 1]
                o += 2
                prefix = (mode,) if mode in (-2, -3) else ()
                push(*prefix, name, text, character); call(41, len(prefix) + 3)
            else:
                push(words[o]); call(43, 1)
                o += 1
        elif command == 7:
            count = w >> 7 & 7
            people = words[o:o + count]
            name, text = words[o + count], words[o + count + 1]
            o += count + 2
            push(name, text)
            for person in people:
                push(who(person), person >> 8 & 7)
            call(42, 2 + 2 * count)
        elif command == 8:
            count = 3 if w >> 4 & 1 else 2
            people = [who(part) for value in words[o:o + count] for part in (value, value >> 8)]
            o += count
            push(*people); call(44 if count == 2 else 45, len(people))
        elif command == 9:
            push(w >> 7 & 0xff, w >> 4 & 7); call(24, 2)
        elif command == 10:
            push(w >> 6 & 0xff, 630, w >> 4 & 3); call(22, 3)
        elif command == 11:
            push(w >> 4 & 7, w >> 7 & 63); call(35, 2)
        elif command == 12:
            push(11); call(47, 1)
        elif command == 13:
            push(w >> 4 & 15, 0); call(7, 2)
        elif command == 14:
            o += 1
        else:
            return out


def rhyme_families(library):
    """The library's rhyme pairs (its word table: pairs of string addresses from cat/fat to the RHYME_END string),
    grouped into families that rhyme: pairs sharing a word, and words alike once their first consonants go ("chat"
    and "rat", "school" and "tool"). Largest first, each in the table's order."""
    import casing
    base = library.previous_data_count
    texts = {address + base: text for address, text in casing.strings(library)}
    start = next(a for a, t in texts.items() if t == RHYME_PROMPT)
    words = library.main_words
    table = words.index(min(a for a in texts if a > start))          # the table starts with the first word's address
    pairs = []
    while texts.get(words[table]) != RHYME_END:
        pairs.append((texts[words[table]], texts[words[table + 1]]))
        table += 2
    return rhyme_groups(pairs)


def rhyme_groups(pairs):
    """Rhyming pairs grouped into families: pairs sharing a word, and words alike once their first consonants go.
    Largest first, each in the pairs' order."""
    rhyme = lambda word: re.sub(r'^[^aeiou]*(?=[aeiouy])', '', word.split('-')[-1]) or word
    family = {}
    order = []
    for pair in pairs:
        for word in pair:
            if word not in order:
                order.append(word)
    parent = {word: word for word in order}

    def root(word):
        while parent[word] != word:
            word = parent[word]
        return word
    for a, b in pairs:
        parent[root(b)] = root(a)
    for word in order:
        family.setdefault(rhyme(word), word)
        parent[root(word)] = root(family[rhyme(word)])
    groups = {}
    for word in order:
        groups.setdefault(root(word), []).append(word)
    return sorted(groups.values(), key=lambda group: -len(group))


def library_game(s, kind, index, library, player=True, music=False):
    """The body replacing a call into the minigame library, then B = the result, as the library leaves it (a score, or
    the face's index): the speed disses as the Lite builds play theirs (speed_diss), Rhythm and beat boxing as SHS's
    word game (71), the face picker as SHS's portrait picker (78)."""
    if kind == 'rhyme':
        speed_diss(s, rhyme_rounds(library, index), player, music)
        return
    if kind == 'faces':
        # (title, subtitle, prompt, count, candidate characters, flag): the candidates' looks are the faces offered.
        # SHS's picker shows one line, so it takes the short prompt ("select your face.").
        s.arg(3); s.arg(4); s.arg(5); s.call(78, 3)
    else:
        banner, good, bad = WORDLESS_GAMES[kind]
        s.text(banner); s.arg(s.argc - 1)                   # its intro text
        s.text('|'.join(good)); s.text('|'.join(bad)); s.push(LIBRARY_GAME_MS)
        if player:
            push_player(s)
        else:
            s.push(NARRATOR)
        s.push(1); s.push(WORD_GAME_REFRESH_MS)
        s.call(71, 8)
    s.push_result(); s.emit(0x04)                           # B, which the caller reads


def rhyme_rounds(library, index):
    """The index-th speed diss's rounds (SPEED_DISS_ROUNDS): (target, options, the rhyme's place among them). Each
    round is a target and one word of its rhyme family, among two or three words of other families; the pairs are
    dealt out in a fixed shuffle, so no two speed disses share a round."""
    import random
    families = rhyme_families(library)
    pairs = [(f[a], f[b]) for f in families for a in range(len(f)) for b in range(a + 1, len(f))]
    deal = random.Random(LIBRARY)
    deal.shuffle(pairs)
    family_of = {word: n for n, f in enumerate(families) for word in f}
    words = [word for f in families for word in f]
    rounds = []
    for target, rhyme in pairs[index * SPEED_DISS_ROUNDS:(index + 1) * SPEED_DISS_ROUNDS]:
        others = [w for w in words if family_of[w] != family_of[target]]
        options = deal.sample(others, 2 + len(rounds) % 2) + [rhyme]
        deal.shuffle(options)
        rounds.append((target, options, options.index(rhyme)))
    return rounds


def speed_diss(s, rounds, player=True, music=False):
    """A speed diss as the Lite builds play theirs: timed choices, "Flow: n/10 Miss: n/3, rhymes with `cat`", each the
    rhyme among non-rhymes, until ten hits or three misses (or the rounds run out). New Rules' right and wrong jingles
    follow each answer when the music is rendered (the answer hints know them). B = the hits, which the story reads
    against its own target (7). The rounds are written out one after another."""
    hits = s.rewriter.words([0, 0])
    misses = hits + 1
    end = s.label()

    def add(address):
        s.push(address); s.emit(0x40, address); s.push(1); s.emit(0x50); s.emit(0x3e); s.emit(0x15)

    for address in (hits, misses):
        s.push(address); s.push(0); s.emit(0x3e); s.emit(0x15)
    for target, options, answer in rounds:
        miss, done = s.label(), s.label()
        s.emit(0x40, hits); s.push(SPEED_DISS_HITS); s.emit(0x0d); s.jump_if_nonzero(end)
        s.emit(0x40, misses); s.push(SPEED_DISS_MISSES); s.emit(0x0d); s.jump_if_nonzero(end)
        s.text(SPEED_DISS_PROMPT); s.emit(0x40, hits); s.emit(0x40, misses); s.text(target.capitalize())
        s.call(0, 4)
        s.text(RHYME_BANNER); s.text('|'.join(option.capitalize() for option in options)); s.push_result()
        s.push(SPEED_DISS_MS); s.push(-1)                   # time out: no answer, a miss
        if player:
            push_player(s)
        else:
            s.push(NARRATOR)
        s.push(-1); s.push(1)
        s.call(1, 8)
        s.push_result(); s.push(answer); s.emit(0x0a); s.jump_if_zero(miss)
        add(hits)
        if music:
            s.push(MUSIC_BASE + RIGHT_TRACK); s.push(0); s.call(80, 2)
        s.jump(done)
        s.label(miss)
        add(misses)
        if music:
            s.push(MUSIC_BASE + WRONG_TRACK); s.push(0); s.call(80, 2)
        s.label(done)
    s.label(end)
    s.emit(0x40, hits); s.emit(0x04)                        # B, which the caller reads


def library_calls(program):
    """[(pc, entry, argument count)] of the program's calls into the linked library: a JUMP past its own code (after a
    SAVE_RETURN), its arguments dropped by the ADJUST_SP that follows."""
    end = len(program.instructions)
    out = []
    for k, i in enumerate(program.instructions):
        if i.opcode == 0x29 and i.operand >= end:
            after = program.instructions[k + 1] if k + 1 < end else None
            out.append((i.pc, i.operand, after.operand if after is not None and after.opcode == 0x19 else 0))
    return out


def build_query(rewriter, pc, argc, context):
    """32: (selector) -> New Rules' constants in R (R is only set by LOAD_R or a host call, so one LOAD_R each).
    Selector 1 answers 1, or 2 where it guards keyboard name entry (keyboard_guards)."""
    answers = {**BUILD, **({1: 2} if pc in context['keyboard_guards'] else {})}

    def build(s):
        done = s.label()
        for selector, value in answers.items():
            other = s.label()
            s.arg(1); s.push(selector); s.emit(0x0a); s.jump_if_zero(other)
            s.result(value); s.jump(done)
            s.label(other)
        s.result(0)
        s.label(done)
    rewriter.redirect(pc, ('build_query', answers[1]), build)


def end_episode(rewriter, pc, argc, context):
    """28: (title, text, flag): New Rules' closing screen and end -> SHS's message panel, then the episode exit."""
    rewriter.redirect(pc, 'end', lambda s: (s.arg(1), s.arg(2), s.push(0), s.call(33, 3), s.call(7, 0)))


def transition(rewriter, pc, argc, context):
    """47: (engine mode). The paired stories show SHS's transition 20 where New Rules sets mode 11."""
    def build(s):
        other = s.label()
        s.arg(1); s.push(11); s.emit(0x0b); s.jump_if_nonzero(other)
        s.push(20); s.call(16, 1)
        s.label(other); s.result(0)
    rewriter.redirect(pc, 'transition', build)


def pushed_values(program, pc, argc):
    """The call's arguments when each was pushed as a constant right before it (None for any that wasn't)."""
    values, position = [], pc - 1
    while len(values) < argc and position >= 0:
        instruction = program.instructions[position]
        pushes = pushes_block(program, position) if instruction.opcode == 0x29 else None
        if pushes is not None:                              # read_lite's two full pushes in place of a PUSH2
            values.extend(reversed(pushes))
        elif instruction.opcode == 0x1a:
            values.append(instruction.operand - 0x10000 if instruction.operand > 0x7fff else instruction.operand)
        elif instruction.opcode == 0x1b:
            low, high = instruction.operand & 255, instruction.operand >> 8
            values.extend([high - 256 if high > 127 else high, low - 256 if low > 127 else low])
        elif instruction.opcode in (0x5a, 0x5b):
            values.append(instruction.opcode - 0x5a)
        else:
            break
        position -= 1
    values = values[:argc]
    return [None] * (argc - len(values)) + values[::-1]


def pushes_block(program, position):
    """The values a JUMP at `position` pushes when it enters a block of constant pushes that jumps back to the next
    instruction (read_lite's replacement for a PUSH2 holding text), in push order; else None."""
    instructions = program.instructions
    target = instructions[position].operand
    if not position < target < len(instructions):
        return None
    values = []
    for instruction in instructions[target:]:
        if instruction.opcode == 0x1a:
            values.append(instruction.operand - 0x10000 if instruction.operand > 0x7fff else instruction.operand)
        elif instruction.opcode == 0x29 and instruction.operand == position + 1 and values:
            return values
        else:
            return None
    return None


def constant_text(program, rewriter, pc, index, argc):
    """The text of argument `index` when it is pushed as a constant before the call, else None."""
    address = pushed_values(program, pc, argc)[index - 1]
    if address is None:
        return None
    words = program.main_words
    if not 0 <= address < len(words):
        return None
    out = bytearray()
    for w in words[address:address + 200]:
        for byte in (w >> 8, w & 255):
            if byte == 0:
                return out.decode('latin-1')
            out.append(byte)
    return None


HANDLERS = {40: dialogue, 41: named_dialogue, 42: named_dialogue, 43: narration, 11: choice, 12: begin_choice, 13: add_option, 14: show_choice,
            49: text_entry, 30: title_card, 35: location, 7: music, 25: look, 26: copy_look, 24: default_expression,
            5: format_text, 28: end_episode, 47: transition, 32: build_query,
            20: owned_number, 21: owned_number, 22: owned_number, 23: owned_number}
