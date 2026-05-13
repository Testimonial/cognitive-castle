# LLM-as-judge Stage 4 (opt-in) — Design Spec

**Date:** 2026-05-13
**Status:** Approved, ready for implementation plan
**Umbrella:** SOTA retrieval upgrade — PR #3 of 4 (PR #1 bge-m3 merged at `2118d1df`; PR #2 mxbai-rerank-large-v2 deferred for multilingual reasons)

## Background

Castle's current retrieval pipeline ends at Stage 3 (cross-encoder rerank). The cross-encoder (`bge-reranker-v2-m3` on GPU, `bge-reranker-base` on CPU) does most of the relevance-judgement heavy lifting. For Castle's published benchmarks this gets 96.6% R@5 raw on LongMemEval — strong but not perfect.

For the last few percent — and especially for queries where lexical / semantic similarity isn't enough (subtle intent, implicit references, multi-hop reasoning) — an LLM-as-judge step can re-rank Stage 3's top candidates using actual language understanding. This is well-studied in the RAG literature: LLM rerankers consistently win on hard examples at the cost of 1-2s latency per query.

Castle already has the infrastructure: `cognitive_castle/llm_client.py` exposes a provider abstraction (`OllamaProvider`, `OpenAICompatProvider`, `AnthropicProvider`) with a uniform `classify(system, user, json_mode=True) -> LLMResponse` interface. The default provider is Ollama with `gemma3:e4b` — local-first, no API key required, runs on consumer GPU. BYOK Anthropic/OpenAI/Google work transparently for users who configure them.

This spec adds an optional Stage 4 to the pipeline. **Opt-in only.** Default behavior is identical to today's. The capability exists for users who want to spend 1-2s for higher precision on high-stakes queries.

## Umbrella context

| # | Sub-project | Status |
|---|---|---|
| 1 | bge-m3 unblock + migration | **Merged at `2118d1df`** |
| 2 | mxbai-rerank-large-v2 swap | **Deferred 2026-05-12** — mxbai is English-trained; Castle's multilingual default (bge-reranker-v2-m3) is the right choice for this user's Czech/English data |
| 3 | LLM-as-judge Stage 4 | **THIS SPEC** |
| 4 | Fusion rules engine | Future |

## Goal

Add an optional Stage 4 to the retrieval pipeline that asks the local LLM to re-rank Stage 3's top-10 candidates. Triggered by:
- `castle search ... --llm-rerank` (CLI flag)
- `llm_rerank: true` (MCP `search_memories` tool param)

No default change. The capability is fully opt-in; users who never pass the flag get exactly today's behavior.

## Non-goals

- **Changing the default to always-LLM-rerank.** Latency cost (1-2s) makes this unsuitable as a default; opt-in is the right primitive.
- **Per-query external-provider privacy warning.** Castle's `castle init` already prints a privacy notice when BYOK is configured; reprinting on every search is paternalistic noise. The fact that `--llm-rerank` invokes the configured LLM (which may be external if BYOK) is documented in the README.
- **A separate `judge_model` config knob.** The existing `llm_client.py` provider config is reused as-is. Users who want a different LLM for judging would need a future PR (or just switch their global provider).
- **Caching judged results.** Same query → same rerank order is not guaranteed (LLMs are nondeterministic at non-zero temperature). YAGNI for now.
- **Touching PR #2 (mxbai reranker swap) or PR #4 (fusion rules).**

## Architecture

```
Query → Stage 1 (recall) → Stage 2 (fusion) → Stage 3 (cross-encoder rerank)
                                                            │
                                              ┌─ if llm_rerank=False (default) ─→ return top-n_results
                                              │
                                              └─ if llm_rerank=True ─→ Stage 4 (LLM judge) ─→ reorder ─→ return top-n_results
```

**New module: `cognitive_castle/judge.py`** (~80 LOC). Mirrors the structure of `cognitive_castle/reranker.py`:

- Public entry point: `judge(query: str, candidates: list[str], cfg) -> list[int]`
- Returns: LLM-preferred ordering of candidate indices (e.g. `[3, 1, 5, 0, 2, 4, 6, 7, 8, 9]` when the LLM thinks candidate 3 is most relevant)
- Internally: builds prompt → `llm_client.classify(system, user, json_mode=True)` → parses JSON → validates → returns indices
- On any failure: prints `[judge] <reason>: falling back to cross-encoder ordering` to stderr, returns identity ordering (`list(range(len(candidates)))`). Search continues, user sees the degradation.

**Pipeline integration** in `searcher.py`:
- Both `search()` (CLI) and `search_memories()` (MCP) gain `llm_rerank: bool = False` param.
- After Stage 3 (around current line 422), if `llm_rerank=True`, take top-`cfg.llm_judge_top_n` candidates, call `judge.judge(query, docs, cfg)`, reorder by returned indices, slice to `n_results`.

**Config** in `config.py`: new `llm_judge_top_n` property (default 10, env `CASTLE_LLM_JUDGE_TOP_N`). Pattern matches existing `reranker_k_interactive` / `reranker_k_hook` knobs at `config.py:392-433`.

## Components (file-level changes)

| File | Change | LOC |
|---|---|---|
| `cognitive_castle/judge.py` (new) | Public `judge(query, candidates, cfg) -> list[int]`. Builds prompt, calls llm_client, parses + validates JSON. Identity-order fallback with stderr warning on any failure. Mirrors `reranker.py`. | +80 |
| `cognitive_castle/searcher.py` | Add `llm_rerank: bool = False` param to both `search()` and `search_memories()`. Thread through internal pipeline. After current line 422 (Stage 3 sort), if enabled: take top-`cfg.llm_judge_top_n` from reranked, call `judge.judge`, reorder, slice. | +20 |
| `cognitive_castle/config.py` | New `llm_judge_top_n` property (default 10, env `CASTLE_LLM_JUDGE_TOP_N`). Pattern matches `reranker_k_interactive` at `config.py:392-413`. | +20 |
| `cognitive_castle/cli.py` | Add `--llm-rerank` flag (store_true, default False) to the `castle search` subparser. Pass through to `search(..., llm_rerank=args.llm_rerank)`. Help text mentions 1-2s latency cost + uses configured LLM provider (default gemma3:e4b via Ollama). | +10 |
| `cognitive_castle/mcp_server.py` | Add optional `llm_rerank: bool = False` param to the `search_memories` MCP tool handler. Update the JSON schema in the `TOOLS` dict. Pass through to `search_memories(..., llm_rerank=...)`. | +15 |
| `tests/test_judge.py` (new) | 7 unit tests for `judge.judge()`: happy path, malformed JSON, missing key, wrong count, duplicate indices, LLM error, empty candidates. All use a mock LLM. | +120 |
| `tests/test_searcher.py` (existing) | 3 integration tests: stage 4 NOT called when `llm_rerank=False`; stage 4 called once with top-`llm_judge_top_n` when True; identity fallback preserves Stage 3 order. | +60 |
| `tests/test_cli.py` (existing) | 1 test: `--llm-rerank` flag propagates to `search(llm_rerank=True)`. | +20 |
| `README.md` | Append `--llm-rerank` subsection inside the existing "Going further" block (added by PR #1). Include: when to use, 1-2s latency cost, "uses configured LLM (gemma3:e4b via Ollama by default; BYOK Anthropic/OpenAI/Google supported)". | +20 |
| `CLAUDE.md` | Update the retrieval pipeline diagram (line 179 area) to show optional Stage 4. | +5 |

**Total:** ~370 LOC across 1 new module, 1 new test file, 8 existing files.

## Data flow

### Default path (`llm_rerank=False`, today's behavior — unchanged)

```
search_memories(query, ..., llm_rerank=False, n_results=5)
  → Stage 1 (parallel recall)
  → Stage 2 (weighted RRF + recency)
  → Stage 3 (cross-encoder rerank)
  → return top-5
```

### Opt-in path (`llm_rerank=True`)

```
search_memories(query, ..., llm_rerank=True, n_results=5)
  → Stage 1-2-3 identical to default
  → top_k_rows = top-10 from Stage 3 (cfg.llm_judge_top_n = 10)
  → docs = [first 400 chars of each row's text]  # truncation keeps prompt tight
  → judge.judge(query, docs, cfg)
      → build prompts (see "LLM contract" below)
      → llm_client.classify(system, user, json_mode=True) → LLMResponse
      → json.loads(response.text)
      → validate: dict with key "ranked_indices", value is list, length 10, unique ints in range(10)
      → on any failure: stderr warning, return list(range(10))
      → on success: return parsed list
  → reorder top_k_rows by returned indices
  → slice to n_results (5)
  → return
```

### LLM prompt contract

**System prompt** (exact text):

```
You are a retrieval re-ranking assistant. Given a user query and 10 candidate document snippets, return the indices of the candidates in order from most to least relevant. Output ONLY JSON in this exact shape: {"ranked_indices": [I0, I1, ..., I9]} where each I is the original 0-based candidate index. Each index appears exactly once. No prose, no explanation.
```

**User prompt** (template — populated at judge call):

```
Query: <query>

Candidates:
[0] <text 0 truncated to 400 chars>
[1] <text 1 truncated to 400 chars>
...
[9] <text 9 truncated to 400 chars>
```

### Response validation (all must hold or fallback fires)

1. `response.text` parses as JSON
2. Parsed value is a `dict`
3. Key `ranked_indices` is present
4. Value is a `list`
5. `len(list) == len(candidates)`
6. Every element is an `int`
7. Set of elements equals `set(range(len(candidates)))` (no duplicates, no out-of-range, all indices covered)

Any failure → identity-order fallback with stderr message `[judge] <specific reason>: falling back to cross-encoder ordering`.

### Truncation

Each candidate snippet is truncated to **400 characters** before being inserted into the user prompt. Hardcoded constant in `judge.py`; not a config knob (YAGNI — promote to config only if benchmarks show it matters).

Rationale: 10 candidates × 400 chars = 4000 chars of candidate context + ~200 char query + ~300 char system prompt = ~4500 chars total. Comfortably fits in any local LLM context window (gemma3:e4b is 8K).

## Error handling

| Failure | Behavior |
|---|---|
| Ollama not running | `LLMError("Cannot reach http://localhost:11434")`. `judge.judge` catches, stderr message, returns identity ordering. Search returns Stage 3 ordering. |
| LLM timeout (120s default in `llm_client`) | Same path. |
| LLM returns non-JSON text | Caught at `json.loads`. Same fallback path: `[judge] malformed JSON response: <first 100 chars>: falling back to cross-encoder ordering`. |
| LLM returns JSON but missing `ranked_indices` key | Validation step 3 fails. Same fallback. |
| LLM returns indices that aren't valid (duplicates, out of range, wrong count, non-int) | Validation steps 4-7 fail. Same fallback. |
| `llm_rerank=False` (default) | Stage 4 never invoked. Performance + behavior identical to today. |
| `candidates` is empty list | `judge.judge` returns `[]` immediately without LLM call. Stage 4 short-circuit. |
| `len(candidates) == 1` | Returns `[0]` immediately without LLM call. (Single candidate has nothing to rerank.) |
| BYOK provider configured (Anthropic/OpenAI/Google) | Candidate snippets are sent to that provider. No per-call warning. `castle init` already printed the privacy notice when BYOK was configured. |

**Privacy note (acceptance #X):** When `--llm-rerank` is enabled AND the configured LLM provider is external (per `LLMProvider.is_external_service` at `llm_client.py:150-162`), candidate snippets DO leave the local machine. The user opted into BYOK at `castle init` time; reprinting privacy notices per-search is noise. The README's "Going further: --llm-rerank" subsection states this explicitly so the behavior is discoverable in docs, not just in code.

## Testing

### New file: `tests/test_judge.py`

```python
import json
from unittest.mock import MagicMock
import pytest
from cognitive_castle.judge import judge
from cognitive_castle.llm_client import LLMError, LLMResponse


def _mock_cfg():
    cfg = MagicMock()
    cfg.llm_judge_top_n = 10
    return cfg


def _mock_provider(text):
    """Return a provider that returns the given text from classify()."""
    provider = MagicMock()
    provider.classify.return_value = LLMResponse(
        text=text, model="gemma3:e4b", provider="ollama", raw={}
    )
    return provider


def test_judge_returns_llm_ordering_on_valid_json(monkeypatch):
    provider = _mock_provider(
        json.dumps({"ranked_indices": [3, 1, 5, 0, 2, 4, 6, 7, 8, 9]})
    )
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("test query", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == [3, 1, 5, 0, 2, 4, 6, 7, 8, 9]


def test_judge_falls_back_to_identity_on_malformed_json(monkeypatch, capsys):
    provider = _mock_provider("this is not json")
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == list(range(10))
    assert "falling back to cross-encoder ordering" in capsys.readouterr().err


def test_judge_falls_back_on_missing_key(monkeypatch, capsys):
    provider = _mock_provider(json.dumps({"foo": "bar"}))
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == list(range(10))
    assert "ranked_indices" in capsys.readouterr().err.lower()


def test_judge_falls_back_on_wrong_count(monkeypatch, capsys):
    provider = _mock_provider(json.dumps({"ranked_indices": [0, 1, 2]}))
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == list(range(10))


def test_judge_falls_back_on_duplicate_indices(monkeypatch, capsys):
    provider = _mock_provider(json.dumps({"ranked_indices": [3] * 10}))
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == list(range(10))


def test_judge_falls_back_on_llm_error(monkeypatch, capsys):
    provider = MagicMock()
    provider.classify.side_effect = LLMError("Cannot reach http://localhost:11434")
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == list(range(10))
    err = capsys.readouterr().err
    assert "Cannot reach" in err
    assert "falling back" in err


def test_judge_empty_candidates_returns_empty_without_llm_call(monkeypatch):
    provider = MagicMock()
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    assert judge("q", [], _mock_cfg()) == []
    provider.classify.assert_not_called()
```

### Extension to `tests/test_searcher.py`

```python
def test_search_memories_llm_rerank_false_skips_stage_4(monkeypatch, ...):
    spy = MagicMock()
    monkeypatch.setattr("cognitive_castle.judge.judge", spy)
    search_memories(query="x", palace_path=..., llm_rerank=False)
    spy.assert_not_called()


def test_search_memories_llm_rerank_true_calls_judge(monkeypatch, ...):
    spy = MagicMock(return_value=[2, 1, 0])
    monkeypatch.setattr("cognitive_castle.judge.judge", spy)
    result = search_memories(query="x", palace_path=..., llm_rerank=True, n_results=3)
    spy.assert_called_once()
    # First positional arg = query
    assert spy.call_args[0][0] == "x"
    # result ordering follows judge's [2, 1, 0]


def test_search_memories_llm_rerank_identity_fallback_preserves_stage3_order(monkeypatch, ...):
    monkeypatch.setattr("cognitive_castle.judge.judge", lambda *a, **kw: list(range(10)))
    # result identical to llm_rerank=False on same fixture
```

(Exact fixture setup follows existing test_searcher.py patterns; implementation plan will spell out the exact code.)

### Extension to `tests/test_cli.py`

```python
def test_search_cli_llm_rerank_flag_propagates(monkeypatch):
    spy = MagicMock()
    monkeypatch.setattr("cognitive_castle.cli.search", spy)
    # Simulate `castle search "x" --llm-rerank --palace /tmp/p`
    # Verify spy called with llm_rerank=True
```

### Default suite

No existing tests change. All current tests pass unchanged.

## Acceptance criteria

The PR is mergeable when ALL hold:

1. `pytest tests/test_judge.py -v` — all 7 unit tests pass
2. `pytest tests/test_searcher.py -v -k llm_rerank` — 3 integration tests pass
3. `pytest tests/test_cli.py -v -k llm_rerank` — CLI flag test passes
4. Default test suite: `pytest tests/ -v --ignore=tests/benchmarks` — no NEW regressions (pre-existing CI-UNSTABLE failures acceptable)
5. `castle search --help` shows `--llm-rerank` flag with help text that includes:
   - "1-2s extra latency" (the cost)
   - "uses configured LLM provider (default: gemma3:e4b via Ollama)" (the mechanism)
6. MCP `search_memories` tool schema (via `castle-mcp` `tools/list` JSON-RPC) shows `llm_rerank` as optional `boolean` property with `default: false`
7. `ruff check .` and `ruff format --check .` clean on all 8 touched files
8. **Live smoke (happy path):**
   ```bash
   # Ollama running with gemma3:e4b
   castle search "test query" --llm-rerank --palace ~/.castle/palace
   ```
   Completes in <5s, returns ranked results, no stderr warnings.
9. **Live smoke (Ollama-down fallback):**
   ```bash
   # Stop Ollama
   sudo systemctl stop ollama
   castle search "test query" --llm-rerank --palace ~/.castle/palace
   ```
   Completes successfully, returns Stage 3 ordering, stderr contains `[judge] ... falling back to cross-encoder ordering`.
10. README has `--llm-rerank` subsection inside the existing "Going further" block, including: when to use, 1-2s latency cost, mention of configured LLM provider, mention that BYOK external providers receive snippets (privacy note).
11. CLAUDE.md retrieval pipeline diagram shows the optional Stage 4 path.
12. **Default behavior unchanged:** `castle search "x"` and MCP `search_memories({"query": "x"})` (both without `--llm-rerank` / `llm_rerank`) produce byte-identical output before and after this PR.

## Out of scope (explicit non-goals revisited)

- Always-on LLM rerank (latency makes this wrong as default)
- Separate `judge_model` config knob (reuse existing LLM provider config)
- Per-search external-provider privacy warning (covered at `castle init`)
- Result caching
- Changes to reranker (PR #2 — deferred for multilingual reasons)
- Changes to fusion (PR #4 — future)

## Spec self-review (2026-05-13)

1. **Placeholders:** None. All test code is concrete (mock setup + assertions shown). Pipeline integration point is `searcher.py:422-ish`; exact line will be discovered at plan-writing time.
2. **Internal consistency:** Architecture, Components, Data Flow, Error Handling, Testing, and Acceptance all reference the same:
   - `cognitive_castle/judge.py` new module
   - `judge(query, candidates, cfg) -> list[int]` signature
   - 10-candidate input default (`cfg.llm_judge_top_n`)
   - 400-char hardcoded truncation
   - JSON contract with `ranked_indices` key
   - Identity-order fallback on every failure mode
   - No new env-var for snippet length
3. **Scope:** Single sub-project (LLM-as-judge as opt-in Stage 4). The defer/skip decisions for PR #2 (mxbai swap) and PR #4 (fusion rules) are restated in the umbrella table and Out-of-Scope.
4. **Ambiguity:** Opt-in semantics ("default=False, never silently invoked") stated in Goal, Architecture, Data Flow, Error Handling, and Acceptance #12. Privacy stance ("no per-search warning; documented at init + README") stated in Non-goals AND Error Handling AND Acceptance #10.
5. **Empirical grounding:** Existing infrastructure verified: `llm_client.py` provides `classify(system, user, json_mode=True)`; `reranker.py` is the structural template for `judge.py`; `config.py:392-433` has the pattern for the new `llm_judge_top_n` property.
6. **Privacy explicit:** BYOK external-provider concern called out in Non-goals, Error Handling table, and Acceptance #10 — three places, consistent framing.
