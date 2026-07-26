# Cognitive Castle in your MCP client

Castle ships an MCP server (`castle-mcp`) that any [Model Context
Protocol](https://modelcontextprotocol.io/) client can consume. The
result is the same in every host: your AI agent gets `castle_*` tools
in its tool palette and can read/write your local palace during
conversation.

The Claude Code plugin at `.claude-plugin/` is the highest-fidelity
integration — auto-registered MCP server, Stop/PreCompact hooks that
mine your conversations into the palace as they happen, and MCP
`initialize.instructions` injection that bakes the `PALACE_PROTOCOL`
into the client's system prompt at session start. Other clients get
the tools; the hook-driven auto-mining is Claude-Code-specific for now.

## Install prerequisites once

```bash
git clone https://github.com/Testimonial/cognitive-castle.git
cd cognitive-castle
pip install -e .
# Verify the entry points landed on PATH
which castle && which castle-mcp
```

Initialize a palace once (per project or globally):

```bash
castle init ~/projects/myapp --yes
```

Everything below assumes `castle-mcp` is on your `$PATH`.

## Claude Code (highest-fidelity — full plugin experience)

```
/plugin marketplace add Testimonial/cognitive-castle
/plugin install castle@cognitive-castle
# then fully quit and reopen Claude Code
```

That's it. MCP tools + Stop/PreCompact hooks + slash commands
(`/castle:init`, `/castle:mine`, `/castle:search`, `/castle:status`,
`/castle:help`) are all wired.

**Manual alternative** (if you prefer not to use the plugin marketplace):

```bash
claude mcp add castle -- castle-mcp
```

## Codex (OpenAI's coding CLI)

Codex reads MCP servers from `~/.codex/config.toml`. Simplest setup:

```toml
[mcp_servers.castle]
command = "castle-mcp"
```

Restart Codex. The 32 `castle_*` tools appear in the tool palette.

### Sharing knowledge with Claude Code (recommended)

Castle stores everything in one LanceDB palace at `~/.castle/palace/`.
Both clients can point at the same palace and the reads/writes go to
the same tables — anything Claude Code files is instantly visible in
Codex, and vice-versa.

To pin the palace explicitly (safer if you ever run more than one):

```toml
[mcp_servers.castle]
command = "castle-mcp"
args = ["--palace", "/home/YOU/.castle/palace"]
```

And the matching Claude Code registration:

```bash
claude mcp add castle -- castle-mcp --palace /home/YOU/.castle/palace
```

Both clients now write to the same LanceDB tables, so the palace is a
single shared memory across your Codex + Claude Code sessions.

### Verifying the two clients see the same data

Quick round-trip smoke test:

1. From Claude Code, ask its agent to file a distinctive drawer:
   > *"Use castle_add_drawer to file wing=cross_check, room=test,
   > content='canary 2026-07-26'"*
2. From Codex, search for it:
   > *"Use castle_search to find 'canary 2026-07-26'"*

If Codex retrieves the exact string Claude Code saved, both are wired
to the same palace.

### Auto-mining is Claude-Code-only — capture Codex sessions manually

Claude Code has plugin-level Stop / PreCompact hooks that mine your
conversation into the palace as you talk (every ~15 turns). Codex has
no equivalent hook interface yet, so Codex conversations aren't
auto-filed. To catch up periodically:

```bash
castle mine ~/.codex/history --mode convos
```

Consider wiring this into a shell alias, cron, or an `after-session`
Codex hook if a later Codex build adds one.

### About `.codex-plugin/plugin.json`

The repo ships `.codex-plugin/plugin.json` with the same manifest
shape as `.claude-plugin/plugin.json` — if Codex ever grows a plugin
marketplace with auto-registration + hook support like Claude Code,
Castle is already packaged for it. Until then, the `config.toml`
snippet above is the working install path.

### Env vars propagate

`CASTLE_EMBEDDER_MODEL`, `CASTLE_PROJECT`, `CASTLE_LLM_*` etc. that
you set in your shell are inherited by the `castle-mcp` subprocess
Codex launches. If you set them for one client, keep them in a
shared shell profile (`~/.bashrc` / `~/.zshrc`) so Claude Code sees
the same values — otherwise you can hit `EmbedderIdentityMismatchError`
on the first search from the mismatched client.

## Cursor

Cursor supports MCP via `.cursor/mcp.json` (per-workspace) or
`~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "castle": { "command": "castle-mcp" }
  }
}
```

Reopen Cursor. Verify with the tool palette in a chat panel — you
should see `castle_search`, `castle_status`, `castle_add_drawer`,
`castle_info_score`, and friends.

## VS Code + GitHub Copilot

Modern GitHub Copilot Chat in VS Code supports MCP servers via
workspace-level `.vscode/mcp.json` or user-level settings. Add:

```json
{
  "mcpServers": {
    "castle": { "command": "castle-mcp" }
  }
}
```

Reload the VS Code window. The tools show up in the Copilot Chat tool
picker under the `castle` prefix.

Older Copilot builds without MCP support cannot consume Castle — the
Claude Code plugin, Codex, or Cursor path is the fallback.

## Gemini CLI

See `examples/gemini_cli_setup.md` — same pattern (`castle-mcp` as the
MCP server binary in Gemini CLI's server config).

## Generic MCP client (anything else)

Any MCP client that supports the standard `mcpServers` config block
works. The one line that matters everywhere is:

```json
{ "mcpServers": { "castle": { "command": "castle-mcp" } } }
```

Environment variables (e.g. `CASTLE_LLM_PROVIDER`, `CASTLE_PROJECT`)
propagate to the subprocess exactly as they would to any child process
launched by the host.

## What tools your client will see

- **Read:** `castle_status`, `castle_list_wings`, `castle_list_rooms`,
  `castle_get_taxonomy`, `castle_search`, `castle_check_duplicate`,
  `castle_info_score` (v3.4.0 — nn_novelty score for arbitrary text)
- **Write:** `castle_add_drawer`, `castle_delete_drawer`
- **Knowledge graph:** `castle_traverse_graph`, `castle_find_tunnels`,
  `castle_create_tunnel`, `castle_list_tunnels`, `castle_delete_tunnel`,
  `castle_follow_tunnels`, `castle_graph_stats`
- **Diary:** `castle_diary_write`, `castle_diary_read`
- **Maintenance:** `castle_reconnect`, `castle_kg_invalidate`
- **Discovery:** `castle_get_aaak_spec`

Full schema for each is emitted by the `tools/list` MCP call your
client makes at connection time.

## Feature parity matrix

| Feature | Claude Code | Codex | Cursor | VS Code+Copilot | Gemini CLI | Generic MCP |
|---|---|---|---|---|---|---|
| `castle_*` MCP tools | ✅ | ✅ | ✅ | ✅ (recent) | ✅ | ✅ |
| Slash commands (`/castle:*`) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Auto-mining Stop/PreCompact hooks | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| MCP `initialize.instructions` injection | ✅ | ✅ (if client honours it) | ⚠️ | ⚠️ | ⚠️ | depends |
| Skill loading | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

Claude Code has the fullest integration because the plugin protocol
lets Castle register hooks and skills, not just an MCP server. All
other clients get the tools and the palace state; auto-mining requires
manually invoking `castle mine` (or a shell alias) after conversations
end.
