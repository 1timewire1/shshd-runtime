"""Add to a library's HD twin store what the per-story pairing (build_hd_twins.py) cannot reach (prototype).

    python tools/extend_hd_twins.py --library LIBRARY [--dry-run]

1. Season bundles. A season also ships as one HD file (A_New_Start_Season_2.exp: the intro script 25001, then two
   scripts per episode), whose title is its first episode's, so it is never the same story as the standalone
   standard episodes it contains, and its scripts are rebuilt rather than copied (resource ids do not line up). A
   standard episode is paired with an HD record of the same pack whose scripts contain its own (by their text: each
   standalone script finds its bundle script at 92-100% shared lines, any other under 5%), and
   `hd_twins.pair_art_detailed` runs on the pair from the bundle's intro, which registers the whole season's cast at
   its first step: portraits pair by character name and expression slot. That cast is each character's look as the
   intro registers it, so a character with more than one look across the season's standalone episodes (a Halloween
   costume: 2_7's Paige and Zoe) is left out -- the name cannot tell which look the intro has (found by eye on the
   pairs; a picture correlation cannot either, the HD portraits being redrawn).
2. Reused backgrounds. A background with no twin yet is compared with every HD background in the library (opaque,
   700 px wide or more); a correlation of 0.98 or more on `hd_twins.correlation`'s small colour version is taken as
   the same picture. HD reuses backgrounds across stories (the art catalogue found 45 such pairs).

Only pictures the store does not already hold are added (`TwinStore.add`); rerun tools/build_hd_coverage.py after.

The looks left out in 1 can be paired by hand: `--review DIR` writes DIR/costume_review.md (each such look's first
expression beside the bundle's portraits nothing links to yet); `--confirmed FILE` reads lines
`<standard episode file> <standard base id> = [<HD episode file>] <base id> [xN]` (the season bundle when no HD episode
is named) and pairs the expressions slot by slot: five, or N (`x1` pairs one picture, as the art catalogue's matches do).
A confirmed line overrides whatever the store already pairs that picture with, and `<episode file> <id> = none [xN]`
removes a wrong pair (the standard picture keeps its own art), so corrections survive a rerun of 1 and 2.
"""
import argparse
import io
import math
import re
from pathlib import Path

from PIL import Image

from exp_runtime.content import ContentLibrary
from exp_runtime.hd_twins import LOCAL_ART, fingerprint, is_upgraded, pair_art_detailed

SHARED_LINES = 0.5              # a standalone script is inside a bundle when half its lines are in one bundle script
SAME_PICTURE = 0.98
BG_MIN, BG_HD = 300, 700


def lines(program):
    data = b''.join(word.to_bytes(2, 'big') for word in program.main_words + program.extra_words)
    return {text for text in re.split(rb'\x00+', data) if len(text) > 24 and text.isascii()}


def bundle_for(library, record, hd_records):
    """The HD record of the same pack whose scripts contain this standard episode's, or None."""
    own = library.open_episode(record['id'])
    first = lines(own.programs[min(own.programs)])
    if not first:
        return None
    for candidate in hd_records:
        if candidate.get('pack_id') != record.get('pack_id'):
            continue
        bundle = library.open_episode(candidate['id'])
        if len(bundle.programs) <= len(own.programs):
            continue
        if any(len(first & lines(program)) / len(first) >= SHARED_LINES for program in bundle.programs.values()):
            return candidate
    return None


def season_looks(library, records):
    """{name: set of first-expression pictures} across a season's standalone episodes, from each one's cast at its
    first step (`set_character_art_base` for everyone it shows)."""
    from exp_runtime.runtime import Session
    looks = {}
    for record in records:
        resources = library.open_episode(record['id'])
        session = Session(resources, ephemeral=True)
        session.advance()
        engine = session.engine
        for character, ids in engine.character_art_variants.items():
            name = engine.character_names.get(character)
            if name and ids and ids[0] >= 0 and resources.exists(ids[0]):
                looks.setdefault(name, set()).add(fingerprint(resources.raw_asset(ids[0])))
    return looks


def casts(library, record):
    """(resources, {name: expression ids}) of an episode's cast at its first step."""
    from exp_runtime.runtime import Session
    resources = library.open_episode(record['id'])
    session = Session(resources, ephemeral=True)
    session.advance()
    engine = session.engine
    return resources, {engine.character_names.get(c): list(ids) for c, ids in engine.character_art_variants.items()
                       if engine.character_names.get(c)}


def masked_picture(resources, resource_id):
    from export_art_catalog import picture
    try:
        image = picture(resources.raw_asset(resource_id))
    except Exception:
        return False
    return image is not None and image.getextrema()[3][0] == 0


def bank_portraits(library, record, bundle_record, looks, store, new):
    """{fingerprint: (standard, hd)}: the episode's shared-bank portraits with no HD (neither the app bundle's by id nor
    a twin), paired by character name and expression slot with the season bundle's intro cast. Characters with more
    than one look this season are left out (see `season_looks`); both pictures must be masked portraits."""
    resources, cast = casts(library, record)
    bundle, bundle_cast = casts(library, bundle_record)
    pairs = {}
    for name, ids in cast.items():
        if len(looks.get(name, ())) > 1 or name not in bundle_cast:
            continue
        for standard_id, hd_id in zip(ids, bundle_cast[name]):
            if not (0 <= standard_id < LOCAL_ART and hd_id >= LOCAL_ART) or library.hd_asset(standard_id) is not None:
                continue
            if not (resources.exists(standard_id) and bundle.exists(hd_id)):
                continue
            standard, hd = resources.raw_asset(standard_id), bundle.raw_asset(hd_id)
            key = fingerprint(standard)
            if key in new or key in pairs or store.twin(standard) is not None:
                continue
            if is_upgraded(standard, hd) and masked_picture(resources, standard_id) and masked_picture(bundle, hd_id):
                pairs[key] = (standard, hd)
    return pairs


def portrait_runs(resources, ids):
    """The masked (portrait) pictures among `ids`, as runs of consecutive ids: a character's expressions."""
    from export_art_catalog import picture
    runs, last = [], None
    for resource_id in sorted(ids):
        image = picture(resources.raw_asset(resource_id))
        if image is None or image.getextrema()[3][0] != 0:
            continue
        if last is not None and resource_id == last + 1:
            runs[-1].append(resource_id)
        else:
            runs.append([resource_id])
        last = resource_id
    return runs


REVIEW_INTRO = """# Season bundle looks to pair by hand

Each standard look below belongs to a character with more than one look this season (a costume), so the bundle pairing
left it out. Find its HD version among the bundle's portraits that nothing links to yet (first expression shown) and add
a line to a confirmed-pairs file: `<episode file> <standard base> = <bundle base>` (the five expressions pair in order),
then run `tools/extend_hd_twins.py --library LIBRARY --confirmed FILE`.
"""


def review(library, folder, seasons, looks, store, new):
    """DIR/costume_review.md: each still-unlinked look of a character with several looks this season, beside the
    bundle's unlinked portrait runs."""
    from exp_runtime.runtime import Session
    from export_art_catalog import picture
    folder.mkdir(parents=True, exist_ok=True)
    pack = (store.directory / 'pack.bin').read_bytes()
    linked = {fingerprint(pack[offset:offset + length]) for offset, length, *_ in store.index.values()}
    linked |= {fingerprint(hd) for _, hd in new.values()}
    out = [REVIEW_INTRO]
    for bundle_id in seasons:
        ambiguous = {name for name, pictures in looks[bundle_id].items() if len(pictures) > 1}
        bundle_record = next(r for r in library.episodes if r['id'] == bundle_id)
        records = seasons[bundle_id]
        bundle = library.open_episode(bundle_id)
        out += [f'## {bundle_record["name"]}', '', '### Looks to pair', '', '| Standard | Episode | Name | Base |',
                '|---|---|---|---|']
        for record in records:
            names = ambiguous
            resources = library.open_episode(record['id'])
            session = Session(resources, ephemeral=True)
            session.advance()
            for character, ids in session.engine.character_art_variants.items():
                name = session.engine.character_names.get(character)
                base = ids[0] if ids else -1
                if name not in names or base < LOCAL_ART or store.twin(resources.raw_asset(base)) is not None:
                    continue
                file = f'sd_{record["name"].removesuffix(".exp")}_{base}.png'
                picture(resources.raw_asset(base)).save(folder / file)
                out.append(f'| <img src="{file}" width="90"> | {record["name"]} | {name} | {base} |')
        runs = portrait_runs(bundle, [i for i in bundle.archive.entries
                                      if i >= LOCAL_ART and fingerprint(bundle.raw_asset(i)) not in linked])
        out += ['', '### Bundle portraits nothing links to yet', '', '| HD | Bundle base | Expressions |', '|---|---|---|']
        for run in runs:
            file = f'hd_{bundle_record["name"].removesuffix(".exp")}_{run[0]}.png'
            picture(bundle.raw_asset(run[0])).save(folder / file)
            out.append(f'| <img src="{file}" width="90"> | {run[0]} | {len(run)} |')
        out.append('')
    (folder / 'costume_review.md').write_text('\n'.join(out) + '\n', encoding='utf-8')
    print(f'review written to {folder / "costume_review.md"}')


def named(library, name, variant):
    """The library record called `name`, of `variant` if there is one."""
    records = [r for r in library.episodes if r['name'] == name]
    return next((r for r in records if r.get('variant') == variant), records[0] if records else None)


def confirmed_pairs(library, path, seasons):
    """({fingerprint: (standard, hd)}, {fingerprint: standard}) from the hand-confirmed lines, five expressions each,
    checked for size: the pairs, and the standard pictures a `none` line says have no HD picture."""
    bundles = {r['id']: r for r in library.episodes}
    by_name = {record['name']: (record, bundles[bundle_id]) for bundle_id, records in seasons.items() for record in records}
    pairs, unpaired = {}, {}
    for number, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        text = raw.split('#', 1)[0].strip()
        if not text:
            continue
        left, _, right = text.partition('=')
        try:
            episode, base = left.split()
            tokens = right.split()
            count = 5
            if tokens and re.fullmatch(r'x[1-5]', tokens[-1]):
                count = int(tokens.pop()[1:])         # "x1": just this picture (catalogue pairs, one per line)
            *source, target = tokens                  # "<bundle base>", "<HD episode file> <base>" or "none"
            base = int(base)
            target = None if target == 'none' and not source else int(target)
        except ValueError:
            print(f'{path}:{number}: expected "<episode file> <base> = [<HD episode file>] <base>|none [xN]"')
            continue
        name = episode if episode.endswith('.exp') else episode + '.exp'
        if target is None:
            # Not a pair after all: the standard picture keeps its own art (and is filled like any unpaired one).
            record = named(library, name, 'standard')
            if record is None:
                print(f'{path}:{number}: {name} is not in the library')
                continue
            resources = library.open_episode(record['id'])
            for slot in range(count):
                if not resources.exists(base + slot) or (slot and not masked_picture(resources, base + slot)):
                    break
                standard = resources.raw_asset(base + slot)
                unpaired[fingerprint(standard)] = standard
            continue
        if source:
            hd_name = source[0] if source[0].endswith('.exp') else source[0] + '.exp'
            # Pictures pair by their own bytes (the twin store's fingerprint), so the episodes only say where to read
            # them: the expected variant first, else any record of that name (older records carry no variant, a
            # standard picture can sit in an HD release, and some standard releases already ship HD-size art).
            record = named(library, name, 'standard')
            bundle_record = named(library, hd_name, 'hd')
            if record is None or bundle_record is None:
                print(f'{path}:{number}: {name} or {hd_name} is not in the library')
                continue
        elif name in by_name:
            record, bundle_record = by_name[name]
        else:
            print(f'{path}:{number}: {episode} is not a standalone episode of a season bundle; name the HD episode')
            continue
        resources, bundle = library.open_episode(record['id']), library.open_episode(bundle_record['id'])
        for slot in range(count):
            if not (resources.exists(base + slot) and bundle.exists(target + slot)):
                break
            # Only the character's real expressions: an unused slot holds whatever follows its art (`portrait_slot`).
            if slot and not (masked_picture(resources, base + slot) and masked_picture(bundle, target + slot)):
                break
            standard, hd = resources.raw_asset(base + slot), bundle.raw_asset(target + slot)
            if is_upgraded(standard, hd):
                pairs[fingerprint(standard)] = (standard, hd)
    return pairs, unpaired


def look(data):
    """`hd_twins.correlation`'s vector (colour on grey, 24 x 24), centred and normalised, or None."""
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = source.convert('RGBA')
    except (OSError, ValueError):
        return None
    if image.getextrema()[3][0] == 0 or min(image.size) < BG_MIN:
        return None                                  # transparent somewhere: not a background
    flat = Image.new('RGB', image.size, (128, 128, 128))
    flat.paste(image, (0, 0), image)
    values = [float(v) for pixel in flat.resize((24, 24), Image.BILINEAR).getdata() for v in pixel]
    mean = sum(values) / len(values)
    centred = [v - mean for v in values]
    norm = math.sqrt(sum(v * v for v in centred))
    if norm <= 1e-6:
        return None                                  # a flat wash: left to the per-story pairing's own rule
    return image.width, [v / norm for v in centred]


def sheet(pairs, path, height=120):
    """Each new pair as standard | HD, both scaled to `height`, in rows of six."""
    tiles = []
    for standard, hd in pairs.values():
        try:
            with Image.open(io.BytesIO(standard)) as a, Image.open(io.BytesIO(hd)) as b:
                a, b = a.convert('RGBA'), b.convert('RGBA')
        except (OSError, ValueError):
            continue
        a = a.resize((max(1, a.width * height // a.height), height))
        b = b.resize((max(1, b.width * height // b.height), height))
        tile = Image.new('RGBA', (a.width + b.width + 6, height), (60, 60, 60, 255))
        tile.paste(a, (0, 0), a)
        tile.paste(b, (a.width + 6, 0), b)
        tiles.append(tile)
    columns = 6
    width = max((t.width for t in tiles), default=1)
    rows = (len(tiles) + columns - 1) // columns
    out = Image.new('RGB', (columns * (width + 10), max(1, rows) * (height + 10)), (30, 30, 30))
    for i, tile in enumerate(tiles):
        out.paste(tile, ((i % columns) * (width + 10), (i // columns) * (height + 10)), tile)
    out.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true', help='report what would be added without writing')
    parser.add_argument('--sheet', type=Path, help='also write the new pairs side by side to this PNG, for a look')
    parser.add_argument('--review', type=Path, help='write a review page of the looks left to pair by hand')
    parser.add_argument('--confirmed', type=Path, help='pairs confirmed by hand: "<episode file> <base> = <bundle base>"')
    args = parser.parse_args()
    with ContentLibrary(args.library) as library:
        library.hd_art_mode = 'off'
        store = library.twin_store()
        standard = sorted((r for r in library.episodes if r.get('variant') == 'standard'), key=lambda r: r['name'])
        hd_records = [r for r in library.episodes if r.get('variant') == 'hd']
        new = {}

        # 1. Season bundles.
        seasons = {}
        for record in standard:
            bundle = bundle_for(library, record, hd_records)
            if bundle is not None:
                seasons.setdefault(bundle['id'], []).append(record)
        looks = {bundle_id: season_looks(library, records) for bundle_id, records in seasons.items()}
        for record in standard:
            bundle = next((b for b in hd_records if record in seasons.get(b['id'], ())), None)
            if bundle is None:
                continue
            try:
                matches, _, _ = pair_art_detailed(library.open_episode(record['id']), library.open_episode(bundle['id']))
            except Exception as error:
                print(f'skipped {record["name"]}: {error}')
                continue
            added = 0
            for match in matches:
                if match.kind == 'portrait' and len(looks[bundle['id']].get(match.std_name, ())) > 1:
                    continue                         # more than one look this season: the name is ambiguous
                key = fingerprint(match.std_bytes)
                if store.twin(match.std_bytes) is None and key not in new:
                    new[key] = (match.std_bytes, match.hd_bytes)
                    added += 1
            # The app's shared bank (ids below 26000): characters like Ben and Cameron are in Android's bank, which the HD
            # app bundle has no replacement for; the season bundle carries them as its own art.
            banked = bank_portraits(library, record, bundle, looks[bundle['id']], store, new)
            new.update(banked)
            added += len(banked)
            print(f'bundle  {record["name"][:42]:42} in {bundle["name"][:28]:28} {len(matches):4} paired, {added:3} new',
                  flush=True)

        # 2. Reused backgrounds.
        pool = {}
        for record in hd_records:
            resources = library.open_episode(record['id'])
            for resource_id in resources.archive.entries:
                if resource_id < LOCAL_ART:
                    continue
                data = resources.raw_asset(resource_id)
                key = fingerprint(data)
                if key in pool:
                    continue
                found = look(data)
                if found is not None and found[0] >= BG_HD:
                    pool[key] = (data, found[1])
        print(f'{len(pool)} HD backgrounds to compare against', flush=True)
        backgrounds = 0
        for record in standard:
            resources = library.open_episode(record['id'])
            for resource_id in resources.archive.entries:
                if resource_id < LOCAL_ART:
                    continue
                data = resources.raw_asset(resource_id)
                key = fingerprint(data)
                if key in new or store.twin(data) is not None:
                    continue
                found = look(data)
                if found is None or found[0] >= BG_HD:
                    continue
                vector = found[1]
                score, hd = max(((sum(a * b for a, b in zip(vector, other)), hd_data)
                                 for hd_data, other in pool.values()), default=(0.0, None), key=lambda p: p[0])
                if hd is not None and score >= SAME_PICTURE and is_upgraded(data, hd):
                    new[key] = (data, hd)
                    backgrounds += 1
        print(f'{backgrounds} reused backgrounds matched', flush=True)

        replace, remove = set(), set()
        if args.confirmed:
            # A hand-confirmed line overrides any automatic pair: a reused background the correlation got wrong (two
            # versions of one place, a sign's text the only difference) or a portrait that is not the same character.
            confirmed, unpaired = confirmed_pairs(library, args.confirmed, seasons)
            for key, pair in confirmed.items():
                if store.twin(pair[0]) != pair[1]:
                    new[key] = pair
                    replace.add(key)
            for key, standard in unpaired.items():
                new.pop(key, None)
                if store.twin(standard) is not None:
                    remove.add(key)
            print(f'{len(confirmed)} pictures paired and {len(unpaired)} unpaired by {args.confirmed} '
                  f'({len(replace)} replacing a pair, {len(remove)} removing one)', flush=True)
        if args.review:
            review(library, args.review, seasons, looks, store, new)

        if args.sheet:
            sheet(new, args.sheet)
        if args.dry_run:
            print(f'{len(new)} pictures would be added or replaced, {len(remove)} removed (dry run)')
        else:
            print(f'{store.add(new, replace, remove)} pictures added, replaced or removed in {store.directory}')


if __name__ == '__main__':
    main()
