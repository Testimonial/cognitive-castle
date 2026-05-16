"""Load LongMemEval into a Parquet-compatible Arrow table whose schema
matches the palace's, with Castle-specific fields (wing, room, added_by)
set to null.

The chunker delegates to ``cognitive_castle.miner.chunk_text`` so research
artefacts split LME sessions on the same boundaries the production palace
would, keeping H3's downstream comparisons honest. Castle's miner exposes
``chunk_text(content, source_file) -> list[{"content", "chunk_index"}]``
with a module-level ``CHUNK_SIZE`` constant rather than a config object,
so we adapt accordingly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

import pyarrow as pa

from cognitive_castle.miner import chunk_text


def load_longmemeval(source: Union[Path, str]) -> pa.Table:
    """Read LME questions (or a fixture JSON), chunk each session through
    Castle's miner, and return an Arrow table compatible with
    ``load_palace()``.

    Castle-specific columns (``wing``, ``room``, ``added_by``) are present
    in the schema with null values so downstream code can treat LME rows
    and palace rows uniformly.
    """
    source = Path(source)
    if source.is_file() and source.suffix == ".json":
        with open(source) as f:
            questions = json.load(f)
    else:
        # Resolve a real LME data file via the benchmark loader.
        from benchmarks.longmemeval_bench import load_questions

        questions = load_questions(source)

    rows = []
    for q in questions:
        qid = q["question_id"]
        qtype = q["question_type"]
        for sess in q["sessions"]:
            sid = sess["session_id"]
            ts = sess["timestamp"]
            joined = "\n".join(t["text"] for t in sess["turns"])
            source_file = f"lme_{qid}_{sid}"
            chunks = chunk_text(joined, source_file)
            for chunk in chunks:
                ci = chunk["chunk_index"]
                rows.append(
                    {
                        "drawer_id": f"lme_{qid}_{sid}_{ci:03d}",
                        "text": chunk["content"],
                        "filed_at": ts,
                        "session_id": sid,
                        "question_id": qid,
                        "question_type": qtype,
                        "chunk_index": ci,
                        "source_file": source_file,
                        "wing": None,
                        "room": None,
                        "added_by": None,
                    }
                )

    schema = pa.schema(
        [
            ("drawer_id", pa.string()),
            ("text", pa.large_string()),
            ("filed_at", pa.string()),
            ("session_id", pa.string()),
            ("question_id", pa.string()),
            ("question_type", pa.string()),
            ("chunk_index", pa.int64()),
            ("source_file", pa.string()),
            ("wing", pa.string()),
            ("room", pa.string()),
            ("added_by", pa.string()),
        ]
    )
    return pa.Table.from_pylist(rows, schema=schema)
