"""The Creator's primary and extra add-ons, the settings that need no add-on, and the BREW catch game node (CREATOR_ADDONS_PLAN.md;
owner, 2026-11-09)."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from exp_runtime.addons import addon_record
from exp_runtime.creator.addons import drop_unused_addons, set_primary_addon
from exp_runtime.creator.compiler import compile_project
from exp_runtime.creator.minigames import catch_cuts
from exp_runtime.creator.model import Asset, Character, Node, Project, ProjectError
from exp_runtime.exp import ExpArchive
from exp_runtime.presentation import presentation_record

SIZES = {'109': [20, 24], '149': [18, 18], '156': [16, 16]}


def library(*ids):
    """A library holding these add-ons, revision 3 each."""
    found = {addon_id: (dict(addon=addon_id, title=addon_id, revision=3), SimpleNamespace(entries=set())) for addon_id in ids}
    return SimpleNamespace(addon=found.get, addons=[found[i][0] for i in ids], game_id='shs')


def story(*nodes, **fields):
    return Project(title='Add-ons', start='a', nodes=[*nodes, Node('z', 'end')], **fields)


def record(project):
    return presentation_record(ExpArchive(compile_project(project))) or {}


class RoleTests(unittest.TestCase):
    def test_the_primary_goes_first_with_its_edition_and_others_stay_extras(self):
        project = story(Node('a', text='Hi', next='z'), addons=[dict(id='shs11', revision=2)])
        set_primary_addon(project, library('shsbrew', 'shs11'), 'shsbrew', '07')
        self.assertEqual(project.addons, [dict(id='shsbrew', revision=3, primary=True, edition='07'), dict(id='shs11', revision=2)])
        set_primary_addon(project, library('shsbrew', 'shs11'), 'shs11')
        self.assertEqual([(e['id'], e.get('primary', False)) for e in project.addons], [('shs11', True), ('shsbrew', False)])
        with self.assertRaises(ProjectError):
            set_primary_addon(project, library('shsbrew'), 'shsbrew', '09')        # BREW needs '07 or '08
        with self.assertRaises(ProjectError):
            set_primary_addon(project, library(), 'shsx360')
        drop_unused_addons(project)                                               # the primary stays, used or not
        self.assertEqual([e['id'] for e in project.addons], ['shs11'])
        set_primary_addon(project, library('shs11'), None)
        self.assertNotIn('primary', project.addons[0])

    def test_the_export_declares_the_primary_the_settings_and_the_extras_aliases(self):
        project = story(Node('a', 'background', asset=26999, next='b'), Node('b', 'background', asset=26543, next='z'),
                        addons=[dict(id='shsbrew', revision=10, primary=True, edition='08'), dict(id='shs11', revision=2)],
                        assets=[Asset(26999, 'BREW frame', None, 'shsbrew'), Asset(26543, "'11 picture", None, 'shs11')],
                        options={'word_forms': True, 'big_pickers': True, 'date_first': False})
        found = record(project)
        self.assertEqual(found, dict(creator=True, word_forms=True, big_pickers=True, addons=('shsbrew', '08'),
                                     aliases={26543: ('shs11', 26543)}))
        self.assertEqual(addon_record(ExpArchive(compile_project(project)))[1], (('shsbrew', 10), ('shs11', 2)))   # primary first

    def test_a_plain_episode_is_marked_as_the_creators_and_a_translation_is_not(self):
        self.assertEqual(record(story(Node('a', text='Hi', next='z'))), dict(creator=True))
        self.assertEqual(record(story(Node('a', text='Hi', next='z'), pack_id=31400)), {})   # the X360 translator builds here
        with self.assertRaises(ProjectError):
            compile_project(story(Node('a', text='Hi', next='z'), options={'unknown': True}))

    def test_a_picker_takes_ten_looks_only_with_the_setting(self):
        characters = [Character(f'c{n}', f'Look {n}', 26000 + n) for n in range(7)]
        assets = [Asset(26000 + n, f'look {n}', b'\x89PNG\r\n\x1a\n' + bytes(64)) for n in range(7)]
        picker = Node('a', 'picker', params={'characters': [c.id for c in characters]}, next='z')
        with self.assertRaises(ProjectError):
            compile_project(story(picker, characters=characters, assets=assets))
        try:
            compile_project(story(picker, characters=characters, assets=assets, options={'big_pickers': True}))
        except ProjectError as error:
            self.assertNotIn('reusable characters', str(error))           # (only the stand-in pictures may be refused)


class CatchTests(unittest.TestCase):
    def project(self, **params):
        node = Node('a', 'brew_catch', params=dict(dict(sizes=SIZES), **params), next='b')
        branch = Node('b', 'branch', variable='catch_score', operator='>=', value=30, next='z', otherwise='z')
        return story(node, branch, addons=[dict(id='shsbrew', revision=10)])

    def session(self, project):
        from exp_runtime.runtime import Session
        archive = ExpArchive(compile_project(project))
        resources = SimpleNamespace(library=SimpleNamespace(game_id='shs', directory=Path(tempfile.gettempdir())),
                                    record={'titles': ['T'] * 5, 'id': 'x'}, identity=dict(profile='test', episode_sha256='0' * 64),
                                    program=archive.programs().__getitem__, linked_program=lambda: None,
                                    exists=lambda key: key in archive.entries, read_asset=archive.read)
        session = Session(resources, ephemeral=True)
        session.advance()
        return session

    def test_the_node_opens_the_catch_game_with_its_settings_and_the_stories_stretches(self):
        from exp_runtime.choice_hints import brew_catch_cuts
        session = self.session(self.project())
        self.assertEqual(session.pending.name, 'brew_catch')
        game = session.engine.brew_catch
        self.assertEqual((game.mode, game.target, game.interval_ms, game.speed, game.chance, game.angle, game.sprite),
                         (1, 45, 520, 330, 65, 40, 109))
        self.assertEqual([t[:3] for t in game.templates], [[3, 149, 25], [-3, 156, 15]])
        self.assertEqual(brew_catch_cuts(session), [30, 45])               # from the branch on its result, and the target
        session._complete_minigame(result=45)
        self.assertNotEqual(session.pending and session.pending.name, 'brew_catch')

    def test_an_orbit_game_takes_its_spread(self):
        game = self.session(self.project(kind='orbit', spread=50)).engine.brew_catch
        self.assertEqual((game.mode, game.spread, game.chance, game.angle), (3, 50, 0, 0))

    def test_it_needs_the_brew_add_on_sizes_and_good_settings(self):
        project = self.project()
        project.addons = []
        with self.assertRaisesRegex(ProjectError, 'shsbrew'):
            compile_project(project)
        with self.assertRaisesRegex(ProjectError, "doesn't draw"):
            compile_project(self.project(sizes={}))                       # no library to read the sizes from
        for bad in (dict(kind='round'), dict(chance=101), dict(items=[]), dict(items=[dict(value=1, picture=149, count=0)])):
            with self.subTest(bad=bad), self.assertRaises(ProjectError):
                compile_project(self.project(**bad))
        self.assertEqual(record(self.project()).get('minigames'), True)    # the player offers its switch

    def test_stretches_follow_each_comparison(self):
        p = dict(target=45)
        self.assertEqual(catch_cuts(p, [('>=', 30)]), [30, 45])
        self.assertEqual(catch_cuts(p, [('>', 30), ('<', 10)]), [10, 31, 45])
        self.assertEqual(catch_cuts(p, [('==', 20), ('>=', 60)]), [20, 21, 45])


if __name__ == '__main__':
    unittest.main()
