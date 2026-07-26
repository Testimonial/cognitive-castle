# Info-Aware Filing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every drawer carries a `novelty` metadata score (prior-only nn_novelty); retrieval can demote — never drop — low-novelty near-duplicates, gated OFF by default behind a LongMemEval benchmark.

**Architecture:** New `novelty_tagger.py` owns the scoring math (one implementation, `info_score.py` delegates to it). The miner embeds batches explicitly, computes novelty per chunk, and passes vectors through to upsert (one forward pass, no double-embedding). Fusion gains a pure `apply_info_weight` applied after `apply_recency`, before the top-K cut; novelty threads `_to_refs → CandidateRef → weighted_rrf → ScoredCandidate → apply_recency → apply_info_weight`. CLI surfaces: `search --info-weight`, `repair --backfill-novelty`, per-wing health in `status`.

**Tech Stack:** Python 3.10+, LanceDB backend (`LanceCollection`), pytest, existing `embed_texts` (bge-m3).

**Spec:** `docs/superpowers/specs/2026-07-26-info-aware-filing-design.md` — read it first; its "Critical invariant: prior-only novelty" section governs Tasks 2–3 and 5.

## Global Constraints

- Verbatim always: no task deletes or rewrites drawer *content*. Only the `novelty` metadata key is added.
- Demotion default OFF: `info_weight_enabled = False` until the Task 10 benchmark gate passes and a human flips it.
- `None`/absent novelty is NEVER punished (factor 1.0). Malformed values → treated as `None`.
- Missing novelty = **key absent** from metadata, never `null`.
- Prior-only: neighbours count only if `filed_at < target.filed_at` (lexicographic ISO compare — accepted limitation per spec).
- Mine-time additionally excludes same-`source_file` neighbours; backfill does NOT.
- Mining never fails because of novelty — every compute error degrades to filing without the key.
- Config knobs: `info_weight_enabled=False` / `info_weight_threshold=0.10` / `info_weight_min_factor=0.5`, env `CASTLE_INFO_WEIGHT_ENABLED` / `_THRESHOLD` / `_MIN_FACTOR`.
- Run tests from repo root `/home/lbihari/cognitive-castle`. Use absolute paths in Bash; never bare `cd`.
- Conventional commits. Never `--no-verify`, never amend.

---

### Task 1: Config knobs

**Files:**
- Modify: `cognitive_castle/config.py` (add 3 properties after `recency_max_boost`, ~line 660)
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Produces: `cfg.info_weight_enabled -> bool`, `cfg.info_weight_threshold -> float`, `cfg.info_weight_min_factor -> float`. Tasks 6–8 consume these exact names.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_config.py`)

```python
class TestInfoWeightConfig:
    """Config knobs for info-aware retrieval demotion (2026-07-26 spec)."""

    def test_defaults(self):
        cfg = _make_config_with_file_config({})
        assert cfg.info_weight_enabled is False
        assert cfg.info_weight_threshold == 0.10
        assert cfg.info_weight_min_factor == 0.5

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("CASTLE_INFO_WEIGHT_ENABLED", "1")
        monkeypatch.setenv("CASTLE_INFO_WEIGHT_THRESHOLD", "0.2")
        monkeypatch.setenv("CASTLE_INFO_WEIGHT_MIN_FACTOR", "0.7")
        cfg = _make_config_with_file_config({})
        assert cfg.info_weight_enabled is True
        assert cfg.info_weight_threshold == 0.2
        assert cfg.info_weight_min_factor == 0.7

    def test_file_config(self):
        cfg = _make_config_with_file_config(
            {"info_weight_enabled": True, "info_weight_threshold": 0.15,
             "info_weight_min_factor": 0.3}
        )
        assert cfg.info_weight_enabled is True
        assert cfg.info_weight_threshold == 0.15
        assert cfg.info_weight_min_factor == 0.3

    def test_malformed_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("CASTLE_INFO_WEIGHT_THRESHOLD", "not-a-float")
        cfg = _make_config_with_file_config({})
        assert cfg.info_weight_threshold == 0.10
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_config.py -k InfoWeight --no-cov -v`
Expected: FAIL — `AttributeError: ... has no attribute 'info_weight_enabled'`

- [ ] **Step 3: Implement the 3 properties** (in `config.py`, mirror the `recency_tau_days` pattern exactly; place after `recency_max_boost`)

```python
    @property
    def info_weight_enabled(self):
        """Gate for info-weight retrieval demotion (2026-07-26 spec).

        Default: ``False`` — flips ON only after the LongMemEval benchmark
        gate. Env ``CASTLE_INFO_WEIGHT_ENABLED`` ("1"/"true" = on), then
        config file, then default.
        """
        env_val = os.environ.get("CASTLE_INFO_WEIGHT_ENABLED")
        if env_val is not None:
            return env_val.strip().lower() in ("1", "true", "yes")
        cfg_val = self._file_config.get("info_weight_enabled")
        if cfg_val is None:
            return False
        # String file-config values must parse, not truthy-coerce —
        # bool("false") is True. Mirrors use_new_retrieval_pipeline.
        if isinstance(cfg_val, str):
            return cfg_val.strip().lower() in ("1", "true", "yes")
        return bool(cfg_val)

    @property
    def info_weight_threshold(self):
        """Novelty below this is demoted. Default 0.10 (research "low" band)."""
        env_val = os.environ.get("CASTLE_INFO_WEIGHT_THRESHOLD")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("info_weight_threshold")
        try:
            return float(cfg_val) if cfg_val is not None else 0.10
        except (TypeError, ValueError):
            return 0.10

    @property
    def info_weight_min_factor(self):
        """Score-multiplier floor for fully-duplicate drawers. Default 0.5."""
        env_val = os.environ.get("CASTLE_INFO_WEIGHT_MIN_FACTOR")
        if env_val:
            try:
                return float(env_val)
            except ValueError:
                pass
        cfg_val = self._file_config.get("info_weight_min_factor")
        try:
            return float(cfg_val) if cfg_val is not None else 0.5
        except (TypeError, ValueError):
            return 0.5
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_config.py -k InfoWeight --no-cov -v`
Expected: 4 PASS. Also run the whole file: `python -m pytest tests/test_config.py --no-cov -q` — no regressions.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/config.py tests/test_config.py
git commit -m "feat(config): info_weight_enabled/threshold/min_factor knobs"
```

---

### Task 2: `novelty_tagger.compute_novelty` (prior-only core)

**Files:**
- Create: `cognitive_castle/novelty_tagger.py`
- Test: `tests/test_novelty_tagger.py` (create)

**Interfaces:**
- Consumes: `LanceCollection.vector_search(vec, n_results, where)` → list of row dicts with `id`, `metadata_json` (JSON string), `_distance` (cosine distance, `1 − cos`).
- Produces: `compute_novelty(vector, collection, wing, filed_at, self_id=None, exclude_source_file=None) -> float`. Tasks 3, 5, 9, 10 call this exact signature.

- [ ] **Step 1: Write the failing tests** (create `tests/test_novelty_tagger.py`)

```python
"""Unit tests for cognitive_castle.novelty_tagger (2026-07-26 spec)."""

import json
from unittest.mock import MagicMock

from cognitive_castle.novelty_tagger import compute_novelty


def _row(id_, distance, filed_at, source_file="f.md"):
    return {
        "id": id_,
        "_distance": distance,
        "metadata_json": json.dumps(
            {"filed_at": filed_at, "source_file": source_file}
        ),
    }


def _col_with(rows):
    col = MagicMock()
    col.vector_search.return_value = rows
    return col


def test_prior_only_twin_pair_asymmetry():
    """Critical invariant: only earlier-filed neighbours count.

    Later twin B (filed_at 2026-02) must NOT lower earlier drawer A's
    novelty — otherwise both twins get demoted and content is buried.
    """
    col = _col_with([_row("b", 0.02, "2026-02-01T00:00:00")])
    novelty_a = compute_novelty(
        [0.1] * 8, col, wing="w", filed_at="2026-01-01T00:00:00"
    )
    assert novelty_a == 1.0  # B is later → ignored → no priors → 1.0

    # Conversely, scoring B against prior A gives low novelty.
    col2 = _col_with([_row("a", 0.02, "2026-01-01T00:00:00")])
    novelty_b = compute_novelty(
        [0.1] * 8, col2, wing="w", filed_at="2026-02-01T00:00:00"
    )
    assert abs(novelty_b - 0.02) < 1e-9  # 1 − (1 − 0.02)


def test_self_id_excluded():
    col = _col_with([
        _row("me", 0.0, "2026-01-01T00:00:00"),
        _row("other", 0.3, "2025-12-01T00:00:00"),
    ])
    n = compute_novelty(
        [0.1] * 8, col, wing="w",
        filed_at="2026-01-02T00:00:00", self_id="me",
    )
    assert abs(n - 0.3) < 1e-9  # self dropped; other counts


def test_same_source_file_excluded_when_requested():
    """Mine-time rule: sibling chunks of the file being (re)filed are
    excluded so multi-batch re-mines don't score against themselves."""
    col = _col_with([
        _row("sib", 0.01, "2025-12-01T00:00:00", source_file="same.md"),
        _row("other", 0.4, "2025-12-01T00:00:00", source_file="diff.md"),
    ])
    n = compute_novelty(
        [0.1] * 8, col, wing="w", filed_at="2026-01-01T00:00:00",
        exclude_source_file="same.md",
    )
    assert abs(n - 0.4) < 1e-9

    # Backfill path (no exclusion): sibling counts.
    n2 = compute_novelty(
        [0.1] * 8, col, wing="w", filed_at="2026-01-01T00:00:00",
    )
    assert abs(n2 - 0.01) < 1e-9


def test_first_drawer_convention():
    col = _col_with([])
    assert compute_novelty([0.1] * 8, col, wing="w", filed_at="2026-01-01") == 1.0


def test_malformed_neighbour_metadata_skipped():
    bad = {"id": "x", "_distance": 0.05, "metadata_json": "{not json"}
    good = _row("y", 0.5, "2025-01-01T00:00:00")
    col = _col_with([bad, good])
    n = compute_novelty([0.1] * 8, col, wing="w", filed_at="2026-01-01")
    assert abs(n - 0.5) < 1e-9  # bad row skipped, not fatal


def test_wing_filter_reaches_backend():
    col = _col_with([])
    compute_novelty([0.1] * 8, col, wing="pro'jects", filed_at="2026-01-01")
    _, kwargs = col.vector_search.call_args
    # SQL-escaped single quote
    assert kwargs.get("where") == "wing = 'pro''jects'"
    assert kwargs.get("n_results") == 10
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_novelty_tagger.py --no-cov -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cognitive_castle.novelty_tagger'`

- [ ] **Step 3: Implement** (create `cognitive_castle/novelty_tagger.py`)

```python
"""Novelty tagging — prior-only nn_novelty against a live palace.

Single home for the scoring math behind info-aware filing (spec:
docs/superpowers/specs/2026-07-26-info-aware-filing-design.md) and the
`castle info-score` surface. Research basis: rho(nn_novelty,
LLE_residual) = 0.982 on the full palace (v3.4.0/v3.4.1 papers).

Critical invariant — PRIOR-ONLY: a drawer is scored only against
neighbours with strictly earlier ``filed_at``. This gives duplicate
pairs an asymmetry (first twin high, later twin low) so demotion buries
at most one of the pair. ``filed_at`` lives inside ``metadata_json``
(not a hoisted column), so filtering happens client-side after an
over-fetch.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_OVERFETCH = 10  # top-N neighbours fetched before client-side filtering


def compute_novelty(
    vector: list[float],
    collection,
    wing: Optional[str],
    filed_at: str,
    self_id: Optional[str] = None,
    exclude_source_file: Optional[str] = None,
) -> float:
    """Prior-only nn_novelty: ``1 − max_cosine`` over earlier-filed neighbours.

    Args:
        vector: the drawer's embedding (pre-computed; this never embeds).
        collection: LanceCollection exposing ``vector_search``.
        wing: same-wing constraint (None → whole palace).
        filed_at: the target's ISO timestamp; neighbours with
            ``filed_at >= this`` are ignored (prior-only).
        self_id: drop this drawer id from neighbours (re-mine safety).
        exclude_source_file: mine-time only — drop neighbours from this
            source file (sibling chunks mid-replacement). Backfill must
            NOT pass this.

    Returns:
        Novelty in [0, 2] (practically [0, 1] for normalized embeddings);
        1.0 when no prior neighbours exist (first-drawer convention).
    """
    where = None
    if wing:
        escaped = str(wing).replace("'", "''")
        where = f"wing = '{escaped}'"

    rows = collection.vector_search(list(vector), n_results=_OVERFETCH, where=where)

    max_cos = None
    for row in rows:
        if self_id is not None and row.get("id") == self_id:
            continue
        raw = row.get("metadata_json")
        try:
            meta = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            continue  # malformed neighbour — skip, never fatal
        if not isinstance(meta, dict):
            continue  # valid JSON but not an object ("null", "[1,2]") — same rule
        n_filed = meta.get("filed_at")
        if not n_filed or str(n_filed) >= str(filed_at):
            continue  # prior-only
        if exclude_source_file is not None and meta.get("source_file") == exclude_source_file:
            continue
        cos = 1.0 - float(row.get("_distance", 1.0))
        if max_cos is None or cos > max_cos:
            max_cos = cos

    if max_cos is None:
        return 1.0
    return 1.0 - max_cos
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_novelty_tagger.py --no-cov -v`
Expected: 6 PASS. Then `ruff check cognitive_castle/novelty_tagger.py tests/test_novelty_tagger.py && ruff format --check` the same files — fix silently if needed.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/novelty_tagger.py tests/test_novelty_tagger.py
git commit -m "feat(novelty): compute_novelty — prior-only nn_novelty core"
```

---

### Task 3: `novelty_tagger.backfill_novelty` (resumable)

**Files:**
- Modify: `cognitive_castle/novelty_tagger.py` (append)
- Test: `tests/test_novelty_tagger.py` (append)

**Interfaces:**
- Consumes: `compute_novelty` (Task 2); `LanceCollection._table.to_arrow()` (full scan — same trick as `prune_suggest._fallback_get_all`); `LanceCollection.update(ids=..., metadatas=...)` (read-merge-write, verified in `lancedb_backend.update`).
- Produces: `backfill_novelty(collection, batch_size=500, only_missing=True, progress=print) -> dict` returning `{"tagged": int, "skipped": int, "failed": int}`. Task 7's `repair --backfill-novelty` calls it.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_novelty_tagger.py`)

```python
import pyarrow as pa

from cognitive_castle.novelty_tagger import backfill_novelty


def _arrow_collection(rows_spec):
    """Mock LanceCollection whose _table.to_arrow() yields rows_spec and
    which records update() calls. rows_spec: list of dicts with id,
    vector, metadata_json, wing."""
    col = MagicMock()
    col._table.to_arrow.return_value = pa.Table.from_pylist(rows_spec)
    col.vector_search.return_value = []  # every drawer scores 1.0
    return col


def _spec_row(id_, has_novelty, wing="w", filed_at="2026-01-01T00:00:00"):
    meta = {"filed_at": filed_at, "source_file": "f.md"}
    if has_novelty:
        meta["novelty"] = 0.42
    return {
        "id": id_,
        "vector": [0.1] * 4,
        "wing": wing,
        "metadata_json": json.dumps(meta),
    }


def test_backfill_only_missing_skips_tagged():
    col = _arrow_collection([
        _spec_row("a", has_novelty=True),
        _spec_row("b", has_novelty=False),
    ])
    stats = backfill_novelty(col, batch_size=10, progress=lambda *_: None)
    assert stats == {"tagged": 1, "skipped": 1, "failed": 0}
    # Only "b" updated
    (call,) = col.update.call_args_list
    assert call.kwargs["ids"] == ["b"]
    assert call.kwargs["metadatas"] == [{"novelty": 1.0}]


def test_backfill_per_drawer_error_counts_failed():
    col = _arrow_collection([
        _spec_row("a", has_novelty=False),
        _spec_row("b", has_novelty=False),
    ])
    # First vector_search raises, second returns fine.
    col.vector_search.side_effect = [RuntimeError("boom"), []]
    stats = backfill_novelty(col, batch_size=10, progress=lambda *_: None)
    assert stats["failed"] == 1
    assert stats["tagged"] == 1


def test_backfill_does_not_pass_source_file_exclusion():
    """Spec: backfill must NOT apply the mine-time same-source_file rule."""
    col = _arrow_collection([_spec_row("a", has_novelty=False)])
    with_neighbour = [
        {"id": "n", "_distance": 0.05,
         "metadata_json": json.dumps(
             {"filed_at": "2025-01-01T00:00:00", "source_file": "f.md"})}
    ]
    col.vector_search.return_value = with_neighbour
    backfill_novelty(col, batch_size=10, progress=lambda *_: None)
    (call,) = col.update.call_args_list
    # Neighbour shares source_file "f.md" with target — still counted.
    assert abs(call.kwargs["metadatas"][0]["novelty"] - 0.05) < 1e-9


def test_backfill_batches_updates():
    col = _arrow_collection(
        [_spec_row(f"d{i}", has_novelty=False) for i in range(5)]
    )
    backfill_novelty(col, batch_size=2, progress=lambda *_: None)
    # 5 drawers, batch 2 → 3 update calls
    assert col.update.call_count == 3
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_novelty_tagger.py -k backfill --no-cov -v`
Expected: FAIL — `ImportError: cannot import name 'backfill_novelty'`

- [ ] **Step 3: Implement** (append to `cognitive_castle/novelty_tagger.py`)

```python
def backfill_novelty(
    collection,
    batch_size: int = 500,
    only_missing: bool = True,
    progress=print,
) -> dict:
    """Tag drawers missing the ``novelty`` metadata key. Resumable.

    Reads the whole table once (``_table.to_arrow()`` — same approach as
    ``prune_suggest``; ~seconds for a 65k palace), computes prior-only
    novelty per untagged drawer (NO source_file exclusion — targets are
    settled drawers, not mid-replacement ones), and applies metadata
    updates in batches via ``collection.update`` (read-merge-write, so
    unrelated metadata fields survive).

    Interrupt-safe: already-tagged drawers are skipped on the next run
    (``only_missing`` targets key-absence).

    Returns ``{"tagged": n, "skipped": n, "failed": n}``.
    """
    table = collection._table.to_arrow()
    rows = table.to_pylist()

    tagged = skipped = failed = 0
    pending_ids: list = []
    pending_metas: list = []

    def _flush():
        if pending_ids:
            collection.update(ids=list(pending_ids), metadatas=list(pending_metas))
            pending_ids.clear()
            pending_metas.clear()

    total = len(rows)
    for i, row in enumerate(rows):
        raw = row.get("metadata_json")
        try:
            meta = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            meta = {}
        if only_missing and "novelty" in meta:
            skipped += 1
            continue
        vector = row.get("vector")
        filed_at = meta.get("filed_at")
        if not vector or not filed_at:
            skipped += 1
            continue
        try:
            novelty = compute_novelty(
                list(vector),
                collection,
                wing=row.get("wing"),
                filed_at=str(filed_at),
                self_id=row.get("id"),
            )
        except Exception as e:  # noqa: BLE001 — per-drawer degrade, never abort
            failed += 1
            logger.warning("backfill: %s failed: %s", row.get("id"), e)
            continue
        pending_ids.append(row.get("id"))
        pending_metas.append({"novelty": novelty})
        tagged += 1
        if len(pending_ids) >= batch_size:
            _flush()
            progress(f"[backfill] {i + 1}/{total} scanned, {tagged} tagged")

    _flush()
    return {"tagged": tagged, "skipped": skipped, "failed": failed}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_novelty_tagger.py --no-cov -v`
Expected: 10 PASS (6 from Task 2 + 4 new). Ruff both files.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/novelty_tagger.py tests/test_novelty_tagger.py
git commit -m "feat(novelty): backfill_novelty — resumable, batched, prior-only"
```

---

### Task 4: Fusion — novelty threading + `apply_info_weight`

**Files:**
- Modify: `cognitive_castle/fusion.py`
- Test: `tests/test_fusion.py` (append)

**Interfaces:**
- Consumes: existing `CandidateRef`, `ScoredCandidate`, `weighted_rrf`, `apply_recency` (all in `fusion.py`; both dataclasses are `frozen=True`).
- Produces: `CandidateRef.novelty: float | None = None`; `ScoredCandidate.novelty: float | None = None`; `weighted_rrf` carries novelty (first non-None ref wins); `apply_recency` copies novelty through its reconstruction; `info_weight_factor(novelty, threshold, min_factor) -> float` (pure, reused by Task 10's bench); `apply_info_weight(scored, threshold, min_factor) -> list[ScoredCandidate]`. Task 6 calls `apply_info_weight` with cfg values.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_fusion.py`)

```python
from cognitive_castle.fusion import apply_info_weight, info_weight_factor


def _sc(did, score, novelty=None):
    return ScoredCandidate(
        drawer_id=did, timestamp_unix=0.0, score=score, novelty=novelty
    )


class TestInfoWeightFactor:
    def test_none_passthrough(self):
        assert info_weight_factor(None, 0.10, 0.5) == 1.0

    def test_at_or_above_threshold_passthrough(self):
        assert info_weight_factor(0.10, 0.10, 0.5) == 1.0
        assert info_weight_factor(0.9, 0.10, 0.5) == 1.0

    def test_floor_at_zero_novelty(self):
        assert info_weight_factor(0.0, 0.10, 0.5) == 0.5

    def test_linear_ramp_midpoint(self):
        # novelty = threshold/2 → factor = (1 + min_factor)/2
        assert abs(info_weight_factor(0.05, 0.10, 0.5) - 0.75) < 1e-9

    def test_threshold_zero_is_inert(self):
        assert info_weight_factor(0.0, 0.0, 0.5) == 1.0  # no div-by-zero
        assert info_weight_factor(0.05, -1.0, 0.5) == 1.0


class TestApplyInfoWeight:
    def test_demotes_below_threshold_and_resorts(self):
        scored = [_sc("dup", 1.0, novelty=0.0), _sc("fresh", 0.9, novelty=0.8)]
        out = apply_info_weight(scored, threshold=0.10, min_factor=0.5)
        # dup: 1.0 * 0.5 = 0.5; fresh: 0.9 * 1.0 = 0.9 → fresh first
        assert [c.drawer_id for c in out] == ["fresh", "dup"]
        assert abs(out[1].score - 0.5) < 1e-9

    def test_none_novelty_never_punished(self):
        scored = [_sc("untagged", 1.0, novelty=None)]
        out = apply_info_weight(scored, threshold=0.10, min_factor=0.5)
        assert out[0].score == 1.0

    def test_tie_broken_by_drawer_id(self):
        scored = [_sc("b", 0.5, novelty=0.9), _sc("a", 0.5, novelty=0.9)]
        out = apply_info_weight(scored, threshold=0.10, min_factor=0.5)
        assert [c.drawer_id for c in out] == ["a", "b"]

    def test_novelty_field_survives(self):
        out = apply_info_weight([_sc("x", 1.0, novelty=0.05)], 0.10, 0.5)
        assert out[0].novelty == 0.05


class TestNoveltyThreading:
    def test_weighted_rrf_carries_novelty(self):
        refs = [CandidateRef(drawer_id="d", timestamp_unix=1.0, novelty=0.3)]
        out = weighted_rrf({"dense": refs}, {"dense": 1.0})
        assert out[0].novelty == 0.3

    def test_weighted_rrf_first_non_none_wins(self):
        dense = [CandidateRef(drawer_id="d", timestamp_unix=1.0, novelty=None)]
        sparse = [CandidateRef(drawer_id="d", timestamp_unix=1.0, novelty=0.3)]
        out = weighted_rrf(
            {"dense": dense, "sparse": sparse}, {"dense": 1.0, "sparse": 1.0}
        )
        assert out[0].novelty == 0.3

    def test_apply_recency_preserves_novelty(self):
        from datetime import datetime, timezone

        sc = ScoredCandidate(
            drawer_id="d", timestamp_unix=0.0, score=1.0, novelty=0.2
        )
        out = apply_recency(
            [sc], now=datetime.now(timezone.utc), tau_days=90.0, max_boost=1.5
        )
        assert out[0].novelty == 0.2
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_fusion.py -k "InfoWeight or NoveltyThreading" --no-cov -v`
Expected: FAIL — `ImportError` / `TypeError: unexpected keyword argument 'novelty'`

- [ ] **Step 3: Implement in `fusion.py`**

3a. Add `novelty` to both dataclasses (keep `frozen=True`; new field last, defaulted):

```python
@dataclass(frozen=True)
class CandidateRef:
    """A drawer reference produced by a single retrieval signal."""

    drawer_id: str
    timestamp_unix: float
    novelty: float | None = None


@dataclass(frozen=True)
class ScoredCandidate:
    """A drawer reference with a fused score."""

    drawer_id: str
    timestamp_unix: float
    score: float
    contributing_signals: frozenset[str] = frozenset()
    novelty: float | None = None
```

3b. In `weighted_rrf`, carry novelty. Add alongside the `timestamps` dict:

```python
    novelties: dict[str, float] = {}
```

In BOTH loops where `timestamps.setdefault(...)` is called, add directly after it:

```python
                if cand.novelty is not None and cand.drawer_id not in novelties:
                    novelties[cand.drawer_id] = cand.novelty
```

And in the final `ScoredCandidate(...)` construction add:

```python
                novelty=novelties.get(did),
```

3c. In `apply_recency`, the reconstruction gains `novelty=c.novelty`:

```python
        boosted.append(
            ScoredCandidate(
                drawer_id=c.drawer_id,
                timestamp_unix=c.timestamp_unix,
                score=c.score * factor,
                contributing_signals=c.contributing_signals,
                novelty=c.novelty,
            )
        )
```

3d. Append the two new pure functions:

```python
def info_weight_factor(
    novelty: float | None, threshold: float, min_factor: float
) -> float:
    """Score multiplier for info-aware demotion (2026-07-26 spec).

    1.0 when the feature is inert (threshold <= 0), the drawer is
    untagged (novelty None), or novelty >= threshold. Below threshold:
    linear ramp from min_factor (novelty 0) up to 1.0 (novelty at
    threshold). Never amplifies; never drops.
    """
    if threshold <= 0 or novelty is None or novelty >= threshold:
        return 1.0
    return min_factor + (1.0 - min_factor) * (novelty / threshold)


def apply_info_weight(
    scored: list[ScoredCandidate],
    threshold: float,
    min_factor: float,
) -> list[ScoredCandidate]:
    """Demote low-novelty candidates and re-sort. Same contract as
    ``apply_recency``: pure, deterministic tie-break by drawer_id."""
    weighted = [
        ScoredCandidate(
            drawer_id=c.drawer_id,
            timestamp_unix=c.timestamp_unix,
            score=c.score * info_weight_factor(c.novelty, threshold, min_factor),
            contributing_signals=c.contributing_signals,
            novelty=c.novelty,
        )
        for c in scored
    ]
    return sorted(weighted, key=lambda s: (-s.score, s.drawer_id))
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_fusion.py --no-cov -v`
Expected: all pass, including every pre-existing fusion test (the new defaulted fields must not break them). Ruff `fusion.py` + `tests/test_fusion.py`.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/fusion.py tests/test_fusion.py
git commit -m "feat(fusion): apply_info_weight + novelty threading through RRF/recency"
```

---

### Task 5: Miner inline tagging

**Files:**
- Modify: `cognitive_castle/miner.py` (`_build_drawer_metadata` ~line 742; batched-upsert loop in `process_file` ~line 855)
- Test: `tests/test_miner.py` (append)

**Interfaces:**
- Consumes: `compute_novelty` (Task 2 signature); `embed_texts(texts) -> list[list[float]]` from `cognitive_castle.embedding`.
- Produces: drawers filed via `process_file` carry `metadata["novelty"]`; upserts pass `embeddings=` explicitly (one forward pass, reused for both novelty and storage).

**Key fact for the implementer:** the miner's re-mine path is delete-then-insert (`collection.delete(where={"source_file": ...})` runs before filing), so *old* siblings are already gone. The `exclude_source_file` guard protects against *same-run* siblings: with multi-batch files, batch 1 is upserted before batch 2 computes.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_miner.py`)

```python
class TestMineTimeNoveltyTagging:
    """Info-aware filing (2026-07-26 spec): every mine path tags novelty."""

    def _mine_one(self, tmp_dir, collection, monkeypatch, novelty_fn):
        import cognitive_castle.miner as miner_mod

        monkeypatch.setattr(
            "cognitive_castle.miner.compute_novelty", novelty_fn
        )
        f = Path(tmp_dir) / "doc.md"
        f.write_text("meaningful content " * 20)  # clears MIN_CHUNK_SIZE
        miner_mod.process_file(
            f, collection, wing="w", room=None, rooms={}, agent="test",
            project_path=str(tmp_dir), closets_col=None,
        )

    def test_mine_writes_novelty_metadata(self, tmp_dir, collection, monkeypatch):
        self._mine_one(tmp_dir, collection, monkeypatch, lambda *a, **k: 0.42)
        got = collection.get(include=["metadatas"])
        assert got.metadatas, "no drawers filed"
        assert all(m.get("novelty") == 0.42 for m in got.metadatas)

    def test_compute_failure_files_without_key(self, tmp_dir, collection, monkeypatch, capsys):
        def boom(*a, **k):
            raise RuntimeError("search down")

        self._mine_one(tmp_dir, collection, monkeypatch, boom)
        got = collection.get(include=["metadatas"])
        assert got.metadatas, "mining must not fail because of novelty"
        assert all("novelty" not in m for m in got.metadatas)

    def test_novelty_call_excludes_own_source_file(self, tmp_dir, collection, monkeypatch):
        seen = {}

        def spy(vector, col, wing, filed_at, self_id=None, exclude_source_file=None):
            seen["exclude_source_file"] = exclude_source_file
            return 1.0

        self._mine_one(tmp_dir, collection, monkeypatch, spy)
        assert seen["exclude_source_file"].endswith("doc.md")
```

*(Adjust `process_file`'s exact call signature to the real one at implementation time — check `grep -n "def process_file" cognitive_castle/miner.py` and mirror how existing tests in `tests/test_miner.py` invoke it. The three behaviours under test are what matter.)*

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_miner.py -k Novelty --no-cov -v`
Expected: FAIL — `AttributeError: ... has no attribute 'compute_novelty'` (monkeypatch target doesn't exist yet)

- [ ] **Step 3: Implement in `miner.py`**

3a. Import at module top (alongside existing imports):

```python
from .novelty_tagger import compute_novelty
```

3b. `_build_drawer_metadata` gains an optional param, placed after `source_mtime`:

```python
def _build_drawer_metadata(
    wing, room, source_file, chunk_index, agent, content, source_mtime=None,
    novelty=None,
):
    ...
    # after the existing decay_score line:
    if novelty is not None:
        metadata["novelty"] = novelty
```

3c. In the batched-upsert loop in `process_file`, replace the batch build + upsert with an embed-first flow:

```python
        from .embedding import embed_texts

        drawers_added = 0
        for batch_start in range(0, len(chunks), DRAWER_UPSERT_BATCH_SIZE):
            batch = chunks[batch_start : batch_start + DRAWER_UPSERT_BATCH_SIZE]
            batch_docs = [c["content"] for c in batch]
            batch_ids = [
                f"drawer_{wing}_{room}_{hashlib.sha256((source_file + str(c['chunk_index'])).encode()).hexdigest()[:24]}"
                for c in batch
            ]

            # One forward pass; vectors reused for novelty AND storage.
            try:
                batch_vecs = embed_texts(batch_docs)
            except Exception:
                batch_vecs = None  # degrade: upsert embeds internally, no novelty

            batch_metas = []
            for j, chunk in enumerate(batch):
                novelty = None
                if batch_vecs is not None:
                    try:
                        novelty = compute_novelty(
                            batch_vecs[j],
                            collection,
                            wing=wing,
                            filed_at=datetime.now().isoformat(),
                            self_id=batch_ids[j],
                            exclude_source_file=source_file,
                        )
                    except Exception as e:  # noqa: BLE001 — never fail mining
                        _warn_novelty_once(e)
                batch_metas.append(
                    _build_drawer_metadata(
                        wing, room, source_file, chunk["chunk_index"],
                        agent, chunk["content"], source_mtime, novelty=novelty,
                    )
                )

            collection.upsert(
                documents=batch_docs,
                ids=batch_ids,
                metadatas=batch_metas,
                embeddings=batch_vecs,  # None → backend embeds internally
            )
            drawers_added += len(batch_docs)
```

3d. Add the once-per-process warning helper near the top of `miner.py`:

```python
_NOVELTY_WARNED = False


def _warn_novelty_once(exc) -> None:
    global _NOVELTY_WARNED
    if not _NOVELTY_WARNED:
        _NOVELTY_WARNED = True
        import sys

        sys.stderr.write(
            f"[castle] novelty tagging degraded ({exc}); drawers filed without the key\n"
        )
```

**Note:** `filed_at` inside `_build_drawer_metadata` and the `filed_at` passed to `compute_novelty` are two `datetime.now()` calls microseconds apart. That is fine — the value used for prior-only comparison at *search-from-backfill* time is the stored one, and both are strictly later than every existing drawer.

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_miner.py --no-cov -q`
Expected: all pass — the 3 new plus every pre-existing miner test (embed-first upsert must be behaviour-compatible). Ruff `miner.py` + `tests/test_miner.py`.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/miner.py tests/test_miner.py
git commit -m "feat(miner): inline novelty tagging — embed-first batches, degrade-safe"
```

---

### Task 6: Searcher — extraction + gate

**Files:**
- Modify: `cognitive_castle/searcher.py` (`_extract_ts` area ~line 336; `_to_refs` + Stage-2 block ~lines 618–646; `search` ~line 208, `search_memories` ~line 253, `_new_pipeline_search` ~line 527 — add `info_weight` param to each)
- Test: `tests/test_searcher.py` (append)

**Interfaces:**
- Consumes: `apply_info_weight`, `CandidateRef(..., novelty=...)` (Task 4); `cfg.info_weight_enabled/threshold/min_factor` (Task 1).
- Produces: `_extract_novelty(row) -> float | None`; `search(..., info_weight: bool = False)`, `search_memories(..., info_weight: bool = False)`, `_new_pipeline_search(..., info_weight: bool = False)`. Task 7's CLI flag threads through `search`. MCP `castle_search` may pass `info_weight=True` (optional; not in this plan's scope to add the MCP schema field).

**Plan-time verification (spec requirement) — run BEFORE writing code:**

```bash
python - <<'EOF'
from cognitive_castle.palace import get_collection
col = get_collection("/home/lbihari/.castle/palace", collection_name="castle_drawers", create=False)
d = col.vector_search([0.0]*1024, n_results=1)
f = col.fts_search("castle", n_results=1)
print("dense keys:", sorted(d[0].keys()) if d else "EMPTY")
print("fts keys:", sorted(f[0].keys()) if f else "EMPTY")
EOF
```

Expected: both include `metadata_json`. If FTS rows lack it, `_extract_novelty` returns None for sparse refs — acceptable (weighted_rrf's first-non-None merge recovers the value from the dense list when the drawer appears in both; sparse-only drawers stay unpunished). Record the observed keys in the task's completion report either way.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_searcher.py`)

```python
class TestNoveltyExtraction:
    def test_extract_novelty_from_metadata_json(self):
        from cognitive_castle.searcher import _extract_novelty
        import json as _json

        row = {"metadata_json": _json.dumps({"novelty": 0.07})}
        assert _extract_novelty(row) == 0.07

    def test_extract_novelty_absent_or_malformed_is_none(self):
        from cognitive_castle.searcher import _extract_novelty
        import json as _json

        assert _extract_novelty({"metadata_json": _json.dumps({})}) is None
        assert _extract_novelty({"metadata_json": "{broken"}) is None
        assert _extract_novelty({}) is None
        # negative / non-numeric → None (never an amplifier)
        assert _extract_novelty(
            {"metadata_json": _json.dumps({"novelty": -0.5})}
        ) is None
        assert _extract_novelty(
            {"metadata_json": _json.dumps({"novelty": "high"})}
        ) is None


class TestInfoWeightGate:
    def test_search_memories_accepts_info_weight_kwarg(self):
        """Signature-level guard: the kwarg exists and defaults False."""
        import inspect
        from cognitive_castle.searcher import search_memories, search

        for fn in (search_memories, search):
            sig = inspect.signature(fn)
            assert "info_weight" in sig.parameters
            assert sig.parameters["info_weight"].default is False
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_searcher.py -k "Novelty or InfoWeightGate" --no-cov -v`
Expected: FAIL — `ImportError: cannot import name '_extract_novelty'`

- [ ] **Step 3: Implement in `searcher.py`**

3a. Add `_extract_novelty` next to `_extract_ts` (~line 336):

```python
def _extract_novelty(row) -> float | None:
    """Novelty from a row's metadata_json. None when absent/malformed —
    untagged drawers are never punished by info-weight demotion."""
    if not isinstance(row, dict):
        return None
    raw = row.get("metadata_json")
    if not raw:
        return None
    try:
        import json as _json

        value = _json.loads(raw).get("novelty")
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None
```

3b. `_to_refs` gains the field:

```python
    def _to_refs(rows):
        return [
            CandidateRef(
                drawer_id=_extract_id(r),
                timestamp_unix=_extract_ts(r),
                novelty=_extract_novelty(r),
            )
            for r in rows
            if _extract_id(r)
        ]
```

3c. Import `apply_info_weight` in `_new_pipeline_search`'s lazy import line (`from .fusion import CandidateRef, weighted_rrf, apply_recency, apply_info_weight`) and insert directly after the `apply_recency` call (~line 646):

```python
    if info_weight or cfg.info_weight_enabled:
        fused = apply_info_weight(
            fused,
            threshold=cfg.info_weight_threshold,
            min_factor=cfg.info_weight_min_factor,
        )
```

3d. Thread the kwarg: add `info_weight: bool = False` to the signatures of `search`, `search_memories`, and `_new_pipeline_search`, and pass it along at each call site (`search → search_memories → _new_pipeline_search` — locate the internal calls with `grep -n "_new_pipeline_search(" cognitive_castle/searcher.py` and add `info_weight=info_weight` to each).

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_searcher.py --no-cov -q`
Expected: all pass — new tests plus every pre-existing searcher test (the disabled gate must leave behaviour identical: with `info_weight_enabled=False` default and no kwarg, `apply_info_weight` never runs). Ruff.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/searcher.py tests/test_searcher.py
git commit -m "feat(searcher): novelty extraction + opt-in info-weight gate"
```

---

### Task 7: CLI — `search --info-weight` + `repair --backfill-novelty`

**Files:**
- Modify: `cognitive_castle/cli.py` (search parser ~line 1302-area `p_search`; repair parser near `--clean-locks` ~line 1366; `cmd_search`; `cmd_repair` ~line 824)
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `search(..., info_weight=...)` (Task 6); `backfill_novelty` (Task 3).
- Produces: user-facing flags. Nothing downstream consumes these.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`)

```python
def test_search_parser_accepts_info_weight():
    from cognitive_castle.cli import build_parser

    args = build_parser().parser.parse_args(["search", "q", "--info-weight"])
    assert args.info_weight is True
    args2 = build_parser().parser.parse_args(["search", "q"])
    assert args2.info_weight is False


def test_repair_backfill_novelty_invokes_backfill(monkeypatch, capsys):
    from cognitive_castle.cli import build_parser, cmd_repair

    called = {}

    def fake_backfill(collection, batch_size=500, only_missing=True, progress=print):
        called["ran"] = True
        return {"tagged": 3, "skipped": 1, "failed": 0}

    monkeypatch.setattr(
        "cognitive_castle.novelty_tagger.backfill_novelty", fake_backfill
    )
    monkeypatch.setattr(
        "cognitive_castle.palace.get_collection", lambda *a, **k: object()
    )
    args = build_parser().parser.parse_args(["repair", "--backfill-novelty"])
    cmd_repair(args)
    out = capsys.readouterr().out
    assert called.get("ran")
    assert "tagged: 3" in out and "failed: 0" in out
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_cli.py -k "info_weight or backfill" --no-cov -v`
Expected: FAIL — `error: unrecognized arguments: --info-weight`

- [ ] **Step 3: Implement in `cli.py`**

3a. Search parser (next to the existing `--mode` argument on `p_search`):

```python
    p_search.add_argument(
        "--info-weight",
        dest="info_weight",
        action="store_true",
        help="Demote near-duplicate (low-novelty) drawers in ranking (opt-in; see docs)",
    )
```

3b. In `cmd_search`, pass it through to the `search(...)` call: add `info_weight=getattr(args, "info_weight", False),` to the existing kwargs.

3c. Repair parser (next to `--clean-locks`):

```python
    p_repair.add_argument(
        "--backfill-novelty",
        dest="backfill_novelty",
        action="store_true",
        help="Tag drawers missing the novelty metadata key (resumable, read-mostly)",
    )
```

3d. In `cmd_repair`, add a branch BEFORE the legacy-message fallthrough:

```python
    if getattr(args, "backfill_novelty", False):
        from .novelty_tagger import backfill_novelty
        from .palace import get_collection

        palace_path = (
            os.path.expanduser(args.palace)
            if getattr(args, "palace", None)
            else CognitiveCastleConfig().palace_path
        )
        col = get_collection(palace_path, collection_name="castle_drawers", create=False)
        stats = backfill_novelty(col)
        print(
            f"Backfill complete — tagged: {stats['tagged']}, "
            f"skipped: {stats['skipped']}, failed: {stats['failed']}"
        )
        return
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_cli.py --no-cov -q`
Expected: all pass. Ruff.

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/cli.py tests/test_cli.py
git commit -m "feat(cli): search --info-weight + repair --backfill-novelty"
```

---

### Task 8: `castle status` — per-wing information health

**Files:**
- Modify: `cognitive_castle/miner.py` (`status()` ~line 1255)
- Test: `tests/test_miner.py` (append)

**Interfaces:**
- Consumes: stored `novelty` metadata (Tasks 3/5). Reads metadata only — ZERO vector searches, ZERO novelty computation.
- Produces: an extra line under each wing in `castle status` output:
  `    info: median novelty 0.07 · 61% below 0.10 · coverage 84%`
  Omitted entirely when coverage is 0% (pre-backfill palaces see no change).

- [ ] **Step 1: Read the current `status()` implementation** (`sed -n '1255,1330p' cognitive_castle/miner.py`) to find where per-wing sections print and what data access it already performs. Reuse its existing per-wing iteration; sample at most 500 rows per wing (whatever order the scan yields — arbitrary is fine per spec).

- [ ] **Step 2: Write the failing test** (append to `tests/test_miner.py`)

```python
class TestStatusInfoHealth:
    def test_status_prints_info_line_when_tagged(self, seeded_collection, capsys, monkeypatch, tmp_dir):
        import cognitive_castle.miner as miner_mod

        # Tag the seeded drawers with novelty via metadata update.
        got = seeded_collection.get(include=["metadatas"])
        seeded_collection.update(
            ids=list(got.ids),
            metadatas=[{"novelty": 0.05} for _ in got.ids],
        )
        monkeypatch.setattr(
            "cognitive_castle.palace.get_collection",
            lambda *a, **k: seeded_collection,
        )
        miner_mod.status(palace_path=tmp_dir)
        out = capsys.readouterr().out
        assert "median novelty" in out
        assert "coverage 100%" in out

    def test_status_omits_info_line_when_untagged(self, seeded_collection, capsys, monkeypatch, tmp_dir):
        import cognitive_castle.miner as miner_mod

        monkeypatch.setattr(
            "cognitive_castle.palace.get_collection",
            lambda *a, **k: seeded_collection,
        )
        miner_mod.status(palace_path=tmp_dir)
        out = capsys.readouterr().out
        assert "median novelty" not in out
```

*(Adapt the collection-access monkeypatch to how `status()` actually opens the palace — check Step 1's read. The two behaviours under test are what matter.)*

- [ ] **Step 3: Run tests, verify they fail**

Run: `python -m pytest tests/test_miner.py -k StatusInfoHealth --no-cov -v`
Expected: FAIL — "median novelty" not in output.

- [ ] **Step 4: Implement** — inside `status()`'s per-wing loop, after the wing's drawer count is known, add:

```python
        # Info-health line (2026-07-26 spec): stored metadata only, no scoring.
        try:
            import statistics as _stats

            sample = wing_rows[:500]  # arbitrary order; cheap health indicator
            novelties = []
            for meta in sample:
                v = meta.get("novelty") if isinstance(meta, dict) else None
                if isinstance(v, (int, float)) and v >= 0:
                    novelties.append(float(v))
            if novelties:
                coverage = round(100 * len(novelties) / max(1, len(sample)))
                below = round(
                    100 * sum(1 for v in novelties if v < 0.10) / len(novelties)
                )
                median = _stats.median(novelties)
                print(
                    f"    info: median novelty {median:.2f} · "
                    f"{below}% below 0.10 · coverage {coverage}%"
                )
        except Exception:
            pass  # health line is best-effort; status never fails because of it
```

*(`wing_rows` = whatever per-wing metadata list the existing `status()` iterates; bind to the real variable name found in Step 1.)*

- [ ] **Step 5: Run tests, verify pass; commit**

Run: `python -m pytest tests/test_miner.py --no-cov -q` — all pass. Ruff.

```bash
git add cognitive_castle/miner.py tests/test_miner.py
git commit -m "feat(status): per-wing info-health line (median novelty, coverage)"
```

---

### Task 9: `info_score` delegates to `novelty_tagger`

**Files:**
- Modify: `cognitive_castle/info_score.py` (`score_novelty` ~line 80–140)
- Test: `tests/test_info_score.py` (must stay green unchanged)

**Interfaces:**
- Consumes: nothing new — this is a DRY refactor. `info_score.score_novelty`'s public contract (`InfoScoreResult` with `novelty`, `band`, `neighbours`) is unchanged.
- Produces: one implementation of the neighbour-scan math. `info_score` keeps its own semantics (NOT prior-only — it scores arbitrary query text "now", so every stored drawer is a prior by definition; it also returns the neighbour list, which `compute_novelty` does not).

**Scope decision (read carefully):** `score_novelty` and `compute_novelty` share the cosine-conversion + max-cosine logic but differ in filtering (info-score has no filed_at, wants top-k neighbours back). The refactor extracts ONE tiny shared helper rather than forcing a fake delegation:

- [ ] **Step 1: Add to `novelty_tagger.py`:**

```python
def novelty_from_hits(hits: list[dict], drop_ids: set[str] | None = None) -> float:
    """``1 − max_cosine`` over already-filtered hit rows (dicts with
    ``_distance``). 1.0 when nothing remains. Shared core for
    compute_novelty and info_score."""
    max_cos = None
    for row in hits:
        if drop_ids and row.get("id") in drop_ids:
            continue
        cos = 1.0 - float(row.get("_distance", 1.0))
        if max_cos is None or cos > max_cos:
            max_cos = cos
    return 1.0 if max_cos is None else 1.0 - max_cos
```

- [ ] **Step 2: Rewrite `compute_novelty`'s tail to build the filtered row list then `return novelty_from_hits(filtered)`; rewrite `info_score.score_novelty`'s max-cosine computation to call `novelty_from_hits(hits)` (its neighbour-list building stays as is).**

- [ ] **Step 3: Run both test files, verify pass**

Run: `python -m pytest tests/test_info_score.py tests/test_novelty_tagger.py --no-cov -q`
Expected: all pass — `test_info_score.py` UNCHANGED and green proves the public contract held.

- [ ] **Step 4: Commit**

```bash
git add cognitive_castle/novelty_tagger.py cognitive_castle/info_score.py
git commit -m "refactor(info-score): share novelty_from_hits core with novelty_tagger"
```

---

### Task 10: Benchmark-gate harness extension

**Files:**
- Modify: `benchmarks/longmemeval_bench.py` (add `--info-weight` flag + demotion in candidate ranking)
- Test: `tests/test_bench_info_weight.py` (create — unit-level only; the full R@5 run is manual)

**Interfaces:**
- Consumes: `info_weight_factor` (Task 4 — the pure factor function, imported from `cognitive_castle.fusion`); `novelty_from_hits` (Task 9).
- Produces: `longmemeval_bench.py --info-weight` toggles demotion in the bench's session-ranking path; per spec Component 5, the bench does NOT run the production fusion pipeline, so this wiring is what makes the R@5 gate measurable at all.

- [ ] **Step 1: Read the bench's ranking path** — `grep -n "def build_palace_and_retrieve\|def _rank\|sort" benchmarks/longmemeval_bench.py | head` and read the function that produces `rankings`. Identify: (a) where per-session candidate scores are computed, (b) where the corpus (haystack sessions) is embedded/indexed per question.

- [ ] **Step 2: Write the failing unit test** (create `tests/test_bench_info_weight.py`)

```python
"""Unit test for the bench's info-weight demotion hook (2026-07-26 spec).

The full R@5 A/B run is a manual gate documented in the spec; this file
only pins the demotion arithmetic the bench applies when --info-weight
is passed.
"""

from benchmarks.longmemeval_bench import apply_bench_info_weight


def test_bench_demotes_low_novelty_session():
    # (session_id, score, novelty)
    ranked = [("dup", 0.9, 0.02), ("fresh", 0.8, 0.9)]
    out = apply_bench_info_weight(ranked, threshold=0.10, min_factor=0.5)
    # dup: 0.9 * (0.5 + 0.5*0.2) = 0.54 ; fresh: 0.8 → fresh first
    assert [sid for sid, _, _ in out] == ["fresh", "dup"]


def test_bench_none_novelty_untouched():
    ranked = [("a", 0.9, None)]
    out = apply_bench_info_weight(ranked, threshold=0.10, min_factor=0.5)
    assert out[0][1] == 0.9
```

- [ ] **Step 3: Run test, verify it fails** (`ImportError`), then implement in `longmemeval_bench.py`:

```python
def apply_bench_info_weight(ranked, threshold: float, min_factor: float):
    """Demote low-novelty sessions in a (session_id, score, novelty) list.
    Mirrors cognitive_castle.fusion.info_weight_factor — imported, not
    reimplemented — so bench numbers measure the production formula."""
    from cognitive_castle.fusion import info_weight_factor

    weighted = [
        (sid, score * info_weight_factor(nov, threshold, min_factor), nov)
        for sid, score, nov in ranked
    ]
    return sorted(weighted, key=lambda t: (-t[1], t[0]))
```

Then wire it: (a) add `--info-weight` to the bench's argparse; (b) at corpus-build time compute per-session novelty with `novelty_from_hits` over a same-corpus query of each session's vector against sessions earlier in `haystack_dates` order (prior-only by date position); (c) when the flag is on, pass the ranked list through `apply_bench_info_weight` before R@5 evaluation. Keep all of (b)/(c) inside the bench file; production code is untouched.

- [ ] **Step 4: Run tests + record the manual gate procedure**

Run: `python -m pytest tests/test_bench_info_weight.py --no-cov -v` — 2 PASS.
Append to the spec's Component 5 the exact commands:

```bash
python benchmarks/longmemeval_bench.py /path/to/longmemeval_s_cleaned.json               # baseline
python benchmarks/longmemeval_bench.py /path/to/longmemeval_s_cleaned.json --info-weight # demotion ON
```

(The actual run needs the LME dataset + hours of compute — it is the human-triggered gate, NOT part of this plan's execution.)

- [ ] **Step 5: Commit**

```bash
git add benchmarks/longmemeval_bench.py tests/test_bench_info_weight.py docs/superpowers/specs/2026-07-26-info-aware-filing-design.md
git commit -m "feat(bench): --info-weight demotion hook for the R@5 gate"
```

---

### Task 11: Docs + full-suite verification

**Files:**
- Modify: `README.md` (CLI table + Retrieval modes note), `CHANGELOG.md` (unreleased entry)
- Test: full suite

- [ ] **Step 1: README** — add to the CLI overview table:

```markdown
| `castle repair --backfill-novelty` | Tag existing drawers with novelty scores (one-time, resumable) |
```

and extend the `castle search` row's description: `; add --info-weight to demote near-duplicates (opt-in)`.

- [ ] **Step 2: CHANGELOG** — add under a new `## [Unreleased]` section at the top:

```markdown
## [Unreleased]

### Added

- **Info-aware filing (opt-in).** Every mined drawer now carries a
  `novelty` metadata score (prior-only nn_novelty — research basis:
  ρ(A,B)=0.982, v3.4.x papers). `castle search --info-weight` (or
  `info_weight_enabled` config) demotes — never drops — near-duplicate
  drawers in ranking. `castle repair --backfill-novelty` tags the
  existing palace (resumable). `castle status` shows per-wing
  information health. Default OFF pending the LongMemEval R@5 gate
  (spec: docs/superpowers/specs/2026-07-26-info-aware-filing-design.md).
```

- [ ] **Step 3: Full-suite verification**

Run: `python -m pytest tests/ --ignore=tests/benchmarks -q`
Expected: everything green (≈1640+ tests as of v3.4.1 plus ~28 new).
Run: `ruff check . && ruff format --check .` — clean.

- [ ] **Step 4: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: info-aware filing — README rows + changelog entry"
```

---

## Self-Review (performed at plan-write time)

- **Spec coverage:** knobs→T1; compute_novelty+invariants→T2; backfill→T3; fusion threading+factor→T4; miner inline→T5; searcher gate+plan-time verifications→T6; CLI flags→T7; status health→T8; info_score DRY→T9; bench gate harness→T10; docs→T11. Benchmark *run* itself is human-gated per spec — plan documents commands (T10 Step 4), does not execute.
- **Type consistency:** `compute_novelty(vector, collection, wing, filed_at, self_id=None, exclude_source_file=None)` used identically in T2/T3/T5; `info_weight_factor(novelty, threshold, min_factor)` in T4/T10; `backfill_novelty(collection, batch_size, only_missing, progress)` in T3/T7; `novelty_from_hits(hits, drop_ids)` in T9/T10.
- **Known judgment points for implementers (explicitly allowed):** exact `process_file` signature in T5 tests; `status()` per-wing variable binding in T8; `search→search_memories→_new_pipeline_search` call-site threading in T6. Each task says how to find the real shape.
