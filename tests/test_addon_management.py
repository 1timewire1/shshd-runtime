"""Addons in Data Management: what the library knows of them, Verify, Storage, Library Info, the Add-Ons page and the export offer."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from exp_runtime.addons import provides_bytes, requires_bytes
from exp_runtime.application import Application
from exp_runtime.content import ContentError, ContentLibrary, digest, import_game
from exp_runtime.desktop_addons import AddonPages, export_offer
from exp_runtime.desktop_pause_hd import DATA_LAST
from exp_runtime.menu import MenuState
from test_content import FAKE_NATIVE, archive, make_apk, metadata
from test_vm import program


def pack(addon='packs', title='The Pack', revision=2, **more):
    return archive({1: metadata(title + ' (addon)'), 4: provides_bytes(addon, title, revision, **more), 26001: b'shared art'})


def story(name, requires=(('packs', 1),)):
    resources = {1: metadata(name), 25001: program(0x33).to_bytes()}
    if requires:
        resources[4] = requires_bytes(list(requires))
    return archive(resources)


class Library(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        profile = patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE))
        profile.start()
        self.addCleanup(profile.stop)
        apk = self.root / 'game.apk'
        make_apk(apk, archive({1: metadata(), 25001: program(0x33).to_bytes()}))
        self.folder = self.root / 'library'
        import_game(apk, [], self.folder)
        self.library = ContentLibrary(self.folder)
        self.addCleanup(self.library.close)
        self.addon = pack()
        self.add('The_Pack.exp', self.addon)
        self.add('Needs.exp', story('Needs it'))
        self.add('Alone.exp', story('Stands alone', ()))
        self.held = next(a for a in self.library.addons if a['addon'] == 'packs')

    def add(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return self.library.add_episodes([path])

    def needing(self):
        return next(r for r in self.library.episodes if r['titles'][0] == 'Needs it')

    def alone(self):
        return next(r for r in self.library.episodes if r['titles'][0] == 'Stands alone')


class LibraryTests(Library):
    def test_an_episode_says_which_addons_it_needs(self):
        self.assertEqual(self.library.episode_requires(self.needing()), (('packs', 1),))
        self.assertEqual(self.library.episode_requires(self.alone()), ())
        self.assertEqual([r['titles'][0] for r in self.library.addon_users(self.held)], ['Needs it'])

    def test_an_episode_needing_what_it_stands_in_for_counts_as_a_user(self):
        self.add('Full.exp', pack('full', 'Everything', 1, supersedes=[('packs', 2)]))
        held = next(a for a in self.library.addons if a['addon'] == 'full')
        self.assertEqual([r['titles'][0] for r in self.library.addon_users(held)], ['Needs it'])

    def test_removing_an_addon_takes_its_file_and_the_episode_says_so(self):
        path = self.folder / self.held['file']
        self.assertTrue(path.is_file())
        self.assertEqual(self.library.remove_addons([self.held['id']]), 1)
        self.assertFalse(path.exists())
        self.assertEqual(self.library.addons, [])
        with ContentLibrary(self.folder) as reopened:
            self.assertEqual(reopened.addons, [])
            with self.assertRaisesRegex(ContentError, 'packs'):
                reopened.open_episode(self.needing()['id']).check_addons()
        self.assertEqual(self.library.remove_addons(['nothing']), 0)

    def test_an_addon_whose_file_went_is_reported_then_restored_by_importing_it_again(self):
        path = self.folder / self.held['file']
        path.unlink()
        resources = self.library.open_episode(self.needing()['id'])
        self.assertEqual(resources.missing_addons(), [('packs', 1)])
        self.add('The_Pack.exp', self.addon)
        self.assertEqual(path.read_bytes(), self.addon)
        self.assertEqual(self.library.open_episode(self.needing()['id']).missing_addons(), [])

    def test_importing_an_addon_it_still_has_changes_nothing(self):
        before = (self.folder / self.held['file']).stat().st_mtime_ns
        self.assertEqual(self.add('The_Pack.exp', self.addon), 0)
        self.assertEqual((self.folder / self.held['file']).stat().st_mtime_ns, before)


class AppTests(Library):
    def app(self):
        app = Application.__new__(Application)
        app.library, app.game, app.shot_cache, app.selected_game = self.library, None, {}, 'shs'
        app.state = MenuState(self.library)
        app.picker = object()
        app.settings = SimpleNamespace(export_folder=str(self.root / 'exports'), backup_folder=None)
        app.progress_text = ''
        app.shell = Mock()
        app.start_data_job = lambda title, work, done: done(work(self.library))
        return app

    def test_verify_checks_addons_and_removes_a_damaged_one(self):
        app = self.app()
        checked, missing, damaged, _ = app.verify_library(self.library)
        self.assertEqual((missing, damaged), ([], []))
        path = self.folder / self.held['file']
        path.write_bytes(b'damaged')
        checked_again, missing, damaged, _ = app.verify_library(self.library)
        self.assertEqual(checked_again, checked)
        self.assertEqual((missing, damaged), ([], ['The Pack (add-on)']))
        self.assertFalse(path.exists())

    def test_storage_counts_addons_apart_and_only_when_there_are_any(self):
        app = self.app()
        lines = app.storage_text(self.library).split('\n')
        self.assertTrue(any(line.startswith('Add-Ons: ') for line in lines), lines)
        self.library.remove_addons([self.held['id']])
        self.assertFalse(any(line.startswith('Add-Ons') for line in app.storage_text(self.library).split('\n')))

    def test_library_info_lists_them(self):
        text = self.app().library_info()
        self.assertIn('Add-Ons: 1.', text)
        self.assertIn('- The Pack, revision 2', text)

    def test_the_page_is_offered_with_data_managements_last_rows(self):
        self.assertEqual(DATA_LAST[0], ('manage_addons', 'Add-Ons'))

    def test_export_finds_what_the_chosen_episodes_need(self):
        app = self.app()
        self.assertEqual(app.addons_needed(self.library, {self.needing()['id']}), [(self.held['id'], 'The Pack')])
        self.assertEqual(app.addons_needed(self.library, {self.alone()['id']}), [])

    def export_folder(self, app):
        app.export_folder = lambda library: self.root / 'exports'
        return self.root / 'exports'

    def test_exporting_an_addon_copies_it_under_its_name_once(self):
        app = self.app()
        folder = self.export_folder(app)
        title, message = app.export_addons(self.library, [self.held['id']])
        self.assertEqual(title, 'Add-Ons Exported')
        self.assertEqual((folder / 'The_Pack.exp').read_bytes(), self.addon)
        app.export_addons(self.library, [self.held['id']])
        self.assertEqual([p.name for p in folder.iterdir()], ['The_Pack.exp'])

    def test_a_different_file_of_that_name_is_kept(self):
        app = self.app()
        folder = self.export_folder(app)
        folder.mkdir()
        (folder / 'The_Pack.exp').write_bytes(b'someone else\'s')
        app.export_addons(self.library, [self.held['id']])
        self.assertEqual((folder / 'The_Pack.exp').read_bytes(), b'someone else\'s')
        self.assertEqual((folder / 'The_Pack (2).exp').read_bytes(), self.addon)

    def test_export_only_offers_when_addons_are_needed_and_only_exports_on_a_yes(self):
        app = self.app()
        self.export_folder(app)
        host = SimpleNamespace(notice=Mock(), confirm=Mock())
        job = lambda title, work, done: done(work(self.library))    # noqa: E731
        export_offer(app, host, (('Done', 'Copied.'), []), job)
        host.notice.assert_called_once_with('Done', 'Copied.')
        host.confirm.assert_not_called()
        host.notice.reset_mock()
        export_offer(app, host, (('Done', 'Copied.'), [(self.held['id'], 'The Pack')]), job)
        host.notice.assert_not_called()
        title, text, verb, action = host.confirm.call_args.args
        self.assertEqual((title, verb), ('Export Add-On Too?', 'Export'))
        self.assertIn('Copied.', text)
        self.assertIn('The Pack', text)
        self.assertFalse((self.root / 'exports').exists())
        action()
        self.assertTrue((self.root / 'exports' / 'The_Pack.exp').is_file())
        self.assertEqual(host.notice.call_args.args[0], 'Add-Ons Exported')

    def pages(self, app):
        self.export_folder(app)
        host = SimpleNamespace(rows=Mock(), text=Mock(), notice=Mock(), confirm=Mock(), deleted=Mock(),
                               job=lambda title, work, done: done(work(self.library)))
        return AddonPages(app, host), host

    def test_the_page_lists_each_addon_and_opens_its_details_export_and_delete(self):
        pages, host = self.pages(self.app())
        pages.open()
        screen, title, rows, parent = host.rows.call_args.args
        self.assertEqual((screen, title, parent), ('data:addons', 'Add-Ons', 'options:data'))
        self.assertEqual([label for _, label in rows], ['The Pack'])
        self.assertTrue(pages.command(rows[0][0]))
        screen, title, rows, parent = host.rows.call_args.args
        self.assertEqual((title, parent, [label for _, label in rows]), ('Add-On', 'data:addons', ['Details: The Pack', 'Export', 'Delete']))
        pages.command(rows[0][0])
        body = host.text.call_args.args[2]
        for piece in ('The Pack', 'Add-on ID: packs', 'Revision: 2', '1 episode needs it.', '- Needs it'):
            self.assertIn(piece, body)
        pages.command(rows[1][0])
        self.assertEqual(host.notice.call_args.args[0], 'Add-Ons Exported')
        self.assertFalse(pages.command('something_else'))

    def test_deleting_warns_with_the_count_and_only_goes_on_a_yes(self):
        pages, host = self.pages(self.app())
        pages.open()
        pages.command('addon_delete:' + self.held['id'])
        title, text, verb, action = host.confirm.call_args.args
        self.assertEqual((title, verb), ('Delete Add-On?', 'Delete'))
        self.assertIn('1 episode needs it', text)
        self.assertIn('Saved games stay', text)
        self.assertEqual(len(self.library.addons), 1)
        action()
        self.assertEqual(self.library.addons, [])
        host.deleted.assert_called_once()
        self.assertEqual(host.notice.call_args.args[0], 'No Add-Ons')

    def test_deleting_lets_go_of_the_live_game(self):
        app = self.app()
        app.game = SimpleNamespace(session=SimpleNamespace(resources=SimpleNamespace(record=self.needing()), episode_ended=False))
        app.state.resume_path = lambda episode: None
        app.addon_deleted()
        self.assertIsNone(app.game)
        self.assertEqual(app.saved, set())


class SyncTests(Library):
    """The sender's and receiver's parts over two real libraries (the talking between them is test_lan_sync's)."""

    def flow(self, library):
        from exp_runtime import sync_flow
        from contextlib import contextmanager

        @contextmanager
        def opened(app, game):
            yield library, SimpleNamespace()
        patcher = patch.object(sync_flow, 'open_library', opened)
        patcher.start()
        self.addCleanup(patcher.stop)
        return sync_flow

    def other_library(self):
        apk = self.root / 'game.apk'
        folder = self.root / 'other'
        import_game(apk, [], folder)
        library = ContentLibrary(folder)
        self.addCleanup(library.close)
        return library

    def provider(self, sync_flow):
        provider = sync_flow.SendProvider.__new__(sync_flow.SendProvider)
        provider.app, provider.categories = SimpleNamespace(state=None), {'episodes'}
        return provider

    def host(self, sync_flow):
        host = sync_flow.ReceiveHost.__new__(sync_flow.ReceiveHost)
        host.flow, host.app = None, None
        return host

    def test_the_sender_offers_every_addon(self):
        provider = self.provider(self.flow(self.library))
        self.assertEqual(provider.offer_addons(['shs']), {'shs': [dict(id=self.held['id'], addon='packs', revision=2)]})

    def test_the_receiver_wants_what_it_lacks_or_holds_older_and_not_a_same_revision_rebuild(self):
        other = self.other_library()
        host = self.host(self.flow(other))
        entry = dict(id='sent', addon='packs', revision=2)
        self.assertEqual(host.want_addons('shs', [entry]), ['sent'])
        path = self.root / 'older.exp'
        path.write_bytes(pack(revision=1))
        other.add_episodes([path])
        self.assertEqual(host.want_addons('shs', [entry]), ['sent'])
        path.write_bytes(pack(revision=2, title='A rebuild'))
        other.add_episodes([path])
        self.assertEqual(host.want_addons('shs', [entry]), [])
        self.assertEqual(host.want_addons('shs', [dict(entry, revision=1)]), [])

    def test_a_pack_standing_in_for_one_counts_as_holding_it_and_the_full_one_is_wanted_over_the_slim(self):
        other = self.other_library()
        host = self.host(self.flow(other))
        path = self.root / 'full.exp'
        path.write_bytes(pack('full', 'Everything', 1, supersedes=[('packs', 2)]))
        other.add_episodes([path])
        self.assertEqual(host.want_addons('shs', [dict(id='slim', addon='packs', revision=2)]), [])
        self.assertEqual(host.want_addons('shs', [dict(id='slim', addon='packs', revision=3)]), ['slim'])
        other.remove_addons([a['id'] for a in other.addons])
        slim = self.root / 'slim.exp'
        slim.write_bytes(pack())
        other.add_episodes([slim])
        self.assertEqual(host.want_addons('shs', [dict(id='whole', addon='full', revision=1)]), ['whole'])

    def test_a_sent_addon_arrives_with_the_episodes_and_is_named_apart(self):
        sync_flow = self.flow(self.library)
        provider = self.provider(sync_flow)
        provider.folder, provider.player, provider.options = None, {}, None
        provider.app = SimpleNamespace(state=None, library_path=lambda game: self.root)
        needs = self.needing()['id']
        with patch('exp_runtime.progress_bundle.write_bundle', lambda *args, **kwargs: None):
            items = provider.items(['shs'], {'shs': [needs]}, {'shs': [self.held['id']]})
        names = [name for kind, name, path in items if kind == 'episode']
        self.assertEqual(names, ['shs/0/Needs.exp', 'shs/1/The_Pack.exp'])
        other = self.other_library()
        stage = self.root / 'stage'
        for kind, name, path in items:
            if kind == 'episode':
                _, index, file = name.split('/')
                target = stage / 'episodes' / index / file
                target.parent.mkdir(parents=True)
                target.write_bytes(path.read_bytes())
        host = self.host(self.flow(other))
        host.app = SimpleNamespace(back_up_progress=Mock())
        parts = host.apply_game(dict(categories=['episodes']), stage, other, SimpleNamespace())
        self.assertEqual(parts, ['1 episode', '1 add-on'])
        self.assertEqual([a['addon'] for a in other.addons], ['packs'])
        record = next(r for r in other.episodes if r['titles'][0] == 'Needs it')
        self.assertEqual(other.open_episode(record['id']).missing_addons(), [])


class ReplacedProgressTests(unittest.TestCase):
    def test_restored_progress_lets_go_of_the_live_game_so_it_cant_hide_what_came_back(self):
        app = Application.__new__(Application)
        app.game = object()
        app.library = SimpleNamespace(episodes=[])
        app.state = SimpleNamespace(ended_saves=set())
        app.shot_cache = {}
        app.saved = set()
        app.restore_player = Mock()
        app.refresh_saves = Mock()
        app.shell = Mock()
        app.progress_restored((dict(saved=[]), {}, None))
        self.assertIsNone(app.game)
        app.refresh_saves.assert_called_once()

    def test_a_received_sync_lets_go_of_the_live_game_so_it_cant_hide_what_came(self):
        from exp_runtime import lan_sync
        from exp_runtime.sync_flow import SyncFlow
        flow = SyncFlow.__new__(SyncFlow)
        flow.pending = {}
        ui = Mock()
        app = SimpleNamespace(library=object(), game=object(), refresh_saves=Mock(), picker=object(), prepare_previews=Mock())
        flow.app = app
        flow.stop = Mock()
        type(flow).ui = property(lambda self: ui)
        session = lan_sync.ReceiveSession.__new__(lan_sync.ReceiveSession)
        session.status, session.message = 'done', 'Synced.'
        flow.finished(session)
        self.assertIsNone(app.game)
        app.refresh_saves.assert_called_once()
        del type(flow).ui


if __name__ == '__main__':
    unittest.main()
