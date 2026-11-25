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
    26940        the journal's cue, DS_Call_Attention (MP3)
    26998        the spec, JSON: looks, look names, pictures, scenes and slices, tracks, story objects (as chc's)
    26999        the frame backdrop beside CoD's frame (the episode selector's own backdrop)
    27000-27257  the story-object photos, their original PNGs: the 253 pictures, then the 5 round sprites photos show
    28000-28417  the portraits, cropped (above), at 28000 + their place in the sorted list (a duplicate takes the first's)
    29100-29108  revision 2: Secret in the Shadows UI, the dialogue skin's spec and pieces (ch2_dialogue_skin.py), and
    29190-29192  its faces, Roboto Condensed, Roboto Slab Bold and Roboto Condensed Italic
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
ADDON_ID, ADDON_TITLE, ADDON_REVISION = 'ch2', 'Claire Hart: Secret in the Shadows', 2     # (2: S2b's skin, 29100 on)
# The ch2 revision the cases need: 1. Revision 2 adds only the skin, which the player draws when it finds it (as chc's 2).
CASES_NEED_CH2 = 1
TITLE_TAG = ' (CH2)'
SLOTS = ('Normal', 'Angry', 'Happy', 'Sad', 'Surprised')
FACE_SLOTS = {'normal': 0, 'neutral': 0, 'angry': 1, 'happy': 2, 'sad': 3, 'surprised': 4}
BACKDROP_BASE, MUSIC_BASE, STORY_OBJECT_BASE, PORTRAIT_BASE = 26000, 26900, 27000, 28000
SPEC, FRAME_BACKDROP, SPEC_VERSION = 26998, 26999, 1
JOURNAL_SOUND = 26940                        # DS_Call_Attention, the journal's cue (decision J)
STORY_VERSION = 1                            # the cases' version (episode_version.py)
LOOK_BANK_BASE = 30000                       # cod/profile.py LOOK_BANKS[31900]: look n is 30000 + 5n on
FRAME_ART = 'textures/SD/episodeSelector/episodeselector_bg'
JOURNAL_CUE = 'references/gamesfx/ogg/Claire_Hart_2_DS_Call_Attention'
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


# --- the converter: a case as a Creator project (plan Stage S2) -------------------------------------------------------
# Decision J (owner, 2026-11-24): the case journal is the pause menu's, its notes grouped by part; each unlock adds the
# data's new entry and says so in a narration box without a portrait, with the game's own cue.
JOURNAL_NOTICE = 'Your case journal has been updated. Pause to view it.'
JOURNAL_TEXT = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '…': '...',
                              '–': '-', '—': '-', ' ': ' ', 'а': 'a', '\r': ''})


def journal_text(body):
    """A journal entry's text by the text rules (story_text's), its paragraphs kept a line each."""
    return '\n'.join(' '.join(line.translate(JOURNAL_TEXT).split()) for line in body.split('\n') if line.strip())


# A later part's opening: its player's introduction and the self-description after it ("I'm Harper. I'm a grad student in
# the San Francisco Bay Area. I also have an unusual ability..."), which goes as Classic's does (owner, 2026-11-20).
SELF = re.compile(r"^(I'm|I am|I also|I have|And I)\b")
# Round places the data spells oddly (case 31's run-together names), as said.
PLACES = {'ItoGuest': 'Ito Guest Room', 'ZooGiftshop': 'Zoo Gift Shop', 'BoomboxxInterior': 'BoomBoxx',
          'BoomBoxxExterior': 'BoomBoxx entrance'}


def trim_intro(text):
    """claire_hart.trim_intro, and every self-description sentence after the introduction."""
    from claire_hart import ABBREVIATION, INTRO
    marked = ABBREVIATION.sub(lambda match: match.group(1) + '.\0', text)
    sentences = [sentence.replace('\0', ' ') for sentence in re.split(r'(?<=[.!?])\s+', marked)]
    if not INTRO.match(sentences[0]):
        return text
    rest = sentences[1:]
    while rest and SELF.match(rest[0]):
        rest = rest[1:]
    return ' '.join(rest).strip()


def place_name(name, look_names):
    """A round's place as a line says it: the data's `location`, a run-together one spaced, a first name of the cast
    possessive ('HarpersLivingRoom' -> "Harper's Living Room")."""
    if name.strip() in PLACES:
        return PLACES[name.strip()]
    name = name.strip()
    if ' ' not in name:
        name = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)
    firsts = {look.split()[0] for look in look_names}
    words = [word[:-1] + "'s" if word.endswith('s') and word[:-1] in firsts else word for word in name.split()]
    return ' '.join(words)


def journal_queue(part):
    """[(chapter, entry text)]: the part's new journal entries in chapter order (an entry once; ENGINE 4.6)."""
    out, seen = [], set()
    for chapter, _ in chapters_of(part.sequences):
        for entry in part.config['sceneRefs'][chapter].get('journal') or []:
            text = journal_text(entry.get('body', ''))
            if not entry.get('pastEntry') and text and text not in seen:
                seen.add(text)
                out.append((chapter, text))
    return out


def player_folder(mirror, part):
    """The portrait folder of a part's player: whom its narration shows most (Claire, Harper, Troy, Sara...)."""
    folders = collections.Counter()
    log = collections.Counter()
    for chapter, _ in chapters_of(part.sequences):
        stage = Stage(refs_for(part.config['sceneRefs'][chapter]), log)
        for node in part.sequences[chapter]['nodes']:
            if node['type'] != 'dialogText':
                stage.step(node)
            elif node['header'] == '':
                path = mirror.path(stage.face(node)[1] or '')
                if path:
                    folders[path.split('/')[2]] += 1
    return folders.most_common(1)[0][0] if folders else 'Avatar_ClaireHart'


def make_builder():
    """ShadowsBuilder, made on first use (Classic's CaseBuilder needs the Creator)."""
    from claire_hart import CaseBuilder, plate_name

    class ShadowsBuilder(CaseBuilder):
        """One case's nodes, characters and assets: Classic's builder with the sequel's stage, music, photos and journal."""

        def __init__(self, mirror, art, names):
            super().__init__(mirror, art)
            self.names = names              # (folder, chapter, object id) -> the photo's name (decision L)
            self.queue = []                 # the part's journal entries still to unlock: [(chapter, text)]
            self.notes = []                 # the part's entries unlocked so far
            self.quest = (0, '')            # the part's journal number and title
            self.log = collections.Counter()

        def asset(self, ident, name):
            self.assets.setdefault(ident, self.Asset(ident, name, None, ADDON_ID))

        def unlock(self, count=1):
            """`count` journal entries in (decision J): the part's journal page rewritten, then the notice."""
            taken = [self.queue.pop(0)[1] for _ in range(min(count, len(self.queue)))]
            if not taken:
                self.log['journal unlocks with nothing left to add (skipped)'] += 1
                return
            self.notes += taken
            number, title = self.quest
            self.add('quest', text='\n\n'.join(self.notes), params={'number': number, 'title': title})
            self.add('speakers', params={'player': self.player or '', 'narrator': ''})    # (narration without a portrait)
            self.asset(JOURNAL_SOUND, 'journal cue')
            self.add('sound', params={'resource': JOURNAL_SOUND})
            self.add(text=JOURNAL_NOTICE, expression=0)
            self.cast = (self.player, None)     # (the next line says who's who again)
            self.report['journal entries'] += len(taken)
            self.report['journal notices'] += 1

        def chapter(self, mirror, part, chapter, last=False, reintroduced=False):
            """A chapter's nodes in order (ENGINE 4.2): its lines with the stage's faces, backdrops, music from its own
            map, photos and journal unlocks. In a part's `last` chapter its sign-off goes; a `reintroduced` player's first
            line loses the introduction (claire_hart's trims)."""
            from claire_hart import UPSELL, trim_outro
            refs = refs_for(part.config['sceneRefs'][chapter])
            stage = Stage(refs, self.log)
            for node in part.sequences[chapter]['nodes']:
                kind = node['type'] if node['type'] != 'event' else node['eventtype']
                if kind == 'dialogText':
                    text = story_text(node['body'])
                    if not text:
                        self.log['blank lines (the game shows an empty box; dropped)'] += 1
                        continue
                    if reintroduced:
                        reintroduced = False
                        kept = trim_intro(text)
                        if kept != text:
                            self.reviews['intros'].append((part.epid, text, kept))
                            if not kept:
                                continue
                            text = kept
                    if last and UPSELL.search(text):
                        kept = trim_outro(text)
                        self.reviews['outros'].append((part.epid, text, kept))
                        if not kept:
                            continue
                        text = kept
                    _, path = stage.face(node)
                    path = mirror.path(path) if path else None
                    if node['header'] == '':
                        if path in self.art['faces']:
                            self.add(text=text, expression=self.narrate(path))
                        else:
                            self.narrate_as_player()
                            self.add(text=text, expression=0)
                        self.report['narration'] += 1
                    elif path in self.art['faces']:
                        cid, slot = self.speaker(node['header'], path)
                        self.add(text=text, character=cid, expression=slot)
                        self.report['speaker lines'] += 1
                    else:
                        self.add(text=text, speaker=plate_name(node['header']))
                        self.report['speaker lines without a portrait'] += 1
                elif kind == 'stageBlockIntro':
                    entry = refs.get(node['ref']) or refs.get(str(node['ref']).lower())
                    if isinstance(entry, dict) and entry.get('type') == 'texture':
                        self.add('background', asset=self.scene(entry['resource'].split('/')[2]))
                        self.report['backdrops'] += 1
                    else:
                        stage.step(node)
                elif kind in ('stageBlockExpressionChange', 'stageBlockOutro', 'clearStage'):
                    stage.step(node)
                elif kind == 'playMusic':
                    # audioPlayer: the chapter's own map only; no track (`FILL THIS IN`) keeps the one playing; a found
                    # one always restarts.
                    track = (refs.get('music') or {}).get(node['id'])
                    if not track or '/' not in track:
                        self.report['music ids missing (track kept)'] += 1
                        continue
                    ident = self.art['music'][track.rsplit('/', 1)[1].rsplit('.', 1)[0]]
                    self.asset(ident, track)
                    self.add('music', params={'resource': ident, 'loop': True})
                elif kind == 'showStoryObject':
                    picture = (refs.get('dialogStoryObjects') or {}).get(node['id'])
                    ident = self.art['story_objects'][picture]
                    self.asset(ident, picture.rsplit('/', 1)[1])
                    self.add('story_object', text=self.names.get((part.folder, chapter, node['id']), ''), asset=ident)
                    self.report['story objects'] += 1
                elif kind == 'animateJournalIcon':
                    self.unlock()
                elif kind == 'dialogIntro':
                    continue                # (the box comes with a line)
                else:
                    raise ValueError(f'{part.epid}: a node this converter doesn\'t know: {kind}')
            # An entry the chapter adds without an unlock (3 chapters, ENGINE 4.6) comes in at its end (decision J: the
            # journal follows its data's entries).
            left = sum(1 for held, _ in self.queue if held == chapter)
            if left:
                self.log['journal entries added at their chapter\'s end'] += left
                self.unlock(left)

        def stand_in(self, mirror, part, chapter, round_id, next_chapter):
            """A round with the real rounds off (S3 brings them): a line naming what the player finds (G, G2), unless the
            next chapter's first two lines tell it (claire_hart.round_told)."""
            from claire_hart import first_name, round_line, round_told
            entry = mirror.round_entry(part.config, chapter, round_id) or {}
            items = []
            for _, item in mirror.round_items(entry) if entry else ():
                if item is not None and item['name'] not in items:
                    items.append(item['name'])
            lines, shown = [], []
            for node in part.sequences[next_chapter]['nodes']:
                if node['type'] == 'dialogText':
                    lines.append(story_text(node['body']))
                    if len(lines) == 2:
                        break
                elif node.get('eventtype') == 'showStoryObject':
                    shown.append(self.names.get((part.folder, next_chapter, node['id']), ''))
            told = round_told(lines, items + [s for s in shown if s], shown=bool(shown))
            scene = entry.get('scene') or part.config['hogConfig'][round_id]['scene']
            where = place_name(entry.get('location') or scene.replace('_HO', ''), self.art['look_names'])
            line = round_line(where, items, first_name(re.sub(r'^Avat[ao]r_', '', self.player_folder)))
            self.reviews['rounds'].append((part.epid, round_id, where, ', '.join(items), told or 'stand-in', line,
                                           ' / '.join(lines)[:220]))
            self.report['rounds'] += 1
            if told:
                self.report['rounds told by the next chapter'] += 1
            else:
                self.add('background', asset=self.scene(scene))
                self.narrate_as_player()
                self.add(text=line, expression=0)
                self.report['round lines'] += 1
            self.cast = (None, None)

    return ShadowsBuilder


def converter_art(mirror, cache=None):
    """What convert reads: the look table, scenes, tracks, photos and their names, and the parts' title-card scenes."""
    banks, names, faces = mirror.look_banks()
    return dict(looks=banks, look_names=names, faces=faces, scenes=mirror.scenes(), own_scenes=set(),
                music={stem: ident for stem, (ident, _) in mirror.tracks().items()},
                story_objects=mirror.story_object_ids(), store=store_scenes(mirror, cache),
                names={(folder, chapter, key): name for folder, chapter, key, _, name, _ in story_object_names(mirror)})


def store_scenes(mirror, cache=None):
    """{part folder: scene folder}: the scene each part's store picture shows (a template shrunk; as Classic's title cards,
    decision N2), else the part's first backdrop (case 31's unlisted parts and case 45 have no picture)."""
    if cache is not None and Path(cache).exists():
        return json.loads(Path(cache).read_text(encoding='utf-8'))
    import numpy as np
    from PIL import Image

    def vector(image):
        pixels = np.asarray(image.convert('L').resize((64, 48), Image.BILINEAR), dtype=float)
        pixels -= pixels.mean()
        return (pixels / (np.linalg.norm(pixels) + 1e-9)).ravel()
    folders = mirror.scene_folders()
    table = np.stack([vector(Image.open(mirror.files[f'references/backgrounds/{f}/hd/template'])) for f in folders])
    thumbnails = {}
    for number, case in enumerate(load(mirror.cases_dir / 'caselist.json')['case_list'], 1):
        for index, episode in enumerate(case['episodes'], 1):
            thumbnails[f'case{number}/ep{index}'] = episode.get('thumbnail', '')
    out = {}
    for _, _, parts in mirror.cases():
        for part in parts:
            picture = mirror.path(thumbnails.get(part.folder, '') if part.listed else '')
            if picture:
                scores = table @ vector(Image.open(mirror.files[picture]))
                best = int(scores.argmax())
                if scores[best] >= 0.9:
                    out[part.folder] = folders[best]
                    continue
            first = chapters_of(part.sequences)[0][0]
            refs = refs_for(part.config['sceneRefs'][first])
            backdrop = next((refs.get(n['ref']) or refs.get(str(n['ref']).lower()) for n in part.sequences[first]['nodes']
                             if n['type'] == 'stageBlockIntro' and (refs.get(n['ref']) or refs.get(str(n['ref']).lower()) or
                                                                     {}).get('type') == 'texture'), None)
            out[part.folder] = backdrop['resource'].split('/')[2]
    if cache is not None:
        Path(cache).write_text(json.dumps(out, indent=1, sort_keys=True), encoding='utf-8')
    return out


def convert(mirror, art, number, title, parts):
    """A case as (a Creator Project for Cause of Death, its backdrop slices, a report): its parts in order, each opened by
    a title card over its store picture's scene (N, N2), its chapters, and each round as a stand-in line (G)."""
    from exp_runtime.creator import Project
    builder = make_builder()(mirror, art, art['names'])
    title = story_text(title)
    for part in parts:
        # The part's title over the case's, as Classic's cards (owner, 2026-11-20).
        builder.add('title', text=story_text(part.title), params={
            'subtitle': title, 'background': builder.scene(art['store'][part.folder]), 'flag': 0})
        player = player_folder(mirror, part)
        again = player == builder.player_folder and part.number > 1
        builder.play_as(player)
        builder.queue, builder.notes = journal_queue(part), []
        builder.quest = (part.number - 1, (f'Part {part.number}: {story_text(part.title)}' if len(parts) > 1
                                           else story_text(part.title))[:80])
        order = chapters_of(part.sequences)
        for k, (chapter, round_id) in enumerate(order):
            builder.chapter(mirror, part, chapter, last=k == len(order) - 1, reintroduced=again and k == 0)
            if round_id:
                builder.stand_in(mirror, part, chapter, round_id, order[k + 1][0])
        builder.log['journal entries never unlocked'] += len(builder.queue)
    builder.add('end')
    project = Project(title=title + TITLE_TAG, game='cod', pack_id=PACK_ID, episode_id=number * 10,
                      episode_version=STORY_VERSION, nodes=builder.nodes)
    project.addons = [dict(id=ADDON_ID, revision=CASES_NEED_CH2)]
    project.assets = [builder.assets[ident] for ident in sorted(builder.assets)]
    project.characters = list(builder.characters.values())
    project.start = builder.nodes[0].id
    for i, node in enumerate(project.nodes):
        node.x, node.y = 40 + 320 * (i % 12), 80 + 140 * (i // 12)
    builder.report.update(builder.log)
    builder.report['parts'] = len(parts)
    builder.report.reviews = builder.reviews
    return project, builder.slices, builder.report


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
        resources[JOURNAL_SOUND] = mp3(mirror.files[JOURNAL_CUE], folder)
    progress(f'tracks: {len(tracks)}')
    with Image.open(mirror.files[FRAME_ART]) as image:
        resources[FRAME_BACKDROP] = png(image.convert('RGB'))
    art = mirror.look_banks(ids)
    resources[SPEC] = json.dumps(spec(mirror, art), separators=(',', ':')).encode('utf-8')
    import ch2_dialogue_skin
    resources.update(ch2_dialogue_skin.build(mirror.root))          # (revision 2: Secret in the Shadows UI)
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


def write_reviews(folder, reviews):
    """The owner's lists, as Classic's: every round's stand-in line or why the next chapter tells it, and the sign-offs
    and later parts' introductions trimmed."""
    folder = Path(folder)
    rounds = reviews['rounds']
    markdown_table(folder / 'rounds.md', 'Secret in the Shadows: rounds as lines',
                   "With the real rounds off (until S3), a round is one stand-in line, unless the next chapter's first two "
                   f'lines already tell the search. {sum(1 for row in rounds if row[4] == "stand-in")} of {len(rounds)} keep '
                   'their line.', ('Episode', 'Round', 'Place', 'Finds', 'Decision', 'Stand-in line', 'Next chapter opens'),
                   rounds)
    for name, title in (('outros', 'episode-end sign-offs'), ('intros', "later parts' introductions")):
        rows = reviews[name]
        markdown_table(folder / f'{name}.md', f'Secret in the Shadows: {title}',
                       f'{sum(1 for row in rows if not row[2])} of {len(rows)} lines go whole; the rest keep their story.',
                       ('Episode', 'Line', 'Kept (blank: the line goes)'), rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('report', 'ids', 'faces', 'portraits', 'names', 'addon', 'build', 'rounds'):
        command = commands.add_parser(name)
        command.add_argument('--mirror', type=Path, required=True)
        command.add_argument('--out', type=Path, required=name in ('ids', 'names', 'addon', 'build', 'rounds'))
        if name == 'rounds':
            command.add_argument('--scenes', help='only these scene folders (a check build)')
            command.add_argument('--workers', type=int, default=3)
        if name == 'build':
            command.add_argument('--cases', help='only these case numbers (1,2,31)')
            command.add_argument('--cache', type=Path, help='the store pictures matched (made on first use)')
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
    elif args.command == 'rounds':
        import claire_hart_shadows_rounds as rounds
        args.out.mkdir(parents=True, exist_ok=True)
        out = args.out / 'CH_Shadows_Rounds.exp'
        report = rounds.build(mirror, out, only=set(args.scenes.split(',')) if args.scenes else None, workers=args.workers)
        print(f"addon: {rounds.ROUNDS_TITLE!r} -> {out} ({report['bytes'] // 2 ** 20} MB), {dict(report)}")
    elif args.command == 'build':
        from claire_hart import compiled
        wanted = {int(n) for n in args.cases.split(',')} if args.cases else None
        art = converter_art(mirror, args.cache)
        args.out.mkdir(parents=True, exist_ok=True)
        reviews = dict(rounds=[], outros=[], intros=[])
        for number, title, parts in mirror.cases():
            if wanted is not None and number not in wanted:
                continue
            project, slices, report = convert(mirror, art, number, title, parts)
            for key in reviews:
                reviews[key] += report.reviews[key]
            name = f'CH2_{number:03d}.exp'
            (args.out / name).write_bytes(compiled(project, slices))
            print(f'{name}: {project.title!r}, {len(project.nodes)} nodes, {dict(report)}')
        write_reviews(args.out, reviews)
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
