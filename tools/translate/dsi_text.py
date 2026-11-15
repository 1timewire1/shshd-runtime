"""The DSiWare game's text in its five languages, paired line for line (for dsi.py's translations).

The DSi has no script engine: each scene is compiled C++, once per language (Football Season is overlays 0-4, one language
each; each Classic overlay holds all five, one after another). The copies are the same machine code but for the literal
pools, which point at each language's own strings. So the code of the English copy and of another language's copy line up
word for word (difflib, over the words with every pointer into the overlay made one token), and the string pointers that
line up give the same line in both languages. About 99% of each copy's pointers pair this way; the rest sit where a
compiler pooled two equal strings in one language and not the other.

`extract(rom)` -> {overlay: [(English, {language: text})]}, in the English copy's code order (scene order).
"""
import difflib
import re
import struct

LANGUAGES = ('fr', 'it', 'de', 'es')
FOOTBALL = {0: 'en', 1: 'fr', 2: 'it', 3: 'de', 4: 'es'}          # Football Season, one language an overlay
CLASSICS = (5, 6, 7, 8, 9, 10, 11)
# Words that tell the languages apart (whole words, lower case), to name each of a Classic overlay's blocks.
MARKERS = {
    'en': ('the', 'you', 'and', 'is', 'what', 'to', 'it'),
    'fr': ('le', 'la', 'les', 'tu', 'je', 'est', 'pas', 'vous', 'et'),
    'it': ('il', 'che', 'non', 'di', 'sono', 'per', 'una', 'mi'),
    'de': ('der', 'die', 'und', 'ich', 'nicht', 'du', 'das', 'ist'),
    'es': ('el', 'que', 'no', 'es', 'por', 'una', 'los', 'con'),
}
HEAD = 32                     # words of a block's start that recur at every other block's start
RECORD = 48                   # words of a record read for its strings (a grid's: ten words a round, up to four rounds)


def _strings(data, base):
    def text(address):
        offset = address - base
        # A string starts after another's NUL, or on a word of its own (one placed right after a table of pointers).
        if not 0 < offset < len(data) or (data[offset - 1] != 0 and offset % 4):
            return None
        end = data.find(b'\0', offset)
        raw = data[offset:end]
        if not raw or len(raw) > 2000 or any(c < 32 and c not in (9, 10) for c in raw):
            return None
        return raw.decode('cp1252', 'replace')
    return text


def tokens(data, base):
    """The overlay's code as tokens (a pointer to a string 'S', any other pointer into the overlay 'P', a branch by its
    condition and kind, a PC-relative load by its register, anything else as it is) and, word for word, the string each
    'S' points at. The code ends where the strings begin."""
    text = _strings(data, base)
    words = struct.unpack_from(f'<{len(data) // 4}I', data)
    inside = [w for w in words if base <= w < base + len(data)]
    end = min((w - base for w in inside if w - base > 0x1000 and text(w) is not None), default=len(data)) // 4
    toks, strings, loads, records, pooled = [], [], [], [], set()
    for index, w in enumerate(words[:end]):
        loaded = record = None
        if base <= w < base + len(data):
            found = text(w)
            toks.append('S' if found is not None else 'P')
            strings.append(found)
        else:
            strings.append(None)
            if (w >> 24) & 0xF in (0xA, 0xB):
                toks.append(w >> 24)
            elif (w & 0x0F7F0000) == 0x051F0000:
                toks.append(('ldr', (w >> 12) & 15))
                slot = 4 * index + 8 + ((w & 0xFFF) if w & (1 << 23) else -(w & 0xFFF))
                if 0 <= slot <= len(data) - 4:
                    value = struct.unpack_from('<I', data, slot)[0]
                    loaded = text(value)
                    pooled.add(slot // 4)
                    if loaded is None and base <= value <= base + len(data) - 4 * RECORD:
                        # A pointer to data: a record the scene copies (a word grid's rounds), its words as text or raw.
                        at = value - base
                        record = tuple(text(v) if text(v) is not None else v
                                       for v in struct.unpack_from(f'<{RECORD}I', data, at - at % 4))
            else:
                toks.append(w)
        loads.append(loaded)
        records.append(record)
    # A string pointer no load reads is in a table (a quiz's questions, read by index): kept apart, paired in order.
    tables = [text if index not in pooled else None for index, text in enumerate(strings)]
    return toks, strings, loads, tables, records


def functions(toks):
    """Where each function starts (an ARM `push {..., lr}`), as word indexes from 0."""
    starts = [i for i, t in enumerate(toks) if isinstance(t, int) and (t & 0xFFFF4000) == 0xE92D4000]
    return [0] + [i for i in starts if i] if not starts or starts[0] else starts


def pairs(english, other):
    """[(English word index, English text, other text)] of the string loads that line up. `english`, `other`: (tokens,
    strings, loads) of one copy each (`tokens`). The copies have the same functions in the same order, so each is aligned
    with its counterpart; aligning whole copies at once let a pool of strings slip onto a like-shaped pool of another
    function."""
    a_toks, b_toks = english[0], other[0]
    a_starts, b_starts = functions(a_toks), functions(b_toks)
    if len(a_starts) != len(b_starts):
        a_starts, b_starts = [0], [0]
    a_ranges = list(zip(a_starts, a_starts[1:] + [len(a_toks)]))
    b_ranges = list(zip(b_starts, b_starts[1:] + [len(b_toks)]))
    found = []
    for (a0, a1), (b0, b1) in zip(a_ranges, b_ranges):
        for column in (2, 3, 4):                # the loads, the tables, the records
            a_loads, b_loads = english[column][a0:a1], other[column][b0:b1]
            a_texts = [(i, text) for i, text in enumerate(a_loads) if text is not None]
            b_texts = [text for text in b_loads if text is not None]
            if column == 4:
                if len(a_texts) == len(b_texts):
                    for (i, record), counterpart in zip(a_texts, b_texts):
                        found += [((a0 + i, k), text, translated) for k, text, translated in _record_pairs(record, counterpart)]
                continue
            if len(a_texts) == len(b_texts):
                # The code is the same in both copies, so its k-th load of a string is the same line: pair the loads, not
                # the pools (a pool can hold one entry more in one language, and pools are all alike to the matcher).
                found += [((a0 + i, 0), text, translated) for (i, text), translated in zip(a_texts, b_texts)]
                continue
            stepped = {}
            if column == 2 and a1 - a0 == b1 - b0:
                # The same instructions, but one language loads fewer strings: where English shows two lines (a quiz's
                # question as narration, in quotes, and as the menu's prompt), French may show one string twice, loaded
                # once and copied from register to register. Walk both in step, following the other copy's registers.
                stepped = {i: (text, translated)
                           for i, text, translated in _in_step(a_toks[a0:a1], a_loads, b_toks[b0:b1], b_loads)}
            # Else, and for what that misses: line the code up (its instructions, the pools aside, are distinctive) and
            # pair the loads that fall in matching runs.
            matcher = difflib.SequenceMatcher(None, a_toks[a0:a1], b_toks[b0:b1], autojunk=False)
            for a, b, size in matcher.get_matching_blocks():
                for i in range(size):
                    if a + i not in stepped and a_loads[a + i] is not None and b_loads[b + i] is not None:
                        stepped[a + i] = (a_loads[a + i], b_loads[b + i])
            found += [((a0 + i, 0), text, translated) for i, (text, translated) in sorted(stepped.items())]
    return found


def _record_pairs(record, counterpart):
    """[(word, English, other)] of two copies of a record (a grid's rounds: title, prompt, words, alphabet, ...): the
    strings at the same word, until the records stop matching (a string against a number, or two numbers that differ:
    past the record's end)."""
    found = []
    for k, (a, b) in enumerate(zip(record, counterpart)):
        if isinstance(a, str) and isinstance(b, str):
            found.append((k + 1, a, b))
        elif isinstance(a, str) or isinstance(b, str) or a != b:
            break
    return found


def _in_step(a_toks, a_loads, b_toks, b_loads):
    """[(index, English, other)]: each English string load paired with what the other copy's same instruction puts in
    its register: a string it loads, or one a `mov` copies from a register that holds one."""
    registers, found = {}, []
    for i, (a, b) in enumerate(zip(a_toks, b_toks)):
        value = None
        if isinstance(b, tuple) and b[0] == 'ldr':
            value = registers[b[1]] = b_loads[i]
        elif isinstance(b, int) and (b & 0x0FEF0FF0) == 0x01A00000:          # mov rd, rm
            value = registers[(b >> 12) & 15] = registers.get(b & 15)
        elif b == 0xEB:                                                       # bl: the call's registers are spent
            for register in (0, 1, 2, 3, 12):
                registers.pop(register, None)
        if a_loads[i] is not None and value is not None:
            found.append((i, a_loads[i], value))
    return found


def blocks(toks):
    """A Classic overlay's five language blocks, as [(start, end)] word ranges."""
    head = toks[:HEAD]
    starts = [i for i in range(len(toks) - HEAD) if toks[i:i + HEAD] == head]
    if len(starts) != 5:
        raise ValueError(f'expected five language blocks, found {len(starts)}')
    return list(zip(starts, starts[1:] + [len(toks)]))


def language(strings):
    """Which language a block's strings are in, by its marker words."""
    counts = dict.fromkeys(MARKERS, 0)
    for text in strings:
        if text:
            for word in re.findall(r"[a-zà-ÿ]+", text.lower()):
                for name, markers in MARKERS.items():
                    if word in markers:
                        counts[name] += 1
    return max(counts, key=counts.get)


def extract(rom):
    """{overlay: [(English, {language: text})]}: every English string of the eight stories with its translations."""
    result = {}
    football = {FOOTBALL[n]: tokens(rom.overlay(n), rom.overlay_ram(n)) for n in FOOTBALL}
    result[0] = _merge(football)
    for number in CLASSICS:
        columns = tokens(rom.overlay(number), rom.overlay_ram(number))
        copies = {}
        for start, end in blocks(columns[0]):
            name = language(columns[1][start:end])
            if name in copies:
                raise ValueError(f'overlay {number}: two blocks read as {name}')
            copies[name] = tuple(column[start:end] for column in columns)
        result[number] = _merge(copies)
    return result


def _merge(copies):
    english = copies['en']
    lines = {}
    for name in LANGUAGES:
        for index, text, translated in pairs(english, copies[name]):
            lines.setdefault(index, (text, {}))[1][name] = translated
    return [lines[index] for index in sorted(lines)]


# ---------- the translation table ----------

# The DSi's text is Windows-1252; the engine's is Latin-1 (owner, 2026-11-15, decision 9: oe and ...).
LATIN1 = {'œ': 'oe', 'Œ': 'OE', '…': '...', '’': "'", '‘': "'", '“': '"', '”': '"',
          '–': '-', '—': '-', '€': 'EUR'}
GAMETEXT = 0x6E46752F                   # Rom_2D.urf's per-locale menu text
GAMETEXT_LOCALES = {'en': 1, 'fr': 3, 'it': 4, 'de': 2, 'es': 0}     # the archive's locale order (Spanish first)
CHOOSE = 'Make your choice!'


GRID = re.compile(r'[a-z]+(\|[a-z]+)*')         # a word grid's words or letters (exp_runtime/dsi.GRID)


def grid_letters(text):
    """A grid's words or letters as its letter font can draw them: lower case, A to Z (the DSi's own lists have ü, ß, é,
    ñ, its font having them; the smartphone's grid font doesn't). None when something else is left."""
    import unicodedata
    text = text.lower().replace('ß', 'ss').replace('œ', 'oe').replace('æ', 'ae')
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return text if GRID.fullmatch(text) else None


def latin1(text):
    for character, written in LATIN1.items():
        text = text.replace(character, written)
    return text.encode('latin-1', 'replace').decode('latin-1')


def norm(text):
    """A line as the table keys it: lower case, letters, digits and name tokens (the copies of a story differ in
    punctuation and spacing; the runtime looks a line up the same way, exp_runtime/dsi.py `key`)."""
    return ' '.join(re.findall(r'[a-z0-9$]+', text.lower()))


def shape(text):
    """What a translation keeps of its line: name tokens and number formats, menu bars and line breaks. (Not its
    emphasis marks: the DSi's quiz lines open one and never close it, in English and not in French.)"""
    return (sorted(re.findall(r'\$[A-Za-z]\w*|%\w', text)), text.count('|'), text.count('\n'))


def plausible(english, translated):
    """Whether a pairing is a translation and not a neighbour's line the alignment slipped onto."""
    if not translated or not translated.strip() or shape(english) != shape(translated):
        return False
    # (A question may be translated as a statement, and a long line as a short one: only a neighbour's line is this far off.)
    return len(english) < 20 or .2 < len(translated) / len(english) < 3.5


def gametext(urf):
    """{language: {hash: text}} of the menu tables."""
    tables = {}
    for name, locale in GAMETEXT_LOCALES.items():
        data = urf.read(GAMETEXT, 'GameText', locale)
        count = struct.unpack_from('<I', data, 0)[0]
        base = 4 + 8 * count
        table = {}
        for i in range(count):
            key, offset = struct.unpack_from('<II', data, 4 + 8 * i)
            end = base + offset
            while data[end:end + 2] != b'\0\0':
                end += 2
            table[key] = data[base + offset:end].decode('utf-16-le', 'replace')
        tables[name] = table
    return tables


def translations(lines_by_overlay, phone_lines, menu):
    """The table the add-on carries: {'lines': {key: {language: text}}, 'context': {key: {previous key: {language:
    text}}}, 'names': ..., 'titles': ...}, and a report.

    `lines_by_overlay`: extract()'s; `phone_lines`: {overlay: [smartphone strings, in their scripts' order]} of every copy
    of that story; `menu`: gametext()'s tables. A DSi line is kept when its English is one of the smartphone story's
    lines, or (a line the DSi rewrote) when it sits alone between two kept lines whose smartphone lines are as far apart
    (decision 10). Where one line has different translations in different scenes, the most common is the default and the
    others are keyed by the line before."""
    report = dict(lines=0, kept=0, rewritten=0, implausible=0, unmatched=[], grids=0)
    found = {}                                   # key -> Counter of (translations tuple) and contexts
    contexts = {}
    words = {}                                   # a grid's words or letters, by the English exactly
    for overlay, lines in lines_by_overlay.items():
        for english, translated in lines:
            if GRID.fullmatch(english):
                kept = {name: grid_letters(text) for name, text in translated.items() if text}
                kept = {name: text for name, text in kept.items() if text}
                if kept:
                    words.setdefault(english, {}).update(kept)
        lines = [(english, translated) for english, translated in lines if not GRID.fullmatch(english)]
        phone = phone_lines.get(overlay, [])
        position = {}
        for i, text in enumerate(phone):
            position.setdefault(norm(text), i)
        keys = [norm(english) for english, _ in lines]
        place = [position.get(k) for k in keys]
        for i, (english, translated) in enumerate(lines):
            report['lines'] += 1
            key = keys[i]
            if not key:
                continue
            if place[i] is None:
                before = next((j for j in range(i - 1, -1, -1) if place[j] is not None), None)
                after = next((j for j in range(i + 1, len(lines)) if place[j] is not None), None)
                if (before is not None and after is not None and after - before == 2
                        and place[after] - place[before] == 2):
                    key = norm(phone[place[before] + 1])
                    report['rewritten'] += 1
                else:
                    report['unmatched'].append(english)
                    continue
            kept = {}
            for name, text in translated.items():
                if text is not None and plausible(english, text):
                    kept[name] = latin1(text)
                else:
                    report['implausible'] += 1
            if not kept:
                continue
            report['kept'] += 1
            previous = keys[i - 1] if i else ''
            entry = found.setdefault(key, {})
            value = tuple(sorted(kept.items()))
            entry[value] = entry.get(value, 0) + 1
            contexts.setdefault(key, {}).setdefault(previous, value)
    lines_table, context_table = {}, {}
    for key, values in found.items():
        default = max(values, key=values.get)
        lines_table[key] = dict(default)
        others = {previous: dict(value) for previous, value in contexts[key].items() if value != default}
        if others:
            context_table[key] = others
    names, titles = {}, {}
    english = menu['en']
    for hash_, text in english.items():
        key = norm(text)
        if not key or key in lines_table:
            continue
        translated = {name: latin1(menu[name][hash_].strip()) for name in LANGUAGES if menu[name].get(hash_, '').strip()}
        if len(translated) == len(LANGUAGES):
            names[key] = translated
    choose = next((h for h, t in english.items() if t.strip() == CHOOSE), None)
    if choose is not None:
        lines_table.setdefault(norm(CHOOSE), {name: latin1(menu[name][choose]) for name in LANGUAGES})
    report['menu'], report['grids'] = len(names), len(words)
    report['unmatched'] = report['unmatched'][:60]
    return dict(languages=list(LANGUAGES), lines=lines_table, context=context_table, menu=names, words=words), report
