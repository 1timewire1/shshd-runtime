"""shshd-runtime: an add-on past an episode's size limit (Claire Hart's rounds, 1.1 GB) imports from a ZIP or a loose file,
streamed to the library and hashed on the way, never held whole; an episode that large is still refused (owner's g54,
2026-11-21: the tester ZIP gave "ZIP member exceeds supported size"). MAX_PAYLOAD is lowered here so small fixtures cross
it."""
from unittest import mock
from zipfile import ZIP_DEFLATED, ZipFile

from exp_runtime import content
from exp_runtime.content import ContentError, digest
from test_addon_management import Library, story

LIMIT = 4096


class LargeAddonImportTests(Library):
    def setUp(self):
        super().setUp()
        from test_content import archive, metadata
        from exp_runtime.addons import provides_bytes
        self.big = archive({1: metadata('The Rounds (addon)'), 4: provides_bytes('rounds', 'The Rounds', 1),
                            26001: bytes(range(256)) * 64})               # 16 KB: past LIMIT
        self.assertGreater(len(self.big), LIMIT)
        patcher = mock.patch.object(content, 'MAX_PAYLOAD', LIMIT)
        patcher.start()
        self.addCleanup(patcher.stop)

    def zipped(self, name, members):
        path = self.root / name
        with ZipFile(path, 'w', ZIP_DEFLATED) as package:
            for member, data in members.items():
                package.writestr(member, data)
        return path

    def holding(self, addon):
        return next((a for a in self.library.addons if a['addon'] == addon), None)

    def test_a_zipped_addon_past_the_limit_is_streamed_into_the_library(self):
        path = self.zipped('rounds.zip', {'Rounds.exp': self.big, 'Story.exp': story('Plays', (('rounds', 1),))})
        real, sizes = content.ExpArchive, []

        def opened(data):
            sizes.append(len(data))
            return real(data)
        with mock.patch.object(content, 'ExpArchive', opened):
            self.library.add_episodes([path])
        held = self.holding('rounds')
        self.assertEqual((held['sha256'], (self.folder / held['file']).read_bytes()), (digest(self.big), self.big))
        self.assertNotIn(len(self.big), sizes)                             # (never read whole)
        self.assertIn('Plays', [r['titles'][0] for r in self.library.episodes])
        self.assertEqual(list(self.folder.glob('.exp-import-*')), [])

    def test_a_loose_addon_past_the_limit_is_streamed_and_a_repeat_changes_nothing(self):
        self.add('Rounds.exp', self.big)
        held = self.holding('rounds')
        self.assertEqual((self.folder / held['file']).read_bytes(), self.big)
        before = (self.folder / held['file']).stat().st_mtime_ns
        self.add('Rounds.exp', self.big)
        self.assertEqual((self.folder / held['file']).stat().st_mtime_ns, before)
        (self.folder / held['file']).unlink()                              # (a lost file comes back from a re-import)
        self.add('Rounds.exp', self.big)
        self.assertEqual((self.folder / held['file']).read_bytes(), self.big)

    def test_an_episode_past_the_limit_is_still_refused_and_nothing_changes(self):
        from test_content import archive, metadata
        from test_vm import program
        huge = archive({1: metadata('Too Big'), 25001: program(0x33).to_bytes(), 26001: bytes(LIMIT * 2)})
        episodes = list(self.library.episodes)
        path = self.zipped('huge.zip', {'Huge.exp': huge})
        with self.assertRaisesRegex(ContentError, 'only an add-on may be larger'):
            self.library.add_episodes([path])
        self.assertEqual(self.library.episodes, episodes)
        self.assertEqual(list(self.folder.glob('.exp-import-*')), [])
