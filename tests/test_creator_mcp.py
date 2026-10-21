"""Exercise the actual MCP stdio transport and filesystem edit boundaries."""
import asyncio
from importlib.util import find_spec
import json
from pathlib import Path
import sys
import tempfile
import unittest

from exp_runtime.creator.workspace import Workspace
from exp_runtime.creator import ProjectError


class CreatorWorkspaceTests(unittest.TestCase):
    def test_revisions_invalid_edits_and_export_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            w = Workspace(directory)
            first = w.create('story.expproj')
            with self.assertRaises(ProjectError): w.path('../escape.expproj')
            second = w.update('story.expproj', first['revision'], {'title': 'Changed'})
            with self.assertRaisesRegex(ProjectError, 'changed'):
                w.update('story.expproj', first['revision'], {'title': 'Stale'})
            with self.assertRaises(ProjectError):
                w.node('story.expproj', second['revision'], 'start', {'kind': 'unknown'})
            self.assertEqual(w.describe('story.expproj')['revision'], second['revision'])
            result = w.export('story.expproj', 'story.exp', second['revision'])
            with self.assertRaisesRegex(ProjectError, 'Export exists'):
                w.export('story.expproj', 'story.exp', second['revision'])
            self.assertEqual(w.export('story.expproj', 'story.exp', second['revision'],
                                      replace_revision=result['sha256']), result)
            changed = w.update('story.expproj', second['revision'], {'library': 'libraries/shs'})
            self.assertEqual(Path(changed['library']), (Path(directory) / 'libraries/shs').resolve())
            with tempfile.TemporaryDirectory() as outside:
                try: (Path(directory) / 'link').symlink_to(outside, target_is_directory=True)
                except OSError: return  # Windows can disallow unprivileged symlink creation.
                with self.assertRaises(ProjectError): w.path('link/escape.expproj')


@unittest.skipUnless(find_spec('mcp'), 'Install the creator-mcp extra for MCP transport checks')
class CreatorMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_tools_resources_edit_export_debug_and_shutdown(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with tempfile.TemporaryDirectory() as directory:
            async def check():
                params = StdioServerParameters(command=sys.executable,
                    args=['-m', 'exp_runtime.creator.mcp_server', '--workspace', directory])
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as client:
                        info = await client.initialize()
                        self.assertEqual(info.serverInfo.name, 'EXP Runtime Creator')
                        tools = await client.list_tools()
                        self.assertIn('project_export_exp', {tool.name for tool in tools.tools})
                        for tool in tools.tools:
                            self.assertRegex(tool.name, r'^[a-z]+(?:_[a-z]+)+$')
                            self.assertLess(len(tool.description.encode()), 1000)
                            self.assertLess(len(json.dumps(tool.inputSchema).encode()), 5000)
                            self.assertIsNotNone(tool.annotations.readOnlyHint)
                            self.assertIsNotNone(tool.annotations.destructiveHint)
                            self.assertFalse(tool.annotations.openWorldHint)
                        schema = await client.read_resource('creator://schema')
                        self.assertIn('football', schema.contents[0].text)
                        async def call(name, **arguments):
                            result = await client.call_tool(name, arguments)
                            self.assertFalse(result.isError, result.content)
                            data = json.loads(result.content[0].text)
                            self.assertEqual(data, result.structuredContent)
                            return data
                        created = await call('project_create', path='story.expproj', game='cod')
                        edited = await call('graph_edit_node', path='story.expproj', revision=created['revision'],
                                            node_id='start', changes={'text': 'Created through MCP.'})
                        exported = await call('project_export_exp', path='story.expproj', destination='story.exp',
                                              revision=edited['revision'])
                        self.assertGreater(exported['bytes'], 100)
                        debug = await call('playtest_start', path='story.expproj')
                        result = await call('playtest_debug_step', session=debug['session'], step_node=False)
                        self.assertEqual(result['details']['text'], 'Created through MCP.')
                        await call('playtest_close', session=debug['session'])
                        example = await call('schema_get', example=True)
                        preview = await call('project_preview_edits', path='story.expproj', revision=edited['revision'],
                                             operations=example['operations'])
                        self.assertTrue(preview['validation']['valid'])
                        self.assertFalse(preview['applied'])
                        applied = await call('project_apply_edits', path='story.expproj', revision=edited['revision'],
                                             operations=example['operations'])
                        report = await call('playtest_run_scenario', path='story.expproj', scenario=example['scenario'])
                        self.assertTrue(report['passed'], report)
                        saved = await call('playtest_save_scenario', destination='branch.exptest', scenario=example['scenario'])
                        scenario = await call('playtest_get_scenario', path='branch.exptest')
                        self.assertEqual(scenario['scenario'], example['scenario'])
                        self.assertEqual(saved['revision'], scenario['revision'])
                        replay = await call('playtest_replay_scenario', path='story.expproj', scenario_path='branch.exptest')
                        self.assertEqual(replay, report)
                        protected = await client.call_tool('playtest_save_scenario',
                            dict(destination='branch.exptest', scenario=example['scenario']))
                        self.assertTrue(protected.isError)
                        await call('playtest_save_scenario', destination='branch.exptest', scenario=example['scenario'],
                                   replace_revision=saved['revision'])
                        invalid = await client.call_tool('playtest_save_scenario',
                            dict(destination='invalid.exptest', scenario=dict(seed=-1, steps=[])))
                        self.assertTrue(invalid.isError)
                        self.assertFalse((Path(directory) / 'invalid.exptest').exists())
                        stale = await client.call_tool('project_update', dict(path='story.expproj', revision=edited['revision'], changes={'title': 'old'}))
                        self.assertTrue(stale.isError)
                        self.assertEqual(json.loads(stale.content[0].text), stale.structuredContent)
                        self.assertEqual(stale.structuredContent['error']['code'], 'stale_revision')
                        # Oversized output remains fully retrievable, with its revision available immediately.
                        applied = await call('graph_edit_node', path='story.expproj', revision=applied['revision'],
                                             node_id='start', changes={'text': 'A' * 24000})
                        full = await call('graph_get_subgraph', path='story.expproj', node_id='start', depth=0)
                        self.assertTrue(full['truncated'])
                        self.assertEqual(full['revision'], applied['revision'])
                        pieces, offset = [], 0
                        while offset is not None:
                            piece = await call('result_read', result_id=full['result_id'], offset=offset)
                            pieces.append(piece['text']); offset = piece['next_offset']
                        self.assertEqual(json.loads(''.join(pieces))['nodes'][0]['text'], 'A' * 24000)
                        # Native candidate pages use the same object/result contract.
                        from exp_runtime.creator.compiler import _Assembler
                        from exp_runtime.exp import Metadata, encode_exp
                        assembler = _Assembler(); address = assembler.text('Native dialogue.'); assembler.emit(0x33)
                        (Path(directory) / 'native.exp').write_bytes(encode_exp({
                            1: Metadata(30000, 1, ('Native',) * 5).to_bytes(), 25001: assembler.finish()}))
                        await call('project_import_exp', source='native.exp', destination='native.expproj')
                        candidates = await call('native_find_text', path='native.expproj', script=25001, query='dialogue', limit=1)
                        self.assertEqual(candidates['candidates'][0]['address'], address)
                        self.assertEqual(candidates['total'], 1)
                        # Media remains an MCP image block, not a giant JSON/base64 string.
                        from test_creator import image_bytes
                        (Path(directory) / 'portrait.png').write_bytes(image_bytes())
                        await call('asset_import_image', path='story.expproj', revision=applied['revision'], source='portrait.png')
                        assets = await call('asset_list_project', path='story.expproj')
                        preview = await client.call_tool('asset_preview_image',
                            dict(path='story.expproj', resource=assets['assets'][0]['id'], size=32))
                        self.assertFalse(preview.isError, preview.content)
                        self.assertEqual(json.loads(preview.content[0].text), preview.structuredContent)
                        self.assertEqual(preview.content[1].type, 'image')
                        self.assertEqual(preview.content[1].mimeType, 'image/png')
                        bad = await client.call_tool('project_create', {'path': '../escape.expproj'})
                        self.assertTrue(bad.isError)
            await asyncio.wait_for(check(), 30)
