# ChromaDB Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the ChromaDB backend entirely from `cognitive_castle/` and its tests, plus the orphaned `.codex-plugin/` Codex CLI scaffolding. After this PR, Castle is LanceDB-only.

**Architecture:** Six-phase, tests-first deletion. Phase 1 deletes 4 chroma-only test files. Phase 2 cleans the chroma half of 4 mixed test files (`test_backends`, `test_repair`, `test_cli`, `test_mcp_server`). Phase 3 deletes the chroma backend code. Post-Phase-3 check verifies `test_dedup` and `test_closets` (whose failures were runtime chroma issues, likely resolved by Phase 3). Phase 4 deletes `migrate.py` and the chroma-only CLI subcommands. Phase 5 deletes `.codex-plugin/`. Phase 6 sweeps remaining chroma references in source markdown.

**Tech Stack:** No new dependencies. pytest, ruff. Pure deletion + minor refactor of `backends/registry.py` and `backends/__init__.py`.

---

## Reality vs spec notes

- **`backends/_utils.py`** is 61 lines, contains a generic `_normalize_get_collection_args` helper that is NOT chroma-specific. The spec said "if chroma-specific, delete; if generic, keep." Decision: **keep**. No edits in Phase 3.
- **`test_dedup.py`** and **`test_closets.py`** have 0 `chroma` text matches but produce runtime `chromadb.errors.NotFoundError: Collection [mempalace_drawers]` failures. After Phase 3 (chroma.py deleted, registry simplified), the registry will only have lancedb, so these tests should auto-correct to LanceDB. Handled as a post-Phase-3 verification (Task 7) rather than upfront cleanup.
- **`cli.py` line numbers** (verified by grep):
  - `cmd_migrate` at line 629
  - `cmd_repair` at line 702
  - `--mode max-seq-id` branch at line 720
  - `repair` subparser registration with `--mode {legacy,max-seq-id}` choices around lines 1236–1284
  - `--max-seq-id-sidecar` arg at line 1271
- **`backends/__init__.py`** has 4 chroma references (line 14 docstring, line 31 import, lines 47–48 `__all__`). All need removing.
- **`backends/registry.py`** has the chroma fallback block at lines 181–193 (verified) plus a `(``chroma``)` mention in the docstring at line 153.

---

## File structure

### Deleted files

| Path | Reason |
|---|---|
| `tests/test_empty_chromadb_results.py` | Chroma-only edge case test |
| `tests/test_migrate.py` | Tests the chroma migrate CLI |
| `tests/test_collection_metric_invariant.py` | Chroma collection metric invariants |
| `tests/test_hnsw_capacity.py` | Chroma HNSW index capacity |
| `cognitive_castle/backends/chroma.py` | The chroma backend (1243 lines) |
| `cognitive_castle/migrate.py` | Chroma-version migration (285 lines) |
| `.codex-plugin/` | Stale Codex CLI plugin scaffolding |

### Modified files

| Path | Change |
|---|---|
| `cognitive_castle/backends/__init__.py` | Remove ChromaBackend/ChromaCollection imports + `__all__` entries (4 line refs) |
| `cognitive_castle/backends/registry.py` | Remove chroma fallback block (lines 181–193); update docstring at line 153 |
| `cognitive_castle/cli.py` | Delete `cmd_migrate` function, `migrate` subparser, dispatch; delete `--mode max-seq-id` branch, `--max-seq-id-sidecar` arg, mode choice |
| `tests/test_backends.py` | Delete chroma-specific tests (~80 chroma matches in 924 lines) |
| `tests/test_repair.py` | Delete `test_max_seq_id_*` tests (~60 chroma matches in 684 lines) |
| `tests/test_cli.py` | Delete `test_cmd_migrate*` tests (~42 chroma matches in 1092 lines) |
| `tests/test_mcp_server.py` | Delete chroma-specific MCP tests (~8 chroma matches in 1162 lines) |
| `cognitive_castle/instructions/*.md`, `cognitive_castle/README.md`, `.claude-plugin/README.md` | Doc sweep for chroma references |

### Untouched

- `cognitive_castle/backends/_utils.py` — generic, kept
- `tests/test_dedup.py`, `tests/test_closets.py` — verified post-Phase-3 (no upfront edits)

---

## Task 1: Delete the 4 chroma-only test files

**Files:**
- Delete: `tests/test_empty_chromadb_results.py`
- Delete: `tests/test_migrate.py`
- Delete: `tests/test_collection_metric_invariant.py`
- Delete: `tests/test_hnsw_capacity.py`

- [ ] **Step 1: Baseline failure count**

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```

Capture the failed/passed counts. Expected: ~156 failed, ~1326 passed.

- [ ] **Step 2: Delete the files**

```bash
git rm tests/test_empty_chromadb_results.py tests/test_migrate.py tests/test_collection_metric_invariant.py tests/test_hnsw_capacity.py
```

- [ ] **Step 3: Confirm deletion**

```bash
ls tests/test_empty_chromadb_results.py tests/test_migrate.py tests/test_collection_metric_invariant.py tests/test_hnsw_capacity.py 2>&1
```

Expected: all four lines report `No such file or directory`.

- [ ] **Step 4: Run focused suite**

Note: the pytest `--ignore` flags for `test_collection_metric_invariant.py` and `test_hnsw_capacity.py` are now no-ops (their files no longer exist), but they remain harmless:

```bash
pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -3
```

Expected: failed count drops modestly (the four deleted files contributed test counts but not necessarily many failures — the two ignored ones never ran). Most importantly: no NEW failures introduced.

- [ ] **Step 5: Commit**

```bash
git commit -m "test: delete 4 chroma-only test files (test_empty_chromadb_results, test_migrate, test_collection_metric_invariant, test_hnsw_capacity)"
```

---

## Task 2: Clean `tests/test_backends.py` (~80 chroma matches in 924 lines)

**Files:**
- Modify: `tests/test_backends.py`

This file tests the backend abstraction layer. After Phase 3, only LanceDB will exist. Strategy: delete every test that explicitly references chroma; keep generic backend-abstraction tests if they don't depend on chroma.

- [ ] **Step 1: Baseline this file's failures**

```bash
pytest tests/test_backends.py -q --tb=no 2>&1 | tail -3
```

Capture pass/fail counts. Expected: ~42 passed, ~9 failed.

- [ ] **Step 2: Inventory chroma references**

```bash
grep -n "chroma\|Chroma\|ChromaBackend\|ChromaCollection\|CASTLE_BACKEND.*chroma" tests/test_backends.py | head -40
```

Capture the line numbers and categorize each match:
- **DELETE**: test functions whose name contains `chroma`, or whose body explicitly instantiates `ChromaBackend()`, or whose body sets `CASTLE_BACKEND=chroma`, or whose body asserts chroma-specific behavior.
- **KEEP & STRIP**: test functions whose name is backend-agnostic but whose body has incidental chroma references. Strip the chroma-specific assertions/fixtures.

- [ ] **Step 3: Identify test functions to delete vs strip**

Run:

```bash
grep -n "^def test_\|^    def test_\|^class Test" tests/test_backends.py | head -40
```

Walk each test function. For each one that appears in the chroma-reference list (Step 2), decide delete vs strip based on the criteria above.

Likely candidates for outright deletion (verify in-file):
- Any test with `chroma` in its name
- Tests that use `ChromaBackend` or `ChromaCollection` as the System Under Test
- Tests that depend on `chromadb.PersistentClient` or other chromadb-specific APIs

Likely candidates to keep (after stripping chroma-side):
- Backend-abstraction tests that have parametrized fixtures for both `chroma` and `lancedb` — keep the lancedb parametrize entries, drop the chroma ones
- Registry tests that just need to assert "lancedb is the default" (now with no chroma to fall back to)

- [ ] **Step 4: Apply the deletions/strips**

Use `Read` to fetch the exact text of each test to remove or modify. Use `Edit` to remove a whole function definition (`old_string` = full function span including preceding blank line, `new_string` = ""). For parametrize lists, use `Edit` to remove just the `"chroma"` entry.

- [ ] **Step 5: Run the file's tests**

```bash
pytest tests/test_backends.py -q --tb=line 2>&1 | tail -10
```

Expected: 0 (or near 0) failures. Some test counts will drop with the deletions. No errors.

If a test fails with an unexpected error (e.g., something that depends on the chroma module that's still in-tree at this phase), note it for re-verification post-Phase-3 — those failures may auto-resolve when chroma.py is gone. Document any such test in the commit message.

- [ ] **Step 6: Ruff**

```bash
ruff check tests/test_backends.py
```

Expected: clean. If unused imports remain (e.g., `from cognitive_castle.backends.chroma import ChromaBackend`), remove them.

- [ ] **Step 7: Commit**

```bash
git add tests/test_backends.py
git commit -m "test(backends): delete chroma-specific tests, keep LanceDB abstraction tests"
```

---

## Task 3: Clean `tests/test_repair.py` (~60 chroma matches in 684 lines)

**Files:**
- Modify: `tests/test_repair.py`

This file tests `castle repair`. The chroma-specific subset is the `--mode max-seq-id` path (chroma-only repair for a chroma version-mismatch bug).

- [ ] **Step 1: Baseline**

```bash
pytest tests/test_repair.py -q --tb=no 2>&1 | tail -3
```

Capture. Expected: ~12 passed, ~24 failed.

- [ ] **Step 2: Inventory chroma + max_seq_id references**

```bash
grep -n "max_seq_id\|max-seq-id\|chroma\|repair_max_seq_id" tests/test_repair.py | head -30
```

- [ ] **Step 3: Identify deletion targets**

Look for:
- `test_max_seq_id_*` functions — DELETE (the mode itself is being removed in Phase 4)
- Tests for `repair_max_seq_id` helper — DELETE
- Tests that use chroma fixtures or assert chroma-specific repair behavior — DELETE
- Tests with names like `test_repair_legacy_mode_*` — KEEP if they test the now-default repair logic; review individually

- [ ] **Step 4: Apply deletions**

Use `Read` then `Edit` per test function. Or use `Write` to rewrite the file end-to-end if more than ~50% of tests are getting deleted.

- [ ] **Step 5: Run the file's tests**

```bash
pytest tests/test_repair.py -q --tb=line 2>&1 | tail -10
```

Expected: near-zero failures, fewer total tests.

- [ ] **Step 6: Ruff**

```bash
ruff check tests/test_repair.py
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add tests/test_repair.py
git commit -m "test(repair): delete chroma-specific max-seq-id repair tests"
```

---

## Task 4: Clean `tests/test_cli.py` (~42 chroma matches in 1092 lines)

**Files:**
- Modify: `tests/test_cli.py`

This file tests the CLI dispatcher. The chroma-specific subset is `castle migrate` (deletes in Phase 4) and `castle repair --mode max-seq-id` (also deletes in Phase 4).

- [ ] **Step 1: Baseline**

```bash
pytest tests/test_cli.py -q --tb=no 2>&1 | tail -3
```

Capture.

- [ ] **Step 2: Inventory**

```bash
grep -n "cmd_migrate\|castle migrate\|max_seq_id\|max-seq-id\|migrate.py\|test_cmd_migrate" tests/test_cli.py | head -30
```

- [ ] **Step 3: Identify deletion targets**

- All `test_cmd_migrate*` functions → DELETE
- Any test that imports `from cognitive_castle.cli import cmd_migrate` → DELETE
- Tests that assert `castle migrate` is registered as a subcommand → DELETE
- Tests for `castle repair --mode max-seq-id` (verify by grep for `max-seq-id` literal in test bodies) → DELETE

- [ ] **Step 4: Apply deletions**

Use `Read` + `Edit` per function.

- [ ] **Step 5: Run the file's tests**

```bash
pytest tests/test_cli.py -q --tb=line 2>&1 | tail -10
```

- [ ] **Step 6: Ruff**

```bash
ruff check tests/test_cli.py
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_cli.py
git commit -m "test(cli): delete tests for chroma-coupled castle migrate + repair --mode max-seq-id"
```

---

## Task 5: Clean `tests/test_mcp_server.py` (~8 chroma matches in 1162 lines)

**Files:**
- Modify: `tests/test_mcp_server.py`

Only ~8 chroma matches in a big file — lighter cleanup.

- [ ] **Step 1: Baseline**

```bash
pytest tests/test_mcp_server.py -q --tb=no 2>&1 | tail -3
```

- [ ] **Step 2: Inventory**

```bash
grep -n "chroma\|Chroma\|ChromaBackend" tests/test_mcp_server.py
```

Likely only 8 matches — possibly all in one or two test methods. Read each test that hits a match.

- [ ] **Step 3: Identify deletion targets**

For each chroma match, decide:
- Is the chroma reference incidental (e.g., a string in a comment or docstring)? → Edit just that line/comment
- Is the chroma reference structural (e.g., test asserts chroma-specific behavior)? → DELETE the test function

- [ ] **Step 4: Apply edits**

`Read` + `Edit` per match.

- [ ] **Step 5: Run the file's tests**

```bash
pytest tests/test_mcp_server.py -q --tb=line 2>&1 | tail -10
```

- [ ] **Step 6: Ruff**

```bash
ruff check tests/test_mcp_server.py
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_mcp_server.py
git commit -m "test(mcp): delete chroma-specific MCP server tests"
```

---

## Task 6: Delete production chroma backend code

**Files:**
- Delete: `cognitive_castle/backends/chroma.py`
- Modify: `cognitive_castle/backends/__init__.py`
- Modify: `cognitive_castle/backends/registry.py`

After this task, the LanceDB backend is the only one registered. `CASTLE_BACKEND=chroma` becomes a no-op (the registry won't have it).

- [ ] **Step 1: Confirm no remaining external callers**

```bash
grep -rn "import chromadb\|from chromadb\|ChromaBackend\|ChromaCollection\|from .chroma\|from cognitive_castle.backends.chroma" cognitive_castle/ tests/ --include="*.py" 2>&1 | head -10
```

Expected: matches only inside the files we're about to modify or delete (`chroma.py` itself, `backends/__init__.py`, possibly `backends/registry.py`). If anything else has external references, STOP and report — those need to be addressed first.

- [ ] **Step 2: Delete `cognitive_castle/backends/chroma.py`**

```bash
git rm cognitive_castle/backends/chroma.py
```

- [ ] **Step 3: Update `cognitive_castle/backends/__init__.py`**

Use `Read` to see current content. Then `Edit` to:
- Remove the docstring line referring to `ChromaBackend` / `ChromaCollection` (line 14 area): the comment `* In-tree Chroma default: :class:`ChromaBackend`, :class:`ChromaCollection`.` → delete entirely
- Remove the import line: `from .chroma import ChromaBackend, ChromaCollection` (line 31)
- Remove `"ChromaBackend"` and `"ChromaCollection"` from `__all__` (lines 47-48)

After editing, verify:

```bash
grep -n "Chroma" cognitive_castle/backends/__init__.py
```

Expected: zero matches.

```bash
python3 -c "from cognitive_castle.backends import BaseBackend, BaseCollection; print('OK')"
```

Expected: `OK` (the kept exports still import).

- [ ] **Step 4: Update `cognitive_castle/backends/registry.py`**

Use `Read` to see current content around lines 153 and 181–193.

Edit the docstring at line 153: change `5. Default (``chroma``)` → `5. Default (``lancedb``)`. Verify other docstring lines for chroma references.

Delete lines 181–193 (the chroma fallback registration block):
```python
    """Register lancedb as the in-tree default; keep chroma as fallback."""
    # ... lancedb registration ...
    # Keep chroma registered so existing palaces can still be opened with
    # CASTLE_BACKEND=chroma, but it is no longer the default.
    try:
        from .chroma import ChromaBackend
    except ImportError:
        pass
    else:
        if "chroma" not in _registry:
            _registry["chroma"] = ChromaBackend
```

Replace with a simpler version that only registers lancedb. Use `Read` to get the exact text first, then `Edit` to remove the chroma-fallback portion while keeping the lancedb registration. Update the function's docstring to remove "keep chroma as fallback."

After editing:

```bash
grep -n "chroma\|Chroma" cognitive_castle/backends/registry.py
```

Expected: zero matches (or comment-only matches if you keep a historical note).

- [ ] **Step 5: Run the focused suite**

```bash
pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -3
```

Expected: significant failure-count drop. No new errors. Tests that previously failed with `chromadb.errors.NotFoundError` should now pass (they'll fall back to lancedb via the registry default).

If `tests/test_dedup.py` or `tests/test_closets.py` had failures before that are now resolved, great — that's Task 7's verification.

- [ ] **Step 6: Ruff**

```bash
ruff check cognitive_castle/backends/
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/backends/
git commit -m "feat(backends): remove ChromaDB backend (lancedb-only architecture)"
```

---

## Task 7: Verify `test_dedup.py` and `test_closets.py` post-Phase-3

**Files:** none (verification + targeted edits only if needed)

These two files have 0 chroma string matches but produced chroma runtime errors (`Collection [mempalace_drawers] does not exist`). After Phase 3 deleted chroma, the registry only has lancedb, so the runtime errors should be gone.

- [ ] **Step 1: Run both files**

```bash
pytest tests/test_dedup.py tests/test_closets.py -q --tb=line 2>&1 | tail -15
```

Capture pass/fail counts.

- [ ] **Step 2: Compare to pre-PR baseline**

Pre-PR baselines for these files (from the brainstorm inventory):
- `test_dedup.py`: 4 failed, 11 passed
- `test_closets.py`: 7 failed, 40 passed

Expected post-Phase-3: significantly fewer failures. Possibly zero.

- [ ] **Step 3: If failures remain, triage**

If any test still fails after chroma removal, read the failure:
- If the test asserts chroma-specific behavior (e.g., a specific error type from chromadb) → DELETE
- If the test's expected output changed because of the backend swap (e.g., asserts a chroma error message) → REWRITE to assert generic / LanceDB behavior
- If the test is failing for an unrelated reason (e.g., the test expected a feature that doesn't exist) → SKIP this PR; treat as pre-existing test debt

Make minimal edits. Don't bundle in unrelated cleanups.

- [ ] **Step 4: Commit only if edits were made**

```bash
git add tests/test_dedup.py tests/test_closets.py
git commit -m "test(dedup,closets): adapt to lancedb-only registry after chroma removal"
```

If both files pass without edits, no commit needed.

---

## Task 8: Delete `migrate.py` + `castle migrate` + `castle repair --mode max-seq-id`

**Files:**
- Delete: `cognitive_castle/migrate.py`
- Modify: `cognitive_castle/cli.py`

- [ ] **Step 1: Confirm no callers of migrate.py outside cli.py**

```bash
grep -rn "from cognitive_castle.migrate\|from .migrate\|import migrate" cognitive_castle/ tests/ --include="*.py" 2>&1 | head -5
```

Expected: matches only in `cli.py` (`from .migrate import ...`) — confirm before deleting.

- [ ] **Step 2: Delete `cognitive_castle/migrate.py`**

```bash
git rm cognitive_castle/migrate.py
```

- [ ] **Step 3: Remove `cmd_migrate` from `cli.py`**

Use `Read` to find `def cmd_migrate(args):` at line 629. Read the full function span (from `def cmd_migrate` through the start of the next `def` — likely `def cmd_repair_status` at line 694). The span is about 65 lines.

Use `Edit` to delete:
- The entire `cmd_migrate` function (line 629 through just before line 694)
- The associated import `from .migrate import ...` near the top of the file (if it exists; verify)
- The subparser registration: locate `sub.add_parser("migrate"` via grep, delete the whole `p_migrate = ...` block and its `add_argument` calls
- The dispatch entry: locate `args.command == "migrate"` or `"migrate": cmd_migrate` in the dispatch dict, delete that line

Verify with:

```bash
grep -n "migrate\|cmd_migrate" cognitive_castle/cli.py
```

Expected: zero matches (or only matches in unrelated contexts, like a comment that explains the rebrand history).

- [ ] **Step 4: Remove `--mode max-seq-id` from `cmd_repair`**

In `cli.py`:
- Find `def cmd_repair(args):` at line 702. Find the `--mode max-seq-id` branch at line 720:
  ```python
  if getattr(args, "mode", "legacy") == "max-seq-id":
      from .repair import repair_max_seq_id
      repair_max_seq_id(...)
  ```
  Delete this entire if-block (and the function call it contains, and any following `else` or `return` that's only needed because of the branch).
- Simplify `cmd_repair` to remove the mode dispatch — it now only does the legacy (default) path.
- Find the subparser registration around lines 1236–1284. Delete:
  - The `--mode` `choices=["legacy", "max-seq-id"]` argument
  - The `--max-seq-id-sidecar` argument (line 1271 area)
  - Any other `max-seq-id`-only argument
- Find any helper imports referenced only for max-seq-id (e.g., `from .repair import repair_max_seq_id`) and remove if no longer used

Verify:

```bash
grep -n "max_seq_id\|max-seq-id" cognitive_castle/cli.py
```

Expected: zero matches.

- [ ] **Step 5: Check `cognitive_castle/repair.py` for now-unused helpers**

```bash
grep -n "def repair_max_seq_id\|max_seq_id" cognitive_castle/repair.py
```

If `repair_max_seq_id` exists in `repair.py` and is no longer called, delete it from `repair.py`. Verify with another grep across the codebase that no other caller depends on it.

- [ ] **Step 6: Run the focused suite**

```bash
pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -3
```

Expected: same or fewer failures vs Task 7. Definitely no NEW failures.

Verify CLI:

```bash
castle --help 2>&1 | head -20
castle repair --help 2>&1 | head -20
```

Expected: `migrate` no longer in subcommand list. `castle repair --help` no longer mentions `--mode` or `--max-seq-id-sidecar`.

- [ ] **Step 7: Ruff**

```bash
ruff check cognitive_castle/cli.py cognitive_castle/repair.py
```

Expected: clean. Remove any newly-unused imports.

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/ tests/  # tests in case repair.py changes ripple
git commit -m "feat(cli): delete castle migrate subcommand + castle repair --mode max-seq-id (chroma-only)"
```

---

## Task 9: Delete `.codex-plugin/`

**Files:**
- Delete: `.codex-plugin/` (recursive)

- [ ] **Step 1: Confirm contents (for the commit message)**

```bash
ls -la .codex-plugin/
find .codex-plugin -type f | head -20
```

- [ ] **Step 2: Confirm no other code references it**

```bash
grep -rn "\.codex-plugin\|codex-plugin" cognitive_castle/ tests/ docs/ --include="*.py" --include="*.json" --include="*.md" 2>&1 | head -5
```

Expected: matches only in historical docs/specs (acceptable) — nothing in `cognitive_castle/` or `tests/`.

- [ ] **Step 3: Delete the directory**

```bash
git rm -r .codex-plugin/
```

- [ ] **Step 4: Verify**

```bash
ls .codex-plugin/ 2>&1
```

Expected: `No such file or directory`.

- [ ] **Step 5: Run focused suite (sanity)**

```bash
pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -3
```

Expected: no change vs Task 8. Codex scaffolding isn't loaded by any test.

- [ ] **Step 6: Commit**

```bash
git commit -m "chore: delete .codex-plugin/ (stale Codex CLI scaffolding, mempalace-branded, unused)"
```

---

## Task 10: Doc sweep for chroma references

**Files:**
- Modify: `cognitive_castle/instructions/*.md` (5 files)
- Modify: `cognitive_castle/README.md`
- Modify: `.claude-plugin/README.md`
- Possibly: module docstrings in `cognitive_castle/*.py` (limited — most were cleaned in PR #4)

- [ ] **Step 1: Inventory chroma references in the in-scope files**

```bash
grep -rn "chroma\|ChromaDB\|chromadb\|CASTLE_BACKEND=chroma" cognitive_castle/instructions/ cognitive_castle/README.md .claude-plugin/README.md
```

Capture each match. Categorize:
- **Replace with LanceDB-only language**: phrasing like "ChromaDB default" or "ChromaDB backend" → "LanceDB" (no fallback mention)
- **Preserve as historical**: "originally backed by ChromaDB" → keep; reword if it confusingly implies current state
- **Delete**: lines explaining `CASTLE_BACKEND=chroma` (the escape hatch no longer exists) → delete entirely

Also grep `cognitive_castle/*.py` docstrings briefly:

```bash
grep -rn "chroma\|ChromaDB" cognitive_castle/ --include="*.py" | head -10
```

If any docstrings still mention chroma (PR #4 cleaned most), update or delete.

- [ ] **Step 2: Walk each file**

Read each affected file, apply Edits per the categorization in Step 1.

- [ ] **Step 3: Final verification**

```bash
grep -rn "chroma\|ChromaDB\|chromadb" cognitive_castle/ .claude-plugin/ --include="*.py" --include="*.md" 2>&1 | head -10
```

Expected: ≤ 3 matches, each in a defensible historical context.

- [ ] **Step 4: Ruff/markdown sanity**

```bash
ruff check cognitive_castle/
```

Expected: clean. (Markdown isn't ruff's concern but Python docstring edits are.)

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/ .claude-plugin/
git commit -m "docs: sweep chroma references from instructions + READMEs (lancedb-only)"
```

---

## Task 11: Final acceptance verification

**Files:** none (verification only)

Walk the 11 spec acceptance criteria from `docs/superpowers/specs/2026-05-12-chroma-removal-design.md`.

- [ ] **Step 1: AC1 — chroma.py deleted**

```bash
ls cognitive_castle/backends/chroma.py 2>&1
```

Expected: `No such file or directory`.

- [ ] **Step 2: AC2 — no chroma imports or references in production code**

```bash
grep -rn "import chromadb\|from chromadb\|ChromaBackend\|ChromaCollection" cognitive_castle/ --include="*.py" 2>&1 | head -5
```

Expected: zero matches.

- [ ] **Step 3: AC3 — migrate.py deleted**

```bash
ls cognitive_castle/migrate.py 2>&1
```

Expected: `No such file or directory`.

- [ ] **Step 4: AC4 — castle migrate gone**

```bash
castle --help 2>&1 | grep -q "migrate" && echo "FAIL — migrate still present" || echo "OK — migrate gone"
```

Expected: `OK — migrate gone`.

- [ ] **Step 5: AC5 — castle repair --mode max-seq-id gone**

```bash
castle repair --help 2>&1 | grep -q "max-seq-id" && echo "FAIL — max-seq-id still present" || echo "OK — max-seq-id gone"
```

Expected: `OK — max-seq-id gone`.

- [ ] **Step 6: AC6 — 4 chroma-only test files gone**

```bash
ls tests/test_empty_chromadb_results.py tests/test_migrate.py tests/test_collection_metric_invariant.py tests/test_hnsw_capacity.py 2>&1
```

Expected: all four `No such file or directory`.

- [ ] **Step 7: AC7 — .codex-plugin/ gone**

```bash
ls .codex-plugin/ 2>&1
```

Expected: `No such file or directory`.

- [ ] **Step 8: AC8 — chroma references in in-scope source/docs ≤ 3**

```bash
grep -rn "chromadb\|ChromaDB" cognitive_castle/ --include="*.py" --include="*.md" 2>&1 | wc -l
```

Expected: ≤ 3.

- [ ] **Step 9: AC9 — focused regression failed ≤ 90**

```bash
pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -3
```

Expected: `failed` count ≤ 90 (down from baseline 156, a drop of ≥ 66).

- [ ] **Step 10: AC10 — manual smoke**

```bash
rm -rf /tmp/castle-chroma-removal-smoke && mkdir -p /tmp/castle-chroma-removal-smoke/sources
cat > /tmp/castle-chroma-removal-smoke/sources/note.md <<'EOF'
# Test Note

Some test content about authentication and tokens. Verifies that the
chroma removal didn't break the basic init → mine → search flow.
EOF
castle --palace /tmp/castle-chroma-removal-smoke/palace init /tmp/castle-chroma-removal-smoke/sources --yes --no-llm 2>&1 | tail -3
castle --palace /tmp/castle-chroma-removal-smoke/palace search "authentication" 2>&1 | head -20
rm -rf /tmp/castle-chroma-removal-smoke && echo "smoke cleaned"
```

Expected:
- `castle init` succeeds, mines 1 file into a fresh palace.
- `castle search` returns at least 1 result with a `score=` line.
- No chroma errors anywhere.

- [ ] **Step 11: AC11 — git status clean after a test run**

```bash
git status --short | head
```

Expected: only untracked files like `test_env/` (the smoke fixture from Step 10, if not cleaned).

(No commit. Verification only.)

---

## Self-Review

**1. Spec coverage** — every spec acceptance criterion maps to a verification step in Task 11:
- AC1 (chroma.py deleted) → Step 1
- AC2 (no chroma imports) → Step 2
- AC3 (migrate.py deleted) → Step 3
- AC4 (castle migrate gone) → Step 4
- AC5 (max-seq-id gone) → Step 5
- AC6 (4 test files deleted) → Step 6
- AC7 (.codex-plugin gone) → Step 7
- AC8 (≤3 chroma refs in docs) → Step 8
- AC9 (failed ≤ 90) → Step 9
- AC10 (manual smoke passes) → Step 10
- AC11 (git status clean) → Step 11

**2. Placeholder scan** — no "TBD"/"TODO". Per-test triage in Tasks 2–5 has explicit decision criteria (delete-vs-strip-vs-keep based on name/imports/body). Task 6's edits to `__init__.py` and `registry.py` reference specific line numbers verified in the recon step.

**3. Type consistency** — N/A (deletion plan, no new types introduced).

**4. Known gaps requiring impl-time judgment:**
- Tasks 2–5 (per-test triage) — each task gives the implementer criteria but expects them to walk individual tests. The criteria are concrete (test name contains `chroma`, body imports `ChromaBackend`, etc.).
- Task 6 Step 4 (registry.py edit) — the implementer needs to read the exact text around lines 181–193 and craft an Edit that preserves the lancedb registration while removing the chroma fallback. Concrete enough.
- Task 8 Step 5 (`repair.py` helper cleanup) — depends on what's actually in `repair.py`; the step has a conditional ("If `repair_max_seq_id` exists ...").

---

Plan complete and saved to `docs/superpowers/plans/2026-05-12-chroma-removal.md`.
