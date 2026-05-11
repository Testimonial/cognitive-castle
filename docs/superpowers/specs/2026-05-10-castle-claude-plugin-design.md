# Cognitive Castle — Claude Code Plugin + Rebrand Completion (Phase 1)

**Date:** 2026-05-10
**Last revised:** 2026-05-11 (scope expanded after the SOTA retrieval upgrade landed)
**Branch target:** develop
**Status:** Phase 2 revision. Original spec (b122f43) said the plugin scaffolding had to be created — wrong; it existed. First revision (4084e93) reframed as revival of the dead plugin. This revision (current) **expands scope** to also include the env-var rename, hook state-dir migration, `MempalaceConfig` class rename, and a documentation sweep — the leftovers from the MemPalace → Cognitive Castle rebrand that the first revision deliberately deferred.

**Scope:** Make the existing but stale `.claude-plugin/` scaffolding actually work for personal use (MCP server + auto-save hooks), AND complete the source-code rebrand from MemPalace to Cognitive Castle everywhere except the live palace data directory. Personal-use only. No marketplace publishing, no SessionStart context injection, no Windows.

## Background — what changed from the previous revision

The previous revision (`4084e93`) was correctly scoped to "revive the dead plugin." During the SOTA retrieval upgrade work (PR #2, merged), it became clear that the legacy rebrand drift was wider than the plugin scaffolding alone:

- `cognitive_castle/hooks_cli.py` reads `MEMPAL_DIR`, `MEMPAL_PYTHON`, `MEMPAL_VERBOSE` env vars directly (~5 places).
- `cognitive_castle/hooks_cli.py` (and the legacy shell scripts about to be deleted) reference `~/.mempalace/hook_state/` as the state directory.
- The main config class is still `MempalaceConfig`.
- ~80 source/doc files still use "MemPalace" / "mempalace" in headers, instruction text, and the package README.

The plugin spec touches the plugin manifest layer cleanly, but leaves these deeper references in place. Lifting them now (with a backward-compat shim where appropriate) finishes the rebrand without doubling the work later.

## Goals

1. After `/plugin marketplace add /home/lbihari/cognitive-castle` and `/plugin install castle@cognitive-castle` (then restart), a fresh Claude Code session has Castle's MCP tools and Stop / PreCompact hooks wired correctly.
2. Every file under `.claude-plugin/` matches current code reality (no `mempalace` / `mempalace-mcp` / ChromaDB references).
3. The half-finished `tests/test_claude_plugin_hook_wrappers.py` is finished — its `cognitive-castle` expectations are reconciled with what pyproject actually ships (`castle`).
4. Orphaned legacy at the top-level `hooks/` directory is deleted so there is one canonical install path (the plugin), not two.
5. `MEMPAL_DIR` / `MEMPAL_PYTHON` / `MEMPAL_VERBOSE` env vars in `cognitive_castle/hooks_cli.py` are renamed to `CASTLE_DIR` / `CASTLE_PYTHON` / `CASTLE_VERBOSE`, with a backward-compat read-shim so users with the legacy names set in their environment keep working (with a one-time stderr deprecation log per process).
6. Hook state directory default is moved from `~/.mempalace/hook_state/` to `~/.castle/hook_state/`. On first read: if the new dir does not exist but the old one does, read from the old location and log a one-time migration note. New writes always go to the new dir. No data movement.
7. `MempalaceConfig` is renamed to `CognitiveCastleConfig`, with `MempalaceConfig = CognitiveCastleConfig` as a backward-compat alias. All internal callers updated to use the new name.
8. Module-level docstrings, comments, instruction markdown, and the package README are swept to replace "MemPalace" → "Cognitive Castle" and "mempalace" → "castle" / "cognitive_castle" depending on context.

## Non-goals

- Marketplace publishing (Phase 2; out of this spec).
- SessionStart context injection.
- Windows hook compatibility.
- The CLAUDE.md doc refresh (separate spec at commit `6533e32`; resumes after this work).
- **Live palace data path migration.** The user has real palace data at `~/.mempalace/palace/`. Renaming that path requires its own design (detect old palace, prompt user, atomic migration with rollback). Out of scope here; tracked as a future spec.
- Test code rebrand: ~89 `os.environ.get("MEMPAL_DIR")` / `patch.dict({"MEMPAL_DIR": ...})` references in test code keep working via the shim. A future "test cleanup" sweep can rename them, but it is not blocking.

## Source of truth (current state, verified by reading the files)

### Plugin scaffolding state

- `pyproject.toml:33-35` ships `castle` and `castle-mcp` entry points. There is no `cognitive-castle` CLI command despite the package name being `cognitive-castle`.
- `.claude-plugin/plugin.json` declares `name: "mempalace"`, `mcpServers.mempalace.command: "mempalace-mcp"`, `keywords: [..., "chromadb", ...]`, `repository: "https://github.com/MemPalace/mempalace"`.
- `.claude-plugin/marketplace.json` declares `name: "mempalace"`, `owner.name: "milla-jovovich"`, `plugins[0].source: "./.claude-plugin"`, `version: "3.3.3"`.
- `.claude-plugin/.mcp.json` duplicates the `mcpServers` block from `plugin.json`. Which Claude Code reads is unverified.
- `.claude-plugin/hooks/hooks.json` references `mempal-stop-hook.sh` and `mempal-precompact-hook.sh`.
- `.claude-plugin/hooks/mempal-stop-hook.sh` / `mempal-precompact-hook.sh` are thin wrappers that try `mempalace` then `python -m mempalace`.
- `.claude-plugin/skills/mempalace/SKILL.md` and `.claude-plugin/commands/*.md` reference the `mempalace` skill name.
- `.claude-plugin/README.md` documents the legacy install path and mentions ChromaDB + `MEMPAL_DIR`.
- `tests/test_claude_plugin_hook_wrappers.py` is half-rebranded: expects `cognitive-castle` as the primary CLI command, but its fallback test still expects `python -m mempalace` and its error-message test still references `"mempalace command or module"`.

### Source-code legacy drift

- `cognitive_castle/hooks_cli.py` reads `MEMPAL_DIR` directly via `os.environ.get("MEMPAL_DIR", "")` in multiple places, and references `~/.mempalace/hook_state` for the state directory.
- `MempalaceConfig` is defined in `cognitive_castle/config.py` and re-exported via `tests/conftest.py` (line 33).
- ~89 test files patch `MEMPAL_DIR` in `os.environ` or reference legacy mock paths. Already validated that tests pass with the env-var shim; no test changes required for correctness.
- ~80 source/doc files still contain "MemPalace" or "mempalace" in docstrings, instructions, or README content.

### Top-level legacy

- `hooks/mempal_save_hook.sh` and `hooks/mempal_precompact_hook.sh` are pre-plugin fat shell scripts. The plugin replaces them (the dash-named thin wrappers in `.claude-plugin/hooks/` do the same job through `castle hook run`).
- `hooks/README.md` documents the legacy manual-install path. Stale.
- `tests/test_hooks_shell.py`, `tests/test_save_hook_mines.py`, `tests/test_save_hook_verbose.py` test the legacy fat scripts directly.

## Naming decisions

Settled in the prior revision; carried forward unchanged:

1. **Plugin name in manifests:** `castle` (not `cognitive-castle`). Matches pyproject's CLI script. Keeps slash commands short (`/castle:init`).
2. **Slash command namespace:** `/castle:<verb>`.
3. **Hook wrapper script names:** `castle-stop-hook.sh`, `castle-precompact-hook.sh` (dash convention).
4. **Hook wrapper primary CLI invocation:** `castle hook run`.
5. **Hook wrapper Python module fallback:** `python -m cognitive_castle`.
6. **Skill directory:** `.claude-plugin/skills/castle/SKILL.md` with `name: castle`.
7. **Marketplace listing:** `name: "cognitive-castle"`, `plugins[0].name: "castle"`, `owner.name: "Ladislav Bihari"`, `owner.url: <fork URL>` (Open Question).
8. **Plugin manifest `mcpServers` entry:** `{"castle": {"command": "castle-mcp"}}`.

New for this revision:

9. **Python class:** `CognitiveCastleConfig`, with `MempalaceConfig = CognitiveCastleConfig` alias kept indefinitely (no deprecation log on this one — class imports are programmatic, harder to migrate, low cost to keep).
10. **Env vars:** `CASTLE_DIR`, `CASTLE_PYTHON`, `CASTLE_VERBOSE`. Legacy `MEMPAL_*` names read as fallback with one-time stderr deprecation log.
11. **Hook state dir:** `~/.castle/hook_state/`. Old `~/.mempalace/hook_state/` read as fallback if new doesn't exist (one-time log); new writes go to new dir.

## File-by-file change list

### Plugin scaffolding (unchanged from prior revision)

[The following sections are unchanged in scope from commit 4084e93 — `.claude-plugin/plugin.json`, `marketplace.json`, `.mcp.json`, `hooks/hooks.json`, the two renamed plugin wrapper scripts, the skill, the slash-command markdowns, and the plugin README. Refer to the previous revision text; no changes here.]

### `.claude-plugin/plugin.json`

```json
{
  "name": "castle",
  "version": "3.3.3",
  "description": "Cognitive Castle — persistent verbatim memory for Claude Code agents. LanceDB-backed local search, MCP tools, auto-save hooks. Local-first, no API keys required.",
  "author": { "name": "Ladislav Bihari" },
  "license": "MIT",
  "commands": [],
  "mcpServers": { "castle": { "command": "castle-mcp" } },
  "keywords": ["memory", "ai", "mcp", "lancedb", "palace", "search", "verbatim"],
  "repository": "<github URL of your fork — see Open Questions>"
}
```

Drop `chromadb` and `rag` keywords.

### `.claude-plugin/marketplace.json`

```json
{
  "name": "cognitive-castle",
  "owner": { "name": "Ladislav Bihari", "url": "<fork URL — Open Questions>" },
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

### `.claude-plugin/.mcp.json`

Keep both files consistent until Open Question #1 resolves which is canonical: `{"castle": {"command": "castle-mcp"}}`.

### `.claude-plugin/hooks/hooks.json`

```json
{
  "description": "Cognitive Castle auto-save and pre-compact hooks",
  "hooks": {
    "Stop": [{ "hooks": [{ "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/castle-stop-hook.sh\"" }] }],
    "PreCompact": [{ "hooks": [{ "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/castle-precompact-hook.sh\"" }] }]
  }
}
```

### `.claude-plugin/hooks/mempal-stop-hook.sh` → `castle-stop-hook.sh` (rename + rewrite)

```bash
#!/bin/bash
# Cognitive Castle Stop Hook — thin wrapper calling the Python CLI.
run_castle_hook() {
  if command -v castle >/dev/null 2>&1; then castle hook run "$@"; return $?; fi
  if command -v python3 >/dev/null 2>&1 && python3 -c "import cognitive_castle" >/dev/null 2>&1; then python3 -m cognitive_castle hook run "$@"; return $?; fi
  if command -v python  >/dev/null 2>&1 && python  -c "import cognitive_castle" >/dev/null 2>&1; then python  -m cognitive_castle hook run "$@"; return $?; fi
  echo "Cognitive Castle hook error: could not find a runnable castle command or cognitive_castle module" >&2
  return 1
}
run_castle_hook --hook stop --harness claude-code
```

### `.claude-plugin/hooks/mempal-precompact-hook.sh` → `castle-precompact-hook.sh`

Same as above, last line uses `--hook precompact`.

### `.claude-plugin/skills/mempalace/` → `.claude-plugin/skills/castle/`

Rename directory. Update `SKILL.md` frontmatter `name: castle`, body says "Cognitive Castle", `pip install cognitive-castle`, `castle instructions <command>`.

### `.claude-plugin/commands/*.md`

Each of `help.md`, `init.md`, `mine.md`, `search.md`, `status.md`: body line changes from `Invoke the generic mempalace skill` to `Invoke the generic castle skill`. Frontmatter `description` rebranded.

### `.claude-plugin/README.md`

Title, install commands, `/castle:*` slash command table, hooks section (`MEMPAL_DIR` → `CASTLE_DIR`), MCP tool count verified against `cognitive_castle/mcp_server.py`.

### `tests/test_claude_plugin_hook_wrappers.py`

- `SCRIPT_CASES`: filenames updated to `castle-stop-hook.sh` / `castle-precompact-hook.sh`.
- Line 82: `cognitive-castle` stub → `castle`.
- Line 131: `-m mempalace` → `-m cognitive_castle`.
- Line 147: error message check → `"could not find a runnable castle command or cognitive_castle module"`.

### Top-level legacy script deletion

Delete:
- `hooks/mempal_save_hook.sh`
- `hooks/mempal_precompact_hook.sh`
- `hooks/README.md` (or rewrite to point at the plugin install)
- `tests/test_hooks_shell.py`
- `tests/test_save_hook_mines.py`
- `tests/test_save_hook_verbose.py`

Rationale: the plugin replaces them. Single canonical install path. CHANGELOG note for users who may have manually wired the old paths into `~/.claude/settings.json`.

### NEW: Env-var rename with backward-compat shim

**Files:** `cognitive_castle/hooks_cli.py` primarily; minor sweeps elsewhere.

Add a helper near the top of `cognitive_castle/hooks_cli.py`:

```python
_DEPRECATED_LEGACY_ENV_WARNED: set[str] = set()

def _read_castle_env(new_name: str, old_name: str, default: str = "") -> str:
    """Read CASTLE_* env var; fall back to legacy MEMPAL_* with one-time deprecation log."""
    new_val = os.environ.get(new_name)
    if new_val is not None:
        return new_val
    old_val = os.environ.get(old_name)
    if old_val is not None:
        if old_name not in _DEPRECATED_LEGACY_ENV_WARNED:
            _DEPRECATED_LEGACY_ENV_WARNED.add(old_name)
            sys.stderr.write(
                f"[castle] WARNING: {old_name} is deprecated; rename to {new_name}.\n"
            )
        return old_val
    return default
```

Replace every direct `os.environ.get("MEMPAL_DIR", ...)` / `os.environ.get("MEMPAL_PYTHON", ...)` / `os.environ.get("MEMPAL_VERBOSE", ...)` in `cognitive_castle/hooks_cli.py` with the corresponding `_read_castle_env(...)` call. Inventory at implementation time via `grep -n "MEMPAL_DIR\|MEMPAL_PYTHON\|MEMPAL_VERBOSE" cognitive_castle/hooks_cli.py`.

User-visible docs that mention env vars (e.g., `cognitive_castle/instructions/*.md`, package README, `.claude-plugin/README.md`) now refer to the new names. Legacy names mentioned only in a "Backward compatibility" subsection.

### NEW: Hook state directory migration

**Files:** `cognitive_castle/hooks_cli.py`.

Replace the hardcoded `~/.mempalace/hook_state` with a helper:

```python
def _state_dir() -> Path:
    """Return the hook state directory, migrating from the legacy path if needed."""
    new = Path.home() / ".castle" / "hook_state"
    old = Path.home() / ".mempalace" / "hook_state"
    if new.exists():
        return new
    if old.exists():
        if "state_dir_migration" not in _DEPRECATED_LEGACY_ENV_WARNED:
            _DEPRECATED_LEGACY_ENV_WARNED.add("state_dir_migration")
            sys.stderr.write(
                f"[castle] NOTE: reading legacy state dir {old}; new writes go to {new}.\n"
            )
        return old
    new.mkdir(parents=True, exist_ok=True)
    return new
```

All callers use `_state_dir()` instead of `Path.home() / ".mempalace" / "hook_state"`. New writes always go to the new dir (the helper creates it). Legacy dir never written to. Old data left in place; the user can delete it manually once they verify nothing depends on it.

### NEW: `MempalaceConfig` → `CognitiveCastleConfig` rename

**Files:** `cognitive_castle/config.py`, plus every internal caller.

In `cognitive_castle/config.py`, rename the class definition:

```python
class CognitiveCastleConfig:
    # ... existing body unchanged
    ...

# Backward-compat alias. Programmatic users still importing the old name keep working.
MempalaceConfig = CognitiveCastleConfig
```

Find and update every internal `MempalaceConfig` reference to `CognitiveCastleConfig`:

```
grep -rln "MempalaceConfig" cognitive_castle/ tests/
```

For each file:
- Production code (`cognitive_castle/`): rename usage to `CognitiveCastleConfig`.
- Tests (`tests/`): rename to `CognitiveCastleConfig`. (The shim alias means tests would still work unchanged, but for internal consistency we update them.)

The alias on `MempalaceConfig` stays — external callers (if any) keep working.

### NEW: Documentation sweep (~80 files)

Mechanical search/replace:
- "MemPalace" → "Cognitive Castle"
- "mempalace" (where it refers to the project/CLI/package brand, not a Python module path) → "castle" (when referring to the CLI) or "cognitive_castle" (when referring to the Python module)

Files in scope:
- `cognitive_castle/README.md` (package readme)
- `cognitive_castle/instructions/*.md` (slash-command instruction text)
- Module-level docstrings in `cognitive_castle/*.py` headers
- Any inline comments / log strings still saying "MemPalace"

NOT in scope (cosmetic but outside this PR):
- `docs/` historical RFCs / plans / specs — those are historical documents; leave them as written.
- `CHANGELOG.md` — historical entries are factual.
- `website/` (if present) — could be a separate sweep.

The implementation plan inventories the actual file list via `grep -rln "MemPalace\|mempalace" cognitive_castle/ --include="*.py" --include="*.md"` and walks them in batches with verification between batches.

## Backward compatibility / migration story

Everything user-facing keeps working:

| Legacy | New | Behavior |
|---|---|---|
| `MEMPAL_DIR` env var | `CASTLE_DIR` | Both read; CASTLE wins; legacy logs deprecation once per process |
| `MEMPAL_PYTHON` env var | `CASTLE_PYTHON` | Same |
| `MEMPAL_VERBOSE` env var | `CASTLE_VERBOSE` | Same |
| `~/.mempalace/hook_state/` | `~/.castle/hook_state/` | Read both; write to new; legacy logs migration note once |
| `MempalaceConfig` class | `CognitiveCastleConfig` | Both names work; alias kept indefinitely |
| `hooks/mempal_save_hook.sh` path | (deleted) | If a user had this in `~/.claude/settings.json`, the hook fails to find the file; user updates settings to use the plugin install. CHANGELOG note. |
| `~/.mempalace/palace/` (live data) | unchanged | Out of scope. User keeps their existing palace data path. |

## Runtime data flow (unchanged from prior revision)

Plugin loads → spawns `castle-mcp` → MCP tools available → Stop/PreCompact hooks fire `castle-stop-hook.sh` / `castle-precompact-hook.sh` → wrapper calls `castle hook run --hook <event> --harness claude-code` → `cognitive_castle.hooks_cli` does the work, reading config via the new env-var shim + state dir helper.

## Failure modes

Existing failure modes from the prior revision carry forward (MCP server / hook wrapper / palace not initialized / etc.). New rows:

| Failure | Surface | Handling |
|---|---|---|
| `CASTLE_DIR` and `MEMPAL_DIR` both set | Shim takes `CASTLE_DIR` (no log). | Documented in `_read_castle_env` docstring. |
| Only `MEMPAL_DIR` set | Shim reads it, logs one-time stderr warning. | Documented. User migrates at leisure. |
| Both `~/.castle/hook_state` and `~/.mempalace/hook_state` exist | Helper reads new (more recent). | Documented. Legacy can be deleted by user. |
| Programmatic user imports `from cognitive_castle.config import MempalaceConfig` | Resolves to the alias. Code keeps working. | Alias kept indefinitely. |
| Doc-sweep search/replace touches a string that shouldn't be rebranded (e.g., a URL containing "mempalace") | Spot-checks during implementation catch this. Tests catch behavioral regressions. | Implementation plan walks the file list in batches and runs tests after each batch. |

## Testing strategy

**Existing tests updated** (from prior revision):
- `tests/test_claude_plugin_hook_wrappers.py` — 4 edits.
- `tests/test_branding.py` — re-run; should be greener after the doc sweep, not redder.
- Delete `tests/test_hooks_shell.py`, `tests/test_save_hook_mines.py`, `tests/test_save_hook_verbose.py` (legacy scripts gone).

**New tests:**
- `tests/test_plugin_manifests.py` — assert plugin.json, marketplace.json, .mcp.json, hooks.json parse and have the expected fields. Version sync with `cognitive_castle.version.__version__`.
- `tests/test_env_var_compat.py` (NEW for this revision) — verify the shim:
  - Set only `CASTLE_DIR` → `_read_castle_env` returns it, no log.
  - Set only `MEMPAL_DIR` → returns it, log written to stderr.
  - Set both → returns `CASTLE_DIR`, no log.
  - Set neither → returns default.
  - Log appears exactly once across multiple calls in the same process.
- `tests/test_state_dir_migration.py` (NEW) — verify the state dir helper:
  - New dir exists → returns new.
  - Old dir exists, new doesn't → returns old, log written.
  - Neither exists → creates new, returns it.

**Existing tests left alone:**
- ~89 test files patching `MEMPAL_DIR`. The shim makes them keep working. A future cleanup PR can rename them.

**Manual end-to-end checklist:**

1. `pip install -e ".[dev]"`. `castle --version` works.
2. `/plugin marketplace add /home/lbihari/cognitive-castle` then `/plugin install castle@cognitive-castle`. Restart Claude Code.
3. Confirm `/castle:help`, `/castle:init`, etc. visible.
4. Confirm Castle MCP tools visible to agent.
5. `/castle:init` completes palace onboarding.
6. End session, start new one: confirm transcript was mined via the new hook path.
7. Trigger PreCompact (let context fill): confirm precompact hook fires.
8. Set `MEMPAL_DIR=/tmp/test` in shell, run a hook: confirm one-time deprecation warning appears.
9. Confirm `~/.castle/hook_state/` exists and is being written to (not `~/.mempalace/hook_state/`).
10. Confirm existing palace at `~/.mempalace/palace/` still loads (path unchanged — out of scope).

## Open questions for the implementation plan

1. **`.mcp.json` vs `plugin.json.mcpServers` redundancy.** Pick canonical, drop the other. Verify against another working plugin or by sandbox test.
2. **Repository / marketplace owner URL.** Fork URL for `plugin.json.repository` and `marketplace.json.owner.url`.
3. **MCP tool count in `.claude-plugin/README.md`.** Verify against `cognitive_castle/mcp_server.py` and update.
4. **Marketplace ID after `/plugin marketplace add`.** Whether Claude Code uses directory name, `marketplace.json.name`, or something else as the ID. Verify and document in README.
5. **Doc-sweep boundaries.** Inventory at implementation time. If file count differs significantly from the ~80 estimate, surface for confirmation. Files like `CHANGELOG.md`, historical specs/plans, `docs/rfcs/*` are explicitly OUT.

## Risk

- **Medium-low.** The shim approach is conservative: no breaking changes for legacy env vars, no class-import breakage, no state data loss. The only genuinely breaking move is deletion of the legacy top-level shell scripts — and the prior audit confirmed those aren't wired into the user's current `~/.claude/settings.json`.
- **Highest single risk:** `.mcp.json` vs `plugin.json.mcpServers` redundancy. Wrong choice silently breaks MCP server loading.
- **Doc-sweep regression risk:** mechanical replace could touch a string that has semantic meaning beyond branding (e.g., a URL fragment). Mitigation: walk in batches and run tests after each batch.

## Acceptance criteria

1. `grep -rn "mempal\|MemPalace\|mempalace" .claude-plugin/` returns zero matches.
2. `tests/test_claude_plugin_hook_wrappers.py` passes against the rebranded wrappers.
3. `tests/test_branding.py` passes (no regressions).
4. `tests/test_plugin_manifests.py` (new) passes.
5. `tests/test_env_var_compat.py` (new) passes.
6. `tests/test_state_dir_migration.py` (new) passes.
7. Top-level `hooks/mempal_*.sh` and three associated test files are deleted.
8. `grep -n "MEMPAL_DIR\|MEMPAL_PYTHON\|MEMPAL_VERBOSE" cognitive_castle/hooks_cli.py` shows references only inside the shim helper + its docstring.
9. `grep -rn "MempalaceConfig" cognitive_castle/` shows references only inside `config.py` (definition + alias).
10. `grep -rln "MemPalace\|mempalace" cognitive_castle/ --include="*.py" --include="*.md"` returns ≤ 5 matches, all in contexts where rebranding would change semantics (e.g., URL fragments, historical comments justifying the rename).
11. Manual end-to-end (above) succeeds.
12. `git status` clean after a full test suite run.
