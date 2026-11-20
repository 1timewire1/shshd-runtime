"""Claire Hart plan Stage 0, F: Claire Hart's translations darken their backdrops as the game drew them (Classic's backdrop
node colour, 110/255), at draw time, while the shared Dim Backdrops switch is on; the add-on keeps the full-brightness art."""
import os
from types import SimpleNamespace
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame

from exp_runtime.desktop import Desktop


def resources(pack):
    return SimpleNamespace(record={'pack_id': pack}, library=SimpleNamespace(game_id='cod'))


def desktop(pack, on=True):
    game = SimpleNamespace(_session=SimpleNamespace(resources=resources(pack)), dim_backdrops=on)
    game.session = game._session
    game.backdrop_dim = lambda: Desktop.backdrop_dim(game)
    game.dim_switch = lambda: Desktop.dim_switch(game)
    return game


class BackdropDimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def picture(self):
        surface = pygame.Surface((4, 4))
        surface.fill((200, 100, 255))
        return surface

    def test_claire_hart_classic_dims_to_110(self):
        from exp_runtime.cod import profile
        self.assertEqual(profile.TRANSLATED_BACKDROP_DIM, {31500: 110})
        game = desktop(31500)
        self.assertTrue(game.dim_switch())
        picture = self.picture()
        dark = Desktop._dimmed(game, picture)
        self.assertEqual(tuple(dark.get_at((0, 0)))[:3], tuple(round(c * 110 / 255) for c in (200, 100, 255)))
        self.assertEqual(tuple(picture.get_at((0, 0)))[:3], (200, 100, 255))         # the art itself is left as it is
        self.assertIs(Desktop._dimmed(game, picture), dark)                          # made once a picture

    def test_the_switch_off_or_another_pack_draws_it_as_it_is(self):
        picture = self.picture()
        self.assertIs(Desktop._dimmed(desktop(31500, on=False), picture), picture)
        other = desktop(31400)
        self.assertFalse(other.dim_switch())
        self.assertIs(Desktop._dimmed(other, picture), picture)


if __name__ == '__main__':
    unittest.main()
