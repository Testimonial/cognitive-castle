import numpy as np
from analysis.block_bootstrap import build_blocks, bootstrap_ci


def test_build_blocks_size_clamped():
    """clamp(N//5, 10, 100)"""
    assert build_blocks(N_total=200, source_files=["a"] * 200)[0] == 40
    assert build_blocks(N_total=50, source_files=["a"] * 50)[0] == 10
    assert build_blocks(N_total=10000, source_files=["a"] * 10000)[0] == 100


def test_source_aware_blocks_span_source_boundaries():
    """Blocks should not all be from the same source_file."""
    source_files = (["fileA"] * 50) + (["fileB"] * 50) + (["fileC"] * 50)
    block_size, blocks = build_blocks(N_total=150, source_files=source_files)
    # At least one block crosses sources
    spans = [len(set(source_files[idx] for idx in block)) for block in blocks]
    assert max(spans) > 1, f"all blocks single-source: {spans}"


def test_bootstrap_ci_coverage_on_ar1():
    """Synthetic AR(1) with known mean; bootstrap CIs cover at ~95% rate."""
    rng = np.random.default_rng(42)
    true_mean = 5.0
    n_datasets = 50  # keep test fast
    covered = 0
    for _ in range(n_datasets):
        n = 200
        x = np.zeros(n)
        x[0] = true_mean + rng.normal()
        for i in range(1, n):
            x[i] = 0.7 * x[i - 1] + 0.3 * true_mean + rng.normal(0, 0.3)
        ci_lo, ci_hi = bootstrap_ci(
            x,
            np.mean,
            n_resamples=200,
            block_size=20,
            source_files=["s"] * n,
            seed=42,
        )
        if ci_lo <= true_mean <= ci_hi:
            covered += 1
    rate = covered / n_datasets
    # Approximate 95% coverage; binomial sd ≈ 0.03 for n=50, so 85-100% acceptable
    assert 0.80 <= rate <= 1.0, f"coverage {rate} out of expected range"
