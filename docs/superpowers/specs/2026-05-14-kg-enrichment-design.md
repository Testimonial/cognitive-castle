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
        ├── Step 2: Hydrate + Stage A — per-drawer extract + bounded corpus build
        │     mention_map  = defaultdict(set)   # name → {drawer_ids that mention it}
        │     corpus_freq  = Counter()           # name → freq within the corpus sample
        │     corpus_chunks = []                 # drawer texts in the corpus sample
        │     corpus_bytes = 0
        │     CORPUS_CAP_BYTES = cfg.entity_classify_corpus_cap  # NEW, default 10 MB
        │
        │     # Deterministic shuffle to avoid scan-order bias: the bounded
        │     # corpus window otherwise covers only the first N drawers in
        │     # LanceDB's scan order, leaving entities that appear exclusively
        │     # in later drawers unclassified. Seed by len(work_ids) so the
        │     # sample is stable for a given palace state (tests can assert
        │     # deterministic outcomes) but varies as the palace grows.
        │     work_ids_shuffled = list(work_ids)
        │     random.Random(len(work_ids_shuffled)).shuffle(work_ids_shuffled)
        │
        │     for batch in chunked(work_ids_shuffled, 1000):
        │       for row in col.get_by_ids(batch):
        │         text = row["text"]
        │         # ONE regex pass per drawer. The per-drawer extract drives
        │         # mention_map for EVERY drawer; for drawers selected into
        │         # the corpus window, the same per-drawer counts are summed
        │         # into corpus_freq. No second extract on combined_text — the
        │         # earlier design's double-regex pass is eliminated.
        │         per_drawer = entity_detector.extract_candidates(
        │           text, cfg.languages
        │         )
        │         for name in per_drawer:
        │           mention_map[name].add(row["id"])
        │
        │         if corpus_bytes < CORPUS_CAP_BYTES:
        │           corpus_chunks.append(text)
        │           corpus_bytes += len(text.encode("utf-8"))
        │           for name, count in per_drawer.items():
        │             corpus_freq[name] += count
        │
        │     combined_text = "\n".join(corpus_chunks)
        │     combined_lines = combined_text.splitlines()
        │     # corpus_freq IS the corpus_candidates dict — same shape, single
        │     # source of truth. Freq + scoring both come from the same
        │     # bounded sample, so signal stays consistent.
        │     corpus_candidates = corpus_freq
        │
        ├── Stage B: classify + promote (consistent corpus-wide signal)
        │     registry = EntityRegistry.load()
        │     threshold = cfg.entity_promote_threshold   # NEW config, default 0.70
        │
        │     for name, freq in corpus_candidates.items():
        │       # lookup() ALWAYS returns a dict with "type" ∈
        │       # {person, project, concept, unknown}. Check explicitly against
        │       # "unknown" — truthiness check would mis-classify all names.
        │       if registry.lookup(name).get("type") != "unknown":
        │         continue   # already known → keep mention_map entry for Stage C
        │
        │       scores = entity_detector.score_entity(
        │         name, combined_text, combined_lines, cfg.languages
        │       )
        │       cls = entity_detector.classify_entity(name, freq, scores)
        │
        │       if cls["type"] in ("person", "project") and cls["confidence"] ≥ threshold:
        │         registry.add_learned(
        │           name, type=cls["type"], confidence=cls["confidence"]
        │         )
        │       else:
        │         del mention_map[name]   # uncertain / rejected → no triples
        │
        │     # Names that appeared ONLY in drawers outside the classify-corpus
        │     # window are absent from corpus_candidates. They stay in mention_map
        │     # but only get Stage C triples if they were already registered.
        │     # This is intentional: unregistered names with too-weak corpus
        │     # presence to score reliably should not auto-promote.
        │     for name in list(mention_map):
        │       if name not in corpus_candidates and \
        │          registry.lookup(name).get("type") == "unknown":
        │         del mention_map[name]
        │
        │     registry.save()
        │
        └── Stage C: write triples for every entity remaining in mention_map
              # Includes pre-onboarded entities, not just newly-promoted ones.
              # Both flow through the same mention_map → KG path.
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
- **Signal-consistent** — corpus-wide frequencies AND scoring come from the same `combined_text` (bounded). No mismatch between corpus-wide freq and per-name sample-based scoring

### Performance estimate

- **Stage A (per-drawer extract + corpus build)**: 20K drawers × ~8 KB text. ONE `extract_candidates` regex pass per drawer (the earlier draft's double-pass on combined_text is eliminated). Estimate 1–5 minutes on this host
- **Stage B (classify)**: `score_entity` runs multiple regex passes (dialogue, person-verbs, pronoun proximity, project-verbs, versioned, code-ref) over the FULL `combined_text` (≤10 MB) per candidate. With ~10²–10³ candidates × ~10 MB × ~5 regex passes each: realistically **1–5 minutes**, not seconds. This is the dominant cost
- **Stage C**: `O(triples)` SQLite inserts in one transaction. Sub-second to seconds at the expected triple count (~200K worst case)
- **Total**: **3–10 minutes** for the user's 20K palace, no hard cap because Phase 2 runs post-mine. Plan can benchmark Stage B against representative samples and tighten if needed

### Storage growth

KG grows by ~one triple per `(entity, drawer)` mention. Worst-case 20K drawers × ~10 unique entities each = 200K triples. At ~100 bytes per SQLite row that's ~20 MB added to `knowledge_graph.sqlite3`. Registry JSON grows by entries for each newly-promoted entity (small — KB-scale at most).

### Memory profile

- `mention_map` worst case: a name in every drawer with a set of 20K drawer-id strings (~40 bytes each) = ~800 KB per name. With ~10³ names: ~800 MB upper bound. Realistic case (most names in few drawers): tens of MB
- `combined_text`: bounded to `cfg.entity_classify_corpus_cap` (default 10 MB)
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
| `cognitive_castle/config.py` | Add `entity_promote_threshold` (env `CASTLE_ENTITY_PROMOTE_THRESHOLD` → file_config → default `0.70`). Add `entity_classify_corpus_cap` (env `CASTLE_ENTITY_CLASSIFY_CORPUS_CAP` → file_config → default `10_485_760` bytes / 10 MB). If `cfg.languages` doesn't already exist, add it with env `CASTLE_LANGUAGES` (comma-separated) → file_config → default `("en",)` |
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
│   ├── drops mention_map entries for names that appear ONLY outside the
│   │     classify-corpus window (when unregistered)
│   ├── KEEPS mention_map entries for names that appear outside the window
│   │     when ALREADY registered (so onboarded entities still get triples)
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
    ├── corpus_cap honored — set cap to small value (e.g., 1 KB) and verify
    │     combined_text doesn't exceed it; verify mention_map still covers all
    │     drawers regardless of the cap
    ├── deterministic shuffle — given the same work_ids set, two runs produce
    │     the same corpus_chunks ordering (regression for the scan-order bias
    │     surfaced during spec review)
    └── shuffle covers entities outside scan-window — palace where entity 'X'
          appears ONLY in drawers whose LanceDB scan position is past the cap;
          deterministic shuffle places at least some of those drawers in the
          window across runs (entity X gets classified, not silently dropped)

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
6. **Stage A + Stage B time estimate calibration** — 3–10 min total for 20K drawers is a guess. Stage B (score_entity over 10 MB combined_text per candidate) dominates. Plan should benchmark Stage B on a representative subset before locking expectations
7. **Sampling-bias mitigation via deterministic shuffle** — random.Random seeded by `len(work_ids)` produces a stable shuffle for a given palace state. An entity that doesn't appear in the ~1250-drawer corpus window after shuffling still gets `mention_map` entries but won't be auto-promoted that run. On the NEXT mine (different `len(work_ids)`), the shuffle changes and the entity may land in-window. Plan should consider whether one mine's window is enough or whether to bump the cap higher for palaces above some size threshold
8. **score_entity per-candidate cost** — `score_entity` runs ~5 regex passes over the FULL `combined_text` per candidate. With 1000+ candidates × 10 MB text, Stage B is the dominant cost. If profiling shows it's the bottleneck, plan can either lower the cap or cache compiled patterns more aggressively (the existing impl already compiles patterns per call — caching across calls would help)

## Out of scope (acknowledged, deferred)

- **`same-project` SOAR production unblock** — needs per-project wing detection during ingest (folder, git remote, …). Separate spec
- **`stale-penalty` SOAR production** — needs "what counts as access" design + access-count persistence in KG/SMem. Separate spec
- **Real entity-entity triple extraction** — would enable `fact_checker.py`, temporal queries, real KG reasoning. Adds LLM dependency to ingest. Future spec if/when the simpler entity-mention indexing proves insufficient

## What this unlocks

After this spec ships:

- `entity-match` SOAR production fires when **a query mentions a named entity** (person/project/concept) that the registry knows about. Technical-topic queries with no entity names (e.g., "SOAR boost-tags retrieval pipeline") still won't trigger it — that's an inherent limit of the rule's design, not a bug
- KG-hop retrieval (Stage 1 of the search pipeline) starts contributing actual results instead of always returning empty
- The user's `~/.castle/palace` self-heals on next `castle mine`, retroactively indexing the 20K-drawer corpus that's been silent for `entity-match` since reindex
- Future onboarding flows can continue to seed the registry; this spec's adapter respects pre-existing entries and only adds learned ones
