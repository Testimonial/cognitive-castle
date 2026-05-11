# Cognitive Castle — ChromaDB Removal

**Date:** 2026-05-12
**Branch target:** develop
**Scope:** Delete the ChromaDB backend entirely from `cognitive_castle/` and its tests, plus the orphaned `.codex-plugin/` Codex CLI scaffolding. Single-backend codebase afterward (LanceDB only).

## Background

ChromaDB was Castle's original storage backend. The SOTA retrieval upgrade (PR #2) made LanceDB the default but kept `cognitive_castle/backends/chroma.py` in-tree as a fallback (`CASTLE_BACKEND=chroma`). The reasoning at the time was "don't break users who already have a chroma palace." Two facts make that reasoning moot:

1. The user has no chroma palaces (verified earlier in the session: `~/.mempalace/palace/` was created at the LanceDB era, not the chroma era).
2. `pyproject.toml` doesn't depend on chromadb. The library is installed transitively or by accident; it isn't a sanctioned dependency.

Keeping chroma costs ~50–70 test failures in the focused suite plus ~600 lines of backend code + a defunct `castle migrate` CLI subcommand + a chroma-specific `castle repair --mode max-seq-id` mode. None of it serves a user.

Earlier in the session the user explicitly wanted this removed ("no fall back to Chrome, remove all chromaevidence and reference") but we pivoted to the SOTA work. This spec executes the deferred removal.

The user also confirmed (earlier brainstorm): `.codex-plugin/` should be deleted — it's a stale Codex CLI plugin scaffolding nobody uses, with the same mempalace branding the rest of the rebrand cleaned up. Bundled in here because it's also dead-code cleanup with a similar motivation.

## Goals

1. `cognitive_castle/backends/chroma.py` deleted. `backends/registry.py` no longer registers a chroma backend. `backends/__init__.py` no longer exports `ChromaBackend` / `ChromaCollection`.
2. `cognitive_castle/migrate.py` deleted (its only purpose was "Recover a palace created with a different ChromaDB version").
3. `castle migrate` CLI subcommand deleted from `cognitive_castle/cli.py`.
4. `castle repair --mode max-seq-id` mode and its `--max-seq-id-sidecar` arg deleted from `cognitive_castle/cli.py` (chroma-specific repair).
5. Chroma-only test files deleted entirely:
   - `tests/test_empty_chromadb_results.py`
   - `tests/test_migrate.py`
   - `tests/test_collection_metric_invariant.py`
   - `tests/test_hnsw_capacity.py`
6. Chroma half of mixed test files cleaned out (specific test methods, not whole files):
   - `tests/test_backends.py` — keep the LanceDB tests, delete the chroma-specific ones
   - `tests/test_repair.py` — delete `max_seq_id`-related tests; keep generic repair tests
   - `tests/test_dedup.py` — rewrite or delete tests that depended on `chromadb` fixtures
   - `tests/test_closets.py` — same
   - `tests/test_cli.py` — delete the `castle migrate` tests; keep the rest
   - `tests/test_mcp_server.py` — delete any tests that exercised chroma-specific MCP behavior
7. `.codex-plugin/` deleted entirely (stale Codex CLI scaffolding, mempalace-branded, unused).
8. `backends/_utils.py` — read it; if it's chroma-specific, delete; if generic, keep.
9. Doc sweep: remove references to `CASTLE_BACKEND=chroma`, ChromaDB, chromadb from `cognitive_castle/instructions/*.md`, `cognitive_castle/README.md`, plugin README (already done in PR #4 for the rebrand, may have residual chroma mentions).
10. Net result: focused-suite failure count drops from 156 to ~80 (down by ~76: ~50 chroma failures plus the chroma-coupled test count reductions; exact number TBD).

## Non-goals

- **Removing `chromadb` from the venv** (`pip uninstall chromadb`). The library may still be transitively required by something; uninstalling is a separate operational step the user can do manually after merge.
- **Re-doing the embedder migration spec** (PR #2 already handled that). This spec only removes chroma; LanceDB stays.
- **Re-exposing other backends** (Qdrant, etc.). LanceDB-only by deliberate design.
- **Benchmark suite** (`tests/benchmarks/test_chromadb_stress.py` etc.). The benchmarks are explicitly ignored in the focused suite; leave them for a separate cleanup if anyone cares. (Optional: delete `test_chromadb_stress.py` since it's purely chroma-only — see Open Questions.)
- **Pre-existing test debt categories E + F** (cognitive_cognitive_castle typo files, mixed misc). Separate future work.

## Source of truth (verified)

- `cognitive_castle/backends/chroma.py` exists (~size unknown, will measure during plan).
- `cognitive_castle/backends/registry.py:181` — "Register lancedb as the in-tree default; keep chroma as fallback."
- `cognitive_castle/backends/registry.py:188-193` — chroma fallback registration block.
- `cognitive_castle/migrate.py` exists; docstring confirms chroma-specific purpose.
- `cognitive_castle/cli.py:626` — `cmd_migrate` function definition (chroma-specific).
- `cognitive_castle/cli.py:821-1265` (approximate) — `castle repair --mode max-seq-id` chroma-specific repair path.
- `.codex-plugin/` exists with same shape as `.claude-plugin/` but unused (stale Codex plugin manifest, branded mempalace).
- Chroma-only test files exist as listed under Goal #5.
- `chromadb 1.5.8` is installed in the venv but not in `pyproject.toml`.

## Approach: phased removal (tests-first or code-first?)

Two ordering options:

**Option A: code-first.** Delete chroma.py first, then watch the chroma-coupled tests start to fail with cleaner errors (`ImportError` rather than `NotFoundError`), then delete those tests.
- Pro: tests reveal the dependency surface honestly.
- Con: intermediate state is broken (tests fail on import).

**Option B: tests-first.** Delete chroma-only tests first, rewrite chroma-half tests in mixed files, then delete the chroma backend code.
- Pro: every commit leaves the suite green-ish (failures only decrease).
- Con: requires upfront awareness of test dependencies on chroma.

**Choice: B (tests-first).** Aligned with the principle that every commit should leave the test suite in a stable state. The implementation plan will sequence accordingly.

## File-by-file change list (high level — implementation plan has the details)

### Phase 1: Delete chroma-only tests

Delete these files outright:
- `tests/test_empty_chromadb_results.py`
- `tests/test_migrate.py`
- `tests/test_collection_metric_invariant.py`
- `tests/test_hnsw_capacity.py`

### Phase 2: Clean chroma half of mixed test files

Per-file work. Each file gets the chroma-specific tests deleted, generic tests rewritten if they currently use chroma fixtures:
- `tests/test_backends.py` — delete chroma-specific tests; keep LanceDB tests
- `tests/test_repair.py` — delete `test_max_seq_id_*` tests; keep generic repair tests
- `tests/test_dedup.py` — rewrite to use LanceDB or delete if chroma was load-bearing
- `tests/test_closets.py` — same case-by-case
- `tests/test_cli.py` — delete `test_cmd_migrate*` tests; keep the rest
- `tests/test_mcp_server.py` — delete tests for chroma-specific MCP behavior; keep the rest

Implementation plan should walk each file individually with the actual delete/rewrite decisions surfaced.

### Phase 3: Delete production chroma code

- Delete `cognitive_castle/backends/chroma.py` entirely
- Update `cognitive_castle/backends/__init__.py`: remove `ChromaBackend`, `ChromaCollection` from imports + `__all__`
- Update `cognitive_castle/backends/registry.py`:
  - Remove the chroma fallback registration block (lines ~181-193)
  - Default selection becomes lancedb-only (no `CASTLE_BACKEND=chroma` escape hatch)
  - Update docstrings that reference chroma as a fallback
- `cognitive_castle/backends/_utils.py`: read the file; if any function is chroma-specific (likely yes given the naming history), delete those functions or the whole file as appropriate

### Phase 4: Delete migrate.py + CLI subcommand

- Delete `cognitive_castle/migrate.py`
- Remove `cmd_migrate` from `cognitive_castle/cli.py` (function body + the `sub.add_parser("migrate", ...)` registration + the dispatch entry)
- Remove `castle repair --mode max-seq-id` from `cmd_repair` in `cli.py` (the mode branch + its `--max-seq-id-sidecar` arg + the helper functions it calls)

### Phase 5: Delete .codex-plugin/

- `git rm -r .codex-plugin/`

### Phase 6: Doc sweep

Grep for chroma references in:
- `cognitive_castle/instructions/*.md` (5 files)
- `cognitive_castle/README.md`
- `.claude-plugin/README.md` (already done in PR #4; verify)
- Module docstrings in `cognitive_castle/*.py` (limited scope; the PR #4 doc sweep already cleaned most of these)

Replace with LanceDB-only language. If a reference is historical context (e.g., "originally used ChromaDB"), preserve the historical fact but make clear it's no longer used.

NOT in scope: `docs/`, `CHANGELOG.md`, `website/`, historical specs/plans/rfcs (those record what was true at the time).

## Testing strategy

After each phase, run focused regression:

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```

(Note: the ignore-list still excludes `test_collection_metric_invariant.py` and `test_hnsw_capacity.py` while they exist. After Phase 1 deletes them, the ignore flags become no-ops but remain harmless.)

Expected progression:
- Baseline: 156 failed
- After Phase 1: ~125-130 failed (chroma-only test files gone; their failures were counted previously)
- After Phase 2: ~85-95 failed (mixed-file chroma halves gone)
- After Phase 3-4: ~70-80 failed (chroma backend code gone; any test that imports `chroma.py` now errors at import — these should already be deleted in Phases 1-2)
- After Phase 5-6: ~70-80 failed (no test impact)

Manual smoke after Phase 4: confirm `castle --version`, `castle init`, `castle mine`, `castle search` all still work in a fresh test palace.

## Failure modes

| Failure | Surface | Handling |
|---|---|---|
| A test in Phase 2 turns out to depend on chroma in a non-obvious way | Test fails after rewrite | Delete the test or rewrite it for LanceDB |
| `cognitive_castle/backends/__init__.py` has external callers importing `ChromaBackend` | ImportError at module import | grep for `ChromaBackend\|ChromaCollection` in `cognitive_castle/` — confirm zero external callers before deleting from `__init__.py` |
| `castle migrate` was somehow used outside the chroma context | User script breakage | None — it was strictly chroma-version migration |
| `castle repair --mode max-seq-id` had a non-chroma use | Hard to imagine, but flag | The `--max-seq-id-sidecar` arg is chroma-only; deleting the mode is safe |
| `chromadb` library still imported somewhere in `cognitive_castle/` after the cleanup | ImportError or silent dead reference | Final grep: `grep -rn "import chromadb\|from chromadb" cognitive_castle/` → zero matches |

## Open questions

1. **Benchmark test `tests/benchmarks/test_chromadb_stress.py`** — delete or leave? It's in the benchmark suite (excluded from focused runs). Delete is cleaner; leaving is harmless. Implementation plan: delete.
2. **`backends/_utils.py`** — read at implementation time; decide delete-entire-file or strip-chroma-functions based on what's actually in it.
3. **chromadb library in the venv** — out of scope per spec, but the user may want to `pip uninstall chromadb` after merge. Mention in PR body.

## Risk

- **Medium-low.** Net deletion. No new code. Each phase is independently revertable.
- **Highest single risk:** Phase 2's per-test triage. If a "chroma half" test is actually testing something generic that happens to use chroma in the fixture, deleting it loses that coverage. Mitigation: review each test before deleting; rewrite when the test concept is generic.
- **Lower risks:** Phase 3 (code deletion) — well-bounded. Phase 5 (.codex-plugin) — purely cosmetic surface. Phase 6 (doc sweep) — text only.
- **Reversible:** `git revert` per phase. Each phase is its own commit.

## Acceptance criteria

1. `cognitive_castle/backends/chroma.py` does not exist.
2. `grep -rn "import chromadb\|from chromadb\|ChromaBackend\|ChromaCollection" cognitive_castle/ --include="*.py"` → zero matches.
3. `cognitive_castle/migrate.py` does not exist.
4. `castle migrate` is not a registered subcommand (verify: `castle --help 2>&1 | grep -q migrate` returns non-zero).
5. `castle repair --help 2>&1 | grep -q "max-seq-id"` returns non-zero.
6. The 4 chroma-only test files do not exist.
7. `.codex-plugin/` does not exist.
8. `grep -rn "chromadb\|ChromaDB" cognitive_castle/ --include="*.py" --include="*.md"` returns ≤ 3 matches, each in a context where the reference is historical (e.g., "originally backed by ChromaDB").
9. Focused regression: failure count is ≤ 90 (down from 156, gain of ≥ 66).
10. Manual smoke: `castle init`, `castle mine`, `castle search` all work in a fresh palace.
11. `git status` clean after a full test suite run.
