"""Cross-stratum aggregation: FDR correction (BH q=0.05), N*
saturation point, and the ≥200-drawer power-floor filter."""

from __future__ import annotations

from typing import Optional

import numpy as np


def benjamini_hochberg(p_values: list, q: float = 0.05) -> list:
    """Return list of bool — True if p survives BH correction at FDR=q.

    BH procedure:
      Sort p_values ascending. Find the largest k such that
      p_(k) ≤ (k/m) * q. Reject all p_(i) for i ≤ k.
    """
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda t: t[1])
    threshold_idx = -1
    for rank, (_, p) in enumerate(indexed, start=1):
        if p <= (rank / m) * q:
            threshold_idx = rank
    out = [False] * m
    if threshold_idx > 0:
        for orig_idx, _ in indexed[:threshold_idx]:
            out[orig_idx] = True
    return out


def _lowess(N: np.ndarray, y: np.ndarray, frac: float = 0.1) -> np.ndarray:
    """Light-weight LOWESS smoothing. Uses statsmodels if available, else
    moving average fallback padded to len(y).
    """
    try:
        from statsmodels.nonparametric.smoothers_lowess import lowess

        return lowess(y, N, frac=frac, return_sorted=False)
    except ImportError:
        win = max(3, int(len(y) * frac))
        cumsum = np.cumsum(np.insert(y, 0, 0))
        ma = (cumsum[win:] - cumsum[:-win]) / win
        # Pad start so output length matches len(y) — same-shape contract
        # as statsmodels' lowess(return_sorted=False).
        pad = np.full(len(y) - len(ma), ma[0] if len(ma) else 0.0)
        return np.concatenate([pad, ma])


def compute_n_star(
    N: np.ndarray,
    info: np.ndarray,
    shuffled_null: np.ndarray,
    threshold_factor: float = 1.0,
    persistence_factor: float = 0.1,
) -> Optional[int]:
    """Smallest N where smoothed info drops below
    threshold_factor × IQR(shuffled_null) AND stays for
    ≥ max(10, len(N) * persistence_factor) consecutive points.

    Returns N* index, or None if never saturates.
    """
    smoothed = _lowess(np.arange(len(info)), info, frac=0.1)
    null_iqr = float(np.percentile(shuffled_null, 75) - np.percentile(shuffled_null, 25))
    threshold = threshold_factor * null_iqr
    persistence = max(10, int(len(N) * persistence_factor))
    below = smoothed < threshold
    # Find first N where `persistence` consecutive Trues follow
    for i in range(len(below) - persistence + 1):
        if all(below[i : i + persistence]):
            return int(N[i])
    return None


def select_fittable_strata(strata_sizes: dict, floor: int = 200) -> tuple[list, list]:
    """Return (fittable_strata, descriptive_only_strata)."""
    fittable = [s for s, n in strata_sizes.items() if n >= floor]
    descriptive = [s for s, n in strata_sizes.items() if n < floor]
    return fittable, descriptive
