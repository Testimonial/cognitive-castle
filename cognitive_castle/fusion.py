"""fusion.py — weighted Reciprocal Rank Fusion + recency multiplier.

Pure functions, no I/O, no model loads. Inputs are simple data structures so
this module is trivially unit-testable in isolation from the retrieval
pipeline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CandidateRef:
    """A drawer reference produced by a single retrieval signal."""

    drawer_id: str
    timestamp_unix: float


@dataclass(frozen=True)
class ScoredCandidate:
    """A drawer reference with a fused score."""

    drawer_id: str
    timestamp_unix: float
    score: float
    contributing_signals: frozenset[str] = frozenset()


def weighted_rrf(
    rank_lists: dict[str, list[CandidateRef]],
    weights: dict[str, float],
    k_rrf: int = 60,
) -> list[ScoredCandidate]:
    """Compute weighted reciprocal rank fusion across multiple signals.

    For each drawer that appears in any signal's rank list, score is
    sum_{signal} weight[signal] / (k_rrf + rank_in_signal). Drawers absent
    from a signal contribute 0 from that signal. Returned in descending
    score order; ties broken by drawer_id for determinism.

    Parameters
    ----------
    rank_lists:
        Map of signal_name -> ordered list of candidates (best first, rank 1).
    weights:
        Map of signal_name -> weight applied to that signal's contribution.
        Signals present in rank_lists but absent here are treated as weight 0.
    k_rrf:
        RRF smoothing constant. Larger values compress score differences.

    Returns
    -------
    list[ScoredCandidate]
        All unique drawers seen, ordered by descending score.
    """
    scores: dict[str, float] = {}
    timestamps: dict[str, float] = {}
    contributing_signals_acc: dict[str, set[str]] = {}

    for signal_name, candidates in rank_lists.items():
        weight = weights.get(signal_name, 0.0)
        if weight == 0.0 or not candidates:
            # Still capture timestamps for drawers we'd otherwise miss.
            for cand in candidates:
                timestamps.setdefault(cand.drawer_id, cand.timestamp_unix)
            continue
        for rank, cand in enumerate(candidates, start=1):
            contribution = weight / (k_rrf + rank)
            scores[cand.drawer_id] = scores.get(cand.drawer_id, 0.0) + contribution
            timestamps.setdefault(cand.drawer_id, cand.timestamp_unix)
            contributing_signals_acc.setdefault(cand.drawer_id, set()).add(signal_name)

    return sorted(
        (
            ScoredCandidate(
                drawer_id=did,
                timestamp_unix=timestamps[did],
                score=score,
                contributing_signals=frozenset(contributing_signals_acc.get(did, set())),
            )
            for did, score in scores.items()
        ),
        key=lambda s: (-s.score, s.drawer_id),
    )


def apply_recency(
    scored: list[ScoredCandidate],
    now: datetime,
    tau_days: float,
    max_boost: float,
) -> list[ScoredCandidate]:
    """Multiply each candidate's score by a recency factor and re-sort.

    factor(age) = 1 + (max_boost - 1) * exp(-age_days / tau_days)

    A drawer at age=0 receives a multiplier of `max_boost`. Ancient drawers
    asymptote to multiplier 1.0. Returned in descending score order; ties
    broken by drawer_id for determinism.

    Parameters
    ----------
    scored:
        Candidates with fused scores from `weighted_rrf`.
    now:
        Reference time for age calculation. Tests pass a fixed value;
        production passes `datetime.now(timezone.utc)`.
    tau_days:
        Decay timescale in days. Larger means recency boost decays slower.
    max_boost:
        Cap on the recency multiplier (max_boost == 1.0 disables the boost).
    """
    now_unix = now.timestamp()
    delta_boost = max_boost - 1.0
    boosted: list[ScoredCandidate] = []
    for c in scored:
        age_days = max(0.0, (now_unix - c.timestamp_unix) / 86400.0)
        factor = 1.0 + delta_boost * math.exp(-age_days / tau_days)
        boosted.append(
            ScoredCandidate(
                drawer_id=c.drawer_id,
                timestamp_unix=c.timestamp_unix,
                score=c.score * factor,
                contributing_signals=c.contributing_signals,
            )
        )
    boosted.sort(key=lambda s: (-s.score, s.drawer_id))
    return boosted
