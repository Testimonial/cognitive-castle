import pytest

from cognitive_castle.backends import (
    GetResult,
    QueryResult,
    get_backend,
)


def test_query_result_empty_preserves_outer_dimension():
    empty = QueryResult.empty(num_queries=2)
    assert empty.ids == [[], []]
    assert empty.documents == [[], []]
    assert empty.distances == [[], []]
    assert empty.embeddings is None


def test_typed_results_support_dict_compat_access():
    """Transitional compat shim per base.py — retained until callers migrate to attrs."""
    result = GetResult(ids=["a"], documents=["da"], metadatas=[{"w": 1}])
    assert result["ids"] == ["a"]
    assert result.get("documents") == ["da"]
    assert result.get("missing", "default") == "default"
    assert "ids" in result
    assert "missing" not in result


def test_registry_unknown_backend_raises():
    with pytest.raises(KeyError):
        get_backend("no-such-backend-exists")


def test_resolve_backend_priority_order(tmp_path):
    from cognitive_castle.backends import resolve_backend_for_palace

    # explicit kwarg wins over everything
    assert resolve_backend_for_palace(explicit="pg", config_value="lance") == "pg"
    # config value wins over env / default
    assert resolve_backend_for_palace(config_value="lance", env_value="qdrant") == "lance"
    # env wins over default
    assert resolve_backend_for_palace(env_value="qdrant", default="lancedb") == "qdrant"


def test_lancedb_schema_uses_config_dim(tmp_path):
    """Schema dim is sourced from config.embedder_dim, not a hardcoded constant."""
    from unittest.mock import MagicMock
    from cognitive_castle.backends.lancedb_backend import _build_schema

    cfg_384 = MagicMock()
    cfg_384.embedder_dim = 384
    schema_384 = _build_schema(cfg_384)
    vector_field_384 = next(f for f in schema_384 if f.name == "vector")
    # pyarrow's list_ field has list_size accessible via .type.list_size
    assert vector_field_384.type.list_size == 384

    cfg_1024 = MagicMock()
    cfg_1024.embedder_dim = 1024
    schema_1024 = _build_schema(cfg_1024)
    vector_field_1024 = next(f for f in schema_1024 if f.name == "vector")
    assert vector_field_1024.type.list_size == 1024


def test_fts_index_is_created_alongside_vector(tmp_path):
    """When a backend creates a new collection, an FTS index on the text column is built."""
    from cognitive_castle.backends.lancedb_backend import LanceDBBackend, PalaceRef

    backend = LanceDBBackend()
    palace = PalaceRef(id="test", local_path=str(tmp_path / "palace"))
    col = backend.get_collection(
        palace=palace,
        collection_name="drawers",
        create=True,
    )
    # Add a row so we have something to search.
    col.add(
        documents=["the quick brown fox jumps over the lazy dog"],
        ids=["d1"],
        metadatas=[{"wing": "test", "room": "test", "ts": "2026-05-10"}],
    )
    # Refresh FTS index after adding data (create_fts_index with replace=True).
    col._ensure_fts_index(replace=True)
    # FTS should find the row by a keyword in the document.
    results = col.fts_search("brown fox", n_results=5)
    assert len(results) >= 1
    # Result row format: at minimum should have an id and the query terms in the text.
    first = results[0]
    # Be liberal in what we accept — the row may have keys "id", "ids", or be a (id, doc) tuple.
    if isinstance(first, dict):
        assert any(v == "d1" for v in first.values())
    else:
        assert "d1" in str(first)
