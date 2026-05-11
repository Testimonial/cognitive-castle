# Cognitive Castle — Claude Code Plugin (Phase 1: revive the existing scaffolding)

**Date:** 2026-05-10
**Branch target:** develop
**Status:** Revised after the original premise (no plugin existed) was found wrong. See "Background — what changed" below.
**Scope:** Make the existing but stale `.claude-plugin/` scaffolding actually work for personal use. MCP server + auto-save hooks. Bundle in the plugin-internal rebrand (`mempalace` → `castle`) since the existing files are referenced by tests that already pin the desired post-rebrand behavior. No SessionStart context injection, no marketplace publishing, no Windows.

## Background — what changed from the previous spec

The first version of this spec (commit `b122f43`) said the plugin scaffolding had to be created. That was wrong. A complete `.claude-plugin/` directory already exists in the repo, untouched by the rebrand commits. Every file inside it is stale (`mempalace`-branded, references the missing `mempalace-mcp` command, mentions ChromaDB instead of LanceDB, etc.). As written, the plugin would fail to load: the MCP server entry points at a command that no longer exists, and the hook wrappers shell out to a Python module (`mempalace`) that has been renamed to `cognitive_castle`.

The actual Phase 1 work is to **revive the dead plugin** by completing the rebrand inside `.claude-plugin/`, fixing one half-finished TDD-red test, and removing two pieces of orphaned legacy. The `castle install-claude` CLI proposed in the previous spec is dropped — the plugin already ships a `/castle:init` slash command that does the same job via the existing skill/instructions infrastructure.

## Goals

1. After running `/plugin marketplace add /home/lbihari/cognitive-castle` and `/plugin install castle@cognitive-castle` inside Claude Code (then restarting), a fresh session has Castle's MCP tools available and the Stop / PreCompact hooks fire correctly.
2. Every file under `.claude-plugin/` matches current code reality: `castle` / `castle-mcp` CLI commands, `cognitive_castle` Python package, LanceDB backend, current author / repo URL.
3. The half-finished test `tests/test_claude_plugin_hook_wrappers.py` is finished — its `cognitive-castle` expectations are reconciled with what pyproject actually ships (`castle`), and the wrapper scripts pass it.
4. Orphaned legacy at the top-level `hooks/` directory is cleaned up so users have one canonical install path (the plugin), not two.

## Non-goals

- Marketplace publishing (Phase 2; out of this spec).
- SessionStart context injection.
- Windows hook compatibility.
- The CLAUDE.md doc refresh (separate spec at commit `6533e32`; resumes after this work).
- Full source-code rebrand of `MempalaceConfig`, `~/.mempalace/` paths in `cognitive_castle/`. Still deferred. *Inside* `.claude-plugin/` and the plugin-related test/hook files, however, the rebrand is in scope, because those files already pin post-rebrand behavior in tests.
- A new `castle install-claude` CLI verifier. Dropped — `/castle:init` already exists.

## Source of truth (current state)

Verified by reading the files:

- `pyproject.toml:33-35` ships `castle = cognitive_castle.cli:main` and `castle-mcp = cognitive_castle.mcp_server:main`. **There is no `cognitive-castle` CLI command** even though `pyproject.toml:2` names the package `cognitive-castle`.
- `.claude-plugin/plugin.json` declares `name: "mempalace"`, `mcpServers.mempalace.command: "mempalace-mcp"` (which does not exist on `$PATH` after `pip install -e .`), `keywords: [..., "chromadb", ...]`, `repository: "https://github.com/MemPalace/mempalace"`.
- `.claude-plugin/marketplace.json` declares `name: "mempalace"`, `owner: "milla-jovovich"`, `plugins[0].source: "./.claude-plugin"`, `version: "3.3.3"`.
- `.claude-plugin/.mcp.json` exists separately and duplicates `plugin.json`'s `mcpServers` block (`{"mempalace": {"command": "mempalace-mcp"}}`). Whether Claude Code reads both, one, or treats the inline one as canonical is *not verified*; see Open Questions.
- `.claude-plugin/hooks/hooks.json` references `mempal-stop-hook.sh` and `mempal-precompact-hook.sh` via `${CLAUDE_PLUGIN_ROOT}/hooks/`.
- `.claude-plugin/hooks/mempal-stop-hook.sh` and `mempal-precompact-hook.sh` are thin wrappers that try `mempalace` on `$PATH` first, then `python3 -m mempalace`, then `python -m mempalace`, then error out with `"could not find a runnable mempalace command or module"`.
- `.claude-plugin/skills/mempalace/SKILL.md` declares `name: mempalace` and tells the agent to run `mempalace instructions <command>`.
- `.claude-plugin/commands/{help,init,mine,search,status}.md` each say `Invoke the generic mempalace skill (using the Skill tool)`. They become slash commands `/<plugin-name>:<command-name>` once the plugin is loaded.
- `.claude-plugin/README.md` documents `claude plugin marketplace add MemPalace/mempalace` and `/mempalace:init`. Mentions ChromaDB and `MEMPAL_DIR`.
- `tests/test_claude_plugin_hook_wrappers.py` has `SCRIPT_CASES = [("mempal-stop-hook.sh", "stop"), ("mempal-precompact-hook.sh", "precompact")]` and expects the wrapper to invoke `cognitive-castle hook run --hook stop --harness claude-code` first (line 82, 100), but its fallback test expects `python -m mempalace` (line 131) and its error-message test expects `"could not find a runnable mempalace command or module"` (line 147). The test is half-rebranded.
- `hooks/mempal_save_hook.sh` and `hooks/mempal_precompact_hook.sh` (top-level, underscore-named) are the *legacy* fat shell scripts from before the Python `castle hook run` command existed. They embed all logic inline. The plugin uses the dash-named thin wrappers in `.claude-plugin/hooks/` instead. The top-level `hooks/README.md` documents the legacy manual install and is also stale.
- `cognitive_castle/instructions/init.md` exists and is what `/castle:init` will surface to the agent.

## Naming decisions (made in this spec — change if you disagree during review)

These all need to land consistently across plugin manifest, marketplace listing, slash commands, skill, hook wrappers, and tests. Picking now to avoid drift.

1. **Plugin name in manifests: `castle`** (not `cognitive-castle`).
   - Rationale: matches pyproject's CLI script name (`castle`), keeps slash commands short (`/castle:init` vs `/cognitive-castle:init`), matches how an end user thinks of the tool.
   - The Python *package* name (`cognitive-castle` on PyPI / in pyproject) stays unchanged. Two namespaces: package = `cognitive-castle`, plugin = `castle`. Same pattern as npm packages with short CLI names.
2. **Slash command namespace: `/castle:<verb>`** (follows from #1).
3. **Hook wrapper script names: `castle-stop-hook.sh`, `castle-precompact-hook.sh`** (preserve the dash convention already established in `.claude-plugin/hooks/`).
4. **Hook wrapper primary CLI invocation: `castle hook run`** (matches pyproject's installed script). Update the test from `"cognitive-castle"` to `"castle"` to match.
5. **Hook wrapper Python module fallback: `python -m cognitive_castle`** (matches the renamed Python package). Update the test from `"-m mempalace"` to `"-m cognitive_castle"`.
6. **Skill directory: `.claude-plugin/skills/castle/SKILL.md`** with `name: castle` (renamed from `mempalace`).
7. **Marketplace listing: `name: "castle"`, `source: "./.claude-plugin"`, `owner.name: "Ladislav Bihari"`, `owner.url: "https://github.com/<your-fork>"`** — actual GitHub URL TBD per #Open-Questions.
8. **Plugin manifest `mcpServers` entry: `{"castle": {"command": "castle-mcp"}}`** — server name and command both updated.

## File-by-file change list

### `.claude-plugin/plugin.json`

Replace contents with:

```json
{
  "name": "castle",
  "version": "3.3.3",
  "description": "Cognitive Castle — persistent verbatim memory for Claude Code agents. LanceDB-backed local search, MCP tools, auto-save hooks. Local-first, no API keys required.",
  "author": { "name": "Ladislav Bihari" },
  "license": "MIT",
  "commands": [],
  "mcpServers": {
    "castle": { "command": "castle-mcp" }
  },
  "keywords": ["memory", "ai", "mcp", "lancedb", "palace", "search", "verbatim"],
  "repository": "<github URL of your fork — see Open Questions>"
}
```

Drop `chromadb` and `rag` keywords (the user has deliberately rejected the RAG framing for this project).

### `.claude-plugin/marketplace.json`

Replace contents with:

```json
{
  "name": "cognitive-castle",
  "owner": {
    "name": "Ladislav Bihari",
    "url": "<github URL of your fork — see Open Questions>"
  },
  "plugins": [
    {
      "name": "castle",
      "source": "./.claude-plugin",
      "description": "Persistent verbatim memory for Claude Code agents — LanceDB-backed, local-first.",
      "version": "3.3.3",
      "author": { "name": "Ladislav Bihari" }
    }
  ]
}
```

Note: marketplace name (`cognitive-castle`) is intentionally different from plugin name (`castle`) — the marketplace is the container; the plugin inside it is one of potentially several. This matches how `claude-plugins-official` is the marketplace and `superpowers`, `context7`, etc. are individual plugins inside.

### `.claude-plugin/.mcp.json`

Two options, picking based on Open Question #1:
- If the inline `mcpServers` in `plugin.json` is the canonical mechanism: **delete this file** as redundant.
- If `.mcp.json` is canonical: **update its content** to `{"castle": {"command": "castle-mcp"}}` and delete the `mcpServers` block from `plugin.json`.

The implementation plan resolves this by checking what other plugins do and/or testing both forms in a sandbox. As an interim safety, **keep both files but make them consistent** until verified.

### `.claude-plugin/hooks/hooks.json`

Replace contents with:

```json
{
  "description": "Cognitive Castle auto-save and pre-compact hooks",
  "hooks": {
    "Stop": [
      { "hooks": [{ "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/castle-stop-hook.sh\"" }] }
    ],
    "PreCompact": [
      { "hooks": [{ "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/castle-precompact-hook.sh\"" }] }
    ]
  }
}
```

### `.claude-plugin/hooks/mempal-stop-hook.sh` → `castle-stop-hook.sh`

Rename the file. Replace contents with:

```bash
#!/bin/bash
# Cognitive Castle Stop Hook — thin wrapper calling Python CLI.
# All logic lives in cognitive_castle.hooks_cli for cross-harness extensibility.
run_castle_hook() {
  if command -v castle >/dev/null 2>&1; then
    castle hook run "$@"
    return $?
  fi

  if command -v python3 >/dev/null 2>&1 && python3 -c "import cognitive_castle" >/dev/null 2>&1; then
    python3 -m cognitive_castle hook run "$@"
    return $?
  fi

  if command -v python >/dev/null 2>&1 && python -c "import cognitive_castle" >/dev/null 2>&1; then
    python -m cognitive_castle hook run "$@"
    return $?
  fi

  echo "Cognitive Castle hook error: could not find a runnable castle command or cognitive_castle module" >&2
  return 1
}

run_castle_hook --hook stop --harness claude-code
```

### `.claude-plugin/hooks/mempal-precompact-hook.sh` → `castle-precompact-hook.sh`

Same as above, but the last line is `run_castle_hook --hook precompact --harness claude-code`.

### `.claude-plugin/skills/mempalace/` → `.claude-plugin/skills/castle/`

Rename the directory. Update `SKILL.md` content:

```markdown
---
name: castle
description: Cognitive Castle — mine projects and conversations into a searchable memory palace. Use when asked about castle, cognitive castle, memory palace, mining memories, searching memories, or palace setup.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Cognitive Castle

A persistent verbatim memory palace for AI — mine projects and conversations, then search them locally with LanceDB. No vector DB to host, no API keys required.

## Prerequisites

Ensure `castle` is installed:

```bash
castle --version
```

If not installed:

```bash
pip install cognitive-castle
```

## Usage

Cognitive Castle provides dynamic instructions via the CLI. To get instructions for any operation:

```bash
castle instructions <command>
```

Where `<command>` is one of: `help`, `init`, `mine`, `search`, `status`.

Run the appropriate instructions command, then follow the returned instructions step by step.
```

### `.claude-plugin/commands/*.md`

Each of `help.md`, `init.md`, `mine.md`, `search.md`, `status.md` has its body line `Invoke the generic mempalace skill (using the Skill tool) with the X command, then follow its instructions.` Update each to `Invoke the generic castle skill (using the Skill tool) with the X command, then follow its instructions.`. Also rebrand each frontmatter `description` field from `MemPalace` to `Cognitive Castle`.

### `.claude-plugin/README.md`

Rewrite for the rebrand. Key changes:
- Title: `# Cognitive Castle Claude Code Plugin`
- Description: drop ChromaDB; mention LanceDB and "local-first, no API keys".
- Installation: `claude plugin marketplace add <user-fork-url>` / `claude plugin install --scope user castle`.
- Slash commands table: rename `/mempalace:*` → `/castle:*`.
- Hooks section: replace `MEMPAL_DIR` with `CASTLE_DIR`.
- MCP server section: "19 MCP tools" — verify the count is still accurate against `cognitive_castle/mcp_server.py`; update if changed.

### `tests/test_claude_plugin_hook_wrappers.py`

Three updates:
1. `SCRIPT_CASES` list at line 19-22: rename script filenames to `castle-stop-hook.sh` / `castle-precompact-hook.sh`.
2. Line 82: the `cognitive-castle` stub command is renamed to `castle` (matching the wrapper's primary CLI invocation).
3. Line 131: the fallback expectation `-m mempalace hook run ...` becomes `-m cognitive_castle hook run ...`.
4. Line 147: error message check `"could not find a runnable mempalace command or module"` becomes `"could not find a runnable castle command or cognitive_castle module"`.

After these updates, the test passes against the rebranded wrappers.

### Top-level `hooks/` cleanup

The legacy fat scripts at `hooks/mempal_save_hook.sh` and `hooks/mempal_precompact_hook.sh` are orphaned post-plugin. The plugin uses the thin wrappers in `.claude-plugin/hooks/`. Two options:

- **Decision: delete the legacy scripts.** Single canonical install path (the plugin). Removes confusion about which script is current.
- Update `hooks/README.md` to point users at the plugin install instead of the manual hand-edit instructions. Or delete `hooks/README.md` along with the scripts.

If a user has manually wired the old paths into their `~/.claude/settings.json`, deletion silently breaks them. Mitigation: include a CHANGELOG note. (No multi-user concern given Phase 1 is personal-use.)

### Tests that touch the legacy scripts

Several test files reference the old `mempal_*` scripts:
- `tests/test_hooks_shell.py` — tests the legacy fat shell scripts. If the legacy scripts are deleted, **delete this test file** along with them.
- `tests/test_save_hook_mines.py` — tests the legacy save hook's mining behavior. **Delete with the legacy script** unless the same coverage exists on the Python `cognitive_castle.hooks_cli` path (verify before deleting).
- `tests/test_save_hook_verbose.py` — same. Verify and delete.

### Branding tests

`tests/test_branding.py` likely already covers some of this surface. Verify it asserts the rebranded strings appear (or at least doesn't fail because of the plugin file changes). The implementation plan should run this test after each batch of file changes.

## Runtime data flow

Once the rebranded plugin is installed via the marketplace and Claude Code is restarted:

1. Claude Code reads `enabledPlugins`, finds `castle@cognitive-castle: true`.
2. Loads the marketplace, resolves to the local repo's `.claude-plugin/` path, reads `plugin.json` + `hooks/hooks.json`.
3. Spawns `castle-mcp` per `plugin.json.mcpServers` (or `.mcp.json`, pending Open Question #1). MCP tools become available with namespace prefix determined by Claude Code (typically `mcp__castle__*`).
4. Registers Stop and PreCompact hooks per `hooks/hooks.json`.
5. Slash commands `/castle:help`, `/castle:init`, `/castle:mine`, `/castle:search`, `/castle:status` are registered.
6. During the session: agent calls flow MCP-protocol → `castle-mcp` subprocess → palace operations → JSON results.
7. On Stop event: Claude Code invokes `castle-stop-hook.sh`. Wrapper resolves `castle` command (or falls back to `python -m cognitive_castle`), calls `castle hook run --hook stop --harness claude-code`, which is implemented in `cognitive_castle/hooks_cli.py`.
8. On PreCompact event: same shape with `--hook precompact`.
9. User runs `/castle:init` once after install to complete onboarding (palace creation, etc.).

## Failure modes

| Failure | Surface | Handling |
|---|---|---|
| `castle-mcp` not on `$PATH` | Plugin loads, MCP server fails to start, no tools in session. | User runs `pip install -e ".[dev]"`. The `/castle:init` command surfaces this in its checks (existing behavior). |
| `castle` command not on `$PATH` (hook scripts) | Wrapper falls back to `python -m cognitive_castle`. If that also fails, exits non-zero with the specific error message tested by `test_plugin_hook_wrapper_errors_cleanly_when_no_runner_exists`. | Existing test pins this; rebrand preserves the behavior. |
| Palace not yet initialized | MCP tool returns "no palace" error; `castle hook run` no-ops with a log. | Existing behavior. User runs `/castle:init` or `castle init`. |
| `$CASTLE_DIR` env var unset | `castle hook run` reads `cognitive_castle.hooks_cli` logic which already handles unset / missing dir. (Verify by reading `hooks_cli.py` during implementation; the previous `MEMPAL_DIR` was the *fat-script* env var. The thin wrapper does not pass through env vars; the Python side reads config.) | Implementation plan: confirm Python-side handling exists; if not, add a single graceful-skip code path. |
| User had legacy `hooks/mempal_*.sh` paths in `settings.json` and we delete them | Hook fires, file not found, Claude Code logs error. User's session is otherwise fine (Stop hooks aren't blocking). | CHANGELOG note. Personal-use only — risk is bounded to the user's own machine. |
| `.mcp.json` and `plugin.json` `mcpServers` give conflicting info | Unknown — depends on Claude Code's resolution. | Open Question #1; address before final commit. |

## Testing strategy

**Existing tests to update:**
- `tests/test_claude_plugin_hook_wrappers.py` — four edits per the file-by-file change list above.
- `tests/test_branding.py` — re-run to confirm rebranded strings now appear / mempalace strings don't.
- `tests/test_hooks_shell.py`, `tests/test_save_hook_mines.py`, `tests/test_save_hook_verbose.py` — delete (per legacy script removal).

**New tests:**
- `tests/test_plugin_manifests.py` — assert each of `plugin.json`, `marketplace.json`, `.mcp.json` (if kept), `hooks/hooks.json` parse as valid JSON, have the expected top-level keys, name fields equal `"castle"` (or `"cognitive-castle"` for marketplace), `mcpServers.castle.command` equals `"castle-mcp"`, hook commands reference `castle-stop-hook.sh` and `castle-precompact-hook.sh` only (no `mempal_*` leftovers).
- Version sync test: `plugin.json["version"]` and `marketplace.json["plugins"][0]["version"]` equal `cognitive_castle.version.__version__`.

**Manual end-to-end checklist (documented in spec; not automated):**

1. `pip install -e ".[dev]"`. Confirm `castle --version` works.
2. Inside Claude Code: `/plugin marketplace add /home/lbihari/cognitive-castle` then `/plugin install castle@cognitive-castle`. Restart Claude Code.
3. New session: confirm `/castle:help`, `/castle:init`, etc. visible. Confirm Castle MCP tools visible to the agent (ask).
4. Run `/castle:init` to complete palace onboarding.
5. End the session, start a new one: confirm transcript was mined (run `castle status` or `/castle:status`).
6. Trigger PreCompact (let context fill or use a debug command if available); confirm precompact hook fired.

## Open questions for the implementation plan

1. **`.mcp.json` vs `plugin.json.mcpServers` redundancy.** Pick one as canonical; delete or align the other. Resolve by reading Claude Code documentation and/or testing both forms. **Implementation plan should resolve this before committing manifest changes** since the wrong choice silently breaks MCP server loading.
2. **Repository / marketplace owner URL.** The current `marketplace.json` says `https://github.com/MemPalace`; you've forked the project. What's the fork URL to put here? (Both `plugin.json.repository` and `marketplace.json.owner.url` need it.) The implementation plan should ask once and then plug it in everywhere.
3. **`$CASTLE_DIR` handling in `cognitive_castle.hooks_cli`.** The wrapper no longer references the env var; the Python side does. Verify it gracefully handles unset / missing dir; if not, add the no-op-with-log path. (Likely already handled; verify before assuming.)
4. **MCP tool count in `.claude-plugin/README.md`.** Current text says "19 MCP tools". Verify against `cognitive_castle/mcp_server.py` and update if changed. Trivial check during implementation.
5. **Marketplace ID after `/plugin marketplace add`.** Whether Claude Code uses the directory name, the `marketplace.json.name`, or something else as the ID for the second slash command (`/plugin install castle@<id>`). Verify once and document in `.claude-plugin/README.md`.

## Risk

- **Medium.** This is a focused rebrand of files that already exist plus deletion of legacy scripts. The blast radius is the plugin install path and four test files. Reversible via `git revert`.
- **Highest single risk:** Open Question #1 (`.mcp.json` vs `plugin.json.mcpServers`). A wrong call here means the plugin appears to install but tools don't surface. The implementation plan must resolve this before final commit, ideally by verifying against another working plugin's structure.
- **Lower risks:** legacy script deletion (only a problem if user wired the old paths in — they did not, per the audit of `~/.claude/settings.json`); skill/command rename (slash command path change — user has to relearn `/castle:init` vs `/mempalace:init`; trivial).

## Acceptance criteria

1. Every file under `.claude-plugin/` reads as if newly written for "castle / cognitive_castle / LanceDB" — `grep -rn "mempal\|MemPalace\|mempalace" .claude-plugin/` returns zero matches.
2. `tests/test_claude_plugin_hook_wrappers.py` passes after wrapper renames + content updates.
3. `tests/test_branding.py` passes (no mempalace-related regressions).
4. `tests/test_plugin_manifests.py` (new) passes, asserting structural contracts on the plugin files.
5. Manual end-to-end (above checklist) succeeds: plugin loads, slash commands appear, MCP tools appear in a fresh session, hooks fire on Stop and PreCompact.
6. Top-level `hooks/mempal_*.sh` and corresponding tests are deleted; `hooks/README.md` updated to point at the plugin install OR also deleted.
7. `git status` clean after a full test suite run.
