# Reproducibility Manifest

This document captures the configuration that produces the numbers in
`paper/results.yaml`. Reviewers reproducing on a different machine
should match all items below; numerical results match within ±1e-3.

## Environment

- Python: `>=3.11`
- OS: Linux (developed on Fedora 44 / kernel 6.19)
- Lockfile: `research/info_theory/uv.lock` (committed; recreate via `uv sync`)
- bge-m3 model revision: pinned in `seeds.yaml` under `bge_m3_revision`
- Castle source-tree commit: pinned in `seeds.yaml` under `castle_commit`
- Palace snapshot fingerprint: pinned in `seeds.yaml` under `palace_snapshot_fingerprint`
- LongMemEval release: pinned in `seeds.yaml` under `longmemeval_release`

## Seeds

All seeds live in `research/info_theory/seeds.yaml`. Any change → new
run → new `results.yaml`. The five active seeds:

- `numpy_seed` — generic NumPy RNG
- `subsample_seed` — C-stage stratified sampling
- `bootstrap_seed` — block-bootstrap resamples for decay-fit CIs
- `prompt_template_seed` — any randomized prompt-template variations
- `downstream_eval_seed` — bootstrap CIs on H3 R@5 deltas

## Hardware

- **CUDA GPU**: required for embedding 65k drawers in reasonable time.
  CPU-only fallback adds ~2-4 hours and is documented but not the
  target configuration.

## Claude CLI invocation

C-stage uses the `claude-cli` provider (PR #49). The exact invocation
is recorded with each call in `llm_surprise_subsample.parquet`:

- Model: `claude-haiku-4-5-20251001`
- Flags: `--no-session-persistence`, `--disable-slash-commands`,
  `--output-format json`
- Prompt template SHA: pinned in `seeds.yaml` under `prompt_template_sha`

## Two-machine verification protocol

Before first commit of `results.yaml`:

1. Developer runs full pipeline on Machine A (GPU dev box).
2. Output written to `paper/results.yaml`.
3. Developer runs Tier 4 reproducibility check on Machine B (fresh
   checkout, different machine if possible). On match (within
   tolerance), `results.yaml` is committed.
4. From that point forward, CI verifies on every commit.

## Tolerance bands

- Same-machine same-seed runs: ±1e-6 on fitted parameters
- Cross-machine runs: ±1e-3 on fitted parameters
- H3 R@5 deltas: ±0.5 percentage points absolute
