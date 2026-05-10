"""LanceDB storage backend for Cognitive Castle (replaces ChromaDB).

Storage layout per palace directory:
  <palace_path>/lancedb/                  — LanceDB database root
    castle_drawers.lance/              — main drawer table
    castle_closets.lance/              — topic/entity pointer table

Schema (both tables):
  id             str      primary key
  vector         fixed-list[float32, 384]
  text           str      document content
  metadata_json  str      full metadata dict, JSON-serialised
  wing           str?     hoisted for fast SQL filtering
  room           str?     hoisted for fast SQL filtering
  source_file    str?     hoisted for fast SQL filtering
  chunk_index    int64?   hoisted for fast SQL filtering
  decay_score    float64  freshness score (1.0 = fresh, decays over time)

Filter translation:
  ChromaDB's $eq / $ne / $in / $nin / $and / $or / $contains / $gt / $gte / $lt / $lte
  are translated to LanceDB SQL WHERE clauses at query time.
  Only the hoisted columns are indexed; filtering on other metadata fields falls
  through to a metadata_json scan (not currently supported — raise UnsupportedFilterError).
"""

from __future__ import annotations

import json
import logging
import os
from threading import Lock
from typing import Any, Optional

import pyarrow as pa

from .base import (
    BaseBackend,
    BaseCollection,
    GetResult,
    HealthStatus,
    PalaceNotFoundError,
    PalaceRef,
    QueryResult,
    UnsupportedFilterError,
    _IncludeSpec,
)

logger = logging.getLogger(__name__)


def _legacy_embed_dim() -> int:
    """Read default embedder_dim from config — for backward-compat constant only."""
    from ..config import MempalaceConfig

    return MempalaceConfig().embedder_dim


EMBED_DIM = _legacy_embed_dim()  # backward-compat: prefer cfg.embedder_dim in new code

# Columns extracted from metadata dict and stored as first-class filterable columns.
_HOISTED = {"wing", "room", "source_file", "chunk_index", "decay_score"}

# Supported filter operators (same set as the chroma backend enforces).
_SUPPORTED_OPS = frozenset(
    {"$eq", "$ne", "$in", "$nin", "$contains", "$and", "$or", "$gt", "$gte", "$lt", "$lte"}
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def _build_schema(cfg) -> pa.Schema:
    """Build the LanceDB Arrow schema using ``cfg.embedder_dim`` for the vector dimension.

    This is the canonical schema factory.  Pass any object with an
    ``embedder_dim`` attribute (e.g. ``MempalaceConfig`` or a ``MagicMock``
    in tests).
    """
    dim = cfg.embedder_dim
    # All non-vector columns are non-nullable; missing strings use "" and
    # missing chunk_index uses -1 as sentinels so Arrow never sees None.
    return pa.schema(
        [
            pa.field("id", pa.utf8()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
            pa.field("text", pa.large_utf8()),
            pa.field("metadata_json", pa.large_utf8()),
            pa.field("wing", pa.utf8()),
            pa.field("room", pa.utf8()),
            pa.field("source_file", pa.utf8()),
            pa.field("chunk_index", pa.int64()),
            pa.field("decay_score", pa.float64()),
        ]
    )


def _make_schema() -> pa.Schema:
    """Backward-compat shim — uses default config dim (384).  Prefer ``_build_schema(cfg)``."""
    from ..config import MempalaceConfig

    return _build_schema(MempalaceConfig())


# ---------------------------------------------------------------------------
# Filter translation: ChromaDB $-operators → SQL string
# ---------------------------------------------------------------------------


def _quote_val(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    escaped = str(val).replace("'", "''")
    return f"'{escaped}'"


def _translate_field_filter(col: str, val: Any) -> str:
    """Translate a single field filter to SQL. val may be a scalar or $-op dict."""
    if not isinstance(val, dict):
        return f"{col} = {_quote_val(val)}"

    if len(val) != 1:
        raise UnsupportedFilterError(f"Expected exactly one operator in field filter, got {val}")

    op, operand = next(iter(val.items()))
    if op not in _SUPPORTED_OPS:
        raise UnsupportedFilterError(f"Unsupported filter operator: {op!r}")

    if op == "$eq":
        return f"{col} = {_quote_val(operand)}"
    if op == "$ne":
        return f"{col} != {_quote_val(operand)}"
    if op == "$in":
        vals = ", ".join(_quote_val(v) for v in operand)
        return f"{col} IN ({vals})"
    if op == "$nin":
        vals = ", ".join(_quote_val(v) for v in operand)
        return f"{col} NOT IN ({vals})"
    if op == "$contains":
        escaped = str(operand).replace("'", "''").replace("%", r"\%").replace("_", r"\_")
        return f"{col} LIKE '%{escaped}%'"
    if op == "$gt":
        return f"{col} > {_quote_val(operand)}"
    if op == "$gte":
        return f"{col} >= {_quote_val(operand)}"
    if op == "$lt":
        return f"{col} < {_quote_val(operand)}"
    if op == "$lte":
        return f"{col} <= {_quote_val(operand)}"

    raise UnsupportedFilterError(f"Unhandled operator: {op!r}")


def _where_to_sql(where: Optional[dict]) -> Optional[str]:
    """Recursively translate a ChromaDB-style where dict to a SQL string."""
    if not where:
        return None

    clauses: list[str] = []
    for key, val in where.items():
        if key == "$and":
            parts = [_where_to_sql(sub) for sub in val]
            parts = [p for p in parts if p]
            if parts:
                clauses.append("(" + " AND ".join(parts) + ")")
        elif key == "$or":
            parts = [_where_to_sql(sub) for sub in val]
            parts = [p for p in parts if p]
            if parts:
                clauses.append("(" + " OR ".join(parts) + ")")
        else:
            # Field filter — only hoisted columns are supported
            if key not in _HOISTED:
                raise UnsupportedFilterError(
                    f"Field {key!r} is not a hoisted column; only {sorted(_HOISTED)} "
                    f"are filterable in the LanceDB backend."
                )
            clauses.append(_translate_field_filter(key, val))

    return " AND ".join(clauses) if clauses else None


def _where_doc_to_sql(where_document: Optional[dict]) -> Optional[str]:
    """Translate a ChromaDB where_document filter to a SQL clause on the ``text`` column."""
    if not where_document:
        return None
    op, operand = next(iter(where_document.items()))
    if op == "$contains":
        escaped = str(operand).replace("'", "''")
        return f"text LIKE '%{escaped}%'"
    raise UnsupportedFilterError(f"where_document operator {op!r} not supported")


def _combine_sql(*clauses: Optional[str]) -> Optional[str]:
    parts = [c for c in clauses if c]
    return " AND ".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------


def _build_row(
    doc_id: str,
    text: str,
    metadata: dict,
    embedding: Optional[list[float]],
    dim: int = EMBED_DIM,
) -> dict:
    md = metadata or {}
    ci = md.get("chunk_index")
    ds = md.get("decay_score")
    return {
        "id": doc_id,
        "vector": embedding if embedding is not None else [0.0] * dim,
        "text": text or "",
        "metadata_json": json.dumps(md),
        # Hoisted columns — use sentinel values so Arrow schema never gets None
        "wing": str(md.get("wing") or ""),
        "room": str(md.get("room") or ""),
        "source_file": str(md.get("source_file") or ""),
        "chunk_index": int(ci) if ci is not None else -1,
        "decay_score": float(ds) if ds is not None else 1.0,
    }


def _row_to_metadata(row: dict) -> dict:
    raw = row.get("metadata_json") or "{}"
    try:
        meta = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        meta = {}
    # Sync back hoisted fields (they're canonical)
    for k in _HOISTED:
        v = row.get(k)
        if v is not None:
            meta[k] = v
    return meta


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


class LanceCollection(BaseCollection):
    """LanceDB-backed Cognitive Castle collection."""

    def __init__(self, table, cfg=None):
        self._table = table
        if cfg is None:
            from ..config import MempalaceConfig

            cfg = MempalaceConfig()
        self._dim: int = cfg.embedder_dim
        self._ensure_fts_index()

    # -- FTS index -----------------------------------------------------------

    def _ensure_fts_index(self, replace: bool = False) -> None:
        """Create a Tantivy-backed FTS index on the ``text`` column if missing.

        Idempotent: ``replace=False`` (default) is a no-op when the index
        already exists.  Pass ``replace=True`` to rebuild after adding data.

        Degrades gracefully: if LanceDB FTS is unavailable in this version the
        exception is swallowed and ``fts_search`` will return ``[]``.
        """
        try:
            self._table.create_fts_index("text", replace=replace)
        except Exception as exc:
            # Index already exists (replace=False), or FTS not supported in
            # this LanceDB build.  Either way the pipeline degrades gracefully.
            logger.debug("_ensure_fts_index: ignored exception: %s", exc)

    # -- FTS search ----------------------------------------------------------

    def fts_search(self, query: str, n_results: int = 100) -> list[dict]:
        """Sparse keyword search via Tantivy FTS.

        Returns rows ordered by relevance score.  Each row is a ``dict`` with
        at minimum ``id`` and ``text`` keys; additional hoisted columns and an
        optional ``_score`` column may be present depending on LanceDB version.

        Returns ``[]`` for blank queries or when FTS is unavailable.
        """
        if not query.strip():
            return []
        try:
            results = (
                self._table.search(query, query_type="fts")
                .limit(n_results)
                .to_list()
            )
            return list(results)
        except Exception as exc:
            logger.debug("fts_search: FTS query failed (%s), returning []", exc)
            return []

    # -- Vector search -------------------------------------------------------

    def vector_search(
        self,
        vec: list[float],
        n_results: int = 100,
        where: Optional[str] = None,
    ) -> list[dict]:
        """Similarity search by query vector.

        Returns rows ordered by ascending cosine distance.  ``where`` is an
        optional SQL filter string applied as a pre-filter.
        """
        q = self._table.search(vec, vector_column_name="vector").metric("cosine").limit(n_results)
        if where:
            try:
                q = q.where(where, prefilter=True)
            except Exception as exc:
                logger.debug("vector_search: where filter ignored (%s)", exc)
        return q.to_list()

    # -- ID fetch ------------------------------------------------------------

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """Return rows matching any of the supplied IDs (order not guaranteed)."""
        if not ids:
            return []
        quoted = ", ".join(_quote_val(i) for i in ids)
        try:
            return (
                self._table.search(None)
                .where(f"id IN ({quoted})")
                .limit(len(ids))
                .to_list()
            )
        except Exception as exc:
            logger.debug("get_by_ids: fetch failed (%s), returning []", exc)
            return []

    # -- Writes --------------------------------------------------------------

    def _embed_if_needed(
        self, documents: list[str], embeddings: Optional[list[list[float]]]
    ) -> list[list[float]]:
        if embeddings is not None:
            return embeddings
        from ..embedding import embed_texts

        return embed_texts(documents)

    def add(self, *, documents, ids, metadatas=None, embeddings=None):
        vecs = self._embed_if_needed(documents, embeddings)
        metas = metadatas or [{} for _ in documents]
        rows = [
            _build_row(doc_id, doc, meta, vec, self._dim)
            for doc_id, doc, meta, vec in zip(ids, documents, metas, vecs)
        ]
        self._table.add(rows)

    def upsert(self, *, documents, ids, metadatas=None, embeddings=None):
        vecs = self._embed_if_needed(documents, embeddings)
        metas = metadatas or [{} for _ in documents]
        rows = [
            _build_row(doc_id, doc, meta, vec, self._dim)
            for doc_id, doc, meta, vec in zip(ids, documents, metas, vecs)
        ]
        (
            self._table.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(rows)
        )

    def update(self, *, ids, documents=None, metadatas=None, embeddings=None):
        if documents is None and metadatas is None and embeddings is None:
            raise ValueError("update requires at least one of documents, metadatas, embeddings")
        existing = self.get(ids=ids, include=["documents", "metadatas", "embeddings"])
        by_id = {
            eid: (existing.documents[i], existing.metadatas[i], existing.embeddings[i] if existing.embeddings else None)
            for i, eid in enumerate(existing.ids)
        }
        merged_docs, merged_metas, merged_vecs = [], [], []
        for i, doc_id in enumerate(ids):
            prev_doc, prev_meta, prev_vec = by_id.get(doc_id, ("", {}, None))
            merged_docs.append(documents[i] if documents is not None else prev_doc)
            new_meta = dict(prev_meta or {})
            if metadatas is not None:
                new_meta.update(metadatas[i] or {})
            merged_metas.append(new_meta)
            merged_vecs.append(embeddings[i] if embeddings is not None else prev_vec)

        self.upsert(
            documents=merged_docs, ids=list(ids), metadatas=merged_metas, embeddings=merged_vecs
        )

    # -- Reads ---------------------------------------------------------------

    def query(
        self,
        *,
        query_texts=None,
        query_embeddings=None,
        n_results=10,
        where=None,
        where_document=None,
        include=None,
    ) -> QueryResult:
        if (query_texts is None) == (query_embeddings is None):
            raise ValueError("query requires exactly one of query_texts or query_embeddings")

        if query_texts is not None:
            from ..embedding import embed_texts
            vecs = embed_texts(query_texts)
        else:
            vecs = query_embeddings

        where_sql = _where_to_sql(where)
        wdoc_sql = _where_doc_to_sql(where_document)
        combined_filter = _combine_sql(where_sql, wdoc_sql)

        spec = _IncludeSpec.resolve(include, default_distances=True)

        all_ids: list[list[str]] = []
        all_docs: list[list[str]] = []
        all_metas: list[list[dict]] = []
        all_dists: list[list[float]] = []
        all_embeds: list[list[list[float]]] = [] if spec.embeddings else None

        for vec in vecs:
            q = self._table.search(vec, vector_column_name="vector").metric("cosine").limit(n_results)
            if combined_filter:
                q = q.where(combined_filter, prefilter=True)
            rows = q.to_list()

            ids_, docs_, metas_, dists_, embeds_ = [], [], [], [], []
            for row in rows:
                ids_.append(row["id"])
                if spec.documents:
                    docs_.append(row.get("text") or "")
                if spec.metadatas:
                    metas_.append(_row_to_metadata(row))
                if spec.distances:
                    dists_.append(float(row.get("_distance", 0.0)))
                if spec.embeddings and all_embeds is not None:
                    v = row.get("vector")
                    embeds_.append(list(v) if v is not None else [])

            all_ids.append(ids_)
            all_docs.append(docs_)
            all_metas.append(metas_)
            all_dists.append(dists_)
            if spec.embeddings and all_embeds is not None:
                all_embeds.append(embeds_)

        return QueryResult(
            ids=all_ids,
            documents=all_docs,
            metadatas=all_metas,
            distances=all_dists,
            embeddings=all_embeds,
        )

    def get(
        self,
        *,
        ids=None,
        where=None,
        where_document=None,
        limit=None,
        offset=None,
        include=None,
    ) -> GetResult:
        where_sql = _where_to_sql(where)
        wdoc_sql = _where_doc_to_sql(where_document)

        if ids is not None:
            quoted = ", ".join(_quote_val(i) for i in ids)
            id_filter = f"id IN ({quoted})"
            combined_filter = _combine_sql(id_filter, where_sql, wdoc_sql)
        else:
            combined_filter = _combine_sql(where_sql, wdoc_sql)

        spec = _IncludeSpec.resolve(include, default_distances=False)
        scan_limit = (limit or 100_000) + (offset or 0)

        q = self._table.search(None)
        if combined_filter:
            q = q.where(combined_filter)
        q = q.limit(scan_limit)
        rows = q.to_list()

        if offset:
            rows = rows[offset:]

        out_ids, out_docs, out_metas, out_embeds = [], [], [], []
        for row in rows:
            out_ids.append(row["id"])
            if spec.documents:
                out_docs.append(row.get("text") or "")
            if spec.metadatas:
                out_metas.append(_row_to_metadata(row))
            if spec.embeddings:
                v = row.get("vector")
                out_embeds.append(list(v) if v is not None else [])

        return GetResult(
            ids=out_ids,
            documents=out_docs,
            metadatas=out_metas,
            embeddings=out_embeds if spec.embeddings else None,
        )

    def delete(self, *, ids=None, where=None):
        where_sql = _where_to_sql(where)
        if ids is not None:
            quoted = ", ".join(_quote_val(i) for i in ids)
            id_filter = f"id IN ({quoted})"
            combined_filter = _combine_sql(id_filter, where_sql)
        else:
            combined_filter = where_sql
        if not combined_filter:
            raise ValueError("delete requires ids or where to prevent full-table deletion")
        self._table.delete(combined_filter)

    def count(self) -> int:
        return self._table.count_rows()

    def health(self) -> HealthStatus:
        try:
            self._table.count_rows()
            return HealthStatus.healthy()
        except Exception as exc:
            return HealthStatus.unhealthy(str(exc))


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class LanceDBBackend(BaseBackend):
    """LanceDB-backed Cognitive Castle storage backend.

    Stores each palace under ``<palace_path>/lancedb/``. One LanceDB
    database per palace, one table per collection name.
    """

    name = "lancedb"
    capabilities = frozenset(
        {
            "supports_embeddings_in",
            "supports_embeddings_out",
            "supports_metadata_filters",
            "local_mode",
        }
    )

    def __init__(self, cfg=None):
        if cfg is None:
            from ..config import MempalaceConfig

            cfg = MempalaceConfig()
        self._cfg = cfg
        self._dbs: dict[str, Any] = {}
        self._tables: dict[tuple[str, str], Any] = {}
        self._lock = Lock()
        self._closed = False

    def _db_dir(self, palace_path: str) -> str:
        return os.path.join(palace_path, "lancedb")

    def _get_db(self, palace_path: str):
        if self._closed:
            from .base import BackendClosedError
            raise BackendClosedError("LanceDBBackend has been closed")

        db_dir = self._db_dir(palace_path)
        cached = self._dbs.get(db_dir)
        if cached is not None:
            return cached

        import lancedb
        os.makedirs(db_dir, exist_ok=True)
        db = lancedb.connect(db_dir)
        self._dbs[db_dir] = db
        return db

    def get_collection(self, *args, **kwargs) -> LanceCollection:
        from ._utils import _normalize_get_collection_args

        palace_ref, collection_name, create, _options = _normalize_get_collection_args(
            args, kwargs
        )

        palace_path = palace_ref.local_path
        if palace_path is None:
            raise PalaceNotFoundError("LanceDBBackend requires PalaceRef.local_path")

        if not create and not os.path.isdir(self._db_dir(palace_path)):
            raise PalaceNotFoundError(palace_path)

        if create:
            os.makedirs(palace_path, exist_ok=True)

        cache_key = (palace_path, collection_name)
        with self._lock:
            cached_table = self._tables.get(cache_key)
            if cached_table is not None:
                return LanceCollection(cached_table, self._cfg)

            db = self._get_db(palace_path)
            schema = _build_schema(self._cfg)
            table = db.create_table(collection_name, schema=schema, exist_ok=True)
            self._tables[cache_key] = table
            return LanceCollection(table, self._cfg)

    def close_palace(self, palace) -> None:
        path = palace.local_path if isinstance(palace, PalaceRef) else palace
        if path is None:
            return
        db_dir = self._db_dir(path)
        with self._lock:
            self._dbs.pop(db_dir, None)
            keys = [k for k in self._tables if k[0] == path]
            for k in keys:
                self._tables.pop(k, None)

    def close(self) -> None:
        with self._lock:
            self._dbs.clear()
            self._tables.clear()
            self._closed = True

    def health(self, palace: Optional[PalaceRef] = None) -> HealthStatus:
        if self._closed:
            return HealthStatus.unhealthy("backend closed")
        return HealthStatus.healthy()

    @classmethod
    def detect(cls, path: str) -> bool:
        return os.path.isdir(os.path.join(path, "lancedb"))
