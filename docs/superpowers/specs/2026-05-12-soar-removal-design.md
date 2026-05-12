# SOAR Removal — Design

**Date:** 2026-05-12
**Branch target:** develop
**Scope:** Delete the SOAR cognitive-architecture integration entirely. 5 file deletions + 1 directory deletion + 1 file edit (mcp_server.py) + 1 file edit (README.md acknowledgements). No production code changes outside `mcp_server.py`. ~500 line net deletion. First PR of a 4-PR "cleanup leftovers + dead code" series (PR #A; #B mempalace production fixes, #C mempalace tests sweep, #D mempalace docs sweep follow).

## Background

Cognitive Castle has a SOAR cognitive-architecture integration that's **dead code in practice**:

- `cognitive_castle/soar_bridge.py` (10 KB) wraps SOAR's SML C++ library and exposes `run_soar_reasoning()` + `apply_soar_boosts()`.
- `cognitive_castle/rules/*.soar` (3 production rule files: castle-boost, castle-chunk, castle-impasse) hold the rule logic.
- `cognitive_castle/mcp_server.py:411-458` calls `apply_soar_boosts()` after every search, wrapped in try/except.
- `tests/test_soar_integration.py` exercises the bridge.

Runtime reality observed in this session:
- `/home/lbihari/.echelon/soar/` is **empty** (0 bytes). SML bindings aren't installed.
- Every `_load_sml()` call raises `ImportError: SOAR SML bindings not found`.
- The try/except in `apply_soar_boosts()` swallows it; logs "SOAR reasoning failed — returning un-boosted scores".
- **Net effect**: every search call sets `soar_boost=1.0` and `soar_score == similarity`. SOAR contributes zero ranking signal today.

The cross-encoder reranker (just made robust to CUDA OOM in PR #12) is the only re-ranking layer actually doing work. SOAR was always the "explainable rule-based boost" layer, but without the SML library it's not doing anything, and even if installed, it's not clear it adds value over the cross-encoder.

The user decided **remove now** rather than "install + benchmark first". Reasoning: cross-encoder is enough; SOAR's install friction + niche maintenance burden outweighs the speculative gain.

## Goals

1. Remove all SOAR code from the repo: source modules, rule files, tests.
2. Remove the single integration point in `mcp_server.py`.
3. Update README acknowledgements to no longer credit SOAR — replace with accurate credit to the current architecture (3-stage retrieval pipeline).
4. Search results no longer include `soar_boost`, `soar_score`, or `soar_boosted` fields (they were inert anyway).
5. No regressions in the focused test suite (excluding the deleted `test_soar_integration.py`).
6. Castle MCP and the CLI `castle search` continue to work end-to-end.

## Non-goals

- Mempalace cleanup — separate PRs #B, #C, #D, designed later.
- Removing the cross-encoder reranker. (It's the active re-ranking layer; only SOAR goes.)
- Touching CHANGELOG.md historical entries that reference SOAR (preserve history).
- Touching `docs/superpowers/specs/` or `docs/superpowers/plans/` (frozen historical context).
- Replacing SOAR with another rule-based system (e.g., a Python rules engine). Don't add complexity to compensate for the removal.
- Re-litigating the install-+-benchmark vs remove decision (user already decided remove).
- Restoring SOAR via a different mechanism (e.g., LLM-as-judge re-ranker). Defer that question.
- Preserving dead infrastructure on the hope it might be useful later. If symbolic-reasoning capability becomes a stated goal, build it deliberately as a new project — a small Python rules engine, an LLM-as-judge layer, or a reinstalled-and-benchmarked SOAR. Don't keep this code "just in case."

## Source of truth

- All identified SOAR-touching files: `cognitive_castle/soar_bridge.py`, `cognitive_castle/rules/*.soar` (3 files), `cognitive_castle/mcp_server.py` (lines 411-458), `tests/test_soar_integration.py`, `README.md` (one Acknowledgements line).
- Confirmed by `grep -rinE "soar|SOAR|Soar" cognitive_castle/ tests/ README.md MISSION.md ROADMAP.md CHANGELOG.md AGENTS.md CONTRIBUTING.md SECURITY.md` during the brainstorming session. CHANGELOG/MISSION/ROADMAP/AGENTS/CONTRIBUTING/SECURITY have zero SOAR refs.
- Decision locked: remove now (no install-+-benchmark path).

## File-by-file change list

### Deleted

| Path | Lines | Reason |
|---|---|---|
| `cognitive_castle/soar_bridge.py` | ~270 | SML wrapper — dead without bindings |
| `cognitive_castle/rules/castle-boost.soar` | ~190 | SOAR production rule file |
| `cognitive_castle/rules/castle-chunk.soar` | ~70 | SOAR production rule file |
| `cognitive_castle/rules/castle-impasse.soar` | ~80 | SOAR production rule file |
| `cognitive_castle/rules/` (directory) | — | Empty after the 3 rule files are deleted |
| `tests/test_soar_integration.py` | ~210 | Tests for the deleted module |

Total: ~820 lines + 1 directory.

### Modified

#### `cognitive_castle/mcp_server.py`

Delete the entire `# ── SOAR re-ranking ─` block from line 411 through line 458. Concrete span:

```python
    # ── SOAR re-ranking ────────────────────────────────────────────────────
    # Apply production-rule boosts (correction > procedural > stale, etc.).
    # Runs only when results are present and SOAR bindings are available.
    hits = result.get("results")
    if hits:
        try:
            from .soar_bridge import apply_soar_boosts as _soar_boost
            project_id = os.environ.get("CASTLE_PROJECT", "default")
            def _soar_id(h: dict) -> str:
                return f"{h.get('wing','')}/{h.get('room','')}/{h.get('source_file','?')}"

            soar_mems = []
            for h in hits:
                meta = h.get("metadata") or {}
                wing_name = h.get("wing", "")
                if "user" in wing_name:
                    mem_type = "user"
                elif wing_name in ("wing_agent", "wing_ai_research"):
                    mem_type = "procedural"
                else:
                    mem_type = meta.get("type", "semantic")
                soar_mems.append({
                    "id": _soar_id(h),
                    "type": mem_type,
                    "subtype": meta.get("subtype", ""),
                    "project_id": meta.get("project_id", ""),
                    "_score": float(h.get("similarity") or 0.0),
                    "decay_score": meta.get("decay_score", 1.0),
                    "access_count": meta.get("access_count", 0),
                    "last_accessed_at": meta.get("last_accessed_at"),
                })
            soar_mems = _soar_boost(soar_mems, sanitized["clean_query"], project_id)
            soar_boost_val = {m["id"]: m.get("_soar_boost", 1.0) for m in soar_mems}
            for h in hits:
                boost = float(soar_boost_val.get(_soar_id(h), 1.0))
                h["soar_boost"] = round(boost, 3)
                h["soar_score"] = round(float(h.get("similarity") or 0.0) * boost, 4)
            hits.sort(key=lambda h: h.get("soar_score", float(h.get("similarity") or 0.0)), reverse=True)
            result["soar_boosted"] = True
        except Exception as _soar_err:
            logger.debug("SOAR boost skipped: %s", _soar_err)
```

Replace with: nothing. The result dict is returned without SOAR fields. Hits stay in their pre-SOAR order (already cross-encoder reranked upstream).

API impact:
- `soar_boost` field no longer present in any hit
- `soar_score` field no longer present in any hit
- `soar_boosted` top-level field no longer present in result

Since these were always inert (boost=1.0, soar_score == similarity), no realistic consumer depends on them. Document in PR body.

#### `README.md`

The Acknowledgements section currently says:

> Cognitive Castle is a fork and continuation of the MemPalace project, re-architected around LanceDB and the SOAR cognitive-architecture heuristics. Original benchmark methodology and "wings/rooms/drawers" naming preserved with credit to the upstream authors.

Replace the SOAR clause with accurate credit to the actual current architecture:

> Cognitive Castle is a fork and continuation of the MemPalace project, re-architected around LanceDB and a 3-stage retrieval pipeline (dense + Tantivy FTS + knowledge-graph traversal, fused via weighted RRF + recency, then cross-encoder reranked). Original benchmark methodology and "wings/rooms/drawers" naming preserved with credit to the upstream authors.

### Test-suite housekeeping

Beyond deleting `tests/test_soar_integration.py`, run a grep before commit to verify no other test file asserts SOAR fields:

```bash
grep -rinE "soar_boost|soar_score|soar_boosted" tests/
```

If matches appear (e.g., in `test_mcp_server.py` or `test_searcher.py`), strip those assertions surgically — but don't delete entire tests over them. The expected output is zero matches outside the soon-to-be-deleted file.

### Untouched

- All other production code (`cognitive_castle/backends/`, `cognitive_castle/searcher.py`, `cognitive_castle/reranker.py`, etc.) — SOAR was an additive layer, not a coupled component.
- CHANGELOG.md — historical entries about SOAR may exist; preserve as historical context.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` — frozen history.
- `cognitive_castle/__init__.py` — does not import soar_bridge directly (only mcp_server.py imports it, and only inside the try/except).

## Testing strategy

1. **File-deletion sanity:**
   ```bash
   ls cognitive_castle/soar_bridge.py cognitive_castle/rules/ tests/test_soar_integration.py 2>&1
   ```
   Expected: all "No such file or directory".

2. **SOAR refs gone from production code:**
   ```bash
   grep -ri "soar\|Soar\|SOAR" cognitive_castle/ --include="*.py"
   ```
   Expected: zero matches.

3. **SOAR refs gone from tests:**
   ```bash
   grep -rinE "soar_boost|soar_score|soar_boosted|soar_bridge" tests/
   ```
   Expected: zero matches.

4. **Focused suite still green relative to baseline:**
   ```bash
   pytest tests/ --ignore=tests/benchmarks -q --tb=no 2>&1 | tail -3
   ```
   Expected: failed count ≤ pre-PR baseline + 0. The `test_soar_integration.py` tests are no longer in the suite (intentional). If any other test asserted SOAR fields, that test should have been surgically updated, not left to fail.

5. **MCP tool call still works:**
   ```bash
   cat > /tmp/mcp-smoke.jsonl <<'EOF'
   {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"1.0"}}}
   {"jsonrpc":"2.0","method":"notifications/initialized"}
   {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"castle_search","arguments":{"query":"embedder decision","limit":1}}}
   EOF
   cat /tmp/mcp-smoke.jsonl | timeout 60 castle-mcp 2>/dev/null | tail -1
   ```
   Expected: a valid search result JSON (no `soar_*` fields). Whether `soar_boosted` flag is present in the result top-level is the diagnostic — it should be **absent**.

6. **CLI smoke:**
   ```bash
   castle search "embedder decision" --results 1 2>&1 | head -20
   ```
   Expected: a result with `score=` line, no `soar_*` references anywhere in the output.

## Risk

- **Low for production behavior.** SOAR was always a silent no-op. Removing inert code can't regress anything because nothing was producing signal.
- **Low for API compat.** The deleted fields (`soar_boost`, `soar_score`, `soar_boosted`) were always `1.0` / equal to `similarity` / `True`-but-from-failed-boost. No useful information is being lost.
- **Test breakage** if any test file outside `test_soar_integration.py` asserts SOAR fields — caught by Step 3 of the testing strategy before commit.
- **Doc drift** if other docs (beyond README) reference SOAR — caught by a grep during implementation. Brainstorm grep showed zero matches in top-level docs (MISSION/ROADMAP/CHANGELOG/AGENTS/CONTRIBUTING/SECURITY).
- **Conceptual: we are closing a bridge, not just deleting dead code.** `soar_bridge.py` is named accurately — it was designed to bridge symbolic reasoning (SOAR production rules) to statistical ranking (cosine similarity). It also bridged retrieval to *action* signals (`widen-search`, `chunk-candidate` actions returned by `run_soar_reasoning`). Both halves of the bridge were never operational on this machine: the symbolic side never loaded because SML bindings were missing, and the action side was unwired even when the symbolic side worked — `apply_soar_boosts` discards the `actions` list before returning to callers. We are removing a conceptual layer that *could* have done something useful, not one that *was* doing something useful. If a future deliberate effort wants symbolic reasoning, see the Non-goals section above for cleaner replacement paths.

## Acceptance criteria

1. `cognitive_castle/soar_bridge.py` deleted.
2. `cognitive_castle/rules/` directory deleted (with its 3 `.soar` rule files).
3. `tests/test_soar_integration.py` deleted.
4. `grep -ri "soar\|Soar\|SOAR" cognitive_castle/ --include="*.py"` returns 0 matches.
5. `grep -rinE "soar_boost|soar_score|soar_boosted|soar_bridge" tests/` returns 0 matches.
6. `mcp_server.py` no longer imports `soar_bridge` and no longer adds `soar_boost`/`soar_score`/`soar_boosted` fields to search results.
7. `README.md` Acknowledgements rephrased (no SOAR mention; replacement preserves the LanceDB + retrieval-pipeline credit per Section "Modified > README.md").
8. Focused suite: failed count ≤ pre-PR baseline (where baseline excludes the `test_soar_integration.py` tests since they're intentionally deleted).
9. `castle search "query"` end-to-end smoke passes — returns valid results without `soar_*` fields.
10. JSON-RPC `tools/call castle_search` smoke passes — returns valid results, no `soar_*` fields, no `soar_boosted` flag.
11. No production code outside `cognitive_castle/mcp_server.py` and the soon-deleted `cognitive_castle/soar_bridge.py` is modified.
12. PR commit count ≤ 2 (deletion + edits in one commit; second commit reserved for any AC fix).
