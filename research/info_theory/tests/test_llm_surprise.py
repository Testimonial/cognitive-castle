from unittest.mock import MagicMock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from pipeline.llm_surprise import (
    SYSTEM_PROMPT,
    build_prompt,
    llm_surprise_one,
    parse_response,
)


def test_build_prompt_includes_priors_and_target():
    priors = [{"text": "prior one"}, {"text": "prior two"}]
    target = {"text": "the target drawer"}
    user_prompt = build_prompt(priors, target)
    assert "prior one" in user_prompt
    assert "prior two" in user_prompt
    assert "the target drawer" in user_prompt
    assert "1-10" in user_prompt or "1–10" in user_prompt


def test_parse_response_valid_json():
    raw = '{"score": 7, "reasoning": "somewhat predictable"}'
    parsed = parse_response(raw)
    assert parsed["score"] == 7
    assert parsed["reasoning"] == "somewhat predictable"


def test_parse_response_strips_markdown_fences():
    raw = '```json\n{"score": 3, "reasoning": "novel"}\n```'
    parsed = parse_response(raw)
    assert parsed["score"] == 3


def test_parse_response_strips_bare_fences_without_language_hint():
    # Extra coverage: LLMs sometimes emit plain ``` fences with no `json` hint.
    # The _FENCE regex claims to handle both; verify the bare form.
    raw = '```\n{"score": 5, "reasoning": "mid"}\n```'
    parsed = parse_response(raw)
    assert parsed["score"] == 5
    assert parsed["reasoning"] == "mid"


def test_parse_response_raises_on_malformed():
    with pytest.raises(ValueError):
        parse_response("not json at all")


def test_parse_response_raises_on_out_of_range_score():
    with pytest.raises(ValueError):
        parse_response('{"score": 11, "reasoning": "bad"}')
    with pytest.raises(ValueError):
        parse_response('{"score": 0, "reasoning": "bad"}')


def test_parse_response_raises_on_missing_score_field():
    # Extra coverage: the implementation explicitly checks for "score" absence
    # before range validation. Guard against a regression that would let a
    # KeyError leak out instead of the intended ValueError.
    with pytest.raises(ValueError):
        parse_response('{"reasoning": "no score here"}')


def test_llm_surprise_one_returns_full_record():
    priors = [{"text": "p"}]
    target = {"drawer_id": "d1", "text": "t"}
    fake_provider = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"score": 6, "reasoning": "ok"}'
    fake_response.raw = {"total_cost_usd": 0.05}
    fake_response.input_tokens = 1000
    fake_response.completion_tokens = 50
    fake_provider.classify.return_value = fake_response

    out = llm_surprise_one(priors, target, provider=fake_provider)
    assert out["drawer_id"] == "d1"
    assert out["llm_surprise"] == 4.0  # 10 - 6
    assert out["llm_surprise_reasoning_spotcheck"] == "ok"
    assert out["llm_surprise_cost_usd"] == 0.05
    assert out["llm_surprise_prompt_tokens"] == 1000
    assert out["llm_surprise_completion_tokens"] == 50

    # Verify the provider was called with the JSON-mode contract the plan specifies.
    fake_provider.classify.assert_called_once()
    call_args = fake_provider.classify.call_args
    assert call_args.args[0] == SYSTEM_PROMPT
    assert "t" in call_args.args[1]  # target text embedded in user prompt
    assert call_args.kwargs.get("json_mode") is True


def test_llm_surprise_one_tolerates_none_raw():
    # Extra coverage: the plan defensively guards `(resp.raw or {}).get(...)`.
    # Confirm that a provider returning raw=None yields cost_usd=None (not a crash).
    priors = [{"text": "p"}]
    target = {"drawer_id": "d2", "text": "t"}
    fake_provider = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"score": 10, "reasoning": "trivial"}'
    fake_response.raw = None
    fake_response.input_tokens = 500
    fake_response.completion_tokens = 20
    fake_provider.classify.return_value = fake_response

    out = llm_surprise_one(priors, target, provider=fake_provider)
    assert out["llm_surprise"] == 0.0  # 10 - 10
    assert out["llm_surprise_cost_usd"] is None


# --- Task 11: resumable batch + cost cap ---


def _fake_provider_with_cost(cost_per_call=0.05):
    p = MagicMock()

    def classify(system, user, json_mode=True):
        r = MagicMock()
        r.text = '{"score": 5, "reasoning": ""}'
        r.raw = {"total_cost_usd": cost_per_call}
        r.input_tokens = 1000
        r.completion_tokens = 50
        return r

    p.classify.side_effect = classify
    return p


def test_process_subsample_writes_partials(tmp_path):
    from pipeline.llm_surprise import process_subsample

    targets = [{"drawer_id": f"d{i}", "text": "t"} for i in range(3)]
    priors_lookup = {f"d{i}": [{"text": "p"}] for i in range(3)}
    partials_dir = tmp_path / "partials"
    process_subsample(
        targets,
        priors_lookup,
        provider=_fake_provider_with_cost(),
        partials_dir=partials_dir,
        max_cost=1.0,
    )
    files = list(partials_dir.glob("*.parquet"))
    assert len(files) == 3


def test_process_subsample_skips_done_drawers(tmp_path):
    from pipeline.llm_surprise import process_subsample

    partials_dir = tmp_path / "partials"
    partials_dir.mkdir()
    # Pre-create partial for d0 so it's skipped
    pq.write_table(
        pa.table({"drawer_id": ["d0"], "llm_surprise": [3.0]}),
        partials_dir / "d0.parquet",
    )
    provider = _fake_provider_with_cost()
    targets = [{"drawer_id": f"d{i}", "text": "t"} for i in range(3)]
    priors_lookup = {f"d{i}": [{"text": "p"}] for i in range(3)}
    process_subsample(
        targets,
        priors_lookup,
        provider=provider,
        partials_dir=partials_dir,
        max_cost=1.0,
    )
    # Only d1, d2 should be called
    assert provider.classify.call_count == 2


def test_process_subsample_aborts_on_cost_cap(tmp_path):
    from pipeline.llm_surprise import CostCapExceeded, process_subsample

    partials_dir = tmp_path / "partials"
    targets = [{"drawer_id": f"d{i}", "text": "t"} for i in range(10)]
    priors_lookup = {f"d{i}": [{"text": "p"}] for i in range(10)}
    # Each call costs $0.05; cap at $0.12 → aborts after 2 calls
    provider = _fake_provider_with_cost(cost_per_call=0.05)
    with pytest.raises(CostCapExceeded):
        process_subsample(
            targets,
            priors_lookup,
            provider=provider,
            partials_dir=partials_dir,
            max_cost=0.12,
        )
    # Verify at least one partial was written before the abort
    assert len(list(partials_dir.glob("*.parquet"))) >= 1


def test_merge_partials_roundtrip(tmp_path):
    # Extra coverage: verify merge_partials concatenates all partials in
    # sorted-drawer-id order, atomically (no lingering .tmp), and handles
    # the empty-dir case as a no-op. Merge is the natural companion to
    # process_subsample and would otherwise be untested.
    from pipeline.llm_surprise import merge_partials

    partials_dir = tmp_path / "partials"
    partials_dir.mkdir()
    # Write out-of-order to confirm merge sorts by filename
    for did, score in [("d2", 2.0), ("d0", 0.0), ("d1", 1.0)]:
        pq.write_table(
            pa.table({"drawer_id": [did], "llm_surprise": [score]}),
            partials_dir / f"{did}.parquet",
        )
    output = tmp_path / "merged.parquet"
    merge_partials(partials_dir, output)
    assert output.exists()
    # No leftover .tmp file after atomic rename
    assert not output.with_suffix(".tmp").exists()
    table = pq.read_table(output)
    assert table.column("drawer_id").to_pylist() == ["d0", "d1", "d2"]
    assert table.column("llm_surprise").to_pylist() == [0.0, 1.0, 2.0]


def test_merge_partials_empty_dir_is_noop(tmp_path):
    # Extra coverage: merge_partials on an empty dir must not create the
    # output file (guard against a regression that would emit an empty
    # Parquet with no schema).
    from pipeline.llm_surprise import merge_partials

    partials_dir = tmp_path / "partials"
    partials_dir.mkdir()
    output = tmp_path / "merged.parquet"
    merge_partials(partials_dir, output)
    assert not output.exists()


def test_process_subsample_skips_per_drawer_errors(tmp_path):
    # Robustness: one failed llm_surprise_one call must not abort the batch.
    # The failed drawer is logged + skipped; remaining drawers still process.
    from pipeline.llm_surprise import process_subsample

    partials_dir = tmp_path / "partials"
    targets = [{"drawer_id": f"d{i}", "text": "t"} for i in range(5)]
    priors_lookup = {f"d{i}": [{"text": "p"}] for i in range(5)}

    call_count = [0]

    def classify(system, user, json_mode=True):
        call_count[0] += 1
        r = MagicMock()
        if call_count[0] == 2:  # 2nd call raises
            raise RuntimeError("simulated timeout")
        r.text = '{"score": 5, "reasoning": ""}'
        r.raw = {"total_cost_usd": 0.01}
        r.input_tokens = 100
        r.completion_tokens = 50
        return r

    provider = MagicMock()
    provider.classify.side_effect = classify

    # Should not raise despite the error at call #2.
    process_subsample(
        targets, priors_lookup, provider=provider, partials_dir=partials_dir, max_cost=1.0
    )

    # 5 targets - 1 error = 4 successful partials
    assert len(list(partials_dir.glob("*.parquet"))) == 4
    # And provider.classify was invoked for all 5 (each drawer got a call attempt)
    assert provider.classify.call_count == 5
