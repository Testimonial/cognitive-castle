"""Tests for KnowledgeGraph.find_drawers_by_entities."""

import pytest

from cognitive_castle.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg_with_drawers(tmp_path):
    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.sqlite"))
    kg.add_entity("Alice", "person")
    kg.add_entity("Bob", "person")
    kg.add_entity("Carol", "person")
    # Drawer d1 mentions Alice; d2 mentions Alice + Bob; d3 mentions Bob; d4 mentions Carol only.
    kg.add_triple("Alice", "mentioned_in", "d1", source_drawer_id="d1", adapter_name="test")
    kg.add_triple("Alice", "mentioned_in", "d2", source_drawer_id="d2", adapter_name="test")
    kg.add_triple("Bob", "mentioned_in", "d2", source_drawer_id="d2", adapter_name="test")
    kg.add_triple("Bob", "mentioned_in", "d3", source_drawer_id="d3", adapter_name="test")
    kg.add_triple("Carol", "mentioned_in", "d4", source_drawer_id="d4", adapter_name="test")
    return kg


def test_single_entity(kg_with_drawers):
    out = kg_with_drawers.find_drawers_by_entities(["Alice"])
    assert set(out) == {"d1", "d2"}


def test_multiple_entities_returns_union(kg_with_drawers):
    out = kg_with_drawers.find_drawers_by_entities(["Alice", "Bob"])
    assert set(out) == {"d1", "d2", "d3"}


def test_match_count_ordering(kg_with_drawers):
    """Drawers tagged with more of the queried entities rank first."""
    out = kg_with_drawers.find_drawers_by_entities(["Alice", "Bob"])
    # d2 has both Alice + Bob; d1 only Alice; d3 only Bob.
    # d2 should appear first.
    assert out[0] == "d2"


def test_unknown_entity_returns_empty(kg_with_drawers):
    assert kg_with_drawers.find_drawers_by_entities(["Nobody"]) == []


def test_empty_input_returns_empty(kg_with_drawers):
    assert kg_with_drawers.find_drawers_by_entities([]) == []


def test_limit_caps_results(kg_with_drawers):
    out = kg_with_drawers.find_drawers_by_entities(["Alice"], limit=1)
    assert len(out) == 1
