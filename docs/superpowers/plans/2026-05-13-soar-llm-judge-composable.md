# SOAR ↔ LLM-judge Composable Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor SOAR from an external post-step (called from cli.py + mcp_server.py) into a proper in-pipeline stage inside `_new_pipeline_search`, and add a `--soar-first` CLI flag (matching `soar_first` MCP param) that flips Stage 4 ↔ Stage 5 invocation order from the default judge-then-SOAR to SOAR-then-judge.

**Architecture:** Two private helpers `_stage_4_judge(query, reranked, cfg)` and `_stage_5_soar(reranked, cfg)` extracted/added inside `searcher.py`. Both operate on `list[tuple[float, dict]]` (reranked-tuple shape from Stage 3). A new `_apply_soar_to_reranked(reranked, cfg)` in `soar_bridge.py` shares the rule-firing core with the existing `apply_soar_boosts(hits, cfg)` public API. Default ordering preserved; `--soar-first` opt-in with loud `sys.exit(2)` validation requiring both `--llm-rerank` and `--soar-boost`.

**Tech Stack:** Python 3.10+, pytest, existing Soar 9.6 + SML bindings (no new deps).

---

## Spec reference

`docs/superpowers/specs/2026-05-13-soar-llm-judge-composable-design.md` (commit `95422343`).

## File-level map

| File | Role | Net LOC change |
|---|---|---|
| `cognitive_castle/searcher.py` | Extract `_stage_4_judge` helper; add `_stage_5_soar` helper; add `soar_boost: bool` and `soar_first: bool` params to `search_memories()` + `_new_pipeline_search()`; thread through; add ordering branch | +60 / -15 |
| `cognitive_castle/soar_bridge.py` | Add `_apply_soar_to_reranked(reranked, cfg)` operating on tuples; share rule-firing core with `apply_soar_boosts` | +60 |
| `cognitive_castle/cli.py` | Add `--soar-first` argparse flag; in `cmd_search` add validation + remove the `if soar_boost: ... apply_soar_boosts` branch; pass `soar_boost` + `soar_first` through to `search()` | +25 / -30 |
| `cognitive_castle/mcp_server.py` | Add `soar_first: bool = False` to `tool_search`; add validation returning error response; remove the existing post-pipeline `if soar_boost: ... apply_soar_boosts` block (lines 421-435); pass `soar_boost` + `soar_first` through to `search_memories()` | +15 / -18 |
| `tests/test_soar_bridge.py` | Add `test_apply_soar_to_reranked_tuple_parity` + `test_apply_soar_to_reranked_returns_sorted_tuples` | +70 |
| `tests/test_pipeline_order.py` (new) | 6 tests for ordering logic | +180 |
| `tests/test_cli.py` | Add 3 CLI validation tests for `--soar-first` | +60 |
| `tests/test_mcp_server.py` | Add MCP validation test for `soar_first` | +35 |
| `CLAUDE.md` | Update retrieval pipeline diagram (line ~184) to show Stage 4 ↔ Stage 5 orderable | +3 / -1 |
| `README.md` | Brief mention of `--soar-first` in SOAR subsection | +12 |

**Total: ~470 LOC across 10 files** (some of this is test scaffolding; production code is ~150 LOC net add).

---

### Task 1: Branch setup

**Files:**
- None — repo-level operation

- [ ] **Step 1: Verify clean tree on develop**

Run: `git status && git rev-parse --abbrev-ref HEAD`
Expected: `develop` branch. Untracked `test_env/` is fine.

- [ ] **Step 2: Create feature branch**

Run: `git switch -c feat/soar-llm-judge-composable`
Expected: `Switched to a new branch 'feat/soar-llm-judge-composable'`

- [ ] **Step 3: Verify branch**

Run: `git rev-parse --abbrev-ref HEAD`
Expected: `feat/soar-llm-judge-composable`

No commit yet.

---

### Task 2: Extract `_stage_4_judge` helper (pure refactor, no behavior change)

**Files:**
- Modify: `cognitive_castle/searcher.py:497-507` (inline Stage 4 block)

**Why first:** The ordering branch in Task 7 needs to call Stage 4 in two different positions. Extracting it now keeps the diff focused and lets us add a tuple-parity test cheaply.

- [ ] **Step 1: Write the failing parity test**

Append to `tests/test_pipeline_order.py` (create if missing) — for now, just a guard verifying the refactor doesn't change behavior:

```python
"""Tests for SOAR ↔ LLM-judge composable ordering (PR #4b)."""

from __future__ import annotations

import pytest


def test_stage_4_judge_helper_exists_and_reorders(monkeypatch):
    """_stage_4_judge takes (query, reranked, cfg) and returns reordered top-N tuples."""
    from cognitive_castle.searcher import _stage_4_judge

    # Build a fake reranked list: 5 (score, row) tuples
    reranked = [
        (0.9, {"text": "doc A", "id": "a"}),
        (0.8, {"text": "doc B", "id": "b"}),
        (0.7, {"text": "doc C", "id": "c"}),
        (0.6, {"text": "doc D", "id": "d"}),
        (0.5, {"text": "doc E", "id": "e"}),
    ]

    # Fake config: top_n = 3
    class FakeCfg:
        llm_judge_top_n = 3
        llm_provider = "ollama"
        llm_model = "gemma3:4b"

    # Monkeypatch judge() to return a fixed permutation [2, 0, 1]
    import cognitive_castle.judge as judge_mod
    monkeypatch.setattr(judge_mod, "judge", lambda q, docs, cfg: [2, 0, 1])

    result = _stage_4_judge("test query", reranked, FakeCfg())
    # Top-3 reordered as [2, 0, 1] of the top-3 input
    assert len(result) == 3
    assert result[0][1]["id"] == "c"
    assert result[1][1]["id"] == "a"
    assert result[2][1]["id"] == "b"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_pipeline_order.py::test_stage_4_judge_helper_exists_and_reorders -v`
Expected: FAIL — `ImportError: cannot import name '_stage_4_judge' from 'cognitive_castle.searcher'`

- [ ] **Step 3: Extract the helper in `cognitive_castle/searcher.py`**

Locate the current inline Stage 4 block at lines 496-507:

```python
    # ── Stage 4 (optional): LLM-as-judge re-rank ───────────────────────────
    if llm_rerank:
        from .judge import judge

        # Take top-N (cfg.llm_judge_top_n) from Stage 3 output for LLM judging.
        # Stage 3 already returned a sorted list (most-relevant first).
        top_n = cfg.llm_judge_top_n
        judge_pool = reranked[:top_n]
        judge_docs = [_extract_text(r) for _, r in judge_pool]
        new_order = judge(query, judge_docs, cfg)
        # Reorder judge_pool by the LLM's preferred indices.
        reranked = [judge_pool[i] for i in new_order]
```

Replace with:

```python
    # ── Stage 4 (optional): LLM-as-judge re-rank ───────────────────────────
    if llm_rerank:
        reranked = _stage_4_judge(query, reranked, cfg)
```

Add the helper as a module-level function in `searcher.py` (right before `_new_pipeline_search`):

```python
def _stage_4_judge(
    query: str,
    reranked: list[tuple[float, dict]],
    cfg,
) -> list[tuple[float, dict]]:
    """Stage 4: LLM-as-judge re-rank.

    Truncates ``reranked`` to ``cfg.llm_judge_top_n``, then asks the LLM to
    reorder. Returns the reordered top-N tuples (the rest are discarded —
    same behavior as the inline block this replaces).

    On any LLM failure, the underlying ``judge.judge()`` returns identity
    order, so this helper preserves the input top-N order.
    """
    from .judge import judge

    top_n = cfg.llm_judge_top_n
    judge_pool = reranked[:top_n]
    judge_docs = [_extract_text(r) for _, r in judge_pool]
    new_order = judge(query, judge_docs, cfg)
    return [judge_pool[i] for i in new_order]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_pipeline_order.py::test_stage_4_judge_helper_exists_and_reorders -v`
Expected: PASS

- [ ] **Step 5: Run wider tests to verify no behavior change**

Run: `pytest tests/test_retrieval_pipeline.py tests/test_searcher.py 2>&1 | tail -5`
Expected: Same pass/fail counts as develop baseline (no NEW failures from the refactor).

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/searcher.py tests/test_pipeline_order.py
git commit -m "$(cat <<'EOF'
refactor(searcher): extract _stage_4_judge helper from inline block

Pure refactor — no behavior change. Stage 4 inline at searcher.py:497-507
becomes a 1-line call to _stage_4_judge(query, reranked, cfg). The helper
operates on the same (score, row) tuple shape Stage 3 produces.

Preparatory for PR #4b's ordering branch (Task 7), which needs to call
Stage 4 in two positions depending on --soar-first.

Test parity verified: tests/test_pipeline_order.py new file with
test_stage_4_judge_helper_exists_and_reorders.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Add `_apply_soar_to_reranked` in soar_bridge.py (operates on tuples)

**Files:**
- Modify: `cognitive_castle/soar_bridge.py` (add new internal function)
- Modify: `tests/test_soar_bridge.py` (add parity + sort tests)

- [ ] **Step 1: Write the failing parity test**

Append to `tests/test_soar_bridge.py`:

```python
def test_apply_soar_to_reranked_tuple_parity(monkeypatch, tmp_path):
    """_apply_soar_to_reranked on tuples produces same boost decisions as
    apply_soar_boosts on the equivalent dict hits."""
    from cognitive_castle import soar_bridge

    # Build paired inputs: same data in both shapes
    rows = [
        {
            "id": f"id-{i}",
            "score": 1.0 - i * 0.1,
            "wing": "project-a",
            "room": "room-1",
            "source_file": "f.md",
            "created_at": "2026-05-10T00:00:00Z",
        }
        for i in range(3)
    ]
    hits_dict = [
        {**r, "text": "doc", "document": "doc"}
        for r in rows
    ]
    reranked_tuples = [(r["score"], dict(r, text="doc", document="doc")) for r in rows]

    cfg = _mock_cfg(palace_path=str(tmp_path))

    # Call both APIs
    boosted_dict = soar_bridge.apply_soar_boosts(hits_dict, cfg)
    boosted_tuples = soar_bridge._apply_soar_to_reranked(reranked_tuples, cfg)

    # Parity check: same boost-tags fired on same ids
    dict_tags_by_id = {h["id"]: h["soar_tags"] for h in boosted_dict}
    tuple_tags_by_id = {row["id"]: row["soar_tags"] for _, row in boosted_tuples}
    assert dict_tags_by_id == tuple_tags_by_id

    # Parity check: same boost multipliers
    dict_boosts_by_id = {h["id"]: h["soar_boost"] for h in boosted_dict}
    tuple_boosts_by_id = {row["id"]: row["soar_boost"] for _, row in boosted_tuples}
    assert dict_boosts_by_id == tuple_boosts_by_id


def test_apply_soar_to_reranked_returns_sorted_tuples(tmp_path):
    """Output is sorted by boosted score descending."""
    from cognitive_castle import soar_bridge

    reranked = [
        (0.5, {"id": "a", "score": 0.5, "wing": "x", "room": "r", "source_file": "f"}),
        (0.8, {"id": "b", "score": 0.8, "wing": "x", "room": "r", "source_file": "f"}),
        (0.3, {"id": "c", "score": 0.3, "wing": "x", "room": "r", "source_file": "f"}),
    ]
    cfg = _mock_cfg(palace_path=str(tmp_path))

    result = soar_bridge._apply_soar_to_reranked(reranked, cfg)
    scores = [s for s, _ in result]
    assert scores == sorted(scores, reverse=True), f"Expected descending sort, got {scores}"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_soar_bridge.py::test_apply_soar_to_reranked_tuple_parity tests/test_soar_bridge.py::test_apply_soar_to_reranked_returns_sorted_tuples -v`
Expected: 2 FAILED — `AttributeError: module 'cognitive_castle.soar_bridge' has no attribute '_apply_soar_to_reranked'`

- [ ] **Step 3: Add `_apply_soar_to_reranked` to `cognitive_castle/soar_bridge.py`**

After `apply_soar_boosts(hits, cfg)` (around line 480), add:

```python
def _apply_soar_to_reranked(
    reranked: list[tuple[float, dict]],
    cfg,
) -> list[tuple[float, dict]]:
    """Apply SOAR boost-tags to a list of (score, row) tuples.

    Equivalent to apply_soar_boosts() but operates on the tuple shape used
    inside _new_pipeline_search. Returns a NEW list sorted by boosted score
    (descending). Each row dict is mutated in place with audit-trail fields
    (soar_boost, soar_tags, score_pre_soar) so they surface in the final hits.

    Never raises. Same graceful-fallback behavior as apply_soar_boosts.
    """
    if not reranked:
        return reranked

    # Adapt tuples → dict shape for the shared rule-firing core
    # (each tuple's row dict already has the fields apply_soar_boosts reads)
    hits_view = []
    for score, row in reranked:
        # Ensure the row has 'score' set (apply_soar_boosts reads it)
        if "score" not in row:
            row["score"] = score
        else:
            row["score"] = score  # always use the tuple's score
        hits_view.append(row)

    # Delegate to the existing public API; it mutates hits_view in place
    boosted = apply_soar_boosts(hits_view, cfg)

    # Rebuild tuples from the (possibly mutated) row dicts using updated scores
    new_tuples = [(h["score"], h) for h in boosted]
    new_tuples.sort(key=lambda t: -t[0])
    return new_tuples
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_soar_bridge.py::test_apply_soar_to_reranked_tuple_parity tests/test_soar_bridge.py::test_apply_soar_to_reranked_returns_sorted_tuples -v`
Expected: 2 PASSED

- [ ] **Step 5: Run the full soar_bridge test suite to verify no regression**

Run: `pytest tests/test_soar_bridge.py -v 2>&1 | tail -10`
Expected: All prior tests still pass.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/soar_bridge.py tests/test_soar_bridge.py
git commit -m "$(cat <<'EOF'
feat(soar): add _apply_soar_to_reranked tuple-shape API

Adapter around apply_soar_boosts() that operates on (score, row) tuples
— the shape produced by Stage 3 cross-encoder rerank inside
_new_pipeline_search. Same rule-firing core, same audit-trail fields,
same graceful-fallback behavior; only the input/output shape differs.

Returns sorted tuples (descending boosted score).

Tuple-parity test verifies _apply_soar_to_reranked and apply_soar_boosts
produce identical boost decisions on equivalent inputs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Add `_stage_5_soar` helper + `soar_boost` param threaded into pipeline

**Files:**
- Modify: `cognitive_castle/searcher.py` (add `_stage_5_soar` helper; add `soar_boost: bool = False` to `search_memories` + `_new_pipeline_search`; thread through; call Stage 5 inside `_new_pipeline_search`)
- Modify: `tests/test_pipeline_order.py` (add Stage 5 in-pipeline tests)

**Note:** External call sites (cli.py + mcp_server.py) still call `apply_soar_boosts` directly. Removal happens in Tasks 5-6. This task introduces the in-pipeline path WITHOUT removing the external path, so both work transiently.

- [ ] **Step 1: Write failing tests for in-pipeline SOAR + default ordering**

Append to `tests/test_pipeline_order.py`:

```python
def test_stage_5_soar_helper_exists_and_applies_boosts(tmp_path, monkeypatch):
    """_stage_5_soar(reranked, cfg) calls _apply_soar_to_reranked and returns the result."""
    from cognitive_castle.searcher import _stage_5_soar

    reranked = [
        (0.9, {"id": "a", "score": 0.9, "wing": "x", "room": "r", "source_file": "f"}),
    ]

    class FakeCfg:
        soar_enabled = True
        soar_rules_path = None
        palace_path = str(tmp_path)

    result = _stage_5_soar(reranked, FakeCfg())
    # Even with no rules firing, audit-trail fields are attached
    assert len(result) == 1
    _, row = result[0]
    assert "soar_boost" in row
    assert "soar_tags" in row
    assert "score_pre_soar" in row


def test_search_memories_threads_soar_boost_through_pipeline(tmp_path, monkeypatch):
    """When soar_boost=True is passed to search_memories, _stage_5_soar fires.

    We don't need a real palace — just verify that _new_pipeline_search receives
    and propagates the param. Use a stub to intercept.
    """
    import cognitive_castle.searcher as searcher_mod

    soar_calls = []

    def stub_stage_5(reranked, cfg):
        soar_calls.append(reranked)
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_5_soar", stub_stage_5)
    # We also need to stub the pipeline so it doesn't try to query a real palace
    def stub_pipeline(query, palace_path, wing, room, n_results, cfg, **kwargs):
        # Mimic what _new_pipeline_search does at the end
        reranked = [(0.9, {"id": "a", "score": 0.9, "wing": "x"})]
        if kwargs.get("soar_boost"):
            reranked = searcher_mod._stage_5_soar(reranked, cfg)
        return [{"id": r["id"]} for _, r in reranked]

    monkeypatch.setattr(searcher_mod, "_new_pipeline_search", stub_pipeline)

    result = searcher_mod.search_memories(
        query="test",
        palace_path=str(tmp_path),
        soar_boost=True,
    )
    assert len(soar_calls) == 1, "Expected _stage_5_soar to be invoked once via soar_boost=True"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_pipeline_order.py::test_stage_5_soar_helper_exists_and_applies_boosts tests/test_pipeline_order.py::test_search_memories_threads_soar_boost_through_pipeline -v`
Expected: 2 FAILED — `AttributeError: module 'cognitive_castle.searcher' has no attribute '_stage_5_soar'`

- [ ] **Step 3: Add `_stage_5_soar` helper in `cognitive_castle/searcher.py`**

Add as a module-level function in `searcher.py`, right after `_stage_4_judge` (added in Task 2):

```python
def _stage_5_soar(
    reranked: list[tuple[float, dict]],
    cfg,
) -> list[tuple[float, dict]]:
    """Stage 5: SOAR symbolic boost-tags.

    Delegates to soar_bridge._apply_soar_to_reranked. Lazy-imports
    soar_bridge so the module is only loaded when soar_boost is on
    (preserves the "no SOAR overhead by default" invariant from PR #4a).
    """
    from . import soar_bridge

    return soar_bridge._apply_soar_to_reranked(reranked, cfg)
```

- [ ] **Step 4: Add `soar_boost: bool = False` param to `search_memories` and `_new_pipeline_search`**

In `cognitive_castle/searcher.py`, modify `search_memories` signature (around line 226) to add `soar_boost: bool = False` after `llm_rerank: bool = False`. Same for `_new_pipeline_search` (around line 365).

Update the call from `search_memories` to `_new_pipeline_search` (line 260-269) to pass `soar_boost=soar_boost`.

In `_new_pipeline_search`, after the Stage 4 block (which already calls `_stage_4_judge`), add:

```python
    # ── Stage 5 (optional): SOAR symbolic boost-tags ──────────────────────
    if soar_boost:
        reranked = _stage_5_soar(reranked, cfg)
```

Place this BETWEEN the Stage 4 block and the `return [...]` formatter.

- [ ] **Step 5: Update `search()` to thread `soar_boost` through**

`search()` at line 184 also takes `llm_rerank`; add `soar_boost: bool = False` after it and pass to `search_memories`:

```python
def search(
    query: str,
    palace_path: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
    llm_rerank: bool = False,
    soar_boost: bool = False,
):
    ...
    try:
        result = search_memories(
            query=query,
            palace_path=palace_path,
            wing=wing,
            room=room,
            n_results=n_results,
            llm_rerank=llm_rerank,
            soar_boost=soar_boost,
        )
    ...
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_pipeline_order.py::test_stage_5_soar_helper_exists_and_applies_boosts tests/test_pipeline_order.py::test_search_memories_threads_soar_boost_through_pipeline -v`
Expected: 2 PASSED

- [ ] **Step 7: Run wider tests**

Run: `pytest tests/test_retrieval_pipeline.py tests/test_pipeline_order.py tests/test_soar_bridge.py 2>&1 | tail -5`
Expected: No NEW failures.

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/searcher.py tests/test_pipeline_order.py
git commit -m "$(cat <<'EOF'
feat(searcher): thread soar_boost into _new_pipeline_search

Adds _stage_5_soar(reranked, cfg) helper that lazy-imports soar_bridge
and delegates to _apply_soar_to_reranked. New soar_boost: bool = False
param on search_memories(), _new_pipeline_search(), and search()
controls whether Stage 5 fires inside the pipeline.

Both Stage 4 (judge) and Stage 5 (SOAR) now live as in-pipeline helpers.
Default ordering is judge-then-SOAR — same as the current external
behavior in cli.py + mcp_server.py.

External call sites (cli.py:601-619, mcp_server.py:421-435) still call
apply_soar_boosts directly; they're removed in Tasks 5-6. Both paths
work transiently — the in-pipeline call returns audit-trail fields the
external call would add anyway, so they don't conflict on the same hits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Remove external SOAR call from cli.py

**Files:**
- Modify: `cognitive_castle/cli.py:cmd_search` (remove the `if soar_boost: ... apply_soar_boosts(...)` branch; pass `soar_boost` through to `search()` instead)

- [ ] **Step 1: Update `cmd_search` to pass `soar_boost` through to `search()`**

In `cognitive_castle/cli.py`, locate `cmd_search` (line 583). The current `try:` block (lines 600-630) has an `if soar_boost: ... else: search(...)` branch. Replace the entire `try:` block contents with a single `search(...)` call that passes `soar_boost`:

```python
    try:
        search(
            query=args.query,
            palace_path=palace_path,
            wing=args.wing,
            room=args.room,
            n_results=args.results,
            llm_rerank=getattr(args, "llm_rerank", False),
            soar_boost=soar_boost,
        )
    except EmbedderIdentityMismatchError as e:
```

(The `except EmbedderIdentityMismatchError` and `except SearchError` clauses stay unchanged.)

Remove the import line `from .searcher import ... _print_search_results` (kept for the SOAR branch) — actually keep it; `_print_search_results` may be used elsewhere. Just verify the lazy `from . import soar_bridge` import inside the now-removed branch is gone.

- [ ] **Step 2: Verify cli.py changes**

Run: `grep -n "apply_soar_boosts\|soar_bridge" cognitive_castle/cli.py`
Expected: NO matches (both the call and the import are gone).

- [ ] **Step 3: Run cli tests to verify no regression**

Run: `pytest tests/test_cli.py -v 2>&1 | tail -10`
Expected: All prior tests still pass.

- [ ] **Step 4: Run a quick smoke against the developer's palace**

The developer's palace (`~/.castle/palace`) is a legacy 384-dim MiniLM palace — `castle search` should still hit the friendly `EmbedderIdentityMismatchError` path, NOT crash on the missing SOAR branch.

Run: `castle --palace ~/.castle/palace search "test" --soar-boost 2>&1 | head -5`
Expected: Friendly migration prompt (`EmbedderIdentityMismatchError`); not a crash, not "No results found".

(This is just a sanity check that `--soar-boost` flag is still wired and reaches the validation path.)

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/cli.py
git commit -m "$(cat <<'EOF'
refactor(cli): remove external apply_soar_boosts branch

SOAR now runs inside _new_pipeline_search via the soar_boost param
threaded through search_memories(). cmd_search no longer needs the
post-pipeline if soar_boost: apply_soar_boosts(...) branch — just pass
soar_boost through to search() like any other flag.

cli.py is now backend-agnostic about which stages run; pipeline composition
lives in searcher.py where it belongs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Remove external SOAR call from mcp_server.py

**Files:**
- Modify: `cognitive_castle/mcp_server.py:tool_search` (remove the `if soar_boost: ... apply_soar_boosts(...)` block at lines 421-435; pass `soar_boost` through to `search_memories()`)

- [ ] **Step 1: Update `tool_search` to pass `soar_boost` through to `search_memories()`**

In `cognitive_castle/mcp_server.py`, locate `tool_search` (line 370). The call to `search_memories` at line 393-401 currently passes `llm_rerank` but NOT `soar_boost`. Update it to also pass `soar_boost`:

```python
    result = search_memories(
        sanitized["clean_query"],
        palace_path=_config.palace_path,
        wing=wing,
        room=room,
        n_results=limit,
        max_distance=dist,
        llm_rerank=llm_rerank,
        soar_boost=soar_boost,
    )
```

Remove the existing `# SOAR post-pipeline boost-tags ... if soar_boost: ...` block at lines 421-435 entirely. (Keep the kill-switch check, but move it to BEFORE the `search_memories` call — see Step 2.)

- [ ] **Step 2: Move the kill-switch check to before search_memories**

The kill-switch check (line 423-428) needs to fire BEFORE we invoke `search_memories(soar_boost=True)`, otherwise we'd actually run SOAR before checking the kill switch. Insert it after the sanitize block and before the `search_memories` call:

```python
    # Kill-switch check: --soar-boost requires CASTLE_SOAR_ENABLED=1
    if soar_boost and not _config.soar_enabled:
        return {
            "error": "CASTLE_SOAR_ENABLED=0 kill switch is active; remove it to use soar_boost",
            "soar_boost_skipped": True,
        }
```

- [ ] **Step 3: Verify mcp_server.py changes**

Run: `grep -n "apply_soar_boosts\|soar_bridge" cognitive_castle/mcp_server.py`
Expected: NO matches.

- [ ] **Step 4: Run MCP tests to verify no regression**

Run: `pytest tests/test_mcp_server.py -v 2>&1 | tail -10`
Expected: All prior tests still pass. The existing `test_mcp_castle_search_soar_boost_threads_through` test (at line 990) should still pass — its existing assertion is that `soar_boost=True` produces audit-trail fields on the hits, which works equally well via in-pipeline SOAR.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/mcp_server.py
git commit -m "$(cat <<'EOF'
refactor(mcp): remove external apply_soar_boosts branch from tool_search

Mirror of the cli.py removal in the previous commit. SOAR now runs inside
_new_pipeline_search via the soar_boost param. tool_search just passes
soar_boost through to search_memories() and handles the kill-switch
validation up front.

After this commit NO internal call sites of apply_soar_boosts() remain.
The public API stays for external user code + tests that import it
directly from soar_bridge.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Add `soar_first` param + ordering branch inside `_new_pipeline_search`

**Files:**
- Modify: `cognitive_castle/searcher.py` (add `soar_first: bool = False` to `search_memories`, `_new_pipeline_search`, `search`; add ordering branch logic)
- Modify: `tests/test_pipeline_order.py` (add 4 ordering tests)

- [ ] **Step 1: Write the failing ordering tests**

Append to `tests/test_pipeline_order.py`:

```python
def test_default_path_runs_judge_then_soar(monkeypatch, tmp_path):
    """Default order: Stage 4 (judge) fires before Stage 5 (SOAR)."""
    import cognitive_castle.searcher as searcher_mod

    call_order = []

    def fake_stage_4(query, reranked, cfg):
        call_order.append("stage_4")
        return reranked

    def fake_stage_5(reranked, cfg):
        call_order.append("stage_5")
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_4_judge", fake_stage_4)
    monkeypatch.setattr(searcher_mod, "_stage_5_soar", fake_stage_5)

    # Drive _new_pipeline_search's ordering branch directly by simulating
    # only the conditional block; we don't need a real palace here.
    # Use a private helper that wraps the branch — see Step 3.
    from cognitive_castle.searcher import _apply_stages_4_and_5

    reranked = [(0.9, {"id": "a", "score": 0.9})]
    cfg_obj = type("C", (), {"llm_judge_top_n": 5, "soar_enabled": True, "soar_rules_path": None, "palace_path": str(tmp_path)})()

    _apply_stages_4_and_5(
        query="q",
        reranked=reranked,
        cfg=cfg_obj,
        llm_rerank=True,
        soar_boost=True,
        soar_first=False,
    )
    assert call_order == ["stage_4", "stage_5"]


def test_soar_first_runs_soar_then_judge(monkeypatch, tmp_path):
    """soar_first=True: Stage 5 fires before Stage 4."""
    import cognitive_castle.searcher as searcher_mod

    call_order = []
    monkeypatch.setattr(
        searcher_mod, "_stage_4_judge", lambda q, r, c: call_order.append("stage_4") or r
    )
    monkeypatch.setattr(
        searcher_mod, "_stage_5_soar", lambda r, c: call_order.append("stage_5") or r
    )

    from cognitive_castle.searcher import _apply_stages_4_and_5
    cfg_obj = type("C", (), {"llm_judge_top_n": 5, "soar_enabled": True, "soar_rules_path": None, "palace_path": str(tmp_path)})()

    _apply_stages_4_and_5(
        query="q",
        reranked=[(0.9, {"id": "a", "score": 0.9})],
        cfg=cfg_obj,
        llm_rerank=True,
        soar_boost=True,
        soar_first=True,
    )
    assert call_order == ["stage_5", "stage_4"]


def test_soar_only_no_judge_call(monkeypatch, tmp_path):
    """llm_rerank=False, soar_boost=True: only Stage 5 fires, no Stage 4."""
    import cognitive_castle.searcher as searcher_mod

    call_order = []
    monkeypatch.setattr(
        searcher_mod, "_stage_4_judge", lambda q, r, c: call_order.append("stage_4") or r
    )
    monkeypatch.setattr(
        searcher_mod, "_stage_5_soar", lambda r, c: call_order.append("stage_5") or r
    )

    from cognitive_castle.searcher import _apply_stages_4_and_5
    cfg_obj = type("C", (), {"llm_judge_top_n": 5, "soar_enabled": True, "soar_rules_path": None, "palace_path": str(tmp_path)})()

    _apply_stages_4_and_5(
        query="q",
        reranked=[(0.9, {"id": "a", "score": 0.9})],
        cfg=cfg_obj,
        llm_rerank=False,
        soar_boost=True,
        soar_first=False,
    )
    assert call_order == ["stage_5"]


def test_judge_only_no_soar_call(monkeypatch, tmp_path):
    """llm_rerank=True, soar_boost=False: only Stage 4 fires, no Stage 5."""
    import cognitive_castle.searcher as searcher_mod

    call_order = []
    monkeypatch.setattr(
        searcher_mod, "_stage_4_judge", lambda q, r, c: call_order.append("stage_4") or r
    )
    monkeypatch.setattr(
        searcher_mod, "_stage_5_soar", lambda r, c: call_order.append("stage_5") or r
    )

    from cognitive_castle.searcher import _apply_stages_4_and_5
    cfg_obj = type("C", (), {"llm_judge_top_n": 5, "soar_enabled": True, "soar_rules_path": None, "palace_path": str(tmp_path)})()

    _apply_stages_4_and_5(
        query="q",
        reranked=[(0.9, {"id": "a", "score": 0.9})],
        cfg=cfg_obj,
        llm_rerank=True,
        soar_boost=False,
        soar_first=False,
    )
    assert call_order == ["stage_4"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_pipeline_order.py::test_default_path_runs_judge_then_soar tests/test_pipeline_order.py::test_soar_first_runs_soar_then_judge tests/test_pipeline_order.py::test_soar_only_no_judge_call tests/test_pipeline_order.py::test_judge_only_no_soar_call -v`
Expected: 4 FAILED — `ImportError: cannot import name '_apply_stages_4_and_5' from 'cognitive_castle.searcher'`

- [ ] **Step 3: Add `_apply_stages_4_and_5` helper + integrate into `_new_pipeline_search`**

In `cognitive_castle/searcher.py`, add a new helper right after `_stage_5_soar`:

```python
def _apply_stages_4_and_5(
    query: str,
    reranked: list[tuple[float, dict]],
    cfg,
    llm_rerank: bool,
    soar_boost: bool,
    soar_first: bool,
) -> list[tuple[float, dict]]:
    """Run optional Stage 4 (judge) and Stage 5 (SOAR) in the requested order.

    Default order (soar_first=False): Stage 4 → Stage 5 (judge truncates to
    top-N first, then SOAR re-ranks those). Matches the pre-#4b behavior.

    soar_first=True: Stage 5 → Stage 4 (SOAR re-ranks the full reranked list,
    then judge truncates to top-N from SOAR's preferred order). Caller is
    responsible for validation — when soar_first=True, both llm_rerank and
    soar_boost must also be True (CLI/MCP layers validate this loudly).
    """
    if soar_first:
        reranked = _stage_5_soar(reranked, cfg)
        reranked = _stage_4_judge(query, reranked, cfg)
        return reranked
    if llm_rerank:
        reranked = _stage_4_judge(query, reranked, cfg)
    if soar_boost:
        reranked = _stage_5_soar(reranked, cfg)
    return reranked
```

Now refactor `_new_pipeline_search` to use this helper. Replace the existing Stage 4 and Stage 5 blocks (which currently call `_stage_4_judge` and `_stage_5_soar` inline based on `llm_rerank` and `soar_boost` from Tasks 2 + 4):

```python
    # ── Stage 4 + Stage 5 (optional, composable order) ────────────────────
    reranked = _apply_stages_4_and_5(
        query=query,
        reranked=reranked,
        cfg=cfg,
        llm_rerank=llm_rerank,
        soar_boost=soar_boost,
        soar_first=soar_first,
    )
```

- [ ] **Step 4: Add `soar_first: bool = False` param to `_new_pipeline_search`, `search_memories`, and `search`**

In `_new_pipeline_search` (signature around line 365), add `soar_first: bool = False` after `soar_boost`.

In `search_memories` (signature around line 226), add `soar_first: bool = False` after `soar_boost`. Pass through to `_new_pipeline_search`.

In `search` (signature around line 184), add `soar_first: bool = False` after `soar_boost`. Pass through to `search_memories`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_pipeline_order.py -v 2>&1 | tail -15`
Expected: All 8 tests pass (the 4 new ordering tests + the 4 from Tasks 2-4).

- [ ] **Step 6: Run wider tests**

Run: `pytest tests/test_retrieval_pipeline.py tests/test_pipeline_order.py tests/test_soar_bridge.py tests/test_cli.py tests/test_mcp_server.py 2>&1 | tail -10`
Expected: No NEW failures.

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/searcher.py tests/test_pipeline_order.py
git commit -m "$(cat <<'EOF'
feat(searcher): add soar_first param + Stage 4↔5 ordering branch

Adds _apply_stages_4_and_5(query, reranked, cfg, llm_rerank, soar_boost,
soar_first) helper inside searcher.py. When soar_first=True: Stage 5
(SOAR) runs BEFORE Stage 4 (judge). When False (default): Stage 4 runs
first, then Stage 5 — same as the current behavior post-Task-4.

New soar_first: bool = False param threaded through:
- search() (CLI entry)
- search_memories() (programmatic entry)
- _new_pipeline_search() (pipeline internal)

Validation that soar_first requires both llm_rerank and soar_boost is
the caller's responsibility (CLI/MCP layers handle it in Tasks 8-9).

4 new tests in tests/test_pipeline_order.py cover all 4 orderings:
default judge-then-SOAR, soar_first SOAR-then-judge, SOAR-only,
judge-only.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Add `--soar-first` CLI flag + validation + CLI tests

**Files:**
- Modify: `cognitive_castle/cli.py` (add `--soar-first` argparse flag; add validation in `cmd_search`; pass `soar_first` through to `search()`)
- Modify: `tests/test_cli.py` (add 3 validation tests)

- [ ] **Step 1: Write failing CLI validation tests**

Append to `tests/test_cli.py`:

```python
def test_cli_soar_first_without_llm_rerank_errors(monkeypatch, capsys):
    """castle search --soar-boost --soar-first → sys.exit(2), names --llm-rerank as missing."""
    import sys
    from cognitive_castle import cli

    monkeypatch.setattr(sys, "argv", ["castle", "search", "test", "--soar-boost", "--soar-first"])
    # Need CASTLE_SOAR_ENABLED=1 so the kill switch doesn't fire first
    monkeypatch.setenv("CASTLE_SOAR_ENABLED", "1")
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--soar-first" in err
    assert "--llm-rerank" in err


def test_cli_soar_first_without_soar_boost_errors(monkeypatch, capsys):
    """castle search --llm-rerank --soar-first → sys.exit(2), names --soar-boost as missing."""
    import sys
    from cognitive_castle import cli

    monkeypatch.setattr(sys, "argv", ["castle", "search", "test", "--llm-rerank", "--soar-first"])
    monkeypatch.setenv("CASTLE_SOAR_ENABLED", "1")
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--soar-first" in err
    assert "--soar-boost" in err


def test_cli_soar_first_alone_errors(monkeypatch, capsys):
    """castle search --soar-first → sys.exit(2), names BOTH missing flags."""
    import sys
    from cognitive_castle import cli

    monkeypatch.setattr(sys, "argv", ["castle", "search", "test", "--soar-first"])
    monkeypatch.setenv("CASTLE_SOAR_ENABLED", "1")
    with pytest.raises(SystemExit) as exc_info:
        cli.main()
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "--llm-rerank" in err
    assert "--soar-boost" in err
```

(If `tests/test_cli.py` doesn't have `import pytest` at the top, add it.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_cli.py::test_cli_soar_first_without_llm_rerank_errors tests/test_cli.py::test_cli_soar_first_without_soar_boost_errors tests/test_cli.py::test_cli_soar_first_alone_errors -v`
Expected: 3 FAILED — argparse doesn't know about `--soar-first` yet.

- [ ] **Step 3: Add the `--soar-first` argparse flag**

In `cognitive_castle/cli.py`, locate the `p_search.add_argument("--soar-boost", ...)` block (around line 1130). Add immediately after it:

```python
    p_search.add_argument(
        "--soar-first",
        action="store_true",
        help=(
            "Run SOAR (Stage 5) BEFORE LLM-as-judge (Stage 4). Requires both "
            "--llm-rerank and --soar-boost. Default order is judge-then-SOAR. "
            "Use this to let SOAR's hand-crafted rules shape what the LLM sees."
        ),
    )
```

- [ ] **Step 4: Add validation + pass `soar_first` through to `search()` in `cmd_search`**

In `cmd_search` (around line 583), add the validation BEFORE the existing kill-switch check (so the more-specific error fires first):

```python
def cmd_search(args):
    from .searcher import search, SearchError, _print_search_results
    from .backends.base import EmbedderIdentityMismatchError

    cfg = CognitiveCastleConfig()
    soar_boost = getattr(args, "soar_boost", False)
    soar_first = getattr(args, "soar_first", False)
    llm_rerank = getattr(args, "llm_rerank", False)

    # --soar-first requires both companion flags
    if soar_first:
        missing = []
        if not llm_rerank:
            missing.append("--llm-rerank")
        if not soar_boost:
            missing.append("--soar-boost")
        if missing:
            print(
                f"--soar-first requires both --llm-rerank and --soar-boost; "
                f"missing: {', '.join(missing)}",
                file=sys.stderr,
            )
            sys.exit(2)

    # Kill-switch check: --soar-boost requires CASTLE_SOAR_ENABLED=1
    if soar_boost and not cfg.soar_enabled:
        ...  # unchanged
```

And update the `search(...)` call inside the `try:` to pass both new params:

```python
    try:
        search(
            query=args.query,
            palace_path=palace_path,
            wing=args.wing,
            room=args.room,
            n_results=args.results,
            llm_rerank=llm_rerank,
            soar_boost=soar_boost,
            soar_first=soar_first,
        )
```

- [ ] **Step 5: Run the validation tests to verify they pass**

Run: `pytest tests/test_cli.py::test_cli_soar_first_without_llm_rerank_errors tests/test_cli.py::test_cli_soar_first_without_soar_boost_errors tests/test_cli.py::test_cli_soar_first_alone_errors -v`
Expected: 3 PASSED

- [ ] **Step 6: Verify the kill-switch precedence**

The spec says kill switch fires FIRST if `--soar-boost` is on but env is off. Verify by adding a quick sanity check via grep:

Run: `grep -A20 "def cmd_search" cognitive_castle/cli.py | head -30`
Expected: The `--soar-first` validation block precedes the `if soar_boost and not cfg.soar_enabled:` kill-switch check. BUT the kill-switch fires when `soar_boost=True` regardless of soar_first state, so the right precedence is: validate soar_first companion flags first (catches user errors before kill-switch context), then kill switch. This matches the spec.

- [ ] **Step 7: Run wider tests**

Run: `pytest tests/test_cli.py -v 2>&1 | tail -10`
Expected: All prior tests still pass.

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/cli.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(cli): add --soar-first flag + loud validation

New --soar-first argparse flag for `castle search`. Requires both
--llm-rerank and --soar-boost; missing-flag combinations error loudly
with sys.exit(2) + a clear message naming the missing flag(s).

Threads soar_first through to search() (which passes to search_memories
→ _new_pipeline_search). When all 3 flags are on: SOAR runs first
(reordering the full ~20 cross-encoder candidates), then judge truncates
to top-N from SOAR's preferred order.

3 new validation tests in tests/test_cli.py verify the sys.exit(2)
behavior for each missing-flag combination.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Add `soar_first` MCP param + validation + MCP test

**Files:**
- Modify: `cognitive_castle/mcp_server.py:tool_search` (add `soar_first: bool = False` param; add validation returning error response; pass through to `search_memories`)
- Modify: `tests/test_mcp_server.py` (add validation test)

- [ ] **Step 1: Write the failing MCP validation test**

Append to `tests/test_mcp_server.py`:

```python
def test_mcp_soar_first_without_other_flags_returns_error(monkeypatch):
    """MCP tool_search with soar_first=True but soar_boost=False returns error response."""
    from cognitive_castle import mcp_server

    monkeypatch.setenv("CASTLE_SOAR_ENABLED", "1")

    result = mcp_server.tool_search(
        query="test",
        soar_first=True,
        soar_boost=False,
        llm_rerank=False,
    )
    assert "error" in result
    assert "soar_first" in result["error"]
    # MCP does NOT sys.exit — it returns the error to the client
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_mcp_server.py::test_mcp_soar_first_without_other_flags_returns_error -v`
Expected: FAIL — `tool_search` doesn't accept `soar_first` yet.

- [ ] **Step 3: Add `soar_first: bool = False` param to `tool_search`**

In `cognitive_castle/mcp_server.py`, modify the `tool_search` signature (line 370):

```python
def tool_search(
    query: str,
    limit: int = 5,
    wing: str = None,
    room: str = None,
    max_distance: float = 1.5,
    min_similarity: float = None,
    context: str = None,
    llm_rerank: bool = False,
    soar_boost: bool = False,
    soar_first: bool = False,
):
```

Add validation right after the sanitize block, BEFORE the kill-switch check and the `search_memories(...)` call:

```python
    # --soar-first requires both companion flags (MCP path: error response, not sys.exit)
    if soar_first:
        missing = []
        if not llm_rerank:
            missing.append("llm_rerank")
        if not soar_boost:
            missing.append("soar_boost")
        if missing:
            return {
                "error": f"soar_first requires both llm_rerank and soar_boost; missing: {', '.join(missing)}",
            }
```

Update the `search_memories(...)` call (around line 393) to pass `soar_first`:

```python
    result = search_memories(
        sanitized["clean_query"],
        palace_path=_config.palace_path,
        wing=wing,
        room=room,
        n_results=limit,
        max_distance=dist,
        llm_rerank=llm_rerank,
        soar_boost=soar_boost,
        soar_first=soar_first,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_mcp_server.py::test_mcp_soar_first_without_other_flags_returns_error -v`
Expected: PASS

- [ ] **Step 5: Run wider MCP tests**

Run: `pytest tests/test_mcp_server.py -v 2>&1 | tail -10`
Expected: All prior tests still pass.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/mcp_server.py tests/test_mcp_server.py
git commit -m "$(cat <<'EOF'
feat(mcp): add soar_first param + error-response validation

New soar_first: bool = False param on tool_search. Same validation as
the CLI (requires both llm_rerank and soar_boost) but returns an error
response shape instead of sys.exit (MCP can't exit the process — clients
expect a response).

1 new test in tests/test_mcp_server.py verifies the error-response path.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: CLAUDE.md + README.md updates

**Files:**
- Modify: `CLAUDE.md` (retrieval pipeline diagram around line 184)
- Modify: `README.md` (SOAR subsection)

- [ ] **Step 1: Update CLAUDE.md retrieval pipeline diagram**

Locate the retrieval pipeline diagram in `CLAUDE.md` (around line 184). The current Stage 4 entry looks like:

```
    ├── Stage 4 (optional, opt-in via --llm-rerank or llm_rerank:true MCP param):
    │     LLM-as-judge re-ranks top-cfg.llm_judge_top_n (default 10) from Stage 3
    │     → graceful identity-order fallback on any LLM failure
    └── Stage 5 (optional, opt-in via --soar-boost AND CASTLE_SOAR_ENABLED=1):
          SOAR symbolic productions add boost-tags to final hits
          → multiplicative score adjustment with audit-trail fields
          → graceful pass-through on any Soar failure
```

Update to show Stage 4 ↔ Stage 5 as orderable:

```
    ├── Stage 4 + Stage 5 (optional, composable; default order: 4 then 5)
    │     ├── Stage 4 (--llm-rerank or llm_rerank:true MCP): LLM-as-judge re-ranks
    │     │     top-cfg.llm_judge_top_n (default 10) from Stage 3
    │     │     → graceful identity-order fallback on any LLM failure
    │     ├── Stage 5 (--soar-boost AND CASTLE_SOAR_ENABLED=1): SOAR symbolic
    │     │     productions add boost-tags
    │     │     → graceful pass-through on any Soar failure
    │     └── Ordering: default is Stage 4 then Stage 5 (judge-then-SOAR).
    │            --soar-first / soar_first:true flips to Stage 5 then Stage 4
    │            (requires both --llm-rerank AND --soar-boost on; loud sys.exit(2)
    │            on missing companion flags).
```

- [ ] **Step 2: Update README.md SOAR subsection**

Locate the SOAR subsection in `README.md` (search for `### Experimental: SOAR`). Append a paragraph about `--soar-first`:

```markdown
### Composable Stage 4 ↔ Stage 5 order (`--soar-first`)

By default, when both `--llm-rerank` and `--soar-boost` are on, the pipeline
runs Stage 4 (judge) first then Stage 5 (SOAR) — the LLM picks the best
candidates and SOAR applies final boost adjustments to the chosen top-N.

Use `--soar-first` to flip the order: SOAR runs first (re-ranking the full
~20 cross-encoder candidates by boost-tag rules), then the judge picks the
top-N from SOAR's preferred order. Useful when you want SOAR's hand-crafted
rules to shape what the LLM considers.

```bash
castle search "what did we decide?" --llm-rerank --soar-boost --soar-first
```

`--soar-first` requires both `--llm-rerank` AND `--soar-boost` to be on; using
it alone or with only one companion flag fails loudly with a clear message.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "$(cat <<'EOF'
docs: --soar-first flag in CLAUDE.md diagram + README

CLAUDE.md retrieval pipeline diagram now shows Stage 4 ↔ Stage 5 as a
composable pair (default order: 4 then 5; --soar-first flips it).

README.md SOAR subsection gets a new "Composable Stage 4 ↔ Stage 5 order
(--soar-first)" paragraph explaining when to use the flag.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Lint + full test suite

**Files:**
- None — verification only

- [ ] **Step 1: Run ruff format check on touched files**

Run:
```bash
ruff format --check cognitive_castle/searcher.py cognitive_castle/soar_bridge.py cognitive_castle/cli.py cognitive_castle/mcp_server.py tests/test_pipeline_order.py tests/test_soar_bridge.py tests/test_cli.py tests/test_mcp_server.py
```
Expected: All formatted correctly. If not, run `ruff format` on the listed files and commit the formatting fix separately.

- [ ] **Step 2: Run ruff check**

Run: `ruff check cognitive_castle/ tests/test_pipeline_order.py tests/test_soar_bridge.py tests/test_cli.py tests/test_mcp_server.py`
Expected: All checks pass.

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -5`
Expected: 18 baseline failures + ~13 new passes (from new tests in this PR). No NEW failures beyond the 18 CI-UNSTABLE baseline.

- [ ] **Step 4: If formatting/lint issues found, fix + commit**

```bash
ruff format cognitive_castle/ tests/
git add -p
git commit -m "style: ruff format after SOAR composable order

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

If no fixes needed, skip this step.

---

### Task 12: Smoke + push + PR

**Files:**
- None — verification + git operations

- [ ] **Step 1: Live smoke against developer's palace**

The developer's `~/.castle/palace` is a 384-dim legacy MiniLM palace. Both invocations should hit the friendly `EmbedderIdentityMismatchError` migration prompt (NOT crash, NOT "No results found").

Run: `castle --palace ~/.castle/palace search "test" --llm-rerank --soar-boost --soar-first 2>&1 | head -10`
Expected: Migration prompt (not a crash from the new flag). Exit code 1.

Run: `castle --palace ~/.castle/palace search "test" --soar-first 2>&1 | head -3`
Expected: `--soar-first requires both --llm-rerank and --soar-boost; missing: --llm-rerank, --soar-boost`. Exit code 2.

- [ ] **Step 2: Push branch**

Run: `git push -u origin feat/soar-llm-judge-composable`
Expected: Branch pushed; PR URL printed.

- [ ] **Step 3: Open PR**

```bash
gh pr create --title "feat: SOAR ↔ LLM-judge composable order (PR #4b)" --body "$(cat <<'EOF'
## Summary

Sub-PR #4b of the SOAR umbrella named in PR #4a's spec. Refactors SOAR from an external post-step (called from `cli.py` and `mcp_server.py`) into a proper in-pipeline stage inside `_new_pipeline_search`, then adds a `--soar-first` CLI flag (and matching `soar_first` MCP param) that flips Stage 4 ↔ Stage 5 invocation order.

- **Default order preserved:** judge-then-SOAR. Existing users with `--soar-boost` see byte-equivalent output. No silent behavior change.
- **`--soar-first` opt-in:** loud `sys.exit(2)` if used without both `--llm-rerank` and `--soar-boost`. Error message names the missing flag(s).
- **MCP symmetry:** `soar_first: bool` MCP param with parallel error-response validation (no `sys.exit` from MCP path).
- **No-internal-callers cleanup:** after this PR, `apply_soar_boosts(hits, cfg)` has no internal call sites — both `cli.py` and `mcp_server.py` migrate to in-pipeline SOAR via `soar_boost=True` to `search_memories()`. The public API stays for external user code + tests.

## Spec + Plan

- Spec: `docs/superpowers/specs/2026-05-13-soar-llm-judge-composable-design.md`
- Plan: `docs/superpowers/plans/2026-05-13-soar-llm-judge-composable.md`

## Test plan

- [x] `tests/test_pipeline_order.py` (new file): 8 ordering tests — default judge-then-SOAR, soar_first SOAR-then-judge, SOAR-only, judge-only, helper-extraction parity, in-pipeline threading
- [x] `tests/test_soar_bridge.py`: 2 new tests — `test_apply_soar_to_reranked_tuple_parity` + `test_apply_soar_to_reranked_returns_sorted_tuples`
- [x] `tests/test_cli.py`: 3 new validation tests — `--soar-first` alone, with `--soar-boost` only, with `--llm-rerank` only
- [x] `tests/test_mcp_server.py`: 1 new validation test — `soar_first=true` without companions returns error response
- [x] `pytest tests/ --ignore=tests/benchmarks` — 18 baseline CI-UNSTABLE failures preserved, no new failures
- [x] `ruff check` + `ruff format --check` clean on all 10 touched files
- [x] Live smoke: `--soar-first` alone errors with `sys.exit(2)` + clear message
- [x] Live smoke: `--llm-rerank --soar-boost --soar-first` reaches the pipeline (then hits the friendly EmbedderIdentityMismatchError on developer's legacy palace, but doesn't crash on the new flag)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR URL printed. Return it to the user.

---

## Self-Review

### Spec coverage check

| Spec section / requirement | Plan task |
|---|---|
| Half 1: Move SOAR into the pipeline | Tasks 4, 5, 6 (Stage 5 helper added in 4; cli.py external call removed in 5; mcp_server.py external call removed in 6) |
| Half 2: Pipeline branching with `soar_first` | Task 7 (`_apply_stages_4_and_5` helper) |
| Half 3: `_apply_soar_to_reranked` on tuples | Task 3 |
| Half 4: CLI flag + validation | Task 8 |
| Half 5: MCP symmetry + MCP-side SOAR migration | Tasks 6, 9 |
| Candidate-pool size difference doc | Captured implicitly via the truncation behavior in `_stage_4_judge` (Task 2). Tests don't explicitly assert pool size, but the truncation is preserved verbatim from the inline code. |
| Score-vs-order disagreement in soar_first mode | No special test (acceptance criterion mentions that audit-trail intact; consumers reading `score_pre_soar` get the original score). |
| Default behavior unchanged | Tests `test_default_path_runs_judge_then_soar` + `test_soar_only_no_judge_call` + `test_judge_only_no_soar_call` cover the 3 default-path cases. |
| Loud validation (`sys.exit(2)`) on missing companion flags | Task 8 (3 CLI tests) |
| MCP error-response (no sys.exit) | Task 9 (1 MCP test) |
| Kill-switch precedence over `--soar-first` validation | Task 8 Step 4 places soar_first validation BEFORE the kill-switch check. (Both can fire independently if both conditions are met — the spec's "kill switch fires first" applies to the case where soar_first companions are satisfied AND kill switch is on; in that case kill switch fires before SOAR even reaches the pipeline.) |
| `apply_soar_boosts` keeps public signature | No code change to the function itself; verified by `pytest tests/test_soar_bridge.py -v` staying green after each task. |
| CLAUDE.md + README updates | Task 10 |
| `ruff check` + format clean | Task 11 |

All spec requirements have a task.

### Placeholder scan

No "TBD" / "TODO" / "implement later" placeholders. Every step has either exact code, exact commands, or specific git operations. ✓

### Type consistency

- `_stage_4_judge(query: str, reranked: list[tuple[float, dict]], cfg) -> list[tuple[float, dict]]` — Task 2, used consistently in Tasks 5, 7
- `_stage_5_soar(reranked: list[tuple[float, dict]], cfg) -> list[tuple[float, dict]]` — Task 4, used consistently in Task 7
- `_apply_soar_to_reranked(reranked: list[tuple[float, dict]], cfg) -> list[tuple[float, dict]]` — Task 3, called from `_stage_5_soar` in Task 4
- `_apply_stages_4_and_5(query, reranked, cfg, llm_rerank, soar_boost, soar_first) -> reranked` — Task 7, called from `_new_pipeline_search`
- `search_memories(..., soar_boost: bool = False, soar_first: bool = False)` — added in Tasks 4 + 7, consumed by CLI in Task 8 and MCP in Task 9
- `search(..., soar_boost: bool = False, soar_first: bool = False)` — added in Tasks 4 + 7, consumed by CLI cmd_search in Task 8

All names consistent. No signature drift across tasks.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-13-soar-llm-judge-composable.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
