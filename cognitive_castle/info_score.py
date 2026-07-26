"""Score the information content of a query against a palace.

Practical application of the research finding shipped in v3.4.0: the
`nn_novelty` estimator (Estimator A of the info-theory paper) — cheap,
O(1) per query, correlates at rho=0.982 with the LLE reconstruction
residual on a real 65k-drawer palace.

Given some text (a new drawer, a message, an arbitrary snippet) and a
palace, returns:

- a `novelty` score in `[0, 2]` where 0 means "identical to something
  already stored" and higher values mean "less overlap with the
  nearest neighbour"
- the top-k closest drawers with their cosine similarity
- an information-band label: `low` / `medium` / `high`

Uses Castle's default embedder (bge-m3, 1024-dim) and LanceDB backend
directly — no dependency on the `research/info_theory` subproject.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .config import CognitiveCastleConfig


@dataclass
class Neighbour:
    """A single nearest-neighbour hit for an info-score query."""

    drawer_id: str
    text: str
    cosine: float
    wing: Optional[str] = None
    room: Optional[str] = None


@dataclass
class InfoScoreResult:
    """Return shape of :func:`score_novelty`."""

    novelty: float
    band: str  # "low" | "medium" | "high"
    neighbours: list[Neighbour]

    def as_dict(self) -> dict:
        return {
            "novelty": self.novelty,
            "band": self.band,
            "neighbours": [
                {
                    "drawer_id": n.drawer_id,
                    "cosine": n.cosine,
                    "wing": n.wing,
                    "room": n.room,
                    "text_excerpt": (n.text[:200] + "…") if len(n.text) > 200 else n.text,
                }
                for n in self.neighbours
            ],
        }


def _band_from_novelty(novelty: float) -> str:
    """Coarse categorical label. Bands calibrated against the full-palace
    empirical distribution from the v3.4.0 research run (median novelty ~0.06
    on `_home_lbihari_cognitive_castle`, 75th percentile ~0.20)."""
    if novelty < 0.10:
        return "low"
    if novelty < 0.50:
        return "medium"
    return "high"


def score_novelty(
    text: str,
    palace_path: Optional[str] = None,
    top_k: int = 5,
    wing: Optional[str] = None,
) -> InfoScoreResult:
    """Return a novelty score for `text` against an existing palace.

    Novelty is `1 - max_cosine(query_vec, drawer_vec)` over the top-k
    nearest neighbours. Range `[0, 2]` (cosine can be negative for
    un-normalised vectors, though bge-m3 normalises so practical range
    is `[0, 1]`).

    Args:
        text: query drawer text.
        palace_path: filesystem path to the palace; defaults to Castle config.
        top_k: how many neighbours to return.
        wing: optional wing filter — restricts the KNN search to same wing.

    Returns:
        InfoScoreResult with novelty score, band, and neighbours.
    """
    if not text or not text.strip():
        raise ValueError("info-score requires non-empty text")

    from .embedding import embed_texts
    from .palace import get_collection

    cfg = CognitiveCastleConfig()
    palace = os.path.expanduser(palace_path) if palace_path else cfg.palace_path

    query_vec = embed_texts([text])[0]

    col = get_collection(palace, collection_name="castle_drawers", create=False)
    where_clause = f"wing = '{wing}'" if wing else None
    hits = col.vector_search(query_vec, n_results=top_k, where=where_clause)

    if not hits:
        return InfoScoreResult(novelty=1.0, band="high", neighbours=[])

    # LanceDB `vector_search` returns cosine distances (1 - cosine) — smaller = closer.
    # Convert back to similarity and take the max.
    neighbours = []
    for hit in hits:
        distance = float(hit.get("_distance", 1.0))
        cosine = 1.0 - distance
        neighbours.append(
            Neighbour(
                drawer_id=hit.get("id") or hit.get("drawer_id", "?"),
                text=hit.get("text", ""),
                cosine=cosine,
                wing=hit.get("wing"),
                room=hit.get("room"),
            )
        )
    max_cos = max(n.cosine for n in neighbours)
    novelty = 1.0 - max_cos
    return InfoScoreResult(
        novelty=novelty, band=_band_from_novelty(novelty), neighbours=neighbours
    )
