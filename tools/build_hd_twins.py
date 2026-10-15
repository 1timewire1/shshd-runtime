"""Build a library's HD twin store: the HD release's version of the art standard episodes share with it (prototype)."""
import argparse
from pathlib import Path
import time

from exp_runtime.content import ContentLibrary
from exp_runtime.episode_index import same_story
from exp_runtime.hd_twins import best_by_source_count, pair_art_detailed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--limit', type=int, help='stop after this many story pairs (a quick try)')
    parser.add_argument('--only', nargs='*', help='only pairs whose standard episode file name is one of these')
    args = parser.parse_args()
    with ContentLibrary(args.library) as library:
        library.hd_art_mode = 'off'             # the store is built from the episodes' own bytes
        records = library.episodes
        standard = [r for r in records if r.get('variant') == 'standard']
        hd = [r for r in records if r.get('variant') == 'hd']
        all_matches, pairs, started = [], 0, time.time()
        for record in sorted(standard, key=lambda r: r['name']):
            if args.only and record['name'] not in args.only:
                continue
            twins = [h for h in hd if same_story(record, h)]
            if not twins:
                continue
            if args.limit and pairs >= args.limit:
                break
            try:
                matches, _, _ = pair_art_detailed(library.open_episode(record['id']), library.open_episode(twins[0]['id']))
            except Exception as error:                      # one bad pair must not lose the rest
                print(f'skipped {record["name"]}: {error}')
                continue
            pairs += 1
            all_matches.extend(matches)
            print(f'{record["name"][:44]:44} {len(matches):4} pictures  ({round(time.time() - started)} s)', flush=True)
        # Ranked once, across the whole library, rather than kept per pair: an SD picture reused under a different
        # identity by more than one story (see `best_by_source_count`) needs every story's own match in hand
        # before the right HD twin for it can be picked, not just whichever story happened to build first.
        entries = best_by_source_count(all_matches)
        store = library.twin_store()
        store.write(entries)
        size = sum(len(hd_bytes) for _, hd_bytes in entries.values())
        print(f'{pairs} pairs, {len(entries)} twins, {round(size / 1e6, 1)} MB in {store.directory}')


if __name__ == '__main__':
    main()
