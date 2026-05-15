# Search Mode Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four-flag search interface (`--llm-rerank`, `--soar-boost`, `--soar-first`, `--no-quality-rerank`) with a single `--mode {fast,standard,boosted,max}` enum across CLI, MCP, and the programmatic Python API.

**Architecture:** Single PR on `feat/search-mode-consolidation-spec`. Sub-commits land in dependency order — refactors first, then signature changes ripple through `_apply_optional_stages` → `_new_pipeline_search` → `search` / `search_memories` → CLI / MCP. Property deletions in `config.py` and the early-return in `soar_bridge.py` MUST land in the same commit (S2 risk).

**Tech Stack:** Python 3.10+, argparse, pytest, ruff, LanceDB. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-15-search-mode-consolidation-design.md`

---

## File Map

**Modified:**
- `cognitive_castle/cli.py` — extract `build_parser()`, replace 4 search flags with `--mode`, update `cmd_search` body
- `cognitive_castle/mcp_server.py` — replace 4 booleans on `tool_search` with `mode`, update `castle_search` JSON schema
- `cognitive_castle/searcher.py` — update `_stage_4_judge` (preserve tail + `judge_status` stash), `_apply_optional_stages` (signature → mode dispatch), `_new_pipeline_search` / `search` / `search_memories` (thread `mode`), result serializer (allowlist `judge_status`), `_print_search_results` (JUDGE block)
- `cognitive_castle/config.py` — delete `cfg.soar_enabled` and `cfg.quality_disabled` properties
- `cognitive_castle/soar_bridge.py` — remove `if not cfg.soar_enabled` early-return
- `cognitive_castle/quality_rerank.py` — docstring only (remove `cfg.quality_disabled` reference)
- `CLAUDE.md` — replace Stage 4-6 retrieval-pipeline block with mode table
- `tests/conftest.py` — add `_mock_cfg` and `_mock_cfg_top_n_3` fixtures
- `tests/test_judge.py` — update 9 `_mock_cfg()` call sites to fixture references; add 4 new tests
- `tests/test_pipeline_order.py` — update 9+ `_apply_optional_stages` call sites; add 2 new tests; delete `--soar-first` test
- `tests/test_cli.py` — add 3 new tests; delete 6 stale flag/kill-switch tests
- `tests/test_mcp_server.py` — add 3 new tests; delete 3 stale kill-switch tests
- `tests/test_config.py` — add 1 parametrized "removed attrs absent" test; delete 6 stale property tests
- `tests/test_searcher.py` — add 3 programmatic-parity tests
- `tests/test_soar_bridge.py` — delete 1 kill-switch test; update 1
- `tests/test_quality_rerank.py` — delete 1 `quality_disabled` test; update 2

**Created:** none

---

## Task 1: Extract `cli.build_parser()` (haiku)

**Why first:** All new CLI tests need to import the parser. Today it's constructed inline in `main()`.

**Files:**
- Modify: `cognitive_castle/cli.py:953-...` (the `def main():` block)

- [ ] **Step 1.1: Locate `main()` and the parser-construction block**

Run: `grep -n "^def main\|argparse.ArgumentParser" cognitive_castle/cli.py`
Expected: One match for `def main()` and one for `argparse.ArgumentParser(`, both inside `main()`. Note both line numbers.

- [ ] **Step 1.2: Refactor — extract `build_parser()` above `main()`**

In `cli.py`, immediately before `def main():`, add:

```python
def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser. Extracted from main() so tests can
    import the parser without invoking the full CLI dispatcher."""
    parser = argparse.ArgumentParser(
        # ... move all existing ArgumentParser arguments + every sub.add_parser /
        # add_argument call from main() up to (but NOT including) the
        # `args = parser.parse_args()` line into this function body ...
    )
    # ... (entire existing parser-build body) ...
    return parser
```

Then in `main()`, replace the moved block with:

```python
def main():
    parser = build_parser()
    args = parser.parse_args()
    # ... rest of main() unchanged (dispatch table, etc.) ...
```

Apply the diff mechanically — no flag or subcommand should change. Every `p_*` variable defined in the old block (`p_init`, `p_search`, `p_mine`, etc.) must remain inside `build_parser()`'s body.

- [ ] **Step 1.3: Run the full test suite to confirm zero behavior change**

Run: `python -m pytest tests/ -v --ignore=tests/benchmarks -x 2>&1 | tail -20`
Expected: All tests pass (whatever count is current — no new failures vs. baseline).

- [ ] **Step 1.4: Commit**

```bash
git add cognitive_castle/cli.py
git commit -m "refactor(cli): extract build_parser() from main() for testability

No behavior change. Subsequent tasks add parser-level tests that
need to import the parser without running the full CLI dispatcher."
```

---

## Task 2: Migrate `_mock_cfg` to a shared pytest fixture (haiku)

**Why:** Subsequent tests in `test_pipeline_order.py` and `test_judge.py` need `_mock_cfg` as a fixture parameter. Today it's a plain function at `test_judge.py:10` called as `_mock_cfg()` from 9 sites in that file.

**Files:**
- Modify: `tests/conftest.py` — add two fixtures
- Modify: `tests/test_judge.py:10` and 9 call sites — convert function calls to fixture parameters

- [ ] **Step 2.1: Add fixtures to `conftest.py`**

Append at the bottom of `tests/conftest.py`:

```python
@pytest.fixture
def _mock_cfg():
    """Minimal cfg for judge / pipeline-stage unit tests.

    Exposes only the knobs Stage 4 (`_stage_4_judge`) reads:
    ``llm_judge_top_n`` and ``llm_model``.
    """
    cfg = MagicMock()
    cfg.llm_judge_top_n = 10
    cfg.llm_model = "qwen3.5:latest"
    return cfg


@pytest.fixture
def _mock_cfg_top_n_3(_mock_cfg):
    """Like ``_mock_cfg`` but with ``llm_judge_top_n=3`` so the
    ``reranked[top_n:]`` preservation path is testable."""
    _mock_cfg.llm_judge_top_n = 3
    return _mock_cfg
```

Verify `from unittest.mock import MagicMock` exists at the top of `conftest.py`; if not, add it.

- [ ] **Step 2.2: Delete the plain-function `_mock_cfg` from `test_judge.py`**

Open `tests/test_judge.py`. Delete lines 10-14 (the `def _mock_cfg(): ...` function body).

- [ ] **Step 2.3: Update call sites in `test_judge.py`**

For every function in `test_judge.py` that calls `_mock_cfg()`, add `_mock_cfg` as a fixture parameter and replace the call with the fixture reference. Run:

`grep -n "_mock_cfg" tests/test_judge.py`

For each occurrence, update both the def line and the call site:

```python
# BEFORE:
def test_judge_returns_identity_on_provider_error():
    result = judge("test query", [f"doc {i}" for i in range(10)], _mock_cfg())

# AFTER:
def test_judge_returns_identity_on_provider_error(_mock_cfg):
    result = judge("test query", [f"doc {i}" for i in range(10)], _mock_cfg)
```

There are 9 such sites — update each. The pattern is exactly `_mock_cfg()` → `_mock_cfg` and adding the param to the test signature.

- [ ] **Step 2.4: Run the targeted test file**

Run: `python -m pytest tests/test_judge.py -v`
Expected: All existing tests pass (same count as before the refactor — fixture migration is behavior-preserving).

- [ ] **Step 2.5: Commit**

```bash
git add tests/conftest.py tests/test_judge.py
git commit -m "test(judge): migrate _mock_cfg from plain function to shared fixture

Adds _mock_cfg and _mock_cfg_top_n_3 fixtures in conftest.py so
test_pipeline_order.py and other test files can reuse them.
Updates 9 call sites in test_judge.py."
```

---

## Task 3: Rewrite `_stage_4_judge` + add judge_status to serializer + add JUDGE printer block (sonnet)

**Why:** This is the C1 fix. Without judge_status flowing through the result serializer allowlist (`searcher.py:645-677`) AND a matching printer block, the audit line never reaches users.

**Files:**
- Modify: `cognitive_castle/searcher.py` — `_stage_4_judge` body + docstring (lines ~394-414); serializer allowlist (~645-677); `_print_search_results` (~145-194)
- Modify: `tests/test_judge.py` — add 3 new tests

- [ ] **Step 3.1: Write the failing tests in `tests/test_judge.py`**

Append to `tests/test_judge.py`:

```python
def test_stage_4_judge_status_on_successful_reorder(_mock_cfg):
    """When judge reorders, _stage_4_judge stashes a status dict on hits[0]."""
    from unittest.mock import patch
    from cognitive_castle import searcher
    fake_reorder = [2, 0, 1]
    reranked = [(1.0 - i * 0.1, {"text": f"t{i}"}) for i in range(3)]
    with patch("cognitive_castle.judge.judge", return_value=fake_reorder):
        out = searcher._stage_4_judge("q", reranked, _mock_cfg)
    status = out[0][1]["judge_status"]
    assert status["reordered"] is True
    assert status["n"] == 3
    assert status["model"] == "qwen3.5:latest"
    assert isinstance(status["elapsed_s"], float)


def test_stage_4_judge_status_on_failure_is_identity_fallback(_mock_cfg):
    """ConnectionError (or any Exception) → identity-order return + error stash."""
    from unittest.mock import patch
    from cognitive_castle import searcher
    reranked = [(1.0 - i * 0.1, {"text": f"t{i}"}) for i in range(3)]
    with patch("cognitive_castle.judge.judge", side_effect=ConnectionError("ollama down")):
        out = searcher._stage_4_judge("q", reranked, _mock_cfg)
    assert out == reranked  # identity-order fallback
    assert out[0][1]["judge_status"] == {"error": "ConnectionError: ollama down"}


def test_stage_4_judge_preserves_hits_beyond_top_n(_mock_cfg_top_n_3):
    """With 5 hits and top_n=3, output keeps all 5 — top-3 reordered, hits
    4 and 5 untouched at the end. Behavior change from live code which
    discards reranked[top_n:]."""
    from unittest.mock import patch
    from cognitive_castle import searcher
    fake_reorder = [2, 0, 1]
    reranked = [(1.0 - i * 0.1, {"text": f"t{i}"}) for i in range(5)]
    with patch("cognitive_castle.judge.judge", return_value=fake_reorder):
        out = searcher._stage_4_judge("q", reranked, _mock_cfg_top_n_3)
    assert len(out) == 5
    assert [r[1]["text"] for r in out[:3]] == ["t2", "t0", "t1"]  # reordered top-3
    assert [r[1]["text"] for r in out[3:]] == ["t3", "t4"]  # tail preserved
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `python -m pytest tests/test_judge.py::test_stage_4_judge_status_on_successful_reorder tests/test_judge.py::test_stage_4_judge_status_on_failure_is_identity_fallback tests/test_judge.py::test_stage_4_judge_preserves_hits_beyond_top_n -v`

Expected:
- `test_stage_4_judge_preserves_hits_beyond_top_n` FAILS — live code truncates so `len(out) == 3`, not 5.
- `test_stage_4_judge_status_on_successful_reorder` FAILS — live code doesn't stash `judge_status`.
- `test_stage_4_judge_status_on_failure_is_identity_fallback` FAILS — live code doesn't catch exceptions; `ConnectionError` propagates out.

- [ ] **Step 3.3: Rewrite `_stage_4_judge` in `cognitive_castle/searcher.py`**

Replace the body at lines ~394-414 with:

```python
def _stage_4_judge(
    query: str,
    reranked: list[tuple[float, dict]],
    cfg,
) -> list[tuple[float, dict]]:
    """Stage 4: LLM-as-judge re-rank.

    Asks the LLM to reorder the top ``cfg.llm_judge_top_n`` hits. The
    rest of the input list is preserved unchanged at the tail of the
    return value.

    On any LLM failure (timeout, connection error, malformed reorder),
    returns ``reranked`` unchanged in identity order and stashes
    ``{"error": "<ExceptionClass>: <msg>"}`` on the first hit's dict so
    the CLI printer can surface a JUDGE audit line.

    On successful reorder, stashes ``{"reordered": True, "n": top_n,
    "model": cfg.llm_model, "elapsed_s": <float>}`` on the first hit's
    dict. If the judge returns identity order, no dict is stashed.

    The stashed ``judge_status`` is dropped by callers unless it appears
    in the result serializer allowlist in ``search_memories``.
    """
    import time
    from .judge import judge

    if not reranked:
        return reranked

    started = time.time()
    try:
        top_n = cfg.llm_judge_top_n
        judge_pool = reranked[:top_n]
        judge_docs = [_extract_text(r) for _, r in judge_pool]
        new_order = judge(query, judge_docs, cfg)
        elapsed = round(time.time() - started, 2)

        if new_order != list(range(len(new_order))):
            reordered_top = [judge_pool[i] for i in new_order]
            new_reranked = reordered_top + reranked[top_n:]
            new_reranked[0][1]["judge_status"] = {
                "reordered": True,
                "n": top_n,
                "model": cfg.llm_model,
                "elapsed_s": elapsed,
            }
            return new_reranked

        # Identity order — return original list, no status stash
        return reranked

    except Exception as e:  # noqa: BLE001 — deliberate broad catch for graceful fallback
        reranked[0][1]["judge_status"] = {"error": f"{type(e).__name__}: {e}"}
        return reranked
```

- [ ] **Step 3.4: Add `judge_status` to the result serializer allowlist**

In `cognitive_castle/searcher.py` at lines ~645-677, find the dict literal returned by `search_memories`. Inside the dict (after the existing `"quality_*"` keys, before the closing `}`), add:

```python
            # LLM judge audit trail — populated only when Stage 4 ran AND
            # either reordered hits or hit an error. Absent otherwise (no
            # audit line emitted for identity-order success).
            "judge_status": (r.get("judge_status") if isinstance(r, dict) else None),
```

- [ ] **Step 3.5: Add JUDGE block to `_print_search_results`**

In `cognitive_castle/searcher.py` at the `_print_search_results` function (~lines 145-194), after the print loop ends, append a JUDGE audit line block. Find the line `print(f"  {'─' * 56}")` (the separator at the end of the per-hit loop) and BEFORE the function returns add:

```python
    # JUDGE audit line — driven by judge_status stashed on hits[0] by
    # _stage_4_judge. Absent for identity-order success (no surprise to
    # surface) or when mode < max (Stage 4 didn't run).
    status = hits[0].get("judge_status") if hits else None
    if status:
        if "error" in status:
            print(f"\n  JUDGE: FAILED ({status['error']}) — identity-order fallback")
        elif status.get("reordered"):
            print(
                f"\n  JUDGE: reordered {status['n']} hits "
                f"({status['model']}, {status['elapsed_s']}s)"
            )
```

- [ ] **Step 3.6: Run the three new tests + the existing test_judge.py suite**

Run: `python -m pytest tests/test_judge.py -v`
Expected: All tests pass — the three new tests + all 9 pre-existing tests.

- [ ] **Step 3.7: Run the full pipeline_order suite to confirm no regressions**

Run: `python -m pytest tests/test_pipeline_order.py -v 2>&1 | tail -10`
Expected: Same pass/fail count as before Step 3.3 (no regressions from the `_stage_4_judge` rewrite).

- [ ] **Step 3.8: Commit**

```bash
git add cognitive_castle/searcher.py tests/test_judge.py
git commit -m "fix(searcher): _stage_4_judge preserves tail + emits judge_status

Three changes to Stage 4 behavior:
1. Preserve reranked[top_n:] at the tail of the return (live code
   truncated — hits beyond top_n were silently dropped).
2. Stash judge_status on hits[0] for the CLI audit-line printer
   to surface (\"reordered N hits\" / \"FAILED ... fallback\").
3. Catch all exceptions and return identity order with an error
   status (live code let exceptions propagate to the caller).

Also wires judge_status through the result serializer allowlist
and adds the printer block to _print_search_results. Without
those, the audit dict is silently dropped before reaching MCP /
CLI callers."
```

---

## Task 4: Switch `_apply_optional_stages` to mode-dispatch + ripple through callers (sonnet)

**Why:** The C2 mode-dispatch logic and the signature change ripple through `_new_pipeline_search`, `search`, and `search_memories`. Doing this in one commit keeps the suite green at each commit boundary.

**Files:**
- Modify: `cognitive_castle/searcher.py` — `_apply_optional_stages` (453-490), `_new_pipeline_search` (492+), `search` (195+), `search_memories` (245+)
- Modify: `tests/test_pipeline_order.py` — update 9+ `_apply_optional_stages` call sites; add 2 new tests; delete the `test_soar_first_*` test

- [ ] **Step 4.1: Write the failing tests at the top of `tests/test_pipeline_order.py`**

Add (preserve existing imports; the new tests use `_mock_cfg` fixture from conftest):

```python
import pytest
from unittest.mock import patch
from cognitive_castle import searcher as searcher_mod


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
        patch("cognitive_castle.searcher._stage_4_judge",
              side_effect=lambda q, r, c: r) as j,
        patch("cognitive_castle.searcher._stage_5_soar",
              side_effect=lambda r, c, query="": r) as s,
        patch("cognitive_castle.searcher._stage_6_quality",
              side_effect=lambda r, c: r) as q,
    ):
        searcher_mod._apply_optional_stages(
            "q", [(1.0, {"text": "x"})], _mock_cfg, mode
        )
    assert j.called is expect_judge
    assert s.called is expect_soar
    assert q.called is expect_quality


def test_max_mode_calls_stages_in_order_4_5_6(_mock_cfg):
    calls = []
    with (
        patch("cognitive_castle.searcher._stage_4_judge",
              side_effect=lambda q, r, c: calls.append("4") or r),
        patch("cognitive_castle.searcher._stage_5_soar",
              side_effect=lambda r, c, query="": calls.append("5") or r),
        patch("cognitive_castle.searcher._stage_6_quality",
              side_effect=lambda r, c: calls.append("6") or r),
    ):
        searcher_mod._apply_optional_stages(
            "q", [(1.0, {"text": "x"})], _mock_cfg, "max"
        )
    assert calls == ["4", "5", "6"]
```

- [ ] **Step 4.2: Run the new tests — they will fail**

Run: `python -m pytest tests/test_pipeline_order.py::test_apply_optional_stages_dispatches_by_mode tests/test_pipeline_order.py::test_max_mode_calls_stages_in_order_4_5_6 -v`
Expected: FAIL with `TypeError: _apply_optional_stages() got an unexpected keyword argument 'mode'` (current signature uses booleans).

- [ ] **Step 4.3: Rewrite `_apply_optional_stages` in `searcher.py`**

Replace the function at lines ~453-490 with:

```python
def _apply_optional_stages(
    query: str,
    reranked: list[tuple[float, dict]],
    cfg,
    mode: str,
) -> list[tuple[float, dict]]:
    """Run optional Stages 4 (judge), 5 (SOAR), and 6 (quality rerank)
    according to ``mode``.

    Modes:
        fast      → Stage 3 only (returns reranked unchanged)
        standard  → Stage 6
        boosted   → Stage 5 + Stage 6
        max       → Stage 4 + Stage 5 + Stage 6  (default)

    Order in ``max`` is fixed: judge → SOAR → quality.

    Raises ValueError on unknown mode.
    """
    if mode == "fast":
        return reranked
    if mode == "standard":
        return _stage_6_quality(reranked, cfg)
    if mode == "boosted":
        reranked = _stage_5_soar(reranked, cfg, query=query)
        return _stage_6_quality(reranked, cfg)
    if mode == "max":
        reranked = _stage_4_judge(query, reranked, cfg)
        reranked = _stage_5_soar(reranked, cfg, query=query)
        return _stage_6_quality(reranked, cfg)
    raise ValueError(f"invalid mode '{mode}' (must be fast|standard|boosted|max)")
```

- [ ] **Step 4.4: Update `_new_pipeline_search` signature in `searcher.py`**

Find the `def _new_pipeline_search(` signature (around line 492). Replace the 4 boolean parameters (`llm_rerank`, `soar_boost`, `soar_first`, `quality_rerank`) with a single `mode: str = "max"`:

```python
def _new_pipeline_search(
    query: str,
    palace_path: str,
    wing: str | None,
    room: str | None,
    n_results: int,
    cfg,
    is_hook_call: bool = False,
    mode: str = "max",
) -> list:
```

Inside `_new_pipeline_search`, find the `reranked = _apply_optional_stages(...)` call (around line 635) and replace its keyword arguments:

```python
# BEFORE:
reranked = _apply_optional_stages(
    query=query,
    reranked=reranked,
    cfg=cfg,
    llm_rerank=llm_rerank,
    soar_boost=soar_boost,
    soar_first=soar_first,
    quality_rerank=quality_rerank,
)

# AFTER:
reranked = _apply_optional_stages(query, reranked, cfg, mode)
```

- [ ] **Step 4.5: Update `search` and `search_memories` signatures in `searcher.py`**

In `def search(...)` (around line 195) — replace the 4 booleans with `mode: str = "max"` and update the `search_memories(...)` call body:

```python
def search(
    query: str,
    palace_path: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
    mode: str = "max",
):
    """CLI entry point ... [keep existing docstring, update the args
    section to describe mode instead of the four booleans]."""
    from .backends.base import EmbedderIdentityMismatchError

    try:
        result = search_memories(
            query=query,
            palace_path=palace_path,
            wing=wing,
            room=room,
            n_results=n_results,
            mode=mode,
        )
    except EmbedderIdentityMismatchError:
        raise
    except Exception as e:
        print(f"\n  Search error: {e}")
        raise SearchError(f"Search error: {e}") from e
    _print_search_results(result, query)
```

In `def search_memories(...)` (around line 245) — same change:

```python
def search_memories(
    query: str,
    palace_path: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
    max_distance: float = 0.0,
    vector_disabled: bool = False,
    candidate_strategy: str = "vector",
    is_hook_call: bool = False,
    mode: str = "max",
) -> dict:
    """[keep existing docstring, update args section]."""
    from .config import CognitiveCastleConfig as _cfg_cls

    cfg = _cfg_cls()
    results = _new_pipeline_search(
        query,
        palace_path,
        wing,
        room,
        n_results,
        cfg,
        is_hook_call=is_hook_call,
        mode=mode,
    )
    # ... rest of body unchanged ...
```

- [ ] **Step 4.6: Update existing `_apply_optional_stages` call sites in `tests/test_pipeline_order.py`**

There are at least 9 call sites. Run:

`grep -n "_apply_optional_stages(" tests/test_pipeline_order.py`

For each call site of the old form:

```python
searcher_mod._apply_optional_stages(
    query=query,
    reranked=reranked,
    cfg=cfg,
    llm_rerank=True,
    soar_boost=True,
    soar_first=False,
    quality_rerank=False,
)
```

Replace with the new form, choosing the mode that gives equivalent stage activation:

| Old combination                                      | Mode       |
|------------------------------------------------------|------------|
| `llm_rerank=False, soar_boost=False, quality_rerank=False` | `"fast"`     |
| `llm_rerank=False, soar_boost=False, quality_rerank=True`  | `"standard"` |
| `llm_rerank=False, soar_boost=True, quality_rerank=True`   | `"boosted"`  |
| `llm_rerank=True,  soar_boost=True,  quality_rerank=True`  | `"max"`      |
| `llm_rerank=True,  soar_boost=True,  quality_rerank=False` | (use `"max"` then verify the existing test still passes — quality rerank is mocked) |

Concretely the replacement is:

```python
searcher_mod._apply_optional_stages(query, reranked, cfg, "max")
```

(positional, four args). Apply mechanically per call site.

- [ ] **Step 4.7: Delete the `--soar-first` test**

In `tests/test_pipeline_order.py`, find and delete the entire `def test_soar_first_runs_soar_then_judge(...)` test (around line 137) — the `--soar-first` toggle no longer exists. The replacement is `test_max_mode_calls_stages_in_order_4_5_6` already added in Step 4.1.

Also delete `def test_soar_only_no_judge_call(...)` (around line 174) — same intent now covered by the parametrized dispatch test.

Verify only 2 deletions:

`grep -c "^def test_" tests/test_pipeline_order.py`

Note the count before and after — expect a decrease of 2.

- [ ] **Step 4.8: Run test_pipeline_order.py**

Run: `python -m pytest tests/test_pipeline_order.py -v`
Expected: All pass, including the 2 new parametrized tests (5 test invocations from `test_apply_optional_stages_dispatches_by_mode`).

- [ ] **Step 4.9: Run test_searcher.py to catch caller-side regressions**

Run: `python -m pytest tests/test_searcher.py -v 2>&1 | tail -20`
Expected: Some tests may fail because they pass the old booleans to `search_memories` or `search`. **Fix them in this same commit** — for each failure, locate the `search_memories(..., llm_rerank=..., soar_boost=..., soar_first=..., quality_rerank=...)` call site and replace with `mode=`. The full mode lookup table from Step 4.6 applies.

- [ ] **Step 4.10: Run the full test suite**

Run: `python -m pytest tests/ -v --ignore=tests/benchmarks 2>&1 | tail -20`
Expected: All pass. If anything fails, it's a missed call site — `grep -rn "llm_rerank\|soar_boost\|soar_first\|quality_rerank" tests/ cognitive_castle/` to find stragglers.

- [ ] **Step 4.11: Commit**

```bash
git add cognitive_castle/searcher.py tests/test_pipeline_order.py tests/test_searcher.py
git commit -m "feat(searcher)!: replace 4 boolean flags with mode enum

Breaking change to search_memories/search/_new_pipeline_search/
_apply_optional_stages — the four optional-stage booleans are
replaced with a single mode: str = 'max' enum:

  fast     → Stage 3 only
  standard → 3 + 6 (quality rerank)
  boosted  → 3 + 5 + 6 (SOAR + quality)
  max      → 3 + 4 + 5 + 6 (LLM judge + SOAR + quality)  ← default

Order in max is fixed: judge → SOAR → quality. The --soar-first
toggle is removed because it was rarely used and made the call
graph harder to reason about.

Stage 6 is now ON by default for all modes except fast. This is
a deliberate behavior change from the previous default-on /
opt-out-via-flag arrangement."
```

---

## Task 5: CLI surface — parser flags + cmd_search body + tests (sonnet)

**Files:**
- Modify: `cognitive_castle/cli.py` — `p_search` add_argument block (~1117-1160), `cmd_search` body (~582-635)
- Modify: `tests/test_cli.py` — add 3 new tests, delete 6 stale ones

- [ ] **Step 5.1: Write failing CLI tests in `tests/test_cli.py`**

Append at the end of `tests/test_cli.py`:

```python
import pytest
from cognitive_castle import cli


@pytest.mark.parametrize("bad", ["full", "FAST", "", "judge"])
def test_search_rejects_invalid_mode(bad, capsys):
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["search", "q", "--mode", bad])
    err = capsys.readouterr().err
    assert "invalid choice" in err


@pytest.mark.parametrize("flag", [
    "--llm-rerank", "--soar-boost", "--soar-first", "--no-quality-rerank"
])
def test_removed_flags_rejected(flag, capsys):
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["search", "q", flag])
    err = capsys.readouterr().err
    assert "unrecognized arguments" in err


def test_search_default_mode_is_max():
    parser = cli.build_parser()
    args = parser.parse_args(["search", "q"])
    assert args.mode == "max"
```

- [ ] **Step 5.2: Delete stale CLI tests**

In `tests/test_cli.py`, find and delete tests that exercise the four removed flags or the kill-switch validation. Use `grep -n "def test_" tests/test_cli.py | grep -iE "llm_rerank|soar_boost|soar_first|quality_rerank|quality_disabled|soar_enabled"` to enumerate candidates.

Expected: 6 deletions matching the spec table. Examples of test names to look for:
- `test_search_llm_rerank_flag_passes_through`
- `test_search_soar_boost_flag_passes_through`
- `test_search_soar_first_without_companion_flags_fails`
- `test_search_soar_boost_requires_kill_switch`
- `test_search_no_quality_rerank_disables_stage_6`
- `test_quality_disabled_env_disables_stage_6`

If the actual names differ in your tree, use the grep output as the source of truth. Delete each test function body entirely (including its decorator).

- [ ] **Step 5.3: Run new tests — they should fail**

Run: `python -m pytest tests/test_cli.py::test_search_rejects_invalid_mode tests/test_cli.py::test_removed_flags_rejected tests/test_cli.py::test_search_default_mode_is_max -v`
Expected: FAIL — the old flags still exist; there's no `--mode`.

- [ ] **Step 5.4: Update the `p_search` add_argument block in `cli.py`**

In `cognitive_castle/cli.py`, find the `p_search.add_argument(...)` block around line 1121-1160 (the four flags `--llm-rerank`, `--soar-boost`, `--soar-first`, `--no-quality-rerank`). Delete all four `p_search.add_argument(...)` calls in that range.

In their place add:

```python
    p_search.add_argument(
        "--mode",
        choices=["fast", "standard", "boosted", "max"],
        default="max",
        help=(
            "Retrieval pipeline mode. "
            "fast=Stage 3 only; "
            "standard=+quality rerank; "
            "boosted=+SOAR boost-tags; "
            "max=+LLM judge (default). "
            "Pick fast for hooks/low latency; max for best quality."
        ),
    )
```

- [ ] **Step 5.5: Rewrite `cmd_search` body in `cli.py`**

Find `def cmd_search(args):` (around line 582). Replace its body up through the `search(...)` call with:

```python
def cmd_search(args):
    from .searcher import search, SearchError
    from .backends.base import EmbedderIdentityMismatchError

    cfg = CognitiveCastleConfig()
    mode = args.mode  # already validated by argparse choices=

    palace_path = os.path.expanduser(args.palace) if args.palace else cfg.palace_path

    try:
        search(
            query=args.query,
            palace_path=palace_path,
            wing=args.wing,
            room=args.room,
            n_results=args.results,
            mode=mode,
        )
    except EmbedderIdentityMismatchError as e:
        # Friendly migration prompt — print cleanly without a traceback.
        print(f"\n{e}", file=sys.stderr)
        sys.stderr.flush()
        # ... (preserve any existing trailing logic — os._exit, etc.) ...
```

If the function body has additional logic after the `search(...)` call (graceful exit handling, etc.), preserve it verbatim — only the kill-switch validation and the boolean-arg extraction at the top get deleted.

- [ ] **Step 5.6: Run the new tests + full test_cli.py**

Run: `python -m pytest tests/test_cli.py -v`
Expected: All pass — new tests succeed, no deleted-test zombies, and the remaining CLI tests are unchanged.

- [ ] **Step 5.7: Commit**

```bash
git add cognitive_castle/cli.py tests/test_cli.py
git commit -m "feat(cli)!: replace 4 search flags with --mode enum

CLI surface mirrors the searcher API change:
  --mode {fast,standard,boosted,max}  (default: max)

Deletes:
  --llm-rerank, --soar-boost, --soar-first, --no-quality-rerank
  and their kill-switch validation (CASTLE_SOAR_ENABLED check,
  --soar-first companion-flag check).

cmd_search body simplifies from ~30 lines of flag extraction +
validation to a 5-line passthrough."
```

---

## Task 6: MCP surface — tool_search + JSON schema + tests (sonnet)

**Files:**
- Modify: `cognitive_castle/mcp_server.py` — `tool_search` (~370-440), `castle_search` TOOLS dict (~1424-1495)
- Modify: `tests/test_mcp_server.py` — add 3 new tests, delete 3 stale kill-switch tests

- [ ] **Step 6.1: Write failing MCP tests in `tests/test_mcp_server.py`**

Append:

```python
def test_mcp_tool_search_default_mode_is_max():
    from unittest.mock import patch
    from cognitive_castle import mcp_server
    with patch(
        "cognitive_castle.mcp_server.search_memories",
        return_value={"results": []},
    ) as m:
        mcp_server.tool_search(query="q")
    assert m.call_args.kwargs.get("mode") == "max"


def test_mcp_tool_search_accepts_valid_modes():
    from unittest.mock import patch
    from cognitive_castle import mcp_server
    for mode in ("fast", "standard", "boosted", "max"):
        with patch(
            "cognitive_castle.mcp_server.search_memories",
            return_value={"results": []},
        ):
            result = mcp_server.tool_search(query="q", mode=mode)
        assert "error" not in result, f"mode={mode} returned error: {result}"


def test_mcp_tool_search_rejects_invalid_mode():
    from cognitive_castle import mcp_server
    result = mcp_server.tool_search(query="q", mode="full")
    assert "error" in result
    assert "invalid mode" in result["error"].lower()
```

- [ ] **Step 6.2: Delete stale MCP tests**

Run: `grep -n "def test_" tests/test_mcp_server.py | grep -iE "llm_rerank|soar_boost|soar_first|quality_rerank|quality_disabled|soar_enabled|kill_switch"`

Expected: 3 stale tests (per the spec table). Examples:
- `test_mcp_tool_search_soar_first_validation`
- `test_mcp_tool_search_soar_kill_switch`
- `test_mcp_tool_search_quality_disabled_kill_switch`

Delete each by name. Use the grep output as the source of truth.

- [ ] **Step 6.3: Run new tests — they fail**

Run: `python -m pytest tests/test_mcp_server.py::test_mcp_tool_search_default_mode_is_max tests/test_mcp_server.py::test_mcp_tool_search_accepts_valid_modes tests/test_mcp_server.py::test_mcp_tool_search_rejects_invalid_mode -v`
Expected: FAIL — `mode` is not a valid kwarg yet.

- [ ] **Step 6.4: Rewrite `tool_search` signature + body in `mcp_server.py`**

Replace the function signature + body at lines ~370-440 with:

```python
def tool_search(
    query: str,
    limit: int = 5,
    wing: str = None,
    room: str = None,
    max_distance: float = 1.5,
    min_similarity: float = None,
    context: str = None,
    mode: str = "max",
):
    # Mode validation in the function body (not the JSON schema) so the
    # error message is specific to Castle.
    if mode not in ("fast", "standard", "boosted", "max"):
        return {
            "error": (
                f"invalid mode '{mode}'. "
                "Must be one of: fast, standard, boosted, max"
            )
        }

    limit = max(1, min(limit, _MAX_RESULTS))
    try:
        wing = _sanitize_optional_name(wing, "wing")
        room = _sanitize_optional_name(room, "room")
    except ValueError as e:
        return {"error": str(e)}

    dist = (1.0 - min_similarity) if min_similarity is not None else max_distance
    sanitized = sanitize_query(query)

    result = search_memories(
        sanitized["clean_query"],
        palace_path=_config.palace_path,
        wing=wing,
        room=room,
        n_results=limit,
        max_distance=dist,
        mode=mode,
    )

    if sanitized["was_sanitized"]:
        result["query_sanitized"] = True
        result["sanitizer"] = {
            "method": sanitized["method"],
            "original_length": sanitized["original_length"],
            "clean_length": sanitized["clean_length"],
            "clean_query": sanitized["clean_query"],
        }
    if context:
        result["context_received"] = True

    # Strip internal metadata field before returning to the caller.
    # ... (preserve any existing trailing logic) ...
    return result
```

Note: if there is post-call shaping logic between `result = search_memories(...)` and `return result` that wasn't quoted above, preserve it verbatim. Only delete the kill-switch blocks, the `--soar-first` validation, and the `_config.quality_disabled` override.

- [ ] **Step 6.5: Update the `castle_search` JSON schema in mcp_server.py**

In the `TOOLS = {` dict (around line 1424), find the `"castle_search"` entry. In its `input_schema.properties` dict, delete the three boolean property entries (`"llm_rerank"`, `"soar_boost"`, `"quality_rerank"` — `soar_first` is NOT present in the schema today, so don't try to delete it).

In their place add:

```python
                "mode": {
                    "type": "string",
                    "enum": ["fast", "standard", "boosted", "max"],
                    "default": "max",
                    "description": (
                        "Retrieval pipeline mode. "
                        "fast=Stage 3 only (lowest latency); "
                        "standard=+quality rerank; "
                        "boosted=+SOAR boost-tags; "
                        "max=+LLM judge (default — highest quality)."
                    ),
                },
```

- [ ] **Step 6.6: Run test_mcp_server.py**

Run: `python -m pytest tests/test_mcp_server.py -v 2>&1 | tail -20`
Expected: All pass — 3 new, no zombies, existing tests survive.

- [ ] **Step 6.7: Commit**

```bash
git add cognitive_castle/mcp_server.py tests/test_mcp_server.py
git commit -m "feat(mcp)!: replace 4 booleans on tool_search with mode enum

Python signature and JSON schema both change. The schema previously
declared 3 booleans (llm_rerank, soar_boost, quality_rerank — note
soar_first was in the Python signature but never advertised in the
schema). All three are deleted; \"mode\" is added.

Mode validation lives in the function body (returns {error: ...})
rather than the JSON schema, so the error message can be specific
to Castle (lists the four valid modes inline)."
```

---

## Task 7: Delete `cfg.soar_enabled` + `cfg.quality_disabled` + remove soar_bridge early-return (haiku)

**Critical — same commit:** Per spec risk S2, deleting `cfg.soar_enabled` from `config.py` BEFORE removing the `if not cfg.soar_enabled` early-return in `soar_bridge.py` causes `AttributeError` in any test that reaches `_stage_5_soar`. Land both edits in the same commit.

**Files:**
- Modify: `cognitive_castle/config.py` — delete properties at lines ~541-556 and ~781-796
- Modify: `cognitive_castle/soar_bridge.py` — delete the `if not cfg.soar_enabled` block at ~439-444; also delete the docstring reference at line 3 and the `cfg.soar_enabled` mention in `apply_soar_boosts` docstring (~line 420)
- Modify: `cognitive_castle/quality_rerank.py` — search for any `cfg.quality_disabled` reference in docstrings; remove
- Modify: `tests/test_config.py` — add 1 parametrized test, delete 6 stale tests
- Modify: `tests/test_soar_bridge.py` — delete 1 test, update 1
- Modify: `tests/test_quality_rerank.py` — delete 1 test, update 2

- [ ] **Step 7.1: Write the failing config test**

Append to `tests/test_config.py`:

```python
import pytest
from cognitive_castle.config import CognitiveCastleConfig


@pytest.mark.parametrize("attr", ["soar_enabled", "quality_disabled"])
def test_removed_config_properties_are_absent(attr):
    cfg = CognitiveCastleConfig()
    assert not hasattr(cfg, attr), (
        f"cfg.{attr} should have been deleted in the search-mode "
        "consolidation; if you need a stage-on/off toggle, use mode="
    )
```

- [ ] **Step 7.2: Delete stale config tests**

Run: `grep -n "def test_" tests/test_config.py | grep -iE "soar_enabled|quality_disabled"`

Expected: 6 tests across two property suites (default, env override, file_config override × 2 properties). Delete each by name.

- [ ] **Step 7.3: Delete the properties in `config.py`**

In `cognitive_castle/config.py`:
- Find `def soar_enabled` (around line 541) and delete the entire property — including its `@property` decorator, the function body, and any trailing docstring. The block typically runs ~15 lines (541-556).
- Find `def quality_disabled` (around line 781) and delete the same way (~15 lines, 781-796).

After both deletions, run `grep -n "soar_enabled\|quality_disabled" cognitive_castle/config.py` — expect zero matches.

- [ ] **Step 7.4: Remove the early-return in `soar_bridge.py`**

In `cognitive_castle/soar_bridge.py` at lines ~439-445, find and delete:

```python
    # Kill switch check (defensive — CLI/MCP layer should have caught this)
    if not cfg.soar_enabled:
        _warn_once(
            "kill-switch-disabled",
            "apply_soar_boosts called with cfg.soar_enabled=False — returning hits unchanged",
        )
        return hits
```

Also remove the docstring references:
- Line 3: `Opt-in via cfg.soar_enabled + --soar-boost CLI flag (or soar_boost:true MCP).` → change to `Opt-in via --mode boosted/max (or mode:boosted/max MCP).`
- Line 420 inside `apply_soar_boosts` docstring: any mention of `.soar_enabled` — delete that sentence.

Run `grep -n "soar_enabled" cognitive_castle/soar_bridge.py` — expect zero matches.

- [ ] **Step 7.5: Update `quality_rerank.py` docstring**

Run: `grep -n "quality_disabled" cognitive_castle/quality_rerank.py`

For each match, delete the sentence/line that references it. Most likely a sentence in the module docstring or a function docstring. Run the grep again — expect zero matches.

- [ ] **Step 7.6: Update affected soar_bridge and quality_rerank tests**

`tests/test_soar_bridge.py` — find the test that exercises the early-return (search for `soar_enabled` in the file):

`grep -n "soar_enabled" tests/test_soar_bridge.py`

Expect 1 test that asserts the kill-switch early-return behavior. Delete that test. Also find any other test that calls the bridge with a config whose `soar_enabled` is False — update to use a config that doesn't set the attr (since `soar_enabled` no longer exists on `CognitiveCastleConfig`).

`tests/test_quality_rerank.py` — find the test that exercises the `cfg.quality_disabled` global kill switch:

`grep -n "quality_disabled" tests/test_quality_rerank.py`

Expect 1 test. Delete it. Update any other test that constructs a config with `quality_disabled` set.

- [ ] **Step 7.7: Run the full test suite**

Run: `python -m pytest tests/ -v --ignore=tests/benchmarks 2>&1 | tail -25`
Expected: All pass. If any `AttributeError: 'CognitiveCastleConfig' object has no attribute 'soar_enabled'` surfaces, you missed a caller — grep `cognitive_castle/` and `tests/` for `soar_enabled` and `quality_disabled`.

- [ ] **Step 7.8: Commit**

```bash
git add cognitive_castle/config.py cognitive_castle/soar_bridge.py cognitive_castle/quality_rerank.py tests/test_config.py tests/test_soar_bridge.py tests/test_quality_rerank.py
git commit -m "feat(config)!: delete soar_enabled + quality_disabled kill switches

Both kill-switch properties go away — modes are the new on/off
mechanism. The soar_bridge early-return is removed in the same
commit to avoid AttributeError during partial deployment.

Closes the open P2 gap from PR #45: programmatic search_memories
callers can no longer have their quality rerank silently disabled
via CASTLE_QUALITY_DISABLED. If you want to skip Stage 6, pass
mode='fast' instead."
```

---

## Task 8: Programmatic mode= parity tests in test_searcher.py (haiku)

**Why:** Explicitly closes the P2 review gap flagged on PR #45 — programmatic callers no longer execute Stage 6 silently.

**Files:**
- Modify: `tests/test_searcher.py` — add 3 new tests

- [ ] **Step 8.1: Add the tests at the end of `tests/test_searcher.py`**

```python
import pytest
from unittest.mock import patch
from cognitive_castle import searcher as searcher_mod


def _make_fake_pipeline_result():
    """Build a result dict shaped like _new_pipeline_search returns."""
    return [
        {"id": f"d{i}", "text": f"t{i}", "score": 1.0 - i * 0.1, "wing": "w", "room": "r"}
        for i in range(3)
    ]


def test_search_memories_default_mode_is_max(palace_path):
    """Programmatic callers get max by default — closes the PR #45 P2 gap."""
    captured = {}

    def stub(*args, **kwargs):
        captured.update(kwargs)
        return _make_fake_pipeline_result()

    with patch("cognitive_castle.searcher._new_pipeline_search", side_effect=stub):
        searcher_mod.search_memories(query="q", palace_path=palace_path)
    assert captured.get("mode") == "max"


def test_search_memories_mode_fast_threads_through(palace_path):
    captured = {}

    def stub(*args, **kwargs):
        captured.update(kwargs)
        return _make_fake_pipeline_result()

    with patch("cognitive_castle.searcher._new_pipeline_search", side_effect=stub):
        searcher_mod.search_memories(query="q", palace_path=palace_path, mode="fast")
    assert captured.get("mode") == "fast"


def test_search_memories_invalid_mode_raises(palace_path):
    """Invalid mode bubbles up from _apply_optional_stages as ValueError."""
    with pytest.raises(ValueError, match="invalid mode"):
        # Don't patch _new_pipeline_search — let the call reach
        # _apply_optional_stages, which validates mode.
        searcher_mod.search_memories(query="q", palace_path=palace_path, mode="full")
```

- [ ] **Step 8.2: Run the new tests**

Run: `python -m pytest tests/test_searcher.py::test_search_memories_default_mode_is_max tests/test_searcher.py::test_search_memories_mode_fast_threads_through tests/test_searcher.py::test_search_memories_invalid_mode_raises -v`
Expected: All pass.

- [ ] **Step 8.3: Run the full test_searcher.py suite**

Run: `python -m pytest tests/test_searcher.py -v 2>&1 | tail -15`
Expected: All pass, no regressions from earlier tasks.

- [ ] **Step 8.4: Commit**

```bash
git add tests/test_searcher.py
git commit -m "test(searcher): add programmatic mode= parity tests

Closes the PR #45 P2 gap: confirms search_memories defaults to
mode=max for direct API callers (not just CLI/MCP), threads
mode=fast correctly, and raises ValueError on invalid mode."
```

---

## Task 9: Update CLAUDE.md retrieval-pipeline section (haiku)

**Files:**
- Modify: `CLAUDE.md:184-195` (Stage 4+5 block + Stage 6 line)

- [ ] **Step 9.1: Locate the block to replace**

Run: `grep -n "Stage 4\|Stage 5\|Stage 6\|soar-first\|llm-rerank\|soar-boost\|no-quality-rerank\|CASTLE_SOAR_ENABLED\|CASTLE_QUALITY_DISABLED" CLAUDE.md`

Confirm matches concentrate around lines 184-195.

- [ ] **Step 9.2: Replace the block**

In `CLAUDE.md`, find the exact block:

```
    ├── Stage 4 + Stage 5 (optional, composable; default order: 4 then 5)
    │     ├── Stage 4 (--llm-rerank or llm_rerank:true MCP): LLM-as-judge re-ranks
    │     │     top-cfg.llm_judge_top_n (default 10) from Stage 3
    │     │     → graceful identity-order fallback on any LLM failure
    │     ├── Stage 5 (--soar-boost AND CASTLE_SOAR_ENABLED=1): 4 SOAR symbolic
    │     │     productions (recency-boost, same-project, entity-match, type-match) add boost-tags
    │     │     → graceful pass-through on any Soar failure
    │     └── Ordering: default is Stage 4 then Stage 5 (judge-then-SOAR).
    │            --soar-first / soar_first:true flips to Stage 5 then Stage 4
    │            (requires both --llm-rerank AND --soar-boost on; loud sys.exit(2)
    │            on missing companion flags).
    ├── Stage 6 (ON by default, opt-out via `--no-quality-rerank` or `CASTLE_QUALITY_DISABLED=1`):
    │     deterministic text-quality rerank via vendored `understanding/` package —
    │     two-tier threshold rule with calibrated defaults (medium ×1.15, high ×1.25)
```

Replace with:

```
    ├── Stage 4-6 (gated by --mode):
    │     ├── --mode fast      → Stage 3 only (lowest latency)
    │     ├── --mode standard  → Stage 3 + Stage 6 (quality rerank)
    │     ├── --mode boosted   → Stage 3 + Stage 5 (SOAR boost-tags) + Stage 6
    │     └── --mode max       → Stage 3 + Stage 4 (LLM judge) + Stage 5 + Stage 6   ← default
    │           Stage 4 graceful-fallback: identity order on any LLM failure;
    │           surfaces via JUDGE audit line.
    │           Stage 5: 4 SOAR symbolic productions (recency-boost,
    │           same-project, entity-match, type-match) add boost-tags.
    │           Stage 6: deterministic text-quality rerank via vendored
    │           `understanding/` package — two-tier threshold (medium ×1.15, high ×1.25).
```

- [ ] **Step 9.3: Verify no stale flag references remain**

Run: `grep -n "\-\-llm-rerank\|\-\-soar-boost\|\-\-soar-first\|\-\-no-quality-rerank\|CASTLE_SOAR_ENABLED\|CASTLE_QUALITY_DISABLED" CLAUDE.md`
Expected: Zero matches.

- [ ] **Step 9.4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): update retrieval-pipeline section for --mode

Replaces the four-flag Stage 4-6 block with the mode table.
Removes references to CASTLE_SOAR_ENABLED, CASTLE_QUALITY_DISABLED,
--llm-rerank, --soar-boost, --soar-first, --no-quality-rerank."
```

---

## Task 10: Slow smoke test for end-to-end max-mode LLM path (sonnet)

**Why:** Catches Ollama URL changes, default-model regressions, and prompt-template breakage. Marked `@pytest.mark.slow` and excluded from CI; the user runs it locally before merging.

**Files:**
- Modify: `tests/test_judge.py` — add helper + fixture + slow test

- [ ] **Step 10.1: Verify pytest.ini / pyproject.toml registers the `slow` marker**

Run: `grep -A3 "markers" pyproject.toml setup.cfg pytest.ini 2>/dev/null`
Expected: A `slow:` marker entry. If absent, add to `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
]
```

- [ ] **Step 10.2: Locate an existing drawer-seeding pattern**

Run: `grep -rn "add_drawer\|seeded_collection" tests/ | head -10`

Note the pattern Castle's test suite uses to seed drawers. The slow test must call the same helper (don't invent a new path).

- [ ] **Step 10.3: Add helper, fixture, and test to `tests/test_judge.py`**

Append:

```python
def _ollama_reachable() -> bool:
    """True if Ollama is responding on localhost:11434."""
    import urllib.request
    import urllib.error
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
        return True
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


@pytest.fixture
def real_palace_fixture(palace_path):
    """A palace seeded with three drawers so search returns enough hits to
    exercise Stage 4.

    Uses Castle's standard add-drawer path so the seeded data flows through
    embedding, FTS index, and KG enrichment exactly as production would.
    """
    # NOTE for implementer: replace the seeding calls below with the helper
    # identified in Step 10.2 (e.g., miner.add_drawer or a conftest helper).
    # The shape is "seed exactly 3 drawers with distinct text content".
    from cognitive_castle import miner
    miner.add_drawer(palace_path, wing="test", room="r1",
                     text="Retrieval weights: dense 0.5, sparse 0.3, kg 0.2.")
    miner.add_drawer(palace_path, wing="test", room="r1",
                     text="We chose recency tau of 30 days.")
    miner.add_drawer(palace_path, wing="test", room="r1",
                     text="Unrelated content about cooking pasta.")
    return palace_path


@pytest.mark.slow
def test_max_mode_end_to_end_with_real_judge(real_palace_fixture):
    """Reaches actual Ollama. Skipped if not reachable; CI excludes via -m."""
    from cognitive_castle import searcher
    if not _ollama_reachable():
        pytest.skip("Ollama not running on localhost:11434")
    result = searcher.search_memories(
        query="What did we decide about retrieval weights?",
        palace_path=real_palace_fixture,
        mode="max",
    )
    assert "results" in result
    assert len(result["results"]) > 0
    # judge_status is absent (no-reorder happy path), a "reordered" success
    # dict, or an "error" failure dict — all three are valid post-conditions.
    status = result["results"][0].get("judge_status")
    if status is not None:
        assert "reordered" in status or "error" in status
```

- [ ] **Step 10.4: Run the slow test locally**

Run: `python -m pytest tests/test_judge.py::test_max_mode_end_to_end_with_real_judge -v -m slow`
Expected: PASS if Ollama is running and the configured model is installed; SKIP if not. Either result is acceptable for the commit.

- [ ] **Step 10.5: Confirm the slow test is excluded from the default CI suite**

Run: `python -m pytest tests/test_judge.py -v 2>&1 | grep -i "slow\|skip"`
Expected: The slow test appears in the SKIPPED list (or not collected at all if pytest is configured to deselect `-m slow` by default).

- [ ] **Step 10.6: Commit**

```bash
git add tests/test_judge.py pyproject.toml
git commit -m "test(judge): add slow smoke for end-to-end max-mode LLM path

Reaches real Ollama via Stage 4 → JUDGE audit line surfaces.
Marked @pytest.mark.slow so CI excludes it; the maintainer runs
it locally before merging.

Catches: Ollama URL changes, default-model regressions, prompt-
template breakage, judge_status serializer/printer regressions."
```

---

## Task 11: Final QA + PR + merge (sonnet)

**Files:** none modified. This task verifies the suite, lints, and lands the PR.

- [ ] **Step 11.1: Run the full test suite (excluding benchmarks and slow)**

Run: `python -m pytest tests/ -v --ignore=tests/benchmarks -m "not slow" 2>&1 | tail -10`
Expected: All tests pass. Capture the pass/fail summary.

- [ ] **Step 11.2: Run ruff check + format check**

Run: `ruff check . && ruff format --check .`
Expected: Both clean.

If ruff format fails, run `ruff format .` and commit the formatting fix:

```bash
git add -u
git commit -m "style: ruff format on mode-consolidation files"
```

- [ ] **Step 11.3: Final residual-flag grep**

Run:

```bash
grep -rn "llm_rerank\|soar_boost\|soar_first\|no_quality_rerank\|cfg.soar_enabled\|cfg.quality_disabled\|CASTLE_SOAR_ENABLED\|CASTLE_QUALITY_DISABLED" cognitive_castle/ tests/ CLAUDE.md docs/ 2>&1 | grep -v "docs/superpowers" | grep -v "\.pyc"
```

Expected: Zero matches outside `docs/superpowers/` (specs and plans reference the old names by design).

- [ ] **Step 11.4: Push and create the PR**

```bash
git push -u origin feat/search-mode-consolidation-spec
gh pr create --title "feat(search)!: consolidate four flags into --mode enum" --body "$(cat <<'EOF'
## Summary
- Replaces `--llm-rerank` / `--soar-boost` / `--soar-first` / `--no-quality-rerank` with a single `--mode {fast,standard,boosted,max}` enum (default `max`)
- Same change on MCP `tool_search` (4 booleans → `mode` string)
- Programmatic `search_memories` / `search` get `mode=` kwarg, closing the open P2 gap from PR #45 (programmatic callers can no longer silently skip Stage 6)
- Deletes `cfg.soar_enabled` and `cfg.quality_disabled` properties along with the `CASTLE_SOAR_ENABLED` / `CASTLE_QUALITY_DISABLED` env vars
- Stage 4 (`_stage_4_judge`) now preserves `reranked[top_n:]` (live code truncated) and surfaces a JUDGE audit line via `judge_status` stash + serializer allowlist + printer block

## Breaking changes
- All CLI flags / MCP booleans listed above are removed (no deprecation window — single-user system)
- Mode `max` is the new default; Stage 6 is now ON for every mode except `fast`
- Combinations that had no exact mode equivalent (e.g., `--soar-boost --no-quality-rerank`) shift behavior — see spec Section 1 "Migration regression" table

## Test plan
- [x] `pytest tests/ --ignore=tests/benchmarks -m "not slow"` clean
- [x] `ruff check .` + `ruff format --check .` clean
- [x] Slow smoke test (`-m slow`) passes locally against running Ollama
- [x] `grep` confirms no residual flag references outside `docs/superpowers/`

Spec: `docs/superpowers/specs/2026-05-15-search-mode-consolidation-design.md`
Plan: `docs/superpowers/plans/2026-05-15-search-mode-consolidation.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Capture the PR URL.

- [ ] **Step 11.5: Verify CI passes**

Run: `gh pr checks <PR-number>`
Expected: All checks green. If any fail, investigate before merging.

- [ ] **Step 11.6: Merge**

```bash
gh pr merge --merge --delete-branch
```

Expected: PR merged into `develop`, feature branch deleted on remote.

- [ ] **Step 11.7: Sync local develop**

```bash
git checkout develop
git pull
```

Expected: Local `develop` includes the merge commit. Branch `feat/search-mode-consolidation-spec` is gone (deleted by `--delete-branch`).
