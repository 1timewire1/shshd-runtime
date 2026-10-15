"""Catalogue every character portrait and background in a library as Markdown documents with full-resolution exports.

    python tools/export_art_catalog.py LIBRARY OUT [--only portraits|backgrounds]

Every episode is opened and its scripts walked briefly (`tree_explorer`): each episode registers its whole cast at
its first step (`set_character_art_base`, five expression slots from a base id, and `set_character_name`), and the
walk also catches later renames and costume swaps. Every registered slot's picture is collected, deduplicated by its
bytes, with every (episode, resource id, character, slot, name) that uses it. A picture's own size decides its side:
HD portraits are 256 px wide and the standard release's 128 (`episode_index.image_variant`), so an HD-format episode
filed as standard (`The_New_Girl.exp`) lands with the HD art; the narrower HD redraws (148-199 wide) are 256 tall, which
no standard portrait is (HD_HEIGHT). The app's shared bank (ids below 26000) is listed from
both sides: Android's picture as standard, the HD app bundle's replacement (`ContentLibrary.hd_asset`) as HD.

Written under OUT (outside the project: these are the player's own pictures):
    hd_portraits.md                 every HD portrait, by name, marked when a standard picture already resolves to it
    sd_portraits_without_hd.md      every standard portrait that resolves to no HD picture, with same-name HD leads
    hd/<serial>.png, sd/<serial>.png    the pictures, full resolution with their transparency
    sd_hd_matches.md                every HD picture beside the standard ones that resolve to it (portraits, then
                                    backgrounds), for checking the pairs by eye
Pictures that look like portraits (a registered portrait's exact size, with transparency) but no walked character
registers are listed at the end of each document without names.

Backgrounds need no walk: every opaque, screen-sized local picture of every episode file is listed
(hd_backgrounds.md, sd_backgrounds_without_hd.md, bg-hd/, bg-sd/), linked through the twin store, with leads for the
unmatched standard ones (the same id in the same story's HD release, and the best-correlating unlinked HD picture).
"""
import argparse
import io
import logging
import time
from collections import defaultdict
from pathlib import Path

from PIL import Image

from exp_runtime.cgbi import CgBIError, decode
from exp_runtime.content import ContentLibrary
from exp_runtime.hd_twins import LOCAL_ART, fingerprint
from exp_runtime.ui_assets import ImagePack

HD_WIDTH = 200          # 256-px HD portraits against 128-px standard ones
# Some HD redraws are narrower (148 to 199 wide) but always 256 tall; no standard portrait is over 150 tall (owner's
# review, 2026-10-13: 109 such pictures had been listed as standard).
HD_HEIGHT = 256


def picture(data):
    """The asset as an RGBA PIL image, or None."""
    try:
        if data[:2] == b'\xff\xd8':             # JPEG (most backgrounds): not a PNG for cgbi.decode
            image = Image.open(io.BytesIO(data))
            image.load()
        elif data[:4] == b'\x89PNG':
            image = decode(data)
        else:
            frame = ImagePack.parse(data).images[0]
            image = Image.frombytes(frame.mode, (frame.width, frame.height), frame.pixels)
        return image.convert('RGBA')
    except (CgBIError, ValueError, OSError, IndexError):
        return None


def portrait_slot(image, slot):
    """Whether a registered expression slot holds a portrait. `SHSEntityTable::setPortrait` (00038380) fills slot n with
    base + n whenever that resource exists, else the base, so a character with fewer than five expressions can have
    slots pointing at whatever follows its art in the file (2_8_The_Halloween_Dance_Part_2's Zach: 26181, then three
    backgrounds), which the script never asks for. A portrait is masked and always has fully transparent pixels; a
    background has none. The base slot is always kept."""
    return slot == 0 or image.getextrema()[3][0] == 0


class Entry:
    def __init__(self, data, image):
        self.data, self.image = data, image
        self.uses = []          # (episode, resource id, character, slot, names)
        self.names = set()
        self.serial = None

    @property
    def hd(self):
        return self.image.width >= HD_WIDTH or self.image.height >= HD_HEIGHT


def walk(library, record, steps, seconds):
    """({character: {'names': set, 'ids': set of (slot, id)}}), from the episode's first step and a short walk."""
    from exp_runtime.runtime import Session
    from exp_runtime.tree_explorer import Explorer, Playthrough
    resources = library.open_episode(record['id'])
    session = Session(resources, ephemeral=True)
    session.advance()
    explorer, playthrough = Explorer(resources, ephemeral=True), Playthrough(1)
    cast = defaultdict(lambda: {'names': set(), 'ids': set()})
    started = time.time()
    for _ in range(steps):
        engine = session.engine
        for character, ids in engine.character_art_variants.items():
            cast[character]['ids'].update(enumerate(ids))
        for character, name in engine.character_names.items():
            if name and name.strip():
                cast[character]['names'].add(name.strip())
        if (time.time() - started > seconds or session.pending is None
                or session.pending.name in ('finished', 'episode_exit')):
            break
        try:
            explorer.act(session, playthrough)
        except Exception:               # an unsupported screen ends the walk, not the catalogue
            break
    return resources, cast


def collect(library, steps, seconds):
    entries = {}                        # fingerprint -> Entry
    unregistered = {}                   # fingerprint -> Entry, portrait-like pictures nobody registers
    shapes = set()
    local_seen = defaultdict(set)       # record id -> registered local ids
    base_ids = defaultdict(lambda: {'names': set(), 'uses': []})

    def add(data, use, names):
        key = fingerprint(data)
        entry = entries.get(key)
        if entry is None:
            image = picture(data)
            if image is None or not portrait_slot(image, use[3]):
                return None
            entry = entries[key] = Entry(data, image)
        elif not portrait_slot(entry.image, use[3]):
            return None
        entry.uses.append(use)
        entry.names.update(names)
        return entry

    opened = []
    for number, record in enumerate(library.episodes, 1):
        try:
            resources, cast = walk(library, record, steps, seconds)
        except Exception as error:
            logging.warning('%s: not walked (%s)', record['name'], error)
            continue
        opened.append((record, resources))
        for character, info in cast.items():
            for slot, resource_id in sorted(info['ids']):
                if resource_id is None or resource_id < 0:
                    continue
                use = (record['name'], resource_id, character, slot)
                if resource_id >= LOCAL_ART:
                    try:
                        data = resources.raw_asset(resource_id)
                    except Exception:
                        continue
                    entry = add(data, use, info['names'])
                    if entry is not None:
                        shapes.add(entry.image.size)
                        local_seen[record['id']].add(resource_id)
                else:
                    base_ids[resource_id]['names'].update(info['names'])
                    base_ids[resource_id]['uses'].append(use)
        if number % 20 == 0:
            logging.info('%d / %d episodes', number, len(library.episodes))
    # The shared bank: Android's picture (standard) and the HD bundle's replacement (HD), linked by id.
    base_links = {}
    for resource_id, info in base_ids.items():
        try:
            android = library.android_asset(resource_id)
        except Exception:
            android = None
        hd = library.hd_asset(resource_id)
        sd_entry = hd_entry = None
        for data in (android, hd):
            if data is None:
                continue
            entry = entries.get(fingerprint(data))
            if entry is None:
                image = picture(data)
                if image is None or not portrait_slot(image, min(s for *_, s in info['uses'])):
                    continue
                entry = entries[fingerprint(data)] = Entry(data, image)
            entry.names.update(info['names'])
            entry.uses.extend(('app bundle' if data is hd else 'Android bank', resource_id, c, s)
                              for _, _, c, s in info['uses'][:1])
            if data is hd:
                hd_entry = entry
            else:
                sd_entry = entry
        if sd_entry is not None and hd_entry is not None:
            base_links[fingerprint(sd_entry.data)] = fingerprint(hd_entry.data)
    # Portrait-shaped local pictures no walked character registers.
    for record, resources in opened:
        for resource_id in resources.archive.entries:
            if resource_id < LOCAL_ART or resource_id in local_seen[record['id']]:
                continue
            try:
                data = resources.raw_asset(resource_id)
            except Exception:
                continue
            key = fingerprint(data)
            if key in entries:
                continue
            target = unregistered.get(key)
            if target is None:
                image = picture(data)
                if image is None or image.size not in shapes or image.getextrema()[3][0] == 255:
                    continue
                target = unregistered[key] = Entry(data, image)
            target.uses.append((record['name'], resource_id, None, None))
    return entries, unregistered, base_links


def links(library, entries, base_links):
    """(sd fingerprint -> hd fingerprint) for every standard picture that already resolves to an HD one."""
    store = library.twin_store()
    resolved = dict(base_links)
    for key, entry in entries.items():
        if entry.hd or key in resolved:
            continue
        twin = store.twin(entry.data)
        if twin is not None:
            resolved[key] = fingerprint(twin)
    return resolved


def clear(folder):
    """An export folder of this tool's own numbered pictures, emptied for a new run."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob('[0-9][0-9][0-9][0-9].png'):
        old.unlink()


def label(entry):
    return ', '.join(sorted(entry.names)) if entry.names else '(no name)'


def sources(entry, limit=6):
    rows = sorted({(episode, resource_id) for episode, resource_id, *_ in entry.uses})
    text = '; '.join(f'{episode.removesuffix(".exp")} #{resource_id}' for episode, resource_id in rows[:limit])
    return text + (f'; +{len(rows) - limit} more' if len(rows) > limit else '')


def expressions(entry):
    slots = sorted({slot for *_, slot in entry.uses if slot is not None})
    return ', '.join(str(slot) for slot in slots) if slots else '-'


def order(entry):
    """A character's expressions together: by name, then the first episode and resource id that show the picture."""
    first = min((episode, resource_id) for episode, resource_id, *_ in entry.uses)
    return label(entry).lower(), first


def thumb(folder, entry):
    return f'<img src="{folder}/{entry.serial}.png" width="72">'


def write(out, entries, unregistered, resolved, base_links=()):
    out.mkdir(parents=True, exist_ok=True)
    hd = sorted((e for e in entries.values() if e.hd), key=order)
    sd = sorted((e for e in entries.values() if not e.hd), key=order)
    extra_hd = sorted((e for e in unregistered.values() if e.hd), key=sources)
    extra_sd = sorted((e for e in unregistered.values() if not e.hd), key=sources)
    for folder, group in (('hd', hd + extra_hd), ('sd', sd + extra_sd)):
        clear(out / folder)
        for number, entry in enumerate(group, 1):
            entry.serial = f'{number:04d}'
            entry.image.save(out / folder / f'{entry.serial}.png')
    by_key = {fingerprint(e.data): e for e in [*entries.values(), *unregistered.values()]}
    linked_from = defaultdict(list)
    for sd_key, hd_key in resolved.items():
        linked_from[hd_key].append(by_key[sd_key] if sd_key in by_key else None)
    unresolved = [e for e in sd if fingerprint(e.data) not in resolved]
    hd_by_name = defaultdict(list)
    for entry in hd:
        for name in entry.names:
            hd_by_name[name.lower()].append(entry)

    lines = ['# HD portraits', '',
             f'{len(hd)} HD portraits (pictures 200 px wide or 256 tall) registered by the library\'s episodes or replaced in the '
             'app bundle, each once however many episodes and characters reuse it. "Linked" means at least one standard '
             'picture already resolves to it in play (the twin store, or the bundle replacing an Android bank picture by id); '
             f'{sum(1 for e in hd if linked_from.get(fingerprint(e.data)))} are linked, '
             f'{sum(1 for e in hd if not linked_from.get(fingerprint(e.data)))} are not.', '',
             "Names starting with `$` are the player-chosen names of a playable lead (`$USR` is the player, `$ZOE`, `$CADY`, `$ALLISON`... a series' own protagonist); a picture used by several characters lists every name it appears under.", '',
             '| Picture | # | Name(s) | Expr. | Size | Linked | Used in (episode #resource) |', '|---|---|---|---|---|---|---|']
    for entry in hd:
        found = linked_from.get(fingerprint(entry.data), [])
        mark = f'yes ({", ".join("sd " + e.serial for e in found if e)})' if found else 'no'
        lines.append(f'| {thumb("hd", entry)} | {entry.serial} | {label(entry)} | {expressions(entry)} | {entry.image.width}x{entry.image.height} '
                     f'| {mark} | {sources(entry)} |')
    if extra_hd:
        lines += ['', '## Portrait-shaped HD pictures no walked character registers', '',
                  '| Picture | # | Size | In |', '|---|---|---|---|']
        lines += [f'| {thumb("hd", e)} | {e.serial} | {e.image.width}x{e.image.height} | {sources(e)} |' for e in extra_hd]
    (out / 'hd_portraits.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    lines = ['# Standard portraits with no HD counterpart', '',
             f'{len(unresolved)} of {len(sd)} standard portraits (under 200 px wide and 256 tall) resolve to no HD picture in play. '
             '"Same-name HD" lists HD portraits registered under one of the same names: the first place to look for a '
             'counterpart (a name can still be shared by different people).', '',
             "Names starting with `$` are the player-chosen names of a playable lead (`$USR` is the player, `$ZOE`, `$CADY`, `$ALLISON`... a series' own protagonist); a picture used by several characters lists every name it appears under.", '',
             '| Picture | # | Name(s) | Expr. | Size | Same-name HD | Used in (episode #resource) |', '|---|---|---|---|---|---|---|']
    for entry in unresolved:
        leads = sorted({e.serial for name in entry.names for e in hd_by_name.get(name.lower(), [])})
        lead = ', '.join(f'hd {serial}' for serial in leads[:8]) + (' ...' if len(leads) > 8 else '') if leads else '-'
        lines.append(f'| {thumb("sd", entry)} | {entry.serial} | {label(entry)} | {expressions(entry)} | {entry.image.width}x{entry.image.height} '
                     f'| {lead} | {sources(entry)} |')
    if extra_sd:
        lines += ['', '## Portrait-shaped standard pictures no walked character registers', '',
                  '| Picture | # | Size | Resolves to HD | In |', '|---|---|---|---|---|']
        lines += [f'| {thumb("sd", e)} | {e.serial} | {e.image.width}x{e.image.height} | '
                  f'{"yes" if fingerprint(e.data) in resolved else "no"} | {sources(e)} |' for e in extra_sd]
    (out / 'sd_portraits_without_hd.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    # The comparison section: every HD picture a standard one resolves to, beside all of them.
    by_serial = {e.serial: e for e in hd + extra_hd}
    bank = set(base_links)            # resolved by the HD app bundle's own id replacement
    rows = []
    for entry in sorted(hd + extra_hd, key=lambda e: e.serial):
        found = [e for e in linked_from.get(fingerprint(entry.data), []) if e is not None]
        if not found:
            continue
        found.sort(key=lambda e: e.serial)
        tag = ' (app bundle)' if all(fingerprint(e.data) in bank for e in found) else ''
        rows.append(f'| {" ".join(thumb("sd", e) for e in found)} | {", ".join(e.serial for e in found)} '
                    f'| {entry.serial}{tag} | {thumb("hd", entry)} |')
    write_matches(out, 'portraits', rows)
    return len(hd), len(sd), len(unresolved), len(extra_hd), len(extra_sd)


MATCH_SECTIONS = {
    'portraits': ('## Portraits', '| SD picture(s) | SD # | HD # | HD picture |'),
    'backgrounds': ('## Backgrounds', '| SD picture(s) | SD # | HD # | HD picture |'),
}


def write_matches(out, section, rows):
    """sd_hd_matches.md: each HD picture beside every standard picture that resolves to it in play, portraits then
    backgrounds, for checking the pairs by eye. One section is rewritten at a time (the other kept from the last run),
    since `--only` exports one kind."""
    path = out / 'sd_hd_matches.md'
    sections = {}
    if path.exists():
        current, buffer = None, []
        for line in path.read_text(encoding='utf-8').splitlines():
            heading = next((k for k, (title, _) in MATCH_SECTIONS.items() if line == title), None)
            if heading is not None:
                if current:
                    sections[current] = buffer
                current, buffer = heading, []
            elif current:
                buffer.append(line)
        if current:
            sections[current] = buffer
    title, header = MATCH_SECTIONS[section]
    folders = 'sd/, hd/' if section == 'portraits' else 'bg-sd/, bg-hd/'
    sections[section] = ['', f'{len(rows)} HD pictures with the standard ones that resolve to them (numbers are this '
                         f'catalogue\'s, pictures in {folders}). "(app bundle)": the HD app replaces the shared-bank picture '
                         'by its id, natively; every other row is this player\'s twin store.', '', header,
                         '|---|---|---|---|', *rows, '']
    lines = ['# SD and HD matches', '',
             'Every standard picture that plays as an HD one, beside it: a last check by eye for a wrong pair.']
    for key, (heading, _) in MATCH_SECTIONS.items():
        if key in sections:
            lines += ['', heading, *sections[key]]
    path.write_text('\n'.join(lines).rstrip('\n') + '\n', encoding='utf-8')


# ------------------------------------------------------------------------------------------------------------- backgrounds

BG_MIN, BG_HD_WIDTH = 300, 700      # standard backgrounds are 400 / 480 wide (some 320), HD ones 768 / 960


def background(image):
    """A location picture: no transparent pixel (portraits are masked) and at least screen-sized in both directions."""
    return image.getextrema()[3][0] > 0 and min(image.size) >= BG_MIN


def look(image):
    """A small grey vector for comparing two pictures of one place at different sizes."""
    small = image.convert('L').resize((24, 32))
    values = list(small.getdata())
    mean = sum(values) / len(values)
    centred = [v - mean for v in values]
    norm = sum(v * v for v in centred) ** .5 or 1.
    return [v / norm for v in centred]


def similarity(a, b):
    return sum(x * y for x, y in zip(a, b))


def collect_backgrounds(library):
    """{fingerprint: Entry} of every background-like local picture of every episode, and each episode's record."""
    entries, records = {}, {}
    for number, record in enumerate(library.episodes, 1):
        try:
            resources = library.open_episode(record['id'])
        except Exception as error:
            logging.warning('%s: not opened (%s)', record['name'], error)
            continue
        records.setdefault(record['name'], []).append(record)
        for resource_id in sorted(resources.archive.entries):
            if resource_id < LOCAL_ART:
                continue
            try:
                data = resources.raw_asset(resource_id)
            except Exception:
                continue
            key = fingerprint(data)
            entry = entries.get(key)
            if entry is None:
                image = picture(data)
                if image is None or not background(image):
                    entries[key] = None
                    continue
                entry = entries[key] = Entry(data, image)
            if entry is not None:
                entry.uses.append((record['name'], resource_id, None, None))
        if number % 40 == 0:
            logging.info('backgrounds: %d / %d episodes', number, len(library.episodes))
    return {k: v for k, v in entries.items() if v is not None}, records


def write_backgrounds(library, out, entries, records):
    from exp_runtime.episode_index import same_story
    hd = sorted((e for e in entries.values() if e.image.width >= BG_HD_WIDTH), key=lambda e: sources(e))
    sd = sorted((e for e in entries.values() if e.image.width < BG_HD_WIDTH), key=lambda e: sources(e))
    for folder, group in (('bg-hd', hd), ('bg-sd', sd)):
        clear(out / folder)
        for number, entry in enumerate(group, 1):
            entry.serial = f'{number:04d}'
            entry.image.save(out / folder / f'{entry.serial}.png')
    store = library.twin_store()
    by_key = {fingerprint(e.data): e for e in hd}
    resolved, linked_from = {}, defaultdict(list)
    for entry in sd:
        twin = store.twin(entry.data)
        if twin is not None:
            resolved[fingerprint(entry.data)] = fingerprint(twin)
            linked_from[fingerprint(twin)].append(entry)
    unresolved = [e for e in sd if fingerprint(e.data) not in resolved]
    unlinked_hd = [e for e in hd if not linked_from.get(fingerprint(e.data))]
    looks = {id(e): look(e.image) for e in unresolved + unlinked_hd}
    hd_at = defaultdict(list)              # resource id -> [(episode, HD entry)]
    for entry in hd:
        for episode, resource_id, *_ in entry.uses:
            hd_at[resource_id].append((episode, entry))

    def thumb_bg(folder, entry):
        return f'<img src="{folder}/{entry.serial}.png" width="96">'

    lines = ['# HD backgrounds', '',
             f'{len(hd)} HD backgrounds (opaque pictures 700 px wide or more) in the library\'s episode files, each once however '
             'many episodes reuse it. "Linked" means a standard background already resolves to it in play (the twin store); '
             f'{len(hd) - len(unlinked_hd)} are linked, {len(unlinked_hd)} are not. The app\'s shared bank is not listed: its '
             'standard pictures are replaced by id from the HD app bundle.', '',
             '| Picture | # | Size | Linked | In (episode #resource) |', '|---|---|---|---|---|']
    for entry in hd:
        found = linked_from.get(fingerprint(entry.data), [])
        mark = f'yes ({", ".join("sd " + e.serial for e in found[:6])}{" ..." if len(found) > 6 else ""})' if found else 'no'
        lines.append(f'| {thumb_bg("bg-hd", entry)} | {entry.serial} | {entry.image.width}x{entry.image.height} | {mark} '
                     f'| {sources(entry)} |')
    (out / 'hd_backgrounds.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    lines = ['# Standard backgrounds with no HD counterpart', '',
             f'{len(unresolved)} of {len(sd)} standard backgrounds (opaque pictures 300 to 699 px wide) resolve to no HD '
             'picture in play. Leads: "Same id" is an HD background at the same resource id in the HD release of the same '
             'story; "Looks like" is the unlinked HD background whose small greyscale version correlates best with this one '
             '(shown at 0.80 or more, with the correlation) -- a lead to check by eye, not a match.', '',
             '| Picture | # | Size | Same id | Looks like | In (episode #resource) |', '|---|---|---|---|---|---|']
    for entry in unresolved:
        same = set()
        for episode, resource_id, *_ in entry.uses:
            for hd_episode, found in hd_at.get(resource_id, ()):
                if any(same_story(a, b) for a in records.get(episode, ()) for b in records.get(hd_episode, ())):
                    same.add(found.serial)
        mine = looks[id(entry)]
        best = max(((similarity(mine, looks[id(h)]), h) for h in unlinked_hd), default=(0, None), key=lambda p: p[0])
        like = f'hd {best[1].serial} ({best[0]:.2f})' if best[1] is not None and best[0] >= .8 else '-'
        lines.append(f'| {thumb_bg("bg-sd", entry)} | {entry.serial} | {entry.image.width}x{entry.image.height} | '
                     f'{", ".join("hd " + s for s in sorted(same)) or "-"} | {like} | {sources(entry)} |')
    (out / 'sd_backgrounds_without_hd.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    rows = []
    for entry in hd:
        found = sorted(linked_from.get(fingerprint(entry.data), []), key=lambda e: e.serial)
        if found:
            rows.append(f'| {" ".join(thumb_bg("bg-sd", e) for e in found)} | {", ".join(e.serial for e in found)} '
                        f'| {entry.serial} | {thumb_bg("bg-hd", entry)} |')
    write_matches(out, 'backgrounds', rows)
    return len(hd), len(unlinked_hd), len(sd), len(unresolved)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('library', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--steps', type=int, default=400)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--only', choices=('portraits', 'backgrounds'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    with ContentLibrary(args.library) as library:
        if args.only != 'backgrounds':
            entries, unregistered, base_links = collect(library, args.steps, args.seconds)
            resolved = links(library, {**entries, **unregistered}, base_links)
            counts = write(args.out, entries, unregistered, resolved, base_links)
            print('portraits: HD %d, standard %d (%d without HD), unregistered HD %d / standard %d' % counts)
        if args.only != 'portraits':
            counts = write_backgrounds(library, args.out, *collect_backgrounds(library))
            print('backgrounds: HD %d (%d unlinked), standard %d (%d without HD)' % counts)


if __name__ == '__main__':
    main()
