# `gemma3:e4b` → `gemma3:4b` default-LLM-tag fix — Design Spec

**Date:** 2026-05-13
**Status:** Revised after review (2026-05-13) — ready for implementation plan
**Scope:** small follow-up surfaced during PR #3 (LLM-as-judge Stage 4) spec review

## Revision history

- **2026-05-13 (initial):** First draft, approved.
- **2026-05-13 (post-review):** Three findings:
  1. **Off-by-one substitution count.** Spec said "9 substitutions" but `cli.py:268` has the broken tag TWICE on one line (`getattr(args, "llm_model", "gemma3:e4b") or "gemma3:e4b"`). Real count is **10 substring replacements across 9 grep-matched lines**. Architecture table footer + Acceptance #1 framing both clarified.
  2. **`gemma3:4b` is a REGISTRY tag** (exists at `ollama.com/library/gemma3`), not necessarily pulled locally on every developer's machine. Fix makes the default name a VALID registry tag so `ollama pull gemma3:4b` succeeds; users still need to pull on first run (or have it already). Background + Data Flow clarified.
  3. **README warning removal needs blank-line handling.** Line 207 is a single warning paragraph with adjacent blank lines. Removing just line 207 leaves a double blank line; plan-writer should delete the warning + one adjacent blank line to preserve formatting. Architecture note added.

## Background

Castle's documented default LLM model is `gemma3:e4b` — a tag that **does not exist in Ollama's registry**. Verified live during PR #3 review (2026-05-13): `ollama show gemma3:e4b` returns "model not found" AND `ollama pull gemma3:e4b` would fail similarly (the tag isn't published at `ollama.com/library/gemma3`). The real tags published there are: `1b`, `4b`, `12b`, `27b`, `270m`, `latest` (plus `-it-qat` and `-cloud` variants).

After this fix, the new default `gemma3:4b` is a real registry tag — users still need to `ollama pull gemma3:4b` on first run (or have it already pulled), but at least the `pull` command succeeds. The bug-fix unlocks the standard "configure default → pull model → it works" Ollama UX that's broken today.

The bug was introduced by PR #20 (`chore: pyproject metadata + LLM default cleanup`, commit `e8e4974a`), which migrated four defaults from `gemma4:e4b` → `gemma3:e4b`. Both tags are non-existent — `e4b` was likely a typo for `4b` with a stray "e." The mistake survived review because nothing in CI actually pulls the model; production callers either pass `CASTLE_LLM_MODEL` explicitly or hit the LLM provider's graceful fallback (which, until PR #3, was a silent return-empty rather than a loud error).

Three downstream PRs explicitly carried the broken default forward as a known issue:
- **PR #3 (LLM-judge Stage 4):** spec section "Background" disclosed the bug. README "Going further" section added a `⚠️ Note` warning users that `gemma3:e4b` doesn't exist and they must override `CASTLE_LLM_MODEL`.
- **PR #4a (SOAR bridge):** umbrella context flagged this as a queued follow-up.
- **PR #4a follow-up (hits-created-at, merged at `b3cdc4e0`):** noted in its umbrella context that the gemma fix was still queued.

This spec closes the gap. After the fix, users who accept defaults get a working Ollama model on first run.

## Goal

Replace every production reference to `gemma3:e4b` with `gemma3:4b` (the most likely original intent — typo "e" + "4b"). Update the test that asserts the default literal value. Remove the obsolete README warning that flagged the bug.

## Why `gemma3:4b` and not other variants?

| Variant | Size | Pros | Cons |
|---|---|---|---|
| **`gemma3:4b` (chosen)** | ~3.3 GB | Likely original intent (typo "e4b" = "e" + "4b"). Multilingual. Stable tag. Good capability for LLM-judge JSON output (10 candidates × 600 chars). | Larger than 1b — first-pull takes longer. |
| `gemma3:1b` | ~815 MB | Lowest barrier to entry. Faster first pull. | Higher risk of malformed JSON output. (LLM-judge has graceful fallback, so this isn't a correctness risk — just a "rule doesn't fire" risk.) |
| `gemma3:latest` | tracking | Tracks Google's current pick. | Moving target — Google can change what `:latest` resolves to, breaking reproducibility across user installs. |
| `gemma3:12b` / `:27b` | 8.1 GB / 17 GB | More capable. | Too large for a default — many users couldn't run it locally. |

The `4b` choice is the smallest defensible model that:
- Was the apparent intent of the original typo
- Reliably produces JSON-mode output for the LLM-judge task
- Fits on consumer GPU + CPU fallback
- Is multilingual (Castle's positioning + this user's Czech/English data)

## Non-goals

- **Updating cosmetic test strings.** 10+ sites in `tests/test_llm_client.py` and `tests/test_corpus_origin_integration.py` use `"gemma3:e4b"` as an arbitrary model-name string identifier. Tests pass with any string — no semantic dependency on the broken tag. Updating them would be cosmetic-only churn.
- **Changing the default provider.** Still Ollama by default.
- **Picking a different size variant** (1b / 12b / 27b). `4b` chosen for balance + typo-intent + size.
- **Adding model-existence validation at `castle init` time.** Existing `LLMProvider.check_available()` already pings the configured endpoint and gracefully reports unavailable; that's a separate concern.
- **Migrating users' existing `castle.yaml` files** that explicitly set `llm_model: "gemma3:e4b"`. Their file overrides the default, so they're already opting out. If they want the fix, they can edit the file (the README warning being removed makes this discoverable).

## Architecture

Pure string-replacement across **9 sites in 4 files**. No logic changes, no new helpers, no schema impact.

| File | Site | Current | After |
|---|---|---|---|
| `cognitive_castle/config.py:470` | `llm_model` property docstring | `Default: ``"gemma3:e4b"``` | `Default: ``"gemma3:4b"``` |
| `cognitive_castle/config.py:483` | property default fallback | `.get("llm_model", "gemma3:e4b")` | `.get("llm_model", "gemma3:4b")` |
| `cognitive_castle/cli.py:140` | comment | `# gemma3:e4b) can return...` | `# gemma3:4b) can return...` |
| `cognitive_castle/cli.py:268` | `cmd_init` fallback | `getattr(args, "llm_model", "gemma3:e4b") or "gemma3:e4b"` | `getattr(args, "llm_model", "gemma3:4b") or "gemma3:4b"` |
| `cognitive_castle/cli.py:1006` | argparse `default=` | `default="gemma3:e4b"` | `default="gemma3:4b"` |
| `cognitive_castle/cli.py:1007` | argparse `help=` text | `default: gemma3:e4b for Ollama` | `default: gemma3:4b for Ollama` |
| `tests/test_config.py:327` | docstring note | `Note: both are 'gemma3:e4b'...` | `Note: both default to 'gemma3:4b'...` (full paragraph rewrites to acknowledge the fix) |
| `tests/test_config.py:336` | assertion | `assert cfg.llm_model == "gemma3:e4b"` | `assert cfg.llm_model == "gemma3:4b"` |
| `README.md:207` | obsolete warning paragraph | `> **⚠️ Note:** Castle's documented default LLM model is gemma3:e4b, but that tag doesn't exist...` | **REMOVED** — warning is obsolete after this PR |

**Total: 10 substring replacements across 9 grep-matched lines + 1 README paragraph removal.** No LOC delta in production code.

**Note on `cli.py:268`:** this single line contains the broken tag TWICE (defensive double-default pattern `getattr(args, "llm_model", "gemma3:e4b") or "gemma3:e4b"`). The implementer must update both occurrences — either via a single `Edit` with `replace_all=True` on that string within the file, or by replacing the full line at once. Don't miss the second one.

**Note on `README.md:207`:** the warning is a standalone paragraph with adjacent blank lines (the markdown looks like `\n\n> **⚠️ Note:** ...\n\n`). Removing only line 207 would leave a double-blank-line gap. The implementer should delete the warning paragraph + one adjacent blank line to preserve the surrounding section's formatting flow.

## Data flow

### Before this fix
```
User installs Castle → runs `castle init` (accepting defaults)
  → cli.py:1006 default = "gemma3:e4b"
  → cli.py:268 cmd_init reads args.llm_model = "gemma3:e4b"
  → LLMProvider.check_available() pings Ollama with "gemma3:e4b"
  → Ollama returns 404 "model not found"
  → castle init flow either (a) prompts user to fix, or (b) silently falls
    through to heuristics-only (depending on flag).
  → SOAR --llm-rerank fires apply_soar_boosts; _load_sml succeeds; agent
    attempts to call gemma3:e4b → graceful fallback fires "[soar] LLM
    call failed... falling back" → hits returned without LLM-judge boost
```

### After this fix
```
User installs Castle → runs `castle init` (accepting defaults)
  → cli.py:1006 default = "gemma3:4b"
  → cli.py:268 cmd_init reads args.llm_model = "gemma3:4b"
  → LLMProvider.check_available() pings Ollama with "gemma3:4b"
  → if user has Ollama installed with gemma3:4b pulled: ✅ works on first try
  → if user has Ollama but no gemma3:4b: clear error pointing at `ollama pull gemma3:4b`
  → if user has no Ollama: existing graceful fallback to heuristics-only
```

The fix REMOVES a silent failure path (the "ollama can't find this specific tag" case for users who accept defaults).

## Error handling

No new error paths. The fix REMOVES an error path that was always going to fail for default-accepting users. Existing graceful-degrade behavior of `LLMProvider.check_available()` continues to work for users without Ollama installed at all.

## Testing

### Two existing test_config.py assertions adapt

The test at `tests/test_config.py:336`:
```python
assert cfg.llm_model == "gemma3:e4b"
```
becomes:
```python
assert cfg.llm_model == "gemma3:4b"
```

The docstring above the test (line 327) currently says:
> "Note: both are 'gemma3:e4b' which is a known pre-existing broken tag (the model doesn't exist in Ollama's registry). Tracking the same broken default keeps cmd_init and the judge consistent — both will be fixed together in a follow-up PR."

After the fix, this docstring is obsolete and is rewritten to:
> "Note: both `cfg.llm_model` and `cmd_init`'s `--llm-model` default point at `gemma3:4b` — a real Ollama tag. The original PR #20 introduced `gemma3:e4b` as a typo; this PR fixed it."

The test name (`test_llm_model_default_matches_cmd_init_default`) stays accurate — both still match.

### No new tests required

This is a one-string-replacement bug fix. The existing test was already asserting the literal default value and will catch any regression of the bug (someone re-typing "e4b" would fail the assertion immediately).

### Smoke

`ollama show gemma3:4b` on the developer's machine confirms the tag is real. Already verified during this spec's brainstorm exploration (it's in the published `ollama.com/library/gemma3` tag list).

## Acceptance criteria

1. `grep -rn "gemma3:e4b" cognitive_castle/ tests/test_config.py README.md` returns **zero matches** (cosmetic test strings in `tests/test_llm_client.py` + `tests/test_corpus_origin_integration.py` are intentionally left alone — out of scope).
2. `pytest tests/test_config.py -v -k "llm_model"` — the 2 existing tests pass with the new value.
3. `pytest tests/ --ignore=tests/benchmarks` — no NEW failures vs. develop baseline at commit `b3cdc4e0` (current baseline is 18 pre-existing CI-UNSTABLE failures).
4. `ruff check` + `ruff format --check` clean on the 4 touched files.
5. `castle init --help` output shows `--llm-model gemma3:4b` (or equivalent) as the documented default. NO mention of `gemma3:e4b`.
6. README at line ~207 no longer contains the "default is broken" warning. The "Going further: Stage 4 LLM-judge" subsection still mentions the LLM-provider config flow (just without the broken-tag caveat).

## Spec self-review (post-revision, 2026-05-13)

1. **Placeholders:** None. All replacements are exact strings shown verbatim in the Architecture table.
2. **Internal consistency:** Architecture, Data Flow, Testing, and Acceptance all reference:
   - `gemma3:4b` as the new default (consistent everywhere)
   - **10 substring replacements across 9 grep-matched lines** (config.py × 2, cli.py × 4 with one line having 2 occurrences, test_config.py × 2) + 1 README paragraph removal
   - Cosmetic test strings (`tests/test_llm_client.py` + `tests/test_corpus_origin_integration.py`) explicitly out of scope
3. **Scope:** Single-purpose string-replacement bug fix. 9 substitution sites in 4 files (10 actual replacements counting the double-occurrence at `cli.py:268`). Not decomposable into sub-projects.
4. **Ambiguity:** "Cosmetic test strings out of scope" stated explicitly in 3 places (Non-goals, Architecture footer, Acceptance #1). Variant choice (`4b` over `1b`/`latest`/`12b`/`27b`) stated explicitly in a comparison table with reasoning. Double-occurrence on `cli.py:268` explicitly flagged in Architecture note. README warning paragraph removal explicitly noted with surrounding-blank-line handling.
5. **Empirical grounding:**
   - Real Ollama gemma3 tags verified at `ollama.com/library/gemma3` (1b, 4b, 12b, 27b, 270m, latest)
   - `gemma3:4b` confirmed as a real registry tag (subset of the verified tag list). Note: registry-existing ≠ pulled locally; users may need `ollama pull gemma3:4b` on first run.
   - `gemma3:e4b` confirmed broken via `ollama show gemma3:e4b` → "model not found"
   - 9 substitution sites (1 README + 2 tests + 6 production code) located via `grep -rn "gemma3:e4b"` across the repo
   - README warning at line 207 confirmed via direct read
6. **Post-review #1 findings addressed:**
   - ✅ Substitution count corrected `9 → 10` (cli.py:268 has the broken tag twice on one line).
   - ✅ Background clarifies `gemma3:4b` is a registry tag (fix unlocks `ollama pull` UX; users still need to pull).
   - ✅ README paragraph-removal blank-line handling noted in Architecture.
   - ✅ "Production sites" wording corrected to "substitution sites" in self-review (avoids conflating test/README/production).
