# Stage 6 — Deterministic Quality Rerank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional Stage 6 to Castle's retrieval pipeline that re-ranks candidates using 31 deterministic text-quality metrics from the vendored `understanding` package, with a two-tier (high / medium / no-boost) threshold rule calibrated to the user's palace.

**Architecture:** Vendor `~/echelon/src/understanding/` into `cognitive_castle/understanding/` (MIT, same author — no dep chain to mempalace). Add `cognitive_castle/quality_rerank.py` with `apply_quality_rerank(reranked, cfg)` implementing two-tier classification. Rename `searcher._apply_stages_4_and_5` → `_apply_optional_stages` and thread a third optional Stage 6 through. Opt-in via `--quality-rerank` + `CASTLE_QUALITY_ENABLED=1` (mirrors SOAR pattern). Audit-trail fields (`quality_score`, `quality_tier`, `quality_boost`, `score_pre_quality`) on every hit.

**Tech Stack:** Python 3.12, pytest, ruff, **NEW deps: spaCy + `en_core_web_sm` model wheel** (added to pyproject.toml). No new LLM calls; deterministic regex + signal counting.

**Spec reference:** `docs/superpowers/specs/2026-05-14-quality-rerank-design.md` (v4 — five review passes).

**Pre-plan verifications already done:**
- `~/echelon/src/understanding/` contains 12 .py files (verified by `ls`)
- `understanding/` does NOT import `transformers` anywhere; only lazy-imports `spacy` in 3 files (entity_metrics, markdown_parser, semantic_metrics)
- `_apply_stages_4_and_5` is referenced 14 times: 2 in `cognitive_castle/searcher.py`, 12 in `tests/test_pipeline_order.py`. The rename must be atomic — all 14 callsites updated in one commit
- Castle's pyproject already has `sentence-transformers>=3.0`, NOT `spacy` (so spaCy is a new dep)
- Calibration ran on 2026-05-14: 100-drawer random sample, mean=0.469, p75=0.534, p90=0.597, stdev=0.113. Thresholds `0.53` / `0.60` reflect that measurement

## Branch

All tasks land on a single feature branch:

```bash
git checkout -b feat/quality-rerank-stage-6
```

Final PR merges to `develop`.

## File Structure

**NEW files:**
- `cognitive_castle/understanding/` — vendored copy (12 .py files, MIT, faithful mirror)
- `cognitive_castle/quality_rerank.py` — Stage 6 implementation (~120 LOC)
- `scripts/calibrate_quality_threshold.py` — one-shot calibration tool
- `tests/test_quality_rerank.py` — unit + integration tests

**MODIFIED files:**
- `pyproject.toml` — add `spacy>=3.0.0` + `en-core-web-sm` wheel URL
- `cognitive_castle/config.py` — 5 new properties
- `cognitive_castle/searcher.py` — rename + Stage 6 wiring + audit fields
- `cognitive_castle/cli.py` — `--quality-rerank` flag + kill-switch validation
- `cognitive_castle/mcp_server.py` — `quality_rerank` MCP param + kill-switch
- `cognitive_castle/__init__.py` — possibly nothing if quality_rerank doesn't need to be exported
- `tests/test_pipeline_order.py` — rename references + new Stage 6 ordering tests
- `tests/test_searcher.py` — quality_* return-dict assertions + audit-line tests
- `tests/test_cli.py` — kill-switch tests
- `tests/test_mcp_server.py` — kill-switch tests
- `tests/test_config.py` — 5 properties × 3 paths = 15 tests
- `CLAUDE.md` — pipeline diagram update

---

## Task 1: Verify spaCy + `en_core_web_sm` install + add deps

**Files:**
- Modify: `pyproject.toml`

**Agent model:** haiku (mechanical) but with pre-flight verification

**Notes:** This is Task 1 because without `spacy` + the model installed, no later task can be tested locally. Implementer MUST verify the install path actually works before committing the dep change. If the wheel URL fails to resolve, escalate immediately.

- [ ] **Step 1: Verify Castle's pyproject deps + Python environment**

```bash
grep -n "spacy\|sentence-transformers" pyproject.toml
```

Expected output: line showing `sentence-transformers>=3.0` exists; NO `spacy` line. If `spacy` is already in pyproject.toml, STOP and report — the spec assumes it's new.

- [ ] **Step 2: Test the spaCy install BEFORE modifying pyproject.toml**

```bash
pip install "spacy>=3.0.0" "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl" 2>&1 | tail -5
```

Expected: `Successfully installed spacy-X.Y.Z en-core-web-sm-3.8.0` or similar. If wheel URL fails (404 or connection error), STOP and report — this is a Risk #2 manifestation.

Verify spaCy imports + loads the model:

```bash
python -c "import spacy; nlp = spacy.load('en_core_web_sm'); print('ok')"
```

Expected: `ok`. If `spacy.load` fails with model-not-found, the wheel install didn't register the package correctly — escalate.

- [ ] **Step 3: Find the right section in `pyproject.toml` to add deps**

```bash
grep -n "^dependencies\|sentence-transformers" pyproject.toml
```

Identify the `dependencies = [...]` block and the line where `sentence-transformers` lives. The new deps go in the same block.

- [ ] **Step 4: Add the two new deps to `pyproject.toml`**

In the `dependencies = [...]` block, after the `sentence-transformers` line, add:

```toml
    "spacy>=3.0.0",
    "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
```

Preserve the trailing comma convention of the surrounding lines. NO `transformers` dep added (verified: `understanding/` doesn't import it).

- [ ] **Step 5: Verify the editable reinstall works**

```bash
pip install -e ".[dev]" 2>&1 | tail -10
```

Expected: re-resolves cleanly, finds both spaCy and the model wheel. If pip resolution fails, the new lines have a syntax error or conflict — fix before proceeding.

- [ ] **Step 6: Verify ruff still passes on pyproject.toml**

ruff doesn't lint TOML files, but check that nothing else broke:

```bash
ruff check . 2>&1 | tail -3
```

Expected: same baseline as before (no new errors introduced).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml
git commit -m "$(cat <<'EOF'
feat(deps): add spacy + en_core_web_sm for Stage 6 quality rerank

The understanding package (vendored in a follow-up commit) lazy-imports
spacy in entity_metrics.py, markdown_parser.py, and semantic_metrics.py.
No transformers dep added — verified understanding/ doesn't import
transformers anywhere; Castle's existing transitive transformers (via
sentence-transformers) is unrelated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Vendor the `understanding` package

**Files:**
- Create: `cognitive_castle/understanding/` directory (12 .py files + a provenance header)

**Agent model:** haiku (mechanical copy + docstring add)

**Notes:** Faithful drop-in copy from `~/echelon/src/understanding/`. NO modifications to the vendored code in this commit — only add a provenance docstring to `__init__.py`. Faithfulness matters: future syncs from echelon should be `rsync` or `cp -r` clean.

- [ ] **Step 1: Verify source exists + count files**

```bash
ls ~/echelon/src/understanding/*.py | wc -l
ls ~/echelon/src/understanding/
```

Expected: `12` and a listing including `__init__.py`, `cli.py`, `behavioral_metrics.py`, `constraint_metrics.py`, `depth_metrics.py`, `energy_metrics.py`, `enhanced_metrics.py`, `entity_metrics.py`, `markdown_parser.py`, `normalized_metrics.py`, `requirements_metrics.py`, `semantic_metrics.py`. If the count differs, the spec assumption is stale — escalate.

- [ ] **Step 2: Copy the package into Castle**

```bash
mkdir -p cognitive_castle/understanding
cp ~/echelon/src/understanding/*.py cognitive_castle/understanding/
ls cognitive_castle/understanding/
```

Expected: same 12 files now under `cognitive_castle/understanding/`.

- [ ] **Step 3: Read the vendored `__init__.py` to find the provenance-insertion point**

```bash
head -5 cognitive_castle/understanding/__init__.py
```

Expected: the existing module docstring opens with `"""Understanding - Requirements understanding...`. The provenance header goes ABOVE that docstring as a new top-level docstring section, OR appended to the existing docstring.

- [ ] **Step 4: Add the VENDORED docstring header to `__init__.py`**

Edit `cognitive_castle/understanding/__init__.py` — replace the FIRST line of the existing docstring (which currently reads `"""Understanding - Requirements understanding and cognitive load metrics.`) with the following prepended provenance + the original first line:

```python
"""VENDORED: source `~/echelon/src/understanding/` v3.7.0 on 2026-05-14.

This is a faithful drop-in copy from echelon — same author (Ladislav
Bihari), MIT license. Castle vendors this rather than depending on
echelon to avoid a Castle → echelon → mempalace dep chain (echelon
depends on mempalace, which Castle is a fork of).

To sync future upstream updates: `cp -r ~/echelon/src/understanding/*.py
cognitive_castle/understanding/` and verify tests still pass.

----

Understanding - Requirements understanding and cognitive load metrics.
```

The rest of the original docstring (and the rest of the file) stays unchanged.

- [ ] **Step 5: Verify the vendored package imports cleanly from Castle's namespace**

```bash
python -c "from cognitive_castle.understanding import analyze_with_enhanced_metrics; r = analyze_with_enhanced_metrics('Hello world test'); print('ok, keys:', list(r.keys())[:5])"
```

Expected: `ok, keys: [...]` (some subset of `base_metrics`, `enhanced_metrics`, `metric_count`, ...). If ImportError, the vendor copy is incomplete or a hidden dep is missing — investigate before proceeding.

- [ ] **Step 6: Run ruff format on the vendored directory**

```bash
ruff format cognitive_castle/understanding/
ruff check cognitive_castle/understanding/ 2>&1 | tail -5
```

Expected: ruff format may reformat per Castle's conventions. ruff check might surface lint errors from the upstream package. If errors appear:
- For RUF/E/W errors that are stylistic and harmless, add a `# noqa: <code>` comment OR (preferred) leave the code unchanged and add `cognitive_castle/understanding/` to ruff's `[tool.ruff.lint.per-file-ignores]` or `extend-exclude` in pyproject.toml. **The vendored code is not Castle code — preserve faithfulness over Castle's lint conventions.**

Recommended approach: add to pyproject.toml's ruff config:

```toml
[tool.ruff]
extend-exclude = ["cognitive_castle/understanding"]
```

(Check the existing `[tool.ruff]` section first; the exact key name may already exist with other excludes.)

- [ ] **Step 7: Verify Castle's existing tests still pass (no regression)**

```bash
python -m pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -3
```

Expected: same `0 failed` baseline from PR #43 (the zero-failures cleanup). If new failures appear, the vendored package is leaking imports or its module-level code has side effects that break something — investigate.

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/understanding/ pyproject.toml
git commit -m "$(cat <<'EOF'
feat(understanding): vendor the understanding package (v3.7.0)

Faithful drop-in copy from ~/echelon/src/understanding/. MIT, same
author. 12 .py files: __init__.py, cli.py, behavioral_metrics.py,
constraint_metrics.py, depth_metrics.py, energy_metrics.py,
enhanced_metrics.py, entity_metrics.py, markdown_parser.py,
normalized_metrics.py, requirements_metrics.py, semantic_metrics.py.

Vendored rather than added as a dep to avoid the echelon → mempalace
chain (echelon depends on mempalace; Castle is a fork of mempalace).

Provenance recorded in cognitive_castle/understanding/__init__.py.
Future upstream syncs: cp -r the .py files and verify tests pass.

Added cognitive_castle/understanding/ to ruff's extend-exclude so
the upstream code isn't reformatted to Castle conventions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Config — five new properties

**Files:**
- Modify: `cognitive_castle/config.py`
- Test: `tests/test_config.py` (append)

**Agent model:** haiku (mechanical, mirrors PR #38's pattern exactly)

**Notes:** Five properties × three test paths each = 15 new tests. Follow Castle's standard env→file→default pattern WITH try-except for invalid input (post-Task 1 of zero-failures cleanup — every numeric property wraps conversions in try-except).

- [ ] **Step 1: Read existing config patterns to mirror them**

```bash
grep -B1 -A15 "def entity_promote_threshold" cognitive_castle/config.py
```

Expected: shows the property with env-var read → try/except → file_config fallback → default. This is the EXACT pattern to mirror for the new numeric properties (`quality_threshold_*` and `quality_boost_*`).

For the boolean property (`quality_enabled`), look at the SOAR pattern:

```bash
grep -B1 -A15 "def soar_enabled" cognitive_castle/config.py
```

- [ ] **Step 2: Write the failing tests** — append to `tests/test_config.py`:

```python
# ── Quality rerank (Stage 6) config tests ─────────────────────────────


def test_quality_enabled_default():
    cfg = CognitiveCastleConfig()
    assert cfg.quality_enabled is False


def test_quality_enabled_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_QUALITY_ENABLED", "1")
    cfg = CognitiveCastleConfig()
    assert cfg.quality_enabled is True


def test_quality_enabled_file_config_override():
    cfg = _make_config_with_file_config({"quality_enabled": True})
    assert cfg.quality_enabled is True


def test_quality_threshold_medium_default():
    cfg = CognitiveCastleConfig()
    assert cfg.quality_threshold_medium == 0.53


def test_quality_threshold_medium_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_QUALITY_THRESHOLD_MEDIUM", "0.40")
    cfg = CognitiveCastleConfig()
    assert cfg.quality_threshold_medium == 0.40


def test_quality_threshold_medium_file_config_override():
    cfg = _make_config_with_file_config({"quality_threshold_medium": 0.45})
    assert cfg.quality_threshold_medium == 0.45


def test_quality_threshold_high_default():
    cfg = CognitiveCastleConfig()
    assert cfg.quality_threshold_high == 0.60


def test_quality_threshold_high_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_QUALITY_THRESHOLD_HIGH", "0.75")
    cfg = CognitiveCastleConfig()
    assert cfg.quality_threshold_high == 0.75


def test_quality_threshold_high_file_config_override():
    cfg = _make_config_with_file_config({"quality_threshold_high": 0.70})
    assert cfg.quality_threshold_high == 0.70


def test_quality_boost_medium_default():
    cfg = CognitiveCastleConfig()
    assert cfg.quality_boost_medium == 1.15


def test_quality_boost_medium_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_QUALITY_BOOST_MEDIUM", "1.10")
    cfg = CognitiveCastleConfig()
    assert cfg.quality_boost_medium == 1.10


def test_quality_boost_medium_file_config_override():
    cfg = _make_config_with_file_config({"quality_boost_medium": 1.20})
    assert cfg.quality_boost_medium == 1.20


def test_quality_boost_high_default():
    cfg = CognitiveCastleConfig()
    assert cfg.quality_boost_high == 1.25


def test_quality_boost_high_env_override(monkeypatch):
    monkeypatch.setenv("CASTLE_QUALITY_BOOST_HIGH", "1.30")
    cfg = CognitiveCastleConfig()
    assert cfg.quality_boost_high == 1.30


def test_quality_boost_high_file_config_override():
    cfg = _make_config_with_file_config({"quality_boost_high": 1.35})
    assert cfg.quality_boost_high == 1.35
```

Verify `_make_config_with_file_config` helper exists in the file (used by KG-enrichment tests). If not, grep for the pattern other file-config tests use and adapt.

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_config.py -k "quality_enabled or quality_threshold or quality_boost" -v 2>&1 | tail -10
```

Expected: 15 FAIL with `AttributeError: 'CognitiveCastleConfig' object has no attribute 'quality_enabled'` (etc.).

- [ ] **Step 4: Implement the five properties** — append to `cognitive_castle/config.py` near other Stage 4/5 properties:

```python
@property
def quality_enabled(self) -> bool:
    """Kill-switch for Stage 6 (deterministic quality rerank). Default False.

    Reads from ``CASTLE_QUALITY_ENABLED`` env var first, then config file,
    then default. Any truthy env value (``1``, ``true``, ``yes`` —
    case-insensitive) enables; anything else disables.
    """
    env_val = os.environ.get("CASTLE_QUALITY_ENABLED")
    if env_val is not None:
        return env_val.strip().lower() in ("1", "true", "yes")
    cfg_val = self._file_config.get("quality_enabled")
    if cfg_val is not None:
        return bool(cfg_val)
    return False


@property
def quality_threshold_medium(self) -> float:
    """Lower threshold for Stage 6's two-tier boost. Default 0.53 (palace
    p75 from 2026-05-14 calibration).

    Reads from ``CASTLE_QUALITY_THRESHOLD_MEDIUM`` env var first, then
    config file, then default.
    """
    env_val = os.environ.get("CASTLE_QUALITY_THRESHOLD_MEDIUM")
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    cfg_val = self._file_config.get("quality_threshold_medium")
    if cfg_val is not None:
        try:
            return float(cfg_val)
        except (ValueError, TypeError):
            pass
    return 0.53


@property
def quality_threshold_high(self) -> float:
    """Upper threshold for Stage 6's two-tier boost. Default 0.60 (palace
    p90 from 2026-05-14 calibration).

    Reads from ``CASTLE_QUALITY_THRESHOLD_HIGH`` env var first, then
    config file, then default.
    """
    env_val = os.environ.get("CASTLE_QUALITY_THRESHOLD_HIGH")
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    cfg_val = self._file_config.get("quality_threshold_high")
    if cfg_val is not None:
        try:
            return float(cfg_val)
        except (ValueError, TypeError):
            pass
    return 0.60


@property
def quality_boost_medium(self) -> float:
    """Score multiplier applied to medium-tier hits in Stage 6. Default 1.15.

    Reads from ``CASTLE_QUALITY_BOOST_MEDIUM`` env var first, then config
    file, then default.
    """
    env_val = os.environ.get("CASTLE_QUALITY_BOOST_MEDIUM")
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    cfg_val = self._file_config.get("quality_boost_medium")
    if cfg_val is not None:
        try:
            return float(cfg_val)
        except (ValueError, TypeError):
            pass
    return 1.15


@property
def quality_boost_high(self) -> float:
    """Score multiplier applied to high-tier hits in Stage 6. Default 1.25.

    Reads from ``CASTLE_QUALITY_BOOST_HIGH`` env var first, then config
    file, then default.
    """
    env_val = os.environ.get("CASTLE_QUALITY_BOOST_HIGH")
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    cfg_val = self._file_config.get("quality_boost_high")
    if cfg_val is not None:
        try:
            return float(cfg_val)
        except (ValueError, TypeError):
            pass
    return 1.25
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_config.py -k "quality_enabled or quality_threshold or quality_boost" -v 2>&1 | tail -10
```

Expected: 15 PASS.

- [ ] **Step 6: Run full config test suite to verify no regression**

```bash
python -m pytest tests/test_config.py -v 2>&1 | tail -5
```

- [ ] **Step 7: Format + lint**

```bash
ruff format cognitive_castle/config.py tests/test_config.py
ruff check cognitive_castle/config.py tests/test_config.py
```

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): add five Stage 6 (quality rerank) properties

Properties (each with env → file_config → default + try-except):
  - quality_enabled (bool, default False)
  - quality_threshold_medium (float, default 0.53 — palace p75 on
    2026-05-14)
  - quality_threshold_high (float, default 0.60 — palace p90 on
    2026-05-14)
  - quality_boost_medium (float, default 1.15)
  - quality_boost_high (float, default 1.25)

Threshold defaults calibrated from a 100-drawer random sample on the
user's 55,710-drawer palace at ~/.castle/palace; see spec for the
distribution. All five follow Castle's standard env-var pattern with
try-except so invalid env values fall through gracefully.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Rename `_apply_stages_4_and_5` → `_apply_optional_stages`

**Files:**
- Modify: `cognitive_castle/searcher.py`
- Modify: `tests/test_pipeline_order.py`

**Agent model:** haiku (mechanical rename, 14 callsites)

**Notes:** This task is atomic — it renames `_apply_stages_4_and_5` to `_apply_optional_stages` in both searcher.py (2 callsites: 1 def + 1 caller) and test_pipeline_order.py (12 references). MUST be one commit; splitting the rename across commits breaks the test suite.

The signature also gains a `quality_rerank: bool = False` parameter in this task — but it's NOT YET USED. The threading of the new param happens here so subsequent tasks can wire it up without breaking the call site.

- [ ] **Step 1: Confirm exact callsite count before rename**

```bash
grep -c "_apply_stages_4_and_5" cognitive_castle/searcher.py
grep -c "_apply_stages_4_and_5" tests/test_pipeline_order.py
```

Expected: `2` and `12`. If different, the codebase has drifted since the spec — investigate before mechanical rename.

- [ ] **Step 2: Read the existing function signature + body for context**

```bash
sed -n '420,475p' cognitive_castle/searcher.py
```

Expected: shows `_apply_stages_4_and_5(query, reranked, cfg, llm_rerank, soar_boost, soar_first)`. The body delegates to `_stage_4_judge` and `_stage_5_soar` per the configured ordering. We're going to:
- Rename the function
- Add `quality_rerank: bool = False` param (last position to preserve back-compat for any callers we missed)
- NOT yet add Stage 6 routing — that's a later task

- [ ] **Step 3: Apply the rename in `searcher.py` — definition + 1 caller**

Edit `cognitive_castle/searcher.py:423`:

```python
def _apply_optional_stages(
    query: str,
    reranked: list[tuple[float, dict]],
    cfg,
    llm_rerank: bool,
    soar_boost: bool,
    soar_first: bool,
    quality_rerank: bool = False,
) -> list[tuple[float, dict]]:
```

Update the existing docstring's first sentence from "Run optional Stage 4 (judge) and Stage 5 (SOAR) in the requested order." to:

```python
"""Run optional Stages 4 (judge), 5 (SOAR), and 6 (quality rerank) in the
requested order.

Default order (soar_first=False): Stage 4 → Stage 5 → Stage 6.

soar_first=True: Stage 5 → Stage 4 → Stage 6 (SOAR re-ranks the full
reranked list, then judge truncates to top-N, then quality reranks).
Stage 6 always runs last.

quality_rerank must be False for now — Stage 6 wiring lands in a
subsequent commit. This param is added here so the call-site signature
is stable while Stage 6 implementation arrives.
"""
```

Update the existing caller at searcher.py:594:

```python
    reranked = _apply_optional_stages(
        query=query,
        reranked=reranked,
        cfg=cfg,
        llm_rerank=llm_rerank,
        soar_boost=soar_boost,
        soar_first=soar_first,
        quality_rerank=False,  # Stage 6 wiring lands in a later commit
    )
```

(The caller may need the `quality_rerank=False` line added; if the existing caller doesn't pass that argument it'll still work due to the default — but explicit is better. Look at the actual call site to decide.)

- [ ] **Step 4: Apply the rename in `tests/test_pipeline_order.py` — 12 references**

```bash
sed -i 's/_apply_stages_4_and_5/_apply_optional_stages/g' tests/test_pipeline_order.py
```

Then verify:

```bash
grep -c "_apply_stages_4_and_5" tests/test_pipeline_order.py
grep -c "_apply_optional_stages" tests/test_pipeline_order.py
```

Expected: `0` and `12`.

- [ ] **Step 5: Run the renamed tests to verify they pass**

```bash
python -m pytest tests/test_pipeline_order.py -v 2>&1 | tail -10
```

Expected: all tests pass with the renamed function. If ImportError or AttributeError, the rename missed a callsite.

- [ ] **Step 6: Run full test suite to verify zero new failures**

```bash
python -m pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -3
```

Expected: `0 failed`. If anything else fails, it's a regression introduced by the rename.

- [ ] **Step 7: Format + lint**

```bash
ruff format cognitive_castle/searcher.py tests/test_pipeline_order.py
ruff check cognitive_castle/searcher.py tests/test_pipeline_order.py
```

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/searcher.py tests/test_pipeline_order.py
git commit -m "$(cat <<'EOF'
refactor(searcher): rename _apply_stages_4_and_5 → _apply_optional_stages

Forward-compatible rename to accommodate Stage 6 (quality rerank)
landing in a follow-up commit. Updates 14 callsites:
  - 1 def + 1 caller in cognitive_castle/searcher.py
  - 12 references in tests/test_pipeline_order.py

Adds quality_rerank: bool = False param to the function signature
(unused for now — Stage 6 wiring arrives in a later commit). This
keeps the call-site signature stable across the Stage 6 implementation.

No semantic change to existing pipeline behavior.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `quality_rerank.py` — Stage 6 core implementation

**Files:**
- Create: `cognitive_castle/quality_rerank.py`
- Create: `tests/test_quality_rerank.py`

**Agent model:** sonnet (judgment — the core algorithm + tier classification + audit fields + failure modes)

**Notes:** This is the heaviest task. Implements `apply_quality_rerank(reranked, cfg) -> list[tuple[float, dict]]` plus the internal `_classify_tier(score, cfg)` helper. Mocks `understanding.analyze_with_enhanced_metrics` in tests so the unit tests don't need spaCy loaded.

- [ ] **Step 1: Write failing tests for tier classification (pure function)**

Create `tests/test_quality_rerank.py`:

```python
"""Tests for cognitive_castle.quality_rerank (Stage 6 of mine())."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────


def _mock_cfg(
    *,
    threshold_medium=0.53,
    threshold_high=0.60,
    boost_medium=1.15,
    boost_high=1.25,
    quality_enabled=True,
):
    """Minimal cfg exposing only the fields quality_rerank reads."""
    cfg = MagicMock()
    cfg.quality_threshold_medium = threshold_medium
    cfg.quality_threshold_high = threshold_high
    cfg.quality_boost_medium = boost_medium
    cfg.quality_boost_high = boost_high
    cfg.quality_enabled = quality_enabled
    return cfg


# ── Tier classification (pure function, no external deps) ───────────


def test_classify_tier_score_above_high_threshold():
    from cognitive_castle.quality_rerank import _classify_tier

    tier, multiplier = _classify_tier(0.75, _mock_cfg())
    assert tier == "high"
    assert multiplier == 1.25


def test_classify_tier_score_at_high_threshold_boundary_inclusive():
    from cognitive_castle.quality_rerank import _classify_tier

    tier, multiplier = _classify_tier(0.60, _mock_cfg())
    assert tier == "high"
    assert multiplier == 1.25


def test_classify_tier_score_in_medium_range():
    from cognitive_castle.quality_rerank import _classify_tier

    tier, multiplier = _classify_tier(0.55, _mock_cfg())
    assert tier == "medium"
    assert multiplier == 1.15


def test_classify_tier_score_at_medium_threshold_boundary_inclusive():
    from cognitive_castle.quality_rerank import _classify_tier

    tier, multiplier = _classify_tier(0.53, _mock_cfg())
    assert tier == "medium"
    assert multiplier == 1.15


def test_classify_tier_score_below_medium_threshold():
    from cognitive_castle.quality_rerank import _classify_tier

    tier, multiplier = _classify_tier(0.40, _mock_cfg())
    assert tier is None
    assert multiplier == 1.0


def test_classify_tier_non_default_thresholds():
    from cognitive_castle.quality_rerank import _classify_tier

    cfg = _mock_cfg(threshold_medium=0.30, threshold_high=0.70)
    assert _classify_tier(0.75, cfg) == ("high", 1.25)
    assert _classify_tier(0.50, cfg) == ("medium", 1.15)
    assert _classify_tier(0.20, cfg) == (None, 1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_quality_rerank.py -v 2>&1 | tail -10
```

Expected: 6 FAIL with `ModuleNotFoundError: No module named 'cognitive_castle.quality_rerank'`.

- [ ] **Step 3: Create the module with `_classify_tier`**

Create `cognitive_castle/quality_rerank.py`:

```python
"""quality_rerank.py — Stage 6 of Castle's retrieval pipeline.

Optional, opt-in via cfg.quality_enabled + --quality-rerank CLI flag.
Re-ranks Stage 3+ candidates using the 31 deterministic text-quality
metrics from the vendored `understanding` package.

Two-tier threshold-and-boost rule with defaults calibrated to the user's
palace on 2026-05-14:
  - score >= cfg.quality_threshold_high (0.60)   → tier="high",   ×1.25
  - score >= cfg.quality_threshold_medium (0.53) → tier="medium", ×1.15
  - otherwise                                    → tier=None,     ×1.0

Per-hit audit-trail fields added to each row:
  - quality_score: float | None       (None when Stage 6 didn't run or
                                       per-hit failure occurred)
  - quality_tier:  "high" | "medium" | None
  - quality_boost: float (default 1.0)
  - score_pre_quality: float (hit's score before Stage 6 ran)

The audit-line printer in searcher._print_search_results only emits a
QUALITY line when quality_tier is not None.

Graceful degradation: if the vendored package fails to import or a
per-hit call raises, the affected hit(s) get default fields and a
warning is logged once per failure class.

See spec: docs/superpowers/specs/2026-05-14-quality-rerank-design.md
"""

from __future__ import annotations

import sys
from typing import Optional


ADAPTER_NAME = "quality-rerank"

# Module-level state. Cleared by _reset_for_test() in test runs.
_WARNED: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    """Print a stderr warning ONCE per process for the given key."""
    if key in _WARNED:
        return
    _WARNED.add(key)
    print(f"[quality_rerank] {message}", file=sys.stderr)


def _reset_for_test() -> None:
    """Test-only: clear module-level state to enable test isolation."""
    _WARNED.clear()


def _classify_tier(score: float, cfg) -> tuple[Optional[str], float]:
    """Apply the two-tier threshold rule. Returns (tier, multiplier).

    >= cfg.quality_threshold_high → ("high",   cfg.quality_boost_high)
    >= cfg.quality_threshold_medium → ("medium", cfg.quality_boost_medium)
    otherwise                       → (None,     1.0)
    """
    if score >= cfg.quality_threshold_high:
        return "high", cfg.quality_boost_high
    if score >= cfg.quality_threshold_medium:
        return "medium", cfg.quality_boost_medium
    return None, 1.0
```

- [ ] **Step 4: Run tier-classification tests to verify they pass**

```bash
python -m pytest tests/test_quality_rerank.py -k "classify_tier" -v 2>&1 | tail -10
```

Expected: 6 PASS.

- [ ] **Step 5: Write failing tests for `apply_quality_rerank` (mocked metrics)**

Append to `tests/test_quality_rerank.py`:

```python
# ── apply_quality_rerank (mocked analyze_with_enhanced_metrics) ────


def test_apply_quality_rerank_empty_input(monkeypatch):
    """Empty input → empty output, no crash."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    result = qr.apply_quality_rerank([], _mock_cfg())
    assert result == []


def test_apply_quality_rerank_all_high_tier(monkeypatch):
    """All hits above high threshold → all ×1.25, all "high"."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    # Stub the metric function to always return high score
    monkeypatch.setattr(
        "cognitive_castle.understanding.analyze_with_enhanced_metrics",
        lambda text: {"enhanced_metrics": {"overall_weighted_average": 0.75}},
    )

    hits = [
        (1.0, {"id": "a", "text": "text a", "wing": "w", "room": "r"}),
        (0.8, {"id": "b", "text": "text b", "wing": "w", "room": "r"}),
    ]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    assert len(result) == 2
    for new_score, row in result:
        assert row["quality_score"] == 0.75
        assert row["quality_tier"] == "high"
        assert row["quality_boost"] == 1.25
    # Top hit (originally 1.0) is now 1.25; second hit (0.8) is now 1.0
    assert result[0][0] == 1.25
    assert result[1][0] == 1.0


def test_apply_quality_rerank_all_below_medium(monkeypatch):
    """All hits below medium → all tier=None, quality_score set, boost=1.0,
    score_pre_quality == original score."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    monkeypatch.setattr(
        "cognitive_castle.understanding.analyze_with_enhanced_metrics",
        lambda text: {"enhanced_metrics": {"overall_weighted_average": 0.40}},
    )

    hits = [
        (0.5, {"id": "a", "text": "text a", "wing": "w", "room": "r"}),
        (0.4, {"id": "b", "text": "text b", "wing": "w", "room": "r"}),
    ]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    for new_score, row in result:
        assert row["quality_score"] == 0.40
        assert row["quality_tier"] is None
        assert row["quality_boost"] == 1.0
        assert row["score_pre_quality"] == new_score


def test_apply_quality_rerank_mixed_tiers(monkeypatch):
    """Mixed input → correct tier per hit."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    # Different scores per hit-id
    score_map = {"a": 0.75, "b": 0.55, "c": 0.40}

    def fake_analyze(text):
        # text is hit's text field; we map by what's in the text
        for hid, score in score_map.items():
            if hid in text:
                return {"enhanced_metrics": {"overall_weighted_average": score}}
        return {"enhanced_metrics": {"overall_weighted_average": 0.5}}

    monkeypatch.setattr(
        "cognitive_castle.understanding.analyze_with_enhanced_metrics",
        fake_analyze,
    )

    hits = [
        (1.0, {"id": "a", "text": "drawer a content", "wing": "w", "room": "r"}),
        (1.0, {"id": "b", "text": "drawer b content", "wing": "w", "room": "r"}),
        (1.0, {"id": "c", "text": "drawer c content", "wing": "w", "room": "r"}),
    ]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    by_id = {row["id"]: row for _, row in result}
    assert by_id["a"]["quality_tier"] == "high"
    assert by_id["b"]["quality_tier"] == "medium"
    assert by_id["c"]["quality_tier"] is None


def test_apply_quality_rerank_all_fields_always_present(monkeypatch):
    """Every hit dict has all 4 quality_* fields regardless of tier."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    monkeypatch.setattr(
        "cognitive_castle.understanding.analyze_with_enhanced_metrics",
        lambda text: {"enhanced_metrics": {"overall_weighted_average": 0.30}},
    )

    hits = [(1.0, {"id": "a", "text": "test", "wing": "w", "room": "r"})]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    _, row = result[0]
    assert "quality_score" in row
    assert "quality_tier" in row
    assert "quality_boost" in row
    assert "score_pre_quality" in row


def test_apply_quality_rerank_score_equals_pre_times_boost(monkeypatch):
    """hit["score"] (in output tuple) == score_pre_quality × quality_boost."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    monkeypatch.setattr(
        "cognitive_castle.understanding.analyze_with_enhanced_metrics",
        lambda text: {"enhanced_metrics": {"overall_weighted_average": 0.75}},
    )

    hits = [(0.8, {"id": "a", "text": "test", "wing": "w", "room": "r"})]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    new_score, row = result[0]
    assert row["score_pre_quality"] == 0.8
    assert row["quality_boost"] == 1.25
    assert new_score == 0.8 * 1.25  # 1.0


def test_apply_quality_rerank_sorted_descending(monkeypatch):
    """Output sorted by boosted score descending — re-rank may reorder."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    # Lower-scored hit gets a bigger boost; should jump to top after rerank
    score_map = {"low_quality_high_relevance": 0.30, "high_quality_low_relevance": 0.75}

    def fake_analyze(text):
        for k, score in score_map.items():
            if k in text:
                return {"enhanced_metrics": {"overall_weighted_average": score}}
        return {"enhanced_metrics": {"overall_weighted_average": 0.5}}

    monkeypatch.setattr(
        "cognitive_castle.understanding.analyze_with_enhanced_metrics",
        fake_analyze,
    )

    hits = [
        (0.9, {"id": "a", "text": "low_quality_high_relevance text", "wing": "w", "room": "r"}),
        (0.8, {"id": "b", "text": "high_quality_low_relevance text", "wing": "w", "room": "r"}),
    ]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    # Hit b: 0.8 × 1.25 = 1.0 — should be top
    # Hit a: 0.9 × 1.0  = 0.9
    assert result[0][1]["id"] == "b"
    assert result[1][1]["id"] == "a"
    # Sorted descending:
    assert result[0][0] >= result[1][0]
```

- [ ] **Step 6: Run new tests to verify they fail**

```bash
python -m pytest tests/test_quality_rerank.py -k "apply_quality_rerank" -v 2>&1 | tail -10
```

Expected: 7 FAIL with `AttributeError: module 'cognitive_castle.quality_rerank' has no attribute 'apply_quality_rerank'`.

- [ ] **Step 7: Implement `apply_quality_rerank`** — append to `cognitive_castle/quality_rerank.py`:

```python
def apply_quality_rerank(
    reranked: list[tuple[float, dict]],
    cfg,
) -> list[tuple[float, dict]]:
    """Stage 6: deterministic text-quality rerank.

    For each candidate, score the drawer text via
    `understanding.analyze_with_enhanced_metrics`, apply two-tier
    threshold-and-boost. Mutate hit dicts with audit-trail fields.

    Returns a NEW list of (score, row) tuples sorted by boosted score
    descending. Each row dict is mutated in place with:
      - quality_score (float, or None on per-hit failure)
      - quality_tier ("high" | "medium" | None)
      - quality_boost (float, 1.0 if no boost)
      - score_pre_quality (float, hit's score going into Stage 6)

    Graceful degradation:
      - If `cognitive_castle.understanding` import fails, all hits get
        default fields (None, None, 1.0, original score). Warns once.
      - If per-hit metric call raises, that hit gets default fields.
        Warns once per exception class.

    Never raises. Same fault-tolerance pattern as soar_bridge.
    """
    if not reranked:
        return reranked

    # Lazy import — only pays the spaCy load cost when Stage 6 actually
    # runs. Failure here means we can't run Stage 6 at all; all hits
    # get default fields.
    try:
        from cognitive_castle.understanding import analyze_with_enhanced_metrics
    except ImportError as e:
        _warn_once(
            "import-failed",
            f"understanding import failed ({type(e).__name__}: {e}); "
            f"Stage 6 skipped for all hits",
        )
        return [
            (
                score,
                _set_defaults(row, original_score=score),
            )
            for score, row in reranked
        ]

    out: list[tuple[float, dict]] = []
    for original_score, row in reranked:
        text = row.get("text") or row.get("document") or ""
        try:
            result = analyze_with_enhanced_metrics(text)
            score = result["enhanced_metrics"]["overall_weighted_average"]
            if not isinstance(score, (int, float)) or score != score:  # NaN check
                raise ValueError(f"non-numeric overall_weighted_average: {score!r}")
        except KeyError as e:
            _warn_once(
                "missing-key",
                f"analyze result missing expected key ({e}); per-hit default",
            )
            out.append((original_score, _set_defaults(row, original_score=original_score)))
            continue
        except Exception as e:
            _warn_once(
                f"analyze-failed-{type(e).__name__}",
                f"analyze_with_enhanced_metrics raised "
                f"({type(e).__name__}: {e}); per-hit default",
            )
            out.append((original_score, _set_defaults(row, original_score=original_score)))
            continue

        tier, multiplier = _classify_tier(float(score), cfg)
        new_score = original_score * multiplier

        row["quality_score"] = float(score)
        row["quality_tier"] = tier
        row["quality_boost"] = multiplier
        row["score_pre_quality"] = original_score
        out.append((new_score, row))

    # Sort by boosted score descending
    out.sort(key=lambda t: -t[0])
    return out


def _set_defaults(row: dict, *, original_score: float) -> dict:
    """Mutate the row dict with default quality_* fields (used on failure
    paths). Returns the same dict for fluent chaining."""
    row["quality_score"] = None
    row["quality_tier"] = None
    row["quality_boost"] = 1.0
    row["score_pre_quality"] = original_score
    return row
```

- [ ] **Step 8: Run apply_quality_rerank tests to verify they pass**

```bash
python -m pytest tests/test_quality_rerank.py -v 2>&1 | tail -15
```

Expected: all 13 tests PASS (6 tier + 7 apply).

- [ ] **Step 9: Write failing tests for failure modes**

Append to `tests/test_quality_rerank.py`:

```python
# ── Failure modes (mocked) ───────────────────────────────────────────


def test_apply_quality_rerank_import_fails(monkeypatch, capsys):
    """understanding import fails → all hits get default fields, warn once."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    # Stub the import to raise
    import sys
    monkeypatch.setitem(sys.modules, "cognitive_castle.understanding", None)

    hits = [
        (1.0, {"id": "a", "text": "test", "wing": "w", "room": "r"}),
        (0.5, {"id": "b", "text": "test", "wing": "w", "room": "r"}),
    ]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    assert len(result) == 2
    for _, row in result:
        assert row["quality_score"] is None
        assert row["quality_tier"] is None
        assert row["quality_boost"] == 1.0
        assert "score_pre_quality" in row

    captured = capsys.readouterr()
    assert "understanding import failed" in captured.err


def test_apply_quality_rerank_per_hit_failure(monkeypatch, capsys):
    """analyze_with_enhanced_metrics raises on a hit → that hit defaults,
    others continue. Warning printed once per exception class."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    def fake_analyze(text):
        if "bad" in text:
            raise RuntimeError("simulated metric failure")
        return {"enhanced_metrics": {"overall_weighted_average": 0.75}}

    monkeypatch.setattr(
        "cognitive_castle.understanding.analyze_with_enhanced_metrics",
        fake_analyze,
    )

    hits = [
        (1.0, {"id": "a", "text": "good text", "wing": "w", "room": "r"}),
        (1.0, {"id": "b", "text": "bad text", "wing": "w", "room": "r"}),
        (1.0, {"id": "c", "text": "good text", "wing": "w", "room": "r"}),
    ]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    by_id = {row["id"]: row for _, row in result}
    assert by_id["a"]["quality_tier"] == "high"
    assert by_id["b"]["quality_tier"] is None  # defaulted
    assert by_id["b"]["quality_score"] is None
    assert by_id["c"]["quality_tier"] == "high"


def test_apply_quality_rerank_missing_enhanced_metrics_key(monkeypatch):
    """Result missing 'enhanced_metrics' key → per-hit skip with defaults."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    monkeypatch.setattr(
        "cognitive_castle.understanding.analyze_with_enhanced_metrics",
        lambda text: {"some_other_key": "value"},
    )

    hits = [(1.0, {"id": "a", "text": "test", "wing": "w", "room": "r"})]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    _, row = result[0]
    assert row["quality_score"] is None
    assert row["quality_tier"] is None
    assert row["quality_boost"] == 1.0


def test_apply_quality_rerank_missing_overall_weighted_average_key(monkeypatch):
    """Result missing 'overall_weighted_average' key → per-hit skip."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    monkeypatch.setattr(
        "cognitive_castle.understanding.analyze_with_enhanced_metrics",
        lambda text: {"enhanced_metrics": {"some_other": 0.5}},
    )

    hits = [(1.0, {"id": "a", "text": "test", "wing": "w", "room": "r"})]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    _, row = result[0]
    assert row["quality_score"] is None


def test_apply_quality_rerank_nan_overall_weighted_average(monkeypatch):
    """overall_weighted_average is NaN → per-hit skip."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    monkeypatch.setattr(
        "cognitive_castle.understanding.analyze_with_enhanced_metrics",
        lambda text: {"enhanced_metrics": {"overall_weighted_average": float("nan")}},
    )

    hits = [(1.0, {"id": "a", "text": "test", "wing": "w", "room": "r"})]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    _, row = result[0]
    assert row["quality_score"] is None
    assert row["quality_tier"] is None


def test_apply_quality_rerank_keyboard_interrupt_propagates(monkeypatch):
    """KeyboardInterrupt must propagate, NOT be swallowed."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    def raising_analyze(text):
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        "cognitive_castle.understanding.analyze_with_enhanced_metrics",
        raising_analyze,
    )

    hits = [(1.0, {"id": "a", "text": "test", "wing": "w", "room": "r"})]
    with pytest.raises(KeyboardInterrupt):
        qr.apply_quality_rerank(hits, _mock_cfg())
```

- [ ] **Step 10: Adjust the implementation to propagate KeyboardInterrupt**

The current `except Exception as e:` block catches RuntimeError but also catches KeyboardInterrupt-subclasses if they aren't BaseException. Actually `KeyboardInterrupt` extends `BaseException`, not `Exception`, so `except Exception` already excludes it. **Verify** by running:

```bash
python -m pytest tests/test_quality_rerank.py -k "keyboard_interrupt" -v 2>&1 | tail -5
```

Expected: PASS (KeyboardInterrupt naturally propagates through `except Exception`). If FAIL, adjust the except clause.

- [ ] **Step 11: Run all quality_rerank tests to verify they pass**

```bash
python -m pytest tests/test_quality_rerank.py -v 2>&1 | tail -15
```

Expected: all tests PASS (6 tier + 7 apply + 6 failure-mode = 19).

- [ ] **Step 12: Write the slow smoke test (real package)**

Append to `tests/test_quality_rerank.py`:

```python
# ── Smoke (real package, slow marker) ────────────────────────────────


@pytest.mark.slow
def test_apply_quality_rerank_smoke():
    """Real understanding package + real apply_quality_rerank on fixture
    prose. Catches vendored import-graph + wiring regressions."""
    from cognitive_castle import quality_rerank as qr
    qr._reset_for_test()

    fixture_text = (
        "The verbatim memory palace stores user data exactly as written. "
        "The retrieval pipeline combines dense vectors, full-text search, "
        "and knowledge-graph traversal, fused via Reciprocal Rank Fusion "
        "weighted by configurable signals. The cross-encoder reranker "
        "produces relevance scores; optional stages 4 and 5 compose "
        "deterministically."
    )  # ~370 chars of well-formed prose

    hits = [
        (0.5, {"id": "h1", "text": fixture_text, "wing": "w", "room": "r"}),
    ]
    result = qr.apply_quality_rerank(hits, _mock_cfg())

    assert len(result) == 1
    new_score, row = result[0]
    # Shape, not exact values (real scores vary)
    assert isinstance(row["quality_score"], float)
    assert 0.0 <= row["quality_score"] <= 1.0
    assert row["quality_tier"] in (None, "medium", "high")
    assert row["quality_boost"] in (1.0, 1.15, 1.25)
    assert "score_pre_quality" in row
    assert row["score_pre_quality"] == 0.5
```

- [ ] **Step 13: Run the smoke test to verify vendored import-graph**

```bash
python -m pytest tests/test_quality_rerank.py::test_apply_quality_rerank_smoke -v 2>&1 | tail -10
```

Expected: PASS. May take a few seconds due to spaCy model load. If `ImportError` or `ModuleNotFoundError`, the vendored copy missed a file or the import path is wrong.

- [ ] **Step 14: Format + lint**

```bash
ruff format cognitive_castle/quality_rerank.py tests/test_quality_rerank.py
ruff check cognitive_castle/quality_rerank.py tests/test_quality_rerank.py
```

- [ ] **Step 15: Commit**

```bash
git add cognitive_castle/quality_rerank.py tests/test_quality_rerank.py
git commit -m "$(cat <<'EOF'
feat(quality_rerank): Stage 6 core implementation

Public entry apply_quality_rerank(reranked, cfg) → list[tuple[float, dict]].
Two-tier threshold rule:
  score >= cfg.quality_threshold_high (0.60) → "high",   ×1.25
  score >= cfg.quality_threshold_medium (0.53) → "medium", ×1.15
  otherwise → None, ×1.0

Per-hit audit fields: quality_score, quality_tier, quality_boost,
score_pre_quality. Always present after Stage 6 runs.

Graceful degradation: import failure → all hits default; per-hit metric
failure → that hit defaults, others continue; KeyboardInterrupt
propagates (not caught).

Lazy-imports cognitive_castle.understanding so spaCy load only happens
when Stage 6 actually fires.

20 tests: 6 tier classification (pure function), 7 apply_quality_rerank
with mocked metrics, 6 failure modes, 1 slow smoke test exercising the
real vendored package.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Wire Stage 6 into `searcher.py` (audit fields + `_stage_6_quality` + `_apply_optional_stages`)

**Files:**
- Modify: `cognitive_castle/searcher.py`
- Test: `tests/test_pipeline_order.py` (append) + `tests/test_searcher.py` (append)

**Agent model:** sonnet (judgment — integration, audit-line printer, return-dict shape)

**Notes:** This task connects the Stage 6 core (Task 5) to the search pipeline. Three sub-pieces: (a) add `_stage_6_quality` lazy-wrapper, (b) update `_apply_optional_stages` to actually run Stage 6 when `quality_rerank=True`, (c) update `_print_search_results` to render the audit line, and (d) update `_new_pipeline_search` to thread `quality_rerank` through and add the four `quality_*` fields to the per-hit return dict.

- [ ] **Step 1: Write failing tests for Stage 6 wiring in `tests/test_pipeline_order.py`**

Append to `tests/test_pipeline_order.py`:

```python
def test_quality_runs_when_quality_rerank_flag_set(monkeypatch, tmp_path):
    """When quality_rerank=True is passed, _stage_6_quality is invoked."""
    import cognitive_castle.searcher as searcher_mod

    invocations = []

    def stub_stage_6(reranked, cfg):
        invocations.append(reranked)
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_6_quality", stub_stage_6)

    cfg_obj = type("C", (), {
        "llm_judge_top_n": 5,
        "soar_enabled": True,
        "soar_rules_path": None,
        "palace_path": str(tmp_path),
        "quality_enabled": True,
    })()

    reranked = [(0.9, {"id": "a", "score": 0.9})]
    searcher_mod._apply_optional_stages(
        query="q",
        reranked=reranked,
        cfg=cfg_obj,
        llm_rerank=False,
        soar_boost=False,
        soar_first=False,
        quality_rerank=True,
    )

    assert len(invocations) == 1


def test_quality_skipped_when_flag_off(monkeypatch, tmp_path):
    """When quality_rerank=False, _stage_6_quality is NOT invoked."""
    import cognitive_castle.searcher as searcher_mod

    invocations = []

    def stub_stage_6(reranked, cfg):
        invocations.append(reranked)
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_6_quality", stub_stage_6)

    cfg_obj = type("C", (), {
        "llm_judge_top_n": 5,
        "soar_enabled": True,
        "soar_rules_path": None,
        "palace_path": str(tmp_path),
    })()

    reranked = [(0.9, {"id": "a", "score": 0.9})]
    searcher_mod._apply_optional_stages(
        query="q",
        reranked=reranked,
        cfg=cfg_obj,
        llm_rerank=False,
        soar_boost=False,
        soar_first=False,
        quality_rerank=False,
    )

    assert len(invocations) == 0


def test_judge_soar_quality_compound_in_default_order(monkeypatch, tmp_path):
    """All three optional stages fire in order: 4 → 5 → 6."""
    import cognitive_castle.searcher as searcher_mod

    call_order = []

    def fake_stage_4(query, reranked, cfg):
        call_order.append("stage_4")
        return reranked

    def fake_stage_5(reranked, cfg, query=""):
        call_order.append("stage_5")
        return reranked

    def fake_stage_6(reranked, cfg):
        call_order.append("stage_6")
        return reranked

    monkeypatch.setattr(searcher_mod, "_stage_4_judge", fake_stage_4)
    monkeypatch.setattr(searcher_mod, "_stage_5_soar", fake_stage_5)
    monkeypatch.setattr(searcher_mod, "_stage_6_quality", fake_stage_6)

    cfg_obj = type("C", (), {
        "llm_judge_top_n": 5,
        "soar_enabled": True,
        "soar_rules_path": None,
        "palace_path": str(tmp_path),
        "quality_enabled": True,
    })()

    searcher_mod._apply_optional_stages(
        query="q",
        reranked=[(0.9, {"id": "a", "score": 0.9})],
        cfg=cfg_obj,
        llm_rerank=True,
        soar_boost=True,
        soar_first=False,
        quality_rerank=True,
    )

    assert call_order == ["stage_4", "stage_5", "stage_6"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_pipeline_order.py -k "quality" -v 2>&1 | tail -10
```

Expected: 3 FAIL with `AttributeError: module 'cognitive_castle.searcher' has no attribute '_stage_6_quality'`.

- [ ] **Step 3: Read existing `_stage_4_judge` and `_stage_5_soar` for style reference**

```bash
grep -B1 -A15 "^def _stage_4_judge\|^def _stage_5_soar" cognitive_castle/searcher.py
```

Expected: both functions exist as thin lazy-wrappers around their respective modules. The pattern to mirror.

- [ ] **Step 4: Add `_stage_6_quality` to `cognitive_castle/searcher.py`**

Insert immediately after `_stage_5_soar` (around line 420):

```python
def _stage_6_quality(
    reranked: list[tuple[float, dict]],
    cfg,
) -> list[tuple[float, dict]]:
    """Stage 6: deterministic text-quality rerank.

    Delegates to quality_rerank.apply_quality_rerank. Lazy-imports
    quality_rerank so the module is only loaded when quality_rerank is on
    (preserves the "no Stage 6 overhead by default" invariant).

    Never raises. Same graceful-fallback behavior as soar_bridge.
    """
    from . import quality_rerank

    return quality_rerank.apply_quality_rerank(reranked, cfg)
```

- [ ] **Step 5: Update `_apply_optional_stages` to invoke Stage 6**

Find the existing function body (around line 423). The existing body delegates to `_stage_4_judge` and `_stage_5_soar` in either of two orders. Add Stage 6 as the FINAL pass regardless of soar_first:

```python
def _apply_optional_stages(
    query: str,
    reranked: list[tuple[float, dict]],
    cfg,
    llm_rerank: bool,
    soar_boost: bool,
    soar_first: bool,
    quality_rerank: bool = False,
) -> list[tuple[float, dict]]:
    """Run optional Stages 4 (judge), 5 (SOAR), and 6 (quality rerank) in
    the requested order.

    Default order (soar_first=False): Stage 4 → Stage 5 → Stage 6.

    soar_first=True: Stage 5 → Stage 4 → Stage 6 (SOAR re-ranks the full
    reranked list, then judge truncates to top-N, then quality reranks).
    Stage 6 always runs last.

    Each stage is gated by its own boolean flag — any combination of
    on/off works. Stages are mutually composable; their score multipliers
    compound multiplicatively.
    """
    if soar_first:
        if soar_boost:
            reranked = _stage_5_soar(reranked, cfg, query=query)
        if llm_rerank:
            reranked = _stage_4_judge(query, reranked, cfg)
    else:
        if llm_rerank:
            reranked = _stage_4_judge(query, reranked, cfg)
        if soar_boost:
            reranked = _stage_5_soar(reranked, cfg, query=query)

    if quality_rerank:
        reranked = _stage_6_quality(reranked, cfg)

    return reranked
```

- [ ] **Step 6: Run the Stage 6 wiring tests to verify they pass**

```bash
python -m pytest tests/test_pipeline_order.py -k "quality" -v 2>&1 | tail -10
```

Expected: 3 PASS.

- [ ] **Step 7: Write failing tests for the search_memories return dict shape**

Append to `tests/test_searcher.py`:

```python
def test_search_memories_return_dict_has_quality_fields_when_enabled(
    tmp_path, monkeypatch
):
    """When quality_rerank=True, returned hits include quality_* fields."""
    import cognitive_castle.searcher as searcher_mod

    # Stub _new_pipeline_search to return a hand-crafted result
    def stub_pipeline(query, palace_path, wing, room, n_results, cfg, **kwargs):
        return [
            {
                "id": "a",
                "text": "test",
                "document": "test",
                "score": 1.25,
                "wing": "w",
                "room": "r",
                "source_file": "f",
                "created_at": "2026-05-14T00:00:00",
                "similarity": 1.25,
                "entity_match": False,
                "soar_tags": [],
                "soar_boost": 1.0,
                "score_pre_soar": 1.0,
                "quality_score": 0.75,
                "quality_tier": "high",
                "quality_boost": 1.25,
                "score_pre_quality": 1.0,
            }
        ]

    monkeypatch.setattr(searcher_mod, "_new_pipeline_search", stub_pipeline)

    result = searcher_mod.search_memories(
        query="test",
        palace_path=str(tmp_path),
        quality_rerank=True,
    )
    hits = result["results"] if isinstance(result, dict) else result
    assert len(hits) == 1
    hit = hits[0]
    assert hit["quality_score"] == 0.75
    assert hit["quality_tier"] == "high"
    assert hit["quality_boost"] == 1.25
    assert hit["score_pre_quality"] == 1.0


def test_search_memories_return_dict_has_default_quality_fields_when_disabled(
    tmp_path, monkeypatch
):
    """When quality_rerank=False, returned hits have default quality_* fields."""
    import cognitive_castle.searcher as searcher_mod

    def stub_pipeline(query, palace_path, wing, room, n_results, cfg, **kwargs):
        return [
            {
                "id": "a",
                "text": "test",
                "document": "test",
                "score": 1.0,
                "wing": "w",
                "room": "r",
                "source_file": "f",
                "created_at": "2026-05-14T00:00:00",
                "similarity": 1.0,
                "entity_match": False,
                "soar_tags": [],
                "soar_boost": 1.0,
                "score_pre_soar": 1.0,
                "quality_score": None,
                "quality_tier": None,
                "quality_boost": 1.0,
                "score_pre_quality": 1.0,
            }
        ]

    monkeypatch.setattr(searcher_mod, "_new_pipeline_search", stub_pipeline)

    result = searcher_mod.search_memories(
        query="test",
        palace_path=str(tmp_path),
        quality_rerank=False,
    )
    hits = result["results"] if isinstance(result, dict) else result
    assert hits[0]["quality_score"] is None
    assert hits[0]["quality_tier"] is None
    assert hits[0]["quality_boost"] == 1.0


def test_print_search_results_renders_quality_high_audit_line(capsys):
    """When quality_tier='high', the QUALITY: line is printed."""
    from cognitive_castle.searcher import _print_search_results

    result = {
        "results": [
            {
                "text": "test text",
                "score": 1.25,
                "wing": "w",
                "room": "r",
                "source_file": "f.md",
                "quality_score": 0.78,
                "quality_tier": "high",
                "quality_boost": 1.25,
                "score_pre_quality": 1.0,
            }
        ],
        "filters": {},
    }
    _print_search_results(result, "test query")
    captured = capsys.readouterr()
    assert "QUALITY: high" in captured.out
    assert "×1.250" in captured.out
    assert "score=0.78" in captured.out


def test_print_search_results_renders_quality_medium_audit_line(capsys):
    """When quality_tier='medium', the QUALITY: line is printed."""
    from cognitive_castle.searcher import _print_search_results

    result = {
        "results": [
            {
                "text": "test text",
                "score": 1.15,
                "wing": "w",
                "room": "r",
                "source_file": "f.md",
                "quality_score": 0.56,
                "quality_tier": "medium",
                "quality_boost": 1.15,
                "score_pre_quality": 1.0,
            }
        ],
        "filters": {},
    }
    _print_search_results(result, "test query")
    captured = capsys.readouterr()
    assert "QUALITY: medium" in captured.out
    assert "×1.150" in captured.out


def test_print_search_results_suppresses_quality_line_when_tier_none(capsys):
    """When quality_tier=None, NO QUALITY: line is printed."""
    from cognitive_castle.searcher import _print_search_results

    result = {
        "results": [
            {
                "text": "test text",
                "score": 0.5,
                "wing": "w",
                "room": "r",
                "source_file": "f.md",
                "quality_score": 0.40,
                "quality_tier": None,
                "quality_boost": 1.0,
                "score_pre_quality": 0.5,
            }
        ],
        "filters": {},
    }
    _print_search_results(result, "test query")
    captured = capsys.readouterr()
    assert "QUALITY:" not in captured.out
```

- [ ] **Step 8: Run tests to verify they fail**

```bash
python -m pytest tests/test_searcher.py -k "quality" -v 2>&1 | tail -15
```

Expected: FAIL — the return dict doesn't yet include quality_* fields, the printer doesn't render the QUALITY line, and `search_memories` doesn't accept `quality_rerank` kwarg.

- [ ] **Step 9: Thread `quality_rerank` through `search_memories` and `_new_pipeline_search`**

Find `def search_memories(` in `cognitive_castle/searcher.py`. Add `quality_rerank: bool = False` to its parameters. Pass it through to `_new_pipeline_search`.

Then find `def _new_pipeline_search(` and similarly add `quality_rerank: bool = False`. In the body, pass it to `_apply_optional_stages`:

```python
    reranked = _apply_optional_stages(
        query=query,
        reranked=reranked,
        cfg=cfg,
        llm_rerank=llm_rerank,
        soar_boost=soar_boost,
        soar_first=soar_first,
        quality_rerank=quality_rerank,
    )
```

Also extend the per-hit return-dict construction (around line 597-614) with the four new audit fields. Locate the existing dict-comprehension that returns hits and add:

```python
            "quality_score": (
                r.get("quality_score") if isinstance(r, dict) else None
            ),
            "quality_tier": (
                r.get("quality_tier") if isinstance(r, dict) else None
            ),
            "quality_boost": (
                float(r.get("quality_boost", 1.0)) if isinstance(r, dict) else 1.0
            ),
            "score_pre_quality": (
                float(r.get("score_pre_quality", s)) if isinstance(r, dict) else float(s)
            ),
```

(Match the existing field pattern — see the `soar_tags` / `soar_boost` / `score_pre_soar` defaults for the exact style.)

Similarly update `search()` (the CLI entry point) to accept and pass `quality_rerank=False`.

- [ ] **Step 10: Update `_print_search_results` to render the QUALITY audit line**

Find the function (around line 145). Locate where the `SOAR:` audit line is rendered. Add an analogous block for QUALITY:

```python
        # Existing SOAR audit-line block here...

        # NEW: QUALITY audit line
        quality_tier = hit.get("quality_tier")
        if quality_tier is not None:
            q_score = float(hit.get("quality_score", 0.0))
            q_boost = float(hit.get("quality_boost", 1.0))
            print(
                f"      QUALITY: {quality_tier} (×{q_boost:.3f}, score={q_score:.2f})"
            )
```

(Match the existing `SOAR:` print-format spacing exactly so the two audit lines align visually.)

- [ ] **Step 11: Run the new searcher tests to verify they pass**

```bash
python -m pytest tests/test_searcher.py -k "quality" -v 2>&1 | tail -15
```

Expected: 5 PASS.

- [ ] **Step 12: Run the full test suite to verify zero regression**

```bash
python -m pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -3
```

Expected: `0 failed`.

- [ ] **Step 13: Format + lint**

```bash
ruff format cognitive_castle/searcher.py tests/test_pipeline_order.py tests/test_searcher.py
ruff check cognitive_castle/searcher.py tests/test_pipeline_order.py tests/test_searcher.py
```

- [ ] **Step 14: Commit**

```bash
git add cognitive_castle/searcher.py tests/test_pipeline_order.py tests/test_searcher.py
git commit -m "$(cat <<'EOF'
feat(searcher): wire Stage 6 (quality rerank) into pipeline

- Add _stage_6_quality lazy-wrapper (mirrors _stage_4_judge,
  _stage_5_soar pattern)
- _apply_optional_stages now invokes Stage 6 last when
  quality_rerank=True; runs after Stages 4 and 5 regardless of
  soar_first flag
- search_memories and _new_pipeline_search accept quality_rerank
  bool param (default False, back-compatible)
- Per-hit return dict gains quality_score, quality_tier,
  quality_boost, score_pre_quality fields (always present)
- _print_search_results renders "QUALITY: <tier> (×<boost>, score=<x>)"
  line when quality_tier is not None; suppressed for below-threshold
  hits (matches SOAR's audit-suppression idiom)

8 new tests: 3 pipeline ordering + 5 search return-dict / audit-line
rendering.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: CLI flag — `--quality-rerank`

**Files:**
- Modify: `cognitive_castle/cli.py`
- Test: `tests/test_cli.py` (append)

**Agent model:** haiku (mechanical, mirrors `--soar-boost` exactly)

**Notes:** Add the flag + kill-switch validation. Pattern is verbatim from SOAR's `--soar-boost` handling.

- [ ] **Step 1: Read existing `--soar-boost` handling for the pattern**

```bash
grep -B2 -A10 "soar_boost\|CASTLE_SOAR_ENABLED\|soar_enabled" cognitive_castle/cli.py | head -40
```

Expected: shows the argparse flag definition AND the kill-switch validation block that exits 2 when the flag is set but `cfg.soar_enabled` is False.

- [ ] **Step 2: Write failing tests** — append to `tests/test_cli.py`:

```python
def test_cli_quality_rerank_without_kill_switch_exits_2(tmp_path, monkeypatch, capsys):
    """--quality-rerank without CASTLE_QUALITY_ENABLED=1 should exit 2 with
    a kill-switch message."""
    monkeypatch.delenv("CASTLE_QUALITY_ENABLED", raising=False)
    from cognitive_castle.cli import cmd_search
    import argparse

    args = argparse.Namespace(
        query="test",
        palace=str(tmp_path),
        wing=None,
        room=None,
        results=5,
        llm_rerank=False,
        soar_boost=False,
        soar_first=False,
        quality_rerank=True,
    )
    with pytest.raises(SystemExit) as exc_info:
        cmd_search(args)
    assert exc_info.value.code == 2

    captured = capsys.readouterr()
    assert "CASTLE_QUALITY_ENABLED" in captured.err or "CASTLE_QUALITY_ENABLED" in captured.out


def test_cli_quality_rerank_with_kill_switch_threads_through(
    tmp_path, monkeypatch
):
    """--quality-rerank with CASTLE_QUALITY_ENABLED=1 should invoke search()
    with quality_rerank=True."""
    monkeypatch.setenv("CASTLE_QUALITY_ENABLED", "1")

    captured_kwargs = {}

    def stub_search(**kwargs):
        captured_kwargs.update(kwargs)

    monkeypatch.setattr("cognitive_castle.searcher.search", stub_search)

    from cognitive_castle.cli import cmd_search
    import argparse

    args = argparse.Namespace(
        query="test",
        palace=str(tmp_path),
        wing=None,
        room=None,
        results=5,
        llm_rerank=False,
        soar_boost=False,
        soar_first=False,
        quality_rerank=True,
    )
    cmd_search(args)
    assert captured_kwargs.get("quality_rerank") is True
```

Verify `pytest` is imported at the top of `tests/test_cli.py`; if not, add the import.

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_cli.py -k "quality_rerank" -v 2>&1 | tail -10
```

Expected: 2 FAIL — the flag doesn't exist, the validation doesn't exist, or `cmd_search` doesn't accept it.

- [ ] **Step 4: Add the `--quality-rerank` argparse flag**

Find the existing `subparser` definition for `castle search` in `cognitive_castle/cli.py` (look for `--soar-boost`). Immediately after the SOAR flag definitions, add:

```python
    search_parser.add_argument(
        "--quality-rerank",
        action="store_true",
        help=(
            "Apply Stage 6 deterministic text-quality rerank via the "
            "vendored `understanding` package (experimental; requires "
            "spaCy + en_core_web_sm; activate via CASTLE_QUALITY_ENABLED=1). "
            "Off by default."
        ),
    )
```

(Mirror the exact flag-help-text format from `--soar-boost` for visual consistency.)

- [ ] **Step 5: Add the kill-switch validation + thread the flag through**

In `cmd_search`, immediately after the `--soar-boost` kill-switch validation block, add:

```python
    quality_rerank = getattr(args, "quality_rerank", False)
    if quality_rerank and not cfg.quality_enabled:
        print(
            "--quality-rerank requires CASTLE_QUALITY_ENABLED=1 "
            "(kill switch is active to prevent accidental Stage 6 invocation; "
            "set the env var to enable Stage 6)",
            file=sys.stderr,
        )
        sys.exit(2)
```

Then update the `search()` call to include `quality_rerank=quality_rerank`:

```python
        search(
            query=args.query,
            palace_path=palace_path,
            wing=args.wing,
            room=args.room,
            n_results=args.results,
            llm_rerank=llm_rerank,
            soar_boost=soar_boost,
            soar_first=soar_first,
            quality_rerank=quality_rerank,  # NEW
        )
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_cli.py -k "quality_rerank" -v 2>&1 | tail -10
```

Expected: 2 PASS.

- [ ] **Step 7: Run full CLI test suite to verify zero regression**

```bash
python -m pytest tests/test_cli.py -q 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 8: Format + lint**

```bash
ruff format cognitive_castle/cli.py tests/test_cli.py
ruff check cognitive_castle/cli.py tests/test_cli.py
```

- [ ] **Step 9: Commit**

```bash
git add cognitive_castle/cli.py tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(cli): add --quality-rerank flag for Stage 6

Mirrors --soar-boost: opt-in CLI flag with CASTLE_QUALITY_ENABLED=1
kill-switch validation. Exits 2 with informative message when flag
is set but kill-switch isn't.

Threads quality_rerank=True through to searcher.search().

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: MCP param — `quality_rerank`

**Files:**
- Modify: `cognitive_castle/mcp_server.py`
- Test: `tests/test_mcp_server.py` (append)

**Agent model:** haiku (mechanical, mirrors SOAR MCP param exactly)

- [ ] **Step 1: Read existing SOAR MCP-param handling**

```bash
grep -B2 -A10 "soar_boost\|quality_rerank\|castle_search" cognitive_castle/mcp_server.py | head -40
```

Identify the `castle_search` tool definition and the kill-switch validation. The pattern to mirror is verbatim from `soar_boost`.

- [ ] **Step 2: Write failing tests** — append to `tests/test_mcp_server.py`:

```python
def test_mcp_quality_rerank_param_without_kill_switch_returns_error(
    tmp_path, monkeypatch
):
    """quality_rerank=true MCP param without CASTLE_QUALITY_ENABLED=1
    should return an MCP-level error."""
    monkeypatch.delenv("CASTLE_QUALITY_ENABLED", raising=False)

    from cognitive_castle.mcp_server import handle_search

    result = handle_search(
        query="test",
        palace_path=str(tmp_path),
        quality_rerank=True,
    )
    # Result should signal an error — exact shape depends on MCP server's
    # convention (probably an "error" key or an exit-2 path captured)
    assert "error" in result or "CASTLE_QUALITY_ENABLED" in str(result)


def test_mcp_quality_rerank_param_with_kill_switch_threads_through(
    tmp_path, monkeypatch
):
    """quality_rerank=true with kill-switch active should reach search_memories."""
    monkeypatch.setenv("CASTLE_QUALITY_ENABLED", "1")

    captured_kwargs = {}

    def stub_search_memories(**kwargs):
        captured_kwargs.update(kwargs)
        return {"results": []}

    monkeypatch.setattr("cognitive_castle.searcher.search_memories", stub_search_memories)

    from cognitive_castle.mcp_server import handle_search

    handle_search(
        query="test",
        palace_path=str(tmp_path),
        quality_rerank=True,
    )
    assert captured_kwargs.get("quality_rerank") is True
```

If `handle_search` isn't the exact entry-point name in `mcp_server.py`, grep for the actual handler and adjust.

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_mcp_server.py -k "quality_rerank" -v 2>&1 | tail -10
```

Expected: 2 FAIL.

- [ ] **Step 4: Add the MCP param + validation**

In `cognitive_castle/mcp_server.py`, find the `castle_search` tool definition (or its handler). Add a `quality_rerank: bool = False` parameter to the function signature.

In the body, add the validation immediately after the SOAR validation:

```python
    if quality_rerank and not cfg.quality_enabled:
        return {
            "error": (
                "quality_rerank requires CASTLE_QUALITY_ENABLED=1 "
                "(kill switch is active to prevent accidental Stage 6 invocation)"
            )
        }
```

(Match the exact return-error pattern used elsewhere in the file. If the MCP server uses raised exceptions instead of error-dicts, follow that convention.)

Update the `search_memories(...)` call to include `quality_rerank=quality_rerank`.

Also update the MCP tool's JSON-schema definition so clients know the param exists. Find the existing schema (look near the SOAR param) and add:

```python
            "quality_rerank": {
                "type": "boolean",
                "description": (
                    "Apply Stage 6 deterministic quality rerank via the "
                    "vendored `understanding` package. Requires CASTLE_QUALITY_ENABLED=1. "
                    "Off by default."
                ),
                "default": False,
            },
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_mcp_server.py -k "quality_rerank" -v 2>&1 | tail -10
```

Expected: 2 PASS.

- [ ] **Step 6: Run full MCP test suite to verify zero regression**

```bash
python -m pytest tests/test_mcp_server.py -q 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 7: Format + lint**

```bash
ruff format cognitive_castle/mcp_server.py tests/test_mcp_server.py
ruff check cognitive_castle/mcp_server.py tests/test_mcp_server.py
```

- [ ] **Step 8: Commit**

```bash
git add cognitive_castle/mcp_server.py tests/test_mcp_server.py
git commit -m "$(cat <<'EOF'
feat(mcp): add quality_rerank param to castle_search tool

Mirrors --soar-boost MCP pattern: opt-in MCP param with
CASTLE_QUALITY_ENABLED=1 kill-switch validation. Returns an error
when param is set but kill switch isn't.

JSON-schema entry added so MCP clients see the param.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Calibration script

**Files:**
- Create: `scripts/calibrate_quality_threshold.py`

**Agent model:** haiku (mechanical CLI tool — the script we already ran during brainstorming)

**Notes:** Commit the calibration script for reproducibility. Users re-run it when palace changes materially. Output: distribution stats + histogram.

- [ ] **Step 1: Verify the `scripts/` directory exists**

```bash
ls scripts/ 2>&1 | head -10
```

If `scripts/` doesn't exist, create it: `mkdir scripts`.

- [ ] **Step 2: Write the calibration script**

Create `scripts/calibrate_quality_threshold.py`:

```python
#!/usr/bin/env python3
"""Calibrate quality_threshold_medium and _high defaults from a palace sample.

Usage:
    python scripts/calibrate_quality_threshold.py \\
        --palace ~/.castle/palace \\
        --sample-size 100 \\
        --seed 42

Prints distribution stats + histogram of overall_weighted_average across
a random sample of drawers. Use p75 → quality_threshold_medium,
p90 → quality_threshold_high (or whichever percentiles match your boost
policy).

Not a test. One-shot investigation tool. Re-run after major ingest
changes.
"""

from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
from pathlib import Path

# Force CPU to avoid GPU contention with other Castle processes
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--palace",
        default=os.path.expanduser("~/.castle/palace"),
        help="Path to the palace directory (default: ~/.castle/palace)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of drawers to sample randomly (default: 100)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    args = parser.parse_args()

    palace_path = str(Path(args.palace).expanduser().resolve())
    if not Path(palace_path).exists():
        print(f"ERROR: palace not found at {palace_path}", file=sys.stderr)
        return 2

    from cognitive_castle.palace import get_collection
    from cognitive_castle.understanding import analyze_with_enhanced_metrics

    col = get_collection(palace_path=palace_path)
    all_ids = col.list_drawer_ids()
    print(f"palace has {len(all_ids)} drawers")

    if len(all_ids) == 0:
        print("ERROR: palace has no drawers", file=sys.stderr)
        return 2

    random.seed(args.seed)
    sample_ids = random.sample(all_ids, min(args.sample_size, len(all_ids)))
    rows = col.get_by_ids(sample_ids)
    print(f"sampled {len(rows)} drawers")
    print()

    t0 = time.time()
    scores: list[float] = []
    text_lens: list[int] = []
    errors: list[str] = []
    for row in rows:
        try:
            text = row["text"]
            text_lens.append(len(text))
            r = analyze_with_enhanced_metrics(text)
            score = r["enhanced_metrics"]["overall_weighted_average"]
            scores.append(score)
        except Exception as e:
            errors.append(type(e).__name__)
            continue

    dt = time.time() - t0
    print(
        f"computed {len(scores)} scores in {dt:.1f}s "
        f"({dt * 1000 / max(len(scores), 1):.0f}ms/drawer avg)"
    )
    if errors:
        print(f"errors: {len(errors)} — {set(errors)}")
    print()

    if text_lens:
        print("TEXT LENGTH distribution:")
        print(
            f"  min={min(text_lens)}  "
            f"median={statistics.median(text_lens):.0f}  "
            f"max={max(text_lens)}  mean={statistics.mean(text_lens):.0f}"
        )
        print()

    if not scores:
        print("ERROR: no scores computed", file=sys.stderr)
        return 2

    print("SCORE distribution (overall_weighted_average):")
    print(f"  n={len(scores)}")
    print(f"  min={min(scores):.3f}  max={max(scores):.3f}")
    print(
        f"  mean={statistics.mean(scores):.3f}  "
        f"stdev={statistics.stdev(scores):.3f}"
    )
    if len(scores) >= 10:
        q = statistics.quantiles(scores, n=10)
        print(
            f"  p10={q[0]:.3f}  p25={q[1]:.3f}  p50={q[4]:.3f}  "
            f"p75={q[6]:.3f}  p90={q[8]:.3f}"
        )
    print()

    # Histogram
    bins = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    counts = [0] * (len(bins) - 1)
    for s in scores:
        for i in range(len(bins) - 1):
            if bins[i] <= s < bins[i + 1] or (i == len(bins) - 2 and s == 1.0):
                counts[i] += 1
                break
    print("HISTOGRAM:")
    for i in range(len(bins) - 1):
        bar = "#" * counts[i]
        print(f"  [{bins[i]:.1f}-{bins[i + 1]:.1f})  {counts[i]:3d}  {bar}")

    print()
    print("RECOMMENDED THRESHOLDS:")
    if len(scores) >= 10:
        print(f"  quality_threshold_medium = {q[6]:.2f}  (p75)")
        print(f"  quality_threshold_high   = {q[8]:.2f}  (p90)")
    else:
        print("  (need at least 10 scores for percentile recommendations)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Make the script executable + verify it runs**

```bash
chmod +x scripts/calibrate_quality_threshold.py
CUDA_VISIBLE_DEVICES="" python scripts/calibrate_quality_threshold.py --palace ~/.castle/palace --sample-size 50 --seed 42 2>&1 | tail -25
```

Expected: distribution + histogram + recommended thresholds. If the palace has fewer than 50 drawers (unlikely), the script handles that gracefully.

- [ ] **Step 4: Verify recommended thresholds match spec defaults (within ~10%)**

Compare the printed `RECOMMENDED THRESHOLDS` to the spec's `0.53` / `0.60`. If they've drifted by >10% (e.g., p75 is now 0.45 or 0.62), the palace has materially changed since 2026-05-14. **STOP and report:** the spec's defaults may need updating in this PR. See spec's Pre-merge re-calibration acceptance criterion.

If thresholds are within ~10% of spec, defaults are fine; proceed.

- [ ] **Step 5: Format + lint**

```bash
ruff format scripts/calibrate_quality_threshold.py
ruff check scripts/calibrate_quality_threshold.py
```

- [ ] **Step 6: Commit**

```bash
git add scripts/calibrate_quality_threshold.py
git commit -m "$(cat <<'EOF'
docs(scripts): calibration tool for Stage 6 threshold defaults

One-shot CLI: random-sample drawers from a palace, compute
overall_weighted_average, print distribution + histogram, recommend
thresholds at p75 / p90.

Use this to re-calibrate Stage 6 defaults if the palace has changed
materially since the 2026-05-14 measurement (spec's "Pre-merge
re-calibration" acceptance criterion).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: CLAUDE.md doc + final integration + PR

**Files:**
- Modify: `CLAUDE.md`
- All files already touched

**Agent model:** sonnet (judgment — final pre-merge sanity check, real CLI smoke, PR body)

- [ ] **Step 1: Update `CLAUDE.md`'s retrieval-pipeline diagram**

Find the existing Architecture section's pipeline diagram. Add a line for Stage 6:

```markdown
    ├── Stage 6 (optional, opt-in `--quality-rerank` + `CASTLE_QUALITY_ENABLED=1`):
    │     deterministic text-quality rerank via vendored `understanding/` package —
    │     two-tier threshold rule with calibrated defaults (medium ×1.15, high ×1.25)
```

(Match the indentation and prefix-char style of the surrounding Stage 4 / Stage 5 lines.)

- [ ] **Step 2: Run the full test suite to confirm 0 regressions**

```bash
python -m pytest tests/ --ignore=tests/benchmarks -q 2>&1 | tail -3
```

Expected: `0 failed, NNNN passed` (where NNNN matches the baseline + new tests).

- [ ] **Step 3: Run `ruff format` and `ruff check` on the whole repo**

```bash
ruff format .
ruff check .
```

Both must be clean. If anything changes, commit it:

```bash
git add -u
git commit -m "style: ruff format on PR-scope files

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Run the CLI smoke test against the live palace**

```bash
CUDA_VISIBLE_DEVICES="" CASTLE_QUALITY_ENABLED=1 castle search "what did we decide about the embedder" --results 5 --quality-rerank 2>&1 | grep -E "score=|SOAR:|QUALITY:|^\s+\[" | head -20
```

Expected: at least one hit shows a `QUALITY: high (×1.250, score=...)` or `QUALITY: medium (×1.150, score=...)` audit line. If NO QUALITY lines appear, EITHER:
- All hits scored below 0.53 (possible if the palace has drifted from the calibration baseline — confirm with the calibration script)
- Stage 6 isn't actually firing (regression — investigate)

- [ ] **Step 5: Commit CLAUDE.md update**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(CLAUDE.md): document Stage 6 (quality rerank) in pipeline diagram

Add one line to the Architecture section's retrieval-pipeline diagram
describing Stage 6's opt-in mechanism and two-tier threshold rule.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Push the branch**

```bash
git push -u origin feat/quality-rerank-stage-6
```

- [ ] **Step 7: Open the PR**

```bash
gh pr create --title "feat: Stage 6 — deterministic quality rerank (vendored understanding/)" --body "$(cat <<'EOF'
## Summary
Adds Stage 6 to Castle's retrieval pipeline: optional post-retrieval quality rerank using 31 deterministic, peer-reviewed-paper-grounded text-quality metrics from the user's `understanding` package (vendored, MIT, ~/echelon/).

Two-tier threshold rule with defaults calibrated to the user's palace on 2026-05-14:
- score >= 0.60 → "high" → ×1.25
- 0.53 ≤ score < 0.60 → "medium" → ×1.15
- otherwise → no boost

Opt-in via `--quality-rerank` flag + `CASTLE_QUALITY_ENABLED=1` kill-switch (mirrors SOAR pattern). Composable with Stages 4 (LLM-judge) and 5 (SOAR); default order judge → SOAR → quality.

## Design
See `docs/superpowers/specs/2026-05-14-quality-rerank-design.md` (v4 — five review passes). Key decisions: vendor the `understanding` package (avoid Castle → echelon → mempalace dep chain), two-tier threshold-and-boost (mirrors SOAR's auditable idiom), audit-trail fields on every hit, graceful degradation if the vendored package fails to import.

## Test plan
- [x] 20 new tests in `tests/test_quality_rerank.py` — tier classification, apply_quality_rerank, audit trail, failure modes, slow smoke test
- [x] 3 new tests in `tests/test_pipeline_order.py` — Stage 6 ordering, default judge→SOAR→quality flow
- [x] 5 new tests in `tests/test_searcher.py` — return-dict shape, audit-line rendering
- [x] 2 new tests in `tests/test_cli.py` — kill-switch validation
- [x] 2 new tests in `tests/test_mcp_server.py` — MCP param kill-switch
- [x] 15 new tests in `tests/test_config.py` — 5 properties × 3 paths each
- [x] Full suite: `pytest tests/ --ignore=tests/benchmarks` returns 0 failed
- [x] Live CLI smoke: `castle search ... --quality-rerank` shows QUALITY audit lines

## What's new
- Vendored `cognitive_castle/understanding/` package (12 .py files, MIT, faithful drop-in from echelon)
- `cognitive_castle/quality_rerank.py` — Stage 6 implementation
- `scripts/calibrate_quality_threshold.py` — reproducibility tool for re-calibrating thresholds
- 5 new config properties (`quality_enabled`, `quality_threshold_*`, `quality_boost_*`)
- spaCy + en_core_web_sm wheel added to pyproject.toml

## Out of scope (per spec)
- Closet QA application (`closet_llm` integration)
- Per-drawer index-time annotation
- `--quality-first` reordering flag
- Auto-calibration / drift detection

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 8: After review, merge + clean up**

```bash
gh pr merge <PR#> --merge --delete-branch
git checkout develop
git pull --ff-only
```

---

## Self-Review

**Spec coverage check:**
- Vendored `understanding/` directory (12 files) → Task 2 ✓
- 5 new config properties → Task 3 ✓
- `_apply_stages_4_and_5` → `_apply_optional_stages` rename → Task 4 ✓
- `quality_rerank.py` two-tier core + audit fields + failure modes → Task 5 ✓
- `_stage_6_quality` lazy wrapper + `_apply_optional_stages` invocation + return-dict shape + `_print_search_results` audit-line rendering → Task 6 ✓
- `--quality-rerank` CLI flag + kill-switch → Task 7 ✓
- `quality_rerank` MCP param + kill-switch → Task 8 ✓
- `scripts/calibrate_quality_threshold.py` → Task 9 ✓
- CLAUDE.md pipeline diagram update → Task 10 ✓
- Live CLI smoke → Task 10 ✓
- Pre-merge re-calibration check (rule-of-thumb: >10% palace growth) → Task 9 Step 4 ✓
- spaCy + `en_core_web_sm` install verification → Task 1 ✓
- Smoke test using real `understanding` package → Task 5 Step 12-13 ✓
- Slow marker for the real-package test → Task 5 Step 12 ✓
- Lazy-import discipline → Task 5 (in `apply_quality_rerank`), Task 6 (in `_stage_6_quality`)

**Placeholder scan:** all steps contain concrete code or commands. No TBDs. No "similar to Task N" without code.

**Type consistency:**
- `apply_quality_rerank(reranked: list[tuple[float, dict]], cfg) -> list[tuple[float, dict]]` — consistent in Tasks 5 and 6
- `_classify_tier(score: float, cfg) -> tuple[Optional[str], float]` — consistent in Task 5
- Per-hit dict fields: `quality_score`, `quality_tier`, `quality_boost`, `score_pre_quality` — consistent across Tasks 5, 6, 7, 8
- Config property names: `quality_enabled`, `quality_threshold_medium`, `quality_threshold_high`, `quality_boost_medium`, `quality_boost_high` — consistent across all tasks
- `_stage_6_quality(reranked, cfg) -> list[tuple[float, dict]]` — defined Task 6, mocked Task 6 tests
- `ADAPTER_NAME = "quality-rerank"` constant — defined Task 5, not consumed anywhere yet (reserved for future symmetry with SOAR's adapter naming)

No issues found.
