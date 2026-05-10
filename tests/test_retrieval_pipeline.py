"""End-to-end test of the new 3-stage retrieval pipeline."""
import time
from unittest.mock import patch

from cognitive_castle.searcher import search_memories


def _seed(palace_path: str, drawers: list):
    """drawers is a list of (id, document, metadata) tuples."""
    from cognitive_castle.palace import get_collection

    col = get_collection(palace_path, collection_name="castle_drawers", create=True)
    for did, doc, md in drawers:
        col.add(documents=[doc], ids=[did], metadatas=[md])


def test_pipeline_returns_results_when_flag_enabled(tmp_path, monkeypatch):
    """With use_new_retrieval_pipeline=True, searcher routes to the new pipeline
    and returns results."""
    palace = str(tmp_path / "palace")
    now = str(int(time.time()))
    _seed(palace, [
        ("d1", "JWT authentication for the API", {"wing": "auth", "room": "2026", "ts": now}),
        ("d2", "the quick brown fox jumps over the lazy dog", {"wing": "misc", "room": "2026", "ts": now}),
    ])
    # Stub the reranker so we don't need to download bge-reranker-base in tests.
    monkeypatch.setenv("CASTLE_USE_NEW_RETRIEVAL_PIPELINE", "true")
    with patch(
        "cognitive_castle.reranker.rerank",
        side_effect=lambda q, c, **kw: [1.0 - i * 0.1 for i, _ in enumerate(c)],
    ):
        results = search_memories("authentication", palace, n_results=5)
    assert isinstance(results, list)
    assert len(results) >= 1


def test_pipeline_disabled_falls_back_to_old_path(tmp_path, monkeypatch):
    """With use_new_retrieval_pipeline=False (default), the old code path runs."""
    palace = str(tmp_path / "palace")
    now = str(int(time.time()))
    _seed(palace, [("d1", "test document", {"wing": "x", "room": "y", "ts": now})])
    monkeypatch.setenv("CASTLE_USE_NEW_RETRIEVAL_PIPELINE", "false")
    results = search_memories("test", palace, n_results=5)
    assert isinstance(results, dict)  # old path returns a dict with "results" key
    assert "results" in results
