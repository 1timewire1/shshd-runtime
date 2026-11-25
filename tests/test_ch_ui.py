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
                       details=['', 'Open till 5', ''], timeout_ms=0)
        page = self.page()
        renderer = self.renderer(page, details)
        _, buttons = renderer.draw_hd(None, self.session(details), page, 0, None, None, False, focus=1)
        self.assertEqual([command for _, command in buttons], [('choose', 0), ('choose', 1), ('choose', 2), ('menu',)])
        self.assertEqual([(r.x, r.y, r.w, r.h) for r, _ in buttons[:3]], [(23, 150 + 44 * i, 274, 44) for i in range(3)])
        self.assertIn(('ch', 'Out', (540, 80), True, 'Open till 5'), renderer._labels)   # (lit, with its detail line)
        self.assertIn(('ch', 'Home', (540, 80), False, None), renderer._labels)
        self.assertGreater(renderer.canvas.get_at((320, 120 * 2)).a, 200)       # (the panel under the description)
        self.assertEqual(renderer.overlay.get_at((320, (282 + 30) * 2)).a, 0)   # (no timer on an untimed choice)

    def test_choice_hints_read_on_the_dark_rows(self):
        # Owner, g54, 2026-11-22: CoD's pastel hints washed out to one grey-green on the skin. Each kind takes its own
        # stronger tint and an edge bar of its colour; off, the rows are the skin's own.
        from exp_runtime.desktop_choice import SKIN_HINT_COLORS
        details = dict(title='Pick', text='Which?', options=['Good', 'Bad', 'Both'], timeout_ms=0)
        page = self.page()
        renderer = self.renderer(page, details)
        renderer.hints = [SimpleNamespace(kind=kind) for kind in ('gain', 'loss', 'mixed')]
        renderer.hint_key = renderer.cached_key = 'k'
        renderer.draw_hd(None, self.session(details), page, 0, None, None, True)
        k, gap = renderer.scale, max(1, round(renderer.SKIN_ROW_GAP * renderer.scale))
        edges = [tuple(renderer.canvas.get_at((23 * k + gap, (150 + 44 * i + 22) * k)))[:3] for i in range(3)]
        self.assertEqual(edges, [SKIN_HINT_COLORS[kind] for kind in ('gain', 'loss', 'mixed')])
        spots = [((23 + 30) * k, (150 + 44 * i + 12) * k) for i in range(3)]
        hinted = [tuple(renderer.canvas.get_at(spot))[:3] for spot in spots]
        renderer.draw_hd(None, self.session(details), page, 0, None, None, False)
        plain = [tuple(renderer.canvas.get_at(spot))[:3] for spot in spots]
        self.assertNotIn(tuple(renderer.canvas.get_at((23 * k + gap, (150 + 22) * k)))[:3], SKIN_HINT_COLORS.values())
        (gr, gg, _), (lr, lg, _) = ([a - b for a, b in zip(hinted[i], plain[i])] for i in (0, 1))
        self.assertGreater(gg, gr)                                              # (a gain's tint leans green)
        self.assertGreater(lr, lg)                                              # (a loss's red)

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


class ChScreenTests(unittest.TestCase):
    """The pause menu, text entry and the portrait picker in the skin: their places and taps CoD's."""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_the_tab_moves_beside_a_portrait_and_stays_centred_without_one(self):
        from exp_runtime.desktop_ch_ui import ChUi
        ui = ChUi.of(a_chc()[0])
        middle, before = ui.tab_bounds(560, .6)
        _, after = ui.tab_bounds(560, .6, tab_centre=560 - (60 * .6 + before + (270 - 180) * .6 + middle / 2))
        self.assertGreater(before, 0)
        _, right = ui.tab_bounds(560, .6, tab_centre=420)
        self.assertGreater(right, before)                              # (moved right, away from a left portrait)
        self.assertIsNot(ui.panel((560, 400), .6), ui.panel((560, 400), .6, tab_centre=420))

    def test_a_title_too_long_for_the_tab_is_set_smaller_so_the_tab_stays_inside_the_frame(self):
        """Owner 2026-11-22: the legal page's long title ran the tab over the panel's right edge."""
        from exp_runtime.desktop_ch_ui import ChUi
        ui = ChUi.of(a_chc()[0])
        p = ui.ui['panel']
        (left, right), (t0, t1, t2, t3) = p['caps'], p['tab']
        width, s, title = 560, .6, 'Privacy Policy/ EULA/ Terms & Conditions'
        room = ui.title_room(width, s)
        middle, before = ui.tab_bounds(width, s, room)
        tab = (t1 - t0 + t3 - t2) * s + middle
        self.assertLessEqual(before + tab, width - (left + right) * s)  # (the widest title's tab clears both caps)
        self.assertGreater(ui.font(40).size(title)[0], room)            # (this title at 40 would not fit)
        drawn = []
        real = ui.font
        with mock.patch.object(ChUi, 'font', lambda self, px: (drawn.append(px), real(px))[1]):
            ui.draw_panel(pygame.Surface((width, 400), pygame.SRCALPHA), pygame.Rect(0, 0, width, 400), s, title, 40)
        self.assertLess(drawn[-1], 40)
        self.assertLessEqual(real(drawn[-1]).size(title)[0], room)
        drawn.clear()
        with mock.patch.object(ChUi, 'font', lambda self, px: (drawn.append(px), real(px))[1]):
            ui.draw_panel(pygame.Surface((width, 400), pygame.SRCALPHA), pygame.Rect(0, 0, width, 400), s, 'Help', 40)
        self.assertEqual(set(drawn), {40})                               # (a short title keeps its size)

    def test_the_pause_menu_takes_classics_dress_and_keeps_its_taps(self):
        from exp_runtime.desktop_cod_pause import CodPauseMenu
        from exp_runtime.desktop_pause_hd import PANEL_X, ROW
        strings = [f's{i}' for i in range(300)]
        with mock.patch.object(CodPauseMenu, 'strings', lambda self: strings):
            menu = CodPauseMenu(a_chc()[0], SimpleNamespace(game_id=lambda: 'cod'))
            layer, buttons = menu.layout({})
            self.assertIsNotNone(menu.ui)
            self.assertEqual(menu.LABEL_COLOR, menu.ui.TEXT)
            self.assertEqual([command for _, command in buttons][:2], [('resume',), ('pause_open', 'options')])
            self.assertEqual(buttons[1][0].height, ROW)
            menu.state.screen = 'options:general'
            layer, buttons = menu.layout({'autoplay': True, 'aspect_ratio': '3:4 (HD)'})
            back = next(rect for rect, command in buttons if command == ('pause_back',))
            self.assertEqual((back.x, back.w, back.h), (PANEL_X + 14, 156, 58))
            self.assertIn(('pause_open', 'choice:aspect_ratio'), [command for _, command in buttons])
            # A switch's OFF is the control's grey, not the skin's off-white page text (g54, 2026-11-22: it vanished).
            track = menu.switch_track(0.0)
            w, h = track.get_size()
            darkest = min(sum(track.get_at((x, y))[:3]) / 3 for x in range(w // 2, w) for y in range(h // 3, 2 * h // 3)
                          if track.get_at((x, y)).a == 255)
            self.assertLess(darkest, 170)                       # (128 now; the off-white label was ~228)
            # The switch off: CoD's own colours come back.
            menu.resources = SimpleNamespace(library=None, dialogue_skin=lambda: None)
            self.assertIsNone(menu.skin())
            self.assertNotIn('LABEL_COLOR', menu.__dict__)

    def test_text_entry_keeps_its_field_and_the_refused_name_takes_the_popup(self):
        from exp_runtime.desktop_input import ALERT_RECT, InputRenderer
        from exp_runtime.ui_assets import Rect
        resources, _ = a_chc()
        places = {23: (10, 40, 260, 20), 34: (10, 80, 260, 40), 44: (20, 85, 240, 30)}

        class Layouts:
            def __init__(self, bank):
                pass

            def rectangle(self, layout, node, origin):
                x, y, w, h = places[node]
                return (origin[0] + x, origin[1] + y, w, h)
        resources.dialogue_layout = lambda: SimpleNamespace(bank=SimpleNamespace(rectangle=lambda layout, node: Rect(0, 0, 260, 20)))
        renderer = InputRenderer.__new__(InputRenderer)
        renderer.resources, renderer.scale, renderer.answer = resources, 2, None
        renderer.canvas = pygame.Surface((640, 960), pygame.SRCALPHA)
        renderer.art = SimpleNamespace(game_id=lambda: 'cod', cod_hd_common=lambda: object(), image=lambda b: None,
                                       background_origin=lambda *a: (160, 180))
        renderer.answer_hint = lambda session, enabled: None
        session = SimpleNamespace(pending=SimpleNamespace(details=dict(title='Your Name', prompt='Who are you?', default='',
                                                                       draft='Claire')),
                                  engine=SimpleNamespace(panel=SimpleNamespace(background_id=-1)))
        with mock.patch('exp_runtime.hd_layout.BankLayouts', Layouts), \
                mock.patch.object(InputRenderer, 'strings', lambda self: {258: 'Alert', 260: 'A-Z and 0-9 only.', 164: 'OK'}):
            buttons = renderer.draw(None, session)
            (field, command), = buttons
            self.assertEqual(command, ('input_focus',))
            ox = (320 - 280) / 2
            self.assertEqual((field.x, field.w, field.h), (round(ox + 10), 260, 40))
            self.assertGreater(renderer.canvas.get_at((field.centerx * 2, field.centery * 2)).a, 200)    # (the capsule)
            self.assertEqual(renderer.draw(None, session, error='refused'), [(pygame.Rect(ALERT_RECT), ('input_dismiss',))])

    def test_the_portrait_picker_takes_the_panel_and_the_pill_over_cods_check(self):
        from exp_runtime.desktop_picker import CodCharacterPickerRenderer
        resources, _ = a_chc()

        def solid(colour, size):
            image = pygame.Surface(size, pygame.SRCALPHA)
            image.fill(colour)
            return image
        boxes = []
        art = SimpleNamespace(game_id=lambda: 'cod', cod_hd_common=lambda: object(), image=lambda asset: None,
                              background_origin=lambda *_: (160, 180), DISC_UNITS=105,
                              box=lambda *a, **k: boxes.append(a),
                              frame_scaled=lambda pack, frame, k: solid((frame, 0, 0, 255), (64 * k, 64 * k)),
                              hd_portrait=lambda asset, flag, k: (solid((0, 0, 255, 255), (20 * k, 20 * k)), 0))
        renderer = CodCharacterPickerRenderer(resources, SimpleNamespace(), art)
        renderer.hint = 'Select portrait then confirm'
        portraits = [SimpleNamespace(pose=(160, 275, 1.), opacity=255), SimpleNamespace(pose=(52, 241, .6), opacity=92)]
        session = SimpleNamespace(
            pending=SimpleNamespace(details={'text': 'Choose your look!'}),
            engine=SimpleNamespace(character_picker=SimpleNamespace(characters=[1, 2], portraits=portraits),
                                   character_art_variants={1: [5], 2: [6]}, numbers={}, number_key=lambda c, v: (c, v),
                                   panel=SimpleNamespace(background_id=-1)))
        with mock.patch('exp_runtime.desktop_picker.panel_theme', return_value=0):
            buttons = renderer.draw(None, session)
        U = renderer.U
        self.assertEqual(boxes, [])                                      # (Classic's panel, not CoD's box)
        self.assertEqual(buttons, [(pygame.Rect(-32, 422, 92, 58), ('menu',))])
        self.assertNotEqual(renderer.canvas.get_at((210 * U, 352 * U))[:3], (41, 0, 0))   # (no frame 41: the pill)
        self.assertTrue(CodCharacterPickerRenderer.confirm_hit((240, 366)))          # (the pill over CoD's tap)
        self.assertGreater(renderer.canvas.get_at((240 * U, 366 * U)).a, 200)


class ChMenuTests(unittest.TestCase):
    """Claire Hart UI's Everywhere (owner, 2026-11-22): the main menu's screens find the skin through the library."""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def library(self, choice='classic', ui=True):
        from exp_runtime.content import ContentLibrary
        resources, spec = a_chc(ui=ui)
        library = ContentLibrary.__new__(ContentLibrary)
        library.game_id, library.ch_dialogue = 'cod', choice
        library.addon_json = lambda addon, rid: spec if (addon, rid) == ('chc', 29100) else None
        library.addon_resource = resources.library.addon_resource
        return library

    def test_only_a_skin_by_name_gives_the_menus_the_skin(self):
        """Owner, 2026-11-24: a game's skin by name dresses the menus too; Auto and Off leave them CoD's. A saved
        Everywhere is Claire Hart Classic, Cases Auto."""
        from exp_runtime.desktop_ch_ui import ChUi
        from exp_runtime.desktop_pause_hd import CH_DIALOGUE_LABEL, CH_DIALOGUE_NAMES
        self.assertEqual((CH_DIALOGUE_LABEL, CH_DIALOGUE_NAMES['classic']), ('Claire Hart UI', 'Claire Hart Classic'))
        library = self.library()
        self.assertIs(library.menu_skin(), library.menu_skin())         # (the same dict: what is kept for it stays)
        self.assertEqual(library.menu_skin()['addon'], 'chc')
        self.assertIsNotNone(ChUi.of(library))                          # (the main menu's art: the library itself)
        self.assertIsNotNone(ChUi.of(SimpleNamespace(library=library)))     # (the main menu's pause card)
        for choice in ('auto', 'off', 'cases'):
            self.assertIsNone(self.library(choice).menu_skin())
        self.assertEqual(self.library('all').menu_skin()['addon'], 'chc')
        self.assertIsNone(self.library('shadows').menu_skin())          # (no ch2 in this library: CoD's menus)
        self.assertIsNone(ChUi.of(self.library(ui=False)))              # (chc revision 1: CoD's menus)

    def test_the_window_lays_out_its_pills_and_returns_their_taps(self):
        from exp_runtime.desktop_ch_ui import ChUi
        from exp_runtime.hd_ui import FRAME, S
        ui = ChUi.of(self.library())
        layer = pygame.Surface((FRAME[0] * S, FRAME[1] * S), pygame.SRCALPHA)
        rects, top, height, lines = ui.window(layer, S, FRAME[0], 'Update Available', 'A new version.', ('No', 'Yes'),
                                              dense=True)
        self.assertEqual(len(rects), 2)
        self.assertLess(rects[0].right, FRAME[0] / 2)
        self.assertGreater(rects[1].left, FRAME[0] / 2)
        self.assertTrue(top < rects[0].top < top + height)
        self.assertEqual(ui.window(layer, S, FRAME[0], 'Busy', 'Reading.', (), spinner=1.0)[0], [])

    def test_the_title_screens_buttons_become_pills_with_romic_labels(self):
        from exp_runtime.desktop_cod_main import CodMainMenu
        from exp_runtime.hd_ui import S
        menu = CodMainMenu.__new__(CodMainMenu)
        menu.library = self.library()
        (pill, place), = menu.piece((100, 30))
        self.assertEqual(place, (0, 0, 200, 60))
        self.assertEqual(pill.get_size(), (200 * S, 60 * S))
        self.assertGreater(menu.label('Now Airing', 0).get_width(), 0)
        menu.library = self.library('cases')
        with mock.patch('exp_runtime.desktop_main_hd.HdMainMenu.piece', return_value='CoD') as plain:
            self.assertEqual(menu.piece((100, 30)), 'CoD')
        plain.assert_called_once()

    def test_the_grid_keeps_its_tiles_but_its_buttons_and_cards_take_the_skin(self):
        # Owner, 2026-11-22: the grid's back and Restore buttons and its New Game / Continue card were CoD's.
        from exp_runtime.desktop_cod_episodes import CodEpisodePicker
        grid = CodEpisodePicker.__new__(CodEpisodePicker)
        grid.library = self.library()
        ui = grid.skin()
        self.assertIsNotNone(ui)
        with mock.patch.object(type(ui), 'pill', wraps=ui.pill) as pill:
            grid.draw_button(pygame.Surface((400, 200), pygame.SRCALPHA), 10, 10, orange=True, label='Restore')
        pill.assert_called_once()
        with mock.patch('exp_runtime.desktop_episode_picker.HdEpisodePicker.font', return_value='CoD') as plain:
            self.assertEqual(grid.font(28), 'CoD')                          # the grid's own text: CoD's
            seen = []
            with mock.patch('exp_runtime.desktop_episode_picker.HdEpisodePicker.draw_overlay_card',
                            lambda self, layer, strings: seen.append((self.font(28), self.TEXT_COLOR))):
                grid.draw_overlay_card(None, {})
        self.assertIsNot(seen[0][0], 'CoD')                                  # the card's: the skin's Romic
        self.assertEqual(seen[0][1], ui.TEXT)
        self.assertNotIn('TEXT_COLOR', grid.__dict__)                       # (given back after the card)
        grid.library = self.library('cases')
        self.assertIsNone(grid.skin())

    def test_the_episode_list_takes_the_skins_colours_and_romics_pitch_and_gives_them_back(self):
        from exp_runtime.desktop_cod_episodes import CodEpisodeList
        listing = CodEpisodeList.__new__(CodEpisodeList)
        listing.library, listing.card = self.library(), None
        ui = listing.skin()
        self.assertIsNotNone(ui)
        self.assertEqual(listing.TEXT_ROW_COLOR, ui.TEXT)
        self.assertEqual(listing.ICON_RING_COLOR, ui.GOLD)
        self.assertGreaterEqual(listing.line_height(28), listing.font(28).get_linesize() / 2 - 1)
        # A row's tag is Options' badge (g54, 2026-11-22): gold, at its size, not Claire Hart's dark green.
        from exp_runtime.desktop_pause_hd import BADGE_HEIGHT
        from exp_runtime.hd_scale import S
        layer = pygame.Surface((200 * S, 60 * S), pygame.SRCALPHA)
        listing.draw_standard_mark(layer, 10, 20, 'CH', (14, 80, 40))
        top = next(y for y in range(layer.get_height()) if any(layer.get_at((x, y)).a for x in range(layer.get_width())))
        bottom = max(y for y in range(layer.get_height()) if any(layer.get_at((x, y)).a for x in range(layer.get_width())))
        self.assertEqual(bottom - top + 1, BADGE_HEIGHT * S)
        border = next(layer.get_at((x, (top + bottom) // 2)) for x in range(layer.get_width())
                      if layer.get_at((x, (top + bottom) // 2)).a > 150)
        self.assertEqual(tuple(border)[:3], ui.GOLD)
        self.assertGreater(listing.mark_width('CH'), 32)
        listing.library = self.library('off')
        self.assertIsNone(listing.skin())
        self.assertNotIn('TEXT_ROW_COLOR', listing.__dict__)
        self.assertEqual(listing.TEXT_ROW_COLOR, (0, 0, 0))             # (CoD's black again)


if __name__ == '__main__':
    unittest.main()
