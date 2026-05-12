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

Brainstorm-time inventory locked the following file list:

**Files with `MempalaceConfig` usage:**
1. `tests/conftest.py` (1 import + 1 instantiation in fixture)
2. `tests/test_config.py` (~20 instantiations + the alias-self-test which is PRESERVED)
3. `tests/test_config_extra.py` (~12 occurrences)
4. `tests/test_embedding.py` (~4 occurrences)
5. `tests/test_entity_detector.py` (~6 `MempalaceConfig` + 4 `MEMPALACE_ENTITY_LANGUAGES`)
6. `tests/test_hall_detection.py` (~2 occurrences via fixture)
7. `tests/test_mcp_server.py` (~1 occurrence)
8. `tests/benchmarks/test_mcp_bench.py` (~1-2 occurrences)
9. `tests/benchmarks/test_memory_profile.py` (~1-2 occurrences)

**Other files to touch:**
- `tests/conftest.py:2,8,17` — three docstring/comment lines mentioning "MemPalace" / "mempalace imports"

## File-by-file change list

### `tests/conftest.py`

Three categories of edits, all in one file:

**a) Module docstring (line 2):**
```python
# Before:
conftest.py — Shared fixtures for MemPalace tests.
# After:
conftest.py — Shared fixtures for Cognitive Castle tests.
```

**b) Comment lines (lines 8 and 17):**
```python
# Before (line 8):
mempalace imports — so that module-level initialisations (e.g.
# After:
cognitive_castle imports — so that module-level initialisations (e.g.

# Before (line 17):
# ── Isolate HOME before any mempalace imports ──────────────────────────
# After:
# ── Isolate HOME before any cognitive_castle imports ───────────────────
```

**c) Import + fixture usage:**
```python
# Before (line 40):
from cognitive_castle.config import MempalaceConfig  # noqa: E402
# After:
from cognitive_castle.config import CognitiveCastleConfig  # noqa: E402

# Then any usages of `MempalaceConfig(...)` in fixtures become `CognitiveCastleConfig(...)`.
```

### `tests/test_config.py`

The whole-file `MempalaceConfig` → `CognitiveCastleConfig` migration applies EXCEPT for the alias-self-test at lines 264-270:

```python
def test_mempalace_config_is_backward_compat_alias():
    """MempalaceConfig still importable as an alias to CognitiveCastleConfig."""
    from cognitive_castle.config import MempalaceConfig, CognitiveCastleConfig

    assert MempalaceConfig is CognitiveCastleConfig

    cfg = MempalaceConfig()
```

This test must continue to use `MempalaceConfig` (lower-case `mempalace` in its name too) — it's the whole point. The test name `test_mempalace_config_is_backward_compat_alias` stays as-is too.

Implementation strategy: do a global file `sed -i 's/MempalaceConfig/CognitiveCastleConfig/g'`, then manually re-revert lines 264-270 back to using `MempalaceConfig`.

### `tests/test_config_extra.py`, `tests/test_embedding.py`, `tests/test_hall_detection.py`, `tests/test_mcp_server.py`, `tests/benchmarks/test_mcp_bench.py`, `tests/benchmarks/test_memory_profile.py`

Bulk `MempalaceConfig` → `CognitiveCastleConfig` substitution per file. No intentional uses of the alias remain in these files.

```bash
sed -i 's/MempalaceConfig/CognitiveCastleConfig/g' \
    tests/test_config_extra.py \
    tests/test_embedding.py \
    tests/test_hall_detection.py \
    tests/test_mcp_server.py \
    tests/benchmarks/test_mcp_bench.py \
    tests/benchmarks/test_memory_profile.py
```

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
