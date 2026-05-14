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


def test_is_cuda_oom_detects_oom_by_message():
    """CUDA OOM should be detected via exception message even without torch."""
    assert rr._is_cuda_oom(RuntimeError("CUDA error: out of memory"))
    assert rr._is_cuda_oom(Exception("cudaErrorMemoryAllocation occurred"))


def test_is_cuda_oom_returns_false_for_other_errors():
    """Non-OOM exceptions should not trigger the CPU fallback path."""
    assert not rr._is_cuda_oom(RuntimeError("some other error"))
    assert not rr._is_cuda_oom(ValueError("bad input"))


def test_rerank_falls_back_to_cpu_on_cuda_oom():
    """When the GPU reranker can't load (OOM), gracefully use the CPU reranker."""
    cfg = MagicMock()
    cfg.reranker_model_gpu = "model-gpu"
    cfg.reranker_model_cpu = "model-cpu"

    fake_cpu_ce = MagicMock()
    fake_cpu_ce.predict.return_value = [0.7, 0.3]

    calls = []

    def fake_get_reranker(model_name, device):
        calls.append((model_name, device))
        if device == "cuda":
            raise RuntimeError("CUDA error: out of memory")
        return fake_cpu_ce

    with (
        patch("cognitive_castle.reranker._cuda_available", return_value=True),
        patch("cognitive_castle.reranker._get_reranker", side_effect=fake_get_reranker),
    ):
        scores = rr.rerank("q", ["a", "b"], device="auto", cfg=cfg)

    assert scores == [0.7, 0.3]
    assert calls == [("model-gpu", "cuda"), ("model-cpu", "cpu")]


def test_rerank_does_not_fall_back_on_non_oom_cuda_error():
    """A non-OOM exception on cuda should propagate, not silently switch to cpu."""
    cfg = MagicMock()
    cfg.reranker_model_gpu = "model-gpu"
    cfg.reranker_model_cpu = "model-cpu"

    with (
        patch("cognitive_castle.reranker._cuda_available", return_value=True),
        patch(
            "cognitive_castle.reranker._get_reranker", side_effect=RuntimeError("unrelated error")
        ),
    ):
        try:
            rr.rerank("q", ["a"], device="auto", cfg=cfg)
            raise AssertionError("expected RuntimeError")
        except RuntimeError as e:
            assert "unrelated error" in str(e)
