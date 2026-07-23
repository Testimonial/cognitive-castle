"""Dry-run cost estimator. Samples 10 drawers, measures input-token
count, multiplies by stratified subsample size and current Haiku
pricing. Prints upper/lower bounds based on observed variance."""

from __future__ import annotations

import numpy as np
import tiktoken

_ENC = tiktoken.get_encoding("cl100k_base")


def _haiku_price_per_1k() -> dict:
    """Pinned Haiku 4.5 pricing as of 2026-05-16. USD per 1k tokens."""
    return {"input": 0.0008, "output": 0.004}


def _sample_drawers(n_samples: int = 10):
    """Stub — replaced in test patches. Production: load real drawers."""
    raise NotImplementedError("set via test patch or call load_palace first")


def estimate_cost(stage: str, n_samples: int = 10, target_calls: int = 1000) -> dict:
    """Returns {lo, mean, hi} USD estimate."""
    if stage != "llm-surprise":
        return {"lo": 0.0, "mean": 0.0, "hi": 0.0, "note": "non-LLM stage"}
    samples = _sample_drawers(n_samples)
    token_counts = [len(_ENC.encode(d["text"])) for d in samples]
    prices = _haiku_price_per_1k()
    # Per call: 20 priors × 500 tokens avg + instructions ~200 + target ~500
    # The samples here approximate target tokens; multiply for priors+instructions
    per_call_tokens = [t + 10000 + 200 for t in token_counts]  # rough
    per_call_cost = [
        t / 1000 * prices["input"] + 100 / 1000 * prices["output"] for t in per_call_tokens
    ]
    mean = float(np.mean(per_call_cost) * target_calls)
    sd = float(np.std(per_call_cost) * target_calls)
    return {
        "lo": max(0.0, mean - 1.96 * sd),
        "mean": mean,
        "hi": mean + 1.96 * sd,
    }
