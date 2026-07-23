import numpy as np

from analysis.fit_decay import (
    aic_model_selection,
    empirical_variance_per_bin,
    fit_exponential,
    fit_powerlaw_weighted,
)

# Seed numpy legacy RNG for the one test that uses np.random.normal without a
# generator (test_empirical_variance_binning). Deterministic runs matter.
np.random.seed(0)


def test_empirical_variance_binning():
    """Bin width 10 → 5 bins for N=50."""
    N = np.arange(1, 51)
    y = np.random.normal(0, 1, 50)
    bins = empirical_variance_per_bin(N, y, bin_width=10)
    assert len(bins) == 5
    assert all(v > 0 for v in bins.values())


def test_powerlaw_recovery_homoscedastic():
    rng = np.random.default_rng(42)
    N = np.arange(1, 1001)
    y = N**-0.5 + rng.normal(0, 0.01, 1000)
    params = fit_powerlaw_weighted(N, y)
    assert abs(params["alpha"] - 0.5) < 0.05


def test_exponential_recovery():
    rng = np.random.default_rng(42)
    N = np.arange(1, 1001)
    y = 1 + 9 * np.exp(-N / 100) + rng.normal(0, 0.1, 1000)
    params = fit_exponential(N, y)
    assert abs(params["tau"] - 100) < 10
    assert abs(params["c"] - 1) < 0.5


def test_aic_picks_powerlaw_for_powerlaw_data():
    rng = np.random.default_rng(42)
    N = np.arange(1, 1001)
    y = N**-0.5 + rng.normal(0, 0.01, 1000)
    pl = fit_powerlaw_weighted(N, y)
    ex = fit_exponential(N, y)
    selection = aic_model_selection(pl, ex)
    assert selection["winner"] == "powerlaw"
    assert selection["weight_powerlaw"] > 0.9
