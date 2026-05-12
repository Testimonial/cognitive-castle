# SOAR Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the SOAR cognitive-architecture integration per spec `4de9c35e` — 5 files + 1 directory deleted, the 48-line SOAR re-ranking block in `mcp_server.py` removed, and the README acknowledgements rephrased. ~820 line net deletion, no production code changes outside `mcp_server.py`.

**Architecture:** Two-task plan. Task 1 (sonnet) does the deletions and edits in one branch + commit. Task 2 (haiku) verifies acceptance criteria, pushes, opens the PR, smokes end-to-end. The cross-encoder reranker (PR #12) is the active re-ranking layer; SOAR was always a silent no-op because the SML bindings were never installed.

**Tech Stack:** No new deps. Pure Python deletions + small markdown edit.

---

## File structure

Deleted in this PR (5 files + 1 directory):
- `cognitive_castle/soar_bridge.py` (~270 lines)
- `cognitive_castle/rules/castle-boost.soar` (~190 lines)
- `cognitive_castle/rules/castle-chunk.soar` (~70 lines)
- `cognitive_castle/rules/castle-impasse.soar` (~80 lines)
- `cognitive_castle/rules/` (directory, empty after the 3 rule files go)
- `tests/test_soar_integration.py` (~210 lines)

Modified:
- `cognitive_castle/mcp_server.py` — delete lines 411-458 (the `# ── SOAR re-ranking ─` block)
- `README.md` — Acknowledgements section: replace SOAR clause with the actual current architecture

Untouched:
- All other production code (`cognitive_castle/backends/`, `searcher.py`, `reranker.py`, etc.)
- CHANGELOG.md historical entries
- `docs/superpowers/specs/` and `docs/superpowers/plans/` (frozen history)
- All tests except the deleted `test_soar_integration.py` and any tests that need surgical SOAR-field assertion removal (caught in Task 2)

Reference (read but don't modify):
- `docs/superpowers/specs/2026-05-12-soar-removal-design.md` (commit `4de9c35e`) — source of truth

---

## Task 1: Branch + delete SOAR + edit mcp_server.py + edit README

**Files:**
- Create branch: `feat/soar-removal` from `develop`
- Delete: `cognitive_castle/soar_bridge.py`
- Delete: `cognitive_castle/rules/` (recursive)
- Delete: `tests/test_soar_integration.py`
- Modify: `cognitive_castle/mcp_server.py` (lines 411-458)
- Modify: `README.md` (Acknowledgements section)

- [ ] **Step 1: Read the spec**

```bash
cat docs/superpowers/specs/2026-05-12-soar-removal-design.md
```

Pay attention to: the verbatim deletion span in `mcp_server.py` (lines 411-458 — full block shown in the spec), the verbatim README replacement text in section "Modified > README.md", and the 12 acceptance criteria.

- [ ] **Step 2: Create the feature branch**

```bash
git checkout develop
git pull origin develop
git checkout -b feat/soar-removal
git log --oneline -3
```

Expected: clean tree on `feat/soar-removal`, recent commits include `4de9c35e` (spec refine) and `cdc5852d` (spec initial).

- [ ] **Step 3: Delete the 5 files + 1 directory**

```bash
git rm cognitive_castle/soar_bridge.py
git rm -r cognitive_castle/rules/
git rm tests/test_soar_integration.py
```

Verify:

```bash
ls cognitive_castle/soar_bridge.py cognitive_castle/rules/ tests/test_soar_integration.py 2>&1
```

Expected: all "No such file or directory".

- [ ] **Step 4: Remove the SOAR re-ranking block from `mcp_server.py`**

Use the `Read` tool to inspect lines 405-465 of `cognitive_castle/mcp_server.py`. Confirm the block bounded by `# ── SOAR re-ranking ─` and the trailing `except Exception as _soar_err:` / `logger.debug("SOAR boost skipped: %s", _soar_err)` matches the spec.

Use the `Edit` tool to remove the full block. The exact `old_string` to remove (verify the indentation matches the file):

```python
    # ── SOAR re-ranking ────────────────────────────────────────────────────
    # Apply production-rule boosts (correction > procedural > stale, etc.).
    # Runs only when results are present and SOAR bindings are available.
    hits = result.get("results")
    if hits:
        try:
            from .soar_bridge import apply_soar_boosts as _soar_boost
            project_id = os.environ.get("CASTLE_PROJECT", "default")
            # Composite id avoids collisions when two hits share the same
            # basename from different directories (e.g. project-a/auth.md
            # and project-b/auth.md both appear as "auth.md" after stripping).
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
                # soar_score = similarity × boost — used for ranking only.
                # similarity is preserved unchanged so callers see the raw
                # cosine value; soar_score reflects SOAR re-ranking priority.
                h["soar_score"] = round(float(h.get("similarity") or 0.0) * boost, 4)
            hits.sort(key=lambda h: h.get("soar_score", float(h.get("similarity") or 0.0)), reverse=True)
            result["soar_boosted"] = True
        except Exception as _soar_err:
            logger.debug("SOAR boost skipped: %s", _soar_err)
```

`new_string` = `""` (empty — the block is removed entirely, leaving a clean gap between the surrounding code).

After editing, verify:

```bash
grep -n "soar\|SOAR\|Soar" cognitive_castle/mcp_server.py
```

Expected: zero matches.

- [ ] **Step 5: Check for unused imports in `mcp_server.py`**

The SOAR block referenced `os` (for `os.environ.get`) and `logger`. Both are likely used elsewhere in the file. Run:

```bash
ruff check cognitive_castle/mcp_server.py
```

Fix any `F401` (unused import) warnings that surface from the block removal. Likely none — `os` and `logger` should still be needed by other code in the file.

- [ ] **Step 6: Update `README.md` Acknowledgements**

Use the `Read` tool to find the Acknowledgements section (search for `## Acknowledgements` near the bottom). Use the `Edit` tool to replace the current line:

Current text:
```
Cognitive Castle is a fork and continuation of the MemPalace project,
re-architected around LanceDB and the SOAR cognitive-architecture
heuristics. Original benchmark methodology and "wings/rooms/drawers"
naming preserved with credit to the upstream authors.
```

Replacement (verbatim from the spec):
```
Cognitive Castle is a fork and continuation of the MemPalace project,
re-architected around LanceDB and a 3-stage retrieval pipeline (dense +
Tantivy FTS + knowledge-graph traversal, fused via weighted RRF +
recency, then cross-encoder reranked). Original benchmark methodology
and "wings/rooms/drawers" naming preserved with credit to the upstream
authors.
```

After editing, verify:

```bash
grep -n "soar\|SOAR\|Soar" README.md
```

Expected: zero matches.

- [ ] **Step 7: Confirm grep across production code**

```bash
grep -ri "soar\|Soar\|SOAR" cognitive_castle/ --include="*.py" 2>&1
```

Expected: zero matches. If non-zero, inspect and remove (the only remaining file that could have refs is `mcp_server.py`; any stale comment should be cleaned).

- [ ] **Step 8: Quick test run to catch broken imports**

```bash
pytest tests/test_mcp_server.py tests/test_searcher.py -q --tb=line 2>&1 | tail -10
```

Expected: tests still pass (or fail for pre-existing reasons unrelated to SOAR). If any test fails with `ImportError: ... soar_bridge ...` or `KeyError: 'soar_boost'`, that test asserts SOAR fields and needs surgical fix in Task 2.

- [ ] **Step 9: Commit**

```bash
git add cognitive_castle/ tests/ README.md
git commit -m "$(cat <<'EOF'
feat: remove SOAR cognitive-architecture integration (PR #A of cleanup series)

SOAR was dead code in practice — SML bindings missing from
~/.echelon/soar/, every _load_sml() raised ImportError,
apply_soar_boosts() swallowed it. Cross-encoder reranker (PR #12) is
the active re-ranking layer.

Per spec docs/superpowers/specs/2026-05-12-soar-removal-design.md
(commit 4de9c35e):

- Deleted cognitive_castle/soar_bridge.py (~270 lines)
- Deleted cognitive_castle/rules/{castle-boost,castle-chunk,castle-impasse}.soar
- Deleted cognitive_castle/rules/ directory
- Deleted tests/test_soar_integration.py (~210 lines)
- Removed 48-line SOAR re-ranking block from cognitive_castle/mcp_server.py
- Updated README.md Acknowledgements: credit the actual current
  architecture (3-stage retrieval pipeline) instead of SOAR

API impact: castle_search MCP tool results no longer include
soar_boost, soar_score, or soar_boosted fields. These were always
inert (boost=1.0, soar_score == similarity) because the SML import
always failed.

First PR of a 4-PR cleanup series. Mempalace cleanup follows in #B-D.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 10: Report ready for Task 2**

Report:
- Branch: `feat/soar-removal`
- Commit SHA
- Files deleted (6 items), files modified (2)
- README grep returns 0 SOAR matches
- mcp_server.py grep returns 0 SOAR matches
- Test impact: whether any non-deleted test broke (defer fix to Task 2 or handle now)
- Next: Task 2 runs all ACs

---

## Task 2: Verify ACs + handle test fallout + push + open PR

**Files:**
- Read-only verification, except for surgical edits if any non-deleted test asserts SOAR fields.

- [ ] **Step 1: AC1-AC3 — deletions exist**

```bash
ls cognitive_castle/soar_bridge.py cognitive_castle/rules/ tests/test_soar_integration.py 2>&1
```

Expected: all three "No such file or directory". Otherwise FAIL.

- [ ] **Step 2: AC4 — no SOAR refs in production code**

```bash
grep -ri "soar\|Soar\|SOAR" cognitive_castle/ --include="*.py" 2>&1 | head -5
```

Expected: zero matches. If non-zero, list them and fix the underlying issue.

- [ ] **Step 3: AC5 — no SOAR field refs in tests**

```bash
grep -rinE "soar_boost|soar_score|soar_boosted|soar_bridge" tests/ 2>&1 | head -10
```

Expected: zero matches. If matches appear (most likely candidates: `test_mcp_server.py`, `test_searcher.py`), do surgical removal:

For each match, read the surrounding test and decide:
- If the assertion is `assert "soar_boost" in result` or similar field-presence check → remove that assertion line
- If the test's body relied on SOAR-boosted ordering → either remove the ordering-specific assertion or skip the test with a comment
- If the test sets up SOAR fixtures → remove the fixture setup
- DO NOT delete entire tests over a single SOAR assertion — surgically remove only the SOAR-touching lines

Run the affected tests again after surgical fixes:

```bash
pytest tests/test_mcp_server.py tests/test_searcher.py -q --tb=line 2>&1 | tail -10
```

Expected: pass count same or higher than before edits.

If surgical fixes were needed, commit them:

```bash
git add tests/
git commit -m "test: strip SOAR field assertions from $(git diff --name-only HEAD~1 tests/ | xargs basename -a | paste -sd ', ' -)"
```

- [ ] **Step 4: AC6 — mcp_server.py no longer imports soar_bridge**

```bash
grep -n "soar_bridge\|soar_boost\|soar_score\|soar_boosted" cognitive_castle/mcp_server.py
```

Expected: zero matches.

- [ ] **Step 5: AC7 — README acknowledgements rephrased**

```bash
grep -n "soar\|SOAR\|Soar" README.md
```

Expected: zero matches.

```bash
grep -n "3-stage retrieval pipeline" README.md
```

Expected: ≥ 1 match (the new acknowledgement text).

- [ ] **Step 6: AC8 — focused suite no regressions**

```bash
pytest tests/ --ignore=tests/benchmarks -q --tb=no 2>&1 | tail -3
```

Compare the failed count to the pre-PR baseline (you can check develop's last test count). The `test_soar_integration.py` tests should be gone (intentional). Any other test that fails for SOAR-related reasons should have been fixed in Step 3.

Expected: failed count ≤ pre-PR baseline. If higher, identify the new failure and decide whether to fix or report.

- [ ] **Step 7: AC9 — CLI smoke**

```bash
castle search "embedder decision" --results 1 2>&1 | head -20
```

Expected: a result block with `score=` and content. No `soar_*` references anywhere in the output (grep the output):

```bash
castle search "embedder decision" --results 1 2>&1 | grep -i soar | head -3
```

Expected: empty.

- [ ] **Step 8: AC10 — MCP tool-call smoke**

```bash
cat > /tmp/soar-removal-smoke.jsonl <<'EOF'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"castle_search","arguments":{"query":"embedder decision","limit":1}}}
EOF
cat /tmp/soar-removal-smoke.jsonl | timeout 60 castle-mcp 2>/dev/null | tail -1
```

Expected: the second JSON-RPC response is a `result` (not `error`), with a `results` array. Critically, the result should NOT contain `soar_boost`, `soar_score`, or `soar_boosted` fields. Verify:

```bash
cat /tmp/soar-removal-smoke.jsonl | timeout 60 castle-mcp 2>/dev/null | tail -1 | grep -c "soar_boost\|soar_score\|soar_boosted"
```

Expected: `0`.

- [ ] **Step 9: AC11 — no production code outside scope modified**

```bash
git diff --name-only develop..HEAD | grep -vE "^(cognitive_castle/soar_bridge\.py|cognitive_castle/rules/|cognitive_castle/mcp_server\.py|tests/test_soar_integration\.py|tests/.*\.py|README\.md)$"
```

Expected: empty output. The only allowable modified production file outside the deletions is `mcp_server.py`. Test surgical fixes (`tests/`) are allowed. README is allowed.

If any other production file (`searcher.py`, `config.py`, etc.) appears, that's a scope violation — investigate.

- [ ] **Step 10: AC12 — commit count ≤ 2**

```bash
git log --oneline develop..HEAD | wc -l
```

Expected: 1 or 2. (Task 1's commit + optional Step 3 test surgery commit.)

- [ ] **Step 11: Push the branch**

```bash
git push -u origin feat/soar-removal
```

Expected: clean push.

- [ ] **Step 12: Open the PR**

```bash
gh pr create --base develop --title "feat: remove SOAR cognitive-architecture integration (PR #A of cleanup series)" --body "$(cat <<'EOF'
## Summary

SOAR was dead code in practice. SML bindings were never installed at \`~/.echelon/soar/\`, so every \`_load_sml()\` call raised \`ImportError\` and \`apply_soar_boosts()\` swallowed it. The cross-encoder reranker (PR #12 fix) is the active re-ranking layer.

Per spec [\`2026-05-12-soar-removal-design.md\`](docs/superpowers/specs/2026-05-12-soar-removal-design.md) (commit 4de9c35e). First PR of a 4-PR cleanup series:

- **#A: SOAR removal** ← this PR
- #B: Mempalace production fixes (i18n + constants/env vars)
- #C: Mempalace tests sweep
- #D: Mempalace docs sweep

#B-D each get their own brainstorm/spec/plan cycle later.

## What changed

Deleted (~820 lines):
- \`cognitive_castle/soar_bridge.py\` — SML wrapper
- \`cognitive_castle/rules/{castle-boost,castle-chunk,castle-impasse}.soar\` — production rule files
- \`cognitive_castle/rules/\` directory
- \`tests/test_soar_integration.py\` — tests for the deleted module

Modified:
- \`cognitive_castle/mcp_server.py\` — 48-line \`# ── SOAR re-ranking ─\` block removed
- \`README.md\` — Acknowledgements section: SOAR clause replaced with credit to the actual 3-stage retrieval pipeline

## API impact

\`castle_search\` MCP tool results no longer include:
- \`soar_boost\` field (always was 1.0)
- \`soar_score\` field (always equaled \`similarity\`)
- \`soar_boosted\` top-level flag (always true-from-failed-boost)

These fields were inert in practice. No realistic consumer depends on them.

## Architectural acknowledgement

This is removing a *bridge*, not just dead code. \`soar_bridge.py\` was designed to bridge symbolic reasoning (production rules) to statistical ranking (cosine). Both halves were broken:
- Symbolic side never loaded (missing SML bindings)
- Action side (\`widen-search\`, \`chunk-candidate\` actions) was never wired — \`apply_soar_boosts\` discarded the actions list

If symbolic reasoning becomes a stated goal later, see the spec's Non-goals for cleaner replacement paths (Python rules engine / LLM-as-judge / reinstalled+benchmarked SOAR). Don't preserve dead infrastructure on the hope it might be useful.

## Test plan

- [x] All 12 acceptance criteria from the spec verified locally
- [x] \`castle search\` end-to-end smoke passes; no \`soar_*\` fields in output
- [x] \`castle-mcp\` JSON-RPC tool call passes; no \`soar_*\` fields in response
- [x] Focused suite: no NEW failures vs pre-PR baseline (the deleted \`test_soar_integration.py\` is intentional)
- [x] \`grep -ri "soar" cognitive_castle/ --include="*.py"\` returns 0

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 13: Report status**

If all ACs pass, report:
- PR URL
- Final line-deletion count
- Confirmation of all 12 ACs
- Any test surgical fixes done in Step 3 (with file names + brief description)

User merges if happy.

---

## Self-Review

**Spec coverage:**
- AC1 (soar_bridge.py deleted) → Task 1 Step 3 + Task 2 Step 1 ✓
- AC2 (rules/ deleted) → Task 1 Step 3 + Task 2 Step 1 ✓
- AC3 (test_soar_integration.py deleted) → Task 1 Step 3 + Task 2 Step 1 ✓
- AC4 (no SOAR refs in production) → Task 1 Step 7 + Task 2 Step 2 ✓
- AC5 (no SOAR field refs in tests) → Task 2 Step 3 ✓
- AC6 (mcp_server.py clean) → Task 1 Step 4 + Task 2 Step 4 ✓
- AC7 (README acknowledgements) → Task 1 Step 6 + Task 2 Step 5 ✓
- AC8 (focused suite stable) → Task 2 Step 6 ✓
- AC9 (CLI smoke) → Task 2 Step 7 ✓
- AC10 (MCP tool-call smoke) → Task 2 Step 8 ✓
- AC11 (scope adherence) → Task 2 Step 9 ✓
- AC12 (commit count ≤ 2) → Task 2 Step 10 ✓

All 12 ACs mapped to verification steps.

**Placeholder scan:**
- The mcp_server.py edit shows the verbatim block to remove — concrete, not a placeholder.
- The README replacement shows the verbatim before/after text.
- Task 2 Step 3 (test surgical fixes) has explicit decision criteria for what to remove vs preserve — not a placeholder.
- No "TBD", "TODO", or vague "implement later".

**Type consistency:**
- N/A (deletion-only PR).

**Known judgment-required points clearly delegated:**
- Test surgery in Task 2 Step 3 (per-file inspection if matches appear)
- Whether unused imports surface in mcp_server.py after the block removal (Task 1 Step 5 — fix if ruff flags any)

Plan complete and ready for execution.
