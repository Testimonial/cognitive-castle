# SOAR `type-match` Rule + Query Intent Classifier (PR #4c-type-match) — Design Spec

**Date:** 2026-05-13
**Status:** Approved, ready for implementation plan
**Scope:** Second slice of the SOAR umbrella's #4c work — adds a fourth SOAR production (`castle-boost*type-match`) that boosts hits whose drawer-type (`room` field, when it's one of the 5 memory_types) matches the inferred query intent.

## Background

PR #4a (merged at `653b8208`) shipped 2 SOAR productions; PR #4b (merged at `764db36e`) made SOAR ↔ LLM-judge composable; PR #4c-entity-match (merged at `ba9fb022`) added a third production by threading hit-provenance from `fusion.py`.

Three rules were deferred from #4a:
- ✅ `entity-match` — shipped in PR #32 (`#4c-entity-match`)
- 🎯 `type-match` — **THIS SPEC**
- ⏳ `stale-penalty` — needs "what counts as access" design + persistence layer; own future spec

## Key insight — drawer-type is already in the schema

When `convo_miner` runs in `extract_mode="general"`, each chunk's `memory_type` (one of: decision, preference, milestone, problem, emotional) becomes its **`room`** value (verified at `convo_miner.py:346`). So drawer-type is already exposed as a queryable LanceDB column — no schema change, no reindex, no backfill.

The catch: `room` is overloaded. Non-general-mode mines (project files via `miner.py`) use `room` for topic names like `tests` or `fusion`. The type-match rule fires only when `hit["room"]` happens to be one of the 5 known memory_type strings.

## Umbrella context

| Sub-PR | Scope | Status |
|---|---|---|
| **#4a** | SOAR bridge + 2 initial rules (recency-boost, same-project) | ✅ Merged at `653b8208` |
| **#4b** | SOAR ↔ LLM-judge composable order | ✅ Merged at `764db36e` |
| **#4c-entity-match** | Third rule + fusion provenance | ✅ Merged at `ba9fb022` |
| **#4c-type-match — THIS SPEC** | Fourth rule + query intent classifier | Designing now |
| #4c-stale-penalty | Fifth rule — needs "what counts as access" design + SMem persistence | Deferred to its own spec |
| #4c-learning | Active learning from LLM-judge disagreement | Deferred indefinitely; revisit only if rule-tuning becomes painful |

## Goal

1. **Add a `query_intent.py` module** that classifies search queries into one of the 5 memory_types (decision/preference/milestone/problem/emotional) using verb/keyword pattern matching. Pure function, deterministic, ~50 LOC.

2. **Thread the search query through to SOAR.** Add `query: str = ""` keyword-only param to `_stage_5_soar`, `_apply_soar_to_reranked`, `apply_soar_boosts`, and `_push_working_memory`. `_new_pipeline_search` (which already has `query` as a function arg) passes it explicitly. Default empty string preserves back-compat for any external callers of `apply_soar_boosts`.

3. **Push `^context.query-type` and `^memory.drawer-type` to SOAR's working memory.** `_push_working_memory` classifies the query (if non-empty) and pushes `^query-type` on the context WME when classification succeeds; pushes `^drawer-type` on each memory WME when the drawer's `room` is one of the 5 known memory_types.

4. **Add `castle-boost*type-match` production.** Fires when `^context.query-type` equals `^memory.drawer-type` (same Soar variable `<t>` bound twice), adds `^boost-tag type-match`. Multiplier `BOOST_MULTIPLIERS["type-match"] = 1.25` (initial guess, tunable).

5. **Single source of truth for the 5 memory_types.** Export `MEMORY_TYPES: frozenset[str]` from `query_intent.py`, derived directly from the `_INTENT_PATTERNS` keys. `soar_bridge.py` imports it. No duplicate lists.

## Non-goals

- **Multilingual query classification.** The verb/keyword patterns are English-only. Slovak, Czech, German, etc. queries classify to `None` → type-match rule never fires → safe degradation. Multilingual support would need per-language pattern sets OR an LLM-call fallback; both belong in a future spec.
- **LLM-based classification.** Considered and rejected for the initial implementation. Adds 0.5-2s latency per search; requires `CASTLE_LLM_PROVIDER` set; non-deterministic in tests. The verb-pattern classifier is good enough for the 5 known types where intent is usually signalled by clear verbs/keywords.
- **`stale-penalty` rule.** Separate future spec (needs "what counts as access" design).
- **Learning loop / chunking from disagreement.** Same indefinite deferral as the rest of the umbrella.
- **Drawer-type for non-general-mode mines.** Project-file drawers (mined via `miner.py`, room = topic name) never fire type-match. Acceptable — those drawers don't have a memory-type concept in the first place.
- **Tuning `BOOST_MULTIPLIERS["type-match"]`.** 1.25 is an initial guess (matches recency-boost's value; tunable later).

## Architecture

### Half 1: `query_intent.py` module

New file: `cognitive_castle/query_intent.py`

```python
"""Classify a search query's intent as one of the 5 memory_types.

Used by SOAR's type-match rule to boost hits whose room (drawer type)
matches the inferred query intent. The 5 types come from
general_extractor.py's ALL_MARKERS keys: decision, preference, milestone,
problem, emotional.

Patterns are ENGLISH-ONLY. Non-English queries classify to None — the
type-match rule simply doesn't fire (safe degradation, no false firings).
Multilingual support would need either per-language patterns or an
LLM-call fallback; both are out of scope for this PR.

Patterns are ordered by SPECIFICITY-DECREASING in _INTENT_PATTERNS:
patterns with multi-word verb phrases ("what did we decide") come before
broader single-keyword patterns ("bug", "feel"). This makes overlapping
queries resolve to the most specific intent. Example resolutions:
- "what shipped to fix the bug?" → milestone (specific verb) wins over
  problem (single keyword)
- "what's our decision about the problem?" → decision (specific phrase)
  wins over problem (single keyword)
"""

from __future__ import annotations

import re
from typing import Optional


# Ordered list: (intent_name, [compiled_patterns]). First match wins.
# Pattern order WITHIN a type doesn't matter for correctness; ORDER OF
# TYPES does matter — see module docstring.
_INTENT_PATTERNS: list[tuple[str, list[re.Pattern]]] = [
    (
        "decision",
        [
            re.compile(
                r"\bwhat (did|do|did we|do we) (decide|chose|choose|pick|picked)\b",
                re.IGNORECASE,
            ),
            re.compile(r"\b(decision|decided) (about|on|for)\b", re.IGNORECASE),
            re.compile(r"\bwhat'?s the (decision|choice|pick)\b", re.IGNORECASE),
        ],
    ),
    (
        "milestone",
        [
            re.compile(
                r"\bwhen (did|was|did we) (ship|release|launch|merge|deploy)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(milestone|shipped|released|launched|deployed)\b", re.IGNORECASE
            ),
        ],
    ),
    (
        "preference",
        [
            re.compile(r"\b(prefer|prefers|preferred|preference)\b", re.IGNORECASE),
            re.compile(r"\bmy (preference|style|favorite)\b", re.IGNORECASE),
        ],
    ),
    (
        "problem",
        [
            re.compile(
                r"\b(problem|issue|bug|error|broken|failing|crash)\b", re.IGNORECASE
            ),
            re.compile(r"\bwhat (went wrong|broke)\b", re.IGNORECASE),
        ],
    ),
    (
        "emotional",
        [
            re.compile(r"\b(feel|felt|feeling|emotion|emotional)\b", re.IGNORECASE),
        ],
    ),
]


# Single source of truth for the 5 memory_types, derived from the patterns
# above so the two can't drift out of sync. Imported by soar_bridge.py.
MEMORY_TYPES: frozenset[str] = frozenset(name for name, _ in _INTENT_PATTERNS)


def classify_query(query: str) -> Optional[str]:
    """Classify a query as one of the 5 memory_types or None.

    First-match-wins on overlap (see module docstring for ordering rationale).
    Empty string and queries with no matching pattern return None.
    """
    if not query:
        return None
    for intent, patterns in _INTENT_PATTERNS:
        for p in patterns:
            if p.search(query):
                return intent
    return None
```

### Half 2: Thread `query` through to SOAR

Current SOAR call chain (after PR #4b):

```
_new_pipeline_search(query, ..., soar_boost=True, ...)
  → _stage_5_soar(reranked, cfg)                    ← query NOT passed
    → soar_bridge._apply_soar_to_reranked(reranked, cfg)  ← query NOT passed
      → soar_bridge.apply_soar_boosts(hits, cfg)    ← query NOT passed
        → _push_working_memory(agent, hits)         ← query NOT passed
```

After this PR:

```
_new_pipeline_search(query, ...)
  → _stage_5_soar(reranked, cfg, query=query)       ← thread query
    → soar_bridge._apply_soar_to_reranked(reranked, cfg, query=query)
      → soar_bridge.apply_soar_boosts(hits, cfg, query="")
        → _push_working_memory(agent, hits, query="")
```

The `query: str = ""` keyword-only default preserves back-compat for any external callers of the public `apply_soar_boosts` API. After PR #4b, `apply_soar_boosts` has NO internal call sites — only `_apply_soar_to_reranked` calls it, and that's also internal. External user code that imports and calls `apply_soar_boosts(hits, cfg)` still works; it just won't get type-match benefit until updated to pass `query=...`.

### Half 3: Push `^query-type` + `^drawer-type` to SOAR's working memory

In `cognitive_castle/soar_bridge.py:_push_working_memory(agent, hits, query="")`:

```python
from .query_intent import MEMORY_TYPES, classify_query

# (existing code that pushes ^context.project)

# ── NEW: push ^context.query-type (if classification succeeds) ────────
query_type = classify_query(query) if query else None
if query_type:
    context_wme.CreateStringWME("query-type", query_type)
# If query_type is None, skip the push — rule can't fire without it.

# (existing per-hit loop creating ^memory WMEs)
for hit in hits:
    m = input_link.CreateIdWME("memory")
    # ... existing pushes (id, project, score, age-seconds,
    #     recently-accessed, entity-match) ...

    # ── NEW: push ^memory.drawer-type (if room is a known memory_type) ─
    room = hit.get("room") or ""
    if room in MEMORY_TYPES:
        m.CreateStringWME("drawer-type", room)
    # If room isn't a known type, skip — rule can't fire for this hit.
```

`MEMORY_TYPES` is imported from `query_intent.py` (the single source of truth). If somebody later adds a 6th memory_type to `_INTENT_PATTERNS`, `MEMORY_TYPES` updates automatically and `_push_working_memory` recognizes it without code changes.

### Half 4: SOAR rule + multiplier

Add to `BOOST_MULTIPLIERS` in `cognitive_castle/soar_bridge.py`:

```python
BOOST_MULTIPLIERS: dict[str, float] = {
    "recency-boost": 1.25,  # ^recently-accessed "true" (age < 7d default)
    "same-project": 1.15,   # ^project matches ^io.input-link.context.project
    "entity-match": 1.30,   # ^entity-match "true" (came via KG-hop entity match)
    "type-match": 1.25,     # ^drawer-type matches ^io.input-link.context.query-type
}
```

**Multiplier value rationale:** 1.25 — same as recency-boost. Type-match is a meaningful relevance signal but weaker than entity-match (1.30, which requires a specific named entity in the query). Initial guess; tunable later after observed retrieval behavior. Same disclaimer pattern as the prior 3 rules.

New production in `cognitive_castle/rules/castle-boost.soar`:

```
sp {castle-boost*type-match
    "Boost hits whose drawer-type (room) matches the inferred query intent."
    (state <s> ^io.input-link <il>)
    (<il> ^context.query-type <t>)
    (<il> ^memory <m>)
    (<m> ^drawer-type <t>)
-->
    (<m> ^boost-tag type-match)
}
```

The same variable `<t>` in both `^query-type` and `^drawer-type` enforces equal-value matching (standard Soar pattern-matching semantics). If `^query-type` is absent (because query didn't classify), the first condition fails → rule doesn't fire. If a memory has no `^drawer-type` (because its room isn't a known type), the third condition fails for that memory → rule doesn't fire FOR THAT MEMORY (others still get evaluated).

### Half 5: Update castle-boost.soar header docstring

Append to the schema documentation block (currently around lines 4-13):

```
## Schema (pushed to input-link by soar_bridge.py):
##   state ^io.input-link <il>
##   <il>  ^context <ctx>
##         ^memory  <m>     (one per hit, up to 50)
##   <ctx> ^project       <string>
##         ^query-type    <string>?   (decision|preference|milestone|problem|emotional — optional)
##   <m>   ^id                <string>  (composite: wing/room/source_file)
##         ^project           <string>  (from hit.wing)
##         ^score             <float>   (Stage 3+4 score)
##         ^age-seconds       <int>
##         ^recently-accessed true|false
##         ^entity-match      true|false  (came via KG-hop entity match)
##         ^drawer-type       <string>?   (decision|preference|milestone|problem|emotional — when room is a known memory_type)
```

## Components (file-level changes)

| File | Change | LOC |
|---|---|---|
| `cognitive_castle/query_intent.py` | NEW. `_INTENT_PATTERNS` for 5 memory_types, `MEMORY_TYPES` frozenset derived from keys, `classify_query(query) -> Optional[str]`. Module docstring documents English-only limitation + first-match-wins ordering rationale. | +60 |
| `cognitive_castle/searcher.py` | In `_new_pipeline_search`, change `_stage_5_soar(reranked, cfg)` to `_stage_5_soar(reranked, cfg, query=query)`. Change `_stage_5_soar` signature to accept `query: str = ""` and pass through to `_apply_soar_to_reranked`. | +4 |
| `cognitive_castle/soar_bridge.py` | Add `"type-match": 1.25` to `BOOST_MULTIPLIERS`. Add `query: str = ""` kwarg to `_apply_soar_to_reranked`, `apply_soar_boosts`, `_push_working_memory`; thread through. In `_push_working_memory`, import `MEMORY_TYPES` + `classify_query` from `.query_intent`; push `^context.query-type` (conditional on classification success) and `^memory.drawer-type` (conditional on `room in MEMORY_TYPES`). | +15 |
| `cognitive_castle/rules/castle-boost.soar` | Add `castle-boost*type-match` production. Update header schema docstring to include `^context.query-type` and `^memory.drawer-type`. | +10 / -1 |
| `tests/test_query_intent.py` | NEW. 5 tests asserting each example query classifies to the expected type. 1 test for None (empty + non-matching). 1 test for overlap ordering (the milestone-wins-over-problem case). 1 test asserting `MEMORY_TYPES` equals `{"decision", "preference", "milestone", "problem", "emotional"}`. | +80 |
| `tests/test_soar_bridge.py` | 2 new tests: `test_type_match_boost_applied_when_types_match` (query classifies to "decision", drawer room="decision", rule fires on SML-available env) + `test_type_match_boost_not_applied_when_types_differ` (query "decision", drawer room="preference", rule doesn't fire). | +70 |
| `tests/test_pipeline_order.py` | 1 new test: `test_type_match_flag_attaches_to_memory_type_rooms` — runs `_new_pipeline_search` with a query that classifies to "decision" and a stubbed col returning a row with room="decision"; asserts the row gets pushed with `drawer-type=decision` (via inspecting the agent state, or — simpler — asserting the final score has the multiplier applied). | +60 |
| `CLAUDE.md` | Update retrieval pipeline description (line ~188) to enumerate 4 SOAR productions (recency-boost, same-project, entity-match, type-match). | +1 / -1 |

**Total: ~300 LOC across 8 files** (~25 production + ~210 tests + ~65 module + 1 doc). Single-rule scope.

## Data flow

### Default invocation (no flags) — unchanged

```
castle search "what did we decide about authentication"
  → _new_pipeline_search(query=..., soar_boost=False, ...)
  → Stage 5 skipped → final hits unchanged
```

Byte-equivalent to PR #32. The query string is in scope but never reaches SOAR.

### With `--soar-boost`

```
castle search "what did we decide about authentication" --soar-boost
  → _new_pipeline_search(query=..., soar_boost=True, ...)
  → Stage 5: _stage_5_soar(reranked, cfg, query="what did we decide about authentication")
       → _apply_soar_to_reranked(reranked, cfg, query=...)
         → apply_soar_boosts(hits, cfg, query=...)
           → _push_working_memory(agent, hits, query=...)
                ↳ classify_query("what did we decide about authentication") → "decision"
                ↳ push ^context.query-type "decision"
                ↳ for each hit: if hit.room == "decision" (or other MEMORY_TYPES),
                                push ^memory.drawer-type=<room>
           → agent.RunSelf — castle-boost*type-match fires for hits where
             ^drawer-type == "decision"
           → those hits get ^boost-tag type-match
           → BOOST_MULTIPLIERS["type-match"] = 1.25 compounds with any other firings
  → final hits: drawer-type=="decision" hits boosted 1.25x (plus compounding)
```

### Query doesn't classify (e.g., Slovak, or "ramble about things")

```
castle search "ahoj svet" --soar-boost
  → classify_query("ahoj svet") → None  (no English pattern matches)
  → ^context.query-type NOT pushed
  → castle-boost*type-match never fires
  → no boost applied
  → safe degradation, no false firings
```

### Drawer's room isn't a memory_type (e.g., project-file mine)

```
castle search "what did we decide about caching"  --soar-boost
  → classify_query(...) → "decision"
  → push ^context.query-type "decision"
  → hits include one with room="cache.py" (project-file mine, not general-mode)
       ↳ "cache.py" NOT in MEMORY_TYPES
       ↳ ^memory.drawer-type NOT pushed for that hit
  → castle-boost*type-match doesn't fire for that hit
  → conversation-mode drawers with room="decision" still fire as normal
```

## Error handling

| Failure | Behavior |
|---|---|
| Query is empty string | `classify_query("")` returns None. `^query-type` not pushed. Rule can't fire. Default-no-flags invocations effectively skip this whole code path because soar_boost is False. |
| Query is non-empty but no pattern matches (non-English, or just an unmatched phrase) | `classify_query(...)` returns None. Same as above — no push, no fire. |
| Drawer has empty/missing `room` field | `hit.get("room") or ""` produces `""`. `"" in MEMORY_TYPES` is False. `^drawer-type` not pushed. Rule doesn't fire for that hit. |
| Drawer's `room` is one of the 5 types but the query classifies to a DIFFERENT type | `^drawer-type X` pushed, `^query-type Y` pushed, `X != Y`. Soar pattern `<t>` can't bind to both — rule doesn't fire. Correct. |
| Drawer's `room` is one of the 5 types AND query classifies to the SAME type | Both WMEs pushed with same value. Soar binds `<t>` to that value. Rule fires. Boost applied. |
| External caller of `apply_soar_boosts(hits, cfg)` (no `query` kwarg) | Uses default `query=""`. `classify_query("")` returns None. No type-match firings. Other rules (recency, same-project, entity-match) work as before. Pure back-compat — external user must update to pass `query=...` to get type-match benefit. |
| `general_extractor.py` adds a 6th memory_type in the future | `_INTENT_PATTERNS` gets a new entry → `MEMORY_TYPES` automatically grows → `_push_working_memory` recognizes the new type. New SOAR rule would still need to be added separately, but the WM push side is forward-compatible. |
| Soar agent / SML failure during rule firing | Identical to current: graceful pass-through, `soar_boost=1.0` on affected hits, audit-trail tags empty. No new failure modes. |

## Testing

### `tests/test_query_intent.py` — 8 tests for the classifier

```python
"""Tests for query_intent.classify_query."""

from __future__ import annotations

import pytest

from cognitive_castle.query_intent import MEMORY_TYPES, classify_query


def test_classify_decision_query():
    assert classify_query("what did we decide about the embedder swap") == "decision"


def test_classify_milestone_query():
    assert classify_query("when did we ship the bge-m3 cutover") == "milestone"


def test_classify_preference_query():
    assert classify_query("my preference for terse commits") == "preference"


def test_classify_problem_query():
    assert classify_query("what's the bug in the search pipeline") == "problem"


def test_classify_emotional_query():
    assert classify_query("how do I feel about this PR") == "emotional"


def test_empty_query_returns_none():
    assert classify_query("") is None
    assert classify_query("   ") is None  # whitespace-only


def test_non_english_query_returns_none():
    """English-only patterns means Slovak/Czech/etc. queries don't classify."""
    assert classify_query("čo sme rozhodli o autentifikácii") is None


def test_overlap_resolves_to_most_specific():
    """When multiple patterns match, first-in-list wins (specificity-decreasing).

    'what shipped to fix the bug' matches BOTH milestone (shipped) AND problem (bug);
    milestone wins because it's earlier in _INTENT_PATTERNS.
    """
    assert classify_query("what shipped to fix the bug") == "milestone"


def test_memory_types_constant_matches_known_set():
    """Single-source-of-truth check: MEMORY_TYPES is derived from _INTENT_PATTERNS keys."""
    assert MEMORY_TYPES == frozenset({"decision", "preference", "milestone", "problem", "emotional"})
```

### `tests/test_soar_bridge.py` — 2 tests for the rule

```python
def test_type_match_boost_applied_when_types_match(tmp_path):
    """Query classifies to 'decision', drawer room='decision' → rule fires.

    Requires SML-available env to exercise the rule; assertion is skipped
    on environments without SML (same pattern as other soar_bridge tests).
    """
    from cognitive_castle import soar_bridge

    hits = [
        {
            "id": "a",
            "score": 1.0,
            "wing": "x",
            "room": "decision",        # ← matches the query intent
            "source_file": "f",
            "entity_match": False,
            "created_at": "2020-01-01T00:00:00Z",
        }
    ]
    cfg = _mock_cfg(rules_path=_RULES)

    boosted = soar_bridge.apply_soar_boosts(hits, cfg, query="what did we decide about X")

    if soar_bridge._load_sml() is not None:
        assert "type-match" in boosted[0]["soar_tags"], (
            f"Expected type-match tag to fire; got soar_tags={boosted[0]['soar_tags']}"
        )
        assert boosted[0]["soar_boost"] >= 1.25, (
            f"Expected boost >= 1.25, got {boosted[0]['soar_boost']}"
        )


def test_type_match_boost_not_applied_when_types_differ(tmp_path):
    """Query classifies to 'decision', drawer room='preference' → rule does not fire."""
    from cognitive_castle import soar_bridge

    hits = [
        {
            "id": "a",
            "score": 1.0,
            "wing": "x",
            "room": "preference",       # ← different memory_type
            "source_file": "f",
            "entity_match": False,
            "created_at": "2020-01-01T00:00:00Z",
        }
    ]
    cfg = _mock_cfg(rules_path=_RULES)

    boosted = soar_bridge.apply_soar_boosts(hits, cfg, query="what did we decide about X")

    if soar_bridge._load_sml() is not None:
        assert "type-match" not in boosted[0]["soar_tags"], (
            "Rule should not fire when query-type != drawer-type"
        )
```

### `tests/test_pipeline_order.py` — 1 end-to-end test

```python
def test_type_match_flag_attaches_to_memory_type_rooms(monkeypatch, tmp_path):
    """End-to-end: query 'what did we decide' + drawer room='decision' → type-match boost.

    Stubs the recall paths to return a row with room='decision', stubs SOAR via
    monkeypatch to capture the query passed to apply_soar_boosts, asserts the
    flag was threaded correctly.

    Implementation strategy: similar to test_entity_match_flag_attaches_to_kg_hop_rows
    from PR #4c-entity-match. Stub _stage_5_soar to capture its arguments; assert
    the query string was forwarded.
    """
    import cognitive_castle.searcher as searcher_mod

    captured = {}

    def stub_stage_5(reranked, cfg, query=""):
        captured["query"] = query
        captured["reranked"] = reranked
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_5_soar", stub_stage_5)

    # ... rest of pipeline stubs (similar to entity-match test) ...

    # Verify the query was threaded through
    assert captured["query"] == "what did we decide about caching"
```

(Concrete stubs at plan-writing time; this test follows the same pattern as `test_entity_match_flag_attaches_to_kg_hop_rows` from PR #32.)

### Smoke tests (manual, for PR description)

- **Smoke #1:** `castle search "what did we decide about authentication" --soar-boost` on a palace with decision-typed drawers. Expected: at least one hit has `type-match` in soar_tags.
- **Smoke #2:** `castle search "ahoj svet" --soar-boost`. Expected: no `type-match` firings (Slovak query doesn't classify).

## Acceptance criteria

1. All new tests pass: 8 in `test_query_intent.py`, 2 in `test_soar_bridge.py`, 1 in `test_pipeline_order.py` = 11 new tests.
2. Existing test suite stays at baseline (no NEW failures vs. develop's 18 CI-UNSTABLE).
3. `pytest tests/test_query_intent.py -v` — 8 tests pass.
4. `pytest tests/test_soar_bridge.py -v -k "type_match"` — 2 tests pass (on SML-available envs; vacuously pass on others).
5. `pytest tests/test_pipeline_order.py -v -k "type_match"` — 1 test passes.
6. `ruff check` + `ruff format --check` clean on all touched files.
7. `castle search "foo"` (default invocation, no flags) — output identical to develop (query NOT threaded to SOAR when soar_boost=False; no behavior change).
8. `castle search "what did we decide" --soar-boost` (with `CASTLE_SOAR_ENABLED=1`) — decision-typed drawers get `type-match` in soar_tags.
9. `castle search "ahoj svet" --soar-boost` — no type-match firings (non-English query).
10. CLAUDE.md mentions 4 SOAR productions.
11. `cognitive_castle/rules/castle-boost.soar` contains the new `castle-boost*type-match` production with the docstring shown in Half 4, and the header schema doc includes `^context.query-type` and `^memory.drawer-type`.

## Out of scope (deferred)

- **Multilingual query classification** — English-only patterns. Future spec for per-language patterns or LLM-call fallback.
- **`stale-penalty` rule** — needs "what counts as access" design + persistence layer.
- **Active learning from judge disagreement** — research-scale, indefinite deferral.
- **Tuning `BOOST_MULTIPLIERS["type-match"]`** — initial value 1.25; tunable later.
- **`drawer_type` schema field for non-general-mode mines** — project-file drawers don't have memory-type semantics. If we ever want them to, separate spec for the schema migration.
- **Query intent as MCP / CLI output** — i.e., a `--explain-intent` flag. Tangential; useful but separate concern.

## Spec self-review (2026-05-13)

1. **Placeholders:** None. `query_intent.py` shown verbatim. WM push code shown verbatim. SOAR rule shown verbatim. One pipeline test has implementation pseudocode referencing the established `test_entity_match_flag_attaches_to_kg_hop_rows` pattern.
2. **Internal consistency:** Architecture, Components, Data Flow, Error Handling, Testing, and Acceptance all reference:
   - 5 memory_types (decision, preference, milestone, problem, emotional)
   - `room` field as drawer-type source (no schema change)
   - `_INTENT_PATTERNS` ordered by specificity-decreasing (decision → milestone → preference → problem → emotional)
   - `MEMORY_TYPES: frozenset[str]` as single source of truth, derived from pattern keys
   - `query: str = ""` keyword default threaded through the SOAR chain
   - `BOOST_MULTIPLIERS["type-match"] = 1.25` initial value
   - English-only limitation called out in 4 places (Goal, Non-goals, Architecture docstring, Error Handling)
3. **Scope:** Single PR. ~300 LOC across 8 files. One rule. No bleed into stale-penalty or learning loop.
4. **Ambiguity:** First-match-wins ordering documented in Half 1 module docstring + spec body. Back-compat note for `apply_soar_boosts` signature change in Goals + Error Handling. English-only limitation in 4 places.
5. **Empirical grounding:**
   - `convo_miner.py:346` confirmed: `chunk_room = chunk.get("memory_type", room) if extract_mode == "general" else room` — drawer-type lives in `room`
   - `general_extractor.py:163-169` confirmed 5 memory_types: decision, preference, milestone, problem, emotional
   - PR #4c-entity-match (commit `ba9fb022`) established the rule-extensibility pattern this follows
   - `_push_working_memory` is the WM-push hook used by all 3 existing SOAR rules
