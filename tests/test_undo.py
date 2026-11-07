"""Undo (undo.py): a save at each stop the story makes, and going back along them."""
import tempfile
import unittest
from pathlib import Path

from exp_runtime.runtime import Session
from exp_runtime.undo import UndoChain, clear, directory, is_stop
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def two_choices():
    words, (title, options, first, second, line, last) = text_words('Choose', 'Left|Right', 'A fork.', 'Another fork.',
                                                                    'On you go.', 'The end.')
    return program(*host_call(1, title, options, first, 0, 1, -1, -1, 0),
                   *host_call(13, line, 0),
                   *host_call(1, title, options, second, 0, 1, -1, -1, 0),
                   *host_call(13, last, 0), 0x33, words=words, gap=2)


class UndoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.chain = UndoChain(Path(self.temporary.name) / 'saves' / 'x.shs-undo')
        self.session = Session(Resources(two_choices()))
        self.session.advance()

    def choose(self, session, value):
        answer_screen(session, value)
        while session.pending.name != 'choice' and not session.episode_ended:
            answer_screen(session)
            if session.pending is None:
                break

    def test_only_a_stop_is_saved_and_only_once(self):
        self.assertEqual(self.session.pending.name, 'choice')
        self.assertTrue(self.chain.record(self.session))
        self.assertFalse(self.chain.record(self.session))               # the same choice again
        answer_screen(self.session, 0)
        self.assertEqual(self.session.pending.name, 'dialogue')
        self.assertFalse(self.chain.record(self.session))               # a line isn't a stop
        self.assertEqual(self.chain.numbers(), [1])
        self.assertTrue(is_stop(type('A', (), {'name': 'presentation'})()))     # the title card is one

    def test_undo_after_a_choice_goes_back_to_it(self):
        self.chain.record(self.session)
        at_choice = (self.session.vm.pc, self.session.vm.steps_executed)
        answer_screen(self.session, 0)
        self.assertTrue(self.chain.can_undo(self.session))
        back = self.chain.undo(self.session)
        self.assertEqual((back.pending.name, back.vm.pc, back.vm.steps_executed), ('choice', *at_choice))
        self.assertEqual(self.chain.numbers(), [1])                     # it stays, as the chain's end
        self.assertFalse(self.chain.record(back))                       # and isn't saved twice

    def test_undo_at_a_stop_drops_it_and_goes_to_the_one_before(self):
        self.chain.record(self.session)
        first_steps = self.session.vm.steps_executed
        self.choose(self.session, 1)
        self.assertEqual(self.session.pending.name, 'choice')           # the second fork
        self.chain.record(self.session)
        self.assertEqual(self.chain.numbers(), [1, 2])
        back = self.chain.undo(self.session)                            # sitting at the second: to the first
        self.assertEqual((back.pending.name, back.vm.steps_executed), ('choice', first_steps))
        self.assertEqual(self.chain.numbers(), [1])
        self.assertFalse(self.chain.can_undo(back))                     # nothing before the first
        self.assertIsNone(self.chain.undo(back))

    def test_restart_reloads_the_latest_save_and_keeps_it(self):
        self.chain.record(self.session)
        self.choose(self.session, 0)
        self.chain.record(self.session)
        steps = self.session.vm.steps_executed
        self.assertTrue(self.chain.at_latest(self.session))
        again = self.chain.restart(self.session)
        self.assertEqual((again.pending.name, again.vm.steps_executed), ('choice', steps))
        self.assertEqual(self.chain.numbers(), [1, 2])                  # nothing dropped
        answer_screen(again, 0)
        self.assertIsNone(self.chain.restart(again))                     # moved on: not on it any more

    def test_a_new_path_after_undo_starts_from_where_it_landed(self):
        self.chain.record(self.session)
        self.choose(self.session, 0)
        self.chain.record(self.session)
        answer_screen(self.session, 0)
        back = self.chain.undo(self.session)                            # past the second: back to it
        self.assertEqual(self.chain.numbers(), [1, 2])
        back = self.chain.undo(back)                                    # at it: to the first, the second goes
        self.assertEqual(self.chain.numbers(), [1])
        self.choose(back, 1)
        self.chain.record(back)
        self.assertEqual(self.chain.numbers(), [1, 2])

    def test_the_chain_is_kept_on_disk_and_cleared_with_the_episode(self):
        self.chain.record(self.session)
        again = UndoChain(self.chain.folder)
        self.assertEqual(again.numbers(), [1])
        self.assertTrue(again.can_undo(type('S', (), {'pending': None})()))
        root = Path(self.temporary.name)
        self.assertEqual(directory(root, 'x'), self.chain.folder)
        clear(root, 'x')
        self.assertFalse(self.chain.folder.exists())

    def test_a_preview_never_saves(self):
        self.session.ephemeral = True
        self.assertFalse(self.chain.record(self.session))

    def test_chains_stay_out_of_synced_progress(self):
        from exp_runtime.progress_bundle import progress_files
        root = Path(self.temporary.name)
        self.chain.record(self.session)
        (root / 'saves' / 'x.shs-auto.json').write_text('{}', encoding='utf-8')
        self.assertEqual([name for name, _ in progress_files(root)], ['saves/x.shs-auto.json'])


class UndoInThePlayer(unittest.TestCase):
    def setUp(self):
        import os
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        self.pygame = pygame
        self.addCleanup(pygame.quit)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        from exp_runtime.desktop import Desktop
        resources = Resources(two_choices())
        resources.library.directory = Path(self.temporary.name)
        resources.record = dict(resources.record, id='x')
        session = Session(resources)
        session.advance()
        self.ui = Desktop(session, audio=False)

    def press_u(self):
        self.ui.handle_event(self.pygame.event.Event(self.pygame.KEYDOWN, key=self.pygame.K_u, mod=0, unicode='u'))

    def test_nothing_is_kept_or_offered_unless_it_is_allowed(self):
        self.ui.tick(0)
        self.assertFalse(directory(self.temporary.name, 'x').exists())
        self.assertNotIn('undo_row', self.ui._pause_settings())

    def test_a_choice_is_kept_and_undo_returns_to_it(self):
        self.ui.undo = True
        self.ui.tick(0)                                                 # the first fork comes up: kept
        self.assertEqual(UndoChain(directory(self.temporary.name, 'x')).numbers(), [1])
        self.assertNotIn('undo_row', self.ui._pause_settings())         # nothing before it
        answer_screen(self.ui.session, 0)
        self.ui.tick(0)
        settings = self.ui._pause_settings()
        self.assertTrue(settings['undo'] and settings['undo_row'])
        self.press_u()
        self.assertEqual(self.ui.session.pending.name, 'choice')
        self.assertEqual(self.ui.fade['phase'], 'in')

    def test_typing_a_u_into_a_name_types_it(self):
        # The `u` (Undo) and `n` (Skip Ahead) keys are letters while a name is entered (owner, 2026-11-07: M.A.S.H.).
        from exp_runtime.desktop import Desktop
        words, (title, options, first, name, prompt, default) = text_words('Choose', 'Left|Right', 'A fork.', 'Name',
                                                                          'Who are you?', '')
        resources = Resources(program(*host_call(1, title, options, first, 0, 1, -1, -1, 0),
                                      *host_call(17, name, prompt, default), 0x21, 0x33, words=words, gap=2))
        resources.library.directory = Path(self.temporary.name)
        resources.record = dict(resources.record, id='y')
        session = Session(resources)
        session.advance()
        ui = Desktop(session, audio=False)
        ui.undo = ui.skip_ahead = True
        ui.tick(0)
        answer_screen(session, 0)
        ui.tick(0)
        self.assertEqual(session.pending.name, 'text_input')
        self.assertTrue(ui._undo_ready())                               # Undo could go back, from the pause menu
        for key, letter in ((self.pygame.K_u, 'u'), (self.pygame.K_n, 'n')):
            ui.handle_event(self.pygame.event.Event(self.pygame.KEYDOWN, key=key, mod=0, unicode=letter))
            ui.handle_event(self.pygame.event.Event(self.pygame.TEXTINPUT, text=letter))
        self.assertEqual(session.pending.name, 'text_input')
        self.assertIsNone(ui.fade)
        self.assertEqual(session.pending.details['draft'][-2:], 'un')

    def test_undo_in_a_game_under_way_restarts_it(self):
        from unittest import mock
        self.ui.undo = True
        self.ui.tick(0)
        answer_screen(self.ui.session, 0)
        while self.ui.session.pending.name != 'choice':
            answer_screen(self.ui.session)
        self.ui.tick(0)                                                 # the second fork: kept, as a game would be
        chain = UndoChain(directory(self.temporary.name, 'x'))
        self.assertEqual(chain.numbers(), [1, 2])
        steps = self.ui.session.vm.steps_executed
        with mock.patch('exp_runtime.desktop.MINIGAMES', frozenset(('choice',))):     # (this fork plays the game)
            self.ui.host_prompt = dict(action=self.ui.session.pending, options=('Win', 'Lose', 'Play'))
            self.assertFalse(self.ui._undo_restarts())                  # at its skip prompt: back one, as before
            self.ui.host_prompt = None
            self.assertTrue(self.ui._undo_restarts())                   # under way: it starts over
            self.press_u()
        self.assertEqual((self.ui.session.pending.name, self.ui.session.vm.steps_executed), ('choice', steps))
        self.assertEqual(UndoChain(directory(self.temporary.name, 'x')).numbers(), [1, 2])

    def test_a_skip_prompt_does_not_hold_undo_up(self):
        self.ui.undo = True
        self.ui.tick(0)
        answer_screen(self.ui.session, 0)
        self.ui.tick(0)
        self.ui.host_prompt = dict(action=self.ui.session.pending, options=('Win', 'Lose', 'Play'))  # (as a mini-game's)
        self.assertTrue(self.ui._pause_settings()['undo_row'])
        self.press_u()
        self.assertIsNone(self.ui.host_prompt)
        self.assertEqual(self.ui.session.pending.name, 'choice')


if __name__ == '__main__':
    unittest.main()
