"""`ch2rounds`, "Claire Hart: Secret in the Shadows: Rounds": the optional add-on that lets the sequel's translated cases play
its hidden-object rounds for real (reference/Other Games/docs/CLAIRE_HART_SHADOWS_ROUNDS_PLAN.md, step 3), as `chcrounds`
does Classic's (claire_rounds_addon.py, whose archive writer and helpers it shares). Built from the player's own mirror;
nothing of it is in the repo.

    python tools/translate/claire_hart_shadows.py rounds --mirror CH2_DIR --out DIR [--scenes A,B] [--workers 3]

Each scene's base (its `default` layers but the close-up's backing), and one sprite pack (claire_rounds.encode_sprite_pack)
holding its objects' sprites as the game's own PNG files: each object's normal and found sprite, the close-up's backing,
hotspot cutout and glow, a multi-part object's parts and its assembled found sprite. The spec says where each goes (the
layout's centres, y from the bottom, turned into top-lefts), each object's name, kind (shadows_rounds.KINDS) and hint offset,
the multi-part objects' parts, and every round's scene, story objects (resolved as decision G2: by name, a multi-part object by
its assembled sprite) and spotlight mode; then the HUD (every named frame of the game's UI atlases:
claire_hart_shadows_frames.py's table), the 22 sound effects (WAV), the particles, the spotlight's overlay and gamebalance.

The scene model follows build 232's sceneloader (ENGINE 5.1): groups whose first sprite ends `_so` are scenery copies of story
objects and dropped; `pip_scene|` groups are close-up objects; `pip_trigger|` holds the hotspot; `component_object_<x>`
groups are a multi-part object's parts, `component_object_completed` its assembled sprite; `*goldkey_normal` is the Gold Key.
In 5 scenes the assembled object's normal sprite was also placed in the scene, where the game counted it as a third part
(any two of three completed it); it is left out here (the owner's fix, 2026-11-24): the object's own two parts complete it.
"""
import collections
import csv
import json
from pathlib import Path
import re
import shutil
import tempfile

import claire_rounds_addon as cra

ROUNDS_ID, ROUNDS_TITLE, ROUNDS_REVISION = 'ch2rounds', 'Claire Hart: Secret in the Shadows: Rounds', 2
PACK_ID = 31900
SPEC, SPEC_VERSION = 26000, 1
BASE_FIRST = 26001                      # the scenes' bases, in the layouts' sorted order
SPRITES_FIRST = 27001                   # each scene's sprite pack, in the same order
HUD_FIRST = 28000                       # every named UI frame (sorted by name)
SOUND_FIRST, PARTICLE_FIRST, FONT_FIRST, SPOTLIGHT = 28600, 28700, 28800, 28900
TUTORIAL_FIRST = 28950                  # How To Play (revision 2): its pictures, then Claire's standing picture
TUTORIAL = 'unpacked/resources_json/cases/howtoplay/howtoplay.json'
TUTORIAL_CONFIG = 'unpacked/resources_json/cases/howtoplay/htpconfig.json'
TUTORIAL_SEQUENCE = 'howToHOG'
ROUND_KEY_BASE = 20000                  # a sequel round's key: 20000 + case x 100 + part x 10 + round (Classic's are < 3,000)
OLD_KEY_BASE = 50000                    # (revision 1's: out of a Creator node's signed word, so re-keyed by add_tutorial)
GAMEBALANCE = 'unpacked/resources_json/config/gamebalance.json'
FRAMES = 'claire_hart_shadows_ui_frames.json'
SPOTLIGHT_PICTURE = 'placeholder/spotlight2alpha'
ORDINARY, CLOSE_UP, PART, WHOLE, GOLD_KEY = 'o', 'p', 'c', 'w', 'k'
# A story entry spelled otherwise than its sprite (case 12 ep 4: the next chapter's photo is these boots; the game, matching
# by substring, never found them).
STORY_SPELLINGS = {'womansboots': 'womensboots'}


TEXT_CHUNKS = (b'tEXt', b'zTXt', b'iTXt')
PNG_SIGNATURE = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))


def without_text(data):
    """A PNG without its text chunks: 316 of the sprites (ArtSupplyStore, ComisGarage and IslandParkStreet's, and two
    more) carry ~5 MB of Adobe XMP each, ~1.5 GB in all; their pixels' chunks are kept byte for byte."""
    import struct
    if data[:8] != PNG_SIGNATURE:
        return data
    out, at = [data[:8]], 8
    while at + 8 <= len(data):
        length, kind = struct.unpack('>I4s', data[at:at + 8])
        end = at + 12 + length
        if kind not in TEXT_CHUNKS:
            out.append(data[at:end])
        at = end
        if kind == b'IEND':
            break
    return b''.join(out)


def compact(data):
    """A PNG stored with its pixels uncompressed (those same heavy sprites: two bytes a pixel or more) re-encoded,
    losslessly; any other as it is."""
    width, height = cra.png_size(data)
    if len(data) <= 2 * width * height:
        return data
    import io
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        out = io.BytesIO()
        image.save(out, 'PNG', optimize=True)
    return out.getvalue() if out.tell() < len(data) else data


def round_key(case, part, number):
    return ROUND_KEY_BASE + case * 100 + part * 10 + number


class SceneData:
    """A scene's layout (hd/<Folder>.json) and names (names.json) as the game's sceneloader reads them (module doc)."""

    def __init__(self, json_dir, files, folder):
        self.folder = folder
        base = Path(json_dir) / 'references/backgrounds' / folder
        layout = json.loads((base / 'hd' / f'{folder}.json').read_text(encoding='utf-8'))
        names_file = base / 'names.json'
        names = json.loads(names_file.read_text(encoding='utf-8'))['names'] if names_file.exists() else []
        self.files = files                  # {real path: local file}
        self.by_sprite = {}
        for entry in names:
            for key in ('normal', 'found'):
                if entry.get(key):
                    self.by_sprite.setdefault(entry[key].lower(), entry)
        self.base_layers, self.backing, self.cutout, self.glow = [], None, None, None
        self.objects = []                   # [name, kind, normal texture or None, found texture, hint offset]
        wholes = {}                         # multi-part group key -> {'parts': [(normal, found)], 'completed': found}
        for group in layout['textures']:
            textures = group['textures']
            if not textures or textures[0]['id'].endswith('_so'):
                continue                    # (a story object's scenery copy)
            gid = str(group['id'])
            tag = textures[0].get('group') or ''
            if gid == 'default':
                for t in textures:
                    if t['id'].lower().startswith('pip'):
                        self.backing = t
                    else:
                        self.base_layers.append(t)
                continue
            if tag.startswith(('pip_trigger', 'piptrigger')):
                for t in textures:
                    if t['id'] == 'cutout':
                        self.cutout = t
                    elif t['id'] == 'glow':
                        self.glow = t
                continue
            normal = next((t for t in textures if not t['id'].endswith('_found')), None)
            found = next((t for t in textures if t['id'].endswith('_found')), None)
            if gid.startswith('component_object_'):
                key = '|'.join(tag.rstrip('|').split('|')[:-1])
                entry = wholes.setdefault(key, {'parts': [], 'completed': None})
                if gid == 'component_object_completed':
                    entry['completed'] = found          # (its normal sprite, in 5 scenes, left out: module doc)
                elif normal is not None and found is not None:
                    entry['parts'].append((normal, found))
                continue
            if normal is None or found is None:
                continue
            if normal['id'].lower().endswith('goldkey_normal'):
                self.objects.append(['Gold Key', GOLD_KEY, normal, found, [0, 0]])
                continue
            kind = CLOSE_UP if tag.startswith(('pip_scene', 'pipscene')) else ORDINARY
            self.objects.append([self.name(normal, found), kind, normal, found, self.hint(normal, found)])
        self.parts = {}
        for key, entry in sorted(wholes.items()):
            if entry['completed'] is None or not entry['parts']:
                continue                    # (JeanettesKitchen's mortar and pestle: no assembled sprite, never listed)
            first = len(self.objects)
            for normal, found in entry['parts']:
                self.objects.append([self.name(normal, found), PART, normal, found, self.hint(normal, found)])
            whole = len(self.objects)
            completed = entry['completed']
            self.objects.append([self.name(None, completed), WHOLE, None, completed, self.hint(None, completed)])
            self.parts[whole] = list(range(first, whole))
        background = max(self.base_layers, key=lambda t: t['width'] * t['height'])
        self.size = (round(background['width']), round(background['height']))

    def name(self, normal, found):
        """The list's name: names.json's by the normal sprite (or the found one), else the sprite id's second word
        (activeobjectlist.mapName), with a capital as every other name has."""
        for texture in (normal, found):
            if texture is not None:
                entry = self.by_sprite.get(texture['id'].lower())
                if entry and entry.get('name', '').strip():
                    name = entry['name'].strip()
                    return name[:1].upper() + name[1:]
        words = (normal or found)['id'].split('_')
        word = words[1] if len(words) > 1 else words[0]
        return word[:1].upper() + word[1:]

    def hint(self, normal, found):
        for texture in (normal, found):
            if texture is not None:
                entry = self.by_sprite.get(texture['id'].lower())
                if entry and entry.get('hintOffset'):
                    return list(entry['hintOffset'])
        return [0, 0]

    def file(self, texture):
        return compact(without_text(Path(self.files[f"references/backgrounds/{self.folder}/hd/{texture['image']}"]).read_bytes()))

    def place(self, texture):
        """A texture's top left in the base's pixels (from the top): the layout gives centres, y from the bottom."""
        return (round(texture['x'] - texture['width'] / 2), round(self.size[1] - texture['y'] - texture['height'] / 2))

    def base_bytes(self):
        if len(self.base_layers) == 1 and self.place(self.base_layers[0]) == (0, 0):
            return self.file(self.base_layers[0])
        from PIL import Image
        import io
        canvas = Image.new('RGBA', self.size, (0, 0, 0, 0))
        for texture in sorted(self.base_layers, key=lambda t: -t['width'] * t['height']):
            canvas.alpha_composite(Image.open(io.BytesIO(self.file(texture))).convert('RGBA'), self.place(texture))
        return cra.png(canvas)

    def story_index(self, entry):
        """A round's story-object entry resolved (decision G2): a multi-part object by its assembled sprite's name; else the
        object names.json names so; else the game's rule, the first sprite containing it (layout order), preferring one
        whose name's own word is the entry (the game's `apple` landed on a pineapple); None for none or "nothing"."""
        key = re.sub(r'[^a-z0-9]', '', entry.lower())
        key = STORY_SPELLINGS.get(key, key)
        if not key or key == 'nothing':
            return None
        for whole in self.parts:
            if key in re.sub(r'[^a-z0-9]', '', self.objects[whole][3]['id'].lower()):
                return whole
        for i, (name, kind, normal, found, _) in enumerate(self.objects):
            if kind in (ORDINARY, CLOSE_UP) and re.sub(r'[^a-z0-9]', '', name.lower()) == key:
                return i
        def bare(sprite_id):
            return re.sub(r'[^a-z0-9]', '', sprite_id.lower())
        # (an entry written as a sprite's own id, `kitchendrawer_knife_normal` or `locket_found`, compared without its
        # punctuation, as the entry is)
        candidates = [i for i, (_, kind, normal, found, _) in enumerate(self.objects)
                      if kind in (ORDINARY, CLOSE_UP) and (key in bare(normal['id']) or key in bare(found['id']))]
        exact = [i for i in candidates if key in self.objects[i][2]['id'].lower().split('_')]
        return (exact or candidates or [None])[0]


_WORKER = {}


def worker_start(json_dir, files):
    """A worker's own copy of the mirror's file table, sent once."""
    _WORKER.update(json_dir=json_dir, files=files)


def scene_job(folder):
    return scene_resources(SceneData(_WORKER['json_dir'], _WORKER['files'], folder))


def scene_resources(scene):
    """A scene's base PNG, its sprite pack and its spec entry (the caller adds the resources' numbers)."""
    from exp_runtime.claire_rounds import encode_sprite_pack
    files, objects = [], []

    def sprite(texture):
        if texture is None:
            return None
        data = scene.file(texture)
        width, height = cra.png_size(data)
        left, top = scene.place(texture)
        files.append(data)
        return [len(files) - 1, width, height, left, top]
    for name, kind, normal, found, hint in scene.objects:
        objects.append([name, kind, sprite(normal), sprite(found), hint])
    close_up = None
    if scene.backing is not None and scene.cutout is not None:
        close_up = {'backing': sprite(scene.backing), 'cutout': sprite(scene.cutout), 'glow': sprite(scene.glow)}
    entry = {'size': list(scene.size), 'objects': objects, 'parts': {str(w): p for w, p in scene.parts.items()},
             'close_up': close_up}
    return scene.base_bytes(), encode_sprite_pack(files), entry


def bundle_rows(root):
    rows = collections.defaultdict(list)
    with open(Path(root) / 'bundle_names.csv', encoding='utf-8-sig', newline='') as file:
        for row in csv.DictReader(file):
            if row['part'] == 'native':
                rows[row['real_path']].append(row)
    return rows


def rounds_table(mirror, scenes):
    """{key: [scene folder, [story objects], location, spotlight]} for every round (855: case 31's unlisted parts too)."""
    from claire_hart_shadows import chapters_of
    table, unplaced = {}, []
    for case, _, parts in mirror.cases():
        for part in parts:
            modes = {n['hogId']: n.get('mode') for n in part.sequences['main']['nodes'] if n['type'] == 'playHOG'}
            for number, (chapter, round_id) in enumerate([c for c in chapters_of(part.sequences) if c[1]], 1):
                entry = mirror.round_entry(part.config, chapter, round_id) or {}
                folder = entry.get('scene') or part.config['hogConfig'][round_id]['scene']
                scene = scenes.get(folder)
                if scene is None:
                    unplaced.append((part.epid, round_id, folder, 'no layout'))
                    continue
                story = []
                listed = entry.get('storyobject') or []
                for value in [listed] if isinstance(listed, str) else listed:
                    index = scene.story_index(value)
                    if index is None:
                        if re.sub(r'[^a-z]', '', value.lower()) not in ('', 'nothing'):
                            unplaced.append((part.epid, round_id, folder, value))
                    elif index not in story:
                        story.append(index)
                table[str(round_key(case, part.number, number))] = [folder, story, (entry.get('location') or '').strip(),
                                                                     modes.get(round_id) == 'spotlight']
    return table, unplaced


def hud_resources(root, frames):
    """[(resource, bytes)] and the spec's `hud` {frame name: resource}: every named frame of the UI atlases, cut whole."""
    from PIL import Image
    out, hud = [], {}
    pages = {}
    for n, name in enumerate(sorted(n for n, f in frames.items() if f.get('texture'))):
        frame = frames[name]
        if frame['texture'] not in pages:
            pages[frame['texture']] = Image.open(Path(root) / frame['texture']).convert('RGBA')
        x, y, w, h = frame['rect']
        page = pages[frame['texture']]
        picture = page.crop((x, y, x + h, y + w)).transpose(Image.ROTATE_90) if frame['rotated'] else \
            page.crop((x, y, x + w, y + h))
        out.append((HUD_FIRST + n, cra.png(picture)))
        hud[name] = HUD_FIRST + n
    if HUD_FIRST + len(out) > SOUND_FIRST:
        raise ValueError('the HUD art runs past its range')
    return out, hud


def tutorial_resources(root, rows):
    """How To Play (owner, 2026-11-25: included, the sequel's only): the round's `howToHOG` sequence as the spec's
    `tutorial`: its pages ({text, name, sprites [[picture, x, y]], claire 'left' / 'right' / None}: what is on the stage at
    each of Claire's lines, x and y from the 800 x 600 stage's centre, y up), the pictures ({name: [resource, width,
    height]}) and Claire's standing picture (her sd default face, as the sequence's character config names it); and
    [(resource, bytes)]."""
    root = Path(root)
    sequence = json.loads((root / TUTORIAL).read_text(encoding='utf-8'))['sequences'][TUTORIAL_SEQUENCE]
    refs = json.loads((root / TUTORIAL_CONFIG).read_text(encoding='utf-8'))['sceneRefs'][TUTORIAL_SEQUENCE]
    out, pictures = [], {}

    def picture(path):
        row = next(r for r in rows[path] if r['ext'] in ('.png', '.jpg'))
        data = (root / row['local_path']).read_bytes()
        if row['ext'] == '.png':
            data = compact(without_text(data))
        out.append((TUTORIAL_FIRST + len(out), data))
        return [TUTORIAL_FIRST + len(out) - 1, int(row['width']), int(row['height'])]
    for name, path in sorted(refs['sprites'].items()):
        pictures[name] = picture(path)
    claire = picture(refs['characters']['Claire']['expressions']['default'])
    pages, shown, side = [], {}, None
    for node in sequence['nodes']:
        kind = node['type']
        if kind == 'spriteIntro':
            shown[node['id']] = [node['ref'], node.get('x', 0), node.get('y', 0)]
        elif kind == 'spriteOutro':
            shown.pop(node['id'], None)
        elif kind == 'stageBlockIntro':
            side = 'right' if node.get('intro') == 'enterFromRight' else 'left'
        elif kind == 'stageBlockOutro':
            side = None
        elif kind == 'dialogText':
            pages.append(dict(text=node['body'], name=node.get('narrator') or node.get('header') or 'Claire',
                              sprites=[list(v) for v in shown.values()], claire=side))
    return out, dict(pictures=pictures, claire=claire, pages=pages)


def add_tutorial(rounds_path, root, out_path, progress=print):
    """A built ch2rounds (revision 1) given How To Play (tutorial_resources), its rounds re-keyed from 20000 (revision
    1's 50000 overflowed a Creator node's signed word) and its HUD cut again, made revision 2, streaming the rest as it is
    (claire_rounds_addon.share_bases' way), so the hour-long build needn't run again."""
    from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes
    index = cra.archive_index(rounds_path)
    spec = json.loads(cra.read_resource(rounds_path, index, SPEC))
    added, spec['tutorial'] = tutorial_resources(root, bundle_rows(root))
    spec['rounds'] = {str(int(k) - OLD_KEY_BASE + ROUND_KEY_BASE) if int(k) >= OLD_KEY_BASE else k: v
                      for k, v in spec['rounds'].items()}
    # (and the HUD cut again from the frames table: 40 frames of revision 1 came from the wrong atlas page)
    hud, spec['hud'] = hud_resources(root, json.loads((Path(root) / FRAMES).read_text(encoding='utf-8')))
    added += hud
    out_path = Path(out_path)
    work = Path(tempfile.mkdtemp(prefix='.ch2rounds-tutorial-', dir=out_path.parent))
    try:
        parts = {}
        for resource, data in added:
            parts[resource] = work / f'{resource}.bin'
            parts[resource].write_bytes(data)
        for resource, (offset, size) in index.items():
            if resource in parts:
                continue
            path = parts[resource] = work / f'{resource}.bin'
            if resource == SPEC:
                path.write_bytes(json.dumps(spec, separators=(',', ':')).encode('utf-8'))
            elif resource == ADDON_RECORD:
                path.write_bytes(provides_bytes(ROUNDS_ID, ROUNDS_TITLE, ROUNDS_REVISION))
            else:
                with open(rounds_path, 'rb') as source, open(path, 'wb') as target:
                    source.seek(offset)
                    left = size
                    while left:
                        block = source.read(min(left, 1 << 20))
                        target.write(block)
                        left -= len(block)
        cra.write_exp(out_path, parts)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    progress(f"How To Play: {len(spec['tutorial']['pages'])} pages; {len(added)} pictures written; revision {ROUNDS_REVISION}")
    return dict(pages=len(spec['tutorial']['pages']), pictures=len(added), bytes=out_path.stat().st_size)


def build(mirror, out, *, only=None, workers=3, progress=print):
    """Write `out` from `mirror` (claire_hart_shadows.Mirror); return a report. `only`: these scene folders alone (a check
    build; its rounds table still lists every round)."""
    from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes
    from exp_runtime.exp import Metadata
    if shutil.which('ffmpeg') is None:
        raise SystemExit('FFmpeg is needed for the sounds')
    root = mirror.root
    files = {path: str(local) for path, local in mirror.files.items() if path.startswith('references/backgrounds/')}
    layouts = root / 'unpacked/resources_json/references/backgrounds'
    folders = sorted(p.name for p in layouts.iterdir() if (p / 'hd' / f'{p.name}.json').exists())
    scenes = {folder: SceneData(mirror.json_dir, files, folder) for folder in folders}
    report = collections.Counter()
    out = Path(out)
    work = Path(tempfile.mkdtemp(prefix='.ch2rounds-', dir=out.parent))
    parts = {}

    def put(resource, data):
        path = work / f'{resource}.bin'
        path.write_bytes(data)
        parts[resource] = path
    try:
        spec = {'version': SPEC_VERSION, 'scenes': {}, 'sounds': {}, 'particles': {}, 'fonts': {}}
        from concurrent.futures import ProcessPoolExecutor
        cra.below_normal()
        wanted = [(n, folder) for n, folder in enumerate(folders) if only is None or folder in only]
        with ProcessPoolExecutor(max_workers=workers, initializer=worker_start, initargs=(str(mirror.json_dir), files)) as pool:
            done = pool.map(scene_job, [folder for _, folder in wanted], chunksize=2)
            for (n, folder), (base, sprites, entry) in zip(wanted, done):
                put(BASE_FIRST + n, base)
                put(SPRITES_FIRST + n, sprites)
                entry['base'], entry['sprites'] = BASE_FIRST + n, SPRITES_FIRST + n
                spec['scenes'][folder] = entry
                kinds = collections.Counter(o[1] for o in entry['objects'])
                report['scenes'] += 1
                report['objects'] += kinds[ORDINARY]
                report['close-up objects'] += kinds[CLOSE_UP]
                report['multi-part objects'] += kinds[WHOLE]
                report['gold keys'] += kinds[GOLD_KEY]
                report['close-ups'] += entry['close_up'] is not None
                if report['scenes'] % 50 == 0:
                    progress(f"{report['scenes']} of {len(wanted)} scenes")
        spec['rounds'], unplaced = rounds_table(mirror, scenes)
        report['rounds'] = len(spec['rounds'])
        report['story objects'] = sum(len(r[1]) for r in spec['rounds'].values())
        report['spotlight rounds'] = sum(r[3] for r in spec['rounds'].values())
        spec['unplaced'] = unplaced
        spec['balance'] = json.loads((root / GAMEBALANCE).read_text(encoding='utf-8'))
        rows = bundle_rows(root)
        with tempfile.TemporaryDirectory() as folder:
            sounds = sorted(p for p in rows if p.startswith('references/gamesfx/ogg/'))
            for i, path in enumerate(sounds):
                put(SOUND_FIRST + i, cra.wav(root / rows[path][0]['local_path'], folder))
                spec['sounds'][path.rsplit('/', 1)[1].replace('Claire_Hart_2_', '')] = SOUND_FIRST + i
        resource = PARTICLE_FIRST
        for path in sorted(p for p, rs in rows.items() if p.startswith('particles/') and any(r['ext'] == '.plist' for r in rs)):
            entry = []
            for ext in ('.plist', '.png'):
                found = [r for r in rows[path] if r['ext'] == ext]
                if found:
                    put(resource, (root / found[0]['local_path']).read_bytes())
                    entry.append(resource)
                    resource += 1
            spec['particles'][path.split('/', 1)[1]] = entry
        fonts = sorted(p for p, rs in rows.items() if p.startswith('font/') and any(r['ext'] == '.ttf' for r in rs))
        for i, path in enumerate(fonts):
            put(FONT_FIRST + i, (root / next(r for r in rows[path] if r['ext'] == '.ttf')['local_path']).read_bytes())
            spec['fonts'][path.rsplit('/', 1)[1]] = FONT_FIRST + i
        put(SPOTLIGHT, (root / next(r for r in rows[SPOTLIGHT_PICTURE] if r['ext'] == '.png')['local_path']).read_bytes())
        spec['spotlight'] = SPOTLIGHT
        added, spec['tutorial'] = tutorial_resources(root, rows)
        for resource, data in added:
            put(resource, data)
        frames = json.loads((root / FRAMES).read_text(encoding='utf-8'))
        hud, spec['hud'] = hud_resources(root, frames)
        for resource, data in hud:
            put(resource, data)
        report['hud pieces'] = len(hud)
        put(SPEC, json.dumps(spec, separators=(',', ':')).encode('utf-8'))
        put(ADDON_RECORD, provides_bytes(ROUNDS_ID, ROUNDS_TITLE, ROUNDS_REVISION))
        put(1, Metadata(PACK_ID, 0, (ROUNDS_TITLE + ' (addon)',) * 5).to_bytes())
        cra.write_exp(out, parts)
        report['resources'] = len(parts)
        report['bytes'] = out.stat().st_size
        report['unplaced'] = len(unplaced)
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)
