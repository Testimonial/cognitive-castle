"""Tests for cognitive_castle.kg_enricher (Phase 2 of mine())."""

from __future__ import annotations

from typing import Iterable
from unittest.mock import MagicMock



# ── Fixtures ─────────────────────────────────────────────────────────────


def _mock_cfg(
    *,
    threshold=0.70,
    sample_drawers=20,
    fetch_batch=1000,
    languages=("en",),
):
    """Minimal cfg exposing only the fields kg_enricher reads."""
    cfg = MagicMock()
    cfg.entity_promote_threshold = threshold
    cfg.entity_score_sample_drawers = sample_drawers
    cfg.entity_fetch_batch_size = fetch_batch
    cfg.languages = languages
    return cfg


class FakeCollection:
    """In-memory stand-in for a LanceDB collection."""

    def __init__(self, rows: list[dict]):
        self._rows = {r["id"]: r for r in rows}

    def list_drawer_ids(self) -> list[str]:
        return list(self._rows.keys())

    def get_by_ids(self, ids: Iterable[str]) -> list[dict]:
        return [self._rows[i] for i in ids if i in self._rows]


# ── Stage A tests ────────────────────────────────────────────────────────


def test_enrich_palace_returns_zeros_on_empty_palace(tmp_path, monkeypatch):
    """Empty palace → no work, returns {0, 0, 0, elapsed}."""
    import cognitive_castle.kg_enricher as kg_enricher

    monkeypatch.setattr(
        "cognitive_castle.palace.get_collection",
        lambda *a, **kw: FakeCollection(rows=[]),
    )

    result = kg_enricher.enrich_palace(str(tmp_path), _mock_cfg())

    assert result["drawers_scanned"] == 0
    assert result["entities_promoted"] == 0
    assert result["triples_written"] == 0
    assert "elapsed_s" in result


def test_walk_corpus_builds_mention_map_and_freq(tmp_path):
    """Stage A: for each drawer, extract candidates → populate mention_map
    and freq_by_name with corpus-wide counts."""
    import cognitive_castle.kg_enricher as kg_enricher

    rows = [
        {
            "id": "d1",
            # 3 occurrences of "Riley" → above the extract_candidates threshold
            "text": "Riley went to the store. Riley likes apples. Riley is happy.",
            "wing": "p",
            "room": "r",
            "source_file": "f1",
        },
        {
            "id": "d2",
            # 3 occurrences of "Riley" in this drawer too
            "text": "Riley discussed bge-m3 with Alice. Riley and Alice talked. Riley agreed.",
            "wing": "p",
            "room": "r",
            "source_file": "f2",
        },
    ]
    col = FakeCollection(rows)
    cfg = _mock_cfg()

    mention_map, freq_by_name = kg_enricher._walk_corpus(col, work_ids=["d1", "d2"], cfg=cfg)

    # mention_map: name → set of drawer_ids that mentioned it
    assert "d1" in mention_map.get("Riley", set())
    assert "d2" in mention_map.get("Riley", set())
    # freq_by_name: corpus-wide occurrence count
    assert freq_by_name.get("Riley", 0) >= 2  # at least 2 mentions


def test_walk_corpus_empty_work_ids(tmp_path):
    """Empty work_ids → empty mention_map and freq_by_name."""
    import cognitive_castle.kg_enricher as kg_enricher

    col = FakeCollection(rows=[])
    cfg = _mock_cfg()

    mention_map, freq_by_name = kg_enricher._walk_corpus(col, work_ids=[], cfg=cfg)
    assert len(mention_map) == 0
    assert len(freq_by_name) == 0


def test_walk_corpus_batches_at_1000(monkeypatch, tmp_path):
    """Stage A batches get_by_ids calls at 1000 per the spec."""
    import cognitive_castle.kg_enricher as kg_enricher

    rows = [
        {"id": f"d{i}", "text": "no entities here", "wing": "p", "room": "r", "source_file": "f"}
        for i in range(2500)
    ]
    col = FakeCollection(rows)
    call_sizes = []
    original_get_by_ids = col.get_by_ids

    def tracking_get_by_ids(ids):
        ids_list = list(ids)
        call_sizes.append(len(ids_list))
        return original_get_by_ids(ids_list)

    col.get_by_ids = tracking_get_by_ids

    kg_enricher._walk_corpus(col, work_ids=[f"d{i}" for i in range(2500)], cfg=_mock_cfg())

    # 2500 → batches of (1000, 1000, 500)
    assert call_sizes == [1000, 1000, 500]


def test_select_work_ids_excludes_adapter_done_drawers(tmp_path):
    """Drawers with this adapter's triples are excluded from work_ids;
    drawers with a DIFFERENT adapter's triples are still included."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.knowledge_graph import KnowledgeGraph

    kg_path = tmp_path / "knowledge_graph.sqlite3"
    kg = KnowledgeGraph(db_path=str(kg_path))
    kg.add_triple(
        "Riley",
        "mentioned_in",
        "d1",
        source_drawer_id="d1",
        adapter_name="entity-mention-indexer",
    )
    kg.add_triple(
        "Bob",
        "married_to",
        "Alice",
        source_drawer_id="d2",
        adapter_name="manual-castle-kg-add",  # different adapter
    )

    work_ids = kg_enricher._select_work_ids(all_ids=["d1", "d2", "d3"], kg_path=str(kg_path))

    # d1 covered by us → excluded. d2 covered by different adapter → included.
    # d3 has no triples → included.
    assert "d1" not in work_ids
    assert "d2" in work_ids
    assert "d3" in work_ids
