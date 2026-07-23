"""Verify the merge of palace + LME drawers produces a valid Arrow
table with Castle-specific fields nullable.

Task 25 (Phase 13, pre-experiment validation): confirms the two loaders
produce schemas that can be aligned to a common column set and concatenated
via ``pa.concat_tables(promote_options="default")`` without silent
type-coercion errors.

Adaptations to the plan:
- ``load_palace()`` currently returns the raw LanceDB column ``id`` rather
  than ``drawer_id``. The test renames it here so the merged table exposes
  the drawer identifier under a single, consistent name.
- Palace lacks LME-specific columns (``session_id``, ``question_id``,
  ``question_type``); those are appended as null string columns before
  projection.
"""

from pathlib import Path

import pyarrow as pa

from pipeline.load_longmemeval import load_longmemeval
from pipeline.load_palace import load_palace


def test_merge_handles_nullable_castle_fields():
    palace = load_palace(Path(__file__).parent / "fixtures" / "palace_lance_mini")
    lme = load_longmemeval(Path(__file__).parent / "fixtures" / "longmemeval_mini.json")

    common_cols = [
        "drawer_id",
        "text",
        "filed_at",
        "chunk_index",
        "source_file",
        "wing",
        "room",
        "added_by",
        "session_id",
        "question_id",
        "question_type",
    ]

    # Palace uses LanceDB's ``id`` column; rename to ``drawer_id`` for parity.
    if "drawer_id" not in palace.column_names and "id" in palace.column_names:
        palace = palace.rename_columns(
            ["drawer_id" if n == "id" else n for n in palace.column_names]
        )

    # Pad palace with LME-specific columns (null-valued) so both sides share a schema.
    for c in ("session_id", "question_id", "question_type"):
        if c not in palace.column_names:
            palace = palace.append_column(c, pa.array([None] * palace.num_rows, type=pa.string()))

    palace_proj = palace.select(common_cols)
    lme_proj = lme.select(common_cols)

    merged = pa.concat_tables([palace_proj, lme_proj], promote_options="default")

    assert merged.num_rows == palace_proj.num_rows + lme_proj.num_rows
    assert "drawer_id" in merged.column_names
    assert set(merged.column_names) == set(common_cols)
    # Palace rows keep their wing/room; LME rows keep session/question metadata.
    assert merged.num_rows > 0
