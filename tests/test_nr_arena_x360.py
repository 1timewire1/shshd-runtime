"""shshd-runtime: New Rules' arena in the X360 prototype's look (desktop_nr_arena_x360.py), drawn from an authored
stand-in for the X360 addon's skin over the New Rules stand-in skin (test_nr_arena_render): the fallback without the
addon, the record carrying the ring, the clicks kept, the HUD, and the player's switch and sound swap."""
import importlib.util
import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from test_nr_arena_render import skin_files

PICTURES = ('note', 'note_broken', 'remix', 'beamed', 'cross', 'stamp_pow', 'stamp_yeah', 'stamp_ooops', 'power_bar',
            'power_fill_green', 'power_fill_yellow', 'power_fill_blue', 'bubble', 'info_box', 'sticker', 'tutorial_1',
            'tutorial_2', 'tutorial_3', 'particles', 'big_particles', 'flames', 'smoke', 'deck_texture', 'note_double',
            'note_fire')
FONTS = ('casual', 'casual_white', 'badaboom', 'badaboom_white', 'turntablz')


def x360_skin(pygame):
    """{resource: bytes} of a small X360 skin in the addon's format (tools/translate/x360_arena_art.py)."""
    def png(colour, size=(16, 16)):
        surface = pygame.Surface(size, pygame.SRCALPHA)
        surface.fill(colour)
        out = io.BytesIO()
        pygame.image.save(surface, out, 'x.png')
        return out.getvalue()
    resources, spec, next_id = {}, dict(format='shshd-arena-skin-x360', version=1, pictures={}, items={}, fonts={},
                                        sounds={'whoosh_1': 26380, 'fail': 26381, 'swap': 26382},
                                        sound_tracks={'13': [26380], '1': [26381], '11': [26382]},
                                        music_track={'14': 26390}), 26301
    for name in PICTURES:
        resources[next_id] = png((40, 200, 40, 255))
        spec['pictures'][name] = next_id
        next_id += 1
    spec['items'] = {str(i): spec['pictures']['note'] for i in range(29)}
    page = 26360
    resources[page] = png((0, 0, 0, 255), (64, 64))
    chars = {str(ord(ch)): [0, 0, 8, 10, 0, 0, 9, 0] for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!:+- .'}
    for name in FONTS:
        spec['fonts'][name] = dict(line_height=12, base=10, chars=chars, kerning={}, pages=[page])
    for i, resource in enumerate((26380, 26381, 26382, 26390)):
        resources[resource] = b'RIFF' + bytes([i])
    # The booth: the deck 1100 wide, the record 670 x 280 on it, every digit slot one 10 x 16 cell.
    resources[26400] = resources[26401] = resources[26402] = png((90, 100, 120, 255), (110, 40))
    atlas = 26403
    resources[atlas] = png((220, 30, 20, 255), (100, 128))
    slots = [[dict(rect=[n * 10, i * 16, 10, 16], box=[900 + 90 * i, 180, 990 + 90 * i, 330]) for n in range(10)]
             for i in range(8)]
    for n in range(10):
        slots[6][n]['box'] = [1180, 680, 1260, 900]
        slots[7][n]['box'] = [1320, 680, 1400, 900]
    for k, name in enumerate(('school_front_diss_002', 'school_hallway_b_diss_001', 'josh_house_in_diss_001',
                              'school_front_diss_001', 'school_hallway_b_diss_002')):
        resources[26404 + k] = png((150, 150, 140, 255), (64, 36))
    spec['booth'] = dict(frame=[1848, 1040], camera='cameras/diss_002', places={
        'school_front_diss_002': 26404}, pieces=dict(deck=dict(id=26400, box=[370, 570, 1470, 970]),
                                                     table=dict(id=26401, box=[370, 570, 1470, 970]),
                                                     record=dict(id=26402, box=[520, 570, 1190, 862])),
        digits=dict(atlas=atlas, slots=slots, score=list(range(6)), time=[6, 7]))
    resources[26300] = json.dumps(spec).encode()
    return resources


def library(resources):
    archive = SimpleNamespace(entries=resources, read=resources.__getitem__)
    return SimpleNamespace(addon=lambda addon_id: ({'addon': addon_id}, archive) if addon_id == 'shsx360' else None)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class X360ArenaTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((1, 1))
        from exp_runtime import desktop_nr_arena, desktop_nr_arena_x360
        self.pygame, self.nr, self.module = pygame, desktop_nr_arena, desktop_nr_arena_x360
        files = skin_files(pygame, frame=(10, 20, 30))
        names = {**desktop_nr_arena.SKIN, 'frame.png': desktop_nr_arena.FRAME_PICTURE}
        self.nr_files = {resource: files[name] for name, resource in names.items()}

    def resources(self, with_addon=True):
        by_id = self.nr_files
        return SimpleNamespace(raw_asset=by_id.__getitem__, exists=by_id.__contains__,
                               library=library(x360_skin(self.pygame)) if with_addon else SimpleNamespace(
                                   addon=lambda addon_id: None))

    def session(self, arena):
        from exp_runtime.nr_arena import ENTRANCE_MS
        arena.entrance_ms = ENTRANCE_MS
        return SimpleNamespace(engine=SimpleNamespace(nr_arena=arena, resolve_text=lambda vm, i: None), vm=None,
                               pending=SimpleNamespace(name='arena_frame', details={}))

    def arena(self):
        from exp_runtime.nr_arena import NRArena
        arena = NRArena.opened(False, True)
        arena.set(-10, 729, 6)
        arena.item_kind = 2
        for slot in range(6):
            arena.set_item(slot, 8018 + slot)
        arena.timer_ms = arena.timer_total_ms = 25000
        arena.timer_shown = True
        arena.score = 3580
        return arena

    def test_without_the_x360_addon_it_isnt_available(self):
        renderer = self.module.X360ArenaRenderer(self.resources(with_addon=False))
        self.assertFalse(renderer.available())
        self.assertFalse(self.module.library_has_skin(self.resources(with_addon=False).library))
        self.assertTrue(self.module.library_has_skin(self.resources().library))

    def test_it_draws_smoothly_at_the_frames_size_and_keeps_new_rules_clicks(self):
        renderer = self.module.X360ArenaRenderer(self.resources())
        self.assertTrue(renderer.available())
        renderer.target_height = 1500
        renderer.draw(None, self.session(self.arena()), now_ms=1234)
        # Not a whole-number scale-up: the frame's own height in the window, at 3:4.
        self.assertEqual(renderer.canvas.get_height(), 1500)
        self.assertAlmostEqual(renderer.canvas.get_width() * 4 / renderer.canvas.get_height(), 3, places=2)
        # The same clicks as New Rules' look: its OK button stays a target (the needle is OK in this look too).
        nr = self.nr.NRArenaRenderer(SimpleNamespace(raw_asset=self.nr_files.__getitem__,
                                                     exists=self.nr_files.__contains__))
        nr.draw(None, self.session(self.arena()), now_ms=1234)
        self.assertEqual(renderer.hit((379, 655)), nr.hit((379, 655)))
        self.assertEqual(renderer.hit((379, 655)), ('arena_key', -5))

    def test_the_ring_follows_the_record_and_the_deck_keeps_its_size_through_a_new_ring_size(self):
        renderer = self.module.X360ArenaRenderer(self.resources())
        arena = self.arena()
        renderer.draw(None, self.session(arena), now_ms=0)
        ring = renderer._field(arena)
        u, cx, cy, rx, ry, _, _ = renderer._deck()
        self.assertAlmostEqual(ring.centerx, cx, delta=1)
        self.assertAlmostEqual(ring.centery, cy, delta=1)
        self.assertAlmostEqual(ring.width / ring.height, 670 / 280, delta=0.2)       # the record's own ellipse
        # A game setting a smaller ring (Fever, Sequences) moves the items, not the deck; a shake (a size each frame)
        # does move it.
        arena.ring_size = 60
        for now in range(0, 1000, 33):
            renderer._paint_x360(renderer.canvas, arena, self.session(arena), now, 0, 0, False)
        self.assertEqual(renderer._sizes[-1][1], 60)
        self.assertEqual(sorted(s for _, s in renderer._sizes)[len(renderer._sizes) // 2], 60)

    def test_the_score_shows_six_digits_and_right_and_wrong_flash_as_stamps(self):
        renderer = self.module.X360ArenaRenderer(self.resources())
        arena = self.arena()
        arena.set_label(694, 'wrong!')                     # box 1's flash label (693-695)
        drawn = []
        real = renderer.blit
        renderer.blit = lambda surface, image, *a, **k: drawn.append(image) or real(surface, image, *a, **k)
        renderer.draw(None, self.session(arena), now_ms=0)
        self.assertIn(renderer.picture('stamp_ooops'), drawn)
        self.assertEqual(self.module.plain_runs('`rap` rhymes~ with;'), [('rap', True), (' rhymes', False),
                                                                          (' with', False)])

    def test_the_countdown_runs_once_press_ok_to_start_closes(self):
        renderer = self.module.X360ArenaRenderer(self.resources())
        arena = self.arena()
        arena.bubbles[0] = ('press ok to start', 0, -4)
        renderer.draw(None, self.session(arena), now_ms=1000)
        self.assertIsNone(renderer.countdown)
        arena.bubbles[0] = None                            # OK pressed: the game runs, the 3-2-1 plays over it
        renderer.draw(None, self.session(arena), now_ms=1100)
        self.assertEqual(renderer.countdown, 1100)
        renderer.draw(None, self.session(arena), now_ms=1100 + 2300)     # 0.5 + 0.75 + 1 s later: gone
        self.assertIsNone(renderer.countdown)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class X360SwitchTests(unittest.TestCase):
    def desktop(self, with_addon=True, arena=True):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((1, 1))
        from exp_runtime.desktop import Desktop
        from exp_runtime.desktop_nr_arena import NRArenaRenderer
        from exp_runtime.desktop_nr_arena_x360 import X360ArenaRenderer
        resources = SimpleNamespace(library=library(x360_skin(pygame)) if with_addon
                                    else SimpleNamespace(addon=lambda addon_id: None))
        ui = Desktop.__new__(Desktop)
        ui.session = SimpleNamespace(resources=resources, engine=SimpleNamespace(nr_arena=object() if arena else None))
        ui.nr_arena_renderer = NRArenaRenderer(resources)
        ui.x360_arena_renderer = X360ArenaRenderer(resources)
        ui.x360_arena_renderer.available = lambda: ui.x360_arena_renderer.x360() is not None   # no New Rules skin here
        ui._x360_arena = None
        ui.hires_switch = Mock(return_value=True)
        return ui

    def test_the_switch_needs_the_addon_and_picks_the_renderer(self):
        ui = self.desktop()
        self.assertTrue(ui.x360_arena_switch())
        self.assertIs(ui._arena_renderer(), ui.nr_arena_renderer)          # New Rules' look by default
        ui.arena_skin = True
        self.assertIs(ui._arena_renderer(), ui.x360_arena_renderer)
        ui.arena_minigames = False                                          # no arena, no look to choose
        ui._arena_minigames = False
        self.assertFalse(ui.x360_arena_switch())
        self.assertIs(ui._arena_renderer(), ui.nr_arena_renderer)
        ui = self.desktop(with_addon=False)
        ui.x360_arena_renderer.available = lambda: False
        ui.arena_skin = True
        self.assertFalse(ui.x360_arena_switch())
        self.assertIs(ui._arena_renderer(), ui.nr_arena_renderer)

    def test_the_x360_sounds_and_music_stand_in_only_while_the_arena_shows_in_its_look(self):
        ui = self.desktop()
        self.assertIsNone(ui._x360_swaps())                                 # the switch is off
        ui.arena_skin = True
        sounds, music, archive = ui._x360_swaps()
        self.assertEqual(sounds, {26993: [26380], 26981: [26381], 26991: [26382]})
        self.assertEqual(music, {26994: 26390})
        self.assertEqual(archive.read(26390), b'RIFF\x03')
        ui = self.desktop(arena=False)
        ui.arena_skin = True
        self.assertIsNone(ui._x360_swaps())                                 # a word game's jingles stay New Rules'

    def test_the_look_is_new_rules_by_default_and_kept(self):
        from exp_runtime.menu import preference_defaults
        self.assertIs(preference_defaults()['arena_skin'], False)


if __name__ == '__main__':
    unittest.main()
