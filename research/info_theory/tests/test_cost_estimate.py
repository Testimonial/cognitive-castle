from unittest.mock import patch

from pipeline.cost_estimate import _haiku_price_per_1k, estimate_cost


def test_estimate_cost_returns_lo_mean_hi():
    with patch("pipeline.cost_estimate._sample_drawers") as m:
        m.return_value = [{"text": "x" * 1000}] * 10
        result = estimate_cost("llm-surprise", n_samples=10, target_calls=1000)
    assert "lo" in result and "mean" in result and "hi" in result
    assert result["lo"] <= result["mean"] <= result["hi"]


def test_haiku_price_constants_match_2026_05():
    """Pinned at experiment start; update if pricing changes."""
    # Haiku 4.5 pricing as of 2026-05-16
    p = _haiku_price_per_1k()
    assert p["input"] > 0 and p["output"] > 0
