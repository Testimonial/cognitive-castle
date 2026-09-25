"""Castle -> frozen drawer sources -> real SUE engine -> retrievable findings.

Only the provider/worker launch is stubbed; no private palace or paid calls.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from cognitive_castle import sue, sue_worker
from cognitive_castle._vendor.sue import sue_dialectic as engine
from cognitive_castle.backends.base import GetResult
from cognitive_castle.llm_client import LLMError, LLMResponse


SOURCE = "Enabled means the switch is on.\r\nEvery enabled deployment records an audit event.\nŽádné zkrácení.  "


@pytest.fixture
def source_collection():
    # Reverse backend result order to catch accidental source/citation misassociation.
    return SimpleNamespace(
        get=lambda **kw: GetResult(
            ids=["older", "requirement"],
            documents=["Historical: off was required.\n", SOURCE],
            metadatas=[
                {"status": "superseded", "revision": "old"},
                {"wing": "demo", "revision": "v2"},
            ],
        )
    )


@pytest.fixture
def queued(monkeypatch, tmp_path, source_collection):
    launches = []

    def spawn(command, **kwargs):
        launches.append((command, kwargs))
        return SimpleNamespace(wait=lambda: sue_worker.run_review(command[-1]))

    monkeypatch.setattr(sue.subprocess, "Popen", spawn)

    def create(**kwargs):
        return sue.start_review(
            tmp_path,
            ["requirement", "older"],
            "Meaning of enabled",
            collection=source_collection,
            **kwargs,
        )

    create.launches = launches
    return create


def reply(op="DEFINE", result="ESTABLISHED", **changes):
    kinds = {
        "DEFINE": "definition",
        "DISTINGUISH": "distinction",
        "CAUSE_OR_CRITERION": "criterion",
        "DIVIDE": "case-split",
        "COUNTEREXAMPLE": "example",
        "FOLLOW_CONSEQUENCE": "consequence",
        "TEST_OPPOSITE": "consequence",
    }
    payload = {
        "answer": "The on state defines enabled; all other states are outside its scope.",
        "verdict": "SUPPORTED",
        "answer_type": kinds[op],
        "test_result": result,
        "claim": "Enabled means the switch is on." if op == "DEFINE" else None,
        "evidence_lines": [2],
        "evidence": [{"line": 2, "quote": "Enabled means the switch is on."}],
        "premises": [
            {
                "statement": "Enabled means the switch is on.",
                "kind": "stated",
                "evidence_lines": [2],
            }
        ],
        "witness": None,
        "open_questions": [],
        "addresses": [],
        "revision_reason": None,
    }
    payload.update(changes)
    return json.dumps(payload)


def install_provider(monkeypatch, responses):
    calls, configurations = [], []
    queue = iter(responses)

    def classify(system, user, json_mode):
        calls.append(user)
        value = next(queue)
        if isinstance(value, Exception):
            raise value
        return LLMResponse(
            text=value, model="requested-test", provider="ollama", raw={"model": "local-test"}
        )

    def provider(*args, **kwargs):
        configurations.append((args, kwargs))
        return SimpleNamespace(classify=classify)

    monkeypatch.setattr(sue_worker, "get_provider", provider)
    return calls, configurations


def test_verbatim_scope_and_provenance(queued, tmp_path):
    result = queued()
    manifest = result["manifest"]
    directory = Path(result["artifacts"])
    assert manifest["provider"] == "ollama" and not manifest["external_processing"]
    assert manifest["max_provider_attempts"] == 14
    assert [s["drawer_id"] for s in manifest["sources"]] == ["requirement", "older"]
    assert manifest["sources"][1]["metadata"]["status"] == "superseded"
    assert (directory / "source-001.txt").read_bytes() == SOURCE.encode()
    bundle = (directory / "specification.txt").read_bytes()
    for source in manifest["sources"]:
        raw = (directory / source["snapshot"]).read_bytes()
        assert bundle[source["byte_start"] : source["byte_end"]] == raw
        assert sue.digest(raw) == source["sha256"]
        assert (
            bundle.decode().splitlines()[source["line_start"] - 1] == raw.decode().splitlines()[0]
        )
    assert sue.digest(bundle) == manifest["spec_sha256"]
    assert SOURCE not in str(queued.launches[0][0])
    assert queued.launches[0][1]["start_new_session"] is True
    assert sue.review_status(tmp_path)["runs"][0]["run_id"] == result["run_id"]
    assert len(sue.review_status(tmp_path)["lenses"]) == 9
    if os.name == "posix":
        assert directory.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("lens", list(sue.LENSES))
def test_all_lenses_reach_real_engine_and_store_dialogue(monkeypatch, queued, tmp_path, lens):
    replies = [reply(op, engine.SUCCESS_RESULT[op]) for op in sue.LENSES[lens]["path"]]
    calls, configs = install_provider(monkeypatch, replies)
    # Ambient Codex markers/provider config cannot opt a local run into an external call.
    monkeypatch.setenv("ECHELON_LLM", "codex")
    monkeypatch.setenv("CASTLE_LLM_ENDPOINT", "https://example.invalid")
    result = queued(lens=lens, wait=True)
    assert result["status"] == "completed", result
    assert result["terminal_state"] == "RESOLVED"
    trace = result["trace"]
    assert len(calls) == 7
    for op, prompt in zip(sue.LENSES[lens]["path"], calls):
        assert f"Current examination operator: {op}." in prompt
        if op != "DEFINE":
            assert "claim=null and revision_reason=null" in prompt
    assert [t["operator"] for t in trace["turns"]] == list(sue.LENSES[lens]["path"])
    assert trace["depth_profile"]["epistemic_status"] == "model_interpretation_requires_review"
    assert trace["depth_profile"]["missing"] == []
    assert trace["source_links"][0]["drawer_id"] == "requirement"
    assert trace["source_links"][0]["drawer_line"] == 1
    assert "Historical: off was required." in calls[0]
    assert "superseded" in calls[0]
    assert "Castle sources (frozen revisions)" in result["report"]
    assert configs[0][1]["endpoint"] == "http://127.0.0.1:11434"
    assert trace["calls"][0]["provider"] == "ollama"
    assert trace["calls"][0]["reported_model"] == "local-test"
    evidence = Path(result["artifacts"]) / trace["calls"][0]["final_output_ref"]
    assert evidence.read_text() == replies[0]
    assert sue.review_status(tmp_path, result["run_id"])["trace"] == trace
    # Completed runs cannot be replayed or overwritten.
    assert sue_worker.run_review(Path(result["artifacts"])) == 1
    assert len(calls) == 7


def test_invalid_citations_fail_with_partial_trace(monkeypatch, queued):
    calls, _ = install_provider(
        monkeypatch,
        [reply(), reply("DISTINGUISH", evidence=[{"line": 2, "quote": "invented"}]), "not json"],
    )
    result = queued(wait=True)
    assert result["status"] == "failed"
    assert len(result["trace"]["turns"]) == 1
    assert result["trace"]["terminal_state"] is None
    assert len(calls) == 3
    assert result["trace"]["calls"][1]["validation_failure"]
    assert len(list((Path(result["artifacts"]) / "calls").glob("*.evidence.json"))) == 3


def test_local_failure_has_no_external_fallback(monkeypatch, queued):
    calls, _ = install_provider(monkeypatch, [LLMError("unavailable"), LLMError("unavailable")])
    monkeypatch.setattr(
        engine.v1, "run_model_call", lambda *a, **kw: pytest.fail("external fallback")
    )
    result = queued(wait=True)
    assert result["status"] == "failed"
    assert len(calls) == 2
    assert result["trace"]["turns"] == []


def test_explicit_codex_uses_hardened_schema_and_light_model(monkeypatch, queued):
    calls = []

    def run(config, prompt, schema):
        calls.append((config, prompt, schema))
        return engine.v1.CallOutcome("ok", reply(), "", 0.01)

    monkeypatch.setattr(engine.v1, "run_model_call", run)
    result = queued(provider="codex", max_turns=1, wait=True)
    assert result["manifest"]["external_processing"] is True
    config, _, schema = calls[0]
    assert (config.model_protocol, config.model_command, config.model, config.reasoning_effort) == (
        "codex-stdin",
        "codex",
        "gpt-5.6-luna",
        "low",
    )
    assert schema["type"] == "object"
    assert result["terminal_state"] == "BOUNDED_STOP"
    assert result["trace"]["provider"] == "codex"


@pytest.mark.parametrize("target", ["specification.txt", "source-001.txt"])
def test_tampering_stops_before_model(monkeypatch, queued, tmp_path, target):
    result = queued()
    (Path(result["artifacts"]) / target).write_text("changed")
    monkeypatch.setattr(sue_worker, "_examine", lambda *a: pytest.fail("model reached"))
    assert sue_worker.run_review(result["artifacts"]) == 1
    result = sue.review_status(tmp_path, result["run_id"])
    assert result["status"] == "failed"
    assert "hash mismatch" in result["error"]


@pytest.mark.parametrize(
    "changes",
    [
        {"drawer_ids": []},
        {"drawer_ids": "one"},
        {"drawer_ids": [False]},
        {"drawer_ids": ["one", "one"]},
        {"drawer_ids": ["x"] * 21},
        {"decision": " "},
        {"decision": None},
        {"model": ""},
        {"lens": "unknown"},
        {"lens": []},
        {"provider": "claude"},
        {"max_turns": True},
        {"max_turns": 15},
        {"max_turns": 0},
        {"timeout": 0},
        {"timeout": 301},
    ],
)
def test_invalid_request_creates_nothing(tmp_path, changes):
    args = {"drawer_ids": ["one"], "decision": "meaning"}
    args.update(changes)
    with pytest.raises(ValueError):
        sue.start_review(tmp_path, **args)
    assert not (tmp_path / ".sue").exists()


@pytest.mark.parametrize("text", ["", " ", "x" * 100_001])
def test_invalid_source_prevents_snapshot(tmp_path, text):
    col = SimpleNamespace(get=lambda **kw: GetResult(["one"], [text], [{}]))
    with pytest.raises(ValueError):
        sue.start_review(tmp_path, ["one"], "meaning", collection=col)
    assert not (tmp_path / ".sue").exists()


def test_missing_drawer_does_not_create_palace(tmp_path, source_collection):
    with pytest.raises(ValueError, match="Unknown drawer"):
        sue.start_review(tmp_path, ["missing"], "meaning", collection=source_collection)
    with pytest.raises(FileNotFoundError):
        sue.start_review(tmp_path / "absent", ["missing"], "meaning")
    assert not (tmp_path / "absent").exists()


def test_failed_spawn_is_visible(monkeypatch, queued, tmp_path):
    def fail(*a, **kw):
        raise OSError("launch denied")

    monkeypatch.setattr(sue.subprocess, "Popen", fail)
    result = queued()
    assert result["status"] == "failed"
    assert "launch denied" in result["error"]


def test_interrupted_worker_is_visible(monkeypatch, queued, tmp_path):
    result = queued()
    monkeypatch.setattr(sue.time, "time", lambda: result["manifest"]["created_at"] + 10_000)
    assert sue.review_status(tmp_path, result["run_id"])["status"] == "interrupted"


def test_dead_worker_is_visible(monkeypatch, queued, tmp_path):
    result = queued()
    directory = Path(result["artifacts"])
    sue.write_json(
        directory / "state.json",
        {"status": "running", "pid": 100000, "updated_at": result["manifest"]["created_at"]},
    )

    def dead(*a):
        raise ProcessLookupError()

    monkeypatch.setattr(sue.os, "kill", dead)
    if os.name == "posix":
        assert sue.review_status(tmp_path, result["run_id"])["status"] == "interrupted"


def test_paths_cannot_escape_palace(tmp_path):
    for value in ("../../elsewhere", "", "ab" * 17, None):
        with pytest.raises(ValueError):
            sue.review_dir(tmp_path, value)


def test_mcp_palace_roundtrip(monkeypatch, collection, palace_path, config):
    from cognitive_castle import mcp_server as mcp

    collection.add(
        ids=["requirement"],
        documents=[SOURCE],
        metadatas=[{"wing": "sue-demo", "room": "requirements"}],
    )
    before = collection.get(ids=["requirement"])
    monkeypatch.setattr(mcp, "_config", config)
    queued_paths = []
    monkeypatch.setattr(sue.subprocess, "Popen", lambda argv, **kw: queued_paths.append(argv[-1]))
    install_provider(monkeypatch, [reply()])
    response = mcp.handle_request(
        {
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "castle_sue_review",
                "arguments": {
                    "drawer_ids": ["requirement"],
                    "decision": "Meaning of enabled",
                    "max_turns": 1,
                },
            },
        }
    )
    result = json.loads(response["result"]["content"][0]["text"])
    assert result["status"] == "queued"
    assert sue_worker.run_review(queued_paths[0]) == 0
    reviewed = mcp.tool_sue_status(result["run_id"])
    assert reviewed["status"] == "completed"
    assert reviewed["trace"]["source_links"][0]["drawer_id"] == "requirement"
    after = collection.get(ids=["requirement"])
    assert before.documents == after.documents
    assert before.metadatas == after.metadatas
    assert collection.count() == 1  # model interpretations never masquerade as original memories
    assert mcp.tool_sue_status()["runs"][0]["run_id"] == result["run_id"]
    assert "error" in mcp.tool_sue_review(["missing"], "meaning")
    assert "error" in mcp.tool_sue_status("../../escape")
    monkeypatch.setattr(mcp, "_get_collection", lambda: None)
    assert "error" in mcp.tool_sue_review(["missing"], "meaning")


def test_cli_dispatch(monkeypatch, tmp_path, capsys):
    from cognitive_castle import cli

    monkeypatch.setattr("sys.argv", ["castle", "--palace", str(tmp_path), "sue", "status"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["runs"] == []
    monkeypatch.setattr(
        "sys.argv",
        [
            "castle",
            "--palace",
            str(tmp_path),
            "sue",
            "review",
            "--drawer",
            "absent",
            "--decision",
            "meaning",
            "--wait",
        ],
    )
    with pytest.raises(SystemExit, match="1"):
        cli.main()
    assert "error" in capsys.readouterr().err


def test_pinned_upstream_is_unmodified():
    root = Path(sue.__file__).parent / "_vendor/sue"
    pin = json.loads((root / "UPSTREAM.json").read_text())
    for name, expected in pin["files_sha256"].items():
        assert sue.digest((root / name).read_bytes()) == expected


def test_revision_prompt_keeps_revision_fields_available():
    prompt = sue_worker._turn_prompt(lambda *args: "upstream text", engine.SUCCESS_RESULT)(
        None, "REVISE", "revise"
    )
    assert "answer_type=revision" in prompt
    assert "claim=null" not in prompt
    assert "upstream text" in prompt
