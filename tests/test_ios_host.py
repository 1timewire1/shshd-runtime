"""Authored checks for the shared-engine iOS host and unsigned packaging."""
import hashlib
import importlib.util
from importlib.metadata import Distribution
import json
from pathlib import Path
import plistlib
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tools import build_ios
from tools.package_ios import audit_binary, audit_ios, package

ROOT = Path(__file__).resolve().parents[1]


def native_binary(*, platform=2, signed=False):
    # Authored Mach-O load commands only; this is not executable game code.
    commands = struct.pack('<6I', 0x32, 24, platform, 15 << 16, 26 << 16, 0)
    if signed:
        commands += struct.pack('<4I', 0x1d, 16, 0, 0)
    return struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 2, 1 + signed, len(commands), 0, 0) + commands


class IOSPrototypeTests(unittest.TestCase):
    def test_embedded_distribution_version_comes_from_project_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            with patch.object(build_ios, 'project_version', return_value='9.8.7'):
                build_ios.stage_metadata(path)
            found = list(Distribution.discover(path=[str(path)]))
            # This fork's name, which app_info.runtime_version looks up (the update check needs a real version).
            self.assertEqual([(d.metadata['Name'], d.version) for d in found], [('shshd-runtime', '9.8.7')])
            self.assertEqual([d.version for d in Distribution.discover(name='shshd-runtime', path=[str(path)])],
                             ['9.8.7'])

    def test_device_probe_uses_both_production_profiles_and_atomic_saves(self):
        spec = importlib.util.spec_from_file_location('exp_ios_probe', ROOT / 'ios/probe/exp_ios_probe.py')
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        with tempfile.TemporaryDirectory() as temporary:
            report = json.loads(probe.request('{"operation":"verify"}', temporary))
            self.assertEqual(report['status'], 'passed')
            self.assertTrue(any(c.startswith('shs:') for c in report['checks']))
            self.assertTrue(any(c.startswith('cod:') for c in report['checks']))
            self.assertEqual(json.loads(Path(temporary, 'ios-verification.json').read_text()), report)
            self.assertEqual([p.name for p in Path(temporary).iterdir()], ['ios-verification.json'])
            with self.assertRaises(ValueError):
                probe.request('{"operation":"eval"}', temporary)

    def test_dependency_cache_requires_the_recorded_digest(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(build_ios, 'DEPENDENCIES', Path(temporary)):
            spec = dict(url='https://example.invalid/authored.whl', sha256=hashlib.sha256(b'authored').hexdigest())
            with self.assertRaisesRegex(ValueError, 'not cached'):
                build_ios.download(spec, offline=True)
            path = Path(temporary, 'authored.whl')
            path.write_bytes(b'authored')
            self.assertEqual(build_ios.download(spec, offline=True), path)
            path.write_bytes(b'damaged')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                build_ios.download(spec, offline=True)


class IOSPackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bundle = self.root / 'dist/ios/iphoneos/EXP Runtime.app'
        self.framework = self.bundle / 'Frameworks/Python.framework'
        self.framework.mkdir(parents=True)
        self.info = dict(CFBundleExecutable='EXP Runtime', CFBundleSupportedPlatforms=['iPhoneOS'])
        (self.bundle / 'Info.plist').write_bytes(plistlib.dumps(self.info))
        (self.bundle / 'EXP Runtime').write_bytes(native_binary())
        (self.framework / 'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleExecutable='Python')))
        (self.framework / 'Python').write_bytes(native_binary())

    def test_ipa_contains_only_the_audited_payload_and_matching_checksum(self):
        (self.root / 'private.exp').write_bytes(b'authored excluded fixture')
        # Windows cannot preserve executable bits; packaging must supply the
        # target permissions for the app and every embedded framework itself.
        for file in self.bundle.rglob('*'):
            if file.is_file():
                file.chmod(0o644)
        path = package(self.root, 'prototype')
        with ZipFile(path) as archive:
            self.assertIsNone(archive.testzip())
            self.assertTrue(all(n.startswith('Payload/EXP Runtime.app/') for n in archive.namelist()))
            self.assertEqual(len(archive.namelist()), 4)
            for member in archive.infolist():
                self.assertEqual(member.create_system, 3)
                expected = 0o644 if member.filename.endswith('Info.plist') else 0o755
                self.assertEqual(member.external_attr >> 16, stat.S_IFREG | expected)
        self.assertEqual(path.with_suffix('.ipa.sha256').read_text(),
                         f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n')

    def test_signed_frameworks_and_simulator_slices_are_rejected(self):
        for binary in (native_binary(platform=7), native_binary(signed=True), b'\xca\xfe\xba\xbe' + b'\0' * 40):
            with self.subTest(binary=binary[:8]):
                (self.framework / 'Python').write_bytes(binary)
                with self.assertRaises(ValueError):
                    package(self.root)
        self.assertFalse((self.root / 'dist/downloads').exists())

    def test_truncated_or_invalid_native_headers_are_rejected(self):
        path = self.framework / 'Python'
        for binary in (b'bad', native_binary()[:-1], native_binary()[:32] + struct.pack('<6I', 0x32, 0, 2, 0, 0, 0)):
            path.write_bytes(binary)
            with self.assertRaises(ValueError):
                audit_binary(path)

    def test_original_inputs_and_loose_extensions_are_rejected(self):
        for name in ('original.ipa', 'episode.exp', 'player.shs-save.json', 'loose.so', 'embedded.mobileprovision'):
            path = self.bundle / name
            path.write_bytes(b'authored excluded fixture')
            with self.subTest(name=name), self.assertRaises(ValueError):
                package(self.root)
            path.unlink()

    def test_python_framework_references_must_resolve_both_directions(self):
        placeholder = self.bundle / 'app_packages' / 'sample.fwork'
        placeholder.parent.mkdir()
        placeholder.write_text('Frameworks/Python.framework/Python\n')
        origin = self.framework / 'Python.origin'
        origin.write_text('app_packages/sample.fwork\n')
        audit_ios(self.bundle)
        for reference in ('../elsewhere', '/outside', ''):
            placeholder.write_text(reference)
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                audit_ios(self.bundle)
        placeholder.write_text('Frameworks/Python.framework/Python\n')
        origin.write_text('wrong.fwork')
        with self.assertRaisesRegex(ValueError, 'Broken embedded'):
            audit_ios(self.bundle)

    def test_build_labels_cannot_escape_the_download_directory(self):
        for label in ('../outside', '/absolute', 'bad\nlabel'):
            with self.subTest(label=label), self.assertRaises(ValueError):
                package(self.root, label)


if __name__ == '__main__':
    unittest.main()
