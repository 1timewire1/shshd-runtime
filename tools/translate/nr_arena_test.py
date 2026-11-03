"""A test episode for New Rules' minigame arena: a menu that plays each of its games on demand.

    python tools/translate/nr_arena_test.py ARENA_DIR [--out OUT_DIR]

ARENA_DIR holds `translate.py newrules ... --addon ADDON.exp --arena` output: the downloads ROUNDS names (Secret
Ingredient, The Outcast, Best Party Ever, Halloween, The Holiday Party). The episode is Secret Ingredient's archive
with its first script opening on the menu, and one script per download round, each its translated story script opening
on the round's arena function (the code the platform query chooses when the player has the arena), then going back to
the menu. The library's games are called at their entries with the arguments King of Diss and Dancing Queen pass.
After each game a line shows what it returned (B: a score or a grade). It needs the arena: with the switch off it says
so and ends.

It writes NR_200_Arena_Test.exp to OUT_DIR (default ARENA_DIR). Nothing it reads or writes belongs in the repo.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from exp_runtime.decode.bytecode import decode_program  # noqa: E402
from exp_runtime.exp import ExpArchive, Metadata, encode_exp  # noqa: E402
from kiwi_rewrite import Rewriter  # noqa: E402
import newrules  # noqa: E402

EPISODE_ID = 200
TITLE = 'Minigame Arena Test'
MENU_SCRIPT = 25001
ROUND_SCRIPTS = 25011                   # the download rounds' scripts, in ROUNDS order
BASE = 'NR_20_19__Secret_Ingredient.exp'
END = "Time's up!"
# Library games: (label, entry, arguments). An int is pushed, ('text', s) pushes a string, ('lib', address) reads the
# library's own variable there (its sequence tables, as the stories pass them). From the stories' calls (0x1b pushes
# its low byte first): Rhyme 25002 pc 118, Rhythm 25002 pc 460, beat boxing 25003 pc 190, dance steps 25103 pc 457,
# DJ Fever 25102 pc 436 (its first argument, the target, is the story's: 3 at least).
LIBRARY_GAMES = (
    ('Rhyme', 32611, (7, -1, 40, 3000, 1, 0, 33, 0, -1, ('text', '`Rhyming`\n\nMatch the words that rhyme.'),
                      ('text', END))),
    ('Rhythm', 31473, (6, -1, 2, 1, -1, 40, ('text', '`Rhythm`\n\nHit the good notes, not the bent ones.'),
                       ('text', END))),
    ('Dance steps (sequences)', 28903, (5, -1, 0, 3, 40, ('text', '`Dance steps!!!`'), ('text', END),
                                        ('lib', 32426), ('lib', 32423), 7, ('lib', 32424), 3)),
    ('Beat boxing (sequences)', 28903, (7, -1, 0, 3, 40, ('text', '`Beat boxing!!!`'), ('text', END),
                                        ('lib', 32427), ('lib', 32423), 7, ('lib', 32424), 3)),
    ('DJ Fever', 30244, (3, -1, 0, 0, 40, ('text', '`DJ Fever`\n\nKeep the music going.'), ('text', END))),
)
# Download rounds: (label, file, script, the arena function its platform query calls). Each download carries its own
# copy of the arena games (newrules.arena_code), in eight sizes holding different sets of them; these are a round of
# each game the copies play (two Rhythm rounds, from different copies), as their screens showed.
ROUNDS = (
    ('Sequences (Secret Ingredient)', BASE, 25001, 1555),
    ('Word match (The Outcast)', 'NR_10_09__The_Outcast.exp', 25002, 1350),
    ('Rhythm: singing (Best Party Ever)', 'NR_16_15__Best_Party_Ever.exp', 25004, 1779),
    ('Fever (Halloween)', 'NR_21_20__Halloween.exp', 25001, 1793),
    ('Rhythm: running (Holiday Party)', 'NR_29_27__The_Holiday_Party.exp', 25003, 1769),
)
BACK, QUIT = 99, 98


def choose(s, description, options):
    """SHS's choice (2, 3, 4) with `options` [(label, value)], leaving the answer in R."""
    s.text(TITLE); s.text(description); s.push(-1); s.push(0); s.push(newrules.NARRATOR); s.push(1)
    s.call(2, 6)
    for label, value in options:
        s.text(label); s.push(value); s.push(1); s.call(3, 3)
    s.push(0); s.call(4, 1)


def branch(s, cases):
    """Jump to cases[value] when R is that value."""
    for value, target in cases.items():
        s.push_result(); s.push(value); s.emit(0x0a); s.jump_if_nonzero(target)


def say(s, text):
    s.text(text); s.push(newrules.NARRATOR); s.call(13, 2)


def show_result(s):
    """A line with B, what the game returned."""
    s.text('The game returned %d.'); s.emit(0x08); s.call(0, 2)
    s.push_result(); s.push(newrules.NARRATOR); s.call(13, 2)


def call_function(s, target, argc=0):
    """SAVE_RETURN + JUMP: a call into the library's or this script's code, its arguments then dropped."""
    s.emit(0x42); s.jump(target)
    if argc:
        s.emit(0x19, argc)


def menu(s):
    top, library, rounds, done, no_arena = s.label(), s.label(), s.label(), s.label(), s.label()
    s.push(newrules.ARENA_QUERY); s.call(70, 1); s.push_result(); s.jump_if_zero(no_arena)
    s.label(top)
    choose(s, 'Which games?', [('New Rules\' library games', 1), ('Download rounds', 2), ('Quit', QUIT)])
    branch(s, {1: library, 2: rounds, QUIT: done})
    s.jump(top)

    s.label(library)
    games = [s.label() for _ in LIBRARY_GAMES]
    choose(s, 'The library\'s games, as the built-in stories call them.',
           [(label, n) for n, (label, _, _) in enumerate(LIBRARY_GAMES)] + [('Back', BACK)])
    branch(s, {**dict(enumerate(games)), BACK: top})
    s.jump(library)
    for label, (_, entry, args) in zip(games, LIBRARY_GAMES):
        s.label(label)
        for arg in args:
            if isinstance(arg, int):
                s.push(arg)
            elif arg[0] == 'text':
                s.text(arg[1])
            else:
                s.emit(0x40, arg[1])
        play, skipped, out = s.label(), s.label(), s.label()
        newrules.arena_skip(s, play, skipped)           # Ask to Skip Mini-Games, as the stories ask
        s.label(skipped)
        s.emit(0x19, len(args)); s.jump(out)
        s.label(play)
        call_function(s, entry, len(args))
        s.label(out)
        show_result(s)
        s.jump(library)

    s.label(rounds)
    choose(s, 'The downloads\' own copies of the games.',
           [(label, n) for n, (label, *_) in enumerate(ROUNDS)] + [('Back', BACK)])
    picks = [s.label() for _ in ROUNDS]
    branch(s, {**dict(enumerate(picks)), BACK: top})
    s.jump(rounds)
    for n, label in enumerate(picks):
        s.label(label)
        s.push(ROUND_SCRIPTS + n); s.push(0); s.call(10, 2); s.emit(0x33)

    s.label(no_arena)
    say(s, 'This test needs the Minigame Arena. Turn it on in Settings, then start the episode again.')
    s.label(done)
    s.call(7, 0); s.emit(0x33)


def round_script(program, function):
    """`program` opening on `function` (a download's arena round), then back to the menu."""
    rewriter = Rewriter(program)

    def build(s):
        play, out = s.label(), s.label()
        newrules.arena_skip(s, play, out)               # Ask to Skip Mini-Games, as the stories ask
        s.label(play)
        call_function(s, function)
        s.label(out)
        show_result(s)
        s.push(MENU_SCRIPT); s.push(0); s.call(10, 2); s.emit(0x33)
    rewriter.prologue(build)
    return rewriter.finish()


def build(arena_dir):
    base = ExpArchive((arena_dir / BASE).read_bytes())
    resources = {rid: base.read(rid) for rid in base.entries
                 if not (MENU_SCRIPT < rid < MENU_SCRIPT + 100)}          # the menu replaces Secret Ingredient's story
    rewriter = Rewriter(decode_program(base.read(MENU_SCRIPT)))
    rewriter.prologue(menu)
    resources[MENU_SCRIPT] = rewriter.finish().to_bytes()
    for n, (_, name, script, function) in enumerate(ROUNDS):
        archive = base if name == BASE else ExpArchive((arena_dir / name).read_bytes())
        program = decode_program(archive.read(script))
        if program.instructions[function].opcode != 0x48:
            raise SystemExit(f'{name} {script}: no function at {function}')
        resources[ROUND_SCRIPTS + n] = round_script(program, function).to_bytes()
    resources[1] = Metadata(newrules.PACK_ID, EPISODE_ID, (TITLE + newrules.TITLE_SUFFIX,) * 5).to_bytes()
    return encode_exp(resources)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('arena_dir', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    out = (args.out or args.arena_dir) / f'NR_{EPISODE_ID}_Arena_Test.exp'
    out.write_bytes(build(args.arena_dir))
    print(f'{TITLE!r} -> {out}')


if __name__ == '__main__':
    main()
