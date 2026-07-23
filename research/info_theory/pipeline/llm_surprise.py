"""Estimator C: llm_surprise via claude-cli. Single-call orchestration
+ JSON parsing. Resumable batch processing in process_subsample()."""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"^```(?:json)?\n?|\n?```$", re.MULTILINE)


def build_prompt(priors: list, target: dict) -> str:
    """User-prompt assembly. System prompt set by caller."""
    prior_text = "\n\n".join(f"[Entry {i + 1}]\n{p['text']}" for i, p in enumerate(priors))
    return (
        f"Given these 20 prior memory entries:\n\n{prior_text}\n\n"
        f"Rate on a 1-10 scale how predictable the following entry is:\n\n"
        f"[Target]\n{target['text']}\n\n"
        f"10 = entirely derivable from priors, 1 = entirely novel.\n"
        f'Return JSON: {{"score": int, "reasoning": short str}}.'
    )


SYSTEM_PROMPT = (
    "You are a retrieval-quality rater. Respond with valid JSON only, no prose, no markdown fences."
)


def parse_response(raw: str) -> dict:
    """Strip markdown fences, parse JSON, validate."""
    cleaned = _FENCE.sub("", raw.strip())
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"malformed JSON: {e}; raw={raw[:200]!r}") from e
    if "score" not in parsed:
        raise ValueError(f"missing 'score' field: {parsed}")
    score = parsed["score"]
    if not (1 <= int(score) <= 10):
        raise ValueError(f"score {score} not in [1,10]")
    return {"score": int(score), "reasoning": parsed.get("reasoning", "")}


def llm_surprise_one(priors: list, target: dict, provider) -> dict:
    """One call to the provider; returns a full output-schema record."""
    user = build_prompt(priors, target)
    resp = provider.classify(SYSTEM_PROMPT, user, json_mode=True)
    parsed = parse_response(resp.text)
    return {
        "drawer_id": target["drawer_id"],
        "llm_surprise": float(10 - parsed["score"]),
        "llm_surprise_reasoning_spotcheck": parsed["reasoning"],
        "llm_surprise_prompt_tokens": getattr(resp, "input_tokens", None),
        "llm_surprise_completion_tokens": getattr(resp, "completion_tokens", None),
        "llm_surprise_cost_usd": (resp.raw or {}).get("total_cost_usd"),
    }
