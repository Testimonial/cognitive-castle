from unittest.mock import patch

from cli import build_arg_parser, dispatch  # noqa: F401


def test_arg_parser_recognizes_subcommands():
    p = build_arg_parser()
    for sub in ["snapshot", "pilot", "run", "status", "figures", "cost-estimate"]:
        args = p.parse_args([sub])
        assert args.command == sub


def test_run_subcommand_accepts_stage_flag():
    p = build_arg_parser()
    args = p.parse_args(["run", "--stage", "embed"])
    assert args.stage == "embed"


def test_run_all_invokes_all_stages():
    with patch("cli.STAGES") as m:
        m.keys.return_value = ["s1", "s2"]
        m.__contains__.return_value = True
        with patch("cli._run_stage") as run_m:
            from cli import dispatch

            class A:
                command = "run"
                stage = None
                all = True
                force = False

            dispatch(A())
            assert run_m.call_count == 2


def test_status_reads_cache_state(tmp_path):
    """Smoke: status doesn't crash with an empty cache dir."""
    from cli import cmd_status

    cmd_status(cache_dir=tmp_path)


def test_cmd_pilot_gracefully_handles_missing_data(tmp_path, capsys, monkeypatch):
    """cmd_pilot must print + return (not raise) when LME data is absent."""
    import cli

    monkeypatch.setattr(cli, "CACHE_DIR_DEFAULT", tmp_path)
    cli.cmd_pilot()  # should not raise
    captured = capsys.readouterr()
    assert "Missing" in captured.out
