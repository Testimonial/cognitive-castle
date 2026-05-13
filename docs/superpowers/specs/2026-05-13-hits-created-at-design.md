# Wire `created_at` + `source_file` + `similarity` through search hits — Design Spec

**Date:** 2026-05-13
**Status:** Revised after review (2026-05-13) — ready for implementation plan
**Scope:** small follow-up surfaced by PR #4a's Task 4 code review

## Revision history

- **2026-05-13 (initial):** First draft, approved.
- **2026-05-13 (post-review):**
  1. **`json` import claim corrected.** Initial spec said "json already imported at the top of searcher.py (used elsewhere)." Fresh-eyes review verified false: `grep -n "^import json" cognitive_castle/searcher.py` returns empty. The implementer must add `import json` to searcher.py's import block as part of this change.
  2. **Acceptance #2 framing tightened.** Was "failure count drops from 20 → 18" — fragile to unrelated flakes. Now "the 2 named tests turn green; `pytest tests/ --ignore=tests/benchmarks` shows no NEW failures vs. the develop baseline at commit `35f2151a`."
  3. **Added fixture-timestamp note.** `seeded_collection` `filed_at` values (January 2026) are 132+ days old as of 2026-05-13 — way past SOAR's 7-day recency threshold. So fixture-based tests don't verify the SOAR motivation; Acceptance #5 (live smoke on a fresh palace) is the only end-to-end verification of recency-boost firing.

## Background

The hit-dict construction at `cognitive_castle/searcher.py:475-487` (`_new_pipeline_search`'s return value) currently emits 6 fields per hit: `id`, `text`, `document`, `score`, `wing`, `room`. Three fields that downstream consumers expect are missing:

- **`source_file`** — already stored as a hoisted column in LanceDB drawers (`backends/lancedb_backend.py:61` lists it in `_HOISTED`), accessible via `r["source_file"]`.
- **`created_at`** — present in the drawer's `metadata_json` as `filed_at` (set in `miner.py:754, 900` at filing time). Requires JSON parse to extract.
- **`similarity`** — a float field expected by `test_result_fields` (type-only assertion; no caller reads the value).

This spec closes the gap. Two motivations:

1. **Unblocks SOAR's `recency-boost` rule (the real driver).** PR #4a's `soar_bridge.py:_compute_age_seconds` reads `hit["created_at"]` to compute drawer age; when missing it returns `float("inf")` → `recently-accessed = "false"` → `recency-boost` rule never fires. With this fix, the SOAR bridge becomes useful end-to-end in production, not just on synthetic test fixtures.
2. **Eliminates 2 chronic CI-UNSTABLE failures.** `test_result_fields` + `test_created_at_contains_filed_at` have been carried through PRs #1, #3, and #4a as "pre-existing failures." Investigation showed they're testing exactly this gap — written for a richer hit schema that never landed. Closing the gap makes them pass.

## Umbrella context

This is a follow-up to PR #4a, NOT a new sub-project of the SOTA-retrieval umbrella. The umbrella's 4 sub-projects (bge-m3, mxbai, LLM-judge, SOAR) are complete or deferred:

| # | Sub-project | Status |
|---|---|---|
| 1 | bge-m3 unblock | ✅ merged at `2118d1df` |
| 2 | mxbai swap | ⊘ deferred — multilingual reasons |
| 3 | LLM-judge Stage 4 | ✅ merged at `5f3f7385` |
| 4a | SOAR bridge | ✅ merged at `653b8208` |
| 4b | SOAR composable with LLM-judge | future |
| 4c | SOAR chunking + persistence | future |

**This PR is one of three queued follow-ups** named in PR #4a's umbrella context:

- bge-m3 default cutover (small PR)
- PR #2-redux docs-only mxbai opt-in (tiny PR)
- `gemma3:e4b` default-LLM-tag fix (small PR)
- **Wire `created_at` through hits — THIS SPEC** (small PR; promoted from the SOAR PR's "Known caveats" section)

## Goal

Add `source_file`, `created_at`, and `similarity` fields to every hit returned by `_new_pipeline_search` (and therefore by `search()`, `search_memories()`, and the MCP `castle_search` tool). Use existing drawer storage — no schema changes, no reindex required.

## Non-goals

- **Adding `filed_at` as a hoisted LanceDB column.** Would require palace reindex. JSON-parse path is sufficient and instant.
- **Computing `similarity` as a semantically distinct value** (e.g., cosine pre-rerank). The test asserts type only; aliasing to `score` is YAGNI-clean. If a future caller needs the pre-rerank cosine specifically, they can request that as a follow-up.
- **Surfacing other metadata fields** (`chunk_index`, `decay_score`, etc.) — not needed by tests or SOAR.
- **Touching the 3-stage retrieval pipeline.** The change is purely in the hit-dict construction at the end of `_new_pipeline_search`.

## Architecture

Single change site: `cognitive_castle/searcher.py`, the return-statement at lines 475-487.

Add three new fields to each hit dict:
- `source_file` ← `r.get("source_file", "")` (already a hoisted LanceDB column)
- `created_at` ← parsed from `r["metadata_json"]` via a new local helper `_get_filed_at(r) -> str`
- `similarity` ← `float(s)` (alias to `score`)

The `_get_filed_at` helper is defensive: returns `""` if `metadata_json` is missing, not a string, or malformed JSON.

**No new module dependencies. No cross-package coupling.** The helper reads `metadata_json` directly rather than calling `backends.lancedb_backend._row_to_metadata` (which is backend-private).

## Components (file-level changes)

| File | Change | LOC |
|---|---|---|
| `cognitive_castle/searcher.py` | Add `import json` to the import block (`json` is NOT currently imported — verified). Add `_get_filed_at(r)` helper (~10 LOC including docstring + json.loads + defensive try/except). Add 3 new fields to the hit dict at lines 475-487. | +16 |

**Total: ~16 LOC across 1 existing file.** No new modules, no new test files.

## Data flow

```
LanceDB drawer row r:
  {
    "id": ...,
    "vector": [...],
    "document": "...",
    "metadata_json": "{\"filed_at\": \"2026-01-01T00:00:00\", \"source_file\": \"auth.md\", ...}",
    "wing": "...", "room": "...", "source_file": "auth.md", ...
  }
  ↓
_new_pipeline_search builds hit dict (cognitive_castle/searcher.py:475-487):
  {
    "id": _extract_id(r),
    "text": _extract_text(r),
    "document": _extract_text(r),
    "score": float(s),
    "wing": r.get("wing", ""),
    "room": r.get("room", ""),
    # NEW:
    "source_file": r.get("source_file", ""),     # hoisted column, direct read
    "created_at": _get_filed_at(r),               # JSON-parse metadata_json → filed_at
    "similarity": float(s),                        # alias to score
  }
  ↓
Two downstream effects:
  1. test_result_fields + test_created_at_contains_filed_at start passing
  2. SOAR's _compute_age_seconds in soar_bridge.py now reads non-empty
     created_at, so the recency-boost rule fires (×1.25) on recent drawers
     when --soar-boost is enabled
```

### `_get_filed_at` helper contract

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

**`json` is NOT currently imported in `searcher.py`** (verified at review time via `grep -n "^import json" cognitive_castle/searcher.py` returning empty). The implementer must add `import json` to searcher.py's import block as part of this change (1 line, alongside the existing imports). The `_get_filed_at` helper's `json.loads` call depends on it.

## Error handling

| Failure | Behavior |
|---|---|
| `metadata_json` key missing on row dict | `_get_filed_at` returns `""`. Hit's `created_at` is `""`. SOAR's `_compute_age_seconds("")` returns `float("inf")` → no recency-boost. |
| `metadata_json` is not a string (e.g., None) | Same — `_get_filed_at` returns `""`. |
| `metadata_json` is malformed JSON | `json.JSONDecodeError` caught — returns `""`. |
| `filed_at` missing from the parsed metadata dict | Returns `""`. |
| `filed_at` present but not a string (e.g., int) | `str(meta.get("filed_at", ""))` coerces. SOAR's `_compute_age_seconds` handles malformed ISO via try/except → `inf`. |

**No new error types. No new exceptions raised. Pre-existing graceful-degrade semantics preserved.**

## Testing

### Two pre-existing tests turn green automatically

`tests/test_searcher.py::TestSearchMemories::test_result_fields` (line 47):
```python
def test_result_fields(self, palace_path, seeded_collection):
    result = search_memories("authentication", palace_path)
    hit = result["results"][0]
    assert "text" in hit
    assert "wing" in hit
    assert "room" in hit
    assert "source_file" in hit       # ← currently FAILS, will PASS
    assert "similarity" in hit         # ← currently FAILS, will PASS
    assert isinstance(hit["similarity"], float)  # ← passes once present
    assert "created_at" in hit         # ← currently FAILS, will PASS
```

`tests/test_searcher.py::TestSearchMemories::test_created_at_contains_filed_at` (line 58):
```python
def test_created_at_contains_filed_at(self, palace_path, seeded_collection):
    result = search_memories("JWT authentication", palace_path)
    hit = result["results"][0]
    assert hit["created_at"] == "2026-01-01T00:00:00"  # ← currently FAILS, will PASS
```

The `seeded_collection` fixture at `tests/conftest.py:118` sets `filed_at: "2026-01-01T00:00:00"` etc. — so the assertions match the fixture once the field is wired through.

### No new tests required

The chronic failures were testing EXACTLY this behavior. They've been documenting the gap. Closing the gap makes them pass. Adding new tests for the same behavior would be redundant.

### Important — fixture timestamps are too old for recency-boost

The `seeded_collection` fixture's `filed_at` values are January 2026 — 132+ days old as of 2026-05-13. SOAR's `recency-boost` rule fires only when `^recently-accessed = "true"`, which requires age < 7 days (default `RECENCY_THRESHOLD_SEC = 7 * 24 * 3600`). So fixture-based tests **will NOT verify recency-boost firing** — they only verify the `created_at` FIELD is present and correctly mapped.

Acceptance #5 (live smoke on a fresh palace) is the only end-to-end verification of the SOAR motivation (rule actually fires). Don't be surprised when fixture-driven tests pass but inspecting `soar_tags` shows `recency-boost` missing — that's correct given the fixture data is old.

### Optional smoke (verify SOAR motivation works end-to-end)

```bash
# Build a small palace
rm -rf /tmp/created-at-smoke
mkdir -p /tmp/created-at-smoke/{palace,src}
echo "auth notes" > /tmp/created-at-smoke/src/auth.md
castle reindex --palace /tmp/created-at-smoke/palace --sources /tmp/created-at-smoke/src --yes

# Run search with SOAR — drawer just filed → recent → recency-boost should fire
CASTLE_SOAR_ENABLED=1 CASTLE_PALACE_PATH=/tmp/created-at-smoke/palace \
  castle search "auth" --soar-boost 2>&1 | grep -E "score|soar"
```

Expected: hit has `created_at` populated AND (if MCP/JSON output mode) `soar_tags` includes `"recency-boost"`. The current CLI print format doesn't show audit fields by default, but the underlying boost would fire (verifiable via MCP or by inspecting score: post-boost should be `original × 1.25`).

## Acceptance criteria

1. `pytest tests/test_searcher.py -v -k "test_result_fields or test_created_at_contains_filed_at"` — **2 passed** (both currently fail).
2. `pytest tests/ --ignore=tests/benchmarks` — the 2 named tests turn green; **no NEW failures** vs. the develop baseline at commit `35f2151a` (the spec commit). Phrasing avoids an absolute failure-count number, which is fragile to unrelated flakes that might develop between now and merge.
3. `ruff check cognitive_castle/searcher.py` clean. `ruff format --check cognitive_castle/searcher.py` clean.
4. **Default behavior unchanged for existing fields:** `id`, `text`, `document`, `score`, `wing`, `room` still present with the same values. Only the 3 new fields are added.
5. **Live smoke (optional, for SOAR motivation):** small palace with newly-filed drawer → `castle search ... --soar-boost` → audit field `soar_tags` includes `"recency-boost"` (verifiable via MCP `castle_search` JSON output if CLI doesn't surface it).

## Out of scope

- New env-var configuration
- Schema changes to LanceDB tables
- Reindex of existing palaces
- Computing `similarity` as semantically-distinct cosine value
- Hoisting `filed_at` to a LanceDB column for indexed filtering
- Adding `filed_at` / `created_at` validation (timestamp format, range checks)
- Changes to hit dicts elsewhere (e.g., layers.py, sweep handlers) — only `_new_pipeline_search` touched

## Spec self-review (post-revision, 2026-05-13)

1. **Placeholders:** None. `_get_filed_at` body shown verbatim. Acceptance criteria are testable (one-liner commands).
2. **Internal consistency:** Architecture, Components, Data Flow, Testing all reference:
   - `cognitive_castle/searcher.py:475-487` as the single change site
   - 3 new fields with exact mapping (`source_file` from hoisted column; `created_at` from JSON-parsed `metadata_json.filed_at`; `similarity` aliased to `score`)
   - Helper `_get_filed_at(r) -> str` with defensive empty-string fallback
   - 2 pre-existing tests turn green; no new tests
   - `import json` must be added (Components row + helper-contract section both mention this)
3. **Scope:** Single-file, ~16 LOC change. Not decomposable into sub-projects.
4. **Ambiguity:** `similarity` semantics explicitly stated as alias to `score` (Non-goals). `created_at` source explicitly named as `filed_at` from `metadata_json` (Background + Data flow). Defensive empty-string behavior on missing/malformed data stated in 2 places (Error handling + helper docstring). Fixture-timestamp limitation stated explicitly in Testing (won't verify recency-boost firing; that's live smoke's job).
5. **Empirical grounding:**
   - `filed_at` confirmed in `miner.py:754, 900` (filing-time set)
   - `seeded_collection` fixture confirmed at `tests/conftest.py:118-168` with `filed_at: "2026-01-01T00:00:00"` etc. (verified via Read)
   - `source_file` confirmed as a hoisted column at `backends/lancedb_backend.py:61` (`_HOISTED` set)
   - `metadata_json` confirmed as the storage substrate at `backends/lancedb_backend.py:89, 221`
   - Only `test_result_fields` reads `similarity`, type-only (verified via grep)
   - `json` confirmed NOT yet imported in `searcher.py` (verified via grep — initial spec wrongly claimed it was, fixed in revision)
6. **Post-review #1 findings addressed:**
   - ✅ `json` import claim corrected (not currently imported — implementer must add).
   - ✅ Acceptance #2 tightened to "no NEW failures vs. develop baseline" instead of absolute count.
   - ✅ Fixture-timestamp limitation made explicit (won't fire recency-boost on fixture queries — only live smoke verifies SOAR motivation).
