# SOTA Retrieval Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Castle's 2021-vintage retrieval (all-MiniLM-L6-v2 + custom Python BM25) with a 2025 SOTA stack: bge-m3 dense embeddings, LanceDB Tantivy FTS for the lexical signal, cross-encoder reranking, KG-hop retrieval signal, and recency boost in fusion.

**Architecture:** Three-stage pipeline. Stage 1 fans out into three parallel candidate sources (dense vector, sparse FTS, KG-hop entity match). Stage 2 fuses with weighted RRF + recency multiplier. Stage 3 cross-encoder reranks top-K. Configuration is the rollout vehicle — every change is config-driven and additive until the final cutover, so the test suite stays green throughout.

**Tech Stack:** Python 3.9+, LanceDB ≥0.20, sentence-transformers ≥3.0 (already shipped), `BAAI/bge-m3` (1024-dim multilingual embedder), `BAAI/bge-reranker-base` / `bge-reranker-v2-m3` (device-aware), SQLite (existing knowledge graph), pytest + existing test fixtures.

---

## Spec corrections noted during planning

- The spec's acceptance criterion (`convomem_bench.py`, `locomo_bench.py`, `longmemeval_bench.py`) references files that **do not exist** in this repo. The actual recall-quality benchmarks are under `tests/benchmarks/` and include `test_search_bench.py`, `test_recall_threshold.py`, and `test_knowledge_graph_bench.py`. This plan's Task 15 (benchmark tuning) and Task 16 (final acceptance) use the real files.
- Searcher has **two entry points**: `search()` (CLI) and `search_memories()` (API). Both must route to the new 3-stage pipeline. The plan accounts for both.

## Sequencing strategy (read first)

The dense vector dimension changes from 384 to 1024. This is a schema break that would invalidate every test that touches LanceDB if done naïvely. The plan's solution: **make every change config-driven first; flip the defaults only at the cutover task (Task 13)**. Until then the default behavior is unchanged, so the existing test suite stays green.

Phase order:
1. **Tasks 1–6:** Pure additive (new modules + new helper methods). No defaults change.
2. **Tasks 7–10:** Make existing modules config-driven. Default config still produces today's behavior.
3. **Task 11:** New 3-stage pipeline lives behind a config flag (off by default).
4. **Task 12:** `castle reindex` command exists and works on small fixtures.
5. **Task 13:** Cutover — flip defaults to bge-m3 + 1024-dim + new pipeline. Update tests that hardcoded 384.
6. **Tasks 14–16:** Cleanup, benchmark tuning, final acceptance.

---

## File structure

### New files

| File | Lines | Responsibility |
|---|---|---|
| `cognitive_castle/fusion.py` | ~80 | Pure functions: weighted RRF + recency multiplier. Dataclasses for `CandidateRef`, `ScoredCandidate`. |
| `cognitive_castle/reranker.py` | ~100 | Lazy singleton wrapper around the cross-encoder. Device-aware model selection. |
| `tests/test_fusion.py` | ~120 | Unit tests for fusion functions. |
| `tests/test_reranker.py` | ~60 | Reranker smoke + device-resolution tests. |
| `tests/test_kg_hop.py` | ~80 | `find_drawers_by_entities` integration test. |
| `tests/test_entity_registry_lookup.py` | ~70 | `lookup_in_text` unit tests. |
| `tests/test_retrieval_pipeline.py` | ~150 | End-to-end pipeline integration test. |

### Modified files

| File | Change |
|---|---|
| `cognitive_castle/config.py` | Add embedder, reranker, fusion, recency, K-cap config keys. Bump `embedder_identity` hash. |
| `cognitive_castle/embedding.py` | Read model name + dim from config. Default unchanged until cutover. |
| `cognitive_castle/backends/lancedb_backend.py` | `EMBED_DIM` becomes config-driven. Add Tantivy FTS index creation + a sparse-search method. |
| `cognitive_castle/searcher.py` | Add new 3-stage pipeline behind a config flag. At cutover, delete `_bm25_scores`, `_hybrid_rank`, `_bm25_only_via_lancedb`, `_merge_bm25_union_candidates`. |
| `cognitive_castle/knowledge_graph.py` | Add `find_drawers_by_entities(entity_ids, limit)`. |
| `cognitive_castle/entity_registry.py` | Add `lookup_in_text(query, max_edit_distance)`. |
| `cognitive_castle/cli.py` | Add `castle reindex` subcommand. |

### Modified or potentially deleted tests

| File | Likely action |
|---|---|
| `tests/test_searcher.py` | Update assertions for new pipeline behavior. |
| `tests/test_hybrid_search.py` | Most assertions about BM25 internals become moot — rewrite for FTS or delete cases that no longer apply. |
| `tests/test_hybrid_candidate_union.py` | Same — `_merge_bm25_union_candidates` is gone post-cutover. |
| `tests/test_embedding.py` | Update for config-driven model + 1024-dim default. |
| `tests/test_backends.py` | Update schema dim assertions. |

---

## Task 1: Add config keys (no behavior change)

**Files:**
- Modify: `cognitive_castle/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_config_has_retrieval_upgrade_keys():
    from cognitive_castle.config import CognitiveCastleConfig
    cfg = CognitiveCastleConfig()
    # Embedder defaults preserve current behavior at this point.
    assert cfg.embedder_model == "all-MiniLM-L6-v2"
    assert cfg.embedder_dim == 384
    # Reranker config exists with sane defaults.
    assert cfg.reranker_model_gpu == "BAAI/bge-reranker-v2-m3"
    assert cfg.reranker_model_cpu == "BAAI/bge-reranker-base"
    assert cfg.reranker_k_interactive == 20
    assert cfg.reranker_k_hook == 10
    # Fusion + recency.
    assert cfg.k_rrf == 60
    assert cfg.weight_dense == 1.0
    assert cfg.weight_sparse == 1.0
    assert cfg.weight_kg == 0.5
    assert cfg.recency_tau_days == 90.0
    assert cfg.recency_max_boost == 1.5
    # KG-hop.
    assert cfg.kg_hop_top_n == 50
    # New pipeline flag.
    assert cfg.use_new_retrieval_pipeline is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_config_has_retrieval_upgrade_keys -v`
Expected: FAIL with `AttributeError` on the first missing attribute.

- [ ] **Step 3: Add config fields**

In `cognitive_castle/config.py`, find the `CognitiveCastleConfig` (or equivalent) class and add the fields with the defaults asserted above. Preserve all existing fields.

```python
# In CognitiveCastleConfig class
embedder_model: str = "all-MiniLM-L6-v2"
embedder_dim: int = 384
reranker_model_gpu: str = "BAAI/bge-reranker-v2-m3"
reranker_model_cpu: str = "BAAI/bge-reranker-base"
reranker_k_interactive: int = 20
reranker_k_hook: int = 10
k_rrf: int = 60
weight_dense: float = 1.0
weight_sparse: float = 1.0
weight_kg: float = 0.5
recency_tau_days: float = 90.0
recency_max_boost: float = 1.5
kg_hop_top_n: int = 50
use_new_retrieval_pipeline: bool = False
```

If `CognitiveCastleConfig` reads from a config file (TOML/JSON), thread these through the file-loading path too, with the same defaults if the user hasn't set them.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_config_has_retrieval_upgrade_keys -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite to confirm no regression**

Run: `pytest tests/ -v --ignore=tests/benchmarks -q`
Expected: All previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/config.py tests/test_config.py
git commit -m "feat(config): add retrieval-upgrade config keys (defaults preserve current behavior)"
```

---

## Task 2: Build `fusion.py` — `weighted_rrf`

**Files:**
- Create: `cognitive_castle/fusion.py`
- Test: `tests/test_fusion.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_fusion.py`:

```python
"""Unit tests for fusion: weighted RRF + recency."""
from datetime import datetime, timedelta, timezone

import pytest

from cognitive_castle.fusion import (
    CandidateRef,
    ScoredCandidate,
    weighted_rrf,
    apply_recency,
)


def _ref(drawer_id: str, ts_unix: float = 0.0) -> CandidateRef:
    return CandidateRef(drawer_id=drawer_id, timestamp_unix=ts_unix)


class TestWeightedRRF:
    def test_single_signal_preserves_order(self):
        rank_lists = {"dense": [_ref("a"), _ref("b"), _ref("c")]}
        weights = {"dense": 1.0}
        out = weighted_rrf(rank_lists, weights, k_rrf=60)
        assert [s.drawer_id for s in out] == ["a", "b", "c"]
        # Score should decrease.
        assert out[0].score > out[1].score > out[2].score

    def test_two_signals_agree(self):
        rank_lists = {
            "dense": [_ref("a"), _ref("b"), _ref("c")],
            "sparse": [_ref("a"), _ref("b"), _ref("c")],
        }
        weights = {"dense": 1.0, "sparse": 1.0}
        out = weighted_rrf(rank_lists, weights, k_rrf=60)
        assert [s.drawer_id for s in out] == ["a", "b", "c"]

    def test_two_signals_disagree(self):
        # Drawer "x" is top in dense but bottom in sparse.
        # Drawer "y" is bottom in dense but top in sparse.
        # With equal weights, they should tie or be close; pick by drawer_id sort for determinism.
        rank_lists = {
            "dense": [_ref("x"), _ref("y")],
            "sparse": [_ref("y"), _ref("x")],
        }
        weights = {"dense": 1.0, "sparse": 1.0}
        out = weighted_rrf(rank_lists, weights, k_rrf=60)
        assert {s.drawer_id for s in out} == {"x", "y"}
        # Both candidates appear.
        assert len(out) == 2

    def test_missing_signal_treated_as_unranked(self):
        rank_lists = {
            "dense": [_ref("a"), _ref("b")],
            "sparse": [_ref("a")],   # b is missing from sparse
        }
        weights = {"dense": 1.0, "sparse": 1.0}
        out = weighted_rrf(rank_lists, weights, k_rrf=60)
        # 'a' appears in both, 'b' only in dense -> 'a' wins.
        assert out[0].drawer_id == "a"
        assert out[1].drawer_id == "b"

    def test_weight_changes_outcome(self):
        # 'x' wins on dense, 'y' on sparse. Heavily weight sparse -> 'y' should win.
        rank_lists = {
            "dense": [_ref("x"), _ref("y")],
            "sparse": [_ref("y"), _ref("x")],
        }
        weights = {"dense": 0.1, "sparse": 1.0}
        out = weighted_rrf(rank_lists, weights, k_rrf=60)
        assert out[0].drawer_id == "y"

    def test_empty_rank_lists_returns_empty(self):
        assert weighted_rrf({}, {}, k_rrf=60) == []

    def test_k_rrf_smoothing(self):
        # Larger k_rrf should compress score differences (smoother).
        rank_lists = {"dense": [_ref("a"), _ref("b"), _ref("c")]}
        weights = {"dense": 1.0}
        small_k = weighted_rrf(rank_lists, weights, k_rrf=1)
        large_k = weighted_rrf(rank_lists, weights, k_rrf=1000)
        # Score gap a→b shrinks as k_rrf grows.
        gap_small = small_k[0].score - small_k[1].score
        gap_large = large_k[0].score - large_k[1].score
        assert gap_large < gap_small
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_fusion.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cognitive_castle.fusion'`.

- [ ] **Step 3: Implement `fusion.py` (just `weighted_rrf` for this task)**

Create `cognitive_castle/fusion.py`:

```python
"""fusion.py — weighted Reciprocal Rank Fusion + recency multiplier.

Pure functions, no I/O, no model loads. Inputs are simple data structures so
this module is trivially unit-testable in isolation from the retrieval
pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CandidateRef:
    """A drawer reference produced by a single retrieval signal."""
    drawer_id: str
    timestamp_unix: float


@dataclass(frozen=True)
class ScoredCandidate:
    """A drawer reference with a fused score."""
    drawer_id: str
    timestamp_unix: float
    score: float


def weighted_rrf(
    rank_lists: dict[str, list[CandidateRef]],
    weights: dict[str, float],
    k_rrf: int = 60,
) -> list[ScoredCandidate]:
    """Compute weighted reciprocal rank fusion across multiple signals.

    For each drawer that appears in any signal's rank list, score is
    sum_{signal} weight[signal] / (k_rrf + rank_in_signal). Drawers absent
    from a signal contribute 0 from that signal. Returned in descending
    score order; ties broken by drawer_id for determinism.

    Parameters
    ----------
    rank_lists:
        Map of signal_name -> ordered list of candidates (best first, rank 1).
    weights:
        Map of signal_name -> weight applied to that signal's contribution.
        Signals present in rank_lists but absent here are treated as weight 0.
    k_rrf:
        RRF smoothing constant. Larger values compress score differences.

    Returns
    -------
    list[ScoredCandidate]
        All unique drawers seen, ordered by descending score.
    """
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


# apply_recency added in next task.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_fusion.py::TestWeightedRRF -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/fusion.py tests/test_fusion.py
git commit -m "feat(fusion): add weighted reciprocal rank fusion with deterministic tie-breaking"
```

---

## Task 3: `fusion.py` — `apply_recency`

**Files:**
- Modify: `cognitive_castle/fusion.py`
- Modify: `tests/test_fusion.py`

- [ ] **Step 1: Add failing tests for `apply_recency`**

Append to `tests/test_fusion.py`:

```python
class TestApplyRecency:
    def _scored(self, did: str, age_days: float, base_score: float = 1.0) -> ScoredCandidate:
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        ts = (now - timedelta(days=age_days)).timestamp()
        return ScoredCandidate(drawer_id=did, timestamp_unix=ts, score=base_score)

    def test_zero_age_gets_max_boost(self):
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        scored = [self._scored("fresh", age_days=0.0, base_score=1.0)]
        out = apply_recency(scored, now=now, tau_days=90.0, max_boost=1.5)
        # factor = 1 + (1.5 - 1) * exp(-0/90) = 1 + 0.5 * 1.0 = 1.5
        assert out[0].score == pytest.approx(1.5, rel=1e-6)

    def test_old_age_approaches_unboosted(self):
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        scored = [self._scored("ancient", age_days=10000.0, base_score=1.0)]
        out = apply_recency(scored, now=now, tau_days=90.0, max_boost=1.5)
        # factor = 1 + 0.5 * exp(-10000/90) ≈ 1.0
        assert out[0].score == pytest.approx(1.0, rel=1e-3)

    def test_reorders_when_recency_dominates(self):
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        # 'old' has higher base score but is ancient.
        # 'fresh' has lower base score but is brand new.
        # With max_boost large, 'fresh' should win.
        scored = [
            self._scored("old", age_days=10000.0, base_score=1.0),
            self._scored("fresh", age_days=0.0, base_score=0.8),
        ]
        out = apply_recency(scored, now=now, tau_days=90.0, max_boost=2.0)
        # old: 1.0 * (1 + 1.0 * exp(-10000/90)) ≈ 1.0
        # fresh: 0.8 * (1 + 1.0 * exp(0)) = 0.8 * 2.0 = 1.6
        assert out[0].drawer_id == "fresh"

    def test_max_boost_one_is_no_op(self):
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        scored = [self._scored("a", age_days=0.0, base_score=1.0)]
        out = apply_recency(scored, now=now, tau_days=90.0, max_boost=1.0)
        # factor = 1 + 0 * exp(0) = 1.0
        assert out[0].score == pytest.approx(1.0)

    def test_empty_input_returns_empty(self):
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        assert apply_recency([], now=now, tau_days=90.0, max_boost=1.5) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fusion.py::TestApplyRecency -v`
Expected: FAIL with `ImportError: cannot import name 'apply_recency'`.

- [ ] **Step 3: Implement `apply_recency`**

Append to `cognitive_castle/fusion.py`:

```python
import math
from datetime import datetime


def apply_recency(
    scored: list[ScoredCandidate],
    now: datetime,
    tau_days: float,
    max_boost: float,
) -> list[ScoredCandidate]:
    """Multiply each candidate's score by a recency factor and re-sort.

    factor(age) = 1 + (max_boost - 1) * exp(-age_days / tau_days)

    A drawer at age=0 receives a multiplier of `max_boost`. Ancient drawers
    asymptote to multiplier 1.0. Returned in descending score order; ties
    broken by drawer_id for determinism.

    Parameters
    ----------
    scored:
        Candidates with fused scores from `weighted_rrf`.
    now:
        Reference time for age calculation. Tests pass a fixed value;
        production passes `datetime.now(timezone.utc)`.
    tau_days:
        Decay timescale in days. Larger means recency boost decays slower.
    max_boost:
        Cap on the recency multiplier (max_boost == 1.0 disables the boost).
    """
    now_unix = now.timestamp()
    delta_boost = max_boost - 1.0
    boosted: list[ScoredCandidate] = []
    for c in scored:
        age_days = max(0.0, (now_unix - c.timestamp_unix) / 86400.0)
        factor = 1.0 + delta_boost * math.exp(-age_days / tau_days)
        boosted.append(
            ScoredCandidate(
                drawer_id=c.drawer_id,
                timestamp_unix=c.timestamp_unix,
                score=c.score * factor,
            )
        )
    boosted.sort(key=lambda s: (-s.score, s.drawer_id))
    return boosted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fusion.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/fusion.py tests/test_fusion.py
git commit -m "feat(fusion): add recency multiplier with configurable tau and max boost"
```

---

## Task 4: `reranker.py` — device-aware cross-encoder wrapper

**Files:**
- Create: `cognitive_castle/reranker.py`
- Test: `tests/test_reranker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_reranker.py`:

```python
"""Tests for the cross-encoder reranker wrapper."""
from unittest.mock import MagicMock, patch

import pytest

from cognitive_castle import reranker as rr


def test_resolve_device_auto_falls_back_to_cpu_when_no_cuda():
    with patch("cognitive_castle.reranker._cuda_available", return_value=False):
        assert rr._resolve_device("auto") == "cpu"


def test_resolve_device_auto_picks_cuda_when_available():
    with patch("cognitive_castle.reranker._cuda_available", return_value=True):
        assert rr._resolve_device("auto") == "cuda"


def test_resolve_device_explicit_cpu_passes_through():
    assert rr._resolve_device("cpu") == "cpu"


def test_resolve_device_explicit_cuda_passes_through():
    assert rr._resolve_device("cuda") == "cuda"


def test_pick_model_for_device():
    cfg = MagicMock()
    cfg.reranker_model_cpu = "model-cpu"
    cfg.reranker_model_gpu = "model-gpu"
    assert rr._pick_model_for_device("cpu", cfg) == "model-cpu"
    assert rr._pick_model_for_device("cuda", cfg) == "model-gpu"


def test_rerank_returns_scores_aligned_to_input():
    """Smoke test with a stub CrossEncoder so we don't load 290MB in CI."""
    fake_ce = MagicMock()
    fake_ce.predict.return_value = [0.9, 0.1, 0.5]
    with patch("cognitive_castle.reranker._get_reranker", return_value=fake_ce):
        scores = rr.rerank("query", ["doc_a", "doc_b", "doc_c"], device="cpu")
    assert scores == [0.9, 0.1, 0.5]
    # Confirm we passed (query, doc) pairs in order.
    call_args = fake_ce.predict.call_args
    pairs = call_args[0][0]
    assert pairs == [("query", "doc_a"), ("query", "doc_b"), ("query", "doc_c")]


def test_rerank_empty_candidates_returns_empty():
    scores = rr.rerank("query", [], device="cpu")
    assert scores == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reranker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cognitive_castle.reranker'`.

- [ ] **Step 3: Implement `reranker.py`**

Create `cognitive_castle/reranker.py`:

```python
"""reranker.py — Cross-encoder reranker wrapper.

Lazy-loaded singleton. Device-aware: picks the GPU model on CUDA, the smaller
CPU-friendly model otherwise. Public entry point `rerank` returns scores
aligned to the input candidate order.
"""
from __future__ import annotations

from typing import Optional

# Cached model instance, keyed by (model_name, device).
_model_cache: dict[tuple[str, str], object] = {}


def _cuda_available() -> bool:
    """Return True if a CUDA device is available. Isolated for test mocking."""
    try:
        import torch  # type: ignore
        return torch.cuda.is_available()
    except Exception:
        return False


def _resolve_device(device: str = "auto") -> str:
    if device == "auto":
        return "cuda" if _cuda_available() else "cpu"
    if device not in ("cuda", "cpu"):
        raise ValueError(f"device must be 'auto', 'cuda', or 'cpu'; got {device!r}")
    return device


def _pick_model_for_device(device: str, cfg) -> str:
    if device == "cuda":
        return cfg.reranker_model_gpu
    return cfg.reranker_model_cpu


def _get_reranker(model_name: str, device: str):
    """Lazy-load and cache the CrossEncoder for (model_name, device)."""
    key = (model_name, device)
    if key not in _model_cache:
        from sentence_transformers import CrossEncoder  # local import keeps test mocking simple
        _model_cache[key] = CrossEncoder(model_name, device=device)
    return _model_cache[key]


def rerank(
    query: str,
    candidates: list[str],
    device: str = "auto",
    cfg: Optional[object] = None,
) -> list[float]:
    """Score (query, candidate) pairs with the device-appropriate cross-encoder.

    Returns scores aligned to the input candidate order. Empty input returns
    an empty list without loading the model.
    """
    if not candidates:
        return []
    if cfg is None:
        from .config import CognitiveCastleConfig
        cfg = CognitiveCastleConfig()
    resolved_device = _resolve_device(device)
    model_name = _pick_model_for_device(resolved_device, cfg)
    model = _get_reranker(model_name, resolved_device)
    pairs = [(query, doc) for doc in candidates]
    raw_scores = model.predict(pairs)
    return [float(s) for s in raw_scores]


def clear_cache() -> None:
    """Drop cached model instances. Useful for tests."""
    _model_cache.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_reranker.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/reranker.py tests/test_reranker.py
git commit -m "feat(reranker): add device-aware cross-encoder wrapper with lazy load"
```

---

## Task 5: `entity_registry.lookup_in_text`

**Files:**
- Modify: `cognitive_castle/entity_registry.py`
- Test: `tests/test_entity_registry_lookup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_entity_registry_lookup.py`:

```python
"""Tests for EntityRegistry.lookup_in_text."""
import pytest

from cognitive_castle.entity_registry import EntityRegistry, EntityMatch


@pytest.fixture
def registry(tmp_path):
    reg = EntityRegistry(path=tmp_path / "entities.json")
    # Seed with some people and projects.
    reg.set_people({
        "Alice": {"birthdate": "1990-01-01"},
        "Bob": {"birthdate": "1985-05-12"},
    })
    reg.set_projects(["cognitive-castle", "deep-learning-course"])
    reg.save()
    return reg


def test_exact_match_person(registry):
    matches = registry.lookup_in_text("Did Alice say something interesting?")
    assert any(m.entity_id == "Alice" and m.matched_token == "Alice" for m in matches)


def test_exact_match_project(registry):
    matches = registry.lookup_in_text("Working on cognitive-castle today.")
    assert any(m.entity_id == "cognitive-castle" for m in matches)


def test_case_insensitive(registry):
    matches = registry.lookup_in_text("alice came over")
    assert any(m.entity_id == "Alice" for m in matches)


def test_fuzzy_match_within_distance(registry):
    matches = registry.lookup_in_text("Alise was here", max_edit_distance=1)
    # 'Alise' vs 'Alice' is edit distance 1.
    assert any(m.entity_id == "Alice" and m.edit_distance == 1 for m in matches)


def test_no_match_returns_empty(registry):
    assert registry.lookup_in_text("Random query about nothing.") == []


def test_strict_match_when_distance_zero(registry):
    matches = registry.lookup_in_text("Alise was here", max_edit_distance=0)
    # Edit distance 1 is not allowed when max_edit_distance=0.
    assert not any(m.entity_id == "Alice" for m in matches)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_entity_registry_lookup.py -v`
Expected: FAIL with `ImportError: cannot import name 'EntityMatch'` or `AttributeError: 'EntityRegistry' object has no attribute 'lookup_in_text'`.

- [ ] **Step 3: Implement `lookup_in_text` and `EntityMatch`**

In `cognitive_castle/entity_registry.py`:

At the top of the file (with other imports/dataclasses), add:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class EntityMatch:
    entity_id: str
    matched_token: str
    edit_distance: int
```

Inside the `EntityRegistry` class, add:

```python
def lookup_in_text(
    self,
    query: str,
    max_edit_distance: int = 1,
) -> list["EntityMatch"]:
    """Find entities mentioned in `query`.

    Tokenizes on whitespace + punctuation. Matches each token (and short
    n-grams up to length 3 for multi-word entities like "John Doe") against
    known people and projects. Allows edit-distance up to `max_edit_distance`
    using the standard Levenshtein metric.

    Returns matches deduplicated on entity_id (best edit_distance wins).
    """
    import re

    # Build the candidate dictionary: lowercase form -> canonical entity_id.
    candidates: dict[str, str] = {}
    for name in self.people.keys():
        candidates[name.lower()] = name
    for proj in self.projects:
        candidates[proj.lower()] = proj

    # Tokenize: split on whitespace + punctuation, drop empty.
    tokens = [t for t in re.split(r"[\s,.;:!?()\[\]{}\"']+", query) if t]
    if not tokens:
        return []

    # Generate token windows of length 1..3 for multi-word entities.
    windows: list[str] = []
    for n in (1, 2, 3):
        for i in range(len(tokens) - n + 1):
            windows.append(" ".join(tokens[i:i + n]))

    best_per_entity: dict[str, EntityMatch] = {}
    for window in windows:
        win_lc = window.lower()
        for cand_lc, canonical in candidates.items():
            d = _levenshtein(win_lc, cand_lc)
            if d <= max_edit_distance:
                existing = best_per_entity.get(canonical)
                if existing is None or d < existing.edit_distance:
                    best_per_entity[canonical] = EntityMatch(
                        entity_id=canonical,
                        matched_token=window,
                        edit_distance=d,
                    )

    return list(best_per_entity.values())
```

At module level (outside the class) add a small Levenshtein helper:

```python
def _levenshtein(a: str, b: str) -> int:
    """Standard iterative Levenshtein distance."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]
```

If `set_people` / `set_projects` don't exist on `EntityRegistry`, replace the test fixture's seeding code with whatever the existing API uses (the registry stores everything in `self._data`; check `update_people` / similar method names in entity_registry.py and adapt).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_entity_registry_lookup.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/benchmarks -q`
Expected: All previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/entity_registry.py tests/test_entity_registry_lookup.py
git commit -m "feat(entity-registry): add lookup_in_text with fuzzy matching for query-time KG hop"
```

---

## Task 6: `knowledge_graph.find_drawers_by_entities`

**Files:**
- Modify: `cognitive_castle/knowledge_graph.py`
- Test: `tests/test_kg_hop.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_kg_hop.py`:

```python
"""Tests for KnowledgeGraph.find_drawers_by_entities."""
import pytest

from cognitive_castle.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg_with_drawers(tmp_path):
    kg = KnowledgeGraph(path=tmp_path / "kg.sqlite")
    kg.add_entity("Alice", "person")
    kg.add_entity("Bob", "person")
    kg.add_entity("Carol", "person")
    # Drawer d1 mentions Alice; d2 mentions Alice + Bob; d3 mentions Bob; d4 mentions Carol only.
    kg.add_triple("Alice", "mentioned_in", "d1", source_drawer_id="d1", adapter_name="test")
    kg.add_triple("Alice", "mentioned_in", "d2", source_drawer_id="d2", adapter_name="test")
    kg.add_triple("Bob", "mentioned_in", "d2", source_drawer_id="d2", adapter_name="test")
    kg.add_triple("Bob", "mentioned_in", "d3", source_drawer_id="d3", adapter_name="test")
    kg.add_triple("Carol", "mentioned_in", "d4", source_drawer_id="d4", adapter_name="test")
    return kg


def test_single_entity(kg_with_drawers):
    out = kg_with_drawers.find_drawers_by_entities(["Alice"])
    assert set(out) == {"d1", "d2"}


def test_multiple_entities_returns_union(kg_with_drawers):
    out = kg_with_drawers.find_drawers_by_entities(["Alice", "Bob"])
    assert set(out) == {"d1", "d2", "d3"}


def test_match_count_ordering(kg_with_drawers):
    """Drawers tagged with more of the queried entities rank first."""
    out = kg_with_drawers.find_drawers_by_entities(["Alice", "Bob"])
    # d2 has both Alice + Bob; d1 only Alice; d3 only Bob.
    # d2 should appear first.
    assert out[0] == "d2"


def test_unknown_entity_returns_empty(kg_with_drawers):
    assert kg_with_drawers.find_drawers_by_entities(["Nobody"]) == []


def test_empty_input_returns_empty(kg_with_drawers):
    assert kg_with_drawers.find_drawers_by_entities([]) == []


def test_limit_caps_results(kg_with_drawers):
    out = kg_with_drawers.find_drawers_by_entities(["Alice"], limit=1)
    assert len(out) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_kg_hop.py -v`
Expected: FAIL with `AttributeError: 'KnowledgeGraph' object has no attribute 'find_drawers_by_entities'`.

- [ ] **Step 3: Implement `find_drawers_by_entities`**

In `cognitive_castle/knowledge_graph.py`, inside the `KnowledgeGraph` class, add:

```python
def find_drawers_by_entities(
    self,
    entity_names: list[str],
    limit: int = 50,
) -> list[str]:
    """Return drawer IDs tagged with any of the supplied entities.

    Drawers are ranked by the count of distinct queried entities they touch
    (descending), then by recency of triple insertion (descending), then by
    drawer_id for determinism.

    Parameters
    ----------
    entity_names:
        Canonical entity names. Internally resolved to entity IDs via the
        existing `_entity_id` hashing.
    limit:
        Maximum number of drawer IDs to return.
    """
    if not entity_names:
        return []
    entity_ids = [self._entity_id(name) for name in entity_names]
    placeholders = ",".join("?" * len(entity_ids))
    sql = f"""
        SELECT t.source_drawer_id,
               COUNT(DISTINCT t.subject) AS match_count,
               MAX(t.id) AS latest_triple_id
        FROM triples t
        WHERE (t.subject IN ({placeholders}) OR t.object IN ({placeholders}))
          AND t.source_drawer_id IS NOT NULL
        GROUP BY t.source_drawer_id
        ORDER BY match_count DESC, latest_triple_id DESC, t.source_drawer_id ASC
        LIMIT ?
    """
    with self._connect() as conn:
        rows = conn.execute(sql, entity_ids + entity_ids + [limit]).fetchall()
    return [r[0] for r in rows]
```

If the `triples` table column for the auto-increment ID is named differently (the spec assumed `id`), check the table schema in `knowledge_graph.py`'s CREATE TABLE statement (around line 86) and adapt the column reference. If there's a `created_at` or `valid_from` column, prefer that over `id` for recency ordering — `MAX(t.created_at)` is semantically cleaner.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_kg_hop.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/benchmarks -q`
Expected: All previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/knowledge_graph.py tests/test_kg_hop.py
git commit -m "feat(kg): add find_drawers_by_entities for query-time KG-hop retrieval"
```

---

## Task 7: Make `embedding.py` config-driven (default unchanged)

**Files:**
- Modify: `cognitive_castle/embedding.py`
- Test: `tests/test_embedding.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_embedding.py`:

```python
def test_embedding_uses_config_default_model_when_unspecified():
    """Without overrides, the embedder reads model name from CognitiveCastleConfig."""
    from cognitive_castle.config import CognitiveCastleConfig
    from cognitive_castle.embedding import _resolve_model_name

    cfg = CognitiveCastleConfig()
    assert _resolve_model_name(cfg) == cfg.embedder_model
    # And the default is still all-MiniLM at this point in the rollout.
    assert _resolve_model_name(cfg) == "all-MiniLM-L6-v2"


def test_embedding_respects_config_override():
    from cognitive_castle.config import CognitiveCastleConfig
    from cognitive_castle.embedding import _resolve_model_name

    cfg = CognitiveCastleConfig()
    cfg.embedder_model = "BAAI/bge-m3"
    assert _resolve_model_name(cfg) == "BAAI/bge-m3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embedding.py::test_embedding_uses_config_default_model_when_unspecified -v`
Expected: FAIL with `ImportError: cannot import name '_resolve_model_name'`.

- [ ] **Step 3: Refactor `embedding.py` to read from config**

Edit `cognitive_castle/embedding.py`. Replace the hardcoded `_MODEL_NAME = "all-MiniLM-L6-v2"` with a config-driven helper. Keep the cached-singleton pattern (the model is expensive to load).

```python
# Replace this:
# _MODEL_NAME = "all-MiniLM-L6-v2"

# With this:
def _resolve_model_name(cfg=None) -> str:
    if cfg is None:
        from .config import CognitiveCastleConfig
        cfg = CognitiveCastleConfig()
    return cfg.embedder_model
```

Update `_get_model` (around line 26) to use `_resolve_model_name`:

```python
_model_cache: dict[str, object] = {}


def _get_model(device: str = "auto", cfg=None):
    name = _resolve_model_name(cfg)
    resolved = _resolve_device(device)
    cache_key = f"{name}@{resolved}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(name, device=resolved)
    _model_cache[cache_key] = model
    return model
```

Update `embed_texts` and any other public function that previously assumed a single global model to use the cache key approach. The test fixture for embedding tests should not be broken because the default model name is still all-MiniLM.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embedding.py -v`
Expected: All tests PASS, including pre-existing tests (default behavior unchanged).

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/benchmarks -q`
Expected: All previously-passing tests still pass. Defaults preserved current behavior.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/embedding.py tests/test_embedding.py
git commit -m "refactor(embedding): make model name config-driven (default still all-MiniLM)"
```

---

## Task 8: Make LanceDB `EMBED_DIM` config-driven

**Files:**
- Modify: `cognitive_castle/backends/lancedb_backend.py`
- Test: `tests/test_backends.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backends.py`:

```python
def test_lancedb_schema_uses_config_dim(tmp_path):
    """Schema dim is sourced from config.embedder_dim, not a hardcoded constant."""
    from cognitive_castle.backends.lancedb_backend import _build_schema
    from cognitive_castle.config import CognitiveCastleConfig

    cfg = CognitiveCastleConfig()
    cfg.embedder_dim = 384
    schema_384 = _build_schema(cfg)
    assert any(
        f.name == "vector" and f.type.list_size == 384
        for f in schema_384
    )

    cfg.embedder_dim = 1024
    schema_1024 = _build_schema(cfg)
    assert any(
        f.name == "vector" and f.type.list_size == 1024
        for f in schema_1024
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_backends.py::test_lancedb_schema_uses_config_dim -v`
Expected: FAIL with `ImportError: cannot import name '_build_schema'`.

- [ ] **Step 3: Refactor `lancedb_backend.py`**

Edit `cognitive_castle/backends/lancedb_backend.py`. Find the module-level `EMBED_DIM = 384` (line 51). Replace with a function that builds the schema from config:

```python
import pyarrow as pa


def _build_schema(cfg) -> pa.Schema:
    """Build the LanceDB drawer-table schema using the configured dim."""
    dim = cfg.embedder_dim
    return pa.schema([
        # Keep all existing fields verbatim. Only the vector field's dim is dynamic.
        pa.field("id", pa.string()),
        pa.field("document", pa.string()),
        # ... (preserve all existing non-vector fields exactly as they were before)
        pa.field("vector", pa.list_(pa.float32(), dim)),
    ])
```

Replace any references in the same file that previously used the constant `EMBED_DIM` (e.g., the line `"vector": embedding if embedding is not None else [0.0] * EMBED_DIM,` at line 197) with a config lookup. The cleanest pattern is to capture `dim` once in `__init__` of the backend class:

```python
class LanceDBBackend:
    def __init__(self, ..., cfg=None):
        if cfg is None:
            from ..config import CognitiveCastleConfig
            cfg = CognitiveCastleConfig()
        self._cfg = cfg
        self._dim = cfg.embedder_dim
        self._schema = _build_schema(cfg)
        # ... rest of existing __init__ logic
```

Then anywhere in the file that referenced `EMBED_DIM`, change to `self._dim`.

Keep a backward-compat shim if any external code imports `EMBED_DIM` directly:

```python
# Module-level alias for backward compat. Read at import time from default config.
def _legacy_embed_dim() -> int:
    from ..config import CognitiveCastleConfig
    return CognitiveCastleConfig().embedder_dim


EMBED_DIM = _legacy_embed_dim()  # noqa: E305
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backends.py -v`
Expected: All tests pass, including the new one and pre-existing.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/benchmarks -q`
Expected: All passing. Default config still says 384, so no behavior change.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/backends/lancedb_backend.py tests/test_backends.py
git commit -m "refactor(lancedb): make EMBED_DIM config-driven (default still 384)"
```

---

## Task 9: Add Tantivy FTS index in LanceDB backend

**Files:**
- Modify: `cognitive_castle/backends/lancedb_backend.py`
- Test: `tests/test_backends.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backends.py`:

```python
def test_fts_index_is_created_alongside_vector(tmp_path):
    """When a backend creates a new collection, an FTS index on the document text is built."""
    from cognitive_castle.backends.lancedb_backend import LanceDBBackend, PalaceRef

    backend = LanceDBBackend()
    palace = PalaceRef(path=str(tmp_path / "palace"), name="test")
    col = backend.get_or_create_collection(palace, "drawers")
    # Add a row so we have something to search.
    col.add(
        documents=["the quick brown fox jumps over the lazy dog"],
        ids=["d1"],
        metadatas=[{"wing": "test", "room": "test", "ts": "2026-05-10"}],
    )
    # FTS should find the row by a keyword in the document.
    results = col.fts_search("brown fox", n_results=5)
    assert len(results) >= 1
    assert results[0]["id"] == "d1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_backends.py::test_fts_index_is_created_alongside_vector -v`
Expected: FAIL — likely with `AttributeError: ... has no attribute 'fts_search'` or because the FTS index wasn't created.

- [ ] **Step 3: Add FTS index creation + search method**

In `cognitive_castle/backends/lancedb_backend.py`, inside the collection class (the class returned by `get_or_create_collection`; in the file, look for a class with `add`, `upsert`, etc. methods), add an `fts_search` method and create the FTS index when the collection is created:

```python
class LanceDBCollection:
    def __init__(self, table, ...):
        # existing init code
        self._ensure_fts_index()

    def _ensure_fts_index(self) -> None:
        """Create a Tantivy-backed FTS index on the document column if missing."""
        try:
            # LanceDB API: create FTS index on a column.
            # Idempotent: skip if already created.
            existing = self._table.list_indices() if hasattr(self._table, "list_indices") else []
            already_has_fts = any(
                getattr(idx, "column_name", None) == "document"
                and getattr(idx, "index_type", "").lower() in ("fts", "inverted")
                for idx in existing
            )
            if not already_has_fts:
                self._table.create_fts_index("document", replace=False)
        except Exception:
            # Older LanceDB versions: create_fts_index may already idempotently no-op,
            # or the API may differ. Catch and continue — verify in impl-time
            # if FTS is unavailable on the user's pinned version.
            pass

    def fts_search(self, query: str, n_results: int = 100) -> list[dict]:
        """Sparse search via Tantivy FTS. Returns rows ordered by relevance score.

        Each row is a dict with keys: id, document, score, plus metadata fields.
        """
        try:
            results = (
                self._table.search(query, query_type="fts")
                .limit(n_results)
                .to_list()
            )
        except Exception:
            # If FTS query API differs in this LanceDB version, surface a clear error.
            raise NotImplementedError(
                f"LanceDB FTS query failed; verify version supports query_type='fts'. "
                f"Underlying query: {query!r}"
            )
        return results
```

Verify the LanceDB API names against the installed version. If `query_type="fts"` isn't the correct kwarg for the pinned LanceDB, consult `python -c "import lancedb; help(lancedb.LanceTable.search)"` or current LanceDB docs and adjust.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_backends.py::test_fts_index_is_created_alongside_vector -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/benchmarks -q`
Expected: All passing.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/backends/lancedb_backend.py tests/test_backends.py
git commit -m "feat(lancedb): add Tantivy FTS index + fts_search method on collections"
```

---

## Task 10: New 3-stage pipeline behind a config flag

**Files:**
- Modify: `cognitive_castle/searcher.py`
- Test: `tests/test_retrieval_pipeline.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_retrieval_pipeline.py`:

```python
"""End-to-end test of the new 3-stage retrieval pipeline."""
import time

import pytest

from cognitive_castle.searcher import search_memories


def _seed(palace_path, drawers: list[tuple[str, str, dict]]):
    """drawers is a list of (id, document, metadata) tuples."""
    from cognitive_castle.backends.lancedb_backend import LanceDBBackend, PalaceRef
    backend = LanceDBBackend()
    palace = PalaceRef(path=palace_path, name="test")
    col = backend.get_or_create_collection(palace, "drawers")
    for did, doc, md in drawers:
        col.add(documents=[doc], ids=[did], metadatas=[md])


def test_pipeline_returns_results_when_flag_enabled(tmp_path, monkeypatch):
    """With use_new_retrieval_pipeline=True, searcher routes to the new pipeline
    and returns results."""
    monkeypatch.setattr(
        "cognitive_castle.config.CognitiveCastleConfig.use_new_retrieval_pipeline",
        True,
        raising=False,
    )
    palace = str(tmp_path / "palace")
    _seed(palace, [
        ("d1", "JWT authentication for the API", {"wing": "auth", "room": "2026", "ts": str(int(time.time()))}),
        ("d2", "the quick brown fox jumps over the lazy dog", {"wing": "misc", "room": "2026", "ts": str(int(time.time()))}),
    ])
    results = search_memories("authentication", palace, n_results=5)
    assert len(results) >= 1
    assert results[0]["id"] == "d1"


def test_pipeline_disabled_falls_back_to_old_path(tmp_path, monkeypatch):
    """With use_new_retrieval_pipeline=False (default), the old code path runs."""
    monkeypatch.setattr(
        "cognitive_castle.config.CognitiveCastleConfig.use_new_retrieval_pipeline",
        False,
        raising=False,
    )
    palace = str(tmp_path / "palace")
    _seed(palace, [("d1", "test document", {"wing": "x", "room": "y", "ts": "1700000000"})])
    # Just confirm the call doesn't error and returns something searchable.
    results = search_memories("test", palace, n_results=5)
    assert isinstance(results, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_retrieval_pipeline.py -v`
Expected: FAIL — likely the flag is ignored, results don't have an `"id"` key in the new format, or the pipeline path doesn't exist.

- [ ] **Step 3: Add the pipeline path to `searcher.py`**

In `cognitive_castle/searcher.py`, add at the top (or as a private helper):

```python
def _new_pipeline_search(
    query: str,
    palace_path: str,
    wing: str | None,
    room: str | None,
    n_results: int,
    cfg,
    is_hook_call: bool = False,
) -> list[dict]:
    """3-stage retrieval pipeline: parallel recall → fusion → cross-encoder rerank."""
    from datetime import datetime, timezone
    from .backends.lancedb_backend import LanceDBBackend, PalaceRef
    from .knowledge_graph import KnowledgeGraph
    from .entity_registry import EntityRegistry
    from .embedding import embed_texts
    from .fusion import CandidateRef, weighted_rrf, apply_recency
    from .reranker import rerank
    from pathlib import Path

    backend = LanceDBBackend(cfg=cfg)
    palace_ref = PalaceRef(path=palace_path, name=Path(palace_path).name)
    col = backend.get_or_create_collection(palace_ref, "drawers")

    # ── Stage 1: parallel recall ──
    # 1a. Dense.
    [query_vec] = embed_texts([query])
    dense_rows = col.vector_search(query_vec, n_results=100, where=_where_filter(wing, room))

    # 1b. Sparse via FTS.
    sparse_rows = col.fts_search(query, n_results=100)

    # 1c. KG-hop.
    reg = EntityRegistry(path=Path(palace_path) / "entities.json")
    matches = reg.lookup_in_text(query)
    kg = KnowledgeGraph(path=Path(palace_path) / "kg.sqlite")
    kg_drawer_ids = (
        kg.find_drawers_by_entities([m.entity_id for m in matches], limit=cfg.kg_hop_top_n)
        if matches else []
    )
    # Materialize KG candidates into CandidateRefs by reading their timestamps from the table.
    kg_rows = col.get_by_ids(kg_drawer_ids) if kg_drawer_ids else []

    def _to_refs(rows):
        return [
            CandidateRef(drawer_id=r["id"], timestamp_unix=float(r.get("ts", 0)))
            for r in rows
        ]

    rank_lists = {
        "dense": _to_refs(dense_rows),
        "sparse": _to_refs(sparse_rows),
        "kg": _to_refs(kg_rows),
    }
    weights = {"dense": cfg.weight_dense, "sparse": cfg.weight_sparse, "kg": cfg.weight_kg}

    # ── Stage 2: fusion + recency ──
    fused = weighted_rrf(rank_lists, weights, k_rrf=cfg.k_rrf)
    fused = apply_recency(
        fused,
        now=datetime.now(timezone.utc),
        tau_days=cfg.recency_tau_days,
        max_boost=cfg.recency_max_boost,
    )

    # ── Stage 3: cross-encoder rerank top-K ──
    k_cap = cfg.reranker_k_hook if is_hook_call else cfg.reranker_k_interactive
    top_k_ids = [s.drawer_id for s in fused[:k_cap]]
    if not top_k_ids:
        return []
    top_k_rows = col.get_by_ids(top_k_ids)
    rerank_scores = rerank(query, [r["document"] for r in top_k_rows], cfg=cfg)
    reranked = sorted(zip(rerank_scores, top_k_rows), key=lambda x: -x[0])

    # Return n_results in the existing dict shape.
    return [
        {"id": r["id"], "document": r["document"], "score": float(s), **r.get("metadata", {})}
        for s, r in reranked[:n_results]
    ]


def _where_filter(wing, room):
    # Build a LanceDB where filter; mirrors existing build_where_filter logic.
    from .searcher import build_where_filter
    return build_where_filter(wing=wing, room=room)
```

Then modify `search_memories` (and `search`) to dispatch based on the flag:

```python
def search_memories(query, palace_path, wing=None, room=None, n_results=5, is_hook_call=False):
    from .config import CognitiveCastleConfig
    cfg = CognitiveCastleConfig()
    if cfg.use_new_retrieval_pipeline:
        return _new_pipeline_search(query, palace_path, wing, room, n_results, cfg, is_hook_call=is_hook_call)
    # ── existing code path unchanged ──
    # ... rest of original search_memories body
```

If `vector_search` and `get_by_ids` aren't currently public methods on the LanceDB collection class, add thin wrappers in `lancedb_backend.py`:

```python
def vector_search(self, vec, n_results=100, where=None):
    q = self._table.search(vec)
    if where:
        q = q.where(where)
    return q.limit(n_results).to_list()


def get_by_ids(self, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    quoted = ", ".join(f"'{i}'" for i in ids)
    return self._table.search(None).where(f"id IN ({quoted})").limit(len(ids)).to_list()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_retrieval_pipeline.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/benchmarks -q`
Expected: All passing. Default flag is False, so old-pipeline tests stay green.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/searcher.py cognitive_castle/backends/lancedb_backend.py tests/test_retrieval_pipeline.py
git commit -m "feat(searcher): add 3-stage pipeline (dense+sparse+KG → RRF+recency → rerank), gated by config flag"
```

---

## Task 11: `castle reindex` CLI command

**Files:**
- Modify: `cognitive_castle/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_reindex_command_is_registered():
    """`castle reindex` is a discoverable subcommand."""
    from cognitive_castle.cli import main
    import sys

    # Invoking with --help should not error and should mention 'reindex'.
    captured = []
    def fake_help(*a, **kw):
        captured.append(kw.get("help", ""))
    # Easiest: parse the argparse help and look for "reindex".
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    sys_argv_save = sys.argv
    sys.argv = ["castle", "--help"]
    try:
        with redirect_stdout(buf):
            try:
                main()
            except SystemExit:
                pass
    finally:
        sys.argv = sys_argv_save
    assert "reindex" in buf.getvalue()


def test_reindex_creates_new_palace_dir(tmp_path, monkeypatch):
    """`castle reindex --palace <path> --sources <dir>` produces a <palace>.new/ directory."""
    from cognitive_castle.cli import cmd_reindex
    from argparse import Namespace

    palace = tmp_path / "palace"
    palace.mkdir()
    (palace / "marker").write_text("old palace marker")
    sources = tmp_path / "sources"
    sources.mkdir()
    # Drop a source file so the mine has something to walk.
    (sources / "note.md").write_text("Hello world.")

    args = Namespace(palace=str(palace), sources=[str(sources)], yes=True)
    cmd_reindex(args)

    # After reindex, expect a backup of the old + a new primary.
    assert (palace.parent / f"{palace.name}.legacy").exists()
    assert palace.exists()
    # The new palace should NOT have the old marker (it's a fresh build).
    assert not (palace / "marker").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py::test_reindex_command_is_registered tests/test_cli.py::test_reindex_creates_new_palace_dir -v`
Expected: FAIL with `ImportError: cannot import name 'cmd_reindex'`.

- [ ] **Step 3: Implement `cmd_reindex` and register the subcommand**

In `cognitive_castle/cli.py`, find the `main()` function and the subparser registrations (the `sub.add_parser(...)` block, around line 964 onward). Add:

```python
def cmd_reindex(args) -> None:
    """Rebuild the palace from sources at the current embedder identity.

    Strategy:
    1. Move existing palace to <palace>.legacy/.
    2. Create a fresh palace at <palace>/.
    3. Walk every directory in args.sources and run the existing mine pipeline
       to populate the new palace.
    4. On success, leave <palace>.legacy/ in place for user verification.
    """
    import shutil
    from pathlib import Path

    palace = Path(args.palace)
    legacy = palace.with_name(palace.name + ".legacy")

    if legacy.exists():
        if not args.yes:
            print(
                f"Refusing to overwrite existing legacy backup at {legacy}. "
                f"Either delete it or pass --yes."
            )
            return
        shutil.rmtree(legacy)

    if palace.exists():
        shutil.move(str(palace), str(legacy))
        print(f"Moved existing palace to {legacy}")

    palace.mkdir(parents=True, exist_ok=True)

    # Run the mine pipeline on every source directory.
    from .miner import mine_path
    for source_dir in args.sources or []:
        print(f"Mining {source_dir} into fresh palace at {palace} ...")
        mine_path(source_dir, palace_path=str(palace))

    print(
        f"Reindex complete. Verify the new palace, then delete {legacy} when satisfied:\n"
        f"    rm -rf {legacy}"
    )
```

Register the subcommand by adding (in `main()`, near the other `sub.add_parser` calls):

```python
p_reindex = sub.add_parser(
    "reindex",
    help="Rebuild the palace from sources (e.g. after an embedder upgrade)",
)
p_reindex.add_argument("--palace", required=True, help="Path to the palace directory.")
p_reindex.add_argument(
    "--sources",
    nargs="+",
    required=True,
    help="One or more source directories to mine into the new palace.",
)
p_reindex.add_argument(
    "--yes",
    action="store_true",
    help="Overwrite an existing <palace>.legacy backup without prompting.",
)
```

In the dispatcher block at the end of `main()` (search for `if args.command == "init":` etc.), add:

```python
elif args.command == "reindex":
    cmd_reindex(args)
```

If `mine_path` doesn't exist as a public function, use whatever the module-level mining entrypoint is (e.g., import the same function called by `cmd_mine`). The point is: reuse the existing mine pipeline, don't reimplement.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py::test_reindex_command_is_registered tests/test_cli.py::test_reindex_creates_new_palace_dir -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/benchmarks -q`
Expected: All passing.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'castle reindex' command for rebuild-from-sources after embedder change"
```

---

## Task 12: Verify `castle reindex` works on a real fixture palace (manual smoke)

**Files:** none (manual verification)

This is a manual smoke step before flipping defaults. If reindex is broken, every user session breaks at cutover.

- [ ] **Step 1: Build a tiny fixture palace using current defaults**

```bash
mkdir -p /tmp/castle-smoke/sources
echo "Test note about authentication and JWTs." > /tmp/castle-smoke/sources/note.md
echo "Another note about FastAPI deployment." > /tmp/castle-smoke/sources/note2.md
castle init --palace /tmp/castle-smoke/palace --yes
castle mine /tmp/castle-smoke/sources --palace /tmp/castle-smoke/palace
```

Confirm:
```bash
castle status --palace /tmp/castle-smoke/palace
```

Expected: shows ≥ 2 drawers.

- [ ] **Step 2: Run reindex**

```bash
castle reindex --palace /tmp/castle-smoke/palace --sources /tmp/castle-smoke/sources --yes
```

Expected:
- A `/tmp/castle-smoke/palace.legacy` directory exists.
- A fresh `/tmp/castle-smoke/palace` exists with re-mined content.
- `castle status --palace /tmp/castle-smoke/palace` shows the same drawer count.

- [ ] **Step 3: Confirm search still works after reindex**

```bash
castle search "authentication" --palace /tmp/castle-smoke/palace
```

Expected: returns the auth note as the top result.

- [ ] **Step 4: Cleanup**

```bash
rm -rf /tmp/castle-smoke
```

(No commit. This is verification of Task 11's work, not new code.)

---

## Task 13: Cutover — flip defaults to bge-m3, 1024-dim, new pipeline

This is the moment the embedder schema changes. Existing palaces become incompatible. The reindex command from Task 11 + 12 is the user's escape hatch.

**Files:**
- Modify: `cognitive_castle/config.py`
- Modify: tests that previously hardcoded `384`

- [ ] **Step 1: Update config defaults**

Edit `cognitive_castle/config.py`:

```python
embedder_model: str = "BAAI/bge-m3"          # was "all-MiniLM-L6-v2"
embedder_dim: int = 1024                     # was 384
use_new_retrieval_pipeline: bool = True      # was False
```

Bump the embedder identity hash so old palaces fail loudly (existing infrastructure for embedder-mismatch detection lives in `backends/__init__.py` per the `EmbedderIdentityMismatchError` export).

```python
embedder_identity: str = "bge-m3-1024-v1"
```

- [ ] **Step 2: Update the prior config-default test**

Edit the test added in Task 1:

```python
def test_config_has_retrieval_upgrade_keys():
    from cognitive_castle.config import CognitiveCastleConfig
    cfg = CognitiveCastleConfig()
    # Cutover: defaults are now the new stack.
    assert cfg.embedder_model == "BAAI/bge-m3"
    assert cfg.embedder_dim == 1024
    assert cfg.use_new_retrieval_pipeline is True
    # ... rest unchanged
```

Also update `test_embedding_uses_config_default_model_when_unspecified` from Task 7:

```python
assert _resolve_model_name(cfg) == "BAAI/bge-m3"
```

- [ ] **Step 3: Find and update tests that hardcoded 384 or `all-MiniLM-L6-v2`**

Run:

```bash
grep -rn "all-MiniLM\|EMBED_DIM\|384" tests/
```

For each match, decide:
- If the test was checking embedder identity → update to bge-m3 / 1024 expectation.
- If it was a fixture seeding pre-computed 384-dim vectors → update fixture to 1024-dim, or refactor to embed via `embed_texts` (model-agnostic).
- If it was specifically about MiniLM behavior → either delete or refactor.

Do this fix-up in commits per file group (e.g., one commit per directory of fixtures) so each commit is reviewable.

- [ ] **Step 4: Reindex any test palaces under `tests/`**

If there are committed test fixture palaces (LanceDB tables) under `tests/`, regenerate them at 1024-dim. If they're rebuilt by fixtures at test-run time (most likely the case given the `palace_path` / `seeded_collection` fixtures in `conftest.py`), no action needed.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/benchmarks -q`
Expected: All passing. Some may need re-runs as model downloads cache. Tests that hit real embedding now download bge-m3 (~570MB) on first run.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/config.py tests/
git commit -m "feat: flip defaults to bge-m3 + 1024-dim + new pipeline (BREAKING: requires reindex)"
```

The commit message must include `BREAKING:` so users see why their palace stopped working until they run `castle reindex`.

---

## Task 14: Delete legacy BM25 code from `searcher.py`

The new pipeline is the default. The `_bm25_*` and `_hybrid_rank` functions in `searcher.py` are now dead code.

**Files:**
- Modify: `cognitive_castle/searcher.py`
- Modify or delete: `tests/test_hybrid_search.py`, `tests/test_hybrid_candidate_union.py`

- [ ] **Step 1: Delete the legacy functions**

In `cognitive_castle/searcher.py`, delete:
- `_bm25_scores` (around line 62)
- `_hybrid_rank` (around line 121)
- `_bm25_only_via_lancedb` (around line 380)
- `_merge_bm25_union_candidates` (around line 506)

Also delete the now-unused dispatch in `search_memories`/`search` that called the old pipeline. Both functions now unconditionally route to `_new_pipeline_search`.

- [ ] **Step 2: Delete or update tests for the removed code**

Run:

```bash
pytest tests/test_hybrid_search.py tests/test_hybrid_candidate_union.py -v --collect-only
```

For each test that referenced the removed functions:
- If the test concept still applies under the new pipeline (e.g., "candidates from multiple signals are merged"), rewrite the test against the new pipeline.
- If the test concept is gone (e.g., "BM25 IDF computation is correct"), delete the test.

When in doubt, delete: the new pipeline has its own integration coverage (`test_retrieval_pipeline.py`).

- [ ] **Step 3: Confirm no stragglers reference the removed names**

```bash
grep -rn "_bm25_scores\|_hybrid_rank\|_bm25_only_via_lancedb\|_merge_bm25_union_candidates" .
```

Expected: zero matches outside CHANGELOG / removed-tests.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/benchmarks -q`
Expected: All passing.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/searcher.py tests/
git commit -m "refactor(searcher): delete legacy BM25 implementation (replaced by Tantivy FTS in new pipeline)"
```

---

## Task 15: Benchmark-driven fusion-weight tuning (load-bearing)

Per the spec, default fusion weights are placeholders. This task makes them load-bearing.

**Files:**
- Modify: `cognitive_castle/config.py` (final commit only, after tuning)

- [ ] **Step 1: Establish baseline**

Check out the parent commit (before Task 13 cutover) and run the recall benchmark to capture the OLD-stack baseline:

```bash
git stash
git checkout HEAD~$(git rev-list --count HEAD ^a19dfc3)  # rough — check exact ref
pytest tests/benchmarks/test_recall_threshold.py tests/benchmarks/test_search_bench.py -v --tb=short
```

Save the Recall@10 / MRR numbers. (If those benchmarks measure something else, capture whatever metric they expose — the goal is "compare new stack to old stack on the same evaluation".)

```bash
git checkout develop
git stash pop || true
```

- [ ] **Step 2: Run the new stack with default weights**

```bash
pytest tests/benchmarks/test_recall_threshold.py tests/benchmarks/test_search_bench.py -v --tb=short
```

Capture metrics. Compare to baseline. If new ≥ old + 5%, the defaults are good as-is — skip ahead to Step 5. If not, continue.

- [ ] **Step 3: Sweep weight configurations**

Try 5 configurations by editing `config.py` defaults and re-running benchmarks:

| Sweep | weight_dense | weight_sparse | weight_kg | recency_max_boost |
|---|---|---|---|---|
| A (baseline) | 1.0 | 1.0 | 0.5 | 1.5 |
| B | 1.5 | 1.0 | 0.5 | 1.5 |
| C | 1.0 | 1.5 | 0.5 | 1.5 |
| D | 1.0 | 1.0 | 1.0 | 1.5 |
| E | 1.0 | 1.0 | 0.5 | 1.0 |

For each: edit config defaults, run benchmarks, record metrics in a scratch markdown file (e.g., `docs/superpowers/notes/2026-05-10-tuning-results.md`). Don't commit until the winner is chosen.

- [ ] **Step 4: Pick the winner**

Choose the configuration with the best Recall@10 (primary) and MRR (tiebreaker). If two are within 1% of each other, prefer the one closer to the baseline (less overfit).

- [ ] **Step 5: Commit chosen defaults**

Edit `cognitive_castle/config.py` to the chosen values. Add a comment line above the config keys:

```python
# Tuned 2026-05-10 on tests/benchmarks/test_recall_threshold.py and
# tests/benchmarks/test_search_bench.py. Re-tune if the embedder, reranker,
# or KG-hop semantics change.
weight_dense: float = ...    # winning value
weight_sparse: float = ...   # winning value
weight_kg: float = ...       # winning value
recency_max_boost: float = ...  # winning value
```

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/config.py
# Optionally also commit the tuning notes:
git add docs/superpowers/notes/2026-05-10-tuning-results.md
git commit -m "chore(retrieval): tune fusion weights against recall benchmark suite"
```

---

## Task 16: Final acceptance — manual smoke + Recall@10 ≥ baseline + 5%

**Files:** none (verification step)

- [ ] **Step 1: Confirm benchmark target met**

Re-run the recall benchmark with the tuned config. Confirm:
- Recall@10 (or whatever the equivalent metric is on `test_recall_threshold.py`) ≥ baseline + 5%.
- If not, the upgrade hasn't earned its complexity. Investigate: is the cross-encoder hurting? Are KG hits poisoning fusion? Roll back individual signals (e.g., set `weight_kg = 0`) and re-test until you find the regression source. Stop and ask for help if stuck.

- [ ] **Step 2: Latency smoke**

Build a small palace via `castle init` + `castle mine`. Run a few `castle search` queries. Time each:

```bash
time castle search "authentication" --palace /tmp/castle-smoke/palace
```

Confirm wall-clock time is under ~1.2s on your laptop.

- [ ] **Step 3: Hook latency smoke**

Hooks are harder to time directly. Run the existing hook tests with the new pipeline:

```bash
pytest tests/test_hooks_cli.py tests/test_save_hook_mines.py -v
```

If those tests now exercise retrieval and pass within their normal time, the hook-recall path is fine. If they regress, the hook-call path may be skipping the K-cap; verify `is_hook_call=True` is plumbed through.

- [ ] **Step 4: Multilingual smoke**

Add a Slovak or Czech note to a test palace:

```bash
echo "Toto je poznámka o overovaní." > /tmp/castle-smoke/sources/sk.md
castle reindex --palace /tmp/castle-smoke/palace --sources /tmp/castle-smoke/sources --yes
castle search "overovanie" --palace /tmp/castle-smoke/palace
```

Confirm the Slovak note surfaces. If it doesn't, the embedder's prompt-prefix usage may need adjustment (Open Question #2 in the spec).

- [ ] **Step 5: Final commit**

If anything was tweaked during this task (e.g., a small bugfix), commit it. Otherwise, no commit. Tag the final state if releasing:

```bash
git tag retrieval-upgrade-shipped
```

---

## Self-Review

**Spec coverage:**
- bge-m3 embedder swap → Tasks 7, 13.
- Tantivy FTS replaces BM25 → Tasks 9, 14.
- Cross-encoder reranker (device-aware, K-capped) → Task 4 (wrapper) + Task 10 (integrated). K caps in `config.py` from Task 1.
- KG-hop signal → Task 5 (entity registry) + Task 6 (KG query) + Task 10 (integration).
- Weighted RRF + recency → Tasks 2, 3, 10.
- Migration via `castle reindex` → Task 11 + Task 12 (smoke).
- Benchmark-driven tuning → Task 15.
- Acceptance: Recall@10 ≥ baseline + 5% → Task 16 Step 1.
- Tests stay green throughout → Sequencing strategy at top; every task ends with full-suite run before commit.

**Placeholder scan:** No "TBD"/"TODO"/"implement later". Every code step shows actual code. Test code is concrete, not "test the function." Tuning task does have value-placeholders (`weight_dense: float = ...`) inside Step 5 of Task 15 but the surrounding mechanism is explicit and the task's purpose is to *fill in those values* by measurement — that's a feature, not a placeholder bug.

**Type consistency:** `CandidateRef` and `ScoredCandidate` defined in Task 2 are reused identically in Task 10. `EntityMatch` defined in Task 5 is reused in Task 10. Method names: `find_drawers_by_entities` (Task 6) used unchanged in Task 10. `lookup_in_text` (Task 5) used unchanged in Task 10. `_resolve_model_name` (Task 7) is internal to embedding.py only — no external use. `_build_schema` (Task 8) is internal to lancedb_backend.py — referenced only in test.

**Known gaps requiring impl-time judgment** (called out in the relevant tasks, not silently elided):
- LanceDB FTS exact API surface (Task 9 Step 3) — adapt if `query_type="fts"` differs in the pinned version.
- Triples table column name for recency ordering in KG (Task 6 Step 3) — adapt to actual schema.
- `EntityRegistry`'s seeding API in test fixtures (Task 5 Step 3) — adapt to actual method names.
- bge-m3 prompt prefix (spec Open Question #2) — verify in Task 16 multilingual smoke; if Slovak note doesn't surface, this is the likely cause and needs a follow-up commit.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-10-sota-retrieval-upgrade.md`.
