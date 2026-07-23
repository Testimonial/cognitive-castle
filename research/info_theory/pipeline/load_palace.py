"""Load the snapshotted palace into a Parquet-compatible PyArrow
table. Parses `metadata_json` to surface `filed_at` and `added_by`
as proper columns. Excludes drawers with missing `filed_at`."""

from __future__ import annotations
import json
import logging
from pathlib import Path
import lancedb
import pyarrow as pa

logger = logging.getLogger(__name__)


def parse_metadata_json(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def load_palace(snapshot_dir: Path) -> pa.Table:
    """Read castle_drawers from snapshot_dir, return Arrow table
    with filed_at + added_by promoted from metadata_json."""
    db = lancedb.connect(str(snapshot_dir))
    table = db.open_table("castle_drawers").to_arrow()

    # Rename raw LanceDB ``id`` column to ``drawer_id`` for cross-loader parity
    # (load_longmemeval also exposes ``drawer_id``).
    if "id" in table.column_names:
        new_names = ["drawer_id" if n == "id" else n for n in table.column_names]
        table = table.rename_columns(new_names)

    filed_at_col, added_by_col, kept_indices = [], [], []
    excluded = 0
    for i, raw in enumerate(table.column("metadata_json").to_pylist()):
        meta = parse_metadata_json(raw)
        if "filed_at" not in meta:
            excluded += 1
            continue
        filed_at_col.append(meta["filed_at"])
        added_by_col.append(meta.get("added_by", "unknown"))
        kept_indices.append(i)

    if excluded:
        logger.warning(f"Excluded {excluded} drawers missing filed_at (of {table.num_rows})")

    kept = table.take(pa.array(kept_indices))
    kept = kept.append_column("filed_at", pa.array(filed_at_col))
    kept = kept.append_column("added_by", pa.array(added_by_col))
    return kept
