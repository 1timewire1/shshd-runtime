"""Where unlisted episodes are filed (owner, 2026-11-17): the Creator's episodes under User-Created Episodes (their
authoring record, resource 2), last, and the novel's Extended adaptation (pack 31500) with Special SHS Novel Content,
rather than Premium Content, the fallback for an episode no catalog knows."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from exp_runtime.authored import MAGIC as AUTHORED_MAGIC
from exp_runtime.content import ContentLibrary, ExpArchive, authored_fields, digest, import_game
from exp_runtime.episode_index import NOVEL_PACK, PREMIUM_LABEL, USER_CREATED_LABEL, build_rows
from exp_runtime.exp import Metadata
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_vm import program

AUTHORED = AUTHORED_MAGIC + json.dumps(dict(format='exp-runtime-authored', version=1)).encode()


def episode(*, authored=False, pack=30900, number=1, title='My Story', text=b'one'):
    records = {1: Metadata(pack, number, (title,) * 5).to_bytes(), 25001: program(0x33).to_bytes(), 26000: text}
    if authored:
        records[2] = AUTHORED
    return archive(records)


def record(pack, number, title, **fields):
    return dict(id=f'{pack}-{number}', name=f'{title}.exp', pack_id=pack, episode_id=number, titles=[title] * 5,
                **fields)


def no_catalog():
    return Mock(category=Mock(return_value=None), pack_title=Mock(return_value=None))


class FieldsTests(unittest.TestCase):
    def test_an_authoring_record_files_it_as_user_created(self):
        self.assertEqual(authored_fields(ExpArchive(episode(authored=True)), {}), {'category': USER_CREATED_LABEL})
        self.assertEqual(authored_fields(ExpArchive(episode()), {}), {})

    def test_a_translations_own_category_comes_first(self):
        data = ExpArchive(episode(authored=True))
        self.assertEqual(authored_fields(data, {'legacy': 'X360', 'category': 'Xbox 360'}), {})

    def test_a_damaged_authoring_record_leaves_it_as_it_was(self):
        data = archive({1: metadata(), 25001: program(0x33).to_bytes(), 2: AUTHORED_MAGIC + b'{nope'})
        self.assertEqual(authored_fields(ExpArchive(data), {}), {})


class RowTests(unittest.TestCase):
    def rows(self, records):
        return [(row.title, [r['id'] for r in row.episodes])
                for row in build_rows(records, {r['id']: 'standard' for r in records}, no_catalog())]

    def test_user_created_episodes_are_their_own_row_after_premium_content(self):
        rows = self.rows([record(30900, 2, 'Mine', category=USER_CREATED_LABEL), record(7, 230, 'Other'),
                          record(101, 1, 'Season One'), record(30900, 1, 'Also mine', category=USER_CREATED_LABEL)])
        self.assertEqual(rows[-1], (USER_CREATED_LABEL, ['30900-1', '30900-2']))
        self.assertIn(PREMIUM_LABEL, [title for title, _ in rows[:-1]])

    def test_the_novels_extended_adaptation_is_with_the_novels_bonus_content(self):
        rows = dict(self.rows([record(NOVEL_PACK, 30, 'Surviving High School: The Novel (Extended)')]))
        self.assertEqual(rows, {'Special SHS Novel Content': [f'{NOVEL_PACK}-30']})


class CodRowTests(unittest.TestCase):
    def test_cause_of_death_lists_them_last_too(self):
        from exp_runtime.cod.episodes import build_rows as cod_rows
        catalog = Mock(category=Mock(return_value=None))
        rows = cod_rows([record(30900, 1, 'Mine', category=USER_CREATED_LABEL), record(7, 4, 'Love and Bullets')],
                        catalog)
        self.assertEqual([row.title for row in rows], ['Premium Content', USER_CREATED_LABEL])


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

    def add(self, data, name='mine.exp'):
        path = self.root / name
        path.write_bytes(data)
        with ContentLibrary(self.target) as library:
            library.add_episodes([path])
        with ContentLibrary(self.target) as library:
            return next(e for e in library.episodes if e['id'] == digest(data))

    def test_a_creator_export_is_filed_on_import(self):
        from exp_runtime.creator.compiler import compile_project
        from exp_runtime.creator.model import Project
        self.assertEqual(self.add(compile_project(Project())).get('category'), USER_CREATED_LABEL)
        self.assertNotIn('category', self.add(episode(text=b'plain'), 'plain.exp'))

    def test_importing_it_again_files_a_copy_imported_before_the_category(self):
        data = episode(authored=True)
        with patch('exp_runtime.content.authored_fields', Mock(return_value={})):
            self.assertNotIn('category', self.add(data))
        self.assertEqual(self.add(data, 'again.exp').get('category'), USER_CREATED_LABEL)


if __name__ == '__main__':
    unittest.main()
