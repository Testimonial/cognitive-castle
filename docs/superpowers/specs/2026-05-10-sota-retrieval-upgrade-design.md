# Cognitive Castle — SOTA Retrieval Upgrade

**Date:** 2026-05-10
**Branch target:** develop
**Scope:** Replace the embedding model and re-architect the retrieval pipeline to a 2025 SOTA-class stack. Single project covering: bge-m3 dense embeddings, LanceDB Tantivy FTS for the sparse signal, cross-encoder reranking, knowledge-graph entity-hop retrieval, and a recency boost in fusion. Migration path is a clean rebuild from sources (no in-place re-embed).

## Background

Castle's current retrieval stack is from 2021-vintage components:

- Embedder: `all-MiniLM-L6-v2` — 384-dim dense vectors, English-tuned, modest quality by 2025 standards (`cognitive_castle/embedding.py:21`).
- Lexical signal: a custom Python tf-idf BM25 implementation embedded in `searcher.py` (`_bm25_scores` and `_hybrid_rank` functions, ~877 lines total).
- Fusion: ad-hoc weighted combination of BM25 + dense vector similarity in `searcher.py`.
- No reranker stage.
- The knowledge graph in `cognitive_castle/knowledge_graph.py` exists and stores entity-relationship data per drawer, but is not used as a retrieval signal.
- No recency or freshness signal in ranking.

Castle's content is mostly English with occasional Slovak/Czech (and possibly other languages). The current English-only embedder degrades on the foreign content. The custom BM25 is not as strong as a real production FTS.

The user has explicitly rejected three directions during brainstorming:
- HyDE (LLM at query time) — too much latency for the hook recall path.
- ColBERT-style multi-vector retrieval — diminishing returns once a cross-encoder reranker is in place.
- Quantization / Matryoshka — defer until palace size justifies it (past ~500K drawers).

This spec covers the rest: a coherent SOTA-ish stack that delivers the bulk of the retrieval-quality win without LLM-at-query-time complexity.

## Goals

1. Retrieval quality on Castle's existing benchmarks (`tests/benchmarks/convomem_bench.py`, `locomo_bench.py`, `longmemeval_bench.py`) measurably improves on Recall@10 and MRR vs. the current stack.
2. Multilingual retrieval: foreign-language content in the palace is searchable at quality comparable to English.
3. Hook-driven background recall stays within the 500ms latency budget per CLAUDE.md.
4. Interactive `/castle:search` returns results in under ~1.2 seconds on a modern CPU laptop.
5. The new retrieval pipeline is built from focused, unit-testable modules. `searcher.py`'s embedded BM25 + hybrid logic is removed; new responsibilities (reranker, fusion) live in their own files.

## Non-goals

- HyDE / LLM at query time. Deferred indefinitely; not in this project.
- bge-m3's learned sparse signal as a BM25 replacement (Plan A1, see "Sparse path ladder"). Targeted as a stretch follow-up after this ships, when LanceDB's sparse vector path can be validated against measured baselines.
- ColBERT-style multi-vector retrieval. Deferred.
- Quantization, binary embeddings, Matryoshka truncation. Deferred — not justified at personal-palace scale.
- In-place re-embedding migration of existing palace data. Per the brainstorming decision, rebuild from sources.
- Touching plugin work (`docs/superpowers/specs/2026-05-10-castle-claude-plugin-design.md` at commit `4084e93`) or the CLAUDE.md refresh (commit `6533e32`). Both resume after this ships.

## Source of truth (verified facts)

- Current embedder model: `all-MiniLM-L6-v2`, 384-dim, set at `cognitive_castle/embedding.py:21` (`_MODEL_NAME = "all-MiniLM-L6-v2"`).
- Current BM25: implemented inline in `cognitive_castle/searcher.py:62` (`_bm25_scores`) and `searcher.py:121` (`_hybrid_rank`).
- File sizes: `searcher.py` 877 lines, `embedding.py` 104 lines, `knowledge_graph.py` 441 lines, `lancedb_backend.py` 531 lines, `config.py` 350 lines.
- Existing dependencies in `pyproject.toml:25-31`: `lancedb>=0.20`, `sentence-transformers>=3.0`, `pyarrow>=14.0`, `pyyaml>=6.0,<7`, `tomli>=2.0.0; python_version < '3.11'`. **No FlagEmbedding currently.**
- Castle has a knowledge graph layer (`cognitive_castle/knowledge_graph.py`) and an entity registry (`cognitive_castle/entity_registry.py`) — both already populated during indexing.
- Castle has a benchmarking suite under `tests/benchmarks/` that this spec relies on for default-weight tuning.

## Sparse path ladder

Three plans, ranked by quality vs. risk:

- **Plan A1 (stretch, NOT in this spec):** bge-m3's learned sparse signal stored as a sparse vector column in LanceDB, retrieved via dot-product. Best quality (SPLADE-class). Requires the FlagEmbedding library and LanceDB sparse-vector retrieval at production scale, which is unverified for our use case.
- **Plan A2 (THIS SPEC's TARGET):** LanceDB's built-in full-text search via Tantivy as the sparse signal. Mature, no new dependency. Strictly better than custom Python tf-idf BM25. Documented and used by other LanceDB consumers in production.
- **Plan A3 (rejected):** Keep Castle's custom Python BM25. No reason to retain — Tantivy is better and free.

This spec ships Plan A2. Plan A1 becomes a follow-up project after A2 is in production with measured benchmark baselines, so we can A/B against a real reference rather than guess.

## Architecture

Three-stage retrieval pipeline:

1. **Recall (parallel):** three candidate sources fan out from a query.
   - 1a. Dense vector search via LanceDB → top-100 drawers.
   - 1b. Tantivy FTS sparse search via LanceDB → top-100 drawers.
   - 1c. KG-hop: query is matched against the entity registry, matched entities are resolved through the knowledge graph, drawers tagged with those entities are returned → top-50.
2. **Fusion:** the three candidate lists are combined with weighted Reciprocal Rank Fusion plus a recency multiplier per candidate. Output: top-K (K configurable, see "Reranker K cap").
3. **Rerank:** a cross-encoder model scores (query, drawer_text) pairs over the top-K candidates and reorders them. Output: top-10 returned to the caller.

## Models loaded at runtime

- bge-m3 embedder (`BAAI/bge-m3`): ~570 MB, 1024-dim dense vectors, multilingual (100+ languages). Loaded once via sentence-transformers, used for both indexing and querying.
- Cross-encoder reranker: device-aware selection.
  - GPU available: `BAAI/bge-reranker-v2-m3` (~568 MB, multilingual, top quality).
  - CPU only: `BAAI/bge-reranker-base` (~290 MB, English-tuned, ~3× faster than v2-m3 on CPU). Acceptable degradation on foreign content given user's "mostly English" content profile.
- Existing local LLM (used at index-time for entity refinement): unchanged.

## Reranker K cap

K = number of candidates fed into the cross-encoder. Configurable; defaults below assume CPU laptop:

- Interactive search (`/castle:search`, `/castle:status`, MCP tool calls during a session): **K = 20**. Reranker latency ~500ms–1s, total query latency under ~1.2s.
- Hook-driven background recall (Stop / PreCompact path): **K = 10**. Reranker latency ~250–500ms, fits the 500ms hook budget per CLAUDE.md.
- GPU available: K = 50 — rerank is fast on GPU and we want to use it.

K caps live in `config.py` as separate values (`reranker_k_interactive`, `reranker_k_hook`).

## KG-hop entity extraction at query time

Method: **entity registry lookup** (not regex, not LLM).

1. Castle's `cognitive_castle/entity_registry.py` already stores known entities (people, projects, etc.) populated during indexing.
2. At query time: tokenize query, lookup each token (and short n-gram windows) against the registry — exact match plus fuzzy match within an edit-distance threshold.
3. Resolved entity IDs are passed to `knowledge_graph.find_drawers_by_entities(entity_ids)` (new method; see file changes) to get the candidate drawer list.
4. If the query has no matched entities, KG-hop returns empty and Stage 2 fusion proceeds with only dense + sparse signals.

Latency: ~5–20ms (registry lookup + SQLite KG query). Cheap.

Future hook (NOT in this spec): optional LLM-assisted entity extraction for ambiguous queries, off by default.

## Fusion: RRF + recency

Weighted Reciprocal Rank Fusion with a per-candidate recency multiplier:

```
score(drawer) = recency_mult(drawer) × Σ_signal weight_signal / (k_rrf + rank_signal(drawer))
```

Where:
- `signal ∈ {dense, sparse, kg}`
- `rank_signal(drawer)` is the drawer's 1-indexed rank in that signal's candidate list (or `+∞` if absent).
- `recency_mult(drawer) = 1 + (recency_max_boost − 1) × exp(-age_days / recency_tau)` — so brand-new drawers get a multiplier of `recency_max_boost`, and old drawers approach 1.0.

Default values (placeholders, to be tuned via the benchmark suite during implementation):

| Knob | Default | Notes |
|---|---|---|
| `k_rrf` | 60 | Standard RRF k-parameter. |
| `weight_dense` | 1.0 | |
| `weight_sparse` | 1.0 | |
| `weight_kg` | 0.5 | KG hits are structurally precise but lower-recall, so weight is lower. |
| `recency_tau_days` | 90 | "Half-decay" timescale; tunable. |
| `recency_max_boost` | 1.5 | Newest drawer gets 1.5× score; capped to avoid drowning out genuine relevance. |

These are guesses. The implementation plan must include a "tune fusion weights against benchmark suite" step before final commit; the test of the weights is "Recall@10 / MRR meet or exceed the old-stack baseline."

## File-by-file changes

### Modified

- **`cognitive_castle/embedding.py`** — replace `_MODEL_NAME = "all-MiniLM-L6-v2"` with `"BAAI/bge-m3"`. Update dim from 384 to 1024 in any constants. Keep using sentence-transformers (no new dependency). Update docstring to reflect bge-m3 and multilingual.
- **`cognitive_castle/searcher.py`** — delete `_bm25_scores` and `_hybrid_rank` functions and all tf-idf-related code (~100 lines removed). Rewrite the search entry point as a 3-stage pipeline that calls into the new modules below. Estimated post-edit size: ~600 lines.
- **`cognitive_castle/backends/lancedb_backend.py`** — bump dense vector dimension from 384 to 1024 in schema. Add a Tantivy FTS index on the drawer text column (LanceDB FTS API). No new dependencies.
- **`cognitive_castle/knowledge_graph.py`** — add public method `find_drawers_by_entities(entity_ids: list[str], limit: int = 50) -> list[DrawerRef]`. Returns drawers tagged with any of the supplied entities, ranked by some heuristic (count of entity matches, recency, or just lexicographic — pick during implementation, defaults are tunable).
- **`cognitive_castle/entity_registry.py`** — add public method `lookup_in_text(query: str, max_edit_distance: int = 1) -> list[EntityMatch]`. Tokenizes the query and looks up tokens (plus short n-grams) in the registry with optional fuzzy match.
- **`cognitive_castle/config.py`** — add config keys: `embedder_model`, `embedder_dim`, `reranker_model_gpu`, `reranker_model_cpu`, `reranker_k_interactive`, `reranker_k_hook`, `kg_hop_top_n`, fusion weights (`k_rrf`, `weight_dense`, `weight_sparse`, `weight_kg`), recency knobs (`recency_tau_days`, `recency_max_boost`). Bump `embedder_identity` hash so old palaces are detected as incompatible on first read.

### Created

- **`cognitive_castle/reranker.py`** — wraps the cross-encoder. Lazy-loaded singleton, mirroring the pattern in `embedding.py`. Auto-detects device and picks the appropriate model variant. Public interface: `rerank(query: str, candidates: list[str]) -> list[float]` returns scores aligned to the input order.
- **`cognitive_castle/fusion.py`** — pure-functions module. `weighted_rrf(rank_lists: dict[str, list[DrawerRef]], weights: dict[str, float], k_rrf: int = 60) -> list[ScoredDrawer]` plus `apply_recency(scored: list[ScoredDrawer], now: datetime, tau_days: float, max_boost: float) -> list[ScoredDrawer]`. Easy to unit-test in isolation.

### Deleted

None. Deletions of chroma-related files are out of scope per the user's earlier decision to skip the chroma cleanup.

## Migration path

Per brainstorming decision: **rebuild from sources, no in-place re-embed.**

1. The `embedder_identity` hash in `config.py` is bumped (e.g., `embedder_identity = "bge-m3-1024-v1"`). On startup, the searcher / MCP server checks this against the palace's stored embedder identity.
2. If mismatch detected: print a clear message, e.g., `"Palace was indexed with a different embedder. Run 'castle reindex' to rebuild from sources."` Search returns no results until reindex.
3. New `castle reindex` command (a new CLI subcommand or a flag on `castle mine`):
   - Creates a new palace at `<palace>.new/` (sibling directory).
   - Walks all sources registered in the source registry (transcripts dir, project dirs).
   - Re-runs the mining pipeline against the new palace.
   - On completion: atomic rename — old palace → `<palace>.legacy/`, new → `<palace>/`.
   - Prints summary and instructs the user to delete `<palace>.legacy/` after verifying.
4. **Risk:** if a user's source files are gone (e.g., transcripts mined from a directory that's since been deleted), those drawers don't get rebuilt. Mitigation: nothing — accepted risk per the rebuild decision.

## Testing strategy

### Unit tests (new)

- `tests/test_fusion.py` — exhaustive tests of `weighted_rrf` (single signal, missing signals, weight effects, k_rrf effect) and `apply_recency` (zero age, large age, edge cases at recency_max_boost).
- `tests/test_reranker.py` — happy path: load reranker, score (q, doc) pairs, assert determinism. Smoke test only (don't pin specific model scores).
- `tests/test_kg_hop.py` — integration test: insert known entities + drawers via the existing test fixtures, query via `find_drawers_by_entities`, assert correct drawers returned in correct order.
- `tests/test_entity_registry_lookup.py` — `lookup_in_text` exact match, fuzzy match within distance, no match (empty result).

### Integration tests (new)

- `tests/test_retrieval_pipeline.py` — end-to-end: build a small palace, issue queries that should hit specific drawers via each retrieval signal (dense-dominant, sparse-dominant, KG-dominant, recency-dominant). Assert top-1 result is the expected drawer in each case.

### Modified tests

- `tests/test_searcher.py`, `tests/test_hybrid_search.py`, `tests/test_hybrid_candidate_union.py` — update assertions to match the new pipeline. Some tests probably need to be deleted because their underlying assumption (custom BM25) is gone; rewrite where possible, delete where not.
- `tests/test_embedding.py` — update for 1024-dim, bge-m3.
- `tests/test_backends.py` — update LanceDB schema test for new dim and FTS index.

### Benchmark suite — load-bearing

- Run `tests/benchmarks/convomem_bench.py`, `locomo_bench.py`, `longmemeval_bench.py` against the new stack. Compare Recall@10 and MRR to baseline (current stack on the same data).
- The implementation plan **must include a benchmark-driven tuning step**: try a few combinations of (weight_dense, weight_sparse, weight_kg, recency_tau, recency_max_boost) and pick the configuration that maximizes Recall@10 + MRR on the convomem benchmark. The chosen config becomes the default in `config.py`.
- Acceptance criterion: post-tuning, the new stack must Recall@10 ≥ baseline + 5%. If not, the upgrade hasn't earned its complexity and we should re-examine.

### Manual smoke (documented checklist, not automated)

1. After implementation: `pip install -e ".[dev]"`, then `castle reindex` on a small test palace.
2. Run `castle search "<query>"` for several queries — confirm latency under 1.2s.
3. Trigger a hook (or test the hook code path) — confirm latency under 500ms.

## Open questions for the implementation plan

1. **LanceDB FTS API surface.** Does it support fuzzy match, phrase queries, prefix queries, language-aware analyzers? Needed to confirm Plan A2 covers the cases Castle's current BM25 covers. Verify against current LanceDB version.
2. **bge-m3 prompt prefix usage.** The bge-m3 documentation (vs. older bge models) recommends *no prefix* on either queries or documents. Verify against bge-m3's current model card before the embedder swap lands.
3. **Reranker base model choice.** `bge-reranker-base` (English-tuned, faster) vs. `bge-reranker-v2-base-multilingual` (slower, multilingual). User's content is "mostly English with occasional other." Defer to impl-time benchmark on a multilingual subset of the test palace; pick the one that doesn't visibly degrade non-English queries.
4. **Fusion weights and recency parameters.** Defaults in this spec are placeholders. Implementation plan must include a benchmark-driven tuning task before the upgrade is considered complete.
5. **`castle reindex` semantics.** New subcommand vs. a flag on `castle mine`? Implementation decides; either works.
6. **Plan A1 (bge-m3 sparse) follow-up.** Out of this spec; flagged for a future project after this ships and a baseline is measured.

## Risk

- **Reranker latency on user's specific hardware.** The spec assumes typical CPU laptop. If the user's hardware is older or has memory pressure, the K caps may need to drop further. Mitigation: K is config-driven; a user-tunable knob if defaults don't fit.
- **Quality regression risk if fusion weights aren't tuned.** Defaults are guesses. The benchmark-driven tuning task in testing strategy is load-bearing; without it, the new stack may underperform the old on specific query types. Mitigation: the spec makes tuning a hard prerequisite for shipping.
- **Migration risk: lost drawers from gone sources.** Per user decision, accepted.
- **LanceDB schema change risk.** Bumping vector dim from 384 → 1024 is a schema break. The migration plan handles this by treating any old palace as incompatible and rebuilding. No subtle silent corruption — the dimension mismatch will fail loudly.
- **Reversible:** `git revert` plus rerunning the OLD `castle reindex` (which would re-embed with all-MiniLM) gets back to baseline. Risk is bounded.

## Acceptance criteria

1. `cognitive_castle/embedding.py` uses `BAAI/bge-m3`. `grep -n "all-MiniLM" cognitive_castle/` returns zero matches.
2. `cognitive_castle/searcher.py` no longer contains `_bm25_scores` or `_hybrid_rank`. The 3-stage pipeline is the entry point for retrieval.
3. `cognitive_castle/reranker.py` and `cognitive_castle/fusion.py` exist with the interfaces described above. Both have unit-test coverage.
4. `cognitive_castle/knowledge_graph.find_drawers_by_entities` and `cognitive_castle/entity_registry.lookup_in_text` exist and are tested.
5. The benchmark-driven tuning step has been completed and the chosen configuration is committed in `config.py` defaults.
6. `tests/benchmarks/convomem_bench.py` shows Recall@10 ≥ baseline + 5% on the new stack.
7. Manual smoke (above) passes: search latency under ~1.2s interactive, under 500ms hook recall, on the user's CPU laptop.
8. Existing test suite passes (with the modifications described in Testing strategy).
