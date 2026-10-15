import os
import unittest
from types import SimpleNamespace

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from exp_runtime.dtview_faceplace import DTView, FaceplaceWall


class _FakeDialogueRenderer:
    """Duck-types the one method these panels call on DialogueRenderer."""
    def __init__(self, portrait_surface=None):
        self.portrait_surface = portrait_surface

    def portrait(self, asset_id, flipped):
        return self.portrait_surface


def _engine(dt_view=None, faceplace=None, character_names=None, character_art_variants=None):
    return SimpleNamespace(
        dt_view=dt_view or DTView(),
        faceplace=faceplace or FaceplaceWall(),
        character_names=character_names or {},
        character_art_variants=character_art_variants or {},
    )


class DTViewRendererTests(unittest.TestCase):
    def _setup(self):
        import pygame
        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode((1, 1))
        return pygame

    def test_empty_tree_draws_nothing(self):
        pygame = self._setup()
        from exp_runtime.desktop_panels import DTViewRenderer

        renderer = DTViewRenderer(None, None, None)
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        session = SimpleNamespace(engine=_engine())
        renderer.draw(window, session, 1.0, pygame.Rect(0, 0, 220, 720))
        self.assertEqual(pygame.image.tobytes(window, 'RGBA'), bytes(480 * 720 * 4))

    def test_zero_progress_draws_nothing_even_with_real_content(self):
        pygame = self._setup()
        from exp_runtime.desktop_panels import DTViewRenderer

        dt = DTView()
        dt.add_node(1203, 'Week 1', 0)
        renderer = DTViewRenderer(None, None, None)
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        session = SimpleNamespace(engine=_engine(dt_view=dt))
        renderer.draw(window, session, 0.0, pygame.Rect(0, 0, 220, 720))
        self.assertEqual(pygame.image.tobytes(window, 'RGBA'), bytes(480 * 720 * 4))

    def test_zero_width_margin_draws_nothing(self):
        pygame = self._setup()
        from exp_runtime.desktop_panels import DTViewRenderer

        dt = DTView()
        dt.add_node(1203, 'Week 1', 0)
        renderer = DTViewRenderer(None, None, None)
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        session = SimpleNamespace(engine=_engine(dt_view=dt))
        renderer.draw(window, session, 1.0, pygame.Rect(0, 0, 0, 720))
        self.assertEqual(pygame.image.tobytes(window, 'RGBA'), bytes(480 * 720 * 4))

    def test_real_tree_draws_in_the_given_margin_with_the_current_node_highlighted(self):
        pygame = self._setup()
        from exp_runtime.desktop_panels import DTViewRenderer, BOX, BOX_CURRENT

        dt = DTView()
        dt.add_node(1203, 'Week 1', 0)
        dt.add_result(0, '')
        dt.add_node(1206, 'Meet Beth', 20)  # becomes dt.current
        renderer = DTViewRenderer(None, None, None)
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        margin = pygame.Rect(40, 0, 220, 720)
        session = SimpleNamespace(engine=_engine(dt_view=dt))
        renderer.draw(window, session, 1.0, margin)
        # Fully open (progress=1.0): the panel sits flush against the
        # margin's own left edge, not the window's.
        colors = {tuple(window.get_at((margin.x + x, y))[:3])
                 for x in (20, 30) for y in (20, 30, 90, 100)}
        self.assertTrue(colors & {BOX, BOX_CURRENT})
        # Nothing drawn to the left of the margin itself.
        self.assertEqual(tuple(window.get_at((10, 50))), (0, 0, 0, 0))

    def test_a_node_outside_the_current_path_is_drawn_inactive(self):
        # Regression for the real cross-playthrough persistence: a branch
        # explored on an earlier playthrough but not part of *this* one's
        # path should still show, desaturated -- not simply vanish or look
        # identical to the active path (see legacy/findings.md).
        pygame = self._setup()
        from exp_runtime.desktop_panels import DTViewRenderer, BOX, BOX_INACTIVE

        dt = DTView()
        # A branch node (CHOICEBRANCH2): a plain choice / game node keeps only one branch (see DTView.add_node).
        dt.add_node(1219, 'What are you into?', 0)
        root = dt.root
        dt.add_result(0, 'Sports')
        dt.add_node(1210, 'Flirt with Beth', 0)  # dt.current, path taken this time
        dt.pending_result_index, dt.current = 1, root  # simulate: a *different* branch persisted from before
        other = dt.add_node(1204, 'Some other branch', 0)
        dt.current = root.children[0]  # restore the real current path
        renderer = DTViewRenderer(None, None, None)
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        renderer.draw(window, SimpleNamespace(engine=_engine(dt_view=dt)), 1.0, pygame.Rect(0, 0, 260, 720))
        self.assertIn(BOX_INACTIVE, {tuple(window.get_at((x, y))[:3])
                                     for x in range(0, 260, 4) for y in range(0, 200, 4)})

    def test_an_offered_but_untaken_choice_renders_as_an_unfilled_placeholder(self):
        # Real device confirmed (see dtview_faceplace.py module docstring):
        # the tree shows every choice the player was offered, not just the
        # branches actually taken ("see all the choices map out"). A slot
        # with a label but no real DTNode child renders as an outline-only
        # placeholder -- filled color would wrongly imply it was explored on
        # some other playthrough.
        pygame = self._setup()
        from exp_runtime.desktop_panels import (
            DTViewRenderer, BOX_INACTIVE, BORDER_INACTIVE, BOX_CURRENT)

        dt = DTView()
        dt.add_node(1216, 'What are you into?', 0)
        dt.current.choice_labels = {0: 'Sports', 1: 'Girls', 2: 'TV'}
        dt.add_result(2, 'TV')
        dt.add_node(1206, 'Meet Spud', 20)  # only slot 2 was ever taken
        renderer = DTViewRenderer(None, None, None)
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, 260, 720)
        renderer.draw(window, SimpleNamespace(engine=_engine(dt_view=dt)), 1.0, rect)

        ghost_box = pygame.Rect(12, 78, 236, 52)  # the "Sports" placeholder
        interior = {tuple(window.get_at((x, y))[:3])
                   for x in range(ghost_box.x + 4, ghost_box.right - 4, 4)
                   for y in range(ghost_box.y + 4, ghost_box.bottom - 4, 4)}
        self.assertNotIn(BOX_INACTIVE, interior)  # unfilled, not desaturated-filled
        edge = {tuple(window.get_at((x, y))[:3])
               for x in range(ghost_box.x, ghost_box.right, 2)
               for y in range(ghost_box.y, ghost_box.bottom, 2)}
        self.assertIn(BORDER_INACTIVE, edge)  # but its outline is still drawn

        taken_box = pygame.Rect(52, 202, 196, 52)  # "Meet Spud", the real taken slot
        taken_colors = {tuple(window.get_at((x, y))[:3])
                        for x in range(taken_box.x, taken_box.right, 4)
                        for y in range(taken_box.y, taken_box.bottom, 4)}
        self.assertIn(BOX_CURRENT, taken_colors)

    def test_a_real_node_type_draws_its_recovered_icon_badge(self):
        # Real per-node-type icon indices recovered from raw disassembly of
        # each DTNode_* subclass's own get_image_id() getter (see
        # NODE_TYPE_IMAGE_ID's docstring) -- 1209 is DTNode_Date, image_id 1,
        # rendered as a two-circle heart badge in this renderer's own design.
        pygame = self._setup()
        from exp_runtime.desktop_panels import DTViewRenderer, ICON_COLORS

        dt = DTView()
        dt.add_node(1209, 'Movie Night', 0)
        renderer = DTViewRenderer(None, None, None)
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        renderer.draw(window, SimpleNamespace(engine=_engine(dt_view=dt)), 1.0, pygame.Rect(0, 0, 260, 720))

        icon_area = {tuple(window.get_at((x, y))[:3])
                    for x in range(10, 32, 2) for y in range(16, 68, 2)}
        self.assertIn(ICON_COLORS[1], icon_area)

    def test_a_ghost_placeholder_draws_no_icon_since_its_type_is_unknown(self):
        # A ghost's node_type is never known -- it was never actually
        # visited (see _GhostChild's docstring) -- so it must not draw any
        # of the real icon badge colors, which would wrongly imply a type.
        pygame = self._setup()
        from exp_runtime.desktop_panels import DTViewRenderer, ICON_COLORS

        dt = DTView()
        dt.add_node(1216, 'What are you into?', 0)
        dt.current.choice_labels = {0: 'Sports', 1: 'Girls', 2: 'TV'}
        dt.add_result(2, 'TV')
        dt.add_node(1206, 'Meet Spud', 20)
        renderer = DTViewRenderer(None, None, None)
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        renderer.draw(window, SimpleNamespace(engine=_engine(dt_view=dt)), 1.0, pygame.Rect(0, 0, 260, 720))

        ghost_box = pygame.Rect(12, 78, 236, 52)  # the "Sports" placeholder
        icon_area = {tuple(window.get_at((x, y))[:3])
                    for x in range(ghost_box.x + 10, ghost_box.x + 32, 2)
                    for y in range(ghost_box.y, ghost_box.bottom, 2)}
        self.assertFalse(icon_area & set(ICON_COLORS.values()))

    def test_a_descendant_of_current_stays_colored_not_inactive(self):
        # Real device confirmed: a node further along the *same* already-
        # recorded continuation as the current one reads as "still my
        # future" (full color) even before this playthrough has actually
        # reached it -- only a sibling branch diverging behind current is
        # desaturated. Ancestors-only was tried first and was wrong.
        pygame = self._setup()
        from exp_runtime.desktop_panels import DTViewRenderer, BOX, BOX_INACTIVE

        dt = DTView()
        dt.add_node(1206, 'Meet Adam', 0)
        dt.add_result(0, '')
        dt.add_node(1215, 'Speak to Adam', 0)
        dt.add_result(0, '')
        dt.add_node(1206, 'Meet Raven', 0)  # A prior playthrough's continuation.
        dt.current = dt.root  # This playthrough is only at "Meet Adam" so far.
        renderer = DTViewRenderer(None, None, None)
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        renderer.draw(window, SimpleNamespace(engine=_engine(dt_view=dt)), 1.0, pygame.Rect(0, 0, 260, 720))
        colors = {tuple(window.get_at((x, y))[:3]) for x in range(0, 260, 4) for y in range(0, 220, 4)}
        self.assertNotIn(BOX_INACTIVE, colors)
        self.assertIn(BOX, colors)


class FaceplacePanelRendererTests(unittest.TestCase):
    def _setup(self):
        import pygame
        self.addCleanup(pygame.quit)
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode((1, 1))
        return pygame

    def test_no_messages_draws_nothing(self):
        pygame = self._setup()
        from exp_runtime.desktop_panels import FaceplacePanelRenderer

        renderer = FaceplacePanelRenderer(None, None, None, _FakeDialogueRenderer())
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        session = SimpleNamespace(engine=_engine())
        renderer.draw(window, session, 1.0, pygame.Rect(260, 0, 220, 720))
        self.assertEqual(pygame.image.tobytes(window, 'RGBA'), bytes(480 * 720 * 4))

    def test_real_message_renders_name_inline_and_a_portrait_when_available(self):
        pygame = self._setup()
        from exp_runtime.desktop_panels import FaceplacePanelRenderer

        wall = FaceplaceWall()
        wall.incoming_message('is remembering the ropes.', 11, 2)
        portrait = pygame.Surface((32, 32), pygame.SRCALPHA)
        portrait.fill((200, 100, 50, 255))
        renderer = FaceplacePanelRenderer(None, None, None, _FakeDialogueRenderer(portrait))
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        margin = pygame.Rect(260, 0, 220, 720)
        session = SimpleNamespace(engine=_engine(
            faceplace=wall, character_names={11: 'Beth'},
            character_art_variants={11: [2010, 2010, 2010, 2010, 2010]}))
        renderer.draw(window, session, 1.0, margin)
        # Fully open: panel flush against the margin's own left edge; the
        # portrait tile sits near its top-left corner.
        self.assertEqual(tuple(window.get_at((margin.x + 18, 58))[:3]), (200, 100, 50))

    def test_zero_progress_draws_nothing_even_with_real_messages(self):
        pygame = self._setup()
        from exp_runtime.desktop_panels import FaceplacePanelRenderer

        wall = FaceplaceWall()
        wall.incoming_message('hello', 11, 2)
        renderer = FaceplacePanelRenderer(None, None, None, _FakeDialogueRenderer())
        window = pygame.Surface((480, 720), pygame.SRCALPHA)
        session = SimpleNamespace(engine=_engine(faceplace=wall))
        renderer.draw(window, session, 0.0, pygame.Rect(260, 0, 220, 720))
        self.assertEqual(pygame.image.tobytes(window, 'RGBA'), bytes(480 * 720 * 4))


if __name__ == '__main__':
    unittest.main()
