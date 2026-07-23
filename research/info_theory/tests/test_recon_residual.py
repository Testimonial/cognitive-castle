"""Tests for Estimator B: LLE reconstruction residual with Tikhonov."""

import numpy as np
import pyarrow as pa

from pipeline.recon_residual import (
    compute_for_table,
    compute_recon_residual,
    lle_weights,
)

np.random.seed(0)


def test_lle_weights_recover_convex_combination():
    """If d_t lies in span of priors, weights reconstruct it exactly."""
    priors = np.array([[1.0, 0.0], [0.0, 1.0]])  # 2x2 basis
    target = np.array([0.5, 0.5])  # in span
    w = lle_weights(target, priors, lam=1e-9)
    recon = w @ priors
    assert np.allclose(recon, target, atol=1e-4)


def test_lle_weights_sum_to_one():
    priors = np.random.rand(5, 3)
    target = np.random.rand(3)
    w = lle_weights(target, priors, lam=1e-3)
    assert abs(w.sum() - 1.0) < 1e-6


def test_lle_handles_collinear_neighbors():
    """All K priors identical — singular Gram matrix.
    Tikhonov-regularized solve must succeed and return finite residual."""
    priors = np.tile(np.array([1.0, 0.0, 0.0]), (5, 1))
    target = np.array([0.0, 1.0, 0.0])  # orthogonal to all
    w = lle_weights(target, priors, lam=1e-3)
    assert np.all(np.isfinite(w))
    recon = w @ priors
    residual = np.linalg.norm(target - recon)
    assert np.isfinite(residual) and residual > 0


def test_recon_residual_zero_when_in_span():
    priors = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    target = np.array([0.3, 0.7])  # in span of priors
    r = compute_recon_residual(target, priors, k=2, lam=1e-9)
    assert r < 1e-3


def test_recon_residual_large_under_orthogonality():
    priors = [np.array([1.0, 0.0, 0.0])] * 5  # all same direction
    target = np.array([0.0, 1.0, 0.0])  # orthogonal
    r = compute_recon_residual(target, priors, k=5, lam=1e-3)
    assert r > 0.5  # substantial residual


def test_recon_residual_null_below_k_floor():
    """K_floor=5: prior set < 5 → recon_residual=None."""
    rows = []
    for i in range(3):
        rows.append(
            {
                "drawer_id": f"d{i}",
                "wing": "w",
                "filed_at": f"2026-01-{i + 1:02d}",
                "chunk_index": 0,
                "source_file": "f",
                "vector": [float(i), 0.0],
            }
        )
    t = pa.Table.from_pylist(rows)
    out = compute_for_table(t, k_target=20, k_floor=5, lam=1e-3, group_by="wing")
    residuals = out.column("recon_residual").to_pylist()
    # First 3 drawers all have <5 priors
    assert all(r is None for r in residuals)
