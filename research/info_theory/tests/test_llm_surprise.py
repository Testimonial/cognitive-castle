from unittest.mock import MagicMock

import pytest

from pipeline.llm_surprise import (
    SYSTEM_PROMPT,
    build_prompt,
    llm_surprise_one,
    parse_response,
)


def test_build_prompt_includes_priors_and_target():
    priors = [{"text": "prior one"}, {"text": "prior two"}]
    target = {"text": "the target drawer"}
    user_prompt = build_prompt(priors, target)
    assert "prior one" in user_prompt
    assert "prior two" in user_prompt
    assert "the target drawer" in user_prompt
    assert "1-10" in user_prompt or "1–10" in user_prompt


def test_parse_response_valid_json():
    raw = '{"score": 7, "reasoning": "somewhat predictable"}'
    parsed = parse_response(raw)
    assert parsed["score"] == 7
    assert parsed["reasoning"] == "somewhat predictable"


def test_parse_response_strips_markdown_fences():
    raw = '```json\n{"score": 3, "reasoning": "novel"}\n```'
    parsed = parse_response(raw)
    assert parsed["score"] == 3


def test_parse_response_strips_bare_fences_without_language_hint():
    # Extra coverage: LLMs sometimes emit plain ``` fences with no `json` hint.
    # The _FENCE regex claims to handle both; verify the bare form.
    raw = '```\n{"score": 5, "reasoning": "mid"}\n```'
    parsed = parse_response(raw)
    assert parsed["score"] == 5
    assert parsed["reasoning"] == "mid"


def test_parse_response_raises_on_malformed():
    with pytest.raises(ValueError):
        parse_response("not json at all")


def test_parse_response_raises_on_out_of_range_score():
    with pytest.raises(ValueError):
        parse_response('{"score": 11, "reasoning": "bad"}')
    with pytest.raises(ValueError):
        parse_response('{"score": 0, "reasoning": "bad"}')


def test_parse_response_raises_on_missing_score_field():
    # Extra coverage: the implementation explicitly checks for "score" absence
    # before range validation. Guard against a regression that would let a
    # KeyError leak out instead of the intended ValueError.
    with pytest.raises(ValueError):
        parse_response('{"reasoning": "no score here"}')


def test_llm_surprise_one_returns_full_record():
    priors = [{"text": "p"}]
    target = {"drawer_id": "d1", "text": "t"}
    fake_provider = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"score": 6, "reasoning": "ok"}'
    fake_response.raw = {"total_cost_usd": 0.05}
    fake_response.input_tokens = 1000
    fake_response.completion_tokens = 50
    fake_provider.classify.return_value = fake_response

    out = llm_surprise_one(priors, target, provider=fake_provider)
    assert out["drawer_id"] == "d1"
    assert out["llm_surprise"] == 4.0  # 10 - 6
    assert out["llm_surprise_reasoning_spotcheck"] == "ok"
    assert out["llm_surprise_cost_usd"] == 0.05
    assert out["llm_surprise_prompt_tokens"] == 1000
    assert out["llm_surprise_completion_tokens"] == 50

    # Verify the provider was called with the JSON-mode contract the plan specifies.
    fake_provider.classify.assert_called_once()
    call_args = fake_provider.classify.call_args
    assert call_args.args[0] == SYSTEM_PROMPT
    assert "t" in call_args.args[1]  # target text embedded in user prompt
    assert call_args.kwargs.get("json_mode") is True


def test_llm_surprise_one_tolerates_none_raw():
    # Extra coverage: the plan defensively guards `(resp.raw or {}).get(...)`.
    # Confirm that a provider returning raw=None yields cost_usd=None (not a crash).
    priors = [{"text": "p"}]
    target = {"drawer_id": "d2", "text": "t"}
    fake_provider = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"score": 10, "reasoning": "trivial"}'
    fake_response.raw = None
    fake_response.input_tokens = 500
    fake_response.completion_tokens = 20
    fake_provider.classify.return_value = fake_response

    out = llm_surprise_one(priors, target, provider=fake_provider)
    assert out["llm_surprise"] == 0.0  # 10 - 10
    assert out["llm_surprise_cost_usd"] is None
