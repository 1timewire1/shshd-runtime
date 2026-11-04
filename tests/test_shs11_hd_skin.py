"""SHS '11's minigames in the HD word game's look: its switch, what a cube shows and where a tap lands. Only the look: the rules are
test_shs11_memory.py's and test_shs11_reflex.py's. Its art is the player's own, so what it draws is checked by eye."""
import importlib.util
import unittest
from types import SimpleNamespace

from exp_runtime.shs11_games import BLANK, HIDDEN, LOOK, MemoryGame, PLAY, RIGHT, ReflexGame, WRONG

HAS_PILLOW = importlib.util.find_spec('PIL') is not None
ROW = [5, 10, 20, 5, 13, 3, 8, 25, 40, 20, 15, 300, 2100]


@unittest.skipUnless(HAS_PILLOW, 'needs Pillow')
class CubeTests(unittest.TestCase):
    def renderer(self):
        from exp_runtime.desktop_shs11_hd import Shs11HdRenderer
        import pygame
        pygame.init()
        pygame.display.set_mode((64, 64))
        return Shs11HdRenderer

    def test_a_memory_cell_shows_its_state(self):
        cell = self.renderer().memory_cell
        game = MemoryGame.opened([['Elf!', 'ELF', 20, 10, 600, 4000]], 60, 300)
        game.word, game.cells, game.order = 'ELF', ['E', 'L', 'F', *'XXXXXX'], [0, 1, 2]
        self.assertEqual(cell(game, 0), ('', 0))
        game.phase, game.landing = LOOK, [700, 400]
        self.assertEqual(cell(game, 1), ('L', 0))
        self.assertEqual(cell(game, 2), ('', 0))                # not dealt yet
        game.phase = PLAY
        game.shows = [HIDDEN, RIGHT, BLANK, WRONG, *[BLANK] * 5]
        self.assertEqual(cell(game, 0), ('?', 0))
        self.assertEqual(cell(game, 1), ('L', 2))
        self.assertEqual(cell(game, 3), ('X', 4))

    def test_a_reflex_cell_shows_its_icon_and_bars_once_its_in_and_until_it_shuts(self):
        cell = self.renderer().reflex_cell
        game = ReflexGame.opened([ROW], 60, 350)
        game.row = list(ROW)
        self.assertEqual(cell(game, 0), ('', 0))
        game.cells[0] = [0, 13, 2, 100, 50, -1]
        self.assertEqual(cell(game, 0), ('', 0))                # still waiting its delay
        game.cells[0][4] = 200
        self.assertEqual(cell(game, 0), (chr(0xE000 + 132), 0))
        game.shows[0] = RIGHT
        self.assertEqual(cell(game, 0)[1], 2)
        game.shows[0] = WRONG
        self.assertEqual(cell(game, 0)[1], 4)
        game.cells[0][5] = 0
        self.assertEqual(cell(game, 0)[0], '')

    def test_a_tap_lands_on_the_cube_under_it(self):
        from exp_runtime.desktop_word_hd import CUBE, GAP, project
        renderer = self.renderer()(SimpleNamespace(library=SimpleNamespace()), None)
        for cell in range(9):
            x, y = project(3, 3, cell % 3 * (CUBE + GAP) + CUBE / 2, cell // 3 * (CUBE + GAP) + CUBE / 2, 0)
            self.assertEqual(renderer.cell_at(x, y), cell)
        self.assertIsNone(renderer.cell_at(5, 5))

    def test_without_the_addon_it_isnt_available(self):
        renderer = self.renderer()(SimpleNamespace(library=SimpleNamespace(addon=lambda name: None)), None)
        self.assertFalse(renderer.available())


class SwitchTests(unittest.TestCase):
    def test_the_switch_is_off_until_asked_for_and_kept(self):
        from exp_runtime.menu import preference_defaults
        self.assertIs(preference_defaults()['word_grid_skin'], False)

    def test_it_wears_11s_tag_and_is_an_add_on_setting(self):
        from exp_runtime.desktop_pause_hd import ADDON_KEYS, WORD_GRID_SKIN_LABEL, switch_badge
        self.assertIn('word_grid_skin', ADDON_KEYS)
        self.assertEqual(WORD_GRID_SKIN_LABEL, 'Use Word Grid Skin')
        self.assertEqual(switch_badge('word_grid_skin')[0], "'11")

    @unittest.skipUnless(HAS_PILLOW, 'needs Pillow')
    def test_it_picks_who_draws_only_with_its_art_there(self):
        from exp_runtime.desktop import Desktop
        own = SimpleNamespace(available=lambda: True)
        ui = SimpleNamespace(word_grid_skin=True, shs11_hd=own, shs11_memory_renderer='memory', shs11_reflex_renderer='reflex')
        action = SimpleNamespace(name='shs11_reflex')
        self.assertIs(Desktop.shs11_renderer(ui, action), own)
        ui.word_grid_skin = False
        self.assertEqual(Desktop.shs11_renderer(ui, action), 'reflex')
        ui.word_grid_skin, own.available = True, lambda: False
        self.assertEqual(Desktop.shs11_renderer(ui, SimpleNamespace(name='shs11_memory')), 'memory')


if __name__ == '__main__':
    unittest.main()
