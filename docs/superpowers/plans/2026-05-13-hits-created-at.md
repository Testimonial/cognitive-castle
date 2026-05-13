# Wire `created_at` + `source_file` + `similarity` Through Hits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `source_file`, `created_at`, and `similarity` fields to every hit dict returned by `_new_pipeline_search` so SOAR's `recency-boost` rule can fire on real searches and 2 chronic CI-UNSTABLE failing tests turn green.

**Architecture:** Single change site at `cognitive_castle/searcher.py:475-487`. Add `import json` to the imports block (currently missing — verified at spec review). Add a `_get_filed_at(r) -> str` helper that JSON-parses `r["metadata_json"]` and returns `filed_at`. Add 3 fields to the hit dict.

**Tech Stack:** Python 3.12, existing LanceDB drawer storage (metadata stored in `metadata_json` JSON-stringified column + hoisted `source_file` column).

**Spec:** [`docs/superpowers/specs/2026-05-13-hits-created-at-design.md`](../specs/2026-05-13-hits-created-at-design.md) (commit `80022f4c`).

**File map (1 file, ~16 LOC):**

| File | Responsibility | Tasks |
|---|---|---|
| `cognitive_castle/searcher.py` | Add `import json` to import block. Add `_get_filed_at(r)` helper. Add 3 new fields to hit dict at lines 475-487. | Tasks 2, 3, 4 |

---

## Task 1: Create feature branch

**Files:** none (git only)

- [ ] **Step 1: Confirm clean tree on develop with the spec commit visible**

Run:
```bash
git status
git log --oneline -3
```

Expected:
- On branch `develop`
- Working tree clean
- Latest commits include `80022f4c` (the spec revision) and `35f2151a` (the spec initial commit)

- [ ] **Step 2: Create + switch to feature branch**

Run:
```bash
git checkout -b feat/hits-created-at
```

Expected: `Switched to a new branch 'feat/hits-created-at'`

No commit yet.

---

## Task 2: Verify the 2 target tests currently fail (TDD red — confirm gap exists)

This task is verification-only: the 2 pre-existing failing tests ARE the failing-test step of the TDD cycle. They've been carried through PRs #1, #3, #4a as documented gaps. Confirming they still fail establishes the baseline.

**Files:** none (verification only)

- [ ] **Step 1: Run the 2 target tests and confirm they FAIL**

Run:
```bash
pytest tests/test_searcher.py -v -k "test_result_fields or test_created_at_contains_filed_at"
```

Expected: both fail.

- `test_result_fields` should fail with `KeyError` or `AssertionError` on the missing `source_file` / `similarity` / `created_at` fields.
- `test_created_at_contains_filed_at` should fail with `KeyError: 'created_at'` (the assertion never reaches the value check because the key is missing).

If they unexpectedly PASS, something has changed since the spec — STOP and re-investigate before proceeding.

No commit yet — this is purely the "red" step.

---

## Task 3: Add `import json` + `_get_filed_at` helper + 3 new hit-dict fields (TDD green)

**Files:**
- Modify: `cognitive_castle/searcher.py` (imports block + new helper + hit-dict construction at lines 475-487)

- [ ] **Step 1: Add `import json` to the import block**

Find the import block at the top of `cognitive_castle/searcher.py`. The existing imports look something like:

```python
from __future__ import annotations
import os
from typing import ...
```

`json` is NOT currently imported (verified via grep at spec review). Add it:

```python
import json
```

Place it in alphabetical order with the other stdlib imports (after `import os` or wherever it slots).

- [ ] **Step 2: Add the `_get_filed_at(r)` helper function**

Find a place for the helper — typically near other private helpers in `searcher.py` (look for `_extract_text`, `_extract_id`, etc.). Insert the helper alongside them:

```python
def _get_filed_at(r) -> str:
    """Extract filed_at (used as created_at in hits) from drawer metadata.

    LanceDB stores per-drawer metadata as a JSON-serialized blob in the
    metadata_json column. filed_at is set by the miner at filing time
    (miner.py:754, 900) but isn't promoted to a hoisted column, so we
    parse it on demand here.

    Returns "" if metadata_json is missing, not a string, or malformed
    JSON — gracefully degrading so missing/old drawers don't crash search.
    """
    if not isinstance(r, dict):
        return ""
    raw = r.get("metadata_json")
    if not isinstance(raw, str):
        return ""
    try:
        meta = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ""
    return str(meta.get("filed_at", ""))
```

- [ ] **Step 3: Add 3 new fields to the hit dict at lines 475-487**

Find the existing return statement in `_new_pipeline_search`:

```python
    return [
        {
            "id": _extract_id(r),
            # "text" is the legacy key expected by MCP callers, tests, and
            # benchmarks; "document" is kept for forward-compat callers.
            "text": _extract_text(r),
            "document": _extract_text(r),
            "score": float(s),
            "wing": r.get("wing", "") if isinstance(r, dict) else "",
            "room": r.get("room", "") if isinstance(r, dict) else "",
        }
        for s, r in reranked[:n_results]
    ]
```

Replace with the version that includes the 3 new fields:

```python
    return [
        {
            "id": _extract_id(r),
            # "text" is the legacy key expected by MCP callers, tests, and
            # benchmarks; "document" is kept for forward-compat callers.
            "text": _extract_text(r),
            "document": _extract_text(r),
            "score": float(s),
            "wing": r.get("wing", "") if isinstance(r, dict) else "",
            "room": r.get("room", "") if isinstance(r, dict) else "",
            # NEW (PR follow-up to #4a — unblocks SOAR recency-boost):
            "source_file": (r.get("source_file") or "") if isinstance(r, dict) else "",
            "created_at": _get_filed_at(r),
            "similarity": float(s),  # alias to score (test asserts type only)
        }
        for s, r in reranked[:n_results]
    ]
```

Notes on the choices:
- `(r.get("source_file") or "")` (not `r.get("source_file", "")`) catches both missing key AND explicit None. Matches the storage layer's coercion pattern at `lancedb_backend.py:225`.
- `similarity` is intentionally aliased to `score` per spec Non-goals — the test asserts type-only, no production caller reads the value.

- [ ] **Step 4: Run the 2 target tests — confirm both PASS**

Run:
```bash
pytest tests/test_searcher.py -v -k "test_result_fields or test_created_at_contains_filed_at"
```

Expected: 2 passed.

- If `test_created_at_contains_filed_at` fails with a value mismatch (e.g., `assert "2026-01-02T00:00:00" == "2026-01-01T00:00:00"`), the auth.py drawer (filed_at `"2026-01-01T00:00:00"`) didn't rank first on "JWT authentication". That's a pre-existing test-design assumption about ranker behavior, not a bug in this change. Investigate separately.
- If `test_result_fields` still fails on the `similarity` type check (`isinstance(hit["similarity"], float)`), verify the spelling and that `float(s)` was used (not `s` directly — `s` is typed as float upstream but the explicit cast is defensive).

- [ ] **Step 5: Run full searcher test file — no NEW regressions**

Run:
```bash
pytest tests/test_searcher.py -v
```

Expected: previously-failing tests now pass (those 2). Previously-passing tests stay passing. Pre-existing CI-UNSTABLE failures in OTHER test files are out of scope.

- [ ] **Step 6: Run full default test suite — no NEW regressions vs. develop**

Run:
```bash
pytest tests/ --ignore=tests/benchmarks 2>&1 | tail -3
```

Expected: total `failed` count drops by exactly 2 compared to the develop baseline at commit `35f2151a`. No NEW failures introduced.

If the failure count moves by more than 2, investigate — the change should be additive only.

- [ ] **Step 7: Lint check**

Run:
```bash
ruff check cognitive_castle/searcher.py && ruff format --check cognitive_castle/searcher.py
```

Expected: no errors. If `ruff format --check` reports a formatting drift, run `ruff format cognitive_castle/searcher.py` to fix, then re-check.

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/searcher.py
git commit -m "$(cat <<'EOF'
feat(searcher): wire source_file + created_at + similarity through hits

Adds 3 new fields to the hit-dict at _new_pipeline_search:475-487:
- source_file (from existing hoisted LanceDB column)
- created_at (parsed from metadata_json.filed_at via new _get_filed_at
  helper — graceful empty-string fallback on missing/malformed data)
- similarity (alias to score; test asserts type only, no caller reads value)

Two effects:
1. Unblocks SOAR's recency-boost rule from PR #4a — bridge reads
   hit["created_at"] to compute age. With this fix, fresh drawers fire
   recency-boost (×1.25) when --soar-boost is enabled.
2. Eliminates 2 chronic CI-UNSTABLE failures (test_result_fields +
   test_created_at_contains_filed_at) that have been carried through
   PRs #1, #3, #4a — they were testing exactly this gap.

Also adds `import json` to searcher.py imports (was not previously
imported; required by the new _get_filed_at helper).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Live smoke (optional — verifies SOAR motivation end-to-end)

Fixture timestamps in `seeded_collection` are 132+ days old (Jan 2026), so they won't trigger `recency-boost` (>7-day threshold). This smoke uses a freshly-mined palace where drawers ARE recent, so SOAR's recency-boost rule actually fires.

**Files:** none (filesystem + Castle only)

- [ ] **Step 1: Build a small palace with a fresh drawer**

```bash
rm -rf /tmp/created-at-smoke
mkdir -p /tmp/created-at-smoke/palace /tmp/created-at-smoke/src
echo "# auth notes — JWT tokens for stateless auth" > /tmp/created-at-smoke/src/auth.md
castle reindex --palace /tmp/created-at-smoke/palace --sources /tmp/created-at-smoke/src --yes
```

Expected: reindex completes; drawer's `filed_at` is set to `datetime.now().isoformat()` per `miner.py:754, 900` — so it's recent.

- [ ] **Step 2: Verify `created_at` is populated in the hit dict via MCP path**

The CLI `castle search` doesn't print audit fields by default. Use a quick Python probe to call `search_memories()` directly:

```bash
CASTLE_PALACE_PATH=/tmp/created-at-smoke/palace python -c "
from cognitive_castle.searcher import search_memories
result = search_memories('auth', '/tmp/created-at-smoke/palace')
hits = result.get('results', [])
for h in hits[:3]:
    print(f\"id={h.get('id', '?')[:30]:30} created_at={h.get('created_at', '?')} score={h.get('score', 0):.3f} source_file={h.get('source_file', '?')}\")
"
```

Expected: hits show `created_at` populated with a recent ISO timestamp (today's date), `source_file=auth.md`, `score` is a float.

- [ ] **Step 3: Run `castle search --soar-boost` and confirm no errors**

```bash
CASTLE_SOAR_ENABLED=1 CASTLE_PALACE_PATH=/tmp/created-at-smoke/palace \
  castle search "auth" --soar-boost 2>&1 | tail -15
```

Expected: completes successfully. No `[soar] ...` stderr warnings.

Note: the CLI doesn't print audit fields by default, so you won't SEE the boost-tag in output. The score WILL have been multiplied by 1.25 if `recency-boost` fired. To verify the boost actually fired, compare the score against a non-SOAR baseline:

```bash
CASTLE_PALACE_PATH=/tmp/created-at-smoke/palace \
  castle search "auth" 2>&1 | grep "score=" | head -1
```

Compare the two `score=X.XXX` values. The `--soar-boost` version should be `1.25x` the no-flag version IF recency-boost fired (drawer age < 7 days).

- [ ] **Step 4: Verify via direct soar_bridge invocation**

The cleanest way to verify recency-boost fires end-to-end:

```bash
CASTLE_SOAR_ENABLED=1 CASTLE_PALACE_PATH=/tmp/created-at-smoke/palace python -c "
from cognitive_castle.config import CognitiveCastleConfig
from cognitive_castle.searcher import search_memories
from cognitive_castle.soar_bridge import apply_soar_boosts

cfg = CognitiveCastleConfig()
result = search_memories('auth', '/tmp/created-at-smoke/palace')
hits = result.get('results', [])
print(f'pre-soar score: {hits[0][\"score\"]:.3f}')
hits = apply_soar_boosts(hits, cfg)
print(f'post-soar score: {hits[0][\"score\"]:.3f}')
print(f'soar_boost multiplier: {hits[0][\"soar_boost\"]}')
print(f'soar_tags: {hits[0][\"soar_tags\"]}')
"
```

Expected output looks like:
```
pre-soar score: 0.123
post-soar score: 0.154
soar_boost multiplier: 1.25
soar_tags: ['recency-boost']
```

This proves end-to-end that `created_at` flows from drawer metadata → hit dict → SOAR `_compute_age_seconds` → `^recently-accessed = true` → `recency-boost` rule fires → score multiplied by 1.25.

- [ ] **Step 5: Clean up**

```bash
rm -rf /tmp/created-at-smoke
```

No commit — this is verification only. Capture the Step 4 output for the PR description.

---

## Task 5: Final acceptance + push + PR

**Files:** none (verification + git push only)

Walk through all 5 acceptance criteria from the spec.

- [ ] **Step 1: Acceptance #1 — the 2 named tests pass**

```bash
pytest tests/test_searcher.py -v -k "test_result_fields or test_created_at_contains_filed_at"
```

Expected: 2 passed.

- [ ] **Step 2: Acceptance #2 — no NEW failures vs develop baseline**

```bash
pytest tests/ --ignore=tests/benchmarks 2>&1 | tail -3
```

Expected: total `failed` count drops by exactly 2 compared to the develop baseline at commit `35f2151a` (which had 20 pre-existing CI-UNSTABLE failures). New count: ~18. No NEW failures introduced.

- [ ] **Step 3: Acceptance #3 — ruff clean on touched file**

```bash
ruff check cognitive_castle/searcher.py && ruff format --check cognitive_castle/searcher.py
```

Expected: no errors.

- [ ] **Step 4: Acceptance #4 — existing fields unchanged**

Spot-check by running a non-SOAR search and verifying the legacy fields are still present:

```bash
CASTLE_PALACE_PATH=~/.castle/palace python -c "
from cognitive_castle.searcher import search_memories
result = search_memories('test', '~/.castle/palace')
hits = result.get('results', [])
if hits:
    h = hits[0]
    for field in ['id', 'text', 'document', 'score', 'wing', 'room', 'source_file', 'created_at', 'similarity']:
        present = field in h
        print(f'  {field}: {\"✓\" if present else \"✗\"}')
" 2>&1 | tail -12
```

Expected: all 9 fields present (6 pre-existing + 3 new).

Note: if you don't have a `~/.castle/palace` set up, skip this step or substitute any palace path you have.

- [ ] **Step 5: Acceptance #5 — live smoke verified SOAR motivation**

Already done in Task 4. Confirm by re-reading the Task 4 Step 4 output (the `soar_tags: ['recency-boost']` line).

- [ ] **Step 6: Push branch**

```bash
git push -u origin feat/hits-created-at
```

Expected: branch pushed; `gh pr create` URL printed.

- [ ] **Step 7: Open PR**

```bash
gh pr create --title "feat: wire created_at + source_file + similarity through hits" --body "$(cat <<'EOF'
## Summary

Small follow-up to PR #4a (SOAR bridge, merged at `653b8208`) that closes 2 real gaps:

1. **Unblocks SOAR's `recency-boost` rule.** The bridge reads `hit["created_at"]` to compute drawer age. Without it, age = infinity → `^recently-accessed = "false"` → rule never fires. With this fix, the bridge becomes useful end-to-end in production, not just on synthetic test fixtures.
2. **Eliminates 2 chronic CI-UNSTABLE failures** (`test_result_fields` + `test_created_at_contains_filed_at`) that have been carried through PRs #1, #3, and #4a. Investigation showed they were testing exactly this gap — written for a richer hit schema that never landed.

## Change

~16 LOC, 1 file (`cognitive_castle/searcher.py`):
- `import json` added (was not previously imported)
- New `_get_filed_at(r) -> str` helper — JSON-parses `metadata_json` and returns `filed_at`. Graceful empty-string fallback on missing/malformed data.
- 3 new fields in hit dict at lines 475-487:
  - `source_file` (from existing hoisted LanceDB column)
  - `created_at` (from `_get_filed_at(r)`)
  - `similarity` (alias to `score` — test asserts type only)

No new modules, no schema changes, no reindex, no new tests.

Spec: `docs/superpowers/specs/2026-05-13-hits-created-at-design.md` (commit `80022f4c`, revised 1× after review).

## Test plan

- [x] `pytest tests/test_searcher.py -v -k "test_result_fields or test_created_at_contains_filed_at"` — **2 passed** (both currently fail on develop)
- [x] `pytest tests/ --ignore=tests/benchmarks` — failure count drops from 20 → 18 (these 2 fixed; no new regressions)
- [x] `ruff check` + `ruff format --check` clean on `searcher.py`
- [x] **Live smoke:** fresh palace + `apply_soar_boosts` call shows `soar_tags: ['recency-boost']` populated and `soar_boost: 1.25` multiplier applied — proves the SOAR motivation works end-to-end

## Known constraint (not a bug)

The `seeded_collection` test fixture has `filed_at` values from January 2026 — 132+ days old. SOAR's `recency-boost` rule won't fire on fixture-based queries (>7-day threshold). Only the live smoke on a freshly-filed drawer verifies the rule actually fires. The 2 target tests verify the `created_at` field is present and correctly mapped, not that recency-boost fires.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed. Report it.

---

## Self-Review

**Spec coverage check:** all 5 acceptance criteria from `2026-05-13-hits-created-at-design.md` map to verification steps:

| Spec acceptance | Implemented / verified in |
|---|---|
| #1 the 2 named tests pass | Task 3 Step 4 + Task 5 Step 1 |
| #2 no NEW failures vs develop baseline | Task 3 Step 6 + Task 5 Step 2 |
| #3 ruff clean | Task 3 Step 7 + Task 5 Step 3 |
| #4 default behavior for existing fields unchanged | Task 5 Step 4 |
| #5 live smoke for SOAR motivation | Task 4 Steps 2-4 + Task 5 Step 5 |

**Placeholder scan:**
- No "TBD", "TODO", "implement later", "add validation."
- One slightly soft step: Task 5 Step 4's "if you don't have a `~/.castle/palace` set up, skip this step." That's acceptable — Acceptance #4 is the "byte-identical legacy fields" check, and the spot-check is just one way to do it; the test suite (Task 5 Step 2) is the canonical verification.

**Type consistency:**
- `_get_filed_at(r) -> str` — same signature in Task 3 helper definition + nowhere else (single use site).
- Hit dict field names (`source_file`, `created_at`, `similarity`) — consistent across Task 3 (impl), Task 4 (smoke verification), Task 5 (acceptance check).
- `_get_filed_at(r)` — same call pattern in the hit-dict literal.
- `float(s)` aliased to both `score` AND `similarity` — same `s` variable from the `for s, r in reranked[:n_results]` loop.

**Spec-spec internal cross-references:**
- Components row (spec) says +16 LOC; plan matches (`import json` line + ~10 LOC helper + ~5 LOC new dict fields).
- "fixture timestamps too old" caveat (spec Testing section) → mirrored in Task 4 intro AND PR body's "Known constraint" section.
- "_get_filed_at handles missing/malformed JSON" (spec Error Handling) → built into the helper code in Task 3 Step 2.
