"""Unit tests for the SOAR post-pipeline boost-tag bridge (PR #4a).

Soar-gated tests use @pytest.mark.soar and @_requires_sml — they auto-skip
if Python_sml_ClientInterface isn't importable. Always-run tests verify
the SML-unavailable fallback path + kill-switch behavior without needing
Soar installed.
"""

import pathlib
import time
from unittest.mock import MagicMock

import pytest

# Path to the live castle-boost.soar rule file used by integration tests.
_RULES = str(
    pathlib.Path(__file__).parent.parent / "cognitive_castle" / "rules" / "castle-boost.soar"
)

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


def test_apply_soar_to_reranked_tuple_parity(monkeypatch, tmp_path):
    """_apply_soar_to_reranked on tuples produces same boost decisions as
    apply_soar_boosts on the equivalent dict hits."""
    from cognitive_castle import soar_bridge

    # Build paired inputs: same data in both shapes
    rows = [
        {
            "id": f"id-{i}",
            "score": 1.0 - i * 0.1,
            "wing": "project-a",
            "room": "room-1",
            "source_file": "f.md",
            "created_at": "2026-05-10T00:00:00Z",
        }
        for i in range(3)
    ]
    hits_dict = [{**r, "text": "doc", "document": "doc"} for r in rows]
    reranked_tuples = [(r["score"], dict(r, text="doc", document="doc")) for r in rows]

    cfg = _mock_cfg()

    # Call both APIs
    boosted_dict = soar_bridge.apply_soar_boosts(hits_dict, cfg)
    boosted_tuples = soar_bridge._apply_soar_to_reranked(reranked_tuples, cfg)

    # Parity check: same boost-tags fired on same ids
    dict_tags_by_id = {h["id"]: h["soar_tags"] for h in boosted_dict}
    tuple_tags_by_id = {row["id"]: row["soar_tags"] for _, row in boosted_tuples}
    assert dict_tags_by_id == tuple_tags_by_id

    # Parity check: same boost multipliers
    dict_boosts_by_id = {h["id"]: h["soar_boost"] for h in boosted_dict}
    tuple_boosts_by_id = {row["id"]: row["soar_boost"] for _, row in boosted_tuples}
    assert dict_boosts_by_id == tuple_boosts_by_id


def test_apply_soar_to_reranked_returns_sorted_tuples(tmp_path):
    """Output is sorted by boosted score descending."""
    from cognitive_castle import soar_bridge

    reranked = [
        (0.5, {"id": "a", "score": 0.5, "wing": "x", "room": "r", "source_file": "f"}),
        (0.8, {"id": "b", "score": 0.8, "wing": "x", "room": "r", "source_file": "f"}),
        (0.3, {"id": "c", "score": 0.3, "wing": "x", "room": "r", "source_file": "f"}),
    ]
    cfg = _mock_cfg()

    result = soar_bridge._apply_soar_to_reranked(reranked, cfg)
    scores = [s for s, _ in result]
    assert scores == sorted(scores, reverse=True), f"Expected descending sort, got {scores}"


def test_extract_filed_at_parses_metadata_json():
    """_extract_filed_at pulls filed_at out of the metadata_json JSON blob.

    Pipeline rows carry filed_at inside metadata_json (not promoted to a
    hoisted column). SOAR's recency rules need it at top-level created_at.
    """
    import json as _json
    from cognitive_castle import soar_bridge

    row = {"metadata_json": _json.dumps({"filed_at": "2026-05-14T07:21:34"})}
    assert soar_bridge._extract_filed_at(row) == "2026-05-14T07:21:34"

    # Missing / malformed metadata_json → empty string, never crash
    assert soar_bridge._extract_filed_at({}) == ""
    assert soar_bridge._extract_filed_at({"metadata_json": None}) == ""
    assert soar_bridge._extract_filed_at({"metadata_json": "not json"}) == ""
    assert soar_bridge._extract_filed_at({"metadata_json": "{}"}) == ""


@pytest.mark.soar
@_requires_sml
def test_apply_soar_to_reranked_promotes_filed_at_for_recency(tmp_path):
    """Pipeline-shape rows (filed_at inside metadata_json) get recency-boost.

    Regression for the bug where _apply_soar_to_reranked passed raw pipeline
    rows to apply_soar_boosts without first promoting filed_at → created_at,
    causing recency-boost to never fire on real-world pipeline output (rows
    coming from get_by_ids).
    """
    import json as _json
    from cognitive_castle import soar_bridge

    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))

    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 3600))
    # Pipeline-shape row: filed_at is buried in metadata_json, NOT at top level.
    row = {
        "id": "a",
        "wing": "p",
        "room": "r",
        "source_file": "f",
        "metadata_json": _json.dumps({"filed_at": recent_iso}),
    }
    reranked = [(1.0, row)]

    result = soar_bridge._apply_soar_to_reranked(reranked, cfg)
    _, boosted_row = result[0]
    assert "recency-boost" in boosted_row.get("soar_tags", []), (
        f"recency-boost should fire on pipeline-shape rows; "
        f"got soar_tags={boosted_row.get('soar_tags')!r}"
    )
    assert boosted_row["created_at"] == recent_iso, (
        "filed_at should be promoted to top-level created_at"
    )


def test_entity_match_boost_applied_when_flag_true(tmp_path):
    """A hit with entity_match=True fires the entity-match rule.

    Uses the existing _mock_cfg helper from this file. Requires SML to actually
    fire the rule; on test environments without SML, the boost-tag never appears.
    """
    import pathlib
    from cognitive_castle import soar_bridge

    _RULES = str(
        pathlib.Path(__file__).parent.parent / "cognitive_castle" / "rules" / "castle-boost.soar"
    )

    hits = [
        {
            "id": "a",
            "score": 1.0,
            "wing": "x",
            "room": "r",
            "source_file": "f",
            "entity_match": True,
            "created_at": "2020-01-01T00:00:00Z",  # old → recency-boost won't fire
        }
    ]
    cfg = _mock_cfg(rules_path=_RULES)

    boosted = soar_bridge.apply_soar_boosts(hits, cfg)
    # On SML-available environments, the rule fires
    if soar_bridge._load_sml() is not None:
        assert "entity-match" in boosted[0]["soar_tags"], (
            f"Expected entity-match tag to fire; got soar_tags={boosted[0]['soar_tags']}"
        )
        assert boosted[0]["soar_boost"] >= 1.30, (
            f"Expected boost >= 1.30, got {boosted[0]['soar_boost']}"
        )


def test_entity_match_boost_not_applied_when_flag_false(tmp_path):
    """A hit with entity_match=False does NOT fire the entity-match rule."""
    import pathlib
    from cognitive_castle import soar_bridge

    _RULES_local = str(
        pathlib.Path(__file__).parent.parent / "cognitive_castle" / "rules" / "castle-boost.soar"
    )

    hits = [
        {
            "id": "a",
            "score": 1.0,
            "wing": "x",
            "room": "r",
            "source_file": "f",
            "entity_match": False,
            "created_at": "2020-01-01T00:00:00Z",
        }
    ]
    cfg = _mock_cfg(rules_path=_RULES_local)

    boosted = soar_bridge.apply_soar_boosts(hits, cfg)
    if soar_bridge._load_sml() is not None:
        assert "entity-match" not in boosted[0]["soar_tags"], (
            "Rule should not fire when entity_match=False"
        )


def test_type_match_boost_applied_when_types_match(tmp_path):
    """Query classifies to 'decision', drawer room='decision' → rule fires.

    Requires SML-available env to exercise the rule; assertions are skipped
    on environments without SML (same pattern as other soar_bridge tests).
    """
    from cognitive_castle import soar_bridge

    hits = [
        {
            "id": "a",
            "score": 1.0,
            "wing": "x",
            "room": "decision",  # ← matches the query intent
            "source_file": "f",
            "entity_match": False,
            "created_at": "2020-01-01T00:00:00Z",  # old → recency-boost won't fire
        }
    ]
    cfg = _mock_cfg(rules_path=_RULES)

    boosted = soar_bridge.apply_soar_boosts(hits, cfg, query="what did we decide about X")

    if soar_bridge._load_sml() is not None:
        assert "type-match" in boosted[0]["soar_tags"], (
            f"Expected type-match tag to fire; got soar_tags={boosted[0]['soar_tags']}"
        )
        assert boosted[0]["soar_boost"] >= 1.25, (
            f"Expected boost >= 1.25, got {boosted[0]['soar_boost']}"
        )


def test_type_match_boost_not_applied_when_types_differ(tmp_path):
    """Query classifies to 'decision', drawer room='preference' → rule does not fire."""
    from cognitive_castle import soar_bridge

    hits = [
        {
            "id": "a",
            "score": 1.0,
            "wing": "x",
            "room": "preference",  # ← different memory_type
            "source_file": "f",
            "entity_match": False,
            "created_at": "2020-01-01T00:00:00Z",
        }
    ]
    cfg = _mock_cfg(rules_path=_RULES)

    boosted = soar_bridge.apply_soar_boosts(hits, cfg, query="what did we decide about X")

    if soar_bridge._load_sml() is not None:
        assert "type-match" not in boosted[0]["soar_tags"], (
            "Rule should not fire when query-type != drawer-type"
        )


def test_normalize_room_to_memory_type_handles_plurals():
    """Plural rooms from convo_miner alias to singular memory_types.

    convo_miner.TOPIC_KEYWORDS emits "decisions"/"problems" (plural), while
    SOAR's type-match rule schema and query_intent.MEMORY_TYPES use singular.
    The aliasing layer normalizes plurals so type-match fires regardless of
    which miner produced the drawer.
    """
    from cognitive_castle import soar_bridge

    # Plurals from convo_miner
    assert soar_bridge._normalize_room_to_memory_type("decisions") == "decision"
    assert soar_bridge._normalize_room_to_memory_type("problems") == "problem"

    # Singulars from general_extractor pass through (identity)
    assert soar_bridge._normalize_room_to_memory_type("decision") == "decision"
    assert soar_bridge._normalize_room_to_memory_type("preference") == "preference"
    assert soar_bridge._normalize_room_to_memory_type("milestone") == "milestone"
    assert soar_bridge._normalize_room_to_memory_type("problem") == "problem"
    assert soar_bridge._normalize_room_to_memory_type("emotional") == "emotional"

    # Non-memory-type rooms (technical/planning/architecture/general/diary)
    # return None — rule must not fire on them
    assert soar_bridge._normalize_room_to_memory_type("technical") is None
    assert soar_bridge._normalize_room_to_memory_type("planning") is None
    assert soar_bridge._normalize_room_to_memory_type("architecture") is None
    assert soar_bridge._normalize_room_to_memory_type("general") is None
    assert soar_bridge._normalize_room_to_memory_type("") is None


@pytest.mark.soar
@_requires_sml
def test_type_match_fires_on_plural_room_from_convo_miner(tmp_path):
    """Drawer room='decisions' (plural, from convo_miner) → type-match fires.

    Regression for the bug where soar_bridge checked `room in MEMORY_TYPES`
    directly. MEMORY_TYPES is singular ({decision, preference, ...}) but the
    bulk of Castle palaces have rooms like "decisions" from convo_miner's
    TOPIC_KEYWORDS plural scheme. Without aliasing, type-match never fired
    on real convo-mined palaces.
    """
    from cognitive_castle import soar_bridge

    hits = [
        {
            "id": "a",
            "score": 1.0,
            "wing": "x",
            "room": "decisions",  # ← plural from convo_miner
            "source_file": "f",
            "entity_match": False,
            "created_at": "2020-01-01T00:00:00Z",  # old — isolates type-match
        }
    ]
    cfg = _mock_cfg(rules_path=_RULES)

    boosted = soar_bridge.apply_soar_boosts(hits, cfg, query="what did we decide about X")

    assert "type-match" in boosted[0]["soar_tags"], (
        f"type-match must fire on plural room 'decisions'; "
        f"got soar_tags={boosted[0]['soar_tags']!r}"
    )
