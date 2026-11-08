"""SHS '11's Memory as a translated story calls it: the rounds the translator finds, the switch, skips, saves and the player's
inputs; and the reader of '11's interface objects that its art comes from."""
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from test_translate_shs11 import FIRST, HAS_PIL, call, program as program_of, push, setup_script, small, story_jar, text_words

if HAS_PIL:
    import shs11
    import shs11_story
    from exp_runtime.decode.bytecode import decode_program
    from exp_runtime.exp import ExpArchive
    from exp_runtime.runtime import SaveError, Session
    from exp_runtime.shs11_services import SHS11_MEMORY
    from exp_runtime.vm import KiwiVM, StopKind

N73_JAR = (Path(__file__).resolve().parents[2]
           / "reference/Other Games/Surviving High School '11 (Java)/Surviving High School 11 [240x320] (N73) (andrew-lviv.net).jar")


def memory_script(mode=0):
    """A script whose game is called as '11's are (the routine's arguments, then 49), jumping past the routine's call. Its
    words: the rounds' address at 1, the difficulties' at 2, two rounds, six difficulties, the rounds' text."""
    start = 3 + 4 + 12
    addresses, words = [], []
    for text in ('I wish I was an elf!', 'ELF', 'Cat!', 'CAT'):
        addresses.append(start + len(words))
        words += text_words(text)
    speeds = [word for level in range(1, 7) for word in (level * 100, level * 1000)]
    table = [3, 7, *addresses, *speeds, *words]
    site = [(0x28, 9), (0x1B, mode | 2 << 8), (0x40, 1), *push(2), *push(40), 0x42, (0x29, 11), (0x19, 5), 0x61, call(49, 0), 0x33,
            (0x1B, 20 | 10 << 8), (0x40, 2), call(51, 6), 0x43]
    return setup_script(*site, table=table), site.index(call(49, 0))


def resources(code):
    return SimpleNamespace(library=SimpleNamespace(game_id='shs', directory=Path('.')),
                           record={'titles': ['x'], 'pack_id': 31600, 'episode_id': 1},
                           identity=dict(profile='memory-test', episode_sha256='0' * 64),
                           program=lambda rid: code, exists=lambda rid: False, linked_program=lambda: None)


def built(mode=0):
    data, pc = memory_script(mode)
    res, story = story_jar(data, fallbacks={(FIRST, pc): shs11_story.OwnWords('Do it', 'Yes|Yep', 'No|Nope|Never')})
    return decode_program(ExpArchive(shs11_story.translate(res, story, None)).read(shs11_story.FIRST_SCRIPT))


def rounds_of(data, pc):
    program = decode_program(data)
    return shs11_story.memory_rounds(shs11_story.Rewriter(program), shs11.script_memory(data), program.instructions, pc)


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class StoryTests(unittest.TestCase):
    def session(self, switch=True):
        session = Session(resources(built()), ephemeral=True)
        session.nr_arena = switch
        session.advance()
        return session

    def test_the_call_gives_its_target_and_how_many_rounds(self):
        target, _table, rounds = rounds_of(*memory_script())
        self.assertEqual((target, rounds), (40, 2))

    def test_a_reflex_game_isnt_memory_and_plays_its_stand_in(self):
        self.assertIsNone(rounds_of(*memory_script(1)))
        asked = []
        vm = KiwiVM(built(1))
        for _ in range(20):
            stop = vm.run()
            if stop.kind == StopKind.HALT:
                break
            asked.append(stop.yield_id)
            vm.resume(0)
        self.assertIn(71, asked)
        self.assertNotIn(SHS11_MEMORY, asked)

    def test_with_the_switch_on_it_plays_memory_with_the_tutorial_first(self):
        session = self.session()
        self.assertEqual(session.pending.name, 'shs11_memory')
        game = session.engine.shs11_memory
        # (difficulty 2 reads its table's second row)
        self.assertEqual(game.rounds, [['I wish I was an elf!', 'ELF', 20, 10, 200, 2000], ['Cat!', 'CAT', 20, 10, 200, 2000]])
        self.assertEqual((game.target, game.clock_ms), (40, 60000))
        self.assertTrue(game.tutorial)
        self.assertTrue(session.engine.shs11_tutorial_seen)

    def run_game(self, query, stops_at, answer):
        """The services a game's call makes, answering service 70 with `query` and the game with `answer`; then its result."""
        vm = KiwiVM(built())
        calls = []
        for _ in range(40):
            stop = vm.run()
            if stop.kind == StopKind.HALT:
                break
            calls.append((stop.yield_id, tuple(stop.args)))
            vm.resume(query if stop.yield_id == 70 else answer if stop.yield_id == stops_at else 0)
        return calls, vm.result

    def test_a_game_has_the_smartphones_song_looping_and_fades_it_after_and_keeps_its_result(self):
        for answer in (2, 1, 0):
            calls, result = self.run_game(1, SHS11_MEMORY, answer)
            services = [service for service, _ in calls]
            self.assertLess(calls.index((80, (8201, 1))), services.index(SHS11_MEMORY))
            self.assertLess(services.index(SHS11_MEMORY), services.index(81))
            self.assertEqual(calls[services.index(81)], (81, (1000,)))
            self.assertEqual(result, answer)

    def test_a_stand_in_has_it_too(self):
        calls, result = self.run_game(0, 71, 6)
        services = [service for service, _ in calls]
        self.assertLess(calls.index((80, (8201, 1))), services.index(71))
        self.assertLess(services.index(71), services.index(81))
        self.assertEqual(result, 2)

    def test_the_old_word_game_has_it_too_and_its_score_still_reaches_the_story(self):
        res, story = story_jar(setup_script(*push(0, 0, 0, 5000), call(25, 4), 0x21, 0x04))
        vm = KiwiVM(decode_program(ExpArchive(shs11_story.translate(res, story, None)).read(shs11_story.FIRST_SCRIPT)))
        calls = []
        for _ in range(40):
            stop = vm.run()
            if stop.kind == StopKind.HALT:
                break
            calls.append(stop.yield_id)
            vm.resume(7 if stop.yield_id == 71 else 0)
        self.assertLess(calls.index(80), calls.index(71))
        self.assertLess(calls.index(71), calls.index(81))
        self.assertEqual(vm.b, 7)

    def test_the_song_and_its_stop_arent_also_placed_on_the_line_after(self):
        words = text_words('Hello') + text_words('Goodbye')
        hello, bye = 0, len(text_words('Hello'))
        twin = shs11_story.ExpArchive(shs11_story.encode_exp({25002: program_of(
            *push(hello, 61), call(13, 2), *push(8201, 1), call(80, 2), *push(1000), call(81, 1), *push(8205, 0), call(80, 2),
            *push(bye, 61), call(13, 2), 0x33, words=words)}))
        _, say = text_words('Hello'), None
        res, story = story_jar(setup_script(*push(hello + 1, 61), call(24, 2)))
        plan, lost = shs11_story.smartphone_music(res, story, twin)
        placed = [c for spots in plan.values() for calls in spots.values() for c in calls]
        self.assertNotIn((80, 8201, 1), placed)
        self.assertNotIn((81, 1000), placed)
        self.assertNotIn((80, 8201, 1), lost)
        self.assertNotIn((81, 1000), lost)

    def test_with_the_switch_off_it_plays_what_the_smartphone_has(self):
        session = self.session(False)
        self.assertEqual(session.pending.name, 'word_game')
        self.assertIsNone(session.engine.shs11_memory)

    def test_a_skip_gives_the_story_2_or_0(self):
        for success, result in ((True, 2), (False, 0)):
            session = self.session()
            self.assertTrue(session.minigame_unstarted)
            session.skip_minigame(success)
            self.assertIsNone(session.engine.shs11_memory)
            self.assertEqual(session.vm.result, result)

    def test_it_counts_as_started_once_it_has_ticked(self):
        session = self.session()
        session.tick(10)
        self.assertFalse(session.minigame_unstarted)

    def test_it_saves_and_comes_back_as_it_was(self):
        session = self.session()
        session.answer(None)
        session.tick(1000)
        state = json.loads(json.dumps(session.snapshot()))
        self.assertEqual(state['version'], 39)
        again = Session.from_snapshot(resources(built()), state)
        self.assertEqual(again.pending.name, 'shs11_memory')
        self.assertEqual(again.engine.shs11_memory, session.engine.shs11_memory)

    def test_a_damaged_save_is_refused(self):
        state = json.loads(json.dumps(self.session().snapshot()))
        state['engine']['shs11_memory']['phase'] = 'nope'
        with self.assertRaises(SaveError):
            Session.from_snapshot(resources(built()), state)

    def test_digits_a_cursor_and_a_tap_pick_cells_and_the_boxes_take_any_press(self):
        import pygame
        from exp_runtime.desktop import Desktop
        from exp_runtime.shs11_games import PLAY
        pygame.init()
        pygame.display.set_mode((768, 1024))
        session = self.session()
        session.answer = Mock(wraps=session.answer)
        ui = Desktop(session, audio=False)
        key = lambda code: SimpleNamespace(key=code)
        game = session.engine.shs11_memory
        self.assertTrue(ui._memory_key(key(pygame.K_RETURN)))
        session.answer.assert_called_with(None)
        game.phase, game.word, game.order, game.shows = PLAY, 'ELF', [0, 1, 2], [1] * 9
        self.assertTrue(ui._memory_key(key(pygame.K_5)))
        session.answer.assert_called_with(4)
        self.assertTrue(ui._memory_key(key(pygame.K_RIGHT)))
        self.assertTrue(ui.shs11_memory_renderer.cursor_shown)
        self.assertEqual(ui.shs11_memory_renderer.cursor, 5)
        self.assertTrue(ui._memory_key(key(pygame.K_SPACE)))
        session.answer.assert_called_with(5)
        self.assertFalse(ui._memory_key(key(pygame.K_F1)))
        ui.bg_viewport = pygame.Rect(0, 0, 768, 1024)
        ui.shs11_memory_renderer.cell_at = lambda x, y: 7
        ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(300, 500)))
        session.answer.assert_called_with(7)

    def test_the_skip_prompt_says_the_score_it_takes_and_the_words(self):
        import pygame
        from exp_runtime.desktop import Desktop
        pygame.init()
        pygame.display.set_mode((768, 1024))
        session = self.session()
        ui = Desktop(session, audio=False)
        self.assertEqual(ui._minigame_summary(session.pending), 'Memory. Score 40 in 60 seconds. Words: ELF, CAT.')

    def badge_renderer(self, pack):
        import pygame
        from exp_runtime.desktop_dialogue import DialogueRenderer
        pygame.init()
        pygame.display.set_mode((64, 64))
        asked = []

        def image(asset):
            asked.append(asset)
            return pygame.Surface((41, 41), pygame.SRCALPHA)
        story = SimpleNamespace(library=SimpleNamespace(game_id='shs', kind='apk'), record={'pack_id': pack})
        return DialogueRenderer(story, None, image), asked

    def test_a_pack_with_its_own_relationship_icons_draws_them_at_shss_size(self):
        renderer, asked = self.badge_renderer(31600)
        icon = renderer.indicator_image(3010, 2)
        self.assertEqual(asked, [26992])
        self.assertEqual(icon.get_size(), (48, 48))
        self.assertIs(renderer.indicator_image(3010, 2), icon)
        self.assertEqual(asked, [26992])
        renderer.indicator_image(3016, 2)
        self.assertEqual(asked, [26992, 26996])

    def test_the_ring_under_a_new_icon_and_other_packs_stay_shss(self):
        renderer, _ = self.badge_renderer(31600)
        self.assertIsNone(renderer.translated_badge(3013, 2))
        renderer, _ = self.badge_renderer(31300)
        self.assertIsNone(renderer.translated_badge(3010, 2))

    @unittest.skipUnless(N73_JAR.is_file(), "needs the player's own '11 jar")
    def test_all_of_11s_games_are_called_the_same_way_and_11_are_memory_at_their_times(self):
        res = shs11.resources(shs11.jar_file(N73_JAR))
        found = []
        for story in shs11_story.STORIES.values():
            for script, pc in story.fallbacks:
                program = decode_program(res[script][1])
                at = max(i for i in range(pc) if program.instructions[i].opcode == 0x29)
                self.assertEqual(program.instructions[at - 5].opcode, 0x1b, (script, pc))
                real = rounds_of(res[script][1], pc)
                if real is not None:
                    found.append(real)
                    self.assertIn(real[0], (300, 350, 400))
                    self.assertEqual(real[2], 10)
        self.assertEqual(len(found), 11)


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class InterfaceReaderTests(unittest.TestCase):
    def reader(self, roots, objects, body):
        return shs11.UiReader(b'\0' + struct.pack('>I', 0) + struct.pack('>II', roots, objects) + body)

    def test_a_text_box_inside_a_container(self):
        text = b'Hi\0'
        body = (bytes([0, 68]) + b''.join(small(v) for v in (1, 2, 30, 40)) + b'\x01' + small(0) + small(0) + b'\0\0' + small(1)
                + bytes([0, 71]) + b''.join(small(v) for v in (3, 4, 5, 6)) + b'\x01'
                + b'\0' + small(len(text)) + text + small(1) + b'\0' + small(1) + b'\0')
        root = self.reader(1, 3, body).read()[0]
        self.assertEqual((root['x'], root['y'], root['w'], root['h']), (1, 2, 30, 40))
        self.assertEqual(root['children'][0]['text'], 'Hi')

    def test_a_kind_it_doesnt_read_says_so(self):
        with self.assertRaises(shs11.Shs11Error):
            self.reader(1, 1, bytes([0, 200])).read()

    def test_a_picture_takes_another_palette(self):
        png = b'head' + struct.pack('>I', 3) + b'PLTE' + b'abc' + b'crcc' + b'tail'
        swapped = shs11.with_palette(png, b'xyzwvu' + b'CRCC')
        self.assertEqual(swapped, b'head' + struct.pack('>I', 6) + b'PLTE' + b'xyzwvu' + b'CRCC' + b'tail')


if __name__ == '__main__':
    unittest.main()
