"""Optional stdio MCP interface to the creator's model, compiler and debugger."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Literal

from .editing import auto_layout
from .model import ProjectError, atomic_write
from .workspace import Workspace


def create_server(root):
    # Keep MCP, Qt, and player dependencies out of headless creator imports.
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    workspace = Workspace(root)
    server = FastMCP('SHSHD Runtime Creator', instructions=(
        'Author SHS/CoD EXP episodes in this workspace. Use schema_get for node contracts. '
        'Use project_get revisions with project_apply_edits; project_preview_edits is read-only. '
        'Validate, playtest, then export. Unknown native calls remain explicit stops. '
        'Open desktop projects share unsaved state; edits enter desktop undo and need Save. '
        'Paths stay in the workspace. Large results include a result_read handle.'))
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
    edit = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

    from .mcp_results import register
    from .mcp_types import Edit, Scenario
    from .schema import node_schema, branching_example
    from . import graph
    read_tool, write_tool, edit_tool = (register(server, workspace, a) for a in (read, write, edit))

    @server.resource('creator://schema')
    def schema() -> str:
        """Discover node kinds, languages and the authoring workflow."""
        return json.dumps(node_schema())

    @server.resource('creator://schema/{kind}')
    def kind_schema(kind: str) -> str:
        """One node kind's contract, defaults and example."""
        return json.dumps(node_schema(kind))

    @server.resource('creator://examples/branching')
    def example() -> str:
        """An authored branching edit and executable playtest scenario."""
        return json.dumps(branching_example())

    @read_tool(name='project_list')
    def list_projects(query: str = '', offset: int = 0, limit: int = 50) -> dict:
        """Find .expproj files by workspace-relative filename. Offset >=0; limit 1–200, default 50."""
        graph.page(offset, limit)
        paths = sorted(str(path.relative_to(workspace.root)) for path in workspace.root.rglob('*.expproj')
            if path.resolve().is_relative_to(workspace.root) and '.creator-history' not in path.parts
            and query.casefold() in str(path.relative_to(workspace.root)).casefold())
        return dict(projects=paths[offset:offset + limit], total=len(paths),
                    next_offset=offset + limit if offset + limit < len(paths) else None)

    @read_tool(name='project_get')
    def read_project(path: str, view: Literal['summary', 'full'] = 'summary', offset: int = 0, limit: int = 50) -> dict:
        """Inspect saved or live desktop state and its revision. live/unsaved identify an open document. Full includes node pages (offset >=0, limit 1–200)."""
        if view == 'full': return workspace.describe(path, offset, limit)
        state = workspace.snapshot(path)
        return dict(revision=state.revision, live=state.live, unsaved=state.unsaved, **graph.overview(state.project))

    @write_tool(name='project_create')
    def create_project(path: str, title: str = 'Untitled episode', game: str = 'shs',
                       pack_id: int = 30000, episode_id: int = 1) -> dict:
        """Create a project at a new .expproj path. Existing files are never replaced."""
        return workspace.create(path, title, game, pack_id, episode_id)

    @edit_tool(name='project_update')
    def update_project(path: str, revision: str, changes: dict) -> dict:
        """Change title/game/IDs/start/language/locales/library. Use project_get's revision."""
        return workspace.update(path, revision, changes)

    @edit_tool(name='graph_edit_node')
    def edit_node(path: str, revision: str, node_id: str, changes: dict | None = None, remove: bool = False) -> dict:
        """Add/update/remove a node. Options are text/target/condition objects. See creator://schema."""
        return workspace.node(path, revision, node_id, changes, remove)

    @edit_tool(name='character_edit')
    def edit_character(path: str, revision: str, character_id: str,
                       changes: dict | None = None, remove: bool = False) -> dict:
        """Edit reusable name, portrait, theme and five expression asset IDs."""
        return workspace.character(path, revision, character_id, changes, remove)

    @edit_tool(name='graph_arrange')
    def arrange_graph(path: str, revision: str) -> dict:
        """Arrange connected nodes in columns; preserve all execution connections."""
        return workspace.edit(path, revision, auto_layout)

    @edit_tool(name='asset_import_image')
    def add_image(path: str, revision: str, source: str) -> dict:
        """Embed a local PNG/JPEG from this workspace in the project."""
        return workspace.import_image(path, revision, source)

    @edit_tool(name='asset_import_audio')
    def add_audio(path: str, revision: str, source: str) -> dict:
        """Embed a local MP3 (music or a sound effect) or WAV (a sound effect) from this workspace in the project."""
        return workspace.import_audio(path, revision, source)

    @read_tool(name='asset_list')
    def library_assets(library: str, episode: str | None = None, kind: str | None = None,
                       query: str = '', offset: int = 0, limit: int = 50) -> dict:
        """Browse supplied resources with type, dimensions and audio duration. Offset >=0; limit 1–200. Numeric IDs are not invented names."""
        from .catalog import library_assets
        return library_assets(workspace, library, episode=episode, kind=kind, query=query, offset=offset, limit=limit)

    @edit_tool(name='asset_import_library_image')
    def add_library_image(path: str, revision: str, library: str,
                          resource: int, episode: str | None = None) -> dict:
        """Reference a game's base image, or embed an image from an imported episode."""
        return workspace.library_image(path, revision, library, resource, episode)

    @write_tool(name='project_import_exp')
    def import_exp(source: str, destination: str, game: str = 'shs') -> dict:
        """Recover an authored graph or import lossless native blocks into a new project."""
        return workspace.import_episode(source, destination, game)

    @read_tool(name='native_get_data')
    def native_data(path: str, script: int) -> dict:
        """Read the fixed native data banks of an imported original script."""
        from .native import _resources
        from exp_runtime.decode.bytecode import decode_program
        project, revision = workspace.read(path)
        if not project.native: raise ProjectError('This is an authored high-level graph')
        program = decode_program(_resources(project)[script])
        return {'revision': revision, 'main': list(program.main_words), 'extra': list(program.extra_words),
                'gap_count': program.gap_count}

    @read_tool(name='native_find_text')
    def native_text(path: str, script: int, query: str = '', offset: int = 0, limit: int = 50) -> dict:
        """Find printable main-bank text candidates; verify their addresses in the instructions. Offset >=0; limit 1–200, default 50."""
        from .native import packed_strings
        graph.page(offset, limit)
        project, revision = workspace.read(path)
        candidates = [row for row in packed_strings(project, script) if query.casefold() in row['text'].casefold()]
        return dict(revision=revision, candidates=candidates[offset:offset + limit], total=len(candidates),
                    next_offset=offset + limit if offset + limit < len(candidates) else None)

    @edit_tool(name='native_update_text')
    def edit_native_text(path: str, revision: str, script: int, address: int, text: str) -> dict:
        """Replace a confirmed packed string within its original allocation; preserve every address."""
        from .native import edit_packed_text
        return workspace.edit(path, revision, lambda project: edit_packed_text(project, script, address, text))

    @edit_tool(name='native_update_data')
    def edit_native_data(path: str, revision: str, script: int, words: list[int], extra: bool = False) -> dict:
        """Replace a native data bank without changing its length or any addresses."""
        from .native import set_data_words
        return workspace.edit(path, revision, lambda project: set_data_words(project, script, words, extra=extra))

    @read_tool(name='project_validate')
    def validate_project(path: str) -> dict:
        """Find export errors and graph warnings with node/field locations and recovery suggestions; writes nothing."""
        from .diagnostics import diagnose
        project, revision = workspace.read(path)
        return dict(revision=revision, **diagnose(project))

    @edit_tool(name='project_export_exp')
    def export_exp(path: str, destination: str, revision: str, language: str | None = None,
                   replace_revision: str | None = None) -> dict:
        """Export native EXP atomically. Replacing an EXP requires its current SHA-256."""
        return workspace.export(path, destination, revision, language, replace_revision)

    @write_tool(name='playtest_start')
    def debug_start(path: str, start: str | None = None, seed: int | None = None,
                    library: str | None = None, language: Literal['en', 'fr', 'it', 'de', 'es'] | None = None) -> dict:
        """Start isolated playback, paused at the first node. Optional seed 0–4294967295; imported library enables accurate layout/screenshots. Limit 8 sessions."""
        result = workspace.start_debug(path, start, seed=seed, library=library, language=language)
        return dict(session=result['session'], revision=result['revision'], **workspace.playtests[result['session']].state())

    @read_tool(name='playtest_get_state')
    def debug_state(session: str, verbose: bool = False) -> dict:
        """Inspect the current node, variables, action, pending arguments and recent node trace."""
        workspace.debugger(session)
        return workspace.playtests[session].state(verbose=verbose)

    @write_tool(name='playtest_debug_step')
    def debug_step(session: str, step_node: bool = True, answer: str | int | None = None,
                   provide_answer: bool = False, milliseconds: int = 0,
                   breakpoints: list[str] | None = None) -> dict:
        """Step/run, answer real inputs or advance time; minigame results are never fabricated."""
        debugger = workspace.debugger(session)
        if not 0 <= milliseconds <= 60000: raise ProjectError('Clock step must be 0–60000 ms')
        if breakpoints is not None: debugger.breakpoints = set(breakpoints)
        return debugger.resume(step=step_node, answer=answer, provide_answer=provide_answer, milliseconds=milliseconds)

    @write_tool(name='playtest_set_variable')
    def debug_set_variable(session: str, name: str, value: int) -> dict:
        """Change an existing numeric variable in the isolated debug session."""
        debugger = workspace.debugger(session)
        debugger.set_variable(name, value)
        return workspace.playtests[session].state()

    @write_tool(name='playtest_grid_pointer')
    def debug_grid_pointer(session: str, phase: str, cell: int | None = None) -> dict:
        """Send down/move/up/cancel to the real SHS grid minigame."""
        from .debugger import _Paused
        if phase not in ('down', 'move', 'up', 'cancel'): raise ProjectError('Invalid grid input phase')
        debugger = workspace.debugger(session)
        try: debugger.session.grid_pointer(phase, cell)
        except _Paused: pass
        return debugger.state()

    @write_tool(name='playtest_close')
    def debug_close(session: str) -> dict:
        """Discard an isolated debug session and its in-memory state."""
        return workspace.close_debug(session)

    @read_tool()
    def schema_get(kind: str | None = None, example: bool = False) -> dict:
        """Discover node kinds, or get one kind's fields, limits, defaults and example. example=true returns a branching transaction and test."""
        return branching_example() if example else node_schema(kind)

    @read_tool()
    def project_preview_edits(path: str, revision: str, operations: list[Edit]) -> dict:
        """Review 1–200 edits as one candidate and validate it without saving. Same operations as project_apply_edits; returns a diff and diagnostics."""
        return workspace.batch(path, revision, [op.model_dump(exclude_unset=True) for op in operations], preview=True)

    @edit_tool()
    def project_apply_edits(path: str, revision: str, operations: list[Edit]) -> dict:
        """Apply 1–200 related story edits atomically with one current revision. Forward references within the batch work. Failure leaves the project intact; success returns an undo checkpoint."""
        return workspace.batch(path, revision, [op.model_dump(exclude_unset=True) for op in operations])

    @read_tool()
    def graph_search_nodes(path: str, text: str = '', character: str | None = None, kind: str | None = None,
                           scene: int | None = None, offset: int = 0, limit: int = 50) -> dict:
        """Find dialogue, choices or other nodes by text, character ID, kind or scene. Offset >=0; limit 1–200, default 50."""
        project, revision = workspace.read(path)
        return dict(revision=revision, **graph.search(project, text=text, character=character, kind=kind,
                                                    scene=scene, offset=offset, limit=limit))

    @read_tool()
    def graph_get_subgraph(path: str, node_id: str, depth: int = 1,
                           direction: Literal['incoming', 'outgoing', 'both'] = 'both', limit: int = 100) -> dict:
        """Inspect a node, nearby branches and boundary connections. Depth 0 reads one node; allowed 0–20. Limit 1–200, default 100."""
        project, revision = workspace.read(path)
        return dict(revision=revision, **graph.subgraph(project, node_id, depth=depth, direction=direction, limit=limit))

    @read_tool()
    def graph_find_paths(path: str, target: str, source: str | None = None, limit: int = 20, max_depth: int = 100) -> dict:
        """Find structural routes to a scene or ending. Limit 1–200, depth 1–500. Conditions require playtesting; cycles are not expanded indefinitely."""
        project, revision = workspace.read(path)
        return dict(revision=revision, **graph.paths(project, target, source=source, limit=limit, max_depth=max_depth))

    @write_tool()
    def checkpoint_create(path: str, revision: str, label: str = 'Checkpoint') -> dict:
        """Keep a restorable copy of this project revision. Label <=200 characters; retain the newest 40 checkpoints per project."""
        return workspace.checkpoint(path, revision, label)

    @read_tool()
    def checkpoint_list(path: str) -> dict:
        """List retained checkpoint IDs and labels for this project; copies survive server restarts."""
        return dict(checkpoints=workspace.checkpoints(path))

    @edit_tool()
    def checkpoint_restore(path: str, revision: str, checkpoint: str) -> dict:
        """Undo edits by restoring a checkpoint against the current revision; preserve the current project as another checkpoint first."""
        return workspace.restore(path, revision, checkpoint)

    @read_tool()
    def export_inspect(path: str) -> dict:
        """Read an existing EXP's checksum and metadata before an intentional replacement export."""
        from exp_runtime.exp import ExpArchive
        source = workspace.path(path, '.exp')
        archive = ExpArchive(source.read_bytes())
        return dict(path=path, sha256=workspace.revision(source), bytes=source.stat().st_size,
                    metadata=asdict(archive.metadata()), resources=len(archive.entries))

    @read_tool()
    def asset_list_episodes(library: str, offset: int = 0, limit: int = 50) -> dict:
        """Find episode IDs and titles in a supplied library for asset discovery. Offset >=0; limit 1–200, default 50."""
        from exp_runtime.content import ContentLibrary
        graph.page(offset, limit)
        with ContentLibrary(workspace.path(library)) as content:
            records = content.episodes
            return dict(game=content.game_id, episodes=[{key: row[key] for key in ('id', 'titles', 'pack_id', 'episode_id')}
                for row in records[offset:offset + limit]], total=len(records),
                next_offset=offset + limit if offset + limit < len(records) else None)

    @read_tool()
    def asset_list_project(path: str, query: str = '', offset: int = 0, limit: int = 50) -> dict:
        """Find imported project images by user label or ID, with dimensions and embedded/reference status. Limit 1–200; offset >=0."""
        from .media import inspect_asset
        graph.page(offset, limit)
        project, revision = workspace.read(path)
        assets = [a for a in project.assets if query.casefold() in f'{a.id} {a.name}'.casefold()]
        return dict(revision=revision, assets=[dict(id=a.id, name=a.name, embedded=a.data is not None,
            **(inspect_asset(a.data) if a.data is not None else dict(type='image', library=project.library)))
            for a in assets[offset:offset + limit]], total=len(assets),
            next_offset=offset + limit if offset + limit < len(assets) else None)

    @read_tool()
    def asset_preview_image(resource: int, path: str | None = None, library: str | None = None,
                            episode: str | None = None, frame: int = 0, size: int = 256) -> dict:
        """See an imported image/atlas frame. Supply exactly one project path or library. Frame >=0; thumbnail size 32–1024, default 256."""
        from .catalog import read_asset
        from .media import thumbnail
        from .mcp_results import media_result
        if bool(path) == bool(library): raise ProjectError('Supply exactly one project path or library')
        if path:
            project, revision = workspace.read(path)
            asset = next((a for a in project.assets if a.id == resource), None)
            if asset is None: raise ProjectError('Unknown project asset')
            data = asset.data if asset.data is not None else read_asset(workspace, project.library, resource)
        else: data = read_asset(workspace, library, resource, episode)
        png, metadata = thumbnail(data, frame=frame, size=size)
        return media_result(png, 'image/png', dict(resource=resource, **metadata))

    @read_tool()
    def asset_preview_audio(library: str, resource: int, episode: str | None = None,
                            start_ms: int = 0, duration_ms: int = 5000) -> dict:
        """Hear a supplied audio resource as a bounded WAV preview. Start 0–3600000 ms; duration 1–10000 ms, default 5000."""
        from .catalog import read_asset
        from .media import audio_preview
        from .mcp_results import media_result
        wav = audio_preview(read_asset(workspace, library, resource, episode), start_ms=start_ms, duration_ms=duration_ms)
        return media_result(wav, 'audio/wav', dict(resource=resource, start_ms=start_ms, duration_ms=duration_ms))

    @read_tool()
    def playtest_list() -> dict:
        """List isolated playtest session handles and source revisions."""
        return dict(sessions=[dict(session=key, path=d.path, revision=d.revision) for key, d in workspace.debuggers.items()])

    @write_tool()
    def playtest_run(session: str, until: Literal['input', 'choice', 'end', 'node'] = 'input', node_id: str | None = None,
                     max_operations: int = 500, max_ms: int = 60000) -> dict:
        """Play until input, a choice, ending or node breakpoint. Drives real acknowledgement/clock gates. Budgets: 1–2000 operations and 0–60000 ms. Stops at unanswered choices and unsupported calls."""
        workspace.debugger(session)
        return workspace.playtests[session].run(until=until, node_id=node_id, max_operations=max_operations, max_ms=max_ms)

    @write_tool()
    def playtest_choose(session: str, option_id: str) -> dict:
        """Select an enabled answer by the exact ID from the current playtest state, preserving identity across shuffled display order."""
        workspace.debugger(session)
        return workspace.playtests[session].choose(option_id)

    @write_tool()
    def playtest_input(session: str, action: Literal['continue', 'answer_text', 'answer', 'tick', 'step', 'grid_pointer'],
                       value: str | int | None = None, milliseconds: int = 0,
                       phase: Literal['down', 'move', 'up', 'cancel'] | None = None, cell: int | None = None) -> dict:
        """Send one real player/debug input. Tick accepts integer 0–60000 ms. Text uses native input rules; minigames use actual selections or pointer cells, never injected results."""
        workspace.debugger(session)
        return workspace.playtests[session].input(action, value=value, milliseconds=milliseconds, phase=phase, cell=cell)

    @read_tool()
    def playtest_render(session: str) -> dict:
        """Capture the current screen through the shared player renderer using its supplied library. Run to a visible input first; rendering does not advance the live session."""
        from .media import render_playtest
        from .mcp_results import media_result
        debugger = workspace.debugger(session)
        return media_result(render_playtest(debugger), 'image/png', dict(width=480, height=720, session=session))

    @read_tool()
    def playtest_run_scenario(path: str, scenario: Scenario, library: str | None = None) -> dict:
        """Run a reproducible isolated test and assertions; no project edits or saves. At most 200 inputs/assertions. Reports failures, transcript, variable changes and visited-node coverage."""
        from .debugger import DebugSession
        from .playtest import run_scenario
        project, revision = workspace.read(path)
        settings = scenario.model_dump(exclude_unset=True)
        settings.setdefault('seed', 0)
        if library is not None: project.library = str(workspace.path(library)) if library else ''
        if project.library: workspace.path(project.library)
        debugger = DebugSession(project, start=settings.get('start'), seed=settings['seed'],
                                language=settings.get('language'), library=project.library or None)
        try: return dict(revision=revision, **run_scenario(debugger, settings))
        finally: debugger.close()

    @edit_tool()
    def playtest_save_scenario(destination: str, scenario: Scenario, replace_revision: str | None = None) -> dict:
        """Save a reusable authored test to a workspace .exptest file. Replacing one requires its current SHA-256 from playtest_get_scenario."""
        target = workspace.path(destination, '.exptest')
        if target.exists() and workspace.revision(target) != replace_revision:
            raise ProjectError('Scenario exists; provide its current SHA-256 to replace it')
        data = dict(format='exp-creator-scenario', version=1, scenario=scenario.model_dump(exclude_unset=True))
        encoded = json.dumps(data, ensure_ascii=False, indent=2).encode()
        if len(encoded) > 1024 * 1024: raise ProjectError('Scenario must fit 1 MiB')
        atomic_write(target, encoded)
        return dict(path=destination, revision=workspace.revision(target))

    def read_scenario(path):
        source = workspace.path(path, '.exptest')
        if source.stat().st_size > 1024 * 1024: raise ProjectError('Scenario must fit 1 MiB')
        record = json.loads(source.read_text(encoding='utf-8'))
        if not isinstance(record, dict) or record.get('format') != 'exp-creator-scenario' or record.get('version') != 1:
            raise ProjectError('Unsupported scenario format')
        return Scenario(**record['scenario']), workspace.revision(source)

    @read_tool()
    def playtest_get_scenario(path: str) -> dict:
        """Read a saved .exptest scenario and its replacement revision."""
        scenario, revision = read_scenario(path)
        return dict(scenario=scenario.model_dump(exclude_unset=True), revision=revision)

    @read_tool()
    def playtest_replay_scenario(path: str, scenario_path: str, library: str | None = None) -> dict:
        """Replay a saved .exptest against a project with real inputs and assertions; writes no player saves."""
        scenario, _ = read_scenario(scenario_path)
        return playtest_run_scenario(path, scenario, library)

    @read_tool()
    def result_read(result_id: str, offset: int = 0, limit: int = 6000) -> dict:
        """Retrieve a full oversized JSON result in character slices. Offset >=0; limit 1–6000, default 6000. The newest eight results are retained in memory."""
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 6000:
            raise ProjectError('Use offset >=0 and limit 1–6000')
        if result_id not in workspace.responses: raise ProjectError('Result expired; repeat the original read with a smaller page')
        value = workspace.responses[result_id]
        return dict(result_id=result_id, text=value[offset:offset + limit],
                    next_offset=offset + limit if offset + limit < len(value) else None)

    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description='SHSHD Runtime Creator MCP server (stdio)')
    parser.add_argument('--workspace', type=Path, required=True, help='Existing directory containing projects and assets')
    args = parser.parse_args(argv)
    try:
        server = create_server(args.workspace)
    except ModuleNotFoundError as error:
        if error.name and error.name.startswith('mcp'):
            parser.error('Install shshd-runtime[creator-mcp] or shshd-runtime-creator[mcp]')
        raise
    except (OSError, ProjectError) as error:
        parser.error(str(error))
    server.run(transport='stdio')


if __name__ == '__main__':
    main()
