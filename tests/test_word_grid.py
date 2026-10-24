import copy
import json
from pathlib import Path
import unittest

from exp_runtime.content import ContentLibrary
from exp_runtime.randomness import NativeRandom
from exp_runtime.runtime import SaveError, Session
from exp_runtime.shs.word_grid import GridProblem, WordGrid
from test_runtime import Resources, host_call, text_words
from test_vm import program


def resources(*, tutorial=False, targets='cat'):
    words, refs = text_words('Find a word', 'CAT', targets, 'catx', 'cat\ncat', 'Learn',
                             'Trace the letters', 'Correct', 'Try again')
    table = len(words)
    words += [3, 2, *refs[:4], 1, 0, 1, -1]
    tutor = len(words)
    words += [refs[5], refs[6], 1, 0, 0, 3, 2, refs[0], refs[1], refs[2], 1,
              refs[4], 1, 1, 0, 0, -2]
    args = [2, 200, 1000, 500, 0, -1, -1, 0, -1, 0, 0, 1, table,
            1, refs[7], refs[8], 0, 0, int(tutorial), tutor]
    return Resources(program(*host_call(96, *args), 0x21, (0x1f, 0xfe01), words=[w & 0xffff for w in words]))


def tutorial_resources():
    words, refs = text_words('Find a word', 'CAT', 'cat', 'catx', '', 'Learn',
                             'Touch to continue.', 'Trace the word.', 'Try the hint.', 'Correct', 'Try again')
    table = len(words)
    words += [3, 2, *refs[:4], 1, 0, 1, -1]
    tutor = len(words)
    # Instruction, exercise, retry explanation, hinted exercise, completion.
    for tap, targets, hints, timed, failure, success, text in (
            (1, refs[4], 0, 0, -1, 1, refs[6]),
            (0, refs[2], 0, 1, 2, 4, refs[7]),
            (1, refs[4], 1, 0, -1, 3, refs[8]),
            (0, refs[2], 1, 1, 2, 4, refs[7]),
            (1, refs[4], 0, 0, -1, -2, refs[6])):
        words += [refs[5], text, 0, tap, 0, 3, 1, refs[0], refs[1], targets,
                  1, refs[2], hints, 0, timed, failure, success]
    args = [2, 200, 1000, 500, 0, -1, -1, 0, -1, 0, 0, 1, table,
            1, refs[9], refs[10], 0, 0, 5, tutor]
    return Resources(program(*host_call(96, *args), 0x21, (0x1f, 0xfe01), words=[w & 0xffff for w in words]))


def play_phase(session):
    for _ in range(60):
        if session.engine.word_grid.phase == 1:
            return
        session.tick(250)
    raise AssertionError('Grid did not enter active play')


class GridTests(unittest.TestCase):
    def test_success_breaks_tiles_with_native_random_draws_and_resumes_in_flight(self):
        r = resources(tutorial=True)
        s = Session(r); s.engine.random = NativeRandom(1); s.advance(); play_phase(s)
        held = s.vm.snapshot()
        expected_random = copy.deepcopy(s.engine.random)
        for _ in range(3 * 8 * 12):
            expected_random.next()
        for phase, cell in (('down', 0), ('move', 1), ('move', 2)):
            s.grid_pointer(phase, cell)
        g = s.engine.word_grid
        self.assertEqual([len(burst) for burst in g.explosions], [8, 8, 8])
        self.assertFalse(g.pop_ms)
        self.assertEqual([(g.tiles[i].grow_ms, g.tiles[i].grow_delay) for i in (0, 1, 2)],
                         [(600, 1)] * 3)
        self.assertEqual(s.engine.random.state, expected_random.state)
        self.assertEqual(s.vm.snapshot(), held)
        fragment = copy.deepcopy(g.explosions[0][0])
        s.tick(100)
        moved = g.explosions[0][0]
        self.assertAlmostEqual(moved.x, fragment.x + fragment.vx / 10, places=4)
        self.assertAlmostEqual(moved.y, fragment.y + fragment.vy / 10, places=4)
        self.assertAlmostEqual(moved.vy, fragment.vy + 160, places=4)
        self.assertEqual([(g.tiles[i].grow_ms, g.tiles[i].grow_delay) for i in (0, 1, 2)],
                         [(501, -99)] * 3)
        saved = json.loads(json.dumps(s.snapshot()))
        restored = Session.from_snapshot(r, saved)
        for _ in range(30):
            s.tick(50); restored.tick(50)
            self.assertEqual(s.snapshot(), restored.snapshot())
        self.assertFalse(g.explosions)
        self.assertFalse(g.pop_ms)
        self.assertEqual(s.engine.random.state, expected_random.state)
        for field, value in (('x', float('nan')), ('scale', -1), ('age_ms', -1)):
            bad = copy.deepcopy(saved)
            bad['engine']['word_grid']['explosions'][0][0][field] = value
            with self.subTest(field=field), self.assertRaises(SaveError):
                Session.from_snapshot(r, bad)

    def test_version_17_grid_keeps_gameplay_and_migrates_only_new_visuals(self):
        r = resources(tutorial=True); s = Session(r); s.advance(); play_phase(s)
        s.grid_pointer('down', 0)
        old = json.loads(json.dumps(s.snapshot())); old['version'] = 17
        for key in ('pop_ms', 'explosions', 'glint_ms'):
            del old['engine']['word_grid'][key]
        before = copy.deepcopy(old)
        restored = Session.from_snapshot(r, old)
        self.assertEqual(old, before)
        self.assertEqual(restored.vm.snapshot(), s.vm.snapshot())
        self.assertEqual(restored.engine.random, s.engine.random)
        self.assertEqual(restored.engine.word_grid.selection, [0])
        current = restored.snapshot()
        self.assertEqual(current['version'], 29)
        for key, value in (('pop_ms', {}), ('explosions', []), ('glint_ms', 100_000_000)):
            self.assertEqual(current['engine']['word_grid'].pop(key), value)
        self.assertEqual(json.loads(json.dumps(current['engine']['word_grid'])), old['engine']['word_grid'])

    def test_native_grid_words_trim_controls_and_drop_empty_fields(self):
        for text, expected in [(' cat ||\x1f| cat | ', ['cat', 'cat']),
                               ('cat|x', ['cat']), ('cat|x ', ['cat', 'x']), ('x', ['x'])]:
            with self.subTest(text=text):
                s = Session(resources(targets=text)); s.engine.random = NativeRandom(1)
                self.assertEqual(s.advance().name, 'word_grid')
                self.assertEqual(s.engine.word_grid.problems[0].words, expected)

    def test_instruction_pages_timeout_retry_save_and_game_callback(self):
        r = tutorial_resources(); s = Session(r); s.engine.random = NativeRandom(1)
        self.assertEqual(s.advance().name, 'word_grid')
        held = s.vm.snapshot(); initial_random = s.engine.random.state
        g = s.engine.word_grid
        self.assertEqual((g.problem.words, g.starts, g.initial_starts), ([], [], 0))
        self.assertEqual((g.problem.failure_next, g.problem.success_next), (-1, 1))
        play_phase(s)
        for _ in range(8): s.tick(250)
        self.assertEqual((g.problem_index, g.round_ms, g.remaining_ms, g.score), (0, 1000, 2000, 0))
        s.answer(); play_phase(s)
        self.assertEqual(g.problem_index, 1)
        for _ in range(4): s.tick(250)  # Let the exercise time out normally.
        play_phase(s)
        self.assertEqual((g.problem_index, g.problem.words, g.starts), (2, [], []))
        saved = json.loads(json.dumps(s.snapshot()))
        s = Session.from_snapshot(r, saved); g = s.engine.word_grid
        self.assertEqual(json.loads(json.dumps(s.snapshot())), saved)
        # Fixed letters consume no random draws, but committing the exercise
        # shuffles its one valid start's highlight offset once.
        expected_random = NativeRandom(initial_random); expected_random.next()
        self.assertEqual(s.engine.random.state, expected_random.state)
        s.answer(); play_phase(s)
        self.assertEqual(g.problem_index, 3)
        self.assertTrue(g.problem.show_hints)
        s.grid_pointer('down', 0); s.grid_pointer('move', 1); s.grid_pointer('move', 2)
        self.assertEqual(g.score, 100)
        play_phase(s)
        self.assertEqual((g.problem_index, g.starts), (4, []))
        self.assertEqual(s.vm.snapshot(), held)
        s.answer(); play_phase(s)
        self.assertFalse(g.tutorial)
        self.assertEqual(g.score, 0)
        self.assertGreaterEqual(len(g.starts), 1)
        s.engine.result_cells[0] = 19
        for _ in range(160):
            action = s.tick(250)
            if action.name != 'word_grid': break
        self.assertEqual(action.request.args, (0,))  # No points in the timed game.
        self.assertEqual(s.engine.result_cells[0], 19)

    def test_playable_grids_and_reachable_tutorial_links_still_require_valid_data(self):
        for targets in ('', ' | ', '\xa0cat', 'catcatcat'):
            with self.subTest(targets=targets):
                s = Session(resources(targets=targets)); before = copy.deepcopy(s.engine)
                with self.assertRaises(ValueError): s.advance()
                self.assertEqual(s.engine, before)
                self.assertEqual(s.vm.pending.yield_id, 96)
        s = Session(tutorial_resources()); s.advance()
        for index, field, value in ((1, 'words', []), (1, 'failure_next', -1),
                                     (0, 'success_next', -1), (0, 'failure_next', 999)):
            invalid = copy.deepcopy(s.engine.word_grid)
            setattr(invalid.tutorials[index], field, value)
            with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                invalid.validate_config()

    def test_native_random_uses_full_product_and_signed_absolute_value(self):
        r = NativeRandom(1)
        self.assertEqual(r.next(), 16838)
        self.assertEqual(r.state, 1103527590)
        # High multiplication bits must survive; ANSI rand() returns 5758 here.
        self.assertEqual(r.next(), 1507104382)
        self.assertEqual(r.state, 2524885223)

    def test_diagonal_paths_no_reuse_and_cumulative_start_score(self):
        s = Session(resources(tutorial=True)); s.advance(); play_phase(s)
        g = s.engine.word_grid
        self.assertEqual(g.board, list('catcat'))
        self.assertEqual(g.starts, [0, 3])
        held = s.vm.snapshot()
        s.grid_pointer('down', 0)
        s.grid_pointer('move', 2)  # Cannot jump over the middle tile.
        self.assertEqual(g.selection, [0])
        s.grid_pointer('move', 4)  # Diagonal C -> A.
        s.grid_pointer('move', 0)  # Cannot revisit the C.
        self.assertEqual(g.selection, [0, 4])
        s.grid_pointer('move', 2)  # Diagonal A -> T; submit without mouse-up.
        self.assertEqual((g.score, g.starts), (100, [3]))
        self.assertEqual(g.selection, [])
        # The word's cells are kept for the HD presentation; they are not part of a save.
        self.assertEqual((g.found_cells, g.found_serial), ([0, 4, 2], 1))
        self.assertNotIn('found_cells', s.snapshot()['engine']['word_grid'])
        self.assertEqual(s.engine.sound_ids, [8110, 8111])
        s.grid_pointer('up')
        # Previously used starting cell cannot score a second time.
        for event, i in [('down', 0), ('move', 1), ('move', 2), ('up', None)]:
            s.grid_pointer(event, i)
        self.assertEqual(g.score, 100)
        for event, i in [('down', 3), ('move', 1), ('move', 5)]:
            s.grid_pointer(event, i)
        self.assertEqual(g.score, 300)
        self.assertEqual(g.phase, 3)
        self.assertEqual(s.vm.snapshot(), held)
        for _ in range(5): s.tick(250)
        self.assertFalse(g.tutorial)
        self.assertEqual(g.score, 0)  # Tutorial points are cleared on entering play.

    def test_clocks_callback_and_result_cells_are_distinct(self):
        for score, expected in [(100, 0), (200, 1)]:
            s = Session(resources());s.advance();g=s.engine.word_grid
            self.assertEqual(g.remaining_ms, 2000)
            s.tick(99999)
            self.assertEqual(g.phase_ms, 750)  # Native clamps a single frame to 250.
            self.assertEqual(g.remaining_ms, 2000)
            play_phase(s)
            g.score = score
            s.engine.result_cells[0] = 19
            for _ in range(160):
                a = s.tick(250)
                if a.name != 'word_grid': break
            self.assertEqual(a.request.args, (expected,))
            self.assertEqual(s.engine.result_cells[0], 19)
            self.assertIsNone(s.engine.word_grid)

    def test_save_mid_drag_and_continue_same_random_boards(self):
        r = resources(tutorial=True);s=Session(r);s.advance();play_phase(s)
        s.grid_pointer('down', 0);s.grid_pointer('move', 4)
        saved = json.loads(json.dumps(s.snapshot()))
        restored = Session.from_snapshot(r, saved)
        self.assertEqual(restored.snapshot(), s.snapshot())
        for stage, i in [('move', 2), ('up', None), ('down', 3), ('move', 4), ('move', 5), ('up', None)]:
            s.grid_pointer(stage, i);restored.grid_pointer(stage, i)
        for _ in range(80):
            s.tick(33);restored.tick(33)
            self.assertEqual(s.snapshot(), restored.snapshot())
        for key, value in [('board', []), ('selection', [0, 0]), ('starts', [2]),
                            ('order', [1]), ('remaining_ms', -1), ('score', -1)]:
            state = copy.deepcopy(saved); state['engine']['word_grid'][key] = value
            with self.subTest(key=key), self.assertRaises(SaveError): Session.from_snapshot(r, state)

    def test_generated_boards_are_solvable_and_restore_without_redrawing(self):
        for seed in range(30):
            s = Session(resources());s.engine.random=NativeRandom(seed);s.advance()
            g=s.engine.word_grid
            self.assertGreaterEqual(len(g.starts), 1)
            for start in g.starts:
                self.assertEqual(''.join(g.board[i] for i in g.find_path(start, 'cat')), 'cat')
            restored=Session.from_snapshot(s.resources,s.snapshot())
            self.assertEqual(restored.snapshot(),s.snapshot())

    @unittest.skipUnless(Path('.shs-library/library.json').exists(), 'user library absent')
    def test_actual_new_girl_grid_records(self):
        with ContentLibrary(Path('.shs-library')) as lib:
            r=lib.open_episode('The_New_Girl.exp');s=Session(r,start_script=25003)
            # Exercise the original frame-building instructions and original data
            # table directly; this is a diagnostic entry, not a production skip.
            s.vm.pc=75;s.vm._push(16362);s.vm.fp=0;s.engine.random=NativeRandom(1)
            a=s.advance();g=s.engine.word_grid
            self.assertEqual(a.name,'word_grid')
            self.assertEqual((g.duration_ms,g.target,g.round_limit_ms,g.bonus_ms),(45000,1800,10000,5000))
            self.assertEqual([p.words for p in g.problems],[['drive'],['avoid'],['careful']])
            self.assertEqual(g.board,list('beirvbrrbriievdd'))
            self.assertEqual(g.starts,[14])
            self.assertEqual(Session.from_snapshot(r,s.snapshot()).snapshot(),s.snapshot())
