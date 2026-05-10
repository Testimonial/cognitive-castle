# Cognitive Castle — Claude Code Plugin (Personal-Use Phase 1)

**Date:** 2026-05-10
**Branch target:** develop
**Scope:** Make Cognitive Castle installable as a Claude Code plugin for the repo author's own use. MCP server + auto-save hooks. No marketplace publishing, no SessionStart context injection, no Windows support, no full source-code rebrand.

## Background

The Cognitive Castle codebase ships a working MCP server (`castle-mcp` entry point in `pyproject.toml:35`) and two hook scripts (`hooks/mempal_save_hook.sh`, `hooks/mempal_precompact_hook.sh`). Today, wiring those into a running Claude Code instance requires hand-editing `~/.claude/settings.json` with absolute paths and remembering the conventions. There is no project-level `.claude/settings.json` for the repo, no plugin manifest, and the hook scripts are still named after the prior "MemPalace" branding.

The current state means Cognitive Castle delivers zero benefit to the agent inside a Claude Code session run from this directory: no MCP tools surface, no transcripts get mined, no context is injected. The repo contains the engine but not the wiring.

This work creates that wiring. The deliverable is a plugin shipped from inside the Castle repo itself, registered via Claude Code's marketplace mechanism, and bootstrapped by a new `castle install-claude` CLI subcommand that does pre-flight checks and prints the exact slash commands the user runs inside Claude Code.

## Goals

1. After running `castle install-claude` and the printed slash commands, a fresh Claude Code session in any directory has `mcp__cognitive-castle__*` tools available.
2. Stop and PreCompact events run the renamed Castle hooks, mining session transcripts into the palace without user intervention.
3. The plugin lives inside the Castle repo, so `git pull` updates the plugin in lockstep with the code.
4. A reproducible per-machine install: `git clone && pip install -e ".[dev]" && castle install-claude` produces a working setup.

## Non-goals

- Marketplace publishing (Phase 2; out of this spec).
- SessionStart context injection (deferred; declined by the user during brainstorming on grounds it needs a recall heuristic that doesn't exist yet).
- Windows hook compatibility (the existing `.sh` scripts target POSIX shells; adding `.cmd` siblings is out).
- Full source-code rebrand of `MempalaceConfig`, `~/.mempalace/` paths, package internals, or the package-level `cognitive_castle/README.md`. Tracked separately. Only the two hook scripts and the `MEMPAL_DIR` env var are renamed here, because the plugin manifest references them.
- Reopening the CLAUDE.md doc refresh (spec at `6533e32`); resumes after this work.

## Source of truth

Every claim in this design is verifiable against the current codebase or Claude Code documentation:

- Plugin manifest format and `enabledPlugins` semantics — confirmed via Claude Code documentation research: local plugins require a marketplace, no `local-path` shortcut exists in `enabledPlugins`. Format is `<plugin-name>@<marketplace-id>: true`.
- Plugin filesystem layout — modeled on inspected installed plugins:
  - `~/.claude/plugins/cache/claude-plugins-official/context7/unknown/` (MCP-only plugin: `.claude-plugin/plugin.json` + `.mcp.json` at root).
  - `~/.claude/plugins/cache/claude-plugins-official/superpowers/5.1.0/` (skills + hooks plugin: `.claude-plugin/plugin.json` + `hooks/hooks.json` at root).
- MCP server entry point — `pyproject.toml:33-35` ships `castle = cognitive_castle.cli:main` and `castle-mcp = cognitive_castle.mcp_server:main`.
- Hook scripts — `hooks/mempal_save_hook.sh` and `hooks/mempal_precompact_hook.sh` exist and currently read a `MEMPAL_DIR` env var.
- Version source — `cognitive_castle/version.py` holds a single canonical version string.

## File layout

The Castle repo root *is* the plugin root, mirroring superpowers. New and modified files:

```
cognitive-castle/                                 # repo root == plugin root
├── .claude-plugin/                               # NEW directory
│   ├── plugin.json                               # NEW: plugin manifest
│   └── marketplace.json                          # NEW: local marketplace listing
├── .mcp.json                                     # NEW: registers castle-mcp as MCP server
├── hooks/
│   ├── hooks.json                                # NEW: registers Stop + PreCompact hooks
│   ├── castle_save_hook.sh                       # RENAME from mempal_save_hook.sh
│   ├── castle_precompact_hook.sh                 # RENAME from mempal_precompact_hook.sh
│   └── README.md                                 # MODIFIED: reflect renamed scripts
└── cognitive_castle/
    ├── claude_plugin_install.py                  # NEW: install/check/--uninstall logic
    ├── cli.py                                    # MODIFIED: add `install-claude` subcommand
    └── version.py                                # unchanged; consumed by manifest sync test
```

### `.claude-plugin/plugin.json`

```json
{
  "name": "cognitive-castle",
  "description": "Persistent verbatim memory for Claude Code agents — local-first, no vector DB required.",
  "version": "3.3.3",
  "author": { "name": "Ladislav Bihari", "email": "ladislav.bihari@gmail.com" }
}
```

The `version` field is a literal string. A unit test asserts equality with `cognitive_castle.version.__version__` so drift fails CI rather than silently shipping mismatched manifests.

### `.claude-plugin/marketplace.json`

```json
{
  "version": "1.0.0",
  "plugins": [
    { "name": "cognitive-castle", "source": "." }
  ]
}
```

`source: "."` points at the repo root because that *is* the plugin. The marketplace ID is determined by Claude Code at `/plugin marketplace add` time. Resolution of the ID is captured under Open Questions.

### `.mcp.json`

```json
{ "cognitive-castle": { "command": "castle-mcp" } }
```

Mirrors context7's `npx`-based pattern. Assumes `castle-mcp` is on `$PATH`, which is true after `pip install -e .` or `pip install cognitive-castle`.

### `hooks/hooks.json`

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [{ "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/castle_save_hook.sh" }] }
    ],
    "PreCompact": [
      { "hooks": [{ "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/castle_precompact_hook.sh" }] }
    ]
  }
}
```

`${CLAUDE_PLUGIN_ROOT}` resolves to the repo root once the plugin is installed via the marketplace.

### Hook script renames

In-scope rename, since the manifest above references the new names:

- `hooks/mempal_save_hook.sh` → `hooks/castle_save_hook.sh`
- `hooks/mempal_precompact_hook.sh` → `hooks/castle_precompact_hook.sh`
- Inside both scripts:
  - Env var `MEMPAL_DIR` → `CASTLE_DIR`
  - State dir `$HOME/.mempalace/hook_state` → `$HOME/.castle/hook_state`
  - Header comments `MEMPALACE` → `Cognitive Castle`
  - Example commands `mempalace mine` → `castle mine`
- `hooks/README.md` updated to match new filenames and env var.

The `$CASTLE_DIR` *resolution policy* (what to do when unset) is left as an open question; the rename itself is mechanical.

## Install command

A new subcommand `castle install-claude` in `cognitive_castle/claude_plugin_install.py`, wired into `cognitive_castle/cli.py`. The command does **not** perform installation; the slash commands `/plugin marketplace add` and `/plugin install` are Claude-Code-internal and have no shell equivalent. The command is a verifier and instruction printer.

### `castle install-claude` (default mode)

1. **Resolve repo root.** Use `pathlib.Path(cognitive_castle.__file__).resolve().parent.parent`. Validate that the resulting directory contains `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.mcp.json`, and `hooks/hooks.json`. If not, exit non-zero with: `Castle does not appear to be installed via 'pip install -e .' from a checkout. Plugin install requires an editable install.`
2. **Pre-flight check.** Verify:
   - `castle-mcp` is on `$PATH` (use `shutil.which`).
   - The four manifest files parse as valid JSON.
   - `cognitive_castle.version.__version__` matches `plugin.json["version"]`.
3. **Print the slash commands** with the resolved repo path interpolated:
   ```
   Cognitive Castle plugin files verified.

   To complete install, run these inside Claude Code:
     /plugin marketplace add /home/lbihari/cognitive-castle
     /plugin install cognitive-castle@cognitive-castle

   Then fully quit Claude Code and reopen it (a `/reload` is not enough for new MCP servers).
   Verify with: castle install-claude --check
   ```
4. Exit 0.

### `castle install-claude --check`

Read-only. Validates the install by:

1. Re-running pre-flight (manifest files parseable, `castle-mcp` on PATH, version sync).
2. Reading `~/.claude/settings.json`. Confirming an `enabledPlugins` entry of the form `cognitive-castle@*: true` exists.
3. Spawning `castle-mcp --help` (or equivalent quick-exit subprocess) to confirm it runs without immediate failure.

Exit 0 if all pass. Exit non-zero with a specific diagnostic if any fail (which check failed, what to do).

### `castle install-claude --uninstall`

Out of this spec. Document in the post-install printout that uninstall is `/plugin uninstall cognitive-castle@cognitive-castle` followed by `/plugin marketplace remove cognitive-castle`.

## Runtime data flow

Once the plugin is registered and Claude Code restarted:

1. Claude Code reads `enabledPlugins`, finds `cognitive-castle@<id>: true`.
2. It loads the marketplace, resolves to the local repo root, reads the four manifest files.
3. It spawns `castle-mcp` via the `.mcp.json` entry. The MCP tools `mcp__cognitive-castle__*` become available in the session.
4. It registers Stop and PreCompact hook handlers per `hooks/hooks.json`.
5. During a session: agent calls flow MCP-protocol → `castle-mcp` subprocess → `cognitive_castle.searcher` and friends → JSON results back to the agent.
6. On Stop: Claude Code invokes `castle_save_hook.sh`. Script reads `$CASTLE_DIR`, runs `castle mine` (or no-ops + logs if unset). Exits.
7. On PreCompact: same shape, `castle_precompact_hook.sh`.

## Failure modes

| Failure | Where it surfaces | Handling |
|---|---|---|
| `castle-mcp` not on `$PATH` | Plugin loads, MCP server fails to start, tools missing in session. Claude Code typically logs to stderr or a plugin log. | `castle install-claude` preflight catches this. User runs `pip install -e .`. |
| Palace not yet initialized | MCP tool returns "no palace at $path" error response. | Existing MCP behavior. User runs `castle init`. |
| Hook script error (e.g., `castle mine` failure) | Stop event completes from Claude Code's perspective; failure appears in `~/.castle/hook_state/<event>.log`. | Hooks must `exit 0` even on internal failure (don't block Claude Code) and append failure context to the log. |
| `$CASTLE_DIR` unset and no fallback configured | Hook no-ops with a single log line: "CASTLE_DIR unset; skipping mine." | Acceptable. Explicit no-op beats silent corruption. |
| Plugin manifest typo / invalid JSON | `/plugin install` rejects it inside Claude Code. | `castle install-claude` preflight validates JSON parseability before printing the slash commands. |
| `plugin.json` and `version.py` drift | Mismatched version visible in `/plugin` UI. | Sync test in CI fails the build. |
| Repo not installed editably | `castle install-claude` exits 1 with: "Plugin install requires an editable install." | User runs `pip install -e .`. |

## Testing strategy

**Unit tests** in a new `tests/test_claude_plugin_install.py`:

- Repo-root resolution returns the expected directory for editable installs (use a fixture mocking `cognitive_castle.__file__`).
- Pre-flight detects each missing manifest file individually, with the failure naming the missing file.
- Pre-flight detects missing `castle-mcp` on `$PATH` (mock `shutil.which`).
- `--check` parses a sample `~/.claude/settings.json` and reports `enabledPlugins` state correctly (present, absent, mistyped).
- Version sync: `plugin.json["version"]` equals `cognitive_castle.version.__version__`.

**Manifest validation tests** in a new `tests/test_plugin_manifests.py`:

- All four manifest files (`plugin.json`, `marketplace.json`, `.mcp.json`, `hooks/hooks.json`) parse as valid JSON.
- Each has the expected required keys (`name`, `version`, `description` for `plugin.json`; `plugins` array with `name` + `source` for `marketplace.json`; etc.).
- The MCP command in `.mcp.json` is `castle-mcp`.
- The hook commands in `hooks/hooks.json` reference `${CLAUDE_PLUGIN_ROOT}/hooks/castle_save_hook.sh` and `castle_precompact_hook.sh` (verbatim — no `mempal_*` leftovers).

**Hook smoke tests** in a new (or extended) `tests/test_hooks_smoke.py`:

- Set `CASTLE_DIR` to a `tmp_path`, invoke each renamed `.sh` script with a fixture transcript path, assert exit code 0.
- Confirm the script writes the expected log line under `$HOME/.castle/hook_state/` (use `monkeypatch` to redirect `$HOME`).
- Confirm `CASTLE_DIR` unset path is the documented no-op (single log line, exit 0).

**Manual end-to-end** (documented checklist in spec; not automated):

1. Fresh Claude Code session in any directory: confirm no `mcp__cognitive-castle__*` tools.
2. Run `castle install-claude` → run printed slash commands → restart Claude Code.
3. `castle install-claude --check` exits 0.
4. New session: tools visible. Run a `castle.search` (or whichever the MCP tool is named), confirm a result returns.
5. End the session, start a new one: confirm the previous session's transcript was mined into the palace (e.g., `castle status` shows new drawers).

## Open questions for the implementation plan

These deliberately don't block the spec; they're items the implementation plan needs to resolve through experimentation or documentation lookup.

1. **Marketplace ID resolution.** When the user runs `/plugin marketplace add /path/to/cognitive-castle`, what marketplace ID does Claude Code assign? Default to repo dirname? Read from `marketplace.json`? The implementation plan needs to verify so the install printer can interpolate the right `@<id>` in the second slash command.
2. **`$CASTLE_DIR` resolution policy in hooks.** When unset, the options are: (a) silent no-op + log, (b) default to `$CLAUDE_PROJECT_DIR` (the dir Claude Code was invoked from), (c) default to a path stored in `~/.castle/config.json`. Pick one with rationale in the implementation plan.
3. **Version sync mechanism.** Literal version string in `plugin.json` plus a CI test (current spec choice), or a build step that reads `version.py` at install time? Literal+test is simpler and matches how npm packages typically ship; confirm.

## Risk

Low overall.

- The plugin is additive — existing CLI, MCP server, and tests are unchanged. The only behavioral change for existing users is the hook script rename, which only affects users who hand-wired the old `mempal_*.sh` paths into their settings. The renamed scripts have identical behavior modulo the env-var name and rebranded log lines.
- The `castle install-claude` command is a verifier; it cannot break an existing install because it doesn't mutate state.
- The marketplace mechanism is documented and used by every plugin shipped via `claude-plugins-official`. Risk of "Claude Code rejects our manifest" is bounded by the validation tests.
- Reversible via `git revert` and `/plugin uninstall`.

## Acceptance criteria

1. New files exist with the contents specified above.
2. Hook scripts are renamed; greps for `mempal_save_hook\|mempal_precompact_hook\|MEMPAL_DIR` across the repo return zero matches.
3. `castle install-claude` runs successfully in a clean checkout after `pip install -e ".[dev]"`, prints the two slash commands with the correct repo path.
4. After the user runs the slash commands and restarts Claude Code, `castle install-claude --check` exits 0.
5. In a new Claude Code session, the agent reports that Cognitive Castle MCP tools are available (exact namespace prefix is determined by Claude Code's plugin/MCP integration; verify by asking the agent or inspecting the tool list).
6. After a Stop event, the session transcript appears in the palace (verifiable via `castle status` or equivalent).
7. All new unit and manifest tests pass; existing tests still pass.
