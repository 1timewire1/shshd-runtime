"""`chcrounds`'s builder (Claire Hart plan Stage 3, step 2): a scene's layout read as build 157 places it (centres, y from the
bottom), its sprites kept as Classic's own files in one pack a scene and found again where the spec says, its base
(EstateBedroom's shadow over its bg), and the archive written as it goes."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:                                     # pragma: no cover
    HAS_PIL = False


def a_scene(root, folder='Office', objects=(('Broom', (40, 20), (100, 700)), ('Ring', (10, 10), (500, 385)))):
    """A scene folder: a 1026 x 770 base, and per object a normal sprite (opaque, its size) at a centre (x, y from the
    bottom) and a found one twice its size."""
    hd = Path(root) / folder / 'hd'
    hd.mkdir(parents=True)
    Image.new('RGBA', (1026, 770), (10, 20, 30, 255)).save(hd / 'background.png')
    textures = [{'id': 'default', 'textures': [{'id': 'bg', 'image': 'background', 'x': 513, 'y': 385, 'width': 1026,
                                                'height': 770}]}]
    names = []
    for n, (name, (w, h), (x, y)) in enumerate(objects):
        stem = f'{folder.lower()}_{name.lower()}'
        Image.new('RGBA', (w, h), (200, 50 + n, 0, 255)).save(hd / f'{stem}_normal.png')
        Image.new('RGBA', (2 * w, 2 * h), (255, 255, 0, 255)).save(hd / f'{stem}_found.png')
        textures.append({'id': str(n), 'textures': [
            {'image': f'{stem}_normal', 'x': x, 'y': y, 'width': w, 'height': h},
            {'image': f'{stem}_found', 'x': x, 'y': y, 'width': 2 * w, 'height': 2 * h}]})
        names.append({'name': name, 'normal': f'{stem}_normal', 'found': f'{stem}_found', 'hintOffset': [n, -n]})
    (hd / f'{folder}.json').write_text(json.dumps({'metadata': {}, 'textures': textures}))
    (Path(root) / folder / 'names.json').write_text(json.dumps({'names': names}))
    return Path(root) / folder


@unittest.skipUnless(HAS_PIL, 'the builder uses Pillow')
class SceneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def test_a_layout_is_read_as_build_157_places_it(self):
        import claire_rounds_addon as ra
        scene = ra.SceneData(a_scene(self.temporary.name))
        self.assertEqual(scene.size, (1026, 770))
        self.assertEqual([name for name, *_ in scene.objects], ['Broom', 'Ring'])
        broom = scene.objects[0][1]
        self.assertEqual(scene.place(broom), (100 - 20, 770 - 700 - 10))      # centre (100, 700 from the bottom), 40 x 20
        self.assertEqual(scene.objects[1][3], [1, -1])                          # its hint offset

    def test_an_object_names_json_lacks_takes_its_sprites_word(self):
        """activeobjectlist.mapName's fallback (5 objects: ArtStudio's 'love'...), capitalized."""
        import claire_rounds_addon as ra
        self.assertEqual(ra.fallback_name('artstudio_love_normal'), 'Love')
        self.assertEqual(ra.fallback_name('statuegarden_fleur-de-lis_normal'), 'Fleur-de-lis')

    def test_a_group_without_a_normal_sprite_is_no_object(self):
        """KeepersCottage's Handbell: two found sprites, no normal one."""
        import claire_rounds_addon as ra
        path = a_scene(self.temporary.name)
        layout = json.loads((path / 'hd' / 'Office.json').read_text())
        layout['textures'][1]['textures'][0]['image'] = 'office_broom_found'
        (path / 'hd' / 'Office.json').write_text(json.dumps(layout))
        self.assertEqual([name for name, *_ in ra.SceneData(path).objects], ['Ring'])

    def test_a_scenes_sprites_come_back_from_its_pack_as_they_were(self):
        import claire_rounds_addon as ra
        from exp_runtime.claire_rounds import sprite_from_pack
        path = a_scene(self.temporary.name)
        scene = ra.SceneData(path)
        base, pack, entry = ra.scene_resources(scene)
        name, normal, found, hint = entry['objects'][0]
        number, w, h, left, top = normal
        self.assertEqual((name, w, h, left, top), ('Broom', 40, 20, 80, 60))
        self.assertEqual(sprite_from_pack(pack, number), (path / 'hd' / 'office_broom_normal.png').read_bytes())
        self.assertEqual(found[1:3], [80, 40])
        self.assertEqual(sprite_from_pack(pack, found[0]), (path / 'hd' / 'office_broom_found.png').read_bytes())
        self.assertEqual(base, (path / 'hd' / 'background.png').read_bytes())    # one layer: Classic's own file
        with self.assertRaises(ValueError):
            sprite_from_pack(pack, 4)

    def test_a_shadow_layer_goes_over_the_bg(self):
        """EstateBedroom's default group lists a smaller `shadow` before its `bg`: the bg goes under."""
        import claire_rounds_addon as ra
        path = a_scene(self.temporary.name)
        Image.new('RGBA', (100, 50), (0, 0, 0, 128)).save(path / 'hd' / 'shadow.png')
        layout = json.loads((path / 'hd' / 'Office.json').read_text())
        layout['textures'][0]['textures'].insert(0, {'id': 'shadow', 'image': 'shadow', 'x': 60, 'y': 745, 'width': 100,
                                                     'height': 50})
        (path / 'hd' / 'Office.json').write_text(json.dumps(layout))
        scene = ra.SceneData(path)
        base = scene.base()
        self.assertLess(base.getpixel((20, 10))[2], 30)                          # darkened by the shadow
        self.assertEqual(base.getpixel((500, 500)), (10, 20, 30, 255))
        self.assertEqual(Image.open(io.BytesIO(scene.base_bytes())).convert('RGBA').getpixel((20, 10)), base.getpixel((20, 10)))



class ArchiveTests(unittest.TestCase):
    def test_the_archive_written_as_it_goes_reads_back(self):
        import claire_rounds_addon as ra
        from exp_runtime.exp import ExpArchive, encode_exp
        with tempfile.TemporaryDirectory() as folder:
            parts = {}
            for resource, data in ((26000, b'{"version":1}'), (27001, b'\x89PNG' * 1000), (1, b'meta')):
                path = Path(folder) / f'{resource}.bin'
                path.write_bytes(data)
                parts[resource] = path
            out = Path(folder) / 'out.exp'
            ra.write_exp(out, parts)
            written = out.read_bytes()
            self.assertEqual(written, encode_exp({r: p.read_bytes() for r, p in parts.items()}))
            self.assertEqual(ExpArchive(written).read(27001), b'\x89PNG' * 1000)


if __name__ == '__main__':
    unittest.main()
