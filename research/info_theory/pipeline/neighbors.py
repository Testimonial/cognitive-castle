"""Per-drawer KNN lookup over the prior set. Same-wing constraint
for palace; same-session for LME (passed via `group_by`)."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyarrow as pa


def _cosine(v1: np.ndarray, v2: np.ndarray) -> float:
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


def find_neighbors(
    table: pa.Table,
    target_idx: int,
    k: int,
    prior_filter: str = "filed_at",
    group_by: Optional[str] = None,
) -> list[int]:
    """Return indices (into table) of up to k nearest priors to row target_idx.

    Priors are rows where `table[prior_filter][i] < table[prior_filter][target_idx]`.
    If `group_by` is set, also restrict to rows where that field matches the target's.
    """
    target = table.slice(target_idx, 1).to_pylist()[0]
    target_vec = np.array(target["vector"])
    target_pivot = target[prior_filter]

    rows = table.to_pylist()
    candidates = []
    for i, r in enumerate(rows):
        if i == target_idx:
            continue
        if r[prior_filter] >= target_pivot:
            continue
        if group_by is not None and r.get(group_by) != target.get(group_by):
            continue
        sim = _cosine(target_vec, np.array(r["vector"]))
        candidates.append((sim, i))
    candidates.sort(reverse=True)
    return [i for _, i in candidates[:k]]
