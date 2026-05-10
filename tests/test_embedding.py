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


def test_auto_picks_cuda(monkeypatch):
    monkeypatch.setattr(
        "onnxruntime.get_available_providers",
        lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
    )

    assert embedding._resolve_providers("auto") == (
        ["CUDAExecutionProvider", "CPUExecutionProvider"],
        "cuda",
    )


def test_auto_falls_to_cpu(monkeypatch):
    monkeypatch.setattr("onnxruntime.get_available_providers", lambda: ["CPUExecutionProvider"])

    assert embedding._resolve_providers("auto") == (["CPUExecutionProvider"], "cpu")


def test_cuda_missing_warns_with_gpu_extra(monkeypatch, caplog):
    monkeypatch.setattr("onnxruntime.get_available_providers", lambda: ["CPUExecutionProvider"])

    assert embedding._resolve_providers("cuda") == (["CPUExecutionProvider"], "cpu")
    assert "mempalace[gpu]" in caplog.text


def test_coreml_missing_warns_with_coreml_extra(monkeypatch, caplog):
    monkeypatch.setattr("onnxruntime.get_available_providers", lambda: ["CPUExecutionProvider"])

    assert embedding._resolve_providers("coreml") == (["CPUExecutionProvider"], "cpu")
    assert "mempalace[coreml]" in caplog.text


def test_dml_missing_warns_with_dml_extra(monkeypatch, caplog):
    monkeypatch.setattr("onnxruntime.get_available_providers", lambda: ["CPUExecutionProvider"])

    assert embedding._resolve_providers("dml") == (["CPUExecutionProvider"], "cpu")
    assert "mempalace[dml]" in caplog.text


def test_unknown_device_warns_once(monkeypatch, caplog):
    monkeypatch.setattr("onnxruntime.get_available_providers", lambda: ["CPUExecutionProvider"])

    assert embedding._resolve_providers("bogus") == (["CPUExecutionProvider"], "cpu")
    assert embedding._resolve_providers("bogus") == (["CPUExecutionProvider"], "cpu")
    assert caplog.text.count("Unknown embedding_device") == 1


def test_onnxruntime_import_error_falls_back_to_cpu(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "onnxruntime":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert embedding._resolve_providers("cuda") == (["CPUExecutionProvider"], "cpu")


def test_get_embedding_function_caches_by_resolved_provider_tuple(monkeypatch):
    class DummyEF:
        def __init__(self, preferred_providers):
            self.preferred_providers = preferred_providers

    monkeypatch.setattr(embedding, "_build_ef_class", lambda: DummyEF)
    monkeypatch.setattr(
        embedding, "_resolve_providers", lambda device: (["CPUExecutionProvider"], "cpu")
    )

    first = embedding.get_embedding_function("cpu")
    second = embedding.get_embedding_function("auto")

    assert first is second
    assert first.preferred_providers == ["CPUExecutionProvider"]


def test_describe_device_uses_resolved_effective_device(monkeypatch):
    monkeypatch.setattr(
        embedding,
        "_resolve_providers",
        lambda device: (["CUDAExecutionProvider", "CPUExecutionProvider"], "cuda"),
    )

    assert embedding.describe_device("auto") == "cuda"


def test_embedding_uses_config_default_model_when_unspecified():
    """Without overrides, the embedder reads model name from config."""
    from cognitive_castle.embedding import _resolve_model_name

    cfg = _make_default_cfg()  # see helper below
    assert _resolve_model_name(cfg) == cfg.embedder_model
    # And the default is still all-MiniLM at this point in the rollout.
    assert _resolve_model_name(cfg) == "all-MiniLM-L6-v2"


def test_embedding_respects_config_override():
    from cognitive_castle.embedding import _resolve_model_name
    from unittest.mock import MagicMock

    cfg = MagicMock()
    cfg.embedder_model = "BAAI/bge-m3"
    assert _resolve_model_name(cfg) == "BAAI/bge-m3"


def _make_default_cfg():
    """Return an instance of the project's config class with all defaults."""
    # The actual config class name may be MempalaceConfig (legacy) or CognitiveCastleConfig.
    # Try CognitiveCastleConfig first, fall back to MempalaceConfig.
    try:
        from cognitive_castle.config import CognitiveCastleConfig
        return CognitiveCastleConfig()
    except ImportError:
        from cognitive_castle.config import MempalaceConfig
        return MempalaceConfig()
