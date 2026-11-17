"""shshd-runtime: the Creator's New Rules minigame node (CREATOR_CATCHUP_PLAN.md Stage 4; decision D, owner 2026-11-17).

A player with New Rules' arena (its minigame library linked from the `shsnr` add-on, and Use Translated Mini-Games on: service 70
selector 200 answers 1) plays the library's own game, as the translated built-in stories call it (tools/translate
nr_arena_test.py LIBRARY_GAMES: King of Diss's and Dancing Queen's arguments), after Ask to Skip Mini-Games (213) has its say.
Any other player takes the translators' fallback (tools/translate newrules.py library_game): a speed diss of timed choices for
Rhyme, an SHS word game with the author's words for the others. Either way the result is a score the story reads against the
node's target: the arena's own, or for a word game the target itself when passed and one less otherwise, as the translations
leave it.
"""
import random

from .model import ProjectError

ARENA_QUERY, ARENA_SKIP = 200, 213
END_TEXT = "Time's up!"
# (entry PC in the linked library, the call's arguments: an int is pushed, 'target'/'intro'/'end' are the node's, ('lib', n)
# reads the library's data word n: the sequence games' tables), as nr_arena_test.LIBRARY_GAMES.
GAMES = {
    'rhyme': (32611, ('target', -1, 40, 3000, 1, 0, 33, 0, -1, 'intro', 'end')),
    'rhythm': (31473, ('target', -1, 2, 1, -1, 40, 'intro', 'end')),
    'dance_steps': (28903, ('target', -1, 0, 3, 40, 'intro', 'end', ('lib', 32426), ('lib', 32423), 7, ('lib', 32424), 3)),
    'beat_boxing': (28903, ('target', -1, 0, 3, 40, 'intro', 'end', ('lib', 32427), ('lib', 32423), 7, ('lib', 32424), 3)),
    'dj_fever': (30244, ('target', -1, 0, 0, 40, 'intro', 'end')),
}
NAMES = {'rhyme': 'Rhyme', 'rhythm': 'Rhythm', 'dance_steps': 'Dance steps', 'beat_boxing': 'Beat boxing', 'dj_fever': 'DJ Fever'}
# Each game's defaults, as King of Diss and Dancing Queen play them: its target, its intro (`emphasis` as New Rules writes a
# title), and the fallback word game's banner and words (newrules.WORDLESS_GAMES).
DEFAULTS = {
    'rhyme': dict(target=7, intro='`Rhyming`\n\nMatch the words that rhyme.', banner='Speed diss!'),
    'rhythm': dict(target=6, intro='`Rhythm`\n\nHit the good notes, not the bent ones.', banner='Rhythm!',
                   good=['beat', 'groove', 'flow', 'bass', 'tempo', 'rhythm'],
                   bad=['bent note', 'off-key', 'screech', 'clunk', 'sour note', 'static']),
    'dance_steps': dict(target=5, intro='`Dance steps!!!`', banner='Dance steps!',
                        good=['two-step', 'funky chicken', 'moonwalk', 'the twist', 'spin', 'shimmy'],
                        bad=['stumble', 'trip', 'faceplant', 'flail', 'stomp', 'freeze']),
    'beat_boxing': dict(target=7, intro='`Beat boxing!!!`', banner='Beat boxing!',
                        good=['ba-dum', 'wicky', 'boots', 'cats', 'boom', 'tss'],
                        bad=['la la la', 'achoo', 'meow', 'hiccup', 'shh', 'moo']),
    'dj_fever': dict(target=3, intro='`DJ Fever`\n\nKeep the music going.', banner='DJ Fever!',
                     good=['groove', 'beat', 'bass', 'remix', 'spin', 'fever'],
                     bad=['record scratch', 'silence', 'skip', 'static', 'feedback', 'unplug']),
}
DEFAULT_RHYMES = [['cat', 'hat', 'bat', 'rat'], ['day', 'play', 'way', 'say'], ['night', 'light', 'bright', 'fight'],
                  ['cool', 'school', 'rule', 'pool'], ['beat', 'street', 'heat', 'feet'], ['flow', 'show', 'go', 'slow']]
# The fallbacks' pace (newrules.py): a word game of 30 s (the library's 40 s don't fit a word) refreshed every 3 s, passed at
# Rhythm's hits for its target (RHYTHM_HITS, at most 19) or 9 for the others; a speed diss of ten hits to win, three misses to
# lose, 3.9 s a round.
WORD_GAME_MS, WORD_GAME_REFRESH_MS = 30000, 3000
RHYTHM_HITS, RHYTHM_MOST_HITS, OTHER_HITS = {1: 8, 2: 8, 3: 8, 4: 10, 5: 13, 6: 16}, 19, 9
SPEED_DISS_HITS, SPEED_DISS_MISSES, SPEED_DISS_MS = 10, 3, 3900
SPEED_DISS_ROUNDS = SPEED_DISS_HITS + SPEED_DISS_MISSES - 1
SPEED_DISS_PROMPT = 'Flow: %d/10\nMiss: %d/3\nRhymes with { %s {'
# The linked library's place (VM_SPEC.md 2.3): a script running beside it keeps its code and data below these.
LIBRARY_CODE, LIBRARY_DATA = 26942, 29396


def defaults():
    return dict(game='rhythm', target=6, intro=DEFAULTS['rhythm']['intro'], good=list(DEFAULTS['rhythm']['good']),
                bad=list(DEFAULTS['rhythm']['bad']), rhymes=[list(f) for f in DEFAULT_RHYMES], result='arena_score')


def validate(p):
    if p['game'] not in GAMES:
        raise ProjectError('The New Rules minigame is ' + ', '.join(GAMES))
    if type(p['target']) is not int or not 1 <= p['target'] <= 10:
        raise ProjectError("The minigame's target is 1 to 10")
    if not isinstance(p['intro'], str) or len(p['intro']) > 300:
        raise ProjectError("The minigame's intro is text of at most 300 characters")
    for key, least in (('good', 2), ('bad', 3)):
        words = p[key]
        if (not isinstance(words, list) or len(words) < least or len(words) > 20
                or any(not isinstance(w, str) or not w.strip() or '|' in w or len(w) > 30 for w in words)):
            raise ProjectError(f'The fallback word game needs {least} to 20 {key} words, without pipes')
    rhymes = p['rhymes']
    if (not isinstance(rhymes, list) or len(rhymes) < 3 or any(
            not isinstance(f, list) or len(f) < 2 or any(not isinstance(w, str) or not w.strip() or '|' in w for w in f)
            for f in rhymes)):
        raise ProjectError('The speed diss needs at least three rhyme families of two words or more')
    if not p['result'].strip() or not p['result'].isidentifier():
        raise ProjectError('Enter a result variable')


def speed_diss_rounds(families, seed=25200):
    """SPEED_DISS_ROUNDS rounds (target, options, the rhyme's place), as newrules.rhyme_rounds deals them: a target and one
    word of its family among two or three words of others."""
    deal = random.Random(seed)
    family_of = {word: n for n, f in enumerate(families) for word in f}
    words = [word for f in families for word in f]
    pairs = [(f[a], f[b]) for f in families for a in range(len(f)) for b in range(a + 1, len(f))]
    deal.shuffle(pairs)
    rounds = []
    while len(rounds) < SPEED_DISS_ROUNDS:
        for target, rhyme in pairs:
            if len(rounds) == SPEED_DISS_ROUNDS:
                break
            others = [w for w in words if family_of[w] != family_of[target]]
            options = deal.sample(others, min(len(others), 2 + len(rounds) % 2)) + [rhyme]
            deal.shuffle(options)
            rounds.append((target, options, options.index(rhyme)))
    return rounds


def emit(asm, p, text, character, store_result, label_prefix):
    """The node's code: the library's game where the arena plays (after Ask to Skip), the fallback elsewhere, then the score
    stored by `store_result()` (it pops the stack's top). `text(field, value)` gives a text reference for a node field."""
    entry, arguments = GAMES[p['game']]
    fallback, play, done = ((label_prefix, k) for k in range(3))
    asm.call(70, ARENA_QUERY); asm.emit(0x21); asm.emit(0x13); asm.jump_if(fallback)
    # Ask to Skip Mini-Games (213): -1 plays; another value is the result the story reads instead.
    asm.call(ARENA_SKIP); asm.emit(0x21); asm.emit(0x1a, -1); asm.emit(0x0a); asm.jump_if(play)
    asm.emit(0x21); store_result(); asm.jump(done)
    asm.labels[play] = len(asm.code)
    for argument in arguments:
        if argument == 'target':
            asm.emit(0x1a, p['target'])
        elif argument == 'intro':
            asm.emit(0x1a, text('intro', p['intro']))
        elif argument == 'end':
            asm.emit(0x1a, asm.text(END_TEXT))
        elif isinstance(argument, tuple):
            asm.emit(0x40, argument[1])                       # the library's own table, as the stories pass it
        else:
            asm.emit(0x1a, argument)
    asm.emit(0x42); asm.jump(entry)                           # SAVE_RETURN + JUMP into the linked library
    asm.emit(0x19, len(arguments))
    asm.emit(0x08); store_result()                            # B: the game's score
    asm.jump(done)
    asm.labels[fallback] = len(asm.code)
    if p['game'] == 'rhyme':
        speed_diss(asm, p, character, label_prefix)
    else:
        word_game(asm, p, text, character, label_prefix)
    store_result()
    asm.labels[done] = len(asm.code)


def word_game(asm, p, text, character, label_prefix):
    """The fallback for the games without words of their own: SHS's word game (71) with the node's words, then the target
    when passed (Rhythm's hits for its target, or 9) and one less otherwise, as newrules.library_game."""
    banner = DEFAULTS[p['game']]['banner']
    asm.call(71, asm.text(banner), text('intro', p['intro']),
             asm.text('|'.join(text(f'good.{i}', w, True) for i, w in enumerate(p['good']))),
             asm.text('|'.join(text(f'bad.{i}', w, True) for i, w in enumerate(p['bad']))),
             WORD_GAME_MS, character, 1, WORD_GAME_REFRESH_MS)
    needed = (RHYTHM_HITS.get(p['target'], RHYTHM_MOST_HITS) if p['game'] == 'rhythm' else OTHER_HITS)
    passed, end = (label_prefix, 'passed'), (label_prefix, 'scored')
    asm.emit(0x21); asm.emit(0x1a, needed); asm.emit(0x0d); asm.jump_if(passed)
    asm.emit(0x1a, p['target'] - 1); asm.jump(end)
    asm.labels[passed] = len(asm.code)
    asm.emit(0x1a, p['target'])
    asm.labels[end] = len(asm.code)


def speed_diss(asm, p, character, label_prefix):
    """The fallback for Rhyme: the Lite builds' speed diss (newrules.speed_diss), timed choices "rhymes with cat" until ten
    hits or three misses; the hits are the score."""
    hits = asm.table([0, 0])
    misses = hits + 1
    end = (label_prefix, 'diss_end')

    def add(address):
        asm.emit(0x1a, address); asm.emit(0x40, address); asm.emit(0x1a, 1); asm.emit(0x50); asm.emit(0x3e); asm.emit(0x15)
    for address in (hits, misses):
        asm.emit(0x1a, address); asm.emit(0x1a, 0); asm.emit(0x3e); asm.emit(0x15)
    for k, (target, options, answer) in enumerate(speed_diss_rounds(p['rhymes'])):
        miss, done = (label_prefix, 'miss', k), (label_prefix, 'round', k)
        asm.emit(0x40, hits); asm.emit(0x1a, SPEED_DISS_HITS); asm.emit(0x0d); asm.jump_if(end)
        asm.emit(0x40, misses); asm.emit(0x1a, SPEED_DISS_MISSES); asm.emit(0x0d); asm.jump_if(end)
        asm.emit(0x1a, asm.text(SPEED_DISS_PROMPT)); asm.emit(0x40, hits); asm.emit(0x40, misses)
        asm.emit(0x1a, asm.text(target.capitalize())); asm.emit(0x1f, 0 << 8 | 4)
        # A timed choice (1): banner, options, the formatted description (R), its time, the time-out answer (none: a miss),
        # who asks, -1, 1, as newrules.speed_diss calls it.
        asm.emit(0x1a, asm.text(DEFAULTS['rhyme']['banner'])); asm.emit(0x1a, asm.text('|'.join(o.capitalize() for o in options)))
        asm.emit(0x21); asm.emit(0x1a, SPEED_DISS_MS); asm.emit(0x1a, -1); asm.emit(0x1a, character)
        asm.emit(0x1a, -1); asm.emit(0x1a, 1); asm.emit(0x1f, 1 << 8 | 8)
        asm.emit(0x21); asm.emit(0x1a, answer); asm.emit(0x0a); asm.emit(0x13); asm.jump_if(miss)
        add(hits); asm.jump(done)
        asm.labels[miss] = len(asm.code)
        add(misses)
        asm.labels[done] = len(asm.code)
    asm.labels[end] = len(asm.code)
    asm.emit(0x40, hits)
