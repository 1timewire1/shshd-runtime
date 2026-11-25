"""Claire Hart: Secret in the Shadows (build 232) for Cause of Death: the reader of its cases, the stage tracker that gives
every line its face, and the story add-on `ch2` (Other Games/docs/CLAIRE_HART_PLAN.md, sequel Stage S1;
CLAIRE_HART_SHADOWS_ENGINE.md for the game's own rules).

    python tools/translate/claire_hart_shadows.py report --mirror CH2_DIR
    python tools/translate/claire_hart_shadows.py ids --mirror CH2_DIR --out claire_hart_shadows_ids.tsv
    python tools/translate/claire_hart_shadows.py faces --mirror CH2_DIR [--out FACES.tsv]
    python tools/translate/claire_hart_shadows.py portraits --mirror CH2_DIR --sheet SHEET.png --classic CLASSIC_DIR
    python tools/translate/claire_hart_shadows.py names --mirror CH2_DIR --out NAMES.md [--sheet SHEET.png]
    python tools/translate/claire_hart_shadows.py addon --mirror CH2_DIR --out OUT_DIR

CH2_DIR is the mirror (`reference/Other Games/Claire Hart Secret in the Shadows`: bundle_names.csv, raw/, unpacked/).

It reads the sequel's own dialect of Classic's data (Classic's reader is claire_hart.py, whose text rules it shares):
- the case list is a list (`case_list`), each case numbered (`case`) with its episodes' titles and ids
  (`ch2_epid.<c>case<e>ep`); case 31's three unlisted parts join it with their released titles, and case 45's
  placeholder takes its released title (decision K);
- an episode's chapters are the ids `main` plays, in its order: `SCENE 1_1`..`SCENE 1_6` or `SCENE 1`..`SCENE 6` (both
  schemes occur), and its rounds the `playHOG` ids between them, kept byte for byte (case 46 ep 3's hold an NBSP);
- a chapter's refs are driver.runConfig's: `backgrounds` and `characters` merged, each character also under its key in
  lower case (how the data's `CLAIRE` intros resolve), the other maps kept whole;
- music is `references/music/<Track>.mp3` in the chapter's own map only (`FILL THIS IN` keeps the track playing).

The faces (`Stage`): the game shows a character's face on its stage, set by the intro (`default`) and each
`stageBlockExpressionChange`; a line lights its speaker (`narrator`, else Claire for an empty header, else the header).
So a line's portrait is the speaker's face on stage. Every speaker line that has an `expression` field agrees with it
(11,482); the tracker gives the 680 without one theirs. Fixes (owner, 2026-11-24, ENGINE section 10): a speaker off stage
(78 lines, case 40 ep 1's empty stage among them) shows their `default`; a `narrator` that names nobody (`Happy`, `Clare`,
`Claire]`) is Claire; a face path in the wrong case (Rufus) resolves case-insensitively.

The looks: every portrait folder is a look of CoD's five slots, Normal (`normal` or `neutral`), Angry, Happy, Sad,
Surprised; pictures with the same pixels are one picture (Harper's neutral and normal, Simon's sd and hd, Paige's two
Halloween copies), and Paige's Halloween is a look of its own. The 14 `template` sheets are never shown and stay out.

The portraits (crop rule, owner's review sheet): the sequel's are half-body figures standing on the canvas foot, their
heads smaller than Classic's head-and-shoulders. Each becomes a window CROP_HEIGHT source pixels tall in CoD's portrait
shape (110 x 120), its top CROP_MARGIN above the figure's top, centred on the head (the alpha's middle over HEAD_BAND rows),
scaled to CoD's portrait at twice its size (220 x 240), as chslim.whole gives Classic's. At 380 the heads match Classic's.

`ch2` holds:

    26000-26519  the scenes' clean bases (the round layout's `default` layer: the scene without its objects; else the
                 template), 1024 x 768, full brightness (dimmed at draw time to 102), in the folders' sorted order
    26900-26936  the tracks, MP3 128 kb/s (FFmpeg)
    26998        the spec, JSON: looks, look names, pictures, scenes and slices, tracks, story objects (as chc's)
    26999        the frame backdrop beside CoD's frame (the episode selector's own backdrop)
    27000-27257  the story-object photos, their original PNGs: the 253 pictures, then the 5 round sprites photos show
    28000-28417  the portraits, cropped (above), at 28000 + their place in the sorted list (a duplicate takes the first's)
"""
import argparse
import collections
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claire_hart import markdown_table, mp3, norm, story_text      # noqa: E402

PACK_ID = 31900
ADDON_ID, ADDON_TITLE, ADDON_REVISION = 'ch2', 'Claire Hart: Secret in the Shadows', 1
TITLE_TAG = ' (CH2)'
SLOTS = ('Normal', 'Angry', 'Happy', 'Sad', 'Surprised')
FACE_SLOTS = {'normal': 0, 'neutral': 0, 'angry': 1, 'happy': 2, 'sad': 3, 'surprised': 4}
BACKDROP_BASE, MUSIC_BASE, STORY_OBJECT_BASE, PORTRAIT_BASE = 26000, 26900, 27000, 28000
SPEC, FRAME_BACKDROP, SPEC_VERSION = 26998, 26999, 1
LOOK_BANK_BASE = 30000                       # cod/profile.py LOOK_BANKS[31900]: look n is 30000 + 5n on
FRAME_ART = 'textures/SD/episodeSelector/episodeselector_bg'
BACKDROP_SIZE = (1024, 768)
SLICE_X = (BACKDROP_SIZE[0] - round(BACKDROP_SIZE[1] * 3 / 4)) // 2     # centred: CoD cut none of these scenes (M, ENGINE 12)
CROP_HEIGHT, CROP_MARGIN, HEAD_BAND = 380, 14, 140
CROP_HEIGHTS = {'Avatar_BrowdyBrothers': 540}     # a look's own window: both brothers (module doc)
PORTRAIT_SIZE = (220, 240)                   # CoD's 110 x 120 at twice its size (chslim.SCALE)
# Decision K (settled 2026-11-20): case 31's parts 2-4, dropped from the case list by build 232, and case 45's
# placeholder, with the titles they were released under (ENGINE 2.1).
UNLISTED_PARTS = {31: ("Eric's Past", 'Accident Averted', "Claire's heart")}
RELEASED_TITLES = {45: ('Lost Soul', ('Lost Soul',))}
WRAPPED = ('textColors', 'music', 'sounds', 'journal', 'dialogStoryObjects', 'sprites')
# Look names a folder's capitals don't give.
LOOK_NAMES = {'AlessandravanderWalt': 'Alessandra van der Walt', 'BrowdyBrothers': 'Browdy Brothers',
              'HalloweenPaige': 'Paige Mills Halloween 2', 'YoungClaireHart': 'Young Claire Hart',
              'YoungSusanHart': 'Young Susan Hart', 'Claudia Young': 'Young Claudia Anderson'}
NOTHING = ('nothing', 'none', 'noobject', 'nostoryobject')
CLAIRE = 'references/characters/Avatar_ClaireHart/sd/avatar_clairehart_normal'
# Decision L: photos whose round list names no item of its scene, named from the picture (owner's review list).
HAND_NAMES = {'case1ep1scene1_5_0': 'Case Folder', 'case12ep4scene4_0': "Woman's Boots", 'case25ep2scene4_0': 'Rope',
              'case36ep1scene4_0': 'Empty Box', 'case36ep2scene6_0': 'Jewel Box'}

Part = collections.namedtuple('Part', 'number title epid folder config sequences listed')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def refs_for(chapter_refs):
    """driver.runConfig: a chapter's sceneRefs merged, each character also under its key in lower case."""
    refs = {}
    for key, value in chapter_refs.items():
        if key in WRAPPED:
            refs[key] = value
            continue
        if key == 'characters' and isinstance(value, dict):
            value = dict(value)
            for name in list(value):
                value.setdefault(name.lower(), value[name])
        refs.update(value)
    return refs


def chapters_of(sequences):
    """The chapters `main` plays, in order, each with the round after it (or None): [(chapter id, round id)]."""
    out = []
    for node in sequences['main']['nodes']:
        if node['type'] == 'playSequence':
            out.append([node['sequenceId'], None])
        elif node['type'] == 'playHOG' and out:
            out[-1][1] = node['hogId']
    return [tuple(pair) for pair in out]


def look_key(path):
    """(look key, slot) of a portrait path: its folder, its face by the file name's last word; `halloween` is a look of
    its own ('happy_copy' is Harrison's Happy)."""
    _, _, folder, _, stem = path.split('/')
    words = stem.lower().replace('_copy', '').split('_')
    if words[-1] == 'halloween':
        return f'{folder}/Halloween', 0
    return folder, FACE_SLOTS[words[-1]]


def look_name(key):
    """'Avatar_ClaireHart' -> 'Claire Hart', 'Avator_James Lieft' -> 'James Lieft', 'Avator_PaigeMills/Halloween' ->
    'Paige Mills Halloween'."""
    folder, _, variant = key.partition('/')
    stem = re.sub(r'^Avat[ao]r[_ ]', '', folder)
    name = LOOK_NAMES.get(stem) or ' '.join(re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', stem.replace('_', ' ')).split())
    return f'{name} {variant}' if variant else name


def portrait_crop(picture, height=CROP_HEIGHT):
    """The crop rule (module doc): the sequel's half-body `picture` (RGBA) as CoD's 220 x 240 portrait. A taller window
    (`height`, CROP_HEIGHTS) is centred on the whole figure instead: the Browdy brothers are two people."""
    import numpy as np
    from PIL import Image
    alpha = np.asarray(picture.getchannel('A'), dtype=float)
    rows = np.nonzero(alpha.max(axis=1) > 16)[0]
    top = int(rows[0]) if len(rows) else 0
    band = alpha[top:top + HEAD_BAND] if height == CROP_HEIGHT else alpha
    weight = band.sum()
    centre = (band.sum(axis=0) * np.arange(alpha.shape[1])).sum() / weight if weight else alpha.shape[1] / 2
    width = round(height * PORTRAIT_SIZE[0] / PORTRAIT_SIZE[1])
    frame = Image.new('RGBA', (width, height))
    frame.paste(picture, (round(width / 2 - centre), -max(0, top - CROP_MARGIN)))
    return frame.resize(PORTRAIT_SIZE, Image.LANCZOS)


def crop_height(path):
    return CROP_HEIGHTS.get(path.split('/')[2], CROP_HEIGHT)


def png(image):
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    return out.getvalue()


class Mirror:
    """Secret in the Shadows' data, read from the mirror folder."""

    def __init__(self, root):
        self.root = Path(root)
        with open(self.root / 'bundle_names.csv', encoding='utf-8-sig', newline='') as file:
            rows = [row for row in csv.DictReader(file) if row['part'] == 'native']
        self.files = {row['real_path']: self.root / row['local_path'] for row in rows}
        self.kinds = {row['real_path']: row['kind'] for row in rows}
        self.folded = {path.lower(): path for path in self.files}
        self.json_dir = self.root / 'unpacked/resources_json'
        self.cases_dir = self.json_dir / 'cases'
        self._names = {}

    def path(self, path):
        """A bundle path as the game names it, matched case-insensitively (Rufus's `_Surprised`), or None."""
        return path if path in self.files else self.folded.get(path.lower())

    # --- cases ---------------------------------------------------------------------------------------------------------
    def cases(self):
        """[(case number, case title, [Part])] in the case list's order, case 31's unlisted parts and case 45's titles in
        (decision K)."""
        out = []
        for number, case in enumerate(load(self.cases_dir / 'caselist.json')['case_list'], 1):
            if case.get('case', number) != number:      # (cases 1 and 2 carry no number; the rest match their place)
                raise ValueError(f"case list place {number} is numbered {case['case']}")
            title, part_titles = RELEASED_TITLES.get(number, (case['title'].strip(), None))
            listed = [(episode['name'].strip(), episode['id'], True) for episode in case['episodes']]
            if part_titles:
                listed = [(name, epid, True) for name, (_, epid, _) in zip(part_titles, listed)]
            for extra in UNLISTED_PARTS.get(number, ()):
                listed.append((extra, f'ch2_epid.{number}case{len(listed) + 1}ep', False))
            parts = []
            for index, (name, epid, was_listed) in enumerate(listed, 1):
                folder = self.cases_dir / f'case{number}' / f'ep{index}'
                parts.append(Part(index, name, epid, f'case{number}/ep{index}', load(folder / 'epconfig.json'),
                                  load(folder / 'sequences.json')['sequences'], was_listed))
            out.append((number, title, parts))
        return out

    def ids(self):
        """The testing table: a row per original episode, its case, part and translated entry (pack 31900, case x 10)."""
        rows = []
        for number, title, parts in self.cases():
            for part in parts:
                rows.append(dict(epid=part.epid, folder=part.folder, case=number, case_title=title, part=part.number,
                                 parts=len(parts), listed=int(part.listed), pack=PACK_ID, episode=number * 10,
                                 title=part.title))
        return rows

    # --- portraits and looks -------------------------------------------------------------------------------------------
    def portraits(self):
        return sorted(path for path, kind in self.kinds.items() if kind == 'portrait' and not path.endswith('/template'))

    def picture_ids(self):
        """{portrait path: its lasting ID}: 28000 + its place in the sorted list, a picture with another's pixels that
        one's."""
        from PIL import Image
        ids, seen = {}, {}
        for index, path in enumerate(self.portraits()):
            with Image.open(self.files[path]) as image:
                key = hashlib.sha1(image.convert('RGBA').tobytes()).hexdigest()
            ids[path] = seen.setdefault(key, PORTRAIT_BASE + index)
        return ids

    def look_banks(self, ids=None):
        """(banks, names, faces): each look's five picture IDs (a face it lacks shows its Normal), its name, and
        {portrait path: (look, slot)}. A duplicate picture's path takes the look of the picture it repeats."""
        ids = ids or self.picture_ids()
        found = collections.defaultdict(dict)
        owner, firsts = {}, {}
        for path in self.portraits():
            key, slot = look_key(path)
            first = firsts.setdefault(ids[path], path)
            if first != path:
                owner[path] = first
                continue
            if slot in found[key]:
                # A second picture for a face (Harper's `normal` beside her `neutral`): a look of its own, as Classic's
                # extra faces are.
                key, slot = f"{key}/{path.rsplit('_', 1)[1].title()}", 0
                if key in found:
                    raise ValueError(f'two {SLOTS[slot]} faces for look {key}')
            found[key][slot] = path
        keys = sorted(found)
        banks, names, faces = [], [], {}
        for number, key in enumerate(keys):
            slots = found[key]
            fallback = slots.get(0) or slots[min(slots)]
            banks.append([ids[slots.get(slot, fallback)] for slot in range(5)])
            names.append(look_name(key))
            for slot, path in slots.items():
                faces[path] = (number, slot)
        for path, first in owner.items():
            faces[path] = faces[first]
        return banks, names, faces

    # --- scenes, music, story objects ----------------------------------------------------------------------------------
    def scene_folders(self):
        return sorted(path.split('/')[2] for path, kind in self.kinds.items() if kind == 'template')

    def scenes(self):
        """{scene folder: (backdrop ID, slice x)}: every scene's 3:4 slice centred in its 1024 x 768 backdrop."""
        return {folder: (BACKDROP_BASE + n, SLICE_X) for n, folder in enumerate(self.scene_folders())}

    def backdrop(self, folder):
        """A scene's picture for the story, 1024 x 768: its clean base (the round layout's `default` layer, the scene
        without the round's objects, as Classic's; owner 2026-11-20), else its template. A base's 1-pixel border
        (1026 x 770, 1282 x 962, 1602 x 1202) is cut before scaling."""
        from PIL import Image
        layout = self.json_dir / 'references/backgrounds' / folder / 'hd' / f'{folder}.json'
        picture = None
        if layout.exists():
            for group in load(layout)['textures']:
                if str(group['id']) == 'default':
                    for texture in group['textures']:
                        path = self.path(f"references/backgrounds/{folder}/hd/{texture['id']}")
                        if texture['width'] >= 1000 and path:
                            picture = Image.open(self.files[path]).convert('RGB')
                            break
                    break
        if picture is None:
            picture = Image.open(self.files[f'references/backgrounds/{folder}/hd/template']).convert('RGB')
        width, height = picture.size
        if width % 4 == 2:                                   # (a base's border)
            picture = picture.crop((1, 1, width - 1, height - 1))
        return picture.resize(BACKDROP_SIZE, Image.LANCZOS) if picture.size != BACKDROP_SIZE else picture

    def tracks(self):
        """{track stem: (music ID, the OGG's path)}."""
        prefix = 'references/music/ogg/'
        stems = sorted(path[len(prefix):] for path in self.files if path.startswith(prefix))
        return {stem: (MUSIC_BASE + n, self.files[prefix + stem]) for n, stem in enumerate(stems)}

    def story_object_ids(self):
        """{photo path: its ID}: the 253 story-object pictures, then the 5 round sprites (`..._found`) photos show."""
        if getattr(self, '_photos', None) is None:
            paths = sorted(path for path, kind in self.kinds.items() if kind == 'storyobj')
            sprites = set()
            for _, _, parts in self.cases():
                for part in parts:
                    for chapter in part.config['sceneRefs'].values():
                        sprites.update(path for path in (chapter.get('dialogStoryObjects') or {}).values()
                                       if path and self.kinds.get(path) != 'storyobj')
            self._photos = {path: STORY_OBJECT_BASE + n for n, path in enumerate(paths + sorted(sprites))}
        return self._photos

    def scene_items(self, scene):
        """A round scene's hidden objects as names.json gives them: [{'normal', 'found', 'name'}]."""
        if scene not in self._names:
            path = self.json_dir / 'references/backgrounds' / scene / 'names.json'
            self._names[scene] = load(path)['names'] if path.exists() else []
        return self._names[scene]

    def round_items(self, entry):
        """A round's story-object list (its `hogScene` entry) resolved to the scene's items, by name first, then as the
        game matches (a substring of a sprite; ENGINE 5.2), then a name inside the entry: [(entry, item or None)]."""
        listed = entry.get('storyobject')
        if not listed:
            return []
        names = self.scene_items(entry['scene'])
        out = []
        for value in [listed] if isinstance(listed, str) else listed:
            base = norm(re.sub(r'\s*[\[\(].*$', '', value).strip())
            if not base or base in NOTHING:
                continue
            hit = [e for e in names if norm(e['name']) == base] or \
                  [e for e in names if base in norm(e.get('normal', ''))] or \
                  [e for e in names if norm(e['name']) and norm(e['name']) in base]
            out.append((value, hit[0] if hit else None))
        return out

    def round_entry(self, config, chapter, round_id):
        """The `hogScene` entry for `round_id`: in the chapter before it, else any chapter's (driver.runConfig's fix)."""
        for name in [chapter] + sorted(config['sceneRefs']):
            entry = config['sceneRefs'].get(name, {}).get('backgrounds', {}).get(round_id)
            if entry and entry.get('type') == 'hogScene':
                return entry
        return None


class Stage:
    """The faces on stage in one chapter (module doc): {stage id in lower case: (its character entry, the face's path)}."""

    def __init__(self, refs, log):
        self.refs, self.log, self.on = refs, log, {}

    def character(self, ref):
        entry = self.refs.get(ref)
        if not isinstance(entry, dict) or 'expressions' not in entry:
            entry = self.refs.get(str(ref).lower())
        return entry if isinstance(entry, dict) and 'expressions' in entry else None

    def step(self, node):
        kind = node['type'] if node['type'] != 'event' else node['eventtype']
        if kind == 'stageBlockIntro':
            entry = self.character(node['ref'])
            if entry is not None:
                faces = entry['expressions']
                self.on[node['id'].lower()] = (entry, faces.get(node.get('expression') or 'default') or faces['default'])
        elif kind == 'stageBlockExpressionChange':
            entry = self.refs.get(node['ref'])               # (the game's exact key)
            held = self.on.get(node['id'].lower())
            if held is None:
                self.log['face changes for someone off stage (ignored)'] += 1
            elif not isinstance(entry, dict) or not entry.get('expressions', {}).get(node.get('expression') or 'default'):
                self.log['face changes to a face they lack (face kept)'] += 1
            else:
                self.on[node['id'].lower()] = (held[0], entry['expressions'][node.get('expression') or 'default'])
        elif kind == 'stageBlockOutro':
            self.on.pop(node['id'].lower(), None)
        elif kind == 'clearStage':
            self.on.clear()

    def speaker(self, line):
        """Whom a line lights: its `narrator`, else Claire for an empty header, else the header; a narrator nobody in
        the chapter is called (`Happy`, `Clare`) is Claire."""
        header, narrator = line.get('header', ''), line.get('narrator') or ''
        if narrator and self.character(narrator) is None and narrator.lower() not in self.on:
            self.log['narrators that name nobody (Claire)'] += 1
            narrator = 'Claire'
        return narrator or ('Claire' if header == '' else header)

    def face(self, line):
        """(speaker, the face path the line shows, or None for no portrait): a speaker line's own `expression` field
        where it names a face (where the game's stage went wrong, case 40 ep 1's empty stage and case 9's failed
        Halloween change, it has the face meant), else the speaker's face on stage, else their `default`; narration
        by Claire in a chapter that doesn't load her shows her Normal."""
        who = self.speaker(line)
        held = self.on.get(who.lower())
        field = line.get('expression')
        if line.get('header') and field is not None:
            entry = self.character(line['header'])
            path = entry['expressions'].get(field or 'default') if entry else None
            if path:
                if held is None or held[1] != path:
                    self.log['speaker lines whose field differs from the stage (field shown)'] += 1
                return who, path
        if held is not None:
            return who, held[1]
        entry = self.character(who)
        if entry is not None:
            self.log['lines whose speaker is off stage (default face)'] += 1
            return who, entry['expressions'].get('default')
        if who.lower() == 'claire':
            self.log["Claire's narration in a chapter without her (her Normal)"] += 1
            return who, CLAIRE
        self.log['lines with nobody to show'] += 1
        return who, None


def faces_census(mirror, art=None, rows=None):
    """Every line's face by the tracker, checked against the lines' own `expression` fields: a Counter (and, given
    `rows`, a row per line: folder, chapter, speaker, header, field, path, look, slot)."""
    _, names, faces = art or mirror.look_banks()
    log = collections.Counter()
    for _, _, parts in mirror.cases():
        for part in parts:
            for chapter, _ in chapters_of(part.sequences):
                refs = refs_for(part.config['sceneRefs'][chapter])
                stage = Stage(refs, log)
                for node in part.sequences[chapter]['nodes']:
                    if node['type'] != 'dialogText':
                        stage.step(node)
                        continue
                    who, path = stage.face(node)
                    real = mirror.path(path) if path else None
                    if path and real != path:
                        log['face paths in another case (resolved)' if real else 'face paths not in the bundle'] += 1
                    look, slot = faces.get(real, (None, None))
                    field = node.get('expression')
                    if node['header']:
                        log['speaker lines with a field' if field is not None else 'speaker lines without a field (tracker)'] += 1
                    else:
                        log['narration lines'] += 1
                    log['lines with a portrait' if look is not None else 'lines without a portrait'] += 1
                    if rows is not None:
                        rows.append((part.folder, chapter, who, node['header'], field or '', real or '',
                                     names[look] if look is not None else '', SLOTS[slot] if slot is not None else ''))
    return log


# --- story-object names (decision L) --------------------------------------------------------------------------------
def story_object_names(mirror):
    """[(folder, chapter, object id, picture path, name, how)]: each photo named from the round before it (its forced
    list resolved, the photo's `_n` choosing the entry), a photo of a round's `_found` sprite by that item; '' where
    neither gives one (the owner's list)."""
    out = []
    for _, _, parts in mirror.cases():
        for part in parts:
            before = None
            for chapter, round_id in chapters_of(part.sequences):
                refs = refs_for(part.config['sceneRefs'][chapter])
                shown = refs.get('dialogStoryObjects') or {}
                for node in part.sequences[chapter]['nodes']:
                    if node.get('eventtype') != 'showStoryObject':
                        continue
                    picture = shown.get(node['id'], '')
                    stem = picture.rsplit('/', 1)[-1]
                    name, how = '', 'by hand'
                    if stem.endswith('_found'):
                        scene, sprite = picture.split('/')[2], re.sub(r'^\d+_', '', stem)     # (its layer prefix)
                        item = next((e for e in mirror.scene_items(scene) if sprite in (e['found'], e.get('normal', '')
                                     .replace('_normal', '_found'))), None)
                        if item is None and sprite.startswith('component_object_completed_'):
                            whole = sprite[len('component_object_completed_'):]
                            item = next((e for e in mirror.scene_items(scene) if whole in (e['found'], e.get('normal'))), None)
                        if item:
                            name, how = item['name'], 'its round sprite'
                    elif before:
                        resolved = [item for _, item in before if item is not None]
                        index = re.search(r'_(\d+)$', stem)
                        index = int(index.group(1)) if index else 0
                        if len(before) > index and before[index][1] is not None:
                            name, how = before[index][1]['name'], f'round list entry {index + 1}'
                        elif resolved:
                            name, how = resolved[0]['name'], 'round list, first found'
                        elif before:
                            name, how = '', f'round list unresolved ({", ".join(v for v, _ in before)})'
                    if not name and stem in HAND_NAMES:
                        name, how = HAND_NAMES[stem], f'by hand; {how}'
                    name = name.strip()
                    out.append((part.folder, chapter, node['id'], picture, name[:1].upper() + name[1:], how))
                entry = mirror.round_entry(part.config, chapter, round_id) if round_id else None
                before = mirror.round_items(entry) if entry else None
    return out


# --- the add-on ---------------------------------------------------------------------------------------------------------
def spec(mirror, art=None):
    banks, names, faces = art or mirror.look_banks()
    ids = mirror.picture_ids()
    return {'version': SPEC_VERSION, 'looks': banks, 'look_names': names,
            'pictures': {path: [*faces[path], ident] for path, ident in ids.items()},
            'scenes': {folder: [ident, x] for folder, (ident, x) in mirror.scenes().items()},
            'music': {stem: ident for stem, (ident, _) in mirror.tracks().items()},
            'story_objects': mirror.story_object_ids()}


def addon(mirror, progress=print):
    """ch2's resources {ID: bytes} and a report (module doc)."""
    from PIL import Image
    from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes
    if shutil.which('ffmpeg') is None:
        raise SystemExit('FFmpeg is needed for the tracks')
    resources = {}
    ids = mirror.picture_ids()
    for path, ident in ids.items():
        if ident not in resources:
            with Image.open(mirror.files[path]) as image:
                resources[ident] = png(portrait_crop(image.convert('RGBA'), crop_height(path)))
    progress(f'portraits: {len(resources)} pictures for {len(ids)} paths')
    scenes = mirror.scenes()
    for n, (folder, (ident, _)) in enumerate(scenes.items(), 1):
        resources[ident] = png(mirror.backdrop(folder))
        if n % 50 == 0:
            progress(f'backdrops: {n} of {len(scenes)}')
    for path, ident in mirror.story_object_ids().items():
        resources[ident] = mirror.files[path].read_bytes()
    tracks = mirror.tracks()
    with tempfile.TemporaryDirectory() as folder:
        for stem, (ident, ogg) in tracks.items():
            resources[ident] = mp3(ogg, folder)
    progress(f'tracks: {len(tracks)}')
    with Image.open(mirror.files[FRAME_ART]) as image:
        resources[FRAME_BACKDROP] = png(image.convert('RGB'))
    art = mirror.look_banks(ids)
    resources[SPEC] = json.dumps(spec(mirror, art), separators=(',', ':')).encode('utf-8')
    resources[ADDON_RECORD] = provides_bytes(ADDON_ID, ADDON_TITLE, ADDON_REVISION)
    report = dict(portraits=len(ids), pictures=len(set(ids.values())), looks=len(art[0]), backdrops=len(scenes),
                  tracks=len(tracks), story_objects=len(mirror.story_object_ids()), resources=len(resources))
    return resources, report


# --- review sheets ----------------------------------------------------------------------------------------------------
def portrait_sheet(mirror, out, classic=None):
    """Every look's five faces as CoD will show them (the crop rule), a row a look, Classic's same person beside the first
    where its mirror (`classic`) has them, for the owner to judge the rule."""
    from PIL import Image, ImageDraw
    banks, names, faces = mirror.look_banks()
    by_id = {}
    for path, ident in mirror.picture_ids().items():
        by_id.setdefault(ident, path)
    cell, label = (110, 120), 150
    rows = len(banks)
    columns = 2
    per = (rows + columns - 1) // columns
    width = label + cell[0] * 6 + 20
    sheet = Image.new('RGB', (width * columns, per * (cell[1] + 6) + 30), (52, 52, 60))
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 8), f'Secret in the Shadows: {rows} looks cropped for CoD (window {CROP_HEIGHT} px from {CROP_MARGIN} '
              f'above the head, centred on it); last column: Classic\'s portrait of the same person, where one exists',
              fill=(230, 230, 230))
    classic_faces = {}
    if classic is not None:
        with open(Path(classic) / 'bundle_names.csv', encoding='utf-8-sig', newline='') as file:
            for row in csv.DictReader(file):
                if row['kind'] == 'portrait' and row['part'] == 'native' and row['real_path'].endswith('_Normal'):
                    key = norm(row['real_path'].split('/')[2])
                    if key not in classic_faces or len(row['real_path']) < len(classic_faces[key][0]):
                        classic_faces[key] = (row['real_path'], Path(classic) / row['local_path'])   # (the plainest)
    for n, (bank, name) in enumerate(zip(banks, names)):
        x0, y0 = (n // per) * width, 30 + (n % per) * (cell[1] + 6)
        draw.text((x0 + 6, y0 + 50), name[:22], fill=(230, 230, 230))
        for slot, ident in enumerate(bank):
            with Image.open(mirror.files[by_id[ident]]) as image:
                face = portrait_crop(image.convert('RGBA'), crop_height(by_id[ident])).resize(cell, Image.LANCZOS)
            tile = Image.new('RGB', cell, (90, 90, 100))
            tile.paste(face, (0, 0), face)
            sheet.paste(tile, (x0 + label + slot * cell[0], y0))
        match = classic_faces.get(norm(name.replace(' ', '')))
        if match:
            with Image.open(match[1]) as image:
                face = image.convert('RGBA').resize(cell, Image.LANCZOS)
            tile = Image.new('RGB', cell, (70, 90, 70))
            tile.paste(face, (0, 0), face)
            sheet.paste(tile, (x0 + label + 5 * cell[0] + 10, y0))
    sheet.save(out)
    return rows


def names_sheet(mirror, rows, out):
    """Every photo with the name it gets and its episode, for the owner's review: a name from the round list in white,
    one by hand in yellow, none in red."""
    from PIL import Image, ImageDraw
    cell = (160, 150)
    columns = 10
    sheet = Image.new('RGB', (cell[0] * columns, cell[1] * ((len(rows) + columns - 1) // columns) + 10), (52, 52, 60))
    draw = ImageDraw.Draw(sheet)
    for n, (folder, chapter, _, picture, name, how) in enumerate(rows):
        x, y = (n % columns) * cell[0], (n // columns) * cell[1]
        with Image.open(mirror.files[picture]) as image:
            image = image.convert('RGBA')
            image.thumbnail((cell[0] - 16, cell[1] - 40))
        tile = Image.new('RGB', image.size, (90, 90, 100))
        tile.paste(image, (0, 0), image)
        sheet.paste(tile, (x + 8 + (cell[0] - 16 - image.width) // 2, y + 6))
        colour = (255, 110, 110) if not name else (255, 220, 90) if how.startswith('by hand') else (240, 240, 240)
        draw.text((x + 8, y + cell[1] - 32), (name or '(no name)')[:24], fill=colour)
        draw.text((x + 8, y + cell[1] - 18), f'{n + 1}. {folder} {chapter.replace("SCENE ", "ch ")}', fill=(170, 170, 170))
    sheet.save(out)
    return sum(1 for row in rows if not row[4])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('report', 'ids', 'faces', 'portraits', 'names', 'addon'):
        command = commands.add_parser(name)
        command.add_argument('--mirror', type=Path, required=True)
        command.add_argument('--out', type=Path, required=name in ('ids', 'names', 'addon'))
        if name in ('portraits', 'names'):
            command.add_argument('--sheet', type=Path, required=name == 'portraits')
        if name == 'portraits':
            command.add_argument('--classic', type=Path, help="Classic's mirror, for its portraits beside the sequel's")
    args = parser.parse_args(argv)
    mirror = Mirror(args.mirror)
    if args.command == 'report':
        cases = mirror.cases()
        banks, _, faces = mirror.look_banks()
        ids = mirror.picture_ids()
        chapters = [chapters_of(part.sequences) for _, _, parts in cases for part in parts]
        print(f'cases {len(cases)}, episodes {sum(len(parts) for _, _, parts in cases)} '
              f'(unlisted {sum(not p.listed for _, _, parts in cases for p in parts)}), chapters '
              f'{sum(len(c) for c in chapters)}, rounds {sum(1 for c in chapters for _, r in c if r)}')
        print(f'chapter id schemes: {dict(collections.Counter(c[0][0].split("_")[0] if "_" in c[0][0] else "SCENE n" for c in chapters))}')
        print(f'portraits {len(ids)} ({len(set(ids.values()))} pictures), looks {len(banks)}')
        print(f'scenes {len(mirror.scenes())}, tracks {len(mirror.tracks())}, story objects {len(mirror.story_object_ids())}')
    elif args.command == 'ids':
        rows = mirror.ids()
        with open(args.out, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        print(f'{len(rows)} episodes in {len({row["case"] for row in rows})} cases -> {args.out}')
    elif args.command == 'faces':
        rows = [] if args.out else None
        log = faces_census(mirror, rows=rows)
        for key, value in sorted(log.items()):
            print(f'  {key}: {value}')
        if rows is not None:
            with open(args.out, 'w', encoding='utf-8', newline='\n') as file:
                file.write('folder\tchapter\tspeaker\theader\tfield\tpath\tlook\tslot\n')
                file.writelines('\t'.join(row) + '\n' for row in rows)
    elif args.command == 'portraits':
        print(f'{portrait_sheet(mirror, args.sheet, args.classic)} looks -> {args.sheet}')
    elif args.command == 'names':
        rows = story_object_names(mirror)
        hows = collections.Counter(re.sub(r' \(.*', '', re.sub(r'\d+', 'n', how)) for *_, how in rows)
        markdown_table(args.out, 'Secret in the Shadows: story-object photo names',
                       'Each photo is named for players without the picture display (decision L): from the round '
                       'before it, its forced list resolved to the scene\'s item; the rest need a name by hand. '
                       f'{len(rows)} photos shown: {dict(hows)}.',
                       ('Episode', 'Chapter', 'Object', 'Picture', 'Name', 'From'), rows)
        if args.sheet:
            print(f'{len(rows)} photos, {names_sheet(mirror, rows, args.sheet)} without a name -> {args.sheet}')
        print(f'{len(rows)} photos -> {args.out}: {dict(hows)}')
    else:
        from exp_runtime.exp import encode_exp
        resources, report = addon(mirror)
        args.out.mkdir(parents=True, exist_ok=True)
        data = encode_exp(resources)
        (args.out / 'CH_Shadows.exp').write_bytes(data)
        print(f'addon: {ADDON_TITLE!r} -> {args.out / "CH_Shadows.exp"} ({len(data) // 2 ** 20} MB), {report}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
