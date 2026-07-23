from unittest.mock import patch, MagicMock
import numpy as np
import pyarrow as pa
from pipeline.embed import embed_drawers, _fingerprint_inputs


def _mock_embedder(dim=1024):
    e = MagicMock()
    # side_effect keeps `e.encode` a MagicMock (so .call_count works) while
    # still returning per-batch vectors. Assigning a bare lambda to .encode
    # would clobber the Mock and drop call tracking.
    e.encode.side_effect = lambda texts, **kw: np.random.rand(len(texts), dim).astype(np.float32)
    e.model_revision = "bge-m3@abc123"
    return e


def test_embed_adds_vector_column():
    table = pa.table({"drawer_id": ["a", "b"], "text": ["x", "y"]})
    with patch("pipeline.embed.get_embedder", return_value=_mock_embedder()):
        out = embed_drawers(table)
    assert "vector" in out.column_names
    assert out.num_rows == 2


def test_embed_caches_by_input_fingerprint(tmp_path):
    table = pa.table({"drawer_id": ["a"], "text": ["x"]})
    cache = tmp_path / "embeddings.parquet"
    with patch("pipeline.embed.get_embedder", return_value=_mock_embedder()) as m:
        embed_drawers(table, cache_path=cache)
        embed_drawers(table, cache_path=cache)
    # Second call hits cache; encode invoked only once
    assert m.return_value.encode.call_count == 1


def test_fingerprint_inputs_changes_when_text_changes():
    t1 = pa.table({"drawer_id": ["a"], "text": ["x"]})
    t2 = pa.table({"drawer_id": ["a"], "text": ["y"]})
    assert _fingerprint_inputs(t1) != _fingerprint_inputs(t2)
