# KG Auto-Enrichment During Ingest — Design Spec

**Date:** 2026-05-14
**Status:** Approved, ready for implementation plan
**Scope:** Make `entity-match` (the third SOAR production, shipped in PR #32 `#4c-entity-match`) actually fire on real Castle palaces by populating the knowledge graph + entity registry automatically as a Phase 2 of `castle mine` and `castle reindex`.

## Background

After shipping the SOAR audit-trail (PR #34), recency-on-pipeline fix (PR #35), and plural-room type-match fix (PR #36), a real-world stress test surfaced that `entity-match` never fires on actual queries — not because the rule is broken, but because the knowledge graph (`knowledge_graph.sqlite3`) is empty.

Investigation: neither `miner.py` nor `convo_miner.py` ever writes to the KG. The KG is only populated via the explicit MCP `castle_kg_add` tool (`mcp_server.py:878`). The entity_registry (`entity_registry.json`) is only populated by the onboarding flow. Both KG-hop retrieval and entity-match rely on data that ingest doesn't produce.

This spec closes that gap with a minimum-viable approach: **entity-mention indexing**. No relationship extraction, no LLM dependency, no schema design. During ingest, scan drawer text for entity mentions, promote high-confidence candidates to the registry, and write `(entity, mentioned_in, drawer_id)` triples whose provenance ties the entity back to the drawer.

## Goals

- Make `entity-match` SOAR production fire on real queries against a stress-tested palace
- Populate `entity_registry.json` + `knowledge_graph.sqlite3` as a natural consequence of `castle mine` / `castle reindex` — no separate command, no migration step
- Self-heal an existing palace (e.g., the user's current 20K-drawer palace) on next mine
- Stay local-only (regex + signal counts; no LLM, no network)
- Honor Castle's append-only and incremental promises

## Non-goals

- **Relationship extraction** (real subject-predicate-object triples). Defer until/if needed; entity-mention indexing alone unblocks the SOAR umbrella's `entity-match` rule
- **Per-project wing splitting** (would unblock `same-project` production). Separate spec
- **`castle kg-backfill` standalone command**. Self-healing inside `mine` covers every realistic case; a standalone adds zero capability
- **Interactive entity confirmation** (hybrid auto-discover + manual review). Threshold-based auto-promotion is sufficient; false-positive entries in the registry produce only noisy boosts, not wrong results
- **Concurrency tests** for simultaneous `castle mine` processes. Correctness relies on SQLite WAL + `INSERT OR IGNORE`; we trust those primitives rather than write flaky timing-sensitive tests

## Key insight — every primitive already exists

Castle already ships:

- `entity_detector.py` (733 LOC) — regex + signal-counting candidate extraction, multi-language via `cfg.languages`. Used today only by `castle init` onboarding
- `entity_registry.py` (768 LOC) — load/save, lookup, learn-from-text. Used today only by onboarding
- `knowledge_graph.py` — SQLite triples table with the `source_drawer_id` provenance column (RFC 002 §5.5)
- `searcher.py` — KG-hop already integrated into the 3-stage pipeline (`searcher.py:517`); fires automatically when the registry + KG have data

The gap is solely the write path during ingest. This spec adds one module (`kg_enricher.py`) that wires the existing primitives together at the end of mining.

## Architecture & data flow

```
castle mine / castle reindex
  │
  ├── PHASE 1 (today's behavior, unchanged)
  │     chunk files → write drawers → upsert with metadata_json
  │
  └── PHASE 2 (NEW: KG enrichment)
        │
        ├── Step 1: Work-set selection (no cross-store query)
        │     all_ids  = LanceDB.list_drawer_ids()                    # one indexed scan
        │     done_ids = KG: SELECT DISTINCT source_drawer_id
        │                    FROM triples
        │                    WHERE adapter_name = 'entity-mention-indexer'
        │                    AND source_drawer_id IS NOT NULL
        │     work_ids = all_ids − done_ids                           # Python set-diff
        │
        │     Filtering by adapter_name is critical: a drawer with triples
        │     from a different adapter (e.g., manual castle_kg_add) must
        │     still be visible to this adapter's work-set.
        │
        ├── Step 2: Stage A — corpus-wide extract (single regex pass per drawer)
        │     mention_map  = defaultdict(set)   # name → {drawer_ids that mention it}
        │     freq_by_name = Counter()           # name → corpus-wide frequency
        │
        │     for batch in chunked(work_ids, 1000):
        │       for row in col.get_by_ids(batch):
        │         per_drawer = entity_detector.extract_candidates(
        │           row["text"], cfg.languages
        │         )
        │         for name, count in per_drawer.items():
        │           mention_map[name].add(row["id"])
        │           freq_by_name[name] += count
        │
        │     # No combined_text, no shuffle, no sample window. Every drawer
        │     # contributes to both mention_map and freq_by_name.
        │
        ├── Stage B: classify + promote (per-candidate sampling for scoring)
        │     registry = EntityRegistry.load()
        │     threshold = cfg.entity_promote_threshold       # NEW, default 0.70
        │     SAMPLE_N  = cfg.entity_score_sample_drawers    # NEW, default 20
        │
        │     # Collect drawer_ids needed for Stage B scoring. Only fetch
        │     # drawers used to score UNREGISTERED candidates — registered
        │     # entities skip scoring entirely.
        │     candidates_to_score = [
        │       name for name in freq_by_name
        │       if registry.lookup(name).get("type") == "unknown"
        │     ]
        │     score_drawer_ids = set()
        │     for name in candidates_to_score:
        │       # Sort the drawer-id set for determinism; take first SAMPLE_N.
        │       sample_ids = sorted(mention_map[name])[:SAMPLE_N]
        │       score_drawer_ids.update(sample_ids)
        │
        │     # Batched bulk fetch. col.get_by_ids returns full rows including
        │     # the 1024-dim vector column (~4 KB) and metadata_json — so per-row
        │     # footprint is ~12-15 KB. With 5K-15K unique sample ids realistic
        │     # for a 20K-drawer palace, a single fetch can hit 60-200 MB.
        │     # Batching keeps per-call memory bounded.
        │     FETCH_BATCH = cfg.entity_fetch_batch_size   # NEW, default 1000
        │     text_by_id = {}
        │     for batch in chunked(sorted(score_drawer_ids), FETCH_BATCH):
        │       for r in col.get_by_ids(batch):
        │         text_by_id[r["id"]] = r["text"]   # discard vector + metadata
        │
        │     for name in candidates_to_score:
        │       sample_ids = sorted(mention_map[name])[:SAMPLE_N]
        │       sample_texts = [text_by_id[did] for did in sample_ids]
        │       sample = "\n".join(sample_texts)
        │       scores = entity_detector.score_entity(
        │         name, sample, sample.splitlines(), cfg.languages
        │       )
        │       cls = entity_detector.classify_entity(
        │         name, freq_by_name[name], scores
        │       )
        │       if cls["type"] in ("person", "project") and cls["confidence"] ≥ threshold:
        │         registry.add_learned(
        │           name, type=cls["type"], confidence=cls["confidence"]
        │         )
        │       else:
        │         del mention_map[name]   # uncertain / rejected → no triples
        │
        │     registry.save()
        │
        │     # No cleanup loop. Every candidate gets scored against drawers
        │     # that actually mention it; no name is silently dropped due to
        │     # falling outside a corpus window.
        │
        └── Stage C: write triples for every entity remaining in mention_map
              # Includes pre-onboarded entities (skipped scoring in Stage B
              # but still mapped to drawer_ids) AND newly-promoted ones.
              for name, drawer_ids in mention_map.items():
                if registry.lookup(name).get("type") == "unknown":
                  continue   # safety net: only emit for confirmed entities
                for drawer_id in drawer_ids:
                  kg.add_triple(
                    subject=name,
                    predicate="mentioned_in",
                    object=drawer_id,
                    source_drawer_id=drawer_id,   # same value — quirk of using
                                                  # triple-store for mention-index
                    adapter_name="entity-mention-indexer",
                  )
              # add_triple uses INSERT OR IGNORE → safe to re-run
```

### Invariants

- **Append-only** — never deletes existing triples or registry entries
- **Idempotent on unchanged state** — re-running with no new drawers: work_ids = ∅, Phase 2 exits without writes. With new drawers, only the new drawers' triples get added; existing triples untouched
- **Self-healing** — interrupt mid-Phase-2, next run resumes via the set-diff
- **Adapter-scoped** — work-set filter is per-`adapter_name`, so manual `castle_kg_add` entries don't mask un-indexed drawers
- **Local-only** — regex + signal-counting + JSON registry + SQLite KG. No LLM, no network. `cfg.languages` controls i18n
- **Stale-tolerant** — drawer_id changes after re-chunking → stale triples reference dead ids; `col.get_by_ids` drops missing rows on read (graceful degradation, no garbage collection)
- **Bias-free sampling** — every candidate gets scored against drawers that actually mention it. No name is silently dropped due to falling outside a corpus window. freq is corpus-wide; scoring sample is per-candidate and consistent with the entity itself
- **Deterministic** — same palace state produces the same triples. Sampling uses `sorted(mention_map[name])[:N]`, no RNG

### Coverage semantics (known limitation)

The work-set query treats a drawer as "done" if it has any triple from this adapter. Combined with mid-stream entity promotion, this produces a coverage gap:

If entity X gets promoted on mine N, only drawers in mine N's `work_ids` (typically new drawers since the last mine) get `mentioned_in` triples for X. Drawers indexed in earlier mines stay un-tripled for X, even if X appears in them.

**For the bootstrap scenario this is fine.** The first mine after this spec ships has `done_ids = ∅`, so `work_ids = all_ids`. Every entity promoted in that first mine gets full palace coverage. The user's current 20K-drawer palace gets bootstrapped completely on next mine.

**For long-running palaces, late-discovered entities have weaker coverage.** If a user starts mentioning a new person months in, the new person gets promoted in a later mine but only earns triples for drawers added since then. Older conversations stay invisible to entity-match for that person.

**Pre-registered entities only get triples where `extract_candidates` matches them.** If a user runs `castle init` and seeds "Riley" as a person, but drawer text uses lowercase "riley" or a pattern the regex doesn't match, then `mention_map["Riley"]` is empty after Stage A and Stage C writes zero triples. The registry says Riley exists, but the KG has no `mentioned_in` triples → entity-match still doesn't fire for queries about Riley.

In practice this means onboarding-seeded entities only earn KG coverage proportional to how well the canonical name from the registry overlaps with how `entity_detector` extracts candidates from drawer text. Casing variation, nicknames, and partial-name mentions all reduce coverage.

Mitigations (out of scope for this spec, deferred):
- A `Stage B.5: rescan-for-newly-promoted` step that uses LanceDB FTS to find pre-existing drawers mentioning newly-promoted entities. Cheap (one FTS query per newly-promoted name) but adds complexity. FTS-based mention indexing would ALSO fix the seeded-entity coverage gap (FTS matches substring, not entity pattern)
- An explicit `castle kg-rescan` command for users who want to refresh coverage after registry changes

This spec ships the simpler design; the bootstrap case (no prior onboarding, no pre-existing entities, fresh adapter run) is the common case, and the mitigation can land as a follow-up if late-discovery or onboarding-mismatch weakness shows up in practice.

### Performance estimate

- **Stage A (per-drawer extract)**: 20K drawers × ~8 KB text. ONE `extract_candidates` regex pass per drawer. Estimate **1–3 minutes** on this host
- **Stage B (classify with per-candidate sampling)**: ~10²–10³ candidates × `score_entity` against a per-candidate sample of ~20 drawer texts (~160 KB each). With ~5 regex passes per call × 160 KB × 1000 candidates: realistically **5–30 seconds**, dominated by the bulk drawer fetch (one LanceDB query). Order of magnitude faster than v3's full-`combined_text` scoring
- **Stage C**: `O(triples)` SQLite inserts in one transaction. Sub-second to seconds at the expected triple count (~200K worst case)
- **Total**: **1–4 minutes** for the user's 20K palace, no hard cap because Phase 2 runs post-mine. Plan can benchmark and tighten if needed

### Storage growth

KG grows by ~one triple per `(entity, drawer)` mention. Worst-case 20K drawers × ~10 unique entities each = 200K triples. At ~100 bytes per SQLite row that's ~20 MB added to `knowledge_graph.sqlite3`. Registry JSON grows by entries for each newly-promoted entity (small — KB-scale at most).

### Memory profile

- `mention_map` worst case: a name in every drawer with a set of 20K drawer-id strings (~40 bytes each) = ~800 KB per name. With ~10³ names: ~800 MB upper bound. Realistic case (most names in few drawers): tens of MB
- `freq_by_name`: ~10² to 10³ entries × ~50 bytes = KB-scale
- `score_drawer_ids` set: union of per-candidate sample-id sets. Realistic 5K-15K unique drawer_ids for a 20K palace with 10³ unregistered candidates (overlap depends on candidate distribution)
- `text_by_id` for Stage B: discards LanceDB's vector + metadata_json columns, keeping only `text`. At ~8 KB per drawer text × 10K drawers = ~80 MB realistic, ~120 MB worst case. NOT "tens of MB" as earlier drafts claimed
- LanceDB bulk fetch is batched (default `FETCH_BATCH = 1000`) so per-call response stays bounded; the cumulative `text_by_id` after all batches is the figure above
- No `combined_text` corpus exists in this design — the per-candidate sampling means there's no global text buffer
- If `mention_map` proves too large at very-large-palace scale, plan can switch to a streaming Stage C that flushes triples per-batch rather than holding all mentions in memory

## Component changes / file map

### NEW files

| File | Purpose |
|---|---|
| `cognitive_castle/kg_enricher.py` | Public entry `enrich_palace(palace_path, cfg) -> dict`. Returns `{"drawers_scanned": int, "entities_promoted": int, "triples_written": int, "elapsed_s": float}`. Internal helpers (`_walk_corpus`, `_classify_and_promote`, `_write_triples`) are private |
| `tests/test_kg_enricher.py` | Per-stage unit tests + one end-to-end integration test against a temp palace (mirrors the `test_soar_bridge.py` fixture pattern) |

### MODIFIED files

| File | Change |
|---|---|
| `cognitive_castle/miner.py` | At end of `mine()` (line 985), lazy-import + call `enrich_palace(palace_path, cfg)`. Wrap in `try/except Exception` — never re-raise. On exception, print a one-line warning and continue. On success, print one line: `KG enrichment: scanned N drawers, promoted M, wrote K triples in T.Ts` |
| `cognitive_castle/convo_miner.py` | Same hook at end of `mine_convos()` (line 379). Inline (not via a shared helper) — the call is 4–5 lines including try/except, and a 3-line helper adds indirection without saving meaningful code |
| `cognitive_castle/config.py` | Add `entity_promote_threshold` (env `CASTLE_ENTITY_PROMOTE_THRESHOLD` → file_config → default `0.70`). Add `entity_score_sample_drawers` (env `CASTLE_ENTITY_SCORE_SAMPLE_DRAWERS` → file_config → default `20`). Add `entity_fetch_batch_size` (env `CASTLE_ENTITY_FETCH_BATCH_SIZE` → file_config → default `1000`). If `cfg.languages` doesn't already exist, add it with env `CASTLE_LANGUAGES` (comma-separated) → file_config → default `("en",)` |
| `cognitive_castle/entity_registry.py` | Add `add_learned(name, type, confidence) -> None` method. Idempotent: if entity already exists, no-op (does not overwrite onboarding-sourced entries). Returns nothing — callers already guard with `lookup(name).get("type")` before calling |
| `cognitive_castle/backends/base.py` | Add abstract `list_drawer_ids(self) -> list[str]` to `BaseCollection` |
| `cognitive_castle/backends/lancedb_backend.py` | Implement via `table.to_arrow().column("id").to_pylist()` — materializes the full id list (~2 MB for 20K rows, ~10 MB for 100K) |
| `cognitive_castle/backends/chroma.py` | Implement for the legacy `CASTLE_BACKEND=chroma` path. Chroma's `.get(include=[])` returns ids in the result dict by default |
| `CLAUDE.md` | One-line note in the Architecture section after the palace-structure diagram: "Phase 2 of `castle mine` / `reindex` runs KG enrichment (`kg_enricher.py`) over un-indexed drawers — populates `entity_registry.json` + `knowledge_graph.sqlite3` with `(entity, mentioned_in, drawer_id)` triples" |

### Import direction (avoids circularity)

```
miner.py  ──→  (lazy import) kg_enricher.py
convo_miner.py  ──→  (lazy import) kg_enricher.py
                                      │
                                      ├─→  palace.get_collection (already public)
                                      ├─→  entity_detector  (public primitives)
                                      ├─→  entity_registry  (public API + new add_learned)
                                      └─→  knowledge_graph  (public add_triple)
```

`kg_enricher` imports nothing from `miner.py` / `convo_miner.py`. Miners import enricher *lazily* (inside `mine()` / `mine_convos()`, after the main loop completes) to keep import cost off the hot path and to keep cycles impossible.

### Observability format

```
KG enrichment: scanned 12 drawers, promoted 3 entities, wrote 47 triples in 1.4s
KG enrichment: no un-indexed drawers (skipped)
KG enrichment FAILED (RuntimeError: ...) — palace unaffected; rerun mine to retry
```

Stdout (matches miner's own progress lines).

### Failure modes

- SQLite locked → catch, warn, continue
- Registry JSON corrupt → `entity_registry` already has a load-failure path; surfaces as a warning, Phase 2 skipped that run
- LanceDB read error → same: warn, continue, retry next mine
- `KeyboardInterrupt` / `SystemExit` → not caught (propagate as today)

### Concurrent-run safety

- Two `castle mine` processes start simultaneously → both compute set-diff against same baseline → both try to write overlapping triples
- KG uses SQLite WAL mode (already enabled). `INSERT OR IGNORE` makes the collision a no-op
- LanceDB allows concurrent readers; both processes only *read* drawer ids in Phase 2, no contention
- Registry writes (`registry.save()`): last-writer wins on the JSON file. Acceptable — entity sets are append-only and converge

## Testing strategy

### Coverage targets

- New code in `kg_enricher.py`, `EntityRegistry.add_learned`, both backend `list_drawer_ids` → hit Castle's 85% threshold
- Miner-side hook tested for invocation + failure isolation
- No performance test — Phase 2 runs post-mine with no user-facing latency budget; budget violations surface via the elapsed-time stdout line

### Test file map

```
tests/test_kg_enricher.py          (NEW)
├── walker (Stage A)
│   ├── extracts candidates from a single text
│   ├── accumulates frequencies across drawers
│   ├── records drawer_ids per name (mention_map)
│   └── honors cfg.languages tuple
│
├── classify_and_promote (Stage B)
│   ├── promotes candidates with confidence ≥ threshold
│   ├── skips candidates below threshold
│   ├── skips entities already in registry (lookup type ≠ "unknown")
│   ├── correctly treats "unknown" type as not-yet-registered (regression for
│   │     the truthy-check bug surfaced during spec review)
│   ├── drops mention_map entries for rejected candidates
│   ├── per-candidate sample uses sorted(mention_map[name])[:SAMPLE_N] —
│   │     deterministic across runs
│   ├── bulk fetch — score_drawer_ids union pre-computed, batched
│   │     col.get_by_ids calls (no per-candidate LanceDB round-trip;
│   │     batch size bounded by entity_fetch_batch_size)
│   ├── entity_fetch_batch_size honored — set to 2, populate >2
│   │     score_drawer_ids, assert multiple get_by_ids invocations
│   │     and that each batch contains ≤2 ids
│   └── promotes only types "person"/"project" (not "uncertain"/"concept")
│
├── write_triples (Stage C)
│   ├── writes one triple per (entity, drawer_id) pair
│   ├── stamps adapter_name="entity-mention-indexer"
│   ├── writes for pre-onboarded entities too (not just newly promoted)
│   └── re-run on same state writes zero new triples
│
├── work_set selection
│   ├── excludes drawer_ids already covered by this adapter's triples
│   ├── INCLUDES drawer_ids covered by a different adapter's triples
│   ├── returns empty when palace is empty
│   └── returns empty when all drawers already indexed
│
├── enrich_palace integration (against tmp_path palace)
│   ├── end-to-end on small fixture (3 drawers, 2 entities)
│   ├── returns dict {drawers_scanned, entities_promoted, triples_written, elapsed_s}
│   ├── returns zeros + does not crash on empty palace
│   └── idempotent: second call produces identical KG state
│
└── edge cases
    ├── drawer with empty text → no candidates extracted, no crash
    ├── drawer in language outside cfg.languages → no candidates
    ├── corrupt registry JSON → warning + skipped run, no crash
    ├── KG file missing → KnowledgeGraph constructor creates schema, succeeds
    ├── 1000-drawer batch boundary respected — fresh palace with 2500 drawers,
    │     work_ids = 2500, expect 3 batches of (1000, 1000, 500)
    ├── per-candidate sample size honored — set SAMPLE_N=2 and verify
    │     score_entity receives a sample built from at most 2 drawers per name
    ├── rare entities still get classified — palace where entity 'X' appears
    │     in exactly 1 drawer; mention_map[X] = {one_id}; X is included in
    │     candidates_to_score; sample is that one drawer's text (no bias-driven
    │     silent drop, regression for the v3 scan-window bias)
    └── coverage-gap acknowledged — entity promoted on mine 2 does NOT get
          triples for drawers added on mine 1 (documented limitation, not bug)

tests/test_entity_registry.py      (EXISTING — append)
├── add_learned: idempotent when name already present
├── add_learned: does not overwrite source="onboarding" entries
└── add_learned: persists to JSON on save

tests/test_lancedb_backend.py      (EXISTING — append)
├── list_drawer_ids returns all ids
└── list_drawer_ids returns [] for empty palace

tests/test_chroma.py               (EXISTING — append)
├── list_drawer_ids returns all ids
└── list_drawer_ids returns [] for empty palace

tests/test_miner.py                (EXISTING — append)
├── mine() invokes enrich_palace after main loop
└── mine() continues + returns success when enrich_palace raises

tests/test_convo_miner.py          (EXISTING — append)
├── mine_convos() invokes enrich_palace after main loop
└── mine_convos() continues + returns success when enrich_palace raises
```

### Test patterns

- Mock-light fixtures: use the existing `tmp_path` + `palace.get_collection` pattern from `test_soar_bridge.py`; build a 3-drawer palace by hand, run `enrich_palace`, assert the KG SQLite + registry JSON
- For miner integration, monkeypatch `kg_enricher.enrich_palace` with a stub that records invocation / raises on demand — keeps miner tests fast (no real palace work)
- For backend tests, follow Castle's existing per-backend pattern (`test_lancedb_backend.py` already exists)

## Risk register (what could surprise us in implementation)

1. **`classify_entity` return-type surface forms** — the `cls["type"]` value may include surface forms beyond `"person"` / `"project"` / `"uncertain"` (possibly `"persona"` from the `_tag_as_persona` path in `entity_detector.py:550`). Plan should grep entity_detector for actual return-type values before locking the "promote only person/project" condition
2. **Empty registry on disk** — the user's machine has no `entity_registry.json` today (onboarding never run). Test fixtures must create it (or rely on `EntityRegistry.load()` empty-default path). Plan should verify that path works without onboarding having been run
3. **LanceDB `to_arrow()` memory profile** — pulling the full id column for a 1M-drawer palace is ~100 MB, possibly fine but worth checking. If problematic, switch to chunked iteration in plan, not in spec
4. **`extract_candidates` API shape verified** — returns `dict[name, count]` (`entity_detector.py:144`). No risk
5. **`lookup()` return shape verified** — always returns a dict with `"type"` key ∈ `{person, project, concept, unknown}` (`entity_registry.py:443`). Spec uses explicit `!= "unknown"` checks. No risk
6. **Stage A time estimate calibration** — 1–3 min for 20K drawers is a guess. Plan should benchmark on a representative subset before locking expectations
7. **score_entity per-candidate behavior on small samples** — the existing `score_entity` was designed against larger combined corpora (e.g., onboarding's 50 KB). On a ~160 KB per-candidate sample, dialogue-marker heuristics that need `>=2` hits may not fire even for real persons. Plan should verify classifier behavior empirically on small samples and adjust SAMPLE_N default if needed
8. **LanceDB bulk fetch batching** — Stage B batches `get_by_ids` calls at `entity_fetch_batch_size` (default 1000) to keep per-call response memory bounded. Plan should verify that batch size doesn't trigger LanceDB performance pathologies (e.g., per-call overhead dominating)
9. **Pattern compilation caching in `entity_detector`** — `score_entity` calls `_build_patterns(name, langs)` per call, which likely compiles regexes from scratch. Stage B invokes `score_entity` ~10²-10³ times; if patterns aren't cached across calls, those compilations could dominate Stage B's wall-clock time. Plan should grep `entity_detector.py` for `_build_patterns` and verify either it caches internally or our enricher caches per-language compiled patterns externally. If neither, add a `@functools.lru_cache` to `_build_patterns` as a small optimization

## Out of scope (acknowledged, deferred)

- **`same-project` SOAR production unblock** — needs per-project wing detection during ingest (folder, git remote, …). Separate spec
- **`stale-penalty` SOAR production** — needs "what counts as access" design + access-count persistence in KG/SMem. Separate spec
- **Real entity-entity triple extraction** — would enable `fact_checker.py`, temporal queries, real KG reasoning. Adds LLM dependency to ingest. Future spec if/when the simpler entity-mention indexing proves insufficient
- **Stage B.5 rescan-for-newly-promoted** — fixes the coverage-semantics limitation (late-discovered entities miss old drawers). FTS-based rescan would be cheap (one query per newly-promoted name) but adds a stage. Ship the simpler design first; add this if late-discovery weakness shows up in practice
- **`castle kg-rescan` command** — explicit user-triggered re-processing after registry edits. Same motivation as Stage B.5; same out-of-scope rationale

## What this unlocks

After this spec ships:

- `entity-match` SOAR production fires when **a query mentions a named entity** (person/project/concept) that the registry knows about. Technical-topic queries with no entity names (e.g., "SOAR boost-tags retrieval pipeline") still won't trigger it — that's an inherent limit of the rule's design, not a bug
- KG-hop retrieval (Stage 1 of the search pipeline) starts contributing actual results instead of always returning empty
- The user's `~/.castle/palace` self-heals on next `castle mine`, retroactively indexing the 20K-drawer corpus that's been silent for `entity-match` since reindex
- Future onboarding flows can continue to seed the registry; this spec's adapter respects pre-existing entries and only adds learned ones
