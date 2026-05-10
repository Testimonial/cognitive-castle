"""Unit tests for fusion: weighted RRF + recency."""
from cognitive_castle.fusion import (
    CandidateRef,
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
            "sparse": [_ref("a")],   # b is missing from sparse
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
