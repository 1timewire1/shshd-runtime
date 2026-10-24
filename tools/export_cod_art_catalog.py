"""Catalogue every character portrait and background in a Cause of Death library as Markdown documents with
full-resolution exports.

    python tools/export_cod_art_catalog.py LIBRARY OUT [--only portraits|backgrounds]

CoD has no HD release, so unlike `export_art_catalog.py` there is nothing to pair: every picture is listed once,
deduplicated by its bytes, with every place it appears. Pictures are found by shape, so none is missed:

    portraits     every picture with transparent pixels 100 to 200 px on both sides (CoD's are 110x120, a few up to
                  128x140), from every episode file and the app bundle
    backgrounds   every opaque picture 400 px or more on both sides (480x720, a few 420 wide), likewise

Each episode is also walked briefly (`tree_explorer`, as the SHS catalogue does) to name the portraits: its cast is
registered at the first step (`set_character_art_base`, five expression slots, `set_character_name`), and the walk
catches later renames and costume swaps. The walk also records every background shown, which is the only way to see
which episodes use the app bundle's own backgrounds (ids 1000-1050); a short walk does not reach every scene, so
those lists can be incomplete.

Written under OUT (outside the project: these are the player's own pictures):
    cod_portraits.md        every portrait, by name; pictures no walked character registers at the end
    cod_backgrounds.md      every background, the app bundle's first
    portraits/<serial>.png, backgrounds/<serial>.png    the pictures, full resolution with their transparency
"""
import argparse
import logging
import time
from collections import defaultdict
from pathlib import Path

from exp_runtime.content import ContentLibrary
from exp_runtime.hd_twins import LOCAL_ART, fingerprint

from export_art_catalog import Entry, clear, picture, portrait_slot

PORTRAIT_SIDES = (100, 200)
BACKGROUND_MIN = 400        # the 320x480 title painting (bundle #6) is not a scene
BUNDLE = 'app bundle'


def is_portrait(image):
    low, high = PORTRAIT_SIDES
    return image.getextrema()[3][0] == 0 and all(low <= side <= high for side in image.size)


def is_background(image):
    return image.getextrema()[3][0] > 0 and min(image.size) >= BACKGROUND_MIN


def walk(resources, steps, seconds):
    """({character: {'names': set, 'ids': set of (slot, id)}}, {background ids shown}) from a short walk."""
    from exp_runtime.runtime import Session
    from exp_runtime.tree_explorer import Explorer, Playthrough
    session = Session(resources, ephemeral=True)
    session.advance()
    explorer, playthrough = Explorer(resources, ephemeral=True), Playthrough(1)
    cast = defaultdict(lambda: {'names': set(), 'ids': set()})
    shown = set()
    started = time.time()
    for _ in range(steps):
        engine = session.engine
        for character, ids in engine.character_art_variants.items():
            cast[character]['ids'].update(enumerate(ids))
        for character, name in engine.character_names.items():
            if name and name.strip():
                cast[character]['names'].add(name.strip())
        if engine.panel.background_id >= 0:
            shown.add(engine.panel.background_id)
        if (time.time() - started > seconds or session.pending is None
                or session.pending.name in ('finished', 'episode_exit')):
            break
        try:
            explorer.act(session, playthrough)
        except Exception:               # an unsupported screen ends the walk, not the catalogue
            break
    return cast, shown


class Catalogue:
    def __init__(self):
        self.portraits, self.backgrounds = {}, {}       # fingerprint -> Entry
        self.rejected = set()                           # fingerprints that are neither

    def add(self, data, use, names=()):
        """File the picture as a portrait or a background by its shape; None if it is neither."""
        key = fingerprint(data)
        entry = self.portraits.get(key) or self.backgrounds.get(key)
        if entry is None:
            if key in self.rejected:
                return None
            image = picture(data)
            if image is not None and is_portrait(image):
                entry = self.portraits[key] = Entry(data, image)
            elif image is not None and is_background(image):
                entry = self.backgrounds[key] = Entry(data, image)
            else:
                self.rejected.add(key)
                return None
        if use not in entry.uses:
            entry.uses.append(use)
        entry.names.update(names)
        return entry


def collect(library, steps, seconds, walk_episodes=True):
    catalogue = Catalogue()
    for resource_id in sorted(library.base_members):
        try:
            data = library.android_asset(resource_id)
        except Exception:
            continue
        catalogue.add(data, (BUNDLE, resource_id, None, None))
    for number, record in enumerate(library.episodes, 1):
        try:
            resources = library.open_episode(record['id'])
        except Exception as error:
            logging.warning('%s: not opened (%s)', record['name'], error)
            continue
        episode = record['name']
        # Names and expression slots first, so a registered slot's use carries them.
        if walk_episodes:
            try:
                cast, shown = walk(resources, steps, seconds)
            except Exception as error:
                logging.warning('%s: not walked (%s)', episode, error)
                cast, shown = {}, set()
            for character, info in cast.items():
                for slot, resource_id in sorted(info['ids']):
                    if resource_id is None or resource_id < 0:
                        continue
                    try:
                        data = resources.raw_asset(resource_id)
                    except Exception:
                        continue
                    key = fingerprint(data)
                    existing = catalogue.portraits.get(key)
                    if existing is None:
                        image = picture(data)
                        if image is None or not is_portrait(image) or not portrait_slot(image, slot):
                            continue
                    catalogue.add(data, (episode, resource_id, character, slot), info['names'])
            for resource_id in sorted(shown):
                if resource_id >= LOCAL_ART:
                    continue                # the episode's own: listed from the file below
                try:
                    data = resources.raw_asset(resource_id)
                except Exception:
                    continue
                if fingerprint(data) in catalogue.backgrounds:
                    catalogue.add(data, (episode, resource_id, None, None))
        registered = {(e, r) for entry in catalogue.portraits.values() for e, r, *_ in entry.uses}
        for resource_id in sorted(resources.archive.entries):
            if resource_id < LOCAL_ART or (episode, resource_id) in registered:
                continue
            try:
                data = resources.raw_asset(resource_id)
            except Exception:
                continue
            catalogue.add(data, (episode, resource_id, None, None))
        logging.info('%d / %d %s', number, len(library.episodes), episode)
    return catalogue


def place(use):
    """Uses in the order shown: the app bundle first, then by episode and resource id."""
    episode, resource_id, *_ = use
    return episode != BUNDLE, episode.lower(), resource_id


def sources(entry, limit=8):
    rows = sorted({(episode, resource_id) for episode, resource_id, *_ in entry.uses}, key=place)
    text = '; '.join(f'{episode.removesuffix(".exp")} #{resource_id}' for episode, resource_id in rows[:limit])
    return text + (f'; +{len(rows) - limit} more' if len(rows) > limit else '')


def episode_count(entry):
    return len({episode for episode, *_ in entry.uses if episode != BUNDLE})


def label(entry):
    return ', '.join(sorted(entry.names)) if entry.names else '(no name)'


def expressions(entry):
    slots = sorted({slot for *_, slot in entry.uses if slot is not None})
    return ', '.join(str(slot) for slot in slots) if slots else '-'


def thumb(folder, entry, width):
    return f'<img src="{folder}/{entry.serial}.png" width="{width}">'


def export(out, folder, group):
    clear(out / folder)
    for number, entry in enumerate(group, 1):
        entry.serial = f'{number:04d}'
        entry.image.save(out / folder / f'{entry.serial}.png')


NAMES_NOTE = ("`$CADY` is a player-chosen name (12_Fallon_Family_Christmas's playable lead); the few other names starting "
              "with `$` (`$Ramsey Brand`, `$Officer NR1`...) are spelled that way in the scripts. A picture used by "
              "several characters lists every name it appears under. \"Expr.\" is the expression slot (0 to 4) the "
              "picture fills; \"Eps\" counts the episode files that use it.")


def write_portraits(out, catalogue):
    named = sorted((e for e in catalogue.portraits.values() if e.names),
                   key=lambda e: (label(e).lower(), min(map(place, e.uses))))
    unnamed = sorted((e for e in catalogue.portraits.values() if not e.names), key=lambda e: min(map(place, e.uses)))
    export(out, 'portraits', named + unnamed)
    bundle = sum(1 for e in catalogue.portraits.values() if any(u[0] == BUNDLE for u in e.uses))
    lines = ['# Cause of Death portraits', '',
             f'{len(catalogue.portraits)} portraits (pictures with transparency, 100 to 200 px on both sides) in the '
             f'library\'s episode files and the app bundle, each once however many episodes and characters reuse it; '
             f'{bundle} are in the app bundle (ids 2000 and up, "{BUNDLE} #id"). {len(named)} are registered by a '
             f'character in a short walk of each episode and listed by name; the other {len(unnamed)} are listed at the '
             'end without names.', '', NAMES_NOTE, '',
             '| Picture | # | Name(s) | Expr. | Size | Eps | Used in (episode #resource) |',
             '|---|---|---|---|---|---|---|']
    for entry in named:
        lines.append(f'| {thumb("portraits", entry, 72)} | {entry.serial} | {label(entry)} | {expressions(entry)} '
                     f'| {entry.image.width}x{entry.image.height} | {episode_count(entry)} | {sources(entry)} |')
    if unnamed:
        lines += ['', '## Portraits no walked character registers', '',
                  'In the files but not registered in the walk: art for a later scene the walk did not reach, a '
                  'character the scripts never show, or (for the app bundle) a portrait no episode in this library '
                  'uses.', '',
                  '| Picture | # | Size | Eps | In (episode #resource) |', '|---|---|---|---|---|']
        lines += [f'| {thumb("portraits", e, 72)} | {e.serial} | {e.image.width}x{e.image.height} | {episode_count(e)} '
                  f'| {sources(e)} |' for e in unnamed]
    (out / 'cod_portraits.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return len(named), len(unnamed)


def write_backgrounds(out, catalogue):
    entries = sorted(catalogue.backgrounds.values(), key=lambda e: min(map(place, e.uses)))
    export(out, 'backgrounds', entries)
    bundle = [e for e in entries if any(u[0] == BUNDLE for u in e.uses)]
    unseen = sum(1 for e in bundle if not episode_count(e))
    lines = ['# Cause of Death backgrounds', '',
             f'{len(entries)} backgrounds (opaque pictures 400 px or more on both sides) in the library\'s episode '
             'files and the app bundle, each once however many episodes reuse it. "Eps" counts the episode files '
             'that use it.', '',
             f'The first {len(bundle)} are the app bundle\'s ("{BUNDLE} #id"). Episodes show those by id rather than '
             'carrying a copy, so the episodes listed for them are the ones whose short walk displayed them, and can '
             f'be incomplete; {unseen} were not seen in any walk. Every other background is listed from the episode '
             'files themselves, so its list is complete.', '',
             '| Picture | # | Size | Eps | In (episode #resource) |', '|---|---|---|---|---|']
    lines += [f'| {thumb("backgrounds", e, 96)} | {e.serial} | {e.image.width}x{e.image.height} | {episode_count(e)} '
              f'| {sources(e)} |' for e in entries]
    (out / 'cod_backgrounds.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return len(entries), len(bundle), unseen


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('library', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--steps', type=int, default=1500)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--only', choices=('portraits', 'backgrounds'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    with ContentLibrary(args.library) as library:
        if library.game_id != 'cod':
            parser.error(f'{args.library} is not a Cause of Death library')
        catalogue = collect(library, args.steps, args.seconds)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.only != 'backgrounds':
        print('portraits: %d named, %d without a name' % write_portraits(args.out, catalogue))
    if args.only != 'portraits':
        print('backgrounds: %d (%d in the app bundle, %d of those not seen in a walk)'
              % write_backgrounds(args.out, catalogue))


if __name__ == '__main__':
    main()
