"""Secret in the Shadows' round on screen (Claire Hart plan S3 step 4; desktop_shadows_round.py), on a small made-up add-on:
the HUD's buttons, the scene's objects and the Gold Key, the close-up (its hotspot, backing, objects and close button; fitted
to a narrow frame), the sensor (it resets the zoom but doesn't look for the player), How To Play's pages, and whole frames
at 3:4 and 9:21 in every state (sensor, spotlight, close-up, multi-part note, spam lock, summary, tutorial)."""
import collections
import io
import os
from types import SimpleNamespace
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame

from exp_runtime import claire_rounds as cr
from exp_runtime import shadows_rounds as sr
from exp_runtime.randomness import Random48

KINDS = [sr.ORDINARY] * 10 + [sr.GOLD_KEY] + [sr.CLOSE_UP] * 2 + [sr.PART, sr.PART, sr.WHOLE]


def png(size, colour):
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill(colour)
    out = io.BytesIO()
    pygame.image.save(surface, out, 'piece.png')
    return out.getvalue()


def an_addon():
    """ch2rounds as {resource: bytes} and its spec: a 1026 x 770 scene, its objects 20 x 20 sprites in a row (the close-up's
    two inside its backing, at 600-800 x 100-250), the hotspot at 900, 600."""
    resources = {26001: png((1026, 770), (40, 60, 80, 255)), 28000: png((60, 60), (0, 120, 120, 255)),
                 28950: png((800, 600), (20, 20, 20, 255)), 28951: png((100, 60), (200, 200, 0, 255)),
                 28952: png((300, 300), (120, 0, 120, 255))}
    path = pygame.font.get_default_font()
    with open(path if os.path.exists(path) else os.path.join(os.path.dirname(pygame.__file__), path), 'rb') as file:
        resources[28800] = file.read()
    sprites, objects = [], []

    def sprite(size, at):
        sprites.append(png(size, (200, 10 * len(sprites) % 255, 0, 255)))
        return [len(sprites) - 1, size[0], size[1], at[0], at[1]]
    for i, kind in enumerate(KINDS):
        at = (650 + 60 * (i - 11), 150) if kind == sr.CLOSE_UP else (40 + 60 * i, 400)
        normal = None if kind == sr.WHOLE else sprite((20, 20), at)
        objects.append([f'Thing {i}', kind, normal, sprite((24, 24), at), [0, 0]])
    close_up = {'backing': sprite((300, 200), (580, 80)), 'cutout': sprite((40, 40), (900, 600)),
                'glow': sprite((40, 40), (900, 600))}
    resources[27001] = cr.encode_sprite_pack(sprites)
    spec = {'version': 1, 'hud': collections.defaultdict(lambda: 28000), 'fonts': collections.defaultdict(lambda: 28800),
            'sounds': {}, 'spotlight': 28000,
            'scenes': {'Bedroom': {'base': 26001, 'sprites': 27001, 'size': [1026, 770], 'objects': objects,
                                   'parts': {'15': [13, 14]}, 'close_up': close_up}},
            'tutorial': {'pictures': {'dark': [28950, 800, 600], 'list': [28951, 100, 60]}, 'claire': [28952, 300, 300],
                         'pages': [dict(text='First line.', name='Claire', sprites=[['dark', 0, 0]], claire='right'),
                                   dict(text='Second.', name='Claire', sprites=[['dark', 0, 0], ['list', -20, -140]],
                                        claire='left')]}}
    return resources, spec, [o[0] for o in objects]


class ShadowsRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def setUp(self):
        from exp_runtime.desktop_shadows_round import ShadowsRoundRenderer
        resources, spec, names = an_addon()
        library = SimpleNamespace(addon_resource=lambda addon, resource: resources.get(resource))
        self.renderer = ShadowsRoundRenderer(SimpleNamespace(library=library))
        self.renderer._specs['ch2rounds'] = spec
        self.game = sr.ShadowsRound.opened('Bedroom', names, KINDS, {15: [13, 14]}, [15], Random48(1))

    def test_the_bars_buttons(self):
        r, game = self.renderer, self.game
        r.draw_game(game)
        self.assertEqual(r.hit(game, *r.sensor_rect().center), ('sensor',))
        self.assertEqual(r.hit(game, *r.gear_rect().center), ('menu',))
        self.assertEqual(r.hit(game, *r.help_rect().center), ('help',))
        self.assertEqual(r.hit(game, *r.stopwatch_rect().center), ('powerup', sr.TIME_WARP))
        self.assertEqual(r.hit(game, *r.small_rect((292.5, 28)).center), ('powerup', sr.HINT))
        self.assertEqual(r.hit(game, *r.small_rect((359.3, 28)).center), ('powerup', sr.CLAIRVOYANCE))

    def test_the_scene_the_key_and_the_hotspot(self):
        r, game = self.renderer, self.game
        r.draw_game(game)
        r.view.centre_on(450, 410)
        r.draw_game(game)
        self.assertEqual(r.hit(game, *r.view.to_canvas(410, 410)), ('scene', [6]))
        self.assertEqual(r.hit(game, *r.view.to_canvas(650, 410)), ('scene', [10]))     # the Gold Key
        self.assertEqual(r.hit(game, *r.view.to_canvas(370, 300)), ('scene', []))
        r.view.centre_on(900, 600)
        r.draw_game(game)
        self.assertEqual(r.hit(game, *r.view.to_canvas(920, 620)), ('open_pip',))
        self.assertEqual(r.hit(game, *r.view.to_canvas(650, 160)), ('scene', []))       # (closed: its objects hidden)

    def test_the_open_close_up_fits_the_frame_and_takes_its_own_taps(self):
        r, game = self.renderer, self.game
        game.open_pip()
        r.draw_game(game, 400)
        rect = r.pip_rect(game)
        self.assertTrue(r.canvas.get_rect().contains(rect))
        self.assertTrue(r.canvas.get_rect().contains(r.close_rect(game)))
        self.assertEqual(r.hit(game, *r.close_rect(game).center), ('close_pip',))
        spot = r.pip_spot(game, r.objects(game)[11][0])
        self.assertEqual(r.hit(game, *spot.center), ('scene', [11]))
        self.assertEqual(r.hit(game, rect.right - 5, rect.bottom - 5), ('backing',))
        self.assertEqual(r.hit(game, 5, r.top_bar_bottom() + 5), ('close_pip',))           # the vignette

    def test_the_sensor_resets_the_zoom_without_looking(self):
        r, game = self.renderer, self.game
        r.draw_game(game)
        r.view.zoom_at(0.5, 300, 300)
        before = (r.view.cx, r.view.cy)
        game.use_sensor()
        r.draw_game(game, 16)
        self.assertEqual(r.view.zoom, 1.0)
        self.assertTrue(r.zoom_locked)
        target = r.sprite_box(game, game.sensor_target)[:2]
        self.assertNotEqual((round(r.view.cx), round(r.view.cy)), tuple(round(v) for v in target))
        self.assertIsNotNone(before)

    def test_how_to_play_turns_its_pages_and_closes(self):
        r, game = self.renderer, self.game
        r.open_tutorial()
        r.draw_game(game, 16)
        self.assertEqual(r.hit(game, 10, 10), ('tutorial',))
        r.tutorial_tap()                                    # finishes the line
        self.assertEqual(r.tutorial['page'], 0)
        r.tutorial_tap()                                    # turns the page
        self.assertEqual(r.tutorial['page'], 1)
        r.draw_game(game, 5000)
        r.tutorial_tap()
        self.assertIsNone(r.tutorial)

    def test_whole_frames_draw_at_3_4_and_9_21(self):
        r, game = self.renderer, self.game
        for units in ((384, 512), (384, 896)):
            r.frame_units = units
            r.draw_game(game, 16)
            self.assertEqual(r.canvas.get_size(), (768, round(768 * units[1] / units[0])))
            game.use_sensor()
            r.draw_game(game, 16)
            game.spotlight = True
            r.draw_game(game, 16)
            game.spotlight = False
            game.tap([13])                                  # a multi-part object's first part: its note
            r.draw_game(game, 16)
            game.open_pip()
            r.draw_game(game, 16)
            game.lock_ms = 1000
            r.draw_game(game, 16)
            game.lock_ms = 0
            r.open_tutorial()
            r.draw_game(game, 16)
            r.tutorial = None
            game.over = True
            r.draw_game(game, 16)
            self.assertIsNone(r.hit(game, *r.continue_rect().center))           # ("Scene Cleared!" first)
            r.draw_game(game, 3000)
            self.assertEqual(r.hit(game, *r.continue_rect().center), ('continue',))
            game.over = False
            game.close_pip()


if __name__ == '__main__':
    unittest.main()
