import pytest

import cognitive_castle.embedding as embedding


@pytest.fixture(autouse=True)
def isolate_embedding_state(monkeypatch):
    if hasattr(embedding, "_EF_CACHE"):
        monkeypatch.setattr(embedding, "_EF_CACHE", {})
    if hasattr(embedding, "_model_cache"):
        monkeypatch.setattr(embedding, "_model_cache", {})
    if hasattr(embedding, "_WARNED"):
        monkeypatch.setattr(embedding, "_WARNED", set())


def test_embedding_uses_config_default_model_when_unspecified():
    """Without overrides, the embedder reads model name from config."""
    from cognitive_castle.embedding import _resolve_model_name

    cfg = _make_default_cfg()
    assert _resolve_model_name(cfg) == cfg.embedder_model
    # Cutover: default is now paraphrase-multilingual-MiniLM-L12-v2.
    assert _resolve_model_name(cfg) == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def test_embedding_respects_config_override():
    from cognitive_castle.embedding import _resolve_model_name
    from unittest.mock import MagicMock

    cfg = MagicMock()
    cfg.embedder_model = "BAAI/bge-m3"
    assert _resolve_model_name(cfg) == "BAAI/bge-m3"


def _make_default_cfg():
    """Return an instance of the project's config class with all defaults."""
    from cognitive_castle.config import CognitiveCastleConfig

    return CognitiveCastleConfig()


def test_is_cuda_oom_detects_oom_by_message():
    """CUDA OOM should be detected via exception message even without torch."""
    from cognitive_castle.embedding import _is_cuda_oom

    assert _is_cuda_oom(RuntimeError("CUDA error: out of memory"))
    assert _is_cuda_oom(Exception("cudaErrorMemoryAllocation occurred"))


def test_is_cuda_oom_returns_false_for_other_errors():
    """Non-OOM exceptions should not trigger the CPU fallback path."""
    from cognitive_castle.embedding import _is_cuda_oom

    assert not _is_cuda_oom(RuntimeError("some other error"))
    assert not _is_cuda_oom(ValueError("bad input"))


def test_get_model_falls_back_to_cpu_on_cuda_oom(monkeypatch):
    """When the GPU embedder can't load (OOM), gracefully use the CPU embedder."""
    from unittest.mock import MagicMock

    fake_cpu_model = MagicMock()
    calls = []

    class FakeST:
        def __new__(cls, name, device):
            calls.append((name, device))
            if device == "cuda":
                raise RuntimeError("CUDA error: out of memory")
            return fake_cpu_model

    monkeypatch.setattr("sentence_transformers.SentenceTransformer", FakeST)
    monkeypatch.setattr(embedding, "_resolve_device", lambda d: "cuda")

    result = embedding._get_model(device="auto", cfg=_make_default_cfg())

    assert result is fake_cpu_model
    assert calls == [
        ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "cuda"),
        ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "cpu"),
    ]


def test_get_model_does_not_fall_back_on_non_oom_cuda_error(monkeypatch):
    """A non-OOM exception on cuda should propagate, not silently switch to cpu."""

    class FakeST:
        def __new__(cls, name, device):
            raise RuntimeError("unrelated error")

    monkeypatch.setattr("sentence_transformers.SentenceTransformer", FakeST)
    monkeypatch.setattr(embedding, "_resolve_device", lambda d: "cuda")

    try:
        embedding._get_model(device="auto", cfg=_make_default_cfg())
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "unrelated error" in str(e)


@pytest.mark.slow
def test_bge_m3_loads_and_embeds_at_1024_dim():
    """Regression: bge-m3 must load + first-encode without hanging.

    The SDP-disable workaround in embedding._get_model is what makes this
    possible — without it, the first CUDA encode triggers a 3+ minute
    flash-attention JIT compilation. If a future torch upgrade breaks the
    workaround, this test catches it before users hit the hang in production
    reindex.

    Marked @pytest.mark.slow because:
    - First run downloads ~2 GB of model weights
    - Even cached, model load takes ~8s
    Default pytest config excludes -m slow tests.
    """
    from unittest.mock import MagicMock
    import cognitive_castle.embedding as emb

    cfg = MagicMock()
    cfg.embedder_model = "BAAI/bge-m3"
    model = emb._get_model(device="auto", cfg=cfg)
    vecs = model.encode(
        ["hello world", "ahoj jak se mas", "cognitive castle"],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    assert vecs.shape == (3, 1024)
    # L2-normalized: first vector should have unit norm
    assert abs(float((vecs[0] ** 2).sum()) ** 0.5 - 1.0) < 1e-4
