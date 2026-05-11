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
