"""SHS HD's Faceplace wall and Decision Tree, authored in the creator and run in the production VM and engine."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from exp_runtime.content import digest
from exp_runtime.creator import Choice, Node, ProjectError, compile_project
from exp_runtime.exp import ExpArchive
from exp_runtime.runtime import Session
from test_creator import session_for
from test_creator_features import sequence
from test_creator_story_services import with_cast
from test_runtime import answer_screen


def session_in(project, directory):
    """A session whose library folder is `directory`, so the episode's story tree files land there."""
    data = compile_project(project)
    archive = ExpArchive(data)
    resources = SimpleNamespace(library=SimpleNamespace(game_id=project.game, directory=Path(directory)),
                                identity=dict(profile='authored', episode_sha256=digest(data)), record={'titles': ['Story']},
                                program=archive.programs().__getitem__, exists=lambda key: key in archive.entries)
    return Session(resources)


class FaceplaceTests(unittest.TestCase):
    def test_posts_links_photos_and_the_default_name_reach_the_wall(self):
        p = with_cast(sequence(
            Node('on', 'faceplace'),
            Node('name', 'faceplace', text='John', params={'action': 'default_name'}),
            Node('post', 'faceplace_post', character='alex', expression=2, text='$USR made the team!'),
            Node('link', 'faceplace_link', text='Tap here', params={'url': 'https://example.com'}),
            Node('photo', 'faceplace_link', text='At the game', asset=26000),
            Node('system', 'faceplace_post', text='System notice'),
            Node('chosen', 'faceplace', params={'action': 'face_chosen'}),
            Node('say', text='Posted')), 'Alex')
        s = session_for(p)
        self.assertEqual(s.advance().details['text'], 'Posted')
        wall = s.engine.faceplace
        self.assertTrue(wall.enabled)
        self.assertEqual(s.engine.strings['$USR'], 'John')
        post, system = wall.messages
        self.assertEqual((post.text, post.from_id, post.expression), ('John made the team!', 1, 2))
        self.assertEqual([(c.kind, c.text, c.url, c.image_id) for c in post.continuations],
                         [('continuation_text', 'Tap here', 'https://example.com', -1),
                          ('continuation_image', 'At the game', '', 26000)])
        self.assertEqual((system.text, system.from_id), ('System notice', -1))

    def test_clear_empties_the_wall(self):
        s = session_for(sequence(Node('post', 'faceplace_post', text='Hi'), Node('clear', 'faceplace', params={'action': 'clear'}),
                                 Node('say', text='Done')))
        s.advance()
        self.assertEqual(s.engine.faceplace.messages, [])

    def test_faceplace_and_the_tree_are_shs_only(self):
        for node in (Node('a', 'faceplace'), Node('a', 'tree'), Node('a', 'faceplace_post', text='x')):
            with self.subTest(kind=node.kind), self.assertRaisesRegex(ProjectError, 'CoD has neither'):
                compile_project(sequence(node, game='cod'))


class DecisionTreeTests(unittest.TestCase):
    def story(self):
        return sequence(
            Node('on', 'tree'),
            Node('meet', 'tree_node', text='Meet Beth', params={'type': 1215}),
            Node('ask', 'choice', text='Talk to her?', options=[Choice('Yes', 'yes'), Choice('No', 'no')]),
            Node('yes', 'tree_result', text='Talked', params={'index': 0}, next='after'),
            Node('no', 'tree_result', params={'index': 1}, next='after'),
            Node('after', 'tree_node', text='Lunch'), Node('say', text='Lunch time'))

    def test_scenes_results_and_choice_labels_build_the_episodes_own_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            s = session_in(self.story(), directory)
            self.assertEqual(s.advance().name, 'choice')
            view = s.engine.dt_view
            self.assertTrue(view.enabled)
            self.assertEqual((view.root.node_type, view.root.lower_label), (1215, 'Meet Beth'))
            self.assertEqual(view.root.choice_labels, {0: 'Yes', 1: 'No'})
            self.assertEqual(answer_screen(s, 1).details['text'], 'Lunch time')
            self.assertEqual((view.root.result_index, view.root.result_labels), (1, {1: '1'}))
            self.assertEqual(view.root.children[1].lower_label, 'Lunch')
            sha = s.resources.identity['episode_sha256']
            library = Path(directory)
            self.assertTrue((library / 'dtview' / f'{sha}.json').exists())
            self.assertEqual(sorted(path.name for path in (library / 'dtsaves' / sha).iterdir()), ['1.json.gz', '2.json.gz'])
            self.assertFalse((library / 'dtview_tree.json').exists())          # Football Star's tree is untouched
            again = session_in(self.story(), directory)
            again.advance()
            answer_screen(again, 0)
            self.assertEqual(again.engine.dt_view.root.result_labels, {1: '1', 0: 'Talked'})
            restored = again.warp(again.engine.dt_view.root)
            self.assertEqual(restored.pending.name, 'choice')

    def test_scenes_and_results_must_alternate_on_every_path(self):
        cases = (
            ([Node('a', 'tree_node', text='A', params={'type': 1215}), Node('b', 'tree_node', text='B')],
             'still waits'),
            ([Node('a', 'tree_node', text='A'), Node('b', 'tree_result')], 'must follow'),
            ([Node('a', 'tree_node', text='A', params={'type': 1215}), Node('b', 'tree_result', params={'index': 2})],
             'does not exist'),
            ([Node('a', 'tree_node', text='A', params={'type': 1215}), Node('b', 'tree', params={'action': 'join'})],
             'still waits'),
            ([Node('a', 'tree_node', text='A', params={'condition': 0x4b})], 'native tests'),
        )
        for nodes, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ProjectError, message):
                compile_project(sequence(*nodes))

    def test_the_tree_type_table_matches_the_runtime_layout(self):
        from exp_runtime.creator.compiler import TREE_AWAITING, TREE_EXITS
        from exp_runtime.dt_layout import SPECS
        from exp_runtime.dtview_faceplace import AWAITING_NODES
        self.assertEqual(TREE_EXITS, {key: spec.exits for key, spec in SPECS.items() if key != 0x4c8})
        self.assertEqual(TREE_AWAITING, range(AWAITING_NODES[0], AWAITING_NODES[1] + 1))


if __name__ == '__main__':
    unittest.main()
