"""Checkpoint acknowledgements and persistent hook controls through MCP."""

import json
from pathlib import Path


from cognitive_castle import mcp_server


def test_checkpoint_is_consumed_once(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert mcp_server.tool_memories_filed_away()["status"] == "quiet"
    ack = tmp_path / ".castle" / "hook_state" / "last_checkpoint"
    ack.parent.mkdir(parents=True)
    ack.write_text(json.dumps({"msgs": 4, "ts": "2026-09-24T12:00:00Z"}))
    report = mcp_server.tool_memories_filed_away()
    assert report["count"] == 4
    assert report["timestamp"] == "2026-09-24T12:00:00Z"
    assert not ack.exists()
    assert mcp_server.tool_memories_filed_away()["status"] == "quiet"


def test_invalid_checkpoint_does_not_claim_a_successful_save(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    ack = tmp_path / ".castle" / "hook_state" / "last_checkpoint"
    ack.parent.mkdir(parents=True)
    ack.write_text("invalid JSON")
    assert mcp_server.tool_memories_filed_away()["status"] == "error"
    assert not ack.exists()


def test_hook_settings_persist_without_changing_other_config(tmp_path, monkeypatch):
    from cognitive_castle import config

    real_config = config.CognitiveCastleConfig
    path = tmp_path / "config"
    cfg = real_config(config_dir=str(path))
    cfg._file_config["llm_model"] = "keep-model"
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text(json.dumps(cfg._file_config))
    monkeypatch.setattr(config, "CognitiveCastleConfig", lambda: real_config(config_dir=str(path)))
    report = mcp_server.tool_hook_settings(silent_save=False, desktop_toast=True)
    assert report["success"] is True
    assert report["settings"] == {"silent_save": False, "desktop_toast": True}
    assert mcp_server.tool_hook_settings()["settings"] == report["settings"]
    assert real_config(config_dir=str(path)).llm_model == "keep-model"


def test_hook_settings_report_config_read_error(monkeypatch):
    from cognitive_castle import config

    def unavailable():
        raise OSError("unreadable settings")

    monkeypatch.setattr(config, "CognitiveCastleConfig", unavailable)
    report = mcp_server.tool_hook_settings()
    assert report["success"] is False
    assert "unreadable" in report["error"]
