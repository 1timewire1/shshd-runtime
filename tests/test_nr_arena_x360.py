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
            'note_fire', 'fx_spark_0', 'fx_puff_0')
FONTS = ('casual', 'casual_white', 'badaboom', 'badaboom_white', 'turntablz')


def x360_skin(pygame, title=True, parts=False):
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
    if parts:
        # The deck split: a blue body, a green record, a white seam from the hole to the right, a yellow spindle, and
        # three arm frames: magenta boxes side by side (the atlas's rows) whose boxes step along the deck's front.
        resources[26414] = png((0, 0, 200, 255), (110, 40))
        resources[26415] = png((0, 120, 0, 255), (67, 28))
        seam = pygame.Surface((64, 64), pygame.SRCALPHA)
        seam.fill((255, 255, 255, 255), (32, 30, 32, 4))
        out = io.BytesIO()
        pygame.image.save(seam, out, 'x.png')
        resources[26416] = out.getvalue()
        resources[26417] = png((255, 255, 0, 255), (4, 8))
        resources[26418] = png((255, 0, 255, 255), (20, 30))
        spec['booth']['parts'] = dict(
            body=dict(id=26414, box=[370, 570, 1470, 970]), record=dict(id=26415, box=[520, 570, 1190, 862]),
            seams=dict(id=26416, centre=[855, 700], radius=180, squash=2.5),
            spindle=dict(id=26417, box=[840, 650, 870, 700]),
            arm=dict(atlas=26418, push=[[0, 0], [100, -10], [400, 20], [1000, 0]], frames=[
                dict(angle=-10, rect=[0, 0, 20, 10], box=[1000, 900, 1100, 950], tip=[1000, 950]),
                dict(angle=0, rect=[0, 10, 20, 10], box=[800, 900, 900, 950], tip=[800, 900]),
                dict(angle=20, rect=[0, 20, 20, 10], box=[600, 800, 700, 850], tip=[600, 800])]))
    if title:
        # The title backdrop: a red sky, clouds clear but for a white band (source x 24-28 of 32), two green glints
        # (the whole screen, then its right fifth) and a front black along the bottom quarter.
        resources[26410] = png((200, 0, 0, 255), (64, 36))
        clouds = pygame.Surface((32, 16), pygame.SRCALPHA)
        clouds.fill((255, 255, 255, 255), (24, 0, 4, 16))
        resources[26412] = png((0, 255, 0, 255), (16, 8))
        front = pygame.Surface((64, 36), pygame.SRCALPHA)
        front.fill((0, 0, 0, 255), (0, 27, 64, 9))
        for resource, surface in ((26411, clouds), (26413, front)):
            out = io.BytesIO()
            pygame.image.save(surface, out, 'x.png')
            resources[resource] = out.getvalue()
        spec['title'] = dict(sky=26410, clouds=dict(id=26411, opacity=0.5, speed=0.01), front=26413,
                             rays=dict(atlas=26412, ms=50, every=3000,
                                       frames=[dict(rect=[0, 0, 8, 8], box=[0, 0, 1, 1]),
                                               dict(rect=[8, 0, 8, 8], box=[0.8, 0, 1, 1])]))
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

    def test_the_canvas_is_exactly_3_by_4_so_the_player_lays_it_over_the_whole_frame(self):
        # Desktop._present lays a layer over the whole frame only at exactly 3:4; a pixel off, it took the canvas for
        # the story's 320 x 480 column and the backdrop showed inside the frame's window (owner, 2026-10-31).
        renderer = self.module.X360ArenaRenderer(self.resources())
        for height in (1024, 1057, 1081, 1500):
            renderer.target_height = height
            renderer.draw(None, self.session(self.arena()), now_ms=0)
            w, h = renderer.canvas.get_size()
            self.assertEqual(w * 512, h * 384, (height, w, h))

    def test_long_bubble_text_wraps_and_an_emphasised_word_keeps_its_edge(self):
        renderer = self.module.X360ArenaRenderer(self.resources())
        renderer.draw(None, self.session(self.arena()), now_ms=0)
        lines = renderer.wrapped('casual', 'AAAA BBBB CCCC DDDD\nEE', 12, 85)
        self.assertEqual(len(lines), 3)                 # 9 a letter: two words a line, then its own break
        self.assertTrue(all(line.get_width() / renderer.k <= 85 + 12 for line in lines))
        self.assertIs(renderer.wrapped('casual', 'AAAA BBBB CCCC DDDD\nEE', 12, 85), lines)     # worked out once
        # Two-tone (white fill, black edge) text keeps its black edge when a word takes the emphasis colour.
        face = renderer.bmfont('casual_white')
        glyph = face.render([('A', (255, 214, 64))])
        colours = {glyph.get_at((x, y))[:3] for x in range(glyph.get_width()) for y in range(glyph.get_height())
                   if glyph.get_at((x, y))[3] > 0}
        self.assertEqual(colours, {(0, 0, 0)})          # the stand-in page is all black: it stays black

    def test_bubbles_sit_on_the_slot_machines_panel_or_a_speech_bubble_with_an_older_addon(self):
        def drawn(renderer):
            renderer.draw(None, self.session(self.arena()), now_ms=0)
            renderer._nine = Mock()
            renderer._bubble_x360(renderer.canvas, self.arena(), None, 'HI', -1, 0, 0)
            return renderer._nine.call_args.args
        renderer = self.module.X360ArenaRenderer(self.resources())
        renderer.draw(None, self.session(self.arena()), now_ms=0)
        self.assertIsNone(renderer.panel_art())                 # (an addon of revision 1)
        self.assertIs(drawn(renderer)[1], renderer.bubble_art()[0])
        renderer = self.module.X360ArenaRenderer(self.resources())
        spec = renderer.x360()[0]
        spec['slot'] = dict(panel=spec['pictures']['info_box'])
        args = drawn(renderer)
        art, edges, _, _, narrowest = renderer.panel_art()
        self.assertIs(args[1], art)
        self.assertEqual(args[6], edges)
        self.assertGreaterEqual(args[4], narrowest)             # a short line keeps both flourishes whole

    def test_the_deck_ignores_a_ring_easing_in_and_follows_a_shake(self):
        renderer = self.module.X360ArenaRenderer(self.resources())
        arena = self.arena()
        session = self.session(arena)
        drawn = []
        real = renderer.blit
        deck = renderer.image(renderer.x360()[0]['booth']['pieces']['deck']['id'])

        def blit(surface, image, x, y, w=None, h=None, **k):
            if image is deck:
                drawn.append(w)
            return real(surface, image, x, y, w, h, **k)
        renderer.blit = blit
        for now, size in enumerate(range(40, 100, 4)):          # easing in: one way only
            arena.ring_size = size
            renderer._paint_x360(renderer.canvas, arena, session, now * 33, 0, 0, False)
        self.assertEqual(len(set(round(w, 3) for w in drawn)), 1)
        drawn.clear()
        for now, size in enumerate((100, 112, 90, 110, 92, 108)):      # a shake: back and forth
            arena.ring_size = size
            renderer._paint_x360(renderer.canvas, arena, session, 2000 + now * 33, 0, 0, False)
        self.assertGreater(len(set(round(w, 3) for w in drawn)), 1)

    def split_deck(self):
        resources = self.resources()
        resources.library = library(x360_skin(self.pygame, parts=True))
        renderer = self.module.X360ArenaRenderer(resources)
        renderer.k = 1
        return renderer, renderer.x360()[0]['booth']['parts']

    def arm(self, motion=1):
        """A split deck's renderer, a turning arena, and `frame(now)`: a frame of drawing, giving the arm's angle."""
        renderer, parts = self.split_deck()
        arena = self.arena()
        arena.motion = motion
        from exp_runtime.desktop_x360_deck import ARM_SPEED

        def frame(now):                                     # `now` on PUSH's own clock, which plays ARM_SPEED times as fast
            renderer._arm_press(arena, now / ARM_SPEED)
            return renderer._arm_frame(parts['arm'], now / ARM_SPEED)['angle']
        frame(0)                                            # the frame before any press
        return renderer, arena, frame

    def test_the_tone_arm_plays_push_at_the_x360s_speed(self):
        renderer, parts = self.split_deck()
        renderer._arm_start = 1000
        self.assertEqual(renderer._arm_frame(parts['arm'], 1100)['angle'], 20)    # PUSH's 400 ms in, 100 ms on

    def with_notes(self, renderer):
        from test_x360_diss import NOTE_CAMERA
        spec = renderer.x360()[0]
        red = self.pygame.Surface((20, 40), self.pygame.SRCALPHA)
        red.fill((255, 0, 0, 255))
        renderer._images[26790] = red
        spec['booth']['parts']['camera'] = NOTE_CAMERA
        spec['booth']['frame'] = [1848, 1040]
        spec['booth']['notes'] = dict(frame=[2560, 1440], height=.25, wheel=[-.1447, 1.0085, -7.8384], out=1.19, kinds={
            kind: dict(id=26790, anchor=[10, 40], depth=3.5) for kind in ('note', 'bad', 'swap', 'double')})

    def test_the_notes_are_the_booths_as_large_as_their_place_on_the_record(self):
        renderer, _ = self.split_deck()
        arena = self.arena()
        self.assertIsNone(renderer._note_of(20))                    # an addon without them keeps the flat pictures
        self.with_notes(renderer)
        ring = renderer._field(arena)
        surface = self.pygame.Surface(self.module.FRAME, self.pygame.SRCALPHA)
        near = renderer._item_x360(surface, arena, 20, 2, ring.centerx, ring.bottom, -1)
        far = renderer._item_x360(surface, arena, 20, 2, ring.centerx, ring.top, -1)
        self.assertGreater(near.height, far.height)
        self.assertAlmostEqual(near.bottom, ring.bottom * renderer.k, delta=1)    # standing where it's put
        for item in (20, 17, 19, 18, 28):
            self.assertIsNotNone(renderer._note_of(item))
        self.assertIsNone(renderer._note_of(21))                    # a cross isn't a note

    def test_the_tone_arm_swings_through_push_from_a_press_in_play_and_rests_otherwise(self):
        _, arena, frame = self.arm()
        self.assertEqual(frame(1), 0)
        arena.button_ms[0] = 250                            # the press, the key taken
        self.assertEqual(frame(1000), 0)                    # PUSH's first key
        arena.button_ms[0] = 200
        self.assertEqual(frame(1100), -10)                  # back, away from the record
        arena.button_ms[0] = 100
        self.assertEqual(frame(1400), 20)                   # then in, over it
        arena.button_ms[0] = -1
        self.assertEqual(frame(1800), 0)                    # easing back; the 250 ms highlight is long over
        self.assertEqual(frame(2000), 0)
        arena.button_ms[0] = 250                            # another press in the swing starts it again
        self.assertEqual(frame(3000), 0)
        self.assertEqual(frame(3400), 20)
        arena.button_ms[0] = 240
        self.assertEqual(frame(3400), 20)
        arena.button_ms[0] = 250
        self.assertEqual(frame(3500), 0)
        self.assertEqual(frame(3900), 20)

    def assert_no_swing(self, arena, frame):
        arena.button_ms[0] = 250
        for now in (1000, 1100, 1400):
            self.assertEqual(frame(now), 0)

    def test_closing_a_prompt_doesnt_swing_the_arm_though_the_bubble_is_gone_by_the_next_frame(self):
        for text in ('press ok to start', "Time's up!", 'your score: 57', 'press ok to finish tutorial.'):
            with self.subTest(text):
                _, arena, frame = self.arm()
                arena.bubbles[0] = [text, 0, 0]
                frame(1)                                    # the prompt drawn
                arena.bubbles[0] = None                     # the press closes it, before the next frame
                self.assert_no_swing(arena, frame)

    def test_the_arm_stays_still_once_time_is_up_and_before_a_game_and_in_the_number_keys_game(self):
        for name, change in (('time up', dict(timer_ms=0)), ('held', dict(time_up=1)), ('still', dict(motion=2)),
                             ('before the ring is set', dict(motion=0, timer_ms=-1)), ('keypad', dict(keypad=True))):
            with self.subTest(name):
                _, arena, frame = self.arm()
                for key, value in change.items():
                    setattr(arena, key, value)
                frame(1)
                self.assert_no_swing(arena, frame)

    def test_a_tutorials_practice_with_the_turntable_swings_the_arm_but_a_gap_between_its_bubbles_doesnt(self):
        _, arena, frame = self.arm()
        arena.timer_ms = -1                                 # no timer yet: "press ok when the green item..."
        frame(1)
        arena.button_ms[0] = 250
        self.assertEqual(frame(1000), 0)
        arena.button_ms[0] = 200
        self.assertEqual(frame(1100), -10)
        _, arena, frame = self.arm()
        arena.keys.append(16)                               # the library isn't reading keys here
        frame(1)
        self.assert_no_swing(arena, frame)

    def test_a_press_waits_for_the_library_to_take_it_and_feedback_is_play_whatever_came_before(self):
        _, arena, frame = self.arm()
        frame(1)
        arena.keys.append(16)
        arena.button_ms[0] = 250
        self.assertEqual(frame(1000), 0)
        arena.keys.clear()                                  # taken 100 ms on: PUSH starts then
        arena.button_ms[0] = 150
        self.assertEqual(frame(1100), 0)
        self.assertEqual(frame(1200), -10)
        _, arena, frame = self.arm(motion=2)
        frame(1)
        arena.button_ms[0] = 250
        arena.feedback = 1
        self.assertEqual(frame(1000), 0)
        self.assertEqual(frame(1100), -10)

    def test_the_records_seams_turn_with_the_panels_angle_about_the_hole_and_the_rest_stays(self):
        import pygame
        renderer, parts = self.split_deck()
        arena = self.arena()
        surface = pygame.Surface((700, 900))

        def bright(angle):
            surface.fill((0, 0, 0))
            arena.angle = angle
            renderer._record_seams(surface, arena, parts['seams'], 1, 0)
            return {(x, y) for x in range(700) for y in range(900) if surface.get_at((x, y))[0] > 100}
        at_0 = bright(0)
        u, _, _, _, _, _, _ = renderer._deck()
        hx, hy, _, _ = renderer._to_native([855, 700, 855, 700])
        reach = 180 * u
        self.assertTrue(at_0)
        self.assertGreater(max(x for x, _ in at_0), hx + reach * 0.8)   # to the right, from the hole
        self.assertLess(max(abs(y - hy) for _, y in at_0), reach / 2.5 * 0.2)
        at_90 = bright(90)                                  # clockwise on screen, as the ring's angles run: down
        self.assertGreater(max(y for _, y in at_90), hy + reach / 2.5 * 0.8)
        self.assertLess(max(abs(x - hx) for x, _ in at_90), reach * 0.2)
        self.assertEqual(at_0, bright(1))                   # a step of SEAM_STEP degrees, kept

    def test_a_split_deck_is_drawn_in_order_and_follows_the_shake_and_the_rise(self):
        renderer, parts = self.split_deck()
        arena = self.arena()
        session = self.session(arena)
        drawn = []
        real = renderer.blit

        def blit(surface, image, x, y, w=None, h=None, **k):
            drawn.append((image, x, y, w))
            return real(surface, image, x, y, w, h, **k)
        renderer.blit = blit
        renderer._paint_x360(renderer.canvas, arena, session, 0, 0, 0, False)
        order = [renderer.image(parts[name]['id']) for name in ('body', 'record', 'spindle')]
        seen = [row for row in drawn if row[0] in order or row[0] is renderer._arm_cell(parts['arm'], parts['arm']['frames'][1])]
        self.assertEqual([row[0] for row in seen[:3]], order)
        self.assertIs(seen[3][0], renderer._arm_cell(parts['arm'], parts['arm']['frames'][1]))    # at rest
        rested = {id(row[0]): row for row in seen}
        drawn.clear()
        renderer._paint_x360(renderer.canvas, arena, session, 40, 0, 100, True)
        for row in drawn:
            if id(row[0]) in rested and row[0] in order:
                self.assertAlmostEqual(row[2], rested[id(row[0])][2] + 100)

    def test_a_press_glows_at_the_needle_only_with_feedback_on_a_split_deck(self):
        import pygame
        renderer, parts = self.split_deck()
        arena = self.arena()
        ring = pygame.Rect(0, 0, 300, 120)
        surface = pygame.Surface((800, 900))
        arena.button_ms[0] = 250
        arena.feedback = 0
        renderer._needle(surface, arena, ring)
        self.assertEqual(surface.get_at((400, 400))[:3], (0, 0, 0))
        self.assertEqual(max(surface.get_at((x, y))[1] for x in range(0, 800, 4) for y in range(0, 900, 4)), 0)
        arena.feedback = 1
        renderer._now = 0
        renderer._needle(surface, arena, ring)
        x, y, _, _ = renderer._to_native([800, 900, 800, 900])       # the resting frame's tip
        self.assertGreater(surface.get_at((round(x), round(y)))[1], 100)

    def test_a_sequences_item_takes_clicks_over_its_whole_drawn_picture(self):
        # The X360 pictures stand taller than New Rules' item cell (61 x 31): a click on the top of a note missed
        # (owner, 2026-11-01). The target is the picture as drawn.
        import pygame
        renderer = self.module.X360ArenaRenderer(self.resources())
        arena = self.arena()
        arena.keypad = True
        tall = {}

        def picture(surface, item, x, bottom, height, alpha=255):
            rect = pygame.Rect(round((x - 20) * renderer.k), round((bottom - 80) * renderer.k), round(40 * renderer.k),
                               round(80 * renderer.k))
            tall[item] = (x, bottom)
            return rect
        renderer._item_picture = picture
        renderer.draw(None, self.session(arena), now_ms=0)
        x, bottom = tall[arena.slots[0]]
        frame = (x * 768 / 489, (bottom - 75) * 1024 / 652)            # near the top of the drawn picture
        self.assertEqual(renderer.hit(frame), ('arena_key', 48 + int(self.nr.KEYPAD[0])))

    def test_hits_burst_sparks_when_right_and_smoke_when_wrong_once_a_press(self):
        from exp_runtime.nr_arena import POPUP_TEXT, Popup
        renderer = self.module.X360ArenaRenderer(self.resources())
        arena = self.arena()
        session = self.session(arena)
        renderer.draw(None, session, now_ms=0)
        self.assertEqual(renderer.effects, [])
        arena.button_ms[0], arena.feedback = 250, 1                 # OK pressed on a good note
        renderer.draw(None, session, now_ms=33)
        arena.button_ms[0] = 217                                    # the same press, still lit
        renderer.draw(None, session, now_ms=66)
        self.assertEqual([e[0] for e in renderer.effects], ['good'])
        arena.button_ms[0], arena.feedback = 250, 2                 # pressed again before the light went out: wrong
        renderer.draw(None, session, now_ms=99)
        self.assertEqual([e[0] for e in renderer.effects], ['good', 'bad'])
        renderer.draw(None, session, now_ms=5000)                   # both over
        self.assertEqual(renderer.effects, [])
        # Sequences: no OK feedback; the key's flash and its "-3" popup say a wrong pick, at that item.
        arena.button_ms[0], arena.feedback = -1, 0
        arena.keypad, arena.keypad_flash, arena.keypad_flash_ms = True, 2, 500
        arena.popups.append(Popup(POPUP_TEXT, arena.text_index('-3'), 2, -5, duration_ms=500))
        renderer.draw(None, session, now_ms=6000)
        self.assertEqual([e[0] for e in renderer.effects], ['bad'])

    def test_the_backdrop_is_the_title_screen_with_drifting_clouds_and_a_glint_every_3_s(self):
        pygame = self.pygame
        renderer = self.module.X360ArenaRenderer(self.resources())
        surface = pygame.Surface((48, 64)).convert()
        # 64 high: the title's 16:9 screen is 114 wide, the frame its right 48 (TITLE_X 1). The clouds' band (114 *
        # 24/32 = 85.5 to 99.75 across the screen) shows at 19.5-33.75 in the frame, half white over the red sky.
        renderer._backdrop(surface, 1, 200)
        self.assertEqual(surface.get_at((5, 5))[:3], (200, 0, 0))
        self.assertEqual(surface.get_at((26, 5))[:3], (228, 128, 128))
        self.assertEqual(surface.get_at((24, 60))[:3], (0, 0, 0))                 # the front's city over all
        # Ten seconds on the clouds have slid left a tenth of the screen (11 pixels), wrapping.
        renderer._backdrop(surface, 1, 10200)
        self.assertEqual(surface.get_at((15, 5))[:3], (228, 128, 128))
        self.assertEqual(surface.get_at((30, 5))[:3], (200, 0, 0))
        # The glints sweep over the first 50 ms of every 3 s, one at a time.
        renderer._backdrop(surface, 1, 3010)
        self.assertEqual(surface.get_at((5, 5))[:3], (0, 255, 0))
        renderer._backdrop(surface, 1, 3060)
        self.assertEqual(surface.get_at((5, 5))[:3], (200, 0, 0))                  # the second: the right fifth only
        self.assertEqual(surface.get_at((40, 5))[:3], (0, 255, 0))
        # Fading in with the arena: the whole backdrop at the given alpha over what's there.
        surface.fill((0, 0, 0))
        renderer._backdrop(surface, 0.5, 200)
        self.assertEqual(surface.get_at((5, 5))[:3], (100, 0, 0))

    def test_a_skin_without_the_title_keeps_diss_practices_place(self):
        resources = self.resources()
        resources.library = library(x360_skin(self.pygame, title=False))
        renderer = self.module.X360ArenaRenderer(resources)
        surface = self.pygame.Surface((48, 64)).convert()
        renderer._backdrop(surface, 1, 200)
        self.assertEqual(surface.get_at((24, 5))[:3], (150, 150, 140))

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

    def test_the_x360_music_fades_out_at_times_up_and_new_rules_music_is_left_alone(self):
        from exp_runtime.nr_arena import NRArena
        ui = self.desktop()
        ui.arena_skin = True
        self.assertTrue(ui.x360_arena_switch())
        arena = NRArena.opened(False, True)
        engine = SimpleNamespace(nr_arena=arena)
        stream = SimpleNamespace(current=dict(id=26390), fade=None, stop=Mock())
        ui._end_x360_music(stream, engine, 100)
        stream.stop.assert_not_called()                     # the game is on
        arena.bubbles[0] = ['Get ready!', 0, 0]              # another bubble: still playing
        ui._end_x360_music(stream, engine, 150)
        stream.stop.assert_not_called()
        arena.timer_ms, arena.timer_total_ms, arena.time_up = 0, 40000, 0
        arena.set(-10, 762, 0, text="Time's up!")            # the timer out, its bubble shows: time_up
        self.assertEqual(arena.time_up, 1)
        ui._end_x360_music(stream, engine, 200)
        stream.stop.assert_called_once()
        stream = SimpleNamespace(current=dict(id=26994), fade=None, stop=Mock())       # New Rules' own track
        ui._end_x360_music(stream, SimpleNamespace(nr_arena=None), 300)
        stream.stop.assert_not_called()
        stream = SimpleNamespace(current=dict(id=26390), fade=None, stop=Mock())       # the arena already gone
        ui._end_x360_music(stream, SimpleNamespace(nr_arena=None), 300)
        stream.stop.assert_called_once()

    def tutorial(self, title='welcome to the `rhyming` game.  view tutorial?', skin=True):
        from exp_runtime.nr_arena import NRArena
        ui = self.desktop()
        ui.arena_skin = skin
        action = SimpleNamespace(details=dict(title=title, options=['yes', 'no']))
        ui.session.pending = action
        ui.session.answer = Mock()
        ui.session.engine = SimpleNamespace(nr_arena=NRArena.opened(False, True), music_serial=4)
        ui._attempt = lambda work: work()
        ui.x360_arena_renderer.x360()[0]['tutorial_music'] = 26391
        ui.x360_arena_renderer.x360()[1].read = Mock(return_value=b'mp3')
        ui.music_enabled, ui.menu_open = True, False
        return ui, action

    def test_a_yes_to_view_tutorial_starts_the_tutorial_until_the_games_music_request(self):
        ui, action = self.tutorial()
        ui._resolve_arena_menu(action, 0)
        ui.session.answer.assert_called_once_with(0)
        self.assertTrue(ui._in_x360_tutorial())
        ui.session.engine.music_serial = 5                  # the game's own track
        self.assertFalse(ui._in_x360_tutorial())
        self.assertIsNone(ui.x360_tutorial)

    def test_no_tutorial_comes_from_a_no_or_another_menu_or_new_rules_own_look(self):
        ui, action = self.tutorial()
        ui._resolve_arena_menu(action, 1)
        self.assertFalse(ui._in_x360_tutorial())
        ui, action = self.tutorial(title='play again?')
        ui._resolve_arena_menu(action, 0)
        self.assertFalse(ui._in_x360_tutorial())
        ui, action = self.tutorial(skin=False)
        ui._resolve_arena_menu(action, 0)
        self.assertFalse(ui._in_x360_tutorial())

    def test_a_tutorial_loops_its_own_music_and_the_games_track_or_its_end_takes_over(self):
        ui, action = self.tutorial()
        stream = SimpleNamespace(current=None, fade=None, play=Mock(), stop=Mock())
        ui._x360_tutorial_music(stream, 100)
        stream.play.assert_not_called()                     # not before the yes
        ui._resolve_arena_menu(action, 0)
        ui._x360_tutorial_music(stream, 100)
        args = stream.play.call_args
        self.assertEqual(args.args[:2], (26391, True))
        self.assertEqual(args.args[2](26391), (b'mp3', 0))
        ui.music_enabled = False
        stream.play.reset_mock()
        ui._x360_tutorial_music(stream, 110)
        stream.play.assert_not_called()                     # Music off stays off
        stream.current = dict(id=26391)
        ui.session.engine.nr_arena = None                   # the arena gone before its game: nothing else stops it
        ui._end_x360_music(stream, ui.session.engine, 120)
        stream.stop.assert_called_once()

    def test_a_tutorials_hits_play_the_games_sounds_but_the_games_own_are_left_to_it(self):
        ui, action = self.tutorial()
        ui._play_sounds = Mock()
        ui.x360_arena_renderer.hits = ['good']
        ui._x360_tutorial_sounds()
        ui._play_sounds.assert_not_called()                 # the game's: its own script plays them
        ui._resolve_arena_menu(action, 0)
        self.assertEqual(ui.x360_arena_renderer.hits, [])   # (and they don't carry over)
        ui.x360_arena_renderer.hits = ['good', 'bad']
        ui._x360_tutorial_sounds()
        ui._play_sounds.assert_called_once_with([26980 + 13, 26980 + 1])
        self.assertEqual(ui.x360_arena_renderer.hits, [])

    def test_the_look_is_new_rules_by_default_and_kept(self):
        from exp_runtime.menu import preference_defaults
        self.assertIs(preference_defaults()['arena_skin'], False)


if __name__ == '__main__':
    unittest.main()
