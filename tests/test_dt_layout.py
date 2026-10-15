import unittest

from exp_runtime.dt_layout import DEFAULT_SZ, JOIN, LabelText, Layout, Metrics
from exp_runtime.dtview_faceplace import DTNode, DTView

SZ = 50.0
EVENT, CHOICE3, CHOICE, BRANCH3, JOIN_TYPE = 1203, 1216, 1215, 1220, 1224


def layout(view, sz=SZ):
    return Layout(view.root, sz, Metrics(), view.current, view.last_was_result)


class PlacementTests(unittest.TestCase):
    def test_rows_are_two_sz_and_a_little_apart_and_events_add_their_width(self):
        view = DTView()
        view.add_node(EVENT, 'Week 1', 20, uid=1, script=1)             # exw 20: 0.2 of sz wider
        view.add_node(EVENT, 'Meet Beth', 0, uid=2, script=2)
        view.add_node(CHOICE3, 'Pick', 0, uid=3, script=3)
        nodes = layout(view).nodes()
        self.assertEqual([round(node.y, 3) for node in nodes], [0, round(2 * SZ + 0.2 * SZ + 8 * SZ / 35, 3),
                                                                 round(4 * SZ + 0.2 * SZ + 16 * SZ / 35, 3)])
        self.assertEqual({node.x for node in nodes}, {0.0})

    def test_children_of_two_three_four_and_five_exits_sit_at_the_apps_offsets(self):
        for node_type, exits, offsets in ((1210, 2, (-0.7, 0.7)), (CHOICE3, 3, (-0.7, 0.0, 0.7)),
                                          (1217, 4, (-0.45, -0.15, 0.15, 0.45)), (1218, 5, (-0.5, -0.25, 0.0, 0.25, 0.5))):
            with self.subTest(exits=exits):
                root = DTNode(node_type, 'Parent', 0, uid=1, script=1)
                root.children = {index: DTNode(EVENT, f'Child {index}', 0, uid=10 + index, script=10 + index)
                                 for index in range(exits)}
                lay = Layout(root, SZ, Metrics())
                self.assertEqual([round(kid.x / SZ, 3) for kid in lay.root.kids], list(offsets))
                rows = 2 * SZ + (24 if exits > 3 else 8) * SZ / 35              # a quiz is taller than the rest
                self.assertEqual({round(kid.y, 3) for kid in lay.root.kids}, {round(rows, 3)})

    def test_the_default_size_is_the_one_the_apps_screenshots_show(self):
        view = DTView()
        view.add_node(EVENT, 'Week 1', 20, uid=1, script=1)
        view.add_node(EVENT, 'Meet Beth', 20, uid=2, script=2)
        self.assertAlmostEqual(Layout(view.root, DEFAULT_SZ, Metrics()).nodes()[1].y, 128.0, delta=0.1)

    def test_a_fork_spaces_its_branches_by_how_wide_each_is_and_the_story_carries_on_where_they_meet(self):
        view = DTView()
        branch = view.add_node(BRANCH3, 'Whom?', 0, uid=1, script=1)
        view.add_result(0, 'Beth')
        view.add_node(EVENT, 'Beth scene', 0, uid=2, script=2)
        view.add_node(JOIN_TYPE, '', 0, uid=9, script=9)
        view.current = branch
        view.add_result(2, 'Nobody')
        view.add_node(EVENT, 'Nobody scene', 0, uid=3, script=3)
        view.add_node(JOIN_TYPE, '', 0, uid=9, script=9)                # the same join reached by the other branch
        view.add_node(EVENT, 'After', 0, uid=4, script=4)                # carries on from the first join
        lay = layout(view)
        left, middle, right = lay.root.kids
        self.assertIsNone(middle)
        self.assertLessEqual(left.x, -0.7 * SZ)
        self.assertGreaterEqual(right.x, 0.7 * SZ)
        self.assertLess(left.x, 0.0)
        after = next(node for node in lay.nodes() if node.src.lower_label == 'After')
        joins = [node for node in lay.nodes() if node.type == JOIN]
        self.assertEqual([join.count for join in joins], [2, 2])
        self.assertAlmostEqual(after.x, 0.0)                              # back on the main lane
        self.assertGreater(after.y, max(join.y for join in joins))

    def test_a_wide_exit_label_inside_one_branch_pushes_the_next_branch_away(self):
        def right_branch(label):
            view = DTView()
            branch = view.add_node(BRANCH3, 'Whom?', 0, uid=1, script=1)
            view.add_result(0, 'Left')
            choice = view.add_node(CHOICE, 'Pick', 0, uid=2, script=2)
            view.add_result(0, label)
            view.add_node(EVENT, 'Under', 0, uid=4, script=4)
            view.current = branch
            view.add_result(2, 'Right')
            view.add_node(EVENT, 'Right', 0, uid=3, script=3)
            self.assertIsNotNone(choice)
            return layout(view).root.kids[2].x
        self.assertGreater(right_branch('A very long exit label indeed'), right_branch('A'))


class LabelTests(unittest.TestCase):
    def test_a_label_over_55_units_breaks_at_the_space_nearest_its_middle(self):
        metrics = Metrics()
        self.assertEqual(LabelText('Week 1', 'outer', metrics).lines, ['Week 1'])
        self.assertEqual(LabelText('What are you into?', 'outer', metrics).lines, ['What are', 'you into?'])
        self.assertEqual(LabelText('Unbreakable' * 6, 'outer', metrics).lines, ['Unbreakable' * 6])
        two = LabelText('Flirt with Beth', 'outer', metrics)
        self.assertEqual(two.lines, ['Flirt', 'with Beth'])
        self.assertAlmostEqual(two.block_width(35.0), max(metrics.length(line, 'outer') for line in two.lines))
        self.assertAlmostEqual(two.text_height(70.0), 2 * metrics.line_height('outer') * 2)


class DrawingTests(unittest.TestCase):
    def tree(self):
        view = DTView()
        view.add_node(EVENT, 'Week 1', 20, uid=1, script=1)
        view.add_node(CHOICE3, 'Pick', 0, uid=2, script=2)
        view.add_result(1, 'B')
        view.add_node(EVENT, 'Next', 0, uid=3, script=3)
        return view

    @staticmethod
    def styles(ops):
        return [(op[2], round(op[3], 3)) for op in ops if op[0] == 'path']

    def test_yellow_along_the_path_to_the_current_scene_and_black_after_it(self):
        view = self.tree()
        view.current = view.root.children[0]                                   # at 'Pick', arrived but not yet answered
        view.last_was_result = False
        view.sweep_forward(view.root)
        ops = layout(view).draw_ops()
        yellow, black, gray = (255, 255, 0), (0, 0, 0), (128, 128, 128)
        paths = [op for op in ops if op[0] == 'path']
        # Week 1 to Pick (the path), Pick's three stubs (only the answered one, to 'Next', is followed), Next's own stub.
        self.assertEqual([op[2] for op in paths], [yellow, gray, black, gray, gray])
        self.assertEqual(paths[0][3], 4 * SZ / 30)                                  # the path is thick
        self.assertEqual(paths[2][3], SZ / 30)
        # Arrived at Pick: its outline is thick yellow, the others' black.
        outlines = [(op[0], op[-2]) for op in ops if op[0] in ('rect', 'polygon')]
        self.assertEqual(outlines, [('rect', black), ('polygon', yellow), ('rect', black)])

    def test_the_result_just_taken_is_the_yellow_stub_until_the_next_scene_exists(self):
        view = DTView()
        view.add_node(CHOICE3, 'Pick', 0, uid=1, script=1)
        view.add_result(2, 'TV')
        lay = layout(view)
        paths = [op for op in lay.draw_ops() if op[0] == 'path']
        self.assertEqual([op[2] for op in paths], [(128, 128, 128), (128, 128, 128), (255, 255, 0)])
        self.assertEqual([op[-2] for op in lay.draw_ops() if op[0] == 'polygon'], [(0, 0, 0)])   # answered: no yellow outline

    def test_stubs_leave_a_diamond_by_its_lower_edges(self):
        view = DTView()
        view.add_node(CHOICE3, 'Pick', 0, uid=1, script=1)
        paths = [op for op in layout(view).draw_ops() if op[0] == 'path']
        top = SZ + 0.25 * SZ
        self.assertEqual([[(round(x, 2), round(y, 2)) for x, y in op[1]] for op in paths],
                         [[(0.0, top), (-0.7 * SZ, top + 0.7 * SZ)], [(0.0, top), (0.0, top + SZ)],
                          [(0.0, top), (0.7 * SZ, top + 0.7 * SZ)]])

    def test_labels_show_from_sz_20_and_exit_labels_from_sz_32(self):
        view = DTView()
        view.add_node(CHOICE3, 'Pick', 0, uid=1, script=1)
        view.add_result(0, 'Sports')
        def kinds(sz):
            return sorted({op[2] for op in layout(view, sz).draw_ops() if op[0] == 'text'})
        self.assertEqual(kinds(50.0), ['exit', 'outer'])
        self.assertEqual(kinds(25.0), ['outer'])
        self.assertEqual(kinds(15.0), [])

    def test_an_exit_label_sits_right_aligned_left_of_its_stub_with_a_white_box_behind_it(self):
        view = DTView()
        view.add_node(1210, 'Flirt', 0, uid=1, script=1)                        # two exits
        view.add_result(0, 'Slick')
        ops = layout(view).draw_ops()
        fill = next(op for op in ops if op[0] == 'fill')
        text = next(op for op in ops if op[0] == 'text' and op[2] == 'exit')
        edge = -(0.2 + 5 / 35) * SZ                                             # the label's right edge
        self.assertAlmostEqual(fill[1] + fill[3], edge)
        self.assertEqual(fill[-1], (255, 255, 255))
        self.assertEqual(text[1], ['Slick'])

    def test_only_the_scenes_with_an_icon_can_be_touched(self):
        view = self.tree()
        lay = layout(view)
        size = lambda image: (126, 113)
        top = lay.root
        self.assertIs(lay.find_touched(top.x + 30, top.y + SZ, size), top)
        self.assertIsNone(lay.find_touched(top.x + 500, top.y + SZ, size))
        self.assertIsNone(lay.find_touched(top.x, top.y - 50, size))


class FlagTests(unittest.TestCase):
    def test_the_sweep_follows_each_scenes_last_result_and_marks_the_way_to_the_current_scene(self):
        view = DTView()
        root = view.add_node(BRANCH3, 'Pick', 0, uid=1, script=1)   # a branch node keeps every branch
        view.add_result(0, 'A')
        first = view.add_node(EVENT, 'A scene', 0, uid=2, script=2)
        view.current = root
        view.add_result(2, 'C')
        other = view.add_node(EVENT, 'C scene', 0, uid=3, script=3)
        view.current = root
        view.add_result(0, 'A')                                                 # the last answer leads to A
        self.assertEqual((root.active, root.path, first.active, first.path, other.active), (True, True, True, False, False))
        view.current = first
        view.sweep_forward(view.root)
        self.assertEqual((root.path, first.path), (True, True))                # the way to the current scene, and it
        view.current = root
        view.add_result(2, 'C')                                                 # now the last answer leads to C
        self.assertEqual((first.active, other.active, other.path), (False, True, False))

    def test_a_join_that_repeats_ids_carries_the_chain_on_from_the_first_one(self):
        view = DTView()
        branch = view.add_node(BRANCH3, 'B', 0, uid=1, script=1)
        view.add_result(0, 'x')
        view.add_node(JOIN_TYPE, '', 0, uid=9, script=9)
        first_join = view.current
        view.add_node(EVENT, 'After', 0, uid=4, script=4)
        after = view.current
        view.current = branch
        view.add_result(2, 'z')
        view.add_node(JOIN_TYPE, '', 0, uid=9, script=9)
        duplicate = view.current
        view.sweep_forward(view.root)
        self.assertFalse(duplicate.primary)
        self.assertEqual((duplicate.active, after.active, first_join.active), (True, True, False))

    def test_a_repeated_join_is_never_the_one_the_story_carries_on_from_even_if_the_walk_meets_it_first(self):
        view = DTView()
        branch = view.add_node(BRANCH3, 'B', 0, uid=1, script=1)
        view.add_result(2, 'z')                                                 # the first branch to reach the join owns it
        view.add_node(JOIN_TYPE, '', 0, uid=9, script=9)
        owner = view.current
        view.current = branch
        view.add_result(0, 'x')                                                 # (slot 0 comes first in a walk of the tree)
        view.add_node(JOIN_TYPE, '', 0, uid=9, script=9)
        duplicate = view.current
        view.add_node(EVENT, 'After', 0, uid=4, script=4)
        self.assertTrue(owner.primary and not duplicate.primary)
        self.assertIs(view.find(9, 9), owner)
        self.assertEqual((sorted(owner.children), duplicate.children), ([0], {}))


if __name__ == '__main__':
    unittest.main()
