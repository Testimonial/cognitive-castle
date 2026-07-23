"""Tests for cross-stratum aggregation: BH-FDR, N* saturation, ≥200 floor."""

import numpy as np

from analysis.aggregation import (
    benjamini_hochberg,
    compute_n_star,
    select_fittable_strata,
)


def test_bh_correction_known_case():
    """BH q=0.05: verify survivor count via hand calculation.

    NOTE: Plan asserted `sum(survivors) == 3`, but hand-checking BH shows
    only 2 survive on this input:
      m = 7, q = 0.05
      rank 1: p=0.001 ≤ (1/7)*0.05 = 0.00714  ✓
      rank 2: p=0.008 ≤ (2/7)*0.05 = 0.01429  ✓
      rank 3: p=0.039 ≤ (3/7)*0.05 = 0.02143  ✗
      rank 4+: all fail
    Largest k satisfying the BH condition is 2, so only p_(1) and p_(2)
    (indices 0 and 1) survive. The plan's assertion was a math error.
    """
    p_values = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.5]
    survivors = benjamini_hochberg(p_values, q=0.05)
    assert sum(survivors) == 2
    assert survivors[0] and survivors[1]
    assert not survivors[2]
    assert not survivors[3]


def test_bh_correction_all_significant():
    survivors = benjamini_hochberg([0.0001, 0.0001, 0.0001], q=0.05)
    assert all(survivors)


def test_bh_correction_none_significant():
    survivors = benjamini_hochberg([0.9, 0.8, 0.7], q=0.05)
    assert not any(survivors)


def test_compute_n_star_finds_saturation():
    """Synthetic: info decays then stays low.

    NOTE: Plan used `shuffled_null = np.full(300, 0.5)`, which has IQR = 0,
    so `threshold = threshold_factor * IQR = 0` and the info series
    (values ≥ 0.05) can never drop below the threshold — the test would
    always return None. Fixed by giving `shuffled_null` real spread so
    IQR > 0 and the saturated region (0.05) falls below threshold.
    """
    N = np.arange(1, 301)
    # First 100: decreasing from 1.0 to 0.1; remainder: stays ~0.05
    info = np.concatenate([np.linspace(1.0, 0.1, 100), np.full(200, 0.05)])
    # Give the null real spread — linspace 0.05..0.35, IQR ≈ 0.15.
    # threshold_factor=1.0 → threshold ≈ 0.15, so saturated tail (0.05)
    # falls below it.
    shuffled_null = np.linspace(0.05, 0.35, 300)
    n_star = compute_n_star(
        N,
        info,
        shuffled_null,
        threshold_factor=1.0,
        persistence_factor=0.1,
    )
    assert 50 <= n_star <= 200  # somewhere in the saturated region


def test_compute_n_star_returns_none_if_never_saturates():
    N = np.arange(1, 101)
    info = np.full(100, 1.0)  # never decays
    shuffled_null = np.full(100, 0.5)
    n_star = compute_n_star(
        N,
        info,
        shuffled_null,
        threshold_factor=1.0,
        persistence_factor=0.1,
    )
    assert n_star is None


def test_select_fittable_strata_enforces_200_floor():
    strata_sizes = {
        "big1": 5000,
        "big2": 300,
        "borderline": 199,
        "small": 50,
    }
    fittable, descriptive = select_fittable_strata(strata_sizes, floor=200)
    assert "big1" in fittable and "big2" in fittable
    assert "borderline" in descriptive
    assert "small" in descriptive
