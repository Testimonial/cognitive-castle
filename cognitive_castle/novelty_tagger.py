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
            continue  # valid JSON that isn't an object — skip, never fatal
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
