"""graphics.faded: fading a surface with its own per-pixel alpha multiplies that alpha (macOS lost it under SDL's
whole-surface alpha: the main menu title's white box), and never changes the surface it was given."""
import importlib.util
import os
import unittest


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class FadedTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        import pygame
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.quit)
        self.pygame = pygame
        from exp_runtime.graphics import faded
        self.faded = faded

    def logo(self):
        """A red square on a transparent field, as the title art is."""
        pygame = self.pygame
        image = pygame.Surface((4, 4), pygame.SRCALPHA)
        image.fill((0, 0, 0, 0))
        image.fill((255, 0, 0, 255), (1, 1, 2, 2))
        return image

    def test_per_pixel_alpha_is_multiplied_on_a_copy(self):
        image = self.logo()
        half = self.faded(image, 128)
        self.assertIsNot(half, image)
        self.assertEqual(tuple(image.get_at((1, 1))), (255, 0, 0, 255))      # the original is untouched
        self.assertIn(half.get_alpha(), (None, 255))                           # no whole-surface alpha involved
        self.assertEqual(half.get_at((0, 0)).a, 0)                             # the transparent field stays clear
        self.assertAlmostEqual(half.get_at((1, 1)).a, 128, delta=1)
        # Drawn over white, only the square tints it: no box around the image.
        white = self.pygame.Surface((4, 4))
        white.fill((255, 255, 255))
        white.blit(half, (0, 0))
        self.assertEqual(tuple(white.get_at((0, 0)))[:3], (255, 255, 255))
        self.assertAlmostEqual(white.get_at((1, 1)).g, 127, delta=2)

    def test_opaque_surfaces_keep_whole_surface_alpha_and_full_opacity_changes_nothing(self):
        pygame = self.pygame
        shade = pygame.Surface((2, 2))                     # black, no per-pixel alpha
        white = pygame.Surface((2, 2))

        def drawn():
            white.fill((255, 255, 255))
            white.blit(shade, (0, 0))
            return white.get_at((0, 0)).r

        self.assertIs(self.faded(shade, 100), shade)
        self.assertAlmostEqual(drawn(), 155, delta=2)      # the whole-surface alpha, as set_alpha gave
        self.assertIs(self.faded(shade, 255), shade)
        self.assertEqual(drawn(), 0)                        # opaque again
        image = self.logo()
        self.assertIs(self.faded(image, None), image)
        self.assertIs(self.faded(image, 300), image)
        self.assertEqual(tuple(image.get_at((1, 1))), (255, 0, 0, 255))


    def test_opaque_raises_an_alpha_0_canvas_and_keeps_its_colour(self):
        # macOS: the main menu's canvas carried alpha 0, so the picker lists' zoom showed black around their card.
        from exp_runtime.graphics import opaque
        pygame = self.pygame
        canvas = pygame.Surface((3, 3), pygame.SRCALPHA)
        canvas.fill((120, 60, 30, 0))
        self.assertIs(opaque(canvas), canvas)
        self.assertEqual(tuple(canvas.get_at((1, 1))), (120, 60, 30, 255))
        plain = pygame.Surface((3, 3))
        plain.fill((10, 20, 30))
        opaque(plain)                                   # no alpha channel: left as it is
        self.assertEqual(tuple(plain.get_at((0, 0)))[:3], (10, 20, 30))


if __name__ == '__main__':
    unittest.main()
