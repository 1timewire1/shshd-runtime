"""The Claire Hart round on screen (Claire Hart plan Stage 3, step 3; desktop_claire_round.py), on a small made-up add-on:
the view (fit to the frame's height, zoom 1-2x, panning), the hit test (HUD pieces, the edge arrows, the scene's sprites by
their alpha), a new mark brought into view, and whole frames drawn at 3:4 and 9:21."""
import io
import json
import os
from types import SimpleNamespace
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame

from exp_runtime import claire_rounds as cr
from exp_runtime.randomness import Random48

HUD = ('cmp_UIbar_top', 'cmp_UIbar_bottom', 'icn_star', 'icn_menu', 'ui-top-combobar', 'ui-top-combobarfrozen', 'extraobjs',
       'zoom', 'time', 'clicks', 'hint_empty_back', 'hint_glass_reflection', 'panel_background', 'panel_summary', 'STAR')


def png(size, colour):
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill(colour)
    out = io.BytesIO()
    pygame.image.save(surface, out, 'piece.png')
    return out.getvalue()


def an_addon(objects=8):
    """chcrounds and chc as {addon: {resource: bytes}}: a 1026 x 770 scene with `objects` 20 x 20 opaque sprites in a row."""
    resources = {26001: png((1026, 770), (40, 60, 80, 255))}
    sprites, entries = [], []
    for i in range(objects):
        sprites += [png((20, 20), (200, 10 * i, 0, 255)), png((40, 40), (255, 255, 0, 255))]
        entries.append([f'Thing {i}', [2 * i, 20, 20, 100 + 100 * i, 300], [2 * i + 1, 40, 40, 90 + 100 * i, 290], [0, 0]])
    resources[27001] = cr.encode_sprite_pack(sprites)
    hud, resource = {}, 26800
    sizes = {'cmp_UIbar_top': (800, 41), 'cmp_UIbar_bottom': (800, 131), 'panel_summary': (372, 310)}
    for name in HUD:
        resources[resource] = png(sizes.get(name, (60, 60)), (0, 120, 120, 255))
        hud[name] = resource
        resource += 1
    for animation in ('vfx_HintFill', 'vfx_hint_starburst', 'vfx_hint_tail', 'vfx_explosion', 'vfx_sparkles'):
        resources[resource] = cr.encode_sprite_pack([png((40, 40), (0, 255, 0, 255))] * 3)
        hud[animation] = [resource, 3]
        resource += 1
    resources[26000] = json.dumps({'version': 1, 'hud': hud, 'scenes': {'Office': {
        'base': 26001, 'sprites': 27001, 'size': [1026, 770], 'objects': entries}}}).encode()
    path = pygame.font.get_default_font()
    with open(path if os.path.exists(path) else os.path.join(os.path.dirname(pygame.__file__), path), 'rb') as file:
        font = file.read()
    chc = {28004: font, 28005: font, 29106: png((209, 57), (0, 160, 0, 255)), 29107: png((209, 57), (0, 120, 0, 255))}
    return {'chcrounds': resources, 'chc': chc}, [e[0] for e in entries]


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def setUp(self):
        from exp_runtime.desktop_claire_round import ClaireRoundRenderer
        archives, self.names = an_addon()
        library = SimpleNamespace(addon_resource=lambda addon, resource: archives[addon].get(resource))
        self.renderer = ClaireRoundRenderer(SimpleNamespace(library=library))
        self.game = cr.ClaireRound.opened('Office', self.names, [], Random48(1))

    def test_the_scene_fits_the_frames_height_and_pans(self):
        from exp_runtime.desktop_claire_round import RoundView
        view = RoundView((1026, 770), (768, 1024))
        view.clamp()
        self.assertAlmostEqual(view.scale, 1024 / 770)
        self.assertEqual(view.to_scene(384, 512), (513, 385))             # centred
        view.pan(-10000, 0)                                                # as far right as it goes
        left, _, width, _ = view.source()
        self.assertAlmostEqual(left + width, 1026)
        view.zoom_at(5, 0, 0)
        self.assertEqual(view.zoom, 2.0)                                   # 1x to 2x
        x, y = view.to_canvas(*view.to_scene(100, 200))
        self.assertAlmostEqual(x, 100)
        self.assertAlmostEqual(y, 200)

    def test_a_scene_a_hair_wider_than_the_frame_fits_its_width(self):
        """(owner, 2026-11-25): a 4:3 frame's arrows panned a pixel or two; now nothing to pan, so no arrows."""
        from exp_runtime.desktop_claire_round import RoundView
        view = RoundView((1026, 770), (1404, 1056))                         # (1,407 wide at its height)
        view.clamp()
        left, _, width, _ = view.source()
        self.assertAlmostEqual(left, 0)
        self.assertAlmostEqual(width, 1026)
        wide = RoundView((1026, 770), (1300, 1056))                        # (well wider: it pans as before)
        self.assertAlmostEqual(wide.scale, 1056 / 770)

    def test_a_tap_hits_hud_pieces_arrows_and_sprites(self):
        r, game = self.renderer, self.game
        r.draw_game(game)
        self.assertEqual(r.hit(game, *r.orb_rect().center), ('hint',))
        self.assertEqual(r.hit(game, *r.segment_rects()[cr.CLAIRVOYANCE].center), ('powerup', cr.CLAIRVOYANCE))
        self.assertEqual(r.hit(game, *r.label_rect(2).center), ('label', 2))
        self.assertEqual(r.hit(game, *r.arrows()[1].center), ('arrow', 1))
        r.view.centre_on(310, 310)
        r.draw_game(game)
        x, y = r.view.to_canvas(310, 310)                                  # object 2's sprite
        self.assertEqual(r.hit(game, x, y), ('scene', [2]))
        bare = r.view.to_canvas(370, 200)
        self.assertEqual(r.hit(game, *bare), ('scene', []))

    def test_an_arrow_goes_at_its_edge(self):
        r, game = self.renderer, self.game
        r.draw_game(game)
        self.assertTrue(r.arrow_shown(-1) and r.arrow_shown(1))         # centred: both ways
        r.view.pan(10000, 0)                                               # as far left as it goes
        self.assertFalse(r.arrow_shown(-1))
        self.assertTrue(r.arrow_shown(1))
        self.assertNotEqual(r.hit(game, *r.arrows()[0].center)[0], 'arrow')        # (a tap there is on the scene)
        r.held = -1
        r.draw_game(game, 100)
        self.assertEqual(r.held, 0)                                        # (held at the edge: it stops)

    def test_a_new_mark_comes_into_view(self):
        r, game = self.renderer, self.game
        r.draw_game(game)
        r.view.pan(-10000, 0)                                              # scrolled to the far right
        game.slots[0] = 0
        game.hint_target = 0                                               # object 0, at the far left
        r.draw_game(game)
        x, _ = r.view.to_canvas(*r.mark_centre(game, 0))
        self.assertTrue(0 <= x <= 768)

    def test_a_find_trails_to_its_name_and_a_hint_flies_from_the_orb(self):
        from exp_runtime import desktop_claire_round as dcr
        r, game = self.renderer, self.game
        r.draw_game(game, 16)
        game.tap([game.listed[1]])
        r.draw_game(game, 16)
        trail = [e for e in r.effects if e[0] == 'trail']
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0][2][1], r.label_point(1))                 # to its own name
        game.hint(Random48(3))
        r.draw_game(game, 16)
        self.assertEqual(sorted(e[0] for e in r.effects), ['explosion', 'hint', 'trail'])
        self.assertTrue(r.flying(game.hint_target))                       # the star isn't on its object yet
        r.draw_game(game, dcr.TRAIL_MS + 2000)
        self.assertEqual(r.effects, [])                                    # all over
        middle = r.catmull_rom(((0, 0), (10, -20), (20, 0)), 0.5)
        self.assertEqual(middle, (10, -20))                                # the curve goes through its middle point

    def test_whole_frames_draw_at_3_4_and_9_21(self):
        r, game = self.renderer, self.game
        for units in ((384, 512), (384, 896)):
            r.frame_units = units
            r.draw_game(game, 16)
            self.assertEqual(r.canvas.get_size(), (768, 1024 if units[1] == 512 else 1792))
        game.tap([game.listed[0]])
        r.draw_game(game, 100)                                             # a find popping
        game.over = True
        r.draw_game(game, 16)                                              # the Level Summary
        self.assertEqual(r.hit(game, *r.summary_rects()[2].center), ('continue',))

    def test_a_taller_frame_grows_the_hud_and_every_piece_still_takes_its_tap(self):
        """Rounds plan R7 (owner, 2026-11-21, B): Classic's HUD as it was at 3:4; at 20:9 the bottom bar, the wheel, the
        names and the summary grow, the top bar sits below a phone's status bar, and taps find each piece where it's drawn."""
        from exp_runtime.desktop_claire_round import BOTTOM_BAR, TOP_BAR
        r, game = self.renderer, self.game
        r.frame_units = (384, 512)
        r.draw_game(game, 16)
        k = r.k
        self.assertEqual((r.kb, r.kt, r.ku), (k, k, k))                  # (3:4: Classic's sizes, unchanged)
        self.assertAlmostEqual(r.bar_top(), r.canvas.get_height() - BOTTOM_BAR * k)
        self.assertAlmostEqual(r.design(400, 50, bottom=True)[0], 400 * k)
        r.frame_units, r.top_pad = (384, 853), 47
        r.draw_game(game, 16)
        self.assertGreater(r.kb, 1.4 * k)
        self.assertGreater(r.kt, 1.25 * k)
        self.assertAlmostEqual(r.summary_rects()[0].width / r.canvas.get_width(), 0.88, delta=0.01)    # (Classic's 57.5%)
        self.assertAlmostEqual(r.top_bar_bottom(), 47 + TOP_BAR * r.kt)
        self.assertEqual(r.hit(game, 300, 20), None)                       # (the strip under the status bar: no scene tap)
        self.assertEqual(r.hit(game, *r.orb_rect().center), ('hint',))
        for powerup, rect in r.segment_rects().items():
            self.assertEqual(r.hit(game, *rect.center), ('powerup', powerup))
        for slot in range(len(game.slots)):
            self.assertEqual(r.hit(game, *r.label_rect(slot).center), ('label', slot))
        self.assertEqual(r.hit(game, *r.design(25, 91, bottom=True)), ('menu',))
        self.assertTrue(all(rect.right <= r.canvas.get_width() for rect in r.segment_rects().values()))

    def test_zoomed_in_the_scene_pans_out_from_under_the_bars(self):
        """(owner, 2026-11-25) an object at the scene's top or bottom edge stayed half under a bar even at 2x: zoomed in,
        the scene's edge may come as far as the bar's inner edge; at 1x it stays as it was."""
        r, game = self.renderer, self.game
        r.frame_units = (384, 512)
        r.draw_game(game, 16)
        r.view.centre_on(513, 0)
        self.assertAlmostEqual(r.view.to_canvas(513, 0)[1], 0)               # (1x: the scene fills the frame's height)
        r.view.zoom_at(1.0, 384, 512)
        self.assertEqual(r.view.zoom, 2.0)
        r.view.centre_on(513, 0)
        self.assertAlmostEqual(r.view.to_canvas(513, 0)[1], r.top_bar_bottom(), places=3)
        r.view.centre_on(513, 770)
        self.assertAlmostEqual(r.view.to_canvas(513, 770)[1], r.bar_top(), places=3)
        r.draw_game(game, 16)                                                # (drawn with the black past the edge)
        r.view.zoom_at(-1.0, 384, 512)
        self.assertAlmostEqual(r.view.to_canvas(513, 770)[1], r.canvas.get_height())     # (back at 1x: as before)

    def test_names_fit_their_columns_in_a_tall_frame(self):
        """(owner's audit, 2026-11-25) at 9:20 the grown text met in the narrowed bar: each name's room stops short of its
        neighbours' and of the wheel; at 3:4 the rooms hold every name Classic has (its widest is 156 px)."""
        r, game = self.renderer, self.game
        for units, least in (((384, 512), 156), ((384, 853), 100)):
            r.frame_units = units
            r.draw_game(game, 16)
            columns = sorted({(round(r.label_point(s)[0]), round(r.label_room(s))) for s in range(len(game.slots))})
            self.assertEqual(len(columns), 3)
            for (x1, room1), (x2, room2) in zip(columns, columns[1:]):
                self.assertLessEqual(x1 + room1 / 2, x2 - room2 / 2)
            wheel = min([r.orb_rect().left] + [rect.left for rect in r.segment_rects().values()])
            self.assertLessEqual(columns[-1][0] + columns[-1][1] / 2, wheel)
            self.assertGreaterEqual(min(room for _, room in columns), least)

    def test_the_score_shows_the_bar_arts_star_only(self):
        """R7, seen in passing: the top bar's art has the score's star, and the renderer drew a second beside it."""
        r, game = self.renderer, self.game
        asked = []
        hud = r.hud
        r.hud = lambda name: (asked.append(name), hud(name))[1]
        r.frame_units = (384, 512)
        r.draw_game(game, 16)
        self.assertNotIn('icn_star', asked)

    def test_a_preloaded_round_decodes_nothing_on_its_first_frame(self):
        """Owner, 2026-11-21: the round's art read while its skip prompt shows, a piece a step (the g54 held ~200 ms)."""
        from unittest import mock
        r, game = self.renderer, self.game
        steps = list(r.preload_steps(game))
        self.assertGreater(len(steps), len(self.names))                    # (a step a sprite, and more)
        real, loads = pygame.image.load, []

        def counted(*args, **kwargs):
            loads.append(args)
            return real(*args, **kwargs)
        with mock.patch.object(pygame.image, 'load', counted):
            r.draw_game(game, 16)
        self.assertEqual(loads, [])
        self.assertIsNotNone(r.view)
        fresh = type(r)(r.resources)                                       # (without the preload, the first frame reads it all)
        with mock.patch.object(pygame.image, 'load', counted):
            fresh.draw_game(game, 16)
        self.assertGreater(len(loads), len(self.names))


if __name__ == '__main__':
    unittest.main()
