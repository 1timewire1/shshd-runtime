"""shshd-runtime: the ch2rounds builder's own rules (tools/translate/claire_hart_shadows_rounds.py; Claire Hart plan S3
step 3): PNG text chunks dropped and uncompressed sprites re-encoded with their pixels kept, the round keys, and a scene's
story entries resolved (multi-part objects by their assembled sprite, sprite-id entries, the boots' spelling)."""
import importlib.util
import io
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
HAS_PIL = importlib.util.find_spec('PIL') is not None


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


@unittest.skipUnless(HAS_PIL, 'Pillow is needed')
class PngTests(unittest.TestCase):
    def test_text_goes_and_the_pixels_stay(self):
        from PIL import Image
        import claire_hart_shadows_rounds as r
        out = io.BytesIO()
        Image.new('RGBA', (8, 6), (10, 20, 30, 255)).save(out, 'PNG')
        plain = out.getvalue()
        padded = plain[:33] + chunk(b'iTXt', b'XML:com.adobe.xmp\x00' + b'x' * 50000) + plain[33:]
        stripped = r.without_text(padded)
        self.assertEqual(stripped, plain)
        self.assertEqual(r.without_text(b'not a png'), b'not a png')

    def test_an_uncompressed_sprite_is_reencoded_losslessly(self):
        from PIL import Image
        import claire_hart_shadows_rounds as r
        raw = b''.join(b'\x00' + bytes((x * 7 % 256, 40, 90, 255)) * 64 for x in range(64))
        stored = zlib.compress(raw, 0)                       # (its pixels stored uncompressed, as the heavy sprites')
        heavy = (r.PNG_SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 6, 0, 0, 0))
                 + chunk(b'IDAT', stored) + chunk(b'IEND', b''))
        small = r.compact(heavy)
        self.assertLess(len(small), len(heavy) / 2)
        pixels = lambda data: Image.open(io.BytesIO(data)).convert('RGBA').tobytes()      # noqa: E731
        self.assertEqual(pixels(small), pixels(heavy))


class RoundKeyTests(unittest.TestCase):
    def test_sequel_keys_stay_clear_of_classics(self):
        import claire_hart_shadows_rounds as r
        from exp_runtime.claire_round_services import round_key
        self.assertEqual(r.round_key(31, 4, 5), 53145)
        self.assertLess(round_key('E266', 5), r.round_key(1, 1, 1))


class StoryEntryTests(unittest.TestCase):
    def scene(self):
        import claire_hart_shadows_rounds as r
        scene = r.SceneData.__new__(r.SceneData)
        sprite = lambda name, end: {'id': f'room_{name}_{end}'}          # noqa: E731
        scene.objects = [['Pineapple', 'o', sprite('pineapple', 'normal'), sprite('pineapple', 'found'), [0, 0]],
                         ['Apple', 'o', sprite('apple', 'normal'), sprite('apple', 'found'), [0, 0]],
                         ['Locket half', 'c', sprite('lockethalfa', 'normal'), sprite('lockethalfa', 'found'), [0, 0]],
                         ['Locket half', 'c', sprite('lockethalfb', 'normal'), sprite('lockethalfb', 'found'), [0, 0]],
                         ['Locket', 'w', None, sprite('locket', 'found'), [0, 0]],
                         ["Women's boots", 'w', None, {'id': 'room_womensboots_found'}, [0, 0]],
                         ['Knife', 'p', sprite('drawer_knife', 'normal'), sprite('drawer_knife', 'found'), [0, 0]]]
        scene.parts = {4: [2, 3], 5: []}
        return scene

    def test_entries_resolve_by_name_assembled_sprite_and_sprite_id(self):
        scene = self.scene()
        self.assertEqual(scene.story_index('apple'), 1)                  # (by name: not the pineapple the game found)
        self.assertEqual(scene.story_index('locket_found'), 4)           # (a multi-part object by its assembled sprite)
        self.assertEqual(scene.story_index('womansboots'), 5)            # (its other spelling)
        self.assertEqual(scene.story_index('drawer_knife_normal'), 6)    # (an entry written as a sprite's id)
        self.assertIsNone(scene.story_index('Nothing'))
        self.assertIsNone(scene.story_index('anchor'))


if __name__ == '__main__':
    unittest.main()
