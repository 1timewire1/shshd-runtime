"""A name typed faster than a frame (found in v1.1.1's full check, 2026-11-22): the app's event loop stops a frame's input
when the screen token changes, so a queued click never lands on a new screen; the token held the name being typed, so a
frame's later letters (and its Enter) were dropped after its first: "Sam" came out "S". A keyboard's autocorrect or a
suggestion sends several at once."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

from exp_runtime.runtime import Session
from test_runtime import Resources, host_call, text_words
from test_vm import program


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class TypedNameTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        self.pygame = pygame
        self.addCleanup(pygame.quit)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        words, (title, prompt, default) = text_words('Name', 'Who are you?', 'Alex')
        resources = Resources(program(*host_call(17, title, prompt, default), 0x21, (0x1f, 0xfe01), words=words))
        resources.library.directory = Path(temporary.name)
        self.ui = Desktop(Session(resources), audio=False)
        self.ui.session.pending.details['draft'] = ''

    def test_letters_typed_in_one_frame_keep_the_screen_and_all_land(self):
        ui, pygame = self.ui, self.pygame
        token = ui._screen_token()
        for letter in 'Sam':
            ui.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=letter))
            self.assertEqual(ui._screen_token(), token)              # (the frame's next key is not dropped)
        self.assertEqual(ui.session.pending.details['draft'], 'Sam')

    def test_a_refused_letters_alert_still_counts_as_a_new_screen(self):
        ui, pygame = self.ui, self.pygame
        token = ui._screen_token()
        ui.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='@'))
        self.assertIsNotNone(ui.input_error)
        self.assertNotEqual(ui._screen_token(), token)


if __name__ == '__main__':
    unittest.main()
