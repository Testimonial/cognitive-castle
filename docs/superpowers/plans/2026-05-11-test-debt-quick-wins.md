# Test Debt Quick Wins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut ~66 failures from the focused test-suite baseline by applying three mechanical fixes to three test files — pure rebrand-drift cleanup, no production code touched.

**Architecture:** Three independent commits, one per test file. Each is a small mechanical change: a one-line path constant fix, an import-path rebrand, and a deletion of stale tests. No interactions between tasks.

**Tech Stack:** pytest, sed.

---

## File structure

### Modified test files

| File | Change | Recovers |
|---|---|---|
| `tests/test_readme_claims.py` | Line 23: `"cognitive-castle"` → `"cognitive_castle"` (dash → underscore in package-dir constant value) | 31 failures |
| `tests/test_known_entities_registry.py` | Sed-driven rebrand: `mempalace.miner` → `cognitive_castle.miner` and `from mempalace import` → `from cognitive_castle import` | 26 failures |
| `tests/test_embedding.py` | Delete 9 ONNX-era stale test methods (lines 16–104). Keep `isolate_embedding_state` fixture (lines 1–15) and modern tests (lines 105+) | 9 failures (deleted, not fixed) |

No production code touched. No new files.

---

## Task 1: Fix `tests/test_readme_claims.py` — one-line path

**Files:**
- Modify: `tests/test_readme_claims.py:23`

The constant at line 23 has `"cognitive-castle"` (with a dash) but the actual package directory is `cognitive_castle` (with an underscore). Every test in the file does `MEMPALACE_PKG / "<module>.py"` which builds an invalid path → `FileNotFoundError`.

- [ ] **Step 1: Run the file's failing tests to capture the baseline**

```bash
pytest tests/test_readme_claims.py -q --tb=no 2>&1 | tail -3
```

Expected: ~31 failures, all `FileNotFoundError`.

- [ ] **Step 2: Apply the one-line fix**

Find this line in `tests/test_readme_claims.py`:

```python
MEMPALACE_PKG = REPO_ROOT / "cognitive-castle"
```

Change to:

```python
MEMPALACE_PKG = REPO_ROOT / "cognitive_castle"
```

(The constant name `MEMPALACE_PKG` stays — renaming it would touch every usage site for no functional benefit. The dash → underscore in the path value is the load-bearing fix.)

- [ ] **Step 3: Verify the file now passes**

```bash
pytest tests/test_readme_claims.py -q --tb=no 2>&1 | tail -3
```

Expected: significantly fewer failures (ideally 0; possibly a few unrelated ones if other claims in the README have drifted). The 31 `FileNotFoundError` failures should be gone.

- [ ] **Step 4: Quick ruff check**

```bash
ruff check tests/test_readme_claims.py
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add tests/test_readme_claims.py
git commit -m "test(readme-claims): fix package path (cognitive-castle -> cognitive_castle)"
```

---

## Task 2: Fix `tests/test_known_entities_registry.py` — import rebrand

**Files:**
- Modify: `tests/test_known_entities_registry.py` (mechanical find-replace)

The file has `from mempalace import miner` and patches at `mempalace.miner.*` paths. The actual package is `cognitive_castle.miner`. The target function `add_to_known_entities` exists at `cognitive_castle/miner.py:529`, so once the imports resolve correctly the tests should pass.

- [ ] **Step 1: Capture baseline failures**

```bash
pytest tests/test_known_entities_registry.py -q --tb=no 2>&1 | tail -3
```

Expected: ~26 failures, all `AttributeError: module 'mempalace.miner' has no attribute X`.

- [ ] **Step 2: Apply the rebrand**

```bash
sed -i 's/from mempalace import/from cognitive_castle import/g' tests/test_known_entities_registry.py
sed -i 's/mempalace\.miner/cognitive_castle.miner/g' tests/test_known_entities_registry.py
```

- [ ] **Step 3: Verify the replacements**

```bash
grep -n "mempalace\.miner\|from mempalace import" tests/test_known_entities_registry.py
```

Expected: zero matches (the sed removed all instances).

```bash
grep -n "cognitive_castle\.miner\|from cognitive_castle import" tests/test_known_entities_registry.py | head -5
```

Expected: the new names are present where the old ones used to be.

Note: the test file's docstring (lines 1–10) mentions `~/.mempalace/known_entities.json` and `~/.mempalace/`. Those are PATH STRINGS describing where data lives, not module imports. **Leave them alone** — they accurately document where the registry file is on disk (which we haven't migrated; see deferred work).

Similarly, line 200 has a literal test fixture string `"mempalace release"`. That's input data fed to the entity detector, not a module reference. **Leave it alone.**

```bash
grep -n "mempalace" tests/test_known_entities_registry.py
```

Expected: only matches in docstrings and fixture data (lines 1–10, line 200 area). No matches on module-path-shape strings like `mempalace.X` or `from mempalace`.

- [ ] **Step 4: Run the tests, confirm they pass**

```bash
pytest tests/test_known_entities_registry.py -q --tb=no 2>&1 | tail -3
```

Expected: passing count goes from 0 (or near-0) to 26+. Failure count drops to near-zero.

If a few tests still fail after the rebrand, that's a real production behavior mismatch (the test expectations don't match what `cognitive_castle.miner.add_to_known_entities` actually does). Treat those as findings — fix or surface in the commit message — don't ignore.

- [ ] **Step 5: Quick ruff check**

```bash
ruff check tests/test_known_entities_registry.py
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add tests/test_known_entities_registry.py
git commit -m "test(known-entities): migrate legacy mempalace.miner imports to cognitive_castle.miner"
```

---

## Task 3: Delete 9 ONNX-era stale tests from `tests/test_embedding.py`

**Files:**
- Modify: `tests/test_embedding.py` (delete 9 functions, ~90 lines)

The file currently has these test functions (verified by `grep -n "^def " tests/test_embedding.py`):
- Line 7: `def isolate_embedding_state(monkeypatch):` — **KEEP** (autouse fixture, uses `hasattr` defensively)
- Line 16: `def test_auto_picks_cuda(monkeypatch):` — **DELETE**
- Line 28: `def test_auto_falls_to_cpu(monkeypatch):` — **DELETE**
- Line 34: `def test_cuda_missing_warns_with_gpu_extra(monkeypatch, caplog):` — **DELETE**
- Line 41: `def test_coreml_missing_warns_with_coreml_extra(monkeypatch, caplog):` — **DELETE**
- Line 48: `def test_dml_missing_warns_with_dml_extra(monkeypatch, caplog):` — **DELETE**
- Line 55: `def test_unknown_device_warns_once(monkeypatch, caplog):` — **DELETE**
- Line 63: `def test_onnxruntime_import_error_falls_back_to_cpu(monkeypatch):` — **DELETE**
- Line 78: `def test_get_embedding_function_caches_by_resolved_provider_tuple(monkeypatch):` — **DELETE**
- Line 95: `def test_describe_device_uses_resolved_effective_device(monkeypatch):` — **DELETE**
- Line 105: `def test_embedding_uses_config_default_model_when_unspecified():` — **KEEP** (modern config-driven test)
- Line 115: `def test_embedding_respects_config_override():` — **KEEP** (modern config-driven test)
- Line 124: `def _make_default_cfg():` — **KEEP** (helper used by the two modern tests)

The 9 to delete span lines 16 through 104 (the last ONNX-era test ends just before line 105 where the first modern test begins).

- [ ] **Step 1: Capture baseline**

```bash
pytest tests/test_embedding.py -q --tb=no 2>&1 | tail -3
```

Expected: 9 failures (the ONNX tests) + 2 passes (the modern tests).

- [ ] **Step 2: Read the file to confirm line spans**

```bash
sed -n '1,20p' tests/test_embedding.py
```

Confirm:
- Line 1 imports.
- Line 5: `@pytest.fixture(autouse=True)` decorator for `isolate_embedding_state`.
- Line 7: `def isolate_embedding_state(monkeypatch):` start.
- Line 14 area: end of `isolate_embedding_state` body (blank line before next `def`).
- Line 16: `def test_auto_picks_cuda(monkeypatch):` — first to delete.

```bash
sed -n '100,130p' tests/test_embedding.py
```

Confirm:
- Around line 104: end of `test_describe_device_uses_resolved_effective_device` (last ONNX test).
- Line 105: blank line or start of `def test_embedding_uses_config_default_model_when_unspecified():`.

If line numbers are off by 1–2 (e.g., because of blank lines), adapt — find the def lines precisely with `grep -n "^def " tests/test_embedding.py` and use those.

- [ ] **Step 3: Delete the 9 ONNX-era test functions**

The cleanest path: use the Read tool to fetch the exact text of each function, then use Edit with `old_string` = entire function body (def line through final blank line before next def) and `new_string` = empty.

Or, more pragmatically: read the whole file, identify the line range `16` through the line just before line 105 (the first modern test), and use Write to rewrite the file without those lines.

Concretely: the new `tests/test_embedding.py` should consist of:
1. The original imports (lines 1–4)
2. The `@pytest.fixture(autouse=True)` decorator + `isolate_embedding_state` function (lines 5–14)
3. A blank line
4. The modern tests starting at the original line 105 (`test_embedding_uses_config_default_model_when_unspecified` onward)
5. The `_make_default_cfg` helper at the end

Use the Write tool. Read the file first to get the exact text of the KEEP sections, then Write the new content.

- [ ] **Step 4: Verify the deletions**

```bash
grep -n "def test_auto_picks_cuda\|def test_auto_falls_to_cpu\|def test_cuda_missing_warns_with_gpu_extra\|def test_coreml_missing_warns_with_coreml_extra\|def test_dml_missing_warns_with_dml_extra\|def test_unknown_device_warns_once\|def test_onnxruntime_import_error_falls_back_to_cpu\|def test_get_embedding_function_caches_by_resolved_provider_tuple\|def test_describe_device_uses_resolved_effective_device" tests/test_embedding.py
```

Expected: zero matches.

```bash
grep -n "^def " tests/test_embedding.py
```

Expected: shows `isolate_embedding_state`, `test_embedding_uses_config_default_model_when_unspecified`, `test_embedding_respects_config_override`, `_make_default_cfg` — and nothing else.

- [ ] **Step 5: Run tests, confirm modern ones still pass + ONNX failures gone**

```bash
pytest tests/test_embedding.py -v --tb=short 2>&1 | tail -15
```

Expected: 2 tests pass (`test_embedding_uses_config_default_model_when_unspecified`, `test_embedding_respects_config_override`). No failures. Total test count: 2.

- [ ] **Step 6: Quick ruff check**

```bash
ruff check tests/test_embedding.py
```

Expected: clean. If ruff complains about unused imports (e.g., the file may have imported `onnxruntime` or similar for the deleted tests), remove those.

- [ ] **Step 7: Commit**

```bash
git add tests/test_embedding.py
git commit -m "test(embedding): delete 9 ONNX-era stale tests (post-sentence-transformers migration cleanup)"
```

---

## Task 4: Final verification

**Files:** none (verification only)

After all three commits land, confirm the cumulative effect on the focused suite.

- [ ] **Step 1: Run focused regression**

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```

Expected: `~149 failed, ~1333 passed` (vs. baseline `215 failed, 1276 passed`).

The exact numbers may differ by a handful:
- Failures should be down by ~66 (31 + 26 + 9).
- Passes should be up by ~57 (31 + 26, minus 9 deleted tests).
- Total test count should be down by ~9 (deleted tests).

If failures didn't drop by ~66, something in the rebrand didn't take. Investigate by re-running the affected file's tests individually:

```bash
pytest tests/test_readme_claims.py -q --tb=line 2>&1 | tail -5
pytest tests/test_known_entities_registry.py -q --tb=line 2>&1 | tail -5
pytest tests/test_embedding.py -q --tb=line 2>&1 | tail -5
```

- [ ] **Step 2: Verify acceptance criteria from the spec**

Spec acceptance criterion 3 (no leftover ONNX-test def lines):

```bash
grep -n "def test_auto_picks_cuda\|def test_auto_falls_to_cpu\|def test_resolve_providers\|def test_coreml_missing\|def test_dml_missing\|def test_unknown_device_warns_once\|def test_onnxruntime_import_error\|def test_get_embedding_function_caches\|def test_describe_device_uses_resolved" tests/test_embedding.py
```

Expected: zero matches.

Spec acceptance criterion 6 (failure count ≤ 150):

The full-suite tail from Step 1. Confirm `failed` count is ≤ 150.

Spec acceptance criterion 7 (no production code modified):

```bash
git diff develop..HEAD --stat
```

Expected: only files under `tests/` (plus possibly `docs/`) listed. No `cognitive_castle/*.py` files.

- [ ] **Step 3: Quick visual sanity check on the three modified test files**

```bash
wc -l tests/test_readme_claims.py tests/test_known_entities_registry.py tests/test_embedding.py
```

Expected:
- `test_readme_claims.py`: ~same line count as before (one-character change).
- `test_known_entities_registry.py`: ~same line count as before (mechanical rename).
- `test_embedding.py`: ~40 lines (down from ~130 — the 9 deleted tests removed ~90 lines).

(No commit — verification only.)

---

## Self-Review

**1. Spec coverage** — every spec acceptance criterion maps to a step:
- AC1 (`test_readme_claims` 31 pass) → Task 1 Step 3
- AC2 (`test_known_entities_registry` 26 pass) → Task 2 Step 4
- AC3 (9 ONNX def lines gone) → Task 3 Step 4 + Task 4 Step 2
- AC4 (isolate_embedding_state fixture preserved) → Task 3 Step 4 (confirms via grep that the keeps are still there)
- AC5 (modern config tests preserved) → Task 3 Step 5 (runs all tests in file, must pass)
- AC6 (failed ≤ 150) → Task 4 Step 1
- AC7 (no production code) → Task 4 Step 2
- AC8 (three commits, one per category) → Task 1 Step 5, Task 2 Step 6, Task 3 Step 7

**2. Placeholder scan** — no "TBD"/"TODO". Each step shows actual commands or actual code/text. The one-character path change in Task 1 is shown verbatim. The Task 3 deletion strategy is concrete: "Read, identify spans, Write the new content without lines 16-104."

**3. Type consistency** — N/A (no code types involved; this is pure test-file editing).

**4. Known gaps requiring impl-time judgment:**
- Task 2 Step 4 mentions "If a few tests still fail after the rebrand, that's a real production behavior mismatch ... treat as findings." If 1–2 tests fail because production semantics changed (e.g., the `add_to_known_entities` signature took a `wing` parameter that didn't exist when these tests were written), the implementer should surface this and decide: skip the test, fix the test's expectations, or escalate.
- Task 3 Step 6 mentions "remove unused imports if ruff complains" — the file may currently import `onnxruntime` or similar for the now-deleted tests. The implementer should remove dead imports as part of the same commit.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-11-test-debt-quick-wins.md`.
