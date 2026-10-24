"""Give New Rules' all-lowercase text its capitalisation back (the owner's decision 7).

New Rules' bitmap fonts had only capitals, so its scripts store text in lowercase. 45 of its stories also exist as
smartphone EXPs in mixed case. `learn` pairs their strings (same words, case ignored) into a dictionary of how each word
is written when it is not starting a sentence; `apply` puts a string into sentence case and uses the dictionary for the
other words. A word the dictionary hasn't seen stays lowercase and goes on the review list.

Casing never changes a string's length, so it can be written back into the script's data bank in place.
"""
from collections import Counter, defaultdict
from pathlib import Path
import re
import string
import struct

WORD = re.compile(r"[A-Za-z][A-Za-z']*")
# A word starts a sentence after . ! ? (and closing quotes) and a space, at the start of the text or of a `|`-separated
# choice option, with only opening quotes, backticks or a music note before it ("team? `does` she", "{ nice goatee").
# After a comma or colon only a double quote opens one: single quotes mark terms ("when ryan calls, 'come over'").
SENTENCE_END = re.compile(r'[.!?]["\'`)]*\s+(?:["\'`(]|\{\s*)*$|(^|\|)\s*(?:["\'`(]|\{\s*)*$|[,:]\s+"$')
# A capitalised form wins only when the smartphone texts write the word that way almost always ("Officer Smith" must
# not turn "parole officer" into "parole Officer").
CAPITAL_SHARE = 0.9
# Single letters joined by dots ("h.e.c.t.o.r.", "p.r.a.t.t.") are spelled-out names, written in capitals.
# Place names the paired stories never teach: the US states and their capitals (Train That Brain!'s capitals quiz).
PLACES = (
    'Alabama Montgomery|Alaska Juneau|Arizona Phoenix|Arkansas|Little Rock|California Sacramento|Colorado Denver|'
    'Connecticut Hartford|Delaware Dover|Florida Tallahassee|Georgia Atlanta|Hawaii Honolulu|Idaho Boise|'
    'Illinois Springfield|Indiana Indianapolis|Iowa|Des Moines|Kansas Topeka|Kentucky Frankfort|Louisiana|'
    'Baton Rouge|Maine Augusta|Maryland Annapolis|Massachusetts Boston|Michigan Lansing|Minnesota|Saint Paul|'
    'Mississippi Jackson|Missouri|Jefferson City|Montana Helena|Nebraska Lincoln|Nevada|Carson City|'
    'New Hampshire|Concord|New Jersey|Trenton|New Mexico|Santa Fe|New York|Albany|North Carolina|Raleigh|'
    'North Dakota|Bismarck|Ohio Columbus|Oklahoma|Oklahoma City|Oregon Salem|Pennsylvania Harrisburg|'
    'Rhode Island|Providence|South Carolina|Columbia|South Dakota|Pierre|Tennessee Nashville|Texas Austin|Utah|'
    'Salt Lake City|Vermont Montpelier|Virginia Richmond|Washington Olympia|West Virginia|Charleston|'
    'Wisconsin Madison|Wyoming Cheyenne')
MULTI_WORD = ('Little', 'Des', 'Baton', 'Saint', 'Jefferson', 'Carson', 'New', 'Santa', 'North', 'Oklahoma', 'Rhode',
              'South', 'Salt', 'West')
# Other proper names the paired stories don't settle: the game's own ("a special episode of `surviving high school!`",
# the end card's "surviving high school", King of Diss's survey).
PROPER_PHRASES = ('Surviving High School: New Rules', 'Surviving High School', 'Surviving Hollywood', 'Centerscore High')
# Titles New Rules writes in quotes: King of Diss's soap opera, "today on 'the valley'". Only quoted, since other
# stories have plain valleys ("stare out at the valley below them", Guys Versus Wild).
QUOTED_TITLES = re.compile(r"(?<=')the valley(?=')", re.IGNORECASE)
# Named things only King of Diss mentions, written as the owner reads them (lowercase -> written form).
OWN_TITLES = {title.lower(): title for title in ("The Beatdown of '06", 'I Eat Your Brains With Salsa')}
OWN_TITLE = re.compile('|'.join(re.escape(title) for title in OWN_TITLES), re.IGNORECASE)
# Acronyms New Rules writes in lowercase that the smartphone stories may not teach ("djs" -> "DJs").
COMMON_ACRONYMS = {word.lower(): word for word in ('DJ', 'TV', 'DVD', 'CD', 'MP3')}
# Names only New Rules' own stories use, which no smartphone story teaches (King of Diss's soap opera star).
OWN_NAMES = {word.lower(): word for word in ('Krystal',)}
# A grade letter: before -plus/-minus ("a d-plus"), or quoted ("your 'a' game"); only a-f, so "rock 'n' roll" stays.
GRADE = re.compile(r"\b[a-f](?=-(?:plus|minus)\b)|(?<=')[a-f](?=')", re.IGNORECASE)
GAZETTEER = re.compile(r'\b(?:' + '|'.join(sorted(
    {p.lower() for group in PLACES.split('|')
     for p in ([group] if ' ' in group and group.split()[0] in MULTI_WORD else group.split())}
    | {p.lower() for p in PROPER_PHRASES}, key=len, reverse=True)) + r')\b', re.IGNORECASE)
SUBSTRING_MIN = 12                     # recase_program: shorter strings are too common to place inside a twin line
ACRONYM = re.compile(r"(?<![A-Za-z.])(?:[A-Za-z]\.){2,}")
# A dot after an abbreviation or a dotted acronym doesn't end the sentence ("mr. hotpants", "h.e.c.t.o.r. method").
# A word after an honorific is a name ("mr. narrator" -> "Mr. Narrator").
HONORIFIC = re.compile(r"\b(?:mr|mrs|ms|dr)\.\s+$", re.IGNORECASE)
ABBREVIATION = re.compile(r"(?:\b(?:mr|mrs|ms|dr|vs|jr|sr|st)\.|(?<![A-Za-z.])(?:[A-Za-z]\.){2,})[\"'`)]*\s+$",
                          re.IGNORECASE)


def learn_from_library(expd_folder, library, exclude=(), twin_of=None):
    """The dictionary learned from every New Rules download paired with a library episode (pairs.py), and, for the
    download named `twin_of`, the strings of the episodes telling its story (`pairs.related`: its twin, or both
    stories the SHS 11 Demos excerpt) by lowercase text (`exact`, for recase_program), and their titles:
    (dictionary, exact, titles). `exclude` leaves stories out of the dictionary (casing_eval measures it that way)."""
    from exp_runtime.decode.bytecode import decode_program
    from exp_runtime.exp import ExpArchive
    import newrules
    import pairs as pairing
    data, exact = [], {}
    for pair in pairing.pair(Path(expd_folder), Path(library)):
        if not pair['paired'] or pair['expd'] in exclude:
            continue
        episode = newrules.read_expd((Path(expd_folder) / pair['expd']).read_bytes())
        archive = ExpArchive((Path(library) / pair['file']).read_bytes())
        theirs = [t for r in archive.entries if archive.read(r)[:4] == b'kiwi'
                  for _, t in strings(decode_program(archive.read(r)))]
        data.append(([t for p in episode.scripts.values() for _, t in strings(p)], theirs))
    titles, related = [], []
    if twin_of is not None:
        for record in pairing.related(Path(expd_folder), Path(library), twin_of):
            archive = ExpArchive((Path(library) / record['file']).read_bytes())
            titles.append(record['titles'][0])
            for r in archive.entries:
                if archive.read(r)[:4] != b'kiwi':
                    continue
                for _, text in strings(decode_program(archive.read(r))):
                    related.append(text)
                    # the twins keep some lowercase leftovers: the best-cased copy wins
                    if capitals(text) > capitals(exact.get(text.lower(), '')):
                        exact[text.lower()] = text
    dictionary = learn(data)
    # Words of this story that the other stories never teach ("samantha"): written as the related episodes write them
    # inside a sentence, capitalized only when they almost always are.
    for word, written in story_words(related).items():
        dictionary.setdefault(word, written)
    return dictionary, exact, titles


def story_words(texts):
    """{lowercase word: its written form} from mixed-case texts, by how each word is written off a sentence start."""
    forms = defaultdict(Counter)
    for text in texts:
        starts = sentence_starts(text)
        for match in WORD.finditer(text):
            if match.start() not in starts and not (match.start() and text[match.start() - 1] == '$'):
                forms[match.group().lower()][match.group()] += 1
    result = {}
    for word, counts in forms.items():
        written, count = counts.most_common(1)[0]
        result[word] = written if written == word or count >= CAPITAL_SHARE * sum(counts.values()) else word
    return result


def strings(program):
    """(address, text) of every printable NUL-terminated string that starts on a word after another string's end."""
    data = struct.pack(f'>{len(program.main_words)}H', *program.main_words)
    result, start = [], 0
    while start < len(data):
        end = data.find(b'\0', start)
        if end < 0:
            break
        raw = data[start:end]
        if len(raw) >= 2 and all(32 <= b < 127 or b in (9, 10) for b in raw):
            result.append((start // 2, raw.decode('latin-1')))
        start = (end + 2) // 2 * 2
    return result


def norm(text):
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def sentence_starts(text):
    """The start offsets of words that begin a sentence."""
    starts = set()
    for match in WORD.finditer(text):
        before = text[:match.start()]
        if (SENTENCE_END.search(before) and not ABBREVIATION.search(before)) or not before.strip(' `"\'(.'):
            starts.add(match.start())
    return starts


def learn(pairs):
    """`pairs`: (New Rules strings, smartphone strings) per story. Returns {lowercase word: written form}."""
    forms = defaultdict(Counter)
    for ours, theirs in pairs:
        cased = {}
        for text in theirs:
            cased.setdefault(norm(text), text)
        for text in ours:
            twin = cased.get(norm(text))
            if twin is None:
                continue
            starts = sentence_starts(twin)
            twin_words = [(m.start(), m.group()) for m in WORD.finditer(twin)]
            our_words = [m.group() for m in WORD.finditer(text)]
            if [w.lower() for _, w in twin_words] != [w.lower() for w in our_words]:
                continue
            for (offset, written), lower in zip(twin_words, our_words):
                if offset not in starts:
                    forms[lower.lower()][written] += 1
    dictionary = {}
    for word, counts in forms.items():
        written, count = counts.most_common(1)[0]
        if written != word and count < CAPITAL_SHARE * sum(counts.values()) and word in counts:
            written = word
        dictionary[word] = written
    return dictionary


# Words a headline leaves lowercase unless they start or end it.
MINOR_WORDS = {'a', 'an', 'the', 'and', 'but', 'or', 'nor', 'for', 'of', 'on', 'at', 'to', 'by', 'in', 'from', 'with',
               'as', 'vs'}


def headline_case(text):
    """A title card's title: every word capitalized but minor ones inside it ("bonus scene!" -> "Bonus Scene!").
    Capitals already there stay; a `$KEY` and a format's `%s` are left alone ("%s morning." -> "%s Morning.")."""
    words = list(WORD.finditer(text))
    out = list(text)
    for n, match in enumerate(words):
        if match.start() > 0 and text[match.start() - 1] in '$%':
            continue
        if match.group().lower() in MINOR_WORDS and 0 < n < len(words) - 1:
            continue
        out[match.start()] = text[match.start()].upper()
    return ''.join(out)


def capitals(text):
    return sum(c.isupper() for c in text)


def title_case(text):
    """Names: every word capitalised ("mr. hotpants" -> "Mr. Hotpants")."""
    out = list(text)
    for match in WORD.finditer(text):
        if match.start() == 0 or text[match.start() - 1] != '$':
            out[match.start()] = text[match.start()].upper()
    return ''.join(out)


def known_form(lower, dictionary, names):
    """How a lowercase word is written: the dictionary's form, a name capitalized, a common acronym, or None."""
    if lower in dictionary:
        return dictionary[lower]
    if lower in names:
        return lower[:1].upper() + lower[1:]
    return COMMON_ACRONYMS.get(lower) or OWN_NAMES.get(lower)


def apply(text, dictionary, names=(), unknown=None):
    """`text` with sentence case and the dictionary's forms; `names` are written with capitals. Same length."""
    out = list(text)
    starts = sentence_starts(text)
    places = set()
    for match in GAZETTEER.finditer(text):                  # "baton rouge" -> "Baton Rouge"
        out[match.start():match.end()] = string.capwords(match.group())
        places.update(range(match.start(), match.end()))
    for match in WORD.finditer(text):
        word = match.group()
        if match.start() > 0 and text[match.start() - 1] == '$' or match.start() in places:
            continue                                        # a $KEY substitution, or a place name
        lower = word.lower()
        written = known_form(lower, dictionary, names)
        for ending in ("'s", "s'", "'", 's'):               # "zoe's" as "Zoe" is written, "'ryan'", "djs" as "DJ"
            if written is None and lower.endswith(ending):
                base = known_form(lower[:-len(ending)], dictionary, names)
                # a plural only after an acronym: "marks" isn't "Marks"
                if base is not None and base != lower[:-len(ending)] and (ending != 's' or base.isupper()):
                    written = base + word[-len(ending):]
        if written is None:
            written = lower
            if unknown is not None and lower not in ('a',):
                unknown[lower] += 1
        if match.start() in starts or HONORIFIC.search(text[:match.start()]):
            written = written[:1].upper() + written[1:]
        if len(written) == len(word):
            out[match.start():match.end()] = written
    for match in ACRONYM.finditer(text):                    # "h.e.c.t.o.r." -> "H.E.C.T.O.R."
        out[match.start():match.end()] = match.group().upper()
    for match in GRADE.finditer(text):                      # "a d-plus" -> "a D-plus"
        out[match.start()] = match.group().upper()
    for match in QUOTED_TITLES.finditer(text):              # "'the valley'" -> "'The Valley'"
        out[match.start():match.end()] = string.capwords(match.group())
    for match in OWN_TITLE.finditer(text):                  # "the beatdown of '06" -> "The Beatdown of '06"
        out[match.start():match.end()] = OWN_TITLES[match.group().lower()]
    return ''.join(out)


def recase_program(program, dictionary, names=(), titles=(), addresses=None, unknown=None, exact=None,
                   headlines=()):
    """The program's main data bank with every string (or those at `addresses`) cased in place. A string the paired
    smartphone story writes too (`exact`: lowercase text -> its casing) takes that casing; one equal to a known
    mixed-case title (`titles`) takes its casing; a name (`names`, lowercase) is title-cased. A title card's title
    (`headlines`: addresses) is headline-cased."""
    words = list(program.main_words)
    data = bytearray(struct.pack(f'>{len(words)}H', *words))
    known = {title.lower(): title for title in titles}
    known.update(exact or {})
    # New Rules often splits one smartphone line into several strings: a string found inside a twin line copies its
    # casing letter for letter, starting with a capital.
    twin = '\n'.join((exact or {}).values())
    twin_lower = twin.lower()
    for address, text in strings(program):
        if addresses is not None and address not in addresses:
            continue
        found = []
        if len(text) >= SUBSTRING_MIN and text == text.lower():
            start = twin_lower.find(text)
            while start >= 0 and len(found) < 20:
                if start > 0 and twin[start - 1].isalnum() and text[0].isalnum():
                    start = twin_lower.find(text, start + 1)     # inside a word or key ("$SUPERZOE tries...")
                    continue
                piece = list(twin[start:start + len(text)])
                for match in WORD.finditer(text):           # "$ZOE tries…" is a name key there: "Zoe tries…" here
                    if start + match.start() > 0 and twin[start + match.start() - 1] == '$':
                        piece[match.start():match.end()] = title_case(match.group())
                piece = ''.join(piece)
                found.append(piece[:1].upper() + piece[1:])
                start = twin_lower.find(text, start + 1)
        candidates = ([known[text]] if text in known else []) + found
        if candidates:
            cased = max(candidates, key=capitals)
        elif text in names:
            cased = title_case(text)
        else:
            cased = apply(text, dictionary, {w for name in names for w in WORD.findall(name)}, unknown)
        for title in titles:                                 # the story's own title (and related ones) inside a line
            core = re.sub(r'^\d+:\s*', '', title).rstrip('!?.').strip()
            if core and ' ' in core:
                cased = re.sub(r'\b' + re.escape(core) + r'\b', lambda m: core, cased, flags=re.IGNORECASE)
        if address in headlines:
            cased = headline_case(cased)
        cased = cased.encode('latin-1')
        data[address * 2:address * 2 + len(cased)] = cased
    return tuple(struct.unpack(f'>{len(words)}H', bytes(data)))
