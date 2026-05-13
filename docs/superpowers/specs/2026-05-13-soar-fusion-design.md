# SOAR Bridge + Post-Pipeline Boost-Tags (PR #4a) — Design Spec

**Date:** 2026-05-13
**Status:** Approved, ready for implementation plan
**Umbrella:** SOTA retrieval upgrade — PR #4 (decomposed into 3 sub-PRs; this is PR #4a)

## Background

SOAR (State, Operator And Result) is a symbolic cognitive architecture with production rules, working memory, and chunking-based learning. Castle originally had a SOAR integration (`cognitive_castle/soar_bridge.py`, 271 LOC + 3 `.soar` rule files totaling 270 LOC + 404 LOC of tests). PR #14 (commit `b49ebe83`, 2026-05-12) deleted all of it as dead code because:

- SML Python bindings were not installed (`Python_sml_ClientInterface` import always failed)
- `apply_soar_boosts()` swallowed the import error and returned hits unchanged
- The 144-line `castle-boost.soar` rule file never fired
- Tests skipped 100% of the time
- The cross-encoder reranker added in PR #12 became the active re-ranking layer

This spec restores SOAR — but **working this time**. Verified 2026-05-13:

```bash
$ python -c "import Python_sml_ClientInterface as sml; \
  kernel = sml.Kernel.CreateKernelInNewThread(); \
  print(kernel.GetSoarKernelVersion())"
9.6.40
```

Soar 9.6.40 + SML Python bindings are live on the user's machine, installed at `/home/lbihari/soar-work/Soar/build/...`. The "bridge to nowhere" failure mode that killed PR #14 no longer applies on the developer's hardware.

This PR is **PR #4a of a 3-sub-PR umbrella** that brings SOAR's full power to Castle's retrieval pipeline:

| Sub-PR | Scope | Status |
|---|---|---|
| **#4a — THIS SPEC** | SOAR bridge restore + post-pipeline boost-tags + EpMem/SMem subsystems configured (but not used) | Designing now |
| #4b — composable with LLM-judge | Wires SOAR + LLM-judge so user controls invocation order | Future, separate spec |
| #4c — chunking + persistent learning | SOAR learns from LLM-judge disagreement, chunks rules to EpMem/SMem, replays on startup. This is the SOTA-research contribution. | Future, separate spec |

Each sub-PR ships independently and is gated by `--soar-boost` (CLI) or `soar_boost:true` (MCP). Default behavior is unchanged across all three.

## Umbrella context

| # | Sub-project | Status |
|---|---|---|
| 1 | bge-m3 unblock + migration | Merged at `2118d1df` |
| 2 | mxbai-rerank-large-v2 swap | Deferred — multilingual reasons |
| 3 | LLM-as-judge Stage 4 | Merged at `5f3f7385` |
| 4a | SOAR bridge + post-pipeline boost-tags | **THIS SPEC** |
| 4b | SOAR composable with LLM-judge | Future |
| 4c | SOAR chunking + persistence | Future |

Queued follow-ups (separate concerns, not in this spec):
- **bge-m3 default cutover** — make bge-m3 the default embedder, retiring MiniLM (small PR)
- **PR #2-redux as docs-only** — document `CASTLE_RERANKER_MODEL_GPU=mixedbread-ai/mxbai-rerank-large-v2` as English-only opt-in (tiny PR)
- **`gemma3:e4b` default-LLM-tag fix** — Castle's documented default doesn't exist in Ollama; need to pick a real working model (small PR)

## Goal

Restore SOAR as the post-pipeline boost-tag layer that was deleted in PR #14, with Soar 9.6+ + SML bindings as a hard prerequisite. Opt-in via `--soar-boost` flag and `soar_boost:true` MCP param. Use Soar's native EpMem + SMem subsystems from day one (configured but not USED in #4a) so the chunking work in #4c doesn't require a storage-layer migration.

Default behavior unchanged. Users who never pass `--soar-boost` AND never set `CASTLE_SOAR_ENABLED=1` get byte-identical output to today. The SOAR module is never imported in the default path.

## Non-goals

- **Activating EpMem/SMem reads/writes.** Subsystems are *configured* via `epmem --set learning on` / `smem --set learning on` but not queried or written from in #4a. That's #4c.
- **Composable order with LLM-judge.** If both `--llm-rerank` and `--soar-boost` are passed, SOAR runs LAST (after LLM-judge). #4b will make this user-configurable.
- **Chunking activation.** No impasse resolution → no chunk creation in #4a. That's #4c.
- **Bundling Soar binary.** PyPI distribution of Soar is not feasible; users must build from source. README documents the install.
- **Touching `searcher.py`'s 3-stage pipeline.** SOAR is post-pipeline; the integration point is the CLI/MCP entry-handler layer.

## Architecture

```
Stage 1 → Stage 2 (fusion) → Stage 3 (cross-encoder rerank)
                                            │
                          ┌─ if --llm-rerank ─→ Stage 4 (LLM-judge re-rank)
                          │
                          └─ otherwise ─→ skip Stage 4
                                            │
                          ┌─ if --soar-boost AND cfg.soar_enabled ─→ Stage 5: SOAR boost-tags
                          │                                            │
                          │                                            └─→ adjust scores via multipliers
                          │                                                + audit-trail fields (soar_boost, soar_tags)
                          │
                          └─ default ─→ return as-is
```

**New module: `cognitive_castle/soar_bridge.py`** (~250 LOC). Structure mirrors the deleted version:

- `_load_sml()` — lazy import with clear error message if Soar unavailable. Cached. Returns `None` and prints stderr warning ONCE per process on failure.
- `_get_kernel()` — module-level singleton Soar kernel.
- `_get_agent(palace_path)` — palace-keyed agent. First-time creation loads productions from `cfg.soar_rules_path` and enables EpMem + SMem subsystems.
- `apply_soar_boosts(hits, cfg) -> list[dict]` — public entry. Builds working memory from hits, runs decision cycle, reads back boost-tags, applies multipliers, returns hits with `score` adjusted + `soar_boost` + `soar_tags` audit fields.
- `BOOST_MULTIPLIERS: dict[str, float]` — module-level tag → multiplier map.

**New rule file: `cognitive_castle/rules/castle-boost.soar`** — initial production set (5-7 rules). Match candidate metadata, emit `^boost-tag <tag>` attributes. Reference material: prior 144-line version in git history (commit `b49ebe83`); this PR ships a *minimal subset* and adds more in follow-ups.

**Pipeline integration:** Post-pipeline boost runs in TWO places — CLI (`cli.py:cmd_search`) and MCP (`mcp_server.py` `castle_search` handler). Both consult the opt-in flag and call `apply_soar_boosts(hits, cfg)` AFTER `search_memories()` returns (and after Stage 4 LLM-judge if enabled).

## Components (file-level changes)

| File | Change | LOC |
|---|---|---|
| `cognitive_castle/soar_bridge.py` (new) | Public `apply_soar_boosts(hits, cfg) -> list[dict]`. Lazy SML import via `_load_sml()`. Singleton kernel via `_get_kernel()`. Per-palace agent via `_get_agent(palace_path)`. Builds working memory from hits using the input-link schema (`^context` + `^memory[]`), runs decision cycle via `agent.RunSelf(50)`, reads back `^boost-tag` attributes, maps tags to multipliers via `BOOST_MULTIPLIERS`, applies to `hit["score"]`. Augments hits with `soar_boost` (float compound multiplier) + `soar_tags` (list[str]) + `score_pre_soar` (original score). Stderr-warning-+-return-unchanged fallback on any Soar failure. Boost clamped to range `[0.1, 10.0]` to prevent compound explosion. One-time-per-process warning via module-level `_WARNED: set`. | +250 |
| `cognitive_castle/rules/castle-boost.soar` (new) | Initial production set (5-7 rules). Each matches on memory attributes and adds `^boost-tag <tag>`. Initial tags: `recency-boost`, `entity-match`, `same-project`, `correction-priority`, `stale-penalty`. Includes the standard Soar header (`sp {*<name>` syntax) with production names prefixed `castle-boost*`. | +60 |
| `cognitive_castle/config.py` | Add 2 new properties (env-first → file-config → default, matching `embedder_model` pattern at `config.py:305-321`): `soar_enabled` (default `False`, env `CASTLE_SOAR_ENABLED`) — kill switch. `soar_rules_path` (default `<package>/rules/castle-boost.soar`, env `CASTLE_SOAR_RULES_PATH`) — lets users point at custom rule files. | +30 |
| `cognitive_castle/cli.py` | Add `--soar-boost` flag (store_true, default False) to `castle search` subparser. Pass through to `search()` (which then propagates to the search dict). Help text: `"Apply SOAR symbolic-rule boost-tags to final scores (experimental; requires Soar 9.6+ + SML Python bindings installed; activate via CASTLE_SOAR_ENABLED=1)"`. ALSO: if `--soar-boost` is passed AND `cfg.soar_enabled` is False, `sys.exit(2)` with clear stderr `"CASTLE_SOAR_ENABLED=0 kill switch is active; remove it to use --soar-boost"` before any palace work happens. | +25 |
| `cognitive_castle/mcp_server.py` | Add `soar_boost: boolean (default false)` to `castle_search` tool schema. Handler reads `arguments.get("soar_boost", False)`; if True AND `cfg.soar_enabled`, call `soar_bridge.apply_soar_boosts(hits, cfg)` BEFORE returning. Runs AFTER llm-rerank (already applied earlier in handler from PR #3). Same kill-switch behavior: if soar_boost requested but soar_enabled False, raise a clear error in the response (MCP can't sys.exit). | +30 |
| `pyproject.toml` | Add `[project.optional-dependencies.soar]` marker. NO PyPI dependencies (Soar isn't on PyPI); just documents the prereq with a clear comment. | +5 |
| `tests/test_soar_bridge.py` (new) | 8 Soar tests gated by `@pytest.mark.soar` marker (auto-skip if SML import fails). Plus 2 non-Soar tests (kill switch, SML-unavailable fallback) that always run. | +200 |
| `tests/test_cli.py` (existing) | 2 tests: `--soar-boost` flag propagation; kill-switch exit code. | +30 |
| `tests/test_mcp_server.py` (existing) | 1 test: `soar_boost:true` MCP param threading. | +20 |
| `README.md` | Append `### Experimental: SOAR symbolic re-ranking` subsection inside the existing "Going further" block. Covers: what SOAR is (1-sentence intro), why experimental, install prerequisites (link to upstream Soar build instructions), how to enable (`CASTLE_SOAR_ENABLED=1` + `--soar-boost`), the kill switch + rules-path knobs, the audit fields in output (`soar_boost`, `soar_tags`, `score_pre_soar`). Strong note that this is research-grade. | +45 |
| `CLAUDE.md` | Update retrieval pipeline diagram (line 175-185 area) to show optional Stage 5. Match the "optional" annotation style used for Stage 4 LLM-judge. | +5 |

**Total:** ~700 LOC across 2 new modules + 1 new rule file + 1 new test file + 5 existing files.

## Data flow

### Default path (no `--soar-boost`, no `CASTLE_SOAR_ENABLED`)

```
castle search "..."   (or MCP castle_search)
  → Stages 1-3 (+ optional Stage 4 LLM-judge from PR #3)
  → return hits
  ← soar_bridge module is NEVER imported
```

Byte-identical to today's behavior.

### Opt-in path (`--soar-boost` AND `CASTLE_SOAR_ENABLED=1`)

```
castle search "..." --soar-boost   (with CASTLE_SOAR_ENABLED=1)
  → kill-switch check: cfg.soar_enabled is True → proceed
  → Stages 1-3 (+ optional Stage 4 LLM-judge)
  → hits = [...]
  → soar_bridge.apply_soar_boosts(hits, cfg)
      → _load_sml() — lazy import (cached)
      → kernel = _get_kernel() — singleton
      → agent = _get_agent(cfg.palace_path):
          → first time: kernel.CreateAgent + LoadProductions(cfg.soar_rules_path)
          → first time: epmem --set learning on; smem --set learning on
      → push WM: ^io.input-link.context.{project, query, query-lang}
                + ^io.input-link.memory[] (one per hit, up to 50)
      → agent.RunSelf(50) — runs to quiescence
      → read back ^io.output-link.boost-tag entries
      → for each hit: compound multipliers from fired tags, clamp [0.1, 10.0]
      → hit["soar_boost"] = compound_multiplier
      → hit["soar_tags"] = [tag_names...]
      → hit["score_pre_soar"] = hit["score"]
      → hit["score"] = hit["score"] * compound_multiplier
      → clear WM for next call
      → return hits
  → CLI re-sorts by adjusted score OR MCP returns augmented JSON
```

### Kill-switch path (`--soar-boost` AND `CASTLE_SOAR_ENABLED=0`)

```
castle search "..." --soar-boost   (with CASTLE_SOAR_ENABLED=0)
  → kill-switch check at CLI entry: cfg.soar_enabled is False
  → stderr: "CASTLE_SOAR_ENABLED=0 kill switch is active; remove it to use --soar-boost"
  → sys.exit(2)
  ← no palace work performed
```

For MCP, since handlers can't `sys.exit`, return an error response: `{"error": {"code": "kill_switch_active", "message": "..."}}`.

### SOAR working memory schema

```
state ^io.input-link <il>
<il>  ^context <ctx>
      ^memory  <m>     (one per hit, up to 50 hits per query)
<ctx> ^project       "ru-sixth-sense"     (from CASTLE_PROJECT env or "default")
      ^query         "try scored corner"  (the user's query string)
      ^query-lang    "en"                 (NEW — useful for multilingual boosts; detected from query)
<m>   ^id                "abc-123"        (composite: wing/room/source_file)
      ^type              "semantic"       (from hit metadata; defaults if missing)
      ^subtype           "correction"     (from hit metadata; defaults if missing)
      ^project           "ru-sixth-sense" (from hit.wing)
      ^score             0.85             (current Stage 3+4 score)
      ^decay             1.0              (computed from age; 1.0 in #4a — full impl in #4c)
      ^access-count      0                (placeholder in #4a — EpMem-driven in #4c)
      ^recently-accessed "true"           (boolean string)
      ^entity-match      "true"           (NEW — set if any KG entity hit triggered this drawer)
```

### Boost-tag multiplier mapping

```python
BOOST_MULTIPLIERS = {
    "recency-boost": 1.25,         # recently-accessed=true
    "entity-match": 1.30,          # KG hit confirms relevance
    "same-project": 1.15,          # hit project == query context project
    "correction-priority": 1.40,   # subtype=correction (high-signal type)
    "stale-penalty": 0.80,         # access-count low + age old
}
```

Multipliers compound multiplicatively. Final boost clamped to `[0.1, 10.0]`.

### Per-hit audit trail in output

```json
{
  "id": "abc-123",
  "text": "...",
  "wing": "...",
  "room": "...",
  "score": 1.38,                  // post-boost
  "score_pre_soar": 0.85,         // pre-boost
  "soar_boost": 1.625,            // compound multiplier (1.25 × 1.30)
  "soar_tags": ["recency-boost", "entity-match"]
}
```

This is what gives SOAR differentiating value vs. neural methods — every score change has a name.

## Error handling

All Soar failures degrade gracefully — search ALWAYS returns hits, never errors out due to Soar failure. Exception: the kill-switch case is intentionally LOUD (user explicitly mismatched flags + env).

| Failure | Behavior |
|---|---|
| `--soar-boost` passed AND `CASTLE_SOAR_ENABLED=0` | CLI: `sys.exit(2)` + stderr `CASTLE_SOAR_ENABLED=0 kill switch is active; remove it to use --soar-boost`. MCP: error response `{"error": {"code": "kill_switch_active"}}`. |
| SML Python bindings not installed (`import Python_sml_ClientInterface` fails) | `_load_sml()` catches ImportError, stderr `[soar] SML Python bindings not available — install Soar 9.6+ with SML or set CASTLE_SOAR_ENABLED=0` ONCE per process, returns hits unchanged. |
| `cfg.soar_enabled = False` AND no `--soar-boost` flag | `apply_soar_boosts` not invoked. Default path. |
| Kernel creation fails (`sml.Kernel.CreateKernelInNewThread()` raises) | Stderr `[soar] kernel creation failed (<error>): boost-tags skipped`, return hits unchanged. |
| Rule file not found (`cfg.soar_rules_path` invalid) | Caught at `agent.LoadProductions(path)`, stderr `[soar] rule file not found: <path>`, agent destroyed, return hits unchanged. |
| Production parse error (malformed `.soar` file) | Caught, stderr `[soar] rule parse failure: <line>`, agent destroyed, return hits unchanged. |
| Decision cycle hangs / exceeds max cycles | `agent.RunSelf(50)` returns after 50 cycles. If no tags emitted, stderr `[soar] no tags emitted after 50 cycles — check rule firing conditions`, return hits unchanged (no boost applied). |
| Working memory exceeds reasonable size (more than 50 hits) | Slice to first 50 before WM population; remaining hits returned unboosted. Stderr `[soar] truncated WM to 50 hits (input was <N>); remainder unboosted`. |
| Boost-tag value unknown (rule emits tag not in `BOOST_MULTIPLIERS`) | Tag ignored, stderr `[soar] unknown boost-tag '<tag>' — add to BOOST_MULTIPLIERS or check rule output` ONCE per process. |
| Compound multiplier outside `[0.1, 10.0]` | Clamp to bounds (silently, since this is a defensive measure documented in code comments). |

**One-time-per-process warning pattern:** module-level `_WARNED: set` tracks emitted warning keys (e.g. `_WARNED.add("sml-import-failed")`). Subsequent identical warnings suppressed. Matches the pattern in `embedding.py:143`.

## Testing

### New file: `tests/test_soar_bridge.py`

8 Soar tests gated by `@pytest.mark.soar` marker + 2 always-run tests:

```python
import pytest
import sys

_SML_AVAILABLE = False
try:
    import Python_sml_ClientInterface  # noqa: F401
    _SML_AVAILABLE = True
except ImportError:
    pass

pytestmark_soar = pytest.mark.skipif(not _SML_AVAILABLE, reason="Soar 9.6+ SML not installed")


# ── Soar-required tests (skip if SML unavailable) ──────────────────────


@pytest.mark.soar
@pytestmark_soar
def test_apply_soar_boosts_loads_rules_and_runs_decision_cycle(tmp_path):
    """Smoke: SOAR kernel + agent + rule file load + decision cycle completes."""
    # ... test body builds a minimal cfg pointing at the shipped rule file,
    # calls apply_soar_boosts with 3 hits, asserts no exception + hits returned.


@pytest.mark.soar
@pytestmark_soar
def test_apply_soar_boosts_returns_hits_unchanged_when_no_tags_fire(tmp_path):
    """Empty rule file → hits returned with soar_boost=1.0, soar_tags=[]."""


@pytest.mark.soar
@pytestmark_soar
def test_apply_soar_boosts_multiplies_score_for_recency_tag(tmp_path):
    """A hit with recently-accessed=true → recency-boost tag → score × 1.25."""


@pytest.mark.soar
@pytestmark_soar
def test_apply_soar_boosts_compounds_multiple_tags(tmp_path):
    """A hit matching 2 rules → both tags fire → multipliers compound (1.25 × 1.30)."""


@pytest.mark.soar
@pytestmark_soar
def test_apply_soar_boosts_clamps_to_range(tmp_path):
    """Compounded multipliers > 10.0 or < 0.1 → clamped to bounds."""


@pytest.mark.soar
@pytestmark_soar
def test_apply_soar_boosts_truncates_to_50_hits(tmp_path, capsys):
    """Input of 100 hits → WM populated with first 50; remaining 50 returned unboosted + stderr warning."""


@pytest.mark.soar
@pytestmark_soar
def test_apply_soar_boosts_clears_wm_between_calls(tmp_path):
    """Two sequential calls don't leak boost-tags from the first call into the second."""


@pytest.mark.soar
@pytestmark_soar
def test_apply_soar_boosts_unknown_tag_ignored_with_warning(tmp_path, capsys):
    """A rule that emits an unrecognized boost-tag → tag ignored, stderr warning once."""


# ── Always-run tests (no Soar dependency) ──────────────────────────────


def test_apply_soar_boosts_no_op_when_sml_unavailable(monkeypatch, capsys):
    """When _load_sml() returns None, return hits unchanged + stderr warning ONCE."""
    from cognitive_castle import soar_bridge
    monkeypatch.setattr(soar_bridge, "_load_sml", lambda: None)
    # Reset _WARNED so test is hermetic
    soar_bridge._WARNED.clear()
    cfg = ...  # minimal cfg with soar_enabled=True
    hits = [{"id": "a", "score": 0.5}]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    assert result == hits  # unchanged
    assert "SML Python bindings not available" in capsys.readouterr().err


def test_apply_soar_boosts_kill_switch_when_disabled(monkeypatch, capsys):
    """When cfg.soar_enabled=False, return hits unchanged + stderr 'disabled via config'."""
    # Note: the kill-switch ALSO fires at the CLI/MCP layer before apply_soar_boosts is called;
    # this test covers the defensive double-check at the function level.
```

### Extension to `tests/test_cli.py`

```python
def test_search_cli_soar_boost_flag_propagates(monkeypatch):
    """`castle search --soar-boost` reaches apply_soar_boosts when soar_enabled=True."""


def test_search_cli_soar_boost_with_kill_switch_exits_2(monkeypatch, capsys):
    """`--soar-boost` + CASTLE_SOAR_ENABLED=0 → sys.exit(2) + clear stderr."""
    monkeypatch.setenv("CASTLE_SOAR_ENABLED", "0")
    args = argparse.Namespace(
        query="x",
        soar_boost=True,
        # ...other args matching cmd_search shape
    )
    with pytest.raises(SystemExit) as exc:
        cmd_search(args)
    assert exc.value.code == 2
    assert "CASTLE_SOAR_ENABLED=0 kill switch is active" in capsys.readouterr().err
```

### Extension to `tests/test_mcp_server.py`

```python
def test_mcp_castle_search_soar_boost_threads_through(monkeypatch):
    """MCP castle_search with soar_boost:true reaches apply_soar_boosts handler."""
```

## Acceptance criteria

The PR is mergeable when ALL hold:

1. `pytest tests/test_soar_bridge.py -v -m soar` — **8 passed** on the developer's hardware (Soar 9.6.40 installed at `/home/lbihari/soar-work/Soar/`)
2. `pytest tests/test_soar_bridge.py -v` (no marker filter) — 2 always-run tests pass; 8 Soar tests skip with `reason="Soar 9.6+ SML not installed"` on systems without SML
3. `pytest tests/test_cli.py -v -k soar_boost` — 2 passed (flag propagation + kill-switch exit code)
4. `pytest tests/test_mcp_server.py -v -k soar_boost` — 1 passed
5. Default test suite: `pytest tests/ -v --ignore=tests/benchmarks` — no NEW regressions
6. `castle search --help` shows `--soar-boost` flag with "experimental; requires Soar 9.6+" mention
7. MCP `castle_search` tool schema (via `castle-mcp` `tools/list`) shows `soar_boost: boolean (default false)` property
8. `ruff check` + `ruff format --check` clean on all touched files
9. **Live smoke (happy path):**
   ```bash
   CASTLE_SOAR_ENABLED=1 CASTLE_PALACE_PATH=/tmp/castle-soar-smoke/palace \
     castle search "authentication" --soar-boost
   ```
   Completes, returns hits with `soar_boost` field populated, no stderr warnings, audit trail visible.
10. **Live smoke (kill switch):**
    ```bash
    CASTLE_SOAR_ENABLED=0 castle search "authentication" --soar-boost
    echo "exit: $?"
    ```
    Exits with code 2, stderr contains `CASTLE_SOAR_ENABLED=0 kill switch is active`.
11. **Live smoke (SML unavailable simulation):**
    ```bash
    # Hide SML by setting PYTHONPATH to a dir without it
    PYTHONPATH=/tmp CASTLE_SOAR_ENABLED=1 castle search "authentication" --soar-boost
    ```
    Completes successfully, returns hits unchanged, stderr contains `SML Python bindings not available`.
12. README has experimental subsection inside "Going further" block.
13. CLAUDE.md retrieval pipeline diagram shows optional Stage 5.
14. **Default behavior unchanged:** users without `--soar-boost` AND without `CASTLE_SOAR_ENABLED=1` get byte-identical output. `soar_bridge` module never imported in default path (verifiable via `python -X importtime castle search ... 2>&1 | grep soar` — should produce no output for default invocation).

## Out of scope (deferred to #4b / #4c)

- ❌ EpMem/SMem queries — subsystems configured at agent init but never read/written in #4a
- ❌ Composable order with LLM-judge — fixed order: SOAR runs LAST in #4a; #4b makes this user-configurable
- ❌ Chunking from impasse resolution — no learning loop in #4a; that's the #4c research payoff
- ❌ Persistent rule learning across sessions — chunks not stored
- ❌ Feedback signal — no signal collected from LLM-judge / user clicks / drawer access patterns
- ❌ Bundled Soar binary — user must build Soar 9.6+ + SML from source

## Spec self-review (2026-05-13)

1. **Placeholders:** None. Test code is concrete (mock setup + assertions shown for the always-run tests; Soar-gated tests describe intent + structure; rule-file structure shown for the new `.soar` file). The "minimal subset" wording for the initial rule set is intentional — exact rule bodies will be authored at plan time after smoke-testing each on the user's actual palace.
2. **Internal consistency:** Architecture, Components, Data Flow, Error Handling, Testing, and Acceptance all reference:
   - `cognitive_castle/soar_bridge.py` new module with `apply_soar_boosts(hits, cfg) -> list[dict]` public entry
   - Post-pipeline placement (Stage 5, after Stage 4 LLM-judge if present)
   - `--soar-boost` CLI flag + `soar_boost:true` MCP param
   - `CASTLE_SOAR_ENABLED` kill switch (loud `sys.exit(2)` on flag-vs-env mismatch)
   - Compound-multiplier boost with `[0.1, 10.0]` clamp
   - `BOOST_MULTIPLIERS` dict with the 5 initial tags + multipliers
   - Audit trail fields: `soar_boost`, `soar_tags`, `score_pre_soar`
   - WM schema with `^context` + `^memory[]` + the 2 NEW additions (`query-lang`, `entity-match`)
   - EpMem/SMem configured at agent init but unused
3. **Scope:** Single sub-PR (PR #4a). PR #4b (composable with LLM-judge) and PR #4c (chunking + persistence) explicitly deferred to their own spec cycles. The umbrella context table makes the 3-sub-PR decomposition explicit.
4. **Ambiguity:** Opt-in semantics ("default=False, never silently invoked, soar_bridge module not imported in default path") stated in Goal, Architecture, Data Flow, Error Handling, Acceptance #14. Kill-switch behavior (loud exit on flag-vs-env mismatch) stated in 3 places (Error Handling, CLI Components row, Acceptance #10).
5. **Empirical grounding:** Soar 9.6.40 + SML verified live on the developer's hardware (Background section quotes the verified `import Python_sml_ClientInterface` succeed). Module location: `/home/lbihari/soar-work/Soar/build/Core/ClientSMLSWIG/python/`.
6. **EpMem/SMem are stubs in #4a:** Configured but unused. The `^access-count` placeholder default of 0 makes this explicit — #4c will wire it to real EpMem data. Tests don't assert on EpMem state.
7. **Boost multiplier values are initial guesses:** The 5 initial multipliers (1.25 / 1.30 / 1.15 / 1.40 / 0.80) are chosen "in the same order of magnitude as cross-encoder score variations." No formal calibration in #4a. PR description should note this as a known limitation; #4c's chunking work will produce empirically grounded values.
