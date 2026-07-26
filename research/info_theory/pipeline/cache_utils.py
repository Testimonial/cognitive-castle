# pipeline/cache_utils.py
"""Shared cache-fingerprint utility used by all pipeline stages that
write Parquet caches. Per the spec, every stage's output Parquet
carries an `inputs_fingerprint` key in its schema metadata so
`cli status` can detect stale stages."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Iterable, Optional
import pyarrow.parquet as pq


def fingerprint_inputs(items: Iterable) -> str:
    """SHA256 of a canonical-JSON serialization of `items`. Order-
    independent if `items` is a sorted iterable; otherwise sensitive
    to order. Callers pre-sort if they want order-independence."""
    payload = json.dumps(list(items), separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def read_cached(path: Path, expected_fingerprint: str):
    """Return cached Arrow table if fingerprint matches; else None."""
    if not Path(path).exists():
        return None
    cached = pq.read_table(path)
    meta = cached.schema.metadata or {}
    if meta.get(b"inputs_fingerprint") == expected_fingerprint.encode():
        return cached
    return None


def write_cached(
    table, path: Path, inputs_fingerprint: str, extra_metadata: Optional[dict] = None
) -> None:
    """Write Parquet with inputs_fingerprint stamped in schema metadata."""
    meta = {b"inputs_fingerprint": inputs_fingerprint.encode()}
    if extra_metadata:
        for k, v in extra_metadata.items():
            meta[k.encode() if isinstance(k, str) else k] = v.encode() if isinstance(v, str) else v
    stamped = table.replace_schema_metadata(meta)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(stamped, path)
