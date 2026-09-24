"""Regression coverage for lossless ingest, retries, and scoped retrieval.

Use real LanceDB/SQLite storage with deterministic embeddings; no model or
service is needed to exercise persistence and retrieval boundaries.
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import lancedb
import pytest

from cognitive_castle import convo_miner, miner
from cognitive_castle.backends.lancedb_backend import LanceCollection, _build_schema
from cognitive_castle.config import CognitiveCastleConfig
from cognitive_castle.palace import file_already_mined
from cognitive_castle.kg_enricher import enrich_palace as real_enrich_palace


@pytest.fixture
def store(tmp_path, monkeypatch):
    cfg = SimpleNamespace(embedder_dim=4)
    db = lancedb.connect(str(tmp_path / "db"))
    col = LanceCollection(db.create_table("drawers", schema=_build_schema(cfg)), cfg)
    monkeypatch.setattr(
        "cognitive_castle.embedding.embed_texts",
        lambda texts: [[1.0, 0.0, 0.0, 0.0] for _ in texts],
    )
    monkeypatch.setattr(miner, "_extract_entities_for_metadata", lambda text: "")
    monkeypatch.setattr(miner, "compute_novelty", lambda *args, **kwargs: None)
    monkeypatch.setattr("cognitive_castle.kg_enricher.enrich_palace", lambda *args: {})
    monkeypatch.setattr(convo_miner, "get_collection", lambda *args: col)
    return col


@pytest.mark.parametrize(
    "text",
    [
        "> Datum: 17. 9.\nOK.\n> Projekt: Atlas.\nOK.\n> Heslo: lev.\nOK.",
        "  preamble\r\n> question\r\ndef foo():\r\n    return 42\r\n---\r\nkeep this too\r\n",
        "x" * 801 + "\n\n\tshort tail  ",
        "\n\t ",
    ],
)
def test_chunks_reconstruct_exact_source(text):
    for chunks in (convo_miner.chunk_exchanges(text), miner.chunk_text(text, "f")):
        assert "".join(c["content"] for c in chunks) == text
        assert all(0 < len(c["content"]) <= 800 for c in chunks)


def test_normalization_preserves_user_spelling_and_whitespace(tmp_path, monkeypatch):
    from cognitive_castle.normalize import normalize

    correct = Mock(side_effect=AssertionError("ingest must not spellcheck source text"))
    monkeypatch.setattr("cognitive_castle.spellcheck.spellcheck_user_text", correct)
    text = "  teh original\n    indented\n<system-reminder>literal user example</system-reminder>\n"
    path = tmp_path / "session.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"type": "user", "message": {"content": text}},
                {"type": "assistant", "message": {"content": "  answer\n"}},
            ]
        )
    )
    normalized = normalize(str(path))
    assert text in normalized
    assert "  answer\n" in normalized
    correct.assert_not_called()
    assert "".join(c["content"] for c in convo_miner.chunk_exchanges(normalized)) == normalized


@pytest.mark.parametrize("kind", ["project", "convos"])
def test_failed_revision_keeps_history_and_retries_all_batches(store, tmp_path, monkeypatch, kind):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "chat.txt"
    source.write_text("Original precise words.\n")
    monkeypatch.setattr(miner, "DRAWER_UPSERT_BATCH_SIZE", 1)
    monkeypatch.setattr(convo_miner, "DRAWER_UPSERT_BATCH_SIZE", 1)

    def ingest():
        if kind == "project":
            miner.process_file(source, source_dir, store, "w", [], "test", False)
        else:
            convo_miner.mine_convos(str(source_dir), str(tmp_path / "palace"), wing="w")

    ingest()
    old = store.get()
    source.write_text("New revision " * 200 + " LAST WORDS")
    write = store.upsert
    calls = 0

    def fail_second(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated storage failure")
        write(**kwargs)

    monkeypatch.setattr(store, "upsert", fail_second)
    with pytest.raises(OSError, match="storage failure"):
        ingest()
    assert store.get(ids=old.ids).documents == old.documents
    assert not file_already_mined(store, str(source), check_mtime=True)
    monkeypatch.setattr(store, "upsert", write)
    ingest()
    assert file_already_mined(store, str(source), check_mtime=True)
    assert store.get(ids=old.ids).documents == old.documents
    rows = store.get()
    new = sorted(
        (m["chunk_index"], d)
        for i, d, m in zip(rows.ids, rows.documents, rows.metadatas)
        if i not in old.ids
    )
    assert "".join(d for _, d in new) == source.read_text()
    before = store.count()
    ingest()
    assert store.count() == before


def test_growing_transcript_and_empty_file_are_revisited(store, tmp_path):
    directory = tmp_path / "source"
    directory.mkdir()
    path = directory / "session.txt"
    path.write_text("")
    for text in ("", "> First.\nOK.\n", "> First.\nOK.\n> New memory.\nYes.\n"):
        path.write_text(text)
        convo_miner.mine_convos(str(directory), str(tmp_path / "palace"), wing="w")
        assert file_already_mined(store, str(path), check_mtime=True)
    assert any("New memory." in doc for doc in store.get().documents)


def test_update_reembeds_content_but_not_metadata(store, monkeypatch):
    store.add(ids=["a"], documents=["old"], embeddings=[[1.0, 0.0, 0.0, 0.0]])
    embed = Mock(return_value=[[0.0, 1.0, 0.0, 0.0]])
    monkeypatch.setattr("cognitive_castle.embedding.embed_texts", embed)
    store.update(ids=["a"], documents=["new"])
    embed.assert_called_once_with(["new"])
    assert store.get(ids=["a"], include=["embeddings"]).embeddings == [[0.0, 1.0, 0.0, 0.0]]
    embed.reset_mock()
    store.update(ids=["a"], metadatas=[{"room": "r"}])
    embed.assert_not_called()


def test_fulltext_filters_before_candidate_limit(store):
    store.add(
        ids=["outside", "inside"],
        documents=["needle needle", "needle"],
        metadatas=[{"wing": "other", "room": "r"}, {"wing": "w", "room": "r"}],
    )
    store._ensure_fts_index(replace=True)
    assert [r["id"] for r in store.fts_search("needle", n_results=1, where="wing = 'w'")] == [
        "inside"
    ]


def test_search_rejects_out_of_scope_recall_rows(store, tmp_path, monkeypatch):
    from cognitive_castle.searcher import _new_pipeline_search

    store.add(
        ids=["outside", "inside"],
        documents=["needle", "needle"],
        metadatas=[{"wing": "other", "room": "r"}, {"wing": "w", "room": "r"}],
    )
    monkeypatch.setattr("cognitive_castle.palace.get_collection", lambda *a, **k: store)
    monkeypatch.setattr(
        store, "fts_search", lambda *a, **k: store.get_by_ids(["outside", "inside"])
    )
    monkeypatch.setattr("cognitive_castle.reranker.rerank", lambda q, docs, **kw: [1.0] * len(docs))
    cfg = CognitiveCastleConfig(config_dir=tmp_path)
    result = _new_pipeline_search("needle", str(tmp_path / "palace"), "w", "r", 5, cfg, mode="fast")
    assert [r["id"] for r in result] == ["inside"]


def test_enrichment_graph_is_used_by_scoped_search(store, tmp_path, monkeypatch):
    from collections import Counter
    from cognitive_castle import kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry
    from cognitive_castle.searcher import _new_pipeline_search

    store.add(
        ids=["a-outside", "z-inside"],
        documents=["Alice", "Alice"],
        metadatas=[{"wing": "other"}, {"wing": "w", "room": "r"}],
    )
    registry = EntityRegistry.load(tmp_path)
    registry._data["people"]["Alice"] = {
        "aliases": [],
        "confidence": 1.0,
        "source": "test",
        "contexts": [],
        "relationship": "",
    }
    registry.save()
    monkeypatch.setattr("cognitive_castle.palace.get_collection", lambda *a, **k: store)
    monkeypatch.setattr(
        kg_enricher,
        "_walk_corpus",
        lambda *a, **k: ({"Alice": {"a-outside", "z-inside"}}, Counter({"Alice": 2})),
    )
    monkeypatch.setattr(kg_enricher, "_classify_and_promote", lambda **kw: [])
    cfg = CognitiveCastleConfig(config_dir=tmp_path)
    cfg._file_config["kg_hop_top_n"] = 1
    palace_path = str(tmp_path / "palace")
    real_enrich_palace(palace_path, cfg)
    assert (tmp_path / "knowledge_graph.sqlite3").exists()
    monkeypatch.setattr(store, "vector_search", lambda *a, **k: [])
    monkeypatch.setattr(store, "fts_search", lambda *a, **k: [])
    monkeypatch.setattr("cognitive_castle.reranker.rerank", lambda q, docs, **kw: [1.0] * len(docs))
    result = _new_pipeline_search("Alice", palace_path, "w", "r", 5, cfg, mode="fast")
    assert [r["id"] for r in result] == ["z-inside"]
    assert result[0]["entity_match"] is True
