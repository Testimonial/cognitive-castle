"""Offline regression and examination-contract tests; no model calls.

Scripted answers exercise the controller, not the accuracy of an LLM or Plato.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import sys

import pytest

# Adapted from Echelon a4286d83: packaged import and portable subprocess fixtures.
from cognitive_castle._vendor.sue import sue_dialectic as dial

v1 = dial.v1

SOURCE = (
    "Enabled means the switch is on.\n"
    "Every enabled deployment records an audit event.\n"
    "A deployment may set the switch on or off.\n"
    "Only administrators may change the switch.\n"
)
CLAIM = "Enabled means the switch is on."
PATHS = {
    "euthyphro": "DEFINE DISTINGUISH CAUSE_OR_CRITERION DIVIDE COUNTEREXAMPLE FOLLOW_CONSEQUENCE TEST_OPPOSITE",
    "meno": "DEFINE CAUSE_OR_CRITERION DISTINGUISH COUNTEREXAMPLE DIVIDE FOLLOW_CONSEQUENCE TEST_OPPOSITE",
    "parmenides": "DEFINE FOLLOW_CONSEQUENCE TEST_OPPOSITE DIVIDE DISTINGUISH CAUSE_OR_CRITERION COUNTEREXAMPLE",
    "cratylus": "DEFINE DISTINGUISH TEST_OPPOSITE CAUSE_OR_CRITERION DIVIDE COUNTEREXAMPLE FOLLOW_CONSEQUENCE",
    "theaetetus": "DEFINE CAUSE_OR_CRITERION FOLLOW_CONSEQUENCE DISTINGUISH COUNTEREXAMPLE DIVIDE TEST_OPPOSITE",
    "sophist": "DEFINE DIVIDE DISTINGUISH TEST_OPPOSITE CAUSE_OR_CRITERION COUNTEREXAMPLE FOLLOW_CONSEQUENCE",
    "gorgias": "DEFINE FOLLOW_CONSEQUENCE CAUSE_OR_CRITERION COUNTEREXAMPLE DIVIDE DISTINGUISH TEST_OPPOSITE",
    "republic": "DEFINE DISTINGUISH DIVIDE CAUSE_OR_CRITERION COUNTEREXAMPLE FOLLOW_CONSEQUENCE TEST_OPPOSITE",
    "philebus": "DEFINE CAUSE_OR_CRITERION DIVIDE TEST_OPPOSITE DISTINGUISH COUNTEREXAMPLE FOLLOW_CONSEQUENCE",
}
TYPES = dict(
    DEFINE="definition",
    DISTINGUISH="distinction",
    CAUSE_OR_CRITERION="criterion",
    DIVIDE="case-split",
    COUNTEREXAMPLE="example",
    FOLLOW_CONSEQUENCE="consequence",
    TEST_OPPOSITE="consequence",
    REVISE="revision",
)
ANSWERS = {
    "DEFINE": "Enabled is defined by the on position, not by an example deployment.",
    "DISTINGUISH": "On describes a switch state; enabled names deployments in that state.",
    "CAUSE_OR_CRITERION": "Inspecting the switch position recognizes an enabled deployment.",
    "DIVIDE": "The stated on/off domain has two cases; only on satisfies the definition.",
    "COUNTEREXAMPLE": "The examined off case is not enabled. No counterexample was found within these two cases.",
    "FOLLOW_CONSEQUENCE": "For an on deployment, enabled follows from line 1, so line 2 requires an audit event.",
    "TEST_OPPOSITE": "An enabled deployment with its switch off would violate the definition in line 1.",
    "REVISE": "The universal on reading was too broad. Enabled means on; off deployments remain permitted.",
}


def source_doc(tmp_path):
    p = tmp_path / "spec.md"
    p.write_bytes(SOURCE.encode("utf-8"))
    return v1.load_spec(p)


def payload(op, result=None, **changes):
    result = result or dial.SUCCESS_RESULT[op]
    verdict = {
        "UNKNOWN": "SILENT",
        "INCOMPLETE": "PARTIAL",
        "CONFLICT": "CONTRADICTED",
    }.get(result, "SUPPORTED")
    refs = [] if verdict == "SILENT" else [1, 2, 3]
    p = dict(
        answer=ANSWERS[op],
        verdict=verdict,
        answer_type=TYPES[op],
        evidence_lines=refs,
        claim=CLAIM if op in ("DEFINE", "REVISE") and verdict in ("SUPPORTED", "PARTIAL") else None,
        test_result=result,
        evidence=[{"line": n, "quote": SOURCE.splitlines()[n - 1]} for n in refs],
        premises=[
            {
                "statement": SOURCE.splitlines()[n - 1],
                "kind": "stated",
                "evidence_lines": [n],
            }
            for n in refs
        ],
        witness=None,
        open_questions=[],
        addresses=[],
        revision_reason=None,
    )
    if result in ("FOUND", "POSSIBLE", "CONFLICT"):
        p["witness"] = dict(
            situation="A deployment with its switch off.",
            reading_a="Every deployment must be on.",
            reading_b="This deployment may be off.",
            why_incompatible="Requiring on and permitting off conflict for the same deployment.",
            lines_a=[1],
            lines_b=[3],
        )
    p.update(changes)
    return p


def run_answers(monkeypatch, tmp_path, replies, lens="euthyphro", max_turns=7):
    spec = source_doc(tmp_path)
    queue = iter(replies)
    prompts = []

    def fake(config, prompt, validator, **kwargs):
        prompts.append(prompt)
        p = next(queue)
        result = validator(p)
        assert not isinstance(result, v1.ParseFailure), result
        return result

    monkeypatch.setattr(v1, "execute_round", fake)
    turns, terminal, error = dial.run_dialogue(None, spec, tmp_path, lens, "enabled", max_turns)
    assert error is None
    return turns, terminal, prompts


@pytest.mark.parametrize("lens", PATHS)
def test_all_dimensions_are_required_for_current_claim(monkeypatch, tmp_path, lens):
    path = PATHS[lens].split()
    turns, terminal, _ = run_answers(monkeypatch, tmp_path, [payload(op) for op in path], lens)
    assert [t.operator for t in turns] == path
    assert terminal == "RESOLVED"
    profile = dial.depth_profile(turns, lens)
    assert profile["missing"] == []
    assert not profile["blocking"]
    assert profile["epistemic_status"] == "model_interpretation_requires_review"
    assert "score" not in profile
    assert turns[-1].stop_reason == "all_dimensions_examined_for_current_claim"


@pytest.mark.parametrize("lens", PATHS)
@pytest.mark.parametrize("operator", list(TYPES)[:-1])
def test_silence_never_resolves_any_dimension(monkeypatch, tmp_path, lens, operator):
    path = PATHS[lens].split()
    prefix = path[: path.index(operator)]
    turns, terminal, _ = run_answers(
        monkeypatch,
        tmp_path,
        [payload(op) for op in prefix] + [payload(operator, "UNKNOWN")],
        lens,
    )
    assert terminal in ("APORIA_UNDEFINED", "APORIA_UNDERDETERMINED")
    profile = dial.depth_profile(turns, lens)
    assert operator in profile["missing"]
    assert profile["open_issues"]


@pytest.mark.parametrize("lens", PATHS)
def test_supported_tolerated_opposite_cannot_resolve(monkeypatch, tmp_path, lens):
    path = PATHS[lens].split()
    before = path[: path.index("TEST_OPPOSITE")]
    replies = [payload(op) for op in before] + [payload("TEST_OPPOSITE", "POSSIBLE")]
    turns, terminal, _ = run_answers(monkeypatch, tmp_path, replies, lens)
    assert terminal == "APORIA_UNDERDETERMINED"
    assert turns[-1].verdict == "SUPPORTED"
    assert turns[-1].witness["lines_b"] == [3]


def test_negative_counterexample_answer_does_not_request_revision():
    step = dial.next_step(
        "euthyphro",
        "COUNTEREXAMPLE",
        "SUPPORTED",
        "example",
        0,
        "NOT_FOUND",
        ["DEFINE", "DISTINGUISH", "CAUSE_OR_CRITERION", "DIVIDE"],
    )
    assert step == "FOLLOW_CONSEQUENCE"
    assert (
        dial.next_step("euthyphro", "COUNTEREXAMPLE", "SUPPORTED", "example", 0, "FOUND")
        == "REVISE"
    )


def test_revision_budget_is_a_bound_not_a_contradiction():
    assert (
        dial.next_step("euthyphro", "COUNTEREXAMPLE", "SUPPORTED", "example", 1, "FOUND")
        == "BOUNDED_STOP"
    )


def test_revision_exhaustion_preserves_the_second_challenge(monkeypatch, tmp_path):
    path = PATHS["euthyphro"].split()
    replies = [payload(op) for op in path[:4]] + [
        payload("COUNTEREXAMPLE", "FOUND"),
        payload(
            "REVISE",
            claim="A narrower interpretation",
            addresses=[1, 2, 3, 4, 5],
            revision_reason="Account for the counterexample by narrowing the scope.",
        ),
    ]
    replies += [payload(op) for op in path[1:4]] + [payload("COUNTEREXAMPLE", "FOUND")]
    turns, terminal, _ = run_answers(monkeypatch, tmp_path, replies, max_turns=14)
    assert terminal == "BOUNDED_STOP"
    assert turns[-1].stop_reason == "revision_budget_exhausted"
    assert turns[-1].witness
    assert dial.depth_profile(turns, "euthyphro")["open_issues"]


def test_partial_definition_can_be_deepened_before_it_is_established(monkeypatch, tmp_path):
    replies = [
        payload("DEFINE", "INCOMPLETE", claim="A preliminary proposal"),
        payload("DISTINGUISH", addresses=[1]),
        payload("DEFINE"),
    ]
    turns, terminal, _ = run_answers(monkeypatch, tmp_path, replies, max_turns=3)
    assert terminal == "BOUNDED_STOP"
    assert turns[0].claim_after == "A preliminary proposal"
    assert turns[2].claim_after == CLAIM
    assert turns[2].claim_version == 2
    assert "DISTINGUISH" in dial.depth_profile(turns, "euthyphro")["missing"]


@pytest.mark.parametrize("op", list(TYPES))
def test_empty_answer_type_cannot_pass_an_examination(tmp_path, op):
    result = dial.validate_turn(payload(op, answer_type="none"), op, source_doc(tmp_path))
    assert isinstance(result, v1.ParseFailure)
    assert "substantive type" in result.reason


def test_examples_trigger_followup_not_definition_completion(monkeypatch, tmp_path):
    turns, terminal, _ = run_answers(
        monkeypatch,
        tmp_path,
        [payload("DEFINE", answer_type="example"), payload("DISTINGUISH")],
        max_turns=2,
    )
    assert [t.operator for t in turns] == ["DEFINE", "DISTINGUISH"]
    assert terminal == "BOUNDED_STOP"
    assert "DEFINE" in dial.depth_profile(turns, "euthyphro")["missing"]


@pytest.mark.parametrize("op", ["COUNTEREXAMPLE", "FOLLOW_CONSEQUENCE", "DISTINGUISH"])
def test_claim_drift_is_rejected(tmp_path, op):
    result = dial.validate_turn(payload(op, claim="Enabled means off."), op, source_doc(tmp_path))
    assert isinstance(result, v1.ParseFailure)
    assert "claim changes" in result.reason


def test_redefinition_cannot_bypass_revision(tmp_path):
    result = dial.validate_turn(
        payload("DEFINE", claim="Enabled means off."),
        "DEFINE",
        source_doc(tmp_path),
        current_claim=CLAIM,
    )
    assert isinstance(result, v1.ParseFailure)
    assert "REVISE" in result.reason


@pytest.mark.parametrize(
    "corruption",
    [
        "range",
        "boolean",
        "quote",
        "duplicate",
        "stated",
        "assumption",
        "no_premise",
        "result",
        "support",
        "unknown_field",
        "type",
        "forward_reference",
    ],
)
def test_malformed_or_unanchored_evidence_rejected(tmp_path, corruption):
    p = payload("DEFINE")
    if corruption == "range":
        p["evidence_lines"].append(99)
    if corruption == "boolean":
        p["evidence_lines"] = [True]
    if corruption == "quote":
        p["evidence"][0]["quote"] = "Enabled means off."
    if corruption == "duplicate":
        p["evidence"][1] = p["evidence"][0]
    if corruption == "stated":
        p["premises"][0]["statement"] = "There is an external API."
    if corruption == "assumption":
        p["premises"][0]["kind"] = "assumption"
    if corruption == "no_premise":
        p["premises"] = []
    if corruption == "result":
        p["test_result"] = "EXCLUDED"
    if corruption == "support":
        p["verdict"] = "SILENT"
    if corruption == "unknown_field":
        p["certainty"] = 1.0
    if corruption == "type":
        p["open_questions"] = "none"
    if corruption == "forward_reference":
        p["addresses"] = [2]
    assert isinstance(dial.validate_turn(p, "DEFINE", source_doc(tmp_path)), v1.ParseFailure)


@pytest.mark.parametrize(
    "corruption", ["missing", "one_side", "same_reading", "no_reason", "outside_source"]
)
def test_unsupported_contradiction_is_rejected(tmp_path, corruption):
    p = payload("FOLLOW_CONSEQUENCE", "CONFLICT")
    if corruption == "missing":
        p["witness"] = None
    if corruption == "one_side":
        p["witness"]["lines_b"] = []
    if corruption == "same_reading":
        p["witness"]["reading_b"] = p["witness"]["reading_a"]
    if corruption == "no_reason":
        p["witness"]["why_incompatible"] = ""
    if corruption == "outside_source":
        p["witness"]["lines_a"] = [99]
    assert isinstance(
        dial.validate_turn(p, "FOLLOW_CONSEQUENCE", source_doc(tmp_path)),
        v1.ParseFailure,
    )


def test_witness_is_a_candidate_not_certified_proof(monkeypatch, tmp_path):
    turns, terminal, _ = run_answers(
        monkeypatch,
        tmp_path,
        [payload("DEFINE"), payload("FOLLOW_CONSEQUENCE", "CONFLICT")],
        "parmenides",
    )
    assert terminal == "APORIA_CONTRADICTED"
    report = dial.render_report(
        source_doc(tmp_path),
        tmp_path / "spec.md",
        "parmenides",
        "enabled",
        "",
        turns,
        terminal,
        "2026-09-24",
    )
    assert "requires review" in report
    assert "Reading A" in report and "Reading B" in report


def test_revision_preserves_history_and_invalidates_previous_probes(monkeypatch, tmp_path):
    first = [payload(op) for op in PATHS["euthyphro"].split()[:4]]
    replies = first + [
        payload("COUNTEREXAMPLE", "FOUND"),
        payload(
            "REVISE",
            claim="An on switch is enabled; off is still permitted.",
            addresses=[1, 2, 3, 4, 5],
            revision_reason="Withdraw the universal-on assumption; preserve the on/off domain.",
        ),
        payload("DISTINGUISH"),
    ]
    turns, terminal, prompts = run_answers(monkeypatch, tmp_path, replies)
    assert terminal == "BOUNDED_STOP"
    assert turns[5].claim_version == 2
    assert turns[0].claim_after == CLAIM
    assert turns[5].claim_before == CLAIM
    profile = dial.depth_profile(turns, "euthyphro")
    assert profile["missing"] == [
        "CAUSE_OR_CRITERION",
        "DIVIDE",
        "COUNTEREXAMPLE",
        "FOLLOW_CONSEQUENCE",
        "TEST_OPPOSITE",
    ]
    assert profile["issues"][0]["status"] == "model_addressed"
    assert "universal-on assumption" in prompts[-1]
    assert '"claim_version": 1' in prompts[-1]
    assert '"claim_version": 2' in prompts[-1]


def test_revision_must_acknowledge_previous_commitments(monkeypatch, tmp_path):
    turns, _, _ = run_answers(monkeypatch, tmp_path, [payload("DEFINE")], max_turns=1)
    p = payload("REVISE", revision_reason="Changed my mind", addresses=[])
    result = dial.validate_turn(p, "REVISE", source_doc(tmp_path), turns=turns, current_claim=CLAIM)
    assert isinstance(result, v1.ParseFailure)
    assert "every turn" in result.reason


def test_questions_and_assumptions_cannot_disappear(monkeypatch, tmp_path):
    p = payload("DEFINE", open_questions=["Does the audit include offline deployments?"])
    p["premises"].append(
        {
            "statement": "All deployments are online.",
            "kind": "assumption",
            "evidence_lines": [],
        }
    )
    turns, terminal, prompts = run_answers(
        monkeypatch, tmp_path, [p, payload("DISTINGUISH")], max_turns=2
    )
    assert terminal == "BOUNDED_STOP"
    assert "offline deployments" in prompts[1] and "All deployments are online" in prompts[1]
    assert len(dial.depth_profile(turns, "euthyphro")["open_issues"][0]["questions"]) == 2


@pytest.mark.parametrize(
    "lens,phrase",
    [
        ("euthyphro", "symptom"),
        ("meno", "recognized"),
        ("parmenides", "related actors"),
        ("cratylus", "referents"),
        ("theaetetus", "repeat it"),
        ("sophist", "uncovered cases"),
        ("gorgias", "persuasive"),
        ("republic", "capability, permission and obligation"),
        ("philebus", "qualitative criterion can suffice"),
    ],
)
def test_lens_specific_method_reaches_actual_prompt(lens, phrase):
    q = dial.build_question("CAUSE_OR_CRITERION", "focus", "claim", "", lens)
    assert phrase in q
    assert "Plato" in dial.LENSES[lens]["reference"]
    assert dial.LENSES[lens]["source"].startswith("https://")


def _stub(tmp_path, responses):
    replay = tmp_path / "replay"
    replay.mkdir(exist_ok=True)
    for i, r in enumerate(responses):
        (replay / f"{i}.json").write_text(r if isinstance(r, str) else json.dumps(r))
    counter = replay / "count"
    counter.write_text("0")
    script = tmp_path / "stub.py"
    script.write_text(
        "import sys\nfrom pathlib import Path\nsys.stdin.read()\n"
        f"counter = Path({str(counter)!r})\n"
        "n = int(counter.read_text())\ncounter.write_text(str(n + 1))\n"
        f"print((Path({str(replay)!r}) / f'{{n}}.json').read_text())\n"
    )
    return script


def cli_run(tmp_path, replies, max_turns=7):
    spec = source_doc(tmp_path)
    stub = _stub(tmp_path, replies)
    rc = dial.main(
        [
            str(spec.path),
            "--seed",
            "enabled",
            "--model-cmd",
            "claude=" + shlex.join([sys.executable, str(stub)]),
            "--max-turns",
            str(max_turns),
        ]
    )
    trace = json.loads((tmp_path / dial.JSON_FILENAME).read_text())
    return rc, trace


def test_cli_snapshot_provenance_and_history_are_preserved(tmp_path):
    rc, trace = cli_run(tmp_path, [payload(op) for op in PATHS["euthyphro"].split()])
    assert rc == 0
    assert trace["schema_version"] == 2
    assert trace["spec_digest"] == hashlib.sha256(SOURCE.encode()).hexdigest()
    assert trace["max_provider_attempts"] == 14
    assert len(trace["calls"]) == 7
    evidence = tmp_path / v1.EVIDENCE_DIR_NAME / trace["run_id"]
    original = (evidence / dial.JSON_FILENAME).read_bytes()
    assert (evidence / "specification.txt").read_text() == SOURCE
    assert all((tmp_path / c["metadata_ref"]).exists() for c in trace["calls"])
    rc2, trace2 = cli_run(tmp_path, [payload("DEFINE", "UNKNOWN")])
    assert rc2 == 0 and trace["run_id"] != trace2["run_id"]
    assert (evidence / dial.JSON_FILENAME).read_bytes() == original
    assert (tmp_path / "spec.md").read_text() == SOURCE


def test_failed_round_preserves_partial_trace_and_both_attempts(tmp_path):
    rc, trace = cli_run(tmp_path, [payload("DEFINE"), "garbage", "garbage"])
    assert rc == 3
    assert trace["status"] == "failed" and trace["terminal_state"] is None
    assert trace["stop_reason"] == "model_output_failure"
    assert len(trace["turns"]) == 1 and len(trace["calls"]) == 3
    assert trace["calls"][-1]["validation_failure"]


def test_report_collision_including_symlink_is_rejected(tmp_path):
    p = tmp_path / "spec.md"
    p.write_text(SOURCE)
    try:
        (tmp_path / dial.REPORT_FILENAME).symlink_to(p)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this platform")
    assert dial.main([str(p), "--seed", "enabled"]) == 1
    assert p.read_text() == SOURCE


def test_codex_turns_use_schema_bearing_runner(monkeypatch, tmp_path):
    spec = source_doc(tmp_path)
    config, _ = dial.parse_args(
        [
            str(spec.path),
            "--seed",
            "enabled",
            "--model-cmd",
            "codex=codex",
            "--model",
            "gpt-5.6-luna",
            "--reasoning-effort",
            "low",
        ]
    )
    seen = []

    def fake(config, prompt, validator, **kwargs):
        seen.append((config, kwargs))
        return validator(payload("DEFINE", "UNKNOWN"))

    monkeypatch.setattr(v1, "execute_round", fake)
    dial.run_dialogue(config, spec, tmp_path, "euthyphro", "enabled", 7)
    assert seen[0][1]["output_schema"] == dial.build_output_schema("DEFINE")
    assert seen[0][0].model == "gpt-5.6-luna"


def test_schema_is_closed_and_json_serializable():
    for op in dial.OPERATORS:
        schema = dial.build_output_schema(op)
        assert set(schema["properties"]) == set(schema["required"])
        assert schema["additionalProperties"] is False
        json.dumps(schema)


def test_missing_seed_fails_without_calls(tmp_path):
    assert dial.main([str(source_doc(tmp_path).path)]) == 1
