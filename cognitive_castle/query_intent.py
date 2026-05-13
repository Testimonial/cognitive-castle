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
            re.compile(r"\b(milestone|shipped|released|launched|deployed)\b", re.IGNORECASE),
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
            re.compile(r"\b(problem|issue|bug|error|broken|failing|crash)\b", re.IGNORECASE),
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
