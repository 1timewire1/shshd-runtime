"""Authored IPA containers and font-discovery tests; no original content."""
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import plistlib
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZipFile

from PIL import Image

from exp_runtime.content import (ContentError, ContentLibrary, IOS_PROFILE,
                                 digest, import_game, is_bundled)
from exp_runtime.ios_fonts import FACES, resolve_face
from exp_runtime.fonts import FontError
from test_content import FAKE_NATIVE, archive, metadata
from test_ui_assets import image_pack, node
from test_vm import program


APP = 'Payload/Authored.app/'
ASSETS = APP + 'res_generated/'
INFO = dict(CFBundleIdentifier='com.ea.shs.row', CFBundleExecutable='Surviving_HS',
            CFBundleShortVersionString='1.4.2', CFBundleVersion='1.4.3.54')


def string_bank(strings):
    head = 9 + len(strings) * 2
    offsets, body = [], bytearray()
    for text in strings:
        offsets.append(head + len(body)); body += text.encode('latin-1') + b'\0'
    return (struct.pack('>iBhh', 1, 0, 0, len(strings))
            + struct.pack(f'>{len(strings)}h', *offsets) + body)


def authored_assets():
    """Synthetic resources exercising each required native asset format."""
    png = BytesIO(); Image.new('RGBA', (2, 2), (10, 20, 30, 255)).save(png, format='PNG')
    assets = {key: png.getvalue() for key in (6, 7, 8, 9, 526, 528, *range(2615, 2624))}
    assets[12] = string_bank(['Authored'] * 303)
    assets[13] = (struct.pack('>bbbbh', 6, 2, 0, 0, 80)
                  + (struct.pack('>hhh', 280, 45, 100) + node((0, 0, 10, 10)) * 100) * 80)
    for key, count in ((15, 108), (125, 60), (203, 14), (219, 14), (235, 14), (251, 14), (271, 8)):
        assets[key] = image_pack(count=count, pixels=b'\x01\x01\xff\x01\x02\x03' * count)
    assets[267] = image_pack(marker=-2, pixels=b'\x80\x96' + b'\0' * (128 * 150))
    for key, count in ((289, 154), (445, 48), (495, 1), (498, 1), (501, 1),
                       *((n, 1) for n in range(506, 526, 2))):
        assets[key] = (struct.pack('>Bhbhhhhh', 16, count, 0, 0, 0, 0, 1, 2)
                       + struct.pack('>h', count) + struct.pack('>6h', 0, 0, 1, 1, 1, 1) * count
                       + b'\xff\x01\x02\x03' * 4)
    for key in (*range(507, 527, 2), 527, 529):
        assets[key] = struct.pack('>BBbhbBhhb', 1, 0, 0, 1, 1, 65, 0, 0, 1)
    for key in (530, 531):
        assets[key] = (struct.pack('>bBbhb', 1, 0, 0, 1, 1) + b'A'
                       + struct.pack('>hhBB', -1, 1, 1, 1) + b'\xff\x01\x02\x03')
    assets.update({14: b'other native data', 42: b'base art', 8203: b'base music'})
    return assets


ASSET_DATA = authored_assets()


def make_ipa(path, episode, *, info=None, native=FAKE_NATIVE, binary=False):
    with ZipFile(path, 'w') as package:
        package.writestr(APP + 'Info.plist', plistlib.dumps(INFO if info is None else info,
                          fmt=plistlib.FMT_BINARY if binary else plistlib.FMT_XML))
        if native is not None:
            package.writestr(APP + 'Surviving_HS', native)
        package.writestr(APP + 'Test.exp', episode)
        for key, value in ASSET_DATA.items():
            package.writestr(ASSETS + str(key), value)
        package.writestr(ASSETS + '0042', b'noncanonical number')
        package.writestr(ASSETS + 'nested/42', b'nested number')
        package.writestr('../escape', b'never extracted')


class IPAImportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / 'source.IPA'
        self.library = self.root / 'library'
        self.episode = archive({1: metadata(), 25001: program(0x33).to_bytes(),
                                42: b'episode low ID', 26000: b'episode art'})
        make_ipa(self.source, self.episode)

    def test_import_without_fonts_preserves_native_ids_and_relocates(self):
        duplicate = self.root / 'duplicate.exp'; duplicate.write_bytes(self.episode)
        with patch('exp_runtime.ios_fonts.resolve_face', side_effect=AssertionError('import requested a font')):
            manifest = import_game(self.source, [duplicate], self.library)
        self.assertEqual((manifest['version'], manifest['profile']), (1, IOS_PROFILE))
        self.assertNotIn('apk', manifest)
        self.assertEqual(len(manifest['episodes']), 1)
        self.assertTrue(is_bundled(manifest['episodes'][0]))
        self.assertFalse((self.root / 'escape').exists())
        moved = self.root / 'moved'; self.library.rename(moved)
        self.source.unlink(); duplicate.unlink()
        with ContentLibrary(moved) as library:
            resources = library.open_episode('Test.exp')
            self.assertEqual(resources.read_asset(13), ASSET_DATA[13])
            self.assertEqual(resources.read_ui_resource(13), ASSET_DATA[12])
            self.assertEqual(resources.read_ui_resource(14), ASSET_DATA[13])
            self.assertEqual(resources.read_ui_resource(126), ASSET_DATA[125])
            self.assertEqual(resources.read_asset(42), b'base art')
            self.assertEqual(resources.read_asset(26000), b'episode art')
            self.assertEqual(resources.read_asset(8203), b'base music')
            self.assertEqual(resources.program(25001).instructions[0].opcode, 0x33)
            self.assertEqual(resources.identity, dict(profile=IOS_PROFILE,
                             ipa_sha256=manifest['ipa']['sha256'], episode_sha256=digest(self.episode)))
            with self.assertRaisesRegex(ContentError, 'IPA resource 126'):
                resources.read_asset(126)  # UI mapping must never leak to scripts.
            with self.assertRaisesRegex(ContentError, 'no named UI asset'):
                library.read_ui_asset('fonts/ArialMT14.fnt')
            self.assertEqual(library.ensure_builtin_episodes(), 0)

    def test_versions_are_informational_and_executable_is_not_required(self):
        for version, native, bundle in (('9.9.9', b'a different executable', 'com.ea.shs.us'),
                                        ('unversioned', None, 'com.ea.shs.us'),
                                        ('1.4.3.53', b'the free edition', 'com.ea.shslite.row')):
            with self.subTest(version=version):
                info = dict(CFBundleIdentifier=bundle, CFBundleVersion=version)
                make_ipa(self.source, self.episode, info=info, native=native)
                path = self.root / version
                manifest = import_game(self.source, [], path)
                self.assertEqual(manifest['ipa']['app'], info)
                self.assertNotIn('native_sha256', manifest['ipa'])
                with ContentLibrary(path) as library:
                    self.assertEqual(library.app_info, info)
                    self.assertTrue(library.open_episode('Test.exp').programs)

    def test_binary_plist_and_additional_episodes_keep_ipa_manifest(self):
        make_ipa(self.source, self.episode, binary=True)
        import_game(self.source, [], self.library)
        extra = self.root / 'extra.exp'
        extra.write_bytes(archive({1: metadata('Another story'), 25001: program(0x33).to_bytes()}))
        with ContentLibrary(self.library) as library:
            self.assertEqual(library.add_episodes([extra]), 1)
            self.assertEqual(library.add_episodes([extra]), 0)
            self.assertEqual(library.manifest['profile'], IOS_PROFILE)
            self.assertFalse(is_bundled(library.select('extra.exp')))
        with ContentLibrary(self.library) as library:
            self.assertEqual(len(library.episodes), 2)

    def test_invalid_identifier_ambiguous_app_and_duplicate_members_are_atomic(self):
        mutations = ('identifier', 'second_app', 'duplicate', 'invalid_xml')
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                make_ipa(self.source, self.episode,
                         info=dict(INFO, CFBundleIdentifier='com.example.other') if mutation == 'identifier' else None)
                if mutation in ('second_app', 'duplicate', 'invalid_xml'):
                    with ZipFile(self.source, 'a') as package, warnings.catch_warnings():
                        warnings.simplefilter('ignore', UserWarning)
                        if mutation == 'second_app':
                            package.writestr('Payload/Other.app/Info.plist', plistlib.dumps(INFO))
                        elif mutation == 'duplicate':
                            package.writestr(ASSETS + '42', b'ambiguous art')
                        else:
                            # Rebuild without the valid plist, so this tests the
                            # XML parser error rather than duplicate detection.
                            items = {n: package.read(n) for n in package.namelist()}
                    if mutation == 'invalid_xml':
                        items[APP + 'Info.plist'] = b'<?xml version="1.0"?><plist>broken'
                        with ZipFile(self.source, 'w') as package:
                            for n, data in items.items(): package.writestr(n, data)
                with self.assertRaises(ContentError):
                    import_game(self.source, [], self.library)
                self.assertFalse(self.library.exists())
                self.assertFalse(list(self.root.glob('.exp-import-*')))

    def test_required_asset_absence_format_and_frame_ranges_are_checked(self):
        replacements = ((13, None), (12, b'invalid strings'), (289, ASSET_DATA[495]),
                        (267, image_pack(marker=-2, pixels=b'\x01\x01\0')), (7, b'not a PNG'))
        for resource, replacement in replacements:
            with self.subTest(resource=resource):
                make_ipa(self.source, self.episode)
                with ZipFile(self.source) as package:
                    items = {n: package.read(n) for n in package.namelist()}
                key = ASSETS + str(resource)
                if replacement is None:
                    del items[key]
                else:
                    items[key] = replacement
                with ZipFile(self.source, 'w') as package:
                    for n, data in items.items(): package.writestr(n, data)
                with self.assertRaisesRegex(ContentError, str(resource)):
                    import_game(self.source, [], self.library)
                self.assertFalse(self.library.exists())
                self.assertFalse(list(self.root.glob('.exp-import-*')))

    def test_hash_path_and_profile_tampering_are_rejected(self):
        manifest = import_game(self.source, [], self.library)
        path = self.library / 'library.json'
        for field, value in (('file', '../source.IPA'), ('sha256', '0' * 64)):
            changed = json.loads(json.dumps(manifest)); changed['ipa'][field] = value
            path.write_text(json.dumps(changed))
            with self.subTest(field=field), self.assertRaises(ContentError): ContentLibrary(self.library)
        for field, value in (('version', 2), ('profile', 'shs-android-1.0.9'), ('apk', manifest['ipa'])):
            changed = dict(manifest, **{field: value})
            path.write_text(json.dumps(changed))
            with self.subTest(field=field), self.assertRaises(ContentError): ContentLibrary(self.library)
        changed = json.loads(json.dumps(manifest))
        changed['episodes'][0]['ipa_member'] = '../outside.exp'
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ContentError, 'bundled episode path'): ContentLibrary(self.library)
        path.write_text(json.dumps(manifest))
        with (self.library / manifest['ipa']['file']).open('ab') as stream: stream.write(b'changed')
        with self.assertRaisesRegex(ContentError, 'content changed'): ContentLibrary(self.library)

    def test_built_in_story_uses_ios_string_bank_and_21_scripts(self):
        strings = [''] * 303
        strings[193:198] = ['Authored football', 'Fr', 'It', 'De', 'Es']
        with ZipFile(self.source) as package: items = {n: package.read(n) for n in package.namelist()}
        items[ASSETS + '12'] = string_bank(strings)
        for scene in range(25001, 25022): items[ASSETS + str(scene)] = program(0x33).to_bytes()
        with ZipFile(self.source, 'w') as package:
            for n, data in items.items(): package.writestr(n, data)
        manifest = import_game(self.source, [], self.library)
        self.assertEqual(len(manifest['episodes']), 2)
        with ContentLibrary(self.library) as library:
            football = library.open_episode('Football_Star.exp')
            self.assertEqual(set(football.programs), set(range(25001, 25022)))
            self.assertEqual(football.record['titles'][0], 'Authored football')
            self.assertTrue(is_bundled(football.record))
            self.assertEqual(library.ensure_builtin_episodes(), 0)


class IOSFontDiscoveryTests(unittest.TestCase):
    def test_installed_original_precedes_system_default(self):
        face = FACES['ArialRoundedMTBold']
        font = SimpleNamespace(getname=lambda: (face.family, face.style))
        with patch('exp_runtime.ios_fonts._candidates', return_value=[(Path('original.ttf'), 0)]), \
             patch('exp_runtime.ios_fonts.ImageFont.truetype', return_value=font), \
             patch('exp_runtime.ios_fonts._system_default', side_effect=AssertionError('unnecessary fallback')):
            self.assertEqual(resolve_face(face), (Path('original.ttf'), 0))

    def test_fontconfig_substitute_is_rejected_before_configured_default(self):
        face = FACES['ArialRoundedMTBold']
        other = SimpleNamespace(getname=lambda: ('Unrequested substituted font', 'Regular'))
        default = SimpleNamespace(getname=lambda: ('System UI', 'Regular'))
        with patch('exp_runtime.ios_fonts._candidates', return_value=[(Path('substitute.ttf'), 0)]), \
             patch('exp_runtime.ios_fonts._system_default', return_value=[(Path('system.ttc'), 2)]), \
             patch('exp_runtime.ios_fonts.ImageFont.truetype', side_effect=[other, default]), \
             self.assertLogs(level='WARNING'):
            self.assertEqual(resolve_face(face), (Path('system.ttc'), 2))

    def test_unreadable_original_uses_system_default(self):
        default = SimpleNamespace(getname=lambda: ('System UI', 'Bold'))
        with patch('exp_runtime.ios_fonts._candidates', return_value=[(Path('broken.ttf'), 0)]), \
             patch('exp_runtime.ios_fonts._system_default', return_value=[(Path('system.ttf'), 0)]), \
             patch('exp_runtime.ios_fonts.ImageFont.truetype', side_effect=[OSError('unreadable'), default]), \
             self.assertLogs(level='WARNING'):
            self.assertEqual(resolve_face(FACES['TrebuchetMS_Bold']), (Path('system.ttf'), 0))

    def test_no_fonts_reports_the_actual_missing_system_dependency(self):
        with patch('exp_runtime.ios_fonts._candidates', return_value=[]), \
             patch('exp_runtime.ios_fonts._system_default', return_value=[]):
            with self.assertRaisesRegex(FontError, 'No usable system font'):
                resolve_face(FACES['ArialMT'])


LOCAL_IPA = Path('decomp/shs/SurvivingHighSchoolPaid1.4.2.ipa')


@unittest.skipUnless(LOCAL_IPA.is_file(), 'optional player IPA is absent')
class LocalIPATests(unittest.TestCase):
    def test_actual_system_default_renders_when_original_faces_are_absent(self):
        from exp_runtime import ios_fonts
        from exp_runtime.fonts import TextStyle, layout_text
        original_candidates = ios_fonts._candidates
        # Keep fontconfig's generic lookup available on Linux while hiding
        # the named game faces. No fonts are copied into the authored fixture.
        def candidates(face):
            return original_candidates(face) if face.family == 'sans-serif' else ()
        library = SimpleNamespace(base_members=set())
        with patch.object(ios_fonts, '_candidates', side_effect=candidates), self.assertLogs(level='WARNING'):
            for name in ('ArialRoundedMTBold16', 'ArialMT14', 'TrebuchetMS_Bold14',
                         'TrebuchetMS_Italic14', 'PajamaHip24'):
                font, atlas = ios_fonts.render_font(library, name)
                layout = layout_text(font, 'An authored name', 200, TextStyle(font.line_height))
                self.assertGreater(layout.width, 0)
                self.assertTrue(atlas.getbbox())
                self.assertIs(ios_fonts.render_font(library, name)[0], font)

    def test_supplied_package_imports_all_bundled_stories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'library'
            manifest = import_game(LOCAL_IPA, [], path)
            self.assertEqual(len(manifest['episodes']), 4)
            with ContentLibrary(path) as library:
                self.assertEqual(len(library.base_members), 857)
                for record in library.episodes:
                    self.assertTrue(library.open_episode(record['id']).programs)

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is absent')
    def test_bundled_music_and_shared_track_cues_play_through_desktop(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.audio import music_cue
        from exp_runtime.runtime import Session
        from exp_runtime.desktop import Desktop
        import pygame
        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'library'; import_game(LOCAL_IPA, [], path)
            with ContentLibrary(path) as library:
                ui = Desktop(Session(library.open_episode('The_New_Girl.exp')), audio=True)
                self.assertTrue(ui.audio)
                # All ten bundled MP3s, plus the three cues that seek within
                # them. Exercise resource lookup and the real SDL decoder;
                # importing/rendering with audio=False cannot verify these.
                for requested in (8203, 8210, 8215, *range(8226, 8233), 8204, 8211, 8216):
                    with self.subTest(requested=requested), self.assertNoLogs(level='WARNING'):
                        self.assertIn(music_cue(requested).asset_id, library.base_members)
                        ui.session.engine.music_id = requested
                        saved = ui.session.snapshot()
                        ui._sync_audio()
                        self.assertTrue(ui.music_loaded)
                        self.assertTrue(pygame.mixer.music.get_busy())
                        self.assertEqual(ui.session.snapshot(), saved)
                pygame.mixer.music.stop()

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is absent')
    def test_new_girl_name_entry_timer_and_save_restore(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.runtime import Session
        from exp_runtime.desktop import Desktop
        from test_runtime import answer_screen
        import pygame
        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'library'; import_game(LOCAL_IPA, [], path)
            with ContentLibrary(path) as library:
                ui = Desktop(Session(library.open_episode('The_New_Girl.exp')), audio=False)
                seen = set()
                for _ in range(150):
                    ui.tick(3000); ui.render()
                    self.assertIsNone(ui.error)
                    s = ui.session; name = s.pending.name; seen.add(name)
                    if name == 'dialogue':
                        from test_shared_dialogue import check_original_page
                        check_original_page(self, s)
                    saved = s.snapshot()
                    pixels = pygame.image.tobytes(ui.canvas, 'RGBA')
                    ui.session = s = Session.from_snapshot(s.resources, saved)
                    ui.render()
                    self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGBA'), pixels)
                    self.assertEqual(s.snapshot(), saved)
                    if name == 'word_game': break
                    if name == 'text_input':
                        ui.input_error = 'invalid'; ui.render(); self.assertIsNone(ui.error)
                        ui.input_error = None; s.answer('Zoe')
                    elif name in ('choice', 'character_picker'): s.answer(0)
                    elif name in ('loading', 'delay'): s.tick(15000)
                    else: answer_screen(s)
                else:
                    self.fail('The original opening did not reach the timed word choices')
                self.assertTrue({'presentation', 'dialogue', 'text_input', 'choice', 'word_game'} <= seen)
                renderer = ui.choice_renderer
                renderer.canvas.fill((255, 255, 255))
                renderer.draw_timer((0, 0), 0)
                start = pygame.image.tobytes(renderer.canvas, 'RGBA')
                renderer.canvas.fill((255, 255, 255))
                renderer.draw_timer((0, 0), 1)
                self.assertNotEqual(pygame.image.tobytes(renderer.canvas, 'RGBA'), start)

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is absent')
    def test_football_targets_feedback_and_grid_use_ipa_assets(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.runtime import Session
        from exp_runtime.desktop import Desktop
        from test_football import resources as football_resources, start_play, wait_for
        from test_word_grid import tutorial_resources, play_phase
        import pygame
        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'library'; import_game(LOCAL_IPA, [], path)
            with ContentLibrary(path) as library:
                resources = library.open_episode('Football_Star.exp')
                resources.programs[25001] = football_resources(100, 100).program(25001)
                ui = Desktop(Session(resources), audio=False)
                s = ui.session; game = s.engine.football
                start_play(s)
                wait_for(s, lambda: all(t.phase in (3, 6) for t in game.targets))
                ui.render(); self.assertIsNone(ui.error)
                saved = s.snapshot(); pixels = pygame.image.tobytes(ui.canvas, 'RGBA')
                ui.session = Session.from_snapshot(resources, saved); ui.render()
                self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGBA'), pixels)
                self.assertEqual(ui.session.snapshot(), saved)
                ui.session.answer(0)
                for _ in range(100):
                    ui.tick(16); ui.render(); self.assertIsNone(ui.error)
                self.assertIsNotNone(ui.football_renderer.feedback_font())
                resources = library.open_episode('The_New_Girl.exp')
                resources.programs[25001] = tutorial_resources().program(25001)
                ui = Desktop(Session(resources), audio=False)
                for _ in range(14): ui.tick(250)
                ui.render(); self.assertIsNone(ui.error)
                play_phase(ui.session); ui.session.answer(); play_phase(ui.session)
                ui.render(); self.assertIsNone(ui.error)
                saved = ui.session.snapshot(); pixels = pygame.image.tobytes(ui.canvas, 'RGBA')
                ui.session = Session.from_snapshot(resources, saved); ui.render()
                self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGBA'), pixels)
                self.assertEqual(ui.session.snapshot(), saved)
