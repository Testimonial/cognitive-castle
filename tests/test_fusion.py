"""Unit tests for fusion: weighted RRF + recency."""

from datetime import datetime, timedelta, timezone

import pytest

from cognitive_castle.fusion import (
    CandidateRef,
    ScoredCandidate,
    apply_info_weight,
    apply_recency,
    info_weight_factor,
    weighted_rrf,
)


def _ref(drawer_id: str, ts_unix: float = 0.0) -> CandidateRef:
    return CandidateRef(drawer_id=drawer_id, timestamp_unix=ts_unix)


class TestWeightedRRF:
    def test_single_signal_preserves_order(self):
        rank_lists = {"dense": [_ref("a"), _ref("b"), _ref("c")]}
        weights = {"dense": 1.0}
        out = weighted_rrf(rank_lists, weights, k_rrf=60)
        assert [s.drawer_id for s in out] == ["a", "b", "c"]
        # Score should decrease.
        assert out[0].score > out[1].score > out[2].score

    def test_two_signals_agree(self):
        rank_lists = {
            "dense": [_ref("a"), _ref("b"), _ref("c")],
            "sparse": [_ref("a"), _ref("b"), _ref("c")],
        }
        weights = {"dense": 1.0, "sparse": 1.0}
        out = weighted_rrf(rank_lists, weights, k_rrf=60)
        assert [s.drawer_id for s in out] == ["a", "b", "c"]

    def test_two_signals_disagree(self):
        # Drawer "x" is top in dense but bottom in sparse.
        # Drawer "y" is bottom in dense but top in sparse.
        # With equal weights, they should tie or be close; pick by drawer_id sort for determinism.
        rank_lists = {
            "dense": [_ref("x"), _ref("y")],
            "sparse": [_ref("y"), _ref("x")],
        }
        weights = {"dense": 1.0, "sparse": 1.0}
        out = weighted_rrf(rank_lists, weights, k_rrf=60)
        assert {s.drawer_id for s in out} == {"x", "y"}
        # Both candidates appear.
        assert len(out) == 2

    def test_missing_signal_treated_as_unranked(self):
        rank_lists = {
            "dense": [_ref("a"), _ref("b")],
            "sparse": [_ref("a")],  # b is missing from sparse
        }
        weights = {"dense": 1.0, "sparse": 1.0}
        out = weighted_rrf(rank_lists, weights, k_rrf=60)
        # 'a' appears in both, 'b' only in dense -> 'a' wins.
        assert out[0].drawer_id == "a"
        assert out[1].drawer_id == "b"

    def test_weight_changes_outcome(self):
        # 'x' wins on dense, 'y' on sparse. Heavily weight sparse -> 'y' should win.
        rank_lists = {
            "dense": [_ref("x"), _ref("y")],
            "sparse": [_ref("y"), _ref("x")],
        }
        weights = {"dense": 0.1, "sparse": 1.0}
        out = weighted_rrf(rank_lists, weights, k_rrf=60)
        assert out[0].drawer_id == "y"

    def test_empty_rank_lists_returns_empty(self):
        assert weighted_rrf({}, {}, k_rrf=60) == []

    def test_k_rrf_smoothing(self):
        # Larger k_rrf should compress score differences (smoother).
        rank_lists = {"dense": [_ref("a"), _ref("b"), _ref("c")]}
        weights = {"dense": 1.0}
        small_k = weighted_rrf(rank_lists, weights, k_rrf=1)
        large_k = weighted_rrf(rank_lists, weights, k_rrf=1000)
        # Score gap a→b shrinks as k_rrf grows.
        gap_small = small_k[0].score - small_k[1].score
        gap_large = large_k[0].score - large_k[1].score
        assert gap_large < gap_small


class TestApplyRecency:
    def _scored(self, did: str, age_days: float, base_score: float = 1.0) -> ScoredCandidate:
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        ts = (now - timedelta(days=age_days)).timestamp()
        return ScoredCandidate(drawer_id=did, timestamp_unix=ts, score=base_score)

    def test_zero_age_gets_max_boost(self):
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        scored = [self._scored("fresh", age_days=0.0, base_score=1.0)]
        out = apply_recency(scored, now=now, tau_days=90.0, max_boost=1.5)
        # factor = 1 + (1.5 - 1) * exp(-0/90) = 1 + 0.5 * 1.0 = 1.5
        assert out[0].score == pytest.approx(1.5, rel=1e-6)

    def test_old_age_approaches_unboosted(self):
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        scored = [self._scored("ancient", age_days=10000.0, base_score=1.0)]
        out = apply_recency(scored, now=now, tau_days=90.0, max_boost=1.5)
        # factor = 1 + 0.5 * exp(-10000/90) ≈ 1.0
        assert out[0].score == pytest.approx(1.0, rel=1e-3)

    def test_reorders_when_recency_dominates(self):
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        # 'old' has higher base score but is ancient.
        # 'fresh' has lower base score but is brand new.
        # With max_boost large, 'fresh' should win.
        scored = [
            self._scored("old", age_days=10000.0, base_score=1.0),
            self._scored("fresh", age_days=0.0, base_score=0.8),
        ]
        out = apply_recency(scored, now=now, tau_days=90.0, max_boost=2.0)
        # old: 1.0 * (1 + 1.0 * exp(-10000/90)) ≈ 1.0
        # fresh: 0.8 * (1 + 1.0 * exp(0)) = 0.8 * 2.0 = 1.6
        assert out[0].drawer_id == "fresh"

    def test_max_boost_one_is_no_op(self):
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        scored = [self._scored("a", age_days=0.0, base_score=1.0)]
        out = apply_recency(scored, now=now, tau_days=90.0, max_boost=1.0)
        # factor = 1 + 0 * exp(0) = 1.0
        assert out[0].score == pytest.approx(1.0)

    def test_empty_input_returns_empty(self):
        now = datetime(2026, 5, 10, tzinfo=timezone.utc)
        assert apply_recency([], now=now, tau_days=90.0, max_boost=1.5) == []


def test_weighted_rrf_populates_contributing_signals():
    """contributing_signals reflects which signals had non-zero weight + the candidate appeared in their rank list."""
    rank_lists = {
        "dense": [_ref("a"), _ref("b")],
        "sparse": [_ref("a")],
        "kg": [_ref("b")],
    }
    weights = {"dense": 1.0, "sparse": 1.0, "kg": 0.5}

    result = weighted_rrf(rank_lists, weights, k_rrf=60)
    by_id = {sc.drawer_id: sc for sc in result}
    assert by_id["a"].contributing_signals == frozenset({"dense", "sparse"})
    assert by_id["b"].contributing_signals == frozenset({"dense", "kg"})


def test_apply_recency_preserves_contributing_signals():
    """apply_recency reconstructs ScoredCandidates with updated score AND preserves provenance.

    This is a regression guard — if apply_recency drops the contributing_signals
    field, SOAR's entity-match rule never fires.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    scored = [
        ScoredCandidate(
            drawer_id="a",
            timestamp_unix=now.timestamp(),
            score=1.0,
            contributing_signals=frozenset({"kg"}),
        )
    ]
    result = apply_recency(scored, now=now, tau_days=90.0, max_boost=1.5)
    assert result[0].contributing_signals == frozenset({"kg"}), (
        "apply_recency must preserve contributing_signals through reconstruction"
    )


def test_weighted_rrf_zero_weight_signal_not_in_contributing():
    """A signal with weight=0 must NOT appear in contributing_signals.

    Regression guard: if someone refactors the early-continue in
    weighted_rrf and accidentally accumulates signal names for
    zero-weight signals, this test catches it.
    """
    rank_lists = {"dense": [_ref("a")], "sparse": [_ref("a")]}
    weights = {"dense": 1.0, "sparse": 0.0}

    result = weighted_rrf(rank_lists, weights, k_rrf=60)
    assert result[0].contributing_signals == frozenset({"dense"})


def _sc(did, score, novelty=None):
    return ScoredCandidate(drawer_id=did, timestamp_unix=0.0, score=score, novelty=novelty)


class TestInfoWeightFactor:
    def test_none_passthrough(self):
        assert info_weight_factor(None, 0.10, 0.5) == 1.0

    def test_at_or_above_threshold_passthrough(self):
        assert info_weight_factor(0.10, 0.10, 0.5) == 1.0
        assert info_weight_factor(0.9, 0.10, 0.5) == 1.0

    def test_floor_at_zero_novelty(self):
        assert info_weight_factor(0.0, 0.10, 0.5) == 0.5

    def test_linear_ramp_midpoint(self):
        # novelty = threshold/2 → factor = (1 + min_factor)/2
        assert abs(info_weight_factor(0.05, 0.10, 0.5) - 0.75) < 1e-9

    def test_threshold_zero_is_inert(self):
        assert info_weight_factor(0.0, 0.0, 0.5) == 1.0  # no div-by-zero
        assert info_weight_factor(0.05, -1.0, 0.5) == 1.0


class TestApplyInfoWeight:
    def test_demotes_below_threshold_and_resorts(self):
        scored = [_sc("dup", 1.0, novelty=0.0), _sc("fresh", 0.9, novelty=0.8)]
        out = apply_info_weight(scored, threshold=0.10, min_factor=0.5)
        # dup: 1.0 * 0.5 = 0.5; fresh: 0.9 * 1.0 = 0.9 → fresh first
        assert [c.drawer_id for c in out] == ["fresh", "dup"]
        assert abs(out[1].score - 0.5) < 1e-9

    def test_none_novelty_never_punished(self):
        scored = [_sc("untagged", 1.0, novelty=None)]
        out = apply_info_weight(scored, threshold=0.10, min_factor=0.5)
        assert out[0].score == 1.0

    def test_tie_broken_by_drawer_id(self):
        scored = [_sc("b", 0.5, novelty=0.9), _sc("a", 0.5, novelty=0.9)]
        out = apply_info_weight(scored, threshold=0.10, min_factor=0.5)
        assert [c.drawer_id for c in out] == ["a", "b"]

    def test_novelty_field_survives(self):
        out = apply_info_weight([_sc("x", 1.0, novelty=0.05)], 0.10, 0.5)
        assert out[0].novelty == 0.05


class TestNoveltyThreading:
    def test_weighted_rrf_carries_novelty(self):
        refs = [CandidateRef(drawer_id="d", timestamp_unix=1.0, novelty=0.3)]
        out = weighted_rrf({"dense": refs}, {"dense": 1.0})
        assert out[0].novelty == 0.3

    def test_weighted_rrf_first_non_none_wins(self):
        dense = [CandidateRef(drawer_id="d", timestamp_unix=1.0, novelty=None)]
        sparse = [CandidateRef(drawer_id="d", timestamp_unix=1.0, novelty=0.3)]
        out = weighted_rrf({"dense": dense, "sparse": sparse}, {"dense": 1.0, "sparse": 1.0})
        assert out[0].novelty == 0.3

    def test_apply_recency_preserves_novelty(self):
        from datetime import datetime, timezone

        sc = ScoredCandidate(drawer_id="d", timestamp_unix=0.0, score=1.0, novelty=0.2)
        out = apply_recency([sc], now=datetime.now(timezone.utc), tau_days=90.0, max_boost=1.5)
        assert out[0].novelty == 0.2
