"""Component boundaries, namespace staging and file-tools behavior."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.cli import main
from tools import build_ios, build_packages
from tools.components import COMPONENTS, RUNTIME_COMPONENTS, check_versions, source_files, source_roots
from test_content import archive, metadata
from test_vm import program

ROOT = Path(__file__).resolve().parents[1]


class ComponentTests(unittest.TestCase):
    def test_release_tag_mismatch_stops_before_building_distributions(self):
        with tempfile.TemporaryDirectory() as temporary:
            for tag in ('v0.0.0', check_versions(ROOT), 'vnext'):
                with self.subTest(tag=tag), patch.object(build_packages.subprocess, 'run') as run:
                    with self.assertRaisesRegex(ValueError, 'must match the package version'):
                        build_packages.build(Path(temporary), tag=tag)
                    run.assert_not_called()
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_component_version_mismatch_stops_before_building_distributions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'pyproject.toml').write_text('version = "1.2.3"\n', encoding='utf-8')
            for component in COMPONENTS:
                path = root / 'packages' / component / 'pyproject.toml'
                path.parent.mkdir(parents=True)
                version = '1.2.2' if component == 'cod' else '1.2.3'
                path.write_text(f'version = "{version}"\n', encoding='utf-8')
            with patch.object(build_packages, 'ROOT', root), patch.object(build_packages.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'must share the root project version'):
                    build_packages.build(root / 'dist', tag='v1.2.3')
                run.assert_not_called()

    def test_formats_source_works_without_engine_games_or_site_packages(self):
        # -S prevents the development environment from masking undeclared
        # imports. Only the formats source root is offered to this process.
        script = '''
import sys
from importlib.util import find_spec
sys.path.insert(0, sys.argv[1])
from exp_runtime.formats import ExpArchive, BitmapFont, MenuFont, decode_program
from exp_runtime.cli import _build_parser
assert _build_parser().parse_args(['inspect', 'authored.exp']).command == 'inspect'
for name in ('exp_runtime.engine', 'exp_runtime.application', 'exp_runtime.shs', 'exp_runtime.cod', 'PIL', 'pygame'):
    assert find_spec(name) is None, name
'''
        result = subprocess.run([sys.executable, '-I', '-S', '-c', script, str(source_roots(ROOT)[0])],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ios_stages_every_component_without_namespace_overlap_or_private_files(self):
        expected = source_files(ROOT, RUNTIME_COMPONENTS)
        self.assertTrue(source_files(ROOT).keys() - expected.keys())
        self.assertFalse(any('creator' in p.parts for p in expected))
        self.assertNotIn(Path('exp_runtime/__init__.py'), expected)
        self.assertTrue(check_versions(ROOT))
        for component in COMPONENTS:
            self.assertEqual((ROOT / 'packages' / component / 'LICENSE').read_bytes(), (ROOT / 'LICENSE').read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            build_ios.stage_runtime(destination)
            actual = {p.relative_to(destination) for p in destination.rglob('*') if p.is_file()}
            self.assertEqual(actual, set(expected))
            for relative, source in expected.items():
                self.assertEqual((destination / relative).read_bytes(), source.read_bytes())

    def test_extraction_decodes_exact_ids_and_never_overwrites(self):
        data = archive({1: metadata('Authored'), 25001: program(0x33).to_bytes(), 64000: b'authored bytes'},
                       compressed=(25001,))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / 'source.exp', root / 'resources'
            source.write_bytes(data)
            with redirect_stdout(StringIO()):
                main(['extract', str(source), '--output', str(output)])
            self.assertEqual({p.name for p in output.iterdir()}, {'1.bin', '25001.bin', '64000.bin'})
            self.assertEqual((output / '25001.bin').read_bytes(), program(0x33).to_bytes())
            (output / '64000.bin').write_bytes(b'keep this edit')
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                main(['extract', str(source), '--output', str(output)])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual((output / '64000.bin').read_bytes(), b'keep this edit')

    def test_corrupt_compression_leaves_no_partial_extraction(self):
        data = bytearray(archive({1: metadata(), 2: b'authored'}, compressed=(2,)))
        offset = struct.unpack_from('>I', data, 17)[0]
        data[offset + 12] = 255  # Invalid LZMA property, after the first good record.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / 'source.exp', root / 'resources'
            source.write_bytes(data)
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(['extract', str(source), '--output', str(output)])
            self.assertFalse(output.exists())
            self.assertEqual(list(root.iterdir()), [source])
