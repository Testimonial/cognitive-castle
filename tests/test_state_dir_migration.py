"""Tests for _state_dir(): resolves hook state directory with legacy fallback."""


def _setup_homes(tmp_path, monkeypatch, new_exists: bool, old_exists: bool):
    """Point ~ at tmp_path; optionally create new and/or legacy dirs.

    Sets both the POSIX and Windows env vars — ``Path.home()`` reads
    ``USERPROFILE`` on Windows and ``HOME`` on POSIX, so we need both
    for the test to work on all CI platforms.
    """
    import os as _os

    monkeypatch.setenv("HOME", str(tmp_path))
    # Windows equivalents (Path.home() reads USERPROFILE first on Windows)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    drive, path = _os.path.splitdrive(str(tmp_path))
    monkeypatch.setenv("HOMEDRIVE", drive or "C:")
    monkeypatch.setenv("HOMEPATH", path or str(tmp_path))
    new = tmp_path / ".castle" / "hook_state"
    old = tmp_path / ".mempalace" / "hook_state"
    if new_exists:
        new.mkdir(parents=True, exist_ok=True)
    if old_exists:
        old.mkdir(parents=True, exist_ok=True)
    return new, old


def _import_fresh_state_dir():
    """Import _state_dir freshly so it picks up the current HOME env."""
    import importlib
    from cognitive_castle import hooks_cli

    importlib.reload(hooks_cli)
    return hooks_cli._state_dir, hooks_cli._DEPRECATED_LEGACY_ENV_WARNED


def test_new_dir_exists_returns_new(tmp_path, monkeypatch):
    new, _ = _setup_homes(tmp_path, monkeypatch, new_exists=True, old_exists=False)
    state_dir, warn_cache = _import_fresh_state_dir()
    warn_cache.clear()
    assert state_dir() == new


def test_only_legacy_exists_returns_legacy_with_log(tmp_path, monkeypatch, capsys):
    _, old = _setup_homes(tmp_path, monkeypatch, new_exists=False, old_exists=True)
    state_dir, warn_cache = _import_fresh_state_dir()
    warn_cache.clear()
    result = state_dir()
    captured = capsys.readouterr()
    assert result == old
    assert "legacy state dir" in captured.err.lower()


def test_neither_exists_creates_new(tmp_path, monkeypatch):
    new, _ = _setup_homes(tmp_path, monkeypatch, new_exists=False, old_exists=False)
    state_dir, warn_cache = _import_fresh_state_dir()
    warn_cache.clear()
    result = state_dir()
    assert result == new
    assert new.exists()


def test_both_exist_returns_new(tmp_path, monkeypatch):
    new, old = _setup_homes(tmp_path, monkeypatch, new_exists=True, old_exists=True)
    state_dir, warn_cache = _import_fresh_state_dir()
    warn_cache.clear()
    assert state_dir() == new


def test_legacy_log_fires_only_once(tmp_path, monkeypatch, capsys):
    _setup_homes(tmp_path, monkeypatch, new_exists=False, old_exists=True)
    state_dir, warn_cache = _import_fresh_state_dir()
    warn_cache.clear()
    capsys.readouterr()  # drain any stderr from the module-level STATE_DIR = _state_dir() call
    state_dir()
    state_dir()
    state_dir()
    captured = capsys.readouterr()
    assert captured.err.lower().count("legacy state dir") == 1
