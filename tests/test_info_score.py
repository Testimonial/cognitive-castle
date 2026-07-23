"""Unit tests for `cognitive_castle.info_score`."""

from unittest.mock import MagicMock, patch

import pytest

from cognitive_castle.info_score import (
    InfoScoreResult,
    Neighbour,
    _band_from_novelty,
    score_novelty,
)


def test_band_low_medium_high():
    assert _band_from_novelty(0.0) == "low"
    assert _band_from_novelty(0.05) == "low"
    assert _band_from_novelty(0.09999) == "low"
    assert _band_from_novelty(0.10) == "medium"
    assert _band_from_novelty(0.49999) == "medium"
    assert _band_from_novelty(0.50) == "high"
    assert _band_from_novelty(1.5) == "high"


def test_empty_text_raises():
    with pytest.raises(ValueError, match="non-empty"):
        score_novelty("")
    with pytest.raises(ValueError, match="non-empty"):
        score_novelty("   \n\t  ")


def test_score_novelty_returns_expected_shape():
    """Query embedded, backend queried, result correctly composed."""
    mock_backend = MagicMock()
    # Simulate a LanceDB-style hit list. `_distance` is cosine distance (1-cos).
    mock_backend.vector_search.return_value = [
        {
            "id": "d1",
            "text": "existing drawer content",
            "wing": "w",
            "room": "r",
            "_distance": 0.2,  # cos = 0.8
        },
        {
            "id": "d2",
            "text": "another drawer",
            "wing": "w",
            "room": "r",
            "_distance": 0.5,  # cos = 0.5
        },
    ]

    with (
        patch("cognitive_castle.embedding.embed_texts", return_value=[[0.1] * 1024]),
        patch("cognitive_castle.palace.get_collection", return_value=mock_backend),
    ):
        result = score_novelty("some query text", palace_path="/tmp/palace-mock")

    assert isinstance(result, InfoScoreResult)
    # novelty = 1 - max_cos = 1 - 0.8 = 0.2 → medium band
    assert abs(result.novelty - 0.2) < 1e-9
    assert result.band == "medium"
    assert len(result.neighbours) == 2
    assert result.neighbours[0].drawer_id == "d1"
    assert abs(result.neighbours[0].cosine - 0.8) < 1e-9


def test_score_novelty_empty_palace_returns_max_novelty():
    """No hits from the backend → nothing to compare against → novelty = 1.0 (high)."""
    mock_backend = MagicMock()
    mock_backend.vector_search.return_value = []
    with (
        patch("cognitive_castle.embedding.embed_texts", return_value=[[0.1] * 1024]),
        patch("cognitive_castle.palace.get_collection", return_value=mock_backend),
    ):
        result = score_novelty("first drawer ever", palace_path="/tmp/palace-mock")
    assert result.novelty == 1.0
    assert result.band == "high"
    assert result.neighbours == []


def test_wing_filter_reaches_backend_where_clause():
    mock_backend = MagicMock()
    mock_backend.vector_search.return_value = []
    with (
        patch("cognitive_castle.embedding.embed_texts", return_value=[[0.1] * 1024]),
        patch("cognitive_castle.palace.get_collection", return_value=mock_backend),
    ):
        score_novelty("q", palace_path="/tmp/p", wing="projects")
    _, kwargs = mock_backend.vector_search.call_args
    assert kwargs.get("where") == "wing = 'projects'"


def test_as_dict_serialises_neighbours_with_excerpt_truncation():
    long_text = "x" * 250
    result = InfoScoreResult(
        novelty=0.3,
        band="medium",
        neighbours=[Neighbour(drawer_id="d1", text=long_text, cosine=0.7)],
    )
    d = result.as_dict()
    assert d["novelty"] == 0.3
    assert d["band"] == "medium"
    n = d["neighbours"][0]
    # Long text got truncated to 200 chars + "…"
    assert n["text_excerpt"].endswith("…")
    assert len(n["text_excerpt"]) == 201
