"""Model-facing authoring workflows, rollback, diagnostics and real playback."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from exp_runtime.creator import Choice, Node, Project, ProjectError, save_project
from exp_runtime.creator.debugger import DebugSession
from exp_runtime.creator.diagnostics import diagnose
from exp_runtime.creator.graph import paths, search, subgraph
from exp_runtime.creator.media import audio_preview, inspect_asset, thumbnail
from exp_runtime.creator.playtest import Playtest, run_scenario
from exp_runtime.creator.schema import branching_example, node_schema
from exp_runtime.creator.workspace import Workspace
from test_creator import image_bytes, story


class CreatorAutomationTests(unittest.TestCase):
    def test_batch_preview_forward_references_rollback_stale_and_checkpoint_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            w = Workspace(directory)
            first = w.create('story.expproj')
            edits = branching_example()['operations']
            preview = w.batch('story.expproj', first['revision'], edits, preview=True)
            self.assertTrue(preview['validation']['valid'])
            self.assertFalse(preview['applied'])
            self.assertEqual(w.read('story.expproj')[1], first['revision'])
            self.assertEqual(w.checkpoints('story.expproj'), [])
            changed = w.batch('story.expproj', first['revision'], edits)
            self.assertNotIn('nodes', changed)
            self.assertEqual(set(changed['changed']['nodes']['added']), {'decision', 'reward'})
            bad = [dict(op='project', changes={'title': 'Must not persist'}), dict(op='node', id='oops', changes={'kind': 'bad'})]
            with self.assertRaises(ProjectError): w.batch('story.expproj', changed['revision'], bad)
            self.assertEqual(w.read('story.expproj')[1], changed['revision'])
            with self.assertRaisesRegex(ProjectError, 'changed'): w.batch('story.expproj', first['revision'], edits)
            # A fresh server can restore the original, retaining a redo copy.
            w = Workspace(directory)
            restored = w.restore('story.expproj', changed['revision'], changed['undo_checkpoint'])
            self.assertEqual(restored['revision'], first['revision'])
            self.assertEqual(len(w.checkpoints('story.expproj')), 2)

    def test_reference_safe_rename_delete_and_library_relocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'stories').mkdir()
            w = Workspace(root); first = w.create('stories/story.expproj')
            first = w.update('stories/story.expproj', first['revision'],
                             dict(locales={'fr': {'node.start.text': 'Bonjour'}}, library='assets/library'))
            changed = w.batch('stories/story.expproj', first['revision'], [dict(op='rename_node', id='start', new_id='arrival')])
            project, _ = w.read('stories/story.expproj')
            self.assertEqual(project.start, 'arrival')
            self.assertIn('node.arrival.text', project.locales['fr'])
            with self.assertRaisesRegex(ProjectError, 'referenced'):
                w.batch('stories/story.expproj', changed['revision'], [dict(op='node', id='end', remove=True)])
            w.restore('stories/story.expproj', changed['revision'], changed['undo_checkpoint'])
            self.assertEqual(w.read('stories/story.expproj')[0].library, str((root / 'assets/library').resolve()))

    def test_graph_queries_cycles_boundaries_search_and_paths(self):
        p = story()
        self.assertEqual(search(p, text='explor')['total'], 2)
        self.assertEqual(search(p, kind='choice')['nodes'][0]['id'], 'ask')
        single = subgraph(p, 'set', depth=0)
        self.assertEqual(len(single['nodes']), 1)
        self.assertEqual({e['source'] for e in single['boundary']}, {'ask', 'set'})
        self.assertIn(['ask', 'set', 'test', 'good'], paths(p, 'good')['paths'])
        p.node('bad').next = 'ask'
        self.assertLess(len(paths(p, 'end')['paths']), 20)
        self.assertTrue(subgraph(p, 'ask', depth=5, limit=1)['truncated'])

    def test_diagnostics_collect_multiple_nodes_fields_warnings_and_native_limits(self):
        p = story()
        p.node('ask').options[0].target = 'missing'
        p.node('good').text = '\U0001f642'
        p.node('set').params['expression'] = 'function()'
        p.nodes.append(Node('unused', 'end'))
        result = diagnose(p)
        self.assertFalse(result['valid'])
        issues = {(i['code'], i['node_id']) for i in result['issues']}
        self.assertTrue({('missing_target', 'ask'), ('text_encoding', 'good'), ('invalid_expression', 'set'),
                         ('unreachable_node', 'unused')} <= issues)
        self.assertTrue(all(i['suggestion'] for i in result['issues']))
        self.assertTrue(diagnose(Project())['valid'])

    def test_schemas_cover_kinds_and_examples(self):
        from exp_runtime.creator.model import KINDS
        self.assertEqual({r['kind'] for r in node_schema()['kinds']}, set(KINDS))
        for kind in KINDS:
            schema = node_schema(kind)
            self.assertEqual(schema['example']['kind'], kind)
            self.assertIn('params', schema['schema']['properties'])
        self.assertEqual(node_schema('grid')['games'], ['shs'])
        self.assertEqual(node_schema('end')['compatibility'], 'native_format')
        self.assertNotIn('episode_link', KINDS)

    def test_playtest_shuffled_choice_ids_real_timers_breakpoints_and_scenarios(self):
        p = story(); p.node('ask').params['shuffle'] = True
        d = DebugSession(p, seed=19); test = Playtest(d)
        state = test.run(until='choice')
        option = next(o for o in state['choices'] if o['id'] == 'ask:0')
        self.assertEqual(option['text'], 'Explore | together')
        state = test.choose('ask:0')
        self.assertEqual(state['variable_changes']['curiosity']['after'], 7)
        self.assertEqual(state['text'], 'We explored.')
        state = test.run(until='end')
        self.assertEqual(state['stop_reason'], 'end')
        timed_project = deepcopy(p); timed_project.node('ask').params['shuffle'] = False
        timed = Playtest(DebugSession(timed_project, seed=19)); timed.run(until='choice')
        self.assertEqual(timed.input('tick', milliseconds=901)['text'], 'We stayed.')
        timed_project.node('ask').timeout_ms = 100
        timed = Playtest(DebugSession(timed_project, seed=19)); timed.run(until='choice')
        expired = timed.choose('ask:0')
        self.assertEqual(expired['text'], 'We stayed.')  # Entrance can expire; don't answer the following panel.
        self.assertEqual(expired['action'], 'dialogue')
        breakpoint = Playtest(DebugSession(p, seed=19))
        state = breakpoint.run(until='node', node_id='ask')
        self.assertEqual(state['stop_reason'], 'breakpoint')
        self.assertEqual(breakpoint.run()['action'], 'choice')
        scenario = dict(seed=19, steps=[dict(action='run', until='choice'), dict(action='choose', option_id='ask:0'),
                                        dict(action='run', until='end')],
                        assertions=[dict(kind='variable', name='curiosity', equals=7), dict(kind='ended')])
        reports = [run_scenario(DebugSession(p, seed=19), scenario) for _ in range(2)]
        self.assertTrue(reports[0]['passed'], reports[0])
        self.assertEqual(reports[0], reports[1])
        scenario['assertions'][0]['equals'] = 8
        self.assertFalse(run_scenario(DebugSession(p, seed=19), scenario)['passed'])

    def test_playtest_keeps_unknown_service_pending_and_reports_argument_frame(self):
        from exp_runtime.creator.native import import_exp
        from exp_runtime.exp import Metadata, encode_exp
        from test_vm import program
        p = import_exp(encode_exp({1: Metadata(30000, 1, ('Probe',) * 5).to_bytes(), 25001: program((0x1a, 42), (0x1f, 0xfa01), 0x33).to_bytes()}))
        test = Playtest(DebugSession(p))
        result = test.run(until='end')
        self.assertEqual(result['stop_reason'], 'unsupported')
        self.assertEqual(result['pending_arguments'], [42])
        self.assertEqual(test.run(until='end')['pending_arguments'], [42])

    def test_image_metadata_and_bounded_audio_preview(self):
        data = image_bytes()
        self.assertEqual(inspect_asset(data)['width'], 32)
        png, info = thumbnail(data, size=32)
        self.assertEqual(info['height'], 32)
        self.assertTrue(png.startswith(b'\x89PNG'))
        raw = BytesIO()
        with wave.open(raw, 'wb') as wav:
            wav.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0' * 22050)
        self.assertEqual(inspect_asset(raw.getvalue())['duration_ms'], 1000)
        clip = audio_preview(raw.getvalue(), start_ms=100, duration_ms=200)
        with wave.open(BytesIO(clip)) as wav:
            self.assertAlmostEqual(wav.getnframes() / wav.getframerate(), .2, places=2)
        with self.assertRaises(ProjectError): audio_preview(raw.getvalue(), duration_ms=10001)

    def test_asset_catalog_reads_episode_metadata_scripts_and_colliding_ids_from_episode_bank(self):
        from exp_runtime.content import digest, import_game
        from exp_runtime.creator.catalog import library_assets, read_asset
        from test_content import FAKE_NATIVE, archive, make_apk, metadata
        from test_vm import program
        with tempfile.TemporaryDirectory() as directory, patch('exp_runtime.shs.content.NATIVE_SHA256', digest(FAKE_NATIVE)):
            root = Path(directory)
            script, image = program(0x33).to_bytes(), image_bytes()
            make_apk(root / 'source.apk', archive({1: metadata(), 42: image, 25001: script}))
            manifest = import_game(root / 'source.apk', [], root / 'library')
            episode = manifest['episodes'][0]['id']
            workspace = Workspace(root)
            self.assertEqual(read_asset(workspace, 'library', 42), b'base image')
            self.assertEqual(read_asset(workspace, 'library', 42, episode), image)
            scripts = library_assets(workspace, 'library', episode=episode, kind='script')
            self.assertEqual([a['id'] for a in scripts['assets']], [25001])
            self.assertIsNone(scripts['assets'][0]['name'])
            images = library_assets(workspace, 'library', episode=episode, kind='image')
            self.assertEqual(images['assets'][0]['width'], 32)
            self.assertIsNone(images['next_offset'])
