# SOAR ↔ LLM-judge Composable Order (PR #4b) — Design Spec

**Date:** 2026-05-13
**Status:** Approved, ready for implementation plan
**Scope:** Sub-PR #4b of the SOAR umbrella named in PR #4a's spec (`2026-05-13-soar-fusion-design.md`). Lets the user control invocation order of Stage 4 (LLM-judge) and Stage 5 (SOAR boost-tags) when both stages are enabled.

## Background

PR #4a (merged at `653b8208`) wired SOAR as a post-pipeline boost-tag layer with a **fixed** invocation order: cross-encoder rerank → LLM-judge (if `--llm-rerank`) → SOAR (if `--soar-boost`). The order was hard-coded because the spec deferred user control to a separate sub-PR.

PR #4a's spec explicitly states:
> "Composable order with LLM-judge — fixed order: SOAR runs LAST in #4a; #4b makes this user-configurable."

This PR is #4b. It introduces a `--soar-first` CLI flag (and matching MCP param) that flips the order to: cross-encoder rerank → SOAR (reorder via boost-tags) → LLM-judge (picks from SOAR-influenced top-N).

The semantic difference matters:
- **Default (judge-then-SOAR):** LLM picks the best from cross-encoder's top, then hand-crafted SOAR rules apply final boost adjustments. "AI judgment with rule-based final touch."
- **`--soar-first` (SOAR-then-judge):** SOAR's hand-crafted rules reorder the top-N first; the LLM picks the best from that SOAR-influenced view. "Rules shape what the AI considers; AI picks the best."

The default ordering is preserved (backwards compat). `--soar-first` is opt-in and requires BOTH `--llm-rerank` AND `--soar-boost` to be on (errors loudly otherwise).

## Umbrella context

| Sub-PR | Scope | Status |
|---|---|---|
| **#4a** | SOAR bridge restore + post-pipeline boost-tags + EpMem/SMem configured (unused) | ✅ Merged at `653b8208` |
| **#4b — THIS SPEC** | SOAR ↔ LLM-judge composable order (user controls invocation order) | Designing now |
| **#4c** | SOAR chunking + persistent learning across sessions (SOTA research payoff) | Future, separate spec |

## Goal

1. **Refactor SOAR into a proper pipeline stage.** Currently `apply_soar_boosts` lives in `cli.py:cmd_search` as an external post-step that operates on the final hits dict. For 4b, SOAR moves INSIDE `_new_pipeline_search` (the same place Stage 4 LLM-judge already lives). The cli.py conditional branch goes away — cli.py just passes through new params.

2. **Add `soar_first: bool = False` param** to `search_memories` + `_new_pipeline_search`. When `True` AND both `soar_boost=True` AND `llm_rerank=True`, SOAR runs BEFORE the LLM-judge step.

3. **Add `--soar-first` CLI flag** with loud validation: if set but `--llm-rerank` or `--soar-boost` missing, `sys.exit(2)` with a clear message naming the missing flag(s).

4. **MCP symmetry:** `soar_first: bool` param on the `search_memories` MCP tool. Same validation, returns MCP error response on mismatch (no `sys.exit` from MCP path).

## Non-goals

- **Skip-conditions or feedback signals.** "Skip SOAR if judge top-1 agrees with cross-encoder top-1" is a feedback loop — that's #4c territory.
- **Boost-tag handoff to LLM prompt.** Passing SOAR's audit-trail (boost-tags, score_pre_soar) INTO the judge prompt so the LLM can reason about SOAR's reasons. Prompt-engineering scope; belongs in #4c research payoff.
- **More than two orderings.** Just judge-then-SOAR (default) and SOAR-then-judge (`--soar-first`). Not "SOAR-then-judge-then-SOAR" or other compositions.
- **New SOAR rules.** Same 2 productions from #4a (`recency-boost`, `same-project`). Rule additions wait on #4c data-fields work.
- **Default behavior change.** Existing users with `--soar-boost` (with or without `--llm-rerank`) get byte-identical output. Only users who explicitly add `--soar-first` see new behavior.
- **`search()` (CLI print path) doesn't get a new param.** It already calls `search_memories(...)` — params flow through transitively.

## Architecture

### Half 1: Move SOAR into the pipeline

Currently in `cli.py:cmd_search`:

```python
if soar_boost:
    result = search_memories(...)
    hits = result.get("results", [])
    if hits:
        from . import soar_bridge
        hits = soar_bridge.apply_soar_boosts(hits, cfg)
        hits.sort(key=lambda h: -h.get("score", 0.0))
    boosted_result = dict(result, results=hits)
    _print_search_results(boosted_result, args.query)
else:
    search(...)
```

After 4b:

```python
search(
    query=args.query,
    palace_path=palace_path,
    ...,
    llm_rerank=llm_rerank,
    soar_boost=soar_boost,
    soar_first=soar_first,
)
```

The `if soar_boost: ... else: ...` branch disappears. SOAR is now invoked from inside `_new_pipeline_search` based on the `soar_boost` param.

### Half 2: SOAR ↔ judge ordering inside `_new_pipeline_search`

Pipeline branches AFTER Stage 3 (cross-encoder produces `reranked: list[tuple[float, dict]]`):

**Default (`soar_first=False`):**
```python
if llm_rerank:
    reranked = _stage_4_judge(query, reranked, cfg)
if soar_boost:
    reranked = _stage_5_soar(reranked, cfg)
# format final hits
```

**`soar_first=True` (requires `soar_boost=True` AND `llm_rerank=True`):**
```python
reranked = _stage_5_soar(reranked, cfg)
reranked = _stage_4_judge(query, reranked, cfg)
# format final hits
```

(`_stage_4_judge` and `_stage_5_soar` are internal helpers in `searcher.py` that wrap the existing Stage 4 inline code and the new tuple-shape SOAR call, respectively. Not new public APIs.)

### Half 3: SOAR API — operate on tuples internally

`soar_bridge.apply_soar_boosts(hits, cfg)` currently takes the final-hits dict shape. For the in-pipeline call, we need to operate on `(rerank_score, row)` tuples — the shape produced by Stage 3.

**New internal function:**
```python
def _apply_soar_to_reranked(
    reranked: list[tuple[float, dict]],
    cfg,
) -> list[tuple[float, dict]]:
    """Apply SOAR boost-tags to a list of (score, row) tuples.

    Returns a new list sorted by boosted score (descending).
    Audit-trail fields (soar_boost, soar_tags, score_pre_soar) are
    attached to each row dict so the final hit formatter can surface them.
    """
```

Implementation: same Soar agent setup, same WM schema, same rule firings as the existing `apply_soar_boosts`. Only the input/output shape differs. The actual rule-firing logic is shared (extracted to a private helper if needed).

`apply_soar_boosts(hits, cfg)` keeps its current signature as a public API for any external user code that imports it directly from `soar_bridge`. After this PR, NO internal call sites remain — both cli.py and mcp_server.py call sites are removed (SOAR now runs inside `search_memories`). The function stays public mainly for tests (`tests/test_soar_bridge.py` exercises it directly) and any third-party plugins that might call it.

### Half 4: CLI flag + validation

`--soar-first` boolean flag added to `castle search` argparse. Validation in `cmd_search`:

```python
if args.soar_first:
    missing = []
    if not args.llm_rerank:
        missing.append("--llm-rerank")
    if not args.soar_boost:
        missing.append("--soar-boost")
    if missing:
        print(
            f"--soar-first requires both --llm-rerank and --soar-boost; "
            f"missing: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(2)
```

`--soar-first` alone or with only one of the other two flags is loud (`sys.exit(2)`). Same loud-fail philosophy as the existing SOAR kill switch (`CASTLE_SOAR_ENABLED=0` + `--soar-boost` mismatch).

### Half 5: MCP symmetry + MCP-side SOAR migration

`soar_first: bool = False` param added to the `search_memories` MCP tool schema (and any other MCP tools that wrap `search_memories`). Same validation, but instead of `sys.exit(2)` the MCP path returns an error response:

```python
if soar_first and not (soar_boost and llm_rerank):
    return {"error": "soar_first requires both soar_boost and llm_rerank to be true"}
```

**The MCP path ALSO has its own external `apply_soar_boosts` call** at `mcp_server.py:421-435` (mirror of the cli.py block this PR removes). To keep CLI and MCP symmetric, that block is REMOVED in this PR. The MCP tool just passes `soar_boost` and `soar_first` through to `search_memories()`, which handles both stages inside the pipeline. After this PR, NO internal call sites of `apply_soar_boosts` remain — it stays as a public API for external user code only.

## Components (file-level changes)

| File | Change | LOC |
|---|---|---|
| `cognitive_castle/searcher.py` | Add `soar_boost: bool = False`, `soar_first: bool = False` to `search_memories()` + `_new_pipeline_search()`. Inside `_new_pipeline_search` after Stage 3 (around line 494): extract Stage 4 (judge) call to a private helper `_stage_4_judge(query, reranked, cfg) -> reranked`. Add Stage 5 (SOAR) call as private helper `_stage_5_soar(reranked, cfg) -> reranked`. Branch on `soar_first` to call them in the right order. | +35 |
| `cognitive_castle/soar_bridge.py` | Add `_apply_soar_to_reranked(reranked, cfg) -> reranked`. Extract the rule-firing core from `apply_soar_boosts` into a shared private helper. Both public entry points (`apply_soar_boosts` for dict input, `_apply_soar_to_reranked` for tuple input) call the shared helper with appropriate adapter logic. | +50 |
| `cognitive_castle/cli.py` | Add `--soar-first` argparse flag to the `search` subcommand. In `cmd_search`: validate combination (errors loudly if `--soar-first` without `--llm-rerank` or `--soar-boost`). REMOVE the existing `if soar_boost: ... else:` conditional branch — both stages now run inside `search_memories`. Just pass `soar_boost` + `soar_first` through to `search()`. | +20, -25 |
| `cognitive_castle/mcp_server.py` | Add `soar_first: bool = False` to the `search_memories` MCP tool schema. Add validation that returns an error response if `soar_first` is True but `soar_boost` or `llm_rerank` is False. Pass `soar_boost` and `soar_first` through to `search_memories()`. **REMOVE** the existing external `if soar_boost: ... apply_soar_boosts(hits, _config) ...` block at lines 421-435 — SOAR now runs inside `search_memories`, mirroring the cli.py removal. | +12, -15 |
| `tests/test_soar_bridge.py` | Add `test_apply_soar_to_reranked_tuple_parity` — feeds the same data to both the dict path and the new tuple path; asserts the boost-tags fired are identical. Add `test_apply_soar_to_reranked_returns_sorted_tuples` — verifies output sorted by boosted score descending. | +50 |
| `tests/test_pipeline_order.py` (new) | New file. 6 tests for the ordering logic (default-preservation × 3, `soar_first` × 3 — see Testing section). | +120 |
| `tests/test_cli.py` | Add `test_cli_soar_first_without_llm_rerank_errors`, `test_cli_soar_first_without_soar_boost_errors`. Both expect `sys.exit(2)` with a message naming the missing flag. | +30 |
| `tests/test_mcp_server.py` | Add `test_mcp_soar_first_without_other_flags_returns_error` — invokes MCP tool with mismatched params, asserts error-response shape. | +20 |
| `CLAUDE.md` | Update retrieval pipeline diagram (around line 184) to show Stage 4 ↔ Stage 5 as orderable. Note `--soar-first` as the flag controlling order. | +3, -1 |
| `README.md` | Brief mention in the SOAR subsection (after the existing `--soar-boost` description) — describes `--soar-first` as an opt-in ordering switch. | +12 |

**Total: ~340 LOC across 10 files.** No new modules; mostly parameterization + 2 small helper extractions.

## Data flow

### Default path (no `--soar-first`, both stages on)

```
castle search "foo" --llm-rerank --soar-boost
  → cmd_search
  → search(query, palace_path, llm_rerank=True, soar_boost=True, soar_first=False)
  → search_memories(...)
  → _new_pipeline_search(...)
  → Stage 1-2 (parallel recall + RRF + recency)
  → Stage 3 (cross-encoder rerank) → reranked: [(s, row), ...]
  → Stage 4 (_stage_4_judge): reorder top-N via LLM
  → Stage 5 (_stage_5_soar): apply boost-tags, re-sort by boosted score
  → format final hits + return
```

Byte-identical to current behavior on develop. Existing users see no change.

### `--soar-first` path

```
castle search "foo" --llm-rerank --soar-boost --soar-first
  → cmd_search
  → validation: all 3 flags present → pass
  → search(query, palace_path, llm_rerank=True, soar_boost=True, soar_first=True)
  → _new_pipeline_search(...)
  → Stage 1-2-3 same as default
  → Stage 5 (_stage_5_soar): apply boost-tags FIRST, re-sort
  → Stage 4 (_stage_4_judge): operates on SOAR-reordered top-N, picks LLM-preferred order
  → format final hits + return
```

Subtle but important: when `soar_first=True`, the LLM-judge sees candidates that SOAR has ALREADY reordered. The judge's top-N selection is from SOAR's view, not the cross-encoder's view. SOAR-applied scores are preserved as `score_pre_soar` in the audit-trail fields; the judge sees the new ordering but the LLM prompt itself does NOT see the boost tags (judge only takes docs + query, no metadata).

### Candidate-pool size difference between the two orderings

Stage 4 (judge) TRUNCATES `reranked` from `cfg.reranker_k_interactive` candidates (~20) down to `cfg.llm_judge_top_n` (~10). This matters for SOAR's input pool:

- **Default (judge-then-SOAR):** judge truncates to top-10 first, then SOAR re-ranks those 10. SOAR sees only the cross-encoder's top-10.
- **`soar_first=True`:** SOAR re-ranks all 20 first, then judge truncates to top-10 from SOAR's preferred order. SOAR sees the full ~20.

Real consequence: a hit ranked 15th by cross-encoder that would fire `same-project` SOAR boost is INVISIBLE to SOAR in default mode (truncated away before SOAR runs) but VISIBLE in `soar_first` mode (SOAR sees it, boosts it, possibly enough to make the judge's top-10). The two orderings can produce genuinely different result sets, not just different orderings of the same set.

### Score vs. order in `soar_first` mode

The final hit list has:
- **`score` field**: SOAR's boosted score (because `_apply_soar_to_reranked` rewrote the tuple's first element)
- **List position**: judge's preferred order (because `_stage_4_judge` reordered the tuples after SOAR ran)

A hit at position 0 might NOT have the highest `score` — the judge moved it there because the LLM prefers it, but a lower-`score` hit could be at position 0 if SOAR-boosted it less than another candidate the judge demoted.

Consumers expecting `score ↓` to correlate with `position ↑` will be surprised. This is intentional in `soar_first` mode (you asked for SOAR-then-judge; judge has final say on order). The audit-trail field `score_pre_soar` already exposes the original cross-encoder score; the SOAR-boosted score is the `score` field; the position is the judge's verdict. No new field added — consumers who care can derive judge's rank from list position.

In default (judge-then-SOAR) mode, `score ↓` and `position ↑` DO agree because SOAR's final sort-by-boosted-score is the last operation.

### Validation-error path

```
castle search "foo" --soar-first
  → cmd_search
  → validation: soar_first set but llm_rerank=False AND soar_boost=False
  → print error to stderr: "--soar-first requires both --llm-rerank and --soar-boost; missing: --llm-rerank, --soar-boost"
  → sys.exit(2)
```

### Default invocation (no flags)

```
castle search "foo"
  → cmd_search
  → search(query, palace_path, llm_rerank=False, soar_boost=False, soar_first=False)
  → _new_pipeline_search(...)
  → Stage 1-2-3
  → Stage 4 skipped (llm_rerank=False)
  → Stage 5 skipped (soar_boost=False)
  → format + return
```

Byte-identical to develop.

## Error handling

| Failure | Behavior |
|---|---|
| `--soar-first` without `--llm-rerank` | `sys.exit(2)` with message: `"--soar-first requires both --llm-rerank and --soar-boost; missing: --llm-rerank"` |
| `--soar-first` without `--soar-boost` | Same shape, names the missing flag |
| `--soar-first` without BOTH | Same shape, names both missing flags in the order checked |
| `--soar-first` + kill switch `CASTLE_SOAR_ENABLED=0` | Existing kill-switch validation fires FIRST (`sys.exit(2)` with kill-switch message). `--soar-first` validation never reached. |
| SOAR rule-firing fails inside pipeline (Soar SML crash, rule init error) | Identical to current: graceful pass-through, `soar_boost=1.0` on all hits, audit-trail tags empty. Pipeline continues to Stage 4 (or skips it if `soar_first=False`) as if SOAR wasn't on. |
| LLM-judge fails when `soar_first=True` | Identical to current Stage 4 fallback: identity-order fallback. Hits keep SOAR-reordered order, no judge influence. |
| MCP `soar_first: true` without `soar_boost` or `llm_rerank` | Tool returns `{"error": "soar_first requires both soar_boost and llm_rerank to be true"}` — no `sys.exit` from MCP path. |
| `_apply_soar_to_reranked` receives empty `reranked` list | Returns empty list. Same as current empty-pipeline behavior. |
| Race condition / threading on Soar agent (re-entrant call) | Existing Soar agent lifecycle preserved — agent created once per call, destroyed when call ends. No re-entrant scenarios introduced by 4b. |

No new failure modes — all SOAR rule-failure paths already exist and are reused.

## Testing

### Default-preservation tests (regression guards)

```python
def test_default_path_unchanged_with_soar_boost_only(...):
    """soar_boost=True, soar_first=False runs judge-then-SOAR. Byte-identical to current."""
    # Capture output with develop's behavior (or use a snapshot fixture)
    # Run with new code, assert identical hits

def test_default_path_unchanged_with_llm_only(...):
    """llm_rerank=True, soar_boost=False unaffected by 4b refactor."""

def test_default_path_unchanged_with_both_off(...):
    """Neither flag set: pipeline is rerank-only. Byte-identical to develop."""
```

### `soar_first` path tests

```python
def test_soar_first_runs_soar_before_judge(...):
    """Instrument _stage_4_judge and _stage_5_soar with call counters.

    Run search with soar_first=True. Assert _stage_5_soar.call_count == 1
    AND it fires BEFORE _stage_4_judge. Verify the reranked list passed to
    judge has SOAR's score adjustments (score != original rerank_score).
    """

def test_soar_first_audit_trail_preserved(...):
    """Final hits still carry soar_boost, soar_tags, score_pre_soar.

    Judge doesn't strip them — the row dict is mutated in place by SOAR
    and the judge only reorders the tuples, not the rows themselves.
    """

def test_soar_first_judge_fallback_preserves_soar_order(...):
    """When LLM-judge fails (identity-order fallback) in soar_first mode,
    final order is SOAR's order — judge's no-op doesn't undo SOAR's work.
    """
```

### Tuple-parity tests (in `tests/test_soar_bridge.py`)

```python
def test_apply_soar_to_reranked_tuple_parity(...):
    """Feed identical data to apply_soar_boosts(hits, cfg) and
    _apply_soar_to_reranked([(s, row), ...], cfg). Assert the boost-tags
    fired are identical (same rule activations, same multipliers).
    """

def test_apply_soar_to_reranked_returns_sorted_tuples(...):
    """Output is sorted by boosted score descending."""
```

### CLI validation tests (in `tests/test_cli.py`)

```python
def test_cli_soar_first_without_llm_rerank_errors(capsys):
    """castle search --soar-boost --soar-first → sys.exit(2), message names --llm-rerank as missing."""

def test_cli_soar_first_without_soar_boost_errors(capsys):
    """castle search --llm-rerank --soar-first → sys.exit(2), message names --soar-boost as missing."""

def test_cli_soar_first_alone_errors(capsys):
    """castle search --soar-first → sys.exit(2), message names BOTH flags as missing."""
```

### MCP test (in `tests/test_mcp_server.py`)

```python
def test_mcp_soar_first_without_other_flags_returns_error():
    """MCP tool call with soar_first=True but soar_boost=False returns
    {"error": "..."}. No sys.exit fires from MCP path.
    """
```

### Smoke tests (manual, for PR description)

- `castle search "test" --llm-rerank --soar-boost --soar-first` returns results, audit-trail intact
- `castle search "test" --soar-first` errors with `sys.exit(2)`
- `castle search "test"` (no flags) — output identical to develop

## Acceptance criteria

1. All new tests pass.
2. Existing test suite stays at baseline (no NEW failures vs develop).
3. `castle search "foo"` (default invocation, no flags) — output (text and hit ordering) identical to develop.
4. `castle search "foo" --soar-boost` (existing behavior) — same hits in same order with same fields as develop.
5. `castle search "foo" --llm-rerank --soar-boost` — same hits in same order with same fields as develop.
6. `castle search "foo" --soar-first` errors with `sys.exit(2)` + clear message naming missing flag(s).
7. `castle search "foo" --llm-rerank --soar-boost --soar-first` works, audit-trail intact (each hit has `soar_boost`, `soar_tags`, `score_pre_soar`).
8. MCP `search_memories(soar_first=true, soar_boost=true, llm_rerank=true)` parity with CLI.
9. MCP `search_memories(soar_first=true, soar_boost=false)` returns error-response.
10. MCP `search_memories(soar_boost=true)` (no `soar_first`) — same hits as `search_memories(soar_boost=true)` on develop. The external→internal SOAR migration in `mcp_server.py` produces equivalent output.
11. `ruff check` + `ruff format --check` clean on all 10 touched files.
12. CLAUDE.md retrieval-pipeline diagram updated to show Stage 4 ↔ Stage 5 as orderable.
13. README's SOAR subsection mentions `--soar-first`.

## Out of scope (deferred)

- **Skip-conditions** (e.g., "skip SOAR if judge top-1 agrees with cross-encoder top-1") — that's #4c feedback-loop territory.
- **Boost-tag handoff to LLM prompt** — passing SOAR's audit-trail into the judge prompt so the LLM can reason about boost reasons. Prompt-engineering scope, belongs in #4c.
- **More than two orderings** — only `judge-then-SOAR` (default) and `soar-then-judge` (`--soar-first`). Not extensible to 3+ orderings without revisiting the boolean-flag design.
- **New SOAR rules** — same 2 productions from #4a (`recency-boost`, `same-project`). Rule additions wait on data-fields work (deferred to #4c).
- **Persistent learning / chunking** — that's #4c.

## Spec self-review (2026-05-13)

1. **Placeholders:** None. Helper function names (`_stage_4_judge`, `_stage_5_soar`, `_apply_soar_to_reranked`) are concrete. Both error-message texts shown verbatim. Code snippets for the cli.py refactor + the ordering branch shown.
2. **Internal consistency:** Architecture, Data Flow, Error Handling, Testing, and Acceptance all reference:
   - Two new params: `soar_boost: bool` + `soar_first: bool` on `search_memories` + `_new_pipeline_search`
   - SOAR moves INSIDE `_new_pipeline_search` (no longer external in cli.py)
   - Default ordering preserved (judge-then-SOAR) — backwards compat
   - `--soar-first` validation: loud `sys.exit(2)` on missing companion flags
   - MCP symmetry: same param, error-response shape (no `sys.exit`)
   - Tuple-shape internal SOAR helper preserves rule-firing parity with the dict path
3. **Scope:** Single PR. ~340 LOC across 10 files. Single feature: composable ordering. No scope-bleeding into #4c.
4. **Ambiguity:** Default behavior preserved (stated in Goal, Architecture, Data Flow, Acceptance). `--soar-first` validation rules stated in 3 places (Architecture, Error Handling, Acceptance). Kill-switch precedence (kill switch fires first) called out explicitly in Error Handling.
5. **Empirical grounding:**
   - SOAR pipeline location confirmed at `cli.py:cmd_search` lines 599-619 (current) — branch is removed in this PR
   - Stage 4 LLM-judge location confirmed at `searcher.py:_new_pipeline_search` lines 497-507 — Stage 5 SOAR is added immediately after; Stage 4 truncates to `cfg.llm_judge_top_n` (=10)
   - `apply_soar_boosts` signature confirmed at `soar_bridge.py:349` — keeps current public API
   - Second `apply_soar_boosts` call site confirmed at `mcp_server.py:421-435` — also removed in this PR for CLI/MCP symmetry
   - 2 SOAR rules from #4a (`recency-boost`, `same-project`) are unchanged
   - `cfg.soar_enabled` kill switch behavior confirmed at `cli.py:cmd_search` lines 590-595 — fires before any `--soar-first` validation

## Revision history

**Revision 2 (2026-05-13):** Spec review surfaced 3 substantive issues. Fixed inline:
- **MCP migration:** the spec described moving SOAR into the pipeline for cli.py but didn't address `mcp_server.py:421-435` (mirror `apply_soar_boosts` call site). Added Half 5 explicit removal note, updated Components row to call out the -15 LOC removal, added new acceptance criterion #10 verifying MCP output equivalence after the migration.
- **Truncation-pool difference:** added a new "Candidate-pool size difference" subsection under Data Flow. Stage 4 truncates from `cfg.reranker_k_interactive` (~20) down to `cfg.llm_judge_top_n` (~10). Default mode SOAR sees the post-truncation 10; `soar_first` mode SOAR sees the full 20. The two orderings can produce different result sets, not just different orderings of the same set.
- **Score-vs-order in `soar_first` mode:** added a new "Score vs. order" subsection. In `soar_first` mode, hit `score` is SOAR's boosted score but list position is the judge's preferred order — they may not agree. Documented as intentional (you asked for SOAR-then-judge, judge has final say on order); audit-trail field `score_pre_soar` already exposes original cross-encoder score. No new field added.

Plus minor polish:
- Replaced "byte-identical" with "same hits in same order with same fields" in acceptance criteria (more accurate for dict-based outputs).
- Named the back-compat consumers of `apply_soar_boosts` explicitly: tests + third-party plugins. After this PR no internal callers remain.
