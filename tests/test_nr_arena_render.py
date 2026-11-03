"""shshd-runtime: New Rules' minigame arena in the player (desktop_nr_arena.py), drawn from an authored stand-in skin:
the bitmap fonts' switches, the ring and buttons, the menu, clicks and keys."""
import importlib.util
import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock


def skin_files(pygame, frame=None):
    """A small skin in the addon's format: one atlas of plain blocks, every node and layout the renderer reads, and
    with `frame` (an RGB colour) a frame picture of that colour."""
    names = ['button/ok', 'button/second', 'button/left', 'button/right', 'meter/0/0', 'meter/0/1', 'dial/0',
             'dial/1', 'menu/bullet', 'icon/0', 'frame/4/22', *(f'timer/{i}' for i in range(17)),
             *(f'menu/arrow/{i}' for i in range(6))]
    glyphs = {56: 'ABC', 59: 'ABC', 61: '0123456789'}
    sprites, x = {}, 0
    for name in names:
        sprites[name] = dict(rect=[x, 0, 8, 8], offset=[0, 0])
        x += 9
    for resource, chars in glyphs.items():
        for ch in chars:
            sprites[f'font/{resource}/{ord(ch)}'] = dict(rect=[x, 0, 6, 10], offset=[0, 0])
            x += 7
    atlas = pygame.Surface((x, 10), pygame.SRCALPHA)
    atlas.fill((200, 40, 40, 255))
    nodes = dict(field=[0, 300, 480, 120], wide=[0, 330, 480, 90], band=[0, 98, 480, 74],
                 bottom_band=[0, 479, 480, 70], table=[-23, 294, 526, 152], ok=[208, 400, 64, 32], second=[216, 297, 49, 24],
                 left=[154, 396, 48, 34], right=[278, 396, 48, 34], hint=[227, 404, 26, 22], timer=[28, 102, 60, 60],
                 meter=[389, 102, 60, 60], meter_frame=[389, 102, 60, 60])
    for box, y in ((0, 106), (1, 345), (2, 486)):
        for part in ('label', 'label_alt', 'text', 'item', 'item_alt'):
            nodes[f'hud{box}_{part}'] = [90, y, 200, 40]
    fill = dict(kind=2, flags=18, payload=[0], base=[0, 0, 10, 10], relative=[0, 0, 4096, 4096])
    face = dict(kind=6, flags=6, payload=[], base=[0, 0, 10, 10], relative=[0, 0, 4096, 4096])
    dial = dict(kind=1, flags=17, payload=[4, -1], base=[0, 0, 10, 10], relative=[0, 0, 4096, 4096])
    layouts = {str(i): dict(size=[10, 10], nodes=[fill] if i in (25, 27, 70) else [dial, face])
               for i in (11, 25, 27, 33, 34, 66, 67, 70)}
    font = dict(space=4, gap=0, track=-2, height=10, extra=0)
    spec = dict(format='shshd-nr-arena-skin', version=1, screen=[480, 650], nodes=nodes, layouts=layouts,
                colors=[0x5E3365, 0xFFFFFF, 0, 0xE7A64A, 0x75FC84, 0, 0xE76110], sprites=sprites,
                markers=[[0] * 10, [0] * 10], background=dict(period=128, step_ms=100),
                buttons=dict(right=0x33FF33, wrong=0xFF3333, pressed=0x9966FF, idle=0x6600CC, alternate=0xFF9933),
                fonts={'56': font, '59': dict(font, extra=1), '61': font}, item_fonts=[56, 61, 59, 56],
                score_font=61, info_font=57)

    def png(surface):
        out = io.BytesIO()
        pygame.image.save(surface, out, 'skin.png')
        return out.getvalue()
    files = {'skin.json': json.dumps(spec).encode(), 'static.png': png(pygame.Surface((480, 650), pygame.SRCALPHA)),
             'tile.png': png(pygame.Surface((128, 128))), 'atlas.png': png(atlas)}
    if frame is not None:
        picture = pygame.Surface((384, 512))
        picture.fill(frame)
        files['frame.png'] = png(picture)
    return files


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class ArenaRenderTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((1, 1))
        from exp_runtime import desktop_nr_arena
        self.pygame, self.module = pygame, desktop_nr_arena
        files = skin_files(pygame)
        by_id = {resource: files[name] for name, resource in desktop_nr_arena.SKIN.items()}
        self.resources = SimpleNamespace(raw_asset=by_id.__getitem__, exists=by_id.__contains__)

    def renderer(self):
        return self.module.NRArenaRenderer(self.resources)

    def session(self, arena, pending='arena_frame', **details):
        from exp_runtime.nr_arena import ENTRANCE_MS
        if arena is not None and pending != 'arena_entrance':
            arena.entrance_ms = ENTRANCE_MS
        return SimpleNamespace(engine=SimpleNamespace(nr_arena=arena, resolve_text=lambda vm, i: None), vm=None,
                               pending=SimpleNamespace(name=pending, details=details))

    def test_a_font_switch_takes_no_room_and_hands_the_next_letters_to_the_other_font(self):
        renderer = self.renderer()
        renderer.available()
        font = renderer.skin().fonts[56]
        cells = font.cells('A`1`B')
        self.assertEqual([(ch, f) for ch, f in cells], [('A', font), ('1', renderer.skin().fonts[61]), ('B', font)])
        self.assertEqual(font.width('A`1`B'), 3 * 6 - 2 * 2)
        self.assertEqual(font.width('ab'), font.width('AB'))     # a missing case borrows the other
        self.assertEqual(font.width('A~A'), 6 + 1 - 2 + 6)        # 59 advances a pixel more
        self.assertEqual([len(line) for line in font.lines('AB AB AB', 12)], [2, 2, 2])

    def test_the_arena_draws_into_the_frame_and_its_buttons_take_clicks(self):
        from exp_runtime.nr_arena import NRArena
        arena = NRArena.opened(False, True)
        arena.set(-10, 729, 4)
        arena.item_kind = 3
        for slot, word in enumerate(('AB', 'BC', 'CA', 'AC')):
            arena.set_text_item(slot, word)
        arena.timer_ms = arena.timer_total_ms = 10000
        arena.timer_shown = True
        renderer = self.renderer()
        self.assertTrue(renderer.available())
        renderer.draw(None, self.session(arena), now_ms=1234)
        # The game area scaled up whole (nearest-neighbour) past the frame's height in the window, at exactly 3:4.
        self.assertEqual(renderer.canvas.get_size(), (489 * 2, 652 * 2))
        renderer.target_height = 1500
        renderer.draw(None, self.session(arena), now_ms=1234)
        self.assertEqual(renderer.canvas.get_size(), (489 * 3, 652 * 3))
        self.assertEqual(renderer.canvas.get_width() * 4, renderer.canvas.get_height() * 3)
        # The OK button (208, 400, 64 x 32 in the X1i's game area, 4 px in) is at about (379, 655) in the frame.
        self.assertEqual(renderer.hit((379, 655)), ('arena_key', -5))
        self.assertEqual(renderer.hit((280, 650)), ('arena_key', -3))
        self.assertIsNone(renderer.hit((20, 20)))

    def test_the_arena_stands_on_the_dialogue_screens_frame_when_the_skin_has_it(self):
        from exp_runtime.nr_arena import NRArena
        files = skin_files(self.pygame, frame=(10, 200, 30))
        names = {**self.module.SKIN, 'frame.png': self.module.FRAME_PICTURE}
        by_id = {resource: files[name] for name, resource in names.items()}
        renderer = self.module.NRArenaRenderer(SimpleNamespace(raw_asset=by_id.__getitem__, exists=by_id.__contains__))
        renderer.draw(None, self.session(NRArena.opened(False, False)), now_ms=0)
        # The static screen is clear here, so the frame's picture shows through, scaled to the whole canvas.
        self.assertEqual(renderer.canvas.get_at((3, 3))[:3], (10, 200, 30))
        self.assertEqual(renderer.canvas.get_at((renderer.canvas.get_width() - 3, 600))[:3], (10, 200, 30))

    def test_the_entrance_draws_its_moving_layouts_and_takes_no_clicks(self):
        from exp_runtime.nr_arena import NRArena
        arena = NRArena.opened(False, True)
        renderer = self.renderer()
        for ms in (0, 300, 1000, 1990):
            arena.entrance_ms = ms
            renderer.draw(None, self.session(arena, 'arena_entrance'), now_ms=ms)
            self.assertEqual(renderer.targets, [])
        for ms in (0, 700, 1500, 1990):                                 # the exit: the same tracks backwards
            arena.exit_ms = ms
            renderer.draw(None, self.session(arena, 'arena_exit'), now_ms=ms)
            self.assertEqual(renderer.targets, [])
        self.assertEqual(self.module.eased(5, 720, 800), 105)          # the bands pass their place, then settle
        self.assertEqual(self.module.eased(6, 1200, 1200), 100)

    def test_after_the_exit_only_the_frame_shows(self):
        # The library waits a frame after closing the panel; that frame (which then fades out over the next screen)
        # is the bare frame, not the arena's table and bands back again (owner, 2026-10-31).
        from exp_runtime.nr_arena import NRArena
        files = skin_files(self.pygame, frame=(10, 200, 30))
        names = {**self.module.SKIN, 'frame.png': self.module.FRAME_PICTURE}
        by_id = {resource: files[name] for name, resource in names.items()}
        renderer = self.module.NRArenaRenderer(SimpleNamespace(raw_asset=by_id.__getitem__, exists=by_id.__contains__))
        skin = renderer.skin()
        skin.static.fill((200, 40, 40, 255))                # a static screen that covers the frame
        renderer.draw(None, self.session(NRArena.opened(False, False)), now_ms=0)
        self.assertEqual(renderer.canvas.get_at((300, 300))[:3], (200, 40, 40))
        renderer.draw(None, self.session(None), now_ms=0)
        self.assertEqual(renderer.canvas.get_at((300, 300))[:3], (10, 200, 30))

    def test_the_menu_highlights_its_selected_option_and_steps_through_them(self):
        from exp_runtime.nr_arena import NRArena
        renderer = self.renderer()
        session = self.session(NRArena.opened(False, False), 'arena_menu', title='AB', options=['A', 'B', 'C'],
                               selected=1)
        action = session.pending
        renderer.draw(None, session, now_ms=0)
        self.assertEqual(renderer.focus(action), 1)
        renderer.move_focus(action, 1)
        renderer.move_focus(action, 1)
        self.assertEqual(renderer.focus(action), 0)
        answers = [command for _, command in renderer.targets]
        self.assertEqual(answers, [('arena_answer', 0), ('arena_answer', 1), ('arena_answer', 2)])
        renderer.draw(None, session, now_ms=0, overlay=False)           # under SHS's choice: no menu of its own
        self.assertNotIn(('arena_answer', 0), [command for _, command in renderer.targets])

    def test_sequences_items_take_clicks_as_their_slots_number_keys(self):
        from exp_runtime.nr_arena import NRArena
        arena = NRArena.opened(False, False)
        arena.set(-10, 729, 6)
        arena.item_kind, arena.keypad = 2, True
        for slot in range(6):
            arena.set_item(slot, 0)
        renderer = self.renderer()
        renderer.draw(None, self.session(arena), now_ms=0)
        items = [(rect, command) for rect, command in renderer.targets if command[1] >= 48]
        self.assertEqual(sorted(command[1] for _, command in items[-6:]), list(range(49, 55)))
        for rect, command in items[-6:]:                    # the items, drawn after the numbers, are hit first
            self.assertEqual(renderer.hit((rect.centerx * 768 / 489, rect.centery * 1024 / 652)), command)
        arena.keypad = False                                # a turning game's items take no clicks
        renderer.draw(None, self.session(arena), now_ms=0)
        self.assertFalse([command for _, command in renderer.targets if command[1] >= 48])

    def test_a_tap_anywhere_closes_the_info_box(self):
        from exp_runtime.nr_arena import NRArena
        renderer = self.renderer()
        renderer.draw(None, self.session(NRArena.opened(False, False), 'arena_info', text='AB'), now_ms=0)
        self.assertEqual(renderer.hit((20, 20)), ('arena_answer', 0))
        self.assertEqual(renderer.hit((700, 1000)), ('arena_answer', 0))


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class ArenaKeyTests(unittest.TestCase):
    """Keys (and a controller's, which arrive as keys) on the arena, its menu and its info box."""

    def desktop(self, pending, **details):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((1, 1))
        from exp_runtime.desktop import Desktop
        from exp_runtime.desktop_nr_arena import NRArenaRenderer
        ui = Desktop.__new__(Desktop)
        ui.press, ui.gear_pointer_down, ui._sync_text_input = Mock(), False, Mock()
        ui.fade, ui.menu_open, ui.error, ui.host_prompt, ui.notice_stack = None, False, None, None, None
        ui.pause_closing, ui._tree_zoom = False, SimpleNamespace(tab=None, showing=False)
        ui.session = SimpleNamespace(pending=SimpleNamespace(name=pending, details=details), transitioning=False,
                                     engine=SimpleNamespace(word_grid=None))
        ui.nr_arena_renderer = NRArenaRenderer(SimpleNamespace())
        ui.command, ui._attempt = Mock(), (lambda operation: operation())
        return ui

    def key(self, ui, key, button=None):
        from exp_runtime.gamepad import key_event
        return ui.handle_event(key_event(key, button))

    def test_keys_reach_the_arena_as_new_rules_key_codes(self):
        import pygame
        ui = self.desktop('arena_frame')
        for key, code in ((pygame.K_RETURN, -5), (pygame.K_SPACE, -5), (pygame.K_UP, -1), (pygame.K_DOWN, -2),
                          (pygame.K_LEFT, -3), (pygame.K_RIGHT, -4), (pygame.K_BACKSPACE, -7), (pygame.K_3, 51),
                          (pygame.K_KP6, 54)):
            self.key(ui, key)
            self.assertEqual(ui.command.call_args.args[0], ('arena_key', code))
        self.key(ui, pygame.K_ESCAPE)                       # Escape still pauses
        self.assertEqual(ui.command.call_args.args[0], ('menu',))

    def test_the_arenas_last_picture_fades_out_over_the_next_screen(self):
        import pygame
        from unittest.mock import patch
        from exp_runtime.desktop import ARENA_HANDOVER_MS
        ui = self.desktop('dialogue')
        ui.capture = False
        ui.window = pygame.Surface((200, 200))
        ui.bg_viewport = pygame.Rect(50, 0, 100, 200)
        layer = pygame.Surface((489, 652))
        layer.fill((255, 255, 255))
        ui.arena_handover = dict(layer=layer, since=None, scaled=None)
        with patch('pygame.time.get_ticks', return_value=1000):
            ui._draw_arena_handover()
        self.assertGreater(ui.window.get_at((100, 100))[0], 200)       # just begun: the arena's picture still shows
        self.assertEqual(ui.window.get_at((10, 100))[:3], (0, 0, 0))     # only over the frame
        ui.window.fill((0, 0, 0))
        with patch('pygame.time.get_ticks', return_value=1000 + ARENA_HANDOVER_MS * 3 // 4):
            ui._draw_arena_handover()
        self.assertLess(ui.window.get_at((100, 100))[0], 100)
        with patch('pygame.time.get_ticks', return_value=1000 + ARENA_HANDOVER_MS):
            ui._draw_arena_handover()
        self.assertIsNone(ui.arena_handover)

    def test_the_menu_takes_the_arrows_and_enter_and_the_info_box_enter(self):
        import pygame
        ui = self.desktop('arena_menu', title='', options=['a', 'b'], selected=0)
        self.key(ui, pygame.K_DOWN, 'down')
        self.key(ui, pygame.K_RETURN, 'south')
        self.assertEqual(ui.command.call_args.args[0], ('arena_answer', 1))
        ui = self.desktop('arena_info', text='')
        self.key(ui, pygame.K_RETURN)
        self.assertEqual(ui.command.call_args.args[0], ('arena_answer', 0))

    def test_a_tap_on_the_arena_is_its_ok_key_and_the_gear_pauses(self):
        ui = self.desktop('arena_frame')
        action = ui.session.pending
        self.assertEqual(ui._arena_tap(action, 400, 100), ('arena_key', -5))
        self.assertEqual(ui._arena_tap(action, 40, 950), ('menu',))
        self.assertIsNone(ui._arena_tap(action, 900, 100))                 # outside the frame
        ui = self.desktop('arena_entrance')
        self.assertIsNone(ui._arena_tap(ui.session.pending, 400, 100))       # New Rules takes no keys meanwhile

    def test_the_minigame_arena_switch_reaches_every_session_and_is_kept(self):
        # Options' Minigame Arena (on by default): off, translated New Rules episodes play their timed choices
        # (test_menu keeps it in player.json).
        from exp_runtime.desktop import Desktop
        from exp_runtime.menu import preference_defaults
        ui = self.desktop('dialogue')
        ui._session = ui.session
        ui.arena_minigames = False
        self.assertIs(ui.session.nr_arena, False)
        Desktop.session.fset(ui, SimpleNamespace(nr_arena=True, share_names=Mock()))
        self.assertIs(ui.session.nr_arena, False)           # the next episode's session too
        self.assertIs(preference_defaults()['arena_minigames'], True)

    def test_ask_to_skip_offers_each_route_of_an_arena_game(self):
        # The skip question before an arena game (213): an option per route its story takes (arena_outcomes), each
        # handing the story its lowest result, then Play (-1). Switched off, the game plays at once.
        from unittest.mock import patch
        from exp_runtime.desktop import arena_skip_options
        self.assertEqual(arena_skip_options([(0, 4), (5, None)]), (('Win', 'Lose', 'Play'), (5, 0)))
        self.assertEqual(arena_skip_options([(0, 4), (5, 5), (6, None)]),
                         (('Score 6 or more', 'Score 5', 'Score 0 to 4', 'Play'), (6, 5, 0)))
        self.assertEqual(arena_skip_options([(0, None)]), (('Skip', 'Play'), (0,)))
        self.assertEqual(arena_skip_options(None), (('Win', 'Lose', 'Play'), (15, 0)))
        ui = self.desktop('arena_skip')
        ui.session.resources, ui.session.scene, ui.session.answer = SimpleNamespace(read_asset=None), None, Mock()
        ui._skip_minigames = True
        with patch('exp_runtime.desktop.arena_outcomes', return_value=[(0, 4), (5, None)]):
            prompt = ui._host_prompt()
        self.assertEqual(prompt['options'], ('Win', 'Lose', 'Play'))
        prompt['resolve'](0)
        ui.session.answer.assert_called_with(5)
        prompt['resolve'](2)
        ui.session.answer.assert_called_with(-1)
        ui = self.desktop('arena_skip')
        ui.session.resources, ui.session.answer = SimpleNamespace(read_asset=None), Mock()
        self.assertIsNone(ui._host_prompt())                # Ask to Skip off: it plays
        ui.session.answer.assert_called_once_with(-1)

    def test_the_arenas_menu_is_shs_choice(self):
        from exp_runtime.desktop import arena_menu_prompt
        self.assertEqual(arena_menu_prompt(dict(title='welcome to the `rhyming` game.  view tutorial?',
                                                options=['yes', 'no'])),
                         ('View tutorial?', 'Welcome to the Rhyming game.', ['Yes', 'No']))
        self.assertEqual(arena_menu_prompt(dict(title='welcome to the `dj fever` game.  view tutorial?',
                                                options=['yes', 'no']))[1], 'Welcome to the DJ Fever game.')
        self.assertEqual(arena_menu_prompt(dict(title='play again?', options=['yes'])), ('Play again?', '', ['Yes']))
        ui = self.desktop('arena_menu', title='welcome to the `sequences` game.  view tutorial?',
                          options=['yes', 'no'], selected=0)
        ui.skip_minigames = False
        ui.session.resources, ui.session.scene, ui.session.answer = SimpleNamespace(read_asset=None), None, Mock()
        prompt = ui._host_prompt()
        details = prompt['session'].pending.details
        self.assertEqual((details['title'], details['text'], details['options']),
                         ('View tutorial?', 'Welcome to the Sequences game.', ['Yes', 'No']))
        self.assertIs(ui._host_prompt(), prompt)
        prompt['resolve'](1)
        ui.session.answer.assert_called_once_with(1)


if __name__ == '__main__':
    unittest.main()
