"""The iOS host's import hand-off: Swift copies picked files into the app and the shared app shows that copy as busy
until the import (or the copy's error) arrives; problems are written to a log the Files app shows."""
import logging
import tempfile
import unittest
from pathlib import Path


class IosImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)          # runs last: the log handler is closed before the folder goes
        self.root = Path(temporary.name)

    def host(self, root):
        from exp_runtime import graphics
        from exp_runtime.app_icon import icon_surface
        from exp_runtime.platforms.drawing import Backend
        from exp_runtime.platforms.ios import Host
        from PIL import Image
        from native_host_fonts import FontHost
        icon = root / 'authored-icon.png'
        Image.new('RGBA', (2, 2), 'green').save(icon)
        backend = Backend(FontHost(), icon)
        previous = graphics.install(backend)
        self.addCleanup(graphics.install, previous)
        icon_surface.cache_clear()
        self.addCleanup(icon_surface.cache_clear)
        host = Host(root, backend=backend, library_root=root / 'libraries', check_updates=False)
        self.addCleanup(host.app.close)
        self.addCleanup(self.drop_log_handlers)
        return host

    @staticmethod
    def drop_log_handlers():
        logger = logging.getLogger()
        for handler in list(logger.handlers):
            if getattr(handler, 'ios_runtime_log', False):
                logger.removeHandler(handler)

    def test_the_copy_shows_as_busy_until_the_import_arrives(self):
        root = self.root
        host = self.host(root)
        host.request(dict(operation='import_copying', kind='bulk', names=['import.zip']))
        self.assertTrue(host.app.busy)
        self.assertEqual(host.app.job_kind, 'copying')
        self.assertIn('import.zip', host.app.progress_text)
        reply = host.request(dict(operation='frame', elapsed=16))
        self.assertTrue(host.app.busy)                          # nothing else starts during the copy
        self.assertTrue(reply['busy'])                          # the host keeps the iPad from auto-locking
        notes = root / 'notes.txt'
        notes.write_text('not a game', encoding='utf-8')
        host.request(dict(operation='import', kind='bulk', paths=[str(notes)]))
        self.assertNotEqual(host.app.job_kind, 'copying')       # the import itself ran: here, a refusal
        self.assertTrue(host.app.message)

    def test_a_failed_copy_is_shown_and_logged(self):
        root = self.root
        host = self.host(root)
        host.request(dict(operation='import_copying', kind='bulk', names=['a.zip', 'b.zip']))
        self.assertIn('2 files', host.app.progress_text)
        reply = host.request(dict(operation='message', text='There is not enough space on the device.'))
        self.assertFalse(host.app.busy)
        self.assertFalse(reply['busy'])                         # auto-lock is allowed again
        self.assertEqual(host.app.message, 'There is not enough space on the device.')
        self.assertIn('not enough space', (root / 'shshd-runtime.log').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
