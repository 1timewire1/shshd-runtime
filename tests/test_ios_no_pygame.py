"""The app as iOS runs it: no pygame at all (tests/ios_no_pygame_check.py, in a process of its own)."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class IosWithoutPygameTests(unittest.TestCase):
    def test_the_ios_host_starts_and_every_module_imports_without_pygame(self):
        """iOS bundles no pygame: a module that names a pygame constant the native backend lacks, or imports pygame
        itself, stops the app as it starts (2026-11-12: desktop.py's WASD keys after the merge from master). Run in a
        fresh process, as modules the other tests loaded with pygame would pass where the device fails."""
        check = Path(__file__).with_name('ios_no_pygame_check.py')
        with tempfile.TemporaryDirectory() as data:
            result = subprocess.run([sys.executable, '-X', 'utf8', str(check), data], capture_output=True, text=True,
                                    timeout=300, env=dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy'))
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn('host frames ok', result.stdout)
        self.assertIn('modules that fail to import without pygame: 0', result.stdout, result.stdout[-2000:])


if __name__ == '__main__':
    unittest.main()
