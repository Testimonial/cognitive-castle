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

    # Stage B + Stage C added in Tasks 5 and 6. For now this task's
    # contract is: work-set + walker work end-to-end; B and C return zero.
    return _result(
        drawers_scanned=len(work_ids),
        entities_promoted=0,
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
