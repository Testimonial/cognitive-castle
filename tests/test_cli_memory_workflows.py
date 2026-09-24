"""Exercise user-facing memory diagnostics and safe index creation."""

import io
import json
from argparse import Namespace
from unittest.mock import MagicMock

import pytest

from cognitive_castle import cli
from cognitive_castle.info_score import InfoScoreResult, Neighbour
from cognitive_castle.prune_suggest import PruneCandidate, PruneSuggestion


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("with_neighbours", [False, True])
def test_info_score_reports_result(as_json, with_neighbours, monkeypatch, capsys):
    neighbours = [Neighbour("d1", "original text", 0.8, "project")] if with_neighbours else []
    result = InfoScoreResult(0.2, "medium", neighbours)
    score = MagicMock(return_value=result)
    monkeypatch.setattr("cognitive_castle.info_score.score_novelty", score)
    monkeypatch.setattr("sys.stdin", io.StringIO("new text"))
    cli.cmd_info_score(Namespace(text=None, palace="palace", top_k=3, wing="project", json=as_json))
    score.assert_called_once_with("new text", palace_path="palace", top_k=3, wing="project")
    out = capsys.readouterr().out
    if as_json:
        assert json.loads(out) == result.as_dict()
    else:
        assert "Novelty: 0.200" in out
        assert ("d1" if with_neighbours else "no prior drawers") in out


def test_info_score_rejects_empty_input_and_missing_palace(monkeypatch, capsys):
    args = Namespace(text="", palace="absent", top_k=3, wing=None, json=False)
    monkeypatch.setattr("sys.stdin", io.StringIO(" \n"))
    with pytest.raises(SystemExit) as exc:
        cli.cmd_info_score(args)
    assert exc.value.code == 2
    assert "no text" in capsys.readouterr().err
    args.text = "text"
    monkeypatch.setattr(
        "cognitive_castle.info_score.score_novelty",
        MagicMock(side_effect=FileNotFoundError("absent")),
    )
    with pytest.raises(SystemExit) as exc:
        cli.cmd_info_score(args)
    assert exc.value.code == 1


@pytest.mark.parametrize("as_json,count", [(False, 0), (False, 21), (True, 21)])
def test_prune_suggestion_is_read_only_and_json_is_complete(as_json, count, monkeypatch, capsys):
    candidates = [
        PruneCandidate(f"d{i}", "project", "room", "verbatim", 0.01, "other", 0.99)
        for i in range(count)
    ]
    result = PruneSuggestion(30, 0.1, candidates)
    monkeypatch.setattr("cognitive_castle.prune_suggest.suggest_candidates", lambda **kw: result)
    cli.cmd_prune_suggest(
        Namespace(palace="palace", sample=30, threshold=0.1, wing=None, seed=42, json=as_json)
    )
    out = capsys.readouterr().out
    if as_json:
        assert len(json.loads(out)["candidates"]) == count
    elif count:
        assert "read-only" in out
        assert "and 1 more" in out
    else:
        assert "no drawers fell below" in out


def test_prune_suggestion_missing_palace_is_nonzero(monkeypatch):
    monkeypatch.setattr(
        "cognitive_castle.prune_suggest.suggest_candidates",
        MagicMock(side_effect=FileNotFoundError("absent")),
    )
    with pytest.raises(SystemExit) as exc:
        cli.cmd_prune_suggest(
            Namespace(palace="absent", sample=1, threshold=0.1, wing=None, seed=42, json=True)
        )
    assert exc.value.code == 1


@pytest.mark.parametrize("dry_run", [False, True])
def test_compress_keeps_original_drawers_and_writes_only_index(
    dry_run, tmp_path, monkeypatch, capsys
):
    original = "Alice works on the project.\n  Keep this exact source.\n"
    drawers, closets = MagicMock(), MagicMock()
    drawers.get.return_value = {
        "ids": ["d1"],
        "documents": [original],
        "metadatas": [{"wing": "project", "room": "notes"}],
    }
    backend = MagicMock()
    backend.get_collection.side_effect = lambda path, name: (
        drawers if name == "castle_drawers" else closets
    )
    monkeypatch.setattr("cognitive_castle.backends.lancedb_backend.LanceDBBackend", lambda: backend)
    cli.cmd_compress(Namespace(palace=str(tmp_path), config=None, wing="project", dry_run=dry_run))
    drawers.upsert.assert_not_called()
    drawers.delete.assert_not_called()
    drawers.update.assert_not_called()
    assert drawers.get.return_value["documents"] == [original]
    if dry_run:
        closets.upsert.assert_not_called()
        assert "nothing stored" in capsys.readouterr().out
    else:
        assert closets.upsert.call_args.kwargs["ids"] == ["d1"]
        assert closets.upsert.call_args.kwargs["metadatas"][0]["wing"] == "project"


def test_share_codex_writes_config_and_preserves_existing_registration(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text('model = "example"\n')
    args = Namespace(with_client="codex", palace=None, write=True, path=str(path))
    cli.cmd_share(args)
    first = path.read_text()
    assert 'model = "example"' in first
    assert "[mcp_servers.castle]" in first
    cli.cmd_share(args)
    assert path.read_text() == first
    args.write = False
    cli.cmd_share(args)
    assert "Paste this" in capsys.readouterr().out
    args.with_client = None
    cli.cmd_share(args)
    assert "Supported clients" in capsys.readouterr().out


def test_share_reports_malformed_json_without_overwriting(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text("{invalid")
    before = path.read_bytes()
    with pytest.raises(SystemExit) as exc:
        cli.cmd_share(Namespace(with_client="cursor", palace=None, write=True, path=str(path)))
    assert exc.value.code == 2
    assert path.read_bytes() == before
