"""Tests for query_intent.classify_query."""

from __future__ import annotations


from cognitive_castle.query_intent import MEMORY_TYPES, classify_query


def test_classify_decision_query():
    assert classify_query("what did we decide about the embedder swap") == "decision"


def test_classify_milestone_query():
    assert classify_query("when did we ship the bge-m3 cutover") == "milestone"


def test_classify_preference_query():
    assert classify_query("my preference for terse commits") == "preference"


def test_classify_problem_query():
    assert classify_query("what's the bug in the search pipeline") == "problem"


def test_classify_emotional_query():
    assert classify_query("how do I feel about this PR") == "emotional"


def test_empty_query_returns_none():
    assert classify_query("") is None


def test_whitespace_only_query_returns_none():
    assert classify_query("   ") is None
    assert classify_query("\t\n") is None


def test_non_english_query_returns_none():
    """English-only patterns means Slovak/Czech/etc. queries don't classify."""
    assert classify_query("čo sme rozhodli o autentifikácii") is None


def test_overlap_resolves_to_most_specific():
    """When multiple patterns match, first-in-list wins (specificity-decreasing).

    'what shipped to fix the bug' matches BOTH milestone (shipped) AND problem (bug);
    milestone wins because it's earlier in _INTENT_PATTERNS.
    """
    assert classify_query("what shipped to fix the bug") == "milestone"


def test_memory_types_constant_matches_known_set():
    """Single-source-of-truth check: MEMORY_TYPES is derived from _INTENT_PATTERNS keys."""
    assert MEMORY_TYPES == frozenset(
        {"decision", "preference", "milestone", "problem", "emotional"}
    )
