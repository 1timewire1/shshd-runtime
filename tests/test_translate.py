"""tools/translate: the KiWi call-site rewriter and the New Rules shims, on authored programs (no original content)."""
import importlib.util
from collections import Counter
from pathlib import Path
import struct
import sys
import unittest

from exp_runtime.decode.bytecode import OPERAND_OPCODES, decode_program
from exp_runtime.vm import KiwiVM, StopKind

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
from kiwi_rewrite import Rewriter  # noqa: E402

HAS_PIL = importlib.util.find_spec('PIL') is not None
HAS_NUMPY = importlib.util.find_spec('numpy') is not None


def text_words(text):
    data = text.encode('latin-1') + b'\0'
    data += b'\0' * (len(data) % 2)
    return [data[i] << 8 | data[i + 1] for i in range(0, len(data), 2)]


def program(*instructions, words=(), gap=0):
    code = bytearray()
    for item in instructions:
        op, arg = item if isinstance(item, tuple) else (item, None)
        code.append(op)
        if op in OPERAND_OPCODES:
            code.extend(struct.pack('>H', arg & 0xFFFF))
    header = b'kiwi\x02\x00\x00' + struct.pack('>4H', len(words), gap, 0, len(instructions))
    return decode_program(header + struct.pack(f'>{len(words)}H', *words) + code)


def call(service, argc):
    return (0x1F, service << 8 | argc)


def yields(prog, results=(), limit=50):
    """(service, args) of every yield until the program halts; each yield is answered from `results`, then 0."""
    vm, out, results = KiwiVM(prog), [], list(results)
    for _ in range(limit):
        stop = vm.run()
        if stop.kind == StopKind.HALT:
            return out
        out.append((stop.yield_id, stop.args))
        vm.resume(results.pop(0) if results else 0)
    raise AssertionError('program did not halt')


class RewriterTests(unittest.TestCase):
    def test_rename_keeps_arguments(self):
        source = program((0x1A, 5), (0x1A, 6), call(1, 2), 0x33)
        rewriter = Rewriter(source)
        (pc, service, argc), = rewriter.calls()
        rewriter.rename(pc, 22)
        self.assertEqual(yields(rewriter.finish()), [(22, (5, 6))])

    def test_shim_reorders_arguments_and_returns_the_new_service_result(self):
        # f(a, b) -> service 13 (b, a + 100); the original code then pushes R and passes it to service 99
        source = program((0x1A, 3), (0x1A, 4), call(40, 2), 0x21, call(99, 1), 0x33)
        rewriter = Rewriter(source)
        pc = rewriter.calls()[0][0]

        def build(s):
            s.arg(2); s.arg(1); s.push(100); s.emit(0x50); s.call(13, 2)
        rewriter.redirect(pc, 'swap', build)
        self.assertEqual(yields(rewriter.finish(), results=[7]), [(13, (4, 103)), (99, (7,))])

    def test_shared_shim_serves_every_site_and_select_maps_values(self):
        source = program((0x1A, 1), call(24, 1), (0x1A, 4), call(24, 1), (0x1A, 9), call(24, 1), 0x33)
        rewriter = Rewriter(source)
        for pc, _, _ in rewriter.calls():
            rewriter.redirect(pc, 'map', lambda s: (s.select(1, {1: 10, 4: 40}, -1), s.call(5, 1)))
        result = rewriter.finish()
        self.assertEqual(yields(result), [(5, (10,)), (5, (40,)), (5, (-1,))])
        self.assertEqual(len(rewriter.shims), 1)

    def test_prologue_runs_before_the_first_instruction(self):
        source = program((0x1A, 2), call(30, 1), 0x33)
        rewriter = Rewriter(source)
        rewriter.prologue(lambda s: (s.push(199), s.call(75, 1)))
        self.assertEqual(yields(rewriter.finish()), [(75, (199,)), (30, (2,))])

    def test_appended_text_is_addressable(self):
        source = program(call(8, 0), 0x33)
        rewriter = Rewriter(source)
        pc = rewriter.calls()[0][0]
        rewriter.redirect(pc, 'title', lambda s: (s.text('Hello'), s.call(8, 1)))
        result = rewriter.finish()
        (_, (address,)), = yields(result)
        vm = KiwiVM(result)
        self.assertEqual(struct.pack('>3H', *(vm.data[address + i] for i in range(3))), b'Hello\0')

    def test_zero_gap_makes_unwritten_words_read_as_zero(self):
        source = program((0x40, 1), call(9, 1), 0x33, words=[0], gap=4)       # reads gap word 1
        with self.assertRaises(Exception):
            yields(Rewriter(source).finish())                                 # SHS leaves the gap uninitialised
        self.assertEqual(yields(Rewriter(source, zero_gap=True).finish()), [(9, (0,))])


@unittest.skipUnless(HAS_PIL, 'tools/translate/nr_art.py needs Pillow')
class NewRulesShimTests(unittest.TestCase):
    def setUp(self):
        import newrules
        self.nr = newrules

    def translate_calls(self, source, names=None, music=True, primary=1):
        nr = self.nr
        rewriter = Rewriter(source, zero_gap=True)
        last_line = rewriter.words([-1])
        report = nr.Report()
        for pc, service, argc in rewriter.calls():
            if service in nr.RENAME:
                rewriter.rename(pc, nr.RENAME[service])
                continue
            nr.HANDLERS[service](rewriter, pc, argc, dict(
                last_line=last_line, rid=25001, bank_of={}, report=report, program=source,
                music={} if music else None, names=names or {}, primary=primary, service=service,
                keyboard_guards=nr.keyboard_guards(source), scores=Counter(),
                scene_players=nr.scene_players(source, names or {}, Counter())))
        return rewriter.finish(), report

    def test_mode_lines_keep_the_thought_prefix_and_drop_other_box_modes(self):
        words = text_words('hm.')
        source = program((0x1A, -2), (0x1A, 0), (0x1A, 3), call(40, 3),
                         (0x1A, -5), (0x1A, 0), (0x1A, 3), call(40, 3),
                         (0x1A, 0), (0x1A, 3), (0x1A, 4), call(40, 3), 0x33, words=words)
        result, _ = self.translate_calls(source)
        key = self.nr.PLAYER_KEY                                   # a thought makes its speaker the player
        self.assertEqual(yields(result), [(74, (3,)), (54, (key, 3)), (13, (-2, 0, 3)), (13, (0, 3)), (13, (0, 3, 1))])

    def test_named_lines_speak_as_the_character_or_under_the_name(self):
        empty, crowd = 0, 1
        words = [0] + text_words('crowd') + text_words('hey!')
        line = 1 + len(text_words('crowd'))
        source = program((0x1A, empty), (0x1A, line), (0x1A, 6), call(41, 3),
                         (0x1A, crowd), (0x1A, line), (0x1A, 6), (0x1A, 2), (0x1A, 7), (0x1A, 2), call(42, 6),
                         0x33, words=words)
        result, _ = self.translate_calls(source)
        self.assertEqual(yields(result), [(13, (line, 6)), (15, (crowd, line))])

    def test_named_line_with_the_characters_own_name_keeps_its_portrait(self):
        words = text_words('kel') + text_words('yo.')
        line = len(text_words('kel'))
        source = program((0x1A, 0), (0x1A, line), (0x1A, 6), (0x1A, 2), call(42, 4), 0x33, words=words)
        result, _ = self.translate_calls(source, names={'kel': {6}})
        self.assertEqual(yields(result), [(13, (line, 6, 2))])

    def test_music_plays_once_and_preload_mode_does_nothing(self):
        source = program((0x1A, 3), (0x1A, 1), call(7, 2), (0x1A, 3), (0x1A, 0), call(7, 2),
                         (0x1A, 4), (0x1A, 2), call(7, 2), 0x33)
        result, _ = self.translate_calls(source)
        base = self.nr.MUSIC_BASE
        self.assertEqual(yields(result), [(80, (base + 3, 0)), (80, (base + 4, 0))])
        result, _ = self.translate_calls(source, music=False)
        self.assertEqual(yields(result), [])

    def test_a_look_sets_the_bubble_theme_from_the_records_sex_and_hides_the_badge(self):
        nr = self.nr
        # look records: (owner, id, sex, slots...) at 0 (male) and 4 (female); service 25 points at the record
        source = program((0x1A, 3), (0x1A, 0), call(25, 2), (0x1A, 5), (0x1A, 4), call(25, 2), 0x33,
                         words=[3, 0, 1, 0, 5, 0, 0, 0])
        rewriter = Rewriter(source, zero_gap=True)
        report = nr.Report()
        for pc, service, argc in rewriter.calls():
            nr.look(rewriter, pc, argc, dict(rid=25001, bank_of={(25001, 0): 26200, (25001, 4): 26205}, report=report))
        self.assertEqual(yields(rewriter.finish()), [
            (52, (3, nr.THEME, 1)), (52, (3, nr.NO_BADGE, 1)), (72, (3, 26200)),
            (52, (5, nr.THEME, 2)), (52, (5, nr.NO_BADGE, 1)), (72, (5, 26205))])

    def test_timed_choices_keep_new_rules_padded_limit_and_time_out_to_the_first_option(self):
        # 12: (title, cursor interval, limit): the minigame rounds' jumping cursor (600) has no SHS counterpart
        source = program((0x1A, 0), (0x1A, 600), (0x1A, 3000), call(12, 3), (0x1A, 0), (0x1A, -1), (0x1A, -1),
                         call(12, 3), 0x33, words=text_words('think!'))
        result, _ = self.translate_calls(source)
        out = yields(result, results=[7, 0, 7, 0])                   # the current player (PLAYER_KEY) is 7
        title, key = out[1][1][0], self.nr.PLAYER_KEY
        self.assertEqual(out, [(55, (key,)), (2, (title, 0, 3900, 0, 7, 1)), (55, (key,)), (2, (title, 0, -1, 0, 7, 1))])

    def test_a_choice_titled_with_a_name_makes_that_character_the_player(self):
        words = text_words('mallika') + text_words('put on the pheromones.|no way.')
        source = program((0x1A, 0), (0x1A, len(text_words('mallika'))), (0x1A, -1), (0x1A, -1), call(11, 4), 0x33,
                         words=words)
        rewriter = Rewriter(source, zero_gap=True)
        last_line = rewriter.words([-1])
        (pc, _, argc), = rewriter.calls()
        self.nr.choice(rewriter, pc, argc, dict(program=source, names={'mallika': {5}}, scores=Counter(),
                                                last_line=last_line))
        out = yields(rewriter.finish())
        key = self.nr.PLAYER_KEY
        self.assertEqual(out[:2], [(74, (5,)), (54, (key, 5))])
        self.assertEqual(out[2][0], 1)
        self.assertEqual(out[2][1][2], -1)            # the description is the last line shown, not "Mallika"
        self.assertEqual(out[2][1][5], 5)             # Mallika's portrait

    def test_the_narrator_hands_over_the_player(self):
        lines = ['jake rushes in, where kim is waiting.', "play as her, and see if you can fix it!",
                 'play as jake and find out!', 'which guy do you want to play as next?']
        words, code = [], []
        for line in lines:
            code += [(0x1A, len(words)), call(43, 1)]
            words += text_words(line)
        source = program(*code, 0x33, words=words)
        found = self.nr.announcements(source, {'kim': {0}, 'jake': {3}}, Counter(), {0: 0, 3: 1})
        self.assertEqual(sorted(found.values()), [0, 3])       # her: Kim, not Jake; "play as next" names no one

    def test_a_round_of_jumping_cursor_choices_becomes_a_word_game(self):
        # a round function: two choices of a good (0) and a bad (1) answer, counting good answers in a word -> B
        words = text_words('think!') + text_words('yes!') + text_words('um...') + [0]
        yes, um, count = 4, 7, len(words) - 1
        one_round = [(0x1A, 0), (0x1A, 600), (0x1A, 3000), call(12, 3),
                     (0x1A, yes), (0x1A, 0), (0x5b, None), (0x5a, None), call(13, 4),
                     (0x1A, um), (0x1A, 1), (0x5b, None), (0x5a, None), call(13, 4),
                     (0x5b, None), call(14, 1), 0x21, (0x1A, 1), 0x0e, (0x2b, 7),        # R < 1: a good answer
                     (0x1A, count), (0x40, count), (0x1A, 1), 0x50, 0x3e, 0x15]           # count += 1
        source = program((0x42, None), (0x29, 4), 0x33, 0x33,                            # main: call it, halt
                         (0x48, None), (0x4a, None), *one_round, *one_round,             # 4: the round function
                         (0x40, count), 0x04, 0x22, 0x43, words=words)
        nr = self.nr
        found = nr.word_games(source)
        self.assertEqual(found, {4: nr.WordGame(2, 0, [yes], [um])})
        rewriter = Rewriter(source, zero_gap=True)
        rewriter.replace_function(4, 'game', lambda s: nr.word_game(s, source, found[4]))
        result = rewriter.finish()
        for score, good in ((6, 2), (3, 1), (0, 0)):
            vm, calls = KiwiVM(result), []
            while (stop := vm.run()).kind != StopKind.HALT:
                calls.append((stop.yield_id, stop.args))
                vm.resume(score if stop.yield_id == 71 else 5)
            self.assertEqual(vm.b, good)
        title, description, good_words, bad_words, *rest = calls[1][1]
        text = lambda address: bytes(b for w in vm.data[address:address + 40] for b in (w >> 8, w & 255)).split(b'\0')[0]
        self.assertEqual((calls[0], calls[1][0], text(good_words), text(bad_words), rest),
                         ((55, (nr.PLAYER_KEY,)), 71, b'yes!|yes!', b'um...|um...|um...', [20000, 5, 1, 3000]))

    def test_platform_query_answers_like_the_smartphone_versions(self):
        # 32(1) == 1: New Rules' own choice rounds instead of the arena; 2 only where it guards typing a name (49)
        def answer(*after):
            result, _ = self.translate_calls(program((0x1A, 1), call(32, 1), 0x21, call(15, 1), *after, 0x33,
                                                     words=text_words('name')))
            return yields(result)[0]
        self.assertEqual(answer(), (54, (1,)))
        self.assertEqual(answer((0x1A, 0), (0x1A, 0), (0x1A, 0), call(49, 3)), (54, (2,)))

    def test_new_rules_own_character_keys_move_out_of_the_dialogue_theme(self):
        source = program((0x1A, 2), (0x1A, 630), (0x1A, 1), call(22, 3),            # shared key: kept
                         (0x1A, 2), (0x1A, 652), call(23, 2),                          # constant own key
                         (0x1A, 2), (0x40, 0), (0x1A, 9), call(22, 3),                 # computed key 651
                         (0x1A, 2), (0x40, 1), (0x1A, 9), call(22, 3), 0x33,           # computed key 630
                         words=[651, 630])
        result, _ = self.translate_calls(source)
        self.assertEqual(yields(result), [(52, (2, 630, 1)), (53, (2, 31652)), (52, (2, 31651, 9)),
                                          (52, (2, 630, 9))])

    def test_location_pictures_follow_the_time_of_day(self):
        nr = self.nr
        source = program((0x1A, 4), (0x1A, 2), call(35, 2), (0x1A, -1), (0x1A, 3), call(35, 2), 0x33)
        result, _ = self.translate_calls(source)
        vm, out, mode = KiwiVM(result), [], 0
        for _ in range(20):
            stop = vm.run()
            if stop.kind == StopKind.HALT:
                break
            out.append((stop.yield_id, stop.args))
            if stop.yield_id == 54:
                mode = stop.args[1]
            vm.resume(mode if stop.yield_id == 55 else 0)               # the global number store, as SHS keeps it
        base, modes = nr.BACKGROUND_BASE, nr.MODES
        self.assertEqual([x for x in out if x[0] == 11], [(11, (0, base + modes * 2 + 4)), (11, (0, base + modes * 3 + 4))])
        episode = nr.Episode(1, 'Test', {25001: source})
        self.assertEqual(nr.used_scenes(episode), {(2, 4), (3, 0)})

    def test_choice_hints_know_the_translated_jingles(self):
        from exp_runtime.shs import profile
        nr = self.nr
        self.assertEqual(profile.TRANSLATED_FEEDBACK_MUSIC[nr.PACK_ID],
                         {nr.MUSIC_BASE + track: feedback for track, feedback in nr.FEEDBACK_TRACKS.items()})

    def test_achievement_beats_become_notices(self):
        notice = self.nr.NOTICE
        for text in ('good answer!', 'handle approved!', 'exhibit successful!', 'Clue Acquired!'):
            self.assertTrue(notice.match(text), text)
        for text in ('and misses!', "that's right!", 'to be continued!', 'smash!', 'the fight begins!'):
            self.assertFalse(notice.match(text), text)
        words = text_words('item obtained!')
        result, report = self.translate_calls(program((0x1A, 0), call(43, 1), 0x33, words=words))
        self.assertEqual((yields(result), report.notices), ([(88, (0,))], 1))

    def test_protagonist_counts_thought_lines_more(self):
        lines = [((0x1A, 0), (0x1A, 5), call(40, 2))] * 5 + [((0x1A, -2), (0x1A, 0), (0x1A, 2), call(40, 3))] * 2
        source = program(*[i for group in lines for i in group], 0x33, words=text_words('x'))
        episode = self.nr.Episode(1, 'Test', {25001: source})
        self.assertEqual(self.nr.protagonist(episode), 2)              # 2 thoughts x 4 beat 5 lines
        self.assertEqual(self.nr.protagonist(self.nr.Episode(1, 'Empty', {25001: program(0x33)})),
                         self.nr.PLAYER)


class CasingTests(unittest.TestCase):
    def test_learned_forms_and_sentence_case(self):
        import casing
        dictionary = casing.learn([(['i met hector at the mall.'], ['I met Hector at the mall.'])])
        self.assertEqual(casing.apply('hector? he left. bye, hector', dictionary), 'Hector? He left. Bye, Hector')
        unknown = Counter()
        self.assertEqual(casing.apply('zorp is here', dictionary, unknown=unknown), 'Zorp is here')
        self.assertEqual(unknown, Counter({'zorp': 1, 'is': 1, 'here': 1}))     # unseen words go on the review list
        self.assertEqual(casing.apply('the h.e.c.t.o.r. method.', dictionary), 'The H.E.C.T.O.R. method.')
        self.assertEqual(casing.apply('the capital of new hampshire? concord.', dictionary),
                         'The capital of New Hampshire? Concord.')
        self.assertEqual(casing.headline_case('Bonus scene!'), 'Bonus Scene!')
        self.assertEqual(casing.apply('an episode of `surviving high school!`', dictionary),
                         'An episode of `Surviving High School!`')
        self.assertEqual(casing.headline_case('the prince plot, part one'), 'The Prince Plot, Part One')
        self.assertEqual(casing.headline_case('a night at the opera'), 'A Night at the Opera')


@unittest.skipUnless(HAS_NUMPY, 'tools/translate/midi_render.py needs numpy')
class MidiTests(unittest.TestCase):
    def test_notes_and_tempo(self):
        import midi_render
        track = bytes([0x00, 0xFF, 0x51, 0x03, 0x07, 0xA1, 0x20,          # 500000 us per quarter
                       0x00, 0xC0, 0x05, 0x00, 0x90, 60, 100,              # program 5, note on
                       0x60, 0x80, 60, 0, 0x00, 0xFF, 0x2F, 0x00])         # 96 ticks later: off; end
        data = (b'MThd' + struct.pack('>IHHH', 6, 0, 1, 96) + b'MTrk' + struct.pack('>I', len(track)) + track)
        song = midi_render.parse_midi(data)
        self.assertEqual(song.notes, [(0.0, 0.5, 0, 60, 100)])
        self.assertEqual(song.controls, [(0.0, 0, 'program', 5)])
        self.assertAlmostEqual(song.duration, 0.5)


if __name__ == '__main__':
    unittest.main()
