"""Roadmap 3.16 and the iPad's chooser (2026-11-19): what each save was found to be is kept between launches, and the
chooser's Options draw their page again only when something on it changed."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test_shared_settings import library


class EndedCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_a_save_is_read_once_and_its_answer_kept_for_the_next_launch(self):
        from exp_runtime.menu import ENDED_CACHE, MenuState
        from exp_runtime.settings import AppSettings
        settings = AppSettings(self.root / 'settings.json')
        shelf = library(self.root, 'shs', music_volume=50)
        saves = shelf.directory / 'saves'
        saves.mkdir()
        save = saves / 'e1.shs-auto.json'
        save.write_text(json.dumps({'pending': {'name': 'dialogue'}}), encoding='utf-8')
        state = MenuState(shelf, shared=settings)
        state.save_path = lambda episode, automatic=True: saves / f'{episode}.shs-{"auto" if automatic else "save"}.json'
        self.assertEqual(state.resume_path('e1'), save)
        state.remember_ended()
        kept = json.loads((shelf.directory / ENDED_CACHE).read_text(encoding='utf-8'))
        self.assertEqual(kept['e1.shs-auto.json'][2], False)
        # The next launch takes the kept answer: the save, unreadable now but its time and size the same, isn't read.
        stat = save.stat()
        save.write_text('x' * stat.st_size, encoding='utf-8')
        os.utime(save, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        again = MenuState(shelf, shared=settings)
        again.save_path = state.save_path
        self.assertEqual(again.resume_path('e1'), save)
        # A save changed since is read again (here it can't be: kept resumable, as before, for loading to report).
        save.write_text(json.dumps({'pending': {'name': 'choice'}}), encoding='utf-8')
        third = MenuState(shelf, shared=settings)
        third.save_path = state.save_path
        self.assertEqual(third.resume_path('e1'), save)
        third.remember_ended()
        self.assertNotEqual(json.loads((shelf.directory / ENDED_CACHE).read_text(encoding='utf-8'))['e1.shs-auto.json'][:2],
                            kept['e1.shs-auto.json'][:2])


class ChooserOptionsPageTests(unittest.TestCase):
    def test_the_page_is_laid_out_again_only_when_something_on_it_changed(self):
        from exp_runtime.desktop_app_hd import AppOptions
        page = object()
        menu = SimpleNamespace(state=SimpleNamespace(screen='data:sync', scroll=0., drag=None, focus=None), pressed=None,
                               frame_height=1024, top_pad=0, bottom_pad=0, row_pages={}, text_pages={},
                               animating=lambda: False, advance=lambda ms: None,
                               layout=Mock(return_value=(page, [('rect', ('pause_back',))])))
        options = AppOptions.__new__(AppOptions)
        options.menu, options.clock, options.pressed = menu, None, None
        settings = {'music': True}
        options.settings = lambda: dict(settings)
        layer = SimpleNamespace(blit=Mock())
        options.draw(layer)
        options.draw(layer)
        self.assertEqual(menu.layout.call_count, 1)                 # nothing changed: drawn again as it was
        self.assertEqual(options.buttons, [('rect', ('pause_back',))])
        settings['music'] = False
        options.draw(layer)
        menu.state.screen = 'data:send'
        options.draw(layer)
        menu.animating = lambda: True
        options.draw(layer)
        options.draw(layer)
        self.assertEqual(menu.layout.call_count, 5)                 # a setting, a page, and each frame of a slide


class SyncCommandTests(unittest.TestCase):
    def test_sync_before_it_is_used_says_so(self):
        from exp_runtime.test_channel import Commands
        commands = Commands(None, SimpleNamespace(sync=None))
        reply = commands.do_sync('devices')
        if hasattr(reply, 'send'):                                  # (a job: run it to its reply)
            try:
                while True:
                    next(reply)
            except StopIteration as stop:
                reply = stop.value
        self.assertFalse(reply['ok'])
        self.assertIn('not been used', reply['error'])


if __name__ == '__main__':
    unittest.main()
