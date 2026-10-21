import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest

from exp_runtime.character_picker import CharacterPicker, POSITIONS
from exp_runtime.content import ContentLibrary
from exp_runtime.runtime import SaveError, Session
from exp_runtime.vm import VMError
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def picker_resources(count=5, address=None):
    words, (text,) = text_words('Choose your look!')
    array = len(words)
    words += [7, 29, 101, 300, 12]
    return Resources(program(*host_call(78, text, count, array if address is None else address),
                             0x21, (0x1f, 0xfe01), words=words))


class CharacterPickerTests(unittest.TestCase):
    def test_selection_confirmation_and_original_index_result(self):
        for index in range(5):
            s = Session(picker_resources())
            action = s.advance()
            request = s.vm.pending
            self.assertEqual(action.name, 'character_picker')
            self.assertEqual(s.engine.character_picker.selected, 0)
            self.assertIs(s.answer(index), action)
            self.assertIs(s.vm.pending, request)
            self.assertIsNone(s.engine.result_cells[0])
            self.assertEqual(s.answer().request.args, (index,))
            self.assertEqual(s.engine.result_cells[0], index)
            self.assertIsNone(s.engine.character_picker)
        s = Session(picker_resources())
        s.advance()
        self.assertEqual(s.answer().request.args, (0,))  # Initial portrait is selected.

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_left_and_right_bring_the_previous_or_next_portrait_to_the_front(self):
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        from exp_runtime.desktop import Desktop
        import pygame
        self.addCleanup(pygame.quit)
        s = Session(picker_resources(count=3))
        s.advance()
        ui = Desktop(s, audio=False)
        ui.viewport = pygame.Rect(0, 0, 480, 720)
        press = lambda key: ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=''))
        press(pygame.K_RIGHT)
        self.assertEqual(s.engine.character_picker.selected, 1)
        press(pygame.K_LEFT)                                          # mid-swap: waits (CharacterPicker.moving)
        self.assertEqual(s.engine.character_picker.selected, 1)
        press(pygame.K_3)
        self.assertEqual(s.engine.character_picker.selected, 1)
        s.engine.character_picker.tick(50)
        press(pygame.K_LEFT)
        s.engine.character_picker.tick(50)
        press(pygame.K_LEFT)
        self.assertEqual(s.engine.character_picker.selected, 2)     # wraps round
        press(pygame.K_RETURN)
        self.assertEqual(s.engine.result_cells[0], 2)

    def test_each_game_plays_its_own_swap_and_confirm_sounds(self):
        for game, sounds in (('shs', (8013, 8010)), ('cod', (8005, 8005))):
            with self.subTest(game=game):
                r = picker_resources(); r.library.game_id = game
                s = Session(r); s.advance()
                s.answer(0)                                   # the front portrait: no swap, no sound
                self.assertEqual(s.engine.sound_serial, 0)
                s.answer(2)
                swap = s.engine.sound_id
                s.answer()
                self.assertEqual((swap, s.engine.sound_id), sounds)

    def test_swaps_keep_identity_and_fixed_hits_with_elapsed_animation(self):
        picker = CharacterPicker.start([7, 29, 101, 300, 12])
        picker.select(3)
        self.assertEqual(picker.order, [3, 1, 2, 0, 4])
        self.assertEqual(picker.hit(POSITIONS[0]), 3)
        self.assertEqual(picker.hit(POSITIONS[3]), 0)
        self.assertIsNone(picker.hit((0, 0)))
        picker.tick(25)
        x, y, scale = picker.portraits[3].pose
        self.assertEqual((x, y), (183.0, 222.5))
        self.assertAlmostEqual(scale, .8)
        picker.tick(25)
        self.assertEqual(picker.portraits[3].pose, (160.0, 275.0, 1.0))
        picker.select(4)
        self.assertEqual(picker.order, [4, 1, 2, 0, 3])
        picker.tick(1000)
        picker.validate()

    def test_save_during_motion_and_upgrade_old_unhandled_frame(self):
        r = picker_resources()
        s = Session(r); s.advance(); s.answer(4); s.tick(17)
        saved = json.loads(json.dumps(s.snapshot()))
        restored = Session.from_snapshot(r, saved)
        self.assertEqual(json.loads(json.dumps(restored.snapshot())), saved)
        s.tick(33); restored.tick(33)
        self.assertEqual(s.snapshot(), restored.snapshot())
        self.assertEqual(restored.answer().request.args, (4,))
        for version in (3, 4):
            old = copy.deepcopy(saved)
            old['version'] = version
            old['engine'].pop('character_picker')
            old['engine'].pop('scene_badge')
            old['engine'].pop('next_dialogue_wobble')
            old['pending'] = dict(name='unhandled_yield', details={})
            if version == 3:
                old['engine'].pop('dialogue_animation')
            upgraded = Session.from_snapshot(r, old)
            self.assertEqual(upgraded.pending.name, 'character_picker')
            self.assertEqual(upgraded.vm.snapshot(), s.vm.snapshot())
            self.assertEqual(upgraded.answer().request.args, (0,))

    def test_bad_frames_inputs_and_saved_state_are_rejected(self):
        for count, address in ((0, None), (6, None), (5, -1), (5, 32767)):
            s = Session(picker_resources(count, address))
            with self.assertRaises(VMError):
                s.advance()
            self.assertEqual(s.vm.pending.yield_id, 78)
        r = picker_resources(); s = Session(r); s.advance()
        saved = s.snapshot()
        for value in (-1, 5, True, '3'):
            with self.assertRaises(ValueError):
                s.answer(value)
            self.assertEqual(s.snapshot(), saved)
        for key, value in (('characters', [0] * 5), ('order', [0] * 5), ('portraits', [])):
            invalid = copy.deepcopy(saved)
            invalid['engine']['character_picker'][key] = value
            with self.assertRaises(SaveError):
                Session.from_snapshot(r, invalid)


class CodPickerRendererTests(unittest.TestCase):
    def test_box_title_check_button_and_hint(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from types import SimpleNamespace
        from exp_runtime.desktop_picker import CodCharacterPickerRenderer
        pygame.init()
        self.addCleanup(pygame.quit)
        pygame.display.set_mode((8, 8))
        r = picker_resources(); r.library.game_id = 'cod'
        s = Session(r); s.advance()

        def solid(colour, size):
            image = pygame.Surface(size, pygame.SRCALPHA); image.fill(colour)
            return image
        boxes, titles = [], []
        art = SimpleNamespace(
            game_id=lambda: 'cod', cod_hd_common=lambda: object(), image=lambda asset: None,
            background_origin=lambda *_: (160, 180),
            box=lambda canvas, rect, theme, alpha=255, scale=1: boxes.append(((rect.x, rect.y, rect.width, rect.height), alpha, scale)),
            frame_scaled=lambda pack, frame, k: solid((frame, 0, 0, 255), (20 * k, 20 * k)),
            hd_portrait=lambda asset, flag, k: (solid((0, 0, 255, 255), (20 * k, 20 * k)), 0))
        text = SimpleNamespace(layout=lambda *a: SimpleNamespace(ink_bounds=(0, 0, 10, 10)),
                               draw_layout=lambda canvas, name, layout, x, y, scale=1: titles.append((name, x, y)))
        renderer = CodCharacterPickerRenderer(r, text, art)
        renderer.hint = 'Hint'
        self.assertTrue(renderer.available())
        buttons = renderer.draw(None, s)
        U = renderer.U
        self.assertEqual(boxes, [((0, 120, 320, 240), 243, U)])
        # The title's ink is centred at (160, 112); the check button is frame 41 at (205, 347).
        self.assertEqual(titles, [('PajamaHip26', (160 - 5) * U, (112 - 5) * U)])
        self.assertEqual(renderer.canvas.get_at((210 * U, 352 * U))[:3], (41, 0, 0))
        self.assertEqual(renderer.footer_text, 'Hint')
        self.assertEqual(buttons, [(pygame.Rect(-32, 422, 92, 58), ('menu',))])


@unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user content unavailable')
class HomecomingQueenTests(unittest.TestCase):
    def setUp(self):
        self.library = ContentLibrary(Path('.shs-library'))
        self.addCleanup(self.library.close)
        matches = [e for e in self.library.episodes if e['titles'][0] == 'Homecoming Queen']
        if not matches:
            self.skipTest('Homecoming Queen is not imported')
        self.resources = self.library.open_episode(matches[0]['id'])

    def reach_picker(self):
        session = Session(self.resources)
        for _ in range(500):
            action = session.advance()
            if action.name == 'character_picker':
                return session
            if action.name == 'choice':
                session.answer(next(i for i, enabled in enumerate(action.details['enabled']) if enabled))
            elif action.name == 'text_input':
                session.answer(action.details['default'])
            elif action.name in ('dialogue', 'presentation', 'vm_pause'):
                answer_screen(session)
            else:
                self.fail(f'Unexpected stop before picker: {session.scene} {action}')
        self.fail('Character picker was not reached')

    def test_scene_25003_pc_303_all_five_looks_continue_with_correct_art(self):
        s = self.reach_picker()
        self.assertEqual((s.scene, s.pending.request.pc), (25003, 303))
        self.assertEqual(s.engine.character_picker.characters, [0, 29, 30, 31, 32])
        saved = s.snapshot()
        for index in range(5):
            restored = Session.from_snapshot(self.resources, saved)
            restored.answer(index)
            self.assertEqual(restored.answer().name, 'dialogue')
            self.assertEqual(restored.pending.request.pc, 319)
            self.assertEqual(restored.engine.character_art_variants[0], list(range(26000 + index * 5, 26005 + index * 5)))

    @unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
    def test_original_art_release_input_resize_and_paused_motion(self):
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        from exp_runtime.desktop import Desktop
        import pygame
        self.addCleanup(pygame.quit)
        s = self.reach_picker()
        ui = Desktop(s, audio=False)
        ui.window = pygame.display.set_mode((640, 600))
        ui.render()
        self.assertIsNone(ui.error)
        def click(point, event_type):
            x, y = point
            pos = (ui.viewport.x + x * ui.viewport.width / 320,
                   ui.viewport.y + y * ui.viewport.height / 480)
            ui.handle_event(pygame.event.Event(event_type, pos=pos, button=1))
        click(POSITIONS[4], pygame.MOUSEBUTTONUP)
        self.assertEqual(s.engine.character_picker.selected, 0)
        click(POSITIONS[4], pygame.MOUSEBUTTONDOWN)
        self.assertEqual(s.engine.character_picker.selected, 0)
        click(POSITIONS[4], pygame.MOUSEBUTTONUP)
        self.assertEqual(s.engine.character_picker.selected, 4)
        ui.command(('menu',)); ui.tick(1000)
        self.assertEqual(s.engine.character_picker.portraits[4].elapsed_ms, 0)
        ui.command(('resume',)); ui.tick(25); ui.render()
        self.assertIsNone(ui.error)
        click((240, 365), pygame.MOUSEBUTTONDOWN)
        click((240, 365), pygame.MOUSEBUTTONUP)
        self.assertEqual(s.pending.name, 'dialogue')
        self.assertEqual(s.engine.character_art_variants[0][0], 26020)
