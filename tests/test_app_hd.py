"""This player's own screens in HD (desktop_app_hd.py, owner 2026-10-30): drawn without any game's art, with the SD
screens' commands as buttons in frame points."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame


def app(root, **values):
    defaults = dict(screen='games', pressed=None, busy=False, message='', update_prompt=None, file_picker=None,
                    selected_game='shs', game_title='SHSHD Runtime', can_quit=True, job_kind=None, progress_text='',
                    focus=None, focus_index=0, transition_direction=1,
                    library_path=lambda key: Path(root) / key)
    defaults.update(values)
    return SimpleNamespace(**defaults)


class AppScreenTests(unittest.TestCase):
    def setUp(self):
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode((1, 1))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = temporary.name
        from exp_runtime.desktop_app_hd import AppScreens
        self.screens = AppScreens()

    def commands(self, state):
        self.screens.slide = self.screens.last = None             # no slide from the screen drawn before
        canvas = self.screens.draw(state)
        self.assertEqual(canvas.get_size(), (768 * self.screens.card.scale, 1024 * self.screens.card.scale))
        return [command for _, command in self.screens.buttons]

    def test_each_screen_offers_the_sd_screens_commands(self):
        self.assertEqual(self.commands(app(self.root)), [('choose_game', 'shs'), ('choose_game', 'cod'), ('bulk',),
                                                         ('options',)])
        self.assertEqual(self.commands(app(self.root, screen='bulk')), [('back',), ('browse', 'bulk')])
        self.assertEqual(self.commands(app(self.root, screen='setup')), [('back',), ('browse', 'apk'),
                                                                         ('browse', 'library')])
        rects = [rect for rect, _ in self.screens.buttons]
        self.assertTrue(all(0 <= r.left and r.right <= 768 and 0 <= r.top and r.bottom <= 1024 for r in rects))

    def test_a_card_takes_the_buttons_the_screen_had(self):
        self.assertEqual(self.commands(app(self.root, message='Added 53 episodes.')), [('dismiss',)])
        self.assertEqual(self.commands(app(self.root, update_prompt=SimpleNamespace(version='1.0.3'))),
                         [('update_no',), ('update_yes',)])
        self.assertEqual(self.commands(app(self.root, update_prompt=SimpleNamespace(version='1.0.3'), can_quit=False)),
                         [('update_no',)])
        self.assertEqual(self.commands(app(self.root, busy=True, job_kind='bulk')), [])     # nothing to press

    def test_the_busy_card_warns_that_importing_takes_a_while_but_not_its_other_jobs(self):
        from exp_runtime.desktop_app_hd import IMPORT_NOTE
        notes = []
        original = self.screens.window

        def window(layer, title, text, labels, commands, *, note=None, spinner=False):
            notes.append((title, text, note))
            return original(layer, title, text, labels, commands, note=note, spinner=spinner)
        self.screens.window = window
        self.commands(app(self.root, busy=True, job_kind='bulk'))
        self.commands(app(self.root, busy=True, job_kind='data', job_title='Verifying library', progress_text='1 of 3'))
        self.assertEqual(notes, [('Importing content', 'Checking and copying your files...', IMPORT_NOTE),
                                 ('Verifying library', '1 of 3', None)])

    def test_a_page_change_slides_and_takes_no_taps_meanwhile(self):
        self.commands(app(self.root))
        self.screens.draw(app(self.root, screen='bulk'))
        self.assertIsNotNone(self.screens.slide)
        self.assertEqual(self.screens.buttons, [])

    def test_long_text_wraps_inside_the_card(self):
        lines = self.screens.card.wrap('word ' * 60, 26, 300)
        self.assertGreater(len(lines), 3)
        font = self.screens.card.font(26)
        self.assertTrue(all(font.size(line)[0] / self.screens.card.scale <= 300 for line in lines))


if __name__ == '__main__':
    unittest.main()
