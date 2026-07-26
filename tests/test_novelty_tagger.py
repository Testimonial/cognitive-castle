"""Unit tests for cognitive_castle.novelty_tagger (2026-07-26 spec)."""

import json
from unittest.mock import MagicMock

from cognitive_castle.novelty_tagger import compute_novelty


def _row(id_, distance, filed_at, source_file="f.md"):
    return {
        "id": id_,
        "_distance": distance,
        "metadata_json": json.dumps({"filed_at": filed_at, "source_file": source_file}),
    }


def _col_with(rows):
    col = MagicMock()
    col.vector_search.return_value = rows
    return col


def test_prior_only_twin_pair_asymmetry():
    """Critical invariant: only earlier-filed neighbours count.

    Later twin B (filed_at 2026-02) must NOT lower earlier drawer A's
    novelty — otherwise both twins get demoted and content is buried.
    """
    col = _col_with([_row("b", 0.02, "2026-02-01T00:00:00")])
    novelty_a = compute_novelty([0.1] * 8, col, wing="w", filed_at="2026-01-01T00:00:00")
    assert novelty_a == 1.0  # B is later → ignored → no priors → 1.0

    # Conversely, scoring B against prior A gives low novelty.
    col2 = _col_with([_row("a", 0.02, "2026-01-01T00:00:00")])
    novelty_b = compute_novelty([0.1] * 8, col2, wing="w", filed_at="2026-02-01T00:00:00")
    assert abs(novelty_b - 0.02) < 1e-9  # 1 − (1 − 0.02)


def test_self_id_excluded():
    col = _col_with(
        [
            _row("me", 0.0, "2026-01-01T00:00:00"),
            _row("other", 0.3, "2025-12-01T00:00:00"),
        ]
    )
    n = compute_novelty(
        [0.1] * 8,
        col,
        wing="w",
        filed_at="2026-01-02T00:00:00",
        self_id="me",
    )
    assert abs(n - 0.3) < 1e-9  # self dropped; other counts


def test_same_source_file_excluded_when_requested():
    """Mine-time rule: sibling chunks of the file being (re)filed are
    excluded so multi-batch re-mines don't score against themselves."""
    col = _col_with(
        [
            _row("sib", 0.01, "2025-12-01T00:00:00", source_file="same.md"),
            _row("other", 0.4, "2025-12-01T00:00:00", source_file="diff.md"),
        ]
    )
    n = compute_novelty(
        [0.1] * 8,
        col,
        wing="w",
        filed_at="2026-01-01T00:00:00",
        exclude_source_file="same.md",
    )
    assert abs(n - 0.4) < 1e-9

    # Backfill path (no exclusion): sibling counts.
    n2 = compute_novelty(
        [0.1] * 8,
        col,
        wing="w",
        filed_at="2026-01-01T00:00:00",
    )
    assert abs(n2 - 0.01) < 1e-9


def test_first_drawer_convention():
    col = _col_with([])
    assert compute_novelty([0.1] * 8, col, wing="w", filed_at="2026-01-01") == 1.0


def test_malformed_neighbour_metadata_skipped():
    bad = {"id": "x", "_distance": 0.05, "metadata_json": "{not json"}
    good = _row("y", 0.5, "2025-01-01T00:00:00")
    col = _col_with([bad, good])
    n = compute_novelty([0.1] * 8, col, wing="w", filed_at="2026-01-01")
    assert abs(n - 0.5) < 1e-9  # bad row skipped, not fatal


def test_wing_filter_reaches_backend():
    col = _col_with([])
    compute_novelty([0.1] * 8, col, wing="pro'jects", filed_at="2026-01-01")
    _, kwargs = col.vector_search.call_args
    # SQL-escaped single quote
    assert kwargs.get("where") == "wing = 'pro''jects'"
    assert kwargs.get("n_results") == 10
