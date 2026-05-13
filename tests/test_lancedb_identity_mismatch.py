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
import pytest  # noqa: F401  # used in test function decorators

from cognitive_castle.backends import EmbedderIdentityMismatchError  # noqa: F401  # used in Tasks 5 & 6
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


def test_dim_mismatch_raises_with_migration_prompt(tmp_path, monkeypatch):
    """Build a 384-dim palace, then re-open with cfg.embedder_dim=1024 → raises."""
    palace_path = tmp_path / "palace"

    # Build palace at 384-dim with MiniLM identity
    _build_palace_with_identity(
        palace_path,
        monkeypatch,
        model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        dim=384,
        identity="paraphrase-ml-MiniLM-L12-v2",
    )

    # Switch cfg back to bge-m3 defaults
    monkeypatch.delenv("CASTLE_EMBEDDER_MODEL", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_DIM", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_IDENTITY", raising=False)

    cfg = CognitiveCastleConfig()
    backend = LanceDBBackend(cfg=cfg)
    with pytest.raises(EmbedderIdentityMismatchError) as exc_info:
        backend.get_collection(
            palace=_make_palace_ref(palace_path),
            collection_name="castle_drawers",
            create=False,
        )
    msg = str(exc_info.value)
    assert "castle reindex" in msg
    assert "--embedder-dim 1024" in msg
    assert "CASTLE_EMBEDDER_MODEL" in msg
    assert "paraphrase-ml-MiniLM-L12-v2" in msg  # legacy identity in opt-out block
    backend.close()


def test_matching_palace_proceeds_silently(tmp_path, monkeypatch):
    """Palace with matching dim + matching identity → __init__ + get_collection do not raise."""
    palace_path = tmp_path / "palace"

    _build_palace_with_identity(
        palace_path,
        monkeypatch,
        model="BAAI/bge-m3",
        dim=1024,
        identity="bge-m3",
    )

    # Re-open with same defaults
    monkeypatch.delenv("CASTLE_EMBEDDER_MODEL", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_DIM", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_IDENTITY", raising=False)

    cfg = CognitiveCastleConfig()
    backend = LanceDBBackend(cfg=cfg)
    collection = backend.get_collection(
        palace=_make_palace_ref(palace_path),
        collection_name="castle_drawers",
        create=False,
    )
    assert collection is not None
    backend.close()


def test_identity_mismatch_raises_when_dim_matches(tmp_path, monkeypatch):
    """Palace dim=1024 + identity 'bge-large-en-v1.5', cfg wants 'bge-m3' → raises."""
    palace_path = tmp_path / "palace"

    # Build a 1024-dim palace stamped with bge-large-en-v1.5
    _build_palace_with_identity(
        palace_path,
        monkeypatch,
        model="BAAI/bge-large-en-v1.5",
        dim=1024,
        identity="bge-large-en-v1.5",
    )

    # Switch cfg to bge-m3 defaults (same dim, different identity)
    monkeypatch.delenv("CASTLE_EMBEDDER_MODEL", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_DIM", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_IDENTITY", raising=False)

    cfg = CognitiveCastleConfig()
    backend = LanceDBBackend(cfg=cfg)
    with pytest.raises(EmbedderIdentityMismatchError) as exc_info:
        backend.get_collection(
            palace=_make_palace_ref(palace_path),
            collection_name="castle_drawers",
            create=False,
        )
    msg = str(exc_info.value)
    assert "bge-large-en-v1.5" in msg
    assert "bge-m3" in msg
    assert "CASTLE_EMBEDDER_MODEL" in msg
    backend.close()


def test_legacy_palace_grandfathers_when_dim_matches(tmp_path, monkeypatch):
    """Palace with castle_drawers but no castle_metadata → grandfather writes identity."""
    palace_path = tmp_path / "palace"

    _build_palace_with_identity(
        palace_path,
        monkeypatch,
        model="BAAI/bge-m3",
        dim=1024,
        identity="bge-m3",
    )

    # Simulate legacy: delete castle_metadata
    import lancedb

    db = lancedb.connect(str(palace_path / "lancedb"))
    db.drop_table("castle_metadata")
    assert "castle_metadata" not in db.table_names()
    del db  # close the connection so our backend gets a fresh one

    # Re-open with matching defaults
    monkeypatch.delenv("CASTLE_EMBEDDER_MODEL", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_DIM", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_IDENTITY", raising=False)

    cfg = CognitiveCastleConfig()
    backend = LanceDBBackend(cfg=cfg)
    # No exception expected; grandfather kicks in
    collection = backend.get_collection(
        palace=_make_palace_ref(palace_path),
        collection_name="castle_drawers",
        create=False,
    )
    assert collection is not None
    backend.close()

    # Verify castle_metadata now exists with bge-m3 (use pyarrow, not pandas)
    import pyarrow.compute as pc

    db = lancedb.connect(str(palace_path / "lancedb"))
    assert "castle_metadata" in db.table_names()
    arrow_table = db.open_table("castle_metadata").to_arrow()
    mask = pc.equal(arrow_table["key"], "embedder_identity")
    matched = arrow_table.filter(mask)
    assert matched.num_rows > 0
    assert matched.column("value").to_pylist()[0] == "bge-m3"


def test_legacy_palace_raises_when_dim_mismatches(tmp_path, monkeypatch):
    """Legacy palace (no manifest) with dim=384, cfg.embedder_dim=1024 → raise immediately."""
    palace_path = tmp_path / "palace"

    _build_palace_with_identity(
        palace_path,
        monkeypatch,
        model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        dim=384,
        identity="paraphrase-ml-MiniLM-L12-v2",
    )

    # Simulate legacy: delete castle_metadata
    import lancedb

    db = lancedb.connect(str(palace_path / "lancedb"))
    db.drop_table("castle_metadata")
    del db

    # Re-open with bge-m3 defaults (dim=1024 conflicts with palace dim=384)
    monkeypatch.delenv("CASTLE_EMBEDDER_MODEL", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_DIM", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_IDENTITY", raising=False)

    cfg = CognitiveCastleConfig()
    backend = LanceDBBackend(cfg=cfg)
    with pytest.raises(EmbedderIdentityMismatchError):
        backend.get_collection(
            palace=_make_palace_ref(palace_path),
            collection_name="castle_drawers",
            create=False,
        )

    # Verify NO grandfather happened (castle_metadata still missing)
    db = lancedb.connect(str(palace_path / "lancedb"))
    assert "castle_metadata" not in db.table_names()
    backend.close()


def _grandfather_worker(palace_path_str, result_queue):
    """Worker process: opens a backend against the palace, captures result/exception."""
    try:
        from cognitive_castle.backends.lancedb_backend import LanceDBBackend
        from cognitive_castle.backends.base import PalaceRef
        from cognitive_castle.config import CognitiveCastleConfig

        cfg = CognitiveCastleConfig()
        backend = LanceDBBackend(cfg=cfg)
        backend.get_collection(
            palace=PalaceRef(id=palace_path_str, local_path=palace_path_str),
            collection_name="castle_drawers",
            create=False,
        )
        backend.close()
        result_queue.put(("ok", None))
    except Exception as e:
        result_queue.put(("error", f"{type(e).__name__}: {e}"))


def test_concurrent_grandfather_is_race_safe(tmp_path, monkeypatch):
    """Two simultaneous backend inits on a legacy palace both succeed."""
    palace_path = tmp_path / "palace"

    _build_palace_with_identity(
        palace_path,
        monkeypatch,
        model="BAAI/bge-m3",
        dim=1024,
        identity="bge-m3",
    )

    # Simulate legacy: delete castle_metadata
    import lancedb

    db = lancedb.connect(str(palace_path / "lancedb"))
    db.drop_table("castle_metadata")
    del db

    # Important: subprocess inherits parent env — clear overrides so workers
    # see the bge-m3 defaults.
    monkeypatch.delenv("CASTLE_EMBEDDER_MODEL", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_DIM", raising=False)
    monkeypatch.delenv("CASTLE_EMBEDDER_IDENTITY", raising=False)

    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    p1 = ctx.Process(target=_grandfather_worker, args=(str(palace_path), result_queue))
    p2 = ctx.Process(target=_grandfather_worker, args=(str(palace_path), result_queue))
    p1.start()
    p2.start()
    p1.join(timeout=30)
    p2.join(timeout=30)

    results = [result_queue.get(timeout=5) for _ in range(2)]
    statuses = [r[0] for r in results]
    errors = [r[1] for r in results if r[0] == "error"]
    assert statuses.count("ok") == 2, f"Expected both workers to succeed; got errors: {errors}"

    # Final state: castle_metadata exists with at least one embedder_identity row
    # (use pyarrow.compute — pandas not installed)
    import pyarrow.compute as pc

    db = lancedb.connect(str(palace_path / "lancedb"))
    assert "castle_metadata" in db.table_names()
    arrow_table = db.open_table("castle_metadata").to_arrow()
    mask = pc.equal(arrow_table["key"], "embedder_identity")
    matched = arrow_table.filter(mask)
    assert matched.num_rows >= 1
    assert matched.column("value").to_pylist()[0] == "bge-m3"
