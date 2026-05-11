# CLAUDE.md Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the project's `CLAUDE.md` so every factual claim matches the current code state on `develop` (post-PRs #2 SOTA, #3 hook cleanup, #4 plugin revival, #5 CLI routing).

**Architecture:** Single-file documentation edit. Replace the whole file with new content because the diff would otherwise be ~80% of the file — easier to verify against the spec by reading the new file end-to-end than by walking 20+ Edit calls. One commit for the edit, optional second commit for any fixup found during the verification grep pass.

**Tech Stack:** None — pure markdown.

---

## File structure

### Modified file

| File | Change |
|---|---|
| `CLAUDE.md` | Full content rewrite per spec `bb008e71`. 134 lines → ~190 lines (added Plugin Scaffolding section + retrieval pipeline diagram + 16 new module entries + 4 new Key Files entries). |

No other files touched. No tests required (documentation-only change; spec acceptance is the 9 verification greps).

---

## Task 1: Replace CLAUDE.md content end-to-end

**Files:**
- Modify: `CLAUDE.md` (full rewrite)

This is one commit. The whole file is replaced because the diff would otherwise span ~25 separate Edit calls in tightly-coupled spots (renames in section headers, in tree branches, in inline code blocks, in tables). End-to-end replacement is reviewable as a unit; the spec's 9 verification greps catch correctness.

- [ ] **Step 1: Read the existing CLAUDE.md once for context**

```bash
cat CLAUDE.md
```

Confirm the current shape matches what the spec described (Mission, Design Principles, Contributing, Setup, Commands, Project Structure with mempalace/ tree, Conventions with Windows-coverage parenthetical, Architecture diagram, Key Files for Common Tasks).

- [ ] **Step 2: Write the new CLAUDE.md content**

Use the `Write` tool to replace `CLAUDE.md` entirely with the content below. Preserve every fact verified in the spec's "Source of truth" section.

```markdown
# CLAUDE.md

## The Mission

Memory is identity. When an AI forgets everything between conversations, it cannot build real understanding — of you, your work, your people, your life.

Cognitive Castle exists to solve this. It is a memory system — not a search engine, not a RAG pipeline, not a vector database wrapper. It treats every word you have shared as sacred, stores it verbatim, and makes it instantly available. Your data never leaves your machine. We never summarize. We never paraphrase. We return your exact words.

100% recall is the design requirement — the target every search path is measured against. Anything less means forgetting, and forgetting means starting over.

The name comes from the ancient "method of loci" — the memory palace technique used for thousands of years to organize and recall vast amounts of information by placing it in imagined rooms of an imagined building. We were also inspired by the Zettelkasten method (created by German sociologist Niklas Luhmann) — small cross-referenced index cards that point to each other. We apply both ideas to AI memory:

- **Wings** for broad categories (people, projects, topics)
- **Rooms** for time-based groupings (days, sessions)
- **Drawers** for full verbatim content (your exact words)
- **AAAK compression** for the index layer — a compact symbolic format (via `dialect.py`) that lets an LLM scan thousands of entries instantly and know exactly which drawer to open

## Design Principles

These are non-negotiable. Every PR, every feature, every refactor must honor them.

- **Verbatim always** — Never summarize, paraphrase, or lossy-compress user data. The system searches the index and returns the original words. If a user said it, we store exactly what they said. This is the foundational promise.
- **Incremental only** — Append-only ingest after initial build. Never destroy existing data to rebuild. A crash mid-operation must leave the existing palace untouched.
- **Entity-first** — Everything is keyed by real names with disambiguation by DOB, ID, or context. People matter more than topics.
- **Local-first, zero external API by default** — All extraction, chunking, embedding, and LLM-assisted refinement happens on the user's machine by default, using locally-hosted runtimes (Ollama, LM Studio, llama.cpp, vLLM, unsloth studio, etc.). External providers (Anthropic, OpenAI, Google) are supported via BYOK but are never required and never enabled silently. The system never sends user content to a service the user has not explicitly configured. "Local LLM" is not an external API — Ollama and equivalents running on localhost are part of the user's machine. External BYOK is always a deliberate user choice, never a default and never a silent fallback.
- **Performance budgets** — Hooks under 500ms. Startup injection under 100ms. Memory should feel instant.
- **Privacy by architecture** — The system physically cannot send your data because it never leaves your machine. No telemetry, no phone-home, no external service dependencies for core operations.
- **Background everything** — Filing, indexing, timestamps, and pipeline work happen via hooks in the background. Nothing interrupts the user's conversation. Zero tokens spent on bookkeeping in the chat window.

## Contributing

We welcome bug fixes, performance improvements, new language support, better entity disambiguation, documentation, and test coverage.

We do not accept summarization of user content, cloud storage/sync features, telemetry or analytics, features requiring API keys for core memory, or shortcuts that bypass verbatim storage.

## Setup

```bash
pip install -e ".[dev]"
```

After install, the `castle` and `castle-mcp` commands are on `$PATH`.

### Plugin install (optional)

To use Castle as a Claude Code plugin (auto-registers MCP server + Stop/PreCompact hooks):

```
/plugin marketplace add /path/to/cognitive-castle
/plugin install castle@cognitive-castle
```

Then fully quit and reopen Claude Code. Run `/castle:init` once to complete palace setup.

## Commands

```bash
# Run tests
python -m pytest tests/ -v --ignore=tests/benchmarks

# Run tests with coverage
python -m pytest tests/ -v --ignore=tests/benchmarks --cov=cognitive_castle --cov-report=term-missing

# Lint
ruff check .

# Format
ruff format .

# Format check (CI mode)
ruff format --check .
```

## Project Structure

```
cognitive_castle/
├── mcp_server.py           # MCP server — all read/write tools
├── cli.py                  # CLI dispatcher (`castle` entry point)
├── config.py               # Configuration + input validation (CognitiveCastleConfig)
├── miner.py                # Project file miner
├── convo_miner.py          # Conversation transcript miner
├── convo_scanner.py        # Parse Claude Code conversation directories into ProjectInfo
├── searcher.py             # 3-stage retrieval pipeline (dense + FTS + KG-hop → RRF + recency → cross-encoder rerank)
├── fusion.py               # Pure functions: weighted Reciprocal Rank Fusion + recency multiplier
├── reranker.py             # Cross-encoder reranker wrapper (device-aware: bge-reranker-base on CPU, v2-m3 on GPU)
├── embedding.py            # Sentence-transformers embedding (paraphrase-multilingual-MiniLM-L12-v2, 384-dim)
├── knowledge_graph.py      # Temporal entity-relationship graph (SQLite)
├── palace.py               # Shared palace operations
├── palace_graph.py         # Room traversal + cross-wing tunnels
├── backends/               # Pluggable storage backends (LanceDB default, ChromaDB legacy fallback)
│   ├── base.py             # Abstract interface — implement this for new backends
│   ├── lancedb_backend.py  # LanceDB implementation (default)
│   ├── chroma.py           # ChromaDB implementation (legacy fallback via CASTLE_BACKEND=chroma)
│   └── registry.py         # Backend entry-point loader and default selection
├── dialect.py              # AAAK compression dialect
├── normalize.py            # Transcript format detection + normalization
├── entity_detector.py      # Auto-detect people/projects from content
├── entity_registry.py      # Entity storage and disambiguation
├── corpus_origin.py        # Detect whether a corpus is an AI-dialogue record
├── project_scanner.py      # Detect projects and people from real signal
├── room_detector_local.py  # Local room detection (folder structure or castle.yaml), no API
├── layers.py               # L0-L3 memory wake-up stack
├── onboarding.py           # Interactive first-run setup
├── repair.py               # Palace repair and consistency checks
├── dedup.py                # Deduplication
├── migrate.py              # ChromaDB version migration
├── spellcheck.py           # Auto-correct user messages
├── exporter.py             # Palace data export
├── hooks_cli.py            # Hook management CLI
├── query_sanitizer.py      # Prompt contamination prevention
├── split_mega_files.py     # Split concatenated transcript files
├── diary_ingest.py         # Ingest daily summary files into the palace
├── sweeper.py              # Message-granular miner that catches what file-level miners dropped
├── closet_llm.py           # Generate closets via a user-configured LLM for richer indexing
├── fact_checker.py         # Verify text against known facts in the palace
├── general_extractor.py    # Extract 5 memory types (decisions, preferences, milestones, …) from text
├── instructions_cli.py     # Instruction text output for CLI commands
├── llm_client.py           # Provider abstraction for LLM-assisted entity refinement
├── llm_refine.py           # Optional LLM refinement of regex-detected entities
├── soar_bridge.py          # Drive the SOAR kernel over retrieved memories
└── version.py              # Single source of truth for version

.claude-plugin/             # Claude Code plugin scaffolding (see "Plugin Scaffolding" below)
```

## Plugin Scaffolding

The Claude Code plugin lives at `.claude-plugin/`:

```
.claude-plugin/
├── plugin.json             # plugin manifest (name: castle, mcpServers.castle)
├── marketplace.json        # marketplace listing (name: cognitive-castle)
├── .mcp.json               # MCP server registration
├── hooks/
│   ├── hooks.json          # Stop + PreCompact registration
│   ├── castle-stop-hook.sh        # thin wrapper → `castle hook run`
│   └── castle-precompact-hook.sh
├── skills/castle/
│   └── SKILL.md            # skill manifest
├── commands/
│   └── {help,init,mine,search,status}.md  # /castle:* slash commands
└── README.md               # plugin install docs
```

Install with `/plugin marketplace add . && /plugin install castle@cognitive-castle` inside Claude Code.

## Conventions

- **Python style**: snake_case for functions/variables, PascalCase for classes
- **Linter**: ruff with E/F/W rules
- **Formatter**: ruff format, double quotes
- **Commits**: conventional commits (`fix:`, `feat:`, `test:`, `docs:`, `ci:`)
- **Tests**: `tests/test_*.py`, fixtures in `tests/conftest.py`
- **Coverage**: 85% threshold

## Architecture

```
User → CLI / MCP Server → Storage Backend (LanceDB default, ChromaDB legacy fallback)
                        → SQLite (knowledge graph)

Palace structure:
  WING (person/project)
    └── ROOM (day/topic)
          └── DRAWER (verbatim text chunk)

Index layer (AAAK):
  Compressed pointers → DRAWER locations
  Scanned by LLM to find relevant drawers without reading all content

Knowledge Graph:
  ENTITY → PREDICATE → ENTITY (with valid_from / valid_to dates)

Retrieval pipeline (3-stage, used by both `castle search` and `search_memories`):
  Query
    ├── Stage 1 (parallel recall, ~top-100 each):
    │     ├── Dense vector search (paraphrase-multilingual-MiniLM-L12-v2 via LanceDB)
    │     ├── Sparse FTS search (Tantivy via LanceDB)
    │     └── KG-hop (entity registry lookup → KnowledgeGraph.find_drawers_by_entities)
    ├── Stage 2: weighted RRF + recency multiplier → top-K (K=20 interactive, K=10 hook)
    └── Stage 3: cross-encoder rerank → top-N results
```

## Key Files for Common Tasks

- **Adding an MCP tool**: `cognitive_castle/mcp_server.py` — add handler function + TOOLS dict entry
- **Changing search**: `cognitive_castle/searcher.py` (3-stage pipeline orchestration)
- **Tuning retrieval weights or recency**: `cognitive_castle/config.py` (`weight_dense`, `weight_sparse`, `weight_kg`, `recency_tau_days`, `recency_max_boost`) + `cognitive_castle/fusion.py`
- **Cross-encoder rerank tweaks**: `cognitive_castle/reranker.py`
- **Modifying mining**: `cognitive_castle/miner.py` (project files) or `cognitive_castle/convo_miner.py` (transcripts)
- **Adding a storage backend**: subclass `cognitive_castle/backends/base.py`, register in `backends/__init__.py`
- **Input validation**: `cognitive_castle/config.py` — `sanitize_name()` / `sanitize_content()`
- **Rebuilding palace after embedder change**: `castle reindex --palace <path> --sources <dirs>` (CLI). See `cognitive_castle/cli.py` `cmd_reindex`.
- **Plugin install / packaging**: `.claude-plugin/README.md` + plugin manifest files
- **Tests**: mirror source structure in `tests/test_<module>.py`
```

The above content is the complete new `CLAUDE.md`. Write it verbatim.

- [ ] **Step 3: Run the spec's verification greps**

Run each of the 9 acceptance criteria from the spec:

```bash
# AC1: no MemPalace / mempal references
grep -in "mempal\|MemPalace" CLAUDE.md
# Expected: zero matches

# AC2: no legacy backend/hybrid claims
grep -in "ChromaDB default\|hybrid BM25" CLAUDE.md
# Expected: zero matches

# AC3: cognitive_castle/ paths present
grep -in "cognitive_castle/" CLAUDE.md | head -5
# Expected: matches in Project Structure and Key Files sections (5+)

# AC4: every cognitive_castle/*.py module present in the tree (except __init__/__main__)
for f in $(ls cognitive_castle/*.py | sed 's|cognitive_castle/||' | grep -v "__init__\|__main__" | sort); do
  base="${f%.py}"
  grep -q "$base\.py" CLAUDE.md || echo "MISSING: $f"
done
# Expected: no "MISSING:" lines printed

# AC5: new pipeline + reindex documented
grep -in "castle reindex\|3-stage" CLAUDE.md | head -3
# Expected: at least 2 matches (3-stage in two places, castle reindex in Key Files)

# AC6: plugin scaffolding mentioned
grep -in ".claude-plugin/\|/plugin marketplace add" CLAUDE.md | head -3
# Expected: at least 2 matches

# AC7: deleted hook filenames NOT referenced
grep -in "mempal_save_hook\|mempal_precompact_hook" CLAUDE.md
# Expected: zero matches

# AC8: old embedder name gone
grep -in "all-MiniLM-L6-v2" CLAUDE.md
# Expected: zero matches

# AC9: factual cross-check (manual)
# Read CLAUDE.md end-to-end and compare against:
#   - pyproject.toml:2 → name: "cognitive-castle"
#   - pyproject.toml:33-35 → castle, castle-mcp entry points
#   - pyproject.toml:84-85 → coverage source = ["cognitive_castle"]
#   - cognitive_castle/backends/registry.py:145 → default: str = "lancedb"
#   - cognitive_castle/config.py → embedder_model default is paraphrase-multilingual-MiniLM-L12-v2
#   - ls cognitive_castle/*.py → every module present in the tree
```

If any grep fails, fix the issue in `CLAUDE.md` and re-run the failing grep before committing.

- [ ] **Step 4: Quick markdown render check**

Verify the markdown renders cleanly:

```bash
python3 -c "
with open('CLAUDE.md') as f:
    content = f.read()
# Basic structural checks
assert content.startswith('# CLAUDE.md')
assert '## The Mission' in content
assert '## Plugin Scaffolding' in content
assert '## Architecture' in content
assert '## Key Files for Common Tasks' in content
# Code blocks should balance (count opening triple-backticks)
import re
fences = re.findall(r'^\`\`\`', content, re.MULTILINE)
assert len(fences) % 2 == 0, f'Unbalanced code fences: {len(fences)}'
print(f'OK — {len(content.splitlines())} lines, {len(fences)} code fences')
"
```

Expected: `OK — <N> lines, <even N> code fences`.

- [ ] **Step 5: Run focused regression check (sanity)**

Since this is documentation-only, tests shouldn't be affected. Verify:

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```

Expected: 215 failed, 1276 passed (matching the current `develop` baseline). No change from a doc-only edit.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): refresh CLAUDE.md for current code reality (rebrand + SOTA + plugin)"
```

---

## Task 2: Verify all spec acceptance criteria + handle edge cases

**Files:** none (verification only; small fixups if needed)

- [ ] **Step 1: Re-run the 8 grep-based acceptance criteria as a single command**

```bash
echo "=== AC1: no mempal references ==="
grep -in "mempal\|MemPalace" CLAUDE.md && echo "FAIL" || echo "OK"
echo "=== AC2: no legacy backend/hybrid claims ==="
grep -in "ChromaDB default\|hybrid BM25" CLAUDE.md && echo "FAIL" || echo "OK"
echo "=== AC3: cognitive_castle/ paths present ==="
grep -c "cognitive_castle/" CLAUDE.md
echo "=== AC4: all .py modules in the tree ==="
missing=0
for f in $(ls cognitive_castle/*.py | sed 's|cognitive_castle/||' | grep -v "__init__\|__main__"); do
  grep -q "${f}" CLAUDE.md || { echo "MISSING: $f"; missing=$((missing+1)); }
done
echo "Total missing: $missing"
echo "=== AC5: 3-stage + reindex mentioned ==="
grep -c "castle reindex\|3-stage" CLAUDE.md
echo "=== AC6: plugin scaffolding mentioned ==="
grep -c ".claude-plugin/\|/plugin marketplace add" CLAUDE.md
echo "=== AC7: deleted hook filenames absent ==="
grep -in "mempal_save_hook\|mempal_precompact_hook" CLAUDE.md && echo "FAIL" || echo "OK"
echo "=== AC8: old embedder name absent ==="
grep -in "all-MiniLM-L6-v2" CLAUDE.md && echo "FAIL" || echo "OK"
```

Expected output:
- AC1: OK
- AC2: OK
- AC3: 5+ (any positive number is fine)
- AC4: Total missing: 0
- AC5: 2+
- AC6: 2+
- AC7: OK
- AC8: OK

- [ ] **Step 2: If any criterion fails, fix and commit a small fixup**

If grep finds an unexpected match (e.g., a stray `mempal` in a code comment in the tree), or AC4 reports missing modules, open `CLAUDE.md` and fix in-place via Edit. Then re-run Step 1 to confirm. If a fixup happens:

```bash
git add CLAUDE.md
git commit -m "docs(claude): fix <specific issue> from acceptance verification"
```

If everything passes on the first try (most likely), no additional commit needed.

- [ ] **Step 3: Spot-check that the file renders as the user would see it**

```bash
head -20 CLAUDE.md
sed -n '40,80p' CLAUDE.md  # mid-section
tail -30 CLAUDE.md
```

Visually confirm:
- Mission paragraph says "Cognitive Castle exists"
- Setup section has both `pip install` and "Plugin install (optional)" subsections
- Project Structure tree has `cognitive_castle/` root and lists `fusion.py`, `reranker.py`
- Plugin Scaffolding section exists
- Architecture diagram includes the 3-stage Retrieval pipeline block
- Key Files for Common Tasks includes "castle reindex" and "Plugin install / packaging"

- [ ] **Step 4: Final regression check**

Run the focused test suite one more time as a sanity check:

```bash
pytest tests/ --ignore=tests/benchmarks --ignore=tests/test_collection_metric_invariant.py --ignore=tests/test_hnsw_capacity.py -q 2>&1 | tail -3
```

Expected: same pass/fail counts as Task 1 Step 5. Documentation changes don't move the needle.

(No commit — verification only unless a fixup was committed in Step 2.)

---

## Self-Review

**1. Spec coverage** — every spec acceptance criterion maps to a verification step:
- AC1 (no mempal/MemPalace) → Task 1 Step 3 AC1 + Task 2 Step 1 AC1
- AC2 (no ChromaDB default / hybrid BM25) → Step 3 AC2 + Step 1 AC2
- AC3 (cognitive_castle/ paths) → AC3
- AC4 (every module in tree) → AC4 (with for-loop)
- AC5 (3-stage + reindex) → AC5
- AC6 (plugin scaffolding) → AC6
- AC7 (deleted hooks not referenced) → AC7
- AC8 (old embedder absent) → AC8
- AC9 (no contradiction with pyproject.toml / registry.py / config.py / module list) → Step 3 Step 9 manual cross-check + AC4 covers the module-list part

**2. Placeholder scan** — no "TBD"/"TODO". The complete new `CLAUDE.md` content is shown verbatim in Task 1 Step 2; the implementer writes it exactly as given. Acceptance criteria are concrete bash commands with expected outputs.

**3. Consistency**:
- Module list in the tree (Task 1 Step 2) is internally ordered: core entry points first, then retrieval modules, then knowledge / entity layers, then utility modules, then version. 41 entries total (matches `ls cognitive_castle/*.py | grep -v __init__ | grep -v __main__ | wc -l`).
- `Architecture` section's retrieval pipeline diagram lists `paraphrase-multilingual-MiniLM-L12-v2` consistent with `embedding.py` line in Project Structure.
- "Plugin Scaffolding" section's file list matches `.claude-plugin/` contents post-PR #4.
- Key Files for Common Tasks references match files that actually exist after the SOTA + plugin work.

**4. Known gaps requiring impl-time judgment** — none. Plan is fully prescribed. If the verification greps surface an unexpected mismatch (e.g., a typo in one of the descriptions), Task 2 Step 2 handles the fixup.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-11-claude-md-refresh.md`.
