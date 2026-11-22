"""shshd-runtime: Claire Hart Dialogue on CoD's other screens (CLAIRE_HART_SKIN_PLAN.md; owner, 2026-11-21): the shared
pieces (desktop_ch_ui.ChUi: Classic's panel with its title tab, rows, pills, the timer bar, the popup), only with chc revision
2's `ui` (revision 1 keeps CoD's look), and the message panel drawn in them."""
import io
import json
import os
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame


def png(size, colour):
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill(colour)
    out = io.BytesIO()
    pygame.image.save(surface, out, 'piece.png')
    return out.getvalue()


def a_chc(ui=True):
    """A chc's skin resources: its spec (with or without `ui`), the pieces at Classic's sizes, Romic as the default font."""
    path = pygame.font.get_default_font()
    with open(path if os.path.exists(path) else os.path.join(os.path.dirname(pygame.__file__), path), 'rb') as file:
        font = file.read()
    spec = {'version': 1, 'fonts': {'body': 28004, 'bold': 28005}, 'pill': [29106, 29107]}
    resources = {28004: font, 28005: font, 29106: png((209, 57), (0, 160, 0, 255)), 29107: png((209, 57), (0, 90, 0, 255))}
    if ui:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools', 'translate'))
        from ch_dialogue_skin import UI_SOURCES, ui_spec
        spec['ui'] = ui_spec()
        sizes = {29109: (718, 498), 29110: (328, 244), 29111: (541, 76), 29112: (225, 82), 29113: (494, 37),
                 29114: (625, 70), 29115: (624, 74), 29116: (45, 45), 29117: (45, 45), 29118: (209, 57)}
        for resource in UI_SOURCES:
            resources[resource] = png(sizes[resource], (20 + resource % 7 * 30, 90, 80, 255))
    resources[29100] = json.dumps(spec).encode()
    library = SimpleNamespace(addon_resource=lambda addon, resource: resources.get(resource) if addon == 'chc' else None)
    return SimpleNamespace(library=library, dialogue_skin=lambda: spec), spec


class ChUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_only_chc_revision_2_gives_the_pieces(self):
        from exp_runtime.desktop_ch_ui import ChUi
        self.assertIsNone(ChUi.of(a_chc(ui=False)[0]))                  # (revision 1: CoD's own look stays)
        self.assertIsNone(ChUi.of(SimpleNamespace(library=None, dialogue_skin=lambda: None)))     # (the switch off)
        resources, _ = a_chc()
        self.assertIs(ChUi.of(resources), ChUi.of(resources))            # (kept for the spec)

    def test_the_panel_keeps_its_header_and_its_tab_grows_with_a_long_title(self):
        from exp_runtime.desktop_ch_ui import ChUi
        ui = ChUi.of(a_chc()[0])
        panel = ui.panel((1120, 600), 1.2)
        self.assertEqual(panel.get_size(), (1120, 600))
        self.assertAlmostEqual(ui.header_height(1.2), 102 * 1.2)
        short, long = ui.panel((1120, 600), 1.2, 50), ui.panel((1120, 600), 1.2, 900)
        self.assertIsNot(short, long)                                    # (a title wider than the tab widens it)
        self.assertEqual(ui.row((900, 120), 1.0, lit=True).get_size(), (900, 120))
        self.assertEqual(ui.pill((400, 80), 1.4).get_size(), (400, 80))
        full, half = ui.timer((600, 40), 0.5, 1.0), ui.timer((600, 40), 0.5, 0.5)
        self.assertNotEqual(full.get_at((500, 20)), half.get_at((500, 20)))   # (the fill cut at its fraction)
        self.assertGreater(ui.pitch(40), ui.font(40).get_linesize() - 1)

    def test_the_message_panel_draws_in_classics_panel_when_the_skin_is_on(self):
        from exp_runtime.desktop_message_hd import CodMessageRenderer
        from exp_runtime.message_panel import MessagePanel
        strings = {29: 'Continue', 30: 'Wait', 36: 'Tap to go on', 39: 'Please wait'}
        session = SimpleNamespace(engine=SimpleNamespace(message_panel=MessagePanel('Objectives', 'Find the phone.', 0, 1000),
                                                         panel=SimpleNamespace(background_id=-1)))
        for ui in (True, False):
            resources, _ = a_chc(ui=ui)
            renderer = CodMessageRenderer(resources, SimpleNamespace())
            with mock.patch.object(CodMessageRenderer, 'strings', lambda self: strings), \
                    mock.patch('exp_runtime.desktop_message_hd.HdMessageRenderer.draw', return_value='CoD') as plain:
                buttons = renderer.draw(None, session)
            if ui:
                plain.assert_not_called()
                self.assertEqual(buttons[-1][1], ('continue',))           # (the same taps as CoD's panel)
                self.assertEqual(renderer.footer_text, 'Tap to go on')
                middle = renderer.canvas.get_at((renderer.canvas.get_width() // 2, renderer.canvas.get_height() // 2))
                self.assertGreater(middle.a, 200)                        # (the panel drawn mid-frame)
            else:
                self.assertEqual(buttons, 'CoD')                          # (revision 1: CoD's own panel)


class ChWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def windows(self, ui=True):
        from exp_runtime.desktop_cod_menu import CodMenuWindows
        resources, _ = a_chc(ui=ui)
        windows = CodMenuWindows.__new__(CodMenuWindows)
        no, yes = SimpleNamespace(id=25, label='No'), SimpleNamespace(id=24, label='Yes')
        menus = {16: SimpleNamespace(id=16, style=2, title='Exit Game?', message='Leave and open your browser?'),
                 38: SimpleNamespace(id=38, style=0xff, title='Connection Error', message='Unable to connect.')}
        windows.data = SimpleNamespace(menu=menus.get, items=lambda menu: [no, yes] if menu == 16 else [no])
        windows.art = SimpleNamespace(resources=resources)
        windows.library = resources.library
        windows.items = windows.data.items
        windows.text_for = lambda value, variables=None: value
        windows.item_label = lambda action, variables: action.label
        windows.strings = lambda: {154: 'OK'}
        return windows, (no, yes)

    def test_an_alert_and_a_notice_take_classics_popup_and_their_taps_follow_the_pills(self):
        from exp_runtime.hd_ui import FRAME, S
        windows, (no, yes) = self.windows()
        layer = pygame.Surface((FRAME[0] * S, FRAME[1] * S), pygame.SRCALPHA)
        g = windows.draw(layer, 16, pressed=('item', 24))
        self.assertEqual(g['kind'], 'alert')
        self.assertEqual([command for _, command in windows.hits], [('item', 25), ('item', 24)])
        left, right = (rect for rect, _ in windows.hits)
        self.assertLess(left.right, FRAME[0] / 2)
        self.assertGreater(right.left, FRAME[0] / 2)                     # (No left of the middle, Yes right)
        self.assertGreater(layer.get_at((left.centerx * S, left.centery * S)).a, 200)    # (a pill drawn under each tap)
        windows.draw(layer, 38)
        self.assertEqual([command for _, command in windows.hits], [('item', 25)])     # (the notice's one OK)

    def test_without_the_pieces_the_windows_keep_cods_card(self):
        from exp_runtime.desktop_hd_menu import HdMenuWindows
        windows, _ = self.windows(ui=False)
        with mock.patch.object(HdMenuWindows, 'draw', return_value='CoD card') as plain:
            self.assertEqual(windows.draw(None, 16), 'CoD card')
        plain.assert_called_once()


class ChChoiceTests(unittest.TestCase):
    """The choice (and the skip prompt, the quiz) in the skin: CoD's rows and taps, Classic's art."""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def page(self, timed=False, scored=False):
        from exp_runtime.hd_choice import COD_GEOMETRY, HdChoicePage, HdRow
        from exp_runtime.ui_assets import Rect
        rows = tuple(HdRow(i, i, Rect(23, 150 + 44 * i, 274, 44), None, (35, 160 + 44 * i)) for i in range(3))
        footer = 150 + 44 * 3
        return HdChoicePage(theme=0, top=90, header_widget=7, header_height=30, tall_title=False, description_height=30,
                            rows_top=150, rows_height=132, footer_widget=3, footer_top=footer,
                            footer_height=60 if timed or scored else 20, title_font='', title=None, title_origin=(0, 0),
                            description=None, description_origin=(30, 125), description_font='', rows=rows,
                            portrait=None, portrait_clip=None, max_scroll=0, table=Rect(23, 150, 274, 132),
                            timer_center=(161, footer + 30) if timed or scored else None, row_colors=((0,) * 4,) * 3,
                            scored=scored, geometry=COD_GEOMETRY)

    def renderer(self, page, details):
        from exp_runtime.desktop_choice import ChoiceRenderer
        resources, _ = a_chc()
        art = SimpleNamespace(game_id=lambda: 'cod', image=lambda background: None,
                              background_origin=lambda background, engine: (160, 180))
        renderer = ChoiceRenderer(resources, SimpleNamespace(), art, scale=2)
        renderer.cached_page, renderer.cached_details, renderer.age_ms = page, details, 5000
        return renderer

    def session(self, details, remaining=None, game=None):
        return SimpleNamespace(pending=SimpleNamespace(details=details), remaining_ms=remaining,
                               engine=SimpleNamespace(word_game=game, panel=SimpleNamespace(background_id=-1)))

    def test_a_choice_keeps_cods_rows_and_taps_and_lights_the_focused_row(self):
        details = dict(title='What do you say?', text='Where were you?', options=['Home', 'Out', 'No comment'],
                       timeout_ms=0)
        page = self.page()
        renderer = self.renderer(page, details)
        _, buttons = renderer.draw_hd(None, self.session(details), page, 0, None, None, False, focus=1)
        self.assertEqual([command for _, command in buttons], [('choose', 0), ('choose', 1), ('choose', 2), ('menu',)])
        self.assertEqual([(r.x, r.y, r.w, r.h) for r, _ in buttons[:3]], [(23, 150 + 44 * i, 274, 44) for i in range(3)])
        self.assertIn(('ch', 'Out', (540, 80), True), renderer._labels)          # (the focused row's label, lit)
        self.assertIn(('ch', 'Home', (540, 80), False), renderer._labels)
        self.assertGreater(renderer.canvas.get_at((320, 120 * 2)).a, 200)       # (the panel under the description)
        self.assertEqual(renderer.overlay.get_at((320, (282 + 30) * 2)).a, 0)   # (no timer on an untimed choice)

    def test_a_timed_choice_runs_the_combo_bar_and_the_quiz_scores_on_the_capsule(self):
        details = dict(title='Quick!', text='Now.', options=['A', 'B', 'C'], timeout_ms=10000)
        page = self.page(timed=True)
        renderer = self.renderer(page, details)
        renderer.draw_hd(None, self.session(details, remaining=5000), page, 0, None, None, False)
        bar, _ = renderer.skin_footer(renderer.ch_ui(page), page, False)
        self.assertGreater(renderer.overlay.get_at(bar.center).a, 200)         # (the bar, outside the menu's fades)
        game = SimpleNamespace(options=['A', 'B', 'C'], duration_ms=20000, remaining_ms=4000, selected=-1, fly_off_ms=0,
                               fly_off_row=-1, shown_ms=5000, score=7, effect_ms=500, last_delta=1, HD_EFFECT_MS=1000,
                               HD_FLY_OFF_MS=500)
        page = self.page(scored=True)
        renderer = self.renderer(page, dict(details, timeout_ms=20000))
        renderer.draw_hd(None, self.session(details, game=game), page, 0, None, None, False)
        bar, capsule = renderer.skin_footer(renderer.ch_ui(page), page, True)
        self.assertLess(bar.right, capsule.left)                                # (the bar shortened for the capsule)
        self.assertGreater(renderer.canvas.get_at(capsule.center).a, 200)


if __name__ == '__main__':
    unittest.main()
