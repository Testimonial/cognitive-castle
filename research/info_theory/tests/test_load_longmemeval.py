from pathlib import Path
import pyarrow as pa
from pipeline.load_longmemeval import load_longmemeval

FIXTURE = Path(__file__).parent / "fixtures" / "longmemeval_mini.json"


def test_load_longmemeval_returns_arrow_table():
    table = load_longmemeval(FIXTURE)
    assert isinstance(table, pa.Table)
    assert table.num_rows > 0


def test_load_longmemeval_has_castle_compatible_schema():
    table = load_longmemeval(FIXTURE)
    cols = set(table.column_names)
    required = {"text", "filed_at", "session_id", "question_id",
                "question_type", "chunk_index", "wing", "room", "added_by"}
    assert required.issubset(cols)


def test_load_longmemeval_nulls_castle_fields():
    table = load_longmemeval(FIXTURE)
    # wing, room, added_by are Castle-specific; LME rows have them null
    assert all(v is None for v in table.column("wing").to_pylist())
    assert all(v is None for v in table.column("added_by").to_pylist())


def test_load_longmemeval_preserves_session_ordering():
    table = load_longmemeval(FIXTURE)
    # q1 has two sessions; chunk_index should increase within session
    q1_rows = [(r["session_id"], r["chunk_index"])
               for r in table.to_pylist() if r["question_id"] == "q1"]
    from collections import defaultdict
    by_session = defaultdict(list)
    for sid, ci in q1_rows:
        by_session[sid].append(ci)
    for sid, chunks in by_session.items():
        assert chunks == sorted(chunks), f"chunks not ordered in {sid}"
