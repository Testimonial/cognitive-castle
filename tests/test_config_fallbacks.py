"""Configuration precedence and recovery from malformed deployment settings."""

import pytest

from cognitive_castle.config import CognitiveCastleConfig


@pytest.mark.parametrize(
    "name,default,configured",
    [
        ("embedder_dim", 1024, 384),
        ("reranker_k_interactive", 20, 7),
        ("reranker_k_hook", 10, 3),
        ("llm_judge_top_n", 10, 4),
        ("llm_timeout", 120, 9),
        ("k_rrf", 60, 40),
        ("weight_dense", 1.0, 0.3),
        ("weight_sparse", 1.0, 0.4),
        ("weight_kg", 0.5, 0.2),
        ("recency_tau_days", 90.0, 30.0),
        ("recency_max_boost", 1.5, 1.2),
        ("info_weight_threshold", 0.1, 0.2),
        ("info_weight_min_factor", 0.5, 0.3),
        ("entity_promote_threshold", 0.7, 0.8),
        ("entity_score_sample_drawers", 20, 5),
        ("entity_fetch_batch_size", 1000, 12),
        ("kg_hop_top_n", 50, 4),
        ("quality_threshold_medium", 0.53, 0.4),
        ("quality_threshold_high", 0.6, 0.8),
        ("quality_boost_medium", 1.15, 1.3),
        ("quality_boost_high", 1.25, 1.7),
    ],
)
def test_numeric_settings_recover_and_respect_precedence(
    name, default, configured, tmp_path, monkeypatch
):
    cfg = CognitiveCastleConfig(config_dir=str(tmp_path))
    env = "CASTLE_" + name.upper()
    monkeypatch.delenv(env, raising=False)
    cfg._file_config = {name: {"invalid": "object"}}
    assert getattr(cfg, name) == default
    cfg._file_config = {name: configured}
    monkeypatch.setenv(env, "invalid-number")
    assert getattr(cfg, name) == configured
    monkeypatch.setenv(env, str(default))
    assert getattr(cfg, name) == default


@pytest.mark.parametrize(
    "name",
    ["reranker_k_interactive", "reranker_k_hook", "kg_hop_top_n", "llm_judge_top_n"],
)
def test_result_budgets_cannot_be_negative(name, tmp_path, monkeypatch):
    cfg = CognitiveCastleConfig(config_dir=str(tmp_path))
    cfg._file_config = {name: -10}
    monkeypatch.setenv("CASTLE_" + name.upper(), "-5")
    assert getattr(cfg, name) == 1
