# Information Theory of Verbatim Memory — Design Spec

**Date:** 2026-05-16
**Status:** Draft, awaiting user review
**Scope:** Phase 1 — research artifact only (estimator + experiment + paper). Castle production integration (info-aware mining, `castle entropy` subcommand, saturation-aware ranking) deferred to a separate Phase 2 spec.

## Background

Castle's design promise is *verbatim memory*: every word the user has shared is stored exactly as it appeared. The architectural inheritance from MemPalace makes this a hard constraint, not a configurable knob.

A consequence of verbatim-only storage is **redundancy**. A "what is AAAK" search currently returns 8 near-identical drawers, each from a different past session. Dense embeddings see them as nearly the same point; the KG sees the same entities; SOAR re-ranks the same recency cluster. **Castle has no formal way to say "the 1st drawer added 4.2 bits of new information; the 8th added 0.03 bits."** The verbatim-only principle is a *storage* claim. There is no corresponding *information* claim.

This spec defines an experiment that:

1. Measures the conditional information content `I(d_t | D_<t)` of each drawer in Castle's palace given its predecessors.
2. Tests whether the marginal information rate decays as the palace grows — i.e., whether **verbatim AI conversation memory saturates**.
3. Produces a paper-grade analysis published on arXiv, with reproducibility on the public LongMemEval corpus.

Phase 1 ends with a paper draft on arXiv and reproducibility code in `research/info_theory/`. Phase 2 (separate spec) uses the validated estimator to drive info-aware mining and search in Castle proper.

### Why Castle specifically can do this

Three uncommon ingredients sit in the same project:

- **Verbatim storage**: the ground truth `D_<t` is uncorrupted. Most memory systems summarize before they can measure.
- **Multiple complementary retrievers** — dense, FTS, KG. We can use them as ensemble predictors of `P(d_t | D_<t)`.
- **A real 65,575-drawer corpus**: most papers in this space test on synthetic data because they don't have one user's months of verbatim conversation.

### Phase 2 forward pointer (not in this spec)

Once Phase 1 validates the estimator, Phase 2 wires it into Castle: a `castle entropy` subcommand exposing per-stratum saturation curves; an info-aware mining mode (`castle mine --skip-low-info`) that drops drawers below an info threshold; saturation-aware ranking (`info_score × relevance`) that collapses near-duplicate retrievals. Phase 2 specs after Phase 1 ships.

## Hypothesis structure

The core question is whether the marginal information rate `I(d_t | D_<t)` *declines as a room grows*. That is a **regression problem** over a `(N, info_score)` time series — not a distribution-fitting problem over a population of values. Clauset–Shalizi–Newman methodology, designed for distribution-of-values claims, is the wrong tool. We use nonlinear regression with proper model comparison instead.

### The falsifiable claim

> In each stratum (corpus × room × source-type for palace; question_id for LongMemEval) with sufficient data, one of {power-law decay, exponential decay-to-floor} fits the smoothed marginal-information sequence with statistically significant improvement over a shuffled-order null (FDR-corrected `p < 0.05`).

Both halves are testable. If no decay model beats the null, saturation is a myth — also a publishable result.

### Variables and operational definitions

- **Drawer ordering**: by `metadata.created_at` (palace-growth time, when the drawer was filed). Not conversation-time. Footnote in paper: "conversation-time ordering is a complementary view we leave to future work."
- **`info_score(d_t, N)`**: computed from three estimators (next section). The **primary decay fit is performed on `recon_residual`** (Estimator B, the principled one); `nn_novelty` (A) and `llm_surprise` (C) are reported as validation.
- **Saturation point `N*`**: smallest `N` such that the LOWESS-smoothed `info_score` drops below 5% of its initial 100-drawer running mean *and stays there* for `≥50` consecutive drawers. Operational, threshold-based, robust to single-point noise.

### Two candidate models — and only two

- **Power-law decay**: `info(N) = a · N^(-α) + ε`. No characteristic scale; saturation is asymptotic.
- **Exponential decay to floor**: `info(N) = c + (a − c) · exp(−N/τ) + ε`. Characteristic timescale `τ`; predictable saturation.

Log-normal and stretched-exponential are dropped — YAGNI for the first paper. If reviewers ask, "future work."

### Procedure (per stratum)

1. **Stratify**: split corpus by stratum identifier (see [Corpora](#corpora)). Palace strata are `wing × room × added_by`; LongMemEval strata are `question_id`. Three palace source types: `mcp` (hand-filed via MCP tools), `session-hook` (Stop-hook checkpoints), `miner` (auto-mined transcripts). Report each separately — they are different populations.
2. **Compute** the `(N, info_score)` sequence for that stratum, with `N` indexing drawer position in `created_at` order.
3. **Fit both models** via nonlinear least squares with **block bootstrap confidence intervals** (block size 100 drawers, B = 1000 resamples). Block bootstrap addresses the IID violation from session-clustered drawers; sensitivity at blocks of 50 and 200 reported in appendix.
4. **Compare models** via AIC. Report ΔAIC and Akaike weights.
5. **Null baseline**: shuffle drawer order 1000 times within each stratum, refit both models. Report empirical distribution of fitted parameters under the null. Real-order fits must lie outside the 95th percentile of the null to count as significant.
6. **Multiple-comparisons correction**: realistic test count is **~110–210 hypothesis tests** (≈3-5 fittable palace strata + ≈50–100 fittable LME strata, each tested against 2 models, real vs. null). Apply Benjamini–Hochberg FDR control at q = 0.05.

### Heterogeneity handling

The 48,848-drawer `_home_lbihari_cognitive_castle/general` room is dominated by `miner` source; `wing_castle/decisions` is `mcp`-only at 8 drawers. Comparing them as "rooms" without stratifying conflates different populations. Stratification forces honesty: saturation curves reported per `(room × source-type)` pair with ≥200 drawers (statistical-power floor). Sub-floor strata reported descriptively, not fit.

### What the paper concludes (plain English)

For each fittable stratum, we report:

- Which decay model wins (with AIC weight)
- Fitted parameter (α for power-law, τ for exponential) with block-bootstrap CI
- Whether the fit beats the shuffled-order null at FDR-corrected significance
- The `N*` saturation point under the operational definition

Headline figure: small-multiples grid of `(N, recon_residual)` plots with fitted curves overlaid, one panel per stratum, null distribution shaded. Headline number: across all sufficiently-large strata in both corpora, what fraction show statistically significant saturation, and what fraction prefer power-law over exponential.

## Estimator architecture

Three estimators answering the same question — *how surprising is `d_t` given `D_<t`?* — at three rigor/cost levels. None is literally `−log P(d_t | D_<t)`; the paper says so explicitly.

### Shared inputs

- Target drawer `d_t` with text + `created_at`
- **Prior set** `D_<t` is corpus-specific:
  - **Palace**: same `wing` AND `created_at < d_t.created_at` (avoids cross-domain confusion)
  - **LongMemEval**: same `session_id` AND `created_at < d_t.created_at`

The LME prior-set unit (`session_id`) is **finer-grained** than the LME stratum unit (`question_id`). This is intentional: prior-set tracks the *local conversational context* a memory system would actually see; stratum tracks the *analytical grouping* for cross-question comparison. This asymmetry is documented in the paper Methods section as a deliberate choice, not an artifact.

- Embeddings: bge-m3, cached as Parquet (see [Caching](#caching-layout)) — re-runs do not re-embed.

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

**True Roweis–Saul LLE weights**: unconstrained weights summing to 1, closed-form solution via small linear system. No non-negativity constraint, no convex-hull requirement.

```
K_effective = min(K_target, |D_<t|)      # K_target = 20
if K_effective < K_floor (= 5):
    recon_residual = null  # excluded from B analysis; A still computed
else:
    fetch K_effective nearest priors (cosine)
    solve LLE: minimize ||embed(d_t) - Σ w_k embed(d_k)||²
               subject to Σ w_k = 1
    recon_residual = ||residual||_2
```

- Closed-form (no QP) → ~5ms per drawer with K=20.
- `K_floor = 5`: B is null for the first 5 drawers in each stratum; flagged `is_first=true`.
- **Sensitivity**: report K ∈ {10, 20, 50, 100} in appendix.
- **Failure mode**: bounded by bge-m3 quality. C is the validation check.
- Cost: ~65k × 5ms ≈ 5–10 min, $0.

### C — `llm_surprise` (subsample validation, gold standard)

For a stratified subsample of `n=1000` drawers, ask Haiku 4.5 (via the **`anthropic` provider**) to rate predictability of `d_t` given recency-selected priors.

**Provider choice clarification**: C uses the `anthropic` provider in `cognitive_castle/llm_client.py` with a dedicated `ANTHROPIC_API_KEY` — **not** the `claude-cli` provider shipped this week (PR #49). Rationale: a 1000-call batch (7-12 hours wall-clock, ~$80-150) needs separable billing and predictable rate limits independent of the user's Claude Code subscription. `claude-cli` is right for interactive single calls; `anthropic` is right for batch.

- **Prior selection**: **top-20 by recency** from `D_<t` (most recent 20 strictly preceding `d_t`). Deterministic, no weighting function to justify.
- **Prompt**: *"Given these 20 prior memory entries [list], rate on a 1–10 scale how predictable the following entry is. 10 = entirely derivable from priors, 1 = entirely novel. Return JSON: `{score: int, reasoning: short str}`."*
- **`llm_surprise = 10 − score`** (higher = more novel, sign-aligned with A and B).
- **Reasoning field**: stored as `llm_surprise_reasoning_spotcheck` for human spot-check only, **not analyzed quantitatively**.
- **Subsample-allocation algorithm** (explicit):
  1. Identify all strata; compute proportional allocation across `n=1000`.
  2. For any stratum below floor (`20` drawers), raise to floor by stealing proportionally from above-floor strata.
  3. Iterate until all floors met. Final allocation deterministic + reproducible from a seed.
- **Cross-corpus split**: proportional to corpus size after stratification (palace ~65k drawers, LME ~75-125k drawers → working estimate ~400 palace + ~600 LME of n=1000; final split derived from the allocation algorithm).

### Cost & runtime

- **Prompt size**: 20 priors × ~500 avg tokens + instructions ≈ **15k–25k input tokens** per call.
- **Per-call cost (Haiku 4.5)**: ~$0.08–$0.15.
- **Per-call wall-clock**: ~25–45s at that prompt size.
- **Total C cost**: **$80–$150**.
- **Total C wall-clock**: **7–12 hours**.

| Estimator | Drawers | Per-drawer | Wall-clock | $ |
|---|---|---|---|---|
| A `nn_novelty` | ~65k + LME | ~10ms | ~11 min | $0 |
| B `recon_residual` | ~65k + LME | ~5ms (LLE closed-form) | ~5–10 min | $0 |
| C `llm_surprise` | 1000 subsample | 25–45s + $0.08–0.15 | 7–12 hr | $80–150 |

### Correlation analysis (validation of A and B against C)

- **Primary**: **Spearman rank correlation** between `(nn_novelty, llm_surprise)` and `(recon_residual, llm_surprise)` on the 1000-drawer subsample.
- **Supplementary**: Pearson, acknowledging C's discrete 1–10 scale vs. continuous A and B.
- **Per-stratum**: each stratum reports its own coefficient with bootstrap CI (since C has a floor of 20/stratum, within-stratum estimates are estimable).

### Output schema (per drawer)

```json
{
  "drawer_id": "drawer_wing_castle_decisions_1735ceedd5...",
  "corpus": "palace",
  "stratum_id": "wing_castle::decisions::mcp",
  "wing": "wing_castle",
  "room": "decisions",
  "added_by": "mcp",
  "session_id": null,
  "question_id": null,
  "created_at": "2026-05-15T22:17:29Z",
  "N_in_stratum": 7,
  "is_first": false,
  "nn_novelty": 0.81,
  "recon_residual": 0.43,
  "recon_residual_K": 20,
  "llm_surprise": 8.0,
  "llm_surprise_reasoning_spotcheck": "Novel decision rationale about claude-cli provider...",
  "llm_surprise_prompt_tokens": 18432,
  "llm_surprise_completion_tokens": 87,
  "llm_surprise_cost_usd": 0.0921
}
```

For LME rows: `wing=null`, `room=null`, `added_by=null`, `session_id` populated, `question_id` populated. `stratum_id = f"longmemeval::question_{question_id}"`.

### Failure handling

- **Prior set empty / below `K_floor` for B**: `recon_residual=null`, drawer marked `is_first=true`, analysis filters apply.
- **C call fails** (timeout, malformed JSON, API error): record `llm_surprise=null`, audit fields populated. Null rate reported in paper Methods. Hard cap: 5% null tolerated; over that, halt and investigate.
- **Embedder unavailable**: A and B abort fast with clear error. C runs standalone (doesn't need embeddings).

## Corpora

### Corpus 1 — Palace (private, headline data)

- **Source**: snapshot of `~/.castle/palace/` taken at experiment start (see [Palace snapshot](#palace-snapshot) below).
- **Size**: 65,575 drawers as of 2026-05-16.
- **Composition** (from `castle status` + audit this session):

| Wing | Drawers | Dominant `added_by` |
|---|---|---|
| `_home_lbihari_cognitive_castle` | 48,848 | `miner` |
| `projects` | 14,000 | `miner` |
| `sessions` | 2,651 | `miner` |
| `wing_castle` | 47 | `mcp` + `session-hook` |
| `wing_lbihari` | 29 | `session-hook` |

Headline asymmetry: **99.99% of drawers are `miner`/`session-hook`; only ~10 are `mcp` (hand-filed via MCP tools).** Stratification will surface differences across source types — itself a finding.

- **Privacy**: stays local. The paper reports aggregate statistics (fitted decay parameters, correlations) — not drawer contents. A small number of `reasoning_spotcheck` excerpts (10-20 illustrative drawers) appear in the paper appendix; those are user-reviewed before publication.

### Palace snapshot

The palace is **actively growing** via the Stop hook. The experiment runs over 6-10 weeks. Without snapshotting, drawer counts and `created_at` orderings shift underneath us → numbers can't be reproduced.

**Snapshot procedure** (in `pipeline/snapshot_palace.py`):

1. At experiment start: `cp -r ~/.castle/palace/ ~/.castle/research/palace_snapshot_2026-05-16/`
2. Record snapshot fingerprint: SHA256 of `(LanceDB files + drawer count + max created_at)` → written to `research/info_theory/seeds.yaml`
3. All downstream stages read from `palace_snapshot_2026-05-16/`, never from live palace.

The Reproducibility manifest includes the snapshot fingerprint alongside the Castle commit hash.

### Corpus 2 — LongMemEval (public, reproducibility)

- **Source**: already in `benchmarks/longmemeval_bench.py`; this code may require **minor refactoring** to expose a `load_questions()` function as an importable API rather than as a script-only entrypoint.
- **Size**: 500 questions × ~50 sessions/question ≈ 25k sessions. After chunking through Castle's miner (consistent with palace mining): estimated **~75k–125k drawers**.
- **Schema** (after chunking): `text`, `created_at`, `session_id`, `question_id`, `question_type` ∈ {single-session-user, single-session-assistant, single-session-preference, temporal-reasoning, knowledge-update, multi-session}. No `wing`/`room`/`added_by` — Castle-specific fields stay `null`.
- **Why include LME**: reviewers can reproduce. The headline-finding numbers must be reported on the public corpus, not just the private palace, or the paper is unfalsifiable.

### Schema verification step

Before running estimators, validate corpus completeness:

- Confirm `created_at` populated for all drawers in scope.
- For palace drawers missing `created_at`: fall back to `metadata.timestamp` if present.
- For drawers missing both: exclude from analysis; record exclusion count.
- Report exclusion count in paper Methods.

### Cross-corpus stratification reconciliation

| | Palace stratum | LongMemEval stratum |
|---|---|---|
| Identifier | `f"{wing}::{room}::{added_by}"` | `f"longmemeval::question_{question_id}"` |
| Ordering within stratum | `created_at` ascending | `(session_index, turn_index)` ascending |
| Min drawers for fit | ≥200 (power floor) | ≥200 |

**The stratification asymmetry is named explicitly in the paper Methods section**: "Palace strata are fine-grained (`wing × room × added_by`) because Castle's schema supports it; LongMemEval strata are coarse (`question_id`) because LME's schema does. We report saturation behavior in both and note where the comparison breaks down. The asymmetry is informative: it characterizes the trade-off between schema richness and reproducibility in AI memory research."

### Loading LME → drawer format

Reuse `benchmarks/longmemeval_bench.py`'s existing session-loading logic via import (refactoring it as needed). Add an adapter that:

1. Loads LME questions + their session histories
2. For each session, runs Castle's miner (`cognitive_castle.miner`) with the **same chunking parameters used for palace ingestion** — guarantees comparable drawer sizes across corpora
3. Tags each chunked drawer with `question_id`, `session_id`, position metadata; leaves Castle-only fields `null`
4. Writes to a Parquet file alongside the palace snapshot: `~/.castle/research/longmemeval_drawers.parquet`

Reusing existing benchmark code matters — divergent chunking between corpora would silently bias the comparison.

### Statistical-power floor

The `≥200 drawers / stratum` floor comes from power analysis: for a power-law decay fit with `α ≈ 0.5` (a priori estimate) and bootstrap CI tightness target of ±0.1 on α, simulation suggests ~150 drawers. Round up to 200 for safety. (Full simulation in paper appendix.)

### What rooms/strata will and won't fit

| Stratum | Drawers | Fittable? |
|---|---|---|
| `palace::_home_lbihari_cognitive_castle::general::miner` | ~48k | **Yes** |
| `palace::projects::general::miner` | ~14k | **Yes** |
| `palace::sessions::technical::miner` | ~2.4k | **Yes** |
| `palace::sessions::architecture::miner` | 164 | **No — below floor**; descriptive only |
| `palace::wing_castle::decisions::mcp` | 8 | **No — far below floor**; reported as single case study with all 8 drawers shown |
| `longmemeval::question_X` (typical) | ~150–300 | **Marginal** — those ≥200 fit, others descriptive |

The paper frames this honestly: "fittable strata are dominated by auto-mining sources; the deliberate `mcp` source is too sparse for power-law fits, itself a finding about how hand-curation works in practice."

## Data flow and code organization

### Where the code lives

New top-level dir `research/info_theory/` — sibling of `benchmarks/`, **not inside `cognitive_castle/`** (this is paper code, not Castle library code).

```
research/info_theory/
├── README.md
├── pyproject.toml          # paper-specific deps (statsmodels, powerlaw, matplotlib)
├── REPRODUCIBILITY.md
├── seeds.yaml              # single source of truth for all RNG seeds + snapshot fingerprint
├── paper/
│   ├── main.tex
│   ├── appendix.tex
│   ├── results.yaml        # every paper number lives here, CI-verified
│   └── figures/            # generated by analysis/figures.py
├── pipeline/
│   ├── snapshot_palace.py  # snapshot LanceDB at experiment start
│   ├── load_palace.py      # snapshot → Parquet
│   ├── load_longmemeval.py # imports benchmarks/longmemeval_bench.py (with refactor as needed)
│   ├── normalize.py        # strip code, truncate to 2000 tokens
│   ├── embed.py            # imports cognitive_castle.embedding
│   ├── neighbors.py
│   ├── nn_novelty.py
│   ├── recon_residual.py   # LLE closed-form
│   ├── llm_surprise.py     # anthropic provider, resumable, partial-Parquet writes
│   └── stratify.py
├── analysis/
│   ├── fit_decay.py        # power-law + exponential MLE
│   ├── block_bootstrap.py
│   ├── correlations.py
│   └── figures.py          # `--tables` emits LaTeX from results.yaml
├── cli.py
├── tests/test_*.py
└── outputs/                # gitignored; mirrors ~/.castle/research/ Parquet
```

### Why a separate top-level dir, not inside `cognitive_castle/`

1. **Different dependency footprint** — statsmodels, `powerlaw`, matplotlib. Castle stays minimal for pip users.
2. **Standalone reproducibility artifact** — others should clone-and-run without pip-installing all of Castle.
3. **Future-portable** — paper code may move to its own repo eventually. Clean seam now avoids painful split later.

Same pattern as `understanding/` (originally in echelon, vendored into Castle). Research artifacts cohabit but don't entangle.

### Entry point

```bash
# from research/info_theory/
python -m cli snapshot                        # take palace snapshot
python -m cli run --all                       # full pipeline, cache-aware
python -m cli run --stage embed               # one stage
python -m cli run --stage llm-surprise        # resumable
python -m cli status                          # show cache state, stale stages
python -m cli figures                         # regenerate plots
python -m cli figures --tables                # emit appendix LaTeX tables from results.yaml
python -m cli cost-estimate --stage llm-surprise  # dry-run before spending $
```

Each stage reads cached Parquet inputs, writes cached Parquet outputs, skips itself if outputs are newer than inputs (Makefile-style). `--force` overrides cache.

### Pipeline DAG

```
[palace LanceDB]                      [LongMemEval public]
       │                                       │
       ▼                                       ▼
  snapshot_palace.py                  load_longmemeval.py
       │                                       │
       ▼                                       │
  load_palace.py (from snapshot)               │
       │                                       │
       └─────────────── merge ─────────────────┘
                          │
                          ▼
                    normalize.py
                          │
                          ▼
                       embed.py ←──── bge-m3 (cached after first run)
                          │
                          ▼
                    neighbors.py (one Parquet per K)
                          │
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
   nn_novelty       recon_residual        stratify
                                              │
                                              ▼
                                          llm_surprise (1000 drawers, resumable)
                          │                   │
                          └──── merge ────────┘
                                  │
                                  ▼
                          fit_decay + block_bootstrap + correlations
                                  │
                                  ▼
                              figures.py
                                  │
                       ┌──────────┴──────────┐
                       ▼                     ▼
                  figures/*.pdf       appendix/*.tex (auto-generated tables)
                       │                     │
                       └──── paper/main.tex ─┘
```

### Cache fingerprinting (per stage)

Each Parquet file carries a fingerprint of its inputs in metadata:

| Cache file | Fingerprint of |
|---|---|
| `palace_snapshot_2026-05-16/` | LanceDB files SHA256 + drawer count + max(created_at) |
| `embeddings.parquet` | normalize output hash + bge-m3 revision |
| `neighbors_K20.parquet` | embeddings hash + K |
| `nn_novelty.parquet` | neighbors hash + algorithm version |
| `recon_residual_K20.parquet` | neighbors hash + K + LLE version |
| `llm_surprise_subsample.parquet` | sample IDs + prompt template hash + model name |

`cli.py status` walks the DAG, compares fingerprints, reports stale stages. A single upstream change invalidates all downstream caches.

### Resumability for `llm_surprise` (the only long-running stage)

Atomic-write contract: **write each completed call to a single-row Parquet in `~/.castle/research/llm_surprise_partials/`** (filename = drawer_id), periodically merge into the master `llm_surprise_subsample.parquet` via a checkpoint step every 50 calls. Naturally atomic, naturally resumable, easy to test.

- Process drawers serially; one `anthropic` provider call at a time.
- On crash / Ctrl-C: next run reads the master Parquet + the partials directory, skips already-completed `drawer_id`s, continues.
- **Hard cost cap**: `--max-cost 200` flag tracks cumulative input + output tokens from each Anthropic API response (`usage.input_tokens`, `usage.output_tokens`), computes cumulative cost via current Haiku pricing, aborts before exceeding the cap. Pricing constants pinned in `pipeline/pricing.py` and updated quarterly.
- **Reasoning spot-check**: every 50 calls, print the most recent `(drawer_id, score, reasoning)` to stdout so the human can sanity-check the LLM isn't drifting.

### Reproducibility manifest

`research/info_theory/REPRODUCIBILITY.md` lists:

- Python version (`>=3.11`)
- Pinned lockfile (uv/Poetry, committed)
- `bge-m3` model revision (HF commit hash)
- Castle source-tree commit hash (snapshot used for palace data)
- **Palace snapshot fingerprint** (from `seeds.yaml`)
- LongMemEval release version
- Seeds in `seeds.yaml`: `numpy_seed`, `torch_seed`, `subsample_seed`, `bootstrap_seed`, `prompt_template_seed`
- Exact `anthropic` provider configuration: model name, max-tokens, prompt template SHA
- Hardware notes: CPU model + GPU (affects wall-clock, not numerical results)

### Integration with existing Castle code (imports, not forks)

- `from cognitive_castle.embedding import get_embedder` — same embedder Castle uses
- `from cognitive_castle.miner import ChunkConfig, chunk_text` — same chunking parameters
- `from benchmarks.longmemeval_bench import load_questions` — single source of truth for LME loading (after refactor to expose loader)
- `from cognitive_castle.llm_client import get_provider` — used in `llm_surprise.py` to instantiate the `anthropic` provider (not `claude-cli` — see [Estimator C](#c--llm_surprise-subsample-validation-gold-standard) for rationale)

### Caching layout (Parquet, in `~/.castle/research/`)

- `palace_snapshot_2026-05-16/` — frozen palace at experiment start (LanceDB dir copy)
- `longmemeval_drawers.parquet` — chunked LME drawers
- `embeddings.parquet` — `(drawer_id, vector)`
- `neighbors_K{K}.parquet` — one file per K
- `metadata.parquet` — `(drawer_id, corpus, stratum_id, …)`
- `nn_novelty.parquet`
- `recon_residual_K{K}.parquet` — one file per K
- `llm_surprise_subsample.parquet` — master file after merge
- `llm_surprise_partials/` — single-row Parquets pre-merge

## Testing and reproducibility

Research code has unusual testing concerns — getting the same output numbers every time matters more than 100% line coverage. Four test tiers, plus a reproducibility verification step.

### Tier 1 — Unit tests (per pipeline module)

Run on every commit via CI. Fast, deterministic, no external deps.

| Module | What gets tested |
|---|---|
| `snapshot_palace.py` | snapshot procedure, fingerprint correctness, read-only verification |
| `normalize.py` | code-block stripping, token truncation, edge cases (empty / pure-code drawers) |
| `embed.py` | mocked embedder; caching keys; bge-m3 model-revision sentinel |
| `neighbors.py` | KNN lookup correctness on synthetic 1000-drawer set with known geometry |
| `nn_novelty.py` | edge cases: empty prior set, single prior, all-identical priors |
| `recon_residual.py` | closed-form LLE on hand-crafted cases (residual=0 when in span); `K_floor` behavior |
| `llm_surprise.py` | subprocess + HTTP mocked (no real API calls); prompt construction, response parsing, malformed-JSON handling, resumability |
| `stratify.py` | floor enforcement; proportional allocation; deterministic seed → identical sample |
| `fit_decay.py` | power-law and exponential fits on synthetic data with known parameters |
| `block_bootstrap.py` | CI coverage rate on synthetic data with known autocorrelation |
| `correlations.py` | Spearman + Pearson on known-correlated synthetic pairs |
| `cli.py` | `cost-estimate` produces sensible numbers without real API calls; `status` reports correct stale stages |

### Tier 2 — Synthetic-data sanity checks

Catch bugs that real-data tests can't, by generating data where the answer is known analytically.

**Estimator sanity**:

| Test | Setup | Expected |
|---|---|---|
| `nn_novelty` decays monotonically | Drawers as small perturbations of previous in embedding space | `nn_novelty` decreases as N grows |
| `nn_novelty` stays high under orthogonality | Orthogonal drawers in embedding space | `nn_novelty ≈ 1.0` throughout |
| `recon_residual` is ~0 when in span | `d_t = 0.5·d_1 + 0.5·d_2` | `recon_residual < 1e-6` |
| `recon_residual` is large under orthogonality | d_t orthogonal to all K priors | `recon_residual ≈ 1` |

**Decay-fit sanity**:

| Test | Setup | Expected |
|---|---|---|
| Power-law recovery | `y = N^(-0.5) + Gaussian(σ=0.1)`, N=1000 | Fitted `α = 0.5 ± 0.05` |
| Exponential recovery | `y = 1 + 9·exp(-N/100) + Gaussian(σ=0.1)` | Fitted `τ = 100 ± 5`, `c=1` |
| Model selection | Generate from power-law, fit both, check AIC | Power law wins, weight > 0.95 |
| Null rejection | Generate from shuffled-order data | Real-order AIC improves over shuffled at p<0.05 |

**Bootstrap sanity**:

| Test | Setup | Expected |
|---|---|---|
| Coverage rate matches nominal | Synthetic AR(1), 1000 reps × 200 datasets | 95% CIs cover truth ~95% (binomial test α=0.01) |
| Block-size sensitivity | Same data, blocks 50/100/200 | CIs widen with block size; consistent across |

### Tier 3 — Integration / cache tests

Run on every commit. Validates pipeline DAG.

- **Stage skip-if-cached**: run stage, mtime outputs, re-run, verify untouched. Modify input, verify refreshed.
- **Fingerprint propagation**: change K for `neighbors`, verify `recon_residual_K{old}` marked stale, `recon_residual_K{new}` rebuilt.
- **Resumability**: simulate kill-9 mid-`llm_surprise`, verify restart processes only missing drawers, total stays at 1000.
- **Cost cap**: run `llm_surprise` against mock with `--max-cost 0.01`, verify aborts before completing.
- **Atomic-write contract**: write partial Parquets, verify merge produces master with no duplicates, no corruption on partial-write interruption.
- **End-to-end smoke**: pipeline runs on 100-drawer fixture in <30s. Asserts file existence + numerical sentinels.

### Tier 4 — Reproducibility verification

Paper's central claim is reproducibility — verify it.

- **Cross-machine re-run**: in CI, run full LongMemEval-only pipeline (palace is local, can't CI). On fixed Castle commit + fixed LME release + fixed seeds: assert fitted decay parameters match `paper/results.yaml` within ±1e-6.
- **`results.yaml` is checked in**: every paper number appears here. Updates are PR-reviewed. CI compares freshly-fitted numbers to committed YAML, fails on divergence.
- **Appendix tables auto-generated**: `analysis/figures.py --tables` reads `results.yaml` and emits LaTeX `.tex` files in `paper/appendix/`. Single source of truth — paper tables and `results.yaml` cannot drift.
- **Seed file is checked in**: any seed change → new run → new `results.yaml`.

### CI shape

- **On every commit**: Tier 1 unit tests (full), Tier 3 integration tests (subset), Tier 4 LME reproducibility on 1000-drawer subsample (fast).
- **Nightly**: full Tier 2 synthetic sweep, Tier 3 full suite, full LME reproducibility.
- **Pre-paper-release**: Tier 4 full run on both corpora end-to-end. Manual gate before submitting.

New workflow: `.github/workflows/research-info-theory.yml` — same Python matrix as Castle, HF cache warm-up for bge-m3, skips palace tests (local-only).

### What we explicitly DON'T test

- **Real Anthropic API calls in CI**: too expensive, non-deterministic. C stage mocked everywhere except manual pre-release.
- **Real palace data in CI**: palace is local-private. Palace tests run locally before push; reproducibility on palace gated manually pre-release.
- **bge-m3 numerical reproducibility across hardware**: ε-level GPU/CPU differences expected. Pin HF revision; reviewers should match within 1e-3 (looser than LME-on-CI 1e-6).
- **PyPI release tests**: not shipping to PyPI.

### Coverage expectation

Meaningful metric isn't line coverage — it's **assertion coverage of numerical results**. Every paper number has a test asserting its value. Expected line coverage 60-75% (lower than Castle's 85%); paper-number coverage 100%.

## Paper structure, scope, success criteria

### Paper structure

| Section | Length | Notes |
|---|---|---|
| Abstract | 250 words | Lead with testable claim + result |
| 1. Introduction | 1 page | Frames hypothesis; cites MemPalace + Castle as data source |
| 2. Related work | 1 page | mem0, Zep, Letta, MemPalace, MemGPT, LongMemEval, info theory (Shannon, MDL) |
| 3. Methods | 3 pages | Estimators A/B/C, corpora + stratification asymmetry, statistical procedure |
| 4. Results | 3-4 pages | Per-stratum fits, model selection, A/B/C correlations, small-multiples headline figure |
| 5. Discussion | 1.5 pages | Saturation implications for AI memory design; verbatim-vs-lossy reframed |
| 6. Limitations | 0.5 page | bge-m3 dependency, LME asymmetry, LLM-rating-not-log-prob, palace heterogeneity, single-user corpus |
| 7. Conclusion | 0.5 page | What's next; Phase 2 pointer |
| Appendix | 3-4 pages | K-sensitivity, block-size sensitivity, per-stratum tables (auto-generated from `results.yaml`), prompt template, raw-text vs normalized |

Total: 9-10 pages main + appendix.

### Paper LaTeX location

`research/info_theory/paper/main.tex`. Same directory as the code, alongside `results.yaml`. Future-portable: if the paper repo splits later, the whole `paper/` subdirectory moves together.

### Venue strategy

1. **arXiv preprint** — primary distribution. Required for ship.
2. **Workshop submission** — encouraged but not required:
   - NeurIPS workshop on Memory in Foundation Models (Oct/Nov)
   - ICLR Mathematical and Empirical Understanding of Foundation Models (March)
   - COLM workshops (summer)
3. **Blog post + Twitter/X** — same-week as arXiv, for non-academic audience.

Not targeting main conferences (NeurIPS/ICLR/ACL main track) for this paper. Workshop + arXiv is the right ambition.

### Timeline estimate

| Phase | Duration |
|---|---|
| Implementation | **3 weeks** |
| First experimental run + debugging | **1 week** |
| C-stage subsample run | **1-2 days wall-clock** (7-12 hr compute, may need 1-2 reruns for prompt iteration) |
| Analysis + figures | **1 week** |
| Paper drafting | **3 weeks** |
| **Total** | **8-10 weeks** part-time |

### In scope (Phase 1)

- Estimators A, B, C per [Estimator architecture](#estimator-architecture)
- Palace + LongMemEval corpora per [Corpora](#corpora)
- Statistical procedure per [Hypothesis structure](#hypothesis-structure)
- Code in `research/info_theory/` per [Data flow](#data-flow-and-code-organization)
- Testing tiers per [Testing](#testing-and-reproducibility)
- arXiv preprint + (optional) workshop submission + blog post + open-source code

### Out of scope (deferred to Phase 2 or future work)

- `castle entropy` CLI subcommand
- Info-aware mining (`castle mine --skip-low-info`)
- Saturation-aware search ranking (`info_score × relevance`)
- True log-prob extraction for C (requires open-weights model + teacher-forcing)
- AAAK rate-distortion analysis (sequel paper)
- Multi-user federated saturation analysis
- Real-time saturation tracking
- Conversation-time vs palace-time ordering (paper footnote)
- Synthetic-palace generator (future benchmark contribution)
- Any Castle production integration

### Success criteria

Phase 1 **ships** when:

- [ ] Paper draft on arXiv
- [ ] Code in `research/info_theory/` on `develop`
- [ ] `paper/results.yaml` committed; CI passes on LongMemEval
- [ ] At least 3 strata × 2 corpora produce decay fits (headline claim has data)
- [ ] Spearman correlations `(A, C)` and `(B, C)` reported with bootstrap CIs (even if low — low correlations are publishable)

Workshop submission is encouraged but **not required for ship**.

Authorship policy for Claude is **decided at submission time based on the target venue's policy**.

Phase 1 is **complete-but-pivoted** if:

- **No saturation detected**: paper publishes "verbatim AI conversation memory does NOT saturate in studied corpora" — negative result still publishable, weakens downstream payoff but doesn't kill the paper.
- **C uncorrelated with A/B**: paper publishes "embedding-based information proxies are insufficient" — also publishable, motivates the future-work AAAK Pareto study.

Phase 1 **fails** (rethink required) if:

- C-stage technical failure (API rate limit, prompt degradation, costs blow past $200 even with `--max-cost`)
- bge-m3 turns out to be uninformative for chat-text, invalidating A and B
- Either corpus supports stratification beyond ≤2 fittable strata (insufficient data)

### Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Cost overrun on C | Medium | `--max-cost 200` hard cap; n=200 dry-run before n=1000 |
| LME asymmetry attacked by reviewers | High | Methods + Limitations honest; counter-frame as informative |
| Palace + LME show different decays | Medium | Report both, don't force unified narrative |
| Block size choice attacked | Low | Sensitivity at 50/100/200 in appendix; cite block-bootstrap lit |
| Single-user palace ungeneralizable | High | Limitations acknowledges; future-work points at multi-user replication |
| bge-m3 underestimates code-heavy drawers | Medium | Raw-text sensitivity in appendix |
| Palace grows during experiment | High | Snapshot at start; all stages read from snapshot |
| `longmemeval_bench.py` not importable | Medium | Spec acknowledges minor refactor likely required |

## Open questions for spec review

1. **Anthropic API key procurement**: spec assumes a dedicated `ANTHROPIC_API_KEY` will be available. Confirm? (Cost cap $200 covers Phase 1 budget.)
2. **bge-m3 hardware**: experiment assumes CUDA GPU available for embedding 65k drawers. CPU-only path adds ~2-4 hours but is feasible.
3. **arXiv category**: `cs.IR` (information retrieval) + `cs.AI` (artificial intelligence) seems right; alternatives `cs.LG` (learning), `stat.ML`. Decision deferred to submission time.

---

End of design spec.
