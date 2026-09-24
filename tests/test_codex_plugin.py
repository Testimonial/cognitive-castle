"""Codex packaging and hook boundary tests without real personal memories."""

import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from cognitive_castle.codex_hooks import handle_hook, session_wing
from cognitive_castle.convo_miner import scan_convos
from cognitive_castle.normalize import normalize

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_resolves_mcp_skills_and_background_hooks():
    manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
    assert manifest["name"] == "cognitive-castle"
    assert (ROOT / manifest["skills"] / "castle/SKILL.md").is_file()
    mcp = json.loads((ROOT / manifest["mcpServers"]).read_text())
    assert mcp["mcpServers"]["castle"]["command"] == "castle-mcp"
    hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]
    for event in ("Stop", "PreCompact"):
        handler = hooks[event][0]["hooks"][0]
        assert handler["async"] is True
        assert "--harness codex" in handler["command"]


def test_startup_returns_codex_context_without_loading_storage(monkeypatch):
    mine = Mock(side_effect=AssertionError("startup must not mine"))
    monkeypatch.setattr("cognitive_castle.convo_miner.mine_convos", mine)
    result = handle_hook("session-start", {"session_id": "test"})
    assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert result["hookSpecificOutput"]["additionalContext"]
    mine.assert_not_called()


@pytest.mark.parametrize("event", ["stop", "precompact"])
def test_capture_selects_only_current_transcript(tmp_path, monkeypatch, capsys, event):
    current = tmp_path / "current.jsonl"
    current.write_text("{}")
    (tmp_path / "unrelated.jsonl").write_text("{}")
    mine = Mock(side_effect=lambda **kwargs: print("mining progress"))
    monkeypatch.setattr("cognitive_castle.convo_miner.mine_convos", mine)
    result = handle_hook(event, {"transcript_path": str(current), "cwd": "/work/My Project"})
    assert result == {}
    args = mine.call_args.kwargs
    assert args["convo_dir"] == str(current)
    assert args["agent"] == "codex"
    assert args["wing"] == "codex_my_project"
    assert scan_convos(args["convo_dir"]) == [current]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "mining progress" in captured.err


@pytest.mark.parametrize("transcript", [None, "", "/not/a/real/transcript.jsonl"])
def test_missing_transcript_is_nonblocking(transcript):
    assert handle_hook("stop", {"transcript_path": transcript}) == {}


def test_codex_dispatch_reports_failure_without_blocking(monkeypatch, capsys):
    from cognitive_castle import hooks_cli

    monkeypatch.setattr("sys.stdin", io.StringIO('{"transcript_path":"test.jsonl"}'))
    monkeypatch.setattr(
        "cognitive_castle.codex_hooks.handle_hook", Mock(side_effect=OSError("disk full"))
    )
    output = Mock()
    monkeypatch.setattr(hooks_cli, "_output", output)
    hooks_cli.run_hook("stop", "codex")
    captured = capsys.readouterr()
    output.assert_called_once_with({})
    assert "disk full" in captured.err


def test_response_item_rollout_preserves_user_text_and_excludes_developer(tmp_path):
    path = tmp_path / "rollout.jsonl"
    text = "  Exact spelling\n    return 42\n"
    rows = [{"type": "session_meta", "payload": {"id": "test"}}]
    for role, body in [("developer", "PRIVATE INSTRUCTIONS"), ("user", text), ("assistant", "OK.")]:
        rows.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": role,
                    "content": [{"type": "input_text", "text": body}],
                },
            }
        )
    path.write_text("\n".join(json.dumps(row) for row in rows))
    result = normalize(str(path))
    assert text in result
    assert "PRIVATE INSTRUCTIONS" not in result
    assert result.count(text) == 1


def test_event_turns_take_precedence_over_duplicate_response_items(tmp_path):
    path = tmp_path / "rollout.jsonl"
    rows = [
        {"type": "session_meta", "payload": {}},
        {
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": [{"text": "duplicate"}]},
        },
        {"type": "event_msg", "payload": {"type": "user_message", "message": "original"}},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows))
    assert normalize(str(path)) == "> original\n"


def test_workspace_wing_is_valid():
    assert session_wing("") == "codex_sessions"
    assert session_wing("/work/a $(unsafe); name") == "codex_a_unsafe_name"
