# Mempalace Tests Sweep — Design (PR #C of cleanup series)

**Date:** 2026-05-12
**Branch target:** develop
**Scope:** Migrate test-file usage of the `MempalaceConfig` backward-compat alias to the canonical `CognitiveCastleConfig` name, migrate one legacy env var name in `test_entity_detector.py`, and update conftest docstring/comments. ~85-95 line changes across 9 test files. **No production code touched.** **Preserves** the alias-self-test, the legacy-path test, and `test_branding.py` rebrand-guard assertions.

## Background

After PR #9 (mempalace import drift sweep) and PR #B (production fixes + i18n), 300 mempalace references still remain across tests/ — but most are intentional. The real residue worth migrating:

- **~85 `MempalaceConfig` import + instantiation refs** across 9 test files. The class is just `MempalaceConfig = CognitiveCastleConfig` at `cognitive_castle/config.py:643` — a back-compat alias. Tests use the old name from when MemPalace was the project name. Functionally equivalent, just stylistically stale.
- **5 `MEMPALACE_ENTITY_LANGUAGES` env var refs** in `tests/test_entity_detector.py`. Production at `config.py:221` reads `CASTLE_ENTITY_LANGUAGES` first with `MEMPALACE_ENTITY_LANGUAGES` as fallback. Tests using the old name still work via the fallback path.
- **3 docstring/comment refs** in `tests/conftest.py` mentioning "MemPalace tests" / "mempalace imports".

What's intentionally preserved:
- `test_branding.py` — negative assertions (`assert "MemPalace" not in output`) that guard the rebrand. KEEP.
- `test_config.py:264-270` — `test_mempalace_config_is_backward_compat_alias` specifically asserts the alias still works. KEEP using `MempalaceConfig` here.
- `test_state_dir_migration.py:8` — tests the `~/.mempalace/` legacy path fallback in `_state_dir()`. KEEP.
- Test-data path strings (`"mempalace-test"` as tmp path names) — no functional impact.

PR #C is the third of a 4-PR cleanup series:
- ✅ PR #A: SOAR removal (PR #14)
- ✅ PR #B: Mempalace production fixes (PR #15)
- ← **PR #C: Mempalace tests sweep (this spec)**
- PR #D: Mempalace docs sweep (deferred)

## Goals

1. Test imports use canonical `CognitiveCastleConfig` everywhere except the one alias-self-test.
2. Test env-var setups use canonical `CASTLE_ENTITY_LANGUAGES` everywhere.
3. `conftest.py` docstring + comments say "Cognitive Castle" rather than "MemPalace".
4. The 3 categories of intentional refs are preserved (test_branding negative asserts, alias-self-test, state_dir_migration legacy path test).
5. Focused suite: failed count ≤ 74 (post-#B baseline). No new regressions.
6. No production code under `cognitive_castle/` is modified.

## Non-goals

- Removing the `MempalaceConfig` alias from `cognitive_castle/config.py:643`. The alias exists for *external* test users / scripts that might import it. Keeping it is the whole reason to migrate internal tests to the canonical name — so we can later remove the alias when external usage tapers off.
- Aggressive cleanup of test-data path strings (`"mempalace-test"` as tmp path names). No functional impact; cosmetic-only changes raise risk-to-value ratio.
- Touching test files that don't have mempalace refs (the 80+ tests already cleaned in PR #9).
- Modifying production code, `MempalaceConfig` definition, `_DEPRECATED_LEGACY_ENV_WARNED` infrastructure, or any of the backward-compat aliases shipped in PR #5.
- Docs cleanup — PR #D handles that.
- Renaming `tests/conftest.py` or moving anything.

## Source of truth

Brainstorm-time inventory (corrected at spec-review time):

**Files with `MempalaceConfig` usage (16 files):**

| File | Refs |
|---|---|
| `tests/test_config.py` | 19 (includes the alias-self-test, PRESERVED) |
| `tests/test_config_extra.py` | 11 |
| `tests/test_entity_detector.py` | 10 + 4 `MEMPALACE_ENTITY_LANGUAGES` env var |
| `tests/test_embedding.py` | 4 |
| `tests/conftest.py` | 3 |
| `tests/test_mcp_server.py` | 2 |
| `tests/benchmarks/test_mcp_bench.py` | 2 |
| `tests/benchmarks/test_memory_profile.py` | 2 |
| `tests/benchmarks/conftest.py` | (count unverified — sed sweep catches it) |
| `tests/test_hall_detection.py` | 1 (docstring comment only) |
| `tests/test_layers.py` | (unverified — sed sweep catches it) |
| `tests/test_cli.py` | (unverified — sed sweep catches it) |
| `tests/test_repair.py` | (unverified — sed sweep catches it) |
| `tests/test_hooks_cli.py` | (unverified — sed sweep catches it) |
| `tests/test_miner.py` | (unverified — sed sweep catches it) |
| `tests/test_corpus_origin_integration.py` | (unverified — sed sweep catches it) |

**Note:** the spec was originally drafted with a 9-file list; spec self-review found 7 more files. The implementation strategy below uses `git grep -l "MempalaceConfig" tests/` to drive the sed — robust to the exact file list and to any new files added between spec and implementation.

**Production aliases that test patches may target:**
1. `cognitive_castle/config.py:643` — `MempalaceConfig = CognitiveCastleConfig`
2. `cognitive_castle/cli.py:43` — `MempalaceConfig = CognitiveCastleConfig`
3. `cognitive_castle/layers.py:30` — `MempalaceConfig = CognitiveCastleConfig`
4. `cognitive_castle/repair.py:34` — `MempalaceConfig = CognitiveCastleConfig`

Tests doing `@patch("cognitive_castle.cli.MempalaceConfig")` etc. must migrate to `@patch("cognitive_castle.cli.CognitiveCastleConfig")` (the patch target follows the test usage).

**Other tests/conftest.py docstring/comment lines:**
- Module docstring lines 1-11 mention "MemPalace tests" and "mempalace imports" (multi-line — needs broader sweep, not just line 2/8)
- Line 17 comment: `# ── Isolate HOME before any mempalace imports ──`

## File-by-file change list

### `tests/conftest.py`

Three categories of edits, all in one file:

**a) Module docstring (multi-line, lines 1-11):**
Replace `MemPalace tests` → `Cognitive Castle tests` (line 2) and `mempalace imports` → `cognitive_castle imports` (line 8). The docstring is multi-line — verify the exact line numbers at implementation time.

**b) Comment line 17:**
```python
# Before:
# ── Isolate HOME before any mempalace imports ──────────────────────────
# After:
# ── Isolate HOME before any cognitive_castle imports ───────────────────
```

**c) Import + fixture usage:**
The bulk sed in the next section handles all `MempalaceConfig` → `CognitiveCastleConfig` substitutions including conftest.py's import and fixture body.

Concrete sed for the conftest-specific cosmetic changes (run BEFORE the bulk sed):

```bash
sed -i 's/MemPalace tests/Cognitive Castle tests/g; s/mempalace imports/cognitive_castle imports/g' tests/conftest.py
```

### `tests/test_config.py`

The whole-file `MempalaceConfig` → `CognitiveCastleConfig` migration applies EXCEPT for the alias-self-test (verified at lines 264-272):

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

This test must continue to use `MempalaceConfig` (the test name retains lower-case `mempalace` too) — it's the whole point.

Implementation strategy: do `sed -i 's/MempalaceConfig/CognitiveCastleConfig/g' tests/test_config.py`, then surgically re-revert the alias-self-test function body (4 in-body `MempalaceConfig` references: 2 in the import line, 2 in the assertions/instantiation). The test function name `test_mempalace_config_is_backward_compat_alias` does NOT contain `MempalaceConfig` so it survives the sed unchanged.

### All other test files with `MempalaceConfig` (rule-driven)

Use `git grep` to enumerate the full file list at implementation time (catches drift between spec and implementation):

```bash
# Enumerate files (excluding test_config.py which gets surgical handling above):
git grep -l "MempalaceConfig" tests/ | grep -v "^tests/test_config\.py$" > /tmp/files-to-migrate.txt
cat /tmp/files-to-migrate.txt

# Apply bulk substitution:
while read f; do
    sed -i 's/MempalaceConfig/CognitiveCastleConfig/g' "$f"
done < /tmp/files-to-migrate.txt
```

Expected file list (16 files total, 15 after excluding test_config.py): `tests/conftest.py`, `tests/test_config_extra.py`, `tests/test_embedding.py`, `tests/test_entity_detector.py`, `tests/test_hall_detection.py`, `tests/test_mcp_server.py`, `tests/test_layers.py`, `tests/test_cli.py`, `tests/test_repair.py`, `tests/test_hooks_cli.py`, `tests/test_miner.py`, `tests/test_corpus_origin_integration.py`, `tests/benchmarks/test_mcp_bench.py`, `tests/benchmarks/test_memory_profile.py`, `tests/benchmarks/conftest.py`.

The sed handles `@patch("cognitive_castle.cli.MempalaceConfig")` etc. correctly — those patch-target strings get migrated to `@patch("cognitive_castle.cli.CognitiveCastleConfig")` and the production aliases at `cli.py:43`, `layers.py:30`, `repair.py:34`, `config.py:643` make both names work, so the patches still find a real attribute.

### `tests/test_entity_detector.py`

Two distinct substitutions:

```bash
sed -i 's/MempalaceConfig/CognitiveCastleConfig/g' tests/test_entity_detector.py
sed -i 's/MEMPALACE_ENTITY_LANGUAGES/CASTLE_ENTITY_LANGUAGES/g' tests/test_entity_detector.py
```

The function at line 418 has comments referencing `mempalace/i18n/` — those describe a path that doesn't exist (`mempalace/` directory). The comment is misleading. Update to `cognitive_castle/i18n/`:

```python
# Before (line 418):
"""Context manager that drops a locale JSON into mempalace/i18n/ for the test body.
# After:
"""Context manager that drops a locale JSON into cognitive_castle/i18n/ for the test body.

# Before (line 423):
Note: writes into the real mempalace/i18n/ directory. If a test process is
# After:
Note: writes into the real cognitive_castle/i18n/ directory. If a test process is

# Before (line 426):
Recover with `rm mempalace/i18n/zz-test-*.json`.
# After:
Recover with `rm cognitive_castle/i18n/zz-test-*.json`.
```

### Untouched

- `tests/test_branding.py` — all 13 refs are negative assertions (`assert "mempalace" not in ...`). DO NOT change.
- `tests/test_state_dir_migration.py` — 1 ref (`tmp_path / ".mempalace"`) tests intentional legacy fallback. DO NOT change.
- `tests/test_config.py:264-270` — alias-self-test specifically uses the old name. DO NOT change.
- All other test files without mempalace refs.
- All production code under `cognitive_castle/`.

## Testing strategy

1. **Alias-self-test still passes:**
   ```bash
   pytest tests/test_config.py::test_mempalace_config_is_backward_compat_alias -v
   ```
   Expected: PASS. If FAIL, the alias-self-test got accidentally migrated and needs re-revert.

2. **Legacy path test still passes:**
   ```bash
   pytest tests/test_state_dir_migration.py -v
   ```
   Expected: PASS.

3. **Branding negative assertions still trigger correctly:**
   ```bash
   pytest tests/test_branding.py -v
   ```
   Expected: PASS (no `MemPalace` strings should appear in CLI output).

4. **Focused suite stability:**
   ```bash
   pytest tests/ --ignore=tests/benchmarks -q --tb=no 2>&1 | tail -3
   ```
   Expected: failed count ≤ 74 (post-#B baseline). If higher, fix surgically.

5. **Verify mempalace refs eliminated (except preserved categories):**
   ```bash
   grep -rn "MempalaceConfig" tests/ | grep -v "test_config.py:[0-9]*: *MempalaceConfig" | head -10
   ```
   Expected: empty (no `MempalaceConfig` refs outside `test_config.py`'s alias-self-test region).

   ```bash
   grep -rn "MEMPALACE_ENTITY_LANGUAGES" tests/
   ```
   Expected: 0 matches.

   ```bash
   grep -nE "MemPalace tests|mempalace imports" tests/conftest.py
   ```
   Expected: 0 matches.

6. **Production code unchanged:**
   ```bash
   git diff --name-only develop..HEAD | grep "^cognitive_castle/"
   ```
   Expected: empty.

## Risk

- **Low.** Mechanical sed migration of an alias to its canonical name. The alias still exists and works identically; tests behave the same.
- **One risk vector**: accidentally migrating the alias-self-test, breaking the explicit alias-verification. Mitigated by: (a) the test will fail loudly if changed, (b) testing strategy step 1 explicitly verifies it.
- **No CI risk**: the `MempalaceConfig` alias remains in production. External test consumers (if any) are unaffected.

## Acceptance criteria

1. `tests/conftest.py` line 2 says "Cognitive Castle tests", not "MemPalace tests".
2. `tests/conftest.py` lines 8 and 17 say "cognitive_castle" rather than "mempalace".
3. `tests/conftest.py` imports `CognitiveCastleConfig` (not `MempalaceConfig`).
4. `tests/test_config.py` uses `CognitiveCastleConfig` everywhere EXCEPT inside `test_mempalace_config_is_backward_compat_alias` (lines 264-270), which still uses `MempalaceConfig` to verify the alias.
5. `tests/test_config_extra.py`, `tests/test_embedding.py`, `tests/test_hall_detection.py`, `tests/test_mcp_server.py`, `tests/test_entity_detector.py`, `tests/benchmarks/test_mcp_bench.py`, `tests/benchmarks/test_memory_profile.py` use `CognitiveCastleConfig` exclusively.
6. `tests/test_entity_detector.py` uses `CASTLE_ENTITY_LANGUAGES` (not `MEMPALACE_ENTITY_LANGUAGES`).
7. `tests/test_entity_detector.py` comments at lines 418-426 say `cognitive_castle/i18n/` instead of `mempalace/i18n/`.
8. `tests/test_branding.py` is UNCHANGED — all rebrand-guard assertions intact.
9. `tests/test_state_dir_migration.py` is UNCHANGED — legacy fallback test intact.
10. `tests/test_config.py::test_mempalace_config_is_backward_compat_alias` still passes (PRESERVED, not migrated).
11. Focused suite: failed ≤ 74 (post-#B baseline).
12. `git diff --name-only develop..HEAD` shows only files under `tests/` — no production code modified.
