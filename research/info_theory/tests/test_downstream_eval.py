"""Tests for pipeline.downstream_eval — H3 R@5 with session-level provenance bridge."""

from unittest.mock import patch

import pyarrow as pa
import pytest

from pipeline.downstream_eval import (
    aggregate_to_session_scores,
    apply_drop_filter,
    drop_bottom_sessions_by_info,
    run_h3_experiment,
)


def test_aggregate_to_session_scores_mean():
    """Drawer-level recon_residual → session-level mean."""
    table = pa.table(
        {
            "drawer_id": ["d0", "d1", "d2", "d3"],
            "session_id": ["s_a", "s_a", "s_b", "s_b"],
            "recon_residual": [0.2, 0.4, 0.6, 0.8],
        }
    )
    session_scores = aggregate_to_session_scores(table)
    assert session_scores["s_a"] == pytest.approx(0.3)  # mean of 0.2, 0.4
    assert session_scores["s_b"] == pytest.approx(0.7)  # mean of 0.6, 0.8


def test_aggregate_handles_null_residuals():
    """Drawers with null recon_residual (below K_floor) are excluded
    from the mean. If all of a session's drawers are null, the session
    is excluded entirely (cannot be info-weighted)."""
    table = pa.table(
        {
            "drawer_id": ["d0", "d1", "d2", "d3"],
            "session_id": ["s_a", "s_a", "s_b", "s_b"],
            "recon_residual": [None, 0.5, None, None],
        }
    )
    session_scores = aggregate_to_session_scores(table)
    assert session_scores["s_a"] == 0.5
    assert "s_b" not in session_scores  # all null


def test_drop_bottom_sessions_threshold_25():
    session_scores = {f"s{i}": float(i) for i in range(100)}
    kept = drop_bottom_sessions_by_info(session_scores, threshold_pct=25)
    # Lowest 25 (s0..s24) dropped
    assert "s24" not in kept and "s0" not in kept
    assert "s25" in kept and "s99" in kept
    assert len(kept) == 75


def test_apply_drop_filter_trims_three_arrays_in_lockstep():
    """The actual filter operation that hits the LME entry shape."""
    entry = {
        "question_id": "q1",
        "haystack_sessions": [["turn1"], ["turn2"], ["turn3"]],
        "haystack_session_ids": ["s_a", "s_b", "s_c"],
        "haystack_dates": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "other_field": "preserved",
    }
    out = apply_drop_filter(entry, drop_ids={"s_b"})
    assert out["haystack_session_ids"] == ["s_a", "s_c"]
    assert out["haystack_sessions"] == [["turn1"], ["turn3"]]
    assert out["haystack_dates"] == ["2026-01-01", "2026-01-03"]
    assert out["other_field"] == "preserved"
    assert out["question_id"] == "q1"
    # Original is not mutated
    assert len(entry["haystack_session_ids"]) == 3


def test_run_h3_experiment_calls_harness_per_threshold():
    """Smoke test with mocked harness."""
    drawer_table = pa.table(
        {
            "drawer_id": ["d0", "d1", "d2", "d3"],
            "session_id": ["s_a", "s_a", "s_b", "s_b"],
            "recon_residual": [0.2, 0.4, 0.6, 0.8],
        }
    )
    lme_entries = [
        {
            "question_id": "q1",
            "haystack_sessions": [["x"], ["y"]],
            "haystack_session_ids": ["s_a", "s_b"],
            "haystack_dates": ["d1", "d2"],
            "answer_session_ids": ["s_b"],
        },
    ]
    # Mock the per-entry retrieval call to return a constant R@5
    fake_r_at_5 = {"uniform": 1.0, 10: 1.0, 25: 0.5, 50: 0.0}

    def fake_eval(entries, drop_ids):
        # Determine threshold from drop_ids size relative to total sessions
        if not drop_ids:
            return fake_r_at_5["uniform"]
        # Total = 2 sessions; drop_ids count tells us threshold
        if len(drop_ids) == 0:
            return fake_r_at_5["uniform"]
        if "s_a" in drop_ids and len(drop_ids) == 1:
            return fake_r_at_5[50]
        return fake_r_at_5[10]

    with patch("pipeline.downstream_eval._run_lme_with_filter", side_effect=fake_eval) as m:
        results = run_h3_experiment(drawer_table, lme_entries, thresholds=(10, 25, 50))
    assert "uniform" in results
    assert all(t in results for t in (10, 25, 50))
    assert m.call_count == 4  # uniform + 3 thresholds
