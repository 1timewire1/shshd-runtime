"""shshd-runtime: an episode's own translations (resource 6, episode_languages.py): SHS '11's Italian (owner, 2026-11-17)."""
import gzip
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from exp_runtime import episode_languages as languages
from exp_runtime.content import ContentError
from exp_runtime.dsi import Translation
from exp_runtime.exp import ExpArchive, encode_exp
from exp_runtime.runtime import Session
from test_runtime import Resources, host_call, text_words
from test_vm import program

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'translate'))

RECORD = dict(setting='shs11_language', languages={'it': 'Italiano'}, titles={'it': 'Scambio culturale'},
              lines={'hello there $usr': {'it': 'Ciao, $USR!'}, 's has d dollars': {'it': '%s ha %d dollari!'},
                     'a bowl of radishes': {'it': 'una ciotola di ravanelli'},
                     'end of game': {'it': 'Fine del gioco'}, 'thanks for playing': {'it': 'Grazie per aver giocato!'},
                     'oh': {'it': 'Oh...'}},
              context={'oh': {'hello there $usr': {'it': 'Oh!'}}},
              menu={'aunt cathy': {'it': 'Zia Cathy'}},
              words={'elf': {'it': 'elfo'}, 'search|gift': {'it': 'cerca|regalo'}},
              ui={'it': {'memory': {'time_up': 'Fine tempo!'}}})


class RecordTests(unittest.TestCase):
    def test_a_record_round_trips_and_is_kept_in_the_library(self):
        archive = ExpArchive(encode_exp({25001: b'x', languages.RESOURCE: languages.languages_bytes(RECORD)}))
        found = languages.episode_languages(archive)
        self.assertEqual(found['lines'], RECORD['lines'])
        self.assertEqual(languages.import_fields(archive), dict(languages=dict(
            setting='shs11_language', names={'it': 'Italiano'}, titles={'it': 'Scambio culturale'})))
        self.assertIsNone(languages.episode_languages(ExpArchive(encode_exp({25001: b'x'}))))

    def test_a_malformed_record_is_refused_and_plays_in_its_own_language(self):
        for bad in (dict(RECORD, setting='dsi_language'), dict(RECORD, languages={'off': 'Off'}),
                    dict(RECORD, lines={'x': {'fr': 'y'}}), dict(RECORD, extra=1)):
            with self.assertRaises(ValueError):
                languages.languages_bytes(bad)
        broken = ExpArchive(encode_exp({languages.RESOURCE: languages.MAGIC + gzip.compress(b'{"format": 1}')}))
        with self.assertRaises(ContentError):
            languages.episode_languages(broken)
        self.assertEqual(languages.import_fields(broken), {})


class OwnResources(Resources):
    """An episode carrying RECORD, with the library's '11 Language as `language`."""

    def __init__(self, first, language='it'):
        super().__init__(first)
        self.library = SimpleNamespace(directory=Path('.'), shs11_language=language)

    def own_languages(self):
        return json.loads(json.dumps(dict(RECORD, format=languages.FORMAT, version=languages.VERSION)))

    def episode_translation(self, language=None):
        # (kept per language, as EpisodeResources keeps them: a translation remembers the line shown before)
        language = self.library.shs11_language if language is None else language
        if language not in RECORD['languages']:
            return None
        made = self.__dict__.setdefault('_made', {})
        return made.setdefault(language, Translation(self.own_languages(), language))


class SessionTests(unittest.TestCase):
    def session(self, code, words, language='it', hd=True):
        resources = OwnResources(program(*code, 0x33, words=words), language)
        session = Session(resources)
        if hd:
            session.engine.hd_version = '1.4.38'
        session.engine.strings['$USR'] = 'Sam'
        return session, resources

    def test_a_line_shows_in_the_language_its_switch_picks_in_hd_only(self):
        words, (line,) = text_words('Hello there, $USR!')
        session, resources = self.session(host_call(13, line, 0), words)
        self.assertEqual(session.advance().details['text'], 'Ciao, Sam!')
        resources.library.shs11_language = 'off'
        self.assertEqual(session.engine.substitute('Hello there, $USR!'), 'Hello there, Sam!')
        self.assertIn('Ciao, Sam!', session.engine.shown_forms('Hello there, $USR!'))       # a save made in Italian loads
        sd, _ = self.session(host_call(13, line, 0), words, hd=False)
        self.assertEqual(sd.advance().details['text'], 'Hello there, Sam!')

    def test_a_name_and_a_line_after_another_take_their_own(self):
        session, _ = self.session([], text_words('x')[0])
        engine = session.engine
        self.assertEqual(engine.substitute('Aunt Cathy'), 'Zia Cathy')
        self.assertEqual(engine.substitute('Oh...'), 'Oh...')
        engine.substitute('Hello there, $USR!')
        self.assertEqual(engine.substitute('Oh...'), 'Oh!')

    def test_formats_and_their_texts_are_put_in_the_language_first(self):
        words, (pattern, item) = text_words('%s has %d dollars!', 'a bowl of radishes')
        session, _ = self.session(host_call(0, pattern, item, 20), words)
        session.advance()
        self.assertEqual(session.engine.dynamic_strings[0], 'una ciotola di ravanelli ha 20 dollari!')

    def test_the_closing_page_is_in_the_language_too(self):
        words, (title, text) = text_words('End of game', 'Thanks for playing!')
        session, _ = self.session(host_call(33, title, text, 4000), words)
        session.advance()
        self.assertEqual((session.engine.message_panel.title, session.engine.message_panel.text),
                         ('Fine del gioco', 'Grazie per aver giocato!'))

    def test_memorys_word_is_the_languages_own(self):
        translation = Translation(OwnResources(program(0x33)).own_languages(), 'it')
        self.assertEqual(translation.words.get('elf', {}).get('it', 'elf').upper(), 'ELFO')
        self.assertEqual(translation.line('search|gift'), 'cerca|regalo')


class PlayerTests(unittest.TestCase):
    def test_the_games_interface_text_takes_the_episodes_own(self):
        from exp_runtime.desktop_shs11_memory import translated_text
        resources = OwnResources(program(0x33))
        resources.library.hd_ipa = {'file': 'x'}
        english = {'time_up': "Time's up!", 'goal': 'Find the letters.'}
        self.assertEqual(translated_text(resources, 'memory', english), {'time_up': 'Fine tempo!', 'goal': 'Find the letters.'})
        resources.library.shs11_language = 'off'
        self.assertEqual(translated_text(resources, 'memory', english), english)
        resources.library.shs11_language = 'it'
        resources.library.hd_ipa = None
        self.assertEqual(translated_text(resources, 'memory', english), english)

    def test_the_episode_list_shows_the_title_for_the_language_picked(self):
        from exp_runtime.episode_picker import PickerModel
        record = dict(id='a', pack_id=31600, episode_id=3, titles=['Foreign Exchange'], languages=dict(setting='shs11_language',
                                                                          titles={'it': 'Scambio culturale'}))
        picker = PickerModel.__new__(PickerModel)
        picker.cod, picker.title_language = None, 'en'
        picker.library = SimpleNamespace(shs11_language='it', dsi_language='off', hd_ipa={'file': 'x'})
        self.assertEqual(picker.label(record), 'Scambio culturale')
        picker.library.shs11_language = 'off'
        self.assertEqual(picker.label(record), 'Foreign Exchange')

    def test_preferred_language_gives_it_italian_alone(self):
        # Owner, 2026-11-18: General's Preferred Language in place of '11 Language (and DSi Language, Story Language and
        # Episode Titles): '11's stories take Italian when it's the preferred one, their own English otherwise.
        from exp_runtime.languages import language_settings
        from exp_runtime.menu import SHARED_PREFERENCES
        from exp_runtime.desktop_pause_hd import CHOICE_NAMES, CHOICE_PARENTS, LANGUAGE_NAMES, PER_GAME_CHOICES
        self.assertNotIn('shs11_language', SHARED_PREFERENCES)
        self.assertEqual(SHARED_PREFERENCES['preferred_language'], ('en', 'fr', 'it', 'de', 'es'))
        self.assertEqual([language_settings(code)['shs11_language'] for code in ('en', 'fr', 'it', 'de', 'es')],
                         ['off', 'off', 'it', 'off', 'off'])
        self.assertEqual((CHOICE_NAMES['preferred_language'], CHOICE_PARENTS['preferred_language']),
                         (LANGUAGE_NAMES, 'options:general'))
        self.assertEqual(PER_GAME_CHOICES, ('ch_dialogue',))                    # DSi Backgrounds is Extras' now


class TranslatorTests(unittest.TestCase):
    def test_two_builds_align_by_what_they_push_however_it_is_packed(self):
        import shs11_italian
        english = program((0x1b, 0x0302), (0x1f, 13 << 8 | 2), 0x33).instructions        # 2, 3 packed in one push
        italian = program((0x1a, 2), (0x1a, 300), (0x1f, 13 << 8 | 2), 0x33).instructions   # the address grew past a byte
        pushes = [(a[2], b[2]) for a, b in shs11_italian.aligned(english, italian) if a[0] == 'push']
        self.assertEqual(pushes, [(2, 2), (3, 300)])

    def test_texts_no_push_reads_pair_between_the_ones_that_do(self):
        import shs11_italian
        english_words, _ = text_words('Hello.', 'Radishes ($%d).', 'Chips ($%d).', 'Bye.')
        italian_words, _ = text_words('Ciao.', 'Ravanelli ($%d).', 'Patatine ($%d).', 'Arrivederci.')
        english = bytes(program(0x33, words=english_words).to_bytes())
        italian = bytes(program(0x33, words=italian_words).to_bytes())
        ea = [a for a, _ in shs11_italian.strings(__import__('shs11').script_memory(english))]
        ia = [a for a, _ in shs11_italian.strings(__import__('shs11').script_memory(italian))]
        pairs = shs11_italian.between_pairs(english, italian, {ea[0]: ia[0], ea[3]: ia[3]})
        self.assertEqual(pairs, [('Radishes ($%d).', 'Ravanelli ($%d).'), ('Chips ($%d).', 'Patatine ($%d).')])

    def test_the_own_grids_fit_their_boards_and_keep_their_letters(self):
        import shs11_italian
        for (heading, title, words), (_, _, italian) in shs11_italian.GRIDS.items():
            self.assertLessEqual(len(italian.replace('|', '')), shs11_italian.GRID_LETTERS_MOST, italian)
            self.assertRegex(italian, r'^[a-z]+(\|[a-z]+)*$')
            self.assertEqual(len(words.split('|')), len(italian.split('|')))
        self.assertEqual(shs11_italian.grid_letters('stai|allerta', 'staytoes', 'stayoei'), 'stailer')
        for english, italian in shs11_italian.OWN.items():
            self.assertEqual(english.count('|'), italian.count('|'), english)


if __name__ == '__main__':
    unittest.main()
