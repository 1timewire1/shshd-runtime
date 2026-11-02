"""The X360 translations' slot machine: MS3's rules, the story's service, saves, the switch and the player's inputs."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from exp_runtime import x360_games as slot
from exp_runtime.runtime import Session
from exp_runtime.x360_games import SlotMachine
from test_runtime import host_call
from test_vm import program


def running():
    game = SlotMachine()
    game.tick(slot.OPENING_MS)                  # the opening's over...
    game.press()                                # ...the player says go and the clock starts...
    game.tick(1)                                # ...and slot 1 comes into focus
    return game


def run(game, ms, step=10):
    for _ in range(ms // step):
        if game.tick(step):
            return True
    return False


class RulesTests(unittest.TestCase):
    def test_each_slot_cycles_faster_as_ms3_has_it(self):
        self.assertEqual([slot.period_ms(n) for n in range(1, 6)], [500, 357, 255, 182, 130])

    def test_it_opens_for_half_a_second_and_presses_do_nothing_then(self):
        game = SlotMachine()
        self.assertFalse(game.press())                          # (one left over from the dialogue can't start it)
        game.tick(499)
        self.assertEqual((game.phase, game.started), (slot.OPENING, False))
        game.tick(1)
        self.assertEqual(game.phase, slot.READY)

    def test_the_clock_waits_for_a_press_however_long_it_takes(self):
        game = SlotMachine()
        game.tick(slot.OPENING_MS)
        self.assertFalse(run(game, 60000, 250))
        self.assertEqual((game.phase, game.clock_ms, game.focus, game.sounds), (slot.READY, 0, -1, []))
        self.assertTrue(game.press())
        self.assertEqual((game.phase, game.points, game.sounds), (slot.RUNNING, 0, [slot.SOUND_TIMER]))
        game.tick(1)
        self.assertEqual((game.clock_ms, game.focus, game.option), (1, 1, slot.BULB))

    def test_the_skip_prompts_play_is_its_go_ahead(self):
        game = SlotMachine()
        self.assertTrue(game.start())
        self.assertEqual(game.phase, slot.OPENING)
        game.tick(slot.OPENING_MS)
        self.assertEqual((game.phase, game.sounds), (slot.RUNNING, [slot.SOUND_TIMER]))
        self.assertFalse(game.start())

    def test_the_slot_in_focus_cycles_bulb_cross_question(self):
        game = running()
        seen = [game.shown[0]]
        for _ in range(4):
            run(game, 510)
            seen.append(game.shown[0])
        self.assertEqual(seen, [slot.BULB, slot.CROSS, slot.QUESTION, slot.BULB, slot.CROSS])
        self.assertEqual(game.shown[1:], [slot.OFF] * 4)

    def test_a_bulb_scores_and_moves_on_a_cross_just_moves_on_a_question_stays(self):
        game = running()
        self.assertTrue(game.press())                           # a bulb
        self.assertEqual((game.points, game.slot, game.sounds[-1]), (1, 2, slot.SOUND_SUCCESS))
        game = running()
        run(game, 510)
        self.assertEqual(game.option, slot.CROSS)
        game.press()
        self.assertEqual((game.points, game.slot, game.sounds[-1]), (0, 2, slot.SOUND_MISS))
        game = running()
        run(game, 1010)
        self.assertEqual(game.option, slot.QUESTION)
        sounds = list(game.sounds)
        game.press()
        self.assertEqual((game.points, game.slot, game.sounds), (0, 1, sounds))
        self.assertEqual(game.shown[0], slot.QUESTION)          # it keeps showing what was taken

    def test_after_a_press_nothing_is_in_focus_for_the_delay_and_a_press_does_nothing(self):
        game = running()
        game.press()
        self.assertEqual(game.focus, -1)
        self.assertFalse(game.press())
        run(game, 790)
        self.assertEqual((game.focus, game.shown[1]), (-1, slot.OFF))
        run(game, 20)
        self.assertEqual(game.focus, 2)

    def test_the_next_slot_opens_on_the_cross_as_ms3s_order_of_events_has_it(self):
        # A press sets the option back to the first while the period's Wait still runs; when that ends it steps on.
        game = running()
        game.press()
        run(game, 830)
        self.assertEqual((game.focus, game.shown[1]), (2, slot.CROSS))

    def test_five_taken_slots_end_it_after_the_delay_with_the_points(self):
        game = running()
        for _ in range(slot.SLOTS):
            for _ in range(200):
                if game.focus == game.slot and game.option == slot.BULB:
                    break
                self.assertFalse(game.tick(10))
            game.press()
        self.assertEqual(game.points, 5)
        finished = run(game, 1000)
        self.assertEqual(game.phase, slot.CLOSING)
        self.assertTrue(finished or run(game, 1000))
        self.assertEqual(game.result, 5)

    def test_the_clock_runs_out_at_15_seconds_and_says_so_for_3(self):
        game = running()
        self.assertFalse(run(game, 14900))
        self.assertEqual(game.phase, slot.RUNNING)
        self.assertFalse(run(game, 200))
        self.assertEqual((game.phase, game.focus), (slot.TIME_UP, -1))
        self.assertFalse(game.press())
        self.assertFalse(run(game, 2700))
        self.assertTrue(run(game, 200))
        self.assertEqual(game.result, 0)

    def test_the_clocks_tick_loops_while_it_runs(self):
        game = running()
        game.sounds.clear()
        run(game, slot.TIMER_LOOP_MS * 3 + 10)
        self.assertEqual(game.sounds, [slot.SOUND_TIMER] * 3)

    def test_any_score_can_be_reached_by_finishing(self):
        # MS3's -1 for a cross left only odd totals (owner, 2026-11-01).
        for bulbs in range(slot.SLOTS + 1):
            game = running()
            for taken in range(slot.SLOTS):
                while game.focus != game.slot or game.option != (slot.BULB if taken < bulbs else slot.CROSS):
                    game.tick(1)
                game.press()
            self.assertFalse(run(game, 700))
            self.assertEqual((game.phase, game.result), (slot.CLOSING, bulbs))


def resources(code):
    return SimpleNamespace(library=SimpleNamespace(game_id='shs', directory=Path('.')),
                           record={'titles': ['x'], 'pack_id': 31400, 'episode_id': 3},
                           identity=dict(profile='slot-test', episode_sha256='0' * 64),
                           program=lambda rid: code, exists=lambda rid: False, linked_program=lambda: None)


class ServiceTests(unittest.TestCase):
    def play(self):
        code = program(*host_call(slot.X360_SLOT), 0x21, 0x33)
        session = Session(resources(code), ephemeral=True)
        action = session.advance()
        self.assertEqual(action.name, 'x360_slot')
        self.assertIsInstance(session.engine.x360_slot, SlotMachine)
        return session

    def test_a_press_is_the_sessions_answer_and_the_time_is_the_sessions(self):
        session = self.play()
        session.tick(250)
        session.tick(250)                                       # (a long gap counts as 250 ms)
        session.answer(None)                                    # the go-ahead
        session.tick(1)
        session.answer(None)
        self.assertEqual(session.engine.x360_slot.points, 1)
        with self.assertRaises(ValueError):
            session.answer(3)

    def test_it_ends_and_the_story_goes_on_without_it(self):
        session = self.play()
        session.engine.x360_slot.start()
        for _ in range(800):
            if session.pending is None or session.pending.name != 'x360_slot':
                break
            session.tick(30)
        self.assertIsNone(session.engine.x360_slot)
        self.assertNotEqual(getattr(session.pending, 'name', None), 'x360_slot')

    def test_a_game_in_progress_saves_and_comes_back_where_it_was(self):
        session = self.play()
        session.tick(250)
        session.tick(250)
        session.answer(None)
        session.tick(1)
        session.answer(None)
        session.tick(240)
        state = json.loads(json.dumps(session.snapshot()))
        self.assertEqual(state['version'], 35)
        again = Session.from_snapshot(resources(program(*host_call(slot.X360_SLOT), 0x21, 0x33)), state)
        self.assertEqual(again.pending.name, 'x360_slot')
        self.assertEqual(again.engine.x360_slot, session.engine.x360_slot)

    def test_a_damaged_save_is_refused(self):
        from exp_runtime.runtime import SaveError
        session = self.play()
        state = json.loads(json.dumps(session.snapshot()))
        state['engine']['x360_slot']['slot'] = 99
        with self.assertRaises(SaveError):
            Session.from_snapshot(resources(program(*host_call(slot.X360_SLOT), 0x21, 0x33)), state)

    def test_the_skip_hands_the_story_those_points(self):
        session = self.play()
        self.assertTrue(session.minigame_unstarted)
        session.engine.x360_slot.tick(slot.OPENING_MS)
        self.assertTrue(session.minigame_unstarted)             # still, while it waits for the go-ahead
        session.answer(None)
        self.assertFalse(session.minigame_unstarted)
        session = self.play()
        session.skip_x360_slot(3)
        self.assertIsNone(session.engine.x360_slot)
        session = self.play()
        session.skip_minigame(True)                             # the generic skip: all five
        self.assertIsNone(session.engine.x360_slot)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class PlayerTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((64, 64))
        self.pygame = pygame
        self.addCleanup(pygame.quit)

    def skin(self):
        import io
        import exp_runtime.desktop_nr_arena_x360 as x
        pygame = self.pygame

        def png(colour=(10, 200, 10, 255), size=(16, 16)):
            surface = pygame.Surface(size, pygame.SRCALPHA)
            surface.fill(colour)
            out = io.BytesIO()
            pygame.image.save(surface, out, 'x.png')
            return out.getvalue()
        chars = {str(ord(ch)): [0, 0, 8, 10, 0, 0, 9, 0] for ch in "Hit the light bulbs!Time's Up"}
        ids = dict(bulb=26420, cross=26421, question=26422, off=26423)
        spec = dict(format=x.FORMAT, version=x.VERSION, slot=dict(
            icons=ids, panel=26424, window=26425, clock=26426,
            font=dict(line_height=12, base=10, chars=chars, kerning={}, pages=[26430])))
        entries = {x.SPEC: json.dumps(spec).encode()}
        entries.update({i: png((i % 256, 100, 100, 255)) for i in (*ids.values(), 26424, 26425, 26426)})
        entries[26430] = png((0, 0, 0, 255), (64, 64))
        archive = SimpleNamespace(entries=entries, read=entries.__getitem__)
        return SimpleNamespace(library=SimpleNamespace(addon=lambda addon_id: ({}, archive)))

    def test_it_draws_every_phase_in_the_whole_frame(self):
        from exp_runtime.desktop_x360_slot import FRAME, X360SlotRenderer
        renderer = X360SlotRenderer(self.skin())
        game = SlotMachine()
        session = SimpleNamespace(engine=SimpleNamespace(x360_slot=game))
        renderer.draw(session)
        self.assertEqual(renderer.canvas.get_size(), FRAME)      # the 3:4 layer Desktop._present lays over the frame
        game.tick(slot.OPENING_MS)
        renderer.draw(session)
        waiting = renderer.canvas.get_bounding_rect()
        game.press()
        game.tick(1)
        renderer.draw(session)
        self.assertGreater(renderer.canvas.get_bounding_rect().height, 300)
        self.assertLess(waiting.top, renderer.canvas.get_bounding_rect().top)   # the prompt sits above the title
        self.assertIsNone(renderer.alpha(game))
        game.phase, game.phase_ms = slot.TIME_UP, 1500
        renderer.draw(session)
        game.phase_ms = 150
        self.assertAlmostEqual(renderer.alpha(game), 0.5)

    def test_the_focus_slot_is_larger_over_its_window(self):
        from exp_runtime.desktop_x360_slot import ICON, ICON_FOCUS, SLOT_X, SLOT_Y, WINDOW, X360SlotRenderer
        renderer = X360SlotRenderer(self.skin())
        game = SlotMachine(phase=slot.RUNNING, focus=2, slot=2, shown=[slot.BULB, slot.CROSS, slot.OFF, slot.OFF, slot.OFF])
        renderer.draw(SimpleNamespace(engine=SimpleNamespace(x360_slot=game)))
        self.assertEqual(renderer.scaled(26421, (ICON_FOCUS, ICON_FOCUS)).get_size(), (ICON_FOCUS, ICON_FOCUS))
        self.assertEqual(renderer.canvas.get_at((SLOT_X[1], SLOT_Y))[:3], (26421 % 256, 100, 100))
        self.assertEqual(renderer.canvas.get_at((SLOT_X[1], SLOT_Y + WINDOW[1] // 2 - 2))[:3], (26425 % 256, 100, 100))
        self.assertGreater(ICON_FOCUS, ICON)

    def test_a_slot_blinks_as_it_is_taken(self):
        from exp_runtime.desktop_x360_slot import SLOT_X, SLOT_Y, X360SlotRenderer
        renderer = X360SlotRenderer(self.skin())
        game = SlotMachine(phase=slot.RUNNING, shown=[slot.BULB, slot.OFF, slot.OFF, slot.OFF, slot.OFF], flash_slot=0,
                           flash_ms=slot.FLASH_MS, slot=2)
        session = SimpleNamespace(engine=SimpleNamespace(x360_slot=game))
        renderer.draw(session)
        hidden = renderer.canvas.get_at((SLOT_X[0], SLOT_Y))[:3]
        game.flash_ms = slot.FLASH_MS - 60
        renderer.draw(session)
        self.assertNotEqual(renderer.canvas.get_at((SLOT_X[0], SLOT_Y))[:3], hidden)

    def desktop(self):
        from exp_runtime.desktop import Desktop
        ui = Desktop.__new__(Desktop)
        ui.session = SimpleNamespace(pending=SimpleNamespace(name='x360_slot'), answer=Mock())
        ui.menu_open, ui.error, ui.host_prompt = False, None, None
        ui._attempt = lambda work: work()
        return ui

    def test_a_click_or_tap_anywhere_presses_it_and_the_gear_opens_the_menu(self):
        import tempfile
        from exp_runtime.desktop import Desktop
        from test_desktop import Resources
        pygame = self.pygame
        with tempfile.TemporaryDirectory() as temporary:
            story = Resources(program(*host_call(slot.X360_SLOT), 0x21, 0x33))
            story.library.directory = Path(temporary)
            session = Session(story, ephemeral=True)
            session.advance()
            ui = Desktop(session, audio=False)
            ui.bg_viewport = frame = pygame.Rect(100, 20, 384, 512)     # (where the story last drew)
            game = session.engine.x360_slot
            for _ in range(3):
                session.tick(250)                               # the opening's over and it waits for a press
            self.assertEqual(game.phase, slot.READY)
            ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=frame.center))
            self.assertEqual(game.phase, slot.RUNNING)
            session.tick(1)
            self.assertEqual(game.focus, 1)
            ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=frame.center))
            self.assertEqual((game.points, game.slot), (1, 2))
            self.assertFalse(ui.menu_open)
            corner = (frame.x + frame.width * 40 // 768, frame.y + frame.height * 980 // 1024)
            ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=corner))
            self.assertTrue(ui.menu_open)
            self.assertEqual(game.slot, 2)                      # the gear isn't a press
            before = (game.clock_ms, game.phase)
            ui.tick(250)
            self.assertEqual((game.clock_ms, game.phase), before)       # nor does it run under the menu

    def test_a_controllers_confirm_presses_it_through_the_players_events(self):
        import tempfile
        from exp_runtime.desktop import Desktop
        from exp_runtime.gamepad import key_event, menu_key
        from test_desktop import Resources
        with tempfile.TemporaryDirectory() as temporary:
            story = Resources(program(*host_call(slot.X360_SLOT), 0x21, 0x33))
            story.library.directory = Path(temporary)
            session = Session(story, ephemeral=True)
            session.advance()
            ui = Desktop(session, audio=False)
            game = session.engine.x360_slot
            for _ in range(3):
                session.tick(250)
            ui.handle_event(key_event(menu_key('south', 'south'), 'south'))
            session.tick(1)
            ui.handle_event(key_event(menu_key('south', 'south'), 'south'))
            self.assertEqual((game.points, game.slot), (1, 2))

    def test_enter_and_space_press_it_and_other_keys_dont(self):
        pygame = self.pygame
        ui = self.desktop()
        for key in (pygame.K_RETURN, pygame.K_SPACE):
            self.assertTrue(ui._slot_key(SimpleNamespace(key=key)))
        self.assertEqual(ui.session.answer.call_count, 2)
        self.assertFalse(ui._slot_key(SimpleNamespace(key=pygame.K_a)))
        ui.menu_open = True
        self.assertFalse(ui._slot_key(SimpleNamespace(key=pygame.K_RETURN)))
        self.assertEqual(ui.session.answer.call_count, 2)


if __name__ == '__main__':
    unittest.main()
