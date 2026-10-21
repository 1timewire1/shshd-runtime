import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from exp_runtime.content import ContentLibrary
from exp_runtime.runtime import SaveError, Session
from exp_runtime.vm import VMError
from test_vm import program


def text_words(*strings):
    data, refs = bytearray(), []
    for text in strings:
        refs.append(len(data) // 2)
        data.extend(text.encode('latin-1') + b'\0')
        if len(data) % 2:
            data.append(0)
    return [int.from_bytes(data[i:i + 2], 'big') for i in range(0, len(data), 2)], refs


def host_call(service, *args):
    return [(0x1a, arg) for arg in args] + [(0x1f, service << 8 | len(args))]


def branching_program(timeout=0):
    words, (title, options, prompt, zero, one) = text_words('Choose', 'Left|Right', 'A fork.', 'Went left.', 'Went right.')
    return program(
        *host_call(1, title, options, prompt, timeout, 1, -1, -1, 0),
        0x21, (0x2a, 5),
        *host_call(13, zero, 0), (0x29, 18),
        *host_call(13, one, 0),
        *host_call(10, 25002, 0), 0x33, words=words, gap=2,
    )


class Resources:
    identity = dict(profile='authored-test', apk_sha256='a' * 64, episode_sha256='b' * 64)

    def __init__(self, first, second=None):
        self.programs = {25001: first, 25002: second or program(0x33)}
        self.record = dict(titles=['Original test story'])
        self.library = SimpleNamespace(directory=Path('.'))

    def program(self, resource_id):
        return self.programs[resource_id]

    def exists(self, resource_id):
        return False


def answer_screen(session, value=None):
    """Walk story fixtures through the real reveal gate before continuing."""
    while session.transitioning:
        session.tick(session.engine.scene_transition.duration_ms)
    if session.pending.name == 'choice' and not session.choice_ready:
        session.tick(250 - session.engine.choice_ms)
    if session.pending.name == 'presentation':
        session.tick(4000)
    if session.pending.name == 'dialogue' and not session.engine.dialogue_animation.complete:
        session.answer()  # Request completion without acknowledging the VM.
        session.tick(2000)
    action = session.answer(value)
    while session.transitioning:
        action = session.tick(session.engine.scene_transition.duration_ms)
    return action


class RuntimeTests(unittest.TestCase):
    def test_notice_after_minigame_is_deferred_to_next_dialogue(self):
        words, refs = text_words('New class', 'Story continues')
        r = Resources(program(*host_call(88, refs[0]), *host_call(13, refs[1], 0), 0x33, words=words))
        s = Session(r)
        self.assertEqual(s.advance().name, 'dialogue')
        self.assertEqual(s.engine.notice, 'New class')
        self.assertEqual(s.engine.next_dialogue_notice, '')
        self.assertEqual(s.engine.notice_ms, 1950)
        s.tick(800)
        restored = Session.from_snapshot(r, s.snapshot())
        self.assertEqual(restored.engine.notice_ms, 1150)
        restored.tick(1150)
        self.assertEqual(restored.engine.notice, '')
        self.assertEqual(restored.pending.name, 'dialogue')

    def test_save_choice_full_memory_and_actual_branches_then_scene_transition(self):
        resources = Resources(branching_program())
        session = Session(resources)
        session.engine.numbers[123] = -9
        session.vm.write_word(session.vm.stack_base + 1023, 2468)
        session.vm.write_word(len(session.vm.data) - 1, 1234)
        first = session.advance()
        self.assertEqual(first.name, 'choice')
        original = json.loads(json.dumps(session.snapshot()))
        with tempfile.TemporaryDirectory() as temporary:
            path = session.save(Path(temporary) / 'progress.shs-save.json')
            for option, line in ((0, 'Went left.'), (1, 'Went right.')):
                restored = Session.load(resources, path)
                self.assertEqual(json.loads(json.dumps(restored.snapshot())), original)
                self.assertEqual(restored.vm.read_word(restored.vm.stack_base + 1023), 2468)
                self.assertEqual(restored.vm.read_word(len(restored.vm.data) - 1), 1234)
                self.assertIsNone(restored.vm.a)
                self.assertIsNone(restored.vm.b)
                self.assertEqual(answer_screen(restored, option).details['text'], line)
                self.assertEqual(restored.engine.result_cells[0], option)
                self.assertEqual(answer_screen(restored).name, 'finished')
                self.assertEqual((restored.scene, restored.scene_loads), (25002, 1))
                self.assertEqual(restored.engine.numbers[123], -9)

    def test_timer_save_load_and_custom_return_values(self):
        resources = Resources(branching_program(timeout=1000))
        session = Session(resources)
        session.advance()
        self.assertEqual(session.tick(250).name, 'choice')
        restored = Session.from_snapshot(resources, session.snapshot())
        self.assertEqual(restored.remaining_ms, 750)
        self.assertEqual(restored.tick(750).name, 'choice')
        self.assertEqual(restored.remaining_ms, 0)
        restored = Session.from_snapshot(resources, restored.snapshot())
        self.assertEqual(restored.tick(0).name, 'choice')
        self.assertEqual(restored.tick(1).details['text'], 'Went right.')
        words, (title, prompt, left, right) = text_words('Pick', 'A question', 'No', 'Yes')
        p = program(*host_call(2, title, prompt, 1000, 0, -1, 0),
                    *host_call(3, left, 77, 0), *host_call(3, right, -999, 1),
                    *host_call(4, 0), 0x21, (0x1f, 0xfe01), words=words)
        resources = Resources(p)
        session = Session(resources)
        self.assertEqual(session.advance().details['values'], [77, 1])
        saved = session.snapshot()
        with self.assertRaises(ValueError):
            session.answer(0)
        self.assertEqual(session.snapshot(), saved)
        self.assertEqual(answer_screen(session, 1).request.args, (1,))
        other = Session.from_snapshot(resources, saved)
        self.assertEqual(other.tick(1001).request.args, (77,))

    def test_text_callback_dynamic_slot_and_pending_draft_survive_save(self):
        words, (title, prompt, default) = text_words('Name', 'Who are you?', 'Alex')
        resources = Resources(program(*host_call(17, title, prompt, default), 0x21,
                                      (0x1f, 0xfe01), words=words))
        session = Session(resources)
        session.advance().details['draft'] = 'Zoe'
        session = Session.from_snapshot(resources, json.loads(json.dumps(session.snapshot())))
        self.assertEqual(session.pending.details['draft'], 'Zoe')
        self.assertEqual(session.answer('Zoe').request.args, (0x7ff5,))
        self.assertEqual(session.engine.dynamic_strings[0], 'Zoe')
        self.assertEqual(session.engine.last_input, 'Zoe')

    def test_unsupported_service_cannot_be_acknowledged_or_autoplayed(self):
        session = Session(Resources(program(*host_call(254, 12, 34), 0x33)))
        action = session.advance()
        state = session.snapshot()
        self.assertEqual(action.name, 'unhandled_yield')
        with self.assertRaises(VMError):
            session.answer(0)
        self.assertIs(session.tick(10000), action)
        self.assertEqual(session.snapshot(), state)

    def test_save_content_version_frame_and_engine_types_are_validated(self):
        resources = Resources(branching_program())
        session = Session(resources)
        session.advance()
        original = session.snapshot()
        for path, value in ((('version',), 999), (('content', 'apk_sha256'), 'wrong'),
                            (('vm', 'pc'), 0), (('vm', 'sp'), 0),
                            (('vm', 'pending', 'yield_id'), 13),
                            (('engine', 'numbers'), {'1': 'not a word'}),
                            (('pending', 'name'), 'dialogue'), (('remaining_ms',), 30)):
            changed = copy.deepcopy(original)
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(SaveError):
                Session.from_snapshot(resources, changed)
        self.assertEqual(session.snapshot(), original)


class LocalGameTests(unittest.TestCase):
    library = Path(__file__).resolve().parents[1] / '.shs-library'

    @unittest.skipUnless((library / 'library.json').exists(), 'user-supplied local library is absent')
    def test_real_first_choice_save_and_two_native_branches(self):
        with ContentLibrary(self.library) as library:
            resources = library.open_episode('The_New_Girl.exp')
            session = Session(resources)
            action, count = session.advance(), 0
            while action.name in ('dialogue', 'presentation', 'vm_pause') and count < 100:
                action = answer_screen(session)
                count += 1
            self.assertEqual((session.scene, count, action.request.pc), (25002, 35, 316))
            self.assertEqual(action.name, 'choice')
            saved = json.loads(json.dumps(session.snapshot()))
            first, second = (Session.from_snapshot(resources, saved) for _ in range(2))
            left, right = answer_screen(first, 0), answer_screen(second, 1)
            self.assertEqual((left.request.pc, right.request.pc), (336, 352))
            self.assertNotEqual(left.details['text'], right.details['text'])
            for branch in (first, second):
                while branch.pending.name in ('dialogue', 'presentation', 'choice', 'vm_pause'):
                    answer_screen(branch, 0 if branch.pending.name == 'choice' else None)
                self.assertEqual((branch.pending.name, branch.pending.request.yield_id), ('word_game', 71))
