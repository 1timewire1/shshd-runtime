"""CgBI decoding and the HD side panels, with authored art only."""
from io import BytesIO
import importlib.util
import os
import struct
from types import SimpleNamespace
import unittest
import zlib

from PIL import Image

from exp_runtime.cgbi import CgBIError, decode, to_standard_png
from exp_runtime.dtview_faceplace import DTNode, FaceplaceMessage


def chunk(kind, body):
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))


def cgbi_png(size, pixels_bgr):
    """An authored CgBI file: CgBI chunk, raw deflate, BGR order."""
    width, height = size
    raw = b''.join(b'\0' + bytes(pixels_bgr[y * width * 3:(y + 1) * width * 3]) for y in range(height))
    compressor = zlib.compressobj(wbits=-15)
    stream = compressor.compress(raw) + compressor.flush()
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'CgBI', b'\0\0\0\0') + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', stream) + chunk(b'IEND', b''))


class CgBITests(unittest.TestCase):
    def test_channels_are_put_back_in_order(self):
        # Two pixels stored blue-first: (blue 10, green 20, red 30) and (1, 2, 3).
        image = decode(cgbi_png((2, 1), bytes([10, 20, 30, 1, 2, 3])))
        self.assertEqual(image.mode, 'RGB')
        self.assertEqual(list(image.getdata()), [(30, 20, 10), (3, 2, 1)])

    def test_ordinary_pngs_pass_through_and_garbage_is_refused(self):
        buffer = BytesIO()
        Image.new('RGB', (2, 2), (5, 6, 7)).save(buffer, 'PNG')
        png, swapped = to_standard_png(buffer.getvalue())
        self.assertFalse(swapped)
        self.assertEqual(decode(png).getpixel((0, 0)), (5, 6, 7))
        with self.assertRaises(CgBIError):
            decode(b'not a png')


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'desktop extra is not installed')
class SidePanelTests(unittest.TestCase):
    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        pygame.init()
        pygame.display.set_mode((16, 16))
        self.addCleanup(pygame.quit)
        from exp_runtime import desktop_side_panels as module
        self.module, self.pygame = module, pygame

        def solid(size, color):
            surface = pygame.Surface(size, pygame.SRCALPHA)
            surface.fill(color)
            return surface

        colors = {0: (60, 60, 60, 255), 1: (0, 0, 200, 255), 3: (0, 0, 220, 255), 72: (0, 90, 200, 255), 56: (10, 10, 10, 255)}
        self.art = SimpleNamespace(
            scale=2, hd_chrome=lambda: True, pack=lambda _id: SimpleNamespace(images=[None] * 80),
            frame_native=lambda pack, index: solid((23 if index == 0 else 100, 40), colors.get(index, (9, 9, 9, 255))),
            portrait_group=lambda portrait: (solid((256, 300), (255, 0, 255, 255)), (-128, -150)))
        def layout(name, text, width, style):
            lines = (1 + len(text) // 26) if text else 0
            return SimpleNamespace(lines=[None] * lines, width=0, glyphs=[],
                                   height=lines * style.height + max(0, lines - 1) * style.gap)

        text = SimpleNamespace(fonts={}, font=lambda name: SimpleNamespace(base=10, line_height=12,
                                                                          glyph=lambda c: SimpleNamespace(advance=4)),
                               layout=layout, draw_layout=lambda *a, **k: None)
        alert = SimpleNamespace(available=lambda: True, fonts=lambda: ('body', 'name'), shrink=lambda g, size: solid(size, (255, 0, 255, 255)),
                                emoticon_font=lambda: ('body', {}), with_emoticons=lambda text: text,
                                key=lambda engine, message: SimpleNamespace(portrait=None, name='', text=message.text))
        self.renderer = module.SidePanels(SimpleNamespace(library=None), text, self.art, alert)
        self.renderer.collage = lambda: solid((1045, 1024), (255, 255, 255, 255))
        self.renderer.node_frames = lambda: [(solid((134, 113), (200, 0, 0, 255)), solid((134, 113), (120, 120, 120, 255)))] * 12
        self.renderer.strings = lambda: None
        self.window = pygame.Surface((2667, 2000))

    def session(self, tree=False, wall=False):
        from exp_runtime.dtview_faceplace import DTView, FaceplaceWall
        engine = SimpleNamespace(dt_view=DTView(), faceplace=FaceplaceWall(), character_names={})
        if tree:
            engine.dt_view.enabled = True               # the script's scriptEnable (service 101)
            engine.dt_view.add_node(1206, 'Meet Beth', 0)
        if wall:
            engine.faceplace.enabled = True
            engine.faceplace.incoming_continuation_text('Want to try more games?', '')
        return SimpleNamespace(engine=engine)

    def draw(self, session, progress=1.0):
        pygame = self.pygame
        self.window.fill((0, 0, 0))
        self.renderer.draw(self.window, session, progress, pygame.Rect(0, 0, 583, 2000), pygame.Rect(2084, 0, 583, 2000))

    def test_without_content_each_panel_is_the_faded_collage_slice_with_its_divider(self):
        self.draw(self.session())
        # Black under a half-alpha white collage: mid gray (127/128).
        self.assertIn(self.window.get_at((100, 800))[0], (127, 128))
        self.assertIn(self.window.get_at((2300, 800))[0], (127, 128))
        # The divider sits at the game-facing edge of each: 11.5 points, dark.
        self.assertEqual(self.window.get_at((580, 800))[:3], (60, 60, 60))
        self.assertEqual(self.window.get_at((2086, 800))[:3], (60, 60, 60))

    def test_with_content_the_panels_are_white_with_their_bars_and_headers(self):
        self.draw(self.session(tree=True, wall=True))
        self.assertEqual(self.window.get_at((100, 800))[:3], (255, 255, 255))
        self.assertEqual(self.window.get_at((2300, 800))[:3], (255, 255, 255))
        self.assertEqual(self.window.get_at((100, 30))[:3], (9, 9, 9))         # one scene: nothing to rewind to (frame 2)
        self.assertEqual(self.window.get_at((100, 1980))[:3], (9, 9, 9))       # ... or to fast forward to
        self.assertEqual(self.window.get_at((2300, 30))[:3], (0, 90, 200))     # faceplace header (frame 72)

    def test_rewind_and_fast_forward_show_only_where_there_is_a_scene_to_go_to(self):
        session = self.session(tree=True)
        view = session.engine.dt_view
        view.add_node(1206, 'Meet Adam', 0)                                    # at the second scene: rewind is possible
        self.draw(session)
        self.assertEqual(self.window.get_at((100, 30))[:3], (0, 0, 220))       # Rewind bar (frame 3)
        self.assertEqual(self.window.get_at((100, 1980))[:3], (9, 9, 9))
        self.assertEqual([target[0] for _rect, target in self.renderer.tree_targets if target[0] != 'node'], ['rewind'])
        view.current = view.root                                               # back at the first: fast forward instead
        view.sweep_forward(view.root)
        self.draw(session)
        self.assertEqual(self.window.get_at((100, 30))[:3], (9, 9, 9))
        self.assertEqual(self.window.get_at((100, 1980))[:3], (0, 0, 200))     # Fast Forward bar (frame 1)
        self.assertEqual([target[0] for _rect, target in self.renderer.tree_targets if target[0] != 'node'], ['forward'])

    def test_while_warping_is_locked_both_bars_show_and_a_black_line_closes_each(self):
        # `SHSEngine +0x6490a`: until Football Season is finished both bars show even with nowhere to go.
        self.renderer.warp_locked = True
        self.draw(self.session(tree=True))
        self.assertEqual(self.window.get_at((100, 30))[:3], (0, 0, 220))       # Rewind bar (frame 3) at the first scene
        self.assertEqual(self.window.get_at((100, 1980))[:3], (0, 0, 200))     # Fast Forward bar (frame 1)
        self.assertEqual(sorted(target[0] for _rect, target in self.renderer.tree_targets if target[0] != 'node'),
                         ['forward', 'rewind'])
        scale = 2000 / 768
        self.assertEqual(self.window.get_at((100, int(35.5 * scale)))[:3], (0, 0, 0))   # the title view's last row
        self.assertEqual(self.window.get_at((100, int(732.5 * scale)))[:3], (0, 0, 0))  # the help view's first

    def test_a_saved_tree_does_not_enable_the_panel_of_an_episode_that_never_asked_for_one(self):
        # The tree file is library-wide (it persists across playthroughs); `script_enable` is per episode.
        session = self.session(tree=True, wall=True)
        session.engine.dt_view.enabled = session.engine.faceplace.enabled = False
        self.draw(session)
        self.assertIn(self.window.get_at((100, 800))[0], (127, 128))
        self.assertIn(self.window.get_at((2300, 800))[0], (127, 128))
        self.assertEqual([target for _rect, target in self.renderer.tree_targets], [])

    def test_a_script_enabled_panel_is_white_even_while_empty(self):
        session = self.session()
        session.engine.dt_view.enabled = session.engine.faceplace.enabled = True
        self.draw(session)
        self.assertEqual(self.window.get_at((100, 800))[:3], (255, 255, 255))
        self.assertEqual(self.window.get_at((2300, 800))[:3], (255, 255, 255))

    def test_panels_slide_in_from_their_own_edges(self):
        self.draw(self.session(tree=True, wall=True), progress=0.0)
        self.assertEqual(self.window.get_at((100, 800))[:3], (0, 0, 0))
        self.assertEqual(self.window.get_at((2300, 800))[:3], (0, 0, 0))

    def test_a_long_tree_keeps_its_size_scrolls_to_the_current_scene_and_touches_only_what_is_on_show(self):
        session = self.session(tree=True)
        for depth in range(60):
            session.engine.dt_view.add_result(0, '')
            session.engine.dt_view.add_node(1206, f'Node {depth}', 0)
        self.draw(session)
        panels = self.renderer
        self.assertEqual(panels.tree_sz_now, 52.7)                     # the app's own size; it does not shrink to fit
        self.assertGreater(panels.tree_scroll, 5000)                    # the newest scene is in view, far down the tree
        nodes = [target[1] for _rect, target in panels.tree_targets if target[0] == 'node']
        self.assertTrue(0 < len(nodes) < 12)
        self.assertIn(session.engine.dt_view.current, nodes)
        panels.zoom_tree(-20, (300, 900))                                # zoomed right out, more of it shows
        self.draw(session)
        self.assertEqual(panels.tree_sz_now, 10.0)
        self.assertGreater(len([1 for _rect, target in panels.tree_targets if target[0] == 'node']), 12)

    def wall_session(self, posts):
        session = self.session(wall=False)
        session.engine.faceplace.enabled = True
        for number in range(posts):
            session.engine.faceplace.incoming_message(f'Post number {number} says something quite long to wrap over lines', -1, 0)
        return session

    def test_a_long_wall_scrolls_within_its_scroll_view_and_stops_at_both_ends(self):
        session = self.wall_session(40)
        panels = self.renderer
        self.draw(session)
        self.assertEqual(panels.wall_scroll, 0.0)
        panels.scroll_wall(-50)                                         # above the first post: nothing to scroll to
        self.draw(session)
        self.assertEqual(panels.wall_scroll, 0.0)
        panels.scroll_wall(100)
        self.draw(session)
        self.assertEqual(panels.wall_scroll, 100.0)
        panels.scroll_wall(10 ** 6)                                     # no bounce (`setBounces:NO`): the end of the wall
        self.draw(session)
        posts, content = panels._wall_layout(session.engine, session.engine.faceplace)
        self.assertEqual(panels.wall_scroll, content - (768 - 36))

    def test_a_short_wall_does_not_scroll(self):
        session = self.wall_session(2)
        self.renderer.scroll_wall(500)
        self.draw(session)
        self.assertEqual(self.renderer.wall_scroll, 0.0)

    def test_a_new_message_scrolls_back_to_the_top_but_a_continuation_does_not(self):
        session = self.wall_session(40)
        panels, wall = self.renderer, session.engine.faceplace
        self.draw(session)
        panels.scroll_wall(300)
        self.draw(session)
        wall.incoming_continuation_text('Tap here to get Pogo Games!', 'http://example.invalid/pogo')
        self.draw(session)
        self.assertEqual(panels.wall_scroll, 300.0)
        wall.incoming_message('Something new', -1, 0)
        self.draw(session)
        self.assertEqual(panels.wall_scroll, 0.0)

    def face_post(self, text):
        session = self.session()
        session.engine.faceplace.enabled = True
        session.engine.faceplace.incoming_message(text, 0, 0)              # from 0: `isFaceMessage`
        return session

    def test_rows_are_measured_as_the_app_measures_them(self):
        module = self.module
        # One line beside a face: 13.3 of text and descent, 3 above, 7 under the last row, made up to 56.
        rows, content = self.renderer._wall_layout(*self._wall(self.face_post('Short')))
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0].height, 13.3 + module.TEXT_TOP + module.LAST_PAD)
        self.assertEqual(rows[0].advance, 56)
        self.assertEqual(content, 56)
        # Six lines (IMG_0245's post): 89.8 tall, so the rule is at int(89.8 - 2) = 87 points below the row's top.
        rows, content = self.renderer._wall_layout(*self._wall(self.face_post('x' * 26 * 5)))
        self.assertAlmostEqual(rows[0].advance, 6 * 13.3 + 10)
        self.assertEqual(int(rows[0].advance - module.RULE_RISE), 87)

    def _wall(self, session):
        return session.engine, session.engine.faceplace

    def test_a_continuation_is_its_own_row_and_a_rows_padding_counts_towards_the_56(self):
        session = self.face_post('Short')
        session.engine.faceplace.incoming_continuation_text('Tap here', 'http://example.invalid/pogo')
        rows, content = self.renderer._wall_layout(*self._wall(session))
        self.assertEqual([(row.first, row.last) for row in rows], [(True, False), (False, True)])
        self.assertAlmostEqual(rows[0].height, 13.3 + 3)                    # no 7: not the group's last row
        self.assertAlmostEqual(rows[0].advance, 13.3 + 3 + 3)               # ... but 3 more below it
        self.assertAlmostEqual(rows[1].height, 13.3 + 7)                    # a continuation's text starts at its top
        self.assertAlmostEqual(content, 56 + 3)                             # the heights are made up to 56, not the advances

    def test_a_picture_continuation_is_its_caption_then_the_picture_and_both_are_the_link(self):
        session = self.face_post('Short')
        session.engine.faceplace.incoming_continuation_image(2200, 'Play now!', 'http://example.invalid/game')
        rows = self.renderer._wall_layout(*self._wall(session))[0]
        self.assertEqual([row.picture is not None for row in rows], [False, False, True])
        self.assertEqual([row.last for row in rows], [False, False, True])
        picture = rows[2].picture
        self.assertEqual(rows[2].height, picture.get_height() + self.module.PICTURE_PAD + self.module.LAST_PAD)
        self.draw(session)
        self.assertEqual(len(self.renderer.wall_targets), 2)               # the caption's row and the picture's

    def test_a_post_without_a_face_keeps_its_continuation_under_it_and_is_not_made_up_to_56(self):
        # `-1 -11 text~url` (IMG_0299's "Looking for another fun game to try?" and its link).
        session = self.wall_session(1)
        session.engine.faceplace.incoming_continuation_text('Tap here', 'http://example.invalid/sims')
        rows, content = self.renderer._wall_layout(*self._wall(session))
        self.assertEqual([(row.first, row.last, row.face) for row in rows], [(True, False, False), (False, True, False)])
        self.assertAlmostEqual(content, sum(row.height for row in rows) + 3)

    def test_a_link_can_be_tapped_only_where_it_shows(self):
        session = self.wall_session(1)
        wall = session.engine.faceplace
        wall.incoming_continuation_text('Tap here to get Pogo Games!', 'http://example.invalid/pogo')
        self.draw(session)
        links = self.renderer.wall_targets
        self.assertEqual([url for _rect, url in links], ['http://example.invalid/pogo'])
        rect = links[0][0]
        self.assertTrue(self.renderer.wall_rect.contains(rect))
        for post in range(60):                                          # older posts push the link out of the scroll view
            wall.incoming_message(f'Filler {post}', -1, 0)
        self.draw(session)
        self.renderer.scroll_wall(-10 ** 6)
        self.draw(session)
        self.assertEqual([url for _rect, url in self.renderer.wall_targets], [])
        self.renderer.scroll_wall(10 ** 6)
        self.draw(session)
        self.assertEqual([url for _rect, url in self.renderer.wall_targets], ['http://example.invalid/pogo'])


if __name__ == '__main__':
    unittest.main()
