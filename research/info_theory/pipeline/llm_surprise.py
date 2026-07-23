"""Estimator C: llm_surprise via claude-cli. Single-call orchestration
+ JSON parsing. Resumable batch processing in process_subsample()."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

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


class CostCapExceeded(Exception):
    """Raised when cumulative cost would exceed --max-cost."""


def process_subsample(
    targets: list,
    priors_lookup: dict,
    provider,
    partials_dir: Path,
    max_cost: float = 200.0,
    merge_every: int = 50,
) -> None:
    """Resumable C-stage processing.

    - One Parquet per completed drawer in partials_dir/{drawer_id}.parquet
    - Skip targets whose partial already exists
    - Track cumulative total_cost_usd; raise CostCapExceeded before exceeding max_cost
    - Print last (drawer_id, score, reasoning) every merge_every calls
    """
    partials_dir = Path(partials_dir)
    partials_dir.mkdir(parents=True, exist_ok=True)
    done_ids = {f.stem for f in partials_dir.glob("*.parquet")}
    cumulative = 0.0

    for i, target in enumerate(targets):
        if target["drawer_id"] in done_ids:
            continue
        priors = priors_lookup[target["drawer_id"]]
        result = llm_surprise_one(priors, target, provider)
        cost = result.get("llm_surprise_cost_usd") or 0.0
        if cumulative + cost > max_cost:
            raise CostCapExceeded(
                f"would exceed max_cost={max_cost} (cumulative={cumulative + cost:.4f})"
            )
        cumulative += cost
        pq.write_table(
            pa.table({k: [v] for k, v in result.items()}),
            partials_dir / f"{target['drawer_id']}.parquet",
        )
        if (i + 1) % merge_every == 0:
            print(
                f"[{i + 1}/{len(targets)}] {target['drawer_id']} "
                f"score={10 - result['llm_surprise']} cumulative=${cumulative:.2f}"
            )
            print(f"  reasoning: {result['llm_surprise_reasoning_spotcheck'][:120]}")


def merge_partials(partials_dir: Path, output: Path) -> None:
    """Atomic merge: write to .tmp then rename."""
    partials_dir = Path(partials_dir)
    output = Path(output)
    files = sorted(partials_dir.glob("*.parquet"))
    if not files:
        return
    tables = [pq.read_table(f) for f in files]
    merged = pa.concat_tables(tables, promote_options="default")
    tmp = output.with_suffix(".tmp")
    pq.write_table(merged, tmp)
    tmp.rename(output)
