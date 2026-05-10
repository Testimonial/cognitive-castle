# Cognitive Castle — CLAUDE.md Refresh

**Date:** 2026-05-10
**Branch target:** develop
**Scope:** documentation only (single file: `CLAUDE.md`)

## Background

`CLAUDE.md` was authored under the prior "MemPalace" branding and has drifted from the current code on three independent axes:

1. **Naming** — the project rebranded to "Cognitive Castle"; `CLAUDE.md` still says "MemPalace" and references the `mempalace/` package directory and `--cov=mempalace`.
2. **Backend defaults** — `CLAUDE.md` claims "ChromaDB default". Recent commits completed a LanceDB migration; `pyproject.toml` ships only `lancedb` as a dependency and `backends/registry.py:145` defaults to `lancedb`. Chroma remains in-tree as a fallback (`CASTLE_BACKEND=chroma`).
3. **Module list** — the Project Structure tree omits ~14 modules that exist in `cognitive_castle/`: `closet_llm`, `convo_scanner`, `corpus_origin`, `diary_ingest`, `embedding`, `fact_checker`, `general_extractor`, `instructions_cli`, `llm_client`, `llm_refine`, `project_scanner`, `room_detector_local`, `soar_bridge`, `sweeper`.

These drifts mislead future agents reading `CLAUDE.md` for orientation. The fix is mechanical but spans several sections.

**Out of scope:** source-code rebrand. The package still contains `MempalaceConfig`, `~/.mempalace/` paths, hook script internals, and a stale `cognitive_castle/README.md`. Those are tracked separately.

## Source of truth

Every claim in the new `CLAUDE.md` must match observable code/config:

- Project name → `pyproject.toml:2` (`name = "cognitive-castle"`)
- CLI entry points → `pyproject.toml:33-35` (`castle`, `castle-mcp`)
- Coverage source → `pyproject.toml:84-85` (`source = ["cognitive_castle"]`)
- Coverage threshold → `pyproject.toml:88` (`fail_under = 85`)
- Default backend → `cognitive_castle/backends/registry.py:145` (`default: str = "lancedb"`)
- Module list → `ls cognitive_castle/*.py` (excluding `__init__.py`, `__main__.py`, `version.py`)
- Hook filenames → `ls hooks/` (filenames remain `mempal_save_hook.sh` and `mempal_precompact_hook.sh`; do not rename in this scope)

## Section-by-section changes

### Mission (line 7)

`MemPalace exists to solve this.` → `Cognitive Castle exists to solve this.`

The Wings/Rooms/Drawers/AAAK paragraph below is correct and stays.

### Setup (lines 36–40)

After the `pip install -e ".[dev]"` block, append a one-line note: "After install, the `castle` and `castle-mcp` commands are on `$PATH`." This calls out the entry points defined in `pyproject.toml:33-35` so the section doesn't leave readers wondering how to invoke the tool.

### Commands (lines 44–59)

Line 49: `--cov=mempalace` → `--cov=cognitive_castle` to match `pyproject.toml`.

### Project Structure (lines 63–96)

- Root directory label `mempalace/` → `cognitive_castle/`.
- `backends/` block:
  - Parent comment "Pluggable storage backends (ChromaDB default)" → "Pluggable storage backends (LanceDB default, ChromaDB fallback)".
  - List `lancedb_backend.py` (default) and `registry.py` (entry-point loader, default selection) alongside the existing `base.py` and `chroma.py`. Update `chroma.py`'s comment to mark it as the fallback.
- Add the missing modules with one-line descriptions sourced from each module's docstring:
  - `closet_llm.py` — Generate closets via a user-configured LLM for richer indexing
  - `convo_scanner.py` — Parse Claude Code conversation directories into ProjectInfo
  - `corpus_origin.py` — Detect whether a corpus is an AI-dialogue record
  - `diary_ingest.py` — Ingest daily summary files into the palace
  - `embedding.py` — Sentence-transformers embedding (all-MiniLM-L6-v2, 384-dim)
  - `fact_checker.py` — Verify text against known facts in the palace
  - `general_extractor.py` — Extract 5 memory types (decisions, preferences, milestones, …) from text
  - `instructions_cli.py` — Instruction text output for CLI commands
  - `llm_client.py` — Provider abstraction for LLM-assisted entity refinement
  - `llm_refine.py` — Optional LLM refinement of regex-detected entities
  - `project_scanner.py` — Detect projects and people from real signal
  - `room_detector_local.py` — Local room detection (folder structure or castle.yaml), no API
  - `soar_bridge.py` — Drive the SOAR kernel over retrieved memories
  - `sweeper.py` — Message-granular miner that catches what file-level miners dropped
- `migrate.py` description: keep "ChromaDB version migration" — `migrate.py` is still a Chroma-version recovery tool; the comment stays accurate.
- Hooks block: filenames stay (`mempal_save_hook.sh`, `mempal_precompact_hook.sh`) — those are the actual on-disk filenames.

### Conventions (lines 98–105)

Line 105: drop the parenthetical "(80% on Windows due to ChromaDB file lock cleanup)". `pyproject.toml` sets a uniform `fail_under = 85` and the Chroma-specific Windows cleanup is no longer load-bearing post-LanceDB migration. Replace with: `**Coverage**: 85% threshold`.

### Architecture (lines 109–124)

Line 110: `Storage Backend (ChromaDB default, pluggable)` → `Storage Backend (LanceDB default, ChromaDB fallback, pluggable)`. The Palace structure / Index layer / Knowledge Graph diagrams below are unchanged.

### Key Files for Common Tasks (lines 126–133)

Replace every `mempalace/<file>` path with `cognitive_castle/<file>`. The conceptual mapping (which file to edit for which task) is unchanged.

## Verification

Acceptance criteria:

1. `grep -in "mempal\|MemPalace" CLAUDE.md` → no matches (case-insensitive).
2. `grep -in "ChromaDB default" CLAUDE.md` → no matches.
3. `grep -in "cognitive_castle/" CLAUDE.md` → matches in Project Structure and Key Files sections.
4. Every module under `cognitive_castle/*.py` appears in the Project Structure tree, excluding `__init__.py` and `__main__.py` (package plumbing). `version.py` stays listed (it's already in the current tree as the version source of truth).
5. `ruff format --check CLAUDE.md` is N/A (markdown), but the file should render as valid GitHub-flavored markdown.
6. No factual claim in the new `CLAUDE.md` contradicts `pyproject.toml`, `cognitive_castle/backends/registry.py`, or the contents of `cognitive_castle/`.

## Risk

Low. Documentation-only change to a single file. No code, tests, or CI affected. Reversible via `git revert`.
