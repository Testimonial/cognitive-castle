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
    # The actual config class name may be CognitiveCastleConfig (legacy) or CognitiveCastleConfig.
    # Try CognitiveCastleConfig first, fall back to CognitiveCastleConfig.
    try:
        from cognitive_castle.config import CognitiveCastleConfig
        return CognitiveCastleConfig()
    except ImportError:
        from cognitive_castle.config import CognitiveCastleConfig
        return CognitiveCastleConfig()
