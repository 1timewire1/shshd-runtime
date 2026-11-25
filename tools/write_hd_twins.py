"""Write a library's HD twin store from a reviewed list of pairs (the 2026-11 art audit's `audit_pairs.json`).

    python tools/write_hd_twins.py --library LIBRARY --pairs PAIRS.json [--source OTHER_LIBRARY ...] [--dry-run]

PAIRS.json holds {"pairs": [{"sd": fingerprint, "hd": fingerprint, "size": [w, h], "effect": null | [kind, ...]}]}
and SD Portraits' tables (`sd_of`, `sd_of_episode`, `redesigned`, `bank_portraits`; `hd_twins.SdPortraits`):
fingerprints, record ids and resource ids only (`hd_twins.fingerprint`), kept outside the project with the art catalogue. Each picture is found in
the libraries' own episodes (LIBRARY first, then each --source: the owner's library lacks the standard copies of most
stories that have an HD release, which a reference library holds). A pair with an effect stores the HD picture
recreated to match the standard one (`hd_effects`), and the store's `effects.json` keeps its HD fingerprint and
effect for tools/export_hd_twin_map.py. The store is replaced as a whole; its coverage cache is kept. A pair whose
pictures no library holds is reported and left out.

Then run tools/export_hd_twin_map.py --library LIBRARY to ship the result.
"""
import argparse
import json
from pathlib import Path

from exp_runtime.content import ContentLibrary
from exp_runtime.hd_effects import apply as apply_effect
from exp_runtime.hd_twins import EFFECTS, PORTRAITS, fingerprint


def find(libraries, wanted):
    """{fingerprint: bytes} for the `wanted` fingerprints, from the libraries' episodes (HD episodes first)."""
    found = {}
    for library in libraries:
        for record in sorted(library.episodes, key=lambda r: r.get('variant') != 'hd'):
            if len(found) == len(wanted):
                return found
            try:
                archive = library.open_episode(record['id']).archive
            except Exception as error:                  # one unreadable episode must not stop the rest
                print(f'skipped {record.get("name")}: {error}')
                continue
            for resource_id in archive.entries:
                try:
                    data = archive.read(resource_id)
                except Exception:
                    continue
                key = fingerprint(data)
                if key in wanted and key not in found:
                    found[key] = data
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--pairs', type=Path, required=True)
    parser.add_argument('--source', type=Path, action='append', default=[])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    document = json.loads(args.pairs.read_text(encoding='utf-8'))
    pairs = document['pairs']
    with ContentLibrary(args.library) as library:
        library.hd_art_mode = 'off'
        sources = [ContentLibrary(path) for path in args.source]
        for source in sources:
            source.hd_art_mode = 'off'
        wanted = {pair['hd'] for pair in pairs} | {pair['sd'] for pair in pairs if pair.get('effect')}
        found = find([library, *sources], wanted)
        pictures, effects, missing = {}, {}, []
        for pair in pairs:
            hd, effect = found.get(pair['hd']), pair.get('effect')
            if hd is None or (effect and pair['sd'] not in found):
                missing.append(pair)
                continue
            data = apply_effect(found[pair['sd']], hd, tuple(effect)) if effect else hd
            pictures[pair['sd']] = (tuple(pair['size']), data)
            if effect:
                effects[pair['sd']] = [pair['hd'], list(effect)]
        print(f'{len(pictures)} pairs found ({len(effects)} with an effect), {len(missing)} missing')
        for pair in missing:
            print('  missing:', pair['sd'], '->', pair['hd'], pair.get('effect') or '')
        if args.dry_run:
            return
        store = library.twin_store()
        store.clear()
        store.add_pictures(pictures)
        (store.directory / EFFECTS).write_text(json.dumps(effects, separators=(',', ':')), encoding='utf-8')
        # SD Portraits' tables, for the export: which original each HD portrait goes back to, the redesigns and the
        # shared bank's portrait ids (`hd_twins.SdPortraits`).
        tables = {key: document.get(key, {} if key.startswith('sd_of') else [])
                  for key in ('sd_of', 'sd_of_episode', 'redesigned', 'bank_portraits')}
        (store.directory / PORTRAITS).write_text(json.dumps(tables, separators=(',', ':')), encoding='utf-8')
        print(f'{len(store)} pictures in {store.directory}')
        for source in sources:
            source.close()


if __name__ == '__main__':
    main()
