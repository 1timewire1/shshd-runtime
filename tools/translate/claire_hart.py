"""Claire Hart Classic (build 157) for Cause of Death: the reader of its cases and the story add-on `chc`
(Other Games/docs/CLAIRE_HART_PLAN.md, Stage 1).

    python tools/translate/claire_hart.py report --mirror CLAIRE_HART_DIR
    python tools/translate/claire_hart.py ids --mirror CLAIRE_HART_DIR --out claire_hart_ids.tsv
    python tools/translate/claire_hart.py addon --mirror CLAIRE_HART_DIR --pairs PAIRS.txt --catalog COD_CATALOG_PORTRAITS \\
        --cod-library COD_LIBRARY --extras EXTRAS_DIR --out OUT_DIR

CLAIRE_HART_DIR is the mirror (`reference/Other Games/Claire Hart Classic`: bundle_names.csv, raw/, unpacked/, index/).

The reader (`Mirror`) holds what the converter needs, besides each episode's own nodes:
- the cases in the case list's order, each a translated entry of pack 31500 numbered `index` x 10 (decision N), its title
  "Case n" or a special's own (N2), its parts the original episodes (`ids`: E-number <-> case and part);
- the looks (`looks`): every portrait folded into a look of CoD's 5 expression slots, Normal, Angry, Happy, Sad and Surprised
  (CoD's 4th, a worried face), so a look is 5 consecutive IDs as CoD draws one (cod/profile.py LOOK_BANKS). A face the look
  lacks takes its Normal, as Classic's driver falls back to `default`; Young*, Masked and the numbered Normals are looks of
  their own, and so is a face past the five (Lavender's Scream);
- the scenes (`scenes`): each of the 787 scene folders' backdrop (`template`) with its 3:4 slice (decision M, A): where
  Cause of Death cut that scene (index/bg_vs_template.json, a confident match), else centred;
- the tracks and story-object pictures, and the rounds' story-object lists resolved to the scene's items (`story_objects`,
  decision G2: the 985 that name an item).

`chc` holds all of it, used or not (owner, 2026-11-19), around chslim revision 1's resources under their IDs (chslim.py):

    26000-26786  the backdrops, the folders' sorted order, their original PNGs (full brightness: dimmed at draw time)
    26900-26932  the tracks, MP3 128 kb/s (FFmpeg)
    26960-26962  the Title Screen Look; 26990 Title Screen Music, the main jingle
    26998        the spec, JSON (SPEC_VERSION): looks, look names, picture IDs, scenes and slices, tracks, story objects
    27000-27644  the story-object pictures, their original PNGs
    28000-28005  chslim's map, frame backdrop, bubbles and fonts; 28010-28844 every portrait (28010 + its place in the sorted
                 list); 29000-29001 chslim's CoD-only edits; 29100-29108 Claire Hart Dialogue (ch_dialogue_skin.py)
"""
import argparse
import collections
import csv
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chslim                                               # noqa: E402

PACK_ID = chslim.PACK_ID                                    # 31500
SLOTS = ('Normal', 'Angry', 'Happy', 'Sad', 'Surprised')    # CoD's expression slots, in order
BACKDROP_BASE, MUSIC_BASE, STORY_OBJECT_BASE = 26000, 26900, 27000
TITLE_SPEC, TITLE_BACKGROUND, TITLE_LOGO, TITLE_MUSIC = 26960, 26961, 26962, 26990
SPEC, SPEC_VERSION = 26998, 1                               # (LOOK_BANKS reads its `looks`)
CUT_AGREEMENT = 0.5                                         # a CoD cut this sure of its scene places the slice
# The Title Screen Look (Stage 0, decision Q): Classic's Play Now forest, and its logo (Claire and Paul over the gem banner)
# cut from the loading atlas; the jingle the episode select plays once.
FOREST = 'textures/new/loading_playnow_bg'
ATLAS, LOGO = 'raw/157/assets/resources/native/17/170baf746.png', (3, 3, 3 + 456, 3 + 381)
JINGLE = 'raw/157/assets/resources/native/b1/b143c842-d6d6-4a59-bf1f-2a3d0884f1e6.ogg'
TITLE_LOOK = {'version': 1,
              'background': {'cover': {'id': TITLE_BACKGROUND, 'scale': 1}},
              # 1.4 points a pixel: 638 points of the 768-wide frame, its foot about 50 points above Play/Resume (HD's
              # 753); in a taller frame it stays halfway between the top and where the buttons go.
              'title': {'picture': {'id': TITLE_LOGO, 'scale': 1.4}, 'centre': [384, 440], 'follow': 0.5}}
WRAPPED = ('textColors', 'music', 'sounds', 'dialog objects', 'sprites')    # driver.runConfig keeps these as sub-maps
NOTHING = ('nothing', 'none', 'noobject', 'nostoryobject')
FACE = re.compile(r'(.*?)_?(Normal|Sad|Angry|Happy|Surprised|Scream|Masked)( \d)?$')


def norm(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def folder_of(scene):
    """sceneloader: a scene's name to its folder."""
    return re.sub(r'[^a-zA-Z0-9]', '', scene)


def refs_for(chapter_refs):
    """driver.runConfig: a chapter's sceneRefs merged into one lookup, the WRAPPED maps kept whole."""
    refs = {}
    for key, value in chapter_refs.items():
        if key in WRAPPED:
            refs[key] = value
        else:
            refs.update(value)
    return refs


def look_of(path):
    """(look key, face) of a portrait path: the folder and the stem without its face. Masked and a numbered Normal are their
    own looks; Young* folds as a look of its own by its stem (Avatar_Claire_YoungSad -> Avatar_Claire_Young, Sad)."""
    folder, stem = path.rsplit('/', 1)
    match = FACE.match(stem)
    if match is None:
        return path, 'Normal'
    base, face, number = match.groups()
    if face == 'Masked':
        base, face = base + '_Masked', 'Normal'
    elif number:
        base, face = f'{base}_Normal{number.strip()}', 'Normal'
    return f'{folder}/{base}', face


def look_name(key):
    """A look's name for the Creator: 'references/characters/ClaireHart/Avatar_Claire_Young' -> 'Claire Young'."""
    stem = re.sub(r'^Avatar_', '', key.rsplit('/', 1)[1])
    words = re.sub(r'(?<=[a-z])(?=[A-Z0-9])', ' ', stem.replace('_', ' '))
    return ' '.join(words.split())


def case_title(case):
    """N2: a numbered case is "Case n"; a special keeps its title."""
    return case['title'].strip() or case['case'].strip().title()


class Mirror:
    """Claire Hart Classic's data, read from the mirror folder."""

    def __init__(self, root):
        self.root = Path(root)
        with open(self.root / 'bundle_names.csv', encoding='utf-8-sig', newline='') as file:
            rows = [row for row in csv.DictReader(file) if row['part'] == 'native']
        self.files = {row['real_path']: self.root / row['local_path'] for row in rows}
        self.kinds = {row['real_path']: row['kind'] for row in rows}
        self.cases_dir = self.root / 'unpacked/resources_json/cases'
        self.scenes_dir = self.root / 'raw/157/res/raw-assets/references/backgrounds'

    def _load(self, path):
        return json.loads(Path(path).read_text(encoding='utf-8'))

    # --- cases ---------------------------------------------------------------------------------------------------------
    def cases(self):
        """[(case key, case record, [(part, epconfig, sequences)])] in the case list's order."""
        caselist = self._load(self.cases_dir / 'caselist.json')
        out = []
        for key, case in sorted(caselist.items(), key=lambda kv: kv[1]['index']):
            folder = case['case'].replace('CASE ', 'case').replace(' ', '')     # hogstart / chapterselection rule
            parts = []
            for number, _ in enumerate(case['episodes'], 1):
                episode = self.cases_dir / folder / f'ep{number}'
                parts.append((number, self._load(episode / 'epconfig.json'),
                              self._load(episode / 'sequences.json')['sequences']))
            out.append((key, case, parts))
        return out

    def ids(self):
        """The testing table (decision N): a row per original episode, E-number to its case, part and translated entry."""
        rows = []
        for key, case, parts in self.cases():
            for number, config, _ in parts:
                rows.append(dict(epid=config['epid'], case=key, case_index=case['index'], case_title=case_title(case),
                                 part=number, parts=len(parts), pack=PACK_ID, episode=case['index'] * 10,
                                 title=config['title'].strip()))
        return rows

    # --- portraits and looks -------------------------------------------------------------------------------------------
    def portraits(self):
        return sorted(path for path, kind in self.kinds.items() if kind == 'portrait')

    def picture_ids(self):
        """{portrait path: its lasting ID} (chslim's rule)."""
        return chslim.portrait_ids(self.portraits())

    def looks(self):
        """[(look key, {face: path})], sorted by key: the look's number is its place here."""
        found = collections.defaultdict(dict)
        for path in self.portraits():
            key, face = look_of(path)
            if face in found[key]:
                raise ValueError(f'two {face} faces for look {key}')
            found[key][face] = path
        out = []
        for key in sorted(found):
            faces = found[key]
            extra = sorted(set(faces) - set(SLOTS))
            if extra and 'Surprised' not in faces and len(extra) == 1:
                faces['Surprised'] = faces.pop(extra[0])        # a lone extra face takes the 5th slot (plan, Stage 1)
                extra = []
            for face in extra:                                  # else its own look (Lavender's Scream)
                out.append((f'{key}_{face}', {'Normal': faces.pop(face)}))
            out.append((key, faces))
        return sorted(out)

    def look_banks(self):
        """(banks, names, slots): each look's 5 picture IDs (a missing face its Normal, or its first face without one), its name,
        and {portrait path: (look, slot)} of the faces it shows itself."""
        ids = self.picture_ids()
        banks, names, slots = [], [], {}
        for number, (key, faces) in enumerate(self.looks()):
            fallback = faces.get('Normal') or next(faces[face] for face in SLOTS if face in faces)
            banks.append([ids[faces.get(face, fallback)] for face in SLOTS])
            names.append(look_name(key))
            for slot, face in enumerate(SLOTS):
                if face in faces:
                    slots[faces[face]] = (number, slot)
        return banks, names, slots

    # --- scenes --------------------------------------------------------------------------------------------------------
    def scene_folders(self):
        return sorted(p.name for p in self.scenes_dir.iterdir() if (p / 'hd' / 'template.png').exists())

    def cod_cuts(self):
        """{scene folder: [(CoD background, centre x in the template)]}: Cause of Death's own cuts, the confident ones."""
        cuts = collections.defaultdict(list)
        index = self._load(self.root / 'index/bg_vs_template.json')
        for number, entry in sorted(index.items()):
            best = (entry.get('cands') or [None])[0]
            if best and best.get('agree', 0) >= CUT_AGREEMENT:
                x, _, w, _ = best['crop']
                cuts[best['scene']].append((number, x + w / 2))
        return cuts

    def scenes(self):
        """{scene folder: (backdrop ID, slice x, how)}: the 3:4 slice's left edge in the template's pixels (a 1024 x 768
        template's slice is 576 wide), at CoD's first cut of the scene ('cod') or centred ('centre')."""
        from PIL import Image
        cuts = self.cod_cuts()
        out = {}
        for number, folder in enumerate(self.scene_folders()):
            with Image.open(self.scenes_dir / folder / 'hd' / 'template.png') as image:
                width, height = image.size
            span = round(height * 3 / 4)
            if folder in cuts:
                centre, how = cuts[folder][0][1], 'cod'
            else:
                centre, how = width / 2, 'centre'
            out[folder] = (BACKDROP_BASE + number, max(0, min(width - span, round(centre - span / 2))), how)
        return out

    def backdrop(self, folder):
        return (self.scenes_dir / folder / 'hd' / 'template.png').read_bytes()

    # --- music and story objects ---------------------------------------------------------------------------------------
    def tracks(self):
        """{track stem: (music ID, the OGG's path)}."""
        prefix = 'references/music/ogg/'
        stems = sorted(path[len(prefix):] for path in self.files if path.startswith(prefix))
        return {stem: (MUSIC_BASE + number, self.files[prefix + stem]) for number, stem in enumerate(stems)}

    def story_object_ids(self):
        """{story-object picture path: its ID}."""
        paths = sorted(path for path, kind in self.kinds.items() if kind == 'storyobj')
        return {path: STORY_OBJECT_BASE + number for number, path in enumerate(paths)}

    def scene_items(self, folder):
        """The scene's hidden objects as names.json gives them: [{'normal', 'name', ...}]."""
        path = self.scenes_dir / folder / 'names.json'
        return self._load(path)['names'] if path.exists() else []

    def story_objects(self):
        """Every round's story-object list resolved (decision G2): [(epid, round scene, entry, item or None)], the item the
        names.json entry the list names: by its name, else as build 157 matched (a substring of the sprite or name)."""
        out = []
        for _, _, parts in self.cases():
            for _, config, _ in parts:
                for chapter in config['sceneRefs'].values():
                    for value in chapter.get('backgrounds', {}).values():
                        if value.get('type') != 'hogScene' or value.get('storyobject') is None:
                            continue
                        listed = value['storyobject']
                        for entry in [listed] if isinstance(listed, str) else listed:
                            base = norm(re.sub(r'\s*[\[\(].*$', '', entry).strip())
                            if not base or base in NOTHING or 'nostoryobject' in norm(entry):
                                continue
                            names = self.scene_items(folder_of(value['scene']))
                            hit = [e for e in names if norm(e['name']) == base] or \
                                  [e for e in names if base in norm(e['normal']) or base in norm(e['name'])] or \
                                  [e for e in names if norm(e['name']) and norm(e['name']) in base]
                            out.append((config['epid'], value['scene'], entry, hit[0] if hit else None))
        return out

    # --- the add-on ----------------------------------------------------------------------------------------------------
    def spec(self):
        banks, names, slots = self.look_banks()
        return {'version': SPEC_VERSION, 'looks': banks, 'look_names': names,
                'pictures': {path: [*slots[path], ident] if path in slots else [None, None, ident]
                             for path, ident in self.picture_ids().items()},
                'scenes': {folder: [ident, x] for folder, (ident, x, _) in self.scenes().items()},
                'music': {stem: ident for stem, (ident, _) in self.tracks().items()},
                'story_objects': self.story_object_ids()}


def mp3(ogg, folder):
    """An OGG as a 128 kb/s MP3, by FFmpeg."""
    out = Path(folder) / 'track.mp3'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(ogg), '-codec:a', 'libmp3lame', '-b:a', '128k', str(out)],
                   check=True)
    return out.read_bytes()


def addon(mirror, pairs, catalog, sources, extras, progress=print):
    """chc's resources {ID: bytes} and a report: chslim revision 1's (`chslim.contents(chc=True)`) and the rest."""
    from PIL import Image
    from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes
    if shutil.which('ffmpeg') is None:
        raise SystemExit('FFmpeg is needed for the tracks')
    resources, report = chslim.contents(mirror.root, pairs, catalog, sources, extras, chc=True)
    progress(f'chslim revision 1: {len(resources)} resources')
    added = 0
    for path, ident in mirror.picture_ids().items():         # every other portrait, whole (chslim's `whole`)
        if ident not in resources:
            resources[ident] = chslim.png(chslim.whole(Image.open(mirror.files[path]).convert('RGBA')))
            added += 1
    progress(f'portraits: {added} added')
    scenes = mirror.scenes()
    for folder, (ident, _, _) in scenes.items():
        resources[ident] = mirror.backdrop(folder)
    progress(f'backdrops: {len(scenes)}')
    for path, ident in mirror.story_object_ids().items():
        resources[ident] = mirror.files[path].read_bytes()
    tracks = mirror.tracks()
    with tempfile.TemporaryDirectory() as folder:
        for stem, (ident, ogg) in tracks.items():
            resources[ident] = mp3(ogg, folder)
        resources[TITLE_MUSIC] = mp3(mirror.root / JINGLE, folder)
    progress(f'tracks: {len(tracks)} and the jingle')
    resources[TITLE_SPEC] = json.dumps(TITLE_LOOK).encode()
    resources[TITLE_BACKGROUND] = chslim.png(Image.open(mirror.files[FOREST]).convert('RGBA'))
    resources[TITLE_LOGO] = chslim.png(Image.open(mirror.root / ATLAS).convert('RGBA').crop(LOGO))
    spec = mirror.spec()
    resources[SPEC] = json.dumps(spec, separators=(',', ':')).encode('utf-8')
    resources[ADDON_RECORD] = provides_bytes(chslim.CHC_ID, chslim.CHC_TITLE, chslim.CHC_REVISION,
                                             supersedes=((chslim.ADDON_ID, chslim.ADDON_REVISION),))
    report.update(portraits=len(mirror.portraits()), looks=len(spec['looks']), backdrops=len(scenes),
                  cod_slices=sum(how == 'cod' for _, _, how in scenes.values()), tracks=len(tracks),
                  story_objects=len(spec['story_objects']), resources=len(resources))
    return resources, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('report', 'ids', 'addon'):
        command = commands.add_parser(name)
        command.add_argument('--mirror', type=Path, required=True)
        if name == 'ids':
            command.add_argument('--out', type=Path, required=True)
        if name == 'addon':
            command.add_argument('--pairs', type=Path, required=True)
            command.add_argument('--catalog', type=Path, required=True, help="the CoD catalogue's portraits folder")
            command.add_argument('--cod-library', type=Path, required=True)
            command.add_argument('--extras', type=Path, required=True)
            command.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    mirror = Mirror(args.mirror)
    if args.command == 'ids':
        rows = mirror.ids()
        with open(args.out, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        print(f'{len(rows)} episodes in {len({row["case"] for row in rows})} cases -> {args.out}')
    elif args.command == 'report':
        cases = mirror.cases()
        banks, _, slots = mirror.look_banks()
        scenes = mirror.scenes()
        resolved = mirror.story_objects()
        print(f'cases {len(cases)}, episodes {sum(len(parts) for _, _, parts in cases)}')
        print(f'portraits {len(mirror.portraits())}, looks {len(banks)}, faces shown in a look\'s own slot {len(slots)}')
        print(f'scenes {len(scenes)}: at CoD\'s cut {sum(h == "cod" for _, _, h in scenes.values())}, '
              f'centred {sum(h == "centre" for _, _, h in scenes.values())}')
        print(f'tracks {len(mirror.tracks())}, story-object pictures {len(mirror.story_object_ids())}')
        print(f'story-object list entries {len(resolved)}: resolve {sum(item is not None for *_, item in resolved)}')
    else:
        from exp_runtime.exp import encode_exp
        resources, report = addon(mirror, chslim.read_pairs(args.pairs.read_text(encoding='utf-8')), args.catalog,
                                  chslim.library_pictures(args.cod_library), args.extras)
        args.out.mkdir(parents=True, exist_ok=True)
        data = encode_exp(resources)
        del resources
        (args.out / 'CH_Classic.exp').write_bytes(data)
        print(f'addon: {chslim.CHC_TITLE!r} -> {args.out / "CH_Classic.exp"} ({len(data) // 2 ** 20} MB), {report}')
        return 1 if report['unfound'] else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
