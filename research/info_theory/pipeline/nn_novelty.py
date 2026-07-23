"""Estimator A: nearest-neighbor novelty.

1 - max_cosine(d_t, prior_set). Cheap baseline.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyarrow as pa

from .neighbors import _cosine, compute_all_neighbors


def compute_nn_novelty(target_vec, prior_vecs):
    """1 - max cosine similarity, or 1.0 if prior set is empty."""
    if not prior_vecs:
        return 1.0
    sims = [_cosine(target_vec, p) for p in prior_vecs]
    return 1.0 - max(sims)


def compute_for_table(
    table: pa.Table,
    group_by: Optional[str] = None,
) -> pa.Table:
    """Compute nn_novelty per row. Adds 'nn_novelty' and 'is_first' columns."""
    novelties: list[float] = []
    is_first: list[bool] = []
    all_neighbors = compute_all_neighbors(table, k=1, prior_filter="filed_at", group_by=group_by)
    vectors = table.column("vector").to_pylist()
    for i in range(table.num_rows):
        neighbors = all_neighbors[i]
        if not neighbors:
            novelties.append(1.0)
            is_first.append(True)
        else:
            target_vec = np.array(vectors[i])
            prior_vec = np.array(vectors[neighbors[0]])
            novelties.append(compute_nn_novelty(target_vec, [prior_vec]))
            is_first.append(False)
    out = table.append_column("nn_novelty", pa.array(novelties, type=pa.float64()))
    out = out.append_column("is_first", pa.array(is_first, type=pa.bool_()))
    return out
