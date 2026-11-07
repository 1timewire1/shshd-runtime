"""Episode versions (episode_version.py, SCHEMA.md "Episode version extension"; owner, 2026-11-06): a newer import
replaces the library's older copies of the episode; a copy with a saved game is asked about first."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from exp_runtime.content import ContentLibrary, ExpArchive, ReplaceSavedEpisodes, digest, import_game
from exp_runtime.episode_version import episode_revision, normalize, version_bytes
from exp_runtime.exp import ContentError, Metadata
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_vm import program


def episode(version=None, *, pack=31000, number=206, text=b'one', title='2.6 Wendy vs. Lenny'):
    records = {1: Metadata(pack, number, (title,) * 5).to_bytes(), 25001: program(0x33).to_bytes(), 26000: text}
    if version is not None:
        records[5] = version_bytes(version)
    return archive(records)


class RecordTests(unittest.TestCase):
    def test_the_record_holds_a_version_from_1_to_65535(self):
        self.assertEqual(episode_revision(ExpArchive(episode(3))), 3)
        self.assertIsNone(episode_revision(ExpArchive(episode())))
        base = dict(format='shshd-episode', version=1)
        for bad in (dict(base, revision=0), dict(base, revision=65536), dict(base, revision='2'), dict(base, version=2, revision=1),
                    dict(base, revision=1, extra=1), base):
            with self.subTest(record=bad), self.assertRaises(ValueError):
                normalize(bad)
        with self.assertRaisesRegex(ContentError, 'Invalid episode version'):
            episode_revision(ExpArchive(archive({1: metadata(), 25001: program(0x33).to_bytes(),
                                                 5: b'SHSHD-EPISODE\0{nope'})))


class ImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        profile.start()
        self.addCleanup(profile.stop)
        apk = self.root / 'user.apk'
        make_apk(apk, archive({1: metadata(), 25001: program(0x33).to_bytes()}))
        self.target = self.root / 'library'
        import_game(apk, [], self.target)
        self.files = 0

    def add(self, *datas, **options):
        paths = []
        for data in datas:
            self.files += 1
            path = self.root / f'{self.files}.exp'
            path.write_bytes(data)
            paths.append(path)
        with ContentLibrary(self.target) as library:
            count = library.add_episodes(paths, **options)
            return count, library

    def ids(self):
        with ContentLibrary(self.target) as library:
            return {e['id']: e.get('revision') for e in library.episodes if e['pack_id'] == 31000}

    def test_a_copy_without_a_version_keeps_the_old_behaviour(self):
        self.add(episode(text=b'one'))
        self.add(episode(text=b'two'))
        self.assertEqual(len(self.ids()), 2)                             # (official releases: both stay)

    def test_a_versioned_import_replaces_an_unversioned_or_older_copy_and_its_files(self):
        old = digest(episode(text=b'one'))
        self.add(episode(text=b'one'))
        (self.target / 'thumbs').mkdir(exist_ok=True)
        (self.target / 'thumbs' / f'{old}.jpg').write_bytes(b'a preview')
        count, library = self.add(episode(1, text=b'two'))
        self.assertEqual((count, [r['id'] for r in library.last_replaced]), (1, [old]))
        self.assertEqual(list(self.ids().values()), [1])
        self.assertFalse((self.target / 'content' / f'{old}.exp').exists())
        self.assertFalse((self.target / 'thumbs' / f'{old}.jpg').exists())
        self.add(episode(2, text=b'three'))
        self.assertEqual(list(self.ids().values()), [2])

    def test_a_rebuild_at_the_same_version_replaces_and_an_older_one_is_left_out(self):
        self.add(episode(2, text=b'one'))
        self.add(episode(2, text=b'two'))
        self.assertEqual(list(self.ids()), [digest(episode(2, text=b'two'))])
        count, library = self.add(episode(1, text=b'old'))
        self.assertEqual((count, len(library.last_older)), (0, 1))
        self.assertEqual(list(self.ids()), [digest(episode(2, text=b'two'))])

    def test_two_versions_in_one_batch_leave_the_newer(self):
        count, _ = self.add(episode(1, text=b'one'), episode(3, text=b'three'), episode(2, text=b'two'))
        self.assertEqual(list(self.ids().values()), [3])

    def test_other_episodes_and_releases_are_left_alone(self):
        self.add(episode(text=b'one'), episode(number=207, text=b'other'))
        self.add(episode(1, text=b'two'))
        self.assertEqual(len(self.ids()), 2)

    def test_a_copy_with_a_saved_game_is_asked_about(self):
        old = digest(episode(text=b'one'))
        self.add(episode(text=b'one'))
        saves = self.target / 'saves'
        saves.mkdir(exist_ok=True)
        (saves / f'{old}.shs-auto.json').write_text('{}', encoding='utf-8')
        with self.assertRaises(ReplaceSavedEpisodes) as raised:
            self.add(episode(1, text=b'two'))
        self.assertEqual([r['id'] for r in raised.exception.records], [old])
        self.assertEqual(list(self.ids()), [old])                       # nothing was written
        count, library = self.add(episode(1, text=b'two'), replace_saved=False)
        self.assertEqual(([r['id'] for r in library.last_kept], len(self.ids())), ([old], 2))
        self.add(episode(1, text=b'three'), replace_saved=True)
        self.assertEqual(list(self.ids()), [digest(episode(1, text=b'three'))])
        self.assertFalse((saves / f'{old}.shs-auto.json').exists())

    def test_the_episode_being_played_stays(self):
        old = digest(episode(text=b'one'))
        self.add(episode(text=b'one'))
        _, library = self.add(episode(1, text=b'two'), keep=(old,))
        self.assertEqual(([r['id'] for r in library.last_kept], len(self.ids())), ([old], 2))


class AppQuestionTests(unittest.TestCase):
    def setUp(self):
        import os
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.application import Application
        self.Application = Application
        self.app = Mock(import_paths_pending=['a.exp'])
        self.error = ReplaceSavedEpisodes([dict(id='x', name='x.exp', titles=['2.6 Wendy vs. Lenny'])])

    def test_the_menu_asks_and_either_answer_finishes_the_import(self):
        self.Application.ask_replace_saved(self.app, self.error)
        title, text, verb, yes = self.app.shell.confirm.call_args[0]
        self.assertEqual((title, verb), ('Replace Saved Episodes?', 'Replace'))
        self.assertIn('2.6 Wendy vs. Lenny', text)
        yes()
        self.app.add_episode_files.assert_called_with(['a.exp'], replace_saved=True)
        self.app.shell.confirm.call_args[1]['cancel']()
        self.app.add_episode_files.assert_called_with(['a.exp'], replace_saved=False)

    def test_a_menu_without_a_confirmation_window_keeps_them(self):
        self.app.shell = None
        self.Application.ask_replace_saved(self.app, self.error)
        self.app.add_episode_files.assert_called_once_with(['a.exp'], replace_saved=False)

    def test_the_result_says_what_was_replaced_kept_and_left_out(self):
        self.app.library = Mock(last_addons_added=0, last_replaced=[1, 2], last_kept=[1], last_older=[1])
        self.assertEqual(self.Application.added_text(self.app, 3),
                         'Added 3 episodes. 2 older copies were replaced. 1 older copy with a saved game was kept. '
                         '1 older version was left out: a newer one is here.')


class CreatorTests(unittest.TestCase):
    def test_a_project_carries_its_version_through_export_and_import(self):
        from exp_runtime.creator.compiler import compile_project
        from exp_runtime.creator.model import Project, project_from_record, project_record
        from exp_runtime.creator.native import import_exp
        project = Project(episode_version=4)
        self.assertEqual(project_from_record(project_record(project)).episode_version, 4)
        data = compile_project(project)
        self.assertEqual(episode_revision(ExpArchive(data)), 4)
        self.assertEqual(import_exp(data).episode_version, 4)
        self.assertIsNone(episode_revision(ExpArchive(compile_project(Project()))))
        record = project_record(Project())
        del record['episode_version']                                   # (a project saved before versions)
        self.assertIsNone(project_from_record(record).episode_version)


if __name__ == '__main__':
    unittest.main()
