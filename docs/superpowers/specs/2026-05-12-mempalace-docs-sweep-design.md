# Mempalace Docs Sweep — Design (PR #D of cleanup series)

**Date:** 2026-05-12
**Branch target:** develop
**Scope:** Final PR of the 4-PR cleanup series. Fix functional bugs in CI workflows and example files where mempalace references actively break things, plus brand-update current-tense doc statements across top-level repo docs, benchmarks, devcontainer, and docs/CLOSETS.md/docs/rfcs/002/docs/schema.sql. Preserve historical context (CHANGELOG entries, docs/HISTORY.md, docs/superpowers/, README acknowledgement, schema.sql's legacy-path comment). ~80-100 line changes across ~14 files.

## Background

After PR #A (SOAR), #B (production fixes), #C (tests sweep), the remaining mempalace references live in:
- CI workflows (functionally broken — coverage check references nonexistent `mempalace/` package; version-guard reads nonexistent `mempalace/version.py`)
- Example scripts and tutorials (tell users to run nonexistent `mempalace` commands)
- Top-level repo docs (CONTRIBUTING, AGENTS, etc. — stale brand)
- Benchmarks docs (stale brand)
- Devcontainer config (banner + name field)
- A few docs/ files mixing intentional history with stale brand references

The brainstorm-time inventory found these are NOT just cosmetic: CI workflows have been silently broken since the rebrand (every PR's UNSTABLE status was partly explained by `--cov=mempalace` failing). User-facing examples copy-paste broken commands.

PR #D is the **fourth and final** PR of the cleanup series:
- ✅ #A: SOAR removal (PR #14)
- ✅ #B: Production fixes (PR #15)
- ✅ #C: Tests sweep (PR #16)
- ← **#D: Docs sweep (this spec)**

## Goals

1. CI coverage check works (`--cov=cognitive_castle` reads real source).
2. Version-guard reads `cognitive_castle/version.py` (the real version source).
3. Example scripts/tutorials show working `castle` commands.
4. Top-level repo docs (CONTRIBUTING, AGENTS, MISSION, ROADMAP, SECURITY) use current branding and file paths.
5. Benchmarks docs use current branding.
6. Devcontainer name/banner reflects current project name.
7. docs/CLOSETS.md, docs/rfcs/002, docs/schema.sql have current paths/commands where they're current-tense statements; preserved where they're historical.
8. CHANGELOG entries are preserved as historical record. Only the present-tense intro at line 3 updates.
9. docs/HISTORY.md, docs/superpowers/{specs,plans}/, README.md acknowledgement are untouched.
10. No production code under `cognitive_castle/` or `tests/` is modified.
11. Focused suite remains stable (failed ≤ 65 post-#C baseline; this PR shouldn't change tests).

## Non-goals

- Touching the backward-compat aliases in production code (`MempalaceConfig` aliases at `config.py:643`, `cli.py:43`, `layers.py:30`, `repair.py:34`) — handled in PR #B's scope.
- Removing `~/.mempalace/` legacy state-dir fallback in `_state_dir()` — intentional behavior. Confirmed at spec-review: `cognitive_castle/hooks_cli.py` + `cognitive_castle/miner.py` still have mempalace refs but ALL are intentional back-compat (legacy state-dir + legacy filename fallback). Leave them.
- Rewriting CHANGELOG entries — those describe historical state and stay verbatim.
- Touching `docs/HISTORY.md` — historical narrative.
- Touching `docs/superpowers/{specs,plans}/` — frozen design history.
- Removing or modifying the README's acknowledgement of the MemPalace project as the upstream — historical credit, already correct.
- Changing the GitHub issue links in docs/rfcs/002 that point to `github.com/MemPalace/mempalace/issues/X` — those reference the upstream org's PR/issue history at the time the RFC was forked. Preserve.
- Renaming directories, modules, or anything import-touched.
- Adding new documentation or expanding existing files beyond brand corrections.
- **Touching `website/`** (36 files, 2702 markdown lines — full Vitepress site). Out of scope here because it's its own product surface that deserves its own PR (potentially merged with productization #3 landing-page work). The spec acknowledges website/ has mempalace residue but defers it.

## Source of truth

Brainstorm-time inventory confirmed file-by-file. Reference grep commands documented in this spec's testing strategy.

Categorization rules:
- **UPDATE** if the doc text makes a present-tense statement that is now wrong (e.g., "MemPalace's source code lives at mempalace/" when the directory is `cognitive_castle/`).
- **UPDATE** if it's executable / user-followable instructions that no longer work (CI workflows, example scripts).
- **PRESERVE** if it's a CHANGELOG entry describing a feature added at a specific past version.
- **PRESERVE** if it's a historical credit / origin story.
- **PRESERVE** if it's a deliberately-kept legacy fallback path comment (e.g., `~/.mempalace/knowledge_graph.db` referenced where the production code falls back to that path).

## File-by-file change list

### Critical — functional bug fixes

#### `.github/workflows/ci.yml` (3 occurrences)

Lines 22, 33, 44 all contain:
```yaml
- run: python -m pytest tests/ -v --ignore=tests/benchmarks --cov=mempalace --cov-report=term-missing --cov-fail-under=80 --durations=10
```

Replace `--cov=mempalace` with `--cov=cognitive_castle`:
```yaml
- run: python -m pytest tests/ -v --ignore=tests/benchmarks --cov=cognitive_castle --cov-report=term-missing --cov-fail-under=80 --durations=10
```

#### `.github/workflows/version-guard.yml` (4 occurrences)

Lines 9, 25, 42, 97 reference `mempalace/version.py`. The real path is `cognitive_castle/version.py`. Substitute all four. Context:

```yaml
# Line 9 — path-trigger filter:
- 'mempalace/version.py'
# →
- 'cognitive_castle/version.py'

# Line 25 — grep for version:
py_version=$(grep -E '^__version__' mempalace/version.py | cut -d'"' -f2)
# →
py_version=$(grep -E '^__version__' cognitive_castle/version.py | cut -d'"' -f2)

# Line 42 — markdown table label:
echo "| mempalace/version.py | \`$py_version\` |"
# →
echo "| cognitive_castle/version.py | \`$py_version\` |"

# Line 97 — error message:
echo "Bump mempalace/version.py, pyproject.toml, and all plugin manifests before tagging a stable release."
# →
echo "Bump cognitive_castle/version.py, pyproject.toml, and all plugin manifests before tagging a stable release."
```

#### `examples/basic_mining.py`

Replace all 3 print statements that show `mempalace ...` commands:
```python
# Before:
print(f"  mempalace init {project_dir}")
print(f"  mempalace mine {project_dir}")
print("  mempalace search 'why did we choose this approach'")
# After:
print(f"  castle init {project_dir}")
print(f"  castle mine {project_dir}")
print("  castle search 'why did we choose this approach'")
```

#### `examples/HOOKS_TUTORIAL.md` — **DOUBLY BROKEN**

Two layers of staleness:

1. **Stale shell-script names**: tutorial references `mempal_save_hook.sh` and `mempal_precompact_hook.sh`. These were renamed in PR #5 to `castle-stop-hook.sh` and `castle-precompact-hook.sh` and now live at `.claude-plugin/hooks/`. The old script names DO NOT EXIST anywhere in the repo (confirmed by `find . -name "mempal_*_hook.sh"` returning empty). Users following the tutorial would fail at step 1.
2. **Stale CLI command + env var names**: `mempalace mine`, `MEMPALACE_PYTHON`, `MEMPAL_DIR`.

Updates needed:
- `mempal_save_hook.sh` → `castle-stop-hook.sh` (with note that it lives at `.claude-plugin/hooks/castle-stop-hook.sh` once the plugin is installed)
- `mempal_precompact_hook.sh` → `castle-precompact-hook.sh`
- `mempalace mine` → `castle mine`
- `mempalace init` → `castle init`
- `MemPalace hooks` / `MemPalace repository` → `Cognitive Castle hooks` / `Cognitive Castle repository`
- `MEMPALACE_PYTHON` → `CASTLE_PYTHON` (with note that `MEMPALACE_PYTHON` is honored as deprecation alias per PR #B)
- `MEMPAL_DIR` → `CASTLE_DIR` (similar deprecation pattern exists for the dir alias)

Actually the cleanest fix for HOOKS_TUTORIAL.md is to point readers at the **plugin install path** (`/plugin marketplace add Testimonial/cognitive-castle && /plugin install castle@cognitive-castle`) which auto-registers the hooks. The manual `~/.claude/settings.local.json` config block in the current tutorial is obsolete — that pattern was for when hooks were standalone scripts, before the plugin packaged them.

Implementer should: read the file end-to-end, decide if the manual-config section is salvageable or should be replaced with the plugin-install path entirely. Worst case: simplify HOOKS_TUTORIAL.md to point at the plugin install + a one-paragraph "hooks fire automatically once the plugin is installed".

#### `examples/mcp_setup.md`

`mempalace-mcp` binary doesn't exist; correct binary is `castle-mcp`. Substitute all occurrences.

```bash
sed -i 's/mempalace-mcp/castle-mcp/g' examples/mcp_setup.md
```

#### `examples/convo_import.py` — **broken `mempalace` print statements**

```python
# Before:
print("  mempalace mine ~/claude-sessions/ --mode convos --wing my_project")
print("  mempalace mine ~/chatgpt-exports/ --mode convos")
# After:
print("  castle mine ~/claude-sessions/ --mode convos --wing my_project")
print("  castle mine ~/chatgpt-exports/ --mode convos")
```

Plus any other `mempalace ...` references in the file.

#### `examples/gemini_cli_setup.md`

User-facing guide for Gemini CLI integration. Full brand sweep needed: `MemPalace` → `Cognitive Castle`, `mempalace` commands → `castle`, repository paths, env vars.

```bash
sed -i 's/MemPalace/Cognitive Castle/g; s/mempalace mine/castle mine/g; s/mempalace init/castle init/g; s/mempalace search/castle search/g; s/mempalace-mcp/castle-mcp/g; s/mempalace\//cognitive_castle\//g' examples/gemini_cli_setup.md
```

Implementer should then re-read and fix any sentence that got over-clobbered.

#### `benchmarks/mine_bench.py` — **broken Python import**

Lines 60, 75, 142 currently:
```python
# Line 60:
(dest / "mempalace.yaml").write_text(...)
# Lines 75, 142:
from mempalace import miner
```

Fixes:
- Line 60: `mempalace.yaml` → `castle.yaml` (matches the production filename — see PR #B's i18n + miner work). Also note `cognitive_castle/miner.py:61` lists `mempalace.yml` as a legacy fallback, so writing `castle.yaml` is correct for new fixtures.
- Lines 75, 142: `from mempalace import miner` → `from cognitive_castle import miner`. The `mempalace` package doesn't exist — this import currently raises `ModuleNotFoundError` if anyone runs the benchmark.

#### `.agents/plugins/marketplace.json` — **points to deleted `.codex-plugin/`**

The whole file describes a "mempalace" plugin pointing at `./.codex-plugin/`. That directory was DELETED in PR #8 (Phase 5 of chroma removal). This file is dead code.

Two acceptable resolutions:
1. **Delete the file** if `.agents/` is unused / no one reads marketplace.json from here (verify by checking if anything reads `.agents/plugins/marketplace.json` — probably not).
2. **Update it** to point at `./.claude-plugin/` if it's actively read by some agent runtime. Rename `"mempalace"` → `"castle"`, `"MemPalace"` → `"Cognitive Castle"`.

Implementer should investigate briefly (`grep -rn "\.agents/plugins/marketplace" .`) and decide. **Default: delete** if no consumer is found.

#### `integrations/openclaw/SKILL.md` — plugin metadata with stale name

```yaml
---
name: mempalace
description: "MemPalace — Local AI memory with ..."
homepage: https://github.com/MemPalace/mempalace
---
```

Should be:
```yaml
---
name: castle
description: "Cognitive Castle — Local AI memory with ..."
homepage: https://github.com/Testimonial/cognitive-castle
---
```

Plus any body content referencing `mempalace ...` commands.

### Brand updates — top-level repo docs

#### `CONTRIBUTING.md` (7 refs)

Stale brand + outdated file paths:
- `# Contributing to MemPalace` → `# Contributing to Cognitive Castle`
- `MemPalace is open source` → `Cognitive Castle is open source`
- `git clone https://github.com/<your-username>/mempalace.git` → `git clone https://github.com/<your-username>/cognitive-castle.git`
- `cd mempalace` → `cd cognitive-castle`
- `git remote add upstream https://github.com/MemPalace/mempalace.git` → `git remote add upstream https://github.com/Testimonial/cognitive-castle.git`
- `mempalace/` (file structure description) → `cognitive_castle/`
- `https://github.com/MemPalace/mempalace/issues` → `https://github.com/Testimonial/cognitive-castle/issues`

#### `AGENTS.md` (8 refs)

- Project description references → `Cognitive Castle`
- `--cov=mempalace` (in test-command documentation) → `--cov=cognitive_castle`
- `mempalace/` file paths (Adding an MCP tool / Changing search / etc.) → `cognitive_castle/`

#### `MISSION.md` (5 refs), `ROADMAP.md` (3 refs), `SECURITY.md` (3 refs)

Bulk brand replacement. Use sed:
```bash
sed -i 's/MemPalace/Cognitive Castle/g; s/mempalace/cognitive_castle/g' MISSION.md ROADMAP.md SECURITY.md
```

Then read each file to verify the replacements don't break sentences (e.g., a `mempalace.io` URL would now read `cognitive_castle.io` which is wrong; if any such URLs exist, fix manually).

### Brand updates — benchmarks

#### `benchmarks/README.md` (3 refs), `benchmarks/BENCHMARKS.md` (4 refs), `benchmarks/HYBRID_MODE.md` (2 refs)

Similar sed sweep. Be careful about:
- Code blocks showing commands — those should use `castle ...` not `mempalace ...`
- Module references — `mempalace/searcher.py` etc. should become `cognitive_castle/searcher.py`
- General brand mentions — `MemPalace` → `Cognitive Castle`

```bash
sed -i 's/MemPalace/Cognitive Castle/g; s/mempalace\//cognitive_castle\//g; s/mempalace mine/castle mine/g; s/mempalace search/castle search/g; s/mempalace init/castle init/g' benchmarks/README.md benchmarks/BENCHMARKS.md benchmarks/HYBRID_MODE.md
```

### Brand updates — devcontainer

#### `.devcontainer/devcontainer.json` (1 ref)

```json
// Before:
"name": "MemPalace",
// After:
"name": "Cognitive Castle",
```

#### `.devcontainer/post-create.sh` (1 ref)

```bash
# Before:
echo "=== MemPalace Dev Container Setup ==="
# After:
echo "=== Cognitive Castle Dev Container Setup ==="
```

### Brand updates — docs/

#### `docs/CLOSETS.md` (6 refs)

Update outdated path/collection references:
- `mempalace mine` → `castle mine` (2 references)
- `mempalace_closets` ChromaDB collection → `castle_closets` (current LanceDB collection name per `cognitive_castle/dedup.py:COLLECTION_NAME`)
- `mempalace_drawers` → `castle_drawers`
- `mempalace/palace.py` → `cognitive_castle/palace.py`
- `mempalace/searcher.py` → `cognitive_castle/searcher.py`
- "ChromaDB collection" → "LanceDB collection" (since chroma was removed in PR #8)

Implementer should also verify `castle_closets` / `castle_drawers` are the actual collection names by reading `cognitive_castle/dedup.py` or `cognitive_castle/palace.py` — if production uses different names, match reality.

#### `docs/rfcs/002-source-adapter-plugin-spec.md`

Mixed treatment:
- **UPDATE** user-facing command references in the RFC body: `mempalace mine` → `castle mine`, `pip install mempalace-source-<name>` → `pip install cognitive-castle-source-<name>` (or similar — verify the actual entry-point group name in `cognitive_castle/backends/__init__.py` is `cognitive_castle.backends`, so adapter packages would follow that pattern).
- **UPDATE** prose mentions of `MemPalace` (the project name) → `Cognitive Castle`.
- **PRESERVE** the historical GitHub issue links at `https://github.com/MemPalace/mempalace/issues/X` and `pulls/X` — those reference the upstream org's history at the time the RFC was forked.

Strategy: do a careful sed for command/prose updates, then visually verify the GitHub links section is unchanged:

```bash
# Update user-facing commands and brand prose (NOT URLs):
sed -i 's/mempalace mine/castle mine/g; s/`mempalace`/`castle`/g; s/MemPalace source adapters/Cognitive Castle source adapters/g; s/MemPalace to function/Cognitive Castle to function/g' docs/rfcs/002-source-adapter-plugin-spec.md

# Then manually inspect and update any remaining current-tense `MemPalace` mentions in the prose, leaving the github.com/MemPalace/mempalace/ URLs intact.
```

If the simple sed doesn't catch everything, the implementer should `grep -nE "mempalace|MemPalace" docs/rfcs/002-source-adapter-plugin-spec.md` after the sed and triage each remaining hit.

#### `docs/schema.sql` (1 of 2 refs updated)

```sql
-- Before:
-- MemPalace Knowledge Graph Schema
-- SQLite database at ~/.mempalace/knowledge_graph.db

-- After:
-- Cognitive Castle Knowledge Graph Schema
-- SQLite database at ~/.castle/knowledge_graph.db (legacy fallback: ~/.mempalace/knowledge_graph.db)
```

The legacy path comment is retained to document the fallback that `_state_dir()` provides.

#### `CHANGELOG.md` — line 3 only

```markdown
# Before (line 3):
All notable changes to [MemPalace](https://github.com/MemPalace/mempalace) are documented in this file.

# After:
All notable changes to [Cognitive Castle](https://github.com/Testimonial/cognitive-castle) (formerly MemPalace) are documented in this file.
```

All other CHANGELOG entries (lines 4-end) preserved verbatim as historical record.

### Preserved — DO NOT MODIFY

- `CHANGELOG.md` lines 4-end (all version entries)
- `docs/HISTORY.md` (historical narrative)
- `docs/superpowers/specs/` and `docs/superpowers/plans/` (frozen)
- `README.md` line 345 acknowledgement (historical credit, already correct)
- `docs/schema.sql` legacy path comment (intentional fallback documentation)
- All GitHub issue/PR links in `docs/rfcs/002-source-adapter-plugin-spec.md` at `github.com/MemPalace/mempalace/...` (historical references to upstream)
- All production code (`cognitive_castle/`, `tests/`)

## Testing strategy

1. **CI workflows fixed:**
   ```bash
   grep -n "mempalace" .github/workflows/ci.yml
   grep -n "mempalace" .github/workflows/version-guard.yml
   ```
   Expected: zero matches in either file.

2. **Examples use working commands:**
   ```bash
   grep -nE "mempalace (init|mine|search)|mempalace-mcp|MEMPALACE_PYTHON" examples/
   ```
   Expected: zero matches.

3. **Top-level docs:**
   ```bash
   grep -nE "mempalace|MemPalace" CONTRIBUTING.md AGENTS.md MISSION.md ROADMAP.md SECURITY.md
   ```
   Expected: zero matches.

4. **Benchmarks:**
   ```bash
   grep -nE "mempalace|MemPalace" benchmarks/README.md benchmarks/BENCHMARKS.md benchmarks/HYBRID_MODE.md
   ```
   Expected: zero matches.

5. **Devcontainer:**
   ```bash
   grep -nE "mempalace|MemPalace" .devcontainer/devcontainer.json .devcontainer/post-create.sh
   ```
   Expected: zero matches.

6. **docs/ partial sweep:**
   ```bash
   grep -nE "mempalace|MemPalace" docs/CLOSETS.md docs/rfcs/002-source-adapter-plugin-spec.md docs/schema.sql | grep -v "MemPalace/mempalace" | grep -v "legacy fallback"
   ```
   Expected: zero matches outside the preserved patterns (GitHub historical links, schema.sql legacy fallback comment).

7. **CHANGELOG line 3 updated:**
   ```bash
   sed -n '3p' CHANGELOG.md | grep -c "Cognitive Castle"
   ```
   Expected: 1 (the updated intro).

8. **CHANGELOG entries preserved:**
   ```bash
   wc -l CHANGELOG.md
   ```
   Expected: unchanged from develop (no entries added/removed; only line 3 reworded).

9. **Preserved files untouched:**
   ```bash
   git diff develop..HEAD -- README.md docs/HISTORY.md docs/superpowers/ | head -5
   ```
   Expected: empty (no changes to any of these).

10. **No production code modified:**
    ```bash
    git diff --name-only develop..HEAD | grep -E "^(cognitive_castle|tests)/"
    ```
    Expected: empty.

11. **Focused suite stable:**
    ```bash
    pytest tests/ --ignore=tests/benchmarks -q --tb=no 2>&1 | tail -3
    ```
    Expected: failed ≤ 65 (post-#C baseline).

12. **CI workflow validity:**
    The new `--cov=cognitive_castle` flag references a real package. To smoke-test locally without pushing:
    ```bash
    python -m pytest tests/test_branding.py -q --cov=cognitive_castle --cov-report=term-missing 2>&1 | tail -5
    ```
    Expected: coverage report runs (regardless of failed-under threshold). If `--cov=cognitive_castle` is invalid, this errors.

## Risk

- **Low-Medium.** Most changes are mechanical sed replacements. The risks:
  - **sed over-matches**: if a prose sentence says "MemPalace" in a context that needs to remain historical (e.g., "originally named MemPalace"), the sed would clobber it. Mitigated by: spot-check the diff after each sed.
  - **URL collateral damage**: `s/mempalace/cognitive_castle/g` would corrupt URLs like `github.com/MemPalace/mempalace/...`. Mitigated by: use lower-case-only `s/mempalace\//cognitive_castle\//g` (with the trailing slash) where path-segment is meant, NOT bare `s/mempalace/cognitive_castle/g`. Per-file judgment.
  - **CHANGELOG history loss**: if sed runs across CHANGELOG, entries get rewritten. Mitigated by: only touching line 3, not the whole file.
- **No CI risk for this PR specifically**: the CI workflow fixes will actually make CI more strict (coverage check will run for real instead of failing silently). Existing PRs that relied on the broken CI to "pass" might surface real coverage issues post-merge. Document in PR body.

## Acceptance criteria

1. `.github/workflows/ci.yml` has zero `mempalace` references; `--cov=cognitive_castle` is the new flag.
2. `.github/workflows/version-guard.yml` has zero `mempalace` references; reads `cognitive_castle/version.py`.
3. `examples/basic_mining.py`, `examples/HOOKS_TUTORIAL.md`, `examples/mcp_setup.md` show `castle` commands (not `mempalace`).
4. `CONTRIBUTING.md`, `AGENTS.md`, `MISSION.md`, `ROADMAP.md`, `SECURITY.md` have zero current-tense `mempalace` / `MemPalace` references.
5. `benchmarks/README.md`, `benchmarks/BENCHMARKS.md`, `benchmarks/HYBRID_MODE.md` have zero `mempalace` / `MemPalace` references.
6. `.devcontainer/devcontainer.json` has `"name": "Cognitive Castle"`. `.devcontainer/post-create.sh` banner updated.
7. `docs/CLOSETS.md` uses `castle_closets`/`castle_drawers`/`cognitive_castle/*` paths.
8. `docs/rfcs/002-source-adapter-plugin-spec.md` body uses `castle` commands and `Cognitive Castle` prose, but `github.com/MemPalace/mempalace/...` GitHub links are PRESERVED (verify the issue-link URLs are unchanged).
9. `docs/schema.sql` header updated; legacy path comment retained with clarifying note.
10. `CHANGELOG.md` line 3 updated; all other entries verbatim from develop.
11. `README.md` UNCHANGED. `docs/HISTORY.md` UNCHANGED. `docs/superpowers/` UNCHANGED.
12. `git diff --name-only develop..HEAD | grep -E "^(cognitive_castle|tests)/"` returns empty (no production code touched).
13. Focused suite: failed ≤ 65 (post-#C baseline).
14. PR commit count ≤ 3 (allows surgical fixes if HOOKS_TUTORIAL.md rewrite or `.agents/plugins/marketplace.json` decision needs a separate commit).
15. `examples/HOOKS_TUTORIAL.md` references the current hook script names (`castle-stop-hook.sh`, `castle-precompact-hook.sh`) OR has been simplified to point at the plugin install path.
16. `examples/convo_import.py`, `examples/gemini_cli_setup.md` use `castle` commands.
17. `benchmarks/mine_bench.py` imports `from cognitive_castle import miner` (not `mempalace`); fixture writes `castle.yaml` (not `mempalace.yaml`).
18. `.agents/plugins/marketplace.json` is either deleted (preferred if dead code) or updated to point at `.claude-plugin/` with current brand naming.
19. `integrations/openclaw/SKILL.md` frontmatter uses current name + homepage.
20. `website/` directory is **NOT** modified by this PR (deferred to a separate PR — confirmed via `git diff --name-only develop..HEAD | grep ^website/` returning empty).
