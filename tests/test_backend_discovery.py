"""Backend extension failures must not hide working storage backends."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cognitive_castle.backends import registry
from cognitive_castle.backends.lancedb_backend import LanceDBBackend


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    monkeypatch.setattr(registry, "_registry", {})
    monkeypatch.setattr(registry, "_instances", {})
    monkeypatch.setattr(registry, "_explicit", set())
    monkeypatch.setattr(registry, "_discovered", False)


def test_discovery_skips_broken_extensions_and_preserves_explicit_override(monkeypatch):
    overridden = MagicMock()
    entries = [
        SimpleNamespace(name="override", load=overridden),
        SimpleNamespace(name="broken", load=MagicMock(side_effect=ImportError("missing"))),
        SimpleNamespace(name="invalid", load=lambda: object),
        SimpleNamespace(name="valid", load=lambda: LanceDBBackend),
    ]
    discover = MagicMock(return_value=SimpleNamespace(select=lambda **kw: entries))
    monkeypatch.setattr(registry.metadata, "entry_points", discover)
    registry.register("override", LanceDBBackend)
    assert registry.available_backends() == ["override", "valid"]
    assert registry.get_backend_class("valid") is LanceDBBackend
    overridden.assert_not_called()
    discover.assert_called_once()
    with pytest.raises(KeyError, match="unknown backend"):
        registry.get_backend_class("missing")


def test_discovery_failure_leaves_explicit_backend_available(monkeypatch):
    monkeypatch.setattr(
        registry.metadata, "entry_points", MagicMock(side_effect=OSError("bad metadata"))
    )
    registry.register("local", LanceDBBackend)
    assert registry.available_backends() == ["local"]


def test_reregistration_invalidates_cached_instance_and_reset_closes_all(monkeypatch):
    monkeypatch.setattr(registry.metadata, "entry_points", lambda: {})
    old, new, healthy = MagicMock(), MagicMock(), MagicMock()
    old_factory, new_factory = MagicMock(return_value=old), MagicMock(return_value=new)
    registry.register("local", old_factory)
    assert registry.get_backend("local") is old
    assert registry.get_backend("local") is old
    old_factory.assert_called_once()
    registry.register("local", new_factory)
    assert registry.get_backend("local") is new
    new.close.side_effect = OSError("close failed")
    registry.register("healthy", MagicMock(return_value=healthy))
    registry.get_backend("healthy")
    registry.reset_backends()
    new.close.assert_called_once()
    healthy.close.assert_called_once()
    assert registry._instances == {}
    registry.unregister("local")
    assert registry.available_backends() == ["healthy"]
    with pytest.raises(KeyError, match="unknown backend"):
        registry.get_backend("local")


def test_detection_continues_after_bad_backend(monkeypatch):
    monkeypatch.setattr(registry.metadata, "entry_points", lambda: {})
    registry.register("broken", SimpleNamespace(detect=MagicMock(side_effect=OSError("bad"))))
    registry.register("local", SimpleNamespace(detect=lambda path: path == "existing"))
    assert registry.resolve_backend_for_palace(palace_path="existing") == "local"
    assert registry.resolve_backend_for_palace(palace_path="new") == "lancedb"
    assert (
        registry.resolve_backend_for_palace(explicit="chosen", palace_path="existing") == "chosen"
    )
