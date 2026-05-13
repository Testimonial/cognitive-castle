# `gemma3:e4b` → `gemma3:4b` Default-LLM-Tag Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `gemma3:e4b` (a non-existent Ollama tag introduced by PR #20 as a typo) with `gemma3:4b` (real, multilingual, ~3.3 GB) across all production + test + doc sites so users who accept Castle's defaults get a working LLM on first run.

**Architecture:** Pure string-replacement. 10 substring replacements across 9 grep-matched lines in 4 files + 1 README warning-paragraph removal. No logic changes, no new helpers, no schema impact.

**Tech Stack:** Python 3.12, Ollama. The fix unlocks the standard `ollama pull gemma3:4b → it works` UX that's broken today (`ollama pull gemma3:e4b` fails — the tag doesn't exist in the registry).

**Spec:** [`docs/superpowers/specs/2026-05-13-gemma3-default-fix-design.md`](../specs/2026-05-13-gemma3-default-fix-design.md) (commit `7984e7da`).

**File map (4 files, 10 substring replacements + 1 paragraph removal):**

| File | Change | Sites |
|---|---|---|
| `cognitive_castle/config.py` | property docstring + default fallback | 2 (lines 470, 483) |
| `cognitive_castle/cli.py` | comment + cmd_init double-default + argparse default + help text | 4 grep lines / 5 substring occurrences (140, 268×2, 1006, 1007) |
| `tests/test_config.py` | docstring rewrite + assertion update | 2 (lines 327, 336) |
| `README.md` | remove obsolete warning paragraph + adjacent blank line | 1 paragraph removed (lines 207-208) |

---

## Task 1: Create feature branch

**Files:** none (git only)

- [ ] **Step 1: Verify clean tree on develop with the spec commit visible**

Run:
```bash
git status
git log --oneline -3
```

Expected:
- On branch `develop`
- Working tree clean
- Latest commits include `7984e7da` (spec revision-1) and `3e5c63da` (spec initial)

- [ ] **Step 2: Create + switch to feature branch**

Run:
```bash
git checkout -b feat/gemma3-default-fix
```

Expected: `Switched to a new branch 'feat/gemma3-default-fix'`

No commit yet.

---

## Task 2: Replace all `gemma3:e4b` references + remove README warning + verify

This is one logical change with multiple edit points. Doing them all in one commit because they're interdependent (the test assertion only passes when the production default is updated).

**Files:**
- Modify: `cognitive_castle/config.py` (lines 470, 483)
- Modify: `cognitive_castle/cli.py` (lines 140, 268, 1006, 1007)
- Modify: `tests/test_config.py` (lines 327, 336)
- Modify: `README.md` (lines 207-208 — warning paragraph + trailing blank line)

- [ ] **Step 1: Baseline — verify `grep` shows the 9 expected sites**

Run:
```bash
grep -n "gemma3:e4b" /home/lbihari/cognitive-castle/cognitive_castle/config.py /home/lbihari/cognitive-castle/cognitive_castle/cli.py /home/lbihari/cognitive-castle/tests/test_config.py /home/lbihari/cognitive-castle/README.md
```

Expected output (exactly 9 lines):
```
/home/lbihari/cognitive-castle/cognitive_castle/config.py:470:        Default: ``"gemma3:e4b"`` (matches ``cmd_init``'s default at
/home/lbihari/cognitive-castle/cognitive_castle/config.py:483:        return str(self._file_config.get("llm_model", "gemma3:e4b")).strip()
/home/lbihari/cognitive-castle/cognitive_castle/cli.py:140:    # gemma3:e4b) can return a wrong likely_ai_dialogue/confidence call
/home/lbihari/cognitive-castle/cognitive_castle/cli.py:268:        provider_model = getattr(args, "llm_model", "gemma3:e4b") or "gemma3:e4b"
/home/lbihari/cognitive-castle/cognitive_castle/cli.py:1006:        default="gemma3:e4b",
/home/lbihari/cognitive-castle/cognitive_castle/cli.py:1007:        help="Model name for the chosen provider (default: gemma3:e4b for Ollama).",
/home/lbihari/cognitive-castle/tests/test_config.py:327:    Note: both are 'gemma3:e4b' which is a known pre-existing broken tag
/home/lbihari/cognitive-castle/tests/test_config.py:336:    assert cfg.llm_model == "gemma3:e4b"
/home/lbihari/cognitive-castle/README.md:207:> **⚠️ Note:** Castle's documented default LLM model is `gemma3:e4b`, but that tag doesn't exist in Ollama's registry — it's a pre-existing bug tracked in a follow-up. To actually use `--llm-rerank`, set `CASTLE_LLM_MODEL` to a model your Ollama (or other provider) has.
```

If the count differs from 9 or the line numbers don't match, STOP and re-investigate before making changes — the spec was written against this exact snapshot.

- [ ] **Step 2: Update `cognitive_castle/config.py:470` (docstring example)**

Use Edit to replace:
- old: `Default: ``"gemma3:e4b"`` (matches ``cmd_init``'s default at`
- new: `Default: ``"gemma3:4b"`` (matches ``cmd_init``'s default at`

- [ ] **Step 3: Update `cognitive_castle/config.py:483` (property default fallback)**

Use Edit to replace:
- old: `        return str(self._file_config.get("llm_model", "gemma3:e4b")).strip()`
- new: `        return str(self._file_config.get("llm_model", "gemma3:4b")).strip()`

- [ ] **Step 4: Update `cognitive_castle/cli.py:140` (comment)**

Use Edit to replace:
- old: `    # gemma3:e4b) can return a wrong likely_ai_dialogue/confidence call`
- new: `    # gemma3:4b) can return a wrong likely_ai_dialogue/confidence call`

- [ ] **Step 5: Update `cognitive_castle/cli.py:268` (cmd_init double-default — BOTH occurrences)**

This line has the broken tag TWICE. Use Edit with `replace_all=False` on the FULL LINE:
- old: `        provider_model = getattr(args, "llm_model", "gemma3:e4b") or "gemma3:e4b"`
- new: `        provider_model = getattr(args, "llm_model", "gemma3:4b") or "gemma3:4b"`

(A full-line replacement handles both occurrences in one edit. Don't try to replace just `"gemma3:e4b"` without `replace_all=True` — that would error because the string isn't unique on the line.)

- [ ] **Step 6: Update `cognitive_castle/cli.py:1006` (argparse default)**

Use Edit to replace:
- old: `        default="gemma3:e4b",`
- new: `        default="gemma3:4b",`

- [ ] **Step 7: Update `cognitive_castle/cli.py:1007` (argparse help text)**

Use Edit to replace:
- old: `        help="Model name for the chosen provider (default: gemma3:e4b for Ollama).",`
- new: `        help="Model name for the chosen provider (default: gemma3:4b for Ollama).",`

- [ ] **Step 8: Update `tests/test_config.py:336` (assertion)**

Use Edit to replace:
- old: `    assert cfg.llm_model == "gemma3:e4b"`
- new: `    assert cfg.llm_model == "gemma3:4b"`

- [ ] **Step 9: Rewrite the test's docstring at `tests/test_config.py:327`**

The current docstring (multi-line, starting at line 327) reads:

```
    Note: both are 'gemma3:e4b' which is a known pre-existing broken tag
    (the model doesn't exist in Ollama's registry). Tracking the same
    broken default keeps cmd_init and the judge consistent — both will be
    fixed together in a follow-up PR. Judge's graceful fallback covers
    the broken-default case; the user must explicitly enable --llm-rerank
    AND have a working model configured (via CASTLE_LLM_MODEL env var or
    castle.yaml) for the path to actually work end-to-end.
```

Find the EXACT lines (use `Read` if needed to confirm wrapping) and replace with:

```
    Note: both `cfg.llm_model` and `cmd_init`'s `--llm-model` default
    point at `gemma3:4b` — a real Ollama tag. The original PR #20
    introduced `gemma3:e4b` as a typo; this PR fixed it. Users who
    accept defaults get a working model on first `ollama pull`.
```

Use Edit with the old multi-line block and the new multi-line block.

- [ ] **Step 10: Remove the obsolete README warning paragraph at `README.md:207`**

The warning paragraph is line 207, with a blank line at 208 separating it from the MCP paragraph at 209. To remove cleanly, delete BOTH line 207 (warning) AND line 208 (trailing blank).

Use Edit to replace:

old (3 lines, lines 207-209):
```
> **⚠️ Note:** Castle's documented default LLM model is `gemma3:e4b`, but that tag doesn't exist in Ollama's registry — it's a pre-existing bug tracked in a follow-up. To actually use `--llm-rerank`, set `CASTLE_LLM_MODEL` to a model your Ollama (or other provider) has.

**MCP:** Claude Code and other MCP clients can pass `llm_rerank: true` to the `search_memories` (or `castle_search`) tool.
```

new (1 line):
```
**MCP:** Claude Code and other MCP clients can pass `llm_rerank: true` to the `search_memories` (or `castle_search`) tool.
```

This removes the warning + its trailing blank in one edit, leaving the env-vars paragraph (line 205) → blank (line 206) → MCP paragraph in correct flow.

- [ ] **Step 11: Verify zero remaining `gemma3:e4b` in scope**

Run:
```bash
grep -rn "gemma3:e4b" /home/lbihari/cognitive-castle/cognitive_castle/ /home/lbihari/cognitive-castle/tests/test_config.py /home/lbihari/cognitive-castle/README.md
```

Expected: **NO output** (empty result). All 10 substring occurrences in scope have been replaced.

If grep returns ANY matches, an edit was missed — go back through Steps 2-10 to find which.

The cosmetic test strings in `tests/test_llm_client.py` + `tests/test_corpus_origin_integration.py` are intentionally out of scope (per spec Non-goals). They contain arbitrary model-name identifiers that don't depend on the tag being valid.

- [ ] **Step 12: Run the 2 test_config tests — both must PASS with the new value**

Run:
```bash
cd /home/lbihari/cognitive-castle && pytest tests/test_config.py -v -k "llm_model"
```

Expected: 2 passed. If `test_llm_model_default_matches_cmd_init_default` fails with `AssertionError: assert 'gemma3:4b' == 'gemma3:4b'` — wait, that's not how it'd fail. If it fails with `AssertionError: assert 'gemma3:e4b' == 'gemma3:4b'`, that means `config.py:483` wasn't actually updated (Step 3 failed silently). Re-check.

- [ ] **Step 13: Run full default test suite — no NEW regressions vs develop baseline**

Run:
```bash
cd /home/lbihari/cognitive-castle && pytest tests/ --ignore=tests/benchmarks 2>&1 | tail -3
```

Expected: **18 failed, 1424 passed** (same as develop baseline at commit `b3cdc4e0` — no NEW failures, no NEW passes). The current cosmetic test strings in `test_llm_client.py` + `test_corpus_origin_integration.py` still use the literal string `"gemma3:e4b"` but those tests don't depend on it being a real model.

If the failure count INCREASES vs 18, investigate — the change should not break any test.

- [ ] **Step 14: Lint check**

Run:
```bash
cd /home/lbihari/cognitive-castle && ruff check cognitive_castle/config.py cognitive_castle/cli.py tests/test_config.py && ruff format --check cognitive_castle/config.py cognitive_castle/cli.py tests/test_config.py
```

Expected: no errors. If `ruff format --check` flags a formatting drift, run `ruff format <file>` to fix and re-check.

- [ ] **Step 15: Verify `castle init --help` shows the new default**

Run:
```bash
castle init --help 2>&1 | grep -A1 "llm-model"
```

Expected: output contains `--llm-model` flag with help text mentioning `gemma3:4b` (not `gemma3:e4b`).

- [ ] **Step 16: Commit**

```bash
git add cognitive_castle/config.py cognitive_castle/cli.py tests/test_config.py README.md
git commit -m "$(cat <<'EOF'
fix(default): replace broken gemma3:e4b LLM tag with gemma3:4b

PR #20 introduced gemma3:e4b as a default — a typo of gemma3:4b with
a stray "e." The tag does not exist in Ollama's registry (verified:
`ollama show gemma3:e4b` returns "model not found"). Users who
accepted Castle's defaults hit a cryptic "model not found" error.

This PR replaces all production + test + doc references with
gemma3:4b, the real Ollama tag matching the original intent.

10 substring replacements across 9 grep-matched lines in 4 files:
- cognitive_castle/config.py:470, 483 (property docstring + default)
- cognitive_castle/cli.py:140, 268 (×2), 1006, 1007 (comment + cmd_init
  fallback + argparse default + help text)
- tests/test_config.py:327, 336 (docstring + assertion)
- README.md:207-208 (obsolete "default is broken" warning paragraph)

Cosmetic test strings in tests/test_llm_client.py +
tests/test_corpus_origin_integration.py left as-is (arbitrary
identifiers; tests pass with any string).

After this fix, `ollama pull gemma3:4b → castle search --llm-rerank`
works out-of-box. Unblocks the LLM-judge Stage 4 (PR #3) and SOAR
bridge (PR #4a) for users who don't manually override CASTLE_LLM_MODEL.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Final acceptance + push + PR

**Files:** none (verification + git push only)

Walk through all 6 acceptance criteria from the spec.

- [ ] **Step 1: Acceptance #1 — grep returns zero matches in scope**

```bash
grep -rn "gemma3:e4b" cognitive_castle/ tests/test_config.py README.md
```

Expected: NO output.

- [ ] **Step 2: Acceptance #2 — test_config.py tests pass**

```bash
pytest tests/test_config.py -v -k "llm_model"
```

Expected: 2 passed.

- [ ] **Step 3: Acceptance #3 — no NEW failures**

```bash
pytest tests/ --ignore=tests/benchmarks 2>&1 | tail -3
```

Expected: 18 failed (same as develop baseline at `b3cdc4e0`), 1424 passed.

- [ ] **Step 4: Acceptance #4 — ruff clean**

```bash
ruff check cognitive_castle/config.py cognitive_castle/cli.py tests/test_config.py && ruff format --check cognitive_castle/config.py cognitive_castle/cli.py tests/test_config.py
```

Expected: no errors.

- [ ] **Step 5: Acceptance #5 — `castle init --help` shows new default**

```bash
castle init --help 2>&1 | grep -A1 "llm-model"
```

Expected: help text includes `gemma3:4b` (no `gemma3:e4b`).

- [ ] **Step 6: Acceptance #6 — README warning gone**

```bash
grep -c "gemma3:e4b" README.md
```

Expected: `0` (zero matches).

Spot-check the surrounding flow:
```bash
sed -n '203,210p' README.md
```

Expected: env-vars paragraph → blank → MCP paragraph (no warning between them).

- [ ] **Step 7: Push branch**

```bash
git push -u origin feat/gemma3-default-fix
```

- [ ] **Step 8: Open PR**

```bash
gh pr create --title "fix(default): replace broken gemma3:e4b LLM tag with gemma3:4b" --body "$(cat <<'EOF'
## Summary

Closes the queued follow-up from PR #3 (LLM-judge Stage 4) and PR #4a (SOAR bridge) umbrella contexts. `gemma3:e4b` doesn't exist in Ollama's registry — verified via `ollama show gemma3:e4b` returning "model not found." PR #20 introduced it as a typo (stray "e" before "4b").

10 substring replacements across 9 grep-matched lines in 4 files + 1 obsolete README warning paragraph removed:

- `cognitive_castle/config.py:470, 483` — `llm_model` property docstring + default fallback
- `cognitive_castle/cli.py:140, 268 (×2), 1006, 1007` — comment + `cmd_init` defensive double-default + argparse `default=` + help text
- `tests/test_config.py:327, 336` — docstring (rewritten to acknowledge fix) + assertion (`"gemma3:e4b"` → `"gemma3:4b"`)
- `README.md:207-208` — obsolete `⚠️ Note: default is broken` warning paragraph

10+ cosmetic test strings in `tests/test_llm_client.py` + `tests/test_corpus_origin_integration.py` left as-is per spec Non-goals (arbitrary identifiers; tests don't depend on the tag being real).

## Why `gemma3:4b`?

- Matches the apparent original intent of PR #20's typo (`e4b` = `e` + `4b`)
- Real Ollama tag (verified at `ollama.com/library/gemma3`)
- ~3.3 GB — installable on consumer GPU, CPU fallback works
- Multilingual — aligns with Castle's positioning
- Stable tag — won't shift under us (unlike `:latest`)

Variant comparison table in the spec covers why not `1b` (smaller but higher JSON-malformation risk), `12b`/`27b` (too large for default), or `:latest` (moving target).

Spec: `docs/superpowers/specs/2026-05-13-gemma3-default-fix-design.md` (commit `7984e7da`, revised 1× after review).
Plan: `docs/superpowers/plans/2026-05-13-gemma3-default-fix.md`.

## Test plan

- [x] `grep -rn "gemma3:e4b" cognitive_castle/ tests/test_config.py README.md` — zero matches
- [x] `pytest tests/test_config.py -v -k "llm_model"` — 2 passed
- [x] `pytest tests/ --ignore=tests/benchmarks` — 18 failed, 1424 passed (same as develop baseline at `b3cdc4e0` — no new failures)
- [x] `ruff check` + `ruff format --check` clean on 3 production/test files
- [x] `castle init --help` shows `--llm-model gemma3:4b` as documented default
- [x] README's "Going further → Stage 4 LLM-judge" subsection no longer contains the warning paragraph; env-vars / MCP / privacy subsections still flow correctly

## Downstream impact

After this fix, users who accept Castle's defaults run `ollama pull gemma3:4b` (which now succeeds) and then `castle search --llm-rerank` works on first run — unblocking the LLM-judge Stage 4 from PR #3 and SOAR `--soar-boost` from PR #4a without manual `CASTLE_LLM_MODEL` overrides.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed. Report it.

---

## Self-Review

**Spec coverage check:** all 6 acceptance criteria from `2026-05-13-gemma3-default-fix-design.md` (commit `7984e7da`) map to verification steps:

| Spec acceptance | Implemented / verified in |
|---|---|
| #1 grep zero matches | Task 2 Step 11 + Task 3 Step 1 |
| #2 test_config tests pass | Task 2 Step 12 + Task 3 Step 2 |
| #3 no NEW failures | Task 2 Step 13 + Task 3 Step 3 |
| #4 ruff clean | Task 2 Step 14 + Task 3 Step 4 |
| #5 `--help` shows new default | Task 2 Step 15 + Task 3 Step 5 |
| #6 README warning removed | Task 2 Step 10 + Task 3 Step 6 |

**Placeholder scan:**
- No "TBD", "TODO", "implement later."
- Every Edit step shows the EXACT old + new strings.
- Step 9 (docstring rewrite) provides full multi-line old + new blocks.
- Step 10 (README removal) provides the full 3-line old block (warning + blank + MCP) and the 1-line new block (MCP only).

**Type / string consistency:**
- `gemma3:4b` used identically in all 9 substitution sites (Steps 2-9).
- Test assertion (Step 8) matches production default (Step 3) — both `"gemma3:4b"`.
- Argparse help text (Step 7) matches argparse default (Step 6) — both `gemma3:4b`.
- README removal target (Step 10) matches the exact paragraph quoted in the spec's Architecture table row for `README.md:207`.

**No gaps identified.**
