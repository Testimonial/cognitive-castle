import os
import json
import tempfile

import pytest
from cognitive_castle.config import MempalaceConfig, normalize_wing_name, sanitize_kg_value, sanitize_name


def test_default_config():
    cfg = MempalaceConfig(config_dir=tempfile.mkdtemp())
    assert "palace" in cfg.palace_path
    assert cfg.collection_name == "castle_drawers"


def test_config_from_file():
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "config.json"), "w") as f:
        json.dump({"palace_path": "/custom/palace"}, f)
    cfg = MempalaceConfig(config_dir=tmpdir)
    assert cfg.palace_path == "/custom/palace"


def test_embedding_device_defaults_to_auto(monkeypatch):
    monkeypatch.delenv("MEMPALACE_EMBEDDING_DEVICE", raising=False)
    cfg = MempalaceConfig(config_dir=tempfile.mkdtemp())
    assert cfg.embedding_device == "auto"


def test_embedding_device_from_config_is_normalized(tmp_path, monkeypatch):
    monkeypatch.delenv("MEMPALACE_EMBEDDING_DEVICE", raising=False)
    with open(tmp_path / "config.json", "w") as f:
        json.dump({"embedding_device": "  CUDA  "}, f)

    cfg = MempalaceConfig(config_dir=str(tmp_path))
    assert cfg.embedding_device == "cuda"


def test_embedding_device_env_overrides_config(tmp_path, monkeypatch):
    with open(tmp_path / "config.json", "w") as f:
        json.dump({"embedding_device": "cpu"}, f)
    monkeypatch.setenv("MEMPALACE_EMBEDDING_DEVICE", "  CoreML  ")

    cfg = MempalaceConfig(config_dir=str(tmp_path))
    assert cfg.embedding_device == "coreml"


def test_env_override():
    raw = "/env/palace"
    os.environ["MEMPALACE_PALACE_PATH"] = raw
    try:
        cfg = MempalaceConfig(config_dir=tempfile.mkdtemp())
        # palace_path normalizes with abspath + expanduser to match the
        # --palace CLI code path. On Unix that's a no-op for "/env/palace";
        # on Windows abspath prepends the current drive letter.
        assert cfg.palace_path == os.path.abspath(os.path.expanduser(raw))
    finally:
        del os.environ["MEMPALACE_PALACE_PATH"]


def test_env_path_expanduser():
    # Tilde must be expanded to match the --palace CLI code path. We don't
    # assert "~" is absent from the final string because Windows 8.3 short
    # paths (e.g. C:\Users\RUNNER~1\...) legitimately contain tildes — the
    # equality check is authoritative.
    raw = os.path.join("~", "mempalace-test")
    os.environ["MEMPALACE_PALACE_PATH"] = raw
    try:
        cfg = MempalaceConfig(config_dir=tempfile.mkdtemp())
        assert cfg.palace_path == os.path.abspath(os.path.expanduser(raw))
        assert cfg.palace_path.endswith("mempalace-test")
    finally:
        del os.environ["MEMPALACE_PALACE_PATH"]


def test_env_path_abspath_collapses_traversal():
    # Build a raw path with a .. segment using the platform separator so
    # the assertion is portable (Windows uses \, POSIX uses /).
    raw = os.path.join(tempfile.gettempdir(), "palace", "..", "mempalace-test")
    expected = os.path.abspath(os.path.expanduser(raw))
    os.environ["MEMPALACE_PALACE_PATH"] = raw
    try:
        cfg = MempalaceConfig(config_dir=tempfile.mkdtemp())
        # .. segments must be collapsed, not preserved literally.
        assert ".." not in cfg.palace_path
        assert cfg.palace_path == expected
    finally:
        del os.environ["MEMPALACE_PALACE_PATH"]


def test_env_path_legacy_alias_normalized():
    # Legacy MEMPAL_PALACE_PATH gets the same normalization treatment as
    # MEMPALACE_PALACE_PATH. We don't assert "~" is absent from the final
    # string because Windows 8.3 short paths (e.g. C:\Users\RUNNER~1\...)
    # legitimately contain tildes — the equality check below is authoritative.
    os.environ.pop("MEMPALACE_PALACE_PATH", None)
    raw = os.path.join("~", "legacy-alias", "..", "mempalace-test")
    os.environ["MEMPAL_PALACE_PATH"] = raw
    try:
        cfg = MempalaceConfig(config_dir=tempfile.mkdtemp())
        assert ".." not in cfg.palace_path
        assert cfg.palace_path == os.path.abspath(os.path.expanduser(raw))
    finally:
        del os.environ["MEMPAL_PALACE_PATH"]


def test_init():
    tmpdir = tempfile.mkdtemp()
    cfg = MempalaceConfig(config_dir=tmpdir)
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
    from cognitive_castle.config import MempalaceConfig
    cfg = MempalaceConfig()
    # Cutover: defaults are now the new stack.
    assert cfg.embedder_model == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert cfg.embedder_dim == 384
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

    cfg = MempalaceConfig(config_dir=str(tmp_path))
    assert cfg.use_new_retrieval_pipeline is False


def test_embedder_dim_rejects_negative_in_config_json(tmp_path):
    """Test that negative embedder_dim in config.json falls back to default."""
    with open(tmp_path / "config.json", "w") as f:
        json.dump({"embedder_dim": -1}, f)

    cfg = MempalaceConfig(config_dir=str(tmp_path))
    assert cfg.embedder_dim == 384


def test_cognitive_castle_config_is_canonical_name():
    """CognitiveCastleConfig is the new canonical class name."""
    from cognitive_castle.config import CognitiveCastleConfig
    cfg = CognitiveCastleConfig()
    # Sanity check: an existing property still works.
    assert cfg.embedder_model == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def test_mempalace_config_is_backward_compat_alias():
    """MempalaceConfig still importable as an alias to CognitiveCastleConfig."""
    from cognitive_castle.config import MempalaceConfig, CognitiveCastleConfig
    # Same class object (alias, not a separate class).
    assert MempalaceConfig is CognitiveCastleConfig
    # Instances of one are instances of the other.
    cfg = MempalaceConfig()
    assert isinstance(cfg, CognitiveCastleConfig)
