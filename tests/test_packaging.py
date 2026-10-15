import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

from tools.package_desktop import audit_bundle, package


class PackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bundle = self.root / 'dist/desktop/SHSHD Runtime'
        self.bundle.mkdir(parents=True)

    def test_windows_download_contains_complete_app_and_no_neighboring_inputs(self):
        (self.bundle / 'SHSHD Runtime.exe').write_bytes(b'authored executable fixture')
        (self.bundle / '_internal').mkdir()
        (self.bundle / '_internal/runtime.dll').write_bytes(b'authored dependency fixture')
        (self.bundle.parent / 'private.apk').write_bytes(b'authored excluded fixture')
        (self.root / 'Episodes').mkdir()
        (self.root / 'Episodes/private.exp').write_bytes(b'authored excluded fixture')
        result = package(self.root, 'windows-x64', 'v0.1.0')
        with zipfile.ZipFile(result) as archive:
            files = {i.filename for i in archive.infolist() if not i.is_dir()}
            self.assertEqual(files, {'SHSHD Runtime/SHSHD Runtime.exe', 'SHSHD Runtime/_internal/runtime.dll'})
            self.assertEqual(archive.read('SHSHD Runtime/_internal/runtime.dll'), b'authored dependency fixture')
        checksum = result.with_name(result.name + '.sha256').read_bytes()
        self.assertEqual(checksum, f'{hashlib.sha256(result.read_bytes()).hexdigest()}  {result.name}\n'.encode('ascii'))

    @unittest.skipIf(os.name == 'nt', 'Unix modes and symbolic links')
    def test_linux_download_preserves_executable_mode_and_relative_link(self):
        program = self.bundle / 'SHSHD Runtime'
        program.write_bytes(b'authored executable fixture')
        program.chmod(0o755)
        (self.bundle / 'library.so').write_bytes(b'authored dependency fixture')
        (self.bundle / 'alias.so').symlink_to('library.so')
        result = package(self.root, 'linux-x64', '0123456789abcdef0123456789abcdef01234567')
        self.assertEqual(result.name, 'shshd-runtime-0123456789ab-linux-x64.tar.gz')
        with tarfile.open(result) as archive:
            self.assertEqual(archive.getmember('SHSHD Runtime/SHSHD Runtime').mode, 0o755)
            link = archive.getmember('SHSHD Runtime/alias.so')
            self.assertTrue(link.issym())
            self.assertEqual(link.linkname, 'library.so')
            self.assertEqual((link.uid, link.gid, link.uname, link.gname), (0, 0, '', ''))

    def test_game_inputs_in_the_app_abort_packaging(self):
        (self.bundle / 'SHSHD Runtime.exe').write_bytes(b'authored executable fixture')
        for name in ('GAME.APK', 'GAME.IPA', 'story.EXP', 'episodes.RAR', 'library.json', 'libshs09.so',
                     'Surviving_HS', 'Surviving_HS.app', 'CoD', 'CoD.app', 'res_generated', 'native-vm.c', 'player.shs-auto.json'):
            with self.subTest(name=name):
                path = self.bundle / name
                path.write_bytes(b'authored prohibited fixture')
                try:
                    with self.assertRaisesRegex(ValueError, 'Game content or research output'):
                        package(self.root, 'windows-x64', 'test')
                finally:
                    path.unlink()
        self.assertFalse((self.root / 'dist/downloads').exists())

    @unittest.skipIf(os.name == 'nt', 'Symbolic links require Windows privileges')
    def test_links_cannot_pull_files_from_outside_the_app(self):
        outside = self.root / 'private.bin'
        outside.write_bytes(b'authored private fixture')
        link = self.bundle / 'external.bin'
        link.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes its bundle'):
            audit_bundle(self.bundle)
        outside.unlink()
        with self.assertRaisesRegex(ValueError, 'Broken application link'):
            audit_bundle(self.bundle)

    def test_tag_cannot_redirect_archive_output(self):
        for label in ('../outside', '/absolute', 'bad\nlabel'):
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, 'Build label'):
                package(self.root, 'windows-x64', label)
        self.assertFalse((self.root / 'dist/downloads').exists())

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_app_smoke_mode_ignores_existing_library_and_exits_cleanly(self):
        supplied = self.root / 'existing-library'
        supplied.mkdir()
        manifest = supplied / 'library.json'
        manifest.write_bytes(b'authored invalid library that smoke mode must ignore')
        before = manifest.read_bytes()
        env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
                   PYGAME_HIDE_SUPPORT_PROMPT='1')
        result = subprocess.run([sys.executable, '-m', 'exp_runtime.application', '--smoke-test',
                                 '--library', str(supplied)], cwd=self.root, env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual(list(supplied.iterdir()), [manifest])


if __name__ == '__main__':
    unittest.main()
