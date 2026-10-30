import json
import lzma
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch
from zipfile import BadZipFile, ZipFile

from exp_runtime.content import (ContentError, ContentLibrary, ExpArchive, NATIVE_MEMBER,
                              HD_APP_EXECUTABLE, HD_ASSET_MAP, HD_RESOURCE_PREFIX,
                              digest, import_game)
from test_vm import program


def metadata(title='An original test episode'):
    result = struct.pack('>HH', 7, 2)
    for text in (title, 'École', 'Scuola', 'Schule', 'Escuela'):
        data = text.encode('utf-8')
        result += struct.pack('>H', len(data)) + data
    return result


def archive(records, *, compressed=(), aliases=None):
    aliases = aliases or {}
    start = 9 + 6 * (len(records) + len(aliases))
    entries, bodies = {}, bytearray()
    for resource_id, data in records.items():
        entries[resource_id] = start + len(bodies)
        if resource_id in compressed:
            alone = lzma.compress(data, format=lzma.FORMAT_ALONE,
                                  filters=[dict(id=lzma.FILTER_LZMA1, dict_size=4096)])
            encoded = alone[:5] + struct.pack('<II', len(data), len(data)) + alone[13:]
        else:
            encoded = data
        bodies += struct.pack('>III', len(encoded), len(data), int(resource_id in compressed)) + encoded
    for alias, original in aliases.items():
        entries[alias] = entries[original]
    return (b'CSPUD' + struct.pack('>I', len(entries))
            + b''.join(struct.pack('>HI', key, offset) for key, offset in sorted(entries.items())) + bodies)


def compressed_archive(body, decoded_size, *, properties=0x5D, dictionary=4096):
    wrapper = struct.pack('<BIII', properties, dictionary, decoded_size, decoded_size) + body
    return (b'CSPUD' + struct.pack('>IHI', 1, 42, 15)
            + struct.pack('>III', len(wrapper), decoded_size, 1) + wrapper)


FAKE_NATIVE = b'authored native-profile test fixture, never executed'
FAKE_HD_EXECUTABLE = b'authored HD-executable test fixture, never executed'


def make_apk(path, episode):
    with ZipFile(path, 'w') as apk:
        apk.writestr(NATIVE_MEMBER, FAKE_NATIVE)
        apk.writestr('assets/Assets/Test.exp', episode)
        apk.writestr('assets/Assets/42', b'base image')
        # 1500/25100 are plain extras for HD-ipa-fallback tests; 25100 avoids
        # FOOTBALL_SCRIPTS (25001-25021, 25023), which extract_football
        # requires to look like real KiWi programs once 25001 exists at all.
        apk.writestr('assets/Assets/1500', b'android shared-content bytes')
        apk.writestr('assets/Assets/25100', b'android bytecode-range bytes')
        apk.writestr('assets/Assets/images/42.png', b'UI atlas with the same number')
        apk.writestr('assets/Assets/0042', b'noncanonical resource name')
        apk.writestr('assets/Assets/audio/music/nested/8201.mp3', b'wrong audio namespace')
        apk.writestr('assets/Assets/audio/music/8201.mp3', b'music bytes')
        apk.writestr('../escape', b'this ZIP path must never be extracted')


def make_hd_ipa(path, resources):
    with ZipFile(path, 'w') as ipa:
        ipa.writestr(HD_APP_EXECUTABLE, FAKE_HD_EXECUTABLE)
        for resource_id, data in resources.items():
            ipa.writestr(f'{HD_RESOURCE_PREFIX}{resource_id}', data)


class ArchiveTests(unittest.TestCase):
    def test_compression_aliases_and_five_utf8_titles(self):
        payload = metadata()
        exp = ExpArchive(archive({1: payload, 25001: program(0x33).to_bytes()},
                                  compressed=(1,), aliases={9: 1}))
        self.assertEqual(exp.read(1), payload)
        self.assertEqual(exp.read(9), payload)
        self.assertEqual(exp.metadata().titles[1], 'École')
        self.assertEqual(len(exp.metadata().titles), 5)
        self.assertEqual(set(exp.programs()), {25001})

    def test_lzma_end_markers_and_property_combinations(self):
        for lc, lp, pb, dictionary in ((3, 0, 2, 4096), (1, 2, 0, 8192), (4, 0, 4, 65536)):
            for payload in (b'', b'Authored compressed resource. ' * 40):
                with self.subTest(lc=lc, lp=lp, pb=pb, dictionary=dictionary, size=len(payload)):
                    filters = [dict(id=lzma.FILTER_LZMA1, dict_size=dictionary, lc=lc, lp=lp, pb=pb)]
                    body = lzma.compress(payload, format=lzma.FORMAT_RAW, filters=filters)
                    data = compressed_archive(body, len(payload),
                                              properties=(pb * 5 + lp) * 9 + lc, dictionary=dictionary)
                    self.assertEqual(ExpArchive(data).read(42), payload)

    def test_lzma_without_an_end_marker(self):
        payload = b'Authored EXP payload without an end marker.'
        # Authored bytes encoded with liblzma's LZMA1EXT, preset 6,
        # dict_size=4096, lc=3, lp=0, pb=2, ext_flags=0 (no end marker).
        body = bytes.fromhex(
            '00209d4a869a6f72a1742c35d7e646a4a143ef922720aa1f6768'
            '0636cae34f2ca70b0395361c7b4f0e64e17454c006')
        self.assertEqual(ExpArchive(compressed_archive(body, len(payload))).read(42), payload)

    def test_lzma_stops_at_the_declared_output_boundary(self):
        payload = b'Declared EXP output.'
        body = lzma.compress(payload + b' More range-coded bytes beyond the declared output.',
                             format=lzma.FORMAT_RAW,
                             filters=[dict(id=lzma.FILTER_LZMA1, dict_size=4096)])
        self.assertEqual(ExpArchive(compressed_archive(body, len(payload))).read(42), payload)

    def test_invalid_and_short_lzma_bodies_are_rejected(self):
        payload = b'An authored complete payload.'
        body = lzma.compress(payload, format=lzma.FORMAT_RAW,
                             filters=[dict(id=lzma.FILTER_LZMA1, dict_size=4096)])
        for encoded, declared in ((b'', len(payload)), (body[:5], len(payload)),
                                  (b'\xFF' + body[1:], len(payload)), (body, len(payload) + 1)):
            with self.subTest(body=encoded, declared=declared), self.assertRaises(ContentError):
                ExpArchive(compressed_archive(encoded, declared)).read(42)

    def test_bad_offsets_flags_sizes_and_lzma_are_rejected(self):
        original = archive({1: metadata()}, compressed=(1,))
        offset, = struct.unpack_from('>I', original, 11)
        mutations = [(11, '>I', 0), (offset, '>I', len(original) + 1),
                     (offset + 8, '>I', 2), (offset + 12 + 5, '<I', 999)]
        for at, fmt, value in mutations:
            with self.subTest(at=at), self.assertRaises(ContentError):
                data = bytearray(original)
                struct.pack_into(fmt, data, at, value)
                ExpArchive(bytes(data)).read(1)
        with self.assertRaises(ContentError):
            ExpArchive(original[:-1])

    def test_missing_exact_resource_is_not_guessed_from_neighbors(self):
        exp = ExpArchive(archive({1: metadata(), 26000: b'an authored resource'}))
        with self.assertRaisesRegex(ContentError, 'grouped lookup is unsupported'):
            exp.read(26001)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        self.profile.start()
        self.addCleanup(self.profile.stop)
        self.data = archive({1: metadata(), 25001: program(0x33).to_bytes(),
                             42: b'episode low ID must not replace base art', 26000: b'episode art'})
        self.apk = self.root / 'user.apk'
        make_apk(self.apk, self.data)

    def test_import_deduplicates_and_remains_relocatable_without_sources(self):
        folder = self.root / 'episodes' / 'nested'
        folder.mkdir(parents=True)
        (folder / 'again.EXP').write_bytes(self.data)
        (folder / 'second.exp').write_bytes(archive({1: metadata('Another episode'), 25001: program(0x33).to_bytes()}))
        target = self.root / 'library'
        manifest = import_game(self.apk, [folder.parent], target)
        self.assertEqual(len(manifest['episodes']), 2)
        self.assertEqual(len(list((target / 'content').glob('*.exp'))), 1)
        self.assertFalse((self.root / 'escape').exists())
        moved = self.root / 'moved-library'
        target.rename(moved)
        self.apk.unlink()
        shutil.rmtree(folder.parent)
        with ContentLibrary(moved) as library:
            resources = library.open_episode('Test.exp')
            self.assertEqual(resources.read_asset(42), b'base image')
            self.assertEqual(library.read_ui_asset('images/42.png'), b'UI atlas with the same number')
            for invalid in ('42', '../42', 'fonts/../42', 'images//42.png', '/images/42.png'):
                with self.subTest(name=invalid), self.assertRaises(ContentError):
                    library.read_ui_asset(invalid)
            self.assertEqual(resources.read_asset(8201), b'music bytes')
            self.assertEqual(resources.read_asset(26000), b'episode art')
            self.assertEqual(resources.program(25001).instructions[0].opcode, 0x33)
            self.assertEqual(resources.identity['episode_sha256'], digest(self.data))

    def test_adding_an_episode_again_restores_its_missing_file(self):
        target = self.root / 'library'
        data = archive({1: metadata('Another episode'), 25001: program(0x33).to_bytes()})
        episode = self.root / 'second.exp'
        episode.write_bytes(data)
        import_game(self.apk, [episode], target)
        with ContentLibrary(target) as library:
            path = target / library.select('second.exp')['file']
            path.unlink()                                       # what Verify Library does to a damaged one
            before = len(library.episodes)
            self.assertEqual(library.add_episodes([episode]), 0)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(len(library.episodes), before)
            self.assertEqual(library.restore_builtin_episodes(), 0)     # nothing built in is lost

    def test_legacy_android_manifest_retains_profile_and_resources(self):
        target = self.root / 'legacy'
        manifest = import_game(self.apk, [], target)
        manifest.update(format='shs-content-library', version=1)
        del manifest['game']
        path = target / 'library.json'
        path.write_text(json.dumps(manifest))
        before = path.read_bytes()
        with ContentLibrary(target) as library:
            self.assertEqual((library.game_id, library.kind), ('shs', 'apk'))
            self.assertEqual(library.open_episode('Test.exp').read_asset(42), b'base image')
            self.assertEqual(library.read_asset(8201), b'music bytes')
        self.assertEqual(path.read_bytes(), before)

    def test_failed_import_is_atomic_and_preserves_existing_library(self):
        target = self.root / 'library'
        broken = self.root / 'broken.exp'
        broken.write_bytes(b'not an EXP')
        with self.assertRaises(ContentError):
            import_game(self.apk, [broken], target)
        self.assertFalse(target.exists())
        self.assertFalse(list(self.root.glob('.exp-import-*')))
        import_game(self.apk, [], target)
        original = (target / 'library.json').read_bytes()
        with self.assertRaisesRegex(ContentError, 'already exists'):
            import_game(self.apk, [], target)
        self.assertEqual((target / 'library.json').read_bytes(), original)

    def test_unknown_native_profile_and_modified_content_are_rejected(self):
        target = self.root / 'library'
        with patch('exp_runtime.shs.content.NATIVE_SHA256', '0' * 64), self.assertRaisesRegex(ContentError, 'Unsupported game APK'):
            import_game(self.apk, [], target)
        manifest = import_game(self.apk, [], target)
        with (target / manifest['apk']['file']).open('ab') as stream:
            stream.write(b'changed after import')
        with self.assertRaisesRegex(ContentError, 'content changed'):
            ContentLibrary(target)

    def test_manifest_cannot_point_outside_library(self):
        target = self.root / 'library'
        manifest = import_game(self.apk, [], target)
        manifest['apk']['file'] = '../user.apk'
        (target / 'library.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ContentError, 'Invalid content path'):
            ContentLibrary(target)

    def test_corrupt_lazy_asset_reports_content_error(self):
        target = self.root / 'library'
        import_game(self.apk, [], target)
        with ContentLibrary(target) as library:
            resources = library.open_episode('Test.exp')
            with patch.object(library.apk, 'read', side_effect=BadZipFile('CRC mismatch')):
                with self.assertRaisesRegex(ContentError, 'Cannot read APK member'):
                    resources.read_asset(42)

    def test_hd_ipa_is_optional_and_unlocks_mapped_assets_only(self):
        target = self.root / 'library'
        manifest = import_game(self.apk, [], target)
        self.assertNotIn('hd_ipa', manifest)
        with ContentLibrary(target) as library:
            self.assertIsNone(library.hd_asset(268))  # no HD ipa imported

        hd_target = self.root / 'hd-library'
        hd_ipa = self.root / 'hd.ipa'
        hd_id = HD_ASSET_MAP[268]
        with patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE)):
            make_hd_ipa(hd_ipa, {hd_id: b'real hd mask bytes'})
            manifest = import_game(self.apk, [], hd_target, hd_ipa_path=hd_ipa)
            self.assertIn('hd_ipa', manifest)
            with ContentLibrary(hd_target) as library:
                self.assertEqual(library.hd_asset(268), b'real hd mask bytes')
                self.assertIsNone(library.hd_asset(999999))  # no correspondence recorded
                resources = library.open_episode('Test.exp')
                self.assertEqual(resources.hd_asset(268), b'real hd mask bytes')

    def test_hd_resource_reads_are_cached_not_redecompressed_every_call(self):
        # An `available()` gate re-checked every rendered frame (HdFootballRenderer's, HdWordRenderer's) used to
        # call hd_raw_resource()/hd_asset() straight through to a fresh zlib-decompressing zip read every single
        # time -- profiled live, this was over half the frame cost during football and word-grid gameplay.
        target = self.root / 'hd-cache-library'
        hd_ipa = self.root / 'hd-cache.ipa'
        hd_id = HD_ASSET_MAP[268]
        with patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE)):
            make_hd_ipa(hd_ipa, {hd_id: b'real hd mask bytes', 17: b'raw by exact id'})
            import_game(self.apk, [], target, hd_ipa_path=hd_ipa)
            with ContentLibrary(target) as library:
                from exp_runtime.content import _zip_read
                with patch('exp_runtime.content._zip_read', wraps=_zip_read) as read:
                    for _ in range(5):
                        self.assertEqual(library.hd_asset(268), b'real hd mask bytes')
                    for _ in range(5):
                        self.assertEqual(library.hd_raw_resource(17), b'raw by exact id')
                    for _ in range(5):
                        self.assertEqual(library.android_asset(1500), b'android shared-content bytes')
                    self.assertEqual(read.call_count, 3)                         # one real read per distinct id

    def test_hd_only_permanent_ui_chrome_has_no_android_fallback(self):
        # Real HD binary confirmed (SHSEngine::initPermanents, resource
        # 0x9b=155): the dialogue "Continue" button and the choice-timer
        # wheel are genuinely new HD-only content with no Android original
        # at all -- unlike every other HD_ASSET_MAP entry, android_asset(155)
        # must keep raising, never silently substitute something unrelated.
        target = self.root / 'library'
        import_game(self.apk, [], target)
        with ContentLibrary(target) as library:
            self.assertIsNone(library.hd_asset(155))
            resources = library.open_episode('Test.exp')
            with self.assertRaises(ContentError):
                resources.android_asset(155)
            with self.assertRaises(ContentError):
                resources.read_asset(155)  # no HD ipa, and no Android original either

        hd_target = self.root / 'hd-library-155'
        hd_ipa = self.root / 'hd-155.ipa'
        with patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE)):
            make_hd_ipa(hd_ipa, {HD_ASSET_MAP[155]: b'continue + timer wheel master image'})
            import_game(self.apk, [], hd_target, hd_ipa_path=hd_ipa)
            with ContentLibrary(hd_target) as library:
                resources = library.open_episode('Test.exp')
                self.assertEqual(resources.hd_asset(155), b'continue + timer wheel master image')
                self.assertEqual(resources.read_asset(155), b'continue + timer wheel master image')

    def test_box_theme_packs_map_to_their_hd_renumbered_ids(self):
        # Real HD binary confirmed (GameModel::setBubbleSex): HD renumbers
        # each of the four per-theme dialogue/choice box packs, but every
        # renumbered pack keeps its Android counterpart's 14-frame layout,
        # so this is a direct id substitution with no frame remapping.
        target = self.root / 'hd-library-box-themes'
        hd_ipa = self.root / 'hd-box-themes.ipa'
        with patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE)):
            make_hd_ipa(hd_ipa, {HD_ASSET_MAP[204]: b'theme 1', HD_ASSET_MAP[220]: b'theme 2',
                                  HD_ASSET_MAP[236]: b'theme default', HD_ASSET_MAP[252]: b'theme 3'})
            import_game(self.apk, [], target, hd_ipa_path=hd_ipa)
            with ContentLibrary(target) as library:
                resources = library.open_episode('Test.exp')
                self.assertEqual(resources.read_asset(204), b'theme 1')
                self.assertEqual(resources.read_asset(220), b'theme 2')
                self.assertEqual(resources.read_asset(236), b'theme default')
                self.assertEqual(resources.read_asset(252), b'theme 3')

    def test_unsupported_hd_ipa_executable_is_rejected_atomically(self):
        target = self.root / 'library'
        hd_ipa = self.root / 'hd.ipa'
        make_hd_ipa(hd_ipa, {HD_ASSET_MAP[268]: b'mask'})
        with self.assertRaisesRegex(ContentError, 'Unsupported HD ipa executable'):
            import_game(self.apk, [], target, hd_ipa_path=hd_ipa)
        self.assertFalse(target.exists())

    def test_hd_ipa_manifest_cannot_point_outside_library(self):
        target = self.root / 'library'
        hd_ipa = self.root / 'hd.ipa'
        with patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE)):
            make_hd_ipa(hd_ipa, {HD_ASSET_MAP[268]: b'mask'})
            manifest = import_game(self.apk, [], target, hd_ipa_path=hd_ipa)
            manifest['hd_ipa']['file'] = '../hd.ipa'
            (target / 'library.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ContentError, 'Invalid content path'):
                ContentLibrary(target)

    def test_hd_ipa_shared_content_range_preferred_by_same_id(self):
        """Per-scene content (background/portrait ids >= 1000) ships at the
        same numeric id on both platforms -- unlike chrome, which needs
        HD_ASSET_MAP's explicit per-id correspondence. See content.py's
        HD_SHARED_CONTENT_RANGE and legacy/findings.md, "53% ... questioned
        and checked properly"."""
        target = self.root / 'library'
        hd_ipa = self.root / 'hd.ipa'
        with patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE)):
            make_hd_ipa(hd_ipa, {1500: b'real hd background bytes'})
            import_game(self.apk, [], target, hd_ipa_path=hd_ipa)
            with ContentLibrary(target) as library:
                self.assertEqual(library.hd_asset(1500), b'real hd background bytes')
                self.assertEqual(library.read_asset(1500), b'real hd background bytes')
                resources = library.open_episode('Test.exp')
                self.assertEqual(resources.read_asset(1500), b'real hd background bytes')

    def test_android_asset_bypasses_hd_substitution(self):
        """Chrome icons (relationship indicators, the scene badge) need the
        Android original specifically, as a size reference, even when an HD
        ipa is attached and would otherwise transparently upgrade the same
        id -- see desktop_dialogue.py's chrome_image / Desktop._chrome_image
        and legacy/findings.md, "Chrome icons render oversized with an HD
        ipa"."""
        target = self.root / 'library'
        hd_ipa = self.root / 'hd.ipa'
        with patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE)):
            make_hd_ipa(hd_ipa, {1500: b'real hd background bytes'})
            import_game(self.apk, [], target, hd_ipa_path=hd_ipa)
            with ContentLibrary(target) as library:
                self.assertEqual(library.read_asset(1500), b'real hd background bytes')
                self.assertEqual(library.android_asset(1500), b'android shared-content bytes')
                resources = library.open_episode('Test.exp')
                self.assertEqual(resources.android_asset(1500), b'android shared-content bytes')

    def test_hd_ipa_never_substitutes_bytecode_range_ids(self):
        """Ids >= 25000 are KiWi bytecode programs (confirmed by their
        `kiwi` header against a real APK, see legacy/findings.md) -- even
        if an id in that range happens to also exist in the HD ipa's own
        bank, it must never be substituted, or a script load would run the
        wrong dialect entirely."""
        target = self.root / 'library'
        hd_ipa = self.root / 'hd.ipa'
        with patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE)):
            make_hd_ipa(hd_ipa, {25100: b'HD dialect bytecode -- must never be used'})
            import_game(self.apk, [], target, hd_ipa_path=hd_ipa)
            with ContentLibrary(target) as library:
                self.assertIsNone(library.hd_asset(25100))
                self.assertEqual(library.read_asset(25100), b'android bytecode-range bytes')
                resources = library.open_episode('Test.exp')
                self.assertEqual(resources.read_asset(25100), b'android bytecode-range bytes')

    def test_hd_ipa_shared_content_range_absent_falls_back_to_android(self):
        target = self.root / 'library'
        hd_ipa = self.root / 'hd.ipa'
        with patch('exp_runtime.content.HD_APP_SHA256', digest(FAKE_HD_EXECUTABLE)):
            make_hd_ipa(hd_ipa, {HD_ASSET_MAP[268]: b'mask'})  # no id 1500 in the HD ipa
            import_game(self.apk, [], target, hd_ipa_path=hd_ipa)
            with ContentLibrary(target) as library:
                self.assertIsNone(library.hd_asset(1500))
                self.assertEqual(library.read_asset(1500), b'android shared-content bytes')
