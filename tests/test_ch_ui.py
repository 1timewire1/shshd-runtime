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


if __name__ == '__main__':
    unittest.main()
