"""Game selection, colliding resource banks and legacy content compatibility."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import ImageFont

from exp_runtime.audio import music_cue
from exp_runtime.content import ContentError, ContentLibrary, import_game
from exp_runtime.games import COD_IOS, COD_IOS_FREE, COD_IOS_FREE_LOCALIZED
from exp_runtime.launcher import default_library, remember_library
from exp_runtime.menu import MenuStrings
from exp_runtime.runtime import SaveError, Session
from test_content import archive, metadata
from test_ipa import APP, ASSETS, ASSET_DATA, make_ipa, string_bank
from test_label_layout import authored_dialogue
from test_runtime import Resources, answer_screen, host_call, text_words
from test_ui_assets import image_pack
from test_vm import program

LOCAL_COD_IPA = Path('decomp/cod/Cause+of+Death+(World)+1.3.4.ipa')


def make_cod_ipa(path, episode, *, missing=None, info=None, free=False, localized=False):
    """Authored paid, compact free or multilingual free resource banks."""
    # Reuse only authored image/layout fixtures and Pillow's own default font.
    # No original game bytes, executable, proprietary font or art is included.
    assets = {12: episode, 13: string_bank([f'CoD string {i}' for i in range(257)]),
              14: ASSET_DATA[13], 42: b'CoD base art', 291: ImageFont.load_default().font_bytes}
    for key in (6, 7, 8, 9):
        assets[key] = image_pack(pixels=b'\x01\x01\xff\x01\x02\x03')
    for cod, shs in ((16, 15), (126, 125), (204, 203), (220, 219), (236, 235),
                     (252, 251), (268, 267), (292, 526), (293, 527), (294, 528),
                     (295, 529), (296, 530), (297, 531)):
        assets[cod] = ASSET_DATA[shs]
    assets[272] = image_pack(count=16, pixels=b'\x01\x01\xff\x01\x02\x03' * 16)
    assets.update({key: f'CoD music {key}'.encode() for key in range(8201, 8210)})
    assets.update({key: f'Script asset {key}'.encode() for key in (1001, 2001, 3000, 8005)})
    if free:
        shift = 5 if localized else 1
        shifted = {}
        for key, data in assets.items():
            if key == 13:
                key = 14
            elif 14 <= key <= 297:
                key += shift
            shifted[key] = data
        assets = shifted
        assets[13] = episode
        if localized:
            for key in range(15, 19):
                assets[key] = string_bank([f'Language {key} string {i}' for i in range(257)])
    with ZipFile(path, 'w') as package:
        package.writestr(APP + 'Info.plist', plistlib.dumps(info if info is not None else dict(
            CFBundleIdentifier='com.ea.causeofdeathfree.inc' if free else 'com.ea.causeofdeath.bv',
            CFBundleVersion='any-compatible-version')))
        for key, data in assets.items():
            if key != missing:
                package.writestr(ASSETS + str(key), data)


class GameLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.episode = archive({1: metadata('Authored shared story'), 25001: program(0x33).to_bytes(),
                                42: b'ignored low episode ID', 26000: b'episode-specific art'})
        self.shs = self.root / 'shs.ipa'
        self.cod = self.root / 'cod.ipa'
        make_ipa(self.shs, self.episode)
        make_cod_ipa(self.cod, self.episode)

    def test_colliding_ids_never_cross_game_banks_or_save_identities(self):
        shs_path, cod_path = self.root / 'shs', self.root / 'cod'
        import_game(self.shs, [], shs_path, game='shs')
        manifest = import_game(self.cod, [], cod_path, game='cod')
        self.assertEqual((manifest['game'], manifest['profile']), ('cod', COD_IOS))
        self.assertEqual(manifest['episodes'][0]['builtin'], 'volume-one')
        self.cod.unlink()  # Only retained imports are needed to reopen.
        with ContentLibrary(shs_path) as shs, ContentLibrary(cod_path) as cod:
            a, b = shs.open_episode('Test.exp'), cod.open_episode('Volume_One.exp')
            self.assertEqual(a.record['id'], b.record['id'])
            self.assertEqual(a.read_asset(42), b'base art')
            self.assertEqual(b.read_asset(42), b'CoD base art')
            self.assertEqual(a.read_asset(26000), b.read_asset(26000))
            self.assertNotEqual(a.identity, b.identity)
            s = Session(a); s.advance()
            with self.assertRaisesRegex(SaveError, 'same imported game'):
                Session.from_snapshot(b, s.snapshot())
            self.assertNotEqual(s.save_path, Session(b).save_path)
            self.assertEqual(cod.ensure_builtin_episodes(), 0)
            self.assertEqual(cod.missing_music_ids, ())
            with self.assertRaisesRegex(ContentError, 'SHS IPA'):
                cod.add_music_apk(self.root / 'does-not-exist.apk')
            self.assertEqual(b.read_ui_resource(528), ASSET_DATA[526])
            with self.assertRaises(ContentError):
                b.read_asset(528)  # Host font roles do not become script aliases.
            self.assertEqual(MenuStrings.load(cod)[125], 'CoD string 117')

    def test_free_edition_imports_under_its_own_profile_and_opens(self):
        free, path = self.root / 'free.ipa', self.root / 'free'
        make_cod_ipa(free, self.episode, free=True)
        manifest = import_game(free, [], path, game='cod')
        self.assertEqual((manifest['game'], manifest['profile']), ('cod', COD_IOS_FREE))
        self.assertEqual(manifest['episodes'][0]['builtin'], 'volume-one')
        free.unlink()
        with ContentLibrary(path) as library:
            self.assertEqual(library.game_id, 'cod')
            episode = library.open_episode('Volume_One.exp')
            # Members are addressed by reference (1.3.4) numbers after translation.
            self.assertEqual(episode.read_asset(42), b'CoD base art')
            self.assertEqual(episode.read_ui_resource(528), ASSET_DATA[526])
            self.assertEqual(MenuStrings.load(library)[125], 'CoD string 117')
            self.assertEqual(library.ensure_builtin_episodes(), 0)
        # The paid IPA is refused against the free library, and vice versa.
        for key, data in (('profile', COD_IOS), ('profile', 'shs-ios-assets-v1')):
            (path / 'library.json').write_text(json.dumps(dict(manifest, **{key: data})))
            with self.subTest(profile=data), self.assertRaises(ContentError):
                ContentLibrary(path)

    def test_asset_layout_selection_relocation_and_manifest_validation(self):
        # All layouts deliberately use the same identifier and version. The
        # multilingual free fixture previously read a string bank as a layout.
        profiles = (COD_IOS, COD_IOS_FREE, COD_IOS_FREE_LOCALIZED)
        for free, localized, expected in ((False, False, COD_IOS), (True, False, COD_IOS_FREE),
                                           (True, True, COD_IOS_FREE_LOCALIZED)):
            with self.subTest(profile=expected):
                source, path = self.root / f'{expected}.ipa', self.root / expected
                make_cod_ipa(source, self.episode, free=free, localized=localized,
                             info=dict(CFBundleIdentifier='com.ea.causeofdeathfree.bv',
                                       CFBundleVersion='arbitrary'))
                manifest = import_game(source, [], path, game='cod')
                self.assertEqual(manifest['profile'], expected)
                self.assertEqual(len(manifest['episodes']), 1)
                source.unlink()
                moved = self.root / (expected + '-moved')
                path.rename(moved)
                before = (moved / 'library.json').read_bytes()
                with ContentLibrary(moved) as library:
                    episode = library.open_episode('Volume_One.exp')
                    self.assertEqual(library.profile, expected)
                    self.assertEqual(library.read_asset(14), ASSET_DATA[13])
                    self.assertEqual(library.read_asset(268), ASSET_DATA[267])
                    self.assertEqual(library.read_asset(291), ImageFont.load_default().font_bytes)
                    self.assertEqual(library.read_ui_resource(528), ASSET_DATA[526])
                    self.assertEqual(library.read_ui_resource(533), ASSET_DATA[531])
                    self.assertEqual(MenuStrings.load(library)[125], 'CoD string 117')
                    for key in (1001, 2001, 3000, 8005):
                        self.assertEqual(episode.read_asset(key), f'Script asset {key}'.encode())
                    self.assertEqual(episode.read_asset(26000), b'episode-specific art')
                    self.assertEqual(library.ensure_builtin_episodes(), 0)
                self.assertEqual((moved / 'library.json').read_bytes(), before)
                for wrong in profiles:
                    if wrong == expected:
                        continue
                    (moved / 'library.json').write_text(json.dumps(dict(manifest, profile=wrong)))
                    with self.subTest(wrong=wrong), self.assertRaisesRegex(ContentError, 'asset layout'):
                        ContentLibrary(moved)

    def test_free_layout_detection_still_validates_assets_and_aborts_failed_imports(self):
        for localized, mask in ((False, 269), (True, 273)):
            for missing in (14, mask):
                with self.subTest(localized=localized, missing=missing):
                    source = self.root / 'incomplete.ipa'
                    destination = self.root / 'incomplete'
                    make_cod_ipa(source, self.episode, free=True, localized=localized, missing=missing)
                    with self.assertRaisesRegex(ContentError, 'Unsupported CoD asset layout'):
                        import_game(source, [], destination, game='cod')
                    self.assertFalse(destination.exists())
                    self.assertFalse(list(self.root.glob('.exp-import-*')))

    def test_wrong_game_missing_assets_and_spoofed_manifest_are_rejected(self):
        target = self.root / 'target'
        for source, expected in ((self.shs, 'cod'), (self.cod, 'shs')):
            with self.subTest(game=expected), self.assertRaisesRegex(ContentError, 'belongs to'):
                import_game(source, [], target, game=expected)
            self.assertFalse(target.exists())
        for missing in (12, 13, 14, 268, 291, 294):
            make_cod_ipa(self.cod, self.episode, missing=missing)
            with self.subTest(missing=missing), self.assertRaises(ContentError):
                import_game(self.cod, [], target)
            self.assertFalse(target.exists())
        make_cod_ipa(self.cod, self.episode)
        manifest = import_game(self.cod, [], target)
        for field, value in (('game', 'shs'), ('profile', 'shs-ios-assets-v1'),
                             ('format', 'shs-content-library'), ('version', 2)):
            (target / 'library.json').write_text(json.dumps(dict(manifest, **{field: value})))
            with self.subTest(field=field), self.assertRaises(ContentError):
                ContentLibrary(target)

    def test_legacy_ipa_library_and_save_open_without_rewriting(self):
        path = self.root / 'legacy'
        manifest = import_game(self.shs, [], path)
        manifest.update(format='shs-content-library', version=2)
        del manifest['game']
        location = path / 'library.json'
        location.write_text(json.dumps(manifest))
        before = location.read_bytes()
        with ContentLibrary(path) as library:
            self.assertEqual(library.game_id, 'shs')
            s = Session(library.open_episode('Test.exp')); s.advance()
            saved = s.snapshot(); saved['format'] = 'shs-runtime-save'
            restored = Session.from_snapshot(s.resources, saved)
            self.assertEqual(restored.snapshot(), s.snapshot())
        self.assertEqual(location.read_bytes(), before)

    def test_runtime_audit_reads_the_selected_source_kind(self):
        from tools.audit_runtime import audit
        for game, source in (('shs', self.shs), ('cod', self.cod)):
            path = self.root / game
            manifest = import_game(source, [], path)
            result = audit(path)
            self.assertEqual((result['game'], result['ipa_sha256'], result['failures']),
                             (game, manifest['ipa']['sha256'], []))


class GameServiceTests(unittest.TestCase):
    def test_named_dialogue_service_in_both_games_survives_save_restore(self):
        words, refs = text_words('The $GROUP', 'A $GROUP reply.')
        r = Resources(program(*host_call(15, *refs, 12, -1), 0x21, (0x1f, 0xfe01), words=words))
        r.dialogue_layout = authored_dialogue
        for game in ('shs', 'cod'):
            with self.subTest(game=game):
                r.library.game_id = game
                s = Session(r); s.engine.strings['$GROUP'] = 'team'
                action = s.advance()
                self.assertEqual((action.name, action.details['speaker'], action.details['text']),
                                 ('dialogue', 'The team', 'A team reply.'))
                self.assertIsNone(s.dialogue_page().portrait)
                s.tick(600)
                restored = Session.from_snapshot(r, s.snapshot())
                self.assertEqual(restored.snapshot(), s.snapshot())
                self.assertEqual(answer_screen(restored).request.args, (0,))
                bad = copy.deepcopy(s.snapshot()); bad['pending']['details']['speaker'] = 'Wrong'
                with self.assertRaises(SaveError): Session.from_snapshot(r, bad)

    def test_music_routing_and_unverified_services_use_selected_game(self):
        self.assertEqual((music_cue(8202).asset_id, music_cue(8202).start_ms), (8201, 2800))
        self.assertEqual((music_cue(8202, game='cod').asset_id, music_cue(8202, game='cod').start_ms), (8202, 0))
        for key in ('shs', 'cod'):
            r = Resources(program(*host_call(79, 8210), 0x33)); r.library.game_id = key
            s = Session(r); s.advance()
            self.assertEqual((s.engine.music_id, s.engine.sound_id), (8210, -1) if key == 'shs' else (-1, 8210))
        for service in (9, 91, 95, 101):
            r = Resources(program(*host_call(service, 1), 0x33)); r.library.game_id = 'cod'
            s = Session(r)
            self.assertEqual(s.advance().name, 'unhandled_yield')
            before = s.vm.snapshot()
            self.assertEqual(Session.from_snapshot(r, s.snapshot()).vm.snapshot(), before)

    def test_cod_relationship_cache_uses_native_ids(self):
        r = Resources(program(0x33)); r.library.game_id = 'cod'
        s = Session(r)
        change = s.engine.prepare_relationship(1)
        self.assertEqual(change.asset_id, 3002)
        self.assertEqual(s.engine.numbers[s.engine.number_key(1, 3000)], 3002)


class LibraryLocationTests(unittest.TestCase):
    def test_legacy_locations_migrate_without_losing_either_game(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            old = root / 'SHS Runtime'; old.mkdir()
            legacy = json.dumps(dict(version=1, library=str(root / 'existing-shs')))
            (old / 'launcher.json').write_text(legacy)
            with patch('exp_runtime.launcher.user_data_directory', return_value=root / 'EXP Runtime'):
                self.assertEqual(default_library('shs'), root / 'existing-shs')
                remember_library(root / 'my-cod', 'cod')
                self.assertEqual(default_library('cod'), root / 'my-cod')
                self.assertEqual(default_library('shs'), root / 'existing-shs')
                remember_library(root / 'new-shs', 'shs')
                self.assertEqual(default_library('cod'), root / 'my-cod')
            self.assertEqual((old / 'launcher.json').read_text(), legacy)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is absent')
class GameChooserTests(unittest.TestCase):
    def setUp(self):
        GameLibraryTests.setUp(self)
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        self.preferences = patch('exp_runtime.launcher.user_data_directory', return_value=self.root / 'EXP Runtime')
        self.preferences.start(); self.addCleanup(self.preferences.stop)
        frozen = patch('sys.frozen', True, create=True)
        frozen.start(); self.addCleanup(frozen.stop)

    def test_asset_free_chooser_requires_the_selected_game_assets(self):
        from exp_runtime.application import Application
        app = Application(audio=False, check_updates=False); self.addCleanup(app.close)
        self.assertEqual(app.screen, 'games')
        app.render()
        self.assertEqual({command for _, command in app.renderer.buttons},
                         {('choose_game', 'shs'), ('choose_game', 'cod'), ('options',)})
        app.choose_game('cod'); app.render()
        self.assertEqual((app.screen, app.selected_game, app.library), ('setup', 'cod', None))
        app.import_paths([self.shs])
        with self.assertRaisesRegex(ContentError, 'belongs to'): app.job.result(timeout=10)
        app.tick(0)
        self.assertIsNone(app.library)
        app.message = ''
        app.import_paths([self.cod]); app.job.result(timeout=10); app.tick(0)
        self.assertEqual((app.screen, app.library.game_id), ('main', 'cod'))
        self.assertEqual(default_library('cod'), app.directory.resolve())

    def test_switch_checkpoints_and_discards_game_asset_caches(self):
        from exp_runtime.application import Application
        for key, source in (('shs', self.shs), ('cod', self.cod)):
            path = self.root / key
            import_game(source, [], path)
            remember_library(path, key)
        app = Application(audio=False, check_updates=False); self.addCleanup(app.close)
        app.choose_game('shs'); app.start(resume=False)
        original = app.game
        original.session.engine.numbers[19] = 123
        app.switch_games()
        self.assertEqual((app.screen, app.library.game_id, app.game), ('main', 'cod', None))
        with self.assertRaisesRegex(ContentError, 'belongs to'):
            app.open_library(self.root / 'shs')
        self.assertEqual(app.library.game_id, 'cod')
        app.start(resume=False)
        self.assertIsNot(app.game, original)
        self.assertNotIn(19, app.game.session.engine.numbers)
        app.switch_games(); app.start()
        self.assertEqual(app.game.session.engine.numbers[19], 123)
        with patch.object(app.state, 'checkpoint', side_effect=OSError('cannot save')):
            with self.assertRaisesRegex(OSError, 'cannot save'): app.switch_games()
        self.assertEqual((app.screen, app.library.game_id), ('game', 'shs'))

    def test_switch_without_other_library_opens_chooser_and_setup_back_stays_there(self):
        from exp_runtime.application import Application
        path = self.root / 'shs'
        import_game(self.shs, [], path)
        remember_library(path, 'shs')
        app = Application(audio=False, check_updates=False); self.addCleanup(app.close)
        app.choose_game('shs'); app.start(resume=False)
        app.switch_games()
        self.assertEqual((app.screen, app.selected_game, app.library), ('games', None, None))
        app.choose_game('cod')
        self.assertEqual(app.screen, 'setup')
        app.back()
        self.assertEqual((app.screen, app.selected_game), ('games', None))


@unittest.skipUnless(LOCAL_COD_IPA.is_file() and importlib.util.find_spec('pygame'),
                     'optional original CoD IPA/desktop is absent')
class LocalCoDTests(unittest.TestCase):
    def test_volume_one_opening_named_dialogue_saves_and_original_music(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.application import Application
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'cod'
            import_game(LOCAL_COD_IPA, [], path, game='cod')
            app = Application(path, audio=True, check_updates=False)
            try:
                for screen in ('main', 'options', 'title_languages', 'library'):
                    app.screen = screen; app.menu_age = 4000; app.render()
                    if screen == 'main':
                        self.assertEqual(app.buttons[3][1], ('switch_games',))
                        self.assertTrue(all(app.renderer.menu_fonts[1].glyph(c) for c in 'SwitchGame'))
                app.selected = app.library.select('Volume_One.exp')['id']
                app.start(resume=False)
                ui, seen, speakers, wrapped = app.game, set(), set(), set()
                for _ in range(150):
                    session, action = ui.session, ui.session.pending
                    seen.add(action.request.yield_id)
                    self.assertIn(action.name, ('presentation', 'dialogue', 'choice'))
                    if action.name != 'choice': session.tick(4000)
                    ui.render(); self.assertIsNone(ui.error)
                    if action.name == 'dialogue':
                        from test_shared_dialogue import check_original_page
                        check_original_page(self, session)
                        speakers.add(action.details['speaker'])
                        page = session.dialogue_page()
                        if action.details['speaker'] in ('Det. Mal Fallon', 'Det. Ken Greene', 'Captain Maria Yeong'):
                            self.assertGreater(len(page.name.lines), 1)
                            self.assertGreater(page.name_origin[1] + page.name.ink_bounds[3] * page.name_scale,
                                               page.box.y)
                            wrapped.add(action.details['speaker'])
                        if page.name.glyphs:
                            ink = ui.dialogue_renderer.name_layer.get_bounding_rect()
                            bounds = page.name_bounds
                            # Include actual atlas outlines and pygame rounding,
                            # not just the layout's floating-point rectangles.
                            self.assertGreaterEqual(ink.left, bounds.x - 1)
                            self.assertGreaterEqual(ink.top, bounds.y - 1)
                            self.assertLessEqual(ink.right, bounds.x + bounds.width + 1)
                            self.assertLessEqual(ink.bottom, bounds.y + bounds.height + 1)
                    saved = session.snapshot()
                    restored = Session.from_snapshot(session.resources, saved)
                    self.assertEqual(restored.snapshot(), saved)
                    if action.name == 'choice':
                        answer_screen(session, next(i for i, on in enumerate(action.details['enabled']) if on))
                    else:
                        answer_screen(session)
                self.assertTrue({1, 8, 13, 15, 65} <= seen)
                # The real sequence includes the reported poker scene, its
                # long-name transition, and a later still-longer speaker.
                self.assertTrue({'Diego', 'Det. Mal Fallon', 'Det. Ken Greene',
                                 'Captain Maria Yeong'} <= speakers)
                self.assertEqual(wrapped, {'Det. Mal Fallon', 'Det. Ken Greene', 'Captain Maria Yeong'})
                self.assertTrue(ui.audio, 'SDL dummy audio must initialize')
                for resource in range(8201, 8210):
                    ui.session.engine.music_id = resource
                    ui.session.engine.audio_stopped = False
                    ui._sync_music()
                    self.assertTrue(ui.music_loaded, resource)
                    self.assertTrue(pygame.mixer.music.get_busy(), resource)
            finally:
                app.close()
