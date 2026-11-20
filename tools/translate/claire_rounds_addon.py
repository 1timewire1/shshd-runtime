"""`chcrounds`, "Claire Hart Classic: Rounds": the optional add-on that lets the translated cases play Claire Hart Classic's
hidden-object rounds for real (reference/Other Games/docs/CLAIRE_HART_ROUNDS_PLAN.md, step 2). Built from the player's own
mirror, as `chc` is; nothing of it is in the repo.

    python tools/translate/claire_hart.py rounds --mirror CLAIRE_HART_DIR --out DIR

Every scene's base picture, and its objects' sprites (each object's "normal" one, drawn in the scene, and its "found" one,
which flies to the list) as Classic's own PNG files, one pack a scene (the add-on's IDs are 16 bits; the sprites number 78,577:
claire_rounds.encode_sprite_pack); a spec saying where each sprite goes in the scene (build 157's layout: centres, y from the
bottom), each object's name and hint offset, and each round's scene and story objects; Classic's 13 round sound effects (as WAV),
its particle systems and fonts, and the round screen's HUD art (hud_resources). (Atlas pages were tried first: repacked as
true-colour pages, Classic's paletted sprites more than doubled, 2.4 GB.)

The archive is written as it is made (write_exp), so its 1.1 GB never sits in memory at once.
"""
import csv
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

ROUNDS_ID, ROUNDS_TITLE, ROUNDS_REVISION = 'chcrounds', 'Claire Hart Classic: Rounds', 1
PACK_ID = 31500
SPEC = 26000
BASE_FIRST = 26001                      # the scenes' bases, in the scene folders' sorted order (chc's own order)
HUD_FIRST = 26800                       # the round's HUD: its pieces, then each animation as a sprite pack (hud_resources)
# The packs holding the round screen's pieces (HogPTSDcomboScene's own, the menus' and the modals'): every frame of them, cut
# whole (original size, trimmed margins restored); and the animations it plays, each frame in order, as one sprite pack.
HUD_PACKS = ('0f/0f14b4a7e.json', '0b/0b3869fa8.json', '03/03492ab2a.json')
HUD_ANIMATIONS = ('vfx_HintFill', 'vfx_explosion', 'vfx_hint_starburst', 'vfx_hint_tail', 'vfx_sparkles', 'vfx_smoke')
HUD_TEXTURES = {'powerup_Hint': 'textures/SD/HOGscene/powerup_Hint'}     # (a texture of its own: the orb's sparkle ring)
SOUND_FIRST = 26900
PARTICLE_FIRST = 26930                  # plist, then its picture
FONT_FIRST = 26960
SPRITES_FIRST = 27001                   # each scene's sprite pack, in the same order as the bases
SPEC_VERSION = 1
SOUNDS = ('Claire_Hart_2_DS_Focus_Different_Character', 'Claire_Hart_2_GES_Button_Click',
          'Claire_Hart_2_GES_Navigation_Option_Appearing', 'Claire_Hart_2_GS_Hint_Power_Up',
          'Claire_Hart_2_GS_Line_Appearing_Chapter_Result', 'Claire_Hart_2_GS_Object_1_Combo',
          'Claire_Hart_2_GS_Object_6_Combo', 'Claire_Hart_2_GS_Object_In_Objectlist', 'Claire_Hart_2_GS_Pop_UP_Notification',
          'Claire_Hart_2_GS_Roll_Over', 'Claire_Hart_2_GS_Scene_Cleard', 'Claire_Hart_2_GS_Time_Wrap_Power_Up', 'tap')
GAMEBALANCE = 'unpacked/resources_json/config/gamebalance.json'


def is_normal(image):
    image = image.lower()
    return image.endswith('_normal') or image.startswith('ho_obj')


def is_found(image):
    image = image.lower()
    return image.endswith('_found') or image.startswith('hof_obj')


class SceneData:
    """A scene's layout (hd/<Folder>.json) and names (names.json): its base, and its objects, each a (name, normal texture,
    found texture, hint offset); a group without a normal sprite (KeepersCottage's Handbell) is no object."""

    def __init__(self, folder_path):
        self.path = Path(folder_path)
        self.folder = self.path.name
        layout = json.loads((self.path / 'hd' / f'{self.folder}.json').read_text(encoding='utf-8'))
        names = json.loads((self.path / 'names.json').read_text(encoding='utf-8'))['names']
        by_normal = {n['normal'].lower(): n for n in names if n.get('normal')}
        self.base_layers, self.objects = [], []
        for group in layout['textures']:
            if group['id'] == 'default':
                self.base_layers = group['textures']
                continue
            normal = [t for t in group['textures'] if is_normal(t['image'])]
            found = [t for t in group['textures'] if is_found(t['image'])]
            if not normal or not found:
                continue
            entry = by_normal.get(normal[0]['image'].lower(), {})
            name = (entry.get('name') or '').strip() or fallback_name(normal[0]['image'])
            self.objects.append((name, normal[0], found[0], list(entry.get('hintOffset') or (0, 0))))
        background = next((t for t in self.base_layers if t['image'].lower() in ('bg', 'background')), None) \
            or max(self.base_layers, key=lambda t: t['width'] * t['height'])
        self.size = (int(background['width']), int(background['height']))
        self.index = {normal['image'].lower(): i for i, (_, normal, _, _) in enumerate(self.objects)}

    def _path(self, image):
        if not hasattr(self, '_files'):
            self._files = {p.stem.lower(): p for p in (self.path / 'hd').iterdir() if p.suffix.lower() == '.png'}
        return self._files[image.lower()]

    def file(self, image):
        return self._path(image).read_bytes()

    def picture(self, image):
        from PIL import Image
        return Image.open(self._path(image)).convert('RGBA')

    def place(self, texture):
        """A texture's top left in the base's pixels (from the top): build 157's layout gives centres, y from the bottom."""
        return (round(texture['x'] - texture['width'] / 2), round(self.size[1] - texture['y'] - texture['height'] / 2))

    def base(self):
        """The base picture: the default group's layers, the largest first (EstateBedroom's bg, then its shadow)."""
        from PIL import Image
        canvas = Image.new('RGBA', self.size, (0, 0, 0, 0))
        for texture in sorted(self.base_layers, key=lambda t: -t['width'] * t['height']):
            canvas.alpha_composite(self.picture(texture['image']), self.place(texture))
        return canvas

    def base_bytes(self):
        """The base as a PNG: Classic's own file when it is one layer filling the scene, else base() flattened."""
        if len(self.base_layers) == 1 and self.place(self.base_layers[0]) == (0, 0):
            return self.file(self.base_layers[0]['image'])
        return png(self.base())


def fallback_name(image):
    """activeobjectlist.mapName's own fallback for a sprite names.json doesn't name: its second word (5 objects: ArtStudio's
    'love', MasterSuite's 'flute'...), capitalized as every other name in the list is (Classic showed it as it is)."""
    words = image.split('_')
    word = words[1] if len(words) > 1 else image
    return word[:1].upper() + word[1:]


def scene_job(path):
    """scene_resources for the scene folder `path`, in a worker process."""
    return scene_resources(SceneData(path))


def scene_resources(scene):
    """A scene's base PNG, its sprite pack (claire_rounds.encode_sprite_pack: every object's normal then found sprite, as
    Classic's own PNG files) and its spec entry (the pack's resource added by the caller)."""
    from exp_runtime.claire_rounds import encode_sprite_pack
    files, objects = [], []
    for name, normal, found, hint in scene.objects:
        sprites = []
        for texture in (normal, found):
            data = scene.file(texture['image'])
            width, height = png_size(data)
            left, top = scene.place(texture)
            sprites.append([len(files), width, height, left, top])
            files.append(data)
        objects.append([name, *sprites, hint])
    return scene.base_bytes(), encode_sprite_pack(files), {'size': list(scene.size), 'objects': objects}


def png_size(data):
    """A PNG's width and height, from its IHDR."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG')
    return struct.unpack('>II', data[16:24])


def png(image):
    out = io.BytesIO()
    image.save(out, 'PNG', compress_level=6)
    return out.getvalue()


def rounds_table(mirror, scenes):
    """{E-number: [[scene folder, [story object indices], the scene's name], ...]} for every round, in order (claire_hart.Mirror.round_items:
    the story lists resolved, then to the scene's objects by their normal sprite)."""
    import claire_hart as ch
    table, unplaced = {}, []
    for _, _, parts in mirror.cases():
        for _, config, sequences in parts:
            rounds = []
            for node in sequences['main']['nodes']:
                if node['type'] != 'playHOG':
                    continue
                number = int(node['hogId'].rsplit(' ', 1)[1])
                chapter = config['sceneRefs'][f'SCENE 1_{number}']
                value = next((v for v in chapter.get('backgrounds', {}).values() if v.get('type') == 'hogScene'), None)
                folder = ch.folder_of(config['hogConfig'][node['hogId']]['scene'])
                scene = scenes[folder]
                story = []
                for entry, item in (mirror.round_items(value) if value else ()):
                    index = scene.index.get(item['normal'].lower()) if item else None
                    if index is None:
                        if item is not None:
                            unplaced.append((config['epid'], number, entry))
                    elif index not in story:
                        story.append(index)
                name = config['hogConfig'][node['hogId']]['scene'].strip()
                rounds.append([folder, story, ch.SCENE_NAMES.get(name, name)])     # (the plate's name, as Classic's)
            table[config['epid']] = rounds
    return table, unplaced


def wav(ogg, folder):
    out = Path(folder) / 'sound.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(ogg), '-acodec', 'pcm_s16le', str(out)], check=True)
    return out.read_bytes()


def hud_resources(mirror_root, rows, first=HUD_FIRST):
    """[(resource, bytes)] and the spec's `hud` {name: resource} (an animation's: [resource, frame count])."""
    import re
    import cocos_frames as cf
    from exp_runtime.claire_rounds import encode_sprite_pack
    cache, out, hud = {}, [], {}
    resource = first
    pieces = cf.frames(mirror_root, HUD_PACKS)
    for name in sorted(pieces):
        out.append((resource, png(cf.cut(mirror_root, pieces[name][0], cache=cache))))
        hud[name] = resource
        resource += 1
    for name, path in HUD_TEXTURES.items():
        row = next(r for r in rows[path] if r['ext'] == '.png')
        out.append((resource, (Path(mirror_root) / row['local_path']).read_bytes()))
        hud[name] = resource
        resource += 1
    every = cf.frames(mirror_root)
    for animation in HUD_ANIMATIONS:
        names = sorted(n for n in every if re.fullmatch(re.escape(animation) + r'\d+', n))
        files = [png(cf.cut(mirror_root, every[n][0], cache=cache)) for n in names]
        out.append((resource, encode_sprite_pack(files)))
        hud[animation] = [resource, len(files)]
        resource += 1
    if resource > SOUND_FIRST:
        raise ValueError('the HUD art runs past its range')
    return out, hud


def below_normal():
    """This process (and the workers it starts after) at below-normal priority, on Windows."""
    import sys
    if sys.platform == 'win32':
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000)


def write_exp(path, parts):
    """A CSPUD archive (exp.encode_exp's layout) from {resource: file} on disk, written as it goes."""
    from exp_runtime.exp import ContentError
    ids = sorted(parts)
    if not ids or len(ids) > 65536 or not all(0 <= i <= 65535 for i in ids):
        raise ContentError('Invalid resource IDs')
    offset = 9 + 6 * len(ids)
    index = bytearray()
    for resource in ids:
        index += struct.pack('>HI', resource, offset)
        offset += 12 + Path(parts[resource]).stat().st_size
    if offset > 0xffffffff:
        raise ContentError('EXP exceeds the native 32-bit archive size')
    with open(path, 'wb') as out:
        out.write(b'CSPUD' + struct.pack('>I', len(ids)) + index)
        for resource in ids:
            size = Path(parts[resource]).stat().st_size
            out.write(struct.pack('>III', size, size, 0))
            with open(parts[resource], 'rb') as source:
                shutil.copyfileobj(source, out, 1 << 20)


def build(mirror, out, *, only=None, workers=3, progress=print):
    """Write `out` (the add-on's .exp) from `mirror` (claire_hart.Mirror); return a report. `only`: these scene folders
    alone (a check build; its rounds table still lists every round)."""
    from exp_runtime.addons import RESOURCE as ADDON_RECORD, provides_bytes
    from exp_runtime.exp import Metadata
    if shutil.which('ffmpeg') is None:
        raise SystemExit('FFmpeg is needed for the sounds')
    root = mirror.scenes_dir
    folders = sorted(p.name for p in root.iterdir() if (p / 'hd' / f'{p.name}.json').exists())
    scenes = {folder: SceneData(root / folder) for folder in folders}
    report = dict(scenes=0, objects=0, unnamed=0)
    out = Path(out)
    work = Path(tempfile.mkdtemp(prefix='.chcrounds-', dir=out.parent))
    parts = {}

    def put(resource, data):
        path = work / f'{resource}.bin'
        path.write_bytes(data)
        parts[resource] = path

    try:
        spec = {'version': SPEC_VERSION, 'scenes': {}, 'sounds': {}, 'particles': {}, 'fonts': {}}
        from concurrent.futures import ProcessPoolExecutor
        below_normal()                  # (the workers take the build's priority: a long build mustn't slow the machine)
        wanted = [(n, folder) for n, folder in enumerate(folders) if only is None or folder in only]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            done = pool.map(scene_job, [root / folder for _, folder in wanted], chunksize=4)
            for (n, folder), (base, sprites, entry) in zip(wanted, done):
                scene = scenes[folder]
                put(BASE_FIRST + n, base)
                put(SPRITES_FIRST + n, sprites)
                entry['base'], entry['sprites'] = BASE_FIRST + n, SPRITES_FIRST + n
                spec['scenes'][folder] = entry
                report['scenes'] += 1
                report['objects'] += len(scene.objects)
                report['unnamed'] += sum(name == fallback_name(normal['image']) for name, normal, _, _ in scene.objects)
                if report['scenes'] % 100 == 0:
                    progress(f"{report['scenes']} scenes")
        spec['rounds'], unplaced = rounds_table(mirror, scenes)
        report['rounds'] = sum(len(r) for r in spec['rounds'].values())
        report['story objects'] = sum(len(entry[1]) for r in spec['rounds'].values() for entry in r)
        report['story objects without a sprite'] = unplaced
        spec['balance'] = json.loads((mirror.root / GAMEBALANCE).read_text(encoding='utf-8'))
        rows = {}
        with open(mirror.root / 'bundle_names.csv', encoding='utf-8-sig', newline='') as file:
            for row in csv.DictReader(file):
                if row['part'] == 'native':
                    rows.setdefault(row['real_path'], []).append(row)
        with tempfile.TemporaryDirectory() as folder:
            for i, name in enumerate(SOUNDS):
                ogg = next(mirror.root / r['local_path'] for r in rows[f'references/gamesfx/ogg/{name}'])
                put(SOUND_FIRST + i, wav(ogg, folder))
                spec['sounds'][name] = SOUND_FIRST + i
        particles = sorted({path for path, rs in rows.items() if path.startswith('particles/')
                            and any(r['ext'] == '.plist' for r in rs)})
        resource = PARTICLE_FIRST
        for path in particles:
            entry = []
            for ext in ('.plist', '.png'):
                found = [r for r in rows[path] if r['ext'] == ext]
                if found:
                    put(resource, (mirror.root / found[0]['local_path']).read_bytes())
                    entry.append(resource)
                    resource += 1
            spec['particles'][path.split('/', 1)[1]] = entry
        fonts = sorted(path for path, rs in rows.items() if path.startswith('font/Roboto') and any(r['ext'] == '.ttf'
                                                                                                  for r in rs))
        for i, path in enumerate(fonts):
            put(FONT_FIRST + i, (mirror.root / next(r for r in rows[path] if r['ext'] == '.ttf')['local_path']).read_bytes())
            spec['fonts'][path.rsplit('/', 1)[1]] = FONT_FIRST + i
        hud, spec['hud'] = hud_resources(mirror.root, rows)
        for resource, data in hud:
            put(resource, data)
        report['hud pieces'] = len(hud)
        put(SPEC, json.dumps(spec, separators=(',', ':')).encode('utf-8'))
        put(ADDON_RECORD, provides_bytes(ROUNDS_ID, ROUNDS_TITLE, ROUNDS_REVISION))
        put(1, Metadata(PACK_ID, 0, (ROUNDS_TITLE + ' (addon)',) * 5).to_bytes())
        write_exp(out, parts)
        report['resources'] = len(parts)
        report['bytes'] = out.stat().st_size
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)
