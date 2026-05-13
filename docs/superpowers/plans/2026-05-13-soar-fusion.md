# SOAR Bridge + Post-Pipeline Boost-Tags (PR #4a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the SOAR bridge deleted in PR #14 as a working, opt-in, post-pipeline boost-tag layer for Castle's retrieval results. Soar 9.6.40 + SML Python bindings verified live on the developer's hardware.

**Architecture:** Lazy-loaded singleton Soar kernel + palace-keyed agent. Two minimal productions emit `^boost-tag` attributes on input-link memory WMEs. Python reads back, applies multiplicative score boosts, augments hits with audit-trail fields. Default behavior byte-identical. EpMem/SMem subsystems enabled but unused (preparation for #4c chunking).

**Tech Stack:** Python 3.12, Soar 9.6.40 via `Python_sml_ClientInterface` (SWIG-wrapped C++ kernel at `/home/lbihari/soar-work/Soar/build/Core/ClientSMLSWIG/python/`), pytest with custom `@pytest.mark.soar` marker.

**Spec:** [`docs/superpowers/specs/2026-05-13-soar-fusion-design.md`](../specs/2026-05-13-soar-fusion-design.md) (commit `db831e63`).

**File map (11 files, ~685 LOC):**

| File | Responsibility | Tasks |
|---|---|---|
| `cognitive_castle/config.py` | 2 new env-first properties: `soar_enabled`, `soar_rules_path` | Task 2 |
| `pyproject.toml` | Register `soar` pytest marker | Task 3 |
| `cognitive_castle/soar_bridge.py` (new) | Lazy SML import, kernel/agent singletons, `apply_soar_boosts()`, `_reset_for_test()` | Task 4 |
| `cognitive_castle/rules/castle-boost.soar` (new) | 2 production rules: `recency-boost`, `same-project` | Task 5 |
| `cognitive_castle/searcher.py` | Extract `_print_search_results()` helper from `search()` so cmd_search can reuse formatting | Task 6 |
| `cognitive_castle/cli.py` | `--soar-boost` flag + kill-switch + lazy import + SOAR-path branch in `cmd_search` | Task 7 |
| `cognitive_castle/mcp_server.py` | `soar_boost` MCP param + lazy import in `tool_search` handler | Task 8 |
| `tests/test_soar_bridge.py` (new) | 8 Soar-gated + 2 always-run tests; autouse `reset_soar_state` fixture | Task 4 |
| `tests/test_config.py` (existing) | 4 tests for the 2 new config properties | Task 2 |
| `tests/test_cli.py` (existing) | 2 tests: `--soar-boost` flag + kill-switch exit code | Task 7 |
| `tests/test_mcp_server.py` (existing) | 1 test: `soar_boost:true` MCP param threading | Task 8 |
| `CLAUDE.md` | Update retrieval pipeline diagram to show optional Stage 5 | Task 9 |
| `README.md` | Append "Experimental: SOAR symbolic re-ranking" subsection | Task 9 |

---

## Task 1: Create feature branch

**Files:** none (git only)

- [ ] **Step 1: Confirm clean tree on develop**

Run:
```bash
git status
git log --oneline -3
```

Expected:
- On branch `develop`
- Working tree clean (no `test_env/` — was fixed in earlier session)
- Latest commit is `db831e63` (the spec revision-4) or later

- [ ] **Step 2: Create + switch to feature branch**

Run:
```bash
git checkout -b feat/soar-bridge
```

Expected: `Switched to a new branch 'feat/soar-bridge'`

No commit yet.

---

## Task 2: Add `soar_enabled` + `soar_rules_path` config properties (TDD)

**Files:**
- Modify: `cognitive_castle/config.py` (append 2 new `@property` methods after the 6 LLM properties from PR #3)
- Modify: `tests/test_config.py` (append 4 new tests)

- [ ] **Step 1: Write the 4 failing tests**

Append to `tests/test_config.py`:

```python
def test_soar_enabled_default_is_false():
    cfg = _make_config_with_file_config({})
    assert cfg.soar_enabled is False


def test_soar_enabled_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_SOAR_ENABLED", "1")
    cfg = _make_config_with_file_config({})
    assert cfg.soar_enabled is True


def test_soar_rules_path_default_points_at_package():
    cfg = _make_config_with_file_config({})
    # Default should be <package>/rules/castle-boost.soar
    assert cfg.soar_rules_path.endswith("rules/castle-boost.soar")
    assert "cognitive_castle" in cfg.soar_rules_path


def test_soar_rules_path_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "my-rules.soar"
    custom.write_text("# placeholder")
    monkeypatch.setenv("CASTLE_SOAR_RULES_PATH", str(custom))
    cfg = _make_config_with_file_config({})
    assert cfg.soar_rules_path == str(custom)
```

- [ ] **Step 2: Run tests — confirm FAIL**

Run:
```bash
pytest tests/test_config.py -v -k "soar"
```

Expected: 4 tests collected, all FAIL with `AttributeError: 'CognitiveCastleConfig' object has no attribute 'soar_enabled'`.

- [ ] **Step 3: Add the 2 properties to `cognitive_castle/config.py`**

Find the end of the LLM property block (the last property added by PR #3 — `llm_timeout`). Append:

```python
    @property
    def soar_enabled(self):
        """Kill switch for SOAR post-pipeline boost-tags (PR #4a).

        Default: ``False``. Must be explicitly set to a truthy value
        (``"1"`` / ``"true"`` / ``"yes"`` case-insensitive) to enable.
        When False, `--soar-boost` CLI flag triggers a loud kill-switch
        error rather than silent no-op.

        Reads from ``CASTLE_SOAR_ENABLED`` env var first, then config file,
        then default.
        """
        env_val = os.environ.get("CASTLE_SOAR_ENABLED")
        if env_val is not None:
            return env_val.strip().lower() in ("1", "true", "yes")
        cfg_val = self._file_config.get("soar_enabled", False)
        return bool(cfg_val)

    @property
    def soar_rules_path(self):
        """Path to the Soar production rule file for #4a's boost-tag layer.

        Default: ``<package>/rules/castle-boost.soar`` (shipped with Castle).
        Override to point at a custom rule file via env or castle.yaml.

        Reads from ``CASTLE_SOAR_RULES_PATH`` env var first, then config file,
        then default.
        """
        env_val = os.environ.get("CASTLE_SOAR_RULES_PATH")
        if env_val:
            return env_val.strip()
        cfg_val = self._file_config.get("soar_rules_path")
        if cfg_val:
            return str(cfg_val).strip()
        # Default: package-relative path to rules/castle-boost.soar
        from pathlib import Path
        return str(Path(__file__).parent / "rules" / "castle-boost.soar")
```

- [ ] **Step 4: Run tests — confirm 4 PASS**

```bash
pytest tests/test_config.py -v -k "soar"
```

Expected: 4 passed.

- [ ] **Step 5: Run full test suite — no regressions**

```bash
pytest tests/ -v --ignore=tests/benchmarks
```

Expected: previous-passing-count + 4 new tests. Pre-existing CI-UNSTABLE failures acceptable.

- [ ] **Step 6: Lint**

```bash
ruff check cognitive_castle/config.py tests/test_config.py && ruff format --check cognitive_castle/config.py tests/test_config.py
```

- [ ] **Step 7: Commit**

```bash
git add cognitive_castle/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): add soar_enabled + soar_rules_path properties

Adds 2 new env-first properties to CognitiveCastleConfig for PR #4a
(SOAR post-pipeline boost-tags):
- soar_enabled (default False, env CASTLE_SOAR_ENABLED) — kill switch
- soar_rules_path (default <package>/rules/castle-boost.soar, env
  CASTLE_SOAR_RULES_PATH) — points at the production rule file

Pattern matches the 6 LLM properties added in PR #3 (env → file → default).
4 unit tests cover defaults + env overrides.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Register `soar` pytest marker

**Files:**
- Modify: `pyproject.toml:78-82` (the `markers` list under `[tool.pytest.ini_options]`)

Without this, `pytest -m soar` filtering would emit `PytestUnknownMarkWarning` for every Soar-gated test.

- [ ] **Step 1: Locate the markers list**

```bash
grep -n "markers\s*=" /home/lbihari/cognitive-castle/pyproject.toml
```

Expected: a line like `markers = [` near line 78.

- [ ] **Step 2: Add `soar` marker**

Find the existing `markers` list. It looks like:

```toml
markers = [
    "benchmark: scale/performance benchmark tests",
    "slow: tests that take more than 30 seconds",
    "stress: destructive scale tests (100K+ drawers)",
]
```

Append a new entry inside the list:

```toml
    "soar: tests requiring Soar 9.6+ + SML Python bindings (auto-skip if unavailable)",
```

The full list should now have 4 entries.

- [ ] **Step 3: Verify pytest doesn't warn about the marker**

Run:
```bash
pytest --markers 2>&1 | grep -E "^@pytest.mark.(soar|benchmark|slow|stress)"
```

Expected: 4 marker lines including `@pytest.mark.soar`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "$(cat <<'EOF'
chore(pyproject): register `soar` pytest marker

Custom marker for Soar-gated tests in tests/test_soar_bridge.py
(landing in Task 4 of PR #4a). Registers the marker so pytest doesn't
emit PytestUnknownMarkWarning for every test that uses it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Build `cognitive_castle/soar_bridge.py` module + 10 tests (TDD)

This is the biggest task. ~260 LOC of bridge code + ~200 LOC of tests. Broken into discrete TDD sub-cycles.

**Files:**
- Create: `cognitive_castle/soar_bridge.py`
- Create: `tests/test_soar_bridge.py`

### Step group A: Build the test file scaffolding + 2 always-run tests (red, then green via partial impl)

- [ ] **Step 1: Create `tests/test_soar_bridge.py` with scaffolding + 2 always-run tests**

```python
"""Unit tests for the SOAR post-pipeline boost-tag bridge (PR #4a).

Soar-gated tests use @pytest.mark.soar and @_requires_sml — they auto-skip
if Python_sml_ClientInterface isn't importable. Always-run tests verify
the SML-unavailable fallback path + kill-switch behavior without needing
Soar installed.
"""
import sys
from unittest.mock import MagicMock

import pytest

_SML_AVAILABLE = False
try:
    import Python_sml_ClientInterface  # noqa: F401
    _SML_AVAILABLE = True
except ImportError:
    pass

_requires_sml = pytest.mark.skipif(not _SML_AVAILABLE, reason="Soar 9.6+ SML not installed")


@pytest.fixture(autouse=True)
def reset_soar_state():
    """Clear singleton kernel + agent cache between tests so they don't share state."""
    yield
    from cognitive_castle import soar_bridge
    soar_bridge._reset_for_test()


def _mock_cfg(soar_enabled=True, rules_path=None):
    """Minimal cfg for tests — only the fields apply_soar_boosts reads."""
    cfg = MagicMock()
    cfg.soar_enabled = soar_enabled
    cfg.soar_rules_path = rules_path or "/dev/null"
    cfg.palace_path = "/tmp/test-palace"
    return cfg


# ── Always-run tests (no Soar dependency) ─────────────────────────────


def test_apply_soar_boosts_no_op_when_sml_unavailable(monkeypatch, capsys):
    """When _load_sml() returns None, return hits unchanged + stderr warning ONCE."""
    from cognitive_castle import soar_bridge
    monkeypatch.setattr(soar_bridge, "_load_sml", lambda: None)
    soar_bridge._WARNED.clear()
    hits = [{"id": "a", "score": 0.5}]
    result = soar_bridge.apply_soar_boosts(hits, _mock_cfg())
    assert result == hits  # unchanged
    err = capsys.readouterr().err
    assert "SML Python bindings not available" in err


def test_apply_soar_boosts_kill_switch_when_disabled(monkeypatch, capsys):
    """When cfg.soar_enabled=False, return hits unchanged + stderr 'disabled'.

    The kill-switch ALSO fires at the CLI/MCP layer before apply_soar_boosts
    is called; this test covers the defensive double-check at the function level.
    """
    from cognitive_castle import soar_bridge
    soar_bridge._WARNED.clear()
    hits = [{"id": "a", "score": 0.5}]
    result = soar_bridge.apply_soar_boosts(hits, _mock_cfg(soar_enabled=False))
    assert result == hits
    err = capsys.readouterr().err
    assert "disabled" in err.lower() or "soar_enabled" in err.lower()
```

- [ ] **Step 2: Run — confirm both FAIL with ModuleNotFoundError**

```bash
pytest tests/test_soar_bridge.py -v
```

Expected: 2 tests collected, both FAIL with `ModuleNotFoundError: No module named 'cognitive_castle.soar_bridge'`.

- [ ] **Step 3: Create `cognitive_castle/soar_bridge.py` — initial scaffolding (fallback paths only)**

Create `cognitive_castle/soar_bridge.py`:

```python
"""soar_bridge.py — SOAR post-pipeline boost-tag layer (PR #4a, experimental).

Opt-in via cfg.soar_enabled + --soar-boost CLI flag (or soar_boost:true MCP).
Default behavior unchanged. Module is lazy-imported by callers so its load
cost is zero for users who never use --soar-boost.

Soar runs ELABORATION productions over the input-link memory WMEs, adding
i-supported ^boost-tag attributes. Python reads tags back, maps via
BOOST_MULTIPLIERS, applies as multiplicative score adjustments. Audit fields
(soar_boost, soar_tags, score_pre_soar) are added to each hit so every score
change has a name — the differentiating value over neural rerankers.

EpMem + SMem subsystems are enabled at agent creation (preparation for #4c
chunking) but not READ/WRITTEN in #4a — the placeholder fields they'd
populate (^access-count, ^decay) are explicitly absent from the #4a WM
schema rather than carry stub values that could fire bad rules.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Optional


# Module-level state. Cleared by _reset_for_test() in test runs.
_KERNEL = None       # singleton kernel instance
_AGENTS: dict = {}   # palace_path → agent instance
_WARNED: set = set() # one-time-per-process warning keys
_SML = None          # cached SML module (or None if unavailable)
_SML_LOAD_ATTEMPTED = False  # whether we've tried _load_sml() at least once


# Boost-tag → multiplier map. Compounded multiplicatively when multiple tags
# fire on the same hit. Final boost clamped to [0.1, 10.0] (see apply_soar_boosts).
BOOST_MULTIPLIERS: dict[str, float] = {
    "recency-boost": 1.25,   # ^recently-accessed "true" (age < 7d default)
    "same-project": 1.15,    # <m>.project == <context>.project
}

# Hardcoded operational limits (YAGNI on promoting to config knobs).
MAX_WM_HITS = 50          # Truncate input WM if more hits than this
DECISION_CYCLES = 50      # Upper bound on agent.RunSelf cycles
RECENCY_THRESHOLD_SEC = 7 * 24 * 3600  # 7 days for "recently-accessed"
BOOST_CLAMP = (0.1, 10.0)  # Min, max for final compound multiplier


def _warn_once(key: str, message: str) -> None:
    """Print a stderr warning ONCE per process for the given key."""
    if key in _WARNED:
        return
    _WARNED.add(key)
    print(f"[soar] {message}", file=sys.stderr)


def _load_sml():
    """Lazy import of Python_sml_ClientInterface. Returns the module or None.

    Respects CASTLE_SML_DISABLED=1 (testability knob) — returns None even
    when SML is importable. Caches the result in module-level _SML.
    """
    global _SML, _SML_LOAD_ATTEMPTED
    if _SML_LOAD_ATTEMPTED:
        return _SML
    _SML_LOAD_ATTEMPTED = True

    if os.environ.get("CASTLE_SML_DISABLED") == "1":
        _warn_once(
            "sml-disabled-env",
            "SML Python bindings not available (CASTLE_SML_DISABLED=1) — install Soar 9.6+ with SML or set CASTLE_SOAR_ENABLED=0",
        )
        return None

    try:
        import Python_sml_ClientInterface as sml  # type: ignore
        _SML = sml
        return sml
    except ImportError:
        _warn_once(
            "sml-import-failed",
            "SML Python bindings not available — install Soar 9.6+ with SML or set CASTLE_SOAR_ENABLED=0",
        )
        return None


def _reset_for_test() -> None:
    """Test-only helper: clear all module-level state.

    Used by the autouse `reset_soar_state` fixture in test_soar_bridge.py
    so sequential tests don't share kernel/agent state. NOT for production use.
    """
    global _KERNEL, _SML, _SML_LOAD_ATTEMPTED
    # Properly destroy any existing agents + kernel before nulling refs.
    if _KERNEL is not None:
        try:
            for agent in _AGENTS.values():
                _KERNEL.DestroyAgent(agent)
        except Exception:
            pass
        try:
            _KERNEL.Shutdown()
        except Exception:
            pass
    _AGENTS.clear()
    _KERNEL = None
    _SML = None
    _SML_LOAD_ATTEMPTED = False
    _WARNED.clear()


def apply_soar_boosts(hits: list[dict], cfg) -> list[dict]:
    """Post-pipeline boost-tag application.

    Args:
        hits: Search hits (typically from search_memories() result["results"]).
            Each hit must have at least: "id", "score", "wing", and optionally
            "created_at" (used to derive recency).
        cfg: Config object exposing .soar_enabled, .soar_rules_path, .palace_path.

    Returns:
        list[dict]: same hits with `score` adjusted by SOAR's compound multiplier
        and 3 new audit-trail fields appended to each hit:
        - soar_boost: float — the compound multiplier applied (1.0 if no tags fired)
        - soar_tags: list[str] — names of boost-tag rules that fired
        - score_pre_soar: float — original score before adjustment

    Never raises. Search continues with degraded behavior on Soar failure.
    On any failure (SML missing, kill switch, kernel/agent/rules error,
    truncation, unknown tag, etc.) prints a one-time-per-process stderr
    warning and returns hits unchanged (or partially boosted).
    """
    # Kill switch check (defensive — CLI/MCP layer should have caught this)
    if not cfg.soar_enabled:
        _warn_once(
            "kill-switch-disabled",
            f"apply_soar_boosts called with cfg.soar_enabled=False — returning hits unchanged",
        )
        return hits

    # Lazy SML import
    sml = _load_sml()
    if sml is None:
        return hits

    # Empty input → fast path
    if not hits:
        return hits

    # The rest of apply_soar_boosts is filled in by subsequent steps.
    # For now, return hits unchanged — tests that just verify scaffolding
    # (no-op when SML unavailable, kill switch) pass with this stub.
    return hits
```

- [ ] **Step 4: Run — confirm both always-run tests PASS**

```bash
pytest tests/test_soar_bridge.py -v
```

Expected: 2 passed (the always-run tests). No Soar-gated tests yet.

### Step group B: Add the 8 Soar-gated test scaffolds (red) + minimal happy-path impl (green for smoke test)

- [ ] **Step 5: Append the 8 Soar-gated test stubs to `tests/test_soar_bridge.py`**

Add at the end of the file:

```python
# ── Soar-required tests (skip if SML unavailable) ──────────────────────


def _write_minimal_rules(path):
    """Write a minimal castle-boost.soar with both production rules to `path`."""
    path.write_text("""
sp {castle-boost*recency-boost
    (state <s> ^io.input-link.memory <m>)
    (<m> ^recently-accessed true)
-->
    (<m> ^boost-tag recency-boost)
}

sp {castle-boost*same-project
    (state <s> ^io.input-link <il>)
    (<il> ^context.project <p>)
    (<il> ^memory <m>)
    (<m> ^project <p>)
-->
    (<m> ^boost-tag same-project)
}
""")


def _write_empty_rules(path):
    """Write an empty .soar file — agent loads no productions, no tags fire."""
    path.write_text("# empty\n")


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_loads_rules_and_runs_decision_cycle(tmp_path):
    """Smoke: SOAR kernel + agent + rule file load + decision cycle completes."""
    from cognitive_castle import soar_bridge
    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    hits = [
        {"id": "a", "score": 0.5, "wing": "proj", "created_at": "2026-05-13T00:00:00"},
        {"id": "b", "score": 0.4, "wing": "other", "created_at": "2020-01-01T00:00:00"},
    ]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    assert len(result) == 2
    assert all("soar_boost" in h for h in result)
    assert all("soar_tags" in h for h in result)
    assert all("score_pre_soar" in h for h in result)


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_returns_hits_unchanged_when_no_tags_fire(tmp_path):
    """Empty rule file → hits returned with soar_boost=1.0, soar_tags=[]."""
    from cognitive_castle import soar_bridge
    rules = tmp_path / "empty.soar"
    _write_empty_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    hits = [{"id": "a", "score": 0.5, "wing": "x"}]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    assert result[0]["soar_boost"] == 1.0
    assert result[0]["soar_tags"] == []
    assert result[0]["score_pre_soar"] == 0.5
    assert result[0]["score"] == 0.5  # unchanged


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_multiplies_score_for_recency_tag(tmp_path):
    """A hit with recently-accessed=true → recency-boost tag → score × 1.25."""
    from cognitive_castle import soar_bridge
    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    # created_at within 7 days → recently-accessed
    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 3600))
    hits = [{"id": "a", "score": 1.0, "wing": "p", "created_at": recent_iso}]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    assert "recency-boost" in result[0]["soar_tags"]
    assert result[0]["soar_boost"] == 1.25
    assert result[0]["score"] == 1.25


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_compounds_multiple_tags(tmp_path, monkeypatch):
    """A hit matching both rules → both tags fire → multipliers compound (1.25 × 1.15 = 1.4375)."""
    from cognitive_castle import soar_bridge
    monkeypatch.setenv("CASTLE_PROJECT", "demo-project")
    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 3600))
    hits = [{"id": "a", "score": 1.0, "wing": "demo-project", "created_at": recent_iso}]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    assert set(result[0]["soar_tags"]) == {"recency-boost", "same-project"}
    assert abs(result[0]["soar_boost"] - 1.4375) < 1e-6
    assert abs(result[0]["score"] - 1.4375) < 1e-6


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_clamps_to_range(tmp_path, monkeypatch):
    """Compounded multipliers > 10.0 → clamped to 10.0 upper bound."""
    from cognitive_castle import soar_bridge
    # Inject extreme multipliers to test the clamp
    monkeypatch.setitem(soar_bridge.BOOST_MULTIPLIERS, "recency-boost", 100.0)
    monkeypatch.setitem(soar_bridge.BOOST_MULTIPLIERS, "same-project", 100.0)
    monkeypatch.setenv("CASTLE_PROJECT", "demo")
    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    hits = [{"id": "a", "score": 1.0, "wing": "demo", "created_at": recent_iso}]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    # Compound would be 100×100=10000, clamped to 10.0
    assert result[0]["soar_boost"] == 10.0
    assert result[0]["score"] == 10.0


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_truncates_to_50_hits(tmp_path, capsys):
    """Input of 60 hits → WM populated with first 50; remaining 10 returned unboosted + stderr warning."""
    from cognitive_castle import soar_bridge
    soar_bridge._WARNED.clear()
    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))
    hits = [{"id": f"id{i}", "score": 0.5, "wing": "p"} for i in range(60)]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    assert len(result) == 60
    # First 50 have audit fields populated
    assert all("soar_boost" in h for h in result[:50])
    # Last 10 have soar_boost == 1.0 (unboosted) but still get audit fields with defaults
    for h in result[50:]:
        assert h.get("soar_boost", 1.0) == 1.0
        assert h.get("soar_tags", []) == []
    err = capsys.readouterr().err
    assert "truncated WM to 50" in err


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_clears_wm_between_calls(tmp_path):
    """Two sequential calls don't leak boost-tags from the first call into the second."""
    from cognitive_castle import soar_bridge
    rules = tmp_path / "rules.soar"
    _write_minimal_rules(rules)
    cfg = _mock_cfg(rules_path=str(rules))

    recent_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    # First call: hit gets recency-boost
    hits1 = [{"id": "first", "score": 1.0, "wing": "p", "created_at": recent_iso}]
    result1 = soar_bridge.apply_soar_boosts(hits1, cfg)
    assert "recency-boost" in result1[0]["soar_tags"]

    # Second call: hit does NOT have recently-accessed → no recency tag should fire
    old_iso = "2020-01-01T00:00:00"
    hits2 = [{"id": "second", "score": 1.0, "wing": "p", "created_at": old_iso}]
    result2 = soar_bridge.apply_soar_boosts(hits2, cfg)
    assert "recency-boost" not in result2[0]["soar_tags"]
    assert result2[0]["soar_boost"] == 1.0


@pytest.mark.soar
@_requires_sml
def test_apply_soar_boosts_unknown_tag_ignored_with_warning(tmp_path, capsys):
    """A rule that emits an unrecognized boost-tag → tag ignored, stderr warning once."""
    from cognitive_castle import soar_bridge
    soar_bridge._WARNED.clear()
    rules = tmp_path / "rules.soar"
    rules.write_text("""
sp {castle-boost*custom-tag
    (state <s> ^io.input-link.memory <m>)
-->
    (<m> ^boost-tag mystery-tag)
}
""")
    cfg = _mock_cfg(rules_path=str(rules))
    hits = [{"id": "a", "score": 1.0, "wing": "p"}]
    result = soar_bridge.apply_soar_boosts(hits, cfg)
    # mystery-tag isn't in BOOST_MULTIPLIERS → ignored, score unchanged
    assert result[0]["soar_boost"] == 1.0
    err = capsys.readouterr().err
    assert "unknown boost-tag" in err.lower()
    assert "mystery-tag" in err
```

- [ ] **Step 6: Run — confirm Soar-gated tests FAIL on the stub implementation**

```bash
pytest tests/test_soar_bridge.py -v -m soar
```

Expected: 8 Soar tests FAIL (the stub `apply_soar_boosts` doesn't yet populate `soar_boost` / `soar_tags` / `score_pre_soar` fields). 2 always-run tests still pass.

### Step group C: Implement the real apply_soar_boosts logic (green)

- [ ] **Step 7: Replace the stub `apply_soar_boosts` body with the full implementation**

In `cognitive_castle/soar_bridge.py`, replace the stub `return hits` at the end of `apply_soar_boosts` with the real logic. Add helper functions BEFORE `apply_soar_boosts`:

```python
def _get_kernel():
    """Return the singleton Soar kernel, creating it on first call."""
    global _KERNEL
    if _KERNEL is None:
        sml = _load_sml()
        if sml is None:
            return None
        try:
            _KERNEL = sml.Kernel.CreateKernelInNewThread()
        except Exception as e:
            _warn_once(
                "kernel-create-failed",
                f"kernel creation failed ({type(e).__name__}: {e}): boost-tags skipped",
            )
            return None
    return _KERNEL


def _get_agent(palace_path: str, rules_path: str):
    """Return the per-palace agent. First-time creation loads productions
    and enables EpMem + SMem subsystems.

    Returns None on any failure (stderr warning emitted).
    """
    if palace_path in _AGENTS:
        return _AGENTS[palace_path]

    kernel = _get_kernel()
    if kernel is None:
        return None

    # Agent name must be unique per kernel + safe characters
    agent_name = f"castle-{abs(hash(palace_path)) % 100_000_000}"
    try:
        agent = kernel.CreateAgent(agent_name)
    except Exception as e:
        _warn_once(
            "agent-create-failed",
            f"agent creation failed ({type(e).__name__}: {e}): boost-tags skipped",
        )
        return None

    # Load productions
    if not os.path.exists(rules_path):
        _warn_once(
            f"rules-not-found-{rules_path}",
            f"rule file not found: {rules_path}",
        )
        kernel.DestroyAgent(agent)
        return None

    try:
        agent.LoadProductions(rules_path)
        # LoadProductions returns a bool in SML; also expose via GetLastCommandLineResult
        if hasattr(agent, "GetLastCommandLineResult"):
            result = agent.GetLastCommandLineResult()
            if "error" in str(result).lower() and "syntax" in str(result).lower():
                _warn_once(
                    f"rules-parse-failure",
                    f"rule parse failure: {result}",
                )
                kernel.DestroyAgent(agent)
                return None
    except Exception as e:
        _warn_once(
            "rules-load-failed",
            f"rule load failed ({type(e).__name__}: {e})",
        )
        kernel.DestroyAgent(agent)
        return None

    # Enable EpMem + SMem subsystems (PR #4c will use them; #4a just configures)
    try:
        agent.ExecuteCommandLine("epmem --set learning on")
        agent.ExecuteCommandLine("smem --set learning on")
    except Exception:
        # Non-fatal — log but don't fail
        _warn_once(
            "epmem-smem-config-failed",
            "EpMem/SMem subsystem configuration failed (boost-tags still work)",
        )

    _AGENTS[palace_path] = agent
    return agent


def _push_working_memory(agent, hits: list[dict]) -> dict:
    """Push input-link WMEs for the given hits. Returns mapping hit_id → memory WME handle.

    Schema (matches castle-boost.soar):
      ^io.input-link.context.{project, query}
      ^io.input-link.memory[]  with id, project, score, age-seconds, recently-accessed
    """
    input_link = agent.GetInputLink()
    project = os.environ.get("CASTLE_PROJECT", "default")

    # Push context
    context_wme = input_link.CreateIdWME("context")
    context_wme.CreateStringWME("project", project)
    # Skip the query string for #4a — rules don't read it. Add in future PRs.

    # Push one ^memory WME per hit
    memory_wmes = {}  # composite_id → WME handle
    now = time.time()
    for hit in hits:
        m = input_link.CreateIdWME("memory")
        composite_id = f"{hit.get('wing','')}/{hit.get('room','')}/{hit.get('source_file','?')}"
        m.CreateStringWME("id", composite_id)
        m.CreateStringWME("project", hit.get("wing", ""))
        m.CreateFloatWME("score", float(hit.get("score", 0.0)))

        # Compute age-seconds from created_at if present
        age_sec = _compute_age_seconds(hit.get("created_at"), now)
        m.CreateIntWME("age-seconds", int(age_sec))

        # ^recently-accessed: "true" (string symbol — Soar matches `^recently-accessed true`)
        recent = "true" if age_sec < RECENCY_THRESHOLD_SEC else "false"
        m.CreateStringWME("recently-accessed", recent)

        memory_wmes[composite_id] = m

    agent.Commit()
    return memory_wmes


def _compute_age_seconds(created_at_iso: Optional[str], now: float) -> float:
    """Compute age in seconds from ISO timestamp. Returns large value if missing/invalid."""
    if not created_at_iso:
        return float("inf")
    try:
        # Parse ISO 8601 — Python 3.11+ supports "Z" suffix, earlier needs handling.
        from datetime import datetime
        # Handle both "2026-05-13T00:00:00" and "2026-05-13T00:00:00Z"
        ts = created_at_iso.rstrip("Z")
        dt = datetime.fromisoformat(ts)
        return max(0.0, now - dt.timestamp())
    except (ValueError, TypeError):
        return float("inf")


def _read_boost_tags(memory_wmes: dict) -> dict:
    """Read back ^boost-tag attributes from each ^memory WME. Returns id → list[tag]."""
    tags_by_id = {}
    for composite_id, m in memory_wmes.items():
        tags = []
        # Iterate children of m — SML Python exposes this via GetNumberChildren + GetChild
        n = m.GetNumberChildren()
        for i in range(n):
            child = m.GetChild(i)
            if child.GetAttribute() == "boost-tag":
                # Boost-tag value is a string symbol
                tags.append(child.GetValueAsString())
        tags_by_id[composite_id] = tags
    return tags_by_id


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
```

Then replace the stub end of `apply_soar_boosts` (after the `if not hits: return hits` line) with:

```python
    # Truncate to MAX_WM_HITS if needed
    truncated_remainder = []
    if len(hits) > MAX_WM_HITS:
        truncated_remainder = hits[MAX_WM_HITS:]
        _warn_once(
            "wm-truncated",
            f"truncated WM to {MAX_WM_HITS} hits (input was {len(hits)}); remainder unboosted",
        )
        hits = hits[:MAX_WM_HITS]

    # Get agent (lazy-init per palace)
    agent = _get_agent(cfg.palace_path, cfg.soar_rules_path)
    if agent is None:
        # Failure already logged; return hits with neutral audit fields
        return _annotate_unboosted(hits + truncated_remainder)

    # Clear prior WM
    try:
        agent.GetInputLink().DestroyAllWMEs()
    except Exception as e:
        _warn_once("wm-clear-failed", f"WM clear failed ({type(e).__name__}: {e})")
        return _annotate_unboosted(hits + truncated_remainder)

    # Build composite_id keys for hit lookup
    composite_ids = [
        f"{h.get('wing','')}/{h.get('room','')}/{h.get('source_file','?')}"
        for h in hits
    ]

    # Push WM
    try:
        memory_wmes = _push_working_memory(agent, hits)
    except Exception as e:
        _warn_once("wm-push-failed", f"WM push failed ({type(e).__name__}: {e})")
        return _annotate_unboosted(hits + truncated_remainder)

    # Run decision cycle
    try:
        agent.RunSelf(DECISION_CYCLES)
    except Exception as e:
        _warn_once("decision-cycle-failed", f"decision cycle failed ({type(e).__name__}: {e})")
        return _annotate_unboosted(hits + truncated_remainder)

    # Read back tags
    try:
        tags_by_id = _read_boost_tags(memory_wmes)
    except Exception as e:
        _warn_once("read-tags-failed", f"read-tags failed ({type(e).__name__}: {e})")
        return _annotate_unboosted(hits + truncated_remainder)

    # Apply multipliers + augment audit fields
    any_tags_fired = False
    for hit, cid in zip(hits, composite_ids):
        tags = tags_by_id.get(cid, [])
        recognized = []
        compound = 1.0
        for tag in tags:
            mul = BOOST_MULTIPLIERS.get(tag)
            if mul is None:
                _warn_once(
                    f"unknown-tag-{tag}",
                    f"unknown boost-tag '{tag}' — add to BOOST_MULTIPLIERS or check rule output",
                )
                continue
            compound *= mul
            recognized.append(tag)
        compound = _clamp(compound, *BOOST_CLAMP)
        if recognized:
            any_tags_fired = True
        hit["score_pre_soar"] = hit["score"]
        hit["soar_boost"] = compound
        hit["soar_tags"] = recognized
        hit["score"] = hit["score"] * compound

    if not any_tags_fired:
        # Not an error — just informational. Don't warn-once because empty rule
        # files are a legitimate test case.
        pass

    # Combine boosted hits with truncated remainder
    return hits + _annotate_unboosted(truncated_remainder)


def _annotate_unboosted(hits: list[dict]) -> list[dict]:
    """Annotate hits with neutral audit fields (no boost applied)."""
    for h in hits:
        h.setdefault("score_pre_soar", h.get("score", 0.0))
        h.setdefault("soar_boost", 1.0)
        h.setdefault("soar_tags", [])
    return hits
```

- [ ] **Step 8: Run — confirm all 10 tests PASS**

```bash
pytest tests/test_soar_bridge.py -v
```

Expected: 10 passed (2 always-run + 8 Soar-gated).

If any Soar test fails, the most likely cause is an SML API method name mismatch (e.g., `CreateStringWME` vs `CreateString`). The SML Python API is at `/home/lbihari/soar-work/Soar/build/Core/ClientSMLSWIG/python/Python_sml_ClientInterface.py` — grep for method names if needed:

```bash
grep -n "def Create" /home/lbihari/soar-work/Soar/build/Core/ClientSMLSWIG/python/Python_sml_ClientInterface.py | head -20
```

- [ ] **Step 9: Run full test suite — no NEW regressions**

```bash
pytest tests/ -v --ignore=tests/benchmarks
```

Expected: previous-passing-count + 10 new tests. Pre-existing CI-UNSTABLE failures acceptable.

- [ ] **Step 10: Lint**

```bash
ruff check cognitive_castle/soar_bridge.py tests/test_soar_bridge.py
ruff format --check cognitive_castle/soar_bridge.py tests/test_soar_bridge.py
```

- [ ] **Step 11: Commit**

```bash
git add cognitive_castle/soar_bridge.py tests/test_soar_bridge.py
git commit -m "$(cat <<'EOF'
feat(soar): add SOAR post-pipeline boost-tag bridge (PR #4a)

cognitive_castle/soar_bridge.py: apply_soar_boosts(hits, cfg) — runs
Soar elaboration productions over input-link memory WMEs, reads back
i-supported ^boost-tag attributes, applies BOOST_MULTIPLIERS to hit
scores. Audit fields (soar_boost, soar_tags, score_pre_soar) added to
each hit for explainability.

Singleton kernel + per-palace agent (lazy-loaded). EpMem + SMem
subsystems enabled at agent creation (preparation for #4c chunking,
unused in #4a). Truncates to MAX_WM_HITS=50 with stderr warning.
Boost clamped to [0.1, 10.0]. One-time-per-process warnings via
_WARNED set. _reset_for_test() helper used by autouse pytest fixture
to prevent cross-test state leakage.

10 unit tests in tests/test_soar_bridge.py: 8 Soar-gated (auto-skip if
SML missing) + 2 always-run (SML-unavailable + kill-switch). All
respect the autouse reset_soar_state fixture.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Build `cognitive_castle/rules/castle-boost.soar`

**Files:**
- Create: `cognitive_castle/rules/castle-boost.soar`
- Create: `cognitive_castle/rules/__init__.py` (empty, so the rules dir is importable as a package data dir)

Task 4's `_get_agent` defaults to loading the package-shipped rule file. Without it, the live-smoke and default-rules-path tests fail.

- [ ] **Step 1: Create the rules directory + empty `__init__.py`**

Run:
```bash
mkdir -p /home/lbihari/cognitive-castle/cognitive_castle/rules
touch /home/lbihari/cognitive-castle/cognitive_castle/rules/__init__.py
```

- [ ] **Step 2: Create the rule file**

Create `cognitive_castle/rules/castle-boost.soar`:

```
##
## castle-boost.soar — Initial production set for PR #4a (2 rules)
##
## Schema (pushed to input-link by soar_bridge.py):
##   state ^io.input-link <il>
##   <il>  ^context <ctx>
##         ^memory  <m>     (one per hit, up to 50)
##   <ctx> ^project       <string>
##   <m>   ^id                <string>  (composite: wing/room/source_file)
##         ^project           <string>  (from hit.wing)
##         ^score             <float>   (Stage 3+4 score)
##         ^age-seconds       <int>
##         ^recently-accessed true|false
##
## Each matching production adds an i-supported ^boost-tag to <m>.
## The Python bridge maps tags → BOOST_MULTIPLIERS → compounded score boost.
##
## Follow-up PRs add entity-match, correction-priority, stale-penalty
## rules as the supporting data lands (hit-provenance from fusion.py,
## drawer-type metadata, EpMem access-counts).
##

sp {castle-boost*recency-boost
    (state <s> ^io.input-link.memory <m>)
    (<m> ^recently-accessed true)
-->
    (<m> ^boost-tag recency-boost)
}

sp {castle-boost*same-project
    (state <s> ^io.input-link <il>)
    (<il> ^context.project <p>)
    (<il> ^memory <m>)
    (<m> ^project <p>)
-->
    (<m> ^boost-tag same-project)
}
```

- [ ] **Step 3: Verify the rule file parses by loading it via a quick standalone test**

Run:
```bash
python -c "
import Python_sml_ClientInterface as sml
k = sml.Kernel.CreateKernelInNewThread()
a = k.CreateAgent('parse-check')
a.LoadProductions('/home/lbihari/cognitive-castle/cognitive_castle/rules/castle-boost.soar')
result = a.GetLastCommandLineResult() if hasattr(a, 'GetLastCommandLineResult') else 'ok'
print(f'Load result: {result}')
print('Production count:', a.ExecuteCommandLine('print --internal'))  # debug only
k.DestroyAgent(a)
k.Shutdown()
"
```

Expected: load result contains no "error" or "syntax" strings; production count output shows 2 rules.

- [ ] **Step 4: Run the Soar-gated tests again with the real rule file**

Re-run with the shipped rules path (not tmp tests):

```bash
pytest tests/test_soar_bridge.py -v -m soar
```

Expected: all 8 still pass (tests use `tmp_path` rules; the shipped rule file is used at runtime by `_get_agent`).

- [ ] **Step 5: Commit**

```bash
git add cognitive_castle/rules/__init__.py cognitive_castle/rules/castle-boost.soar
git commit -m "$(cat <<'EOF'
feat(soar): add castle-boost.soar with 2 initial productions

Initial production set for PR #4a:
- castle-boost*recency-boost (matches ^recently-accessed true)
- castle-boost*same-project (matches <m>.project == <context>.project)

Each emits an i-supported ^boost-tag attribute on the matching memory
WME. soar_bridge.py reads tags back, maps via BOOST_MULTIPLIERS
(recency-boost=1.25, same-project=1.15), applies compounded score boost.

Follow-up PRs add entity-match, correction-priority, stale-penalty
rules as the supporting data fields land.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Extract `_print_search_results` from `searcher.search()`

This refactor is required so `cmd_search` can call `search_memories()` directly when `--soar-boost` is on, apply SOAR boosts, then print using the same formatter as the default path.

**Files:**
- Modify: `cognitive_castle/searcher.py` (extract a helper from `search()` and refactor `search()` to use it)

NOTE: this is NOT touching the 3-stage pipeline. It's pure output-formatting refactor.

- [ ] **Step 1: Locate `search()` in searcher.py**

Run:
```bash
grep -n "^def search\b" /home/lbihari/cognitive-castle/cognitive_castle/searcher.py
```

Expected: a line like `def search(query, palace_path, ...):` around line 145.

- [ ] **Step 2: Inspect what `search()` prints**

Read lines 145-200 of `searcher.py` (the body of `search()`). The current implementation calls `_new_pipeline_search(...)` then iterates results to print them. Identify the printing block — typically starts with `print("====")` or similar.

- [ ] **Step 3: Extract a `_print_search_results(result)` helper**

Add a new module-level function `_print_search_results(result: dict, query: str) -> None` that takes the dict returned by `search_memories()` and prints in the same format `search()` currently does. The printing logic — header, per-result block with separator, "no results" message — moves into this helper.

The exact body depends on what `search()` currently prints. Inspect first, then extract.

After extraction, `search()` should look approximately like:

```python
def search(query, palace_path, wing=None, room=None, n_results=5, llm_rerank=False):
    """Print-style CLI search. Calls search_memories() internally and prints."""
    try:
        result = search_memories(
            query=query, palace_path=palace_path, wing=wing, room=room,
            n_results=n_results, llm_rerank=llm_rerank,
        )
    except Exception as e:
        raise SearchError(str(e)) from e
    _print_search_results(result, query)
```

- [ ] **Step 4: Run searcher tests + cli tests to verify no regression**

```bash
pytest tests/test_searcher.py tests/test_cli.py -v
```

Expected: all previously-passing tests still pass.

- [ ] **Step 5: Lint**

```bash
ruff check cognitive_castle/searcher.py && ruff format --check cognitive_castle/searcher.py
```

- [ ] **Step 6: Commit**

```bash
git add cognitive_castle/searcher.py
git commit -m "$(cat <<'EOF'
refactor(searcher): extract _print_search_results helper from search()

No behavior change. The print logic in search() is extracted to a
helper so cmd_search can call search_memories() directly (returning
the dict), apply post-pipeline operations (PR #4a's SOAR boost-tags),
and then format output identical to search().

This is NOT a 3-stage pipeline touch — pure output-formatting refactor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Add `--soar-boost` CLI flag + kill-switch + SOAR-path branch in `cmd_search`

**Files:**
- Modify: `cognitive_castle/cli.py` (add argparse flag + restructure `cmd_search`)
- Modify: `tests/test_cli.py` (append 2 new tests)

- [ ] **Step 1: Write the 2 failing tests**

Append to `tests/test_cli.py`:

```python
def test_search_cli_soar_boost_flag_propagates(monkeypatch):
    """`castle search --soar-boost` calls apply_soar_boosts when soar_enabled=True."""
    import argparse
    from unittest.mock import MagicMock, patch
    from cognitive_castle.cli import cmd_search

    monkeypatch.setenv("CASTLE_SOAR_ENABLED", "1")
    fake_result = {"results": [{"id": "a", "score": 0.5}], "query": "x", "filters": {}}
    spy = MagicMock(return_value=[{"id": "a", "score": 0.625, "soar_boost": 1.25, "soar_tags": ["recency-boost"], "score_pre_soar": 0.5}])

    args = argparse.Namespace(
        query="x", palace=None, wing=None, room=None, results=5,
        llm_rerank=False, soar_boost=True,
    )

    with patch("cognitive_castle.cli.search_memories", return_value=fake_result), \
         patch("cognitive_castle.soar_bridge.apply_soar_boosts", spy):
        cmd_search(args)
    spy.assert_called_once()
    # First positional arg is the hits list
    assert spy.call_args.args[0] == fake_result["results"]


def test_search_cli_soar_boost_with_kill_switch_exits_2(monkeypatch, capsys):
    """`--soar-boost` + CASTLE_SOAR_ENABLED=0 → sys.exit(2) + clear stderr."""
    import argparse
    import pytest
    from cognitive_castle.cli import cmd_search

    monkeypatch.setenv("CASTLE_SOAR_ENABLED", "0")
    args = argparse.Namespace(
        query="x", palace=None, wing=None, room=None, results=5,
        llm_rerank=False, soar_boost=True,
    )
    with pytest.raises(SystemExit) as exc:
        cmd_search(args)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "CASTLE_SOAR_ENABLED=0 kill switch is active" in err
```

- [ ] **Step 2: Run — confirm FAIL**

```bash
pytest tests/test_cli.py -v -k soar_boost
```

Expected: 2 tests FAIL with `AttributeError: 'Namespace' object has no attribute 'soar_boost'` or similar (since cmd_search doesn't read it yet).

- [ ] **Step 3: Add `--soar-boost` to the argparse setup**

In `cognitive_castle/cli.py`, find the `p_search = sub.add_parser("search", ...)` block. After the existing `--llm-rerank` argument added by PR #3, append:

```python
    p_search.add_argument(
        "--soar-boost",
        action="store_true",
        help=(
            "Apply SOAR symbolic-rule boost-tags to final scores "
            "(experimental; requires Soar 9.6+ + SML Python bindings "
            "installed; activate via CASTLE_SOAR_ENABLED=1). Off by default."
        ),
    )
```

- [ ] **Step 4: Restructure `cmd_search` to handle the SOAR-boost branch**

Find `cmd_search` at `cli.py:582`. Replace its current body with:

```python
def cmd_search(args):
    from .searcher import search, search_memories, SearchError, _print_search_results
    from .config import CognitiveCastleConfig

    cfg = CognitiveCastleConfig()
    soar_boost = getattr(args, "soar_boost", False)

    # Kill-switch check: --soar-boost requires CASTLE_SOAR_ENABLED=1
    if soar_boost and not cfg.soar_enabled:
        print(
            "CASTLE_SOAR_ENABLED=0 kill switch is active; remove it to use --soar-boost",
            file=sys.stderr,
        )
        sys.exit(2)

    palace_path = (
        os.path.expanduser(args.palace) if args.palace else cfg.palace_path
    )

    try:
        if soar_boost:
            # SOAR path: call search_memories directly, apply boosts, format output.
            result = search_memories(
                query=args.query,
                palace_path=palace_path,
                wing=args.wing,
                room=args.room,
                n_results=args.results,
                llm_rerank=getattr(args, "llm_rerank", False),
            )
            hits = result.get("results", [])
            if hits:
                # LAZY IMPORT (per spec acceptance #14): soar_bridge module
                # is only loaded when --soar-boost is actually used.
                from .soar_bridge import apply_soar_boosts
                hits = apply_soar_boosts(hits, cfg)
                hits.sort(key=lambda h: -h.get("score", 0.0))
                result["results"] = hits
            _print_search_results(result, args.query)
        else:
            # Default path: unchanged.
            search(
                query=args.query,
                palace_path=palace_path,
                wing=args.wing,
                room=args.room,
                n_results=args.results,
                llm_rerank=getattr(args, "llm_rerank", False),
            )
    except SearchError:
        sys.exit(1)
```

NOTE: this requires `_print_search_results` to be exported from `searcher.py` (Task 6 made it module-level — no underscore visibility issue for internal imports).

NOTE 2: The test in Step 1 uses `patch("cognitive_castle.cli.search_memories", ...)` — this requires `search_memories` to be importable from `cognitive_castle.cli`. The `from .searcher import ... search_memories ...` line above puts it in the cli module namespace, making the patch target valid.

- [ ] **Step 5: Run tests — confirm both PASS**

```bash
pytest tests/test_cli.py -v -k soar_boost
```

Expected: 2 passed.

- [ ] **Step 6: Verify `--help` shows the new flag**

```bash
castle search --help 2>&1 | grep -A2 "soar-boost"
```

Expected: `--soar-boost` flag with the help text from Step 3.

- [ ] **Step 7: Run full default suite — no NEW regressions**

```bash
pytest tests/ -v --ignore=tests/benchmarks
```

- [ ] **Step 8: Lint**

```bash
ruff check cognitive_castle/cli.py tests/test_cli.py && ruff format --check cognitive_castle/cli.py tests/test_cli.py
```

- [ ] **Step 9: Verify the lazy-import discipline (Acceptance #14 prep)**

```bash
python -X importtime -c "from cognitive_castle import cli" 2>&1 | grep soar_bridge
```

Expected: NO output (soar_bridge is NOT imported when cli.py is loaded).

```bash
python -X importtime -c "
import argparse
from cognitive_castle.cli import cmd_search
" 2>&1 | grep soar_bridge
```

Expected: still no output (just importing cmd_search doesn't trigger soar_bridge).

- [ ] **Step 10: Commit**

```bash
git add cognitive_castle/cli.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(cli): add --soar-boost flag with kill-switch + lazy import

Store-true flag, default False. When passed AND CASTLE_SOAR_ENABLED=1:
cmd_search calls search_memories() directly (not search()), applies
apply_soar_boosts() to the result["results"] list, re-sorts by adjusted
score, formats output via the extracted _print_search_results helper.

Kill switch: --soar-boost + CASTLE_SOAR_ENABLED=0 → sys.exit(2) with
clear stderr, BEFORE any palace work happens.

Lazy import discipline: `from .soar_bridge import apply_soar_boosts`
is INSIDE the conditional branch, NOT at module top, so soar_bridge
is never loaded for default-path users (verifiable via Acceptance #14).

2 new tests cover flag propagation + kill-switch exit code.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Add `soar_boost` MCP param + lazy import in `tool_search`

**Files:**
- Modify: `cognitive_castle/mcp_server.py` (add tool schema entry + handler logic)
- Modify: `tests/test_mcp_server.py` (1 new test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mcp_server.py`:

```python
def test_mcp_castle_search_soar_boost_threads_through(monkeypatch):
    """MCP castle_search with soar_boost:true reaches apply_soar_boosts handler."""
    from unittest.mock import MagicMock, patch
    from cognitive_castle.mcp_server import tool_search

    monkeypatch.setenv("CASTLE_SOAR_ENABLED", "1")
    fake_hits = [{"id": "a", "score": 0.5, "wing": "w", "room": "r", "source_file": "f"}]
    fake_result = {"results": fake_hits, "query": "x", "filters": {}}
    spy = MagicMock(return_value=[{"id": "a", "score": 0.625, "soar_boost": 1.25, "soar_tags": ["recency-boost"], "score_pre_soar": 0.5}])

    with patch("cognitive_castle.mcp_server.search_memories", return_value=fake_result), \
         patch("cognitive_castle.soar_bridge.apply_soar_boosts", spy):
        result = tool_search(query="x", soar_boost=True)
    spy.assert_called_once()
    # Result has the boosted hit
    assert result.get("results", [])[0]["soar_boost"] == 1.25
```

- [ ] **Step 2: Run — confirm FAIL**

```bash
pytest tests/test_mcp_server.py -v -k soar_boost
```

Expected: FAIL with `TypeError: tool_search() got an unexpected keyword argument 'soar_boost'`.

- [ ] **Step 3: Add `soar_boost` param + handler logic**

In `cognitive_castle/mcp_server.py`, find `def tool_search(...)` at line 370. Add `soar_boost: bool = False` as the last keyword argument.

Then, after the existing block where `hits = result.get("results")` is read (around line 414), insert the SOAR-boost handling:

```python
    # SOAR post-pipeline boost-tags (PR #4a, opt-in via soar_boost param)
    if soar_boost:
        if not _config.soar_enabled:
            # Kill switch — surface error in MCP response
            result["error"] = (
                "CASTLE_SOAR_ENABLED=0 kill switch is active; remove it to use soar_boost"
            )
            result["soar_boost_skipped"] = True
        elif hits:
            # LAZY IMPORT (per spec acceptance #14)
            from .soar_bridge import apply_soar_boosts
            adjusted = apply_soar_boosts(hits, _config)
            adjusted.sort(key=lambda h: -h.get("score", 0.0))
            result["results"] = adjusted
```

The exact placement depends on the existing handler's flow — insert AFTER any existing post-processing (like the `sanitized["was_sanitized"]` block) but BEFORE the final return.

- [ ] **Step 4: Also add `soar_boost` to the MCP tool input schema**

Find the `TOOLS` dict or wherever `castle_search` tool's input schema is defined in `mcp_server.py`. Search for `"castle_search"` and the adjacent `"input_schema"` block. Inside the `properties` dict, alongside the existing `llm_rerank` property (added in PR #3), add:

```python
                "soar_boost": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Apply SOAR symbolic-rule boost-tags to final scores "
                        "(experimental; requires Soar 9.6+ + SML Python bindings "
                        "installed; activate via CASTLE_SOAR_ENABLED=1). Off by default."
                    ),
                },
```

- [ ] **Step 5: Run test — confirm PASS**

```bash
pytest tests/test_mcp_server.py -v -k soar_boost
```

Expected: 1 passed.

- [ ] **Step 6: Verify MCP schema includes the new property**

```bash
python -c "
from cognitive_castle.mcp_server import TOOLS
sm = next((t for t in TOOLS if t.get('name') == 'castle_search'), None)
if sm is None:
    sm = TOOLS.get('castle_search') if isinstance(TOOLS, dict) else None
props = sm.get('input_schema', sm.get('inputSchema', {})).get('properties', {})
print('soar_boost present:', 'soar_boost' in props)
print('  type:', props['soar_boost'].get('type') if 'soar_boost' in props else 'N/A')
print('  default:', props['soar_boost'].get('default') if 'soar_boost' in props else 'N/A')
"
```

Expected: `soar_boost present: True`, `type: boolean`, `default: False`.

- [ ] **Step 7: Run full default suite — no NEW regressions**

```bash
pytest tests/ -v --ignore=tests/benchmarks
```

- [ ] **Step 8: Verify lazy-import discipline for MCP startup**

```bash
python -X importtime -c "from cognitive_castle.mcp_server import tool_search" 2>&1 | grep soar_bridge
```

Expected: NO output (soar_bridge isn't loaded when MCP server starts).

- [ ] **Step 9: Lint**

```bash
ruff check cognitive_castle/mcp_server.py tests/test_mcp_server.py && ruff format --check cognitive_castle/mcp_server.py tests/test_mcp_server.py
```

- [ ] **Step 10: Commit**

```bash
git add cognitive_castle/mcp_server.py tests/test_mcp_server.py
git commit -m "$(cat <<'EOF'
feat(mcp): add soar_boost param to castle_search tool

Optional boolean MCP param, default false. When true AND
cfg.soar_enabled, the handler:
1. Calls search_memories() as today
2. Lazy-imports soar_bridge + calls apply_soar_boosts on result["results"]
3. Re-sorts by adjusted score before returning

Kill switch: if soar_boost requested but CASTLE_SOAR_ENABLED=0, the
response includes an error field rather than raising — MCP handlers
can't sys.exit. Hits are returned unboosted in that case.

Lazy import discipline: `from .soar_bridge import apply_soar_boosts`
is INSIDE the conditional branch, so MCP server startup doesn't load
soar_bridge unless a request actually uses the flag (verifiable via
python -X importtime).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Update CLAUDE.md + README.md

**Files:**
- Modify: `CLAUDE.md` (update retrieval pipeline diagram around line 175-185 to show optional Stage 5)
- Modify: `README.md` (append "Experimental: SOAR symbolic re-ranking" subsection inside the existing "Going further" block)

- [ ] **Step 1: Update CLAUDE.md retrieval pipeline diagram**

Find the retrieval pipeline diagram in CLAUDE.md (around line 175-185). After Stage 4's optional LLM-judge entry added by PR #3, append a Stage 5 entry. The result should look like:

```
Retrieval pipeline (3-stage default, with up to 2 optional opt-in stages):
  Query
    ├── Stage 1 (parallel recall, ~top-100 each):
    │     ├── Dense vector search
    │     ├── Sparse FTS search
    │     └── KG-hop
    ├── Stage 2: weighted RRF + recency multiplier → top-K
    ├── Stage 3: cross-encoder rerank → top-N candidates
    ├── Stage 4 (optional, opt-in via --llm-rerank or llm_rerank:true MCP param):
    │     LLM-as-judge re-ranks top-cfg.llm_judge_top_n (default 10) from Stage 3
    │     → graceful identity-order fallback on any LLM failure
    └── Stage 5 (optional, opt-in via --soar-boost AND CASTLE_SOAR_ENABLED=1):
          SOAR symbolic productions add boost-tags to final hits
          → multiplicative score adjustment with audit-trail fields
          → graceful pass-through on any Soar failure
```

The exact line edits depend on what the current diagram looks like — read CLAUDE.md and adapt.

- [ ] **Step 2: Update README.md "Going further" block**

Inside the existing "Going further" block (from PR #1 + PR #3), append a new subsection BEFORE the closing `---` separator:

```markdown

### Experimental: SOAR symbolic re-ranking (`--soar-boost`)

SOAR is a symbolic cognitive architecture from Carnegie Mellon (production rules + working memory + chunking-based learning). Castle uses it as an **optional, opt-in, post-pipeline boost-tag layer**: after Stage 3 (cross-encoder rerank) and optional Stage 4 (LLM-judge), SOAR productions can re-weight hits using hand-crafted rules.

This is research-grade — default users should ignore. Real value lands in #4c when chunking is wired up so SOAR can learn rules from impasses over time.

**Prerequisites:**
1. Build Soar 9.6+ from source with SML Python bindings: https://github.com/SoarGroup/Soar
2. Ensure `python -c "import Python_sml_ClientInterface"` succeeds in your environment
3. Set `CASTLE_SOAR_ENABLED=1` (kill switch — must be explicitly enabled)

**Usage:**
```bash
CASTLE_SOAR_ENABLED=1 castle search "your query" --soar-boost
```

The two initial production rules (in `cognitive_castle/rules/castle-boost.soar`):
- `recency-boost`: drawer accessed within 7 days → `score × 1.25`
- `same-project`: drawer's wing matches `CASTLE_PROJECT` env → `score × 1.15`

These compound multiplicatively. Final boost is clamped to `[0.1, 10.0]`.

**Audit trail:** every boosted hit gains 3 new fields so every score change has a name (the differentiating value over neural rerankers):

```json
{
  "score": 1.4375,
  "score_pre_soar": 1.0,
  "soar_boost": 1.4375,
  "soar_tags": ["recency-boost", "same-project"]
}
```

**Kill switch:** if you set `CASTLE_SOAR_ENABLED=0` but pass `--soar-boost`, Castle exits with code 2 + a clear stderr message rather than silently degrading.

**MCP:** Claude Code and other MCP clients can pass `soar_boost: true` to the `castle_search` tool. Same kill-switch rule applies.

**Custom rules:** point `CASTLE_SOAR_RULES_PATH` at your own `.soar` file to extend or replace the production set.
```

- [ ] **Step 3: Verify the README section landed**

```bash
grep -E "Experimental: SOAR|--soar-boost|CASTLE_SOAR_ENABLED" /home/lbihari/cognitive-castle/README.md | head -10
```

Expected: multiple matches — section heading, CLI usage, env var docs.

- [ ] **Step 4: Verify CLAUDE.md diagram updated**

```bash
grep -B1 -A3 "Stage 5" /home/lbihari/cognitive-castle/CLAUDE.md | head -10
```

Expected: Stage 5 entry visible, "optional" annotation.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "$(cat <<'EOF'
docs: document SOAR Stage 5 in CLAUDE.md + README

CLAUDE.md retrieval pipeline diagram now shows 5 stages — Stage 4
(LLM-judge from PR #3) and Stage 5 (SOAR boost-tags from PR #4a) both
marked optional with their opt-in mechanisms.

README "Going further" block gains "Experimental: SOAR symbolic
re-ranking" subsection covering: what SOAR is (1-sentence intro), why
experimental, build-from-source prerequisites, how to enable
(CASTLE_SOAR_ENABLED=1 + --soar-boost), the 2 initial rules + their
multipliers, audit-trail field shape, kill switch, MCP equivalent,
custom rules via CASTLE_SOAR_RULES_PATH.

Strong note that this is research-grade — default users should ignore.
Real value lands in #4c when chunking is wired up.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Live smoke (happy + kill switch + SML disabled + default unchanged)

Four manual smoke runs that exercise the live end-to-end path. Capture results for the PR description.

**Files:** none (filesystem + Soar + Castle only)

- [ ] **Step 1: Prepare a smoke palace**

Run:
```bash
rm -rf /tmp/castle-soar-smoke
mkdir -p /tmp/castle-soar-smoke/palace /tmp/castle-soar-smoke/src
cat > /tmp/castle-soar-smoke/src/auth.md <<'EOF'
# Authentication architecture

We use JWT tokens for stateless auth. Tokens are signed with RS256 and rotated every 24h.
EOF
cat > /tmp/castle-soar-smoke/src/database.md <<'EOF'
# Database

Postgres 16 primary, read replicas in two AZs.
EOF
castle reindex --palace /tmp/castle-soar-smoke/palace --sources /tmp/castle-soar-smoke/src --yes
```

Expected: reindex completes, 2 drawers filed.

- [ ] **Step 2: Smoke #1 — happy path (Soar enabled)**

```bash
CASTLE_SOAR_ENABLED=1 CASTLE_PALACE_PATH=/tmp/castle-soar-smoke/palace \
  CASTLE_PROJECT=castle-soar-smoke \
  castle search "authentication" --soar-boost 2>&1 | head -25
```

Expected:
- Completes successfully
- Output shows hits with adjusted scores
- No `[soar] ...` stderr warnings (rules loaded, decision cycle ran)
- (Optional) verbose inspection — score values reflect 1.25 multiplier for recently-mined drawers

Record the output for the PR description.

- [ ] **Step 3: Smoke #2 — kill switch**

```bash
CASTLE_SOAR_ENABLED=0 CASTLE_PALACE_PATH=/tmp/castle-soar-smoke/palace \
  castle search "authentication" --soar-boost
echo "exit: $?"
```

Expected:
- Exits with code 2
- Stderr contains `CASTLE_SOAR_ENABLED=0 kill switch is active`
- No search results printed

- [ ] **Step 4: Smoke #3 — SML disabled simulation**

```bash
CASTLE_SML_DISABLED=1 CASTLE_SOAR_ENABLED=1 \
  CASTLE_PALACE_PATH=/tmp/castle-soar-smoke/palace \
  castle search "authentication" --soar-boost 2>&1 | head -20
```

Expected:
- Completes successfully (returns hits unchanged)
- Stderr contains `[soar] SML Python bindings not available`
- Hits don't have `soar_boost` audit fields

- [ ] **Step 5: Smoke #4 — default behavior unchanged**

```bash
unset CASTLE_SOAR_ENABLED CASTLE_SML_DISABLED CASTLE_PROJECT
CASTLE_PALACE_PATH=/tmp/castle-soar-smoke/palace \
  castle search "authentication" 2>&1 | head -20
```

Expected:
- Completes normally
- No `[soar] ...` stderr lines
- No `soar_boost` fields in output
- Identical output to running `castle search "authentication"` on a pre-PR-#4a checkout

- [ ] **Step 6: Verify default-path lazy-import discipline**

```bash
python -X importtime -c "
import os
os.environ['CASTLE_PALACE_PATH'] = '/tmp/castle-soar-smoke/palace'
from cognitive_castle import cli
" 2>&1 | grep soar_bridge
```

Expected: NO output. `soar_bridge` is NOT imported during default `castle` startup.

- [ ] **Step 7: Clean up**

```bash
rm -rf /tmp/castle-soar-smoke
```

No commit — these are verification steps. Capture results for the PR description.

---

## Task 11: Final acceptance + push + PR

**Files:** none (verification + git push only)

Walk through all 14 acceptance criteria from the spec.

- [ ] **Step 1: Acceptance #1 — Soar-gated tests pass**

```bash
pytest tests/test_soar_bridge.py -v -m soar
```
Expected: 8 passed.

- [ ] **Step 2: Acceptance #2 — without marker filter, 2 always-run pass + 8 skip on systems without SML**

```bash
pytest tests/test_soar_bridge.py -v
```

On the developer's hardware (SML available): all 10 pass. On systems without SML: 2 pass + 8 skip with `reason="Soar 9.6+ SML not installed"`. Note which scenario applies.

- [ ] **Step 3: Acceptance #3 — CLI tests pass**

```bash
pytest tests/test_cli.py -v -k soar_boost
```
Expected: 2 passed.

- [ ] **Step 4: Acceptance #4 — MCP test passes**

```bash
pytest tests/test_mcp_server.py -v -k soar_boost
```
Expected: 1 passed.

- [ ] **Step 5: Acceptance #5 — full suite no new regressions**

```bash
pytest tests/ -v --ignore=tests/benchmarks
```
Expected: previous-passing-count + ~17 new tests (4 config + 10 soar_bridge + 2 cli + 1 mcp). Pre-existing CI-UNSTABLE failures acceptable.

- [ ] **Step 6: Acceptance #6 — `castle search --help` shows `--soar-boost`**

```bash
castle search --help 2>&1 | grep -A3 "soar-boost"
```
Expected: flag shown with "experimental; requires Soar 9.6+" mention.

- [ ] **Step 7: Acceptance #7 — MCP schema includes soar_boost**

Run the schema check from Task 8 Step 6. Expected: `soar_boost: boolean (default false)` property present.

- [ ] **Step 8: Acceptance #8 — ruff clean on touched files**

```bash
ruff check cognitive_castle/soar_bridge.py cognitive_castle/config.py cognitive_castle/cli.py cognitive_castle/mcp_server.py cognitive_castle/searcher.py tests/test_soar_bridge.py tests/test_cli.py tests/test_config.py tests/test_mcp_server.py
ruff format --check cognitive_castle/soar_bridge.py cognitive_castle/config.py cognitive_castle/cli.py cognitive_castle/mcp_server.py cognitive_castle/searcher.py tests/test_soar_bridge.py tests/test_cli.py tests/test_config.py tests/test_mcp_server.py
```
Expected: no errors. (Repo-wide `ruff format --check .` will show pre-existing drift unrelated to this PR — documented CI-UNSTABLE.)

- [ ] **Step 9: Acceptance #9-#11 — live smokes** (already done in Task 10)

Confirm the Task 10 results: happy path produced `soar_boost` audit fields; kill switch exited 2; SML-disabled produced graceful warning; default unchanged.

- [ ] **Step 10: Acceptance #12-#13 — docs updated**

```bash
grep -E "Stage 5|--soar-boost" /home/lbihari/cognitive-castle/CLAUDE.md /home/lbihari/cognitive-castle/README.md | head -10
```
Expected: Stage 5 in CLAUDE.md diagram, "--soar-boost" in README "Going further" block.

- [ ] **Step 11: Acceptance #14 — default-path lazy-import**

Already verified in Task 10 Step 6. Re-run to confirm:

```bash
python -X importtime -c "from cognitive_castle import cli" 2>&1 | grep soar_bridge
```
Expected: NO output.

- [ ] **Step 12: Push branch**

```bash
git push -u origin feat/soar-bridge
```

- [ ] **Step 13: Open PR**

```bash
gh pr create --title "feat: SOAR bridge + post-pipeline boost-tags (PR #4a, experimental)" --body "$(cat <<'EOF'
## Summary

PR #4a of the SOTA-retrieval umbrella. Restores the SOAR integration deleted in PR #14 (commit `b49ebe83`) — but **working this time**. Soar 9.6.40 + SML Python bindings verified live at `/home/lbihari/soar-work/Soar/build/Core/ClientSMLSWIG/python/`.

- **Opt-in only:** `castle search --soar-boost` (CLI) + `soar_boost:true` (MCP `castle_search`). Requires `CASTLE_SOAR_ENABLED=1` kill-switch ack.
- **2 initial production rules:** `recency-boost` (×1.25 if drawer accessed in last 7d), `same-project` (×1.15 if wing matches CASTLE_PROJECT). Compound multiplicatively, clamp `[0.1, 10.0]`.
- **Audit trail:** every boosted hit gains `soar_boost` (compound multiplier), `soar_tags` (which rules fired), `score_pre_soar` (original score). Every score change has a name — the differentiating value over neural rerankers.
- **EpMem + SMem subsystems** enabled at agent creation (preparation for #4c chunking, unused in #4a).
- **Graceful fallback:** any Soar failure (SML missing, kernel/agent/rules error, decision-cycle hang, unknown tag) prints one-time-per-process stderr + returns hits unchanged. Search ALWAYS returns results.
- **Lazy import discipline:** `soar_bridge` module is NOT loaded for default-path users (verified via `python -X importtime`).

This is PR #4a of a 3-sub-PR umbrella:
- #4a (this PR): bridge + post-pipeline boost-tags
- #4b (future): composable order with LLM-judge from PR #3
- #4c (future): chunking + persistent learning — the SOTA-research contribution

Spec: `docs/superpowers/specs/2026-05-13-soar-fusion-design.md` (commit `db831e63`).
Plan: `docs/superpowers/plans/2026-05-13-soar-fusion.md`.

## Test plan

- [x] `pytest tests/test_soar_bridge.py -v -m soar` — 8 passed (developer's hardware with Soar 9.6.40)
- [x] `pytest tests/test_soar_bridge.py -v` — 10 passed (all on developer; would be 2 passed + 8 skipped on systems without SML)
- [x] `pytest tests/test_cli.py -v -k soar_boost` — 2 passed (flag propagation + kill-switch exit)
- [x] `pytest tests/test_mcp_server.py -v -k soar_boost` — 1 passed
- [x] `pytest tests/test_config.py -v -k soar` — 4 passed (2 properties × default + env)
- [x] `pytest tests/ -v --ignore=tests/benchmarks` — no new regressions
- [x] `ruff check` + `ruff format --check` clean on all touched files
- [x] `castle search --help` shows `--soar-boost`
- [x] MCP `castle_search` tool schema includes `soar_boost: boolean (default false)`
- [x] **Live smoke (happy path):** `CASTLE_SOAR_ENABLED=1 castle search "auth" --soar-boost` produced hits with `soar_boost` field populated, no stderr warnings
- [x] **Live smoke (kill switch):** `CASTLE_SOAR_ENABLED=0 castle search "auth" --soar-boost` exited 2 with clear stderr
- [x] **Live smoke (SML disabled):** `CASTLE_SML_DISABLED=1 ... --soar-boost` completed with stderr warning, hits unchanged
- [x] **Live smoke (default unchanged):** no-flag `castle search` identical to pre-PR-#4a behavior
- [x] **Lazy-import verified:** `python -X importtime -c "from cognitive_castle import cli"` produces no `soar_bridge` output

## Known caveats

- The 2 initial rules have a small per-query effect (limited by the data fields current pipeline exposes). 3 more rules (`entity-match`, `correction-priority`, `stale-penalty`) queued for follow-up PRs once supporting data lands (hit-provenance from fusion.py, drawer-type metadata, EpMem access-counts).
- EpMem/SMem subsystems are configured at agent creation but **unused** in #4a — preparation for #4c. Chunks won't accumulate.
- Boost multiplier values (1.25, 1.15) are initial guesses, not calibrated. #4c's chunking work will produce empirically grounded values.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opens at `https://github.com/Testimonial/cognitive-castle/pull/<N>`. Report the URL.

---

## Self-Review

**Spec coverage check:** all 14 acceptance criteria from `2026-05-13-soar-fusion-design.md` (commit `db831e63`) map to at least one task:

| Spec acceptance | Implemented in |
|---|---|
| #1 8 Soar tests | Task 4 |
| #2 always-run + skip pattern | Task 4 |
| #3 CLI tests | Task 7 |
| #4 MCP test | Task 8 |
| #5 default suite | Task 11 Step 5 |
| #6 `--help` shows flag | Task 7 Step 6 + Task 11 Step 6 |
| #7 MCP schema | Task 8 Step 6 + Task 11 Step 7 |
| #8 ruff clean | Tasks 2/4/7/8 + Task 11 Step 8 |
| #9 happy-path smoke | Task 10 Step 2 |
| #10 kill-switch smoke | Task 10 Step 3 |
| #11 SML-disabled smoke | Task 10 Step 4 |
| #12 README updated | Task 9 |
| #13 CLAUDE.md updated | Task 9 |
| #14 default-path lazy-import | Task 7 Step 9 + Task 10 Step 6 + Task 11 Step 11 |

**Placeholder scan:**
- No "TBD", "TODO", "implement later".
- Two intentional non-placeholders worth flagging:
  - Task 6 Step 3 doesn't show the FULL extracted `_print_search_results` body — the body depends on what `search()` currently prints in this repo. The plan says "Inspect first, then extract." This is a "follow established patterns" pointer that requires local file inspection. Acceptable per writing-plans skill guidance.
  - Task 8 Step 3 placement of the SOAR-boost block in the MCP handler depends on "the existing handler's flow." Again — a follow-existing-patterns pointer.

**Type consistency:**
- `apply_soar_boosts(hits: list[dict], cfg) -> list[dict]` — same signature in Tasks 4 (impl), 7 (CLI test mock), 8 (MCP test mock).
- `_reset_for_test()` — same name in Tasks 4 (impl + test fixture).
- `BOOST_MULTIPLIERS` — same dict name + 2 keys across Tasks 4, 5, 9.
- Audit fields `soar_boost`, `soar_tags`, `score_pre_soar` — consistent in Tasks 4, 7, 8, 9.
- `_print_search_results(result, query)` — same signature in Tasks 6 (impl), 7 (cmd_search call).
- `--soar-boost` flag + `soar_boost` Namespace attr — consistent across Tasks 7, 8.
- `CASTLE_SOAR_ENABLED` env var — consistent across Tasks 2, 7, 8, 10.

**Inconsistencies fixed inline:** none surfaced.
