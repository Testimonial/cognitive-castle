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

| Mode | Stages run | Latency tax (informational, not enforced) | Use case |
|---|---|---:|---|
| `fast`       | 3            | ~0 ms          | Hook-driven background pulls; lowest latency |
| `standard`   | 3, 6         | ~760 ms        | Default-quality interactive search w/o LLM |
| `boosted`    | 3, 5, 6      | ~770 ms        | Add SOAR symbolic boost-tags (deterministic) |
| `max`        | 3, 4, 5, 6   | ~1.8–2.8 s     | Full pipeline incl. LLM judge (default) |

Latency numbers are pre-PR measurements on the user's hardware. No test enforces them; they are documentation, not acceptance criteria.

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

### Migration regression: SOAR-without-quality

The map above is correct for each flag *alone*, but **combinations have no exact equivalent**:

| Old combination | What you got | Closest new mode | Difference |
|---|---|---|---|
| `--soar-boost --no-quality-rerank`           | Stages 3, 5         | `--mode boosted` (adds Stage 6) or `--mode fast` (drops SOAR) | Either gain quality rerank or lose SOAR |
| `--llm-rerank --no-quality-rerank`           | Stages 3, 4         | `--mode max` (adds 5, 6) or `--mode fast` (drops judge) | Either gain SOAR+quality or lose judge |
| `--llm-rerank --soar-boost --no-quality-rerank` | Stages 3, 4, 5    | `--mode max` (adds Stage 6) | Always gains quality rerank |
| `CASTLE_QUALITY_DISABLED=1` + any combo      | (combo with Stage 6 stripped) | (closest mode) | Quality rerank either gained or stages dropped |

This is a deliberate consequence of treating mode as a bundle, not a per-stage toggle. The user is the only caller; there are no saved invocations using these combinations. Acknowledged as an accepted behavior change, not a bug.

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

**`cmd_search` body changes:**

The function currently reads four boolean flags off `args` and threads them into `searcher.search()`. Replace those reads with a single `args.mode` read:

```python
# BEFORE (delete):
result = searcher.search(
    query=args.query,
    palace_path=args.palace,
    llm_rerank=args.llm_rerank,
    soar_boost=args.soar_boost,
    soar_first=args.soar_first,
    no_quality_rerank=args.no_quality_rerank,
    ...
)

# AFTER (replace with):
result = searcher.search(
    query=args.query,
    palace_path=args.palace,
    mode=args.mode,
    ...
)
```

Same pattern in any other CLI subcommand that calls `searcher.search()` (e.g., `cmd_hook`). Plan-time grep: `args.llm_rerank|args.soar_boost|args.soar_first|args.no_quality_rerank` across `cli.py`.

**`cmd_init` changes:** _(out of scope — see Section 6)_

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

**MCP JSON schema (`TOOLS` dict) update:**

Two separate changes — Python signature AND the advertised JSON schema. Both must match or MCP clients see ghost parameters.

In the `TOOLS` dict entry for `castle_search` (or whichever tool name maps to `tool_search`):

```python
# DELETE these four property entries from "properties":
"llm_rerank":       {"type": "boolean", "default": False, "description": "..."},
"soar_boost":       {"type": "boolean", "default": False, "description": "..."},
"soar_first":       {"type": "boolean", "default": False, "description": "..."},
"no_quality_rerank":{"type": "boolean", "default": False, "description": "..."},

# ADD this single property entry:
"mode": {
    "type": "string",
    "enum": ["fast", "standard", "boosted", "max"],
    "default": "max",
    "description": "Retrieval pipeline mode. fast=Stage 3 only; standard=+quality; boosted=+SOAR; max=+LLM judge.",
},
```

Plan-time grep: locate the `TOOLS` dict entry by searching for `"llm_rerank"` in `mcp_server.py`.

#### `cognitive_castle/searcher.py`

Signature changes:

```python
def search_memories(query, palace_path, *, mode: str = "max", ...): ...
def search(query, *, mode: str = "max", ...): ...
def _new_pipeline_search(query, ..., mode: str = "max"): ...
```

`search()` is a thin wrapper around `search_memories()` (currently at `searcher.py:195-235`). Its body passes the four old booleans through. The body must change too:

```python
# BEFORE (delete):
def search(query, *, llm_rerank=False, soar_boost=False, soar_first=False, quality_rerank=True, ...):
    return search_memories(
        query=query,
        llm_rerank=llm_rerank,
        soar_boost=soar_boost,
        soar_first=soar_first,
        quality_rerank=quality_rerank,
        ...
    )

# AFTER:
def search(query, *, mode: str = "max", ...):
    return search_memories(query=query, mode=mode, ...)
```

The `is_hook_call: bool = False` parameter on `search_memories` is **orthogonal to mode** — it controls reranker top-K caps (`reranker_k_hook` vs `reranker_k_interactive`). It is preserved unchanged. Mode and `is_hook_call` are independent dimensions; both can co-vary.

`_apply_optional_stages` keeps its name (already correct in `searcher.py:453`). Only its signature changes: replace the four boolean flags with a single `mode` string. Body becomes a mode-dispatched if/elif/else.

Stage helper signatures (verified against `searcher.py:394-450`):
- `_stage_4_judge(query, reranked, cfg)` — query first
- `_stage_5_soar(reranked, cfg, query="")` — query is keyword-only, last
- `_stage_6_quality(reranked, cfg)` — no query argument

The new body must respect these:

```python
def _apply_optional_stages(query, reranked, cfg, mode):
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

**Critical: serializer + printer updates** — without these, the `judge_status` dict is silently dropped before reaching callers.

The result serializer at `searcher.py:645-677` builds output dicts from an explicit allowlist. SOAR (`soar_tags`, `soar_boost`) and Stage 6 (`quality_score`, `quality_tier`) appear in that list precisely because their audit trails would otherwise vanish. `judge_status` needs the same treatment:

```python
# Add to the dict literal at searcher.py:645-677:
"judge_status": (r.get("judge_status") if isinstance(r, dict) else None),
```

The audit-line printer at `_print_search_results` (~lines 170-191) reads named keys like `soar_tags` and `quality_tier`. It has no `judge_status` read path. Add one:

```python
# Add to _print_search_results after the existing SOAR / quality blocks:
status = results[0].get("judge_status") if results else None
if status:
    if "error" in status:
        print(f"JUDGE: FAILED ({status['error']}) — identity-order fallback")
    elif status.get("reordered"):
        print(f"JUDGE: reordered {status['n']} hits ({status['model']}, {status['elapsed_s']}s)")
```

Verify before commit: grep `searcher.py` for `_print_search_results` and confirm both the allowlist and printer blocks land in the right place.

#### `cognitive_castle/config.py`

- Delete `cfg.soar_enabled` property (lines ~550–556).
- Delete `cfg.quality_disabled` property (added 1 day ago in PR #45 — net-zero churn).

#### `cognitive_castle/soar_bridge.py`

Remove the `if not cfg.soar_enabled: return hits unchanged` early-return. The bridge now runs whenever `_stage_5_soar` is called (which mode-dispatch already gates).

#### `cognitive_castle/quality_rerank.py`

Docstring update only — remove references to `cfg.quality_disabled`.

#### `cognitive_castle/judge.py`

No code changes (error surfacing happens in the searcher wrapper).

#### `CLAUDE.md`

Replace the entire Stage 4+5 block at `CLAUDE.md:184-194` (starts `├── Stage 4 + Stage 5 (optional, composable...` and ends with the `(requires both --llm-rerank AND --soar-boost on; loud sys.exit(2)...)` line) and the Stage 6 line at `CLAUDE.md:195` (starts `├── Stage 6 (ON by default, opt-out via --no-quality-rerank...`) with the new mode block.

New block to substitute:

```
    ├── Stage 4-6 (gated by --mode):
    │     ├── --mode fast      → Stage 3 only
    │     ├── --mode standard  → Stage 3 + Stage 6 (quality rerank)
    │     ├── --mode boosted   → Stage 3 + Stage 5 (SOAR boost-tags) + Stage 6
    │     └── --mode max       → Stage 3 + Stage 4 (LLM judge) + Stage 5 + Stage 6   ← default
    │           Stage 4 graceful-fallback: identity order on any LLM failure; surfaces via JUDGE audit line.
```

Plan-time grep: search the file for any remaining `--llm-rerank`, `--soar-boost`, `--soar-first`, `--no-quality-rerank`, `CASTLE_SOAR_ENABLED`, `CASTLE_QUALITY_DISABLED` references and delete them. None should remain after the substitution.

---

## 3. Testing strategy

### Scope

The consolidation is a flag-shape refactor. The four pipeline stages (3 / 4 / 5 / 6) keep their existing logic and existing tests. What we test here is the new **dispatch surface** — that `--mode` correctly selects which stages run, that removed flags and env vars no longer have effect, that the JUDGE audit line surfaces success/failure correctly, and that programmatic callers behave identically to CLI/MCP callers.

### Test surface changes

| File | Delete | Update | Add |
|---|--:|--:|--:|
| `tests/test_pipeline_order.py`             | 2  | 12 | 2 |
| `tests/test_cli.py`                        | 6  | 8  | 3 |
| `tests/test_mcp_server.py`                 | 3  | 6  | 3 |
| `tests/test_config.py`                     | 6  | 0  | 1 |
| `tests/test_searcher.py`                   | 0  | 4  | 3 |
| `tests/test_quality_rerank.py`             | 1  | 2  | 0 |
| `tests/test_soar_bridge.py`                | 1  | 1  | 0 |
| `tests/test_judge.py`                      | 0  | 0  | 4 |
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

`_mock_cfg` and `_mock_cfg_top_n_3` are pytest fixtures defined at the top of `test_pipeline_order.py` and `test_judge.py` (or once in `conftest.py` and reused). Note: the existing `_mock_cfg` in `test_judge.py:10` is a plain function (no `@pytest.fixture` decorator) — it must be redefined as a fixture for Section 3's tests to collect:

```python
# In tests/conftest.py (preferred — shared between test files):
@pytest.fixture
def _mock_cfg():
    cfg = SimpleNamespace()
    cfg.llm_model = "qwen3.5:latest"
    cfg.llm_judge_top_n = 10
    return cfg

@pytest.fixture
def _mock_cfg_top_n_3(_mock_cfg):
    _mock_cfg.llm_judge_top_n = 3
    return _mock_cfg
```

If `_mock_cfg` is redefined as a fixture in `conftest.py`, the existing plain-function caller at `test_judge.py:10` and its call sites must be updated in the same commit — turning function calls (`_mock_cfg()`) into fixture parameter references.

**2. Mode ordering in `max`** — `tests/test_pipeline_order.py`

```python
def test_max_mode_calls_stages_in_order_4_5_6(_mock_cfg):
    calls = []
    # Stage 4 sig: (query, reranked, cfg)         — return reranked unchanged
    # Stage 5 sig: (reranked, cfg, query=...)     — return reranked unchanged
    # Stage 6 sig: (reranked, cfg)                — return reranked unchanged
    with (
        patch("cognitive_castle.searcher._stage_4_judge",
              side_effect=lambda q, r, c: calls.append("4") or r),
        patch("cognitive_castle.searcher._stage_5_soar",
              side_effect=lambda r, c, query="": calls.append("5") or r),
        patch("cognitive_castle.searcher._stage_6_quality",
              side_effect=lambda r, c: calls.append("6") or r),
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

**6. MCP mode validation (3 tests)** — `tests/test_mcp_server.py`

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

**7. Config: removed properties (parametrized)** — `tests/test_config.py`

```python
@pytest.mark.parametrize("attr", ["soar_enabled", "quality_disabled"])
def test_removed_config_properties_are_absent(attr):
    cfg = CognitiveCastleConfig(palace_path="/tmp/p")
    assert not hasattr(cfg, attr)
```

Six existing tests around these two properties are deleted.

**8. Programmatic `mode=` parity (3 tests)** — `tests/test_searcher.py`

```python
def _mock_recall_layer():
    """Helper: patches Stage 1-3 to return a fixed reranked list of 3 hits."""
    fake_hits = [(f"d{i}", {"text": f"t{i}", "score": 1.0 - i * 0.1}) for i in range(3)]
    return patch(
        "cognitive_castle.searcher._stage_3_rerank",
        return_value=fake_hits,
    )

def test_search_memories_default_mode_runs_all_stages(palace_path):
    """Programmatic callers get max by default — closes the PR #45 P2 gap."""
    with (
        _mock_recall_layer(),
        patch("cognitive_castle.searcher._stage_4_judge",
              side_effect=lambda q, r, c: r) as j,
        patch("cognitive_castle.searcher._stage_5_soar",
              side_effect=lambda r, c, query="": r) as s,
        patch("cognitive_castle.searcher._stage_6_quality",
              side_effect=lambda r, c: r) as q,
    ):
        searcher.search_memories(query="q", palace_path=palace_path)
    assert j.called and s.called and q.called

def test_search_memories_mode_fast_skips_all_optional_stages(palace_path):
    with (
        _mock_recall_layer(),
        patch("cognitive_castle.searcher._stage_4_judge") as j,
        patch("cognitive_castle.searcher._stage_5_soar")  as s,
        patch("cognitive_castle.searcher._stage_6_quality") as q,
    ):
        searcher.search_memories(query="q", palace_path=palace_path, mode="fast")
    assert not j.called and not s.called and not q.called

def test_search_memories_invalid_mode_raises(palace_path):
    with _mock_recall_layer():
        with pytest.raises(ValueError, match="invalid mode"):
            searcher.search_memories(query="q", palace_path=palace_path, mode="full")
```

`palace_path` is the existing fixture in `tests/conftest.py` (returns a string path to an empty palace dir).

**Plan-time verification:** `_mock_recall_layer` patches `cognitive_castle.searcher._stage_3_rerank`. The actual function name in `searcher.py` may differ (`_stage_3`, `_rerank`, `cross_encoder_rerank`, etc.). Before writing this test, grep `searcher.py` for the Stage 3 rerank function and update the patch path. Same applies to the `_stage_4_judge`, `_stage_5_soar`, `_stage_6_quality` patch paths used throughout Section 3 — if any of these helpers have different names in the current code, update consistently across all tests.

Test 8.1 explicitly closes the P2 review gap flagged on PR #45 — programmatic callers no longer execute Stage 6 silently.

**9. JUDGE audit line — happy + error + top_n preservation (3 tests)** — `tests/test_judge.py`

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

def test_judge_preserves_hits_beyond_top_n(_mock_cfg_top_n_3):
    """Spec changes _stage_4_judge to preserve reranked[top_n:] (live code
    truncates). Lock the new behavior: with 5 hits and top_n=3, output keeps
    all 5 — top-3 reordered, hits 4 and 5 untouched at the end."""
    fake_reorder = [2, 0, 1]
    with patch("cognitive_castle.judge.judge", return_value=fake_reorder):
        reranked = [(f"d{i}", {"text": f"t{i}"}) for i in range(5)]
        out = searcher._stage_4_judge("q", reranked, _mock_cfg_top_n_3)
    assert len(out) == 5
    # Top-3 reordered:
    assert [r[0] for r in out[:3]] == ["d2", "d0", "d1"]
    # Tail preserved in original order:
    assert [r[0] for r in out[3:]] == ["d3", "d4"]
```

`_mock_cfg_top_n_3` is a sibling fixture identical to `_mock_cfg` but with `llm_judge_top_n=3` so the truncation boundary is testable.

**Behavior change note:** Live `_stage_4_judge` (`searcher.py:410-414`) returns `[judge_pool[i] for i in new_order]` — discarding `reranked[top_n:]`. The spec deliberately changes this to preserve the tail. The docstring at `searcher.py:401-403` ("the rest are discarded — same behavior as the inline block this replaces") must be updated to reflect the new "tail preserved" behavior.

Edge case: empty `reranked` returns `[]` immediately; no audit line emitted; no test crash. Implicitly covered by the existing `test_searcher_handles_empty_hits` integration test.

This brings test_judge.py additions to 4 (was 3): success-reorder, failure-fallback, top_n preservation, slow smoke. Update the surface table accordingly.

**10. Slow smoke (LLM end-to-end)** — `tests/test_judge.py`, marked `@pytest.mark.slow`

Both the helper and the fixture must be defined alongside the test (neither exists today):

```python
def _ollama_reachable() -> bool:
    """True if Ollama is responding on localhost:11434."""
    import urllib.request, urllib.error
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
        return True
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False

@pytest.fixture
def real_palace_fixture(palace_path):
    """A palace seeded with three drawers so search returns enough hits to
    exercise Stage 4."""
    from cognitive_castle import miner
    # Seed three drawers with text the judge can reorder.
    miner.add_drawer(palace_path, wing="test", room="r1", text="Retrieval weights: dense 0.5, sparse 0.3, kg 0.2.")
    miner.add_drawer(palace_path, wing="test", room="r1", text="We chose recency tau of 30 days.")
    miner.add_drawer(palace_path, wing="test", room="r1", text="Unrelated content about cooking pasta.")
    return palace_path

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

Plan-time verification: the seeding call (`miner.add_drawer`) is illustrative — replace with whatever helper Castle's existing test suite uses to add drawers (grep `tests/` for `add_drawer` or look at how `seeded_collection` fixture builds its content). Catches: Ollama URL changes, default-model-not-installed regressions, prompt template breakage. Excluded from CI; runs locally before PR merge.

### Coverage targets

- `searcher._apply_optional_stages` mode-dispatch: **100% branch coverage** (4 modes × parametrized test).
- `searcher._stage_4_judge`: **≥ 90% line coverage** (happy + error paths).
- `cli.build_parser()` search subparser block: **100% line coverage**.
- `mcp_server.tool_search` mode-validation block: **100% line coverage**.

### Risk register

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| 1 | `_apply_optional_stages` callers in `_new_pipeline_search` get out-of-sync signatures | Medium | Signature change + caller updates in a single commit; grep-verify all callers compile before commit. |
| 2 | Slow smoke passes locally but Ollama default model differs in CI | Low | Marked `@pytest.mark.slow`, excluded from CI. Unit tests under #10 catch success/error shapes deterministically. |
| 3 | Programmatic callers in third-party plugins break on missing `mode=` kwarg | Very Low | `mode` defaults to `"max"` in `search_memories()` signature — no caller is required to pass it. |
| 4 | `cfg.soar_enabled` deletion + `soar_bridge.py` early-return removal must land together | Medium | Same commit. If `config.py` change lands first, any test that reaches `_stage_5_soar` raises `AttributeError`. Grep `soar_enabled` across the repo before the deletion commit. |

### Non-goals

- Re-testing Stage 3/4/5/6 internals.
- Performance regression tests (mode latencies match Section 1 table by construction).
- Migration script for old saved CLI invocations (single-user system).

---

## 4. Acceptance criteria

- All 16 new tests pass.
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

---

## 6. Out of scope — follow-up PR

The default LLM model swap (`cmd_init` `--llm-model` default and `config.py:476` fallback: `"gemma3:4b"` → `"qwen3.5:latest"`) was originally scoped here but is being split out. Rationale: `gemma3:4b` is not in the Ollama registry; the user's installed models include `qwen3.5:latest` but not `gemma3:4b`. The docstring at `config.py:476` already flags this.

Splitting keeps this PR's diff focused on flag-shape changes and makes the LLM-default change independently revertable. Suggested follow-up commit:

```
fix(config): default cmd_init --llm-model to qwen3.5:latest

gemma3:4b is not in the Ollama registry. qwen3.5:latest is one of the
user's installed models and the spec audit found this discrepancy
during the search-mode consolidation review.
```

Scope: change three lines (argparse default + body fallback + config.py default) and one regression test (`test_cmd_init_llm_model_default_is_qwen35` from the original spec — moved to the follow-up PR).
