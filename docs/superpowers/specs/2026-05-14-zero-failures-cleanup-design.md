# Zero Failures Cleanup — Design Spec

**Date:** 2026-05-14
**Status:** Approved, ready for implementation plan
**Scope:** Bring the full test suite from 18 pre-existing failures to zero across five small focused PRs. Each PR addresses one cluster of related stale-test or doc-drift issues left behind by prior refactorings.

## Background

After every recent PR (#26, #29-#37), the report includes the line "pre-existing 18 failures unchanged — no regressions." That baseline has been masking signal: a real regression could slip into the 18-failure floor unnoticed. The failures have accumulated from successive refactorings (MemPalace → cognitive-castle rename, hooks moving to `castle` console script, BM25+closet hybrid search replaced by the 3-stage pipeline, default embedder cutover to bge-m3, etc.) without test-side cleanup.

This spec catalogs all 18, groups them by root cause, and ships one PR per cluster. After this work, the baseline is zero — future PRs can claim "no new failures" with real evidence.

## Goals

- Reduce full-suite failure count from 18 to 0 on `develop`
- Each PR is independently reviewable and mergeable (no inter-PR dependencies)
- Restore CI signal: a single new failure on any future PR is now informative
- Preserve test intent: fix or delete based on whether the asserted behavior still applies, never `xfail` to defer

## Non-goals

- **No `xfail` / `skip` markers** — we either fix the failure or delete the dead test. Strictly enforced; if a single failure proves too expensive to diagnose, defer the WHOLE cluster (ship 4 PRs instead of 5) rather than mark `xfail`
- **No new test coverage** — this is cleanup, not coverage expansion. New tests stay out of these PRs (fixtures/helpers needed to make existing tests pass are OK)
- **No code refactoring** beyond what's needed to make tests pass
- **No scope expansion to "make CI green forever"** — we ship five PRs, get to zero, and stop. Drift-prevention is a follow-up conversation

## Policy: real production bugs surfaced during cleanup

A test may fail because production code is genuinely broken, not because the test is stale. If that's the case during any cluster:

1. Fix the bug in the same PR with a **separate commit** (`fix(<area>): ...` before the `test(<area>): ...` commit)
2. Call it out **explicitly in the PR body** under a `## Production bug discovered` heading
3. The cleanup-PR still counts toward the cluster; no separate "real bug" PR needed

This applies uniformly to all five clusters.

## Failure inventory

Full failure list captured from `python -m pytest tests/ --ignore=tests/benchmarks --tb=no -q` on `develop` at commit `16bb3b61`:

```
FAILED tests/test_closets.py::TestSearchMemoriesHybrid::test_pure_drawer_when_no_closets
FAILED tests/test_closets.py::TestSearchMemoriesHybrid::test_closet_boost_marks_hit_as_drawer_plus_closet
FAILED tests/test_closets.py::TestSearchMemoriesHybrid::test_max_distance_filters_hybrid_hits
FAILED tests/test_closets.py::TestDrawerGrepExpansion::test_hybrid_search_enrichment_populates_drawer_index_and_total
FAILED tests/test_config.py::test_config_from_file
FAILED tests/test_embedding.py::test_get_model_falls_back_to_cpu_on_cuda_oom
FAILED tests/test_hooks_cli.py::test_maybe_auto_ingest_uses_castle_python
FAILED tests/test_hooks_cli.py::test_mine_sync_uses_castle_python
FAILED tests/test_known_entities_registry.py::test_populated_registry_improves_miner_recall
FAILED tests/test_llm_refine.py::test_parse_response_restores_canonical_casing
FAILED tests/test_palace_graph_tunnels.py::TestHyphenatedWingNormalization::test_list_tunnels_filters_hyphenated_wing
FAILED tests/test_palace_graph_tunnels.py::TestHyphenatedWingNormalization::test_follow_tunnels_matches_hyphenated_wing
FAILED tests/test_project_scanner.py::test_merge_primary_wins_case_insensitive
FAILED tests/test_readme_claims.py::TestReadmeToolsExistInCode::test_every_readme_tool_exists_in_tools_dict
FAILED tests/test_readme_claims.py::TestNoUnlistedTools::test_no_undocumented_tools
FAILED tests/test_readme_claims.py::TestClosetFirstSearch::test_closet_boost_search_exists
FAILED tests/test_readme_claims.py::TestClosetFirstSearch::test_searcher_imports_closets
FAILED tests/test_retrieval_pipeline.py::test_pipeline_returns_results_when_flag_enabled
```

## Cluster A — MemPalace → cognitive-castle rename (4 failures)

**Tests:**
- `test_llm_refine.py::test_parse_response_restores_canonical_casing`
- `test_palace_graph_tunnels.py::TestHyphenatedWingNormalization::test_list_tunnels_filters_hyphenated_wing`
- `test_palace_graph_tunnels.py::TestHyphenatedWingNormalization::test_follow_tunnels_matches_hyphenated_wing`
- `test_project_scanner.py::test_merge_primary_wins_case_insensitive`

**Root cause:** The project was rebranded from MemPalace to cognitive-castle. Test fixtures and assertions still use the old name, while production code uses the new one. Confirmed by sampling: `assert 'MemPalace' in {'cognitive-castle': ...}` — the test expects the old name to survive canonical-casing restoration; production restores the new name.

**Approach:** Update test fixtures and assertions to use `cognitive-castle` consistently. Verify that production code's rename was complete — no test should hide a real bug where a code path still emits `MemPalace`.

**No production code changes expected** — if any do surface, scope them tight and call them out in the commit.

**Acceptance:** All 4 tests pass. `grep -rn "MemPalace" tests/` returns zero matches (or only intentional historical-context strings, flagged in commits).

## Cluster B — Hooks now use `castle` console script (2 failures)

**Tests:**
- `test_hooks_cli.py::test_maybe_auto_ingest_uses_castle_python`
- `test_hooks_cli.py::test_mine_sync_uses_castle_python`

**Root cause:** Hooks were refactored to invoke the `castle` console script directly (`subprocess.run(["castle", ...])`) instead of computing a `python -m cognitive_castle.cli` path. Tests still assert the old command shape (`cmd[0] == "/fake/venv/python"`).

**Approach:** Update both tests to assert `cmd[0] == "castle"`. Remove the `/fake/venv/python` fixture if it's no longer needed elsewhere. Update test docstrings if they reference the old behavior.

**Test renames considered:** The function names contain `_uses_castle_python`, which is now misleading. Rename to `_uses_castle_console_script` or similar. Each rename is one-line in test file. **Before renaming, run** `grep -rn "test_maybe_auto_ingest_uses_castle_python\|test_mine_sync_uses_castle_python" .` to verify no CI configs, fixture references, or parametrized test selectors mention the current names — if any do, update them in the same commit.

**Acceptance:** Both tests pass. Test names accurately reflect what's asserted.

## Cluster C — Closets legacy hybrid-search (6 failures)

**Tests:**
- `test_closets.py::TestSearchMemoriesHybrid::test_pure_drawer_when_no_closets`
- `test_closets.py::TestSearchMemoriesHybrid::test_closet_boost_marks_hit_as_drawer_plus_closet`
- `test_closets.py::TestSearchMemoriesHybrid::test_max_distance_filters_hybrid_hits`
- `test_closets.py::TestDrawerGrepExpansion::test_hybrid_search_enrichment_populates_drawer_index_and_total`
- `test_readme_claims.py::TestClosetFirstSearch::test_closet_boost_search_exists`
- `test_readme_claims.py::TestClosetFirstSearch::test_searcher_imports_closets`

**Root cause:** The BM25 + closet-boost hybrid search path that `search_memories` used to expose was replaced by the new 3-stage pipeline (Tantivy FTS + dense vector + KG-hop → RRF + recency → cross-encoder rerank). The closets table still exists in LanceDB (and `closet_llm.py` still generates AAAK closets), but the SEARCH-side hybrid behavior was removed. The tests assert against the old behavior; the README claims tests assert that the closet-first search path is still wired into `searcher.py`.

**Approach (investigation required first):**

1. Read `cognitive_castle/searcher.py` to confirm the current pipeline doesn't reference `closets` for search-time boost
2. Read `cognitive_castle/closet_llm.py` and `cognitive_castle/miner.py` to confirm closets are still WRITTEN (just no longer read at search time)
3. For each of the 6 failing tests:
   - If the asserted behavior is genuinely gone from the codebase → **delete the test** (it asserts a removed feature)
   - If the test asserts a still-extant behavior with a stale interface → **update the test** to use the new interface

**Expected outcome:** Most or all 6 tests get deleted. The hybrid-search-via-closets concept was replaced, not refactored. Keeping the closet generation (for future use or alternative search paths) is fine; tests asserting it influences current `search_memories` are misleading.

**Production code changes:** None expected. If investigation reveals stub functions that exist solely to satisfy these tests, those can also be removed in the same PR.

**Acceptance:** All 6 failures resolved (whether by deletion or update). `grep -rn "closet_boost\|TestSearchMemoriesHybrid" cognitive_castle/` shows no orphaned references.

## Cluster D — README/CLAUDE.md doc-parser drift (2 failures)

**Tests:**
- `test_readme_claims.py::TestReadmeToolsExistInCode::test_every_readme_tool_exists_in_tools_dict`
- `test_readme_claims.py::TestNoUnlistedTools::test_no_undocumented_tools`

**Root cause:** Tests parse `website/reference/mcp-tools.md` looking for `### \`castle_xxx\`` headings (one per MCP tool). Currently zero matches — either the file structure changed, or the heading style was reformatted.

**Approach:**

1. Read `website/reference/mcp-tools.md` to see the current heading style
2. Decide: is the new style intentional? Then update the test parser regex. Is it accidental drift? Then fix the doc.
3. The intent of the test is "every documented tool exists in code AND every code tool is documented" — preserve that contract regardless of which side gets touched

**Acceptance:** Both tests pass. Either docs match the parser, or parser matches the docs, but the doc↔code symmetry is preserved.

## Cluster E — Misc drift (4 failures)

These need individual investigation rather than a single recipe.

**E.1 `test_config.py::test_config_from_file`** — Passes in isolation, fails in full suite. This is a **test-isolation bug**, not a stale-test issue. Some prior test pollutes shared state (likely an environment variable or a singleton cfg cache). Approach: identify the polluting test (use `pytest --collect-only` ordering + bisect with `-k`), isolate the polluted state, fix the leak in a test fixture (or `monkeypatch` the variable so it's reset between tests). **Time-box: 90 minutes.** If diagnosis exceeds that, defer Cluster E entirely — ship 4 PRs (A, B, C, D) and leave E for a separate spec.

**E.2 `test_embedding.py::test_get_model_falls_back_to_cpu_on_cuda_oom`** — Test mocks CUDA OOM and asserts the returned model entries. Assertion expects `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, actual is `BAAI/bge-m3`. The default cutover (PR #26) changed the model; test wasn't updated. Approach: update the assertion to expect the current default. If the test parameterizes over both models, that's even cleaner.

**E.3 `test_known_entities_registry.py::test_populated_registry_improves_miner_recall`** — Test asserts `'cognitive-castle' in extracted_entities` but the entity_detector returned `{'Julia Grib', 'Kevin Heifner', 'hyperion-history'}`. Either the test fixture's source text changed, or the entity_detector's recall changed. Approach: read the test, the fixture, and entity_detector behavior. Likely a fixture issue — the source text probably needs to actually contain "cognitive-castle" enough times (3+ per the discovery from KG enrichment work).

**E.4 `test_retrieval_pipeline.py::test_pipeline_returns_results_when_flag_enabled`** — Tests the `CASTLE_USE_NEW_RETRIEVAL_PIPELINE` env-var feature flag. **Verified: the flag is dead.** `cognitive_castle/searcher.py` unconditionally calls `_new_pipeline_search` (line 279); no code reads the env var. The file `test_retrieval_pipeline.py` contains **two tests** — the failing one plus `test_pipeline_disabled_falls_back_to_old_path` (currently passing by happenstance because both branches now run the same code path). Approach: **delete both tests**. If the file becomes empty after deletion, delete the file too.

**Acceptance:** E.1, E.2, E.3 pass with updated tests; E.4 is deleted along with its passing partner. (If E.1 hits the 90-minute time-box, entire cluster E is deferred to a separate spec.)

## Implementation order

**Work in this order** (landing order doesn't matter for correctness, but the work-sequence is ramped by complexity):

1. **B** (hooks console-script) — 30 min, 2 tests, smallest. Builds momentum.
2. **A** (rename) — 1 hr, 4 tests, mechanical. Continued momentum.
3. **D** (doc-parser) — 30 min, 2 tests. One small decision (doc vs parser).
4. **E** (misc) — 2-3 hr, 4 tests. Each one's own diagnosis. Time-boxed (see Cluster E).
5. **C** (closets) — 2-4 hr, 6 tests. Most investigation, possibly the biggest deletions.

Total estimated effort: ~6-9 hours of focused work across 5 PRs. Each PR ~5 min reviewer time.

**File-overlap note:** Clusters C and D both touch `tests/test_readme_claims.py` (different classes — C touches `TestClosetFirstSearch`, D touches `TestReadmeToolsExistInCode` and `TestNoUnlistedTools`). The recommended order (D before C) lands D first; C then deletes its classes from the file. Reverse order works too, but the second PR will rebase against the first. **Don't develop C and D in parallel branches** — rebase friction.

## Per-PR workflow

Standard Castle flow applies:

```bash
git checkout -b fix/<cluster-name>
# investigate + change
python -m pytest <touched-tests> -v
python -m pytest tests/ --ignore=tests/benchmarks -q  # verify failure count decreased
ruff format <touched-files>
ruff check <touched-files>
git add <touched-files>
git commit -m "test(<area>): <description>"  # or "fix(<area>): ..." if production code touched
git push -u origin fix/<cluster-name>
gh pr create --title "..." --body "..."
gh pr merge <PR#> --merge --delete-branch
git checkout develop
git pull --ff-only
```

Each PR's body should include the before/after failure counts (e.g., "18 → 16" for cluster B) so the cumulative cleanup is visible from PR history.

## Risk register

1. **Cluster C investigation may surface a feature decision** — if the closets-based hybrid search has constituents who want it back, the spec's "delete the tests" default flips. Investigation step in Cluster C addresses this
2. **Cluster E.1 (test isolation) may be hard to diagnose** — 90-minute time-box; if exceeded, defer entire Cluster E to a separate spec (4 PRs ship, 1 deferred; still strictly no `xfail`)
3. **Production bugs found during cleanup** — handled by the uniform policy above ("fix in same PR with separate commit; flag in PR body")
4. **README/docs may have a third source of truth** — `test_readme_claims` may parse `website/reference/mcp-tools.md` while CLAUDE.md and the actual README differ. Investigation step should confirm which source of truth the test expects
5. **Cluster B test renaming bleeds into other test files** — grep is now explicitly in the cluster's approach; risk mitigated
6. **Clusters C and D both touch `tests/test_readme_claims.py`** — different classes, no logical conflict, but rebase friction if developed in parallel. Mitigation in implementation-order section

## Out of scope

- **CI gate hardening** — once we hit zero, future PRs that introduce a new failure should fail CI. That's a separate spec/discussion (Castle's current CI config may already enforce this; verify in a follow-up).
- **Test-suite speed-up** — current suite runs ~30s; not in scope here.
- **Adding new tests** — only fixing/deleting existing ones.
- **Refactoring touched modules** — if `test_palace_graph_tunnels.py` reveals that `palace_graph.py` itself is sprawling, that's a separate cleanup spec.
- **The CI workflow file itself** — if `.github/workflows/*.yml` skips the failing tests, leave it; we just want green from the test suite.

## Acceptance criteria

- `python -m pytest tests/ --ignore=tests/benchmarks -q` returns `0 failed` (or `14 failed` if Cluster E was deferred per E.1 time-box)
- All 5 PRs (or 4, if E deferred) merged to `develop` and feature branches deleted
- No `@pytest.mark.skip`, `@pytest.mark.xfail`, or similar markers were added during this work
- Historical spec/plan docs that mention "18 pre-existing failures" are LEFT AS-IS (they reflect a true state at the time of writing; updating post-hoc would be revisionist)

## What this unlocks

- Future PRs can claim "no regressions" with real evidence
- A single new test failure is now informative — no longer noise lost in the baseline
- The closets-related dead tests stop confusing readers about what features exist
- The MemPalace → cognitive-castle rename is finally fully reflected in tests
