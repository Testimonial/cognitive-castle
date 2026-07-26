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
