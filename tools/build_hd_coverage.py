"""Build a library's HD art coverage cache: how much of each standard episode's own art has an HD twin
(hd_twins.py), so the picker can tell one that already plays entirely in HD (once hd_art is on) apart from one
that still shows real SD-only pictures. Prototype, like hd_twins.py itself.

A "total" here is only what one deterministic `collect_art()` sample walk found, the same walk `hd_twins`'s own
pairing already relies on and carries the same limit: a branch the walk never reaches cannot be counted, so a
reported 100% is "100% of what was found," not a guarantee against an unexplored branch holding one more SD-only
picture. Rerun after rebuilding the twin store (`build_hd_twins.py`) or importing new episodes.
"""
import argparse
from pathlib import Path
import time

from export_art_catalog import picture             # this folder's own catalogue tool
from exp_runtime.content import ContentLibrary, is_bundled
from exp_runtime.episode_index import HD, STANDARD, duplicates
from exp_runtime.hd_twins import LOCAL_ART, collect_art, image_size, is_hd_size


def episode_coverage(library, record):
    """(total, matched) pictures the episode registers while played through: matched when the HD app bundle replaces a
    shared-bank picture (ids below 26000) by id, or when the twin store holds the picture.

    A portrait's expression slots past the first count only when they hold a portrait: `SHSEntityTable::setPortrait`
    fills a missing expression with whatever resource follows the character's art in the file (2_8's Zach: three
    backgrounds), which the script never shows (tools/export_art_catalog.py, `portrait_slot`)."""
    resources = library.open_episode(record['id'])
    variants, backgrounds, _ = collect_art(resources)
    ids = set(backgrounds)
    for portraits in variants.values():
        for slot, resource_id in enumerate(portraits):
            if slot == 0 or resource_id != portraits[0] and masked(resources, resource_id):
                ids.add(resource_id)
    store = library.twin_store()
    total = matched = 0
    for resource_id in ids:
        if resource_id < 0 or not resources.exists(resource_id):
            continue
        total += 1
        # A shared-bank picture is HD when the HD app bundle replaces it by id, else (like the episode's own art) when
        # the twin store has it: `EpisodeResources.read_asset` puts a standard episode's bank pictures through the store.
        if resource_id < LOCAL_ART and library.hd_asset(resource_id) is not None:
            matched += 1
        elif store.twin(resources.raw_asset(resource_id)) is not None:
            matched += 1
        elif is_hd_size(image_size(resources.raw_asset(resource_id))):
            matched += 1                    # already HD in the standard file (Set_12's pool)
    return total, matched


def masked(resources, resource_id):
    """Whether a picture has fully transparent pixels (a masked portrait; a background has none)."""
    try:
        image = picture(resources.raw_asset(resource_id))   # RGBA, however the asset is stored
    except Exception:
        return False
    return image is not None and image.getextrema()[3][0] == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--only', nargs='*', help='only episode file names to (re)measure')
    args = parser.parse_args()
    with ContentLibrary(args.library) as library:
        library.hd_art_mode = 'off'   # measure the episode's own bytes, never an already-substituted picture
        all_records = library.episodes
        # The same population the picker itself shows (episode_picker.PickerModel): a standard release hidden
        # behind its own HD twin never gets a tile at all, so measuring its coverage would be wasted walking.
        prefer = HD if library.hd_ipa is not None else STANDARD
        hidden = duplicates(all_records, prefer, bundled=is_bundled)
        records = [r for r in all_records if r['id'] not in hidden and r.get('variant') == 'standard']
        coverage, started = {}, time.time()
        for record in sorted(records, key=lambda r: r['name']):
            if args.only and record['name'] not in args.only:
                continue
            try:
                total, matched = episode_coverage(library, record)
            except Exception as error:                      # one bad episode must not lose the rest
                print(f'skipped {record["name"]}: {error}')
                continue
            coverage[record['id']] = {'total': total, 'matched': matched}
            pct = 100 * matched / total if total else 100
            print(f'{record["name"][:44]:44} {matched:4}/{total:<4} ({pct:5.1f}%)  ({round(time.time() - started)} s)',
                  flush=True)
        store = library.twin_store()
        if args.only:                       # a partial run updates those episodes and keeps everyone else's
            store.coverage('')              # loads the cache
            coverage = {**(store._coverage or {}), **coverage}
        store.write_coverage(coverage)
        full = sum(1 for c in coverage.values() if c['total'] and c['matched'] == c['total'])
        print(f'{len(coverage)} standard episodes measured, {full} fully covered, in {store.directory}')


if __name__ == '__main__':
    main()
