"""Claire Hart Dialogue (Claire Hart plan Stage 0; owner, 2026-11-19): CoD's dialogue in Claire Hart's speech bubbles and Romic,
with CoD's attached ring; Off, Claire Hart Cases (pack 31500) or All Episodes."""
import json
from types import SimpleNamespace
import unittest

from exp_runtime.content import EpisodeResources
from exp_runtime.dialogue import SKIN_BODY, SKIN_NAME, SKIN_NARRATION, DialogueLayout
from exp_runtime.ui_assets import Rect

SPEC = {'version': 1, 'density': 4, 'text': [112, 45, 25], 'emphasis': [166, 132, 22], 'fonts': {'body': 28004, 'bold': 28005},
        'speaker': {'picture': 29101, 'slice': [80, 67, 80, 57], 'outset': [10, 10, 10, 10]},
        'narrator': {'picture': 29103, 'slice': [63, 63, 63, 63], 'outset': [10, 10, 10, 10]},
        'tab': {'picture': 29102, 'size': [663, 143], 'caps': [93, 93], 'base': 104, 'name': [7, 104], 'inset': 50},
        'ring': 29104, 'disc': 29105, 'pill': [29106, 29107], 'slot': 29108}


def episode(pack, choice='cases', spec=True):
    held = {29100: json.dumps(SPEC).encode()} if spec else {}
    library = SimpleNamespace(game_id='cod', ch_dialogue=choice,
                              addon_resource=lambda addon, resource: held.get(resource) if addon == 'chc' else None)
    resources = object.__new__(EpisodeResources)
    resources.library, resources.record = library, dict(pack_id=pack, name='test')
    resources._presentation = {}
    return resources


class SkinChoiceTests(unittest.TestCase):
    def test_off_claire_hart_cases_or_all_episodes(self):
        from exp_runtime.cod import profile
        self.assertEqual(profile.DIALOGUE_SKIN, ('chc', 29100, (31500,)))
        self.assertEqual(episode(31500).dialogue_skin()['addon'], 'chc')
        self.assertIsNone(episode(30000).dialogue_skin())                    # CoD's own: only with All Episodes
        self.assertEqual(episode(30000, 'all').dialogue_skin()['tab']['base'], 104)
        self.assertIsNone(episode(31500, 'off').dialogue_skin())
        self.assertIsNone(episode(31500, spec=False).dialogue_skin())        # an older chc: CoD's own look

    def test_the_setting_is_kept_and_named(self):
        from exp_runtime.desktop_pause_hd import CH_DIALOGUE_NAMES, PER_GAME_CHOICES
        from exp_runtime.menu import SHARED_PREFERENCES
        self.assertEqual(SHARED_PREFERENCES['ch_dialogue'], ('off', 'cases', 'all'))
        self.assertEqual(list(CH_DIALOGUE_NAMES.values()), ['Off', 'Claire Hart Cases', 'All Episodes'])
        self.assertIn('ch_dialogue', PER_GAME_CHOICES)


class SkinTabTests(unittest.TestCase):
    def name(self, width):
        return SimpleNamespace(width=width, ink_bounds=(0, 2, width, 14))

    def test_the_tab_sits_beside_the_ring_on_the_speakers_side(self):
        box, ring = Rect(30, 300, 260, 70), Rect(0, 230, 128, 128)
        tab, origin = DialogueLayout.skin_tab(SPEC, box, ring, 1, self.name(80))
        self.assertEqual((tab.x, tab.y), (ring.x + ring.width - 6, box.y - 10 - 104 / 4))
        self.assertEqual(tab.width, 80 + 2 * 50 / 4)
        self.assertAlmostEqual(origin[0], tab.x + (tab.width - 80) / 2)
        right_ring = Rect(200, 230, 128, 128)
        tab, _ = DialogueLayout.skin_tab(SPEC, box, right_ring, 2, self.name(80))
        self.assertEqual(tab.x + tab.width, right_ring.x + 6)
        tab, _ = DialogueLayout.skin_tab(SPEC, box, None, 3, self.name(80))         # no portrait: at the bubble's left
        self.assertEqual(tab.x, box.x - 10 + 12)

    def test_a_long_name_stays_on_the_bubble(self):
        box = Rect(30, 300, 260, 70)
        tab, _ = DialogueLayout.skin_tab(SPEC, box, Rect(0, 230, 128, 128), 1, self.name(240))
        self.assertLessEqual(tab.x + tab.width, box.x + box.width + 10 - 4)

    def test_the_faces_are_romic_bold_and_narration_slanted(self):
        self.assertEqual((SKIN_BODY, SKIN_NAME, SKIN_NARRATION), ('CHRomicBold16', 'CHRomicBold18', 'CHRomicBoldItalic16'))


class SlantTests(unittest.TestCase):
    def test_a_slanted_glyph_leans_right_above_its_baseline(self):
        import pygame
        from exp_runtime.vector_text import _slanted
        pygame.init()
        glyph = pygame.Surface((4, 10), pygame.SRCALPHA)
        glyph.fill((0, 0, 0, 0))
        glyph.fill((255, 0, 0, 255), (0, 0, 1, 10))                     # a vertical stroke at x 0
        out, shift = _slanted(glyph, 0.5, 8)                              # baseline at row 8
        lit = lambda y: next(x for x in range(out.get_width()) if out.get_at((x, y))[3])   # noqa: E731
        self.assertEqual(lit(0) - lit(8), 4)                              # 8 rows above: 4 pixels right
        self.assertLess(shift, 0)                                         # the rows below lean left of the pen
        self.assertEqual(out.get_height(), 10)


class CoveredGlyphTests(unittest.TestCase):
    def test_the_cmap_reader_knows_what_a_face_maps(self):
        import pygame
        from pathlib import Path
        from exp_runtime.vector_text import ttf_covered
        path = Path(pygame.__file__).parent / pygame.font.get_default_font()
        covered = ttf_covered(path.read_bytes())
        self.assertTrue({ord('A'), ord('/'), ord('&')} <= covered)
        self.assertIsNone(ttf_covered(b'not a font'))


if __name__ == '__main__':
    unittest.main()
