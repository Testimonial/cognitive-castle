"""Tests for cognitive_castle.kg_enricher (Phase 2 of mine())."""

from __future__ import annotations

from collections import Counter
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


def test_enrich_palace_happy_path_walks_drawers(tmp_path, monkeypatch):
    """End-to-end through _walk_corpus when work_ids is non-empty.
    Stage B + Stage C are not implemented in Task 4 — promoted/written stay 0."""
    import cognitive_castle.kg_enricher as kg_enricher

    rows = [
        {
            "id": "d1",
            "text": "Riley went home. Riley said hi. Riley laughed.",
            "wing": "p",
            "room": "r",
            "source_file": "f1",
        },
        {
            "id": "d2",
            "text": "Riley discussed code. Riley typed fast. Riley waved.",
            "wing": "p",
            "room": "r",
            "source_file": "f2",
        },
    ]
    monkeypatch.setattr(
        "cognitive_castle.palace.get_collection",
        lambda *a, **kw: FakeCollection(rows=rows),
    )

    # Use a fresh palace dir so kg_path doesn't exist yet → done_ids = empty
    palace_dir = tmp_path / ".castle" / "palace"
    palace_dir.mkdir(parents=True)

    result = kg_enricher.enrich_palace(str(palace_dir), _mock_cfg())

    assert result["drawers_scanned"] == 2
    assert result["entities_promoted"] == 0  # Stage B not yet implemented
    assert result["triples_written"] == 0  # Stage C not yet implemented
    assert isinstance(result["elapsed_s"], float)
    assert result["elapsed_s"] >= 0


def test_query_done_ids_returns_empty_on_corrupt_kg(tmp_path):
    """SQLite read errors degrade gracefully — _query_done_ids returns
    set() instead of raising."""
    import cognitive_castle.kg_enricher as kg_enricher

    # Write garbage bytes that aren't a valid SQLite file
    bad_kg = tmp_path / "knowledge_graph.sqlite3"
    bad_kg.write_bytes(b"not a sqlite db at all")

    result = kg_enricher._query_done_ids(kg_path=str(bad_kg))
    assert result == set()


# ── Stage B tests ────────────────────────────────────────────────────────


def test_classify_promotes_above_threshold(tmp_path, monkeypatch):
    """Stage B: a candidate with classifier confidence >= threshold and
    type in {person, project} gets added to the registry."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")

    # Stub classifier to return a clean "person, 0.9" verdict for "Riley"
    monkeypatch.setattr(
        "cognitive_castle.entity_detector.score_entity",
        lambda *a, **kw: {
            "person_score": 10,
            "project_score": 0,
            "person_signals": ["dialogue marker (3x)", "addressed directly (2x)"],
            "project_signals": [],
        },
    )

    mention_map = {"Riley": {"d1"}}
    freq_by_name = Counter({"Riley": 3})
    text_by_id = {"d1": "Riley went to the store."}

    promoted = kg_enricher._classify_and_promote(
        mention_map=mention_map,
        freq_by_name=freq_by_name,
        text_by_id=text_by_id,
        registry=registry,
        cfg=_mock_cfg(threshold=0.70),
    )

    assert "Riley" in promoted
    assert "Riley" in registry._data["people"]
    assert registry._data["people"]["Riley"]["source"] == "learned"


def test_classify_skips_unknown_uncertain(tmp_path, monkeypatch):
    """Below-threshold or 'uncertain' classifications drop the entry from
    mention_map (no triples will be written for them)."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")

    # Zero scores → classify_entity returns "uncertain"
    monkeypatch.setattr(
        "cognitive_castle.entity_detector.score_entity",
        lambda *a, **kw: {
            "person_score": 0,
            "project_score": 0,
            "person_signals": [],
            "project_signals": [],
        },
    )

    mention_map = {"weakword": {"d1"}}
    freq_by_name = Counter({"weakword": 1})
    text_by_id = {"d1": "weakword appears here."}

    promoted = kg_enricher._classify_and_promote(
        mention_map=mention_map,
        freq_by_name=freq_by_name,
        text_by_id=text_by_id,
        registry=registry,
        cfg=_mock_cfg(threshold=0.70),
    )

    assert not promoted
    assert "weakword" not in mention_map  # dropped


def test_classify_skips_already_registered(tmp_path, monkeypatch):
    """Pre-registered entities (lookup type != 'unknown') skip scoring
    entirely; they stay in mention_map untouched."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")
    registry._data["people"]["Riley"] = {
        "source": "onboarding",
        "contexts": ["personal"],
        "aliases": [],
        "relationship": "child",
        "confidence": 1.0,
    }

    # score_entity should not be called for Riley at all — stub to raise
    def _should_not_be_called(*a, **kw):
        raise AssertionError("score_entity called for known entity")

    monkeypatch.setattr(
        "cognitive_castle.entity_detector.score_entity",
        _should_not_be_called,
    )

    mention_map = {"Riley": {"d1", "d2"}}
    freq_by_name = Counter({"Riley": 5})
    text_by_id = {"d1": "x", "d2": "y"}

    promoted = kg_enricher._classify_and_promote(
        mention_map=mention_map,
        freq_by_name=freq_by_name,
        text_by_id=text_by_id,
        registry=registry,
        cfg=_mock_cfg(),
    )

    # No promotion happened, but Riley remains in mention_map for Stage C
    assert "Riley" in mention_map
    assert "Riley" not in promoted


def test_unknown_type_means_not_registered(tmp_path, monkeypatch):
    """Regression: lookup() returns {'type': 'unknown'} for missing entries.
    The check must compare against 'unknown' explicitly, not use truthiness
    (the truthy-check would skip every entry)."""
    import cognitive_castle.kg_enricher as kg_enricher
    from cognitive_castle.entity_registry import EntityRegistry

    registry = EntityRegistry(EntityRegistry._empty(), tmp_path / "reg.json")

    # Stub classifier to promote
    monkeypatch.setattr(
        "cognitive_castle.entity_detector.score_entity",
        lambda *a, **kw: {
            "person_score": 12,
            "project_score": 0,
            "person_signals": ["dialogue marker (3x)", "addressed directly (2x)"],
            "project_signals": [],
        },
    )

    mention_map = {"NewPerson": {"d1"}}
    freq_by_name = Counter({"NewPerson": 3})
    text_by_id = {"d1": "x"}

    promoted = kg_enricher._classify_and_promote(
        mention_map=mention_map,
        freq_by_name=freq_by_name,
        text_by_id=text_by_id,
        registry=registry,
        cfg=_mock_cfg(threshold=0.70),
    )

    # Promotion happened — proves lookup()['type'] == 'unknown' was recognized
    # as "not yet registered"
    assert "NewPerson" in promoted


def test_build_text_cache_respects_batch_size(monkeypatch):
    """_build_text_cache batches col.get_by_ids calls at entity_fetch_batch_size."""
    import cognitive_castle.kg_enricher as kg_enricher

    rows = [
        {"id": f"d{i}", "text": f"text {i}", "wing": "p", "room": "r", "source_file": "f"}
        for i in range(5)
    ]
    col = FakeCollection(rows)
    call_sizes = []
    original = col.get_by_ids

    def tracking(ids):
        ids_list = list(ids)
        call_sizes.append(len(ids_list))
        return original(ids_list)

    col.get_by_ids = tracking

    text_by_id = kg_enricher._build_text_cache(
        col,
        drawer_ids={f"d{i}" for i in range(5)},
        cfg=_mock_cfg(fetch_batch=2),
    )

    # 5 ids → batches of (2, 2, 1)
    assert sorted(call_sizes) == [1, 2, 2]
    assert len(text_by_id) == 5


def test_build_text_cache_empty():
    """Empty drawer_ids → empty dict, no fetch calls."""
    import cognitive_castle.kg_enricher as kg_enricher

    col = FakeCollection(rows=[])
    text_by_id = kg_enricher._build_text_cache(col, drawer_ids=set(), cfg=_mock_cfg())
    assert text_by_id == {}
