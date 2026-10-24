import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp_runtime.content import ContentError, ContentLibrary, digest, import_game
from exp_runtime.menu import MenuFont, MenuState, MenuStrings, default_library, remember_library
from exp_runtime.languages import TITLE_LANGUAGES, episode_title
from exp_runtime.runtime import SaveError
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_vm import program


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra required')
class MenuAnimationTests(unittest.TestCase):
    def test_submenu_tracks_preserve_the_background_and_native_pivots(self):
        import pygame
        from exp_runtime.application import Application
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        pygame.display.init(); pygame.display.set_mode((320, 480))
        self.addCleanup(pygame.quit)
        app = Application.__new__(Application)
        background = pygame.Surface((320, 480)); background.fill((20, 30, 40))
        incoming = pygame.Surface((320, 480), pygame.SRCALPHA)
        outgoing = pygame.Surface((320, 480), pygame.SRCALPHA)
        pygame.draw.rect(incoming, (0, 255, 0), (140, 116, 40, 80))
        pygame.draw.rect(outgoing, (255, 0, 0), (200, 116, 40, 80))
        app.library = SimpleNamespace(kind='apk')
        app.renderer = SimpleNamespace(background=background, layer=incoming)
        app.transition_layer = outgoing
        app.transition_source, app.screen = 'main', 'options'
        app.transition_age, app.transition_direction, app.transition_zoom = 150, 1, True
        def color(canvas, point, expected):
            self.assertTrue(all(abs(a - b) <= 5 for a, b in zip(canvas.get_at(point)[:3], expected)),
                            (point, canvas.get_at(point), expected))
        self.assertEqual(app.transition_duration, 300)
        canvas = app._menu_transition()
        color(canvas, (150, 80), (0, 255, 0))  # .6 scale around (160,16).
        self.assertEqual(canvas.get_at((160, 160))[:3], (20, 30, 40))
        self.assertEqual(canvas.get_at((210, 130))[:3], (20, 30, 40))  # No frozen main layer.
        app.screen = 'help'
        self.assertEqual(app.transition_duration, 400)
        app.transition_age = 200
        color(app._menu_transition(), (160, 80), (0, 255, 0))
        app.transition_source, app.screen, app.transition_age = 'options', 'help', 100
        self.assertEqual(app.transition_duration, 200)
        canvas = app._menu_transition()
        self.assertEqual(canvas.get_at((50, 130))[:3], (255, 0, 0))
        self.assertEqual(canvas.get_at((310, 130))[:3], (0, 255, 0))
        self.assertEqual(canvas.get_at((160, 240))[:3], (20, 30, 40))
        app.transition_source, app.screen, app.transition_age = 'episodes', 'main', 200
        color(app._menu_transition(), (185, 80), (255, 0, 0))
        app.transition_source = 'options'
        self.assertEqual(app._menu_transition().get_at((210, 130))[:3], (255, 0, 0))
        app.library.kind, app.transition_zoom = 'ipa', False
        app.transition_source, app.screen = 'options', 'help'
        self.assertEqual(app.transition_duration, 400)
        self.assertEqual(app._menu_transition().get_at((50, 130))[:3], (255, 0, 0))
        self.assertEqual(background.get_at((160, 80))[:3], (20, 30, 40))

    def test_info_fades_before_the_gear_grows_and_final_layout_is_retained(self):
        import pygame
        from exp_runtime.desktop_menu import MenuRenderer
        from exp_runtime.ui_assets import Rect
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        pygame.display.init(); pygame.display.set_mode((320, 480))
        self.addCleanup(pygame.quit)
        renderer = MenuRenderer.__new__(MenuRenderer)
        renderer.canvas = pygame.Surface((320, 480))
        renderer.bank = SimpleNamespace(rectangle=lambda layout, node: Rect(0, 0, 275, 135)
                                        if layout == 74 else Rect(0, 0, 184, 28))
        renderer.strings = ['Authored'] * 128
        renderer.backdrop = lambda **_: renderer.canvas.fill((0, 0, 0))
        renderer.layout = lambda _, rect: pygame.draw.rect(renderer.canvas, (100, 100, 100),
                                                           (rect.x, rect.y, rect.width, rect.height))
        label = pygame.Surface((4, 4)); label.fill((255, 255, 255))
        renderer.menu_label = lambda *_: label
        def frame(_, index):
            image = pygame.Surface((20, 18) if index == 13 else (42, 41), pygame.SRCALPHA)
            image.fill((255, 128, 0) if index == 13 else (0, 200, 200))
            return image
        renderer.art = SimpleNamespace(frame=frame)
        app = SimpleNamespace(intro=True, menu_age=3000, pressed=None, ready=True, can_resume=lambda: False)
        rectangles = [Rect(20, 355 + i * 21, 160, 20) for i in range(4)]
        def render(age, *, exit_ms=None):
            app.menu_age, renderer.buttons = age, []
            renderer.main(app, exit_ms=exit_ms)
            layer = renderer.canvas
            renderer.canvas = renderer.background.copy()
            renderer.canvas.blit(layer, (0, 0))
            self.assertEqual(app.menu_age, age)
            return pygame.image.tobytes(renderer.canvas, 'RGB')
        with patch('exp_runtime.desktop_menu.main_button_rects', return_value=rectangles):
            render(3000)
            self.assertNotIn(('options',), [command for _, command in renderer.buttons])
            self.assertEqual(tuple(renderer.canvas.get_at((300, 450)))[:3], (0, 0, 0))
            render(3150)
            self.assertLessEqual(abs(renderer.canvas.get_at((300, 450)).g - 100), 1)
            def orange_pixels():
                return sum(renderer.canvas.get_at((x, y)).r > 150 and renderer.canvas.get_at((x, y)).b < 20
                           for x in range(180, 220) for y in range(443, 471))
            render(3300)
            small = orange_pixels()
            self.assertIn(('options',), [command for _, command in renderer.buttons])
            render(3425)
            medium = orange_pixels()
            final = render(3550)
            self.assertLess(small, medium)
            self.assertLess(medium, orange_pixels())
            app.intro = False
            self.assertEqual(render(500), final)
            render(500, exit_ms=0)
            self.assertEqual(orange_pixels(), 0)
            self.assertEqual(renderer.buttons, [])
            render(500, exit_ms=249)
            self.assertEqual(renderer.canvas.get_at((300, 450)).g, 200)
            render(500, exit_ms=250)
            self.assertEqual(tuple(renderer.canvas.get_at((300, 450)))[:3], (0, 0, 0))


class MenuContractTests(unittest.TestCase):
    def test_menu_tracks_retain_the_native_parent_space_and_stagger(self):
        from exp_runtime.menu import main_button_x, main_button_rects
        from exp_runtime.ui_assets import Rect
        bank = SimpleNamespace(rectangle=lambda layout, node: Rect(0, 0, 275, 135)
                               if layout == 74 else Rect(0, 0, 184, 28))
        self.assertEqual([main_button_x(bank, i, 0) for i in range(4)], [-464, -418, -412, -405])
        self.assertEqual([rect.x for rect in main_button_rects(bank)], [14, 40, 26, 13])
        self.assertEqual([main_button_x(bank, i, 1, exiting=True) for i in range(4)], [-366, -366, -366, -352])
        self.assertEqual(main_button_x(bank, 0, .5), -224)
        self.assertEqual(main_button_x(bank, 0, .5, exiting=True), -176)

    def test_title_slots_and_missing_translations(self):
        record = dict(name='Authored.exp', titles=['School', 'École', 'Scuola', 'Schule', 'Escuela'])
        self.assertEqual([episode_title(record, code) for code in TITLE_LANGUAGES], record['titles'])
        for missing in ('', '   '):
            record['titles'][1] = missing
            self.assertEqual(episode_title(record, 'fr'), 'School')
        record['titles'][0] = ''
        self.assertEqual(episode_title(record, 'fr'), 'Authored.exp')
        with self.assertRaises(ValueError):
            episode_title(record, 'unknown')

    def test_ui_strings_are_offsets_and_byte_text_not_exp_metadata(self):
        payload = b'Play\0Caf\xe9\0'
        data = struct.pack('>iBhh2h', 1, 0, 0, 2, 13, 18) + payload
        strings = MenuStrings.parse(data)
        self.assertEqual(strings.strings, ('Play', 'Café'))
        with self.assertRaises(ContentError):
            MenuStrings.parse(data[:-1])
        invalid = bytearray(data)
        struct.pack_into('>h', invalid, 9, 1)
        with self.assertRaises(ContentError):
            MenuStrings.parse(bytes(invalid))

    def test_embedded_glyph_colors_and_spacing_are_read_from_content(self):
        data = struct.pack('>bBbhb', 3, 0, -1, 1, 2) + b'A' + struct.pack('>hhBB', -1, 1, 2, 2)
        data += bytes((128, 10, 20, 30)) * 4
        font = MenuFont.parse(data)
        self.assertEqual((font.space, font.tracking, font.height), (3, -1, 2))
        self.assertEqual(font.glyph('a').pixels, bytes((10, 20, 30, 128)) * 4)
        for bad in (data[:-1], data + b'bad'):
            with self.assertRaises(ContentError):
                MenuFont.parse(bad)

    def test_frozen_default_never_uses_working_directory(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'platform', 'linux'), \
                patch.dict(os.environ, {'XDG_DATA_HOME': '/tmp/shs-test-data'}):
            self.assertEqual(default_library(), Path('/tmp/shs-test-data/SHSHD Runtime/libraries/shs'))

    def test_chosen_library_is_remembered_across_working_directories(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('exp_runtime.launcher.user_data_directory', return_value=Path(directory) / 'preferences'):
            chosen = Path(directory) / 'my-game'
            remember_library(chosen)
            with patch.object(sys, 'frozen', True, create=True):
                self.assertEqual(default_library(), chosen.resolve())
            self.assertEqual(default_library(), chosen.resolve())  # Also overrides a checkout's library.
            self.assertEqual(json.loads((Path(directory) / 'preferences/launcher.json').read_text())['version'], 2)


class LibraryMenuTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        profile.start()
        self.addCleanup(profile.stop)
        self.episode = archive({1: metadata(), 25001: program(0x33).to_bytes()})
        self.apk = self.root / 'input.apk'
        make_apk(self.apk, self.episode)
        self.directory = self.root / 'library'
        import_game(self.apk, [], self.directory)
        self.library = ContentLibrary(self.directory)
        self.addCleanup(self.library.close)

    def test_incremental_import_deduplicates_and_validates_whole_batch(self):
        state = MenuState(self.library)
        session = state.session(state.selected)
        session.advance()
        state.checkpoint(session)
        checkpoint = state.resume_path(state.selected).read_bytes()
        first = self.root / 'first.exp'
        first.write_bytes(archive({1: metadata('Second'), 25001: program(0x33).to_bytes()}))
        second = self.root / 'bad.exp'
        second.write_bytes(b'not an EXP')
        before = (self.directory / 'library.json').read_bytes()
        with self.assertRaises(ContentError):
            self.library.add_episodes([first, second])
        self.assertEqual((self.directory / 'library.json').read_bytes(), before)
        self.assertFalse(list((self.directory / 'content').glob('*.exp')))
        self.assertEqual(self.library.add_episodes([first]), 1)
        self.assertEqual(self.library.add_episodes([first]), 0)
        self.assertEqual(state.resume_path(state.selected).read_bytes(), checkpoint)
        self.assertEqual(self.library.read_asset(42), b'base image')
        with ContentLibrary(self.directory) as reopened:
            self.assertEqual(reopened.open_episode('Second').archive.metadata().title, 'Second')

    def test_checkpoints_preserve_manual_saves_and_resume_survives_reopen(self):
        state = MenuState(self.library)
        session = state.session(state.selected)
        session.advance()
        manual = session.save()
        before = manual.read_bytes()
        session.engine.music_id = 8201
        state.music = False
        state.checkpoint(session)
        automatic = state.save_path(state.selected, automatic=True)
        os.utime(manual, ns=(1, 1))
        self.assertEqual(manual.read_bytes(), before)
        restored = MenuState(self.library)
        self.assertFalse(restored.music)
        self.assertEqual(restored.resume_path(restored.selected), automatic)
        self.assertEqual(restored.session(restored.selected).snapshot(), session.snapshot())
        fresh = restored.session(restored.selected, resume=False)
        self.assertIsNone(fresh.pending)
        self.assertNotEqual(fresh.engine.music_id, session.engine.music_id)

    def test_corrupt_resume_is_reported_without_resetting_progress(self):
        state = MenuState(self.library)
        path = state.save_path(state.selected, automatic=True)
        path.parent.mkdir()
        path.write_text('{ broken')
        with self.assertRaises(SaveError):
            state.session(state.selected)
        self.assertEqual(path.read_text(), '{ broken')
        with self.assertRaises(ContentError):
            state.save_path('../../outside')

    def test_choice_hint_preferences_default_off_and_survive_reopen(self):
        state = MenuState(self.library)
        self.assertFalse(state.choice_hints)
        state.choice_hints = True
        state.persist()
        self.assertTrue(MenuState(self.library).choice_hints)
        data = json.loads(state.path.read_text())
        del data['choice_hints']
        state.path.write_text(json.dumps(data))
        self.assertFalse(MenuState(self.library).choice_hints)
        data['choice_hints'] = 'yes'
        state.path.write_text(json.dumps(data))
        restored = MenuState(self.library)
        self.assertFalse(restored.choice_hints)
        self.assertIn('Invalid player preferences', restored.warning)

    def test_the_hd_backdrop_switch_defaults_on_and_survives_reopen(self):
        state = MenuState(self.library)
        self.assertTrue(state.hd_backdrop)
        state.hd_backdrop = False
        state.persist()
        self.assertFalse(MenuState(self.library).hd_backdrop)
        data = json.loads(state.path.read_text())
        data['hd_backdrop'] = 'no'                      # not a bool: ignored, the default stays
        state.path.write_text(json.dumps(data))
        self.assertTrue(MenuState(self.library).hd_backdrop)

    def test_autoplay_and_the_choice_timer_switch_default_off_and_survive_reopen(self):
        state = MenuState(self.library)
        self.assertEqual((state.autoplay, state.disable_choice_timer), (False, False))
        state.autoplay = state.disable_choice_timer = True
        state.persist()
        restored = MenuState(self.library)
        self.assertEqual((restored.autoplay, restored.disable_choice_timer), (True, True))
        data = json.loads(state.path.read_text())
        data['autoplay'] = 'yes'                                 # not a bool: the whole file is refused, as before
        state.path.write_text(json.dumps(data))
        self.assertIn('Invalid player preferences', MenuState(self.library).warning)

    def test_skip_upsell_intros_defaults_off_and_survives_reopen(self):
        state = MenuState(self.library)
        self.assertFalse(state.skip_upsell_intros)
        state.skip_upsell_intros = True
        state.persist()
        self.assertTrue(MenuState(self.library).skip_upsell_intros)
        data = json.loads(state.path.read_text())
        data['skip_upsell_intros'] = 'yes'                       # not a bool: the whole file is refused
        state.path.write_text(json.dumps(data))
        self.assertIn('Invalid player preferences', MenuState(self.library).warning)

    def test_hires_portraits_default_on_and_survive_reopen(self):
        state = MenuState(self.library)
        self.assertTrue(state.hires_portraits)
        state.hires_portraits = False
        state.persist()
        self.assertFalse(MenuState(self.library).hires_portraits)

    def test_the_vibration_switch_defaults_off_and_survives_reopen(self):
        state = MenuState(self.library)
        self.assertFalse(state.vibration)
        state.vibration = True
        state.persist()
        self.assertTrue(MenuState(self.library).vibration)
        data = json.loads(state.path.read_text())
        data['vibration'] = 1                                   # not a bool: the default
        state.path.write_text(json.dumps(data))
        self.assertFalse(MenuState(self.library).vibration)

    def test_title_preferences_keep_existing_saves_and_scripts_compatible(self):
        state = MenuState(self.library)
        session = state.session(state.selected)
        session.advance()
        manual, automatic = session.save(), state.checkpoint(session)
        original = {path: path.read_bytes() for path in (manual, automatic)}
        snapshot = session.snapshot()
        manifest = (self.directory / 'library.json').read_bytes()
        state.title_language = 'fr'
        state.persist()
        restored = MenuState(self.library)
        self.assertEqual(restored.title(self.library.select(state.selected)), 'École')
        self.assertEqual(restored.session(restored.selected).snapshot(), snapshot)
        self.assertEqual(restored.session(restored.selected, resume=False).vm.program.to_bytes(),
                         session.vm.program.to_bytes())
        self.assertEqual((self.directory / 'library.json').read_bytes(), manifest)
        self.assertEqual({path: path.read_bytes() for path in original}, original)
        # Existing preferences predate this presentation-only field.
        data = json.loads(state.path.read_text())
        del data['title_language']
        state.path.write_text(json.dumps(data))
        self.assertEqual(MenuState(self.library).title_language, 'en')
        data['title_language'] = ['fr']
        state.path.write_text(json.dumps(data))
        invalid = MenuState(self.library)
        self.assertEqual(invalid.title_language, 'en')
        self.assertIn('Invalid player preferences', invalid.warning)

    def test_translated_selectors_and_read_only_cli_title_override(self):
        from exp_runtime.cli import main
        english = self.library.episodes[0]
        self.assertEqual(self.library.select('École')['id'], english['id'])
        state = MenuState(self.library)
        state.title_language = 'fr'
        state.persist()
        preferences = state.path.read_bytes()
        for args, title in (([], 'École'), (['--title-language', 'de'], 'Schule')):
            output = StringIO()
            with patch('sys.stdout', output):
                main(['list', '--library', str(self.directory), *args])
            self.assertIn(title, output.getvalue())
            self.assertEqual(state.path.read_bytes(), preferences)
        other = self.root / 'other.exp'
        other.write_bytes(archive({1: metadata('Another school'), 25001: program(0x33).to_bytes()}))
        self.library.add_episodes([other])
        with self.assertRaisesRegex(ContentError, 'matched 2 episodes'):
            self.library.select('École')
        self.assertEqual(self.library.select(english['id'][:12])['id'], english['id'])


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class ApplicationTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def make_app(self, library=False):
        from exp_runtime.application import Application
        path = self.root / 'library'
        if library:
            source = Path('.shs-library').resolve()
            path.mkdir()
            (path / 'content').mkdir()
            (path / 'library.json').write_bytes((source / 'library.json').read_bytes())
            # Share immutable input bytes, never the user's save directory.
            for item in (source / 'content').iterdir():
                (path / 'content' / item.name).symlink_to(item)
        app = Application(path, audio=False, check_updates=False)
        self.addCleanup(app.close)
        return app

    def test_first_launch_needs_no_assets_and_drop_events_form_one_batch(self):
        import pygame
        app = self.make_app()
        app.render()
        self.assertEqual(app.screen, 'setup')
        app.command(('browse', 'apk'))
        app.tick(200)
        app.render()
        self.assertEqual(app.screen, 'browser')
        with patch.object(app, 'import_paths') as importer:
            app.handle_event(pygame.event.Event(pygame.DROPBEGIN))
            app.handle_event(pygame.event.Event(pygame.DROPFILE, file='/tmp/game.apk'))
            app.tick(16)
            importer.assert_not_called()
            app.handle_event(pygame.event.Event(pygame.DROPFILE, file='/tmp/story.exp'))
            app.handle_event(pygame.event.Event(pygame.DROPCOMPLETE))
            importer.assert_called_once_with([Path('/tmp/game.apk'), Path('/tmp/story.exp')])

    def test_menu_buttons_show_hold_and_cancel_on_drag_focus_and_modal(self):
        import pygame
        app = self.make_app()
        app.render()
        rect = next(r for r, c in app.buttons if c == ('browse', 'apk'))
        point = tuple(v * 1.5 for v in rect.center)
        def pointer(kind, position=point):
            app.handle_event(pygame.event.Event(kind, button=1, pos=position))
            app.render()
        normal = pygame.image.tobytes(app.renderer.canvas, 'RGB')
        pointer(pygame.MOUSEBUTTONDOWN)
        self.assertEqual(app.screen, 'setup')
        self.assertEqual(app.pressed, ('browse', 'apk'))
        self.assertNotEqual(pygame.image.tobytes(app.renderer.canvas, 'RGB'), normal)
        pointer(pygame.MOUSEMOTION, (-1, -1))
        self.assertIsNone(app.pressed)
        self.assertEqual(pygame.image.tobytes(app.renderer.canvas, 'RGB'), normal)
        pointer(pygame.MOUSEBUTTONUP, (-1, -1))
        self.assertEqual(app.screen, 'setup')
        pointer(pygame.MOUSEBUTTONDOWN)
        app.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        app.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
        pointer(pygame.MOUSEBUTTONUP)
        self.assertEqual(app.screen, 'setup')
        pointer(pygame.MOUSEBUTTONDOWN)
        app.message = 'Authored alert'
        app.render()
        pointer(pygame.MOUSEBUTTONUP, (240, 553))
        self.assertEqual(app.message, 'Authored alert')
        pointer(pygame.MOUSEBUTTONDOWN, (240, 553))
        self.assertEqual(app.pressed, ('dismiss',))
        pointer(pygame.MOUSEBUTTONUP, (240, 553))
        self.assertEqual(app.message, '')


    def test_episode_browser_lists_zips_and_selection_uses_shared_importer(self):
        app = self.make_app()
        episode_zip = (self.root / 'episodes.ZIP').resolve()
        episode_zip.touch()
        (self.root / 'notes.txt').touch()
        app.folder = self.root
        app.browse('episodes')
        self.assertIn(episode_zip, app.files)
        self.assertNotIn((self.root / 'notes.txt').resolve(), app.files)
        with patch.object(app, 'import_paths') as importer:
            app.command(('file', episode_zip))
            importer.assert_called_once_with([episode_zip])

    def test_about_displays_runtime_version_and_opens_project_only_on_request(self):
        from exp_runtime.app_info import PROJECT_URL
        from unittest.mock import Mock
        app = self.make_app()
        opener = Mock()
        app.url_opener = opener
        app.screen = 'help'
        with patch('exp_runtime.desktop_menu.runtime_version', return_value='9.8.7'), \
                patch.object(app.renderer, 'label', wraps=app.renderer.label) as label:
            app.render()
            self.assertIn('SHSHD Runtime v9.8.7', [call.args[0] for call in label.call_args_list])
        self.assertIn(('project',), [command for _, command in app.buttons])
        opener.assert_not_called()
        app.command(('project',))
        opener.assert_called_once_with(PROJECT_URL)
        app.url_opener = None
        with patch('webbrowser.open', return_value=True) as browser:
            app.command(('project',))
            browser.assert_called_once_with(PROJECT_URL)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content is unavailable')
    def test_main_menu_navigation_resizing_pause_and_live_resume(self):
        import pygame
        app = self.make_app(library=True)
        self.assertEqual(app.message, '')
        app.tick(2400)
        app.render()
        self.assertFalse(app.buttons)  # Entrance input gate.
        app.tick(1150)
        app.window = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
        app.render()
        self.assertEqual(len(app.buttons), 6)
        self.assertEqual(app.buttons[3][1], ('switch_games',))
        self.assertTrue(all(app.renderer.menu_fonts[1].glyph(c) for c in 'SwitchGame'))
        rect, command = app.buttons[0]
        point = (app.viewport.x + rect.centerx * app.viewport.width / 320,
                 app.viewport.y + rect.centery * app.viewport.height / 480)
        app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
        self.assertEqual(app.screen, 'main')
        app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=point))
        self.assertEqual(app.screen, 'episodes')
        app.tick(200)
        app.render()
        self.assertFalse(app.buttons)  # Submenu entry has not settled yet.
        app.tick(200)
        app.render()
        self.assertTrue(app.buttons)
        self.assertEqual(app.main_exit_ms, 400)  # Main rows continue behind the incoming panel.
        app.command(('episode', app.library.select('The_New_Girl.exp')['id']))
        app.command(('start', True))
        app.render()
        self.assertIsNone(app.game.error)
        self.assertEqual(app.game.window.get_size(), (800, 600))
        before = app.game.session.snapshot()
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        app.tick(5000)
        self.assertEqual(app.game.session.snapshot(), before)
        app.game.command(('main_menu',))
        self.assertEqual(app.screen, 'main')
        app.tick(5000)
        self.assertEqual(app.game.session.snapshot(), before)
        automatic = app.state.resume_path(app.selected)
        self.assertTrue(automatic.is_file())
        app.command(('start', True))
        self.assertEqual(app.game.session.snapshot(), before)
        app.return_to_menu()
        for screen in ('options', 'help', 'library'):
            app.show(screen)
            app.tick(1550)
            app.render()
        app.command(('toggle', 'sound'))
        self.assertFalse(MenuState(app.library).sound)
        app.browse('episodes')
        app.tick(200)
        app.render()

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content is unavailable')
    def test_long_episode_list_search_and_hit_testing(self):
        import pygame
        app = self.make_app(library=True)
        source = app.library.episodes[0]
        # Authored list entries suffice for scrolling; no story data are copied.
        app.library.episodes = [dict(source, id=f'{i:064x}', titles=[f'Episode {i:02}', '', '', '', '']) for i in range(30)]
        app.show('episodes')
        app.scope = 'all'
        app.tick(1550)
        app.command(('episode_groups',))
        app.tick(200)
        app.render()
        app.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-20))
        app.render()
        rows = [command for _, command in app.buttons if command[0] == 'episode']
        self.assertEqual(rows[0], ('episode', f'{16:064x}'))
        app.command(('search',))
        app.handle_event(pygame.event.Event(pygame.TEXTINPUT, text='Episode 29'))
        app.render()
        rows = [command for _, command in app.buttons if command[0] == 'episode']
        self.assertEqual(rows, [('episode', f'{29:064x}')])

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content is unavailable')
    def test_added_episode_appears_in_play_before_and_after_restarting(self):
        from exp_runtime.application import Application
        app = self.make_app(library=True)
        episode = self.root / 'added.exp'
        episode.write_bytes(archive({1: metadata('An imported story'), 25001: program(0x33).to_bytes()}))
        self.assertEqual(app.library.add_episodes([episode]), 1)
        key = digest(episode.read_bytes())
        app.scope = 'play'
        self.assertIn(key, [e['id'] for e in app.visible_episodes()])
        self.assertNotIn(key, app.saved)  # A save is not required for visibility.
        reopened = Application(app.directory, audio=False, check_updates=False)
        self.addCleanup(reopened.close)
        reopened.scope = 'play'
        self.assertIn(key, [e['id'] for e in reopened.visible_episodes()])
        self.assertNotIn(key, reopened.saved)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content is unavailable')
    def test_episode_order_uses_numeric_pack_and_episode_ids(self):
        app = self.make_app(library=True)
        source = app.library.episodes[0]
        rows = [(2, 1, 'Z'), (1, 10, 'A'), (1, 2, 'B')]
        app.library.episodes = [dict(source, id=f'{i:064x}', pack_id=pack, episode_id=episode,
                                     titles=[title, '', '', '', '']) for i, (pack, episode, title) in enumerate(rows)]
        self.assertEqual([e['titles'][0] for e in app.visible_episodes()], ['B', 'A', 'Z'])
        app.command(('order',))
        self.assertEqual([e['titles'][0] for e in app.visible_episodes()], ['A', 'B', 'Z'])
        self.assertEqual(MenuState(app.library).order, 'title')

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content is unavailable')
    def test_only_the_mega_packs_header_is_orange_the_rest_are_blue(self):
        # Native header art (`MenuRenderer.art.frame`, sampled straight from the APK, not eyeballed) has both a
        # blue strip (pack 16 frame 73) and an orange one (frame 76) -- but the draw code always blitted frame 76,
        # so every category showed orange. The owner's own iPad SD screenshots confirm only "Mega Packs" is orange
        # and every other category is blue; `episode_group` rows now pick the strip by comparing the section's
        # title against the Mega Packs string (82) the same way `desktop_episode_list_hd.py`'s own list already
        # does.
        app = self.make_app(library=True)
        source = app.library.episodes[0]
        # `name` is overridden too: a source record the real catalog recognizes (e.g. the bundled novel bonus
        # story) would otherwise categorize these by filename regardless of the pack/episode ids below.
        mega = dict(source, id='f' * 64, pack_id=999901, episode_id=1, titles=['Bundled', '', '', '', ''],
                    name='zzz_fake_bundled_test.exp', apk_member='fake_bundled.exp')
        other = {k: v for k, v in source.items() if k != 'apk_member'}
        other = dict(other, id='e' * 64, pack_id=999902, episode_id=1, titles=['Imported', '', '', '', ''],
                     name='zzz_fake_imported_test.exp', builtin=None)
        app.library.episodes = [mega, other]
        app.show('episodes')
        app.scope = 'all'
        app.render()
        sections_by_key = {section.key: section.title for section in app.episode_sections()}
        self.assertIn(app.renderer.strings[82], sections_by_key.values())   # sanity: "mega" resolved to Mega Packs
        colors = {sections_by_key[command[1]]: app.renderer.canvas.get_at(rect.center)[:3]
                  for rect, command in app.renderer.buttons if command[0] == 'episode_group'}
        self.assertEqual(tuple(colors[app.renderer.strings[82]]), (213, 138, 58))       # orange, Mega Packs only
        other_title = next(title for title in colors if title != app.renderer.strings[82])
        self.assertEqual(tuple(colors[other_title]), (41, 104, 221))                    # blue, every other group

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content is unavailable')
    def test_language_choices_localize_titles_search_and_sort_preserving_live_game(self):
        import pygame
        app = self.make_app(library=True)
        record = next(e for e in app.library.episodes if e['titles'][1] != e['titles'][0])
        app.selected = record['id']
        app.start(resume=False)
        self.assertIsNone(app.game.error)
        app.return_to_menu()
        game, snapshot = app.game, app.game.session.snapshot()
        checkpoint = app.state.resume_path(record['id'])
        saved = checkpoint.read_bytes()
        app.show('options')
        app.tick(1550)
        app.render()
        self.assertIn(('title_languages',), [command for _, command in app.buttons])
        app.command(('title_languages',))
        app.tick(200)
        app.render()
        self.assertEqual({command[1] for _, command in app.buttons if command[0] == 'title_language'},
                         set(TITLE_LANGUAGES))
        app.command(('title_language', 'fr'))
        self.assertEqual(MenuState(app.library).title_language, 'fr')
        self.assertEqual(app.state.title(record), record['titles'][1])
        self.assertEqual(game.session.snapshot(), snapshot)
        self.assertEqual(checkpoint.read_bytes(), saved)
        app.query = record['titles'][1]
        self.assertIn(record, app.visible_episodes())
        app.query = record['titles'][0]
        self.assertIn(record, app.visible_episodes())
        app.query = ''
        app.state.order = 'title'
        titles = [app.state.title(e).casefold() for e in app.visible_episodes()]
        self.assertEqual(titles, sorted(titles))
        app.start()
        self.assertIs(app.game, game)
        self.assertEqual(game.episode_title, record['titles'][1])
        self.assertIn(record['titles'][1], pygame.display.get_caption()[0])
        self.assertEqual(game.session.snapshot(), snapshot)


if __name__ == '__main__':
    unittest.main()
