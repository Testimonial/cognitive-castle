"""Unit tests for the LLM-as-judge Stage 4 module."""

import json
from unittest.mock import MagicMock

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
