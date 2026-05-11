"""
test_searcher.py -- Tests for both search() (CLI) and search_memories() (API).

Uses the real ChromaDB fixtures from conftest.py for integration tests,
plus mock-based tests for error paths.
"""

from unittest.mock import patch

import pytest

from cognitive_castle.searcher import SearchError, search, search_memories


# ── search_memories (API) ──────────────────────────────────────────────


class TestSearchMemories:
    def test_basic_search(self, palace_path, seeded_collection):
        result = search_memories("JWT authentication", palace_path)
        assert "results" in result
        assert len(result["results"]) > 0
        assert result["query"] == "JWT authentication"

    def test_wing_filter(self, palace_path, seeded_collection):
        result = search_memories("planning", palace_path, wing="notes")
        assert all(r["wing"] == "notes" for r in result["results"])

    def test_room_filter(self, palace_path, seeded_collection):
        result = search_memories("database", palace_path, room="backend")
        assert all(r["room"] == "backend" for r in result["results"])

    def test_wing_and_room_filter(self, palace_path, seeded_collection):
        result = search_memories("code", palace_path, wing="project", room="frontend")
        assert all(r["wing"] == "project" and r["room"] == "frontend" for r in result["results"])

    def test_n_results_limit(self, palace_path, seeded_collection):
        result = search_memories("code", palace_path, n_results=2)
        assert len(result["results"]) <= 2

    def test_no_palace_returns_empty_results(self, tmp_path):
        """New pipeline degrades gracefully: empty results, no error dict."""
        result = search_memories("anything", str(tmp_path / "missing"))
        assert result.get("results", None) is not None
        assert result["results"] == []

    def test_result_fields(self, palace_path, seeded_collection):
        result = search_memories("authentication", palace_path)
        hit = result["results"][0]
        assert "text" in hit
        assert "wing" in hit
        assert "room" in hit
        assert "source_file" in hit
        assert "similarity" in hit
        assert isinstance(hit["similarity"], float)
        assert "created_at" in hit

    def test_created_at_contains_filed_at(self, palace_path, seeded_collection):
        """created_at surfaces the filed_at metadata from the drawer."""
        result = search_memories("JWT authentication", palace_path)
        hit = result["results"][0]
        assert hit["created_at"] == "2026-01-01T00:00:00"


    def test_search_memories_missing_palace_returns_empty(self, tmp_path):
        """search_memories on a non-existent palace returns empty results dict."""
        result = search_memories("test", str(tmp_path / "no_palace_here"))
        assert isinstance(result, dict)
        assert result.get("results") == []

    def test_search_memories_filters_in_result(self, palace_path, seeded_collection):
        result = search_memories("test", palace_path, wing="project", room="backend")
        assert result["filters"]["wing"] == "project"
        assert result["filters"]["room"] == "backend"

    def test_search_memories_returns_dict_with_results_key(self, tmp_path):
        """search_memories always returns a dict containing a 'results' key."""
        # A missing palace should return an empty results dict, not crash.
        result = search_memories("anything", str(tmp_path / "no_palace"))
        assert isinstance(result, dict)
        assert "results" in result


# ── tokenize safety ───────────────────────────────────────────────────


class TestTokenizeSafety:
    """Regression tests for None / empty document safety in _tokenize."""

    def test_tokenize_handles_none(self):
        from cognitive_castle.searcher import _tokenize

        assert _tokenize(None) == []

    def test_tokenize_handles_empty_string(self):
        from cognitive_castle.searcher import _tokenize

        assert _tokenize("") == []


# ── search() (CLI print function) ─────────────────────────────────────


class TestSearchCLI:
    def test_search_prints_results(self, palace_path, capsys):
        """`search()` prints a header and per-result block when hits exist."""
        fake_hits = [{
            "id": "d1", "text": "drawer content", "score": 0.8,
            "wing": "w", "room": "r", "source_file": "f.md",
        }]
        with patch("cognitive_castle.searcher._new_pipeline_search", return_value=fake_hits):
            search("query", palace_path)
        captured = capsys.readouterr()
        assert 'Results for: "query"' in captured.out
        assert "drawer content" in captured.out

    def test_search_with_wing_filter(self, palace_path, capsys):
        with patch("cognitive_castle.searcher._new_pipeline_search", return_value=[]) as mock_p:
            search("q", palace_path, wing="auth")
        mock_p.assert_called_once()
        args = mock_p.call_args.args
        assert "auth" in args

    def test_search_with_room_filter(self, palace_path, capsys):
        with patch("cognitive_castle.searcher._new_pipeline_search", return_value=[]) as mock_p:
            search("q", palace_path, room="2026")
        mock_p.assert_called_once()
        args = mock_p.call_args.args
        assert "2026" in args

    def test_search_with_wing_and_room(self, palace_path, capsys):
        with patch("cognitive_castle.searcher._new_pipeline_search", return_value=[]) as mock_p:
            search("q", palace_path, wing="auth", room="2026")
        mock_p.assert_called_once()
        args = mock_p.call_args.args
        assert "auth" in args
        assert "2026" in args

    def test_search_no_palace_raises(self, tmp_path):
        """If the palace doesn't exist, the pipeline raises; search() re-raises as SearchError."""
        with patch(
            "cognitive_castle.searcher._new_pipeline_search",
            side_effect=Exception("no palace"),
        ):
            with pytest.raises(SearchError):
                search("q", str(tmp_path / "nonexistent"))

    def test_search_no_results(self, palace_path, capsys):
        with patch("cognitive_castle.searcher._new_pipeline_search", return_value=[]):
            search("q", palace_path)
        captured = capsys.readouterr()
        assert 'No results found for: "q"' in captured.out

    def test_search_query_error_raises(self):
        with patch(
            "cognitive_castle.searcher._new_pipeline_search",
            side_effect=Exception("boom"),
        ):
            with pytest.raises(SearchError, match="boom"):
                search("q", "/fake")

    def test_search_n_results(self, palace_path, capsys):
        with patch("cognitive_castle.searcher._new_pipeline_search", return_value=[]) as mock_p:
            search("q", palace_path, n_results=3)
        mock_p.assert_called_once()
        args = mock_p.call_args.args
        assert 3 in args

    def test_search_shows_score(self, capsys):
        """CLI output displays the reranker score with label `score=`, not `cosine=`."""
        fake_hits = [{
            "id": "d1", "text": "x", "score": 0.7,
            "wing": "w", "room": "r", "source_file": "f.md",
        }]
        with patch("cognitive_castle.searcher._new_pipeline_search", return_value=fake_hits):
            search("foo", "/fake/path")
        captured = capsys.readouterr()
        assert "score=0.7" in captured.out
        assert "cosine=" not in captured.out

    def test_search_handles_none_metadata_without_crash(self, palace_path, capsys):
        """search() must not crash if a hit dict has missing keys."""
        fake_hits = [{
            "id": "d1", "text": "x", "score": 0.5,
            # Missing: wing, room, source_file
        }]
        with patch("cognitive_castle.searcher._new_pipeline_search", return_value=fake_hits):
            search("q", palace_path)  # should not raise
        captured = capsys.readouterr()
        assert "?" in captured.out


def test_cli_search_routes_through_new_pipeline(tmp_path, capsys):
    """`castle search` (CLI) goes through the 3-stage pipeline, not legacy vector-only."""
    fake_hits = [
        {
            "id": "d1",
            "text": "JWT authentication notes",
            "score": 0.92,
            "wing": "auth",
            "room": "2026",
            "source_file": "/tmp/foo/notes.md",
        },
    ]
    with patch(
        "cognitive_castle.searcher._new_pipeline_search",
        return_value=fake_hits,
    ) as mock_pipeline:
        search("authentication", str(tmp_path / "palace"), n_results=5)

    mock_pipeline.assert_called_once()
    kwargs = mock_pipeline.call_args.kwargs
    assert kwargs.get("is_hook_call") is False

    captured = capsys.readouterr()
    assert "score=0.92" in captured.out
    assert "cosine=" not in captured.out
    assert 'Results for: "authentication"' in captured.out
    assert "JWT authentication notes" in captured.out
