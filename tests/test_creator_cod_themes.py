"""The Creator's colours for Cause of Death (owner, 2026-11-19): CoD has its grey box only, with the speaker's name standard
(1, every character in its episodes) or upright (3: its narrator, Holiday Interlude's Ghostly Specter); its pink-red 2 is never
used. A CoD project's characters and lines come out as 1 or 3; SHS keeps all four."""
import unittest

from exp_runtime.creator import Character, Node, Project
from exp_runtime.creator.compiler import COD_THEMES, game_theme
from exp_runtime.creator import operations
from test_creator import image_bytes, session_for
from test_creator_features import sequence


def project(game):
    p = sequence(*(Node(f'line{theme}', text=f'Theme {theme}.', character=f'c{theme}') for theme in range(4)), game=game)
    face = p.add_image('Face', image_bytes())
    p.characters = [Character(f'c{theme}', f'Speaker {theme}', face.id, theme) for theme in range(4)]
    return p


def themes(p):
    session = session_for(p)
    session.advance()
    engine = session.engine
    return [engine.numbers.get(engine.number_key(number, 651)) for number in range(1, 5)]


class CodThemeTests(unittest.TestCase):
    def test_cod_lines_take_its_standard_or_upright_name(self):
        self.assertEqual(COD_THEMES, {1: 'Standard', 3: 'Upright name'})
        self.assertEqual(themes(project('cod')), [1, 1, 1, 3])
        self.assertEqual(themes(project('shs')), [0, 1, 2, 3])
        self.assertEqual([game_theme(Project(game='cod'), t) for t in range(4)], [1, 1, 1, 3])

    def test_new_cod_characters_start_standard(self):
        for game, theme in (('cod', 1), ('shs', 2)):
            p = Project(game=game)
            operations.apply(None, p, dict(op='character', id='mal', changes=dict(name='Mal')))
            self.assertEqual(p.characters[0].theme, theme)


if __name__ == '__main__':
    unittest.main()
