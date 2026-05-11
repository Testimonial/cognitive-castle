# Cognitive Castle — CLAUDE.md Refresh

**Date:** 2026-05-10
**Last revised:** 2026-05-11 (scope expanded for SOTA + plugin + CLI work that landed afterward)
**Branch target:** develop
**Status:** Phase 2 revision. Original spec (this file at commit `6533e32`) targeted the rebrand drift in CLAUDE.md (naming, backend defaults, module list). Since then, four PRs have landed that introduce additional drift: SOTA retrieval upgrade (PR #2), plugin revival + rebrand completion (PR #4), CLI search pipeline routing (PR #5), and a small hook-tests cleanup (PR #3). This revision expands the spec to cover those.
**Scope:** documentation only (single file: `CLAUDE.md`).

## Background — what changed from the previous revision

The original spec captured three rebrand-drift axes (naming, ChromaDB default, module list). It was correct at the time. Since `6533e32` was committed, the following work has landed on `develop`, none of which the original spec accounts for:

- **PR #2 (SOTA retrieval upgrade)** — New retrieval architecture: 3-stage pipeline (parallel dense + Tantivy FTS + KG-hop → weighted RRF + recency → cross-encoder rerank). New modules `cognitive_castle/fusion.py` and `cognitive_castle/reranker.py`. New `castle reindex` CLI command. Default embedder is now `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (multilingual, 384-dim) — the original spec's `all-MiniLM-L6-v2` description on `embedding.py` is now wrong.
- **PR #4 (plugin revival + rebrand completion)** — The `.claude-plugin/` directory now contains a working Castle Claude Code plugin (manifest, hooks, slash commands, skill). Top-level legacy hook scripts at `hooks/mempal_save_hook.sh` and `hooks/mempal_precompact_hook.sh` were DELETED. The original spec said to keep them; reality says they're gone.
- **PR #5 (CLI search pipeline routing)** — The `castle search` CLI now routes through the same 3-stage pipeline as `search_memories` (MCP path). Doesn't directly affect CLAUDE.md, but the searcher.py module description should reflect the new pipeline.

The original spec stays mostly load-bearing. Most of its section-by-section edits still apply unchanged. This revision **adds** four new sections (Retrieval pipeline, Plugin scaffolding, `castle reindex` command, embedder + module-list adjustments) and **corrects** two existing sections (hooks-block guidance + embedding.py description).

## Goals

1. Every factual claim in CLAUDE.md matches the current code state on `develop` (post-PRs #2, #3, #4, #5).
2. The Project Structure tree includes every relevant Python module under `cognitive_castle/`, including the post-SOTA additions `fusion.py` and `reranker.py`.
3. The Architecture section reflects the 3-stage retrieval pipeline, not the legacy hybrid BM25 + vector summary.
4. The Setup section mentions both the `pip install -e ".[dev]"` path AND the plugin install path for users who want the Claude Code plugin.
5. Reading CLAUDE.md gives a future agent an accurate mental model of how the project works — no chasing dead references.

## Non-goals

- Source-code rebrand of `MempalaceConfig` (renamed to `CognitiveCastleConfig` in PR #4, with an alias kept), `~/.mempalace/palace/` (still the live data path; migration is a separate future spec), etc. These are deferred.
- Removing ChromaDB code entirely. `backends/chroma.py` still ships as a fallback (`backends/registry.py:181` says "Register lancedb as the in-tree default; keep chroma as fallback"). CLAUDE.md reflects this status, doesn't pretend chroma is gone.
- Pre-existing test failures (215 in focused suite). Documentation-only change.
- Source code edits inside `cognitive_castle/`. CLAUDE.md is documentation only.

## Source of truth

Every claim in the new `CLAUDE.md` must match observable code/config:

- Project name → `pyproject.toml:2` (`name = "cognitive-castle"`)
- CLI entry points → `pyproject.toml:33-35` (`castle`, `castle-mcp`)
- Coverage source → `pyproject.toml:84-85` (`source = ["cognitive_castle"]`)
- Coverage threshold → `pyproject.toml:88` (`fail_under = 85`)
- Default backend → `cognitive_castle/backends/registry.py:145` (`default: str = "lancedb"`); fallback path `backends/registry.py:181` (`"keep chroma as fallback"`)
- Default embedder model → `cognitive_castle/config.py` `embedder_model` default property: `"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"` (384-dim, multilingual)
- Module list → `ls cognitive_castle/*.py` (excluding `__init__.py`, `__main__.py`)
- Retrieval pipeline implementation → `cognitive_castle/searcher.py` `_new_pipeline_search()` (3-stage: dense + FTS + KG-hop → fuse → rerank)
- New retrieval modules → `cognitive_castle/fusion.py`, `cognitive_castle/reranker.py`
- New CLI command → `castle reindex` registered in `cognitive_castle/cli.py`
- Plugin scaffolding → `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.claude-plugin/hooks/{castle-stop,castle-precompact}-hook.sh`
- Top-level legacy hook scripts → **gone** (deleted in PR #4). Do not reference them anywhere in CLAUDE.md.

## Section-by-section changes

### Mission (line 7)

`MemPalace exists to solve this.` → `Cognitive Castle exists to solve this.`

The Wings/Rooms/Drawers/AAAK paragraph below is correct and stays.

### Setup (lines 36–40) — **expanded**

After the `pip install -e ".[dev]"` block, append a short subsection covering both install paths:

```markdown
After install, the `castle` and `castle-mcp` commands are on `$PATH`.

### Plugin install (optional)

To use Castle as a Claude Code plugin (auto-registers MCP server + Stop/PreCompact hooks):

    /plugin marketplace add /path/to/cognitive-castle
    /plugin install castle@cognitive-castle

Then fully quit and reopen Claude Code. Run `/castle:init` once to complete palace setup.
```

This addition reflects the working plugin scaffolding from PR #4.

### Commands (lines 44–59)

Line 49: `--cov=mempalace` → `--cov=cognitive_castle` to match `pyproject.toml`.

### Project Structure (lines 63–96) — **expanded**

- Root directory label `mempalace/` → `cognitive_castle/`.
- `backends/` block:
  - Parent comment "Pluggable storage backends (ChromaDB default)" → "Pluggable storage backends (LanceDB default, ChromaDB legacy fallback)".
  - List `lancedb_backend.py` (default) and `registry.py` (entry-point loader, default selection) alongside the existing `base.py` and `chroma.py`. Update `chroma.py`'s comment to mark it as the fallback.
- Add the missing modules with one-line descriptions sourced from each module's docstring. Now includes the SOTA additions:
  - `closet_llm.py` — Generate closets via a user-configured LLM for richer indexing
  - `convo_scanner.py` — Parse Claude Code conversation directories into ProjectInfo
  - `corpus_origin.py` — Detect whether a corpus is an AI-dialogue record
  - `diary_ingest.py` — Ingest daily summary files into the palace
  - `embedding.py` — Sentence-transformers embedding (paraphrase-multilingual-MiniLM-L12-v2, 384-dim)
  - `fact_checker.py` — Verify text against known facts in the palace
  - `fusion.py` — Pure functions: weighted Reciprocal Rank Fusion + recency multiplier (PR #2)
  - `general_extractor.py` — Extract 5 memory types (decisions, preferences, milestones, …) from text
  - `instructions_cli.py` — Instruction text output for CLI commands
  - `llm_client.py` — Provider abstraction for LLM-assisted entity refinement
  - `llm_refine.py` — Optional LLM refinement of regex-detected entities
  - `project_scanner.py` — Detect projects and people from real signal
  - `reranker.py` — Cross-encoder reranker wrapper (device-aware: bge-reranker-base on CPU, v2-m3 on GPU) (PR #2)
  - `room_detector_local.py` — Local room detection (folder structure or castle.yaml), no API
  - `soar_bridge.py` — Drive the SOAR kernel over retrieved memories
  - `sweeper.py` — Message-granular miner that catches what file-level miners dropped
- Update `searcher.py` description from "Semantic search (hybrid BM25 + vector)" → "3-stage retrieval pipeline (dense + FTS + KG-hop → RRF + recency → cross-encoder rerank)".
- `migrate.py` description: keep "ChromaDB version migration" — `migrate.py` is still a Chroma-version recovery tool; the comment stays accurate.
- **Hooks block: DELETE.** The original spec said to keep the filename references for `hooks/mempal_save_hook.sh` / `hooks/mempal_precompact_hook.sh`. Reality post-PR #4: those files are gone. Remove the `hooks/` entry from Project Structure entirely. Hook wrappers now live at `.claude-plugin/hooks/castle-stop-hook.sh` and `.claude-plugin/hooks/castle-precompact-hook.sh`, but those are plugin internals — they go in a new Plugin Scaffolding section, not the main Project Structure tree.
- Add a new top-level entry to Project Structure: `.claude-plugin/` — Claude Code plugin scaffolding (manifest, hooks, slash commands, skill). See "Plugin scaffolding" subsection below.

### Plugin Scaffolding (NEW section, insert after Project Structure)

Add a short new section between Project Structure and Conventions:

```markdown
## Plugin Scaffolding

The Claude Code plugin lives at `.claude-plugin/`:

    .claude-plugin/
    ├── plugin.json            # plugin manifest (name: castle, mcpServers.castle)
    ├── marketplace.json       # marketplace listing (name: cognitive-castle)
    ├── .mcp.json              # MCP server registration
    ├── hooks/
    │   ├── hooks.json         # Stop + PreCompact registration
    │   ├── castle-stop-hook.sh        # thin wrapper → `castle hook run`
    │   └── castle-precompact-hook.sh
    ├── skills/castle/
    │   └── SKILL.md           # skill manifest
    ├── commands/
    │   └── {help,init,mine,search,status}.md  # /castle:* slash commands
    └── README.md              # plugin install docs

Install with `/plugin marketplace add . && /plugin install castle@cognitive-castle` inside Claude Code.
```

### Conventions (lines 98–105)

Line 105: drop the parenthetical "(80% on Windows due to ChromaDB file lock cleanup)". `pyproject.toml` sets a uniform `fail_under = 85` and the Chroma-specific Windows cleanup is no longer load-bearing post-LanceDB migration. Replace with: `**Coverage**: 85% threshold`.

### Architecture (lines 109–124) — **expanded**

Line 110: `Storage Backend (ChromaDB default, pluggable)` → `Storage Backend (LanceDB default, ChromaDB legacy fallback)`.

Below the existing User → CLI/MCP → Storage Backend → SQLite (KG) diagram, add a new sub-block showing the retrieval pipeline:

```markdown
Retrieval pipeline (3-stage, used by both `castle search` and `search_memories`):
  Query
    ├── Stage 1 (parallel recall, ~top-100 each):
    │     ├── Dense vector search (paraphrase-multilingual-MiniLM-L12-v2 via LanceDB)
    │     ├── Sparse FTS search (Tantivy via LanceDB)
    │     └── KG-hop (entity registry lookup → KnowledgeGraph.find_drawers_by_entities)
    ├── Stage 2: weighted RRF + recency multiplier → top-K (K=20 interactive, K=10 hook)
    └── Stage 3: cross-encoder rerank → top-N results
```

The Palace structure / Index layer / Knowledge Graph diagrams below the existing diagram are unchanged.

### Key Files for Common Tasks (lines 126–133) — **expanded**

- Replace every `mempalace/<file>` path with `cognitive_castle/<file>`.
- Add new task pointers:
  - **Tuning retrieval weights or recency** → `cognitive_castle/config.py` (`weight_dense`, `weight_sparse`, `weight_kg`, `recency_tau_days`, `recency_max_boost`) + `cognitive_castle/fusion.py`
  - **Rebuilding palace after embedder change** → `castle reindex --palace <path> --sources <dirs>` (CLI). See `cognitive_castle/cli.py` `cmd_reindex`.
  - **Cross-encoder rerank tweaks** → `cognitive_castle/reranker.py`
  - **Plugin install / packaging** → `.claude-plugin/README.md` + plugin manifest files

## Verification

Acceptance criteria:

1. `grep -in "mempal\|MemPalace" CLAUDE.md` → no matches (case-insensitive).
2. `grep -in "ChromaDB default\|hybrid BM25" CLAUDE.md` → no matches.
3. `grep -in "cognitive_castle/" CLAUDE.md` → matches in Project Structure and Key Files sections.
4. Every module under `cognitive_castle/*.py` appears in the Project Structure tree, excluding `__init__.py` and `__main__.py` (package plumbing). `version.py` stays listed. `fusion.py` and `reranker.py` are present (the two SOTA additions).
5. `grep -in "castle reindex\|3-stage" CLAUDE.md` → matches (the new retrieval pipeline + new CLI command are documented).
6. `grep -in ".claude-plugin/\|/plugin marketplace add" CLAUDE.md` → matches (plugin scaffolding mentioned).
7. `grep -in "mempal_save_hook\|mempal_precompact_hook" CLAUDE.md` → zero matches (the deleted files aren't referenced).
8. `grep -in "all-MiniLM-L6-v2" CLAUDE.md` → zero matches (the original embedder is gone).
9. No factual claim in the new `CLAUDE.md` contradicts `pyproject.toml`, `cognitive_castle/backends/registry.py`, `cognitive_castle/config.py`, or the contents of `cognitive_castle/`.

## Risk

Low. Documentation-only change to a single file. No code, tests, or CI affected. Reversible via `git revert`. Slightly higher risk than the original spec because we're now describing more (retrieval pipeline, plugin scaffolding) — more opportunity for factual drift if the description gets out of sync with the code. The verification grep set catches the obvious classes of mistake.
