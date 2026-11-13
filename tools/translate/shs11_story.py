"""SHS '11's stories as smartphone SHS episodes: their KiWi scripts with every host call rewritten for SHS's services.

'11's own services and SHS's differ, but its machine, script-queue and scene-table layout are SHS's. Each story opens with a
setup script that defines the cast and walks a table of (scene, script), as an SHS episode's 25001 does: it queues itself
and the next scene's script (18, SHS 10), then halts. So that script is 25001 here and the others follow it.

What a host call becomes is in HANDLERS. Three things differ underneath:

- **Numbers.** An unset '11 number reads -1 and an SHS one 0, and the scripts test for -1, so a number is stored here plus
  one (`number`, `set_number`).
- **Relationships.** '11's character key 4000 runs 0-7, with -1 for none: 0-3 show 4-1 skulls and 4-7 show 1-4 smileys, or
  hearts for the one character key 4001 names (`dc`, `co.a(int, dc)`, `b.n`). SHS's key 407 shows the same icons from
  negative numbers up, and key 629 hides them, so 407 = value - 4, 601 = key 4001 and 629 = no value.
- **Minigames.** The rounds (50-52) go, and each game (49) plays what the smartphone has at that spot (FALLBACKS).
- **Sound.** Effects (19) stay '11's own, and the smartphone's music goes in before the lines it comes before
  (`smartphone_music`). The player's Smartphone Music switch picks whether it's heard (profile SMARTPHONE_MUSIC_PACKS).

Nothing here keeps art: a story reads its pictures and music from the addon (shs11.build_addon).
"""
import collections
from dataclasses import dataclass
import re

from exp_runtime.addons import RESOURCE as ADDON_RECORD, requires_bytes
from exp_runtime.episode_version import RESOURCE as VERSION_RECORD, version_bytes
from exp_runtime.decode.bytecode import decode_program
from exp_runtime.exp import ExpArchive, Metadata, encode_exp
from exp_runtime.vm import signed16

from exp_runtime.shs11_services import SHS11_MEMORY, SHS11_MINIGAMES_QUERY, SHS11_REFLEX
from kiwi_rewrite import Rewriter
import shs11

# The stories' version (episode_version.py): a newer one replaces an older copy on import, and a rebuild at the same
# version replaces it too. Raise it when a build must never be replaced by an earlier one.
STORY_VERSION = 1
FIRST_SCRIPT = 25001                    # where SHS starts an episode
TITLE_SUFFIX = ' (SHS11)'
NARRATOR = 199                          # '11 narrates with no speaker; SHS needs a character (as newrules.NARRATOR)
PLAYER_KEY = 31601                      # SHS global number holding the player (4), for what '11 asks of its key 2003
BACKGROUND_KEY = 31602                  # SHS global number holding the picture on show, for a grid's own background
THEME, RELATIONSHIP, LOVE_INTEREST, NO_BADGE = 651, 407, 601, 629   # SHS keys
RELATIONSHIP_11, LOVE_INTEREST_11 = 4000, 4001                      # '11's
RELATIONSHIP_ZERO = 4                   # the '11 value SHS's 0 means: one smiley
OBJECT_KIND = 3                         # a cast record's kind: 1 male, 2 female, 3 an object ("TV", "Phone")
CHOICE_PORTRAIT = 1
GAME_TITLE = 'Make Your Choice!'        # as '11's menus have it
LOOK_TITLE = 'Choose your look!'        # (gamelib entry 32; the scripts pass only the looks)
END_TITLE, END_TEXT, END_ARGUMENT = 'End of game', 'Thanks for playing!', 4000  # as the smartphone's closing message
NAME_PROMPT = ''                        # '11's name entry has only a title
# Story selector (19) -> the track it plays: all short cues, each played once. The scripts ask for these five. A selector
# picks a slot, and a slot picks an object of gamelib entry 5, where one is a second reference to another: selectors 0 and 2
# are the same sound, in the full builds' classes and the Italian one's alike (SHS_11_PLAN.md). shs11.SURPRISE_TRACK is that
# sound again under its own ID, as only selector 0 is the smartphone's "wrong" (TRANSLATED_FEEDBACK_MUSIC).
CUE_TRACKS = {0: 2, 1: 0, 2: shs11.SURPRISE_TRACK, 3: 4, 4: 3}
MUSIC_SERVICES = (80, 81)                # what the smartphone's music is, of its services (smartphone_music)
GAME_SONG, GAME_SONG_FADE = 8201, 1000  # the smartphone's song for its grids: looped, then faded out (owner, 2026-11-04: every game has it)
MUSIC_REACH = 3                          # how many lines '11 lacks a music call may pass to find one it has
WORD_GAME_MS, WORD_GAME_REFRESH_MS, WORD_GAME_PASS = 20000, 3000, 6     # as the smartphone calls service 71
WON, MIDDLE, LOST = 2, 1, 0              # 49's results: 2 is >= 98% of the target, 1 above 75%; only 2 is a win in most
REFLEX_ROW = 9                          # words a round takes in a script's Reflex table
MEMORY_SECONDS = 60                     # as the scripts' routine calls service 50
GRID_FILLER = 'wb'                      # the extra letters the smartphone's grids add to a word's own
GRID_FRAME = dict(seconds=45, target=1800, deadline=10000, bonus=5000)  # its letter grids' usual settings


class StoryError(ValueError):
    pass


@dataclass(frozen=True)
class Story:
    """One of '11's stories: its scripts, setup first, and its games' stand-ins, by (script, the site of its 49)."""
    title: str
    number: int
    scripts: range
    fallbacks: dict


@dataclass(frozen=True)
class TwinWords:
    """The smartphone's timed word game at that spot: its call to 71. `tiers`: the game's three results count, as the
    Superstore's does: a score this close below a win is 1."""
    script: int
    pc: int
    tiers: int = 0


@dataclass(frozen=True)
class TwinGrid:
    """The smartphone's letter grid at that spot: its call to 96."""
    script: int
    pc: int


@dataclass(frozen=True)
class OwnWords:
    """A timed word game where the smartphone has nothing."""
    description: str
    good: str
    bad: str


@dataclass(frozen=True)
class MemoryGrid:
    """A letter grid of the words of '11's Memory game, where the smartphone has nothing: the rounds' table in `word`."""
    word: int


STORIES = {
    # Numbered in '11's own order of them (e.java).
    'Best Party Ever': Story('Best Party Ever', 1, range(277, 288), {
        (278, 685): MemoryGrid(6483),           # Impressing the nerds: the smartphone has a talk
        (278, 828): MemoryGrid(6484),           # ...the preps
        (278, 958): MemoryGrid(6485),           # ...the punks
        (280, 449): MemoryGrid(15329),          # Angie's invitations: a choice
        (283, 1168): TwinGrid(25009, 94),       # The prop room
        (283, 1536): TwinWords(25009, 835),     # Wesley's robot costume
        (284, 1187): MemoryGrid(9857),          # Stalling Zach: a choice
        (284, 1919): TwinGrid(25008, 94),       # Sneaking to the frat house
        (285, 1110): TwinWords(25007, 528),     # The mall sale
        (286, 913): TwinWords(25011, 160, tiers=3),     # The Superstore shift
    }),
    'The New Girl': Story('The New Girl', 2, range(270, 277), {
        (271, 1032): TwinWords(25002, 92),      # Catching Sam
        (272, 1272): TwinGrid(25004, 82),       # Gym practice: the first of the smartphone's five
        (273, 2233): OwnWords('Roll down the hill!', 'Roll!|Tumble!', 'Crash!|Trip!|Stop!|Fall!'),
        (273, 3734): TwinGrid(25003, 90),       # The street race
        (273, 4005): MemoryGrid(16753),         # Talking Amanda into decaf
        (274, 565): TwinGrid(25005, 90),        # The cheer tryout
    }),
    'Foreign Exchange': Story('Foreign Exchange', 3, range(288, 292), {
        (290, 404): TwinWords(25002, 84),       # The Double Medusa exam
        (291, 601): TwinWords(25003, 237),      # Howard's dance
    }),
    'Lost Recipe': Story('Lost Recipe', 4, range(292, 296), {
        (293, 969): TwinGrid(25001, 120),       # Panicking with Spike: the grid, as service 70 picks it for this app
    }),
    'Secret Ingredient': Story('Secret Ingredient', 5, range(296, 300), {
        (297, 1052): TwinWords(25001, 98),      # Cheering up Ms. Rose
    }),
}


# -- reading the smartphone's calls ------------------------------------------------------------------------------------
def _pushes(instruction):
    """The values a constant push puts on the stack, or None. 0x1b packs two, low byte first."""
    if instruction.opcode == 0x1a:
        return [signed16(instruction.operand)]
    if instruction.opcode == 0x1b:
        low, high = instruction.operand & 255, instruction.operand >> 8 & 255
        return [low - 256 if low >= 128 else low, high - 256 if high >= 128 else high]
    if instruction.opcode in (0x5a, 0x5b):
        return [instruction.opcode - 0x5a]
    return None


def call_arguments(program, pc):
    """The constant arguments of the host call at `pc`, a load of a local (0x5f-0x62, 0x3f) reading what the function
    pushed for it on entry."""
    instructions = program.instructions
    count = instructions[pc].operand & 255
    start = max(i for i in range(pc) if instructions[i].opcode == 0x4a)
    local = []
    for instruction in instructions[start + 1:pc]:
        values = _pushes(instruction)
        if values is None:
            break
        local += values
    found, i = [], pc - 1
    while len(found) < count:
        values = _pushes(instructions[i])
        if values is not None:
            found[:0] = values
            i -= 1
        elif instructions[i].opcode == 0x3f and 0x5f <= instructions[i - 1].opcode <= 0x62:
            found.insert(0, local[instructions[i - 1].opcode - 0x5f])
            i -= 2
        else:
            raise StoryError(f'argument {count - len(found)} of the call at {pc} is not a constant')
    return found[-count:]


# -- what a story's calls become ---------------------------------------------------------------------------------------
def remember_line(s, i, context):
    """Store argument i (a text reference) as the last line shown, the question over a choice."""
    s.push(context['last_line']); s.arg(i); s.emit(0x3e); s.emit(0x15)


def dropped(rewriter, pc, argc, context):
    rewriter.redirect(pc, 'drop', lambda s: s.result(0))


def returns_one(rewriter, pc, argc, context):
    """28: the story's poll storage is ready; with 44 at 0, polls are never offered."""
    rewriter.redirect(pc, 'one', lambda s: s.result(1))


def set_number(s, owner, key, value):
    """The SHS calls for a '11 number: each is a callable pushing its word."""
    owner(); key(); value(); s.push(1); s.emit(0x50); s.call(52, 3)


def number_set(rewriter, pc, argc, context):
    """0: (owner, key, value), with what SHS itself reads for relationships."""
    def build(s):
        set_number(s, lambda: s.arg(1), lambda: s.arg(2), lambda: s.arg(3))
        other, done = s.label(), s.label()
        s.arg(2); s.push(RELATIONSHIP_11); s.emit(0x0a); s.jump_if_zero(other)
        relationship(s, lambda: s.arg(1), lambda: s.arg(3))
        s.jump(done)
        s.label(other)
        s.arg(2); s.push(LOVE_INTEREST_11); s.emit(0x0a); s.jump_if_zero(done)
        s.push(0); s.push(LOVE_INTEREST); s.arg(3); s.call(52, 3)
        s.label(done)
    rewriter.redirect(pc, 'set', build)


def relationship(s, character, value):
    """SHS's badge for a '11 relationship value: see the module's note."""
    character(); s.push(RELATIONSHIP); value(); s.push(RELATIONSHIP_ZERO); s.emit(0x51); s.call(52, 3)
    character(); s.push(NO_BADGE); value(); s.push(0); s.emit(0x0e); s.call(52, 3)


def number_get(rewriter, pc, argc, context):
    """1: (owner, key). A shim can only leave a constant in R, so this one leaves the value in B, and the push of R that
    follows every such call in the scripts becomes a push of B."""
    if rewriter.code[pc + 1] != (0x21, None):
        raise StoryError(f'the read at {pc} is not followed by a push of its result')
    rewriter.code[pc + 1] = (0x08, None)

    def build(s):
        s.arg(1); s.arg(2); s.call(53, 2)
        s.push_result(); s.push(1); s.emit(0x51); s.emit(0x04)
    rewriter.redirect(pc, 'get', build)


def player(rewriter, pc, argc, context):
    """4: (character) the player: SHS's primary speaker (74), with '11's own key 2003."""
    def build(s):
        s.arg(1); s.call(74, 1)
        s.push(PLAYER_KEY); s.arg(1); s.call(54, 2)
        set_number(s, lambda: s.push(0), lambda: s.push(2003), lambda: s.arg(1))
    rewriter.redirect(pc, 'player', build)


def push_player(s):
    s.push(PLAYER_KEY); s.call(55, 1); s.push_result()


def cast_member(rewriter, pc, argc, context):
    """5: (address of a cast record): name, bubble colour, hidden badge and look. '11's font shows names in capitals, so
    those its table has in lower case (`nicole`) get a capital. Each record is known here, so each gets its own branch."""
    def build(s):
        done = s.label()
        for address, character, kind, name, faces in context['cast']:
            other = s.label()
            s.arg(1); s.push(address); s.emit(0x0a); s.jump_if_zero(other)
            s.push(character); s.push(THEME); s.push(2 if kind == 2 else 1); s.call(52, 3)
            s.push(character); s.push(NO_BADGE); s.push(1); s.call(52, 3)
            s.push(character); s.text(name[:1].upper() + name[1:]); s.call(64, 2)
            s.push(character); s.push(-1 if faces is None else faces); s.call(72, 2)
            s.jump(done)
            s.label(other)
        s.label(done)
    rewriter.redirect(pc, ('cast', context['rid']), build)


def for_each(s, count, step, body):
    """Run `body(i)`, i pushing the running offset, for offsets 0, step... below `count`. The offset is a local."""
    s.push(0)
    top, end = s.label(), s.label()
    s.label(top)
    s.emit(0x41, 0); count(); s.emit(0x0e); s.jump_if_zero(end)
    body(lambda: s.emit(0x41, 0))
    s.emit(0x23, 0); s.emit(0x41, 0); s.push(step); s.emit(0x50); s.emit(0x3e); s.emit(0x15)
    s.jump(top)
    s.label(end)


def relationships(rewriter, pc, argc, context):
    """10: (words, address of (character, value) pairs): the story's opening relationships."""
    def build(s):
        def body(i):
            word = lambda offset: (s.arg(2), i(), s.push(offset), s.emit(0x50), s.emit(0x50), s.emit(0x3f))
            set_number(s, lambda: word(0), lambda: s.push(RELATIONSHIP_11), lambda: word(1))
            relationship(s, lambda: word(0), lambda: word(1))
        for_each(s, lambda: s.arg(1), 2, body)
    rewriter.redirect(pc, 'relationships', build)


def reset_numbers(rewriter, pc, argc, context):
    """11: (count, address of keys): each global set to 0."""
    def build(s):
        def body(i):
            set_number(s, lambda: s.push(0), lambda: (s.arg(2), i(), s.emit(0x50), s.emit(0x3f)), lambda: s.push(0))
        for_each(s, lambda: s.arg(1), 1, body)
    rewriter.redirect(pc, 'reset', build)


def stored_name(rewriter, pc, argc, context):
    """12: (character, `$KEY`, default): a name given in another story, or the default, in `$KEY` and on the character. '11
    also carries that character's looks and numbers over from a saved story; SHS's table only holds the name."""
    def build(s):
        s.arg(2); s.arg(3); s.push(-1); s.call(47, 3)
        s.push_result()                                     # a local: the next call replaces R
        s.arg(2); s.emit(0x41, 0); s.call(46, 2)
        s.arg(1); s.emit(0x41, 0); s.call(64, 2)
    rewriter.redirect(pc, 'stored_name', build)


def number_and_bit(s):
    """Locals: a '11 number from (owner, key) in 0, argument 3's bit's value in 1. Then it pushes whether the bit is set. Only
    a bag of up to 15 bits, or an unset number (-1, all set), comes here (script 287's), so a negative number has them all."""
    s.arg(1); s.arg(2); s.call(53, 2); s.push_result(); s.push(1); s.emit(0x51)
    s.push(s.rewriter.words([1 << bit for bit in range(15)])); s.arg(3); s.emit(0x50); s.emit(0x3f)
    yes, done = s.label(), s.label()
    s.emit(0x41, 0); s.push(0); s.emit(0x0e); s.jump_if_nonzero(yes)
    s.emit(0x41, 0); s.emit(0x41, 1); s.emit(0x53); s.push(2); s.emit(0x54); s.jump_if_nonzero(yes)
    s.push(0); s.jump(done)
    s.label(yes); s.push(1)
    s.label(done)


def bit_set(rewriter, pc, argc, context):
    """2: (owner, key, bit, 1 to set it or else clear it)."""
    def build(s):
        def changed():
            adding, end = s.label(), s.label()
            s.arg(4); s.push(1); s.emit(0x0a); s.jump_if_nonzero(adding)
            s.emit(0x41, 0); s.emit(0x41, 1); s.emit(0x51); s.jump(end)
            s.label(adding)
            s.emit(0x41, 0); s.emit(0x41, 1); s.emit(0x50)
            s.label(end)
        number_and_bit(s)
        done = s.label()
        s.emit(0x41, 2); s.arg(4); s.push(1); s.emit(0x0a); s.emit(0x0a); s.jump_if_nonzero(done)   # it already is
        set_number(s, lambda: s.arg(1), lambda: s.arg(2), changed)
        s.label(done)
    rewriter.redirect(pc, 'bit_set', build)


def bit_get(rewriter, pc, argc, context):
    """3: (owner, key, bit), left in B as number_get's."""
    if rewriter.code[pc + 1] != (0x21, None):
        raise StoryError(f'the read at {pc} is not followed by a push of its result')
    rewriter.code[pc + 1] = (0x08, None)

    def build(s):
        number_and_bit(s)
        s.emit(0x04)
    rewriter.redirect(pc, 'bit_get', build)


def copy_look(rewriter, pc, argc, context):
    """9: (to, from): the look the player chose."""
    rewriter.redirect(pc, 'copy_look', lambda s: (s.arg(1), s.arg(2), s.call(73, 1), s.push_result(), s.call(72, 2)))


def next_script(rewriter, pc, argc, context):
    """18: (script) queued to run after this one halts, last in first out as SHS 10's. The setup script queues itself
    first, with the flag the smartphone's 25001 gives itself."""
    first = context['first']

    def build(s):
        for service, *arguments in context['scene_music'] if context['rid'] == first else ():
            for argument in arguments:
                s.push(argument)
            s.call(service, len(arguments))
        s.arg(1); s.push(first); s.emit(0x51); s.push(FIRST_SCRIPT); s.emit(0x50)
        s.arg(1); s.push(first); s.emit(0x0a)
        s.call(10, 2)
    rewriter.redirect(pc, ('next_script', first), build)


def cue(rewriter, pc, argc, context):
    """19: (selector) a short cue, as an effect so that it never stops anything."""
    def build(s):
        done = s.label()
        for selector, track in CUE_TRACKS.items():
            other = s.label()
            s.arg(1); s.push(selector); s.emit(0x0a); s.jump_if_zero(other)
            s.push(shs11.MUSIC_BASE + track); s.call(79, 1); s.jump(done)
            s.label(other)
        s.label(done)
        s.result(0)
    rewriter.redirect(pc, 'cue', build)


def look_picker(rewriter, pc, argc, context):
    """22: (count, address of characters): SHS's portrait picker, which also answers with an index."""
    rewriter.redirect(pc, 'look_picker', lambda s: (s.text(LOOK_TITLE), s.arg(1), s.arg(2), s.call(78, 3)))


def thought_or_line(rewriter, pc, argc, context):
    """23: (mode, text, character, expression): only -2, a thought, changes anything; SHS has the same prefix."""
    def build(s):
        plain, done = s.label(), s.label()
        remember_line(s, 2, context)
        s.arg(1); s.push(-2); s.emit(0x0a); s.jump_if_zero(plain)
        s.push(-2); s.arg(2); s.arg(3); s.arg(4); s.call(13, 4); s.jump(done)
        s.label(plain)
        s.arg(2); s.arg(3); s.arg(4); s.call(13, 3)
        s.label(done)
    rewriter.redirect(pc, ('thought', context['rid']), build)


def line(rewriter, pc, argc, context):
    """24: (text, character, expression). A look's five faces are at its base in '11's own order, so an expression passes
    through."""
    def build(s):
        remember_line(s, 1, context)
        s.arg(1); s.arg(2); s.arg(3); s.call(13, 3)
    rewriter.redirect(pc, ('line', context['rid']), build)


def narration(rewriter, pc, argc, context):
    def build(s):
        remember_line(s, 1, context)
        s.arg(1); s.push(NARRATOR); s.call(13, 2)
    rewriter.redirect(pc, ('narration', context['rid']), build)


def choice(rewriter, pc, argc, context):
    """26: (title, `a|b`) -> SHS 1, the player's portrait beside it and the line before it as the question."""
    def build(s):
        s.arg(1); s.arg(2); s.emit(0x40, context['last_line'])
        s.push(-1); s.push(0); s.push(-2); s.push(-1); s.push(CHOICE_PORTRAIT)
        s.call(1, 8)
    rewriter.redirect(pc, ('choice', context['rid']), build)


def begin_choice(rewriter, pc, argc, context):
    """29: (title, limit in ms or -1, the option a limit picks, -1 for where the cursor rests, the first) -> SHS 2."""
    def build(s):
        s.arg(1); s.emit(0x40, context['last_line']); s.arg(2); s.select(3, {-1: 0})
        push_player(s); s.push(CHOICE_PORTRAIT)
        s.call(2, 6)
    rewriter.redirect(pc, ('begin_choice', context['rid']), build)


def add_option(rewriter, pc, argc, context):
    """30: (text, value) -> SHS 3."""
    rewriter.redirect(pc, 'add_option', lambda s: (s.arg(1), s.arg(2), s.push(1), s.call(3, 3)))


def show_choice(rewriter, pc, argc, context):
    """31 -> SHS 4, unshuffled: '11 keeps its options in order."""
    rewriter.redirect(pc, 'show_choice', lambda s: (s.push(0), s.call(4, 1)))


def name_entry(rewriter, pc, argc, context):
    """32: (title, default, `$KEY`, character): the name goes in SHS's table for `$KEY`, and on the character. A name typed
    before is offered again, as 47 does on the smartphone."""
    def build(s):
        s.arg(3); s.arg(2); s.push(-1); s.call(47, 3)
        s.arg(1); s.text(NAME_PROMPT); s.push_result(); s.call(17, 3)
        s.push_result()                                     # a local: the next call replaces R
        s.arg(3); s.emit(0x41, 0); s.call(46, 2)
        s.arg(4); s.emit(0x41, 0); s.call(64, 2)
    rewriter.redirect(pc, 'name_entry', build)


def picture(s, location, variant, context):
    """Push the addon's picture of a location: `location` and `variant` push theirs. A location with one lighting has it
    whatever the variant (shs11.location_palettes), which a table of the two-lighting ones settles."""
    other, done = s.label(), s.label()
    variant(); s.jump_if_zero(other)
    location(); s.push(context['second_lighting']); s.emit(0x50); s.emit(0x3f); s.jump(done)
    s.label(other); s.push(0)
    s.label(done)
    location(); s.push(2); s.emit(0x52); s.emit(0x50); s.push(shs11.BACKGROUND_BASE); s.emit(0x50)


def title_card(rewriter, pc, argc, context):
    """35: (title, subtitle, location, variant) -> SHS 8."""
    def build(s):
        s.arg(1); s.arg(2); picture(s, lambda: s.arg(3), lambda: s.arg(4), context); s.push(0); s.call(8, 4)
    rewriter.redirect(pc, ('title_card', context['rid']), build)


def location(rewriter, pc, argc, context):
    """36: (variant, location) -> SHS 11, remembering the picture for a grid."""
    def build(s):
        s.push(BACKGROUND_KEY); picture(s, lambda: s.arg(2), lambda: s.arg(1), context); s.call(54, 2)
        s.push(0); s.push(BACKGROUND_KEY); s.call(55, 1); s.push_result(); s.call(11, 2)
    rewriter.redirect(pc, ('location', context['rid']), build)


def the_end(rewriter, pc, argc, context):
    """27: '11's "What do you want to do next?": the smartphone's closing message and the episode's exit."""
    rewriter.redirect(pc, 'end', lambda s: (s.text(END_TITLE), s.text(END_TEXT), s.push(END_ARGUMENT), s.call(33, 3),
                                            s.call(7, 0)))


def words_game(s, description, good, bad, tiers=0):
    """SHS 71 as the smartphone calls it, then 49's result: `tiers` below a win is the middle one, if it has one."""
    won, done = s.label(), s.label()
    s.text(GAME_TITLE); s.text(description); s.text(good); s.text(bad)
    s.push(WORD_GAME_MS); push_player(s); s.push(1); s.push(WORD_GAME_REFRESH_MS)
    s.call(71, 8)
    s.push_result()                                     # a local: the next call replaces R
    s.emit(0x41, 0); s.push(WORD_GAME_PASS); s.emit(0x0d); s.jump_if_nonzero(won)
    if tiers:
        lost = s.label()
        s.emit(0x41, 0); s.push(WORD_GAME_PASS - tiers); s.emit(0x0d); s.jump_if_zero(lost)
        s.result(MIDDLE); s.jump(done)
        s.label(lost)
    s.result(LOST); s.jump(done)
    s.label(won); s.result(WON)
    s.label(done)


def grid_game(s, frame, problems, success, failure):
    """SHS 96, the player's portrait in the corner the smartphone's has it, no tutorial, over the picture on show, then
    49's result. `problems`: the words of a table."""
    won, done = s.label(), s.label()
    table = s.rewriter.words(problems)
    for value in (frame['seconds'], frame['target'], frame['deadline'], frame['bonus']):
        s.push(value)
    s.push(0); s.push(BACKGROUND_KEY); s.call(55, 1); s.push_result()
    s.push(-1); s.push(-1); push_player(s); s.push(0)
    s.push(1); s.push(len(problems) // 10); s.push(table)
    s.push(1); s.text(success); s.text(failure)
    s.push(0); s.push(0); s.push(0); s.push(0)
    s.call(96, 20)
    s.push_result(); s.jump_if_nonzero(won)
    s.result(LOST); s.jump(done)
    s.label(won); s.result(WON)
    s.label(done)


def twin_problems(rewriter, memory, table, count):
    """A smartphone problem table's words, its text moved into this script."""
    words = []
    for k in range(count):
        record = list(memory[table + 10 * k:table + 10 * k + 10])
        for field in range(2, 6):
            record[field] = rewriter.text(shs11.text_at(memory, record[field]))
        words += record
    return words


def memory_problems(rewriter, memory, table, rounds=10):
    """One problem per word of a Memory game's rounds (table: cue, word), in the shape of the smartphone's one-word boards."""
    words = []
    for k in range(rounds):
        word = shs11.text_at(memory, memory[table + 2 * k + 1])
        name = word.capitalize()
        letters = ''.join(dict.fromkeys(word.lower())) + ''.join(c for c in GRID_FILLER if c not in word.lower())
        words += [4, 4, rewriter.text(f'{name}!'), rewriter.text(name), rewriter.text(word.lower()),
                  rewriter.text(letters), 1, 0, 1, -1]
    return words


def memory_rounds(rewriter, memory, instructions, pc):
    """(target, a table of its rounds, how many) if the game at this 49 is Memory, else None. All 22 of '11's are called the
    same way (tests/test_translate_shs11.py checks the jar's, where it has one). The call before it reads
    (mode, difficulty, the rounds' table, rounds, target), and that routine fills in each round with a bonus, points a letter
    and, from a table of its own by difficulty, a letter time and a limit (N73 scripts' routine; services 50 and 51)."""
    at = max((i for i in range(pc) if instructions[i].opcode == 0x29), default=0)     # the routine's call
    if at < 5:
        return None
    if [instructions[at + k].opcode for k in range(-5, 1)] != [0x1b, 0x40, 0x1a, 0x1a, 0x42, 0x29]:
        return None
    mode, difficulty = _pushes(instructions[at - 5])
    if mode != 0:
        return None
    table, rounds, target = memory[instructions[at - 4].operand], instructions[at - 3].operand, instructions[at - 2].operand
    start = instructions[at].operand
    add_round = next(i for i in range(start, len(instructions)) if instructions[i].opcode == 0x1f and instructions[i].operand >> 8 == 51)
    packed = next(i for i in range(add_round, start - 1, -1) if instructions[i].opcode == 0x1b)
    bonus, points = _pushes(instructions[packed])
    speeds = memory[instructions[packed + 1].operand]
    words = []
    for k in range(rounds):
        words += [rewriter.text(shs11.text_at(memory, memory[table + 2 * k])),
                  rewriter.text(shs11.text_at(memory, memory[table + 2 * k + 1])),
                  bonus, points, memory[speeds + 2 * (difficulty - 1)], memory[speeds + 2 * (difficulty - 1) + 1]]
    return target, rewriter.words(words), rounds


def reflex_rounds(rewriter, memory, instructions, pc):
    """(target, a table of its rounds, how many) if the game at this 49 is Reflex, else None. The call before it reads as
    Memory's does. The routine fills in each round from a row of nine words: right icons at least, the gauge's size, the three
    pictures and the four odds; and with a bonus, points a bar and, by difficulty, a flash and a hold time (service 52)."""
    at = max((i for i in range(pc) if instructions[i].opcode == 0x29), default=0)
    if at < 5 or [instructions[at + k].opcode for k in range(-5, 1)] != [0x1b, 0x40, 0x1a, 0x1a, 0x42, 0x29]:
        return None
    mode, difficulty = _pushes(instructions[at - 5])
    if mode == 0:
        return None
    table, rounds, target = memory[instructions[at - 4].operand], instructions[at - 3].operand, instructions[at - 2].operand
    start = instructions[at].operand
    add_round = next((i for i in range(start, len(instructions)) if instructions[i].opcode == 0x1f and instructions[i].operand >> 8 == 52), None)
    if add_round is None:
        return None
    packed = next(i for i in range(add_round, start - 1, -1) if instructions[i].opcode == 0x1b)
    last_table = next(i for i in range(add_round, start - 1, -1) if instructions[i].opcode == 0x40)
    bonus, points = _pushes(instructions[packed])
    times = memory[instructions[last_table].operand]
    words = []
    for k in range(rounds):
        row = list(memory[table + REFLEX_ROW * k:table + REFLEX_ROW * k + REFLEX_ROW])
        words += [row[0], row[1], bonus, points, *row[2:], memory[times + 2 * (difficulty - 1)], memory[times + 2 * (difficulty - 1) + 1]]
    return target, rewriter.words(words), rounds


def stop_game_song(s):
    """Fade the game's song out, leaving the game's result in R, where the stop would replace it."""
    end = s.label()
    for result in (WON, MIDDLE, LOST):
        other = s.label()
        s.push_result(); s.push(result); s.emit(0x0a); s.jump_if_zero(other)
        s.push(GAME_SONG_FADE); s.call(81, 1); s.result(result); s.jump(end)
        s.label(other)
    s.label(end)


def game(rewriter, pc, argc, context):
    """49: the real game if the player has it (only this one says so, through service 70), else what the smartphone has at
    this spot (FALLBACKS)."""
    plan = context['fallbacks'].get((context['rid'], pc))
    if plan is None:
        raise StoryError(f"no stand-in for the game at script {context['rid']}, {pc}")
    memory = context['memory']
    instructions = rewriter.program.instructions
    service = SHS11_MEMORY
    real = memory_rounds(rewriter, memory, instructions, pc)
    if real is None:
        service = SHS11_REFLEX
        real = reflex_rounds(rewriter, memory, instructions, pc)

    def build(s):
        s.push(GAME_SONG); s.push(1); s.call(80, 2)
        if real is None:
            stand_in(s)
        else:
            target, table, rounds = real
            playing, done = s.label(), s.label()
            s.push(SHS11_MINIGAMES_QUERY); s.call(70, 1)
            s.push_result(); s.jump_if_nonzero(playing)
            stand_in(s)
            s.jump(done)
            s.label(playing)
            s.push(MEMORY_SECONDS); s.push(target); s.push(rounds); s.push(table); push_player(s)
            s.call(service, 5)
            s.label(done)
        stop_game_song(s)

    def stand_in(s):
        if isinstance(plan, OwnWords):
            words_game(s, plan.description, plan.good, plan.bad)
        elif isinstance(plan, MemoryGrid):
            table = memory[plan.word]
            frame = GRID_FRAME
            grid_game(s, frame, memory_problems(rewriter, memory, table), 'Next round', "Time's up!")
        else:
            twin = context['twin'](plan.script)
            arguments = call_arguments(twin.program, plan.pc)
            text = lambda ref: shs11.text_at(twin.memory, ref)
            if isinstance(plan, TwinWords):
                words_game(s, text(arguments[1]), text(arguments[2]), text(arguments[3]), plan.tiers)
            else:
                seconds, target, deadline, bonus = arguments[:4]
                frame = dict(seconds=seconds, target=target, deadline=deadline, bonus=bonus)
                problems = twin_problems(rewriter, twin.memory, arguments[12], arguments[11])
                grid_game(s, frame, problems, text(arguments[14]), text(arguments[15]))
    rewriter.redirect(pc, ('game', context['rid'], pc), build)


def game_query(rewriter, pc, argc, context):
    """48: -1, play the game, unless '11's own skip flags are on (they never are here)."""
    rewriter.redirect(pc, 'play_games', lambda s: s.result(-1))


def old_word_game(rewriter, pc, argc, context):
    """25: (description, good words, bad words, duration in ms): '11 keeps the smartphone's word game, and this is it, with the
    game song as every game has. Its score goes on in B for the push after the call, as the stop would replace R."""
    reads = rewriter.code[pc + 1] == (0x21, None)
    if reads:
        rewriter.code[pc + 1] = (0x08, None)

    def build(s):
        s.push(GAME_SONG); s.push(1); s.call(80, 2)
        s.text(GAME_TITLE); s.arg(1); s.arg(2); s.arg(3); s.arg(4)
        push_player(s); s.push(1); s.push(WORD_GAME_REFRESH_MS)
        s.call(71, 8)
        if reads:
            s.push_result(); s.emit(0x04)
        s.push(GAME_SONG_FADE); s.call(81, 1)
    rewriter.redirect(pc, ('old_word_game', reads), build)


HANDLERS = {0: number_set, 1: number_get, 2: bit_set, 3: bit_get, 12: stored_name, 4: player, 5: cast_member, 9: copy_look, 10: relationships, 11: reset_numbers,
            18: next_script, 19: cue, 22: look_picker, 23: thought_or_line, 24: line, 25: old_word_game, 26: choice, 27: the_end,
            28: returns_one, 29: begin_choice, 30: add_option, 31: show_choice, 32: name_entry, 33: narration,
            35: title_card, 36: location, 48: game_query, 49: game}
# No-ops in '11 (20), its saves and unlocks (15, 37-43), its minigames' setup, which 49's stand-in replaces (50-52), and
# its polls, which 44 at 0 never offers (45-47).
DROPPED = {15, 20, 21, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 50, 51, 52}
RENAME = {55: 0,                         # format: -k means slot k + 1 in both
          6: 46,                          # (`$KEY`, its text)
          54: 27}                         # a random number below its bound; 0 or less gives 0 in both


@dataclass
class Twin:
    program: object
    memory: list


def _pushed_before(instructions, pc, count):
    """(the `count` constants pushed right before pc, the index of the push that starts them), or None."""
    values, i = [], pc
    while len(values) < count and i > 0:
        got = _pushes(instructions[i - 1])
        if got is None:
            return None
        values[:0] = got
        i -= 1
    return (values, i) if len(values) == count else None


def _text(memory, address):
    if not 0 <= address < len(memory):
        return None
    text = shs11.text_at(memory, address)
    return text if text and all(32 <= ord(c) for c in text.replace('\r', ' ').replace('\n', ' ')) else None


def spoken_sites(data):
    """[(the pc to run something before, the text, whether it's narration)] of a '11 script's lines, in code order. A line goes through
    a function of four words around 23 and 24: (text, character, expression, 0), or (-2, text, character, expression)."""
    program = decode_program(data)
    memory, instructions = shs11.script_memory(data), program.instructions
    speakers = set()
    for pc, instruction in enumerate(instructions):
        if instruction.opcode == 0x1f and instruction.operand >> 8 in (23, 24):
            speakers.add(max((i for i in range(pc) if instructions[i].opcode == 0x48), default=None))
    found = []
    for pc, instruction in enumerate(instructions):
        if (instruction.opcode == 0x42 and pc + 1 < len(instructions) and instructions[pc + 1].opcode == 0x29
                and instructions[pc + 1].operand in speakers):
            pushed = _pushed_before(instructions, pc, 4)
            if pushed is not None:
                text = _text(memory, pushed[0][1] if pushed[0][0] < 0 else pushed[0][0])
                if text is not None:
                    found.append((pushed[1], text, False))
        elif instruction.opcode == 0x1f and instruction.operand == 33 << 8 | 1:
            pushed = _pushed_before(instructions, pc, 1)
            if pushed is not None and _text(memory, pushed[0][0]) is not None:
                found.append((pushed[1], _text(memory, pushed[0][0]), True))
    return found


def twin_calls(data):
    """A smartphone script's instructions, its lines {pc: text} and its music calls {pc: (service, *arguments)}."""
    instructions = decode_program(data).instructions
    memory = shs11.script_memory(data)
    lines, music = {}, {}
    for pc, instruction in enumerate(instructions):
        if instruction.opcode != 0x1f:
            continue
        service, argc = instruction.operand >> 8, instruction.operand & 255
        pushed = _pushed_before(instructions, pc, argc)
        if pushed is None:
            continue
        if service in MUSIC_SERVICES:
            music[pc] = (service, *pushed[0])
        elif service == 13:
            text = _text(memory, pushed[0][1] if pushed[0][0] == -2 else pushed[0][0])
            if text is not None:
                lines[pc] = text
    return instructions, lines, music


def lines_after(instructions, lines, pc, known):
    """The lines in `known` that the code can reach first from pc, down every branch and back out of a function to wherever
    it's called, passing up to MUSIC_REACH lines '11 doesn't have."""
    found, seen, ahead = [], set(), [(pc + 1, 0)]
    starts = [i for i, instruction in enumerate(instructions) if instruction.opcode == 0x48]
    callers = collections.defaultdict(list)
    for i in range(len(instructions) - 1):
        if instructions[i].opcode == 0x42 and instructions[i + 1].opcode == 0x29:
            callers[instructions[i + 1].operand].append(i + 2)
    while ahead:
        pc, passed = ahead.pop()
        if (pc, passed) in seen or not 0 <= pc < len(instructions):
            continue
        seen.add((pc, passed))
        opcode, operand = instructions[pc].opcode, instructions[pc].operand
        if pc in lines:
            if lines[pc] in known:
                found.append(pc)
            elif passed < MUSIC_REACH:
                ahead.append((pc + 1, passed + 1))
        elif opcode == 0x42 and instructions[pc + 1].opcode == 0x29:
            ahead.append((pc + 2, passed))                  # a function's call: on its return
        elif opcode == 0x29:
            ahead.append((operand, passed))
        elif opcode == 0x28:
            ahead.append((pc + signed16(operand), passed))
        elif opcode in (0x2a, 0x2b, 0x2c, 0x2d, 0x2e):
            ahead += [(pc + 1, passed), (pc + signed16(operand), passed)]
        elif opcode == 0x43:
            start = max((i for i in starts if i <= pc), default=None)
            ahead += [(caller, passed) for caller in callers[start]]
        elif opcode not in (0x33, 0x5c):                    # (it halts, or goes where the data says)
            ahead.append((pc + 1, passed))
    return sorted(found)


def _plain(text):
    """A line for comparing: '11 marks with ` some of what the smartphone puts in quotes."""
    return text.replace('`', '').replace("'", '')


def game_sites(data):
    """Where a '11 script plays a game: its 49s and its old word games' 25s."""
    return [pc for pc, instruction in enumerate(decode_program(data).instructions)
            if instruction.opcode == 0x1f and instruction.operand >> 8 in (49, 25)]


def smartphone_music(res, story, twin_archive):
    """({script: {pc: [(service, *arguments)]}}, the music calls with no line to go to). Each of the smartphone's music calls
    in its scenes (its setup script's are `scene_music`'s),
    run before whichever of '11's lines it comes before. A line can be said in several places: it goes where the lines either
    side match too, or one of them; else, if the smartphone says it only once, everywhere '11 does. Where '11 adds a card of
    its own just before the line ("In English..."), it goes before the card, unless a game comes between them."""
    setup = twin_setup(twin_archive)
    scripts = [twin_calls(twin_archive.read(i)) for i in sorted(twin_archive.entries)
               if i != setup and twin_archive.read(i)[:4] == b'kiwi']
    scripts = [(instructions, {pc: _plain(text) for pc, text in lines.items()}, music) for instructions, lines, music in scripts]
    said = collections.Counter(text for _, lines, _ in scripts for text in lines.values())
    sites = collections.defaultdict(list)
    for script in story.scripts:
        spoken = [(pc, _plain(text), narrated) for pc, text, narrated in spoken_sites(res[script][1])]
        games = game_sites(res[script][1])
        for k, (pc, text, _) in enumerate(spoken):
            # (Not a card that comes before a game this line comes after: that's the game's instruction.)
            card = (spoken[k - 1][0] if k and spoken[k - 1][2] and said[spoken[k - 1][1]] == 0
                    and not any(spoken[k - 1][0] < game < pc for game in games) else pc)
            sites[text].append((script, card, spoken[k - 1][1] if k else None, spoken[k + 1][1] if k + 1 < len(spoken) else None))
    plan, lost = collections.defaultdict(dict), []
    for instructions, lines, music in scripts:
        order = sorted(lines)
        previous = None
        for pc, call in sorted(music.items()):
            # Each game starts and stops its own song (stop_game_song), wherever the smartphone has one or not.
            around_a_game = call == (80, GAME_SONG, 1) or (call[0] == 81 and previous == (80, GAME_SONG, 1))
            previous = call
            if around_a_game:
                continue
            placed = False
            for line in lines_after(instructions, lines, pc, sites):
                at = order.index(line)
                before, after = lines[order[at - 1]] if at else None, lines[order[at + 1]] if at + 1 < len(order) else None
                here = sites[lines[line]]
                places = ([place for place in here if place[2:] == (before, after)]
                          or [place for place in here if before == place[2] != None or after == place[3] != None]  # noqa: E711
                          or (here if said[lines[line]] == 1 else []))
                for script, site, _, _ in places:
                    calls = plan[script].setdefault(site, [])
                    if call not in calls:
                        calls.append(call)
                    placed = True
            if not placed:
                lost.append(call)
    return dict(plan), lost


def twin_setup(twin_archive):
    """The smartphone's script that only sets scenes going, if it has one: some episodes start their story in that script."""
    if FIRST_SCRIPT not in twin_archive.entries or twin_calls(twin_archive.read(FIRST_SCRIPT))[1]:
        return None
    return FIRST_SCRIPT


def scene_music(twin_archive):
    """The music calls of the smartphone's setup script, which it makes between scenes (a stop)."""
    setup = twin_setup(twin_archive)
    return [] if setup is None else list(twin_calls(twin_archive.read(setup))[2].values())


def cast_of(res, story):
    """[(address, character, kind, name, picture base or None)] of a setup script's cast table."""
    tables = shs11.cast_tables(res)
    looks = shs11.looks_of(tables)
    number = {look.pairs: i for i, look in enumerate(looks)}
    memory = shs11.script_memory(res[story.scripts[0]][1])
    instructions = decode_program(res[story.scripts[0]][1]).instructions
    base = next(memory[instructions[i].operand] for i in range(len(instructions) - 2)
                if instructions[i].opcode == 0x40 and instructions[i + 2].opcode == 0x1a
                and instructions[i + 2].operand == shs11.CAST_RECORD)
    cast = []
    for k, (character, kind, name, pairs) in enumerate(tables[story.scripts[0]]):
        faces = shs11.PORTRAIT_BASE + shs11.EXPRESSIONS * number[pairs]
        if not any(pairs[pair][0] >= 0 for pair in shs11.drawn_pairs(0)):
            faces = None                                    # (a voice with no picture: a cat behind a door)
        cast.append((base + shs11.CAST_RECORD * k, character, kind, name, faces))
    return cast


def translate(res, story, twin_archive):
    """The story's SHS `.exp` bytes, from the English jar's resources and the smartphone twin's archive, for its games."""
    twins = {}

    def twin(script):
        if script not in twins:
            data = twin_archive.read(script)
            twins[script] = Twin(decode_program(data), shs11.script_memory(data))
        return twins[script]
    cast = cast_of(res, story)
    music = smartphone_music(res, story, twin_archive)[0] if twin_archive is not None else {}
    between = scene_music(twin_archive) if twin_archive is not None else []
    second = [1 if shs11.lightings(res[i][1]) == 2 else 0 for i in range(shs11.LOCATIONS)]
    resources = {}
    for script in story.scripts:
        data = res[script][1]
        program = decode_program(data)
        rewriter = Rewriter(program)
        context = dict(rid=script, first=story.scripts[0], cast=cast, last_line=rewriter.words([-1]), scene_music=between,
                       second_lighting=rewriter.words(second), fallbacks=story.fallbacks,
                       memory=shs11.script_memory(data), twin=twin)
        for pc, service, argc in rewriter.calls():
            if service in RENAME:
                rewriter.rename(pc, RENAME[service])
            elif service in DROPPED:
                dropped(rewriter, pc, argc, context)
            elif service in HANDLERS:
                HANDLERS[service](rewriter, pc, argc, context)
            else:
                raise StoryError(f'script {script} calls service {service} with {argc} arguments, which has no translation')
        for pc, calls in music.get(script, {}).items():
            rewriter.insert(pc, lambda s, calls=calls: [(*map(s.push, call[1:]), s.call(call[0], len(call) - 1)) for call in calls])
        if script == story.scripts[0]:
            rewriter.prologue(lambda s: (s.push(NARRATOR), s.call(75, 1),
                                         s.push(NARRATOR), s.text(''), s.call(64, 2),
                                         s.push(NARRATOR), s.push(-1), s.call(72, 2)))
        resources[FIRST_SCRIPT + script - story.scripts[0]] = rewriter.finish().to_bytes()
    resources[ADDON_RECORD] = requires_bytes([(shs11.ADDON_ID, shs11.ADDON_REVISION)])
    resources[VERSION_RECORD] = version_bytes(STORY_VERSION)
    resources[1] = Metadata(shs11.PACK_ID, story.number, (story.title + TITLE_SUFFIX,) * 5).to_bytes()
    return encode_exp(resources)


def file_name(story):
    return re.sub(r'\W+', '_', story.title) + '_SHS11.exp'


def build(english, story_title, twin_path):
    """(file name, bytes) of a story, from the open English jar and the path of its smartphone twin."""
    story = STORIES[story_title]
    return file_name(story), translate(shs11.resources(english), story, ExpArchive(twin_path.read_bytes()))
