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


def test_default_path_runs_judge_then_soar(monkeypatch, tmp_path):
    """Default order: Stage 4 (judge) fires before Stage 5 (SOAR)."""
    import cognitive_castle.searcher as searcher_mod

    call_order = []

    def fake_stage_4(query, reranked, cfg):
        call_order.append("stage_4")
        return reranked

    def fake_stage_5(reranked, cfg):
        call_order.append("stage_5")
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_4_judge", fake_stage_4)
    monkeypatch.setattr(searcher_mod, "_stage_5_soar", fake_stage_5)

    from cognitive_castle.searcher import _apply_stages_4_and_5

    reranked = [(0.9, {"id": "a", "score": 0.9})]
    cfg_obj = type("C", (), {"llm_judge_top_n": 5, "soar_enabled": True, "soar_rules_path": None, "palace_path": str(tmp_path)})()

    _apply_stages_4_and_5(
        query="q",
        reranked=reranked,
        cfg=cfg_obj,
        llm_rerank=True,
        soar_boost=True,
        soar_first=False,
    )
    assert call_order == ["stage_4", "stage_5"]


def test_soar_first_runs_soar_then_judge(monkeypatch, tmp_path):
    """soar_first=True: Stage 5 fires before Stage 4."""
    import cognitive_castle.searcher as searcher_mod

    call_order = []
    monkeypatch.setattr(
        searcher_mod, "_stage_4_judge", lambda q, r, c: call_order.append("stage_4") or r
    )
    monkeypatch.setattr(
        searcher_mod, "_stage_5_soar", lambda r, c: call_order.append("stage_5") or r
    )

    from cognitive_castle.searcher import _apply_stages_4_and_5
    cfg_obj = type("C", (), {"llm_judge_top_n": 5, "soar_enabled": True, "soar_rules_path": None, "palace_path": str(tmp_path)})()

    _apply_stages_4_and_5(
        query="q",
        reranked=[(0.9, {"id": "a", "score": 0.9})],
        cfg=cfg_obj,
        llm_rerank=True,
        soar_boost=True,
        soar_first=True,
    )
    assert call_order == ["stage_5", "stage_4"]


def test_soar_only_no_judge_call(monkeypatch, tmp_path):
    """llm_rerank=False, soar_boost=True: only Stage 5 fires, no Stage 4."""
    import cognitive_castle.searcher as searcher_mod

    call_order = []
    monkeypatch.setattr(
        searcher_mod, "_stage_4_judge", lambda q, r, c: call_order.append("stage_4") or r
    )
    monkeypatch.setattr(
        searcher_mod, "_stage_5_soar", lambda r, c: call_order.append("stage_5") or r
    )

    from cognitive_castle.searcher import _apply_stages_4_and_5
    cfg_obj = type("C", (), {"llm_judge_top_n": 5, "soar_enabled": True, "soar_rules_path": None, "palace_path": str(tmp_path)})()

    _apply_stages_4_and_5(
        query="q",
        reranked=[(0.9, {"id": "a", "score": 0.9})],
        cfg=cfg_obj,
        llm_rerank=False,
        soar_boost=True,
        soar_first=False,
    )
    assert call_order == ["stage_5"]


def test_judge_only_no_soar_call(monkeypatch, tmp_path):
    """llm_rerank=True, soar_boost=False: only Stage 4 fires, no Stage 5."""
    import cognitive_castle.searcher as searcher_mod

    call_order = []
    monkeypatch.setattr(
        searcher_mod, "_stage_4_judge", lambda q, r, c: call_order.append("stage_4") or r
    )
    monkeypatch.setattr(
        searcher_mod, "_stage_5_soar", lambda r, c: call_order.append("stage_5") or r
    )

    from cognitive_castle.searcher import _apply_stages_4_and_5
    cfg_obj = type("C", (), {"llm_judge_top_n": 5, "soar_enabled": True, "soar_rules_path": None, "palace_path": str(tmp_path)})()

    _apply_stages_4_and_5(
        query="q",
        reranked=[(0.9, {"id": "a", "score": 0.9})],
        cfg=cfg_obj,
        llm_rerank=True,
        soar_boost=False,
        soar_first=False,
    )
    assert call_order == ["stage_4"]
