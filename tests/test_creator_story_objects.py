"""The Creator's Story object picture node (Claire Hart plan Stage 0, P): service 225 where service 70 selector 206 says the
player draws it (Cause of Death here), else a message naming the item; Clear empties the row."""
import unittest

from exp_runtime.creator import Node, ProjectError, compile_project
from test_creator import image_bytes, session_for
from test_creator_features import sequence


def story(game, *nodes):
    project = sequence(*nodes, game=game)
    picture = project.add_image('Push Broom', image_bytes())
    for node in project.nodes:
        if node.kind == 'story_object' and not node.params.get('clear'):
            node.asset = picture.id
    return project, picture.id


def found(**params):
    return Node('found', 'story_object', text='Push Broom', params=params)


class CreatorStoryObjectTests(unittest.TestCase):
    def test_cause_of_death_shows_the_picture_with_the_next_line(self):
        project, picture = story('cod', found(), Node('say', text="These are Ed's things."))
        action = session_for(project).advance()
        self.assertEqual((action.name, action.details.get('story_objects')), ('dialogue', [picture]))

    def test_a_player_without_it_shows_a_message_naming_the_item(self):
        project, _ = story('shs', found(title='Found'), Node('say', text="These are Ed's things."))
        session = session_for(project)
        self.assertEqual(session.advance().name, 'message_panel')
        self.assertIn('Push Broom', repr(session.engine.message_panel))

    def test_clear_empties_the_row(self):
        project, picture = story('cod', found(), Node('one', text='Look.'), Node('gone', 'story_object', params={'clear': True}),
                                 Node('two', text='Gone now.'))
        session = session_for(project)
        first = session.advance()
        self.assertEqual(first.details.get('story_objects'), [picture])
        session.tick(3000)
        second = session.answer()
        while second.name != 'dialogue' or second is first:
            session.tick(3000)
            second = session.answer()
        self.assertEqual((second.details['text'], second.details.get('story_objects')), ('Gone now.', None))

    def test_a_picture_needs_its_image_and_a_name(self):
        project = sequence(found(), game='cod')
        with self.assertRaisesRegex(ProjectError, 'choose the picture'):
            compile_project(project)
        project, _ = story('cod', Node('found', 'story_object', text=' '))
        with self.assertRaisesRegex(ProjectError, 'name the item'):
            compile_project(project)


if __name__ == '__main__':
    unittest.main()
