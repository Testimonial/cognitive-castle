"""Spearman + Pearson with bootstrap CIs for A↔C and B↔C validation."""

from __future__ import annotations

import numpy as np
from scipy import stats


def _bootstrap_correlation(x, y, corr_func, n_resamples, seed):
    rng = np.random.default_rng(seed)
    n = len(x)
    estimates = []
    for _ in range(n_resamples):
        idx = rng.integers(0, n, n)
        estimates.append(corr_func(x[idx], y[idx])[0])
    return np.quantile(estimates, 0.025), np.quantile(estimates, 0.975)


def spearman_with_ci(x, y, n_resamples: int = 1000, seed: int = 42):
    """Spearman rank correlation + bootstrap 95% CI."""
    x = np.asarray(x)
    y = np.asarray(y)
    rho = stats.spearmanr(x, y)[0]
    lo, hi = _bootstrap_correlation(x, y, stats.spearmanr, n_resamples, seed)
    return float(rho), float(lo), float(hi)


def pearson_with_ci(x, y, n_resamples: int = 1000, seed: int = 42):
    """Pearson correlation + bootstrap 95% CI."""
    x = np.asarray(x)
    y = np.asarray(y)
    rho = stats.pearsonr(x, y)[0]
    lo, hi = _bootstrap_correlation(x, y, stats.pearsonr, n_resamples, seed)
    return float(rho), float(lo), float(hi)
