"""C-stage subsample allocation with floor + termination guard."""

from __future__ import annotations

import random


def allocate_subsample(
    strata_sizes: dict,
    n_total: int,
    floor: int,
    max_iter: int = 10,
    seed: int = 42,
) -> dict:
    """Stratified allocation with per-stratum floor.

    Algorithm:
      1. If floor*num_strata > n_total: reduce floor to n_total // num_strata.
      2. Proportional allocation across n_total.
      3. Iteratively raise sub-floor strata to floor by stealing from above-floor.
      4. Round-half-up tiebreaks deterministic from seed.
    """
    rng = random.Random(seed)
    num = len(strata_sizes)
    if floor * num > n_total:
        floor = max(1, n_total // num)

    total_size = sum(strata_sizes.values())
    alloc = {k: max(floor, round(n_total * v / total_size)) for k, v in strata_sizes.items()}

    # Normalize to n_total via random rounding tiebreaks.
    # Loop until diff resolves or no progress can be made: each pass reshuffles
    # keys and applies ±1 adjustments, skipping strata that would drop below floor.
    while True:
        diff = n_total - sum(alloc.values())
        if diff == 0:
            break
        keys = list(alloc.keys())
        rng.shuffle(keys)
        progress = False
        for k in keys:
            if diff == 0:
                break
            step = 1 if diff > 0 else -1
            new_v = alloc[k] + step
            if new_v >= floor:
                alloc[k] = new_v
                diff -= step
                progress = True
        if not progress:
            break

    return alloc
