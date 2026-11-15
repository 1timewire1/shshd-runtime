"""Surviving Hollywood's full chapter (tools/translate shw_full.py; SURVIVING_HOLLYWOOD_ADDON_PLAN.md phase 3).

The translator's own rules run on authored text. The whole chapter is built and played only where the player's copy of the
demo's 240 x 320 jar is named by SHSHD_SHW_JAR (no original content is kept here): New Game to the month's end, with Where to?,
the quest journal, minigames and the exit. Line-for-line agreement with Tardy-Slip's engine is checked outside the suite
(reference/Other Games/tools/shw_ref.mjs and shw_compare.py)."""
import importlib.util
import os
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
HAS_PIL = importlib.util.find_spec('PIL') is not None
JAR = os.environ.get('SHSHD_SHW_JAR')


@unittest.skipUnless(HAS_PIL, 'needs Pillow')
class TranslatorRuleTests(unittest.TestCase):
    def test_a_places_hours_come_from_its_description(self):
        import shw_full
        self.assertEqual(shw_full.place_hours('beach hours:\n\n9am-9pm every day.\n\nhot sun and hot bodies...'),
                         '9am-9pm every day')
        self.assertEqual(shw_full.place_hours('open hours:\n\nmon-wed 12-9pm\nthu, fri, sun 12-6pm\nsat 9am-3pm\n\nmodest...'),
                         'Mon-Wed 12-9pm, Thu, Fri, Sun 12-6pm, Sat 9am-3pm')
        self.assertEqual(shw_full.place_hours('open 24 hrs, 7 days a week.\n\ncheck in your soft clay...'),
                         'Open 24 hrs, 7 days a week')
        self.assertEqual(shw_full.place_hours('your humble abode.'), '')        # home: no hours

    def test_a_rehearsal_asks_for_the_word_the_demo_counts_to(self):
        import shw_full
        self.assertEqual(shw_full.spelling_word('i am red, i am blue, i am all these to you.', 10), 'these')
        self.assertEqual(shw_full.spelling_word('oh glamlet, to thine own avocado, be faithful.', 8), 'faithful')

    def test_tables_that_read_as_text_are_left_alone(self):
        import shw_full
        self.assertIsNone(shw_full.tidy(b'\n[\n]'))                              # word-list addresses 0x0A5B, 0x0A5D
        self.assertIsNone(shw_full.tidy(b'\x06c\x07['))                          # the setup's cast table
        self.assertEqual(shw_full.tidy(b"hi, $usr! { press '1' to view."), b"hi, $USR! pause to view it.")

    def test_its_scripts_keep_their_numbers_apart(self):
        import shw_full
        self.assertEqual([shw_full.shs_script(r) for r in (10002, 10017, 11000, 11007)], [25002, 25017, 25100, 25107])

    def test_its_month_has_the_demos_calendar(self):
        import shw_full
        dates = shw_full.date_texts(dict(month0=2, date0=1, weekday0=0, days=29))
        self.assertEqual((dates[0], dates[1], dates[28]), ('Sunday, February 1', 'Monday, February 2', 'Sunday, March 1'))


class OptionDetailTests(unittest.TestCase):
    """shshd-runtime: a built choice option's detail line (engine.OPTION_DETAIL; owner, 2026-11-14)."""

    def choice(self, options, shuffle=0):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))
        import brew
        from exp_runtime.decode.bytecode import decode_program
        from kiwi_rewrite import Rewriter
        rewriter = Rewriter(decode_program(brew.upgrade(brew.EMPTY_SCRIPT)), zero_gap=True)

        def body(s):
            s.text('Where to?'); s.push(-1); s.push(0); s.push(0); s.push(0); s.push(0); s.call(2, 6)
            for value, text in enumerate(options):
                s.text(text); s.push(value); s.push(1); s.call(3, 3)
            s.push(shuffle); s.call(4, 1)
        rewriter.prologue(body)
        import playthrough
        from exp_runtime.exp import Metadata, encode_exp
        data = encode_exp({25001: rewriter.finish().to_bytes(), 1: Metadata(30000, 1, ('Test',) * 5).to_bytes()})
        session = playthrough.session(data)
        session.advance()
        return session

    def test_the_label_is_the_option_and_the_detail_rides_beside_it(self):
        from exp_runtime.engine import OPTION_DETAIL
        session = self.choice(['Downtown: Gym' + OPTION_DETAIL + 'Open 24 hrs', 'The Flats: Home', 'Stats'])
        details = session.pending.details
        self.assertEqual(details['options'], ['Downtown: Gym', 'The Flats: Home', 'Stats'])
        self.assertEqual(details['details'], ['Open 24 hrs', '', ''])

    def test_without_details_a_choice_is_as_it_was(self):
        session = self.choice(['Yes', 'No'])
        self.assertNotIn('details', session.pending.details)

    def test_a_detail_moves_with_its_label_when_shuffled_and_is_saved(self):
        from exp_runtime.engine import OPTION_DETAIL
        from exp_runtime.runtime import Session
        session = self.choice([f'Place {n}' + OPTION_DETAIL + f'hours {n}' for n in range(6)], shuffle=1)
        details = session.pending.details
        for label, line, value in zip(details['options'], details['details'], details['values']):
            self.assertEqual((label[-1], line[-1]), (str(value), str(value)))
        restored = Session.from_snapshot(session.resources, session.snapshot())
        self.assertEqual(restored.pending.details['details'], details['details'])


@unittest.skipUnless(HAS_PIL and JAR and Path(JAR or '.').exists(), 'SHSHD_SHW_JAR (the demo\'s 1.0.2 jar) is not set')
class FullChapterTests(unittest.TestCase):
    """The chapter built from the player's jar (and the add-on, without its music) and played to its end."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        import shw
        import shw_full
        cls.folder = tempfile.TemporaryDirectory()
        addon, _ = shw.build_addon(JAR, music=False)
        addon_path = Path(cls.folder.name) / 'shshw.exp'
        addon_path.write_bytes(addon)
        cls.name, cls.data = shw_full.build_story(JAR, addon_path)
        from exp_runtime.exp import ExpArchive
        cls.addon = ExpArchive(addon)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_it_is_episode_one_and_needs_the_sun(self):
        import shw_full
        from exp_runtime.addons import addon_record
        from exp_runtime.exp import ExpArchive
        archive = ExpArchive(self.data)
        self.assertEqual((archive.metadata().pack_id, archive.metadata().episode_id), (31700, 1))
        self.assertEqual(addon_record(archive), ('requires', (('shshw', shw_full.ADDON_REQUIRED),)))
        self.assertIn(shw_full.DRIVER, archive.entries)

    def test_a_month_plays_to_its_end(self):
        import playthrough
        from exp_runtime import quest_journal
        session = playthrough.session(self.data, addons=[self.addon])
        session.engine.random.state = 1
        rng = random.Random(1)
        record, journal = [], []

        class Answers:
            def __len__(self):
                return 1

            def pop(self, _):
                if session.pending is not None and session.pending.name == 'choice':
                    journal.append(len(quest_journal.quests(session)))
                options = record[-1].get('options') or ['']
                return rng.randrange(len(options))
        playthrough.steps(session, Answers(), 'Kate', 20000, record)
        kinds = {r['kind'] for r in record}
        self.assertEqual(record[-1]['kind'], 'exit')
        self.assertTrue({'line', 'choice', 'message', 'title', 'word_game'} <= kinds)
        wheres = [r for r in record if r['kind'] == 'choice' and r['title'] == 'Where to?']
        self.assertGreater(len(wheres), 100)
        self.assertIn('Quest Journal', wheres[0]['options'])
        self.assertGreater(max(journal), 3)                                     # the pause menu's journal fills in
        self.assertTrue(any(r['kind'] == 'message' and r['title'] == 'Stat changes' for r in record))


if __name__ == '__main__':
    unittest.main()
