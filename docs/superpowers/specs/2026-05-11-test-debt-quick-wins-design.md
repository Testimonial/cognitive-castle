# Test Debt Quick Wins — Categories A + B + C

**Date:** 2026-05-11
**Branch target:** develop
**Scope:** test-suite cleanup only. Fixes 3 specific files. No production code changed.

## Background

The focused-suite baseline post-PR #6 is 215 failures, 1276 passes. The failures decompose into ~6 categories of varying difficulty. The user has scoped this work to the three "quick win" categories that need no design judgment and no chroma policy decision:

- **A. `tests/test_readme_claims.py` (31 failures):** Every test fails with `FileNotFoundError: '/home/lbihari/cognitive-castle/cognitive-castle/<module>.py'`. The test file has a module-level constant `MEMPALACE_PKG = REPO_ROOT / "cognitive-castle"` (line 23) using a **dash**; the actual package directory is `cognitive_castle/` with an **underscore**.
- **B. `tests/test_known_entities_registry.py` (26 failures):** Every test fails with `AttributeError: module 'mempalace.miner' has no attribute X`. The test file has `from mempalace import miner` (line 15) and patches at `mempalace.miner.*` paths. The actual package is `cognitive_castle.miner`. The function being patched (`add_to_known_entities`) exists at `cognitive_castle/miner.py:529`.
- **C. `tests/test_embedding.py` (9 failures):** Every failing test references the ONNX-era API (`_resolve_providers`, `_build_ef_class`, etc.) that was removed when the project switched to sentence-transformers. The tests are testing code that no longer exists. The current `cognitive_castle.embedding` uses `SentenceTransformer` directly, not ONNX.

Fixing all three: ~66 failures recovered with three small, mechanical changes. No production code touched. No design judgment needed.

## Goals

1. `tests/test_readme_claims.py` passes (all 31 failing tests).
2. `tests/test_known_entities_registry.py` passes (all 26 failing tests).
3. The 9 ONNX-era stale tests in `tests/test_embedding.py` are deleted (test count drops by 9; failure count drops by 9).
4. Focused-suite failure count drops from 215 to ~149.
5. No production code changed.
6. No new test failures introduced.

## Non-goals

- Fixing categories D (ChromaDB-coupled tests, ~50–70 failures), E (`cognitive_cognitive_castle` typo files), F (mixed misc, ~80 failures). Those are separate future projects with their own design judgment calls (skip-vs-delete-vs-fix for chroma).
- Restoring deleted tests. The 9 ONNX-era tests test code that doesn't exist; restoring them would require restoring the ONNX backend, which is out of scope.
- Renaming the `MEMPALACE_PKG` constant cosmetically. Function over form; the value change (dash → underscore) is the critical fix.
- Changing the `~/.mempalace/` path strings in docstrings of `test_known_entities_registry.py`. Those are doc text, not module paths. The user's live palace data is still at `~/.mempalace/palace/` — see deferred work in earlier specs.

## Source of truth

- `tests/test_readme_claims.py:23` — `MEMPALACE_PKG = REPO_ROOT / "cognitive-castle"` (verified)
- `tests/test_known_entities_registry.py:15` — `from mempalace import miner` (verified)
- `cognitive_castle/miner.py:529` — `def add_to_known_entities(entities_by_category: dict, wing: str = None) -> str:` (verified; the function exists)
- `tests/test_embedding.py:17–104` — 9 ONNX-era tests: `test_auto_picks_cuda`, `test_auto_falls_to_cpu`, `test_cuda_missing_warns_with_gpu_extra`, `test_coreml_missing_warns_with_coreml_extra`, `test_dml_missing_warns_with_dml_extra`, `test_unknown_device_warns_once`, `test_onnxruntime_import_error_falls_back_to_cpu`, `test_get_embedding_function_caches_by_resolved_provider_tuple`, `test_describe_device_uses_resolved_effective_device` (verified by sampling stderr)
- `cognitive_castle/embedding.py` (current state) — uses `SentenceTransformer` from `sentence-transformers`, no `_resolve_providers` function, no `_EF_CACHE` constant, no `onnxruntime` import (verified earlier in session)

## File-by-file change list

### `tests/test_readme_claims.py`

One-line change at line 23:

```python
# Before:
MEMPALACE_PKG = REPO_ROOT / "cognitive-castle"

# After:
MEMPALACE_PKG = REPO_ROOT / "cognitive_castle"
```

The constant name `MEMPALACE_PKG` is stale but kept as-is to minimize the diff and avoid touching every usage site. (Renaming is cosmetic; the value fix is what makes the 31 tests pass.)

### `tests/test_known_entities_registry.py`

Two find-replaces. The actual production function is at `cognitive_castle.miner.add_to_known_entities`, so the test just needs to import / patch the correct module path.

```bash
sed -i 's/from mempalace import/from cognitive_castle import/g' tests/test_known_entities_registry.py
sed -i 's/mempalace\.miner/cognitive_castle.miner/g' tests/test_known_entities_registry.py
```

After this:
- `from mempalace import miner` → `from cognitive_castle import miner`
- Any `mock.patch("mempalace.miner.X")` → `mock.patch("cognitive_castle.miner.X")`
- Any `mempalace.miner.X` attribute reference → `cognitive_castle.miner.X`

**Out of scope (do NOT rebrand):**
- `~/.mempalace/` references in the docstring (lines 4, 8) — those are documentation text describing the path; the actual live palace data still lives there
- Test fixture data containing `"mempalace release"` literal string (line 200) — that's input text fed to the entity detector, not a module reference

### `tests/test_embedding.py`

Delete 9 ONNX-era test functions (lines approximately 17–104, depending on exact spans). The functions test attributes that don't exist on `cognitive_castle.embedding`:
- `_resolve_providers` — replaced by `_resolve_device` (different signature)
- `_EF_CACHE` — never replaced (sentence-transformers caches internally)
- `_build_ef_class` — never replaced
- `_WARNED` — never replaced

Specific test method names to delete (verified via earlier failure-list):
- `test_auto_picks_cuda`
- `test_auto_falls_to_cpu`
- `test_cuda_missing_warns_with_gpu_extra`
- `test_coreml_missing_warns_with_coreml_extra`
- `test_dml_missing_warns_with_dml_extra`
- `test_unknown_device_warns_once`
- `test_onnxruntime_import_error_falls_back_to_cpu`
- `test_get_embedding_function_caches_by_resolved_provider_tuple`
- `test_describe_device_uses_resolved_effective_device`

**Keep:**
- The `isolate_embedding_state` autouse fixture — it uses `hasattr` checks before manipulating attributes, so it's defensive against missing attributes. Newer tests use it.
- The two modern tests added during the SOTA work: `test_embedding_uses_config_default_model_when_unspecified` and `test_embedding_respects_config_override`. These should keep passing after the deletions.

After deletion, the file goes from ~13 tests to ~4 tests (9 ONNX gone + 2 SOTA-era + 2 helper config tests, depending on what else is there).

## Testing strategy

After each file change, run that file's tests and confirm:

```bash
pytest tests/test_readme_claims.py -v --tb=no -q  # expect 31+ passing
pytest tests/test_known_entities_registry.py -v --tb=no -q  # expect 26+ passing
pytest tests/test_embedding.py -v --tb=no -q  # expect modern tests still passing, ONNX tests gone
```

After all three changes, full focused regression:

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```

Expected: failed count drops from 215 to ~149 (down by ~66). Passed count goes up by ~57 net (26 + 31 from A+B, minus 9 deleted from C, plus 9 fewer failures from C = net +57 passes plus -9 total tests). The exact numbers depend on a few edge cases but should be in this ballpark.

## Risk

- **Trivial.** Three test-file changes. No production code touched. Each change is mechanical.
- If `cognitive_castle.miner.add_to_known_entities` doesn't actually behave the way `test_known_entities_registry.py` expects, some of the 26 tests will reveal a real production bug. Treat that as a finding, not a regression.
- If the 9 ONNX-era tests are somehow load-bearing (e.g., another test depends on them passing), regressions surface in the post-change full-suite run. Mitigate by running the full focused suite after all changes.

## Acceptance criteria

1. `pytest tests/test_readme_claims.py -q` passes all 31 currently-failing tests.
2. `pytest tests/test_known_entities_registry.py -q` passes all 26 currently-failing tests.
3. `tests/test_embedding.py` no longer contains the 9 ONNX-era test method definitions (verify with grep: `grep -n "def test_auto_picks_cuda\|def test_auto_falls_to_cpu\|def test_resolve_providers\|def test_coreml_missing\|def test_dml_missing\|def test_unknown_device_warns_once\|def test_onnxruntime_import_error\|def test_get_embedding_function_caches\|def test_describe_device_uses_resolved" tests/test_embedding.py` returns zero matches).
4. The autouse `isolate_embedding_state` fixture in `tests/test_embedding.py` is preserved.
5. The two modern tests (`test_embedding_uses_config_default_model_when_unspecified`, `test_embedding_respects_config_override`) in `tests/test_embedding.py` are preserved and pass.
6. Focused-suite full run shows failed count ≤ 150 (down from baseline 215). Passed count up to ~1330+.
7. No production code in `cognitive_castle/` was modified.
8. Three commits, one per category — keeps history readable.
