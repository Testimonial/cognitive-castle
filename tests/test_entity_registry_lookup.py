"""Tests for EntityRegistry.lookup_in_text."""

import pytest

from cognitive_castle.entity_registry import EntityRegistry, EntityMatch  # noqa: F401


@pytest.fixture
def registry(tmp_path):
    reg = EntityRegistry(EntityRegistry._empty(), path=tmp_path / "entities.json")
    # Seed directly via _data — no set_people/set_projects methods exist.
    reg._data["people"] = {
        "Alice": {
            "source": "onboarding",
            "contexts": ["personal"],
            "aliases": [],
            "relationship": "friend",
            "confidence": 1.0,
        },
        "Bob": {
            "source": "onboarding",
            "contexts": ["personal"],
            "aliases": [],
            "relationship": "colleague",
            "confidence": 1.0,
        },
    }
    reg._data["projects"] = ["cognitive-castle", "deep-learning-course"]
    reg.save()
    return reg


def test_exact_match_person(registry):
    matches = registry.lookup_in_text("Did Alice say something interesting?")
    assert any(m.entity_id == "Alice" and m.matched_token == "Alice" for m in matches)


def test_exact_match_project(registry):
    matches = registry.lookup_in_text("Working on cognitive-castle today.")
    assert any(m.entity_id == "cognitive-castle" for m in matches)


def test_case_insensitive(registry):
    matches = registry.lookup_in_text("alice came over")
    assert any(m.entity_id == "Alice" for m in matches)


def test_fuzzy_match_within_distance(registry):
    matches = registry.lookup_in_text("Alise was here", max_edit_distance=1)
    # 'Alise' vs 'Alice' is edit distance 1.
    assert any(m.entity_id == "Alice" and m.edit_distance == 1 for m in matches)


def test_no_match_returns_empty(registry):
    assert registry.lookup_in_text("Random query about nothing.") == []


def test_strict_match_when_distance_zero(registry):
    matches = registry.lookup_in_text("Alise was here", max_edit_distance=0)
    # Edit distance 1 is not allowed when max_edit_distance=0.
    assert not any(m.entity_id == "Alice" for m in matches)
