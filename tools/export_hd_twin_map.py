"""Export a library's reviewed HD twin store as SHS's shipped twin map (packages/shs/src/exp_runtime/shs/hd_twin_map.py).

    python tools/export_hd_twin_map.py --library LIBRARY

The twin store (tools/write_hd_twins.py from the art audit's reviewed pairs; formerly build_hd_twins.py and
extend_hd_twins.py) can only be built where a library holds the standard *and* HD copies of the same stories, and it
holds extracted art, so it cannot ship. This writes what can: each standard picture's fingerprint and size, with its
HD twin's fingerprint and, for a picture the store keeps recreated (`hd_effects`), the effect; and, per standard
episode, the pictures its coverage counts (`build_hd_coverage.coverage_ids`, one playthrough walk each). The app
rebuilds the store from the player's own episodes (`hd_twins.build_from_map`) whenever the map's version changes. No
picture is written: fingerprints, sizes, effect names and resource ids only.

The library's own store is then marked as built from the new map (and its coverage cache counted), so the app does not
rebuild the owner's store from the map: a rebuild keeps only what that library's own files hold, and the next export
would lose the pairs that came from other libraries.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

from build_hd_coverage import coverage_ids
from exp_runtime.content import ContentLibrary, is_bundled
from exp_runtime.dsi import TRANSLATED_PACKS
from exp_runtime.episode_index import HD, STANDARD, duplicates
from exp_runtime.hd_twins import EFFECTS, INDEX, PACK, PORTRAITS, coverage_counts, fingerprint

OUTPUT = Path(__file__).resolve().parents[1] / 'packages/shs/src/exp_runtime/shs/hd_twin_map.py'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    with ContentLibrary(args.library) as library:
        library.hd_art_mode = 'off'                         # the episodes' own bytes, never a substituted picture
        store = library.twin_store()
        index = json.loads((store.directory / INDEX).read_text(encoding='utf-8'))
        pack = (store.directory / PACK).read_bytes()
        try:
            effects = json.loads((store.directory / EFFECTS).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            effects = {}
        try:
            portraits = json.loads((store.directory / PORTRAITS).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            portraits = {}
        twins = {}
        for standard, (offset, length, size, _hd_size) in sorted(index.items()):
            if standard in effects:
                hd, effect = effects[standard]
                twins[standard] = (hd, *size, tuple(effect))
            else:
                twins[standard] = (fingerprint(pack[offset:offset + length]), *size)
        records = library.episodes
        prefer = HD if library.hd_ipa is not None else STANDARD
        hidden = duplicates(records, prefer, bundled=is_bundled)
        # The original SHS episodes only: this fork's translated games (packs 31000 and up, `dsi.TRANSLATED_PACKS`)
        # draw their own add-ons' art and never have an HD twin.
        standard_records = sorted((r for r in records if r['id'] not in hidden and r.get('variant') == 'standard'
                                   and (r.get('pack_id') or 0) < TRANSLATED_PACKS), key=lambda r: r['name'])
        coverage, counts, started = {}, {}, time.time()
        for record in standard_records:
            try:
                resources = library.open_episode(record['id'])
                coverage[record['id']] = tuple(coverage_ids(resources))
                total, matched = coverage_counts(library, resources, coverage[record['id']])
                counts[record['id']] = {'total': total, 'matched': matched}
            except Exception as error:                  # one bad episode must not lose the rest
                print(f'skipped {record["name"]}: {error}')
                continue
            print(f'{record["name"][:44]:44} {len(coverage[record["id"]]):4} pictures, {counts[record["id"]]["matched"]:4} HD  '
                  f'({round(time.time() - started)} s)', flush=True)
        body = ''.join(f"    {key!r}: {value!r},\n" for key, value in twins.items())
        cover = ''.join(f"    {key!r}: {ids!r},\n" for key, ids in sorted(coverage.items()))
        sd_of = ''.join(f"    {key!r}: {tuple(value)!r},\n" for key, value in sorted(portraits.get('sd_of', {}).items()))
        episodes = ''.join(
            f"    {record!r}: {{{', '.join(f'{hd!r}: {tuple(entry)!r}' for hd, entry in sorted(table.items()))}}},\n"
            for record, table in sorted(portraits.get('sd_of_episode', {}).items()))
        redesigned = ''.join(f"    {key!r},\n" for key in sorted(portraits.get('redesigned', ())))
        bank = ', '.join(str(i) for i in sorted(portraits.get('bank_portraits', ())))
        portrait_text = (
            '# SD Portraits (Extras): the standard original each HD portrait goes back to, best first\n'
            f'SD_OF = {{\n{sd_of}}}\n\n'
            "# ...an HD episode's own original where its story's standard release shows another: (standard, strict), strict\n"
            '# when it is a different look (no fallback to SD_OF)\n'
            f'SD_OF_EPISODE = {{\n{episodes}}}\n\n'
            '# standard pictures whose pair is a redesign (Redesigns Only)\n'
            f'REDESIGNED = frozenset({{\n{redesigned}}})\n\n'
            "# shared-bank ids that are portraits (Everywhere draws Android's)\n"
            f'BANK_PORTRAITS = frozenset({{{bank}}})\n') if portraits else ''
        version = hashlib.sha1((body + cover + portrait_text).encode('ascii')).hexdigest()[:12]
        text = (f'"""SHS\'s HD twin map, shipped with the app: {len(twins)} standard pictures with their HD twins, and the\n'
                f'pictures {len(coverage)} standard episodes count for coverage. Generated by tools/export_hd_twin_map.py from the\n'
                "owner's reviewed library; do not edit by hand. Fingerprints (`hd_twins.fingerprint`), sizes, effect names\n"
                "(`hd_effects`) and resource ids only: the app finds every picture in the player's own episodes\n"
                '(`hd_twins.build_from_map`)."""\n\n'
                f'VERSION = {version!r}\n\n'
                '# standard picture fingerprint: (HD twin fingerprint, standard width, standard height[, effect])\n'
                f'TWINS = {{\n{body}}}\n\n'
                '# standard episode id (its sha256): the picture resource ids its coverage counts\n'
                f'COVERAGE = {{\n{cover}}}\n' + (f'\n{portrait_text}' if portrait_text else ''))
        args.output.write_bytes(text.encode('ascii'))
        store.write_coverage(counts)
        store.mark_source(version)
    full = sum(1 for c in counts.values() if c['total'] and c['matched'] == c['total'])
    mean = sum(c['matched'] / c['total'] for c in counts.values() if c['total']) / max(1, len(counts))
    print(f'{len(twins)} twins ({sum(1 for t in twins.values() if len(t) > 3)} with an effect), {len(coverage)} episodes, '
          f'version {version} -> {args.output}')
    print(f'coverage: {len(counts)} standard episodes, mean {100 * mean:.1f}%, {full} complete')


if __name__ == '__main__':
    main()
