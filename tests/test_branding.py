# tests/test_branding.py
"""Ensure all user-facing strings say 'Cognitive Castle', never 'MemPalace'."""
import subprocess
import sys


def _run(args):
    return subprocess.run(
        [sys.executable, "-m", "cognitive_castle.cli"] + args,
        capture_output=True, text=True,
    )


def test_main_help_no_mempalace():
    r = _run(["--help"])
    combined = r.stdout + r.stderr
    assert "MemPalace" not in combined, f"Found 'MemPalace' in --help output:\n{combined}"
    assert "mempalace" not in combined, f"Found 'mempalace' in --help output:\n{combined}"


def test_mine_help_no_mempalace():
    r = _run(["mine", "--help"])
    combined = r.stdout + r.stderr
    assert "MemPalace" not in combined
    assert "mempalace" not in combined


def test_mcp_output_no_mempalace(tmp_path, monkeypatch):
    """cmd_mcp prints the setup command — must say 'castle-mcp', not 'mempalace-mcp'."""
    import argparse
    import io
    import contextlib
    from cognitive_castle.cli import cmd_mcp
    args = argparse.Namespace(palace=None)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_mcp(args)
    out = buf.getvalue()
    assert "mempalace" not in out.lower(), f"Found 'mempalace' in cmd_mcp output:\n{out}"
    assert "castle-mcp" in out, f"Expected 'castle-mcp' in cmd_mcp output:\n{out}"


def test_mine_banner_no_mempalace(tmp_path):
    """The mine banner must say 'Cognitive Castle Mine', not 'MemPalace Mine'."""
    import io
    import contextlib
    from cognitive_castle.miner import mine

    (tmp_path / "castle.yaml").write_text(
        "wing: testproj\nrooms:\n  - name: general\n    patterns: ['*']\n"
    )
    (tmp_path / "hello.txt").write_text("hello world")

    palace = tmp_path / "palace"
    palace.mkdir()

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mine(
            project_dir=str(tmp_path),
            palace_path=str(palace),
            dry_run=True,
        )
    out = buf.getvalue()
    assert "MemPalace" not in out, f"Found 'MemPalace' in mine output:\n{out}"
    assert "Cognitive Castle" in out, f"Expected 'Cognitive Castle' in mine output:\n{out}"
