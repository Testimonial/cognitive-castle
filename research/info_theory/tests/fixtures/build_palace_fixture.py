# tests/fixtures/build_palace_fixture.py — run once, output committed
import json
import lancedb
import pyarrow as pa
from pathlib import Path

dst = Path(__file__).parent / "palace_lance_mini"
dst.mkdir(exist_ok=True)
db = lancedb.connect(str(dst))

rows = []
for i in range(10):
    rows.append({
        "id": f"drawer_{i:03d}",
        "text": f"sample text {i}",
        "vector": [0.1] * 1024,
        "metadata_json": json.dumps({
            "filed_at": f"2026-01-{i+1:02d}T00:00:00Z",
            "added_by": "miner" if i < 7 else "mcp",
        }),
        "wing": "test_wing",
        "room": "test_room",
        "source_file": f"/tmp/src_{i//2}.jsonl",  # pairs share source_file
        "chunk_index": i % 2,
        "decay_score": 1.0,
    })

schema = pa.schema([
    ("id", pa.string()),
    ("text", pa.large_string()),
    ("vector", pa.list_(pa.float32(), 1024)),
    ("metadata_json", pa.large_string()),
    ("wing", pa.string()),
    ("room", pa.string()),
    ("source_file", pa.string()),
    ("chunk_index", pa.int64()),
    ("decay_score", pa.float64()),
])
db.create_table("castle_drawers", data=rows, schema=schema, exist_ok=True)
print(f"Wrote {len(rows)} fixture drawers to {dst}")
