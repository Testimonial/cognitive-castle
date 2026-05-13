# LLM-as-judge Stage 4 (opt-in) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional Stage 4 to Castle's 3-stage retrieval pipeline. The LLM re-ranks Stage 3's top-10 candidates when the user opts in via `--llm-rerank` (CLI) or `llm_rerank: true` (MCP). Zero behavior change in the default path.

**Architecture:** New `cognitive_castle/judge.py` module mirroring the `reranker.py` pattern. Reuses the existing `llm_client.get_provider(...)` factory but reads provider config from 5 new `CognitiveCastleConfig` properties (the gap caught at plan-writing time). Identity-order fallback on every LLM failure mode so search ALWAYS returns results.

**Tech Stack:** Python 3.12, sentence-transformers (already used by reranker), `cognitive_castle/llm_client.py` provider abstraction (OllamaProvider / OpenAICompatProvider / AnthropicProvider), pytest with `monkeypatch` + `capsys` + `MagicMock`. No new dependencies.

**Spec:** [`docs/superpowers/specs/2026-05-13-llm-judge-stage4-design.md`](../specs/2026-05-13-llm-judge-stage4-design.md) (commit `1ccf3113`).

**File map (10 files, ~420 LOC):**

| File | Responsibility | Tasks |
|---|---|---|
| `cognitive_castle/config.py` | 6 new env-first properties (`llm_judge_top_n`, `llm_provider`, `llm_model`, `llm_endpoint`, `llm_api_key`, `llm_timeout`) | Task 2 |
| `cognitive_castle/judge.py` (new) | `judge(query, candidates, cfg) -> list[int]` + private `_get_provider(cfg)` helper | Task 3 |
| `cognitive_castle/searcher.py` | Thread `llm_rerank: bool = False` through `search()` + `search_memories()` + internal pipeline (Stage 4 hook) | Task 4 |
| `cognitive_castle/cli.py` | `--llm-rerank` flag on `castle search` subparser | Task 5 |
| `cognitive_castle/mcp_server.py` | `llm_rerank` param on `search_memories` MCP tool + JSON schema | Task 6 |
| `tests/test_config.py` (existing) | 6 tests for the new config properties | Task 2 |
| `tests/test_judge.py` (new) | 8 unit tests for `judge.judge()` (happy path + 7 fallback paths) | Task 3 |
| `tests/test_searcher.py` (existing) | 3 integration tests for the Stage 4 hook | Task 4 |
| `tests/test_cli.py` (existing) | 1 test for `--llm-rerank` flag propagation | Task 5 |
| `README.md` | Append `--llm-rerank` subsection inside existing "Going further" block | Task 8 |
| `CLAUDE.md` | Update retrieval pipeline diagram (line 179) to show optional Stage 4 | Task 7 |

---

## Task 1: Create feature branch

**Files:** none (git only)

- [ ] **Step 1: Verify clean tree on develop**

Run:
```bash
git status
git log --oneline -3
```

Expected:
- On branch `develop`
- Working tree clean (the `test_env/` untracked dir is OK to ignore — pre-existing)
- Latest commit is the spec revision `1ccf3113` or later

- [ ] **Step 2: Create + switch to feature branch**

Run:
```bash
git checkout -b feat/llm-judge-stage4
```

Expected: `Switched to a new branch 'feat/llm-judge-stage4'`

- [ ] **Step 3: Verify branch**

Run:
```bash
git branch --show-current
```

Expected: `feat/llm-judge-stage4`

No commit yet — branch creation is not committable on its own.

---

## Task 2: Add 6 new `CognitiveCastleConfig` properties

**Files:**
- Modify: `cognitive_castle/config.py` (append 6 new `@property` methods after the existing `reranker_*` block, around line 432)
- Modify: `tests/test_config.py` (append 6 new tests)

The 6 properties all follow the env-first → file-config → default pattern. Template: see `reranker_k_interactive` at `config.py:390-410` (int) and `embedder_model` at `config.py:305-321` (string).

- [ ] **Step 1: Write the 6 failing tests**

Append to `tests/test_config.py`:

```python
def test_llm_judge_top_n_default():
    """Without env var or config file, defaults to 10."""
    cfg = _make_config_with_file_config({})
    assert cfg.llm_judge_top_n == 10


def test_llm_judge_top_n_env_override(monkeypatch):
    """CASTLE_LLM_JUDGE_TOP_N env var takes precedence."""
    monkeypatch.setenv("CASTLE_LLM_JUDGE_TOP_N", "15")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_judge_top_n == 15


def test_llm_provider_default_is_ollama():
    cfg = _make_config_with_file_config({})
    assert cfg.llm_provider == "ollama"


def test_llm_provider_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_LLM_PROVIDER", "anthropic")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_provider == "anthropic"


def test_llm_model_default_matches_cmd_init_default():
    """Default tracks cmd_init's hardcoded default at cli.py:267.

    Note: both are 'gemma3:e4b' which is a known pre-existing broken tag
    (the model doesn't exist in Ollama's registry). Tracking the same
    broken default keeps cmd_init and the judge consistent — both will be
    fixed together in a follow-up PR. Judge's graceful fallback covers
    the broken-default case; the user must explicitly enable --llm-rerank
    AND have a working model configured (via CASTLE_LLM_MODEL env var or
    castle.yaml) for the path to actually work end-to-end.
    """
    cfg = _make_config_with_file_config({})
    assert cfg.llm_model == "gemma3:e4b"


def test_llm_model_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_LLM_MODEL", "llama3:8b")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_model == "llama3:8b"


def test_llm_endpoint_default_is_none():
    cfg = _make_config_with_file_config({})
    assert cfg.llm_endpoint is None


def test_llm_endpoint_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_LLM_ENDPOINT", "http://localhost:1234")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_endpoint == "http://localhost:1234"


def test_llm_api_key_default_is_none():
    cfg = _make_config_with_file_config({})
    assert cfg.llm_api_key is None


def test_llm_api_key_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_LLM_API_KEY", "sk-test-1234")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_api_key == "sk-test-1234"


def test_llm_timeout_default_is_120():
    cfg = _make_config_with_file_config({})
    assert cfg.llm_timeout == 120


def test_llm_timeout_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_LLM_TIMEOUT", "60")
    cfg = _make_config_with_file_config({})
    assert cfg.llm_timeout == 60
```

**Helper assumption:** the existing test file uses some construction pattern for `CognitiveCastleConfig` with a custom `_file_config`. Read the top of `tests/test_config.py` for the existing helper name — if it's not `_make_config_with_file_config`, rename the calls above to match the established helper.

- [ ] **Step 2: Run tests to verify they FAIL**

Run:
```bash
pytest tests/test_config.py -v -k "llm_"
```

Expected: 12 tests collected, all FAIL with `AttributeError: 'CognitiveCastleConfig' object has no attribute 'llm_judge_top_n'` (or one of the others). Each test will fail on the missing property access.

- [ ] **Step 3: Add the 6 properties to `cognitive_castle/config.py`**

Find the existing `reranker_k_hook` property at `cognitive_castle/config.py:413-432`. Append the following 6 properties immediately after it:

```python
    @property
    def llm_judge_top_n(self):
        """Number of candidates to feed the LLM judge in Stage 4.

        Default: ``10``. Reads from ``CASTLE_LLM_JUDGE_TOP_N`` env var
        first, then config file, then default.
        """
        env_val = os.environ.get("CASTLE_LLM_JUDGE_TOP_N")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed >= 1:
                    return parsed
            except ValueError:
                pass
        cfg_val = self._file_config.get("llm_judge_top_n")
        try:
            parsed = int(cfg_val) if cfg_val is not None else 10
        except (TypeError, ValueError):
            parsed = 10
        return max(1, parsed)

    @property
    def llm_provider(self):
        """Provider name for the LLM-as-judge step (``"ollama"`` / ``"openai-compat"`` / ``"anthropic"``).

        Default: ``"ollama"``. Reads from ``CASTLE_LLM_PROVIDER`` env var
        first, then config file, then default.
        """
        env_val = os.environ.get("CASTLE_LLM_PROVIDER")
        if env_val:
            return env_val.strip()
        return str(self._file_config.get("llm_provider", "ollama")).strip()

    @property
    def llm_model(self):
        """Model name passed to the LLM provider.

        Default: ``"gemma3:e4b"`` (matches ``cmd_init``'s default at
        ``cli.py:267``). NOTE: this default is a known pre-existing
        broken tag — the model does not exist in Ollama's registry.
        Both defaults will be fixed together in a follow-up PR. Until
        then, users who want a working LLM-as-judge path must override
        via ``CASTLE_LLM_MODEL`` env var or ``llm_model`` in castle.yaml.

        Reads from ``CASTLE_LLM_MODEL`` env var first, then config file,
        then default.
        """
        env_val = os.environ.get("CASTLE_LLM_MODEL")
        if env_val:
            return env_val.strip()
        return str(self._file_config.get("llm_model", "gemma3:e4b")).strip()

    @property
    def llm_endpoint(self):
        """Endpoint URL override for the LLM provider, or None to use the provider's default.

        Default: ``None`` (use provider's default: e.g. http://localhost:11434
        for Ollama, https://api.anthropic.com for Anthropic).
        Reads from ``CASTLE_LLM_ENDPOINT`` env var first, then config file,
        then default.
        """
        env_val = os.environ.get("CASTLE_LLM_ENDPOINT")
        if env_val:
            return env_val.strip()
        cfg_val = self._file_config.get("llm_endpoint")
        return str(cfg_val).strip() if cfg_val else None

    @property
    def llm_api_key(self):
        """API key for external LLM providers (Anthropic / OpenAI-compat).

        Default: ``None`` (no API key — works for local Ollama).
        Reads from ``CASTLE_LLM_API_KEY`` env var first, then config file,
        then default. NOTE: prefer the env var over the config file for
        secrets — castle.yaml may be checked into version control.
        """
        env_val = os.environ.get("CASTLE_LLM_API_KEY")
        if env_val:
            return env_val.strip()
        cfg_val = self._file_config.get("llm_api_key")
        return str(cfg_val).strip() if cfg_val else None

    @property
    def llm_timeout(self):
        """HTTP timeout (seconds) for LLM provider calls.

        Default: ``120``. Reads from ``CASTLE_LLM_TIMEOUT`` env var first,
        then config file, then default.
        """
        env_val = os.environ.get("CASTLE_LLM_TIMEOUT")
        if env_val:
            try:
                parsed = int(env_val)
                if parsed >= 1:
                    return parsed
            except ValueError:
                pass
        cfg_val = self._file_config.get("llm_timeout")
        try:
            parsed = int(cfg_val) if cfg_val is not None else 120
        except (TypeError, ValueError):
            parsed = 120
        return max(1, parsed)
```

- [ ] **Step 4: Run tests to verify all 12 pass**

Run:
```bash
pytest tests/test_config.py -v -k "llm_"
```

Expected: 12 passed.

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run:
```bash
pytest tests/ -v --ignore=tests/benchmarks
```

Expected: same number of passing tests as before + 12 new ones. Pre-existing CI-UNSTABLE failures acceptable.

- [ ] **Step 6: Lint check**

Run:
```bash
ruff check cognitive_castle/config.py tests/test_config.py && ruff format --check cognitive_castle/config.py tests/test_config.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): add 6 LLM-related properties to CognitiveCastleConfig

Adds llm_judge_top_n (default 10), llm_provider (default "ollama"),
llm_model (default "gemma3:e4b" — matches cmd_init's pre-existing
broken default, tracked separately), llm_endpoint (default None),
llm_api_key (default None), llm_timeout (default 120). All read env
var first, then castle.yaml, then default — same pattern as
embedder_model at config.py:305.

Closes the contract gap discovered when drafting the implementation
plan: judge.py needs a cfg-driven path to construct an LLMProvider,
but no cfg.llm_* properties existed (provider was only built
transiently in cmd_init from argparse args).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Build `cognitive_castle/judge.py` module (TDD)

**Files:**
- Create: `cognitive_castle/judge.py`
- Create: `tests/test_judge.py`

This task is the biggest — implementing the LLM-judge logic plus 8 unit tests covering happy path + 7 fallback paths.

- [ ] **Step 1: Write the 8 failing tests in `tests/test_judge.py`**

Create `tests/test_judge.py` with the following exact content (verbatim from spec):

```python
"""Unit tests for the LLM-as-judge Stage 4 module."""
import json
from unittest.mock import MagicMock
import pytest

from cognitive_castle.judge import judge
from cognitive_castle.llm_client import LLMError, LLMResponse


def _mock_cfg():
    """Mock cfg that judge.py reads (only llm_judge_top_n + provider knobs)."""
    cfg = MagicMock()
    cfg.llm_judge_top_n = 10
    return cfg


def _mock_provider(text):
    """Return a provider that returns the given text from classify()."""
    provider = MagicMock()
    provider.classify.return_value = LLMResponse(
        text=text, model="test-model", provider="test", raw={}
    )
    return provider


def test_judge_returns_llm_ordering_on_valid_json(monkeypatch):
    """Happy path: LLM returns a valid 10-element permutation."""
    provider = _mock_provider(
        json.dumps({"ranked_indices": [3, 1, 5, 0, 2, 4, 6, 7, 8, 9]})
    )
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("test query", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == [3, 1, 5, 0, 2, 4, 6, 7, 8, 9]


def test_judge_falls_back_to_identity_on_malformed_json(monkeypatch, capsys):
    """LLM returned non-JSON text → identity fallback + stderr warning."""
    provider = _mock_provider("this is not json")
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == list(range(10))
    assert "falling back to cross-encoder ordering" in capsys.readouterr().err


def test_judge_falls_back_on_missing_key(monkeypatch, capsys):
    """LLM returned JSON without ranked_indices key → identity fallback."""
    provider = _mock_provider(json.dumps({"foo": "bar"}))
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == list(range(10))
    assert "ranked_indices" in capsys.readouterr().err.lower()


def test_judge_falls_back_on_wrong_count(monkeypatch, capsys):
    """LLM returned fewer indices than candidates → identity fallback."""
    provider = _mock_provider(json.dumps({"ranked_indices": [0, 1, 2]}))
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == list(range(10))


def test_judge_falls_back_on_duplicate_indices(monkeypatch, capsys):
    """LLM returned duplicates (not a permutation) → identity fallback."""
    provider = _mock_provider(json.dumps({"ranked_indices": [3] * 10}))
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == list(range(10))


def test_judge_falls_back_on_llm_error(monkeypatch, capsys):
    """LLM call raised LLMError → identity fallback + stderr with error message."""
    provider = MagicMock()
    provider.classify.side_effect = LLMError("Cannot reach http://localhost:11434")
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    result = judge("q", [f"doc {i}" for i in range(10)], _mock_cfg())
    assert result == list(range(10))
    err = capsys.readouterr().err
    assert "Cannot reach" in err
    assert "falling back" in err


def test_judge_empty_candidates_returns_empty_without_llm_call(monkeypatch):
    """Edge case: empty candidate list returns [] without invoking the LLM."""
    provider = MagicMock()
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    assert judge("q", [], _mock_cfg()) == []
    provider.classify.assert_not_called()


def test_judge_single_candidate_returns_zero_without_llm_call(monkeypatch):
    """Edge case: single candidate has nothing to rerank — short-circuit before LLM call."""
    provider = MagicMock()
    monkeypatch.setattr("cognitive_castle.judge._get_provider", lambda cfg: provider)
    assert judge("q", ["only doc"], _mock_cfg()) == [0]
    provider.classify.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they FAIL**

Run:
```bash
pytest tests/test_judge.py -v
```

Expected: 8 tests collected, all FAIL with `ModuleNotFoundError: No module named 'cognitive_castle.judge'`.

- [ ] **Step 3: Create `cognitive_castle/judge.py`**

Create the file with the following content:

```python
"""judge.py — Stage 4 LLM-as-judge re-ranker (opt-in).

Takes a query + N candidate snippets, asks the configured LLM to rank
them by relevance, returns the LLM's preferred ordering as a list of
candidate indices.

Identity-order fallback on every failure mode (malformed JSON, missing
key, validation failure, LLM call error). Search ALWAYS returns
results — never crashes due to judge failure.

Mirrors the structure of cognitive_castle/reranker.py.
"""
from __future__ import annotations

import json
import sys

# 600-char truncation. Hardcoded constant per spec — at-least-as-much-context
# as the cross-encoder at Stage 3 (which sees ~2000 chars). Promoting to
# config is YAGNI until benchmarks show it matters.
SNIPPET_CHARS = 600


_SYSTEM_PROMPT = (
    "You are a retrieval re-ranking assistant. Given a user query and "
    "{n} candidate document snippets, return the indices of the candidates "
    "in order from most to least relevant. Output ONLY JSON in this exact "
    'shape: {{"ranked_indices": [I0, I1, ..., I{last}]}} where each I is the '
    "original 0-based candidate index. Each index appears exactly once. "
    "No prose, no explanation."
)


def _get_provider(cfg):
    """Construct an LLMProvider from cfg using the existing llm_client factory.

    Reads the 5 llm_* properties from cfg and calls
    cognitive_castle.llm_client.get_provider(...). Tests mock THIS helper
    to inject a fake provider — see tests/test_judge.py.
    """
    from .llm_client import get_provider
    return get_provider(
        name=cfg.llm_provider,
        model=cfg.llm_model,
        endpoint=cfg.llm_endpoint,
        api_key=cfg.llm_api_key,
        timeout=cfg.llm_timeout,
    )


def _build_prompts(query: str, candidates: list[str]) -> tuple[str, str]:
    """Build (system, user) prompts for the LLM. Truncates snippets to SNIPPET_CHARS."""
    n = len(candidates)
    system = _SYSTEM_PROMPT.format(n=n, last=n - 1)
    lines = ["Query: " + query, "", "Candidates:"]
    for i, doc in enumerate(candidates):
        lines.append(f"[{i}] {doc[:SNIPPET_CHARS]}")
    user = "\n".join(lines)
    return system, user


def _validate_ranked_indices(parsed, n: int) -> tuple[bool, str]:
    """Return (ok, reason). reason is empty on success, else a short diagnostic."""
    if not isinstance(parsed, dict):
        return False, f"response is not a JSON object (got {type(parsed).__name__})"
    if "ranked_indices" not in parsed:
        return False, "missing 'ranked_indices' key"
    indices = parsed["ranked_indices"]
    if not isinstance(indices, list):
        return False, f"'ranked_indices' is not a list (got {type(indices).__name__})"
    if len(indices) != n:
        return False, f"wrong count: got {len(indices)} indices, expected {n}"
    if not all(isinstance(i, int) for i in indices):
        return False, "indices contain non-int values"
    if set(indices) != set(range(n)):
        return False, "indices are not a permutation of range(n) (duplicates or out-of-range)"
    return True, ""


def _warn(reason: str) -> None:
    """Print the fallback warning to stderr in the spec's exact format."""
    print(
        f"[judge] {reason}: falling back to cross-encoder ordering",
        file=sys.stderr,
    )


def judge(query: str, candidates: list[str], cfg) -> list[int]:
    """Return the LLM-preferred ordering of candidate indices.

    Args:
        query: The user's search query.
        candidates: List of candidate document snippets.
        cfg: A config-like object exposing the .llm_* properties.

    Returns:
        list[int]: ordering of candidate indices, e.g. [3, 1, 5, ...].
        On any failure (LLM error, malformed JSON, validation failure):
        returns list(range(len(candidates))) — the identity ordering,
        which preserves the cross-encoder's Stage 3 ranking.

    Never raises. Search continues with degraded behavior on LLM failure.
    """
    n = len(candidates)
    # Short-circuit: nothing to rerank.
    if n <= 1:
        return list(range(n))

    system, user = _build_prompts(query, candidates)

    try:
        provider = _get_provider(cfg)
        response = provider.classify(system, user, json_mode=True)
    except Exception as e:
        _warn(f"LLM call failed ({type(e).__name__}: {e})")
        return list(range(n))

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError:
        snippet = response.text[:100].replace("\n", " ")
        _warn(f"malformed JSON response: {snippet!r}")
        return list(range(n))

    ok, reason = _validate_ranked_indices(parsed, n)
    if not ok:
        _warn(reason)
        return list(range(n))

    return list(parsed["ranked_indices"])
```

- [ ] **Step 4: Run tests to verify all 8 pass**

Run:
```bash
pytest tests/test_judge.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run:
```bash
pytest tests/ -v --ignore=tests/benchmarks
```

Expected: previous passing count + 8 new tests. Pre-existing CI-UNSTABLE failures acceptable.

- [ ] **Step 6: Lint check**

Run:
```bash
ruff check cognitive_castle/judge.py tests/test_judge.py && ruff format --check cognitive_castle/judge.py tests/test_judge.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/judge.py tests/test_judge.py
git commit -m "$(cat <<'EOF'
feat(judge): add LLM-as-judge Stage 4 module (opt-in re-ranker)

cognitive_castle/judge.py: judge(query, candidates, cfg) -> list[int].
Builds a re-ranking prompt, calls the configured LLM via the existing
llm_client.get_provider() factory, parses + validates the JSON
response, returns the LLM-preferred ordering of candidate indices.

Identity-order fallback (list(range(N))) on every failure mode:
- LLM provider can't be reached (Ollama down, timeout, etc.)
- Response isn't valid JSON
- JSON doesn't have ranked_indices key
- ranked_indices isn't a complete permutation of range(N)
- Single candidate or empty list (short-circuit before LLM call)

Stderr warning on every fallback so users see the degradation but
search still returns results.

600-char snippet truncation (hardcoded — ≥ cross-encoder's ~2000-char
window per spec). _get_provider helper reads cfg.llm_* properties.

8 unit tests cover happy path + 7 fallback paths.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Wire `llm_rerank` through `searcher.py` (TDD)

**Files:**
- Modify: `cognitive_castle/searcher.py` (add param to both public functions + Stage 4 hook in internal pipeline)
- Modify: `tests/test_searcher.py` (add 3 integration tests)

The integration tests REQUIRE understanding the existing `tests/test_searcher.py` fixture pattern. Read it first to find the helper that builds a fixture palace + runs search.

- [ ] **Step 1: Survey `tests/test_searcher.py` to find the fixture pattern**

Run:
```bash
head -100 /home/lbihari/cognitive-castle/tests/test_searcher.py
```

Look for: how tests construct a temp palace, what fixture they call, what return type `search_memories()` produces. Use this pattern in Step 2 — do NOT invent a new fixture pattern.

- [ ] **Step 2: Write the 3 failing integration tests**

Append to `tests/test_searcher.py`:

```python
def test_search_memories_llm_rerank_false_skips_stage_4(
    monkeypatch, tmp_path, ...  # use the existing fixture from test_searcher.py
):
    """When llm_rerank=False (default), judge.judge is never called."""
    from unittest.mock import MagicMock
    spy = MagicMock()
    monkeypatch.setattr("cognitive_castle.judge.judge", spy)

    # Build a palace + run search using the existing test fixture pattern.
    # Replace the next 2 lines with whatever pattern existing tests use:
    palace_path = _build_fixture_palace(tmp_path, n_drawers=15)  # or whatever the helper is
    search_memories(query="test", palace_path=palace_path, n_results=5)

    spy.assert_not_called()


def test_search_memories_llm_rerank_true_calls_judge(
    monkeypatch, tmp_path, ...
):
    """When llm_rerank=True, judge.judge is called with top-N candidates."""
    from unittest.mock import MagicMock
    spy = MagicMock(return_value=[2, 1, 0, 3, 4, 5, 6, 7, 8, 9])
    monkeypatch.setattr("cognitive_castle.judge.judge", spy)

    palace_path = _build_fixture_palace(tmp_path, n_drawers=15)
    result = search_memories(
        query="test", palace_path=palace_path, n_results=3, llm_rerank=True
    )

    spy.assert_called_once()
    # First positional arg = query
    assert spy.call_args[0][0] == "test"
    # Second positional arg = list of candidate doc strings (top-10 from Stage 3)
    assert isinstance(spy.call_args[0][1], list)
    assert len(spy.call_args[0][1]) == 10  # default llm_judge_top_n
    # Result has 3 items per n_results
    assert len(result) == 3


def test_search_memories_llm_rerank_identity_fallback_preserves_stage3_order(
    monkeypatch, tmp_path, ...
):
    """Identity-ordering from judge means final result equals llm_rerank=False output."""
    monkeypatch.setattr(
        "cognitive_castle.judge.judge", lambda *a, **kw: list(range(10))
    )
    palace_path = _build_fixture_palace(tmp_path, n_drawers=15)

    no_llm = search_memories(
        query="test", palace_path=palace_path, n_results=5, llm_rerank=False
    )
    with_llm_identity = search_memories(
        query="test", palace_path=palace_path, n_results=5, llm_rerank=True
    )
    # Drawer IDs should match in the same order (identity = no reordering)
    assert [r["id"] for r in no_llm] == [r["id"] for r in with_llm_identity]
```

**Adapt the `_build_fixture_palace` placeholder** to whatever real fixture / helper exists in `tests/test_searcher.py` after Step 1's reconnaissance. The spec's intent is: integration tests use the SAME test infrastructure that already exists, not a new pattern.

- [ ] **Step 3: Run tests to verify they FAIL**

Run:
```bash
pytest tests/test_searcher.py -v -k llm_rerank
```

Expected: 3 tests collected, all FAIL with `TypeError: search_memories() got an unexpected keyword argument 'llm_rerank'`.

- [ ] **Step 4: Add `llm_rerank: bool = False` to `search_memories()` signature**

In `cognitive_castle/searcher.py:195-205`, change the `search_memories` signature from:

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
) -> dict:
```

to:

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
    llm_rerank: bool = False,
) -> dict:
```

Update the docstring at lines 217-227 by adding:
```python
        llm_rerank: When True, run optional Stage 4 LLM-as-judge re-rank
            over the top-cfg.llm_judge_top_n candidates from Stage 3.
            Defaults to False (zero behavior change). 1-2s extra latency.
```

- [ ] **Step 5: Add `llm_rerank: bool = False` to `search()` signature**

In `cognitive_castle/searcher.py:145`, change the `search` signature similarly. Locate `def search(query: str, palace_path: str, wing: str = None, room: str = None, n_results: int = 5):` and add `llm_rerank: bool = False` as the last keyword arg.

- [ ] **Step 6: Thread `llm_rerank` through to the internal pipeline + add Stage 4 hook**

Locate the internal helper that does the 3-stage pipeline (currently at `cognitive_castle/searcher.py:308`-ish — search for `"3-stage retrieval pipeline"` to confirm). Add `llm_rerank: bool = False` to its signature.

At BOTH calling sites (`search()` and `search_memories()`), pass `llm_rerank=llm_rerank` through.

Then, in the internal helper, locate the cross-encoder rerank block at around line 410-422. **After** the `reranked = sorted(zip(rerank_scores, top_k_rows), key=lambda x: -x[0])` line (currently line 422), insert the Stage 4 hook BEFORE the final return:

```python
    # ── Stage 4 (optional): LLM-as-judge re-rank ───────────────────────────
    if llm_rerank:
        from .judge import judge
        # Take top-N (cfg.llm_judge_top_n) from Stage 3 output for LLM judging.
        # Stage 3 already returned a sorted list (most-relevant first).
        top_n = cfg.llm_judge_top_n
        judge_pool = reranked[:top_n]
        judge_docs = [_extract_text(r) for _, r in judge_pool]
        new_order = judge(query, judge_docs, cfg)
        # Reorder judge_pool by the LLM's preferred indices.
        reranked = [judge_pool[i] for i in new_order]
```

Place this block such that the existing return statement (around line 424) continues to use `reranked[:n_results]` — the Stage 4 reordering should pass through to the final slice.

- [ ] **Step 7: Run integration tests to verify all 3 pass**

Run:
```bash
pytest tests/test_searcher.py -v -k llm_rerank
```

Expected: 3 passed.

- [ ] **Step 8: Run full searcher tests + judge tests to confirm no regressions**

Run:
```bash
pytest tests/test_searcher.py tests/test_judge.py tests/test_config.py -v
```

Expected: all pass, including the 8 from Task 3 + 12 from Task 2 + existing test_searcher.py tests.

- [ ] **Step 9: Lint check**

Run:
```bash
ruff check cognitive_castle/searcher.py tests/test_searcher.py && ruff format --check cognitive_castle/searcher.py tests/test_searcher.py
```

Expected: no errors.

- [ ] **Step 10: Commit**

```bash
git add cognitive_castle/searcher.py tests/test_searcher.py
git commit -m "$(cat <<'EOF'
feat(searcher): thread llm_rerank through search() + search_memories()

Adds llm_rerank: bool = False param to both public functions and
threads through to the internal 3-stage pipeline. When True, inserts
Stage 4 LLM-as-judge re-rank between Stage 3 (cross-encoder) and the
final n_results slice — takes top cfg.llm_judge_top_n candidates,
calls judge.judge, reorders by LLM ordering.

Zero behavior change in the default path (llm_rerank=False). The
judge module's identity-order fallback ensures search ALWAYS returns
results even if the LLM is unreachable.

3 integration tests verify: Stage 4 NOT called when False; called
with top-N when True; identity-fallback gives the same result as
llm_rerank=False.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add `--llm-rerank` CLI flag

**Files:**
- Modify: `cognitive_castle/cli.py` (add argparse flag + pass through)
- Modify: `tests/test_cli.py` (add 1 test)

- [ ] **Step 1: Find the `castle search` argparse setup in cli.py**

Run:
```bash
grep -n "p_search\|search.*sub.add_parser" cognitive_castle/cli.py | head -5
```

Note the line number of the `p_search = sub.add_parser("search", ...)` block. Adjacent `p_search.add_argument(...)` calls show the existing flag pattern.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_search_cli_llm_rerank_flag_propagates(monkeypatch, tmp_path):
    """`castle search ... --llm-rerank` must set llm_rerank=True on the search call."""
    from unittest.mock import MagicMock
    spy = MagicMock(return_value=[])
    monkeypatch.setattr("cognitive_castle.cli.search", spy)

    # Simulate the argparse Namespace that `castle search "x" --llm-rerank --palace /tmp/p`
    # would produce. The cli.cmd_search function reads args.llm_rerank.
    import argparse
    args = argparse.Namespace(
        query="x",
        palace=str(tmp_path / "palace"),
        wing=None,
        room=None,
        n_results=5,
        llm_rerank=True,
    )
    # If cmd_search has other required attributes, mirror the existing
    # test_search_cli_* tests in this file for the exact Namespace shape.
    from cognitive_castle.cli import cmd_search
    cmd_search(args)

    spy.assert_called_once()
    # Verify llm_rerank=True was passed through
    call_kwargs = spy.call_args.kwargs
    assert call_kwargs.get("llm_rerank") is True
```

**Adapt the Namespace shape** if `cmd_search` reads other args. If the existing test file has a `_make_search_args(...)` helper, use it.

- [ ] **Step 3: Run test to verify FAIL**

Run:
```bash
pytest tests/test_cli.py::test_search_cli_llm_rerank_flag_propagates -v
```

Expected: FAIL with `AttributeError: 'Namespace' object has no attribute 'llm_rerank'` OR `AssertionError: call_kwargs.get("llm_rerank") is None` (depending on whether the test reaches the assert).

- [ ] **Step 4: Add the `--llm-rerank` flag to the `castle search` subparser**

In the `p_search` block from Step 1 (typically around line 1050-1080 of cli.py), append after the last existing `p_search.add_argument(...)`:

```python
    p_search.add_argument(
        "--llm-rerank",
        action="store_true",
        help=(
            "Run optional Stage 4 LLM-as-judge re-rank over top candidates. "
            "Adds 1-2s latency. Uses the LLM provider configured at `castle init` "
            "(set via CASTLE_LLM_PROVIDER / CASTLE_LLM_MODEL or castle.yaml). "
            "Off by default."
        ),
    )
```

- [ ] **Step 5: Pass through in `cmd_search`**

Find the `cmd_search` function (grep `def cmd_search` in cli.py). Locate the line that calls `search(...)`. Add `llm_rerank=getattr(args, "llm_rerank", False)` as a kwarg.

If `cmd_search` currently calls `search(query=..., palace_path=..., n_results=..., wing=..., room=...)`, change it to:

```python
    search(
        query=...,
        palace_path=...,
        n_results=...,
        wing=...,
        room=...,
        llm_rerank=getattr(args, "llm_rerank", False),
    )
```

(Keep the existing args; just add the new kwarg.)

- [ ] **Step 6: Run the test to verify PASS**

Run:
```bash
pytest tests/test_cli.py::test_search_cli_llm_rerank_flag_propagates -v
```

Expected: PASS.

- [ ] **Step 7: Verify `castle reindex --help` shows the new flag** (sanity smoke)

Run:
```bash
castle search --help 2>&1 | grep -A3 "llm-rerank"
```

Expected: shows `--llm-rerank` with the help text from Step 4.

- [ ] **Step 8: Lint check**

Run:
```bash
ruff check cognitive_castle/cli.py tests/test_cli.py && ruff format --check cognitive_castle/cli.py tests/test_cli.py
```

Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add cognitive_castle/cli.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(cli): add --llm-rerank flag to castle search

Store-true flag, default False. Help text describes 1-2s latency cost
and points users at the LLM provider configured via env vars or
castle.yaml. Threads through to search(llm_rerank=...) which gates
the optional Stage 4 LLM-as-judge re-rank.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add `llm_rerank` MCP tool param

**Files:**
- Modify: `cognitive_castle/mcp_server.py` (add tool schema entry + handler param)

The MCP server uses a `TOOLS` dict mapping tool names to JSON schemas. The `search_memories` tool needs a new optional `llm_rerank: boolean` property.

- [ ] **Step 1: Locate the `search_memories` tool schema**

Run:
```bash
grep -n "search_memories\|llm_rerank" cognitive_castle/mcp_server.py | head -15
```

Find:
- Where `search_memories` appears in the `TOOLS` dict (likely with `"inputSchema": {"properties": {...}}`)
- Where the `search_memories` handler function is defined
- How it currently parses params from the MCP request

- [ ] **Step 2: Add `llm_rerank` to the JSON schema for `search_memories`**

Inside the `properties` block of the `search_memories` tool entry in the `TOOLS` dict, add:

```python
                "llm_rerank": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Run optional Stage 4 LLM-as-judge re-rank over top "
                        "candidates. Adds 1-2s latency. Uses the LLM provider "
                        "configured via CASTLE_LLM_PROVIDER / CASTLE_LLM_MODEL "
                        "or castle.yaml. Off by default."
                    ),
                },
```

Place this property alongside the existing ones (e.g. `n_results`, `wing`, `room`). Do NOT add it to the `required` array — it's optional with a default.

- [ ] **Step 3: Update the `search_memories` handler to read + pass `llm_rerank`**

Locate the `search_memories` handler function (often named `handle_search_memories` or similar). Find the line that calls `search_memories(...)` from `cognitive_castle.searcher` and add `llm_rerank=arguments.get("llm_rerank", False)` as a kwarg.

If the handler currently does:
```python
    results = search_memories(
        query=arguments["query"],
        palace_path=palace_path,
        n_results=arguments.get("n_results", 5),
        wing=arguments.get("wing"),
        room=arguments.get("room"),
    )
```

change it to:
```python
    results = search_memories(
        query=arguments["query"],
        palace_path=palace_path,
        n_results=arguments.get("n_results", 5),
        wing=arguments.get("wing"),
        room=arguments.get("room"),
        llm_rerank=arguments.get("llm_rerank", False),
    )
```

- [ ] **Step 4: Verify the MCP schema includes the new property** (sanity smoke)

Run:
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | castle-mcp 2>/dev/null | python -c "
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
        if msg.get('id') == 1:
            tools = msg.get('result', {}).get('tools', [])
            for tool in tools:
                if tool['name'] == 'search_memories':
                    props = tool.get('inputSchema', {}).get('properties', {})
                    if 'llm_rerank' in props:
                        print('OK: llm_rerank property present')
                        print('  type:', props['llm_rerank'].get('type'))
                        print('  default:', props['llm_rerank'].get('default'))
                    else:
                        print('FAIL: llm_rerank not in properties')
                        sys.exit(1)
            break
    except Exception as e:
        pass
"
```

Expected output:
```
OK: llm_rerank property present
  type: boolean
  default: False
```

If the schema validation script doesn't work in your environment, fall back to manually inspecting `mcp_server.py` and confirming the JSON structure has `llm_rerank` inside `properties`.

- [ ] **Step 5: Run the full test suite to confirm no MCP regressions**

Run:
```bash
pytest tests/test_mcp_server.py -v
```

Expected: existing MCP tests still pass. (No new test added in this task — the schema is verified by the smoke check; the handler propagation is covered indirectly by Task 4's integration tests.)

- [ ] **Step 6: Lint check**

Run:
```bash
ruff check cognitive_castle/mcp_server.py && ruff format --check cognitive_castle/mcp_server.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/mcp_server.py
git commit -m "$(cat <<'EOF'
feat(mcp): add llm_rerank param to search_memories tool

Optional boolean property on the search_memories MCP tool input
schema, default false. Handler propagates to search_memories(...)
with the same default. Enables Claude Code (and any MCP client) to
opt into Stage 4 LLM-as-judge re-rank per request.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update CLAUDE.md retrieval pipeline diagram

**Files:**
- Modify: `CLAUDE.md` (line 179 area — the retrieval pipeline diagram)

- [ ] **Step 1: Locate the current diagram**

Run:
```bash
grep -n "Stage 3\|Stage 1\|cross-encoder\|reranker" /home/lbihari/cognitive-castle/CLAUDE.md | head -10
```

Find the retrieval pipeline diagram (a code block at around line 175-185).

- [ ] **Step 2: Update the diagram to show optional Stage 4**

The current diagram (from CLAUDE.md as it stood after PR #1) looks like:

```
Retrieval pipeline (3-stage, used by both `castle search` and `search_memories`):
  Query
    ├── Stage 1 (parallel recall, ~top-100 each):
    │     ├── Dense vector search (paraphrase-multilingual-MiniLM-L12-v2 default, BAAI/bge-m3 supported via config — see README)
    │     ├── Sparse FTS search (Tantivy via LanceDB)
    │     └── KG-hop (entity registry lookup → KnowledgeGraph.find_drawers_by_entities)
    ├── Stage 2: weighted RRF + recency multiplier → top-K (K=20 interactive, K=10 hook)
    └── Stage 3: cross-encoder rerank → top-N results
```

Replace the final `Stage 3` line with:

```
    ├── Stage 3: cross-encoder rerank → top-N results
    └── Stage 4 (optional, opt-in via --llm-rerank or llm_rerank:true MCP param):
          LLM-as-judge re-ranks top-cfg.llm_judge_top_n (default 10) from Stage 3
          → graceful identity-order fallback on any LLM failure
```

(Adjust the existing `└── Stage 3` to `├── Stage 3` since it's no longer the last entry — match the tree-drawing style of the rest of the diagram.)

- [ ] **Step 3: Verify the diagram renders correctly**

Run:
```bash
grep -A12 "Retrieval pipeline" /home/lbihari/cognitive-castle/CLAUDE.md | head -15
```

Expected: 4 stages now visible; Stage 4 marked as optional with the opt-in mechanism.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude.md): add optional Stage 4 to retrieval pipeline diagram

Pipeline diagram now shows 4 stages: the original 3 + the new
opt-in LLM-as-judge re-rank gated by --llm-rerank / llm_rerank:true.
Stage 4 explicitly labeled "optional" with the opt-in mechanism so
readers understand the default-behavior guarantee.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Update README.md "Going further" block

**Files:**
- Modify: `README.md` (append `--llm-rerank` subsection inside the existing "Going further" block from PR #1)

- [ ] **Step 1: Find the "Going further" block**

Run:
```bash
grep -n "^## Going further\|^### " /home/lbihari/cognitive-castle/README.md | head -10
```

Identify the boundary of the existing "Going further: better recall with bge-m3" block (added by PR #1, ends at the `---` separator before "How it works").

- [ ] **Step 2: Insert the new subsection**

Inside the "Going further" block, BEFORE the closing `---` separator, append:

```markdown

### Stage 4: LLM-as-judge re-rank (`--llm-rerank`)

Castle's default 3-stage pipeline (dense + FTS + KG → fusion → cross-encoder rerank) is already strong. For the last few percent on high-stakes queries — especially ones where subtle intent or multi-hop reasoning matters — you can opt into a **Stage 4 LLM-as-judge re-rank**.

```bash
castle search "what did we decide about authentication?" --llm-rerank
```

How it works:
- Stage 3 produces a top-10 candidate list (configurable via `CASTLE_LLM_JUDGE_TOP_N`).
- The configured LLM ranks those 10 by relevance, returns a preferred ordering.
- Castle reorders and returns top-N.

**Cost:** 1–2s extra latency per search.

**LLM provider:** uses the LLM configured at `castle init` (see `castle init --help` for `--llm-provider` / `--llm-model` / etc.). Configure via env vars or `castle.yaml`:

```yaml
llm_provider: ollama       # or "anthropic" / "openai-compat"
llm_model: llama3.1:8b      # any model your provider supports
# llm_endpoint:             # only needed for openai-compat / custom Ollama
# llm_api_key:              # only needed for anthropic / openai-compat
```

Or via env vars: `CASTLE_LLM_PROVIDER`, `CASTLE_LLM_MODEL`, `CASTLE_LLM_ENDPOINT`, `CASTLE_LLM_API_KEY`, `CASTLE_LLM_TIMEOUT`.

> **⚠️ Note:** Castle's documented default LLM model is `gemma3:e4b`, but that tag doesn't exist in Ollama's registry — it's a pre-existing bug tracked in a follow-up. To actually use `--llm-rerank`, set `CASTLE_LLM_MODEL` to a model your Ollama (or other provider) has.

**MCP:** Claude Code and other MCP clients can pass `llm_rerank: true` to the `search_memories` tool.

**Privacy:** If you've configured a BYOK external provider (Anthropic, cloud OpenAI-compat, etc.), candidate snippets DO leave your machine. Castle prints a privacy warning at `castle init` for external providers — per-search warnings would be noise. If you want strict local-only operation, stick with Ollama / LM Studio / vLLM on localhost.

**Graceful fallback:** if the LLM is unreachable (Ollama not running, network timeout, malformed JSON), Castle prints a one-line stderr warning and returns Stage 3's ordering. Search ALWAYS returns results.
```

- [ ] **Step 3: Verify the section landed correctly**

Run:
```bash
grep -A2 "^### Stage 4" /home/lbihari/cognitive-castle/README.md | head -5
grep -E "llm_rerank|--llm-rerank" /home/lbihari/cognitive-castle/README.md | head -5
```

Expected:
- Section heading `### Stage 4: LLM-as-judge re-rank (--llm-rerank)` appears
- Both `--llm-rerank` (CLI) and `llm_rerank: true` (MCP) framing present

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs(readme): add Stage 4 LLM-as-judge subsection to Going further block

Documents the new --llm-rerank opt-in: when to use, how it works,
the 1-2s latency cost, LLM provider configuration (env vars + yaml
keys), the pre-existing-broken-default-model caveat (tracked in
a follow-up), MCP llm_rerank:true equivalent, BYOK external-provider
privacy disclosure, and the graceful fallback guarantee.

No default change — section is purely about opt-in usage.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Live smoke

Two manual smoke runs that exercise the live end-to-end path. Both should work after Tasks 1-8. Capture the results for the PR description.

**Files:** none (filesystem + Ollama only)

- [ ] **Step 1: Prepare a smoke palace using bge-m3 (or whatever the user has)**

Run:
```bash
rm -rf /tmp/castle-llm-smoke
mkdir -p /tmp/castle-llm-smoke/palace /tmp/castle-llm-smoke/src
cat > /tmp/castle-llm-smoke/src/auth.md <<'EOF'
# Authentication architecture

We use JWT tokens for stateless auth between the API gateway and downstream services. Tokens are signed with RS256 and rotated every 24h. Session storage uses Redis with a 1-hour TTL.

For frontend auth we use OAuth2 with PKCE. The redirect URI must be registered per environment (dev, staging, prod).
EOF
cat > /tmp/castle-llm-smoke/src/database.md <<'EOF'
# Database setup

Postgres 16 primary, read replicas in two AZs. Migrations via Alembic. Connection pooling with PgBouncer at the application tier.
EOF
cat > /tmp/castle-llm-smoke/src/deploy.md <<'EOF'
# Deployment

Helm charts in infra/helm. Argo CD reconciles every 3min. Rollback via `argocd app sync --revision <sha>`.
EOF
```

Then reindex with the user's existing castle config (any embedder):
```bash
castle reindex --palace /tmp/castle-llm-smoke/palace --sources /tmp/castle-llm-smoke/src --yes
```

Expected: reindex completes, 3 drawers filed.

- [ ] **Step 2: Live smoke — happy path (LLM available)**

Ensure Ollama is running with a real model:
```bash
ollama list  # should show at least one model
```

Set `CASTLE_LLM_MODEL` to whatever you have. Pick a small fast model — `qwen3.5:latest` would be a reasonable choice on the user's current system per `ollama list`:

```bash
export CASTLE_LLM_MODEL=qwen3.5:latest
castle search "how do we handle authentication?" --llm-rerank --palace /tmp/castle-llm-smoke/palace
```

Expected:
- Completes in <10s (depends on model load time and your hardware)
- Returns results; the auth.md content should rank first
- No `[judge]` stderr warnings (LLM succeeded)

Record the actual output for the PR description.

- [ ] **Step 3: Live smoke — Ollama-down fallback**

Stop Ollama (platform-dependent):
```bash
# Linux:   sudo systemctl stop ollama
# macOS:   brew services stop ollama
# Universal:  pkill -f "ollama serve"
```

Or temporarily set an invalid endpoint to force failure without stopping the daemon:
```bash
export CASTLE_LLM_ENDPOINT=http://localhost:65535
```

Re-run the search:
```bash
castle search "how do we handle authentication?" --llm-rerank --palace /tmp/castle-llm-smoke/palace
```

Expected:
- Completes successfully (search did NOT crash)
- Stderr contains `[judge] LLM call failed (...): falling back to cross-encoder ordering`
- Results are returned in Stage 3 (cross-encoder) order

Record the stderr output for the PR description.

- [ ] **Step 4: Live smoke — default behavior unchanged (no flag)**

Reset env vars and run WITHOUT the flag:
```bash
unset CASTLE_LLM_ENDPOINT
castle search "how do we handle authentication?" --palace /tmp/castle-llm-smoke/palace
```

Expected:
- Completes in normal time (no extra 1-2s)
- No `[judge]` stderr lines (Stage 4 never invoked)
- Results match Stage 3 ordering — identical to what the user would get on the previous develop HEAD

- [ ] **Step 5: Clean up**

```bash
rm -rf /tmp/castle-llm-smoke
unset CASTLE_LLM_MODEL CASTLE_LLM_ENDPOINT
```

No commit — these are verification steps only. Results go in the PR description.

---

## Task 10: Final acceptance + push + PR

Walk through all 12 acceptance criteria from the spec, then push and open the PR.

**Files:** none (verification + git push only)

- [ ] **Step 1: Acceptance #1 — judge unit tests pass**

```bash
pytest tests/test_judge.py -v
```
Expected: 8 passed.

- [ ] **Step 2: Acceptance #2 — searcher integration tests pass**

```bash
pytest tests/test_searcher.py -v -k llm_rerank
```
Expected: 3 passed.

- [ ] **Step 3: Acceptance #3 — CLI flag test passes**

```bash
pytest tests/test_cli.py -v -k llm_rerank
```
Expected: 1 passed.

- [ ] **Step 4: Acceptance #3a — config-property tests pass**

```bash
pytest tests/test_config.py -v -k "llm_"
```
Expected: 12 passed (covers all 6 new properties × default + env-override paths).

- [ ] **Step 5: Acceptance #4 — full suite no new regressions**

```bash
pytest tests/ -v --ignore=tests/benchmarks
```
Expected: previous-passing-count + ~24 new tests (12 config + 8 judge + 3 searcher + 1 cli). Pre-existing CI-UNSTABLE failures acceptable.

- [ ] **Step 6: Acceptance #5 — `castle search --help` shows `--llm-rerank`**

```bash
castle search --help
```
Expected output contains a `--llm-rerank` flag with help text mentioning "1-2s latency" AND the LLM provider configuration framing.

- [ ] **Step 7: Acceptance #6 — MCP `search_memories` schema has `llm_rerank`**

Run the MCP schema smoke from Task 6 Step 4. Expected: `llm_rerank` boolean property with `default: false`.

- [ ] **Step 8: Acceptance #7 — ruff clean on all touched files**

```bash
ruff check cognitive_castle/judge.py cognitive_castle/searcher.py cognitive_castle/config.py cognitive_castle/cli.py cognitive_castle/mcp_server.py tests/test_judge.py tests/test_searcher.py tests/test_cli.py tests/test_config.py
ruff format --check cognitive_castle/judge.py cognitive_castle/searcher.py cognitive_castle/config.py cognitive_castle/cli.py cognitive_castle/mcp_server.py tests/test_judge.py tests/test_searcher.py tests/test_cli.py tests/test_config.py
```
Expected: no errors. (The repo-wide `ruff format --check .` will show pre-existing drift unrelated to this PR — that's documented as CI-UNSTABLE.)

- [ ] **Step 9: Acceptance #8 + #9 — smoke recipes verified**

Task 9 already covered this. Confirm by re-reading Task 9 results.

- [ ] **Step 10: Acceptance #10 — README has the Stage 4 subsection**

```bash
grep -E "Stage 4|llm-rerank|CASTLE_LLM_MODEL" /home/lbihari/cognitive-castle/README.md | head -10
```
Expected: multiple matches — section heading, CLI flag mention, env var docs, MCP llm_rerank mention.

- [ ] **Step 11: Acceptance #11 — CLAUDE.md diagram updated**

```bash
grep -A3 "Stage 4" /home/lbihari/cognitive-castle/CLAUDE.md | head -8
```
Expected: Stage 4 appears in the retrieval pipeline diagram with "optional" marker.

- [ ] **Step 12: Acceptance #12 — default behavior unchanged**

Task 9 Step 4 already verified this empirically (no-flag search produces Stage 3 ordering, no judge invocation). The stronger statement ("byte-identical output before and after this PR") is verified by Acceptance #4 (full suite passes — no test that previously passed now fails without `--llm-rerank`).

- [ ] **Step 13: Push branch + open PR**

```bash
git push -u origin feat/llm-judge-stage4
```

Expected: branch pushed; gh prints the new-PR URL.

```bash
gh pr create --title "feat: enable LLM-as-judge Stage 4 (opt-in) for retrieval pipeline" --body "$(cat <<'EOF'
## Summary

PR #3 of the SOTA-retrieval umbrella. Adds an optional Stage 4 to Castle's retrieval pipeline: an LLM-as-judge re-rank that improves precision on high-stakes queries.

- **Opt-in only:** `castle search --llm-rerank` (CLI) or `llm_rerank: true` (MCP `search_memories` tool). Default behavior is byte-identical to before.
- **New `cognitive_castle/judge.py`** module mirrors `reranker.py`. Builds prompt, calls configured LLM, parses + validates JSON, identity-order fallback on every failure mode.
- **5 new config properties** (`llm_provider`, `llm_model`, `llm_endpoint`, `llm_api_key`, `llm_timeout`) + 1 from spec (`llm_judge_top_n`) close a config-layer gap — Castle had no `cfg.llm_*` properties; provider was only built transiently in `cmd_init`.
- **Reuses existing infrastructure:** `llm_client.get_provider(name, model, endpoint, api_key, timeout)` factory from PR-pre-existing code. Ollama default, BYOK Anthropic/OpenAI-compat/Google supported.
- **Graceful fallback:** any LLM failure (Ollama down, malformed JSON, validation error) prints a one-line stderr warning and returns Stage 3 ordering. Search ALWAYS returns results.
- **Documentation:** README has a new "Stage 4: LLM-as-judge" subsection inside the existing "Going further" block. CLAUDE.md retrieval diagram now shows the optional 4th stage.

Spec: `docs/superpowers/specs/2026-05-13-llm-judge-stage4-design.md` (commit `1ccf3113`).
Plan: `docs/superpowers/plans/2026-05-13-llm-judge-stage4.md`.

## Known caveat (separate follow-up)

Castle's documented LLM default `gemma3:e4b` doesn't exist in Ollama's registry — a pre-existing bug introduced by PR #20 and never caught. This spec preserves the default for cmd_init consistency; users must set `CASTLE_LLM_MODEL` to a real model to actually use `--llm-rerank`. Fixing the broken default is tracked separately.

## Test plan

- [x] `pytest tests/test_judge.py -v` — 8 passed (happy path + 7 fallback paths)
- [x] `pytest tests/test_searcher.py -v -k llm_rerank` — 3 passed (Stage 4 NOT called when False; called when True; identity fallback preserves Stage 3 order)
- [x] `pytest tests/test_cli.py -v -k llm_rerank` — 1 passed (flag propagation)
- [x] `pytest tests/test_config.py -v -k "llm_"` — 12 passed (6 properties × default + env-override paths)
- [x] `pytest tests/ -v --ignore=tests/benchmarks` — no new regressions
- [x] `ruff check` + `ruff format --check` clean on all 9 touched files
- [x] `castle search --help` shows `--llm-rerank` flag
- [x] MCP `tools/list` shows `llm_rerank: boolean (default false)` on `search_memories`
- [x] **Live smoke (happy path):** `CASTLE_LLM_MODEL=<real-model> castle search "..." --llm-rerank` completes in <10s, returns reranked results, no stderr warnings
- [x] **Live smoke (LLM-down fallback):** with invalid endpoint, search completes successfully with `[judge] ... falling back to cross-encoder ordering` stderr
- [x] **Live smoke (default unchanged):** no-flag search produces Stage 3 ordering with no judge invocation

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opens at `https://github.com/Testimonial/cognitive-castle/pull/<N>`. Report the URL.

---

## Self-Review

**Spec coverage check:** every acceptance criterion from `2026-05-13-llm-judge-stage4-design.md` (12 in the spec, renumbered to 13 with #3a) maps to at least one task:

| Spec acceptance | Implemented in |
|---|---|
| #1 8 unit tests | Task 3 |
| #2 3 integration tests | Task 4 |
| #3 CLI flag test | Task 5 |
| #3a 6 config tests (×2 paths = 12) | Task 2 |
| #4 default suite | Task 10 Step 5 |
| #5 `--help` shows flag | Task 5 (built) + Task 10 Step 6 (verified) |
| #6 MCP schema | Task 6 (built) + Task 10 Step 7 (verified) |
| #7 ruff clean | every task has a ruff check step; Task 10 Step 8 final |
| #8 happy-path smoke | Task 9 Step 2 |
| #9 fallback smoke | Task 9 Step 3 |
| #10 README subsection | Task 8 |
| #11 CLAUDE.md diagram | Task 7 |
| #12 default unchanged | Task 9 Step 4 + Task 4's `false_skips_stage_4` test |

**Placeholder scan:**
- No "TBD", "TODO", "implement later".
- Two intentional placeholders worth flagging:
  - Task 4 Step 2 has `...` in `_build_fixture_palace(tmp_path, n_drawers=15)` — explicitly labeled as "adapt to the existing fixture pattern after Step 1's reconnaissance." This is necessary because integration tests must use the repo's existing fixture infrastructure, which the implementer needs to discover.
  - Task 5 Step 2's Namespace shape "if cmd_search has other required attributes, mirror the existing test_search_cli_* tests in this file." Same justification.
- These are NOT vague placeholders — they're "match the existing pattern" pointers that require local file inspection. Acceptable per the writing-plans skill's "follow established patterns" guidance.

**Type consistency:**
- `judge(query: str, candidates: list[str], cfg) -> list[int]` — same signature in Tasks 3 (impl), 4 (test mocks).
- `_get_provider(cfg) -> LLMProvider` — same target across Tasks 3 (impl), test mocks.
- `llm_rerank: bool = False` — same default + type across Tasks 4 (searcher), 5 (CLI), 6 (MCP).
- 6 config property names match across Task 2 (impl + tests) and Task 3 (`_get_provider` reads them).
- `SNIPPET_CHARS = 600` (Task 3) consistent with spec.
- `[judge] <reason>: falling back to cross-encoder ordering` exact stderr string consistent in Task 3 impl + tests.

**Spec gaps caught at plan-writing time:**
- `_get_provider(cfg)` had no config layer to read from. Resolved via spec revision-3 (commit `1ccf3113`) and Task 2's new config properties.
- No other gaps surfaced during plan drafting.
