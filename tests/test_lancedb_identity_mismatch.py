"""Tests for embedder-identity check + EmbedderIdentityMismatchError wiring.

Covers the LanceDB backend's per-palace identity verification:
- Fresh palace stamps castle_metadata with cfg.embedder_identity on first write
- Dim mismatch → EmbedderIdentityMismatchError (cheap layer-1 check)
- Identity mismatch → EmbedderIdentityMismatchError (layer-2 read from castle_metadata)
- Legacy palace (drawers without metadata) → grandfather if dim matches, raise otherwise
- Race-safe grandfather when two processes contend
- Matching palace → silent pass
"""

from __future__ import annotations

import multiprocessing
import pytest

from cognitive_castle.backends import EmbedderIdentityMismatchError
from cognitive_castle.backends.base import PalaceRef
from cognitive_castle.backends.lancedb_backend import LanceDBBackend
from cognitive_castle.config import CognitiveCastleConfig


def _make_palace_ref(palace_path):
    p = str(palace_path)
    return PalaceRef(id=p, local_path=p)


def _build_palace_with_identity(palace_path, monkeypatch, *, model, dim, identity):
    """Helper: build a fresh palace at palace_path with the given embedder config."""
    monkeypatch.setenv("CASTLE_EMBEDDER_MODEL", model)
    monkeypatch.setenv("CASTLE_EMBEDDER_DIM", str(dim))
    monkeypatch.setenv("CASTLE_EMBEDDER_IDENTITY", identity)
    cfg = CognitiveCastleConfig()
    backend = LanceDBBackend(cfg=cfg)
    collection = backend.get_collection(
        palace=_make_palace_ref(palace_path),
        collection_name="castle_drawers",
        create=True,
    )
    # First add() materializes castle_drawers + castle_metadata
    collection.add(
        documents=["seed doc"],
        ids=["seed-1"],
        embeddings=[[0.1] * dim],
    )
    backend.close()


def test_fresh_palace_writes_identity_on_first_add(tmp_path, monkeypatch):
    """Empty palace + first add() creates castle_metadata + writes embedder_identity."""
    _build_palace_with_identity(
        tmp_path / "palace",
        monkeypatch,
        model="BAAI/bge-m3",
        dim=1024,
        identity="bge-m3",
    )

    # Verify castle_metadata table exists with the right row
    import lancedb
    import pyarrow.compute as pc

    db = lancedb.connect(str(tmp_path / "palace" / "lancedb"))
    assert "castle_metadata" in db.table_names()
    table = db.open_table("castle_metadata")
    arrow_table = table.to_arrow()
    mask = pc.equal(arrow_table["key"], "embedder_identity")
    matched = arrow_table.filter(mask)
    assert matched.num_rows > 0, "embedder_identity row not found in castle_metadata"
    assert matched.column("value").to_pylist()[0] == "bge-m3"
