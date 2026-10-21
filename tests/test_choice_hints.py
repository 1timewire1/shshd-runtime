from pathlib import Path
import unittest

from exp_runtime.choice_hints import preview_choices
from exp_runtime.runtime import Session
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program


def choice_session(first, second=(), *, ending=(0x33,), custom=False):
    words, refs = text_words('Choose', 'Left|Right', 'Question', 'Reply', 'Score Up!',
                            'Detective Score Up!', 'Left', 'Right')
    if custom:
        prefix = (host_call(2, refs[0], refs[2], 3000, 0, -1, 0)
                  + host_call(3, refs[6], 73, 1) + host_call(3, refs[7], -73, 1)
                  + host_call(4, 1))
        check = [0x21, (0x1a, 73), 0x0b]  # != 73, independent of shuffled index.
    else:
        prefix = host_call(1, refs[0], refs[1], refs[2], 3000, 0, -1, -1, 0)
        check = [0x21]
    first, second = first(refs), second(refs) if callable(second) else list(second)
    branch_at = len(prefix) + len(check)
    second_at = branch_at + 1 + len(first) + len(ending)
    p = program(*prefix, *check, (0x2a, second_at - branch_at), *first, *ending,
                *second, *ending, words=words)
    s = Session(Resources(p)); s.advance()
    return s


def kinds(session, **kwargs):
    return [hint.kind for hint in preview_choices(session, **kwargs)]


def deferred_session(*, custom=False, threshold=2, reward=True, mixed=False):
    """Authored three-question quiz with one reward after the whole sequence."""
    words, refs = text_words('Choose', 'Left|Middle|Right', 'Question',
                            'Left', 'Middle', 'Right', 'Score Up!')
    counter = len(words)
    words.append(0)
    code = []
    values = (73, -20, 5) if custom else (0, 1, 2)
    for answer in (2, 0, 2):
        if custom:
            code += host_call(2, refs[0], refs[2], 0, 0, -1, 0)
            for text, value in zip(refs[3:6], values):
                code += host_call(3, text, value, 1)
            code += host_call(4, 1)
        else:
            code += host_call(1, refs[0], refs[1], refs[2], 0, 0, -1, -1, 0)
        code += [0x21, (0x1a, values[answer]), 0x0b, (0x2a, 3), (0x01, counter), 0x25]
    gain = (host_call(88, refs[6]) + host_call(52, 2, 407, 1)) if reward else []
    if mixed:
        gain += host_call(52, 3, 407, -1)
    code += [(0x40, counter), (0x1a, threshold), 0x0e, (0x2a, len(gain) + 1), *gain, 0x33]
    s = Session(Resources(program(*code, words=words)))
    s.advance()
    return s, values


class ChoiceHintTests(unittest.TestCase):
    def test_further_sd_score_notices_count_as_gain_and_loss(self):
        # shshd-runtime: "Score Way Up!" is a gain and "Detective Score Down!" a loss; track notices stay unknown.
        for left, right, expected in (('Score Way Up!', 'Nerd Approval Up!', ['gain', 'no_gain']),
                                      ('Detective Score Down!', 'Nerd Approval Up!', ['loss', 'no_gain'])):
            with self.subTest(left=left):
                words, refs = text_words('Choose', 'Left|Right', 'Question', left, right)
                prefix = host_call(1, refs[0], refs[1], refs[2], 3000, 0, -1, -1, 0)
                first, second = host_call(88, refs[3]), host_call(88, refs[4])
                branch_at = len(prefix) + 1
                second_at = branch_at + 1 + len(first) + 1
                s = Session(Resources(program(*prefix, 0x21, (0x2a, second_at - branch_at), *first, 0x33,
                                              *second, 0x33, words=words)))
                s.advance()
                hints = kinds(s)
                self.assertEqual(hints[0], expected[0])
                self.assertIn(hints[1], ('no_gain', 'unknown'))

    def test_cod_feedback_marks_survival_and_failure_branches_without_score_notices(self):
        for custom in (False, True):
            s = choice_session(lambda refs: host_call(79, 8002) + host_call(13, refs[3], 0),
                               lambda refs: host_call(79, 8001) + host_call(13, refs[3], 0), custom=custom)
            s.engine.game_key = 'cod'
            before = s.snapshot()
            correct = 73 if custom else 0
            self.assertEqual(kinds(s), ['gain' if v == correct else 'loss'
                                       for v in s.pending.details['values']])
            self.assertEqual(s.snapshot(), before)
        # Neither another game's cues, music requests, nor a stale cue proves
        # the outcome of this choice. Unknown calls still stop the preview.
        for first, second in ((host_call(79, 8003), host_call(79, 8004)),
                              (host_call(80, 8002, 0), host_call(80, 8001, 0)),
                              (host_call(79, 8002) + host_call(254), host_call(254))):
            s = choice_session(lambda _: first, second)
            s.engine.game_key = 'cod'
            s.engine.sound_id = 8002
            self.assertEqual(kinds(s), ['unknown', 'unknown'])

    def test_quiz_feedback_sounds_mark_shuffled_answers_without_score_notices(self):
        for custom in (False, True):
            s = choice_session(lambda refs: host_call(79, 8007) + host_call(13, refs[3], 0),
                               lambda refs: host_call(79, 8003) + host_call(13, refs[3], 0), custom=custom)
            s.tick(250)
            before = s.snapshot()
            correct = 73 if custom else 0
            expected = ['gain' if value == correct else 'loss' for value in s.pending.details['values']]
            self.assertEqual(kinds(s), expected)
            self.assertEqual(s.snapshot(), before)
            restored = Session.from_snapshot(s.resources, before)
            self.assertEqual(kinds(restored), expected)
            # Answer through the real callback; the preview did not play sound
            # or consume the timer, callback, shuffle or original VM branch.
            s.answer(s.pending.details['values'].index(correct))
            self.assertEqual(s.engine.sound_id, 8007)

    def test_quiz_feedback_respects_game_service_and_preview_boundaries(self):
        s = choice_session(lambda _: host_call(79, 8007), lambda _: host_call(79, 8003))
        s.engine.game_key = 'cod'
        self.assertEqual(kinds(s), ['unknown', 'unknown'])
        music = choice_session(lambda _: host_call(80, 8007, 0), lambda _: host_call(80, 8003, 0))
        self.assertEqual(kinds(music), ['unknown', 'unknown'])
        unrelated = choice_session(lambda _: host_call(79, 8010), lambda _: host_call(79, 8011))
        unrelated.engine.sound_id = 8007
        self.assertEqual(kinds(unrelated), ['unknown', 'unknown'])
        stopped = choice_session(lambda _: host_call(79, 8007) + host_call(254, 42),
                                 lambda _: host_call(79, 8003) + host_call(254, 42))
        self.assertEqual(kinds(stopped), ['unknown', 'unknown'])
        mixed = choice_session(lambda _: host_call(79, 8007) + host_call(79, 8003))
        self.assertEqual(kinds(mixed), ['mixed', 'unknown'])
        s = choice_session(lambda _: host_call(79, 8007), lambda _: host_call(79, 8003))
        s.pending.details['enabled'][0] = False
        self.assertEqual(kinds(s), ['unknown', 'loss'])

    def test_deferred_quiz_compares_identical_later_answers_and_preserves_state(self):
        # Every first answer can still reach the reward. Only the correct one
        # improves the outcome for all matching continuations (two of three).
        for custom in (False, True):
            s, values = deferred_session(custom=custom)
            for answer in (2, 0):
                before = s.snapshot()
                expected = ['gain' if v == values[answer] else 'no_gain'
                            for v in s.pending.details['values']]
                self.assertEqual(kinds(s), expected)
                self.assertEqual(s.snapshot(), before)
                answer_screen(s, s.pending.details['values'].index(values[answer]))
            # Once the threshold is met, every final option earns the reward.
            self.assertEqual(kinds(s), ['gain'] * 3)

    def test_deferred_hints_leave_unproven_or_conflicting_outcomes_unknown(self):
        for options, budgets in ((dict(reward=False), {}), (dict(threshold=0), {}),
                                (dict(mixed=True), {}), ({}, dict(max_decisions=1)),
                                ({}, dict(max_branches=10))):
            s, _ = deferred_session(**options)
            before = s.snapshot()
            with self.subTest(options=options, budgets=budgets):
                self.assertEqual(kinds(s, **budgets), ['unknown'] * 3)
                self.assertEqual(s.snapshot(), before)

    def test_word_quiz_hints_follow_current_deal_and_preserve_runtime(self):
        from test_minigames import word_resources
        s = Session(word_resources()); s.advance(); s.tick(400)
        for _ in range(12):
            game = s.engine.word_game
            before = s.snapshot()
            self.assertEqual(kinds(s), ['gain' if w > 0 else 'loss' for w in game.weights])
            self.assertEqual(s.snapshot(), before)
            # A bad answer is still bad at score zero; identical words in the
            # two lists must not replace the actual shuffled weights.
            s.answer(game.weights.index(-1))
        self.assertEqual(game.score, 0)
        same = Session(word_resources(good='same|right', bad='same|wrong|bad'))
        same.advance()
        self.assertEqual(kinds(same), ['gain' if w > 0 else 'loss' for w in same.engine.word_game.weights])

    def test_score_feedback_in_ordinary_branches_without_touching_live_state(self):
        for marker in (4, 5):
            s = choice_session(lambda refs: host_call(88, refs[marker]) + host_call(13, refs[3], 0))
            before = s.snapshot()
            self.assertEqual(kinds(s), ['gain', 'no_gain'])
            self.assertEqual(s.snapshot(), before)
            self.assertEqual(s.remaining_ms, 3000)
            self.assertEqual(answer_screen(s, 0).name, 'dialogue')
            self.assertIn('Score Up!', s.engine.notice)

    def test_relationship_gain_loss_mixed_and_reset_on_exit(self):
        s = choice_session(lambda _: host_call(52, 2, 407, 1),
                           lambda _: host_call(52, 2, 407, -1), ending=host_call(7))
        self.assertEqual(kinds(s), ['gain', 'loss'])
        mixed = choice_session(lambda _: host_call(52, 2, 407, 1) + host_call(52, 3, 407, -1))
        self.assertEqual(kinds(mixed), ['mixed', 'unknown'])

    def test_unrelated_flags_ui_caches_and_quoted_feedback_do_not_imply_scores(self):
        s = choice_session(lambda refs: host_call(44, 2000, 99) + host_call(52, 2, 3001, 4)
                           + host_call(13, refs[4], 0))
        s.engine.notice = 'Score Up!'
        s.engine.next_dialogue_notice = 'Score Up!'
        self.assertEqual(kinds(s), ['unknown', 'unknown'])

    def test_unknown_calls_and_execution_limits_stay_unmarked(self):
        s = choice_session(lambda refs: host_call(88, refs[4]) + host_call(254, 42))
        held = s.snapshot()
        self.assertEqual(kinds(s), ['unknown', 'unknown'])
        self.assertEqual(s.snapshot(), held)
        long = choice_session(lambda refs: host_call(13, refs[3], 0) * 3 + host_call(88, refs[4]))
        self.assertEqual(kinds(long, max_panels=1), ['unknown', 'unknown'])
        loop = choice_session(lambda _: [(0x29, 0)])
        self.assertEqual(kinds(loop, max_steps=40), ['unknown', 'unknown'])

    def test_unmatched_future_decisions_stay_unknown(self):
        s = choice_session(lambda refs: host_call(1, refs[0], refs[1], refs[2], 0, 0, -1, -1, 0)
                           + host_call(88, refs[4]))
        self.assertEqual(kinds(s), ['unknown', 'unknown'])

    def test_shuffled_custom_values_disabled_options_and_rng_are_preserved(self):
        s = choice_session(lambda refs: host_call(27, 100) + host_call(88, refs[4]), custom=True)
        s.engine.scene_value = 20
        before = s.snapshot()
        expected = ['gain' if value == 73 else 'no_gain' for value in s.pending.details['values']]
        self.assertEqual(kinds(s), expected)
        self.assertEqual(s.snapshot(), before)
        index = s.pending.details['values'].index(73)
        s.pending.details['enabled'][index] = False
        self.assertEqual(kinds(s), ['unknown', 'unknown'])

    def test_scheduled_scene_uses_same_budget_and_preview_does_not_write_files(self):
        from unittest.mock import patch
        s = choice_session(lambda _: host_call(10, 25002, 0))
        words, refs = text_words('Score Up!')
        s.resources.programs[25002] = program(*host_call(88, refs[0]), 0x33, words=words)
        before = s.snapshot()
        with patch.object(Path, 'open', side_effect=AssertionError('Preview touched filesystem')):
            self.assertEqual(kinds(s), ['gain', 'no_gain'])
        self.assertEqual(s.snapshot(), before)

    def test_preview_crosses_loading_and_vm_pauses_without_losing_feedback(self):
        for prefix in ([0x32], host_call(91, 1), host_call(91, 0), [0x32, 0x32]):
            s = choice_session(lambda refs: prefix + host_call(88, refs[4]),
                               lambda _: [0x32] + host_call(79, 8003))
            before = s.snapshot()
            self.assertEqual(kinds(s), ['gain', 'loss'])
            self.assertEqual(s.snapshot(), before)
            self.assertEqual(kinds(s, max_panels=1),
                             ['unknown', 'loss'] if prefix == [0x32, 0x32] else ['gain', 'loss'])

    @unittest.skipUnless(Path('decomp/cod/Cause+of+Death+(World)+1.3.4.ipa').is_file()
                         and Path('decomp/cod/CoD Episodes/Volume_2.exp').is_file(),
                         'original user CoD IPA/Volume Two is unavailable')
    def test_original_cod_volume_two_fight_marks_the_death_branch(self):
        import tempfile
        from exp_runtime.content import ContentLibrary, import_game
        from test_runtime import answer_screen
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'library'
            import_game(Path('decomp/cod/Cause+of+Death+(World)+1.3.4.ipa'),
                        [Path('decomp/cod/CoD Episodes/Volume_2.exp')], path, game='cod')
            with ContentLibrary(path) as library:
                s = Session(library.open_episode('Volume_2.exp'))
                s.advance()
                # Use the episode's own chapter picker and live callbacks.
                route = iter((1, 0, 2, 0, 0))
                for _ in range(150):
                    if s.pending.name == 'choice':
                        if (s.scene, s.pending.request.pc) == (25006, 187):
                            break
                        answer_screen(s, next(route))
                    else:
                        answer_screen(s)
                else:
                    self.fail('The original opening fight was not reached')
                before = s.snapshot()
                self.assertEqual(kinds(s), ['gain', 'loss'])
                self.assertEqual(s.snapshot(), before)
                restored = Session.from_snapshot(s.resources, before)
                self.assertEqual(kinds(restored), ['gain', 'loss'])
                answer_screen(s, 1)
                for _ in range(50):
                    if s.pending.name == 'choice':
                        break
                    answer_screen(s)
                self.assertEqual((s.scene, s.pending.request.pc), (25006, 2080))


if __name__ == '__main__':
    unittest.main()
