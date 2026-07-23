"""Suggest low-information drawers as candidates for pruning.

Practical application of the v3.4.0 research finding: two dominant wings
in the reference palace held ~95% of drawers with the lowest median info
scores (0.06 and 0.07 for `_home_lbihari_cognitive_castle` and `projects`
respectively). Massive intra-wing repetition — a lot of near-duplicate
content Castle files anyway because the design principle is
"verbatim always, never destroy".

This module reads a random sample of drawers, scores each with
nn_novelty (cheap — the palace already has vectors from bge-m3), and
returns the lowest-scoring ones. Read-only — never touches the palace.
Users decide whether to actually prune.

Public API:

    suggest_candidates(palace_path, sample=200, threshold=0.10,
                       wing=None) -> PruneSuggestion

Nothing here embeds new text or writes to disk — memory footprint stays
small (one N×dim numpy matrix for the sampled vectors).
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import Optional

from .config import CognitiveCastleConfig


@dataclass
class PruneCandidate:
    """A single drawer flagged as a low-information duplicate risk."""

    drawer_id: str
    wing: Optional[str]
    room: Optional[str]
    text: str
    novelty: float
    nearest_neighbour_id: Optional[str]
    nearest_neighbour_cosine: float


@dataclass
class PruneSuggestion:
    """Result of scanning a sample of the palace for pruning candidates."""

    sampled: int
    threshold: float
    candidates: list[PruneCandidate]

    def as_dict(self) -> dict:
        return {
            "sampled": self.sampled,
            "threshold": self.threshold,
            "num_candidates": len(self.candidates),
            "candidates": [
                {
                    "drawer_id": c.drawer_id,
                    "wing": c.wing,
                    "room": c.room,
                    "novelty": c.novelty,
                    "nearest_neighbour_id": c.nearest_neighbour_id,
                    "nearest_neighbour_cosine": c.nearest_neighbour_cosine,
                    "text_excerpt": (c.text[:200] + "…") if len(c.text) > 200 else c.text,
                }
                for c in self.candidates
            ],
        }


def _sample_drawers(all_drawers: list[dict], sample: int, seed: int) -> list[dict]:
    """Deterministic reservoir sample. `seed` makes CI reproducible."""
    if sample >= len(all_drawers):
        return list(all_drawers)
    rng = random.Random(seed)
    return rng.sample(all_drawers, sample)


def suggest_candidates(
    palace_path: Optional[str] = None,
    sample: int = 200,
    threshold: float = 0.10,
    wing: Optional[str] = None,
    seed: int = 42,
) -> PruneSuggestion:
    """Sample drawers, score each with nn_novelty, return the low-info ones.

    Args:
        palace_path: filesystem path to the palace; defaults to Castle config.
        sample: how many drawers to sample. Higher = better coverage,
            more memory (each drawer's vector is 1024-dim float32).
        threshold: drawers with `novelty < threshold` are flagged. Default
            0.10 matches the "low" band from the v3.4.0 research.
        wing: optional wing filter — only sample within one wing.
        seed: RNG seed for reproducibility.

    Returns:
        PruneSuggestion with the sampled count, threshold, and flagged
        candidates sorted by novelty ascending (lowest = most duplicate-y).
    """
    from .backends.registry import get_backend

    cfg = CognitiveCastleConfig()
    palace = os.path.expanduser(palace_path) if palace_path else cfg.palace_path

    backend = get_backend(cfg)
    backend.connect(palace)

    all_drawers = backend.get_all_drawers(wing=wing) if hasattr(backend, "get_all_drawers") \
        else _fallback_get_all(backend, wing)

    sampled = _sample_drawers(all_drawers, sample, seed)

    candidates: list[PruneCandidate] = []
    for target in sampled:
        vec = target.get("vector")
        if not vec:
            continue
        # nn_novelty against top-2 (top-1 is likely the drawer itself if
        # LanceDB indexed it; take the next best).
        hits = backend.vector_search(
            list(vec),
            n_results=3,
            where=f"wing = '{target.get('wing')}'" if target.get("wing") else None,
        )
        # Filter self out (LanceDB has no exclusion — drop by ID).
        target_id = target.get("id") or target.get("drawer_id")
        other_hits = [h for h in hits if (h.get("id") or h.get("drawer_id")) != target_id]
        if not other_hits:
            continue
        nn = other_hits[0]
        cosine = 1.0 - float(nn.get("_distance", 1.0))
        novelty = 1.0 - cosine
        if novelty < threshold:
            candidates.append(
                PruneCandidate(
                    drawer_id=target_id or "?",
                    wing=target.get("wing"),
                    room=target.get("room"),
                    text=target.get("text", ""),
                    novelty=novelty,
                    nearest_neighbour_id=nn.get("id") or nn.get("drawer_id"),
                    nearest_neighbour_cosine=cosine,
                )
            )

    candidates.sort(key=lambda c: c.novelty)
    return PruneSuggestion(sampled=len(sampled), threshold=threshold, candidates=candidates)


def _fallback_get_all(backend, wing: Optional[str]) -> list[dict]:
    """When the backend doesn't expose get_all_drawers, use a large search.

    This is a degraded path — it fetches up to 10k drawers with an empty
    vector query. Not efficient at scale, but keeps prune-suggest working
    on backends that don't ship a bulk-read method.
    """
    where = f"wing = '{wing}'" if wing else None
    # Empty-vector search returns everything sorted by an arbitrary distance,
    # which is fine — we only need the drawer metadata + vectors.
    dim = 1024  # bge-m3 default; wrong dim will fail loudly, that's fine
    return backend.vector_search([0.0] * dim, n_results=10_000, where=where)
