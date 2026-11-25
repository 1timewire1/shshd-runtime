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
                         (48, [27001, 27002], []))
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


def photos(session, lines):
    """The sequel's photo shown with each of `lines` lines (-1: none)."""
    shown = []
    for _ in range(lines):
        while session.pending is None or session.pending.name != 'dialogue':
            session.advance()
        line = session.pending
        shown.append(line.details.get('story_photo', -1))
        for _ in range(4):
            if session.pending is not line:
                break
            session.tick(3000)
            session.answer()
    return shown


class StoryPhotoTests(unittest.TestCase):
    """Secret in the Shadows' way (the profile's STORY_OBJECT_PHOTO, pack 31900; CLAIRE_HART_PLAN.md P): one photo at a time,
    shown with the next line and gone as the line after starts, a new one replacing it, whoever speaks."""

    def sequel(self):
        session = Session(story_resources())
        session.engine.story_photo_mode = True
        return session

    def test_a_photo_lasts_one_line_and_a_new_one_replaces_it(self):
        # (the story: the broom, Ann; the key, Ann; Bo; a mug then a clear, Bo; a picture 27004, Bo)
        self.assertEqual(photos(self.sequel(), 5), [27001, 27002, -1, -1, 27004])

    def test_it_never_draws_classics_row(self):
        session = self.sequel()
        while session.pending is None or session.pending.name != 'dialogue':
            session.advance()
        self.assertNotIn('story_objects', session.pending.details)

    def test_the_pack_turns_it_on(self):
        from exp_runtime.cod import profile
        self.assertEqual(profile.STORY_OBJECT_PHOTO, (31900,))
        self.assertFalse(Session(story_resources()).engine.story_photo_mode)      # (any other episode: Classic's row)

    def test_a_save_keeps_the_photo_and_an_older_save_shows_none(self):
        session = self.sequel()
        photos(session, 1)                                  # Ann's second line is up, with the key
        state = json.loads(json.dumps(session.snapshot()))
        self.assertEqual((state['version'], state['engine']['story_photo'], state['engine']['story_photo_due']),
                         (48, 27002, -1))
        restored = Session.from_snapshot(story_resources(), state)
        restored.engine.story_photo_mode = True
        self.assertEqual(photos(restored, 1), [27002])
        old = json.loads(json.dumps(session.snapshot()))
        old['version'] = 46
        for key in ('story_photo_due', 'story_photo', 'story_photo_lines'):
            old['engine'].pop(key)
        self.assertEqual(Session.from_snapshot(story_resources(), old).engine.story_photo, -1)


class StoryPhotoLayoutTests(unittest.TestCase):
    def test_the_line_after_names_the_photo_leaving(self):
        session = Session(story_resources())
        session.engine.story_photo_mode = True
        leaving = []
        for _ in range(5):
            while session.pending is None or session.pending.name != 'dialogue':
                session.advance()
            line = session.pending
            leaving.append(line.details.get('story_photo_leaving', -1))
            for _ in range(4):
                if session.pending is not line:
                    break
                session.tick(3000)
                session.answer()
        # (the broom shows; the key replaces it; the key goes as Bo speaks; the clear leaves nothing; 27004 shows)
        self.assertEqual(leaving, [-1, 27001, 27002, -1, -1])

    def test_the_photo_fits_whole_in_its_box(self):
        """Owner, 2026-11-24: tall photos were cut off (filled and cropped); each is shown whole, its shape kept."""
        import pygame
        from exp_runtime.desktop_dialogue import DialogueRenderer
        pygame.init()
        self.addCleanup(pygame.quit)
        pictures = {1: pygame.Surface((200, 100)), 2: pygame.Surface((60, 120)), 3: pygame.Surface((10, 8))}
        renderer = SimpleNamespace(image=pictures.get, _story_objects={})
        fit = lambda n: DialogueRenderer.story_photo_image(renderer, n, (79, 63)).get_size()     # noqa: E731
        self.assertEqual(fit(1), (79, 40))          # (a wide one: its width)
        self.assertEqual(fit(2), (32, 63))          # (a tall one: its height, where the game cut it)
        self.assertEqual(fit(3), (79, 63))          # (a small one grows to fit, as the four the game never drew)

    def test_it_slides_in_and_the_last_one_fades_out_on_the_lines_clock(self):
        from exp_runtime.desktop_dialogue import (DialogueRenderer, STORY_PHOTO_IN_MS, STORY_PHOTO_OUT_MS,
                                                  STORY_PHOTO_SLIDE)
        place = Rect(175, 180, 105, 106)
        page = SimpleNamespace(story_photo=(27002, place), story_photo_leaving=(27001, place))
        states = DialogueRenderer.story_photo_states
        (gone, _, _, gone_alpha), (new, _, shift, alpha) = states(page, 0)
        self.assertEqual((gone, gone_alpha, new, shift, alpha), (27001, 1, 27002, STORY_PHOTO_SLIDE, 0))
        middle = states(page, STORY_PHOTO_OUT_MS // 2)
        self.assertAlmostEqual(middle[0][3], .5)
        self.assertEqual([s[0] for s in states(page, STORY_PHOTO_OUT_MS)], [27002])        # (the old one is gone)
        self.assertEqual(states(page, STORY_PHOTO_IN_MS)[0][2:], (0., 1.))                 # (in place, opaque)
        renderer = SimpleNamespace()
        moving = lambda age: DialogueRenderer.story_photo_moving(renderer, page, SimpleNamespace(age_ms=age))
        self.assertTrue(moving(100))
        self.assertFalse(moving(STORY_PHOTO_IN_MS))                                         # (the line can rest)
