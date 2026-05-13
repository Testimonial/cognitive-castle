"""Unit tests for the SOAR post-pipeline boost-tag bridge (PR #4a).

Soar-gated tests use @pytest.mark.soar and @_requires_sml — they auto-skip
if Python_sml_ClientInterface isn't importable. Always-run tests verify
the SML-unavailable fallback path + kill-switch behavior without needing
Soar installed.
"""

import time
from unittest.mock import MagicMock

import pytest

_SML_AVAILABLE = False
try:
    import Python_sml_ClientInterface  # noqa: F401

    _SML_AVAILABLE = True
except ImportError:
    pass

_requires_sml = pytest.mark.skipif(not _SML_AVAILABLE, reason="Soar 9.6+ SML not installed")


@pytest.fixture(autouse=True)
def reset_soar_state():
    """Clear singleton kernel + agent cache between tests so they don't share state."""
    yield
    from cognitive_castle import soar_bridge

    soar_bridge._reset_for_test()


def _mock_cfg(soar_enabled=True, rules_path=None):
    """Minimal cfg for tests — only the fields apply_soar_boosts reads."""
    cfg = MagicMock()
    cfg.soar_enabled = soar_enabled
    cfg.soar_rules_path = rules_path or "/dev/null"
    cfg.palace_path = "/tmp/test-palace"
    return cfg


# ── Always-run tests (no Soar dependency) ─────────────────────────────


def test_apply_soar_boosts_no_op_when_sml_unavailable(monkeypatch, capsys):
    """When _load_sml() returns None, return hits unchanged + stderr warning ONCE."""
    from cognitive_castle import soar_bridge

    monkeypatch.setattr(soar_bridge, "_load_sml", lambda: None)
    soar_bridge._WARNED.clear()
    hits = [{"id": "a", "score": 0.5}]
    result = soar_bridge.apply_soar_boosts(hits, _mock_cfg())
    assert result == hits  # unchanged
    err = capsys.readouterr().err
    assert "SML Python bindings not available" in err


def test_apply_soar_boosts_kill_switch_when_disabled(monkeypatch, capsys):
    """When cfg.soar_enabled=False, return hits unchanged + stderr 'disabled'.

    The kill-switch ALSO fires at the CLI/MCP layer before apply_soar_boosts
    is called; this test covers the defensive double-check at the function level.
    """
    from cognitive_castle import soar_bridge

    soar_bridge._WARNED.clear()
    hits = [{"id": "a", "score": 0.5}]
    result = soar_bridge.apply_soar_boosts(hits, _mock_cfg(soar_enabled=False))
    assert result == hits
    err = capsys.readouterr().err
    assert "disabled" in err.lower() or "soar_enabled" in err.lower()


# ── Soar-required tests (skip if SML unavailable) ──────────────────────


def _write_minimal_rules(path):
    """Write a minimal castle-boost.soar with both production rules to `path`."""
    path.write_text("""
sp {castle-boost*recency-boost
    (state <s> ^io.input-link.memory <m>)
    (<m> ^recently-accessed true)
-->
    (<m> ^boost-tag recency-boost)
}

sp {castle-boost*same-project
    (state <s> ^io.input-link <il>)
    (<il> ^context.project <p>)
    (<il> ^memory <m>)
    (<m> ^project <p>)
-->
    (<m> ^boost-tag same-project)
}
""")


def _write_empty_rules(path):
    """Write an empty .soar file — agent loads no productions, no tags fire."""
    path.write_text("# empty\n")


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_loads_rules_and_runs_decision_cycle(tmp_path):
    """Smoke: SOAR kernel + agent + rule file load + decision cycle completes."""
    from cognitive_castle import soar_bridge

    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    hits = [
        {"id": "a", "score": 0.5, "wing": "proj", "created_at": "2026-05-13T00:00:00"},
        {"id": "b", "score": 0.4, "wing": "other", "created_at": "2020-01-01T00:00:00"},
    ]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    assert len(result) == 2
    assert all("soar_boost" in h for h in result)
    assert all("soar_tags" in h for h in result)
    assert all("score_pre_soar" in h for h in result)


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_returns_hits_unchanged_when_no_tags_fire(tmp_path):
    """Empty rule file → hits returned with soar_boost=1.0, soar_tags=[]."""
    from cognitive_castle import soar_bridge

    rules = tmp_path / "empty.soar"
    _write_empty_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    hits = [{"id": "a", "score": 0.5, "wing": "x"}]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    assert result[0]["soar_boost"] == 1.0
    assert result[0]["soar_tags"] == []
    assert result[0]["score_pre_soar"] == 0.5
    assert result[0]["score"] == 0.5  # unchanged


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_multiplies_score_for_recency_tag(tmp_path):
    """A hit with recently-accessed=true → recency-boost tag → score × 1.25."""
    from cognitive_castle import soar_bridge

    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    # created_at within 7 days → recently-accessed
    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 3600))
    hits = [{"id": "a", "score": 1.0, "wing": "p", "created_at": recent_iso}]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    assert "recency-boost" in result[0]["soar_tags"]
    assert result[0]["soar_boost"] == 1.25
    assert result[0]["score"] == 1.25


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_compounds_multiple_tags(tmp_path, monkeypatch):
    """A hit matching both rules → both tags fire → multipliers compound (1.25 × 1.15 = 1.4375)."""
    from cognitive_castle import soar_bridge

    monkeypatch.setenv("CASTLE_PROJECT", "demo-project")
    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 3600))
    hits = [{"id": "a", "score": 1.0, "wing": "demo-project", "created_at": recent_iso}]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    assert set(result[0]["soar_tags"]) == {"recency-boost", "same-project"}
    assert abs(result[0]["soar_boost"] - 1.4375) < 1e-6
    assert abs(result[0]["score"] - 1.4375) < 1e-6


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_clamps_to_range(tmp_path, monkeypatch):
    """Compounded multipliers > 10.0 → clamped to 10.0 upper bound."""
    from cognitive_castle import soar_bridge

    # Inject extreme multipliers to test the clamp
    monkeypatch.setitem(soar_bridge.BOOST_MULTIPLIERS, "recency-boost", 100.0)
    monkeypatch.setitem(soar_bridge.BOOST_MULTIPLIERS, "same-project", 100.0)
    monkeypatch.setenv("CASTLE_PROJECT", "demo")
    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    hits = [{"id": "a", "score": 1.0, "wing": "demo", "created_at": recent_iso}]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    # Compound would be 100×100=10000, clamped to 10.0
    assert result[0]["soar_boost"] == 10.0
    assert result[0]["score"] == 10.0


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_truncates_to_50_hits(tmp_path, capsys):
    """Input of 60 hits → WM populated with first 50; remaining 10 returned unboosted + stderr warning."""
    from cognitive_castle import soar_bridge

    soar_bridge._WARNED.clear()
    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    hits = [{"id": f"id{i}", "score": 0.5, "wing": "p"} for i in range(60)]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    assert len(result) == 60
    # First 50 have audit fields populated
    assert all("soar_boost" in h for h in result[:50])
    # Last 10 have soar_boost == 1.0 (unboosted) but still get audit fields with defaults
    for h in result[50:]:
        assert h.get("soar_boost", 1.0) == 1.0
        assert h.get("soar_tags", []) == []
    err = capsys.readouterr().err
    assert "truncated WM to 50" in err


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_clears_wm_between_calls(tmp_path):
    """Two sequential calls don't leak boost-tags from the first call into the second."""
    from cognitive_castle import soar_bridge

    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))

    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    # First call: hit gets recency-boost
    hits1 = [{"id": "first", "score": 1.0, "wing": "p", "created_at": recent_iso}]
    result1 = soar_bridge.apply_soar_boosts(hits1, cfg)
    assert "recency-boost" in result1[0]["soar_tags"]

    # Second call: hit does NOT have recently-accessed → no recency tag should fire
    old_iso = "2020-01-01T00:00:00"
    hits2 = [{"id": "second", "score": 1.0, "wing": "p", "created_at": old_iso}]
    result2 = soar_bridge.apply_soar_boosts(hits2, cfg)
    assert "recency-boost" not in result2[0]["soar_tags"]
    assert result2[0]["soar_boost"] == 1.0


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_unknown_tag_ignored_with_warning(tmp_path, capsys):
    """A rule that emits an unrecognized boost-tag → tag ignored, stderr warning once."""
    from cognitive_castle import soar_bridge

    soar_bridge._WARNED.clear()
    rules = tmp_path / "rules.soar"
    rules.write_text("""
sp {castle-boost*custom-tag
    (state <s> ^io.input-link.memory <m>)
-->
    (<m> ^boost-tag mystery-tag)
}
""")
    cfg = _mock_cfg(rules_path=str(rules))
    hits = [{"id": "a", "score": 1.0, "wing": "p"}]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    # mystery-tag isn't in BOOST_MULTIPLIERS → ignored, score unchanged
    assert result[0]["soar_boost"] == 1.0
    err = capsys.readouterr().err
    assert "unknown boost-tag" in err.lower()
    assert "mystery-tag" in err
