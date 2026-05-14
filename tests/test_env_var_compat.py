"""Tests for _read_castle_env: CASTLE_* with legacy MEMPAL_* fallback."""

import pytest

from cognitive_castle.hooks_cli import _read_castle_env, _DEPRECATED_LEGACY_ENV_WARNED


@pytest.fixture(autouse=True)
def _clear_warn_cache():
    """Reset the per-process warning-once cache before each test."""
    _DEPRECATED_LEGACY_ENV_WARNED.clear()
    yield
    _DEPRECATED_LEGACY_ENV_WARNED.clear()


def test_castle_var_set_returns_castle_value(monkeypatch):
    monkeypatch.setenv("CASTLE_DIR", "/path/from/new")
    monkeypatch.delenv("MEMPAL_DIR", raising=False)
    assert _read_castle_env("CASTLE_DIR", "MEMPAL_DIR") == "/path/from/new"


def test_both_vars_set_castle_wins(monkeypatch):
    monkeypatch.setenv("CASTLE_DIR", "/from/new")
    monkeypatch.setenv("MEMPAL_DIR", "/from/old")
    assert _read_castle_env("CASTLE_DIR", "MEMPAL_DIR") == "/from/new"


def test_only_legacy_set_returns_legacy_with_warning(monkeypatch, capsys):
    monkeypatch.delenv("CASTLE_DIR", raising=False)
    monkeypatch.setenv("MEMPAL_DIR", "/path/from/old")
    out = _read_castle_env("CASTLE_DIR", "MEMPAL_DIR")
    captured = capsys.readouterr()
    assert out == "/path/from/old"
    assert "MEMPAL_DIR is deprecated" in captured.err
    assert "CASTLE_DIR" in captured.err


def test_neither_set_returns_default(monkeypatch):
    monkeypatch.delenv("CASTLE_DIR", raising=False)
    monkeypatch.delenv("MEMPAL_DIR", raising=False)
    assert _read_castle_env("CASTLE_DIR", "MEMPAL_DIR", default="/fallback") == "/fallback"


def test_neither_set_no_default_returns_empty_string(monkeypatch):
    monkeypatch.delenv("CASTLE_DIR", raising=False)
    monkeypatch.delenv("MEMPAL_DIR", raising=False)
    assert _read_castle_env("CASTLE_DIR", "MEMPAL_DIR") == ""


def test_warning_fires_only_once_per_process(monkeypatch, capsys):
    monkeypatch.delenv("CASTLE_DIR", raising=False)
    monkeypatch.setenv("MEMPAL_DIR", "/path")
    _read_castle_env("CASTLE_DIR", "MEMPAL_DIR")
    _read_castle_env("CASTLE_DIR", "MEMPAL_DIR")
    _read_castle_env("CASTLE_DIR", "MEMPAL_DIR")
    captured = capsys.readouterr()
    assert captured.err.count("MEMPAL_DIR is deprecated") == 1


def test_hooks_cli_uses_read_castle_env_for_dir(monkeypatch):
    """The MEMPAL_DIR caller in hooks_cli should now flow through the shim."""
    monkeypatch.delenv("CASTLE_DIR", raising=False)
    monkeypatch.setenv("MEMPAL_DIR", "/legacy/projects")
    _DEPRECATED_LEGACY_ENV_WARNED.clear()
    from cognitive_castle import hooks_cli

    assert hooks_cli._read_castle_env("CASTLE_DIR", "MEMPAL_DIR") == "/legacy/projects"


def test_castle_dir_takes_precedence_over_mempal_dir(monkeypatch):
    monkeypatch.setenv("CASTLE_DIR", "/new/projects")
    monkeypatch.setenv("MEMPAL_DIR", "/legacy/projects")
    from cognitive_castle import hooks_cli

    assert hooks_cli._read_castle_env("CASTLE_DIR", "MEMPAL_DIR") == "/new/projects"
