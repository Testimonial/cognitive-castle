# Stage 6 — Deterministic Quality Rerank — Design Spec

**Date:** 2026-05-14
**Status:** Approved, ready for implementation plan
**Scope:** Add an optional Stage 6 to Castle's retrieval pipeline that re-ranks Stage 3+ candidates using the 31 deterministic, peer-reviewed-paper-grounded text-quality metrics from the user's `understanding` package (v3.7.0, MIT, part of `~/echelon/`). Two-tier threshold-and-boost rule, mirrors SOAR's auditable boolean idiom. Opt-in via `--quality-rerank` flag and `CASTLE_QUALITY_ENABLED=1` kill-switch.

## Background

This session shipped the KG enrichment work (PR #37) and the zero-failures cleanup (PRs #38-43). With the test baseline now at 0 failed, the next question is: what's the next signal to add to retrieval?

Castle's pipeline:

```
Stage 1: dense + Tantivy FTS + KG-hop (parallel recall)
Stage 2: weighted RRF + recency multiplier → top-K
Stage 3: cross-encoder rerank → top-N
Stage 4 (optional): LLM-as-judge re-rank
Stage 5 (optional): SOAR symbolic boost-tags (4 productions)
```

The user maintains a separate project (`~/echelon/`) whose `understanding` submodule implements **31 deterministic text-quality metrics** across **6 categories**: 6 readability metrics, 5 structure metrics, 7 cognitive metrics, 6 semantic metrics, 3 testability metrics, 4 behavioral metrics (6+5+7+6+3+4 = 31). Citations: ISO 29148 (requirements engineering), Lucassen 2017 (user-story quality), Sweller 1988 (cognitive load), Flesch 1948 (readability). The `depth_metrics.py` file in the package exists but isn't part of the public-API metric count per the package's own docstring.

The metrics package was designed for software-requirements documents. **Calibration on Castle's actual chat-drawer data showed the metrics DO discriminate** (see Calibration Evidence below), so a Stage 6 quality rerank is viable.

This Stage 6 mirrors Castle's existing optional-stage pattern (`--llm-rerank` for Stage 4, `--soar-boost` for Stage 5):
- Opt-in via CLI flag + kill-switch env var
- Lazy-imports the heavy dependency (preserves "no overhead by default")
- Adds audit-trail fields to each hit
- Composable with Stages 4 and 5

## Calibration evidence

Before this design was finalized, a 100-drawer random sample from the user's 55,710-drawer palace at `~/.castle/palace` was passed through `understanding.analyze_with_enhanced_metrics`. Results:

```
n=100 (random sample, seed=42)
errors=0
latency=38ms/drawer avg (~760ms per 20-candidate query — matches budget)

Score distribution (overall_weighted_average):
  min=0.194  max=0.756
  mean=0.469  stdev=0.113
  p10=0.330  p25=0.386  p50=0.472  p75=0.534  p90=0.597

Histogram:
  [0.0-0.1)    0
  [0.1-0.2)    4
  [0.2-0.3)    5
  [0.3-0.4)   13
  [0.4-0.5)   38
  [0.5-0.6)   31
  [0.6-0.7)    7
  [0.7-0.8)    2
  [0.8-0.9)    0
  [0.9-1.0)    0
```

The distribution discriminates on chat-data (stdev 0.113, range 0.194-0.756, no collapse to a narrow band) despite the metrics being designed for requirements documents. **This empirical evidence justifies a two-tier threshold-and-boost rule with thresholds calibrated to this distribution's p75 and p90.**

If the user's palace changes shape materially, the calibration script (`scripts/calibrate_quality_threshold.py`, committed as part of this work) should be re-run.

## Goals

- Add Stage 6 (deterministic quality rerank) as an optional final pass after Stages 4 and 5
- Two-tier threshold-and-boost: `score >= 0.60 → ×1.25 boost ("high")`, `0.53 <= score < 0.60 → ×1.15 boost ("medium")`, otherwise no boost
- Per-hit audit trail: `quality_score`, `quality_tier`, `quality_boost`, `score_pre_quality` fields always present
- CLI audit line: `QUALITY: high (×1.250, score=0.78)` printed only when boost fires
- Composable with Stages 4 (LLM-judge) and 5 (SOAR), default execution order judge → SOAR → quality
- Local-only (regex + spaCy + transformers + torch; no LLM call, no network)
- Append-only audit (never modifies prior-stage outputs)
- Graceful degradation if the vendored package or its model loads fail

## Non-goals

- **No `--quality-first` reordering flag** — quality always runs last in the chain. If users want a different order, that's a follow-up
- **No closet QA application** (Option 3 from brainstorming) — only post-retrieval rerank in this PR
- **No per-drawer index-time annotation** (Option 2 from brainstorming) — only query-time scoring
- **No threshold auto-calibration** — calibration is a one-time investigation; thresholds are tunable knobs in config but don't auto-update
- **No multi-language support** — `understanding` is English-only via spaCy `en_core_web_sm`. Non-English drawers may score low; this is acknowledged, not addressed in this PR
- **No surfacing of individual metric categories** — only the aggregate `overall_weighted_average` is consumed. The 6-category breakdown is internal to `understanding`

## Architecture & data flow

```
Stage 3 (cross-encoder rerank)
  │
  ├── opt [4] LLM-as-judge       --llm-rerank
  ├── opt [5] SOAR boost-tags    --soar-boost + CASTLE_SOAR_ENABLED=1
  └── opt [6] Quality rerank     --quality-rerank + CASTLE_QUALITY_ENABLED=1
       │
       │  Default execution order: 4 → 5 → 6 (each optional, each composable)
       │
       ├── For each candidate (after Stage 5, if Stage 5 ran):
       │     score = understanding.analyze_with_enhanced_metrics(text)
       │             ["enhanced_metrics"]["overall_weighted_average"]
       │
       ├── Three-state tier classification:
       │     if score >= cfg.quality_threshold_high (0.60):
       │         tier = "high",   multiplier = cfg.quality_boost_high (1.25)
       │     elif score >= cfg.quality_threshold_medium (0.53):
       │         tier = "medium", multiplier = cfg.quality_boost_medium (1.15)
       │     else:
       │         tier = None,     multiplier = 1.0
       │
       └── Mutate hit dict:
              hit["quality_score"]      = score   (float, always set when Stage 6 ran)
              hit["quality_tier"]       = tier    ("high" | "medium" | None)
              hit["quality_boost"]      = multiplier
              hit["score_pre_quality"]  = hit["score"]
              hit["score"]              = hit["score"] * multiplier
       │
       └── Sort result by new hit["score"] descending
```

### Invariants

- **Append-only audit** — never modifies prior-stage outputs; only adds `quality_*` fields to hit dict
- **Deterministic** — same input → same output (no RNG, no concurrent state, threshold defaults from a fixed calibration moment)
- **Local-only** — spaCy + transformers + torch are local; no LLM call, no network
- **Composable** — runs after Stages 4 and 5 by default; multipliers compound multiplicatively
- **Idempotent display** — printing the audit line is a function of hit fields, not pipeline state
- **Graceful degradation** — if `understanding` import fails or per-hit calls raise, the affected hits get default fields (`quality_score=None, quality_tier=None, quality_boost=1.0, score_pre_quality=score`), warning logged once

### Audit line format

```
QUALITY: high (×1.250, score=0.78)        ← score >= 0.60, line shown
QUALITY: medium (×1.150, score=0.56)      ← 0.53 <= score < 0.60, line shown
                                            ← score < 0.53: NO line (suppressed)
QUALITY: FAILED (RuntimeError: ...)       ← module-level failure, ONCE per process
```

Below-threshold hits have all four `quality_*` fields populated programmatically; only the console audit line is suppressed (matches SOAR's idiom for "no tags fired").

### Performance estimate

| Mode | First query | Subsequent queries |
|---|---|---|
| **CLI** (`castle search --quality-rerank ...`) | 25-90ms × ~20 candidates + **+381ms one-time spaCy load** = ~0.9-2.2s | Same (each CLI invocation is a fresh process, so spaCy reloads) |
| **MCP** (long-running `castle-mcp` server) | First query: +381ms spaCy load. Subsequent: pure rerank cost | 0.5-1.8s |

Latency range bounded by the calibration measurement: **38ms/drawer mean** on the user's 100-drawer random sample (range observed 25-90ms across drawer text-length distribution). For CLI-heavy users the cold-load tax is repeated. For MCP-mode (the user's primary consumption path via Claude Code), it's one-time per server process.

## Component changes / file map

### NEW files

| File | Purpose |
|---|---|
| `cognitive_castle/understanding/` (directory, 12 .py files) | Vendored copy of `~/echelon/src/understanding/`. MIT, same author. Files (verified by `ls`): `__init__.py`, `cli.py`, `behavioral_metrics.py`, `constraint_metrics.py`, `depth_metrics.py`, `energy_metrics.py`, `enhanced_metrics.py`, `entity_metrics.py`, `markdown_parser.py`, `normalized_metrics.py`, `requirements_metrics.py`, `semantic_metrics.py`. Metric categories from the package docstring (readability, structure, cognitive, testability) are implemented WITHIN these files, not as separate modules. Top-level `__getattr__` lazy-loader preserved. NO modifications to the vendored code. Provenance recorded as a docstring header in `__init__.py` (source: `~/echelon/src/understanding/` v3.7.0 on 2026-05-14) |
| `cognitive_castle/quality_rerank.py` | Public entry `apply_quality_rerank(reranked: list[tuple[float, dict]], cfg) -> list[tuple[float, dict]]`. Implements the three-state threshold rule. Lazy-imports `cognitive_castle.understanding` so it's only loaded when Stage 6 fires |
| `tests/test_quality_rerank.py` | Stage 6 unit + integration + audit-trail tests. Mirrors `test_soar_bridge.py` fixture pattern |
| `scripts/calibrate_quality_threshold.py` | One-shot CLI tool: random-sample drawers from a palace, run `analyze_with_enhanced_metrics`, print distribution stats + histogram. Not a test; reproducibility helper. Users re-run after material palace changes |

### MODIFIED files

| File | Change |
|---|---|
| `pyproject.toml` | Add `spacy>=3.0.0` (NEW). Add `transformers>=4.30.0` explicitly (NOT relying on `sentence-transformers` transitive — pinning avoids silent breakage if sentence-transformers ever changes its transformers range). Add `en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl` (same wheel URL echelon uses, ~12MB) |
| `cognitive_castle/config.py` | Five new properties, each env→file→default with try-except (Castle's standard pattern post-Task 1 of zero-failures cleanup): `quality_enabled` (env `CASTLE_QUALITY_ENABLED`, default `False`), `quality_threshold_medium` (env `CASTLE_QUALITY_THRESHOLD_MEDIUM`, default `0.53`), `quality_threshold_high` (env `CASTLE_QUALITY_THRESHOLD_HIGH`, default `0.60`), `quality_boost_medium` (env `CASTLE_QUALITY_BOOST_MEDIUM`, default `1.15`), `quality_boost_high` (env `CASTLE_QUALITY_BOOST_HIGH`, default `1.25`) |
| `cognitive_castle/searcher.py` | (a) Add `_stage_6_quality(reranked, cfg)` lazy-wrapper that imports `cognitive_castle.quality_rerank` only when invoked. (b) **Rename `_apply_stages_4_and_5` → `_apply_optional_stages`** (forward-compatible for future stages). Update all callers in this file. Also update all references in `tests/test_pipeline_order.py` in the same PR (mechanical, no semantic change). (c) Thread `quality_rerank: bool = False` through `_new_pipeline_search` and `search_memories` signatures. (d) Per-hit return dict gains `quality_score: float \| None`, `quality_tier: str \| None`, `quality_boost: float = 1.0`, `score_pre_quality: float = score`. (e) Extend `_print_search_results` to render `QUALITY:` line ONLY when `hit["quality_tier"] is not None` |
| `cognitive_castle/cli.py` | Add `--quality-rerank` flag with kill-switch validation (`if args.quality_rerank and not cfg.quality_enabled: print(...); sys.exit(2)`, mirroring SOAR's pattern). Thread through to `search()` |
| `cognitive_castle/mcp_server.py` | Add `quality_rerank` MCP param to `castle_search` tool + same kill-switch validation |
| `CLAUDE.md` | Update retrieval-pipeline diagram in the Architecture section: add Stage 6 line. One-sentence description: "Stage 6 (optional, opt-in `--quality-rerank` + `CASTLE_QUALITY_ENABLED=1`): deterministic text-quality rerank via vendored `understanding/` package — three-state threshold rule with calibrated defaults" |

### Vendored package verification

During implementation, verify which files in `understanding/` are actually loaded by `analyze_with_enhanced_metrics`:

```python
import sys
prior = set(sys.modules)
import understanding
understanding.analyze_with_enhanced_metrics("test fixture text")
loaded = sorted(m for m in (set(sys.modules) - prior) if m.startswith("understanding"))
print(loaded)
```

All files are vendored regardless (faithful drop-in mirror, sync-friendly), but the verified list is documented in the vendored `__init__.py` header so future changes are easier to validate.

### Import direction (avoids circularity)

```
searcher.py
  └─→ (lazy) cognitive_castle/quality_rerank.py
                └─→ (lazy) cognitive_castle.understanding
                                └─→ spacy, torch, transformers (third-party only)
```

`quality_rerank` and `understanding` import nothing from Castle's other modules.

### Failure modes

| Failure | Action | Per-hit dict fields |
|---|---|---|
| `understanding` import fails (vendored copy broken, spaCy model missing) | `_warn_once`, skip Stage 6 entirely | `quality_score=None, quality_tier=None, quality_boost=1.0, score_pre_quality=score` |
| `analyze_with_enhanced_metrics(text)` raises on specific hit | `_warn_once` per exception class, default that hit's fields | Same defaults |
| `result["enhanced_metrics"]["overall_weighted_average"]` missing/non-numeric/NaN | Per-hit skip | Same defaults |
| `KeyboardInterrupt` / `SystemExit` | Propagate | N/A |

### Concurrent-run safety

Stage 6 is pure read/transform per-process. spaCy's `nlp` model is module-local; Castle's single-process / single-threaded-asyncio architecture doesn't trigger concurrent calls into Stage 6 from one process. Multi-process safety: each process loads its own spaCy model independently.

Not threadsafe-claimed; not tested for thread safety.

## Testing strategy

### Coverage targets

- `cognitive_castle/quality_rerank.py`: ≥ 85% line coverage (Castle's threshold)
- 5 new config properties: standard 3-path coverage (default / env-override / file_config-override) = 15 tests
- CLI + MCP kill-switch validation: regression for the SOAR-pattern mirror
- `_apply_optional_stages` (renamed): existing tests adapted + new Stage 6 ordering tests

### Test file map

```
tests/test_quality_rerank.py          (NEW)
├── tier classification (pure function, no external deps)
│   ├── score >= 0.60 → tier="high"
│   ├── score == 0.60 → tier="high" (boundary inclusive)
│   ├── 0.53 <= score < 0.60 → tier="medium"
│   ├── score == 0.53 → tier="medium" (boundary inclusive)
│   ├── 0 <= score < 0.53 → tier=None
│   └── Non-default thresholds via _mock_cfg respected
│
├── apply_quality_rerank (mocked analyze_with_enhanced_metrics)
│   ├── empty input → empty output
│   ├── all hits above high → all ×1.25, all "high"
│   ├── all hits below medium → all quality_tier=None, quality_score=<float>,
│   │     quality_boost=1.0, score_pre_quality=score (full field assertion)
│   ├── mixed input → correct tier per hit
│   ├── all 4 quality_* fields present on every hit regardless of tier
│   ├── hit["score"] equals score_pre_quality × quality_boost
│   ├── output sorted by boosted score descending
│   └── deterministic: same input → same output
│
├── audit-trail surface (via _print_search_results)
│   ├── high-tier hit emits "QUALITY: high (×1.250, score=...)"
│   ├── medium-tier hit emits "QUALITY: medium (×1.150, score=...)"
│   └── below-threshold hit emits NO QUALITY line
│
├── failure modes (mocked)
│   ├── understanding import fails → _warn_once, all hits skip Stage 6
│   ├── analyze_with_enhanced_metrics raises on a hit → that hit defaults, others continue
│   ├── result missing "enhanced_metrics" key → per-hit skip
│   ├── result missing "overall_weighted_average" key → per-hit skip
│   ├── overall_weighted_average is None / NaN / negative → per-hit skip
│   └── KeyboardInterrupt propagates (not caught)
│
├── smoke (real package, @pytest.mark.slow)
│   └── test_apply_quality_rerank_smoke — uses ~370-char fixture prose,
│        asserts shape of returned fields (types and ranges, not exact values)
│
└── edge cases
    ├── empty drawer text → defensive skip, no crash
    ├── 1-char drawer text → defensive skip or score, no crash
    ├── 10KB drawer text → completes, no crash
    └── unicode/emoji-only text → metric returns a value or skips, no crash

tests/test_pipeline_order.py          (EXISTING — append + adapt)
├── (adapt existing) all tests now import _apply_optional_stages instead
│     of _apply_stages_4_and_5 — mechanical rename, no semantic change
├── test_quality_runs_when_quality_rerank_flag_set
├── test_quality_skipped_when_flag_off
├── test_default_order_judge_then_soar_then_quality
├── test_quality_alone_no_judge_no_soar
└── test_all_three_optional_stages_compound_correctly

tests/test_searcher.py                (EXISTING — append)
├── search_memories return dict has quality_* fields when quality_rerank=True
├── search_memories return dict has default quality_* fields when quality_rerank=False
├── _print_search_results renders QUALITY line for high/medium tiers
└── _print_search_results suppresses QUALITY line when quality_tier is None

tests/test_cli.py                     (EXISTING — append)
├── --quality-rerank without CASTLE_QUALITY_ENABLED=1 → exit(2)
└── --quality-rerank with CASTLE_QUALITY_ENABLED=1 → runs Stage 6

tests/test_mcp_server.py              (EXISTING — append)
├── quality_rerank=true MCP param without kill switch → exit(2)
└── quality_rerank=true with kill switch → runs Stage 6

tests/test_config.py                  (EXISTING — append)
└── 5 properties × 3 paths each = 15 tests (default / env / file_config)
```

### Test patterns

- **Mock-light**: most tests stub `analyze_with_enhanced_metrics` via `monkeypatch.setattr` with controlled scores. Avoids spaCy loads in unit tests
- **One slow smoke test** calls the real package on fixed fixture prose — catches import-graph + wiring regressions
- **Tier classification is a pure function**, tested with direct calls
- **Failure tests use `monkeypatch` + side-effect lambdas** for controlled per-call failures

### Explicit testing non-goals

1. **Performance benchmarks** — no `tests/benchmarks/` additions
2. **Multi-language behavior** — `understanding` is English-only via spaCy `en_core_web_sm`. We test "doesn't crash on unicode," not "correctly scores Portuguese"
3. **Calibration regression** — threshold defaults reflect a one-time measurement. Documented as evidence, not enforced as a recurring test
4. **Real-palace end-to-end** — covered by manual smoke during the final integration task
5. **Score drift over palace lifetime** — out of scope; threshold is configurable, not auto-tuned
6. **spaCy thread safety** — not claimed, not tested

## Risk register

1. **Vendored package's hidden dependencies** — `analyze_with_enhanced_metrics` may load files we don't list in the vendor manifest. The smoke test (real call on fixture prose) catches this if the vendor copy is incomplete
2. **`pip install` of `en-core-web-sm` wheel** — wheel URL requires network access at install time. Plan-time verification: a developer runs `pip install -e ".[dev]"` from scratch and confirms `understanding` imports cleanly. CI behavior with wheel URLs is out of this spec's scope; failure surfaces on first PR CI run
3. **Calibration may drift** — defaults reflect 2026-05-14 palace state. Plan must verify the user's palace hasn't materially changed between spec date and implementation date; if so, re-run calibration and adjust defaults
4. **Stage 6 underperforms on chat-data despite calibration showing variance** — the metrics discriminate (stdev 0.113) but it's not proven that high-scoring drawers are USEFULLY high-scoring (i.e., more relevant). Acceptable risk because: (a) Stage 6 is opt-in, (b) audit trail surfaces what's being boosted so user can inspect quality, (c) thresholds are configurable for easy adjustment
5. **CLI cold-load tax** — every CLI invocation pays +381ms for spaCy. Not a blocker (CLI usage is rare per the user's actual workflow); MCP-mode amortizes the cost
6. **`understanding` package upgrades** — vendored copy is a snapshot. Future upgrades to the upstream `echelon` package require manual sync. The `VENDORED` docstring records the source version

## Out of scope

- **Closet QA application** (Option 3 from brainstorming) — apply metrics to AAAK closets during `closet_llm` generation
- **Per-drawer index-time annotation** (Option 2 from brainstorming) — store metric scores in `metadata_json` for query-time filtering
- **`--quality-first` reordering flag** — quality always runs last in Stages 4-6
- **Surfacing individual metric categories as separate boost-tags** (richer audit) — only the aggregate is consumed
- **Auto-calibration / threshold drift detection** — manual re-run of the calibration script is the supported path
- **Multi-language scoring** — `understanding` is English-only via spaCy `en_core_web_sm`
- **CI workflow file modifications** — pyproject.toml changes are in-scope; `.github/workflows/*.yml` is not

## Acceptance criteria

- All new tests pass; existing tests (renamed `_apply_optional_stages` references) pass
- `pytest tests/ --ignore=tests/benchmarks` returns 0 failed (no regression from zero-failures baseline)
- `ruff format` + `ruff check` clean
- CLI smoke: `CUDA_VISIBLE_DEVICES="" CASTLE_QUALITY_ENABLED=1 castle search "what did we decide about the embedder" --results 5 --quality-rerank` shows `QUALITY: high (...)` or `QUALITY: medium (...)` audit lines on hits in the appropriate tiers
- MCP smoke (via Claude Code session): `quality_rerank: true` parameter routes through Stage 6
- Calibration script committed (`scripts/calibrate_quality_threshold.py`) and runs successfully against the live palace
- **Pre-merge re-calibration:** before merging, if the palace has grown materially since 2026-05-14 (rule-of-thumb: >10% new drawers), re-run the calibration script and update `quality_threshold_medium` / `quality_threshold_high` defaults in the same PR to match the new p75 / p90

## What this unlocks

- A third post-rerank signal (alongside LLM-judge and SOAR) for further differentiating search results
- An empirical baseline showing the `understanding` package produces non-trivial scores (stdev 0.113, range 0.194-0.756) on conversational text — calibration showed VARIANCE; whether high-scoring drawers are also USEFULLY high-scoring (i.e., more relevant) remains an open question for live use (see risk register #4)
- The pattern for vendoring local-only sibling packages without creating dep chains
- A reproducibility tool (calibration script) for future threshold-tuning conversations
