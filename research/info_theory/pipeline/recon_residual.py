"""Estimator B: LLE reconstruction residual with Tikhonov regularization."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyarrow as pa

from .neighbors import compute_all_neighbors


def lle_weights(target: np.ndarray, priors: np.ndarray, lam: float = 1e-3) -> np.ndarray:
    """Roweis-Saul LLE weights summing to 1, closed-form with Tikhonov.

    minimize ||target - Σ w_k priors_k||² subject to Σ w_k = 1
    Solution: w = G_reg⁻¹ 1 / (1ᵀ G_reg⁻¹ 1)
    where G = (priors - target)(priors - target)ᵀ
          G_reg = G + λ·trace(G)·I
    """
    K = priors.shape[0]
    centered = priors - target
    G = centered @ centered.T
    G_reg = G + lam * np.trace(G) * np.eye(K)
    try:
        ones = np.ones(K)
        inv_ones = np.linalg.solve(G_reg, ones)
        return inv_ones / inv_ones.sum()
    except np.linalg.LinAlgError:
        # Even with regularization, fall back to uniform weights
        return np.ones(K) / K


def compute_recon_residual(target: np.ndarray, priors: list, k: int, lam: float) -> float:
    """L2 norm of reconstruction residual."""
    P = np.array(priors[:k])
    w = lle_weights(target, P, lam)
    recon = w @ P
    return float(np.linalg.norm(target - recon))


def compute_for_table(
    table: pa.Table,
    k_target: int = 20,
    k_floor: int = 5,
    lam: float = 1e-3,
    group_by: Optional[str] = None,
) -> pa.Table:
    """Add 'recon_residual' column. Null for first K_floor-1 drawers per stratum."""
    residuals = []
    all_neighbors = compute_all_neighbors(
        table, k=k_target, prior_filter="filed_at", group_by=group_by
    )
    vectors = table.column("vector").to_pylist()
    for i in range(table.num_rows):
        neighbors = all_neighbors[i]
        if len(neighbors) < k_floor:
            residuals.append(None)
            continue
        target_vec = np.array(vectors[i])
        prior_vecs = [np.array(vectors[j]) for j in neighbors]
        residuals.append(compute_recon_residual(target_vec, prior_vecs, k=len(neighbors), lam=lam))
    return table.append_column("recon_residual", pa.array(residuals, type=pa.float64()))
