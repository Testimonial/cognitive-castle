# Information Content in Verbatim AI Memory — Design Spec

**Date:** 2026-05-16
**Status:** Draft v2 (pivoted), awaiting user review
**Working title (paper)**: *"Measuring Information Content in Verbatim AI Memory: Methodology, Source-Type Heterogeneity, and a Downstream Utility Test"*
**Scope:** Phase 1 — research artifact only (estimator + experiment + downstream validation + paper). Castle production integration deferred to a separate Phase 2 spec.

## Background

Castle's design promise is *verbatim memory*: every word the user has shared is stored exactly as it appeared. The architectural inheritance from MemPalace makes this a hard constraint, not a configurable knob.

A consequence of verbatim-only storage is **redundancy**. A "what is AAAK" search currently returns 8 near-identical drawers, each from a different past session. Dense embeddings see them as nearly the same point; the KG sees the same entities; SOAR re-ranks the same recency cluster. Castle has no formal way to say "the 1st drawer added 4.2 bits of new information; the 8th added 0.03 bits." The verbatim-only principle is a *storage* claim. There is no corresponding *information* claim.

This spec defines an experiment that:

1. Introduces a **methodology** for measuring conditional information content `I(d_t | D_<t)` of each drawer given its predecessors, using three composable estimators at increasing rigor.
2. **Characterizes source-type heterogeneity** in information-decay behavior across drawer sources (`miner` auto-captured transcripts, `session-hook` rolling checkpoints, `mcp` hand-curated filings) within a single user's palace, and across question types within the public LongMemEval corpus.
3. **Validates downstream utility** by testing whether the estimator improves a real retrieval task (LongMemEval R@5 under uniform vs. info-weighted corpus conditions).
4. Produces a paper-grade analysis published on arXiv, with reproducibility on the public LongMemEval corpus.

### Paper framing (post-pivot)

This is a **methodology paper with exploratory empirical evidence**, not an empirical-findings paper. The claim shape is *"we introduce a methodology and apply it to two corpora, finding heterogeneity by source"* — not *"verbatim memory saturates."* The latter would over-generalize from n=1 user + LongMemEval. The former is defensible and the more interesting result.

Phase 1 ends with a paper draft on arXiv and reproducibility code in `research/info_theory/`. Phase 2 (separate spec) uses the validated estimator to drive info-aware mining and search in Castle proper.

### Why Castle specifically can do this

Three uncommon ingredients sit in the same project:

- **Verbatim storage**: the ground truth `D_<t` is uncorrupted. Most memory systems summarize before they can measure.
- **Source-type metadata** (`added_by` ∈ {`miner`, `session-hook`, `mcp`}): enables the heterogeneity analysis that's the paper's primary finding.
- **A real 65,575-drawer corpus**: most papers in this space test on synthetic data because they don't have one user's months of verbatim conversation.

### Phase 2 forward pointer (not in this spec)

Once Phase 1 validates the estimator, Phase 2 wires it into Castle: a `castle entropy` subcommand exposing per-stratum saturation curves; an info-aware mining mode (`castle mine --skip-low-info`) that drops drawers below an info threshold; saturation-aware ranking (`info_score × relevance`) that collapses near-duplicate retrievals. Phase 1's downstream-utility experiment (Hypothesis H3 below) provides the evidence that motivates Phase 2.

## Hypothesis structure

The core question is whether the marginal information rate `I(d_t | D_<t)` *declines as a stratum grows*, and whether the decay shape varies by source type. The paper tests three hypotheses.

### H1 — Source-type heterogeneity (primary)

> **Within each corpus, the marginal-information decay rate differs significantly across drawer source types** (`miner`, `session-hook`, `mcp` for palace; `question_type` for LongMemEval).

Tested via comparison of fitted decay parameters (α for power-law, τ for exponential) across source-type groups using bootstrap-CI overlap and Kruskal-Wallis test. If true, this is the paper's headline: information accumulation is not a property of memory in general but a property of *how memory is captured*.

### H2 — Saturation form (per stratum)

> **For each (corpus × stratum × source-type) cell with sufficient data, one of {power-law decay, exponential decay-to-floor} fits the smoothed marginal-information sequence with statistically significant improvement over a shuffled-order null at FDR q=0.05.**

Tested as a regression problem over `(N, info_score)` time series. AIC + block bootstrap. This is the per-cell-level claim; H1 aggregates across cells.

### H3 — Downstream utility (validates the estimator's practical value)

> **On LongMemEval, retrieval R@5 under an info-weighted corpus (drop bottom-X% by `recon_residual`) is non-inferior or superior to retrieval under the uniform corpus, for X ∈ {10%, 25%, 50%}.**

Tested via paired comparison of R@5 across thresholds against uniform baseline, with bootstrap-CI for each delta. If true, Phase 2's smart-mining motivation is empirically validated. If false, it's a 1-sentence negative result in Methods.

### Variables and operational definitions

- **Drawer ordering**: by `(filed_at, chunk_index)` ascending. `filed_at` lives in `metadata_json` (verified against Castle schema). `chunk_index` is the column-level tiebreaker for multi-chunk drawers filed in the same operation.

  Note: chunks-of-the-same-source-file have identical `filed_at` and consecutive `chunk_index` values. They are **highly correlated** in embedding space (same conversation context). The block bootstrap design accounts for this (next section).

- **`info_score(d_t, N)`**: computed from three estimators (see [Estimator architecture](#estimator-architecture)). The **primary decay fit is performed on `recon_residual`** (Estimator B); `nn_novelty` (A) and `llm_surprise` (C) are reported as validation.
- **Saturation point `N*`**: smallest `N` such that the LOWESS-smoothed `info_score` drops below `1× IQR-of-shuffled-null` (adaptive, not arbitrary 5%) **and stays there** for `≥ max(10, N_stratum/10)` consecutive drawers (adaptive persistence floor, not fixed 50). Sensitivity analysis at fixed thresholds {0.5×IQR, 2×IQR} in appendix.

### Two candidate decay models — and only two

- **Power-law decay**: `info(N) = a · N^(-α) + ε`, `ε ~ N(0, σ_N²)` with heteroscedastic noise (`σ_N² ∝ N^(-α)`). MLE under this noise model is weighted least squares.
- **Exponential decay to floor**: `info(N) = c + (a − c) · exp(−N/τ) + ε`, `ε ~ N(0, σ²)` homoscedastic. MLE is ordinary least squares.

Log-normal and stretched-exponential dropped — YAGNI. Cited as future work.

### Procedure (per stratum)

1. **Stratify**: split corpus by stratum identifier (see [Corpora](#corpora)).

   - Palace strata: `wing × room × added_by`. Source types: `mcp`, `session-hook`, `miner`.
   - LongMemEval strata: `question_id`, additionally tagged with `question_type`.

   Report per-cell, then aggregate by source type / question type for H1.

2. **Compute** the `(N, info_score)` sequence for that stratum, with `N` indexing drawer position in `(filed_at, chunk_index)` order.

3. **Fit both decay models** via weighted least squares (power-law) / OLS (exponential) with **block bootstrap confidence intervals**:
   - Block size: `min(100, max(10, N_stratum / 5))`. Adaptive — block_size ≤ N/5 floor prevents the 2-block degeneracy from earlier draft.
   - **Source-aware blocking** (important): blocks span across `source_file` boundaries where possible. Within-source-file chunks are correlated; blocks that cluster within a single source file underestimate variance.
   - B = 1000 bootstrap resamples. Sensitivity at block sizes ±50% in appendix.

4. **Compare models** via AIC. Report ΔAIC and Akaike weights.

5. **Null baseline**: shuffle drawer order 1000 times **at the source-file level** (preserves within-file correlation, randomizes between-file order). Refit both models. Real-order fits must lie outside the 95th percentile of the null distribution to count as significant.

6. **Multiple-comparisons correction**: realistic test count is **~110-210 hypothesis tests** (≈3-5 fittable palace cells + ≈50-100 fittable LME cells, each tested against 2 models, real vs. null). Apply Benjamini-Hochberg FDR control at **q = 0.05** (FDR rate; not a per-test p-value cutoff — the q vs. p distinction matters and is used consistently throughout).

### Heterogeneity aggregation (for H1)

Per-stratum results aggregate to the H1 claim via:

- **Within-source-type fitted-α distribution**: report median + IQR of fitted α per source type.
- **Kruskal-Wallis test** across source types: tests whether α distributions differ significantly between `miner`, `session-hook`, `mcp` strata.
- **Headline figure for H1**: violin plot of fitted α across all strata, grouped by source type. Visual immediately reveals whether `miner` saturates faster than `mcp` (the likely empirical finding).

### What the paper concludes (plain English)

For each fittable stratum, we report:

- Which decay model wins (with AIC weight)
- Fitted parameter (α for power-law, τ for exponential) with block-bootstrap CI
- Whether the fit beats the shuffled-order null at FDR-corrected significance
- The `N*` saturation point under the operational definition

For the headline H1 claim:

- Per-source-type α distribution
- Kruskal-Wallis statistic across source types
- Qualitative description of the heterogeneity pattern (e.g., "miner saturates fastest, mcp shows no detectable saturation")

For the H3 downstream claim:

- R@5 deltas per threshold (10%, 25%, 50%)
- Per-question-type R@5 deltas (does info-weighting help on some question types more than others?)

Headline figure: a small-multiples grid showing `(N, recon_residual)` curves grouped by source type, with fitted models overlaid and null distributions shaded.

## Estimator architecture

Three estimators answering the same question — *how surprising is `d_t` given `D_<t`?* — at three rigor/cost levels. None is literally `−log P(d_t | D_<t)`; the paper says so explicitly.

### Shared inputs

- Target drawer `d_t` with `text`, `filed_at`, `chunk_index`, `source_file`.
- **Prior set** `D_<t` is corpus-specific:
  - **Palace**: same `wing` AND `(filed_at, chunk_index) < (d_t.filed_at, d_t.chunk_index)` (avoids cross-domain confusion; respects within-file chunk ordering).
  - **LongMemEval**: same `session_id` AND ordering by chunk position within session.

The LME prior-set unit (`session_id`) is **finer-grained** than the LME stratum unit (`question_id`). This is intentional: prior-set tracks the *local conversational context* a memory system would actually see; stratum tracks the *analytical grouping* for cross-question comparison. Documented in paper Methods as a deliberate choice, not an artifact.

- Embeddings: bge-m3, cached as Parquet (see [Caching](#caching-layout-parquet-in-castleresearch)) — re-runs do not re-embed.

### Drawer text normalization (applies to all estimators)

Before embedding (A, B) or passing to the LLM (C):

- Strip fenced code blocks (regex on triple-backtick).
- Truncate to 2000 tokens (bge-m3's effective limit).
- Sensitivity analysis with **raw text** reported in appendix.

Acknowledged bias: heavily-code drawers contribute their surrounding prose, not their code. Footnoted as a limitation.

### A — `nn_novelty` (cheap baseline)

`nn_novelty(d_t) = 1 − max_{d ∈ D_<t} cosine(embed(d_t), embed(d))`

Single LanceDB top-1 vector search per drawer. ~10ms. **Measures atypicality, not info content** — saturates at 0 once any near-duplicate exists. Full corpus cost: ~11 min, $0.

### B — `recon_residual` (principled primary)

**True Roweis–Saul LLE weights with Tikhonov regularization**: unconstrained weights summing to 1, closed-form solution via regularized linear system. The regularization is mandatory in practice — without it, collinear neighborhoods produce singular Gram matrices.

```
K_effective = min(K_target, |D_<t|)               # K_target = 20
if K_effective < K_floor (= 5):
    recon_residual = null  # excluded from B analysis; A still computed
else:
    fetch K_effective nearest priors (cosine)
    G = (X - x_t)(X - x_t)ᵀ                       # Gram matrix of centered neighbors
    G_reg = G + λ · trace(G) · I                  # Tikhonov regularization
                                                  # λ = 1e-3 (standard LLE default)
    w = G_reg⁻¹ · 1 / (1ᵀ · G_reg⁻¹ · 1)          # closed-form LLE weights
    recon_residual = ||embed(d_t) - Σ w_k embed(d_k)||_2
```

- **Closed-form** (no QP, no iterative solver) — but includes the K=20 LanceDB query (~10ms) + matrix solve (~1ms) = ~12-15ms per drawer.
- `K_floor = 5`: B is null for the first 5 drawers in each stratum; flagged `is_first=true`.
- **Sensitivity**: report K ∈ {10, 20, 50, 100} in appendix; also report λ ∈ {1e-4, 1e-3, 1e-2}.
- **Failure mode**: bounded by bge-m3 quality. C is the validation check.
- Cost: ~65k × 13ms ≈ **14 min**, $0.

### C — `llm_surprise` (subsample validation, gold standard)

For a stratified subsample of `n=1000` drawers, ask Haiku 4.5 (via the **`claude-cli` provider**) to rate predictability of `d_t` given recency-selected priors.

**Provider choice**: C uses the `claude-cli` provider (PR #49), which shells out to `claude -p --output-format json`. Reuses the user's existing Claude Code subscription auth; no separate `ANTHROPIC_API_KEY` to provision. Per-call cost is read from `total_cost_usd` in the response envelope.

**Known caveat (subscription rate limits)**: 1000 calls × 25-45s sustained over 7-12 hours could brush against Claude Code's rate limits. Mitigation: process drawers serially (no concurrency); spread across 2-3 days if needed; n=50 dry-run to validate throughput before n=1000. The resumable design (next section) means rate-limit pauses are non-fatal — restart resumes from the last completed drawer.

- **Prior selection**: **top-20 by `(filed_at, chunk_index)` recency** from `D_<t`. Deterministic.
- **Prompt template**: *"Given these 20 prior memory entries [list], rate on a 1–10 scale how predictable the following entry is. 10 = entirely derivable from priors, 1 = entirely novel. Return JSON: `{score: int, reasoning: short str}`."*
- **`llm_surprise = 10 − score`** (higher = more novel, sign-aligned with A and B).
- **Reasoning field**: stored as `llm_surprise_reasoning_spotcheck` for human spot-check only, **not analyzed quantitatively**.
- **Subsample-allocation algorithm** (with explicit termination):
  1. Identify all strata with `≥ K_floor` drawers.
  2. Compute proportional allocation across `n=1000`.
  3. For any stratum below floor (`floor=20`), raise to floor by stealing proportionally from above-floor strata.
  4. Iterate at most 10 times. **Termination guard**: if total floor commitment > `n_total`, reduce floor proportionally (`floor = floor(n_total / num_strata)`) and re-run. Algorithm always terminates.

### Cost & runtime estimate

- **Per-call input tokens**: 20 priors × ~500 avg + instructions ~200 + target ~500 = **~10.7k tokens** (tighter than earlier "15-25k" estimate).
- **Per-call cost (Haiku 4.5)**: ~$0.04-$0.10.
- **Per-call wall-clock**: ~25-45s at that prompt size.
- **Total C cost**: **$40-$100** (revised down from earlier $80-150).
- **Total C wall-clock**: **7-12 hours**.

| Estimator | Drawers | Per-drawer | Wall-clock | $ |
|---|---|---|---|---|
| A `nn_novelty` | ~65k + LME | ~10ms | ~11 min | $0 |
| B `recon_residual` | ~65k + LME | ~13ms (LLE + KNN) | ~14 min | $0 |
| C `llm_surprise` | 1000 subsample | 25-45s + $0.04-0.10 | 7-12 hr | $40-100 |

### Correlation analysis (validation of A and B against C)

- **Primary**: **Spearman rank correlation** between `(nn_novelty, llm_surprise)` and `(recon_residual, llm_surprise)` on the 1000-drawer subsample.
- **Supplementary**: Pearson, acknowledging C's discrete 1-10 scale vs. continuous A and B.
- **Per-stratum**: each stratum reports its own coefficient with bootstrap CI.

### Output schema (per drawer)

```json
{
  "drawer_id": "drawer_wing_castle_decisions_1735ceedd5...",
  "corpus": "palace",
  "stratum_id": "wing_castle::decisions::mcp",
  "wing": "wing_castle",
  "room": "decisions",
  "added_by": "mcp",
  "source_file": "/path/to/source.jsonl",
  "chunk_index": 0,
  "session_id": null,
  "question_id": null,
  "question_type": null,
  "filed_at": "2026-05-15T22:17:29Z",
  "N_in_stratum": 7,
  "is_first": false,
  "nn_novelty": 0.81,
  "recon_residual": 0.43,
  "recon_residual_K": 20,
  "recon_residual_lambda": 0.001,
  "llm_surprise": 8.0,
  "llm_surprise_reasoning_spotcheck": "...",
  "llm_surprise_prompt_tokens": 10732,
  "llm_surprise_completion_tokens": 87,
  "llm_surprise_cost_usd": 0.0521
}
```

For LME rows: `wing=null`, `room=null`, `added_by=null`, `session_id`/`question_id`/`question_type` populated. `stratum_id = f"longmemeval::question_{question_id}"`.

### Failure handling

- **Prior set empty / below `K_floor` for B**: `recon_residual=null`, drawer marked `is_first=true`, analysis filters apply.
- **C call fails** (timeout, malformed JSON, rate-limited): record `llm_surprise=null`, audit fields populated. Null rate reported in paper Methods. Hard cap: 5% null tolerated; over that, halt and investigate.
- **Embedder unavailable**: A and B abort fast with clear error. C runs standalone.
- **LLE singular** (despite λ regularization): increment λ × 10, retry once; if still singular, `recon_residual=null` and log warning.

## Corpora

### Corpus 1 — Palace (private, exploratory data)

- **Source**: snapshot of `~/.castle/palace/` at experiment start (see [Palace snapshot](#palace-snapshot)).
- **Size**: 65,575 drawers as of 2026-05-16.
- **Composition**:

| Wing | Drawers | Dominant `added_by` |
|---|---|---|
| `_home_lbihari_cognitive_castle` | 48,848 | `miner` |
| `projects` | 14,000 | `miner` |
| `sessions` | 2,651 | `miner` |
| `wing_castle` | 47 | `mcp` + `session-hook` |
| `wing_lbihari` | 29 | `session-hook` |

Headline asymmetry: **99.99% of drawers are `miner`/`session-hook`; only ~10 are `mcp`.** H1 specifically tests whether these source types behave differently.

- **Schema** (actual, verified):
  - LanceDB columns: `id`, `vector`, `text`, `metadata_json`, `wing`, `room`, `source_file`, `chunk_index`, `decay_score`.
  - `filed_at` and `added_by` live inside `metadata_json` (JSON-parsed at load time).
  - `chunk_index` lives at the column level — useful for ordering within multi-chunk source files.

- **Privacy**: stays local. The paper reports aggregate statistics (fitted decay parameters, correlations, R@5 deltas) — not drawer contents. Up to 20 `reasoning_spotcheck` excerpts (illustrative drawers) appear in the paper appendix; user-reviewed before publication.

### Palace snapshot

The palace is **actively growing** via the Stop hook. Experiment runs over 9-11 weeks. Without snapshotting, drawer counts and orderings shift underneath us → numbers can't be reproduced.

**Snapshot procedure** (in `pipeline/snapshot_palace.py`):

1. At experiment start: `cp -r ~/.castle/palace/ ~/.castle/research/palace_snapshot_2026-05-16/`.
2. Record snapshot fingerprint: **stable hash of `(drawer_id list + filed_at values + chunk_index values)`** sorted by `drawer_id` — NOT raw file hashes, which include non-deterministic LanceDB index timestamps. Written to `research/info_theory/seeds.yaml`.
3. All downstream stages read from `palace_snapshot_2026-05-16/`, never from live palace.

Reproducibility manifest includes the snapshot fingerprint alongside the Castle commit hash.

### Corpus 2 — LongMemEval (public, reproducibility)

- **Source**: already in `benchmarks/longmemeval_bench.py`. **May require minor refactoring** to expose a `load_questions()` function as an importable API rather than as a script-only entry point. Risk explicitly listed.

- **Size estimate**: 500 questions × ~50 sessions/question ≈ 25k sessions. After chunking through Castle's miner: **estimated ~75k-125k drawers**, range uncertainty acknowledged. **Pilot**: 5% pilot run on ~25 questions to tighten the estimate before committing to full pipeline (~30 min, ~$0). Pilot result updates the spec's downstream cost/runtime numbers.

- **Schema** (after chunking): `text`, `filed_at` (synthesized to match palace schema — set to LME's session timestamp), `session_id`, `question_id`, `question_type` ∈ {single-session-user, single-session-assistant, single-session-preference, temporal-reasoning, knowledge-update, multi-session}, `chunk_index`. Castle-specific fields (`wing`, `room`, `added_by`) stay `null`.

- **Why include LME**: reviewers can reproduce. The H1 heterogeneity finding (now via `question_type` rather than `added_by`) and the H3 downstream finding must reproduce on the public corpus, or the paper is unfalsifiable.

### Schema verification step

Before running estimators, validate corpus completeness in `pipeline/load_palace.py`:

- Parse `metadata_json` column for every palace drawer; assert `filed_at` is populated.
- For drawers with missing `filed_at`: log + exclude from analysis; record exclusion count.
- Verify `chunk_index` is non-null and integer for every drawer.
- Report exclusion count in paper Methods.

### Cross-corpus stratification reconciliation

| | Palace stratum | LongMemEval stratum |
|---|---|---|
| Identifier | `f"{wing}::{room}::{added_by}"` | `f"longmemeval::question_{question_id}"` |
| Heterogeneity grouping (H1) | `added_by` (3 levels: miner/session-hook/mcp) | `question_type` (6 levels) |
| Ordering within stratum | `(filed_at, chunk_index)` ascending | `(session_index, chunk_index)` ascending |
| Min drawers for fit | ≥200 (statistical-power floor) | ≥200 |

**The stratification asymmetry is named explicitly in the paper Methods**: "Palace cells use a fine-grained `wing × room × added_by` stratification; LongMemEval cells use `question_id` because LME lacks Castle's source-type field. The H1 source-type analysis groups palace cells by `added_by`; for LME we report parallel analysis by `question_type`. The two groupings are not directly comparable but each is a within-corpus heterogeneity finding."

### Loading LME → drawer format

Reuse `benchmarks/longmemeval_bench.py`'s session-loading via import (refactoring it to expose a loader API as needed). Adapter:

1. Loads LME questions + session histories.
2. For each session, runs Castle's miner (`cognitive_castle.miner`) with the **same chunking parameters used for palace ingestion** — guarantees comparable drawer sizes.
3. Tags each chunked drawer with `question_id`, `session_id`, `question_type`, position metadata; leaves Castle-only fields `null`.
4. Writes to `~/.castle/research/longmemeval_drawers.parquet`.

### Statistical-power floor

The `≥200 drawers/stratum` floor comes from power analysis: for a power-law decay fit with `α ≈ 0.5` (a priori) and bootstrap CI tightness target of ±0.1 on α, simulation suggests ~150 drawers. Round up to 200 for safety. Full simulation in paper appendix.

### What rooms/strata will and won't fit

| Stratum | Drawers | Fittable? |
|---|---|---|
| `palace::_home_lbihari_cognitive_castle::general::miner` | ~48k | **Yes** |
| `palace::projects::general::miner` | ~14k | **Yes** |
| `palace::sessions::technical::miner` | ~2.4k | **Yes** |
| `palace::sessions::architecture::miner` | 164 | **No — below floor**; descriptive only |
| `palace::wing_castle::decisions::mcp` | 8 | **No — far below floor**; reported as case study with all drawers shown |
| `palace::wing_castle::diary::session-hook` | ~42 | **No — below floor**; descriptive only |
| `palace::wing_lbihari::diary::session-hook` | ~29 | **No — below floor**; descriptive only |
| `longmemeval::question_X` (typical) | ~150-300 | **Marginal** — those ≥200 fit, others descriptive |

The paper frames this honestly: "fittable cells are dominated by auto-mining sources; the deliberate `mcp` source is too sparse for power-law fits, **itself a finding** about how hand-curation works in practice (only ~10 deliberate filings emerged across months of usage, despite the MCP protocol injection nudging the agent to file)."

## Data flow and code organization

### Where the code lives

New top-level dir `research/info_theory/` — sibling of `benchmarks/`, **not inside `cognitive_castle/`** (paper code, not Castle library code).

```
research/info_theory/
├── README.md
├── pyproject.toml          # paper-specific deps (statsmodels, powerlaw, matplotlib, scipy)
├── REPRODUCIBILITY.md
├── seeds.yaml              # all RNG seeds + snapshot fingerprint
├── paper/
│   ├── main.tex
│   ├── appendix.tex
│   ├── results.yaml        # every paper number lives here, CI-verified
│   └── figures/            # generated by analysis/figures.py
├── pipeline/
│   ├── snapshot_palace.py
│   ├── load_palace.py
│   ├── load_longmemeval.py # imports benchmarks/longmemeval_bench.py (refactor as needed)
│   ├── normalize.py
│   ├── embed.py            # imports cognitive_castle.embedding
│   ├── neighbors.py
│   ├── nn_novelty.py
│   ├── recon_residual.py   # LLE closed-form + Tikhonov
│   ├── llm_surprise.py     # claude-cli, resumable, partial-Parquet writes
│   ├── stratify.py
│   └── downstream_eval.py  # NEW: H3 LongMemEval R@5 under info-weighted corpora
├── analysis/
│   ├── fit_decay.py        # power-law + exponential MLE
│   ├── block_bootstrap.py  # source-aware blocks
│   ├── correlations.py
│   ├── heterogeneity.py    # H1: Kruskal-Wallis across source types
│   └── figures.py          # `--tables` emits LaTeX from results.yaml
├── cli.py
├── tests/test_*.py
└── outputs/                # gitignored; mirrors ~/.castle/research/ Parquet
```

### Why a separate top-level dir

1. **Different dependency footprint** — statsmodels, `powerlaw`, matplotlib, scipy. Castle stays minimal for pip users.
2. **Standalone reproducibility artifact** — clone-and-run without pip-installing all of Castle.
3. **Future-portable** — paper code may move to its own repo. Clean seam now avoids painful split later.

Same pattern as `understanding/` (originally in echelon, vendored into Castle).

### Entry point

```bash
# from research/info_theory/
python -m cli snapshot                              # take palace snapshot
python -m cli pilot                                 # 5% LME pilot to tighten size estimate
python -m cli run --all                             # full pipeline, cache-aware
python -m cli run --stage embed                     # one stage
python -m cli run --stage llm-surprise              # resumable
python -m cli run --stage downstream-eval           # NEW: H3 R@5 experiment
python -m cli status                                # show cache state, stale stages
python -m cli figures                               # regenerate plots
python -m cli figures --tables                      # emit appendix LaTeX tables from results.yaml
python -m cli cost-estimate --stage llm-surprise    # dry-run before spending $
```

**Cost-estimate mechanism**: samples 10 random drawers from the stratified subsample plan, runs the prompt-construction step end-to-end, measures input-token count via `tiktoken` (or `claude tokens` if available), multiplies `(n_subsample / 10) × mean_input_tokens × current_Haiku_pricing`. Prints upper/lower bounds based on observed variance.

Each stage reads cached Parquet inputs, writes cached Parquet outputs, skips if outputs newer than inputs (Makefile-style). `--force` overrides.

### Pipeline DAG

```
[palace LanceDB]                          [LongMemEval public]
       │                                          │
       ▼                                          ▼
  snapshot_palace.py                     load_longmemeval.py
       │                                          │
       ▼                                          │
  load_palace.py (from snapshot)                  │
       │                                          │
       └────────────────── merge ─────────────────┘
                              │
                              ▼
                        normalize.py
                              │
                              ▼
                          embed.py  ←── bge-m3 (cached)
                              │
                              ▼
                       neighbors.py (one Parquet per K)
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   nn_novelty           recon_residual           stratify
                                                     │
                                                     ▼
                                                llm_surprise (1000 drawers, resumable)
                              │                      │
                              └───── merge ──────────┘
                                      │
                  ┌───────────────────┼───────────────────┐
                  ▼                   ▼                   ▼
            fit_decay +        downstream_eval       correlations
            block_bootstrap    (LME R@5 under         (A↔C, B↔C)
                  │            info-weighted corpus)        │
                  ▼                   │                     │
            heterogeneity             │                     │
            (H1 Kruskal-Wallis)       │                     │
                  │                   │                     │
                  └──────── merge ────┴─────────────────────┘
                              │
                              ▼
                          figures.py
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
            figures/*.pdf            appendix/*.tex (auto-generated)
                │                           │
                └────── paper/main.tex ─────┘
```

### Cache fingerprinting (per stage)

Each Parquet file carries a fingerprint of its inputs in metadata. **Fingerprints exclude non-deterministic write-time artifacts** (e.g., LanceDB index timestamps).

| Cache file | Fingerprint of |
|---|---|
| `palace_snapshot_2026-05-16/` | stable hash of `(sorted drawer_ids, filed_at values, chunk_index values)` |
| `embeddings.parquet` | normalize output hash + bge-m3 revision |
| `neighbors_K20.parquet` | embeddings hash + K |
| `nn_novelty.parquet` | neighbors hash + algorithm version |
| `recon_residual_K20.parquet` | neighbors hash + K + λ + LLE version |
| `llm_surprise_subsample.parquet` | sample IDs + prompt template hash + model name |
| `downstream_eval_results.parquet` | recon_residual hash + threshold list + LME version |

`cli.py status` walks the DAG, compares fingerprints, reports stale stages.

### Resumability for `llm_surprise` (the only long-running stage)

**Atomic-write contract** (consistent terminology — Section 2 and Section 4 now align):

- Write each completed call to a single-row Parquet in `~/.castle/research/llm_surprise_partials/{drawer_id}.parquet`. Single-file writes are atomic via close-and-rename.
- Periodically (every 50 calls) merge partials into `llm_surprise_subsample.parquet` via `pyarrow.concat_tables()`. Merge is atomic via write-to-`.tmp` + rename.
- On crash / Ctrl-C: next run reads master + partials, skips already-completed `drawer_id`s, continues.
- **Hard cost cap**: `--max-cost 200` tracks cumulative `total_cost_usd` from each `claude -p` response envelope; aborts before exceeding.
- **Reasoning spot-check**: every 50 calls, print the most recent `(drawer_id, score, reasoning)` to stdout for human sanity-check.

### Reproducibility manifest

`research/info_theory/REPRODUCIBILITY.md` lists:

- Python version (`>=3.11`)
- Pinned lockfile (uv/Poetry, committed)
- `bge-m3` model revision (HF commit hash)
- Castle source-tree commit hash
- **Palace snapshot fingerprint** (from `seeds.yaml`)
- LongMemEval release version
- Seeds in `seeds.yaml`: `numpy_seed`, `torch_seed`, `subsample_seed`, `bootstrap_seed`, `prompt_template_seed`, `downstream_eval_seed`
- Exact `claude-cli` invocation: model name (e.g., `claude-haiku-4-5-20251001`), prompt template SHA, `--no-session-persistence` and `--disable-slash-commands` flags
- Hardware notes: **CUDA GPU confirmed available** (CPU-only fallback would add ~2-4 hours and is not the target configuration)

### Initial-numbers chicken-and-egg

The CI Tier 4 verifies that fitted parameters match `paper/results.yaml`. But who establishes `results.yaml` first? **Two-machine verification protocol**:

1. Developer runs full pipeline on Machine A (the dev box, GPU available).
2. Output is written to `results.yaml`.
3. Developer runs Tier 4 reproducibility check on Machine B (a fresh checkout, ideally a different machine). On match (within tolerance), `results.yaml` is committed.
4. From that point forward, CI verifies on every commit.

This catches single-machine determinism bugs that pure CI cannot — e.g., a hardware-specific floating-point quirk.

### Tolerance specification (consistent across spec)

- **Same-machine same-seed runs** (CI on a single hosted runner): ±1e-6 on fitted parameters.
- **Cross-machine runs** (initial two-machine verification + reviewer reproductions): ±1e-3 on fitted parameters. Justified by bge-m3 GPU/CPU determinism ceiling.
- **R@5 deltas in H3**: ±0.5 percentage points absolute (well above floating-point noise; sensitive to LME version drift).

### Integration with existing Castle code (imports, not forks)

- `from cognitive_castle.embedding import get_embedder` — same embedder Castle uses
- `from cognitive_castle.miner import ChunkConfig, chunk_text` — same chunking parameters
- `from benchmarks.longmemeval_bench import load_questions` — single source of truth for LME loading (after refactor)
- `from cognitive_castle.llm_client import get_provider` — instantiates `claude-cli` provider (PR #49)

### Caching layout (Parquet, in `~/.castle/research/`)

- `palace_snapshot_2026-05-16/` — frozen palace at experiment start
- `longmemeval_drawers.parquet` — chunked LME drawers
- `embeddings.parquet`
- `neighbors_K{K}.parquet` — one file per K
- `metadata.parquet`
- `nn_novelty.parquet`
- `recon_residual_K{K}.parquet` — one file per K
- `llm_surprise_subsample.parquet` — master file post-merge
- `llm_surprise_partials/` — single-row Parquets pre-merge
- `downstream_eval_results.parquet` — H3 R@5 deltas per threshold
- `heterogeneity_results.parquet` — H1 Kruskal-Wallis statistics per source-type group

## Testing and reproducibility

Four test tiers, plus a reproducibility verification step.

### Tier 1 — Unit tests (per pipeline module)

Run on every commit via CI. Fast, deterministic, no external deps.

| Module | What gets tested |
|---|---|
| `snapshot_palace.py` | snapshot procedure, stable fingerprint (LanceDB-index-independent), read-only verification |
| `load_palace.py` | `metadata_json` parsing, `filed_at` extraction, missing-field handling |
| `load_longmemeval.py` | LME → drawer chunking with Castle's miner; refactor of `longmemeval_bench.py` accessor |
| `normalize.py` | code-block stripping, token truncation, edge cases |
| `embed.py` | mocked embedder; caching keys; bge-m3 model-revision sentinel |
| `neighbors.py` | KNN lookup correctness on synthetic 1000-drawer set |
| `nn_novelty.py` | edge cases: empty prior set, single prior, all-identical priors |
| `recon_residual.py` | closed-form LLE on hand-crafted cases; Tikhonov-regularized singular-matrix recovery; `K_floor` behavior |
| `llm_surprise.py` | subprocess mocked; prompt construction, response parsing, malformed-JSON handling, resumability, atomic partial-Parquet writes |
| `stratify.py` | floor enforcement; proportional allocation; **termination guard** when total floor > n_total |
| `downstream_eval.py` | mocked retrieval; correctness of info-weighted corpus subset; threshold sweep |
| `fit_decay.py` | power-law (heteroscedastic) and exponential (homoscedastic) MLE on synthetic data with known parameters |
| `block_bootstrap.py` | CI coverage rate on synthetic AR(1); **source-aware blocking** (blocks span source-file boundaries) |
| `heterogeneity.py` | Kruskal-Wallis on known-differing-source-type synthetic data |
| `correlations.py` | Spearman + Pearson on known-correlated synthetic pairs |
| `cli.py` | `cost-estimate` produces sensible numbers without real API calls; `status` reports correct stale stages |

### Tier 2 — Synthetic-data sanity checks

**Estimator sanity**:

| Test | Setup | Expected |
|---|---|---|
| `nn_novelty` decays monotonically | Drawers as small perturbations | `nn_novelty` decreases as N grows |
| `nn_novelty` stays high under orthogonality | Orthogonal drawers | `nn_novelty ≈ 1.0` |
| `recon_residual` is ~0 when in span | `d_t = 0.5·d_1 + 0.5·d_2` | `recon_residual < 1e-6` |
| `recon_residual` is large under orthogonality | d_t orthogonal to K priors | `recon_residual ≈ 1` |
| LLE handles collinear neighbors | All K priors identical | Tikhonov-regularized solve succeeds; finite residual |

**Decay-fit sanity**:

| Test | Setup | Expected |
|---|---|---|
| Power-law recovery (heteroscedastic) | `y = N^(-0.5) + N^(-0.5)·N(0,1)`, N=1000 | Fitted `α = 0.5 ± 0.05` |
| Exponential recovery | `y = 1 + 9·exp(-N/100) + N(0,0.1)` | Fitted `τ = 100 ± 5`, `c=1` |
| Model selection | Generate from power-law, fit both | Power law wins, AIC weight > 0.95 |
| Null rejection | Generate shuffled-order from real corpus | Real-order AIC improves at FDR-corrected q<0.05 |

**Heterogeneity sanity (H1)**:

| Test | Setup | Expected |
|---|---|---|
| Kruskal-Wallis detects difference | Synth: source A has α=0.3, source B has α=0.7, n=20 strata each | `p < 0.05` |
| Kruskal-Wallis rejects null | Both sources from α=0.5 | `p > 0.05` typically |

**Bootstrap sanity**:

| Test | Setup | Expected |
|---|---|---|
| Coverage rate matches nominal | Synthetic AR(1), 1000 reps × 200 datasets | 95% CIs cover truth ~95% (binomial test α=0.01) |
| Source-aware blocks reduce variance correctly | Synth with strong within-file correlation | Source-aware blocks produce wider CIs than naive blocks |

**Downstream sanity (H3)**:

| Test | Setup | Expected |
|---|---|---|
| Info-weighting helps on synth | Generate corpus where bottom-X% are noise, top is signal | R@5 improves at X=10, 25, 50 |
| Info-weighting neutral on uniform corpus | Generate corpus where all drawers equally informative | R@5 delta ~0 (within CI) |

### Tier 3 — Integration / cache tests

Run on every commit. Validates pipeline DAG.

- **Stage skip-if-cached**: run stage, mtime outputs, re-run, verify untouched. Modify input, verify refreshed.
- **Fingerprint propagation**: change K, verify `recon_residual_K{old}` marked stale, `recon_residual_K{new}` rebuilt.
- **Resumability**: simulate kill-9 mid-`llm_surprise`, verify restart processes only missing drawers, total stays at 1000.
- **Cost cap**: run `llm_surprise` against mock with `--max-cost 0.01`, verify aborts.
- **Atomic-write contract**: write partials, kill mid-write, verify no corruption; merge produces master with no duplicates.
- **Cross-corpus merge**: load palace + LME fixtures, merge, verify nullable Castle-specific fields handled correctly (no schema errors, no silent type coercion).
- **End-to-end smoke**: pipeline runs on 100-drawer fixture in <30s. Asserts file existence + numerical sentinels.

### Tier 4 — Reproducibility verification

- **Cross-machine re-run** (CI for LME-only, manual for palace): on fixed Castle commit + fixed LME release + fixed seeds, fitted decay parameters match `paper/results.yaml` within **±1e-3** (cross-machine) or **±1e-6** (same-machine).
- **`results.yaml` is checked in**: every paper number lives here. Updates PR-reviewed. CI compares freshly-fitted numbers to YAML, fails on divergence.
- **Initial two-machine verification protocol**: developer runs on Machine A + Machine B before first commit of `results.yaml`. Documented in `REPRODUCIBILITY.md`.
- **Appendix tables auto-generated**: `analysis/figures.py --tables` reads `results.yaml`, emits LaTeX `.tex` in `paper/appendix/`. Single source of truth.
- **Seeds checked in**: any change → new run → new `results.yaml`.

### CI shape

- **On every commit**: Tier 1 unit (full), Tier 3 integration (subset), Tier 4 LME reproducibility on 1000-drawer subsample (fast).
- **Nightly**: full Tier 2 synthetic sweep, Tier 3 full suite, full LME reproducibility, **H3 downstream check** on a 100-question LME subset.
- **Pre-paper-release**: Tier 4 full run on both corpora end-to-end + full LongMemEval H3 evaluation. Manual gate.

New workflow: `.github/workflows/research-info-theory.yml`. Same Python matrix as Castle, HF cache warm-up for bge-m3, skips palace tests (local-only).

### What we explicitly DON'T test

- **Real `claude -p` calls in CI**: too expensive, non-deterministic. Mocked everywhere except manual pre-release.
- **Real palace data in CI**: palace is local-private. Palace tests run locally pre-push.
- **bge-m3 numerical reproducibility across hardware**: ε-level GPU/CPU differences acknowledged via the cross-machine tolerance band.
- **PyPI release tests**: not shipping to PyPI.

### Coverage expectation

**Assertion coverage of numerical results** is the meaningful metric, not line coverage. Every paper number has a test asserting its value. Expected line coverage 60-75%; paper-number coverage 100%.

## Paper structure, scope, success criteria

### Paper structure

| Section | Length | Content |
|---|---|---|
| Abstract | 250 words | Methodology contribution + H1 source-type heterogeneity finding + H3 downstream result |
| 1. Introduction | 1 page | Frames as methodology paper; cites MemPalace + Castle as data infrastructure; motivates source-type analysis as a novel axis |
| 2. Related work | 1 page | mem0, Zep, Letta, MemPalace, MemGPT, LongMemEval, classical info theory, locally linear embedding |
| 3. Methods | 3 pages | Estimators A/B/C, corpora + stratification, H1/H2/H3 procedures, statistical correction |
| 4. Results | 3-4 pages | H2 per-cell fits, H1 source-type violin plot (likely headline figure), A/B/C correlations, **H3 downstream R@5 deltas** |
| 5. Discussion | 1.5 pages | Heterogeneity implications; what verbatim-vs-lossy means information-theoretically; downstream-validation interpretation |
| 6. Limitations | 0.5 page | n=1 user palace; bge-m3 dependency; LME stratification asymmetry; LLM-rating-not-log-prob; within-file correlation |
| 7. Conclusion | 0.5 page | What's next; Phase 2 pointer |
| Appendix | 3-4 pages | K-sensitivity, λ-sensitivity, block-size sensitivity, per-cell tables, prompt template, raw-text vs. normalized, downstream per-question-type breakdown |

Total: 9-10 pages main + appendix.

### Paper LaTeX location

`research/info_theory/paper/main.tex`. Same directory as code, alongside `results.yaml`. Future-portable.

### Venue strategy

1. **arXiv preprint** — primary distribution. **Required for ship.**
2. **Workshop submission** — encouraged, not required for ship:
   - NeurIPS Memory in Foundation Models workshop (Oct/Nov)
   - ICLR Mathematical and Empirical Understanding of Foundation Models (March)
   - COLM workshops (summer)
3. **Blog post + Twitter/X** — same-week as arXiv.

Not targeting NeurIPS/ICLR/ACL main track.

### Timeline estimate (post-pivot)

| Phase | Duration |
|---|---|
| Implementation (incl. `downstream_eval.py`) | **3.5 weeks** |
| First experimental run + debugging | **1 week** |
| C-stage subsample run | **1-2 days wall-clock** (7-12 hr compute, 1-2 reruns) |
| **H3 downstream evaluation** | **3-5 days** |
| Analysis + figures | **1 week** |
| Paper drafting | **3 weeks** |
| **Total** | **9-11 weeks part-time** |

### In scope (Phase 1)

- Estimators A, B, C per [Estimator architecture](#estimator-architecture)
- Palace + LongMemEval corpora per [Corpora](#corpora)
- Hypotheses H1 (heterogeneity), H2 (saturation form), H3 (downstream utility)
- Statistical procedure per [Hypothesis structure](#hypothesis-structure)
- Code in `research/info_theory/` per [Data flow](#data-flow-and-code-organization)
- Testing tiers per [Testing](#testing-and-reproducibility)
- arXiv preprint + (optional) workshop submission + blog post + open-source code

### Out of scope (deferred to Phase 2 or future work)

- `castle entropy` CLI subcommand
- Info-aware mining (`castle mine --skip-low-info`)
- Saturation-aware search ranking
- True log-prob extraction for C
- AAAK rate-distortion analysis (sequel paper)
- Multi-user federated saturation analysis
- Real-time saturation tracking
- Conversation-time vs. palace-time ordering (paper footnote)
- Synthetic-palace generator
- Castle production integration

### Success criteria

Phase 1 **ships** when:

- [ ] Paper draft on arXiv
- [ ] Code in `research/info_theory/` on `develop`
- [ ] `paper/results.yaml` committed; CI passes on LongMemEval
- [ ] At least **5 fittable cells per corpus** (H2 has data behind it)
- [ ] H1 reported with effect size: per-source-type α distribution, Kruskal-Wallis statistic, violin plot
- [ ] H3 reported: R@5 deltas at thresholds {10%, 25%, 50%} with bootstrap CIs
- [ ] Spearman correlations `(A, C)` and `(B, C)` reported with bootstrap CIs

Workshop submission encouraged, not required.

Authorship policy: **Ladislav Bihari decides at submission time based on the target venue's AI-co-authorship policy.**

Phase 1 is **complete-but-pivoted** if:

- **H1 null (no source-type heterogeneity)**: paper publishes "source type does not meaningfully predict decay behavior in our corpora" — also publishable. Likely indicates either confound (e.g., topic diversity dominates source type) or insufficient power. Reframes Discussion.
- **H2 null (no detectable saturation)**: paper publishes "verbatim AI memory does NOT show clean parametric saturation in our corpora; we provide upper bounds on decay rates" — methodologically still solid.
- **H3 null (info-weighting doesn't help)**: paper publishes "estimator is descriptive but does not improve downstream retrieval at tested thresholds" — saves Phase 2 from a bad path; still publishable as a negative result.
- **Asymmetric findings** (saturation in palace only, not LME, or vice versa): explicitly framed as a finding, not a failure. Discussion section addresses why.

Phase 1 **fails** (rethink) if:

- C-stage technical failure (rate-limit blocks > 50% of calls; costs blow past $200 even with `--max-cost`)
- bge-m3 turns out uninformative for chat-text, invalidating A and B simultaneously
- Either corpus supports < 5 fittable cells (insufficient data for H1)
- **H3 downstream experiment cannot be set up** (LME benchmark harness too fragile to support the info-weighted variant)

### Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Cost overrun on C | Medium | `--max-cost 200` hard cap; n=50 dry-run before n=1000 |
| Subscription rate limit throttles claude-cli batch | Medium | Serial processing; spread across 2-3 days; resumable design absorbs pauses |
| LME asymmetry attacked by reviewers | Medium-High | Methods + Limitations honest; counter-frame as informative |
| Palace + LME show different decays | Medium | Report both; asymmetric findings explicitly handled as pivot scenario |
| Block size choice attacked | Low | Adaptive block size + sensitivity at ±50% in appendix |
| Single-user palace ungeneralizable | High | Limitations acknowledges; paper reframed as methodology, not generalization |
| bge-m3 underestimates code-heavy drawers | Medium | Raw-text sensitivity in appendix |
| Palace grows during experiment | High | Snapshot at start; all stages read from snapshot |
| `longmemeval_bench.py` not importable | Medium | Spec acknowledges minor refactor; ~1 day budget allocated |
| H3 downstream experiment shows no improvement | Medium | Publishable as negative result; reframes Phase 2 motivation |
| LME version drift between local and CI | Low | Pin LME release version in REPRODUCIBILITY.md |

## Confirmed design decisions

- **C-stage backend**: `claude-cli` provider (PR #49). Reuses Claude Code subscription auth.
- **bge-m3 hardware**: CUDA GPU confirmed available.
- **arXiv category**: `cs.IR` + `cs.AI` (revisable at submission).
- **Paper framing**: methodology + heterogeneity + downstream validation. Source-type heterogeneity is the likely headline.
- **Timestamp field**: `filed_at` from `metadata_json` (verified against Castle schema 2026-05-16). Ordering tiebreaker: `chunk_index`.

---

End of design spec.
