import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from exp_runtime.runtime import Session
from test_runtime import Resources, answer_screen, branching_program


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class DesktopTests(unittest.TestCase):
    def test_continue_tab_tracks_box_theme_and_reveal_without_drawing_side_effects(self):
        from unittest.mock import Mock, patch
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.dialogue_animation import DialogueAnimation
        from exp_runtime.ui_assets import Rect
        import pygame
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        pygame.display.init(); pygame.display.set_mode((320, 480))
        self.addCleanup(pygame.quit)
        text = Mock()
        text.font.return_value = SimpleNamespace(cap_height=10)
        text.layout.return_value = SimpleNamespace(ink_bounds=(0, 0, 50, 10))
        renderer = DialogueRenderer(None, text, None)
        def frame(asset, index):
            self.assertEqual(asset, 126)
            tab = pygame.Surface((99, 17), pygame.SRCALPHA)
            tab.fill((index * 20, 100, 150, 255))
            return tab
        renderer.frame = frame
        motion = DialogueAnimation(10)
        with patch('exp_runtime.desktop_dialogue.MenuStrings.load', return_value={29: 'Continue'}):
            for theme, index in ((1, 5), (2, 3), (3, 6), (-1, 4)):
                for box in (Rect(13, 55, 294, 68), Rect(25, 115, 130, 40)):
                    renderer.canvas.fill((0, 0, 0))
                    renderer.draw_continue(box, theme, motion)
                    self.assertEqual(tuple(renderer.canvas.get_at((box.x + box.width - 50, box.y + box.height))[:3]), (0, 0, 0))
                    motion.settle()
                    renderer.draw_continue(box, theme, motion)
                    self.assertEqual(tuple(renderer.canvas.get_at((box.x + box.width - 50, box.y + box.height + 8))[:3]),
                                     (index * 20, 100, 150))
                    self.assertEqual(tuple(renderer.canvas.get_at((box.x + box.width, box.y + box.height + 8))[:3]), (0, 0, 0))
                    self.assertEqual(motion.continue_ms, 250)
                    motion.next_page(10)
            self.assertEqual(text.draw_layout.call_count, 4)
            self.assertTrue(all(call.args[1] == 'TrebuchetMS_Bold14' for call in text.draw_layout.call_args_list))

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user library is not present')
    def test_dialogue_motion_renders_between_states_and_pauses_without_advancing_vm(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as library:
            resources = library.open_episode('The_New_Girl.exp')
            ui = Desktop(Session(resources), audio=False)
            for _ in range(100):
                if (ui.session.pending.name == 'dialogue'
                        and ui.session.engine.dialogue_animation.portrait is not None):
                    break
                answer_screen(ui.session)
            else:
                self.fail('Expected a portrait in the opening scene')
            session = ui.session
            before_vm = session.vm.snapshot()
            ui.tick(250)
            frames = set()
            for _ in range(19):
                ui.render()
                self.assertIsNone(ui.error)
                frames.add(pygame.image.tobytes(ui.canvas, 'RGB'))
                ui.tick(16)
            self.assertGreaterEqual(len(frames), 15)
            self.assertEqual(session.vm.snapshot(), before_vm)
            saved = session.snapshot()
            ui.render()
            pixels = pygame.image.tobytes(ui.canvas, 'RGB')
            self.assertEqual(session.snapshot(), saved)  # Drawing never advances clocks.
            ui.session = Session.from_snapshot(resources, saved)
            ui.render()
            self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGB'), pixels)
            ui.command(('menu',)); ui.tick(2000)
            self.assertEqual(ui.session.snapshot(), saved)
            ui.command(('resume',))
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST)); ui.tick(2000)
            self.assertEqual(ui.session.snapshot(), saved)
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            ui.render()
            token = ui._screen_token()
            for _ in range(2):
                ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
            self.assertNotEqual(ui._screen_token(), token)
            self.assertEqual(ui.session.vm.snapshot(), before_vm)
            ui.tick(1000)
            ui.render()
            self.assertIsNone(ui.error)
            self.assertNotEqual(pygame.image.tobytes(ui.canvas, 'RGB'), pixels)
            self.assertTrue(ui.session.engine.dialogue_animation.complete)
            self.assertEqual(ui.session.vm.snapshot(), before_vm)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user library is not present')
    def test_minigame_input_pause_and_original_art(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        from test_football import resources as football_resources, start_play
        from test_word_grid import resources as grid_resources, play_phase
        from test_minigames import word_resources
        import pygame

        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as library:
            r = library.open_episode('The_New_Girl.exp')
            for fixture in (word_resources(), grid_resources(tutorial=True), football_resources(100)):
                r.programs[25001] = fixture.program(25001)
                ui = Desktop(Session(r), audio=False)
                s = ui.session
                if s.engine.word_grid:
                    play_phase(s)
                elif s.engine.football:
                    start_play(s)
                    for _ in range(5): ui.tick(250)
                else:
                    ui.tick(400)
                ui.window = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
                ui.render(); self.assertIsNone(ui.error)
                saved = s.snapshot()
                ui.command(('menu',)); ui.tick(1000)
                self.assertEqual(s.snapshot(), saved)
                ui.command(('resume',))
                ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST)); ui.tick(1000)
                self.assertEqual(s.snapshot(), saved)
                ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))

                def pointer(kind, point):
                    x, y = point
                    pos = (ui.viewport.x + x * ui.viewport.width / 320,
                           ui.viewport.y + y * ui.viewport.height / 480)
                    ui.handle_event(pygame.event.Event(kind, button=1, pos=pos))

                if s.engine.word_grid:
                    for kind, index in [(pygame.MOUSEBUTTONDOWN, 0), (pygame.MOUSEMOTION, 1),
                                        (pygame.MOUSEMOTION, 2)]:
                        pointer(kind, ui.grid_renderer.cells[index][1].center)
                    self.assertEqual(s.engine.word_grid.score, 100)
                    pointer(pygame.MOUSEBUTTONUP, (0, 0))
                elif s.engine.football:
                    game = s.engine.football
                    self.assertTrue(game.targets[0].visible)
                    pointer(pygame.MOUSEBUTTONDOWN, (60, 200))
                    self.assertEqual(game.phase, 4)
                    self.assertEqual(game.down, 1)
                else:
                    page = ui.choice_renderer.page(s)
                    row = page.rows[s.engine.word_game.weights.index(1)]
                    pointer(pygame.MOUSEBUTTONDOWN, row.rect.center)
                    self.assertEqual(s.engine.word_game.score, 0)
                    pointer(pygame.MOUSEBUTTONUP, row.rect.center)
                    self.assertEqual(s.engine.word_game.score, 1)
                ui.render(); self.assertIsNone(ui.error)

    def test_masked_portraits_blend_on_opaque_cocoa_surface(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Raster
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((4, 1))
        # Transparent white, real black artwork, a translucent edge, and a
        # colored pixel that the portrait mask turns into transparent black.
        pixels = bytes((255, 255, 255, 0, 0, 0, 0, 255,
                        50, 80, 110, 128, 90, 200, 15, 255))
        source = pygame.image.frombytes(pixels + b'\0' * (4 * 12 * 4), (4, 13), 'RGBA')
        renderer = DialogueRenderer(None, None, lambda _: source)
        renderer.pack = lambda _: SimpleNamespace(images=(Raster(4, 13, b'\0\0\0\xff' + b'\0' * 48, 'A'),))
        expected = [(120, 150, 180), (0, 0, 0), (85, 115, 145), (120, 150, 180)]
        for alpha_mask in (0, 0xff000000):
            for flipped in (False, True):
                with self.subTest(alpha_mask=alpha_mask, flipped=flipped):
                    # Cocoa's opaque canvas retains an alpha bitmask with
                    # zero alpha bytes, despite not having the SRCALPHA flag.
                    target = pygame.Surface((4, 1), 0, 32,
                                            (0xff0000, 0xff00, 0xff, alpha_mask))
                    target.fill((120, 150, 180, 0))
                    target.blit(renderer.portrait(1, flipped), (0, 0))
                    self.assertEqual([tuple(target.get_at((x, 0))[:3]) for x in range(4)],
                                     expected[::-1] if flipped else expected)

    def test_larger_portraits_are_normalized_before_masking_and_flipping(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Raster
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init(); pygame.display.set_mode((8, 2))
        pixels = bytes((20, 40, 60, 255, 80, 100, 120, 255,
                        140, 160, 180, 255, 200, 220, 240, 255))
        logical = pygame.image.frombytes(pixels + b'\0' * (4 * 12 * 4), (4, 13), 'RGBA')
        source = pygame.transform.scale(logical, (8, 26))
        before = pygame.image.tobytes(source, 'RGBA')
        renderer = DialogueRenderer(None, None, lambda _: source)
        renderer.pack = lambda _: SimpleNamespace(images=(Raster(4, 15, b'\xff' * 8 + b'\0\0\1\0' + b'\xff' * 48, 'A'),))
        expected = [pixels[i:i + 4] for i in range(0, 16, 4)]
        expected[2] = b'\0' * 4
        for flipped in (False, True):
            image = renderer.portrait(1, flipped)
            self.assertEqual(image.get_size(), (4, 1))
            self.assertEqual(pygame.image.tobytes(image, 'RGBA'),
                             b''.join(expected[::-1] if flipped else expected))
        self.assertEqual(pygame.image.tobytes(source, 'RGBA'), before)
        self.assertEqual(source.get_size(), (8, 26))

    def test_portrait_art_reaches_circle_bottom_after_native_crop(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.desktop_picker import CharacterPickerRenderer
        from exp_runtime.dialogue_animation import DialoguePortrait
        from exp_runtime.ui_assets import Raster
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init(); pygame.display.set_mode((20, 20))
        for height in (8, 9):
            source = pygame.Surface((6, height + 12), pygame.SRCALPHA)
            source.fill((240, 0, 0, 255))
            source.fill((0, 200, 0, 255), (0, 0, 3, height))
            source.fill((0, 0, 200, 255), (3, 0, 3, height))
            before = pygame.image.tobytes(source, 'RGBA')
            art = DialogueRenderer(None, None, lambda _: source)
            # Only the first portrait rows survive the mask. The trailing
            # twelve must be removed before aligning to the circle.
            mask = Raster(6, height + 14, b'\xff' * 12 + b'\0' * (6 * height) + b'\xff' * 72, 'A')
            art.pack = lambda _: SimpleNamespace(images=(mask,))
            art.frame = lambda *_: pygame.Surface((14, height + 2), pygame.SRCALPHA)
            picker = CharacterPickerRenderer(None, None, art)
            for theme in (1, 2, 3):
                for mode in (1, 2):
                    with self.subTest(height=height, theme=theme, mode=mode):
                        portrait = DialoguePortrait(1, 1, mode, theme)
                        layer, origin = art.portrait_group(portrait)
                        self.assertEqual(origin, (-7, -5))
                        # Both odd and even heights reach the ring's bottom
                        # row, leaving two clear rows above the character.
                        self.assertEqual(layer.get_bounding_rect(), pygame.Rect(4, 2, 6, height))
                        flipped = mode == 2 and theme != 3
                        self.assertEqual(tuple(layer.get_at((4, height + 1))),
                                         (0, 0, 200, 255) if flipped else (0, 200, 0, 255))
                layer, origin = picker.portrait(1, theme)
                self.assertEqual(origin, (-7, -5))
                self.assertEqual(layer.get_bounding_rect(), pygame.Rect(4, 2, 6, height))
            self.assertEqual(pygame.image.tobytes(source, 'RGBA'), before)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user library is not present')
    def test_imported_new_girl_portraits_render_through_opening_and_save_restore(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as library:
            selector = 'SHS_The_New_Girl.exp'
            if selector not in {entry['name'] for entry in library.episodes}:
                self.skipTest('imported New Girl is not present')
            resources = library.open_episode(selector)
            ui = Desktop(Session(resources), audio=False)
            for _ in range(200):
                action = ui.session.pending
                if action.name == 'dialogue':
                    ui.session.tick(2000)  # Make the portrait entrance visible.
                before = ui.session.snapshot()
                ui.render()
                self.assertIsNone(ui.error, (ui.session.scene, action.request.pc))
                self.assertEqual(ui.session.vm.snapshot(), before['vm'])
                self.assertEqual(ui.session.snapshot()['engine'], before['engine'])
                if action.name == 'word_game':
                    break
                if action.name == 'choice':
                    answer_screen(ui.session, next(i for i, enabled in enumerate(action.details['enabled']) if enabled))
                elif action.name == 'text_input':
                    ui.session.answer('Alex')
                elif action.name == 'character_picker':
                    ui.session.answer(0); ui.session.tick(25); ui.session.answer()
                else:
                    self.assertIn(action.name, ('dialogue', 'presentation', 'vm_pause'))
                    answer_screen(ui.session)
            self.assertEqual(ui.session.pending.name, 'word_game')
            self.assertEqual(ui._image(26021).get_size(), (256, 256))
            self.assertEqual(ui.dialogue_renderer.portrait(26021, True).get_size(), (128, 116))
            self.assertEqual(ui.dialogue_renderer.portrait(26005, False).get_size(), (113, 116))
            saved = ui.session.snapshot()
            pixels = pygame.image.tobytes(ui.canvas, 'RGB')
            ui.session = Session.from_snapshot(resources, saved)
            ui.render(); self.assertIsNone(ui.error)
            self.assertEqual(ui.session.snapshot(), saved)
            self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGB'), pixels)

    def test_window_input_save_load_and_resized_mouse_coordinates(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            ui = Desktop(Session(resources), audio=False)
            ui.session.tick(250)
            ui.render()
            saved = ui.session.snapshot()
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            self.assertEqual(ui.session.snapshot(), saved)  # Enter cannot invent a choice.
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F5))
            self.assertTrue(ui.session.save_path.exists())
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
            self.assertEqual(ui.session.pending.details['text'], 'Went right.')
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F9))
            self.assertEqual(ui.session.snapshot(), saved)
            ui.window = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
            ui.render()
            rect = next(rect for rect, command in ui.buttons if command == ('choose', 0))
            x = ui.viewport.x + rect.centerx * ui.viewport.width / 480
            y = ui.viewport.y + rect.centery * ui.viewport.height / 720
            ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y)))
            self.assertEqual(ui.session.snapshot(), saved)
            ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(x, y)))
            self.assertEqual(ui.session.pending.details['text'], 'Went left.')
            self.assertIsNone(ui.error)
            self.assertFalse(ui.handle_event(pygame.event.Event(pygame.QUIT)))

    def test_choice_finger_down_during_attachment_cannot_select_after_it(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        from test_choice import timed_resources
        self.addCleanup(pygame.quit)
        ui = Desktop(Session(timed_resources()), audio=False)
        ui.viewport = pygame.Rect(0, 0, 480, 720)
        ui.buttons = [(pygame.Rect(20, 20, 100, 50), ('choose', 0))]
        original = ui.session.pending
        ui.tick(249)
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(40, 40)))
        self.assertIsNone(ui.press.origin)
        ui.tick(1)
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(40, 40)))
        self.assertIs(ui.session.pending, original)
        self.assertEqual(ui.session.engine.sound_serial, 0)
        for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            ui.handle_event(pygame.event.Event(kind, button=1, pos=(40, 40)))
        self.assertEqual(ui.session.pending.request.args, (0,))

    def test_held_choice_cancels_on_drag_and_deal_change(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        from test_minigames import word_resources
        self.addCleanup(pygame.quit)
        ui = Desktop(Session(word_resources()), audio=False)
        ui.tick(400)
        # Authored host buttons exercise the production input path without art.
        ui.viewport = pygame.Rect(0, 0, 480, 720)
        ui.buttons = [(pygame.Rect(20, 20, 100, 50), ('choose', 0)),
                      (pygame.Rect(20, 80, 100, 50), ('choose', 1))]
        def pointer(kind, pos=(40, 40)):
            ui.handle_event(pygame.event.Event(kind, button=1, pos=pos))
        before = ui.session.snapshot()
        pointer(pygame.MOUSEBUTTONDOWN)
        self.assertEqual(ui.press.pressed, ('choose', 0))
        self.assertEqual(ui.session.snapshot(), before)
        pointer(pygame.MOUSEMOTION, (40, 100))
        self.assertIsNone(ui.press.pressed)
        pointer(pygame.MOUSEBUTTONUP, (40, 100))
        self.assertEqual(ui.session.snapshot(), before)
        pointer(pygame.MOUSEBUTTONDOWN)
        pointer(pygame.MOUSEMOTION, (-1, -1))
        pointer(pygame.MOUSEMOTION)
        self.assertEqual(ui.press.pressed, ('choose', 0))
        pointer(pygame.MOUSEBUTTONUP)
        self.assertEqual(ui.session.engine.word_game.round, before['engine']['word_game']['round'] + 1)
        pointer(pygame.MOUSEBUTTONDOWN)
        ui.session.answer(0)  # Another input/round invalidates the old finger.
        changed = ui.session.snapshot()
        pointer(pygame.MOUSEBUTTONUP)
        self.assertEqual(ui.session.snapshot(), changed)
        pointer(pygame.MOUSEBUTTONDOWN)
        ui.cancel_pointer()
        pointer(pygame.MOUSEBUTTONUP)
        self.assertEqual(ui.session.snapshot(), changed)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user library is not present')
    def test_original_dialogue_fonts_on_opening_and_saved_choice_branches(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as library:
            resources = library.open_episode('The_New_Girl.exp')
            ui = Desktop(Session(resources), audio=False)
            screens = 0
            while ui.session.pending.name in ('presentation', 'dialogue') and screens < 100:
                ui.render()
                self.assertIsNone(ui.error)
                answer_screen(ui.session)
                screens += 1
            self.assertEqual(screens, 35)
            self.assertEqual(ui.session.pending.name, 'choice')
            saved = ui.session.snapshot()
            for choice in (0, 1):
                ui.session = Session.from_snapshot(resources, saved)
                answer_screen(ui.session, choice)
                ui.render()
                self.assertIsNone(ui.error)
                self.assertEqual(ui.session.pending.name, 'dialogue')
            self.assertIn('ArialRoundedMTBold16', ui.story_text.fonts)
            self.assertIn('TrebuchetMS_Italic16', ui.story_text.fonts)
            self.assertTrue(any(name.startswith('PajamaHip') for name in ui.story_text.fonts))
