from pathlib import Path
import pyarrow as pa
from pipeline.load_palace import load_palace, parse_metadata_json

FIXTURE = Path(__file__).parent / "fixtures" / "palace_lance_mini"


def test_load_palace_returns_arrow_table():
    table = load_palace(FIXTURE)
    assert isinstance(table, pa.Table)
    assert table.num_rows == 10


def test_load_palace_extracts_filed_at_from_metadata_json():
    table = load_palace(FIXTURE)
    cols = table.column_names
    assert "filed_at" in cols
    assert "added_by" in cols
    first = table.column("filed_at")[0].as_py()
    assert first.startswith("2026-01-")


def test_load_palace_includes_chunk_index():
    table = load_palace(FIXTURE)
    assert "chunk_index" in table.column_names
    # Pairs share source_file, alternating chunk_index 0,1
    chunks = table.column("chunk_index").to_pylist()
    assert 0 in chunks and 1 in chunks


def test_parse_metadata_json_handles_missing_fields():
    assert parse_metadata_json("{}") == {}
    assert parse_metadata_json(None) == {}
    assert parse_metadata_json('{"filed_at":"x"}') == {"filed_at": "x"}


def test_load_palace_excludes_drawers_with_missing_filed_at(tmp_path):
    """Schema verification step: drawers missing filed_at are excluded
    and logged. Use a fixture with one bad row."""
    import lancedb

    db = lancedb.connect(str(tmp_path))
    rows = [
        {
            "id": "good_1",
            "text": "x",
            "vector": [0.1] * 1024,
            "metadata_json": '{"filed_at":"2026-01-01","added_by":"miner"}',
            "wing": "w",
            "room": "r",
            "source_file": "/tmp/a",
            "chunk_index": 0,
            "decay_score": 1.0,
        },
        {
            "id": "bad",
            "text": "y",
            "vector": [0.1] * 1024,
            "metadata_json": "{}",
            "wing": "w",
            "room": "r",
            "source_file": "/tmp/a",
            "chunk_index": 1,
            "decay_score": 1.0,
        },
        {
            "id": "good_2",
            "text": "z",
            "vector": [0.1] * 1024,
            "metadata_json": '{"filed_at":"2026-01-02","added_by":"miner"}',
            "wing": "w",
            "room": "r",
            "source_file": "/tmp/b",
            "chunk_index": 0,
            "decay_score": 1.0,
        },
    ]
    db.create_table("castle_drawers", data=rows, exist_ok=True)
    table = load_palace(tmp_path)
    ids = table.column("drawer_id").to_pylist()
    assert "bad" not in ids
    assert "good_1" in ids and "good_2" in ids


def test_load_palace_renames_id_to_drawer_id():
    """load_palace exposes ``drawer_id`` (LanceDB's raw ``id`` column is
    renamed) so downstream loaders see a consistent identifier name."""
    table = load_palace(FIXTURE)
    assert "drawer_id" in table.column_names
    assert "id" not in table.column_names
