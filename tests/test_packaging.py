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

from tools.package_desktop import NOTICES, archive_name, audit_bundle, bundle_name, executable, package, scratch_data_env


class PackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bundle = self.root / 'dist/desktop/SHSHD Runtime'
        self.bundle.mkdir(parents=True)
        (self.bundle / NOTICES).write_text('third-party notices fixture\n' * 100, encoding='utf-8')

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
            self.assertEqual(files, {'SHSHD Runtime/SHSHD Runtime.exe', 'SHSHD Runtime/_internal/runtime.dll',
                                     f'SHSHD Runtime/{NOTICES}'})
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

    def test_an_app_without_its_notices_is_refused(self):
        # Decision 2 (owner, 2026-11-17): both apps carry THIRD_PARTY_NOTICES.txt.
        (self.bundle / 'SHSHD Runtime.exe').write_bytes(b'authored executable fixture')
        (self.bundle / NOTICES).unlink()
        with self.assertRaisesRegex(ValueError, NOTICES):
            package(self.root, 'windows-x64', 'v0.1.0')

    def test_the_creator_has_its_own_names_and_archive(self):
        self.assertEqual(bundle_name('windows-x64', True), 'SHSHD Runtime Creator')
        self.assertEqual(bundle_name('macos-arm64', True), 'SHSHD Runtime Creator.app')
        self.assertEqual(executable(Path('B'), 'macos-x64', True), Path('B/Contents/MacOS/SHSHD Runtime Creator'))
        self.assertEqual(executable(Path('B'), 'windows-x64', True), Path('B/SHSHD Runtime Creator.exe'))
        self.assertEqual(archive_name('v1.1.0', 'linux-x64', True), 'shshd-runtime-creator-v1.1.0-linux-x64.tar.gz')
        self.assertEqual(archive_name('v1.1.0', 'windows-x64'), 'shshd-runtime-v1.1.0-windows-x64.zip')
        creator = self.root / 'dist/desktop/SHSHD Runtime Creator'
        creator.mkdir()
        (creator / 'SHSHD Runtime Creator.exe').write_bytes(b'authored executable fixture')
        (creator / '_internal').mkdir()
        (creator / '_internal' / NOTICES).write_text('notices\n' * 200, encoding='utf-8')
        result = package(self.root, 'windows-x64', 'v1.1.0', creator=True)
        self.assertEqual(result.name, 'shshd-runtime-creator-v1.1.0-windows-x64.zip')
        (creator / 'story.expproj').write_bytes(b'{}')                       # an author's project never ships
        with self.assertRaises(ValueError):
            package(self.root, 'windows-x64', 'v1.1.0', creator=True)

    @unittest.skipUnless(importlib.util.find_spec('mcp') and importlib.util.find_spec('pygame'),
                         "Install the creator-mcp extra for the Creator's smoke checks")
    def test_the_creators_smoke_checks_pass_from_python(self):
        # The checks the packaged smoke test runs on the frozen Creator (decisions 5 and 6), here on `python -m`.
        from tools.package_desktop import creator_checks
        env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYGAME_HIDE_SUPPORT_PROMPT='1',
                   QT_QPA_PLATFORM='offscreen')
        creator_checks([sys.executable, '-m', 'exp_runtime.creator'], self.root, env)

    def test_the_scratch_data_folder_is_the_platforms_root(self):
        env = scratch_data_env({}, Path('S'))
        key = 'LOCALAPPDATA' if sys.platform == 'win32' else 'HOME' if sys.platform == 'darwin' else 'XDG_DATA_HOME'
        self.assertEqual(env, {key: 'S'})

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
