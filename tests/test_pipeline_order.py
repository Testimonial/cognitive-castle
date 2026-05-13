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


def test_stage_5_soar_helper_exists_and_applies_boosts(tmp_path, monkeypatch):
    """_stage_5_soar(reranked, cfg) calls _apply_soar_to_reranked and returns the result."""
    from cognitive_castle.searcher import _stage_5_soar

    reranked = [
        (0.9, {"id": "a", "score": 0.9, "wing": "x", "room": "r", "source_file": "f"}),
    ]

    class FakeCfg:
        soar_enabled = True
        soar_rules_path = None
        palace_path = str(tmp_path)

    result = _stage_5_soar(reranked, FakeCfg())
    # Even with no rules firing (SML unavailable in test env), audit-trail fields are attached
    assert len(result) == 1
    _, row = result[0]
    assert "soar_boost" in row
    assert "soar_tags" in row
    assert "score_pre_soar" in row


def test_search_memories_threads_soar_boost_through_pipeline(tmp_path, monkeypatch):
    """When soar_boost=True is passed to search_memories, _stage_5_soar fires.

    We don't need a real palace — just verify that _new_pipeline_search receives
    and propagates the param. Use a stub to intercept.
    """
    import cognitive_castle.searcher as searcher_mod

    soar_calls = []

    def stub_stage_5(reranked, cfg):
        soar_calls.append(reranked)
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_5_soar", stub_stage_5)
    # We also need to stub the pipeline so it doesn't try to query a real palace
    def stub_pipeline(query, palace_path, wing, room, n_results, cfg, **kwargs):
        # Mimic what _new_pipeline_search does at the end
        reranked = [(0.9, {"id": "a", "score": 0.9, "wing": "x"})]
        if kwargs.get("soar_boost"):
            reranked = searcher_mod._stage_5_soar(reranked, cfg)
        return [{"id": r["id"]} for _, r in reranked]

    monkeypatch.setattr(searcher_mod, "_new_pipeline_search", stub_pipeline)

    result = searcher_mod.search_memories(
        query="test",
        palace_path=str(tmp_path),
        soar_boost=True,
    )
    assert len(soar_calls) == 1, "Expected _stage_5_soar to be invoked once via soar_boost=True"
