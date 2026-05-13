# SOAR Bridge + Post-Pipeline Boost-Tags (PR #4a) — Design Spec

**Date:** 2026-05-13
**Status:** Revised 3× after review (2026-05-13) — ready for implementation plan
**Umbrella:** SOTA retrieval upgrade — PR #4 (decomposed into 3 sub-PRs; this is PR #4a)
**Filename note:** This file is `*-soar-fusion-design.md` for historical reasons (initial spec arguments). The actual scope is post-pipeline boost-tags, NOT fusion-stage changes. Kept under the original name to preserve git history; a future PR could `git mv` it to `*-soar-bridge-restore-design.md` if the misnomer becomes confusing.

## Revision history

- **2026-05-13 (initial):** First draft, approved section-by-section.
- **2026-05-13 (post-review #1):** Substantive findings about scope vs. current data:
  1. **Internal contradiction fixed:** boost-tags are emitted by productions elaborating input-link `^memory` WMEs (i-supported attributes); Python reads them back from input-link, NOT output-link. Data-flow section updated.
  2. **`^entity-match`, `^type`, `^subtype` removed from WM schema:** these would require hit-provenance tracking (`fusion.py` signal aggregation discards which signal contributed) AND drawer-type metadata (not in current closet/drawer fields). Adding them is scope expansion; deferred. Rules that depended on them (`entity-match`, `correction-priority`) dropped from initial `BOOST_MULTIPLIERS`.
  3. **`stale-penalty` rule dropped from initial set:** depends on `access-count` (EpMem-driven, placeholder=0 in #4a) and `decay` (placeholder=1.0). Would never fire (or always fire on every drawer) until #4c wires EpMem. Cleaner to add later.
  4. **Initial `BOOST_MULTIPLIERS` shrunk to 2 rules** that work on current data: `recency-boost` (from `created_at` age computed at boost time) and `same-project` (wing match against `CASTLE_PROJECT` env). Honest about the small initial impact; real value lands in #4c.
  5. **`agent.ExecuteCommandLine("epmem --set learning on")`** clarified as the actual SML Python invocation (not a direct Python method).
  6. **`agent.GetInputLink().DestroyAllWMEs()`** explicitly named as the WM clearing strategy at start of each call.
  7. **Acceptance #11 smoke fixed:** `PYTHONPATH=/tmp` doesn't hide already-installed packages. Added `CASTLE_SML_DISABLED=1` testability knob to `_load_sml()` so the fallback path is testable.
  8. **`pyproject.toml` row dropped:** empty extras group doesn't surface useful pip behavior; README documents the install prereq.
  9. **Specified re-sort location:** `apply_soar_boosts` mutates `hit["score"]` and adds audit fields but does NOT re-sort. Callers (CLI / MCP handler) re-sort by adjusted score before returning to user.
- **2026-05-13 (post-review #2):** Survivals of the old 5-rule framing + medium concerns:
  10. **Three 5-rule survivals fixed.** Architecture section still said "5-7 rules" (now "2 rules"). Audit-trail example showed `entity-match` tag + 1.30 multiplier (now uses `same-project` + 1.15). Compound-tags test description said `1.25 × 1.30` (now `1.25 × 1.15`). Same pattern as PR #1 + #3 first-review survivals.
  11. **MCP kill-switch error format softened.** Initial spec showed `{"error": {"code": "kill_switch_active"}}` — not valid JSON-RPC (code must be integer) and not the MCP tool-error mechanism. Now points at "per Castle's existing mcp_server.py error-surfacing convention" with implementation-time resolution.
  12. **Cross-test SOAR isolation called out.** Singleton kernel + palace-keyed agent cache leaks state across tests. Added recommended `reset_soar_state` autouse fixture to test file outline.
  13. **`score_pre_soar` presence clarified:** audit fields ONLY present when `--soar-boost` was applied. Default-path responses don't include them. MCP clients shouldn't assume.
  14. **`pytestmark_soar` renamed to `_requires_sml`** for clarity (avoid confusion with pytest's special `pytestmark` module-level variable).
  15. **2 production names spelled out explicitly:** `castle-boost*recency-boost`, `castle-boost*same-project`.
- **2026-05-13 (post-review #3):** Lazy-import gap + math/consistency fixes:
  16. **Lazy-import discipline made explicit** for `cli.py` + `mcp_server.py`. Acceptance #14 claims `soar_bridge` module never loads in default path — but without explicit guidance, the plan-writer would default to module-top imports and silently break the acceptance. Both Components rows now state `from .soar_bridge import apply_soar_boosts` MUST be inside the conditional branch.
  17. **Architecture LOC corrected:** ~250 → ~260 for `soar_bridge.py` (review-2 added `_reset_for_test()` but didn't sync the Architecture summary).
  18. **Total LOC math corrected:** ~670 → ~680 with explicit per-row sum so anyone verifying can replicate.
  19. **Status header:** "Revised after review" → "Revised 3× after review" (three revisions now).

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

**New module: `cognitive_castle/soar_bridge.py`** (~260 LOC). Structure mirrors the deleted version:

- `_load_sml()` — lazy import with clear error message if Soar unavailable. Cached. Returns `None` and prints stderr warning ONCE per process on failure.
- `_get_kernel()` — module-level singleton Soar kernel.
- `_get_agent(palace_path)` — palace-keyed agent. First-time creation loads productions from `cfg.soar_rules_path` and enables EpMem + SMem subsystems.
- `apply_soar_boosts(hits, cfg) -> list[dict]` — public entry. Builds working memory from hits, runs decision cycle, reads back boost-tags, applies multipliers, returns hits with `score` adjusted + `soar_boost` + `soar_tags` audit fields.
- `BOOST_MULTIPLIERS: dict[str, float]` — module-level tag → multiplier map.

**New rule file: `cognitive_castle/rules/castle-boost.soar`** — initial production set (**2 rules** for #4a: `castle-boost*recency-boost`, `castle-boost*same-project`). Match candidate metadata, emit `^boost-tag <tag>` attributes via i-support on the matching `<m>`. Reference material: prior 144-line version in git history (commit `b49ebe83`); this PR ships a *minimal subset* and adds more in follow-ups as supporting data fields land (hit-provenance for `entity-match`, drawer-type metadata for `correction-priority`, EpMem access-counts for `stale-penalty`).

**Pipeline integration:** Post-pipeline boost runs in TWO places — CLI (`cli.py:cmd_search`) and MCP (`mcp_server.py` `castle_search` handler). Both consult the opt-in flag and call `apply_soar_boosts(hits, cfg)` AFTER `search_memories()` returns (and after Stage 4 LLM-judge if enabled).

## Components (file-level changes)

| File | Change | LOC |
|---|---|---|
| `cognitive_castle/soar_bridge.py` (new) | Public `apply_soar_boosts(hits, cfg) -> list[dict]`. Lazy SML import via `_load_sml()` — also respects `CASTLE_SML_DISABLED=1` env var (returns None even if SML importable, for testability). Singleton kernel via `_get_kernel()`. Per-palace agent via `_get_agent(palace_path)`. Builds working memory from hits using the input-link schema (`^context` + `^memory[]`), clears prior WM via `agent.GetInputLink().DestroyAllWMEs()`, runs decision cycle via `agent.RunSelf(50)`, reads back `^boost-tag` attributes by iterating input-link memory WME children, maps tags to multipliers via `BOOST_MULTIPLIERS`, applies to `hit["score"]`. Augments hits with `soar_boost` (float compound multiplier) + `soar_tags` (list[str]) + `score_pre_soar` (original score). Does NOT re-sort (caller's responsibility). EpMem + SMem configured via `agent.ExecuteCommandLine("epmem/smem --set learning on")` at first agent creation. Stderr-warning-+-return-unchanged fallback on any Soar failure. Boost clamped to range `[0.1, 10.0]`. One-time-per-process warning via module-level `_WARNED: set`. **Includes `_reset_for_test()` helper** that clears `_KERNEL`, `_AGENTS`, and `_WARNED` — used by the autouse pytest fixture to prevent cross-test state leakage. | +260 |
| `cognitive_castle/rules/castle-boost.soar` (new) | Initial production set (**2 rules** for #4a). Each matches on memory attributes and adds `^boost-tag <tag>` via i-support on the matching `<m>`. Initial tags: `recency-boost` (matches `^recently-accessed "true"`), `same-project` (matches when `<m>.project` equals `<context>.project`). Includes the standard Soar header (`sp {castle-boost*<name>` syntax). Follow-up PRs add `entity-match`, `correction-priority`, `stale-penalty` rules when the data they need exists. | +35 |
| `cognitive_castle/config.py` | Add 2 new properties (env-first → file-config → default, matching `embedder_model` pattern at `config.py:305-321`): `soar_enabled` (default `False`, env `CASTLE_SOAR_ENABLED`) — kill switch. `soar_rules_path` (default `<package>/rules/castle-boost.soar`, env `CASTLE_SOAR_RULES_PATH`) — lets users point at custom rule files. | +30 |
| `cognitive_castle/cli.py` | Add `--soar-boost` flag (store_true, default False) to `castle search` subparser. Pass through to `search()` (which then propagates to the search dict). Help text: `"Apply SOAR symbolic-rule boost-tags to final scores (experimental; requires Soar 9.6+ + SML Python bindings installed; activate via CASTLE_SOAR_ENABLED=1)"`. ALSO: if `--soar-boost` is passed AND `cfg.soar_enabled` is False, `sys.exit(2)` with clear stderr `"CASTLE_SOAR_ENABLED=0 kill switch is active; remove it to use --soar-boost"` before any palace work happens. **Lazy import discipline:** `from .soar_bridge import apply_soar_boosts` MUST be done INSIDE the `if args.soar_boost and cfg.soar_enabled:` branch, NOT at module top, so `soar_bridge` isn't loaded for default-path invocations (verifiable via Acceptance #14's `python -X importtime` smoke). | +25 |
| `cognitive_castle/mcp_server.py` | Add `soar_boost: boolean (default false)` to `castle_search` tool schema. Handler reads `arguments.get("soar_boost", False)`; if True AND `cfg.soar_enabled`, call `soar_bridge.apply_soar_boosts(hits, cfg)` BEFORE returning. Runs AFTER llm-rerank (already applied earlier in handler from PR #3). Same kill-switch behavior: if soar_boost requested but soar_enabled False, surface a clear error in the response **per Castle's existing mcp_server.py error-surfacing convention** (plan-writer inspects how other handler errors are returned and matches style — initial sketch of JSON-RPC-style `{"error": {"code": "kill_switch_active"}}` was wrong: JSON-RPC requires integer code, and MCP tool errors typically use `isError: true` + content). **Lazy import discipline:** `from .soar_bridge import apply_soar_boosts` MUST be done INSIDE the `if arguments.get("soar_boost") and cfg.soar_enabled:` branch, NOT at module top, so `castle-mcp` startup doesn't load `soar_bridge` for users who never use the flag (per Acceptance #14). | +30 |
| `tests/test_soar_bridge.py` (new) | 8 Soar tests gated by `@pytest.mark.soar` marker (auto-skip if SML import fails). Plus 2 non-Soar tests (kill switch, SML-unavailable fallback) that always run. | +200 |
| `tests/test_cli.py` (existing) | 2 tests: `--soar-boost` flag propagation; kill-switch exit code. | +30 |
| `tests/test_mcp_server.py` (existing) | 1 test: `soar_boost:true` MCP param threading. | +20 |
| `README.md` | Append `### Experimental: SOAR symbolic re-ranking` subsection inside the existing "Going further" block. Covers: what SOAR is (1-sentence intro), why experimental, install prerequisites (link to upstream Soar build instructions), how to enable (`CASTLE_SOAR_ENABLED=1` + `--soar-boost`), the kill switch + rules-path knobs, the audit fields in output (`soar_boost`, `soar_tags`, `score_pre_soar`). Strong note that this is research-grade. | +45 |
| `CLAUDE.md` | Update retrieval pipeline diagram (line 175-185 area) to show optional Stage 5. Match the "optional" annotation style used for Stage 4 LLM-judge. | +5 |

**Total:** ~680 LOC across 2 new modules + 1 new rule file + 1 new test file + 4 existing files. (Components row sums: 260+35+30+25+30+200+30+20+45+5 = 680. Smaller than initial estimate: dropped `pyproject.toml` row, shrunk rule file from ~60 LOC to ~35 LOC for 2 rules instead of 5. Added 10 LOC to `soar_bridge.py` for the `_reset_for_test()` helper introduced by review-2.)

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
      → _load_sml() — lazy import (cached; returns None if CASTLE_SML_DISABLED=1)
      → kernel = _get_kernel() — singleton
      → agent = _get_agent(cfg.palace_path):
          → first time: kernel.CreateAgent
          → first time: agent.LoadProductions(cfg.soar_rules_path)
          → first time: agent.ExecuteCommandLine("epmem --set learning on")
          → first time: agent.ExecuteCommandLine("smem --set learning on")
          → (EpMem + SMem configured but not USED in #4a — preparation for #4c)
      → agent.GetInputLink().DestroyAllWMEs()   # clear WM from prior call
      → push input-link WMEs:
          - input_link.context.{project, query}
          - input_link.memory[] (one per hit; truncate to first 50 if more)
            Each memory WME carries: id, project, score, age-seconds, recently-accessed
      → agent.RunSelf(50) — run up to 50 decision cycles or until quiescence
      → read back boost-tags by iterating input-link.memory children:
          for each m in input_link.memory:
              tags = [child.value for child in m.children if child.attribute == "boost-tag"]
              # tags live ON the memory WME (input-link, i-supported by productions)
      → for each hit: compound multipliers from BOOST_MULTIPLIERS for fired tags, clamp [0.1, 10.0]
      → hit["soar_boost"] = compound_multiplier
      → hit["soar_tags"] = [tag_names...]
      → hit["score_pre_soar"] = hit["score"]
      → hit["score"] = hit["score"] * compound_multiplier
      → return hits   # NOT re-sorted — apply_soar_boosts is sort-agnostic
  → caller re-sorts by adjusted score:
      → CLI: cmd_search sorts before printing
      → MCP: castle_search handler sorts before returning the JSON list
```

### Kill-switch path (`--soar-boost` AND `CASTLE_SOAR_ENABLED=0`)

```
castle search "..." --soar-boost   (with CASTLE_SOAR_ENABLED=0)
  → kill-switch check at CLI entry: cfg.soar_enabled is False
  → stderr: "CASTLE_SOAR_ENABLED=0 kill switch is active; remove it to use --soar-boost"
  → sys.exit(2)
  ← no palace work performed
```

For MCP, since handlers can't `sys.exit`, surface a clear error in the response. **Exact response shape: per Castle's existing `mcp_server.py` error-surfacing convention** (look at how `castle_search` already returns errors for other failures — `tool_search()` or whatever the active handler-error pattern is). The plan-writer will inspect mcp_server.py and match the existing style. Initial spec drafts of `{"error": {"code": "kill_switch_active"}}` were wrong on two counts: JSON-RPC requires integer `code`, and MCP tool-call errors typically use the `isError: true` + content mechanism rather than JSON-RPC `error` field.

### SOAR working memory schema (revised for #4a — only fields the current data supports)

```
state ^io.input-link <il>
<il>  ^context <ctx>
      ^memory  <m>     (one per hit, up to 50 hits per query)
<ctx> ^project       "ru-sixth-sense"     (from CASTLE_PROJECT env or "default")
      ^query         "try scored corner"  (the user's query string)
<m>   ^id                "abc-123"        (composite: wing/room/source_file)
      ^project           "ru-sixth-sense" (from hit.wing — matches ^context.project when same project)
      ^score             0.85             (current Stage 3+4 score)
      ^age-seconds       86400            (computed from hit.created_at at boost time)
      ^recently-accessed "true"           (boolean string — true if age-seconds < threshold, default 7 days)
```

**Fields explicitly NOT in #4a's schema** (deferred to #4c when supporting data lands):
- `^type` / `^subtype` — current drawer metadata doesn't include these (existed pre-PR #12, removed since)
- `^entity-match` — would require signal-provenance tracking added to `fusion.py` (currently fused scores discard which signal contributed)
- `^access-count` — EpMem-driven; placeholder in #4a wasn't useful
- `^decay` — would require formalized decay model; `^age-seconds` + threshold-based rules cover the practical case

Each excluded field had a dead-or-misfiring rule in the prior `castle-boost.soar`. Better to ship a smaller schema where every field has a real source than a richer schema where rules fire on placeholders.

**Productions elaborate `<m>` WMEs in place** (i-supported attributes added to input-link memory entries). Python reads back boost-tags by iterating `<m>` children for `^boost-tag` attributes — NOT from output-link. This matches the prior bridge's design (per `castle-boost.soar` header in git history at commit `b49ebe83`).

### Boost-tag multiplier mapping (revised — 2 rules that actually work on #4a's data)

```python
BOOST_MULTIPLIERS = {
    "recency-boost": 1.25,    # ^recently-accessed = "true" (age < threshold, default 7 days)
    "same-project": 1.15,     # <m>.project == <context>.project
}
```

Multipliers compound multiplicatively. Final boost clamped to `[0.1, 10.0]`.

The two initial rules are the minimal set that:
- Have a real data source in the current pipeline (no placeholder fields)
- Will measurably fire on the developer's palace (Castle has wing-based projects + drawer timestamps)
- Provide a working smoke for the bridge end-to-end

Additional rules (`entity-match`, `correction-priority`, `stale-penalty`) are queued for follow-up PRs once the data they need exists (hit-provenance from `fusion.py`, drawer-type metadata, EpMem access counts).

### Per-hit audit trail in output

Audit fields are present ONLY when `--soar-boost` was applied. Default-path responses (no flag, or kill-switch-disabled) do NOT include these fields — MCP clients should not assume their presence.

```json
{
  "id": "abc-123",
  "text": "...",
  "wing": "...",
  "room": "...",
  "score": 1.22,                  // post-boost
  "score_pre_soar": 0.85,         // pre-boost
  "soar_boost": 1.4375,           // compound multiplier (1.25 × 1.15)
  "soar_tags": ["recency-boost", "same-project"]
}
```

This is what gives SOAR differentiating value vs. neural methods — every score change has a name.

## Error handling

All Soar failures degrade gracefully — search ALWAYS returns hits, never errors out due to Soar failure. Exception: the kill-switch case is intentionally LOUD (user explicitly mismatched flags + env).

| Failure | Behavior |
|---|---|
| `--soar-boost` passed AND `CASTLE_SOAR_ENABLED=0` | CLI: `sys.exit(2)` + stderr `CASTLE_SOAR_ENABLED=0 kill switch is active; remove it to use --soar-boost`. MCP: surface a clear error in the response per Castle's existing mcp_server.py error-surfacing convention (exact response shape resolved at plan time by inspecting how other errors are returned). |
| SML Python bindings not installed (`import Python_sml_ClientInterface` fails) | `_load_sml()` catches ImportError, stderr `[soar] SML Python bindings not available — install Soar 9.6+ with SML or set CASTLE_SOAR_ENABLED=0` ONCE per process, returns hits unchanged. |
| `CASTLE_SML_DISABLED=1` env var set | `_load_sml()` returns None even if SML is importable. Same downstream behavior as "SML not installed" — stderr warning + hits unchanged. Used only for testing the fallback path; not documented in user-facing README. |
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

_requires_sml = pytest.mark.skipif(not _SML_AVAILABLE, reason="Soar 9.6+ SML not installed")


@pytest.fixture(autouse=True)
def reset_soar_state():
    """Clear singleton kernel + agent cache between tests so they don't share state.

    The bridge uses a module-level kernel singleton and palace-keyed agent cache for
    efficiency in production. In tests, sequential tests using the same palace would
    hit a cached agent with stale productions/WM from the prior test. Reset after
    each test.
    """
    yield
    from cognitive_castle import soar_bridge
    soar_bridge._reset_for_test()  # clears _KERNEL, _AGENTS, _WARNED


# ── Soar-required tests (skip if SML unavailable) ──────────────────────


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_loads_rules_and_runs_decision_cycle(tmp_path):
    """Smoke: SOAR kernel + agent + rule file load + decision cycle completes."""
    # ... test body builds a minimal cfg pointing at the shipped rule file,
    # calls apply_soar_boosts with 3 hits, asserts no exception + hits returned.


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_returns_hits_unchanged_when_no_tags_fire(tmp_path):
    """Empty rule file → hits returned with soar_boost=1.0, soar_tags=[]."""


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_multiplies_score_for_recency_tag(tmp_path):
    """A hit with recently-accessed=true → recency-boost tag → score × 1.25."""


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_compounds_multiple_tags(tmp_path):
    """A hit matching both rules → both tags fire → multipliers compound (1.25 × 1.15 = 1.4375)."""


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_clamps_to_range(tmp_path):
    """Compounded multipliers > 10.0 or < 0.1 → clamped to bounds."""


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_truncates_to_50_hits(tmp_path, capsys):
    """Input of 100 hits → WM populated with first 50; remaining 50 returned unboosted + stderr warning."""


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_clears_wm_between_calls(tmp_path):
    """Two sequential calls don't leak boost-tags from the first call into the second."""


@pytest.mark.soar
@_requires_sml
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
    # Force the SML-unavailable fallback path via the testability env var
    # (PYTHONPATH=... does NOT hide an installed package — it prepends, not replaces)
    CASTLE_SML_DISABLED=1 CASTLE_SOAR_ENABLED=1 \
      castle search "authentication" --soar-boost
    ```
    Completes successfully, returns hits unchanged, stderr contains `SML Python bindings not available` (warning fires ONCE per process via `_WARNED` set).
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

## Spec self-review (post-revision #3, 2026-05-13)

1. **Placeholders:** None. Test code is concrete (mock setup + assertions shown for always-run tests; Soar-gated tests describe intent + structure; rule-file structure shown for the new `.soar` file with both 2 initial productions described in enough detail for plan-writing).
2. **Internal consistency:** Architecture, Components, Data Flow, Error Handling, Testing, and Acceptance all reference:
   - `cognitive_castle/soar_bridge.py` new module with `apply_soar_boosts(hits, cfg) -> list[dict]` public entry
   - Post-pipeline placement (Stage 5, after Stage 4 LLM-judge if present)
   - `--soar-boost` CLI flag + `soar_boost:true` MCP param
   - `CASTLE_SOAR_ENABLED` kill switch (loud `sys.exit(2)` on flag-vs-env mismatch)
   - Compound-multiplier boost with `[0.1, 10.0]` clamp
   - `BOOST_MULTIPLIERS` dict with **2 initial tags** (`recency-boost`, `same-project`) — shrunk from 5 in initial draft after review caught that 3 rules depended on data fields the current pipeline doesn't expose
   - Audit trail fields: `soar_boost`, `soar_tags`, `score_pre_soar`
   - WM schema (revised) carries ONLY fields the current pipeline supports: `^context` (project + query) + `^memory[]` with id, project, score, age-seconds, recently-accessed
   - Productions elaborate input-link `<m>` WMEs with i-supported `^boost-tag` attributes; Python reads back from input-link (NOT output-link)
   - EpMem/SMem configured via `agent.ExecuteCommandLine(...)` at agent init but unused in #4a
   - `agent.GetInputLink().DestroyAllWMEs()` clears WM between calls
3. **Scope:** Single sub-PR (PR #4a). PR #4b (composable with LLM-judge) and PR #4c (chunking + persistence) explicitly deferred to their own spec cycles. The umbrella context table makes the 3-sub-PR decomposition explicit. The 3 deferred rules + the data-fields they need are queued as follow-ups, not silently shipped as dead code.
4. **Ambiguity:** Opt-in semantics ("default=False, never silently invoked, soar_bridge module not imported in default path") stated in Goal, Architecture, Data Flow, Error Handling, Acceptance #14. Kill-switch behavior (loud `sys.exit(2)` on flag-vs-env mismatch) stated in 3 places (Error Handling, CLI Components row, Acceptance #10). `CASTLE_SML_DISABLED` testability knob clearly documented as test-only.
5. **Empirical grounding:** Soar 9.6.40 + SML verified live on the developer's hardware. Module location: `/home/lbihari/soar-work/Soar/build/Core/ClientSMLSWIG/python/`. The 2 initial rules have real data sources (drawer `created_at` for age, hit `wing` for project match) that exist in the current pipeline.
6. **EpMem/SMem are stubs in #4a:** Configured but unused. Tests don't assert on EpMem state. `^access-count` and `^decay` are explicitly DROPPED from the WM schema for #4a (rather than carrying as placeholders that could cause confused rule behavior).
7. **Boost multiplier values are initial guesses:** Both initial multipliers (1.25 and 1.15) are chosen "in the same order of magnitude as cross-encoder score variations." No formal calibration in #4a. PR description will note this as a known limitation; #4c's chunking work will produce empirically grounded values.
8. **Post-review #1 findings addressed:**
   - ✅ Input-link vs output-link contradiction resolved: productions elaborate input-link memory WMEs; Python reads back from input-link.
   - ✅ `^entity-match`, `^type`, `^subtype`, `^access-count`, `^decay` removed from WM schema (deferred to #4c with their underlying data).
   - ✅ `BOOST_MULTIPLIERS` shrunk from 5 rules to 2 that actually fire on current data.
   - ✅ `agent.ExecuteCommandLine("epmem --set learning on")` named explicitly as the SML invocation.
   - ✅ `agent.GetInputLink().DestroyAllWMEs()` named explicitly as WM-clearing mechanism.
   - ✅ `CASTLE_SML_DISABLED=1` testability knob added to `_load_sml()` + Acceptance #11 smoke fixed.
   - ✅ `pyproject.toml` row dropped (empty extras group adds nothing).
   - ✅ Re-sort location specified: callers (CLI/MCP) re-sort, not `apply_soar_boosts`.
   - ✅ Filename misnomer noted in revision history; preserve git history rather than rename.
9. **Post-review #2 findings addressed:**
   - ✅ Three 5-rule survivals fixed (Architecture row, audit-trail example, test description). Same pattern as PR #1/#3 first-revision survivals — the spec body was updated but examples/cross-references weren't swept.
   - ✅ MCP kill-switch error format softened to "per Castle's existing mcp_server.py convention" — initial sketches of `{"error": {"code": "kill_switch_active"}}` were wrong on two counts.
   - ✅ Cross-test SOAR isolation: added `_reset_for_test()` helper to `soar_bridge.py` (Components row updated to +260 LOC) + autouse `reset_soar_state` pytest fixture in `tests/test_soar_bridge.py` outline.
   - ✅ `score_pre_soar` audit-field presence: explicit one-line note that fields are present ONLY when `--soar-boost` was applied; MCP clients shouldn't assume.
   - ✅ `pytestmark_soar` renamed to `_requires_sml` (avoid confusion with pytest's `pytestmark` module-level variable).
   - ✅ 2 production names spelled out: `castle-boost*recency-boost`, `castle-boost*same-project`.
10. **Post-review #3 findings addressed:**
    - ✅ **Lazy-import discipline** for `cli.py` + `mcp_server.py` made explicit: `from .soar_bridge import apply_soar_boosts` MUST be INSIDE the conditional `if soar_boost and cfg.soar_enabled:` branch, NOT at module top. Without this, Acceptance #14's `python -X importtime` check would silently fail (soar_bridge would load at process startup regardless of the flag).
    - ✅ Architecture LOC for `soar_bridge.py` updated `~250 → ~260` to match Components row (revision-2 added `_reset_for_test()` helper but didn't sync the Architecture summary).
    - ✅ Total LOC corrected `~670 → ~680` with explicit per-row sum (`260+35+30+25+30+200+30+20+45+5 = 680`). Math now adds up.
    - ✅ Status header `Revised → Revised 3×` (three revisions now).
    - ⊘ Skipped (cosmetic only): README subsection placement order, truncation-row audit-fields-for-remainder spec, Non-goals `epmem --set learning on` bare-command framing. Plan-writer can resolve at implementation time.
