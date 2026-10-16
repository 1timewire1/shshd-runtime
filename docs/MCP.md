# Creator MCP server

The optional stdio server lets an MCP client author stories, inspect supplied
assets, export native EXPs and playtest with the production VM and renderer.
It uses the same model and compiler as the desktop creator. Projects are
ordinary `.expproj` files; no game assets are supplied.

```sh
uv run --locked --extra creator-mcp exp-creator-mcp --workspace /path/to/stories
```

Install the server with pip:

```sh
python -m pip install 'exp-runtime[creator-mcp]>=0.6.1'
# Equivalent component-only install:
python -m pip install 'exp-runtime-creator[mcp]>=0.6.1'
```

This extra installs the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x),
engine, both game profiles and shared player with pygame for isolated media
previews. It does not install Qt. The ordinary creator compiler still depends
only on the formats component. The maintained MCP 1.x line preserves this
project's Python 3.10 support.

## Connect Codex CLI

Create a workspace directory, then register the installed entry point:

```sh
codex mcp add exp_creator -- /absolute/path/to/venv/bin/exp-creator-mcp --workspace /absolute/path/to/stories
codex mcp list
```

The equivalent Codex configuration is:

```toml
[mcp_servers.exp_creator]
command = "/absolute/path/to/venv/bin/exp-creator-mcp"
args = ["--workspace", "/absolute/path/to/stories"]
startup_timeout_sec = 20
tool_timeout_sec = 60
```

Use `Scripts/exp-creator-mcp.exe` on Windows. For source development, set
`command` to the absolute path of `uv` and use arguments
`["run", "--directory", "/path/to/exp-runtime", "--locked", "--extra",
"creator-mcp", "exp-creator-mcp", "--workspace", "/path/to/stories"]`.

Codex also supports `enabled_tools` and `disabled_tools` for a smaller exposed
catalog. See the official [MCP setup](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
For other clients supporting `mcpServers`, use:

```json
{
  "mcpServers": {
    "exp_creator": {
      "command": "/absolute/path/to/venv/bin/exp-creator-mcp",
      "args": ["--workspace", "/absolute/path/to/stories"]
    }
  }
}
```

The server itself requires no HTTP listener, account or network service.

## Edit alongside the desktop creator

Save a project inside the configured MCP workspace and open that same `.expproj`
in the desktop creator. The status bar shows **MCP: live editing ready**.
Keep chatting in your MCP client; no second server configuration or embedded
chat account is needed. Projects must be saved once so both processes can
identify the same file.

While that project is open, the desktop owns its live document:

- `project_get` includes unsaved desktop edits and returns `live: true` and
  `unsaved`. Graph queries, validation, export and new playtests use that state.
- Model transactions appear immediately in the graph and inspector. Each
  transaction enters the desktop undo history as one edit. Undo/redo is visible
  to the model on its next read. Edits also write an autosave recovery copy.
- Model edits remain unsaved in the desktop, just like human edits. Use **Save**
  to write the `.expproj`. The response includes `unsaved: true`; an undo
  checkpoint is retained in the MCP workspace as well.
- If the user edits after a model read, the transaction fails with
  `stale_revision`; reread and reapply. A modal dialog, drag or unfinished number
  entry returns `project_busy`, so the model cannot replace a pending UI edit.
- Closing the project returns MCP to editing its saved file. A broken connection
  returns `desktop_unavailable` instead of writing behind the editor's back.
  Reopen the project in the creator to recover a crashed session, then reread.

The desktop uses an authenticated local loopback connection and a private
`.creator-session` directory next to the project for discovery and process
locks. One desktop window owns a project at a time. Session credentials are
removed on close; leftover lock files are harmless. Keep this directory out of
version control and distribution. Qt stays in the desktop process; the MCP
server and compiler remain usable without it. MCP asset paths still follow the
workspace restriction below, including libraries used for rendered playtests.

## Tool and result contracts

Tool names follow this project's `<domain>_<action>[_object]` convention:
`project_apply_edits`, `graph_search_nodes`, `asset_preview_image` and
`playtest_run_scenario`. The server name supplies the product namespace;
tools use searchable lowercase words separated by underscores. This exact
spelling is a project choice. OpenAI's guidance recommends stable action
identifiers, explicit schemas and accurate read/write annotations; it does not
mandate this separator. See [tool planning](https://developers.openai.com/plugins/plan/tools)
and [metadata guidance](https://developers.openai.com/plugins/guides/optimize-metadata).

Keep descriptions under 1,000 UTF-8 bytes and input schemas under 5,000 bytes.
The initial server instructions fit within 512 characters. Limits and defaults
appear in descriptions as well as server validation, because clients can
normalize away JSON Schema constraints. Detailed contracts live in
`schema_get` and resources rather than every tool description. These budgets
are project regression checks, not promises about every client's limits.
[Kyle Avery's MCP design article](https://kyleavery.com/posts/mcp-design/)
motivated checking the client-visible definitions and results directly.

JSON results have matching text and `structuredContent`. Operation errors use
`isError` with an error code, message and recovery instruction. Results above
18,000 UTF-8 bytes return a bounded preview, useful top-level status/revision
fields and a `result_id`; `result_read` retrieves the full JSON in slices of
up to 6,000 characters. The newest eight oversized results remain in memory.
Image and audio previews return native MCP media blocks with small metadata;
playback/display support depends on the client.

## Authoring workflow

1. Call `schema_get` for available node kinds, or pass `kind` for that kind's
   field schema, defaults, example, game support and compatibility notes.
   `example=true` returns a branching transaction and executable scenario.
   Equivalent resources are `creator://schema`, `creator://schema/{kind}`
   and `creator://examples/branching`.
2. Use `project_list`, `project_create` or `project_import_exp`, then
   `project_get` for a summary and current revision. `view="full"` pages node
   records without embedded image bytes. Graph tools search dialogue/choices,
   fetch a neighborhood and find bounded structural paths to an ending.
   Structural paths do not prove that runtime conditions permit traversal.
3. Submit `project_preview_edits` with a revision and 1–200 operations for a
   diff and diagnostics. Submit the same operations to `project_apply_edits`
   to apply atomically. Closed projects save to disk; open desktop projects update
   the live document and its undo history. A stale revision or invalid operation
   leaves the project intact. Success returns the new revision and an undo
   checkpoint, with `live` and `unsaved` indicating where the edit was applied.
4. `project_validate` returns multiple issues with code, severity, node ID,
   field, message and suggestion. Incomplete connections may be saved while
   authoring, but missing targets prevent export. Unreachable nodes are
   warnings. Validation does not establish every possible gameplay path.
5. Playtest, then call `project_export_exp` with the current revision. Use
   `export_inspect` before replacing an existing EXP and pass its SHA-256 as
   `replace_revision`. Export writes atomically and does not publish anything.

Batch operations share the following vocabulary:

| `op` | Fields and behavior |
| --- | --- |
| `project` | Patch `changes`: title/game/IDs/start/language/locales/library. |
| `node`, `character` | Supply `id` and `changes`, or `remove: true`. |
| `connect` | Set `source`, `target`, and `field`: `next`, `otherwise` or `options.N.target`. |
| `rename_node` | Set `id` and `new_id`; update edges, start and translation keys. |
| `image` | Embed a workspace PNG/JPEG at `source`. |
| `library_image` | Supply `library`, exact `resource` ID and optional `episode`. |
| `asset_label` | Give integer asset `id` a user-defined `label`. |
| `layout` | Arrange nodes without changing execution connections. |

Nodes use model defaults when created. Forward references within a batch work;
removing a node or character requires reconnecting references in that batch.
Use `schema_get` for node-specific fields. Focused single-edit tools remain
available: `project_update`, `graph_edit_node`, `character_edit`,
`graph_arrange`, `asset_import_image` and `asset_import_library_image`.

`checkpoint_create`, `checkpoint_list` and `checkpoint_restore` support named
save points and undo. The newest 40 snapshots per project persist in
`.creator-history` inside the workspace, including embedded project assets.
Restore preserves a checkpoint of the state being replaced. History is keyed
by the project's workspace-relative path; moving it changes that identity.
Treat history as private project content alongside the project itself.

## Assets and original EXPs

Import original game files through the player first. Put the resulting library
inside the MCP workspace. `asset_list_episodes` finds episode IDs and titles;
`asset_list` lists resource types, image/atlas dimensions and audio duration.
Resource names absent from the archive remain unknown. Use `asset_list_project`
and `asset_label` for user-defined image labels.

Library scans inspect at most 200 IDs per call. Follow `next_offset` even when
a filtered page has no matches. `asset_preview_image` returns a bounded PNG
thumbnail or atlas frame. `asset_preview_audio` decodes up to 10 seconds into a
WAV clip. Imported base images remain library references; episode images are
embedded in the project.

`project_import_exp` recovers authored graphs or preserves original scripts as
native blocks. `native_get_data` and `native_find_text` inspect fixed data banks
and printable text candidates. Confirm an instruction's reference before using
`native_update_text`: a candidate alone is not proof that data is dialogue.
Replacement strings must fit their original allocations; `native_update_data`
preserves bank length and addresses.

## Reproducible playtests

`playtest_start` opens an isolated session, initially paused at its first node.
An optional unsigned 32-bit seed initializes both native random streams. Pass
an imported `library` (or save it on the project) for original layout metrics
and screenshots. Asset-free tests exercise story logic with fallback metrics.
There are at most eight live sessions; `playtest_list` and `playtest_close`
manage their handles. No player saves are written.

`playtest_run` drives real acknowledgement and clock gates until an input,
choice, ending or node breakpoint. It stops at unanswered choices, minigames
and unsupported calls. Operation/time budgets prevent unbounded runs.
`playtest_get_state` reports dialogue, choices, variables, remaining time and
next actions; `verbose=true` adds PC, stack, pending arguments and native state.
`playtest_render` snapshots the current visible screen through the shared
renderer in a separate process without advancing the live session.

Choose by the exact ID from the current state using `playtest_choose`. IDs
combine node ID and original answer value, preserving identity when display
order shuffles within a project revision. Timed defaults retain the native
visible-row semantics. `playtest_input` submits real text/answer/pointer inputs,
Continue or explicit clock ticks. Lower-level `playtest_debug_step` and
`playtest_grid_pointer` support debugging. `playtest_set_variable` is an
explicit manual override recorded in the session state; it is not a simulated
player result. Unknown service arguments remain pending.

`playtest_run_scenario` executes a declarative `scenario` with up to 200 steps
and 200 assertions. For example, adapt the IDs to your graph:

```json
{
  "seed": 7,
  "steps": [
    {"action": "run", "until": "choice"},
    {"action": "choose", "option_id": "decision:0"},
    {"action": "run", "until": "end"}
  ],
  "assertions": [
    {"kind": "variable", "name": "points", "equals": 1},
    {"kind": "ended"}
  ]
}
```

Reports include failures, transcript, variable changes and visited-node
coverage. `playtest_save_scenario` stores a reusable `.exptest` file;
`playtest_get_scenario` returns its contents and replacement revision, and
`playtest_replay_scenario` runs it against a project. No Python evaluation or
invented minigame callback results are exposed.

## Verification and boundaries

```sh
uv run --locked --extra creator --extra creator-mcp python -m unittest discover -s tests -p 'test_creator*.py'
uv run --locked --extra creator-mcp python tools/test_creator_codex.py
```

The first command covers authoring, transport, rollback, live desktop editing
through an actual stdio client, shared undo and playback. The
optional Codex probe uses the installed CLI and a temporary localhost fake
Responses endpoint with two fixed read-only tool calls. It makes no remote
model requests and does not intercept credentials. Tested with Codex CLI
0.162.1: names, compact schemas, parameter-limit prose, success output and
failed-call recovery reach the client. This tests ordinary namespaced tool
mode, not every deferred/code-mode client path or a model's tool selection.

All tool paths resolve inside the workspace; traversal and escaping symlinks
are rejected. Create destination directories before writing. Cooperative locks
serialize this project's file writers; live transactions are serialized on the
desktop UI thread and recheck their revision there. Unrelated programs do not
participate in those locks. The desktop checks for external file changes before
saving and offers Save as through the normal workflow to preserve its draft.
The server exposes no shell, signing, repository publishing or release tools.

Exports use native CSPUD/KiWi. Football and grid minigames are SHS-only.
End nodes use native episode-exit service 7 and the existing game menu/episode
picker. Full original-app playback is still unverified.
See [CREATOR.md](CREATOR.md) for original-slot export and native evidence.
