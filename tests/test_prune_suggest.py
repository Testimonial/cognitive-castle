"""Unit tests for `cognitive_castle.prune_suggest`."""

from unittest.mock import MagicMock, patch

from cognitive_castle.prune_suggest import (
    PruneCandidate,
    PruneSuggestion,
    _sample_drawers,
    suggest_candidates,
)


def test_sample_drawers_deterministic_seed():
    """Same seed → same sample."""
    drawers = [{"drawer_id": f"d{i}"} for i in range(100)]
    a = _sample_drawers(drawers, sample=10, seed=42)
    b = _sample_drawers(drawers, sample=10, seed=42)
    assert a == b


def test_sample_drawers_size_capped_at_population():
    """Requesting more than we have returns the whole list."""
    drawers = [{"drawer_id": f"d{i}"} for i in range(5)]
    out = _sample_drawers(drawers, sample=20, seed=0)
    assert len(out) == 5


def test_suggest_flags_below_threshold_ordered_ascending():
    """The candidates list is sorted by novelty ascending."""
    backend = MagicMock()

    # Two drawers, one very similar to a prior (low novelty), one novel.
    drawer_dup = {
        "id": "dup1",
        "vector": [1.0] * 1024,
        "wing": "w",
        "room": "r",
        "text": "duplicate content",
    }
    drawer_novel = {
        "id": "novel1",
        "vector": [0.5] * 1024,
        "wing": "w",
        "room": "r",
        "text": "novel content",
    }
    backend.get_all_drawers = MagicMock(return_value=[drawer_dup, drawer_novel])

    def fake_vs(vec, n_results=3, where=None):
        # For dup1 → its top hit (after self exclusion) is very close
        # For novel1 → next hit is far
        if vec[0] == 1.0:  # dup query
            return [
                {"id": "dup1", "_distance": 0.0},  # self
                {"id": "prior", "_distance": 0.05},  # cos ≈ 0.95, novelty ≈ 0.05
            ]
        return [
            {"id": "novel1", "_distance": 0.0},
            {"id": "far", "_distance": 0.8},  # cos ≈ 0.2, novelty ≈ 0.8
        ]

    backend.vector_search.side_effect = fake_vs

    with patch(
        "cognitive_castle.backends.registry.get_backend", return_value=backend
    ):
        result = suggest_candidates(palace_path="/tmp/p", sample=2, threshold=0.10)

    assert isinstance(result, PruneSuggestion)
    assert result.sampled == 2
    # Only dup1 falls below threshold=0.10
    assert len(result.candidates) == 1
    assert result.candidates[0].drawer_id == "dup1"
    assert result.candidates[0].nearest_neighbour_id == "prior"
    assert result.candidates[0].nearest_neighbour_cosine > 0.9


def test_suggest_skips_drawers_without_vectors():
    """Missing vector field → drawer silently skipped."""
    backend = MagicMock()
    backend.get_all_drawers = MagicMock(return_value=[{"id": "d1", "wing": "w"}])
    with patch(
        "cognitive_castle.backends.registry.get_backend", return_value=backend
    ):
        result = suggest_candidates(palace_path="/tmp/p", sample=1, threshold=0.10)
    assert result.candidates == []


def test_as_dict_truncates_long_text_excerpt():
    long_text = "y" * 300
    result = PruneSuggestion(
        sampled=1,
        threshold=0.10,
        candidates=[
            PruneCandidate(
                drawer_id="d1",
                wing="w",
                room=None,
                text=long_text,
                novelty=0.02,
                nearest_neighbour_id="d2",
                nearest_neighbour_cosine=0.98,
            )
        ],
    )
    d = result.as_dict()
    assert d["sampled"] == 1
    assert d["num_candidates"] == 1
    excerpt = d["candidates"][0]["text_excerpt"]
    assert excerpt.endswith("…")
    assert len(excerpt) == 201


def test_fallback_get_all_used_when_backend_lacks_bulk_read():
    """Backend without `get_all_drawers` still works via vector_search fallback."""
    backend = MagicMock(spec=["vector_search", "connect"])  # no get_all_drawers
    backend.vector_search.return_value = []  # empty palace
    with patch(
        "cognitive_castle.backends.registry.get_backend", return_value=backend
    ):
        result = suggest_candidates(palace_path="/tmp/p", sample=1, threshold=0.10)
    # First vector_search call is the fallback bulk read
    assert backend.vector_search.called
    assert result.sampled == 0
    assert result.candidates == []
