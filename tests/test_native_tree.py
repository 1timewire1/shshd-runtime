import unittest

from exp_runtime import native_tree
from exp_runtime.dtview_faceplace import DTView

DUMP = """N4 1210 x x|||Flirt with Beth|Slick||0 1 4 4203 302 0 0 0
N3 1216 4 x x|||What are you into?|Sports|||0 1 3 4203 197 0 0 0
N2 1206 3|||Meet Beth||20 1 2 4203 116 0 0 1 -3013=1
N1 1203 2|||Week 1||20 1 1 3202 163 0 0 0
"""


class NativeTreeTests(unittest.TestCase):
    def test_a_dump_is_read_and_written_back_exactly_and_passes_the_loaders_checks(self):
        nodes = native_tree.parse(DUMP)
        self.assertEqual(nodes[3].kids, [4, None, None])
        self.assertEqual((nodes[3].results, nodes[2].gates, nodes[2].ids), (['Sports', '', ''], ['-3013=1'], (4203, 116)))
        self.assertEqual(native_tree.format_nodes(nodes), DUMP)
        self.assertEqual(native_tree.check(nodes), [])
        with self.assertRaises(ValueError):
            native_tree.parse('N1 1203 2|||Week 1|20 1 9 3202 163 0 0 0\n')

    def test_the_checks_name_what_makes_the_app_refuse_a_file(self):
        nodes = native_tree.parse(DUMP)
        nodes[5] = native_tree.NativeNode(5, 1203, [None], '', [''], serial=5)             # a second root
        self.assertTrue(any('parentless' in problem for problem in native_tree.check(nodes)))
        nodes = native_tree.parse(DUMP)
        nodes[1].kids = [4]                                                                # a child that already has a parent
        self.assertTrue(any('N4' in problem for problem in native_tree.check(nodes)))
        nodes = native_tree.parse(DUMP)
        nodes[2].kids = [1]                                                                # a child listed after its parent
        self.assertTrue(any('N1' in problem for problem in native_tree.check(nodes)))

    def test_our_tree_becomes_a_loadable_one_with_real_scenes_keeping_their_serials(self):
        view = DTView()
        view.add_node(1203, 'Week 1', 20, uid=3202, script=162)
        view.add_node(1206, 'Meet Beth', 20, uid=4203, script=115)
        view.add_node(1216, 'What are you into?', 0, uid=4203, script=196)
        view.add_result(1, 'Girls')
        view.add_node(1210, 'Flirt with Girls', 0, uid=4203, script=400)
        view.add_result(0, 'Kiss')
        view.current = view.root                                                 # a second visit reaches the same scene again
        view.add_node(1203, 'Week 1', 20, uid=3202, script=162)
        made, report = native_tree.export(native_tree.parse(DUMP), view)
        self.assertEqual(native_tree.check(made), [])
        self.assertEqual((report['nodes'], report['matched'], report['new_scenes']), (4, 3, 1))
        self.assertEqual([made[line].serial for line in sorted(made)], [1, 2, 3, 5])         # the new scene follows serial 4
        self.assertEqual(made[3].kids, [None, 4, None])
        self.assertEqual((made[3].results, made[2].gates), (['', 'Girls', ''], ['-3013=1']))
        self.assertEqual(made[4].results, ['Kiss', ''])
        again = native_tree.parse(native_tree.format_nodes(made))
        self.assertEqual(native_tree.check(again), [])

    def test_a_scene_reached_twice_is_two_lines_with_one_serial(self):
        view = DTView()
        view.add_node(1220, 'Pick', 0, uid=1, script=1)          # a branch node: it can fork
        view.add_result(0, 'A')
        view.add_node(1203, 'Same', 0, uid=2, script=2)
        view.current = view.root
        view.add_result(1, 'B')
        view.add_node(1203, 'Same', 0, uid=2, script=2)                          # the same ids, another branch
        made, _ = native_tree.export({}, view)
        self.assertEqual(native_tree.check(made), [])
        self.assertEqual(len(made), 3)
        self.assertEqual(sorted(node.serial for node in made.values()), [1, 2, 2])
        self.assertEqual([kid for kid in made[1].kids if kid], [2, 3])


if __name__ == '__main__':
    unittest.main()
