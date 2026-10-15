"""Cause of Death's episode lists in SHS HD's picker: categories (the tile grid, Episodes On Demand) and first
release dates (Now Airing).

The picker (`episode_picker.PickerModel`) is SHS HD's; only the grouping is CoD's own (owner's choice, 2026-10-14).
SHS's rules (`episode_index.build_rows`) misfile CoD: its bundled base game becomes "Mega Packs", and uncatalogued
episodes take a season from SHS's pack numbering (pack 1001 is not a season here). So:

* **Categories** are CoD's catalogue's own (`cod_options.sav`): "VOLUME ONE" (the base game's synthetic entry, pack 0
  episode 0), "VOLUME TWO" to "VOLUME SIX", "Season 7" to "Season 15" for the Volume sets, "Volume 14" / "Volume 16"
  for their chapters, "SIDE STORIES", "PREMIUM CONTENT". The device catalogues name the sets that way themselves.
  Episodes no catalogue in the library lists are filed by `FALLBACK_CATEGORIES`.
* **Order.** Volume One, then the volumes by number, then Side Stories and Premium Content, as SHS HD's rule puts its
  seasons before the generic categories, then any other category (the Now Airing Special's). CoD's own iPhone list
  (IMG_0467, and 1.4.7's episode catalogue) puts Premium Content and Side Stories right after Volume One instead.
  Within a category episodes go by first release.
* **Dates** (`RELEASE_DATES`) are docs/COD_RELEASE_DATES.md's first releases, keyed by the library's own titles. A
  Volume set takes its Chapter One's date, as SHS's season bundles take their season's start (the help page says
  episodes are listed "when each chapter first became playable"). Secret Files was never announced; its date is the
  store listing's (an upload date), the doc's fallback.
"""
import re

from ..episode_catalog import basename
from ..episode_index import PickerRow, build_chronological_rows, episode_label, sort_key, title_case

VOLUME_ONE = 'VOLUME ONE'
VOLUME_ONE_TITLE = 'Volume One: The Maskmaker'            # the catalogue's base-game title; also bank 13 string 182
SIDE_STORIES, PREMIUM = 'Side Stories', 'Premium Content'
FALLBACK_CATEGORIES = {
    # 1.4.7's episode catalogue files (1201, 45) "Interlude: Perfect Getaway" here, under its On Demand file's name.
    '13_interlude_airing.exp': 'Volume 13',
    # Owner's choice (2026-10-14): Premium Content. 1.3.4's catalogue files its byte copy (1_1_magic_school.exp) under
    # "Interlude", a category of one.
    '12_fallon_family_christmas.exp': PREMIUM,
    # No catalogue lists the free Now Airing promo. 1.4.7's store listing (mtxprods, product 840878) files it under
    # a category of its own, by its own name (owner, 2026-10-15: follow the store, not our earlier Side Stories
    # placement and "Just Another Day" caption).
    'now_airing_special.exp': 'Now Airing Special',
}
TRAILING = (SIDE_STORIES.casefold(), PREMIUM.casefold())
NUMBERS = {word: index for index, word in enumerate(
    'one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen'.split(), 1)}

RELEASE_DATES = {
    'Volume 2 Set': '2010-12-17',                                         # Volume 2 - Chapter One: Tough Love
    'Volume One': '2010-12-17',                                           # Volume One: The Maskmaker (base game)
    'Volume 3 Set': '2011-02-04',                                         # Volume 3 - Chapter One: Prey
    'Your Case: The Missing Child': '2011-03-11',
    'Side Stories: Detective Kalaba, Part 1': '2011-04-01',
    'Side Stories: Detective Kalaba, Part 2': '2011-04-08',
    'Volume 4 Set': '2011-04-15',                                         # Volume 4 - Chapter One: Zero Hour
    "Side Stories: Amy's Case, Part 1": '2011-06-10',
    'Secret Files': '2011-06-13',
    "Side Stories: Amy's Case, Part 2": '2011-06-17',
    'Volume 5 Set': '2011-06-23',                                         # Volume 5 - Chapter One: Dread Silence
    'Now Airing Special': '2011-07-14',                                   # Now Airing Special (free short story)
    'Side Stories: Fallon And Yeong, Part 1': '2011-08-22',
    'Side Stories: Fallon And Yeong, Part 2': '2011-08-29',
    'Volume 6 Set': '2011-09-05',                                         # Volume 6 - Chapter One: Opening Moves
    'Love and Bullets': '2011-09-19',                                     # Love and Bullets (short story collection)
    'What Happened To Colt, Part 2': '2011-10-21',
    'Halloween Special: Dead Man Walking, Part 1': '2011-10-31',
    'Halloween Special: Dead Man Walking, Part 2': '2011-11-07',
    'Volume 7: The Ladykiller': '2011-11-14',                             # Volume 7 - Chapter One: Bad Romance
    'A Cause of Death Christmas': '2012-01-03',
    'Side Stories: Greene Zone, Part 1': '2012-01-23',
    'Side Stories: Greene Zone, Part 2': '2012-01-30',
    'Valentine Short Stories': '2012-02-06',
    'Volume 8: The Kraken': '2012-02-13',                                 # Volume 8 - Chapter One: Tendrils
    'First Date, First Kiss, First Kill': '2012-03-05',
    'Side Stories: In The Cards, Part 1': '2012-04-09',
    'Side Stories: In The Cards, Part 2': '2012-04-16',
    'Volume 9: Livewire': '2012-04-23',                                   # Volume 9 - Chapter One: Walk the Wire
    'Buried Secrets, Buried Lives': '2012-06-25',
    'Side Stories: Fourth of July Special, Part 1': '2012-06-25',
    'Side Stories: Fourth of July Special, Part 2': '2012-07-02',
    'Volume 10: Nightmare': '2012-07-09',                                 # Volume 10 - Chapter One: Fear and Loathing
    'Life Lessons, Deadly Desires': '2012-08-20',
    'Side Stories: Far From Home, Part 1': '2012-09-10',
    'Side Stories: Far From Home, Part 2': '2012-09-17',
    'Volume 11: The Salazars': '2012-09-24',                              # Volume 11 - Chapter One: Best Served Cold
    'Halloween Special: Undying Love': '2012-10-30',
    'Side Stories: Peacemaker, Part 1': '2012-11-26',
    'Side Stories: Peacemaker, Part 2': '2012-12-03',
    'Volume 12: The Boogeyman': '2012-12-17',                             # Volume 12 - Chapter One: Monsters Among Us
    'Holiday Interlude: A Fallon Family Christmas': '2012-12-24',
    'Side Stories: Kai Hard, Part 1': '2013-02-18',
    'Side Stories: Kai Hard, Part 2': '2013-02-25',
    'Volume 13: Spinnerette': '2013-03-04',                               # Volume 13 - Chapter One: The Creeping Darkness
    'Interlude: Perfect Getaway': '2013-04-02',                           # Volume 13 - Interlude: Perfect Getaway
    'Side Stories: Seth, Lies, and Videotape, Part 1': '2013-05-06',
    'Side Stories: Seth, Lies, and Videotape, Part 2': '2013-05-13',
    'Chapter One: Joint Forces': '2013-05-20',                            # Volume 14 - Chapter One: Joint Forces
    'Chapter Two: Accelerant': '2013-05-27',                              # Volume 14 - Chapter Two: Accelerant
    'Chapter Three: Catch and Release': '2013-06-03',                     # Volume 14 - Chapter Three: Catch and Release
    'Chapter Four: One Step Ahead': '2013-06-10',                         # Volume 14 - Chapter Four: One Step Ahead
    'Interlude: Madness In Orbit': '2013-06-17',                          # Volume 14 - Interlude: Madness In Orbit
    'Chapter Five: Second Chances': '2013-06-24',                         # Volume 14 - Chapter Five: Second Chances
    'Short Story: Retreats and Advances': '2013-07-08',                   # Volume 14 - Short Story: Retreats and Advances
    'Chapter Six: The Greater Good': '2013-07-15',                        # Volume 14 - Chapter Six: The Greater Good
    'Chapter Seven: Prodigal Son': '2013-07-22',                          # Volume 14 - Chapter Seven: Prodigal Son
    'Chapter Eight: New World Order, Part 1': '2013-07-29',               # Volume 14 - Chapter Eight: New World Order, Part 1
    'Chapter Nine: New World Order, Part 2': '2013-08-05',                # Volume 14 - Chapter Nine: New World Order, Part 2
    'Side Stories: Forks in the Road, Part 1': '2013-08-15',
    'Side Stories: Forks in the Road, Part 2': '2013-08-19',
    'Secret Files 02': '2013-09-03',
    'Volume 15: The Cleaners': '2013-09-10',                              # Volume 15 - Chapter One: Across The Pond
    'Holiday Stories: Past and Presents': '2013-12-23',
    'Side Stories: City of Love, Part 1': '2014-02-24',
    'Side Stories: City of Love, Part 2': '2014-03-11',
    'Chapter One: Haunted': '2014-03-24',                                 # Volume 16 - Chapter One: Haunted
    'Chapter Two: Metamorphosis': '2014-04-08',                           # Volume 16 - Chapter Two: Metamorphosis
    'Chapter Three: Unfinished Business': '2014-04-23',                   # Volume 16 - Chapter Three: Unfinished Business
    'Chapter Four: Sunrise': '2014-06-04',                                # Volume 16 - Chapter Four: Sunrise
    'Interlude: Promises and Compromises': '2014-06-04',                  # Volume 16 - Interlude: Promises and Compromises
    'Chapter Five: The Red Room': '2014-06-20',                           # Volume 16 - Chapter Five: The Red Room
    'Chapter Six: True Faces': '2014-07-04',                              # Volume 16 - Chapter Six: True Faces
    'Chapter Seven: Sunset': '2014-07-16',                                # Volume 16 - Chapter Seven: Sunset
}


def category(record, catalog, *, bundled=lambda record: False):
    """The catalogue category a record is listed under (as written, e.g. "VOLUME TWO", "Season 7")."""
    if bundled(record):
        return VOLUME_ONE
    label = catalog.category(record)
    if label and label.strip():
        return label.strip()
    return FALLBACK_CATEGORIES.get(basename(record['name']), PREMIUM)


def label(record, *, bundled=lambda record: False):
    """The tile caption / row title: the base game's full title, else SHS HD's rule."""
    if bundled(record):
        return VOLUME_ONE_TITLE
    return episode_label(record)


def volume_number(title):
    """2 for "Volume Two", 7 for "Season 7", 14 for "Volume 14"; None for any other category."""
    match = re.fullmatch(r'(?:volume|season) (\w+)', title.strip().casefold())
    if not match:
        return None
    word = match.group(1)
    return int(word) if word.isdigit() else NUMBERS.get(word)


def released(record):
    return RELEASE_DATES.get(record['titles'][0], '9999'), sort_key(record)


def build_rows(records, catalog, *, bundled=lambda record: False):
    """Rows of episodes, one per category: the volumes in order, then Side Stories and Premium Content. Categories
    naming the same volume share a row ("Season 13" for the Volume 13 set, "Volume 13" for its Perfect Getaway
    interlude), under the label of the row's earliest episode."""
    rows = {}
    for record in records:
        title = title_case(category(record, catalog, bundled=bundled))
        number = volume_number(title)
        key = f'volume {number}' if number is not None else title.casefold()
        rows.setdefault(key, []).append((record, title))

    def order(row):
        title = row.title.casefold()
        number = volume_number(row.title)
        if number is not None:
            return 0, number, ''
        return (1, TRAILING.index(title), '') if title in TRAILING else (2, 0, title)
    result = []
    for key, members in rows.items():
        members.sort(key=lambda member: released(member[0]))
        result.append(PickerRow(f'category:{key}', members[0][1], tuple(record for record, _ in members)))
    return sorted(result, key=order)


def category_labels(records, catalog, *, bundled=lambda record: False):
    return {record['id']: row.title for row in build_rows(records, catalog, bundled=bundled) for record in row.episodes}


def build_airing_rows(records):
    """Now Airing: one row per year of first release. Nothing is set apart, unlike SHS's redundant season bundles:
    the one overlap, Interlude: Perfect Getaway's Now Airing file, repeats an interlude inside the Volume 13 set,
    which is the only copy of that volume's other chapters, so both stay, each at its own date (both 2013)."""
    return build_chronological_rows(records, RELEASE_DATES)
