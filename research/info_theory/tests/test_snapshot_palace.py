import os, hashlib, json
from pathlib import Path
import pytest
from pipeline.snapshot_palace import snapshot_palace, compute_fingerprint


def test_snapshot_copies_files(tmp_path):
    src = tmp_path / "live_palace"
    dst = tmp_path / "snapshot"
    src.mkdir()
    (src / "a.lance").write_text("hello")
    (src / "b.lance").write_text("world")
    snapshot_palace(src, dst)
    assert (dst / "a.lance").read_text() == "hello"
    assert (dst / "b.lance").read_text() == "world"


def test_snapshot_refuses_to_overwrite(tmp_path):
    src = tmp_path / "live"
    dst = tmp_path / "snap"
    src.mkdir(); dst.mkdir()
    with pytest.raises(FileExistsError):
        snapshot_palace(src, dst)


def test_fingerprint_is_tuple_hash_not_value_concatenation():
    """sha256(sorted [(drawer_id, filed_at, chunk_index) tuples])
    must differ from sha256(drawer_ids + filed_ats + chunk_indexes)."""
    rows = [
        {"drawer_id": "A", "filed_at": "2026-01-01", "chunk_index": 0},
        {"drawer_id": "B", "filed_at": "2026-01-02", "chunk_index": 1},
    ]
    fp = compute_fingerprint(rows)
    rows_permuted = [
        {"drawer_id": "A", "filed_at": "2026-01-02", "chunk_index": 1},
        {"drawer_id": "B", "filed_at": "2026-01-01", "chunk_index": 0},
    ]
    fp_permuted = compute_fingerprint(rows_permuted)
    assert fp != fp_permuted, "fingerprint must bind drawer_id to its filed_at"


def test_fingerprint_is_deterministic():
    rows = [{"drawer_id": "X", "filed_at": "2026-01-01", "chunk_index": 0}]
    assert compute_fingerprint(rows) == compute_fingerprint(rows)


def test_fingerprint_is_order_independent_within_id_sort():
    rows1 = [
        {"drawer_id": "B", "filed_at": "t2", "chunk_index": 0},
        {"drawer_id": "A", "filed_at": "t1", "chunk_index": 0},
    ]
    rows2 = [
        {"drawer_id": "A", "filed_at": "t1", "chunk_index": 0},
        {"drawer_id": "B", "filed_at": "t2", "chunk_index": 0},
    ]
    assert compute_fingerprint(rows1) == compute_fingerprint(rows2)
