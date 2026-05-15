# Search Mode Consolidation — Design Spec

**Status:** Approved (brainstorm complete, 2026-05-15)
**Type:** Breaking change (single PR, no deprecation window)
**Scope:** Castle search surface — CLI flags, MCP tool params, config properties, env vars
**Out of scope:** Stage 3/4/5/6 internals, pipeline ordering logic, ranking math

---

## 1. Goal

Replace the four-flag combinatorial search interface with a single `--mode {fast,standard,boosted,max}` enum. Same observable retrieval behavior; smaller surface to teach, test, and document.

### What sprawl looks like today

`castle search` has four orthogonal toggles plus a kill switch each:

| Surface | Flags / vars |
|---|---|
| CLI flags | `--llm-rerank`, `--soar-boost`, `--soar-first`, `--no-quality-rerank` |
| MCP booleans | `llm_rerank`, `soar_boost`, `soar_first`, `no_quality_rerank` |
| Kill-switch env vars | `CASTLE_SOAR_ENABLED`, `CASTLE_QUALITY_DISABLED` |
| Loud validation | `--soar-first` requires both companion flags; `sys.exit(2)` on missing |

That's `2^4 = 16` combinatorial surface for users to reason about, of which only 4 combinations are documented and tested as first-class. The rest are accidental.

### What the consolidated interface looks like

| Mode | Stages run | Latency tax | Use case |
|---|---|---:|---|
| `fast`       | 3            | ~0 ms          | Hook-driven background pulls; lowest latency |
| `standard`   | 3, 6         | ~760 ms        | Default-quality interactive search w/o LLM |
| `boosted`    | 3, 5, 6      | ~770 ms        | Add SOAR symbolic boost-tags (deterministic) |
| `max`        | 3, 4, 5, 6   | ~1.8–2.8 s     | Full pipeline incl. LLM judge (default) |

The default is `max`. Stage 4 already has graceful identity-order fallback on any LLM failure, so picking `max` cannot break searches — at worst it transparently degrades to `boosted`-equivalent and surfaces a JUDGE audit line.

### Migration map

| Old surface | New equivalent |
|---|---|
| `--llm-rerank`                | `--mode max` |
| `--soar-boost`                | `--mode boosted` |
| `--soar-first`                | (removed — fixed order judge → SOAR → quality in `max`) |
| `--no-quality-rerank`         | `--mode fast` |
| `CASTLE_SOAR_ENABLED=1`       | (no longer needed — `boosted` / `max` always include SOAR) |
| `CASTLE_QUALITY_DISABLED=1`   | `--mode fast` |
| MCP `llm_rerank: true`        | MCP `mode: "max"` |
| MCP `soar_boost: true`        | MCP `mode: "boosted"` |
| MCP `soar_first: true`        | (removed) |
| MCP `no_quality_rerank: true` | MCP `mode: "fast"` |

This PR **resolves the open P2 gap from PR #45** ("global quality-rerank disable path unenforced for direct search API calls"). The fix is by removal: `cfg.quality_disabled` ceases to exist; programmatic callers pass `mode=` and get exactly the stages they asked for.

---

## 2. Implementation surface

### Files modified

#### `cognitive_castle/cli.py`

**Prerequisite refactor** — extract argparse setup into module-level `build_parser()`:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(...)
    # ... all existing setup ...
    return parser

def main():
    parser = build_parser()
    args = parser.parse_args()
    # ... rest unchanged ...
```

Zero behavioral change; makes the parser testable. All new CLI tests depend on this.

**Search subparser changes:**

- Delete `--llm-rerank`, `--soar-boost`, `--soar-first`, `--no-quality-rerank`.
- Add `--mode`, `choices=["fast", "standard", "boosted", "max"]`, `default="max"`.
- Delete kill-switch validation block (~lines 607–613): the `sys.exit(2)` enforcing `--soar-first` companion-flag requirement is removed along with the flag.

**`cmd_init` changes:**

- Argparse `--llm-model` default: `"gemma3:4b"` → `"qwen3.5:latest"`.
- Body fallback `or "gemma3:4b"` → `or "qwen3.5:latest"`.

Rationale: `gemma3:4b` is not in the Ollama registry; the user's installed models include `qwen3.5:latest` but not `gemma3:4b`. The docstring at `config.py:476` already flagged this.

#### `cognitive_castle/mcp_server.py`

`tool_search` parameter changes:

- Delete: `llm_rerank: bool = False`, `soar_boost: bool = False`, `soar_first: bool = False`, `no_quality_rerank: bool = False`.
- Add: `mode: str = "max"`.
- Delete kill-switch validation block (~lines 406–416).
- Add 3-line mode-validation guard at the top of the function body:
  ```python
  if mode not in ("fast", "standard", "boosted", "max"):
      return {"error": f"invalid mode '{mode}'. Must be one of: fast, standard, boosted, max"}
  ```
- Validation lives in **the function body, not the JSON schema** — keeps the JSON schema generic and the error message specific to Castle.

#### `cognitive_castle/searcher.py`

Signature changes:

```python
def search_memories(query, palace_path, *, mode: str = "max", ...): ...
def search(query, *, mode: str = "max", ...): ...
def _new_pipeline_search(query, ..., mode: str = "max"): ...
```

`_apply_stages_4_and_5` → renamed `_apply_optional_stages`. Body becomes a mode-dispatched if/elif/else:

```python
def _apply_optional_stages(query, reranked, cfg, mode):
    if mode == "fast":
        return reranked
    if mode == "standard":
        return _stage_6_quality(query, reranked, cfg)
    if mode == "boosted":
        reranked = _stage_5_soar(query, reranked, cfg)
        return _stage_6_quality(query, reranked, cfg)
    if mode == "max":
        reranked = _stage_4_judge(query, reranked, cfg)
        reranked = _stage_5_soar(query, reranked, cfg)
        return _stage_6_quality(query, reranked, cfg)
    raise ValueError(f"invalid mode '{mode}'")
```

**`_stage_4_judge` audit-line surfacing** — wraps the LLM judge call and stashes a status dict on `reranked[0][1]`:

```python
def _stage_4_judge(query, reranked, cfg):
    if not reranked:
        return reranked
    started = time.time()
    try:
        top_n = cfg.llm_judge_top_n
        reordered = judge.judge(
            query,
            [r[1].get("text", "") for r in reranked[:top_n]],
            cfg,
        )
        elapsed = round(time.time() - started, 2)
        if reordered != list(range(len(reordered))):
            new_reranked = [reranked[i] for i in reordered] + reranked[top_n:]
            new_reranked[0][1]["judge_status"] = {
                "reordered": True,
                "n": top_n,
                "model": cfg.llm_model,
                "elapsed_s": elapsed,
            }
            return new_reranked
        return reranked
    except Exception as e:
        reranked[0][1]["judge_status"] = {"error": f"{type(e).__name__}: {e}"}
        return reranked
```

**`judge_status` schema:**
- Success (reordering happened): `{"reordered": bool, "n": int, "model": str, "elapsed_s": float}`
- Failure: `{"error": "<ExceptionClass>: <message>"}`
- No reordering OR empty hits: dict absent

**Audit-line printer output:**
- `JUDGE: reordered N hits (<model>, <elapsed>s)` — success path
- `JUDGE: FAILED (<error>) — identity-order fallback` — failure path
- No line printed if `judge_status` is absent.

`judge.judge()` itself: **no signature change**. The exception handling lives entirely in the searcher wrapper.

#### `cognitive_castle/config.py`

- Delete `cfg.soar_enabled` property (lines ~550–556).
- Delete `cfg.quality_disabled` property (added 1 day ago in PR #45 — net-zero churn).
- Change `cfg.llm_model` default at line ~476: `"gemma3:4b"` → `"qwen3.5:latest"`.

#### `cognitive_castle/soar_bridge.py`

Remove the `if not cfg.soar_enabled: return hits unchanged` early-return. The bridge now runs whenever `_stage_5_soar` is called (which mode-dispatch already gates).

#### `cognitive_castle/quality_rerank.py`

Docstring update only — remove references to `cfg.quality_disabled`.

#### `cognitive_castle/judge.py`

No code changes (error surfacing happens in the searcher wrapper).

#### `CLAUDE.md`

Replace the four-flag retrieval-pipeline diagram block with the mode table from Section 1.

---

## 3. Testing strategy

### Scope

The consolidation is a flag-shape refactor. The four pipeline stages (3 / 4 / 5 / 6) keep their existing logic and existing tests. What we test here is the new **dispatch surface** — that `--mode` correctly selects which stages run, that removed flags and env vars no longer have effect, that the JUDGE audit line surfaces success/failure correctly, and that programmatic callers behave identically to CLI/MCP callers.

### Test surface changes

| File | Delete | Update | Add |
|---|--:|--:|--:|
| `tests/test_pipeline_order.py`             | 2  | 12 | 2 |
| `tests/test_cli.py`                        | 6  | 8  | 4 |
| `tests/test_mcp_server.py`                 | 3  | 6  | 3 |
| `tests/test_config.py`                     | 6  | 0  | 1 |
| `tests/test_searcher.py`                   | 0  | 4  | 3 |
| `tests/test_quality_rerank.py`             | 1  | 2  | 0 |
| `tests/test_soar_bridge.py`                | 1  | 1  | 0 |
| `tests/test_judge.py`                      | 0  | 0  | 3 |
| **Totals**                                 | 19 | 33 | 16 |

### Prerequisite refactor

`cli.py:953-955` builds `argparse.ArgumentParser()` inside `main()`. Tests cannot reach it without running `main()` end-to-end. The plan therefore includes a single mechanical preceding task to extract `build_parser()` (see Section 2 — `cli.py`). All new CLI tests depend on this.

### New tests (16 total)

**1. Mode dispatch (parametrized, 4 rows)** — `tests/test_pipeline_order.py`

```python
@pytest.mark.parametrize(
    "mode,expect_judge,expect_soar,expect_quality",
    [
        ("fast",     False, False, False),
        ("standard", False, False, True),
        ("boosted",  False, True,  True),
        ("max",      True,  True,  True),
    ],
)
def test_apply_optional_stages_dispatches_by_mode(
    mode, expect_judge, expect_soar, expect_quality, _mock_cfg
):
    with (
        patch("cognitive_castle.searcher._stage_4_judge") as j,
        patch("cognitive_castle.searcher._stage_5_soar") as s,
        patch("cognitive_castle.searcher._stage_6_quality") as q,
    ):
        j.return_value = s.return_value = q.return_value = [("d1", {"text": "x"})]
        searcher._apply_optional_stages("q", [("d1", {"text": "x"})], _mock_cfg, mode)
    assert j.called is expect_judge
    assert s.called is expect_soar
    assert q.called is expect_quality
```

`_mock_cfg` is a fixture at the top of `test_pipeline_order.py` — a minimal `CognitiveCastleConfig` with `llm_model="qwen3.5:latest"`, `llm_judge_top_n=10`.

**2. Mode ordering in `max`** — `tests/test_pipeline_order.py`

```python
def test_max_mode_calls_stages_in_order_4_5_6(_mock_cfg):
    calls = []
    with (
        patch("cognitive_castle.searcher._stage_4_judge", side_effect=lambda *a: calls.append("4") or a[1]),
        patch("cognitive_castle.searcher._stage_5_soar",  side_effect=lambda *a: calls.append("5") or a[1]),
        patch("cognitive_castle.searcher._stage_6_quality", side_effect=lambda *a: calls.append("6") or a[1]),
    ):
        searcher._apply_optional_stages("q", [("d1", {"text": "x"})], _mock_cfg, "max")
    assert calls == ["4", "5", "6"]
```

Locks the fixed order (replaces the deleted `--soar-first` toggle test).

**3. Invalid mode rejection (parametrized)** — `tests/test_cli.py`

```python
@pytest.mark.parametrize("bad", ["full", "FAST", "", "judge"])
def test_search_rejects_invalid_mode(bad, capsys):
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["search", "q", "--mode", bad])
    err = capsys.readouterr().err
    assert "invalid choice" in err
```

**4. Removed-flag rejection (parametrized)** — `tests/test_cli.py`

```python
@pytest.mark.parametrize("flag", ["--llm-rerank", "--soar-boost", "--soar-first", "--no-quality-rerank"])
def test_removed_flags_rejected(flag, capsys):
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["search", "q", flag])
    assert "unrecognized arguments" in capsys.readouterr().err
```

**5. CLI default mode = max** — `tests/test_cli.py`

```python
def test_search_default_mode_is_max():
    parser = cli.build_parser()
    args = parser.parse_args(["search", "q"])
    assert args.mode == "max"
```

**6. `cmd_init` --llm-model default** — `tests/test_cli.py`

```python
def test_cmd_init_llm_model_default_is_qwen35():
    parser = cli.build_parser()
    args = parser.parse_args(["init", "/tmp/test_palace"])
    assert args.llm_model == "qwen3.5:latest"
```

Three-line regression test for the `gemma3:4b` → `qwen3.5:latest` swap.

**7. MCP mode validation (3 tests)** — `tests/test_mcp_server.py`

```python
def test_mcp_tool_search_default_mode_is_max():
    with patch("cognitive_castle.mcp_server.search_memories", return_value={"results": []}) as m:
        asyncio.run(mcp_server.tool_search({"query": "q", "palace": "/tmp/p"}))
    assert m.call_args.kwargs["mode"] == "max"

def test_mcp_tool_search_accepts_valid_modes():
    for m in ("fast", "standard", "boosted", "max"):
        with patch("cognitive_castle.mcp_server.search_memories", return_value={"results": []}):
            result = asyncio.run(mcp_server.tool_search({"query": "q", "palace": "/tmp/p", "mode": m}))
        assert "error" not in result

def test_mcp_tool_search_rejects_invalid_mode():
    result = asyncio.run(mcp_server.tool_search({"query": "q", "palace": "/tmp/p", "mode": "full"}))
    assert "error" in result
    assert "invalid mode" in result["error"].lower()
```

MCP validation lives in `tool_search` body (3-line guard), NOT in the JSON schema.

**8. Config: removed properties (parametrized)** — `tests/test_config.py`

```python
@pytest.mark.parametrize("attr", ["soar_enabled", "quality_disabled"])
def test_removed_config_properties_are_absent(attr):
    cfg = CognitiveCastleConfig(palace_path="/tmp/p")
    assert not hasattr(cfg, attr)
```

Six existing tests around these two properties are deleted.

**9. Programmatic `mode=` parity (3 tests)** — `tests/test_searcher.py`

```python
def _mock_recall_layer():
    """Helper: patches Stage 1-3 to return a fixed reranked list of 3 hits."""
    fake_hits = [(f"d{i}", {"text": f"t{i}", "score": 1.0 - i * 0.1}) for i in range(3)]
    return patch(
        "cognitive_castle.searcher._stage_3_rerank",
        return_value=fake_hits,
    )

def test_search_memories_default_mode_runs_all_stages(tmp_palace):
    """Programmatic callers get max by default — closes the PR #45 P2 gap."""
    with (
        _mock_recall_layer(),
        patch("cognitive_castle.searcher._stage_4_judge", side_effect=lambda q, r, c: r) as j,
        patch("cognitive_castle.searcher._stage_5_soar",  side_effect=lambda q, r, c: r) as s,
        patch("cognitive_castle.searcher._stage_6_quality", side_effect=lambda q, r, c: r) as q,
    ):
        searcher.search_memories(query="q", palace_path=str(tmp_palace))
    assert j.called and s.called and q.called

def test_search_memories_mode_fast_skips_all_optional_stages(tmp_palace):
    with (
        _mock_recall_layer(),
        patch("cognitive_castle.searcher._stage_4_judge") as j,
        patch("cognitive_castle.searcher._stage_5_soar")  as s,
        patch("cognitive_castle.searcher._stage_6_quality") as q,
    ):
        searcher.search_memories(query="q", palace_path=str(tmp_palace), mode="fast")
    assert not j.called and not s.called and not q.called

def test_search_memories_invalid_mode_raises(tmp_palace):
    with _mock_recall_layer():
        with pytest.raises(ValueError, match="invalid mode"):
            searcher.search_memories(query="q", palace_path=str(tmp_palace), mode="full")
```

`tmp_palace` is the existing fixture in `tests/conftest.py` that creates a minimal LanceDB-backed palace.

Test 9.1 explicitly closes the P2 review gap flagged on PR #45 — programmatic callers no longer execute Stage 6 silently.

**10. JUDGE audit line — happy + error path (2 tests)** — `tests/test_judge.py`

```python
def test_judge_status_on_successful_reorder(_mock_cfg):
    fake_reorder = [2, 0, 1]  # different from identity
    with patch("cognitive_castle.judge.judge", return_value=fake_reorder):
        reranked = [(f"d{i}", {"text": f"t{i}"}) for i in range(3)]
        out = searcher._stage_4_judge("q", reranked, _mock_cfg)
    status = out[0][1]["judge_status"]
    assert status["reordered"] is True
    assert status["n"] == 3
    assert status["model"] == _mock_cfg.llm_model
    assert isinstance(status["elapsed_s"], float)

def test_judge_status_on_failure_is_identity_fallback(_mock_cfg):
    with patch("cognitive_castle.judge.judge", side_effect=ConnectionError("ollama down")):
        reranked = [(f"d{i}", {"text": f"t{i}"}) for i in range(3)]
        out = searcher._stage_4_judge("q", reranked, _mock_cfg)
    assert out == reranked  # identity-order fallback
    assert out[0][1]["judge_status"] == {"error": "ConnectionError: ollama down"}
```

Edge case: empty `reranked` returns `[]` immediately; no audit line emitted; no test crash. Implicitly covered by the existing `test_searcher_handles_empty_hits` integration test.

**11. Slow smoke (LLM end-to-end)** — `tests/test_judge.py`, marked `@pytest.mark.slow`

```python
@pytest.mark.slow
def test_max_mode_end_to_end_with_real_judge(real_palace_fixture):
    """Reaches actual Ollama. Skipped in CI; run locally before PR merge."""
    if not _ollama_reachable():
        pytest.skip("Ollama not running")
    result = searcher.search_memories(
        query="What did we decide about retrieval weights?",
        palace_path=real_palace_fixture,
        mode="max",
    )
    assert "results" in result
    assert len(result["results"]) > 0
    status = result["results"][0].get("judge_status")
    assert status is None or "reordered" in status or "error" in status
```

Catches: Ollama URL changes, default-model-not-installed regressions, prompt template breakage. Excluded from CI; runs locally before PR merge.

### Coverage targets

- `searcher._apply_optional_stages` mode-dispatch: **100% branch coverage** (4 modes × parametrized test).
- `searcher._stage_4_judge`: **≥ 90% line coverage** (happy + error paths).
- `cli.build_parser()` search subparser block: **100% line coverage**.
- `mcp_server.tool_search` mode-validation block: **100% line coverage**.

### Risk register

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| 1 | `_apply_optional_stages` callers in `_new_pipeline_search` get out-of-sync signatures | Medium | Rename + signature change in a single commit; grep-verify all 3 callers compile before commit. |
| 2 | Slow smoke passes locally but Ollama default model differs in CI | Low | Marked `@pytest.mark.slow`, excluded from CI. Unit tests under #10 catch success/error shapes deterministically. |
| 3 | Programmatic callers in third-party plugins break on missing `mode=` kwarg | Very Low | `mode` defaults to `"max"` in `search_memories()` signature — no caller is required to pass it. |

### Non-goals

- Re-testing Stage 3/4/5/6 internals.
- Performance regression tests (mode latencies match Section 1 table by construction).
- Migration script for old saved CLI invocations (single-user system).

---

## 4. Acceptance criteria

- All 14 new tests pass.
- All 33 updated tests pass.
- All 19 deleted tests are gone (no zombies).
- `python -m pytest tests/ -v --ignore=tests/benchmarks` reports zero failures.
- `ruff check .` and `ruff format --check .` both clean.
- Slow smoke test passes locally against the user's running Ollama.
- `CLAUDE.md` retrieval-pipeline diagram reflects the mode table.
- PR merged via `gh pr merge --merge --delete-branch` to `develop`.

---

## 5. Rollout

Single PR, breaking-change commit on `feat/search-mode-consolidation` branch. Conventional-commit syntax:

```
feat(search)!: consolidate four search flags into --mode {fast,standard,boosted,max}
```

No deprecation window — single-user system, the user is the only caller, and Castle has no external plugin consumers.
