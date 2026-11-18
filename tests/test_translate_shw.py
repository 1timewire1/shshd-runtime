"""Surviving Hollywood's full chapter (tools/translate shw_full.py; SURVIVING_HOLLYWOOD_ADDON_PLAN.md phase 3).

The translator's own rules run on authored text. The whole chapter is built and played only where the player's copies of the
demo's 240 x 320 jar and of the 1.0.4 (88K) demo's jar (its silhouettes) are named by SHSHD_SHW_JAR and SHSHD_SHW_LITE_JAR (no
original content is kept here): New Game to the month's end, with Where to?, the quest journal, minigames and the exit. Line-for-line agreement with Tardy-Slip's engine is checked outside the suite
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
LITE_JAR = os.environ.get('SHSHD_SHW_LITE_JAR')


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

    def test_its_casing_rules(self):
        import shw_full
        case = shw_full.case_text
        self.assertEqual(case("(he whispers) you better get on it."), "(He whispers) You better get on it.")
        self.assertEqual(case("he was so hot in 'last love'. the sequel is 'last love 2'."),
                         "He was so hot in 'Last Love'. The sequel is 'Last Love 2'.")
        self.assertEqual(case("i'm 'jellyfish a.' you're 'jellyfish b.'"), "I'm 'Jellyfish A.' You're 'Jellyfish B.'")
        self.assertEqual(case('tony talks to the boom mike operator. mike calls.'), 'Tony talks to the boom mike operator. Mike calls.')
        self.assertEqual(case('a studio in studio central, in la.'), 'A studio in Studio Central, in LA.')
        self.assertEqual(case("you said, 'i told you.'"), "You said, 'I told you.'")

    def test_its_read_lines_change_only_case(self):
        import shw_full
        self.assertGreater(len(shw_full.CASING_FIXES), 150)
        for source, written in shw_full.CASING_FIXES.items():
            self.assertEqual((written.lower(), len(written)), (source.lower(), len(source)), source)
        self.assertEqual(shw_full.case_text('in seaside as an executive assistant'), 'in Seaside as an executive assistant')

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


@unittest.skipUnless(HAS_PIL and JAR and Path(JAR or '.').exists() and LITE_JAR and Path(LITE_JAR or '.').exists(),
                     'SHSHD_SHW_JAR and SHSHD_SHW_LITE_JAR (the 1.0.2 and 1.0.4 demos\' jars) are not set')
class FullChapterTests(unittest.TestCase):
    """The chapter built from the player's jars (and the add-on, without its music) and played to its end."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        import shw
        import shw_full
        cls.folder = tempfile.TemporaryDirectory()
        addon, cls.spec = shw.build_addon(JAR, music=False, lite_jar=LITE_JAR)
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

    def test_badges_portraits_and_silhouettes_follow_the_owners_notes(self):
        """A badge for the one screen after it and never on a title card; the player's every line with her portrait; the
        silhouettes turned to face the middle; the street kid of 11002 a girl (owner's g54 notes, 2026-11-17)."""
        import playthrough
        import shw
        import shw_full
        session = playthrough.session(self.data, addons=[self.addon])
        session.engine.random.state = 2
        rng = random.Random(2)

        class Record(list):
            def append(self, r):
                badge = session.engine.scene_badge
                r['badge'] = badge.text if badge else None
                if r['kind'] == 'line':
                    r['art'] = session.engine.character_art_bases.get(r['character'])
                super().append(r)
        record = Record()

        class Answers:
            def __len__(self):
                return 1

            def pop(self, _):
                return rng.randrange(len(record[-1].get('options') or ['']))
        playthrough.steps(session, Answers(), 'Kate', 20000, record)
        self.assertEqual(record[-1]['kind'], 'exit')
        self.assertFalse([r for r in record if r['kind'] == 'title' and r['badge']])
        stale = [(a['badge'], b) for a, b in zip(record, record[1:]) if a['badge'] and a['badge'] == b['badge']
                 and a['kind'] != 'title']
        self.assertFalse(stale)
        you = [r for r in record if r['kind'] == 'line' and r['speaker'] == 'You']
        self.assertTrue(you)
        self.assertEqual({r['character'] for r in you}, {shw_full.PLAYER})
        mom = {r['art'] for r in record if r['kind'] == 'line' and r['speaker'] == 'Mom'}
        self.assertEqual(mom, {shw.TURNED_SILHOUETTE_BASE + 7})
        self.assertIn('turned_silhouettes', self.spec)
        self.assertIn(shw.PHONE_BADGE, self.addon.entries)
        journal = [r for r in record if r['badge'] == shw_full.JOURNAL_UPDATED]
        self.assertTrue(journal)
        self.assertEqual(shw_full.JOURNAL_ICON, shw.PHONE_BADGE)

    def test_every_person_without_a_portrait_wears_a_silhouette(self):
        import shw
        import shw_full
        setup = shw_full.setup_tables(shw.jar_resources(JAR)[shw_full.SETUP_SCRIPT])
        faceless = {e for e in setup['cast'] if setup['portraits'].get(e, -1) < 0}
        voices = {shw_full.EVENT, *shw_full.NAMED}
        self.assertEqual(set(shw_full.SILHOUETTES), faceless - voices)
        self.assertEqual(len(self.spec['silhouettes']), shw.SILHOUETTES)
        from exp_runtime.exp import ExpArchive
        for k, rid in enumerate(self.spec['silhouettes']):
            self.assertEqual(rid, shw.SILHOUETTE_BASE + k)
            self.assertIn(rid, self.addon.entries)

    def test_a_silhouetted_speaker_talks_in_their_own_line(self):
        import playthrough
        import shw
        import shw_full
        session = playthrough.session(self.data, addons=[self.addon])
        session.engine.random.state = 3
        rng = random.Random(3)
        record = []

        class Answers:
            def __len__(self):
                return 1

            def pop(self, _):
                return rng.randrange(len(record[-1].get('options') or ['']))
        playthrough.steps(session, Answers(), 'Kate', 6000, record)
        names = {casing_name(n) for n in ('mom', 'dad', 'cop', 'telemarketer', 'kid', 'vendor', 'girl', 'guy')}
        lines = [r for r in record if r['kind'] == 'line' and r.get('speaker') in names]
        self.assertTrue(lines)
        pictures = {base + k for base in (shw.SILHOUETTE_BASE, shw.TURNED_SILHOUETTE_BASE) for k in range(shw.SILHOUETTES)}
        for r in lines:
            self.assertIn(session.engine.character_art_bases.get(r['character']), pictures, r)
            self.assertEqual(r['expression'], 0)                    # the next silhouette is no expression of this one


def casing_name(name):
    import casing
    return casing.title_case(name)


if __name__ == '__main__':
    unittest.main()
