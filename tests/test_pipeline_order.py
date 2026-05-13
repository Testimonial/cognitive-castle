"""Tests for SOAR ↔ LLM-judge composable ordering (PR #4b)."""

from __future__ import annotations

import pytest


def test_stage_4_judge_helper_exists_and_reorders(monkeypatch):
    """_stage_4_judge takes (query, reranked, cfg) and returns reordered top-N tuples."""
    from cognitive_castle.searcher import _stage_4_judge

    # Build a fake reranked list: 5 (score, row) tuples
    reranked = [
        (0.9, {"text": "doc A", "id": "a"}),
        (0.8, {"text": "doc B", "id": "b"}),
        (0.7, {"text": "doc C", "id": "c"}),
        (0.6, {"text": "doc D", "id": "d"}),
        (0.5, {"text": "doc E", "id": "e"}),
    ]

    # Fake config: top_n = 3
    class FakeCfg:
        llm_judge_top_n = 3
        llm_provider = "ollama"
        llm_model = "gemma3:4b"

    # Monkeypatch judge() to return a fixed permutation [2, 0, 1]
    import cognitive_castle.judge as judge_mod
    monkeypatch.setattr(judge_mod, "judge", lambda q, docs, cfg: [2, 0, 1])

    result = _stage_4_judge("test query", reranked, FakeCfg())
    # Top-3 reordered as [2, 0, 1] of the top-3 input
    assert len(result) == 3
    assert result[0][1]["id"] == "c"
    assert result[1][1]["id"] == "a"
    assert result[2][1]["id"] == "b"
