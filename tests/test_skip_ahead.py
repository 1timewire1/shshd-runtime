"""Skip Ahead (skip_ahead.py): where it stops, what it keeps, and that it never runs off the end of a story."""
import os
import tempfile
import unittest

from exp_runtime.skip_ahead import can_skip, skip_ahead

from test_tree_warp import answer_screen, dialogue_story


class SkipAheadOnAStory(unittest.TestCase):
    def setUp(self):
        from exp_runtime.runtime import Session
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.session = Session(dialogue_story(self.temporary.name), ephemeral=True)
        self.session.advance()

    def text(self):
        return self.session.pending.details['text']

    def lines_in_play(self):
        """Every line of the story by playing it normally: what the skip has to agree with."""
        from exp_runtime.runtime import Session
        session = Session(dialogue_story(tempfile.mkdtemp(dir=self.temporary.name)), ephemeral=True)
        session.advance()
        lines = []
        while session.pending is not None and session.pending.name == 'dialogue':
            lines.append(session.pending.details['text'])
            answer_screen(session)
        return lines, session.pending.name if session.pending else None

    def test_with_nothing_left_to_stop_at_it_holds_on_the_last_line(self):
        lines, end = self.lines_in_play()
        self.assertGreater(len(lines), 2)
        self.assertTrue(skip_ahead(self.session))
        self.assertEqual(self.session.pending.name, 'dialogue')
        self.assertEqual(self.text(), lines[-1])
        self.assertFalse(self.session.episode_exited)

    def test_on_the_last_line_there_is_nothing_to_skip(self):
        self.assertTrue(skip_ahead(self.session))
        line = self.text()
        self.assertFalse(skip_ahead(self.session))
        self.assertEqual(self.text(), line)

    def test_the_tree_still_fills_in(self):
        tree = self.session.engine.dt_view
        before = len(list(tree.nodes()))
        self.assertTrue(skip_ahead(self.session))
        self.assertGreater(len(list(tree.nodes())), before)

    def test_the_copy_it_looks_ahead_with_leaves_the_session_alone(self):
        steps = self.session.vm.steps_executed
        line = self.text()
        from exp_runtime import skip_ahead as module
        original = module._Walk.run
        calls = []

        def spy(walk, session, limit):
            calls.append(session is self.session)
            if session is not self.session:
                self.assertEqual((self.session.vm.steps_executed, self.text()), (steps, line))
            original(walk, session, limit)

        module._Walk.run = spy
        self.addCleanup(setattr, module._Walk, 'run', original)
        skip_ahead(self.session)
        self.assertEqual(calls, [False, True])


class StopsAndPasses(unittest.TestCase):
    """The stop list, on the walk itself: a stand-in session whose screens are a list."""

    class Action:
        def __init__(self, name):
            self.name, self.details = name, {}

    class Session:
        transitioning = False
        episode_exited = False

        def __init__(self, names):
            self.queue = [StopsAndPasses.Action(name) for name in names]
            self.vm = type('VM', (), dict(steps_executed=0))()
            self.engine = type('Engine', (), dict(dialogue_animation=None, scene_transition=None))()

        @property
        def pending(self):
            return self.queue[0] if self.queue else None

        def _next(self):
            self.vm.steps_executed += 1
            self.queue.pop(0)

        def answer(self):
            self._next()

        def tick(self, _ms):
            if self.pending.name in ('loading', 'download_poll'):
                self._next()

    def walked(self, *names):
        from exp_runtime.skip_ahead import _Walk
        session = self.Session(names)
        walk = _Walk()
        walk.run(session, 1000)
        return walk.stop, walk.passed

    def test_what_it_passes(self):
        for name in ('dialogue', 'vm_pause', 'message_panel', 'survey_confirmation', 'cutscene', 'loading', 'download_poll'):
            self.assertEqual(self.walked(name, 'choice'), ('choice', 1), name)

    def test_what_stops_it(self):
        for name in ('choice', 'text_input', 'character_picker', 'word_game', 'word_grid', 'football', 'shs11_memory',
                     'shs11_reflex', 'x360_slot', 'x360_leash', 'x360_puzzle', 'x360_diss', 'arena_skip', 'arena_entrance',
                     'arena_frame', 'arena_menu', 'arena_info', 'arena_exit', 'unhandled_yield', 'episode_exit', 'finished'):
            self.assertEqual(self.walked('dialogue', name), (name, 1), name)

    def test_the_next_title_card_stops_it_but_the_one_it_starts_on_does_not(self):
        self.assertEqual(self.walked('dialogue', 'presentation', 'dialogue'), ('presentation', 1))
        self.assertEqual(self.walked('presentation', 'dialogue', 'presentation'), ('presentation', 2))

    def test_a_screen_that_will_not_go_away_stops_it_rather_than_hanging(self):
        session = self.Session(['loading'])
        session.tick = lambda _ms: None
        from exp_runtime.skip_ahead import _Walk
        walk = _Walk()
        walk.run(session, 1000)
        self.assertEqual(walk.stop, 'stuck')

    def test_it_only_starts_on_something_it_can_pass(self):
        self.assertTrue(can_skip(self.Session(['dialogue'])))
        self.assertTrue(can_skip(self.Session(['presentation'])))
        self.assertFalse(can_skip(self.Session(['choice'])))
        self.assertFalse(can_skip(self.Session(['word_game'])))
        self.assertFalse(can_skip(self.Session([])))


class SkipAheadInThePlayer(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        self.pygame = pygame
        self.addCleanup(pygame.quit)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        from exp_runtime.desktop import Desktop
        from exp_runtime.runtime import Session
        session = Session(dialogue_story(self.temporary.name), ephemeral=True)
        session.advance()
        self.ui = Desktop(session, audio=False)

    def press_n(self):
        self.ui.handle_event(self.pygame.event.Event(self.pygame.KEYDOWN, key=self.pygame.K_n, mod=0, unicode='n'))

    def test_the_key_does_nothing_unless_it_is_allowed(self):
        line = self.ui.session.pending.details['text']
        self.press_n()
        self.assertEqual(self.ui.session.pending.details['text'], line)

    def test_the_key_skips_and_the_screen_fades_in_silently(self):
        self.ui.skip_ahead = True
        line = self.ui.session.pending.details['text']
        self.ui.session.engine.request_sound(1)
        self.press_n()
        self.assertNotEqual(self.ui.session.pending.details['text'], line)
        self.assertEqual(self.ui.sound_serial, self.ui.session.engine.sound_serial)
        self.assertEqual(self.ui.fade['phase'], 'in')

    def test_the_pause_menu_offers_it_only_when_allowed_and_it_can_go(self):
        self.assertNotIn('skip_ahead_row', self.ui._pause_settings())
        self.ui.skip_ahead = True
        settings = self.ui._pause_settings()
        self.assertTrue(settings['skip_ahead'])
        self.assertTrue(settings['skip_ahead_row'])

    def test_on_the_last_line_it_says_so_and_stays(self):
        self.ui.skip_ahead = True
        self.press_n()
        self.ui.fade = None
        line = self.ui.session.pending.details['text']
        self.press_n()
        self.assertEqual(self.ui.session.pending.details['text'], line)
        self.assertEqual(self.ui.message, 'Nothing left to skip')


if __name__ == '__main__':
    unittest.main()
