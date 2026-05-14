"""kg_enricher.py — Phase 2 of `castle mine` / `castle reindex`.

Walks the un-indexed drawer set, extracts entity candidates, classifies
+ promotes high-confidence ones to the registry, and writes
``(entity, mentioned_in, drawer_id)`` triples to the knowledge graph.

Opt-in by virtue of being called from the miner's end-of-pipeline hook.
Local-only — regex + signal-counting (no LLM, no network). Append-only,
idempotent, self-healing on interrupt.

See spec: docs/superpowers/specs/2026-05-14-kg-enrichment-design.md
"""

from __future__ import annotations

import sqlite3
import time
from collections import Counter, defaultdict
from itertools import batched
from pathlib import Path
from typing import Iterable

from . import entity_detector
from . import palace as palace_mod


ADAPTER_NAME = "entity-mention-indexer"


def enrich_palace(palace_path: str, cfg) -> dict:
    """Public entry point. Runs all four steps of Phase 2.

    Returns ``{"drawers_scanned", "entities_promoted", "triples_written",
    "elapsed_s"}``. Never raises — caller catches at miner boundary.
    """
    started = time.time()
    col = palace_mod.get_collection(palace_path=palace_path)

    all_ids = col.list_drawer_ids()
    if not all_ids:
        return _result(0, 0, 0, started)

    kg_path = str(Path(palace_path).parent / "knowledge_graph.sqlite3")
    work_ids = _select_work_ids(all_ids=all_ids, kg_path=kg_path)
    if not work_ids:
        return _result(0, 0, 0, started)

    mention_map, freq_by_name = _walk_corpus(col, work_ids=work_ids, cfg=cfg)

    # ── Stage B: load registry, classify, promote ────────────────────
    from .entity_registry import EntityRegistry

    palace_dir = Path(palace_path).parent
    registry = EntityRegistry.load(palace_dir)

    # Determine which drawer_ids are needed for Stage B scoring
    candidates_to_score = [
        name for name in freq_by_name if registry.lookup(name).get("type") == "unknown"
    ]
    sample_n = cfg.entity_score_sample_drawers
    score_drawer_ids: set[str] = set()
    for name in candidates_to_score:
        score_drawer_ids.update(sorted(mention_map.get(name, ()))[:sample_n])

    text_by_id = _build_text_cache(col, drawer_ids=score_drawer_ids, cfg=cfg)

    promoted = _classify_and_promote(
        mention_map=mention_map,
        freq_by_name=freq_by_name,
        text_by_id=text_by_id,
        registry=registry,
        cfg=cfg,
    )
    registry.save()

    # Stage C lands in Task 6 — triples_written stays 0 for now
    return _result(
        drawers_scanned=len(work_ids),
        entities_promoted=len(promoted),
        triples_written=0,
        started=started,
    )


def _select_work_ids(*, all_ids: list[str], kg_path: str) -> list[str]:
    """all_ids − done_ids (this-adapter triples). Returns a list (Stage A
    iterates it). Order matches all_ids minus removed entries."""
    done_ids = _query_done_ids(kg_path=kg_path)
    return [i for i in all_ids if i not in done_ids]


def _query_done_ids(*, kg_path: str) -> set[str]:
    """Pull source_drawer_ids of triples written by this adapter."""
    if not Path(kg_path).exists():
        return set()
    try:
        with sqlite3.connect(kg_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT source_drawer_id
                FROM triples
                WHERE adapter_name = ?
                  AND source_drawer_id IS NOT NULL
                """,
                (ADAPTER_NAME,),
            ).fetchall()
        return {row[0] for row in rows}
    except sqlite3.Error:
        # Missing table on first run is normal — KnowledgeGraph creates schema
        # on its own first write. Treat any read error here as "nothing done".
        return set()


def _walk_corpus(col, *, work_ids: Iterable[str], cfg) -> tuple[dict, Counter]:
    """Stage A: single regex pass per drawer. Returns
    ``(mention_map, freq_by_name)`` where mention_map is
    ``name → set[drawer_id]`` and freq_by_name is corpus-wide name counts."""
    mention_map: dict[str, set[str]] = defaultdict(set)
    freq_by_name: Counter = Counter()

    for batch in batched(work_ids, 1000):
        for row in col.get_by_ids(batch):
            per_drawer = entity_detector.extract_candidates(row["text"], cfg.languages)
            for name, count in per_drawer.items():
                mention_map[name].add(row["id"])
                freq_by_name[name] += count

    return dict(mention_map), freq_by_name


def _build_text_cache(col, *, drawer_ids: set[str], cfg) -> dict[str, str]:
    """Batched bulk fetch. Returns ``{drawer_id: text}`` for the requested
    ids. Skips the LanceDB vector + metadata columns by reading text only
    from each returned row."""
    if not drawer_ids:
        return {}
    batch_size = cfg.entity_fetch_batch_size
    text_by_id: dict[str, str] = {}
    for batch in batched(sorted(drawer_ids), batch_size):
        for row in col.get_by_ids(batch):
            text_by_id[row["id"]] = row["text"]
    return text_by_id


def _classify_and_promote(
    *,
    mention_map: dict,
    freq_by_name: Counter,
    text_by_id: dict,
    registry,
    cfg,
) -> set[str]:
    """Stage B: score each unregistered candidate against a per-candidate
    sample of ~SAMPLE_N drawer texts. Classify. Promote if confident,
    else drop from mention_map.

    Returns the set of names newly added to the registry by this call.
    Mutates ``mention_map`` (deletes rejected entries) and ``registry``
    (adds learned entries). Caller is responsible for ``registry.save()``.
    """
    sample_n = cfg.entity_score_sample_drawers
    threshold = cfg.entity_promote_threshold
    languages = cfg.languages

    candidates_to_score = [
        name for name in freq_by_name if registry.lookup(name).get("type") == "unknown"
    ]

    promoted: set[str] = set()
    for name in candidates_to_score:
        sample_ids = sorted(mention_map.get(name, ()))[:sample_n]
        sample_texts = [text_by_id[did] for did in sample_ids if did in text_by_id]
        if not sample_texts:
            # Defensive: no usable sample → reject
            if name in mention_map:
                del mention_map[name]
            continue
        sample = "\n".join(sample_texts)
        scores = entity_detector.score_entity(name, sample, sample.splitlines(), languages)
        cls = entity_detector.classify_entity(name, freq_by_name[name], scores)

        if cls["type"] in ("person", "project") and cls["confidence"] >= threshold:
            registry.add_learned(name, type=cls["type"], confidence=cls["confidence"])
            promoted.add(name)
        else:
            if name in mention_map:
                del mention_map[name]

    return promoted


def _result(
    drawers_scanned: int,
    entities_promoted: int,
    triples_written: int,
    started: float,
) -> dict:
    return {
        "drawers_scanned": drawers_scanned,
        "entities_promoted": entities_promoted,
        "triples_written": triples_written,
        "elapsed_s": round(time.time() - started, 2),
    }
