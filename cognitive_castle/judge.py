"""judge.py — Stage 4 LLM-as-judge re-ranker (opt-in).

Takes a query + N candidate snippets, asks the configured LLM to rank
them by relevance, returns the LLM's preferred ordering as a list of
candidate indices.

Identity-order fallback on every failure mode (malformed JSON, missing
key, validation failure, LLM call error). Search ALWAYS returns
results — never crashes due to judge failure.

Mirrors the structure of cognitive_castle/reranker.py.
"""

from __future__ import annotations

import json
import sys

# 600-char truncation. Hardcoded constant per spec — at-least-as-much-context
# as the cross-encoder at Stage 3 (which sees ~2000 chars). Promoting to
# config is YAGNI until benchmarks show it matters.
SNIPPET_CHARS = 600


_SYSTEM_PROMPT = (
    "You are a retrieval re-ranking assistant. Given a user query and "
    "{n} candidate document snippets, return the indices of the candidates "
    "in order from most to least relevant. Output ONLY JSON in this exact "
    'shape: {{"ranked_indices": [I0, I1, ..., I{last}]}} where each I is the '
    "original 0-based candidate index. Each index appears exactly once. "
    "No prose, no explanation."
)


def _get_provider(cfg):
    """Construct an LLMProvider from cfg using the existing llm_client factory.

    Reads the 5 llm_* properties from cfg and calls
    cognitive_castle.llm_client.get_provider(...). Tests mock THIS helper
    to inject a fake provider — see tests/test_judge.py.
    """
    from .llm_client import get_provider

    return get_provider(
        name=cfg.llm_provider,
        model=cfg.llm_model,
        endpoint=cfg.llm_endpoint,
        api_key=cfg.llm_api_key,
        timeout=cfg.llm_timeout,
    )


def _build_prompts(query: str, candidates: list[str]) -> tuple[str, str]:
    """Build (system, user) prompts for the LLM. Truncates snippets to SNIPPET_CHARS."""
    n = len(candidates)
    system = _SYSTEM_PROMPT.format(n=n, last=n - 1)
    lines = ["Query: " + query, "", "Candidates:"]
    for i, doc in enumerate(candidates):
        lines.append(f"[{i}] {doc[:SNIPPET_CHARS]}")
    user = "\n".join(lines)
    return system, user


def _validate_ranked_indices(parsed, n: int) -> tuple[bool, str]:
    """Return (ok, reason). reason is empty on success, else a short diagnostic."""
    if not isinstance(parsed, dict):
        return False, f"response is not a JSON object (got {type(parsed).__name__})"
    if "ranked_indices" not in parsed:
        return False, "missing 'ranked_indices' key"
    indices = parsed["ranked_indices"]
    if not isinstance(indices, list):
        return False, f"'ranked_indices' is not a list (got {type(indices).__name__})"
    if len(indices) != n:
        return False, f"wrong count: got {len(indices)} indices, expected {n}"
    if not all(isinstance(i, int) for i in indices):
        return False, "indices contain non-int values"
    if set(indices) != set(range(n)):
        return False, "indices are not a permutation of range(n) (duplicates or out-of-range)"
    return True, ""


def _warn(reason: str) -> None:
    """Print the fallback warning to stderr in the spec's exact format."""
    print(
        f"[judge] {reason}: falling back to cross-encoder ordering",
        file=sys.stderr,
    )


def judge(query: str, candidates: list[str], cfg) -> list[int]:
    """Return the LLM-preferred ordering of candidate indices.

    Args:
        query: The user's search query.
        candidates: List of candidate document snippets.
        cfg: A config-like object exposing the .llm_* properties.

    Returns:
        list[int]: ordering of candidate indices, e.g. [3, 1, 5, ...].
        On any failure (LLM error, malformed JSON, validation failure):
        returns list(range(len(candidates))) — the identity ordering,
        which preserves the cross-encoder's Stage 3 ranking.

    Never raises. Search continues with degraded behavior on LLM failure.
    """
    n = len(candidates)
    # Short-circuit: nothing to rerank.
    if n <= 1:
        return list(range(n))

    system, user = _build_prompts(query, candidates)

    try:
        provider = _get_provider(cfg)
        response = provider.classify(system, user, json_mode=True)
    except Exception as e:
        _warn(f"LLM call failed ({type(e).__name__}: {e})")
        return list(range(n))

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError:
        snippet = response.text[:100].replace("\n", " ")
        _warn(f"malformed JSON response: {snippet!r}")
        return list(range(n))

    ok, reason = _validate_ranked_indices(parsed, n)
    if not ok:
        _warn(reason)
        return list(range(n))

    return list(parsed["ranked_indices"])
