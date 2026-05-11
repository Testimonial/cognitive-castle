"""Structural tests for .claude-plugin/ manifest files."""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / ".claude-plugin"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_plugin_json_valid_structure():
    data = _load(PLUGIN_DIR / "plugin.json")
    assert data["name"] == "castle"
    assert data["version"]  # non-empty string
    assert data["description"]
    assert "mcpServers" in data
    assert data["mcpServers"]["castle"]["command"] == "castle-mcp"
    # No chromadb / mempalace keyword leftovers
    keywords = data.get("keywords", [])
    assert "chromadb" not in keywords
    assert "mempalace" not in keywords


def test_plugin_json_no_mempalace_references():
    raw = (PLUGIN_DIR / "plugin.json").read_text()
    assert "mempalace" not in raw.lower()


def test_marketplace_json_valid_structure():
    data = _load(PLUGIN_DIR / "marketplace.json")
    assert data["name"] == "cognitive-castle"
    assert "owner" in data
    plugins = data["plugins"]
    assert len(plugins) >= 1
    castle = next((p for p in plugins if p["name"] == "castle"), None)
    assert castle is not None, "marketplace must list a plugin named 'castle'"
    assert castle["source"] == "./.claude-plugin"


def test_mcp_json_points_at_castle_mcp():
    data = _load(PLUGIN_DIR / ".mcp.json")
    assert "castle" in data
    assert data["castle"]["command"] == "castle-mcp"


def test_hooks_json_references_castle_wrappers():
    data = _load(PLUGIN_DIR / "hooks" / "hooks.json")
    stop_hooks = data["hooks"]["Stop"]
    precompact_hooks = data["hooks"]["PreCompact"]
    stop_cmd = stop_hooks[0]["hooks"][0]["command"]
    precompact_cmd = precompact_hooks[0]["hooks"][0]["command"]
    assert "castle-stop-hook.sh" in stop_cmd
    assert "castle-precompact-hook.sh" in precompact_cmd
    # No mempal references
    assert "mempal" not in stop_cmd
    assert "mempal" not in precompact_cmd


def test_version_sync_with_package():
    """plugin.json and marketplace.json should match cognitive_castle.version."""
    from cognitive_castle.version import __version__
    plugin_data = _load(PLUGIN_DIR / "plugin.json")
    marketplace_data = _load(PLUGIN_DIR / "marketplace.json")
    assert plugin_data["version"] == __version__, (
        f"plugin.json version {plugin_data['version']!r} != "
        f"cognitive_castle.version.__version__ {__version__!r}"
    )
    castle_plugin = next(p for p in marketplace_data["plugins"] if p["name"] == "castle")
    assert castle_plugin["version"] == __version__


def test_wrapper_scripts_exist_and_executable():
    """Renamed hook wrapper scripts are present and executable."""
    import os
    stop = PLUGIN_DIR / "hooks" / "castle-stop-hook.sh"
    precompact = PLUGIN_DIR / "hooks" / "castle-precompact-hook.sh"
    assert stop.exists()
    assert precompact.exists()
    assert os.access(stop, os.X_OK), f"{stop} must be executable"
    assert os.access(precompact, os.X_OK), f"{precompact} must be executable"


def test_legacy_wrapper_names_do_not_exist():
    """The pre-rename filenames are gone."""
    assert not (PLUGIN_DIR / "hooks" / "mempal-stop-hook.sh").exists()
    assert not (PLUGIN_DIR / "hooks" / "mempal-precompact-hook.sh").exists()
