"""quality_rerank.py — Stage 6 of Castle's retrieval pipeline.

ON by default. Opt-out via --mode fast (or mode:fast MCP).
Re-ranks Stage 3+ candidates using the 31 deterministic text-quality
metrics from the vendored `understanding` package.

Two-tier threshold-and-boost rule with defaults calibrated to the user's
palace on 2026-05-14:
  - score >= cfg.quality_threshold_high (0.60)   → tier="high",   ×1.25
  - score >= cfg.quality_threshold_medium (0.53) → tier="medium", ×1.15
  - otherwise                                    → tier=None,     ×1.0

Per-hit audit-trail fields added to each row:
  - quality_score: float | None       (None when Stage 6 didn't run or
                                       per-hit failure occurred)
  - quality_tier:  "high" | "medium" | None
  - quality_boost: float (default 1.0)
  - score_pre_quality: float (hit's score before Stage 6 ran)

The audit-line printer in searcher._print_search_results only emits a
QUALITY line when quality_tier is not None.

Graceful degradation: if the vendored package fails to import or a
per-hit call raises, the affected hit(s) get default fields and a
warning is logged once per failure class.

See spec: docs/superpowers/specs/2026-05-14-quality-rerank-design.md
"""

from __future__ import annotations

import sys
from typing import Optional


ADAPTER_NAME = "quality-rerank"

# Module-level state. Cleared by _reset_for_test() in test runs.
_WARNED: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    """Print a stderr warning ONCE per process for the given key."""
    if key in _WARNED:
        return
    _WARNED.add(key)
    print(f"[quality_rerank] {message}", file=sys.stderr)


def _reset_for_test() -> None:
    """Test-only: clear module-level state to enable test isolation."""
    _WARNED.clear()


def _classify_tier(score: float, cfg) -> tuple[Optional[str], float]:
    """Apply the two-tier threshold rule. Returns (tier, multiplier).

    >= cfg.quality_threshold_high → ("high",   cfg.quality_boost_high)
    >= cfg.quality_threshold_medium → ("medium", cfg.quality_boost_medium)
    otherwise                       → (None,     1.0)
    """
    if score >= cfg.quality_threshold_high:
        return "high", cfg.quality_boost_high
    if score >= cfg.quality_threshold_medium:
        return "medium", cfg.quality_boost_medium
    return None, 1.0


def apply_quality_rerank(
    reranked: list[tuple[float, dict]],
    cfg,
) -> list[tuple[float, dict]]:
    """Stage 6: deterministic text-quality rerank.

    For each candidate, score the drawer text via
    `understanding.analyze_with_enhanced_metrics`, apply two-tier
    threshold-and-boost. Mutate hit dicts with audit-trail fields.

    Returns a NEW list of (score, row) tuples sorted by boosted score
    descending. Each row dict is mutated in place with:
      - quality_score (float, or None on per-hit failure)
      - quality_tier ("high" | "medium" | None)
      - quality_boost (float, 1.0 if no boost)
      - score_pre_quality (float, hit's score going into Stage 6)

    Graceful degradation:
      - If `cognitive_castle.understanding` import fails, all hits get
        default fields (None, None, 1.0, original score). Warns once.
      - If per-hit metric call raises, that hit gets default fields.
        Warns once per exception class.

    Never raises. Same fault-tolerance pattern as soar_bridge.
    """
    if not reranked:
        return reranked

    # Lazy import — only pays the spaCy load cost when Stage 6 actually
    # runs. Failure here means we can't run Stage 6 at all; all hits
    # get default fields.
    try:
        from cognitive_castle.understanding import analyze_with_enhanced_metrics
    except ImportError as e:
        _warn_once(
            "import-failed",
            f"understanding import failed ({type(e).__name__}: {e}); Stage 6 skipped for all hits",
        )
        return [
            (
                score,
                _set_defaults(row, original_score=score),
            )
            for score, row in reranked
        ]

    out: list[tuple[float, dict]] = []
    for original_score, row in reranked:
        text = row.get("text") or row.get("document") or ""
        try:
            result = analyze_with_enhanced_metrics(text)
            score = result["enhanced_metrics"]["overall_weighted_average"]
            if not isinstance(score, (int, float)) or score != score:  # NaN check
                raise ValueError(f"non-numeric overall_weighted_average: {score!r}")
        except KeyError as e:
            _warn_once(
                "missing-key",
                f"analyze result missing expected key ({e}); per-hit default",
            )
            out.append((original_score, _set_defaults(row, original_score=original_score)))
            continue
        except Exception as e:
            _warn_once(
                f"analyze-failed-{type(e).__name__}",
                f"analyze_with_enhanced_metrics raised ({type(e).__name__}: {e}); per-hit default",
            )
            out.append((original_score, _set_defaults(row, original_score=original_score)))
            continue

        tier, multiplier = _classify_tier(float(score), cfg)
        new_score = original_score * multiplier

        row["quality_score"] = float(score)
        row["quality_tier"] = tier
        row["quality_boost"] = multiplier
        row["score_pre_quality"] = original_score
        out.append((new_score, row))

    # Sort by boosted score descending
    out.sort(key=lambda t: -t[0])
    return out


def _set_defaults(row: dict, *, original_score: float) -> dict:
    """Mutate the row dict with default quality_* fields (used on failure
    paths). Returns the same dict for fluent chaining."""
    row["quality_score"] = None
    row["quality_tier"] = None
    row["quality_boost"] = 1.0
    row["score_pre_quality"] = original_score
    return row
