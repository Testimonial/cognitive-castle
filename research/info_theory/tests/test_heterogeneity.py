import numpy as np
from analysis.heterogeneity import kruskal_wallis_with_epsilon_sq


def test_kruskal_wallis_detects_difference():
    rng = np.random.default_rng(42)
    group_a = rng.normal(0.3, 0.1, 20)
    group_b = rng.normal(0.7, 0.1, 20)
    result = kruskal_wallis_with_epsilon_sq({"a": group_a, "b": group_b})
    assert result["p_value"] < 0.001
    assert result["epsilon_squared"] > 0.3  # large effect


def test_kruskal_wallis_no_difference():
    rng = np.random.default_rng(42)
    a = rng.normal(0.5, 0.1, 30)
    b = rng.normal(0.5, 0.1, 30)
    result = kruskal_wallis_with_epsilon_sq({"a": a, "b": b})
    assert result["p_value"] > 0.05
    assert result["epsilon_squared"] < 0.1


def test_handles_three_groups():
    rng = np.random.default_rng(42)
    groups = {
        "miner": rng.normal(0.7, 0.1, 20),
        "session_hook": rng.normal(0.5, 0.1, 20),
        "mcp": rng.normal(0.2, 0.1, 5),
    }
    result = kruskal_wallis_with_epsilon_sq(groups)
    assert result["p_value"] < 0.001
    assert "n_per_group" in result
    assert result["n_per_group"]["mcp"] == 5
