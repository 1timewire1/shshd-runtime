"""Claire Hart plan Stage 0, P: story-object pictures (shshd-runtime service 225, asked for by service 70 selector 206). As
Classic's storyobjectmanager: a picture waits for the next line, shows in a row of framed squares along the bottom of the
dialogue box, and the row goes at the change of speaker after (or when the script empties it, or on Skip)."""
import json
from types import SimpleNamespace
import unittest

from exp_runtime.dialogue import STORY_OBJECT_GAP, STORY_OBJECT_MARGIN, STORY_OBJECT_SLOT, story_object_slots
from exp_runtime.engine import EngineState
from exp_runtime.runtime import Session
from exp_runtime.story_object_services import STORY_OBJECT, STORY_OBJECT_CLEAR, STORY_OBJECT_QUERY, STORY_OBJECT_ROW
from exp_runtime.ui_assets import Rect
from test_runtime import Resources, host_call, text_words
from test_vm import program


def story_resources():
    """Ann: a broom; Ann again with a key (the row grows); Bo (the row goes); a mug, then a clear, then Bo once more."""
    words, (ann, bo, one, two, three, four, five) = text_words('Ann', 'Bo', 'Look.', 'And this.', 'Hm.', 'Again.', 'Done.')
    return Resources(program(
        *host_call(STORY_OBJECT, 27001), *host_call(15, ann, one),
        *host_call(STORY_OBJECT, 27002), *host_call(15, ann, two),
        *host_call(15, bo, three),
        *host_call(STORY_OBJECT, 27003), *host_call(STORY_OBJECT, STORY_OBJECT_CLEAR & 0xffff), *host_call(15, bo, four),
        *host_call(STORY_OBJECT, 27004), *host_call(15, bo, five),
        0x33, words=words))


def rows(session, lines):
    shown = []
    for _ in range(lines):
        while session.pending is None or session.pending.name != 'dialogue':
            session.advance()
        line = session.pending
        shown.append(line.details.get('story_objects', []))
        for _ in range(4):                          # the box comes in and the letters type before a tap goes on
            if session.pending is not line:
                break
            session.tick(3000)
            session.answer()
    return shown


class StoryObjectTests(unittest.TestCase):
    def test_a_picture_shows_with_the_next_line_and_goes_at_the_change_of_speaker(self):
        session = Session(story_resources())
        self.assertEqual(rows(session, 5), [[27001], [27001, 27002], [], [], [27004]])

    def test_the_row_holds_eight_at_most(self):
        engine = EngineState()
        for picture in range(27000, 27010):
            engine.story_objects_due.append(picture) if len(engine.story_objects_due) < STORY_OBJECT_ROW else None
        self.assertEqual(len(engine.story_object_row(['Ann'])), STORY_OBJECT_ROW)
        engine.story_objects_due = [27100]
        self.assertEqual(len(engine.story_object_row(['Ann'])), STORY_OBJECT_ROW)       # a full row stays full

    def test_saves_keep_the_row_and_its_speaker(self):
        session = Session(story_resources())
        rows(session, 1)                                    # Ann's second line is up, with the broom and the key
        state = json.loads(json.dumps(session.snapshot()))
        self.assertEqual((state['version'], state['engine']['story_objects'], state['engine']['story_objects_due']),
                         (43, [27001, 27002], []))
        restored = Session.from_snapshot(story_resources(), state)
        self.assertEqual(rows(restored, 2), [[27001, 27002], []])
        old = json.loads(json.dumps(state))
        old['version'] = 42
        for key in ('story_objects_due', 'story_objects', 'story_objects_speaker'):
            del old['engine'][key]
        self.assertEqual(Session.from_snapshot(story_resources(), old).engine.story_objects, [])

    def test_skip_ahead_takes_them_away(self):
        from exp_runtime.skip_ahead import skip_ahead
        session = Session(story_resources())
        rows(session, 1)
        skip_ahead(session)
        self.assertEqual((session.engine.story_objects, session.engine.story_objects_due), ([], []))

    def test_cod_says_it_draws_them(self):
        from exp_runtime.cod.services import dispatch
        engine = EngineState()
        resumed = []
        vm = SimpleNamespace(pending=SimpleNamespace(yield_id=70, args=[STORY_OBJECT_QUERY], pc=0),
                             resume=resumed.append)
        action = dispatch(engine, vm)
        self.assertEqual((action.name, resumed), ('query_build', [1]))


class StoryObjectLayoutTests(unittest.TestCase):
    def test_squares_along_the_bottom_from_the_right(self):
        box = Rect(20, 300, 260, 80)
        grown, slots = story_object_slots(box, (27001, 27002, 27003))
        self.assertEqual(grown.height, 80 + STORY_OBJECT_SLOT + STORY_OBJECT_MARGIN)
        right = box.x + box.width - STORY_OBJECT_MARGIN
        self.assertEqual([r.x for _, r in slots],
                         [right - (3 - i) * STORY_OBJECT_SLOT - (2 - i) * STORY_OBJECT_GAP for i in range(3)])
        self.assertTrue(all(r.y + r.height == grown.y + grown.height - STORY_OBJECT_MARGIN for _, r in slots))

    def test_a_long_row_shares_the_width_and_a_narrator_box_widens(self):
        box = Rect(20, 300, 260, 80)
        _, slots = story_object_slots(box, tuple(range(8)))
        self.assertLess(slots[0][1].width, STORY_OBJECT_SLOT)
        self.assertGreaterEqual(slots[0][1].x, box.x + STORY_OBJECT_MARGIN - 1e-6)
        narrow, _ = story_object_slots(Rect(25, 115, 130, 40), (1, 2, 3, 4), widen=True)
        self.assertGreater(narrow.width, 130)


if __name__ == '__main__':
    unittest.main()
