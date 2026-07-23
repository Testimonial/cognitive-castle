"""H1 heterogeneity test: Kruskal-Wallis with epsilon-squared effect size."""

from __future__ import annotations

import numpy as np
from scipy import stats


def kruskal_wallis_with_epsilon_sq(groups: dict) -> dict:
    """Run Kruskal-Wallis on a dict of {group_name: values}.

    Returns dict with:
      H: KW statistic
      p_value: p-value
      epsilon_squared: eps_sq_H = (H - k + 1) / (n - k)
      n_per_group: counts
      median_per_group: medians
    """
    arrays = [np.asarray(v) for v in groups.values()]
    H, p = stats.kruskal(*arrays)
    n = sum(len(a) for a in arrays)
    k = len(arrays)
    # Epsilon-squared per Tomczak & Tomczak 2014
    eps_sq = (H - k + 1) / max(n - k, 1)
    return {
        "H": float(H),
        "p_value": float(p),
        "epsilon_squared": float(max(eps_sq, 0)),
        "n_per_group": {name: len(np.asarray(v)) for name, v in groups.items()},
        "median_per_group": {name: float(np.median(np.asarray(v))) for name, v in groups.items()},
    }
