# Mempalace Production Fixes — Design (PR #B of cleanup series)

**Date:** 2026-05-12
**Branch target:** develop
**Scope:** Fix the small set of broken/stale mempalace references in production code: rename one internal constant, rename two env vars with deprecation aliases, fix 14 i18n strings that show the wrong command name to non-English users. ~30 lines production changes + 14 trivial JSON edits. No tests modified (those go in PR #C).

## Background

After the MemPalace → Cognitive Castle rebrand (PRs #2-#7) and the chroma + plugin cleanups, ~1,193 mempalace references remain across the repo. Most are intentional (backward-compat aliases, legacy filename/path fallbacks, historical docs). A handful are **actively wrong** in production:

- **P2 (Constants / env vars):** Three identifiers still use `MEMPALACE_*` naming:
  - `_MEMPALACE_PROJECT_FILES` in `cli.py:46` (internal constant)
  - `MEMPALACE_SOURCE_DIR` env var in `split_mega_files.py:32, 242` (user-set)
  - `MEMPALACE_PYTHON` env var in `hooks_cli.py:80, 86` (user-set)
  
  The values these symbols hold are correct (the constant stores `castle.yaml`/`entities.json`; the env vars are just override knobs). Only the *names* are stale.

- **P6 (i18n):** All 14 localized `no_palace` error messages tell the user to run `mempalace init <dir>`. That command doesn't exist — the CLI binary is `castle`. Non-English users see broken instructions.

This is PR #B of a 4-PR cleanup series:
- ✅ PR #A: SOAR removal (merged as #14)
- ← **PR #B: Mempalace production fixes (this spec)**
- PR #C: Mempalace tests sweep
- PR #D: Mempalace docs sweep

## Goals

1. The single internal constant `_MEMPALACE_PROJECT_FILES` is renamed to `_CASTLE_PROJECT_FILES`. No external callers (leading underscore = private).
2. The two user-set env vars (`MEMPALACE_SOURCE_DIR`, `MEMPALACE_PYTHON`) are renamed to `CASTLE_SOURCE_DIR` / `CASTLE_PYTHON`, with one-time deprecation warnings if the old names are still in the user's shell.
3. All 14 i18n `no_palace` strings tell the user to run `castle init` instead of `mempalace init`.
4. No NEW test failures relative to the post-#A baseline (74 failed, 1286 passed).
5. No production code outside `cli.py`, `split_mega_files.py`, `hooks_cli.py`, `i18n/*.json` is modified.

## Non-goals

- Renaming the `MempalaceConfig` backward-compat aliases (P1) — those are intentional, kept for legacy test patches. PR #C will revisit if tests get cleaned to no longer need them.
- Removing the legacy `~/.mempalace/` path fallback in `_state_dir()` (P4) — user's live palace data may still be there.
- Removing the legacy filename fallback `mempalace.yml`/`mempal.yml`/`mempal.yaml` in `miner.py:61` (P3) — intentional for old projects.
- Cleaning tests (PR #C) or docs (PR #D).
- Adding new env vars beyond the two renames.
- Renaming any directory or import path.
- Touching the `_read_castle_env` helper itself (the new deprecation logic for SOURCE_DIR/PYTHON lives where the env vars are read, not in the shared helper — keeps the change localized).

## Source of truth

- Exact surface inventoried during brainstorm (16:50 UTC, 2026-05-12). Grep results pasted into the brainstorming dialog.
- Decisions locked:
  - Internal constant rename: hard rename, no back-compat needed.
  - Env vars: rename + add deprecation aliases (read new name first, fall back to old + one-time warning).
  - i18n: surgical `s/mempalace init/castle init/` in 14 files. No other i18n drift.

## File-by-file change list

### `cognitive_castle/cli.py` (3 occurrences)

Hard rename `_MEMPALACE_PROJECT_FILES` → `_CASTLE_PROJECT_FILES`:

```python
# Line 46 — definition:
_CASTLE_PROJECT_FILES = ("castle.yaml", "entities.json")

# Line 82 — usage in cmd_init's filepath check:
if filepath.name in _CASTLE_PROJECT_FILES:

# Line 221 — usage in `missing` calculation:
missing = [p for p in _CASTLE_PROJECT_FILES if p not in existing_lines]
```

No alias needed. The symbol is private (leading underscore) and not imported by any other module — verified during brainstorm.

### `cognitive_castle/split_mega_files.py` (2 occurrences)

Replace direct `os.environ.get("MEMPALACE_SOURCE_DIR", ...)` with a small read-helper that supports both env-var names. Add a one-time deprecation warning if the legacy name is in use.

Current code (line 32):
```python
LUMI_DIR = Path(os.environ.get("MEMPALACE_SOURCE_DIR", str(HOME / "Desktop/transcripts")))
```

New code (insert a helper near the top of the file, after imports, before `LUMI_DIR`):
```python
def _source_dir_default() -> Path:
    """Resolve the transcript source dir, supporting both CASTLE_SOURCE_DIR (current)
    and MEMPALACE_SOURCE_DIR (legacy, deprecation-warned)."""
    new = os.environ.get("CASTLE_SOURCE_DIR", "")
    if new:
        return Path(new)
    old = os.environ.get("MEMPALACE_SOURCE_DIR", "")
    if old:
        import sys
        print(
            "[split-mega-files] MEMPALACE_SOURCE_DIR is deprecated — "
            "rename to CASTLE_SOURCE_DIR. Reading legacy value for now.",
            file=sys.stderr,
        )
        return Path(old)
    return HOME / "Desktop/transcripts"


LUMI_DIR = _source_dir_default()
```

Also update the argparse help text at line 242:
```python
# Before:
help="Source directory (default: MEMPALACE_SOURCE_DIR or ~/Desktop/transcripts)",
# After:
help="Source directory (default: CASTLE_SOURCE_DIR or ~/Desktop/transcripts; "
     "MEMPALACE_SOURCE_DIR is deprecated but still honored)",
```

### `cognitive_castle/hooks_cli.py` (2 occurrences)

Same pattern. The `_castle_python()` function at line 75-98 currently reads `MEMPALACE_PYTHON` directly. Replace with a deprecation-aware read.

Current code (line 80, 86):
```python
def _castle_python() -> str:
    """Return the python interpreter that has cognitive_castle installed.

    ...
    Resolution order:
    1. MEMPALACE_PYTHON env var (explicit override)
    2. Venv python from package install path
    3. Editable install: venv/ sibling to cognitive_castle/
    4. sys.executable fallback
    """
    # Honor explicit override (used by shell hook wrappers)
    env_python = os.environ.get("MEMPALACE_PYTHON", "")
    if env_python and os.path.isfile(env_python) and os.access(env_python, os.X_OK):
        return env_python
    ...
```

New code:
```python
def _castle_python() -> str:
    """Return the python interpreter that has cognitive_castle installed.

    ...
    Resolution order:
    1. CASTLE_PYTHON env var (explicit override; MEMPALACE_PYTHON also honored
       for back-compat with one-time deprecation warning)
    2. Venv python from package install path
    3. Editable install: venv/ sibling to cognitive_castle/
    4. sys.executable fallback
    """
    # Honor explicit override (used by shell hook wrappers)
    env_python = os.environ.get("CASTLE_PYTHON", "")
    if not env_python:
        legacy = os.environ.get("MEMPALACE_PYTHON", "")
        if legacy:
            import sys
            if "castle_python_deprecation" not in _DEPRECATED_LEGACY_ENV_WARNED:
                print(
                    "[hooks] MEMPALACE_PYTHON is deprecated — rename to "
                    "CASTLE_PYTHON. Reading legacy value for now.",
                    file=sys.stderr,
                )
                _DEPRECATED_LEGACY_ENV_WARNED.add("castle_python_deprecation")
            env_python = legacy
    if env_python and os.path.isfile(env_python) and os.access(env_python, os.X_OK):
        return env_python
    ...
```

The `_DEPRECATED_LEGACY_ENV_WARNED` set already exists in `hooks_cli.py` (used by `_state_dir()` for the `~/.mempalace/` path fallback). Re-use it.

### `cognitive_castle/i18n/*.json` (14 files)

For each language file, change exactly one substring in the `no_palace` value: `mempalace init` → `castle init`. Preserve all other localization (capitalisation, punctuation, surrounding translated text).

Files affected: `be.json, de.json, en.json, es.json, fr.json, hi.json, id.json, it.json, ja.json, ko.json, pt-br.json, ru.json, zh-CN.json, zh-TW.json`.

Example for `en.json`:
```json
// Before:
"no_palace": "No palace found. Run: mempalace init <dir>"
// After:
"no_palace": "No palace found. Run: castle init <dir>"
```

All other keys in the i18n files stay unchanged. Confirmed during brainstorm that `no_palace` is the only mempalace-tainted i18n string.

## Testing strategy

1. **Constant rename verification:**
   ```bash
   grep -nE "_MEMPALACE_PROJECT_FILES" cognitive_castle/cli.py
   grep -nE "_CASTLE_PROJECT_FILES" cognitive_castle/cli.py
   ```
   Expected: 0 / 3.

2. **Env var deprecation alias smoke test:**
   ```bash
   # New env var works:
   CASTLE_PYTHON=/usr/bin/python3 python -c "from cognitive_castle.hooks_cli import _castle_python; print(_castle_python())"
   # Expected: /usr/bin/python3 (or your override)
   
   # Old env var still works + emits warning:
   MEMPALACE_PYTHON=/usr/bin/python3 python -c "from cognitive_castle.hooks_cli import _castle_python; print(_castle_python())" 2>&1
   # Expected: prints the path AND a stderr line "[hooks] MEMPALACE_PYTHON is deprecated..."
   
   # New takes precedence over old:
   CASTLE_PYTHON=/usr/bin/python3 MEMPALACE_PYTHON=/wrong/path python -c "from cognitive_castle.hooks_cli import _castle_python; print(_castle_python())"
   # Expected: /usr/bin/python3, no deprecation warning
   ```

3. **i18n string check:**
   ```bash
   grep -niE "mempalace init" cognitive_castle/i18n/*.json
   ```
   Expected: 0 matches.
   ```bash
   grep -nE "castle init" cognitive_castle/i18n/*.json | wc -l
   ```
   Expected: 14 matches (one per language file).

4. **Focused suite stability:**
   ```bash
   pytest tests/ --ignore=tests/benchmarks -q --tb=no 2>&1 | tail -3
   ```
   Expected: failed count ≤ 74 (post-#A baseline). Some tests may reference `MEMPALACE_*` env vars — if any starts failing because of the rename, it goes in PR #C (tests sweep), not here. **Document any such failure in the PR body** rather than fixing it in this PR (out of scope).

5. **Scope adherence:**
   ```bash
   git diff --name-only develop..HEAD | grep -vE "^cognitive_castle/(cli|split_mega_files|hooks_cli)\.py$|^cognitive_castle/i18n/.*\.json$|^docs/superpowers/specs/"
   ```
   Expected: empty (or only the spec file).

## Risk

- **Low.** Three small renames + 14 trivial JSON edits.
- The deprecation-alias pattern is already proven in `hooks_cli.py` (`_state_dir()`, `_read_castle_env`).
- One possible test breakage: if any test sets `MEMPALACE_PYTHON` or `MEMPALACE_SOURCE_DIR` directly, they'll still work but emit a deprecation warning. If a test asserts "no stderr output," it could fail. Caught by the testing-strategy step 4 grep.
- The i18n change is the most user-impactful — non-English users now see correct instructions. Reverse the change is trivial if needed.

## Acceptance criteria

1. `grep -nE "_MEMPALACE_PROJECT_FILES" cognitive_castle/cli.py` returns 0.
2. `grep -nE "_CASTLE_PROJECT_FILES" cognitive_castle/cli.py` returns ≥ 3.
3. `grep -niE "mempalace init" cognitive_castle/i18n/*.json` returns 0.
4. `grep -niE "castle init" cognitive_castle/i18n/*.json | wc -l` returns 14.
5. Setting `MEMPALACE_PYTHON=<path>` and calling `_castle_python()`: returns the path AND logs `MEMPALACE_PYTHON is deprecated` to stderr (one-time per process).
6. Setting `CASTLE_PYTHON=<path>` and calling `_castle_python()`: returns the path with NO deprecation warning.
7. Setting both `CASTLE_PYTHON=A` and `MEMPALACE_PYTHON=B`: `_castle_python()` returns A, no warning (new takes precedence).
8. Same three behaviors verified for `CASTLE_SOURCE_DIR` / `MEMPALACE_SOURCE_DIR` in `split_mega_files.py`.
9. Focused suite: failed count ≤ 74 (post-#A baseline). If higher, document the cause; tests-sweep is PR #C.
10. `git diff --name-only develop..HEAD` lists only files matching the scope grep above (no scope creep).
11. PR commit count ≤ 2 (single commit + optional AC fix).
12. CLI still works: `castle init /tmp/x --yes` and `castle search "..."` end-to-end smokes succeed.
