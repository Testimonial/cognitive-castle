#!/usr/bin/env python3
"""
searcher.py — Find anything. Exact words.

Search routes unconditionally through the 3-stage retrieval pipeline
(dense + sparse + KG recall → weighted RRF + recency → cross-encoder rerank).
The legacy BM25 Python implementation was removed in Task 14; Tantivy FTS
via LanceDB now provides the sparse-retrieval signal.
"""

import logging
import re
from pathlib import Path

# Closet pointer line format: "topic|entities|→drawer_id_a,drawer_id_b"
# Multiple lines may join with newlines inside one closet document.
_CLOSET_DRAWER_REF_RE = re.compile(r"→([\w,]+)")

logger = logging.getLogger("castle_mcp")


class SearchError(Exception):
    """Raised when search cannot proceed (e.g. no palace found)."""


_TOKEN_RE = re.compile(r"\w{2,}", re.UNICODE)


def _first_or_empty(results, key: str) -> list:
    """Return the first inner list of a query result field, or [].

    Accepts both the typed :class:`QueryResult` (attribute access) and the
    plain dict shape; this polymorphism is retained so test mocks still work.
    Preserves the empty-collection semantics from issue #195: when no queries
    returned hits, the outer list may be empty and indexing ``[0]`` would raise.
    """
    outer = getattr(results, key, None) if not isinstance(results, dict) else results.get(key)
    if not outer:
        return []
    return outer[0] or []


def _tokenize(text: str) -> list:
    """Lowercase + strip to alphanumeric tokens of length ≥ 2.

    Tolerates ``None`` documents — the backend can return ``None`` in the
    ``documents`` field for drawers without text content, which would
    otherwise raise ``AttributeError`` mid-rerank.
    """
    if not text:
        return []
    return _TOKEN_RE.findall(text.lower())


def build_where_filter(wing: str = None, room: str = None) -> dict:
    """Build a metadata where-filter dict for wing/room filtering."""
    if wing and room:
        return {"$and": [{"wing": wing}, {"room": room}]}
    elif wing:
        return {"wing": wing}
    elif room:
        return {"room": room}
    return {}


def _extract_drawer_ids_from_closet(closet_doc: str) -> list:
    """Parse all `→drawer_id_a,drawer_id_b` pointers out of a closet document.

    Preserves order and dedupes.
    """
    seen: dict = {}
    for match in _CLOSET_DRAWER_REF_RE.findall(closet_doc):
        for did in match.split(","):
            did = did.strip()
            if did and did not in seen:
                seen[did] = None
    return list(seen.keys())


def _expand_with_neighbors(drawers_col, matched_doc: str, matched_meta: dict, radius: int = 1):
    """Expand a matched drawer with its ±radius sibling chunks in the same source file.

    Motivation — "drawer-grep context" feature: a closet hit returns one
    drawer, but the chunk boundary may clip mid-thought (e.g., the matched
    chunk says "here's a breakdown:" and the actual breakdown lives in the
    next chunk). Fetching the small neighborhood around the match gives
    callers enough context without forcing a follow-up ``get_drawer`` call.

    Returns a dict with:
        ``text``            combined chunks in chunk_index order
        ``drawer_index``    the matched chunk's index in the source file
        ``total_drawers``   total drawer count for the source file (or None)

    On any backend failure or missing metadata, falls back to returning the
    matched drawer alone so search never breaks because neighbor expansion
    failed.
    """
    src = matched_meta.get("source_file")
    chunk_idx = matched_meta.get("chunk_index")
    if not src or not isinstance(chunk_idx, int):
        return {"text": matched_doc, "drawer_index": chunk_idx, "total_drawers": None}

    target_indexes = [chunk_idx + offset for offset in range(-radius, radius + 1)]
    try:
        neighbors = drawers_col.get(
            where={
                "$and": [
                    {"source_file": src},
                    {"chunk_index": {"$in": target_indexes}},
                ]
            },
            include=["documents", "metadatas"],
        )
    except Exception:
        return {"text": matched_doc, "drawer_index": chunk_idx, "total_drawers": None}

    indexed_docs = []
    for doc, meta in zip(neighbors.documents, neighbors.metadatas):
        ci = meta.get("chunk_index")
        if isinstance(ci, int):
            indexed_docs.append((ci, doc))
    indexed_docs.sort(key=lambda pair: pair[0])

    if not indexed_docs:
        combined_text = matched_doc
    else:
        combined_text = "\n\n".join(doc for _, doc in indexed_docs)

    # Cheap total_drawers lookup: metadata-only scan of the source file.
    total_drawers = None
    try:
        all_meta = drawers_col.get(where={"source_file": src}, include=["metadatas"])
        total_drawers = len(all_meta.ids) if all_meta.ids else None
    except Exception:
        pass

    return {
        "text": combined_text,
        "drawer_index": chunk_idx,
        "total_drawers": total_drawers,
    }


def search(
    query: str,
    palace_path: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
    llm_rerank: bool = False,
):
    """CLI entry point.

    Routes through the 3-stage pipeline (dense + FTS + KG-hop → fuse → rerank),
    same as `search_memories()`. Prints results to stdout in the legacy format
    so existing scraping tests keep working. Score shown is the cross-encoder
    reranker score, not cosine distance.

    Args:
        llm_rerank: When True, appends Stage 4 LLM-as-judge re-rank after the
            cross-encoder (Stage 3). Default False — no behavior change.

    Raises SearchError if the pipeline fails. Returns None either way (this is
    a print-only function — programmatic callers should use `search_memories`).
    """
    from .config import CognitiveCastleConfig

    cfg = CognitiveCastleConfig()

    try:
        hits = _new_pipeline_search(
            query,
            palace_path,
            wing,
            room,
            n_results,
            cfg,
            is_hook_call=False,
            llm_rerank=llm_rerank,
        )
    except Exception as e:
        print(f"\n  Search error: {e}")
        raise SearchError(f"Search error: {e}") from e

    if not hits:
        print(f'\n  No results found for: "{query}"')
        return

    print(f"\n{'=' * 60}")
    print(f'  Results for: "{query}"')
    if wing:
        print(f"  Wing: {wing}")
    if room:
        print(f"  Room: {room}")
    print(f"{'=' * 60}\n")

    for i, hit in enumerate(hits, 1):
        text = hit.get("text") or hit.get("document", "")
        score = round(float(hit.get("score", 0.0)), 3)
        wing_name = hit.get("wing", "?")
        room_name = hit.get("room", "?")
        source = Path(hit.get("source_file", "?")).name

        print(f"  [{i}] {wing_name} / {room_name}")
        print(f"      Source: {source}")
        print(f"      Match:  score={score}\n")
        print(f"      {text}\n")
        print(f"  {'─' * 56}")


def search_memories(
    query: str,
    palace_path: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
    max_distance: float = 0.0,
    vector_disabled: bool = False,
    candidate_strategy: str = "vector",
    is_hook_call: bool = False,
    llm_rerank: bool = False,
) -> dict:
    """Programmatic search — returns a dict instead of printing.

    Routes unconditionally through the 3-stage retrieval pipeline
    (dense + sparse + KG recall → weighted RRF + recency → cross-encoder rerank).

    The ``max_distance``, ``vector_disabled``, and ``candidate_strategy``
    parameters are accepted for API compatibility but are no longer acted on
    by the pipeline (the new pipeline handles its own recall budget internally).

    Used by the MCP server and other callers that need data.

    Args:
        query: Natural language search query.
        palace_path: Path to the palace directory.
        wing: Optional wing filter.
        room: Optional room filter.
        n_results: Max results to return.
        max_distance: Accepted for compatibility; ignored by new pipeline.
        vector_disabled: Accepted for compatibility; ignored by new pipeline.
        candidate_strategy: Accepted for compatibility; ignored by new pipeline.
        is_hook_call: When True, uses a smaller reranker K cap (hook budget).
        llm_rerank: When True, appends Stage 4 LLM-as-judge re-rank after the
            cross-encoder (Stage 3). Default False — no behavior change.
    """
    from .config import CognitiveCastleConfig as _cfg_cls

    cfg = _cfg_cls()
    results = _new_pipeline_search(
        query, palace_path, wing, room, n_results, cfg, is_hook_call, llm_rerank=llm_rerank
    )

    # ``_new_pipeline_search`` returns a list. Wrap it in the legacy dict
    # shape so MCP-tool callers and tests that expect ``result["results"]`` /
    # ``result.get("results")`` keep working without changes.
    if isinstance(results, dict):
        # Propagate any error dict the pipeline may return.
        return results
    return {
        "query": query,
        "filters": {"wing": wing, "room": room},
        "results": results if results is not None else [],
    }


# ── New 3-stage retrieval pipeline ────────────────────────────────────────────


def _extract_id(row) -> str:
    """Extract drawer id from a LanceDB row dict."""
    if isinstance(row, dict):
        return row.get("id") or ""
    return ""


def _extract_text(row) -> str:
    """Extract document text from a LanceDB row dict."""
    if isinstance(row, dict):
        return row.get("text") or row.get("document") or ""
    return ""


def _extract_ts(row) -> float:
    """Extract unix timestamp from a LanceDB row dict."""
    if isinstance(row, dict):
        # Check hoisted ts column first, then metadata_json, then nested metadata dict.
        ts = row.get("ts")
        if ts is None:
            import json as _json

            raw = row.get("metadata_json")
            if raw:
                try:
                    meta = _json.loads(raw)
                    ts = meta.get("ts")
                except (ValueError, TypeError):
                    pass
        if ts is None:
            ts = (row.get("metadata") or {}).get("ts")
        try:
            return float(ts) if ts is not None else 0.0
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _build_where_sql(wing, room) -> str | None:
    """Build a LanceDB SQL WHERE fragment for wing/room filtering."""
    conditions = []
    if wing:
        escaped = str(wing).replace("'", "''")
        conditions.append(f"wing = '{escaped}'")
    if room:
        escaped = str(room).replace("'", "''")
        conditions.append(f"room = '{escaped}'")
    return " AND ".join(conditions) if conditions else None


def _new_pipeline_search(
    query: str,
    palace_path: str,
    wing: str | None,
    room: str | None,
    n_results: int,
    cfg,
    is_hook_call: bool = False,
    llm_rerank: bool = False,
) -> list:
    """3-stage retrieval pipeline: parallel recall → fusion → cross-encoder rerank.

    Stage 1: Recall
        1a. Dense vector search via ``LanceCollection.vector_search`` → top-100.
        1b. Tantivy FTS sparse search via ``LanceCollection.fts_search`` → top-100.
        1c. KG-hop: query → ``EntityRegistry.lookup_in_text`` → entity IDs →
            ``KnowledgeGraph.find_drawers_by_entities`` → top-N, then hydrate.

    Stage 2: Fusion
        Weighted RRF over the three recall lists, then recency boost.

    Stage 3: Rerank
        Top-K candidates fed through the cross-encoder; top-N returned.

    Returns a list of result dicts.  Only runs when
    ``cfg.use_new_retrieval_pipeline`` is True.
    """
    from datetime import datetime, timezone
    from pathlib import Path as _Path

    from .palace import get_collection as _get_collection
    from .embedding import embed_texts
    from .fusion import CandidateRef, weighted_rrf, apply_recency
    from .reranker import rerank

    # Resolve the LanceCollection from the default palace backend.
    try:
        col = _get_collection(palace_path, collection_name="castle_drawers", create=False)
    except Exception:
        # No palace found — degrade to empty results rather than crashing.
        return []

    where_sql = _build_where_sql(wing, room)

    # ── Stage 1a: dense vector search ──────────────────────────────────────
    try:
        [query_vec] = embed_texts([query])
        dense_rows = col.vector_search(query_vec, n_results=100, where=where_sql)
    except Exception:
        dense_rows = []

    # ── Stage 1b: Tantivy FTS sparse search ────────────────────────────────
    try:
        sparse_rows = col.fts_search(query, n_results=100)
    except Exception:
        sparse_rows = []

    # ── Stage 1c: KG-hop ───────────────────────────────────────────────────
    kg_rows: list = []
    palace_dir = _Path(palace_path)
    entities_path = palace_dir / "entity_registry.json"
    kg_path = palace_dir / "knowledge_graph.sqlite3"
    if entities_path.exists() and kg_path.exists():
        try:
            from .entity_registry import EntityRegistry
            from .knowledge_graph import KnowledgeGraph

            # EntityRegistry.load expects a directory; pass the palace dir.
            reg = EntityRegistry.load(config_dir=palace_dir)
            matches = reg.lookup_in_text(query)
            if matches:
                kg = KnowledgeGraph(db_path=str(kg_path))
                kg_drawer_ids = kg.find_drawers_by_entities(
                    [m.entity_id for m in matches],
                    limit=cfg.kg_hop_top_n,
                )
                if kg_drawer_ids:
                    kg_rows = col.get_by_ids(kg_drawer_ids)
        except Exception:
            # KG-hop is best-effort; degrade to dense+sparse only.
            kg_rows = []

    # ── Stage 2: fusion + recency boost ────────────────────────────────────
    def _to_refs(rows):
        return [
            CandidateRef(
                drawer_id=_extract_id(r),
                timestamp_unix=_extract_ts(r),
            )
            for r in rows
            if _extract_id(r)
        ]

    rank_lists = {
        "dense": _to_refs(dense_rows),
        "sparse": _to_refs(sparse_rows),
        "kg": _to_refs(kg_rows),
    }
    weights = {
        "dense": cfg.weight_dense,
        "sparse": cfg.weight_sparse,
        "kg": cfg.weight_kg,
    }

    fused = weighted_rrf(rank_lists, weights, k_rrf=cfg.k_rrf)
    fused = apply_recency(
        fused,
        now=datetime.now(timezone.utc),
        tau_days=cfg.recency_tau_days,
        max_boost=cfg.recency_max_boost,
    )

    # ── Stage 3: cross-encoder rerank ──────────────────────────────────────
    k_cap = cfg.reranker_k_hook if is_hook_call else cfg.reranker_k_interactive
    top_k_ids = [s.drawer_id for s in fused[:k_cap]]
    if not top_k_ids:
        return []

    top_k_rows = col.get_by_ids(top_k_ids)
    if not top_k_rows:
        return []

    docs = [_extract_text(r) for r in top_k_rows]
    rerank_scores = rerank(query, docs, cfg=cfg)
    reranked = sorted(zip(rerank_scores, top_k_rows), key=lambda x: -x[0])

    # ── Stage 4 (optional): LLM-as-judge re-rank ───────────────────────────
    if llm_rerank:
        from .judge import judge

        # Take top-N (cfg.llm_judge_top_n) from Stage 3 output for LLM judging.
        # Stage 3 already returned a sorted list (most-relevant first).
        top_n = cfg.llm_judge_top_n
        judge_pool = reranked[:top_n]
        judge_docs = [_extract_text(r) for _, r in judge_pool]
        new_order = judge(query, judge_docs, cfg)
        # Reorder judge_pool by the LLM's preferred indices.
        reranked = [judge_pool[i] for i in new_order]

    return [
        {
            "id": _extract_id(r),
            # "text" is the legacy key expected by MCP callers, tests, and
            # benchmarks; "document" is kept for forward-compat callers.
            "text": _extract_text(r),
            "document": _extract_text(r),
            "score": float(s),
            "wing": r.get("wing", "") if isinstance(r, dict) else "",
            "room": r.get("room", "") if isinstance(r, dict) else "",
        }
        for s, r in reranked[:n_results]
    ]
