# H3 feasibility spike — notes

**Date:** 2026-05-16
**Branch:** `feat/info-theory-impl`
**Scope:** Task 0 of the info-saturation implementation plan. Determine whether
`benchmarks/longmemeval_bench.py` can be parameterized to drop a subset of
drawers from the corpus before retrieval, so we can measure R@5 under an
info-weighted corpus (H3) without major refactoring.

## What worked / what didn't

### Harness anatomy

- **Entry point:** CLI under `if __name__ == "__main__"` (lines 3266-3442), but
  the actual benchmark loop lives in the importable `run_benchmark(...)`
  function (line 2936). Individual retrieval modes are exposed as plain
  module-level functions (`build_palace_and_retrieve`, `..._aaak`, `..._rooms`,
  `..._hybrid`, `..._hybrid_v[2,3,4]`, `..._palace`, `..._diary`, `..._full`).
  All of them are importable without invoking the CLI.
- **Corpus-ingestion path:** corpus is built **per question, in memory** inside
  each `build_palace_and_retrieve_*` function from three parallel arrays on the
  question entry: `entry["haystack_sessions"]`, `entry["haystack_session_ids"]`,
  `entry["haystack_dates"]`. The retrieval index (ChromaDB `EphemeralClient`
  collection) is **recreated fresh per question** via `_fresh_collection()`
  (line 146) — `delete_collection` + `create_collection`, then `collection.add`
  with the current question's haystack content.
- **R@5 measurement path:** `evaluate_retrieval(rankings, correct_ids,
  corpus_ids, k)` at line 71. `rankings` is a list of indices into the
  per-question `corpus_ids` array; `correct_ids` is `entry["answer_session_ids"]`
  for session granularity (or all turn IDs whose session part is an answer
  session for turn granularity). `recall_any@5` is the metric we need.

### The corpus-filter seam — clean and trivial

Because the corpus is rebuilt per question from the entry's three haystack
arrays and the index is ephemeral, **filtering = trimming those arrays in
lockstep before the entry is passed into a `build_palace_and_retrieve_*`
function.** There is no persistent index to invalidate, no rebuild step, no
"reingest" semantics to figure out. Concretely:

```python
def apply_drop_filter(entry: dict, drop_ids: set) -> dict:
    sessions, sids, dates = [], [], []
    for s, sid, d in zip(entry["haystack_sessions"],
                          entry["haystack_session_ids"],
                          entry["haystack_dates"]):
        if sid in drop_ids:
            continue
        sessions.append(s); sids.append(sid); dates.append(d)
    out = dict(entry)
    out["haystack_sessions"] = sessions
    out["haystack_session_ids"] = sids
    out["haystack_dates"] = dates
    return out
```

That's the entire mechanism. For H3 we wrap this around the existing
`run_benchmark` data-loading step (line 2960-2976), iterating over entries and
applying `apply_drop_filter` against an info-weighted drop-set computed offline
from `recon_residual` percentiles.

### Spike script behavior (synthetic corpus, no LME data download)

`~/scratch/h3_spike.py` (not committed, throwaway) constructs an LME-shaped
entry with 50 sessions: session 0 contains the gold token "mango"; the other 49
are random distractor topics. It then:

1. Runs `build_palace_and_retrieve` on the uniform corpus → **R@5 = 1.000**
   (top-1 is `sess_000`).
2. Drops a random 10% of non-gold sessions (5 sessions), runs again →
   **R@5 = 1.000** (gold still top-1).
3. Sanity check: drops the gold session → **R@5 = 0.000** (confirms the
   filtered IDs really are absent from the rebuilt index).
4. Reports the delta (+0.000 — not meaningful with a single trivial entry; the
   purpose of the spike is mechanism validation, not effect-size estimation).

All three runs completed in well under a second on ChromaDB's default
embedding model. No errors. The arity assertion and gold-killed assertion both
hold.

### LME data availability

The real `longmemeval_s_cleaned.json` is **not present** on this machine. The
README at `benchmarks/README.md:19-21` documents the download path:

```bash
mkdir -p /tmp/longmemeval-data
curl -fsSL -o /tmp/longmemeval-data/longmemeval_s_cleaned.json \
  https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json
```

There is also a pre-existing stable split file at
`benchmarks/lme_split_50_450.json` (50 dev / 450 held-out, seed=42), which
H3 should reuse so its R@5 numbers compare apples-to-apples with the rest of
the benchmark suite.

The spike validates the **filter mechanism** without LME data; the actual H3
experiment needs the download as part of its setup (Task 17).

### What didn't work / nothing actually blocking

Nothing was blocking. The only minor friction:

- The harness imports `chromadb` at top-level (line 42) and creates an
  `EphemeralClient` at module import (line 97). This makes the import slightly
  slow (~2-3s on a cold start) but does not interfere with `apply_drop_filter`.
- The module-level `_bench_embed_fn` global needs to be set before benchmark
  runs if a non-default embedder is desired (line 99-101, 3418-3423). H3 should
  use a deterministic embedder choice (e.g., `bge-large` for consistency with
  the rest of the info-theory experiments) and set it identically across the
  uniform-vs-filtered comparison so the only varying factor is the corpus
  subset. This is a configuration concern, not a refactor concern.

## Estimated refactoring effort if needed (in days)

**Zero days** to the harness itself for H3's core mechanical need.

The mechanism is a ~15-line `apply_drop_filter(entry, drop_ids) -> entry`
helper called by an H3-specific runner (Task 17) that wraps the existing
`run_benchmark` data-load. That runner is part of the info-theory package
(Task 17), **not** a modification to `benchmarks/longmemeval_bench.py`.

If we later want a first-class `--drop-ids-file` CLI flag on the harness
(nice-to-have for reproducibility, not required for H3 numbers), that is a
~0.5 day diff: one argparse argument, one `set` load, one extra line inside
the `run_benchmark` per-entry loop applying the filter. That work is
deferred to Task 4 ("formal `load_longmemeval` implementation") per plan,
or simply skipped if the H3 runner does its own data loading.

LME data download + first-time embedder warmup is a ~30 min one-shot
operational task, not refactoring.

## Decision: **H3 IN** for Phase 1

The corpus-filter seam exists today, is trivial to use, and does not require
any change to `benchmarks/longmemeval_bench.py`. The cost of including H3 in
Phase 1 is bounded by Task 17's own complexity (drop-percentile sweep, R@5
non-inferiority margin computation, plotting), not by harness-refactoring
risk.

## Recommended next step

For **Task 17 (H3 downstream R@5 evaluation)**:

1. **Setup:** download `longmemeval_s_cleaned.json` to a stable location
   (suggest `data/longmemeval/longmemeval_s_cleaned.json` under the repo, or
   reuse the README's `/tmp/longmemeval-data/` path with a `--data` flag).
   Reuse `benchmarks/lme_split_50_450.json` for the held-out subset.
2. **Drop-set construction:** offline, compute `recon_residual` for every
   drawer in the snapshot palace (output of Tasks 8-11). Sort ascending.
   For each `X ∈ {5, 10, 15, 20, 25}` percent, build a `drop_ids: set[str]`
   of session-IDs (or turn-IDs at `--granularity turn`) keyed to LME's
   `haystack_session_ids` namespace.
3. **Runner:** copy the 15-line `apply_drop_filter` from this spike into
   `research/info_theory/h3_runner.py` (Task 17). For each X, iterate the
   held-out 450 entries, apply `apply_drop_filter`, call
   `lme.build_palace_and_retrieve(entry_filtered, granularity="session")`,
   compute R@5 via `lme.evaluate_retrieval(...)`, and aggregate.
4. **Non-inferiority test:** bootstrap CI on the per-question R@5 delta
   between uniform corpus and each X. H3 confirmed if the lower bound of
   the CI on the delta exceeds the pre-registered non-inferiority margin
   (paper says `δ = -0.02`).
5. **Mapping concern to flag in Task 17 design:** `recon_residual` is keyed
   by **drawer-ID** (Castle namespace); LME's drop-set is keyed by
   **session-ID** (LME namespace). The H3 runner needs a bridge step that
   maps Castle drawer-IDs through the ingest provenance (Task 5 normalize
   step) to LME session-IDs before constructing `drop_ids`. If the snapshot
   palace was not ingested from LME haystacks, H3 cannot run on LME at all
   and a per-paper-corpus snapshot is required — flag this dependency
   explicitly in Task 17's spec.

If H3 had been OUT (it isn't), the Discussion future-work text would have
been: "Downstream utility on LongMemEval is deferred because the benchmark
harness's per-question corpus rebuild does not expose a stable drawer-level
filter; future work should refactor the haystack loader to accept an
externally-supplied drop-set keyed to Castle drawer-IDs." That paragraph is
**not needed** — H3 IN.
