"""The name-replacement table every episode shares (SHSEntityTable renames; player.json `names`)."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from exp_runtime.menu import MenuState
from exp_runtime.runtime import Session
from test_runtime import Resources, host_call, text_words
from test_vm import program


def episode(*calls, strings):
    words, refs = text_words(*strings)
    body = [item for call in calls for item in host_call(call[0], *(refs[i] if isinstance(i, int) and i >= 0 else i
                                                                     for i in call[1:]))]
    return Session(Resources(program(*body, 0x33, words=words)))


class SharedNamesTests(unittest.TestCase):
    def test_a_name_stored_in_one_episode_is_the_one_the_next_episode_reads(self):
        table = {}
        first = episode((46, 0, 1), strings=('$ZOE', 'Zelda'))
        first.share_names(table)
        first.advance()
        self.assertEqual(table, {'$ZOE': 'Zelda'})
        second = episode((47, 0, 1, -1), strings=('$ZOE', 'Zoe'))      # key, default, slot 0
        second.share_names(table)
        second.advance()
        self.assertEqual(second.engine.dynamic_strings[0], 'Zelda')
        self.assertEqual(table, {'$ZOE': 'Zelda'})

    def test_a_name_never_set_takes_the_scripts_default_and_keeps_it(self):
        table = {}
        session = episode((47, 0, 1, -1), strings=('$Scott', 'Scott'))
        session.share_names(table)
        session.advance()
        self.assertEqual((session.engine.dynamic_strings[0], table), ('Scott', {'$Scott': 'Scott'}))

    def test_service_113_names_the_player_only_while_no_name_exists(self):
        table = {}
        session = episode((113, 0, 1), strings=('$USR', 'John'))
        session.share_names(table)
        session.advance()
        self.assertEqual(table, {'$USR': 'John'})
        table['$USR'] = 'Johnny'
        session = episode((113, 0, 1), strings=('$USR', 'John'))
        session.share_names(table)
        session.advance()
        self.assertEqual(table, {'$USR': 'Johnny'})

    def test_saves_record_the_table_but_loading_one_keeps_the_shared_values(self):
        table = {'$USR': 'Johnny'}
        session = episode((46, 0, 1), strings=('$DATE', 'Raven'))
        session.share_names(table)
        session.advance()
        saved = session.snapshot()
        table['$DATE'] = 'Beth'                                     # a later episode changed it
        self.assertEqual(saved['engine']['strings'], {'$USR': 'Johnny', '$DATE': 'Raven'})
        saved['engine']['strings']['$OLD'] = 'From an older save'
        restored = Session.from_snapshot(session.resources, saved)
        restored.share_names(table)
        self.assertIs(restored.engine.strings, table)
        self.assertEqual(table, {'$USR': 'Johnny', '$DATE': 'Beth', '$OLD': 'From an older save'})


class PlayerFileTests(unittest.TestCase):
    def test_names_persist_in_player_json_and_bad_tables_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            record = dict(id='a' * 64, pack_id=5, episode_id=9, titles=['t'] * 5, name='x.exp')
            library = SimpleNamespace(directory=Path(directory), episodes=[record], select=lambda selector: record,
                                      open_episode=None)
            state = MenuState(library)
            self.assertEqual(state.names, {})
            state.names.update({'$ZOE': 'Zelda', '$USR': 'Johnny'})
            state.persist()
            self.assertEqual(MenuState(library).names, {'$USR': 'Johnny', '$ZOE': 'Zelda'})
            self.assertEqual(list(MenuState(library).names), ['$ZOE', '$USR'])   # insertion order kept
            path = Path(directory) / 'player.json'
            data = json.loads(path.read_text(encoding='utf-8'))
            data['names'] = {'$ZOE': 7}
            path.write_text(json.dumps(data), encoding='utf-8')
            again = MenuState(library)
            self.assertEqual(again.names, {})
            self.assertIn('Invalid saved names', again.warning)

    def test_a_translated_games_names_are_its_own_and_persist(self):
        # New Rules' Dancing Queen and the smartphone Homecoming Queen both write `$Emily`: each game keeps its own.
        with tempfile.TemporaryDirectory() as directory:
            smartphone = dict(id='a' * 64, pack_id=5, episode_id=10, titles=['t'] * 5, name='x.exp')
            translated = dict(id='b' * 64, pack_id=31300, episode_id=101, titles=['t'] * 5, name='y.exp')
            library = SimpleNamespace(directory=Path(directory), episodes=[smartphone, translated], game_id='shs',
                                      select=lambda selector: smartphone, open_episode=None)
            state = MenuState(library)
            self.assertIs(state.names_for(smartphone), state.names)
            state.names_for(translated)['$Emily'] = 'Nova'
            state.names['$Emily'] = 'Emily'
            state.persist()
            again = MenuState(library)
            self.assertEqual(again.names_for(smartphone), {'$Emily': 'Emily'})
            self.assertEqual(again.names_for(translated), {'$Emily': 'Nova'})

    def test_a_name_the_opening_resets_wins_over_the_last_playthroughs(self):
        # The intro skips run the opening script before the window shares the table: Hector's Guide sets "$matt" back
        # to "you" there, and the last playthrough's handle must not come back.
        with tempfile.TemporaryDirectory() as directory:
            record = dict(id='a' * 64, pack_id=5, episode_id=9, titles=['t'] * 5, name='x.exp')
            opening = episode((46, 0, 1), strings=('$matt', 'you'))
            opening.resources.record = record
            library = SimpleNamespace(directory=Path(directory), episodes=[record], select=lambda selector: record,
                                      open_episode=lambda record: opening.resources)
            state = MenuState(library)
            state.names['$matt'] = 'StanTheDevil'
            state.skip_upsell_intros = True
            session = state.session(record, resume=False)
            self.assertEqual(state.names['$matt'], 'you')
            session.share_names(state.names)                        # what the window does next
            self.assertEqual(session.engine.substitute('$matt'), 'you')


class DesktopSharingTests(unittest.TestCase):
    def test_every_session_the_window_plays_uses_the_library_table(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        self.addCleanup(pygame.quit)
        table = {'$ZOE': 'Zelda'}
        session = episode((47, 0, 1, -1), strings=('$ZOE', 'Zoe'))
        ui = Desktop(session, audio=False, names=table)
        self.assertIs(ui.session.engine.strings, table)
        self.assertEqual(ui.session.engine.dynamic_strings[0], 'Zelda')
        replacement = Session.from_snapshot(session.resources, session.snapshot())
        ui.session = replacement                                   # a load or a warp
        self.assertIs(replacement.engine.strings, table)
        alone = Desktop(episode((46, 0, 1), strings=('$X', 'y')), audio=False)
        self.assertEqual(alone.session.engine.strings, {'$X': 'y'})     # no table: the session keeps its own


if __name__ == '__main__':
    unittest.main()
