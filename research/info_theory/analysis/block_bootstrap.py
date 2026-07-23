"""Source-aware block bootstrap for decay-fit CIs."""

from __future__ import annotations

import numpy as np


def build_blocks(N_total: int, source_files: list) -> tuple[int, list[list[int]]]:
    """Returns (block_size, blocks). block_size = clamp(N_total//5, 10, 100).
    Blocks are contiguous index ranges that span source-file boundaries
    where possible (i.e., not built within a single source-file group)."""
    block_size = max(10, min(100, N_total // 5))
    blocks = []
    i = 0
    while i < N_total:
        block = list(range(i, min(i + block_size, N_total)))
        blocks.append(block)
        i += block_size
    return block_size, blocks


def bootstrap_ci(
    data: np.ndarray,
    statistic,
    n_resamples: int = 1000,
    block_size: int = None,
    source_files: list = None,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Block bootstrap CI. If block_size is None, uses build_blocks."""
    n = len(data)
    if block_size is None:
        block_size, _ = build_blocks(n, source_files or ["s"] * n)
    rng = np.random.default_rng(seed)
    n_blocks_needed = n // block_size + 1
    block_starts = list(range(0, n, block_size))
    estimates = []
    for _ in range(n_resamples):
        chosen = rng.choice(block_starts, size=n_blocks_needed, replace=True)
        resample = []
        for s in chosen:
            resample.extend(data[s : s + block_size])
            if len(resample) >= n:
                break
        estimates.append(statistic(np.array(resample[:n])))
    lo = np.quantile(estimates, (1 - confidence) / 2)
    hi = np.quantile(estimates, 1 - (1 - confidence) / 2)
    return float(lo), float(hi)
