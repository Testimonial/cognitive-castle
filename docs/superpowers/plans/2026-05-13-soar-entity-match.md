# SOAR `entity-match` Rule + Fusion Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third SOAR production (`castle-boost*entity-match`) that boosts hits whose drawer shares an entity with the query, by threading hit-provenance from `fusion.py` (which signal(s) contributed) through `_new_pipeline_search` into SOAR's working memory.

**Architecture:** New `contributing_signals: frozenset[str]` field on `ScoredCandidate` is populated during `weighted_rrf` and explicitly preserved through `apply_recency`. In `_new_pipeline_search`, the top-K ScoredCandidates' `"kg" in contributing_signals` membership is materialized as a `row["entity_match"]` bool on each LanceDB row dict, which `_push_working_memory` then pushes to SOAR as `^entity-match true|false`. A new production in `castle-boost.soar` fires `^boost-tag entity-match` on hits where the flag is true; `BOOST_MULTIPLIERS["entity-match"] = 1.30` provides the multiplier. The `entity_match` flag is also surfaced in the final hit dict for audit/debugging.

**Tech Stack:** Python 3.10+, pytest, existing Soar 9.6 + SML bindings (no new deps).

---

## Spec reference

`docs/superpowers/specs/2026-05-13-soar-entity-match-design.md` (commit `2cf8131c`).

## File-level map

| File | Role | Net LOC change |
|---|---|---|
| `cognitive_castle/fusion.py` | Add `contributing_signals: frozenset[str] = frozenset()` to `ScoredCandidate`; populate in `weighted_rrf` via dict-of-sets accumulator; preserve in `apply_recency` reconstruction | +20 / -2 |
| `cognitive_castle/searcher.py` | Derive `entity_match_by_id` from `fused[:k_cap]` provenance; attach `row["entity_match"]` to top_k_rows; add `entity_match` field to final hit dict | +12 |
| `cognitive_castle/soar_bridge.py` | Add `"entity-match": 1.30` to `BOOST_MULTIPLIERS`; in `_push_working_memory`, push `^entity-match true|false` per hit | +4 |
| `cognitive_castle/rules/castle-boost.soar` | Add `castle-boost*entity-match` production; update header docstring schema to list `^entity-match` | +9 / -1 |
| `tests/test_fusion.py` | 3 new tests: contributing_signals populated, apply_recency preserves, zero-weight signal not in contributing | +75 |
| `tests/test_soar_bridge.py` | 2 new tests: entity_match boost applied when flag true, not applied when false | +60 |
| `tests/test_pipeline_order.py` | 1 new test: entity_match flag attaches to KG-hop rows in `_new_pipeline_search` | +60 |
| `CLAUDE.md` | Update SOAR rules description (line ~188 retrieval-pipeline-diagram region) to mention 3 productions and name `entity-match` | +1 / -1 |

**Total: ~240 LOC across 8 files** (~45 production + ~195 tests + ~3 docs). Single-rule scope.

---

### Task 1: Branch setup

**Files:** None — repo-level operation

- [ ] **Step 1: Verify clean tree on develop**

Run: `git status && git rev-parse --abbrev-ref HEAD`
Expected: `develop` branch. Untracked `test_env/` is fine.

- [ ] **Step 2: Create feature branch**

Run: `git switch -c feat/soar-entity-match`
Expected: `Switched to a new branch 'feat/soar-entity-match'`

- [ ] **Step 3: Verify branch**

Run: `git rev-parse --abbrev-ref HEAD`
Expected: `feat/soar-entity-match`

No commit yet.

---

### Task 2: Add `contributing_signals` field + populate in `weighted_rrf` (TDD)

**Files:**
- Modify: `cognitive_castle/fusion.py` (add field; update fusion-loop accumulator)
- Modify: `tests/test_fusion.py` (add 1 test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fusion.py`:

```python
def test_weighted_rrf_populates_contributing_signals():
    """contributing_signals reflects which signals had non-zero weight + the candidate appeared in their rank list."""
    rank_lists = {
        "dense": [_ref("a"), _ref("b")],
        "sparse": [_ref("a")],
        "kg": [_ref("b")],
    }
    weights = {"dense": 1.0, "sparse": 1.0, "kg": 0.5}

    result = weighted_rrf(rank_lists, weights, k_rrf=60)
    by_id = {sc.drawer_id: sc for sc in result}
    assert by_id["a"].contributing_signals == frozenset({"dense", "sparse"})
    assert by_id["b"].contributing_signals == frozenset({"dense", "kg"})
```

(The `_ref(drawer_id)` helper already exists at `tests/test_fusion.py:14`. Confirm `frozenset` doesn't need an import — it's a builtin.)

- [ ] **Step 2: Run the test, verify it fails**

Run: `pytest tests/test_fusion.py::test_weighted_rrf_populates_contributing_signals -v`
Expected: FAIL — `AttributeError: 'ScoredCandidate' object has no attribute 'contributing_signals'`

- [ ] **Step 3: Add the field to `ScoredCandidate` in `cognitive_castle/fusion.py`**

Locate the `@dataclass(frozen=True) class ScoredCandidate:` block (around line 21-26). Add the `contributing_signals` field at the bottom:

```python
@dataclass(frozen=True)
class ScoredCandidate:
    """A drawer reference with a fused score."""
    drawer_id: str
    timestamp_unix: float
    score: float
    contributing_signals: frozenset[str] = frozenset()
```

The default `frozenset()` is immutable so it works as a default on a frozen dataclass. Existing 3-arg call sites (`ScoredCandidate(drawer_id, timestamp_unix, score)`) keep working.

- [ ] **Step 4: Update `weighted_rrf` to accumulate signal names**

Locate `weighted_rrf` in `cognitive_castle/fusion.py` (around line 29-81). The current body has:

```python
    scores: dict[str, float] = {}
    timestamps: dict[str, float] = {}

    for signal_name, candidates in rank_lists.items():
        weight = weights.get(signal_name, 0.0)
        if weight == 0.0 or not candidates:
            # Still capture timestamps for drawers we'd otherwise miss.
            for cand in candidates:
                timestamps.setdefault(cand.drawer_id, cand.timestamp_unix)
            continue
        for rank, cand in enumerate(candidates, start=1):
            contribution = weight / (k_rrf + rank)
            scores[cand.drawer_id] = scores.get(cand.drawer_id, 0.0) + contribution
            timestamps.setdefault(cand.drawer_id, cand.timestamp_unix)

    return sorted(
        (
            ScoredCandidate(
                drawer_id=did,
                timestamp_unix=timestamps[did],
                score=score,
            )
            for did, score in scores.items()
        ),
        key=lambda s: (-s.score, s.drawer_id),
    )
```

Add a `contributing_signals_acc: dict[str, set[str]]` accumulator and feed it inside the rank loop. New body:

```python
    scores: dict[str, float] = {}
    timestamps: dict[str, float] = {}
    contributing_signals_acc: dict[str, set[str]] = {}

    for signal_name, candidates in rank_lists.items():
        weight = weights.get(signal_name, 0.0)
        if weight == 0.0 or not candidates:
            # Still capture timestamps for drawers we'd otherwise miss.
            for cand in candidates:
                timestamps.setdefault(cand.drawer_id, cand.timestamp_unix)
            continue
        for rank, cand in enumerate(candidates, start=1):
            contribution = weight / (k_rrf + rank)
            scores[cand.drawer_id] = scores.get(cand.drawer_id, 0.0) + contribution
            timestamps.setdefault(cand.drawer_id, cand.timestamp_unix)
            contributing_signals_acc.setdefault(cand.drawer_id, set()).add(signal_name)

    return sorted(
        (
            ScoredCandidate(
                drawer_id=did,
                timestamp_unix=timestamps[did],
                score=score,
                contributing_signals=frozenset(contributing_signals_acc.get(did, set())),
            )
            for did, score in scores.items()
        ),
        key=lambda s: (-s.score, s.drawer_id),
    )
```

Note that the `weight == 0.0 or not candidates: continue` branch DOES NOT touch `contributing_signals_acc` — signals with zero weight are correctly excluded.

- [ ] **Step 5: Run the test, verify it passes**

Run: `pytest tests/test_fusion.py::test_weighted_rrf_populates_contributing_signals -v`
Expected: PASS

- [ ] **Step 6: Run the full fusion test suite**

Run: `pytest tests/test_fusion.py -v 2>&1 | tail -10`
Expected: All prior tests still pass (the new field has a default, so existing constructions work unchanged).

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/fusion.py tests/test_fusion.py
git commit -m "$(cat <<'EOF'
feat(fusion): track contributing_signals provenance on ScoredCandidate

Adds frozenset[str] field tracking which retrieval signals contributed
non-zero weight + had the candidate in their rank list. weighted_rrf
populates via a dict-of-sets accumulator during the rank loop; signals
with zero weight or empty rank lists are correctly excluded.

Existing 3-arg ScoredCandidate constructions keep working (default is
empty frozenset). apply_recency preservation comes in the next commit.

Unblocks SOAR's entity-match rule (PR #4c-entity-match): "kg" membership
in contributing_signals tells SOAR a hit came via KG-hop entity match.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Preserve `contributing_signals` through `apply_recency` (TDD regression guard)

**Files:**
- Modify: `cognitive_castle/fusion.py:apply_recency` (1-line addition to the ScoredCandidate reconstruction)
- Modify: `tests/test_fusion.py` (add 1 regression-guard test)

**Why a separate task:** This is the most fragile point of the implementation — `apply_recency` reconstructs `ScoredCandidate`s with updated scores, and without explicit propagation the new field silently resets to `frozenset()`, killing the signal before SOAR sees it. The spec's Half 1 calls this out in 3 places. A standalone task + dedicated test makes the preservation explicit.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fusion.py`:

```python
def test_apply_recency_preserves_contributing_signals():
    """apply_recency reconstructs ScoredCandidates with updated score AND preserves provenance.

    This is a regression guard — if apply_recency drops the contributing_signals
    field, SOAR's entity-match rule never fires.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    scored = [
        ScoredCandidate(
            drawer_id="a",
            timestamp_unix=now.timestamp(),
            score=1.0,
            contributing_signals=frozenset({"kg"}),
        )
    ]
    result = apply_recency(scored, now=now, tau_days=90.0, max_boost=1.5)
    assert result[0].contributing_signals == frozenset({"kg"}), (
        "apply_recency must preserve contributing_signals through reconstruction"
    )
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `pytest tests/test_fusion.py::test_apply_recency_preserves_contributing_signals -v`
Expected: FAIL — `AssertionError: ... preserve contributing_signals through reconstruction`. The current `apply_recency` produces a new `ScoredCandidate` with the default empty frozenset.

- [ ] **Step 3: Update `apply_recency` to propagate the field**

Locate `apply_recency` in `cognitive_castle/fusion.py` (around lines 84-124). Inside the for loop, the reconstruction looks like:

```python
        boosted.append(
            ScoredCandidate(
                drawer_id=c.drawer_id,
                timestamp_unix=c.timestamp_unix,
                score=c.score * factor,
            )
        )
```

Add the preservation:

```python
        boosted.append(
            ScoredCandidate(
                drawer_id=c.drawer_id,
                timestamp_unix=c.timestamp_unix,
                score=c.score * factor,
                contributing_signals=c.contributing_signals,
            )
        )
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `pytest tests/test_fusion.py::test_apply_recency_preserves_contributing_signals -v`
Expected: PASS

- [ ] **Step 5: Run the full fusion test suite**

Run: `pytest tests/test_fusion.py -v 2>&1 | tail -10`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/fusion.py tests/test_fusion.py
git commit -m "$(cat <<'EOF'
fix(fusion): preserve contributing_signals through apply_recency

apply_recency reconstructs ScoredCandidates with the recency-multiplied
score. Without explicit propagation, the new contributing_signals field
silently resets to the default empty frozenset — killing SOAR's
entity-match signal before any rule fires.

Regression guard: test_apply_recency_preserves_contributing_signals.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Zero-weight signal edge case (TDD)

**Files:**
- Modify: `tests/test_fusion.py` (add 1 edge-case test)

**Note:** This task adds a test only; the behavior is already correct from Task 2 (signals with `weight == 0.0` skip the rank loop before the accumulator step). The test pins the invariant so a future refactor can't silently break it.

- [ ] **Step 1: Write the test**

Append to `tests/test_fusion.py`:

```python
def test_weighted_rrf_zero_weight_signal_not_in_contributing():
    """A signal with weight=0 must NOT appear in contributing_signals.

    Regression guard: if someone refactors the early-continue in
    weighted_rrf and accidentally accumulates signal names for
    zero-weight signals, this test catches it.
    """
    rank_lists = {"dense": [_ref("a")], "sparse": [_ref("a")]}
    weights = {"dense": 1.0, "sparse": 0.0}

    result = weighted_rrf(rank_lists, weights, k_rrf=60)
    assert result[0].contributing_signals == frozenset({"dense"})
```

- [ ] **Step 2: Run the test (should already pass)**

Run: `pytest tests/test_fusion.py::test_weighted_rrf_zero_weight_signal_not_in_contributing -v`
Expected: PASS (Task 2's implementation already handles this correctly).

- [ ] **Step 3: Run the full fusion test suite**

Run: `pytest tests/test_fusion.py -v 2>&1 | tail -10`
Expected: All tests pass — 3 new tests in this PR so far.

- [ ] **Step 4: Commit**

```bash
git add tests/test_fusion.py
git commit -m "$(cat <<'EOF'
test(fusion): zero-weight signal regression guard

Pins the invariant that weighted_rrf excludes zero-weight signals from
contributing_signals. Already correct from the prior commit; this test
keeps it locked in if someone refactors the early-continue in the
fusion loop.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Thread `entity_match` flag into rows + surface in final hit dict (TDD)

**Files:**
- Modify: `cognitive_castle/searcher.py` (build `entity_match_by_id` from `fused[:k_cap]`; attach to row dicts; surface in final hit dict)
- Modify: `tests/test_pipeline_order.py` (add 1 integration-shape test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline_order.py`:

```python
def test_entity_match_flag_attaches_to_kg_hop_rows(monkeypatch, tmp_path):
    """In _new_pipeline_search, KG-hop hits get row['entity_match']=True; non-KG hits get False.

    Strategy: stub the recall paths (dense/sparse/kg) so we control which signals fire for
    which ids. Stub col.get_by_ids to return matching row dicts. Run _new_pipeline_search.
    Inspect the final hit dicts.
    """
    import cognitive_castle.searcher as searcher_mod
    from cognitive_castle.fusion import CandidateRef

    # Stage 1: mock recall paths via vector_search + fts_search + KG lookup
    # We monkeypatch at the call sites inside _new_pipeline_search.

    class FakeCollection:
        def vector_search(self, query_vec, n_results, where=None):
            return [{"id": "dense-only", "wing": "x", "room": "r", "source_file": "f.md", "text": "dense"}]

        def fts_search(self, query, n_results, where=None):
            return []

        def get_by_ids(self, ids):
            # Return rows in the order of IDs requested; include both ids
            id_to_row = {
                "kg-hit": {"id": "kg-hit", "wing": "x", "room": "r", "source_file": "f.md",
                           "text": "kg hit", "decay_score": 1.0, "chunk_index": 0,
                           "metadata_json": "{}"},
                "dense-only": {"id": "dense-only", "wing": "x", "room": "r", "source_file": "f.md",
                               "text": "dense only", "decay_score": 1.0, "chunk_index": 0,
                               "metadata_json": "{}"},
            }
            return [id_to_row[i] for i in ids if i in id_to_row]

    # Stub _get_collection to return our FakeCollection
    monkeypatch.setattr(
        "cognitive_castle.palace.get_collection",
        lambda *a, **kw: FakeCollection(),
    )

    # Stub the embedder to skip model loads
    monkeypatch.setattr(
        "cognitive_castle.embedding.embed_texts",
        lambda texts: [[0.0] * 384 for _ in texts],
    )

    # Stub the KG-hop path to return "kg-hit" only
    import cognitive_castle.knowledge_graph as kg_mod
    monkeypatch.setattr(
        kg_mod.KnowledgeGraph,
        "find_drawers_by_entities",
        lambda self, entities, top_n: ["kg-hit"],
    )
    monkeypatch.setattr(
        "cognitive_castle.entity_registry.EntityRegistry.lookup_in_text",
        lambda self, text: ["entity-1"],
    )

    # Stub the cross-encoder rerank to return scores preserving input order
    monkeypatch.setattr(
        "cognitive_castle.reranker.rerank",
        lambda query, docs, cfg: [1.0 - i * 0.1 for i in range(len(docs))],
    )

    # Now run the pipeline
    from cognitive_castle.config import CognitiveCastleConfig
    cfg = CognitiveCastleConfig()

    result = searcher_mod._new_pipeline_search(
        query="test",
        palace_path=str(tmp_path),
        wing=None,
        room=None,
        n_results=10,
        cfg=cfg,
    )

    # Find the kg-hit and dense-only hits in the result
    by_id = {hit["id"]: hit for hit in result}
    assert "kg-hit" in by_id, f"Expected kg-hit in results, got ids: {list(by_id)}"
    assert "dense-only" in by_id, f"Expected dense-only in results, got ids: {list(by_id)}"
    assert by_id["kg-hit"]["entity_match"] is True, (
        "kg-hit came via KG-hop; entity_match should be True"
    )
    assert by_id["dense-only"]["entity_match"] is False, (
        "dense-only came via dense vector search only; entity_match should be False"
    )
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `pytest tests/test_pipeline_order.py::test_entity_match_flag_attaches_to_kg_hop_rows -v`
Expected: FAIL — the final hit dict doesn't have `entity_match` key yet (KeyError or False on both).

- [ ] **Step 3: Update `_new_pipeline_search` to derive + attach entity_match**

Open `cognitive_castle/searcher.py`. Locate the region around lines 553-573 (the post-fusion / pre-rerank section). The current code:

```python
    fused = weighted_rrf(rank_lists, weights, k_rrf=cfg.k_rrf)
    fused = apply_recency(
        fused,
        now=datetime.now(timezone.utc),
        tau_days=cfg.recency_tau_days,
        max_boost=cfg.recency_max_boost,
    )

    # ── Stage 3: cross-encoder rerank ──────────────────────────────────────
    k_cap = cfg.reranker_k_hook if is_hook_call else cfg.reranker_k_interactive
    top_k_ids = [s.drawer_id for s in fused[:k_cap]]
    if not top_k_ids:
        return []

    top_k_rows = col.get_by_ids(top_k_ids)
    if not top_k_rows:
        return []
```

Insert the entity-match derivation between `top_k_ids` and `col.get_by_ids`, plus an attach loop after `col.get_by_ids`:

```python
    fused = weighted_rrf(rank_lists, weights, k_rrf=cfg.k_rrf)
    fused = apply_recency(
        fused,
        now=datetime.now(timezone.utc),
        tau_days=cfg.recency_tau_days,
        max_boost=cfg.recency_max_boost,
    )

    # ── Stage 3: cross-encoder rerank ──────────────────────────────────────
    k_cap = cfg.reranker_k_hook if is_hook_call else cfg.reranker_k_interactive
    top_k_ids = [s.drawer_id for s in fused[:k_cap]]
    if not top_k_ids:
        return []

    # Derive entity-match flag from fusion provenance for the top-K candidates.
    entity_match_by_id = {
        sc.drawer_id: "kg" in sc.contributing_signals
        for sc in fused[:k_cap]
    }

    top_k_rows = col.get_by_ids(top_k_ids)
    if not top_k_rows:
        return []

    # Attach entity-match flag to each row so SOAR can read it via _push_working_memory.
    for row in top_k_rows:
        if isinstance(row, dict):
            row["entity_match"] = entity_match_by_id.get(row.get("id"), False)
```

- [ ] **Step 4: Surface `entity_match` in the final hit dict**

Locate the final-hit construction at the end of `_new_pipeline_search` (the `return [...]` block). Find the dict comprehension that builds each hit:

```python
    return [
        {
            "id": _extract_id(r),
            "text": _extract_text(r),
            "document": _extract_text(r),
            "score": float(s),
            "wing": r.get("wing", "") if isinstance(r, dict) else "",
            "room": r.get("room", "") if isinstance(r, dict) else "",
            "source_file": (r.get("source_file") or "") if isinstance(r, dict) else "",
            "created_at": _get_filed_at(r),
            "similarity": float(s),
        }
        for s, r in reranked[:n_results]
    ]
```

Add one line for `entity_match` (insertion point: between `similarity` and the closing brace, or anywhere — naming matches the existing snake_case audit-trail pattern):

```python
    return [
        {
            "id": _extract_id(r),
            "text": _extract_text(r),
            "document": _extract_text(r),
            "score": float(s),
            "wing": r.get("wing", "") if isinstance(r, dict) else "",
            "room": r.get("room", "") if isinstance(r, dict) else "",
            "source_file": (r.get("source_file") or "") if isinstance(r, dict) else "",
            "created_at": _get_filed_at(r),
            "similarity": float(s),
            "entity_match": (r.get("entity_match", False) if isinstance(r, dict) else False),
        }
        for s, r in reranked[:n_results]
    ]
```

- [ ] **Step 5: Run the test, verify it passes**

Run: `pytest tests/test_pipeline_order.py::test_entity_match_flag_attaches_to_kg_hop_rows -v`
Expected: PASS

If the test fails because of an unexpected stub interaction (e.g., the embedder mock isn't picked up, or fusion expects timestamps in a specific format), inspect the test output and adjust the stubs. The test as written is a starting point; the exact monkeypatch surface may need minor adjustments to match the actual code paths.

- [ ] **Step 6: Run wider tests**

Run: `pytest tests/test_fusion.py tests/test_pipeline_order.py tests/test_retrieval_pipeline.py 2>&1 | tail -10`
Expected: No NEW failures vs baseline.

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/searcher.py tests/test_pipeline_order.py
git commit -m "$(cat <<'EOF'
feat(searcher): thread entity_match flag from fusion to final hits

After Stage 2 fusion+recency, _new_pipeline_search derives entity_match_by_id
from the top-K candidates' contributing_signals ("kg" membership). The flag
is attached to each LanceDB row dict so _push_working_memory will read it,
and surfaced in the final hit dict for audit/debugging.

Test: test_entity_match_flag_attaches_to_kg_hop_rows verifies KG-hop hits
get entity_match=True and dense-only hits get False.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Add `entity-match` SOAR rule + push to WM + multiplier (TDD)

**Files:**
- Modify: `cognitive_castle/soar_bridge.py` (add to `BOOST_MULTIPLIERS`; update `_push_working_memory`)
- Modify: `cognitive_castle/rules/castle-boost.soar` (add production; update header schema)
- Modify: `tests/test_soar_bridge.py` (add 2 tests)

This task is the integration point: the rule, the multiplier, and the WM push all need to be in place together for the rule to actually fire.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_soar_bridge.py`:

```python
def test_entity_match_boost_applied_when_flag_true(tmp_path):
    """A hit with entity_match=True fires the entity-match rule.

    Uses the existing _mock_cfg helper from this file. Requires SML to actually
    fire the rule; on test environments without SML, the boost-tag never appears.
    """
    from cognitive_castle import soar_bridge

    hits = [
        {
            "id": "a",
            "score": 1.0,
            "wing": "x",
            "room": "r",
            "source_file": "f",
            "entity_match": True,
            "created_at": "2020-01-01T00:00:00Z",  # old → recency-boost won't fire
        }
    ]
    cfg = _mock_cfg(palace_path=str(tmp_path))

    boosted = soar_bridge.apply_soar_boosts(hits, cfg)
    # On SML-available environments, the rule fires
    if soar_bridge._load_sml() is not None:
        assert "entity-match" in boosted[0]["soar_tags"], (
            f"Expected entity-match tag to fire; got soar_tags={boosted[0]['soar_tags']}"
        )
        assert boosted[0]["soar_boost"] >= 1.30, (
            f"Expected boost >= 1.30, got {boosted[0]['soar_boost']}"
        )


def test_entity_match_boost_not_applied_when_flag_false(tmp_path):
    """A hit with entity_match=False does NOT fire the entity-match rule."""
    from cognitive_castle import soar_bridge

    hits = [
        {
            "id": "a",
            "score": 1.0,
            "wing": "x",
            "room": "r",
            "source_file": "f",
            "entity_match": False,
            "created_at": "2020-01-01T00:00:00Z",
        }
    ]
    cfg = _mock_cfg(palace_path=str(tmp_path))

    boosted = soar_bridge.apply_soar_boosts(hits, cfg)
    if soar_bridge._load_sml() is not None:
        assert "entity-match" not in boosted[0]["soar_tags"], (
            "Rule should not fire when entity_match=False"
        )
```

Note: the tests use the `_load_sml()` check pattern to skip the rule-fire assertions on environments without SML installed. The dev box has SML; CI typically doesn't. This matches the pattern other soar_bridge tests use.

- [ ] **Step 2: Run the tests, verify the True-branch fails**

Run: `pytest tests/test_soar_bridge.py::test_entity_match_boost_applied_when_flag_true tests/test_soar_bridge.py::test_entity_match_boost_not_applied_when_flag_false -v`
Expected:
- `test_entity_match_boost_applied_when_flag_true`: FAIL on SML-available env (rule doesn't exist yet; assertion fails). On non-SML env: passes vacuously (the `if soar_bridge._load_sml() is not None` skips assertions).
- `test_entity_match_boost_not_applied_when_flag_false`: PASS (rule doesn't exist, so it can't fire — correct behavior).

- [ ] **Step 3: Add `"entity-match"` to `BOOST_MULTIPLIERS` in `cognitive_castle/soar_bridge.py`**

Locate the `BOOST_MULTIPLIERS` dict (around line 39). Add a third entry:

```python
BOOST_MULTIPLIERS: dict[str, float] = {
    "recency-boost": 1.25,  # ^recently-accessed "true" (age < 7d default)
    "same-project": 1.15,   # ^project matches ^io.input-link.context.project
    "entity-match": 1.30,   # ^entity-match "true" (hit came via KG-hop entity match)
}
```

The 1.30 value is an initial guess (same disclaimer pattern as the other two; tunable in a follow-up).

- [ ] **Step 4: Update `_push_working_memory` to push `^entity-match`**

Locate `_push_working_memory` in `cognitive_castle/soar_bridge.py` (around line 205). Inside the per-hit loop (around lines 232-250), after the `^recently-accessed` push, add:

```python
        # ^entity-match: "true" if hit came via KG-hop (fusion provenance flag),
        # else "false". String symbol to match the recently-accessed pattern.
        entity_match = "true" if hit.get("entity_match") else "false"
        m.CreateStringWME("entity-match", entity_match)
```

Place this AFTER the existing `m.CreateStringWME("recently-accessed", recent)` line and BEFORE `memory_wmes[composite_id] = m`.

- [ ] **Step 5: Add the new production to `cognitive_castle/rules/castle-boost.soar`**

Open `cognitive_castle/rules/castle-boost.soar`. First, update the header docstring (around lines 8-13) to include `^entity-match` in the documented WM schema:

```
## Schema (pushed to input-link by soar_bridge.py):
##   state ^io.input-link <il>
##   <il>  ^context <ctx>
##         ^memory  <m>     (one per hit, up to 50)
##   <ctx> ^project       <string>
##   <m>   ^id                <string>  (composite: wing/room/source_file)
##         ^project           <string>  (from hit.wing)
##         ^score             <float>   (Stage 3+4 score)
##         ^age-seconds       <int>
##         ^recently-accessed true|false
##         ^entity-match      true|false  (came via KG-hop entity match)
```

Then append the new production at the bottom of the file (after the existing `same-project` rule):

```
sp {castle-boost*entity-match
    "Boost hits whose drawer shares an entity with the query (came via KG-hop)."
    (state <s> ^io.input-link.memory <m>)
    (<m> ^entity-match true)
-->
    (<m> ^boost-tag entity-match)
}
```

(Production naming follows the `castle-boost*<rule-name>` convention from the existing rules.)

- [ ] **Step 6: Run the tests, verify they pass**

Run: `pytest tests/test_soar_bridge.py::test_entity_match_boost_applied_when_flag_true tests/test_soar_bridge.py::test_entity_match_boost_not_applied_when_flag_false -v`
Expected: PASS (on SML-available envs the rule now fires; on non-SML envs the assertions skip).

- [ ] **Step 7: Run the full soar_bridge test suite**

Run: `pytest tests/test_soar_bridge.py -v 2>&1 | tail -10`
Expected: All prior tests still pass (12+ tests from #4a/#4b + 2 new).

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/soar_bridge.py cognitive_castle/rules/castle-boost.soar tests/test_soar_bridge.py
git commit -m "$(cat <<'EOF'
feat(soar): add entity-match production + BOOST_MULTIPLIERS entry

Third SOAR boost-tag production: castle-boost*entity-match fires when
^entity-match is "true" on a memory WME and adds ^boost-tag entity-match.
The Python bridge maps the tag to BOOST_MULTIPLIERS["entity-match"] = 1.30
(initial guess, tunable).

_push_working_memory now pushes ^entity-match true|false per hit, sourced
from the hit dict's entity_match field (threaded from fusion provenance
in the previous commit).

castle-boost.soar header docstring updated to document the new ^entity-match
WM attribute.

Two new tests in test_soar_bridge.py exercise the rule's fire/skip behavior;
on environments without SML, the rule-fire assertions are skipped (matching
the pattern of other soar_bridge tests).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md` (mention 3 SOAR productions instead of 2; name `entity-match`)

- [ ] **Step 1: Update the SOAR rules description in CLAUDE.md**

Open `/home/lbihari/cognitive-castle/CLAUDE.md`. Locate the retrieval-pipeline diagram region (search for `Stage 5` or `--soar-boost`). The current description (added by PR #4a) mentions 2 productions: `recency-boost` and `same-project`. Update to name 3.

Use the Read tool first to find the exact current text, then Edit with the verbatim old_string. The change is small (adding `entity-match` to a list, possibly bumping a count). Example shape:

Before:
```
SOAR symbolic productions add boost-tags
```

After (if a count is mentioned anywhere):
```
3 SOAR symbolic productions (recency-boost, same-project, entity-match) add boost-tags
```

If CLAUDE.md doesn't enumerate the rules explicitly, this task is a no-op aside from any "follow-up rules deferred" comment that should now exclude `entity-match`. Check the file content and make the minimal accurate change.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(CLAUDE.md): name entity-match as a SOAR production

Updates the retrieval pipeline description to reflect 3 SOAR productions
(recency-boost, same-project, entity-match) shipped, with entity-match
landing in PR #4c-entity-match.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Lint + full test suite

**Files:** None — verification only

- [ ] **Step 1: Run ruff format check on touched files**

Run:
```bash
ruff format --check cognitive_castle/fusion.py cognitive_castle/searcher.py cognitive_castle/soar_bridge.py tests/test_fusion.py tests/test_pipeline_order.py tests/test_soar_bridge.py
```
Expected: All formatted correctly. If not, run `ruff format` on the listed files. The `.soar` file is not a Python file; ruff ignores it.

- [ ] **Step 2: Run ruff check**

Run: `ruff check cognitive_castle/ tests/test_fusion.py tests/test_pipeline_order.py tests/test_soar_bridge.py`
Expected: All checks pass.

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -5`
Expected: 18 baseline failures (CI-UNSTABLE) + ~1452 passes (~6 more than develop, from this PR's new tests). No NEW failures.

- [ ] **Step 4: If formatting/lint issues found, fix + commit separately**

```bash
ruff format cognitive_castle/fusion.py cognitive_castle/searcher.py cognitive_castle/soar_bridge.py tests/test_fusion.py tests/test_pipeline_order.py tests/test_soar_bridge.py
git add -p  # stage only PR-scope formatting changes
git commit -m "style: ruff format after entity-match changes

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Per the pattern established in earlier PRs this session: if `ruff format` touched files OUTSIDE this PR's scope (e.g., `cognitive_castle/embedding.py`), use `git restore <those files>` to keep them out — those are pre-existing drift, not this PR's concern.

If no fixes needed, skip this step.

---

### Task 9: Smoke + push + PR

**Files:** None — verification + git operations

- [ ] **Step 1: Live smoke against developer's palace**

The developer's `~/.castle/palace` is currently a 384-dim legacy MiniLM palace, so `castle search` will hit the friendly `EmbedderIdentityMismatchError` first. That's fine — the goal is to verify the new flag doesn't crash on the way in.

Run: `castle --palace ~/.castle/palace search "test" 2>&1 | head -10`
Expected: Friendly migration prompt (`EmbedderIdentityMismatchError`). NOT a crash from the new `entity_match` field or fusion code.

If the developer's palace gets reindexed to bge-m3 during this session, try:

Run: `CASTLE_SOAR_ENABLED=1 castle --palace ~/.castle/palace search "ladislav cognitive castle" --soar-boost --results 3 2>&1`
Expected: 3 hits. Some hits may have `entity-match` in their soar_tags (if KG-hop returned them); others may not. No crash.

- [ ] **Step 2: Push branch**

Run: `git push -u origin feat/soar-entity-match`
Expected: Branch pushed; PR URL printed.

- [ ] **Step 3: Open PR**

```bash
gh pr create --title "feat: SOAR entity-match rule + fusion provenance (PR #4c-entity-match)" --body "$(cat <<'EOF'
## Summary

First slice of the SOAR umbrella's #4c work — unblocks the `entity-match` rule deferred from PR #4a. Threads hit-provenance from `fusion.py` (which signal contributed each hit) through `_new_pipeline_search` into SOAR's working memory, enabling a third SOAR production that boosts hits whose drawer shares an entity with the query.

- **New `contributing_signals: frozenset[str]` field on `ScoredCandidate`** — populated during `weighted_rrf` from per-signal rank lists; preserved explicitly through `apply_recency` (the most fragile point — regression-guarded with a dedicated test).
- **Entity-match flag threading** — after fusion, `_new_pipeline_search` derives `entity_match_by_id = {drawer_id: "kg" in contributing_signals}` and attaches `row["entity_match"] = bool` to each LanceDB row. `_push_working_memory` reads this and pushes `^entity-match true|false` to SOAR's WM.
- **New `castle-boost*entity-match` production** — fires when `^entity-match true` and adds `^boost-tag entity-match`. `BOOST_MULTIPLIERS["entity-match"] = 1.30` (initial guess, tunable).
- **`entity_match` surfaced in final hit dict** — alongside the existing audit-trail fields (`score_pre_soar`, `soar_boost`, `soar_tags`). Consumers ignoring unknown fields keep working.

Scope: single rule. `type-match` (needs drawer-type schema + query intent classification) and `stale-penalty` (needs "what counts as access" design) explicitly deferred to their own future specs. Active learning from judge disagreement deferred indefinitely.

## Spec + Plan

- Spec: `docs/superpowers/specs/2026-05-13-soar-entity-match-design.md`
- Plan: `docs/superpowers/plans/2026-05-13-soar-entity-match.md`

## Test plan

- [x] `tests/test_fusion.py`: 3 new tests — `test_weighted_rrf_populates_contributing_signals`, `test_apply_recency_preserves_contributing_signals`, `test_weighted_rrf_zero_weight_signal_not_in_contributing`
- [x] `tests/test_pipeline_order.py`: 1 new test — `test_entity_match_flag_attaches_to_kg_hop_rows`
- [x] `tests/test_soar_bridge.py`: 2 new tests — `test_entity_match_boost_applied_when_flag_true`, `test_entity_match_boost_not_applied_when_flag_false` (rule-fire assertions skip on non-SML envs, matching the existing test pattern)
- [x] `pytest tests/ --ignore=tests/benchmarks` — 18 baseline CI-UNSTABLE failures preserved, ~6 new passes from this PR's tests
- [x] `ruff check` + `ruff format --check` clean on touched files
- [x] Live smoke against developer's palace: search command doesn't crash; friendly `EmbedderIdentityMismatchError` still fires correctly on the legacy 384-dim palace

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR URL printed.

---

## Self-Review

### Spec coverage check

| Spec section / requirement | Plan task |
|---|---|
| Half 1: `contributing_signals` field on `ScoredCandidate` | Task 2 |
| Half 1: `weighted_rrf` populates the field with dict-of-sets accumulator | Task 2 |
| Half 1: `apply_recency` preserves the field (most fragile point) | Task 3 (dedicated task + regression-guard test) |
| Half 1: zero-weight signals correctly NOT in contributing_signals | Task 4 (edge-case regression test) |
| Half 2: derive `entity_match_by_id` from `fused[:k_cap]` and attach to rows | Task 5 |
| Half 3: `BOOST_MULTIPLIERS["entity-match"] = 1.30` | Task 6 |
| Half 3: `_push_working_memory` pushes `^entity-match true|false` | Task 6 |
| Half 3: new `castle-boost*entity-match` production + updated header docstring schema | Task 6 |
| Half 4: surface `entity_match` in final hit dict | Task 5 (combined since both edits live in `_new_pipeline_search`) |
| `1.30` flagged as initial guess (tunable) | Task 6 (inline code comment) + PR description |
| CLAUDE.md update | Task 7 |
| Lint clean | Task 8 |
| Full test suite (no NEW failures) | Task 8 |
| Acceptance #1-6 (all new tests pass + baseline preserved) | Tasks 2-6 (per-task verification) + Task 8 (final sweep) |
| Acceptance #7 (default invocation surfaces `entity_match` field) | Task 5 |
| Acceptance #8 (KG-hop hits get `entity-match` soar_tag on `--soar-boost`) | Task 6 |
| Acceptance #9 (CLAUDE.md mentions 3 productions) | Task 7 |
| Acceptance #10 (.soar file contains new production with docstring) | Task 6 |

All spec requirements have a task. No gaps.

### Placeholder scan

No "TBD" / "TODO" / "similar to" / "add appropriate error handling" placeholders. Every step has exact code, exact commands, or specific git operations. The 1 pipeline test (Task 5) uses monkeypatch stubs whose exact paths may need minor adjustment when actually run; the test body is shown in full and the strategy is clearly described. Acceptable — the alternative would be a placeholder.

### Type consistency

- `contributing_signals: frozenset[str] = frozenset()` field on `ScoredCandidate` — defined in Task 2, consumed in Task 3 (preservation), Task 4 (edge case), Task 5 (derivation in `_new_pipeline_search`)
- `entity_match` snake_case field on row dict + final hit dict — set in Task 5, read in Task 6 (`_push_working_memory`)
- `^entity-match true|false` SOAR WM attribute — push in Task 6, match in Task 6's `.soar` production
- `BOOST_MULTIPLIERS["entity-match"] = 1.30` — defined in Task 6, multiplier applied by the existing `apply_soar_boosts` logic (no new code needed in the multiplier path)
- All names consistent across tasks. No drift.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-13-soar-entity-match.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
