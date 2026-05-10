"""Tests for the cross-encoder reranker wrapper."""
from unittest.mock import MagicMock, patch

from cognitive_castle import reranker as rr


def test_resolve_device_auto_falls_back_to_cpu_when_no_cuda():
    with patch("cognitive_castle.reranker._cuda_available", return_value=False):
        assert rr._resolve_device("auto") == "cpu"


def test_resolve_device_auto_picks_cuda_when_available():
    with patch("cognitive_castle.reranker._cuda_available", return_value=True):
        assert rr._resolve_device("auto") == "cuda"


def test_resolve_device_explicit_cpu_passes_through():
    assert rr._resolve_device("cpu") == "cpu"


def test_resolve_device_explicit_cuda_passes_through():
    assert rr._resolve_device("cuda") == "cuda"


def test_pick_model_for_device():
    cfg = MagicMock()
    cfg.reranker_model_cpu = "model-cpu"
    cfg.reranker_model_gpu = "model-gpu"
    assert rr._pick_model_for_device("cpu", cfg) == "model-cpu"
    assert rr._pick_model_for_device("cuda", cfg) == "model-gpu"


def test_rerank_returns_scores_aligned_to_input():
    """Smoke test with a stub CrossEncoder so we don't load 290MB in CI."""
    fake_ce = MagicMock()
    fake_ce.predict.return_value = [0.9, 0.1, 0.5]
    with patch("cognitive_castle.reranker._get_reranker", return_value=fake_ce):
        scores = rr.rerank("query", ["doc_a", "doc_b", "doc_c"], device="cpu")
    assert scores == [0.9, 0.1, 0.5]
    # Confirm we passed (query, doc) pairs in order.
    call_args = fake_ce.predict.call_args
    pairs = call_args[0][0]
    assert pairs == [("query", "doc_a"), ("query", "doc_b"), ("query", "doc_c")]


def test_rerank_empty_candidates_returns_empty():
    scores = rr.rerank("query", [], device="cpu")
    assert scores == []
