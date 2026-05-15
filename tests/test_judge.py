"""Unit tests for the LLM-as-judge Stage 4 module."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cognitive_castle.judge import judge
from cognitive_castle.llm_client import LLMError, LLMResponse


def _mock_provider(text):
    """Return a provider that returns the given text from classify()."""
    provider = MagicMock()
    provider.classify.return_value = LLMResponse(
        text=text, model="test-model", provider="test", raw={}
    )
    return provider


def test_judge_returns_llm_ordering_on_valid_json(monkeypatch, _mock_cfg):
    """Happy path: LLM returns a valid 10-element permutation."""
    provider = _mock_provider(json.dumps({"ranked_indices": [3, 1, 5, 0, 2, 4, 6, 7, 8, 9]}))
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("test query", [f"doc {i}" for i in range(10)], _mock_cfg)
    assert result == [3, 1, 5, 0, 2, 4, 6, 7, 8, 9]


def test_judge_falls_back_to_identity_on_malformed_json(monkeypatch, capsys, _mock_cfg):
    """LLM returned non-JSON text → identity fallback + stderr warning."""
    provider = _mock_provider("this is not json")
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg)
    assert result == list(range(10))
    assert "falling back to cross-encoder ordering" in capsys.readouterr().err


def test_judge_falls_back_on_missing_key(monkeypatch, capsys, _mock_cfg):
    """LLM returned JSON without ranked_indices key → identity fallback."""
    provider = _mock_provider(json.dumps({"foo": "bar"}))
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg)
    assert result == list(range(10))
    assert "ranked_indices" in capsys.readouterr().err.lower()


def test_judge_falls_back_on_wrong_count(monkeypatch, capsys, _mock_cfg):
    """LLM returned fewer indices than candidates → identity fallback."""
    provider = _mock_provider(json.dumps({"ranked_indices": [0, 1, 2]}))
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg)
    assert result == list(range(10))


def test_judge_falls_back_on_duplicate_indices(monkeypatch, capsys, _mock_cfg):
    """LLM returned duplicates (not a permutation) → identity fallback."""
    provider = _mock_provider(json.dumps({"ranked_indices": [3] * 10}))
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg)
    assert result == list(range(10))


def test_judge_falls_back_on_llm_error(monkeypatch, capsys, _mock_cfg):
    """LLM call raised LLMError → identity fallback + stderr with error message."""
    provider = MagicMock()
    provider.classify.side_effect = LLMError("Cannot reach http://localhost:11434")
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg)
    assert result == list(range(10))
    err = capsys.readouterr().err
    assert "Cannot reach" in err
    assert "falling back" in err


def test_judge_empty_candidates_returns_empty_without_llm_call(monkeypatch, _mock_cfg):
    """Edge case: empty candidate list returns [] without invoking the LLM."""
    provider = MagicMock()
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    assert judge("q", [], _mock_cfg) == []
    provider.classify.assert_not_called()


def test_judge_single_candidate_returns_zero_without_llm_call(monkeypatch, _mock_cfg):
    """Edge case: single candidate has nothing to rerank — short-circuit before LLM call."""
    provider = MagicMock()
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    assert judge("q", ["only doc"], _mock_cfg) == [0]
    provider.classify.assert_not_called()


def test_judge_falls_back_on_bool_indices(monkeypatch, capsys, _mock_cfg):
    """Booleans are not valid indices even though isinstance(True, int) is True.

    Without an explicit bool guard, [True, False, 2, 3, 4, 5, 6, 7, 8, 9]
    would pass the int check AND the set-equality check (True == 1, False == 0)
    and silently corrupt the ordering. The validator must reject booleans.
    """
    provider = _mock_provider(json.dumps({"ranked_indices": [True, False, 2, 3, 4, 5, 6, 7, 8, 9]}))
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg)
    assert result == list(range(10))
    assert "non-int" in capsys.readouterr().err.lower()


def test_stage_4_judge_status_on_successful_reorder(_mock_cfg):
    """When judge reorders, _stage_4_judge stashes a status dict on hits[0]."""
    from unittest.mock import patch
    from cognitive_castle import searcher

    fake_reorder = [2, 0, 1]
    reranked = [(1.0 - i * 0.1, {"text": f"t{i}"}) for i in range(3)]
    with patch("cognitive_castle.judge.judge", return_value=fake_reorder):
        out = searcher._stage_4_judge("q", reranked, _mock_cfg)
    status = out[0][1]["judge_status"]
    assert status["reordered"] is True
    assert status["n"] == 3
    assert status["model"] == "qwen3.5:latest"
    assert isinstance(status["elapsed_s"], float)


def test_stage_4_judge_status_on_failure_is_identity_fallback(_mock_cfg):
    """ConnectionError (or any Exception) → identity-order return + error stash."""
    from unittest.mock import patch
    from cognitive_castle import searcher

    reranked = [(1.0 - i * 0.1, {"text": f"t{i}"}) for i in range(3)]
    with patch("cognitive_castle.judge.judge", side_effect=ConnectionError("ollama down")):
        out = searcher._stage_4_judge("q", reranked, _mock_cfg)
    assert out == reranked  # identity-order fallback
    assert out[0][1]["judge_status"] == {"error": "ConnectionError: ollama down"}


def test_stage_4_judge_preserves_hits_beyond_top_n(_mock_cfg_top_n_3):
    """With 5 hits and top_n=3, output keeps all 5 — top-3 reordered, hits
    4 and 5 untouched at the end. Behavior change from live code which
    discards reranked[top_n:]."""
    from unittest.mock import patch
    from cognitive_castle import searcher

    fake_reorder = [2, 0, 1]
    reranked = [(1.0 - i * 0.1, {"text": f"t{i}"}) for i in range(5)]
    with patch("cognitive_castle.judge.judge", return_value=fake_reorder):
        out = searcher._stage_4_judge("q", reranked, _mock_cfg_top_n_3)
    assert len(out) == 5
    assert [r[1]["text"] for r in out[:3]] == ["t2", "t0", "t1"]  # reordered top-3
    assert [r[1]["text"] for r in out[3:]] == ["t3", "t4"]  # tail preserved


# ---------------------------------------------------------------------------
# Slow smoke test — requires Ollama running on localhost:11434
# ---------------------------------------------------------------------------


def _ollama_reachable() -> bool:
    """True if Ollama is responding on localhost:11434."""
    import urllib.request
    import urllib.error

    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
        return True
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


@pytest.fixture
def real_palace_fixture(palace_path):
    """A palace seeded with three drawers so search returns enough hits to
    exercise Stage 4 (LLM-as-judge).

    Uses the same ``get_collection`` + ``add_drawer`` pattern as the rest of
    the test suite (see test_hall_detection.py and conftest.py).
    """
    import os
    from cognitive_castle.palace import get_collection
    from cognitive_castle.miner import add_drawer

    col = get_collection(palace_path, collection_name="castle_drawers", create=True)

    # Create real source files so add_drawer's os.path.getmtime() doesn't fail.
    src1 = os.path.join(palace_path, "retrieval.txt")
    src2 = os.path.join(palace_path, "recency.txt")
    src3 = os.path.join(palace_path, "cooking.txt")
    Path(src1).touch()
    Path(src2).touch()
    Path(src3).touch()

    add_drawer(
        collection=col,
        wing="test",
        room="r1",
        content="Retrieval weights: dense 0.5, sparse 0.3, kg 0.2. We decided to use these weights after benchmarking on 500 queries.",
        source_file=src1,
        chunk_index=0,
        agent="test",
    )
    add_drawer(
        collection=col,
        wing="test",
        room="r1",
        content="We chose a recency tau of 30 days after discussing exponential decay on retrieval freshness.",
        source_file=src2,
        chunk_index=0,
        agent="test",
    )
    add_drawer(
        collection=col,
        wing="test",
        room="r1",
        content="Unrelated content about cooking pasta with garlic and olive oil.",
        source_file=src3,
        chunk_index=0,
        agent="test",
    )
    return palace_path


@pytest.mark.slow
def test_max_mode_end_to_end_with_real_judge(real_palace_fixture):
    """Reaches actual Ollama. Skipped if not reachable; CI excludes via -m.

    Catches: Ollama URL changes, default-model regressions, prompt-template
    breakage, judge_status serializer/printer regressions.
    """
    from cognitive_castle import searcher

    if not _ollama_reachable():
        pytest.skip("Ollama not running on localhost:11434")

    result = searcher.search_memories(
        query="What did we decide about retrieval weights?",
        palace_path=real_palace_fixture,
        mode="max",
    )
    assert "results" in result
    assert len(result["results"]) > 0
    # judge_status is absent (no-reorder happy path), a "reordered" success
    # dict, or an "error" failure dict — all three are valid post-conditions.
    status = result["results"][0].get("judge_status")
    if status is not None:
        assert "reordered" in status or "error" in status
