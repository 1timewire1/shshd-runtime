"""Claire Hart Dialogue (Claire Hart plan Stage 0; owner, 2026-11-19): CoD's dialogue in Claire Hart's speech bubbles and Romic,
with CoD's attached ring; Off, Claire Hart Cases (pack 31500) or Everywhere (Claire Hart UI)."""
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
        self.assertEqual(profile.DIALOGUE_SKINS['classic'], ('chc', 29100, (31500,), 'CHRomic'))
        self.assertEqual(episode(31500).dialogue_skin()['addon'], 'chc')
        self.assertIsNone(episode(30000).dialogue_skin())                    # CoD's own: only with Everywhere
        self.assertEqual(episode(30000, 'all').dialogue_skin()['tab']['base'], 104)
        self.assertIsNone(episode(31500, 'off').dialogue_skin())
        self.assertIsNone(episode(31500, spec=False).dialogue_skin())        # an older chc: CoD's own look

    def test_each_choice_picks_its_skin(self):
        """Owner, 2026-11-24: Auto gives each game's cases its own skin and CoD's episodes and menus none; a game by name is
        everyone's; Off is no one's. The old Off / Cases / Everywhere carry over as Off / Auto / Claire Hart Classic."""
        from exp_runtime.content import skin_choice, skin_entry
        addon = lambda choice, pack: (skin_entry('cod', choice, pack) or (None,))[0]     # noqa: E731
        self.assertEqual([addon('auto', pack) for pack in (31500, 31900, 1, None)], ['chc', 'ch2', None, None])
        self.assertEqual([addon('classic', pack) for pack in (31500, 31900, 1, None)], ['chc'] * 4)
        self.assertEqual([addon('shadows', pack) for pack in (31500, 31900, 1, None)], ['ch2'] * 4)
        self.assertEqual([addon('off', pack) for pack in (31500, 31900)], [None, None])
        self.assertEqual([skin_choice(v) for v in ('off', 'cases', 'all', 'shadows', 'nonsense')],
                         ['off', 'auto', 'classic', 'shadows', 'auto'])
        self.assertIsNone(skin_entry('shs', 'classic', 31500))          # (SHS has no Claire Hart skin)

    def test_the_setting_is_kept_and_named(self):
        from exp_runtime.desktop_pause_hd import CH_DIALOGUE_NAMES, PER_GAME_CHOICES
        from exp_runtime.menu import SHARED_PREFERENCES
        self.assertEqual(SHARED_PREFERENCES['ch_dialogue'], ('auto', 'off', 'classic', 'shadows'))
        self.assertEqual(list(CH_DIALOGUE_NAMES.values()), ['Auto', 'Off', 'Claire Hart Classic', 'Secret in the Shadows'])
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

    def test_the_tab_comes_in_ahead_of_its_name(self):
        """Owner, 2026-11-20: a new speaker's name showed over the backdrop before its tab, which waited for the box to
        finish growing. The tab comes in from when the box's strip is in place, faster than the name fades in."""
        try:
            from exp_runtime.desktop_dialogue import DialogueRenderer
        except ImportError as error:                    # (the player's pygame)
            self.skipTest(str(error))
        from exp_runtime.dialogue_animation import DialogueAnimation, DialoguePortrait
        motion = DialogueAnimation(20, portrait=DialoguePortrait(1, 2, 1, 0), changed=True, box_grow=True)
        start = motion.name_delay_ms
        for elapsed in range(start - 50, start + 400, 10):
            motion.elapsed_ms = elapsed
            self.assertGreaterEqual(DialogueRenderer.skin_tab_alpha(motion), motion.name_alpha)
        motion.elapsed_ms = start + DialogueRenderer.SKIN_TAB_FADE_MS
        self.assertEqual(DialogueRenderer.skin_tab_alpha(motion), 255)
        box = motion.box_rect(Rect(30, 300, 260, 70), Rect(0, 230, 128, 128))
        self.assertEqual((box.y, box.width), (300, 260))                # its top edge is in place from then on
        self.assertLess(box.height, 70)

    def test_text_wraps_around_the_ring_on_either_side(self):
        """Owner, 2026-11-20: the skin's ring is whole over the box, so each line clears its circle (a third line ran
        under it with CoD's two fixed insets); a narrator's ring is smaller (SKIN_NARRATION_RING) and its text with it."""
        import math
        from exp_runtime import dialogue
        from exp_runtime.fonts import TextStyle
        style, rect = TextStyle(11, 10), Rect(37, 304, 246, 80)
        x0, y0 = 37 - dialogue.COD_TYPING_PAD, 304 - dialogue.COD_TYPING_PAD + dialogue.COD_BASELINE_DROP
        for mode, portrait in ((1, Rect(-7, 225, 128, 128)), (2, Rect(199, 225, 128, 128))):
            insets = dialogue.skin_ring_insets(portrait, mode, rect, style, True)
            cx, cy = portrait.x + 64, portrait.y + 64
            for row, inset in enumerate(insets[:4]):
                top, bottom = y0 + 21 * row, y0 + 21 * row + 11
                # the line's end on the ring's side, against the circle at that row
                edge = x0 + inset if mode == 1 else x0 + rect.width + inset
                dy = 0 if top <= cy <= bottom else min(abs(top - cy), abs(bottom - cy))
                reach = math.sqrt(max(0, 64 ** 2 - dy ** 2))
                self.assertGreaterEqual(abs(edge - cx), reach if reach else 0, (mode, row))
            self.assertNotEqual(insets[2], 0)                       # the third line clears the ring too
            self.assertEqual(insets[4], 0)                          # below it, full width
            narration = dialogue.skin_ring_insets(portrait, mode, rect, style, True, 64 * dialogue.SKIN_NARRATION_RING)
            self.assertLess(abs(narration[2]), abs(insets[2]))

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



class SequelSkinTests(unittest.TestCase):
    def test_the_sequels_spec_has_what_the_renderer_reads(self):
        """Secret in the Shadows UI (owner, 2026-11-24; tools/translate/ch2_dialogue_skin.py): the pieces Classic's skin
        has, its Roboto under its own prefix, the name in capitals in teal, its purple CONTINUE."""
        import importlib.util
        import sys
        from pathlib import Path
        if importlib.util.find_spec('PIL') is None:
            self.skipTest('Pillow is needed')
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
        import ch2_dialogue_skin as skin
        from exp_runtime.cod.profile import DIALOGUE_SKINS
        from exp_runtime.vector_text import SKIN_FONTS
        spec = skin.spec()
        for key in ('speaker', 'narrator', 'tab', 'ring', 'disc', 'pill', 'slot', 'fonts', 'text', 'density', 'ui'):
            self.assertIn(key, spec)
        prefix = DIALOGUE_SKINS['shadows'][3]
        self.assertIn(prefix, SKIN_FONTS)
        self.assertTrue(all(name.startswith(prefix) for name in spec['font_names'].values()))
        self.assertEqual((spec['name_upper'], spec['name_colour'], spec['pill_label']), (True, [27, 245, 208], 'CONTINUE'))
        for key in ('panel', 'popup', 'row', 'row_lit', 'capsule', 'timer', 'close', 'colours'):
            self.assertIn(key, spec['ui'])
        box = skin.box_picture()
        self.assertEqual(box.width, skin.px(2 * skin.CAP + 2))           # (its caps, and a little middle to stretch)
        self.assertGreater(box.getpixel((box.width // 2, box.height // 2))[0], 200)     # (the cream paper in the middle)


if __name__ == '__main__':
    unittest.main()
