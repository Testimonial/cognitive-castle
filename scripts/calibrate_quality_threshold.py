#!/usr/bin/env python3
"""Calibrate quality_threshold_medium and _high defaults from a palace sample.

Usage:
    python scripts/calibrate_quality_threshold.py \
        --palace ~/.castle/palace \
        --sample-size 100 \
        --seed 42

Prints distribution stats + histogram of overall_weighted_average across
a random sample of drawers. Use p75 → quality_threshold_medium,
p90 → quality_threshold_high (or whichever percentiles match your boost
policy).

Not a test. One-shot investigation tool. Re-run after major ingest
changes.
"""

from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
from pathlib import Path

# Force CPU to avoid GPU contention with other Castle processes
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--palace",
        default=os.path.expanduser("~/.castle/palace"),
        help="Path to the palace directory (default: ~/.castle/palace)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of drawers to sample randomly (default: 100)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    args = parser.parse_args()

    palace_path = str(Path(args.palace).expanduser().resolve())
    if not Path(palace_path).exists():
        print(f"ERROR: palace not found at {palace_path}", file=sys.stderr)
        return 2

    from cognitive_castle.palace import get_collection
    from cognitive_castle.understanding import analyze_with_enhanced_metrics

    col = get_collection(palace_path=palace_path)
    all_ids = col.list_drawer_ids()
    print(f"palace has {len(all_ids)} drawers")

    if len(all_ids) == 0:
        print("ERROR: palace has no drawers", file=sys.stderr)
        return 2

    random.seed(args.seed)
    sample_ids = random.sample(all_ids, min(args.sample_size, len(all_ids)))
    rows = col.get_by_ids(sample_ids)
    print(f"sampled {len(rows)} drawers")
    print()

    t0 = time.time()
    scores: list[float] = []
    text_lens: list[int] = []
    errors: list[str] = []
    for row in rows:
        try:
            text = row["text"]
            text_lens.append(len(text))
            r = analyze_with_enhanced_metrics(text)
            score = r["enhanced_metrics"]["overall_weighted_average"]
            scores.append(score)
        except Exception as e:
            errors.append(type(e).__name__)
            continue

    dt = time.time() - t0
    print(
        f"computed {len(scores)} scores in {dt:.1f}s "
        f"({dt * 1000 / max(len(scores), 1):.0f}ms/drawer avg)"
    )
    if errors:
        print(f"errors: {len(errors)} — {set(errors)}")
    print()

    if text_lens:
        print("TEXT LENGTH distribution:")
        print(
            f"  min={min(text_lens)}  "
            f"median={statistics.median(text_lens):.0f}  "
            f"max={max(text_lens)}  mean={statistics.mean(text_lens):.0f}"
        )
        print()

    if not scores:
        print("ERROR: no scores computed", file=sys.stderr)
        return 2

    print("SCORE distribution (overall_weighted_average):")
    print(f"  n={len(scores)}")
    print(f"  min={min(scores):.3f}  max={max(scores):.3f}")
    print(f"  mean={statistics.mean(scores):.3f}  stdev={statistics.stdev(scores):.3f}")
    if len(scores) >= 10:
        q = statistics.quantiles(scores, n=10)
        print(f"  p10={q[0]:.3f}  p25={q[1]:.3f}  p50={q[4]:.3f}  p75={q[6]:.3f}  p90={q[8]:.3f}")
    print()

    # Histogram
    bins = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    counts = [0] * (len(bins) - 1)
    for s in scores:
        for i in range(len(bins) - 1):
            if bins[i] <= s < bins[i + 1] or (i == len(bins) - 2 and s == 1.0):
                counts[i] += 1
                break
    print("HISTOGRAM:")
    for i in range(len(bins) - 1):
        bar = "#" * counts[i]
        print(f"  [{bins[i]:.1f}-{bins[i + 1]:.1f})  {counts[i]:3d}  {bar}")

    print()
    print("RECOMMENDED THRESHOLDS:")
    if len(scores) >= 10:
        print(f"  quality_threshold_medium = {q[6]:.2f}  (p75)")
        print(f"  quality_threshold_high   = {q[8]:.2f}  (p90)")
    else:
        print("  (need at least 10 scores for percentile recommendations)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
