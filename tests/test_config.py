import os
import json
import tempfile

import pytest
from cognitive_castle.config import (
    CognitiveCastleConfig,
    normalize_wing_name,
    sanitize_kg_value,
    sanitize_name,
)


def test_default_config():
    cfg = CognitiveCastleConfig(config_dir=tempfile.mkdtemp())
    assert "palace" in cfg.palace_path
    assert cfg.collection_name == "castle_drawers"


def test_config_from_file():
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "config.json"), "w") as f:
        json.dump({"palace_path": "/custom/palace"}, f)
    cfg = CognitiveCastleConfig(config_dir=tmpdir)
    assert cfg.palace_path == "/custom/palace"


def test_embedding_device_defaults_to_auto(monkeypatch):
    monkeypatch.delenv("CASTLE_EMBEDDING_DEVICE", raising=False)
    cfg = CognitiveCastleConfig(config_dir=tempfile.mkdtemp())
    assert cfg.embedding_device == "auto"


def test_embedding_device_from_config_is_normalized(tmp_path, monkeypatch):
    monkeypatch.delenv("CASTLE_EMBEDDING_DEVICE", raising=False)
    with open(tmp_path / "config.json", "w") as f:
        json.dump({"embedding_device": "  CUDA  "}, f)

    cfg = CognitiveCastleConfig(config_dir=str(tmp_path))
    assert cfg.embedding_device == "cuda"


def test_embedding_device_env_overrides_config(tmp_path, monkeypatch):
    with open(tmp_path / "config.json", "w") as f:
        json.dump({"embedding_device": "cpu"}, f)
    monkeypatch.setenv("CASTLE_EMBEDDING_DEVICE", "  CoreML  ")

    cfg = CognitiveCastleConfig(config_dir=str(tmp_path))
    assert cfg.embedding_device == "coreml"


def test_env_override():
    raw = "/env/palace"
    os.environ["CASTLE_PALACE_PATH"] = raw
    try:
        cfg = CognitiveCastleConfig(config_dir=tempfile.mkdtemp())
        # palace_path normalizes with abspath + expanduser to match the
        # --palace CLI code path. On Unix that's a no-op for "/env/palace";
        # on Windows abspath prepends the current drive letter.
        assert cfg.palace_path == os.path.abspath(os.path.expanduser(raw))
    finally:
        del os.environ["CASTLE_PALACE_PATH"]


def test_env_path_expanduser():
    # Tilde must be expanded to match the --palace CLI code path. We don't
    # assert "~" is absent from the final string because Windows 8.3 short
    # paths (e.g. C:\Users\RUNNER~1\...) legitimately contain tildes — the
    # equality check is authoritative.
    raw = os.path.join("~", "mempalace-test")
    os.environ["CASTLE_PALACE_PATH"] = raw
    try:
        cfg = CognitiveCastleConfig(config_dir=tempfile.mkdtemp())
        assert cfg.palace_path == os.path.abspath(os.path.expanduser(raw))
        assert cfg.palace_path.endswith("mempalace-test")
    finally:
        del os.environ["CASTLE_PALACE_PATH"]


def test_env_path_abspath_collapses_traversal():
    # Build a raw path with a .. segment using the platform separator so
    # the assertion is portable (Windows uses \, POSIX uses /).
    raw = os.path.join(tempfile.gettempdir(), "palace", "..", "mempalace-test")
    expected = os.path.abspath(os.path.expanduser(raw))
    os.environ["CASTLE_PALACE_PATH"] = raw
    try:
        cfg = CognitiveCastleConfig(config_dir=tempfile.mkdtemp())
        # .. segments must be collapsed, not preserved literally.
        assert ".." not in cfg.palace_path
        assert cfg.palace_path == expected
    finally:
        del os.environ["CASTLE_PALACE_PATH"]


def test_env_path_legacy_alias_normalized():
    # Legacy MEMPAL_PALACE_PATH gets the same normalization treatment as
    # CASTLE_PALACE_PATH. We don't assert "~" is absent from the final
    # string because Windows 8.3 short paths (e.g. C:\Users\RUNNER~1\...)
    # legitimately contain tildes — the equality check below is authoritative.
    os.environ.pop("CASTLE_PALACE_PATH", None)
    raw = os.path.join("~", "legacy-alias", "..", "mempalace-test")
    os.environ["MEMPAL_PALACE_PATH"] = raw
    try:
        cfg = CognitiveCastleConfig(config_dir=tempfile.mkdtemp())
        assert ".." not in cfg.palace_path
        assert cfg.palace_path == os.path.abspath(os.path.expanduser(raw))
    finally:
        del os.environ["MEMPAL_PALACE_PATH"]


def test_init():
    tmpdir = tempfile.mkdtemp()
    cfg = CognitiveCastleConfig(config_dir=tmpdir)
    cfg.init()
    assert os.path.exists(os.path.join(tmpdir, "config.json"))


# --- normalize_wing_name ---


def test_normalize_wing_name_hyphen():
    assert normalize_wing_name("mempal-private") == "mempal_private"


def test_normalize_wing_name_space():
    assert normalize_wing_name("My Project") == "my_project"


def test_normalize_wing_name_already_clean():
    assert normalize_wing_name("memorymark") == "memorymark"


def test_normalize_wing_name_mixed():
    assert normalize_wing_name("My-Cool App") == "my_cool_app"


# --- sanitize_name ---


def test_sanitize_name_ascii():
    assert sanitize_name("hello") == "hello"


def test_sanitize_name_latvian():
    assert sanitize_name("Jānis") == "Jānis"


def test_sanitize_name_cjk():
    assert sanitize_name("太郎") == "太郎"


def test_sanitize_name_cyrillic():
    assert sanitize_name("Алексей") == "Алексей"


def test_sanitize_name_rejects_leading_underscore():
    with pytest.raises(ValueError):
        sanitize_name("_foo")


def test_sanitize_name_rejects_path_traversal():
    with pytest.raises(ValueError):
        sanitize_name("../etc/passwd")


def test_sanitize_name_rejects_empty():
    with pytest.raises(ValueError):
        sanitize_name("")


# --- sanitize_kg_value ---


def test_kg_value_accepts_commas():
    assert sanitize_kg_value("Alice, Bob, and Carol") == "Alice, Bob, and Carol"


def test_kg_value_accepts_colons():
    assert sanitize_kg_value("role: engineer") == "role: engineer"


def test_kg_value_accepts_parentheses():
    assert sanitize_kg_value("Python (programming)") == "Python (programming)"


def test_kg_value_accepts_slashes():
    assert sanitize_kg_value("owner/repo") == "owner/repo"


def test_kg_value_accepts_hash():
    assert sanitize_kg_value("issue #123") == "issue #123"


def test_kg_value_accepts_unicode():
    assert sanitize_kg_value("Jānis Bērziņš") == "Jānis Bērziņš"


def test_kg_value_strips_whitespace():
    assert sanitize_kg_value("  hello  ") == "hello"


def test_kg_value_rejects_empty():
    with pytest.raises(ValueError):
        sanitize_kg_value("")


def test_kg_value_rejects_whitespace_only():
    with pytest.raises(ValueError):
        sanitize_kg_value("   ")


def test_kg_value_rejects_null_bytes():
    with pytest.raises(ValueError):
        sanitize_kg_value("hello\x00world")


def test_kg_value_rejects_over_length():
    with pytest.raises(ValueError):
        sanitize_kg_value("a" * 129)


def test_config_has_retrieval_upgrade_keys():
    from cognitive_castle.config import CognitiveCastleConfig

    cfg = CognitiveCastleConfig()
    # Cutover: defaults are now the new stack.
    assert cfg.embedder_model == "BAAI/bge-m3"
    assert cfg.embedder_dim == 1024
    assert cfg.use_new_retrieval_pipeline is True
    # Reranker, fusion, recency, kg-hop unchanged.
    assert cfg.reranker_model_gpu == "BAAI/bge-reranker-v2-m3"
    assert cfg.reranker_model_cpu == "BAAI/bge-reranker-base"
    assert cfg.reranker_k_interactive == 20
    assert cfg.reranker_k_hook == 10
    assert cfg.k_rrf == 60
    assert cfg.weight_dense == 1.0
    assert cfg.weight_sparse == 1.0
    assert cfg.weight_kg == 0.5
    assert cfg.recency_tau_days == 90.0
    assert cfg.recency_max_boost == 1.5
    assert cfg.kg_hop_top_n == 50


def test_use_new_retrieval_pipeline_handles_false_string_in_config_json(tmp_path):
    """Test that string 'false' in config.json is correctly parsed as False."""
    with open(tmp_path / "config.json", "w") as f:
        json.dump({"use_new_retrieval_pipeline": "false"}, f)

    cfg = CognitiveCastleConfig(config_dir=str(tmp_path))
    assert cfg.use_new_retrieval_pipeline is False


def test_embedder_dim_rejects_negative_in_config_json(tmp_path):
    """Test that negative embedder_dim in config.json falls back to default."""
    with open(tmp_path / "config.json", "w") as f:
        json.dump({"embedder_dim": -1}, f)

    cfg = CognitiveCastleConfig(config_dir=str(tmp_path))
    assert cfg.embedder_dim == 1024


def test_cognitive_castle_config_is_canonical_name():
    """CognitiveCastleConfig is the new canonical class name."""
    from cognitive_castle.config import CognitiveCastleConfig

    cfg = CognitiveCastleConfig()
    # Sanity check: an existing property still works.
    assert cfg.embedder_model == "BAAI/bge-m3"


def test_mempalace_config_is_backward_compat_alias():
    """MempalaceConfig still importable as an alias to CognitiveCastleConfig."""
    from cognitive_castle.config import MempalaceConfig, CognitiveCastleConfig

    # Same class object (alias, not a separate class).
    assert MempalaceConfig is CognitiveCastleConfig
    # Instances of one are instances of the other.
    cfg = MempalaceConfig()
    assert isinstance(cfg, CognitiveCastleConfig)


# ── Helper for LLM-judge config tests ──────────────────────────────────────


def _make_config_with_file_config(file_config):
    """Construct a CognitiveCastleConfig with a custom file config dict.

    Used by LLM-judge property tests. Bypasses JSON parsing by directly
    setting _file_config, allowing tests to override individual properties
    without touching the filesystem.
    """
    cfg = CognitiveCastleConfig(config_dir=tempfile.mkdtemp())
    cfg._file_config = file_config
    return cfg


# ── LLM-judge config properties (Stage 4 judge module contract) ──────────────


def test_llm_judge_top_n_default():
    """Without env var or config file, defaults to 10."""
    cfg = _make_config_with_file_config({})
    assert cfg.llm_judge_top_n == 10


def test_llm_judge_top_n_env_override(monkeypatch):
    """CASTLE_LLM_JUDGE_TOP_N env var takes precedence."""
    monkeypatch.setenv("CASTLE_LLM_JUDGE_TOP_N", "15")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_judge_top_n == 15


def test_llm_provider_default_is_ollama():
    cfg = _make_config_with_file_config({})
    assert cfg.llm_provider == "ollama"


def test_llm_provider_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_LLM_PROVIDER", "anthropic")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_provider == "anthropic"


def test_llm_model_default_matches_cmd_init_default():
    """Default tracks cmd_init's hardcoded default at cli.py:267.

    Note: both `cfg.llm_model` and `cmd_init`'s `--llm-model` default
    point at `gemma3:4b` — a real Ollama tag. This test verifies the
    config-driven and CLI-driven paths stay in sync; if a future change
    drifts them apart, users would get different LLM defaults via
    `castle init` vs in-process config loading. Both must match.
    """
    cfg = _make_config_with_file_config({})
    assert cfg.llm_model == "gemma3:4b"


def test_llm_model_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_LLM_MODEL", "llama3:8b")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_model == "llama3:8b"


def test_llm_endpoint_default_is_none():
    cfg = _make_config_with_file_config({})
    assert cfg.llm_endpoint is None


def test_llm_endpoint_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_LLM_ENDPOINT", "http://localhost:1234")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_endpoint == "http://localhost:1234"


def test_llm_api_key_default_is_none():
    cfg = _make_config_with_file_config({})
    assert cfg.llm_api_key is None


def test_llm_api_key_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_LLM_API_KEY", "sk-test-1234")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_api_key == "sk-test-1234"


def test_llm_timeout_default_is_120():
    cfg = _make_config_with_file_config({})
    assert cfg.llm_timeout == 120


def test_llm_timeout_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_LLM_TIMEOUT", "60")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_timeout == 60


def test_soar_enabled_default_is_false():
    cfg = _make_config_with_file_config({})
    assert cfg.soar_enabled is False


def test_soar_enabled_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_SOAR_ENABLED", "1")
    cfg = _make_config_with_file_config({})
    assert cfg.soar_enabled is True


def test_soar_rules_path_default_points_at_package():
    cfg = _make_config_with_file_config({})
    # Default should be <package>/rules/castle-boost.soar
    assert cfg.soar_rules_path.endswith("rules/castle-boost.soar")
    assert "cognitive_castle" in cfg.soar_rules_path


def test_soar_rules_path_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "my-rules.soar"
    custom.write_text("# placeholder")
    monkeypatch.setenv("CASTLE_SOAR_RULES_PATH", str(custom))
    cfg = _make_config_with_file_config({})
    assert cfg.soar_rules_path == str(custom)


def test_embedder_identity_auto_derives_from_model(monkeypatch):
    """When CASTLE_EMBEDDER_IDENTITY is unset, identity derives from the model path."""
    from cognitive_castle.config import CognitiveCastleConfig

    # Clear any existing override
    monkeypatch.delenv("CASTLE_EMBEDDER_IDENTITY", raising=False)
    monkeypatch.setenv("CASTLE_EMBEDDER_MODEL", "BAAI/bge-large-en-v1.5")
    cfg = CognitiveCastleConfig()
    assert cfg.embedder_identity == "bge-large-en-v1.5"

    # Default model (no override) derives to "bge-m3"
    monkeypatch.delenv("CASTLE_EMBEDDER_MODEL", raising=False)
    cfg = CognitiveCastleConfig()
    assert cfg.embedder_identity == "bge-m3"

    # Explicit identity wins over auto-derive
    monkeypatch.setenv("CASTLE_EMBEDDER_IDENTITY", "custom-id")
    cfg = CognitiveCastleConfig()
    assert cfg.embedder_identity == "custom-id"
