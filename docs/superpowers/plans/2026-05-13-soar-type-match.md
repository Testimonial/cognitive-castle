# SOAR `type-match` Rule + Query Intent Classifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fourth SOAR production (`castle-boost*type-match`) that boosts hits whose drawer-type (`room` field, when it's one of the 5 known memory_types) matches the inferred query intent. Adds a new `query_intent.py` module for verb-pattern query classification.

**Architecture:** New module `cognitive_castle/query_intent.py` exports `classify_query(query) -> Optional[str]` plus a `MEMORY_TYPES: frozenset[str]` constant derived from `_INTENT_PATTERNS` keys (single source of truth). The query string is threaded through the SOAR call chain (`_stage_5_soar` → `_apply_soar_to_reranked` → `apply_soar_boosts` → `_push_working_memory`) via a new `query: str = ""` kwarg. `_push_working_memory` pushes `^context.query-type` (when classification succeeds) and `^memory.drawer-type` (when `hit["room"]` is in `MEMORY_TYPES`). A new SOAR production fires when both attributes match.

**Tech Stack:** Python 3.10+, pytest, existing Soar 9.6 + SML bindings (no new deps).

---

## Spec reference

`docs/superpowers/specs/2026-05-13-soar-type-match-design.md` (commit `ee7de9a8`).

## File-level map

| File | Role | Net LOC change |
|---|---|---|
| `cognitive_castle/query_intent.py` | NEW. `_INTENT_PATTERNS` for 5 memory_types, `MEMORY_TYPES` frozenset derived from keys, `classify_query(query)` function. English-only verb/keyword patterns; first-match-wins on overlap. | +60 |
| `cognitive_castle/searcher.py` | Add `query: str = ""` kwarg to `_stage_5_soar`. Update the TWO call sites within `_apply_stages_4_and_5` (lines 432 and 438) to pass `query=query`. | +4 |
| `cognitive_castle/soar_bridge.py` | Add `"type-match": 1.25` to `BOOST_MULTIPLIERS`. Add `query: str = ""` kwarg to `_apply_soar_to_reranked`, `apply_soar_boosts`, `_push_working_memory`. In `_push_working_memory`: import `MEMORY_TYPES` + `classify_query` from `.query_intent`; push `^context.query-type` (conditional) and `^memory.drawer-type` per hit (conditional on `room in MEMORY_TYPES`). | +15 |
| `cognitive_castle/rules/castle-boost.soar` | Add `castle-boost*type-match` production. Update header schema docstring to include `^context.query-type` and `^memory.drawer-type`. | +10 / -1 |
| `tests/test_query_intent.py` | NEW. 9 tests: 5 type-classification tests, 1 empty/whitespace, 1 non-English, 1 overlap, 1 MEMORY_TYPES constant check. | +90 |
| `tests/test_soar_bridge.py` | 2 new tests: `test_type_match_boost_applied_when_types_match` + `test_type_match_boost_not_applied_when_types_differ`. | +70 |
| `tests/test_pipeline_order.py` | 1 new test: `test_query_threaded_through_to_stage_5_soar` (verifies the param plumbing). | +50 |
| `CLAUDE.md` | Update SOAR rules description to enumerate 4 productions (recency-boost, same-project, entity-match, type-match). | +1 / -1 |

**Total: ~300 LOC across 8 files** (~25 production + ~210 tests + ~65 module + 1 doc).

---

### Task 1: Branch setup

**Files:** None — repo-level operation

- [ ] **Step 1: Verify clean tree on develop**

Run: `git status && git rev-parse --abbrev-ref HEAD`
Expected: `develop`. Untracked `test_env/` is fine.

- [ ] **Step 2: Create feature branch**

Run: `git switch -c feat/soar-type-match`
Expected: `Switched to a new branch 'feat/soar-type-match'`

- [ ] **Step 3: Verify branch**

Run: `git rev-parse --abbrev-ref HEAD`
Expected: `feat/soar-type-match`

No commit yet.

---

### Task 2: New `query_intent.py` module (TDD)

**Files:**
- Create: `cognitive_castle/query_intent.py`
- Create: `tests/test_query_intent.py`

The module is standalone — no dependencies on SOAR yet. Tested first because it's the foundation everything else builds on.

- [ ] **Step 1: Write the failing test file**

Create `tests/test_query_intent.py`:

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


def test_whitespace_only_query_returns_none():
    assert classify_query("   ") is None
    assert classify_query("\t\n") is None


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

- [ ] **Step 2: Run the tests, verify they fail**

Run: `pytest tests/test_query_intent.py -v`
Expected: 10 FAILED — `ModuleNotFoundError: No module named 'cognitive_castle.query_intent'`

- [ ] **Step 3: Create `cognitive_castle/query_intent.py`**

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
    Empty / whitespace-only / non-matching queries return None.
    """
    if not query or not query.strip():
        return None
    for intent, patterns in _INTENT_PATTERNS:
        for p in patterns:
            if p.search(query):
                return intent
    return None
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `pytest tests/test_query_intent.py -v`
Expected: 10 PASSED

- [ ] **Step 5: Lint the new file**

Run: `ruff check cognitive_castle/query_intent.py && ruff format --check cognitive_castle/query_intent.py`
Expected: Both clean.

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/query_intent.py tests/test_query_intent.py
git commit -m "$(cat <<'EOF'
feat(query-intent): classify queries into one of 5 memory_types

New cognitive_castle/query_intent.py with classify_query(query) verb/
keyword pattern matcher for: decision, preference, milestone, problem,
emotional. Patterns ordered by specificity-decreasing; first-match-wins
on overlap.

English-only — non-English queries return None (safe degradation, no
false firings). Documented limitation; multilingual support deferred.

MEMORY_TYPES: frozenset[str] exported as the single source of truth,
derived from _INTENT_PATTERNS keys so they can't drift apart.

10 tests cover all 5 types, empty/whitespace, non-English, overlap,
and the MEMORY_TYPES constant invariant.

Unblocks SOAR's type-match rule (PR #4c-type-match).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Thread `query` through the SOAR call chain (plumbing, no behavior change)

**Files:**
- Modify: `cognitive_castle/searcher.py` (add kwarg to `_stage_5_soar`, pass through to `_apply_soar_to_reranked`, wire at 2 sites in `_apply_stages_4_and_5`)
- Modify: `cognitive_castle/soar_bridge.py` (add kwarg to `_apply_soar_to_reranked`, `apply_soar_boosts`, `_push_working_memory`; thread through but DON'T consume yet)

This task is pure plumbing. The query reaches `_push_working_memory` but isn't used yet — no WM push, no rule. Task 4 will activate the consumption. Splitting plumbing from activation keeps diffs reviewable.

- [ ] **Step 1: Update `_stage_5_soar` signature in `cognitive_castle/searcher.py`**

Locate `_stage_5_soar` at line 398. Current:

```python
def _stage_5_soar(
    reranked: list[tuple[float, dict]],
    cfg,
) -> list[tuple[float, dict]]:
    """Stage 5: SOAR symbolic boost-tags.

    Delegates to soar_bridge._apply_soar_to_reranked. Lazy-imports
    soar_bridge so the module is only loaded when soar_boost is on
    (preserves the "no SOAR overhead by default" invariant from PR #4a).
    """
    from . import soar_bridge

    return soar_bridge._apply_soar_to_reranked(reranked, cfg)
```

Change to:

```python
def _stage_5_soar(
    reranked: list[tuple[float, dict]],
    cfg,
    query: str = "",
) -> list[tuple[float, dict]]:
    """Stage 5: SOAR symbolic boost-tags.

    Delegates to soar_bridge._apply_soar_to_reranked. Lazy-imports
    soar_bridge so the module is only loaded when soar_boost is on
    (preserves the "no SOAR overhead by default" invariant from PR #4a).

    The query string is threaded through to soar_bridge so the type-match
    rule (PR #4c-type-match) can classify it into a memory_type intent.
    """
    from . import soar_bridge

    return soar_bridge._apply_soar_to_reranked(reranked, cfg, query=query)
```

- [ ] **Step 2: Wire 2 call sites in `_apply_stages_4_and_5`**

Locate `_apply_stages_4_and_5` at line 413. The body has 2 calls to `_stage_5_soar` — at line 432 (`soar_first` branch) and line 438 (default-order branch). Update both:

```python
    if soar_first:
        reranked = _stage_5_soar(reranked, cfg, query=query)   # NEW: pass query
        reranked = _stage_4_judge(query, reranked, cfg)
        return reranked
    if llm_rerank:
        reranked = _stage_4_judge(query, reranked, cfg)
    if soar_boost:
        reranked = _stage_5_soar(reranked, cfg, query=query)   # NEW: pass query
    return reranked
```

`_apply_stages_4_and_5` already accepts `query: str` as a positional arg (added in PR #4b), so `query` is in scope.

- [ ] **Step 3: Update `_apply_soar_to_reranked` signature in `cognitive_castle/soar_bridge.py`**

Locate `_apply_soar_to_reranked` at line 489. Update signature:

```python
def _apply_soar_to_reranked(
    reranked: list[tuple[float, dict]],
    cfg,
    query: str = "",
) -> list[tuple[float, dict]]:
    """Apply SOAR boost-tags to a list of (score, row) tuples.

    Equivalent to apply_soar_boosts() but operates on the tuple shape used
    inside _new_pipeline_search. Returns a NEW list sorted by boosted score
    (descending). Each row dict is mutated in place with audit-trail fields
    (soar_boost, soar_tags, score_pre_soar) so they surface in the final hits.

    The query string is forwarded to apply_soar_boosts so the type-match
    rule (PR #4c-type-match) can use it.

    Never raises. Same graceful-fallback behavior as apply_soar_boosts.
    """
```

In the body, find the call to `apply_soar_boosts` and add `query=query`:

```python
    # Delegate to the existing public API; it mutates hits_view in place
    # (sets soar_boost, soar_tags, score_pre_soar and updates "score").
    boosted = apply_soar_boosts(hits_view, cfg, query=query)
```

- [ ] **Step 4: Update `apply_soar_boosts` signature**

Locate `apply_soar_boosts` at line 355. Add `query: str = ""` kwarg:

```python
def apply_soar_boosts(hits: list[dict], cfg, query: str = "") -> list[dict]:
    """Post-pipeline boost-tag application.

    Args:
        hits: Search hits (typically from search_memories() result["results"]).
            Each hit must have at least: "id", "score", "wing", and optionally
            "created_at" (used to derive recency).
        cfg: Config object exposing .soar_enabled, .soar_rules_path, .palace_path.
        query: The original search query string. Forwarded to
            _push_working_memory so the type-match rule (PR #4c-type-match)
            can classify it into a memory_type intent. Default empty preserves
            back-compat for external callers that don't have the query handy.

    Returns:
        list[dict]: same hits with `score` adjusted by SOAR's compound multiplier
        and 3 new audit-trail fields appended to each hit:
        - soar_boost: float — the compound multiplier applied (1.0 if no tags fired)
        - soar_tags: list[str] — names of boost-tag rules that fired
        - score_pre_soar: float — original score before adjustment

    Never raises. Search continues with degraded behavior on Soar failure.
    On any failure (SML missing, kill switch, kernel/agent/rules error,
    truncation, unknown tag, etc.) prints a one-time-per-process stderr
    warning and returns hits unchanged (or partially boosted).
    """
```

In the body, find the call to `_push_working_memory` and add `query=query`:

```python
    # Push WM
    try:
        memory_wmes, top_level_wmes = _push_working_memory(agent, hits, query=query)
    except Exception as e:
        ...
```

- [ ] **Step 5: Update `_push_working_memory` signature (no behavior change yet)**

Locate `_push_working_memory` at line 206. Add `query: str = ""` kwarg to the signature:

```python
def _push_working_memory(agent, hits: list[dict], query: str = "") -> tuple[dict, list]:
    """Push hits + context to SOAR's working memory.

    Builds ^io.input-link structure:
      ^io.input-link <il>
      <il>           ^context <ctx>
                     ^memory[]  with id, project, score, age-seconds,
                                recently-accessed, entity-match
      ^context <ctx> ^project <string>
                     [^query-type <string>]   ← added in PR #4c-type-match
      ^memory <m>    [^drawer-type <string>]  ← added in PR #4c-type-match

    query is accepted (for the type-match rule wiring in PR #4c-type-match)
    but NOT yet consumed — task 4 of that PR adds the ^query-type and
    ^drawer-type pushes.

    Returns (memory_wmes, top_level_wmes) for later WM cleanup.
    """
```

Don't add any consumption yet. The `query` param is just accepted and ignored. Task 4 will activate it.

- [ ] **Step 6: Run the full test suite to verify no regression**

Run: `pytest tests/test_pipeline_order.py tests/test_soar_bridge.py tests/test_retrieval_pipeline.py 2>&1 | tail -10`
Expected: Same pass/fail counts as develop baseline. The new `query` kwarg is unused — no behavior change.

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/searcher.py cognitive_castle/soar_bridge.py
git commit -m "$(cat <<'EOF'
feat(soar): thread query through SOAR call chain (no consumption yet)

Adds query: str = "" kwarg to _stage_5_soar, _apply_soar_to_reranked,
apply_soar_boosts, and _push_working_memory. Wires the 2 call sites
in _apply_stages_4_and_5 (default-order branch + soar_first branch)
to pass query=query.

Pure plumbing — no behavior change. The query reaches _push_working_memory
but is accepted-and-ignored for now. Task 4 of PR #4c-type-match activates
the consumption (^query-type + ^drawer-type WM pushes + the rule).

External callers of the public apply_soar_boosts(hits, cfg) API continue
to work unchanged (default empty string). To get type-match benefit they
must update to pass query=...

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Activate type-match — WM pushes + rule + multiplier + tests (integration commit)

**Files:**
- Modify: `cognitive_castle/soar_bridge.py` (add `"type-match": 1.25` to `BOOST_MULTIPLIERS`; add `^context.query-type` + `^memory.drawer-type` pushes in `_push_working_memory`)
- Modify: `cognitive_castle/rules/castle-boost.soar` (add production + update header docstring)
- Modify: `tests/test_soar_bridge.py` (add 2 tests)

This is the integration commit — all three pieces (WM push, multiplier, rule) must land together for the rule to fire end-to-end.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_soar_bridge.py`:

```python
def test_type_match_boost_applied_when_types_match(tmp_path):
    """Query classifies to 'decision', drawer room='decision' → rule fires.

    Requires SML-available env to exercise the rule; assertions are skipped
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
            "created_at": "2020-01-01T00:00:00Z",  # old → recency-boost won't fire
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

Note: `_mock_cfg` and `_RULES` are existing test helpers in `tests/test_soar_bridge.py` — `_RULES` points at the live `cognitive_castle/rules/castle-boost.soar` so the new production is loaded.

- [ ] **Step 2: Run the tests, verify behavior**

Run: `pytest tests/test_soar_bridge.py::test_type_match_boost_applied_when_types_match tests/test_soar_bridge.py::test_type_match_boost_not_applied_when_types_differ -v`

Expected on SML-available env:
- `test_type_match_boost_applied_when_types_match`: FAIL — the rule doesn't exist yet AND `^query-type`/`^drawer-type` aren't pushed.
- `test_type_match_boost_not_applied_when_types_differ`: PASS — rule doesn't exist, assertion passes vacuously.

Expected on non-SML env: both pass vacuously (the `if soar_bridge._load_sml() is not None:` skip guards the assertions).

- [ ] **Step 3: Add `"type-match"` to `BOOST_MULTIPLIERS` in `cognitive_castle/soar_bridge.py`**

Locate `BOOST_MULTIPLIERS` (around line 39). Currently has 3 entries (`recency-boost`, `same-project`, `entity-match`). Add a fourth:

```python
BOOST_MULTIPLIERS: dict[str, float] = {
    "recency-boost": 1.25,  # ^recently-accessed "true" (age < 7d default)
    "same-project": 1.15,   # ^project matches ^io.input-link.context.project
    "entity-match": 1.30,   # ^entity-match "true" (came via KG-hop entity match)
    "type-match": 1.25,     # ^drawer-type matches ^io.input-link.context.query-type
}
```

1.25 is an initial guess (same as recency-boost). Tunable later — same disclaimer pattern as the prior 3 rules.

- [ ] **Step 4: Update `_push_working_memory` to push `^context.query-type` and `^memory.drawer-type`**

Locate `_push_working_memory` (around line 206). Add the import at the function top (NOT module-level — keeps query_intent.py only loaded when SOAR fires):

```python
from .query_intent import MEMORY_TYPES, classify_query
```

After the existing `context_wme.CreateStringWME("project", project)` line (which pushes `^context.project`), add:

```python
    # ── NEW: push ^context.query-type when classification succeeds ────────
    # classify_query handles empty/whitespace/non-matching internally — returns None.
    query_type = classify_query(query)
    if query_type:
        context_wme.CreateStringWME("query-type", query_type)
    # If query_type is None, skip the push — rule can't fire without it.
```

Then inside the per-hit loop, after the existing `m.CreateStringWME("entity-match", entity_match)` line (added in PR #4c-entity-match), add:

```python
        # ── NEW: push ^memory.drawer-type when room is a known memory_type ─
        room = hit.get("room") or ""
        if room in MEMORY_TYPES:
            m.CreateStringWME("drawer-type", room)
        # If room isn't a known type, skip — rule can't fire for this hit.
```

Update the function docstring to document the now-active behavior — replace the existing note:

```python
    """Push hits + context to SOAR's working memory.

    Builds ^io.input-link structure:
      ^io.input-link <il>
      <il>           ^context <ctx>
                     ^memory[]  with id, project, score, age-seconds,
                                recently-accessed, entity-match, drawer-type
      ^context <ctx> ^project <string>
                     [^query-type <string>]   ← when classify_query succeeds
      ^memory <m>    [^drawer-type <string>]  ← when hit.room in MEMORY_TYPES

    query is classified via cognitive_castle.query_intent.classify_query;
    if it returns one of the 5 memory_types, ^context.query-type is pushed.
    For each hit, if its room is one of the 5 known memory_types,
    ^memory.drawer-type is pushed. The castle-boost*type-match rule fires
    when both attributes match.

    Returns (memory_wmes, top_level_wmes) for later WM cleanup.
    """
```

- [ ] **Step 5: Add the new production to `cognitive_castle/rules/castle-boost.soar`**

Open `cognitive_castle/rules/castle-boost.soar`. First, update the header docstring schema block (around lines 4-13). The current schema doc after PR #4c-entity-match reads:

```
## Schema (pushed to input-link by soar_bridge.py):
##   state ^io.input-link <il>
##   <il>  ^context <ctx>
##         ^memory  <m>     (one per hit, up to 50)
##   <ctx> ^project       <string>
##   <m>   ^id                <string>  (composite: wing/room/source_file)
##         ^project           <string>  (from hit.wing)
##         ^score             <float>   (Stage 3+4 score)
##         ^age-seconds       <int>
##         ^recently-accessed true|false
##         ^entity-match      true|false  (came via KG-hop entity match)
```

Add lines for `^query-type` and `^drawer-type`:

```
## Schema (pushed to input-link by soar_bridge.py):
##   state ^io.input-link <il>
##   <il>  ^context <ctx>
##         ^memory  <m>     (one per hit, up to 50)
##   <ctx> ^project       <string>
##         ^query-type    <string>?   (decision|preference|milestone|problem|emotional — optional, only present when classify_query succeeds)
##   <m>   ^id                <string>  (composite: wing/room/source_file)
##         ^project           <string>  (from hit.wing)
##         ^score             <float>   (Stage 3+4 score)
##         ^age-seconds       <int>
##         ^recently-accessed true|false
##         ^entity-match      true|false  (came via KG-hop entity match)
##         ^drawer-type       <string>?   (decision|preference|milestone|problem|emotional — only when hit.room is one of these)
```

Then APPEND the new production at the bottom of the file (after the existing 3 productions):

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

The same variable `<t>` in both `^query-type` and `^drawer-type` enforces equal-value matching.

- [ ] **Step 6: Run the tests, verify they pass**

Run: `pytest tests/test_soar_bridge.py::test_type_match_boost_applied_when_types_match tests/test_soar_bridge.py::test_type_match_boost_not_applied_when_types_differ -v`
Expected: PASS (on SML-available envs the rule now fires; on non-SML envs the assertions skip).

- [ ] **Step 7: Run the full soar_bridge test suite**

Run: `pytest tests/test_soar_bridge.py -v 2>&1 | tail -15`
Expected: All prior tests still pass (14 from PR #4a/#4b/#4c-entity-match + 2 new from this PR = 16 tests).

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/soar_bridge.py cognitive_castle/rules/castle-boost.soar tests/test_soar_bridge.py
git commit -m "$(cat <<'EOF'
feat(soar): add type-match production + BOOST_MULTIPLIERS entry

Fourth SOAR boost-tag production: castle-boost*type-match fires when
the query's inferred memory_type (^context.query-type) matches a hit's
drawer-type (^memory.drawer-type, sourced from the room field when it's
one of the 5 known memory_types: decision/preference/milestone/problem/
emotional). The Python bridge maps the tag to BOOST_MULTIPLIERS
["type-match"] = 1.25 (initial guess, tunable).

_push_working_memory now pushes:
- ^context.query-type when classify_query(query) returns one of the 5
  memory_types
- ^memory.drawer-type per hit when hit.room is in MEMORY_TYPES

MEMORY_TYPES is imported from cognitive_castle.query_intent (single
source of truth — derived from _INTENT_PATTERNS keys).

castle-boost.soar header docstring updated to document the new
^context.query-type and ^memory.drawer-type attributes.

Two new tests in test_soar_bridge.py exercise the rule's fire/no-fire
behavior; on environments without SML, rule-fire assertions are
skipped (matching the established test pattern).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: End-to-end pipeline threading test

**Files:**
- Modify: `tests/test_pipeline_order.py` (add 1 test verifying query is threaded through to `_stage_5_soar`)

The integration test from PR #4c-entity-match established the pattern for end-to-end pipeline tests. This task adds the analogous test for query threading.

- [ ] **Step 1: Write the test**

Append to `tests/test_pipeline_order.py`:

```python
def test_query_threaded_through_to_stage_5_soar(monkeypatch, tmp_path):
    """When _new_pipeline_search is called with a query and soar_boost=True,
    _stage_5_soar receives the query via kwarg.

    Verifies the plumbing in _apply_stages_4_and_5 passes query=query to
    both _stage_5_soar call sites (default-order branch + soar_first branch).
    """
    import cognitive_castle.searcher as searcher_mod

    captured: dict = {}

    def stub_stage_5(reranked, cfg, query=""):
        captured["query"] = query
        captured["reranked"] = reranked
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_5_soar", stub_stage_5)

    # Drive _apply_stages_4_and_5 directly with a known query
    cfg_obj = type(
        "C",
        (),
        {"llm_judge_top_n": 5, "soar_enabled": True, "soar_rules_path": None, "palace_path": str(tmp_path)},
    )()

    reranked = [(0.9, {"id": "a", "score": 0.9})]
    searcher_mod._apply_stages_4_and_5(
        query="what did we decide about caching",
        reranked=reranked,
        cfg=cfg_obj,
        llm_rerank=False,
        soar_boost=True,
        soar_first=False,
    )

    assert captured.get("query") == "what did we decide about caching", (
        f"Expected query forwarded to _stage_5_soar; got {captured.get('query')!r}"
    )


def test_query_threaded_through_soar_first_branch(monkeypatch, tmp_path):
    """Same as above but exercises the soar_first=True branch."""
    import cognitive_castle.searcher as searcher_mod

    captured: dict = {}

    def stub_stage_5(reranked, cfg, query=""):
        captured["query"] = query
        return reranked

    def stub_stage_4(query, reranked, cfg):
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_5_soar", stub_stage_5)
    monkeypatch.setattr(searcher_mod, "_stage_4_judge", stub_stage_4)

    cfg_obj = type(
        "C",
        (),
        {"llm_judge_top_n": 5, "soar_enabled": True, "soar_rules_path": None, "palace_path": str(tmp_path)},
    )()

    searcher_mod._apply_stages_4_and_5(
        query="when did we ship the migration",
        reranked=[(0.9, {"id": "a", "score": 0.9})],
        cfg=cfg_obj,
        llm_rerank=True,
        soar_boost=True,
        soar_first=True,
    )

    assert captured.get("query") == "when did we ship the migration", (
        f"Expected query forwarded to _stage_5_soar in soar_first branch; got {captured.get('query')!r}"
    )
```

- [ ] **Step 2: Run the tests, verify they pass**

Run: `pytest tests/test_pipeline_order.py::test_query_threaded_through_to_stage_5_soar tests/test_pipeline_order.py::test_query_threaded_through_soar_first_branch -v`
Expected: 2 PASSED (the plumbing was set up in Task 3).

- [ ] **Step 3: Run wider tests**

Run: `pytest tests/test_pipeline_order.py tests/test_soar_bridge.py tests/test_query_intent.py 2>&1 | tail -10`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_pipeline_order.py
git commit -m "$(cat <<'EOF'
test(pipeline): verify query threaded to both _stage_5_soar call sites

Two integration tests confirm _apply_stages_4_and_5 forwards the query
kwarg to _stage_5_soar in BOTH branches (default-order + soar_first).
Locks in the wiring established in Task 3 of PR #4c-type-match.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md` (mention 4 SOAR productions instead of 3)

- [ ] **Step 1: Find and update the SOAR rules description**

Open `/home/lbihari/cognitive-castle/CLAUDE.md`. Locate the retrieval-pipeline diagram region (around line 188). After PR #4c-entity-match (commit `ba9fb022`), the description should read approximately:

```
    │     ├── Stage 5 (--soar-boost AND CASTLE_SOAR_ENABLED=1): 3 SOAR symbolic
    │     │     productions (recency-boost, same-project, entity-match) add boost-tags
    │     │     → graceful pass-through on any Soar failure
```

Use the Read tool to confirm the exact current text, then replace with:

```
    │     ├── Stage 5 (--soar-boost AND CASTLE_SOAR_ENABLED=1): 4 SOAR symbolic
    │     │     productions (recency-boost, same-project, entity-match, type-match) add boost-tags
    │     │     → graceful pass-through on any Soar failure
```

Just changes `3` to `4` and adds `type-match` to the rule list.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(CLAUDE.md): name type-match as a SOAR production

Updates the retrieval pipeline description to reflect 4 SOAR productions
(recency-boost, same-project, entity-match, type-match). type-match lands
in this PR.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Lint + full test suite

**Files:** None — verification only

- [ ] **Step 1: Run ruff format check on touched files**

Run:
```bash
ruff format --check cognitive_castle/query_intent.py cognitive_castle/searcher.py cognitive_castle/soar_bridge.py tests/test_query_intent.py tests/test_pipeline_order.py tests/test_soar_bridge.py
```

If any "Would reformat:" output, run `ruff format` on those files. Then `git restore` any files that were reformatted by ruff that aren't part of this PR's scope (per the established pattern from prior PRs).

- [ ] **Step 2: Run ruff check**

Run: `ruff check cognitive_castle/query_intent.py cognitive_castle/searcher.py cognitive_castle/soar_bridge.py tests/test_query_intent.py tests/test_pipeline_order.py tests/test_soar_bridge.py`
Expected: All checks pass.

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -5`
Expected: 18 baseline failures preserved, ~1465 passed (was 1452 after PR #32; +13 from this PR's tests: 10 query_intent + 2 soar_bridge + 1 pipeline_order = 13. Actually 2 pipeline tests, so +14 = ~1466).

- [ ] **Step 4: If formatting fixes needed, commit them**

```bash
ruff format cognitive_castle/query_intent.py cognitive_castle/searcher.py cognitive_castle/soar_bridge.py tests/test_query_intent.py tests/test_pipeline_order.py tests/test_soar_bridge.py
# Check what was reformatted; restore anything outside PR scope
git status --short
git restore <any files outside PR scope>
git add cognitive_castle/query_intent.py cognitive_castle/searcher.py cognitive_castle/soar_bridge.py tests/test_query_intent.py tests/test_pipeline_order.py tests/test_soar_bridge.py
git commit -m "$(cat <<'EOF'
style: ruff format on PR-scope files

No semantic changes. ruff check + full test suite stay green.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If no formatting fixes were needed, skip this step.

---

### Task 8: Smoke + push + PR

**Files:** None — verification + git operations

- [ ] **Step 1: Live smoke against developer's palace**

The developer's `~/.castle/palace` is currently a 384-dim legacy MiniLM palace, so `castle search` hits the friendly `EmbedderIdentityMismatchError` first. The smoke verifies the new code doesn't crash on the way in.

Run: `castle --palace ~/.castle/palace search "what did we decide" 2>&1 | head -5`
Expected: Friendly migration prompt. NOT a crash from query_intent or threading code.

If the developer's palace is bge-m3 (post-reindex), try:

Run: `CASTLE_SOAR_ENABLED=1 castle --palace ~/.castle/palace search "what did we decide about embedder" --soar-boost --results 3 2>&1`
Expected: Some hits. If any hits have `room` matching a memory_type (decision/preference/milestone/problem/emotional), they should have `type-match` in their `soar_tags`. Even if no hits match, the code shouldn't crash.

- [ ] **Step 2: Push branch**

Run: `git push -u origin feat/soar-type-match`
Expected: Branch pushed; PR URL printed.

- [ ] **Step 3: Open PR**

```bash
gh pr create --title "feat: SOAR type-match rule + query intent classifier (PR #4c-type-match)" --body "$(cat <<'EOF'
## Summary

Second slice of the SOAR umbrella's #4c work — adds the fourth SOAR production (`castle-boost*type-match`) that boosts hits whose drawer-type matches the inferred query intent. Adds a new `query_intent.py` module for verb-pattern query classification.

- **New `cognitive_castle/query_intent.py` module** — `classify_query(query) -> Optional[str]` maps queries to one of 5 memory_types (decision/preference/milestone/problem/emotional) via verb/keyword pattern matching. First-match-wins on overlap; specificity-decreasing pattern order. Exports `MEMORY_TYPES: frozenset[str]` derived from `_INTENT_PATTERNS` keys (single source of truth).
- **Query threaded through SOAR call chain** — `query: str = ""` kwarg added to `_stage_5_soar`, `_apply_soar_to_reranked`, `apply_soar_boosts`, `_push_working_memory`. `_apply_stages_4_and_5` passes `query=query` at both call sites (default-order branch + soar_first branch).
- **WM pushes** — `_push_working_memory` pushes `^context.query-type` when classification succeeds; `^memory.drawer-type` per hit when `hit["room"]` is in `MEMORY_TYPES`.
- **New `castle-boost*type-match` production** — fires when `^query-type` equals `^drawer-type` (same Soar variable `<t>` bound twice). `BOOST_MULTIPLIERS["type-match"] = 1.25` (initial guess, tunable).
- **Key insight** — drawer-type is ALREADY in the schema. When `convo_miner` runs in `extract_mode="general"`, each chunk's `memory_type` becomes its `room` value (verified at `convo_miner.py:346`). No schema change, no reindex, no backfill. Project-file drawers (room=topic name, not memory_type) safely ignored.

Scope: single rule. `stale-penalty` (needs "what counts as access" design + persistence layer) and active learning from judge disagreement remain deferred to future specs.

## Commits

- `<sha>` feat(query-intent): classify queries into one of 5 memory_types
- `<sha>` feat(soar): thread query through SOAR call chain (no consumption yet)
- `<sha>` feat(soar): add type-match production + BOOST_MULTIPLIERS entry
- `<sha>` test(pipeline): verify query threaded to both _stage_5_soar call sites
- `<sha>` docs(CLAUDE.md): name type-match as a SOAR production
- `<sha>` style: ruff format on PR-scope files (if needed)

## Spec + Plan

- Spec: `docs/superpowers/specs/2026-05-13-soar-type-match-design.md`
- Plan: `docs/superpowers/plans/2026-05-13-soar-type-match.md`

## Known limitation

**English-only query classification.** `_INTENT_PATTERNS` are English regexes. Slovak/Czech/etc. queries return None from `classify_query` → `^query-type` never pushed → `castle-boost*type-match` never fires. Safe degradation (no false firings, just no boost). Multilingual support would need per-language pattern sets or an LLM-call fallback; both deferred to a future spec.

## Test plan

- [x] `tests/test_query_intent.py` (new file): 10 tests — 5 type-classification tests, empty/whitespace, non-English, overlap-resolution, MEMORY_TYPES constant
- [x] `tests/test_soar_bridge.py`: 2 new tests — `test_type_match_boost_applied_when_types_match`, `test_type_match_boost_not_applied_when_types_differ` (rule-fire assertions skip on non-SML envs)
- [x] `tests/test_pipeline_order.py`: 2 new tests — query threaded through to both `_stage_5_soar` call sites (default-order + soar_first branches)
- [x] `pytest tests/ --ignore=tests/benchmarks` — 18 baseline CI-UNSTABLE failures preserved, ~14 new passes
- [x] `ruff check` + `ruff format --check` clean on touched files
- [x] Live smoke against developer's palace: search command doesn't crash; friendly `EmbedderIdentityMismatchError` still fires correctly on the legacy 384-dim palace

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Replace `<sha>` placeholders with actual commit SHAs from `git log --oneline a1ebe000..HEAD` (use the develop ancestor SHA before this PR's branch, which you can find with `git merge-base develop HEAD`).

Expected: PR URL printed. Return it to the user.

---

## Self-Review

### Spec coverage check

| Spec section / requirement | Plan task |
|---|---|
| Half 1: `query_intent.py` module + `classify_query` + `MEMORY_TYPES` constant | Task 2 |
| Half 1: English-only pattern documentation in module docstring | Task 2 (module docstring) |
| Half 1: `classify_query` handles empty/whitespace/non-matching → None | Task 2 + tests |
| Half 1: First-match-wins ordering | Task 2 (overlap test) |
| Half 1: Single source of truth via `MEMORY_TYPES = frozenset(name for name, _ in _INTENT_PATTERNS)` | Task 2 |
| Half 2: `query: str = ""` kwarg threaded through 4 functions | Task 3 |
| Half 2: 2 call sites in `_apply_stages_4_and_5` pass `query=query` | Task 3 (Step 2) |
| Half 2: Back-compat for external `apply_soar_boosts` callers via default `""` | Task 3 (signature) |
| Half 3: `_push_working_memory` pushes `^context.query-type` (conditional on classification) | Task 4 |
| Half 3: `_push_working_memory` pushes `^memory.drawer-type` (conditional on `room in MEMORY_TYPES`) | Task 4 |
| Half 4: `BOOST_MULTIPLIERS["type-match"] = 1.25` | Task 4 |
| Half 4: New `castle-boost*type-match` production | Task 4 |
| Half 5: castle-boost.soar header docstring updated | Task 4 (Step 5) |
| Acceptance #1-5 (all new tests pass + baseline preserved) | Tasks 2, 4, 5 + Task 7 sweep |
| Acceptance #6 (lint clean) | Task 7 |
| Acceptance #7 (default invocation byte-equivalent to develop) | Implicitly verified by Task 3's no-behavior-change wiring |
| Acceptance #8-9 (SML-available smoke tests) | Task 8 |
| Acceptance #10 (CLAUDE.md mentions 4 productions) | Task 6 |
| Acceptance #11 (.soar file contains new production + updated header) | Task 4 (Step 5) |

All spec requirements have a task. No gaps.

### Placeholder scan

No "TBD" / "TODO" / "similar to" / "add appropriate error handling" patterns. Every step has either exact code (with the full intended content) or exact commands. The PR description in Task 8 has `<sha>` placeholders that the executor fills in from `git log` — explicit recipe given. Acceptable.

### Type consistency

- `classify_query(query: str) -> Optional[str]` — defined in Task 2, consumed in Task 4
- `MEMORY_TYPES: frozenset[str]` — defined in Task 2, imported in Task 4
- `query: str = ""` kwarg — added consistently to `_stage_5_soar` (Task 3), `_apply_soar_to_reranked` (Task 3), `apply_soar_boosts` (Task 3), `_push_working_memory` (Task 3), consumed in Task 4
- `BOOST_MULTIPLIERS["type-match"] = 1.25` — defined in Task 4, multiplier mechanism is existing code (no signature changes)
- `^context.query-type` / `^memory.drawer-type` Soar WM attributes — pushed in Task 4 (`_push_working_memory`), matched in Task 4's production
- All names consistent across tasks. No drift.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-13-soar-type-match.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
