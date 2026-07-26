# Info-Aware Filing — Design

**Date:** 2026-07-26
**Status:** Approved (user-reviewed brainstorm, Section 1 amended after critical-flaw review)
**Derived from:** v3.4.0/v3.4.1 info-theory research (`research/info_theory/`,
paper in `research/info_theory/paper/`). Key inputs: ρ(nn_novelty,
LLE_residual) = 0.982 on the full 65,779-drawer palace validates the cheap
estimator as an information-content proxy; a live `prune-suggest` run found
41/50 sampled drawers with novelty < 0.10 (near-duplicates at cosine > 0.97).
This design is the "smart mining Phase 2" the paper's Discussion promises.

## Goal

The palace learns what's worth remembering **without forgetting anything**.
Every drawer is still stored verbatim (design principle: verbatim always,
never destroy). New: each drawer carries a `novelty` metadata score, and
retrieval can *demote* (never drop) low-novelty near-duplicates so the top-K
surfaces distinct content instead of the 47th copy of the same JSON envelope.

Three user-visible surfaces:

1. `castle search --info-weight` (and `info_weight_enabled` config) — opt-in
   retrieval demotion.
2. `castle status` — per-wing information-health line (median novelty +
   coverage %).
3. `castle repair --backfill-novelty` — one-time (resumable) backfill of the
   existing 65k drawers.

## Locked decisions (from brainstorm)

| Decision | Choice | Rationale |
|---|---|---|
| Backfill existing drawers? | **Yes, once** — resumable pass, ~20–45 min (vectors exist, no re-embedding) | Demotion must work on the measured 82%-near-duplicate mass immediately |
| Compute path for new drawers | **Always inline** (amended from "Hybrid" during spec self-review) — every mine path computes novelty at filing time | Fact-check during spec review: hooks spawn `castle mine` as a *detached background subprocess* (`hooks_cli._spawn_mine`), so mining latency never counts against the <500ms hook budget. The hybrid's agent-string gate was also unimplementable — hook mining reaches `_build_drawer_metadata` via the same CLI path (`added_by: "cognitive-castle"` uniformly in the live palace). Always-inline is simpler and closes the coverage gap. |
| Rollout | **Opt-in + benchmark gate** — default OFF until LongMemEval R@5 with demotion ≥ baseline | "100% recall is the design requirement"; flip the default on evidence, not on the MMR argument |
| Pipeline placement | **Fusion stage (Stage 2)**, after `apply_recency`, before the top-K cut | Demotion before the cut creates diversity (frees top-K slots); after the cut it only reshuffles |

## Critical invariant: prior-only novelty

nn_novelty is defined **prior-only** (research-faithful): a drawer is scored
against drawers filed *before* it (`filed_at < target.filed_at`). This gives
duplicate pairs an asymmetry — first-filed twin keeps high novelty, later
twin gets low — so demotion buries at most one of the pair and the content
always survives ranking.

A naive backfill against the *current* palace would find the later twin when
scoring the earlier one, give **both** low novelty, demote both, and bury the
content entirely — a real recall regression. Therefore:

> `compute_novelty` over-fetches top-10 same-wing neighbours, parses
> `metadata_json` client-side, drops self-ID and any neighbour with
> `filed_at ≥ target.filed_at`, then takes `1 − max_cosine` over what
> remains. No prior neighbours → novelty = 1.0 (first-drawer convention,
> same as the research).

Client-side filtering is required because `filed_at` lives inside
`metadata_json`, not a hoisted LanceDB column, so it is not
where-clause-filterable.

## Components

### 1. `cognitive_castle/novelty_tagger.py` (new, ~100 lines)

- `compute_novelty(vector, collection, wing, filed_at, self_id=None) -> float`
  — one top-10 vector search, client-side prior-only + self-exclusion filter,
  `1 − max_cosine`. Takes a pre-computed vector; never embeds.
- `backfill_novelty(collection, batch_size=500, only_missing=True) -> dict`
  — walks drawers missing the `novelty` metadata key, computes, batches
  metadata updates. Resumable by construction (key-absence = todo). Returns
  `{tagged, skipped, failed}` stats.
- `info_score.score_novelty` (existing CLI/MCP surface) is refactored to
  delegate its scoring core to this module — one implementation of the math.

### 2. Mine-time tagging (`miner.py`)

- `_build_drawer_metadata` gains an optional `novelty` field.
- Batched-upsert path: after embeddings are computed, each chunk gets
  `compute_novelty(...)` before upsert — **every mine path**, interactive
  and hook-spawned alike (hook mining runs in a detached background
  subprocess, so the <500ms hook budget is unaffected; see Locked
  decisions).
- On any compute failure: warn once to stderr, file the drawer **without**
  the key (key-absence, not `null`). Backfill targets key-absence, so
  failure gaps self-heal on the next `castle repair --backfill-novelty`.
- Mining never fails because of novelty.

### 3. Retrieval demotion (`fusion.py`, `searcher.py`)

- `CandidateRef` gains `novelty: float | None = None`.
- New pure function in `fusion.py`:

  ```python
  def apply_info_weight(scored, threshold: float, min_factor: float): ...
  # factor = 1.0                                  if novelty is None
  # factor = 1.0                                  if novelty >= threshold
  # factor = min_factor + (1 - min_factor) * (novelty / threshold)  otherwise
  ```

  Re-sorts descending, ties broken by drawer_id — the exact contract of
  `apply_recency`. `None` (untagged) is **never** punished.
- `searcher.py`'s `_to_refs` extracts novelty from each recall row's
  `metadata_json` (rows already in hand; zero extra I/O). Malformed values
  (non-numeric, negative) → `None` → factor 1.0. Demotion can only be a
  no-op on bad data, never an amplifier.
- Gate: `cfg.info_weight_enabled` (default **False**) OR the per-query
  `castle search --info-weight` CLI flag.
- **Plan-time verification required:** all three recall paths (dense, FTS,
  KG-hop via `get_by_ids`) must return rows carrying `metadata_json`.
  Believed true; verify before writing `_to_refs` extraction.

### 4. Surfacing (`cli.py`)

- `castle status`: one line per wing, **read from stored metadata only**
  (bounded deterministic sample — first 500 rows per wing in stable scan
  order; zero vector searches):
  `median novelty 0.07 · 61% below 0.10 · coverage 84%`
  Coverage = fraction of sampled drawers that have the key at all; without
  it a median over partial coverage would mislead.
- `castle repair --backfill-novelty` runs `backfill_novelty` with a progress
  line per batch; Ctrl-C-safe.
- `castle search --info-weight` forces demotion on for that query.

### 5. Benchmark gate (manual step, documented deliverable)

Run `benchmarks/longmemeval_bench.py` R@5: baseline vs `--info-weight`.
Record both numbers in this spec (below) before any default flip. The
default changes to ON only if R@5 with demotion ≥ baseline.

**Results (to be filled after implementation):**

| Config | R@5 |
|---|---|
| Baseline (info_weight_enabled=False) | _pending_ |
| Demotion ON (threshold 0.10, min_factor 0.5) | _pending_ |

## Config knobs (`config.py`, file + env, same pattern as recency)

| Key | Default | Env |
|---|---|---|
| `info_weight_enabled` | `False` | `CASTLE_INFO_WEIGHT_ENABLED` |
| `info_weight_threshold` | `0.10` | `CASTLE_INFO_WEIGHT_THRESHOLD` |
| `info_weight_min_factor` | `0.5` | `CASTLE_INFO_WEIGHT_MIN_FACTOR` |

Threshold 0.10 = the "low" band from the research's empirical palace
distribution. `min_factor` bounds worst-case demotion at 2× score reduction.

## Non-interactions (explicit)

- **`decay_score`**: existing metadata field read by `_hybrid_rank`.
  Info-weight is an independent multiplicative factor at a different
  pipeline stage. No interaction, no shared config.
- **SOAR boosts (Stage 5)**: run after the rerank; info-weight runs before
  the top-K cut. Multiplicatively independent; audit fields unaffected.
- **Verbatim storage**: no write path in this design deletes or rewrites
  drawer *content*, ever. Only the `novelty` metadata key is added.

## Error handling summary

| Failure | Behaviour |
|---|---|
| compute_novelty raises at mine-time | warn once, file drawer without key |
| Backfill per-drawer error | log + skip, count in `failed`, continue |
| Malformed novelty at search time | treat as None → factor 1.0 |
| Empty wing / no prior neighbours | novelty = 1.0 |
| Both config gate and CLI flag off | pipeline byte-identical to today |

## Testing (~20 tests)

- `tests/test_novelty_tagger.py` (new): prior-only twin-pair asymmetry (the
  critical invariant — A early / B late → A high, B low), self-exclusion on
  re-mine, first-drawer 1.0, malformed-metadata skip, backfill resumability
  (key-absence idempotence), batched update correctness, stats dict shape.
- `tests/test_fusion.py` (extend): `apply_info_weight` — None passthrough,
  ≥ threshold passthrough, floor at min_factor for novelty→0, linear ramp
  midpoint (novelty = threshold/2 → factor = (1+min_factor)/2), re-sort +
  deterministic tie-break, threshold=0 edge (no division blowup).
- `tests/test_miner.py` (extend): mine writes `novelty` on every path;
  compute-failure path files the drawer without the key (and does not
  raise).
- `tests/test_searcher.py` (extend): `_to_refs` novelty extraction from
  metadata_json; disabled-gate regression guard (pipeline output identical
  to pre-feature behaviour when off).
- `tests/test_cli.py` (extend): status renders median + below-threshold % +
  coverage; `--info-weight` flag threads to the searcher.

## Out of scope (YAGNI)

- Two-axis (A × C) scoring — separate future design.
- Per-wing adaptive recency from decay constants — separate future design.
- Automatic default-ON flip — human decision after the benchmark gate.
- Prune/delete of any drawer — never in this design.
