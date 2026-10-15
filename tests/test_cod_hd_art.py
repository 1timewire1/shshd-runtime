"""Cause of Death's optional SHS HD art source (content.ContentLibrary.add_shs_hd_art, cod/hd_art.py)."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.cod.hd_art import derive_pack
from exp_runtime.content import ContentError, ContentLibrary, digest, import_game
from exp_runtime.ui_assets import ImagePack
from test_content import FAKE_HD_EXECUTABLE, archive, make_hd_ipa, metadata
from test_games import make_cod_ipa
from test_ipa import make_ipa
from test_vm import program


def pack(width, height, argb):
    """A one-frame raw ARGB image pack."""
    return (struct.pack('>Bhbhhh', 48, 1, 0, 0, 0, 0) + struct.pack('>hh', -1, 1)
            + struct.pack('>hh', width, height) + bytes(argb) * (width * height))


class DerivationTests(unittest.TestCase):
    def test_a_recoloured_frame_keeps_the_hd_size_and_takes_the_cod_colour(self):
        cod = pack(2, 1, (242, 80, 81, 81))             # grey, alpha 242
        hd = pack(4, 2, (255, 52, 112, 223))            # SHS blue, opaque
        data, report = derive_pack(cod, hd)
        frame = ImagePack.parse(data).images[0]
        self.assertEqual((frame.width, frame.height), (4, 2))
        self.assertEqual(frame.pixels[:4], bytes((80, 81, 81, 242)))
        self.assertEqual(report[0][0], 0)

    def test_an_unchanged_frame_is_kept_as_it_is(self):
        same = (200, 10, 200, 240)
        data, report = derive_pack(pack(2, 2, same), pack(4, 4, same))
        self.assertEqual(ImagePack.parse(data).images[0].pixels[:4], bytes((10, 200, 240, 200)))
        self.assertEqual(report[0][1], 'colours kept')

    def test_alpha_follows_cods_proportional_change_only(self):
        # A translucent strip CoD raised from 242 to 254 is raised the same way at 2x.
        data, _ = derive_pack(pack(2, 1, (254, 89, 90, 90)), pack(4, 2, (242, 89, 90, 90)))
        self.assertEqual(ImagePack.parse(data).images[0].pixels[3], 254)
        # Where CoD is as solid as SHS, an antialiased HD edge keeps its own alpha rather than being refitted.
        row = bytes((255, 86, 223, 255)) * 7 + bytes((120, 86, 223, 255))
        hd = struct.pack('>Bhbhhh', 48, 1, 0, 0, 0, 0) + struct.pack('>hh', -1, 1) + struct.pack('>hh', 8, 2) + row * 2
        frame = ImagePack.parse(derive_pack(pack(4, 1, (255, 170, 170, 170)), hd)[0]).images[0]
        self.assertEqual(frame.pixels[-4:], bytes((170, 170, 170, 120)))

    def test_a_renumbered_pack_changes_only_the_mapped_frames(self):
        def two(argb):
            return (struct.pack('>Bhbhhh', 48, 2, 0, 0, 0, 0) + struct.pack('>hh', -1, 2)
                    + (struct.pack('>hh', 2, 2) + bytes(argb) * 4) * 2)
        cod = struct.pack('>Bhbhhh', 48, 1, 0, 0, 0, 0) + struct.pack('>hh', -1, 1) + struct.pack('>hh', 1, 1) + bytes(
            (255, 170, 170, 170))
        data, report = derive_pack(cod, two((255, 86, 223, 255)), {1: 0})
        frames = ImagePack.parse(data).images
        self.assertEqual(frames[0].pixels[:3], bytes((86, 223, 255)))      # unmapped: SHS HD's own
        self.assertEqual(frames[1].pixels[:3], bytes((170, 170, 170)))
        self.assertEqual([index for index, _, _ in report], [1])

    def test_common_frames_are_whole_2x_stand_ins(self):
        from exp_runtime.cod.hd_art import BAR_FRAME, COMMON_FRAMES
        self.assertEqual(COMMON_FRAMES[37], 46)                               # the ring
        self.assertEqual([COMMON_FRAMES[7 + wedge] for wedge in range(16)], list(range(12, 28)))
        self.assertNotIn(BAR_FRAME, COMMON_FRAMES)                            # composed from 55 + 56

    def test_packs_with_different_frames_are_refused(self):
        two = struct.pack('>Bhbhhh', 48, 2, 0, 0, 0, 0) + struct.pack('>hh', -1, 2) + (
            struct.pack('>hh', 1, 1) + bytes(4)) * 2
        with self.assertRaises(ValueError):
            derive_pack(two, pack(2, 2, (0, 0, 0, 0)))


class LibraryLinkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.episode = archive({1: metadata('Authored shared story'), 25001: program(0x33).to_bytes()})
        make_cod_ipa(self.root / 'cod.ipa', self.episode)
        self.hd = self.root / 'shs-hd.ipa'
        make_hd_ipa(self.hd, {311: b'HD portrait mask', 1500: b'SHS HD shared content'})
        self.patch = patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_linking_serves_only_cods_own_map_and_never_turns_on_shs_hd(self):
        import_game(self.root / 'cod.ipa', [], self.root / 'cod', game='cod')
        with ContentLibrary(self.root / 'cod') as cod:
            self.assertIsNone(cod.hd_asset(268))         # nothing linked: the base game exactly as before
            self.assertTrue(cod.add_shs_hd_art(self.hd))
            self.assertFalse(cod.add_shs_hd_art(self.hd))
            self.assertEqual(cod.hd_asset(268), b'HD portrait mask')
            self.assertEqual(cod.read_asset(268), b'HD portrait mask')
            self.assertIsNone(cod.hd_asset(1500))        # no SHS id is taken by number alone
            self.assertIsNone(cod.hd_ipa)                # SHS HD's own screens never switch on for CoD
            self.assertIsNone(cod.hd_asset(155))         # common frames come only through cod_hd_common
            self.assertIsNone(cod.cod_hd_common())       # this SHS HD bundle has no pack 155
        with ContentLibrary(self.root / 'cod') as reopened:
            self.assertEqual(reopened.hd_asset(268), b'HD portrait mask')

    def test_only_a_cod_library_takes_the_art_source(self):
        make_ipa(self.root / 'shs.ipa', self.episode)
        import_game(self.root / 'shs.ipa', [], self.root / 'shs', game='shs')
        with ContentLibrary(self.root / 'shs') as shs, self.assertRaisesRegex(ContentError, 'Cause of Death'):
            shs.add_shs_hd_art(self.hd)
        manifest = json.loads((self.root / 'shs' / 'library.json').read_text())
        (self.root / 'shs' / 'library.json').write_text(json.dumps(dict(manifest, shs_hd_art=dict(
            file='content/x.ipa', sha256='0' * 64, executable_sha256='x'))))
        with self.assertRaises(ContentError):
            ContentLibrary(self.root / 'shs')


class CodHousingTests(unittest.TestCase):
    def test_cods_bubble_clip_cuts_10_unit_corners(self):
        from types import SimpleNamespace
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Rect
        box = Rect(20, 300, 280, 100)
        for game, corner in (('cod', 10), ('shs', 5)):
            renderer = SimpleNamespace(game_id=lambda game=game: game, bubble_polygon=DialogueRenderer.bubble_polygon)
            outline = DialogueRenderer.housing_polygon(renderer, box)
            self.assertEqual(outline[:3], [(13, 407), (13, 293 + corner), (13 + corner, 293)])

    def test_only_the_free_edition_keeps_room_for_its_in_game_banner(self):
        from types import SimpleNamespace
        from exp_runtime.cod.profile import in_game_banner
        app = lambda bundle: SimpleNamespace(manifest={'ipa': {'app': {'CFBundleIdentifier': bundle}}})
        self.assertTrue(in_game_banner(app('com.ea.causeofdeathfree.bv')))
        self.assertFalse(in_game_banner(app('com.ea.causeofdeath')))
        self.assertFalse(in_game_banner(SimpleNamespace()))

    def test_cods_portrait_layer_is_flush_with_the_housing(self):
        from exp_runtime.desktop_dialogue import DialogueRenderer
        self.assertEqual((DialogueRenderer.COD_PORTRAIT_BOTTOM, DialogueRenderer.HD_PORTRAIT_LAYER[1]), (320, 320))
        self.assertEqual(DialogueRenderer.HD_PORTRAIT_BOTTOM, 318)


class CodTextStyleTests(unittest.TestCase):
    def test_narration_and_body_follow_cods_own_fonts(self):
        from exp_runtime.dialogue import dialogue_styles
        _, _, font, narration = dialogue_styles(1, narrator=True, game='cod')
        self.assertEqual((font, narration.color, narration.markers), ('TrebuchetMS_Italic16', (0, 0, 0),
                                                                      (('`', (180, 109, 26)),)))
        _, _, _, body = dialogue_styles(1, game='cod')
        self.assertEqual((body.color, body.markers), ((0, 0, 0), (('`', (254, 53, 53)),)))   # ';' is plain text
        _, _, _, rose = dialogue_styles(2, game='cod')
        self.assertEqual(rose.markers, (('`', (41, 104, 221)),))
        # SHS keeps its own.
        _, _, _, shs = dialogue_styles(1, narrator=True)
        self.assertEqual(shs.color, (223, 163, 52))
        self.assertEqual(dialogue_styles(1)[3].markers, (('`', (254, 53, 0)), (';', (1, 76, 215))))

    def test_vector_fonts_need_the_art_source(self):
        from types import SimpleNamespace
        from exp_runtime import vector_text
        base = object()
        with patch('exp_runtime.fonts.load_font', return_value=base):
            plain = SimpleNamespace(kind='ipa', game_id='cod', shs_hd_art=None)
            self.assertIs(vector_text.load_font(plain, 'ArialRoundedMTBold16'), base)
            linked = SimpleNamespace(kind='ipa', game_id='cod', shs_hd_art=object())
            with patch.object(vector_text, 'cod_vector_font', return_value='vector') as upgrade:
                self.assertEqual(vector_text.load_font(linked, 'ArialRoundedMTBold16'), 'vector')
                self.assertEqual(vector_text.load_font(linked, 'ArialRoundedMTBold16'), 'vector')
                upgrade.assert_called_once()                  # cached per library


if __name__ == '__main__':
    unittest.main()
