import numpy as np
from analysis.correlations import spearman_with_ci, pearson_with_ci


def test_spearman_perfect_correlation():
    x = np.array([1, 2, 3, 4, 5, 6])
    y = np.array([2, 4, 6, 8, 10, 12])
    rho, ci_lo, ci_hi = spearman_with_ci(x, y, n_resamples=100, seed=42)
    assert abs(rho - 1.0) < 1e-9


def test_spearman_no_correlation():
    rng = np.random.default_rng(42)
    x = rng.normal(0, 1, 200)
    y = rng.normal(0, 1, 200)
    rho, ci_lo, ci_hi = spearman_with_ci(x, y, n_resamples=200, seed=42)
    assert abs(rho) < 0.2
    # CI should include 0
    assert ci_lo <= 0 <= ci_hi


def test_pearson_known_correlation():
    rng = np.random.default_rng(42)
    n = 1000
    x = rng.normal(0, 1, n)
    y = 0.7 * x + 0.3 * rng.normal(0, 1, n)
    rho, _, _ = pearson_with_ci(x, y, n_resamples=100, seed=42)
    assert 0.5 < rho < 0.95
