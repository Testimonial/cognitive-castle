"""Embed drawer texts via Castle's bge-m3 embedder. Cached as Parquet.

Castle exposes ``embed_texts`` and ``get_embedding_function`` (returning a
callable) rather than a ``get_embedder()`` object with ``.encode`` and
``.model_revision``. To keep this stage's interface aligned with the research
plan (and to make mocking trivial), we wrap Castle's real API in a small
adapter and expose it as ``get_embedder`` at module scope. Tests patch
``pipeline.embed.get_embedder`` directly.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from cognitive_castle.embedding import embed_texts


class _CastleEmbedderAdapter:
    """Adapter over Castle's ``embed_texts`` to match the plan's expected
    ``.encode(texts) -> np.ndarray`` and ``.model_revision`` interface."""

    def __init__(self) -> None:
        from cognitive_castle.embedding import _resolve_model_name

        self.model_revision = _resolve_model_name()

    def encode(self, texts, **kwargs) -> np.ndarray:
        vecs = embed_texts(list(texts))
        return np.asarray(vecs, dtype=np.float32)


def get_embedder() -> _CastleEmbedderAdapter:
    """Return a Castle-backed embedder with ``.encode`` and ``.model_revision``."""
    return _CastleEmbedderAdapter()


def _fingerprint_inputs(table: pa.Table) -> str:
    """Hash of (drawer_id, text) pairs in deterministic order."""
    pairs = sorted(
        zip(
            table.column("drawer_id").to_pylist(),
            table.column("text").to_pylist(),
        )
    )
    payload = "|".join(f"{d}::{t}" for d, t in pairs).encode()
    return hashlib.sha256(payload).hexdigest()


def embed_drawers(
    table: pa.Table,
    cache_path: Optional[Path] = None,
    batch_size: int = 32,
) -> pa.Table:
    """Add a ``vector`` column. Cache hit if ``cache_path`` exists and its
    schema-metadata fingerprint matches the current inputs."""
    fp = _fingerprint_inputs(table)

    if cache_path and Path(cache_path).exists():
        cached = pq.read_table(cache_path)
        if cached.schema.metadata and cached.schema.metadata.get(b"fingerprint") == fp.encode():
            return cached

    embedder = get_embedder()
    texts = table.column("text").to_pylist()
    vectors: list = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vectors.extend(embedder.encode(batch))
    vec_array = pa.array(
        [np.asarray(v, dtype=np.float32).tolist() for v in vectors],
        type=pa.list_(pa.float32()),
    )
    out = table.append_column("vector", vec_array)

    if cache_path:
        meta = {
            b"fingerprint": fp.encode(),
            b"embedder_revision": embedder.model_revision.encode(),
        }
        out = out.replace_schema_metadata(meta)
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(out, cache_path)
    return out
