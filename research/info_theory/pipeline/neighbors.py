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


def compute_all_neighbors(
    table: pa.Table,
    k: int,
    prior_filter: str = "filed_at",
    group_by: Optional[str] = None,
) -> list[list[int]]:
    """Return, for every row i, the indices of up to k nearest priors.

    Priors are rows where `table[prior_filter][j] < table[prior_filter][i]`.
    If `group_by` is set, restrict to rows where that field matches row i's.

    Vectorized: one numpy matmul across the full normalized matrix instead
    of N per-row cosine loops.
    """
    n = table.num_rows
    if n == 0:
        return []

    vectors = np.asarray(table.column("vector").to_pylist(), dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normed = np.where(norms > 0, vectors / np.maximum(norms, 1e-12), 0.0)

    pivots = np.asarray(table.column(prior_filter).to_pylist())
    groups = np.asarray(table.column(group_by).to_pylist()) if group_by else None

    result: list[list[int]] = []
    for i in range(n):
        mask = pivots < pivots[i]
        if groups is not None:
            mask = mask & (groups == groups[i])
        # Self is already excluded by strict `<` on the pivot, but be defensive.
        mask[i] = False
        prior_idx = np.where(mask)[0]
        if prior_idx.size == 0:
            result.append([])
            continue

        sims = normed[prior_idx] @ normed[i]

        # Match legacy tie-breaking: original code sorted (sim, i) descending,
        # so among equal sims the larger index came first. Replicate by using
        # -index as the secondary key in a lexsort (primary key comes last).
        neg_sims = -sims
        neg_idx = -prior_idx
        if prior_idx.size <= k:
            order = np.lexsort((neg_idx, neg_sims))
        else:
            # argpartition finds the top-k candidates cheaply, then we sort
            # only those k using the same lexsort tie-break rule.
            top = np.argpartition(neg_sims, k - 1)[:k]
            top_order = np.lexsort((neg_idx[top], neg_sims[top]))
            order = top[top_order]

        result.append(prior_idx[order].tolist())
    return result


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

    Thin wrapper over `compute_all_neighbors` for API compatibility. Production
    code that needs KNN for many rows should call `compute_all_neighbors`
    directly to amortize vector extraction and normalization.
    """
    return compute_all_neighbors(table, k=k, prior_filter=prior_filter, group_by=group_by)[
        target_idx
    ]
