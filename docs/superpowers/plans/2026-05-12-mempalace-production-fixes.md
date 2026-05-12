# Mempalace Production Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the 3 small renames + 14 i18n string fixes specified in `c8638a6c` — rename `_MEMPALACE_PROJECT_FILES` → `_CASTLE_PROJECT_FILES`, rename `MEMPALACE_PYTHON` → `CASTLE_PYTHON` and `MEMPALACE_SOURCE_DIR` → `CASTLE_SOURCE_DIR` with deprecation aliases, change `mempalace init` → `castle init` in 14 i18n no_palace strings.

**Architecture:** Two-task plan. Task 1 (sonnet) applies all edits across 3 production files + 14 i18n files in one commit. Task 2 (haiku) verifies 12 ACs, pushes, opens PR.

**Tech Stack:** No new deps. ~30 lines production Python + 14 trivial JSON string edits.

---

## File structure

Modified in this PR (3 production + 14 i18n):

| Path | Change |
|---|---|
| `cognitive_castle/cli.py` | Rename `_MEMPALACE_PROJECT_FILES` → `_CASTLE_PROJECT_FILES` (3 occurrences: lines 46, 82, 221) |
| `cognitive_castle/split_mega_files.py` | Add `import sys` at module top; replace direct `os.environ.get("MEMPALACE_SOURCE_DIR")` with `_source_dir_default()` helper that supports CASTLE_SOURCE_DIR (current) + MEMPALACE_SOURCE_DIR (deprecated). Update argparse help text at line 242. |
| `cognitive_castle/hooks_cli.py` | Update `_castle_python()` to read CASTLE_PYTHON first, fall back to MEMPALACE_PYTHON with one-time deprecation warning via existing `_DEPRECATED_LEGACY_ENV_WARNED` set. Update docstring. |
| `cognitive_castle/i18n/be.json` | `no_palace` string: `mempalace init` → `castle init` |
| `cognitive_castle/i18n/de.json` | Same |
| `cognitive_castle/i18n/en.json` | Same |
| `cognitive_castle/i18n/es.json` | Same |
| `cognitive_castle/i18n/fr.json` | Same |
| `cognitive_castle/i18n/hi.json` | Same |
| `cognitive_castle/i18n/id.json` | Same |
| `cognitive_castle/i18n/it.json` | Same |
| `cognitive_castle/i18n/ja.json` | Same |
| `cognitive_castle/i18n/ko.json` | Same |
| `cognitive_castle/i18n/pt-br.json` | Same |
| `cognitive_castle/i18n/ru.json` | Same |
| `cognitive_castle/i18n/zh-CN.json` | Same |
| `cognitive_castle/i18n/zh-TW.json` | Same |

Untouched:
- All other production code (`mcp_server.py`, `searcher.py`, `config.py`, etc.)
- All tests (no tests reference these env vars or assert the i18n string content — verified during spec review)
- Backward-compat aliases (`MempalaceConfig`, `~/.mempalace/`, `mempalace.yml` filename) — intentional

Reference (read but don't modify):
- `docs/superpowers/specs/2026-05-12-mempalace-production-fixes-design.md` (commit `c8638a6c`) — source of truth

---

## Task 1: Apply all renames + i18n fixes

**Files:**
- Create branch: `feat/mempalace-production-fixes` from `develop`
- Modify: `cognitive_castle/cli.py`
- Modify: `cognitive_castle/split_mega_files.py`
- Modify: `cognitive_castle/hooks_cli.py`
- Modify: 14 files under `cognitive_castle/i18n/`

- [ ] **Step 1: Read the spec end-to-end**

```bash
cat docs/superpowers/specs/2026-05-12-mempalace-production-fixes-design.md
```

The spec has the verbatim before/after code for each file. Use it.

- [ ] **Step 2: Create the feature branch**

```bash
git checkout develop
git pull origin develop
git checkout -b feat/mempalace-production-fixes
git log --oneline -3
```

Expected: clean tree on `feat/mempalace-production-fixes`, recent commits include `c8638a6c` (spec refine).

- [ ] **Step 3: Rename `_MEMPALACE_PROJECT_FILES` → `_CASTLE_PROJECT_FILES` in `cli.py`**

Use `Edit` with `replace_all=True` on the single symbol substitution. The 3 occurrences are at lines 46, 82, 221.

```python
# Edit cognitive_castle/cli.py, replace all occurrences:
# old_string: "_MEMPALACE_PROJECT_FILES"
# new_string: "_CASTLE_PROJECT_FILES"
# replace_all: True
```

Verify:

```bash
grep -nE "_MEMPALACE_PROJECT_FILES" cognitive_castle/cli.py
grep -nE "_CASTLE_PROJECT_FILES" cognitive_castle/cli.py
```

Expected: 0 / 3.

- [ ] **Step 4: Update `cognitive_castle/split_mega_files.py`**

Use `Read` to confirm the current imports block + line 32 + line 242 state.

**4a.** Add `import sys` to the existing imports block at the top of the file. Place it alphabetically (after `import os`).

**4b.** Replace line 32:

```python
# Before:
LUMI_DIR = Path(os.environ.get("MEMPALACE_SOURCE_DIR", str(HOME / "Desktop/transcripts")))
```

With:

```python
def _source_dir_default() -> Path:
    """Resolve the transcript source dir, supporting both CASTLE_SOURCE_DIR (current)
    and MEMPALACE_SOURCE_DIR (legacy, deprecation-warned)."""
    new = os.environ.get("CASTLE_SOURCE_DIR", "")
    if new:
        return Path(new)
    old = os.environ.get("MEMPALACE_SOURCE_DIR", "")
    if old:
        print(
            "[split-mega-files] MEMPALACE_SOURCE_DIR is deprecated — "
            "rename to CASTLE_SOURCE_DIR. Reading legacy value for now.",
            file=sys.stderr,
        )
        return Path(old)
    return HOME / "Desktop/transcripts"


LUMI_DIR = _source_dir_default()
```

**4c.** Update line 242 (the argparse help text):

```python
# Before:
help="Source directory (default: MEMPALACE_SOURCE_DIR or ~/Desktop/transcripts)",
# After:
help="Source directory (default: CASTLE_SOURCE_DIR or ~/Desktop/transcripts; "
     "MEMPALACE_SOURCE_DIR is deprecated but still honored)",
```

Verify:

```bash
grep -nE "MEMPALACE_SOURCE_DIR|CASTLE_SOURCE_DIR" cognitive_castle/split_mega_files.py
```

Expected: 4 lines — 2 with `MEMPALACE_SOURCE_DIR` (in the helper's fallback + the argparse help text), 2 with `CASTLE_SOURCE_DIR` (helper's primary read + argparse help text).

- [ ] **Step 5: Update `cognitive_castle/hooks_cli.py`** — `_castle_python()` function

Use `Read` on lines 75-100 to see the current state.

The `_DEPRECATED_LEGACY_ENV_WARNED` set already exists at line 19 of this file. `sys` is already imported at line 13. Don't re-add either.

Use `Edit` to replace the function body. The current state (lines 75-98):

```python
def _castle_python() -> str:
    """Return the python interpreter that has cognitive_castle installed.

    When hooks are invoked by Claude Code, sys.executable may be the system
    python which lacks cognitive_castle and its deps.  Resolution order:
    1. MEMPALACE_PYTHON env var (explicit override)
    2. Venv python from package install path
    3. Editable install: venv/ sibling to cognitive_castle/
    4. sys.executable fallback
    """
    # Honor explicit override (used by shell hook wrappers)
    env_python = os.environ.get("MEMPALACE_PYTHON", "")
    if env_python and os.path.isfile(env_python) and os.access(env_python, os.X_OK):
        return env_python
```

Replace with:

```python
def _castle_python() -> str:
    """Return the python interpreter that has cognitive_castle installed.

    When hooks are invoked by Claude Code, sys.executable may be the system
    python which lacks cognitive_castle and its deps.  Resolution order:
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
```

Verify:

```bash
grep -n "MEMPALACE_PYTHON\|CASTLE_PYTHON" cognitive_castle/hooks_cli.py
```

Expected: 3 lines — docstring mentions both, code reads both. No bare `os.environ.get("MEMPALACE_PYTHON")` as the primary.

- [ ] **Step 6: Fix all 14 i18n `no_palace` strings**

Use a single shell loop to do the string replacement across all 14 files:

```bash
for f in cognitive_castle/i18n/*.json; do
  python3 -c "
import json, sys
path = sys.argv[1]
with open(path) as fp:
    data = json.load(fp)
if 'no_palace' in data:
    data['no_palace'] = data['no_palace'].replace('mempalace init', 'castle init')
with open(path, 'w') as fp:
    json.dump(data, fp, ensure_ascii=False, indent=4)
    fp.write('\n')
" "$f"
done
```

This loads each JSON, replaces the substring in the `no_palace` value (preserving all other localization), and writes back with consistent formatting.

Verify:

```bash
grep -nE "mempalace init" cognitive_castle/i18n/*.json
```

Expected: 0 matches.

```bash
grep -nE "castle init" cognitive_castle/i18n/*.json | wc -l
```

Expected: 14 (one per language file).

Diff sanity check:

```bash
git diff --stat cognitive_castle/i18n/
```

Expected: 14 files changed, ~14-30 insertions, ~14-30 deletions. If a JSON file's formatting changed significantly (re-indented, key reordered), the diff will be huge. If that happens, revert and use a more surgical sed-based approach instead:

```bash
for f in cognitive_castle/i18n/*.json; do
  sed -i 's/mempalace init/castle init/g' "$f"
done
```

The sed approach preserves the file exactly as it was, only changing the matched substring.

- [ ] **Step 7: Local sanity checks**

```bash
# Ruff
ruff check cognitive_castle/cli.py cognitive_castle/split_mega_files.py cognitive_castle/hooks_cli.py
```

Expected: clean. If `import sys` is flagged as unused in split_mega_files.py, that means the helper wasn't placed correctly — fix.

```bash
# Import-level sanity (catches syntax errors)
python3 -c "from cognitive_castle.cli import main; from cognitive_castle.hooks_cli import _castle_python; from cognitive_castle.split_mega_files import LUMI_DIR; print('OK')"
```

Expected: `OK`. If any import fails, fix before committing.

```bash
# No production code outside scope modified
git diff --name-only develop..HEAD | grep -vE "^cognitive_castle/(cli|split_mega_files|hooks_cli)\.py$|^cognitive_castle/i18n/.*\.json$"
```

Expected: empty.

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/
git commit -m "$(cat <<'EOF'
feat: rename remaining MEMPALACE_* identifiers + fix i18n broken strings (PR #B)

Per spec docs/superpowers/specs/2026-05-12-mempalace-production-fixes-design.md
(commit c8638a6c):

Production renames:
- _MEMPALACE_PROJECT_FILES → _CASTLE_PROJECT_FILES (internal, cli.py)
- MEMPALACE_SOURCE_DIR → CASTLE_SOURCE_DIR (split_mega_files.py)
  + deprecation alias: old name still read with one-time stderr warning
- MEMPALACE_PYTHON → CASTLE_PYTHON (hooks_cli.py)
  + deprecation alias using existing _DEPRECATED_LEGACY_ENV_WARNED set

i18n fix:
- 14 language files had no_palace error showing `mempalace init <dir>`
  (a command that doesn't exist). Now shows `castle init <dir>` in
  each localized form.

Second PR of a 4-PR cleanup series:
- #A: SOAR removal (PR #14, merged)
- #B: This PR — mempalace production fixes
- #C: Mempalace tests sweep (deferred)
- #D: Mempalace docs sweep (deferred)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 9: Report ready for Task 2**

Report:
- Branch: `feat/mempalace-production-fixes`
- Commit SHA
- Files modified: 3 .py + 14 .json
- All grep checks pass (verified at Step 7)
- Ready for Task 2 verification

---

## Task 2: Verify 12 ACs + push + open PR

**Files:**
- Read-only verification, except for surgical fixes if any AC fails.

- [ ] **Step 1: AC1+AC2 — `_CASTLE_PROJECT_FILES` rename**

```bash
echo "AC1: $(grep -cE "_MEMPALACE_PROJECT_FILES" cognitive_castle/cli.py) (expect 0)"
echo "AC2: $(grep -cE "_CASTLE_PROJECT_FILES" cognitive_castle/cli.py) (expect >= 3)"
```

- [ ] **Step 2: AC3+AC4 — i18n strings**

```bash
echo "AC3: $(grep -nE "mempalace init" cognitive_castle/i18n/*.json | wc -l) (expect 0)"
echo "AC4: $(grep -nE "castle init" cognitive_castle/i18n/*.json | wc -l) (expect 14)"
```

- [ ] **Step 3: AC5 — MEMPALACE_PYTHON deprecation alias works**

```bash
MEMPALACE_PYTHON=/usr/bin/python3 python3 -c "
from cognitive_castle.hooks_cli import _castle_python
result = _castle_python()
print(f'result={result}')
" 2>&1
```

Expected: prints `result=/usr/bin/python3` AND a stderr line containing `MEMPALACE_PYTHON is deprecated`.

- [ ] **Step 4: AC6 — CASTLE_PYTHON works without warning**

```bash
CASTLE_PYTHON=/usr/bin/python3 python3 -c "
from cognitive_castle.hooks_cli import _castle_python
result = _castle_python()
print(f'result={result}')
" 2>&1
```

Expected: prints `result=/usr/bin/python3` AND no `MEMPALACE_PYTHON is deprecated` in stderr.

- [ ] **Step 5: AC7 — CASTLE_PYTHON takes precedence over MEMPALACE_PYTHON**

```bash
CASTLE_PYTHON=/usr/bin/python3 MEMPALACE_PYTHON=/wrong/path python3 -c "
from cognitive_castle.hooks_cli import _castle_python
result = _castle_python()
print(f'result={result}')
" 2>&1
```

Expected: prints `result=/usr/bin/python3` (not `/wrong/path`) AND no deprecation warning.

- [ ] **Step 6: AC8 — Same three behaviors for SOURCE_DIR**

```bash
echo "--- MEMPALACE_SOURCE_DIR alone ---"
MEMPALACE_SOURCE_DIR=/tmp/x python3 -c "
from cognitive_castle.split_mega_files import LUMI_DIR
print(f'LUMI_DIR={LUMI_DIR}')
" 2>&1

echo "--- CASTLE_SOURCE_DIR alone ---"
CASTLE_SOURCE_DIR=/tmp/y python3 -c "
from cognitive_castle.split_mega_files import LUMI_DIR
print(f'LUMI_DIR={LUMI_DIR}')
" 2>&1

echo "--- Both set ---"
CASTLE_SOURCE_DIR=/tmp/y MEMPALACE_SOURCE_DIR=/tmp/z python3 -c "
from cognitive_castle.split_mega_files import LUMI_DIR
print(f'LUMI_DIR={LUMI_DIR}')
" 2>&1
```

Expected:
- MEMPALACE_SOURCE_DIR alone: `LUMI_DIR=/tmp/x` + deprecation warning
- CASTLE_SOURCE_DIR alone: `LUMI_DIR=/tmp/y` + no warning
- Both: `LUMI_DIR=/tmp/y` + no warning (new takes precedence)

- [ ] **Step 7: AC9 — Focused suite stability**

```bash
pytest tests/ --ignore=tests/benchmarks -q --tb=no 2>&1 | tail -3
```

Expected: failed count ≤ 74 (the post-#A baseline). If higher:
- Check if any new failure is caused by the renames. The brainstorm verified that zero tests reference `MEMPALACE_PYTHON`, `MEMPALACE_SOURCE_DIR`, `_MEMPALACE_PROJECT_FILES`, or the `mempalace init` string content. So new failures should be rare.
- If a new failure appears that's clearly caused by this PR, fix it surgically (don't punt to PR #C).
- If a new failure is unrelated, document it in the PR body.

- [ ] **Step 8: AC10 — Scope adherence**

```bash
git diff --name-only develop..HEAD | grep -vE "^cognitive_castle/(cli|split_mega_files|hooks_cli)\.py$|^cognitive_castle/i18n/.*\.json$"
```

Expected: empty output. If any other file appears, that's a scope violation.

- [ ] **Step 9: AC11 — Commit count ≤ 2**

```bash
git log --oneline develop..HEAD | wc -l
```

Expected: 1-2.

- [ ] **Step 10: AC12 — CLI smoke**

```bash
# Init a fresh tiny palace
rm -rf /tmp/castle-b-smoke && mkdir -p /tmp/castle-b-smoke/src
echo "# test note about authentication tokens" > /tmp/castle-b-smoke/src/note.md
castle --palace /tmp/castle-b-smoke/palace init /tmp/castle-b-smoke/src --yes 2>&1 | tail -3

# Search
castle --palace /tmp/castle-b-smoke/palace search "authentication" 2>&1 | head -10

# Cleanup
rm -rf /tmp/castle-b-smoke
```

Expected: init succeeds; search returns at least one result; no `mempalace init` or `MEMPALACE_*` strings in any output.

- [ ] **Step 11: Push the branch**

```bash
git push -u origin feat/mempalace-production-fixes
```

- [ ] **Step 12: Open the PR**

```bash
gh pr create --base develop --title "feat: rename remaining MEMPALACE_* identifiers + fix i18n broken strings (PR #B)" --body "$(cat <<'EOF'
## Summary

PR #B of a 4-PR cleanup series — small production-code fixes for the remaining \`MEMPALACE_*\` identifiers + the broken \`mempalace init\` strings in 14 i18n language files.

Per spec [\`2026-05-12-mempalace-production-fixes-design.md\`](docs/superpowers/specs/2026-05-12-mempalace-production-fixes-design.md) (commit c8638a6c).

## What changed

**Production renames (3 files):**
- \`_MEMPALACE_PROJECT_FILES\` → \`_CASTLE_PROJECT_FILES\` in \`cli.py\` (internal constant, no back-compat needed)
- \`MEMPALACE_SOURCE_DIR\` → \`CASTLE_SOURCE_DIR\` in \`split_mega_files.py\` (with deprecation alias)
- \`MEMPALACE_PYTHON\` → \`CASTLE_PYTHON\` in \`hooks_cli.py\` (with deprecation alias)

Both env-var renames keep the old name working with a one-time stderr deprecation warning, using the existing \`_DEPRECATED_LEGACY_ENV_WARNED\` pattern.

**i18n fix (14 files):**
- 14 language files had \`"no_palace": "<localized> mempalace init <dir>"\` — a non-existent command. Now shows \`castle init <dir>\` in each localized form.

## Series progress

- ✅ #A: SOAR removal (PR #14, merged)
- ← **#B: Mempalace production fixes (this PR)**
- #C: Mempalace tests sweep
- #D: Mempalace docs sweep

## Test plan

- [x] AC1-AC4: grep verification (constant renamed, i18n strings fixed)
- [x] AC5-AC8: env var deprecation aliases work (old + warning, new + no warning, new precedence)
- [x] AC9: focused suite stable (≤ 74 failed)
- [x] AC10: scope adherence (only 4 production files + 14 i18n files modified)
- [x] AC11: commit count ≤ 2
- [x] AC12: CLI smoke (init + search end-to-end)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 13: Report status**

If all 12 ACs pass, report:
- PR URL
- Confirmation of all 12 ACs
- Any AC fixes done (with brief description)
- Focused-suite failed count

User merges if happy.

---

## Self-Review

**Spec coverage:**
- AC1 (constant rename: 0 old) → Task 2 Step 1 ✓
- AC2 (constant rename: 3+ new) → Task 2 Step 1 ✓
- AC3 (i18n: 0 `mempalace init`) → Task 2 Step 2 ✓
- AC4 (i18n: 14 `castle init`) → Task 2 Step 2 ✓
- AC5 (MEMPALACE_PYTHON works + warns) → Task 2 Step 3 ✓
- AC6 (CASTLE_PYTHON works, no warn) → Task 2 Step 4 ✓
- AC7 (CASTLE_PYTHON > MEMPALACE_PYTHON) → Task 2 Step 5 ✓
- AC8 (SOURCE_DIR — same three) → Task 2 Step 6 ✓
- AC9 (focused suite stable) → Task 2 Step 7 ✓
- AC10 (scope) → Task 2 Step 8 ✓
- AC11 (commit count ≤ 2) → Task 2 Step 9 ✓
- AC12 (CLI smoke) → Task 2 Step 10 ✓

All 12 ACs mapped to verification steps.

**Placeholder scan:**
- The i18n loop in Task 1 Step 6 has two implementations (Python-based + sed-based fallback). Both are concrete and complete — not placeholders.
- The `_castle_python` rewrite shows full before + after code.
- The deprecation alias helper for `split_mega_files.py` shows full code.
- No "TBD", "TODO", or vague "implement later".

**Type consistency:**
- N/A (small rename PR, no new types).

Plan complete and ready for execution.
