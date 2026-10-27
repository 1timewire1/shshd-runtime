"""The creator's coverage of the host services real SHS, SHS HD and CoD episodes call."""
import json
import os
from pathlib import Path
import unittest
import zipfile

from exp_runtime.creator import Asset, Character, Choice, Node, Project, compile_project
from exp_runtime.creator.coverage import CORPUS, STATUS, summary
from exp_runtime.exp import ExpArchive

# Services the creator cannot express yet. Moving one out of this set means its STATUS entry must be updated too, and
# a service that newly stops being expressible fails here.
PENDING = set()


def services(data):
    """Every service number called by the archive's scripts."""
    found = set()
    for program in ExpArchive(data).programs().values():
        for ins in program.instructions:
            if ins.opcode == 0x1f:
                found.add(ins.operand >> 8)
            elif ins.opcode == 0x1e:
                found.add(ins.operand)
    return found


def fixture(kind):
    """A small valid story that uses `kind`; nodes are chained in order and end the episode."""
    project = Project(title='Coverage', characters=[Character('alex', 'Alex', 100)], assets=[Asset(100, 'Base art')])
    nodes = {
        'choice': [Node('n', 'choice', text='Pick', options=[Choice('A', 'end'), Choice('B', 'end')])],
        'end': [Node('n', text='Bye')],
        'scene': [Node('n', text='One'), Node('m', text='Two', scene=25002)],
        'background': [Node('n', 'background', asset=100)],
        'dialogue': [Node('n', 'set', variable='points', value=1), Node('m', character='alex', text='Hi {points}'),
                     Node('o', speaker='Sam', text='Hey')],
        'branch': [Node('n', 'branch', params={'expression': "prop('alex', 1) + bit(0, 1, 2) + art('alex') + build(9)"},
                        otherwise='end')],
        'expression_default': [Node('n', 'expression_default', character='alex', expression=1)],
        'character_art': [Node('n', 'character_art', character='alex', asset=100)],
        'character_name': [Node('n', 'character_name', character='alex', text='Al')],
        'picker': [Node('n', 'picker', text='Pick', character='alex', params={'characters': ['alex']})],
        'speakers': [Node('n', 'speakers', params={'player': 'alex'})],
        'football': [Node('n', 'football', params={'home_result': 'home'})],
        'open_url': [Node('n', 'open_url', params={'url': 'https://example.com'})],
        'faceplace': [Node(f'n{i}', 'faceplace', text='John', params={'action': action})
                      for i, action in enumerate(('enable', 'default_name', 'name_chosen', 'face_chosen', 'clear'))],
        'tree': [Node('n', 'tree'), Node('m', 'tree', params={'action': 'clear_accumulator', 'id': 3038}),
                 Node('o', 'tree', params={'action': 'join'})],
        'tree_node': [Node('n', 'tree_node', text='Meet'), Node('m', 'tree_node', text='Wide', params={'width': 20}),
                      Node('o', 'tree_node', text='Auto', params={'type': 1221, 'condition': 0x4b}),
                      Node('p', 'tree_result')],
        'tree_result': [Node('n', 'tree_node', text='Pick', params={'type': 1215}), Node('m', 'tree_result', text='Yes'),
                        Node('o', 'tree_node', text='Again', params={'type': 1215}), Node('p', 'tree_result')],
        'text_branch': [Node('n', 'text_branch', otherwise='end')],
        'input': [Node('n', 'input')],
        'relationship': [Node('n', 'relationship', character='alex', params={'romantic': True})],
        'word_game': [Node('n', 'word_game', text='Go')],
    }.get(kind, [Node('n', kind, text='Text')])
    nodes.append(Node('end', 'end'))
    for node, following in zip(nodes, nodes[1:]):
        if node.kind != 'choice' and not node.next:
            node.next = following.id
    project.nodes, project.start = nodes, nodes[0].id
    return project


class CreatorCoverageTests(unittest.TestCase):
    def test_every_corpus_service_is_classified(self):
        self.assertEqual(set(STATUS), set(CORPUS))
        for service, coverage in STATUS.items():
            self.assertIn(coverage.status, ('emits', 'equivalent', 'no_op', 'pending'), service)
            self.assertTrue(coverage.detail, service)
        self.assertEqual(len(summary()), len(CORPUS))

    def test_pending_services_are_the_known_gaps(self):
        self.assertEqual({s for s, c in STATUS.items() if c.status == 'pending'}, PENDING)

    def test_emitting_kinds_really_compile_to_their_services(self):
        for service, coverage in STATUS.items():
            if coverage.status != 'emits':
                continue
            for kind in coverage.detail:
                with self.subTest(service=service, kind=kind):
                    self.assertIn(service, services(compile_project(fixture(kind))))

    def test_the_native_harness_probes_every_emitted_service(self):
        # tools/test_creator_native.py runs these probes in the original binaries; a service the creator emits but no
        # probe calls would never reach them. CoD's probes cover every service a CoD-capable kind emits.
        import importlib.util
        from exp_runtime.creator.schema import SHS_ONLY
        path = Path(__file__).resolve().parents[1] / 'tools' / 'test_creator_native.py'
        spec = importlib.util.spec_from_file_location('creator_native_probes', path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        for game in ('shs', 'cod'):
            probed = set().union(*(services(compile_project(project)) for project, _ in harness.probes(game)))
            wanted = {service for service, coverage in STATUS.items() if coverage.status == 'emits'
                      and (game == 'shs' or set(coverage.detail) - SHS_ONLY)}
            with self.subTest(game=game):
                self.assertEqual(wanted - probed, set())

    @unittest.skipUnless(os.environ.get('SHSHD_COVERAGE_LIBRARIES'),
                         'set SHSHD_COVERAGE_LIBRARIES to imported library folders to rescan real episodes')
    def test_local_libraries_call_no_unclassified_service(self):
        found = set()
        for folder in os.environ['SHSHD_COVERAGE_LIBRARIES'].split(os.pathsep):
            directory = Path(folder)
            manifest = json.loads((directory / 'library.json').read_text(encoding='utf-8'))
            for record in manifest['episodes']:
                if 'file' in record:
                    found |= services((directory / record['file']).read_bytes())
                else:
                    package = manifest.get('apk') or manifest.get('ipa')
                    with zipfile.ZipFile(directory / package['file']) as archive:
                        member = record.get('apk_member') or record.get('ipa_member')
                        found |= services(archive.read(member))
        self.assertEqual(found - set(STATUS), set())


if __name__ == '__main__':
    unittest.main()
