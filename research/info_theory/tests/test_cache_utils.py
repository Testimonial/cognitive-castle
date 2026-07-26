import pyarrow as pa
from pipeline.cache_utils import fingerprint_inputs, read_cached, write_cached


def test_fingerprint_is_deterministic():
    items = [("a", 1), ("b", 2)]
    assert fingerprint_inputs(items) == fingerprint_inputs(items)


def test_fingerprint_changes_with_input():
    assert fingerprint_inputs([("a", 1)]) != fingerprint_inputs([("a", 2)])


def test_write_then_read_roundtrip(tmp_path):
    table = pa.table({"x": [1, 2, 3]})
    fp = "abc123"
    write_cached(table, tmp_path / "t.parquet", fp)
    cached = read_cached(tmp_path / "t.parquet", expected_fingerprint=fp)
    assert cached is not None
    assert cached.column("x").to_pylist() == [1, 2, 3]


def test_read_cached_returns_none_on_fingerprint_mismatch(tmp_path):
    table = pa.table({"x": [1]})
    write_cached(table, tmp_path / "t.parquet", "fp_old")
    assert read_cached(tmp_path / "t.parquet", "fp_new") is None


def test_read_cached_returns_none_on_missing_file(tmp_path):
    assert read_cached(tmp_path / "nonexistent.parquet", "fp") is None
