from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from exp_runtime.desktop_hd_menu import HdMenuWindows
from exp_runtime.dtview_faceplace import DTNode, DTView, JOIN_NODE
from exp_runtime.menu_engine import BACK, MenuEngineData, MenuStack
from exp_runtime.runtime import SaveError, Session
from test_hd_menus import FakeLibrary, NO, engine_data
from test_runtime import Resources, answer_screen, host_call, text_words
from test_vm import program

ADD_NODE = ((0x1A, 1203), (0x1A, -1), (0x1F, 0x6602))            # addNode(type 1203, label '')


class TreeStructureTests(unittest.TestCase):
    def test_new_nodes_get_serials_and_a_repeated_join_shares_its_first_nodes(self):
        view = DTView()
        first = view.add_node(1203, '', 0, uid=5, script=10)
        second = view.add_node(JOIN_NODE, '', 0, uid=6, script=20)
        self.assertEqual((first.serial, second.serial), (1, 2))
        # A join reached again from another path carries the ids of the first one and so its number.
        other = DTView()
        other.add_node(1203, '', 0, uid=1, script=1)
        other.add_node(JOIN_NODE, '', 0, uid=6, script=20)
        other.current = None
        other.add_node(1203, '', 0, uid=1, script=1)                       # revisiting reuses the root: no new serial
        self.assertEqual(other.max_serial(), 2)
        self.assertIs(other.by_serial(2), other.root.children[0])
        self.assertIsNone(other.by_serial(9))

    def test_old_trees_without_serials_are_numbered_when_loaded(self):
        leaf = dict(node_type=JOIN_NODE, lower_label='', exw=0, uid=2, script=2, primary=False)
        middle = dict(node_type=1203, lower_label='', exw=0, uid=2, script=2, primary=True, children={'0': leaf})
        root = dict(node_type=1203, lower_label='', exw=0, uid=1, script=1, primary=True, children={'0': middle})
        view = DTView.from_dict(dict(root=root))
        self.assertEqual([node.serial for node in view.nodes()], [1, 2, 2])

    def test_a_node_without_results_continues_in_slot_zero(self):
        view = DTView()
        view.add_node(1216, '', 0, uid=1, script=1)
        view.add_result(1, '')
        view.add_node(1203, '', 0, uid=2, script=2)                        # a decision's chosen branch: slot 1
        view.add_node(1203, '', 0, uid=3, script=3)                        # its plain follower: slot 0, not 1
        self.assertEqual(sorted(view.root.children), [1])
        self.assertEqual(sorted(view.root.children[1].children), [0])

    def test_every_result_taken_keeps_its_exit_label_and_shows_as_a_stub_until_something_follows(self):
        from exp_runtime.desktop_panels import _GhostChild, _child_slots
        view = DTView()
        node = view.add_node(1216, 'What are you into?', 0, uid=1, script=1)
        view.add_result(0, 'Sports')
        view.add_result(2, 'TV')                                            # a later playthrough takes another result
        self.assertEqual(node.result_labels, {0: 'Sports', 2: 'TV'})
        slots = _child_slots(node)
        self.assertEqual(sorted(slots), [0, 2])
        self.assertTrue(all(isinstance(child, _GhostChild) for child in slots.values()))
        again = DTView.from_dict(view.to_dict())
        self.assertEqual(again.root.result_labels, {0: 'Sports', 2: 'TV'})
        older = view.to_dict()
        del older['root']['result_labels']                                  # a tree saved before the labels were kept
        self.assertEqual(DTView.from_dict(older).root.result_labels, {2: 'TV'})

    def test_rewind_and_fast_forward_skip_branches_and_joins(self):
        view = DTView()
        a = view.add_node(1203, '', 0, uid=1, script=1)
        auto = view.add_node(0x4c5, '', 0, uid=2, script=2)                 # an automatic branch
        view.add_node(JOIN_NODE, '', 0, uid=3, script=3)
        b = view.add_node(1203, '', 0, uid=4, script=4)
        self.assertIs(view.real_child(a), b)
        self.assertIs(view.real_parent(b), a)
        self.assertIsNone(view.real_parent(a))
        self.assertIsNone(view.real_child(b))
        self.assertIsNone(view.real_parent(auto))                         # never a visible stop on the path

    def test_a_path_that_loops_back_through_a_repeated_join_ends_instead_of_hanging(self):
        # Football Star's practice hub: a later join repeats the hub's ids, so the path continues from the hub again.
        # Opening the side panels on a scene off that loop froze the app (real_parent walked the loop forever).
        root = DTNode(1203, '', 0, uid=1, script=1, result_index=0)
        hub = DTNode(JOIN_NODE, '', 0, uid=10, script=10, serial=2)
        scene = DTNode(1203, '', 0, uid=11, script=11, serial=3)
        repeat = DTNode(JOIN_NODE, '', 0, uid=10, script=10, primary=False, serial=2)
        off_path = DTNode(1203, '', 0, uid=12, script=12, serial=4)
        root.children, hub.children, scene.children = {0: hub, 1: off_path}, {0: scene}, {0: repeat}
        view = DTView(root=root)
        self.assertIs(view.real_child(root), scene)
        self.assertIs(view.real_child(scene), scene)                        # the loop comes straight back
        self.assertIs(view.real_parent(scene), root)
        self.assertIsNone(view.real_parent(off_path))                       # off the loop: no parent, no hang
        # A loop of nothing but joins has no next visible scene.
        hub.children = {0: repeat}
        self.assertIsNone(view.real_child(root))


def dialogue_story(directory):
    words, refs = text_words('First scene', 'Second scene', 'Third scene')
    resources = Resources(program(*ADD_NODE, *host_call(13, refs[0], 0), *ADD_NODE, *host_call(13, refs[1], 0),
                                  *ADD_NODE, *host_call(13, refs[2], 0), 0x33, words=words))
    resources.library.directory = Path(directory)
    resources.record = dict(resources.record, builtin='football-star')      # the original app's one story tree
    return resources


class EpisodeTreeTests(unittest.TestCase):
    """Only Football Star adds to the library's original tree; any other episode keeps a tree of its own."""

    def test_another_episodes_tree_and_saved_scenes_are_its_own(self):
        with tempfile.TemporaryDirectory() as directory:
            football = Session(dialogue_story(directory))
            football.advance()
            other = dialogue_story(directory)
            other.record = dict(titles=['Authored story'])
            other.identity = dict(other.identity, episode_sha256='c' * 64)
            session = Session(other)
            self.assertIsNone(session.engine.dt_view.root)              # Football Star's tree is not loaded
            session.advance()
            answer_screen(session)
            library = Path(directory)
            self.assertEqual(session.dt_view_path, library / 'dtview' / ('c' * 64 + '.json'))
            self.assertEqual(sorted(path.name for path in (library / 'dtsaves' / ('c' * 64)).iterdir()),
                             ['1.json.gz', '2.json.gz'])
            self.assertEqual(sorted(path.name for path in (library / 'dtsaves').glob('*.json.gz')), ['1.json.gz'])
            self.assertEqual(len(list(Session(dialogue_story(directory)).engine.dt_view.nodes())), 1)
            again = Session(other)
            self.assertEqual((len(list(again.engine.dt_view.nodes())), again.tree_serials()), (2, {1, 2}))
            restored = again.warp(again.engine.dt_view.by_serial(2))
            self.assertIn('Second scene', restored.pending.details['text'])


class WarpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.resources = dialogue_story(self.temporary.name)

    def play_to(self, text):
        session = Session(self.resources)
        session.advance()
        while text not in session.pending.details['text']:
            answer_screen(session)
        return session

    def test_every_add_node_saves_the_game_at_that_point_and_warp_returns_to_it(self):
        session = self.play_to('Third scene')
        view = session.engine.dt_view
        nodes = list(view.nodes())
        self.assertEqual([node.serial for node in nodes], [1, 2, 3])
        self.assertTrue(all(session.has_tree_state(node) for node in nodes))
        self.assertEqual(sorted(path.name for path in (Path(self.temporary.name) / 'dtsaves').iterdir()),
                         ['1.json.gz', '2.json.gz', '3.json.gz'])
        restored = session.warp(nodes[1])
        self.assertEqual(restored.pending.name, 'dialogue')
        self.assertIn('Second scene', restored.pending.details['text'])
        self.assertIs(restored.engine.dt_view, view)                  # the tree is not part of a save
        self.assertIs(view.current, nodes[1])
        self.assertEqual((view.pending_result_index, view.awaiting_result), (0, False))
        self.assertEqual(len(list(view.nodes())), 3)
        # Playing on re-walks the existing nodes instead of adding any.
        answer_screen(restored)
        self.assertIn('Third scene', restored.pending.details['text'])
        self.assertEqual(len(list(view.nodes())), 3)
        self.assertIs(view.current, nodes[2])

    def test_a_warp_keeps_names_the_kept_properties_and_empties_the_wall(self):
        session = self.play_to('Third scene')
        engine = session.engine
        engine.character_names[3] = 'Renamed'
        engine.strings['$USR'] = 'Player'
        engine.numbers[engine.number_key(0, 0xbbc)] = 7
        engine.numbers[engine.number_key(0, 0xbda)] = 9
        engine.faceplace.incoming_message('hello', 3, 0)
        engine.faceplace.enabled = True
        restored = session.warp(engine.dt_view.root)
        self.assertEqual(restored.engine.character_names[3], 'Renamed')
        self.assertEqual(restored.engine.strings['$USR'], 'Player')
        self.assertEqual(restored.engine.numbers[engine.number_key(0, 0xbbc)], 7)
        self.assertEqual(restored.engine.numbers[engine.number_key(0, 0xbda)], 9)
        self.assertEqual(restored.engine.faceplace.messages, [])
        self.assertTrue(restored.engine.faceplace.enabled)

    def test_a_node_without_a_saved_game_cannot_be_warped_to(self):
        session = self.play_to('Second scene')
        stranger = DTNode(1203, '', 0, serial=99)
        self.assertFalse(session.has_tree_state(stranger))
        with self.assertRaises(SaveError):
            session.warp(stranger)

    def test_saved_games_outlive_the_session_and_ephemeral_sessions_write_none(self):
        session = self.play_to('Second scene')
        self.assertEqual(session.tree_serials(), {1, 2})
        again = Session(self.resources)
        self.assertEqual(again.tree_serials(), {1, 2})
        self.assertTrue(again.has_tree_state(session.engine.dt_view.root))
        quiet = Session(dialogue_story(self.temporary.name + '/quiet'), ephemeral=True)
        quiet.advance()
        self.assertEqual(quiet.tree_serials(), set())


class ZoomTests(unittest.TestCase):
    def panels(self):
        import pygame
        from exp_runtime.desktop_side_panels import SidePanels
        panels = object.__new__(SidePanels)
        panels.tree_rect, panels._origin, panels.tree_scale = pygame.Rect(0, 0, 424, 1440), (0, 0), 2.0
        panels.tree_sz_now, panels.tree_scroll, panels.tree_scroll_x = 50.0, 300.0, 40.0
        return panels

    def test_zooming_scales_the_tree_about_the_pointer(self):
        from exp_runtime.desktop_side_panels import BAR
        panels = self.panels()
        margin = panels.TREE_MARGIN
        point = (100, 400)                                                     # window pixels: 50 x 200 panel points
        tree_x = 50 + panels.tree_scroll_x                                     # the tree point under the pointer
        tree_y = 200 - BAR - margin + panels.tree_scroll
        panels.zoom_tree(-3, point)
        size = panels.tree_sz
        self.assertLess(size, 50.0)
        ratio = size / 50.0
        self.assertAlmostEqual(tree_x * ratio - panels.tree_scroll_x, 50)      # it is still where the pointer is
        self.assertAlmostEqual(tree_y * ratio - panels.tree_scroll, 200 - BAR - margin)
        self.assertFalse(panels.tree_follow)

    def test_zoom_is_limited_and_the_middle_button_fits_the_tree_again(self):
        panels = self.panels()
        panels.zoom_tree(200, (0, 0))
        self.assertEqual(panels.tree_sz, panels.ZOOM_RANGE[1])
        self.assertEqual(panels.ZOOM_RANGE, (10.0, 60.0))
        panels.tree_sz_now = panels.tree_sz
        panels.zoom_tree(-500, (0, 0))
        self.assertEqual(panels.tree_sz, panels.ZOOM_RANGE[0])
        panels.reset_tree_zoom()
        self.assertEqual((panels.tree_sz, panels.tree_follow), (None, True))


class SaveLinkTests(unittest.TestCase):
    """A game save names its current scene by serial and the scene is found in the tree the game already has (`SHSDTView loadGame:`)."""

    setUp = WarpTests.setUp
    play_to = WarpTests.play_to

    def test_a_save_holds_the_current_serial_not_the_tree_and_loading_links_it_to_the_live_tree(self):
        session = self.play_to('Second scene')
        state = session.snapshot()
        self.assertIsNone(state['engine']['dt_view']['root'])
        self.assertEqual(state['engine']['dt_view']['current_serial'], 2)
        restored = Session.from_snapshot(self.resources, state)
        view = restored.engine.dt_view
        self.assertIs(view.current, view.by_serial(2))                # in the tree, so it is highlighted and Rewind has a scene
        self.assertIs(view.real_parent(view.current), view.by_serial(1))
        self.assertTrue(view.current.path)

    def test_loading_an_older_save_keeps_the_scenes_found_since(self):
        session = self.play_to('Second scene')
        state = session.snapshot()
        answer_screen(session)                                          # the third scene is added to the library's tree
        self.assertIn('Third scene', session.pending.details['text'])
        restored = Session.from_snapshot(self.resources, state)
        self.assertEqual([node.serial for node in restored.engine.dt_view.nodes()], [1, 2, 3])
        self.assertEqual(restored.engine.dt_view.current.serial, 2)

    def test_a_warp_installs_the_scene_state_the_story_followed_gives_it(self):
        from exp_runtime.dt_state import STATE_IDS
        session = self.play_to('Third scene')
        view = session.engine.dt_view
        view.by_serial(2).deltas = [(-STATE_IDS[0], 44), (STATE_IDS[31], 2)]      # what the second scene changed
        view.accumulators.append(3038)
        restored = session.warp(view.by_serial(2))
        numbers, key = restored.engine.numbers, restored.engine.number_key
        self.assertEqual(numbers[key(0, STATE_IDS[0])], 44)                        # `installStateData`
        self.assertEqual(numbers[key(0, STATE_IDS[31])], 2)
        self.assertEqual(numbers[key(44, 3000)], 3012)                             # a derived display property (nobody is dated)
        self.assertEqual(restored.engine.dt_view.accumulators, [])

    def test_an_older_save_that_embeds_its_tree_is_linked_inside_that_tree(self):
        session = self.play_to('Second scene')
        state = session.snapshot()
        view = session.engine.dt_view
        state['version'] = 20
        state['engine']['dt_view'] = dict(asdict_of(view))               # the tree and its current scene, as saved before
        (Path(self.temporary.name) / 'dtview_tree.json').unlink()       # and a library that has no such tree
        restored = Session.from_snapshot(dialogue_story(self.temporary.name), state)
        embedded = restored.engine.dt_view
        self.assertEqual([node.serial for node in embedded.nodes()], [1, 2])
        self.assertIs(embedded.current, embedded.by_serial(2))


def asdict_of(view):
    from dataclasses import asdict
    return asdict(view)


class DesktopWarpTests(unittest.TestCase):
    def setUp(self):
        import os
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        import pygame
        self.pygame = pygame
        self.addCleanup(pygame.quit)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        from exp_runtime.desktop import Desktop
        session = Session(dialogue_story(self.temporary.name))
        session.advance()
        while 'Third scene' not in session.pending.details['text']:
            answer_screen(session)
        self.ui = Desktop(session, audio=False)
        self.ui.warp_unlocked = True
        self.ui.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
        self.ui.tick(1000)
        # The panels' art comes from the imported app, so the touch areas the drawn tree would leave are stood in.
        rect = self.pygame.Rect
        self.ui.side_panels.tree_targets = [(rect(0, 0, 100, 40), ('rewind',)), (rect(0, 500, 100, 40), ('forward',))]
        for index, node in enumerate(session.engine.dt_view.nodes()):
            self.ui.side_panels.tree_targets.append((rect(0, 60 + 40 * index, 30, 30), ('node', node)))

    def tap(self, command):
        rect = next(rect for rect, target in self.ui.side_panels.tree_targets if target[0] == command[0]
                    and (command[0] != 'node' or target[1] is command[1]))
        self.ui.handle_event(self.pygame.event.Event(self.pygame.MOUSEBUTTONUP, pos=rect.center, button=1))

    def text(self):
        return self.ui.session.pending.details['text']

    def test_tapping_a_node_warps_there_with_a_fade_and_the_panels_stay_open(self):
        view = self.ui.session.engine.dt_view
        self.assertEqual([target[0] for _rect, target in self.ui.side_panels.tree_targets].count('node'), 3)
        self.tap(('node', view.by_serial(1)))
        self.assertIn('First scene', self.text())
        self.assertTrue(self.ui.panels_open)
        self.assertTrue(self.ui.side_panels.tree_follow)                 # and the tree scrolls to the scene
        self.assertEqual(self.ui.fade['kind'], 6)
        self.assertIs(self.ui.session.engine.dt_view, view)

    def test_rewind_and_fast_forward_step_between_the_scenes_seen(self):
        self.tap(('rewind',))
        self.assertIn('Second scene', self.text())
        self.assertTrue(self.ui.panels_open)

    def test_a_drag_scrolls_the_tree_and_is_not_a_tap(self):
        pygame = self.pygame
        panels = self.ui.side_panels
        panels.tree_rect, panels.tree_scale, panels.tree_scroll, panels.tree_scroll_x = pygame.Rect(0, 0, 200, 700), 2.0, 100.0, 0.0
        node_rect = next(rect for rect, target in panels.tree_targets if target[0] == 'node')
        events = [pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=node_rect.center, button=1),
                  pygame.event.Event(pygame.MOUSEMOTION, pos=(node_rect.centerx + 20, node_rect.centery + 60), rel=(20, 60), buttons=(1, 0, 0)),
                  pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(node_rect.centerx + 20, node_rect.centery + 60), button=1)]
        for event in events:
            self.ui.handle_event(event)
        self.assertEqual((panels.tree_scroll, panels.tree_scroll_x), (70.0, -10.0))     # 60 and 20 pixels at 2 px a point
        self.assertFalse(panels.tree_follow)
        self.assertIn('Third scene', self.text())                       # nothing warped
        self.assertTrue(self.ui.panels_open)
        for event in (events[0], pygame.event.Event(pygame.MOUSEBUTTONUP, pos=node_rect.center, button=1)):
            self.ui.handle_event(event)                                 # a plain tap still warps
        self.assertIn('First scene', self.text())

    def test_only_scenes_on_the_followed_story_are_warp_targets(self):
        view = self.ui.session.engine.dt_view
        first = view.by_serial(1)
        first.active = False                                             # grayed: off the chain of last results
        self.tap(('node', first))
        self.assertIn('Third scene', self.text())                       # nothing happened
        first.active = True
        self.tap(('node', first))
        self.assertIn('First scene', self.text())

    def test_a_locked_feature_shows_its_notice_for_any_scene_touched(self):
        view = self.ui.session.engine.dt_view
        self.ui.warp_unlocked = False
        view.by_serial(1).active = False
        self.tap(('node', view.by_serial(1)))
        self.assertIn('Third scene', self.text())
        self.assertTrue(self.ui.message)                                 # string 271, even for a scene that is not a target

    def test_a_locked_feature_with_hd_resources_opens_the_native_notice_not_the_toast(self):
        """With an HD bundle's resource 17 available, the lock opens the native "Locked" window (menu 28,
        string 271) exactly the way a faceplace wall link opens "Exit Game?" (`test_faceplace_wall.py`'s
        `WallConfirmTests`), not the toast `_notice()` draws when no HD resources are available."""
        view = self.ui.session.engine.dt_view
        self.ui.warp_unlocked = False
        menus = [(1, NO, 0xff, ())] * 28 + [(1, 2, 0xff, (0,))]              # menu 28: title 1, message 2, one item
        actions = [(8, (0xff, 0xff), [(BACK, 0xffff)])]                     # a plain back step, like menu 17's "No"
        data = MenuEngineData(engine_data(menus, actions))
        self.ui.notice_data = data
        self.ui.notice_windows = HdMenuWindows(FakeLibrary(), data, None)
        self.ui.notice_stack = MenuStack(data, self.ui._wall_perform)
        self.tap(('node', view.by_serial(1)))
        self.assertEqual(self.ui.notice_stack.stack, [28])
        self.assertIn('Third scene', self.text())                          # nothing warped
        self.assertFalse(self.ui.message)                                  # not the bottom-bar toast
        # Modal like the pause menu: the game behind it (typing, clocks) waits for its button.
        held = repr(self.ui.session.snapshot())
        with patch.object(self.ui.session, 'tick', side_effect=AssertionError('the game ran behind the notice')):
            self.ui.tick(2000)
        self.assertEqual(repr(self.ui.session.snapshot()), held)

    def test_touches_are_ignored_while_locked_out_and_a_locked_feature_only_shows_its_notice(self):
        self.ui.warp_lockout = self.pygame.time.get_ticks() + 5000
        self.tap(('rewind',))
        self.assertIn('Third scene', self.text())
        self.ui.warp_lockout = 0
        self.ui.warp_unlocked = False
        self.tap(('rewind',))
        self.assertIn('Third scene', self.text())
        self.assertTrue(self.ui.panels_open)


if __name__ == '__main__':
    unittest.main()
