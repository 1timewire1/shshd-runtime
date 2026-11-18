"""SHS '11's own Italian, as a translated story's languages record (resource 6, exp_runtime/episode_languages.py).

The owner's A1 (2026-11-17; reference/Other Games/docs/SHS_11_ITALIAN_PLAN.md): each of the five '11 episodes carries
'11's Italian, shown with the "'11 Language" switch (HD only). Nothing is a separate episode.

Sources: an Italian build's jar (1.36.76 480 x 800, or 1.37.32: the same text). Its scripts are the English (N73)
programs with translated text: 24 of the 30 match opcode for opcode, and six differ by one instruction each, so the two
are aligned by sequence matching (`aligned`) and every text an aligned push reads is paired (`script_pairs`). Also from
the jar: the cast tables' names, Memory's rounds (its own words: ELFO), the story titles (gamelib entry 21), the games'
interface text (entries 16, 17, 18) and the look picker's title (entry 32).

The smartphone twins' fallback word games and grids (Use Translated Mini-Games off) and this translator's own few strings
have no Italian original: OWN is this fork's translation (owner, 2026-11-17: "Yes, translate them"), kept short enough
for the grids' boards (a grid's words take at most 16 letters together).
"""
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import re

import shs11
from exp_runtime.decode.bytecode import decode_program
from exp_runtime.dsi import key

LANGUAGE, LANGUAGE_NAME, SETTING = 'it', 'Italiano', 'shs11_language'
TEXT_WORDS = 400                        # words a text may take (shs11.text_at stops at 80)
GAMELIB_TITLES, GAMELIB_LOOK = 21, 32
LOOK_TITLE_INDEX = 11                   # entry 32's 11th text: "Choose your look!"
NAME_ENTRY = 32                         # '11's name entry: (title, default name, `$KEY`, character)
THANKS_RE = re.compile(r'^[^\r\n]+')
# This fork's own Italian for text with no Italian original: the translator's own strings and the twins' fallbacks
# (English as the episode shows it -> Italian). Grids: (heading, board title, words) -> (heading, title, words), lower-case
# unaccented words as the grid's letter font has them.
OWN = {
    'Make Your Choice!': 'Fai la tua scelta!',
    'End of game': 'Fine del gioco',
    'Thanks for playing!': 'Grazie per aver giocato!',
    'Next round': 'Prossimo turno',
    # Best Party Ever
    'Pick robot parts!': 'Scegli i pezzi del robot!',
    'Metal head!|Steel hands!|Laser eyes!': "Testa di metallo!|Mani d'acciaio!|Occhi laser!",
    'Dragon claws!|Monkey tail!|Mermaid fins!|Stove-top hat!|Cat ears!':
        'Artigli di drago!|Coda di scimmia!|Pinne di sirena!|Cappello a cilindro!|Orecchie di gatto!',
    'Pick clothes!': 'Scegli i vestiti!',
    'Haltertop!|Miniskirt!|Cardigan!': "Top all'americana!|Minigonna!|Cardigan!",
    'Toaster!|Rocket ship!|Refridgerator!|Eggplant!|Sophistry!': 'Tostapane!|Razzo!|Frigorifero!|Melanzana!|Sofismi!',
    'Do your job!': 'Fai il tuo lavoro!',
    'Help customers!|Move quickly!|Find what they want!': 'Aiuta i clienti!|Muoviti in fretta!|Trova ciò che cercano!',
    'Trip on your own foot!|Grab the wrong item!|Confuse customers!|Find the wrong item!|Move slowly!':
        "Inciampa nei tuoi piedi!|Prendi l'articolo sbagliato!|Confondi i clienti!|Trova l'articolo sbagliato!|"
        'Muoviti lentamente!',
    # Foreign Exchange
    'Be cool!': 'Mantieni la calma!',
    'Stay calm!|Be cool!': 'Calma!|Tranquillità!',
    'Panic!|Aggh!|Terror!|Insecurity!': 'Panico!|Aaah!|Terrore!|Insicurezza!',
    'Dance to the music!': 'Balla a ritmo di musica!',
    'Headspin!|Dance!': 'Giro sulla testa!|Balla!',
    'Trip!|Slip!|Step on her feet!|Fall down!': 'Inciampa!|Scivola!|Pestale i piedi!|Cadi!',
    # Secret Ingredient
    'Help Kim think of a solution!': 'Aiuta Kim a trovare una soluzione!',
    "I know!!|I've got it!": 'Lo so!!|Ci sono!',
    'Um...|Er...|Uh...|Hm...': 'Uhm...|Ehm...|Uh...|Mmm...',
    # The New Girl
    'Try to catch Sam!': 'Prova a prendere Sam!',
    'Grab!|Snag!': 'Afferra!|Prendi!',
    'Drop!|Fumble!|Fail!|Miss!': 'Lascia!|Pasticcia!|Sbaglia!|Manca!',
    'Roll down the hill!': 'Rotola giù dalla collina!',
    'Roll!|Tumble!': 'Rotola!|Capitombola!',
    'Crash!|Trip!|Stop!|Fall!': 'Schianto!|Inciampa!|Fermati!|Cadi!',
}
GRIDS = {
    # Best Party Ever
    ('Search for\nThe gift!', 'Search\nGift', 'search|gift'): ('Cerca\nil regalo!', 'Cerca\nRegalo', 'cerca|regalo'),
    ('Find the\nLocket!', 'Find\nLocket', 'find|locket'): ('Trova il\nciondolo!', 'Trova\nCiondolo', 'trova|ciondolo'),
    ('Scramble!', 'Scramble', 'scramble'): ('Sbrigati!', 'Sbrigati', 'sbrigati'),
    ('Sneak to\nThe house!', 'Sneak!', 'sneak'): ('Sgattaiola\nnella casa!', 'Sgattaiola!', 'sgattaiola'),
    ('Creep stealthily!', 'Creep\nStealthily!', 'creep|stealthily'): ('Avanza piano\npiano!', 'Avanza\nPiano!', 'avanza|piano'),
    ('Move like\nA ninja!', 'Move\nNinja!', 'move|ninja'): ('Muoviti come\nun ninja!', 'Muoviti\nNinja!', 'muoviti|ninja'),
    # The New Girl
    ('Do a\nflip!', 'Flip', 'flip'): ('Fai una\ncapriola!', 'Capriola', 'capriola'),
    ('Move real\nfast!', 'Move\nFast', 'move|fast'): ('Muoviti\nin fretta!', 'Muoviti\nVeloce', 'muoviti|veloce'),
    ('Jump and\ncheer!', 'Jump\nCheer', 'jump|cheer'): ('Salta e\nfai il tifo!', 'Salta\nTifo', 'salta|tifo'),
    ('Drive Fast!', 'Drive', 'drive'): ('Guida veloce!', 'Guida', 'guida'),
    ('Avoid The\nCars', 'Avoid', 'avoid'): ('Evita le\nauto', 'Evita', 'evita'),
    ('Be Careful!', 'Careful', 'careful'): ('Stai attento!', 'Attento', 'attento'),
    ('Stay On\nYour Toes!', 'Stay\nToes', 'stay|toes'): ('Stai\nall\'erta!', 'Stai\nAllerta', 'stai|allerta'),
    ('Focus!', 'Focus', 'focus'): ('Concentrati!', 'Concentrati', 'concentrati'),
    ('Perform Tricks!', 'Tricks', 'tricks'): ('Fai le\nacrobazie!', 'Acrobazie', 'acrobazie'),
    # Lost Recipe
    ('Stay\nhappy.', 'Stay\nHappy...', 'stay|happy'): ('Resta\nallegro.', 'Resta\nAllegro...', 'resta|allegro'),
    ('Play it\ncool.', 'Play it\nCool...', 'play|cool'): ('Mantieni\nla calma.', 'Mantieni\nCalma...', 'mantieni|calma'),
    ('Keep\nchill.', 'Keep\nChill...', 'keep|chill'): ('Stai\nrilassato.', 'Stai\nRilassato...', 'stai|rilassato'),
}
GRID_LETTERS_MOST = 16                  # a grid's board holds its words' letters (4 x 4)


def text(memory, address):
    """A script's text at `address` (cp1252), longer than shs11.text_at reads."""
    out = bytearray()
    for word in memory[address:address + TEXT_WORDS]:
        word &= 0xFFFF
        for byte in (word >> 8, word & 255):
            if not byte:
                return out.decode('cp1252', 'replace')
            out.append(byte)
    return out.decode('cp1252', 'replace')


def is_text(found):
    return (bool(found) and '�' not in found and re.search(r'[A-Za-zÀ-ÿ]', found) is not None
            and all(c in '\n\r' or c.isprintable() for c in found))


def string_start(memory, address):
    """Whether a text starts at `address`: the word before it ends one (texts are packed two bytes a word, each ending
    in a zero byte) or it's memory's first."""
    return address == 0 or (memory[address - 1] & 0xFF) == 0


def tokens(instructions):
    """A program as what it does, for aligning two builds: each constant pushed is a token ('push', its instruction
    index, the value) and any other instruction one of its own (its opcode, its index). A text's address can be pushed
    one way in one build and another in the other (two small values packed in one instruction, or a word each), so
    pushes are compared by what they push, not by how."""
    from shs11_story import _pushes
    found = []
    for index, instruction in enumerate(instructions):
        values = _pushes(instruction)
        if values is None:
            found.append((instruction.opcode, index, None))
        else:
            found += [('push', index, value & 0xFFFF) for value in values]
    return found


def aligned(english, italian):
    """(English token, Italian token) of the two programs' matching tokens (`tokens`), by kind."""
    a, b = tokens(english), tokens(italian)
    for block in SequenceMatcher(None, [t[0] for t in a], [t[0] for t in b], autojunk=False).get_matching_blocks():
        for k in range(block.size):
            yield a[block.a + k], b[block.b + k]


def script_pairs(english_data, italian_data):
    """([(English pc, English text, Italian text)] of the texts the two scripts' aligned pushes read, {English pc: Italian
    pc} of their aligned instructions)."""
    pa, pb = decode_program(english_data).instructions, decode_program(italian_data).instructions
    ma, mb = shs11.script_memory(english_data), shs11.script_memory(italian_data)
    pairs, pcs, anchors = [], {}, {}
    for (kind, i, x), (_, j, y) in aligned(pa, pb):
        if kind != 'push':
            pcs[i] = j
            continue
        if 0 < x < len(ma) and 0 < y < len(mb) and string_start(ma, x) and string_start(mb, y):
            ta, tb = text(ma, x), text(mb, y)
            if is_text(ta) and is_text(tb) and ta != tb:
                pairs.append((i, ta, tb))
                anchors.setdefault(x, y)
    return pairs, pcs, anchors


def strings(memory):
    """[(address, text)] of every text in a script's memory, in address order: one starts where a word ends a text (or at
    memory's start) and reads as text (`is_text`)."""
    found, p = [], 0
    while p < len(memory):
        if string_start(memory, p):
            got = text(memory, p)
            if len(got) >= 2 and is_text(got):
                found.append((p, got))
                p += len(got.encode('cp1252', 'replace')) // 2 + 1
                continue
        p += 1
    return found


def between_pairs(english_data, italian_data, anchors):
    """Texts no push reads (a table's: a shop's options, a menu's lines), paired by order: between two texts the pushes
    paired (`anchors`, English address -> Italian), each build's texts in address order are taken one for one where the
    two hold as many."""
    ma, mb = shs11.script_memory(english_data), shs11.script_memory(italian_data)
    sa, sb = strings(ma), strings(mb)
    points = [(-1, -1)] + sorted(anchors.items()) + [(len(ma), len(mb))]
    pairs = []
    for (a0, b0), (a1, b1) in zip(points, points[1:]):
        if b1 <= b0:
            continue                                        # (out of order: left alone)
        left = [t for address, t in sa if a0 < address < a1]
        right = [t for address, t in sb if b0 < address < b1]
        if left and len(left) == len(right):
            pairs += [(x, y) for x, y in zip(left, right) if x != y]
    return pairs


def memory_words(data, instructions, pc):
    """[(cue, word)] of the Memory game whose routine is called before `pc` (shs11_story.memory_rounds' reading), or []."""
    memory = shs11.script_memory(data)
    at = max((i for i in range(pc) if instructions[i].opcode == 0x29), default=0)
    if at < 5 or [instructions[at + k].opcode for k in range(-5, 1)] != [0x1b, 0x40, 0x1a, 0x1a, 0x42, 0x29]:
        return []
    table, rounds = memory[instructions[at - 4].operand], instructions[at - 3].operand
    return [(text(memory, memory[table + 2 * k]), text(memory, memory[table + 2 * k + 1])) for k in range(rounds)]


def story_titles(entry):
    """The story titles of gamelib entry 21, in order: each a short text (`#`, a one-byte length, the text, two zero
    bytes) followed by its blurb, a long one (`#`, a two-byte length)."""
    return [(m.group(1).decode('cp1252', 'replace'), m.group(2).decode('cp1252', 'replace'))
            for m in re.finditer(rb'#[\x02-\x7f]([^\x00#]{2,60}?)\x00\x00#[\x80-\xff]\x00([^\x00]+)\x00', entry)]


def grid_letters(words, english_words, english_letters):
    """A grid's letter set for `words`: their letters once each, then the English set's own extra letters (those not in
    its words), as the smartphone's sets are built (a word's letters, then a filler or two)."""
    own = ''.join(dict.fromkeys(words.replace('|', '')))
    filler = ''.join(c for c in english_letters if c not in english_words and c not in own)
    return own + filler


class Table:
    """The record's tables as dsi.Translation reads them, built pair by pair; a key with several translations keeps the
    most common, and the others by the line before it (`context`)."""

    def __init__(self):
        self.seen = defaultdict(Counter)            # key -> Counter of Italian
        self.after = defaultdict(dict)              # key -> {previous key: Italian}
        self.menu, self.words = {}, {}

    def line(self, english, italian, previous=None):
        found = key(english)
        if not found or english == italian:
            return
        self.seen[found][italian] += 1
        if previous:
            self.after[found].setdefault(key(previous), italian)

    def word(self, english, italian):
        self.words[english] = {LANGUAGE: italian}

    def name(self, english, italian):
        if key(english) and english != italian:
            self.menu[key(english)] = {LANGUAGE: italian}

    def tables(self):
        lines, context = {}, {}
        for found, counts in self.seen.items():
            best = counts.most_common(1)[0][0]
            lines[found] = {LANGUAGE: best}
            others = {previous: {LANGUAGE: italian} for previous, italian in self.after[found].items() if italian != best}
            if others:
                context[found] = others
        return dict(lines=lines, context=context, menu=self.menu, words=self.words)


def record(english_res, italian_res, italian_gamelib, english_gamelib, story, fallbacks, cast_of):
    """The story's languages record (episode_languages.languages_bytes takes it). `fallbacks`: the stand-ins the story's
    games have ({(script, pc): plan}, with their twins' texts as `fallback_texts` gives them); `cast_of(res, story)` is
    shs11_story's cast table reader."""
    table = Table()
    for script in story.scripts:
        pairs, pcs, anchors = script_pairs(english_res[script][1], italian_res[script][1])
        previous = None
        for _, english, italian in pairs:
            table.line(english, italian, previous)
            previous = english
        for english, italian in between_pairs(english_res[script][1], italian_res[script][1], anchors):
            if key(english) not in table.seen:
                table.line(english, italian)
        ea = decode_program(english_res[script][1]).instructions
        eb = decode_program(italian_res[script][1]).instructions
        for pc, instruction in enumerate(ea):
            if instruction.opcode == 0x1f and instruction.operand is not None and instruction.operand >> 8 == 49 and pc in pcs:
                for (cue_en, word_en), (cue_it, word_it) in zip(memory_words(english_res[script][1], ea, pc),
                                                                   memory_words(italian_res[script][1], eb, pcs[pc])):
                    table.line(cue_en, cue_it)
                    table.word(word_en.lower(), word_it.lower())
                    table.line(word_en.capitalize(), word_it.capitalize())
                    filler = 'wb'
                    letters = ''.join(dict.fromkeys(word_en.lower())) + ''.join(c for c in filler if c not in word_en.lower())
                    table.word(letters, ''.join(dict.fromkeys(word_it.lower()))
                               + ''.join(c for c in filler if c not in word_it.lower()))
    # A name entry's default is a name, not text: the Italian build's is a placeholder (`IT-PLAYER`, which the name
    # check refuses for its hyphen), so it stays as the episode has it.
    from shs11_story import call_arguments
    for script in story.scripts:
        program = decode_program(english_res[script][1])
        memory = shs11.script_memory(english_res[script][1])
        for pc, instruction in enumerate(program.instructions):
            if instruction.opcode == 0x1f and instruction.operand is not None and instruction.operand >> 8 == NAME_ENTRY:
                default = text(memory, call_arguments(program, pc)[1])
                table.seen.pop(key(default), None)
                table.after.pop(key(default), None)
    for (character, kind, name, faces), (_, _, italian, _) in zip(
            [entry[1:] for entry in cast_of(english_res, story)], [entry[1:] for entry in cast_of(italian_res, story)]):
        table.name(name[:1].upper() + name[1:], italian[:1].upper() + italian[1:])
    for english, italian in OWN.items():
        table.line(english, italian)
    for plan in fallbacks:
        if plan['kind'] == 'grid':
            table.line(plan['success'], OWN.get(plan['success'], plan['success']))
            for heading, title, words, letters in plan['rows']:
                found = GRIDS[(heading, title, words)]
                if len(found[2].replace('|', '')) > GRID_LETTERS_MOST:
                    raise ValueError(f'{found[2]!r} has too many letters for a grid')
                table.line(heading, found[0])
                table.line(title, found[1])
                table.word(words, found[2])
                table.word(letters, grid_letters(found[2], words.replace('|', ''), letters))
        else:
            for part in ('description', 'good', 'bad'):
                table.line(plan[part], OWN[plan[part]])
    # '11's own words for its menus: the look picker's title, "Time's up!", the end's thanks.
    look = shs11.UiReader(italian_gamelib[GAMELIB_LOOK], True).read()
    table.line('Choose your look!', look[LOOK_TITLE_INDEX])
    memory_en, memory_it = interface_text(english_gamelib, False), interface_text(italian_gamelib, True)
    table.line("Time's up!", memory_it['memory']['time_up'])
    titles = {}
    for (title_en, blurb_en), (title_it, blurb_it) in zip(story_titles(english_gamelib[GAMELIB_TITLES]),
                                                          story_titles(italian_gamelib[GAMELIB_TITLES])):
        titles[title_en] = title_it
        table.line(title_en, title_it)
        table.line(blurb_en, blurb_it)
    tables = table.tables()
    found = dict(setting=SETTING, languages={LANGUAGE: LANGUAGE_NAME}, **tables,
                 ui={LANGUAGE: {game: {name: words for name, words in memory_it[game].items()
                                       if words != memory_en[game].get(name)} for game in memory_it}})
    if story.title in titles:
        found['titles'] = {LANGUAGE: titles[story.title]}
    return found


def interface_text(gamelib, wide):
    """{'memory': {...}, 'reflex': {...}} of '11's game interface text, under the names shs11.memory_ui / reflex_ui give
    the addon's (entries 16, 17, 18)."""
    def entry(number, borrowed=0):
        return shs11.UiReader(gamelib[number], wide, borrowed).read()
    words = entry(17)
    reflex = entry(18, 13) if wide else shs11.UiReader(gamelib[18]).read()
    return dict(
        memory=dict(spelling=words[3], goal=words[4], look=words[5], select=words[6], careful=words[7], ready=words[8],
                    time_up=entry(16)[1]),
        reflex=dict(goal=reflex[10], gauge=reflex[11], select=reflex[12], bars=reflex[13], penalty=reflex[14],
                    skull=reflex[15], ready=reflex[16]))
