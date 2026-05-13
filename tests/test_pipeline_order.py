"""Tests for SOAR ↔ LLM-judge composable ordering (PR #4b)."""

from __future__ import annotations


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

    def stub_stage_5(reranked, cfg, query=""):
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

    searcher_mod.search_memories(
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

    def fake_stage_5(reranked, cfg, query=""):
        call_order.append("stage_5")
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_4_judge", fake_stage_4)
    monkeypatch.setattr(searcher_mod, "_stage_5_soar", fake_stage_5)

    from cognitive_castle.searcher import _apply_stages_4_and_5

    reranked = [(0.9, {"id": "a", "score": 0.9})]
    cfg_obj = type(
        "C",
        (),
        {
            "llm_judge_top_n": 5,
            "soar_enabled": True,
            "soar_rules_path": None,
            "palace_path": str(tmp_path),
        },
    )()

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
        searcher_mod, "_stage_5_soar", lambda r, c, query="": call_order.append("stage_5") or r
    )

    from cognitive_castle.searcher import _apply_stages_4_and_5

    cfg_obj = type(
        "C",
        (),
        {
            "llm_judge_top_n": 5,
            "soar_enabled": True,
            "soar_rules_path": None,
            "palace_path": str(tmp_path),
        },
    )()

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
        searcher_mod, "_stage_5_soar", lambda r, c, query="": call_order.append("stage_5") or r
    )

    from cognitive_castle.searcher import _apply_stages_4_and_5

    cfg_obj = type(
        "C",
        (),
        {
            "llm_judge_top_n": 5,
            "soar_enabled": True,
            "soar_rules_path": None,
            "palace_path": str(tmp_path),
        },
    )()

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
        searcher_mod, "_stage_5_soar", lambda r, c, query="": call_order.append("stage_5") or r
    )

    from cognitive_castle.searcher import _apply_stages_4_and_5

    cfg_obj = type(
        "C",
        (),
        {
            "llm_judge_top_n": 5,
            "soar_enabled": True,
            "soar_rules_path": None,
            "palace_path": str(tmp_path),
        },
    )()

    _apply_stages_4_and_5(
        query="q",
        reranked=[(0.9, {"id": "a", "score": 0.9})],
        cfg=cfg_obj,
        llm_rerank=True,
        soar_boost=False,
        soar_first=False,
    )
    assert call_order == ["stage_4"]


def test_entity_match_flag_attaches_to_kg_hop_rows(monkeypatch, tmp_path):
    """In _new_pipeline_search, KG-hop hits get row['entity_match']=True; non-KG hits get False.

    Strategy: stub the recall paths (dense/sparse/kg) so we control which signals fire for
    which ids. Stub col.get_by_ids to return matching row dicts. Run _new_pipeline_search.
    Inspect the final hit dicts.
    """
    import cognitive_castle.searcher as searcher_mod

    class FakeCollection:
        def vector_search(self, query_vec, n_results, where=None):
            return [
                {
                    "id": "dense-only",
                    "wing": "x",
                    "room": "r",
                    "source_file": "f.md",
                    "text": "dense",
                }
            ]

        def fts_search(self, query, n_results, where=None):
            return []

        def get_by_ids(self, ids):
            id_to_row = {
                "kg-hit": {
                    "id": "kg-hit",
                    "wing": "x",
                    "room": "r",
                    "source_file": "f.md",
                    "text": "kg hit",
                    "decay_score": 1.0,
                    "chunk_index": 0,
                    "metadata_json": "{}",
                },
                "dense-only": {
                    "id": "dense-only",
                    "wing": "x",
                    "room": "r",
                    "source_file": "f.md",
                    "text": "dense only",
                    "decay_score": 1.0,
                    "chunk_index": 0,
                    "metadata_json": "{}",
                },
            }
            return [id_to_row[i] for i in ids if i in id_to_row]

    # Stub get_collection used inside _new_pipeline_search
    monkeypatch.setattr(
        "cognitive_castle.palace.get_collection",
        lambda *a, **kw: FakeCollection(),
    )

    # Stub the embedder to skip model loads
    monkeypatch.setattr(
        "cognitive_castle.embedding.embed_texts",
        lambda texts: [[0.0] * 384 for _ in texts],
    )

    # Create sentinel files so the KG-hop block is entered
    (tmp_path / "entity_registry.json").write_text("{}")
    (tmp_path / "knowledge_graph.sqlite3").write_bytes(b"")

    # Stub the KG-hop path to return "kg-hit" only.
    # lookup_in_text must return objects with .entity_id (production code does
    # [m.entity_id for m in matches]), so we use a simple namespace object.
    import types
    import cognitive_castle.knowledge_graph as kg_mod

    monkeypatch.setattr(
        kg_mod.KnowledgeGraph,
        "find_drawers_by_entities",
        lambda self, entities, **kwargs: ["kg-hit"],
    )
    monkeypatch.setattr(
        "cognitive_castle.entity_registry.EntityRegistry.lookup_in_text",
        lambda self, text, **kwargs: [types.SimpleNamespace(entity_id="entity-1")],
    )

    # Stub cross-encoder rerank to preserve input order
    monkeypatch.setattr(
        "cognitive_castle.reranker.rerank",
        lambda query, docs, cfg: [1.0 - i * 0.1 for i in range(len(docs))],
    )

    from cognitive_castle.config import CognitiveCastleConfig

    cfg = CognitiveCastleConfig()

    result = searcher_mod._new_pipeline_search(
        query="test",
        palace_path=str(tmp_path),
        wing=None,
        room=None,
        n_results=10,
        cfg=cfg,
    )

    by_id = {hit["id"]: hit for hit in result}
    assert "kg-hit" in by_id, f"Expected kg-hit in results, got ids: {list(by_id)}"
    assert "dense-only" in by_id, f"Expected dense-only in results, got ids: {list(by_id)}"
    assert by_id["kg-hit"]["entity_match"] is True, (
        "kg-hit came via KG-hop; entity_match should be True"
    )
    assert by_id["dense-only"]["entity_match"] is False, (
        "dense-only came via dense vector search only; entity_match should be False"
    )


def test_query_threaded_through_to_stage_5_soar(monkeypatch, tmp_path):
    """When _new_pipeline_search is called with a query and soar_boost=True,
    _stage_5_soar receives the query via kwarg.

    Verifies the plumbing in _apply_stages_4_and_5 passes query=query to
    both _stage_5_soar call sites (default-order branch + soar_first branch).
    """
    import cognitive_castle.searcher as searcher_mod

    captured: dict = {}

    def stub_stage_5(reranked, cfg, query=""):
        captured["query"] = query
        captured["reranked"] = reranked
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_5_soar", stub_stage_5)

    # Drive _apply_stages_4_and_5 directly with a known query
    cfg_obj = type(
        "C",
        (),
        {
            "llm_judge_top_n": 5,
            "soar_enabled": True,
            "soar_rules_path": None,
            "palace_path": str(tmp_path),
        },
    )()

    reranked = [(0.9, {"id": "a", "score": 0.9})]
    searcher_mod._apply_stages_4_and_5(
        query="what did we decide about caching",
        reranked=reranked,
        cfg=cfg_obj,
        llm_rerank=False,
        soar_boost=True,
        soar_first=False,
    )

    assert captured.get("query") == "what did we decide about caching", (
        f"Expected query forwarded to _stage_5_soar; got {captured.get('query')!r}"
    )


def test_query_threaded_through_soar_first_branch(monkeypatch, tmp_path):
    """Same as above but exercises the soar_first=True branch."""
    import cognitive_castle.searcher as searcher_mod

    captured: dict = {}

    def stub_stage_5(reranked, cfg, query=""):
        captured["query"] = query
        return reranked

    def stub_stage_4(query, reranked, cfg):
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_5_soar", stub_stage_5)
    monkeypatch.setattr(searcher_mod, "_stage_4_judge", stub_stage_4)

    cfg_obj = type(
        "C",
        (),
        {
            "llm_judge_top_n": 5,
            "soar_enabled": True,
            "soar_rules_path": None,
            "palace_path": str(tmp_path),
        },
    )()

    searcher_mod._apply_stages_4_and_5(
        query="when did we ship the migration",
        reranked=[(0.9, {"id": "a", "score": 0.9})],
        cfg=cfg_obj,
        llm_rerank=True,
        soar_boost=True,
        soar_first=True,
    )

    assert captured.get("query") == "when did we ship the migration", (
        f"Expected query forwarded to _stage_5_soar in soar_first branch; got {captured.get('query')!r}"
    )
