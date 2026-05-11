# Castle Plugin + Rebrand Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revive the dead Castle Claude Code plugin and complete the source-code rebrand from MemPalace → Cognitive Castle (env vars, state dir, config class, ~80 docstrings/markdown files), without touching live palace data at `~/.mempalace/palace/`.

**Architecture:** Six phases, each fully reversible. Phase 1 adds env-var shim. Phase 2 adds state-dir helper. Phase 3 renames `MempalaceConfig` to `CognitiveCastleConfig` with an alias. Phase 4 rebrands `.claude-plugin/`. Phase 5 deletes legacy top-level shell scripts. Phase 6 sweeps remaining docstrings/markdown. Each task is committable independently; backward-compat shims keep the suite green throughout.

**Tech Stack:** Python 3.9+, sentence-transformers (already integrated), LanceDB (already integrated), pytest + existing fixtures. Plugin manifests are JSON; plugin commands/skill are markdown with frontmatter; hook wrappers are bash.

---

## Reality vs spec deviations to note up front

- **Spec assumes** `cognitive_castle/hooks_cli.py` uses `~/.mempalace/hook_state` and needs migration. **Reality:** `hooks_cli.py:18` already uses `STATE_DIR = Path.home() / ".castle" / "hook_state"`. The `_state_dir()` helper is still added per the spec — it's a defensive abstraction with a one-time legacy-detection log path, but the log will never fire on this machine (verified `~/.mempalace/hook_state` does not exist).
- **Spec lists** "~80 files with MemPalace/mempalace references." **Reality:** `grep -rln "MemPalace\|mempalace" cognitive_castle/ --include="*.py" --include="*.md"` returns 11 files. Doc-sweep scope is correspondingly smaller.
- **Spec lists** "~89 test files patching MEMPAL_DIR." **Reality:** lower count; doesn't change the policy (leave them alone, shim makes them keep working).

These deviations don't change the spec's intent — they make the plan smaller.

---

## File structure

### New files

| File | Lines | Responsibility |
|---|---|---|
| `tests/test_env_var_compat.py` | ~80 | Verifies `_read_castle_env` shim: CASTLE_* precedence, MEMPAL_* fallback with one-time log, no-set returns default. |
| `tests/test_state_dir_migration.py` | ~50 | Verifies `_state_dir()` helper: new exists → returns new; only legacy exists → returns legacy + one-time log; neither → creates new. |
| `tests/test_plugin_manifests.py` | ~80 | Asserts plugin.json, marketplace.json, .mcp.json, hooks/hooks.json parse as valid JSON with expected fields. Version-sync test against `cognitive_castle.version.__version__`. |

### Modified Python source

| File | Change |
|---|---|
| `cognitive_castle/hooks_cli.py` | Add `_read_castle_env` + `_state_dir`. Replace 6 `os.environ.get("MEMPAL_*", ...)` calls. Keep `STATE_DIR = _state_dir()` as the module-level constant (existing callers unchanged). |
| `cognitive_castle/config.py` | Rename `class MempalaceConfig` → `class CognitiveCastleConfig`. Add `MempalaceConfig = CognitiveCastleConfig` alias. |
| `cognitive_castle/backends/lancedb_backend.py` | Update internal references from `MempalaceConfig` to `CognitiveCastleConfig` (5 occurrences). |
| `cognitive_castle/cli.py` | Same — internal `MempalaceConfig` → `CognitiveCastleConfig`. |
| `cognitive_castle/convo_miner.py` | Same. |
| `cognitive_castle/dedup.py` | Same. |
| `cognitive_castle/embedding.py` | Same. |
| `cognitive_castle/fact_checker.py` | Same. |
| `cognitive_castle/layers.py` | Same. |
| `cognitive_castle/palace.py` | Same. |
| `cognitive_castle/palace_graph.py` | Same. |

### Modified plugin manifest files

| File | Change |
|---|---|
| `.claude-plugin/plugin.json` | Replace entire content — name=castle, mcpServers.castle, drop chromadb keyword |
| `.claude-plugin/marketplace.json` | Replace — marketplace name=cognitive-castle, plugins[0].name=castle, owner=Ladislav Bihari |
| `.claude-plugin/.mcp.json` | Update to `{"castle": {"command": "castle-mcp"}}` |
| `.claude-plugin/hooks/hooks.json` | Update to reference renamed scripts |
| `.claude-plugin/hooks/mempal-stop-hook.sh` | **RENAME** to `castle-stop-hook.sh` + rewrite content |
| `.claude-plugin/hooks/mempal-precompact-hook.sh` | **RENAME** to `castle-precompact-hook.sh` + rewrite content |
| `.claude-plugin/skills/mempalace/SKILL.md` | **MOVE** to `.claude-plugin/skills/castle/SKILL.md` + rebrand content |
| `.claude-plugin/commands/help.md` | Rebrand body + frontmatter description |
| `.claude-plugin/commands/init.md` | Same |
| `.claude-plugin/commands/mine.md` | Same |
| `.claude-plugin/commands/search.md` | Same |
| `.claude-plugin/commands/status.md` | Same |
| `.claude-plugin/README.md` | Rebrand title, install commands, slash-command table, hooks section |

### Modified tests

| File | Change |
|---|---|
| `tests/test_claude_plugin_hook_wrappers.py` | SCRIPT_CASES filenames updated; stub command `cognitive-castle` → `castle`; `-m mempalace` → `-m cognitive_castle`; error message check rebranded |

### Deleted

| Path | Reason |
|---|---|
| `hooks/mempal_save_hook.sh` | Legacy fat shell script, orphaned post-plugin |
| `hooks/mempal_precompact_hook.sh` | Same |
| `hooks/README.md` | Documented the legacy manual-install path |
| `tests/test_hooks_shell.py` | Tested the legacy fat scripts directly |
| `tests/test_save_hook_mines.py` | Same |
| `tests/test_save_hook_verbose.py` | Same |

### Doc-sweep targets (`MemPalace` / `mempalace` → `Cognitive Castle` / `castle`)

11 files identified by `grep -rln "MemPalace\|mempalace" cognitive_castle/ --include="*.py" --include="*.md"`. The implementation plan inventories the exact list at Phase 6 start and walks them in two batches: Python docstrings, then markdown files.

---

## Phase 1: Env-var shim

### Task 1: Add `_read_castle_env` helper + tests

**Files:**
- Create: `tests/test_env_var_compat.py`
- Modify: `cognitive_castle/hooks_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_env_var_compat.py`:

```python
"""Tests for _read_castle_env: CASTLE_* with legacy MEMPAL_* fallback."""
import os
from unittest.mock import patch

import pytest

from cognitive_castle.hooks_cli import _read_castle_env, _DEPRECATED_LEGACY_ENV_WARNED


@pytest.fixture(autouse=True)
def _clear_warn_cache():
    """Reset the per-process warning-once cache before each test."""
    _DEPRECATED_LEGACY_ENV_WARNED.clear()
    yield
    _DEPRECATED_LEGACY_ENV_WARNED.clear()


def test_castle_var_set_returns_castle_value(monkeypatch):
    monkeypatch.setenv("CASTLE_DIR", "/path/from/new")
    monkeypatch.delenv("MEMPAL_DIR", raising=False)
    assert _read_castle_env("CASTLE_DIR", "MEMPAL_DIR") == "/path/from/new"


def test_both_vars_set_castle_wins(monkeypatch):
    monkeypatch.setenv("CASTLE_DIR", "/from/new")
    monkeypatch.setenv("MEMPAL_DIR", "/from/old")
    assert _read_castle_env("CASTLE_DIR", "MEMPAL_DIR") == "/from/new"


def test_only_legacy_set_returns_legacy_with_warning(monkeypatch, capsys):
    monkeypatch.delenv("CASTLE_DIR", raising=False)
    monkeypatch.setenv("MEMPAL_DIR", "/path/from/old")
    out = _read_castle_env("CASTLE_DIR", "MEMPAL_DIR")
    captured = capsys.readouterr()
    assert out == "/path/from/old"
    assert "MEMPAL_DIR is deprecated" in captured.err
    assert "CASTLE_DIR" in captured.err


def test_neither_set_returns_default(monkeypatch):
    monkeypatch.delenv("CASTLE_DIR", raising=False)
    monkeypatch.delenv("MEMPAL_DIR", raising=False)
    assert _read_castle_env("CASTLE_DIR", "MEMPAL_DIR", default="/fallback") == "/fallback"


def test_neither_set_no_default_returns_empty_string(monkeypatch):
    monkeypatch.delenv("CASTLE_DIR", raising=False)
    monkeypatch.delenv("MEMPAL_DIR", raising=False)
    assert _read_castle_env("CASTLE_DIR", "MEMPAL_DIR") == ""


def test_warning_fires_only_once_per_process(monkeypatch, capsys):
    monkeypatch.delenv("CASTLE_DIR", raising=False)
    monkeypatch.setenv("MEMPAL_DIR", "/path")
    _read_castle_env("CASTLE_DIR", "MEMPAL_DIR")
    _read_castle_env("CASTLE_DIR", "MEMPAL_DIR")
    _read_castle_env("CASTLE_DIR", "MEMPAL_DIR")
    captured = capsys.readouterr()
    # Warning text contains "MEMPAL_DIR is deprecated" — count occurrences
    assert captured.err.count("MEMPAL_DIR is deprecated") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_env_var_compat.py -v`
Expected: FAIL with `ImportError: cannot import name '_read_castle_env' from 'cognitive_castle.hooks_cli'` (or similar for `_DEPRECATED_LEGACY_ENV_WARNED`).

- [ ] **Step 3: Add the helper to hooks_cli.py**

Open `cognitive_castle/hooks_cli.py`. Find the top of the file (after imports, before any other module-level code). Add:

```python
# Track which legacy env-var names have already produced a deprecation warning
# in this process. Cleared by tests via direct manipulation.
_DEPRECATED_LEGACY_ENV_WARNED: set[str] = set()


def _read_castle_env(new_name: str, old_name: str, default: str = "") -> str:
    """Read a CASTLE_* env var, falling back to legacy MEMPAL_* with a one-time deprecation log.

    Precedence: CASTLE_* > MEMPAL_* > default. If only the legacy name is set,
    a deprecation warning is written to stderr once per process. Subsequent
    reads of the same legacy name are silent.
    """
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

If `sys` is not already imported at the top of the file, add `import sys` next to the other `import` lines.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_env_var_compat.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Run focused regression check**

Run:
```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```
Expected: No NEW failures vs current baseline. The shim is additive (no caller uses it yet).

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/hooks_cli.py tests/test_env_var_compat.py
git commit -m "feat(hooks): add _read_castle_env shim helper for MEMPAL_* -> CASTLE_* env var rename"
```

---

### Task 2: Migrate the 6 MEMPAL_* references in hooks_cli.py to use the shim

**Files:**
- Modify: `cognitive_castle/hooks_cli.py`

The current production references (located via `grep -n "MEMPAL_DIR\|MEMPAL_PYTHON\|MEMPAL_VERBOSE" cognitive_castle/hooks_cli.py`):
- 1 in a docstring mentioning the env var name (line ~203)
- 1 referencing `mempal_dir = os.environ.get("MEMPAL_DIR", "")` (line ~211)
- 1 in a docstring (line ~208)
- 1 in a docstring (line ~274)
- 1 in a docstring (line ~295)
- 1 comment (line ~686)

The actual runtime read is line ~211. The others are docs. Inventory exhaustively at impl time via `grep -n "MEMPAL_" cognitive_castle/hooks_cli.py` and walk each.

- [ ] **Step 1: Write the migration test**

Append to `tests/test_env_var_compat.py`:

```python
def test_hooks_cli_uses_read_castle_env_for_dir(monkeypatch):
    """The MEMPAL_DIR caller in hooks_cli should now flow through the shim."""
    monkeypatch.delenv("CASTLE_DIR", raising=False)
    monkeypatch.setenv("MEMPAL_DIR", "/legacy/projects")
    _DEPRECATED_LEGACY_ENV_WARNED.clear()
    # The internal call that picks up MEMPAL_DIR for project mining.
    # Use whatever the public function is — likely `_get_project_dir` or similar.
    # If not exposed as a function, import the module and call the underlying logic.
    from cognitive_castle import hooks_cli
    # The simplest verification: re-read via the shim directly with the same params
    # that the production code now uses.
    assert hooks_cli._read_castle_env("CASTLE_DIR", "MEMPAL_DIR") == "/legacy/projects"


def test_castle_dir_takes_precedence_over_mempal_dir(monkeypatch):
    monkeypatch.setenv("CASTLE_DIR", "/new/projects")
    monkeypatch.setenv("MEMPAL_DIR", "/legacy/projects")
    from cognitive_castle import hooks_cli
    assert hooks_cli._read_castle_env("CASTLE_DIR", "MEMPAL_DIR") == "/new/projects"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_env_var_compat.py::test_hooks_cli_uses_read_castle_env_for_dir tests/test_env_var_compat.py::test_castle_dir_takes_precedence_over_mempal_dir -v`
Expected: Both PASS (the helper exists; we're testing that calling it produces the right behavior, which it does regardless of internal migration).

These tests confirm the shim works; they don't directly verify production callers use it. That comes via the regression suite + the fact that tests patching MEMPAL_DIR still pass.

- [ ] **Step 3: Migrate production callers in hooks_cli.py**

Replace each `os.environ.get("MEMPAL_DIR", "")` and similar with `_read_castle_env("CASTLE_DIR", "MEMPAL_DIR", default="")`. Same pattern for `MEMPAL_PYTHON` → `CASTLE_PYTHON` and `MEMPAL_VERBOSE` → `CASTLE_VERBOSE`.

Concrete pattern. Where the code currently has:
```python
mempal_dir = os.environ.get("MEMPAL_DIR", "")
```
Replace with:
```python
castle_dir = _read_castle_env("CASTLE_DIR", "MEMPAL_DIR", default="")
```

Update the local variable name from `mempal_dir` to `castle_dir` and propagate the rename through the function's body. This keeps the local naming consistent with the new env var name.

Update docstrings in the file that reference `MEMPAL_DIR`/`MEMPAL_PYTHON`/`MEMPAL_VERBOSE`. Change each to mention `CASTLE_DIR`/`CASTLE_PYTHON`/`CASTLE_VERBOSE` as the primary name, with a note that the legacy `MEMPAL_*` names are still read (with deprecation warning).

After the edit, run:
```bash
grep -n "MEMPAL_DIR\|MEMPAL_PYTHON\|MEMPAL_VERBOSE" cognitive_castle/hooks_cli.py
```
Expected: matches appear ONLY inside the `_read_castle_env` helper's call signatures (`_read_castle_env("CASTLE_DIR", "MEMPAL_DIR", ...)`) and in the helper's docstring. NO bare `os.environ.get("MEMPAL_*", ...)` calls.

- [ ] **Step 4: Run focused regression check**

Run:
```bash
pytest tests/test_hooks_cli.py tests/test_env_var_compat.py -v --tb=short 2>&1 | tail -20
```
Expected: All previously-passing hooks_cli tests still pass. The ~89 test files that patch `MEMPAL_DIR` in `os.environ` continue working via the shim.

Full focused suite:
```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```
Expected: Same passed/failed counts as before (no new regressions).

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/hooks_cli.py tests/test_env_var_compat.py
git commit -m "refactor(hooks): migrate MEMPAL_* env var reads to CASTLE_* via shim"
```

---

## Phase 2: State-dir helper

### Task 3: Add `_state_dir()` helper + tests

**Files:**
- Create: `tests/test_state_dir_migration.py`
- Modify: `cognitive_castle/hooks_cli.py`

**Context:** Production `hooks_cli.py:18` already uses `STATE_DIR = Path.home() / ".castle" / "hook_state"`. The helper formalizes this resolution so a hypothetical user with legacy data at `~/.mempalace/hook_state/` gets a graceful one-time migration note. On a machine without legacy state (the common case), the helper returns `~/.castle/hook_state` identically to today.

- [ ] **Step 1: Write the failing test**

Create `tests/test_state_dir_migration.py`:

```python
"""Tests for _state_dir(): resolves hook state directory with legacy fallback."""
from pathlib import Path

import pytest


def _setup_homes(tmp_path, monkeypatch, new_exists: bool, old_exists: bool):
    """Point HOME at tmp_path; optionally create new and/or legacy dirs."""
    monkeypatch.setenv("HOME", str(tmp_path))
    new = tmp_path / ".castle" / "hook_state"
    old = tmp_path / ".mempalace" / "hook_state"
    if new_exists:
        new.mkdir(parents=True, exist_ok=True)
    if old_exists:
        old.mkdir(parents=True, exist_ok=True)
    return new, old


def _import_fresh_state_dir():
    """Import _state_dir freshly so it picks up the current HOME env."""
    # Reload the module so module-level constants re-evaluate against the new HOME.
    import importlib
    from cognitive_castle import hooks_cli
    importlib.reload(hooks_cli)
    return hooks_cli._state_dir, hooks_cli._DEPRECATED_LEGACY_ENV_WARNED


def test_new_dir_exists_returns_new(tmp_path, monkeypatch):
    new, _ = _setup_homes(tmp_path, monkeypatch, new_exists=True, old_exists=False)
    state_dir, warn_cache = _import_fresh_state_dir()
    warn_cache.clear()
    assert state_dir() == new


def test_only_legacy_exists_returns_legacy_with_log(tmp_path, monkeypatch, capsys):
    _, old = _setup_homes(tmp_path, monkeypatch, new_exists=False, old_exists=True)
    state_dir, warn_cache = _import_fresh_state_dir()
    warn_cache.clear()
    result = state_dir()
    captured = capsys.readouterr()
    assert result == old
    assert "legacy state dir" in captured.err.lower()


def test_neither_exists_creates_new(tmp_path, monkeypatch):
    new, _ = _setup_homes(tmp_path, monkeypatch, new_exists=False, old_exists=False)
    state_dir, warn_cache = _import_fresh_state_dir()
    warn_cache.clear()
    result = state_dir()
    assert result == new
    assert new.exists()


def test_both_exist_returns_new(tmp_path, monkeypatch):
    new, old = _setup_homes(tmp_path, monkeypatch, new_exists=True, old_exists=True)
    state_dir, warn_cache = _import_fresh_state_dir()
    warn_cache.clear()
    assert state_dir() == new


def test_legacy_log_fires_only_once(tmp_path, monkeypatch, capsys):
    _setup_homes(tmp_path, monkeypatch, new_exists=False, old_exists=True)
    state_dir, warn_cache = _import_fresh_state_dir()
    warn_cache.clear()
    state_dir()
    state_dir()
    state_dir()
    captured = capsys.readouterr()
    assert captured.err.lower().count("legacy state dir") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_state_dir_migration.py -v`
Expected: FAIL with `AttributeError` on `hooks_cli._state_dir`.

- [ ] **Step 3: Add the helper**

In `cognitive_castle/hooks_cli.py`, near the existing `STATE_DIR = Path.home() / ".castle" / "hook_state"` line (line 18), add the helper function ABOVE the constant and rewrite the constant to call it:

```python
def _state_dir() -> Path:
    """Return the hook state directory, preferring ~/.castle/ and falling back to ~/.mempalace/.

    Behavior:
    - If ~/.castle/hook_state/ exists, return it.
    - Else if ~/.mempalace/hook_state/ exists (legacy from MemPalace days),
      return it and log a one-time migration note to stderr.
    - Otherwise create ~/.castle/hook_state/ and return it.

    The legacy-path log uses the same one-time-warning mechanism as
    `_read_castle_env`, sharing `_DEPRECATED_LEGACY_ENV_WARNED`.
    """
    new = Path.home() / ".castle" / "hook_state"
    old = Path.home() / ".mempalace" / "hook_state"
    if new.exists():
        return new
    if old.exists():
        if "state_dir_migration" not in _DEPRECATED_LEGACY_ENV_WARNED:
            _DEPRECATED_LEGACY_ENV_WARNED.add("state_dir_migration")
            sys.stderr.write(
                f"[castle] NOTE: reading legacy state dir {old}; "
                f"new writes will go to {new}.\n"
            )
        return old
    new.mkdir(parents=True, exist_ok=True)
    return new


STATE_DIR = _state_dir()  # module-level constant, computed once at import
```

This MUST be placed AFTER `_DEPRECATED_LEGACY_ENV_WARNED` is defined (from Task 1) but BEFORE any code references `STATE_DIR`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_state_dir_migration.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Run focused regression check**

Run:
```bash
pytest tests/test_hooks_cli.py tests/test_env_var_compat.py tests/test_state_dir_migration.py -v 2>&1 | tail -10
```
Expected: All pass. The existing STATE_DIR behavior is preserved (returns `~/.castle/hook_state`); the helper just centralizes the resolution.

Full focused suite:
```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```
Expected: Same passed/failed counts as before.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/hooks_cli.py tests/test_state_dir_migration.py
git commit -m "feat(hooks): add _state_dir() helper with legacy ~/.mempalace/hook_state fallback"
```

---

## Phase 3: Class rename

### Task 4: Rename `MempalaceConfig` → `CognitiveCastleConfig` with alias

**Files:**
- Modify: `cognitive_castle/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_cognitive_castle_config_is_canonical_name():
    """CognitiveCastleConfig is the new canonical class name."""
    from cognitive_castle.config import CognitiveCastleConfig
    cfg = CognitiveCastleConfig()
    # Sanity check: an existing property still works.
    assert cfg.embedder_model == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def test_mempalace_config_is_backward_compat_alias():
    """MempalaceConfig still importable as an alias to CognitiveCastleConfig."""
    from cognitive_castle.config import MempalaceConfig, CognitiveCastleConfig
    # Same class object (alias, not a separate class).
    assert MempalaceConfig is CognitiveCastleConfig
    # Instances of one are instances of the other.
    cfg = MempalaceConfig()
    assert isinstance(cfg, CognitiveCastleConfig)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py::test_cognitive_castle_config_is_canonical_name tests/test_config.py::test_mempalace_config_is_backward_compat_alias -v`
Expected: FAIL with `ImportError: cannot import name 'CognitiveCastleConfig'`.

- [ ] **Step 3: Rename the class + add alias**

In `cognitive_castle/config.py`, find `class MempalaceConfig:` (around line 149). Rename the class to `CognitiveCastleConfig` (rename ONLY the class declaration line and any internal `self`-class references — those are normally none in a class body). After the class definition, add the alias:

```python
class CognitiveCastleConfig:
    """... existing docstring unchanged ..."""
    # ... existing class body unchanged ...


# Backward-compat alias. Programmatic users still importing the old name keep
# working. Kept indefinitely; remove only after a deliberate breaking-change
# version bump.
MempalaceConfig = CognitiveCastleConfig
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py::test_cognitive_castle_config_is_canonical_name tests/test_config.py::test_mempalace_config_is_backward_compat_alias -v`
Expected: Both PASS.

- [ ] **Step 5: Run focused regression check**

```bash
pytest tests/test_config.py -v 2>&1 | tail -10
```
Expected: All previously-passing config tests still pass (the alias means existing `from ... import MempalaceConfig` lines keep working).

Full focused suite:
```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```
Expected: Same passed/failed counts.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/config.py tests/test_config.py
git commit -m "refactor(config): rename MempalaceConfig -> CognitiveCastleConfig (alias kept for backward compat)"
```

---

### Task 5: Update internal callers in `cognitive_castle/` to use `CognitiveCastleConfig`

**Files:**
- Modify: 9 files under `cognitive_castle/` (per earlier inventory)

The set of files is enumerable via:
```bash
grep -rln "MempalaceConfig" cognitive_castle/ --include="*.py" | grep -v config.py
```

Expected files (per earlier inventory; verify at impl time):
- `cognitive_castle/backends/lancedb_backend.py`
- `cognitive_castle/cli.py`
- `cognitive_castle/convo_miner.py`
- `cognitive_castle/dedup.py`
- `cognitive_castle/embedding.py`
- `cognitive_castle/fact_checker.py`
- `cognitive_castle/hooks_cli.py`
- `cognitive_castle/layers.py`
- `cognitive_castle/palace.py`
- `cognitive_castle/palace_graph.py`

In each file, change every occurrence of `MempalaceConfig` to `CognitiveCastleConfig`. This is a mechanical find-replace within `cognitive_castle/` (NOT under `tests/` — tests keep working via the alias).

- [ ] **Step 1: Run the find-replace**

```bash
for f in $(grep -rln "MempalaceConfig" cognitive_castle/ --include="*.py" | grep -v config.py); do
  sed -i 's/MempalaceConfig/CognitiveCastleConfig/g' "$f"
done
```

- [ ] **Step 2: Verify no straggler references**

```bash
grep -rn "MempalaceConfig" cognitive_castle/
```
Expected: References appear ONLY in `cognitive_castle/config.py` (the class body and the `MempalaceConfig = CognitiveCastleConfig` alias).

- [ ] **Step 3: Run focused regression check**

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```
Expected: Same passed/failed counts as before (the rename is internal, alias preserves external compat).

- [ ] **Step 4: Run ruff to confirm clean**

```bash
ruff check cognitive_castle/
```
Expected: No new errors (find-replace is straightforward; should produce no syntax issues).

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/
git commit -m "refactor: migrate internal callers from MempalaceConfig to CognitiveCastleConfig"
```

---

## Phase 4: Plugin scaffolding rebrand

### Task 6: Rebrand plugin manifest JSON files

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `.claude-plugin/.mcp.json`

**Context:** All three are small JSON files. The spec specifies their target content. Pre-flight: ask the user (Open Question #2) for their fork URL to put in `repository` and `owner.url` fields.

- [ ] **Step 1: Replace `.claude-plugin/plugin.json`**

Write the entire file content:

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
  "repository": "https://github.com/Testimonial/cognitive-castle"
}
```

(Use the actual fork URL — `Testimonial/cognitive-castle` is the verified origin from `git remote -v` output during the SOTA work.)

- [ ] **Step 2: Replace `.claude-plugin/marketplace.json`**

```json
{
  "name": "cognitive-castle",
  "owner": {
    "name": "Ladislav Bihari",
    "url": "https://github.com/Testimonial"
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

- [ ] **Step 3: Replace `.claude-plugin/.mcp.json`**

```json
{
  "castle": {
    "command": "castle-mcp"
  }
}
```

- [ ] **Step 4: Verify JSON validity**

```bash
python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); json.load(open('.claude-plugin/marketplace.json')); json.load(open('.claude-plugin/.mcp.json')); print('all valid')"
```
Expected: `all valid`.

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json .claude-plugin/.mcp.json
git commit -m "feat(plugin): rebrand plugin manifest JSON files (mempalace -> castle, ChromaDB removed)"
```

---

### Task 7: Rebrand hook wrappers and `hooks/hooks.json`

**Files:**
- Modify: `.claude-plugin/hooks/hooks.json`
- Rename: `.claude-plugin/hooks/mempal-stop-hook.sh` → `.claude-plugin/hooks/castle-stop-hook.sh`
- Rename: `.claude-plugin/hooks/mempal-precompact-hook.sh` → `.claude-plugin/hooks/castle-precompact-hook.sh`

- [ ] **Step 1: Rename the hook wrapper scripts via `git mv`**

```bash
git mv .claude-plugin/hooks/mempal-stop-hook.sh .claude-plugin/hooks/castle-stop-hook.sh
git mv .claude-plugin/hooks/mempal-precompact-hook.sh .claude-plugin/hooks/castle-precompact-hook.sh
```

- [ ] **Step 2: Rewrite `castle-stop-hook.sh`**

Replace contents with:

```bash
#!/bin/bash
# Cognitive Castle Stop Hook — thin wrapper calling the Python CLI.
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

- [ ] **Step 3: Rewrite `castle-precompact-hook.sh`**

Same content as Step 2 but last line is `run_castle_hook --hook precompact --harness claude-code`.

- [ ] **Step 4: Make both scripts executable**

```bash
chmod 0755 .claude-plugin/hooks/castle-stop-hook.sh .claude-plugin/hooks/castle-precompact-hook.sh
```

- [ ] **Step 5: Update `.claude-plugin/hooks/hooks.json`**

```json
{
  "description": "Cognitive Castle auto-save and pre-compact hooks",
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/castle-stop-hook.sh\""
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/castle-precompact-hook.sh\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 6: Verify**

```bash
python3 -c "import json; json.load(open('.claude-plugin/hooks/hooks.json')); print('valid')"
ls -la .claude-plugin/hooks/
```
Expected: `valid`; both renamed `.sh` files present and executable.

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin/hooks/
git commit -m "feat(plugin): rename + rebrand hook wrappers (castle-stop-hook.sh, castle-precompact-hook.sh)"
```

---

### Task 8: Finish `tests/test_claude_plugin_hook_wrappers.py`

**Files:**
- Modify: `tests/test_claude_plugin_hook_wrappers.py`

This test was half-rebranded in an earlier session — its primary-command expectation is `cognitive-castle` (line 82) but its fallback expectation still references `mempalace`. After Task 7 renamed the wrapper scripts, the test's `SCRIPT_CASES` list (line 19) also needs updating.

- [ ] **Step 1: Update `SCRIPT_CASES`**

Find lines 19-22 of `tests/test_claude_plugin_hook_wrappers.py`:
```python
SCRIPT_CASES = [
    ("mempal-stop-hook.sh", "stop"),
    ("mempal-precompact-hook.sh", "precompact"),
]
```
Replace with:
```python
SCRIPT_CASES = [
    ("castle-stop-hook.sh", "stop"),
    ("castle-precompact-hook.sh", "precompact"),
]
```

- [ ] **Step 2: Update the primary-CLI stub from `cognitive-castle` to `castle`**

Around line 82, find:
```python
"cognitive-castle": (
    "#!/bin/sh\n"
    f'printf \'%s\' "$*" > "{_shell_path(args_file)}"\n'
    ...
```
The function-name string and the file name `cognitive-castle` (the stub written to bin dir) should be `castle` because pyproject's actual CLI is `castle`:
```python
"castle": (
    "#!/bin/sh\n"
    ...
```

- [ ] **Step 3: Update the fallback-Python expectation**

Around line 131:
```python
== f"-m mempalace hook run --hook {hook_name} --harness claude-code"
```
Replace with:
```python
== f"-m cognitive_castle hook run --hook {hook_name} --harness claude-code"
```

- [ ] **Step 4: Update the error-message expectation**

Around line 147:
```python
assert "could not find a runnable mempalace command or module" in result.stderr
```
Replace with:
```python
assert "could not find a runnable castle command or cognitive_castle module" in result.stderr
```

- [ ] **Step 5: Run the test**

```bash
pytest tests/test_claude_plugin_hook_wrappers.py -v --tb=short 2>&1 | tail -20
```
Expected: All ~8 parameterized tests PASS.

If a test fails because the wrappers (from Task 7) don't match the expected stub-command name `castle`, double-check the wrapper script: line 5 should say `if command -v castle >/dev/null 2>&1; then` (this is what Task 7 wrote — confirm).

- [ ] **Step 6: Commit**

```bash
git add tests/test_claude_plugin_hook_wrappers.py
git commit -m "test(plugin): finish rebranding test_claude_plugin_hook_wrappers (castle CLI + cognitive_castle module)"
```

---

### Task 9: Rebrand plugin skill and slash commands

**Files:**
- Move: `.claude-plugin/skills/mempalace/` → `.claude-plugin/skills/castle/`
- Modify: `.claude-plugin/skills/castle/SKILL.md` (content rewrite)
- Modify: `.claude-plugin/commands/help.md`, `init.md`, `mine.md`, `search.md`, `status.md`

- [ ] **Step 1: Rename the skill directory**

```bash
git mv .claude-plugin/skills/mempalace .claude-plugin/skills/castle
```

- [ ] **Step 2: Rewrite `.claude-plugin/skills/castle/SKILL.md`**

Replace contents with:

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

- [ ] **Step 3: Rewrite `.claude-plugin/commands/help.md`**

Each command file has a frontmatter description and a body. The current body says `Invoke the generic mempalace skill ...`. New content:

```markdown
---
description: Show comprehensive Cognitive Castle help — available skills, MCP tools, CLI commands, hooks, and architecture.
allowed-tools: Bash, Read
---

Invoke the generic castle skill (using the Skill tool) with the `help` command, then follow its instructions.
```

- [ ] **Step 4: Rewrite `.claude-plugin/commands/init.md`**

```markdown
---
description: Set up Cognitive Castle — install the package, initialize a palace, configure MCP server, and verify everything works.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

Invoke the generic castle skill (using the Skill tool) with the `init` command, then follow its instructions.
```

- [ ] **Step 5: Rewrite `.claude-plugin/commands/mine.md`**

```markdown
---
description: Mine projects and conversations into the Cognitive Castle. Supports project files, conversation exports, and auto-classification.
argument-hint: Path to project or conversation export to mine.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

Invoke the generic castle skill (using the Skill tool) with the `mine` command, then follow its instructions.
```

- [ ] **Step 6: Rewrite `.claude-plugin/commands/search.md`**

```markdown
---
description: Search your memories across the Cognitive Castle using semantic search with wing/room filtering.
argument-hint: Search query, optionally with wing/room filters.
allowed-tools: Bash, Read
---

Invoke the generic castle skill (using the Skill tool) with the `search` command, then follow its instructions.
```

- [ ] **Step 7: Rewrite `.claude-plugin/commands/status.md`**

```markdown
---
description: Show the current state of your Cognitive Castle — wings, rooms, drawer counts, and suggestions.
allowed-tools: Bash, Read
---

Invoke the generic castle skill (using the Skill tool) with the `status` command, then follow its instructions.
```

- [ ] **Step 8: Verify directory structure and grep for stragglers**

```bash
ls .claude-plugin/skills/  # expect: castle/
ls .claude-plugin/commands/  # expect: help.md init.md mine.md search.md status.md
grep -rn "mempalace\|MemPalace" .claude-plugin/skills/ .claude-plugin/commands/
```
Expected: directory shows `castle/`; the grep returns zero matches.

- [ ] **Step 9: Commit**

```bash
git add .claude-plugin/skills/ .claude-plugin/commands/
git commit -m "feat(plugin): rebrand skill (mempalace -> castle) and 5 slash command markdown files"
```

---

### Task 10: Rewrite `.claude-plugin/README.md`

**Files:**
- Modify: `.claude-plugin/README.md`

The current README documents `claude plugin marketplace add MemPalace/mempalace`, `/mempalace:init`, mentions ChromaDB and `MEMPAL_DIR`.

- [ ] **Step 1: Count MCP tools to verify the README claim**

```bash
grep -c "^def tool_\|^TOOLS\[" cognitive_castle/mcp_server.py 2>/dev/null
grep -n "^def tool_\|MCP_TOOLS\|TOOLS = " cognitive_castle/mcp_server.py | head -25
```
Count the MCP tool registrations. Note the exact number.

- [ ] **Step 2: Replace `.claude-plugin/README.md`**

```markdown
# Cognitive Castle Claude Code Plugin

A Claude Code plugin that gives your AI a persistent memory system. Mine projects and conversations into a searchable palace backed by LanceDB, with MCP tools, auto-save hooks, and 5 guided skills.

## Prerequisites

- Python 3.9+
- `pip install cognitive-castle` (or `pip install -e .` from a checkout)

## Installation

### From this repository

Inside Claude Code:

```
/plugin marketplace add /path/to/cognitive-castle
/plugin install castle@cognitive-castle
```

Then fully quit and reopen Claude Code (a `/reload` is not enough for new MCP servers).

## Post-Install Setup

After installing the plugin, run the init command to complete setup (pip install, MCP configuration, palace creation, etc.):

```
/castle:init
```

## Available Slash Commands

| Command | Description |
|---------|-------------|
| `/castle:help` | Show available tools, skills, and architecture |
| `/castle:init` | Set up Cognitive Castle — install, configure MCP, onboard |
| `/castle:search` | Search your memories across the palace |
| `/castle:mine` | Mine projects and conversations into the palace |
| `/castle:status` | Show palace overview — wings, rooms, drawer counts |

## Hooks

Cognitive Castle registers two hooks that run automatically:

- **Stop** — Saves conversation context every 15 messages.
- **PreCompact** — Preserves important memories before context compaction.

Set the `CASTLE_DIR` environment variable to a directory path to automatically run `castle mine` on that directory during each save trigger. (Legacy `MEMPAL_DIR` is still read with a one-time deprecation warning per process.)

## MCP Server

The plugin automatically configures a local MCP server with <N> tools for storing, searching, and managing memories. No manual MCP setup is required — `/castle:init` handles everything.

## Full Documentation

See the main [README](../README.md) for complete documentation, architecture details, and advanced usage.
```

Replace `<N>` with the actual MCP tool count from Step 1.

- [ ] **Step 3: Verify no stragglers**

```bash
grep -in "mempalace\|MemPalace\|chromadb\|ChromaDB" .claude-plugin/README.md
```
Expected: zero matches.

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/README.md
git commit -m "docs(plugin): rewrite README for Cognitive Castle rebrand"
```

---

### Task 11: Add `tests/test_plugin_manifests.py`

**Files:**
- Create: `tests/test_plugin_manifests.py`

- [ ] **Step 1: Write the test**

```python
"""Structural tests for .claude-plugin/ manifest files."""
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / ".claude-plugin"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_plugin_json_valid_structure():
    data = _load(PLUGIN_DIR / "plugin.json")
    assert data["name"] == "castle"
    assert data["version"]  # non-empty string
    assert data["description"]
    assert "mcpServers" in data
    assert data["mcpServers"]["castle"]["command"] == "castle-mcp"
    # No chromadb / mempalace keyword leftovers
    keywords = data.get("keywords", [])
    assert "chromadb" not in keywords
    assert "mempalace" not in keywords


def test_plugin_json_no_mempalace_references():
    raw = (PLUGIN_DIR / "plugin.json").read_text()
    assert "mempalace" not in raw.lower()


def test_marketplace_json_valid_structure():
    data = _load(PLUGIN_DIR / "marketplace.json")
    assert data["name"] == "cognitive-castle"
    assert "owner" in data
    plugins = data["plugins"]
    assert len(plugins) >= 1
    castle = next((p for p in plugins if p["name"] == "castle"), None)
    assert castle is not None, "marketplace must list a plugin named 'castle'"
    assert castle["source"] == "./.claude-plugin"


def test_mcp_json_points_at_castle_mcp():
    data = _load(PLUGIN_DIR / ".mcp.json")
    assert "castle" in data
    assert data["castle"]["command"] == "castle-mcp"


def test_hooks_json_references_castle_wrappers():
    data = _load(PLUGIN_DIR / "hooks" / "hooks.json")
    stop_hooks = data["hooks"]["Stop"]
    precompact_hooks = data["hooks"]["PreCompact"]
    stop_cmd = stop_hooks[0]["hooks"][0]["command"]
    precompact_cmd = precompact_hooks[0]["hooks"][0]["command"]
    assert "castle-stop-hook.sh" in stop_cmd
    assert "castle-precompact-hook.sh" in precompact_cmd
    # No mempal references
    assert "mempal" not in stop_cmd
    assert "mempal" not in precompact_cmd


def test_version_sync_with_package():
    """plugin.json and marketplace.json should match cognitive_castle.version."""
    from cognitive_castle.version import __version__
    plugin_data = _load(PLUGIN_DIR / "plugin.json")
    marketplace_data = _load(PLUGIN_DIR / "marketplace.json")
    assert plugin_data["version"] == __version__, (
        f"plugin.json version {plugin_data['version']!r} != "
        f"cognitive_castle.version.__version__ {__version__!r}"
    )
    castle_plugin = next(p for p in marketplace_data["plugins"] if p["name"] == "castle")
    assert castle_plugin["version"] == __version__


def test_wrapper_scripts_exist_and_executable():
    """Renamed hook wrapper scripts are present and executable."""
    import os
    stop = PLUGIN_DIR / "hooks" / "castle-stop-hook.sh"
    precompact = PLUGIN_DIR / "hooks" / "castle-precompact-hook.sh"
    assert stop.exists()
    assert precompact.exists()
    assert os.access(stop, os.X_OK), f"{stop} must be executable"
    assert os.access(precompact, os.X_OK), f"{precompact} must be executable"


def test_legacy_wrapper_names_do_not_exist():
    """The pre-rename filenames are gone."""
    assert not (PLUGIN_DIR / "hooks" / "mempal-stop-hook.sh").exists()
    assert not (PLUGIN_DIR / "hooks" / "mempal-precompact-hook.sh").exists()
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/test_plugin_manifests.py -v --tb=short 2>&1 | tail -15
```
Expected: All 8 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_plugin_manifests.py
git commit -m "test(plugin): add structural tests for .claude-plugin/ manifest files"
```

---

## Phase 5: Delete legacy top-level

### Task 12: Delete legacy top-level shell scripts + their tests

**Files:**
- Delete: `hooks/mempal_save_hook.sh`
- Delete: `hooks/mempal_precompact_hook.sh`
- Delete: `hooks/README.md`
- Delete: `tests/test_hooks_shell.py`
- Delete: `tests/test_save_hook_mines.py`
- Delete: `tests/test_save_hook_verbose.py`

**Pre-flight:** confirm these are orphaned (nobody references them outside the deleted set).

- [ ] **Step 1: Confirm no live references**

```bash
grep -rn "mempal_save_hook\|mempal_precompact_hook" \
  --include="*.py" --include="*.sh" --include="*.json" --include="*.md" \
  cognitive_castle/ tests/ docs/ .claude/ .claude-plugin/ 2>/dev/null \
  | grep -v "tests/test_hooks_shell\|tests/test_save_hook_mines\|tests/test_save_hook_verbose"
```
Expected: zero matches. If matches appear, they need to be updated/removed before deletion.

- [ ] **Step 2: Confirm user's own settings don't wire these in**

```bash
grep -n "mempal_save_hook\|mempal_precompact_hook" ~/.claude/settings.json ~/.claude/settings.local.json /home/lbihari/cognitive-castle/.claude/settings.json 2>/dev/null
```
Expected: zero matches (the prior audit confirmed this). If matches appear, surface to the user before deletion — they'd need to update settings first.

- [ ] **Step 3: Delete the files**

```bash
git rm hooks/mempal_save_hook.sh hooks/mempal_precompact_hook.sh hooks/README.md
git rm tests/test_hooks_shell.py tests/test_save_hook_mines.py tests/test_save_hook_verbose.py
```

If `hooks/` is now empty, leave the directory. (git doesn't track empty dirs; the next commit removes the listed files.)

- [ ] **Step 4: Run focused regression check**

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```
Expected: total test count decreases by however many tests lived in the deleted test files. No NEW failures.

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: delete legacy top-level shell hooks and their tests (replaced by .claude-plugin/)"
```

---

## Phase 6: Documentation sweep

### Task 13: Inventory + sweep `cognitive_castle/` markdown and Python docstrings

**Files (verify exact list at impl time):**
- `cognitive_castle/README.md`
- `cognitive_castle/instructions/help.md`
- `cognitive_castle/instructions/init.md`
- `cognitive_castle/instructions/mine.md`
- `cognitive_castle/instructions/search.md`
- `cognitive_castle/instructions/status.md`
- Python modules under `cognitive_castle/` with `MemPalace`/`mempalace` in docstrings or comments

- [ ] **Step 1: Inventory exact files in scope**

```bash
grep -rln "MemPalace\|mempalace" cognitive_castle/ --include="*.py" --include="*.md"
```
Capture this list. Should be ≤ 15 files.

- [ ] **Step 2: Sweep markdown files in `cognitive_castle/instructions/`**

For each `.md` file under `cognitive_castle/instructions/`, apply these mechanical replacements:
- `MemPalace` → `Cognitive Castle`
- `mempalace` (when referring to the project/CLI name) → `castle` (CLI invocations) or `cognitive_castle` (Python module references)
- `~/.mempalace/` (in any URL/path that's part of brand documentation, NOT the live palace dir mentioned as a path the user already has) → `~/.castle/` for hook state, leave palace data path alone

Walk each file individually. For each file:
1. Read with `Read` tool
2. Identify each `MemPalace`/`mempalace` occurrence and the appropriate replacement
3. Apply `Edit` calls
4. Verify with grep: `grep -n "MemPalace\|mempalace" <file>` — should return zero (or only intentional residual matches)

Files in this batch:
- `cognitive_castle/instructions/help.md`
- `cognitive_castle/instructions/init.md`
- `cognitive_castle/instructions/mine.md`
- `cognitive_castle/instructions/search.md`
- `cognitive_castle/instructions/status.md`

- [ ] **Step 3: Sweep `cognitive_castle/README.md`**

The package README. Same rebrand logic. Verify with `grep -n "MemPalace\|mempalace" cognitive_castle/README.md` → zero matches.

- [ ] **Step 4: Sweep Python module docstrings**

For each remaining `cognitive_castle/*.py` file in the inventory list, the matches are typically in:
- Module-level docstring at the top of the file
- Inline comments
- Function/class docstrings

Walk each file. Use `Read` then `Edit` (or `Edit` with `replace_all=True` if the replacement is mechanical and unambiguous within the file).

- [ ] **Step 5: Verify**

```bash
grep -rln "MemPalace\|mempalace" cognitive_castle/ --include="*.py" --include="*.md"
```
Expected: very few or zero remaining matches. Any remaining matches should be in contexts where rebrand would be wrong (e.g., a comment explaining the rebrand itself).

- [ ] **Step 6: Run regression check**

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```
Expected: same pass/fail counts. Docstrings don't affect runtime behavior.

Also run the existing branding test:
```bash
pytest tests/test_branding.py -v 2>&1 | tail -10
```
Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/
git commit -m "docs: sweep cognitive_castle/ for MemPalace -> Cognitive Castle / mempalace -> castle in docstrings and instructions"
```

---

## Phase 7: Final acceptance

### Task 14: Verify all spec acceptance criteria

**Files:** none (verification only)

Walk each acceptance criterion from the spec and confirm. Document results in the report.

- [ ] **Step 1: Plugin manifest verification**

```bash
grep -rn "mempal\|MemPalace\|mempalace" .claude-plugin/ 2>/dev/null
```
Expected: zero matches.

- [ ] **Step 2: Test wrappers pass**

```bash
pytest tests/test_claude_plugin_hook_wrappers.py -v 2>&1 | tail -10
pytest tests/test_plugin_manifests.py -v 2>&1 | tail -10
pytest tests/test_env_var_compat.py tests/test_state_dir_migration.py -v 2>&1 | tail -10
pytest tests/test_branding.py -v 2>&1 | tail -10
```
Expected: all pass.

- [ ] **Step 3: Legacy deletion verified**

```bash
ls hooks/mempal_save_hook.sh hooks/mempal_precompact_hook.sh tests/test_hooks_shell.py tests/test_save_hook_mines.py tests/test_save_hook_verbose.py 2>&1
```
Expected: every line shows "No such file or directory".

- [ ] **Step 4: Env var residue check**

```bash
grep -n "MEMPAL_DIR\|MEMPAL_PYTHON\|MEMPAL_VERBOSE" cognitive_castle/hooks_cli.py
```
Expected: only matches inside the `_read_castle_env` helper signatures and the deprecation log message.

- [ ] **Step 5: Class rename verification**

```bash
grep -rn "MempalaceConfig" cognitive_castle/
```
Expected: matches only inside `cognitive_castle/config.py` (definition + alias).

- [ ] **Step 6: Doc-sweep residue**

```bash
grep -rln "MemPalace\|mempalace" cognitive_castle/ --include="*.py" --include="*.md"
```
Expected: ≤ 5 matches, all in contexts where the string is load-bearing (e.g., a comment explaining the rename or a URL).

- [ ] **Step 7: Full focused regression**

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -5
```
Expected: pass count matches baseline + new tests; fail count not increased beyond pre-existing.

- [ ] **Step 8: Working tree clean**

```bash
git status --short
```
Expected: clean.

- [ ] **Step 9: Manual live-plugin smoke (optional but recommended)**

Inside Claude Code:
1. `/plugin marketplace add /home/lbihari/cognitive-castle`
2. `/plugin install castle@cognitive-castle`
3. Restart Claude Code.
4. Confirm `/castle:help`, `/castle:init`, etc. visible.
5. Confirm Castle MCP tools visible to agent.

If any step fails, surface findings and iterate.

(No commit — this is verification.)

---

## Self-Review

**1. Spec coverage** — every section of the spec maps to a task:
- Plugin manifests rebrand → Task 6
- Hook wrappers rename + rewrite → Task 7
- Half-rebranded `test_claude_plugin_hook_wrappers.py` → Task 8
- Skill + slash commands rebrand → Task 9
- Plugin README rewrite → Task 10
- Top-level legacy deletion → Task 12
- Env var shim → Tasks 1–2
- State dir helper → Task 3
- `MempalaceConfig` class rename + alias → Task 4
- Internal callers migrated → Task 5
- Documentation sweep → Task 13
- New tests `test_plugin_manifests.py`, `test_env_var_compat.py`, `test_state_dir_migration.py` → Tasks 1, 3, 11
- Open Question #2 (fork URL) → resolved in Task 6 using verified `Testimonial/cognitive-castle`
- Final acceptance → Task 14

**2. Placeholder scan:** no "TBD"/"TODO"/"fill in later". Code blocks contain actual content. Acceptance criteria measurable.

**3. Type consistency:** `_read_castle_env(new_name, old_name, default)` signature consistent in Tasks 1 and 2. `_state_dir() -> Path` consistent in Task 3. `CognitiveCastleConfig` class name consistent in Tasks 4–5. `MempalaceConfig` alias defined in Task 4, used by tests via alias in unchanged callers.

**4. Sequencing constraints honored:**
- Env-var shim helper added (Task 1) BEFORE production callers migrated (Task 2) ✓
- State-dir helper added (Task 3) BEFORE any caller depends on it (existing `STATE_DIR` constant just gets recomputed via the helper) ✓
- Class rename + alias landed (Task 4) BEFORE internal callers updated (Task 5) ✓
- Plugin manifest changes (Tasks 6–11) independent of source-code changes (Phases 1–3); can be reviewed separately ✓
- Doc sweep landed LAST (Task 13) so test changes haven't drifted it ✓
- Legacy deletion (Task 12) happens after the plugin scaffolding works ✓
- Final acceptance verification (Task 14) is the last step ✓

**5. Known gaps requiring impl-time judgment** (called out in the relevant tasks, not silently elided):
- Exact MCP tool count for `.claude-plugin/README.md` (Task 10 Step 1) — counted at implementation time from `cognitive_castle/mcp_server.py`
- Fork URL — locked in via Task 6 (`https://github.com/Testimonial/cognitive-castle`, confirmed via `git remote -v`)
- `.mcp.json` vs `plugin.json.mcpServers` canonical answer — both kept consistent (defensive); resolve at manual smoke time

---

## Open questions resolved during plan writing

| Spec OQ | Resolution |
|---|---|
| OQ #1: `.mcp.json` vs `plugin.json.mcpServers` canonical | Keep both consistent (defensive). Manual smoke at Task 14 Step 9 verifies which Claude Code actually uses. |
| OQ #2: Fork URL | `https://github.com/Testimonial/cognitive-castle` (verified via earlier `git remote -v`) |
| OQ #3: MCP tool count in README | Counted at Task 10 Step 1 via `grep -c "^def tool_\|^TOOLS\[" cognitive_castle/mcp_server.py` |
| OQ #4: Marketplace ID after `/plugin marketplace add` | Verified at Task 14 Step 9 (manual smoke); document the actual ID in README if it differs from "cognitive-castle". |
| OQ #5: Doc-sweep boundaries | Inventoried at Task 13 Step 1 via grep. Excluded: `docs/`, `CHANGELOG.md`, `website/`, historical specs/plans/rfcs. |
