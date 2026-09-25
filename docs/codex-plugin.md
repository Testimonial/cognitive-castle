# Connect Cognitive Castle to Codex

The `cognitive-castle` plugin provides local `castle_*` MCP tools, the `castle`
skill, and background capture of Codex conversations. The setup below was
verified with Codex CLI **0.156.1** on Linux. Shell examples use Bash; `/hooks`
and `/mcp` are commands inside the interactive Codex CLI.

## 1. Install the Python runtime

For a new checkout:

```bash
git clone --branch develop https://github.com/Testimonial/cognitive-castle.git
cd cognitive-castle
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
castle --version
command -v castle
command -v castle-mcp
codex --version
```

If you already have the checkout and a Python environment, run
`python -m pip install -e .` there instead. Both `castle` and `castle-mcp` must
be on the PATH inherited by Codex. Launch `codex` from the activated terminal.
A desktop application may inherit a different PATH.

The plugin does not install Python dependencies or download embedding models.
Models may need an initial download before offline use. Core memory needs no
external API key; optional LLM processing uses your existing provider settings.

If you already use Castle with Claude, keep the existing palace and model
configuration. The default palace is `~/.castle/palace`; both clients can use it.
For first-time project setup, run `castle init /path/to/project --no-llm` and
follow the prompts. Project-file import is separate from conversation capture.

## 2. Install the personal plugin

This route uses Codex's `plugin-creator` skill and its local helper scripts.
The examples assume they are installed at
`~/.codex/skills/.system/plugin-creator/`. If that directory is absent, ask Codex
to use its available `plugin-creator` skill for this checkout. The
[MCP-only alternative](#mcp-only-alternative) below works without these helpers.

For the first installation, run from the repository root:

```bash
python ~/.codex/skills/.system/plugin-creator/scripts/create_basic_plugin.py \
  cognitive-castle --with-skills --with-hooks --with-mcp --with-marketplace
cp -R .codex-plugin .mcp.json hooks skills ~/plugins/cognitive-castle/
python ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py \
  ~/plugins/cognitive-castle
python ~/.codex/skills/.system/plugin-creator/scripts/read_marketplace_name.py
codex plugin add cognitive-castle@personal
codex plugin list --marketplace personal --json
```

If the helper prints a marketplace name other than `personal`, substitute that
name in the two Codex commands. An existing installation should use the update
steps below instead of scaffolding again.

Check that the list reports `installed: true` and `enabled: true`. The personal
catalog is `~/.agents/plugins/marketplace.json`, its source package is
`~/plugins/cognitive-castle`, and Codex installs a cached copy. Editing a source
file in the checkout does not automatically refresh that cached plugin.

Fully exit and reopen Codex, then start a new thread to load the plugin.

## 3. Activate the capture hooks

Installing the plugin and trusting its hooks are separate steps. Codex requires
review of each new or changed hook before it runs. See the official
[hook documentation](https://learn.chatgpt.com/docs/hooks).

Inside Codex CLI:

1. Enter `/hooks`.
2. Select **PreCompact**, then press **Enter**.
3. Check `Source: Plugin - cognitive-castle@personal` and the command
   `castle hook run --hook precompact --harness codex`.
4. Press **t** to trust that hook.
5. Repeat for **SessionStart** and **Stop**.

The first screen lists **event names**, not a row named Cognitive Castle. Scroll
down to find **Stop**. When these are the only hooks for each event, the expected
state is:

| Event | Installed | Active | Purpose |
|---|---:|---:|---|
| SessionStart | 1 | 1 | Small memory capability reminder |
| Stop | 1 | 1 | Capture the current transcript after a turn |
| PreCompact | 1 | 1 | Capture the transcript before context compaction |

`Installed: 1, Active: 0` means the hook is present but will not run; open its
details to check trust or disabled state. Additional plugins can increase counts.

## 4. Verify tools and an actual save

Enter `/mcp` and check that `castle` connected. This checkout exposes 34 tools,
including `castle_search`, `castle_get_drawer`, `castle_add_drawer`,
`castle_sue_review`, and `castle_sue_status`. Restart an existing MCP connection
after updating the editable Castle installation to refresh its tool list.

For requirement reviews, ask Codex to select the relevant drawers, state the
decision, and call `castle_sue_review`; call `castle_sue_status` with its returned
run ID to read the dialogue and source links. SUE runs separately in the
background. Its default provider is local Ollama. Explicitly choosing
`provider="codex"` sends that selected bundle to the configured Codex provider,
using `gpt-5.6-luna` / low reasoning unless a model is supplied. Merely running
Castle inside Codex does not choose external processing. See the
[complete SUE guide](sue-scope.md).

To test automatic capture, send a distinctive sentence, for example:

> Castle capture check 2026-09-24: the copper owl is on the windowsill.

Let Codex finish its answer and allow the background hook to complete. In a
subsequent turn, ask:

> Use castle_search in fast mode to find my copper owl sentence, then retrieve
> the original drawer and show its wing and source. Do not file it manually.

For this repository, the expected wing is `codex_cognitive_castle`. Other
workspaces use `codex_` followed by a normalized directory name. A retrieved
drawer containing the sentence and the correct transcript source confirms a
save. An active hook, a successful MCP connection, or a completed answer alone
does not confirm that capture finished.

## What is saved

Stop and PreCompact import only the transcript supplied by Codex, with
`added_by=codex`. They run asynchronously and preserve message text without
creating diary summaries. SessionStart does not import the transcript.

Project files are imported separately:

```bash
castle mine /path/to/project
```

The importer supports Codex rollouts using canonical `event_msg` turns or newer
`response_item` message records. In the latter format, developer/system messages
are excluded. Missing transcripts are a no-op. Transcript formats may change
between Codex versions, and background work can be interrupted.

To retry a specific transcript manually, use its actual path:

```bash
castle mine /absolute/path/to/rollout.jsonl --mode convos \
  --wing codex_cognitive_castle --agent codex
```

This confirms manual import, not automatic hook execution. Choose the wing for
that transcript's workspace. Do not substitute the whole sessions directory
unless you intend to import all of it.

## Updating the installation

After updating your checkout, run from its root:

```bash
python -m pip install -e .
python ~/.codex/skills/.system/plugin-creator/scripts/read_marketplace_name.py
cp -R .codex-plugin .mcp.json hooks skills ~/plugins/cognitive-castle/
python ~/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py \
  ~/plugins/cognitive-castle
python ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py \
  ~/plugins/cognitive-castle
codex plugin add cognitive-castle@personal
```

Use the marketplace name printed by the helper. The cachebuster refreshes the
installed package without changing the repository's release version. Restart
Codex, open a new thread, and check `/hooks` again: changed definitions may need
new trust. The editable Python install uses this checkout directly; the cached
manifest, skill, and hook definitions still require the reinstall step.

## Troubleshooting

| Symptom | Check or action |
|---|---|
| No `cognitive-castle` row in `/hooks` | Open `PreCompact`, `SessionStart`, or `Stop`; the plugin name appears under `Source` in the details. |
| Plugin installed but no automatic save | Verify all three hooks are active, then check for the actual drawer after a completed turn. |
| No `castle` entry in `/mcp` | Check `codex plugin list --marketplace personal --json`, then restart Codex with the plugin enabled. |
| `castle-mcp` not found | Activate the environment containing this checkout before starting Codex; inspect `command -v castle-mcp`. |
| MCP startup timed out after 30 seconds | Update the Python runtime from this checkout and restart Codex. Older code scanned the entire palace during the handshake; initialization now leaves statistics to `castle_status`. |
| MCP works, capture fails | Confirm `castle` is also on PATH. Inspect hook details/output and `~/.castle/hook_state/hook.log` for capture errors. Legacy installations may use `~/.mempalace/hook_state/`. |
| Hook files changed but behavior did not | Copy the files, run the cachebuster, reinstall, and start a new thread. |
| No `/hooks` command | Check `codex --version` and use a CLI version supporting lifecycle hooks. These instructions describe the CLI, not a desktop menu. |

`castle-mcp` waits for JSON-RPC on stdin; running it alone and seeing a startup
message is not a complete connection test. An old `last_checkpoint` file or the
`castle_memories_filed_away` tool reflects the diary checkpoint mechanism and is
not proof that the Codex transcript hook completed.

## MCP-only alternative

To expose memory tools without installing the plugin, add this to
`~/.codex/config.toml`:

```toml
[mcp_servers.castle]
command = "castle-mcp"
```

Restart Codex and check `/mcp`. Use an absolute executable path if needed. This
configuration supplies tools only; it does not install the skill or capture
hooks. Use either this registration or the plugin's bundled MCP registration
for `castle` to keep configuration unambiguous.

## Package layout and developer checks

The repository bundles `.codex-plugin/plugin.json`, `.mcp.json`,
`skills/castle/`, and `hooks/hooks.json`. Claude's separate `.claude-plugin/`
integration remains available. See the official
[plugin packaging guide](https://developers.openai.com/plugins/build/plugins).

```bash
python -m pytest tests/test_codex_plugin.py tests/test_hooks_cli.py tests/test_normalize.py -q
```

These tests use synthetic transcripts. They check scoped capture, startup
output, failure handling, and both rollout formats without reading personal
memories. Successful unit tests do not substitute for the capture check above.
