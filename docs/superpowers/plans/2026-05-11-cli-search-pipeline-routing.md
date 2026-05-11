# CLI `castle search` Pipeline Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the `castle search` CLI entry through the same 3-stage retrieval pipeline that the MCP-path `search_memories` uses, so shell users get the same quality as agents.

**Architecture:** Single-function refactor in `cognitive_castle/searcher.py`. The body of `search()` becomes a thin wrapper that calls `_new_pipeline_search()` and prints results. Score label changes from `cosine=` to `score=` (the reranker score is not cosine). Many existing CLI tests patched `col.query` directly; those get rewritten to patch `_new_pipeline_search` instead. Tests for the now-removed `_warn_if_legacy_metric` branch are deleted (the new pipeline doesn't go through that path).

**Tech Stack:** Python 3.9+, pytest + capsys, unittest.mock.patch. No new dependencies.

---

## Reality vs spec deviations to note up front

- **Spec assumed** "existing tests scraping stdout keep passing." **Reality:** ~10 tests in `tests/test_searcher.py` patch `cognitive_castle.searcher.get_collection` or set `mock_col.query.return_value`. After the refactor, `search()` doesn't call `get_collection` or `col.query` directly — it calls `_new_pipeline_search`. Those tests need rewriting (mock the new function) or deletion (test concept no longer applies).
- **Tests to delete entirely:**
  - `test_search_warns_when_palace_uses_wrong_distance_metric` (lines 167-184)
  - `test_search_does_not_warn_when_palace_is_correctly_configured` (lines 185-197)
  - Reason: the new pipeline doesn't call `_warn_if_legacy_metric`. The legacy-metric warning was a pre-pipeline safety check on raw `col.query` results; the new pipeline doesn't need it.
- **Tests to rewrite (mock `_new_pipeline_search` instead of `col.query`):** ~8 tests in `TestSearchCLI` class (lines 105-201). Specific list at Task 2.

These deviations don't change the spec's intent — they just acknowledge the test-rewrite footprint.

---

## File structure

### Modified files

| File | Change |
|---|---|
| `cognitive_castle/searcher.py` | Replace body of `search()` (lines 184-258); call `_new_pipeline_search`. Score label `cosine=` → `score=`. Function signature unchanged. |
| `tests/test_searcher.py` | Rewrite ~8 CLI-search tests to patch `_new_pipeline_search`; delete 2 legacy-metric tests; rename `test_search_shows_cosine_score` → `test_search_shows_score` with new assertion; add new `test_cli_search_routes_through_new_pipeline`. |

### Possibly modified (cleanup)

| File | Change |
|---|---|
| `cognitive_castle/searcher.py` | If `_first_or_empty` or `_warn_if_legacy_metric` have no remaining callers after the refactor, delete them. Task 2 verifies. |

---

## Task 1: Refactor `search()` body + update affected tests (atomic)

**Files:**
- Modify: `cognitive_castle/searcher.py:184-258` (body of `search()`)
- Modify: `tests/test_searcher.py` (rewrite/delete affected tests; add new pipeline-dispatch test)

This task is intentionally one commit. The refactor and the test updates are tightly coupled — committing them separately leaves the test suite broken in the intermediate state.

- [ ] **Step 1: Write the new pipeline-dispatch test**

Append to `tests/test_searcher.py` (place it inside or alongside the `TestSearchCLI` class):

```python
def test_cli_search_routes_through_new_pipeline(tmp_path, capsys):
    """`castle search` (CLI) goes through the 3-stage pipeline, not legacy vector-only.

    Verified by patching `_new_pipeline_search` and checking it was called.
    Also confirms the printed output uses 'score=' not 'cosine='.
    """
    from unittest.mock import patch
    from cognitive_castle.searcher import search

    fake_hits = [
        {
            "id": "d1",
            "text": "JWT authentication notes",
            "score": 0.92,
            "wing": "auth",
            "room": "2026",
            "source_file": "/tmp/foo/notes.md",
        },
    ]
    with patch(
        "cognitive_castle.searcher._new_pipeline_search",
        return_value=fake_hits,
    ) as mock_pipeline:
        search("authentication", str(tmp_path / "palace"), n_results=5)

    # Confirm dispatch.
    mock_pipeline.assert_called_once()
    # The pipeline should be invoked with is_hook_call=False.
    kwargs = mock_pipeline.call_args.kwargs
    assert kwargs.get("is_hook_call") is False

    # Confirm printed output uses score= and not cosine=.
    captured = capsys.readouterr()
    assert "score=0.92" in captured.out
    assert "cosine=" not in captured.out
    # And the rest of the layout is preserved.
    assert 'Results for: "authentication"' in captured.out
    assert "JWT authentication notes" in captured.out
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:
```bash
pytest tests/test_searcher.py::test_cli_search_routes_through_new_pipeline -v
```

Expected: FAIL. The current `search()` does not call `_new_pipeline_search` (it calls `col.query` directly). The mock's `assert_called_once()` fails OR the output uses `cosine=` (also a failure).

- [ ] **Step 3: Refactor `search()` body in `cognitive_castle/searcher.py`**

Open `cognitive_castle/searcher.py`. Locate `def search(query: str, palace_path: str, ...)` at line 184. Replace the entire function body (lines 184-258, everything from the `def` line through the end of the function) with:

```python
def search(query: str, palace_path: str, wing: str = None, room: str = None, n_results: int = 5):
    """CLI entry point.

    Routes through the 3-stage pipeline (dense + FTS + KG-hop → fuse → rerank),
    same as `search_memories()`. Prints results to stdout in the legacy format
    so existing scraping tests keep working. Score shown is the cross-encoder
    reranker score, not cosine distance.

    Raises SearchError if the pipeline fails. Returns None either way (this is
    a print-only function — programmatic callers should use `search_memories`).
    """
    from .config import CognitiveCastleConfig
    cfg = CognitiveCastleConfig()

    try:
        hits = _new_pipeline_search(
            query, palace_path, wing, room, n_results, cfg, is_hook_call=False
        )
    except Exception as e:
        print(f"\n  Search error: {e}")
        raise SearchError(f"Search error: {e}") from e

    if not hits:
        print(f'\n  No results found for: "{query}"')
        return

    print(f"\n{'=' * 60}")
    print(f'  Results for: "{query}"')
    if wing:
        print(f"  Wing: {wing}")
    if room:
        print(f"  Room: {room}")
    print(f"{'=' * 60}\n")

    for i, hit in enumerate(hits, 1):
        text = hit.get("text") or hit.get("document", "")
        score = round(float(hit.get("score", 0.0)), 3)
        wing_name = hit.get("wing", "?")
        room_name = hit.get("room", "?")
        source = Path(hit.get("source_file", "?")).name

        print(f"  [{i}] {wing_name} / {room_name}")
        print(f"      Source: {source}")
        print(f"      Match:  score={score}\n")
        print(f"      {text}\n")
        print(f"  {'─' * 56}")
```

Notes on the change:
- The previous body called `get_collection(palace_path)` and `col.query(...)` directly, then built `hits` from `documents`/`metadatas`/`distances` lists.
- The new body delegates entirely to `_new_pipeline_search`.
- Score label is `score={score}` instead of `cosine={vec_sim}`.
- `_warn_if_legacy_metric(col)` call is gone (the new pipeline doesn't operate on a raw `col`).
- `_first_or_empty(...)` calls are gone (the new pipeline returns ready-to-use dicts).
- Result layout is structurally identical: header, optional Wing/Room lines, `=` separator, per-result block, `─` separator.

- [ ] **Step 4: Run the new test to verify it passes**

```bash
pytest tests/test_searcher.py::test_cli_search_routes_through_new_pipeline -v
```

Expected: PASS.

- [ ] **Step 5: Run the broader CLI search test class — expect many failures**

```bash
pytest tests/test_searcher.py::TestSearchCLI -v --tb=line 2>&1 | tail -25
```

Expected: many failures. The existing tests patch `cognitive_castle.searcher.get_collection` or set `mock_col.query.return_value`, which the new `search()` body doesn't use. These tests need rewriting.

Note which tests fail. The expected failure set:
- `test_search_prints_results`
- `test_search_with_wing_filter`
- `test_search_with_room_filter`
- `test_search_with_wing_and_room`
- `test_search_no_palace_raises` (may or may not fail depending on how `_new_pipeline_search` reacts to a missing palace)
- `test_search_no_results`
- `test_search_query_error_raises`
- `test_search_n_results`
- `test_search_shows_cosine_score`
- `test_search_warns_when_palace_uses_wrong_distance_metric`
- `test_search_does_not_warn_when_palace_is_correctly_configured`
- `test_search_handles_none_metadata_without_crash`

- [ ] **Step 6: Rewrite/delete affected tests in `tests/test_searcher.py`**

Locate the `TestSearchCLI` class (around line 100). For each test below, apply the indicated change. Refer to the full test bodies when editing — use `Read` first to see the current shape, then `Edit` to replace each.

**(a) `test_search_prints_results`** — rewrite to mock `_new_pipeline_search`:

```python
def test_search_prints_results(self, palace_path, capsys):
    """`search()` prints a header and per-result block when hits exist."""
    from unittest.mock import patch
    fake_hits = [{
        "id": "d1", "text": "drawer content", "score": 0.8,
        "wing": "w", "room": "r", "source_file": "f.md",
    }]
    with patch("cognitive_castle.searcher._new_pipeline_search", return_value=fake_hits):
        search("query", palace_path)
    captured = capsys.readouterr()
    assert 'Results for: "query"' in captured.out
    assert "drawer content" in captured.out
```

**(b) `test_search_with_wing_filter`** — confirm wing is passed through:

```python
def test_search_with_wing_filter(self, palace_path, capsys):
    from unittest.mock import patch
    with patch("cognitive_castle.searcher._new_pipeline_search", return_value=[]) as mock_p:
        search("q", palace_path, wing="auth")
    mock_p.assert_called_once()
    # 2nd positional arg after query was wing in the old API; the new helper
    # takes them in order (query, palace_path, wing, room, n_results, cfg, ...).
    args = mock_p.call_args.args
    assert "auth" in args  # wing="auth" passed somewhere
```

**(c) `test_search_with_room_filter`** — analogous to (b) with `room="2026"`:

```python
def test_search_with_room_filter(self, palace_path, capsys):
    from unittest.mock import patch
    with patch("cognitive_castle.searcher._new_pipeline_search", return_value=[]) as mock_p:
        search("q", palace_path, room="2026")
    mock_p.assert_called_once()
    args = mock_p.call_args.args
    assert "2026" in args
```

**(d) `test_search_with_wing_and_room`** — both filters:

```python
def test_search_with_wing_and_room(self, palace_path, capsys):
    from unittest.mock import patch
    with patch("cognitive_castle.searcher._new_pipeline_search", return_value=[]) as mock_p:
        search("q", palace_path, wing="auth", room="2026")
    mock_p.assert_called_once()
    args = mock_p.call_args.args
    assert "auth" in args
    assert "2026" in args
```

**(e) `test_search_no_palace_raises`** — confirm `SearchError` is still raised when the pipeline fails:

```python
def test_search_no_palace_raises(self, tmp_path):
    """If the palace doesn't exist, the pipeline raises; search() re-raises as SearchError."""
    from unittest.mock import patch
    from cognitive_castle.searcher import SearchError
    with patch(
        "cognitive_castle.searcher._new_pipeline_search",
        side_effect=Exception("no palace"),
    ):
        with pytest.raises(SearchError):
            search("q", str(tmp_path / "nonexistent"))
```

**(f) `test_search_no_results`** — empty hits prints "No results":

```python
def test_search_no_results(self, palace_path, capsys):
    from unittest.mock import patch
    with patch("cognitive_castle.searcher._new_pipeline_search", return_value=[]):
        search("q", palace_path)
    captured = capsys.readouterr()
    assert 'No results found for: "q"' in captured.out
```

**(g) `test_search_query_error_raises`** — pipeline raises → SearchError:

```python
def test_search_query_error_raises(self):
    from unittest.mock import patch
    from cognitive_castle.searcher import SearchError
    with patch(
        "cognitive_castle.searcher._new_pipeline_search",
        side_effect=Exception("boom"),
    ):
        with pytest.raises(SearchError, match="boom"):
            search("q", "/fake")
```

**(h) `test_search_n_results`** — confirm `n_results` reaches the pipeline:

```python
def test_search_n_results(self, palace_path, capsys):
    from unittest.mock import patch
    with patch("cognitive_castle.searcher._new_pipeline_search", return_value=[]) as mock_p:
        search("q", palace_path, n_results=3)
    mock_p.assert_called_once()
    # n_results is the 5th positional arg (query, palace_path, wing, room, n_results).
    args = mock_p.call_args.args
    assert 3 in args
```

**(i) Rename `test_search_shows_cosine_score` → `test_search_shows_score`:**

```python
def test_search_shows_score(self, capsys):
    """CLI output displays the reranker score with label `score=`, not `cosine=`."""
    from unittest.mock import patch
    fake_hits = [{
        "id": "d1", "text": "x", "score": 0.7,
        "wing": "w", "room": "r", "source_file": "f.md",
    }]
    with patch("cognitive_castle.searcher._new_pipeline_search", return_value=fake_hits):
        search("foo", "/fake/path")
    captured = capsys.readouterr()
    assert "score=0.7" in captured.out
    assert "cosine=" not in captured.out
```

**(j) DELETE `test_search_warns_when_palace_uses_wrong_distance_metric`** (lines 167-184). The new pipeline doesn't call `_warn_if_legacy_metric`. The legacy-metric warning was specific to the pre-pipeline raw `col.query` path. Use `Edit` with the complete old method body as `old_string` and an empty string would be invalid — instead, delete the method via finding its def line and removing through the next `def` or end of class.

To delete a method cleanly: use `Read` to find the method's exact span, then `Edit` with `old_string` = entire method (including the blank line before the next method) and `new_string` = empty.

**(k) DELETE `test_search_does_not_warn_when_palace_is_correctly_configured`** (lines 185-197). Same rationale.

**(l) `test_search_handles_none_metadata_without_crash`** (line 198) — rewrite to mock the pipeline returning a hit with missing metadata fields:

```python
def test_search_handles_none_metadata_without_crash(self, palace_path, capsys):
    """search() must not crash if a hit dict has missing keys."""
    from unittest.mock import patch
    fake_hits = [{
        "id": "d1", "text": "x", "score": 0.5,
        # Missing: wing, room, source_file
    }]
    with patch("cognitive_castle.searcher._new_pipeline_search", return_value=fake_hits):
        search("q", palace_path)  # should not raise
    captured = capsys.readouterr()
    # Defaults from .get() should appear.
    assert "?" in captured.out
```

- [ ] **Step 7: Run the rewritten test class — expect green**

```bash
pytest tests/test_searcher.py::TestSearchCLI -v --tb=short 2>&1 | tail -30
```

Expected: all rewritten tests pass. 2 tests (the two `_warn_if_legacy_metric` tests) are gone. The class should be ~10 tests now.

If any test still fails, read its body and figure out which patch pattern is wrong, then fix.

- [ ] **Step 8: Run the full `tests/test_searcher.py`**

```bash
pytest tests/test_searcher.py -v --tb=line 2>&1 | tail -20
```

Expected: all tests in the file pass (the `TestSearchMemories` class and `TestTokenize` were not affected by this change).

- [ ] **Step 9: Run focused regression check**

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```

Expected: ~215 failed, ~1277 passed (matching the pre-PR baseline). No NEW failures.

- [ ] **Step 10: Run ruff**

```bash
ruff check cognitive_castle/searcher.py tests/test_searcher.py
```

Expected: clean.

- [ ] **Step 11: Commit**

```bash
git add cognitive_castle/searcher.py tests/test_searcher.py
git commit -m "feat(cli): route castle search through the 3-stage retrieval pipeline"
```

---

## Task 2: Delete unused helpers (if any)

After Task 1, `_first_or_empty` and `_warn_if_legacy_metric` in `cognitive_castle/searcher.py` may have no callers. Confirm and delete cleanly.

**Files:**
- Modify: `cognitive_castle/searcher.py`

- [ ] **Step 1: Check if `_first_or_empty` is still used**

```bash
grep -n "_first_or_empty" cognitive_castle/ tests/ --include="*.py" -r
```

Expected: matches in `cognitive_castle/searcher.py` only (definition + call sites if any). If the only matches are the definition itself, it's dead code.

- [ ] **Step 2: Check if `_warn_if_legacy_metric` is still used**

```bash
grep -n "_warn_if_legacy_metric" cognitive_castle/ tests/ --include="*.py" -r
```

Expected: same as above — if only the definition remains, it's dead code.

- [ ] **Step 3: Delete `_first_or_empty` if dead**

If grep showed only the definition, find the function in `cognitive_castle/searcher.py` (look for `def _first_or_empty(`), `Read` to get its exact text, then `Edit` to remove the entire function definition (including its preceding blank line and trailing blank line for clean spacing).

- [ ] **Step 4: Delete `_warn_if_legacy_metric` if dead**

Same procedure for `_warn_if_legacy_metric`.

- [ ] **Step 5: Verify no new ruff F401 (unused) errors**

```bash
ruff check cognitive_castle/searcher.py
```

Expected: clean. If ruff complains about unused imports that supported the deleted helpers (e.g., a `warnings` import that's no longer used), remove those imports too.

- [ ] **Step 6: Run tests to confirm no regression**

```bash
pytest tests/test_searcher.py -q 2>&1 | tail -5
```

Expected: same pass count as after Task 1.

- [ ] **Step 7: Commit (skip if no deletions happened)**

If Task 2 deleted at least one helper:

```bash
git add cognitive_castle/searcher.py
git commit -m "chore(searcher): remove unused helpers after CLI pipeline routing"
```

If both helpers turned out to be still in use by something else, this task is a no-op. Skip the commit and proceed to Task 3.

---

## Task 3: Final acceptance verification

**Files:** none (verification only)

- [ ] **Step 1: Verify spec acceptance criteria**

Walk each spec acceptance criterion and confirm:

```bash
# AC1: search() calls _new_pipeline_search
grep -n "_new_pipeline_search" cognitive_castle/searcher.py | head -5

# AC2: CLI output uses score=
grep -n 'score=' cognitive_castle/searcher.py | head -3

# AC7: no col.query in search() body
grep -n "col\.query" cognitive_castle/searcher.py | head -3
# Expected: matches only inside other functions (not search()) — verify by checking line numbers
```

- [ ] **Step 2: New tests pass; existing tests still pass**

```bash
pytest tests/test_searcher.py::test_cli_search_routes_through_new_pipeline -v
pytest tests/test_searcher.py -q --tb=no 2>&1 | tail -3
```

Expected: new test passes; whole file passes; no NEW failures vs baseline.

- [ ] **Step 3: Full focused regression**

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```

Expected: 215 failed, 1277 passed (or better; deleted `_warn_if_legacy_metric` tests reduce both counts slightly). No NEW failures.

- [ ] **Step 4: Optional manual smoke**

Build a small palace, run a search, confirm format:

```bash
rm -rf /tmp/castle-cli-smoke && mkdir -p /tmp/castle-cli-smoke/sources
cat > /tmp/castle-cli-smoke/sources/note.md <<'EOF'
# Authentication

Notes about JWT authentication. We use HS256 with a 256-bit secret.
Tokens expire after 24 hours. Refresh tokens last 30 days. Every failed
authentication attempt is logged to security.log for analysis.
EOF

castle --palace /tmp/castle-cli-smoke/palace init /tmp/castle-cli-smoke/sources --yes --no-llm 2>&1 | tail -3
castle --palace /tmp/castle-cli-smoke/palace search "authentication" 2>&1 | head -20
```

Expected output contains:
- `Results for: "authentication"` header
- A per-result block with `Match:  score=<float>` (NOT `cosine=`)
- The drawer text from the note
- Final `─` separator

Cleanup:

```bash
rm -rf /tmp/castle-cli-smoke
```

(No commit — verification only.)

---

## Self-Review

**1. Spec coverage** — every spec acceptance criterion maps to a task:
- AC1 (search() calls _new_pipeline_search) → Task 1 Step 3 + Task 3 Step 1
- AC2 (CLI uses score= label) → Task 1 Step 3 + Task 3 Step 1
- AC3 (CLI output header/per-result/no-results preserved) → Task 1 Step 6 tests
- AC4 (new test passes) → Task 1 Step 4
- AC5 (existing tests pass with updates) → Task 1 Steps 7–8
- AC6 (full regression no new failures) → Task 1 Step 9 + Task 3 Step 3
- AC7 (no col.query in search() body) → Task 3 Step 1
- AC8 (git status clean) → implicit in commits

**2. Placeholder scan:** no "TBD"/"TODO"/"fill in later". Each step shows the actual code or command. The "rewrite tests" step in Task 1 has explicit code for each test. The cleanup task is conditional (only if helpers turn out to be dead code) — that's not a placeholder, it's a documented conditional path.

**3. Type consistency:**
- `_new_pipeline_search` signature `(query, palace_path, wing, room, n_results, cfg, is_hook_call=False)` matches what's in the source per the spec (lines 365+ of searcher.py).
- Result-dict keys `text`/`document`/`score`/`wing`/`room`/`source_file` consistent across all tests and the production code.
- `SearchError` import consistent (already exported from `cognitive_castle.searcher`).

**4. Known gaps requiring impl-time judgment:**
- Whether `_first_or_empty` / `_warn_if_legacy_metric` are dead code post-Task 1 — Task 2 verifies before deleting.
- Exact line numbers of the tests to delete in Task 1 Step 6 (j)(k) — given via `lines 167-184` and `lines 185-197` from the spec; implementer should `Read` to confirm before editing.
- Manual smoke at Task 3 Step 4 is optional. If the user/operator chooses to skip it, the task is still complete via the automated checks.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-11-cli-search-pipeline-routing.md`.
