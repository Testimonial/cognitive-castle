"""Emit copy-paste-ready MCP-client config snippets for Cognitive Castle.

Powered by `castle share --with <client>`. Each generator returns a
single string (the snippet the user should paste into the target
client's config, or a shell command they should run). Optionally
writes the snippet directly to the target client's config file, but
never without opt-in — the default is print-and-exit so nothing on
disk changes without user consent.

Currently supported:

- ``codex``          → TOML block for ``~/.codex/config.toml``
- ``cursor``         → JSON block for ``.cursor/mcp.json``
- ``vscode``         → JSON block for ``.vscode/mcp.json``
- ``gemini-cli``     → JSON block for Gemini CLI's mcpServers config
- ``claude``         → ``claude mcp add`` shell command
- ``generic``        → Standard ``mcpServers`` JSON block for any MCP client
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Optional


SUPPORTED_CLIENTS = ("codex", "cursor", "vscode", "gemini-cli", "claude", "generic")


def _default_palace() -> Path:
    return Path.home() / ".castle" / "palace"


def _server_argv(palace: Optional[Path]) -> list[str]:
    """Argv list for the ``castle-mcp`` invocation, palace-pinned or not."""
    if palace is None:
        return ["castle-mcp"]
    return ["castle-mcp", "--palace", str(palace)]


def snippet_codex(palace: Optional[Path]) -> str:
    """TOML block for ``~/.codex/config.toml``."""
    argv = _server_argv(palace)
    if len(argv) == 1:
        return '[mcp_servers.castle]\ncommand = "castle-mcp"\n'
    args_toml = ", ".join(f'"{a}"' for a in argv[1:])
    return f'[mcp_servers.castle]\ncommand = "castle-mcp"\nargs = [{args_toml}]\n'


def snippet_json_mcp(palace: Optional[Path], indent: int = 2) -> str:
    """Standard ``{"mcpServers": {...}}`` JSON block used by Cursor, VS Code,
    Gemini CLI, and any generic MCP client."""
    argv = _server_argv(palace)
    server_block: dict = {"command": argv[0]}
    if len(argv) > 1:
        server_block["args"] = argv[1:]
    payload = {"mcpServers": {"castle": server_block}}
    return json.dumps(payload, indent=indent) + "\n"


def snippet_cursor(palace: Optional[Path]) -> str:
    return snippet_json_mcp(palace)


def snippet_vscode(palace: Optional[Path]) -> str:
    return snippet_json_mcp(palace)


def snippet_gemini_cli(palace: Optional[Path]) -> str:
    return snippet_json_mcp(palace)


def snippet_generic(palace: Optional[Path]) -> str:
    return snippet_json_mcp(palace)


def snippet_claude(palace: Optional[Path]) -> str:
    """Shell command to register Castle as an MCP server in Claude Code
    without the plugin. For the auto-registering plugin, use ``/plugin
    install castle@cognitive-castle`` in Claude Code instead."""
    argv = _server_argv(palace)
    quoted = " ".join(shlex.quote(a) for a in argv)
    return f"claude mcp add castle -- {quoted}\n"


_GENERATORS = {
    "codex": snippet_codex,
    "cursor": snippet_cursor,
    "vscode": snippet_vscode,
    "gemini-cli": snippet_gemini_cli,
    "claude": snippet_claude,
    "generic": snippet_generic,
}


def generate(client: str, palace: Optional[Path]) -> str:
    """Return the snippet string for ``client``."""
    if client not in _GENERATORS:
        raise ValueError(
            f"unknown client {client!r} — supported: {', '.join(sorted(SUPPORTED_CLIENTS))}"
        )
    return _GENERATORS[client](palace)


def default_config_path(client: str) -> Optional[Path]:
    """Where the snippet WOULD be written with ``--write``. ``None`` if the
    client's target is not a file we manage."""
    if client == "codex":
        return Path.home() / ".codex" / "config.toml"
    if client == "cursor":
        return Path.home() / ".cursor" / "mcp.json"
    if client == "vscode":
        return Path.home() / ".vscode" / "mcp.json"
    # gemini-cli / claude / generic have per-user paths we don't presume to know
    return None


def write_snippet(client: str, snippet: str, path: Optional[Path] = None) -> Optional[Path]:
    """Append (TOML) or merge (JSON) the snippet into the client's config file.

    Returns the path on a real write, ``None`` when the file already had a
    ``castle`` registration and this call was a no-op. Either way, no
    existing registration is overwritten — callers must edit manually to
    change one.
    """
    import sys

    if path is None:
        path = default_config_path(client)
    if path is None:
        raise ValueError(f"no default config path for {client!r}; pass an explicit --path")
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = path.read_text(encoding="utf-8") if path.exists() else ""

    if client == "codex":
        # TOML append; check for existing [mcp_servers.castle] block.
        if "[mcp_servers.castle]" in existing:
            print(
                f"[share] {path} already has [mcp_servers.castle] — no-op. "
                f"Edit manually if you need to change it.",
                file=sys.stderr,
            )
            return None
        separator = "" if existing.endswith("\n") or not existing else "\n"
        path.write_text(existing + separator + snippet, encoding="utf-8")
        return path

    if client in ("cursor", "vscode"):
        # JSON merge into existing mcpServers dict.
        if existing.strip():
            try:
                data = json.loads(existing)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"{path} is not valid JSON — cannot merge, fix or delete it first: {e}"
                ) from e
        else:
            data = {}
        data.setdefault("mcpServers", {})
        if "castle" in data["mcpServers"]:
            print(
                f"[share] {path} already has mcpServers.castle — no-op. "
                f"Edit manually if you need to change it.",
                file=sys.stderr,
            )
            return None
        # Snippet is the full {"mcpServers": {"castle": {...}}} envelope; unwrap.
        new = json.loads(snippet)
        data["mcpServers"]["castle"] = new["mcpServers"]["castle"]
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return path

    raise ValueError(f"--write not supported for {client!r} — copy the snippet manually")
