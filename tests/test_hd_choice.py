import os
import unittest
from pathlib import Path

from exp_runtime.hd_choice import argb, units, wedge_opacity, wedge_position


class CircleTimerTests(unittest.TestCase):
    def test_each_wedge_holds_then_fades_in_its_own_sixteenth(self):
        # SHSCircleTimerLayer: model opacity 1 until the wedge's animation begins at index/16 of the timeout,
        # then keyframes 0.8, 0.8, 0 at 0, 0.4, 1 of a sixteenth (linear, filled forwards).
        total = 16000
        self.assertEqual(wedge_opacity(3, 2999, total), 1.)
        self.assertEqual(wedge_opacity(3, 3000, total), .8)
        self.assertEqual(wedge_opacity(3, 3399, total), .8)
        self.assertAlmostEqual(wedge_opacity(3, 3700, total), .4)
        self.assertEqual(wedge_opacity(3, 4000, total), 0.)
        self.assertEqual(wedge_opacity(0, 16000, total), 0.)
        self.assertEqual(wedge_opacity(15, 0, total), 1.)

    def test_wedges_run_clockwise_from_twelve_around_the_layer_centre(self):
        # initWithImages: quadrants top-right, bottom-right, bottom-left, top-left around (50, 50).
        self.assertEqual(wedge_position(0, 19, 50), (50, 0))
        self.assertEqual(wedge_position(4, 50, 19), (50, 50))
        self.assertEqual(wedge_position(8, 19, 50), (31, 50))
        self.assertEqual(wedge_position(15, 50, 19), (0, 31))


class QuizPacingTests(unittest.TestCase):
    def game(self):
        from exp_runtime.minigames import WordGame
        from exp_runtime.randomness import Random48
        random = Random48()
        game = WordGame(['a', 'b'], ['c', 'd', 'e'], 20000, 0, 20000, 0, hd=True, entry_ms=0)
        game.deal(random)
        return game, random

    def test_a_tap_scores_after_the_selection_then_flies_and_deals(self):
        # SHSMenu selectionCallback 0.1 s -> handleMenuSelection -> flyAwayLabels 0.5 s -> deal -> input 0.7 s later.
        game, random = self.game()
        good = game.weights.index(1)
        self.assertFalse(game.pick(good, random))
        self.assertFalse(game.pick(good, random))           # a second tap while one is pending is ignored
        game.tick(99, random)
        self.assertEqual((game.score, game.selected), (0, good))
        game.tick(1, random)
        self.assertEqual((game.score, game.scored, game.fly_off_ms, game.round), (1, 1, 500, 1))
        game.tick(499, random)
        self.assertEqual(game.round, 1)
        game.tick(1, random)
        self.assertEqual((game.round, game.fly_on_ms, game.shown_ms), (2, 700, 0))
        self.assertFalse(game.pick(0, random))
        self.assertEqual(game.selected, -1)                # input stays off until the fly-on timer ends
        game.tick(700, random)
        game.pick(0, random)
        self.assertEqual(game.selected, 0)
        game.validate()

    def test_the_game_waits_for_a_pending_selection_before_ending(self):
        game, random = self.game()
        game.tick(19950, random)
        game.pick(0, random)
        self.assertFalse(game.tick(60, random))             # out of time, but a selection is pending
        self.assertTrue(game.tick(40, random))


class FlairLayoutTests(unittest.TestCase):
    def test_letters_are_spaced_centred_over_the_housing_and_padded(self):
        from exp_runtime.dialogue_notice import hd_letter_origins
        origins = hd_letter_origins([20, 10], 50, 503, 28)
        # W = 20 + 10 + 3 = 33; x0 = 50 + (256 - 33) / 2 = 161.5; top = 503 - 60 - 14 + 20 = 449.
        self.assertEqual(origins, [(181.5, 449), (204.5, 449)])
        self.assertEqual(hd_letter_origins([400], 600, 0, 0)[0][0], 748 - 400 + 20)
        self.assertEqual(hd_letter_origins([400], -300, 0, 0)[0][0], 20)

    def test_cause_of_death_uses_its_own_raise_limit_and_housing(self):
        # CoD 1.4.7's startLetterEffectAnimation: a 30-point raise and a 300-point limit over its 128-point layer;
        # the 10-point padding is fitted to IMG_0322 / IMG_0412 (the banner's outline starts 8 points in).
        from exp_runtime.dialogue_notice import COD_NOTICE, hd_letter_origins
        origins = hd_letter_origins([20, 10], 50, 250, 14, **COD_NOTICE)
        # W = 33; x0 = 50 + (128 - 33) / 2 = 97.5; top = 250 - 30 - 7 + 10 = 223.
        self.assertEqual(origins, [(107.5, 223), (130.5, 223)])
        self.assertEqual(hd_letter_origins([240], -60, 0, 0, **COD_NOTICE)[0][0], 10)      # "Detective Score Up!"
        self.assertEqual(hd_letter_origins([200], 250, 0, 0, **COD_NOTICE)[0][0], 300 - 200 + 10)


class PanelTransitionTests(unittest.TestCase):
    """`SHSUIMenu::internalTransitionOn` / `Off`: the menu view's alpha over 0.25 s, ease in/out; a pick waits 0.1 s."""

    def test_the_panel_fades_in_over_a_quarter_second(self):
        from exp_runtime.hd_choice import panel_alpha
        self.assertAlmostEqual(panel_alpha(0), 0)
        self.assertAlmostEqual(panel_alpha(125), .5, places=3)
        self.assertAlmostEqual(panel_alpha(250), 1)

    def test_after_a_pick_the_row_shows_pressed_for_a_tenth_then_the_panel_fades_out(self):
        from exp_runtime.hd_choice import panel_alpha
        self.assertAlmostEqual(panel_alpha(0, closing_ms=0), 1)        # a pick during the fade-in shows it whole
        self.assertAlmostEqual(panel_alpha(1000, closing_ms=100), 1)
        self.assertAlmostEqual(panel_alpha(1000, closing_ms=225), .5, places=3)
        self.assertAlmostEqual(panel_alpha(1000, closing_ms=350), 0)

    def test_the_choice_is_answered_only_when_the_fade_out_ends(self):
        from types import SimpleNamespace
        from exp_runtime.desktop import Desktop
        action = object()
        answered = []
        fake = SimpleNamespace(session=SimpleNamespace(pending=action), _pick=lambda act, index: answered.append(index),
                               choice_closing=dict(action=action, index=2, ms=0))
        Desktop._tick_choice_closing(fake, 340)
        self.assertEqual(answered, [])
        Desktop._tick_choice_closing(fake, 10)
        self.assertEqual((answered, fake.choice_closing), ([2], None))

    def test_a_closing_choice_that_is_no_longer_pending_is_dropped(self):
        from types import SimpleNamespace
        from exp_runtime.desktop import Desktop
        fake = SimpleNamespace(session=SimpleNamespace(pending=object()), _answer=self.fail,
                               choice_closing=dict(action=object(), index=0, ms=0))
        Desktop._tick_choice_closing(fake, 1000)
        self.assertIsNone(fake.choice_closing)


class GeometryTests(unittest.TestCase):
    def test_frame_points_map_to_the_column(self):
        # The housing of a mode-1 choice portrait: centre x 104 + 74, top at the panel's top.
        self.assertEqual(units(178 - 128, 206), (-7, 76.5))
        self.assertEqual(argb(0xf3eff9fa), (239, 249, 250, 243))


@unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content unavailable')
class PhotographedChoiceTests(unittest.TestCase):
    """SHSWidgetMenu::solveMetrics against the owner's light-mode photos (IMG_0226, IMG_0227, IMG_0222)."""

    def setUp(self):
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        import pygame
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.quit)
        from exp_runtime.content import ContentLibrary
        self.library = ContentLibrary(Path('.shs-library'))
        self.addCleanup(self.library.close)
        if self.library.hd_raw_resource(16) is None:
            self.skipTest('no HD app bundle imported')

    def page(self, **details):
        from exp_runtime.hd_choice import (DESCRIPTION_GAP, OPTION_GAP, TITLE_GAP, FontMetrics, hd_choice_page)
        from exp_runtime.hd_layout import HdLayouts
        from exp_runtime.vector_text import cap_height, descent, load_font, load_font_sized
        title = load_font(self.library, 'PajamaHip26')
        body = load_font(self.library, 'ArialRoundedMTBold16')
        option = load_font_sized(self.library, 'ArialRoundedMTBold16', 15)
        has_portrait = details.pop('has_portrait', True)
        details = dict(dict(title='Make your choice!', portrait_mode=1, timeout_ms=0, enabled=[True] * 3), **details)
        return hd_choice_page(HdLayouts(self.library), details, theme=1, has_portrait=has_portrait,
                              title=FontMetrics(title, cap_height(title), TITLE_GAP / 2, descent(title)),
                              title_font='PajamaHip26',
                              description=FontMetrics(body, cap_height(body), DESCRIPTION_GAP / 2),
                              description_font='ArialRoundedMTBold16',
                              option=FontMetrics(option, cap_height(option), OPTION_GAP / 2),
                              color=(1, 76, 215), option_color=(2, 76, 215))

    def test_untimed_choice_with_a_portrait(self):
        page = self.page(text='What are you into?', options=['Working out.', 'Hanging out with the ladies.',
                                                             'Watching TV.'])
        # The row separators in IMG_0226 are at 544 (description), 632, 720 and 808 points.
        self.assertEqual((page.top, page.header_height, page.description_height, page.rows_top),
                         (267, 142, 136, 545))
        self.assertTrue(page.tall_title)
        self.assertEqual(page.footer_top + page.footer_height, 849)

    def test_timed_choice_places_the_wheel_in_the_footer_notch(self):
        page = self.page(text='Hey, are you a parking ticket?', timeout_ms=12000,
                         options=["Cuz you'd look great on my windshield.",
                                  'Cuz I feel a sudden urge to pay you 10 dollars.',
                                  "Cuz you've got fine written all over you."])
        self.assertEqual((page.top, page.rows_top, page.footer_height), (206, 484, 120))
        self.assertEqual(page.portrait.y, 76.5)
        self.assertEqual(page.timer_center, units(385, 484 + 264 + 61))

    def test_survey_without_a_character(self):
        page = self.page(has_portrait=False, title='Give us feedback!', enabled=[True, True],
                         text='Help us improve the game by taking this optional survey.',
                         options=['Take Survey.', 'Skip Survey.'])
        self.assertEqual((page.top, page.header_height, page.rows_top), (288, 126, 520))
        self.assertFalse(page.tall_title)
        self.assertIsNone(page.portrait)


class CodGeometryTests(unittest.TestCase):
    """Cause of Death's iPhone SHSWidgetMenu is SHS HD's with every constant halved (hd_choice.COD_GEOMETRY)."""

    def test_points_are_column_units_and_the_constants_are_halved(self):
        from exp_runtime.hd_choice import COD_GEOMETRY as cod, HD_GEOMETRY as hd
        self.assertEqual(cod.units(20, 117), (20, 117))
        self.assertEqual((cod.panel_x, cod.panel_width, cod.row_height, cod.description_minimum),
                         (20, 280, hd.row_height // 2, hd.description_minimum // 2))
        self.assertEqual(cod.menu_line_offsets[2], tuple(o // 2 for o in hd.menu_line_offsets[2]))
        # Both put the housing and the timer at the same place in the column.
        self.assertEqual(cod.units(cod.panel_x + cod.portrait_left, 0)[0], hd.units(hd.panel_x + hd.portrait_left, 0)[0])
        self.assertEqual(cod.units(cod.portrait_right - cod.panel_x, 0)[0],
                         hd.units(hd.portrait_right - hd.panel_x, 0)[0])

    def test_labels_fly_from_its_own_offset_and_the_wheel_turns_on_its_own_layer(self):
        from exp_runtime.hd_choice import COD_GEOMETRY, label_offsets
        self.assertEqual(label_offsets(0, COD_GEOMETRY), (-200, 274))       # not HD's -600 halved
        self.assertEqual(label_offsets(1, COD_GEOMETRY), (0, 0))
        self.assertEqual(wedge_position(0, 10, 25, centre=25), (25, 0))

    def test_the_quiz_layers_are_halved_but_the_effect_rises_as_far(self):
        # setScored's layers (widget 22 nodes 17 / 18) are halved; doScoreEffectAnimation is the same code in both
        # builds, so the effect rises 30 points: twice as far in column units.
        from exp_runtime.hd_choice import COD_GEOMETRY as cod, HD_GEOMETRY as hd
        for mine, theirs in ((cod.score_box, hd.score_box), (cod.effect_box, hd.effect_box)):
            self.assertEqual(mine[2:], tuple(v // 2 for v in theirs[2:]))
            # CoD's own layout bank rounds an odd position up (373 -> 187, 493 -> 247).
            self.assertEqual(mine[:2], tuple(-(-v // 2) for v in theirs[:2]))
        self.assertEqual(cod.effect_rise / cod.density, 2 * hd.effect_rise / hd.density)
        self.assertEqual((cod.running_man, hd.running_man), ((23, 5, .07), (28, 5, .07)))


@unittest.skipUnless(os.environ.get('EXP_COD_LIBRARY') and Path(os.environ['EXP_COD_LIBRARY'], 'library.json').is_file(),
                     'set EXP_COD_LIBRARY to a Cause of Death library with the SHS HD art source')
class PhotographedCodChoiceTests(unittest.TestCase):
    """solveMetrics at CoD's scale against the owner's 1x photos (2 px per point): IMG_0483 and IMG_0406."""

    def setUp(self):
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        import pygame
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.quit)
        from exp_runtime.choice import ChoiceLayout
        from exp_runtime.content import ContentLibrary
        self.library = ContentLibrary(Path(os.environ['EXP_COD_LIBRARY']))
        self.addCleanup(self.library.close)
        self.bank = ChoiceLayout(self.library.open_episode(self.library.episodes[0]['id'])).bank

    def page(self, **details):
        from exp_runtime.hd_choice import COD_GEOMETRY, FontMetrics, hd_choice_page
        from exp_runtime.hd_layout import BankLayouts
        from exp_runtime.vector_text import cap_height, descent, load_font
        title, body, option = (load_font(self.library, name)
                               for name in ('PajamaHipY26', 'ArialRoundedMTBold16', 'ArialRoundedMTBold15'))
        if cap_height(title) is None:
            self.skipTest('no vector fonts (the library has no SHS HD art source)')
        has_portrait = details.pop('has_portrait', True)
        details = dict(dict(portrait_mode=1, timeout_ms=0, enabled=[True] * len(details['options'])), **details)
        return hd_choice_page(BankLayouts(self.bank), details, theme=0, has_portrait=has_portrait,
                              title=FontMetrics(title, cap_height(title), 8, descent(title)), title_font='PajamaHipY26',
                              description=FontMetrics(body, cap_height(body), 10),
                              description_font='ArialRoundedMTBold16',
                              option=FontMetrics(option, cap_height(option), 8), color=(0, 0, 0),
                              option_color=(0, 0, 0), geometry=COD_GEOMETRY)

    def test_choice_without_a_character(self):
        page = self.page(has_portrait=False, title='Make your choice.', text='What do you do?',
                         options=['Check your messages.', 'Watch TV.', 'Go to bed.'])
        # IMG_0483's rules are at 210 (the description's), 254, 298 and 342 points.
        self.assertEqual((page.top, page.header_height, page.description_height, page.rows_top), (117, 63, 31, 211))
        self.assertEqual(page.footer_top, 343)

    def test_choice_with_a_portrait_and_a_two_line_description(self):
        page = self.page(title='Make your choice!', text='What do you want to do?',
                         options=['Replay from checkpoint.', 'Replay chapter.'])
        self.assertTrue(page.tall_title)
        self.assertEqual((page.top, page.description_height, page.rows_top), (129, 68, 268))
        self.assertEqual((page.portrait.x, page.portrait.y), (-7, 129))
