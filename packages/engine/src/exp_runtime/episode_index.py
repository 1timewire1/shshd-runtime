"""Which release an episode belongs to, which imports are the same story, and the HD picker's rows.

The iOS HD app's episode picker (`SHSMTXMenu`) groups episodes into rows and shows one preview image per episode.
Its rows come from a downloaded server config that no longer exists, so they are rebuilt here from what the player
imported: the categories of the `shs_options.sav` catalogs (the HD one is primary, the Android one is optional and only
needed for standard episodes), or a season derived from the pack id.

Everything here is derived data about user-supplied episodes; nothing original is embedded.
"""
from dataclasses import dataclass
import hashlib
import re
import struct

HD, STANDARD = 'hd', 'standard'
# A library record's `index`: the `image_variant` rules its release was read with (missing: 1, widths only; 2: heights
# too). An undecided release read with older rules is read again (`ContentLibrary.unindexed`).
INDEX_VERSION = 2
SIGNATURE_SIZE = 32
OVERLAP_THRESHOLD = 0.9
PREMIUM_LABEL = 'Premium Content'
VOTE_PACKS = (1000, 2000, 3000, 4000, 5000)
# Pack ids of the season packs: 101 = Season 1, 201 = Season 2 ... 1201 = Season 12 (100 per season, +1).
_SEASON_PACK = re.compile(r'^(\d+)01$')
# Episodes whose download id does not match the preview the app ships for them.
PREVIEW_ALIASES = {
    (401, 24): (401, 64),        # "Set 4" episode filed under a mistyped id
    (5, 9): (1, 1),              # The New Girl
}
SEASON_PACKS_1_TO_5 = (101, 201, 301, 401, 501)
_TEXT_RUN = re.compile(rb'[\x20-\x7e]{10,}')


# ---------------------------------------------------------------- signatures and variants

def script_signature(programs):
    """A bottom-k sketch of the episode's script text: the smallest hashes of its text runs, as one hex string.

    Two copies of the same story (the standard and the HD release) share nearly all their text; overlap of the
    sketches estimates the Jaccard similarity of the two sets of runs.
    """
    runs = set()
    for program in programs.values():
        data = b''.join(word.to_bytes(2, 'big') for word in program.main_words)
        for match in _TEXT_RUN.finditer(data):
            runs.add(re.sub(rb'\s+', b' ', match.group().strip().lower()))
    hashes = sorted(int.from_bytes(hashlib.sha256(run).digest()[:8], 'big') for run in runs)
    return ''.join(f'{value:016x}' for value in hashes[:SIGNATURE_SIZE])


def _hashes(signature):
    return {int(signature[i:i + 16], 16) for i in range(0, len(signature), 16)}


def signature_overlap(a, b):
    if not a or not b:
        return 0.
    left, right = _hashes(a), _hashes(b)
    union = sorted(left | right)[:SIGNATURE_SIZE]
    return sum(1 for value in union if value in left and value in right) / len(union)


def image_variant(archive):
    """'hd' / 'standard' from the portrait art, or None when the episode carries none that tells.

    HD portraits are 256 pixels wide, the standard release's 128; standard backgrounds are 400 or 480 wide (HD's
    live in the app bundle). Measured on every shipped episode of both sets. Narrower HD portraits (148 to 254
    wide) are still 256 tall, and narrower standard ones 128 tall; no standard picture in the library is 256 tall.
    Counting heights too found 29 HD episodes whose art is all narrower than 256 (Homecoming_Sara_1: fifteen
    226 x 256 portraits), which width alone left undecided and the picker then marked standard.
    """
    hd = standard = 0
    for resource_id in archive.entries:
        head = archive.read(resource_id)[:24]
        if head[:8] == b'\x89PNG\r\n\x1a\n' and len(head) >= 24:
            width, height = struct.unpack('>II', head[16:24])
            if width == 256 or height == 256:
                hd += 1
            elif width in (128, 400, 480) or height == 128:
                standard += 1
    if hd == standard:
        return None
    return HD if hd > standard else STANDARD


def is_vote_pack(record):
    return record['pack_id'] in VOTE_PACKS or 'vote pack' in record['titles'][0].casefold()


def same_story(a, b):
    """Two different records that are one story in two releases: the same title, and either the same ids or
    near-identical script text under different ids. Vote packs (one script, several candidates sharing a generic
    title, e.g. "Taylor Large Vote Package") never merge *by text* -- but the same specific candidate's own two
    releases, sharing both its pack and episode id, are still the same story (found in the library: MTX_Dr_Pepper_1
    through _5 and Sam3/Sara3/Taylor3/Zoe3 each import an hd and a standard record at the identical (pack, episode)
    id, and were shown as if they were two different candidates until this checked ids before the vote-pack exclusion).

    A shared (pack, episode) id is not always the same story on its own: two unrelated episodes can coincidentally
    reuse one (confirmed in the library -- pack 7, episode 2005 is both "April Fools" and, unrelated, "St. Patrick's
    Day"), so this still requires the title to agree too, *unless* the two records are literally the same imported
    file (matched by its own filename): that can carry a slightly reworded title between releases and still be one
    story (found in the library: 13_4_Getting_Over_Howard.exp's own "Special: Getting Over Howard" (HD) versus
    "Getting Over Howard" (standard); MTX_The_Storm_Part_2.exp's "...Part Two" versus "...Part 2"; MTX_SNG_The_
    Floating_Isle.exp's "The Super New Girl 2" versus "The Floating Isle" -- all three shown as duplicate rows
    before this checked the filename)."""
    if a['id'] == b['id'] or a.get('legacy') != b.get('legacy'):
        return False            # shshd-runtime: a translation from another game is never its smartphone twin
    same_slot = (a['pack_id'], a['episode_id']) == (b['pack_id'], b['episode_id'])
    if same_slot and a['name'].casefold() == b['name'].casefold():
        return True
    if a['titles'][0].casefold() != b['titles'][0].casefold():
        return False
    if same_slot:
        return True
    if is_vote_pack(a) or is_vote_pack(b):
        return False
    return signature_overlap(a.get('signature', ''), b.get('signature', '')) >= OVERLAP_THRESHOLD


def resolve_variants(records, catalog):
    """{id: 'hd' | 'standard'} for every record.

    A record's own evidence (an explicit choice at import, else its portrait art) decides where it exists. The rest
    carry no art of their own, so they are the other release of a twin that does have evidence, or HD when the HD
    catalog lists them, or standard.
    """
    variants = {r['id']: r['variant'] for r in records if r.get('variant') in (HD, STANDARD)}
    known = [r for r in records if r['id'] in variants]
    for record in records:
        if record['id'] in variants:
            continue
        twins = [variants[t['id']] for t in known if same_story(record, t)]
        if twins:
            variants[record['id']] = HD if twins.count(STANDARD) > twins.count(HD) else STANDARD
        else:
            variants[record['id']] = HD if HD in catalog.sources(record) else STANDARD
    return variants


def duplicates(records, prefer, *, bundled=lambda record: False):
    """Ids of the records hidden because another import of the same story is shown instead.

    Stories that share a title and either their ids or nearly all their script text are one story; the release
    the player can render (`prefer`) wins, then an episode with art of its own over a script-only one, then the
    bundled one.
    """
    def rank(record):
        evidence = record.get('variant')
        return (0 if evidence == prefer else 1 if evidence is None else 2, not bundled(record),
                record['name'].casefold(), record['id'])

    # `same_story` always needs a shared title or a shared (pack, episode) id, so grouping by either first (rather
    # than every record against every other one) still finds every pair worth checking -- including the same
    # imported file at the same (pack, episode) id under two slightly different titles (see `same_story`), which a
    # title-only grouping would never even compare.
    by_title, by_slot = {}, {}
    for record in records:
        by_title.setdefault(record['titles'][0].casefold(), []).append(record)
        by_slot.setdefault((record['pack_id'], record['episode_id']), []).append(record)

    parent = {record['id']: record['id'] for record in records}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_a] = root_b

    for bucket in (*by_title.values(), *by_slot.values()):
        for index, a in enumerate(bucket):
            for b in bucket[index + 1:]:
                if same_story(a, b):
                    union(a['id'], b['id'])

    groups = {}
    for record in records:
        groups.setdefault(find(record['id']), []).append(record)

    hidden = set()
    for group in groups.values():
        if len(group) < 2:
            continue
        _keeper, *rest = sorted(group, key=rank)
        hidden.update(r['id'] for r in rest)
    return hidden


# ---------------------------------------------------------------- rows

@dataclass(frozen=True)
class PickerRow:
    key: str
    title: str
    episodes: tuple


# Categories that gather unrelated packs; they stay one row however many packs they span.
GENERIC = ('premium content', 'special', 'magic school', 'mtx', 'mega packs')
ALIASES = {'premium': PREMIUM_LABEL}
_SEASON_LABEL = re.compile(r'season (\d+)', re.IGNORECASE)


def title_case(label):
    """Catalog categories are sometimes all caps ('SEASON 2'): title-case those, keep authored capitals and acronyms."""
    if label.isupper():
        return ' '.join(word if word == 'MTX' else word[:1] + word[1:].lower() for word in label.split(' '))
    return label


def season_label(record):
    match = _SEASON_PACK.match(str(record['pack_id']))
    if match and 1 <= int(match.group(1)) <= 40:
        return f'Season {int(match.group(1))}'
    return None


# Titles the game ships that don't work as a caption on their own, keyed by (pack_id, episode_id)
# since the text itself isn't a safe or unique match: Homecoming_Taylor_2.exp ships as "Specials", the
# same Medium Vote Package slot its three siblings correctly title "<Name> Medium Vote Package".
TITLE_OVERRIDES = {
    (1000, 2): 'Taylor Medium Vote Package',
}


def episode_label(record, language='en'):
    """The tile's caption: the episode title without its 'N: ' numbering, a known bad title corrected,
    and an underscore left in by mistake ("Dance_Dilemma") rendered as a space. Another title language takes that
    language's title (English where it has none), whose numbering may read 'N - ' or 'N. ' instead."""
    if language == 'en':
        title = TITLE_OVERRIDES.get((record['pack_id'], record['episode_id']), record['titles'][0])
        title = re.sub(r'^\d+:\s*', '', title)
    else:
        from .languages import episode_title
        title = re.sub(r'^\d+\s*(?::|-|\.)\s*', '', episode_title(record, language))
    return title.replace('_', ' ')


def _range(records):
    numbers = sorted(r['episode_id'] for r in records)
    lo, hi = numbers[0], numbers[-1]
    return f'{lo}–{hi}' if lo != hi else str(lo)


def sort_key(record):
    """Season packs first in numeric order; specials and one-off packs (ids below 100) after them. A translated
    episode's `order` (content.legacy_fields) stands in for its id."""
    pack = record['pack_id']
    return (pack if pack >= 100 else 10 ** 6 + pack, record.get('order', record['episode_id']), record['id'])


def episode_category(record, variant, catalog, *, mega_label, novel_label, bundled):
    """The category an episode is listed under.

    The catalog of the episode's own release wins and the other release's fills the gaps. The HD catalog files some
    Season 3 episodes under "Season 1"; a "Season N" that disagrees with the pack's own season is not trusted.
    """
    from .episode_catalog import basename
    if record.get('category'):
        return record['category']        # shshd-runtime: set on import (content.legacy_fields)
    other = STANDARD if variant == HD else HD
    pack_season = season_label(record)
    for source in (variant, other):
        label = catalog.category(record, source=source)
        if not label:
            continue
        match = _SEASON_LABEL.fullmatch(label.strip())
        if source == HD and match and pack_season and f'Season {int(match.group(1))}' != pack_season:
            continue
        return label
    if bundled(record):
        return novel_label if basename(record['name']) == 'novel_bonus_content.exp' else mega_label
    if is_vote_pack(record):
        return PREMIUM_LABEL
    return pack_season or PREMIUM_LABEL


def build_rows(records, variants, catalog, *, mega_label='Mega Packs', novel_label='Special SHS Novel Content',
               bundled=lambda record: False):
    """Rows of episodes, one per catalog category (title-cased).

    A category that spans several packs is split off per pack where the catalog names the pack's season
    ('A New Start: Season 2'); uncategorized episodes fall back to the season implied by their pack id, and vote
    packs to Premium Content.
    """
    def clean(label):
        label = title_case(label.strip())
        return ALIASES.get(label.casefold(), label)

    rows = {}
    for record in records:
        label = clean(episode_category(record, variants[record['id']], catalog, mega_label=mega_label,
                                       novel_label=novel_label, bundled=bundled))
        rows.setdefault(label.casefold(), [label, []])[1].append(record)
    # Split reused, non-generic names by pack where the catalog names the packs.
    for key, (label, episodes) in list(rows.items()):
        packs = {r['pack_id'] for r in episodes}
        if key in GENERIC or len(packs) < 2:
            continue
        for pack in sorted(packs):
            title = catalog.pack_title(pack) if pack >= 100 else None
            if not title or clean(title).casefold() == key:
                continue
            title = clean(title)
            moved = [r for r in episodes if r['pack_id'] == pack]
            rows[key][1] = [r for r in rows[key][1] if r['pack_id'] != pack]
            rows.setdefault(title.casefold(), [title, []])[1].extend(moved)
    result = [PickerRow(f'category:{key}', label, tuple(sorted(episodes, key=sort_key)))
              for key, (label, episodes) in rows.items() if episodes]
    result.sort(key=lambda row: (row.title.casefold() != mega_label.casefold(), row.title.casefold() in GENERIC,
                                 sort_key(row.episodes[0])))
    return result


def category_labels(records, variants, catalog, *, mega_label='Mega Packs', novel_label='Special SHS Novel Content',
                    bundled=lambda record: False):
    """Maps each record's id to the exact category label `build_rows()` would file it under -- for showing a
    record's own category elsewhere (the Now Airing list's per-row subtitle) without grouping by it."""
    rows = build_rows(records, variants, catalog, mega_label=mega_label, novel_label=novel_label, bundled=bundled)
    return {record['id']: row.title for row in rows for record in row.episodes}


def format_airdate(iso_date):
    """`'2009-11-22'` as `'11/22/2009'`, for display next to a title."""
    year, month, day = iso_date.split('-')
    return f'{month}/{day}/{year}'


def build_chronological_rows(records, release_dates, *, redundant_bundles=(), vote_packages=(),
                             bundles_label='Season Bundles', vote_label='Vote Packages', unknown_label='Date Unknown'):
    """Rows for a "Now Airing" list grouped by release year (earliest first) instead of by category.

    `release_dates` maps an episode's own title (`record['titles'][0]`) to an ISO date string, external
    research with no native source (see docs/EPISODE_RELEASE_DATES.md). `redundant_bundles` and
    `vote_packages` name titles to pull into their own trailing rows instead of the year they released in:
    a season sold again as one bundle after already airing week by week, or a bonus purchase that isn't a
    narrative episode in its own right. A title in neither set, whatever it is, sorts into its own real year.
    """
    years, vote, bundles, unknown = {}, [], [], []
    for record in records:
        title = record['titles'][0]
        if title in vote_packages:
            vote.append(record)
        elif title in redundant_bundles:
            bundles.append(record)
        elif title in release_dates:
            years.setdefault(release_dates[title][:4], []).append(record)
        else:
            unknown.append(record)

    def dated(record):
        return release_dates.get(record['titles'][0], ''), sort_key(record)

    result = [PickerRow(f'year:{year}', year, tuple(sorted(episodes, key=dated)))
              for year, episodes in years.items()]
    result.sort(key=lambda row: row.title)
    if vote:
        result.append(PickerRow('extra:vote', vote_label, tuple(sorted(vote, key=sort_key))))
    if bundles:
        result.append(PickerRow('extra:bundles', bundles_label, tuple(sorted(bundles, key=sort_key))))
    if unknown:
        result.append(PickerRow('extra:unknown', unknown_label, tuple(sorted(unknown, key=sort_key))))
    return result


def preview_names(record):
    """Candidate bundled preview file names for an episode, best first (`preview_<pack>_<episode>.jpg`)."""
    key = (record['pack_id'], record['episode_id'])
    names = [PREVIEW_ALIASES.get(key, key)]
    if key[0] in SEASON_PACKS_1_TO_5:
        # Seasons 1-5 number their episodes globally, so a pack id that disagrees with the episode still finds it.
        names += [(pack, key[1]) for pack in SEASON_PACKS_1_TO_5]
    return [f'preview_{pack}_{episode}.jpg' for pack, episode in names]
