"""Unit tests for `cognitive_castle.share`."""

import json
import shlex
from pathlib import Path

import pytest

from cognitive_castle.share import (
    SUPPORTED_CLIENTS,
    default_config_path,
    generate,
    snippet_claude,
    snippet_codex,
    snippet_json_mcp,
    write_snippet,
)


# ── generators (pure, no I/O) ─────────────────────────────────────────


def test_snippet_codex_unpinned_is_bare():
    out = snippet_codex(palace=None)
    assert "[mcp_servers.castle]" in out
    assert 'command = "castle-mcp"' in out
    # No args line when unpinned
    assert "args" not in out


def test_snippet_codex_pinned_includes_args_toml_list():
    palace = Path("/tmp/palace")
    out = snippet_codex(palace=palace)
    assert f'args = ["--palace", {json.dumps(str(palace))}]' in out


@pytest.mark.parametrize("path", ["C:\\Users\\Alice\\palace", '/tmp/a"b', "/tmp/český palác"])
def test_snippet_codex_paths_round_trip_through_toml(path):
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    palace = Path(path)
    data = tomllib.loads(snippet_codex(palace))
    assert data["mcp_servers"]["castle"]["args"] == ["--palace", str(palace)]


def test_snippet_json_mcp_shape_unpinned():
    out = snippet_json_mcp(palace=None)
    data = json.loads(out)
    assert data == {"mcpServers": {"castle": {"command": "castle-mcp"}}}


def test_snippet_json_mcp_shape_pinned():
    out = snippet_json_mcp(palace=Path("/tmp/p"))
    data = json.loads(out)
    server = data["mcpServers"]["castle"]
    assert server["command"] == "castle-mcp"
    assert server["args"] == ["--palace", str(Path("/tmp/p"))]


def test_snippet_claude_unpinned():
    out = snippet_claude(palace=None)
    assert out.strip() == "claude mcp add castle -- castle-mcp"


def test_snippet_claude_pinned_quotes_path_with_spaces():
    out = snippet_claude(palace=Path("/tmp/with space/palace"))
    # shlex.quote wraps in single quotes when spaces are present
    assert shlex.split(out)[-3:] == ["castle-mcp", "--palace", str(Path("/tmp/with space/palace"))]


def test_generate_unknown_client_raises():
    with pytest.raises(ValueError, match="unknown client"):
        generate("emacs", palace=None)


def test_all_supported_clients_have_generators():
    for client in SUPPORTED_CLIENTS:
        # Should not raise
        out = generate(client, palace=None)
        assert isinstance(out, str)
        assert out  # non-empty


# ── default_config_path ───────────────────────────────────────────────


def test_default_config_path_known_clients():
    codex = default_config_path("codex")
    cursor = default_config_path("cursor")
    vscode = default_config_path("vscode")
    assert codex is not None and codex.name == "config.toml"
    assert codex.parent.name == ".codex"
    assert cursor is not None and cursor.name == "mcp.json"
    assert vscode is not None and vscode.name == "mcp.json"


def test_default_config_path_unmanaged_returns_none():
    assert default_config_path("claude") is None
    assert default_config_path("gemini-cli") is None
    assert default_config_path("generic") is None


# ── write_snippet (integration with tmp_path) ─────────────────────────


def test_write_snippet_codex_creates_file_and_returns_path(tmp_path):
    target = tmp_path / "codex" / "config.toml"
    snippet = snippet_codex(palace=None)
    written = write_snippet("codex", snippet, path=target)
    assert written == target
    assert target.exists()
    content = target.read_text()
    assert "[mcp_servers.castle]" in content


def test_write_snippet_codex_noop_when_already_registered(tmp_path, capsys):
    target = tmp_path / "config.toml"
    target.write_text('[mcp_servers.castle]\ncommand = "castle-mcp"\n')

    snippet = snippet_codex(palace=None)
    result = write_snippet("codex", snippet, path=target)

    assert result is None  # sentinel for "no-op"
    stderr = capsys.readouterr().err
    assert "already has" in stderr
    # File unchanged
    assert target.read_text() == '[mcp_servers.castle]\ncommand = "castle-mcp"\n'


def test_write_snippet_cursor_merges_into_existing_json(tmp_path):
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {"otherThing": {"command": "x"}}}))

    snippet = snippet_json_mcp(palace=None)
    written = write_snippet("cursor", snippet, path=target)

    assert written == target
    data = json.loads(target.read_text())
    # Both entries present
    assert "castle" in data["mcpServers"]
    assert "otherThing" in data["mcpServers"]


def test_write_snippet_cursor_noop_when_castle_already_present(tmp_path, capsys):
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {"castle": {"command": "pre-existing"}}}))
    snippet = snippet_json_mcp(palace=None)
    result = write_snippet("cursor", snippet, path=target)
    assert result is None
    assert "already has" in capsys.readouterr().err
    # Pre-existing config preserved
    data = json.loads(target.read_text())
    assert data["mcpServers"]["castle"]["command"] == "pre-existing"


def test_write_snippet_cursor_invalid_json_raises(tmp_path):
    target = tmp_path / "mcp.json"
    target.write_text("{not valid json")
    with pytest.raises(ValueError, match="not valid JSON"):
        write_snippet("cursor", snippet_json_mcp(palace=None), path=target)


def test_write_snippet_unmanaged_client_raises(tmp_path):
    with pytest.raises(ValueError, match="--write not supported"):
        write_snippet("claude", snippet_claude(palace=None), path=tmp_path / "wrong.txt")
