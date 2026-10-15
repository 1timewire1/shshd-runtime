"""Export every standard/HD art pairing found in the library as a side-by-side comparison, for a human review pass.

For every story that has both releases, `hd_twins.pair_art_detailed` is run and every match is composited into one
PNG (the standard picture on the left, its HD twin on the right, both scaled to the same height) under `--out`:

    art-comp/
      confident/<serial>.png       -- matches an automated check trusts (see below)
      unsure/<serial>.png          -- a single-candidate match: worth a look
      unsure/<serial>/1.png, 2.png, ... -- a *conflicted* match (see below): every candidate HD picture, ranked
                                           most-sourced first, none of them singled out as "the" match
      unpaired-sd/<serial>.png     -- a standard picture the matched HD release never lined up with anything
      unpaired-hd/<serial>.png     -- the same, on the HD side
      confident_pairs.txt          -- "<serial> y [<standard id>]", one per confident match
      unsure_pairs.txt             -- "<serial> n [<standard id>]" per single-candidate match, or
                                       "<serial> n [<standard id>]" per conflict -- write the confirmed
                                       candidate back as "<serial> y <candidate number> [<standard id>]"
      manifest.json                -- every serial's full provenance (episodes, ids, kind, size), for re-import
      README.txt                   -- this scheme, written out

A serial, not a resource id, is the tracking key: the same picture is often reused across many episode files under
different local numbering (or the same numbering meaning unrelated art), so no single id names a pairing. The
optional trailing id on each line is the standard-side id the most common source story pair used -- present so a
correction can be written back in the same place, not because it is the only standard id that ever carries this
picture (`hd_twins.TwinStore` keys purely on picture content, not on id).

Confidence (a starting point, not a verdict): a background is confident when the two pictures correlate closely
(they are meant to be the exact same photo at 2x); a portrait is confident when at least one of its source story
pairs was matched by identical (pack, episode) ids *and* used the same numeric id on both sides, or when the two
releases' own script-set character names agree (`hd_twins.pair_art_detailed` only ever pairs a portrait this way,
never on a disagreeing name) -- still not proof, since a picture can be a genuine match that just looks wrong (an
extreme HD redraw, seen on 12_7_Howards_College_Tour's "Viv" and 12_3_Howards_Last_Day's "Vampire Players"), so a
"confident" match is still worth a glance. A name, shown on the pictures' own labels when either release's script
set one, is the strongest signal this tool has for a portrait -- stronger than a matching id, which can belong to
two different people between releases (found in 9_4_This_is_Spartan: HD folds one of three "Colt" ids away, shifting
every id from "Jeeves" on down by one). A picture whose content disagreed between two different story pairs (a
conflict) always lands in `unsure`, as a numbered folder of every candidate rather than one picked representative --
picking one and hiding the rest would just move the guess into the tool instead of removing it. `unpaired-sd` and
`unpaired-hd` are sorted by name first: a leftover on each side sharing a name is `pair_art_detailed`'s own best
lead on a pairing it could not make on its own (usually a differing expression count), worth a manual look.

An SD picture can be unpaired in the one story that shows it as itself, and still not be a real gap: `TwinStore`
keys purely on content, so a picture already matched *somewhere* in the library (reused, under a different
identity, by a different story -- e.g. 11_0_April_Fools' own "Monkey" costume shares its SD bytes with several
other episodes' "Amanda") already gets real HD art in play, just not from its own story's pairing. Those are
dropped from `unpaired-sd` rather than shown as a mystery a human has to notice is already resolved elsewhere.
`unpaired-hd` gets the same treatment for the mirror-image case: a small pool of stock pictures shared by more
than one named character (found in 7_8_Halloween_The_Second_Kiss's own "Zombie" family) can have one character's
own zip succeed at a given id while a sibling character's zip fails on that same id, leaving the exact same HD
picture looking unpaired even though it is already a real match.
"""
import argparse
import io
import json
import logging
from pathlib import Path

from PIL import Image, ImageDraw

from exp_runtime.content import ContentLibrary
from exp_runtime.episode_index import same_story
from exp_runtime.hd_twins import correlation, fingerprint, image_size, names_compatible, pair_art_detailed

TARGET_HEIGHT = 320
PAD, GUTTER, LABEL_H = 10, 6, 22
BACKDROP = (90, 105, 95)
CORRELATION_THRESHOLD = 0.9


def _scaled(data):
    image = Image.open(io.BytesIO(data)).convert('RGBA')
    scale = TARGET_HEIGHT / image.height
    return image.resize((max(1, round(image.width * scale)), TARGET_HEIGHT), Image.LANCZOS)


def _sheet(width):
    return Image.new('RGB', (width, PAD * 2 + TARGET_HEIGHT + LABEL_H), BACKDROP)


def composite(std_bytes, hd_bytes, std_label, hd_label):
    """The comparison PNG: the standard picture, a gutter, its HD twin, both scaled to TARGET_HEIGHT on a neutral
    backdrop (portraits carry alpha; a mid backdrop shows the cutout without biasing toward white or black)."""
    left, right = _scaled(std_bytes), _scaled(hd_bytes)
    sheet = _sheet(PAD * 2 + left.width + GUTTER + right.width)
    backdrop = Image.new('RGBA', sheet.size, (*BACKDROP, 255))
    backdrop.paste(left, (PAD, PAD), left)
    backdrop.paste(right, (PAD + left.width + GUTTER, PAD), right)
    sheet.paste(backdrop.convert('RGB'), (0, 0))
    draw = ImageDraw.Draw(sheet)
    draw.text((PAD, PAD + TARGET_HEIGHT + 4), std_label, fill=(235, 235, 235))
    draw.text((PAD + left.width + GUTTER, PAD + TARGET_HEIGHT + 4), hd_label, fill=(235, 235, 235))
    return sheet


def single(data, label):
    image = _scaled(data)
    sheet = _sheet(PAD * 2 + image.width)
    backdrop = Image.new('RGBA', sheet.size, (*BACKDROP, 255))
    backdrop.paste(image, (PAD, PAD), image)
    sheet.paste(backdrop.convert('RGB'), (0, 0))
    ImageDraw.Draw(sheet).text((PAD, PAD + TARGET_HEIGHT + 4), label, fill=(235, 235, 235))
    return sheet


def confidence(match, trusted):
    if match.kind == 'background':
        return correlation(match.std_bytes, match.hd_bytes) >= CORRELATION_THRESHOLD
    # A portrait: the same (pack, episode, id) triple on both sides, or -- just as strong a signal, and how a
    # gap like 9_4_This_is_Spartan's shifted ids gets a match at all -- the two releases' own script-set names
    # for the character agreeing (or one being a shorter title of the other's fuller name, e.g. "Coach" /
    # "Coach Kessler" -- see `names_compatible`). `pair_art_detailed` never returns a portrait match whose two
    # names outright disagree, so this is purely a promotion, not a check that could fail.
    return trusted or (match.std_name is not None and match.hd_name is not None
                       and names_compatible(match.std_name, match.hd_name))


def name_label(std_name, hd_name):
    if std_name is None and hd_name is None:
        return ''
    if std_name == hd_name:
        return f"  '{std_name}'"
    return f"  SD '{std_name}' / HD '{hd_name}'"          # only possible when one side never showed a name at all


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='the art-comp folder (its four subfolders must exist)')
    parser.add_argument('--only', nargs='*', help='only story pairs whose standard episode file name is one of these')
    args = parser.parse_args()

    for name in ('confident', 'unsure', 'unpaired-sd', 'unpaired-hd'):
        (args.out / name).mkdir(parents=True, exist_ok=True)

    with ContentLibrary(args.library) as library:
        library.hd_art_mode = 'off'
        records = library.episodes
        standard_records = [r for r in records if r.get('variant') == 'standard']
        hd_records = [r for r in records if r.get('variant') == 'hd']

        # picture content -> every distinct HD picture a story pair matched it to, and every (story, ids) that found
        # it -- collected across ALL story pairs before any file is written, so a picture two pairs disagree about
        # is caught as a conflict rather than silently overwritten by whichever pair happened to run last.
        by_std_fingerprint = {}   # std fingerprint -> {hd fingerprint: (match, [source dict, ...])}
        unpaired_std_by_fp, unpaired_hd_by_fp = {}, {}

        for record in sorted(standard_records, key=lambda r: r['name']):
            if args.only and record['name'] not in args.only:
                continue
            twins = [h for h in hd_records if same_story(record, h)]
            if not twins:
                continue
            hd_record = twins[0]
            try:
                standard = library.open_episode(record['id'])
                hd = library.open_episode(hd_record['id'])
                matches, unpaired_std, unpaired_hd = pair_art_detailed(standard, hd)
            except Exception as error:
                logging.warning('skipped %s: %s', record['name'], error)
                continue
            exact_story = (record['pack_id'], record['episode_id']) == (hd_record['pack_id'], hd_record['episode_id'])
            for match in matches:
                std_fp, hd_fp = fingerprint(match.std_bytes), fingerprint(match.hd_bytes)
                variants = by_std_fingerprint.setdefault(std_fp, {})
                _, sources = variants.setdefault(hd_fp, (match, []))
                sources.append(dict(std_episode=record['name'], std_id=match.std_id, hd_episode=hd_record['name'],
                                    hd_id=match.hd_id, exact=(match.std_id == match.hd_id and exact_story),
                                    std_name=match.std_name, hd_name=match.hd_name))
            for item in unpaired_std:
                unpaired_std_by_fp.setdefault(fingerprint(item.data), (item, record['name']))
            for item in unpaired_hd:
                unpaired_hd_by_fp.setdefault(fingerprint(item.data), (item, hd_record['name']))
            print(f'{record["name"][:44]:44} matches {len(matches):4}  unpaired std {len(unpaired_std):3}  unpaired hd {len(unpaired_hd):3}', flush=True)

        # A standard picture unpaired in its own story is not a real gap if the exact same content is matched
        # somewhere else in the library: `TwinStore` keys purely on content, so it already gets real HD art in
        # play from whichever story's pairing won (`hd_twins.best_by_source_count`'s own selection). Reporting it
        # as unpaired here would send a human looking for a fix that already exists.
        resolved = [fp for fp in unpaired_std_by_fp if fp in by_std_fingerprint]
        for fp in resolved:
            del unpaired_std_by_fp[fp]
        if resolved:
            print(f'{len(resolved)} standard picture(s) unpaired in their own story already matched elsewhere in the library')

        # The same blind spot exists on the HD side, from an id pool shared by more than one named character (a
        # small set of stock pictures rotated across several costumes, found in 7_8_Halloween_The_Second_Kiss's own
        # "Zombie"/"Zombie Linda"/"Zombie Zach"): one character's own zip can succeed at a given id while a
        # sibling character's zip, landing on the same id by way of the shared pool, fails -- the exact same HD
        # picture then shows up as both a real match and (from the failed attempt) "unpaired".
        resolved_hd_fps = {hd_fp for variants in by_std_fingerprint.values() for hd_fp in variants}
        resolved_hd = [fp for fp in unpaired_hd_by_fp if fp in resolved_hd_fps]
        for fp in resolved_hd:
            del unpaired_hd_by_fp[fp]
        if resolved_hd:
            print(f'{len(resolved_hd)} HD picture(s) unpaired in their own story already matched elsewhere in the library')

        manifest = {'confident': {}, 'unsure': {}, 'unpaired_std': {}, 'unpaired_hd': {}}
        confident_lines, unsure_lines = [], []
        for serial, std_fp in enumerate(sorted(by_std_fingerprint), start=1):
            variants = by_std_fingerprint[std_fp]
            # The variant with the most sources wins the representative image; anything else found for this exact
            # standard picture is a conflict, noted rather than silently dropped.
            ranked = sorted(variants.items(), key=lambda kv: -len(kv[1][1]))
            best_hd_fp, (best_match, best_sources) = ranked[0]
            conflict = len(ranked) > 1
            trusted = any(source['exact'] for source in best_sources)
            key = f'{serial:04d}'
            bucket = 'confident' if not conflict and confidence(best_match, trusted) else 'unsure'
            std_label = (f"SD {best_sources[0]['std_episode'][:28]} #{best_match.std_id}  {image_size(best_match.std_bytes)}"
                        + (f"  '{best_match.std_name}'" if best_match.std_name else ''))
            if bucket == 'unsure' and conflict:
                # Every candidate gets its own numbered picture -- picking a "most common" one to show and burying
                # the rest in a footnote just relocates the guess, which is exactly what this folder is for resolving.
                folder = args.out / 'unsure' / key
                folder.mkdir(parents=True, exist_ok=True)
                candidates = []
                for number, (_, (match, sources)) in enumerate(ranked, start=1):
                    hd_label = (f"HD {sources[0]['hd_episode'][:24]} #{match.hd_id}  {image_size(match.hd_bytes)}"
                               f"  ({len(sources)} source(s)){name_label(match.std_name, match.hd_name)}")
                    composite(match.std_bytes, match.hd_bytes, std_label, hd_label).save(folder / f'{number}.png')
                    candidates.append(dict(number=number, hd_episode=sources[0]['hd_episode'], hd_id=match.hd_id,
                                           kind=match.kind, character=match.character, hd_name=match.hd_name,
                                           sources=sources))
                manifest[bucket][key] = dict(kind=best_match.kind, character=best_match.character, conflict=True,
                                             std_name=best_match.std_name, candidates=candidates)
                unsure_lines.append(f"{key} n {best_match.std_id}")
            else:
                hd_label = (f"HD {best_sources[0]['hd_episode'][:28]} #{best_match.hd_id}  {image_size(best_match.hd_bytes)}"
                           f"{name_label(best_match.std_name, best_match.hd_name)}")
                composite(best_match.std_bytes, best_match.hd_bytes, std_label, hd_label).save(args.out / bucket / f'{key}.png')
                manifest[bucket][key] = dict(kind=best_match.kind, character=best_match.character,
                                             std_name=best_match.std_name, hd_name=best_match.hd_name, sources=best_sources)
                (confident_lines if bucket == 'confident' else unsure_lines).append(
                    f"{key} {'y' if bucket == 'confident' else 'n'} {best_match.std_id}")

        for prefix, table, manifest_key in (('S', unpaired_std_by_fp, 'unpaired_std'), ('H', unpaired_hd_by_fp, 'unpaired_hd')):
            folder = 'unpaired-sd' if prefix == 'S' else 'unpaired-hd'
            # Sorted by name first, not by fingerprint hash, so an SD leftover and an HD leftover that share a
            # character name -- the two folders' best hint at a recoverable pairing `pair_art_detailed` itself
            # could not make (e.g. a name whose expression counts differ between releases) -- land at the same
            # rank in both folders instead of being scattered.
            by_name = sorted(table, key=lambda fp: (table[fp][0].name or '￿', table[fp][1], table[fp][0].id))
            for n, fp in enumerate(by_name, start=1):
                item, episode_name = table[fp]
                key = f'{prefix}{n:04d}'
                label = (f"{episode_name[:28]} #{item.id}  {image_size(item.data)}  {item.kind}"
                        + (f"  '{item.name}'" if item.name else ''))
                single(item.data, label).save(args.out / folder / f'{key}.png')
                manifest[manifest_key][key] = dict(episode=episode_name, id=item.id, kind=item.kind,
                                                   character=item.character, name=item.name)

        (args.out / 'confident_pairs.txt').write_text('\n'.join(confident_lines) + '\n', encoding='utf-8')
        (args.out / 'unsure_pairs.txt').write_text('\n'.join(unsure_lines) + '\n', encoding='utf-8')
        (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
        (args.out / 'README.txt').write_text(__doc__, encoding='utf-8')

        print(f'\n{len(confident_lines)} confident, {len(unsure_lines)} unsure, '
              f'{len(manifest["unpaired_std"])} unpaired standard, {len(manifest["unpaired_hd"])} unpaired HD')


if __name__ == '__main__':
    main()
