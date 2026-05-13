# SOAR `entity-match` Rule + Fusion Provenance (PR #4c-entity-match) — Design Spec

**Date:** 2026-05-13
**Status:** Approved, ready for implementation plan
**Scope:** First slice of the SOAR umbrella's #4c — unblocks the `entity-match` rule deferred from PR #4a by threading hit-provenance from `fusion.py` through to SOAR's working memory.

## Background

PR #4a (merged at `653b8208`) shipped 2 SOAR productions (`recency-boost`, `same-project`). Three rules were deferred to #4c because they depended on data fields the pipeline didn't expose:

- `entity-match` — needs to know whether a hit came via the KG-hop recall path
- `type-match` — needs drawer-type metadata (decision/preference/milestone)
- `stale-penalty` — needs an access-count or last-accessed timestamp

The `#4c` framing in #4a's spec was "chunking + persistent learning across sessions" — a research-scale project that bundles 4 distinct concerns (learning signal, chunking, persistence, data-fields gap). On reflection, the data-fields gap is the only concretely shippable piece RIGHT NOW; the other three depend on harder questions (what's a learning signal? what counts as access?) that don't have settled answers.

This PR is the smallest unit of "rules unblock" — the `entity-match` rule alone. It validates the pattern for adding SOAR rules that consume real pipeline signals (vs. the hardcoded recency/wing fields #4a's 2 rules used). After this ships, `type-match` and `stale-penalty` can each get their own spec when there's appetite.

## Umbrella context

| Sub-PR | Scope | Status |
|---|---|---|
| **#4a** | SOAR bridge + post-pipeline boost-tags + 2 initial rules | ✅ Merged at `653b8208` |
| **#4b** | SOAR ↔ LLM-judge composable order | ✅ Merged at `764db36e` |
| **#4c-entity-match — THIS SPEC** | Third SOAR rule (`entity-match`) + fusion provenance plumbing | Designing now |
| #4c-type-match | Fourth SOAR rule (drawer-type matching) — needs schema work + query intent classification | Deferred to its own spec |
| #4c-stale-penalty | Fifth SOAR rule (penalty for unaccessed drawers) — needs "what counts as access" design | Deferred to its own spec |
| #4c-learning | Active learning from LLM-judge disagreement (the original "research payoff" framing) | Deferred indefinitely; revisit after rules-unblock work has shipped and exposed real signal |

## Goal

1. **Track hit provenance through `fusion.py`.** Add `contributing_signals: frozenset[str]` to `ScoredCandidate`. Populate it during `weighted_rrf` from the per-signal rank lists. Preserve it through `apply_recency`.

2. **Thread the entity-match flag into row dicts.** In `_new_pipeline_search`, after `weighted_rrf` + `apply_recency`, derive `entity_match_by_id = {drawer_id: "kg" in contributing_signals}` from the top-K `ScoredCandidate`s and attach `row["entity_match"] = bool` to each LanceDB row before cross-encoder rerank.

3. **Wire `entity-match` into SOAR's working memory.** Update `_push_working_memory` to set `^entity-match true|false` on each memory WME. Add a new `BOOST_MULTIPLIERS["entity-match"] = 1.30` entry. Add a new production to `cognitive_castle/rules/castle-boost.soar` that fires when `^entity-match true` and adds `^boost-tag entity-match`.

4. **Surface `entity_match` in the final hit dict.** One-line addition to the hit-construction comprehension at `searcher.py:509-525`. Consumers (CLI, MCP, audit-trail consumers, future tooling) see whether each hit came via KG-hop. Matches the existing `score_pre_soar` / `soar_tags` audit-trail pattern.

## Non-goals

- **`type-match` rule** — needs drawer-type schema work + query intent classification. Separate spec when wanted.
- **`stale-penalty` rule** — needs a settled definition of "accessed" + persistence layer. Separate spec when wanted.
- **Active learning loop / chunking from disagreement** — research-scale, separate effort. Revisit after entity-match (and any other rules) have shipped and given a sense of whether learning even moves the needle.
- **Tuning `BOOST_MULTIPLIERS["entity-match"]`.** 1.30 is an initial guess (matching the #4a pattern of `recency-boost: 1.25`, `same-project: 1.15` initial values). Tunable in a follow-up after observed retrieval behavior.
- **Backward-compat for `ScoredCandidate` consumers outside fusion.py.** All known callers construct `ScoredCandidate` inside `weighted_rrf`/`apply_recency` (verified). External consumers read `drawer_id`/`timestamp_unix`/`score` and would see an additional field — pure additive, no break.
- **MCP schema for the new `entity_match` final-hit field.** It just appears as a new key in the result dict. Existing MCP clients ignoring unknown fields keep working unchanged.

## Architecture

### Half 1: Provenance tracking in `fusion.py`

#### Add `contributing_signals` field to `ScoredCandidate`

```python
@dataclass(frozen=True)
class ScoredCandidate:
    """A drawer reference with a fused score."""
    drawer_id: str
    timestamp_unix: float
    score: float
    contributing_signals: frozenset[str] = frozenset()
```

The field has a default of empty frozenset, so existing 3-arg call sites (`ScoredCandidate(drawer_id, timestamp_unix, score)`) keep working. Since `frozen=True` requires the default to be immutable, `frozenset()` is correct (regular `set()` would error at class-creation time).

#### Update `weighted_rrf` to accumulate signal names per drawer

The current rank-loop produces `scores` and `timestamps` dicts keyed by `drawer_id`. Add a parallel `contributing_signals_acc: dict[str, set[str]]` accumulator:

```python
scores: dict[str, float] = {}
timestamps: dict[str, float] = {}
contributing_signals_acc: dict[str, set[str]] = {}

for signal_name, candidates in rank_lists.items():
    weight = weights.get(signal_name, 0.0)
    if weight == 0.0 or not candidates:
        # Still capture timestamps for drawers we'd otherwise miss.
        for cand in candidates:
            timestamps.setdefault(cand.drawer_id, cand.timestamp_unix)
        continue
    for rank, cand in enumerate(candidates, start=1):
        contribution = weight / (k_rrf + rank)
        scores[cand.drawer_id] = scores.get(cand.drawer_id, 0.0) + contribution
        timestamps.setdefault(cand.drawer_id, cand.timestamp_unix)
        contributing_signals_acc.setdefault(cand.drawer_id, set()).add(signal_name)
```

On construction, freeze the accumulated set:

```python
return sorted(
    (
        ScoredCandidate(
            drawer_id=did,
            timestamp_unix=timestamps[did],
            score=score,
            contributing_signals=frozenset(contributing_signals_acc.get(did, set())),
        )
        for did, score in scores.items()
    ),
    key=lambda s: (-s.score, s.drawer_id),
)
```

**Correctness note:** signals with `weight == 0.0` continue out of the rank loop BEFORE the accumulator step, so they're correctly NOT counted as contributing. Only signals with non-zero weight AND non-empty rank-list AND the candidate appears in that signal's list count.

#### Update `apply_recency` to PRESERVE `contributing_signals`

`apply_recency` reconstructs `ScoredCandidate` objects with updated scores. Without explicit propagation, `contributing_signals` resets to the default empty frozenset — silently killing the signal before SOAR ever sees it.

```python
def apply_recency(scored, now, tau_days, max_boost):
    ...
    return sorted(
        (
            ScoredCandidate(
                drawer_id=sc.drawer_id,
                timestamp_unix=sc.timestamp_unix,
                score=sc.score * recency_factor,
                contributing_signals=sc.contributing_signals,  # MUST preserve
            )
            for sc in scored
        ),
        ...
    )
```

This is the most fragile point in the implementation. A test will cover it explicitly (`test_apply_recency_preserves_contributing_signals` — see Testing section).

### Half 2: Thread entity-match flag into row dicts

In `cognitive_castle/searcher.py:_new_pipeline_search`, the relevant section is lines 553-573 (verified):

```python
fused = weighted_rrf(rank_lists, weights, k_rrf=cfg.k_rrf)
fused = apply_recency(fused, ...)

# ── Stage 3: cross-encoder rerank ──────────────────────────────────────
k_cap = cfg.reranker_k_hook if is_hook_call else cfg.reranker_k_interactive
top_k_ids = [s.drawer_id for s in fused[:k_cap]]
if not top_k_ids:
    return []

top_k_rows = col.get_by_ids(top_k_ids)
```

Add the entity-match map derivation right after `top_k_ids` is built, BEFORE `col.get_by_ids`:

```python
top_k_ids = [s.drawer_id for s in fused[:k_cap]]
if not top_k_ids:
    return []

# Derive entity-match flag from fusion provenance for the top-K candidates.
entity_match_by_id = {
    sc.drawer_id: "kg" in sc.contributing_signals
    for sc in fused[:k_cap]
}

top_k_rows = col.get_by_ids(top_k_ids)
if not top_k_rows:
    return []

# Attach entity-match flag to each row so SOAR can read it.
for row in top_k_rows:
    if isinstance(row, dict):
        row["entity_match"] = entity_match_by_id.get(row.get("id"), False)
```

Reasoning for placement: the flag lives on the LanceDB row dict because that's what `_push_working_memory` reads from. The row dicts flow through cross-encoder rerank (which only touches the score, not the row payload) and then into Stage 4/Stage 5 helpers. SOAR's `_push_working_memory` is the consumer.

### Half 3: SOAR rule + multiplier

#### Add to `cognitive_castle/soar_bridge.py:BOOST_MULTIPLIERS`

```python
BOOST_MULTIPLIERS: dict[str, float] = {
    "recency-boost": 1.25,
    "same-project": 1.15,
    "entity-match": 1.30,   # entity overlap with the query — strong relevance signal
}
```

**Multiplier value rationale:** 1.30 is an initial guess. Entity overlap is a stronger relevance signal than mere project-match (an entity match means the query explicitly named someone/something that's in the drawer; a project match just means same wing). Placed between `same-project` (1.15) and the spec's upper bound. **Tunable** in a follow-up after observed retrieval behavior — same disclaimer as #4a's `recency-boost: 1.25` and `same-project: 1.15` initial values.

#### Update `_push_working_memory` in soar_bridge.py

The existing function pushes `^id`, `^project`, `^score`, `^age-seconds`, `^recently-accessed` per hit. Add `^entity-match`:

```python
mem.CreateStringWME("entity-match", "true" if hit.get("entity_match") else "false")
```

**Why stringy boolean:** the existing `^recently-accessed` uses the same `"true"|"false"` string convention (verified in `soar_bridge.py`). Soar 9.6 SML doesn't have a first-class boolean WME type — strings are the established pattern. Matching it for `^entity-match` keeps the rule syntax uniform.

If `hit.get("entity_match")` returns None (because Half 2's wiring didn't fire for this hit, e.g., the row wasn't a dict), it falls through to `"false"` — safe default, rule just doesn't fire.

#### Add the new production to `cognitive_castle/rules/castle-boost.soar`

```
sp {castle*entity-match
    "Boost hits whose drawer shares an entity with the query (came via KG-hop)."
    (state <s> ^io.input-link.memory <m>)
    (<m> ^entity-match true)
-->
    (<m> ^boost-tag entity-match)
}
```

Production structure mirrors the existing `castle*recency-boost` and `castle*same-project` rules in the same file. The Python bridge maps the `entity-match` tag → `BOOST_MULTIPLIERS["entity-match"] = 1.30` → multiplicative score adjustment.

### Half 4: Surface `entity_match` in the final hit dict

`_new_pipeline_search` constructs the final hits at lines 509-525 (verified — though after Task 7 of PR #4b, the exact line numbers may have shifted slightly; locate via the `return [...]` block in the function). The current dict comprehension:

```python
return [
    {
        "id": _extract_id(r),
        "text": _extract_text(r),
        "document": _extract_text(r),
        "score": float(s),
        "wing": r.get("wing", "") if isinstance(r, dict) else "",
        "room": r.get("room", "") if isinstance(r, dict) else "",
        "source_file": (r.get("source_file") or "") if isinstance(r, dict) else "",
        "created_at": _get_filed_at(r),
        "similarity": float(s),
    }
    for s, r in reranked[:n_results]
]
```

Add one line:

```python
        "entity_match": (r.get("entity_match", False) if isinstance(r, dict) else False),
```

Naming `entity_match` (snake_case) matches the existing audit-trail field naming (`score_pre_soar`, `soar_boost`, `soar_tags`).

**Why surface it:** useful for audit (`castle search --json | jq '.[] | {id, entity_match}'` once we add `--json`; or just for plain-text debug output), debugging the rule's coverage on real palaces, and future tooling (e.g., a `--explain` flag showing why each hit ranked where it did). Tiny cost — one line.

## Components (file-level changes)

| File | Change | LOC |
|---|---|---|
| `cognitive_castle/fusion.py` | Add `contributing_signals: frozenset[str] = frozenset()` to `ScoredCandidate`. Update `weighted_rrf` to accumulate per-drawer signal names via dict-of-sets, freeze on construction. Update `apply_recency` to explicitly preserve `contributing_signals` when reconstructing `ScoredCandidate` (most fragile point). | +20, -2 |
| `cognitive_castle/searcher.py` | After `apply_recency`, derive `entity_match_by_id` from `fused[:k_cap]` provenance. After `col.get_by_ids`, attach `row["entity_match"] = bool` to each row dict. In the final-hit comprehension, add `"entity_match": ...` field. | +12, -0 |
| `cognitive_castle/soar_bridge.py` | Add `"entity-match": 1.30` to `BOOST_MULTIPLIERS`. In `_push_working_memory`, push `^entity-match true|false` per hit. | +4, -0 |
| `cognitive_castle/rules/castle-boost.soar` | Add `castle*entity-match` production. | +8, -0 |
| `tests/test_fusion.py` | 2 new tests: `test_weighted_rrf_populates_contributing_signals` (per-signal correctness, edge cases for empty/zero-weight signals) + `test_apply_recency_preserves_contributing_signals` (regression guard for the fragile preservation step). | +60 |
| `tests/test_soar_bridge.py` | 2 new tests: `test_entity_match_boost_applied_when_flag_true` + `test_entity_match_boost_not_applied_when_flag_false`. | +50 |
| `tests/test_pipeline_order.py` (or new `tests/test_entity_match_pipeline.py`) | 1 new test: `test_entity_match_flag_attaches_to_kg_hop_rows` — runs `_new_pipeline_search` with mocked recall paths and verifies `row["entity_match"]` is True for hits in `rank_lists["kg"]` and False for dense/sparse-only hits. | +50 |
| `CLAUDE.md` | Update SOAR rules description (~line 188) to mention 3 productions instead of 2; add `entity-match` to the list. | +1, -1 |
| `README.md` | If the SOAR section enumerates rules, add `entity-match` to the list. Otherwise skip (the README's SOAR subsection is high-level). | +2, -0 or 0 |

**Total: ~210 LOC across 7-9 files** (production code: ~45 LOC; tests: ~160 LOC; docs: ~3 LOC). Single-rule scope holds.

## Data flow

### Default invocation (no flags) — unchanged

```
castle search "foo"
  → _new_pipeline_search(llm_rerank=False, soar_boost=False, soar_first=False)
  → Stage 1 (parallel recall): dense + sparse + KG-hop produce rank_lists
  → Stage 2: weighted_rrf + apply_recency → fused: list[ScoredCandidate]
                                            (each now carries contributing_signals)
  → Stage 3: top_k_ids → col.get_by_ids → top_k_rows (each now has entity_match)
                                            cross-encoder rerank → reranked
  → Stage 4 skipped (llm_rerank=False)
  → Stage 5 skipped (soar_boost=False)
  → final hits (each now exposes entity_match)
```

Byte-equivalent to develop except for the new `entity_match` field on each hit. Consumers that ignore unknown fields see no behavior change.

### With `--soar-boost`

```
castle search "what did Maria say about authentication" --soar-boost
  → ...
  → Stage 5 (_stage_5_soar → _apply_soar_to_reranked → apply_soar_boosts):
       _push_working_memory pushes ^entity-match per hit
       new production castle*entity-match fires for hits with ^entity-match true
       → adds ^boost-tag entity-match
       → Python reads back, applies BOOST_MULTIPLIERS["entity-match"] = 1.30
       → compounds with any other rule firings (e.g., entity-match * same-project = 1.30 * 1.15)
       → final score = score_pre_soar * compound (clamped to [0.1, 10.0])
  → final hits have soar_tags=["entity-match"] for KG-hop hits + entity_match=True
```

A hit that came ONLY via dense vector search (no KG-hop entity match) shows `entity_match=False` and gets no entity-match boost. A hit that came via KG-hop (with or without other signals) shows `entity_match=True` and fires the rule.

### With `--llm-rerank` only (no SOAR)

`entity_match` still attaches to row dicts in Half 2. The judge doesn't read it (judge only sees doc text + query). Final hits still expose `entity_match` for downstream consumers. No SOAR rule fires.

### With both `--llm-rerank` and `--soar-boost`

Default ordering (judge-then-SOAR): judge truncates to top-N, then SOAR fires on those N. Hits with `entity_match=True` get the boost.

`--soar-first`: SOAR fires on the full ~20 candidates first, including the `entity-match` boost. Judge then truncates to top-N from SOAR's preferred order. The boost can pull a KG-hop-found hit INTO the judge's top-N pool when it would otherwise have been truncated.

## Error handling

| Failure | Behavior |
|---|---|
| `contributing_signals` missing on a `ScoredCandidate` (e.g., constructed by external code that doesn't know about the field) | Defaults to `frozenset()`. `"kg" in frozenset()` returns False. `entity_match=False` for that drawer. Rule doesn't fire. Safe degradation. |
| `apply_recency` strips the field (REGRESSION — missed implementation of Half 1's preservation note) | `entity_match=False` for all hits. Rule never fires. Caught by `test_apply_recency_preserves_contributing_signals`. |
| Half 2 wiring missed (row doesn't get `entity_match` key) | `hit.get("entity_match")` returns None. `_push_working_memory` pushes `"false"`. Rule doesn't fire. Safe — same as if the rule didn't exist. |
| Row is NOT a dict (e.g., LanceDB returns a tuple or row-object in some path) | `isinstance(row, dict)` check skips the attach. Rule doesn't fire for that hit. |
| `BOOST_MULTIPLIERS["entity-match"]` typo'd in the production (e.g., rule outputs `entity_match` underscore instead) | Existing `unknown-tag-{tag}` warning fires once; multiplier not applied. Safe — same as #4a's "unknown tag" handling. |
| Soar agent / SML failure during rule firing | Identical to current: graceful pass-through, `soar_boost=1.0`, audit-trail tags empty. No new failure modes introduced. |

No new failure modes. All graceful-fallback paths reuse #4a's existing behavior.

## Testing

### 2 fusion tests in `tests/test_fusion.py`

```python
def test_weighted_rrf_populates_contributing_signals():
    """contributing_signals reflects which signals had non-zero weight + the candidate appeared in their rank list."""
    cand_a = CandidateRef(drawer_id="a", timestamp_unix=0.0)
    cand_b = CandidateRef(drawer_id="b", timestamp_unix=0.0)

    rank_lists = {
        "dense": [cand_a, cand_b],
        "sparse": [cand_a],
        "kg": [cand_b],
    }
    weights = {"dense": 1.0, "sparse": 1.0, "kg": 0.5}

    result = weighted_rrf(rank_lists, weights, k_rrf=60)
    by_id = {sc.drawer_id: sc for sc in result}
    assert by_id["a"].contributing_signals == frozenset({"dense", "sparse"})
    assert by_id["b"].contributing_signals == frozenset({"dense", "kg"})


def test_apply_recency_preserves_contributing_signals():
    """apply_recency reconstructs ScoredCandidates with updated score AND preserves provenance."""
    from datetime import datetime, timezone

    scored = [
        ScoredCandidate(
            drawer_id="a",
            timestamp_unix=datetime.now(timezone.utc).timestamp(),
            score=1.0,
            contributing_signals=frozenset({"kg"}),
        )
    ]
    result = apply_recency(scored, now=datetime.now(timezone.utc), tau_days=90.0, max_boost=1.5)
    assert result[0].contributing_signals == frozenset({"kg"}), (
        "apply_recency must preserve contributing_signals through reconstruction"
    )


def test_weighted_rrf_zero_weight_signal_not_in_contributing():
    """A signal with weight=0 should NOT appear in contributing_signals even if the candidate is in its rank list."""
    cand_a = CandidateRef(drawer_id="a", timestamp_unix=0.0)
    rank_lists = {"dense": [cand_a], "sparse": [cand_a]}
    weights = {"dense": 1.0, "sparse": 0.0}

    result = weighted_rrf(rank_lists, weights, k_rrf=60)
    assert result[0].contributing_signals == frozenset({"dense"})
```

(The third test is an edge-case check — keeps the +60 LOC count.)

### 2 soar_bridge tests in `tests/test_soar_bridge.py`

```python
def test_entity_match_boost_applied_when_flag_true(tmp_path):
    """A hit with entity_match=True fires the entity-match rule when SML is available.

    Uses the same SML-available test pattern as other soar_bridge tests in this file
    (mark with pytest.importorskip or the existing pytest.mark.soar gate).
    """
    from cognitive_castle import soar_bridge

    hits = [
        {
            "id": "a",
            "score": 1.0,
            "wing": "x",
            "room": "r",
            "source_file": "f",
            "entity_match": True,
            "created_at": "2020-01-01T00:00:00Z",  # old, so recency-boost doesn't confuse the test
        }
    ]
    cfg = _mock_cfg(palace_path=str(tmp_path))

    boosted = soar_bridge.apply_soar_boosts(hits, cfg)
    assert "entity-match" in boosted[0]["soar_tags"], "Expected entity-match tag to fire"
    assert boosted[0]["soar_boost"] >= 1.30, f"Expected boost >= 1.30, got {boosted[0]['soar_boost']}"


def test_entity_match_boost_not_applied_when_flag_false(tmp_path):
    """A hit with entity_match=False does NOT fire the entity-match rule."""
    from cognitive_castle import soar_bridge

    hits = [
        {
            "id": "a",
            "score": 1.0,
            "wing": "x",
            "room": "r",
            "source_file": "f",
            "entity_match": False,
            "created_at": "2020-01-01T00:00:00Z",
        }
    ]
    cfg = _mock_cfg(palace_path=str(tmp_path))

    boosted = soar_bridge.apply_soar_boosts(hits, cfg)
    assert "entity-match" not in boosted[0]["soar_tags"], (
        "Rule should not fire when entity_match=False"
    )
```

Tests use the existing `_mock_cfg` helper (look at the test file for the actual signature — may need an `soar_rules_path` arg pointing to `cognitive_castle/rules/castle-boost.soar` so the new production is loaded).

### 1 pipeline test in `tests/test_pipeline_order.py` (or new file)

```python
def test_entity_match_flag_attaches_to_kg_hop_rows(tmp_path, monkeypatch):
    """When a row's drawer_id appears in rank_lists['kg'], the row gets entity_match=True.

    Stubs the recall paths to control which signals fire for which IDs, then verifies
    the row dicts that come out of the col.get_by_ids step have entity_match correctly set.
    """
    # Implementation strategy:
    # - Stub Stage 1c (KG-hop) to return rank_lists["kg"] = [CandidateRef("kg-hit")]
    # - Stub Stage 1a (dense) to return rank_lists["dense"] = [CandidateRef("dense-only")]
    # - Stub col.get_by_ids to return two row dicts with matching ids
    # - Run _new_pipeline_search with mocked Stage 3 cross-encoder (return scores in order)
    # - Assert the returned hit for "kg-hit" has entity_match=True; "dense-only" has False
```

(Implementation pseudocode shown; concrete monkeypatch + assertion code at plan-writing time.)

### Smoke tests (manual, for PR description)

- **Smoke #1:** `castle search "ladislav cognitive castle" --llm-rerank --soar-boost` on the developer's palace. Expected: friendly `EmbedderIdentityMismatchError` (the developer's palace is still 384-dim). After legacy reindex, expected: at least one hit has `soar_tags` including `entity-match` (if any KG-hop hits actually land in top-K).

- **Smoke #2:** unit-test that `castle*entity-match` is in the loaded productions when `castle.yaml` doesn't override `soar_rules_path`. Use the same agent introspection technique #4a's tests use.

## Acceptance criteria

1. All new tests pass (3 fusion + 2 soar_bridge + 1 pipeline = 6 new tests).
2. Existing test suite stays at baseline (no NEW failures vs develop's 18 CI-UNSTABLE).
3. `pytest tests/test_fusion.py -v -k "contributing_signals"` — 3 tests pass.
4. `pytest tests/test_soar_bridge.py -v -k "entity_match"` — 2 tests pass.
5. `pytest tests/test_pipeline_order.py -v -k "entity_match"` — 1 test passes.
6. `ruff check` + `ruff format --check` clean on all touched files.
7. `castle search "foo"` (default invocation, no flags) — same hits in same order as develop, PLUS new `entity_match` field on each hit (`True` for KG-hop hits, `False` otherwise).
8. `castle search "foo" --soar-boost` (with `CASTLE_SOAR_ENABLED=1`) — KG-hop hits get `soar_tags` including `entity-match`.
9. CLAUDE.md mentions 3 SOAR productions (not 2).
10. `cognitive_castle/rules/castle-boost.soar` contains the new `castle*entity-match` production with the docstring shown in Half 3.

## Out of scope (deferred)

- **`type-match` rule** — drawer-type schema work + query intent classification. Separate spec.
- **`stale-penalty` rule** — needs "what counts as access" design + persistence layer. Separate spec.
- **Active learning from judge disagreement** — research-scale, separate effort. Revisit after the rule-unblock work has shipped enough rules to see if learning even moves retrieval quality.
- **Tuning `BOOST_MULTIPLIERS["entity-match"]`** — initial value 1.30; tunable once observed retrieval behavior is in.
- **`--explain` flag for hits** — useful for audit, but tangential to entity-match itself.
- **MCP schema annotation for the new `entity_match` field** — additive, existing clients ignore unknown fields.

## Spec self-review (2026-05-13)

1. **Placeholders:** None. Code snippets shown verbatim. The 1 pipeline test has implementation pseudocode (concrete code at plan-writing time, since it requires specific monkeypatch setup).
2. **Internal consistency:** Architecture, Components, Data Flow, Error Handling, Testing, and Acceptance all reference:
   - `contributing_signals: frozenset[str]` field on `ScoredCandidate`
   - `apply_recency` MUST preserve the field (called out in 3 places: Half 1, Components, Error Handling)
   - Variable name `fused` (not `top_k_scored`) for the post-recency ScoredCandidate list
   - Signal name `"kg"` for KG-hop (verified at `searcher.py:545`)
   - `entity_match` (snake_case) for the row + final-hit field
   - `BOOST_MULTIPLIERS["entity-match"] = 1.30` initial value
   - `^entity-match true|false` stringy boolean in SOAR WM (matches `^recently-accessed` pattern)
3. **Scope:** Single PR. ~210 LOC across 7-9 files. One rule. No scope-bleed into `type-match`, `stale-penalty`, or the learning loop.
4. **Ambiguity:** `apply_recency`-preservation noted in 3 places to keep it from being missed. Default behavior preservation noted in Data Flow + Acceptance. Initial-multiplier-value disclaimer in Goal + Non-goals + Half 3.
5. **Empirical grounding:**
   - `searcher.py` lines 542-573 verified for the attachment point + signal names
   - Existing 2 SOAR productions confirmed in `cognitive_castle/rules/castle-boost.soar`
   - `^recently-accessed true|false` string convention verified in soar_bridge.py
   - `BOOST_MULTIPLIERS` at `soar_bridge.py:39` confirmed (3rd entry adds cleanly)
   - `_push_working_memory` confirmed as the WM-push hook
