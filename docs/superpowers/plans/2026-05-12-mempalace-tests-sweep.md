# Mempalace Tests Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate test-file usage of the `MempalaceConfig` back-compat alias to the canonical `CognitiveCastleConfig` name, plus the `MEMPALACE_ENTITY_LANGUAGES` env-var legacy name, plus conftest.py docstring/comment cosmetic cleanup. ~85-110 line changes across ~16 test files. Per spec `d9cac872`.

**Architecture:** Two-task plan. Task 1 (sonnet) runs a rule-driven `git grep`-based sed across all test files that use `MempalaceConfig`, plus targeted sed for the env var rename and conftest docstring/comment cleanup, then surgically restores the alias-self-test (which must continue using the old name to verify the alias works). Task 2 (haiku) verifies 12 ACs, pushes, opens PR.

**Tech Stack:** Bash, sed, git grep. No new deps. No production code touched.

---

## File structure

Modified in this PR (16 test files total — enumerated at impl time via `git grep -l "MempalaceConfig" tests/`):

Known-affected files (confirmed during spec review):
- `tests/conftest.py` — 3 `MempalaceConfig` refs + 3 docstring/comment lines about "MemPalace tests" / "mempalace imports"
- `tests/test_config.py` — 19 refs; PRESERVE the alias-self-test (lines 264-272)
- `tests/test_config_extra.py` — 11 refs
- `tests/test_entity_detector.py` — 10 `MempalaceConfig` + 4 `MEMPALACE_ENTITY_LANGUAGES` + 3 `mempalace/i18n/` comment refs
- `tests/test_embedding.py` — 4 refs
- `tests/test_mcp_server.py` — 2 refs
- `tests/test_layers.py`, `tests/test_cli.py`, `tests/test_repair.py`, `tests/test_hooks_cli.py`, `tests/test_miner.py`, `tests/test_corpus_origin_integration.py`, `tests/test_hall_detection.py` — counts vary (sed catches all)
- `tests/benchmarks/test_mcp_bench.py`, `tests/benchmarks/test_memory_profile.py`, `tests/benchmarks/conftest.py` — bench files, included for consistency

Preserved (DO NOT MODIFY):
- `tests/test_branding.py` — rebrand-guard negative assertions
- `tests/test_state_dir_migration.py` — legacy `~/.mempalace/` path fallback test
- `tests/test_config.py` lines 264-272 — the alias-self-test (sed touches them, then we re-revert)

Untouched:
- All production code under `cognitive_castle/`
- Any test file without `MempalaceConfig` refs

Reference (read but don't modify):
- `docs/superpowers/specs/2026-05-12-mempalace-tests-sweep-design.md` (commit `d9cac872`)

---

## Task 1: Apply migrations + restore alias-self-test + commit

**Files:**
- Create branch: `feat/mempalace-tests-sweep` from `develop`
- Modify: 16 test files (enumerated at runtime)

- [ ] **Step 1: Read the spec end-to-end**

```bash
cat docs/superpowers/specs/2026-05-12-mempalace-tests-sweep-design.md
```

Pay attention to: the rule-driven implementation strategy, the alias-self-test preservation (lines 264-272 of `test_config.py`), and the 3 categories of intentional refs that stay (rebrand guards, alias-self-test, legacy path test).

- [ ] **Step 2: Create the feature branch**

```bash
git checkout develop
git pull origin develop
git checkout -b feat/mempalace-tests-sweep
git log --oneline -3
```

Expected: clean tree on `feat/mempalace-tests-sweep`, recent commits include `d9cac872` (spec refine) and `7745da6a` (spec initial).

- [ ] **Step 3: Capture the alias-self-test before mutation**

The alias-self-test at `tests/test_config.py:264-272` will get caught by the sed. Capture its current content so we can restore it surgically afterward.

```bash
sed -n '263,273p' tests/test_config.py > /tmp/alias-self-test.bak
cat /tmp/alias-self-test.bak
```

Expected output:
```python

def test_mempalace_config_is_backward_compat_alias():
    """MempalaceConfig still importable as an alias to CognitiveCastleConfig."""
    from cognitive_castle.config import MempalaceConfig, CognitiveCastleConfig
    # Same class object (alias, not a separate class).
    assert MempalaceConfig is CognitiveCastleConfig
    # Instances of one are instances of the other.
    cfg = MempalaceConfig()
    assert isinstance(cfg, CognitiveCastleConfig)

```

If the test's location has drifted (line numbers shifted), find it via `grep -n "test_mempalace_config_is_backward_compat_alias" tests/test_config.py` and adjust the line range accordingly.

- [ ] **Step 4: Enumerate files for migration**

```bash
git grep -l "MempalaceConfig" tests/ > /tmp/files-to-migrate.txt
echo "Files to migrate:"
cat /tmp/files-to-migrate.txt
wc -l /tmp/files-to-migrate.txt
```

Expected: 16 file paths listed. Verify the list looks right — should include `tests/conftest.py`, `tests/test_config.py`, plus 14 others.

- [ ] **Step 5: Conftest cosmetic cleanup (before bulk sed)**

```bash
sed -i 's/MemPalace tests/Cognitive Castle tests/g' tests/conftest.py
sed -i 's/mempalace imports/cognitive_castle imports/g' tests/conftest.py
```

Verify:

```bash
grep -nE "MemPalace tests|mempalace imports" tests/conftest.py
```

Expected: 0 matches.

- [ ] **Step 6: Bulk MempalaceConfig migration**

```bash
while IFS= read -r f; do
    sed -i 's/MempalaceConfig/CognitiveCastleConfig/g' "$f"
done < /tmp/files-to-migrate.txt
```

Verify:

```bash
grep -rn "MempalaceConfig" tests/ | head -20
```

Expected: matches only in `tests/test_config.py` (the alias-self-test, which sed already mutated and we'll restore in Step 8).

- [ ] **Step 7: Env-var rename + i18n-comment fix in test_entity_detector.py**

```bash
sed -i 's/MEMPALACE_ENTITY_LANGUAGES/CASTLE_ENTITY_LANGUAGES/g' tests/test_entity_detector.py
sed -i 's|mempalace/i18n/|cognitive_castle/i18n/|g' tests/test_entity_detector.py
```

Verify:

```bash
grep -nE "MEMPALACE_ENTITY_LANGUAGES|mempalace/i18n/" tests/test_entity_detector.py
```

Expected: 0 matches.

- [ ] **Step 8: Restore the alias-self-test**

After Step 6's sed, `test_config.py:263-272` now looks like:

```python

def test_mempalace_config_is_backward_compat_alias():
    """CognitiveCastleConfig still importable as an alias to CognitiveCastleConfig."""
    from cognitive_castle.config import CognitiveCastleConfig, CognitiveCastleConfig
    # Same class object (alias, not a separate class).
    assert CognitiveCastleConfig is CognitiveCastleConfig
    # Instances of one are instances of the other.
    cfg = CognitiveCastleConfig()
    assert isinstance(cfg, CognitiveCastleConfig)

```

This is wrong on multiple levels (broken import, tautological assert, lost test intent). Restore using the backup from Step 3:

Use the `Edit` tool. First read the current state of the test in test_config.py (line numbers may have shifted by ±2 depending on what other edits happened):

```bash
grep -n "test_mempalace_config_is_backward_compat_alias" tests/test_config.py
```

This gives you the def line. Then use Edit to replace the broken post-sed content with the verbatim backup from `/tmp/alias-self-test.bak`:

The Edit's `old_string` (broken post-sed state):
```python
def test_mempalace_config_is_backward_compat_alias():
    """CognitiveCastleConfig still importable as an alias to CognitiveCastleConfig."""
    from cognitive_castle.config import CognitiveCastleConfig, CognitiveCastleConfig
    # Same class object (alias, not a separate class).
    assert CognitiveCastleConfig is CognitiveCastleConfig
    # Instances of one are instances of the other.
    cfg = CognitiveCastleConfig()
    assert isinstance(cfg, CognitiveCastleConfig)
```

The Edit's `new_string` (restored from backup):
```python
def test_mempalace_config_is_backward_compat_alias():
    """MempalaceConfig still importable as an alias to CognitiveCastleConfig."""
    from cognitive_castle.config import MempalaceConfig, CognitiveCastleConfig
    # Same class object (alias, not a separate class).
    assert MempalaceConfig is CognitiveCastleConfig
    # Instances of one are instances of the other.
    cfg = MempalaceConfig()
    assert isinstance(cfg, CognitiveCastleConfig)
```

The test function NAME (`test_mempalace_config_is_backward_compat_alias`) doesn't contain the substring `MempalaceConfig` (note: lower-case `mempalace`) so sed didn't touch the name itself — good.

- [ ] **Step 9: Verify the alias-self-test is correct**

```bash
pytest tests/test_config.py::test_mempalace_config_is_backward_compat_alias -v 2>&1 | tail -5
```

Expected: PASS. If FAIL, the restoration didn't work — re-read the test code and verify it matches the backup at `/tmp/alias-self-test.bak`.

- [ ] **Step 10: Verify branding negative-assertion tests still trigger correctly**

```bash
pytest tests/test_branding.py -v 2>&1 | tail -10
```

Expected: all PASS. `test_branding.py` should be UNCHANGED by this PR (no mempalace ref in test_branding.py is "MempalaceConfig" or "MEMPALACE_ENTITY_LANGUAGES" or in the cleaned conftest strings).

- [ ] **Step 11: Verify legacy-path test still passes**

```bash
pytest tests/test_state_dir_migration.py -v 2>&1 | tail -5
```

Expected: PASS. `test_state_dir_migration.py` should be UNCHANGED by this PR.

- [ ] **Step 12: Verify no production code modified**

```bash
git diff --name-only develop..HEAD | grep -v "^tests/" | grep -v "^docs/superpowers/specs/"
```

Expected: empty. If any file outside `tests/` appears, that's a scope violation.

- [ ] **Step 13: Focused suite run**

```bash
pytest tests/ --ignore=tests/benchmarks -q --tb=no 2>&1 | tail -3
```

Expected: failed count ≤ 74 (post-#B baseline). If higher, check the new failures:
- If a test failed because it asserted `MempalaceConfig` exists as a name in its imports — that's likely a test that genuinely tested the alias (other than the explicit alias-self-test). Investigate and either revert that test's migration or fix the assertion.
- If unrelated, document in the PR body.

- [ ] **Step 14: Commit**

```bash
git add tests/
git commit -m "$(cat <<'EOF'
test: migrate MempalaceConfig → CognitiveCastleConfig in test files (PR #C)

Per spec docs/superpowers/specs/2026-05-12-mempalace-tests-sweep-design.md
(commit d9cac872):

- ~85 MempalaceConfig refs across 16 test files migrated to canonical
  CognitiveCastleConfig name (the production alias still exists, so
  both names work identically; this is purely stylistic cleanup)
- MEMPALACE_ENTITY_LANGUAGES → CASTLE_ENTITY_LANGUAGES (5 refs in
  test_entity_detector.py)
- mempalace/i18n/ → cognitive_castle/i18n/ (3 docstring refs in
  test_entity_detector.py)
- conftest.py docstring + comments: "MemPalace tests" → "Cognitive
  Castle tests", "mempalace imports" → "cognitive_castle imports"

Preserved:
- tests/test_config.py::test_mempalace_config_is_backward_compat_alias
  (explicit alias verification — still uses MempalaceConfig to prove
  the alias works)
- tests/test_branding.py (rebrand-guard negative assertions)
- tests/test_state_dir_migration.py (legacy ~/.mempalace/ path test)

Third PR of a 4-PR cleanup series:
- #A: SOAR removal (PR #14, merged)
- #B: Production fixes (PR #15, merged)
- #C: This PR — tests sweep
- #D: Docs sweep (deferred)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 15: Report ready for Task 2**

Report:
- Branch: `feat/mempalace-tests-sweep`
- Commit SHA
- Number of files modified
- Number of `MempalaceConfig` → `CognitiveCastleConfig` substitutions
- Confirmation: alias-self-test restored + passes
- Confirmation: test_branding.py + test_state_dir_migration.py unchanged
- Focused suite count (failed/passed)
- Ready for Task 2 verification

---

## Task 2: Verify 12 ACs + push + open PR

**Files:**
- Read-only verification, except for surgical fixes if any AC fails.

- [ ] **Step 1: AC1 — conftest.py module docstring updated**

```bash
grep -nE "Cognitive Castle tests|MemPalace tests" tests/conftest.py
```

Expected: ≥ 1 match for "Cognitive Castle tests", 0 matches for "MemPalace tests".

- [ ] **Step 2: AC2 — conftest.py comment lines updated**

```bash
grep -nE "cognitive_castle imports|mempalace imports" tests/conftest.py
```

Expected: matches for "cognitive_castle imports", 0 matches for "mempalace imports".

- [ ] **Step 3: AC3 — conftest.py uses CognitiveCastleConfig**

```bash
grep -nE "MempalaceConfig|CognitiveCastleConfig" tests/conftest.py
```

Expected: matches for `CognitiveCastleConfig` only, no `MempalaceConfig`.

- [ ] **Step 4: AC4 — test_config.py alias-self-test preserved, all other usages migrated**

```bash
grep -nE "MempalaceConfig" tests/test_config.py
```

Expected: exactly 4 matches, all inside `test_mempalace_config_is_backward_compat_alias` (the import line + 2 assertions + 1 instantiation).

- [ ] **Step 5: AC5 — other test files use CognitiveCastleConfig only**

```bash
git grep -l "MempalaceConfig" tests/ | grep -v "^tests/test_config\.py$"
```

Expected: empty (no other files still reference `MempalaceConfig`).

- [ ] **Step 6: AC6 — env var migrated**

```bash
grep -rn "MEMPALACE_ENTITY_LANGUAGES" tests/
```

Expected: 0 matches.

```bash
grep -rn "CASTLE_ENTITY_LANGUAGES" tests/
```

Expected: ≥ 4 matches in test_entity_detector.py.

- [ ] **Step 7: AC7 — test_entity_detector.py i18n comment paths updated**

```bash
grep -nE "mempalace/i18n/" tests/test_entity_detector.py
```

Expected: 0 matches.

- [ ] **Step 8: AC8 — test_branding.py is UNCHANGED**

```bash
git diff develop..HEAD -- tests/test_branding.py | head -5
```

Expected: empty (no diff).

- [ ] **Step 9: AC9 — test_state_dir_migration.py is UNCHANGED**

```bash
git diff develop..HEAD -- tests/test_state_dir_migration.py | head -5
```

Expected: empty.

- [ ] **Step 10: AC10 — alias-self-test still passes**

```bash
pytest tests/test_config.py::test_mempalace_config_is_backward_compat_alias -v 2>&1 | tail -3
```

Expected: PASS.

- [ ] **Step 11: AC11 — focused suite stable**

```bash
pytest tests/ --ignore=tests/benchmarks -q --tb=no 2>&1 | tail -3
```

Expected: failed ≤ 74 (post-#B baseline). If higher, identify cause.

- [ ] **Step 12: AC12 — no production code modified**

```bash
git diff --name-only develop..HEAD | grep -v "^tests/" | head -5
```

Expected: empty.

- [ ] **Step 13: Push the branch**

```bash
git push -u origin feat/mempalace-tests-sweep
```

- [ ] **Step 14: Open the PR**

```bash
gh pr create --base develop --title "test: migrate MempalaceConfig usage to canonical name (PR #C of cleanup series)" --body "$(cat <<'EOF'
## Summary

PR #C of the 4-PR cleanup series — migrate test-file usage of the \`MempalaceConfig\` back-compat alias to the canonical \`CognitiveCastleConfig\` name. Plus one env-var rename + conftest.py cosmetic cleanup.

Per spec [\`2026-05-12-mempalace-tests-sweep-design.md\`](docs/superpowers/specs/2026-05-12-mempalace-tests-sweep-design.md) (commit d9cac872).

## What changed

- **~85 \`MempalaceConfig\` refs** across 16 test files migrated to \`CognitiveCastleConfig\`. The production alias remains in 4 modules (\`config.py\`, \`cli.py\`, \`layers.py\`, \`repair.py\`) so external consumers / future migration is preserved.
- **\`MEMPALACE_ENTITY_LANGUAGES\`** env var (5 refs in \`test_entity_detector.py\`) → \`CASTLE_ENTITY_LANGUAGES\` (production already supports both as primary + fallback).
- **\`mempalace/i18n/\`** docstring path (3 refs in \`test_entity_detector.py\`) → \`cognitive_castle/i18n/\`.
- **\`conftest.py\`**: module docstring "MemPalace tests" → "Cognitive Castle tests", comments "mempalace imports" → "cognitive_castle imports".

## Preserved (DO NOT MIGRATE)

- \`tests/test_config.py::test_mempalace_config_is_backward_compat_alias\` — explicitly asserts the alias works; still uses \`MempalaceConfig\`.
- \`tests/test_branding.py\` — rebrand-guard negative assertions (\`assert "MemPalace" not in output\`). Untouched.
- \`tests/test_state_dir_migration.py\` — tests the intentional \`~/.mempalace/\` fallback in \`_state_dir()\`. Untouched.

## Series progress

- ✅ #A: SOAR removal (PR #14)
- ✅ #B: Mempalace production fixes (PR #15)
- ← **#C: Mempalace tests sweep (this PR)**
- #D: Mempalace docs sweep

## Test plan

- [x] AC1-AC7: grep verifications (conftest/config/entity_detector all clean)
- [x] AC8-AC9: test_branding.py and test_state_dir_migration.py UNCHANGED (git diff empty)
- [x] AC10: alias-self-test still passes
- [x] AC11: focused suite stable (failed ≤ 74)
- [x] AC12: no production code modified

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 15: Report status**

If all 12 ACs pass, report:
- PR URL
- All 12 ACs PASS/FAIL
- Final focused-suite numbers
- Any surgical fixes done

User merges if happy.

---

## Self-Review

**Spec coverage:**
- AC1 (conftest docstring) → Task 2 Step 1 ✓
- AC2 (conftest comments) → Task 2 Step 2 ✓
- AC3 (conftest uses new name) → Task 2 Step 3 ✓
- AC4 (test_config preserves alias-self-test) → Task 2 Step 4 ✓
- AC5 (other files use new name) → Task 2 Step 5 ✓
- AC6 (env var renamed) → Task 2 Step 6 ✓
- AC7 (i18n comment paths) → Task 2 Step 7 ✓
- AC8 (test_branding unchanged) → Task 2 Step 8 ✓
- AC9 (test_state_dir_migration unchanged) → Task 2 Step 9 ✓
- AC10 (alias-self-test passes) → Task 1 Step 9 + Task 2 Step 10 ✓
- AC11 (focused suite) → Task 1 Step 13 + Task 2 Step 11 ✓
- AC12 (no production code) → Task 1 Step 12 + Task 2 Step 12 ✓

All 12 ACs mapped to verification steps.

**Placeholder scan:**
- The Step 8 alias-self-test restoration uses verbatim `old_string` and `new_string` content with full code blocks — concrete.
- The sed commands are all complete and runnable.
- No "TBD", "TODO", or vague "implement later".

**Type consistency:**
- N/A (test cleanup, no new types).

**Special risk noted:**
- Task 1 Step 13 might surface unexpected test failures from files whose `MempalaceConfig` usage was load-bearing (e.g., tests that import the symbol and then verify `__module__` attribute or similar). If that happens, the implementer's option is: (a) re-revert that specific file or (b) fix the assertion. The plan's Step 13 explicitly tells the implementer to investigate before continuing.

Plan complete and ready for execution.
