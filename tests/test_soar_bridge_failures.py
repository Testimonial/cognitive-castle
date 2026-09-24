"""Exercise symbolic reranking failures without requiring a Soar installation."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cognitive_castle import soar_bridge as bridge


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    monkeypatch.setattr(bridge, "_WARNED", set())
    monkeypatch.setattr(bridge, "_PREV_TOP_WMES", {})


@pytest.mark.parametrize("failure", ["clear", "push", "run", "read"])
def test_engine_failure_keeps_all_hits_and_scores(failure, monkeypatch, capsys):
    agent = MagicMock()
    monkeypatch.setattr(bridge, "_load_sml", lambda: object())
    monkeypatch.setattr(bridge, "_get_agent", lambda *args: agent)
    monkeypatch.setattr(bridge, "MAX_WM_HITS", 1)
    push = MagicMock(return_value=({}, [object()]))
    read = MagicMock(return_value={})
    monkeypatch.setattr(bridge, "_push_working_memory", push)
    monkeypatch.setattr(bridge, "_read_boost_tags", read)
    operation = {"clear": agent.DestroyWME, "push": push, "run": agent.RunSelf, "read": read}[
        failure
    ]
    operation.side_effect = RuntimeError("engine failed")
    if failure == "clear":
        bridge._PREV_TOP_WMES["palace"] = [object()]
    hits = [{"id": "a", "score": 0.7}, {"id": "b", "score": 0.4}]
    result = bridge.apply_soar_boosts(
        hits, SimpleNamespace(palace_path="palace", soar_rules_path="rules")
    )
    assert [hit["id"] for hit in result] == ["a", "b"]
    assert [hit["score"] for hit in result] == [0.7, 0.4]
    assert all(hit["soar_tags"] == [] and hit["soar_boost"] == 1.0 for hit in result)
    assert "engine failed" in capsys.readouterr().err


def test_engine_output_tags_are_parsed_compounded_and_audited(monkeypatch, capsys):
    agent = MagicMock()
    agent.ExecuteCommandLine.return_value = """(I2 ^memory M1 ^memory M2)
(M1 ^id |project/room/source with spaces|
    ^boost-tag recency-boost ^boost-tag same-project ^boost-tag mystery)

(M2 ^id |other/room/file|)
"""
    monkeypatch.setattr(bridge, "_load_sml", lambda: object())
    monkeypatch.setattr(bridge, "_get_agent", lambda *args: agent)
    monkeypatch.setattr(bridge, "_push_working_memory", lambda *args, **kw: ({}, []))
    hits = [
        {"wing": "project", "room": "room", "source_file": "source with spaces", "score": 1.0},
        {"wing": "other", "room": "room", "source_file": "file", "score": 0.5},
    ]
    result = bridge.apply_soar_boosts(
        hits, SimpleNamespace(palace_path="palace", soar_rules_path="rules")
    )
    assert result[0]["score"] == pytest.approx(1.25 * 1.15)
    assert result[0]["score_pre_soar"] == 1.0
    assert result[0]["soar_tags"] == ["recency-boost", "same-project"]
    assert result[1]["score"] == 0.5
    assert result[1]["soar_tags"] == []
    assert "unknown boost-tag 'mystery'" in capsys.readouterr().err
