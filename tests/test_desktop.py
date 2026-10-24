import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from exp_runtime.runtime import Session
from test_runtime import Resources, answer_screen, branching_program, host_call, text_words
from test_vm import program as vm_program


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class DesktopTests(unittest.TestCase):
    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user library is not present')
    def test_dialogue_motion_renders_between_states_and_pauses_without_advancing_vm(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as library:
            resources = library.open_episode('The_New_Girl.exp')
            ui = Desktop(Session(resources), audio=False)
            for _ in range(100):
                if (ui.session.pending.name == 'dialogue'
                        and ui.session.engine.dialogue_animation.portrait is not None):
                    break
                answer_screen(ui.session)
            else:
                self.fail('Expected a portrait in the opening scene')
            session = ui.session
            before_vm = session.vm.snapshot()
            ui.tick(250)
            frames = set()
            for _ in range(19):
                ui.render()
                self.assertIsNone(ui.error)
                frames.add(pygame.image.tobytes(ui.canvas, 'RGB'))
                ui.tick(16)
            self.assertGreaterEqual(len(frames), 15)
            self.assertEqual(session.vm.snapshot(), before_vm)
            saved = session.snapshot()
            ui.render()
            pixels = pygame.image.tobytes(ui.canvas, 'RGB')
            self.assertEqual(session.snapshot(), saved)  # Drawing never advances clocks.
            ui.session = Session.from_snapshot(resources, saved)
            ui.render()
            self.assertEqual(pygame.image.tobytes(ui.canvas, 'RGB'), pixels)
            ui.command(('menu',)); ui.tick(2000)
            self.assertEqual(ui.session.snapshot(), saved)
            ui.command(('resume',))
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST)); ui.tick(2000)
            self.assertEqual(ui.session.snapshot(), saved)
            ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
            ui.render()
            token = ui._screen_token()
            for _ in range(2):
                ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
            self.assertNotEqual(ui._screen_token(), token)
            self.assertEqual(ui.session.vm.snapshot(), before_vm)
            ui.tick(1000)
            ui.render()
            self.assertIsNone(ui.error)
            self.assertNotEqual(pygame.image.tobytes(ui.canvas, 'RGB'), pixels)
            self.assertTrue(ui.session.engine.dialogue_animation.complete)
            self.assertEqual(ui.session.vm.snapshot(), before_vm)

    def test_rendering_one_action_never_probes_the_others_availability(self):
        # render()'s renderer-selection used to be one dict literal built from every action's own value --
        # Python evaluates a dict literal's values eagerly, so selecting 'football' by key still ran
        # `self.word_hd.available()`, `self.message_hd.available()`, `self.title_hd.available()` and the
        # loading renderer's own check too, each of which (before `ContentLibrary`'s own hd_raw_resource cache)
        # cost a fresh zip read and zlib decompression per resource checked. Profiled live: over half the frame
        # cost during football/word-grid gameplay came from exactly this.
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        from test_football import resources as football_resources, start_play
        import pygame

        self.addCleanup(pygame.quit)
        session = Session(football_resources(100))
        session.advance()
        start_play(session)
        ui = Desktop(session, audio=False)
        # The synthetic fixture's own Resources stub has no read_asset(), so the standard football renderer's
        # own art loading is beside the point here -- only that render() reaches and uses it without first
        # probing every other renderer's own availability.
        with patch.object(ui.football_renderer, 'draw', return_value=[]) as football_draw, \
             patch.object(ui.word_hd, 'available') as word_available, \
             patch.object(ui.message_hd, 'available') as message_available, \
             patch.object(ui.title_hd, 'available') as title_available, \
             patch.object(ui.loading_hd, 'available') as loading_available, \
             patch.object(ui.picker_hd, 'available') as picker_available:
            ui.render()
            self.assertIsNone(ui.error)
            football_draw.assert_called_once()
            for mock in (word_available, message_available, title_available, loading_available, picker_available):
                mock.assert_not_called()

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user library is not present')
    def test_minigame_input_pause_and_original_art(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        from test_football import resources as football_resources, start_play
        from test_word_grid import resources as grid_resources, play_phase
        from test_minigames import word_resources
        import pygame

        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as library:
            r = library.open_episode('The_New_Girl.exp')
            for fixture in (word_resources(), grid_resources(tutorial=True), football_resources(100)):
                r.programs[25001] = fixture.program(25001)
                ui = Desktop(Session(r), audio=False)
                s = ui.session
                if s.engine.word_grid:
                    play_phase(s)
                elif s.engine.football:
                    start_play(s)
                    for _ in range(5): ui.tick(250)
                else:
                    ui.tick(400)
                ui.window = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
                ui.render(); self.assertIsNone(ui.error)
                saved = s.snapshot()
                ui.command(('menu',)); ui.tick(1000)
                self.assertEqual(s.snapshot(), saved)
                ui.command(('resume',))
                ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST)); ui.tick(1000)
                self.assertEqual(s.snapshot(), saved)
                ui.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))

                def pointer(kind, point):
                    x, y = point
                    pos = (ui.viewport.x + x * ui.viewport.width / 320,
                           ui.viewport.y + y * ui.viewport.height / 480)
                    ui.handle_event(pygame.event.Event(kind, button=1, pos=pos))

                if s.engine.word_grid:
                    for kind, index in [(pygame.MOUSEBUTTONDOWN, 0), (pygame.MOUSEMOTION, 1),
                                        (pygame.MOUSEMOTION, 2)]:
                        pointer(kind, ui.grid_renderer.cells[index][1].center)
                    self.assertEqual(s.engine.word_grid.score, 100)
                    pointer(pygame.MOUSEBUTTONUP, (0, 0))
                elif s.engine.football:
                    game = s.engine.football
                    self.assertTrue(game.targets[0].visible)
                    pointer(pygame.MOUSEBUTTONDOWN, (60, 200))
                    self.assertEqual(game.phase, 4)
                    self.assertEqual(game.down, 1)
                else:
                    page = ui.choice_renderer.page(s)
                    row = page.rows[s.engine.word_game.weights.index(1)]
                    pointer(pygame.MOUSEBUTTONDOWN, row.rect.center)
                    self.assertEqual(s.engine.word_game.score, 0)
                    pointer(pygame.MOUSEBUTTONUP, row.rect.center)
                    self.assertEqual(s.engine.word_game.score, 1)
                ui.render(); self.assertIsNone(ui.error)

    def test_masked_portraits_blend_on_opaque_cocoa_surface(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Raster
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((4, 1))
        # Transparent white, real black artwork, a translucent edge, and a
        # colored pixel that the portrait mask turns into transparent black.
        pixels = bytes((255, 255, 255, 0, 0, 0, 0, 255,
                        50, 80, 110, 128, 90, 200, 15, 255))
        source = pygame.image.frombytes(pixels, (4, 1), 'RGBA')
        renderer = DialogueRenderer(None, None, lambda _: source)
        renderer.pack = lambda _: SimpleNamespace(images=(Raster(4, 1, b'\0\0\0\xff', 'A'),))
        expected = [(120, 150, 180), (0, 0, 0), (85, 115, 145), (120, 150, 180)]
        for alpha_mask in (0, 0xff000000):
            for flipped in (False, True):
                with self.subTest(alpha_mask=alpha_mask, flipped=flipped):
                    # Cocoa's opaque canvas retains an alpha bitmask with
                    # zero alpha bytes, despite not having the SRCALPHA flag.
                    target = pygame.Surface((4, 1), 0, 32,
                                            (0xff0000, 0xff00, 0xff, alpha_mask))
                    target.fill((120, 150, 180, 0))
                    target.blit(renderer.portrait(1, flipped), (0, 0))
                    self.assertEqual([tuple(target.get_at((x, 0))[:3]) for x in range(4)],
                                     expected[::-1] if flipped else expected)

    def test_oversized_hd_portrait_scales_the_mask_instead_of_raising(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Raster
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((256, 300))
        # A 128x150 reference mask (top half kept, bottom half cleared,
        # matching the real Android resource 268) against a portrait 2x its
        # size in both dimensions, the same shape HD's own per-episode
        # portraits take relative to it (see desktop_dialogue._scaled_mask).
        # With no `resources` able to answer android_asset() (None here),
        # portrait() falls back to the fixed ANDROID_MASK_SIZE constant for
        # its scale target -- see test_portrait_scales_to_its_own_android_
        # asset_size_not_the_fixed_mask_constant below for the normal path,
        # which uses this specific portrait's own Android size instead.
        source = pygame.Surface((256, 300), pygame.SRCALPHA)
        source.fill((10, 20, 30, 255))
        renderer = DialogueRenderer(None, None, lambda _: source)
        renderer.pack = lambda _: SimpleNamespace(
            images=(Raster(128, 150, bytes([0] * (128 * 75) + [255] * (128 * 75)), 'A'),))
        image = renderer.portrait(1, False)
        self.assertEqual(image.get_size(), (128, 150))
        self.assertGreater(image.get_at((0, 0))[3], 0)  # kept region stays visible
        self.assertEqual(image.get_at((0, 149))[3], 0)  # cleared region stays transparent

    def test_hd_portraits_draw_at_their_own_2x_size_whatever_the_android_original(self):
        # Real device confirmed twice (reference/football_star_beth_greeting_hd.webp,
        # reference/IMG_0069.PNG): an HD portrait occupies its own pixel size at
        # 2x density -- 226x256 is 113x128 layout units -- not a fit into the
        # Android original's size. Beth's original (113x122) is close enough
        # that the old fit looked right; the player avatar's (94x123) is a
        # different, smaller drawing and came out ~20% too small.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from io import BytesIO
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Raster
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((226, 256))

        def png_bytes(size):
            surface = pygame.Surface(size, pygame.SRCALPHA)
            buffer = BytesIO()
            pygame.image.save(surface, buffer, 'png')
            return buffer.getvalue()

        def portrait(hd_size, android_size, density=1):
            source = pygame.Surface(hd_size, pygame.SRCALPHA)
            source.fill((10, 20, 30, 255))
            resources = SimpleNamespace(android_asset=lambda asset_id: png_bytes(android_size))
            renderer = DialogueRenderer(resources, None, lambda _: source)
            renderer.pack = lambda _: SimpleNamespace(
                images=(Raster(128, 150, bytes([255] * (128 * 150)), 'A'),))
            return renderer.portrait(1, False, density).get_size()

        self.assertEqual(portrait((226, 256), (113, 122)), (113, 128))   # Beth
        self.assertEqual(portrait((226, 256), (94, 123)), (113, 128))    # the player avatar
        self.assertEqual(portrait((226, 256), (94, 123), density=2), (226, 256))
        # Android-density art is left at its own size.
        self.assertEqual(portrait((113, 122), (113, 122)), (113, 122))

    def test_hd_portrait_is_bottom_anchored_and_clipped_by_the_unmirrored_mask(self):
        # SHSPortraitLayer.drawLayer:inContext: (HD 1.4.38): a 256x320-point layer whose bottom is the housing's;
        # the 256x300 mask clips from y 20; the art is drawn at its own size centred with its bottom at y 318, and
        # mirrored after the clip. 1x art (no Android copy, inside the 128x150 mask) is drawn at 2x.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Raster
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        source = pygame.Surface((50, 60), pygame.SRCALPHA)
        source.fill((10, 20, 30, 255))
        source.fill((200, 0, 0, 255), (0, 0, 10, 60))        # a red left edge, to see the mirror
        renderer = DialogueRenderer(None, None, lambda _: source)
        # Clip the mask's left 40 points; keep the rest.
        renderer.pack = lambda _: SimpleNamespace(
            images=(Raster(256, 300, bytes(([255] * 40 + [0] * 216) * 300), 'A'),))
        layer, lift = renderer.hd_portrait(1, False, 2)
        self.assertEqual(layer.get_size(), (256, 320))
        self.assertEqual(lift, 64)
        # 50x60 at 1x is 100x120 points: x from (256-100)/2 = 78, bottom at 318.
        self.assertEqual(layer.get_at((80, 317))[:3], (200, 0, 0))
        self.assertEqual(layer.get_at((100, 198))[3], 255)
        self.assertEqual(layer.get_at((100, 197))[3], 0)
        self.assertEqual(layer.get_at((100, 318))[3], 0)
        # Mirrored, the red edge moves to the right, but the mask's clipped left columns stay on the left.
        mirrored, _ = renderer.hd_portrait(1, True, 2)
        self.assertEqual(mirrored.get_at((175, 317))[:3], (200, 0, 0))
        self.assertEqual(mirrored.get_at((80, 317))[:3], (10, 20, 30))
        tall = pygame.Surface((256, 300), pygame.SRCALPHA)
        tall.fill((10, 20, 30, 255))
        renderer = DialogueRenderer(None, None, lambda _: tall)
        renderer.pack = lambda _: SimpleNamespace(
            images=(Raster(256, 300, bytes(([255] * 40 + [0] * 216) * 300), 'A'),))
        layer, _ = renderer.hd_portrait(1, False, 2)
        self.assertEqual(layer.get_at((39, 300))[3], 0)       # clipped by the mask
        self.assertEqual(layer.get_at((100, 19))[3], 0)       # above the mask's rectangle
        self.assertEqual(layer.get_at((100, 20))[3], 255)

    def test_portrait_art_anchors_to_the_outer_ring_not_the_inner_themed_one(self):
        # Real device confirmed (reference/football_star_beth_greeting_hd.webp):
        # the portrait's own bottom edge should sit level with the *outer*
        # ring (frame 37, a fixed 128px frame shared by every theme), not
        # the smaller inner themed ring (frame 38/39/40, ~105px) -- anchoring
        # to the inner ring left hair spilling out above the outer ring and
        # a visible gap of backdrop below the chin.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.dialogue_animation import DialoguePortrait
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))

        def frame(asset_id, index):
            size = 128 if index == 37 else 105
            return pygame.Surface((size, size), pygame.SRCALPHA)

        renderer = DialogueRenderer(None, None, None)
        renderer.frame_native = frame
        renderer.portrait = lambda asset_id, flipped, density=1, crop=False: pygame.Surface(
            (128, 150 - 12 * crop), pygame.SRCALPHA)
        portrait = DialoguePortrait(character_id=1, asset_id=1, mode=2, theme=2)
        layer, (x, y) = renderer.portrait_group(portrait)
        # The native 12-row crop leaves the art 138 tall, aligned to the
        # inner ring's bottom (52): its top sits at 52-138=-86 -- exactly
        # where uncropped art (150 tall) aligned to the outer ring's own
        # half-height (64) would put it. The outer ring's own top is -64,
        # so bounds top is the art's.
        self.assertEqual(y, -86)

    def test_episode_portraits_at_2x_are_treated_as_half_size_android_art(self):
        # Downloadable HD episodes ship 226x256 / 256x256 portraits inside
        # the EXP with no Android copy to compare against; they must come
        # back at half size (113x128 / 128x128), not at the fixed mask size.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Raster

        for size, expected in (((226, 256), (113, 128)), ((256, 256), (128, 128)),
                               ((199, 256), (100, 128)), ((113, 128), (113, 128)),  # 1x art keeps its size
                               ((300, 400), (128, 150))):
            self.assertEqual(DialogueRenderer._episode_portrait_size(Raster(*size, b'')), expected, size)
        # The mask a 2x cutout is clipped with is exactly twice the mask.
        mask = Raster(128, 150, bytes(128 * 150), mode='A')
        self.assertEqual(DialogueRenderer._scaled_mask(mask, 226, 256).width, 256)
        self.assertEqual(DialogueRenderer._scaled_mask(mask, 226, 256).height, 300)

    def test_portrait_rings_and_art_are_separate_layers_sharing_one_bounds(self):
        # HD draws the rings beneath the body text (a third line's top edge
        # crosses the ring's bottom arc) and the art above the relationship
        # icon, so the group is exposed as two same-sized layers.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.dialogue_animation import DialoguePortrait
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))

        def solid(size, color):
            surface = pygame.Surface(size, pygame.SRCALPHA)
            surface.fill(color)
            return surface

        renderer = DialogueRenderer(None, None, None)
        renderer.frame_native = lambda asset_id, index: solid((128, 128) if index == 37 else (105, 105),
                                                              (255, 255, 255, 255))
        renderer.frame_scaled = lambda asset_id, index, scale: renderer.frame_native(asset_id, index)
        renderer.portrait = lambda asset_id, flipped, density=1, crop=False: solid((100, 116), (200, 0, 0, 255))
        portrait = DialoguePortrait(character_id=1, asset_id=1, mode=1, theme=1)
        rings, art, topleft = renderer.portrait_layers(portrait)
        self.assertEqual(rings.get_size(), art.get_size())
        # Rings hold no art pixels and the art layer no ring pixels.
        self.assertEqual(rings.get_at((rings.get_width() // 2, rings.get_height() // 2))[:3], (255, 255, 255))
        self.assertEqual(art.get_at((art.get_width() // 2, art.get_height() // 2))[:3], (200, 0, 0))
        self.assertEqual(art.get_at((1, 1)).a, 0)
        combined, combined_topleft = renderer.portrait_group(portrait)
        self.assertEqual(combined_topleft, topleft)
        self.assertEqual(combined.get_at((combined.get_width() // 2, combined.get_height() // 2))[:3], (200, 0, 0))

    def test_bottom_bar_layer_spans_the_full_view_in_hd_and_the_ui_column_otherwise(self):
        # HD anchors the bar and gear to the edges of its 3:4 view (20 units
        # wider each side than the UI column); Android's bar sits in the column.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))

        def solid(size, color):
            surface = pygame.Surface(size, pygame.SRCALPHA)
            surface.fill(color)
            return surface

        text = SimpleNamespace(layout=lambda *a, **k: SimpleNamespace(width=10),
                               draw_layout=lambda *a, **k: None)
        renderer = DialogueRenderer(SimpleNamespace(hd_asset=lambda _id: None), text, None, scale=2)
        renderer.frame_scaled = lambda asset, index, scale: solid(
            (round(320 * scale), round(49 * scale)) if index == 47 else (round(74 * scale), round(72 * scale)),
            (0, 200, 0, 255) if index == 47 else (200, 0, 0, 255))
        layer = renderer.bottom_bar_layer('hint')
        self.assertEqual(layer.get_size(), (768, 144))
        self.assertEqual(layer.get_at((10, 100)).a, 0)            # left of the column (32 units): nothing
        self.assertEqual(layer.get_at((300, 130))[:3], (0, 200, 0))  # the bar, in the column (32 units in)
        self.assertEqual(layer.get_at((100, 100))[:3], (200, 0, 0))   # the gear, 32 units in
        renderer = DialogueRenderer(SimpleNamespace(hd_asset=lambda _id: b'hd'), text, None, scale=2)
        renderer.hd_chrome = lambda: True
        packs = []

        def hd_frame(index, scale, pack=155):
            packs.append(pack)
            return solid({55: (64, 49), 56: (64, 24)}[index] if index in (55, 56) else (74, 72),
                         {55: (0, 0, 200, 255), 56: (0, 200, 200, 255)}.get(index, (200, 0, 0, 255)))
        renderer._hd_frame = hd_frame
        renderer._hd_gear = lambda k, pressed=False: solid((68, 66), (200, 0, 0, 255))
        layer = renderer.bottom_bar_layer('hint')
        # The gear's box is at (-3.5, 441) in the frame, one unit under the layer's top and running off its left edge.
        self.assertEqual(layer.get_at((2, 40))[:3], (200, 0, 0))
        self.assertEqual(layer.get_at((2, 1)).a, 0)
        self.assertEqual(layer.get_at((100, 130))[:3], (0, 200, 200))  # the strip runs on across the view
        self.assertEqual(layer.get_at((layer.get_width() - 2, 130))[:3], (0, 200, 200))
        self.assertEqual(set(packs), {155})
        # Cause of Death with the SHS HD art source takes the same edge-to-edge layout from its derived stand-ins.
        renderer = DialogueRenderer(SimpleNamespace(hd_asset=lambda _id: None), text, None, scale=2)
        renderer.cod_hd_common = lambda: object()
        renderer._hd_frame, renderer._hd_gear = hd_frame, lambda k, pressed=False: solid((68, 66), (200, 0, 0, 255))
        packs.clear()
        layer = renderer.bottom_bar_layer('hint')
        self.assertEqual(layer.get_at((layer.get_width() - 2, 130))[:3], (0, 200, 200))
        self.assertEqual(set(packs), {'cod-hd'})

    def test_ios_hint_font_takes_arial_rounded_advances(self):
        # Both iOS builds lay ArialMT out at Arial Rounded MT Bold's advances (initFonts builds the ArialMT advance
        # table from the Rounded face); Android's bitmap hint keeps its own.
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.fonts import BitmapFont, Glyph
        import pygame
        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        fonts = {'ArialMT11': BitmapFont('Arial', 11, 13, 'a.png', {84: Glyph(84, 0, 0, 5, 7, 0, 2, 6)}, {}),
                 'ArialRoundedMTBold11': BitmapFont('Rounded', 11, 13, 'r.png', {84: Glyph(84, 9, 0, 6, 7, 0, 2, 7.5)}, {})}
        text = SimpleNamespace(fonts={name: (font, 'atlas') for name, font in fonts.items()},
                               font=lambda name: fonts[name])
        for game, hd, expected in (('cod', False, 7.5), ('shs', True, 7.5), ('shs', False, 6)):
            with self.subTest(game=game, hd=hd):
                renderer = DialogueRenderer(SimpleNamespace(library=SimpleNamespace(game_id=game),
                                                            hd_asset=lambda _id, hd=hd: b'hd' if hd else None),
                                            text, None, scale=2)
                font, atlas = text.fonts.get(renderer.footer_font(), (fonts['ArialMT11'], 'atlas'))
                self.assertEqual(font.glyphs[84].advance, expected)
                self.assertEqual((font.glyphs[84].x, atlas), (0, 'atlas'))     # the Arial glyph image is kept

    def test_hd_housing_is_a_frame_46_ring_and_a_vector_disc_clipped_against_the_bubble(self):
        # SHSPortraitLayer.drawInContext: frame 46 (a 256px ring), then a
        # CGContextFillEllipseInRect disc 105 units across in the theme's exact
        # color; the ring is clipped against the bubble, the disc is not.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Rect
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))

        renderer = DialogueRenderer(SimpleNamespace(), None, None, scale=2)
        renderer.hd_chrome = lambda: True
        renderer._hd_frame = lambda index, scale: pygame.Surface((round(128 * scale), round(128 * scale)), pygame.SRCALPHA)
        # Disc: 105 units -> 210 px, filled with the theme colors read from the binary.
        for theme, color in ((1, (188, 214, 226)), (2, (246, 174, 168)), (3, (142, 155, 156)), (0, (142, 155, 156))):
            disc = renderer.disc_frame(theme, 2)
            self.assertEqual(disc.get_size(), (210, 210))
            self.assertEqual(tuple(disc.get_at((105, 105)))[:3], color)
            self.assertEqual(disc.get_at((0, 0)).a, 0)               # a circle, not a square
        # The clip polygon is the bubble layer's frame (the box grown by its 10-unit border) inset 3 units, the top
        # corners cut 5 units (10 points).
        box = Rect(30, 296, 260, 72)
        polygon = DialogueRenderer.bubble_polygon(box)
        self.assertEqual(polygon[0], (23, 375))
        self.assertIn((28, 289), polygon)
        self.assertIn((292, 289), polygon)
        self.assertIn((23, 294), polygon)
        # The story canvas spans the whole 384-unit frame; its column is a view of it.
        self.assertEqual(renderer.wide.get_size(), ((320 + 64) * 2, 960))
        self.assertEqual(renderer.canvas.get_size(), (640, 960))
        renderer.canvas.fill((9, 9, 9, 255))
        self.assertEqual(renderer.wide.get_at((64, 0))[:3], (9, 9, 9))
        self.assertEqual(renderer.wide.get_at((63, 0)).a, 0)

    def test_footer_hints_come_from_the_string_bank_with_an_english_fallback(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.menu import MenuStrings
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        renderer = DialogueRenderer(None, None, None)
        self.assertEqual(renderer.footer_hint(36, 'Touch the screen to continue'), 'Touch the screen to continue')
        renderer.menu_strings = lambda: MenuStrings(('a',) * 36 + ('Localized',))
        self.assertEqual(renderer.footer_hint(36, 'x'), 'Localized')
        self.assertEqual(renderer.footer_hint(300, 'fallback'), 'fallback')

    def test_continue_button_only_appears_once_text_is_revealed_and_hd_is_available(self):
        # Real HD device confirmed: once dialogue text finishes revealing,
        # HD shows a "Continue" pill (resource 155, see content.HD_ASSET_MAP)
        # instead of this build's own implicit tap-anywhere affordance --
        # but that resource is genuinely HD-only, so it must stay silent
        # (not raise, not fall back to Android art) on Android-only content.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Rect
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))

        page = SimpleNamespace(box=Rect(20, 300, 260, 72))
        # Without HD the supplied skin's own tab (draw_continue_tab) expands with continue_scale instead.
        incomplete = SimpleNamespace(engine=SimpleNamespace(
            dialogue_animation=SimpleNamespace(complete=False, continue_scale=0.0)))
        complete = SimpleNamespace(engine=SimpleNamespace(
            dialogue_animation=SimpleNamespace(complete=True, continue_scale=0.0)))

        renderer = DialogueRenderer(SimpleNamespace(hd_asset=lambda _id: None), None, None)
        before = pygame.image.tobytes(renderer.canvas, 'RGBA')
        renderer.draw_continue(incomplete, page, 0)
        self.assertEqual(pygame.image.tobytes(renderer.canvas, 'RGBA'), before)
        renderer.draw_continue(complete, page, 0)  # HD unavailable -- still silent
        self.assertEqual(pygame.image.tobytes(renderer.canvas, 'RGBA'), before)

        def opaque_frame(asset_id, index):
            surface = pygame.Surface((20, 20), pygame.SRCALPHA)
            surface.fill((200, 60, 60, 255))
            return surface

        renderer = DialogueRenderer(SimpleNamespace(hd_asset=lambda _id: b'present'), None, None)
        renderer.frame_native = opaque_frame
        renderer.text = SimpleNamespace(
            layout=lambda *a, **k: SimpleNamespace(ink_bounds=(0, 0, 0, 0)),
            draw_layout=lambda *a, **k: None)
        before = pygame.image.tobytes(renderer.canvas, 'RGBA')
        # The pill expands over 250 ms from when the text settles
        # (GameModel::expandContinue: y scale ~0 -> 1): nothing at first,
        # partial height halfway, the full pill after.
        clock = [1000]
        with patch('pygame.time.get_ticks', lambda: clock[0]):
            renderer.draw_continue(complete, page, 0)
            self.assertEqual(pygame.image.tobytes(renderer.canvas, 'RGBA'), before)
            clock[0] = 1125
            renderer.draw_continue(complete, page, 0)
            half = renderer.canvas.get_bounding_rect()
            renderer.canvas.fill((0, 0, 0, 0))
            clock[0] = 1300
            renderer.draw_continue(complete, page, 0)
            full = renderer.canvas.get_bounding_rect()
        self.assertGreater(half.height, 0)
        self.assertLess(half.height, full.height)
        self.assertNotEqual(pygame.image.tobytes(renderer.canvas, 'RGBA'), before)

    def test_the_continue_pill_never_spills_left_of_a_narrator_box_narrower_than_it(self):
        # A one-word narrator line (dialogue.py's DialoguePage.page(), which sizes a narrator box tightly around
        # its own text) can be narrower than the pill itself; it must still anchor to the box's own left edge
        # rather than overlap past it (found live: "Except...", "SMASH!" in 7_5_WeddingSmashers.exp).
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Rect
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))

        # -6 is dialogue.py's own fixed x for every narrator box (DialoguePage.page()'s HD-font branch), not
        # something a short line pushes it to; a short line only shrinks the width.
        box = Rect(-6, 300, 40, 30)
        page = SimpleNamespace(box=box)
        complete = SimpleNamespace(engine=SimpleNamespace(dialogue_animation=SimpleNamespace(complete=True)))
        pill_size = (160, 40)                                         # 80 x 20 logical units: wider than the box

        def opaque_frame(asset_id, index):
            surface = pygame.Surface(pill_size, pygame.SRCALPHA)
            surface.fill((200, 60, 60, 255))
            return surface

        renderer = DialogueRenderer(SimpleNamespace(hd_asset=lambda _id: b'present'), None, None)
        renderer.frame_native = opaque_frame
        renderer.text = SimpleNamespace(
            layout=lambda *a, **k: SimpleNamespace(ink_bounds=(0, 0, 0, 0)),
            draw_layout=lambda *a, **k: None)
        clock = [1000]
        with patch('pygame.time.get_ticks', lambda: clock[0]):
            renderer.draw_continue(complete, page, 0)                # starts the 250 ms expansion clock
            clock[0] = 1300
            renderer.draw_continue(complete, page, 0)                # now past it: the pill is fully shown
        # The pill must never be cut off against `canvas`'s own subsurface edge either -- it must be drawn on
        # `wide`, which (like the box's own background) has real margin to spill into on a negative box.x, not
        # clamped-looking-fine-but-actually-truncated there. Checking `canvas` alone would not have caught this:
        # a subsurface still reports *a* bounding rect for whatever of the pill happens to overlap it.
        self.assertEqual(renderer.wide.get_bounding_rect().width, pill_size[0] // 2)

    def test_choice_timer_wheel_fills_proportionally_to_elapsed_time(self):
        # Real HD device confirmed: a timed choice shows a filling wheel,
        # not this build's own "Xs" footer text. The exact native per-frame
        # composite (resource 155, frames 12-27) isn't reproduced here (see
        # ChoiceRenderer.draw_timer_wheel's own docstring); this exercises
        # the fallback radial-sweep rendering that stands in for it.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_choice import ChoiceRenderer
        from exp_runtime.ui_assets import Rect
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))

        renderer = ChoiceRenderer(None, None, None)
        page = SimpleNamespace(box=Rect(20, 20, 260, 300), theme=0)
        renderer.draw_timer_wheel(page, 10000, 10000)  # just started: no fill
        empty = pygame.image.tobytes(renderer.canvas, 'RGBA')
        renderer.canvas.fill((0, 0, 0, 0))
        renderer.draw_timer_wheel(page, 0, 10000)  # expired: fully filled
        full = pygame.image.tobytes(renderer.canvas, 'RGBA')
        self.assertNotEqual(empty, full)

    def test_choice_canvas_and_wheel_scale_with_density(self):
        # The choice panel draws at STORY_SCALE pixels per logical unit like
        # the dialogue panel, so HD art keeps its own density; its geometry
        # (here the timer wheel's center) must land on the same logical spot.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_choice import ChoiceRenderer
        from exp_runtime.ui_assets import Rect
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))

        page = SimpleNamespace(box=Rect(20, 20, 260, 300), theme=0)
        centers = []
        for scale in (1, 2):
            renderer = ChoiceRenderer(None, None, None, scale=scale)
            self.assertEqual(renderer.canvas.get_size(), (320 * scale, 480 * scale))
            renderer.draw_timer_wheel(page, 5000, 10000)
            bounds = renderer.canvas.get_bounding_rect()
            centers.append(((bounds.centerx) / scale, (bounds.centery) / scale))
        self.assertAlmostEqual(centers[0][0], centers[1][0], delta=1)
        self.assertAlmostEqual(centers[0][1], centers[1][1], delta=1)

    def test_word_grid_portrait_scale_matches_the_hd_to_android_size_ratio(self):
        # Real device confirmed: word-grid portraits rendered comically
        # oversized, overlapping most of the screen -- unlike dialogue's own
        # portrait() (see test_oversized_hd_portrait_scales_the_mask_instead_
        # of_raising above), GridRenderer drew a raw, unmasked portrait with
        # no HD-vs-Android scale compensation at all. GridRenderer._hd_scale
        # mirrors DialogueRenderer's own established technique (compare
        # actual size against the Android-sourced original) without
        # reusing portrait() outright, since word-grid draws its own
        # frame/ring decoration around an unmasked cutout.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from io import BytesIO
        from exp_runtime.shs.desktop_grid import GridRenderer
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))

        def png_bytes(size):
            surface = pygame.Surface(size, pygame.SRCALPHA)
            buffer = BytesIO()
            pygame.image.save(surface, buffer, 'png')
            return buffer.getvalue()

        resources = SimpleNamespace(
            android_asset=lambda asset_id: png_bytes((128, 150)),
            read_asset=lambda asset_id: png_bytes((256, 300)))
        renderer = GridRenderer(resources, None, None)
        self.assertEqual(renderer._hd_scale(1), 2.0)

    def test_portrait_housing_rect_carries_the_hd_vertical_correction(self):
        # Real device confirmed: the Android layout bank's own portrait
        # housing rect floats the portrait ring well above where real HD
        # positions it relative to the dialogue box (measured against two
        # real-device photos of named dialogue, reference/IMG_0069.PNG and
        # IMG_0070.PNG -- see DialogueRenderer._portrait_rect). Both of the
        # bank's two housing-rect variants (mode 1 and mode 2) share this
        # correction through a single helper so draw_portrait,
        # draw_relationship and draw_notice all move together.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Rect
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        seen = []
        def rectangle(layout_id, node_id):
            seen.append((layout_id, node_id))
            base = Rect(-7, 225, 128, 128) if node_id == 0x30 else Rect(199, 225, 128, 128)
            return base
        resources = SimpleNamespace(
            dialogue_layout=lambda: SimpleNamespace(bank=SimpleNamespace(rectangle=rectangle)))
        renderer = DialogueRenderer(resources, None, None)
        offset = DialogueRenderer._HD_PORTRAIT_VERTICAL_OFFSET
        self.assertEqual(renderer._portrait_rect(1), Rect(-7, 225 + offset, 128, 128))
        self.assertEqual(renderer._portrait_rect(2), Rect(199, 225 + offset, 128, 128))
        self.assertEqual(seen, [(17, 0x30), (17, 0x4e)])

    def test_relationship_slots_use_the_housings_own_side_not_always_the_right(self):
        # The layout bank carries two separately authored slot-node sets, not one mirrored at runtime: nodes
        # 54-57 ring the left (mode 1) housing, 0x54-0x57 the right (mode 2) one -- read directly off Battle of
        # the Schools: Girl's layout bank. Using the mode-2 set unconditionally (the bug) put Kelly's own
        # relationship badge (mode 1, her first line) far to the wrong side, clipping off the screen's left edge.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.ui_assets import Rect
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((1, 1))
        rects = {
            0x30: Rect(-7, 225, 128, 128), 0x4e: Rect(199, 225, 128, 128),
            54: Rect(106, 273, 22, 22), 55: Rect(99, 254, 22, 22), 56: Rect(90, 236, 22, 22), 57: Rect(74, 223, 22, 22),
            0x54: Rect(192, 273, 22, 22), 0x55: Rect(197, 254, 22, 22), 0x56: Rect(208, 236, 22, 22), 0x57: Rect(224, 223, 22, 22)}
        resources = SimpleNamespace(
            dialogue_layout=lambda: SimpleNamespace(bank=SimpleNamespace(rectangle=lambda layout_id, node: rects[node])))
        renderer = DialogueRenderer(resources, None, None)
        self.assertEqual(renderer.relationship_slots(2), [(-60, -5), (-55, -24), (-44, -42), (-28, -55)])
        self.assertEqual(renderer.relationship_slots(1), [(60, -5), (53, -24), (44, -42), (28, -55)])

    def test_tab_toggles_panels_open_and_progress_animates_both_ways(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            ui = Desktop(Session(resources), audio=False)
            self.assertEqual((ui.panels_open, ui.panels_progress), (False, 0.0))
            width, height = ui.window.get_size()
            self.assertAlmostEqual(width / height, 3 / 4, places=2)
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
            self.assertTrue(ui.panels_open)
            # Real device confirmed: the window widens to its new 4:3 shape
            # as soon as the panels start opening, not only once the slide
            # animation finishes (see desktop_panels.py's module docstring).
            ui.tick(16)
            width, height = ui.window.get_size()
            self.assertAlmostEqual(width / height, 4 / 3, places=2)
            ui.tick(1000)
            self.assertEqual(ui.panels_progress, 1.0)
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
            self.assertFalse(ui.panels_open)
            # Closing keeps the window's size (owner's choice), during and after the slide-out.
            ui.tick(16)
            self.assertEqual(ui.window.get_size(), (width, height))
            ui.tick(1000)
            self.assertEqual(ui.panels_progress, 0.0)
            self.assertEqual(ui.window.get_size(), (width, height))
            # A window already 4:3 or wider has room for both panels at full height: opening leaves it alone.
            ui.window = pygame.display.set_mode((1200, 600), pygame.RESIZABLE)
            ui.toggle_panels()
            ui.tick(16)
            self.assertEqual(ui.window.get_size(), (1200, 600))
            ui.toggle_panels()
            ui.tick(1000)
            # A narrower one is widened to 4:3 at its own height.
            ui.window = pygame.display.set_mode((600, 600), pygame.RESIZABLE)
            ui.toggle_panels()
            ui.tick(16)
            self.assertEqual(ui.window.get_size(), (800, 600))
            ui.toggle_panels()
            ui.tick(1000)
            # The Options screen's Side Panels switch toggles them too.
            ui.command(('pause_toggle', 'side_panels'))
            self.assertTrue(ui.panels_open)
            ui.command(('pause_toggle', 'side_panels'))
            self.assertFalse(ui.panels_open)
            # Tab is swallowed by the pause menu instead of toggling panels.
            ui.command(('menu',))
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
            self.assertFalse(ui.panels_open)

    def test_arrow_keys_highlight_the_pause_menus_rows_and_enter_taps_them(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            ui = Desktop(Session(resources), audio=False)
            key = lambda code: ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code))
            rect = pygame.Rect(0, 0, 1, 1)
            with patch.object(ui.pause_hd, 'available', return_value=False):
                ui.command(('menu',))
                ui.buttons = [(rect, ('resume',)), (rect, ('main_menu',))]
                key(pygame.K_DOWN)
                key(pygame.K_DOWN)
                key(pygame.K_DOWN)
                self.assertEqual(ui.menu_focus, ('main_menu',))
                self.assertIsNone(ui.choice_focus)                  # the choice under the menu keeps its own
                key(pygame.K_UP)
                key(pygame.K_RETURN)
                ui.tick(400)                                        # Resume's zoom out
                self.assertFalse(ui.menu_open)
                ui.command(('menu',))
                self.assertIsNone(ui.menu_focus)                    # each opening starts without a highlight
            with patch.object(ui.pause_hd, 'available', return_value=True):
                # HD's: Left / Right move a highlighted slider.
                ui.pause_hd.buttons = [(rect, ('pause_slider', 'music', rect)), (rect, ('pause_back',))]
                ui.music_volume = .5
                key(pygame.K_DOWN)
                key(pygame.K_RIGHT)
                self.assertAlmostEqual(ui.music_volume, .6)
                key(pygame.K_DOWN)
                ui.pause_hd.state.screen = 'options'
                key(pygame.K_SPACE)
                self.assertEqual((ui.pause_hd.state.screen, ui.menu_open), ('pause', True))

    def test_opening_the_menu_dismisses_a_showing_faceplace_toast(self):
        # Real device confirmed (see dtview_faceplace.FaceplaceToast): a
        # Faceplace toast has no timer of its own -- pausing with the
        # settings menu is one of its three explicit dismissal triggers.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        from exp_runtime.dtview_faceplace import FaceplaceMessage, FaceplaceToast
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            ui = Desktop(Session(resources), audio=False)
            ui.session.engine.faceplace_toast = FaceplaceToast(FaceplaceMessage('message', text='hi'))
            ui.command(('menu',))
            self.assertIsNone(ui.session.engine.faceplace_toast)

    def test_opening_the_panels_dismisses_a_showing_faceplace_toast(self):
        # Real device confirmed: opening the side panels also dismisses a
        # showing toast -- that data is visible in the panel already.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        from exp_runtime.dtview_faceplace import FaceplaceMessage, FaceplaceToast
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            ui = Desktop(Session(resources), audio=False)
            ui.session.engine.faceplace_toast = FaceplaceToast(FaceplaceMessage('message', text='hi'))
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
            self.assertTrue(ui.panels_open)
            self.assertIsNone(ui.session.engine.faceplace_toast)

    def test_panel_margins_start_at_the_wider_background_edge_not_the_narrower_viewport(self):
        # Real device correction: the background layer is deliberately drawn
        # *wider* than self.viewport (bg_viewport, showing more of HD's true
        # 3:4 view beyond the narrower Android-authored UI canvas -- see
        # _draw_background_layer's own docstring). Panel margins used to
        # start at self.viewport's own edge, which is *inside* where that
        # wider background already extends to -- so the panel covered the
        # outermost strip of the background instead of sitting fully beside
        # it, confirmed live ("they cover up part of the background on each
        # side"). Margins must start at bg_viewport's edge instead.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            ui = Desktop(Session(resources), audio=False)
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
            ui.tick(1000)
            ui.render()
            self.assertLess(ui.bg_viewport.x, ui.viewport.x)
            self.assertGreater(ui.bg_viewport.right, ui.viewport.right)
            expected_left_margin = ui.bg_viewport.x
            expected_right_margin = ui.window.get_width() - ui.bg_viewport.right
            self.assertGreater(expected_left_margin, 0)
            self.assertGreater(expected_right_margin, 0)

    def test_a_background_window_past_the_arts_edge_keeps_its_scale_and_leaves_the_rest_uncovered(self):
        # Owner report: Cause of Death's apartment looked wider than the photo. A focal point near the art's edge puts
        # part of the 3:4 frame's window outside the 480x720 art; the clipped crop used to be stretched over the whole
        # frame (its clock 26% wider), instead of drawn at its own scale.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            ui = Desktop(Session(resources), audio=False)
            ui.render()
            art = pygame.Surface((480, 720))
            art.fill((200, 40, 40))
            ui.window.fill((0, 0, 0))
            ui.pending_background, ui.pending_background_origin = art, (240, 180)    # the art's left edge at x 0
            ui._background_layer_cache = None
            ui._draw_background_layer(ui.bg_viewport.size, ui.bg_viewport)
            (_, crop, size), scaled = ui._background_layer_cache
            self.assertLess(crop[2], 384)                                               # the window was clipped
            self.assertAlmostEqual(size[0] / crop[2], size[1] / crop[3], delta=.02)     # ... and not stretched
            self.assertEqual(ui.window.get_at((ui.bg_viewport.x + 1, ui.bg_viewport.centery))[:3], (0, 0, 0))
            self.assertEqual(ui.window.get_at((ui.bg_viewport.right - 2, ui.bg_viewport.centery))[:3], (200, 40, 40))

    def test_a_covering_background_fills_the_frame_at_an_even_scale(self):
        # Cause of Death's chapter card: its 480x720 picture is scaled evenly until it covers the 3:4 frame (owner:
        # no dead space, and no stretch).
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            ui = Desktop(Session(resources), audio=False)
            ui.render()
            art = pygame.Surface((480, 720))
            art.fill((40, 200, 40))
            ui.window.fill((0, 0, 0))
            ui.pending_background, ui.pending_background_origin = art, 'cover'
            ui._background_layer_cache = None
            ui._draw_background_layer(ui.bg_viewport.size, ui.bg_viewport)
            (_, crop, size), _ = ui._background_layer_cache
            self.assertEqual(crop[2], 480)                                              # the whole width
            self.assertAlmostEqual(size[0] / crop[2], size[1] / crop[3], delta=.02)     # even scale
            for corner in ((ui.bg_viewport.x, ui.bg_viewport.y),
                           (ui.bg_viewport.right - 1, ui.bg_viewport.bottom - 1)):
                self.assertEqual(ui.window.get_at(corner)[:3], (40, 200, 40))

    def test_a_translated_episode_shows_its_own_backdrop_where_the_art_leaves_the_frame_black(self):
        # Translated New Rules episodes (pack 31300) carry New Rules' UI backdrop (shs/profile.py
        # TRANSLATED_FRAME_BACKDROP); their 3:1 strips leave bands above and below. Other episodes keep black.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        from exp_runtime.shs.profile import TRANSLATED_FRAME_BACKDROP
        import pygame

        self.addCleanup(pygame.quit)
        (pack_id, asset_id), = TRANSLATED_FRAME_BACKDROP.items()
        with tempfile.TemporaryDirectory() as temporary:
            for translated in (True, False):
                resources = Resources(branching_program())
                resources.library.directory = Path(temporary)
                ui = Desktop(Session(resources), audio=False)
                ui.render()
                backdrop = pygame.Surface((384, 512))
                backdrop.fill((30, 60, 150))
                path = Path(temporary) / 'backdrop.png'
                pygame.image.save(backdrop, str(path))
                resources.record = dict(resources.record, pack_id=pack_id if translated else 1)
                resources.exists = lambda rid: rid == asset_id
                resources.read_asset = lambda rid, data=path.read_bytes(): data
                strip = pygame.Surface((480, 160))
                strip.fill((200, 40, 40))
                ui.window.fill((0, 0, 0))
                ui.pending_background, ui.pending_background_origin = strip, (240, 180)
                ui._background_layer_cache = None
                ui._draw_background_layer(ui.bg_viewport.size, ui.bg_viewport)
                band = (30, 60, 150) if translated else (0, 0, 0)
                for y in (ui.bg_viewport.y + 1, ui.bg_viewport.bottom - 2):
                    self.assertEqual(ui.window.get_at((ui.bg_viewport.centerx, y))[:3], band)
                self.assertEqual(ui.window.get_at(ui.bg_viewport.center)[:3], (200, 40, 40))

    def _location_ui(self, temporary):
        """A Desktop drawing Cause of Death's location layer on its own clock: (ui, clock, draw(art, origin))."""
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        resources = Resources(branching_program())
        resources.library.directory = Path(temporary)
        ui = Desktop(Session(resources), audio=False)
        ui.render()
        ui.dialogue_renderer.game_id = lambda: 'cod'
        clock = [0]
        ticks = patch('pygame.time.get_ticks', lambda: clock[0])
        ticks.start()
        self.addCleanup(ticks.stop)
        ui.location_shown = ui.location_changing = None

        def draw(art, origin):
            ui.pending_background, ui.pending_background_origin, ui.pending_background_alpha = art, origin, 255
            ui._draw_background_layer(ui.bg_viewport.size, ui.bg_viewport)
            return tuple(ui.window.get_at(ui.bg_viewport.center))[:3]
        return ui, clock, draw

    def test_a_new_location_picture_crossfades_in_over_a_quarter_second(self):
        # zazatree's TouchHLE recordings: scene pictures crossfade (Core Animation's implicit contents action on the
        # location layer, ~0.25 s, the default ease); ours used to cut in one frame.
        import pygame
        from exp_runtime.location_pan import default_ease
        with tempfile.TemporaryDirectory() as temporary:
            ui, clock, draw = self._location_ui(temporary)
            cabin, dark = pygame.Surface((480, 720)), pygame.Surface((480, 720))
            cabin.fill((200, 200, 200))
            dark.fill((0, 0, 0))
            self.assertEqual(draw(cabin, (160, 180)), (200, 200, 200))
            clock[0] = 1000
            self.assertEqual(draw(dark, (160, 180)), (200, 200, 200))            # starts from the old picture
            clock[0] = 1125
            self.assertAlmostEqual(draw(dark, (160, 180))[0], 200 * (1 - default_ease(.5)), delta=3)
            clock[0] = 1250
            self.assertEqual(draw(dark, (160, 180)), (0, 0, 0))
            clock[0] = 2000
            self.assertEqual(draw(dark, (160, 180)), (0, 0, 0))                  # the same picture: no change

    def test_the_chapter_card_sets_its_picture_without_a_crossfade_and_its_exit_glides(self):
        # SHSUIChapterScreen::animate turns the implicit actions off around its picture; its internalTransitionOff
        # resets the layer's scale and position with them on, so the card's framing glides into the scene's.
        import pygame
        with tempfile.TemporaryDirectory() as temporary:
            ui, clock, draw = self._location_ui(temporary)
            cabin, docks, bar = (pygame.Surface((480, 720)) for _ in range(3))
            cabin.fill((200, 0, 0))
            docks.fill((0, 200, 0))
            bar.fill((0, 0, 200))
            draw(cabin, (160, 180))
            with patch.object(ui.session, 'pending', SimpleNamespace(name='presentation', details={})):
                clock[0] = 1000
                self.assertEqual(draw(docks, 'cover'), (0, 200, 0))             # no crossfade into the card
                card = ui.location_shown[1]
            clock[0] = 5000
            draw(bar, (160, 180))
            scene = ui.location_shown[1]
            self.assertNotEqual(card, scene)
            clock[0] = 5125
            middle = draw(bar, (160, 180))
            self.assertTrue(0 < middle[1] < 200 and 0 < middle[2] < 200)        # both pictures, mid-crossfade
            self.assertEqual(ui._background_placement(bar, ui.bg_viewport.size), scene)
            clock[0] = 5250
            self.assertEqual(draw(bar, (160, 180)), (0, 0, 200))
            self.assertIsNone(ui.location_changing)

    def test_episode_complete_freezes_on_the_last_real_background_not_a_blank_one(self):
        # engine.py's own scene teardown resets panel.background_id to -1 once the episode exits (confirmed in
        # test_episode_exit.py's test_scene_teardown_...); found live: without a fallback, the "Episode complete"
        # screen behind the end-of-episode card -- and, through Desktop.snapshot(), the card's own sepia
        # backdrop -- showed no picture at all there instead of freezing on the last real scene the way pausing
        # mid-scene already does (panel.background_id is still valid then).
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from io import BytesIO
        from exp_runtime.desktop import Desktop
        from exp_runtime.engine import EngineAction, PanelState
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            surface = pygame.Surface((64, 64), pygame.SRCALPHA)
            surface.fill((80, 140, 200, 255))
            stream = BytesIO()
            pygame.image.save(surface, stream, 'x.png')
            picture = stream.getvalue()

            def read_asset(resource_id):
                if resource_id == 42:
                    return picture
                raise OSError(f'no such test asset {resource_id}')

            resources.read_asset = read_asset
            ui = Desktop(Session(resources), audio=False)
            ui.session.engine.panel.background_id = 42
            ui.render()
            self.assertEqual(ui.last_background_id, 42)
            self.assertIsNotNone(ui.pending_background)          # sanity: the normal, still-valid-scene path works
            # Simulate the episode having just exited (engine.py's own teardown, reproduced directly rather than
            # scripting a real exit): the panel resets and pending becomes a plain episode_exit action.
            ui.session.engine.panel = PanelState()
            ui.session.pending = EngineAction('episode_exit', ui.session.pending.request, False)
            self.assertEqual(ui.session.engine.panel.background_id, -1)
            ui.render()
            self.assertIsNotNone(ui.pending_background)
            self.assertEqual(ui.pending_background.get_size(), (64, 64))

    def test_chrome_image_normalizes_an_oversized_hd_icon_back_to_android_size(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from io import BytesIO
        from exp_runtime.desktop_dialogue import DialogueRenderer
        import pygame

        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.display.set_mode((256, 300))
        # Relationship icons (3010-3012) were confirmed to silently double
        # in size (22x24 -> 44x48) through the generalized HD-asset
        # fallback -- nothing downstream was scaling them back down. See
        # legacy/findings.md, "Chrome icons render oversized with an HD ipa".
        oversized = pygame.Surface((44, 48), pygame.SRCALPHA)
        oversized.fill((10, 20, 30, 255))
        android_reference = pygame.Surface((22, 24), pygame.SRCALPHA)
        buffer = BytesIO()
        pygame.image.save(android_reference, buffer, 'PNG')
        resources = SimpleNamespace(android_asset=lambda asset_id: buffer.getvalue())
        renderer = DialogueRenderer(resources, None, lambda _: oversized)
        image = renderer.chrome_image(3010)
        self.assertEqual(image.get_size(), (22, 24))
        # A same-size asset (no HD ipa, or a chrome id HD never touches)
        # must not be resampled at all.
        same_size = pygame.Surface((22, 24), pygame.SRCALPHA)
        renderer2 = DialogueRenderer(resources, None, lambda _: same_size)
        self.assertIs(renderer2.chrome_image(3010), same_size)
        self.assertIsNone(renderer.chrome_image(-1))

    def test_hd_gear_touch_area_covers_the_icon_including_the_side_margin(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            ui = Desktop(Session(resources), audio=False)
            ui.window = pygame.display.set_mode((768, 1024), pygame.RESIZABLE)
            ui.render()
            ui.dialogue_renderer.hd_chrome = lambda: True
            ui.buttons.append((pygame.Rect(0, 0, 1, 1), ('menu',)))    # the screen offers the gear
            frame, unit = ui.bg_viewport, ui.bg_viewport.width / 384
            # The gear's left third lies in the 32-unit margin outside the UI column; its top is above the
            # old touch rectangle. The frame's corner outside the icon's box does nothing.
            for x, y in ((0, 445), (33, 447), (33, 505), (66, 477)):
                ui.menu_open = False
                ui.buttons = [(pygame.Rect(0, 0, 1, 1), ('menu',))]
                for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):     # held, then released to open
                    ui.handle_event(pygame.event.Event(kind, button=1, pos=(frame.x + x * unit, frame.y + y * unit)))
                self.assertTrue(ui.menu_open, (x, y))
            ui.menu_open = False
            for x, y in ((75, 477), (33, 435)):
                ui.buttons = [(pygame.Rect(0, 0, 1, 1), ('menu',))]
                for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                    ui.handle_event(pygame.event.Event(kind, button=1, pos=(frame.x + x * unit, frame.y + y * unit)))
                self.assertFalse(ui.menu_open, (x, y))

    def test_a_queued_transition_runs_blinds_around_the_answer(self):
        # SHS HD's GameModel (fade_transition.py): the panel stays under the closing blinds with the script held, the
        # script runs once they are shut, and the next panel is revealed with input off throughout.
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        from exp_runtime.fade_transition import FadeTransition
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            words, (title, text) = text_words('Title', 'Body')
            resources = Resources(vm_program(*host_call(16, 2), *host_call(33, title, text, 4000),
                                             *host_call(33, title, text, 4000), 0x33, words=words))
            resources.library.directory = Path(temporary)
            resources.library.hd_app_version = lambda: '1.4.38'          # the HD bundle's own transition model
            ui = Desktop(Session(resources), audio=False)
            ui.window = pygame.display.set_mode((768, 1024), pygame.RESIZABLE)
            transition = ui.session.engine.scene_transition
            self.assertIsInstance(transition, FadeTransition)
            self.assertEqual(ui.session.pending.name, 'message_panel')
            ui.session.engine.scene_value = 2
            ui.session.tick(5000)
            first = ui.session.pending
            ui.command(('continue',))
            self.assertEqual((transition.selector, transition.phase), (2, 4))
            self.assertIs(ui.session.pending, first)                # held: the script has not run yet
            before = ui.session.snapshot()
            ui.command(('continue',))                               # input is off while the blinds run
            ui.command(('menu',))
            self.assertFalse(ui.menu_open)
            self.assertEqual(ui.session.snapshot(), before)
            ui._draw_transition()
            ui.tick(1499)
            self.assertIs(ui.session.pending, first)
            ui.tick(1)                                              # shut: the callback, then the next panel
            self.assertIsNot(ui.session.pending, first)
            self.assertEqual((ui.session.pending.name, transition.phase), ('message_panel', 3))
            ui._draw_transition()
            ui.tick(1800)                                           # 0.3 s wait, then 1.2 s of opening
            self.assertFalse(ui.session.transitioning)

    def test_window_input_save_load_and_resized_mouse_coordinates(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            ui = Desktop(Session(resources), audio=False)
            ui.session.tick(250)
            ui.render()
            saved = ui.session.snapshot()
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            self.assertEqual(ui.session.snapshot(), saved)  # Enter cannot invent a choice.
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F5))
            self.assertTrue(ui.session.save_path.exists())
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
            self.assertEqual(ui.session.pending.details['text'], 'Went right.')
            ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F9))
            self.assertEqual(ui.session.snapshot(), saved)
            ui.window = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
            ui.render()
            rect = next(rect for rect, command in ui.buttons if command == ('choose', 0))
            x = ui.viewport.x + rect.centerx * ui.viewport.width / 480
            y = ui.viewport.y + rect.centery * ui.viewport.height / 720
            ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y)))
            self.assertEqual(ui.session.snapshot(), saved)
            ui.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(x, y)))
            self.assertEqual(ui.session.pending.details['text'], 'Went left.')
            self.assertIsNone(ui.error)
            self.assertFalse(ui.handle_event(pygame.event.Event(pygame.QUIT)))

    def test_arrow_keys_focus_a_choice_and_enter_picks_it(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with tempfile.TemporaryDirectory() as temporary:
            resources = Resources(branching_program())
            resources.library.directory = Path(temporary)
            ui = Desktop(Session(resources), audio=False)
            ui.render()
            key = lambda code: ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code))
            key(pygame.K_DOWN)
            self.assertEqual(ui.choice_focus, 0)                # the first press selects the top row
            key(pygame.K_DOWN)
            key(pygame.K_DOWN)
            self.assertEqual(ui.choice_focus, 1)                # and stops at the last one
            ui.render()
            key(pygame.K_UP)
            self.assertEqual(ui.choice_focus, 0)
            ui.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(0, 0), rel=(1, 1), buttons=(0, 0, 0)))
            self.assertIsNone(ui.choice_focus)                  # the mouse takes over
            key(pygame.K_UP)
            self.assertEqual(ui.choice_focus, 1)                # Up first selects the bottom row
            ui.tick(250)                                        # past the menu's 250 ms attachment
            key(pygame.K_RETURN)
            self.assertEqual(ui.session.pending.details['text'], 'Went right.')
            ui.render()
            self.assertIsNone(ui.choice_focus)

    @unittest.skipUnless(Path('.shs-library/library.json').is_file(), 'user library is not present')
    def test_original_dialogue_fonts_on_opening_and_saved_choice_branches(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.content import ContentLibrary
        from exp_runtime.desktop import Desktop
        import pygame

        self.addCleanup(pygame.quit)
        with ContentLibrary(Path('.shs-library')) as library:
            resources = library.open_episode('The_New_Girl.exp')
            ui = Desktop(Session(resources), audio=False)
            screens = 0
            while ui.session.pending.name in ('presentation', 'dialogue') and screens < 100:
                ui.render()
                self.assertIsNone(ui.error)
                answer_screen(ui.session)
                screens += 1
            self.assertEqual(screens, 35)
            self.assertEqual(ui.session.pending.name, 'choice')
            saved = ui.session.snapshot()
            for choice in (0, 1):
                ui.session = Session.from_snapshot(resources, saved)
                ui.session.answer(choice)
                ui.render()
                self.assertIsNone(ui.error)
                self.assertEqual(ui.session.pending.name, 'dialogue')
            self.assertIn('ArialRoundedMTBold16', ui.story_text.fonts)
            self.assertIn('TrebuchetMS_Italic16', ui.story_text.fonts)
            self.assertTrue(any(name.startswith('PajamaHip') for name in ui.story_text.fonts))

    def test_continue_tab_tracks_box_theme_and_reveal_without_drawing_side_effects(self):
        from unittest.mock import Mock, patch
        from exp_runtime.desktop_dialogue import DialogueRenderer
        from exp_runtime.dialogue_animation import DialogueAnimation
        from exp_runtime.ui_assets import Rect
        import pygame
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        pygame.display.init(); pygame.display.set_mode((320, 480))
        self.addCleanup(pygame.quit)
        text = Mock()
        text.font.return_value = SimpleNamespace(cap_height=10)
        text.layout.return_value = SimpleNamespace(ink_bounds=(0, 0, 50, 10))
        renderer = DialogueRenderer(None, text, None)
        def frame(asset, index):
            self.assertEqual(asset, 126)
            tab = pygame.Surface((99, 17), pygame.SRCALPHA)
            tab.fill((index * 20, 100, 150, 255))
            return tab
        renderer.frame = frame
        motion = DialogueAnimation(10)
        with patch('exp_runtime.desktop_dialogue.MenuStrings.load', return_value={29: 'Continue'}):
            for theme, index in ((1, 5), (2, 3), (3, 6), (-1, 4)):
                for box in (Rect(13, 55, 294, 68), Rect(25, 115, 130, 40)):
                    renderer.canvas.fill((0, 0, 0))
                    renderer.draw_continue_tab(box, theme, motion)
                    self.assertEqual(tuple(renderer.canvas.get_at((box.x + box.width - 50, box.y + box.height))[:3]), (0, 0, 0))
                    motion.settle()
                    renderer.draw_continue_tab(box, theme, motion)
                    self.assertEqual(tuple(renderer.canvas.get_at((box.x + box.width - 50, box.y + box.height + 8))[:3]),
                                     (index * 20, 100, 150))
                    self.assertEqual(tuple(renderer.canvas.get_at((box.x + box.width, box.y + box.height + 8))[:3]), (0, 0, 0))
                    self.assertEqual(motion.continue_ms, 250)
                    motion.next_page(10)
            self.assertEqual(text.draw_layout.call_count, 4)
            self.assertTrue(all(call.args[1] == 'TrebuchetMS_Bold14' for call in text.draw_layout.call_args_list))

    def test_held_choice_cancels_on_drag_and_deal_change(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        from exp_runtime.desktop import Desktop
        from test_minigames import word_resources
        self.addCleanup(pygame.quit)
        ui = Desktop(Session(word_resources()), audio=False)
        ui.tick(400)
        # Authored host buttons exercise the production input path without art.
        ui.viewport = pygame.Rect(0, 0, 480, 720)
        ui.buttons = [(pygame.Rect(20, 20, 100, 50), ('choose', 0)),
                      (pygame.Rect(20, 80, 100, 50), ('choose', 1))]
        def pointer(kind, pos=(40, 40)):
            ui.handle_event(pygame.event.Event(kind, button=1, pos=pos))
        before = ui.session.snapshot()
        pointer(pygame.MOUSEBUTTONDOWN)
        self.assertEqual(ui.press.pressed, ('choose', 0))
        self.assertEqual(ui.session.snapshot(), before)
        pointer(pygame.MOUSEMOTION, (40, 100))
        self.assertIsNone(ui.press.pressed)
        pointer(pygame.MOUSEBUTTONUP, (40, 100))
        self.assertEqual(ui.session.snapshot(), before)
        pointer(pygame.MOUSEBUTTONDOWN)
        pointer(pygame.MOUSEMOTION, (-1, -1))
        pointer(pygame.MOUSEMOTION)
        self.assertEqual(ui.press.pressed, ('choose', 0))
        pointer(pygame.MOUSEBUTTONUP)
        self.assertEqual(ui.session.engine.word_game.round, before['engine']['word_game']['round'] + 1)
        pointer(pygame.MOUSEBUTTONDOWN)
        ui.session.answer(0)  # Another input/round invalidates the old finger.
        changed = ui.session.snapshot()
        pointer(pygame.MOUSEBUTTONUP)
        self.assertEqual(ui.session.snapshot(), changed)
        pointer(pygame.MOUSEBUTTONDOWN)
        ui.cancel_pointer()
        pointer(pygame.MOUSEBUTTONUP)
        self.assertEqual(ui.session.snapshot(), changed)

    def test_main_menu_row_hands_the_pause_box_to_the_main_menu(self):
        from unittest.mock import Mock
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        ui = Desktop.__new__(Desktop)
        ui.session, ui.error, ui.menu_open, ui.active, ui.fade = Mock(), None, True, True, None
        ui.press, ui.gear_pointer_down, ui.on_main_menu = Mock(), False, Mock()
        ui._sync_text_input = ui._menu_sound = ui.render = lambda *args, **kwargs: None
        ui.pause_box = lambda: 'box'
        ui.command(('main_menu',))
        ui.on_main_menu.assert_called_once_with(pause_box='box')
        self.assertFalse(ui.menu_open)

    def test_choice_hints_switch_and_preview_time_stays_off_the_story_clock(self):
        from unittest.mock import Mock
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        from exp_runtime.desktop import Desktop
        ui = Desktop.__new__(Desktop)
        ui.session, ui.error, ui.menu_open, ui.active, ui.fade = Mock(), None, False, True, None
        ui.press, ui.gear_pointer_down, ui.on_settings = Mock(), False, Mock()
        ui._sync_text_input = ui._ui_sound = lambda *args, **kwargs: None
        ui.choice_hints = False
        ui.command(('pause_toggle', 'choice_hints'))
        self.assertTrue(ui.choice_hints)
        ui.on_settings.assert_called_once()
        # A 1900 ms preview is charged to the frames after it, not to the story.
        ui._attempt = lambda operation: operation()
        ui.hint_discount_ms = 1900
        ui.tick(1916)
        ui.session.tick.assert_called_once_with(16)
        self.assertEqual(ui.hint_discount_ms, 0)
        ui.hint_discount_ms = 1900
        ui.tick(1000)
        ui.tick(1000)
        self.assertEqual([c.args[0] for c in ui.session.tick.call_args_list[1:]], [0, 100])
