"""Directory ingestion reports partial failures without losing successful work."""

from argparse import Namespace
from unittest.mock import MagicMock

import pytest

from cognitive_castle import cli, sweeper


def test_directory_sweep_continues_after_one_file_fails(tmp_path, monkeypatch, capsys):
    for name in ("a.jsonl", "b.jsonl", "c.jsonl", "ignored.txt"):
        (tmp_path / name).write_text("")

    def ingest(path, palace, source_label):
        assert palace == "palace"
        assert source_label == path
        if path.endswith("b.jsonl"):
            raise OSError("unreadable transcript")
        return {"drawers_added": 2, "drawers_already_present": 1, "drawers_skipped": 3}

    monkeypatch.setattr(sweeper, "sweep", ingest)
    result = sweeper.sweep_directory(str(tmp_path), "palace")
    assert result["files_attempted"] == 3
    assert result["files_succeeded"] == 2
    assert result["drawers_added"] == 4
    assert result["drawers_already_present"] == 2
    assert result["drawers_skipped"] == 6
    assert result["failures"] == [
        {"file": str(tmp_path / "b.jsonl"), "error": "unreadable transcript"}
    ]
    assert len(result["per_file"]) == 2
    assert "unreadable transcript" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["file", "directory", "partial", "missing"])
def test_sweep_cli_exit_status_reflects_ingest_result(mode, tmp_path, monkeypatch, capsys):
    result = {
        "drawers_added": 2,
        "drawers_already_present": 1,
        "drawers_skipped": 3,
        "files_attempted": 2,
        "files_succeeded": 1 if mode == "partial" else 2,
        "failures": [{"error": "bad file"}] if mode == "partial" else [],
    }
    single = MagicMock(return_value=result)
    directory = MagicMock(return_value=result)
    monkeypatch.setattr(sweeper, "sweep", single)
    monkeypatch.setattr(sweeper, "sweep_directory", directory)
    target = tmp_path / "target"
    if mode == "file":
        target.write_text("")
    elif mode != "missing":
        target.mkdir()
    args = Namespace(palace="palace", target=str(target))
    if mode in ("partial", "missing"):
        with pytest.raises(SystemExit) as exc:
            cli.cmd_sweep(args)
        assert exc.value.code == (2 if mode == "partial" else 1)
        assert ("failed to sweep" if mode == "partial" else "Not a file") in capsys.readouterr().err
    else:
        cli.cmd_sweep(args)
        assert "+2 new, 1 already present, 3 skipped" in capsys.readouterr().out
    if mode == "file":
        single.assert_called_once_with(str(target), "palace")
        directory.assert_not_called()
    elif mode != "missing":
        directory.assert_called_once_with(str(target), "palace")
        single.assert_not_called()
    else:
        directory.assert_not_called()
        single.assert_not_called()
